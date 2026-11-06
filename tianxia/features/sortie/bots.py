"""假人看到出陣、守勢怎麼按與約戰卡上的事（開發規範手冊 3.8；原本寫在 bot_policy 的 score 的 act:train、act:duty 那幾行與 duel_play，全部拆包第 60 批搬來，Verb.bot 問；
bot_policy 留 `from .features.sortie.bots import duel_play`，take_turn 與測試照舊讀那個名字）。

_crippled、_cannot_push、_outmatched、_train_value、_bounty_here 與分數常數還在 bot_policy（移動包的 move: 也讀，測試換的是 bot_policy 的屬性；計畫第三節），所以經 `from tianxia import bot_policy`
延後 import（舊模組 import engine，包不能在模組載入時 import 它；第 47 批前例）；照模組屬性讀，測試換掉也生效。**模組層不准碰 engine、bot_policy**（bot_policy 模組層 import 這個檔）。
這一路的先後算行為：_crippled → 運糧隊 → _cannot_push → _outmatched（跑模擬、有快取）→ 四樣加分 → _train_value。
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from tianxia import orders, precise  # 共用規則層（照模組屬性叫，tally 軌換掉 orders.win_counts、duty_counts、precise.on）

from . import actions, duel_actions, duel_rules, rules

if TYPE_CHECKING:
    from tianxia.models import Location
    from tianxia.state import BotProfile

# ── 出陣約戰（減法季批 3b-3；整合設計 4.3、5.7「假人可以應約戰、封招，不可以寫字」）──
ANSWER_AFTER = 0.5  # 窗開過這麼多才應（前一半留給同一邊的真人先應；到時沒人應另有補位）【預設】
ANSWER_POWER_FLOOR = 0.7  # 應戰：自己的威力至少是攻方的這麼多才應（「威力不被壓太多」）【預設】
JOIN_CHANCE = 1 / 3  # 同袍的約戰去同去的機會（每個假人每一場擲一次，同一場永遠一樣）【預設】


def duel_play(game, profile: BotProfile, rng: random.Random) -> list[str] | None:
    """約戰卡上的事（sortie_cards）：對面貼的、同一區、窗開過一半、還有應戰次數與體力（卡上的 can_answer）、自己的威力不被壓太多的就應
    （封招 bot.duel_moves）；同袍貼的約三分之一同去（卡上的 can_join：同一區、還有出陣次數）。不會應自己陣營的（那一張是同去）。都沒有是 None。"""
    from tianxia import bot  # noqa: PLC0415  過渡：待搬（整季機器人與假人共用的底層 bot.py：封招）

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
            return game.choose(f"{duel_rules.PREFIX}answer:{duel.id}:{','.join(bot.duel_moves(rng))}")
        if card["role"] == "join" and card["can_join"]:
            if random.Random(f"{profile.seed}|同去|{duel.id}").random() >= JOIN_CHANCE:
                continue
            return game.choose(f"{duel_rules.PREFIX}join:{duel.id}")
    return None


def foes(game, loc: Location) -> list[str]:
    """那裡出陣會打的每一路（bot_policy._sortie_win 照勝算平均）。"""
    return actions.sortie_foes(game, loc)


def train(game, profile: BotProfile) -> float | None:
    """出陣（關著時遊歷）的分數；None＝不按。"""
    from tianxia import bot_policy as bp  # noqa: PLC0415  過渡：待搬（假人的分數與挑法還在舊模組）

    if bp._crippled(game):
        return None
    s, c = game.state, game.content
    convoy = game.duel_on() and game.duel_convoy_here()  # 約戰開著：運糧隊經過時出陣是截糧（自家的地方也打）
    if not convoy and bp._cannot_push(game, s.player.location):  # 領地爭奪：推不動的地方不出陣（翻地 QA 順帶：真人看得出有人一直在推不動的地方出陣）
        return None
    if bp._outmatched(game, s.player.location):  # 領地爭奪：贏面太低的地方不攻（打輸不推，只扣血掉銀兩）；去練功、去贏得了的地方
        return None
    bonus = bp.ORDER_SCORE if orders.win_counts(s, c, game._side(), s.player.location) else 0.0
    if rules.on(c) and game.sortie_mode() == "hold" and orders.duty_counts(s, c, game._side(), s.player.location):
        bonus += bp.ORDER_SCORE  # 出陣的守算一次守城（同守勢行動）
    bonus += bp.BOUNTY_SCORE if bp._bounty_here(game, "strike") else 0.0
    bonus += bp.PRACTICE_SCORE if precise.on(c, s.world) else 0.0  # 一類一顆：出陣照舊排在練功前面（9.2）
    return bp.TRAIN_SCORE + bp._train_value(game, profile) + bonus


def duty(game) -> float:
    """守勢行動（計畫 T6）：替守城記功才值得做；約戰開著時不算守城（減法季批 3b：守是應戰）。"""
    from tianxia import bot_policy as bp  # noqa: PLC0415  過渡：待搬（假人的分數與挑法還在舊模組）

    s = game.state
    counts = not game.duel_on() and orders.duty_counts(s, game.content, game._side(), s.player.location)
    return bp.DUTY_SCORE + (bp.ORDER_SCORE if counts else 0.0)
