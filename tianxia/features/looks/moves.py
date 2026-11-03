"""招式動畫（功能包 looks 第三批；Joy 2026-10-31「自創完武學時，玩家也可以選擇建立武學攻擊的模型」、設計 v3 第三期）。純規則，不讀時鐘。

一個招式動畫是一張六格的光效（fx，1320×220，透明底），出招時疊在人身上（不管穿哪一套形象都疊得上去）。
- 下單：替自己現在練的武功（自己合成或自創的，不是內容裡的）寫一句樣子，扣元寶（購買那一列就是訂單，同自建形象）。打法照下單那一刻
  手上的兵器（揮砍、長兵、拳腳、射）。
- 上架了放進「招式庫」：帳號的，換季也帶著走（Joy「花錢買的東西不能不見」）。武學每季歸零，所以每一季要把招式重新綁到自己的一門武功上；
  同一種打法免費改綁（設計 v3），換打法要重畫（這一版不做，要重新下單）。
- 擂台：上擂台那一刻（報名、更新分身、挑人），身上的武功綁了招式、手上的打法也對得上，出招就疊那一張光效。

訂單的狀態同 orders.py（pending／review／made／rejected）；上架了 data 記 move_id＝m<購買 id>。
身上穿哪一招記在帳號那一側（mall_entitlements，同形象），跟練哪一門武功無關、換季也帶著走。
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from tianxia import speech  # 共用規則層（玩家寫的字過字表）
from tianxia.models import Content, MallItem
from tianxia.wallet import Purchase, Wallet

from . import orders, scenes

EFFECT = "move_order"  # 購買那一列的欄位（兩種絕招共用，差別記在 data 的 basic）
WEAR_KIND, WEAR_KEY = "look", "move"  # 穿哪一招記在帳號那一側（同形象 rules.WEAR_*；換季也帶著走）
EFFECT_BASIC = "move_basic"  # 通用絕招那件商品的效果（60 元寶、不另外畫圖、當場學成）
PREFIX = "m"
SHEET, FRAMES = "fx", 6
STYLES = {"slash": "揮砍", "pole": "長兵", "fist": "拳腳", "shoot": "射"}
KIND_STYLE = {"劍": "slash", "刀": "slash", "槍": "pole", "棍": "pole", "弓弩": "shoot", "拳腳": "fist"}  # 同 web/arena_anim.js 的 RING_ARMS

# 待 joy 潤
NOT_SOLD = "招式動畫還沒開賣。"
NO_ART = "先練一門自己合成或自創的武功，才能替它畫招式。"
NO_PROMPT = "寫一句這一招長什麼樣子。"
OPEN_ORDER = "你還有一張招式動畫在做：等它好了、或按「撤回」退掉，再下一張。"
ALREADY = "「{art}」這一種打法已經綁了招式。"  # 還留著：舊的訊息，現在不擋下單了
NOT_WORN = "（你身上已經穿著一招，這一招先放進招式庫；要換上去到「形象」那一頁按一下。）"
# 獨門絕招一定要畫一樣東西；那一句裡沒有看得出形狀的東西就不收錢（企劃者 2026-11-02 分兩種版本）
NO_SUBJECT = "獨門絕招要畫一樣看得出形狀的東西（法相、巨掌、石碑……）；這一句裡沒有，換一句，或買通用絕招（{price} 元寶，用現成的光效、當場學成）。"
LEARNED_BASIC = "「{art}」的通用絕招學成了（{style}）：元寶 -{price}（還剩 {left}）。擂台上這一招發動時就照這樣演。"
SHORT = "元寶不夠：招式動畫要 {price}，你有 {balance}。"
PLACED = "替「{art}」下單了招式動畫（{style}）：元寶 -{price}（還剩 {left}）。做好、審核過了會放進招式庫。"
LEARNED = "「{art}」的絕招學成了（{style}）：元寶 -{price}（還剩 {left}）。擂台上這一招發動時就照這樣演。"
WAIT_ART = "替「{art}」下單了絕招（{style}）：元寶 -{price}（還剩 {left}）。要畫的「{arts}」畫好、審過了就放進招式庫；沒過元寶全退。"
DUPLICATE = "這一張已經下過單了。"
WORN = "換上「{name}」了：擂台上出{style}的時候就照這一招演。"
TAKEN_OFF = "把「{name}」脫下來了：擂台上照舊只演光效。"
WEARING = "你身上就是「{name}」。"
NOT_MINE = "招式庫裡沒有這一招。"
WRONG_STYLE = "這一招是{want}的，你手上的打法是{have}：換一樣兵器，或重新下單。"
# 綁著、但手上的打法變了：擂台上不會演（出招的身體圖四種打法各一套，拳腳的光效疊在揮砍上對不準）
ASLEEP = "這一招是{want}的，你現在的打法是{have}——擂台上不會演，換回{want}才演得出來。"
ORDER_STYLE = "照你現在的打法（{style}）登記。換成別種兵器時這一招不會演，要另外下一張。"


def style_of(kind: str) -> str:
    """手上兵器的種類 → 打法（沒拿兵器是拳腳）。"""
    return KIND_STYLE.get(kind or "", "fist")


def move_id(pid: int) -> str:
    return f"{PREFIX}{pid}"


def is_move(look: str) -> bool:
    return bool(re.fullmatch(rf"{PREFIX}\d+", look or ""))


@dataclass(frozen=True)
class Move:
    pid: int
    owner: str
    art: str
    art_name: str
    style: str
    prompt: str
    status: str
    reason: str
    move: str  # 上架了的 id（m<購買 id>）
    scene: dict | None = None  # 一句話自創的導演稿（scenes.clean）；舊的光效單（一張 fx）是 None

    @property
    def name(self) -> str:  # orders.reject 寫「退回了『…』」用
        return self.art_name


def of(b: Purchase) -> Move | None:
    d = b.data
    if not d.get(EFFECT):
        return None
    status = orders.REJECTED if b.refunded is not None else str(d.get("status", orders.PENDING))
    return Move(pid=b.id, owner=b.owner, art=str(d.get("art", "")), art_name=str(d.get("art_name", "")), style=str(d.get("style", "fist")),
                prompt=str(d.get("prompt", "")), status=status, reason=str(d.get("reason", "")), move=str(d.get("move_id", "")),
                scene=d.get("scene") if isinstance(d.get("scene"), dict) else None)


def mine(wallet: Wallet, owner: str) -> list[Move]:
    return [m for m in (of(b) for b in wallet.purchases(owner)) if m is not None]


def item_ids(content: Content) -> tuple[str, ...]:
    """兩種絕招那兩件商品的 id（通用、獨門）：查某一招要兩件都看（購買那一列記的是買的那一件）。"""
    return tuple(i.id for i in (item_of(content), item_of(content, True)) if i is not None)


def every(wallet: Wallet, items) -> list[Move]:
    """這幾件商品賣出去的全部招式（items 可以是一個 id，也可以是 item_ids 那一串；舊的在前）。"""
    names = (items,) if isinstance(items, str) else tuple(items)
    out: list[Move] = []
    for name in names:
        out += [m for m in (of(b) for b in wallet.purchases_of(name)) if m is not None]
    return sorted(out, key=lambda m: m.pid)


def item_of(content: Content, basic: bool = False) -> MallItem | None:
    """絕招那件商品：basic 是通用（60，不畫圖、當場學成），不然是獨門（300，一定畫圖、送出等審核）。"""
    key = EFFECT_BASIC if basic else EFFECT
    return next((i for i in content.mall.values() if i.effects.get(key)), None)


def place(
    content: Content, wallet: Wallet, owner: str, art: str, art_name: str, style: str, prompt: str, ref: str, *,
    now: float, day: int, season: int, move_name: str = "", draft: dict | None = None, basic: bool = False,
) -> tuple[int | None, str]:
    """下單（同 orders.place 的那幾步）。art 是呼叫端驗過的、自己合成或自創的武功（空字串是沒有）。
    prompt 是玩家寫的一句（scenes.MAX_TEXT 字內、只能中文），當場變成導演稿（scenes.direct）存在這一列；
    draft 是模型在行動鎖外填好的那一張表（server.py 的三段式；沒有就走關鍵字導演）；
    basic 是通用絕招（60 元寶，企劃者 2026-11-02）：不另外畫圖、只用現成的光效，當場上架（學成）；
    獨門（300 元寶）一定要畫（法相、巨物），送出變等圖、畫好待審、管理者上架，那一句導不出東西就不收錢。
    move_name 是落款寫的招名。"""
    item = item_of(content, basic)
    if item is None:
        return None, NOT_SOLD
    if not art:
        return None, NO_ART
    prompt = speech.clean(prompt)
    full = f"buy:{owner}:{ref}"
    with wallet.db.transaction():
        if wallet.purchase_by_ref(full) is not None:
            return None, DUPLICATE
        if not prompt:
            return None, NO_PROMPT
        problem = scenes.text_problem(prompt) or speech.word_problem(prompt, content, speech.MOTTO, scenes.MAX_TEXT)
        if problem:
            return None, problem
        moves = mine(wallet, owner)
        # 要畫的那種一次只能有一張在做（畫坊的量）；通用不畫圖、當場學成，不受這一條管，也不擋別人
        if not basic and any(m.status in (orders.PENDING, orders.REVIEW) for m in moves):
            return None, OPEN_ORDER
        # 幾招都可以創（企劃者 2026-11-02）：買幾招隨你，身上同時只穿一招。
        # 身上空著，做好的那一招自己會穿上（worn 的規則：沒自己動過就是最早做好的那一招）；
        # 已經穿著別的，新的先進招式庫（獨門還要等畫好審過才上得了身，當場把能用的那一招脫掉，等圖那幾天就沒招可演）。
        taken = bool(worn(wallet, owner))
        balance = wallet.balance(owner)
        if balance < item.price:
            return None, SHORT.format(price=item.price, balance=balance)
        scene = scenes.direct(prompt, move_name or art_name, draft)
        if basic:  # 通用：要畫的那幾樣拿掉，只留現成的光效
            scene = scenes.plain(scene)
        arts = scenes.needs_art(scene)
        if not basic and not arts:  # 獨門卻沒東西可畫：不收錢（錢在下面才扣）
            other = item_of(content, True)
            return None, NO_SUBJECT.format(price=other.price if other is not None else 0)
        data = {EFFECT: 1, "art": art, "art_name": art_name, "style": style, "prompt": prompt, "status": orders.PENDING,
                "scene": scene, "basic": basic}
        pid = wallet.add_purchase(owner, full, item.id, item.price, time=now, day=day, season=season, data=data)
        if not wallet.post(owner, -item.price, "buy", full, time=now, purchase_id=pid):
            raise RuntimeError(f"購買編號 {full} 已經記過帳，購買紀錄卻沒有")
        if not arts:  # 不用畫：當場學成
            wallet.update_data(pid, status=orders.MADE, move_id=move_id(pid))
        left = wallet.balance(owner)
    words = {"art": art_name, "style": STYLES.get(style, style), "price": item.price, "left": left}
    line = (WAIT_ART.format(arts="」「".join(a["label"] for a in arts), **words) if arts
            else (LEARNED_BASIC if basic else LEARNED).format(**words))
    return pid, (line + NOT_WORN if taken else line)


def worn(wallet: Wallet, owner: str) -> int:
    """身上穿著哪一招（購買編號；沒有是 0）。同形象：記在帳號那一側，換季也帶著走、跟練哪一門武功無關
    （企劃者 2026-11-02「你那個武學形象是用綁定的呀，這應該跟穿衣服一樣」）。
    還認得舊資料：還沒穿過任何一招的人，拿舊的綁定當他穿著的那一招。"""
    data = wallet.entitlement(owner, WEAR_KIND, WEAR_KEY) or {}
    mine_ = [m for m in mine(wallet, owner) if m.status == orders.MADE]
    if "move" in data:  # 自己穿過、脫過（0 就是脫了，不要再自動穿回去）
        pid = int(data.get("move") or 0)
        return pid if any(m.pid == pid for m in mine_) else 0
    if not mine_:
        return 0
    # 還沒自己動過：舊的綁定優先（2026-11-03 以前的資料），不然就是最早做好的那一招（買了就穿上）
    was_bound = {b.id for b in wallet.purchases(owner) if (b.data or {}).get("bound_art")}
    older = sorted(m.pid for m in mine_ if m.pid in was_bound)
    return older[-1] if older else min(m.pid for m in mine_)  # 最早做好的那一招（purchases 的順序不保證）


def wear(wallet: Wallet, owner: str, pid: int) -> tuple[bool, str]:
    """換上招式庫裡的一招（pid 0 是脫下來）；回（動了沒、那一句）。打法對不對不在這裡擋——
    穿著不對的打法就是不演（view 的 asleep 會寫明白），同形象穿哪一套是自己的事。"""
    now = worn(wallet, owner)
    if pid == 0:
        if not now:
            return False, NOT_MINE
        found = find_mine(wallet, owner, now)
        wallet.set_entitlement(owner, WEAR_KIND, WEAR_KEY, {"move": 0})
        return True, TAKEN_OFF.format(name=found.art_name if found else "")
    found = find_mine(wallet, owner, pid)
    if found is None or found.status != orders.MADE:
        return False, NOT_MINE
    if pid == now:
        return False, WEARING.format(name=found.art_name)
    wallet.set_entitlement(owner, WEAR_KIND, WEAR_KEY, {"move": pid})
    return True, WORN.format(name=found.art_name, style=STYLES.get(found.style, found.style))


def find_mine(wallet: Wallet, owner: str, pid: int) -> Move | None:
    return next((m for m in mine(wallet, owner) if m.pid == pid), None)


def playing(wallet: Wallet, owner: str, style: str) -> str:
    """擂台上這一刻要疊哪一張（m<id>）：身上穿的那一招，而且打法對得上；不然是空字串。"""
    pid = worn(wallet, owner)
    found = find_mine(wallet, owner, pid) if pid else None
    return found.move if found is not None and found.style == style else ""


def find(wallet: Wallet, items, pid: int) -> Move | None:
    return next((m for m in every(wallet, items) if m.pid == pid), None)


def view(content: Content, wallet: Wallet, owner: str, art: str, art_name: str, style: str, season: int) -> dict | None:  # noqa: ARG001
    """萬寶閣「形象」那一頁的絕招：現在練的那一門（自己的才畫得了，下單用）、手上的打法、兩種版本的價錢
    （通用 price_basic：不畫圖、當場學成；獨門 price：畫圖、送出等審核）、招式庫（上架了的，寫身上穿的是哪一招）、訂單。
    穿哪一招跟練哪一門武功無關、換季也帶著走（企劃者 2026-11-02「這應該跟穿衣服一樣」）。"""
    item = item_of(content)
    if item is None:
        return None
    moves = mine(wallet, owner)
    on = worn(wallet, owner)

    def row(m: Move) -> dict:
        mine_now = m.pid == on
        asleep = mine_now and m.style != style  # 穿著，但手上的兵器換了打法：擂台上不會演
        return {"id": m.pid, "move": m.move, "art": m.art_name, "style": m.style, "style_text": STYLES.get(m.style, m.style),
                "prompt": m.prompt, "status": m.status, "status_text": orders.STATUS_TEXT[m.status], "reason": m.reason,
                "withdraw": m.status in orders.CAN_WITHDRAW,
                "scene": m.scene is not None, "arts": [a["label"] for a in scenes.needs_art(m.scene or {})],
                "worn": mine_now, "plays": mine_now and not asleep, "asleep": asleep,
                "asleep_text": ASLEEP.format(want=STYLES.get(m.style, m.style), have=STYLES.get(style, style)) if asleep else "",
                "wearable": m.status == orders.MADE and not mine_now}
    cheap = item_of(content, True)
    rows = [row(m) for m in moves if m.status == orders.MADE]
    return {
        "price": item.price, "price_basic": cheap.price if cheap is not None else 0,
        "prompt_max": scenes.MAX_TEXT, "art": art_name, "has_art": bool(art),
        "style": style, "style_text": STYLES.get(style, style),
        "order_style_note": ORDER_STYLE.format(style=STYLES.get(style, style)),
        "asleep_text": next((r["asleep_text"] for r in rows if r["asleep"]), ""),
        "worn": next((r["art"] for r in rows if r["worn"]), ""),  # 身上穿的那一招（寫字用）
        "open": any(m.status in (orders.PENDING, orders.REVIEW) for m in moves),  # 獨門一次只能有一張在做
        "library": rows,
        "list": [row(m) for m in moves if m.status != orders.MADE],
    }


def missing(m: Move, root: Path) -> list[str]:
    """這一招還缺哪幾張圖：一句話自創的是導演稿要畫的那幾樣（art1、art2），舊的光效單是那一張 fx。"""
    need = [a["slot"] for a in scenes.needs_art(m.scene)] if m.scene is not None else [SHEET]
    return [slot for slot in need if orders.sheet_file(root, move_id(m.pid), slot) is None]


def mark(wallet: Wallet, m: Move, root: Path) -> Move:
    if m.status == orders.PENDING and not missing(m, root):
        wallet.update_data(m.pid, status=orders.REVIEW)
        return Move(**{**m.__dict__, "status": orders.REVIEW})
    return m


def release(wallet: Wallet, m: Move, root: Path) -> str:
    if m.status in (orders.MADE, orders.REJECTED):
        return f"（「{m.art_name}」的招式{orders.STATUS_TEXT[m.status]}了。）"
    if missing(m, root):
        return f"（「{m.art_name}」的招式還沒有圖。）"
    wallet.update_data(m.pid, status=orders.MADE, move_id=move_id(m.pid))
    return f"「{m.art_name}」的招式上架了。"


ART_PX = 1024  # 法相、巨物那一張最大多少（邊長）


def art_problem(m: Move, slot: str, data: bytes) -> str | None:
    """一句話自創的那幾張：只收導演稿要的格子（art1、art2），PNG 或 WebP、邊長不超過 ART_PX。舊的光效單照 sheet_problem。"""
    if m.scene is None:
        return sheet_problem(slot, data)
    want = {a["slot"]: a["label"] for a in scenes.needs_art(m.scene)}
    if slot not in want:
        return f"這一招只要{'、'.join(f'{k}（{v}）' for k, v in want.items()) or '不用畫圖'}。"
    if len(data) > orders.MAX_BYTES:
        return f"「{want[slot]}」太大了。"
    size = orders.image_size(data)
    if size is None:
        return f"「{want[slot]}」要是 PNG 或 WebP。"
    if max(size[1:]) > ART_PX:
        return f"「{want[slot]}」邊長最多 {ART_PX}，這張是 {size[1]}×{size[2]}。"
    return None


def sheet_problem(sheet: str, data: bytes) -> str | None:
    if sheet != SHEET:
        return f"招式動畫只收一張「{SHEET}」。"
    if len(data) > orders.MAX_BYTES:
        return f"「{SHEET}」太大了。"
    size = orders.image_size(data)
    if size is None:
        return f"「{SHEET}」要是 PNG 或 WebP。"
    if size[1:] != (FRAMES * orders.CELL, orders.CELL):
        return f"「{SHEET}」要 {FRAMES * orders.CELL}×{orders.CELL}（{FRAMES} 格，透明底），這張是 {size[1]}×{size[2]}。"
    return None


def fake_generate(root: Path, mid: str, sample: Path) -> None:
    """假的生圖器（TIANXIA_LOOK_GEN=fake）：抄範例的那一張光效。"""
    if sample.is_file():
        target = orders.folder(root, mid)
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sample, target / f"{SHEET}.webp")


def gen_prompt(m: Move) -> str:
    """給生圖工具的提示詞：一張六格的光效，透明底，疊在出招的人身上（人不要畫）。"""
    return (
        "Style: soft ink-wash watercolor energy effect, Chinese wuxia, same palette as the attached reference sprite sheet.\n"
        f"Draw ONLY the visual effect of a martial arts move described by the player as: \"{m.prompt}\" "
        f"(attack style: {m.style}). Do NOT draw any person, weapon, ground or text.\n"
        "Sprite sheet: 6 frames in one row, each frame square, TRANSPARENT background. The effect plays during a side-view attack "
        "facing right, centred where the attacker's fists are (lower-middle of each frame): 1 gathering, 2 building, 3 release, "
        "4 strongest, 5 fading trail, 6 almost gone. Aspect 6:1."
    )
