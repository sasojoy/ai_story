"""形象市集（功能包 looks 第四批；設計 v3 第四期：創作者與官方五五分）。純規則，不讀時鐘（now 由呼叫端傳進來）。

- 上架：自己下單做好的自建形象（u<購買 id>，orders.MADE）可以掛到市集，自己定價（PRICE_MIN～PRICE_MAX）；隨時下架。
  上架記在 mall_entitlements（kind 'look'、key 'market:<形象 id>'、data {"price"}），不改資料表。下架了，買過的人照樣留著（花錢買的不能不見）。
- 購買：別人花元寶買一份（購買那一列 data 記 look_market、look_id、name、seller、share），買到的跟官方形象一樣是帳號的、換季也在。
  自己的不能買、同一套買過了不再賣。假人不買。Config.mall.market_paid_only 開著時只准用儲值的元寶（儲值進來的減掉已經花在市集的）。
- 分成：賣出的一半（SHARE，無條件捨去）給創作者，但先押 HOLD_DAYS 天（退款期）；過了才入帳（編號 sale:<購買 id>，原因 grant、
  帳上寫「市集分成」）。入帳是懶的：創作者看「形象」那一頁、或上架、下架時結一次（settle）。押著的時候退了款，分成就不給；
  已經入帳的再退款，分成不追回（官方吸收，這一版）。
"""
from __future__ import annotations

from dataclasses import dataclass

from tianxia.models import Content, MallItem
from tianxia.wallet import Purchase, Wallet

from . import orders

EFFECT = "look_market"
KIND, KEY = "look", "market:"
PRICE_MIN, PRICE_MAX, PRICE_DEFAULT = 300, 3000, 600
SHARE = 0.5
HOLD_DAYS = 7
DAY = 86400.0

# 待 joy 潤
NOT_OPEN = "市集還沒開。"
NOT_YOURS = "這一套不是你做的，不能上架。"
BAD_PRICE = "價錢要在 {lo}～{hi} 元寶之間。"
LISTED = "「{name}」掛到市集了，一份 {price} 元寶；賣出一份你分 {share}（{days} 天後入帳）。"
UNLISTED = "「{name}」從市集撤下了；買過的人照樣留著。"
NOT_LISTED = "市集上沒有這一套。"
OWN = "這是你自己做的。"
HAVE = "這一套你已經有了。"
SHORT = "元寶不夠：這一套要 {price}，你有 {balance}。"
PAID_ONLY = "市集只收儲值的元寶：這一套要 {price}，你能用的有 {paid}。"
DUPLICATE = "這一份已經買過了。"
BOUGHT = "買下了「{name}」（{seller}做的）：元寶 -{price}（還剩 {left}）。到「形象」換上。"
SETTLED = "市集分成入帳：元寶 +{n}。"


@dataclass(frozen=True)
class Sale:
    pid: int
    buyer: str
    look: str
    name: str
    seller: str
    price: int
    share: int
    time: float
    refunded: bool


def item_of(content: Content) -> MallItem | None:
    return next((i for i in content.mall.values() if i.effects.get(EFFECT)), None)


def share_of(price: int) -> int:
    return int(price * SHARE)


def of(b: Purchase) -> Sale | None:
    d = b.data
    if not d.get(EFFECT):
        return None
    return Sale(pid=b.id, buyer=b.owner, look=str(d.get("look_id", "")), name=str(d.get("name", "")), seller=str(d.get("seller", "")),
                price=b.price, share=int(d.get("share", 0)), time=b.time, refunded=b.refunded is not None)


def sales(wallet: Wallet, item: str) -> list[Sale]:
    return [s for s in (of(b) for b in wallet.purchases_of(item)) if s is not None]


def bought(wallet: Wallet, owner: str) -> dict[str, str]:
    """這個人從市集買到、沒退的：形象 id → 名字。"""
    return {s.look: s.name for s in (of(b) for b in wallet.purchases(owner)) if s is not None and not s.refunded}


def listings(wallet: Wallet) -> list[dict]:
    """市集上每一套（舊的在前）：{look, seller, price}。"""
    return [{"look": key[len(KEY):], "seller": owner, "price": int(data.get("price", PRICE_DEFAULT))}
            for owner, key, data in wallet.entitlements(KIND) if key.startswith(KEY)]


