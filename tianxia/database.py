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
from collections.abc import Callable, Iterator
from typing import TypeVar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "saves" / "tianxia.db"
ENV_VAR = "TIANXIA_DB"  # 線上版與開發版用不同的資料（線上架構設計 8.1）：設了這個環境變數就開那個檔
T = TypeVar("T")
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

# 第 3 版（悟意境設計 0.2b）：感悟悟出來的意境是私有的（存在角色自己的存檔），全服只記「這一季誰第一個在哪裡、用什麼做法、
# 畫出什麼屬性悟到」——key 是「地點|做法屬性|畫出的屬性」，名字是首悟那人的意境名，寫進江湖史。照季分，換季不刪。
SCHEMA_V3_TABLES: tuple[str, ...] = (
    """CREATE TABLE insight_firsts (
        season INTEGER NOT NULL,
        key TEXT NOT NULL,
        name TEXT NOT NULL,
        creator TEXT,
        place TEXT NOT NULL,
        time REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (season, key)
    )""",
)

# 第 4 版（兵器設計第五節、兵器第二批）：全服的裝備配方。配方鍵的前綴就是欄位（裝備四欄設計 4.7）：這一批只有武器「兵|種類|主料+輔料」；
# 之後防具打造用同一張表、前綴「鎧|主料+輔料」，不必再升版。名字跟功法、改過的名字、意境共用一個名字空間（sqlite_world._name_taken）。照季分，換季不刪。
SCHEMA_V4_TABLES: tuple[str, ...] = (
    """CREATE TABLE gear_recipes (
        season INTEGER NOT NULL,
        key TEXT NOT NULL,
        name TEXT NOT NULL,
        creator TEXT,
        data TEXT NOT NULL,
        PRIMARY KEY (season, key)
    )""",
    "CREATE UNIQUE INDEX gear_recipes_by_name ON gear_recipes (season, name)",
)

# 第 5 版（玩家傳，企劃者 2026-10-12；PM 核准第 5 版）：每個角色每季一篇傳。角色每季重來，行狀（PlayerState.annals）在換季前存進來；
# 傳本身跨季留著，季末寫成之後填 text，公開分享時產生 share_code（不用登入的唯讀網址 /zhuan/<代碼>）。key 是名號的 casefold（同 characters.key）。
SCHEMA_V5_TABLES: tuple[str, ...] = (
    """CREATE TABLE biographies (
        season INTEGER NOT NULL,
        key TEXT NOT NULL,
        name TEXT NOT NULL,
        annals TEXT NOT NULL,
        profile TEXT NOT NULL DEFAULT '{}',
        text TEXT,
        written_by TEXT,
        written_at REAL,
        rewrites INTEGER NOT NULL DEFAULT 0,
        share_code TEXT UNIQUE,
        public INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (season, key)
    )""",
)

# 第 6 版（商城架構設計 4.1、4.4、4.5、4.9；PM 排給商城）：元寶的帳本、購買紀錄、月卡這類有到期的東西。錢包不另存餘額：
# 餘額＝帳的加總（對得起來）。owner 是角色名號的 casefold（同 characters.key、真人的 accounts.character_key；假人沒有帳號也有錢包，
# 見 tianxia/wallet.py）。帳與購買都帶不重複的編號 ref，同一個編號重送不會算兩次（之後接金流的回呼也靠它）。跨季保留、不照季分。
SCHEMA_V6_TABLES: tuple[str, ...] = (
    # 一次購買一列：day 是回體丹換日的那一天（台灣 00:00）、season 是那時的季數（限購照它們數）；data 是發了什麼（退的時候照它收回）
    """CREATE TABLE mall_purchases (
        id INTEGER PRIMARY KEY,
        owner TEXT NOT NULL,
        ref TEXT NOT NULL UNIQUE,
        item TEXT NOT NULL,
        price INTEGER NOT NULL CHECK (price >= 0),
        time REAL NOT NULL,
        day INTEGER NOT NULL,
        season INTEGER NOT NULL,
        data TEXT NOT NULL DEFAULT '{}',
        refunded REAL
    )""",
    "CREATE INDEX mall_purchases_by_owner ON mall_purchases (owner, item, id)",
    # 每一筆進出：原因是封測發放 grant、購買 buy、退款 refund、補發 reissue、扣回 revoke、儲值 topup（留給之後的金流）；admin 是經手的管理者
    """CREATE TABLE mall_ledger (
        id INTEGER PRIMARY KEY,
        owner TEXT NOT NULL,
        time REAL NOT NULL,
        delta INTEGER NOT NULL,
        reason TEXT NOT NULL CHECK (reason IN ('grant', 'buy', 'refund', 'reissue', 'revoke', 'topup')),
        ref TEXT NOT NULL UNIQUE,
        purchase_id INTEGER REFERENCES mall_purchases (id),
        admin TEXT,
        note TEXT NOT NULL DEFAULT ''
    )""",
    "CREATE INDEX mall_ledger_by_owner ON mall_ledger (owner, id)",
    # 跟著帳號的東西：月卡 card（key 是效果，例 pill_cap；start_day～end_day，不含 end_day）、通行證 pass、外觀 look（這一版還沒有）
    """CREATE TABLE mall_entitlements (
        owner TEXT NOT NULL,
        kind TEXT NOT NULL CHECK (kind IN ('card', 'pass', 'look')),
        key TEXT NOT NULL,
        start_day INTEGER,
        end_day INTEGER,
        data TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (owner, kind, key)
    )""",
)

