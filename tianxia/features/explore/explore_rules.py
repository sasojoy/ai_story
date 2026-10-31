"""探索一顆（減法季整合設計 4.1；主機側實作計畫 Task 2-2）的純規則：這一處算哪一張表（`kind_of`）、這一趟四類事的比重
（`weights`）、抽一類（`roll`）、出門一趟發生哪一件事（`draw`）、自己的亂數（`rng_for`）。

按一下「探索」＝出門一趟：照這一處的表抽**一件事**（`draw`）——事件、遭遇、素材、感悟其中一類。素材與遭遇自動結算；
事件與感悟要玩家選。2d（企劃者 2026-10-26「只抽一件事情」）以前是連抽三拍，同一類最多兩拍、要選的拍放最後；一件事就沒有那些規則了。
接了這裡的討伐懸賞，這一趟就是遭遇（`weights` 的 `bounty_here`：遭遇 100、其餘 0），交了差回原表。

cfg 是 `Config.jianfa`（`models.JianfaRules`，繼承 `jianfa_numbers.JianfaNumbers`；純規則的測試直接建後者）；地點只讀 `tags`、
`danger` 與 `explore_mix`。不 import engine、不碰 Game.rng：開關、選單、結算在引擎（`Game._explore_one`，Task 2-3）；
這裡另放鈕上的小字（`hint_of`，照比重算）與段落的寫法（`line`：照 content/outing_lines.json 抽句子、接成一段，結尾「得：…　失：…」）。
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tianxia.jianfa_numbers import ExploreOneTable, JianfaNumbers

TOWN, TEMPLE, FORD, WILD, HILL, CAMP = "town", "temple", "ford", "wild", "hill", "camp"  # 六種地點（jianfa_numbers.ExploreKind）
EVENT, ENCOUNTER, MATERIAL, INSIGHT = "event", "encounter", "material", "insight"
KINDS = (EVENT, ENCOUNTER, MATERIAL, INSIGHT)  # 一趟可能發生的四類事（比重的鍵照這個順序）
# 上一趟在這裡要選的那件事若是這幾類，這一趟不再抽它：同一處的感悟是同一則（設計 4.1「同一處連續兩趟要選的拍不同一則」）。
# 事件不在這裡：事件的不重照舊交給 events.rotation_pool，連兩趟都抽到事件是兩則不同的。
REPEATS_SAME = (INSIGHT,)
FILL = MATERIAL  # 什麼都抽不出來（比重全是 0）補素材


def match(cfg: JianfaNumbers, tags: Iterable[str]) -> ExploreOneTable | None:
    """這組地點標籤靠自己對得上哪一張表：照 `explore_tables` 的順序，第一張有共同標籤的；一個都對不上是 None。
    內容驗證（每個正式地點都歸得到一張）問它；探索本身問 `kind_of`。"""
    have = set(tags)
    return next((t for t in cfg.explore_tables if have & set(t.tags)), None)


def kind_of(cfg: JianfaNumbers, loc) -> ExploreOneTable:
    """這一處用哪一張表：`match`；標籤一張都對不上的歸最後一張（野）。"""
    return match(cfg, loc.tags) or cfg.explore_tables[-1]


def encounter_only() -> dict[str, int]:
    """這一趟一定是遭遇（接了這裡的討伐懸賞、頭目擋路）：遭遇 100、其餘 0。"""
    return {kind: 100 if kind == ENCOUNTER else 0 for kind in KINDS}


def weights(cfg: JianfaNumbers, loc, *, has_foes: bool, bounty_here: bool = False) -> dict[str, int]:
    """這一處這一趟四類的比重（設計 4.1）：
    - 接了這裡的討伐懸賞（bounty_here）：一趟只有一件事，這一趟就是懸賞那一路的遭遇（`encounter_only`；企劃者 2026-10-26 2d。懸賞那一路
      易手了也找得到，所以不看 has_foes），交了差回原表；
    - 照表；危險度每多一星（一星就是表上的數字），遭遇 +`danger_shift`、事件 −`danger_shift`，這兩欄夾在 `beat_floor`～`beat_cap`；
    - 這裡沒有對手（has_foes：引擎照此刻站的、不是自家的隊伍判）：遭遇是 0，那一份照比重分給其餘三類。
    地點自己寫了四欄（`Location.explore_mix`，設計 4.1 的覆寫）就照它，不照表的四欄。"""
    if bounty_here:
        return encounter_only()
    t = getattr(loc, "explore_mix", None) or kind_of(cfg, loc)
    got = {EVENT: t.event, ENCOUNTER: t.encounter, MATERIAL: t.material, INSIGHT: t.insight}
    shift = cfg.danger_shift * (loc.danger - 1)
    if shift:
        got[EVENT] = _clamp(cfg, t.event - shift)
        got[ENCOUNTER] = _clamp(cfg, t.encounter + shift)
    if not has_foes:
        got[ENCOUNTER] = 0
    return got


def _clamp(cfg: JianfaNumbers, value: int) -> int:
    return min(cfg.beat_cap, max(cfg.beat_floor, value))


def roll(rng: random.Random, weights: Mapping[str, float], exclude: Iterable[str] = ()) -> str | None:
    """照比重抽一類（比重是 0 的與 exclude 裡的不抽）；一類都抽不了是 None。擲一次 rng.random()。"""
    skip = set(exclude)
    pool = [(kind, w) for kind, w in weights.items() if w > 0 and kind not in skip]
    if not pool:
        return None
    x = rng.random() * sum(w for _, w in pool)
    for kind, w in pool:
        x -= w
        if x < 0:
            return kind
    return pool[-1][0]


def draw(rng: random.Random, weights: Mapping[str, float], *, last_choice: str | None = None) -> str:
    """出門一趟發生的那一件事（設計 4.1；2d，企劃者 2026-10-26「只抽一件事情」）：照比重抽一類。
    - last_choice：上一趟在這裡要選的那件事是哪一類（換了地方就給 None）；是 `REPEATS_SAME` 的（感悟）這一趟不抽它；
    - 什麼都抽不了（比重全是 0）補素材（`FILL`）。
    接了討伐懸賞、頭目擋路的趟，引擎給的比重是 `encounter_only`，抽出來就是遭遇。
    「這一件沒收穫補一個一階素材」看的是結算的結果，在引擎（Task 2-3）。"""
    exclude = (last_choice,) if last_choice in REPEATS_SAME else ()
    return roll(rng, weights, exclude) or FILL


def rng_for(season: int, name: str, serial: int, what: str) -> random.Random:
    """出門這一趟、這一個用途自己的亂數：季數｜名號｜第幾次探索（PlayerState.explore_seq）｜用途。決定性，不動 Game.rng；
    跟 `explore_modes.rng_for`（「探索|…」）分開，這一件事裡叫的舊結算照舊用它自己的。"""
    return random.Random(f"出門|{season}|{name}|{serial}|{what}")


# ── 鈕上的小字與段落（Task 2-3；字都待 joy 潤）──

# 這一處「多半給什麼」（設計 4.1「地點決定多半給什麼」）：**照表算出來，不寫死**（2e，FB-882，企劃者 2026-10-26「小字照表寫」；字待 joy 潤）。
# 一張表（或此刻擲骰用的比重）四欄裡最大的那一欄寫成兩個字（BEAT_MOSTLY），並列最大寫「參半」（mostly_of），前面接地點種類的字（PLACE_WORDS）。
# 鈕上括號最後那一段與四格探索那一格的小字（/api/main 的 mostly）讀這一處此刻的比重（hint_of：危險度往上加減、沒有對手、抽不到事件、悟不出感悟都算進去），
# 所以跟行動列底下那一行（howto.outing_line）永遠說同一件事。輿圖第一層名字旁的兩個字（tail_of，2f，FB-886）是同一個小字的最後兩個字：Game.map_mostly 替每一處
# 「假裝站過去」叫 _outing_plan 取得（看的人是誰、有沒有對手、懸賞、自家營寨都算進去）；玩法說明列六張表的樣子（hint_in）是講地點種類的通則，照表本身
# （沒有危險度，後面接一句危險的地方遇敵多些）、序章裡沒有比重可看時名字旁的退路（mostly_in）也照表。
# 以前（FB-832）寫的是寫死的一組字、只有招牌類的比重是 0 才改寫，寺的「多悟」就跟表對不上（事件 50、感悟 30）。
PLACE_WORDS = {TOWN: "城裡", TEMPLE: "寺裡", FORD: "渡口", WILD: "野外", HILL: "山裡", CAMP: "營裡"}
BEAT_MOSTLY = {EVENT: "多事", ENCOUNTER: "多敵", MATERIAL: "多料", INSIGHT: "多悟"}  # 比重最高的那一類寫成哪兩個字
BALANCED = "參半"  # 最高的有兩類以上並列
BOUNTY_WORD = "有賞"  # 接了這裡的討伐懸賞：「多半」那兩個字換成「有賞」（設計 4.1）：「野外有賞」
SPAR_WORD = "比劃"  # 自家營寨：遭遇是跟同袍比劃（輿圖名字旁寫這兩個字，鈕上寫 SPAR_HINT）
SPAR_HINT = "同袍" + SPAR_WORD  # 自家營寨：遭遇是跟同袍比劃（待 joy 潤）


def mostly_of(weights: Mapping[str, float]) -> str:
    """「多半」那兩個字照比重寫：四類裡比重最高的那一類（BEAT_MOSTLY），並列最高寫「參半」；全是 0 的那一趟補素材（FILL）所以寫「多料」。"""
    top = max((weights.get(kind, 0) for kind in KINDS), default=0)
    if top <= 0:
        return BEAT_MOSTLY[FILL]
    best = [kind for kind in KINDS if weights.get(kind, 0) == top]
    return BALANCED if len(best) > 1 else BEAT_MOSTLY[best[0]]


def table_weights(table: ExploreOneTable) -> dict[str, int]:
    """一張表的四欄（事件、遭遇、素材、感悟），照 KINDS 的順序。"""
    return {EVENT: table.event, ENCOUNTER: table.encounter, MATERIAL: table.material, INSIGHT: table.insight}


def mostly_in(table: ExploreOneTable) -> str:
    """這一種地點的「多半」兩個字，照它的表算（沒有危險度、不看誰站在那裡）：序章裡沒有比重可看時輿圖名字旁的退路
    （平常是 Game.map_mostly 照每一處自己的比重，tail_of）。"""
    return mostly_of(table_weights(table))


def hint_in(table: ExploreOneTable) -> str:
    """這一種地點的小字，照它的表算（沒有危險度）：玩法說明列六張表的樣子、沒有比重可看時的退路。"""
    return PLACE_WORDS[table.kind] + mostly_in(table)


def named_hint(table: ExploreOneTable) -> str:
    """玩法說明列表時一張表的寫法：表的名字加「多半」兩個字（「官署多事」「河畔多料」）；表沒寫名字照 `hint_in`。"""
    return table.name + mostly_in(table) if table.name else hint_in(table)


def tail_of(how: str | None, weights: Mapping[str, float]) -> str:
    """小字的最後兩個字（輿圖第一層名字旁就是它，2f，FB-886）：接了這裡的討伐懸賞「有賞」、自家營寨「比劃」，其餘是這一處此刻比重最大的
    那一類（`mostly_of`）。`hint_of` 就是在它前面接地點種類的字，所以名字旁永遠是鈕上小字的最後兩個字。"""
    if how == "bounty":
        return BOUNTY_WORD
    if how == "spar":
        return SPAR_WORD
    return mostly_of(weights)


def hint_of(kind: str, how: str | None, weights: Mapping[str, float]) -> str:
    """鈕上括號裡最後那一段與四格探索那一格的小字：接了這裡的討伐懸賞「野外有賞」、自家營寨「同袍比劃」，其餘是地點種類的字加上這一處此刻
    比重最大的那一類（`mostly_of`）。weights 就是擲骰用的那一份（`weights()` 再扣掉做不到的——沒有對手遭遇是 0、抽不到事件、悟不出感悟），
    所以行動列底下那一行寫「多半遇事」，這裡就是「…多事」：長社的官軍遭遇是 0 不寫「野外多敵」（FB-832）、寺的事件比感悟重寫「寺裡多事」、
    危險的山遭遇追過素材寫「山裡多敵」（2e，FB-882）。最後兩個字是 `tail_of`（輿圖名字旁，2f）。"""
    return SPAR_HINT if how == "spar" else PLACE_WORDS[kind] + tail_of(how, weights)


BEAT_WORDS = {EVENT: "遇事", ENCOUNTER: "遇敵", MATERIAL: "得料", INSIGHT: "有悟"}  # 一類事寫成兩個字（紀錄的結果標記、行動列底下那一行）
TRAVELER = "旅人"  # 野類地點的事件偏這個標籤的事件（救助旅人那一類；content.check_explore_one 驗至少三則、都在野類地點）


def items_of(lines: list[str], prefix: str) -> str:
    """素材那幾句「獲得 精鐵砂 ×1」去掉開頭（materials.GRANT_PREFIX）、同一種的數量加起來、用頓號接起來：「精鐵砂 ×2、獸皮 ×1」；
    一句都沒有是空字串。不是「名字 ×數量」寫法的照原樣列。"""
    return "、".join(merge_items(line.removeprefix(prefix) for line in lines if line.startswith(prefix)))


def is_item(text: str) -> bool:
    """「精鐵砂 ×1」「驚羽 ×1（拾遺囊）」這種一樣東西的寫法（materials.item_text，後面可以接來源）。「獲得」開頭的敘事裡，
    破境丹、回體丹那一句（「【破境丹】一枚——衝擊絕學時可以服下…」）是說明，不是一樣東西：得失那一行只列它後面的「破境丹 +1」（FB-831）。"""
    name, sep, count = text.partition(" ×")
    return bool(name) and bool(sep) and count[:1].isdigit()


def merge_items(items: Iterable[str]) -> list[str]:
    """「精鐵砂 ×1」這種同一種的加總（照第一次出現的順序）；不是這種寫法的照原樣留著。"""
    counts: dict[str, int] = {}
    order: list[str] = []
    for item in items:
        name, sep, count = item.rpartition(" ×")
        if sep and count.isdigit():
            if name not in counts:
                order.append(name)
            counts[name] = counts.get(name, 0) + int(count)
        else:
            order.append(item)
    return [f"{key} ×{counts[key]}" if key in counts else key for key in order]

# content/outing_lines.json 的組與鍵（content.check_outing_lines 驗）；句子裡可以寫 {place} 地點、{foe} 對手、{item} 素材
LINE_KEYS: dict[str, tuple[str, ...]] = {
    "open": (TOWN, TEMPLE, FORD, WILD, HILL, CAMP),  # 出門那一句，照這一處是哪一種地點
    "material": ("found",),  # 素材拍撿到東西（item 是「精鐵砂 ×1」這種）
    # 遭遇拍：打贏、僵持、落敗；城裡的地痞（town_*，也有贏、平手、落敗，FB-819）；自家營寨跟同袍比劃（spar）；頭目擋路（boss，接著就是頭目戰）
    "encounter": ("win", "draw", "lose", "town_win", "town_draw", "town_lose", "spar", "boss"),
    "event": ("lead",),  # 事件拍：接在事件卡前面那一句
    "insight": ("lead",),  # 感悟拍：接在有所感前面那一句
    # 結尾：疲勞打了折（tired）、對手配不上你（outlevel）、境界已到經驗換心得（capped）、這一趟沒收穫補一個一階（empty）
    "close": ("tired", "outlevel", "capped", "empty"),
}
SAMPLE = {"place": "潁水河畔", "foe": "河灘潑皮", "item": "精鐵砂 ×1"}  # 驗句子填不填得進去用的（content.check_outing_lines）
# 內容沒有 outing_lines.json 時的退路（測試內容）：每一個鍵一句
FALLBACK: dict[str, dict[str, list[str]]] = {
    "open": {k: ["你出了門，往{place}一帶走了一趟。"] for k in LINE_KEYS["open"]},
    "material": {"found": ["路上撿了{item}。"]},
    "encounter": {
        "win": ["半路撞上{foe}，你佔了上風。"], "draw": ["半路撞上{foe}，相持不下。"], "lose": ["半路撞上{foe}，你吃了虧。"],
        "town_win": ["街角的{foe}找碴，被你打發了。"], "town_draw": ["街角的{foe}纏著你，推搡了一陣，誰也沒占到便宜。"],
        "town_lose": ["街角的{foe}找碴，你吃了點虧。"],
        "spar": ["營裡的{foe}拉你比劃了幾手。"], "boss": ["前頭有人擋住去路，是{foe}。"],
    },
    "event": {"lead": ["走著走著，碰上一樁事。"]},
    "insight": {"lead": ["走著走著，忽然心有所感。"]},
    "close": {
        "tired": ["今天練得多了，收穫漸少。"], "outlevel": ["這一帶的對手已經配不上你，所得有限。"],
        "capped": ["境界已到，再往上只能打出來。"], "empty": ["一路沒什麼收穫，只在路邊拾了{item}。"],
    },
}


def line(lines: Mapping[str, Mapping[str, list[str]]], group: str, key: str, rng: random.Random, **slots: str) -> str:
    """段落的一句：outing_lines（Content.outing_lines）那一組那一個鍵挑一句（沒寫照 FALLBACK），填上 slots（沒給的填空字串）。擲一次 rng。"""
    pool = (lines.get(group) or {}).get(key) or FALLBACK[group][key]
    filled = {name: "" for name in SAMPLE} | slots
    return rng.choice(pool).format(**filled)


def ledger(gains: list[str], losses: list[str]) -> str:
    """段落最後那一行「得：精鐵砂 ×1、銀兩 +5　失：氣血 -12」：兩樣都沒有是空字串，只有一樣只寫那一樣。"""
    parts = ([f"得：{'、'.join(gains)}"] if gains else []) + ([f"失：{'、'.join(losses)}"] if losses else [])
    return "　".join(parts)
