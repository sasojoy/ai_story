"""Email、手機驗證碼的純規則（帳號與客服第 203 批；設計 4.2 驗證碼、4.6 防刷、第五節個資告知）。

不讀時鐘、不讀環境：現在時間、金鑰、旁檔、寄送介面、「這個身分有沒有綁」都由 routes 傳進來。
- 來源：IPv4 原樣一格；IPv6 以 /64 一格、再加 /48 一格（ip_buckets）。
- 計數一律走旁檔的 check_all_and_record（一號 60 秒、每日共用格或信任瀏覽器格、來源一小時、全服池的時與天，同一筆交易全記或全不記）。
- 只存 HMAC：身分是 identity_base.subject_hmac，碼是 HMAC(金鑰, challenge_id|碼)；顯示字是遮過的。
- 對外同一句：寄出、額度滿了都回 SENT（同一份位元組，不透露有沒有帳號）；只有寄送服務本身出錯才回 CANNOT_SEND。
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
import unicodedata

from tianxia.core import identity_base

# ── 玩家看的字（每一句都待 joy 潤）────────────────────
SENT = "驗證碼已寄出，收不到請稍後再試。"  # 待 joy 潤
CANNOT_SEND = "現在無法寄送，請稍後再試。"  # 待 joy 潤
BAD_PHONE = "只收台灣手機門號（09 開頭十碼）。"  # 待 joy 潤
BAD_EMAIL = "這看起來不是 Email。"  # 待 joy 潤
NEED_HUMAN = "請先完成真人驗證，再按一次。"  # 待 joy 潤
BAD_CODE = "驗證碼不對或已過期，請重新取得。"  # 待 joy 潤
NOT_THIS = "這不是這個帳號綁的號碼，請用這個帳號綁的那一個重新驗證。"  # 待 joy 潤（第 204 批：重驗打了別的號碼）
NOTICE = "這個 Email 或手機只用來寄驗證碼與帳號通知；我們只存加密過的雜湊與遮掉一半的顯示字，不另作他用。詳見隱私權說明。"  # 待 joy 潤
SMS_LOGIN = "【天下大勢】登入驗證碼 {code}，{minutes} 分鐘內有效。客服不會跟你要驗證碼，請勿告訴任何人。"  # 待 joy 潤
SMS_BIND = "【天下大勢】有人要把這支手機綁到遊戲帳號，驗證碼 {code}，{minutes} 分鐘內有效。不是你就不用理會。客服不會跟你要驗證碼。"  # 待 joy 潤
MAIL_SUBJECT = "天下大勢驗證碼"  # 待 joy 潤
MAIL_LOGIN = "你的登入驗證碼是 {code}，{minutes} 分鐘內有效。\n客服不會跟你要驗證碼，請勿告訴任何人。不是你要登入就不用理會這封信。"  # 待 joy 潤
MAIL_BIND = "有人要把這個 Email 綁到遊戲帳號，驗證碼是 {code}，{minutes} 分鐘內有效。\n不是你就不用理會這封信。客服不會跟你要驗證碼。"  # 待 joy 潤

CHANNELS = ("phone", "email")
HOUR = 3600
DAY = 86400
PURPOSE = "login"  # 預設用途（第 203 批只有它）
PURPOSES = ("login", "bind", "reauth")  # 第 204 批：bind 用綁定那一份字、bind 池；reauth（沒密碼的帳號重驗一次）用登入那一份字、登入池


def normalize(channel: str, to: str | None) -> tuple[str, str] | None:
    """(正規化後的值, 遮過的顯示字)；不收的回 None。"""
    if channel == "phone":
        value = identity_base.normalize_phone(to)
        return None if value is None else (value, identity_base.mask_phone(value))
    value = identity_base.normalize_email(to)
    return None if value is None else (value, identity_base.mask_email(value))


def ip_buckets(ip: str | None) -> list[str]:
    """來源的格：IPv4（含 IPv4-mapped）一格；IPv6 回 /64、/48 兩格；讀不懂的照原字一格。"""
    raw = (ip or "").strip()
    try:
        addr = ipaddress.ip_address(raw)
    except ValueError:
        return [f"raw:{raw}"]
    if addr.version == 6 and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if addr.version == 4:
        return [f"v4:{addr}"]
    return [f"v6/{bits}:{ipaddress.ip_network(f'{addr}/{bits}', strict=False).network_address}" for bits in (64, 48)]


def pool_of(purpose: str, bound: bool) -> str:
    """全服分池：已綁的登入與找回 login；綁定 bind（第 204 批）；沒綁的新號碼 anon。"""
    if purpose == "bind":
        return "bind"
    return "login" if bound else "anon"


def buckets_for(cfg, channel: str, subject: str, pool: str, ips: list[str], dev_hash: str | None, trusted: bool):
    """這一次寄送要記的每一格：(桶名, window 秒, limit)。一號 60 秒排最前面；每日只記一格（信任的瀏覽器記自己那一格）。"""
    caps = cfg.sms_caps if channel == "phone" else cfg.mail_caps
    day_cap, hour_cap = caps[pool]
    out = [(f"resend:{channel}:{subject}", cfg.resend_seconds, 1)]
    if trusted and dev_hash:
        out.append((f"day:{channel}:{subject}:dev:{dev_hash}", DAY, cfg.daily_trusted))
    else:
        out.append((f"day:{channel}:{subject}:shared", DAY, cfg.daily_shared))
    out += [(f"src:{b}", HOUR, cfg.source_hour) for b in ips]
    out += [(f"pool:{channel}:{pool}:hour", HOUR, hour_cap), (f"pool:{channel}:{pool}:day", DAY, day_cap)]
    return out


def new_code(randbelow=secrets.randbelow) -> str:
    return f"{randbelow(1_000_000):06d}"


def code_hmac(key: bytes, challenge_id: str, code: str) -> str:
    return hmac.new(key, f"{challenge_id}|{code}".encode("utf-8"), hashlib.sha256).hexdigest()


def text_for(channel: str, purpose: str, code: str, ttl: int = 300) -> tuple[str | None, str]:
    """(信的主旨或 None, 內文)：簡訊與信分用途。"""
    minutes = max(1, ttl // 60)
    if channel == "phone":
        return None, (SMS_BIND if purpose == "bind" else SMS_LOGIN).format(code=code, minutes=minutes)
    return MAIL_SUBJECT, (MAIL_BIND if purpose == "bind" else MAIL_LOGIN).format(code=code, minutes=minutes)


def sent_reply(cfg) -> dict:
    """寄出與額度滿了同一份回應（個資告知短文與隱私權連結一起帶）。"""
    return {"message": SENT, "notice": NOTICE, "privacy": cfg.privacy_url}


def send(*, cfg, key: bytes, store, senders, channel: str, to, token, ip: str, hostname: str | None,
         dev_hash: str | None, is_bound, now: float, make_id=None, make_code=None, purpose: str = PURPOSE,
         account_id: int | None = None, subject_ok=None) -> tuple[int, dict, str | None]:
    """寄一張驗證碼（purpose：login、bind、reauth；第 204 批起 bind、reauth 的單記 account_id）。回 (狀態碼, 回應, 新單的 id 或 None)。
    subject_ok(subject) 給了就在 Turnstile 之後問一次（reauth：要是這個帳號綁的那一個），回假的回 (400, {error: NOT_THIS}, None)。
    正規化 → Turnstile（失敗不碰計數）→ 查有沒有綁（決定池）→ 每一格一起記（滿了回 SENT、不寄、舊單不動）→ 產碼、寄
    （SendFailed 回 CANNOT_SEND，計數不退）→ 開單（同一個身分的舊單作廢）。"""
    from .senders import SendFailed  # noqa: PLC0415  同一包；放這裡讓純規則的 import 不拖 urllib

    norm = normalize(channel, to)
    if norm is None:
        return 400, {"error": BAD_PHONE if channel == "phone" else BAD_EMAIL}, None
    value, display = norm
    if not senders.turnstile.verify(str(token or ""), ip, hostname):
        return 400, {"error": NEED_HUMAN}, None
    subject = identity_base.subject_hmac(key, channel, value)
    if subject_ok is not None and not subject_ok(subject):
        return 400, {"error": NOT_THIS}, None
    pool = pool_of(purpose, bool(is_bound(subject)))
    trusted = bool(dev_hash) and store.is_trusted(dev_hash, subject)
    if store.check_all_and_record(buckets_for(cfg, channel, subject, pool, ip_buckets(ip), dev_hash, trusted), now) is not None:
        return 200, sent_reply(cfg), None
    cid = (make_id or (lambda: secrets.token_urlsafe(24)))()
    code = (make_code or new_code)()
    title, text = text_for(channel, purpose, code, cfg.code_ttl)
    try:
        if channel == "phone":
            senders.sms.send(value, text)
        else:
            senders.mail.send(value, title, text)
    except SendFailed:
        return 400, {"error": CANNOT_SEND}, None
    store.put_challenge(cid, purpose, channel, subject, display, code_hmac(key, cid, code), now + cfg.code_ttl, now,
                        account_id=account_id)
    return 200, sent_reply(cfg), cid


def verify(*, cfg, key: bytes, store, cid: str | None, code, now: float) -> dict | None:
    """對了回那張單（已刪：同一碼不能用第二次）；沒單、過期、錯碼回 None。錯碼算在這張單上，到 code_tries 次刪單。"""
    if not cid:
        return None
    row = store.challenge(cid)
    if row is None or row.get("purpose") not in PURPOSES or not row.get("channel"):
        return None
    if row["expires"] <= now:
        store.drop_challenge(cid)
        return None
    given = unicodedata.normalize("NFKC", str(code or "")).strip()
    if not hmac.compare_digest(code_hmac(key, cid, given), row["code_hmac"]):
        store.bump_tries(cid, cfg.code_tries)
        return None
    if not store.drop_challenge(cid):  # 同時在途的另一個請求先刪了（用過、或錯到作廢）：這一下不算對（K 波修）
        return None
    return row
