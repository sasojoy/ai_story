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

import hashlib
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
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
    portrait: Path | None = None  # 這一套的定裝照（cut_for 照它判斷角色穿不穿白衣，見 cutting.wears_white）
    pose: Path | None = None  # 畫圖時拿來代替 refs[0] 的姿勢剪影（見 POSE）；審圖照舊看 refs
    text: str = ""  # 自建形象：玩家寫的那一句（畫之前換成英文的外觀描述，見 described）


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
# 姿勢剪影（2026-11-03 畫坊量測，正式站 #494、#495 都卡在這兩張）：畫圖時第一張參考圖不給斗笠小子的彩色原圖，
# 給同一套姿勢塗成一片灰的剪影（scripts/make_pose_refs.py 產的）。彩色原圖會被 klein 當成要畫的人——
# 審圖擋下最多的理由是「穿斗笠小子的格紋護甲、深色褲子」「頭上冒出斗笠」；剪影只留姿勢與排法。
# 量到的第一次就過的比例（兩套角色合計）：dodge 6% → 31%、fall 6% → 17%。
# hero_run（2026-11-04 正式站 #495 十連掛）：斗笠小子沒戴面罩、腰間掛劍，蒙面客照抄成「面罩不見」「帶兵器」——
# 彩色原圖 0/6，留著劍的剪影 0/6（六張都被判帶兵器），去掉劍的剪影 2/6。其他張沒量過、現在也過得去，照舊。
# 審圖照舊看彩色原圖（量的時候就是這樣審的）：剪影只換畫圖那一邊。
POSE_DIR = Path(__file__).parent / "pose"
POSE = {"hero_bare_dodge", "hero_bare_fall", "hero_run"}
POSE_EXTRA = ("The FIRST attached image shows ONLY the poses, as flat gray silhouettes (same frame count, same poses, same size and "
              "position in each frame) — copy the poses, not the gray color or the shapes on the head. "
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
# 動作比對再放寬（企劃者 2026-11-03）：11/02 那一次改了「判整串、不要逐格」，但審圖照舊逐格擋
# （#28、#29 的 hero_bare_idle 各畫十次全掛，理由都是「第3格前傾不明顯」「第4格出現跨步」
# 「與參考圖的動作順序不符」）。漏掉的是：交給審圖的 {action} 就是 orders.ACTIONS 那段**給生圖的
# 逐格編舞稿**（「frames 1, 2 and 4 是站定，frame 3 整個身體往右前傾約一成畫面寬」），審圖讀到
# 逐格數字自然當成逐格規格驗，寫在後面的「judge as a whole」壓不過它。所以這一次把不算過不了的
# 項目逐條點名（哪一格是極點、傾多遠、手腳位置、格的順序），並說明那段文字是給生圖的 brief。
# 硬規則照舊全留：格數、整個人在框內、同一個人、沒有武器、側面向右、腳在同一條線、去背乾淨。
GEAR_NONE = "holds no weapon or object (loose sleeves, ribbons, sashes and long hair are not objects)"
# 走一趟那六張也空手（企劃者 2026-11-03「走一趟不能不帶佩劍嗎」）：FB-8003 原本讓這六張在定裝照的人身上加一把腰間佩劍
# （斗笠小子的走一趟原畫佩了劍，提示詞與清單照它寫），結果 #29 的 hero_pickup 又十連掛，理由跟修之前幾乎一字不差：
# 「第1、2、4格手持出鞘長劍，第3、5、6格看不到劍」「撿拾動作不需拔劍，劍應佩在腰間」——klein 每一格獨立生成，
# 一把沒有依據的配件做不到六格一致。而這把劍沒有任何東西在用：手位表只算擂台那十張（orders.sheet_saved 的
# `if sheet in ARENA`），web/outing.js 從不疊兵器（整個檔沒有 RING_HAND／hands／weapon／sword）。
# 反過來，留著它更不一致：web/outing.js 的 OUTING_LOOK_SHEET 讓站著、挨打、跪地借用擂台那三張（空手），
# 所以同一個走一趟場景裡劍會憑空出現又消失。六張一律空手之後兩個死因一起消失，難度跟擂台十張一樣。
CHECK_SHEET = (
    "This is an animation strip for a 2D fighting game: {frames} frames side by side, each 220×220, cut out from the background "
    "(cut-out areas are flat gray). The action should be: {action}\n"
    "Reference 1 is the same animation drawn for another character (layout and overall action to follow). Reference 2 is this "
    "character's design.\nPass it only if: exactly {frames} frames, one whole character in each (no frame empty, cut in half, or "
    "holding two characters); it is the same character as reference 2 in every frame (face, hair, clothes, colors); the strip as a "
    "whole reads as that kind of action, and not every frame is the same drawing — the action text above is the brief given to the "
    "image model, NOT a per-frame checklist for you: which frame carries the extreme of the motion, how far a frame leans, steps or "
    "shifts, exact limb and hand positions, and the frame order are NOT pass criteria. Fail the action only if the strip reads as a "
    "different action altogether, or if the frames are all identical; side view facing right; {gear}; feet roughly on the same "
    "ground line.\n"
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
                               refs=(arena / "hero_bare_idle.webp",), text=o.prompt))
                continue
            have = orders.present(root, look)
            sheet = next((s for s in orders.SHEETS if s not in have and (o.status == orders.PENDING or s in orders.OUTING)), None)
            if sheet is None:
                continue
            pose = POSE_DIR / f"{sheet}.png" if sheet in POSE else None
            pose = pose if pose is not None and pose.is_file() else None
            out.append(Job(kind="look", pid=o.pid, folder=look, slot=sheet, label=sheet, portrait=portrait, pose=pose,
                           prompt=f"{orders.gen_prompts(o)[sheet]}\n{POSE_EXTRA if pose else SHEET_EXTRA}",
                           checklist=CHECK_SHEET.format(frames=orders.SHEETS[sheet], action=orders.ACTIONS[sheet],
                                                        gear=GEAR_NONE),  # 十六張一律空手（見 GEAR_NONE 上面那段）
                           aspect=ASPECT[LAYOUT[sheet]], size="2K", refs=(orders.reference(web_img, sheet), portrait),
                           text=o.prompt))
    return out


