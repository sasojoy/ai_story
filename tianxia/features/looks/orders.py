"""自建形象的訂單（功能包 looks 第二批；Joy 2026-10-31「誰跟你等金流好才開工…繼續優化這邊」、設計 v3 第二期）。純規則，不讀時鐘。

流程：玩家在萬寶閣「形象」那一頁寫名字與一句樣子下單（place：扣元寶、記一筆購買，那一列就是訂單）→ 生圖（gen.py：預設關著等管理者
上傳；開發可以用假的生圖器）→ 十張都到了變成「待審」→ 管理者看過上架（release：那一列的 data 記 look_id＝u<購買 id>，從此就是買到的一套，
帳號的、換季也帶著走）或退回（reject：元寶全退，那一列記退了）。

訂單的狀態記在購買那一列的 data（status）：
- pending：等圖（十張還沒齊）
- review：十張齊了，等管理者看
- made：上架了（data.look_id）
- rejected：退回了（元寶退了，data.reason 寫原因）

圖放在資料庫旁邊的 looks/<id>/（不進版控；伺服器的 /api/looks/img/<id>/<張> 照它送），十張的檔名與格數同預設的斗笠小子。
"""
from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from tianxia import naming
from tianxia import speech  # 過渡：待搬（玩家寫的字過字表；名帖、挑釁同一道）
from tianxia.models import Content, MallItem
from tianxia.wallet import Purchase, Wallet

EFFECT = "look_order"
PREFIX = "u"  # 自建形象的 id：u<購買 id>（官方的寫在 content/looks.json，只有小寫英數；不會撞）
CELL = 220
SHEETS = {  # 一套十張：檔名 → 格數（每格 220×220，腳底在 (100, 212)；同 web/arena_anim.js 的 RING_SHEETS）
    "hero_bare_idle": 4, "hero_bare_hit": 3, "hero_bare_kneel": 4, "hero_bare_dodge": 4, "hero_bare_fall": 6, "hero_bare_block": 4,
    "hero_atk_slash": 6, "hero_atk_pole": 6, "hero_atk_fist": 6, "hero_atk_shoot": 6,
}
NAME_MAX, PROMPT_MAX = 6, 120
MAX_BYTES = 2_000_000  # 一張最大多少（上傳那一道）
PENDING, REVIEW, MADE, REJECTED = "pending", "review", "made", "rejected"
STATUS_TEXT = {PENDING: "等圖中", REVIEW: "審核中", MADE: "已上架", REJECTED: "退回"}  # 待 joy 潤

# 待 joy 潤
NO_NAME = "先替這一套取個名字。"
NAME_LONG = "名字最多 {n} 個字。"
NAME_TAKEN = "已經有一套叫「{name}」的形象了，換個名字。"
NO_PROMPT = "寫一句這一套長什麼樣子。"
OPEN_ORDER = "你還有一張自建形象在做，等它好了再下一張。"
SHORT = "元寶不夠：自建形象要 {price}，你有 {balance}。"
PLACED = "下單了「{name}」：元寶 -{price}（還剩 {left}）。圖做好、審核過了，就會出現在「形象」這一頁。"
DUPLICATE = "這一張已經下過單了。"
NOT_SOLD = "自建形象還沒開賣。"


@dataclass(frozen=True)
class Order:
    pid: int
    owner: str
    name: str
    prompt: str
    status: str
    reason: str
    look: str  # 上架了的 id（u<購買 id>）；還沒是空字串
    time: float


def look_id(pid: int) -> str:
    return f"{PREFIX}{pid}"


def is_custom(look: str) -> bool:
    return bool(re.fullmatch(rf"{PREFIX}\d+", look or ""))


def of(b: Purchase) -> Order | None:
    d = b.data
    if not d.get(EFFECT):
        return None
    status = REJECTED if b.refunded is not None else str(d.get("status", PENDING))
    return Order(pid=b.id, owner=b.owner, name=str(d.get("name", "")), prompt=str(d.get("prompt", "")), status=status,
                 reason=str(d.get("reason", "")), look=str(d.get("look_id", "")), time=b.time)


def mine(wallet: Wallet, owner: str) -> list[Order]:
    """這個人的訂單（新的在前）。"""
    return [o for o in (of(b) for b in wallet.purchases(owner)) if o is not None]


def every(wallet: Wallet, item: str) -> list[Order]:
    """全服的訂單（舊的在前）：管理者那一頁。"""
    return [o for o in (of(b) for b in wallet.purchases_of(item)) if o is not None]


