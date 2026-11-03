"""假人看到決戰的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 battle 那一段與 bot_policy._battle_score，全部拆包第 7 批拿了
battle: 前綴之後搬來，照宴客）。bot_policy 照舊留著 _battle_score、JOIN_BATTLE_SCORE 這兩個名字（tests/bots/test_bot_policy.py、
tests/season/test_real_content.py 直接叫；指到這裡同一個函式、同一個數）。

集結時的加入、臨時投效由 bot_policy.take_turn 自己挑（battle:join 一看到就按、投效照 bot.enlist_pick），回合裡的三招由 battle_move 挑；
走到打分數的只有這兩支剩下的：加入與晚到一律 JOIN_BATTLE_SCORE，出招照份量，其餘（挑同伴、觀戰、已選擇……）不按。
"""
from __future__ import annotations

from tianxia import battle_instance  # 過渡：待搬（戰鬥規則核心：招的份量、氣血狀態）
from tianxia.core.option import Option

JOIN_BATTLE_SCORE = 100.0


def battle_score(game, arg: str) -> float | None:
    """集結或晚到時加入（一定站自己陣營那邊，引擎只給這個選項）；交戰中照自己每招的份量（乘這一場的氣血狀態）打分數，
    扣血相對剩下的氣血越重扣分越多（決戰改版一）。沒有招的選項一律 0。
    沒有快照（份量全 0）時只剩扣血的差別，損耗最低的固守分數最高。"""
    kind, _, tag = arg.partition(":")
    if kind in ("join", "join_late"):
        return JOIN_BATTLE_SCORE
    if kind != "act":
        return None
    battle = game.battle_now()  # 自己參戰的那一場（決戰或攻城，領地爭奪第二批）
    definition = game.content.battles[battle.battle_id]
    me = battle.participants.get(game.state.player.name)
    if me is None:
        return 0.0
    tuning = game.content.config.battle
    hp = max(me.neili, 1.0)
    option = battle_instance.option_of(definition, battle.act_index, me.faction, tag)
    if option is None or option.move is None:  # 放手一搏等沒有招的：假人不選（free_text 本來就排除）
        return 0.0
    return me.scores.get(option.move, 0.0) * battle_instance.condition(me) / 100 - tuning.damage[option.move] / hp


def score(game, option: Option) -> float | None:
    """選項的分數；None＝假人不會按。"""
    return battle_score(game, option.id.partition(":")[2])
