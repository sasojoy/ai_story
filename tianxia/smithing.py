"""打造與淬煉（docs/superpowers/specs/2026-10-09-兵器-design.md 4.2～4.4、4.7；兵器第二批；四欄設計 4.7：防具照同一套；
打造隱藏配方設計第八、九節：不再叫模型取名）。

| 誰 | 做什麼 |
|---|---|
| 引擎 | 配方鍵、屬性、階、工錢、品質擲骰、名字（一般組合照對照表）、淬煉 |
| 模型 | 不碰打造 |

防具沒有種類：單子與開爐鈕上用 ARMOR_KIND（「防具」）佔種類那一格（smith:forge-go:防具:<主料>:<輔料>），照它分派欄位、組合鍵、開關、
設定（slot_of、recipe_key、here、rules_of）。防具的字、組合鍵、名字對照表在 armor.py。

這個模組 import team 與 fusion（品質的推法、悟性、天時地利）；team 會 import weapons，所以 weapons 不能 import 這裡。
鐵匠鋪的選單項（Option）在 engine 裡，回選單的函式延後 import（同 foreshadow.talk_options）。"""
from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable

from . import annals, armor, equipment, forge_secrets, four_tiers, fusion, library, naming, silver, team, traits, weapons
from .fusion import QualityOdds
from .insights import merged_attribute
from .models import WEAPON_KINDS, Content, Material
from .rules import add_chronicle, add_rumor
from .state import COPY_NAME, DIVINE_UNNAMED, Equipment, GameState, SmithDraft, Weapon
from .world_state import WorldStateStore

NOT_ENOUGH = "身上的素材不到兩個"  # 待 joy 潤
ARMOR_KIND = "防具"  # 單子（SmithDraft.kind）與開爐鈕 id 上代表防具的那一格（防具沒有種類，四欄設計 4.7）


def is_armor(kind: str | None) -> bool:
    """這一爐（單子、開爐鈕、forge 的 kind）打的是防具。"""
    return kind == ARMOR_KIND


def slot_of(kind: str | None) -> str:
    """這一爐打出來放哪一欄：防具 armor，其餘（兵器的種類、還沒挑種類的兵器單子）weapon。"""
    return "armor" if kind == ARMOR_KIND else "weapon"


def rules_of(content: Content, slot: str):
    """打造與淬煉照哪一組設定（工錢、品質、淬煉）：防具 Config.armor，兵器 Config.weapons（四欄設計 2.6、3.4：各欄自己的設定）。"""
    return content.config.armor if slot == "armor" else content.config.weapons


def recipe_key(kind: str, main: str, aux: str) -> str:
    """這一爐的組合鍵：兵器「兵|種類|主料+輔料」（weapons.recipe_key），防具「鎧|主料+輔料」（armor.recipe_key）。"""
    return armor.recipe_key(main, aux) if kind == ARMOR_KIND else weapons.recipe_key(kind, main, aux)


def here(state: GameState, content: Content, kind: str | None) -> bool:
    """這一爐在這裡打得了：防具看防具的開關、其餘看武器的開關，人都要在城鎮（armor.smith_here、weapons.smith_here）。"""
    return (armor.smith_here if kind == ARMOR_KIND else weapons.smith_here)(state, content)


def tier_of(content: Content, main: str) -> int:
    """打出來的階照主料的階（4.2）。"""
    return content.materials[main].tier


def price(content: Content, tier: int, slot: str = "weapon", state: GameState | None = None) -> int:
    """打一件這一階的工錢（兵器 4.2；防具照同一張表，Config.armor.forge_silver）。state 給了照所在地的地盤福利（出陣探索與地盤設計 4.3），
    四捨五入。"""
    base = rules_of(content, slot).forge_silver.get(str(tier), 0)
    if state is None:
        return base
    from . import territory  # noqa: PLC0415  territory → rules：延後 import

    return int(base * territory.price_here(state, content) + 0.5)  # 地盤福利（照依附那一軍）× 名望的店家折扣（名聲設計 4.1）


def attribute_with(content: Content, tianji: int, kind: str, main: str, aux: str) -> str:
    """打出來的屬性（4.2）：照 insights.merged_attribute，種子是「天機|配方鍵」（同 fusion.recipe_seed），所以同一季同一個配方一樣；
    防具的組合鍵是「鎧|主料+輔料」。
    同屬性與四對（剛快、柔慢、快柔、剛慢）合出來的跟主輔順序無關；其餘組合（剛柔、快慢）照種子的雜湊挑兩者之一，配方鍵分主輔，
    主輔對調是另一個配方，挑到的屬性可能不同（4.4：主輔不交換）。選單一次要算好幾個時先讀一次天機，用這一個。"""
    seed = f"{tianji}|{recipe_key(kind, main, aux)}"
    return merged_attribute(content.materials[main], content.materials[aux], seed)


def attribute_of(world: WorldStateStore, content: Content, kind: str, main: str, aux: str) -> str:
    return attribute_with(content, world.tianji(), kind, main, aux)


def forge_problem(state: GameState, content: Content, kind: str, main: str, aux: str) -> str | None:
    """打不成的原因；None＝打得成。順序：不在鐵匠鋪（這一欄關著）、種類、素材認不得、素材不夠（主輔同一種要兩個）、裝備庫滿、銀兩不夠。
    kind 是兵器種類或 ARMOR_KIND。鐵匠鋪的鈕灰掉時寫它，forge 也再驗一次。"""
    if not here(state, content, kind):
        return weapons.NOT_HERE
    if kind not in WEAPON_KINDS and kind != ARMOR_KIND:
        return "沒有這種兵器"
    if main not in content.materials or aux not in content.materials:
        return "沒有這種素材"
    held = state.player.materials
    for mid, need in Counter([main, aux]).items():
        if held.get(mid, 0) < need:
            return f"{content.materials[mid].name}不夠（要 {need} 個）"
    if equipment.rack_full(state, content, slot_of(kind)):
        return weapons.RACK_FULL
    if state.world.divine_lineup is not None:  # 神器輪替季：同一件神器一人一把（正式季整合 5.8），再開那一爐先擋下
        recipe = forge_secrets.match(content, state.world.tianji, slot_of(kind), kind, main, aux, state.world)
        if recipe is not None and recipe.divine and forge_secrets.owns_divine(state.player, recipe.id):
            return forge_secrets.HAVE_DIVINE
    short = price(content, tier_of(content, main), slot_of(kind), state) - state.player.stats.get("silver", 0)
    return f"還差 {short} 兩" if short > 0 else None


