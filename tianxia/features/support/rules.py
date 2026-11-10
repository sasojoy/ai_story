"""客服單的純規則（帳號與客服第 211 批；設計 6.1、6.2）：類別白名單、長度、沒結的單與一天的上限、狀態轉換、回覆的去向；
第 212 批加查帳號（設計 6.3）的種類、輸入檢查、正規化與紀錄裡存的遮好的字、這一小時、綁定與帳本的字。
不讀時鐘（now 一律由 routes.py 傳進來）、不碰檔案；旁檔的讀寫在 store.py，在同一筆交易裡叫這裡的判斷。"""
from __future__ import annotations

from tianxia.accounts import normalize
from tianxia.core import identity_base

DAY_SECONDS = 86400.0

# 類別（白名單，順序就是畫面上的順序）：id → 顯示的字
CATEGORIES: dict[str, str] = {
    "account": "帳號",  # 待 joy 潤
    "mall": "商城",  # 待 joy 潤
    "game": "遊戲問題",  # 待 joy 潤
    "other": "其他",  # 待 joy 潤
}

# 狀態：open 處理中（等客服）／answered 已回覆（等玩家）／closed 已結
OPEN, ANSWERED, CLOSED = "open", "answered", "closed"
STATUSES = (OPEN, ANSWERED, CLOSED)

# 客服回完之後：等玩家／結單／請管理者處理（內部註記，玩家看不到）
THEN = ("wait", "close", "admin")

# 拒絕的話（對每一個人同一句，不看是誰、不看名號）
BAD_CATEGORY = "沒有這一種類別。"  # 待 joy 潤
EMPTY = "內容是空的。"  # 待 joy 潤
TOO_LONG = "太長了：一則最多 {n} 個字。"  # 待 joy 潤
TOO_MANY_OPEN = "已經有 {n} 張還沒結的單，等客服回覆或結單之後再送。"  # 待 joy 潤
TOO_MANY_TODAY = "一天最多送 {n} 張單，明天再送。"  # 待 joy 潤
CLOSED_ALREADY = "這張單已經結了。"  # 待 joy 潤
NOT_FOUND = "找不到這張單。"  # 待 joy 潤
BAD_THEN = "不知道回完要怎麼辦。"  # 待 joy 潤

# 「客服」紀錄（on_own_turn 寫進江湖紀錄；標題就是設計 6.6 的「客服」）
JOURNAL_TITLE = "客服"  # 待 joy 潤
JOURNAL_TAG = "回覆了你的單"  # 待 joy 潤
JOURNAL_LINE = "客服回覆了你的第 {id} 號單，到「設定 › 客服」看。"  # 待 joy 潤

# ── 客服官（客服自動受理第 216 批；設計 5.2～5.4）──
SYSTEM_ACCOUNT = 0  # 系統回覆（自動結單那一則）記在這個帳號 id 上（accounts.id 從 1 起，不會撞）
AUTO_CLOSED = "{days} 天沒再回，單自動結了。"  # 待 joy 潤
HUMAN_ASKED = "已請真人處理"  # 待 joy 潤
RELAY_NOTE = "轉達自 {who}"  # 待 joy 潤


# ── 查帳號（第 212 批；設計 6.3）：只收完整帳號、Email、手機，不收名號、不做模糊搜尋 ──
HOUR_SECONDS = 3600.0
LOOKUP_KINDS = ("login", "email", "phone")
LOGIN_SHOWN_MAX = 64  # 紀錄裡帳號那一格最多存幾個字（亂打一長串不會撐大旁檔）

LOOKUP_NONE = "查無此帳號。"  # 待 joy 潤
LOOKUP_LIMIT = "這一小時查帳號的次數用完了（每小時 {n} 次），晚點再查。"  # 待 joy 潤
LOOKUP_EMPTY = "請輸入要查的帳號、Email 或手機。"  # 待 joy 潤
LOOKUP_BAD_EMAIL = "Email 的寫法不對。"  # 待 joy 潤
LOOKUP_BAD_PHONE = "只收台灣手機門號（09 開頭十碼）。"  # 待 joy 潤
LOOKUP_BAD_KIND = "只能照帳號、Email 或手機查。"  # 待 joy 潤

# ── 截圖（客服自動受理第 215 批；設計 5.1）：只看檔頭認種類（不信副檔名、不信 Content-Type、不驗整張圖），種類就是存檔的副檔名 ──
CONTENT_TYPES: dict[str, str] = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
FILE_TOO_BIG = "圖太大了：一張最多 {mb} MB。"  # 待 joy 潤
FILE_NOT_IMAGE = "只收 PNG、JPEG、WebP 的圖。"  # 待 joy 潤
FILES_FULL = "一張單最多附 {n} 張圖。"  # 待 joy 潤


def image_kind(head: bytes) -> str | None:
    """前 12 位元組認種類：PNG 89 50 4E 47 0D 0A 1A 0A、JPEG FF D8 FF、WebP RIFF＋4 位元組＋WEBP；其他回 None。"""
    head = bytes(head[:12])
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if len(head) == 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None

# 帳號卡「綁了」那一格（logins.provider → 字；先後就是畫面上的先後）
PROVIDER_NAMES: dict[str, str] = {
    "password": "密碼",  # 待 joy 潤
    "line": "LINE",  # 待 joy 潤
    "google": "Google",  # 待 joy 潤
    "email": "Email",  # 待 joy 潤
    "phone": "手機",  # 待 joy 潤
}
SHOWN_PROVIDERS = ("email", "phone")  # 只有這兩種帶遮好的顯示字（LINE、Google 的暱稱不給客服看）

