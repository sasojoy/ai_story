"""全服決戰的規則那一半（全部拆包第 54 批）：原本在 tianxia/battle_instance.py，逐字搬來（別的包、核心、共用規則層讀 tianxia/core/battle_base.py）。
資料型別與核心、共用規則層、舊模組、別的包非讀不可的判定（63 個名字）在 tianxia/core/battle_base.py，這裡 re-export 同一批物件：bi.BattleInstance、bi.merit 這些經舊名照舊拿得到。

全服共用的即時多人戰鬥（設計討論：集結選陣營→逐幕逐回合鎖步→打完最後一回合、或戰局一面倒時
判定勝負；每幕固定幾回合，見戰鬥系統設計 3.2 與 resolve_round）。

固定選項（強攻／固守／奇襲，三招互剋，戰鬥系統 3.4）的推力與氣血損耗是 Config.battle 的數字加上每個人加入時快照的
份量算出來的確定性結果，不信任 LLM 自己算數字；
自訂行動（放手一搏，見 BattleOption.free_text／FreeTextGamble）則是 LLM 評估一個成功率
（這件事 LLM 做得到、也實測過排序穩定），系統拿這個機率真的擲骰、用寫死的公式換算
成戰局推動/氣血損耗——玩家的奇葩操作因此真的會影響戰局（賭贏大賺、賭輸慘賠），但
「最後是不是成功」跟「成功該加多少」都是系統的亂數/公式決定，LLM 從頭到尾不會直接
吐出任何被拿去套用的數字，只吐一個被擲骰消費掉的機率。回合的敘事是系統判定的句子（誰佔了上風、為什麼，
見 round_line／round_causes），不叫模型潤色：結算在行動鎖裡，鎖內等模型會讓全服跟著等（試玩回饋 2026-10-08）。

這裡是純粹的資料模型跟引擎函式，不碰共用儲存的存讀鎖（那是 world_state.py::
get_battle/mutate_battle/start_battle 的事）、不碰網頁介面（那是 engine.py/server.py 的事）。
回合「鎖步」的意思是：每個參戰者各自送出一個行動，全員都送出（或逾時被系統代選）才會
真正結算那一回合，由誰送出最後一個行動就由誰的這次呼叫觸發結算，不需要背景常駐程式。
"""
from __future__ import annotations

from collections.abc import Sequence

import math
import random
import re
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field, model_serializer

from tianxia import encounter, gender, tactics, zh
from tianxia.core.battle_base import (  # noqa: F401  核心那一半全部 63 個名字，舊名 battle_instance 照舊拿得到；這一半自己讀的是其中 37 個
    GambleMoment, GambleTale, Escort, SealBare, BattleParticipant, BattleRound, BattleMvp, BattleRoundRecord, RoundSwing, Commander,
    SiegeInfo, FrontNote, BattleInstance, SuccessRateJudgment, GambleVerdict, hollow, more_dramatic, standing_commanders, caller,
    call_orders, neutral_guard, melee, fields, side_names, start_muster, shift_deadlines, start_from_front, sides, role_for, role_name,
    strength, move_scores, idle, _main_move, merit_counts, merit, sworn_pct, note_sworn, outcome_reason, result_at, claims_a_kill, clean_story, assess_gamble,
    _real_name, Phase, UNFINISHED_TITLE, CENTER, BIG_WIN_MARGIN, DEFAULT_FREE_TEXT_SUCCESS_RATE, GAMBLE_WORDS, HOLLOW_BELOW, _NOT_WORDS,
    ORDER_MARK, GUARD_SUFFIX, GUARD, GUARD_SIDE, BLOW_REASON, BLOW_REASON_NOBODY, MELEE_HOLD_REASON, ROLE_MOVES, CAVALRY_MOVES, KEY_ROUNDS,
    STORY_LIMIT, _DIGITS, KILL_WORDS,
)
from tianxia.models import (
    BEATS, MOVES, BattleAct, BattleDef, BattleOption, BattleOutcome, BattleTuning, FreeTextGamble, TacticTuning,
)
from tianxia.ollama_client import OllamaClient

UNFINISHED_TEXT = "季終了，這場決戰沒打完就各自收兵，不算勝負。"


# 戰線動了多少的說法（Joy 2026-10-10 轉玩家反饋：「那個推進多少我都不知道是啥意思」）：句子裡不寫數字，照大小分三段
# （同 front_lines.BANDS 的想法；決戰一回合的變動比戰況大，所以門檻不同）。數字只畫在戰局條上（gauge）。
SHOVE_BANDS: tuple[tuple[int, str], ...] = ((10, "一大截"), (4, "一截"), (1, "一點"))


def shove_size(delta: int) -> str:
    """變動（看絕對值）是「一點」「一截」還是「一大截」。"""
    size = abs(delta)
    return next((word for low, word in SHOVE_BANDS if size >= low), SHOVE_BANDS[-1][1])


def shove(side: str, delta: int) -> str:
    """「替官軍把戰線推前了一截」／「讓官軍的戰線退了一點」；delta 是這一邊這一下推了多少（負是倒退）。"""
    if delta >= 0:
        return f"替{side}把戰線推前了{shove_size(delta)}"
    return f"讓{side}的戰線退了{shove_size(delta)}"


GAMBLES_KEPT = 6  # 每個參戰者記幾次放手一搏給行狀（per_act 不限之後，九回合的仗最多九次，行狀只留最近六次）


ESCORT_KEY = "隨|{owner}"  # 同伴在這一回合 moves／factions 裡的鍵（參戰者照名號、人物照名字，這個前綴不會撞到）
ESCORT_FOCUS_LINE = "{enemy}的強攻掃到{side}隨行的 {n} 位武將，合起來氣血 -{hp}。"  # 待 joy 潤：集火打到同伴合成一句（第五節「讀得下去」）
ESCORT_FALL_LINE = "隨{owner}出陣的{name}陣前敗走，戰線往{enemy}那邊推了{size}！"  # 待 joy 潤


def escort_key(owner: str) -> str:
    return ESCORT_KEY.format(owner=owner)


def one_miss_left(p: BattleParticipant, gamble: FreeTextGamble) -> bool:
    """氣血池撐不過一次最壞的失手（成功率 0 的失手扣的量，同 resolve_round）：再失手一次就倒下。"""
    worst = p.neili_cap * min(1.0, gamble.failure_neili_share_base + 100 * gamble.failure_neili_share_per_risk)
    return p.neili <= worst


def order_text(instance: BattleInstance, side: str, tuning: BattleTuning) -> str:
    """決戰畫面：自己這一方這一回合的將令；沒有人喊令是空字串。三方混戰助守的人（GUARD）不寫：他們的份量不推戰線（裁決 22）。"""
    c, move = caller(instance, side), instance.orders.get(side)
    if c is None or not move or side == GUARD:
        return ""
    return ORDER_LINE.format(name=c.name, move=move, pct=round(tuning.generals.order_bonus * 100))


ORDER_LINE = "{name}傳令：**{move}**（照令出招，份量多 {pct}%）"  # 待 joy 潤
FALL_LINE = "{name}陣前敗走，{side}一時號令不行，戰線往{enemy}那邊推了{size}！"  # 待 joy 潤
FALL_BY_LINE = "{name}被{who}擊退，陣前敗走，{side}一時號令不行，戰線往{enemy}那邊推了{size}！"


# 單方攻中立地時的幕文字（範本的 text_by_lead 寫的是兩軍對打，「漢家的旗」「官軍的陣線」對中立的守軍不對，FB-540）；待 joy 潤
GUARD_LEAD_TEXT = {
    "attacker": "{who}的陣腳越壓越前，守軍一步步退回寨牆後面。",
    "guard": "守軍據著寨牆死守，{who}一波波攻上來，都被打了回去。",
}
# 三方混戰（裁決 22）的幕文字、補上最後一刀的那幾句；待 joy 潤
MELEE_TEXT = "兩軍同時殺到寨牆下，守軍兩頭應付；誰補上守將最後一刀，這一塊就歸誰。"
MELEE_LEAD_TEXT = "{lead}把{other}擠開，搶先貼近了寨牆；守軍兩頭應付，還沒倒。"
GUARD_HIT_LINE = "{side}的強攻撲向{guard}：{guard}氣血 -{hp}{shield}。"  # 兩軍的強攻打守將（一軍一句）
GUARD_SHIELD = "，{n} 人固守護住了 {hp}"
BLOW_LINE = "{who}替{side}補上最後一刀，{guard}倒下了！{side}拿下了這一塊。"  # 守將倒下那一下（回合裡）
BLOW_LINE_NOBODY = "{side}補上最後一刀，{guard}倒下了！{side}拿下了這一塊。"  # 那一軍打守將的只有不是參戰者的（萬一）
MEND_LINE = "{name}這一搏成功了！替{guard}補回氣血 {hp}，自己氣血 -{cost}。"  # 助守的人沒點名的放手一搏成了
MEND_STORY = "{story}（替{guard}補回氣血 {hp}，自己氣血 -{cost}）"
MELEE_CAPTION = "{lead}；{guard}還剩氣血 {hp}/{cap}，誰補上最後一刀誰拿下"  # 三方混戰的戰局條說明
MELEE_LEAD = "{side}佔上風、離寨牆比較近"
MELEE_EVEN = "兩軍不分上下"


def _option_side(definition: BattleDef, faction: str) -> str:
    """選項照哪一格的招：助守三方混戰守將的人（GUARD）用第一方（官軍）那一組招的字（範本只寫了兩軍的招）。"""
    return definition.factions[0].id if faction == GUARD else faction


def role_text(tuning: BattleTuning, role: str) -> str:
    """職位與它做什麼，一句話（決戰畫面用）；沒有職位是空字串。數字照 tuning 寫。"""
    name = role_name(tuning, role)
    if not name:
        return ""
    if role in ROLE_MOVES:
        does = f"{ROLE_MOVES[role]}的份量多 {round(tuning.role_move_bonus * 100)}%"
    elif role == "wis":
        does = f"放手一搏的成功率多 {tuning.role_gamble_rate} 個百分點"
    elif role == "lore":
        does = f"被對面剋住時，吃虧少 {round(tuning.role_counter_relief * 100)}%"
    else:
        return name
    return f"{name}（{does}）"


# 戴名號（金、朱）的人第一次加入一場決戰：戰報一句（稱號與官職設計稿 v5 第五節做法乙；待 joy 潤）
TITLE_ENTRANCE = "「{title}」{name}親臨陣前，眾人一陣譁然。"


def _title_entrance(instance: BattleInstance, name: str, title: dict | None) -> None:
    if title and title.get("grade") in ("gold", "zhu") and name not in instance.participants:
        instance.narrative_log.append(TITLE_ENTRANCE.format(title=title.get("name", ""), name=name))


def join_faction(
    instance: BattleInstance, name: str, faction: str, neili_cap: float, power: float = 0.0, is_bot: bool = False,
    scores: dict[str, float] | None = None, attribute: str = "", role: str = "", mount: str = "", cavalry: float = 0.0,
    troops: str = "", troop_bonus: float = 0.0, turncoat: bool = False, newbie: bool = False,
    kit: tactics.BoutSide | None = None, renown: list[str] | None = None, escort: Escort | None = None,
    seal_bare: SealBare | None = None, cut: float = 0.0, card: dict | None = None,
    title: dict | None = None, sworn: list[str] | None = None, sworn_step: int = 0, sworn_max: int = 0,
) -> None:
    """集結期選陣營；已經選過的人再選一次視為改選（還沒進入 active 都還能換）。escort 是隨他上陣的歷史武將（沒給＝沒派）。
    scores 是這個人此刻每招的份量快照（move_scores），之後戰局只讀這份；沒給＝每招 0。
    mount、cavalry 是加入那一刻騎的馬與騎兵加成（裝備四欄 5.9）；沒給＝沒騎馬。troops、troop_bonus 是帶的部下與份量加成（沒給＝沒帶）。
    turncoat、newbie 是加入那一刻的快照（玉璽碎片設計 4.6）；沒給＝都不是。renown 是加入那一刻的稱號（名聲 2.5；沒給＝沒有）。
    seal_bare 是不含玉璽碎片戰力的那一份（改版；沒給＝沒有碎片）。cut 是加入那一刻的防具減損（鐵匠鋪與合成流程 3.9；沒給＝沒穿）。"""
    if instance.phase != "muster":
        return
    _title_entrance(instance, name, title)
    instance.participants[name] = BattleParticipant(
        name=name, faction=faction, neili=neili_cap, neili_cap=neili_cap, power=power, is_bot=is_bot,
        scores=dict(scores or {}), attribute=attribute, role=role, mount=mount, cavalry=cavalry,
        troops=troops, troop_bonus=troop_bonus, turncoat=turncoat, newbie=newbie, kit=kit, renown=list(renown or []),
        escort=escort, seal_bare=seal_bare, cut=cut, card=card, title=dict(title or {}),
        sworn=list(sworn or []), sworn_step=sworn_step, sworn_max=sworn_max,  # 並肩作戰（結義第二批）：加入那一刻的兄弟
    )


def close_muster(
    instance: BattleInstance, definition: BattleDef, rng: random.Random, now: float = 0.0, tuning: BattleTuning | None = None,
) -> None:
    """集結期結束：還沒選陣營的人（名字已經在 participants 裡但沒指定，或完全沒動作、
    呼叫端另外傳進來的在線名單）由這個函式統一處理——這裡只負責「把已經報名但沒選邊的人
    隨機分配」，呼叫端自己決定要不要把從沒選過的在線玩家也塞進 participants。"""
    if instance.phase != "muster":
        return
    armies = sides(definition)  # 沒選邊的分到兩軍之一（三方混戰助守的人站守軍那一格，不改分）
    for p in instance.participants.values():
        if p.faction not in armies and not (p.faction == GUARD and melee(instance)):
            p.faction = rng.choice(armies)
    instance.phase = "active"
    instance.round = BattleRound(opened_real=now)
    instance.narrative_log.append(f"【{definition.name}】集結完畢，戰鬥開始！")
    call_orders(instance, definition, tuning)


