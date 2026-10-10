"""兵器（docs/superpowers/specs/2026-10-09-兵器-design.md）。

第一批（拿著就有用）：武學的兵器種類、身上那把的加成與鋒利度、鐵匠鋪的買、修、換、打贏掉落、角色卡那一行。
這個模組只 import models、state、martial_arts、world_state；team 反過來呼叫它（player_boost、_styled_fighters），
所以這裡不 import team——要武學本體的地方由呼叫端傳進來。
"""
from __future__ import annotations

import hashlib
import random

from .insights import PAIR_ATTRIBUTES
from .martial_arts import MartialArt, counters
from .materials import by_tier
from .models import WEAPON_KINDS, Content, Material
from .state import GameState, Weapon
from .world_state import WorldStateStore


def art_weapon(art_id: str | None, content: Content, world: WorldStateStore) -> str | None:
    """這門武學配哪一種兵器（2.3）：內容裡的照 SkillDef.weapon；全服登記的合成武學照底（武學＋意境）一代一代往上找，
    武學＋武學從兩門來源挑一個（照 art id 的 sha256，同一門每次都一樣）；舊的自創武學推不出來是 None。內功一律 None。"""
    seen: set[str] = set()
    while art_id and art_id not in seen:
        seen.add(art_id)
        if art_id in content.skills:
            return content.skills[art_id].weapon
        art = world.get_skill(art_id)
        if art is None or art.kind != "武學":
            return None
        if art.base:
            art_id = art.base
            continue
        if art.parents:
            kinds = [art_weapon(p, content, world) for p in sorted(art.parents)]
            kinds = [k for k in kinds if k]
            if not kinds:
                return None
            return kinds[hashlib.sha256(art.id.encode("utf-8")).digest()[0] % len(kinds)]
        return None
    return None


def usable(weapon: Weapon | None, art: MartialArt | None, content: Content, world: WorldStateStore) -> bool:
    """這把兵器配不配得上身上這門武學（2.3）：開關開著、兩樣都有、種類一樣。"""
    return (
        content.config.weapons.enabled and weapon is not None and art is not None
        and art_weapon(art.id, content, world) == weapon.kind
    )


def edge_factor(content: Content, weapon: Weapon) -> float:
    """鋒利度係數（3.4）：全鈍剩 edge_floor，滿的是 1。"""
    floor = content.config.weapons.edge_floor
    return floor + (1 - floor) * max(0, min(100, weapon.edge)) / 100


def bonus(weapon: Weapon | None, art: MartialArt | None, content: Content, world: WorldStateStore) -> float:
    """這把兵器現在給幾成威力（3.1～3.4）：配不上是 0；（階＋品質＋淬煉＋屬性搭配）夾在 0 以上，再乘鋒利度係數。
    每次現算、不快取：換了武學、修了、鈍了，下一場就照新的算。"""
    if not usable(weapon, art, content, world):
        return 0.0
    rule = content.config.weapons
    base = rule.tier_bonus.get(str(weapon.tier), 0.0) + rule.quality_bonus.get(weapon.quality, 0.0)
    base += rule.temper_step * weapon.tempers
    if weapon.attribute == art.attribute:
        base += rule.match
    elif counters(weapon.attribute, art.attribute) or counters(art.attribute, weapon.attribute):
        base -= rule.match
    return max(0.0, base) * edge_factor(content, weapon)


def style_factor(weapon: Weapon | None, art: MartialArt | None, content: Content, world: WorldStateStore, style) -> float:
    """一門打不遍（3.3）：兵器屬性落在大場面對手怕的那一路 ×(1＋style_soft)、最會對付的那一路 ×(1－style_hard)。
    配不上的兵器、不是大場面（style 是 None）都是 1。"""
    if style is None or not usable(weapon, art, content, world):
        return 1.0
    rule = content.config.weapons
    if weapon.attribute == style.soft:
        return 1 + rule.style_soft
    if weapon.attribute == style.hard:
        return 1 - rule.style_hard
    return 1.0


EDGE_WARNING = "你的{name}刀口鈍了，找間鐵匠鋪修一修。"  # 待 joy 潤


def wear(state: GameState, content: Content, tier: str) -> list[str]:
    """打完一場，身上那把扣鋒利度（3.4，照結果）；第一次鈍到 edge_warn 以下回一句提醒（只一次，修好才重設）。
    劇情戰與全服決戰不呼叫這裡（engine._file_battle 擋劇情戰；決戰不走 _file_battle）。"""
    rule, p = content.config.weapons, state.player
    if not rule.enabled or p.weapon is None:
        return []
    p.weapon.edge = max(0, p.weapon.edge - rule.wear.get(tier, 0))
    if p.weapon.edge < rule.edge_warn and not p.edge_warned:
        p.edge_warned = True
        return [EDGE_WARNING.format(name=p.weapon.name)]
    return []


