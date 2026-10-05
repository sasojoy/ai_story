"""意境（武學與成長設計 3.2）：基本意境（風火水山、浩然、血煞）在 content/insights.json，
合併出來的存在全服（world.get_insight）。玩家悟得的記在 PlayerState.insights——只記 id、永久學會，
合成、修練、合併都不會用掉。這個模組管查、悟、探索悟哪一個、合併的屬性與正邪；合併本身在 fusion.py。
"""
from __future__ import annotations

import hashlib
import random

from .martial_arts import Insight
from .models import Content, Location
from .state import GameState
from .world_state import WorldStateStore

# 第一層合併長出另外四個屬性（設計 3.2.1）。照屬性寫、不照意境 id：基本意境火、風、水、山的屬性剛好是
# 剛、快、柔、慢，程式就不必綁死內容的 id。
PAIR_ATTRIBUTES: dict[frozenset[str], str] = {
    frozenset({"剛", "快"}): "陽",
    frozenset({"柔", "慢"}): "陰",
    frozenset({"快", "柔"}): "虛",
    frozenset({"剛", "慢"}): "實",
}


def resolve(insight_id: str | None, content: Content, world: WorldStateStore) -> Insight | None:
    """基本意境（content/insights.json）或全服合併出來的意境；都找不到是 None。"""
    if insight_id is None:
        return None
    d = content.insights.get(insight_id)
    if d is not None:
        return Insight(id=d.id, name=d.name, attribute=d.attribute, lean=d.lean, note=d.desc)
    return world.get_insight(insight_id)


def learn(state: GameState, content: Content, world: WorldStateStore, insight_id: str | None) -> list[str]:
    """悟得一個意境（探索、奇遇、名聲）。已經會的化成心得（設計 3.2.2）。上限不擋：超過上限的人照樣悟得，
    只是在熔回上限以內之前不能合成、合併（設計 4.5）。"""
    insight = resolve(insight_id, content, world)
    if insight is None:
        return []
    p = state.player
    if insight.id in p.insights:
        amount = content.config.duplicate_insight_xinde
        p.stats["xinde"] = p.stats.get("xinde", 0) + amount
        return [f"你又悟到一次「{insight.name}」，這份體會化成了心得。", f"心得 +{amount}"]
    p.insights.append(insight.id)
    return [f"你悟得了「{insight.name}」的意境（屬{insight.attribute}）！"]


def grant_by_name(state: GameState, content: Content, world: WorldStateStore) -> list[str]:
    """名聲第一次到門檻就悟得對應的意境（浩然、血煞，武學與成長設計 7.2）。給過就記旗標 `悟得:<id>`：
    之後熔掉也不會再給（不然熔了又拿、拿了又熔可以刷心得）。旗標跟著角色走，換季跟角色一起重來。"""
    p = state.player
    msgs: list[str] = []
    for d in content.insights.values():
        if d.grant is None:
            continue
        flag = f"悟得:{d.id}"
        if flag in p.flags or p.stats.get(d.grant.stat, 0) < d.grant.at:
            continue
        p.flags.add(flag)
        msgs.append(f"你心有所感，胸中多了一股{d.name}之氣。")
        msgs += learn(state, content, world, d.id)
    return msgs


def explore_pool(loc: Location, content: Content) -> list[str]:
    """在這裡探索悟得到的意境：地點寫了 insights 就是那幾個；沒寫的給靠探索悟的基本意境（內容不必每個地點都填）。
    靠名聲才悟得的（浩然、血煞）永遠不在這裡。"""
    by_exploring = [i for i, d in content.insights.items() if d.grant is None]
    return [i for i in loc.insights if i in by_exploring] or by_exploring


def roll_explore(loc: Location, content: Content, rng: random.Random) -> str | None:
    pool = explore_pool(loc, content)
    return rng.choice(pool) if pool else None


def merge_key(a: str, b: str) -> str:
    """合併的配方鍵：兩個意境 id 排序後接起來（A＋B 與 B＋A 是同一個配方；自己跟自己也可以）。"""
    return "+".join(sorted((a, b)))


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
