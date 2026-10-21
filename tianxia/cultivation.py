"""修練（武學重構，Joy 2026-10-20）：品級不再靠修練衝——合成（fusion.blend_grade）與自創才長品級。
修練頁的「修練」只剩最後一步：上品練到第十成，就等契機晉為絕學（seize：打贏一場硬仗、在決戰裡出手滿幾回合，
擲一次頓悟），或服一枚破境丹關起門來強行衝關（cultivate(use_legend=True)，force_odds）。
心得換丹、心得衝關都拿掉了（Joy 2026-10-21「把破境丹也加入商城，取消可以用心得衝」）：丹從探索、打點、銀兩與萬寶閣來。
品質是每個人各練各的（PlayerState.art_quality）；升品時「成」不變。
練成絕學走 tianxia/ascend.py（破境：招升為絕招、破境卡、江湖史、傳聞）。「第一個練成的人替全服定名」退掉了（招式與絕學稿案
第二輪）；這一版之前還等著定名的（PlayerState.naming）照舊定得了名（master_request、name_mastered）。
只改狀態與回傳訊息；要不要寫江湖紀錄由 engine 決定（只有真的擲了骰、或真的定了名才寫）。
"""
from __future__ import annotations

import random

from . import arts as arts_mod, ascend as ascend_mod, library, naming, silver, team, treasures
from .martial_arts import MAX_LEVEL, next_quality
from .models import Content
from .rules import add_chronicle
from .state import GameState
from .world_state import WorldStateStore

NO_RANK_LINE = "品級不靠修練：合成或自創才長品級。練到第十成的上品，等一場硬仗的契機，或服一枚破境丹，便能晉為絕學。"  # 待 joy 潤
CHANCE_LINE = "【{name}】已到上品的極處，剩下那一步不在練功房裡——打一場硬仗等契機，或服一枚{pill}強行衝關。"  # 待 joy 潤
NOT_RIPE_LINE = "【{name}】還沒到極處：練到第十成，才談得上絕學（現在第{level}成）。"  # 待 joy 潤


def ready(state: GameState, content: Content, world: WorldStateStore, art_id: str) -> tuple[bool, str | None]:
    """這一門到了衝絕學的門檻沒：上品、第十成（寫死的武學不衝）。回（到了沒, 沒到的原因）。
    評分不是門檻（Joy 2026-10-20「武學衝絕品跟評分無關，等契機、破鏡丹、大量心得」）：評分只拿來比高下、排武學榜。"""
    art = team.resolve_art(art_id, content, world)
    if art is None or arts_mod.fixed(content, art_id):
        return False, None
    if next_quality(team.art_quality(state, art)) != "絕學":
        return False, None
    level = library.level_of(state, art_id) or 1
    need = max(content.config.cultivate_min_level.get("絕學", MAX_LEVEL), 1)
    if level < need:
        return False, NOT_RIPE_LINE.format(name=art.name, level=level)
    return True, None


def cultivate_problem(
    state: GameState, content: Content, world: WorldStateStore, art_id: str, gate: bool = True, use_legend: bool = False,
) -> str | None:
    """不能修練的原因；None＝可以（只剩服丹強行衝關這一條路）。gate 留著讓舊呼叫端不改（不看）。"""
    art = team.resolve_art(art_id, content, world)
    if art is None or art_id not in library.owned_arts(state):
        return "你沒有這門武學。"
    target = next_quality(team.art_quality(state, art))
    if target is None:
        return "已經是絕學，修無可修。"
    if target != "絕學" or arts_mod.fixed(content, art_id):
        return NO_RANK_LINE
    if state.player.naming is not None:
        # 取名的權利一人一次只留一門（PlayerState.naming）；再衝一門絕學會把它蓋掉，那門就永遠沒有人替它定名
        pending = team.resolve_art(state.player.naming, content, world)
        return f"你練成絕學的【{pending.name if pending else state.player.naming}】還沒定名，先替它取好正式的名字。"
    ok, why = ready(state, content, world, art_id)
    if not ok:
        return why
    if not (use_legend and state.player.legend_items > 0):
        return CHANCE_LINE.format(name=art.name, pill=content.config.legend_item_name)
    cost = content.config.cultivate_stamina
    if state.player.stamina < cost:
        return f"體力不足：修練一次要 {cost}。"
    return None


def needs_pill(state: GameState, content: Content, world: WorldStateStore, art_id: str) -> bool:
    """到了極處、只差一枚破境丹（手上沒有）：修練頁那一格引去萬寶閣（Joy 2026-10-21「破境丹沒有可以引導他去商城」）。"""
    if state.player.legend_items > 0:
        return False
    art = team.resolve_art(art_id, content, world)
    return art is not None and cultivate_problem(state, content, world, art_id, use_legend=True) == CHANCE_LINE.format(
        name=art.name, pill=content.config.legend_item_name)


