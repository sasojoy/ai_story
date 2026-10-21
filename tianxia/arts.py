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

from . import insight_fx
from .martial_arts import QUALITIES, MartialArt, Insight, power_at
from .models import Content, GeneralTrait, HighTrait, SpecialTrait
from .state import GameState
from .world_state import WorldStateStore

MAX_STRENGTH = 3
STRENGTH_MARKS = {1: "一重", 2: "二重", 3: "三重"}  # Joy 2026-10-20「●好醜」：寫成重數，網頁另畫三節玉
ULTIMATE_SLOT = "絕招"  # 絕學第五格

LEAN_OF = {"正": "正", "邪": "邪"}


def fixed(content: Content, art_id: str) -> bool:
    """槽寫死的武學：內容寫了功效或本命戰法的（本命武學）、不是下品的內容武學（部下用的上品）。基礎武學與學來的武學（下品，
    帶小戰法的也是）有空槽。"""
    s = content.skills.get(art_id)
    return s is not None and (bool(s.traits) or (s.tactic is not None and not s.tactic.minor) or s.quality != "下品")


def slot_count(content: Content, quality: str) -> int:
    return int(content.config.arts.slots.get(quality, 2))


def slots_of(state: GameState, content: Content, art: MartialArt) -> list[str | None]:
    """這一門的槽（照品級的格數補齊、多的砍掉）。寫死的武學回空清單。"""
    if fixed(content, art.id):
        return []
    n = max(1, slot_count(content, state.player.art_quality.get(art.id, art.quality)) + art.slot_adjust)
    raw = list(state.player.art_slots.get(art.id, []))[:n]
    return raw + [None] * (n - len(raw))


def strength_of(state: GameState, insight_id: str) -> int:
    """這一份意境最深的一般功效是幾重（意境效果池；舊存檔照 insight_strength）。"""
    return insight_fx.strength(state, insight_id)


def strength_mark(n: int) -> str:
    return STRENGTH_MARKS.get(max(1, min(MAX_STRENGTH, n)), "一重")


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


def skill_name(content: Content, insight: Insight, fx=None) -> str:
    """這個意境是哪一招（技能的名字）：秘方的特別功效 → 高階 → 一般功效；內容沒有功效表時是屬性。
    給了 fx（insight_fx.record，那一份的效果）照它寫：「掠影二重・流光」，秘方的特別功效排在最前面。"""
    sp = special_of(content, insight.secret_special) if insight.secret_special else None
    if fx is not None:
        label = insight_fx.label(content, fx)
        return "・".join(x for x in (sp.name if sp is not None else "", label) if x) or insight.attribute
    if sp is not None:
        return sp.name
    if is_compound(content, insight):
        h = high_of(content, insight.attribute)
        if h is not None:
            return h.name
    g = general_of(content, insight.attribute)
    return g.name if g is not None else insight.attribute


def skill_desc(content: Content, insight: Insight, strength: int, fx=None) -> str:
    """這一招在回合裡做什麼（卡上那一句，數字照強度）。給了 fx 照那一份的每一個效果各寫一句「〔名〕…」。"""
    from . import traits as traits_mod

    sp = special_of(content, insight.secret_special) if insight.secret_special else None
    if fx is not None:
        parts = [f"〔{sp.name}〕" + sp.desc.replace("{value}", traits_mod._value(sp.hook, sp.amount))] if sp is not None else []
        parts += [f"〔{e['name']}〕{e['desc']}" for e in insight_fx.effects(content, fx) if e["desc"]]
        return "；".join(parts)
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


