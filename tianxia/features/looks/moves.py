"""招式動畫（功能包 looks 第三批；Joy 2026-10-31「自創完武學時，玩家也可以選擇建立武學攻擊的模型」、設計 v3 第三期）。純規則，不讀時鐘。

一個招式動畫是一張六格的光效（fx，1320×220，透明底），出招時疊在人身上（不管穿哪一套形象都疊得上去）。
- 下單：替自己現在練的武功（自己合成或自創的，不是內容裡的）寫一句樣子，扣元寶（購買那一列就是訂單，同自建形象）。打法照下單那一刻
  手上的兵器（揮砍、長兵、拳腳、射）。
- 上架了放進「招式庫」：帳號的，換季也帶著走（Joy「花錢買的東西不能不見」）。武學每季歸零，所以每一季要把招式重新綁到自己的一門武功上；
  同一種打法免費改綁（設計 v3），換打法要重畫（這一版不做，要重新下單）。
- 擂台：上擂台那一刻（報名、更新分身、挑人），身上的武功綁了招式、手上的打法也對得上，出招就疊那一張光效。

訂單的狀態同 orders.py（pending／review／made／rejected）；上架了 data 記 move_id＝m<購買 id>，綁定記 bound_art、bound_name、bound_season。
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from tianxia import speech  # 過渡：待搬（玩家寫的字過字表）
from tianxia.models import Content, MallItem
from tianxia.wallet import Purchase, Wallet

from . import orders, scenes

EFFECT = "move_order"
PREFIX = "m"
SHEET, FRAMES = "fx", 6
STYLES = {"slash": "揮砍", "pole": "長兵", "fist": "拳腳", "shoot": "射"}
KIND_STYLE = {"劍": "slash", "刀": "slash", "槍": "pole", "棍": "pole", "弓弩": "shoot", "拳腳": "fist"}  # 同 web/arena_anim.js 的 RING_ARMS

# 待 joy 潤
NOT_SOLD = "招式動畫還沒開賣。"
NO_ART = "先練一門自己合成或自創的武功，才能替它畫招式。"
NO_PROMPT = "寫一句這一招長什麼樣子。"
OPEN_ORDER = "你還有一張招式動畫在做，等它好了再下一張。"
ALREADY = "「{art}」這一種打法已經綁了招式。"
SHORT = "元寶不夠：招式動畫要 {price}，你有 {balance}。"
PLACED = "替「{art}」下單了招式動畫（{style}）：元寶 -{price}（還剩 {left}）。做好、審核過了會放進招式庫。"
LEARNED = "「{art}」的絕招學成了（{style}）：元寶 -{price}（還剩 {left}）。擂台上這一招發動時就照這樣演。"
WAIT_ART = "替「{art}」下單了絕招（{style}）：元寶 -{price}（還剩 {left}）。要畫的「{arts}」畫好、審過了就放進招式庫；沒過元寶全退。"
DUPLICATE = "這一張已經下過單了。"
BOUND = "把招式綁到「{art}」上了（這一季）。"
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
    bound_art: str
    bound_name: str
    bound_season: int
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
                bound_art=str(d.get("bound_art", "")), bound_name=str(d.get("bound_name", "")), bound_season=int(d.get("bound_season", 0)),
                scene=d.get("scene") if isinstance(d.get("scene"), dict) else None)


def mine(wallet: Wallet, owner: str) -> list[Move]:
    return [m for m in (of(b) for b in wallet.purchases(owner)) if m is not None]


def every(wallet: Wallet, item: str) -> list[Move]:
    return [m for m in (of(b) for b in wallet.purchases_of(item)) if m is not None]


def item_of(content: Content) -> MallItem | None:
    return next((i for i in content.mall.values() if i.effects.get(EFFECT)), None)


def place(
    content: Content, wallet: Wallet, owner: str, art: str, art_name: str, style: str, prompt: str, ref: str, *,
    now: float, day: int, season: int, move_name: str = "",
) -> tuple[int | None, str]:
    """下單（同 orders.place 的那幾步）。art 是呼叫端驗過的、自己合成或自創的武功（空字串是沒有）。
    prompt 是玩家寫的一句（scenes.MAX_TEXT 字內、只能中文），當場變成導演稿（scenes.direct）存在這一列；
    稿裡沒有要畫的就當場上架（學成），有要畫的（法相、巨物）等管理者上傳那幾張、審過再上架。move_name 是落款寫的招名。"""
    item = item_of(content)
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
        if any(m.status in (orders.PENDING, orders.REVIEW) for m in moves):
            return None, OPEN_ORDER
        # 同一門武功、同一種打法只能一招；不同打法各一招（換了兵器原本那一招不會演，要能再下一張，Joy 2026-11-02）
        if any(m.status == orders.MADE and m.bound_art == art and m.bound_season == season and m.style == style for m in moves):
            return None, ALREADY.format(art=art_name)
        balance = wallet.balance(owner)
        if balance < item.price:
            return None, SHORT.format(price=item.price, balance=balance)
        scene = scenes.direct(prompt, move_name or art_name)
        arts = scenes.needs_art(scene)
        data = {EFFECT: 1, "art": art, "art_name": art_name, "style": style, "prompt": prompt, "status": orders.PENDING,
                "bound_art": art, "bound_name": art_name, "bound_season": season, "scene": scene}
        pid = wallet.add_purchase(owner, full, item.id, item.price, time=now, day=day, season=season, data=data)
        if not wallet.post(owner, -item.price, "buy", full, time=now, purchase_id=pid):
            raise RuntimeError(f"購買編號 {full} 已經記過帳，購買紀錄卻沒有")
        if not arts:  # 不用畫：當場學成
            wallet.update_data(pid, status=orders.MADE, move_id=move_id(pid))
        left = wallet.balance(owner)
    words = {"art": art_name, "style": STYLES.get(style, style), "price": item.price, "left": left}
    return pid, (WAIT_ART.format(arts="」「".join(a["label"] for a in arts), **words) if arts else LEARNED.format(**words))


def bind(wallet: Wallet, owner: str, pid: int, art: str, art_name: str, style: str, season: int) -> tuple[bool, str]:
    """把招式庫的一招綁到這一季的一門武功上（同一種打法免費）；同一門武功原本綁的那一招鬆開。"""
    moves = mine(wallet, owner)
    target = next((m for m in moves if m.pid == pid and m.status == orders.MADE), None)
    if target is None:
        return False, NOT_MINE
    if not art:
        return False, NO_ART
    if target.style != style:
        return False, WRONG_STYLE.format(want=STYLES.get(target.style, target.style), have=STYLES.get(style, style))
    with wallet.db.transaction():
        for m in moves:
            if m.pid != pid and m.status == orders.MADE and m.bound_art == art and m.bound_season == season and m.style == target.style:
                wallet.update_data(m.pid, bound_art="", bound_name="", bound_season=0)
        wallet.update_data(pid, bound_art=art, bound_name=art_name, bound_season=season)
    return True, BOUND.format(art=art_name)


def bound(wallet: Wallet, owner: str, art: str, style: str, season: int) -> str:
    """這一季綁在 art 上、打法對得上的那一招（m<id>）；沒有是空字串。"""
    if not art:
        return ""
    for m in mine(wallet, owner):
        if m.status == orders.MADE and m.bound_art == art and m.bound_season == season and m.style == style:
            return m.move
    return ""


def find(wallet: Wallet, item: str, pid: int) -> Move | None:
    return next((m for m in every(wallet, item) if m.pid == pid), None)


def view(content: Content, wallet: Wallet, owner: str, art: str, art_name: str, style: str, season: int) -> dict | None:
    """萬寶閣「形象」那一頁的招式動畫：現在練的那一門（自己的才畫得了）、手上的打法、招式庫（上架了的，寫綁在哪）、訂單。"""
    item = item_of(content)
    if item is None:
        return None
    moves = mine(wallet, owner)

    def row(m: Move) -> dict:
        here = m.bound_season == season and bool(m.bound_art)
        on_art = here and m.bound_art == art
        # 綁在現在練的那一門上，但手上的打法對不上：擂台上根本不會演（actions.move_of → bound()），畫面要講明白
        asleep = on_art and m.style != style
        return {"id": m.pid, "move": m.move, "art": m.art_name, "style": m.style, "style_text": STYLES.get(m.style, m.style),
                "prompt": m.prompt, "status": m.status, "status_text": orders.STATUS_TEXT[m.status], "reason": m.reason,
                "scene": m.scene is not None, "arts": [a["label"] for a in scenes.needs_art(m.scene or {})],
                "bound": m.bound_name if here else "", "on_art": on_art,
                "plays": on_art and not asleep, "asleep": asleep,
                "asleep_text": ASLEEP.format(want=STYLES.get(m.style, m.style), have=STYLES.get(style, style)) if asleep else "",
                "bindable": m.status == orders.MADE and bool(art) and m.style == style and not on_art}
    return {
        "price": item.price, "prompt_max": scenes.MAX_TEXT, "art": art_name, "has_art": bool(art),
        "style": style, "style_text": STYLES.get(style, style),
        "open": any(m.status in (orders.PENDING, orders.REVIEW) for m in moves),
        "order_style_note": ORDER_STYLE.format(style=STYLES.get(style, style)),
        "asleep_text": next((ASLEEP.format(want=STYLES.get(m.style, m.style), have=STYLES.get(style, style))
                             for m in moves
                             if m.status == orders.MADE and art and m.bound_art == art
                             and m.bound_season == season and m.style != style), ""),
        "bound": any(m.status == orders.MADE and m.bound_art == art and m.bound_season == season and m.style == style
                     for m in moves) if art else False,
        "library": [row(m) for m in moves if m.status == orders.MADE],
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
