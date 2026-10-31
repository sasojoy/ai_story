"""自創武學（武學重構，Joy 2026-10-20：先選兵器、擺姿勢當圖示、寫一句意，槽分顏色；草案 https://claude.ai/artifact/54XJZ7jutrsND8YLnyCC4x）。

五步，單子記在 PlayerState.creating（state.CreateDraft）：
1. 執器（begin）：內功或武學，再挑兵器種類（武學）或行功之法（內功）。每一種有一張偏向表（content/create_forms.json），
   拳腳容易出快、弓弩容易出快與虛……只是機率高一點，不是絕對（Joy「這也會讓玩家分流派」）。檢查付不付得起，還不收錢。
2. 擺式（set_pose）：玩家拖火柴人擺出一個姿勢（POSE_KEYS 九個角度）。姿勢照幾何讀出偏向（pose_read：手伸得遠偏剛、
   雙手收在胸前偏柔、馬步寬偏實、提腿偏虛……），不叫模型（Joy「不要 LLM 評姿勢」）；存下來當這一門的圖示。
3. 立意（set_intent）：20 字的「意」。模型讀這一句（三段式：A Game.create_request → B create.read 鎖外 → C Game.create_intent），
   回一個 0～100 的分數、最多兩路屬性與正邪；叫不動照關鍵字表讀（fallback_read，分數 DEFAULT_SCORE）。
4. 成形（roll_colors，立意之後馬上擲）：照權重擲四格顏色——第一格一定是權重最高那一路的單色（玩家引導的方向），
   其餘每格照 create_slot_odds 擲單色、雙色、任色。意讀出「不偏」時任色的機會加倍（create_neutral_any_scale）。
   不滿意可以回頭重擺或重寫一次（create_redo，免費）；亂數是「自創｜天機｜名號｜第幾門｜第幾擲」，不碰 Game.rng。
5. 立名（finish）：自己取名（心得在立意那一刻收，Joy 2026-10-21；這一版之前成形、還沒付的單子在這裡收）。自創的一律是 Config.arts.create_grade（上品，Joy 2026-10-21「自創武學應該保底
   都是上品」；多付心得加分拿掉了，「多付心得很莫名其妙」），四格全開；意分＋赤璋只定底子（power_scale_of）；
   威力從第一成起練；注解就是那一句意。
   這一門自己長出一招（以意成招，tianxia/moves.py）：擺式定勢（stance_of）、主屬性定路數、意分定火候（生熟透），
   模型照意起的招名玩家可改；成形時有稀有路數那一格照 move_rare_odds 擲。開著的格子全單色是純、全任色是渾（打起來功效多一截）。

價錢：Config.arts.create_xinde × create_step^（這一季已自創幾門）；這一季第一門是 create_first_xinde（有寫的話）；create_per_season 0 是不限門數。
只改狀態與回傳訊息；數字全由這裡算，模型只給一個分數與兩個屬性字。
"""
from __future__ import annotations

import math
import random
import zlib
from dataclasses import dataclass

from pydantic import BaseModel, Field

from . import annals, arts as arts_mod, library, might, moves, naming, tactics, team, treasures
from .martial_arts import ATTRIBUTES, QUALITY_BASE_POWER, QUALITY_TOP_POWER, MartialArt, scaled
from .models import Content, TacticDef
from .ollama_client import OllamaClient
from .state import CreateDraft, GameState
from .world_state import WorldStateStore

KINDS = ("內功", "武學")
LEANS = ("無", "正", "邪")
STEPS = ("pose", "intent", "name")
INTENT_MAX = 20
INTENT_MIN = 2
DEFAULT_SCORE = 40
SCORE_FLOOR, SCORE_CAP = 5, 85
READ_MAX = 2  # 意最多讀出兩路
POSE_KEYS = ("t", "lS", "lE", "rS", "rE", "lH", "lK", "rH", "rK")
TORSO_LIMIT = 35
DEFAULT_PRESET = "起手"

# 火柴人的骨架（跟 web/app.js 的 RIG 同一組數字：拖出來的角度照同一個幾何讀）
CX, SY, HIPY = 110.0, 96.0, 146.0
UA, FA, TH, SH = 27.0, 25.0, 31.0, 29.0
POSE_FLOOR = 0.35  # 最強那一路不到這麼多就是「平正，不偏」