def setting_points(state: GameState, content: Content, attribute: str, slot: str = "weapon") -> list[tuple[str, float]]:
    """打造的天時地利（附帶決定 b）：地利、戰場、心靜都同合成（地利看此地探索悟得到同屬性的意境）。最多 setting_max 條。
    兵器沒有正邪，所以合成的「晝夜」這裡沒有；防具照 Config.armor.quality（同一套規則）。"""
    rule = rules_of(content, slot).quality
    out: list[tuple[str, float]] = []
    if rule.terrain and fusion.terrain_here(state, content, attribute):
        out.append(("terrain", rule.terrain))
    if rule.battlefield and attribute == "剛" and fusion.battlefield_here(state, content):
        out.append(("battlefield", rule.battlefield))
    if rule.calm and fusion.calm_now(state, rule.calm_hours):
        out.append(("calm", rule.calm))
    out.sort(key=lambda item: -abs(item[1]))
    return out[: rule.setting_max]


def setting_line(content: Content, scored: list[tuple[str, float]], slot: str = "weapon") -> list[str]:
    """結果多一句含蓄的話：天時地利合起來加分寫 setting_good、扣分寫 setting_bad；沒有、或那句是空的就不寫。"""
    rule = rules_of(content, slot).quality
    total = sum(points for _, points in scored)
    line = rule.setting_good if total > 0 else rule.setting_bad if total < 0 else ""
    return [line] if line else []


def forge_odds(state: GameState, content: Content, world: WorldStateStore, kind: str, main: str, aux: str) -> QualityOdds:
    """這一爐的品質機率（4.3）：輔料的階（比主料高幾階）、悟性、熟手（這個配方這一季打過幾次，有上限）、天時地利，
    從這一欄的 quality.odds（兵器 Config.weapons、防具 Config.armor）推（fusion.odds_from_points）。只看這一爐的組成，
    配方有沒有人打過都一樣。"""
    rule = rules_of(content, slot_of(kind)).quality
    m, a = content.materials[main], content.materials[aux]
    wis = state.player.stats.get("wis", team.BASE_STAT)
    done = state.player.forge_counts.get(recipe_key(kind, main, aux), 0)
    scored = [
        ("aux", rule.aux_tier.get(str(a.tier - m.tier), 0.0)),
        ("wis", (team.stat_factor(content, wis, state.world) - 1) * 100 * rule.wis_weight),
        ("practice", min(rule.practice_cap, rule.practice_point * done)),
    ]
    scored += setting_points(state, content, attribute_of(world, content, kind, main, aux), slot_of(kind))
    return fusion.odds_from_points(scored, rule, silver.furnace_base(state, content, rule.odds))  # 看火候（銀兩出口）換基準


# 開爐的結果句（待 joy 潤）：打出的東西寫在最前面（FB-143：375 寬鐵匠鋪選單長時「剛剛」收成一行，只露開頭十幾個字），「鐵匠把…下爐」接在後面
# 待 joy 潤。{kind} 寫兵器字、{unit} 拳套是副（FB-133）。375 寬「剛剛」收成一行時只露開頭十五、六個字（FB-148）：名器跟一般組合要分得出來、
# 品質也要看得到——名器寫在名字前面（{mark}，括號裡不再寫），階品排在括號最前面。神器原品與仿品打出來那一刻叫「無名神器」「仿・…」，
# 名字已經看得出來，標記照舊寫在階品後面（「三階上品・神器」），不在名字前面重複
FORGED = "打出一{unit}{mark}【{name}】（{grade}・{kind}・屬{attribute}）：鐵匠把{what}下爐。"
ARMOR_FORGED = "打出一件{mark}【{name}】（{grade}・防具・屬{attribute}）：鐵匠把{what}下爐。"


def noun_label(kind: str) -> str:
    """開爐鈕上種類那一格：兵器寫 NOUNS 的字（「棍」「拳套」），防具寫「防具」。"""
    return ARMOR_KIND if kind == ARMOR_KIND else weapons.NOUNS[kind]


def own_rng(state: GameState, key: str) -> random.Random:
    """防具打造的品質擲骰用自己的一份亂數（不動 Game.rng，FB-129；打造隱藏配方設計 9.3）：種子「打造|季數|名號|流水號|組合鍵」，
    流水號是這一件會拿到的 id 號（weapon_serial＋1），同一個人同一季每一件都不同；不看時間。兵器照舊用 Game.rng。"""
    p = state.player
    return random.Random(f"打造|{p.season_number}|{p.name}|{p.weapon_serial + 1}|{key}")


def general_name(content: Content, world: WorldStateStore, kind: str, main: str, aux: str, attribute: str) -> str:
    """一般組合的名字（打造隱藏配方設計 4.1、PM 2026-10-12 決定第 1 條）：防具照對照表（armor.table_name；防具在這一批之前不能打，
    沒有舊的登記）；兵器先看上線前這一季登記過的「兵|」配方（10.1：只讀、不再新增，同一季同一個組合前後才不會兩個名字；下一季起
    表裡沒有），其餘照對照表（weapons.table_name）。不叫模型、不登記。"""
    if kind == ARMOR_KIND:
        return armor.table_name(content, main, aux, attribute)
    old = world.lookup_weapon_recipe(weapons.recipe_key(kind, main, aux))
    return old.name if old is not None else weapons.table_name(content, kind, main, aux)


