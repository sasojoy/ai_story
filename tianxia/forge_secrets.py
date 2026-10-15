"""打造的隱藏配方（docs/superpowers/specs/2026-10-12-打造隱藏配方-design.md；第一批：名器、首位發現者、線索與鑄譜；第二批：神器原品與仿品、定名的檢查、神器譜）。

| 誰 | 做什麼 |
|---|---|
| 內容（content/forge_secrets.json） | 隱藏配方池：欄位、種類、主料與輔料的形狀（屬性＋階）、名器的名字、一句說明、三句口訣 |
| 這裡 | 這一季挑哪幾條（照天機）、這一爐合不合得上、首位發現者那一筆、名器的名字照內容讀、鑄譜（聽過的口訣、打中過的） |
| smithing | 打中了怎麼打、登記、傳聞、回饋 |

每季照天機從池子裡照「欄位:組」挑 Config.forge_secrets.per_season 條（全服同一批，換季換一批；這一欄的裝備關著就不挑）。認形狀不認素材 id；
主輔不交換；比對不擲骰。打中了的全服登記在 gear_recipes（鍵「鑄|配方 id」，名字欄寫鍵本身、不佔名字空間）。口訣三句：0 說書、1 鐵匠、2 殘譜；
玩家聽過的、打中過的記在鑄譜（PlayerState.forge_manual），只記這一季的。擲骰一律用自己的亂數（secret_recipes.roll），不動 Game.rng。
只 import models、state、calendar、equipment、weapons、armor、secret_recipes、world_state（型別）；smithing、engine、content 反過來用它。"""
from __future__ import annotations

import hashlib

from . import armor, calendar, equipment, secret_recipes, weapons
from .models import WEAPON_KINDS, Content, ForgeSecret, ForgeSide, Material
from .state import COPY_NAME, DIVINE_UNNAMED, Equipment, GameState, GearFind, Manual, PlayerState, WorldState
from .world_state import WorldStateStore

PREFIX = "鑄|"  # gear_recipes 裡隱藏配方那幾列的鍵開頭（7.1）：不跟「融|」「合|」「兼|」「秘|」「兵|」「鎧|」撞；state.GearFind.id 用同一個字
GROUPS = tuple(f"{slot}:{group}" for slot in ("weapon", "armor") for group in ("1", "2", "3", "divine"))
SEED_PAIRS = ({"剛", "柔"}, {"快", "慢"})  # insights.merged_attribute 照種子挑的兩對：每季可能不同，隱藏配方不收（3.1）
TALE, SMITH, SCRAP = 0, 1, 2  # 口訣的三個版本（ForgeSecret.clues 的位置；設計 6.1：武學的人物順口換成鐵匠順口）


def _rank(tianji: int, recipe_id: str) -> bytes:
    return hashlib.sha256(f"{tianji}|{recipe_id}|鑄法".encode("utf-8")).digest()


def group_of(recipe: ForgeSecret) -> str:
    """這一條屬於哪一組（3.2）：「欄位:主料的階」，神器配方是「欄位:divine」。"""
    return f"{recipe.slot}:divine" if recipe.divine else f"{recipe.slot}:{recipe.main.tier}"


def covers(side: ForgeSide) -> range:
    """這一樣料認哪幾階：寫死 tier 就是那一階，min_tier 是那一階到三階；都沒寫（壞資料，載入時擋）是空的。"""
    if side.tier is not None:
        return range(side.tier, side.tier + 1)
    if side.min_tier is not None:
        return range(side.min_tier, 4)
    return range(0)


def fits(side: ForgeSide, material: Material) -> bool:
    return material.attribute == side.attribute and material.tier in covers(side)


def active(content: Content, tianji: int, season: WorldState | None = None) -> list[ForgeSecret]:
    """這一季（天機）的隱藏配方：照 per_season 每一組挑幾條，同一季全服同一批、換季換一批；這一欄的裝備關著（equipment.on）不挑。
    這一季蓋了 forge_divine_per_kind 的章（素材與經濟設計第二節，企劃者 2026-10-15）：兵器的神器配方同一種兵器只挑一條——
    第一季的章（calendar.season_one_on）池子裡的每一種都挑一條（練什麼武學都有配得上的神器可以追）；其餘的季照天機排好，
    挑 per_season 條、跳過已經挑到的種類（池子的種類不夠就少挑）。防具照舊。season 是 None、沒蓋章（正在跑的季）照舊。"""
    out: list[ForgeSecret] = []
    per_kind = season is not None and season.forge_divine_per_kind
    for group, count in content.config.forge_secrets.per_season.items():
        if count <= 0 or not equipment.on(content, group.partition(":")[0]):
            continue
        pool = sorted((r for r in content.forge_secrets.values() if group_of(r) == group), key=lambda r: _rank(tianji, r.id))
        if per_kind and group == "weapon:divine":
            first: dict[str | None, ForgeSecret] = {}
            for recipe in pool:
                first.setdefault(recipe.kind, recipe)
            picked = list(first.values())
            out += picked if calendar.season_one_on(season, content) else picked[:count]
        else:
            out += pool[:count]
    return out


