"""意境（武學與成長設計 3.2）：基本意境（風火水山、浩然、血煞）在 content/insights.json，
合併出來的存在全服（world.get_insight）。玩家悟得的記在 PlayerState.insights——只記 id、永久學會，
合成、修練、合併都不會用掉。這個模組管查、悟、探索悟哪一個、合併的屬性與正邪；合併本身在 fusion.py。
"""
from __future__ import annotations

import hashlib
import random

from . import insight_fx
from .martial_arts import Insight
from .models import Content, InsightScene, Location
from .state import GameState
from .world_state import WorldStateStore

SENSE_ATTRIBUTES = ("剛", "柔", "快", "慢")  # 有所感的做法與畫出來的那一筆只分這四種（基本意境風火水山的屬性）
OWN_PREFIX = "悟:"  # 私有意境的 id 開頭（悟意境設計 0.2b）：「悟:3」是這個人自己第 3 個；內容與全服的意境 id 都不會這樣開頭


def is_own(insight_id: str | None) -> bool:
    """這個意境 id 是不是某個人私有的（畫圖悟來的、或拿私有的合併出來的）。"""
    return bool(insight_id) and insight_id.startswith(OWN_PREFIX)

# 第一層合併長出另外四個屬性（設計 3.2.1）。照屬性寫、不照意境 id：基本意境火、風、水、山的屬性剛好是
# 剛、快、柔、慢，程式就不必綁死內容的 id。
PAIR_ATTRIBUTES: dict[frozenset[str], str] = {
    frozenset({"剛", "快"}): "陽",
    frozenset({"柔", "慢"}): "陰",
    frozenset({"快", "柔"}): "虛",
    frozenset({"剛", "慢"}): "實",
}


def resolve(
    insight_id: str | None, content: Content, world: WorldStateStore, state: GameState | None = None,
) -> Insight | None:
    """查一個意境：內容寫死的 → 這個玩家自己的（state 給了才查，悟意境設計 0.2b）→ 全服合併出來的；都找不到是 None。
    私有的 id 只在悟的人自己的存檔裡：沒給 state（或給的是別人的）就找不到。"""
    if insight_id is None:
        return None
    base = insight_fx.base_id(insight_id)  # 第二份起「feng~2」：照那一種查，id 換成這一份的（意境效果池）
    d = content.insights.get(base)
    if d is not None:
        return Insight(id=insight_id, name=d.name, attribute=d.attribute, lean=d.lean, note=d.desc)
    if is_own(insight_id):
        return state.player.own_insights.get(insight_id) if state is not None else None
    got = world.get_insight(base)
    return got if got is None or base == insight_id else got.model_copy(update={"id": insight_id})


def art_attribute(art, content: Content, world: WorldStateStore, state: GameState | None = None) -> str | None:
    """這門武學修練要的意境屬性：記了 insight_attr 的照它；舊的（悟意境之前登記的）照它融的那個意境查；都沒有是 None。"""
    if getattr(art, "insight_attr", None):
        return art.insight_attr
    found = resolve(art.insight, content, world, state) if art.insight else None
    return found.attribute if found is not None else None


def for_cultivation(state: GameState, content: Content, world: WorldStateStore, art) -> Insight | None:
    """修練這門武學拿哪一個意境（悟意境設計 0.2b）：它融的那一個還在手上就是它；不然（融的是私有意境——全服登記不記私有的 id，
    或者那一個已經熔掉）拿手上同屬性的一個：先挑自己悟的、再照悟到的先後。沒有融過意境、手上也沒有同屬性的是 None。"""
    held = state.player.insights
    if art.insight and art.insight in held:
        return resolve(art.insight, content, world, state)
    attribute = art_attribute(art, content, world, state)
    if attribute is None:
        return None
    found = [i for i in (resolve(x, content, world, state) for x in held) if i is not None and i.attribute == attribute]
    found.sort(key=lambda i: not is_own(i.id))
    return found[0] if found else None


