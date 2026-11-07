"""同意紀錄的小檔（sqlite，遊戲資料庫旁邊的 <db>-terms.sqlite，同手機通知的 <db>-push.sqlite）：一筆是「帳號、哪一版、什麼時候、從哪裡同意」，
只加不刪（日後有爭議拿得出來）。不進遊戲資料庫：資料庫不升版，換回舊程式只是沒有人被問同意。認帳號（accounts 的鍵），不認名號。"""
from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

SOURCES = ("register", "gate", "update")  # 註冊時勾的、登入後第一次按的、改版頁按的


class ConsentStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(self._conn()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS consents (id INTEGER PRIMARY KEY, account TEXT NOT NULL, version TEXT NOT NULL, "
                "source TEXT NOT NULL, at REAL NOT NULL)")
            conn.execute("CREATE INDEX IF NOT EXISTS consents_by_account ON consents (account, id)")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def record(self, account: str, version: str, source: str, at: float) -> None:
        if source not in SOURCES:
            raise ValueError(f"不認得的來源：{source}")
        with contextlib.closing(self._conn()) as conn, conn:
            conn.execute("INSERT INTO consents (account, version, source, at) VALUES (?, ?, ?, ?)", (account, version, source, at))

    def latest(self, account: str) -> str | None:
        """這個帳號最後同意的版本；沒同意過是 None。"""
        with contextlib.closing(self._conn()) as conn:
            row = conn.execute("SELECT version FROM consents WHERE account = ? ORDER BY id DESC LIMIT 1", (account,)).fetchone()
        return None if row is None else row["version"]

    def history(self, account: str) -> list[dict]:
        with contextlib.closing(self._conn()) as conn:
            return [dict(r) for r in conn.execute("SELECT version, source, at FROM consents WHERE account = ? ORDER BY id", (account,))]