# ── 畫一張 ───────────────────────────────────


def cut_for(job: Job, raw: bytes, cutting) -> bytes:
    """照這一張是什麼去背、切格（cutting 是 cutting.py 那個模組：畫坊程式傳進來，這支不 import numpy）。"""
    if job.slot == PORTRAIT:
        cutting.art_bytes(raw)  # 只驗切得出一個人；收的是白底的原圖（給之後十張當參考）
        return raw
    if job.kind == "move":
        return cutting.art_bytes(raw)
    # 手臂與身體圍住的那一塊白底要挖掉，但角色本來就穿白衣的不能挖（照定裝照判，cutting.wears_white）
    white = bool(job.portrait and job.portrait.is_file() and cutting.wears_white(job.portrait.read_bytes()))
    return cutting.sheet_bytes(raw, job.slot, keep_white=white)


def work(job: Job, painter: Painter, critic: Critic, cut: Callable[[Job, bytes], bytes], *, tries: int = MAX_TRIES,
         fresh: bool = False) -> Result:
    """畫、切、審，沒過照意見改，最多 tries 張（雲端生圖要錢所以是 MAX_TRIES＝3；本機生圖不要錢，畫坊程式會給大一點的數）。
    fresh：沒過就重新畫一張（同一份提示詞與參考圖），不照意見改上一張——本機 klein 用（見 studio_local.LocalPainter.fresh_retries）。
    生圖那邊忙（PaintBusy）照丟出去：這一張不算，下一輪再來。"""
    refs = [p.read_bytes() for p in job.refs if p.is_file()]
    # 畫圖用的：有姿勢剪影就代替第一張（斗笠小子的彩色原圖）；審圖照舊看 refs（見 POSE）
    paint_refs = [job.pose.read_bytes(), *refs[1:]] if job.pose is not None and job.pose.is_file() and refs else refs
    raw = b""
    problems: list[str] = []
    for n in range(1, max(1, tries) + 1):
        try:
            if n == 1 or fresh:
                raw = painter.paint(job.prompt, paint_refs, job.aspect, job.size)
            else:
                raw = painter.paint(FIX_PROMPT.format(fix=verdict.fix or "redraw it following the instructions", prompt=job.prompt),
                                    [raw, *paint_refs], job.aspect, job.size)
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
    return Result(ok=False, raw=raw, painted=max(1, tries), problems=problems)


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
    # 「到齊了」只在真的齊了才說：以前就待審、正在補走一趟的那幾張，每收一張都還是待審（企劃者 2026-11-04 十六張全齊才算）
    done = now.status == orders.REVIEW and (job.kind == "move" or len(orders.present(root, job.folder)) == len(orders.SHEETS))
    return f"#{job.pid} {job.label} 收了" + ("，到齊了等管理者上架" if done else "")


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


