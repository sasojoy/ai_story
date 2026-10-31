"""全服狀態存在 SQLite（線上架構設計第三節）；介面與各方法的說明見 world_state.WorldStateStore。

- `world` 表一列：SharedWorldState 除了賽季以外的小資料，整份覆寫。
- `seasons` 表一季一列：WorldState，整份覆寫。換季不刪資料：賽季編號加一、新的一季另起一列，
  舊的一季原封不動留著。
- 傳聞（`rumors` 表）與江湖史（`chronicle` 表）一則一列：寫的時候只新增還沒有流水號的；讀全服狀態時不讀回來，
  只有 get_season() 讀（給畫面看）。江湖史跨季保留。
- 目前的決戰在 `battles` 表（一場一列、整份覆寫，`world.active_battle_id` 指向它），結算過的回合在
  `battle_rounds` 表一回合一列（只寫不讀回）。換季、開新的一場時舊的那一場留著；收場的那幾場給參戰者補送戰報
  （ended_battles）。
- 自創武學（`skills`）、煉製配方（`recipes`）、投靠名冊（`faction_rolls`）一列一筆、記著第幾季：
  換季不用清空，新的一季自然是空的，上一季的留著。第 2 版再加改過的名字（`skill_aliases`）、合併出來的意境
  （`insights`、`insight_recipes`）、第一個練成絕學的人（`masters`），同樣照季分；功法、改過的名字與意境
  共用一個名字空間（`_name_taken`）。第 3 版加感悟的首悟紀錄（`insight_firsts`，悟意境設計 0.2b）：只是紀錄，
  意境本身私有、存在角色存檔裡，不佔名字空間。第 4 版加全服的兵器配方（`gear_recipes`，兵器設計 4.4）：照季分，名字也在同一個名字空間裡。
  投靠名冊的 faction 欄寫 `allied.roll_key`（豪強分屬兩軍時依附的豪強是「haoqiang@guan」，結構不動）：`faction_of` 回算哪一方、
  `faction_counts` 照陣營、`roll_of`／`roll_counts` 是鍵本身。
- 每個會寫的方法自己是一筆交易；呼叫端已經在 action_lock() 裡時，併進那一筆（見 database.Database）。
"""
from __future__ import annotations

import json
import random
from collections.abc import Callable, Collection
from contextlib import AbstractContextManager
from pathlib import Path
from sqlite3 import Connection, Row

from . import allied, calendar, divine
from .battle_instance import BattleInstance, BattleRoundRecord, SiegeInfo, shift_deadlines, start_muster
from .characters import name_key
from .database import Database, open_database
from .characters import name_key
from .martial_arts import Insight, MartialArt
from .models import BattleDef, Content
from .state import GearFind, Rumor, SignatureClaim, WeaponRecipe, WorldState
from .world_state import (
    JADE_SEAL_FRAGMENT_COUNT, CompanionProgress, DivineRegistry, JadeSealFragment, SealDuel, SealRegistry, SealView, SeasonPhase,
    SharedWorldState, SortieDuel,
    fresh_season,
    jade_seal_summary, stamp_season,
)


def open_world(path: Path | None = None) -> SqliteWorldStore:
    """開 path 那個資料庫檔的全服狀態；沒給就開預設的資料庫（環境變數 TIANXIA_DB 或 saves/tianxia.db）。"""
    return SqliteWorldStore(open_database(path))


