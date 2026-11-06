"""往來紀錄（介面重整 2026-11-05，Joy「我們可以讓用戶看他們跟大勢人物的歷史對話紀錄嗎」）：你跟每一位大勢人物說過的每一句。

存在資料庫旁邊的小檔 <db>-talk.sqlite（同 narration 的 <db>-narration.sqlite），不進角色存檔：角色那一整塊 JSON 每個動作都在行動鎖裡
整份讀寫，紀錄放進去會越存越慢（Joy 11/5「這樣的資料結構在之後玩家多的時候會壓垮我們嗎」）。一句一列，打開紀錄才分頁讀；
兩季以前的整批搬到 <db>-talk-archive.sqlite（同傳聞的封存），主檔只留這一季與上一季。丟了這個檔只是看不到舊紀錄，遊戲照玩。

模型照舊只看角色存檔裡最近的那幾十則（companion_agent.MAX_HISTORY_MESSAGES）；這裡只給畫面讀。
怎麼知道這一下多談了幾輪：每談一輪 used_dialogue_options 多一句、dialogue_history 多兩則（玩家一句、人物一句），
伺服器在動作前後各數一次（snapshot / new_lines），不用改引擎。
"""
from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

PAGE = 30  # 一次讀幾句

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS talk (id INTEGER PRIMARY KEY AUTOINCREMENT, who TEXT NOT NULL, season INTEGER NOT NULL, "
    "figure TEXT NOT NULL, at REAL NOT NULL, stamp TEXT NOT NULL, place TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL, "
    "affinity INTEGER NOT NULL DEFAULT 0)",
    "CREATE INDEX IF NOT EXISTS talk_by_who ON talk (who, figure, season, id)",
)


def snapshot(state) -> dict[str, int]:
    """動作之前：每一位人物你已經說過幾句（used_dialogue_options 的長度）；情誼另記在 affinity_before 照抄一份。"""
    return {cid: len(said) for cid, said in state.player.used_dialogue_options.items()}


def affinity_before(state) -> dict[str, int]:
    """動作之前的情誼：玩家那一句記動作前的、人物那一句記動作後的，畫面照兩句相減寫「情誼 +N」。"""
    return dict(state.player.affinities)


def new_lines(state, before: dict[str, int]) -> list[tuple[str, str, str]]:
    """動作之後：多出來的那幾輪 → [(人物 id, role, 那一句)]，照說話的順序。一輪兩句：玩家（user）、人物（assistant）。"""
    p = state.player
    out: list[tuple[str, str, str]] = []
    for cid, said in p.used_dialogue_options.items():
        turns = len(said) - before.get(cid, 0)
        if turns <= 0:
            continue
        history = p.dialogue_history.get(cid, [])
        for line in history[-2 * turns:]:
            out.append((cid, line.get("role", ""), line.get("content", "")))
    return out


class TalkLogStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.archive_path = self.path.with_name(self.path.name.replace(".sqlite", "-archive.sqlite"))
        self._swept = -1
        with contextlib.closing(self._conn(self.path)) as conn, conn:
            for sql in _SCHEMA:
                conn.execute(sql)

    @staticmethod
    def _conn(path: Path) -> sqlite3.Connection:
        conn = sqlite3.connect(path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, who: str, season: int, rows: list[dict]) -> None:
        """記幾句（rows 每一筆：figure、at、stamp、place、role、text、affinity）。換了季的第一筆順手把兩季以前的搬去封存檔。"""
        if not rows:
            return
        with contextlib.closing(self._conn(self.path)) as conn, conn:
            conn.executemany(
                "INSERT INTO talk (who, season, figure, at, stamp, place, role, text, affinity) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(who, season, r["figure"], r["at"], r["stamp"], r["place"], r["role"], r["text"], int(r.get("affinity", 0)))
                 for r in rows])
        if self._swept != season:
            self._swept = season
            self.archive_before(season - 1)

    def archive_before(self, season: int) -> int:
        """season 以前（不含）的整批搬到封存檔；回傳搬了幾句。"""
        with contextlib.closing(self._conn(self.path)) as conn:
            old = conn.execute("SELECT * FROM talk WHERE season < ?", (season,)).fetchall()
        if not old:
            return 0
        with contextlib.closing(self._conn(self.archive_path)) as arc, arc:
            for sql in _SCHEMA:
                arc.execute(sql)
            arc.executemany(
                "INSERT INTO talk (who, season, figure, at, stamp, place, role, text, affinity) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(r["who"], r["season"], r["figure"], r["at"], r["stamp"], r["place"], r["role"], r["text"], r["affinity"]) for r in old])
        with contextlib.closing(self._conn(self.path)) as conn, conn:
            conn.execute("DELETE FROM talk WHERE season < ?", (season,))
        return len(old)

    def page(self, who: str, figure: str, season: int, before: int | None = None, limit: int = PAGE) -> tuple[list[dict], bool]:
        """這一季（season）你跟他的紀錄，新的在前，一次 limit 句；before 是上一頁最舊那一句的 id。回傳（幾句, 還有沒有更舊的）。
        兩季以前的在封存檔：主檔沒有就去那裡找。"""
        sql = "SELECT * FROM talk WHERE who = ? AND figure = ? AND season = ?" + (" AND id < ?" if before else "") + " ORDER BY id DESC LIMIT ?"
        args = (who, figure, season, *((before,) if before else ()), limit + 1)
        rows: list = []
        for path in (self.path, self.archive_path):
            if not path.is_file():
                continue
            with contextlib.closing(self._conn(path)) as conn:
                try:
                    rows = conn.execute(sql, args).fetchall()
                except sqlite3.OperationalError:  # 封存檔還沒有這張表
                    rows = []
            if rows:
                break
        more = len(rows) > limit
        return [dict(r) for r in rows[:limit]], more

    def meets(self, who: str, figure: str) -> int:
        """見過幾次：照紀錄裡不同的那幾天（同一天同一處談幾輪都算一次見面）數。只數主檔（這一季與上一季）。"""
        with contextlib.closing(self._conn(self.path)) as conn:
            rows = conn.execute("SELECT DISTINCT season, place, stamp FROM talk WHERE who = ? AND figure = ?", (who, figure)).fetchall()
        return len({(r["season"], r["place"], r["stamp"].rsplit(" ", 1)[0]) for r in rows})
