"""防具（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第四節；裝備一）：一場仗少扣的氣血與內傷、耐久、鐵匠鋪架上四件、
修、換、拆、機器人該按哪一顆、修練頁每一列與角色卡那一行。

只 import models、state、martial_arts、equipment、weapons（兵器的字表：防具的名字不能有兵器的字；weapons 不 import 這裡）；
team 反過來呼叫它（take_encounter_toll、toll_saved、Game._raid_spoils 都經
team.armor_cut），所以這裡不 import team 或 rules——身上那門內功由呼叫端解好（team.player_art）再傳進來，同 weapons 拿武學的做法。
防具不從打仗掉（4.9）。打造與淬煉（四欄設計 4.7、打造隱藏配方設計第九節）：配方鍵、防具字、名字對照表在這裡，打造的流程在
smithing（照兵器那一套）。
"""
from __future__ import annotations

from . import equipment, weapons
from .equipment import NO_REPAIR_MATERIAL, NOT_HERE, RACK_FULL, grade, repair_material
from .martial_arts import MartialArt, counters
from .models import Content
from .state import Equipment, GameState

SHOP_ATTRIBUTES = ("剛", "柔", "快", "慢")  # 4.6：架上照屬性擺四件、不分種類；陰陽虛實要等防具打造
SHOP_NAMES = {"剛": "鐵葉甲", "柔": "軟皮甲", "快": "輕綃衫", "慢": "厚氈袍"}  # 待 joy 潤（都過了 naming.name_problem）
WEAR_WORD = equipment.WEAR_WORDS["armor"]  # 「耐久度」：角色卡、修練頁每一列（_row 的 wear_word）、鐵匠鋪修與換上兩顆鈕都讀這個，不寫死（3.1、2.5）
WORN_WARNING = "你的{name}破了好幾處，找間鐵匠鋪補一補。"  # 待 joy 潤（4.5）
EMPTY = "身上沒有防具。"  # 待 joy 潤：修練頁防具那一段身上空著
RACK_NOTE = "城裡的鐵匠鋪打得出、買得到、修得好，也淬得了；用不上的拆了換素材。"  # 待 joy 潤：修練頁防具那一段底下（防具打造之後同兵器那一句）
NO_ARMOR = "身上沒有防具"  # 待 joy 潤：修鈕灰掉時的原因
NO_SUCH = "沒有這一件"  # 待 joy 潤：買架上沒有的屬性（舊分頁、手改的 id）
INTACT = "還很完好"  # 待 joy 潤：耐久滿的不用修
MATCH_NOTE = "跟你的內功同屬性"  # 待 joy 潤
CLASH_NOTE = "跟你的內功相剋"  # 待 joy 潤
BUY = "smith:armor-buy:"
REPAIR = "smith:armor-repair"
REPAIR_AT = 50  # 機器人與假人耐久低到這裡以下才修（同 weapons.REPAIR_AT）


def _match(attribute: str, neigong: MartialArt | None) -> int:
    """對上內功（4.2）：同屬性 +1、相剋（ATTRIBUTE_COUNTERS 兩個方向都查）−1、其餘或沒有內功 0。"""
    if neigong is None or not attribute:
        return 0
    if attribute == neigong.attribute:
        return 1
    return -1 if counters(attribute, neigong.attribute) or counters(neigong.attribute, attribute) else 0


def edge_factor(content: Content, item: Equipment) -> float:
    """耐久度係數（4.1）：全壞剩 edge_floor，滿的是 1。"""
    floor = content.config.armor.edge_floor
    return floor + (1 - floor) * max(0, min(100, item.edge)) / 100


def cut(item: Equipment | None, neigong: MartialArt | None, content: Content) -> float:
    """這件防具現在一場少扣幾成氣血（4.1）：（階＋品質＋淬煉＋對上內功）夾在 0 以上，再乘耐久度係數。開關關著、沒穿、
    不是防具那一欄的是 0。每次現算、不快取：換了內功、修了、破了，下一場就照新的算。內傷是扣掉的量的固定幾成，所以同比例跟著少。"""
    rule = content.config.armor
    if not rule.enabled or item is None or item.slot != "armor":
        return 0.0
    if item.original:  # 神器原品、仿品（打造隱藏配方設計 4.3、5.6）：基本值取代階那一格；不看內容、不另加名器的 2%
        base = rule.original_cut
    elif item.copy_of is not None:
        base = rule.copy_cut
    else:
        base = rule.tier_cut.get(str(item.tier), 0.0)
    base += rule.quality_cut.get(item.quality, 0.0) + rule.temper_step * item.tempers
    base += rule.match * _match(item.attribute, neigong)
    if equipment.named(content, item):
        base += rule.named_cut  # 名器多一截（打造隱藏配方設計 4.2）
    return max(0.0, base) * edge_factor(content, item)


