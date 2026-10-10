"""打造與淬煉（docs/superpowers/specs/2026-10-09-兵器-design.md 4.2～4.4、4.7；兵器第二批：自己打造）。

| 誰 | 做什麼 |
|---|---|
| 模型 | 只替這一季第一次打出來的配方取名字＋一句說明（三段式），一個數字都不碰 |
| 引擎 | 配方鍵、屬性、階、工錢、品質擲骰、全服登記、淬煉 |

這個模組 import team 與 fusion（品質的推法、悟性、天時地利）；team 會 import weapons，所以 weapons 不能 import 這裡。
鐵匠鋪的選單項（Option）在 engine 裡，回選單的函式延後 import（同 foreshadow.talk_options）。"""
from __future__ import annotations

import functools
import random
from collections import Counter

from . import fusion, naming, team, weapons
from .fusion import QualityOdds
from .insights import merged_attribute
from .models import WEAPON_KINDS, Content
from .ollama_client import OllamaClient
from .state import GameState, Weapon, WeaponRecipe
from .world_state import WorldStateStore

NOT_ENOUGH = "身上的素材不到兩個"  # 待 joy 潤


def tier_of(content: Content, main: str) -> int:
    """打出來的階照主料的階（4.2）。"""
    return content.materials[main].tier


def price(content: Content, tier: int) -> int:
    """打一把這一階的工錢（4.2，Config.weapons.forge_silver）。"""
    return content.config.weapons.forge_silver.get(str(tier), 0)


def attribute_with(content: Content, tianji: int, kind: str, main: str, aux: str) -> str:
    """打出來的屬性（4.2）：照 insights.merged_attribute，種子是「天機|配方鍵」（同 fusion.recipe_seed），所以同一季同一個配方一樣。
    同屬性與四對（剛快、柔慢、快柔、剛慢）合出來的跟主輔順序無關；其餘組合（剛柔、快慢）照種子的雜湊挑兩者之一，配方鍵分主輔，
    主輔對調是另一個配方，挑到的屬性可能不同（4.4：主輔不交換）。選單一次要算好幾個時先讀一次天機，用這一個。"""
    seed = f"{tianji}|{weapons.recipe_key(kind, main, aux)}"
    return merged_attribute(content.materials[main], content.materials[aux], seed)


def attribute_of(world: WorldStateStore, content: Content, kind: str, main: str, aux: str) -> str:
    return attribute_with(content, world.read().tianji, kind, main, aux)


def forge_problem(state: GameState, content: Content, kind: str, main: str, aux: str) -> str | None:
    """打不成的原因；None＝打得成。順序：不在鐵匠鋪、種類、素材認不得、素材不夠（主輔同一種要兩個）、裝備庫滿、銀兩不夠。
    鐵匠鋪的鈕灰掉時寫它，C 段（forge）也再驗一次。"""
    if not weapons.smith_here(state, content):
        return weapons.NOT_HERE
    if kind not in WEAPON_KINDS:
        return "沒有這種兵器"
    if main not in content.materials or aux not in content.materials:
        return "沒有這種素材"
    held = state.player.materials
    for mid, need in Counter([main, aux]).items():
        if held.get(mid, 0) < need:
            return f"{content.materials[mid].name}不夠（要 {need} 個）"
    if weapons.rack_full(state, content):
        return weapons.RACK_FULL
    short = price(content, tier_of(content, main)) - state.player.stats.get("silver", 0)
    return f"還差 {short} 兩" if short > 0 else None


def setting_points(state: GameState, content: Content, attribute: str) -> list[tuple[str, float]]:
    """打造的天時地利（附帶決定 b）：地利、戰場、心靜都同合成（地利看此地探索悟得到同屬性的意境）。最多 setting_max 條。
    兵器沒有正邪，所以合成的「晝夜」這裡沒有。"""
    rule = content.config.weapons.quality
    out: list[tuple[str, float]] = []
    if rule.terrain and fusion.terrain_here(state, content, attribute):
        out.append(("terrain", rule.terrain))
    if rule.battlefield and attribute == "剛" and fusion.battlefield_here(state, content):
        out.append(("battlefield", rule.battlefield))
    if rule.calm and fusion.calm_now(state, rule.calm_hours):
        out.append(("calm", rule.calm))
    out.sort(key=lambda item: -abs(item[1]))
    return out[: rule.setting_max]


