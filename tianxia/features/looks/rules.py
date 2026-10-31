"""擂台形象的規則（純函式；功能包 tianxia/features/looks/）。

- 預設是斗笠小子（id 空字串，圖在 web/img/arena/）；其他的一套寫在 content/looks.json，圖在 web/img/looks/<id>/（九張，同預設的檔名）。
- 買到的形象是帳號的（購買那一列 data 的 look_id，core.services.look_ids），換季也帶著走（Joy 2026-10-31「花錢買的東西不能不見」）。
- 穿哪一套記在 mall_entitlements（kind 'look'、key 'wear'、data {"look": id}）；讀的時候再驗一次買到了沒（退了款就換回預設）。
- 假人不買，照名號的雜湊挑一套 bots 開著的（多數穿預設的）：不然「穿付費形象的一定是真人」看得出來（伺服器假人設計）。
不讀時鐘、不碰 rng。
"""
from __future__ import annotations

import hashlib

from tianxia.core.services import look_ids
from tianxia.models import Content
from tianxia.wallet import Wallet

DEFAULT = ""  # 預設的斗笠小子
DEFAULT_NAME = "斗笠小子"
WEAR_KIND, WEAR_KEY = "look", "wear"
BOT_PLAIN = 3  # 假人挑形象時預設那一套佔幾份（每一套 bots 開著的各佔一份）

# 待 joy 潤
WORN = "換上了「{name}」。擂台上照這一套畫。"
ALREADY = "你身上就是「{name}」。"
NOT_OWNED = "你還沒有這一套形象，先到萬寶閣買。"
OFF = "形象還沒開。"


def on(content: Content) -> bool:
    """形象開著：商城開著（錢包讀得到）而且 content/looks.json 至少一套。"""
    return content.config.mall.enabled and bool(content.looks)


def name_of(content: Content, look: str) -> str:
    known = content.looks.get(look)
    return known.name if known else DEFAULT_NAME


def owned(content: Content, wallet: Wallet, owner: str) -> list[str]:
    """買到、而且內容裡還認得的那幾套（舊的在前）；預設的不算。"""
    return [look for look in look_ids(wallet, owner) if look in content.looks]


def worn(content: Content, wallet: Wallet, owner: str) -> str:
    """穿著哪一套：記的那一套還買著、內容裡還有才算，其餘是預設的。"""
    data = wallet.entitlement(owner, WEAR_KIND, WEAR_KEY) or {}
    look = str(data.get("look", DEFAULT))
    return look if look in owned(content, wallet, owner) else DEFAULT


def wear(content: Content, wallet: Wallet, owner: str, look: str) -> tuple[bool, str]:
    """換上一套（DEFAULT 是換回斗笠小子）：回（換了沒、那一句）。"""
    if look != DEFAULT and look not in owned(content, wallet, owner):
        return False, NOT_OWNED
    if look == worn(content, wallet, owner):
        return False, ALREADY.format(name=name_of(content, look))
    wallet.set_entitlement(owner, WEAR_KIND, WEAR_KEY, {"look": look})
    return True, WORN.format(name=name_of(content, look))


def bot_look(content: Content, name: str) -> str:
    """假人穿哪一套：照名號的雜湊（同一個名號每次一樣），bots 開著的每一套一份、預設的 BOT_PLAIN 份。"""
    pool = [look.id for look in content.looks.values() if look.bots]
    if not pool:
        return DEFAULT
    pick = int.from_bytes(hashlib.sha256(f"look:{name}".encode()).digest()[:4], "big") % (len(pool) + BOT_PLAIN)
    return pool[pick] if pick < len(pool) else DEFAULT


def view(content: Content, wallet: Wallet, owner: str, shop: dict[str, str]) -> dict:
    """萬寶閣「形象」那一頁：穿著哪一套、每一套（預設在最前）買了沒、沒買的賣哪一件商品（shop：look id → 商品 id，沒上架的不在）。"""
    have = set(owned(content, wallet, owner))
    items = [{"id": DEFAULT, "name": DEFAULT_NAME, "note": "", "owned": True, "item": None}]
    for look in content.looks.values():
        if look.id in have or look.id in shop:
            items.append({"id": look.id, "name": look.name, "note": look.note, "owned": look.id in have,
                          "item": None if look.id in have else shop[look.id]})
    return {"worn": worn(content, wallet, owner), "looks": items}


def problems(content: Content) -> list[str]:
    """content/looks.json 哪裡寫錯（check_content）：id 只能小寫英數與底線（當資料夾名）、不能是空的。"""
    out = []
    for look in content.looks.values():
        if not look.id or not all(ch.isascii() and (ch.islower() or ch.isdigit() or ch == "_") for ch in look.id):
            out.append(f"形象 {look.id!r}：id 只能寫小寫英數與底線")
    return out
