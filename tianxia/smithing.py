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
from .models import WEAPON_KINDS, Content, Material
from .ollama_client import OllamaClient
from .state import GameState, SmithDraft, Weapon, WeaponRecipe
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


# ---- 鐵匠鋪的一步一步選單（375×812：每一步只有一排按鈕，最多十二種素材＋兩顆）----

OPEN = "smith:forge"
KIND = "smith:forge-kind:"
MAIN = "smith:forge-main:"
AUX = "smith:forge-aux:"
GO = "smith:forge-go:"
UNDO = "smith:forge-undo"
CANCEL = "smith:forge-cancel"
GO_VERB = "forge-go"
STEP_VERBS = ("forge", "forge-kind", "forge-main", "forge-aux", "forge-undo", "forge-cancel", "temper")
FORGE_TITLE = "打造"
FORGE_WAIT = "鐵匠掂著料，想給它取個名字……"  # 待 joy 潤：首創配方等模型取名時按鈕上的字（Option.wait）
ASK_KIND = "要打哪一種兵器？"  # 以下待 joy 潤
ASK_MAIN = "挑主料：主料定這把兵器的階，也定工錢。"
ASK_AUX = "挑輔料：主料與輔料合起來定這把兵器的屬性。"
READY = "料都齊了，看一眼機率再開爐。"
CANCELLED = "你把素材收了回去，這回先不打。"
NEW_RECIPE = "這個配方還沒人打過"
KNOWN_RECIPE = "照【{name}】的配方打"
ATTR_MARK = "・跟你的武學同屬性"


def is_go(option_id: str) -> bool:
    return option_id.startswith(GO)


def parse_go(option_id: str) -> tuple[str, str, str]:
    """開爐那一顆的 id 拆回（種類, 主料, 輔料）；拆不出來是三個空字串（forge_problem 會擋下來）。"""
    parts = option_id[len(GO):].split(":") if is_go(option_id) else []
    return (parts[0], parts[1], parts[2]) if len(parts) == 3 else ("", "", "")


def is_forge_step(arg: str) -> bool:
    """smith: 後面這一段是打造的一步（含打開與開爐）：江湖紀錄的標題是「打造」；打開以外的每一步併進同一則
    （Game.choose 照它 merge，打開那一步 "forge" 另起一則）。"""
    return arg.partition(":")[0].startswith("forge")


def title(arg: str) -> str:
    """鐵匠鋪上這一下的江湖紀錄標題：打造的每一步是「打造」、淬煉是「淬煉」，其餘是「鐵匠鋪」。"""
    if is_forge_step(arg):
        return FORGE_TITLE
    return TEMPER_TITLE if arg == "temper" else weapons.SMITH


def _held(state: GameState, content: Content) -> list[tuple[str, int]]:
    """背包裡打得了的素材：高階的先、同階數量多的先、再照 id（最可能要用的排在第一屏）。"""
    mats = content.materials
    return sorted(
        ((mid, n) for mid, n in state.player.materials.items() if n > 0 and mid in mats),
        key=lambda pair: (-mats[pair[0]].tier, -pair[1], pair[0]),
    )


def draft_stale(content: Content, draft: SmithDraft) -> bool:
    """存檔裡的單子指著內容已經沒有的種類或素材（內容改版）：選單畫不出來（go_option 查素材會丟 KeyError），要從頭來。"""
    return (draft.kind is not None and draft.kind not in WEAPON_KINDS) or any(
        mid is not None and mid not in content.materials for mid in (draft.main, draft.aux))


def open_problem(state: GameState, content: Content) -> str | None:
    """「打造兵器…」按不按得下去：裝備庫滿了、素材不到兩個、最便宜的一爐也付不起，就灰掉寫原因。"""
    if weapons.rack_full(state, content):
        return weapons.RACK_FULL
    held = _held(state, content)
    if sum(n for _, n in held) < 2:
        return NOT_ENOUGH
    short = min(price(content, content.materials[mid].tier) for mid, _ in held) - state.player.stats.get("silver", 0)
    return f"還差 {short} 兩" if short > 0 else None


