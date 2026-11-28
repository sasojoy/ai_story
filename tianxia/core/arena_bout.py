"""擂台分身對打的一回合與勝負（從單挑包的 arena_rules、arena_actions 搬進核心：門派論劍〔features/lunjian〕兩邊都是分身，
要用同一套打法；包不能 import 包。Joy 2026-11-28 在門派論劍設計稿第 5 題「搬一小塊到核心」之後回「機制這樣可以 開始做」）。

函式照抄、名字不變、一個數字都沒動：單挑包的 arena_rules re-export exchange_full、Exchange、verdict、_weight、_clamp、_pool，
arena_actions re-export faced，擂台的行為一個字不變。只算數字與句子、改傳進來的 ArenaFight，不碰存檔、不碰 Game、不讀時鐘。
"""
from __future__ import annotations

import random
from typing import NamedTuple

from .. import tactics, team
from ..models import Content, DuelTuning
from ..state import ArenaFight, ArenaSide
from . import battle_base as battle_instance
from . import duel_base


def faced(content, me: ArenaSide, foe: ArenaSide) -> None:
    """五項屬性的季：兩邊的威力與份量照對手真正的五項重算（我的武力對他的統御；企劃者 2026-11-04）。舊的季、舊的分身不動。"""
    if me.card is None or foe.card is None:
        return
    mine, theirs = me.card, foe.card
    me.power, me.scores, me.bare = team.pvp_faced(content, me.power, me.scores, mine, theirs, me.bare)
    foe.power, foe.scores, foe.bare = team.pvp_faced(content, foe.power, foe.scores, theirs, mine, foe.bare)
    me.dodge, foe.dodge = team.pvp_dodge(content, mine, theirs), team.pvp_dodge(content, theirs, mine)
    me.role, me.scores = team.pvp_unrole(content, me.role, me.scores)
    foe.role, foe.scores = team.pvp_unrole(content, foe.role, foe.scores)



def _weight(side: ArenaSide, move: str, content: Content) -> float:
    return side.scores.get(move) or battle_instance.strength(content.config.battle, side.power) * content.config.duel.foe_fit


def _clamp(edge: float) -> float:
    return max(0.0, min(100.0, edge))


def _pool(side: ArenaSide, lost: int) -> int:
    """池子扣 lost（負的是回，回到上限為止）：回實際扣了多少（取整數：池子是小數，見底那一下扣的是剩的那一截，
    回合那一句照 :+d 寫，小數會丟 ValueError——2026-10-16 量表的假人擂台每一回合見底都炸）。"""
    lost = min(side.hp, lost) if lost > 0 else max(-(side.hp_cap - side.hp), lost)
    side.hp -= lost
    return round(lost)


class Exchange(NamedTuple):
    delta: int
    mine_hp: int
    foe_hp: int
    beat: int
    mine: str | None
    his: str | None
    lines: list[str]
    skills: tuple[list[str], list[str]] = ((), ())  # 這一回合兩邊發動的戰法是哪一門武學帶的（擂台動畫：綁了招式的那一門發動了才疊光效）


