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
5. 立名（finish）：自己取名、可以多付心得加分；這一步才付心得。品級引擎擲（grade_odds，意分＋加分往上推），
   品級決定開幾格（下 2、中 3、上 4，照第 4 步的前幾格）；威力從第一成起練；注解就是那一句意。

價錢：Config.arts.create_xinde × create_step^（這一季已自創幾門），一季最多 create_per_season 門。
只改狀態與回傳訊息；數字全由這裡算，模型只給一個分數與兩個屬性字。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from pydantic import BaseModel, Field

from . import annals, arts as arts_mod, library, naming, team, treasures
from .martial_arts import ATTRIBUTES, QUALITY_BASE_POWER, QUALITY_TOP_POWER, MartialArt, scaled
from .models import Content
from .ollama_client import OllamaClient
from .rules import add_chronicle
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
NO_REDO = "已經重來過了，這一回就照這個形立名吧（或擱下重起）。"  # 待 joy 潤
NAME_TAKEN = "這個名字已經有人用了，換一個。"
EXTRA_LINE = "加付的心得要是 0 或正數，而且付得起。"
BEGUN_LINE = "你握起{form}，想立一門自己的{kind}。先擺個架式。"  # 待 joy 潤
POSED_LINE = "你擺定了這一式：{read}。"  # 待 joy 潤
FORMED_LINE = "你閉目良久，「{intent}」——這門功夫有了形：{colors}。"  # 待 joy 潤
BACK_LINE = "你散了架式，重新來過。"  # 待 joy 潤
CREATED_LINE = "你開宗立派，自創了一門{kind}【{name}】（{grade}）！"  # 待 joy 潤
CHRONICLE_LINE = "{who}自創了一門{kind}【{name}】。"
CANCELLED = "你把這門還沒成形的功夫擱下了。"
BONUS_LINE = "多付的 {extra} 點心得化成了底子（+{bonus} 分）。"
FLAT_LINE = "此式平正，不偏一路"  # 待 joy 潤
LEAN_TEXT = {"正": "，帶一股正氣", "邪": "，帶一股邪氣", "無": ""}  # 待 joy 潤


# ── 價錢與門檻 ──────────────────────────────────────────


def on(content: Content) -> bool:
    return content.config.arts.create_xinde > 0 and content.config.arts.create_per_season > 0


def price(state: GameState, content: Content) -> int:
    cfg = content.config.arts
    return int(round(cfg.create_xinde * (cfg.create_step ** state.player.created_count)))


def allowed(state: GameState, content: Content) -> str | None:
    """現在能不能自創（每一步之前都問它）；None＝可以。"""
    from . import prologue

    cfg = content.config.arts
    if not on(content):
        return OFF
    if prologue.active(state, content):
        return IN_PROLOGUE
    if state.player.naming is not None:
        return NAMING_FIRST
    if state.player.created_count >= cfg.create_per_season:
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


def pose_scores(pose: dict[str, float]) -> dict[str, float]:
    """姿勢讀出來的偏向（只有剛柔快慢虛實；陰陽靠兵器與意）。"""
    j = joints(pose)
    lh, rh, lf, rf = j["lHa"], j["rHa"], j["lFt"], j["rFt"]
    reach = max(abs(rh[0] - CX), abs(lh[0] - CX)) / (UA + FA)
    high = max(SY - rh[1], SY - lh[1]) / (UA + FA)
    tucked = math.hypot(rh[0] - CX, rh[1] - (SY + 20)) < 30 and math.hypot(lh[0] - CX, lh[1] - (SY + 20)) < 30
    spread = abs(lf[0] - rf[0]) / (TH + SH)
    lift = min(lf[1], rf[1]) < HIPY + TH * 1.3
    lean = pose.get("t", 0.0)
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
    if _xinde(state) < need:
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


