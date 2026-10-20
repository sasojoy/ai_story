"""武學重構（Joy 2026-10-20「我想改整個架構，不要縫縫補補」；定案 /mnt/project-files/plan/武學重構定案.md）：

| 東西 | 是什麼 |
|---|---|
| 武學（門面） | 全服登記的那一份只有 id、名字、內功／武學、兵器種類、來歷、首創者、注解 |
| 品級 | 玩家自己那一份（PlayerState.art_quality）：只管威力上限（martial_arts.QUALITY_TOP_POWER）與意境槽數（Config.arts.slots） |
| 威力 | 心得練上去的成數（第一成到第十成，power_at），上限照品級 |
| 意境槽 | PlayerState.art_slots：功法 id → 每一格裝的意境 id（None 是空的）；一個意境同時只能裝在一門上 |
| 意境 | 就是技能：基本意境（風火水山浩然血煞）是那個屬性的一般功效、強度（PlayerState.insight_strength，●～●●●）是層數；
|       | 不同意境合出來的是那個屬性的高階技能（traits.json 的 high）；秘方合出來的帶特別功效 |
| 相容屬性 | MartialArt.affinity：意境槽只收這幾種屬性的意境（追風步只收快與快的複合）；空的＝兼容並蓄、什麼都收（基礎武學） |
| 屬性 | 武學自己的屬性＝相容屬性的第一個；兼容並蓄的沒有屬性（不搭、不剋、不吃一門打不遍）；正邪照浩然、血煞那兩招 |
| 本命武學 | 內容寫死的槽（SkillDef.traits、tactic），不能裝、不能當料；部下用的上品武學也是寫死的 |

apply() 把玩家自己那一份換成「身上的樣子」（traits／special／high／attribute／lean 照槽填），下游（traits.loadout、tactics、
team.pairing、weapons）照舊讀那幾個欄位，一個字不改。
"""
from __future__ import annotations

from .martial_arts import QUALITIES, MartialArt, Insight, power_at
from .models import Content, GeneralTrait, HighTrait, SpecialTrait
from .state import GameState
from .world_state import WorldStateStore

MAX_STRENGTH = 3
STRENGTH_MARKS = {1: "●", 2: "●●", 3: "●●●"}
ULTIMATE_SLOT = "絕招"  # 絕學第五格

LEAN_OF = {"正": "正", "邪": "邪"}


def fixed(content: Content, art_id: str) -> bool:
    """槽寫死的武學：內容寫了功效或戰法的（本命武學）、不是下品的內容武學（部下用的上品）。基礎武學（下品）有空槽。"""
    s = content.skills.get(art_id)
    return s is not None and (bool(s.traits) or s.tactic is not None or s.quality != "下品")


def slot_count(content: Content, quality: str) -> int:
    return int(content.config.arts.slots.get(quality, 2))


def slots_of(state: GameState, content: Content, art: MartialArt) -> list[str | None]:
    """這一門的槽（照品級的格數補齊、多的砍掉）。寫死的武學回空清單。"""
    if fixed(content, art.id):
        return []
    n = slot_count(content, state.player.art_quality.get(art.id, art.quality))
    raw = list(state.player.art_slots.get(art.id, []))[:n]
    return raw + [None] * (n - len(raw))


def strength_of(state: GameState, insight_id: str) -> int:
    return max(1, min(MAX_STRENGTH, int(state.player.insight_strength.get(insight_id, 1))))


def strength_mark(n: int) -> str:
    return STRENGTH_MARKS.get(max(1, min(MAX_STRENGTH, n)), "●")


def where_slotted(state: GameState, insight_id: str) -> str | None:
    """這個意境裝在哪一門上；沒裝是 None。"""
    for art_id, slots in state.player.art_slots.items():
        if insight_id in slots:
            return art_id
    return None


# ── 意境＝技能 ──────────────────────────────────────────


def general_of(content: Content, attribute: str) -> GeneralTrait | None:
    return next((t for t in content.traits.general if t.attribute == attribute), None)


def high_of(content: Content, attribute: str) -> HighTrait | None:
    return next((h for h in content.traits.high if h.attribute == attribute), None)


def special_of(content: Content, special_id: str | None) -> SpecialTrait | None:
    if not special_id:
        return None
    return next((t for t in content.traits.special if t.id == special_id), None)


def is_compound(content: Content, insight: Insight) -> bool:
    """不同意境合出來的（高階技能）：有兩個來源、而且不是同一個意境合自己。基本意境與自己悟的不是。"""
    return len(insight.parents) == 2 and insight.parents[0] != insight.parents[1] and insight.id not in content.insights


def skill_name(content: Content, insight: Insight) -> str:
    """這個意境是哪一招（技能的名字）：秘方的特別功效 → 高階 → 一般功效；內容沒有功效表時是屬性。"""
    sp = special_of(content, insight.secret_special) if insight.secret_special else None
    if sp is not None:
        return sp.name
    if is_compound(content, insight):
        h = high_of(content, insight.attribute)
        if h is not None:
            return h.name
    g = general_of(content, insight.attribute)
    return g.name if g is not None else insight.attribute