class SqliteWorldStore:
    def __init__(self, db: Database):
        self.db = db

    def action_lock(self, timeout: float | None = None) -> AbstractContextManager[Connection]:
        return self.db.transaction(timeout)

    # ── 整份讀寫 ──────────────────────────────────────

    def read(self) -> SharedWorldState:
        with self.db.snapshot() as conn:
            return self._load(conn)

    def mutate(self, fn: Callable[[SharedWorldState], None]) -> SharedWorldState:
        """整份讀出、交給 fn 改、整份寫回。fn 裡面不能再呼叫 mutate、mutate_season、mutate_battle 或靠它們
        實作的方法：內層寫的會被這裡最後的存檔蓋掉，所以巢狀時直接丟 RuntimeError（見 Database.rewriting）。"""
        with self.db.rewriting(), self.db.transaction() as conn:
            state = self._load(conn)
            fn(state)
            self._save(conn, state)
            return state

    def _load(self, conn: Connection, logs: bool = False) -> SharedWorldState:
        row = conn.execute("SELECT data, active_battle_id FROM world WHERE id = 1").fetchone()
        state = SharedWorldState() if row is None else SharedWorldState.model_validate_json(row["data"])
        state.season = self._load_season(conn, state.season_number, logs)
        if row is not None and row["active_battle_id"] is not None:
            state.active_battle = self._load_battle(conn, row["active_battle_id"])
        state.sieges = [self._load_battle(conn, rid) for rid in state.siege_records]  # 攻城戰（領地爭奪第二批）：另存一串
        return state

    def _save(self, conn: Connection, state: SharedWorldState) -> None:
        battle_id = self._save_battle(conn, state.season_number, state.active_battle)  # 先寫決戰：world 要指向它
        state.siege_records = [self._save_battle(conn, state.season_number, b) for b in state.sieges]  # 攻城戰：一場一列，world 記流水號
        conn.execute(
            "INSERT INTO world (id, data, active_battle_id) VALUES (1, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET data = excluded.data, active_battle_id = excluded.active_battle_id",
            (state.model_dump_json(exclude={"season", "active_battle", "sieges"}), battle_id),
        )
        self._save_season(conn, state.season_number, state.season)

    def _load_season(self, conn: Connection, number: int, logs: bool = False) -> WorldState:
        """logs=True 才把這一季的傳聞與江湖史讀回來（只有 get_season 要）。其他時候兩個清單是空的：
        往裡面加的照樣寫得進去（見 _save_season），已經寫過的也不會因此被蓋掉。"""
        row = conn.execute("SELECT data FROM seasons WHERE number = ?", (number,)).fetchone()
        season = WorldState() if row is None else WorldState.model_validate_json(row["data"])
        if logs:
            season.rumors = [
                _rumor(r) for r in conn.execute("SELECT * FROM rumors WHERE season = ? ORDER BY id", (number,))
            ]
            season.chronicle = [
                _chronicle_entry(r)
                for r in conn.execute("SELECT * FROM chronicle WHERE season = ? ORDER BY id", (number,))
            ]
        return season

    def _save_season(self, conn: Connection, number: int, season: WorldState) -> None:
        """季的小資料整份覆寫；傳聞與江湖史只新增還沒有流水號的（id 是 None），寫完把流水號填回去。
        交易撤回時流水號已經填上了：Game 每個動作開頭都 sync、重新讀一份賽季，不會拿著它繼續用。"""
        conn.execute(
            "INSERT INTO seasons (number, data) VALUES (?, ?) ON CONFLICT (number) DO UPDATE SET data = excluded.data",
            (number, season.model_dump_json(exclude={"rumors", "chronicle"})),
        )
        for rumor in season.rumors:
            if rumor.id is None:
                rumor.id = conn.execute(
                    "INSERT INTO rumors (season, time, layer, faction, region, location, character, named, text) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        number, rumor.time, rumor.layer, rumor.faction, rumor.region, rumor.location,
                        rumor.character, rumor.named, rumor.text,
                    ),
                ).lastrowid
        for entry in season.chronicle:
            if entry.id is None:
                entry.id = conn.execute(
                    "INSERT INTO chronicle (season, time, location, text) VALUES (?, ?, ?, ?)",
                    (number, entry.time, entry.location, entry.text),
                ).lastrowid

    def _load_battle(self, conn: Connection, battle_id: int) -> BattleInstance:
        row = conn.execute("SELECT data FROM battles WHERE id = ?", (battle_id,)).fetchone()
        battle = BattleInstance.model_validate_json(row["data"])
        battle.record_id = battle_id
        return battle

    def _save_battle(self, conn: Connection, season: int, battle: BattleInstance | None) -> int | None:
        """決戰整份覆寫（不含回合紀錄），回傳它的流水號；結算過的回合只新增還沒有流水號的。"""
        if battle is None:
            return None
        data = battle.model_dump_json(exclude={"record_id", "rounds"})
        if battle.record_id is None:
            battle.record_id = conn.execute(
                "INSERT INTO battles (season, battle_def, phase, outcome_title, data) VALUES (?, ?, ?, ?, ?)",
                (season, battle.battle_id, battle.phase, battle.outcome_title, data),
            ).lastrowid
        else:
            conn.execute(
                "UPDATE battles SET phase = ?, outcome_title = ?, data = ? WHERE id = ?",
                (battle.phase, battle.outcome_title, data, battle.record_id),
            )
        for record in battle.rounds:
            if record.id is None:
                record.id = conn.execute(
                    "INSERT INTO battle_rounds (battle_id, data) VALUES (?, ?)",
                    (battle.record_id, record.model_dump_json(exclude={"id"})),
                ).lastrowid
        return battle.record_id

    # ── 武學命名登記與煉製配方 ──────────────────────────────

    def _season_number(self, conn: Connection) -> int:
        row = conn.execute("SELECT json_extract(data, '$.season_number') AS number FROM world WHERE id = 1").fetchone()
        return 1 if row is None or row["number"] is None else int(row["number"])

    def get_skill(self, name: str) -> MartialArt | None:
        with self.db.snapshot() as conn:
            row = conn.execute(
                "SELECT data FROM skills WHERE season = ? AND name = ?", (self._season_number(conn), name.strip()),
            ).fetchone()
        return None if row is None else MartialArt.model_validate_json(row["data"])

    def is_skill_name_taken(self, name: str) -> bool:
        with self.db.snapshot() as conn:
            return _name_taken(conn, self._season_number(conn), name.strip())

    def is_character_name(self, name: str) -> bool:
        # 角色存檔（characters.CharacterStore）跟全服狀態在同一個資料庫檔；主鍵就是名號的 casefold（characters.name_key）。
        # 只看有沒有這一列，不讀 is_bot：命名過濾回的話不能透露是不是假人
        with self.db.snapshot() as conn:
            return conn.execute("SELECT 1 FROM characters WHERE key = ?", (name_key(name),)).fetchone() is not None

    def claim_skill_name(self, art: MartialArt) -> bool:
        with self.db.transaction() as conn:
            return _insert_skill(conn, self._season_number(conn), art)

    def lookup_recipe(self, key: str) -> MartialArt | None:
        with self.db.snapshot() as conn:
            return _recipe(conn, self._season_number(conn), key)

    def recipe_keys(self) -> set[str]:
        with self.db.snapshot() as conn:
            rows = conn.execute("SELECT key FROM recipes WHERE season = ?", (self._season_number(conn),)).fetchall()
        return {row["key"] for row in rows}

    def claim_recipe(self, key: str, art: MartialArt) -> tuple[MartialArt | None, bool]:
        with self.db.transaction() as conn:
            season = self._season_number(conn)
            existing = _recipe(conn, season, key)
            if existing is not None:
                return existing, False
            if not _insert_skill(conn, season, art):
                return None, False  # 名字撞到，呼叫端換名字
            conn.execute(
                "INSERT INTO recipes (season, key, skill_name, creator) VALUES (?, ?, ?, ?)",
                (season, key, art.name.strip(), art.creator),
            )
            return art, True

    def rename_skill(self, skill_name: str, new_name: str) -> bool:
        new_name = new_name.strip()
        with self.db.transaction() as conn:
            season = self._season_number(conn)
            row = conn.execute(
                "SELECT data FROM skills WHERE season = ? AND name = ?", (season, skill_name),
            ).fetchone()
            if row is None or _name_taken(conn, season, new_name):
                return False
            art = MartialArt.model_validate_json(row["data"])
            art.name = new_name
            conn.execute(
                "UPDATE skills SET data = ? WHERE season = ? AND name = ?", (art.model_dump_json(), season, skill_name),
            )
            conn.execute(
                "INSERT INTO skill_aliases (season, name, skill_name) VALUES (?, ?, ?)", (season, new_name, skill_name),
            )
            return True

    def renamed_skill_ids(self) -> set[str]:
        with self.db.snapshot() as conn:
            rows = conn.execute("SELECT skill_name FROM skill_aliases WHERE season = ?", (self._season_number(conn),)).fetchall()
        return {row["skill_name"] for row in rows}

    def get_insight(self, name: str) -> Insight | None:
        with self.db.snapshot() as conn:
            row = conn.execute(
                "SELECT data FROM insights WHERE season = ? AND name = ?", (self._season_number(conn), name.strip()),
            ).fetchone()
        return None if row is None else Insight.model_validate_json(row["data"])

    def lookup_insight_recipe(self, key: str) -> Insight | None:
        with self.db.snapshot() as conn:
            return _insight_recipe(conn, self._season_number(conn), key)

    def claim_insight_recipe(self, key: str, insight: Insight) -> tuple[Insight | None, bool]:
        with self.db.transaction() as conn:
            season = self._season_number(conn)
            existing = _insight_recipe(conn, season, key)
            if existing is not None:
                return existing, False
            name = insight.name.strip()
            if _name_taken(conn, season, name):
                return None, False
            conn.execute(
                "INSERT INTO insights (season, name, creator, data) VALUES (?, ?, ?, ?)",
                (season, name, insight.creator, insight.model_dump_json()),
            )
            conn.execute(
                "INSERT INTO insight_recipes (season, key, insight_name, creator) VALUES (?, ?, ?, ?)",
                (season, key, name, insight.creator),
            )
            return insight, True

    # ── 兵器配方（兵器設計 4.4；第 4 版）：打造隱藏配方第一批起不再新增 ──────────────────────

    def lookup_weapon_recipe(self, key: str) -> WeaponRecipe | None:
        with self.db.snapshot() as conn:
            return _gear_recipe(conn, self._season_number(conn), key)

    def claim_weapon_recipe(self, key: str, recipe: WeaponRecipe) -> tuple[WeaponRecipe | None, bool]:
        with self.db.transaction() as conn:
            season = self._season_number(conn)
            existing = _gear_recipe(conn, season, key)
            if existing is not None:
                return existing, False
            name = recipe.name.strip()
            if _name_taken(conn, season, name):
                return None, False  # 名字撞到，呼叫端換名字
            conn.execute(
                "INSERT INTO gear_recipes (season, key, name, creator, data) VALUES (?, ?, ?, ?, ?)",
                (season, key, name, recipe.creator, recipe.model_dump_json()),
            )
            return recipe, True

    # ── 隱藏配方的發現（打造隱藏配方設計 7.1；第 4 版的 gear_recipes，不升版）──────

    # 神器輪替（正式季整合 5.6、10.4）：蓋了章的季打的神器，原品那一筆記在全服登記（SharedWorldState.divine.finds，跨季、全服一把），
    # 不在照季分的 gear_recipes。下面四個方法照同一個判斷讀哪一邊（FB-402）：registry 是 None 時看這一季蓋沒蓋輪替的章
    # （_rotating，同 claim_gear_find）；呼叫端手上有那一件神器時照它打出來那一季的判斷傳（Equipment.collected），
    # 所以輪替用過再關掉時，帶過季的那一把照舊讀登記、沒章那一季打的照季分的那一列

    def lookup_gear_find(self, key: str, registry: bool | None = None) -> GearFind | None:
        with self.db.snapshot() as conn:
            season = self._season_number(conn)
            found = _registry_find(conn, season, key, registry)
            if found is not None or registry:
                return found
            return _gear_find(conn, season, key)

    def claim_gear_find(self, key: str, find: GearFind) -> tuple[GearFind, bool]:
        if not key.startswith("鑄|"):
            raise ValueError(f"隱藏配方的鍵要是「鑄|配方 id」：{key}")
        with self.db.transaction() as conn:
            season = self._season_number(conn)
            if find.divine and _rotating(conn, season):  # 輪替季的神器：全服一把，誰先寫進登記誰拿原品（同一筆交易）
                reg = _divine(conn)
                rid = key.removeprefix("鑄|")
                if rid in reg.finds:
                    return reg.finds[rid], False
                find.season = season
                reg.finds[rid] = find
                _put_divine(conn, reg)
                return find, True
            existing = _gear_find(conn, season, key)
            if existing is not None:
                return existing, False
            conn.execute(  # 名字欄寫鍵本身：一定不是合法的名字，不佔名字空間（_name_taken 查得到它，但沒人能取這個名字）
                "INSERT INTO gear_recipes (season, key, name, creator, data) VALUES (?, ?, ?, ?, ?)",
                (season, key, key, find.creator, find.model_dump_json()),
            )
            return find, True

    def add_copy(self, key: str, registry: bool | None = None) -> None:
        with self.db.transaction() as conn:
            season = self._season_number(conn)
            if registry or (registry is None and _rotating(conn, season)):
                reg = _divine(conn)
                rid = key.removeprefix("鑄|")
                if rid in reg.finds:  # 輪替季的神器：全服仿品數跨季累加
                    reg.finds[rid].copies += 1
                    _put_divine(conn, reg)
                    return
                if registry:
                    return
            find = _gear_find(conn, season, key)
            if find is None:
                return
            find.copies += 1
            conn.execute(
                "UPDATE gear_recipes SET data = ? WHERE season = ? AND key = ?", (find.model_dump_json(), season, key),
            )

    def name_divine(self, key: str, owner: str, name: str, registry: bool | None = None) -> str | None:
        name = name.strip()
        with self.db.transaction() as conn:
            season = self._season_number(conn)
            reg = _divine(conn)
            rid = key.removeprefix("鑄|")
            use_registry = registry or (registry is None and _rotating(conn, season))
            if use_registry and rid not in reg.finds and registry:
                return "gone"
            if use_registry and rid in reg.finds:  # 輪替季的原品：名字跨季保留，之後別人不能取（_name_taken 也查登記）
                find = reg.finds[rid]
                if find.owner != owner:
                    return "owner"
                if find.divine_name is not None:
                    return "named"
                if _name_taken(conn, season, name):
                    return "taken"
                find.divine_name = name
                _put_divine(conn, reg)
                return None
            find = _gear_find(conn, season, key)
            if find is None or not find.divine:
                return "gone"
            if find.owner != owner:
                return "owner"
            if find.divine_name is not None:
                return "named"
            if _name_taken(conn, season, name):
                return "taken"
            find.divine_name = name
            conn.execute(  # 名字欄從鍵本身改成定的名字：之後 _name_taken 查得到它（gear_recipes_by_name 也擋同一季重名）
                "UPDATE gear_recipes SET name = ?, data = ? WHERE season = ? AND key = ?", (name, find.model_dump_json(), season, key),
            )
            return None

    def divine_records(self) -> list[tuple[int, GearFind]]:
        with self.db.snapshot() as conn:
            rows = conn.execute(
                "SELECT season, data FROM gear_recipes WHERE key LIKE '鑄|%' ORDER BY season, key",
            ).fetchall()
            reg = _divine(conn)
        finds = [(row["season"], GearFind.model_validate_json(row["data"])) for row in rows]
        finds += [(find.season or 0, find) for find in reg.finds.values()]  # 輪替季的原品（全服登記，跨季）
        finds.sort(key=lambda pair: pair[0])  # 穩定排序：同一季照季分的那幾列在前
        return [(season, find) for season, find in finds if find.divine and find.owner]

    def signature_records(self) -> list[tuple[int, dict[str, SignatureClaim]]]:
        with self.db.snapshot() as conn:
            rows = conn.execute(
                "SELECT number, json_extract(data, '$.signature_arms') AS arms FROM seasons ORDER BY number",
            ).fetchall()
        records = []
        for row in rows:
            raw = json.loads(row["arms"]) if row["arms"] else {}
            if raw:
                records.append((row["number"], {cid: SignatureClaim.model_validate(claim) for cid, claim in raw.items()}))
        return records

    # ── 合到舊的（武學與成長設計 12.2）──────────────────────

    def fused_arts(self) -> list[MartialArt]:
        with self.db.snapshot() as conn:
            rows = conn.execute(
                "SELECT data FROM skills WHERE season = ? AND json_extract(data, '$.origin') = 'fused' ORDER BY rowid",
                (self._season_number(conn),),
            ).fetchall()
        return [MartialArt.model_validate_json(row["data"]) for row in rows]

    def merged_insights(self) -> list[Insight]:
        with self.db.snapshot() as conn:
            rows = conn.execute(
                "SELECT data FROM insights WHERE season = ? ORDER BY rowid", (self._season_number(conn),),
            ).fetchall()
        return [Insight.model_validate_json(row["data"]) for row in rows]

    def season_firsts(self) -> dict[str, int]:
        with self.db.snapshot() as conn:
            season = self._season_number(conn)
            arts = conn.execute(
                "SELECT DISTINCT r.skill_name, json_extract(s.data, '$.creator') AS creator, "
                "json_extract(s.data, '$.co_creator') AS co FROM recipes r "
                "JOIN skills s ON s.season = r.season AND s.name = r.skill_name WHERE r.season = ? "
                "AND COALESCE(json_extract(s.data, '$.preset'), 0) = 0",
                (season,),
            ).fetchall()
            insights = conn.execute(
                "SELECT DISTINCT r.insight_name, json_extract(i.data, '$.creator') AS creator, "
                "json_extract(i.data, '$.co_creator') AS co FROM insight_recipes r "
                "JOIN insights i ON i.season = r.season AND i.name = r.insight_name WHERE r.season = ?",
                (season,),
            ).fetchall()
        counts: dict[str, int] = {}
        for row in [*arts, *insights]:
            for who in {row["creator"], row["co"]} - {None, ""}:
                counts[who] = counts.get(who, 0) + 1
        return counts

    def link_recipe(self, key: str, skill_name: str, creator: str | None) -> tuple[MartialArt | None, bool]:
        with self.db.transaction() as conn:
            season = self._season_number(conn)
            existing = _recipe(conn, season, key)
            if existing is not None:
                return existing, False
            row = conn.execute(
                "SELECT data FROM skills WHERE season = ? AND name = ?", (season, skill_name),
            ).fetchone()
            if row is None:
                return None, False
            conn.execute(
                "INSERT INTO recipes (season, key, skill_name, creator) VALUES (?, ?, ?, ?)",
                (season, key, skill_name, creator),
            )
            return MartialArt.model_validate_json(row["data"]), True

    def link_insight_recipe(self, key: str, insight_name: str, creator: str | None) -> tuple[Insight | None, bool]:
        with self.db.transaction() as conn:
            season = self._season_number(conn)
            existing = _insight_recipe(conn, season, key)
            if existing is not None:
                return existing, False
            row = conn.execute(
                "SELECT data FROM insights WHERE season = ? AND name = ?", (season, insight_name),
            ).fetchone()
            if row is None:
                return None, False
            conn.execute(
                "INSERT INTO insight_recipes (season, key, insight_name, creator) VALUES (?, ?, ?, ?)",
                (season, key, insight_name, creator),
            )
            return Insight.model_validate_json(row["data"]), True

    def claim_master(self, skill_name: str, player: str, shown: str | None = None) -> bool:
        with self.db.transaction() as conn:
            season = self._season_number(conn)
            cursor = conn.execute(
                "INSERT INTO masters (season, skill_name, master) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                (season, skill_name, player),
            )
            if cursor.rowcount != 1:
                return False
            row = conn.execute("SELECT data FROM skills WHERE season = ? AND name = ?", (season, skill_name)).fetchone()
            if shown is not None and row is not None:  # 寫給別人看的名號記在那門武學身上（不動資料表結構；改名時跟著留下）
                art = MartialArt.model_validate_json(row["data"])
                art.master_shown = shown
                conn.execute(
                    "UPDATE skills SET data = ? WHERE season = ? AND name = ?", (art.model_dump_json(), season, skill_name),
                )
            return True

    def master_of(self, skill_name: str) -> str | None:
        with self.db.snapshot() as conn:
            row = conn.execute(
                "SELECT master FROM masters WHERE season = ? AND skill_name = ?",
                (self._season_number(conn), skill_name),
            ).fetchone()
        return None if row is None else row["master"]

    # ── 感悟的首悟紀錄 ────────────────────────────────────
    def claim_insight_first(self, key: str, name: str, creator: str, place: str, time: float = 0.0) -> bool:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO insight_firsts (season, key, name, creator, place, time) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT DO NOTHING",
                (self._season_number(conn), key, name, creator, place, time),
            )
            return cursor.rowcount == 1

    def insight_first(self, key: str) -> tuple[str, str] | None:
        with self.db.snapshot() as conn:
            row = conn.execute(
                "SELECT name, creator FROM insight_firsts WHERE season = ? AND key = ?", (self._season_number(conn), key),
            ).fetchone()
        return None if row is None else (row["name"], row["creator"] or "")

    # ── 玩家傳 ────────────────────────────────────────────

    def save_annals(self, season: int, name: str, annals: list[dict], profile: dict) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO biographies (season, key, name, annals, profile) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (season, key) DO UPDATE SET annals = excluded.annals, profile = excluded.profile, name = excluded.name "
                "WHERE biographies.text IS NULL",
                (season, name_key(name), name, json.dumps(annals, ensure_ascii=False), json.dumps(profile, ensure_ascii=False)),
            )

    def add_saved_annal(self, season: int, name: str, entry: dict) -> None:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT annals FROM biographies WHERE season = ? AND key = ?", (season, name_key(name)),
            ).fetchone()
            if row is None:
                return
            annals = json.loads(row["annals"]) + [entry]
            conn.execute(
                "UPDATE biographies SET annals = ? WHERE season = ? AND key = ?",
                (json.dumps(annals, ensure_ascii=False), season, name_key(name)),
            )

    @staticmethod
    def _biography_row(row: Row) -> dict:
        out = dict(row)
        out["annals"] = json.loads(out["annals"])
        out["profile"] = json.loads(out["profile"])
        out["public"] = bool(out["public"])
        return out

    def rename_character(self, old: str, new: str) -> None:
        """易名帖（rename.py）：資料庫裡名號當身分的地方一起從 old 換成 new，一筆交易。只換整個字串相等的（rename.swap）；
        這一季的全服狀態、決戰、全服登記與投靠名冊照換，以前的季不動；列傳、錢包、帳號、見聞紀錄跨季照鍵搬；
        別人的存檔裡提到他的（邀請、結伴、風聞……）照換。自己那一列角色由呼叫端用新名號存（這裡刪掉舊的那一列）。"""
        from .core.swap import swap_json
        okey, nkey = name_key(old), name_key(new)
        mapping = {old: new, okey: nkey}
        number = self.get_season_number()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT data FROM world WHERE id = 1").fetchone()
            if row is not None:
                conn.execute("UPDATE world SET data = ? WHERE id = 1", (swap_json(row["data"], mapping),))
            for r in conn.execute("SELECT number, data FROM seasons WHERE number = ?", (number,)).fetchall():
                conn.execute("UPDATE seasons SET data = ? WHERE number = ?", (swap_json(r["data"], mapping), r["number"]))
            for r in conn.execute("SELECT id, data FROM battles WHERE season = ?", (number,)).fetchall():
                conn.execute("UPDATE battles SET data = ? WHERE id = ?", (swap_json(r["data"], mapping), r["id"]))
                for rr in conn.execute("SELECT id, data FROM battle_rounds WHERE battle_id = ?", (r["id"],)).fetchall():
                    conn.execute("UPDATE battle_rounds SET data = ? WHERE id = ?", (swap_json(rr["data"], mapping), rr["id"]))
            for table, col in (("skills", "creator"), ("recipes", "creator"), ("insights", "creator"), ("insight_recipes", "creator"),
                               ("insight_firsts", "creator"), ("gear_recipes", "creator"), ("masters", "master"),
                               ("faction_rolls", "character"), ("rumors", "character")):
                for o, n in mapping.items():
                    conn.execute(f"UPDATE {table} SET {col} = ? WHERE season = ? AND {col} = ?", (n, number, o))
            for table in ("skills", "insights", "gear_recipes"):
                for r in conn.execute(f"SELECT rowid, data FROM {table} WHERE season = ?", (number,)).fetchall():
                    conn.execute(f"UPDATE {table} SET data = ? WHERE rowid = ?", (swap_json(r["data"], mapping), r["rowid"]))
            conn.execute("UPDATE rumor_heard SET character = ? WHERE character IN (?, ?)", (nkey, old, okey))
            conn.execute("UPDATE biographies SET key = ? WHERE key = ?", (nkey, okey))
            conn.execute("UPDATE character_backups SET key = ? WHERE key = ?", (nkey, okey))
            conn.execute("UPDATE accounts SET character = ?, character_key = ? WHERE character_key = ?", (new, nkey, okey))
            for table in ("mall_ledger", "mall_purchases"):
                for r in conn.execute(f"SELECT id, ref FROM {table} WHERE owner = ?", (okey,)).fetchall():
                    ref = ":".join(nkey if part == okey else part for part in r["ref"].split(":"))
                    conn.execute(f"UPDATE {table} SET owner = ?, ref = ? WHERE id = ?", (nkey, ref, r["id"]))
            conn.execute("UPDATE mall_entitlements SET owner = ? WHERE owner = ?", (nkey, okey))
            conn.execute("DELETE FROM characters WHERE key = ?", (okey,))
            for r in conn.execute("SELECT key, data FROM characters").fetchall():
                data = swap_json(r["data"], mapping)
                if data != r["data"]:
                    conn.execute("UPDATE characters SET data = ? WHERE key = ?", (data, r["key"]))

    def biography(self, season: int, name: str) -> dict | None:
        with self.db.snapshot() as conn:
            row = conn.execute("SELECT * FROM biographies WHERE season = ? AND key = ?", (season, name_key(name))).fetchone()
        return None if row is None else self._biography_row(row)

    def biographies_of(self, name: str) -> list[dict]:
        with self.db.snapshot() as conn:
            rows = conn.execute("SELECT * FROM biographies WHERE key = ? ORDER BY season DESC", (name_key(name),)).fetchall()
        return [self._biography_row(row) for row in rows]

    def store_biography(self, season: int, name: str, text: str, written_by: str, written_at: float, rewrite: bool) -> bool:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "UPDATE biographies SET text = ?, written_by = ?, written_at = ?, rewrites = rewrites + ? "
                "WHERE season = ? AND key = ? AND (? OR text IS NULL)",
                (text, written_by, written_at, int(rewrite), season, name_key(name), int(rewrite)),
            )
            return cursor.rowcount == 1

    def share_biography(self, season: int, name: str, public: bool, code: str) -> str | None:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT share_code FROM biographies WHERE season = ? AND key = ? AND text IS NOT NULL", (season, name_key(name)),
            ).fetchone()
            if row is None:
                return None
            code = row["share_code"] or code
            conn.execute(
                "UPDATE biographies SET public = ?, share_code = ? WHERE season = ? AND key = ?",
                (int(public), code, season, name_key(name)),
            )
            return code

    def biography_by_code(self, code: str) -> dict | None:
        with self.db.snapshot() as conn:
            row = conn.execute(
                "SELECT * FROM biographies WHERE share_code = ? AND public = 1 AND text IS NOT NULL", (code,),
            ).fetchone()
        return None if row is None else self._biography_row(row)

    # ── 同伴性情漂移 ──────────────────────────────────────

    def record_companion_tag(self, companion_id: str, tag: str) -> None:
        def _apply(state: SharedWorldState) -> None:
            counts = state.companion_tag_counts.setdefault(companion_id, {})
            counts[tag] = counts.get(tag, 0) + 1

        self.mutate(_apply)

    def get_companion_drift_note(self, companion_id: str) -> str:
        return self.read().companion_drift_note.get(companion_id, "")

    def set_companion_drift_note(self, companion_id: str, note: str) -> None:
        self.mutate(lambda state: state.companion_drift_note.__setitem__(companion_id, note))

    def tag_counts_since_last_drift(self, companion_id: str) -> int:
        state = self.read()
        total = sum(state.companion_tag_counts.get(companion_id, {}).values())
        return total - state.companion_drift_synthesized_at.get(companion_id, 0)

    def record_drift_synthesis(self, companion_id: str, note: str) -> None:
        def _apply(state: SharedWorldState) -> None:
            state.companion_drift_note[companion_id] = note
            total = sum(state.companion_tag_counts.get(companion_id, {}).values())
            state.companion_drift_synthesized_at[companion_id] = total

        self.mutate(_apply)

    # ── 江湖大事潤色 ──────────────────────────────────────

    def get_event_flavor(self, fire_id: str) -> str:
        return self.read().event_flavor.get(fire_id, "")

    def set_event_flavor(self, fire_id: str, text: str) -> None:
        def _set(state) -> None:
            from .flavor import clean  # noqa: PLC0415

            if not clean(state.event_flavor.get(fire_id, "")):  # 先寫的為準；先寫的那一句不合格（舊快取）才換
                state.event_flavor[fire_id] = text

        self.mutate(_set)

    # ── 傳國玉璽碎片（跨季）───────────────────────────────

    def record_jade_seal_fragment(self, finder: str, season_name: str, text: str) -> JadeSealFragment | None:
        result: dict[str, JadeSealFragment | None] = {"fragment": None}

        def _apply(state: SharedWorldState) -> None:
            if len(state.jade_seal_fragments) >= JADE_SEAL_FRAGMENT_COUNT:
                return
            fragment = JadeSealFragment(
                number=len(state.jade_seal_fragments) + 1, finder=finder, season_name=season_name, text=text,
            )
            state.jade_seal_fragments.append(fragment)
            result["fragment"] = fragment

        self.mutate(_apply)
        return result["fragment"]

    def get_jade_seal_fragments(self) -> list[JadeSealFragment]:
        return self.read().jade_seal_fragments

    def jade_seal_summary(self) -> str:
        return jade_seal_summary(self.get_jade_seal_fragments())

    # ── 共享賽季 ──────────────────────────────────────────

    def get_season(self) -> WorldState:
        with self.db.snapshot() as conn:
            return self._load(conn, logs=True).season

    def chronicle_before(self, season_number: int) -> list[tuple[int, list[Rumor]]]:
        with self.db.snapshot() as conn:
            rows = conn.execute(
                "SELECT * FROM chronicle WHERE season < ? ORDER BY season DESC, id", (season_number,),
            ).fetchall()
        seasons: dict[int, list[Rumor]] = {}
        for row in rows:
            seasons.setdefault(row["season"], []).append(_chronicle_entry(row))
        return list(seasons.items())

    def past_season(self, number: int) -> WorldState | None:
        with self.db.snapshot() as conn:
            row = conn.execute("SELECT data FROM seasons WHERE number = ?", (number,)).fetchone()
        return None if row is None else WorldState.model_validate_json(row["data"])

    def get_season_number(self) -> int:
        return self.read().season_number

    def fingerprint_parts(self) -> tuple[SharedWorldState, int, int]:
        """推送的看守（server.current_fingerprint）每幾秒讀一次用：同一個唯讀快照裡讀出（全服狀態，這一季最大的天下大事傳聞
        流水號，這一季江湖史的則數）。全服狀態照 read()（含目前的決戰，賽季裡的傳聞與江湖史是空的）；傳聞與江湖史不讀回
        每一列，讓資料庫數（MAX、COUNT）：一季的列數隨人數長大，整份讀回來五萬列要 244 毫秒（審查 m2）。
        一個快照＝三樣是同一個時刻的：分開讀的話，中間有人寫（決戰收場、套結果）就會讀到一半舊一半新的狀態。"""
        with self.db.snapshot() as conn:
            state = self._load(conn)
            number = state.season_number
            rumor = conn.execute(
                "SELECT MAX(id) FROM rumors WHERE season = ? AND layer = 'world'", (number,),
            ).fetchone()[0]
            chronicle = conn.execute("SELECT COUNT(*) FROM chronicle WHERE season = ?", (number,)).fetchone()[0]
        return state, rumor or 0, chronicle

    def mutate_season(self, fn: Callable[[WorldState], None]) -> WorldState:
        return self.mutate(lambda state: fn(state.season)).season

    def save_season(self, season: WorldState) -> None:
        self.mutate(lambda state: setattr(state, "season", season))

    def season_phase(self) -> SeasonPhase:
        return self.read().season_phase()

    def seed_first_season(self, content: Content) -> WorldState:
        def _apply(state: SharedWorldState) -> None:
            if state.season.storyline:
                return
            state.season = fresh_season(content)
            state.season_opened = content.config.auto_open_first_season
            if state.season_opened:  # 自動開的第一季（測試內容）：同開季那一刻挑這一季的神器（divine.stamp，開關關著什麼都不做）
                divine.stamp(state, content)
                self._stamp_cache(state, content)

        return self.mutate(_apply).season

    def open_season(self, content: Content, now: float) -> bool:
        result = {"ok": False}

        def _apply(state: SharedWorldState) -> None:
            if not state.season.storyline or state.season_opened:
                return
            stamp_season(state.season, content, now=now)  # 種下之後設定可能換過（例如重開時才設 weekend）；21 天季照這一刻蓋錨點
            from .timetable import avoid_quiet_hours  # noqa: PLC0415  延後 import：timetable → rules → world_state

            avoid_quiet_hours(state.season, content, now)  # 季曆排的決戰照開季這一刻挪開半夜（企劃者 2026-10-15）
            state.season.territory = None  # 章換了：地盤照開季的戰線重算，第一次不發天下大事（出陣探索與地盤設計第六節）
            state.season.conquest = None  # 領地爭奪同上：照開季的區塊與戰線重算（偏移從這一刻的戰線起算）
            state.sieges = []  # 攻城戰（第二批）：籌備中不會有，保險
            state.season.tianji = state.tianji  # 這一季的天機蓋進季裡：週初掛單的重賞亂數看它（裝備四欄 6.4；bounties.issue 讀不到全服那一列）
            divine.stamp(state, content)  # 神器輪替（正式季整合 5.6）：照全服登記挑這一季的神器；開關關著什麼都不做
            self._stamp_cache(state, content)  # 領地爭奪的季：碎片藏在中立地（Task 14）
            state.season_opened = True
            state.season_last_real = now
            state.seal.opened_real = now  # 「這一季上線過」與隱沒看它（玉璽碎片設計 5.3、7.6）
            state.paused_at = None  # 新開的季時鐘是走著的：暫停不會漏進來
            result["ok"] = True

        self.mutate(_apply)
        return result["ok"]

    def next_season(self, content: Content, now: float) -> bool:
        with self.db.transaction() as conn:
            state = self._load(conn)
            if state.season_phase() != "resting":
                return False
            lines = _season_firsts_lines(conn, state.season_number)
            wrote = False
            if content.seal:  # 玉璽碎片（7.6、5.11、8.4）：直接改 state.seal（這裡是手動 _load／_save，不能巢狀 mutate）
                from . import seal  # noqa: PLC0415

                reg = seal.filled(state.seal, content)
                mandate = state.season.mandate  # 剛結束的是天命之季：這一次不判隱沒、最後七片散去（8.4）
                if content.config.seal.enabled and not mandate:  # 主機關掉碎片時不判隱沒（登記照留）
                    seen = {s.holder: _seen_real(conn, s.holder) for s in reg.shards.values() if s.state == "held" and s.holder}
                    for shard, name in seal.sink(reg, state.season_number, seen, now, content.config.seal):
                        text = seal.sink_text(content, name, content.seal[shard.id].name)  # 改版：不點名
                        state.season.chronicle.append(Rumor(time=state.season.time, text=text))
                        wrote = True
                for duel in state.seal_duels:  # 還沒收場的單挑記成未分勝負，兩人補得到（開關關著時留下來的也一樣，不帶進下一季）
                    seal.log(reg, state.season_number, "unsettled", shard=duel.shard, holder=duel.holder.name, other=duel.challenger.name,
                             record=duel.record, where=duel.where, lines=list(duel.lines))
                if mandate:  # 散去不看 seal.enabled：季的章已經蓋了，下一輪照樣要從頭來
                    seal.scatter(reg, state.season_number)
                    state.season.chronicle.append(Rumor(time=state.season.time, text=seal.SCATTER))
                    wrote = True
            state.seal_duels = []
            for line in lines:  # 上一季的首創（合成、意境、絕學）寫進那一季的江湖史（第一季設計第十四節、武學與成長設計 3.10）
                state.season.chronicle.append(Rumor(time=state.season.time, text=line))
            if lines or wrote:
                self._save_season(conn, state.season_number, state.season)
            state.season = fresh_season(content, now=now)  # 新的一季另起一列（_save 照新的編號寫），舊的那一列不動；21 天季照這一刻蓋錨點
            state.season_number += 1
            state.season_opened = True
            state.season_last_real = now
            state.seal.opened_real = now  # 「這一季上線過」與隱沒看它（玉璽碎片設計 5.3、7.6）
            state.paused_at = None  # 暫停不會漏進下一季
            state.companions = {}  # 跨季不滾雪球第二條：同伴全部重獲自由、等級武學歸零
            state.tianji += 1  # 第三條：天機 +1；武學命名、煉製配方、投靠名冊照季分開存，新的一季自然是空的
            state.season.tianji = state.tianji  # 同 open_season：新的一季蓋上新的天機
            divine.stamp(state, content)  # 同 open_season：新的一季照全服登記挑神器（季數、天機都是新的）
            if content.seal and content.config.seal.enabled:  # 七片這一輪都現世過：新的一季蓋天命之季的章（8.1）
                self._stamp_mandate(state, content)
            self._stamp_cache(state, content)  # 上一季沒撿到的清掉；領地爭奪的季（天命之季除外）重擲藏一片（Task 14）
            from .timetable import avoid_quiet_hours  # noqa: PLC0415  延後 import：timetable → rules → world_state

            avoid_quiet_hours(state.season, content, now)  # 同開季：季曆排的決戰（含天命之爭）照這一刻挪開半夜
            state.active_battle = None  # 上一季沒打完（或打完沒清掉）的戰鬥不帶進新的一季
            state.sieges = []  # 攻城戰同上（領地爭奪第二批）
            state.sorties = {}  # 出陣約戰（減法季批 3b）同上：季結束時還沒打的已記成作廢（sortie_duel.advance），塊與條都是上一季的
            self._save(conn, state)
            return True

    @staticmethod
    def _stamp_cache(state: SharedWorldState, content: Content) -> None:
        """開季那一刻（自動開的第一季、管理者開季、換季）：碎片藏在中立地（seal.stamp_cache：上一季沒撿到的清掉、領地爭奪的季照
        hide_chance 擲、天命之季不藏）。直接改 state（同一筆交易、不巢狀 mutate）；內容沒有七片就什麼都不做。"""
        if not content.seal:
            return
        from . import seal  # noqa: PLC0415

        seal.stamp_cache(state, content)

    @staticmethod
    def _stamp_mandate(state: SharedWorldState, content: Content) -> None:
        """next_season 換好新的一季之後：該蓋天命之季（seal.mandate_due）就蓋（seal.stamp_mandate，天命之爭的時刻照這一季的章算）；
        這一季打不了天命之爭（沒蓋第一季規則的章、劇本沒標或沒有那一場決戰）就記 mandate_pending，延到下一個能打的季（8.1、8.5）。
        直接改 state（同一筆交易、不巢狀 mutate）。"""
        from . import seal, timetable  # noqa: PLC0415

        reg = seal.filled(state.seal, content)
        if not seal.mandate_due(reg, content):
            return
        event = seal.mandate_event(content)
        if event is None or seal.mandate_battle(content) is None or not state.season.season_one:
            reg.mandate_pending = True
            return
        seal.stamp_mandate(state, content, timetable.default_time(event, content, state.season))

    def catch_up_season(self, content: Content, now: float, rng: random.Random) -> list[str]:
        """整段在同一筆交易裡：對時鐘與推進賽季一起成功或一起撤回。實際「推進 N 秒會發生什麼事」在
        world.py::advance_season（world.py 會 import 這個模組的介面，只能在函式裡 import 它）。
        賽季時鐘暫停中（paused_at）什麼都不做：不推進、對時點也不動（繼續時一起往後挪，見 resume_clock）。"""
        from . import world as world_module

        result = {"elapsed": 0.0}

        def _apply(state: SharedWorldState) -> None:
            if state.paused_at is not None:  # 賽季時鐘暫停中：不推、對時點也不動（繼續時一起往後挪，見 resume_clock）
                return
            last = state.season_last_real
            state.season_last_real = now if last is None else max(last, now)
            if last is None or state.season_phase() != "running":
                return
            result["elapsed"] = max(0.0, now - last) * content.config.time_scale

        with self.db.transaction():
            self.mutate(_apply)
            if result["elapsed"] <= 0:
                return []
            return world_module.advance_season(self, content, result["elapsed"], rng, now)

    # ── 賽季時鐘暫停 ──────────────────────────────────────

    def paused_at(self) -> float | None:
        with self.db.snapshot() as conn:
            row = conn.execute("SELECT json_extract(data, '$.paused_at') AS at FROM world WHERE id = 1").fetchone()
        return None if row is None or row["at"] is None else float(row["at"])

    def pause_clock(self, now: float) -> bool:
        result = {"ok": False}

        def _apply(state: SharedWorldState) -> None:
            if state.paused_at is not None or state.season_phase() != "running":
                return
            state.paused_at = now
            result["ok"] = True

        self.mutate(_apply)
        return result["ok"]

    def resume_clock(self, content: Content, now: float) -> float | None:
        from . import world as world_module  # world → world_state：在函式裡 import，同 catch_up_season

        result: dict[str, float | None] = {"span": None}

        def _apply(state: SharedWorldState) -> None:
            if state.paused_at is None:
                return
            span = max(0.0, now - state.paused_at)
            state.paused_at = None
            if state.season_last_real is not None:
                skipped = world_module.pause_skip(state.season, content, span)
                state.season_last_real += skipped
                scale = content.config.time_scale
                until = None
                if calendar.season21_on(state.season, content):
                    # FB-332：暫停那一刻與繼續那一刻是同一個世界秒（暫停的這一段不算進賽季）。賽季多走 RESUME_NUDGE，
                    # 舊的偏移用到兩者中間：暫停前寫下的照舊、繼續之後（含繼續那一刻結算的大事）照對回現實的偏移
                    paused_season = state.season.time + max(0.0, now - state.season_last_real) * scale
                    state.season_last_real -= world_module.RESUME_NUDGE / scale
                    until = paused_season + world_module.RESUME_NUDGE / 2
                world_module.realign_paused_calendar(state.season, content, skipped, until)  # 21 天季：季曆對回現實的星期（其他季不動）
                season_now = state.season.time + max(0.0, now - state.season_last_real) * scale
                world_module.keep_showdowns_on_time(state.season, content, skipped, season_now)
            if state.active_battle is not None:
                shift_deadlines(state.active_battle, span)
            for siege in state.sieges:  # 攻城戰同上（領地爭奪第二批，Review Focus 5）
                shift_deadlines(siege, span)
            for duel in state.seal_duels:  # 奪璽單挑的時間一起挪（5.4）：不挪的話一繼續兩邊都過了在場窗口，全由代打打完
                duel.starts_real += span
                if duel.opened_real is not None:
                    duel.opened_real += span
                for side in (duel.challenger, duel.holder):
                    if side.last_seen is not None:
                        side.last_seen += span
            for sortie in state.sorties.values():  # 出陣約戰（減法季批 3b）：還沒結算的，窗的期限往後挪停的長度（開的時刻不動：這一場的亂數照舊）
                if sortie.status in ("open", "answered"):
                    sortie.expires_at += span
            result["span"] = span

        self.mutate(_apply)
        return result["span"]

    # ── 投靠名冊 ──────────────────────────────────────────

    def record_faction(self, name: str, faction_id: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO faction_rolls (season, character, faction) VALUES (?, ?, ?) "
                "ON CONFLICT (season, character) DO UPDATE SET faction = excluded.faction",
                (self._season_number(conn), name, faction_id),
            )

    def roll_of(self, name: str) -> str | None:
        with self.db.snapshot() as conn:
            row = conn.execute(
                "SELECT faction FROM faction_rolls WHERE season = ? AND character = ?",
                (self._season_number(conn), name),
            ).fetchone()
        return None if row is None else row["faction"]

    def faction_of(self, name: str) -> str | None:
        return allied.side_of_key(self.roll_of(name))

    def roll_counts(self) -> dict[str, int]:
        with self.db.snapshot() as conn:
            rows = conn.execute(
                "SELECT faction, COUNT(*) AS n FROM faction_rolls WHERE season = ? GROUP BY faction",
                (self._season_number(conn),),
            ).fetchall()
        return {row["faction"]: row["n"] for row in rows}

    def faction_counts(self) -> dict[str, int]:
        return allied.faction_totals(self.roll_counts())

    def seal_state(self) -> SealView:
        with self.db.snapshot() as conn:
            row = conn.execute(
                "SELECT json_extract(data, '$.seal') AS seal, json_extract(data, '$.seal_duels') AS duels, "
                "json_extract(data, '$.season_number') AS season, json_extract(data, '$.tianji') AS tianji, "
                "json_extract(data, '$.paused_at') AS paused FROM world WHERE id = 1"
            ).fetchone()
        if row is None:
            return SealView(SealRegistry(), [], 1, 0, False)
        registry = SealRegistry.model_validate_json(row["seal"]) if row["seal"] else SealRegistry()
        duels = [SealDuel.model_validate(d) for d in json.loads(row["duels"])] if row["duels"] else []
        return SealView(registry, duels, int(row["season"] or 1), int(row["tianji"] or 0), row["paused"] is not None)

    def divine_state(self) -> DivineRegistry:
        with self.db.snapshot() as conn:
            return _divine(conn)

    def seal_duel_open(self) -> bool:
        with self.db.snapshot() as conn:
            row = conn.execute("SELECT json_array_length(data, '$.seal_duels') AS n FROM world WHERE id = 1").fetchone()
        return row is not None and bool(row["n"])

    def sortie_duels(self) -> dict[str, SortieDuel]:
        with self.db.snapshot() as conn:
            row = conn.execute("SELECT json_extract(data, '$.sorties') AS sorties FROM world WHERE id = 1").fetchone()
        if row is None or not row["sorties"]:  # 空的時候 world 那一列沒有這個鍵（SharedWorldState._drop_empty_sorties）
            return {}
        return {key: SortieDuel.model_validate(d) for key, d in json.loads(row["sorties"]).items()}

    # ── 全服即時多人戰鬥 ──────────────────────────────────

    def get_battle(self) -> BattleInstance | None:
        return self.read().active_battle

    def mutate_battle(self, fn: Callable[[BattleInstance], None]) -> BattleInstance | None:
        result: dict[str, BattleInstance | None] = {"battle": None}

        def _apply(state: SharedWorldState) -> None:
            if state.active_battle is None:
                return
            fn(state.active_battle)
            result["battle"] = state.active_battle

        self.mutate(_apply)
        return result["battle"]

    def start_battle(self, definition: BattleDef, now: float, trend_start: int | None = None) -> BattleInstance:
        result: dict[str, BattleInstance] = {}

        def _apply(state: SharedWorldState) -> None:
            if state.active_battle is not None and state.active_battle.phase != "ended":
                result["battle"] = state.active_battle
                return
            state.active_battle = start_muster(definition, now, trend_start)
            result["battle"] = state.active_battle

        self.mutate(_apply)
        return result["battle"]

    def clear_battle(self) -> None:
        self.mutate(lambda state: setattr(state, "active_battle", None))

    def get_sieges(self) -> list[BattleInstance]:
        """跟 read().sieges 同一份（world 那一列記的流水號照順序、一場一列），只是不整份解析共用狀態與季：Game._sieges 每一下選單、
        每一次 _battle_status 都叫，領地爭奪開著時整份讀佔了假人一個動作的兩成多（打開領地爭奪，計畫 2026-10-22-打開領地爭奪.md 4.4）。"""
        with self.db.snapshot() as conn:
            row = conn.execute("SELECT json_extract(data, '$.siege_records') AS ids FROM world WHERE id = 1").fetchone()
            ids = json.loads(row["ids"]) if row is not None and row["ids"] else []
            return [self._load_battle(conn, rid) for rid in ids]

    def mutate_siege(self, record_id: int, fn: Callable[[BattleInstance], None]) -> BattleInstance | None:
        result: dict[str, BattleInstance | None] = {"battle": None}

        def _apply(state: SharedWorldState) -> None:
            found = next((b for b in state.sieges if b.record_id == record_id), None)
            if found is not None:
                fn(found)
                result["battle"] = found

        self.mutate(_apply)
        return result["battle"]

    def start_siege(self, definition: BattleDef, now: float, trend_start: int, info: SiegeInfo) -> BattleInstance:
        result: dict[str, BattleInstance] = {}

        def _apply(state: SharedWorldState) -> None:
            battle = start_muster(definition, now, trend_start)
            battle.siege = info
            state.sieges.append(battle)
            result["battle"] = battle

        self.mutate(_apply)  # 寫回時 _save_battle 填上流水號（同一個物件）
        return result["battle"]

    def drop_siege(self, record_id: int) -> None:
        self.mutate(lambda state: setattr(state, "sieges", [b for b in state.sieges if b.record_id != record_id]))

    def battle_rounds(self, record_id: int) -> list[BattleRoundRecord]:
        with self.db.snapshot() as conn:
            rows = conn.execute(
                "SELECT id, data FROM battle_rounds WHERE battle_id = ? ORDER BY id", (record_id,),
            ).fetchall()
        return [BattleRoundRecord.model_validate_json(row["data"]).model_copy(update={"id": row["id"]}) for row in rows]

    def ended_battles(self, after: int = 0, skip: Collection[int] = ()) -> list[tuple[int, BattleInstance]]:
        """每個人每次同步（包括畫面每 10 秒的計時器）都會問，所以只讀流水號比 after 大的那幾列（主鍵的範圍查詢），
        通常一列都沒有。流水號是 INTEGER PRIMARY KEY、這張表從不刪列，新的一場永遠比舊的大。
        skip 裡的流水號（呼叫端補過的）先用流水號濾掉、不讀內容（攻城戰同時打，after 是往回讓的下限，見介面的說明）。"""
        done = set(skip)
        with self.db.snapshot() as conn:
            rows = conn.execute(
                "SELECT id, season FROM battles WHERE id > ? AND phase = 'ended' ORDER BY id", (after,),
            ).fetchall()
            return [(row["season"], self._load_battle(conn, row["id"])) for row in rows if row["id"] not in done]

    def ended_battle(self, record_id: int) -> BattleInstance | None:
        with self.db.snapshot() as conn:
            row = conn.execute("SELECT id FROM battles WHERE id = ? AND phase = 'ended'", (record_id,)).fetchone()
            return self._load_battle(conn, row["id"]) if row is not None else None

    def season_ended_battles(self, season: int) -> list[BattleInstance]:
        with self.db.snapshot() as conn:
            rows = conn.execute("SELECT id FROM battles WHERE season = ? AND phase = 'ended' ORDER BY id", (season,)).fetchall()
            return [self._load_battle(conn, row["id"]) for row in rows]

    # ── 同伴進度與招募 ────────────────────────────────────

    def get_companion(self, companion_id: str) -> CompanionProgress:
        return self.read().companions.get(companion_id, CompanionProgress())

    def try_recruit(self, companion_id: str, player_name: str, cap: int | None = None) -> bool:
        """原子地招一位：已經有主、或（給了 cap）這個人名下已經有 cap 位（名號比對不分大小寫），都不寫、回 False。
        上限在同一筆寫入裡判，兩個分頁同時招第四位也只有一個成（歷史武將同行第四節）。"""
        result = {"ok": False}

        def _apply(state: SharedWorldState) -> None:
            progress = state.companions.setdefault(companion_id, CompanionProgress())
            if progress.owner is not None:
                return
            if cap is not None and sum(
                1 for p in state.companions.values() if p.owner is not None and name_key(p.owner) == name_key(player_name)
            ) >= cap:
                return
            progress.owner = player_name
            result["ok"] = True

        self.mutate(_apply)
        return result["ok"]

    def release_companion(self, companion_id: str) -> None:
        def _apply(state: SharedWorldState) -> None:
            if companion_id in state.companions:
                state.companions[companion_id].owner = None

        self.mutate(_apply)

    def update_companion(self, companion_id: str, fn: Callable[[CompanionProgress], None]) -> CompanionProgress:
        def _apply(state: SharedWorldState) -> None:
            fn(state.companions.setdefault(companion_id, CompanionProgress()))

        return self.mutate(_apply).companions[companion_id]


