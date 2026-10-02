"""全服共用的即時多人戰鬥（設計討論：集結選陣營→逐幕逐回合鎖步→決戰幕判定勝負）。

固定選項（穩守/猛攻）的推進/氣血損耗是查表決定的確定性結果，不信任 LLM 自己算數字；
自訂行動（放手一搏，見 BattleOption.free_text／FreeTextGamble）則是 LLM 評估一個成功率
（這件事 LLM 做得到、也實測過排序穩定），系統拿這個機率真的擲骰、用寫死的公式換算
成戰局推動/氣血損耗——玩家的奇葩操作因此真的會影響戰局（賭贏大賺、賭輸慘賠），但
「最後是不是成功」跟「成功該加多少」都是系統的亂數/公式決定，LLM 從頭到尾不會直接
吐出任何被拿去套用的數字，只吐一個被擲骰消費掉的機率。LLM 另外也負責在固定骨架
（BattleDef.acts）裡，依這一回合發生的事生成一段敘事潤色，骨架本身一定會照查表/擲骰
結果往下走，不會被 LLM 帶偏。

這裡是純粹的資料模型跟引擎函式，不碰共用儲存的存讀鎖（那是 world_state.py::
get_battle/mutate_battle/start_battle 的事）、不碰 Gradio UI（那是 engine.py/app.py 的事）。
回合「鎖步」的意思是：每個參戰者各自送出一個行動，全員都送出（或逾時被系統代選）才會
真正結算那一回合，由誰送出最後一個行動就由誰的這次呼叫觸發結算，不需要背景常駐程式。
"""
from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, Field

from . import zh
from .models import BattleAct, BattleActionEffect, BattleDef, BattleOption, BattleOutcome
from .ollama_client import OllamaClient

Phase = Literal["muster", "active", "ended"]

DEFAULT_FREE_TEXT_SUCCESS_RATE = 40  # LLM 評估失敗/無 client 時的保底值——明顯偏低（放手一搏預設不利），
# 不是 50/50，呼應「不會全程 LLM 自由發展」的框架精神：評不出來就當作風險自負，不讓機制因為評估失敗而意外變得穩賺不賠。


class BattleParticipant(BaseModel):
    name: str
    faction: str
    neili: float  # 這場戰鬥專屬的氣血池，從角色當下的氣血上限抓一份快照，跟角色本身的
    # Member.neili（存檔裡的，練功/療傷用的那個）完全分開——戰鬥的傷害不會回頭影響角色
    # 平常的氣血，這是刻意的設計邊界（見設計討論沒有明講時的預設假設，之後如果想要「這場
    # 戰鬥真的會傷到我的角色」，再回頭改這裡）。
    neili_cap: float
    power: float = 0.0  # 加入時快照的武學威力（給 mitigated_by_power 用，見 resolve_round）——
    # 戰局結算只看共用戰鬥狀態本身，不會、也不能回頭去讀別的玩家自己存檔裡的角色資料，
    # 所以威力要在加入當下、由那個玩家自己的 Game 執行個體算好存進來。
    eliminated: bool = False
    is_bot: bool = False


class BattleRound(BaseModel):
    pending_actions: dict[str, str] = Field(default_factory=dict)  # 玩家名號 -> tag
    custom_texts: dict[str, str] = Field(default_factory=dict)  # 玩家名號 -> 自訂行動文字（free_text 選項才有）
    success_rates: dict[str, int] = Field(default_factory=dict)  # 玩家名號 -> LLM 評估的成功率（0~100，
    # free_text 選項才有；在送出的當下就評好存起來，不是結算時才問——resolve_round 不能
    # 呼叫 LLM，見模組說明。這個欄位有值就代表這個人這回合是賭局型行動，沒有值就是走
    # action_tags 查表的一般行動，resolve_round 靠這個區分兩條路徑）。
    opened_real: float = 0.0  # 這回合開放選擇的時間點，逾時代選判斷用