def setting_line(content: Content, scored: list[tuple[str, float]]) -> list[str]:
    """結果多一句含蓄的話：天時地利合起來加分寫 setting_good、扣分寫 setting_bad；沒有、或那句是空的就不寫。"""
    rule = content.config.weapons.quality
    total = sum(points for _, points in scored)
    line = rule.setting_good if total > 0 else rule.setting_bad if total < 0 else ""
    return [line] if line else []


def forge_odds(state: GameState, content: Content, world: WorldStateStore, kind: str, main: str, aux: str) -> QualityOdds:
    """這一爐的品質機率（4.3）：輔料的階（比主料高幾階）、悟性、熟手（這個配方這一季打過幾次，有上限）、天時地利，
    從 Config.weapons.quality.odds 推（fusion.odds_from_points）。只看這一爐的組成，配方有沒有人打過都一樣。"""
    rule = content.config.weapons.quality
    m, a = content.materials[main], content.materials[aux]
    wis = state.player.stats.get("wis", team.BASE_STAT)
    done = state.player.forge_counts.get(weapons.recipe_key(kind, main, aux), 0)
    scored = [
        ("aux", rule.aux_tier.get(str(a.tier - m.tier), 0.0)),
        ("wis", (team.stat_factor(content, wis) - 1) * 100 * rule.wis_weight),
        ("practice", min(rule.practice_cap, rule.practice_point * done)),
    ]
    scored += setting_points(state, content, attribute_of(world, content, kind, main, aux))
    return fusion.odds_from_points(scored, rule, rule.odds)


SYSTEM = (
    "你是武俠小說裡替兵器取名的鑄劍師。你只負責取名字、寫一句話的說明，"
    "**絕對不要提到任何數字、品質、等級或威力**。全程使用繁體中文。"
)
FORGED = "鐵匠把{what}下爐，打出一把【{name}】（{kind}・屬{attribute}・{grade}）。"  # 待 joy 潤
FIRST_LINE = "這是江湖上第一次有人打出這把兵器——這個配方從此就叫這個名字。"  # 待 joy 潤
MINE_LINE = "這是你首創的配方，又打了一把。"  # 待 joy 潤
FOLLOW_LINE = "這個配方由{who}首創，你照著打出了同一把。"  # 待 joy 潤
FIZZLE = "爐火熄了，這一次什麼也沒打成（名字都被用掉了，再試一次）。"


def _messages(content: Content, kind: str, main: str, aux: str, attribute: str, tier: int) -> list[dict[str, str]]:
    """取名的提示（附帶決定 c）：寫明兵器種類與要帶的字，不寫任何數字。"""
    m, a = content.materials[main], content.materials[aux]
    noun = weapons.NOUNS[kind]
    words = "、".join(f"「{w}」" for w in weapons.WEAPON_WORDS[kind])
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": (
            f"鐵匠拿{m.name}（屬{m.attribute}）當主料、{a.name}（屬{a.attribute}）當輔料，打出一把{noun}："
            f"屬{attribute}、{weapons.TIER_WORDS[tier]}。\n"
            f"名字裡要有 {words} 其中一個，看得出是{noun}；不要用別種兵器的字。\n{naming.FORMAT_RULES}"
        )},
    ]


def forge_request(
    state: GameState, content: Content, world: WorldStateStore, kind: str, main: str, aux: str,
) -> naming.NamingRequest | None:
    """A 段（行動鎖內、很快；Game.smith_forge_request 的本體）：這一爐是這一季沒人打過的配方，就開一張取名的單子給 B 段
    （naming.generate）；打不成（forge_problem）、配方已經有人登記（查表就好）是 None。只讀。"""
    if forge_problem(state, content, kind, main, aux) is not None:
        return None
    key = weapons.recipe_key(kind, main, aux)
    if world.lookup_weapon_recipe(key) is not None:
        return None
    tier = tier_of(content, main)
    return naming.NamingRequest(
        "weapon", key, kind, _messages(content, kind, main, aux, attribute_of(world, content, kind, main, aux), tier),
        check=functools.partial(weapons.kind_problem, kind),
    )