def listing(wallet: Wallet, look: str) -> dict | None:
    return next((x for x in listings(wallet) if x["look"] == look), None)


def made_by(wallet: Wallet, owner: str) -> dict[str, str]:
    """這個人做好、上架了的自建形象：id → 名字（只有這些能掛到市集）。"""
    return orders.names(wallet, owner)


def list_look(wallet: Wallet, owner: str, look: str, price: int) -> tuple[bool, str]:
    mine = made_by(wallet, owner)
    if look not in mine:
        return False, NOT_YOURS
    if not PRICE_MIN <= price <= PRICE_MAX:
        return False, BAD_PRICE.format(lo=PRICE_MIN, hi=PRICE_MAX)
    wallet.set_entitlement(owner, KIND, KEY + look, {"price": price})
    return True, LISTED.format(name=mine[look], price=price, share=share_of(price), days=HOLD_DAYS)


def unlist_look(wallet: Wallet, owner: str, look: str) -> tuple[bool, str]:
    mine = made_by(wallet, owner)
    if look not in mine or listing(wallet, look) is None:
        return False, NOT_LISTED
    wallet.drop_entitlement(owner, KIND, KEY + look)
    return True, UNLISTED.format(name=mine[look])


def paid_left(wallet: Wallet, owner: str, item: str) -> int:
    """儲值的元寶還剩多少能用在市集：儲值進來的，減掉已經花在市集（沒退）的，不超過餘額。"""
    spent = sum(s.price for s in sales(wallet, item) if s.buyer == owner and not s.refunded)
    return max(0, min(wallet.balance(owner), wallet.reason_total(owner, "topup") - spent))


def buy(
    content: Content, wallet: Wallet, owner: str, look: str, ref: str, *, names: dict[str, str], seller_name: str,
    now: float, day: int, season: int,
) -> tuple[int | None, str]:
    """買一份（同 mall.buy：查重 → 驗 → 寫購買紀錄 → 扣元寶，同一筆交易）。names：這一套的名字（呼叫端從創作者的訂單查）。"""
    item = item_of(content)
    if item is None:
        return None, NOT_OPEN
    full = f"buy:{owner}:{ref}"
    with wallet.db.transaction():
        if wallet.purchase_by_ref(full) is not None:
            return None, DUPLICATE
        found = listing(wallet, look)
        if found is None or look not in names:
            return None, NOT_LISTED
        if found["seller"] == owner:
            return None, OWN
        if look in bought(wallet, owner):
            return None, HAVE
        price = found["price"]
        balance = wallet.balance(owner)
        if balance < price:
            return None, SHORT.format(price=price, balance=balance)
        if content.config.mall.market_paid_only:
            paid = paid_left(wallet, owner, item.id)
            if paid < price:
                return None, PAID_ONLY.format(price=price, paid=paid)
        data = {EFFECT: 1, "look_id": look, "name": names[look], "seller": found["seller"], "share": share_of(price)}
        pid = wallet.add_purchase(owner, full, item.id, price, time=now, day=day, season=season, data=data)
        if not wallet.post(owner, -price, "buy", full, time=now, purchase_id=pid):
            raise RuntimeError(f"購買編號 {full} 已經記過帳，購買紀錄卻沒有")
        left = wallet.balance(owner)
    return pid, BOUGHT.format(name=names[look], seller=seller_name, price=price, left=left)


def settle(wallet: Wallet, item: str, seller: str, now: float) -> int:
    """把押滿 HOLD_DAYS 天、沒退款的分成入帳（編號 sale:<購買 id>，重複叫不會算兩次）：回這一次入了多少。"""
    total = 0
    for s in sales(wallet, item):
        if s.seller == seller and not s.refunded and s.share > 0 and now >= s.time + HOLD_DAYS * DAY:
            if wallet.post(seller, s.share, "grant", f"sale:{s.pid}", time=now, purchase_id=s.pid, note=f"市集分成：{s.name}"):
                total += s.share
    return total


def earnings(wallet: Wallet, item: str, seller: str) -> dict:
    """創作者看的：賣出幾份、入帳了多少、還押著多少。"""
    mine = [s for s in sales(wallet, item) if s.seller == seller and not s.refunded]
    paid = sum(s.share for s in mine if wallet.has_ref(f"sale:{s.pid}"))
    return {"sold": len(mine), "paid": paid, "held": sum(s.share for s in mine) - paid}
