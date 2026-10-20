"""自創武學（武學重構，Joy 2026-10-20「玩家可以消耗大量心得直接自創一門武學……例如設定形意、式、最後取名」）。

三步儀式，單子記在 PlayerState.creating（state.CreateDraft）：
1. 形意（intent）：內功或武學、相容屬性（最多 MAX_AFFINITY 種；空著是兼容並蓄、什麼意境都收，代價是少一格槽）、正邪、
   20 字的「意」。模型只評這一句意寫得好不好（0～100，夾 5～85；評不到 DEFAULT_SCORE），三段式同隨口應對：
   A Game.create_request（只讀）→ B create.score（鎖外）→ C Game.create_intent(score=)。
2. 式（form）：武學挑兵器種類（內功沒有）；從悟過、還沒裝在別門上的意境裡挑一個當起手式（屬性要在相容屬性裡），登記時裝進第一格。
3. 取名（name）：自己取（naming.name_problem、全服不重名，world.claim_skill_name 原子判斷），可以多付心得加分；這一步才付心得。
   品級由引擎擲（create_odds 起算，意分與加分每一分把下品的機率往上挪 create_point_shift 個百分點、三分之二到上品、三分之一到中品；
   絕學不在這裡出），威力從第一成起練；注解就是那一句意。登記成全服武學（首創者是自己、origin "created"），別人學不到；
   江湖史一行、行狀一筆。
價錢：Config.arts.create_xinde × create_step^（這一季已自創幾門），一季最多 create_per_season 門。
只改狀態與回傳訊息；數字全由這裡算，模型只給一個分數。
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from pydantic import BaseModel

from . import annals, arts as arts_mod, insights, library, naming, team, treasures
from .martial_arts import ATTRIBUTES, QUALITY_BASE_POWER, QUALITY_TOP_POWER, MartialArt
from .models import WEAPON_KINDS, Content
from .ollama_client import OllamaClient
from .rules import add_chronicle
from .state import CreateDraft, GameState
from .world_state import WorldStateStore

KINDS = ("內功", "武學")
LEANS = ("無", "正", "邪")
MAX_AFFINITY = 3
INTENT_MAX = 20
INTENT_MIN = 2
DEFAULT_SCORE = 40
SCORE_FLOOR, SCORE_CAP = 5, 85
UNIVERSAL_SLOT_ADJUST = -1  # 兼容並蓄少一格槽

OFF = "這裡不興自創武學。"
IN_PROLOGUE = "師父還沒教到這一步。"
NAMING_FIRST = "你練成絕學的武學還沒定名，先替它取好正式的名字。"
CAP_LINE = "這一季你已經自創了 {n} 門，再多也立不住了。"
FULL_LINE = "功法庫滿了，先熔掉一門再立新派。"
XINDE_LINE = "心得不足：自創一門要 {price}（你有 {have}）。"
NO_DRAFT = "你還沒起意。先到「煉製」寫下這一門的形意。"
WRONG_STEP = "這一步不對：先{what}。"
KIND_LINE = "要立的是內功還是武學？"
LEAN_LINE = "正邪只能是正、邪或無。"
AFFINITY_LINE = "相容屬性只能從陰陽剛柔快慢虛實裡挑，最多 {n} 種、不重複。"
INTENT_LINE = f"「意」要 {INTENT_MIN}～{INTENT_MAX} 個字，一句話說這門功夫的神。"
WEAPON_LINE = "武學要挑一種兵器：{kinds}。"
NEIGONG_WEAPON = "內功不配兵器。"
INSIGHT_LINE = "起手式要是你悟過、還沒裝在別門上的意境。"
INSIGHT_AFFINITY = "「{insight}」不在這門的相容屬性（{attrs}）裡。"
NAME_TAKEN = "這個名字已經有人用了，換一個。"
EXTRA_LINE = "加付的心得要是 0 或正數，而且付得起。"
STARTED_LINE = "你閉目良久，心中隱隱有了一門{kind}的形：{intent}"  # 待 joy 潤
FORMED_LINE = "你以「{insight}」為起手式，一招一式演了一遍，這門功夫有了式。"  # 待 joy 潤
CREATED_LINE = "你開宗立派，自創了一門{kind}【{name}】（{grade}）！"  # 待 joy 潤
CHRONICLE_LINE = "{who}自創了一門{kind}【{name}】。"
CANCELLED = "你把這門還沒成形的功夫擱下了。"
BONUS_LINE = "多付的 {extra} 點心得化成了底子（+{bonus} 分）。"


# ── 價錢與門檻 ──────────────────────────────────────────


def on(content: Content) -> bool:
    return content.config.arts.create_xinde > 0 and content.config.arts.create_per_season > 0


def price(state: GameState, content: Content) -> int:
    cfg = content.config.arts
    return int(round(cfg.create_xinde * (cfg.create_step ** state.player.created_count)))


def allowed(state: GameState, content: Content) -> str | None:
    """現在能不能自創（三步之前都問它）；None＝可以。"""
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


# ── 第一步：形意 ────────────────────────────────────────


def clean_intent(text: str) -> str:
    return " ".join(str(text or "").split())


def intent_problem(state: GameState, content: Content, kind: str, affinity: list[str], lean: str, text: str) -> str | None:
    problem = allowed(state, content)
    if problem is not None:
        return problem
    if kind not in KINDS:
        return KIND_LINE
    if lean not in LEANS:
        return LEAN_LINE
    if len(affinity) > MAX_AFFINITY or len(set(affinity)) != len(affinity) or any(a not in ATTRIBUTES for a in affinity):
        return AFFINITY_LINE.format(n=MAX_AFFINITY)
    text = clean_intent(text)
    if not (INTENT_MIN <= len(text) <= INTENT_MAX):
        return INTENT_LINE
    need = price(state, content)
    if _xinde(state) < need:
        return XINDE_LINE.format(price=need, have=_xinde(state))
    return None


@dataclass(frozen=True)
class IntentRequest:
    """形意那一步的 A 段單子：鎖外請模型評這一句意。"""

    kind: str
    affinity: tuple[str, ...]
    lean: str
    text: str
    name: str


class IntentScore(BaseModel):
    score: int


SCORE_PREDICT = 24
SYSTEM_PROMPT = (
    "你是武俠小說裡評判武功立意的宗師。玩家要自創一門功夫，先寫下一句「意」。"
    "只評這一句意寫得好不好：有神、有象、合乎武理給高分，空洞、灌水、亂寫、跟功夫無關給低分。"
    "只回 0～100 的整數 score。"
)


def request(state: GameState, kind: str, affinity: list[str], lean: str, text: str) -> IntentRequest:
    return IntentRequest(kind, tuple(affinity), lean, clean_intent(text), state.player.name)


def score(client: OllamaClient | None, req: IntentRequest) -> int:
    """B 段：模型評意分；叫不動回 DEFAULT_SCORE。夾在 SCORE_FLOOR～SCORE_CAP 由 clamp_score 做（C 段再夾一次）。"""
    if client is None:
        return DEFAULT_SCORE
    attrs = "、".join(req.affinity) if req.affinity else "兼容並蓄"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"要立的：{req.kind}（屬性傾向：{attrs}；{req.lean}派）\n這一句意：「{req.text}」"},
    ]
    try:
        result = client.chat_structured(messages, IntentScore, temperature=0.3, num_predict=SCORE_PREDICT, required_fields=["score"])
    except Exception:
        return DEFAULT_SCORE
    return max(0, min(100, int(result.score)))


def clamp_score(value: int | None) -> int:
    if value is None:
        return DEFAULT_SCORE
    return max(SCORE_FLOOR, min(SCORE_CAP, int(value)))


def start(
    state: GameState, content: Content, kind: str, affinity: list[str], lean: str, text: str, score_value: int | None = None,
) -> list[str]:
    problem = intent_problem(state, content, kind, affinity, lean, text)
    if problem is not None:
        return [problem]
    state.player.creating = CreateDraft(
        kind=kind, affinity=list(affinity), lean=lean, intent=clean_intent(text), score=clamp_score(score_value), step="form",
    )
    return [STARTED_LINE.format(kind=kind, intent=clean_intent(text))]


# ── 第二步：式 ──────────────────────────────────────────


def _draft(state: GameState, step: str) -> tuple[CreateDraft | None, str | None]:
    draft = state.player.creating
    if draft is None:
        return None, NO_DRAFT
    if draft.step != step:
        return None, WRONG_STEP.format(what="演式" if draft.step == "form" else "取名")
    return draft, None


def insight_choices(state: GameState, content: Content, world: WorldStateStore) -> list[str]:
    """式那一步挑得了的起手式：悟過、沒裝在別門上、屬性在相容屬性裡。"""
    draft = state.player.creating
    if draft is None:
        return []
    out = []
    for insight_id in state.player.insights:
        if arts_mod.where_slotted(state, insight_id) is not None:
            continue
        ins = insights.resolve(insight_id, content, world, state)
        if ins is None or (draft.affinity and ins.attribute not in draft.affinity):
            continue
        out.append(insight_id)
    return out


def form_problem(state: GameState, content: Content, world: WorldStateStore, weapon: str | None, insight_id: str) -> str | None:
    problem = allowed(state, content)
    if problem is not None:
        return problem
    draft, problem = _draft(state, "form")
    if problem is not None:
        return problem
    if draft.kind == "武學" and weapon not in WEAPON_KINDS:
        return WEAPON_LINE.format(kinds="、".join(WEAPON_KINDS))
    if draft.kind == "內功" and weapon:
        return NEIGONG_WEAPON
    if insight_id not in state.player.insights or arts_mod.where_slotted(state, insight_id) is not None:
        return INSIGHT_LINE
    ins = insights.resolve(insight_id, content, world, state)
    if ins is None:
        return INSIGHT_LINE
    if draft.affinity and ins.attribute not in draft.affinity:
        return INSIGHT_AFFINITY.format(insight=ins.name, attrs="、".join(draft.affinity))
    return None


def form(state: GameState, content: Content, world: WorldStateStore, weapon: str | None, insight_id: str) -> list[str]:
    problem = form_problem(state, content, world, weapon, insight_id)
    if problem is not None:
        return [problem]
    draft = state.player.creating
    draft.weapon = weapon if draft.kind == "武學" else None
    draft.insight = insight_id
    draft.step = "name"
    ins = insights.resolve(insight_id, content, world, state)
    return [FORMED_LINE.format(insight=ins.name if ins else insight_id)]


# ── 第三步：取名、擲品級、登記 ───────────────────────────


def bonus_of(content: Content, extra: int) -> int:
    cfg = content.config.arts
    return min(cfg.create_bonus_cap, 5 * (max(0, extra) // cfg.create_bonus_per))


def seal_points(state: GameState, content: Content) -> int:
    """玉璽赤璋（fuse_points）：合成不擲品質之後改加在自創的意分上（夾之前加，品級機率照它挪）。"""
    return int(treasures.amount(state, content, "fuse_points"))


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
    if draft.insight not in state.player.insights or arts_mod.where_slotted(state, draft.insight) is not None:
        return INSIGHT_LINE  # 式之後意境熔了、裝到別門上了：回去重演式
    problem = naming.name_problem(naming.clean_name(name), content, person=world.is_character_name)
    if problem is not None:
        return problem
    need = price(state, content)
    if extra < 0 or _xinde(state) < need + extra:
        return EXTRA_LINE if extra else XINDE_LINE.format(price=need, have=_xinde(state))
    return None


def finish(
    state: GameState, content: Content, world: WorldStateStore, name: str, rng: random.Random, extra: int = 0,
) -> tuple[MartialArt | None, list[str]]:
    """取名、擲品級、登記、付錢、裝起手式；名字被人用了回 (None, [NAME_TAKEN])，什麼都不收。"""
    problem = name_problem(state, content, world, name, extra)
    if problem is not None:
        return None, [problem]
    draft = state.player.creating
    clean = naming.clean_name(name)
    bonus = bonus_of(content, extra)
    grade = roll_grade(content, draft.score + seal_points(state, content), bonus, rng)
    art = MartialArt(
        id=clean, name=clean, kind=draft.kind, quality="下品", attribute=draft.affinity[0] if draft.affinity else "",
        base_power=QUALITY_BASE_POWER["下品"], top_power=QUALITY_TOP_POWER["下品"], origin="created",
        creator=state.player.name, creator_shown=state.player.name, note=draft.intent, lean=draft.lean,
        affinity=list(draft.affinity), weapon=draft.weapon,
        slot_adjust=UNIVERSAL_SLOT_ADJUST if not draft.affinity else 0,
    )
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
    if draft.insight:
        msgs += arts_mod.slot(state, content, world, art.id, draft.insight)
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


def view(state: GameState, content: Content, world: WorldStateStore) -> dict:
    """煉製頁「自創」那一塊要的資料：能不能、價錢、一季還剩幾門、走到哪一步、每一步的選項。只讀。"""
    cfg = content.config.arts
    draft = state.player.creating
    problem = allowed(state, content)
    base = {
        "on": on(content), "problem": problem, "price": price(state, content), "xinde": _xinde(state),
        "left": max(0, cfg.create_per_season - state.player.created_count), "kinds": list(KINDS), "leans": list(LEANS),
        "attributes": list(ATTRIBUTES), "max_affinity": MAX_AFFINITY, "intent_max": INTENT_MAX, "weapons": list(WEAPON_KINDS),
        "bonus_per": cfg.create_bonus_per, "bonus_cap": cfg.create_bonus_cap, "step": "intent" if draft is None else draft.step,
        "draft": None,
    }
    if draft is None:
        return base
    choices = []
    for insight_id in insight_choices(state, content, world):
        ins = insights.resolve(insight_id, content, world, state)
        if ins is not None:
            choices.append({"id": insight_id, "name": ins.name, "attribute": ins.attribute,
                            "mark": arts_mod.strength_mark(arts_mod.strength_of(state, insight_id))})
    base["draft"] = {
        "kind": draft.kind, "affinity": list(draft.affinity), "affinity_text": "、".join(draft.affinity) or "兼容並蓄",
        "lean": draft.lean, "intent": draft.intent, "weapon": draft.weapon, "insight": draft.insight,
        "insight_choices": choices, "odds": grade_odds(content, draft.score + seal_points(state, content), 0),
    }
    return base
