"""封存區（審查 S-12，企劃者 Joy「上上季的資料存在另一個封存區備用」）：只會一直長大的傳聞（`rumors`）與決戰回合紀錄
（`battle_rounds`），換季時把上上季（含更早）的搬到資料庫旁邊另一個檔 `<資料庫檔名>-archive.sqlite`，主檔只留這一季與上一季。
江湖史（`chronicle`）不搬、跨季照留；決戰本身（`battles`，戰報照它重讀完整戰況、參戰者補送戰報）不搬；戰記本來就在另一個小檔。

搬法（SqliteWorldStore.next_season 在換季那一筆交易裡叫 move_old_logs）：
1. 主檔的寫入交易裡讀出要搬的列；
2. 另開一條連線把它們寫進封存檔、在那裡 COMMIT（同一個流水號 INSERT OR REPLACE：再搬一次不會重複）；
3. 封存檔 COMMIT 成功了，才在主檔的同一筆交易裡（一個 savepoint）刪掉那幾列。
任何一步出錯都只是這一次不搬：封存檔寫不進去就不刪、刪不掉就撤回那個 savepoint，換季照常成功，下一次換季再搬。
主檔那一筆之後撤回時，封存檔裡多一份、主檔還在——同一筆資料兩邊都有，不會兩邊都沒有。
不用 ATTACH：交易裡不能 ATTACH，主檔是 WAL，跨檔的交易也只有各自原子、不是一起原子。

封存檔只寫不讀（遊戲裡沒有任何畫面讀它），是備用的；要查就自己開那個檔。
"""
from __future__ import annotations

import contextlib
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

KEEP_SEASONS = 2  # 主檔留幾季：這一季與上一季（新開的第 N 季 → 第 N-2 季與更早的搬走）

ARCHIVE_SCHEMA: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS rumors (
        id INTEGER PRIMARY KEY,
        season INTEGER NOT NULL,
        time REAL NOT NULL,
        layer TEXT NOT NULL,
        faction TEXT,
        region TEXT,
        location TEXT,
        character TEXT,
        named INTEGER NOT NULL,
        text TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS rumors_by_season ON rumors (season, id)",
    # 主檔的 battle_rounds 沒有季數（照 battles.season 認）；封存時一起記下來，封存檔不帶 battles
    """CREATE TABLE IF NOT EXISTS battle_rounds (
        id INTEGER PRIMARY KEY,
        battle_id INTEGER NOT NULL,
        season INTEGER NOT NULL,
        data TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS battle_rounds_by_battle ON battle_rounds (battle_id, id)",
)

_RUMOR_COLUMNS = "id, season, time, layer, faction, region, location, character, named, text"
_OLD_ROUNDS = (
    "SELECT r.id AS id, r.battle_id AS battle_id, b.season AS season, r.data AS data "
    "FROM battle_rounds r JOIN battles b ON b.id = r.battle_id WHERE b.season <= ? ORDER BY r.id"
)


def archive_path(db_path: Path) -> Path:
    """主資料庫檔旁邊的封存檔（跟戰記的 `-tale.sqlite` 同一種取名）：saves/tianxia.db → saves/tianxia-archive.sqlite。"""
    db_path = Path(db_path)
    return db_path.with_name(f"{db_path.stem}-archive.sqlite")


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA synchronous = FULL")
    return conn


def _write_archive(path: Path, rumors: list[tuple], rounds: list[tuple]) -> None:
    """寫進封存檔並 COMMIT；出錯整筆撤回、例外照丟。"""
    with contextlib.closing(_connect(path)) as conn:
        with conn:  # 一筆交易：成功 COMMIT、出錯 ROLLBACK
            for statement in ARCHIVE_SCHEMA:
                conn.execute(statement)
            conn.executemany(f"INSERT OR REPLACE INTO rumors ({_RUMOR_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rumors)
            conn.executemany("INSERT OR REPLACE INTO battle_rounds (id, battle_id, season, data) VALUES (?, ?, ?, ?)", rounds)


def move_old_logs(db, conn: sqlite3.Connection, upto_season: int) -> tuple[int, int] | None:
    """把第 upto_season 季與更早的傳聞、決戰回合紀錄搬進封存檔，再從主檔刪掉。db 是 database.Database、conn 是它這個執行緒
    正在寫入交易裡的連線（呼叫端握著寫入權，讀出來到刪掉之間沒有別人寫）。回（搬了幾則傳聞, 幾回合）；沒東西可搬回 (0, 0)；
    這一次沒搬成（封存檔寫不進去、主檔刪不掉）回 None，主檔原封不動、換季照常。"""
    if upto_season < 1:
        return (0, 0)
    rumors = [tuple(r) for r in conn.execute(
        f"SELECT {_RUMOR_COLUMNS} FROM rumors WHERE season <= ? ORDER BY id", (upto_season,))]
    rounds = [tuple(r) for r in conn.execute(_OLD_ROUNDS, (upto_season,))]
    if not rumors and not rounds:
        return (0, 0)
    try:
        _write_archive(archive_path(db.path), rumors, rounds)
    except Exception:  # noqa: BLE001  封存檔寫不進去（磁碟滿、權限、檔壞了）：這一次不搬、主檔不刪，換季照常
        log.exception("封存上上季的傳聞與回合紀錄失敗，這一次不搬（主檔原封不動）")
        return None
    try:
        with db.savepoint() as c:
            if rumors:
                c.execute("DELETE FROM rumors WHERE season <= ? AND id <= ?", (upto_season, rumors[-1][0]))
            if rounds:
                c.execute(
                    "DELETE FROM battle_rounds WHERE id <= ? AND battle_id IN (SELECT id FROM battles WHERE season <= ?)",
                    (rounds[-1][0], upto_season),
                )
    except Exception:  # noqa: BLE001  刪不掉：撤回這一段，封存檔多一份備用，換季照常（下一次再搬，同一個流水號照蓋）
        log.exception("封存之後從主檔刪掉上上季的傳聞與回合紀錄失敗，這一次不刪")
        return None
    return (len(rumors), len(rounds))