def forge_door(state: GameState, content: Content):
    """鐵匠鋪選單上的「打造兵器…」：打開一步一步的單子（step 的 "forge"）。"""
    from .engine import Option  # noqa: PLC0415  延後 import：engine → smithing

    problem = open_problem(state, content)
    return Option(id=OPEN, label=f"打造兵器…（{problem or '挑種類、主料、輔料'}）", enabled=problem is None)


def step(state: GameState, content: Content, verb: str, arg: str) -> list[str]:
    """單子往前或往後一步（選項都由 Game.choose 驗過在選單上，arg 一定是選單給的）。開爐（forge-go）不在這裡，見 forge。"""
    p = state.player
    if verb == "temper":
        return temper(state, content)
    if verb == "forge":
        p.smith_draft = SmithDraft()
        return [ASK_KIND]
    d = p.smith_draft
    if d is None:
        return ["（此刻無法這麼做。）"]
    if verb == "forge-kind":
        d.kind = arg
        return [ASK_MAIN]
    if verb == "forge-main":
        d.main = arg
        return [ASK_AUX]
    if verb == "forge-aux":
        d.aux = arg
        return [READY]
    if verb == "forge-undo":
        if d.aux is not None:
            d.aux = None
            return [ASK_AUX]
        if d.main is not None:
            d.main = None
            return [ASK_MAIN]
        d.kind = None
        return [ASK_KIND]
    if verb == "forge-cancel":
        p.smith_draft = None
        return [CANCELLED]
    return ["（此刻無法這麼做。）"]


def go_option(state: GameState, content: Content, world: WorldStateStore, kind: str, main: str, aux: str):
    """開爐那一顆：寫配方名（有人打過）或「還沒人打過」、種類屬性階、工錢與三個品質的機率（不寫品級）；打不成灰掉寫原因。
    沒人打過的要等模型取名，帶 wait。"""
    from .engine import Option  # noqa: PLC0415

    known = world.lookup_weapon_recipe(weapons.recipe_key(kind, main, aux))
    tier = tier_of(content, main)
    problem = forge_problem(state, content, kind, main, aux)
    head = KNOWN_RECIPE.format(name=known.name) if known else NEW_RECIPE
    odds = fusion.quality_odds_text(forge_odds(state, content, world, kind, main, aux))
    note = problem or f"工錢 {price(content, tier)} 兩；{odds}"
    attribute = attribute_of(world, content, kind, main, aux)
    return Option(
        id=f"{GO}{kind}:{main}:{aux}",
        label=f"開爐：{head}（{weapons.NOUNS[kind]}・屬{attribute}・{weapons.TIER_WORDS[tier]}・{note}）",
        enabled=problem is None, wait="" if known else FORGE_WAIT,
    )


def draft_options(state: GameState, content: Content, world: WorldStateStore, art) -> list:
    """單子這一步的選單：挑種類（配得上身上武學的排第一）→ 挑主料（寫階、剩幾個、工錢；付不起灰掉）→ 挑輔料（寫合出來的屬性；
    主料那一種只剩一個時不列）→ 開爐。每一步後面是「上一步」「不打了」（挑種類那一步只有「不打了」）。"""
    from .engine import Option  # noqa: PLC0415

    d = state.player.smith_draft
    fit = weapons.art_weapon(art.id, content, world) if art is not None else None
    undo, cancel = Option(id=UNDO, label="上一步"), Option(id=CANCEL, label="不打了")
    if d.kind is None:
        kinds = sorted(WEAPON_KINDS, key=lambda k: k != fit)
        return [Option(id=f"{KIND}{k}", label=weapons.NOUNS[k] + (weapons.FITS_MARK if k == fit else "")) for k in kinds] + [cancel]
    mats = content.materials
    held = _held(state, content)
    if d.main is None:
        silver = state.player.stats.get("silver", 0)
        out = []
        for mid, n in held:
            m = mats[mid]
            cost = price(content, m.tier)
            note = f"還差 {cost - silver} 兩" if cost > silver else f"工錢 {cost} 兩"
            out.append(Option(id=f"{MAIN}{mid}", label=f"主料：{m.name}（{m.attribute}・{weapons.TIER_WORDS[m.tier]}・剩 {n}・{note}）",
                              enabled=cost <= silver))
        return out + [undo, cancel]
    if d.aux is None:
        tianji = world.read().tianji
        out = []
        for mid, n in held:
            left = n - (1 if mid == d.main else 0)
            if left < 1:
                continue
            m = mats[mid]
            attribute = attribute_with(content, tianji, d.kind, d.main, mid)
            mark = ATTR_MARK if art is not None and d.kind == fit and attribute == art.attribute else ""
            out.append(Option(id=f"{AUX}{mid}", label=f"輔料：{m.name}（{m.attribute}・{weapons.TIER_WORDS[m.tier]}・剩 {left}）→ 屬{attribute}{mark}"))
        return out + [undo, cancel]
    return [go_option(state, content, world, d.kind, d.main, d.aux), undo, cancel]