def fresh_cut(item: Equipment | None, neigong: MartialArt | None, content: Content) -> float:
    """修好之後（耐久 100）的減損：機器人比較兩件防具用這個，不然破一點的好防具會被當成比較差的。"""
    return cut(item.model_copy(update={"edge": 100}), neigong, content) if item is not None else 0.0


def wears(kind: str, tier: str) -> bool:
    """這一場磨不磨防具（4.5）：遊歷、探索野怪磨；截殺只有落敗的那一邊磨（截殺只有輸的挨打，4.4）。挑戰大勢人物本人的戰報 kind 是
    event，由 Game._challenge 明說要磨（_file_battle 的 armor_wear）；切磋、頭目戰、劇情戰都不磨；全服決戰不走 _file_battle。"""
    return kind in ("train", "wild") or (kind == "raid" and tier == "落敗")


def wear(state: GameState, content: Content, tier: str) -> list[str]:
    """打完一場，身上那件扣耐久度（4.5，照結果）；第一次低到 edge_warn 以下回一句提醒（只一次，修好或換一件才重設）。"""
    rule, p = content.config.armor, state.player
    if not rule.enabled or p.armor is None:
        return []
    p.armor.edge = max(0, p.armor.edge - rule.wear.get(tier, 0))
    if p.armor.edge < rule.edge_warn and not p.armor_warned:
        p.armor_warned = True
        return [WORN_WARNING.format(name=p.armor.name)]
    return []


# ---- 鐵匠鋪的防具頁（4.6）：買、修、換、拆 ----

def smith_here(state: GameState, content: Content) -> bool:
    """這裡買得到、修得了防具：防具開著、人在城鎮。"""
    return equipment.on(content, "armor") and equipment.in_town(state, content)


def shop_item(attribute: str) -> Equipment:
    """架上那一件（還沒買，id 是「架:屬性」）：一階下品。鐵匠鋪的「買」鈕寫它的減損、機器人比較用。"""
    return Equipment(id=f"架:{attribute}", slot="armor", name=SHOP_NAMES[attribute], attribute=attribute, tier=1, quality="下品")


def new_armor(
    state: GameState, *, name: str, attribute: str, tier: int, quality: str, recipe: str | None = None, secret: str | None = None,
    original: bool = False, copy_of: str | None = None,
) -> Equipment:
    """新的一件（四欄共用的流水號 +1，id「甲:N」）；recipe 是自己打的那一件的組合鍵（「鎧|主料+輔料」），買的沒有；secret 是名器或神器的
    隱藏配方 id；original／copy_of 是神器的原品與仿品（打造隱藏配方設計 5.3、5.6）。"""
    return Equipment(id=equipment.next_id(state, "armor"), slot="armor", name=name, attribute=attribute, tier=tier, quality=quality,
                     recipe=recipe, secret=secret, original=original, copy_of=copy_of)


def rack_full(state: GameState, content: Content) -> bool:
    return equipment.rack_full(state, content, "armor")


def buy_problem(state: GameState, content: Content, attribute: str) -> str | None:
    if not smith_here(state, content):
        return NOT_HERE  # 鐵匠鋪的選單關了、人走了：引擎層自己也再驗一次
    if attribute not in SHOP_ATTRIBUTES:
        return NO_SUCH
    if rack_full(state, content):
        return RACK_FULL
    short = content.config.armor.shop_price - state.player.stats.get("silver", 0)
    return f"還差 {short} 兩" if short > 0 else None


def buy(state: GameState, content: Content, attribute: str) -> list[str]:
    problem = buy_problem(state, content, attribute)
    if problem is not None:
        return [f"（{problem}。）"]
    price = content.config.armor.shop_price
    state.player.stats["silver"] -= price
    item = new_armor(state, name=SHOP_NAMES[attribute], attribute=attribute, tier=1, quality="下品")
    return [f"你花 {price} 兩買下一件【{item.name}】。", equipment.store(state, item)]  # 待 joy 潤


def repair_problem(state: GameState, content: Content) -> str | None:
    p, rule = state.player, content.config.armor
    if not smith_here(state, content):
        return NOT_HERE
    if p.armor is None:
        return NO_ARMOR
    if p.armor.edge >= 100:
        return INTACT
    if repair_material(state, content) is None:
        return NO_REPAIR_MATERIAL
    short = rule.repair_silver - p.stats.get("silver", 0)
    return f"還差 {short} 兩" if short > 0 else None


def repair(state: GameState, content: Content) -> list[str]:
    """修（4.5）：一個一階素材（屬性不限）＋工錢，耐久度回滿。只能在鐵匠鋪。"""
    problem = repair_problem(state, content)
    if problem is not None:
        return [f"（{problem}。）"]
    p, rule = state.player, content.config.armor
    material = repair_material(state, content)
    p.materials[material] -= 1
    if not p.materials[material]:
        del p.materials[material]
    p.stats["silver"] -= rule.repair_silver
    p.armor.edge, p.armor_warned = 100, False
    return [f"鐵匠拿{content.materials[material].name}把【{p.armor.name}】補好了（銀兩 -{rule.repair_silver}）。"]  # 待 joy 潤


