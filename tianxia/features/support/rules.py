"""客服單的純規則（帳號與客服第 211 批；設計 6.1、6.2）：類別白名單、長度、沒結的單與一天的上限、狀態轉換、回覆的去向。
不讀時鐘（now 一律由 routes.py 傳進來）、不碰檔案；旁檔的讀寫在 store.py，在同一筆交易裡叫這裡的判斷。"""
from __future__ import annotations

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