def exchange_full(fight: ArenaFight, move: str, content: Content, rng: random.Random, trng: random.Random | None = None) -> Exchange:
    """你出一招、分身出他擲好的那一招。兩邊各扣自己的池子（同奪璽單挑）。fight.bout 在（有人帶著本命戰法）時先照戰法打這一回合
    （tactics.step，亂數是 trng）：招可能被改掉、剋照無隙改、氣勢多推戰法那一份、沒挨打的那一邊不掉血、回的與焚身這類照池子算。
    擂台吃防具（鐵匠鋪與合成流程 3.9）：兩邊打中對方的那一下，各自乘過自己這一邊的 ArenaSide.cut（挑的人開打那一刻、分身報名那一刻抄的）
    與戰法的化勁（duel.blow_taken，合計夾在 Config.armor.total_cap）；放手一搏失手與戰法自扣不吃，也不磨耐久。"""
    tuning, battle, tt = content.config.duel, content.config.battle, content.config.tactics
    me, foe = fight.me, fight.foe
    his = fight.move
    step = None
    if fight.bout is not None and trng is not None:
        step = tactics.step(fight.bout, move, his, fight.edge, tt, trng, a_ratio=me.hp / max(1.0, me.hp_cap),
                            b_ratio=foe.hp / max(1.0, foe.hp_cap), b_auto=True)
        move, his = step.a_move, step.b_move
    mine, theirs = _weight(me, move or "", content), _weight(foe, his or "", content)
    beat = step.beat if step is not None else duel_base.counter(move, his)
    luck = rng.uniform(-tuning.luck, tuning.luck) * tactics.luck_scale(fight.bout if step is not None else None)
    push = round(tactics.scale_push(duel_base.push_of(mine, theirs, beat, me.role, tuning, battle, luck, foe_role=foe.role), step))
    my_hp = duel_base.harm_of(me.hp_cap, mine, theirs, beat, tuning)
    foe_hp = duel_base.harm_of(foe.hp_cap, theirs, mine, -beat, tuning)
    # 打中的那一下乘過各自的防具與戰法的化勁（鐵匠鋪與合成流程 3.9；兩邊各吃自己的，沒穿甲的跟以前一字不差）；失手與戰法自扣不吃
    cap = content.config.armor.total_cap
    my_hp = duel_base.blow_taken(my_hp, me.cut, step.a_cut if step is not None else 0.0, cap)
    foe_hp = duel_base.blow_taken(foe_hp, foe.cut, step.b_cut if step is not None else 0.0, cap)
    lines: list[str] = []
    skills: tuple[list[str], list[str]] = ([], [])
    if step is not None:
        skills = (list(step.a_skills), list(step.b_skills))
        push += round(step.push)
        my_hp = (my_hp if step.a_hit else 0) - round(step.a_hp * me.hp_cap)
        foe_hp = (foe_hp if step.b_hit else 0) - round(step.b_hp * foe.hp_cap)
        lines += list(step.lines)
        guarded, said = tactics.guard_pool(fight.bout, "a", me.hp, my_hp, me.hp_cap)
        my_hp = round(guarded)
        lines += said
        guarded, said = tactics.guard_pool(fight.bout, "b", foe.hp, foe_hp, foe.hp_cap)
        foe_hp = round(guarded)
        lines += said
    # 五項屬性的季：身法讓挨的那一下有機會閃掉——不掉氣血、這一回合的氣勢也推不動他（同閃成僵持；ArenaSide.dodge，faced 填；
    # 舊的季是 0，不擲骰、亂數一個都不多用）
    if me.dodge > 0 and my_hp > 0 and rng.random() < me.dodge:
        my_hp, push = 0, max(0, push)
        lines.append("你身形一閃，這一下打空了")
    if foe.dodge > 0 and foe_hp > 0 and rng.random() < foe.dodge:
        foe_hp, push = 0, min(0, push)
        lines.append(f"{foe.name}身形一閃，這一下打空了")
    my_hp, foe_hp = _pool(me, my_hp), _pool(foe, foe_hp)
    before = fight.edge
    fight.edge = _clamp(fight.edge + push)
    if step is not None:
        lines += tactics.close_round(fight.bout, fight.edge - before, tt, trng, skills)
    return Exchange(round(fight.edge - before), my_hp, foe_hp, beat, move, his, lines, skills)



def verdict(fight: ArenaFight, tuning: DuelTuning) -> str | None:
    """分出勝負沒有（挑的人的角度，同奪璽單挑）：你的池子見底或氣勢到底落敗；他的池子見底大勝；氣勢到頂提前大勝（寫大勝）；
    打滿看氣勢。還沒是 None。"""
    if fight.me.hp <= 0 or fight.edge <= tuning.early_lose:
        return "落敗"
    if fight.foe.hp <= 0 or fight.edge >= tuning.early_win:
        return "大勝"
    return duel_base.verdict_at(fight.edge, fight.me.hp, fight.round, fight.rounds, tuning)
