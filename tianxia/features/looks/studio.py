"""畫坊：自動生圖、審圖、修圖（功能包 looks；Joy 2026-11-01「我現在就要一步到位…現在 Claude 也會幫忙審圖跟微調要修正，之後自動該怎麼辦」，
同日審圖選了 Claude）。這一支是純流程：要畫的、怎麼叫、審過了怎麼收，都在這裡；真的去叫 Nano Banana 與 Claude 的是 studio_api.py，
去背切格是 cutting.py，跑起來的是根目錄的 run_studio.py（跟 server.py、run_bots.py 一起開著）。不讀時鐘。

一張圖怎麼做（work）：
1. 叫生圖的畫一張（提示詞＋參考圖：擂台斗笠小子那一套是格式與畫風，自建形象另外附這一套的定裝照）。
2. 去背、切格（cutting）；切不出來就當作沒畫好。
3. 叫審圖的照清單看（CHECK_*）：東西對不對、格數、同一個人、沒有字、沒有色情血腥商標名人……；回過不過、哪裡不對（中文，寫給管理者）、
   怎麼改（英文，寫給生圖的）。
4. 沒過：把上一張和「怎麼改」丟回去叫生圖的照著改，最多 MAX_TRIES 張。還是不過就記在訂單上（data.studio.failed），停手等管理者：
   管理者可以自己上傳、退回（元寶全退），或按「再畫一次」（retry）清掉重來。
過了的照管理者上傳那一條收（save_sheet、mark）：到齊了變「待審」，上架照舊是管理者按（Joy 10/31 定的管理者上架）。

一個訂單一次只做一張（jobs 回每張訂單下一張要畫的），程式每一輪只做一張：一張圖要叫好幾次外部服務，慢、而且要錢。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from tianxia.models import Content
from tianxia.wallet import Wallet

from . import moves, orders, scenes

MAX_TRIES = 3  # 一張最多畫幾次（第一次＋照審圖的意見改兩次）
PORTRAIT = "ref"  # 自建形象的定裝照（十張都照它畫同一個人；放在那一套的資料夾，不是十張之一，不上架）
GRAY = (128, 128, 128)  # 給審圖看的時候透明的地方鋪成灰的

ASPECT = {(4, 1): "4:1", (3, 1): "21:9", (3, 2): "3:2", (4, 2): "16:9"}  # 一張的排法（cutting.LAYOUT）→ 生圖的長寬比
LAYOUT = {  # 同 cutting.LAYOUT（這支不 import cutting：伺服器的管理者頁也讀 studio，不能拉進 numpy）
    "hero_bare_idle": (4, 1), "hero_bare_hit": (3, 1), "hero_bare_kneel": (4, 1), "hero_bare_dodge": (4, 1), "hero_bare_fall": (3, 2),
    "hero_bare_block": (4, 1), "hero_atk_slash": (3, 2), "hero_atk_pole": (3, 2), "hero_atk_fist": (3, 2), "hero_atk_shoot": (3, 2),
    "hero_run": (4, 2), "hero_pickup": (3, 2), "hero_lift": (3, 1), "hero_slash": (3, 2), "hero_meditate": (4, 1), "hero_push": (4, 1),
}


class PaintBusy(Exception):
    """生圖的那邊忙、斷線、逾時：這一張不算失敗，下一輪再來。"""


class PaintBlocked(Exception):
    """生圖的那邊拒畫（安全規則擋下）：算一次沒畫好。"""


class CutError(ValueError):
    """切不出來（cutting 丟的也是這一種的子類或同名的；畫坊一律當作沒畫好）。"""


class CutProblem(CutError):
    """切出來了，但我們自己機械驗就看得出不能用（空格、貼邊、地面線、去背吃掉大半）。

    為什麼獨立一種（Joy 2026-11-02「要把能過的方法模組化，不要每次都重複做一堆」）：這幾樣以前要
    等 Claude 審圖才擋得下來——花一次審圖的錢、而且意見每次寫法不同，人要重新判一輪是生圖的錯
    還是我們切壞的。改成切完就驗（cutting.sheet_problems），壞的當場帶著指定好的改法重畫，
    不叫審圖；過得了這一關的才送 Claude 看「像不像同一個人、有沒有不該有的東西」。
    problems 是寫給管理者看的中文，fix 是丟回生圖的英文一句。"""

    def __init__(self, problems: list[str], fix: str):
        super().__init__("；".join(problems))
        self.problems = problems
        self.fix = fix


@dataclass(frozen=True)
class Verdict:
    ok: bool
    problems: list[str] = field(default_factory=list)  # 中文，寫給管理者看
    fix: str = ""  # 英文，丟回去給生圖的


class Painter(Protocol):
    def paint(self, prompt: str, images: list[bytes], aspect: str, size: str) -> bytes: ...


class Critic(Protocol):
    def review(self, checklist: str, image: bytes, refs: list[bytes]) -> Verdict: ...


@dataclass(frozen=True)
class Job:
    kind: str  # "move"：一句話自創絕招要畫的那幾樣；"look"：自建形象（先定裝照，再十張）
    pid: int
    folder: str  # m<id>／u<id>
    slot: str  # art1、art2；ref；十張的檔名
    label: str  # 寫給管理者看的（大佛、定裝照、hero_atk_slash……）
    prompt: str
    checklist: str
    aspect: str
    size: str
    refs: tuple[Path, ...]


@dataclass(frozen=True)
class Result:
    ok: bool
    image: bytes = b""  # 切好、可以收的那一張
    raw: bytes = b""  # 生圖給的原圖（定裝照收原圖：拿它當之後十張的參考）
    painted: int = 0  # 這一張叫了生圖幾次（算錢）
    problems: list[str] = field(default_factory=list)


# ── 提示詞與清單 ─────────────────────────────

ART_STYLE = ("Style: soft ink-wash watercolor, Chinese wuxia, glowing, same palette and brushwork as the attached arena sprite "
             "(the attached image is only a style reference; do not draw that character).")
PORTRAIT_PROMPT = (
    "{style}\nCharacter design (定裝照) for a 2D fighting sprite: ONE chibi child martial artist (big head about one third of body "
    "height), same proportions, size and drawing style as the attached reference sprite, described by the player as: \"{text}\".\n"
    "Full body, side view facing right, idle fighting stance, fists loosely closed, holding NO weapon and NO object. "
    "Pure white background, no ground shadow, no text, no frame border.\n"
    # 清單（CHECK_PORTRAIT）要求「full body, nothing cut off」：定裝照也要講明留白，不然髮飾一高就被上緣裁掉
    "The whole character must be inside the frame, with a clear empty margin above the hair and below the feet."
)
SHEET_EXTRA = ("The FIRST attached image is the layout and pose reference (same frame count, same poses, same character size). "
               "The SECOND attached image is this character's design: keep exactly the same face, hair, clothes and colors in every frame.")
FIX_PROMPT = ("Edit the attached image (the first one) to fix these problems: {fix}\n"
              "Keep everything else the same. The original instructions were:\n{prompt}")

CHECK_COMMON = (
    "Also fail it for: any text, letters, numbers, watermark or signature; nudity or sexual content; blood or gore; logos or brands; "
    "a real person's likeness; a well-known character from another game, film, anime or novel; modern objects."
)
CHECK_ART = (
    "This image is ONE element of a wuxia special move in a 2D game, cut out from its background (cut-out areas are shown as flat "
    "gray). It must show 「{label}」 for a move the player described as 「{text}」.\n"
    "Pass it only if: it is one clear subject that reads as 「{label}」; it fills the image (nothing important is cut off at the edges); "
    "the cut-out is clean (no leftover white background blobs, no halo); soft ink-wash watercolor style like the reference sprite; "
    "no person, no ground. " + CHECK_COMMON
)
CHECK_PORTRAIT = (
    "This is a character design for a chibi 2D fighting sprite, on a white background. The player described it as 「{text}」.\n"
    "Pass it only if: exactly one character, full body, nothing cut off; side view facing right; chibi proportions (head about one "
    "third of the height) like the reference sprite; it matches the description; holds no weapon or object; soft ink-wash watercolor "
    "style like the reference. " + CHECK_COMMON
)
# 動作比對放寬（Joy 2026-11-02 選的）：原本要求「逐格照參考圖的姿勢」，出招那四張因此一直過不了——
# 2026-11-02 #3 的理由是「第2格雙拳未併攏舉至右肩上方」「第5格不是低位收勢」這種逐格手部位置，
# 而六格的出招圖要生圖穩定對準手的位置本來就做不到。硬規則全留（格數、整個人在框內、同一個人、
# 沒有武器、側面向右、腳在同一條線），只把姿勢那一句改成「整串讀起來是那個動作、順序對」。
# 「沒有武器」也補一句：寬袖、飄帶、長髮不算東西——魔教聖女的紅袖一揚就被判成「手持紅布或刀刃」。
GEAR_NONE = "holds no weapon or object (loose sleeves, ribbons, sashes and long hair are not objects)"
GEAR_SWORD = ("carries one plain straight sword like reference 1 (at the hip, or in hand when the action draws it) and no other "
              "weapon; a small found item in the hands is fine where reference 1 has one")
CHECK_SHEET = (
    "This is an animation strip for a 2D fighting game: {frames} frames side by side, each 220×220, cut out from the background "
    "(cut-out areas are flat gray). The action should be: {action}\n"
    "Reference 1 is the same animation drawn for another character (layout and overall action to follow). Reference 2 is this "
    "character's design.\nPass it only if: exactly {frames} frames, one whole character in each (no frame empty, cut in half, or "
    "holding two characters); it is the same character as reference 2 in every frame (face, hair, clothes, colors); the frames read "
    "as the action above and run in the same order as reference 1 — small differences in limb position are fine, judge the action as "
    "a whole, not frame by frame; side view facing right; {gear}; feet roughly on the same ground line.\n"
    # 校準（2026-11-02）：審圖連去背留下的 1～2 像素白邊都當成「白色毛絨狀雜物」擋下來，但量過了——
    # 那種邊緣佔實心像素的 0.0～0.2%，預設的斗笠小子（同一條去背管線切的）與這一套已經過審的六張
    # 都在同一個量級。所以要寫明比較的基準是斗笠小子，不是乾淨的向量圖。
    "The strip was cut out automatically, so a one or two pixel pale edge along the outline is normal — the default "
    "hat-boy sprites have the same. Judge it at normal viewing size: ignore single-pixel fringes and faint edge "
    "halos, and only fail the cut-out if a whole limb or a large area is missing, see-through or buried in leftover "
    "background. " + CHECK_COMMON
)


def art_prompt(text: str, art: dict) -> str:
    """法相、巨物那一張給生圖的（同 scenes.art_prompt，底改成純白：生圖的畫不出透明，畫坊自己去背）。"""
    return (f"{ART_STYLE}\nDraw ONE subject only: 「{art['label']}」, from a martial arts move the player described as 「{text}」.\n"
            "It appears huge on screen as a spirit/manifestation (法相) or a giant thrown object. Front view, centred, fills the "
            "frame. Pure white background, no ground, no text, no other characters.")


# ── 要畫的 ───────────────────────────────────


def _failed(data: dict) -> bool:
    return bool((data.get("studio") or {}).get("failed"))


def jobs(content: Content, wallet: Wallet, root: Path, web_img: Path) -> list[Job]:
    """每張還在等圖、畫坊沒放棄的訂單，下一張要畫的（舊的訂單在前）。"""
    out: list[Job] = []
    arena = web_img / "arena"
    move_item = moves.item_of(content)
    if move_item is not None:
        for b in wallet.purchases_of(move_item.id):
            m = moves.of(b)
            if m is None or m.status != orders.PENDING or m.scene is None or _failed(b.data):
                continue
            mid = moves.move_id(m.pid)
            gone = moves.missing(m, root)
            art = next((a for a in scenes.needs_art(m.scene) if a["slot"] in gone), None)
            if art is None:
                continue
            out.append(Job(kind="move", pid=m.pid, folder=mid, slot=art["slot"], label=art["label"],
                           prompt=art_prompt(m.prompt, art), checklist=CHECK_ART.format(label=art["label"], text=m.prompt),
                           aspect="1:1", size="1K", refs=(arena / "hero_bare_idle.webp",)))
    look_item = orders.item_of(content)
    if look_item is not None:
        for b in wallet.purchases_of(look_item.id):
            o = orders.of(b)
            # 等圖的照順序畫；審核中、上架了的只補走一趟那幾張（2026-11-02 加的，之前做好的少這幾張）
            if o is None or o.status not in (orders.PENDING, orders.REVIEW, orders.MADE) or _failed(b.data):
                continue
            look = orders.look_id(o.pid)
            portrait = orders.folder(root, look) / f"{PORTRAIT}.png"
            if not portrait.is_file():  # 沒有定裝照（管理者手動上傳的那幾套）：拿它自己站著那一張當這個人的樣子
                portrait = orders.sheet_file(root, look, "hero_bare_idle") or portrait
            if not portrait.is_file():
                if o.status != orders.PENDING:
                    continue
                out.append(Job(kind="look", pid=o.pid, folder=look, slot=PORTRAIT, label="定裝照",
                               prompt=PORTRAIT_PROMPT.format(style=orders.BASE_STYLE, text=o.prompt),
                               checklist=CHECK_PORTRAIT.format(text=o.prompt), aspect="3:4", size="1K",
                               refs=(arena / "hero_bare_idle.webp",)))
                continue
            have = orders.present(root, look)
            sheet = next((s for s in orders.SHEETS if s not in have and (o.status == orders.PENDING or s in orders.OUTING)), None)
            if sheet is None:
                continue
            out.append(Job(kind="look", pid=o.pid, folder=look, slot=sheet, label=sheet,
                           prompt=f"{orders.gen_prompts(o)[sheet]}\n{SHEET_EXTRA}",
                           checklist=CHECK_SHEET.format(frames=orders.SHEETS[sheet], action=orders.ACTIONS[sheet],
                                                        gear=GEAR_SWORD if sheet in orders.OUTING else GEAR_NONE),
                           aspect=ASPECT[LAYOUT[sheet]], size="2K", refs=(orders.reference(web_img, sheet), portrait)))
    return out


# ── 畫一張 ───────────────────────────────────


def cut_for(job: Job, raw: bytes, cutting) -> bytes:
    """照這一張是什麼去背、切格（cutting 是 cutting.py 那個模組：畫坊程式傳進來，這支不 import numpy）。"""
    if job.slot == PORTRAIT:
        cutting.art_bytes(raw)  # 只驗切得出一個人；收的是白底的原圖（給之後十張當參考）
        return raw
    if job.kind == "move":
        return cutting.art_bytes(raw)
    return cutting.sheet_bytes(raw, job.slot)


def work(job: Job, painter: Painter, critic: Critic, cut: Callable[[Job, bytes], bytes]) -> Result:
    """畫、切、審，沒過照意見改，最多 MAX_TRIES 張。生圖那邊忙（PaintBusy）照丟出去：這一張不算，下一輪再來。"""
    refs = [p.read_bytes() for p in job.refs if p.is_file()]
    raw = b""
    problems: list[str] = []
    for n in range(1, MAX_TRIES + 1):
        try:
            if n == 1:
                raw = painter.paint(job.prompt, refs, job.aspect, job.size)
            else:
                raw = painter.paint(FIX_PROMPT.format(fix=verdict.fix or "redraw it following the instructions", prompt=job.prompt),
                                    [raw, *refs], job.aspect, job.size)
        except PaintBlocked as exc:
            problems = [f"生圖的拒畫（{exc}）"]
            return Result(ok=False, painted=n, problems=problems)
        try:
            image = cut(job, raw)
        except CutProblem as exc:  # 我們自己驗出來的：帶著指定好的改法重畫，不花審圖的錢
            verdict = Verdict(False, exc.problems, exc.fix)
        except (CutError, ValueError) as exc:
            verdict = Verdict(False, [f"切不出來：{exc}"], "Draw the subject(s) clearly on a pure white background, "
                                                              "well separated, nothing touching the edges.")
        else:
            verdict = critic.review(job.checklist, image if job.slot != PORTRAIT else raw, refs)
            if verdict.ok:
                return Result(ok=True, image=image, raw=raw, painted=n)
        problems = verdict.problems or ["審圖沒過"]
    return Result(ok=False, raw=raw, painted=MAX_TRIES, problems=problems)


# ── 收 ───────────────────────────────────────


def apply(content: Content, wallet: Wallet, root: Path, job: Job, result: Result) -> str:
    """畫好的收下（照管理者上傳那一條：驗格式、存、到齊了變待審）；沒畫好記在訂單上。呼叫端包在行動鎖裡。回一句給主控台。
    訂單在畫的時候被退回、上傳齊了，就什麼都不動。"""
    b = wallet.purchase(job.pid)
    if b is None:
        return f"#{job.pid} 不見了"
    found = moves.of(b) if job.kind == "move" else orders.of(b)
    backfill = job.kind == "look" and job.slot in orders.OUTING and found is not None and found.status in (orders.REVIEW, orders.MADE)
    if found is None or (found.status != orders.PENDING and not backfill):
        return f"#{job.pid} 已經不在等圖（{orders.STATUS_TEXT.get(found.status, '') if found else ''}）"
    studio = dict(b.data.get("studio") or {})
    studio["painted"] = int(studio.get("painted", 0)) + result.painted
    if not result.ok:
        studio["failed"] = f"{job.label}：{'；'.join(result.problems)}"[:300]
        wallet.update_data(job.pid, studio=studio)
        return f"#{job.pid} {job.label} 沒畫好，停手等管理者：{studio['failed']}"
    if job.slot == PORTRAIT:
        target = orders.folder(root, job.folder)
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{PORTRAIT}.png").write_bytes(_png(result.raw))
        wallet.update_data(job.pid, studio=studio)
        return f"#{job.pid} 定裝照好了"
    problem = moves.art_problem(found, job.slot, result.image) if job.kind == "move" else orders.sheet_problem(job.slot, result.image)
    if problem:
        studio["failed"] = f"{job.label}：{problem}"
        wallet.update_data(job.pid, studio=studio)
        return f"#{job.pid} {job.label} 格式不對，停手等管理者：{problem}"
    orders.save_sheet(root, job.folder, job.slot, result.image)
    wallet.update_data(job.pid, studio=studio)
    now = moves.mark(wallet, moves.of(wallet.purchase(job.pid)), root) if job.kind == "move" else \
        orders.mark(wallet, orders.of(wallet.purchase(job.pid)), root)
    return f"#{job.pid} {job.label} 收了" + ("，到齊了等管理者上架" if now.status == orders.REVIEW else "")


def _png(raw: bytes) -> bytes:
    """定裝照存成 PNG（生圖的可能給 JPEG；轉檔要 Pillow，畫坊程式那邊一定有）。"""
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return raw
    import io  # noqa: PLC0415

    from PIL import Image  # noqa: PLC0415

    out = io.BytesIO()
    Image.open(io.BytesIO(raw)).convert("RGB").save(out, "PNG")
    return out.getvalue()


def retry(wallet: Wallet, pid: int) -> bool:
    """管理者按「再畫一次」：清掉畫坊的放棄，下一輪從缺的那一張重來（花了多少照記著）。"""
    b = wallet.purchase(pid)
    if b is None or not _failed(b.data):
        return False
    studio = dict(b.data.get("studio") or {})
    studio.pop("failed", None)
    wallet.update_data(pid, studio=studio)
    return True


def note(data: dict) -> dict:
    """管理者頁看的：畫坊畫了幾張、放棄的原因。"""
    studio = data.get("studio") or {}
    return {"painted": int(studio.get("painted", 0)), "failed": str(studio.get("failed", ""))}


def tick(content: Content, store, root: Path, web_img: Path, painter: Painter, critic: Critic,
         cut: Callable[[Job, bytes], bytes], *, budget: int = 1) -> list[str]:
    """畫坊巡一輪：做最多 budget 張（每張最多叫 MAX_TRIES 次生圖）。畫在鎖外（慢），收在行動鎖裡（同伺服器的一個動作）。
    store 是 open_world() 那個（有 db、action_lock）。回幾句給主控台。"""
    wallet = Wallet(store.db)
    lines: list[str] = []
    for job in jobs(content, wallet, root, web_img)[:max(0, budget)]:
        try:
            result = work(job, painter, critic, cut)
        except PaintBusy as exc:
            lines.append(f"#{job.pid} {job.label} 生圖的那邊忙，下一輪再來（{exc}）")
            continue
        with store.action_lock():
            lines.append(apply(content, wallet, root, job, result))
    return lines