# 第 7 版（減法季批 0，設計稿第十章「真人量表」、整合設計 11.4 的 action_counts）：真人每天按了哪幾顆、哪幾天上線、
# 第一次寫隨口應對、第一次跟人物說話、第一次看「全區」是哪一天。
# 只有伺服器（真人的請求）寫，假人程式不經過伺服器、不記；不露給玩家，只給主機端的 scripts/play_metrics.py 算總數。
# owner 同第 6 版（characters.name_key；一個帳號一個角色）；day 是回體丹換日的那一天（台灣 00:00，Game._pill_day），season 是那時的季數。
SCHEMA_V7_TABLES: tuple[str, ...] = (
    # 一人一季一天一列：那一天有上線（自己的請求）就有一列；buttons 是 {按鈕: 次數}（playlog.button_of 歸類，JSON）
    """CREATE TABLE action_counts (
        owner TEXT NOT NULL,
        season INTEGER NOT NULL,
        day INTEGER NOT NULL,
        buttons TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (owner, season, day)
    )""",
    # 第一次做某件事：free_text 寫隨口應對、figure_talk 跟人物說話、whole_area 看過輿圖的「全區」（輿圖四層那一批才記）；同一季只記第一次
    """CREATE TABLE action_firsts (
        owner TEXT NOT NULL,
        season INTEGER NOT NULL,
        kind TEXT NOT NULL CHECK (kind IN ('free_text', 'figure_talk', 'whole_area')),
        day INTEGER NOT NULL,
        time REAL NOT NULL,
        PRIMARY KEY (owner, season, kind)
    )""",
)

SCHEMA: tuple[str, ...] = (  # 新檔一次建好
    SCHEMA_V1 + SCHEMA_V2_TABLES + SCHEMA_V3_TABLES + SCHEMA_V4_TABLES + SCHEMA_V5_TABLES + SCHEMA_V6_TABLES + SCHEMA_V7_TABLES
)
MIGRATIONS: dict[int, tuple[str, ...]] = {  # 第 n 版 → 第 n+1 版要跑的句子
    1: SCHEMA_V2_TABLES, 2: SCHEMA_V3_TABLES, 3: SCHEMA_V4_TABLES, 4: SCHEMA_V5_TABLES, 5: SCHEMA_V6_TABLES, 6: SCHEMA_V7_TABLES,
}
SCHEMA_VERSION = 7


def default_path() -> Path:
    """預設的資料庫檔：設了環境變數 TIANXIA_DB 就用它，否則 saves/tianxia.db。呼叫當下才讀。"""
    override = os.environ.get(ENV_VAR)
    return Path(override) if override else DEFAULT_PATH