OFF = "這裡不興自創武學。"
IN_PROLOGUE = "師父還沒教到這一步。"
NAMING_FIRST = "你練成絕學的武學還沒定名，先替它取好正式的名字。"
CAP_LINE = "這一季你已經自創了 {n} 門，再多也立不住了。"
FULL_LINE = "功法庫滿了，先熔掉一門再立新派。"
XINDE_LINE = "心得不足：自創一門要 {price}（你有 {have}）。"
NO_DRAFT = "你還沒起意。先到「煉製」執器，起一門新功夫。"
WRONG_STEP = "這一步不對：先{what}。"
STEP_WORDS = {"pose": "擺式", "intent": "立意", "name": "立名"}
BUSY_LINE = "你手上已經有一門還沒成形的功夫，先把它立好或擱下。"
KIND_LINE = "要立的是內功還是武學？"
FORM_LINE = "{kind}要挑一種：{forms}。"
INTENT_LINE = f"「意」要 {INTENT_MIN}～{INTENT_MAX} 個字，一句話說這門功夫的神。"
MOVE_MIN, MOVE_MAX = 2, 4  # 招名幾個字
SAY_MIN, SAY_MAX = 4, 24  # 模型寫的那一句幾個字
MOVE_LINE = f"招名要 {MOVE_MIN}～{MOVE_MAX} 個中文字。"  # 待 joy 潤
NO_REDO = "已經重來過了，這一回就照這個形立名吧（或擱下重起）。"  # 待 joy 潤
NAME_TAKEN = "這個名字已經有人用了，換一個。"
BEGUN_LINE = "你握起{form}，想立一門自己的{kind}。先擺個架式。"  # 待 joy 潤
POSED_LINE = "你擺定了這一式：{read}。"  # 待 joy 潤
FORMED_LINE = "你閉目良久，「{intent}」——這門功夫有了形：{colors}。"  # 待 joy 潤
BACK_LINE = "你散了架式，重新來過。"  # 待 joy 潤
CREATED_LINE = "你自創了一門{kind}【{name}】。"  # 待 joy 潤
MOVE_SHOWN = "招：{card}"  # 待 joy 潤
CANCELLED = "你把這門還沒成形的功夫擱下了。"
CANCELLED_PAID = "你把這門功夫擱下了。立意時付的 {paid} 心得不退。"  # 待 joy 潤
REROLLED = "你又把「{intent}」推演了一遍——這門功夫換了個形：{colors}。"  # 待 joy 潤
NO_REROLL = "手上沒有重悟帖：萬寶閣買得到。"  # 待 joy 潤
REROLL_CAPPED = "這一門已經重骰 {cap} 次，不能再骰了：留下這個形，或回頭重來。"  # 待 joy 潤
REROLL_STEP = "要先立了意、成了形，才能重骰。"  # 待 joy 潤
# 重悟帖的第二個用法「重讀這句意」（Joy 2026-10-22「立意那邊好像也要可以重骰」，PM 定的做法）。待 joy 潤
REREAD_LINE = "你把「{intent}」重新體會了一遍，意分與屬性重讀過——這門功夫換了個形：{colors}。"
REREAD_FAILED = "這一句意這會兒沒讀成，重悟帖沒有用掉，稍後再試。"
FLAT_LINE = "此式平正，不偏一路"  # 待 joy 潤
LEAN_TEXT = {"正": "，帶一股正氣", "邪": "，帶一股邪氣", "無": ""}  # 待 joy 潤
# 擺式那一步讓人知道怎麼擺是哪個勢、對應哪個時機（Joy 2026-10-22「要加」）：照 stance_of 認的先後排（提腿先看）。待 joy 潤
STANCE_ORDER = ("變勢", "守勢", "攻勢", "起勢")
STANCE_HOW = {"變勢": "提起一條腿", "守勢": "雙手收在胸前，或馬步放寬、手不伸出去", "攻勢": "手伸得遠，或身子前傾", "起勢": "其餘的架式"}
# 稀有路數（content/create_forms.json 的 moves 標 rare 的那幾格）：只說哪幾格有、不說招名（留驚喜）。待 joy 潤
RARE_LINE = "每一格都有機會撞到稀有路數（成形時約{odds}）"  # 待 joy 潤
# 成形撞到稀有路數時招上面那一句：一併寫出這一格常見的是哪一招，玩家才知道撞到的跟平常的不一樣（Joy 2026-10-23）
RARE_HIT = "撞到稀有路數！這一格常見的是〔{common}〕，你成形的是另一招。"  # 待 joy 潤


# ── 價錢與門檻 ──────────────────────────────────────────


def on(content: Content) -> bool:
    return content.config.arts.create_xinde > 0  # create_per_season 0＝不限門數（招式與絕學稿案第二輪）


def price(state: GameState, content: Content) -> int:
    cfg = content.config.arts
    if cfg.create_first_xinde and state.player.created_count == 0:
        return cfg.create_first_xinde  # 這一季第一門（Joy 2026-10-21）
    return int(round(cfg.create_xinde * (cfg.create_step ** state.player.created_count)))


def allowed(state: GameState, content: Content) -> str | None:
    """現在能不能自創（每一步之前都問它）；None＝可以。不照週解鎖：開季就有（企劃者 2026-10-28「開季就有」）。"""
    from . import prologue

    cfg = content.config.arts
    if not on(content):
        return OFF
    if prologue.active(state, content):
        return IN_PROLOGUE
    if state.player.naming is not None:
        return NAMING_FIRST
    paid = state.player.creating is not None and state.player.creating.paid  # 立意付過了：這一門已經數進去，照樣走完
    if cfg.create_per_season and not paid and state.player.created_count >= cfg.create_per_season:
        return CAP_LINE.format(n=state.player.created_count)
    if library.full(state, content):
        return FULL_LINE
    return None


def _xinde(state: GameState) -> int:
    return int(state.player.stats.get("xinde", 0))


def forms_of(content: Content, kind: str) -> list:
    return [f for f in content.create_forms.forms if f.kind == kind]


def form_def(content: Content, kind: str, key: str):
    return next((f for f in forms_of(content, kind) if f.key == key), None)


def _draft(state: GameState, step: str) -> tuple[CreateDraft | None, str | None]:
    draft = state.player.creating
    if draft is None:
        return None, NO_DRAFT
    if draft.step != step:
        return None, WRONG_STEP.format(what=STEP_WORDS.get(draft.step, "執器"))
    return draft, None


# ── 第一步：執器 ────────────────────────────────────────


def begin_problem(state: GameState, content: Content, kind: str, form: str) -> str | None:
    problem = allowed(state, content)
    if problem is not None:
        return problem
    if state.player.creating is not None:
        return BUSY_LINE
    if kind not in KINDS:
        return KIND_LINE
    if form_def(content, kind, form) is None:
        return FORM_LINE.format(kind=kind, forms="、".join(f.key for f in forms_of(content, kind)))
    need = price(state, content)
    if _xinde(state) < need:
        return XINDE_LINE.format(price=need, have=_xinde(state))
    return None


def preset(content: Content, name: str = DEFAULT_PRESET) -> dict[str, float]:
    p = next((x for x in content.create_forms.presets if x.name == name), None)
    angles = dict(p.angles) if p is not None else {}
    return {k: float(angles.get(k, 0.0)) for k in POSE_KEYS}


# 功法卡上的小圖：自創的照自己擺的式；其餘照兵器挑一個預設的架式（內功與推不出兵器的照 None）
ICON_PRESET = {"拳腳": "起手", "劍": "進擊", "刀": "進擊", "槍": "進擊", "棍": "守禦", "弓弩": "奇變", None: "守禦"}


def icon_pose(content: Content, art: MartialArt, weapon: str | None) -> dict[str, float]:
    if art.pose:
        return {k: float(art.pose.get(k, 0.0)) for k in POSE_KEYS}
    return preset(content, ICON_PRESET.get(weapon if art.kind == "武學" else None, DEFAULT_PRESET))