def _name_taken(conn: Connection, season: int, name: str) -> bool:
    """這一季這個名字被用掉了沒：功法（id）、改過的名字、合併出來的意境、gear_recipes 都算（上線前的兵器配方；隱藏配方那幾列的名字欄
    是鍵本身，不會撞到合法的名字）。定了名的神器原品那一列名字欄是定的名字，照樣算（打造隱藏配方設計 7.3）。"""
    if any(f.divine_name == name for f in _divine(conn).finds.values()):  # 輪替季的神器原品：名字跨季保留（正式季整合 10.4）
        return True
    return any(
        conn.execute(f"SELECT 1 FROM {table} WHERE season = ? AND name = ?", (season, name)).fetchone()
        for table in ("skills", "skill_aliases", "insights", "gear_recipes")
    )


def _insert_skill(conn: Connection, season: int, art: MartialArt) -> bool:
    """登記一門功法；這一季名字已經被用掉（功法、改過的名字、意境）就不登記。"""
    name = art.name.strip()
    if _name_taken(conn, season, name):
        return False
    cursor = conn.execute(
        "INSERT INTO skills (season, name, creator, data) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
        (season, name, art.creator, art.model_dump_json()),
    )
    return cursor.rowcount == 1


def _recipe(conn: Connection, season: int, key: str) -> MartialArt | None:
    row = conn.execute(
        "SELECT s.data FROM recipes r JOIN skills s ON s.season = r.season AND s.name = r.skill_name "
        "WHERE r.season = ? AND r.key = ?",
        (season, key),
    ).fetchone()
    return None if row is None else MartialArt.model_validate_json(row["data"])