def key(recipe: ForgeSecret) -> str:
    return PREFIX + recipe.id


def key_for(secret_id: str) -> str:
    """配方 id 換成 gear_recipes 的鍵（同 key，給只有 Equipment.secret 的地方用）。"""
    return PREFIX + secret_id


def owned_gear(p: PlayerState) -> list[Equipment]:
    """身上的兵器與防具、裝備庫、寄放的每一件（名器與神器的名字重寫、找原品都照這一份）。"""
    return [item for item in (p.weapon, p.armor, *p.rack, *p.held_gear) if item is not None]


def match(content: Content, tianji: int, slot: str, kind: str | None, main: str, aux: str,
          season: WorldState | None = None) -> ForgeSecret | None:
    """這一爐合得上這一季的哪一條隱藏配方（3.1）：欄位、兵器種類（防具不看）、主料、輔料各自對得上形狀；主輔不交換。不擲骰。
    season：這一季（照它的章挑配方，active）。"""
    if not content.forge_secrets or main not in content.materials or aux not in content.materials:
        return None
    m, a = content.materials[main], content.materials[aux]
    want = kind if slot == "weapon" else None
    return next((r for r in active(content, tianji, season) if r.slot == slot and r.kind == want and fits(r.main, m) and fits(r.aux, a)), None)


# ── 名器與首位發現者（4.2、7.1、7.2）──────────────────────────


def manual(state: GameState, tianji: int) -> Manual:
    """這一季的鑄譜（PlayerState.forge_manual；同 secret_recipes.manual）：記的是別一季的就換一本新的（隱藏配方每季換一批）。"""
    if state.player.forge_manual.tianji != tianji:
        state.player.forge_manual = Manual(tianji=tianji)
    return state.player.forge_manual


def solve(state: GameState, tianji: int, recipe: ForgeSecret, combo: str) -> None:
    """打中了（6.3「打中過」＝自己打出過這條的東西，不看是不是全服第一個）：記進鑄譜，連同打中的那一爐的組合鍵（鑄譜寫配方用）。"""
    book = manual(state, tianji)
    if recipe.id not in book.solved:
        book.solved.append(recipe.id)
    book.made.setdefault(recipe.id, combo)


def new_find(state: GameState, recipe: ForgeSecret, kind: str | None, attribute: str, tier: int) -> GearFind:
    """首位發現者那一筆（7.1）：登記當下記下名器的名字（神器配方是譜名）與寫給別人看的名號（同 fusion._secret_lines 用名號）。
    神器配方（照 14.1 甲）首位發現者就是原品主人：同一筆一起記，claim_gear_find 那一筆交易誰先寫進去誰拿原品。"""
    me = state.player.name
    return GearFind(secret=recipe.id, slot=recipe.slot, kind=kind if recipe.slot == "weapon" else "", attribute=attribute, tier=tier,
                    title=recipe.name, creator=me, creator_shown=me, divine=recipe.divine,
                    owner=me if recipe.divine else None, master_shown=me if recipe.divine else None)


def arrival(state: GameState, content: Content, recipe: ForgeSecret, find: GearFind, first: bool) -> list[str]:
    """名器或神器打出來那一句的下面（4.2、5.2、5.3、7.2）：一句說明（note），再一句——
    名器：全服第一個摸出來的、自己又打一件、或照別人摸出來的打成了；
    神器：原品（叫你去定名）、仿品而原品在自己手上、仿品而原品在別人手上。"""
    rule = content.config.forge_secrets
    lines = [recipe.note] if recipe.note else []
    me = state.player.name
    if recipe.divine:
        if first:
            lines.append(rule.divine_line.format(unit=equipment.unit_for(recipe.slot, find.kind)))
        elif find.owner == me:
            lines.append(rule.copy_mine_line)
        else:
            lines.append(rule.copy_line.format(who=find.master_shown or find.owner or "不知名的前人"))
    elif first:
        lines.append(rule.first_line)
    elif find.creator == me:
        lines.append(rule.mine_line)
    else:
        lines.append(rule.follow_line.format(who=find.creator_shown or find.creator or "不知名的前人"))
    return [line for line in lines if line]