def begin(state: GameState, content: Content, kind: str, form: str) -> list[str]:
    problem = begin_problem(state, content, kind, form)
    if problem is not None:
        return [problem]
    state.player.creating = CreateDraft(
        kind=kind, form=form, pose=preset(content), step="pose", redo=content.config.arts.create_redo,
    )
    return [BEGUN_LINE.format(form=form, kind=kind)]


# ── 第二步：擺式 ────────────────────────────────────────


def _norm(d: float) -> float:
    d = math.fmod(d, 360.0)
    if d > 180:
        d -= 360
    elif d < -180:
        d += 360
    return d


def clean_pose(pose: dict, base: dict[str, float]) -> dict[str, float]:
    """網頁送來的九個角度：不是數字的照 base，其餘正規化到 ±180，上身傾夾在 ±TORSO_LIMIT。"""
    out = {k: float(base.get(k, 0.0)) for k in POSE_KEYS}
    for k in POSE_KEYS:
        try:
            v = float((pose or {}).get(k, out[k]))
        except (TypeError, ValueError, AttributeError):
            continue
        if not math.isfinite(v):
            continue
        v = max(-TORSO_LIMIT, min(TORSO_LIMIT, v)) if k == "t" else _norm(v)
        out[k] = round(v, 1)
    return out


def joints(pose: dict[str, float]) -> dict[str, tuple[float, float]]:
    """九個角度 → 兩手兩腳的座標（跟網頁的火柴人同一個幾何；0 度朝下、正的往右）。"""
    r = math.radians
    t = r(pose.get("t", 0.0))

    def chain(x, y, a1, l1, a2, l2):
        e = (x + math.sin(a1) * l1, y + math.cos(a1) * l1)
        return (e[0] + math.sin(a1 + a2) * l2, e[1] + math.cos(a1 + a2) * l2)

    return {
        "lHa": chain(CX - 9, SY, r(pose.get("lS", 0)) + t, UA, r(pose.get("lE", 0)), FA),
        "rHa": chain(CX + 9, SY, r(pose.get("rS", 0)) + t, UA, r(pose.get("rE", 0)), FA),
        "lFt": chain(CX - 7, HIPY, r(pose.get("lH", 0)), TH, r(pose.get("lK", 0)), SH),
        "rFt": chain(CX + 7, HIPY, r(pose.get("rH", 0)), TH, r(pose.get("rK", 0)), SH),
    }


def _features(pose: dict[str, float]) -> tuple[float, float, bool, float, bool, float]:
    """（手伸多遠, 手抬多高, 雙手收胸, 馬步多寬, 提腿, 前後傾）——偏向與勢都照它讀（跟網頁 poseRead 同一套幾何）。"""
    j = joints(pose)
    lh, rh, lf, rf = j["lHa"], j["rHa"], j["lFt"], j["rFt"]
    reach = max(abs(rh[0] - CX), abs(lh[0] - CX)) / (UA + FA)
    high = max(SY - rh[1], SY - lh[1]) / (UA + FA)
    tucked = math.hypot(rh[0] - CX, rh[1] - (SY + 20)) < 30 and math.hypot(lh[0] - CX, lh[1] - (SY + 20)) < 30
    spread = abs(lf[0] - rf[0]) / (TH + SH)
    lift = min(lf[1], rf[1]) < HIPY + TH * 1.3
    return reach, high, tucked, spread, lift, pose.get("t", 0.0)


def stance_of(pose: dict[str, float]) -> str:
    """以意成招的「勢」（moves.STANCE_TIMING）：提腿是變勢；雙手收胸、或馬步寬而手不出是守勢；手伸得遠或身子前傾是攻勢；其餘起勢。"""
    reach, _high, tucked, spread, lift, lean = _features(pose)
    if lift:
        return "變勢"
    if tucked or (spread > 1.1 and reach < 0.95):
        return "守勢"
    if reach >= 1.0 or lean <= -10:
        return "攻勢"
    return "起勢"


def pose_scores(pose: dict[str, float]) -> dict[str, float]:
    """姿勢讀出來的偏向（只有剛柔快慢虛實；陰陽靠兵器與意）。"""
    reach, high, tucked, spread, lift, lean = _features(pose)
    s = {a: 0.0 for a in ("剛", "柔", "快", "慢", "實", "虛")}
    s["剛"] += max(0.0, reach - 0.95) * 8 + max(0.0, high - 0.15) * 2
    if tucked:
        s["柔"] += 1.6
    s["實"] += max(0.0, spread - 0.9) * 3
    s["慢"] += max(0.0, spread - 1.1) * 2
    if lift:
        s["虛"] += 2.0
        s["快"] += 1.0
    if lean < -12:
        s["快"] += (-lean - 12) / 15
    if lean > 10:
        s["慢"] += (lean - 10) / 15
    return s


def pose_read(pose: dict[str, float]) -> list[str]:
    """最強的一路（不到 POSE_FLOOR 是空的＝平正），第二路要過 POSE_FLOOR 又有第一路的六成才算。"""
    ranked = sorted(pose_scores(pose).items(), key=lambda kv: (-kv[1], ATTRIBUTES.index(kv[0])))
    if ranked[0][1] < POSE_FLOOR:
        return []
    out = [ranked[0][0]]
    if ranked[1][1] > POSE_FLOOR and ranked[1][1] > ranked[0][1] * 0.6:
        out.append(ranked[1][0])
    return out


def read_text(attrs: list[str]) -> str:
    if not attrs:
        return FLAT_LINE
    return "此式偏" + attrs[0] + ("、兼" + attrs[1] if len(attrs) > 1 else "")


def set_pose(state: GameState, content: Content, pose: dict) -> list[str]:
    problem = allowed(state, content)
    if problem is not None:
        return [problem]
    draft, problem = _draft(state, "pose")
    if problem is not None:
        return [problem]
    draft.pose = clean_pose(pose, draft.pose or preset(content))
    draft.step = "intent"
    return [POSED_LINE.format(read=read_text(pose_read(draft.pose)))]


# ── 第三步：立意（模型讀一句意）──────────────────────────


