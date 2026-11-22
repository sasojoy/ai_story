"""異聞的旁檔 <db stem>-yiwen.sqlite（資料庫第 9 版不升；表都是 CREATE TABLE IF NOT EXISTS，之後加表不 ALTER 舊表）。

照帖友書信（features/mail/store.py）的做法：不進角色存檔，一則一列、一幕一列。丟了這個檔只是看不到異聞，遊戲照玩
（眼前那一則畫不出來：選單不接管、下一次同步清掉，見 actions.valid）。鍵一律是 ctx._mall_owner()（名號的 casefold）；
易名帖改名時由核心 core/renames 叫 rename 換掉（*_shown 不動：照說話那一刻）。

表（總計畫「異聞一」那一張）：tales（一則）、nodes（一幕）、walks（誰走過哪一則）、reports、mutes（異聞四才寫，這一批只建表）。
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS tales (id INTEGER PRIMARY KEY AUTOINCREMENT, season INTEGER NOT NULL, opening TEXT NOT NULL, place TEXT NOT NULL, "
    "discoverer TEXT NOT NULL, discoverer_shown TEXT NOT NULL, discovered_at REAL NOT NULL, status TEXT NOT NULL, "
    "verdict_node INTEGER, verdict_side TEXT, settled_at REAL, UNIQUE (season, opening))",
    "CREATE TABLE IF NOT EXISTS nodes (id INTEGER PRIMARY KEY AUTOINCREMENT, tale INTEGER NOT NULL, parent INTEGER NOT NULL, depth INTEGER NOT NULL, "
    "pick TEXT NOT NULL, typed INTEGER NOT NULL DEFAULT 0, by TEXT NOT NULL, by_shown TEXT NOT NULL, luck TEXT NOT NULL, text TEXT NOT NULL, "
    "options TEXT NOT NULL, ledger TEXT NOT NULL, fallback INTEGER NOT NULL DEFAULT 0, branch INTEGER NOT NULL DEFAULT 0, paid TEXT, "
    "hidden TEXT NOT NULL DEFAULT '', views INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, UNIQUE (tale, parent, pick))",
    "CREATE INDEX IF NOT EXISTS nodes_tale ON nodes (tale, parent)",
    "CREATE TABLE IF NOT EXISTS walks (tale INTEGER NOT NULL, account TEXT NOT NULL, season INTEGER NOT NULL, path TEXT NOT NULL, "
    "side TEXT NOT NULL DEFAULT '', started_at REAL NOT NULL, finished_at REAL, PRIMARY KEY (tale, account))",
    "CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, tale INTEGER NOT NULL, node INTEGER NOT NULL, target TEXT NOT NULL, "
    "kind TEXT NOT NULL, by TEXT NOT NULL, at REAL NOT NULL, resolved TEXT NOT NULL DEFAULT '', UNIQUE (node, target, kind, by))",
    "CREATE TABLE IF NOT EXISTS mutes (account TEXT PRIMARY KEY, until REAL NOT NULL, by TEXT NOT NULL, at REAL NOT NULL)",
)
TABLES = ("tales", "nodes", "walks", "reports", "mutes")
_JSON = ("text", "options", "ledger")

_OPEN: dict[Path, YiwenStore] = {}
_OPEN_LOCK = threading.Lock()


class Taken(Exception):
    """這一季這一句開場已經是一則了（UNIQUE(season, opening)）。"""


@dataclass
class AddResult:
    kind: str  # "new"／"taken"（同父同 pick 已經有人寫了：node 是那一列）／"full"（岔路開滿、或沒有免費名額又不能付）
    node: dict | None = None
    needs_pay: bool = False


def side_path(db_path: Path) -> Path:
    db_path = Path(db_path)
    return db_path.with_name(f"{db_path.stem}-yiwen.sqlite")


def for_db(db_path: Path) -> YiwenStore:
    """資料庫檔旁邊那一份（<stem>-yiwen.sqlite）；同一個檔只開一次。開了不建檔：第一次寫才建（第 251 批）。"""
    path = side_path(db_path)
    with _OPEN_LOCK:
        store = _OPEN.get(path)
        if store is None:
            store = _OPEN[path] = YiwenStore(path)
        return store


def store_of(ctx) -> YiwenStore | None:
    """這個世界的旁檔；測試用的記憶體世界沒有資料庫就是 None（異聞不開）。"""
    return store_of_world(getattr(ctx, "world", None))


def store_of_world(world_store) -> YiwenStore | None:
    """世界那一格用（異聞四）：world_store 是 None 或沒有 db.path 回 None。"""
    path = getattr(getattr(world_store, "db", None), "path", None)
    return None if path is None else for_db(path)


def _row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    out = dict(row)
    for key in _JSON:
        if key in out and isinstance(out[key], str):
            out[key] = json.loads(out[key])
    if "path" in out and isinstance(out["path"], str):
        out["path"] = json.loads(out["path"])
    return out


class YiwenStore:
    """第 251 批：檔等第一次真的要寫才建（沒人撞見過、撞見了還沒說第一步，都沒有這個檔）；讀的時候檔不在當成空、不建
    （sqlite3.connect 會建出空檔，所以讀之前先看檔在不在）。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._built = False

    def _ensure(self) -> None:
        """每一種寫法開連線之前先叫：檔不在、或這個物件還沒建過表，就建（表都是 IF NOT EXISTS）；檔被刪掉之後再寫也會重建表。"""
        if self._built and self.path.is_file():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(self._conn()) as conn, conn:
            conn.execute("PRAGMA journal_mode=WAL")
            for sql in _SCHEMA:
                conn.execute(sql)
        self._built = True

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _read(self, sql: str, args: tuple = ()) -> list[dict]:
        if not self.path.is_file():
            return []
        with contextlib.closing(self._conn()) as conn:
            return [_row(r) for r in conn.execute(sql, args).fetchall()]

    def _one(self, sql: str, args: tuple = ()) -> dict | None:
        got = self._read(sql, args)
        return got[0] if got else None

    def _write(self, sql: str, args: tuple = ()) -> int:
        self._ensure()
        with contextlib.closing(self._conn()) as conn, conn:
            cur = conn.execute(sql, args)
            return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount

    # ── 則 ──

    def open_tale(self, *, season: int, opening: str, place: str, by: str, shown: str, at: float) -> int:
        try:
            return self._write("INSERT INTO tales (season, opening, place, discoverer, discoverer_shown, discovered_at, status) "
                               "VALUES (?, ?, ?, ?, ?, ?, 'walking')", (season, opening, place, by, shown, at))
        except sqlite3.IntegrityError as exc:
            raise Taken(opening) from exc

    def tale(self, tid: int) -> dict | None:
        return self._one("SELECT * FROM tales WHERE id = ?", (tid,))

    def tales(self, season: int) -> list[dict]:
        return self._read("SELECT * FROM tales WHERE season = ? ORDER BY id", (season,))

    def tale_by_opening(self, season: int, opening: str) -> dict | None:
        """這一季這一句開場的那一則（UNIQUE(season, opening)，最多一列）；第 251 批撤回後接回用。"""
        return self._one("SELECT * FROM tales WHERE season = ? AND opening = ?", (season, opening))

    def walking(self, season: int) -> list[dict]:
        return self._read("SELECT * FROM tales WHERE season = ? AND status = 'walking' ORDER BY id", (season,))

    def set_status(self, tid: int, status: str) -> None:
        self._write("UPDATE tales SET status = ? WHERE id = ?", (status, tid))

    def settle(self, tid: int, *, node: int | None, side: str, at: float) -> None:
        self._write("UPDATE tales SET status = 'settled', verdict_node = ?, verdict_side = ?, settled_at = ? WHERE id = ?", (node, side, at, tid))

    # ── 幕 ──

    def node(self, nid: int) -> dict | None:
        return self._one("SELECT * FROM nodes WHERE id = ?", (nid,))

    def children(self, tale: int, parent: int) -> list[dict]:
        return self._read("SELECT * FROM nodes WHERE tale = ? AND parent = ? ORDER BY id", (tale, parent))

    def nodes(self, tale: int) -> list[dict]:
        return self._read("SELECT * FROM nodes WHERE tale = ? ORDER BY id", (tale,))

    def add_node(self, *, tale: int, parent: int, depth: int, pick: str, typed: bool, by: str, shown: str, luck: str, text: list[str],
                 options: list[str], ledger: list[str], fallback: bool, at: float, branch_cap: int, free_branches: int,
                 can_pay: bool, own: bool) -> AddResult:
        """一筆 BEGIN IMMEDIATE：同父同 pick 已在 → taken（那一列）；父節點已有別的子節點而且不是自己的路 → 這是一條岔路：
        重數已開的岔路，滿了 full；還有免費名額就寫；沒有就 can_pay 才寫（needs_pay），不然 full。寫成 new。"""
        self._ensure()
        with contextlib.closing(self._conn()) as conn:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                same = conn.execute("SELECT * FROM nodes WHERE tale = ? AND parent = ? AND pick = ?", (tale, parent, pick)).fetchone()
                if same is not None:
                    conn.execute("ROLLBACK")
                    return AddResult("taken", _row(same))
                siblings = conn.execute("SELECT COUNT(*) FROM nodes WHERE tale = ? AND parent = ?", (tale, parent)).fetchone()[0]
                branch, needs_pay = bool(siblings) and not own, False
                if branch:
                    opened = conn.execute("SELECT COUNT(*) FROM nodes WHERE tale = ? AND branch = 1", (tale,)).fetchone()[0]
                    if opened >= branch_cap:
                        conn.execute("ROLLBACK")
                        return AddResult("full")
                    if opened >= free_branches:
                        if not can_pay:
                            conn.execute("ROLLBACK")
                            return AddResult("full")
                        needs_pay = True
                cur = conn.execute(
                    "INSERT INTO nodes (tale, parent, depth, pick, typed, by, by_shown, luck, text, options, ledger, fallback, branch, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (tale, parent, depth, pick, int(typed), by, shown, luck, json.dumps(text, ensure_ascii=False),
                     json.dumps(options, ensure_ascii=False), json.dumps(ledger, ensure_ascii=False), int(fallback), int(branch), at))
                row = conn.execute("SELECT * FROM nodes WHERE id = ?", (cur.lastrowid,)).fetchone()
                conn.execute("COMMIT")
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    conn.execute("ROLLBACK")
                raise
        return AddResult("new", _row(row), needs_pay)

    def set_paid(self, nid: int, purchase_id) -> None:
        self._write("UPDATE nodes SET paid = ? WHERE id = ?", (None if purchase_id is None else str(purchase_id), nid))

    # ── 走 ──

    def walk(self, tid: int, account: str) -> dict | None:
        return self._one("SELECT * FROM walks WHERE tale = ? AND account = ?", (tid, account))

    def step_walk(self, *, tale: int, account: str, season: int, node: int, at: float) -> None:
        """沒有就建；path 接上這一個節點（走完的不再動）。"""
        self._ensure()
        with contextlib.closing(self._conn()) as conn, conn:
            row = conn.execute("SELECT path, finished_at FROM walks WHERE tale = ? AND account = ?", (tale, account)).fetchone()
            if row is None:
                conn.execute("INSERT INTO walks (tale, account, season, path, started_at) VALUES (?, ?, ?, ?, ?)",
                             (tale, account, season, json.dumps([node]), at))
            elif row["finished_at"] is None:
                path = json.loads(row["path"])
                if node in path:
                    path = path[:path.index(node)]
                conn.execute("UPDATE walks SET path = ? WHERE tale = ? AND account = ?", (json.dumps(path + [node]), tale, account))

    def restart_walk(self, *, tale: int, account: str) -> None:
        """重新走一則（放下之後再撞見）：沒走完的那一列的路清空，從開場接著記。"""
        self._write("UPDATE walks SET path = '[]' WHERE tale = ? AND account = ? AND finished_at IS NULL", (tale, account))

    def finish_walk(self, *, tale: int, account: str, side: str, at: float) -> bool:
        """第一次走完回 True（之後再叫不動、回 False）。"""
        return self._write("UPDATE walks SET finished_at = ?, side = ? WHERE tale = ? AND account = ? AND finished_at IS NULL",
                           (at, side, tale, account)) > 0

    def footprints(self, tid: int) -> dict[int, int]:
        """葉子 id → 走完的人數（走到一半的不算）。"""
        out: dict[int, int] = {}
        for row in self._read("SELECT path FROM walks WHERE tale = ? AND finished_at IS NOT NULL", (tid,)):
            if row["path"]:
                leaf = row["path"][-1]
                out[leaf] = out.get(leaf, 0) + 1
        return out

    def steps(self, tid: int) -> dict[int, int]:
        """節點 id → 走過而且走完的人數。"""
        out: dict[int, int] = {}
        for row in self._read("SELECT path FROM walks WHERE tale = ? AND finished_at IS NOT NULL", (tid,)):
            for nid in row["path"]:
                out[nid] = out.get(nid, 0) + 1
        return out

    # ── 禁寫（第 252 批先接讀法；寫的管理者動作是異聞四）──

    def muted(self, account: str, now: float) -> bool:
        """這個鍵現在被禁寫（mutes.until 在 now 之後）：自己說灰掉、猜法照走。只讀；檔不在當成沒有。now 是季鐘。"""
        row = self._one("SELECT until FROM mutes WHERE account = ?", (account,))
        return row is not None and float(row["until"]) > float(now)

    # ── 易名帖 ──

    def rename(self, old_key: str, new_key: str) -> None:
        if not old_key or old_key == new_key:
            return
        self._ensure()
        with contextlib.closing(self._conn()) as conn, conn:
            conn.execute("UPDATE tales SET discoverer = ? WHERE discoverer = ?", (new_key, old_key))
            conn.execute("UPDATE nodes SET by = ? WHERE by = ?", (new_key, old_key))
            conn.execute("UPDATE OR IGNORE walks SET account = ? WHERE account = ?", (new_key, old_key))
            conn.execute("UPDATE OR IGNORE reports SET by = ? WHERE by = ?", (new_key, old_key))
            conn.execute("UPDATE OR IGNORE mutes SET account = ? WHERE account = ?", (new_key, old_key))
