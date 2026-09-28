"""戰鬥：武學相剋、一般遭遇的自動結算、關鍵戰鬥的回合選擇。"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .models import Content, Enemy
from .state import BattleState, GameState

BEATS = {"剛": "巧", "巧": "快", "快": "柔", "柔": "剛"}  # key 克制 value
ADVANTAGE = 1.25
MAX_AUTO_ROUNDS = 10
MAX_KEY_ROUNDS = 12
TACTICS = ("強攻", "巧取", "固守", "絕招", "撤退")


@dataclass
class Fighter:
    name: str
    hp: int
    atk: int
    dfn: int
    spd: int
    style: str


def player_fighter(state: GameState, content: Content) -> Fighter:
    p = state.player
    atk, dfn, spd = p.stats["str"] * 2, p.stats["con"] * 2, p.stats["agi"] * 2
    style = "無"
    for skill_id in p.equipped:
        if skill_id is None:
            continue
        skill = content.skills[skill_id]
        bonus = skill.power * (10 + p.skills[skill_id].level) // 20
        if skill.slot == "外功":
            atk += bonus
            if style == "無":
                style = skill.style
        elif skill.slot == "內功":
            dfn += bonus
        else:
            spd += bonus
    return Fighter(p.name, 80 + p.stats["con"] * 5, atk, dfn, spd, style)


def enemy_fighter(enemy: Enemy) -> Fighter:
    return Fighter(enemy.name, enemy.hp, enemy.atk, enemy.dfn, enemy.spd, enemy.style)


def style_multiplier(attacker: str, defender: str) -> float:
    if BEATS.get(attacker) == defender:
        return ADVANTAGE
    if BEATS.get(defender) == attacker:
        return 1 / ADVANTAGE
    return 1.0


def damage(attacker: Fighter, defender: Fighter, rng: random.Random, mult: float = 1.0) -> int:
    base = attacker.atk * style_multiplier(attacker.style, defender.style) * mult - defender.dfn * 0.5
    return max(1, round(base * rng.uniform(0.85, 1.15)))


def auto_battle(player: Fighter, enemy: Fighter, rng: random.Random) -> tuple[bool, int]:
    """回傳（是否勝利, 交手回合數）。回合打完仍未分勝負時，比較剩餘氣血比例。"""
    fighters = {"p": player, "e": enemy}
    hp = {"p": player.hp, "e": enemy.hp}
    order = ["p", "e"] if player.spd >= enemy.spd else ["e", "p"]
    for rnd in range(1, MAX_AUTO_ROUNDS + 1):
        for side in order:
            other = "e" if side == "p" else "p"
            hp[other] -= damage(fighters[side], fighters[other], rng)
            if hp[other] <= 0:
                return side == "p", rnd
    return hp["p"] / player.hp >= hp["e"] / enemy.hp, MAX_AUTO_ROUNDS


def start_battle(
    state: GameState, content: Content, enemy_id: str, event_id: str, choice_index: int
) -> list[str]:
    pf = player_fighter(state, content)
    enemy = content.enemies[enemy_id]
    state.battle = BattleState(
        enemy_id=enemy_id, event_id=event_id, choice_index=choice_index,
        player_hp=pf.hp, player_hp_max=pf.hp, enemy_hp=enemy.hp,
    )
    return [f"⚔ 對手：{enemy.name}——{enemy.desc}", "生死一線，你要如何應對？"]


def battle_status(state: GameState, content: Content) -> str:
    b = state.battle
    enemy = content.enemies[b.enemy_id]
    return (
        f"第{b.round}回合｜你 {max(0, b.player_hp)}/{b.player_hp_max}　"
        f"{enemy.name} {max(0, b.enemy_hp)}/{enemy.hp}"
    )


def battle_round(
    state: GameState, content: Content, tactic: str, rng: random.Random
) -> tuple[str | None, list[str]]:
    b = state.battle
    pf = player_fighter(state, content)
    ef = enemy_fighter(content.enemies[b.enemy_id])
    deal, take, heal = 1.0, 1.0, 0
    msgs: list[str] = []
    if tactic == "強攻":
        deal, take = 1.4, 1.2
        msgs.append("你搶身而上，招招搶攻！")
    elif tactic == "巧取":
        chance = min(0.9, max(0.1, 0.5 + (state.player.stats["wis"] * 2 - ef.spd) * 0.03))
        if rng.random() < chance:
            deal, take = 1.8, 0.5
            msgs.append("你看準破綻，以巧破力！")
        else:
            deal, take = 0.5, 1.0
            msgs.append("你想以巧取勝，卻被對方識破。")
    elif tactic == "固守":
        deal, take, heal = 0.5, 0.4, b.player_hp_max // 10
        msgs.append("你守住門戶，調勻氣息。")
    elif tactic == "絕招":
        if b.ultimate_used:
            raise ValueError("絕招每場只能施展一次")
        b.ultimate_used = True
        deal = 2.2
        msgs.append("你運起全身功力，施展壓箱絕技！")
    elif tactic == "撤退":
        chance = min(0.9, max(0.1, 0.4 + (pf.spd - ef.spd) * 0.02))
        if rng.random() < chance:
            state.battle = None
            return "flee", msgs + ["你虛晃一招，全身而退。"]
        deal = 0.0
        msgs.append("你想抽身而退，卻被對方纏住！")
    else:
        raise ValueError(f"未知的戰術：{tactic}")
    b.round += 1

    def player_hits() -> None:
        if deal > 0:
            dmg = damage(pf, ef, rng, deal)
            b.enemy_hp -= dmg
            msgs.append(f"你對{ef.name}造成 {dmg} 點傷害。")

    def enemy_hits() -> None:
        dmg = damage(ef, pf, rng, take)
        b.player_hp -= dmg
        msgs.append(f"{ef.name}對你造成 {dmg} 點傷害。")

    for step in ([enemy_hits, player_hits] if ef.spd > pf.spd else [player_hits, enemy_hits]):
        step()
        if b.enemy_hp <= 0:
            state.battle = None
            return "win", msgs + [f"{ef.name}倒地不起，你贏了！"]
        if b.player_hp <= 0:
            state.battle = None
            return "lose", msgs + ["你眼前一黑，敗下陣來……"]
    if heal:
        b.player_hp = min(b.player_hp_max, b.player_hp + heal)
    if b.round >= MAX_KEY_ROUNDS:
        won = b.player_hp / b.player_hp_max >= b.enemy_hp / ef.hp
        state.battle = None
        return ("win" if won else "lose"), msgs + ["雙方力竭，勝負已分。"]
    msgs.append(battle_status(state, content))
    return None, msgs