def clean_intent(text: str) -> str:
    return " ".join(str(text or "").split())


def intent_problem(state: GameState, content: Content, text: str) -> str | None:
    problem = allowed(state, content)
    if problem is not None:
        return problem
    draft, problem = _draft(state, "intent")
    if problem is not None:
        return problem
    if not (INTENT_MIN <= len(clean_intent(text)) <= INTENT_MAX):
        return INTENT_LINE
    need = price(state, content)
    if not draft.paid and _xinde(state) < need:  # 付過了（成形之後回頭重立意）不再收
        return XINDE_LINE.format(price=need, have=_xinde(state))
    return None


@dataclass(frozen=True)
class IntentRequest:
    """立意那一步的 A 段單子：鎖外請模型讀這一句意。"""

    kind: str
    form: str
    pose: str  # 這一式讀出來的那句（給模型當背景）
    text: str
    name: str


class IntentReading(BaseModel):
    score: int = DEFAULT_SCORE
    attributes: list[str] = Field(default_factory=list)
    lean: str = "無"
    move: str = ""  # 以意成招：模型照這一句意替招取的名字（二到四字；立名時玩家可改）
    say: str = ""  # 招發動時那一句（名字後面接的話，十到二十字）


READ_PREDICT = 200
SYSTEM_PROMPT = (
    "你是武俠小說裡評判武功立意的宗師。玩家要自創一門功夫，已經挑好兵器、擺好架式，最後寫下一句「意」。\n"
    "1. score：這一句意寫得好不好，0～100 的整數。有神、有象、合乎武理給高分；空洞、灌水、亂寫、跟功夫無關給低分。\n"
    "2. attributes：這一句意的神韻偏向哪幾路，從「陰、陽、剛、柔、快、慢、虛、實」裡挑零到兩個字，最像的放前面；"
    "看不出偏向就給空清單。陰是陰柔詭譎、陽是光明熾烈、剛是剛猛、柔是綿柔借力、快是迅捷、慢是沉穩後發、虛是虛實變幻、實是紮實厚重。\n"
    "3. lean：這一句意是正派、邪派還是不分，只回「正」「邪」「無」其中一個。\n"
    "4. move：照這一句意替這門功夫的殺招取一個名字，二到四個中文字，不要用現成武俠小說裡的招名。\n"
    "5. say：這一招使出來時的一句描寫，十到二十字，主詞省略（例：「腳下一錯追了上去」），不寫數字、不寫對手的名字。\n"
    "只回 JSON。"
)


def request(state: GameState, text: str) -> IntentRequest:
    draft = state.player.creating
    return IntentRequest(draft.kind, draft.form, read_text(pose_read(draft.pose)), clean_intent(text), state.player.name)


def clamp_score(value: int | None) -> int:
    if value is None:
        return DEFAULT_SCORE
    try:
        return max(SCORE_FLOOR, min(SCORE_CAP, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_SCORE


def clean_reading(reading: IntentReading | None) -> IntentReading:
    """引擎再驗一次：屬性只留認得的、不重複、最多兩個；正邪不認得當無；分數夾 SCORE_FLOOR～SCORE_CAP。"""
    if reading is None:
        return IntentReading()
    attrs = [a for a in dict.fromkeys(str(x).strip() for x in (reading.attributes or [])) if a in ATTRIBUTES][:READ_MAX]
    lean = reading.lean if reading.lean in LEANS else "無"
    move = naming.clean_name(reading.move or "")
    move = move if MOVE_MIN <= len(move) <= MOVE_MAX and all("\u4e00" <= ch <= "\u9fff" for ch in move) else ""
    say = " ".join(str(reading.say or "").split())
    say = say if SAY_MIN <= len(say) <= SAY_MAX and not any(ch.isdigit() for ch in say) and "{" not in say else ""
    return IntentReading(score=clamp_score(reading.score), attributes=attrs, lean=lean, move=move, say=say)


def fallback_read(content: Content, text: str) -> IntentReading:
    """模型叫不動（假人、整季機器人、斷路）：照關鍵字表讀，命中最多的兩路；分數 DEFAULT_SCORE。"""
    text = clean_intent(text)
    hits = {a: sum(text.count(w) for w in words) for a, words in content.create_forms.keywords.items() if a in ATTRIBUTES}
    ranked = [a for a, n in sorted(hits.items(), key=lambda kv: (-kv[1], ATTRIBUTES.index(kv[0]))) if n > 0][:READ_MAX]
    lean = "無"
    for side in ("正", "邪"):
        if any(w in text for w in content.create_forms.lean_words.get(side, [])):
            lean = side
            break
    return IntentReading(score=DEFAULT_SCORE, attributes=ranked, lean=lean)


def read_or_none(client: OllamaClient | None, req: IntentRequest) -> IntentReading | None:
    """B 段（重讀這句意）：模型讀這一句意；叫不動是 None（重讀不照關鍵字表讀：讀不成就不扣帖、什麼都不改）。"""
    if client is None:
        return None
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"要立的：一門{req.kind}（{req.form}）；架式：{req.pose}\n這一句意：「{req.text}」"},
    ]
    try:
        result = client.chat_structured(
            messages, IntentReading, temperature=0.3, num_predict=READ_PREDICT,
            required_fields=["score", "lean"], require_in_schema=True,
        )
    except Exception:
        return None
    return clean_reading(result)


def read(client: OllamaClient | None, req: IntentRequest, content: Content) -> IntentReading:
    """B 段：模型讀這一句意；叫不動照關鍵字表。結果 C 段再過 clean_reading。"""
    if client is None:
        return fallback_read(content, req.text)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"要立的：一門{req.kind}（{req.form}）；架式：{req.pose}\n這一句意：「{req.text}」"},
    ]
    try:
        result = client.chat_structured(
            messages, IntentReading, temperature=0.3, num_predict=READ_PREDICT,
            required_fields=["score", "lean"], require_in_schema=True,
        )
    except Exception:
        return fallback_read(content, req.text)
    return clean_reading(result)


# ── 第四步：成形（擲每一格的顏色）────────────────────────


