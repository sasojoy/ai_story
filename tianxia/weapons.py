"""兵器（docs/superpowers/specs/2026-10-09-兵器-design.md）。

第一批（拿著就有用）：武學的兵器種類、身上那把的加成與鋒利度、鐵匠鋪的買、修、換、打贏掉落、角色卡那一行。
這個模組只 import models、state、martial_arts、world_state、equipment；team 反過來呼叫它（player_boost、_styled_fighters），
所以這裡不 import team——要武學本體的地方由呼叫端傳進來。

裝備四欄（裝備一）：跟欄位內容無關的（裝備庫、換上、拆解、階品、鐵匠鋪的字）搬到 equipment.py，這裡原名照留（smithing、engine、測試都寫
weapons.X）；store／rack_full／wield／dismantle 轉呼叫 equipment、只看武器那一欄。
"""
from __future__ import annotations

import hashlib
import random

from . import equipment, tactics
from .equipment import (  # noqa: F401  搬到 equipment 的共用部分，原名照留（smithing、engine、測試都寫 weapons.X）
    DISMANTLE_ASK, DISMANTLE_LIST, DISMANTLE_MISSING, DISMANTLE_MORE, DISMANTLE_PREFIX, DISMANTLE_YES, NO_REPAIR_MATERIAL,
    NOT_HERE, RACK_FULL, SMITH, TIER_WORDS, TOWN_TAG, dismantle_confirm, dismantle_material, dismantle_order, grade,
    grade_line, repair_material,
)
from .martial_arts import MartialArt, counters
from .models import WEAPON_KINDS, Content
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
        if art.weapon:  # 自創的武學：式那一步挑的種類
            return art.weapon
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
    """這把兵器配不配得上身上這門武學（2.3）：開關開著、兩樣都有、是武器那一欄的（裝備四欄 3.3：防具、坐騎、寶物一律不算）、種類一樣。"""
    return (
        content.config.weapons.enabled and weapon is not None and art is not None and weapon.slot == "weapon"
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
    if weapon.original:  # 神器原品、仿品（打造隱藏配方設計 4.3）：基本值取代階那一格；品質存上品、照查表 +4；不看內容、不另加名器的 2%
        base = rule.original_base
    elif weapon.copy_of is not None:
        base = rule.copy_base
    else:
        base = rule.tier_bonus.get(str(weapon.tier), 0.0)
    base += rule.quality_bonus.get(weapon.quality, 0.0) + rule.temper_step * weapon.tempers
    if equipment.named(content, weapon):
        base += rule.named_bonus  # 名器多一截（打造隱藏配方設計 4.2）
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


EDGE_WARNING = "你的{name}{dull}，找間鐵匠鋪修一修。"  # 待 joy 潤；{dull} 照種類（DULL，FB-127：拳套、弩、棍沒有刀口）


def wear(state: GameState, content: Content, tier: str) -> list[str]:
    """打完一場，身上那把扣鋒利度（3.4，照結果）；第一次鈍到 edge_warn 以下回一句提醒（只一次，修好才重設）。
    劇情戰與全服決戰不呼叫這裡（engine._file_battle 擋劇情戰；決戰不走 _file_battle）；頭目戰（kind=duel）、切磋、截殺雙方照磨（防具另有自己的條件，見 armor.wears）。"""
    rule, p = content.config.weapons, state.player
    if not rule.enabled or p.weapon is None:
        return []
    p.weapon.edge = max(0, p.weapon.edge - rule.wear.get(tier, 0))
    if p.weapon.edge < rule.edge_warn and not p.edge_warned:
        p.edge_warned = True
        return [EDGE_WARNING.format(name=p.weapon.name, dull=DULL.get(p.weapon.kind, "鈍了"))]
    return []


# ---- 鐵匠鋪（4.1～4.7）：買、修、換 ----

NOUNS = {"劍": "劍", "刀": "刀", "槍": "槍", "棍": "棍", "弓弩": "弩", "拳腳": "拳套"}
UNITS = equipment.WEAPON_UNITS  # 量詞（FB-133、FB-160）：拳套論副，其他兵器論把（表在 equipment，防具與坐騎的也在那裡）
# 鈍了、還不用修的說法照種類（FB-127：拳套、弩、棍寫「刀口」不通）。待 joy 潤。DULL 接在名字後面（「你的厚背拳套磨薄了」），
# 名字本身就是兵器，不再寫一次兵器字（終審 F3：「你的厚背拳套拳套磨薄了」）；KEEN 單獨寫在「修」鈕的括號裡，可以帶兵器字
DULL = {"劍": "鋒口鈍了", "刀": "刃口鈍了", "槍": "鋒頭鈍了", "棍": "磨禿了", "弓弩": "弦鬆了", "拳腳": "磨薄了"}
KEEN = {"劍": "劍鋒還利", "刀": "刀口還利", "槍": "槍尖還利", "棍": "棍頭還結實", "弓弩": "弩弦還緊", "拳腳": "拳套還結實"}
CLASH_NOTE = "（與武學屬性相剋）"  # 待 joy 潤（FB-127）：配得上、屬性卻相剋時威力後面多這一句，不然「+0%」看起來像沒配上


def noun(kind: str) -> str:
    """寫給玩家看的兵器字（拳套、弩）：種類名（拳腳、弓弩）只拿來認東西（FB-127、FB-133）。"""
    return NOUNS.get(kind, kind)


def unit(kind: str) -> str:
    """兵器的量詞：拳套一副，其他一把（FB-133、FB-160）。"""
    return equipment.unit_for("weapon", kind)


def clashes(weapon: Weapon | None, art: MartialArt | None) -> bool:
    """兵器的屬性跟武學相剋（任一邊剋另一邊，bonus 那一截扣 match）。沒有兵器或武學是 False。"""
    return (weapon is not None and art is not None
            and (counters(weapon.attribute, art.attribute) or counters(art.attribute, weapon.attribute)))
ATTR_WORDS = {"陰": "寒鐵", "陽": "赤銅", "剛": "厚背", "柔": "軟鋼", "快": "輕鋒", "慢": "沉鐵", "虛": "花紋", "實": "重鐵"}  # 待 joy 潤
FITS_MARK = "・配得上你的武學"  # 待 joy 潤：鐵匠鋪的「買」鈕上，種類對得上身上那門武學的那一把
UNFIT_NOTE = "・這{unit}配不上你的武學，加成用不上"  # 待 joy 潤（量詞照種類，終審 F4；用 unfit_note）：鐵匠鋪的「修」「淬煉」鈕（按得下去的）上，身上那把配不上身上的武學（含沒有武學）時多的一句，免得白花料與銀兩


def unfit_note(weapon: Weapon) -> str:
    """UNFIT_NOTE 照這把的量詞（拳套一副，終審 F4）。"""
    return UNFIT_NOTE.format(unit=equipment.unit_for("weapon", weapon.kind))


def worn_unfit(state: GameState, art: MartialArt | None, content: Content, world: WorldStateStore) -> bool:
    """身上有一把兵器、可是配不上身上這門武學（art 是 None 也算配不上）：它現在的加成是 0，修與淬煉都看不到回報（PM 2026-10-11）。"""
    return state.player.weapon is not None and not usable(state.player.weapon, art, content, world)


def shop_name(kind: str, attribute: str) -> str:
    """架上與掉落的兵器名（4.5、4.8）：屬性字＋兵器字，例「厚背刀」「輕鋒弩」。不叫模型。"""
    return f"{ATTR_WORDS[attribute]}{NOUNS[kind]}"


# 名字看得出是哪一種兵器的字（附帶決定 c）：自己這一種至少要有一個、別種的一個都不能有
WEAPON_WORDS: dict[str, tuple[str, ...]] = {
    "劍": ("劍",), "刀": ("刀",), "槍": ("槍", "矛"), "棍": ("棍", "杖", "錘"), "弓弩": ("弩", "弓"), "拳腳": ("拳套", "護手", "拳"),
}
KIND_MISSING = "名字看不出是什麼兵器"  # 待 joy 潤
KIND_CLASH = "名字像是另一種兵器"  # 待 joy 潤
SHOP_CLASH = "跟鐵匠鋪架上的兵器同名"  # 待 joy 潤


def kind_problem(kind: str, name: str) -> str | None:
    """兵器配方的名字對不對得上種類（附帶決定 c；content.validate 驗對照表與隱藏配方的名字時跑它，第二批的神器定名也用擋別種兵器的那一段）：要有這一種的字、不能有別種的字、
    不能跟架上的現成兵器（shop_name）同名——不然買的跟打的分不出來。None＝可以。"""
    if not any(word in name for word in WEAPON_WORDS.get(kind, ())):
        return KIND_MISSING
    if any(word in name for other, words in WEAPON_WORDS.items() if other != kind for word in words):
        return KIND_CLASH
    if name in {shop_name(k, a) for k in WEAPON_KINDS for a in ATTR_WORDS}:
        return SHOP_CLASH
    return None


def table_name(content: Content, kind: str, main: str, aux: str) -> str:
    """一般組合的兵器名（打造隱藏配方設計 4.1、PM 2026-10-12 決定第 1 條）：字首照主料、中間字照輔料在素材表（content.materials，
    就是 materials.json 的順序）的位置取，最後接兵器字（NOUNS）。不叫模型、不登記；同一個組合每季一樣，同一種兵器的每個組合名字都不同
    （content.validate 驗過字表的前「素材數」個字夠、不重複）。主輔不交換：對調是另一個名字。"""
    order = list(content.materials)
    names = content.craft_names
    return names.prefixes[order.index(main)] + names.weapon[order.index(aux)] + NOUNS[kind]


def smith_here(state: GameState, content: Content) -> bool:
    """這裡打得了、買得到、修得了兵器（4.1）：武器開著、人在城鎮（equipment.in_town）。鐵匠鋪開不開門另看 equipment.smith_open
    （防具開著、武器關著時也開門，只是只有防具那一頁）。"""
    return equipment.on(content, "weapon") and equipment.in_town(state, content)


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


FORGE_PREFIX = "兵|"  # 兵器配方鍵的開頭（兵器設計 4.4）：前綴就是欄位（裝備四欄設計 4.7），之後防具打造用同一張 gear_recipes 表、前綴「鎧|」


def recipe_key(kind: str, main: str, aux: str) -> str:
    """兵器配方鍵（4.4）：「兵|種類|主料+輔料」。前綴「兵|」就是武器那一欄（之後防具是「鎧|主料+輔料」，共用 gear_recipes）。
    主輔不交換：同兩種素材對調是另一個配方。"""
    return f"{FORGE_PREFIX}{kind}|{main}+{aux}"


def recipe_parts(key: str | None) -> tuple[str, str, str] | None:
    """recipe_key 拆回（種類, 主料, 輔料）；不是武器欄的配方鍵（別的前綴，例如之後防具的「鎧|」，或 None）回 None。"""
    if not key or not key.startswith(FORGE_PREFIX):
        return None
    kind, _, pair = key[len(FORGE_PREFIX):].partition("|")
    main, plus, aux = pair.partition("+")
    return (kind, main, aux) if kind and plus and main and aux else None


def recipe_text(content: Content, key: str | None) -> str | None:
    """配方寫給玩家看（修練頁的裝備庫）：「精鐵砂＋驚羽」（主料在前）；不是自己打的（買的、掉落的）是 None。"""
    parts = recipe_parts(key)
    if parts is None:
        return None
    _, main, aux = parts
    name = lambda mid: content.materials[mid].name if mid in content.materials else mid  # noqa: E731
    return f"{name(main)}＋{name(aux)}"


def new_weapon(
    state: GameState, *, name: str, kind: str, attribute: str, tier: int, quality: str, recipe: str | None = None,
    secret: str | None = None, original: bool = False, copy_of: str | None = None, named_entry: str | None = None,
    collected: bool = False,
) -> Weapon:
    """新的一把（四欄共用的流水號 +1，id「兵:N」）；recipe 是自己打的那一把的配方鍵，買的與掉落的沒有；secret 是名器或神器的隱藏配方 id；
    original／copy_of 是神器的原品與仿品（copy_of 記「鑄|配方 id」，打造隱藏配方設計 5.3）。"""
    return Weapon(id=equipment.next_id(state, "weapon"), name=name, kind=kind, attribute=attribute, tier=tier, quality=quality,
                  recipe=recipe, secret=secret, original=original, copy_of=copy_of, named_entry=named_entry, collected=collected)


def rack_full(state: GameState, content: Content) -> bool:
    """手上有一把、裝備庫（四欄合算）也滿了就放不下（手上空著的話新的直接拿在手上，用不到裝備庫）。"""
    return equipment.rack_full(state, content, "weapon")


def store(state: GameState, content: Content, weapon: Weapon) -> str:
    """拿到一把：手上空著就拿在手上，不然放進裝備庫（呼叫端先用 rack_full 擋）。拿在手上的是另一把，鈍了要有它自己的提醒。"""
    return equipment.store(state, weapon)


DROP_LINE = "撿到一{unit}【{name}】"  # 待 joy 潤；{unit} 拳套是副（FB-133）
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
    return weapon, [DROP_LINE.format(unit=unit(kind), name=weapon.name), store(state, content, weapon)]


def buy_problem(state: GameState, content: Content, kind: str) -> str | None:
    if not smith_here(state, content):
        return NOT_HERE  # 鐵匠鋪的選單關了、人走了：引擎層自己也再驗一次
    if kind not in WEAPON_KINDS:
        return "沒有這種兵器"
    if rack_full(state, content):
        return RACK_FULL
    short = content.config.weapons.shop_price - state.player.stats.get("silver", 0)
    return f"還差 {short} 兩" if short > 0 else None


SWAPPED = "你換上了【{name}】，原本那{unit}【{old}】放上了裝備庫。"  # 待 joy 潤（FB-128：買下配得上的就直接換上）


def buy(state: GameState, content: Content, kind: str, art: MartialArt | None = None, world: WorldStateStore | None = None) -> list[str]:
    """買一把架上的（4.5）：空手就拿在手上，不然進裝備庫——手上那把配不上身上的武學、買下的這把配得上時直接換上，舊的進裝備庫
    （FB-128，PM 2026-10-14；配得上卻相剋的不算配不上，照舊進裝備庫）。art、world 沒給（舊的呼叫）照舊不換。"""
    problem = buy_problem(state, content, kind)
    if problem is not None:
        return [f"（{problem}。）"]
    item = next(w for w in stock(state, content) if w.kind == kind)
    price = content.config.weapons.shop_price
    state.player.stats["silver"] -= price
    weapon = new_weapon(state, name=item.name, kind=kind, attribute=item.attribute, tier=1, quality="下品")
    head = f"你花 {price} 兩買下一{unit(kind)}【{weapon.name}】。"
    old = state.player.weapon
    if old is not None and world is not None and not usable(old, art, content, world) and usable(weapon, art, content, world):
        state.player.rack.append(weapon)
        equipment.wield(state, content, weapon.id, ("weapon",))
        return [head, SWAPPED.format(name=weapon.name, unit=unit(old.kind), old=old.name)]
    return [head, store(state, content, weapon)]


def repair_problem(state: GameState, content: Content) -> str | None:
    p, rule = state.player, content.config.weapons
    if not smith_here(state, content):
        return NOT_HERE
    if p.weapon is None:
        return "手上沒有兵器"
    if p.weapon.edge >= 100:
        return KEEN.get(p.weapon.kind, "還不用修")
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
    """換兵器（2.2）：裝備庫裡那一把換到手上，手上那把放回裝備庫。只看武器那一欄（鐵匠鋪兵器頁的「換上」）；修練頁走
    Game.wield_weapon（武器、防具都收）。不花體力。"""
    return equipment.wield(state, content, weapon_id, ("weapon",))


def dismantle(state: GameState, content: Content, weapon_id: str) -> list[str]:
    """拆解（兵器設計 4.7.1）：裝備庫裡的一把拆成一個素材（equipment.dismantle_material）。只看武器那一欄（鐵匠鋪兵器頁）；
    修練頁走 Game.dismantle_weapon。網頁先問一次（FB-125），引擎收到就拆；手上那把、開關關著、裝備庫沒這一把，什麼都不動。"""
    return equipment.dismantle(state, content, weapon_id, ("weapon",))


REPAIR_AT = 50  # 機器人與假人鈍到這裡以下才修


def wanted(state: GameState, content: Content, world: WorldStateStore, art: MartialArt | None) -> str | None:
    """在鐵匠鋪最該按的那一顆（整季機器人與伺服器假人共用）：先把裝備庫裡配得上的換到手上，再買一把配得上的，再修配得上的那把。"""
    if not smith_here(state, content) or art is None:
        return None
    p = state.player
    if not usable(p.weapon, art, content, world):
        fit = next((w for w in equipment.in_slot(p, "weapon") if usable(w, art, content, world)
                    and equipment.wear_problem(state, content, w) is None), None)  # 裝備四欄 3.3：只看武器那一欄；穿不上的神器不挑
        if fit is not None:
            return f"smith:wield:{fit.id}"
        kind = art_weapon(art.id, content, world)
        if kind and buy_problem(state, content, kind) is None:
            return f"smith:buy:{kind}"
    if usable(p.weapon, art, content, world) and p.weapon.edge < REPAIR_AT and repair_problem(state, content) is None:
        return "smith:repair"
    return None


def _pct(ratio: float) -> str:
    """跟 skillview._pct 同一種寫法：帶正負號、最多一位小數、整數不寫「.0」。"""
    return f"{ratio:+.1%}".replace(".0%", "%")


def _describe(w: Weapon) -> str:
    tempered = f"・淬煉 {w.tempers} 次" if w.tempers else ""  # 待 joy 潤
    return f"【{w.name}】{noun(w.kind)}・屬{w.attribute}・{grade(w)}{tempered}・鋒利度 {w.edge}"


def _mismatch(w: Weapon, art: MartialArt | None, content: Content, world: WorldStateStore) -> str:
    """配不上的那一句（待 joy 潤）：拳腳、弓弩寫成「拳腳法」「弓弩法」不通順，各自另寫。前半寫東西不寫種類名（FB-127：「這副拳套」）。"""
    mine = art_weapon(art.id, content, world) if art is not None else None
    if not mine:
        return "你身上沒有用得上兵器的武學"
    if mine == "拳腳":
        return f"這{unit(w.kind)}{noun(w.kind)}用不上你的拳腳功夫"
    if mine == "弓弩":
        return f"這{unit(w.kind)}{noun(w.kind)}用不上你的弓弩上的功夫"
    return f"這{unit(w.kind)}{noun(w.kind)}用不上你的{mine}法"


EMPTY = "手上沒有兵器。"  # 修練頁武器那一段手上空著（原本寫在 web/app.js）
RACK_NOTE = "城裡的鐵匠鋪打得出、買得到、修得好，也淬得了；用不上的拆了換素材。"  # 待 joy 潤：修練頁武器那一段底下（兵器第二批 Task 8 的字）


def card_line(state: GameState, content: Content, world: WorldStateStore, art: MartialArt | None) -> str:
    """本人卡上的「兵器」那一行（3.6）：空手或開關關著是空字串。神器與名將本命兵器底下多一兩行特技與人器合一（本命戰法第三批）。"""
    w = state.player.weapon
    if not content.config.weapons.enabled or w is None:
        return ""
    if not usable(w, art, content, world):
        return "\n".join([f"兵器　{_describe(w)}，{_mismatch(w, art, content, world)}", *tactics.item_lines(content, w)])
    return "\n".join([f"兵器　{_describe(w)}，威力 {_power(w, art, content, world)}", *tactics.item_lines(content, w)])


def _power(w: Weapon, art: MartialArt | None, content: Content, world: WorldStateStore) -> str:
    """配得上的那把給幾成威力，相剋時後面多 CLASH_NOTE（FB-127）。"""
    return _pct(bonus(w, art, content, world)) + (CLASH_NOTE if clashes(w, art) else "")


def _row(w: Weapon, art: MartialArt | None, content: Content, world: WorldStateStore, worn: bool = False) -> dict:
    fits = usable(w, art, content, world)
    return {
        "id": w.id, "name": w.name, "kind": w.kind, "noun": noun(w.kind), "attribute": w.attribute, "tier": w.tier, "quality": w.quality,
        "edge": w.edge, "fits": fits, "bonus": _power(w, art, content, world) if fits else None,
        "grade": grade(w),
        "confirm": "" if worn or w.original else dismantle_confirm(content, w),  # 身上那把不能拆，沒有問句（FB-125）；原品也拆不得（5.4）
        "keep": equipment.kept(w),  # 網頁照它把拆解鈕灰掉寫原因（神器原品、本命兵器）
        "tempers": w.tempers, "temper_max": content.config.weapons.temper_max,
        "recipe": recipe_text(content, w.recipe),  # 自己打的那一把寫配方（主料＋輔料），買的、掉落的是 None
        "tactic": tactics.item_lines(content, w),  # 神器、名將本命兵器的特技與人器合一（本命戰法第三批），沒有是空的
    }


def fit_line(art: MartialArt | None, content: Content, world: WorldStateStore) -> str:
    """修練頁武器那一段最上面一句：身上的武學配哪一種兵器（Joy 2026-10-17：換了一門武學之後整排都寫「用不上」，看不出為什麼）。"""
    mine = art_weapon(art.id, content, world) if art is not None else None
    if not mine:
        return "你身上的武學用不上兵器，哪一把都沒有加成。"
    return f"你身上的【{art.name}】配{noun(mine)}，只有{noun(mine)}有加成。"


def rows(state: GameState, content: Content, world: WorldStateStore, art: MartialArt | None) -> dict:
    """修練頁的兵器那一塊（skillview.gear_rows 把它併進 server.menxia_view 的 gear 裡 slot 是 weapon 的那一段）：身上那把、裝備庫、格數。開關關著時 worn 是 None、rack 是空的。"""
    p = state.player
    if not content.config.weapons.enabled:
        return {"worn": None, "rack": [], "cap": content.config.weapons.rack_cap}
    return {
        "fit_line": fit_line(art, content, world),
        "worn": _row(p.weapon, art, content, world, worn=True) if p.weapon else None,
        "rack": [equipment.wear_row(_row(w, art, content, world), state, content, w) for w in equipment.in_slot(p, "weapon")],  # 只列武器那一欄（裝備四欄 3.3）
        "cap": content.config.weapons.rack_cap,
    }