def _candidates(content: Content, world: WorldStateStore, key: str, kind: str, tianji: int, name: str | None):
    """登記時依序試的名字：先試模型取的（有的話），再試退路字表（種子是配方鍵＋天機、鹽從 0 起；同 fusion._candidates），
    組出來剛好是某個角色名號的跳過（FB-069）。"""
    if name is not None:
        yield name
    for salt in range(naming.CLAIM_ATTEMPTS):
        fallback = weapons.fallback_name(content, key, kind, salt=salt, tianji=tianji)
        if not world.is_character_name(fallback):
            yield fallback


def _arrival(state: GameState, recipe: WeaponRecipe, first: bool) -> str:
    tail = f"\n{recipe.note}" if recipe.note else ""
    if first:
        return tail + "\n" + FIRST_LINE
    if recipe.creator == state.player.name:
        return tail + "\n" + MINE_LINE
    return tail + "\n" + FOLLOW_LINE.format(who=recipe.creator_shown or recipe.creator or "不知名的前人")


def forge(
    state: GameState, content: Content, world: WorldStateStore, client: OllamaClient | None,
    kind: str, main: str, aux: str, proposed: tuple[str | None, str] | None = None, rng: random.Random | None = None,
) -> tuple[Weapon | None, list[str]]:
    """C 段（鎖內）：打一把（4.2～4.4）。回（那一把, 訊息）；打不成回 (None, [原因])，什麼都不收、不登記。
    配方這一季沒人打過：proposed 是鎖外先取好的（名字, 說明），再過一次 naming.recheck 與 kind_problem；沒給（整季機器人、腳本、測試）
    才在這裡叫模型（client 是 Game._quick_client 的複本）；過不了走退路字表，claim_weapon_recipe 原子登記，名字撞到就換下一個。
    品質照 forge_odds 擲（熟手照這一爐之前打過幾次）；收工錢與兩樣素材、熟手 +1、放進手上或裝備庫，別人首創的記首創名望回饋。"""
    problem = forge_problem(state, content, kind, main, aux)
    if problem is not None:
        return None, [f"（{problem}。）"]
    key = weapons.recipe_key(kind, main, aux)
    tier = tier_of(content, main)
    attribute = attribute_of(world, content, kind, main, aux)
    odds = forge_odds(state, content, world, kind, main, aux)
    setting = setting_points(state, content, attribute)
    recipe, first = world.lookup_weapon_recipe(key), False
    if recipe is None:
        tianji, _ = fusion.recipe_seed(world, key)
        check = functools.partial(weapons.kind_problem, kind)
        if proposed is not None:
            name, note = naming.recheck(content, proposed, person=world.is_character_name, check=check)
        else:
            name, note = naming.propose(
                client, content, _messages(content, kind, main, aux, attribute, tier), person=world.is_character_name, check=check,
            )
        for candidate in _candidates(content, world, key, kind, tianji, name):
            draft = WeaponRecipe(
                name=candidate, key=key, kind=kind, attribute=attribute, tier=tier, main=main, aux=aux,
                creator=state.player.name, creator_shown=state.player.name, note=note if candidate == name else "",
            )
            recipe, first = world.claim_weapon_recipe(key, draft)
            if recipe is not None:
                break
        if recipe is None:
            return None, [FIZZLE]
    quality = fusion.roll_quality(odds, rng)
    p = state.player
    used = Counter([main, aux])
    for mid, n in used.items():
        p.materials[mid] -= n
        if not p.materials[mid]:
            del p.materials[mid]
    cost = price(content, tier)
    p.stats["silver"] -= cost
    p.forge_counts[key] = p.forge_counts.get(key, 0) + 1
    weapon = weapons.new_weapon(state, name=recipe.name, kind=kind, attribute=recipe.attribute, tier=tier, quality=quality, recipe=key)
    m, a = content.materials[main], content.materials[aux]
    what = f"兩份{m.name}" if main == aux else f"{m.name}與{a.name}"
    msgs = [FORGED.format(what=what, name=recipe.name, kind=kind, attribute=recipe.attribute, grade=weapons.grade(weapon))
            + _arrival(state, recipe, first)]
    msgs += setting_line(content, setting)
    msgs.append(f"銀兩 -{cost}")
    msgs += [f"{content.materials[mid].name} -{n}" for mid, n in used.items()]
    msgs.append(weapons.store(state, content, weapon))
    fusion.echo(state, content, recipe, first, made="打")
    return weapon, msgs
