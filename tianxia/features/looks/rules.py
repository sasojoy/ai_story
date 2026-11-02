"""擂台形象的規則（純函式；功能包 tianxia/features/looks/）。

- 預設是斗笠小子（id 空字串，圖在 web/img/arena/）；其他的一套寫在 content/looks.json，圖在 web/img/looks/<id>/（十張，同預設的檔名）。
- 買到的形象是帳號的（購買那一列 data 的 look_id，core.services.look_ids），換季也帶著走（Joy 2026-10-31「花錢買的東西不能不見」）。
- 穿哪一套記在 mall_entitlements（kind 'look'、key 'wear'、data {"look": id}）；讀的時候再驗一次買到了沒（退了款就換回預設）。
- 假人不買，照名號的雜湊挑一套 bots 開著的（多數穿預設的）：不然「穿付費形象的一定是真人」看得出來（伺服器假人設計）。
- 疊圖飾品（Joy 2026-11-02）：content/looks.json 裡寫了 slot 的那幾件。頭（head）、臉（face）、腰（waist）各戴一件，記在
  mall_entitlements（kind 'look'、key 'gear'、data {slot: id}）；任何一套形象都戴得上（網頁照每一格自己找頭、腰的位置疊上去）。
  擂台、走一趟送的是「皮」：形象 id，戴了飾品再接「~飾品.飾品」（skin()）。假人也照名號的雜湊戴（同形象）。
不讀時鐘、不碰 rng。
"""
from __future__ import annotations

import hashlib

from tianxia.core.services import look_ids
from tianxia.models import Content
from tianxia.wallet import Wallet

from . import market, orders

DEFAULT = ""  # 預設的斗笠小子
DEFAULT_NAME = "斗笠小子"
WEAR_KIND, WEAR_KEY = "look", "wear"
GEAR_KEY = "gear"
SLOTS = ("head", "face", "waist")  # 疊的順序：先頭再臉再腰（skin 裡照這個順序）
SLOT_NAMES = {"head": "頭", "face": "臉", "waist": "腰"}
BOT_PLAIN = 3  # 假人挑形象時預設那一套佔幾份（每一套 bots 開著的各佔一份）
BOT_BARE = 4  # 假人每一個位置不戴飾品佔幾份（每一件 bots 開著的各佔一份）

# 待 joy 潤
WORN = "換上了「{name}」。擂台上照這一套畫。"
ALREADY = "你身上就是「{name}」。"
NOT_OWNED = "你還沒有這一套形象，先到萬寶閣買。"
GEAR_ON = "戴上了「{name}」。"
GEAR_OFF = "拿下了「{name}」。"
GEAR_NOT_OWNED = "你還沒有這一件飾品，先到萬寶閣買。"
OFF = "形象還沒開。"


def on(content: Content) -> bool:
    """形象開著：商城開著（錢包讀得到）而且 content/looks.json 至少一套。"""
    return content.config.mall.enabled and bool(content.looks)


def name_of(content: Content, look: str, custom: dict[str, str] | None = None) -> str:
    known = content.looks.get(look)
    return known.name if known else (custom or {}).get(look, DEFAULT_NAME)


def full(content: Content) -> list:
    """整套的形象（不是飾品的那幾件），照檔案的順序。"""
    return [look for look in content.looks.values() if not look.slot]


def owned(content: Content, wallet: Wallet, owner: str) -> list[str]:
    """買到、而且還認得的那幾套（舊的在前）：內容裡的官方形象，加上自己下單、上架了的自建形象（u<購買 id>）；預設的不算。飾品不算。"""
    return [look for look in look_ids(wallet, owner)
            if (look in content.looks and not content.looks[look].slot) or orders.is_custom(look)]


def owned_gear(content: Content, wallet: Wallet, owner: str) -> list[str]:
    """買到、而且內容裡還有的飾品。"""
    return [gid for gid in look_ids(wallet, owner) if gid in content.looks and content.looks[gid].slot]


def gear_worn(content: Content, wallet: Wallet, owner: str) -> list[str]:
    """戴著哪幾件（照 SLOTS 的順序）：記的那一件還買著、還在那個位置才算。"""
    data = wallet.entitlement(owner, WEAR_KIND, GEAR_KEY) or {}
    have = set(owned_gear(content, wallet, owner))
    return [str(data[s]) for s in SLOTS if data.get(s) in have and content.looks[str(data[s])].slot == s]


def wear_gear(content: Content, wallet: Wallet, owner: str, gid: str) -> tuple[bool, str]:
    """戴上一件飾品（那個位置原本戴的換下來）；已經戴著的再按一次就拿下。回（動了沒、那一句）。"""
    if gid not in owned_gear(content, wallet, owner):
        return False, GEAR_NOT_OWNED
    item = content.looks[gid]
    data = {s: v for s, v in (wallet.entitlement(owner, WEAR_KIND, GEAR_KEY) or {}).items() if s in SLOTS}
    if data.get(item.slot) == gid:
        data.pop(item.slot)
        line = GEAR_OFF.format(name=item.name)
    else:
        data[item.slot] = gid
        line = GEAR_ON.format(name=item.name)
    wallet.set_entitlement(owner, WEAR_KIND, GEAR_KEY, data)
    return True, line


def skin(look: str, gear: list[str]) -> str:
    """擂台、走一趟送給網頁的「皮」：形象 id，戴了飾品接「~頭.臉.腰」（網頁 skinParts 拆開）。"""
    return f"{look}~{'.'.join(gear)}" if gear else look


