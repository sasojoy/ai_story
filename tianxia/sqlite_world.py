"""全服狀態存在 SQLite（線上架構設計第三節）；介面與各方法的說明見 world_state.WorldStateStore。

- `world` 表一列：SharedWorldState 除了賽季以外的小資料，整份覆寫。
- `seasons` 表一季一列：WorldState，整份覆寫。換季不刪資料：賽季編號加一、新的一季另起一列，
  舊的一季原封不動留著。
- 每個會寫的方法自己是一筆交易；呼叫端已經在 action_lock() 裡時，併進那一筆（見 database.Database）。
"""
from __future__ import annotations

import random
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from sqlite3 import Connection

from .battle_instance import BattleInstance, start_muster
from .database import Database, open_database
from .martial_arts import MartialArt
from .models import BattleDef, Content
from .state import WorldState
from .world_state import (
    JADE_SEAL_FRAGMENT_COUNT, CompanionProgress, JadeSealFragment, SeasonPhase, SharedWorldState, fresh_season,
    jade_seal_summary,
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
        with self.db.transaction() as conn:
            state = self._load(conn)
            fn(state)
            self._save(conn, state)
            return state

    def _load(self, conn: Connection) -> SharedWorldState:
        row = conn.execute("SELECT data FROM world WHERE id = 1").fetchone()
        state = SharedWorldState() if row is None else SharedWorldState.model_validate_json(row["data"])
        state.season = self._load_season(conn, state.season_number)
        return state

    def _save(self, conn: Connection, state: SharedWorldState) -> None:
        conn.execute(
            "INSERT INTO world (id, data) VALUES (1, ?) ON CONFLICT (id) DO UPDATE SET data = excluded.data",
            (state.model_dump_json(exclude={"season"}),),
        )
        self._save_season(conn, state.season_number, state.season)

    def _load_season(self, conn: Connection, number: int) -> WorldState:
        row = conn.execute("SELECT data FROM seasons WHERE number = ?", (number,)).fetchone()
        return WorldState() if row is None else WorldState.model_validate_json(row["data"])

    def _save_season(self, conn: Connection, number: int, season: WorldState) -> None:
        conn.execute(
            "INSERT INTO seasons (number, data) VALUES (?, ?) ON CONFLICT (number) DO UPDATE SET data = excluded.data",
            (number, season.model_dump_json()),
        )

    # ── 武學命名登記與煉製配方 ──────────────────────────────

    def is_skill_name_taken(self, name: str) -> bool:
        return name.strip() in self.read().created_skills

    def claim_skill_name(self, art: MartialArt) -> bool:
        claimed = {"ok": False}

        def _apply(state: SharedWorldState) -> None:
            if art.name.strip() in state.created_skills:
                return
            state.created_skills[art.name.strip()] = art
            claimed["ok"] = True

        self.mutate(_apply)
        return claimed["ok"]

    def lookup_recipe(self, key: str) -> MartialArt | None:
        state = self.read()
        name = state.recipes.get(key)
        return state.created_skills.get(name) if name else None

    def claim_recipe(self, key: str, art: MartialArt) -> tuple[MartialArt | None, bool]:
        result: dict[str, object] = {"art": None, "first": False}

        def _apply(state: SharedWorldState) -> None:
            existing = state.recipes.get(key)
            if existing:
                result["art"] = state.created_skills.get(existing)
                return
            if art.name in state.created_skills:
                return  # 名字撞到，呼叫端換名字
            state.created_skills[art.name] = art
            state.recipes[key] = art.name
            result["art"], result["first"] = art, True

        self.mutate(_apply)
        return result["art"], bool(result["first"])  # type: ignore[return-value]

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
        return self.read().season

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

    def open_season(self, now: float) -> bool:
        result = {"ok": False}

        def _apply(state: SharedWorldState) -> None:
            if not state.season.storyline or state.season_opened:
                return
            state.season_opened = True
            state.season_last_real = now
            result["ok"] = True

        self.mutate(_apply)
        return result["ok"]

    def next_season(self, content: Content, now: float) -> bool:
        result = {"ok": False}

        def _apply(state: SharedWorldState) -> None:
            if state.season_phase() != "resting":
                return
            state.season = fresh_season(content)  # 新的一季另起一列（_save 照新的編號寫），舊的那一列不動
            state.season_number += 1
            state.season_opened = True
            state.season_last_real = now
            state.companions = {}  # 跨季不滾雪球第二條：同伴全部重獲自由、等級武學歸零
            state.created_skills = {}  # 第三條：自創武學名字全部釋出
            state.recipes = {}  # 煉製配方跟著清空，大家重新發現、首創者重新認定（第一季設計第十四節）
            state.tianji += 1
            state.active_battle = None  # 上一季沒打完（或打完沒清掉）的戰鬥不帶進新的一季
            state.faction_rolls = {}  # 新的一季大家重新投靠
            result["ok"] = True

        self.mutate(_apply)
        return result["ok"]

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
        self.mutate(lambda state: state.faction_rolls.__setitem__(name, faction_id))

    def faction_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for faction_id in self.read().faction_rolls.values():
            counts[faction_id] = counts.get(faction_id, 0) + 1
        return counts

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

    def start_battle(self, definition: BattleDef, now: float) -> BattleInstance:
        result: dict[str, BattleInstance] = {}

        def _apply(state: SharedWorldState) -> None:
            if state.active_battle is not None and state.active_battle.phase != "ended":
                result["battle"] = state.active_battle
                return
            state.active_battle = start_muster(definition, now)
            result["battle"] = state.active_battle

        self.mutate(_apply)
        return result["battle"]

    def clear_battle(self) -> None:
        self.mutate(lambda state: setattr(state, "active_battle", None))

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