# ---- 淬煉（4.7）：只淬身上那把；素材挑同階以上最便宜的 ----

TEMPER = "smith:temper"
TEMPER_TITLE = "淬煉"
FULL = "已經淬滿了"  # 待 joy 潤


def temper_material(state: GameState, content: Content) -> str | None:
    """淬身上那把要用的素材：階不低於兵器的、最低階的先（最便宜），同階數量多的先，再照 id；沒有是 None。"""
    w = state.player.weapon
    if w is None:
        return None
    mats = content.materials
    held = [(mats[mid].tier, -n, mid) for mid, n in state.player.materials.items() if n > 0 and mid in mats and mats[mid].tier >= w.tier]
    return min(held)[2] if held else None


def temper_price(content: Content, material: Material) -> int:
    return content.config.weapons.temper_silver.get(str(material.tier), 0)


def temper_problem(state: GameState, content: Content) -> str | None:
    p = state.player
    if not weapons.smith_here(state, content):
        return weapons.NOT_HERE
    if p.weapon is None:
        return "手上沒有兵器"
    if p.weapon.tempers >= content.config.weapons.temper_max:
        return FULL
    mid = temper_material(state, content)
    if mid is None:
        return f"沒有{weapons.TIER_WORDS[p.weapon.tier]}以上的素材"
    short = temper_price(content, content.materials[mid]) - p.stats.get("silver", 0)
    return f"還差 {short} 兩" if short > 0 else None


def temper(state: GameState, content: Content) -> list[str]:
    """淬煉身上那把（4.7）：用一個同階以上的素材（＋那一階的工錢），淬煉次數 +1（加成每次 +temper_step，bonus 現算）。"""
    problem = temper_problem(state, content)
    if problem is not None:
        return [f"（{problem}。）"]
    p = state.player
    mid = temper_material(state, content)
    material = content.materials[mid]
    cost = temper_price(content, material)
    p.materials[mid] -= 1
    if not p.materials[mid]:
        del p.materials[mid]
    p.stats["silver"] -= cost
    p.weapon.tempers += 1
    msgs = [f"鐵匠拿{material.name}把【{p.weapon.name}】淬了一回，這是第 {p.weapon.tempers} 次。"]  # 待 joy 潤
    if cost:
        msgs.append(f"銀兩 -{cost}")
    return msgs + [f"{material.name} -1"]


def temper_option(state: GameState, content: Content):
    """鐵匠鋪選單上的「淬煉」（手上有兵器才有）：寫第幾次、用哪一個素材與工錢；淬滿、沒料、沒錢灰掉寫原因。"""
    from .engine import Option  # noqa: PLC0415

    w = state.player.weapon
    if w is None:
        return None
    rule = content.config.weapons
    if w.tempers >= rule.temper_max:
        return Option(id=TEMPER, label=f"淬煉【{w.name}】（{FULL}）", enabled=False)
    problem = temper_problem(state, content)
    if problem is None:
        m = content.materials[temper_material(state, content)]
        cost = temper_price(content, m)
        note = f"{m.name}×1" + (f"＋{cost} 兩" if cost else "")
    else:
        note = problem
    return Option(id=TEMPER, label=f"淬煉【{w.name}】（第 {w.tempers + 1}/{rule.temper_max} 次・{note}）", enabled=problem is None)
