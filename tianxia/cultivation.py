"""修練（武學與成長設計 3.5、3.6）：融過意境的武學，用它融的那個意境反覆修練衝品質。

每修練一次擲一次能不能升一品；失敗了熟練度 +1、下一次機會更高（Config.cultivate_odds）：下品→中品、中品→上品加到 100% 就必成，
上品→絕學沒有保底，累積的機會最多到 Config.cultivate_cap（預設 50%），剩下靠破境丹——探索偶爾撿到的傳奇道具，
由玩家自己決定哪一次衝絕學要服（修練頁勾「服下破境丹」）：服的那一次多 Config.legend_item_bonus%，成不成都用掉一枚；
被拒絕的修練（體力不足、沒有意境、還有絕學等著取名……）不擲骰，丹也不動（企劃者 2026-10-05）。
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


def chance(
    content: Content, target_quality: str, failures: int, boost: int = 0, *, wis: float = team.BASE_STAT,
) -> int:
    """升到 target_quality 的機率（%）：第一次的機率＋每失敗一次加的量，乘上悟性的加成（×（1＋3%×（悟性−5）），
    武學與成長設計 6.1），最多到這一階的上限（Config.cultivate_cap，沒寫的那一階是 100）；再加上 boost
    （破境丹，見 boost_for），總和最多 100。悟性在上限之內、丹在上限之上（計畫二 G2）：上限是企劃者訂的天花板，
    丹才是越過它的那一招。寫明會必成的那一次（沒乘悟性就到 100、這一階也沒有上限）悟性再低照樣必成。"""
    first, step = content.config.cultivate_odds[target_quality]
    cap = content.config.cultivate_cap.get(target_quality, 100)
    raw = first + step * failures
    if raw >= 100 and cap >= 100:
        base = 100
    else:
        base = min(cap, round(raw * team.stat_factor(content, wis)))
    return min(100, base + boost)


def odds_for(state: GameState, content: Content, target_quality: str, failures: int, boost: int = 0) -> int:
    """這個玩家這一次的機率：chance 帶上自己的悟性。擲骰、「下一次約 N%」與修練頁寫的都用它，頁面上寫的就是實際擲的。"""
    return chance(content, target_quality, failures, boost, wis=state.player.stats.get("wis", team.BASE_STAT))


def boost_for(state: GameState, content: Content, target_quality: str, use_legend: bool = False) -> int:
    """這一次衝 target_quality 的加成（%）：玩家勾了服破境丹、衝的是絕學、手上也還有丹才有。要不要算丹全由這裡決定：
    擲骰與修練頁寫的加成機率都用它，頁面上寫的就是實際擲的。"""
    if use_legend and target_quality == "絕學" and state.player.legend_items > 0:
        return content.config.legend_item_bonus
    return 0


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
    use_legend: bool = False,
) -> list[str]:
    """修練一次：花體力，擲一次能不能升一品。被拒絕時只回原因（什麼都不扣、不動，破境丹也留著）。
    use_legend：玩家勾了「服下破境丹」。衝絕學、手上有丹才真的服（這一次的機率多一份加成，成不成都用掉一枚）；
    頁面過期了（丹已經沒有、下一步不是絕學）不拒絕這次修練，照一般的機率擲，多回一句話說這一回沒服。"""
    problem = cultivate_problem(state, content, world, art_id)
    if problem is not None:
        return [problem]
    p = state.player
    art = team.resolve_art(art_id, content, world)
    quality = team.art_quality(state, art)
    target = next_quality(quality)
    failures = p.art_mastery.get(art_id, 0)
    cost = content.config.cultivate_stamina
    p.stamina -= cost
    # 花的體力寫在擲骰那一句後面，跟合併的回話（fusion.merge）同一種寫法（FB-070）；江湖紀錄的數值變化另由 engine 照實際扣的算
    tired = f"體力 -{cost}"
    pill = content.config.legend_item_name
    boost = boost_for(state, content, target, use_legend)
    msgs: list[str] = []
    if boost:
        p.legend_items -= 1
        msgs.append(f"你服下一枚【{pill}】，心神一片澄明。")
    elif use_legend:
        if target != "絕學":
            msgs.append(f"{pill}只在衝擊絕學時用得上，這一回沒服。")
        else:
            msgs.append(f"你身上已經沒有{pill}了，這一回沒服。")
    if rng.random() * 100 < odds_for(state, content, target, failures, boost):
        p.art_quality[art_id] = target
        p.art_mastery.pop(art_id, None)
        msgs += [f"【{art.name}】修練有成，從{quality}晉為{target}！", tired]
        if target == "絕學":
            msgs += _mastered(state, world, art_id)
        return msgs
    p.art_mastery[art_id] = failures + 1
    hint = ""
    if target == "絕學" and p.legend_items > 0:  # 下一次要不要服由玩家決定；這裡只提醒還握著一枚
        hint = f"，服下{pill}可再 +{content.config.legend_item_bonus}%"
    msgs += [
        f"【{art.name}】修練了一回，還差一點火候（熟練度 {failures + 1}，"
        f"下一次約 {odds_for(state, content, target, failures + 1)}% 的機會晉為{target}{hint}）。",
        tired,
    ]
    return msgs


def _mastered(state: GameState, world: WorldStateStore, art_id: str) -> list[str]:
    """練成絕學的那一刻：全服第一個的人拿到取名的權利（claim_master 是原子的，同時練成的兩個人只有先登記的算數）。
    登記的是名號，後到的人看到的、換季的江湖史寫的也是名號（傳聞分層第七節：江湖史一律具名；這一版之前匿名記下的
    master_shown 照舊）。"""
    if world.claim_master(art_id, state.player.name):
        state.player.naming = art_id
        return ["你是江湖上第一個把這門武學練成絕學的人——到「修練」頁替它取一個正式的名字吧。"]
    art = world.get_skill(art_id)
    first = (art.master_shown if art is not None else None) or world.master_of(art_id)  # 舊資料沒記，照名號
    return [f"這門武學已由{first}率先練成絕學。"]


def master_request(state: GameState, content: Content, world: WorldStateStore) -> naming.NamingRequest | None:
    """定名的 A 段（鎖內、只讀）：輪到自己替練成絕學的武學取正式名字時，開一張請模型另取新名字的單（伺服器假人用，
    企劃者 2026-10-06：沿用原名的話江湖史同一個名字出現兩次，看得出是假人；真人自己填名字，不走這裡）。
    沒有等著定名的、或找不到那一門，是 None。"""
    art_id = state.player.naming
    art = team.resolve_art(art_id, content, world) if art_id is not None else None
    if art is None:
        return None
    note = f"——{art.note}" if art.note else ""
    messages = [
        {"role": "system", "content": naming.SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"一門{art.kind}【{art.name}】（屬{art.attribute}）{note}\n"
            f"有人把它練成了絕學，要替它取一個正式的新名字：跟原名【{art.name}】不一樣，聽得出是同一門功夫練到了極致。\n\n"
            f"{naming.FORMAT_RULES}"
        )},
    ]
    return naming.NamingRequest("master", f"定名|{art_id}", art.kind, messages)


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
    # FB-069：也不能取成江湖上任何角色的名號（真人、假人一樣、不分大小寫），回的話看不出是不是假人
    problem = naming.name_problem(name, content, world.is_character_name)
    if problem is not None:
        return [f"這個名字不行：{problem}。"]
    # 沿用目前的名字（模型取的就很好）也算定名，只是名字不動；其他名字原子判斷：武學、改過的名字、意境都不能撞名
    if name != old.name and not world.rename_skill(art_id, name):
        return [f"【{name}】已經有人用了，換一個吧。"]
    state.player.naming = None
    add_chronicle(state, f"{state.player.name}把【{old.name}】練成絕學，為之定名【{name}】。")  # 江湖史一律寫名號（傳聞分層第七節）
    return [f"從今以後，江湖上這門武學就叫【{name}】。"]