def skill_desc(content: Content, insight: Insight, strength: int) -> str:
    """這一招在回合裡做什麼（卡上那一句，數字照強度）。"""
    from . import traits as traits_mod

    sp = special_of(content, insight.secret_special) if insight.secret_special else None
    if sp is not None:
        return sp.desc.replace("{value}", traits_mod._value(sp.hook, sp.amount))
    if is_compound(content, insight):
        h = high_of(content, insight.attribute)
        if h is not None:
            return h.desc
    g = general_of(content, insight.attribute)
    if g is None:
        return ""
    number = min(g.cap, g.per_layer * strength)
    extra = min(g.extra_cap, g.extra_per_layer * strength)
    return g.desc.replace("{value}", traits_mod._value(g.hook, number)).replace("{extra}", traits_mod._value(g.hook, extra))


def skill_weight(content: Content, insight: Insight, strength: int) -> float:
    """戰力裡這一招值多少（Config.arts 的三個權重 × 強度；高階與特別功效強度固定算 1）。"""
    cfg = content.config.arts
    if insight.secret_special:
        return cfg.special_weight
    if is_compound(content, insight):
        return cfg.high_weight
    return cfg.general_weight * strength


# ── 身上的樣子 ───────────────────────────────────────────


def apply(state: GameState, content: Content, world: WorldStateStore, art: MartialArt | None) -> MartialArt | None:
    """玩家自己那一份「身上的樣子」：traits（一般功效，一層一個屬性，照強度重複）、special、high、attribute、lean 照槽填。
    寫死的武學原樣回。art 要是 team.player_art 那一份（品質照自己的）。"""
    if art is None or fixed(content, art.id):
        return art
    from . import insights as insights_mod

    traits: list[str] = []
    special = None
    high = None
    lean = "無"
    lean_strength = 0
    for insight_id in slots_of(state, content, art):
        if insight_id is None:
            continue
        ins = insights_mod.resolve(insight_id, content, world, state)
        if ins is None:
            continue
        strength = strength_of(state, insight_id)
        if ins.secret_special and special is None and special_of(content, ins.secret_special) is not None:
            special = ins.secret_special
        elif is_compound(content, ins) and high is None and high_of(content, ins.attribute) is not None:
            high = high_of(content, ins.attribute).id
        else:
            traits += [ins.attribute] * strength
        if ins.lean in LEAN_OF and strength > lean_strength:
            lean, lean_strength = ins.lean, strength
    attribute = art.affinity[0] if art.affinity else ""
    return art.model_copy(update={
        "traits": traits, "special": special, "high": high, "extra_specials": [], "dormant": [],
        "attribute": attribute, "lean": lean, "insight": None, "insight_attr": None,
    })


def rating(content: Content, view: MartialArt, level: int, state: GameState | None = None, world: WorldStateStore | None = None) -> int:
    """戰力：威力 ×（1 ＋ 槽裡技能的加成總和）。view 是 apply 過的那一份；寫死的武學照它的功效算。"""
    cfg = content.config.arts
    bonus = 0.0
    counts: dict[str, int] = {}
    for a in view.traits or ([view.attribute] if view.attribute and fixed(content, view.id) else []):
        counts[a] = counts.get(a, 0) + 1
    for a, n in counts.items():
        bonus += cfg.general_weight * min(MAX_STRENGTH, n)
    if view.special and special_of(content, view.special) is not None:
        bonus += cfg.special_weight
    if view.high:
        bonus += cfg.high_weight
    if content.skills.get(view.id) is not None and content.skills[view.id].tactic is not None:
        bonus += cfg.signature_weight
    return int(round(power_at(view, level) * (1 + bonus)))


# ── 裝與拆 ───────────────────────────────────────────────

FIXED_LINE = "【{name}】的招式是定的，裝不了意境。"  # 待 joy 潤
NOT_OWNED = "你沒有這一門武學。"
NO_INSIGHT = "你沒有這個意境。"
FULL_LINE = "【{name}】的意境槽已經滿了（{n} 格），先拆一個下來。"
ELSEWHERE_LINE = "「{insight}」裝在【{other}】上，先從那裡拆下來。"
SLOTTED_LINE = "「{insight}」裝進了【{art}】第 {i} 格。"
UNSLOTTED_LINE = "「{insight}」從【{art}】拆了下來。"
NOT_IN_LINE = "「{insight}」沒有裝在【{art}】上。"
DUP_LINE = "【{name}】上已經有「{insight}」了。"
AFFINITY_LINE = "【{name}】收不下「{insight}」（只收{attrs}的意境）。"  # 待 joy 潤


def takes(art: MartialArt, attribute: str) -> bool:
    """這一門的槽收不收這個屬性的意境：相容屬性空著什麼都收。"""
    return not art.affinity or attribute in art.affinity


def affinity_text(art: MartialArt) -> str:
    return "、".join(art.affinity) if art.affinity else "兼容並蓄"