def forge(
    state: GameState, content: Content, world: WorldStateStore, kind: str, main: str, aux: str, rng: random.Random | None = None,
    report: dict | None = None,
) -> tuple[Equipment | None, list[str]]:
    """打一件（兵器 4.2、4.3；防具 4.7 照同一套，kind 是 ARMOR_KIND；打造隱藏配方設計 4.1、4.2、7.2）：一次拿鎖做完，不叫模型。
    回（那一件, 訊息）；打不成回 (None, [原因])，什麼都不收。先比這一季的隱藏配方（forge_secrets.match，不擲骰）：打中了是名器，
    名字照內容，全服第一個打出的人登記成首位發現者（world.claim_gear_find，原子）、江湖上傳一句，別人照著打記首創名望回饋；
    沒打中照 general_name（上線前登記的舊名字 → 對照表），什麼都不登記。品質照 forge_odds 擲（隱藏配方不改機率；rng 由呼叫端給：
    兵器 Game.rng、防具 own_rng；沒給是下品），名器也只擲這一次；收工錢與兩樣素材、熟手 +1、放進身上或裝備庫。
    神器配方（5.1 甲）一爐必出神器、不擲品質（不碰亂數）：這一季第一把是原品（首位發現者就是原品主人），之後每一把是仿品，仿品數 +1。
    report 給了就填這一爐的首位發現（first）、隱藏配方 id（secret）、神器（divine）：店面的出爐卡用（店面獨立介面設計 2.3）。"""
    problem = forge_problem(state, content, kind, main, aux)
    if problem is not None:
        return None, [f"（{problem}。）"]
    key, slot = recipe_key(kind, main, aux), slot_of(kind)
    tier = tier_of(content, main)
    tianji = world.tianji()
    attribute = attribute_with(content, tianji, kind, main, aux)
    odds = forge_odds(state, content, world, kind, main, aux)
    setting = setting_points(state, content, attribute, slot)
    secret = forge_secrets.match(content, tianji, slot, kind, main, aux, state.world)  # 隱藏配方優先於上線前登記的舊名字（10.1）
    find, first = None, False
    if secret is not None:
        find, first = world.claim_gear_find(forge_secrets.key(secret), forge_secrets.new_find(state, secret, kind, attribute, tier))
        name = secret.name
    else:
        name = general_name(content, world, kind, main, aux, attribute)
    entry = None
    if secret is None and (chance := four_tiers.named_chance(content, main, aux)) > 0:
        # 四階名器（正式季整合 5.2）：沒打中隱藏配方、主料四階時擲一次；用自己的亂數（不碰呼叫端給的 rng，品質那一擲的位置不變），
        # 中了照同一顆亂數從名字表挑一條。不登記、沒有首位發現、不傳江湖
        roll = own_rng(state, f"名器|{key}")
        if roll.random() < chance:
            entry = four_tiers.pick_named(content, slot, kind if slot == "weapon" else None, attribute, roll)
            if entry is not None:
                name = entry.name
    divine = secret is not None and secret.divine
    if report is not None:
        report.update(first=first, secret=secret.id if secret is not None else None, divine=divine)
    if divine:
        # 神器配方（打造隱藏配方設計 5.1 甲）：一爐必出神器、不擲品質（不碰亂數）。第一把是原品（claim_gear_find 那一筆交易裡記下原品主人＝
        # 首位發現者，見 forge_secrets.new_find），之後每一把是仿品（打的人是原品主人自己也一樣，5.3），仿品數 +1
        quality = "上品"
        name = DIVINE_UNNAMED if first else COPY_NAME.format(name=find.name)
        if not first:
            world.add_copy(forge_secrets.key(secret))
    else:
        quality = fusion.roll_quality(odds, rng)  # 跟以前同一個位置、只擲一次：Game.rng 的序列不位移
        silver.use_furnace(state)  # 看火候（銀兩出口）擲這一次就用掉；神器那一爐不擲品質，不用掉
    p = state.player
    used = Counter([main, aux])
    for mid, n in used.items():
        p.materials[mid] -= n
        if not p.materials[mid]:
            del p.materials[mid]
    cost = price(content, tier, slot, state)
    p.stats["silver"] -= cost
    p.forge_counts[key] = p.forge_counts.get(key, 0) + 1
    m, a = content.materials[main], content.materials[aux]
    what = f"兩份{m.name}" if main == aux else f"{m.name}與{a.name}"
    secret_id = secret.id if secret is not None else None
    gear = {"original": divine and first, "copy_of": forge_secrets.key(secret) if divine and not first else None,
            "named_entry": entry.id if entry is not None else None,
            "collected": divine and state.world.divine_lineup is not None}  # 輪替季打的神器跨季帶著走（正式季整合 5.8）
    if slot == "armor":
        item = armor.new_armor(state, name=name, attribute=attribute, tier=tier, quality=quality, recipe=key, secret=secret_id, **gear)
    else:
        item = weapons.new_weapon(state, name=name, kind=kind, attribute=attribute, tier=tier, quality=quality, recipe=key, secret=secret_id,
                                  **gear)
    head = forged_head(item, what)
    lines = forge_secrets.arrival(state, content, secret, find, first) if secret is not None else []
    if entry is not None and entry.note:
        lines = [entry.note]  # 四階名器那一句說明（名字表上的，待 joy 潤）
    msgs = ["\n".join([head, *lines])]
    msgs += [] if divine else setting_line(content, setting, slot)  # 神器那一爐不擲品質：天時地利那一句不寫
    msgs.append(f"銀兩 -{cost}")
    msgs += [f"{content.materials[mid].name} -{n}" for mid, n in used.items()]
    msgs.append(equipment.store(state, item, content))  # 15 級以下打出的神器先進裝備庫（正式季整合 5.8）
    if secret is not None:
        forge_secrets.solve(state, tianji, secret, key)
        if first:  # 7.2：江湖上傳一句（具名，同 fusion._secret_lines）；神器那一句不帶名字（還沒定名），定名時另傳（name_divine）
            # 行狀（玩家傳）：首創。神器原品這時還叫「無名神器」，寫鑄譜上的譜名（待 joy 潤）；定名時另記一筆（name_divine）
            deed = DIVINE_DEED.format(name=secret.name) if divine else f"江湖上第一個打出名器【{secret.name}】。"
            annals.note(state, content, annals.DEED, deed, 4)
            rule = content.config.forge_secrets
            text = rule.divine_rumor.format(who=state.player.name, unit=equipment.unit_for(item.slot, item.kind)) if divine else rule.rumor.format(who=state.player.name, name=secret.name)
            add_rumor(state, text, None, content=content, named=True)
        fusion.echo(state, content, find, first, made="打")  # 別人照著打：首位發現者的首創名望回饋（照 find.id＝「鑄|配方 id」記）
    return item, msgs


def forged_head(item: Equipment, what: str) -> str:
    """開爐成了那一則的第一句（FB-143：打出的東西寫在最前面）：兵器寫兵器字與量詞（FB-133：拳套、弩，拳套一副），防具一件；
    名器、神器、仿品寫在名字前面、階品排在括號最前面（FB-148）。"""
    named = equipment.mark_word(item) == equipment.NAMED_MARK.removeprefix("・")
    mark, grade = ("名器", equipment.tier_quality(item)) if named else ("", equipment.grade(item))
    if item.slot == "armor":
        return ARMOR_FORGED.format(what=what, mark=mark, name=item.name, attribute=item.attribute, grade=grade)
    return FORGED.format(what=what, mark=mark, name=item.name, unit=weapons.unit(item.kind), kind=weapons.noun(item.kind),
                         attribute=item.attribute, grade=grade)


# ---- 神器原品定名（打造隱藏配方設計 5.2；同 cultivation.name_mastered）----

