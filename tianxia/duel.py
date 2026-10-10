"""單人頭目戰（Joy 2026-10-10：「多加一些特殊事件，有種打小 boss 的感覺，也可以算是大事件的單人體驗版，可以放手一搏自訂行動」）。

在有頭目的地點探索時可能遇上（content/duels.json，DuelBoss）。一場 3～5 回合：每回合你出決戰的三招之一（固守剋強攻、強攻剋奇襲、
奇襲剋固守）或放手一搏（20 字自訂行動：模型在行動鎖外只評成功率、寫成敗兩版劇情，擲骰與推進、損耗全由這裡算）；他也出一招，
回合開始時你看得到他的架勢（有幾成是虛招，DuelTuning.tell_truth）。兩邊爭一條氣勢，你用自己的氣血池（開打時的氣血）。
份量、職位、放手一搏的實力倍數與軍師、參謀照決戰的規則（battle_instance）。數字都在 Config.duel（DuelTuning）。

這個模組只算數字與句子、改 DuelState；遇上、收場（獎勵、戰報、扣回本人的氣血）在 Game（engine.py）。
"""
from __future__ import annotations

import random
from typing import NamedTuple

from . import battle_instance, prologue
from .models import BEATS, MOVES, BattleTuning, Content, DuelBoss, DuelFoe, DuelTuning
from .state import DuelState, GameState

# 他出招之前你看到的架勢（每一招兩句，挑一句）。文字待內容方改
TELLS: dict[str, tuple[str, ...]] = {
    "強攻": ("他沉肩墜肘，腳下一蹬，像是要硬衝過來。", "他把兵刃高高舉起，眼裡全是殺氣。"),
    "固守": ("他退了半步，門戶守得嚴嚴實實。", "他氣息一沉，像一塊石頭似的等你上門。"),
    "奇襲": ("他眼珠亂轉，腳下悄悄往你側面繞。", "他身形一晃，看不出下一步要從哪裡來。"),
}
COUNTER_WORDS = {1: "你這一招正剋住他", -1: "他這一招正剋住你", 0: "兩邊招式相當"}


def season_key(state: GameState, boss_id: str) -> str:
    return f"{state.player.season_number}:{boss_id}"


def cooling(state: GameState, tuning: DuelTuning) -> bool:
    """上一場頭目戰開打到現在還沒過 cooldown_seconds（同一季的世界秒；換了季就不算）。"""
    last = state.player.duel_last
    if len(last) != 2 or int(last[0]) != state.player.season_number:
        return False
    return 0 <= state.world.time - last[1] < tuning.cooldown_seconds


def available(state: GameState, content: Content) -> DuelBoss | None:
    """此刻在這裡探索遇得上的頭目（照 id 排第一個）：不在序章、沒有正在打的、不在冷卻、這一季遇上這一隻還沒滿 per_boss_season 次。"""
    p, tuning = state.player, content.config.duel
    if p.duel is not None or prologue.active(state, content) or cooling(state, tuning):
        return None
    for boss in sorted(content.duels.values(), key=lambda b: b.id):
        if p.location in boss.locations and p.duel_tally.get(season_key(state, boss.id), 0) < tuning.per_boss_season:
            return boss
    return None


def foe_index(boss: DuelBoss, faction: str | None) -> int:
    """照玩家的陣營挑面貌：第一個不是自己人的（散人就是第一個）。載入時檢查過每個陣營都挑得到。"""
    return next((i for i, foe in enumerate(boss.foes) if faction is None or foe.side != faction), 0)


def foe_of(content: Content, duel: DuelState) -> tuple[DuelBoss, DuelFoe]:
    boss = content.duels[duel.boss]
    return boss, boss.foes[duel.foe]


def roll_next(duel: DuelState, foe: DuelFoe, tuning: DuelTuning, rng: random.Random) -> None:
    """擲他下一回合的招與你看到的架勢：招照他的偏好（沒寫的當 1）；架勢 tell_truth 的機會照實，其餘是另一招的架勢（虛招）。"""
    weights = [foe.moves.get(m, 1.0) for m in MOVES]
    duel.move = rng.choices(MOVES, weights=weights)[0]
    shown = duel.move if rng.random() < tuning.tell_truth else rng.choice([m for m in MOVES if m != duel.move])
    duel.tell = rng.choice(TELLS[shown])


def foe_strength(battle: BattleTuning, tuning: DuelTuning, boss: DuelBoss) -> float:
    """他的份量：照決戰的實力算他的難度，乘適性的基準（foe_fit）。"""
    return battle_instance.strength(battle, boss.difficulty) * tuning.foe_fit


def counter(mine: str, his: str) -> int:
    """剋：你剋他 +1、他剋你 −1、同招或不相干 0。"""
    if BEATS[mine] == his:
        return 1
    if BEATS[his] == mine:
        return -1
    return 0


def _clamp(edge: float) -> float:
    return max(0.0, min(100.0, edge))