def weights(content: Content, draft: CreateDraft, pose: bool = True) -> dict[str, float]:
    """每一路屬性的權重：底＋兵器或行功之法的偏向＋姿勢讀出的兩路＋意讀出的兩路。pose 是 False 時不加姿勢那兩路
    （擺式那一步網頁照拖到一半的姿勢自己加，view 的 base_weights）。"""
    cfg = content.config.arts
    w = {a: float(cfg.create_base_weight) for a in ATTRIBUTES}
    f = form_def(content, draft.kind, draft.form)
    for a, n in (f.bias.items() if f is not None else []):
        if a in w:
            w[a] += float(n)
    for a, n in zip(pose_read(draft.pose) if pose else [], cfg.create_pose_weights):
        w[a] += float(n)
    for a, n in zip(draft.read, cfg.create_intent_weights):
        if a in w:
            w[a] += float(n)
    return w


def _pick(rng: random.Random, w: dict[str, float], skip: str | None = None) -> str:
    items = [(a, v) for a, v in w.items() if a != skip and v > 0]
    roll = rng.random() * sum(v for _, v in items)
    acc = 0.0
    for a, v in items:
        acc += v
        if roll < acc:
            return a
    return items[-1][0]


def seed_of(state: GameState, world: WorldStateStore, draft: CreateDraft) -> str:
    from . import secret_recipes

    return f"自創|{secret_recipes.tianji_of(world)}|{state.player.name}|{state.player.created_count}|{draft.rolls}"


def top_of(content: Content, draft: CreateDraft) -> str:
    """主屬性：權重最高的那一路（武學的屬性、招的路數都照它）。"""
    w = weights(content, draft)
    return max(ATTRIBUTES, key=lambda a: (w[a], -ATTRIBUTES.index(a)))


def roll_colors(content: Content, draft: CreateDraft, rng: random.Random) -> list[list[str]]:
    """每一格的顏色，照 create_slot_odds 擲單、雙、任（意不偏時任色加倍）。第一格單色、雙色都以主屬性打頭（定向）；
    第一格也擲，所以三格全單色（純）約 0.55³、三格全任色（渾）約 0.1³（招式與絕學稿案「稀有」）。"""
    cfg = content.config.arts
    w = weights(content, draft)
    top = top_of(content, draft)
    odds = {k: float(v) for k, v in cfg.create_slot_odds.items()}
    if not draft.read:
        odds["全"] = odds.get("全", 0.0) * cfg.create_neutral_any_scale
    out: list[list[str]] = []
    for i in range(max(1, cfg.create_slots)):
        roll = rng.random() * sum(odds.values())
        shape = "全"
        acc = 0.0
        for k in ("單", "雙", "全"):
            acc += odds.get(k, 0.0)
            if roll < acc:
                shape = k
                break
        if shape == "單":
            out.append([top] if i == 0 else [_pick(rng, w)])
        elif shape == "雙":
            first = top if i == 0 else _pick(rng, w)
            out.append([first, _pick(rng, w, skip=first)])
        else:
            out.append([])
    return out


# ── 撞出來的稀有（招式與絕學稿案「強不強、稀有不稀有」）────────────────


PURE, WHOLE = moves.PURE, moves.WHOLE
CLEAR, RARE = "透", "奇"  # 待 joy 潤
MARK_TEXT = {PURE: "三格全單色", WHOLE: "三格全任色", CLEAR: "招已透", RARE: moves.RARE_WORD}  # 待 joy 潤
TIER_TEXT = {0: "凡", 1: "佳", 2: "珍", 3: "神"}  # 跟意境的品相同一條梯子（Joy 2026-10-21「那武學呢 有分？」）


purity = moves.purity


def marks_of(colors: list[list[str]], fire: str | None, rare: bool) -> list[str]:
    """撞到的稀有：純或渾、招透、稀有路數。"""
    out = [m for m in (purity(colors),) if m]
    if fire == "透":
        out.append(CLEAR)
    if rare:
        out.append(RARE)
    return out


def tier_of(marks: list[str]) -> str | None:
    """品相：一樣都沒撞到「凡」、一樣「佳」、兩樣「珍」、三樣「神」。"""
    return TIER_TEXT[min(len(marks), 3)]


def look_text(marks: list[str]) -> str:
    """卡上那一行品相：「珍・三格全單色、招已透」；什麼都沒撞到是「凡」。"""
    return "・".join([tier_of(marks)] + (["、".join(MARK_TEXT[m] for m in marks)] if marks else []))


def colors_text(colors: list[list[str]]) -> str:
    return "、".join(arts_mod.color_text(c) for c in colors)


def set_intent(
    state: GameState, content: Content, world: WorldStateStore, text: str, reading: IntentReading | None = None,
) -> list[str]:
    """C 段（或直接呼叫）：記下意與讀出來的東西，馬上成形（擲四格顏色）。reading 沒給照關鍵字表讀。
    心得在這一刻收（Joy 2026-10-21「應該立意按下去就要收吧，因為那時候就算是骰出來武學的品質了」）：一張單子只收一次
    （draft.paid；成形之後回頭重立意不再收），這一季自創的門數也在這裡數（price 的第一門優惠照它）；之後擱下不退。"""
    problem = intent_problem(state, content, text)
    if problem is not None:
        return [problem]
    draft = state.player.creating
    reading = clean_reading(reading) if reading is not None else fallback_read(content, text)
    draft.intent = clean_intent(text)
    draft.read = list(reading.attributes)
    draft.lean = reading.lean
    draft.score = reading.score
    draft.move = reading.move
    draft.say = reading.say
    _form(state, content, world, draft)
    msgs = [FORMED_LINE.format(intent=draft.intent, colors=colors_text(draft.colors))]
    msgs += move_lines(state, content, draft)
    if not draft.paid:
        p = state.player
        need = price(state, content)
        p.stats["xinde"] = _xinde(state) - need
        p.created_count += 1
        draft.paid = need
        msgs.append(f"心得 -{need}")
    return msgs