class BattleInstance(BaseModel):
    battle_id: str
    phase: Phase = "muster"
    muster_deadline_real: float = 0.0
    participants: dict[str, BattleParticipant] = Field(default_factory=dict)
    trend: int = 50
    act_index: int = 0
    round: BattleRound = Field(default_factory=BattleRound)
    narrative_log: list[str] = Field(default_factory=list)
    outcome_title: str | None = None
    outcome_text: str | None = None
    outcome_world_flags: list[str] = Field(default_factory=list)  # 結果要套用到共用賽季的世界旗標（複製自
    # BattleOutcome.world_flags_add，不是參照——戰鬥結算只碰共用戰鬥狀態本身，套用到賽季是
    # 呼叫端 engine.py 的事，見 Game._apply_battle_outcome；這裡存一份複本給它讀，不用
    # 重新比對一次是哪個 BattleOutcome）。
    outcome_trend_delta: dict[str, int] = Field(default_factory=dict)  # 同上，複製自 BattleOutcome.trend_delta


def start_muster(definition: BattleDef, now: float) -> BattleInstance:
    return BattleInstance(
        battle_id=definition.id, trend=definition.trend_start, muster_deadline_real=now + definition.muster_seconds,
    )


def join_faction(
    instance: BattleInstance, name: str, faction: str, neili_cap: float, power: float = 0.0, is_bot: bool = False,
) -> None:
    """集結期選陣營；已經選過的人再選一次視為改選（還沒進入 active 都還能換）。"""
    if instance.phase != "muster":
        return
    instance.participants[name] = BattleParticipant(
        name=name, faction=faction, neili=neili_cap, neili_cap=neili_cap, power=power, is_bot=is_bot,
    )


def close_muster(instance: BattleInstance, definition: BattleDef, rng: random.Random, now: float = 0.0) -> None:
    """集結期結束：還沒選陣營的人（名字已經在 participants 裡但沒指定，或完全沒動作、
    呼叫端另外傳進來的在線名單）由這個函式統一處理——這裡只負責「把已經報名但沒選邊的人
    隨機分配」，呼叫端自己決定要不要把從沒選過的在線玩家也塞進 participants。"""
    if instance.phase != "muster":
        return
    faction_ids = [f.id for f in definition.factions]
    for p in instance.participants.values():
        if p.faction not in faction_ids:
            p.faction = rng.choice(faction_ids)
    instance.phase = "active"
    instance.round = BattleRound(opened_real=now)
    instance.narrative_log.append(f"【{definition.name}】集結完畢，戰鬥開始！")


def auto_assign_latecomer(
    instance: BattleInstance, definition: BattleDef, name: str, neili_cap: float, rng: random.Random,
    power: float = 0.0, is_bot: bool = False, faction: str | None = None,
) -> None:
    """集結期結束後才出現的人（包含機器人）：有指定陣營（劇本分陣營時的玩家）就站自己那邊，
    否則塞進人數較少的一方，維持陣營平衡。"""
    faction_ids = [f.id for f in definition.factions]
    if faction not in faction_ids:
        counts = {fid: sum(1 for p in instance.participants.values() if p.faction == fid) for fid in faction_ids}
        faction = min(counts, key=lambda fid: (counts[fid], rng.random()))
    instance.participants[name] = BattleParticipant(
        name=name, faction=faction, neili=neili_cap, neili_cap=neili_cap, power=power, is_bot=is_bot,
    )


def _active_participants(instance: BattleInstance) -> list[BattleParticipant]:
    return [p for p in instance.participants.values() if not p.eliminated]


def current_act(instance: BattleInstance, definition: BattleDef) -> BattleAct:
    return definition.acts[instance.act_index]


def options_for(instance: BattleInstance, definition: BattleDef, name: str) -> list[BattleOption]:
    """這個人這回合能選的選項：框架給的選項，依陣營篩選（faction=None 的選項雙方都能選）。"""
    p = instance.participants.get(name)
    if p is None:
        return []
    act = current_act(instance, definition)
    return [o for o in act.options if o.faction in (None, p.faction)]


def submit_action(
    instance: BattleInstance, name: str, tag: str, text: str | None = None, success_rate: int | None = None,
) -> None:
    """記錄一個人這回合選的行動；已經陣亡或不在這場戰鬥裡的人送出無效。text/success_rate
    是 free_text 選項才有（見 BattleOption.free_text）——success_rate 是呼叫端（engine.py
    ::submit_battle_custom_action）在送出的當下先問過 LLM 評好的成功率，resolve_round
    靠這個欄位有沒有值決定這個人這回合是賭局型行動還是一般查表行動，自己不會、也不能
    呼叫 LLM（見模組說明）。"""
    p = instance.participants.get(name)
    if p is None or p.eliminated or instance.phase != "active":
        return
    instance.round.pending_actions[name] = tag
    if text:
        instance.round.custom_texts[name] = text
    if success_rate is not None:
        instance.round.success_rates[name] = max(0, min(100, success_rate))


