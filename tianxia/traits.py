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
from . import moves, tactics
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


def copies_of(art: MartialArt) -> dict[str, list[int]]:
    """這一門每個一般功效各有幾份、每份幾層（arts.apply 填的 MartialArt.copies）；沒有的（內容寫的武學、舊資料）每個功效當作一份。"""
    if art.copies:
        return {k: list(v) for k, v in art.copies.items()}
    mine = traits_of(art)
    return {k: [mine.count(k)] for k in dict.fromkeys(mine)}


def stack_value(values: list[float], cap: float, share: float, ceiling: float) -> float:
    """同一個功效好幾份合起來算多少（Joy 2026-10-22 選「第二份算半」）：只有一份、或加起來沒超過上限，照舊相加（夾在 cap）；
    超過時第一份照算（夾在 cap），第二份起每份先夾在 cap、再算 share，合起來最多 cap × ceiling。values 與 cap 同一種單位
    （打仗是數字，戰力與評分是重數）。"""
    if not values:
        return 0.0
    each = sorted((min(cap, v) for v in values), reverse=True)
    return max(min(cap, sum(values)), min(cap * ceiling, each[0] + share * sum(each[1:])))


def stack_shares(values: list[float], cap: float, share: float, ceiling: float) -> list[float]:
    """每一份實際算了幾成（照先後一份一份加上去，多出來的那一截 ÷ 那一份自己的數字；一份自己超過上限的那一截本來就不算，
    所以除的是夾過上限的數）：卡上「算五成」「不加」那幾個字。"""
    out, before = [], 0.0
    for k, v in enumerate(values):
        after = stack_value(values[:k + 1], cap, share, ceiling)
        out.append(max(0.0, min(1.0, (after - before) / min(cap, v))) if v > 0 else 1.0)
        before = after
    return out


def top_of(content: Content, trait: GeneralTrait) -> tuple[float, float]:
    """一般功效打起來最多到多少（數字、extra）：好幾份疊上去時是上限的 stack_ceiling 倍。"""
    ceil = content.config.arts.stack_ceiling
    return trait.cap * ceil, trait.extra_cap * ceil


def high_counts(art: MartialArt) -> dict[str, int]:
    """這一門每個真意各有幾份（同一個真意第二份照樣記在 extra_highs）。"""
    out: dict[str, int] = {}
    for h in (art.high, *art.extra_highs):
        if h:
            out[h] = out.get(h, 0) + 1
    return out


def high_tactic(content: Content, tactic: TacticDef, copies: int) -> TacticDef:
    """同一個真意好幾份：第二份起發動率 ×(1＋stack_share)；本來就每次發動的（鎮岳、金身）改成多撐一回合；第三份起不再加。"""
    if copies < 2:
        return tactic
    share = content.config.arts.stack_share
    if (tactic.rate or 0) < 1:
        return tactic.model_copy(update={"rate": min(1.0, (tactic.rate or 0) * (1 + share))})
    if tactic.rounds:
        return tactic.model_copy(update={"rounds": tactic.rounds + 1})
    if "turns" in tactic.params:
        return tactic.model_copy(update={"params": {**tactic.params, "turns": tactic.params["turns"] + 1}})
    return tactic


def highs_of(content: Content, art: MartialArt) -> list:
    """這一門帶的大獎（高階技能），照槽的先後、同一個只列一次（幾份看 high_counts）；內容沒有那個 id 的略過。"""
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
    cfg = content.config.arts
    pooled: dict[str, list[float]] = {}  # 身上兩門的每一份（層數已乘品質）：同一個功效好幾份照 stack_value 算
    tops: dict[str, tuple[object, int]] = {}  # 真意：名字 → (那一個, 兩門合起來幾份)
    for skill_id in (state.player.member.wugong_id, state.player.member.neigong_id):
        art = team.player_art(state, content, world, skill_id)  # 自己那一份：槽裡裝的技能已經填上（arts.apply）
        if art is None:
            continue
        mult = multiplier(content, art.quality) * (1 + moves.look_bonus(content, art))
        for key, each in copies_of(art).items():
            trait = general(content, key)
            pooled.setdefault(trait.hook, []).extend(n * mult for n in each)
            layers = sum(each) * mult
            if layers > best.get(trait.name, (0.0, ""))[0]:
                best[trait.name] = (layers, art.name)
        for sid in [art.special, *art.extra_specials]:
            sp = special(content, sid)
            if sp is not None and sp.hook not in out.specials:
                out.specials[sp.hook] = sp
                best.setdefault(sp.name, (1.0, art.name))
        counts = high_counts(art)
        for top in highs_of(content, art):
            had = tops.get(top.tactic.name, (top, 0))[1]
            tops[top.tactic.name] = (top, had + counts.get(top.id, 1))
            best.setdefault(top.tactic.name, (1.0, art.name))
    for trait in content.traits.general:
        if trait.hook in pooled and trait.per_layer > 0:
            value = stack_value([trait.per_layer * n for n in pooled[trait.hook]], trait.cap, cfg.stack_share, cfg.stack_ceiling)
            out.layers[trait.hook] = value / trait.per_layer
    out.highs = [high_tactic(content, top.tactic, n) for top, n in tops.values()]
    out.source = {name: art_name for name, (_, art_name) in best.items()}
    return out


def amount(content: Content, lo: Loadout, hook: str) -> float:
    """一般功效的數字：每層 × 層數，套上限；身上沒有是 0。"""
    trait = next((t for t in content.traits.general if t.hook == hook), None)
    if trait is None:
        return 0.0
    return min(top_of(content, trait)[0], trait.per_layer * lo.layers.get(hook, 0.0))


