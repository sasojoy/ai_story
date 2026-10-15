"""武學的功效（武學與成長設計第十三節）：八個一般功效（一個屬性一個）與特別功效。

| 誰 | 做什麼 |
|---|---|
| 內容（content/traits.json） | 每個功效叫什麼、掛在哪裡（hook）、每層多少、上限、一句說明 |
| 這裡 | 一門武學帶哪幾個（traits_of）、本人身上兩門加起來各幾層（loadout）、換算成數字（amount） |
| encounter／team／engine | 照 hook 把數字用在遭遇戰的各一步 |

一門武學的一般功效記成**屬性的清單**（MartialArt.traits，最多 3 個：第一個是自己的屬性，後面是傳下來的，13.3）；
舊資料與內容寫的武學沒有這個欄位，當作只有自己的屬性。功效只算玩家本人身上那兩門（13.1）。
程式裡叫 trait，不叫 effect：models.Effect 是事件的效果。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .martial_arts import MartialArt
from .models import Content, GeneralTrait, SpecialTrait
from .state import GameState
from .world_state import WorldStateStore

MAX_TRAITS = 3  # 一門最多帶幾個一般功效（13.3）
POINT_HOOKS = {"win_xinde", "train_stamina"}  # 這兩個的數字是點數（心得、體力），其他都是比例


def traits_of(art: MartialArt) -> list[str]:
    """這一門的一般功效（屬性的清單，照順序）；舊資料與內容寫的武學沒有，當作只有自己的屬性。"""
    return list(art.traits) or [art.attribute]


def general(content: Content, attribute: str) -> GeneralTrait:
    for trait in content.traits.general:
        if trait.attribute == attribute:
            return trait
    raise KeyError(f"content/traits.json 沒有屬性 {attribute} 的一般功效")


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


def loadout(state: GameState, content: Content, world: WorldStateStore) -> Loadout:
    from . import team  # team 會 import 這個模組

    out = Loadout()
    best: dict[str, tuple[float, str]] = {}
    if not content.traits.general:
        return out
    for skill_id in (state.player.member.wugong_id, state.player.member.neigong_id):
        art = team.player_art(state, content, world, skill_id)  # 自己那一份：品質照自己修到的
        if art is None:
            continue
        mult, mine = multiplier(content, art.quality), traits_of(art)
        for attribute in dict.fromkeys(mine):
            trait = general(content, attribute)
            layers = mine.count(attribute) * mult
            out.layers[trait.hook] = out.layers.get(trait.hook, 0.0) + layers
            if layers > best.get(trait.name, (0.0, ""))[0]:
                best[trait.name] = (layers, art.name)
        sp = special(content, art.special)
        if sp is not None and sp.hook not in out.specials:
            out.specials[sp.hook] = sp
            best.setdefault(sp.name, (1.0, art.name))
    out.source = {name: art_name for name, (_, art_name) in best.items()}
    return out


def amount(content: Content, lo: Loadout, hook: str) -> float:
    """一般功效的數字：每層 × 層數，套上限；身上沒有是 0。"""
    trait = next((t for t in content.traits.general if t.hook == hook), None)
    if trait is None:
        return 0.0
    return min(trait.cap, trait.per_layer * lo.layers.get(hook, 0.0))


def has(lo: Loadout, hook: str) -> bool:
    """身上有沒有這個掛點的功效（一般的層數大於 0，或特別功效）。"""
    return lo.layers.get(hook, 0.0) > 0 or hook in lo.specials


def inherit_fuse(base: MartialArt, attribute: str) -> list[str]:
    """武學＋意境（13.3）：新武學的屬性（意境的）排第一；底的功效整串往後推，最多留 2 個，擠掉最舊的。
    只傳一般功效，特別功效不傳給後代（13.4）。"""
    return [attribute] + traits_of(base)[: MAX_TRAITS - 1]


def inherit_blend(a: MartialArt, b: MartialArt, attribute: str) -> list[str]:
    """武學＋武學（13.3）：新武學的屬性排第一；兩門各傳一個下來——各自屬性的那個功效，照 id 排序（不分先後）。"""
    first, second = sorted((a, b), key=lambda art: art.id)
    return [attribute, first.attribute, second.attribute]


def roll_special(content: Content, key: str, tianji: int) -> str | None:
    """長出新武學時擲特別功效（13.4）：配方加這一季天機的雜湊，同一個配方同一季永遠一樣；只從共用清單（pool）挑，
    機會是 Config.special_trait_chance。沒有清單或沒擲中是 None。"""
    pool = sorted(t.id for t in content.traits.special if t.pool)
    digest = hashlib.sha256(f"{tianji}|{key}|special".encode("utf-8")).digest()
    roll = int.from_bytes(digest[:8], "big") / 2**64
    if not pool or roll >= content.config.special_trait_chance:
        return None
    return pool[digest[8] % len(pool)]


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
    內容沒有功效（沒有 traits.json）就是空字串，卡片不畫這一行。"""
    if not content.traits.general:
        return ""
    mult, mine, parts = multiplier(content, art.quality), traits_of(art), []
    for attribute in dict.fromkeys(mine):
        trait = general(content, attribute)
        number = min(trait.cap, trait.per_layer * mine.count(attribute) * mult)
        parts.append(f"〔{trait.name}〕" + trait.desc.replace("{value}", _value(trait.hook, number)))
    sp = special(content, art.special)
    if sp is not None:
        parts.append(f"〔{sp.name}〕" + sp.desc.replace("{value}", _value(sp.hook, sp.amount)))
    return "功效：" + "・".join(parts)
