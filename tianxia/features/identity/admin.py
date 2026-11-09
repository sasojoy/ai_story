"""管理者的帳號工具（帳號與客服第 204 批；設計 4.3「管理者重設密碼的畫面同時列出綁定與時間」、6.4、6.5）。

- /api/do/<op> 的三樣（routes.admin_tools 登記、給 gate 與現實時間；殼先 gate、再 is_admin，在行動鎖裡跑）：
  identity_view {target}：一行一種，綁定與上次驗證的時間；identity_unbind {target, provider}：解綁某一種（不看近期驗證、72 小時、扣押，
  只看至少留一種）；identity_delete {target}：刪帳號（刪 accounts、logins、sessions 列；名號由存檔占住、錢包留著；不能刪自己）。
  解綁與刪帳號的雜湊永久留在旁檔（30 天與封測發放照用），被解綁的帳號寫一則「帳號」紀錄。
- search_rows：/api/identity/admin/accounts 的每一列（AccountStore.search(keys=True) 加綁定與時間）。
target 照管理者重設密碼的找法（先帳號、再名號：AccountStore.find）。現實時間由 routes 傳進來（now），不讀時鐘、不 import fastapi。
"""
from __future__ import annotations

from datetime import datetime

from tianxia.core import identity_base

from . import binding, contacts, notes, store

NOT_FOUND = "找不到這個帳號或名號。"  # 管理者重設密碼的同一句（features/admin/routes.py；不是新字）
ADMIN_UNBOUND = "已解綁 {who} 的{kind}。"  # 待 joy 潤
ADMIN_DELETED = "已刪除 {who} 的帳號（名號仍被占住，錢包留著）。"  # 待 joy 潤
ADMIN_SELF = "不能刪自己的帳號。"  # 待 joy 潤
ADMIN_VIEW_HEAD = "{who} 的登入方式："  # 待 joy 潤
ADMIN_VIEW_LINE = "{kind}：{shown}（綁定 {bound}，上次驗證 {verified}）"  # 待 joy 潤
ADMIN_FIRST = "開帳號時"  # 待 joy 潤（bound_at 是 NULL：開帳號那一種或第 204 批以前綁的）
ADMIN_NONE = "—"  # 待 joy 潤（沒有驗證紀錄）
ADMIN_NO_WAY = "這個帳號沒有綁這一種（密碼不從這裡拿掉）。"  # 待 joy 潤


def _when(at: float | None, empty: str) -> str:
    return empty if at is None else datetime.fromtimestamp(at).strftime("%Y-%m-%d %H:%M")


def _side() -> store.IdentityStore:
    return store.IdentityStore()


def _lines(shell, key: str) -> list[dict]:
    """這個帳號每一種（照 binding.ORDER；記號列不算）：{provider, name, shown, bound_at, verified_at}。"""
    accounts = shell.account_store()
    account = accounts.get(key)
    if account is None:
        return []
    meta = _side().meta(account.id)
    rows = {r["provider"]: r for r in accounts.logins_of(key) if r["provider"] != binding.MARKER}
    out = []
    for provider in binding.kinds_of(rows):
        m = meta.get(provider) or {}
        out.append({"provider": provider, "name": binding.kind_name(provider), "shown": rows[provider]["display"],
                    "bound_at": m.get("bound_at"), "verified_at": m.get("verified_at")})
    return out


def search_rows(shell, q: str) -> list[dict]:
    rows = shell.account_store().search(q, keys=True)
    return [{**r, "binds": _lines(shell, r["key"])} for r in rows]


def _target(shell, body: dict) -> tuple[str | None, object]:
    accounts = shell.account_store()
    key = accounts.find(str(body.get("target", "")))
    return key, (accounts.get(key) if key is not None else None)


def view(shell, game, body: dict) -> list[str]:
    key, account = _target(shell, body)
    if account is None:
        return [NOT_FOUND]
    out = [ADMIN_VIEW_HEAD.format(who=account.login)]
    for line in _lines(shell, key):
        out.append(ADMIN_VIEW_LINE.format(kind=line["name"], shown=line["shown"], bound=_when(line["bound_at"], ADMIN_FIRST),
                                          verified=_when(line["verified_at"], ADMIN_NONE)))
    return out


def unbind(shell, game, body: dict, now: float) -> list[str]:
    key, account = _target(shell, body)
    if account is None:
        return [NOT_FOUND]
    provider = str(body.get("provider", ""))
    accounts = shell.account_store()
    rows = {r["provider"]: r for r in accounts.logins_of(key) if r["provider"] != binding.MARKER}
    if provider == "password" or provider not in rows:
        return [ADMIN_NO_WAY]
    if not binding.can_remove(rows, provider):
        return [binding.KEEP_ONE]
    accounts.remove_login(key, provider)
    side = _side()
    side.record_unbound(binding.subject_hash(identity_base.read_key() or b"", provider, rows[provider]["subject"]), provider, account.id, now)
    side.drop_meta(account.id, provider)
    side.drop_contacts(account.id, provider)  # 第 208 批：通知用的加密號碼一起刪
    notes.add(side, account.id, binding.NOTE_ADMIN_UNBOUND.format(kind=binding.kind_name(provider)), now)
    # 第 209 批（PM 11/09 定寄）：寄給剩下綁著的 Email、手機（被拿掉的那一支上面已刪）；沒有可寄的只寫上面那則紀錄
    contacts.send_all(shell, side, account.id, binding.MAIL_ADMIN_UNBOUND.format(kind=binding.kind_name(provider)))
    return [ADMIN_UNBOUND.format(who=account.login, kind=binding.kind_name(provider))]


def delete(shell, game, body: dict, now: float) -> list[str]:
    key, account = _target(shell, body)
    if account is None:
        return [NOT_FOUND]
    accounts = shell.account_store()
    mine = accounts.owner_of(game.state.player.name) if game.state.player.name else None
    if mine is not None and accounts.account_id(mine) == account.id:
        return [ADMIN_SELF]
    gone = accounts.delete_account(key)
    side = _side()
    secret = identity_base.read_key() or b""
    for row in gone:
        if row["provider"] in binding.WAYS:
            side.record_unbound(binding.subject_hash(secret, row["provider"], row["subject"]), row["provider"], account.id, now)
    side.drop_meta(account.id)
    side.drop_contacts(account.id)  # 第 208 批
    return [ADMIN_DELETED.format(who=account.login)]