def wield(state: GameState, content: Content, item_id: str) -> list[str]:
    """鐵匠鋪防具頁的「換上」：只看防具那一欄。"""
    return equipment.wield(state, content, item_id, ("armor",))


def dismantle(state: GameState, content: Content, item_id: str) -> list[str]:
    """鐵匠鋪防具頁的「拆解」（4.8）：只看防具那一欄。"""
    return equipment.dismantle(state, content, item_id, ("armor",))


def _shop_pick(neigong: MartialArt | None) -> str:
    """機器人買哪一件（第九節）：跟內功同屬性的；架上沒有（陰陽虛實的內功、沒有內功）就挑第一件不相剋的（照 SHOP_ATTRIBUTES 的順序，
    每次挑同一件）。架上四件都不剋陰陽虛實，所以一定挑得到。"""
    if neigong is not None and neigong.attribute in SHOP_ATTRIBUTES:
        return neigong.attribute
    return next(a for a in SHOP_ATTRIBUTES if _match(a, neigong) >= 0)


def wanted(state: GameState, content: Content, neigong: MartialArt | None) -> str | None:
    """在鐵匠鋪防具頁最該按的那一顆（整季機器人與伺服器假人共用，裝備四欄設計第九節）：裝備庫裡有比身上好的就換上；再來架上那一件
    （_shop_pick）比身上的好就買（身上空著、或身上那件被內功剋）；再來耐久低於 REPAIR_AT 就修。比的是修好之後的減損（fresh_cut），
    身上那件跟架上一樣好就不買。不在鐵匠鋪或防具關著是 None。拆解不在這裡（機器人與假人不拆）。"""
    if not smith_here(state, content):
        return None
    p = state.player
    now = fresh_cut(p.armor, neigong, content)
    best = max(equipment.in_slot(p, "armor"), key=lambda a: (fresh_cut(a, neigong, content), a.id), default=None)
    if best is not None and fresh_cut(best, neigong, content) > now + 1e-9:
        return f"smith:wield:{best.id}"
    pick = _shop_pick(neigong)
    if fresh_cut(shop_item(pick), neigong, content) > now + 1e-9 and buy_problem(state, content, pick) is None:
        return f"{BUY}{pick}"
    if p.armor is not None and p.armor.edge < REPAIR_AT and repair_problem(state, content) is None:
        return REPAIR
    return None


# ---- 看得到（2.5）：修練頁每一列、角色卡那一行 ----

def pct(ratio: float) -> str:
    """減損寫成整數百分比（設計 2.5 的例子：8.1% 寫 8%）。"""
    return f"{ratio:.0%}"


def clashes(attribute: str, neigong: MartialArt | None) -> bool:
    """這個屬性跟身上的內功相剋（兩個方向都算，同 _match 的 −1）；沒有內功不算。整季機器人挑打造的配對時用（smithing.armor_plan）。"""
    return _match(attribute, neigong) < 0


def fit_note(item: Equipment, neigong: MartialArt | None) -> str:
    """對上內功那一句：同屬性、相剋各一句，其餘是空字串。"""
    m = _match(item.attribute, neigong)
    return MATCH_NOTE if m > 0 else CLASH_NOTE if m < 0 else ""


def _row(item: Equipment, neigong: MartialArt | None, content: Content, worn: bool = False) -> dict:
    return {
        "id": item.id, "name": item.name, "attribute": item.attribute, "tier": item.tier, "quality": item.quality,
        "grade": grade(item), "edge": item.edge, "wear_word": WEAR_WORD,  # 網頁照這個字寫「耐久度 N」（3.1 的字表，不在網頁寫死）
        "cut": pct(cut(item, neigong, content)), "fit": fit_note(item, neigong),
        "tempers": item.tempers, "temper_max": content.config.armor.temper_max,  # 網頁寫「淬煉 N/M」（防具打造）
        "recipe": recipe_text(content, item.recipe),  # 自己打的那一件寫配方（主料＋輔料），買的是 None
        "confirm": "" if worn or item.original else equipment.dismantle_confirm(content, item),  # 身上那件、原品（5.4）不能拆，沒有問句
        "keep": equipment.ORIGINAL_KEPT if item.original else "",
    }