def names(wallet: Wallet, owner: str) -> dict[str, str]:
    """這個人上架了的自建形象：id → 名字。"""
    return {o.look: o.name for o in mine(wallet, owner) if o.status == MADE and o.look}


def item_of(content: Content) -> MallItem | None:
    """賣自建形象的那一件（content/mall.json 裡效果寫 look_order 的第一件）；沒有就是還沒開賣。"""
    return next((i for i in content.mall.values() if i.effects.get(EFFECT)), None)


def name_problem(content: Content, wallet: Wallet, item: str, name: str) -> str | None:
    if not name:
        return NO_NAME
    if len(name) > NAME_MAX:
        return NAME_LONG.format(n=NAME_MAX)
    problem = naming.name_problem(name, content)
    if problem:
        return problem
    taken = {look.name for look in content.looks.values()} | {o.name for o in every(wallet, item) if o.status != REJECTED}
    return NAME_TAKEN.format(name=name) if name in taken else None


def place(
    content: Content, wallet: Wallet, owner: str, name: str, prompt: str, ref: str, *, now: float, day: int, season: int,
) -> tuple[int | None, str]:
    """下單（同 mall.buy 的那幾步：查重 → 名字與樣子 → 一次一張 → 餘額 → 寫購買紀錄 → 扣元寶，同一筆交易）：回（購買 id、那一句）；
    不成 id 是 None、什麼都不寫。一個人同時只能有一張還沒上架、沒退回的。"""
    item = item_of(content)
    if item is None:
        return None, NOT_SOLD
    name = speech.clean(name)
    prompt = speech.clean(prompt)
    full = f"buy:{owner}:{ref}"
    with wallet.db.transaction():
        if wallet.purchase_by_ref(full) is not None:
            return None, DUPLICATE
        problem = name_problem(content, wallet, item.id, name)
        if problem:
            return None, problem
        if not prompt:
            return None, NO_PROMPT
        problem = speech.word_problem(prompt, content, speech.MOTTO, PROMPT_MAX)
        if problem:
            return None, problem
        if any(o.status in (PENDING, REVIEW) for o in mine(wallet, owner)):
            return None, OPEN_ORDER
        balance = wallet.balance(owner)
        if balance < item.price:
            return None, SHORT.format(price=item.price, balance=balance)
        data = {EFFECT: 1, "name": name, "prompt": prompt, "status": PENDING}
        pid = wallet.add_purchase(owner, full, item.id, item.price, time=now, day=day, season=season, data=data)
        if not wallet.post(owner, -item.price, "buy", full, time=now, purchase_id=pid):
            raise RuntimeError(f"購買編號 {full} 已經記過帳，購買紀錄卻沒有")
        left = wallet.balance(owner)
    return pid, PLACED.format(name=name, price=item.price, left=left)


# ── 圖 ──────────────────────────────────────


def folder(root: Path, look: str) -> Path:
    return root / look


def present(root: Path, look: str) -> list[str]:
    """這一套已經有的那幾張（照 SHEETS 的順序）。"""
    return [s for s in SHEETS if sheet_file(root, look, s) is not None]


def sheet_file(root: Path, look: str, sheet: str) -> Path | None:
    for ext in ("webp", "png"):
        path = folder(root, look) / f"{sheet}.{ext}"
        if path.is_file():
            return path
    return None


def image_size(data: bytes) -> tuple[str, int, int] | None:
    """PNG 或 WebP 的格式與寬高（只讀檔頭，不解圖）；認不得是 None。"""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return "png", int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        kind = data[12:16]
        if kind == b"VP8X":
            return "webp", 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
        if kind == b"VP8L" and data[20] == 0x2F:
            bits = int.from_bytes(data[21:25], "little")
            return "webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if kind == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            return "webp", int.from_bytes(data[26:28], "little") & 0x3FFF, int.from_bytes(data[28:30], "little") & 0x3FFF
    return None


def sheet_problem(sheet: str, data: bytes) -> str | None:
    """上傳的一張哪裡不對；None 是可以收。"""
    if sheet not in SHEETS:
        return f"沒有「{sheet}」這一張（要 {'、'.join(SHEETS)}）。"
    if len(data) > MAX_BYTES:
        return f"「{sheet}」太大了（最多 {MAX_BYTES // 1_000_000} MB）。"
    size = image_size(data)
    if size is None:
        return f"「{sheet}」要是 PNG 或 WebP。"
    want = (SHEETS[sheet] * CELL, CELL)
    if size[1:] != want:
        return f"「{sheet}」要 {want[0]}×{want[1]}（{SHEETS[sheet]} 格，每格 {CELL}），這張是 {size[1]}×{size[2]}。"
    return None


