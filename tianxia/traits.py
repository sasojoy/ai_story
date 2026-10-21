"""武學的功效（武學與成長設計第十三節）：八個一般功效（一個屬性一個）與特別功效。

| 誰 | 做什麼 |
|---|---|
| 內容（content/traits.json） | 每個功效叫什麼、掛在哪裡（hook）、每層多少、上限、一句說明 |
| 這裡 | 一門武學帶哪幾個（traits_of）、本人身上兩門加起來各幾層（loadout）、換算成數字（amount） |
| encounter／team／engine | 照 hook 把數字用在遭遇戰的各一步 |

一門武學的一般功效記成**屬性的清單**（MartialArt.traits：一個屬性一層；玩家自己的武學照意境槽填，arts.apply）；
舊資料與內容寫的武學沒有這個欄位，當作只有自己的屬性。功效只算玩家本人身上那兩門（13.1）。
程式裡叫 trait，不叫 effect：models.Effect 是事件的效果。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .martial_arts import MartialArt
from .models import Content, GeneralTrait, SpecialTrait, TacticDef
from . import tactics
from .state import GameState
from .world_state import WorldStateStore

POINT_HOOKS = {"win_xinde", "train_stamina"}  # 這兩個的數字是點數（心得、體力），其他都是比例


def traits_of(art: MartialArt) -> list[str]:
    """這一門的一般功效（屬性的清單，照順序）：玩家自己的武學照槽填（arts.apply）；槽寫死的內容武學沒寫 traits 時當作只有自己的屬性；
    槽空著的武學是空的。"""
    if art.traits:
        return list(art.traits)
    return [art.attribute] if art.origin == "historical" and art.attribute else []


def general(content: Content, key: str) -> GeneralTrait:
    """一般功效的鍵換成內容：第一個功效的鍵就是屬性，第二個起是 id（意境效果池）。"""
    for trait in content.traits.general:
        if trait.key == key:
            return trait
    raise KeyError(f"content/traits.json 沒有一般功效 {key}")


def highs_of(content: Content, art: MartialArt) -> list:
    """這一門帶的大獎（高階技能），照槽的先後、同一個只算一次；內容沒有那個 id 的略過。"""
    out = []
    for hid in dict.fromkeys(h for h in (art.high, *art.extra_highs) if h):
        top = high(content, hid)
        if top is not None:
            out.append(top)
    return out


def special(content: Content, special_id: str | None) -> SpecialTrait | None:
    """特別功效的 id 換成內容；沒有這個 id（沒帶、或內容改過已經沒有了）就是 None。"""
    if not special_id:
        return None
    return next((t for t in content.traits.special if t.id == special_id), None)


def multiplier(content: Content, quality: str) -> float:
    return content.config.trait_quality_multiplier.get(quality, 1.0)


@dataclass
class Loadout:
    """本人身上兩門加起來的功效：一般功效照 hook 記層數（已乘品質），特別功效照 hook 記一個（相同的只算一次）；
    source 是每個功效名對到「帶它、層數最多的那一門」的名字（演出句的 {art}）。"""

    layers: dict[str, float] = field(default_factory=dict)
    specials: dict[str, SpecialTrait] = field(default_factory=dict)
    source: dict[str, str] = field(default_factory=dict)
    highs: list[TacticDef] = field(default_factory=list)  # 高階技能（不同意境合出來的意境裝進槽，arts.apply）：強度固定，同名的只算一個


def loadout(state: GameState, content: Content, world: WorldStateStore) -> Loadout:
    from . import team  # team 會 import 這個模組

    out = Loadout()
    best: dict[str, tuple[float, str]] = {}
    if not content.traits.general:
        return out
    for skill_id in (state.player.member.wugong_id, state.player.member.neigong_id):
        art = team.player_art(state, content, world, skill_id)  # 自己那一份：槽裡裝的技能已經填上（arts.apply）
        if art is None:
            continue
        mult, mine = multiplier(content, art.quality), traits_of(art)
        for attribute in dict.fromkeys(mine):
            trait = general(content, attribute)
            layers = mine.count(attribute) * mult
            out.layers[trait.hook] = out.layers.get(trait.hook, 0.0) + layers
            if layers > best.get(trait.name, (0.0, ""))[0]:
                best[trait.name] = (layers, art.name)
        for sid in [art.special, *art.extra_specials]:
            sp = special(content, sid)
            if sp is not None and sp.hook not in out.specials:
                out.specials[sp.hook] = sp
                best.setdefault(sp.name, (1.0, art.name))
        for top in highs_of(content, art):
            if all(t.name != top.tactic.name for t in out.highs):
                out.highs.append(top.tactic)
                best.setdefault(top.tactic.name, (1.0, art.name))
    out.source = {name: art_name for name, (_, art_name) in best.items()}
    return out


def amount(content: Content, lo: Loadout, hook: str) -> float:
    """一般功效的數字：每層 × 層數，套上限；身上沒有是 0。"""
    trait = next((t for t in content.traits.general if t.hook == hook), None)
    if trait is None:
        return 0.0
    return min(trait.cap, trait.per_layer * lo.layers.get(hook, 0.0))


def tactic_defs(content: Content, lo: Loadout) -> list[TacticDef]:
    """本人身上的功效在回合裡的樣子（第三批，tactics.py）：一般功效照層數算出數字（rate、params 寫 "value"／"extra" 的換掉），
    特別功效照內容寫的。沒有回合裡的作用的（厚：只改氣血係數的下限）不算。"""
    out: list[TacticDef] = []
    for trait in content.traits.general:
        layers = lo.layers.get(trait.hook, 0.0)
        if trait.tactic is None or layers <= 0:
            continue
        value = min(trait.cap, trait.per_layer * layers)
        extra = min(trait.extra_cap, trait.extra_per_layer * layers)

        def pick(v: float | str) -> float:
            return value if v == "value" else extra if v == "extra" else float(v)

        tt = trait.tactic
        out.append(TacticDef(
            name=trait.name, timing=tt.timing, kind=tt.kind, rate=min(1.0, pick(tt.rate)), rounds=tt.rounds,
            params={k: pick(v) for k, v in tt.params.items()}, say=tt.say,
            desc=trait.desc.replace("{value}", _value(trait.hook, value)).replace("{extra}", _value(trait.hook, extra)),
        ))
    for sp in lo.specials.values():
        if sp.tactic is not None:
            out.append(sp.tactic)
    return out + list(lo.highs)


ULTIMATE_TITLE = tactics.ULTIMATE_SEAL  # 絕招那一行蓋金印「絕」（招式與絕學稿案第一節）
MASTERED = "絕學"


def ultimate_trait(content: Content, art: MartialArt | None) -> GeneralTrait | None:
    """絕學立招（玩家武學追上本命）：自己合成的武學（不是內容寫的）練成絕學時，層數最多的那個一般功效（一樣多取前面的）。
    art 要是玩家自己那一份（team.player_art：品質照自己修到的）。不是絕學、是內容武學、那個功效沒寫絕招都是 None。"""
    if art is None or art.id in content.skills or art.quality != MASTERED or not content.traits.general:
        return None
    mine = [k for k in traits_of(art) if any(t.key == k and t.ultimate is not None for t in content.traits.general)]
    if not mine:  # 意境槽空著、或只裝著沒有絕招的功效（各路第二個功效）：沒有功效可立招
        return None
    top = max(dict.fromkeys(mine), key=mine.count)
    return general(content, top)


def ultimate_of(content: Content, art: MartialArt | None) -> TacticDef | None:
    """那一門的絕招：功效寫好的那一招，名字換成那門絕學的名字（定過名就是定的名字）。"""
    trait = ultimate_trait(content, art)
    if trait is None or art is None:
        return None
    return trait.ultimate.model_copy(update={"name": art.name})


def has(lo: Loadout, hook: str) -> bool:
    """身上有沒有這個掛點的功效（一般的層數大於 0，或特別功效）。"""
    return lo.layers.get(hook, 0.0) > 0 or hook in lo.specials


def naming_note(content: Content, trait_list: list[str], special_id: str | None) -> str:
    """取名的提示裡那一行（13.1：取名時看得到功效，名字要配得上）：只寫功效的名字，不寫數字。
    內容沒有功效就是空字串（提示照舊）。"""
    if not content.traits.general:
        return ""
    names = [general(content, attribute).name for attribute in trait_list]
    sp = special(content, special_id)
    tail = f"，還帶著罕見的「{sp.name}」" if sp is not None else ""
    return f"這門武學的功效是：{'、'.join(names)}{tail}。名字要配得上它的功效。\n"


def _value(hook: str, number: float) -> str:
    """說明裡的 {value}：點數照原樣、比例換成百分比（七點五個百分點寫 7.5%，不四捨五入掉）。"""
    return f"{number:g}" if hook in POINT_HOOKS else f"{round(number * 100, 1):g}%"


def card_line(content: Content, art: MartialArt) -> str:
    """功法卡的一行（13.6）：這一門的每個一般功效（照這一門自己的層數與品質算出來的數字），再加特別功效。
    內容沒有功效（沒有 traits.json）就是空字串，卡片不畫這一行。
    本命武學另起一行寫本命特效（signature.card_text：名字、說明、數字），有沒有 traits.json 都寫。"""
    sig = tactics.of_art(content, art)  # 本命戰法、學來的武學的小戰法、自創借來的小戰法
    tail = tactics.card_text(sig, tactics.title_of(sig, art)) if sig is not None else ""
    ult = ultimate_of(content, art)
    if ult is not None:  # 絕學立招：「絕〔名〕乘勢・剋中對手後 100%：……」
        tail = tactics.card_text(ult, ULTIMATE_TITLE)
    if not content.traits.general:
        return tail
    mult, mine, parts = multiplier(content, art.quality), traits_of(art), []
    for attribute in dict.fromkeys(mine):
        trait = general(content, attribute)
        layers = mine.count(attribute) * mult
        number = min(trait.cap, trait.per_layer * layers)
        extra = min(trait.extra_cap, trait.extra_per_layer * layers)
        parts.append(f"〔{trait.name}〕" + trait.desc.replace("{value}", _value(trait.hook, number)).replace("{extra}", _value(trait.hook, extra)))
    for sid in [art.special, *art.extra_specials]:
        sp = special(content, sid)
        if sp is not None:
            parts.append(f"〔{sp.name}〕" + sp.desc.replace("{value}", _value(sp.hook, sp.amount)))
    for top in highs_of(content, art):
        parts.append(HIGH_MARK.format(name=top.name) + top.desc)
    if not parts:
        return (EMPTY_LINE + (f"\n{tail}" if tail else "")) if not fixed_art(content, art) else tail
    line = "功效：" + "・".join(parts)
    return line + (f"\n{tail}" if tail else "")


HIGH_MARK = "〔高階・{name}〕"
EMPTY_LINE = "功效：（意境槽空著，到煉製頁裝意境）"  # 待 joy 潤


def high(content: Content, high_id: str | None):
    if not high_id:
        return None
    return next((h for h in content.traits.high if h.id == high_id), None)


def fixed_art(content: Content, art: MartialArt) -> bool:
    from . import arts as arts_mod

    return arts_mod.fixed(content, art.id)
