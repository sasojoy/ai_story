"""綁定通知用的加密號碼（帳號與客服第 208 批；設計 4.3「每次綁、解綁、設密碼……通知現有的 Email、手機」，企劃者 11/08 選「另存加密的號碼給通知用」）。

- 金鑰：.local/identity.json 的 notify_key（第二把，至少 16 字；同 senders.turnstile_secret 的讀法，路徑 identity_base.KEY_FILE）。讀不到、
  cryptography 沒裝都當沒有：seal 回 None、send_all 不寄回 0（只寫紀錄、不 500）。
- 加密：AESGCM（金鑰＝sha256(notify_key)，nonce 12 位元組放在密文前面）。存進旁檔 contacts 的 aad 是 "<account_id>|<provider>"；
  綁定的單在寄碼那一下先封一次（aad "challenge|<channel>"），綁成功才拆開、照帳號再封一次存進 contacts。
- 跟 HMAC 分開：contacts 只在寄通知那一刻解開，不進任何查詢與比對（認人一律照 logins.subject 的 HMAC）。
- 寄：senders.pick 的 sms／mail（SendFailed 吞掉）；fake_services 開著另印一行給主機看（只寫遮過的號碼，不印明碼）。
不讀時鐘；寄送是網路呼叫，路由不拿行動鎖。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from tianxia.core import identity_base

from . import senders

MAIL_SUBJECT = "天下大勢帳號通知"  # 待 joy 潤
SMS_TEXT = "【天下大勢】{text}"  # 待 joy 潤
LOG_LINE = "identity 通知 {provider} {display}：{text}"  # 主機看的字（fake_services 開著時印；不是玩家看的）
NONCE = 12


def notify_key(path: Path | None = None) -> bytes | None:
    try:
        data = json.loads(Path(path or identity_base.KEY_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    key = data.get("notify_key") if isinstance(data, dict) else None
    if not isinstance(key, str) or len(key) < identity_base.KEY_MIN:
        return None
    return key.encode("utf-8")


def _aead():
    key = notify_key()
    if key is None:
        return None
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415  沒裝就當沒有金鑰
    except ImportError:
        return None
    return AESGCM(hashlib.sha256(key).digest())


def seal(value: str, aad: str) -> bytes | None:
    aead = _aead()
    if aead is None:
        return None
    nonce = os.urandom(NONCE)
    return nonce + aead.encrypt(nonce, value.encode("utf-8"), aad.encode("utf-8"))


def unseal(blob: bytes | None, aad: str) -> str | None:
    aead = _aead()
    if aead is None or not blob or len(blob) <= NONCE:
        return None
    try:
        return aead.decrypt(bytes(blob[:NONCE]), bytes(blob[NONCE:]), aad.encode("utf-8")).decode("utf-8")
    except Exception:  # noqa: BLE001  金鑰換了、資料壞了：當沒有這一列
        return None


def _aad(account_id: int, provider: str) -> str:
    return f"{account_id}|{provider}"


def sealer(channel: str):
    """綁定那一下寄碼時封號碼用（codes.send 的 seal=）：value → 封好的 bytes 或 None。"""
    return lambda value: seal(value, f"challenge|{channel}")


def keep(side, account_id: int, provider: str, challenge_blob: bytes | None, display: str) -> bool:
    """綁成功：拆開單上封的號碼、照帳號再封一次存進 contacts；單上沒有（沒有金鑰、舊單）回假、不存。"""
    value = unseal(challenge_blob, f"challenge|{provider}")
    if value is None:
        return False
    blob = seal(value, _aad(account_id, provider))
    if blob is None:
        return False
    side.put_contact(account_id, provider, blob, display or "")
    return True


def send_all(shell, side, account_id: int, text: str, *, extra=(), skip=()) -> int:
    """寄一則通知給這個帳號現有的每一個號碼（extra：剛拿掉的那一列也寄；skip：不寄的 provider）。回寄出的則數；沒有金鑰回 0。"""
    if _aead() is None:
        return 0
    content = shell.CONTENT
    out = senders.pick(content)
    fake = bool(content.config.identity.fake_services)
    rows = [*side.contacts(account_id), *extra]
    sent = 0
    for row in rows:
        provider = row["provider"]
        if provider in skip:
            continue
        value = unseal(row["sealed"], _aad(account_id, provider))
        if value is None:
            continue
        try:
            if provider == "phone":
                out.sms.send(value, SMS_TEXT.format(text=text))
            else:
                out.mail.send(value, MAIL_SUBJECT, text)
        except senders.SendFailed:
            continue
        sent += 1
        if fake:
            print(LOG_LINE.format(provider=provider, display=row.get("display") or "", text=text), flush=True)
    return sent