def strong_of(loc: Location | None, content: Content) -> str | None:
    """這一處最濃的意境 id（意境提示設計第一節）：開關關著、沒有地點、沒寫、或寫的已經悟不到（內容驗過，保險）都是 None。
    最濃的好處都問這一個：感悟擲中的門檻（sensing.rate）、悟到時的心得與那一句（learn）、輿圖的底圖（mapdata.base）。"""
    if loc is None or not content.config.insight_strong.enabled or loc.insight_strong is None:
        return None
    return loc.insight_strong if loc.insight_strong in explore_gives(loc, content) else None


def learn(
    state: GameState, content: Content, world: WorldStateStore, insight_id: str | None, at: Location | None = None,
) -> list[str]:
    """悟得一個意境（探索、奇遇、名聲）。已經會的化成心得（設計 3.2.2）。上限不擋：超過上限的人照樣悟得，
    只是在熔回上限以內之前不能合成、合併（設計 4.5）。at 是在哪裡悟的（探索才給）：悟到的正是那裡最濃的一種，
    前面多一句它的 strong_line、已經會的化成 Config.insight_strong.duplicate_xinde（意境提示設計第二節）。"""
    insight = resolve(insight_id, content, world, state)
    if insight is None:
        return []
    p = state.player
    strong = strong_of(at, content) == insight.id
    d = content.insights.get(insight.id)
    lead = [d.strong_line] if strong and d is not None and d.strong_line else []
    if insight_fx.pieces(state, insight.id):
        if not is_own(insight.id) and insight_fx.room_for(state, content, insight.id):  # 意境效果池：再悟到一次是另一份，自己的品質與效果（揣摩要兩份）
            piece = insight_fx.new_piece_id(state, insight.id)
            p.insights.append(piece)
            fx = insight_fx.roll(state, content, world, piece, strong=strong)
            return lead + [AGAIN.format(name=insight.name, quality=fx.quality, label=insight_fx.label(content, fx))]
        amount = content.config.insight_strong.duplicate_xinde if strong else content.config.duplicate_insight_xinde
        p.stats["xinde"] = p.stats.get("xinde", 0) + amount
        return lead + [f"你又悟到一次「{insight.name}」，這份體會化成了心得。", f"心得 +{amount}"]
    p.insights.append(insight.id)
    fx = insight_fx.roll(state, content, world, insight.id, strong=strong)
    return lead + [f"你悟得了「{insight.name}」的意境（屬{insight.attribute}）！", FX_LINE.format(quality=fx.quality, label=insight_fx.label(content, fx))]


AGAIN = "你又悟得一份「{name}」（{quality}・{label}）。"  # 待 joy 潤
FX_LINE = "這一份是{quality}：{label}。"  # 待 joy 潤


GRANT_LINES = {"good": "你行俠日久，胸中多了一股{name}之氣。", "evil": "你橫行日久，胸中多了一股{name}之氣。"}  # 名聲 5.1，待 joy 潤
GRANT_LINE = "你心有所感，胸中多了一股{name}之氣。"


def grant_by_name(state: GameState, content: Content, world: WorldStateStore) -> list[str]:
    """名聲第一次到門檻就悟得對應的意境（浩然、血煞，武學與成長設計 7.2）。給過就記旗標 `悟得:<id>`：
    之後熔掉也不會再給（不然熔了又拿、拿了又熔可以刷心得）。旗標跟著角色走，換季跟角色一起重來。
    名聲的 virtue_insight 開著時（名聲設計 5.1）還要走對那條路：浩然要善名不低於惡名（俠）、血煞要惡名高過善名（寇）；
    門檻照內容寫的（15），不乘季長倍數；那一句寫原因（GRANT_LINES）。"""
    from . import renown  # noqa: PLC0415  renown 不 import insights；放在函式裡免得 insights 的 import 鏈多一段

    p = state.player
    by_path = renown.on(content, "virtue_insight")
    good, evil = p.stats.get("good", 0), p.stats.get("evil", 0)
    msgs: list[str] = []
    for d in content.insights.values():
        if d.grant is None:
            continue
        flag = f"悟得:{d.id}"
        if flag in p.flags or p.stats.get(d.grant.stat, 0) < d.grant.at:
            continue
        if by_path and (d.grant.stat == "good" and good < evil or d.grant.stat == "evil" and evil <= good):
            continue
        p.flags.add(flag)
        msgs.append((GRANT_LINES.get(d.grant.stat, GRANT_LINE) if by_path else GRANT_LINE).format(name=d.name))
        msgs += learn(state, content, world, d.id)
    return msgs