def move_lines(state: GameState, content: Content, draft: CreateDraft) -> list[str]:
    """成形、重骰、重讀之後寫的那一兩句：長出來的招（撞到稀有路數的後面補小章），撞到的另寫一句這一格常見的是哪一招。"""
    move = draft_move(state, content, draft)
    if move is None:
        return []
    out = [MOVE_SHOWN.format(card=tactics.card_text(move, state.player.name[:1] or tactics.MINOR_TITLE) + (f"（{moves.RARE_WORD}）" if draft.rare else ""))]
    if draft.rare:
        common = moves.cell(content, top_of(content, draft), moves.timing_of(draft.kind, stance_of(draft.pose)))
        out.append(RARE_HIT.format(common=common.name))
    return out


def _form(state: GameState, content: Content, world: WorldStateStore, draft: CreateDraft) -> None:
    """成形：照兵器、姿勢、意擲每一格的顏色與變招（種子含 draft.rolls，每擲一次換一個）。"""
    rng = random.Random(seed_of(state, world, draft))
    draft.colors = roll_colors(content, draft, rng)
    timing = moves.timing_of(draft.kind, stance_of(draft.pose))
    draft.rare = moves.has_rare(content, top_of(content, draft), timing) and rng.random() < content.config.arts.move_rare_odds
    draft.rolls += 1
    draft.step = "name"


def reroll(state: GameState, content: Content, world: WorldStateStore) -> list[str]:
    """重悟帖（萬寶閣，Joy 2026-10-21「弄個商城道具可以直接重骰，有上限」）：成了形還沒立名，用掉一張，同一個架式與意
    直接再擲一次顏色與變招（火候照意分，不變）；不收心得、不用掉免費的重來。帖子買幾張都行，一門最多重骰
    Config.arts.create_reroll_cap 次（Joy「一次創造武學的時候可能最多重骰3或是5」）。"""
    problem = reroll_problem(state, content)
    if problem is not None:
        return [problem]
    p, draft = state.player, state.player.creating
    cap = content.config.arts.create_reroll_cap
    p.create_rerolls -= 1
    draft.rerolled += 1
    _form(state, content, world, draft)
    return [REROLLED.format(intent=draft.intent, colors=colors_text(draft.colors)), *move_lines(state, content, draft),
            f"重悟帖 -1（剩 {p.create_rerolls} 張；這一門還能重骰 {cap - draft.rerolled} 次）"]


def reroll_problem(state: GameState, content: Content) -> str | None:
    """重悟帖兩個用法（重骰形、重讀這句意）共用的門檻：成了形還沒立名、這一門還沒骰滿、手上有帖。"""
    draft = state.player.creating
    if draft is None:
        return NO_DRAFT
    if draft.step != "name" or not draft.colors:
        return REROLL_STEP
    cap = content.config.arts.create_reroll_cap
    if draft.rerolled >= cap:
        return REROLL_CAPPED.format(cap=cap)
    if state.player.create_rerolls <= 0:
        return NO_REROLL
    return None


def reread_problem(state: GameState, content: Content, text: str) -> str | None:
    """重讀這句意之前（A 段與 C 段都問）：自創還開著、重悟帖用得了、那一句意（可以改寫）長短合格。"""
    problem = allowed(state, content) or reroll_problem(state, content)
    if problem is not None:
        return problem
    if not (INTENT_MIN <= len(clean_intent(text)) <= INTENT_MAX):
        return INTENT_LINE
    return None


def reread(
    state: GameState, content: Content, world: WorldStateStore, text: str, reading: IntentReading | None,
) -> list[str]:
    """重悟帖的第二個用法：重讀這句意（Joy 2026-10-22「立意那邊好像也要可以重骰」）。同一句意（或改寫過的）請模型再讀一次，
    換掉意分、火候、屬性與正邪，照新的讀法重擲成形；跟重骰形共用 create_reroll_cap、各用掉一張帖，不另收心得。
    reading 是 None（模型叫不動）就什麼都不改、不扣帖。"""
    problem = reread_problem(state, content, text)
    if problem is not None:
        return [problem]
    if reading is None:
        return [REREAD_FAILED]
    p, draft = state.player, state.player.creating
    reading = clean_reading(reading)
    draft.intent = clean_intent(text)
    draft.read = list(reading.attributes)
    draft.lean = reading.lean
    draft.score = reading.score
    draft.move = reading.move
    draft.say = reading.say
    p.create_rerolls -= 1
    draft.rerolled += 1
    _form(state, content, world, draft)
    cap = content.config.arts.create_reroll_cap
    msgs = [REREAD_LINE.format(intent=draft.intent, colors=colors_text(draft.colors))] + move_lines(state, content, draft)
    return msgs + [f"重悟帖 -1（剩 {p.create_rerolls} 張；這一門還能重骰 {cap - draft.rerolled} 次）"]


def back(state: GameState, content: Content, to: str) -> list[str]:
    """回頭：立意回擺式免費；成形之後回擺式或立意要用掉一次重來（create_redo）。"""
    draft = state.player.creating
    if draft is None:
        return [NO_DRAFT]
    if to not in ("pose", "intent") or STEPS.index(to) >= STEPS.index(draft.step):
        return [WRONG_STEP.format(what=STEP_WORDS.get(draft.step, "執器"))]
    if draft.step == "name":
        if draft.redo <= 0:
            return [NO_REDO]
        draft.redo -= 1
        draft.colors = []
        draft.rare = False
    draft.step = to
    return [BACK_LINE]


# ── 第五步：立名、登記 ───────────────────────────


def seal_points(state: GameState, content: Content) -> int:
    """玉璽赤璋（fuse_points）：加在自創的意分上（夾 0～100 之前加），底子威力的倍數（power_scale_of）跟著往上推。
    品級不擲，自創的一律是 create_grade（武學重構之後合成不擲品質，PM 2026-10-21 合 develop 時定：改版 +10、子開關關著照舊 +5）。"""
    return int(treasures.amount(state, content, "fuse_points"))


MIGHT_LINE = "換上這一門：戰力 {now} → {first}，練滿 {full}。"  # 待 joy 潤
DRAFT_ID = "（成形中）"  # 算戰力時那一門還沒登記的暫名（不給玩家看）