def refresh_names(p: PlayerState, content: Content, world: WorldStateStore | None = None) -> None:
    """讀檔時重寫名器與神器的名字（name 只當備份）：Game._drop_stale_references 每次建 Game 都叫。
    名器照內容（4.2：joy 改名不動存檔；同 treasures.refresh_names），內容拿掉了那一條就留著舊名字。
    神器照全服那一列（5.2、5.3）：原品是定的名字（還沒定是「無名神器」），仿品是「仿・」接原品的名字——原品定名之後，別人手上的仿品
    下一次讀檔跟著改；這一季沒有那一列（別一季打的、資料不在）或沒給 world 就留著。只有 original／copy_of 的那幾件才查資料庫。"""
    for item in owned_gear(p):
        if item.secret is None:
            continue
        if item.original or item.copy_of is not None:
            find = world.lookup_gear_find(item.copy_of or key_for(item.secret)) if world is not None else None
            if find is not None and find.divine:
                item.name = find.name if item.original else COPY_NAME.format(name=find.name)
            continue
        recipe = content.forge_secrets.get(item.secret)
        if recipe is not None:
            item.name = recipe.name


# ── 神器原品定名的檢查（5.2；訊息、江湖史、傳聞在 smithing.name_divine）──────────

TABLE_CLASH = "跟鐵匠鋪尋常打得出的名字同名"  # 待 joy 潤：神器定的名字跟一般組合字表組得出的名字撞了


def what_text(slot: str, kind: str) -> str:
    """寫給人看的「哪一種」：兵器寫兵器字（weapons.NOUNS：劍、拳套），防具寫「防具」。"""
    return weapons.NOUNS.get(kind, kind) if slot == "weapon" else "防具"


def table_names(content: Content) -> set[str]:
    """一般組合的字表組得出來的每一個名字（5.2）：兵器 字首×兵器中間字×兵器字、防具 字首×防具中間字×甲鎧袍衫。用整張字表（不只前
    「素材數」個字），joy 之後在素材表後面加素材也擋得住。約三千個字串，只在定名時現算，不快取。"""
    names = content.craft_names
    made = {p + m + n for p in names.prefixes for m in names.weapon for n in weapons.NOUNS.values()}
    return made | {p + m + n for p in names.prefixes for m in names.armor for n in armor.FORGE_WORDS}


def divine_name_problem(content: Content, slot: str, kind: str, name: str) -> str | None:
    """神器原品定的名字還要過的（5.2；name_problem 另外過）：兵器不能有**別種**兵器的字（不要求帶自己這一種的字，例「斬月」）、
    不能跟架上的現成兵器同名；防具不能有兵器的字、不能跟架上的防具同名；都不能跟一般組合的字表組得出的名字同名
    （不然「仿・X」跟一般組合的「X」並存）。None＝可以。"""
    if slot == "weapon":
        if any(word in name for other, words in weapons.WEAPON_WORDS.items() if other != kind for word in words):
            return weapons.KIND_CLASH
        if name in {weapons.shop_name(k, a) for k in WEAPON_KINDS for a in weapons.ATTR_WORDS}:
            return weapons.SHOP_CLASH
    else:
        if any(word in name for words in weapons.WEAPON_WORDS.values() for word in words):
            return armor.WORD_CLASH
        if name in armor.SHOP_NAMES.values():
            return armor.SHOP_CLASH
    if name in table_names(content):
        return TABLE_CLASH
    return None


def unnamed_originals(state: GameState, world: WorldStateStore) -> dict[str, str]:
    """身上、裝備庫、寄放的神器原品裡還等著你定名的（5.2）：裝備 id → 譜名（「沿用譜名」那一顆寫的字，登記當下記的 GearFind.title）。
    只查有 original 的那幾件（一個人頂多幾件）；全服那一列的主人是你、還沒定名才算。一個人可以同時有好幾把（5.2：不能像絕學那樣擋）。"""
    p = state.player
    out: dict[str, str] = {}
    for item in owned_gear(p):
        if not item.original or item.secret is None:
            continue
        find = world.lookup_gear_find(key_for(item.secret))
        if find is not None and find.divine and find.owner == p.name and find.divine_name is None:
            out[item.id] = find.title
    return out


# ── 神器譜（5.5：見聞→江湖史底下，跨季保留）──────────────────

DIVINE_BOOK = "### 神器譜"  # 待 joy 潤：江湖史那一頁另起的一段標題


def divine_book(records: list[tuple[int, GearFind]], extra: list[tuple[int, str]] | None = None) -> str:
    """神器譜那一段的 Markdown（Game.chronicle_text 接在江湖史後面）：一把一行——第幾季、名字（還沒定名寫「無名神器（劍）」）、
    種類或防具、屬性、原品在誰手上（打出那一刻記下的 master_shown）、仿品幾把（不列人名）。extra 是別處來的（季數, 那一行）：
    名將本命兵器（signature_arms.book_rows，打造第三批），併進來照季排，同一季打出來的神器在前。都沒有是空字串。整行待 joy 潤。"""
    rows: list[tuple[int, str]] = []
    for season, find in records:
        what = what_text(find.slot, find.kind)
        name = f"【{find.divine_name}】" if find.divine_name else f"{DIVINE_UNNAMED}（{what}）"
        copies = f"，仿品 {find.copies} {equipment.unit_for(find.slot, find.kind)}" if find.copies else ""  # 防具論件（終審 F5，FB-146）
        rows.append((season, f"- 第 {season} 季　{name}　{what}・屬{find.attribute}　原品在{find.master_shown or find.owner}手上{copies}"))
    rows += extra or []
    if not rows:
        return ""
    rows.sort(key=lambda row: row[0])  # 穩定排序：同一季照原來的先後（打出來的神器、再本命兵器）
    return f"{DIVINE_BOOK}\n\n" + "\n".join(line for _, line in rows)


