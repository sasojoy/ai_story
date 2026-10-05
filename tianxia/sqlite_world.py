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
  共用一個名字空間（`_name_taken`）。
- 每個會寫的方法自己是一筆交易；呼叫端已經在 action_lock() 裡時，併進那一筆（見 database.Database）。
"""
from __future__ import annotations

import random
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from sqlite3 import Connection, Row

from .battle_instance import BattleInstance, BattleRoundRecord, start_muster
from .database import Database, open_database
from .martial_arts import Insight, MartialArt
from .models import BattleDef, Content
from .state import Rumor, WorldState
from .world_state import (
    JADE_SEAL_FRAGMENT_COUNT, CompanionProgress, JadeSealFragment, SeasonPhase, SharedWorldState, fresh_season,
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
        return state

    def _save(self, conn: Connection, state: SharedWorldState) -> None:
        battle_id = self._save_battle(conn, state.season_number, state.active_battle)  # 先寫決戰：world 要指向它
        conn.execute(
            "INSERT INTO world (id, data, active_battle_id) VALUES (1, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET data = excluded.data, active_battle_id = excluded.active_battle_id",
            (state.model_dump_json(exclude={"season", "active_battle"}), battle_id),
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

    def claim_master(self, skill_name: str, player: str) -> bool:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO masters (season, skill_name, master) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                (self._season_number(conn), skill_name, player),
            )
            return cursor.rowcount == 1

    def master_of(self, skill_name: str) -> str | None:
        with self.db.snapshot() as conn:
            row = conn.execute(
                "SELECT master FROM masters WHERE season = ? AND skill_name = ?",
                (self._season_number(conn), skill_name),
            ).fetchone()
        return None if row is None else row["master"]

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
        self.mutate(lambda state: state.event_flavor.setdefault(fire_id, text))

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

    def get_season_number(self) -> int:
        return self.read().season_number

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

        return self.mutate(_apply).season

    def open_season(self, content: Content, now: float) -> bool:
        result = {"ok": False}

        def _apply(state: SharedWorldState) -> None:
            if not state.season.storyline or state.season_opened:
                return
            stamp_season(state.season, content)  # 種下之後設定可能換過（例如重開時才設 weekend）
            state.season_opened = True
            state.season_last_real = now
            result["ok"] = True

        self.mutate(_apply)
        return result["ok"]

    def next_season(self, content: Content, now: float) -> bool:
        with self.db.transaction() as conn:
            state = self._load(conn)
            if state.season_phase() != "resting":
                return False
            line = _first_crafts_line(conn, state.season_number)
            if line:  # 上一季的煉製首創寫進那一季的江湖史（第一季設計第十四節）
                state.season.chronicle.append(Rumor(time=state.season.time, text=line))
                self._save_season(conn, state.season_number, state.season)
            state.season = fresh_season(content)  # 新的一季另起一列（_save 照新的編號寫），舊的那一列不動
            state.season_number += 1
            state.season_opened = True
            state.season_last_real = now
            state.companions = {}  # 跨季不滾雪球第二條：同伴全部重獲自由、等級武學歸零
            state.tianji += 1  # 第三條：天機 +1；武學命名、煉製配方、投靠名冊照季分開存，新的一季自然是空的
            state.active_battle = None  # 上一季沒打完（或打完沒清掉）的戰鬥不帶進新的一季
            self._save(conn, state)
            return True

    def catch_up_season(self, content: Content, now: float, rng: random.Random) -> list[str]:
        """整段在同一筆交易裡：對時鐘與推進賽季一起成功或一起撤回。實際「推進 N 秒會發生什麼事」在
        world.py::advance_season（world.py 會 import 這個模組的介面，只能在函式裡 import 它）。"""
        from . import world as world_module

        result = {"elapsed": 0.0}

        def _apply(state: SharedWorldState) -> None:
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

    # ── 投靠名冊 ──────────────────────────────────────────

    def record_faction(self, name: str, faction_id: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO faction_rolls (season, character, faction) VALUES (?, ?, ?) "
                "ON CONFLICT (season, character) DO UPDATE SET faction = excluded.faction",
                (self._season_number(conn), name, faction_id),
            )

    def faction_of(self, name: str) -> str | None:
        with self.db.snapshot() as conn:
            row = conn.execute(
                "SELECT faction FROM faction_rolls WHERE season = ? AND character = ?",
                (self._season_number(conn), name),
            ).fetchone()
        return None if row is None else row["faction"]

    def faction_counts(self) -> dict[str, int]:
        with self.db.snapshot() as conn:
            rows = conn.execute(
                "SELECT faction, COUNT(*) AS n FROM faction_rolls WHERE season = ? GROUP BY faction",
                (self._season_number(conn),),
            ).fetchall()
        return {row["faction"]: row["n"] for row in rows}

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

    def battle_rounds(self, record_id: int) -> list[BattleRoundRecord]:
        with self.db.snapshot() as conn:
            rows = conn.execute(
                "SELECT id, data FROM battle_rounds WHERE battle_id = ? ORDER BY id", (record_id,),
            ).fetchall()
        return [BattleRoundRecord.model_validate_json(row["data"]).model_copy(update={"id": row["id"]}) for row in rows]

    def ended_battles(self, after: int = 0) -> list[tuple[int, BattleInstance]]:
        """每個人每次同步（包括畫面每 10 秒的計時器）都會問，所以只讀流水號比 after 大的那幾列（主鍵的範圍查詢），
        通常一列都沒有。流水號是 INTEGER PRIMARY KEY、這張表從不刪列，新的一場永遠比舊的大。"""
        with self.db.snapshot() as conn:
            rows = conn.execute(
                "SELECT id, season FROM battles WHERE id > ? AND phase = 'ended' ORDER BY id", (after,),
            ).fetchall()
            return [(row["season"], self._load_battle(conn, row["id"])) for row in rows]

    # ── 同伴進度與招募 ────────────────────────────────────

    def get_companion(self, companion_id: str) -> CompanionProgress:
        return self.read().companions.get(companion_id, CompanionProgress())

    def try_recruit(self, companion_id: str, player_name: str) -> bool:
        result = {"ok": False}

        def _apply(state: SharedWorldState) -> None:
            progress = state.companions.setdefault(companion_id, CompanionProgress())
            if progress.owner is not None:
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
    """這一季這個名字被用掉了沒：功法（id）、改過的名字、合併出來的意境都算。"""
    return any(
        conn.execute(f"SELECT 1 FROM {table} WHERE season = ? AND name = ?", (season, name)).fetchone()
        for table in ("skills", "skill_aliases", "insights")
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


def _first_crafts_line(conn: Connection, season: int) -> str:
    """這一季每個配方的首創者，寫成一則江湖史；這一季沒有人煉出新配方就是空字串。"""
    rows = conn.execute(
        "SELECT skill_name, creator FROM recipes WHERE season = ? ORDER BY rowid", (season,),
    ).fetchall()
    if not rows:
        return ""
    firsts = "、".join(f"【{row['skill_name']}】{row['creator'] or '無名氏'}" for row in rows)
    return f"第 {season} 季煉製首創 {len(rows)} 門：{firsts}"


def _rumor(row: Row) -> Rumor:
    return Rumor(
        id=row["id"], time=row["time"], text=row["text"], location=row["location"], layer=row["layer"],
        faction=row["faction"], region=row["region"], character=row["character"], named=bool(row["named"]),
    )


def _chronicle_entry(row: Row) -> Rumor:
    return Rumor(id=row["id"], time=row["time"], text=row["text"], location=row["location"])
