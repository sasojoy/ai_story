"""帳號綁定「別人也要讀」的那一半（帳號與客服第 201 批；設計 docs/superpowers/specs/2026-11-08-帳號綁定與客服-design.md 4.1、4.5、第七節）：
Email、手機的正規化與遮罩、加金鑰的雜湊、讀金鑰、開關（on）、綁手機才能用的功能問這裡（phone_ok、phone_subject、被擋的那一句 PHONE_NEEDED；
第 205 批接上九個入口：截殺、掛通緝、玩家單的揭與交、贈物、切磋與論武的發起與答應、市集上架與買、商城買、封測發放）、名號擋不擋（blocked_name）。

純規則：不 import 功能包、不讀時鐘、不寫東西（第 204 批的 session_auth 例外，見下）。只有 phone_ok、phone_subject 讀主資料庫的 accounts、logins 兩張表（經 ctx.world.db），
account_key_for（第 203 批）只讀 logins（第 204 批起就是 AccountStore.login_key，併成一份）。
第 204 批：這次登入的方式與時間（record_session、record_reauth、session_auth、staff_session_ok）讀寫旁檔 <db>-identity.sqlite 的
session_auth 一張表（核心讀包的旁檔只碰這一張；DDL 在這裡一份、包的 store.py import），時間由呼叫端傳入。
客服名單也在這（第 212 批從 support 包搬來：商城的易名帖要問「這個名號是不是客服」；support_staff_name 只讀 accounts、logins，
名單的 .local/support.txt 只讀不寫）。
第 208 批：扣押期（hold_reason：花元寶、贈物、上架市集三個入口在 phone_ok 那一行之後問；只讀旁檔的 bindings_meta、holds、reset_holds，
旁檔不在不建）；「不寫東西」多一個例外 record_admin_reset（admin 包重設密碼成功之後寫 reset_holds 與一則「帳號」紀錄）。
那四張表的 DDL 也在這裡一份（identity 包的 store.py import）。
第 209 批：寄通知的口（set_notifier／notify）：identity 包掛路由時登記寄送函式，admin 包重設密碼之後經 notify 寄 NOTICE_ADMIN_RESET
（admin 包不能 import identity 包）；這裡只轉手、不碰網路。
金鑰在 .local/identity.json（不進版控）：讀不到、格式不對都當功能關著（on 回假）。
核心本體（tianxia/core/ 底下的檔），不進 MODULES。identity 包、server.py 的 name_taken、商城包的易名帖讀它。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import threading
import unicodedata
from pathlib import Path

from ..accounts import AccountStore, SessionStore, normalize
from ..characters import name_key
from ..database import default_path
from .name_base import STAFF_NAMES

_REPO = Path(__file__).resolve().parent.parent.parent
KEY_FILE = _REPO / ".local" / "identity.json"  # {"key": "<至少 16 字>"}；不進版控
KEY_MIN = 16
ID_PREFIX = "id:"  # 沒有密碼的帳號的鍵（accounts.id）；名號不准以它開頭

_PHONE_JUNK = re.compile(r"[\s\-()]")
_TW_LOCAL = re.compile(r"09\d{8}")
_TW_INTL = re.compile(r"\+8869\d{8}")
_GMAIL = frozenset(("gmail.com", "googlemail.com"))


def normalize_phone(text: str | None) -> str | None:
    """台灣手機門號轉成 +8869XXXXXXXX（NFKC、去空白與連字號、括號）；不是台灣手機門號回 None。"""
    raw = _PHONE_JUNK.sub("", unicodedata.normalize("NFKC", text or ""))
    if _TW_LOCAL.fullmatch(raw):
        return "+886" + raw[1:]
    if _TW_INTL.fullmatch(raw):
        return raw
    return None


def normalize_email(text: str | None) -> str | None:
    """Email 小寫；Gmail 去掉點與 + 之後的部分，其他網域去掉 + 之後。不像 Email 回 None。"""
    raw = unicodedata.normalize("NFKC", text or "").strip().lower()
    if raw.count("@") != 1:
        return None
    local, domain = raw.split("@")
    local = local.split("+", 1)[0]
    if domain in _GMAIL:
        local = local.replace(".", "")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith(".") or re.search(r"\s", raw):
        return None
    return f"{local}@{domain}"


def mask_phone(phone: str) -> str:
    """正規化後的門號 → 09*****678（只留開頭兩碼與最後三碼）。"""
    local = "0" + phone[4:] if phone.startswith("+886") else phone
    return local[:2] + "*" * 5 + local[-3:]


def mask_email(email: str) -> str:
    """正規化後的 Email → r*@gmail.com（只留首字與網域；星號不照長度，看不出幾個字）。"""
    local, domain = email.split("@", 1)
    return f"{local[:1]}*@{domain}"


def read_key(path: Path | None = None) -> bytes | None:
    """金鑰；檔案不在、讀不了、不是 {"key": "<至少 16 字>"} 都回 None。"""
    try:
        data = json.loads(Path(path or KEY_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    key = data.get("key") if isinstance(data, dict) else None
    if not isinstance(key, str) or len(key) < KEY_MIN:
        return None
    return key.encode("utf-8")


def subject_hmac(key: bytes, provider: str, value: str) -> str:
    """logins.subject 存的值（email、phone）：HMAC-SHA256(金鑰, provider|正規化後的值) 的 hex。"""
    return hmac.new(key, f"{provider}|{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def on(content) -> bool:
    """開關開著、金鑰讀得到，這一包才算開著。"""
    return bool(content.config.identity.enabled) and read_key() is not None


# 綁手機才能用的功能被擋時的回話與灰鈕的 note（同一句；四包共用，包之間不能互相 import，所以放核心；第 205 批）
PHONE_NEEDED = "要先在設定裡綁定手機，才能這麼做。"  # 待 joy 潤


def _account_phone(ctx, feature_key: str) -> tuple[bool, str | None]:
    """phone_ok 與 phone_subject 共用的判斷（設計 4.5 的順序）：(要不要問, 綁的那一列 phone 的 subject 或 None)。
    identity 關或 phone_gate 關 → 不問；鍵不在 phone_required → 不問；假人（state.player.bot 不是 None）→ 不問；
    其餘查這個名號的帳號：查不到、或帳號沒有 provider='phone' 的列 → (真, None)。只問動手的這一個人（ctx 自己）。"""
    cfg = ctx.content.config.identity
    if not cfg.enabled or not cfg.phone_gate or feature_key not in cfg.phone_required or not on(ctx.content):
        return False, None
    player = ctx.state.player
    if player.bot is not None:
        return False, None
    with ctx.world.db.snapshot() as conn:
        row = conn.execute("SELECT id FROM accounts WHERE character_key = ?", (name_key(player.name),)).fetchone()
        if row is None:
            return True, None
        phone = conn.execute(
            "SELECT subject FROM logins WHERE account_id = ? AND provider = 'phone'", (row["id"],),
        ).fetchone()
    return True, (phone["subject"] if phone is not None else None)


def phone_ok(ctx, feature_key: str) -> bool:
    """這個角色能不能用這個功能（設計 4.5；第 205 批接上九個入口）。identity 關、phone_gate 關、功能不在名單、假人都回真；
    不是假人又查不到帳號回假；其餘看這個帳號有沒有綁手機（logins 有沒有 provider='phone'）。"""
    asked, subject = _account_phone(ctx, feature_key)
    return not asked or subject is not None


def phone_subject(ctx, feature_key: str) -> str | None:
    """綁的那支手機的 logins.subject（加金鑰的雜湊 hex）：只有 phone_ok 走到「有 phone 列」才回，其餘（關著、不在名單、假人、沒綁）一律 None。
    封測發放記「同一支手機一輩子一次」用（第 205 批）。"""
    return _account_phone(ctx, feature_key)[1]


def account_key_for(db, provider: str, subject: str) -> str | None:
    """這個身分（logins 的 provider、subject）綁在哪個帳號；查無回 None。第 204 批併成一份：就是 AccountStore(db).login_key
    （K 波審查：兩份同義；補設密碼的記號列也照它認 id:<n>）。只讀。"""
    return AccountStore(db).login_key(provider, subject)


# ── 這次登入的方式與時間（第 204 批；設計 4.3「這次 session 的登入方式與時間記在旁檔，查不到就當沒驗過」、4.4）──
# 旁檔 <db>-identity.sqlite 的 session_auth 一張表：殼的 _start_session 開著時寫（密碼、LINE、Google、驗證碼四種都記），
# identity 包的近期驗證與 support 包的客服權限讀。DDL 只有這一份（identity 包的 store.py import 它）。時間一律由呼叫端傳入。
SIDE_SUFFIX = "identity"
SESSION_DDL = ("CREATE TABLE IF NOT EXISTS session_auth (token_hash TEXT PRIMARY KEY, method TEXT NOT NULL, at REAL NOT NULL, "
               "verified REAL, verified_by TEXT)")
SESSION_COLUMNS = (("session_auth", "verified", "REAL"), ("session_auth", "verified_by", "TEXT"))  # 第 201～203 批開的旁檔沒有這兩欄
_READY: set[tuple[str, str]] = set()  # (旁檔路徑, 哪一份表) 跑過建表的（K 波審查：每次請求都跑 DDL 與 PRAGMA，新檔併發會 database is locked）
_READY_LOCK = threading.Lock()


def side_file(db_path=None) -> Path:
    """遊戲資料庫旁邊同名多 -identity.sqlite（跟著 TIANXIA_DB，呼叫當下才讀）。"""
    db = Path(db_path) if db_path is not None else default_path()
    return db.with_name(f"{db.stem}-{SIDE_SUFFIX}.sqlite")


def ensure_schema(path: Path, name: str, tables, added=()) -> None:
    """這個旁檔建表、補欄、WAL；同一個路徑同一份表只跑一次（檔案被刪掉了再跑：sb 的 _wipe_db 會刪旁檔）。"""
    key = (str(path), name)
    if key in _READY and Path(path).exists():
        return
    with _READY_LOCK:
        if key in _READY and Path(path).exists():
            return
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, isolation_level=None, timeout=10)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            for sql in tables:
                conn.execute(sql)
            for table, column, kind in added:
                have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                if column not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
        finally:
            conn.close()
        _READY.add(key)


def _session_conn(path: Path | None):
    path = Path(path) if path is not None else side_file()
    ensure_schema(path, "session", (SESSION_DDL,), SESSION_COLUMNS)
    return sqlite3.connect(path, isolation_level=None, timeout=10)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8", "surrogatepass")).hexdigest()  # 同 accounts._token_hash


def record_session(token: str, method: str, at: float, path: Path | None = None) -> None:
    """開一個 session 時記它用哪一種登入（password、line、google、email、phone）與時間；同一個 token 再記一次就蓋過（重驗欄清掉）。"""
    conn = _session_conn(path)
    try:
        conn.execute(
            "INSERT INTO session_auth (token_hash, method, at, verified, verified_by) VALUES (?, ?, ?, NULL, NULL) "
            "ON CONFLICT (token_hash) DO UPDATE SET method = excluded.method, at = excluded.at, verified = NULL, verified_by = NULL",
            (token_digest(token), method, at),
        )
    finally:
        conn.close()


def record_reauth(token: str, by: str, at: float, path: Path | None = None) -> bool:
    """重新驗證過一次：只改 verified、verified_by（method 不變）。這個 session 沒有紀錄回假（查不到就當沒驗過）。"""
    conn = _session_conn(path)
    try:
        return conn.execute(
            "UPDATE session_auth SET verified = ?, verified_by = ? WHERE token_hash = ?", (at, by, token_digest(token)),
        ).rowcount == 1
    finally:
        conn.close()


def session_auth(token: str | None, path: Path | None = None) -> dict | None:
    """{method, at, verified, verified_by}；沒帶 token、旁檔沒有這一筆回 None。"""
    if not token:
        return None
    path = Path(path) if path is not None else side_file()
    if not path.exists():
        return None
    conn = _session_conn(path)
    try:
        row = conn.execute(
            "SELECT method, at, verified, verified_by FROM session_auth WHERE token_hash = ?", (token_digest(token),),
        ).fetchone()
    finally:
        conn.close()
    return None if row is None else {"method": row[0], "at": row[1], "verified": row[2], "verified_by": row[3]}


def last_checked(auth: dict | None) -> float | None:
    """這個 session 最後一次證明「是本人」的時間：登入那一下或重驗那一下，取晚的；沒有紀錄回 None。"""
    if auth is None:
        return None
    return max(auth["at"], auth["verified"] or 0.0)


def staff_session_ok(db, content, token: str | None, now: float) -> bool:
    """客服權限要的 session（設計 4.4、6.2）：開著時這次是密碼登入、而且 staff_hours 內登入或重驗過；
    關著時（session 都是密碼登入）看 session 建立的時間在 staff_hours 內。查不到一律回假。"""
    hours = content.config.identity.staff_hours * 3600
    if on(content):
        auth = session_auth(token)
        return auth is not None and auth["method"] == "password" and now - last_checked(auth) <= hours
    created = SessionStore(db, clock=lambda: now).created_at(token)
    return created is not None and now - created <= hours


def admin_session_ok(content, token: str | None, clock) -> bool:
    """管理者權限要的 session（設計 4.4 最後一條；第 207 批）：關著一律回真（管理者行為位元組一樣：不走 staff_session_ok 關著那一支，
    那一支看 session 建立的時間，會讓關著時登入超過 staff_hours 的管理者掉權限；也不碰旁檔）；開著時同 staff_session_ok 開著那一支：
    這次是密碼登入、而且 staff_hours 內登入或重驗過，查不到回假。clock 是呼叫端給的「現在」（零參數函式）：開著才叫，關著不讀時鐘（same_behavior 的假時鐘每讀一次走一格）。名號是不是管理者照舊由 Game.is_admin 判，殼先問它、再問這一支。"""
    if not on(content):
        return True
    return staff_session_ok(None, content, token, clock())  # 開著那一支不讀主資料庫


def listed(content, login: str | None = None, character: str | None = None, account_id: int | None = None) -> bool:
    """名單上的帳號（第 207 批；密碼至少 12 字那一條問）：名號在管理者名單上（config.admins，已併 .local/admins.txt 與 TIANXIA_ADMINS；
    跟 Game.is_admin 同一個比法）、帳號名照名單上的名號比（不分大小寫：註冊時還沒有角色）、或客服名單（support_staff，不看客服開關）。"""
    admins = content.config.admins
    if character is not None and character in admins:
        return True
    key = normalize(login) if login else ""
    if key and key in {normalize(a) for a in admins}:
        return True
    if account_id is not None:
        return support_staff(content.config, account_id, login or "")
    return bool(key) and not key.isdigit() and key in support_names(content.config)


def blocked_name(name: str | None, content) -> bool:
    """開著時不准拿來當名號的：id: 開頭（跟帳號鍵撞）、客服與官方的字（name_base.STAFF_NAMES）。關著一律回假（行為不變）。"""
    if not on(content):
        return False
    text = (name or "").strip().casefold()
    return text.startswith(ID_PREFIX) or text in {n.casefold() for n in STAFF_NAMES}


# ── 客服名單（帳號與客服第 212 批從 features/support/staff.py 搬來：商城的易名帖也要問，包不能 import 別包）──
# 認帳號，不認名號（設計 6.2）。三個來源合起來：Config.support.staff、.local/support.txt（一行一個，# 開頭是註解；照檔的修改時間重讀）、
# 環境變數 TIANXIA_SUPPORT（逗號分開）。每一筆是 accounts.id 的數字，或登入名（accounts.normalize：不分大小寫）。
SUPPORT_ENV = "TIANXIA_SUPPORT"
SUPPORT_FILE = "support.txt"
# 客服官的金鑰檔（客服自動受理第 216 批；設計第八節，企劃者 2026-11-10「照計畫繼續」）：.local/support.json，核心只讀 bot_token 一鍵
SUPPORT_BOT_FILE = "support.json"
SUPPORT_BOT_TOKEN_MIN = 32  # 少於這麼多字一律當沒設

_support_cache: dict = {"path": None, "mtime": None, "names": frozenset()}  # support/staff.py 的 _cache 是同一個 dict


def support_file() -> Path:
    from tianxia import content as content_module  # noqa: PLC0415  content 在 import 時讀設定檔：放函式裡免循環（測試換 LOCAL_DIR 當下看得到）

    return content_module.LOCAL_DIR / SUPPORT_FILE


def _support_file_names(path: Path) -> frozenset[str]:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return frozenset()
    if _support_cache["path"] == path and _support_cache["mtime"] == mtime:
        return _support_cache["names"]
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return frozenset()
    names = frozenset(normalize(line) for line in lines if line.strip() and not line.strip().startswith("#"))
    _support_cache.update(path=path, mtime=mtime, names=names)
    return names


_support_bot_cache: dict = {"path": None, "mtime": None, "token": None}


def support_bot_file() -> Path:
    from tianxia import content as content_module  # noqa: PLC0415  同 support_file

    return content_module.LOCAL_DIR / SUPPORT_BOT_FILE


def support_bot_token() -> str | None:
    """客服官的 token（第 216 批）：.local/support.json 的 bot_token。沒檔、讀不到、壞 json、不是物件、不是字串、少於 32 字一律 None；
    照檔的修改時間快取（改了不必重開伺服器）。其他鍵不讀（第 217 批的事）。"""
    path = support_bot_file()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    if _support_bot_cache["path"] == path and _support_bot_cache["mtime"] == mtime:
        return _support_bot_cache["token"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        data = None
    token = data.get("bot_token") if isinstance(data, dict) else None
    if not isinstance(token, str) or len(token) < SUPPORT_BOT_TOKEN_MIN:
        token = None
    _support_bot_cache.update(path=path, mtime=mtime, token=token)
    return token


def support_names(config) -> frozenset[str]:
    """名單上每一筆（小寫、去空白）。"""
    listed = {normalize(x) for x in config.support.staff}
    listed |= {normalize(x) for x in os.environ.get(SUPPORT_ENV, "").split(",")}
    listed |= _support_file_names(support_file())
    listed.discard("")
    return frozenset(listed)


def support_staff(config, account_id: int, login: str) -> bool:
    """這個帳號（accounts.id、密碼列的登入名，沒有是空字串）在不在名單上。名單上全是數字的一筆只當 id：
    登入名可以全是數字、註冊又是開放的，不然搶註冊登入名 777 就頂了 id 777 的客服（第 J 波審查）。"""
    listed = support_names(config)
    key = normalize(login) if login else ""
    return str(account_id) in listed or (bool(key) and not key.isdigit() and key in listed)


def support_staff_name(db, config, name: str | None) -> bool:
    """這個名號綁著的帳號是不是客服（商城的易名帖問：客服也不能改名，同管理者）。客服開關關著、名號沒綁帳號（假人、還沒綁的）都回假。
    只讀主資料庫的 accounts、logins。"""
    if not config.support.enabled or not name:
        return False
    with db.snapshot() as conn:
        row = conn.execute(
            "SELECT a.id, l.display FROM accounts a LEFT JOIN logins l ON l.account_id = a.id AND l.provider = 'password' "
            "WHERE a.character_key = ?", (name_key(name),),
        ).fetchone()
    return row is not None and support_staff(config, int(row["id"]), row["display"] or "")


# ── 扣押期（帳號與客服第 208 批；設計 4.3「新綁 72 小時」、4.4「只剩過期一種 7 天」、6.4「管理者重設後 72 小時」）──
# 花元寶（mall_buy）、贈物（gift）、上架市集（looks_market）三個入口緊接在 phone_ok 那一行之後問 hold_reason。
# 資料在旁檔：bindings_meta.bound_at（第 204 批）、holds（第 204 批，只剩過期一種）、reset_holds（第 208 批，管理者重設）。
# 這幾張的 DDL 只有這一份（identity 包的 store.py import；兩邊誰先建表都一樣）。admin 包不能 import identity 包，重設後的扣押經 record_admin_reset 寫。
HOLD_DDL = "CREATE TABLE IF NOT EXISTS holds (account_id INTEGER PRIMARY KEY, until REAL NOT NULL)"
NOTES_DDL = ("CREATE TABLE IF NOT EXISTS account_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER NOT NULL, text TEXT NOT NULL, "
             "at REAL NOT NULL, state INTEGER NOT NULL DEFAULT 0, jtime REAL)")
NOTES_INDEX_DDL = "CREATE INDEX IF NOT EXISTS account_notes_account ON account_notes (account_id, state)"
META_DDL = ("CREATE TABLE IF NOT EXISTS bindings_meta (account_id INTEGER NOT NULL, provider TEXT NOT NULL, subject_hmac TEXT NOT NULL, "
            "verified_at REAL NOT NULL, PRIMARY KEY (account_id, provider))")
META_COLUMNS = (("bindings_meta", "bound_at", "REAL"), ("bindings_meta", "reminded_at", "REAL"))  # 第 201～203 批開的旁檔沒有這兩欄
RESET_HOLD_DDL = "CREATE TABLE IF NOT EXISTS reset_holds (account_id INTEGER PRIMARY KEY, until REAL NOT NULL)"
HOLD_TABLES = (META_DDL, HOLD_DDL, NOTES_DDL, NOTES_INDEX_DDL, RESET_HOLD_DDL)

HOLD_KEYS = ("mall_buy", "gift", "looks_market")
HOLD_NEW = "這個帳號剛綁了新的登入方式，{hours} 小時內不能花元寶、贈物或上架市集。"  # 待 joy 潤
HOLD_STALE = "這個帳號在保護期中（{days} 天），暫時不能花元寶、贈物或上架市集。"  # 待 joy 潤
HOLD_RESET = "管理者剛幫這個帳號重設了密碼，{hours} 小時內不能花元寶、贈物或上架市集。"  # 待 joy 潤
NOTE_ADMIN_RESET = ("管理者幫這個帳號重設了密碼，{hours} 小時內不能花元寶、贈物、上架市集或綁定新的登入方式。"
                    "不是你要求的話，請馬上寫信給客服。")  # 待 joy 潤（「帳號」紀錄；admin 包經這裡拿）


def _hold_conn(path: Path | None, create: bool):
    """扣押那幾張表的連線；create 假時旁檔不在就回 None（不建檔：貨架每畫一次都問）。"""
    path = Path(path) if path is not None else side_file()
    if not create and not path.exists():
        return None
    ensure_schema(path, "hold", HOLD_TABLES, META_COLUMNS)
    return sqlite3.connect(path, isolation_level=None, timeout=10)


def _until(conn, table: str, account_id: int) -> float | None:
    row = conn.execute(f"SELECT until FROM {table} WHERE account_id = ?", (account_id,)).fetchone()  # 表名只有本檔兩個字面
    return None if row is None else row[0]


def hold_reason(ctx, key: str, path: Path | None = None) -> str | None:
    """這個角色此刻被扣押、不能做 key 這件事時回那一句，不然 None（只讀）。identity 關、key 不在 HOLD_KEYS、假人、名號沒綁帳號、
    旁檔不在都回 None（假人與沒帳號同一個樣子；扣押是帳號的狀態，沒帳號不擋，跟 phone_ok 不同）。依序：管理者重設（reset_holds）、
    只剩過期一種（holds）、任一種新綁不滿 new_binding_hours（bindings_meta.bound_at；NULL 不算）。現在時間是 ctx.now（Game.sync 給的現實秒）。"""
    if not on(ctx.content) or key not in HOLD_KEYS:
        return None
    player = ctx.state.player
    if player.bot is not None:
        return None
    with ctx.world.db.snapshot() as conn:
        row = conn.execute("SELECT id FROM accounts WHERE character_key = ?", (name_key(player.name),)).fetchone()
    now = ctx.now
    if row is None or not now:
        return None
    side = _hold_conn(path, create=False)
    if side is None:
        return None
    cfg = ctx.content.config.identity
    account_id = row["id"]
    try:
        reset = _until(side, "reset_holds", account_id)
        stale = _until(side, "holds", account_id)
        bound = side.execute(
            "SELECT MAX(bound_at) FROM bindings_meta WHERE account_id = ? AND bound_at IS NOT NULL", (account_id,),
        ).fetchone()[0]
    finally:
        side.close()
    if reset is not None and now < reset:
        return HOLD_RESET.format(hours=cfg.reset_hold_hours)
    if stale is not None and now < stale:
        return HOLD_STALE.format(days=cfg.stale_hold_days)
    if bound is not None and now - bound < cfg.new_binding_hours * 3600:
        return HOLD_NEW.format(hours=cfg.new_binding_hours)
    return None


def record_admin_reset(account_id: int, at: float, hours: int, text: str, path: Path | None = None) -> None:
    """管理者重設密碼成功之後（admin 包叫；設計 6.4）：一筆交易寫 reset_holds（取晚的）與一則「帳號」紀錄（account_notes，
    之後由 identity 包的 notes.journal_notes 照兩段式寫進存檔）。時間由呼叫端傳入。"""
    conn = _hold_conn(path, create=True)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO reset_holds (account_id, until) VALUES (?, ?) "
                "ON CONFLICT (account_id) DO UPDATE SET until = MAX(until, excluded.until)",
                (account_id, at + hours * 3600),
            )
            conn.execute("INSERT INTO account_notes (account_id, text, at) VALUES (?, ?, ?)", (account_id, text, at))
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    finally:
        conn.close()


NOTICE_ADMIN_RESET = "管理者幫這個帳號重設了密碼。不是你要求的話，請馬上寫信給客服。"  # 待 joy 潤（第 209 批：寄給這個帳號綁著的 Email、手機）
_NOTIFIER = None  # 第 209 批：identity 包在 router(shell) 登記的寄送函式 (account_id, text) -> 寄出幾則；admin 包不能 import identity 包，經這裡寄


def set_notifier(fn) -> None:
    """identity 包登記寄送函式（殼掛路由那一下）；None 拿掉。"""
    global _NOTIFIER
    _NOTIFIER = fn


def notify(account_id: int, text: str) -> int:
    """寄一則通知給這個帳號綁著的 Email、手機（admin 包重設密碼之後叫）；沒登記（identity 包沒掛）回 0。寄送失敗、沒有金鑰都是 0 則，不丟例外。"""
    if _NOTIFIER is None:
        return 0
    return _NOTIFIER(account_id, text)


def reset_held(account_id: int, now: float, path: Path | None = None) -> bool:
    """管理者重設之後的扣押還在不在（identity 包擋綁新方式用）；旁檔不在回假、不建檔。"""
    conn = _hold_conn(path, create=False)
    if conn is None:
        return False
    try:
        until = _until(conn, "reset_holds", account_id)
    finally:
        conn.close()
    return until is not None and now < until
