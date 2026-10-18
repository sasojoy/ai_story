"""裝備四欄的共用部分（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第二、三節；裝備一）。

身上每欄一件（PlayerState.weapon、armor、mount〔坐騎，裝備二〕；寶物是裝備三），其餘放四欄共用的裝備庫（PlayerState.rack，
Config.weapons.rack_cap 格）。這裡只放不看欄位內容的部分：欄位表、各欄開著沒、裝備庫裡某一欄的、滿了沒、拿到新東西放哪、換上、
拆解的共用流程與問句、階品寫法、鐵匠鋪的字。要看欄位內容的（加成、減損、架上、每一列的字）在各欄自己的模組（weapons、armor），
它們反過來 import 這裡；這裡不 import weapons、armor，也不 import team、rules（team 會呼叫 weapons、armor，rules 會 import team）。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .four_tiers import TOP_COMMON
from .insights import PAIR_ATTRIBUTES
from .materials import by_tier
from .models import Content, Material
from .state import Equipment, GameState, PlayerState


@dataclass(frozen=True)
class Slot:
    """一欄（裝備四欄設計 3.1、3.2）。"""

    rules: str  # Config 上那一組設定的名字：它的 enabled 就是這一欄開著沒（2.6）
    warned: str  # PlayerState 上這一欄「磨損低了提醒過」的旗標；換一件、修好時重設；沒有磨損的欄位（寶物）是空字串
    prefix: str  # 新的一件的 id 開頭（「兵:N」「甲:N」，共用 PlayerState.weapon_serial）
    label: str  # 修練頁「裝備」那一段的名字
    put_on: str  # 拿到新東西、這一欄身上空著時那一句
    road_locked: bool = False  # 路上不能換（裝備四欄 2.3：坐騎的快慢出發時就算進抵達時刻，路上換了也不會變快）


# 武器、防具（裝備一）、坐騎（裝備二）、寶物（裝備三）。表外的欄位一律當關著：不列、不能換、不能拆（3.3）
SLOTS: dict[str, Slot] = {
    "weapon": Slot(rules="weapons", warned="edge_warned", prefix="兵", label="武器", put_on="你把【{name}】拿在手上。"),
    "armor": Slot(rules="armor", warned="armor_warned", prefix="甲", label="防具", put_on="你穿上了【{name}】。"),  # 待 joy 潤
    "mount": Slot(rules="mounts", warned="hunger_warned", prefix="騎", label="坐騎", put_on="你騎上了【{name}】。", road_locked=True),  # 待 joy 潤
    "treasure": Slot(rules="treasures", warned="", prefix="寶", label="寶物", put_on="你把【{name}】帶在身上。"),  # 待 joy 潤；隨時能換（2.3）
}
WEAR_WORDS = {"weapon": "鋒利度", "armor": "耐久度", "mount": "飽足度"}  # 待 joy 潤：Equipment.edge 在各欄叫什麼（3.1、2.5）；防具這一側都讀這裡（armor.WEAR_WORD），武器那一側的舊字這一批不動
WIELDABLE = ("weapon", "armor", "mount", "treasure")  # 修練頁「換上」收哪幾欄（2.3：武器、防具、寶物隨時能換〔寶物不設限制，企劃者 2026-10-11〕；坐騎路上不能換〔Slot.road_locked〕）
ROAD_LOCKED = "在路上不能換{label}。"  # 待 joy 潤
DISMANTLABLE = ("weapon", "armor")  # 拆得了的（4.8：坐騎、寶物沒有屬性，也不該拆成素材）

SMITH = "鐵匠鋪"
TOWN_TAG = "城鎮"
NOT_HERE = "這裡沒有鐵匠鋪"
SMITH_WHERE = "城鎮裡的鐵匠鋪買得到。"  # 待 joy 潤（FB-138）：修練頁「裝備」塊武器、防具空著時，每一行寫哪裡買得到
WHERE_HERE = "此地就有。"  # 待 joy 潤（FB-138）：人正站在那種地方（鐵匠鋪看是不是城鎮、馬市看有沒有馬市標籤）時，接在後面
RACK_FULL = "裝備庫滿了"  # 程式裡的 rack、rack_cap、rack_full 就是玩家看到的「裝備庫」（企劃者 2026-10-10 由「兵器架」改名）
NO_REPAIR_MATERIAL = "沒有一階素材"
STORED = "【{name}】放上了裝備庫。"
WIELD_MISSING = "裝備庫上沒有這一件。"  # 待 joy 潤（原本 weapons.wield 寫「這一把」：防具也走這一句，量詞跟 DISMANTLE_MISSING 一樣用「一件」）
WIELDED = "你換上了【{name}】。"  # Game.wield_weapon 照開頭「你換上了」寫修練紀錄
NOT_NOW = "（此刻無法這麼做。）"
TIER_WORDS = {1: "一階", 2: "二階", 3: "三階", 4: "四階"}
NAMED_MARK = "・名器"  # 待 joy 潤：照隱藏配方打出來的那一件，階品後面多這一段（打造隱藏配方設計 4.2）
DIVINE_MARK = "・神器"  # 待 joy 潤：神器原品，階品後面多這一段（打造隱藏配方設計 5.3）
COPY_MARK = "・仿品"  # 待 joy 潤：神器仿品
SIGNATURE_MARK = "・本命"  # 待 joy 潤：名將本命兵器，階品後面多這一段（打造第三批；同時也是原品，但寫這一段不寫「・神器」）
SIGNATURE_KEPT = "本命兵器不能拆"  # 待 joy 潤：本命兵器那一列的拆解鈕灰掉時寫的原因
SIGNATURE_KEPT_LINE = "這是名將的本命兵器，一季全江湖只有這一{unit}，拆不得。"  # 待 joy 潤：引擎收到拆本命兵器時回的那一句
DISMANTLE_PREFIX = "你拆解了"
DISMANTLE_MISSING = "裝備庫裡沒有這一件。"  # 待 joy 潤
DISMANTLE_LIST = 8  # 鐵匠鋪的選單上最多列幾件可拆的，其餘到修練頁的裝備庫拆
DISMANTLE_MORE = "還有 {n} 件，到修練頁的裝備庫拆"  # 待 joy 潤
WIELD_MORE = "還有 {n} 件，到修練頁的裝備庫換"  # 待 joy 潤：鐵匠鋪防具頁「換上」超過 DISMANTLE_LIST 件時那一行（FB-134）
DISMANTLE_ASK = "把【{name}】（{grade}{tempered}）拆成{material}×1？拆掉就沒了{lost}。"  # 待 joy 潤（FB-125：拆解先問一次；FB-133：淬過的寫幾次、一起沒了）
DISMANTLE_TEMPERED = "・淬煉 {n} 次"  # 待 joy 潤
DISMANTLE_LOST = "，淬過的 {n} 次也一起沒了"  # 待 joy 潤
DISMANTLE_YES = "拆掉"  # 待 joy 潤：確認層上那一顆
ORIGINAL_KEPT = "原品不能拆"  # 待 joy 潤：神器原品那一列的拆解鈕灰掉時寫的原因（打造隱藏配方設計 5.4）
ORIGINAL_KEPT_LINE = "這是神器的原品，一季全江湖只有這一{unit}，拆不得。"  # 待 joy 潤：引擎收到拆原品時回的那一句


def kept(item: Equipment) -> str:
    """拆不得的原因（修練頁那一列灰掉的拆解鈕、鐵匠鋪那一顆）：本命兵器、神器原品（打造隱藏配方設計 5.4）；其餘是空字串。"""
    if item.signature is not None:
        return SIGNATURE_KEPT
    return ORIGINAL_KEPT if item.original else ""


def on(content: Content, slot: str) -> bool:
    """這一欄開著沒（2.6：每欄自己的 enabled，不問第一季開關）；表外的欄位一律 False。"""
    entry = SLOTS.get(slot)
    return entry is not None and getattr(content.config, entry.rules).enabled


def worn(p: PlayerState, slot: str) -> Equipment | None:
    """身上這一欄那一件；表外的欄位是 None。"""
    return getattr(p, slot) if slot in SLOTS else None


def in_slot(p: PlayerState, slot: str) -> list[Equipment]:
    """裝備庫裡這一欄的（照放進去的先後）。3.3：每個讀裝備庫的地方都照欄位過濾，不要直接讀 p.rack。"""
    return [item for item in p.rack if item.slot == slot]


def in_town(state: GameState, content: Content) -> bool:
    """人不在路上、所在地點有「城鎮」標籤（有鐵匠鋪的地方，兵器設計 4.1）。"""
    if state.player.journey is not None:
        return False
    return TOWN_TAG in (content.locations[state.player.location].tags or [])


def smith_where(state: GameState, content: Content) -> str:
    """修練頁武器、防具那一段「哪裡買得到」（FB-138；網頁在身上什麼裝備都沒有時畫精簡的一塊）：鐵匠鋪在帶「城鎮」標籤的地點
    （地點資料讀內容，不寫死地名；內容裡一處城鎮都沒有就不寫）；人正站在城鎮（in_town）多接一句「此地就有」。"""
    if not any(TOWN_TAG in (loc.tags or []) for loc in content.locations.values()):
        return ""
    return SMITH_WHERE + (WHERE_HERE if in_town(state, content) else "")


def rack_full(state: GameState, content: Content, slot: str) -> bool:
    """這一欄身上有東西、裝備庫（四欄合算）也滿了，就放不下（2.2；這一欄空著的話新的直接穿上，用不到裝備庫）。"""
    return worn(state.player, slot) is not None and len(state.player.rack) >= content.config.weapons.rack_cap


def next_id(state: GameState, slot: str) -> str:
    """新的一件的 id（流水號 +1；四欄共用 weapon_serial，舊的「兵:N」不重編）。"""
    state.player.weapon_serial += 1
    return f"{SLOTS[slot].prefix}:{state.player.weapon_serial}"


def store(state: GameState, item: Equipment) -> str:
    """拿到一件（2.2）：這一欄身上空著就穿上（重設這一欄的提醒：穿上的是另一件），不然放進裝備庫（呼叫端先用 rack_full 擋）。"""
    p = state.player
    entry = SLOTS[item.slot]
    if worn(p, item.slot) is None:
        setattr(p, item.slot, item)
        if entry.warned:
            setattr(p, entry.warned, False)  # 寶物沒有磨損、沒有提醒旗標（warned 是空字串）
        return entry.put_on.format(name=item.name)
    p.rack.append(item)
    return STORED.format(name=item.name)


def _find(p: PlayerState, item_id: str, slots: tuple[str, ...]) -> Equipment | None:
    return next((item for item in p.rack if item.id == item_id and item.slot in slots), None)


def wield(state: GameState, content: Content, item_id: str, slots: tuple[str, ...]) -> list[str]:
    """換上（2.3）：裝備庫裡 slots 這幾欄的一件換到身上它自己那一欄，身上原本那件放回裝備庫（空著就直接穿上）；重設那一欄的提醒。
    不花體力；只有 road_locked 的欄位（坐騎）在路上不能換，其餘不看人在做什麼（寶物也是，2.3【定】）。先照 id 找、再看那一欄開著沒：找到了而那一欄關著、或 slots 裡一欄都沒開著，是 NOT_NOW；
    開著的欄位裡找不到是 WIELD_MISSING（表外的欄位也是找不到）。"""
    p = state.player
    chosen = _find(p, item_id, slots)
    if chosen is None:
        return [WIELD_MISSING if any(on(content, slot) for slot in slots) else NOT_NOW]
    if not on(content, chosen.slot):
        return [NOT_NOW]
    if SLOTS[chosen.slot].road_locked and p.journey is not None:
        return [ROAD_LOCKED.format(label=SLOTS[chosen.slot].label)]  # 坐騎（2.3）：閉關中照樣能換，只擋路上
    p.rack.remove(chosen)
    current = worn(p, chosen.slot)
    if current is not None:
        p.rack.append(current)
    setattr(p, chosen.slot, chosen)
    if SLOTS[chosen.slot].warned:
        setattr(p, SLOTS[chosen.slot].warned, False)  # 換上來的是另一件：磨損低了要有它自己的提醒（寶物沒有磨損）
    return [WIELDED.format(name=chosen.name)]


def grade(item: Equipment) -> str:
    """「一階下品」：階＋品質（FB-127：修練頁的裝備庫每列都要寫）；照隱藏配方打出來的再接一段（打造隱藏配方設計 4.2、5.3；只看存檔的欄位，
    不查內容）：本命兵器「・本命」、神器原品「・神器」、仿品「・仿品」、名器「・名器」。內容拿掉了那一條名器，加成照一般的算（named）、這一段照寫。"""
    mark = mark_word(item)
    return f"{tier_quality(item)}・{mark}" if mark else tier_quality(item)


def tier_quality(item: Equipment) -> str:
    """「一階下品」：只有階與品質（grade 去掉後面那一段）。"""
    return f"{TIER_WORDS.get(item.tier, '')}{item.quality}"


def mark_word(item: Equipment) -> str:
    """grade 後面那一段的字（「本命」「神器」「仿品」「名器」），一般的是空字串。開爐的結果句把它寫在名字前面（FB-148）。"""
    if item.signature is not None:
        mark = SIGNATURE_MARK
    elif item.original:
        mark = DIVINE_MARK
    elif item.copy_of is not None:
        mark = COPY_MARK
    elif item.secret is not None:
        mark = NAMED_MARK
    else:
        mark = ""
    return mark.removeprefix("・")


def named(content: Content, item: Equipment | None) -> bool:
    """名器（打造隱藏配方設計 4.2）：照隱藏配方打出來的（secret），而且內容裡還有那一條（拿掉了加成照一般的算）。仿品、原品不算（它們有自己的基本值，4.3）。"""
    return (item is not None and item.secret is not None and item.secret in content.forge_secrets
            and item.copy_of is None and not item.original)


def grade_line(item: Equipment) -> str:
    """鐵匠鋪「換上」「拆解」鈕上用來分辨同一個配方好幾把的那一段：「一階中品」，淬過的再接「・淬煉 2」（終審 F2）。"""
    return grade(item) + (f"・淬煉 {item.tempers}" if item.tempers else "")  # 待 joy 潤


def dismantle_material(content: Content, item: Equipment) -> Material:
    """拆一件拿到的素材（兵器設計 4.7.1、裝備四欄 4.8）：同階；屬性剛柔快慢直接對，陰陽虛實是兩個屬性合出來的
    （insights.PAIR_ATTRIBUTES），從兩個來源裡挑一個，由 id 的 sha256 決定（同一件永遠拆出同一種；演算法不能改，不然舊兵器拆出來的會變）。
    該階該屬性沒有素材時 by_tier 退回同階的全部。主料四階的一件拆出三階（正式季整合 12.3 第 37 條：擋住一直重打洗屬性）。"""
    attribute = item.attribute
    sources = next((sorted(pair) for pair, result in PAIR_ATTRIBUTES.items() if result == attribute), None)
    if sources is not None:
        attribute = sources[hashlib.sha256(item.id.encode("utf-8")).digest()[0] % 2]
    tier = min(item.tier, TOP_COMMON)
    return (by_tier(content, tier, attribute) or by_tier(content, 1, attribute) or list(content.materials.values()))[0]


def dismantle_order(item: Equipment) -> tuple[int, int, str]:
    """可拆的排前面的是磨損最多的，再來階數低的，最後照 id 求穩定（4.7.1）。"""
    return (item.edge, item.tier, item.id)


WEAPON_UNITS = {"拳腳": "副"}  # 兵器的量詞（FB-133、FB-160）：拳套論副，其他兵器論把。待 joy 潤


def unit_for(slot: str, kind: str = "") -> str:
    """量詞照欄位（FB-146：防具神器前面寫「一件」、後面寫「一把」）：防具、寶物一件，坐騎一匹，兵器照種類（拳套一副、其他一把）。"""
    if slot == "weapon":
        return WEAPON_UNITS.get(kind, "把")
    return "匹" if slot == "mount" else "件"


def dismantle_confirm(content: Content, item: Equipment) -> str:
    """拆解之前問的那一句（FB-125，企劃者 2026-10-10 第二批附帶決定 a）：修練頁與鐵匠鋪同一句，寫明拆出什麼。"""
    n = item.tempers
    return DISMANTLE_ASK.format(name=item.name, grade=grade(item), material=dismantle_material(content, item).name,
                                tempered=DISMANTLE_TEMPERED.format(n=n) if n else "", lost=DISMANTLE_LOST.format(n=n) if n else "")


def dismantle(state: GameState, content: Content, item_id: str, slots: tuple[str, ...]) -> list[str]:
    """拆解（兵器設計 4.7.1、裝備四欄 4.8）：裝備庫裡 slots 這幾欄的一件拆掉，換一個素材。不花銀兩、不花體力、不必在鐵匠鋪；
    網頁先問一次（FB-125），引擎收到就拆。坐騎、寶物不在 DISMANTLABLE 裡，一開頭就濾掉（寶物的 attribute 是空字串，
    丟進 dismantle_material 會硬拆出東西）。身上那件不在裝備庫裡，找不到。拒絕的順序同 wield。"""
    p = state.player
    slots = tuple(slot for slot in slots if slot in DISMANTLABLE)
    chosen = _find(p, item_id, slots)
    if chosen is None:
        return [DISMANTLE_MISSING if any(on(content, slot) for slot in slots) else NOT_NOW]
    if not on(content, chosen.slot):
        return [NOT_NOW]
    if chosen.signature is not None:
        return [SIGNATURE_KEPT_LINE.format(unit=unit_for(chosen.slot, chosen.kind))]  # 本命兵器：一季全服只有一把，拆了就沒了、上不了神器譜
    if chosen.original:
        return [ORIGINAL_KEPT_LINE.format(unit=unit_for(chosen.slot, chosen.kind))]  # 5.4：一季全服只有一把，拆了就沒了、上不了神器譜；仿品照一般的拆
    material = dismantle_material(content, chosen)
    p.rack.remove(chosen)
    p.materials[material.id] = p.materials.get(material.id, 0) + 1
    return [f"{DISMANTLE_PREFIX}【{chosen.name}】，拆出了{material.name}×1。"]


def repair_material(state: GameState, content: Content) -> str | None:
    """修要用的一階素材（武器、防具一樣）：背包裡數量最多的那一種（同數照 id），沒有是 None。"""
    held = [(n, mid) for mid, n in state.player.materials.items() if n > 0 and mid in content.materials and content.materials[mid].tier == 1]
    return max(held, key=lambda pair: (pair[0], pair[1]))[1] if held else None


# ---- 鐵匠鋪的兩頁（裝備四欄設計 4.6）：兵器、防具；兩欄都開著時預設兵器頁，最後「離開」前一顆切到另一頁 ----

SMITH_PAGES = ("weapon", "armor")  # 照這個順序：進門停在第一個開著的
PAGE_LABELS = {"weapon": "轉去看兵器", "armor": "轉去看防具"}  # 待 joy 潤：切頁那一顆
# 素材那一頁（素材與經濟設計第四、五節：收購、升階；Config.economy 的 sell／upgrade 有一樣開著才有，Game._trade_on）。不是裝備的一欄，
# 所以不在 SMITH_PAGES 裡：page() 在這一頁時照舊回兵器、防具裡的第一頁（換上、拆解只看那兩欄）
MATERIAL_PAGE = "material"
MATERIAL_LABEL = "素材買賣…"  # 待 joy 潤：兵器、防具頁進素材頁那一顆


def smith_open(state: GameState, content: Content) -> bool:
    """鐵匠鋪開不開門：武器或防具開著、人在城鎮。進門（act:smith）、收選單（存檔修補、同步）看這個；能不能買修打某一欄的東西
    另看那一欄自己的 smith_here（weapons.smith_here、armor.smith_here）。"""
    return any(on(content, slot) for slot in SMITH_PAGES) and in_town(state, content)


def first_page(content: Content) -> str:
    """走進鐵匠鋪停在哪一頁：第一個開著的（兩欄都開著是兵器頁）。"""
    return next((slot for slot in SMITH_PAGES if on(content, slot)), SMITH_PAGES[0])


def page(p: PlayerState, content: Content) -> str:
    """鐵匠鋪現在停在哪一頁：存著的那一頁還開著就是它，不然退回 first_page（開關中途關了、舊存檔）。"""
    return p.smith_page if p.smith_page in SMITH_PAGES and on(content, p.smith_page) else first_page(content)


def other_page(p: PlayerState, content: Content) -> str | None:
    """切頁那一顆要切到哪一頁：另一頁也開著才有（只開一欄時不畫切頁鈕）。"""
    here = page(p, content)
    return next((slot for slot in SMITH_PAGES if slot != here and on(content, slot)), None)


def open_smith(p: PlayerState, content: Content) -> None:
    """走進鐵匠鋪（act:smith）：打開選單、打造的單子從頭開始（兵器第二批 Review Focus 4）、停在第一個開著的那一頁。"""
    p.picking_smith, p.smith_draft, p.smith_page = True, None, first_page(content)


def close_smith(p: PlayerState) -> None:
    """收起鐵匠鋪：選單、打造的單子、停在哪一頁、店面上掌櫃那一句（店面獨立介面設計 1.4）一起清。凡是把 picking_smith 設成 False 的地方
    都走這裡（離開、存檔修補、同步時人不在城鎮、出發），存檔裡不留舊的單子或舊的頁（裝備四欄設計 3.2）。"""
    p.picking_smith, p.smith_draft, p.smith_page = False, None, SMITH_PAGES[0]
    p.shop_line, p.shop_clue, p.shop_hold = "", "", ""