# ── 線索與鑄譜（第六節）──────────────────────────────────


def hear(state: GameState, content: Content, tianji: int, source: int, seed: str) -> str | None:
    """說書與殘譜：照 secret_recipes.hear_from 挑這一季一條隱藏配方的那一版口訣，記進鑄譜，回那一句；這一季沒有隱藏配方回 None。"""
    recipes = active(content, tianji, state.world)
    if not recipes:
        return None
    return secret_recipes.hear_from(recipes, manual(state, tianji), source, seed)


def towns(content: Content) -> list[str]:
    """有鐵匠鋪的地方（標籤「城鎮」，同 equipment.in_town）。"""
    return [lid for lid, loc in content.locations.items() if equipment.TOWN_TAG in (loc.tags or [])]


def smith_clue(content: Content, tianji: int, location: str, season: WorldState | None = None) -> ForgeSecret | None:
    """這家鐵匠鋪這一季知道哪一條（6.2）：城鎮與這一季的隱藏配方各自照「天機|id」雜湊排好，第 i 家知道第 i mod 條數條；城鎮比條數多時
    每一條至少有一家知道，想聽別條就要換一家。不是城鎮、這一季沒有隱藏配方是 None。"""
    recipes = sorted(active(content, tianji, season), key=lambda r: _rank(tianji, r.id))
    places = sorted(towns(content), key=lambda lid: hashlib.sha256(f"{tianji}|{lid}|鐵匠".encode("utf-8")).digest())
    if not recipes or location not in places:
        return None
    return recipes[places.index(location) % len(recipes)]


def hear_smith(state: GameState, content: Content, tianji: int) -> str | None:
    """鐵匠順口（6.2）：這家知道的那一句（鐵匠版）直接記進鑄譜（不走 hear 的挑法，同人物順口）；已經聽過那一句就不再說，回 None。"""
    recipe = smith_clue(content, tianji, state.player.location, state.world)
    if recipe is None or not secret_recipes.note(manual(state, tianji), recipe, SMITH):
        return None
    return recipe.clues[SMITH]


def recipe_text(content: Content, combo: str | None) -> str | None:
    """鑄譜上寫的配方（6.3）：「劍：柳絲綿＋驚羽」「防具：流雲絮＋沉淵石」；認不得的鍵是 None。"""
    parts = weapons.recipe_parts(combo)
    if parts is not None:
        return f"{weapons.NOUNS.get(parts[0], parts[0])}：{weapons.recipe_text(content, combo)}"
    if armor.recipe_parts(combo) is not None:
        return f"防具：{armor.recipe_text(content, combo)}"
    return None


def view(state: GameState, content: Content, world: WorldStateStore) -> list[dict]:
    """鑄譜給畫面的資料（status_data["forge_manual"]，形狀同 secret_recipes.view 多一個 recipe）：這一季聽過口訣或打中過的隱藏配方，
    一條一筆——聽過的那幾句（照版本的先後）、打中了寫名字與配方（照自己打中的那一爐）；沒聽過也沒打過的不露。"""
    tianji = world.read().tianji
    book = state.player.forge_manual if state.player.forge_manual.tianji == tianji else Manual(tianji=tianji)
    rows = []
    for recipe in active(content, tianji, state.world):
        heard = book.heard.get(recipe.id, [])
        solved = recipe.id in book.solved
        if heard or solved:
            rows.append({"clues": [recipe.clues[i] for i in heard], "solved": recipe.name if solved else None,
                         "recipe": recipe_text(content, book.made.get(recipe.id)) if solved else None})
    return rows


def solved_name(state: GameState, content: Content, tianji: int, slot: str, kind: str | None, main: str, aux: str) -> str | None:
    """開爐鈕上寫不寫名字（6.4）：這一爐合得上這一季的隱藏配方、而且**自己的**鑄譜上打中過它，才回它的名字；其餘 None（不露）。"""
    recipe = match(content, tianji, slot, kind, main, aux, state.world)
    book = state.player.forge_manual
    if recipe is None or book.tianji != tianji or recipe.id not in book.solved:
        return None
    return recipe.name