def auto_assign_latecomer(
    instance: BattleInstance, definition: BattleDef, name: str, neili_cap: float, rng: random.Random,
    power: float = 0.0, is_bot: bool = False, faction: str | None = None, scores: dict[str, float] | None = None,
    attribute: str = "", role: str = "", mount: str = "", cavalry: float = 0.0, troops: str = "", troop_bonus: float = 0.0,
    turncoat: bool = False, newbie: bool = False, kit: tactics.BoutSide | None = None, renown: list[str] | None = None,
    escort: Escort | None = None, seal_bare: SealBare | None = None, cut: float = 0.0, card: dict | None = None,
    title: dict | None = None, sworn: list[str] | None = None, sworn_step: int = 0, sworn_max: int = 0,
) -> None:
    """集結期結束後才出現的人（包含機器人）：有指定陣營（劇本分陣營時的玩家、臨時投效的人投效的那一軍）就站自己那邊，
    否則塞進兩軍裡人數較少的一方，維持陣營平衡。scores、mount、cavalry、troops、troop_bonus、turncoat、newbie、renown、seal_bare、cut
    同 join_faction。三方混戰助守的人（GUARD）照站守軍那一格。"""
    if faction not in sides(definition) and not (faction == GUARD and melee(instance)):
        armies = sides(definition)
        counts = {fid: sum(1 for p in instance.participants.values() if p.faction == fid) for fid in armies}
        faction = min(counts, key=lambda fid: (counts[fid], rng.random()))
    _title_entrance(instance, name, title)
    instance.participants[name] = BattleParticipant(
        name=name, faction=faction, neili=neili_cap, neili_cap=neili_cap, power=power, is_bot=is_bot,
        scores=dict(scores or {}), attribute=attribute, role=role, mount=mount, cavalry=cavalry,
        troops=troops, troop_bonus=troop_bonus, turncoat=turncoat, newbie=newbie, kit=kit, renown=list(renown or []),
        escort=escort, seal_bare=seal_bare, cut=cut, card=card, title=dict(title or {}),
        sworn=list(sworn or []), sworn_step=sworn_step, sworn_max=sworn_max,  # 並肩作戰（結義第二批）：加入那一刻的兄弟
    )


def escorts_on_field(instance: BattleInstance, armies: tuple[str, str]) -> list[tuple[BattleParticipant, Escort]]:
    """這一回合在陣上的同伴：（主人, 同伴）。主人在交戰兩軍、沒離開大區（倒下了他照樣在，固守），同伴還沒敗走。"""
    return [
        (p, p.escort) for p in instance.participants.values()
        if p.escort is not None and p.escort.fallen_round is None and p.faction in armies and not p.away
    ]


def _active_participants(instance: BattleInstance) -> list[BattleParticipant]:
    """還在場上、這回合要出手的人：沒倒下，也沒離開決戰的大區。"""
    return [p for p in instance.participants.values() if not p.eliminated and not p.away]


def set_away(instance: BattleInstance, name: str, away: bool) -> None:
    """參戰者離開／回到決戰的大區（地圖擴充設計第六節）：離開的人這回合不出手，已經選好的行動也作廢；
    回來之後從當下這一回合起照常出手。不在名單上的人不理會。"""
    p = instance.participants.get(name)
    if p is None:
        return
    p.away = away
    if away:
        instance.round.pending_actions.pop(name, None)
        instance.round.custom_texts.pop(name, None)
        instance.round.success_rates.pop(name, None)
        instance.round.stories.pop(name, None)


def current_act(instance: BattleInstance, definition: BattleDef) -> BattleAct:
    return definition.acts[instance.act_index]


def act_text(instance: BattleInstance, definition: BattleDef) -> str:
    """這一幕的文字（戰鬥系統 3.2）：照誰佔上風換版本——戰局高於 50 用第一方佔上風的那一版、低於 50 用第二方的，
    剛好 50 或那一方沒寫就用 text。只看公開的戰局，不看伏筆鎖定（4.3）。
    單方攻中立地（neutral_guard）不用範本的兩軍版本（「漢家的旗」對中立的守軍不對，FB-540），改寫 GUARD_LEAD_TEXT。"""
    act = current_act(instance, definition)
    first, second = definition.factions[0].id, definition.factions[1].id
    leader = first if instance.trend > CENTER else second if instance.trend < CENTER else None
    if melee(instance):  # 三方混戰（裁決 22）：戰線是兩軍之間的，守軍兩頭應付
        if leader is None:
            return MELEE_TEXT
        names = side_names(instance, definition)
        return MELEE_LEAD_TEXT.format(lead=names[leader], other=names[second if leader == first else first])
    guard = neutral_guard(instance)
    if guard is not None and leader is not None:
        names = side_names(instance, definition)
        who = "、".join(names.get(a, a) for a in instance.siege.attackers)
        return GUARD_LEAD_TEXT["guard" if leader == guard else "attacker"].format(who=who)
    return act.text_by_lead.get(leader, act.text) if leader else act.text


def total_rounds(definition: BattleDef) -> int:
    """整場打幾回合（戰鬥系統設計 3.2）：每幕 rounds_per_act 回合 × 幕數；黃巾決戰是 3 × 3 ＝ 9。"""
    return definition.rounds_per_act * len(definition.acts)


def options_for(instance: BattleInstance, definition: BattleDef, name: str) -> list[BattleOption]:
    """這個人這回合能選的選項：框架給的選項，依陣營篩選（faction=None 的選項雙方都能選）。"""
    p = instance.participants.get(name)
    if p is None:
        return []
    act = current_act(instance, definition)
    options = [o for o in act.options if o.faction in (None, _option_side(definition, p.faction))]
    if pinned(instance, p):  # 被險招牽制住：這一回合只能固守
        held = [o for o in options if o.move == "固守" and not o.free_text]
        if held:
            return held
    if not can_gamble(instance, definition, p):  # 這一幕放手一搏過了
        options = [o for o in options if not o.free_text]
    return options


def pinned(instance: BattleInstance, p: BattleParticipant) -> bool:
    """這一回合（整場第 round_number＋1 回合）是不是被牽制住、只能固守。"""
    return p.pinned_round == instance.round_number + 1


def can_gamble(instance: BattleInstance, definition: BattleDef, p: BattleParticipant) -> bool:
    """這一幕還能不能放手一搏（FreeTextGamble.per_act；0 ＝ 不限，每回合都能搏）。"""
    limit = definition.free_text_gamble.per_act if definition.free_text_gamble is not None else 0
    if limit <= 0:
        return True
    return p.gambled_act != instance.act_index or p.gambles_this_act < limit


def find_target(instance: BattleInstance, definition: BattleDef, name: str, text: str) -> BattleParticipant | None:
    """放手一搏的文字裡點名的對面參戰者：名號 2 字以上、在文字裡最先出現的那一個（一樣早取長的）。只認交戰兩軍裡對面那一邊、
    還沒倒下的人。由引擎認，不靠模型。三方混戰（裁決 22）三格互為對面：兩軍點得到另一軍與助守的人，助守的人點得到兩軍的人。"""
    me = instance.participants.get(name)
    armies = set(fields(instance, definition))
    if me is None or me.faction not in armies:
        return None
    found = [
        (text.find(q.name), -len(q.name), q.name) for q in instance.participants.values()
        if q.faction in armies and q.faction != me.faction and not q.eliminated and len(q.name) >= 2 and q.name in text
    ]
    return instance.participants[min(found)[2]] if found else None


def target_line(instance: BattleInstance, definition: BattleDef, name: str, text: str, tuning: BattleTuning) -> str:
    """給模型評成功率的那一行：點名的對手是誰、身手跟你比如何（只寫比較，不寫數字）；沒點名是空字串。"""
    target = find_target(instance, definition, name, text)
    me = instance.participants.get(name)
    names = side_names(instance, definition)  # 守將那一格寫守軍（FB-540）
    if target is None and me is not None and (chief := find_commander(instance, definition, name, text)) is not None:
        side = names.get(chief.faction, chief.faction)
        hurt = "，已經帶傷" if chief.neili < chief.neili_cap * 0.5 else ""
        return f"{chief.name}（{side}{'主將' if chief.rank == 0 else '副將'}，親自坐鎮陣中、身邊護衛重重{hurt}）"
    if target is None or me is None:
        return ""
    ratio = strength(tuning, target.power) / max(1.0, strength(tuning, me.power))
    how = ("遠比玩家強" if ratio >= 1.5 else "比玩家強" if ratio >= 1.1 else "跟玩家不相上下" if ratio > 0.9
           else "比玩家弱" if ratio > 0.6 else "遠比玩家弱")
    role = role_name(tuning, target.role)
    side = names.get(target.faction, target.faction)
    hurt = "，已經帶傷" if target.neili < target.neili_cap * 0.5 else ""
    return f"{target.name}（{side}{'的' + role if role else ''}，身手{how}{hurt}）"


def fixed_options(instance: BattleInstance, definition: BattleDef, name: str) -> list[BattleOption]:
    """這個人這回合能選的三招（固定選項，有 move；放手一搏不算）。"""
    return [o for o in options_for(instance, definition, name) if not o.free_text and o.move is not None]


def submit_action(
    instance: BattleInstance, name: str, tag: str, text: str | None = None, success_rate: int | None = None,
    stories: tuple[str, str] | list[str] | None = None, sex: str | None = None,
) -> None:
    """記錄一個人這回合選的行動；已經陣亡或不在這場戰鬥裡的人送出無效。text/success_rate
    是 free_text 選項才有（見 BattleOption.free_text）——success_rate 是呼叫端（engine.py
    ::submit_battle_custom_action）在送出的當下先問過 LLM 評好的成功率，resolve_round
    靠這個欄位有沒有值決定這個人這回合是賭局型行動還是一般查表行動，自己不會、也不能
    呼叫 LLM（見模組說明）。"""
    p = instance.participants.get(name)
    if p is None or p.eliminated or p.away or instance.phase != "active":
        return
    instance.round.pending_actions[name] = tag
    if name in instance.round.auto_picked:  # 系統代選過、結算前自己又選了：這回合算自己出手
        instance.round.auto_picked.remove(name)
    p.idle_streak = 0  # 按了任何行動就不算掛機
    if text:
        instance.round.custom_texts[name] = text
    if success_rate is not None:
        instance.round.success_rates[name] = max(0, min(100, success_rate))
        if sex:
            instance.round.sexes[name] = sex
        if stories:
            instance.round.stories[name] = [str(stories[0]), str(stories[1])]


def round_is_complete(instance: BattleInstance, timed_out: bool = False) -> bool:
    """所有還在場上、沒在掛機的人都送出行動了（陣亡的人不用等；掛機的人也不等，結算前由 fill_idle_actions 代選）。
    場上全是掛機的人時照舊等這一回合逾時；timed_out（這一回合已經逾時，呼叫端剛照逾時代選完）時就算齊了，照代選的結算
    （FB-173：以前沒有要等的人就一直回假，掛機的人鈕又是灰的，整場卡死）。場上沒人（全倒下、全走開）不算，那是 end_without_fighters 的事。"""
    active = _active_participants(instance)
    awaited = [p for p in active if not idle(p)]
    if not awaited:
        return timed_out and bool(active) and all(p.name in instance.round.pending_actions for p in active)
    return all(p.name in instance.round.pending_actions for p in awaited)


def round_progress(instance: BattleInstance, definition: BattleDef) -> tuple[int, int]:
    """這一回合（已送出, 在場）的人數：在場是還沒倒下、沒離開大區、沒在掛機的人，已送出是其中選好行動的。
    畫面寫「已送出 X／在場 Y」，讓人知道是在等人、不是壞了（試玩回饋 2026-10-08）。
    跟 round_is_complete 等的是同一批人（Joy 2026-10-13：以前全員送出了倒數還在跳）。"""
    active = [p for p in _active_participants(instance) if not idle(p)]
    return sum(1 for p in active if p.name in instance.round.pending_actions), len(active)


def idle_count(instance: BattleInstance, definition: BattleDef) -> int:
    """掛機中的人數（round_progress 的「在場」不算他們；畫面另寫「掛機 N 人」）。"""
    return sum(1 for p in _active_participants(instance) if idle(p))


def _war_rally(instance: BattleInstance, moves: dict[str, str], on: bool) -> dict[tuple[str, str], list[tuple[str, float]]]:
    """名將本命兵器〔號令〕（本命戰法第三批）：帶著它出固定招的人，同一邊出同一招的友軍份量 +war_ally_pct（自己不算）。
    （陣營, 招）→ [(帶著它的人, 加幾成)]；戰法關著是空的。"""
    out: dict[tuple[str, str], list[tuple[str, float]]] = {}
    if not on:
        return out
    for name, move in moves.items():
        p = instance.participants.get(name)
        if p is None or p.eliminated or p.kit is None:
            continue
        pct = max((h.tactic.params.get("war_ally_pct", 0.0) for h in p.kit.holders), default=0.0)
        if pct > 0:
            out.setdefault((p.faction, move), []).append((name, pct))
    return out


def counter_coefficient(tuning: BattleTuning, move: str, enemy_mix: dict[str, float]) -> float:
    """剋制係數（戰鬥系統 3.4）：1 ＋ 0.5 × 對面出「被你剋的招」的比例 － 0.5 × 對面出「剋你的招」的比例，0.5～1.5。
    enemy_mix 是對面這回合各招的比例（_mix；對面沒人出固定招時呼叫端不呼叫、係數當 1）。"""
    beaten = BEATS[move]
    beater = next(m for m, v in BEATS.items() if v == move)
    return 1 + tuning.counter * enemy_mix.get(beaten, 0.0) - tuning.counter * enemy_mix.get(beater, 0.0)


def condition(p: BattleParticipant) -> float:
    """這一場的氣血狀態：0.5 ＋ 0.5 × 剩的 ÷ 上限（同遭遇戰，戰鬥系統 3.4）。"""
    return encounter.condition_of(p.neili, p.neili_cap)


def option_of(definition: BattleDef, act_index: int, faction: str, tag: str) -> BattleOption | None:
    """這一幕、這個陣營能選的、tag 是 tag 的那個選項；沒有就是 None。三方混戰助守的人（GUARD）用第一方那一組招（_option_side）。"""
    side = _option_side(definition, faction)
    return next(
        (o for o in definition.acts[act_index].options if o.tag == tag and o.faction in (None, side)), None,
    )


def _mix(moves: dict[str, str], factions: dict[str, str], side: str) -> dict[str, float]:
    """這一邊這回合各招的比例（只算出固定招的人）；沒人出就是空的。"""
    mine = [moves[name] for name in moves if factions[name] == side]
    return {m: mine.count(m) / len(mine) for m in MOVES} if mine else {}


def _mix_of(moves: dict[str, str], factions: dict[str, str], sides_: set[str]) -> dict[str, float]:
    """好幾格合起來這回合各招的比例（三方混戰：自己以外的兩格，裁決 22）；沒人出就是空的。"""
    theirs = [moves[name] for name in moves if factions[name] in sides_]
    return {m: theirs.count(m) / len(theirs) for m in MOVES} if theirs else {}


def safest_option_tag(
    instance: BattleInstance, definition: BattleDef, name: str, tuning: BattleTuning | None = None,
) -> str | None:
    """這個人這回合最保守的固定選項（氣血損耗最低：三招時就是固守；一樣低時取框架裡排前面的）。只看他自己陣營能選的，
    所以逾時代選不會把黃巾的人代選成官軍的招、替對面推戰局。這一幕沒有他能選的固定選項就回 None。"""
    options = fixed_options(instance, definition, name)
    if not options:
        return None
    tuning = tuning or BattleTuning()
    return min(options, key=lambda o: tuning.damage[o.move]).tag