def _insight_recipe(conn: Connection, season: int, key: str) -> Insight | None:
    row = conn.execute(
        "SELECT i.data FROM insight_recipes r JOIN insights i ON i.season = r.season AND i.name = r.insight_name "
        "WHERE r.season = ? AND r.key = ?",
        (season, key),
    ).fetchone()
    return None if row is None else Insight.model_validate_json(row["data"])


def _gear_recipe(conn: Connection, season: int, key: str) -> WeaponRecipe | None:
    row = conn.execute("SELECT data FROM gear_recipes WHERE season = ? AND key = ?", (season, key)).fetchone()
    return None if row is None else WeaponRecipe.model_validate_json(row["data"])


def _divine(conn: Connection) -> DivineRegistry:
    """神器輪替的全服登記（world 那一列 JSON 的 divine；正式季整合 10.4）：只讀那一欄，不讀季。"""
    row = conn.execute("SELECT json_extract(data, '$.divine') AS divine FROM world WHERE id = 1").fetchone()
    return DivineRegistry.model_validate_json(row["divine"]) if row is not None and row["divine"] else DivineRegistry()


def _put_divine(conn: Connection, reg: DivineRegistry) -> None:
    """只改 world 那一列 JSON 的 divine（json_set），不整份覆寫、不碰季。"""
    conn.execute("UPDATE world SET data = json_set(data, '$.divine', json(?)) WHERE id = 1", (reg.model_dump_json(),))