def skill_weight(content: Content, insight: Insight, strength: int, fx=None) -> float:
    """戰力裡這一招值多少（Config.arts 的三個權重 × 強度；高階與特別功效強度固定算 1）。給了 fx 照那一份的每一個效果加起來。"""
    cfg = content.config.arts
    if fx is not None:
        total = cfg.special_weight if insight.secret_special else 0.0
        total += sum(cfg.general_weight * min(MAX_STRENGTH, n) for n in fx.general.values())
        return total + (cfg.high_weight if fx.grand else 0.0)
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
    highs: list[str] = []  # 槽裡的大獎（意境效果池）：同一個只算一次，第一個記在 high、其餘在 extra_highs
    lean = art.lean if art.lean in LEAN_OF else "無"  # 內容寫的正邪（守義劍、剪徑刀…）與自創挑的正邪是底，槽裡帶正邪的意境蓋過它
    lean_strength = 0
    top_attr, top_strength = "", 0  # 兼容並蓄的武學：屬性照強度最高的那一格（一樣高取前面的；定案第二節）
    for insight_id in slots_of(state, content, art):
        if insight_id is None:
            continue
        ins = insights_mod.resolve(insight_id, content, world, state)
        if ins is None:
            continue
        strength = strength_of(state, insight_id)
        if ins.secret_special and special is None and special_of(content, ins.secret_special) is not None:
            special = ins.secret_special
        fx = insight_fx.record(state, content, world, insight_id, ins)
        for key, layers in fx.general.items():  # 一般功效：一層一個鍵（第一個功效的鍵就是屬性，舊的下游照讀）
            traits += [key] * max(1, min(MAX_STRENGTH, layers))
        if fx.grand and fx.grand not in highs and insight_fx.grand(content, fx.grand) is not None:
            highs.append(fx.grand)
        if ins.attribute and strength > top_strength:
            top_attr, top_strength = ins.attribute, strength
        if ins.lean in LEAN_OF and strength > lean_strength:
            lean, lean_strength = ins.lean, strength
    # 屬性：相容屬性的第一個；兼容並蓄的照槽裡強度最高那一格，槽空著沒有屬性（不相剋、不搭配）
    attribute = art.affinity[0] if art.affinity else top_attr
    if special is None:  # 「裝滿」秘方（secret_recipes.match_slots）：槽裡沒有特別功效時給秘方的那一條
        from . import secret_recipes

        recipe = secret_recipes.match_slots(state, content, world, art.id, art, slots_of(state, content, art))
        if recipe is not None:
            special = secret_recipes.special_for(content, recipe, secret_recipes.tianji_of(world))
    return art.model_copy(update={
        "traits": traits, "special": special, "high": highs[0] if highs else None, "extra_highs": highs[1:],
        "extra_specials": [], "dormant": [],
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
    bonus += cfg.high_weight * len({h for h in (view.high, *view.extra_highs) if h})
    if content.skills.get(view.id) is not None and content.skills[view.id].tactic is not None:
        bonus += cfg.signature_weight * (0.5 if content.skills[view.id].tactic.minor else 1.0)  # 小戰法算半個
    elif view.tactic_from:
        bonus += cfg.signature_weight * 0.5  # 自創借來的小戰法：同學來的
    return int(round(power_at(view, level) * (1 + bonus)))


def score(state: GameState, content: Content, world: WorldStateStore, art: MartialArt | None) -> int:
    """評分（第三批）：槽裡每一份意境的效果加總，單色格的 ×score_single_color（見 Config.arts）；槽裡沒有特別功效、
    卻暗合「裝滿」秘方的另加一條特別功效。寫死的武學照它內容寫的功效算（本命戰法算一個大獎）。art 是 team.player_art 那一份。"""
    if art is None:
        return 0
    cfg = content.config.arts
    if fixed(content, art.id):
        counts: dict[str, int] = {}
        for key in art.traits or ([art.attribute] if art.attribute else []):
            counts[key] = counts.get(key, 0) + 1
        total = sum(cfg.score_per_layer * min(MAX_STRENGTH, n) for n in counts.values())
        total += cfg.score_grand * len({h for h in (art.high, *art.extra_highs) if h})
        total += cfg.score_special if art.special and special_of(content, art.special) is not None else 0
        skill = content.skills.get(art.id)
        total += cfg.score_grand if skill is not None and skill.tactic is not None else 0
        return int(round(total))
    from . import insights as insights_mod

    slots, colors = slots_of(state, content, art), slot_colors(state, content, art)
    total, specials = 0.0, 0
    for i, insight_id in enumerate(slots):
        ins = insights_mod.resolve(insight_id, content, world, state) if insight_id else None
        if ins is None:
            continue
        fx = insight_fx.record(state, content, world, insight_id, ins)
        pts = sum(cfg.score_per_layer * min(MAX_STRENGTH, n) for n in fx.general.values())
        pts += cfg.score_grand if fx.grand and insight_fx.grand(content, fx.grand) is not None else 0
        if ins.secret_special and special_of(content, ins.secret_special) is not None:
            pts += cfg.score_special
            specials += 1
        if i < len(colors) and len(colors[i]) == 1:
            pts *= cfg.score_single_color
        total += pts
    if not specials:
        view = apply(state, content, world, art)
        if view is not None and view.special and special_of(content, view.special) is not None:
            total += cfg.score_special
    return int(round(total))


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
NO_SUCH_SLOT = "沒有這一格。"
TAKEN_SLOT = "第 {i} 格已經裝了東西，先拆下來。"
COLOR_LINE = "第 {i} 格是{colors}色，收不下「{insight}」。"  # 待 joy 潤
COLOR_FULL = "【{name}】收得下「{insight}」的那幾格都裝滿了。"  # 待 joy 潤


class Refusal(str):
    """做不了的原因：照舊是那一句話（呼叫端都當字串用），另外帶一個兩三個字的 short，給煉製頁在清單上標「合不了」用
    （skillview.forge_picks，企劃者 2026-10-10「常常丟上去按合成才知道」）。fusion 的合成與這裡的裝槽共用。"""

    short: str = "合不了"


def refuse(text: str, short: str) -> Refusal:
    out = Refusal(text)
    out.short = short
    return out


def colors_of(art: MartialArt, n: int) -> list[list[str]]:
    """前 n 格各收哪幾種屬性（每格分顏色，Joy 2026-10-20「有些是單色，有些是雙色，有些是全部都能放」）：
    寫了 slot_colors 的照它（自創、合成的），沒寫或不夠的格照相容屬性（內容武學每一格都收整份相容屬性）；空清單＝什麼都收。"""
    out: list[list[str]] = []
    for i in range(n):
        if i < len(art.slot_colors):
            out.append(list(art.slot_colors[i]))
        else:
            out.append(list(art.affinity))
    return out


def takes_at(art: MartialArt, colors: list[str], attribute: str) -> bool:
    return not colors or attribute in colors


def takes(art: MartialArt, attribute: str) -> bool:
    """這一門有沒有哪一格收這個屬性的意境：相容屬性空著什麼都收。"""
    if art.slot_colors:
        return any(takes_at(art, c, attribute) for c in art.slot_colors)
    return not art.affinity or attribute in art.affinity


def color_text(colors: list[str]) -> str:
    """一格的顏色寫成字：「剛」「剛快」「任」。待 joy 潤"""
    return "".join(colors) if colors else "任"


def slot_colors(state: GameState, content: Content, art: MartialArt) -> list[list[str]]:
    """這一門此刻開著的每一格的顏色（跟 slots_of 一樣長）；寫死的武學是空清單。"""
    return colors_of(art, len(slots_of(state, content, art)))


def affinity_text(art: MartialArt) -> str:
    return "、".join(art.affinity) if art.affinity else "兼容並蓄"


def takes_text(affinity: str) -> str:
    """「收快、陽的意境」；兼容並蓄寫「什麼意境都收」（不寫「收兼容並蓄的意境」）。待 joy 潤"""
    return "什麼意境都收" if affinity == "兼容並蓄" else f"收{affinity}的意境"


def slot_problem(
    state: GameState, content: Content, world: WorldStateStore, art_id: str, insight_id: str, index: int | None = None,
) -> str | None:
    from . import library, team

    art = team.resolve_art(art_id, content, world)
    if art is None or art_id not in library.owned_arts(state):
        return NOT_OWNED
    if fixed(content, art_id):
        return refuse(FIXED_LINE.format(name=art.name), "寫死的")
    if insight_id not in state.player.insights:
        return NO_INSIGHT
    slots = slots_of(state, content, art)
    if insight_id in slots:
        return refuse(DUP_LINE.format(name=art.name, insight=_iname(state, content, world, insight_id)), "已裝上")
    from . import insights as insights_mod

    ins = insights_mod.resolve(insight_id, content, world, state)
    colors = colors_of(art, len(slots))
    if ins is not None and not any(takes_at(art, c, ins.attribute) for c in colors):
        return refuse(AFFINITY_LINE.format(name=art.name, insight=ins.name, attrs=affinity_text(art)), "收不下")
    other = where_slotted(state, insight_id)
    if other is not None:
        o = team.resolve_art(other, content, world)
        return refuse(ELSEWHERE_LINE.format(insight=_iname(state, content, world, insight_id), other=o.name if o else other), "裝在別門")
    if None not in slots:
        return refuse(FULL_LINE.format(name=art.name, n=len(slots)), "槽滿了")
    if index is not None:
        if not 0 <= index < len(slots):
            return refuse(NO_SUCH_SLOT, "沒這格")
        if slots[index] is not None:
            return refuse(TAKEN_SLOT.format(i=index + 1), "這格有了")
        if ins is not None and not takes_at(art, colors[index], ins.attribute):
            return refuse(COLOR_LINE.format(i=index + 1, colors=color_text(colors[index]), insight=ins.name), "顏色不合")
        return None
    if ins is not None and _open_slot(slots, colors, ins.attribute) is None:
        return refuse(COLOR_FULL.format(name=art.name, insight=ins.name), "顏色不合")
    return None


def _open_slot(slots: list[str | None], colors: list[list[str]], attribute: str) -> int | None:
    """第一個空著、顏色收得下的格；單色、雙色的先（任色的留給別的意境）。"""
    open_ = [i for i, v in enumerate(slots) if v is None and (not colors[i] or attribute in colors[i])]
    if not open_:
        return None
    return min(open_, key=lambda i: (not colors[i], i))


def slot(
    state: GameState, content: Content, world: WorldStateStore, art_id: str, insight_id: str, index: int | None = None,
) -> list[str]:
    """裝進 index 那一格；沒給照 _open_slot 挑（單色雙色先、任色後）。"""
    problem = slot_problem(state, content, world, art_id, insight_id, index)
    if problem is not None:
        return [problem]
    from . import insights as insights_mod, team

    art = team.resolve_art(art_id, content, world)
    slots = slots_of(state, content, art)
    if index is not None:
        i = index
    else:
        ins = insights_mod.resolve(insight_id, content, world, state)
        i = _open_slot(slots, colors_of(art, len(slots)), ins.attribute if ins else "")
    slots[i] = insight_id
    state.player.art_slots[art_id] = slots
    msgs = [SLOTTED_LINE.format(insight=_iname(state, content, world, insight_id), art=art.name, i=i + 1)]
    from . import secret_recipes  # 裝滿最後一格才可能暗合「裝滿」秘方（之前有空格，一定沒合上）

    recipe = secret_recipes.match_slots(state, content, world, art_id, art, slots)
    if recipe is not None:
        msgs += secret_recipes.set_lines(state, content, world, recipe, art.name)
    return msgs


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
    p.insight_fx = {k: v for k, v in p.insight_fx.items() if k in p.insights}