# ---- 鐵匠鋪（4.1～4.7）：買、修、換 ----

SMITH = "鐵匠鋪"
TOWN_TAG = "城鎮"
NOUNS = {"劍": "劍", "刀": "刀", "槍": "槍", "棍": "棍", "弓弩": "弩", "拳腳": "拳套"}
ATTR_WORDS = {"陰": "寒鐵", "陽": "赤銅", "剛": "厚背", "柔": "軟鋼", "快": "輕鋒", "慢": "沉鐵", "虛": "花紋", "實": "重鐵"}  # 待 joy 潤
NO_REPAIR_MATERIAL = "沒有一階素材"
RACK_FULL = "裝備庫滿了"  # 程式裡的 rack、rack_cap、rack_full 就是玩家看到的「裝備庫」（企劃者 2026-10-10 由「兵器架」改名）
NOT_HERE = "這裡沒有鐵匠鋪"
FITS_MARK = "・配得上你的武學"  # 待 joy 潤：鐵匠鋪的「買」鈕上，種類對得上身上那門武學的那一把


def shop_name(kind: str, attribute: str) -> str:
    """架上與掉落的兵器名（4.5、4.8）：屬性字＋兵器字，例「厚背刀」「輕鋒弩」。不叫模型。"""
    return f"{ATTR_WORDS[attribute]}{NOUNS[kind]}"


def smith_here(state: GameState, content: Content) -> bool:
    """這裡有沒有鐵匠鋪（4.1）：開關開著、人不在路上、所在地點有「城鎮」標籤。"""
    if not content.config.weapons.enabled or state.player.journey is not None:
        return False
    return TOWN_TAG in (content.locations[state.player.location].tags or [])


def _local_attribute(state: GameState, content: Content) -> str:
    """當地鐵匠打的屬性：Location.materials（路邊採集出的素材）第一樣的屬性，沒寫就是剛。
    內容裡寫的是素材 id（「man_1」），查素材的屬性；直接寫屬性字（測試內容）也認；認不得的略過。"""
    for entry in content.locations[state.player.location].materials or []:
        material = content.materials.get(entry)
        attribute = material.attribute if material is not None else entry
        if attribute in ATTR_WORDS:
            return attribute
    return "剛"


def stock(state: GameState, content: Content) -> list[Weapon]:
    """架上擺的（4.5）：六種各一把一階下品，屬性照當地。還沒買，id 是「架:種類」。"""
    attribute = _local_attribute(state, content)
    return [
        Weapon(id=f"架:{kind}", name=shop_name(kind, attribute), kind=kind, attribute=attribute, tier=1, quality="下品")
        for kind in WEAPON_KINDS
    ]


def new_weapon(state: GameState, *, name: str, kind: str, attribute: str, tier: int, quality: str) -> Weapon:
    state.player.weapon_serial += 1
    return Weapon(id=f"兵:{state.player.weapon_serial}", name=name, kind=kind, attribute=attribute, tier=tier, quality=quality)


def rack_full(state: GameState, content: Content) -> bool:
    """手上有一把、架上也滿了就放不下（手上空著的話新的直接拿在手上，用不到架子）。"""
    return state.player.weapon is not None and len(state.player.rack) >= content.config.weapons.rack_cap


def store(state: GameState, content: Content, weapon: Weapon) -> str:
    """拿到一把：手上空著就拿在手上，不然放上裝備庫（呼叫端先用 rack_full 擋）。拿在手上的是另一把，鈍了要有它自己的提醒。"""
    p = state.player
    if p.weapon is None:
        p.weapon, p.edge_warned = weapon, False
        return f"你把【{weapon.name}】拿在手上。"
    p.rack.append(weapon)
    return f"【{weapon.name}】放上了裝備庫。"


DROP_PREFIX = "撿到一把"
DROP_LINE = DROP_PREFIX + "【{name}】"
GAIN_LINE = "兵器【{name}】"  # 戰鬥卡片「得失」那一格（素材寫「精鐵砂 ×1」，兵器寫「兵器【厚背刀】」）


def drop(state: GameState, content: Content, rng: random.Random) -> tuple[Weapon | None, list[str]]:
    """打贏遊歷或野怪的掉落（4.8）：drop_chance 掉一把一階下品，種類隨機、屬性照當地。架子滿了不掉（不擲骰）。
    回（掉出來的兵器, 訊息）；沒掉是（None, []）。"""
    rule = content.config.weapons
    if not rule.enabled or rack_full(state, content) or rng.random() >= rule.drop_chance:
        return None, []
    kind = rng.choice(WEAPON_KINDS)
    attribute = _local_attribute(state, content)
    weapon = new_weapon(state, name=shop_name(kind, attribute), kind=kind, attribute=attribute, tier=1, quality="下品")
    return weapon, [DROP_LINE.format(name=weapon.name), store(state, content, weapon)]