class _ThreadState:
    """一個執行緒在這個資料庫上的連線與交易狀態。放在 threading.local 裡：執行緒結束、local 被釋放時，
    這個物件被回收，登記的 weakref.finalize 就把連線關掉。"""

    __slots__ = ("conn", "depth", "reading", "rewriting", "savepoints", "began", "generation", "epoch", "memo", "notes", "after",
                 "__weakref__")

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.depth = 0  # 寫入交易的巢狀深度，0 表示不在寫入交易裡
        self.savepoints = 0  # 現在開著的 savepoint 數（見 Database.savepoint），拿來給每一個取不同的名字
        self.reading = False  # 是不是在 snapshot() 的最外層
        self.rewriting = False  # 是不是在 rewriting() 的區段裡（整份讀出、改、整份寫回）
        # 這一筆交易（寫入或快照的最外層）的記號（見 Database.unchanged、Database.memo）：開始時連線的 total_changes；
        # epoch 每開一筆、結束一筆、撤回一個 savepoint 就加一（撤回不會讓 total_changes 變小，靠它認出「資料退回去了」）
        self.began: int | None = None
        self.generation = 0  # 開這一筆時 Database.generation 是多少（見 Database.unchanged）
        self.epoch = 0
        self.memo: dict[object, tuple[int, int, object]] = {}
        self.notes: set[object] = set()  # 這一筆交易記下的事（Database.note）
        self.after: list[Callable[[], None]] = []  # 這一筆 COMMIT 之後要做的事（Database.after_commit）


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._local = threading.local()
        # 有人宣告「之前讀進記憶體、記下來的東西不算數了」就加一（bump；例：易名帖改了傳聞的名號）。比它早開的交易讀到的不記
        self.generation = 0
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
        self._opened(state)
        try:
            yield conn
        except BaseException:
            state.depth = 0
            self._closed(state)
            self._rollback(conn)
            raise
        state.depth = 0
        after = state.after
        self._closed(state)
        try:
            conn.execute("COMMIT")
        except BaseException:
            self._rollback(conn)  # COMMIT 失敗時交易還開著：不撤掉，這條連線就永遠握著寫入權
            raise
        for fn in after:
            fn()

    @contextlib.contextmanager
    def savepoint(self) -> Iterator[sqlite3.Connection]:
        """寫入交易裡的一段「可以單獨撤回」的區間（SQLite 的 SAVEPOINT）。transaction() 巢狀只是合進外層、深度加一，
        裡面出錯時外層要不要撤回由外層決定；要「裡面這一段的寫入撤回、外層照常 COMMIT」就用這個：裡面丟例外，
        只把這一段做的寫入撤回，例外照舊丟出去。裡面順利結束就併進外層，外層撤回時一起撤回。可以巢狀。
        只能在寫入交易裡用（不在交易裡、或在 snapshot 裡就丟 RuntimeError）。
        SQLite 已經把整筆交易撤掉了（磁碟滿、I/O 錯誤）時沒有 savepoint 可撤，什麼都不做、不蓋掉本來的錯。"""
        state = self._thread()
        if not state.depth:
            raise RuntimeError("savepoint 只能在寫入交易裡用：先開 transaction()")
        conn = state.conn
        state.savepoints += 1
        name = f"sp{state.savepoints}"
        conn.execute(f"SAVEPOINT {name}")
        try:
            yield conn
        except BaseException:
            state.epoch += 1  # 這一段的寫入撤回了：之前記下的（Database.memo）不算數
            if conn.in_transaction:
                conn.execute(f"ROLLBACK TO {name}")
                conn.execute(f"RELEASE {name}")
            raise
        else:
            conn.execute(f"RELEASE {name}")
        finally:
            state.savepoints -= 1

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
        self._opened(state)
        try:
            yield conn
        finally:
            state.reading = False
            self._closed(state)
            self._rollback(conn)  # 唯讀：一律 ROLLBACK，不 COMMIT

    def _opened(self, state: _ThreadState) -> None:
        state.began = state.conn.total_changes
        state.generation = self.generation
        state.epoch += 1
        state.memo.clear()
        state.notes = set()
        state.after = []

    @staticmethod
    def _closed(state: _ThreadState) -> None:
        state.began = None
        state.epoch += 1
        state.memo.clear()
        state.notes = set()
        state.after = []

    def unchanged(self) -> bool:
        """這個執行緒正在一筆交易（寫入或快照）裡，這一筆到現在還沒寫過任何東西，而且開始之後沒有人 bump：看到的每一列都是
        已經 COMMIT 的，不會因為這一筆撤回而不見，也不是 bump 宣告作廢的舊樣子（sqlite_world 的傳聞快取只收這種時候讀到的）。
        不在交易裡回 False。"""
        state = getattr(self._local, "state", None)
        return (state is not None and state.began is not None and state.conn.total_changes == state.began
                and state.generation == self.generation)

    def bump(self) -> None:
        """宣告「記在這個程式裡、讀自資料庫的東西不算數了」：之後才開的交易讀到的才記（見 unchanged）。"""
        with self._states_lock:
            self.generation += 1

    def note(self, key: object) -> None:
        """在這一筆交易（寫入的最外層）上記一件事，交易結束（COMMIT 或撤回）就忘掉；不在寫入交易裡什麼都不做。"""
        state = getattr(self._local, "state", None)
        if state is not None and state.depth:
            state.notes.add(key)

    def noted(self, key: object) -> bool:
        state = getattr(self._local, "state", None)
        return state is not None and state.began is not None and key in state.notes

    def after_commit(self, fn: Callable[[], None]) -> None:
        """這一筆寫入交易（最外層）COMMIT 成功之後做 fn；撤回就不做。不在寫入交易裡時當場做。"""
        state = getattr(self._local, "state", None)
        if state is None or not state.depth:
            fn()
            return
        state.after.append(fn)

    def memo(self, key: object, make: Callable[[], T]) -> T:
        """同一筆交易裡、中間沒有寫過東西（也沒撤回過 savepoint）時，同一個 key 只算一次 make()，之後回同一個值：
        同一個請求裡反覆讀同一份全服狀態不必一再解析（審查 S-02）。寫過、撤回過、換了一筆交易就重算。
        回的是同一個物件：只給不會改它、也不會把它交出去的讀取用。不在交易裡時每次都算。"""
        state = getattr(self._local, "state", None)
        if state is None or state.began is None:
            return make()
        stamp = (state.epoch, state.conn.total_changes)
        hit = state.memo.get(key)
        if hit is not None and (hit[0], hit[1]) == stamp:
            return hit[2]  # type: ignore[return-value]
        value = make()
        state.memo[key] = (*stamp, value)  # 照算之前的記號記：make() 裡要是寫了東西，下一次就對不上、重算
        return value

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