def rows(state: GameState, content: Content, neigong: MartialArt | None) -> dict:
    """修練頁的防具那一段（skillview.gear_rows）：身上那件、裝備庫裡的防具。開關關著時 worn 是 None、rack 是空的。"""
    p = state.player
    if not equipment.on(content, "armor"):
        return {"worn": None, "rack": []}
    return {
        "worn": _row(p.armor, neigong, content, worn=True) if p.armor else None,
        "rack": [_row(a, neigong, content) for a in equipment.in_slot(p, "armor")],
    }


def card_line(state: GameState, content: Content, neigong: MartialArt | None) -> str:
    """本人卡上的「防具」那一行（2.5，待 joy 潤）：沒穿或開關關著是空字串。淬過的寫「・淬煉 N 次」（同兵器 weapons._describe）。"""
    item = state.player.armor
    if not equipment.on(content, "armor") or item is None:
        return ""
    note = fit_note(item, neigong)
    tempered = f"・淬煉 {item.tempers} 次" if item.tempers else ""  # 待 joy 潤
    line = (f"防具　【{item.name}】屬{item.attribute}・{grade(item)}{tempered}・{WEAR_WORD} {item.edge}，"
            f"一場少扣 {pct(cut(item, neigong, content))} 氣血")
    return line + (f"（{note}）" if note else "")


# ---- 打造的配方鍵與名字（四欄設計 4.7；打造隱藏配方設計 4.1、第九節）----

FORGE_PREFIX = "鎧|"  # 防具組合鍵的開頭：前綴就是欄位（兵器是「兵|」）；不用「甲|」（「甲:N」是防具的 id 開頭，3.1）
FORGE_WORDS = ("甲", "鎧", "袍", "衫")  # 防具的名字一定帶其中一個字（4.7）
# 一般組合最後接的字，照這一件的屬性（架上四件就是這個對法：鐵葉甲、軟皮甲、輕綃衫、厚氈袍）。待 joy 潤
FORGE_NOUNS = {"剛": "甲", "柔": "甲", "快": "衫", "虛": "衫", "慢": "袍", "陰": "袍", "陽": "鎧", "實": "鎧"}
WORD_MISSING = "名字看不出是防具"  # 待 joy 潤
WORD_CLASH = "名字像是兵器"  # 待 joy 潤
SHOP_CLASH = "跟鐵匠鋪架上的防具同名"  # 待 joy 潤


def recipe_key(main: str, aux: str) -> str:
    """防具的組合鍵（4.7）：「鎧|主料+輔料」。沒有種類；主輔不交換（同兵器 4.4）。"""
    return f"{FORGE_PREFIX}{main}+{aux}"


def recipe_parts(key: str | None) -> tuple[str, str] | None:
    """recipe_key 拆回（主料, 輔料）；不是防具欄的鍵（兵器的「兵|」、隱藏配方的「鑄|」、None）回 None。"""
    if not key or not key.startswith(FORGE_PREFIX):
        return None
    main, plus, aux = key[len(FORGE_PREFIX):].partition("+")
    return (main, aux) if plus and main and aux else None


def recipe_text(content: Content, key: str | None) -> str | None:
    """配方寫給玩家看（修練頁的裝備庫、鑄譜）：「精鐵砂＋驚羽」（主料在前）；不是自己打的（買的）是 None。"""
    parts = recipe_parts(key)
    if parts is None:
        return None
    name = lambda mid: content.materials[mid].name if mid in content.materials else mid  # noqa: E731
    return f"{name(parts[0])}＋{name(parts[1])}"


def noun_for(attribute: str) -> str:
    """一般組合的防具名最後那個字：照這一件的屬性查 FORGE_NOUNS；認不得的屬性接「甲」。"""
    return FORGE_NOUNS.get(attribute, "甲")


def word_problem(name: str) -> str | None:
    """防具的名字對不對（4.7；content.validate 驗對照表與隱藏配方的名字，第二批的神器定名也用）：要帶防具的字（甲、鎧、袍、衫之一）、
    不能有任何兵器的字（weapons.WEAPON_WORDS：「避刀甲」會讓人以為是刀）、不能跟架上的防具同名。None＝可以。"""
    if not any(word in name for word in FORGE_WORDS):
        return WORD_MISSING
    if any(word in name for words in weapons.WEAPON_WORDS.values() for word in words):
        return WORD_CLASH
    if name in SHOP_NAMES.values():
        return SHOP_CLASH
    return None


def table_name(content: Content, main: str, aux: str, attribute: str) -> str:
    """一般組合的防具名（打造隱藏配方設計 4.1、PM 2026-10-12 決定第 1 條；同 weapons.table_name）：字首照主料、中間字（craft_names.armor）
    照輔料在素材表的位置取，最後接照屬性挑的防具字（noun_for）。前兩個字只看組合；屬性照天機挑的組合（快＋慢）最後那個字跟著屬性換。"""
    order = list(content.materials)
    names = content.craft_names
    return names.prefixes[order.index(main)] + names.armor[order.index(aux)] + noun_for(attribute)