def buy_problem(state: GameState, content: Content, kind: str) -> str | None:
    if not smith_here(state, content):
        return NOT_HERE  # 鐵匠鋪的選單關了、人走了：引擎層自己也再驗一次
    if kind not in WEAPON_KINDS:
        return "沒有這種兵器"
    if rack_full(state, content):
        return RACK_FULL
    short = content.config.weapons.shop_price - state.player.stats.get("silver", 0)
    return f"還差 {short} 兩" if short > 0 else None


def buy(state: GameState, content: Content, kind: str) -> list[str]:
    problem = buy_problem(state, content, kind)
    if problem is not None:
        return [f"（{problem}。）"]
    item = next(w for w in stock(state, content) if w.kind == kind)
    price = content.config.weapons.shop_price
    state.player.stats["silver"] -= price
    weapon = new_weapon(state, name=item.name, kind=kind, attribute=item.attribute, tier=1, quality="下品")
    return [f"你花 {price} 兩買下一把【{weapon.name}】。", store(state, content, weapon)]


def repair_material(state: GameState, content: Content) -> str | None:
    """修要用的一階素材：背包裡數量最多的那一種（同數照 id），沒有是 None。"""
    held = [(n, mid) for mid, n in state.player.materials.items() if n > 0 and mid in content.materials and content.materials[mid].tier == 1]
    return max(held, key=lambda pair: (pair[0], pair[1]))[1] if held else None


def repair_problem(state: GameState, content: Content) -> str | None:
    p, rule = state.player, content.config.weapons
    if not smith_here(state, content):
        return NOT_HERE
    if p.weapon is None:
        return "手上沒有兵器"
    if p.weapon.edge >= 100:
        return "刀口還利"
    if repair_material(state, content) is None:
        return NO_REPAIR_MATERIAL
    short = rule.repair_silver - p.stats.get("silver", 0)
    return f"還差 {short} 兩" if short > 0 else None


def repair(state: GameState, content: Content) -> list[str]:
    """修（4.7）：一個一階素材（屬性不限）＋工錢，鋒利度回滿。"""
    problem = repair_problem(state, content)
    if problem is not None:
        return [f"（{problem}。）"]
    p, rule = state.player, content.config.weapons
    material = repair_material(state, content)
    p.materials[material] -= 1
    if not p.materials[material]:
        del p.materials[material]
    p.stats["silver"] -= rule.repair_silver
    p.weapon.edge, p.edge_warned = 100, False
    return [f"鐵匠拿{content.materials[material].name}把【{p.weapon.name}】重新磨利了（銀兩 -{rule.repair_silver}）。"]


def wield(state: GameState, content: Content, weapon_id: str) -> list[str]:
    """換兵器（2.2）：裝備庫上那一把換到手上，手上那把放回架上（手上空著就直接拿下來）。不花體力。"""
    if not content.config.weapons.enabled:
        return ["（此刻無法這麼做。）"]
    p = state.player
    chosen = next((w for w in p.rack if w.id == weapon_id), None)
    if chosen is None:
        return ["裝備庫上沒有這一把。"]
    p.rack.remove(chosen)
    if p.weapon is not None:
        p.rack.append(p.weapon)
    p.weapon, p.edge_warned = chosen, False  # 換上來的是另一把：鈍了要有它自己的提醒
    return [f"你換上了【{chosen.name}】。"]


DISMANTLE_PREFIX = "你拆解了"
DISMANTLE_MISSING = "裝備庫裡沒有這一件。"  # 待 joy 潤
DISMANTLE_LIST = 8  # 鐵匠鋪的選單上最多列幾把可拆的，其餘到修練頁的裝備庫拆
DISMANTLE_MORE = "還有 {n} 件，到修練頁的裝備庫拆"  # 待 joy 潤


def dismantle_material(content: Content, weapon: Weapon) -> Material:
    """拆一把兵器拿到的素材（兵器設計 4.7.1）：同階；屬性剛柔快慢直接對，陰陽虛實是兩個屬性合出來的（insights.PAIR_ATTRIBUTES），
    從兩個來源裡挑一個，由兵器 id 的 sha256 決定（同一把永遠拆出同一種）。該階該屬性沒有素材時 by_tier 退回同階的全部。"""
    attribute = weapon.attribute
    sources = next((sorted(pair) for pair, result in PAIR_ATTRIBUTES.items() if result == attribute), None)
    if sources is not None:
        attribute = sources[hashlib.sha256(weapon.id.encode("utf-8")).digest()[0] % 2]
    return (by_tier(content, weapon.tier, attribute) or by_tier(content, 1, attribute) or list(content.materials.values()))[0]