def fill_idle_actions(instance: BattleInstance, definition: BattleDef, tuning: BattleTuning | None = None) -> None:
    """其他人都送齊了、不等掛機的人：還沒送出的掛機者照逾時一樣代選（fill_timed_out_actions）。"""
    fill_timed_out_actions(instance, definition, tuning, only_idle=True)


def fill_timed_out_actions(
    instance: BattleInstance, definition: BattleDef, tuning: BattleTuning | None = None, only_idle: bool = False,
) -> None:
    """逾時：還沒送出行動的在場者（沒倒下、沒離開大區），系統代選他自己陣營最保守的固定選項（三招時是固守）；
    這一幕他沒有固定選項（驗過的內容每邊每幕都有三招，走不到這裡）就跳過他。
    代選的人記進 round.auto_picked：這一回合不算他自己出手（FB-027）。"""
    for p in _active_participants(instance):
        if only_idle and not idle(p):
            continue
        if p.name not in instance.round.pending_actions:
            tag = safest_option_tag(instance, definition, p.name, tuning)
            if tag is None:
                continue
            instance.round.pending_actions[p.name] = tag
            instance.round.auto_picked.append(p.name)


def diversity(instance: BattleInstance, moves: dict[str, str], side: str, tuning: BattleTuning) -> float:
    """這一回合這一邊出固定招的人，身上武學有幾路不同的屬性（一門打不遍）：每多一路，力量多乘 diversity_per，最多 diversity_cap。
    屬性是加入時的快照（BattleParticipant.attribute），空的（第一季沒開、舊資料）不算一路，所以開關關著時一律是 1。"""
    roads = {
        p.attribute for name in moves if (p := instance.participants.get(name)) is not None and p.faction == side and p.attribute
    }
    return 1 + min(tuning.diversity_cap, tuning.diversity_per * max(0, len(roads) - 1))


