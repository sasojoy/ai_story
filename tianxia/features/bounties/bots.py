"""假人看到懸賞榜的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 bounty 那一段，全部拆包第 45 批拿了 bounty: 前綴之後搬來，照鐵匠鋪包）。
`act:bounties`（打開榜）的分數與 takeable 第 60 批搬來（enter，Verb.bot 問；bot.pick 不按它是 Verb.bot_skip）。_bounty_here、_bounty_hop、BOUNTY_MOVE_SCORE 還在 bot_policy（移動包的 move: 也讀），
bot_policy.BOUNTY_SCORE、_takeable 名字照舊留著（同一個數、同一個函式；SMITH_SCORE = BOUNTY_SCORE 等還在用，測試讀 _takeable）。整季機器人用的 bot.take_bounties 是共用底層，不搬；它經舊名 bounties 叫 rules。
**模組層不准碰 engine、bot_policy**（bot_policy 模組層 import 這個檔）。
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


def enter(game) -> float | None:
    """act:bounties（懸賞榜）：有揭得下的才打開（不然只是開了又返回）。"""
    return BOUNTY_SCORE if takeable(game) else None


def takeable(game) -> bool:
    """此地的懸賞榜上有揭得下的，或有交得出的求兵（rules.give_choice）：假人為了交東西也會打開榜（懸賞榜設計 9.3）。
    假人不為了交東西繞路（rules.targets 不列求兵）。
    手上已經揭了的不算（榜上那一張是「放棄」、沒有「揭下」）：以前算進來，揭著一張還沒交的假人每路過有懸賞榜的城鎮就打開、什麼都揭不了又關上，
    下一輪又打開（2026-10-22 量 7 天季：前三天十三個假人開了又關上九十到一百四十次，每一次白花兩輪）。"""
    s, c = game.state, game.content
    held = {b.id for b in rules.mine(s, c)}
    if any(b.id not in held and rules.can_take(s, b) and rules.take_problem(s, c, b) is None for b in rules.open_bounties(s, c)):
        return True
    return rules.give_choice(s, c, game.world) is not None