def round_is_complete(instance: BattleInstance) -> bool:
    """所有還在場上的人都送出行動了（陣亡的人不用等）。"""
    active = _active_participants(instance)
    return bool(active) and all(p.name in instance.round.pending_actions for p in active)


def fill_timed_out_actions(instance: BattleInstance, definition: BattleDef, default_tag: str) -> None:
    """逾時：還沒送出行動的在場者，系統代選一個保守行動（呼叫端決定要用哪個 tag 當保守
    選項，通常是 action_tags 裡 trend_delta/neili_damage 都最溫和的那一個）。"""
    for p in _active_participants(instance):
        instance.round.pending_actions.setdefault(p.name, default_tag)


def _power_mitigation(power: float | None) -> float:
    """自身武學威力對氣血損耗的抵銷比例：威力愈高抵銷愈多，但抵銷不了全部（再強也會受傷），
    用一個簡單、好懂的公式，不是精算平衡（之後實測覺得不合理再調）。"""
    if not power:
        return 0.0
    return min(0.6, power / 200)


def resolve_round(instance: BattleInstance, definition: BattleDef, rng: random.Random, now: float = 0.0) -> list[str]:
    """結算一回合：依每個人選的 tag 查表推動戰局 trend、扣氣血，氣血歸零的人出局；
    檢查目前幕的進幕條件，滿足就換下一幕；最後把回合狀態重置給下一回合用（opened_real
    設成 now，給下一回合的逾時判斷當起點）。威力抵銷（mitigated_by_power）直接讀
    BattleParticipant.power——那是加入戰鬥當下由各自的 Game 執行個體算好快照進來的
    （見 BattleParticipant 的欄位註解），這裡不需要、也不能臨時去查任何人的角色資料。
    回傳這回合發生的事件訊息（系統判定的部分，不含 LLM 潤色、也不會自己寫進
    narrative_log——那兩件事都是呼叫端的事，見 narrate_round：呼叫端通常是先結算拿到
    msgs，請 LLM 潤色成一段敘事，再把潤色後的文字（或潤色失敗時的 msgs 本身）加進
    narrative_log，這裡不越俎代庖）。"""
    msgs: list[str] = []
    positive_faction = definition.factions[0].id
    for name, tag in list(instance.round.pending_actions.items()):
        p = instance.participants.get(name)
        if p is None or p.eliminated:
            continue
        success_rate = instance.round.success_rates.get(name)
        custom_text = instance.round.custom_texts.get(name)
        if success_rate is not None and definition.free_text_gamble is not None:
            gamble = definition.free_text_gamble
            risk = 100 - success_rate
            succeeded = rng.random() * 100 < success_rate
            sign = 1 if p.faction == positive_faction else -1
            if custom_text:
                msgs.append(f"{name}放手一搏：「{custom_text}」（評估成功率 {success_rate}%）")
            if succeeded:
                delta = gamble.success_trend_base + round(risk * gamble.success_trend_per_risk)
                damage = gamble.success_neili_damage
                msgs.append(f"{name}這一搏成功了！")
            else:
                delta = -round(risk * gamble.failure_trend_per_risk)
                damage = gamble.failure_neili_base + risk * gamble.failure_neili_per_risk
                msgs.append(f"{name}這一搏失敗了，付出了慘痛代價。")
            instance.trend = max(0, min(100, instance.trend + sign * delta))
        else:
            effect = definition.action_tags.get(tag)
            if effect is None:
                continue
            if custom_text:
                msgs.append(f"{name}放手一搏：「{custom_text}」")
            instance.trend = max(0, min(100, instance.trend + effect.trend_delta))
            damage = effect.neili_damage
            if effect.mitigated_by_power:
                damage *= 1 - _power_mitigation(p.power)
        p.neili = max(0.0, p.neili - damage)
        if p.neili <= 0 and not p.eliminated:
            p.eliminated = True
            msgs.append(f"{name}氣血耗盡，倒在戰場上，退出了這場戰鬥（轉為觀戰）。")
    act = current_act(instance, definition)
    advanced = False
    if act.advance_when is not None:
        aw = act.advance_when
        if aw.trend_outside is not None:
            crossed = abs(instance.trend - definition.trend_start) >= aw.trend_outside
        else:
            crossed = (aw.trend_min is None or instance.trend >= aw.trend_min) and (
                aw.trend_max is None or instance.trend <= aw.trend_max
            )
        if crossed and instance.act_index < len(definition.acts) - 1:
            instance.act_index += 1
            advanced = True
            msgs.append(f"【{definition.acts[instance.act_index].title}】{definition.acts[instance.act_index].text}")
    # 剛換到新的一幕時，這一幕還沒有人真的行動過，不該在同一回合裡立刻判終局（至少要讓
    # 大家在新的一幕裡選過一次行動，才輪到檢查是不是已經分出勝負）。
    outcome = None if advanced else _check_outcome(instance, definition)
    if outcome is not None:
        msgs += _record_outcome(instance, outcome)
    instance.round = BattleRound(opened_real=now)
    return msgs