DIVINE_NAMED = "從今以後，江湖上這{unit}神器就叫【{name}】。"  # 待 joy 潤（同絕學定名那一句；{unit} 照欄位，FB-146）
NAME_GONE = "（沒有等著你定名的神器。）"  # 待 joy 潤
NAME_BAD = "這個名字不行：{problem}。"  # 待 joy 潤（同 cultivation.name_mastered）
NAME_TAKEN = "【{name}】已經有人用了，換一個吧。"  # 待 joy 潤（同 cultivation.name_mastered）
DIVINE_DEED = "江湖上第一個打出神器（鑄譜上叫【{name}】）。"  # 待 joy 潤：行狀（玩家傳），打出原品那一下
DIVINE_NAMED_DEED = "替自己打出的神器定名【{name}】。"  # 待 joy 潤：行狀（玩家傳），同絕學定名那一則的份量 5


def name_divine(
    state: GameState, content: Content, world: WorldStateStore, item_id: str, name: str, keep: bool = False,
) -> tuple[bool, list[str]]:
    """替手上的神器原品定名：回（定成了沒, 訊息）。只有原品主人、這一把還沒定名（forge_secrets.unnamed_originals）才行。
    自己取的名字過 naming.name_problem（帶 world.is_character_name，同絕學定名）與 forge_secrets.divine_name_problem；
    keep＝「沿用譜名」：直接用登記當下記的譜名，不過命名過濾（譜名由內容驗過；name_problem 會回 FORGE_CLASH 擋它自己）。
    全服不重名由 world.name_divine 原子判斷。定成了：原品與主人自己的仿品當下改名（別人的仿品下次讀檔跟著改）、首創名望回饋
    記著的名字換掉、江湖史一行（寫名號）、江湖上傳一句（具名）；神器譜照全服那一列。不合格、被搶先、不是你的都什麼都不動，定名的權利還在。"""
    pending = forge_secrets.unnamed_originals(state, world)
    if item_id not in pending:
        return False, [NAME_GONE]
    item = next(i for i in forge_secrets.owned_gear(state.player) if i.id == item_id)
    if keep:
        name = pending[item_id]
    else:
        name = naming.clean_name(name)
        problem = naming.name_problem(name, content, world.is_character_name) or forge_secrets.divine_name_problem(
            content, item.slot, item.kind, name)
        if problem is not None:
            return False, [NAME_BAD.format(problem=problem)]
    reason = world.name_divine(forge_secrets.key_for(item.secret), state.player.name, name, registry=item.collected)  # FB-402
    if reason == "taken":
        return False, [NAME_TAKEN.format(name=name)]
    if reason is not None:
        return False, [NAME_GONE]
    item.name = name
    forge_secrets.refresh_names(state.player, content, world)  # 主人自己手上與裝備庫裡的仿品當下跟著改成「仿・新名字」，不等下一次讀檔
    fusion.rename_echo(state, forge_secrets.key_for(item.secret), name)  # 定名之前就有人照著打：首創名望回饋記的名字也換掉（M2）
    rule, who = content.config.forge_secrets, state.player.name
    unit = equipment.unit_for(item.slot, item.kind)
    add_chronicle(state, rule.named_chronicle.format(who=who, name=name, unit=unit, what=forge_secrets.what_text(item.slot, item.kind)))
    add_rumor(state, rule.named_rumor.format(who=who, name=name), None, content=content, named=True)
    annals.note(state, content, annals.DEED, DIVINE_NAMED_DEED.format(name=name), 5)
    return True, [DIVINE_NAMED.format(name=name, unit=unit)]


# ---- 以器配招（玩家武學追上本命定案 四）：神器原品的主人把它綁在自己一門絕學上，那門絕招照功效寫的 ultimate_bond 加強 ----

BIND_NOT_ORIGINAL = "（只有你打出的神器原品能以器配招。）"
BIND_BAD_ART = "（這一門配不上：要是你自己合成、練成絕學、有絕招的那一門。）"
BIND_ALREADY = "（【{item}】已經配了【{art}】，不能改配。）"
BIND_DONE = "【{item}】與【{art}】人器合一：{bond}。"
BIND_LINE = "以器配招〔{art}〕：{bond}"
NAMED_LINE = "名器同氣〔{art}〕：{bond}"


def bind_options(state: GameState, content: Content, world: WorldStateStore) -> list[tuple[str, str, str]]:
    """配得上的絕學：自己手上（身上與功法庫）自己合成、練成絕學、功效寫了以器配招的那幾門：（武學 id, 名字, 加強的那一句）。"""
    out = []
    for art_id in library.owned_arts(state):
        art = team.player_art(state, content, world, art_id)
        trait = traits.ultimate_trait(content, art)
        if trait is not None and trait.ultimate_bond is not None:
            out.append((art_id, art.name, trait.ultimate_bond.desc))
    return out


def bound_alive(state: GameState, item: Equipment) -> bool:
    return item.bound_art is not None and item.bound_art in library.owned_arts(state)


def bind_problem(state: GameState, content: Content, world: WorldStateStore, item_id: str, art_id: str) -> str | None:
    """以器配招做不了的原因：不是自己手上的神器原品（名將本命兵器不算）、已經配了一門還在手上的、那一門配不上。"""
    item = next((i for i in forge_secrets.owned_gear(state.player) if i.id == item_id), None)
    if item is None or not item.original or not item.secret or item.signature:
        return BIND_NOT_ORIGINAL
    if bound_alive(state, item):
        art = team.player_art(state, content, world, item.bound_art)
        return BIND_ALREADY.format(item=item.name, art=art.name if art else item.bound_art)
    if art_id not in {a for a, _n, _d in bind_options(state, content, world)}:
        return BIND_BAD_ART
    return None


def bind_art(state: GameState, content: Content, world: WorldStateStore, item_id: str, art_id: str) -> tuple[bool, list[str]]:
    """以器配招：綁定了回（True, 那一句）。綁的那一門熔掉、交掉之後才能再配別門（bound_alive）。"""
    problem = bind_problem(state, content, world, item_id, art_id)
    if problem is not None:
        return False, [problem]
    item = next(i for i in forge_secrets.owned_gear(state.player) if i.id == item_id)
    art = team.player_art(state, content, world, art_id)
    item.bound_art = art_id
    bond = traits.ultimate_trait(content, art).ultimate_bond
    return True, [BIND_DONE.format(item=item.name, art=art.name, bond=bond.desc.split("：", 1)[-1])]


def bond_lines(state: GameState, content: Content, world: WorldStateStore, item: Equipment) -> list[str]:
    """修練頁那一列寫的：這件綁了哪一門（以器配招），或身上哪一門絕學跟這件名器同氣。沒有是空的。"""
    if bound_alive(state, item):
        art = team.player_art(state, content, world, item.bound_art)
        trait = traits.ultimate_trait(content, art)
        if trait is not None and trait.ultimate_bond is not None:
            return [BIND_LINE.format(art=art.name, bond=trait.ultimate_bond.desc.split("：", 1)[-1])]
    out = []
    for art_id in (state.player.member.wugong_id, state.player.member.neigong_id):
        art = team.player_art(state, content, world, art_id)
        found = team.gear_bond(content, art, item) if art is not None else None
        if found is not None and found[1] == team.NAMED_SOURCE:
            out.append(NAMED_LINE.format(art=art.name, bond=found[0].desc))
    return out


