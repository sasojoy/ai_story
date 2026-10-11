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

from . import equipment
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
    劇情戰與全服決戰不呼叫這裡（engine._file_battle 擋劇情戰；決戰不走 _file_battle）；頭目戰（kind=duel）、切磋、截殺雙方照磨（防具另有自己的條件，見 armor.wears）。"""
    rule, p = content.config.weapons, state.player
    if not rule.enabled or p.weapon is None:
        return []
    p.weapon.edge = max(0, p.weapon.edge - rule.wear.get(tier, 0))
    if p.weapon.edge < rule.edge_warn and not p.edge_warned:
        p.edge_warned = True
        return [EDGE_WARNING.format(name=p.weapon.name)]
    return []


# ---- 鐵匠鋪（4.1～4.7）：買、修、換 ----

NOUNS = {"劍": "劍", "刀": "刀", "槍": "槍", "棍": "棍", "弓弩": "弩", "拳腳": "拳套"}
ATTR_WORDS = {"陰": "寒鐵", "陽": "赤銅", "剛": "厚背", "柔": "軟鋼", "快": "輕鋒", "慢": "沉鐵", "虛": "花紋", "實": "重鐵"}  # 待 joy 潤
FITS_MARK = "・配得上你的武學"  # 待 joy 潤：鐵匠鋪的「買」鈕上，種類對得上身上那門武學的那一把


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
    """兵器配方的名字對不對得上種類（附帶決定 c；naming.NamingRequest.check 跑它）：要有這一種的字、不能有別種的字、
    不能跟架上的現成兵器（shop_name）同名——不然買的跟打的分不出來。None＝可以。"""
    if not any(word in name for word in WEAPON_WORDS.get(kind, ())):
        return KIND_MISSING
    if any(word in name for other, words in WEAPON_WORDS.items() if other != kind for word in words):
        return KIND_CLASH
    if name in {shop_name(k, a) for k in WEAPON_KINDS for a in ATTR_WORDS}:
        return SHOP_CLASH
    return None


def fallback_name(content: Content, key: str, kind: str, salt: int = 0, tianji: int = 0) -> str:
    """兵器配方的退路名字（模型叫不動、取壞了）：字首＋craft_names.weapon 的一個字＋兵器字（NOUNS），一定帶兵器的字。
    種子同 naming.fallback_name（配方鍵＋這一季的天機，加鹽），同一個配方同一季永遠組出同一個名字。"""
    names = content.craft_names
    seed = key if tianji == 0 else f"{tianji}|{key}"
    digest = hashlib.sha256(f"{seed}#{salt}".encode()).digest()
    return names.prefixes[digest[0] % len(names.prefixes)] + names.weapon[digest[1] % len(names.weapon)] + NOUNS[kind]


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
) -> Weapon:
    """新的一把（四欄共用的流水號 +1，id「兵:N」）；recipe 是自己打的那一把的配方鍵，買的與掉落的沒有。"""
    return Weapon(id=equipment.next_id(state, "weapon"), name=name, kind=kind, attribute=attribute, tier=tier, quality=quality,
                  recipe=recipe)


def rack_full(state: GameState, content: Content) -> bool:
    """手上有一把、裝備庫（四欄合算）也滿了就放不下（手上空著的話新的直接拿在手上，用不到裝備庫）。"""
    return equipment.rack_full(state, content, "weapon")


def store(state: GameState, content: Content, weapon: Weapon) -> str:
    """拿到一把：手上空著就拿在手上，不然放進裝備庫（呼叫端先用 rack_full 擋）。拿在手上的是另一把，鈍了要有它自己的提醒。"""
    return equipment.store(state, weapon)


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
        fit = next((w for w in equipment.in_slot(p, "weapon") if usable(w, art, content, world)), None)  # 裝備四欄 3.3：只看武器那一欄
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
    return f"【{w.name}】{w.kind}・屬{w.attribute}・{grade(w)}{tempered}・鋒利度 {w.edge}"


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


def _row(w: Weapon, art: MartialArt | None, content: Content, world: WorldStateStore, worn: bool = False) -> dict:
    fits = usable(w, art, content, world)
    return {
        "id": w.id, "name": w.name, "kind": w.kind, "attribute": w.attribute, "tier": w.tier, "quality": w.quality,
        "edge": w.edge, "fits": fits, "bonus": _pct(bonus(w, art, content, world)) if fits else None,
        "grade": grade(w),
        "confirm": "" if worn else dismantle_confirm(content, w),  # 身上那把不能拆，沒有問句（FB-125）
        "tempers": w.tempers, "temper_max": content.config.weapons.temper_max,
        "recipe": recipe_text(content, w.recipe),  # 自己打的那一把寫配方（主料＋輔料），買的、掉落的是 None
    }


def rows(state: GameState, content: Content, world: WorldStateStore, art: MartialArt | None) -> dict:
    """修練頁的兵器那一塊（server.menxia_view 的 weapons）：身上那把、裝備庫、格數。開關關著時 worn 是 None、rack 是空的。"""
    p = state.player
    if not content.config.weapons.enabled:
        return {"worn": None, "rack": [], "cap": content.config.weapons.rack_cap}
    return {
        "worn": _row(p.weapon, art, content, world, worn=True) if p.weapon else None,
        "rack": [_row(w, art, content, world) for w in equipment.in_slot(p, "weapon")],  # 只列武器那一欄（裝備四欄 3.3）
        "cap": content.config.weapons.rack_cap,
    }
