"""綁定、解綁、補設與忘記密碼、門號回收的純規則與玩家看的字（帳號與客服第 204 批；設計 4.3、4.4、6.4）。

不讀時鐘、不讀檔：現在時間、設定（Config.identity）、旁檔讀出來的列都由 routes 傳進來。
- 近期驗證（recent）：這次 session 登入或重驗之後 recent_seconds 內；session 沒有紀錄當沒驗過。
- 新綁（is_new）：bound_at 有值而且不滿 new_binding_hours（bound_at 是 NULL＝開帳號那一種或舊資料，不算新綁）。
- 30 天（rebind_wait）：同一個身分從別的帳號解綁或刪帳號不滿 rebind_days。
- 門號回收（stale）：Email、手機的 verified_at 超過 fresh_days（沒有那一列當新鮮）。
- 扣押（held）：只剩過期那一種登入的帳號 stale_hold_days 內不能設密碼、解綁。
新寫給玩家看的字每一句都待 joy 潤。
"""
from __future__ import annotations

from tianxia.core import identity_base

HOUR = 3600
DAY = 86400
JOURNAL_TITLE = "帳號"  # 待 joy 潤（遊戲紀錄的標題）
JOURNAL_TAG = "identity"
KIND_NAMES = {"password": "密碼", "line": "LINE", "google": "Google", "email": "Email", "phone": "手機"}  # 待 joy 潤
ORDER = ("password", "line", "google", "email", "phone")
WAYS = ("line", "google", "email", "phone")  # 綁得了的四種（密碼走補設）
MARKER = "id"  # 補設密碼的帳號在 logins 多一列 provider='id'（鍵留在 id:<n>），不算一種登入方式

# ── 回話（每一句都待 joy 潤）──
NEED_RECENT = "為了安全，請先重新驗證一次（打密碼，或收一次驗證碼）。"  # 待 joy 潤
SWITCH_ASK = "你已經登入了。要登出現在這個帳號，換成另一個嗎？"  # 待 joy 潤
BOUND_ELSEWHERE = "這個已綁定其他帳號。"  # 待 joy 潤
ALREADY_KIND = "這個帳號已經綁了這一種，要換請先解綁。"  # 待 joy 潤
REBIND_WAIT = "這個剛從別的帳號解綁，{days} 天內不能再拿來綁定或開新帳號。"  # 待 joy 潤
KEEP_ONE = "至少要留一種登入方式。"  # 待 joy 潤
KEEP_PASSWORD = "密碼不能解綁。"  # 待 joy 潤
NEW_BINDING = "剛綁上去的方式 {hours} 小時內不能拿來做這件事，請改用其他方式重新驗證。"  # 待 joy 潤
ON_HOLD = "這個帳號在保護期中（{days} 天），暫時不能設密碼或解綁。"  # 待 joy 潤
STALE_USE_OTHER = "這個號碼太久沒驗證了，請先用這個帳號的其他方式登入；這不是你的帳號的話，按「這不是我的帳號」。"  # 待 joy 潤
NOT_MINE_DONE = "已經從原本的帳號拿掉，接著建立你自己的角色。"  # 待 joy 潤
RESET_EXPIRED = "要重設密碼，請先用綁定的方式重新登入，登入後 {minutes} 分鐘內有效。"  # 待 joy 潤
PASSWORD_SET = "密碼設好了，之後也可以用帳號密碼登入。"  # 待 joy 潤
PASSWORD_RESET = "密碼已更新，其他裝置都登出了。"  # 待 joy 潤
HAS_PASSWORD = "這個帳號已經有密碼了，要改請用「修改密碼」。"  # 待 joy 潤
BOUND = "綁好了。"  # 待 joy 潤
REAUTH_OK = "驗證好了，接下來 {minutes} 分鐘內可以改綁定與密碼。"  # 待 joy 潤
REAUTH_WAYS = "這個帳號沒有密碼，請用下面其中一種重新驗證。"  # 待 joy 潤
UNBOUND = "已解綁。"  # 待 joy 潤
NO_SUCH_WAY = "這個帳號沒有綁這一種。"  # 待 joy 潤
RESET_NO_BIND = "管理者剛幫這個帳號重設了密碼，{hours} 小時內不能綁定新的登入方式。"  # 待 joy 潤（第 208 批；設計 6.4）