def save_sheet(root: Path, look: str, sheet: str, data: bytes) -> None:
    """存一張（同一張的另一種格式先刪掉，免得送出去的是舊的）。呼叫端先過 sheet_problem。"""
    fmt = image_size(data)[0]
    target = folder(root, look)
    target.mkdir(parents=True, exist_ok=True)
    for ext in ("webp", "png"):
        (target / f"{sheet}.{ext}").unlink(missing_ok=True)
    (target / f"{sheet}.{fmt}").write_bytes(data)


def fake_generate(root: Path, look: str, prompt: str, sources: list[Path]) -> None:
    """假的生圖器（開發與測試用；TIANXIA_LOOK_GEN=fake）：照樣子那一句的雜湊挑一套現成的圖抄過去。不叫任何外部服務。"""
    if not sources:
        return
    pick = sources[int.from_bytes(hashlib.sha256(prompt.encode()).digest()[:4], "big") % len(sources)]
    target = folder(root, look)
    target.mkdir(parents=True, exist_ok=True)
    for sheet in SHEETS:
        src = pick / f"{sheet}.webp"
        if src.is_file():
            shutil.copyfile(src, target / f"{sheet}.webp")


# ── 管理者 ──────────────────────────────────


def find(wallet: Wallet, item: str, pid: int) -> Order | None:
    return next((o for o in every(wallet, item) if o.pid == pid), None)


def mark(wallet: Wallet, order: Order, root: Path) -> Order:
    """十張齊了而且還在等圖：換成待審。回最新的那一張。"""
    if order.status == PENDING and len(present(root, look_id(order.pid))) == len(SHEETS):
        wallet.update_data(order.pid, status=REVIEW)
        return Order(**{**order.__dict__, "status": REVIEW})
    return order


def release(wallet: Wallet, order: Order, root: Path) -> str:
    if order.status == MADE:
        return f"（「{order.name}」已經上架了。）"
    if order.status == REJECTED:
        return f"（「{order.name}」已經退回了。）"
    missing = [s for s in SHEETS if s not in present(root, look_id(order.pid))]
    if missing:
        return f"（「{order.name}」還缺 {len(missing)} 張：{'、'.join(missing)}。）"
    wallet.update_data(order.pid, status=MADE, look_id=look_id(order.pid))
    return f"「{order.name}」上架了，{order.owner}可以換上。"


def reject(wallet: Wallet, order: Order, *, now: float, admin: str, note: str) -> str:
    """退回：元寶全退（編號 refund:<購買>，同商城退款），那一列記退了、原因。上架了的不在這裡退（照商城退款，形象跟著收回）。"""
    note = (note or "").strip()
    if not note:
        return "（要寫原因：會寫給下單的人看。）"
    if order.status in (MADE, REJECTED):
        return f"（「{order.name}」{STATUS_TEXT[order.status]}了，不在這裡退。）"
    bought = wallet.purchase(order.pid)
    with wallet.db.transaction():
        if not wallet.post(order.owner, bought.price, "refund", f"refund:{order.pid}", time=now, admin=admin, note=note,
                           purchase_id=order.pid):
            return "（這一筆已經退過了。）"
        wallet.mark_refunded(order.pid, now)
        wallet.update_data(order.pid, status=REJECTED, reason=note)
    return f"退回了「{order.name}」：元寶 +{bought.price} 退給{order.owner}。"


def gen_prompts(order: Order) -> dict[str, str]:
    """給生圖工具的提示詞（一張一段）：畫風、十張的動作照斗笠小子那一套（擂台圖提示表），人物換成下單的人寫的那一句。
    生好的圖要切成 220 格、腳底對齊（scripts/cut_look.py）再上傳。"""
    character = (f"Character: a chibi child martial artist (big head about one third of body height) described by the player as: "
                 f"\"{order.prompt}\". Keep the same proportions, size and poses as the attached reference sprite sheet.")
    return {sheet: f"{BASE_STYLE}\n{character}\n{RULES}\n\n{ACTIONS[sheet]}" for sheet in SHEETS}


BASE_STYLE = ("Style: soft ink-wash watercolor with warm muted tints, hand-drawn ink outlines, same style as the attached reference "
              "image (Chinese wuxia, Three Kingdoms era).")