def _record_outcome(instance: BattleInstance, outcome: BattleOutcome) -> list[str]:
    """把終局記到戰鬥上（套用到共用賽季是呼叫端 engine.py 的事，見 BattleInstance 的欄位註解），
    回傳要給大家看的兩行。"""
    instance.phase = "ended"
    instance.outcome_title, instance.outcome_text = outcome.title, outcome.text
    instance.outcome_world_flags = list(outcome.world_flags_add)
    instance.outcome_trend_delta = dict(outcome.trend_delta)
    return [f"══ {outcome.title} ══", outcome.text]


def end_without_fighters(instance: BattleInstance, definition: BattleDef, now: float) -> list[str]:
    """場上已經沒有任何還能打的人（沒人參戰、或全都倒下了），而且這一回合已經逾時：
    沒有人能送出行動，round_is_complete 永遠不會成立，這場戰鬥就會永遠卡著——這時直接用
    內容最後那個無條件的保底結果（definition.outcomes[-1]，content.py::validate 保證它
    沒有門檻）收場，記錄方式跟 resolve_round 分出勝負時一樣。這裡沒有 LLM 潤色，收場的
    幾句話直接寫進 narrative_log。還有人在場、還在集結、或回合還沒逾時，什麼都不做、回傳空清單。"""
    if instance.phase != "active" or _active_participants(instance):
        return []
    if now - instance.round.opened_real < definition.round_seconds:
        return []
    msgs = ["戰場上已經沒有人還能出手，這場戰鬥就此收場。"] + _record_outcome(instance, definition.outcomes[-1])
    instance.narrative_log.append("\n".join(msgs))
    instance.round = BattleRound(opened_real=now)
    return msgs


def _check_outcome(instance: BattleInstance, definition: BattleDef) -> BattleOutcome | None:
    """只在最後一幕才判斷最終勝負——中間幕的進幕條件只是換場景，不是分勝負（設計上，決戰
    幕本身的進幕條件通常就是「沒有下一幕了」，呼叫端在內容裡把真正的終局門檻放在最後一幕）。"""
    if instance.act_index != len(definition.acts) - 1:
        return None
    for outcome in definition.outcomes:
        lo, hi = outcome.trend_min, outcome.trend_max
        if (lo is None or instance.trend >= lo) and (hi is None or instance.trend <= hi):
            return outcome
    return None


def bot_choose_action(instance: BattleInstance, definition: BattleDef, name: str, rng: random.Random) -> str | None:
    """機器人這回合要選什麼：依選項的風險（action_tags 查到的氣血損耗）反向加權隨機選，
    損耗愈低愈容易被選到，但不是完全不會選有風險的——這樣測試戰鬥用機器人湊場時行為
    會有變化，不會每次都選同一個，也不會像真的 AI 一樣聰明判斷局勢（那不是這裡的目標，
    設計討論原文：「不會全程 LLM 自由發展...大框架還是會進行下去」，機器人只是補位湊人數，
    不需要聰明）。正式營運時要用機器人增加活躍感，也是同一套函式。故意排除 free_text
    選項——機器人不會自己想出一段有意義的描述，用它只會得到一句空話，交給固定選項就好。"""
    options = [o for o in options_for(instance, definition, name) if not o.free_text]
    if not options:
        return None
    weights = [1.0 / (definition.action_tags.get(o.tag, BattleActionEffect()).neili_damage + 1) for o in options]
    return rng.choices(options, weights=weights, k=1)[0].tag