def resolve_round(
    instance: BattleInstance, definition: BattleDef, rng: random.Random, now: float = 0.0,
    tuning: BattleTuning | None = None, tactic: TacticTuning | None = None,
) -> list[str]:
    """結算一回合：固定招走三招（戰鬥系統 3.4）：每個人的力量＝份量（加入時快照的 scores，乘這一場的氣血狀態）×
    剋制係數（對面這回合出招的比例），一邊的力量＝Σ ÷ √（這一邊出固定招的人數），推力＝push_max ×（第一方 − 第二方）÷
    （兩方相加），四捨五入；一邊沒人出固定招、另一邊有就推滿，兩邊都沒有是 0。扣氣血照招的損耗 ×（2 − 剋制係數）。
    放手一搏照舊走賭局公式、推動加在三招合成之後（決戰改版三再改）。
    沒有 scores（舊資料、沒走 Game 加入的人）份量算 0：照常出招、扣血、出局，只是推不動戰局。
    氣血歸零的人出局；一開頭先把所有人的 last_result 清空，只有這一回合出了固定招的人才寫上新的。
    回合數加一之後照戰鬥系統設計 3.2 決定接下來怎麼走（只有兩個時機判結果）：
    - 戰局偏離中線 50 到 decisive_margin（壓倒性，戰局到 90 或 10）：當回合收場，不再換幕——剛好是該換幕的那一回合
      也一樣。看的是 50、不是這一場的起點（戰鬥系統 5.3：時刻表決戰的起點照戰況走，看起點會不對稱）；
    - 打完最後一回合（total_rounds）：看戰局收場；
    - 都不是、而且這一幕的回合打滿了：換下一幕。換幕只看回合數，不看戰局。
    最後把回合狀態重置給下一回合用（opened_real
    設成 now，給下一回合的逾時判斷當起點）。威力抵銷（mitigated_by_power）直接讀
    BattleParticipant.power——那是加入戰鬥當下由各自的 Game 執行個體算好快照進來的
    （見 BattleParticipant 的欄位註解），這裡不需要、也不能臨時去查任何人的角色資料。
    回傳這回合發生的事件訊息（系統判定的部分，不含 LLM 潤色、也不會自己寫進
    narrative_log——那兩件事都是呼叫端的事，見 narrate_round：呼叫端通常是先結算拿到
    msgs，請 LLM 潤色成一段敘事，再把潤色後的文字（或潤色失敗時的 msgs 本身）加進
    narrative_log，這裡不越俎代庖）。
    參戰者自己的戰報（FB-027）也在這裡記：這回合的行動不是系統代選的（不在 round.auto_picked 裡），出手回合數
    加一——在結算時數，一回合只會數一次，送出後又離開大區（行動作廢）的也不會被數到；倒下的人記下第幾回合。"""
    tuning = tuning or BattleTuning()
    act_index = instance.act_index
    msgs: list[str] = []
    first, second = definition.factions[0].id, definition.factions[1].id  # first 是戰局的正向方
    # 三方混戰（裁決 22）：守將與助守的人站第三格 GUARD——出招算進兩軍各自的「對面」，不推戰線（戰線只算兩軍之間）
    three = melee(instance)
    sides3 = (first, second, GUARD) if three else (first, second)
    for p in instance.participants.values():
        p.last_result = ""  # 沒出固定招的人（放手一搏、離開大區、倒下、沒出手）不留上一回合的字
    # 這一回合出固定招的人：名號 → 哪一招（放手一搏的人不算進比例；不在交戰雙方的陣營這一份不算）
    factions = {name: p.faction for name, p in instance.participants.items()}
    moves: dict[str, str] = {}
    for name, tag in instance.round.pending_actions.items():
        p = instance.participants.get(name)
        if p is None or p.eliminated or name in instance.round.success_rates or p.faction not in sides3:
            continue
        option = option_of(definition, act_index, p.faction, tag)
        if option is not None and option.move is not None:
            moves[name] = option.move
    gen = tuning.generals
    on_field = [c for c in instance.commanders if c.fallen_round is None and c.faction in (first, second)]
    for c in on_field:  # 上陣的大勢人物照這一方的將令出手，也算進出招的比例（對面剋不剋得住他）
        moves[c.name] = instance.orders.get(c.faction) or "固守"
        factions[c.name] = c.faction
    keeper = next((c for c in instance.commanders if three and c.faction == GUARD and c.fallen_round is None), None)
    if keeper is not None:  # 三方混戰的守將：照自己喊的那一招出手，兩軍都算他是對面
        moves[keeper.name] = instance.orders.get(GUARD) or "固守"
        factions[keeper.name] = GUARD
    escorts = escorts_on_field(instance, (first, second))
    for p, e in escorts:  # 隨主人上陣的同伴：照主人這一回合的固定招出手，主人放手一搏、倒下時固守（也算進出招的比例）
        key = escort_key(p.name)
        moves[key] = moves.get(p.name) or "固守"
        factions[key] = p.faction
    callers = {side for side in (first, second) if caller(instance, side) is not None}
    chief_hits: list[tuple[str, str, int, int, str, str, int, float, str]] = []  # 點名人物的放手一搏成了（_strike_commanders 結算）
    escort_hits: list[tuple[str, str, int, int, str, str, int, float, str]] = []  # 點名同伴的（第二格是主人的名號，_strike_escorts）
    mixes = {side: _mix(moves, factions, side) for side in sides3}
    # 每一格的「對面」這一回合各招的比例（剋制係數照它算）：兩軍對打就是另一軍；三方混戰是自己以外兩格合起來
    foe_mix = ({side: _mix_of(moves, factions, set(sides3) - {side}) for side in sides3} if three
               else {first: mixes[second], second: mixes[first]})
    force, counts = {first: 0.0, second: 0.0}, {first: 0, second: 0}
    names = side_names(instance, definition)  # 守將那一格寫守軍（FB-540）
    gambles: dict[str, int] = {}  # 陣營 → 這一回合放手一搏替自己這一邊推了多少（正是推進、負是倒退），回合摘要用
    gains: dict[str, int] = {}  # 陣營 → 其中成了的合起來推進多少（success_trend_cap 夾）
    losses: dict[str, int] = {}  # 陣營 → 其中失手的合起來倒退多少（負的，side_trend_cap 夾）
    coefs: dict[str, list[float]] = {first: [], second: []}  # 陣營 → 這一回合每個出固定招的人的剋制係數，回合摘要用
    fitness: dict[str, list[tuple[float, float]]] = {first: [], second: []}  # 陣營 → 每個出固定招的人的（份量, 氣血狀態），回合摘要用
    shares: dict[str, list[tuple[float, str, str]]] = {first: [], second: []}  # 陣營 →（力量, 名號, 招）：回合原因點名帶頭的人
    hits: list[_Hit] = []  # 點名的放手一搏成了：對被點名的人的傷害等這一圈結算完才一起扣（誰先誰後不影響這一回合的力量）
    targets_now: dict[str, list[str]] = {}  # 這一回合被點名的人 → 點名他的人
    trend_before = instance.trend
    rnd_no = instance.round_number + 1  # 這是整場的第幾回合（round_number 結算完才加一）
    fired: dict[str, list[str]] = {}  # 陣營 → 這一回合發動本命戰法的那幾句（〔名〕開頭，誰發動的寫在句子裡）

    rally = _war_rally(instance, moves, tactic is not None)  # 名將本命兵器〔號令〕：（陣營, 招）→ [(號令的人, 加幾成)]
    for side, move_, who, _pct in sorted({(k[0], k[1], w, pc) for k, rows in rally.items() for w, pc in rows}):
        if any(n != who and q.faction == side and moves.get(n) == move_ for n, q in instance.participants.items() if not q.eliminated):
            fired.setdefault(side, []).append(f"{tactics.LEAD}號令〕{who}號令一下，同出{move_}的友軍份量加重")
            instance.tactic_kinds["號令"] = "order"

    def war(name: str, p: BattleParticipant, move: str | None, coef: float) -> tactics.War:
        """本命戰法（本命戰法第二批）：只算自己身上的（tactics.WAR_KINDS）；沒帶著或沒開是中性值。"""
        if p.kit is None or tactic is None:
            return tactics.War()
        edge = instance.trend if p.faction == first else 100 - instance.trend
        ratio = p.neili / p.neili_cap if p.neili_cap else 1.0
        out = tactics.war_round(p.kit, move, 1 if coef > 1 else 0, rnd_no, edge, ratio, tactic, _war_rng(instance, name, rnd_no))
        if out.lines:  # 招一句一行（「〔名〕某某……」），哪一軍的由場景照名號標（Game._battle_rounds 的 side_of），不另寫標頭
            fired.setdefault(p.faction, []).extend(out.lines)
            instance.tactic_kinds.update(out.kinds)
        if out.hp:
            p.neili = max(0.0, min(p.neili_cap, p.neili + p.neili_cap * out.hp))
        return out

    def escort_war(p: BattleParticipant, e: Escort, move: str, coef: float) -> tactics.War:
        """同伴自己的本命戰法（他身上的兩門，照決戰的規矩）：亂數照他的鍵自己一份；發動的那一句寫他的名字。"""
        if e.kit is None or tactic is None:
            return tactics.War()
        edge = instance.trend if p.faction == first else 100 - instance.trend
        ratio = e.neili / e.neili_cap if e.neili_cap else 1.0
        out = tactics.war_round(e.kit, move, 1 if coef > 1 else 0, rnd_no, edge, ratio, tactic, _war_rng(instance, escort_key(p.name), rnd_no))
        if out.lines:
            fired.setdefault(p.faction, []).extend(out.lines)
            instance.tactic_kinds.update(out.kinds)
        if out.hp:
            e.neili = max(0.0, min(e.neili_cap, e.neili + e.neili_cap * out.hp))
        return out

    def tale(name: str, p: BattleParticipant, text: str, won: bool, target: str, fixed: str, numbers: str) -> None:
        """沒有現成劇情的放手一搏：先播固定句，記一筆等著回合結算後補（GambleTale）。"""
        instance.tales.append(GambleTale(
            round=rnd_no, act_index=act_index, name=name, faction=p.faction, text=text, won=won, target=target,
            sex=instance.round.sexes.get(name, "男"), fixed=fixed, numbers=numbers,
        ))
    for name, tag in list(instance.round.pending_actions.items()):
        p = instance.participants.get(name)
        if p is None or p.eliminated:
            continue
        if name not in instance.round.auto_picked:
            p.acted_rounds += 1
        else:  # 逾時被代選：掛機（下一回合起不等他）
            p.idle_streak += 1
            p.held_rounds += 1
        success_rate = instance.round.success_rates.get(name)
        custom_text = instance.round.custom_texts.get(name)
        if success_rate is not None and definition.free_text_gamble is not None:
            gamble = definition.free_text_gamble
            assessed = success_rate
            if p.role == "wis":  # 軍師：模型評完再加（職位，試玩回饋 2026-10-08）
                success_rate = min(100, success_rate + tuning.role_gamble_rate)
            risk = 100 - success_rate
            succeeded = rng.random() * 100 < success_rate
            saved = None
            if not succeeded and tactic is not None and p.kit is not None:  # 神上使：失手改成功（自己的亂數，不碰 rng）
                saved = tactics.divine_save(p.kit.holders, _war_rng(instance, name, rnd_no, "神上使"))
                succeeded = saved is not None
            p.moves[rnd_no] = f"放手一搏「{custom_text}」，{'成了' if succeeded else '沒成'}" if custom_text else f"放手一搏，{'成了' if succeeded else '沒成'}"
            if custom_text:
                plus = f"，{role_name(tuning, p.role)} +{success_rate - assessed}" if success_rate != assessed else ""
                msgs.append(f"{name}放手一搏：「{custom_text}」（評估成功率 {assessed}%{plus}）")
            if saved is not None:
                msgs.append(tactics.divine_line(saved))
            fx = war(name, p, None, 1.0)
            if fx.lines:
                p.moves[rnd_no] += "；" + "；".join(fx.lines)
            side_name = names.get(p.faction, p.faction)
            helper = three and p.faction == GUARD  # 三方混戰助守的人：沒有戰線可推（裁決 22）
            win_story, lose_story = (instance.round.stories.get(name) or ["", ""])[:2]
            if p.gambled_act == act_index:  # 一幕最多搏幾次（FreeTextGamble.per_act）
                p.gambles_this_act += 1
            else:
                p.gambled_act, p.gambles_this_act = act_index, 1
            target = find_target(instance, definition, name, custom_text or "")
            chief = find_commander(instance, definition, name, custom_text or "") if target is None else None
            # 點名的認法：參戰者 → 上陣的人物 → 隨行的同伴（歷史武將同行第五節：參戰者優先）
            mate = find_escort(instance, definition, name, custom_text or "") if target is None and chief is None else None
            if target is not None:  # 點名：這一幕他變得顯眼；成不成都記下誰盯上了他
                instance.marked[target.name] = act_index
                if name not in target.targeted_by:
                    target.targeted_by.append(name)
                targets_now.setdefault(target.name, []).append(name)
            # 試玩回饋 2026-10-08：對戰局只有小影響，主要的代價是自己的氣血池（扣到 0 就照下面倒下出局）
            if succeeded and helper:  # 助守的人搏成了：點名兩軍的人照打（不推戰線），沒點名替守將補回一截（同點名守將打掉的量）
                delta = 0
                damage = p.neili_cap * gamble.success_neili_share
                instance.marked[name] = act_index
                p.gambles_won += 1
                if target is not None:
                    want = target.neili_cap * min(tuning.target_hit_max, tuning.target_hit_base + risk * tuning.target_hit_per_risk)
                    hits.append(_Hit(
                        len(msgs), name, target.name, want, success_rate <= tuning.pin_rate, win_story, side_name, 0, damage,
                        custom_text or "", False,
                    ))
                    msgs.append("")
                else:
                    mend = 0.0
                    if keeper is not None:
                        mend = min(keeper.neili_cap * min(gen.hit_max, gen.hit_base + risk * gen.hit_per_risk), keeper.neili_cap - keeper.neili)
                        keeper.neili += mend
                    who = keeper.name if keeper is not None else GUARD_SIDE
                    numbers = f"替{who}補回氣血 {round(mend)}，自己氣血 -{round(damage)}"
                    if win_story:
                        msgs.append(MEND_STORY.format(story=win_story, guard=who, hp=round(mend), cost=round(damage)))
                    else:
                        msgs.append(MEND_LINE.format(name=name, guard=who, hp=round(mend), cost=round(damage)))
                        if custom_text:
                            tale(name, p, custom_text, True, "", msgs[-1], numbers)
            elif succeeded:
                # 越強越有份量：推進乘實力（新手打五折、練滿最多兩倍）
                might = max(tuning.gamble_strength_min, min(tuning.gamble_strength_max, strength(tuning, p.power) / tuning.gamble_strength_ref))
                delta = max(1, round((gamble.success_trend_base + risk * gamble.success_trend_per_risk) * might))
                damage = p.neili_cap * gamble.success_neili_share
                instance.marked[name] = act_index  # 搏成了的人也顯眼
                p.gambles_won += 1
                if target is not None:  # 點名：推進打折，其餘化成對他的傷害（等這一圈結算完才扣，訊息到時候再寫）
                    delta = max(1, round(delta * tuning.target_push_share))
                    want = target.neili_cap * min(tuning.target_hit_max, tuning.target_hit_base + risk * tuning.target_hit_per_risk)
                    hits.append(_Hit(
                        len(msgs), name, target.name, want, success_rate <= tuning.pin_rate, win_story, side_name, delta, damage,
                        custom_text or "",
                    ))
                    msgs.append("")
                elif chief is not None:  # 點名上陣的大勢人物：推進同樣打折，傷害等這一圈結算完才扣（_strike_commanders）
                    delta = max(1, round(delta * tuning.target_push_share))
                    chief_hits.append((name, chief.name, risk, len(msgs), win_story, side_name, delta, damage, custom_text or ""))
                    msgs.append("")
                elif mate is not None:  # 點名隨行的同伴：同人物，傷害等這一圈結算完才扣（_strike_escorts）
                    delta = max(1, round(delta * tuning.target_push_share))
                    escort_hits.append((name, mate[0].name, risk, len(msgs), win_story, side_name, delta, damage, custom_text or ""))
                    msgs.append("")
                elif win_story:  # 模型寫的劇情，數字照引擎算的另外附在後面
                    msgs.append(f"{win_story}（{shove(side_name, delta)}，自己氣血 -{round(damage)}）")
                else:
                    numbers = f"{shove(side_name, delta)}，自己氣血 -{round(damage)}"
                    msgs.append(f"{name}這一搏成功了！{numbers}。")
                    if custom_text:
                        tale(name, p, custom_text, True, "", msgs[-1], numbers)
            else:
                delta = 0 if helper else -min(gamble.failure_trend_cap, round(risk * gamble.failure_trend_per_risk))
                damage = p.neili_cap * min(1.0, gamble.failure_neili_share_base + risk * gamble.failure_neili_share_per_risk)
                # 代價照引擎算的寫出來（試玩回饋 2026-10-08：「慘痛的代價是什麼？」）
                cost = f"{shove(side_name, delta)}，" if delta else ""
                if lose_story:
                    msgs.append(f"{lose_story}（{cost}自己氣血 -{round(damage)}）")
                else:
                    msgs.append(f"{name}這一搏失敗了，付出了慘痛代價：{cost}自己氣血 -{round(damage)}。")
                    if custom_text:
                        tale(name, p, custom_text, False, target.name if target is not None else "", msgs[-1],
                             f"{cost}自己氣血 -{round(damage)}")
            if custom_text:
                moment = GambleMoment(
                    name=name, faction=p.faction, text=custom_text, story=win_story if succeeded else lose_story,
                    rate=assessed, won=succeeded, target=target.name if target is not None else "", round=rnd_no,
                )
                if len(p.gambles) < GAMBLES_KEPT:
                    p.gambles.append(moment)
                if more_dramatic(moment, instance.highlight):
                    instance.highlight = moment
            if not helper:  # 助守的人不推戰線（三方混戰）
                gambles[p.faction] = gambles.get(p.faction, 0) + delta
                if delta > 0:
                    gains[p.faction] = gains.get(p.faction, 0) + delta
                elif delta < 0:
                    losses[p.faction] = losses.get(p.faction, 0) + delta
        elif name in moves:
            move = moves[name]
            foe = foe_mix[p.faction]  # 兩軍對打是另一軍（同以前的 mixes[enemy]）；三方混戰是自己以外兩格合起來
            coef = counter_coefficient(tuning, move, foe) if foe else 1.0
            if p.role == "lore" and coef < 1:  # 參謀：被剋時吃虧少一些
                coef = 1 - (1 - coef) * (1 - tuning.role_counter_relief)
            fx = war(name, p, move, coef)
            if fx.unbeaten:  # 無隙：被剋也不吃虧
                coef = max(coef, 1.0)
            might = p.scores.get(move, 0.0) * condition(p) * coef * fx.force
            might *= 1 + sum(pct for who, pct in rally.get((p.faction, move), []) if who != name)
            if p.faction in callers and move == instance.orders.get(p.faction):  # 照將令出招（龍頭上陣）
                might *= 1 + gen.order_bonus
            if p.faction in force:  # 三方混戰助守的人不推戰線（戰線只算兩軍之間）
                force[p.faction] += might  # 份量在扣這一回合的血之前算
                shares[p.faction].append((might, name, move))
                counts[p.faction] += 1
                coefs[p.faction].append(coef)
                fitness[p.faction].append((p.scores.get(move, 0.0), condition(p)))
            damage = tuning.damage[move] * (2 - coef)
            if move == "強攻":
                damage *= 1 - min(tuning.strong_mitigation_cap, p.power / 200)
            damage *= fx.damage
            p.last_result = f"{move}（剋制 ×{coef:.1f}）"
            p.moves[rnd_no] = move + ("（逾時代選）" if name in instance.round.auto_picked else "") + "".join("；" + x for x in fx.lines)
        else:  # 這個人這回合沒有三招可算（選項不在這一幕、不在交戰雙方、放手一搏卻沒有賭局設定）：不推戰局、不扣血
            continue
        p.neili = max(0.0, p.neili - damage)
        if p.neili <= 0 and not p.eliminated:
            p.eliminated = True
            p.fell_round = instance.round_number + 1  # 這一回合（round_number 結算完才加一）
            msgs.append(f"{name}氣血耗盡，倒在戰場上，退出了這場戰鬥（轉為觀戰）。")
    for c in on_field:  # 上陣的大勢人物的力量（份量在扣這一回合的血之前算）
        foe = foe_mix[c.faction]
        coef = counter_coefficient(tuning, moves[c.name], foe) if foe else 1.0
        cond = encounter.condition_of(c.neili, c.neili_cap)
        force[c.faction] += c.score * cond * coef
        counts[c.faction] += 1
        coefs[c.faction].append(coef)
        fitness[c.faction].append((c.score, cond))
    shields: dict[str, float] = {}  # 主人名號 → 這一回合同伴挨的打乘多少（化影）
    for p, e in escorts:  # 隨行同伴的力量（同人物：算進那一邊的人數；不扣出招的血）
        key = escort_key(p.name)
        foe = foe_mix[p.faction]
        coef = counter_coefficient(tuning, moves[key], foe) if foe else 1.0
        fx = escort_war(p, e, moves[key], coef)
        if fx.unbeaten:
            coef = max(coef, 1.0)
        shields[p.name] = fx.damage
        cond = encounter.condition_of(e.neili, e.neili_cap)
        force[p.faction] += e.score * cond * coef * fx.force
        counts[p.faction] += 1
        coefs[p.faction].append(coef)
        fitness[p.faction].append((e.score, cond))
    harmed: dict[str, float] = {}  # 這一回合每個人被別人打掉多少（點名＋集火，target_round_cap）
    for hit in hits:
        msgs[hit.index], fixed, numbers = _land_hit(instance, tuning, hit, harmed, msgs)
        if fixed and hit.text:
            tale(hit.attacker, instance.participants[hit.attacker], hit.text, True, hit.target, fixed, numbers)
    msgs += _focus_fire(instance, tuning, moves, factions, sides3, names, act_index, harmed)
    fall_delta = 0
    if on_field:
        fall_lines, fall_delta = _strike_commanders(
            instance, tuning, moves, factions, (first, second), names, chief_hits, msgs, harmed, rnd_no, tale,
        )
        msgs += fall_lines
    if escorts:
        mate_lines, mate_delta = _strike_escorts(
            instance, tuning, moves, factions, (first, second), names, escort_hits, msgs, harmed, rnd_no, tale, shields,
            extra=(GUARD,) if three else (),
        )
        msgs += mate_lines
        fall_delta += mate_delta
    if keeper is not None:  # 三方混戰：兩軍打守將，池子歸零那一下算誰補上最後一刀（裁決 22）
        msgs += _strike_guard(instance, tuning, keeper, moves, factions, (first, second), names, chief_hits, msgs, harmed,
                              rnd_no, tale, trend_before)
    for hurt_name, amount in harmed.items():  # 被盯上打掉了氣血、回合結束還站著：戰功（撐住）
        q = instance.participants.get(hurt_name)
        if q is not None and amount >= 0.5 and not q.eliminated:
            q.stood_marked += 1
    instance.last_targets = targets_now
    # 同一邊同一回合放手一搏合起來有上限，成了的與失手的分開夾（Joy 2026-10-15「成功另算」）：失手的合起來最多退
    # side_trend_cap（一群人亂寫拖不垮全軍），成了的照人數疊、最多推 success_trend_cap
    if definition.free_text_gamble is not None:
        gamble = definition.free_text_gamble
        back_cap = gamble.side_trend_cap
        push_cap = gamble.success_trend_cap if gamble.success_trend_cap is not None else back_cap
        for side in list(gambles):
            up, down = gains.get(side, 0), losses.get(side, 0)
            up_capped, down_capped = min(push_cap, up), max(-back_cap, down)
            gambles[side] = up_capped + down_capped
            if up_capped != up:
                msgs.append(f"各路奇招互相牽扯，{names.get(side, side)}這一回合成了的放手一搏合起來只把戰線推前了{shove_size(up_capped)}。")
            if down_capped != down:
                msgs.append(f"各路奇招互相牽扯，{names.get(side, side)}這一回合失手的放手一搏合起來只讓戰線退了{shove_size(down_capped)}。")
    gamble_delta = sum((1 if side == first else -1) * d for side, d in gambles.items())
    push = 0.0
    if counts[first] or counts[second]:
        mine = force[first] / math.sqrt(counts[first]) * diversity(instance, moves, first, tuning) if counts[first] else 0.0
        theirs = force[second] / math.sqrt(counts[second]) * diversity(instance, moves, second, tuning) if counts[second] else 0.0
        if not counts[second]:
            push = tuning.push_max
        elif not counts[first]:
            push = -tuning.push_max
        elif mine + theirs > 0:
            push = tuning.push_max * (mine - theirs) / (mine + theirs)
        sides = "；".join(
            f"{names[side]}：" + "・".join(f"{m} {round(mixes[side][m] * 100)}%" for m in MOVES)
            for side in sides3 if mixes[side]  # 三方混戰多寫守軍那一格
        )
        # 這一行放在這一回合訊息的最前面（只進戰報，場景上拿掉，見 without_mix_line）；推了多少照 shove 的說法，數字記在 RoundSwing.fixed
        leader = names[first] if round(push) > 0 else names[second]
        moved = f"三招交鋒，戰線往{leader}那邊推了{shove_size(round(push))}" if round(push) else "三招交鋒，兩軍持平"
        msgs.insert(0, f"{sides}（{moved}）")
    instance.trend = max(0, min(100, instance.trend + round(push) + gamble_delta + fall_delta))
    for side in (first, second):  # 這一回合發動的招，一招一行（放在固定句之後，回合原因之前）
        msgs.extend(fired.get(side, []))
    if tactic is not None:
        gained = instance.trend - trend_before
        for q in instance.participants.values():
            if q.kit is not None and not q.eliminated:
                won = (gained > 0 if q.faction == first else gained < 0) and q.faction != GUARD  # 助守的人沒有戰線
                tactics.war_close(q.kit, won, tactic, _war_rng(instance, q.name, rnd_no, "收"))
        for q, e in escorts:
            if e.kit is not None and e.fallen_round is None:
                won = gained > 0 if q.faction == first else gained < 0
                tactics.war_close(e.kit, won, tactic, _war_rng(instance, escort_key(q.name), rnd_no, "收"))
    instance.last_mix = mixes
    instance.round_number += 1
    # 這一回合為什麼往哪邊推（試玩回饋 2026-10-08：全是官軍卻輸了，卻看不出為什麼）：放在場景上看得到的第一行
    auto = {side: sum(1 for n in moves if factions[n] == side and n in instance.round.auto_picked) for side in (first, second)}
    leads = _leads(instance, shares, mixes, tuning, push, (first, second))
    causes = round_causes(names, (first, second), push, counts, mixes, coefs, gambles, auto, fitness, leads, tuning.lead_crowd)
    msgs.insert(1 if counts[first] or counts[second] else 0, round_line(names, (first, second), trend_before, instance.trend, causes))
    instance.swings.append(RoundSwing(
        round=instance.round_number, delta=instance.trend - trend_before, causes="；".join(causes), fixed=round(push),
    ))
    if three:  # 三方混戰（裁決 22）：偏離中線不收場，守將倒下那一回合當場收場
        decisive = keeper is not None and keeper.fallen_round is not None
    else:
        decisive = abs(instance.trend - CENTER) >= definition.decisive_margin
    if decisive or instance.round_number >= total_rounds(definition):
        msgs += _record_outcome(instance, decide_outcome(instance, definition))
        instance.outcome_reason = outcome_reason(instance, definition)
        if instance.outcome_reason:
            msgs.append(instance.outcome_reason)
    else:
        # 只往後換：回合上限之前就開打的舊資料，round_number 從 0 數起，不能把幕倒退回去
        next_act = min(instance.round_number // definition.rounds_per_act, len(definition.acts) - 1)
        if next_act > instance.act_index:
            instance.act_index = next_act
            act = current_act(instance, definition)
            msgs.append(f"【{act.title}】{act_text(instance, definition)}")
    instance.rounds.append(BattleRoundRecord(
        act_index=act_index, round_number=instance.round_number, resolved_real=now,
        actions=dict(instance.round.pending_actions), custom_texts=dict(instance.round.custom_texts),
        success_rates=dict(instance.round.success_rates), messages=list(msgs), trend_after=instance.trend,
    ))
    del instance.tales[:-TALES_KEPT]  # 沒有伺服器補劇情（假人程式、測試、腳本）時不會一直長
    note_sworn(instance)  # 並肩作戰（結義第二批）：記下同一方出過手的兄弟；沒人結義什麼都不動
    instance.round = BattleRound(opened_real=now)
    call_orders(instance, definition, tuning)  # 下一回合的將令（收場了就清掉）
    return msgs


def _war_rng(instance: BattleInstance, name: str, round_: int, what: str = "") -> random.Random:
    """決戰裡本命戰法的亂數：自己一份，不碰回合結算的 rng（沒帶戰法的人一場打下來一個字都不變）。"""
    return random.Random(f"決戰|{instance.battle_id}|{instance.record_id}|{round_}|{name}|{what}")


TALES_KEPT = 60  # 等著補劇情的放手一搏最多留幾筆（一回合二十人搏也留得下三回合）


class _Hit(NamedTuple):
    """一次點名成了的放手一搏，等這一圈結算完才扣被點名的人（_land_hit）。index 是訊息先佔好的位置。"""

    index: int
    attacker: str
    target: str
    want: float
    pin: bool
    story: str
    side_name: str
    delta: int
    damage: float
    text: str = ""  # 玩家寫的那一句（沒有現成劇情時記一筆等著補，GambleTale）
    push: bool = True  # 括號裡寫不寫推了戰線（三方混戰助守的人沒有戰線可推，裁決 22）


def _harm(tuning: BattleTuning, q: BattleParticipant, want: float, harmed: dict[str, float]) -> float:
    """別人這一回合打掉 q 的氣血：不超過他剩的、也不超過這一回合被打的上限（target_round_cap，免得被圍毆秒殺）。"""
    room = q.neili_cap * tuning.target_round_cap - harmed.get(q.name, 0.0)
    hit = max(0.0, min(want, room, q.neili))
    q.neili -= hit
    q.hurt_taken += hit
    harmed[q.name] = harmed.get(q.name, 0.0) + hit
    return hit


def _fell(instance: BattleInstance, q: BattleParticipant, msgs: list[str]) -> None:
    if q.neili <= 0 and not q.eliminated:
        q.eliminated = True
        q.fell_round = instance.round_number + 1
        msgs.append(f"{q.name}氣血耗盡，倒在戰場上，退出了這場戰鬥（轉為觀戰）。")


def _land_hit(
    instance: BattleInstance, tuning: BattleTuning, hit: _Hit, harmed: dict[str, float], msgs: list[str],
) -> tuple[str, str, str]:
    """點名的放手一搏成了：扣被點名的人、記帳；險招成了他下一回合被牽制。回傳那一搏的訊息（劇情＋括號裡的數字），
    加上沒有現成劇情時先播的固定句與括號裡的數字（等著補劇情，GambleTale；有劇情時兩個都是空字串）。"""
    q, me = instance.participants[hit.target], instance.participants[hit.attacker]
    dealt = _harm(tuning, q, hit.want, harmed)
    me.hurt_dealt += dealt
    if dealt >= 0.5:
        me.hits_landed += 1
    pinned_now = hit.pin and q.neili > 0
    if pinned_now:
        q.pinned_round = instance.round_number + 2  # 這一回合是第 round_number＋1 回合，牽制的是下一回合
    lead = f"{shove(hit.side_name, hit.delta)}，" if hit.push else ""
    numbers = f"{lead}{q.name}氣血 -{round(dealt)}，自己氣血 -{round(hit.damage)}"
    fixed = "" if hit.story else f"{hit.attacker}這一搏成功了，正中{q.name}！{numbers}。"
    line = f"{hit.story}（{numbers}）" if hit.story else fixed
    if pinned_now:
        line += f"{q.name}被牽制住了，下一回合只能固守。"
    _fell(instance, q, msgs)
    return line, fixed, numbers if fixed else ""


def _focus_fire(
    instance: BattleInstance, tuning: BattleTuning, moves: dict[str, str], factions: dict[str, str],
    armies: tuple[str, ...], names: dict[str, str], act_index: int, harmed: dict[str, float],
) -> list[str]:
    """引人注目：對面這一回合每一個出強攻的人，另外有 focus_per_attacker 的傷害平分到這一邊這一幕顯眼的人身上
    （每人最多他上限的 focus_cap，也受 target_round_cap 夾）。三方混戰（armies 三格，裁決 22）自己以外兩格都是對面。"""
    out: list[str] = []
    for side in armies:
        enemies = [a for a in armies if a != side]
        attackers = sum(1 for n, m in moves.items() if factions.get(n) in enemies and m == "強攻")
        enemy = "、".join(  # 誰的強攻（兩軍對打只有另一軍）
            names.get(e, e) for e in enemies if any(factions.get(n) == e and m == "強攻" for n, m in moves.items()))
        marked = [
            q for q in instance.participants.values()
            if q.faction == side and not q.eliminated and not q.away and instance.marked.get(q.name) == act_index
        ]
        if not attackers or not marked or tuning.focus_per_attacker <= 0:
            continue
        each = tuning.focus_per_attacker * attackers / len(marked)
        landed = []
        for q in marked:
            dealt = _harm(tuning, q, min(each, q.neili_cap * tuning.focus_cap), harmed)
            if dealt >= 0.5:
                landed.append(f"{q.name}氣血 -{round(dealt)}")
        if landed:
            out.append(f"{enemy}的強攻盯著顯眼的人打：{'、'.join(landed)}。")
        for q in marked:
            _fell(instance, q, out)
    return out


def _strike_commanders(
    instance: BattleInstance, tuning: BattleTuning, moves: dict[str, str], factions: dict[str, str],
    armies: tuple[str, str], names: dict[str, str], chief_hits: list[tuple[str, str, int, int, str, str, int, float, str]],
    msgs: list[str], harmed: dict[str, float], rnd_no: int, tale,
) -> tuple[list[str], int]:
    """上陣的大勢人物這一回合挨的打（龍頭上陣）：對面每一個出強攻的（含對面的人物）照集火打他 focus_per_attacker，點名他的放手一搏
    成了打掉他池子的 hit_base＋風險×hit_per_risk（最多 hit_max）；一回合最多 round_cap。同一邊出固守的人替他擋掉一部分（guard_per、
    盾陣 guard_role，最多 guard_cap），擋下來的平分給他們（照 _harm 夾）。池子打光就敗走：戰局往對面推 fall_push，最後一擊的人記 slew。
    點名那幾句填回 msgs 先佔好的位置；回傳其餘的句子與敗走推了多少（正是往第一方）。"""
    gen = tuning.generals
    out: list[str] = []
    shove_total = 0
    first = armies[0]
    for c in [c for c in instance.commanders if c.fallen_round is None and c.faction in armies]:
        enemy = armies[1] if c.faction == first else first
        guards = [
            q for n, m in moves.items() if m == "固守" and (q := instance.participants.get(n)) is not None
            and q.faction == c.faction and not q.eliminated
        ]
        share = min(gen.guard_cap, sum(gen.guard_role if q.role == "con" else gen.guard_per for q in guards))
        room = c.neili_cap * gen.round_cap
        last_hitter = ""

        def strike(want: float) -> tuple[float, float]:
            """打他 want：擋掉的那一份平分給固守的人，回傳（他掉的, 護住的）。"""
            nonlocal room
            blocked = want * share
            for q in guards:
                _harm(tuning, q, blocked / len(guards), harmed)
            hit = max(0.0, min(want - blocked, room, c.neili))
            c.neili -= hit
            room -= hit
            return hit, blocked

        for attacker, chief, risk, index, story, side_name, delta, damage, text in chief_hits:
            if chief != c.name:
                continue
            hit, blocked = strike(c.neili_cap * min(gen.hit_max, gen.hit_base + risk * gen.hit_per_risk))
            me = instance.participants.get(attacker)
            if me is not None and hit >= 0.5:
                me.hits_landed += 1
                me.hurt_dealt += hit
                last_hitter = attacker
            guard = f"（{len(guards)} 人固守護住了 {round(blocked)}）" if blocked >= 0.5 else ""
            numbers = f"{shove(side_name, delta)}，{c.name}氣血 -{round(hit)}{guard}，自己氣血 -{round(damage)}"
            fixed = "" if story else f"{attacker}這一搏成功了，正中{c.name}！{numbers}。"
            msgs[index] = f"{story}（{numbers}）" if story else fixed
            if fixed and text and me is not None:
                tale(attacker, me, text, True, c.name, fixed, numbers)
        attackers = [n for n, m in moves.items() if factions.get(n) == enemy and m == "強攻"]
        if attackers and tuning.focus_per_attacker > 0 and c.neili > 0:
            hit, blocked = strike(tuning.focus_per_attacker * len(attackers))
            if hit >= 0.5 or blocked >= 0.5:
                guard = f"，{len(guards)} 人固守護住了 {round(blocked)}" if blocked >= 0.5 else ""
                out.append(f"{names.get(enemy, enemy)}的強攻直撲{c.name}：{c.name}氣血 -{round(hit)}{guard}。")
        if c.neili <= 0:
            c.neili = 0.0
            c.fallen_round = rnd_no
            if not last_hitter:  # 沒有點名的最後一擊：算對面出強攻的人裡份量最重的那一個
                best = max(
                    (q for n in attackers if (q := instance.participants.get(n)) is not None),
                    key=lambda q: (q.scores.get("強攻", 0.0), q.name), default=None,
                )
                last_hitter = best.name if best is not None else ""
            c.felled_by = last_hitter
            if (q := instance.participants.get(last_hitter)) is not None:
                q.slew += 1
            sign = 1 if enemy == first else -1
            shove_total += sign * gen.fall_push
            size = shove_size(gen.fall_push)
            line = (FALL_BY_LINE.format(name=c.name, who=last_hitter, side=names.get(c.faction, c.faction), enemy=names.get(enemy, enemy), size=size)
                    if last_hitter else FALL_LINE.format(name=c.name, side=names.get(c.faction, c.faction), enemy=names.get(enemy, enemy), size=size))
            out.append(line)
    return out, shove_total


def _owner(key: str) -> str:
    """出招的鍵是誰的：隨行同伴的鍵（escort_key）算主人，其餘就是自己。"""
    head = ESCORT_KEY.format(owner="")
    return key[len(head):] if key.startswith(head) else key


def blow_side(dealt: dict[str, float], trend: int, armies: tuple[str, str], seed: str) -> str:
    """三方混戰守將倒下那一回合，最後一刀算哪一軍（裁決 22）：這一回合打守將打得多的那一軍；一樣多看這一回合開打時戰線偏向誰
    （trend 以 armies[0] 為正向）；戰線也在中線，照 seed 擲（自己的亂數，不碰回合結算的 rng）。"""
    a, b = armies
    if abs(dealt.get(a, 0.0) - dealt.get(b, 0.0)) > 1e-9:
        return a if dealt.get(a, 0.0) > dealt.get(b, 0.0) else b
    if trend != CENTER:
        return a if trend > CENTER else b
    return random.Random(seed).choice(armies)


def _strike_guard(
    instance: BattleInstance, tuning: BattleTuning, keeper: Commander, moves: dict[str, str], factions: dict[str, str],
    armies: tuple[str, str], names: dict[str, str], chief_hits: list[tuple[str, str, int, int, str, str, int, float, str]],
    msgs: list[str], harmed: dict[str, float], rnd_no: int, tale, trend: int,
) -> list[str]:
    """三方混戰的守將這一回合挨的打（裁決 22，照單方攻中立地時守將池子的扣法）：兩軍每一個出強攻的（隨行同伴算主人的）打他
    focus_per_attacker，點名他的放手一搏成了打掉池子的 hit_base＋風險×hit_per_risk（最多 hit_max）；**一軍打的再乘這一回合開打時
    戰線往自己偏多少**（自己那一頭的戰局 ÷ 50：中線 ×1、壓到底 ×2、被壓到底 ×0）。助守的人出固守替他擋（guard_per、盾陣 guard_role，
    最多 guard_cap，擋下的平分給他們）；一回合最多 round_cap，兩軍合起來超過時照比例分。池子歸零那一回合：打得多的那一軍補上最後一刀
    （blow_side），那一軍這一回合打守將打得最多的參戰者記 slew、Commander.felled_by；SiegeInfo.blow 記那一軍。不推戰線。
    點名那幾句填回 msgs 先佔好的位置；回傳其餘的句子。"""
    gen = tuning.generals
    first, second = armies
    lean = {first: trend / CENTER, second: (100 - trend) / CENTER}
    helpers = _guards(instance, moves, GUARD)
    share = min(gen.guard_cap, sum(gen.guard_role if q.role == "con" else gen.guard_per for q in helpers))
    per: dict[str, dict[str, float]] = {a: {} for a in armies}  # 一軍 → 參戰者 → 這一回合想打掉多少（乘過戰線、還沒扣擋）
    focus: dict[str, float] = {a: 0.0 for a in armies}
    named = []
    for attacker, chief, risk, index, story, side_name, delta, damage, text in chief_hits:
        me = instance.participants.get(attacker)
        if chief != keeper.name or me is None or me.faction not in armies:
            continue
        want = keeper.neili_cap * min(gen.hit_max, gen.hit_base + risk * gen.hit_per_risk) * lean[me.faction]
        per[me.faction][attacker] = per[me.faction].get(attacker, 0.0) + want
        named.append((attacker, me, index, story, side_name, delta, damage, text, want))
    for n, m in moves.items():
        side = factions.get(n)
        if m != "強攻" or side not in armies or tuning.focus_per_attacker <= 0:
            continue
        want = tuning.focus_per_attacker * lean[side]
        per[side][_owner(n)] = per[side].get(_owner(n), 0.0) + want
        focus[side] += want
    raw = {a: sum(per[a].values()) for a in armies}
    blocked = sum(raw.values()) * share
    if blocked > 0 and helpers:
        for q in helpers:
            _harm(tuning, q, blocked / len(helpers), harmed)
    total = sum(raw.values()) * (1 - share)
    room = min(keeper.neili_cap * gen.round_cap, keeper.neili)
    scale = (1 - share) * (min(1.0, room / total) if total > 0 else 0.0)  # 想打的 → 真的打掉的
    dealt = {a: raw[a] * scale for a in armies}
    keeper.neili = max(0.0, keeper.neili - sum(dealt.values()))
    out: list[str] = []
    for attacker, me, index, story, side_name, delta, damage, text, want in named:
        hit = want * scale
        if hit >= 0.5:
            me.hits_landed += 1
            me.hurt_dealt += hit
        cover = f"（{len(helpers)} 人固守護住了 {round(want * share)}）" if want * share >= 0.5 else ""
        numbers = f"{shove(side_name, delta)}，{keeper.name}氣血 -{round(hit)}{cover}，自己氣血 -{round(damage)}"
        fixed = "" if story else f"{attacker}這一搏成功了，正中{keeper.name}！{numbers}。"
        msgs[index] = f"{story}（{numbers}）" if story else fixed
        if fixed and text:
            tale(attacker, me, text, True, keeper.name, fixed, numbers)
    for a in armies:
        if focus[a] <= 0:
            continue
        cover = focus[a] * share
        out.append(GUARD_HIT_LINE.format(
            side=names.get(a, a), guard=keeper.name, hp=round(focus[a] * scale),
            shield=GUARD_SHIELD.format(n=len(helpers), hp=round(cover)) if cover >= 0.5 else "",
        ))
    if keeper.neili > 1e-6:
        return out
    keeper.neili, keeper.fallen_round = 0.0, rnd_no
    side = blow_side(dealt, trend, armies, f"最後一刀|{instance.battle_id}|{instance.record_id}|{rnd_no}")
    crew = [(amount, instance.participants[n]) for n, amount in per[side].items() if n in instance.participants]
    best = max(crew, key=lambda row: (row[0], row[1].scores.get("強攻", 0.0), row[1].name), default=None)
    who = best[1].name if best is not None else ""
    keeper.felled_by = who
    if best is not None:
        best[1].slew += 1
    if instance.siege is not None:
        instance.siege.blow = side
    line = BLOW_LINE if who else BLOW_LINE_NOBODY
    out.append(line.format(who=who, side=names.get(side, side), guard=keeper.name))
    return out


def _guards(instance: BattleInstance, moves: dict[str, str], side: str) -> list[BattleParticipant]:
    """這一回合這一邊出固守、還站著的參戰者（替人物、同伴擋打）。"""
    return [
        q for n, m in moves.items() if m == "固守" and (q := instance.participants.get(n)) is not None
        and q.faction == side and not q.eliminated
    ]


def _strike_escorts(
    instance: BattleInstance, tuning: BattleTuning, moves: dict[str, str], factions: dict[str, str],
    armies: tuple[str, str], names: dict[str, str], hits: list[tuple[str, str, int, int, str, str, int, float, str]],
    msgs: list[str], harmed: dict[str, float], rnd_no: int, tale, shields: dict[str, float], extra: tuple[str, ...] = (),
) -> tuple[list[str], int]:
    """隨行的同伴這一回合挨的打（歷史武將同行第五節，照 _strike_commanders 的規矩）：點名他的放手一搏成了打掉他池子的
    hit_base＋風險×hit_per_risk（最多 hit_max）；對面每一個出強攻的照 focus_per_attacker 算一份，平分到這一邊站著的同伴身上；
    一回合最多 round_cap；同一邊出固守的人照 guard_per／guard_role 替他擋（最多 guard_cap），擋下來的平分給他們。
    集火打到的合成一句（ESCORT_FOCUS_LINE，「讀得下去」），點名與敗走各一句。池子打光就敗走：戰局往對面推 escort_fall_push，
    最後一擊的人記 slew。回傳其餘的句子與敗走推了多少（正是往第一方）。
    extra 是兩軍以外也算對面的格（三方混戰的守軍 GUARD，裁決 22：守將與助守的人的強攻也打得到兩軍的同伴）。"""
    gen = tuning.generals
    first = armies[0]
    out: list[str] = []
    shove_total = 0
    standing = escorts_on_field(instance, armies)
    rooms = {p.name: e.neili_cap * gen.round_cap for p, e in standing}
    last: dict[str, str] = {}

    def strike(p: BattleParticipant, e: Escort, want: float) -> tuple[float, float, int]:
        guards = _guards(instance, moves, p.faction)
        share = min(gen.guard_cap, sum(gen.guard_role if q.role == "con" else gen.guard_per for q in guards))
        blocked = want * share
        for q in guards:
            _harm(tuning, q, blocked / len(guards), harmed)
        hit = max(0.0, min((want - blocked) * shields.get(p.name, 1.0), rooms[p.name], e.neili))
        e.neili -= hit
        rooms[p.name] -= hit
        return hit, blocked, len(guards)

    for attacker, owner, risk, index, story, side_name, delta, damage, text in hits:
        pair = next(((p, e) for p, e in standing if p.name == owner), None)
        me = instance.participants.get(attacker)
        if pair is None:  # 點名之後同一回合先敗走了：照沒點到寫
            msgs[index] = story or f"{attacker}這一搏成功了！{shove(side_name, delta)}，自己氣血 -{round(damage)}。"
            continue
        p, e = pair
        hit, blocked, n = strike(p, e, e.neili_cap * min(gen.hit_max, gen.hit_base + risk * gen.hit_per_risk))
        if me is not None and hit >= 0.5:
            me.hits_landed += 1
            me.hurt_dealt += hit
            last[p.name] = attacker
        guard = f"（{n} 人固守護住了 {round(blocked)}）" if blocked >= 0.5 else ""
        numbers = f"{shove(side_name, delta)}，{e.name}氣血 -{round(hit)}{guard}，自己氣血 -{round(damage)}"
        fixed = "" if story else f"{attacker}這一搏成功了，正中{e.name}！{numbers}。"
        msgs[index] = f"{story}（{numbers}）" if story else fixed
        if fixed and text and me is not None:
            tale(attacker, me, text, True, e.name, fixed, numbers)
    for side in armies:
        enemy = armies[1] if side == first else first
        foes = (enemy, *extra)
        attackers = [n for n, m in moves.items() if factions.get(n) in foes and m == "強攻"]
        mine = [(p, e) for p, e in standing if p.faction == side and e.neili > 0]
        if not attackers or not mine or tuning.focus_per_attacker <= 0:
            continue
        each = tuning.focus_per_attacker * len(attackers) / len(mine)
        total, hurt = 0.0, 0
        for p, e in mine:
            hit, _, _ = strike(p, e, each)
            total += hit
            hurt += hit >= 0.5
        if hurt:
            who = "、".join(names.get(f, f) for f in foes if any(factions.get(n) == f for n in attackers))
            out.append(ESCORT_FOCUS_LINE.format(enemy=who, side=names.get(side, side), n=hurt, hp=round(total)))
    for p, e in standing:
        if e.neili > 0:
            continue
        enemy = armies[1] if p.faction == first else first
        foes = (enemy, *extra)
        e.neili, e.fallen_round = 0.0, rnd_no
        hitter = last.get(p.name, "")
        if not hitter:  # 沒有點名的最後一擊：算對面出強攻的人裡份量最重的那一個（同人物）
            best = max(
                (q for n, m in moves.items() if m == "強攻" and (q := instance.participants.get(n)) is not None and q.faction in foes),
                key=lambda q: (q.scores.get("強攻", 0.0), q.name), default=None,
            )
            hitter = best.name if best is not None else ""
        e.felled_by = hitter
        if (q := instance.participants.get(hitter)) is not None:
            q.slew += 1
        shove_total += (1 if enemy == first else -1) * gen.escort_fall_push
        out.append(ESCORT_FALL_LINE.format(owner=p.name, name=e.name, enemy=names.get(enemy, enemy), size=shove_size(gen.escort_fall_push)))
    return out, shove_total


def find_escort(instance: BattleInstance, definition: BattleDef, name: str, text: str) -> tuple[BattleParticipant, Escort] | None:
    """放手一搏的文字裡點名的對面隨行同伴（同 find_commander：名字 2 字以上、最先出現的那一個）；只認還在陣上的（主人沒離開大區）。"""
    me = instance.participants.get(name)
    armies = {f.id for f in definition.factions}
    if me is None or me.faction not in armies:
        return None
    found = [
        (text.find(q.escort.name), -len(q.escort.name), q.name) for q in instance.participants.values()
        if q.escort is not None and q.escort.fallen_round is None and not q.away and q.faction in armies
        and q.faction != me.faction and len(q.escort.name) >= 2 and q.escort.name in text
    ]
    if not found:
        return None
    owner = instance.participants[min(found)[2]]
    return owner, owner.escort


def guard_alias(c: Commander) -> str:
    """中立地的守將（隊伍當的，fid 是「squad:…」，顯示名是「隊伍名（守將）」）放手一搏也點得到他的另一個叫法：拿掉後綴的隊伍名本身
    （FB-542）。其他人物沒有，是空字串。"""
    return c.name.removesuffix(GUARD_SUFFIX) if c.fid.startswith("squad:") and c.name.endswith(GUARD_SUFFIX) else ""


def _alias_at(alias: str, text: str, instance: BattleInstance) -> int:
    """隊伍名在文字裡最先出現的位置（沒有是 -1）。隊伍名只是別人名字的一部分時不算（「劫道響馬王」是一位參戰者、或另一位人物的名號：
    寫的是他，不是守將）：先把那些比它長、又含著它的名號蓋掉再找；蓋掉用同樣長度的填字，位置不變。"""
    longer = sorted(
        {n for n in (*instance.participants, *(c.name for c in instance.commanders)) if len(n) > len(alias) and alias in n},
        key=len, reverse=True,
    )
    for n in longer:
        text = text.replace(n, "\u3000" * len(n))
    return text.find(alias)


def find_commander(instance: BattleInstance, definition: BattleDef, name: str, text: str) -> Commander | None:
    """放手一搏的文字裡點名的對面上陣人物（同 find_target：名字 2 字以上、最先出現的那一個）；只認還在陣上的。
    三方混戰（裁決 22）的守將站 GUARD 那一格：兩軍的人點得到他。中立地的守將顯示名帶著「（守將）」，照抄整個名字、或只寫隊伍名
    本身都算點名到他（FB-542；guard_alias，隊伍名也要 2 字以上，也不能只是別人名字的一部分）。"""
    me = instance.participants.get(name)
    armies = set(fields(instance, definition))
    if me is None or me.faction not in armies:
        return None
    found = []
    for i, c in enumerate(instance.commanders):
        if c.faction not in armies or c.faction == me.faction or c.fallen_round is not None or len(c.name) < 2:
            continue
        if c.name in text:
            found.append((text.find(c.name), -len(c.name), i))
        alias = guard_alias(c)
        if len(alias) >= 2 and (at := _alias_at(alias, text, instance)) >= 0:
            found.append((at, -len(alias), i))
    return instance.commanders[min(found)[2]] if found else None


def _leads(
    instance: BattleInstance, shares: dict[str, list[tuple[float, str, str]]], mixes: dict[str, dict[str, float]],
    tuning: BattleTuning, push: float, armies: tuple[str, str],
) -> dict[str, tuple[str, str, int]]:
    """每一邊這一回合帶頭出固定招的人：出得最多的那一招裡力量最大的那一個（名號, 招, 出這一招的人數）。
    推力往哪邊，那一邊帶頭的人記一個 led_rounds（戰報寫）。帶頭只從自己下令的人裡挑、人數也只算他們：逾時被代為固守的
    （round.auto_picked）照記固守的基本戰功，但不算帶頭、回合原因與勝負的關鍵都不寫他；這一招都是代選的就沒有帶頭的人（FB-181）。"""
    out: dict[str, tuple[str, str, int]] = {}
    auto = set(instance.round.auto_picked)
    for side in armies:
        if not shares[side]:
            continue
        move = _main_move(mixes[side])
        crew = [row for row in shares[side] if row[2] == move and row[1] not in auto]
        if not crew:
            continue
        _, lead, _ = max(crew, key=lambda row: (row[0], row[1]))
        out[side] = (lead, move, len(crew))
    shift = round(push)
    winner = armies[0] if shift > 0 else armies[1] if shift < 0 else None
    if winner in out:
        instance.participants[out[winner][0]].led_rounds += 1
    return out


def lead_clause(lead: tuple[str, str, int], crowd: int, with_move: bool = True) -> str:
    """「張三帶頭強攻」／「張三等 4 人結成強攻陣勢」；前一句已經寫了招（剋住的那一句）就不再寫招：「張三一馬當先」／「張三等 4 人結成陣勢」。"""
    name, move, count = lead
    if count >= crowd:
        return f"{name}等 {count} 人結成{move if with_move else ''}陣勢"
    return f"{name}帶頭{move}" if with_move else f"{name}一馬當先"


COUNTER_VERB = {"固守": "擋住了"}  # 待 joy 潤：剋住的不是兩邊出最多的招時那一句，固守寫「擋住了」，其餘「剋住了」


def counter_clause(w: str, lo: str, win_mix: dict[str, float], lose_mix: dict[str, float]) -> tuple[str, bool]:
    """剋住的那一句與它寫的是不是兩邊出最多的招（FB-365）。兩邊最多的那一招真的相剋就照舊寫它們（「黃巾的固守剋住了官軍的強攻」）；
    不然（例：官軍三強攻兩固守對黃巾三強攻，剋住的其實是那兩個固守）寫真正剋住的那一對：贏的一方出的招 m 剋對面出的 BEATS[m]，
    兩邊人數乘起來最多的那一對（一樣多照 MOVES 的順序）；一對都沒有（剋制係數的差來自別處）寫 COUNTER_PLAIN。"""
    mine, theirs = _main_move(win_mix), _main_move(lose_mix)
    if BEATS[mine] == theirs:
        return f"{w}的{mine}剋住了{lo}的{theirs}", True
    pairs = [(win_mix.get(m, 0.0) * lose_mix.get(BEATS[m], 0.0), m) for m in MOVES]
    weight, move = max(pairs, key=lambda p: p[0])
    if weight <= 0:
        return COUNTER_PLAIN.format(w=w, lo=lo), False
    return f"{w}的{move}{COUNTER_VERB.get(move, '剋住了')}{lo}的{BEATS[move]}", False


COUNTER_PLAIN = "{w}的招式壓過了{lo}"  # 待 joy 潤：剋制係數差得多、卻找不到哪一招剋哪一招時


def round_causes(
    names: dict[str, str], armies: tuple[str, str], push: float, counts: dict[str, int], mixes: dict[str, dict[str, float]],
    coefs: dict[str, list[float]], gambles: dict[str, int], auto: dict[str, int],
    fitness: dict[str, list[tuple[float, float]]] | None = None, leads: dict[str, tuple[str, str, int]] | None = None,
    crowd: int = 3,
) -> list[str]:
    """這一回合戰局為什麼這樣走，寫成幾句話（試玩回饋 2026-10-08：輸了要看得懂為什麼）。都照結算的數字挑，不叫模型：
    - 三招交鋒（推力不是 0）：對面沒人正面出招 → 一邊壓上；平均剋制係數差到 0.2 → 誰的哪招剋住誰的哪招；
      人數差到 1.5 倍 → 人多；都不是 → 份量（武藝）與氣血狀態，兩者裡差得多的那一個（fitness 是每個人的（份量, 氣血狀態））；
    - 放手一搏：每一邊這一回合賭贏賭輸的淨推動（失手寫倒退多少）；
    - 逾時沒出手、被系統代為固守的人數（固守會被奇襲剋）。
    leads 給了，佔上風那一邊帶頭出固定招的人接在第一句後面（Joy 2026-10-10：「跟從預設選項的玩家……應該也要有出場機會」）。"""
    out: list[str] = []
    shift = round(push)
    if shift:
        win, lose = (armies[0], armies[1]) if shift > 0 else (armies[1], armies[0])
        w, lo = names.get(win, win), names.get(lose, lose)
        lead = (leads or {}).get(win)
        tail = f"，{lead_clause(lead, crowd)}" if lead else ""
        if not counts[lose]:
            out.append(f"{lo}沒有人正面出陣迎戰，{w}放手壓了上去{tail}")
        else:
            avg = {side: sum(coefs[side]) / len(coefs[side]) for side in armies if coefs[side]}
            if avg.get(win, 1.0) - avg.get(lose, 1.0) >= 0.2:
                said, main = counter_clause(w, lo, mixes[win], mixes[lose])
                tail = f"，{lead_clause(lead, crowd, with_move=not main)}" if lead else ""  # 剋住的不是帶頭那一招時照寫招
                out.append(said + tail)
            elif counts[win] >= 1.5 * counts[lose]:
                out.append(f"{w}人多勢眾（{counts[win]} 人對 {counts[lose]} 人）{tail}")
            else:
                out.append(_edge(w, lo, (fitness or {}).get(win, []), (fitness or {}).get(lose, [])) + tail)
    for side in armies:
        delta = gambles.get(side, 0)
        if delta < 0:
            out.append(f"{names.get(side, side)}有人放手一搏失手，戰線退了{shove_size(delta)}")
        elif delta > 0:
            out.append(f"{names.get(side, side)}有人放手一搏得手，把戰線推前了{shove_size(delta)}")
    for side in armies:
        if auto.get(side):
            out.append(f"{names.get(side, side)}有 {auto[side]} 人遲遲沒有下令，只能原地固守")
    return out


def _edge(w: str, lo: str, mine: list[tuple[float, float]], theirs: list[tuple[float, float]]) -> str:
    """出招沒剋、人數也差不多時，贏的一方贏在哪：平均份量（武藝）與平均氣血狀態，比例差得多的那一個。"""
    def avg(rows: list[tuple[float, float]], i: int) -> float:
        return sum(r[i] for r in rows) / len(rows) if rows else 0.0

    ratio = [avg(mine, i) / avg(theirs, i) if avg(theirs, i) > 0 else math.inf for i in (0, 1)]
    if ratio[1] > ratio[0]:
        return f"{lo}氣血耗損，漸漸撐不住{w}"
    return f"{w}的武藝更勝一籌"


def round_line(names: dict[str, str], armies: tuple[str, str], before: int, after: int, causes: list[str]) -> str:
    """場景上這一回合的第一行：誰佔了上風、把戰線往他那邊推了多少（shove 的說法，不寫數字；數字畫在戰局條上），再接原因。"""
    if after != before:
        side = names.get(armies[0], armies[0]) if after > before else names.get(armies[1], armies[1])
        head = f"這一回合{side}佔了上風，把戰線往自己這邊推了{shove_size(after - before)}"
    else:
        head = "這一回合兩軍相持不下，戰線沒有動"
    return head + ("：" + "；".join(causes) + "。" if causes else "。")


MERIT_TOP = 3  # 戰局條旁「本場戰功」每一邊列幾個人
MERIT_PARTS = (  # 戰功的每一項怎麼寫（順序就是戰報與畫面上的順序）
    ("acted", "出手 {n} 回合"), ("held", "代為固守 {n} 回合"), ("led", "帶頭佔上風 {n} 回合"), ("gamble", "搏成 {n} 次"),
    ("hit", "點名打傷 {n} 次"), ("stood", "被盯上撐住 {n} 回合"), ("slew", "擊退大將 {n} 位"),
)


def merit_parts(p: BattleParticipant) -> list[str]:
    counts = merit_counts(p)
    return [text.format(n=counts[key]) for key, text in MERIT_PARTS if counts[key]]


def merit_ranking(instance: BattleInstance, tuning: BattleTuning, side: str) -> list[tuple[BattleParticipant, int]]:
    """一邊的參戰者照戰功排（同分照名號，免得每次刷新順序亂跳）。"""
    rows = [(p, merit(tuning, p)) for p in instance.participants.values() if p.faction == side]
    return sorted(rows, key=lambda row: (-row[1], row[0].name))


def top_merit(instance: BattleInstance, tuning: BattleTuning, side: str) -> BattleParticipant | None:
    """這一邊的首功：自己至少按過一招的人裡戰功最高、至少 1 分的那一個；一邊全員都沒按過就從缺。
    代為固守的回合照算戰功，但全程掛機的人不拿首功（PM 2026-10-10：認真打的人看了不服）。"""
    return next((p for p, m in merit_ranking(instance, tuning, side) if m > 0 and p.acted_rounds > 0), None)


def merit_board(
    instance: BattleInstance, tuning: BattleTuning, left: str, right: str, viewer: str | None,
) -> dict:
    """戰局條旁的「本場戰功」：兩邊各列前 MERIT_TOP 名（戰功 0 的不列）、看的人自己在自己那一邊排第幾、戰功怎麼來的。"""
    board: dict = {"me": None}
    for key, side in (("left", left), ("right", right)):
        ranking = merit_ranking(instance, tuning, side)
        board[key] = [{"name": p.name, "merit": m, "mine": p.name == viewer, "renown": list(p.renown),
                       **({"title": dict(p.title)} if p.title else {})}  # 稱號與官職：加入時戴的那一個（沒戴不寫這個鍵）
                      for p, m in ranking[:MERIT_TOP] if m > 0]
        for rank, (p, m) in enumerate(ranking, 1):
            if p.name == viewer:
                board["me"] = {"rank": rank, "of": len(ranking), "merit": m, "parts": merit_parts(p)}
    return board


def gauge(
    instance: BattleInstance, definition: BattleDef, viewer_side: str | None, timetable: bool,
    tuning: BattleTuning | None = None, viewer: str | None = None,
) -> dict:
    """決戰畫面的即時戰局條（Joy 2026-10-10 轉玩家反饋：「有辦法看即時戰局？」）：拔河，兩軍各佔一頭，數字只畫在這裡。

    左邊是看的人那一邊（兩軍以外的人看第一方在左）；lean 是「往左邊那一方偏多少」（0～100，100 是左邊大獲全勝），
    網頁把旗子畫在 100−lean：誰佔上風，旗子就被拉到誰那一頭。zones 是分勝負的那一截（時刻表決戰是偏離中線 BIG_WIN_MARGIN
    的大勝，其餘照 outcomes 的門檻），decisive 是偏離中線多少當場收場。rounds 是每一回合從哪裡到哪裡、誰佔上風。
    merit 是條旁的「本場戰功」（merit_board；viewer 是看的人的名號）。"""
    first, second = definition.factions[0].id, definition.factions[1].id
    names = side_names(instance, definition)  # 守將那一格寫守軍（FB-540）
    left = viewer_side if viewer_side in (first, second) else first
    right = second if left == first else first

    def lean(trend: int) -> int:
        return trend if left == first else 100 - trend

    def span(lo: int, hi: int) -> tuple[int, int]:  # 戰局座標的一段換成 lean 座標
        a, b = lean(lo), lean(hi)
        return min(a, b), max(a, b)

    zones: list[dict] = []
    if timetable:
        for side, (lo, hi) in ((first, (CENTER + BIG_WIN_MARGIN, 100)), (second, (0, CENTER - BIG_WIN_MARGIN))):
            a, b = span(lo, hi)
            zones.append({"from": a, "to": b, "side": "left" if side == left else "right", "label": f"{names[side]}大勝"})
    else:
        for o in definition.outcomes:
            if o.trend_min is None and o.trend_max is None or o.faction not in (first, second):
                continue
            a, b = span(o.trend_min if o.trend_min is not None else 0, o.trend_max if o.trend_max is not None else 100)
            zones.append({"from": a, "to": b, "side": "left" if o.faction == left else "right", "label": o.title})
    start = instance.trend_start if instance.trend_start is not None else (instance.trend if instance.phase == "muster" else CENTER)
    rounds, at = [], start
    for s in instance.swings:
        after = max(0, min(100, at + s.delta))
        mover = "tie" if after == at else ("left" if lean(after) > lean(at) else "right")
        rounds.append({"n": s.round, "from": lean(at), "to": lean(after), "side": mover})
        at = after
    now = lean(instance.trend)
    leader = left if now > CENTER else right if now < CENTER else None
    if instance.phase == "ended":
        caption = instance.outcome_title or "收場"
    elif instance.phase == "muster":
        caption = (f"集結中：開戰時戰線偏向{names[leader]}{shove_size(now - CENTER)}" if leader
                   else "集結中：開戰時戰線在正中間")
    elif leader is None:
        caption = "兩軍不分上下，戰線在正中間"
    else:
        gap = definition.decisive_margin - abs(now - CENTER)
        caption = f"{names[leader]}佔上風；再推{shove_size(gap)}就當場分出勝負"
    decisive = definition.decisive_margin
    keeper = next((c for c in instance.commanders if c.faction == GUARD), None) if melee(instance) else None
    if keeper is not None:  # 三方混戰（裁決 22）：偏離中線不收場（兩道細線畫在兩頭），說明寫守將還剩多少
        decisive = CENTER
        if instance.phase == "active":
            lead = MELEE_LEAD.format(side=names[leader]) if leader is not None else MELEE_EVEN
            caption = MELEE_CAPTION.format(lead=lead, guard=keeper.name, hp=round(keeper.neili), cap=round(keeper.neili_cap))
    return {
        "name": definition.name, "phase": instance.phase,
        "round": instance.round_number + (0 if instance.phase == "ended" else 1), "total": total_rounds(definition),
        "left": {"id": left, "name": names[left], "mine": viewer_side == left},
        "right": {"id": right, "name": names[right], "mine": viewer_side == right},
        "lean": now, "start": lean(start), "decisive": decisive, "zones": zones, "rounds": rounds,
        "caption": caption,
        "merit": merit_board(instance, tuning or BattleTuning(), left, right, viewer),
        **({"flags": flags} if (flags := title_flags(instance, left, right)) else {}),  # 稱號與官職的將旗：沒有人戴頭銜不寫這個鍵
    }


FLAG_TOP = 5  # 將旗：兩軍各列幾個（稱號與官職設計稿 v5 做法乙）
_GRADE_RANK = {"gold": 0, "zhu": 1, "ink": 2}


def title_flags(instance: BattleInstance, left: str, right: str) -> dict:
    """集結與戰局條上的將旗：兩軍各列戴頭銜的人（名號在前、官職在後，一樣高照加入時的戰力），最多 FLAG_TOP 個；都沒有是 {}。"""
    out = {}
    for key, side in (("left", left), ("right", right)):
        worn = [p for p in instance.participants.values() if p.faction == side and p.title.get("name")]
        worn.sort(key=lambda p: (_GRADE_RANK.get(p.title.get("grade", "ink"), 2), -p.power, p.name))
        if worn:
            out[key] = [{"name": p.name, "title": dict(p.title)} for p in worn[:FLAG_TOP]]
    return out


def overruled_reason(instance: BattleInstance, definition: BattleDef, lock_side: str | None, defender: str) -> str:
    """時刻表決戰收場時，伏筆鎖定的一方贏了、戰場上卻是另一方佔上風：勝負的關鍵改寫這一句（原本那一句寫的是戰場上的贏家）。
    戰場上的贏家跟最後的贏家是同一方就是空字串（照舊用 outcome_reason）。"""
    field, _ = result_at(instance.trend, definition, None, defender)
    winner, _ = result_at(instance.trend, definition, lock_side, defender)
    if field == winner:
        return ""
    name = next((f.name for f in definition.factions if f.id == field), field)
    return f"勝負的關鍵：戰場上{name}佔了上風，卻沒能扭轉大局。"


def _record_outcome(instance: BattleInstance, outcome: BattleOutcome) -> list[str]:
    """把終局記到戰鬥上（套用到共用賽季是呼叫端 engine.py 的事，見 BattleInstance 的欄位註解），
    回傳要給大家看的兩行。"""
    instance.phase = "ended"
    instance.outcome_title, instance.outcome_text = outcome.title, outcome.text
    if outcome.trend_min is not None or outcome.trend_max is not None:  # 有門檻的才是分出了勝負；最後那個保底是膠著
        instance.outcome_side = outcome.faction
        instance.outcome_margin = "大勝" if abs(instance.trend - CENTER) >= BIG_WIN_MARGIN else "險勝"
    instance.outcome_world_flags = list(outcome.world_flags_add)
    instance.outcome_trend_delta = dict(outcome.trend_delta)
    return [f"══ {outcome.title} ══", outcome.text]


def end_without_fighters(
    instance: BattleInstance, definition: BattleDef, now: float, tuning: BattleTuning | None = None,
) -> list[str]:
    """場上已經沒有任何還能打的人（沒人參戰、或全都倒下了）：
    沒有人能送出行動，round_is_complete 永遠不會成立，這場戰鬥就會永遠卡著——這時直接用
    內容最後那個無條件的保底結果（definition.outcomes[-1]，content.py::validate 保證它
    沒有門檻）收場，記錄方式跟 resolve_round 分出勝負時一樣。這裡沒有 LLM 潤色，收場的
    幾句話直接寫進 narrative_log。還有人在場、還在集結，什麼都不做、回傳空清單。
    什麼時候收：兩軍上過陣的人全都倒下了（倒下的人回不來）就當場收，不讓觀戰的人乾等這一回合逾時（手機介面自檢 U-08）；
    一個人都沒有、或還有人只是走開了大區（他可能回來、也可能有人晚到投效），照舊等這一回合逾時。"""
    armies = {f.id for f in definition.factions}
    if instance.phase != "active" or any(p.faction in armies for p in _active_participants(instance)):
        return []
    fought = [p for p in instance.participants.values() if p.faction in armies]
    all_fallen = bool(fought) and all(p.eliminated for p in fought)
    if not all_fallen and now - instance.round.opened_real < definition.round_seconds:
        return []
    msgs = ["戰場上已經沒有人還能出手，這場戰鬥就此收場。"] + _record_outcome(instance, definition.outcomes[-1])
    instance.narrative_log.append("\n".join(msgs))
    instance.round_number += 1  # 這一回合逾時過去了，也算一回合
    instance.rounds.append(BattleRoundRecord(
        act_index=instance.act_index, round_number=instance.round_number, resolved_real=now,
        messages=list(msgs), trend_after=instance.trend,
    ))
    instance.round = BattleRound(opened_real=now)
    return msgs


def decide_outcome(instance: BattleInstance, definition: BattleDef) -> BattleOutcome:
    """從戰局決定結果：照 definition.outcomes 的順序，取第一個戰局落在門檻內的。最後那個沒有門檻的保底
    （content.py::validate 保證有）一定接得住，所以一定有結果。打完最後一回合與壓倒性提前收場都走這裡
    （戰鬥系統設計 3.2）。沒人能打的收場不走這裡，見 end_without_fighters。時刻表決戰的 outcomes 只有一筆保底，
    真正的結果（含伏筆鎖定誰贏，第四節）由 engine 在收場後照 decide_result 判、交給時刻表。"""
    for outcome in definition.outcomes:
        lo, hi = outcome.trend_min, outcome.trend_max
        if (lo is None or instance.trend >= lo) and (hi is None or instance.trend <= hi):
            return outcome
    return definition.outcomes[-1]


def decide_result(
    instance: BattleInstance, definition: BattleDef, lock_side: str | None, defender: str,
) -> tuple[str, str]:
    """時刻表決戰的結果（戰鬥系統 4.1、4.2）：回傳（贏家, "大勝" | "險勝"），贏家是 factions 的 id（guan／huang）。
    - 戰場上的贏家：戰局以 factions[0]（官軍）為正向，高於 50 是它、低於 50 是另一方，剛好 50 算守方守住（沒有膠著）；
      偏離 50 達 BIG_WIN_MARGIN（65 以上、35 以下）是大勝，否則險勝。
    - 有人鎖定（lock_side 是交戰的一方）：鎖定方一定贏，戰場上也贏是大勝、打輸是險勝。
    只有收場這一刻看鎖定（呼叫端讀 WorldState.locks 傳進來）；起點、推力、選項都不看，鎖定才不會在戰場上露出來（4.3）。"""
    return result_at(instance.trend, definition, lock_side, defender)


BOT_BEST_MOVE_CHANCE = 0.7  # 機器人出自己份量最高的那一招的機率，其餘三成在三招裡隨便挑


def bot_choose_action(
    instance: BattleInstance, definition: BattleDef, name: str, rng: random.Random, tuning: BattleTuning | None = None,
) -> str | None:
    """機器人這回合要選什麼：七成出自己份量最高的那一招、三成在三招裡隨便挑
    （份量全一樣——例如沒有快照的舊資料全是 0——取損耗最低的固守，不是列在最前面的那一招）——這樣測試戰鬥用機器人
    湊場時行為會有變化，不會每次都選同一個，也不會像真的 AI 一樣聰明判斷局勢（那不是這裡的目標，
    設計討論原文：「不會全程 LLM 自由發展...大框架還是會進行下去」，機器人只是補位湊人數，
    不需要聰明）。正式營運時要用機器人增加活躍感，也是同一套函式。故意排除 free_text
    選項——機器人不會自己想出一段有意義的描述，用它只會得到一句空話，交給固定選項就好。
    （伺服器假人不走這裡：它們是一般參戰者，照 bot_policy 挑。）這一幕沒有三招可選就回 None。"""
    fixed = fixed_options(instance, definition, name)
    if not fixed:
        return None
    tuning = tuning or BattleTuning()
    p = instance.participants[name]
    if rng.random() < BOT_BEST_MOVE_CHANCE:
        return max(fixed, key=lambda o: (p.scores.get(o.move, 0.0), -tuning.damage[o.move])).tag
    return rng.choice(fixed).tag


def assess_action_success_rate(
    client: OllamaClient | None, act: BattleAct, faction_name: str, text: str,
) -> int:
    """只要成功率（舊的呼叫端）：見 assess_gamble。"""
    return assess_gamble(client, act, faction_name, text).rate


class GambleScore(BaseModel):
    success_rate: int = DEFAULT_FREE_TEXT_SUCCESS_RATE


SCORE_PREDICT = 24  # 只評成功率的那一次最多生幾個 token：{"success_rate": 35} 十個上下，多留一點不被截斷


def score_gamble(
    client: OllamaClient | None, act: BattleAct, faction_name: str, text: str, name: str = "",
    target: str = "", sex: str = "男",
) -> int:
    """決戰的放手一搏只評成功率（Joy 2026-10-13「這是我們效能問題，我們應該要做到能承受」：二十人同一回合各搏一次，
    每一個都要在回合結算前評到）：提示短、只要一個整數、num_predict 只給 SCORE_PREDICT，劇情等回合結算後一整回合批給
    write_tales 寫。跟 assess_gamble 同一套評法（只評行動本身合不合理，荒唐的給低分）；評不到回保底值。"""
    if client is None:
        return DEFAULT_FREE_TEXT_SUCCESS_RATE
    who, text = zh.prompt_safe(name) or "這位" + gender.hero(sex), zh.prompt_safe(text)  # 名號與那一句夾掉引號、換行（M-13）
    messages = [
        {"role": "system", "content": (
            "你是漢末兩軍交戰的戰場判定系統。評估玩家描述的行動在戰場上合理的成功機率，只回 0~100 的整數 success_rate："
            "只根據行動本身的合理性，荒唐、灌水、亂寫的行動給低分。"
        )},
        {"role": "user", "content": (
            f"戰場情境：【{act.title}】{act.text}\n玩家：{who}（所屬：{faction_name}）\n"
            + (f"玩家點名攻擊的對手：{target}\n" if target else "")
            + f"玩家的行動：「{text}」"
        )},
    ]
    try:
        result = client.chat_structured(
            messages, GambleScore, temperature=0.3, num_predict=SCORE_PREDICT, required_fields=["success_rate"],
        )
    except Exception:
        return DEFAULT_FREE_TEXT_SUCCESS_RATE
    return max(0, min(100, int(result.success_rate)))


class TaleItem(BaseModel):
    """寫劇情的單子上的一搏（GambleTale 拿掉場景記錄用的欄位，加上陣營的名字）。"""

    name: str
    faction_name: str
    text: str
    won: bool
    target: str = ""
    sex: str = "男"


class TaleLine(BaseModel):
    name: str = ""
    story: str = ""


class TaleBatch(BaseModel):
    lines: list[TaleLine] = Field(default_factory=list)


TALE_PREDICT_EACH = 90  # 一搏一句四十字上下，加上 JSON 的名號與括號
TALE_BATCH = 20  # 一次最多寫幾搏（一回合二十人都搏時一次寫完；再多下一次再寫）


def foe_names(items: list[TaleItem], sides: Sequence[str] = ()) -> dict[str, set[str]]:
    """每一位的「敵方陣營叫什麼」：這一批出現過的陣營名，加上呼叫端給的兩軍名字，去掉他自己那一邊。
    給 write_tales 守門用（失手那一句不准寫敵方受損）。"""
    every = {item.faction_name for item in items} | {s for s in sides if s}
    return {item.name: {n for n in every if n and n != item.faction_name} for item in items}


def write_tales(
    client: OllamaClient | None, act: BattleAct, items: list[TaleItem], setting: str = "漢末兩軍交戰的戰場",
    sides: Sequence[str] = (), fallen: Sequence[str] = (),
) -> dict[str, str]:
    """回合結算後，把這一回合等著補劇情的放手一搏一次批給模型寫（Joy 2026-10-13：評分與劇情拆開，二十人同時搏也撐得住）：
    成敗已經擲好了，一搏一句、照成敗寫，以名號開頭、第三人稱，不寫數字。回傳 名號 → 整理過的一句（clean_story）；
    寫壞的、名單外的、沒寫到的不在裡面（那一搏照舊播固定句）。模型失敗回空的。"""
    if client is None or not items:
        return {}
    women = {item.name for item in items if item.sex == "女"}
    safe = {item.name: zh.prompt_safe(item.name) or item.name for item in items}  # 名號、寫的字夾掉引號與換行（M-13）：一個人的名號
    listing = "\n".join(  # 不能改掉同一批別人那一行的意思
        f"{i}. {safe[item.name]}（{item.faction_name}{'，女子' if item.name in women else ''}）："
        f"「{zh.prompt_safe(item.text)}」——{'成功' if item.won else '失敗'}"
        + (f"，點名攻擊的對手是{zh.prompt_safe(item.target)}" if item.target else "")
        for i, item in enumerate(items, 1)
    )
    messages = [
        {"role": "system", "content": (
            f"你是{setting}的說書人。下面每一位玩家這一回合都放手一搏，成敗已經定了。替每一位各寫一句結果：40 字以內、繁體中文，"
            "以那位玩家的名號開頭、用第三人稱寫（不用「你」，名號後面不接冒號）；名號就是出手的那個人，不是在一旁看的人；"
            "用名號稱呼雙方，不要拿「散人」「官軍」「黃巾」這類身分當代名詞。要具體接住玩家寫的內容，照成敗寫：成功就寫成了，"
            "失敗就寫出糗、被識破、反被追打，可以荒謬、好笑。**失敗那一句的苦果一定要落在他自己或他那一方身上**："
            "不可以寫成對手受損、中計、倒地、吃虧，也不可以寫成對他有利——那會跟引擎算出來的結果矛盾"
            "（實例：一位黃巾玩家失手，卻被寫成「官軍吸入異味嘔吐倒地」，玩家看起來是贏了，數字卻是自己退了一截）。"
            "不要寫任何數字、不要寫戰局推進多少或扣多少氣血。"
            # 成功＝引擎把戰線推過去，不等於玩家喊的那件事真的做到了（claims_a_kill 上面那段）
            "**誰死誰活不是你決定的**：成功只代表他占了上風，不代表他喊的那件事全做到了。"
            "除了下面寫明「這一回合倒下的」那幾位，不准寫任何人被斬首、取下首級、斃命、陣亡、倒在血泊——"
            "哪怕玩家自己寫的那句話就是要取對方性命，也只能寫到逼退、重創、打得對方狼狽為止。"
            "標了女子的玩家用「她」稱呼。回傳 lines：每一位一筆，name 照抄名號，story 是那一句。"
        )},
        {"role": "user", "content": f"戰場情境：【{act.title}】{act.text}\n這一回合的放手一搏：\n{listing}"
                                    + (f"\n這一回合倒下的：{'、'.join(fallen)}" if fallen else "\n這一回合沒有人倒下。")},
    ]
    try:
        result = client.chat_structured(
            messages, TaleBatch, temperature=0.7, num_predict=64 + TALE_PREDICT_EACH * len(items),
            required_fields=["lines"], require_in_schema=True,  # TaleBatch.lines 有預設值，不寫進 required 的話模型可以回 {}
        )
    except Exception:
        return {}
    wanted = {item.name for item in items}
    named = {s: n for n, s in reversed(list(safe.items()))}  # 模型照抄的是夾過的名號：換回本名（同一個夾法撞名時算排在前面的）
    known = [n for item in items for n in (item.name, item.text, item.target)]  # 同一批的名號、寫的字（英文只能是這些裡面有的）
    lost = {item.name for item in items if not item.won}
    foes = foe_names(items, sides)
    out: dict[str, str] = {}
    for line in result.lines:
        name = str(line.name or "").strip()
        name = name if name in wanted else named.get(name, name)
        if name in wanted and name not in out:
            story = clean_story(_real_name(line.story, safe[name], name), name, known)
            # 失手的那一句提到敵方陣營的名字就不用（Joy 2026-10-19：黃巾玩家失手卻被寫成「官軍嘔吐倒地」，
            # 文字看起來贏了、數字是自己退了一截）。提示詞本來就禁止拿陣營名當代名詞，這裡只是確定性地攔下來；
            # 攔掉的照舊播固定句（「X這一搏失敗了，付出了慘痛代價：…」），寧可平淡也不要跟數字矛盾。
            if story and name in lost and any(foe in story for foe in foes.get(name, ())):
                story = ""
            # 寫到死人的那一句，要指名這一回合引擎真的放倒的人才算數（claims_a_kill 上面那段）；
            # 提示詞已經交代過，這裡確定性地攔下來，攔掉的照舊播固定句。
            if story and claims_a_kill(story) and not any(who in story for who in fallen):
                story = ""
            if story:
                out[name] = story
    return out


def tales_due(instance: BattleInstance) -> list[GambleTale]:
    """下一批要寫的：等著補劇情的最早那一回合的放手一搏（最多 TALE_BATCH 筆）。"""
    if not instance.tales:
        return []
    first = min(t.round for t in instance.tales)
    return [t for t in instance.tales if t.round == first][:TALE_BATCH]


def apply_tales(instance: BattleInstance, done: list[tuple[int, str]], stories: dict[str, str]) -> int:
    """寫好的劇情補回去：場景記錄（narrative_log）裡那一搏的固定句換成「劇情（數字）」，這個人那一回合的放手一搏（GambleMoment，
    戰報、行狀、最有戲的一幕都讀它）記下劇情。done 是這一批的（回合, 名號）：寫到沒寫到都從等著補的單子拿掉（寫不出來就照固定句，
    不重寫）。回傳補了幾句。"""
    keys = set(done)
    patched = 0
    for tale in [t for t in instance.tales if (t.round, t.name) in keys]:
        story = stories.get(tale.name)
        if not story:
            continue
        line = f"{story}（{tale.numbers}）"
        # 一回合一段：往後的回合（同一個人、同樣的數字可能寫出一模一樣的固定句）不碰，從那一回合那一段往前找
        start = min(len(instance.narrative_log) - 1, len(instance.narrative_log) - 1 - (instance.round_number - tale.round))
        for i in range(start, -1, -1):
            if tale.fixed in instance.narrative_log[i]:
                instance.narrative_log[i] = instance.narrative_log[i].replace(tale.fixed, line, 1)
                patched += 1
                break
        p = instance.participants.get(tale.name)
        moments = (p.gambles if p is not None else []) + ([instance.highlight] if instance.highlight is not None else [])
        for moment in moments:
            if moment.name == tale.name and moment.round == tale.round and not moment.story:
                moment.story = story
    instance.tales = [t for t in instance.tales if (t.round, t.name) not in keys]
    return patched


def without_mix_line(instance: BattleInstance, msgs: list[str]) -> list[str]:
    """這回合的系統訊息拿掉最前面那一行出招比例（resolve_round 在有人出固定招的回合才加那一行，而且一定放第一行；
    判斷看 instance.last_mix：任何一邊有比例就代表有那一行）。出招比例只留在回合紀錄（戰報）裡，
    場景上的記錄（narrative_log）不放它——場景已經有「對面上一回合」那一段，每回合再留一行 53 字會讓場景每回合多約 88px。"""
    return list(msgs[1:] if any(instance.last_mix.values()) else msgs)