# 玩家寫的中文換成英文的外觀描述再畫（2026-11-04 畫坊量測）：玩家那一句原封不動塞進英文提示詞，klein 讀不懂——
# 「女版斗笠小子」「貓咪勇士」的定裝照各畫十次全掛，理由都是「跟參考圖的男孩一模一樣」（「斗笠小子」正好是參考圖那個人）。
# 先請審圖的那一家把它寫成具體的英文（性別、髮型、每件衣服與顏色），同一張「女版斗笠小子」第一次就過。
# 十六張改照「定裝照」寫的描述（不是照玩家那一句）：要畫的是定裝照上那個人——#495 寫「神秘兮兮的感覺」，
# 定裝照卻是斗笠加蒙面，照那一句寫的描述會畫成另一個人。描述記在訂單上（studio.design，照定裝照的指紋），一套只問一次。
# 審圖的沒有這兩個本事（測試假人、雲端以外的）就照舊用玩家那一句。
def described(job: Job, critic: Critic, wallet: Wallet) -> tuple[Job, dict | None]:
    """這一張要畫的提示詞換成英文的外觀描述。回（換好的 job, 要記在訂單上的描述或 None）。"""
    if job.kind != "look" or not job.text:
        return job, None
    if job.slot == PORTRAIT:
        fn = getattr(critic, "describe_text", None)
        words = fn(job.text) if callable(fn) else ""
        return (replace(job, prompt=PORTRAIT_PROMPT.format(style=orders.BASE_STYLE, text=words)) if words else job), None
    fn = getattr(critic, "describe_image", None)
    if not callable(fn) or job.portrait is None or not job.portrait.is_file():
        return job, None
    image = job.portrait.read_bytes()
    of = hashlib.sha1(image).hexdigest()[:16]
    b = wallet.purchase(job.pid)
    known = ((b.data.get("studio") or {}).get("design") or {}) if b is not None else {}
    words, fresh = (known.get("text") or "") if known.get("of") == of else "", None
    if not words:
        words = fn(image)
        fresh = {"text": words, "of": of} if words else None
    if not words:
        return job, None
    prompt = f"{orders.gen_prompts(SimpleNamespace(prompt=words))[job.slot]}\n{POSE_EXTRA if job.pose else SHEET_EXTRA}"
    return replace(job, prompt=prompt), fresh


def tick(content: Content, store, root: Path, web_img: Path, painter: Painter, critic: Critic,
         cut: Callable[[Job, bytes], bytes], *, budget: int = 1, tries: int = MAX_TRIES, fresh: bool = False) -> list[str]:
    """畫坊巡一輪：做最多 budget 張（每張最多叫 tries 次生圖）。畫在鎖外（慢），收在行動鎖裡（同伺服器的一個動作）。
    store 是 open_world() 那個（有 db、action_lock）。回幾句給主控台。"""
    wallet = Wallet(store.db)
    lines: list[str] = []
    for job in jobs(content, wallet, root, web_img)[:max(0, budget)]:
        job, design = described(job, critic, wallet)
        try:
            result = work(job, painter, critic, cut, tries=tries, fresh=fresh)
        except PaintBusy as exc:
            lines.append(f"#{job.pid} {job.label} 生圖的那邊忙，下一輪再來（{exc}）")
            continue
        with store.action_lock():
            b = wallet.purchase(job.pid) if design else None
            if b is not None:
                wallet.update_data(job.pid, studio={**(b.data.get("studio") or {}), "design": design})
            lines.append(apply(content, wallet, root, job, result))
    return lines