def exchange(
    duel: DuelState, boss: DuelBoss, move: str, tuning: DuelTuning, battle: BattleTuning, rng: random.Random,
) -> tuple[int, int, int]:
    """出一招：（氣勢推了多少, 你掉多少氣血, 剋）。改 duel.edge、duel.hp。參謀被剋時吃虧少一截（同決戰）。"""
    mine = duel.scores.get(move) or battle_instance.strength(battle, duel.power) * tuning.foe_fit
    theirs = foe_strength(battle, tuning, boss)
    ratio = mine / (mine + theirs) if mine + theirs > 0 else 0.5
    beat = counter(move, duel.move)
    weight = beat * (1 - battle.role_counter_relief) if beat < 0 and duel.role == "lore" else beat
    delta = round(tuning.push_base * (2 * ratio - 1) + tuning.counter_push * weight + rng.uniform(-tuning.luck, tuning.luck))
    harm = tuning.hit_countered if beat < 0 else tuning.hit_countering if beat > 0 else 1.0
    scale = max(0.5, min(tuning.hit_scale_max, (theirs / mine) ** 0.5)) if mine > 0 else tuning.hit_scale_max
    hp = min(duel.hp, round(duel.hp_cap * tuning.hit * harm * scale))
    before = duel.edge
    duel.edge = _clamp(duel.edge + delta)
    duel.hp -= hp
    return round(duel.edge - before), hp, beat


def gamble(
    duel: DuelState, rate: int, tuning: DuelTuning, battle: BattleTuning, rng: random.Random,
) -> tuple[bool, int, int, int]:
    """放手一搏：（成了沒有, 氣勢推了多少, 你掉多少氣血, 實際的成功率）。成功率是模型評的再加軍師的（夾在 0～100）；
    成了的推進乘實力倍數（同決戰），沒成的不乘。這一回合他的招不算（你搶了先手，或自己栽了）。"""
    rate = max(0, min(100, rate + (battle.role_gamble_rate if duel.role == "wis" else 0)))
    risk = 100 - rate
    won = rng.random() * 100 < rate
    if won:
        might = battle_instance.strength(battle, duel.power) / battle.gamble_strength_ref
        might = max(battle.gamble_strength_min, min(battle.gamble_strength_max, might))
        delta = max(1, round((tuning.gamble_base + risk * tuning.gamble_per_risk) * might))
        hp = round(duel.hp_cap * tuning.success_hp)
    else:
        delta = -min(round(tuning.fail_cap), round(risk * tuning.fail_per_risk))
        hp = round(duel.hp_cap * (tuning.fail_hp_base + risk * tuning.fail_hp_per_risk))
    hp = min(duel.hp, hp)
    before = duel.edge
    duel.edge = _clamp(duel.edge + delta)
    duel.hp -= hp
    return won, round(duel.edge - before), hp, rate


def verdict(duel: DuelState, boss: DuelBoss, tuning: DuelTuning) -> str | None:
    """打完這一回合分出勝負沒有：池子見底或氣勢到 early_lose 以下提前落敗、到 early_win 以上提前大勝；打滿回合看氣勢。還沒是 None。"""
    if duel.hp <= 0 or duel.edge <= tuning.early_lose:
        return "落敗"
    if duel.edge >= tuning.early_win:
        return "大勝"
    if duel.round < boss.rounds:
        return None
    if duel.edge >= tuning.big:
        return "大勝"
    if duel.edge >= tuning.win:
        return "險勝"
    return "僵持" if duel.edge > tuning.draw else "落敗"


def shown_move(duel: DuelState) -> str | None:
    """你看到的架勢是哪一招的（不一定是他真的要出的）。"""
    return next((m for m, tells in TELLS.items() if duel.tell in tells), None)


def answer_to(duel: DuelState) -> str | None:
    """剋得住你看到的架勢的那一招（假人照它出招：真人也是看架勢出招）。"""
    shown = shown_move(duel)
    return next((m for m in MOVES if BEATS[m] == shown), None) if shown else None


def move_label(move: str) -> str:
    """選單上的一招：寫它剋哪一招（「固守（剋強攻）」）。"""
    return f"{move}（剋{BEATS[move]}）"


def edge_words(edge: float) -> str:
    """氣勢的一句話（場景用）。"""
    if edge >= 75:
        return "你大佔上風"
    if edge >= 58:
        return "你略佔上風"
    if edge > 42:
        return "兩邊僵持不下"
    if edge > 25:
        return "你落了下風"
    return "你被壓著打"


# ── 放手一搏的情境（給模型評成功率、寫成敗兩版劇情：battle_instance.assess_gamble）──────────

SETTING = "江湖上一對一單打獨鬥的"
PLACE = "打鬥"


class Scene(NamedTuple):
    """assess_gamble 只讀 title 與 text：決戰傳那一幕，頭目戰傳這個。"""

    title: str
    text: str


def scene(content: Content, duel: DuelState) -> Scene:
    boss, foe = foe_of(content, duel)
    return Scene(f"{foe.title}{foe.name}", f"{foe.intro}（第 {duel.round + 1}／{boss.rounds} 回合，{edge_words(duel.edge)}）{duel.tell}")
