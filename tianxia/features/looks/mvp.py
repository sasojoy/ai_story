"""決戰的回合 MVP（Joy 2026-11-03「我們的目的是展示，玩家也會想要炫……在放手一搏成功的人裡面且他有絕招動畫的挑一個當這回合的MVP，
播放他的絕招」）。純規則，不讀時鐘、不碰回合結算的亂數、不動任何數字。

- 放手一搏送出那一刻（Game._submit_battle_action），身上穿著絕招、而且那一招有導演稿（上架了的一句話自創，通用、獨門都算），
  就把那一招、穿的形象、手上的兵器記在這一回合（BattleRound.ults；actions.battle_ult 拍的）。
- 回合結算完（Game._advance_battle_round 經 actions.crowned），這一回合放手一搏成了（gambles_won 多了）、又記了絕招的人裡挑一位：
  評的成功率越低越先（越險越值得演，同 battle_instance.more_dramatic）；一樣險照「決戰|這一場|第幾回合|名號」的雜湊排，
  同一回合每個看的人看到同一位。記進 BattleInstance.mvps 與那一回合的 BattleRoundRecord.mvp，回合紀錄多一行標出來。
- 沒人符合就不挑、不多那一行。
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable

from tianxia.battle_instance import BattleInstance, BattleMvp  # 過渡：待搬（決戰的共用狀態；總表第 54 批拆兩半）

LINE = "★ 本回合 MVP：{name}，絕招「{move}」"  # 待 joy 潤
LINE_BARE = "★ 本回合 MVP：{name}"  # 導演稿沒有招名時（舊稿）


def _order(instance: BattleInstance, round_no: int, name: str) -> str:
    return hashlib.sha256(f"決戰|{instance.battle_id}|{instance.record_id}|{round_no}|{name}".encode()).hexdigest()


def crown(instance: BattleInstance, ults: dict[str, dict[str, str]], rates: dict[str, int], won: dict[str, int]) -> BattleMvp | None:
    """剛結算完的那一回合（instance.round_number）挑 MVP；ults、rates、won 是結算前拍的（這一回合記的絕招、評的成功率、
    每個人到上一回合為止成了幾次）。挑到了記進 instance.mvps 與最後一筆回合紀錄，回傳那一位；沒人符合回 None。"""
    round_no = instance.round_number
    if not ults or not round_no:
        return None
    hits = [
        name for name, ult in ults.items()
        if ult.get("move") and (p := instance.participants.get(name)) is not None and p.gambles_won > won.get(name, 0)
    ]
    if not hits:
        return None
    name = min(hits, key=lambda n: (rates.get(n, 100), _order(instance, round_no, n)))
    ult, p = ults[name], instance.participants[name]
    record = instance.rounds[-1] if instance.rounds and instance.rounds[-1].round_number == round_no else None
    mvp = BattleMvp(
        round=round_no, name=name, faction=p.faction, move=ult["move"], move_name=ult.get("name", ""),
        look=ult.get("look", ""), weapon=ult.get("weapon", ""), text=record.custom_texts.get(name, "") if record is not None else "",
    )
    instance.mvps.append(mvp)
    if record is not None:
        record.mvp = name
    return mvp


def line(mvp: BattleMvp) -> str:
    return LINE.format(name=mvp.name, move=mvp.move_name) if mvp.move_name else LINE_BARE.format(name=mvp.name)


def crowned(instance: BattleInstance, resolve: Callable[[], list[str]]) -> list[str]:
    """包著 battle_instance.resolve_round：結算前拍下這一回合記的絕招與成了幾次，結算完挑 MVP，挑到了回合紀錄最後多一行。"""
    ults = {n: dict(u) for n, u in instance.round.ults.items()}
    rates = dict(instance.round.success_rates)
    won = {n: p.gambles_won for n, p in instance.participants.items()}
    msgs = resolve()
    mvp = crown(instance, ults, rates, won)
    if mvp is not None:
        msgs = [*msgs, line(mvp)]
        record = instance.rounds[-1] if instance.rounds else None
        if record is not None and record.round_number == mvp.round:
            record.messages.append(line(mvp))
    return msgs


def latest(instance: BattleInstance) -> dict | None:
    """決戰畫面要演的那一位：最近一回合挑出來的 MVP，而且就是剛結算完的那一回合（再下一回合沒人符合就不再演舊的）。"""
    if not instance.mvps or instance.phase == "muster":
        return None
    mvp = instance.mvps[-1]
    if mvp.round != instance.round_number:
        return None
    return {
        "id": f"{instance.record_id or 0}-{mvp.round}", "round": mvp.round, "name": mvp.name, "faction": mvp.faction,
        "move": mvp.move, "move_name": mvp.move_name, "look": mvp.look, "weapon": mvp.weapon, "text": mvp.text,
    }

