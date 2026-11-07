"""假人看到馬市的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 market 那兩行，全部拆包第 42 批拿了 market: 前綴之後搬來，照鐵匠鋪）。
bot_policy 照舊留著 MARKET_SCORE 這個名字（tests/bots/test_bot_policy.py 直接讀；數同一個，8.0 = SMITH_SCORE = BOUNTY_SCORE）。`act:market`（進馬市）的分數
第 60 批搬來（enter，Verb.bot 問）。

整季機器人與假人共用的 market_want、MOUNT_SILVER_RESERVE 第二輪第 89 批從 bot 搬來，visit_market、feed_mount、wear_better 第 101 批從 bot 搬來（bot 留 re-export 同一批物件）。
**模組層不准碰 engine 與假人殼**（bot 模組層 import 這個檔）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import mounts, treasures
from tianxia.core.option import Option

if TYPE_CHECKING:
    from tianxia.engine import Game

MOUNT_SILVER_RESERVE = 30  # 買了馬至少還留幾兩（療傷用；同 bot_policy.LEARN_SILVER_RESERVE）：設計第九節「100＋保留額度」
MARKET_SCORE = 8.0  # 馬市（裝備四欄設計第九節）：趕路疾行省體力，跟鐵匠鋪一樣急；真人會騎馬，假人也要（bot_policy.MARKET_SCORE = SMITH_SCORE 同一個數）


def enter(game) -> float | None:
    """act:market（馬市）：有要換、要買、要餵的才進去（不然只是開了又離開；不寫的話會落到 ACT_SCORES 的 0.0、進去就卡住）。"""
    return MARKET_SCORE if market_want(game) else None


def score(game, option: Option) -> float | None:
    """選項的分數；None＝假人不會按。馬市上：照 market_want 按那一顆（換、買、餵），沒事就離開。"""
    arg = option.id.partition(":")[2]
    return MARKET_SCORE if option.id == market_want(game) else 0.0 if arg == "back" else None


def market_want(game: Game) -> str | None:
    """在馬市最該按的那一顆（整季機器人與伺服器假人共用；裝備四欄設計第九節）：換上更快的、沒馬就買（留 MOUNT_SILVER_RESERVE）、
    飽足低於 mounts.FEED_AT 就餵。沒事是 None。"""
    return mounts.wanted(game.state, game.content, reserve=MOUNT_SILVER_RESERVE)


def visit_market(game: Game) -> None:
    """城裡有馬市就看一眼（裝備四欄設計第九節）：照 market_want 換、買、餵（最多各一次），最後離開。不花體力。
    沒事要做時連選單都不叫。假人不走這裡（bot_policy 照 market_want 給分）。"""
    s = game.state
    if s.pending_event or market_want(game) is None:
        return

    def enabled() -> set[str]:
        return {o.id for o in game.options(odds=False) if o.enabled}

    if "act:market" not in enabled():
        return
    game.choose("act:market")
    for _ in range(3):
        move = market_want(game)
        if move is None or move not in enabled():
            break
        game.choose(move)
    if s.player.picking_market:
        game.choose(mounts.BACK)


def feed_mount(game: Game) -> None:
    """飽足低於 mounts.FEED_AT 就餵（設計第九節：約每 10 段一次；走 Game.feed_mount，同修練頁的「餵」）：閒著時哪裡都能餵，
    在路上、閉關中、沒有一階素材時什麼都不做。整季機器人每一步看一次，假人在 bot_policy.look_after 看。"""
    s, c = game.state, game.content
    item = mounts.riding(s, c)
    if item is not None and item.edge < mounts.FEED_AT and mounts.feed_problem(s, c) is None:
        game.feed_mount()


def wear_better(game: Game) -> None:
    """裝備庫裡有更好的寶物或更快的馬就換上（裝備四欄設計第九節；整季機器人每一步看一次，假人在 bot_policy.look_after 看）：
    寶物照 treasures.wanted（固定順序；寶物不設限制，身上已經是最前面的就不換），馬照 mounts.better_mount（吃飽的腳力，同馬市的
    wanted；路上不換，2.3）。走 Game.wield_weapon（修練頁的「換上」），跟真人一樣。拿到新的、那一欄空著時本來就自動穿上，這裡只管換；不叫模型。"""
    s, c = game.state, game.content
    tid = treasures.wanted(s, c)
    if tid is not None:
        game.wield_weapon(tid)
    if s.player.journey is None and (horse := mounts.better_mount(s, c)) is not None:
        game.wield_weapon(horse)
