"""SQLite 資料庫（線上架構設計第三節）：帳號、角色、全服狀態、傳聞、江湖史、戰鬥都在一個檔案裡。

一個動作＝一筆交易：transaction() 用 BEGIN IMMEDIATE 拿寫入權，做完 COMMIT、出錯 ROLLBACK。
第 1 期還是兩支程式（server.py 與 run_bots.py）寫同一個檔案，SQLite 的寫入權取代原本的檔案鎖：
timeout=None 等到拿到為止（伺服器），給秒數時等不到就丟 TimeoutError（假人程式跳過這一輪）。
程式被強制結束時，沒 COMMIT 的交易由 SQLite 自己撤掉，不會留下卡住別人的鎖。

每個執行緒一條連線，執行緒結束時那條連線跟著關掉（網頁伺服器的工作執行緒會來來去去）。同一個執行緒裡
巢狀的 transaction() 併進最外層那一筆（可重入）；snapshot() 是唯讀交易：幾句 SELECT 看到同一個時間點，
也不擋寫入的人（WAL 模式），離開時一律 ROLLBACK，在裡面誤寫的東西不會留下來。

COMMIT 失敗（例如延後檢查的外鍵到這時才出錯）時交易還開著，這裡會接著 ROLLBACK 再把 COMMIT 的錯丟出去，
不會讓這條連線永遠握著寫入權；SQLite 已經自己撤掉交易（磁碟滿、I/O 錯誤）時就不再下 ROLLBACK，
免得另一個錯把本來的錯蓋掉。

資料庫結構的版本記在 PRAGMA user_version。改結構時：新表或新欄加進新的一組句子、`SCHEMA` 接上它、
`MIGRATIONS[舊版]` 指向它、`SCHEMA_VERSION` 加一；舊檔打開時照 `MIGRATIONS` 一版一版升上來
（升級在同一筆交易裡，中途出錯整個撤回，檔還是舊版）。
"""
from __future__ import annotations

import contextlib
import os
import sqlite3
import threading
import time
import weakref
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "saves" / "tianxia.db"
ENV_VAR = "TIANXIA_DB"  # 線上版與開發版用不同的資料（線上架構設計 8.1）：設了這個環境變數就開那個檔
BUSY_SLICE = 5.0  # 不限時等寫入權時，每次最多等幾秒就重試一次