def slot_problem(state: GameState, content: Content, world: WorldStateStore, art_id: str, insight_id: str) -> str | None:
    from . import library, team

    art = team.resolve_art(art_id, content, world)
    if art is None or art_id not in library.owned_arts(state):
        return NOT_OWNED
    if fixed(content, art_id):
        return FIXED_LINE.format(name=art.name)
    if insight_id not in state.player.insights:
        return NO_INSIGHT
    slots = slots_of(state, content, art)
    if insight_id in slots:
        return DUP_LINE.format(name=art.name, insight=_iname(state, content, world, insight_id))
    from . import insights as insights_mod

    ins = insights_mod.resolve(insight_id, content, world, state)
    if ins is not None and not takes(art, ins.attribute):
        return AFFINITY_LINE.format(name=art.name, insight=ins.name, attrs=affinity_text(art))
    other = where_slotted(state, insight_id)
    if other is not None:
        o = team.resolve_art(other, content, world)
        return ELSEWHERE_LINE.format(insight=_iname(state, content, world, insight_id), other=o.name if o else other)
    if None not in slots:
        return FULL_LINE.format(name=art.name, n=len(slots))
    return None


def slot(state: GameState, content: Content, world: WorldStateStore, art_id: str, insight_id: str) -> list[str]:
    problem = slot_problem(state, content, world, art_id, insight_id)
    if problem is not None:
        return [problem]
    from . import team

    art = team.resolve_art(art_id, content, world)
    slots = slots_of(state, content, art)
    i = slots.index(None)
    slots[i] = insight_id
    state.player.art_slots[art_id] = slots
    return [SLOTTED_LINE.format(insight=_iname(state, content, world, insight_id), art=art.name, i=i + 1)]


def unslot(state: GameState, content: Content, world: WorldStateStore, art_id: str, insight_id: str) -> list[str]:
    from . import team

    art = team.resolve_art(art_id, content, world)
    name = art.name if art else art_id
    slots = list(state.player.art_slots.get(art_id, []))
    if insight_id not in slots:
        return [NOT_IN_LINE.format(insight=_iname(state, content, world, insight_id), art=name)]
    slots[slots.index(insight_id)] = None
    state.player.art_slots[art_id] = slots
    return [UNSLOTTED_LINE.format(insight=_iname(state, content, world, insight_id), art=name)]


def release_all(state: GameState, art_id: str) -> list[str]:
    """這一門的意境全部拆回背包（熔掉、交出、合成當料時）；回拆下來的 id。"""
    slots = state.player.art_slots.pop(art_id, [])
    return [i for i in slots if i]


def _iname(state: GameState, content: Content, world: WorldStateStore, insight_id: str) -> str:
    from . import insights as insights_mod

    ins = insights_mod.resolve(insight_id, content, world, state)
    return ins.name if ins else insight_id


# ── 舊存檔 ───────────────────────────────────────────────


def migrate(state: GameState, content: Content, world: WorldStateStore) -> None:
    """這一版之前的存檔：武學的功效照來路寫在全服那一份的 traits 上，玩家手上沒有槽。第一次讀到（PlayerState.arts_migrated 是 False）
    替每一門自己的武學把手上同屬性、還沒裝的意境裝進槽（照來路的順序），意境的強度照舊的重數（rank）。只做一次、不碰別的。"""
    p = state.player
    if p.arts_migrated:
        return
    from . import insights as insights_mod, library, team

    held = [i for i in p.insights if insights_mod.resolve(i, content, world, state) is not None]
    for i in held:
        ins = insights_mod.resolve(i, content, world, state)
        if ins is not None and ins.rank and ins.rank > 1 and i not in p.insight_strength:
            p.insight_strength[i] = min(MAX_STRENGTH, int(ins.rank))
    used: set[str] = set()
    for art_id in library.owned_arts(state):
        art = team.resolve_art(art_id, content, world)
        if art is None or fixed(content, art_id) or art_id in p.art_slots:
            continue
        n = slot_count(content, p.art_quality.get(art_id, art.quality))
        wanted = list(dict.fromkeys(list(art.traits) or [art.attribute]))
        slots: list[str | None] = []
        for attribute in wanted:
            pick = next((i for i in held if i not in used and insights_mod.resolve(i, content, world, state).attribute == attribute), None)
            if pick is not None and len(slots) < n:
                slots.append(pick)
                used.add(pick)
        p.art_slots[art_id] = slots + [None] * (n - len(slots))
    p.arts_migrated = True


def prune(state: GameState, content: Content, world: WorldStateStore) -> None:
    """讀檔修補：槽只留自己還有的武學、手上還有的意境；同一個意境只留第一處。"""
    from . import library

    p = state.player
    owned = set(library.owned_arts(state))
    seen: set[str] = set()
    kept: dict[str, list[str | None]] = {}
    for art_id, slots in p.art_slots.items():
        if art_id not in owned or fixed(content, art_id):
            continue
        row: list[str | None] = []
        for i in slots:
            if i and i in p.insights and i not in seen:
                row.append(i)
                seen.add(i)
            else:
                row.append(None)
        kept[art_id] = row
    p.art_slots = kept
    p.insight_strength = {k: v for k, v in p.insight_strength.items() if k in p.insights and v > 1}
