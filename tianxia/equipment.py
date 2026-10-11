"""裝備四欄的共用部分（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第二、三節；裝備一）。

身上每欄一件（PlayerState.weapon、armor；坐騎、寶物等裝備二、三），其餘放四欄共用的裝備庫（PlayerState.rack，
Config.weapons.rack_cap 格）。這裡只放不看欄位內容的部分：欄位表、各欄開著沒、裝備庫裡某一欄的、滿了沒、拿到新東西放哪、換上、
拆解的共用流程與問句、階品寫法、鐵匠鋪的字。要看欄位內容的（加成、減損、架上、每一列的字）在各欄自己的模組（weapons、armor），
它們反過來 import 這裡；這裡不 import weapons、armor，也不 import team、rules（team 會呼叫 weapons、armor，rules 會 import team）。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .insights import PAIR_ATTRIBUTES
from .materials import by_tier
from .models import Content, Material
from .state import Equipment, GameState, PlayerState


@dataclass(frozen=True)
class Slot:
    """一欄（裝備四欄設計 3.1、3.2）。"""

    rules: str  # Config 上那一組設定的名字：它的 enabled 就是這一欄開著沒（2.6）
    warned: str  # PlayerState 上這一欄「磨損低了提醒過」的旗標；換一件、修好時重設
    prefix: str  # 新的一件的 id 開頭（「兵:N」「甲:N」，共用 PlayerState.weapon_serial）
    label: str  # 修練頁「裝備」那一段的名字
    put_on: str  # 拿到新東西、這一欄身上空著時那一句


# 這一批只有武器、防具；坐騎（騎）、寶物（寶）在裝備二、三各加一列（PlayerState 同時加那一欄）。表外的欄位（裝備庫裡混進來的
# 坐騎、寶物）一律當關著：不列、不能換、不能拆（3.3）
SLOTS: dict[str, Slot] = {
    "weapon": Slot(rules="weapons", warned="edge_warned", prefix="兵", label="武器", put_on="你把【{name}】拿在手上。"),
    "armor": Slot(rules="armor", warned="armor_warned", prefix="甲", label="防具", put_on="你穿上了【{name}】。"),  # 待 joy 潤
}
WEAR_WORDS = {"weapon": "鋒利度", "armor": "耐久度", "mount": "飽足度"}  # 待 joy 潤：Equipment.edge 在各欄叫什麼（3.1、2.5）；防具這一側都讀這裡（armor.WEAR_WORD），武器那一側的舊字這一批不動
WIELDABLE = ("weapon", "armor")  # 修練頁「換上」收哪幾欄（2.3：武器、防具隨時能換；寶物、坐騎的限制等各自那一批）
DISMANTLABLE = ("weapon", "armor")  # 拆得了的（4.8：坐騎、寶物沒有屬性，也不該拆成素材）

SMITH = "鐵匠鋪"
TOWN_TAG = "城鎮"
NOT_HERE = "這裡沒有鐵匠鋪"
RACK_FULL = "裝備庫滿了"  # 程式裡的 rack、rack_cap、rack_full 就是玩家看到的「裝備庫」（企劃者 2026-10-10 由「兵器架」改名）
NO_REPAIR_MATERIAL = "沒有一階素材"
STORED = "【{name}】放上了裝備庫。"
WIELD_MISSING = "裝備庫上沒有這一件。"  # 待 joy 潤（原本 weapons.wield 寫「這一把」：防具也走這一句，量詞跟 DISMANTLE_MISSING 一樣用「一件」）
WIELDED = "你換上了【{name}】。"  # Game.wield_weapon 照開頭「你換上了」寫修練紀錄
NOT_NOW = "（此刻無法這麼做。）"
TIER_WORDS = {1: "一階", 2: "二階", 3: "三階"}
DISMANTLE_PREFIX = "你拆解了"
DISMANTLE_MISSING = "裝備庫裡沒有這一件。"  # 待 joy 潤
DISMANTLE_LIST = 8  # 鐵匠鋪的選單上最多列幾件可拆的，其餘到修練頁的裝備庫拆
DISMANTLE_MORE = "還有 {n} 件，到修練頁的裝備庫拆"  # 待 joy 潤
DISMANTLE_ASK = "把【{name}】（{grade}）拆成{material}×1？拆掉就沒了。"  # 待 joy 潤（FB-125：拆解先問一次）
DISMANTLE_YES = "拆掉"  # 待 joy 潤：確認層上那一顆


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
        setattr(p, entry.warned, False)
        return entry.put_on.format(name=item.name)
    p.rack.append(item)
    return STORED.format(name=item.name)


def _find(p: PlayerState, item_id: str, slots: tuple[str, ...]) -> Equipment | None:
    return next((item for item in p.rack if item.id == item_id and item.slot in slots), None)


def wield(state: GameState, content: Content, item_id: str, slots: tuple[str, ...]) -> list[str]:
    """換上（2.3）：裝備庫裡 slots 這幾欄的一件換到身上它自己那一欄，身上原本那件放回裝備庫（空著就直接穿上）；重設那一欄的提醒。
    不花體力、不看人在做什麼。先照 id 找、再看那一欄開著沒：找到了而那一欄關著、或 slots 裡一欄都沒開著，是 NOT_NOW；
    開著的欄位裡找不到是 WIELD_MISSING（表外的坐騎、寶物也是找不到）。"""
    p = state.player
    chosen = _find(p, item_id, slots)
    if chosen is None:
        return [WIELD_MISSING if any(on(content, slot) for slot in slots) else NOT_NOW]
    if not on(content, chosen.slot):
        return [NOT_NOW]
    p.rack.remove(chosen)
    current = worn(p, chosen.slot)
    if current is not None:
        p.rack.append(current)
    setattr(p, chosen.slot, chosen)
    setattr(p, SLOTS[chosen.slot].warned, False)  # 換上來的是另一件：磨損低了要有它自己的提醒
    return [WIELDED.format(name=chosen.name)]


def grade(item: Equipment) -> str:
    """「一階下品」：階＋品質（FB-127：修練頁的裝備庫每列都要寫）。"""
    return f"{TIER_WORDS.get(item.tier, '')}{item.quality}"


def grade_line(item: Equipment) -> str:
    """鐵匠鋪「換上」「拆解」鈕上用來分辨同一個配方好幾把的那一段：「一階中品」，淬過的再接「・淬煉 2」（終審 F2）。"""
    return grade(item) + (f"・淬煉 {item.tempers}" if item.tempers else "")  # 待 joy 潤


def dismantle_material(content: Content, item: Equipment) -> Material:
    """拆一件拿到的素材（兵器設計 4.7.1、裝備四欄 4.8）：同階；屬性剛柔快慢直接對，陰陽虛實是兩個屬性合出來的
    （insights.PAIR_ATTRIBUTES），從兩個來源裡挑一個，由 id 的 sha256 決定（同一件永遠拆出同一種；演算法不能改，不然舊兵器拆出來的會變）。
    該階該屬性沒有素材時 by_tier 退回同階的全部。"""
    attribute = item.attribute
    sources = next((sorted(pair) for pair, result in PAIR_ATTRIBUTES.items() if result == attribute), None)
    if sources is not None:
        attribute = sources[hashlib.sha256(item.id.encode("utf-8")).digest()[0] % 2]
    return (by_tier(content, item.tier, attribute) or by_tier(content, 1, attribute) or list(content.materials.values()))[0]


def dismantle_order(item: Equipment) -> tuple[int, int, str]:
    """可拆的排前面的是磨損最多的，再來階數低的，最後照 id 求穩定（4.7.1）。"""
    return (item.edge, item.tier, item.id)


def dismantle_confirm(content: Content, item: Equipment) -> str:
    """拆解之前問的那一句（FB-125，企劃者 2026-10-10 第二批附帶決定 a）：修練頁與鐵匠鋪同一句，寫明拆出什麼。"""
    return DISMANTLE_ASK.format(name=item.name, grade=grade(item), material=dismantle_material(content, item).name)


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
    material = dismantle_material(content, chosen)
    p.rack.remove(chosen)
    p.materials[material.id] = p.materials.get(material.id, 0) + 1
    return [f"{DISMANTLE_PREFIX}【{chosen.name}】，拆出了{material.name}×1。"]


def repair_material(state: GameState, content: Content) -> str | None:
    """修要用的一階素材（武器、防具一樣）：背包裡數量最多的那一種（同數照 id），沒有是 None。"""
    held = [(n, mid) for mid, n in state.player.materials.items() if n > 0 and mid in content.materials and content.materials[mid].tier == 1]
    return max(held, key=lambda pair: (pair[0], pair[1]))[1] if held else None