# 帳本那一列的原因（同商城 mall/rules.py 的 REASONS；包不能 import 別包，自己一份）
LEDGER_REASONS: dict[str, str] = {
    "grant": "封測發放",  # 待 joy 潤
    "buy": "購買",  # 待 joy 潤
    "refund": "退款",  # 待 joy 潤
    "reissue": "補發",  # 待 joy 潤
    "revoke": "扣回",  # 待 joy 潤
    "topup": "儲值",  # 待 joy 潤
}


def lookup_problem(kind: str, text: str) -> str | None:
    """查帳號的輸入：種類不在白名單、空的、Email／手機寫法不對都不收（不算次數、不留紀錄）。沒問題回 None。"""
    if kind not in LOOKUP_KINDS:
        return LOOKUP_BAD_KIND
    if not (text or "").strip():
        return LOOKUP_EMPTY
    if kind == "email" and identity_base.normalize_email(text) is None:
        return LOOKUP_BAD_EMAIL
    if kind == "phone" and identity_base.normalize_phone(text) is None:
        return LOOKUP_BAD_PHONE
    return None


def lookup_value(kind: str, text: str) -> str:
    """正規化後拿去比對的值（先過 lookup_problem）：帳號照 accounts.normalize，Email、手機照 identity_base。"""
    if kind == "email":
        return identity_base.normalize_email(text) or ""
    if kind == "phone":
        return identity_base.normalize_phone(text) or ""
    return normalize(text)


def lookup_shown(kind: str, value: str) -> str:
    """紀錄裡存的字：帳號存正規化後的（截到 LOGIN_SHOWN_MAX），Email、手機只存遮好的（不存明碼也不存雜湊）。"""
    if kind == "email":
        return identity_base.mask_email(value)
    if kind == "phone":
        return identity_base.mask_phone(value)
    return value[:LOGIN_SHOWN_MAX]


def hour_start(now: float) -> float:
    """「這一小時」從 now 往回推 3600 秒。"""
    return now - HOUR_SECONDS


def body_problem(body: str, body_max: int) -> str | None:
    """一則的內容：去頭尾空白之後不能是空的、不能超過 body_max 個字。回拒絕的話，沒問題回 None。"""
    text = (body or "").strip()
    if not text:
        return EMPTY
    if len(text) > body_max:
        return TOO_LONG.format(n=body_max)
    return None


def ticket_problem(category: str, body: str, body_max: int) -> str | None:
    if category not in CATEGORIES:
        return BAD_CATEGORY
    return body_problem(body, body_max)


def quota_problem(open_count: int, recent_count: int, open_max: int, daily_max: int) -> str | None:
    """送一張新單之前（store 在同一筆交易裡數好傳進來）：沒結的單到上限、24 小時內送的到上限都不收。"""
    if open_count >= open_max:
        return TOO_MANY_OPEN.format(n=open_max)
    if recent_count >= daily_max:
        return TOO_MANY_TODAY.format(n=daily_max)
    return None


def day_start(now: float) -> float:
    """「一天」從 now 往回推 24 小時（不照日曆的換日：伺服器時區跟玩家不一定一樣）。"""
    return now - DAY_SECONDS


def owns(ticket: dict, account_id: int, account_created: float) -> bool:
    """這張單是不是這個帳號的：帳號 id 與建帳號的時間都要對（主檔退回舊時間點之後 id 會被新帳號拿到，設計第七節 backup 那一列）。"""
    return ticket["account_id"] == account_id and ticket["account_created"] == account_created


def after_player_reply(status: str) -> str:
    """玩家再回一句：沒結的單回到「處理中」；結了的不准回（呼叫端先擋）。"""
    return OPEN


def after_staff(then: str, status: str) -> str:
    """客服回完的狀態：等玩家 → 已回覆；結單 → 已結；請管理者處理（內部註記）→ 狀態不變。"""
    if then == "wait":
        return ANSWERED
    if then == "close":
        return CLOSED
    return status


def visible_to_player(reply: dict) -> bool:
    """內部註記（請管理者處理）玩家看不到。"""
    return not reply["internal"]


def reply_auto(reply: dict, bot_id: int | None, relayed: frozenset[int]) -> bool:
    """這一則是不是自動回覆（第 216 批）：系統回覆（SYSTEM_ACCOUNT）一律是；客服官的帳號回的、又不是轉達真人的話（relayed 是那幾則的 id）才是。
    玩家的、真人客服的都不是；沒設客服官（bot_id None）只剩系統回覆。"""
    if not reply["staff"]:
        return False
    if reply["by_account_id"] == SYSTEM_ACCOUNT:
        return True
    return bot_id is not None and reply["by_account_id"] == bot_id and reply["id"] not in relayed


def after_human(status: str) -> str:
    """玩家按了找真人：已回覆（等玩家）回到處理中；處理中照舊（結了的呼叫端先擋）。"""
    return OPEN if status == ANSWERED else status


def last_by(replies: list[dict], bot_id: int | None, relayed: frozenset[int]) -> str | None:
    """最後一則玩家看得到的回覆是誰寫的（客服頁的清單與單用）：system 系統／desk 自動回覆／staff 真人客服／player 玩家；沒有回覆 None。
    內部註記不算。值裡不寫 bot 這個字（任何回應都不透露）。"""
    shown = [r for r in replies if not r["internal"]]
    if not shown:
        return None
    r = shown[-1]
    if not r["staff"]:
        return "player"
    if r["by_account_id"] == SYSTEM_ACCOUNT:
        return "system"
    return "desk" if reply_auto(r, bot_id, relayed) else "staff"