# ---- 鐵匠鋪的一步一步選單（375×812：每一步只有一排按鈕，最多十二種素材＋兩顆）----

OPEN = "smith:forge"
KIND = "smith:forge-kind:"
MAIN = "smith:forge-main:"
AUX = "smith:forge-aux:"
GO = "smith:forge-go:"
UNDO = "smith:forge-undo"
CANCEL = "smith:forge-cancel"
GO_VERB = "forge-go"
STEP_VERBS = ("forge", "forge-kind", "forge-main", "forge-aux", "forge-undo", "forge-cancel", "temper", "armor-temper")
FORGE_TITLE = "打造"
ASK_KIND = "要打哪一種兵器？"  # 待 joy 潤
ASK_MAIN = "挑主料：主料定這把兵器的階，也定工錢。"  # 待 joy 潤
UNDONE = "退回一步。"  # 待 joy 潤（FB-133）：按「上一步」先回這一句，再問那一步
ASK_AUX = "挑輔料：主料與輔料合起來定這把兵器的屬性。"  # 待 joy 潤
READY = "料都齊了，看一眼機率再開爐。"  # 待 joy 潤
PICKED_KIND = "兵器：{what}。"  # 待 joy 潤：每挑一樣，這一步的回話先回報挑了什麼（進同一則「打造」紀錄），再問下一步
PICKED_MAIN = "主料：{what}。"  # 待 joy 潤
PICKED_AUX = "輔料：{what}。"  # 待 joy 潤
CANCELLED = "你把素材收了回去，這回先不打。"  # 待 joy 潤
ATTR_MARK = "・跟你的武學同屬性"  # 待 joy 潤
ARMOR_ASK_MAIN = "挑主料：主料定這件防具的階，也定工錢。"  # 待 joy 潤（防具沒有挑種類那一步，打開就從主料挑起）
ARMOR_ASK_AUX = "挑輔料：主料與輔料合起來定這件防具的屬性。"  # 待 joy 潤
ARMOR_ATTR_MARK = "・跟你的內功同屬性"  # 待 joy 潤（防具看內功，四欄設計 4.2）
GO_LABEL = "開爐：{what}{head}（{kind}・屬{attribute}・{tier}・{note}）"  # 待 joy 潤：{what} 是放進爐裡的主料＋輔料；{head} 平常是空的（設計 6.4：不露隱藏配方），自己的鑄譜上打中過這一爐才寫 SOLVED_HEAD
SOLVED_HEAD = " → 照鑄譜上的【{name}】打"  # 待 joy 潤：這一爐在自己的鑄譜上打中過才寫（打造隱藏配方設計 6.4）；別人打中的、沒打中過的都不寫
NAMED_HINT = "四階的料，打出名器的機會很大"  # 待 joy 潤：主料是四階時開爐鈕機率那一段多這一句（正式季整合 5.2）
DIVINE_HEAD = " → 照鑄譜上的【{name}】打：必出神器（仿品）"  # 待 joy 潤：自己的鑄譜上打中過的神器配方（6.4、5.1 甲）；{name} 是譜名


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


# 打造單子自己的回話（step 回的那幾句）：問下一步的、退回去的、不打了的整句照常數認；挑了什麼（PICKED_*）的中間是素材或種類的名字，
# 拆成前後兩段認。Game.choose 開爐成了併進「打造」那一則時用 is_step_line 收掉這些（FB-141），別的話（大勢門檻的消息之類）留著
_STEP_LINES = frozenset({ASK_KIND, ASK_MAIN, ASK_AUX, ARMOR_ASK_MAIN, ARMOR_ASK_AUX, READY, CANCELLED, UNDONE})
_PICKED_FRAMES = tuple(tuple(template.split("{what}")) for template in (PICKED_KIND, PICKED_MAIN, PICKED_AUX))


def is_step_line(line: str) -> bool:
    """這一行是不是打造單子一步一步走時自己回的話（step 的回話：問下一步、挑了什麼、上一步、不打了）。開爐的結果、拒絕句、
    別的消息都不是。照上面的常數認，句子改了這裡跟著改，不另寫一份。"""
    if line in _STEP_LINES:
        return True
    return any(len(line) > len(head) + len(tail) and line.startswith(head) and line.endswith(tail) for head, tail in _PICKED_FRAMES)


def title(arg: str) -> str:
    """鐵匠鋪上這一下的江湖紀錄標題：打造的每一步是「打造」、淬煉是「淬煉」，其餘是「鐵匠鋪」。"""
    if is_forge_step(arg):
        return FORGE_TITLE
    return TEMPER_TITLE if arg in ("temper", "armor-temper") else weapons.SMITH


def _held(state: GameState, content: Content) -> list[tuple[str, int]]:
    """背包裡打得了的素材：高階的先、同階數量多的先、再照 id（最可能要用的排在第一屏）。"""
    mats = content.materials
    return sorted(
        ((mid, n) for mid, n in state.player.materials.items() if n > 0 and mid in mats),
        key=lambda pair: (-mats[pair[0]].tier, -pair[1], pair[0]),
    )


def held(state: GameState, content: Content) -> list[tuple[str, int]]:
    """背包裡打得了的素材（店面的素材格照這個順序排，同一步一步選單的主料、輔料）：高階的先、同階數量多的先、再照 id。"""
    return _held(state, content)


def draft_stale(content: Content, draft: SmithDraft) -> bool:
    """存檔裡的單子指著內容已經沒有的種類或素材（內容改版）：選單畫不出來（go_option 查素材會丟 KeyError），要從頭來。
    防具的單子 kind 是 ARMOR_KIND。"""
    return (draft.kind is not None and draft.kind not in WEAPON_KINDS and draft.kind != ARMOR_KIND) or any(
        mid is not None and mid not in content.materials for mid in (draft.main, draft.aux))


def draft_here(state: GameState, content: Content, draft: SmithDraft) -> bool:
    """這張單子在這裡還打得了（存檔修補、同步時看）：防具的單子看防具的開關、兵器的看武器的開關（人都要在城鎮）。"""
    return here(state, content, draft.kind)