def power_scale_of(content: Content, points: int) -> float:
    """自創的基本威力倍數：意分＋赤璋（夾 0～100）從 power_scale_range 的下限線性推到上限。"""
    low, high = content.config.arts.power_scale_range
    return round(low + (high - low) * max(0, min(100, points)) / 100, 3)


def name_problem(state: GameState, content: Content, world: WorldStateStore, name: str) -> str | None:
    problem = allowed(state, content)
    if problem is not None:
        return problem
    draft, problem = _draft(state, "name")
    if problem is not None:
        return problem
    problem = naming.name_problem(naming.clean_name(name), content, person=world.is_character_name)
    if problem is not None:
        return problem
    need = price(state, content)
    if not draft.paid and _xinde(state) < need:  # 立意時付過了，立名不再看心得
        return XINDE_LINE.format(price=need, have=_xinde(state))
    return None


def affinity_of(colors: list[list[str]]) -> list[str]:
    """登記的相容屬性：開著的格子裡出現的屬性（照先後、不重複）。"""
    return list(dict.fromkeys(a for c in colors for a in c))


def fire_of_draft(state: GameState, content: Content, draft: CreateDraft) -> str:
    """火候：意分加赤璋（夾之前）照 move_fire_cuts 分生、熟、透。"""
    return moves.fire_of(content, draft.score + seal_points(state, content))


def draft_move(state: GameState, content: Content, draft: CreateDraft, name: str | None = None) -> TacticDef | None:
    """這一份草稿會長出哪一招（成形之後才有；沒成形是 None）：路數＝主屬性、勢照姿勢、火候照意分。
    招名照 name（立名時玩家給的）、模型起的、表上的預設名的順序；照練開之後的數算（前幾成招還生，戰鬥時才打折）。"""
    if not draft.colors:
        return None
    return moves.build(
        content, draft.kind, top_of(content, draft), stance_of(draft.pose), fire_of_draft(state, content, draft),
        draft.rare, name or draft.move or None, draft.say,
    )


def draft_art(state: GameState, content: Content, draft: CreateDraft, name: str, move: str | None = None) -> MartialArt:
    """這一份成形的單子立名之後是哪一門武學（還沒登記）：finish 照它登記，成形那一步拿它算換上後的戰力（might.with_new）。"""
    grade = content.config.arts.create_grade
    attribute = top_of(content, draft)
    affinity = list(dict.fromkeys([attribute, *affinity_of(draft.colors[: arts_mod.slot_count(content, grade)])]))
    card = draft_move(state, content, draft, move)
    art = MartialArt(
        id=name, name=name, kind=draft.kind, quality="下品", attribute=attribute,
        base_power=QUALITY_BASE_POWER["下品"], top_power=QUALITY_TOP_POWER["下品"], origin="created",
        creator=state.player.name, creator_shown=state.player.name, note=draft.intent, lean=draft.lean,
        affinity=affinity, slot_colors=[list(c) for c in draft.colors], pose=dict(draft.pose),
        weapon=draft.form if draft.kind == "武學" else None, method=draft.form if draft.kind == "內功" else None,
        move_name=card.name if card is not None else None, move_say=draft.say, move_fire=fire_of_draft(state, content, draft),
        move_rare=draft.rare, move_stance=stance_of(draft.pose),
    )
    return scaled(art, power_scale_of(content, draft.score + seal_points(state, content)))


def move_problem(content: Content, world: WorldStateStore, name: str) -> str | None:
    """招名過不過得了：二到四個中文字，過一般的名字過濾（禁用名單、人物、內容武學……）。招名不必全服獨一。"""
    if not (MOVE_MIN <= len(name) <= MOVE_MAX):
        return MOVE_LINE
    return naming.name_problem(name, content, person=world.is_character_name)


def finish(
    state: GameState, content: Content, world: WorldStateStore, name: str, move: str | None = None,
) -> tuple[MartialArt | None, list[str]]:
    """取名、登記、付錢；名字被人用了回 (None, [NAME_TAKEN])，什麼都不收。品級一律 create_grade。
    move 是招名（空的照模型起的、再沒有照表的預設名）。"""
    problem = name_problem(state, content, world, name)
    if problem is not None:
        return None, [problem]
    move_name = naming.clean_name(move or "")
    if move_name and (problem := move_problem(content, world, move_name)) is not None:
        return None, [problem]
    draft = state.player.creating
    grade = content.config.arts.create_grade
    art = draft_art(state, content, draft, naming.clean_name(name), move_name or None)
    card = draft_move(state, content, draft, move_name or None)
    if not world.claim_skill_name(art):
        return None, [NAME_TAKEN]
    p = state.player
    need = 0 if draft.paid else price(state, content)  # 立意時收過了；這一版之前成形、還沒付的單子在這裡收
    if need:
        p.stats["xinde"] = _xinde(state) - need
        p.created_count += 1
    p.creating = None
    msgs = [CREATED_LINE.format(kind=art.kind, name=art.name), art.note]
    if card is not None:
        msgs.append(MOVE_SHOWN.format(card=tactics.card_text(card, tactics.title_of(card, art)) + (f"（{moves.RARE_WORD}）" if art.move_rare else "")))
    msgs += library.store_art(state, art, grade)
    if need:
        msgs.append(f"心得 -{need}")
    annals.note(state, content, annals.DEED, f"自創了一門{art.kind}【{art.name}】。", 3)
    if art.id in p.arts:
        note = team.compare_with_worn(state, content, world, art)
        msgs += ([note] if note else []) + [library.SWITCH_HINT]
    return art, msgs


def cancel(state: GameState) -> list[str]:
    draft = state.player.creating
    if draft is None:
        return [NO_DRAFT]
    state.player.creating = None
    return [CANCELLED_PAID.format(paid=draft.paid) if draft.paid else CANCELLED]


def prune(state: GameState, content: Content) -> None:
    """讀檔修補：這一版之前的三步單子（沒有 form）、走到不認得的步、表裡沒有的兵器，一律收掉（還沒付錢）。"""
    draft = state.player.creating
    if draft is None:
        return
    if not draft.form or draft.step not in STEPS or form_def(content, draft.kind, draft.form) is None:
        state.player.creating = None
        return
    if draft.step == "name" and not draft.colors:
        draft.step = "intent"