class SuccessRateJudgment(BaseModel):
    success_rate: int = DEFAULT_FREE_TEXT_SUCCESS_RATE
    reasoning: str = ""


def assess_action_success_rate(
    client: OllamaClient | None, act: BattleAct, faction_name: str, text: str,
) -> int:
    """請 LLM 評估這段自訂行動聽起來有多可能成功（0~100）——只評機率，不評「成不成功」
    本身（那是 resolve_round 擲骰決定的），也不會被拿去當作任何數值直接套用，只是擲骰
    用的機率輸入。連不上/生成失敗/格式不對都回傳保底值（見 DEFAULT_FREE_TEXT_SUCCESS_RATE），
    不會讓整個行動失敗——這類評估本來就是錦上添花，寧可給一個偏低的保守值，也不要卡住
    玩家的回合。"""
    if client is None:
        return DEFAULT_FREE_TEXT_SUCCESS_RATE
    messages = [
        {"role": "system", "content": (
            "你是漢末兩軍交戰的戰場判定系統，負責評估玩家描述的行動合理的成功機率，不是故事"
            "寫手、也不負責決定最終是否成功。只能根據行動本身在戰場上的合理性判斷，"
            "請給出 0~100 的整數 success_rate（成功機率）與一句話 reasoning。"
        )},
        {"role": "user", "content": (
            f"戰場情境：【{act.title}】{act.text}\n玩家所屬：{faction_name}\n"
            f"玩家的行動：「{text}」\n請給出 success_rate、reasoning。"
        )},
    ]
    try:
        result = client.chat_structured(messages, SuccessRateJudgment, temperature=0.7, required_fields=["success_rate"])
    except Exception:
        return DEFAULT_FREE_TEXT_SUCCESS_RATE
    return max(0, min(100, result.success_rate))


# 試玩時潤色寫出「劍尖相碰」這種武俠單挑的畫面；全服決戰是兩軍對陣，要寫成漢末的戰陣。
BATTLE_NARRATOR_PROMPT = (
    "你是漢末三國文字遊戲的戰場敘事生成器，只潤色既有判定，不自創結果。這是兩軍對陣的戰場："
    "旌旗、陣列、鼓聲號角、弓弩齊發、騎兵衝陣、步卒廝殺；不要寫成武俠的單打獨鬥或刀劍特寫，"
    "也不要提到判定裡沒有的人物或事件。用繁體中文。"
)


def narrate_round(client: OllamaClient | None, definition: BattleDef, instance: BattleInstance, msgs: list[str]) -> str:
    """這回合的 LLM 潤色：給它目前幕的框架文字跟系統已經判定好的事件訊息，請它寫一段
    貼合戰場氣氛的敘事——骨架跟結果都已經是定案的了，LLM 只是把它寫得生動一點，連不上
    或生成失敗就直接用系統訊息本身，不會讓戰鬥卡住。"""
    if client is None:
        return "\n".join(msgs)
    act = current_act(instance, definition)
    prompt = (
        f"戰場目前的局面：【{act.title}】{act.text}\n"
        f"這一回合系統判定發生的事：{'；'.join(msgs) if msgs else '雙方交戰，暫無重大變化。'}\n"
        "請用兩三句話，貼合戰場氣氛，把這些已經判定好的事寫成生動的敘事，不要改變、也不要"
        "新增任何判定結果，只是把它寫得有畫面感。"
    )
    try:
        text = client.chat_text(
            [{"role": "system", "content": BATTLE_NARRATOR_PROMPT}, {"role": "user", "content": prompt}],
            num_predict=200,
        )
    except Exception:
        return "\n".join(msgs)
    return zh.to_traditional(text.strip()) or "\n".join(msgs)
