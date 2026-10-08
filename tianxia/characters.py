"""角色存檔（線上架構設計第三節）：一個角色一列，存 GameState——不含賽季（賽季在全服狀態裡，見 sqlite_world；
Game 每次建構、每次 sync 都會把 state.world 指向共用賽季）。

名號同服不重複、比對不分大小寫（第六節）：主鍵是名號的 casefold，另存原本的寫法。
是不是假人（is_bot）只給假人程式挑人用，任何畫面都不能顯示（伺服器假人設計第五節）。
"""
from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from .database import Database, open_database
from .state import GameState


def name_key(name: str) -> str:
    """名號比對用的鍵：前後空白去掉、不分大小寫。"""
    return (name or "").strip().casefold()


def open_characters(path: Path | None = None) -> CharacterStore:
    """開 path 那個資料庫檔的角色存檔；沒給就開預設的資料庫（環境變數 TIANXIA_DB 或 saves/tianxia.db）。"""
    return CharacterStore(open_database(path))


class CharacterStore:
    def __init__(self, db: Database):
        self.db = db

    def save(self, state: GameState) -> None:
        p = state.player
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO characters (key, name, is_bot, faction, data) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (key) DO UPDATE SET name = excluded.name, is_bot = excluded.is_bot, "
                "faction = excluded.faction, data = excluded.data",
                (name_key(p.name), p.name, p.bot is not None, p.faction, state.model_dump_json()),
            )

    def load(self, name: str) -> GameState | None:
        """沒有這個角色回傳 None；讀不懂（舊格式）丟 pydantic 的 ValidationError，呼叫端決定要不要備份重開。"""
        with self.db.snapshot() as conn:
            row = conn.execute("SELECT data FROM characters WHERE key = ?", (name_key(name),)).fetchone()
        return None if row is None else GameState.model_validate_json(row["data"])

    def exists(self, name: str) -> bool:
        with self.db.snapshot() as conn:
            return conn.execute("SELECT 1 FROM characters WHERE key = ?", (name_key(name),)).fetchone() is not None

    def names(self) -> set[str]:
        """所有角色的名號（照原本的寫法），讀不懂的存檔也算在內。"""
        with self.db.snapshot() as conn:
            return {row["name"] for row in conn.execute("SELECT name FROM characters")}

    def present(self, location: str, since: float, exclude: str = "") -> list[GameState]:
        """此刻人在 location、上次同步不早於 since 的角色（玩家之間的互動第一層：「此地還有誰」），照名號排序；exclude 是名號，
        不列自己。真人與假人一起查、不分（伺服器假人設計第五節）。在 SQL 裡先挑地點與時間，免得每次畫面都把整張表讀進來；
        讀不懂的存檔跳過。路上、序章裡的人由呼叫端再篩（social.visible）。"""
        sql = (
            "SELECT data FROM characters WHERE json_extract(data, '$.player.location') = ? "
            "AND json_extract(data, '$.last_real') >= ? AND key != ? ORDER BY name"
        )
        with self.db.snapshot() as conn:
            rows = conn.execute(sql, (location, since, name_key(exclude))).fetchall()
        states: list[GameState] = []
        for row in rows:
            try:
                states.append(GameState.model_validate_json(row["data"]))
            except ValidationError:
                continue
        return states

    def tagging(self, leader: str) -> list[GameState]:
        """答應跟著 leader（名號原樣）結伴同行的人（PlayerState.tagalong），照名號排序；還算不算數由呼叫端看（social.party）。"""
        sql = "SELECT data FROM characters WHERE json_extract(data, '$.player.tagalong.leader') = ? ORDER BY name"
        with self.db.snapshot() as conn:
            rows = conn.execute(sql, (leader,)).fetchall()
        states: list[GameState] = []
        for row in rows:
            try:
                states.append(GameState.model_validate_json(row["data"]))
            except ValidationError:
                continue
        return states

    def all(self, bots_only: bool = False) -> list[GameState]:
        """照名號排序；讀不懂的存檔跳過（不讓一份壞檔拖垮榜單或假人程式）。"""
        sql = "SELECT data FROM characters" + (" WHERE is_bot = 1" if bots_only else "") + " ORDER BY name"
        with self.db.snapshot() as conn:
            rows = conn.execute(sql).fetchall()
        states: list[GameState] = []
        for row in rows:
            try:
                states.append(GameState.model_validate_json(row["data"]))
            except ValidationError:
                continue
        return states

    def backup(self, name: str) -> None:
        """讀不懂的存檔搬到 character_backups（不刪任何東西），這個名號就能重新開始。"""
        with self.db.transaction() as conn:
            row = conn.execute("SELECT key, data FROM characters WHERE key = ?", (name_key(name),)).fetchone()
            if row is None:
                return
            conn.execute("INSERT INTO character_backups (key, data) VALUES (?, ?)", (row["key"], row["data"]))
            conn.execute("DELETE FROM characters WHERE key = ?", (row["key"],))