def open_problem(state: GameState, content: Content, slot: str = "weapon") -> str | None:
    """「打造兵器…／打造防具…」按不按得下去：這一欄放不下、素材不到兩個、最便宜的一爐也付不起，就灰掉寫原因。"""
    if equipment.rack_full(state, content, slot):
        return weapons.RACK_FULL
    held = _held(state, content)
    if sum(n for _, n in held) < 2:
        return NOT_ENOUGH
    short = min(price(content, content.materials[mid].tier, slot, state) for mid, _ in held) - state.player.stats.get("silver", 0)
    return f"還差 {short} 兩" if short > 0 else None


def forge_door(state: GameState, content: Content, slot: str = "weapon"):
    """鐵匠鋪那一頁的「打造兵器…」或「打造防具…」：打開一步一步的單子（step 的 "forge"，照停在哪一頁開兵器或防具的單子）。"""
    from .engine import Option  # noqa: PLC0415  延後 import：engine → smithing

    problem = open_problem(state, content, slot)
    if slot == "armor":
        return Option(id=OPEN, label=f"打造防具…（{problem or '挑主料、輔料'}）", enabled=problem is None)  # 待 joy 潤
    return Option(id=OPEN, label=f"打造兵器…（{problem or '挑種類、主料、輔料'}）", enabled=problem is None)


def _material_name(content: Content, mid: str) -> str:
    return content.materials[mid].name if mid in content.materials else mid


def step(state: GameState, content: Content, verb: str, arg: str) -> list[str]:
    """單子往前或往後一步（選項都由 Game.choose 驗過在選單上，arg 一定是選單給的）。開爐（forge-go）不在這裡，見 forge。
    挑種類、主料、輔料的回話先寫挑了什麼（PICKED_*），再問下一步：這幾句併進同一則「打造」紀錄，事後看得到這一爐放了哪兩樣。"""
    p = state.player
    if verb == "temper":
        return temper(state, content)
    if verb == "armor-temper":
        return temper(state, content, "armor")
    if verb == "forge":
        armor_page = equipment.page(p, content) == "armor"  # 兩頁共用 smith:forge：照停在哪一頁開兵器或防具的單子
        p.smith_draft = SmithDraft(kind=ARMOR_KIND) if armor_page else SmithDraft()
        return [ARMOR_ASK_MAIN if armor_page else ASK_KIND]
    d = p.smith_draft
    if d is None:
        return ["（此刻無法這麼做。）"]
    if verb == "forge-kind":
        d.kind = arg
        return [PICKED_KIND.format(what=weapons.NOUNS.get(arg, arg)), ASK_MAIN]
    if verb == "forge-main":
        d.main = arg
        return [PICKED_MAIN.format(what=_material_name(content, arg)), ARMOR_ASK_AUX if d.kind == ARMOR_KIND else ASK_AUX]
    if verb == "forge-aux":
        d.aux = arg
        return [PICKED_AUX.format(what=_material_name(content, arg)), READY]
    if verb == "forge-undo":  # 先說退回了一步，再問（FB-133：只回下一步的問句，讀起來像同一個問題問了兩次）
        armor_draft = d.kind == ARMOR_KIND
        if d.aux is not None:
            d.aux = None
            return [UNDONE, ARMOR_ASK_AUX if armor_draft else ASK_AUX]
        if d.main is not None:
            d.main = None
            return [UNDONE, ARMOR_ASK_MAIN if armor_draft else ASK_MAIN]
        if armor_draft:
            return [ARMOR_ASK_MAIN]  # 防具沒有挑種類那一步：已經在第一步（選單上也沒有這一顆）
        d.kind = None
        return [UNDONE, ASK_KIND]
    if verb == "forge-cancel":
        p.smith_draft = None
        return [CANCELLED]
    return ["（此刻無法這麼做。）"]


def go_option(state: GameState, content: Content, world: WorldStateStore, kind: str, main: str, aux: str):
    """開爐那一顆（打造隱藏配方設計 6.4）：寫放進爐裡的主料＋輔料、種類（防具寫「防具」，noun_label）、屬性、階、工錢與三個品質的
    機率（不寫品級）；不帶 wait（不再等模型）。不露隱藏配方：只有這一爐在**自己的**鑄譜上打中過，才在兩樣後面接 SOLVED_HEAD
    （神器配方接 DIVINE_HEAD，不寫機率：一定是上品的仿品）；別人打中的、沒打中過的都不寫。打不成灰掉寫原因。"""
    from .engine import Option  # noqa: PLC0415

    tianji, slot = world.tianji(), slot_of(kind)
    known = forge_secrets.solved_name(state, content, tianji, slot, kind, main, aux)
    recipe = forge_secrets.match(content, tianji, slot, kind, main, aux, state.world) if known else None
    divine = recipe is not None and recipe.divine
    tier = tier_of(content, main)
    problem = forge_problem(state, content, kind, main, aux)
    cost = f"工錢 {price(content, tier, slot, state)} 兩"
    note = problem or (cost if divine else f"{cost}；{fusion.quality_odds_text(forge_odds(state, content, world, kind, main, aux))}")
    if problem is None and not divine and four_tiers.named_chance(content, main, aux) > 0:
        note += f"；{NAMED_HINT}"  # 正式季整合 5.2：不寫百分比、不寫會不會出神器（開爐鈕不能變成試配方的工具）
    head = (DIVINE_HEAD if divine else SOLVED_HEAD).format(name=known) if known else ""
    return Option(
        id=f"{GO}{kind}:{main}:{aux}",
        label=GO_LABEL.format(
            what=f"{content.materials[main].name}＋{content.materials[aux].name}",
            head=head, kind=noun_label(kind),
            attribute=attribute_of(world, content, kind, main, aux), tier=weapons.TIER_WORDS[tier], note=note,
        ),
        enabled=problem is None,
    )