def _reroll_shop(content: Content) -> str | None:
    from .core.services import item_for  # 「去萬寶閣」停在哪一件：核心的錢包服務（開發規範手冊 3.10），不叫商城

    return item_for(content, "create_reroll")


def _every_cell_rare(content: Content) -> bool:
    rows = content.create_forms.moves
    return all(moves.has_rare(content, m.attribute, m.timing) for m in rows)


def _odds_word(x: float) -> str:
    """機會寫成「一成」「兩成」；不到一成寫百分比。"""
    tenths = round(x * 10, 6)
    if tenths >= 1 and tenths == int(tenths):
        return f"{'一兩三四五六七八九十'[int(tenths) - 1]}成"
    return f"{x * 100:g}%"


def view(state: GameState, content: Content, world: WorldStateStore) -> dict:
    """煉製頁「自創」那一塊要的資料。只讀。"on" 只看自創開不開（開季就有，不照週解鎖：企劃者 2026-10-28）。"""
    cfg = content.config.arts
    draft = state.player.creating
    base = {
        "on": on(content), "problem": allowed(state, content), "price": price(state, content), "xinde": _xinde(state),
        # 一季還能立幾門：create_per_season 0 是不限（None）
        "left": max(0, cfg.create_per_season - state.player.created_count) if cfg.create_per_season else None,
        "kinds": list(KINDS),
        "forms": {k: [{"key": f.key, "blurb": f.blurb, "bias": dict(f.bias)} for f in forms_of(content, k)] for k in KINDS},
        "presets": [{"name": p.name, "angles": {k: float(p.angles.get(k, 0.0)) for k in POSE_KEYS}} for p in content.create_forms.presets],
        "intent_max": INTENT_MAX, "grade": cfg.create_grade,
        "slots": {q: arts_mod.slot_count(content, q) for q in ("下品", "中品", "上品")},
        "step": "form" if draft is None else draft.step, "draft": None,
        "rerolls": state.player.create_rerolls,  # 手上的重悟帖（萬寶閣）
        "reroll_cap": cfg.create_reroll_cap,  # 一門最多重骰幾次
        # 手上沒有重悟帖時引去萬寶閣（Joy 2026-10-22）：賣重悟帖的那一件商品 id；商城關著、沒賣、手上還有帖是 None
        "shop": _reroll_shop(content) if state.player.create_rerolls <= 0 else None,
        # 擺式：怎麼擺是哪個勢、對應哪個時機（照 stance_of 認的先後）；網頁照同一套幾何即時讀出現在是哪一個（poseRead）
        "stances": {k: [{"stance": st, "timing": moves.timing_of(k, st), "how": STANCE_HOW[st]} for st in STANCE_ORDER] for k in KINDS},
        # 稀有路數一行（Joy 2026-10-22「怎麼擺都要有機會」）：表上每一格都有稀有的版本才寫，不列哪幾格、不給招名
        "rare_line": RARE_LINE.format(odds=_odds_word(cfg.move_rare_odds)) if _every_cell_rare(content) else "",
        "pose_weights": list(cfg.create_pose_weights), "attributes": list(ATTRIBUTES),  # 網頁擺式時即時算主屬性（top_of 的同一套）
    }
    if draft is None:
        return base
    base["draft"] = {
        "kind": draft.kind, "form": draft.form, "pose": dict(draft.pose), "pose_read": read_text(pose_read(draft.pose)),
        "intent": draft.intent, "read": list(draft.read), "lean": draft.lean,
        "read_text": ("意偏" + "、".join(draft.read) if draft.read else "意不偏一路") + LEAN_TEXT.get(draft.lean, ""),
        "colors": [list(c) for c in draft.colors], "colors_text": [arts_mod.color_text(c) for c in draft.colors],
        "redo": draft.redo,
        "paid": draft.paid,  # 立意時付了多少心得（0＝還沒付）
        "reroll_left": max(0, content.config.arts.create_reroll_cap - draft.rerolled),  # 這一門還能重骰幾次
        "power": "",
        # 主屬性要的權重，不含姿勢那兩路（擺式時網頁照拖到一半的姿勢加上 pose_weights，取最高的那一路＝top_of）
        "base_weights": weights(content, draft, pose=False),
    }
    if draft.colors:  # 成形了：換上這一門的戰力（招式與絕學稿案第二輪：付心得之前就知道值不值）
        mine = might.now(state, content, world)
        first, full = might.with_new(state, content, world, draft_art(state, content, draft, DRAFT_ID), cfg.create_grade)
        base["draft"]["power"] = MIGHT_LINE.format(now=mine, first=first, full=full)
        base["draft"]["might"] = {"now": mine, "first": first, "full": full}
    stance = stance_of(draft.pose)
    base["draft"]["stance"] = stance  # 擺式讀出的勢（攻勢／守勢／變勢／起勢）
    base["draft"]["timing"] = moves.timing_of(draft.kind, stance)
    base["draft"]["main"] = top_of(content, draft)  # 照擺定的姿勢與意，現在的主屬性
    move = draft_move(state, content, draft)
    fire = fire_of_draft(state, content, draft) if draft.colors else None
    marks = marks_of(draft.colors, fire, draft.rare) if draft.colors else []
    common = moves.cell(content, base["draft"]["main"], base["draft"]["timing"]) if draft.rare and move is not None else None
    base["draft"].update({
        # 成形之後長出來的招：蓋自己名號第一個字的私印，照練開之後的數算；撞到稀有路數的後面補小章
        "tactic": (tactics.card_text(move, state.player.name[:1] or tactics.MINOR_TITLE) + (f"（{moves.RARE_WORD}）" if draft.rare else "")) if move is not None else "",
        "rare_hit": RARE_HIT.format(common=common.name) if common is not None else "",
        "move": move.name if move is not None else "", "say": move.say if move is not None else "",
        "fire": fire, "look": look_text(marks) if draft.colors else "", "tier": tier_of(marks) if draft.colors else None, "marks": marks,
        "seal": state.player.name[:1],
    })
    return base
