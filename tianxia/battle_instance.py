"""全服共用的即時多人戰鬥（設計討論：集結選陣營→逐幕逐回合鎖步→決戰幕判定勝負）。

跟整個專案一貫的原則一樣：戰局推進/氣血損耗是查表決定的確定性結果，不信任 LLM 自己算
數字；LLM 只負責在固定骨架（BattleDef.acts）裡，依這一回合大家選擇的傾向生成一段敘事
潤色，骨架本身一定會照查表結果往下走，不會被 LLM 帶偏。

這裡只有純粹的資料模型跟引擎函式，不碰 UI、不碰共用儲存的存讀——那是下一步的事（先把
骨架用假內容測通，再決定要怎麼接進 WorldStateStore／Gradio UI，見設計討論）。回合「鎖步」
的意思是：每個參戰者各自送出一個行動，全員都送出（或逾時被系統代選）才會真正結算那一
回合，由誰送出最後一個行動就由誰的這次呼叫觸發結算，不需要背景常駐程式。
"""
from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, Field

from .models import BattleAct, BattleDef, BattleOption, BattleOutcome
from .ollama_client import OllamaClient

Phase = Literal["muster", "active", "ended"]


class BattleParticipant(BaseModel):
    name: str
    faction: str
    neili: float  # 這場戰鬥專屬的氣血池，從角色當下的氣血上限抓一份快照，跟角色本身的
    # Member.neili（存檔裡的，練功/療傷用的那個）完全分開——戰鬥的傷害不會回頭影響角色
    # 平常的氣血，這是刻意的設計邊界（見設計討論沒有明講時的預設假設，之後如果想要「這場
    # 戰鬥真的會傷到我的角色」，再回頭改這裡）。
    neili_cap: float
    eliminated: bool = False
    is_bot: bool = False


class BattleRound(BaseModel):
    pending_actions: dict[str, str] = Field(default_factory=dict)  # 玩家名號 -> tag
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


def start_muster(definition: BattleDef, now: float) -> BattleInstance:
    return BattleInstance(
        battle_id=definition.id, trend=definition.trend_start, muster_deadline_real=now + definition.muster_seconds,
    )


def join_faction(
    instance: BattleInstance, name: str, faction: str, neili_cap: float, is_bot: bool = False,
) -> None:
    """集結期選陣營；已經選過的人再選一次視為改選（還沒進入 active 都還能換）。"""
    if instance.phase != "muster":
        return
    instance.participants[name] = BattleParticipant(
        name=name, faction=faction, neili=neili_cap, neili_cap=neili_cap, is_bot=is_bot,
    )


def close_muster(instance: BattleInstance, definition: BattleDef, rng: random.Random) -> None:
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
    instance.round = BattleRound(opened_real=0.0)
    instance.narrative_log.append(f"【{definition.name}】集結完畢，戰鬥開始！")


def auto_assign_latecomer(
    instance: BattleInstance, definition: BattleDef, name: str, neili_cap: float, rng: random.Random,
    is_bot: bool = False,
) -> None:
    """集結期結束後才出現的人（包含機器人）：直接塞進人數較少的一方，維持陣營平衡。"""
    faction_ids = [f.id for f in definition.factions]
    counts = {fid: sum(1 for p in instance.participants.values() if p.faction == fid) for fid in faction_ids}
    faction = min(counts, key=lambda fid: (counts[fid], rng.random()))
    instance.participants[name] = BattleParticipant(
        name=name, faction=faction, neili=neili_cap, neili_cap=neili_cap, is_bot=is_bot,
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


def submit_action(instance: BattleInstance, name: str, tag: str) -> None:
    """記錄一個人這回合選的行動；已經陣亡或不在這場戰鬥裡的人送出無效。"""
    p = instance.participants.get(name)
    if p is None or p.eliminated or instance.phase != "active":
        return
    instance.round.pending_actions[name] = tag


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


def resolve_round(
    instance: BattleInstance, definition: BattleDef, rng: random.Random, power_of=lambda name: None,
) -> list[str]:
    """結算一回合：依每個人選的 tag 查表推動戰局 trend、扣氣血，氣血歸零的人出局；
    檢查目前幕的進幕條件，滿足就換下一幕；最後把回合狀態重置給下一回合用。power_of(name)
    是個函式，回傳這個人當下的武學威力（給 mitigated_by_power 用），預設一律回傳 None
    （不抵銷），呼叫端（engine.py）接進真正的角色資料時再換成真的查詢函式。回傳這回合發生
    的事件訊息（系統判定的部分，不含 LLM 潤色——那是呼叫端另外接的，見 narrate_round）。"""
    msgs: list[str] = []
    for name, tag in list(instance.round.pending_actions.items()):
        p = instance.participants.get(name)
        if p is None or p.eliminated:
            continue
        effect = definition.action_tags.get(tag)
        if effect is None:
            continue
        instance.trend = max(0, min(100, instance.trend + effect.trend_delta))
        damage = effect.neili_damage
        if effect.mitigated_by_power:
            damage *= 1 - _power_mitigation(power_of(name))
        p.neili = max(0.0, p.neili - damage)
        if p.neili <= 0 and not p.eliminated:
            p.eliminated = True
            msgs.append(f"{name}氣血耗盡，倒在戰場上，退出了這場戰鬥（轉為觀戰）。")
    act = current_act(instance, definition)
    advanced = False
    if act.advance_when is not None:
        lo, hi = act.advance_when.trend_min, act.advance_when.trend_max
        crossed = (lo is None or instance.trend >= lo) and (hi is None or instance.trend <= hi)
        if crossed and instance.act_index < len(definition.acts) - 1:
            instance.act_index += 1
            advanced = True
            msgs.append(f"【{definition.acts[instance.act_index].title}】{definition.acts[instance.act_index].text}")
    # 剛換到新的一幕時，這一幕還沒有人真的行動過，不該在同一回合裡立刻判終局（至少要讓
    # 大家在新的一幕裡選過一次行動，才輪到檢查是不是已經分出勝負）。
    outcome = None if advanced else _check_outcome(instance, definition)
    if outcome is not None:
        instance.phase = "ended"
        instance.outcome_title, instance.outcome_text = outcome.title, outcome.text
        msgs.append(f"══ {outcome.title} ══")
        msgs.append(outcome.text)
    instance.round = BattleRound(opened_real=0.0)
    instance.narrative_log.extend(msgs)
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
            [{"role": "system", "content": "你是文字武俠遊戲的戰場敘事生成器，只潤色既有判定，不自創結果。"},
             {"role": "user", "content": prompt}],
            num_predict=200,
        )
    except Exception:
        return "\n".join(msgs)
    return text.strip() or "\n".join(msgs)