def draft_options(state: GameState, content: Content, world: WorldStateStore, art, neigong=None) -> list:
    """單子這一步的選單：兵器是挑種類（配得上身上武學的排第一）→ 挑主料（寫階、剩幾個、工錢；付不起灰掉）→ 挑輔料（寫合出來的屬性；
    主料那一種只剩一個時不列；跟身上武學同屬性的標出來）→ 開爐。防具（kind 是 ARMOR_KIND）沒有挑種類那一步，從主料挑起、第一步沒有
    「上一步」，輔料標的是跟身上**內功**同屬性的（neigong）。每一步後面是「上一步」「不打了」（第一步只有「不打了」）。"""
    from .engine import Option  # noqa: PLC0415

    d = state.player.smith_draft
    armor_draft = d.kind == ARMOR_KIND
    fit = weapons.art_weapon(art.id, content, world) if art is not None and not armor_draft else None
    undo, cancel = Option(id=UNDO, label="上一步"), Option(id=CANCEL, label="不打了")
    if d.kind is None:
        kinds = sorted(WEAPON_KINDS, key=lambda k: k != fit)
        return [Option(id=f"{KIND}{k}", label=weapons.NOUNS[k] + (weapons.FITS_MARK if k == fit else "")) for k in kinds] + [cancel]
    mats = content.materials
    held = _held(state, content)
    slot = slot_of(d.kind)
    if d.main is None:
        silver = state.player.stats.get("silver", 0)
        out = []
        for mid, n in held:
            m = mats[mid]
            cost = price(content, m.tier, slot, state)
            note = f"還差 {cost - silver} 兩" if cost > silver else f"工錢 {cost} 兩"
            out.append(Option(id=f"{MAIN}{mid}", label=f"主料：{m.name}（{m.attribute}・{weapons.TIER_WORDS[m.tier]}・剩 {n}・{note}）",
                              enabled=cost <= silver))
        return out + ([cancel] if armor_draft else [undo, cancel])
    if d.aux is None:
        tianji = world.tianji()
        out = []
        for mid, n in held:
            left = n - (1 if mid == d.main else 0)
            if left < 1:
                continue
            m = mats[mid]
            attribute = attribute_with(content, tianji, d.kind, d.main, mid)
            if armor_draft:
                mark = ARMOR_ATTR_MARK if neigong is not None and attribute == neigong.attribute else ""
            else:
                mark = ATTR_MARK if art is not None and d.kind == fit and attribute == art.attribute else ""
            out.append(Option(id=f"{AUX}{mid}", label=f"輔料：{m.name}（{m.attribute}・{weapons.TIER_WORDS[m.tier]}・剩 {left}）→ 屬{attribute}{mark}"))
        return out + [undo, cancel]
    return [go_option(state, content, world, d.kind, d.main, d.aux), undo, cancel]


# ---- 淬煉（兵器 4.7；防具 4.1 照同一套）：只淬身上那一件；素材挑同階以上最便宜的 ----

TEMPER = "smith:temper"
ARMOR_TEMPER = "smith:armor-temper"  # 防具頁的「淬煉」（同 armor-buy、armor-repair 另開一個 id；兩頁各淬各的）
TEMPER_TITLE = "淬煉"
FULL = "已經淬滿了"  # 待 joy 潤


def temper_floor(item: Equipment) -> int:
    """淬這一件至少要幾階的料：同階或更高；四階裝備（含四階的神器原品、仿品）收三階以上（正式季整合 5.3：不然淬一次就要吃一個神器料）。"""
    return min(item.tier, four_tiers.TOP_COMMON)


def temper_material(state: GameState, content: Content, slot: str = "weapon") -> str | None:
    """淬身上那一件（slot 那一欄）要用的素材：階不低於 temper_floor 的、最低階的先（最便宜），同階數量多的先，再照 id；沒有是 None。"""
    item = equipment.worn(state.player, slot)
    if item is None:
        return None
    mats, floor = content.materials, temper_floor(item)
    held = [(mats[mid].tier, -n, mid) for mid, n in state.player.materials.items() if n > 0 and mid in mats and mats[mid].tier >= floor]
    return min(held)[2] if held else None


def temper_price(content: Content, material: Material, slot: str = "weapon") -> int:
    return rules_of(content, slot).temper_silver.get(str(material.tier), 0)


def temper_problem(state: GameState, content: Content, slot: str = "weapon") -> str | None:
    p = state.player
    if not here(state, content, ARMOR_KIND if slot == "armor" else None):
        return weapons.NOT_HERE
    item = equipment.worn(p, slot)
    if item is None:
        return armor.NO_ARMOR if slot == "armor" else "手上沒有兵器"
    if item.tempers >= rules_of(content, slot).temper_max:
        return FULL
    mid = temper_material(state, content, slot)
    if mid is None:
        return f"沒有{weapons.TIER_WORDS[temper_floor(item)]}以上的素材"
    short = temper_price(content, content.materials[mid], slot) - p.stats.get("silver", 0)
    return f"還差 {short} 兩" if short > 0 else None


def temper(state: GameState, content: Content, slot: str = "weapon") -> list[str]:
    """淬煉身上那一件（兵器 4.7、防具 4.1）：用一個同階以上的素材（＋那一階的工錢），淬煉次數 +1（兵器的加成、防具的減損每次
    +temper_step，都是現算）。"""
    problem = temper_problem(state, content, slot)
    if problem is not None:
        return [f"（{problem}。）"]
    p = state.player
    item = equipment.worn(p, slot)
    mid = temper_material(state, content, slot)
    material = content.materials[mid]
    cost = temper_price(content, material, slot)
    p.materials[mid] -= 1
    if not p.materials[mid]:
        del p.materials[mid]
    p.stats["silver"] -= cost
    item.tempers += 1
    msgs = [f"鐵匠拿{material.name}把【{item.name}】淬了一回，這是第 {item.tempers} 次。"]  # 待 joy 潤
    if cost:
        msgs.append(f"銀兩 -{cost}")
    return msgs + [f"{material.name} -1"]


def temper_option(state: GameState, content: Content, slot: str = "weapon"):
    """鐵匠鋪那一頁的「淬煉」（身上那一欄有東西才有；兵器頁 smith:temper、防具頁 smith:armor-temper）：寫第幾次、用哪一個素材與工錢；
    淬滿、沒料、沒錢灰掉寫原因。"""
    from .engine import Option  # noqa: PLC0415

    item = equipment.worn(state.player, slot)
    if item is None:
        return None
    oid, rule = (ARMOR_TEMPER if slot == "armor" else TEMPER), rules_of(content, slot)
    if item.tempers >= rule.temper_max:
        return Option(id=oid, label=f"淬煉【{item.name}】（{FULL}）", enabled=False)
    problem = temper_problem(state, content, slot)
    if problem is None:
        m = content.materials[temper_material(state, content, slot)]
        cost = temper_price(content, m, slot)
        note = f"{m.name}×1" + (f"＋{cost} 兩" if cost else "")
    else:
        note = problem
    return Option(id=oid, label=f"淬煉【{item.name}】（第 {item.tempers + 1}/{rule.temper_max} 次・{note}）", enabled=problem is None)


# ---- 整季機器人用的（兵器設計第六節、四欄設計第九節：量平衡要用到打造與淬煉；伺服器假人不打造不淬煉，打造隱藏配方 PM 決定第 3 條）----


def wizard_steps(kind: str, main: str, aux: str) -> list[str]:
    """照單子打一件要按的幾顆：兵器五顆（打開、種類、主料、輔料、開爐），防具沒有種類那一顆（四顆）。"""
    steps = [OPEN, f"{MAIN}{main}", f"{AUX}{aux}", f"{GO}{kind}:{main}:{aux}"]
    return steps if kind == ARMOR_KIND else [OPEN, f"{KIND}{kind}", *steps[1:]]