def bot_gear(content: Content, name: str) -> list[str]:
    """假人戴哪幾件：每一個位置照名號的雜湊挑（bots 開著的各一份、不戴的 BOT_BARE 份），同一個名號每次一樣。"""
    out = []
    for s in SLOTS:
        pool = [acc.id for acc in content.looks.values() if acc.slot == s and acc.bots]
        if not pool:
            continue
        pick = int.from_bytes(hashlib.sha256(f"gear:{s}:{name}".encode()).digest()[:4], "big") % (len(pool) + BOT_BARE)
        if pick < len(pool):
            out.append(pool[pick])
    return out


def worn(content: Content, wallet: Wallet, owner: str) -> str:
    """穿著哪一套：記的那一套還買著、內容裡還有才算，其餘是預設的。"""
    data = wallet.entitlement(owner, WEAR_KIND, WEAR_KEY) or {}
    look = str(data.get("look", DEFAULT))
    return look if look in owned(content, wallet, owner) else DEFAULT


def wear(content: Content, wallet: Wallet, owner: str, look: str) -> tuple[bool, str]:
    """換上一套（DEFAULT 是換回斗笠小子）：回（換了沒、那一句）。"""
    if look != DEFAULT and look not in owned(content, wallet, owner):
        return False, NOT_OWNED
    custom = {**orders.names(wallet, owner), **market.bought(wallet, owner)}
    if look == worn(content, wallet, owner):
        return False, ALREADY.format(name=name_of(content, look, custom))
    wallet.set_entitlement(owner, WEAR_KIND, WEAR_KEY, {"look": look})
    return True, WORN.format(name=name_of(content, look, custom))


def bot_look(content: Content, name: str) -> str:
    """假人穿哪一套：照名號的雜湊（同一個名號每次一樣），bots 開著的每一套一份、預設的 BOT_PLAIN 份。"""
    pool = [look.id for look in full(content) if look.bots]
    if not pool:
        return DEFAULT
    pick = int.from_bytes(hashlib.sha256(f"look:{name}".encode()).digest()[:4], "big") % (len(pool) + BOT_PLAIN)
    return pool[pick] if pick < len(pool) else DEFAULT


def view(content: Content, wallet: Wallet, owner: str, shop: dict[str, str]) -> dict:
    """萬寶閣「形象」那一頁：穿著哪一套、每一套（預設在最前）買了沒、沒買的賣哪一件商品（shop：look id → 商品 id，沒上架的不在）。"""
    have = set(owned(content, wallet, owner))
    items = [{"id": DEFAULT, "name": DEFAULT_NAME, "note": "", "owned": True, "item": None, "mine": False}]
    for look in full(content):
        if look.id in have or look.id in shop:
            items.append({"id": look.id, "name": look.name, "note": look.note, "owned": look.id in have,
                          "item": None if look.id in have else shop[look.id], "mine": False})
    mine = orders.mine(wallet, owner)
    for o in reversed(mine):  # 自建的、上架了的（舊的在前）
        if o.status == orders.MADE and o.look in have:
            items.append({"id": o.look, "name": o.name, "note": o.prompt, "owned": True, "item": None, "mine": True})
    for look, name in market.bought(wallet, owner).items():  # 從市集買到的（別人做的）
        if look in have:
            items.append({"id": look, "name": name, "note": "", "owned": True, "item": None, "mine": False})
    item = orders.item_of(content)
    order = None if item is None else {
        "price": item.price, "name_max": orders.NAME_MAX, "prompt_max": orders.PROMPT_MAX,
        "open": any(o.status in (orders.PENDING, orders.REVIEW) for o in mine),
        "list": [{"id": o.pid, "name": o.name, "prompt": o.prompt, "status": o.status, "status_text": orders.STATUS_TEXT[o.status],
                  "reason": o.reason, "withdraw": o.status in orders.CAN_WITHDRAW} for o in mine],
    }
    mine_gear, on_now = set(owned_gear(content, wallet, owner)), set(gear_worn(content, wallet, owner))
    gear = [{"id": acc.id, "name": acc.name, "note": acc.note, "slot": acc.slot, "slot_text": SLOT_NAMES[acc.slot], "owned": acc.id in mine_gear,
             "item": None if acc.id in mine_gear else shop[acc.id], "worn": acc.id in on_now}
            for acc in content.looks.values() if acc.slot and (acc.id in mine_gear or acc.id in shop)]
    return {"worn": worn(content, wallet, owner), "looks": items, "order": order, "gear": gear,
            "skin": skin(worn(content, wallet, owner), gear_worn(content, wallet, owner))}


def problems(content: Content) -> list[str]:
    """content/looks.json 哪裡寫錯（check_content）：id 只能小寫英數與底線（當資料夾名）、不能是空的。"""
    out = []
    for look in content.looks.values():
        if not look.id or not all(ch.isascii() and (ch.islower() or ch.isdigit() or ch == "_") for ch in look.id):
            out.append(f"形象 {look.id!r}：id 只能寫小寫英數與底線")
        if look.slot and not look.id.startswith(f"{look.slot}_"):
            out.append(f"飾品 {look.id!r}：id 要以「{look.slot}_」開頭（網頁照它認戴在哪）")
        if not look.slot and look.id.split("_")[0] in SLOTS:
            out.append(f"形象 {look.id!r}：整套的形象 id 不能以 head_、face_、waist_ 開頭（那是飾品）")
    return out
