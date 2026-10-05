"""修練（武學與成長設計 3.5、3.6）：融過意境的武學，用它融的那個意境反覆修練衝品質。

每修練一次擲一次能不能升一品；失敗了熟練度 +1、下一次機會更高，加到 100% 就必成（Config.cultivate_odds）。
品質是每個人各練各的（PlayerState.art_quality），熟練度記在 PlayerState.art_mastery；升品時「成」不變。
第一個把某門武學修到絕學的人替全服取正式名字：功法 id 不變，只改顯示的名字（world.rename_skill）——
所以這裡凡是「認東西」的都用 id（art_id），凡是寫給玩家看的都用 resolve_art 回來的 art.name（改名之後兩者不一樣）。
只改狀態與回傳訊息；要不要寫江湖紀錄由 engine 決定（只有真的擲了骰、或真的定了名才寫）。
"""
from __future__ import annotations

import random

from . import insights, library, naming, team
from .martial_arts import next_quality
from .models import Content
from .rules import add_chronicle
from .state import GameState
from .world_state import WorldStateStore


def chance(content: Content, target_quality: str, failures: int) -> int:
    """升到 target_quality 的機率（%）：第一次的機率＋每失敗一次加的量，最多 100。"""
    first, step = content.config.cultivate_odds[target_quality]
    return min(100, first + step * failures)


def cultivate_problem(state: GameState, content: Content, world: WorldStateStore, art_id: str) -> str | None:
    """不能修練的原因；None＝可以。"""
    art = team.resolve_art(art_id, content, world)
    if art is None or art_id not in library.owned_arts(state):
        return "你沒有這門武學。"
    if art.insight is None:
        return "這門武學沒有融過意境，沒辦法修練——先拿它去「煉製」融一個意境。"
    if art.insight not in state.player.insights:
        insight = insights.resolve(art.insight, content, world)
        return f"修練要用「{insight.name if insight else art.insight}」，你已經把它熔掉了。"
    target = next_quality(team.art_quality(state, art))
    if target is None:
        return "已經是絕學，修無可修。"
    if target == "絕學" and state.player.naming is not None:
        # 取名的權利一人一次只留一門（PlayerState.naming）；再衝一門絕學會把它蓋掉，那門就永遠沒有人替它定名
        pending = team.resolve_art(state.player.naming, content, world)
        return f"你練成絕學的【{pending.name if pending else state.player.naming}】還沒定名，先替它取好正式的名字。"
    cost = content.config.cultivate_stamina
    if state.player.stamina < cost:
        return f"體力不足：修練一次要 {cost}。"
    return None


def cultivate(
    state: GameState, content: Content, world: WorldStateStore, art_id: str, rng: random.Random,
) -> list[str]:
    """修練一次：花體力，擲一次能不能升一品。被拒絕時只回原因（什麼都不扣、不動）。"""
    problem = cultivate_problem(state, content, world, art_id)
    if problem is not None:
        return [problem]
    p = state.player
    art = team.resolve_art(art_id, content, world)
    quality = team.art_quality(state, art)
    target = next_quality(quality)
    failures = p.art_mastery.get(art_id, 0)
    p.stamina -= content.config.cultivate_stamina
    if rng.random() * 100 < chance(content, target, failures):
        p.art_quality[art_id] = target
        p.art_mastery.pop(art_id, None)
        msgs = [f"【{art.name}】修練有成，從{quality}晉為{target}！"]
        if target == "絕學":
            msgs += _mastered(state, world, art_id)
        return msgs
    p.art_mastery[art_id] = failures + 1
    return [
        f"【{art.name}】修練了一回，還差一點火候（熟練度 {failures + 1}，"
        f"下一次約 {chance(content, target, failures + 1)}% 的機會晉為{target}）。"
    ]


def _mastered(state: GameState, world: WorldStateStore, art_id: str) -> list[str]:
    """練成絕學的那一刻：全服第一個的人拿到取名的權利（claim_master 是原子的，同時練成的兩個人只有先登記的算數）。"""
    if world.claim_master(art_id, state.player.name):
        state.player.naming = art_id
        return ["你是江湖上第一個把這門武學練成絕學的人——到「修練」頁替它取一個正式的名字吧。"]
    return [f"這門武學已由{world.master_of(art_id)}率先練成絕學。"]


def name_mastered(state: GameState, content: Content, world: WorldStateStore, name: str) -> list[str]:
    """第一個練成絕學的人替全服取正式名字；全服的這門一起改名，江湖史記上一筆。
    不合格（過不了命名過濾、被用掉）時什麼都不動，取名的權利還在，可以換個名字再來。"""
    art_id = state.player.naming
    if art_id is None:
        return ["（沒有等著你取名的武學。）"]
    old = team.resolve_art(art_id, content, world)
    if old is None:
        return ["找不到這門武學的資料，沒辦法定名。"]
    name = naming.clean_name(name)
    problem = naming.name_problem(name, content)
    if problem is not None:
        return [f"這個名字不行：{problem}。"]
    if not world.rename_skill(art_id, name):  # 原子判斷：武學、改過的名字、意境都不能撞名
        return [f"【{name}】已經有人用了，換一個吧。"]
    state.player.naming = None
    add_chronicle(state, f"{state.player.name}把【{old.name}】練成絕學，為之定名【{name}】。")
    return [f"從今以後，江湖上這門武學就叫【{name}】。"]