def _pick_pair(
    state: GameState, content: Content, prefer: str | None, mine: list[Equipment],
    ok: Callable[[str, str], bool] | None = None,
) -> tuple[str, str] | None:
    """整季機器人一爐挑哪兩樣（兵器、防具共用）：主料挑背包裡最高階的（同階先挑屬性是 prefer 的、再挑最多的、再照 id）；輔料先挑同一種
    （夠兩個時），不然挑跟主料最近一階、數量最多的。素材不到兩個、或 mine（身上與裝備庫裡算數的那幾件）裡已經有一件階比主料高、
    或同階而且是自己打的，是 None（不然每次路過都打一件）。ok 給了就跳過它說不行的組合（防具：合出來會被內功剋的），照同樣的順序
    試下一個輔料、再試同階的下一個主料，都不行是 None；沒給（兵器）就是第一個組合，跟抽出來之前的 forge_plan 一模一樣。"""
    mats = content.materials
    held = {mid: n for mid, n in state.player.materials.items() if n > 0 and mid in mats}
    # 素材四階（正式季整合 8.1）：一般組合不拿四階（神器的料）；湊齊兩個四階（不分屬性）才開四階的爐，主輔都是四階
    tier4 = {mid: n for mid, n in held.items() if four_tiers.is_tier4(mats[mid])}
    if sum(tier4.values()) >= 2 and (pair := _pick_from(content, tier4, prefer, mine, ok)) is not None:
        return pair
    return _pick_from(content, {mid: n for mid, n in held.items() if mid not in tier4}, prefer, mine, ok)


def _pick_from(
    content: Content, held: dict[str, int], prefer: str | None, mine: list[Equipment], ok: Callable[[str, str], bool] | None,
) -> tuple[str, str] | None:
    """_pick_pair 在這一堆素材裡挑一爐（規則見 _pick_pair）。"""
    mats = content.materials
    if sum(held.values()) < 2:
        return None
    top = max(mats[mid].tier for mid in held)
    if any(item.tier > top or (item.tier == top and item.recipe is not None) for item in mine):
        return None
    mains = sorted((mid for mid in held if mats[mid].tier == top), key=lambda mid: (mats[mid].attribute != prefer, -held[mid], mid))
    for main in mains:
        auxes = ([main] if held[main] >= 2 else []) + sorted(
            (mid for mid in held if mid != main), key=lambda mid: (top - mats[mid].tier, -held[mid], mid))
        for aux in auxes:
            if ok is None or ok(main, aux):
                return main, aux
    return None


def forge_plan(state: GameState, content: Content, world: WorldStateStore, art) -> tuple[str, str, str] | None:
    """整季機器人要打哪一把：身上那門武學配得上的種類；主料、輔料照 _pick_pair（同階先挑跟武學同屬性的）。手上或裝備庫已經有一把
    配得上、階比主料高、或同階而且是自己打的，就不打。打不成（forge_problem）是 None。兵器不看相剋（跟抽出 _pick_pair 之前一樣）。"""
    if art is None or not weapons.smith_here(state, content):
        return None
    kind = weapons.art_weapon(art.id, content, world)
    if kind is None:
        return None
    mine = [w for w in [state.player.weapon, *equipment.in_slot(state.player, "weapon")] if weapons.usable(w, art, content, world)]  # 裝備四欄 3.3
    pair = _pick_pair(state, content, art.attribute, mine)
    if pair is None:
        return None
    main, aux = pair
    return (kind, main, aux) if forge_problem(state, content, kind, main, aux) is None else None


def armor_plan(state: GameState, content: Content, world: WorldStateStore, neigong) -> tuple[str, str, str] | None:
    """整季機器人要打哪一件防具（照兵器的 forge_plan）：主料、輔料照 _pick_pair（同階先挑跟身上內功同屬性的：防具對上內功，四欄設計 4.2），
    跳過合出來會被內功剋的組合（attribute_of 照天機算）。身上或裝備庫已經有一件不被內功剋的防具階比主料高、或同階而且是自己打的，
    就不打（被內功剋的那幾件不算：不然打出一件相剋的就再也不打那一階）。防具關著、打不成是 None。"""
    if not armor.smith_here(state, content):
        return None
    mine = [a for a in [state.player.armor, *equipment.in_slot(state.player, "armor")]
            if a is not None and not armor.clashes(a.attribute, neigong)]
    pair = _pick_pair(
        state, content, neigong.attribute if neigong is not None else None, mine,
        ok=lambda main, aux: not armor.clashes(attribute_of(world, content, ARMOR_KIND, main, aux), neigong),
    )
    if pair is None:
        return None
    main, aux = pair
    return (ARMOR_KIND, main, aux) if forge_problem(state, content, ARMOR_KIND, main, aux) is None else None


def better_in_rack(state: GameState, content: Content, world: WorldStateStore, art) -> Weapon | None:
    """裝備庫裡威力加成比手上那把高的那一把（最高的；同分照 id），沒有是 None。"""
    now = weapons.bonus(state.player.weapon, art, content, world)
    spare = [w for w in equipment.in_slot(state.player, "weapon") if equipment.wear_problem(state, content, w) is None]  # 穿不上的神器不挑
    best = max(spare, key=lambda w: (weapons.bonus(w, art, content, world), w.id), default=None)
    return best if best is not None and weapons.bonus(best, art, content, world) > now + 1e-9 else None


def temper_wanted(state: GameState, content: Content, world: WorldStateStore, art) -> bool:
    """手上那把配得上、淬得了、而且沒有更高的一把要打（素材先留給打新的）。"""
    return (
        weapons.usable(state.player.weapon, art, content, world) and temper_problem(state, content) is None
        and forge_plan(state, content, world, art) is None
    )


def has_errand(state: GameState, content: Content, world: WorldStateStore, art) -> bool:
    return (
        forge_plan(state, content, world, art) is not None or better_in_rack(state, content, world, art) is not None
        or temper_wanted(state, content, world, art)
    )


def armor_temper_wanted(state: GameState, content: Content, world: WorldStateStore, neigong) -> bool:
    """身上有防具、淬得了、而且沒有更高的一件要打（素材先留給打新的）。"""
    return (
        state.player.armor is not None and temper_problem(state, content, "armor") is None
        and armor_plan(state, content, world, neigong) is None
    )


def armor_errand(state: GameState, content: Content, world: WorldStateStore, neigong) -> bool:
    """防具頁有打造或淬煉的事（換、買、修看 armor.wanted，bot.smith_want 已經算了）。"""
    return armor_plan(state, content, world, neigong) is not None or armor_temper_wanted(state, content, world, neigong)
