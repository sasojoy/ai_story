"""全服池上限到了通知管理者（帳號與客服第 208 批；第 203 批留下的；設計 4.6 全服分池）。

- pool_full(shell, bucket, now)：codes.send 的 on_full（check_all_and_record 回了滿的那一格）。只認 pool: 開頭（一號 60 秒、每日、來源滿了不算）；
  同一格一小時最多一次（旁檔 cap_alerts，alert_due 檢查並記同一筆交易）；經殼的 shell.WEB_PUSH（None 就跳過）推給 Config.admins 每個名號綁的帳號
  （AccountStore.owner_of；查不到跳過），tag identity。推送出錯吞掉：回給寄碼的人的位元組不變。
- admin_slot(ctx)：管理頁（STATUS_ORDER["admin"] 的表外格，接在表尾）identity_alerts：這 24 小時內通知過的每一格一行；identity 關、旁檔不在、沒有通知都回 {}。
管理者看的字（不是玩家看的）每一句也標待 joy 潤。現實時間由呼叫端傳入（路由的 shell.time、Game.now），不讀時鐘。
"""
from __future__ import annotations

from datetime import datetime

from tianxia.core import identity_base

from . import store

POOL_FULL = "驗證碼全服上限到了：{channel}{pool}池（{span}），{stamp}起暫停寄送。"  # 待 joy 潤（管理者看）
CHANNEL = {"phone": "簡訊", "email": "Email"}  # 待 joy 潤
POOL = {"login": "登入", "bind": "綁定", "anon": "新號碼"}  # 待 joy 潤
SPAN = {"hour": "一小時", "day": "一天"}  # 待 joy 潤
EVERY = 3600  # 同一格多久才再通知一次
WINDOW = 86400  # 管理頁列多久以內的
TAG = "identity"


def line(bucket: str, at: float) -> str | None:
    """pool:<channel>:<pool>:<hour|day> → 管理者看的一行；不是全服池的桶回 None。"""
    parts = bucket.split(":")
    if len(parts) != 4 or parts[0] != "pool":
        return None
    _p, channel, pool, span = parts
    return POOL_FULL.format(channel=CHANNEL.get(channel, channel), pool=POOL.get(pool, pool), span=SPAN.get(span, span),
                            stamp=datetime.fromtimestamp(at).strftime("%m-%d %H:%M"))


def pool_full(shell, bucket: str, now: float) -> None:
    text = line(bucket, now)
    if text is None:
        return
    if not store.IdentityStore().alert_due(bucket, now, EVERY):
        return
    push = shell.WEB_PUSH
    if push is None:
        return
    accounts = shell.account_store()
    for name in shell.CONTENT.config.admins:
        key = accounts.owner_of(name)
        if key is None:
            continue
        try:
            push.send(key, shell.NOTICE_TITLE, text, tag=TAG, now=now)
        except Exception:  # noqa: BLE001  推送是附帶的：出錯不影響寄碼那一下的回應
            continue


def admin_slot(ctx) -> dict:
    if not identity_base.on(ctx.content):
        return {}
    path = store.default_side_path()
    now = ctx.now
    if not now or not path.exists():
        return {}
    rows = store.IdentityStore(path).alerts_since(now - WINDOW)
    lines = [text for bucket, at in rows if (text := line(bucket, at)) is not None]
    return {"identity_alerts": lines} if lines else {}