def tactic_defs(content: Content, lo: Loadout) -> list[TacticDef]:
    """本人身上的功效在回合裡的樣子（第三批，tactics.py）：一般功效照層數算出數字（rate、params 寫 "value"／"extra" 的換掉），
    特別功效照內容寫的。沒有回合裡的作用的（厚：只改氣血係數的下限）不算。"""
    out: list[TacticDef] = []
    for trait in content.traits.general:
        layers = lo.layers.get(trait.hook, 0.0)
        if trait.tactic is None or layers <= 0:
            continue
        top, top_extra = top_of(content, trait)  # 層數已經照 stack_value 算好，這裡只夾疊上去的上限
        value = min(top, trait.per_layer * layers)
        extra = min(top_extra, trait.extra_per_layer * layers)

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
AFTER_TITLE = "後勁"  # 自創破境之後，八種照屬性配的絕招接在自己的招後面那一下（招式與絕學稿案第三節）
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
    """那一門的絕招：功效寫好的那一招，名字換成那門絕學的名字（定過名就是定的名字）。
    自創的（破境）：它是接在自己絕招後面的後勁，名字照功效（先手、破甲……）。"""
    trait = ultimate_trait(content, art)
    if trait is None or art is None:
        return None
    return trait.ultimate.model_copy(update={"name": trait.name if moves.is_own(content, art) else art.name})


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
    if ult is not None and moves.is_own(content, art):  # 破境：自己的招升為絕招（金印，title_of），後面接一行後勁
        tail += "\n" + tactics.card_text(ult, AFTER_TITLE)
    elif ult is not None:  # 合成的絕學立招：「絕〔名〕乘勢・剋中對手後 100%：……」
        tail = tactics.card_text(ult, ULTIMATE_TITLE)
    if not content.traits.general:
        return tail
    cfg = content.config.arts
    mult, parts = multiplier(content, art.quality) * (1 + moves.look_bonus(content, art)), []
    for key, each in copies_of(art).items():
        trait = general(content, key)
        values = [trait.per_layer * n * mult for n in each]
        number = stack_value(values, trait.cap, cfg.stack_share, cfg.stack_ceiling)
        extra = min(top_of(content, trait)[1], trait.extra_per_layer * number / trait.per_layer) if trait.per_layer else 0.0
        parts.append(f"〔{trait.name}〕" + trait.desc.replace("{value}", _value(trait.hook, number)).replace("{extra}", _value(trait.hook, extra))
                     + stack_note(values, trait.cap, cfg.stack_share, cfg.stack_ceiling))
    for sid in [art.special, *art.extra_specials]:
        sp = special(content, sid)
        if sp is not None:
            parts.append(f"〔{sp.name}〕" + sp.desc.replace("{value}", _value(sp.hook, sp.amount)))
    counts = high_counts(art)
    for top in highs_of(content, art):
        parts.append(HIGH_MARK.format(name=top.name) + top.desc + high_note(top.tactic, counts.get(top.id, 1)))
    if not parts:
        return (EMPTY_LINE + (f"\n{tail}" if tail else "")) if not fixed_art(content, art) else tail
    line = "功效：" + "・".join(parts)
    return line + (f"\n{tail}" if tail else "")


HIGH_MARK = "〔高階・{name}〕"
HIGH_TWICE = "（兩份：第二份{word}）"  # 待 joy 潤
HIGH_MORE_WORD, HIGH_LONGER_WORD = "多一半發動的機會", "多撐一回合"  # 待 joy 潤


def high_note(tactic: TacticDef, copies: int) -> str:
    """功法卡上同一個真意好幾份的小註（照 high_tactic）：兩份「第二份多一半發動的機會」，本來就每次發動的「第二份多撐一回合」；
    三份起後面再寫第三份不加。"""
    if copies < 2:
        return ""
    note = HIGH_TWICE.format(word=HIGH_MORE_WORD if (tactic.rate or 0) < 1 else HIGH_LONGER_WORD)
    return note if copies == 2 else note.replace("兩份：", f"{COUNT_WORDS.get(copies, '好幾')}份：").replace("）", "，第三份起不加）")


def stack_note(values: list[float], cap: float, share: float, ceiling: float) -> str:
    """功法卡那一行同一個功效好幾份時的小註：「（兩份：第二份算五成）」「（三份：到頂，第三份不加）」。只有一份是空字串。待 joy 潤"""
    if len(values) < 2:
        return ""
    shares = stack_shares(values, cap, share, ceiling)
    words = [f"第{'一二三四五六七八'[k]}份{share_word(x)}" for k, x in enumerate(shares) if k and x < 0.95]
    full = stack_value(values, cap, share, ceiling) >= cap * ceiling - 1e-9
    return f"（{COUNT_WORDS[len(values)]}份{'：' + '、'.join(words) if words else ''}{'・到頂' if full else ''}）"


COUNT_WORDS = {1: "一", 2: "兩", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八"}


def share_word(x: float) -> str:
    """一份算了幾成：算五成、算三成；不到半成寫「不加」。"""
    n = round(x * 10)
    return "不加" if n <= 0 else f"算{'零一二三四五六七八九十'[n]}成"


EMPTY_LINE = "功效：（意境槽空著，到煉製頁裝意境）"  # 待 joy 潤


def high(content: Content, high_id: str | None):
    if not high_id:
        return None
    return next((h for h in (*content.traits.high, *content.traits.god) if h.id == high_id), None)


def fixed_art(content: Content, art: MartialArt) -> bool:
    from . import arts as arts_mod

    return arts_mod.fixed(content, art.id)