# 第 1 版的結構。已經有檔案是這個樣子了（試玩伺服器），不要再改它；要改結構就加新的一組、升版本。
SCHEMA_V1: tuple[str, ...] = (
    # 全服的小資料（SharedWorldState 除了賽季與目前的決戰），整份覆寫；只有 id = 1 一列
    """CREATE TABLE world (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        data TEXT NOT NULL,
        active_battle_id INTEGER REFERENCES battles (id)
    )""",
    # 一季一列（WorldState 去掉傳聞與江湖史），整份覆寫；換季另起一列，舊的一季留著
    """CREATE TABLE seasons (
        number INTEGER PRIMARY KEY,
        data TEXT NOT NULL
    )""",
    # 傳聞（傳聞分層設計第二、七節）：layer 是天下大事 world／陣營軍情 faction／地方傳聞 local／個人線索 personal
    """CREATE TABLE rumors (
        id INTEGER PRIMARY KEY,
        season INTEGER NOT NULL,
        time REAL NOT NULL,
        layer TEXT NOT NULL CHECK (layer IN ('world', 'faction', 'local', 'personal')),
        faction TEXT,
        region TEXT,
        location TEXT,
        character TEXT,
        named INTEGER NOT NULL DEFAULT 1,
        text TEXT NOT NULL
    )""",
    "CREATE INDEX rumors_by_season ON rumors (season, id)",
    # 見聞紀錄（傳聞分層設計 3.1）：第 1 期只建表，傳聞分層的規則實作才寫入
    """CREATE TABLE rumor_heard (
        character TEXT NOT NULL,
        rumor_id INTEGER NOT NULL REFERENCES rumors (id),
        PRIMARY KEY (character, rumor_id)
    )""",
    # 江湖史：跨季保留，每筆記著第幾季
    """CREATE TABLE chronicle (
        id INTEGER PRIMARY KEY,
        season INTEGER NOT NULL,
        time REAL NOT NULL,
        location TEXT,
        text TEXT NOT NULL
    )""",
    "CREATE INDEX chronicle_by_season ON chronicle (season, id)",
    # 自創與煉製的功法、煉製配方：每季各一份，記取名者／首創者
    """CREATE TABLE skills (
        season INTEGER NOT NULL,
        name TEXT NOT NULL,
        creator TEXT,
        data TEXT NOT NULL,
        PRIMARY KEY (season, name)
    )""",
    """CREATE TABLE recipes (
        season INTEGER NOT NULL,
        key TEXT NOT NULL,
        skill_name TEXT NOT NULL,
        creator TEXT,
        PRIMARY KEY (season, key),
        FOREIGN KEY (season, skill_name) REFERENCES skills (season, name)
    )""",
    # 投靠名冊：一季裡一個名號投靠哪個陣營（真人與假人一起記，不記誰是假人）
    """CREATE TABLE faction_rolls (
        season INTEGER NOT NULL,
        character TEXT NOT NULL,
        faction TEXT NOT NULL,
        PRIMARY KEY (season, character)
    )""",
    # 全服決戰（不含回合紀錄），整份覆寫；結算過的回合一回合一列
    """CREATE TABLE battles (
        id INTEGER PRIMARY KEY,
        season INTEGER NOT NULL,
        battle_def TEXT NOT NULL,
        phase TEXT NOT NULL,
        outcome_title TEXT,
        data TEXT NOT NULL
    )""",
    """CREATE TABLE battle_rounds (
        id INTEGER PRIMARY KEY,
        battle_id INTEGER NOT NULL REFERENCES battles (id),
        data TEXT NOT NULL
    )""",
    "CREATE INDEX battle_rounds_by_battle ON battle_rounds (battle_id, id)",
    # 角色：key 是名號的 casefold（同服不分大小寫不重複，線上架構設計第六節）；data 是 GameState（不含賽季）
    """CREATE TABLE characters (
        key TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        is_bot INTEGER NOT NULL,
        faction TEXT,
        data TEXT NOT NULL
    )""",
    # 讀不懂的舊存檔搬到這裡（不刪任何東西）
    """CREATE TABLE character_backups (
        id INTEGER PRIMARY KEY,
        key TEXT NOT NULL,
        data TEXT NOT NULL
    )""",
    # 帳號；一個帳號一個角色。帳號的登入方式另一張表：第 1 期只有 password，第 3 期加 line、google
    """CREATE TABLE accounts (
        id INTEGER PRIMARY KEY,
        character TEXT,
        character_key TEXT UNIQUE,
        created REAL NOT NULL
    )""",
    """CREATE TABLE logins (
        provider TEXT NOT NULL,
        subject TEXT NOT NULL,
        account_id INTEGER NOT NULL REFERENCES accounts (id),
        display TEXT NOT NULL,
        salt TEXT,
        hash TEXT,
        PRIMARY KEY (provider, subject)
    )""",
)

# 第 2 版（武學與成長設計 3.2、3.6）：改過的名字、合併出來的意境、第一個練成絕學的人。都照季分，換季不刪。
SCHEMA_V2_TABLES: tuple[str, ...] = (
    # 修到絕學時第一人取的正式名字：功法 id（skills.name）不變，新名記在這裡，全服重名檢查一起看
    """CREATE TABLE skill_aliases (
        season INTEGER NOT NULL,
        name TEXT NOT NULL,
        skill_name TEXT NOT NULL,
        PRIMARY KEY (season, name)
    )""",
    # 合併出來的意境：名字就是 id；基本意境在 content/insights.json，不在這裡
    """CREATE TABLE insights (
        season INTEGER NOT NULL,
        name TEXT NOT NULL,
        creator TEXT,
        data TEXT NOT NULL,
        PRIMARY KEY (season, name)
    )""",
    """CREATE TABLE insight_recipes (
        season INTEGER NOT NULL,
        key TEXT NOT NULL,
        insight_name TEXT NOT NULL,
        creator TEXT,
        PRIMARY KEY (season, key)
    )""",
    # 每門武學這一季第一個修到絕學的人
    """CREATE TABLE masters (
        season INTEGER NOT NULL,
        skill_name TEXT NOT NULL,
        master TEXT NOT NULL,
        PRIMARY KEY (season, skill_name)
    )""",
)