READ_PREDICT = 120
SYSTEM_PROMPT = (
    "你是武俠小說裡評判武功立意的宗師。玩家要自創一門功夫，已經挑好兵器、擺好架式，最後寫下一句「意」。\n"
    "1. score：這一句意寫得好不好，0～100 的整數。有神、有象、合乎武理給高分；空洞、灌水、亂寫、跟功夫無關給低分。\n"
    "2. attributes：這一句意的神韻偏向哪幾路，從「陰、陽、剛、柔、快、慢、虛、實」裡挑零到兩個字，最像的放前面；"
    "看不出偏向就給空清單。陰是陰柔詭譎、陽是光明熾烈、剛是剛猛、柔是綿柔借力、快是迅捷、慢是沉穩後發、虛是虛實變幻、實是紮實厚重。\n"
    "3. lean：這一句意是正派、邪派還是不分，只回「正」「邪」「無」其中一個。\n"
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
    return IntentReading(score=clamp_score(reading.score), attributes=attrs, lean=lean)


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


def weights(content: Content, draft: CreateDraft) -> dict[str, float]:
    """每一路屬性的權重：底＋兵器或行功之法的偏向＋姿勢讀出的兩路＋意讀出的兩路。"""
    cfg = content.config.arts
    w = {a: float(cfg.create_base_weight) for a in ATTRIBUTES}
    f = form_def(content, draft.kind, draft.form)
    for a, n in (f.bias.items() if f is not None else []):
        if a in w:
            w[a] += float(n)
    for a, n in zip(pose_read(draft.pose), cfg.create_pose_weights):
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


def roll_colors(content: Content, draft: CreateDraft, rng: random.Random) -> list[list[str]]:
    """四格的顏色：第一格是權重最高那一路的單色；其餘照 create_slot_odds 擲單、雙、任（意不偏時任色加倍）。"""
    cfg = content.config.arts
    w = weights(content, draft)
    top = max(ATTRIBUTES, key=lambda a: (w[a], -ATTRIBUTES.index(a)))
    odds = {k: float(v) for k, v in cfg.create_slot_odds.items()}
    if not draft.read:
        odds["全"] = odds.get("全", 0.0) * cfg.create_neutral_any_scale
    out: list[list[str]] = [[top]]
    for _ in range(max(0, cfg.create_slots - 1)):
        roll = rng.random() * sum(odds.values())
        shape = "全"
        acc = 0.0
        for k in ("單", "雙", "全"):
            acc += odds.get(k, 0.0)
            if roll < acc:
                shape = k
                break
        if shape == "單":
            out.append([_pick(rng, w)])
        elif shape == "雙":
            first = _pick(rng, w)
            out.append([first, _pick(rng, w, skip=first)])
        else:
            out.append([])
    return out


def colors_text(colors: list[list[str]]) -> str:
    return "、".join(arts_mod.color_text(c) for c in colors)


def set_intent(
    state: GameState, content: Content, world: WorldStateStore, text: str, reading: IntentReading | None = None,
) -> list[str]:
    """C 段（或直接呼叫）：記下意與讀出來的東西，馬上成形（擲四格顏色）。reading 沒給照關鍵字表讀。只改單子、不收錢。"""
    problem = intent_problem(state, content, text)
    if problem is not None:
        return [problem]
    draft = state.player.creating
    reading = clean_reading(reading) if reading is not None else fallback_read(content, text)
    draft.intent = clean_intent(text)
    draft.read = list(reading.attributes)
    draft.lean = reading.lean
    draft.score = reading.score
    draft.colors = roll_colors(content, draft, random.Random(seed_of(state, world, draft)))
    draft.rolls += 1
    draft.step = "name"
    return [FORMED_LINE.format(intent=draft.intent, colors=colors_text(draft.colors))]


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
    draft.step = to
    return [BACK_LINE]


# ── 第五步：立名、擲品級、登記 ───────────────────────────


def bonus_of(content: Content, extra: int) -> int:
    cfg = content.config.arts
    return min(cfg.create_bonus_cap, 5 * (max(0, extra) // cfg.create_bonus_per))


def seal_points(state: GameState, content: Content) -> int:
    """玉璽赤璋（fuse_points）：加在自創的意分上（夾之前加，品級機率照它挪）。"""
    return int(treasures.amount(state, content, "fuse_points"))


POWER_LINE = "底子：同品級威力的 {pct}%（意寫得越好越厚，多付心得也加）。"  # 待 joy 潤


def power_scale_of(content: Content, points: int) -> float:
    """自創的基本威力倍數：意分＋加分＋赤璋（夾 0～100）從 power_scale_range 的下限線性推到上限。"""
    low, high = content.config.arts.power_scale_range
    return round(low + (high - low) * max(0, min(100, points)) / 100, 3)


def grade_odds(content: Content, score_value: int, bonus: int) -> dict[str, float]:
    """品級機率（%）：從 create_odds 起算，意分＋加分每一分把下品挪 create_point_shift 個百分點，三分之二到上品、三分之一到中品。"""
    cfg = content.config.arts
    odds = {q: float(cfg.create_odds.get(q, 0)) for q in ("下品", "中品", "上品")}
    move = min(odds["下品"], (score_value + bonus) * cfg.create_point_shift)
    odds["下品"] -= move
    odds["上品"] += move * 2 / 3
    odds["中品"] += move / 3
    return odds


def roll_grade(content: Content, score_value: int, bonus: int, rng: random.Random) -> str:
    odds = grade_odds(content, score_value, bonus)
    roll = rng.random() * sum(odds.values())
    acc = 0.0
    for grade in ("下品", "中品", "上品"):
        acc += odds[grade]
        if roll < acc:
            return grade
    return "上品"


def name_problem(state: GameState, content: Content, world: WorldStateStore, name: str, extra: int = 0) -> str | None:
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
    if extra < 0 or _xinde(state) < need + extra:
        return EXTRA_LINE if extra else XINDE_LINE.format(price=need, have=_xinde(state))
    return None


def affinity_of(colors: list[list[str]]) -> list[str]:
    """登記的相容屬性：開著的格子裡出現的屬性（照先後、不重複）。"""
    return list(dict.fromkeys(a for c in colors for a in c))


def finish(
    state: GameState, content: Content, world: WorldStateStore, name: str, rng: random.Random, extra: int = 0,
) -> tuple[MartialArt | None, list[str]]:
    """取名、擲品級、登記、付錢；名字被人用了回 (None, [NAME_TAKEN])，什麼都不收。"""
    problem = name_problem(state, content, world, name, extra)
    if problem is not None:
        return None, [problem]
    draft = state.player.creating
    clean = naming.clean_name(name)
    bonus = bonus_of(content, extra)
    points = draft.score + seal_points(state, content)
    grade = roll_grade(content, points, bonus, rng)
    affinity = affinity_of(draft.colors[: arts_mod.slot_count(content, grade)])
    art = MartialArt(
        id=clean, name=clean, kind=draft.kind, quality="下品", attribute=affinity[0] if affinity else "",
        base_power=QUALITY_BASE_POWER["下品"], top_power=QUALITY_TOP_POWER["下品"], origin="created",
        creator=state.player.name, creator_shown=state.player.name, note=draft.intent, lean=draft.lean,
        affinity=affinity, slot_colors=[list(c) for c in draft.colors], pose=dict(draft.pose),
        weapon=draft.form if draft.kind == "武學" else None, method=draft.form if draft.kind == "內功" else None,
    )
    art = scaled(art, power_scale_of(content, points + bonus))
    if not world.claim_skill_name(art):
        return None, [NAME_TAKEN]
    p = state.player
    need = price(state, content)
    p.stats["xinde"] = _xinde(state) - need - extra
    p.created_count += 1
    p.creating = None
    msgs = [CREATED_LINE.format(kind=art.kind, name=art.name, grade=grade), art.note]
    if bonus:
        msgs.append(BONUS_LINE.format(extra=extra, bonus=bonus))
    msgs += library.store_art(state, art, grade)
    msgs.append(f"心得 -{need + extra}")
    add_chronicle(state, CHRONICLE_LINE.format(who=p.name, kind=art.kind, name=art.name))
    annals.note(state, content, annals.DEED, f"自創了一門{art.kind}【{art.name}】。", 3)
    if art.id in p.arts:
        note = team.compare_with_worn(state, content, world, art)
        msgs += ([note] if note else []) + [library.SWITCH_HINT]
    return art, msgs


def cancel(state: GameState) -> list[str]:
    if state.player.creating is None:
        return [NO_DRAFT]
    state.player.creating = None
    return [CANCELLED]


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


def view(state: GameState, content: Content, world: WorldStateStore) -> dict:
    """煉製頁「自創」那一塊要的資料。只讀。"""
    cfg = content.config.arts
    draft = state.player.creating
    base = {
        "on": on(content), "problem": allowed(state, content), "price": price(state, content), "xinde": _xinde(state),
        "left": max(0, cfg.create_per_season - state.player.created_count), "kinds": list(KINDS),
        "forms": {k: [{"key": f.key, "blurb": f.blurb, "bias": dict(f.bias)} for f in forms_of(content, k)] for k in KINDS},
        "presets": [{"name": p.name, "angles": {k: float(p.angles.get(k, 0.0)) for k in POSE_KEYS}} for p in content.create_forms.presets],
        "intent_max": INTENT_MAX, "bonus_per": cfg.create_bonus_per, "bonus_cap": cfg.create_bonus_cap,
        "slots": {q: arts_mod.slot_count(content, q) for q in ("下品", "中品", "上品")},
        "step": "form" if draft is None else draft.step, "draft": None,
    }
    if draft is None:
        return base
    base["draft"] = {
        "kind": draft.kind, "form": draft.form, "pose": dict(draft.pose), "pose_read": read_text(pose_read(draft.pose)),
        "intent": draft.intent, "read": list(draft.read), "lean": draft.lean,
        "read_text": ("意偏" + "、".join(draft.read) if draft.read else "意不偏一路") + LEAN_TEXT.get(draft.lean, ""),
        "colors": [list(c) for c in draft.colors], "colors_text": [arts_mod.color_text(c) for c in draft.colors],
        "redo": draft.redo, "odds": grade_odds(content, draft.score + seal_points(state, content), 0),
        "power": POWER_LINE.format(pct=round(power_scale_of(content, draft.score + seal_points(state, content)) * 100)),
    }
    return base