# 審圖的清單（studio.CHECK_SHEET）要求「每一格一個完整的人，不能空、不能被切半」，所以這裡要把它講明白：
# 2026-11-02 第一張自建形象連七張都被擋下，理由都是同一類——頭頂（髮髻、髮飾）被畫面上緣裁掉、有一格模糊成殘影、
# 臉與下襬褪色泛白。生圖的提示詞只說了白底、無陰影、腳踩同一條地平線，從來沒說「整個人要留在畫面裡」，
# 也沒禁止殘影與褪色，要求跟指示對不上。下面 FRAMING 就是補這一段（Joy 2026-11-02「我們自己補足玩家給的提示詞」）。
FRAMING = ("The WHOLE character must be inside every frame: the top of the head — including hair, hair ornaments and headdress — "
           "and the feet must not touch or cross the frame edge. Leave a clear empty margin of about one tenth of the frame above "
           "the head and below the feet. Draw a complete, solid character in every frame: no motion blur, no ghosting or "
           "afterimages, no fading, no transparency, no washed-out or half-drawn figures; the face and clothes keep their full "
           "colour in every frame.")
RULES = ("IMPORTANT: the character holds NO weapon and NO object. Hands are closed into loose fists as if gripping an invisible handle. "
         "Sprite sheet rules: pure white background, no ground shadow, NO ground line, no horizon line, no floor or platform, "
         "no text, no numbers, no frame borders. Every frame is the same "
         "size and the character is the same size in every frame. Feet stand on the same horizontal ground line in every frame. "
         "Side view, facing right. " + FRAMING)
ACTIONS = {
    "hero_bare_idle": "Idle fighting stance, gentle breathing loop: 4 frames, right fist held forward at waist height. "
                      "Breathing means the WHOLE body moves straight up and down by roughly a tenth of its height: frame 1 lowest, "
                      "frames 2 and 3 higher, frame 4 back down, so no two frames are the same drawing. Keep exactly the same "
                      "stance, the same facing and the feet in the same place — do NOT lean forward, do not step, do not stretch "
                      "or squash the body, no motion blur. Layout: 4 frames in one row. Aspect 4:1.",
    "hero_bare_hit": "Getting hit: 1 flinch, head snapping back, 2 knocked backward, arms flung out, 3 staggering to regain balance. Layout: 3 frames in one row. Aspect 3:1.",
    "hero_bare_kneel": "Losing and dropping to one knee: 1 wobbling, 2 one knee bending, 3 kneeling, right fist planted on the ground, head down, 4 same pose, breathing hard. Layout: 4 frames in one row. Aspect 4:1.",
    "hero_bare_dodge": "Dodging: 1 stance, 2 quick lean back and sidestep, 3 deepest point of the dodge, low and leaning back, 4 springing back into stance. Layout: 4 frames in one row. Aspect 4:1.",
    "hero_bare_block": "Guarding / blocking: 1 settling into a low, wide defensive stance, 2 both fists raised crossed in front of the chest as if holding a blade sideways to block, 3 bracing against an impact, body pushed slightly back, back foot sliding, 4 holding the guard firmly, eyes on the opponent. Layout: 4 frames in one row. Aspect 4:1.",
    "hero_bare_fall": "Knocked down: 1 big hit, flinching back, 2 knocked back with arms up, 3 stumbling backward, 4 falling backward, 5 lying on the back, 6 lying still (knocked out, no blood). Layout: 6 frames in a 3x2 grid. Aspect 3:2.",
    "hero_atk_slash": "Two-handed overhead slash with an invisible blade: 1 stance, fists together at waist, 2 fists raised over the right shoulder, 3 fists at the top, 4 fast downward diagonal swing, 5 follow-through low in front, 6 returning to stance. Layout: 6 frames in a 3x2 grid. Aspect 3:2.",
    "hero_atk_pole": "Long-weapon attack with an invisible spear, fists one behind the other at hip height: 1 low stance, 2 pulling back, 3 lunging thrust, arms extended, 4 recovering, 5 wide horizontal sweep, 6 back to stance. Layout: 6 frames in a 3x2 grid. Aspect 3:2.",
    "hero_atk_fist": "Unarmed attack (real fists): 1 stance, fists up, 2 stepping in, 3 straight right punch, 4 pulling back, 5 high front kick, 6 landing back into stance. Layout: 6 frames in a 3x2 grid. Aspect 3:2.",
    "hero_atk_shoot": "Shooting an invisible crossbow: 1 stance, 2 raising fists to the right shoulder, 3 aiming, 4 the shot with small recoil, 5 lowering, 6 back in stance. Layout: 6 frames in a 3x2 grid. Aspect 3:2.",
}