SCHEMA: tuple[str, ...] = SCHEMA_V1 + SCHEMA_V2_TABLES  # 新檔一次建好
MIGRATIONS: dict[int, tuple[str, ...]] = {1: SCHEMA_V2_TABLES}  # 第 n 版 → 第 n+1 版要跑的句子
SCHEMA_VERSION = 2


def default_path() -> Path:
    """預設的資料庫檔：設了環境變數 TIANXIA_DB 就用它，否則 saves/tianxia.db。呼叫當下才讀。"""
    override = os.environ.get(ENV_VAR)
    return Path(override) if override else DEFAULT_PATH


class _ThreadState:
    """一個執行緒在這個資料庫上的連線與交易狀態。放在 threading.local 裡：執行緒結束、local 被釋放時，
    這個物件被回收，登記的 weakref.finalize 就把連線關掉。"""

    __slots__ = ("conn", "depth", "reading", "rewriting", "__weakref__")

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.depth = 0  # 寫入交易的巢狀深度，0 表示不在寫入交易裡
        self.reading = False  # 是不是在 snapshot() 的最外層
        self.rewriting = False  # 是不是在 rewriting() 的區段裡（整份讀出、改、整份寫回）


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._local = threading.local()
        self._states: weakref.WeakSet[_ThreadState] = weakref.WeakSet()
        self._states_lock = threading.Lock()
        try:
            self._ensure_schema()
        except BaseException:
            self.close()  # 版本不對時也要把剛開的連線關掉
            raise

    def _thread(self) -> _ThreadState:
        """這個執行緒的連線與交易狀態；第一次用時開連線。"""
        local = self._local
        state = getattr(local, "state", None)
        if state is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=BUSY_SLICE, autocommit=True, check_same_thread=False)
            try:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = FULL")  # 每次 COMMIT 都寫進磁碟：WAL 搭 NORMAL 停電時可能少掉最後幾筆已 COMMIT 的
                conn.execute("PRAGMA foreign_keys = ON")
            except BaseException:
                conn.close()  # 設定沒做完的連線不留著，不然它沒人管、也不會被回收
                raise
            state = _ThreadState(conn)
            weakref.finalize(state, conn.close)  # 執行緒結束、state 被回收時關連線（不能參照 state 本身）
            local.state = state
            with self._states_lock:
                self._states.add(state)
        return state

    @contextlib.contextmanager
    def transaction(self, timeout: float | None = None) -> Iterator[sqlite3.Connection]:
        state = self._thread()  # 進出都用同一個 state：離開時不重新查 threading.local
        conn = state.conn
        if state.reading:
            raise RuntimeError("讀取快照裡不能寫入：先離開 snapshot() 再開交易")
        if state.depth:
            state.depth += 1
            try:
                yield conn
            finally:
                state.depth -= 1
            return
        self._begin(conn, timeout)
        state.depth = 1
        try:
            yield conn
        except BaseException:
            state.depth = 0
            self._rollback(conn)
            raise
        state.depth = 0
        try:
            conn.execute("COMMIT")
        except BaseException:
            self._rollback(conn)  # COMMIT 失敗時交易還開著：不撤掉，這條連線就永遠握著寫入權
            raise

    @contextlib.contextmanager
    def rewriting(self) -> Iterator[None]:
        """整份讀出、改、整份寫回（SqliteWorldStore.mutate）的區段，同一個執行緒不能巢狀：內層寫的東西
        會被外層最後的整份存檔蓋掉、悄悄不見。同一個檔案的所有 store 共用同一個 Database，所以不同的 store
        物件之間巢狀也擋得到。要巢狀就改成在同一個 mutate 裡一次改完。"""
        state = self._thread()
        if state.rewriting:
            raise RuntimeError(
                "mutate 不能巢狀：裡面再呼叫一次 mutate（或靠它實作的方法），內層寫的會被外層的整份存檔蓋掉；"
                "請在同一個 mutate 的函式裡一次改完"
            )
        state.rewriting = True
        try:
            yield
        finally:
            state.rewriting = False

    @staticmethod
    def _rollback(conn: sqlite3.Connection) -> None:
        """撤掉還開著的交易；SQLite 已經自己撤掉了（磁碟滿、I/O 錯誤）就什麼都不做。"""
        if conn.in_transaction:
            conn.execute("ROLLBACK")

    def _begin(self, conn: sqlite3.Connection, timeout: float | None) -> None:
        deadline = None if timeout is None else time.monotonic() + timeout
        try:
            while True:
                wait = BUSY_SLICE if deadline is None else max(0.0, deadline - time.monotonic())
                conn.execute(f"PRAGMA busy_timeout = {int(wait * 1000)}")
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    return
                except sqlite3.OperationalError as exc:
                    if exc.sqlite_errorcode & 0xFF not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                        raise
                    if deadline is not None and time.monotonic() >= deadline:
                        raise TimeoutError(f"等不到資料庫的寫入權：{self.path}") from exc
        finally:
            conn.execute(f"PRAGMA busy_timeout = {int(BUSY_SLICE * 1000)}")  # 別把剩下的零頭留給之後的讀取

    @contextlib.contextmanager
    def snapshot(self) -> Iterator[sqlite3.Connection]:
        state = self._thread()
        conn = state.conn
        if state.depth or state.reading:
            yield conn
            return
        conn.execute("BEGIN")  # DEFERRED：第一句 SELECT 才拿讀取的快照，不擋寫入的人
        state.reading = True
        try:
            yield conn
        finally:
            state.reading = False
            self._rollback(conn)  # 唯讀：一律 ROLLBACK，不 COMMIT

    def writing(self) -> bool:
        """這個執行緒現在是不是在寫入交易裡（沒碰過資料庫的執行緒不會因為問這句而開連線）。"""
        state = getattr(self._local, "state", None)
        return state is not None and state.depth > 0

    def _ensure_schema(self) -> None:
        with self.transaction() as conn:  # 拿到寫入權再看版本：兩支程式同時開新檔也只建一次
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == SCHEMA_VERSION:
                return
            if version == 0:
                statements = SCHEMA
            elif version < SCHEMA_VERSION and all(v in MIGRATIONS for v in range(version, SCHEMA_VERSION)):
                statements = tuple(s for v in range(version, SCHEMA_VERSION) for s in MIGRATIONS[v])
            else:
                raise RuntimeError(
                    f"資料庫結構是第 {version} 版，這版程式只認得第 {SCHEMA_VERSION} 版：{self.path}"
                )
            for statement in statements:
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        """關掉所有還活著的執行緒的連線（關兩次也沒事）。"""
        with self._states_lock:
            states = list(self._states)
            self._states.clear()
        for state in states:
            state.conn.close()
        self._local = threading.local()


_OPEN: dict[Path, Database] = {}
_OPEN_LOCK = threading.Lock()


def open_database(path: Path | None = None) -> Database:
    """同一個檔案在同一個程式裡只開一個 Database：同一個執行緒因此共用同一條連線、同一筆交易
    （全服狀態、角色、帳號各自的 store 才能在同一個動作裡一起寫進同一筆交易）。"""
    resolved = Path(path if path is not None else default_path()).resolve()
    with _OPEN_LOCK:
        if resolved not in _OPEN:
            _OPEN[resolved] = Database(resolved)
        return _OPEN[resolved]


def close_all() -> None:
    """關掉 open_database 開過的所有資料庫（測試結束時用，Windows 才刪得掉暫存檔）。"""
    with _OPEN_LOCK:
        databases = list(_OPEN.values())
        _OPEN.clear()
    for db in databases:
        db.close()