def _registry_find(conn: Connection, season: int, key: str, registry: bool | None) -> GearFind | None:
    """全服登記裡這條神器配方的原品那一筆（FB-402）：registry 給了照它（呼叫端照那一件神器 Equipment.collected 傳），
    None 時看這一季蓋沒蓋輪替的章（_rotating）；不讀登記、或登記裡沒有回 None。"""
    if registry is False or (registry is None and not _rotating(conn, season)):
        return None
    return _divine(conn).finds.get(key.removeprefix("鑄|"))


def _rotating(conn: Connection, season: int) -> bool:
    """這一季蓋了神器輪替的章（WorldState.divine_lineup 不是 null）。"""
    row = conn.execute("SELECT json_extract(data, '$.divine_lineup') IS NOT NULL AS r FROM seasons WHERE number = ?", (season,)).fetchone()
    return row is not None and bool(row["r"])


def _gear_find(conn: Connection, season: int, key: str) -> GearFind | None:
    row = conn.execute("SELECT data FROM gear_recipes WHERE season = ? AND key = ?", (season, key)).fetchone()
    return None if row is None else GearFind.model_validate_json(row["data"])


def _season_firsts_lines(conn: Connection, season: int) -> list[str]:
    """這一季的首創，寫成江湖史（跨季保留，武學與成長設計 3.10）：合成首創、首悟意境（合併出來的）、感悟首悟（悟意境設計 0.2b）、
    練成絕學。
    武學照現在顯示的名字（練成絕學改過名的寫新名）；沒有的那一類不寫。
    人名寫登記當下記下的「寫給別人看的名號」（現在一律是名號；這一版之前匿名行走的人記成「某位少俠」，照舊）：
    功法、意境的 creator_shown，武學的 master_shown；舊資料沒記的照資料表裡的名號。
    （舊季的煉製配方也在 recipes 表裡，照樣列在「合成首創」，不用分。）
    合到舊的會讓好幾個配方指向同一門（設計 12.2）：一門只列一次，寫首創的那一列。"""
    lines = []
    arts = conn.execute(
        "SELECT json_extract(s.data, '$.name') AS name, "
        "COALESCE(json_extract(s.data, '$.creator_shown'), r.creator) AS creator, MIN(r.rowid) AS first FROM recipes r "
        "JOIN skills s ON s.season = r.season AND s.name = r.skill_name WHERE r.season = ? "
        "AND COALESCE(json_extract(s.data, '$.preset'), 0) = 0 "  # 師門配方（新手引導）沒有首創者：不列、不算進件數
        "GROUP BY r.skill_name ORDER BY first",
        (season,),
    ).fetchall()
    if arts:
        firsts = "、".join(f"【{row['name']}】{row['creator'] or '無名氏'}" for row in arts)
        lines.append(f"第 {season} 季合成首創 {len(arts)} 門：{firsts}")
    insights_rows = conn.execute(
        "SELECT r.insight_name, COALESCE(json_extract(i.data, '$.creator_shown'), r.creator) AS creator, "
        "MIN(r.rowid) AS first FROM insight_recipes r LEFT JOIN insights i ON i.season = r.season AND i.name = r.insight_name "
        "WHERE r.season = ? GROUP BY r.insight_name ORDER BY first",
        (season,),
    ).fetchall()
    if insights_rows:
        firsts = "、".join(f"「{row['insight_name']}」{row['creator'] or '無名氏'}" for row in insights_rows)
        lines.append(f"第 {season} 季首悟意境 {len(insights_rows)} 個：{firsts}")
    sensed = conn.execute(
        "SELECT name, creator, place FROM insight_firsts WHERE season = ? ORDER BY rowid", (season,),
    ).fetchall()
    if sensed:  # 心有所感、一筆畫下悟到的意境是私有的，全服只留首悟的紀錄（悟意境設計 0.2b）
        firsts = "、".join(f"「{row['name']}」{row['creator'] or '無名氏'}（{row['place']}）" for row in sensed)
        lines.append(f"第 {season} 季感悟首悟 {len(sensed)} 處：{firsts}")
    masters = conn.execute(
        "SELECT json_extract(s.data, '$.name') AS name, "
        "COALESCE(json_extract(s.data, '$.master_shown'), m.master) AS master FROM masters m "
        "JOIN skills s ON s.season = m.season AND s.name = m.skill_name WHERE m.season = ? ORDER BY m.rowid",
        (season,),
    ).fetchall()
    if masters:
        firsts = "、".join(f"【{row['name']}】{row['master']}" for row in masters)
        lines.append(f"第 {season} 季練成絕學 {len(masters)} 門：{firsts}")
    return lines


def _rumor(row: Row) -> Rumor:
    return Rumor(
        id=row["id"], time=row["time"], text=row["text"], location=row["location"], layer=row["layer"],
        faction=row["faction"], region=row["region"], character=row["character"], named=bool(row["named"]),
    )


def _chronicle_entry(row: Row) -> Rumor:
    return Rumor(id=row["id"], time=row["time"], text=row["text"], location=row["location"])


def _seen_real(conn: Connection, name: str) -> float | None:
    """持有者最後一次自己上線的現實秒（玉璽碎片設計 7.6）：存檔的 seen_real，舊存檔退回 last_real；查不到那一列是 None。"""
    row = conn.execute(
        "SELECT json_extract(data, '$.player.seen_real') AS seen, json_extract(data, '$.last_real') AS last FROM characters WHERE key = ?",
        (name_key(name),),
    ).fetchone()
    if row is None:
        return None
    value = row["seen"] if row["seen"] is not None else row["last"]
    return None if value is None else float(value)