def explore_pool(loc: Location, content: Content) -> list[str]:
    """在這裡探索悟得到的意境：地點寫了 insights 就是那幾個；沒寫的給靠探索悟的基本意境（內容不必每個地點都填）。
    靠名聲才悟得的（浩然、血煞）永遠不在這裡。"""
    by_exploring = [i for i, d in content.insights.items() if d.grant is None]
    return [i for i in loc.insights if i in by_exploring] or by_exploring


def explore_gives(loc: Location, content: Content) -> list[str]:
    """探索在這裡真的悟得到的意境（W3）：輿圖詳情欄的「這裡能悟」與探索自己（Game._explore_can）共用這一個判斷，所以那一行
    永遠不會說探索給不出的東西。這類地點探索時「悟意境」那一支的比例是 0（Config.explore_mix 照地點類型挑，跟探索同一個
    explore_mix_of），那就什麼也悟不到；否則就是 explore_pool。"""
    if content.config.explore_mix_of(loc.tags).weights.get("insight", 0) <= 0:
        return []
    return explore_pool(loc, content)


def scenes_for(loc: Location, content: Content) -> list[InsightScene]:
    """這一處有所感時挑得到的場景（序章的不算）：寫了這個地點的那幾段；沒有就是標籤對得上的；再沒有就是通用的（tags、locations 都空）。"""
    scenes = [scene for scene in content.insight_scenes.values() if not scene.prologue]
    tags = set(loc.tags)
    return (
        [scene for scene in scenes if loc.id in scene.locations]
        or [scene for scene in scenes if not scene.locations and tags & set(scene.tags)]
        or [scene for scene in scenes if not scene.locations and not scene.tags]
    )


def pool_attributes(loc: Location, content: Content) -> set[str]:
    """這一處悟得到的意境的屬性：做法的屬性在這裡面就是選對（悟意境設計 4.1，地點的池子就是答案）。"""
    return {content.insights[i].attribute for i in explore_pool(loc, content)}


def base_of(attribute: str, loc: Location, content: Content) -> str | None:
    """這一處悟得到、屬性是 attribute 的那個基本意境（畫出來結合的屬性剛好是這裡的，就是悟到它）；沒有是 None。"""
    return next((i for i in explore_pool(loc, content) if content.insights[i].attribute == attribute), None)


def roll_explore(loc: Location, content: Content, rng: random.Random) -> str | None:
    pool = explore_pool(loc, content)
    return rng.choice(pool) if pool else None


def merge_key(a: str, b: str) -> str:
    """合併的配方鍵：兩個意境 id 排序後接起來（A＋B 與 B＋A 是同一個配方；自己跟自己也可以）。"""
    return "+".join(sorted((insight_fx.base_id(a), insight_fx.base_id(b))))  # 第二份起照那一種（同一個配方）


def merged_attribute(a, b, seed: str) -> str:
    """合出來的屬性（設計 3.2.1）：同屬性就是那個；剛快、柔慢、快柔、剛慢照 PAIR_ATTRIBUTES；其他組合從兩個來源裡挑一個，
    由配方種子（f"{天機}|{配方鍵}"）的雜湊決定（設計 12.6：原本用新名字，改成配方，才能在取名之前知道屬性、
    找合到舊的候選）。跟參數順序無關。a、b 只要有 id 與 attribute：意境合併、武學＋武學（12.3）共用。"""
    if a.attribute == b.attribute:
        return a.attribute
    pair = PAIR_ATTRIBUTES.get(frozenset({a.attribute, b.attribute}))
    if pair is not None:
        return pair
    first, second = sorted((a, b), key=lambda thing: thing.id)
    return (first, second)[hashlib.sha256(seed.encode("utf-8")).digest()[0] % 2].attribute


def merged_lean(a, b) -> str:
    """正邪跟著傳（設計 7.3）：正＋無＝正、邪＋無＝邪、同向不變；正＋邪互相抵銷成無。意境與武學共用（12.3）。"""
    leans = {a.lean, b.lean} - {"無"}
    return leans.pop() if len(leans) == 1 else "無"
