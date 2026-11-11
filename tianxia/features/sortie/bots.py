"""假人看到出陣、守勢怎麼按與約戰卡上的事（開發規範手冊 3.8；原本寫在 bot_policy 的 score 的 act:train、act:duty 那幾行與 duel_play，全部拆包第 60 批搬來，Verb.bot 問；
bot_policy 留 `from .features.sortie.bots import duel_play`，take_turn 與測試照舊讀那個名字）。

_crippled、_cannot_push、_outmatched、_train_value、_bounty_here 與 ORDER_SCORE、BOUNTY_SCORE、PRACTICE_SCORE 別包也讀，第二輪第 89 批搬進共用層 bot_base，一律寫 `bot_base.X`，測試換 bot_base 的才打得到；
TRAIN_SCORE、DUTY_SCORE、封招的 duel_moves 只有這一包讀，同一批從 bot_policy、bot 搬來，舊名 re-export。**模組層不准碰 engine、bot_policy**（bot_policy 模組層 import 這個檔）。
這一路的先後算行為：_crippled → 運糧隊 → _cannot_push → _outmatched（跑模擬、有快取）→ 四樣加分 → _train_value。
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from tianxia import bot_base, orders, precise, tactics  # 共用規則層（照模組屬性叫，tally 軌換掉 orders.win_counts、duty_counts、precise.on）
from tianxia.models import MOVES

from . import duel_actions, duel_rules, rules

if TYPE_CHECKING:
    from tianxia.state import BotProfile

# ── 出陣約戰（減法季批 3b-3；整合設計 4.3、5.7「假人可以應約戰、封招，不可以寫字」）──
ANSWER_AFTER = 0.5  # 窗開過這麼多才應（前一半留給同一邊的真人先應；到時沒人應另有補位）【預設】
ANSWER_POWER_FLOOR = 0.7  # 應戰：自己的威力至少是攻方的這麼多才應（「威力不被壓太多」）【預設】
JOIN_CHANCE = 1 / 3  # 同袍的約戰去同去的機會（每個假人每一場擲一次，同一場永遠一樣）【預設】
TRAIN_SCORE = 0.6  # 遊歷本身的分數（低於探索）；對自己陣營有利的地點再加上大勢分
DUTY_SCORE = 0.5  # 守勢行動本身（不替軍令記功時）：低於探索，不然假人整天巡哨


def duel_moves(rng: random.Random) -> list[str]:
    """約戰封的三招（減法季批 3b；設計 5.7「假人可以應約戰、封招」，計畫 Task 3b-3）：對面封的招看不到，每一回合先猜一招，出剋它的那一招
    （tactics.best_against），其中隨機一回合換成隨便一招；不撤退（撤退是真人看形勢用的）。整季機器人與伺服器假人共用。"""
    random_round = rng.randrange(3)
    moves = []
    for i in range(3):
        guess = rng.choice(MOVES)
        moves.append(rng.choice(MOVES) if i == random_round else tactics.best_against([guess], list(MOVES)))
    return moves


def duel_play(game, profile: BotProfile, rng: random.Random) -> list[str] | None:
    """約戰卡上的事（sortie_cards）：對面貼的、同一區、窗開過一半、還有應戰次數與體力（卡上的 can_answer）、自己的威力不被壓太多的就應
    （封招 duel_moves）；同袍貼的約三分之一同去（卡上的 can_join：同一區、還有出陣次數）。不會應自己陣營的（那一張是同去）。都沒有是 None。"""
    if not game.duel_on():
        return None
    cards = duel_actions.sortie_cards(game) or []
    if not cards:
        return None
    duels = game.world.sortie_duels()
    power: float | None = None
    for card in cards:
        duel = duels.get(card["id"])
        if duel is None or duel.status not in ("open", "answered"):
            continue
        if card["role"] == "answer" and card["can_answer"]:
            if game.now - duel.opened_at < ANSWER_AFTER * (duel.expires_at - duel.opened_at):
                continue
            power = duel_actions.duel_power(game) if power is None else power
            if power < duel.attacker.power * ANSWER_POWER_FLOOR:
                continue
            return game.choose(f"{duel_rules.PREFIX}answer:{duel.id}:{','.join(duel_moves(rng))}")
        if card["role"] == "join" and card["can_join"]:
            if random.Random(f"{profile.seed}|同去|{duel.id}").random() >= JOIN_CHANCE:
                continue
            return game.choose(f"{duel_rules.PREFIX}join:{duel.id}")
    return None


def train(game, profile: BotProfile) -> float | None:
    """出陣（關著時遊歷）的分數；None＝不按。"""
    if bot_base._crippled(game):
        return None
    s, c = game.state, game.content
    convoy = game.duel_on() and game.duel_convoy_here()  # 約戰開著：運糧隊經過時出陣是截糧（自家的地方也打）
    if not convoy and bot_base._cannot_push(game, s.player.location):  # 領地爭奪：推不動的地方不出陣（翻地 QA 順帶：真人看得出有人一直在推不動的地方出陣）
        return None
    if bot_base._outmatched(game, s.player.location):  # 領地爭奪：贏面太低的地方不攻（打輸不推，只扣血掉銀兩）；去練功、去贏得了的地方
        return None
    bonus = bot_base.ORDER_SCORE if orders.win_counts(s, c, game._side(), s.player.location) else 0.0
    if rules.on(c) and game.sortie_mode() == "hold" and orders.duty_counts(s, c, game._side(), s.player.location):
        bonus += bot_base.ORDER_SCORE  # 出陣的守算一次守城（同守勢行動）
    bonus += bot_base.BOUNTY_SCORE if bot_base._bounty_here(game, "strike") else 0.0
    bonus += bot_base.PRACTICE_SCORE if precise.on(c, s.world) else 0.0  # 一類一顆：出陣照舊排在練功前面（9.2）
    return TRAIN_SCORE + bot_base._train_value(game, profile) + bonus


def duty(game) -> float:
    """守勢行動（計畫 T6）：替守城記功才值得做；約戰開著時不算守城（減法季批 3b：守是應戰）。"""
    s = game.state
    counts = not game.duel_on() and orders.duty_counts(s, game.content, game._side(), s.player.location)
    if game.duel_on() and orders.idle_duty_counts(s, game.content, game._side(), s.player.location):
        counts = True  # 沒人來打的守城：在自家地方按守勢記一次（一天一次；今天按過了選項是灰的）
    return DUTY_SCORE + (bot_base.ORDER_SCORE if counts else 0.0)