def dismantle_order(weapon: Weapon) -> tuple[int, int, str]:
    """可拆的排前面的是刀口最鈍的，再來階數低的，最後照 id 求穩定（4.7.1）。"""
    return (weapon.edge, weapon.tier, weapon.id)


def dismantle(state: GameState, content: Content, weapon_id: str) -> list[str]:
    """拆解（兵器設計 4.7.1）：裝備庫裡的一把拆掉，換一個素材（dismantle_material）。不花銀兩、不花體力、不必在鐵匠鋪，也不問第二次。
    手上那把不能拆（先換下來）；開關關著或裝備庫沒這一把，什麼都不動。"""
    if not content.config.weapons.enabled:
        return ["（此刻無法這麼做。）"]
    p = state.player
    chosen = next((w for w in p.rack if w.id == weapon_id), None)
    if chosen is None:
        return [DISMANTLE_MISSING]
    material = dismantle_material(content, chosen)
    p.rack.remove(chosen)
    p.materials[material.id] = p.materials.get(material.id, 0) + 1
    return [f"{DISMANTLE_PREFIX}【{chosen.name}】，拆出了{material.name}×1。"]


REPAIR_AT = 50  # 機器人與假人鈍到這裡以下才修


def wanted(state: GameState, content: Content, world: WorldStateStore, art: MartialArt | None) -> str | None:
    """在鐵匠鋪最該按的那一顆（整季機器人與伺服器假人共用）：先把裝備庫裡配得上的換到手上，再買一把配得上的，再修配得上的那把。"""
    if not smith_here(state, content) or art is None:
        return None
    p = state.player
    if not usable(p.weapon, art, content, world):
        fit = next((w for w in p.rack if usable(w, art, content, world)), None)
        if fit is not None:
            return f"smith:wield:{fit.id}"
        kind = art_weapon(art.id, content, world)
        if kind and buy_problem(state, content, kind) is None:
            return f"smith:buy:{kind}"
    if usable(p.weapon, art, content, world) and p.weapon.edge < REPAIR_AT and repair_problem(state, content) is None:
        return "smith:repair"
    return None


TIER_WORDS = {1: "一階", 2: "二階", 3: "三階"}


def _pct(ratio: float) -> str:
    """跟 skillview._pct 同一種寫法：帶正負號、最多一位小數、整數不寫「.0」。"""
    return f"{ratio:+.1%}".replace(".0%", "%")


def _describe(w: Weapon) -> str:
    return f"【{w.name}】{w.kind}・屬{w.attribute}・{TIER_WORDS.get(w.tier, '')}{w.quality}・鋒利度 {w.edge}"


def _mismatch(w: Weapon, art: MartialArt | None, content: Content, world: WorldStateStore) -> str:
    """配不上的那一句（待 joy 潤）：拳腳、弓弩寫成「拳腳法」「弓弩法」不通順，各自另寫。"""
    mine = art_weapon(art.id, content, world) if art is not None else None
    if not mine:
        return "你身上沒有用得上兵器的武學"
    if mine == "拳腳":
        return f"這把{w.kind}用不上你的拳腳功夫"
    if mine == "弓弩":
        return f"這把{w.kind}用不上你的弓弩上的功夫"
    return f"這把{w.kind}用不上你的{mine}法"


def card_line(state: GameState, content: Content, world: WorldStateStore, art: MartialArt | None) -> str:
    """本人卡上的「兵器」那一行（3.6）：空手或開關關著是空字串。"""
    w = state.player.weapon
    if not content.config.weapons.enabled or w is None:
        return ""
    if not usable(w, art, content, world):
        return f"兵器　{_describe(w)}，{_mismatch(w, art, content, world)}"
    return f"兵器　{_describe(w)}，威力 {_pct(bonus(w, art, content, world))}"


def _row(w: Weapon, art: MartialArt | None, content: Content, world: WorldStateStore) -> dict:
    fits = usable(w, art, content, world)
    return {
        "id": w.id, "name": w.name, "kind": w.kind, "attribute": w.attribute, "tier": w.tier, "quality": w.quality,
        "edge": w.edge, "fits": fits, "bonus": _pct(bonus(w, art, content, world)) if fits else None,
    }


def rows(state: GameState, content: Content, world: WorldStateStore, art: MartialArt | None) -> dict:
    """修練頁的兵器那一塊（server.menxia_view 的 weapons）：身上那把、裝備庫、格數。開關關著時 worn 是 None、rack 是空的。"""
    p = state.player
    if not content.config.weapons.enabled:
        return {"worn": None, "rack": [], "cap": content.config.weapons.rack_cap}
    return {
        "worn": _row(p.weapon, art, content, world) if p.weapon else None,
        "rack": [_row(w, art, content, world) for w in p.rack],
        "cap": content.config.weapons.rack_cap,
    }