# ── 「帳號」紀錄（每一句都待 joy 潤）──
NOTE_BOUND = "這個帳號綁定了{kind}。不是你做的話，請馬上寫信給客服。"  # 待 joy 潤
NOTE_UNBOUND = "這個帳號解綁了{kind}。不是你做的話，請馬上寫信給客服。"  # 待 joy 潤
NOTE_PASSWORD_SET = "這個帳號補設了密碼（帳號名 {login}）。不是你做的話，請馬上寫信給客服。"  # 待 joy 潤
NOTE_PASSWORD_RESET = "這個帳號用{kind}登入後重設了密碼，其他裝置都登出了。不是你做的話，請馬上寫信給客服。"  # 待 joy 潤
NOTE_ADMIN_UNBOUND = "管理者幫這個帳號解綁了{kind}。"  # 待 joy 潤
NOTE_REMIND = "你綁的{kind}已經很久沒驗證了，還是你的嗎？到設定的「帳號綁定」重新驗一次就好，不驗也不影響遊戲。"  # 待 joy 潤
NOTE_RELEASED = "有人驗過這個帳號綁的{kind}，說那不是你的帳號：已經從這個帳號拿掉。"  # 待 joy 潤


def kind_name(provider: str) -> str:
    return KIND_NAMES.get(provider, provider)


def recent(auth: dict | None, now: float, cfg) -> bool:
    """近期驗證：登入或重驗之後 recent_seconds 內。session 沒有紀錄（查不到）當沒驗過。"""
    last = identity_base.last_checked(auth)
    return last is not None and now - last <= cfg.recent_seconds


def checked_by(auth: dict | None) -> str | None:
    """這次 session 最近一次是拿哪一種證明是本人的（重驗過看重驗那一種，沒有看登入那一種）。"""
    if auth is None:
        return None
    return auth.get("verified_by") or auth["method"]


def is_new(row: dict | None, now: float, cfg) -> bool:
    """新綁（不滿 new_binding_hours）；沒有 bindings_meta、bound_at 是 NULL 都不算新綁。"""
    return row is not None and row.get("bound_at") is not None and now - row["bound_at"] < cfg.new_binding_hours * HOUR


def rebind_wait(unbound_at: float | None, now: float, cfg) -> bool:
    return unbound_at is not None and now - unbound_at < cfg.rebind_days * DAY


def stale(row: dict | None, now: float, cfg) -> bool:
    """門號回收：verified_at 超過 fresh_days；沒有那一列當新鮮。"""
    return row is not None and row.get("verified_at") is not None and now - row["verified_at"] > cfg.fresh_days * DAY


def remind_due(row: dict | None, now: float, cfg) -> bool:
    """該不該提醒一次（用密碼或第三方的玩家）：那一種過期了，而且上次提醒也超過 fresh_days（沒提醒過算該提醒）。"""
    if not stale(row, now, cfg):
        return False
    last = row.get("reminded_at")
    return last is None or now - last > cfg.fresh_days * DAY


def held(until: float | None, now: float) -> bool:
    return until is not None and now < until


def kinds_of(providers) -> list[str]:
    """這個帳號的登入方式（照 ORDER 排；補設密碼的記號列不算）。"""
    have = [p for p in providers if p != MARKER]
    return sorted(have, key=lambda p: (ORDER.index(p) if p in ORDER else len(ORDER), p))


def can_remove(providers, provider: str) -> bool:
    """解綁之後至少還留一種（密碼算一種）。"""
    left = [p for p in kinds_of(providers) if p != provider]
    return provider in providers and len(left) >= 1


def subject_hash(key: bytes, provider: str, subject: str) -> str:
    """解綁、30 天比的雜湊：Email、手機的 logins.subject 本來就是加金鑰的雜湊；LINE、Google 的是對方給的 sub，這裡再算一次。"""
    if provider in ("email", "phone"):
        return subject
    return identity_base.subject_hmac(key, provider, subject)