def cultivate(
    state: GameState, content: Content, world: WorldStateStore, art_id: str, rng: random.Random,
    use_legend: bool = False, gate: bool = True,
) -> list[str]:
    """修練一次＝服一枚破境丹強行衝絕學（花體力與一枚丹，成不成都用掉）。被拒絕時只回原因（什麼都不扣）。"""
    problem = cultivate_problem(state, content, world, art_id, gate, use_legend)
    if problem is not None:
        return [problem]
    cost = content.config.cultivate_stamina
    state.player.stamina -= cost
    return _force(state, content, world, art_id, rng) + [f"體力 -{cost}"]


def seize(
    state: GameState, content: Content, world: WorldStateStore, ratio: float, rng: random.Random,
) -> list[str]:
    """契機：剛打贏一場難度比（對手難度 ÷ 我方威力，決戰是 Breakthrough.showdown_ratio）ratio 的仗。身上兩門
    （武學先、內功後）裡第一門到了門檻（ready）的，擲一次頓悟（只擲一門，一場仗最多一次）。
    機會＝chance ×（ratio ÷ par_ratio）× 悟性，夾在 1～max_chance。
    難度比不到 min_ratio、契機關著（chance 0）、還有絕學等著定名，都什麼也不做。成了寫「頓悟」與取名的話，沒成只留一句摸到了又滑走。"""
    cfg = content.config
    rule = cfg.breakthrough
    p = state.player
    if rule.chance <= 0 or ratio < rule.min_ratio or p.naming is not None:
        return []
    member = p.member
    for art_id in (member.wugong_id, member.neigong_id):
        if not art_id or not ready(state, content, world, art_id)[0]:
            continue
        art = team.resolve_art(art_id, content, world)
        # 寶物「cultivate」（凝神香囊、檀木念珠）以前乘修練升品，衝品拿掉之後改乘絕學這一步（契機與服丹都乘）
        odds = rule.chance * ratio / rule.par_ratio * team.stat_factor(content, p.stats.get("wis", team.BASE_STAT))
        odds *= treasures.amount(state, content, "cultivate")
        odds += silver.take_mentor(state, content)  # 名師指點（銀兩出口）：衝品拿掉之後加在絕學這一步，擲一次用掉
        if rng.random() * 100 < max(1.0, min(rule.max_chance, odds)):
            return ascend_mod.ascend(state, content, world, art_id, "seize")  # 破境（招式與絕學稿案第三節）
        return [f"打到緊處，【{art.name}】似乎摸到了什麼，轉眼又滑走了。"]
    return []


def force_odds(state: GameState, content: Content, world: WorldStateStore, art_id: str) -> int:
    """不等契機，服一枚破境丹關起門來強行衝關的機會（%）：legend_item_bonus × 悟性，夾在 1～breakthrough.max_chance。"""
    cfg = content.config
    odds = cfg.legend_item_bonus * team.stat_factor(content, state.player.stats.get("wis", team.BASE_STAT))
    odds *= treasures.amount(state, content, "cultivate")  # 衝絕學的寶物，同 seize
    odds += silver.mentor_bonus(state, content)  # 名師指點（銀兩出口）：在上限之內加，服丹那一次用掉（_force）
    return round(max(1.0, min(cfg.breakthrough.max_chance, odds)))


def _force(state: GameState, content: Content, world: WorldStateStore, art_id: str, rng: random.Random) -> list[str]:
    """服丹強行衝關（待 joy 潤）：成不成都用掉一枚；沒成火候還在，下一次照樣可以再服、或等契機。"""
    p, cfg = state.player, content.config
    art = team.resolve_art(art_id, content, world)
    odds = force_odds(state, content, world, art_id)
    silver.take_mentor(state, content)
    p.legend_items -= 1
    msgs = [f"你服下一枚【{cfg.legend_item_name}】，關起門來強行衝關。"]
    if rng.random() * 100 < odds:
        return msgs + ascend_mod.ascend(state, content, world, art_id, "pill")  # 破境（招式與絕學稿案第三節）
    return msgs + [f"【{art.name}】撞在那一層上，又彈了回來（約 {odds}% 的機會）。"]


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
    if art_id not in state.player.renames_told:  # 自己定的名：定名那一句已經說了，下次同步不必再通知自己（FB-083）
        state.player.renames_told.append(art_id)
    add_chronicle(state, f"{state.player.name}把【{old.name}】練成絕學，為之定名【{name}】。")  # 江湖史一律寫名號（傳聞分層第七節）
    return [f"從今以後，江湖上這門武學就叫【{name}】。"]
