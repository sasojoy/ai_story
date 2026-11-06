"""假人看到懸賞榜的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 bounty 那一段，全部拆包第 45 批拿了 bounty: 前綴之後搬來，照鐵匠鋪包）。
`act:bounties`（打開榜）的分數、_takeable、_bounty_here、_bounty_hop、BOUNTY_MOVE_SCORE 還在 bot_policy（前綴 act 是核心的，掛鉤問不到），bot_policy.BOUNTY_SCORE 照舊留著（同一個數；
SMITH_SCORE = BOUNTY_SCORE 等還在用）。整季機器人用的 bot.take_bounties 與 pick() 排除的 act:bounties 是共用底層，不搬；它們經舊名 bounties 叫 rules。
"""
from __future__ import annotations

from tianxia.core.option import Option

from . import rules

BOUNTY_SCORE = 8.0  # 比推大勢的遊歷值得，比軍令低（陣營的事先做）；bot_policy.BOUNTY_SCORE 同一個數


def score(game, option: Option) -> float | None:
    """選項的分數；None＝假人不會按。懸賞榜上：揭得下的去揭，揭滿了或沒得揭就返回；不放棄手上的。"""
    arg = option.id.partition(":")[2]
    verb = arg.partition(":")[0]
    if verb in ("pick", "give"):  # 求兵：只交 rules.give_choice 指的那一張、那一件（不隨機，懸賞榜設計 9.3）
        move = rules.give_choice(game.state, game.content, game.world)
        wanted = None if move is None else f"bounty:pick:{move[0]}" if verb == "pick" else f"bounty:give:{move[0]}:{move[1]}"
        return BOUNTY_SCORE if option.id == wanted else None
    return BOUNTY_SCORE if verb == "take" else 0.0 if verb in ("back", "unpick") else None
