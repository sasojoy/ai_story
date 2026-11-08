"""假人看到銀兩出口與捐軍備兩串選單的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 dadian、donate 兩段，
全部拆包第 43 批拿了 donate:、dadian: 前綴之後搬來）。

萬一停在打點那一間店裡只會離開（每一顆都 0.0）；萬一停在軍需官那一串裡只會離開（捐由 look_after 的 bot.donate_spare 直接捐，不按這一串的鈕）。
`act:donate`、`act:dadian` 是 act 子動詞，第 60 批接進 Verb（bot 回 None：假人不進，只是打開一間店；以前落到 ACT_SCORES 的 0.0，隨手挑的那一半會按開、
那一串的鈕又都不打分，假人就停在大本營的軍需官前面一整季，2026-10-22 量 7 天季時看到：季末十三個假人有七到十個卡在這裡）。

捐多少（donate_want、donate_spare）第二輪第 101 批從 bot 搬來，舊名 re-export 同一批物件；留多少（trade_keep、TRADE_MOVES）鐵匠鋪也讀，在共用層 bot_base，一律寫 `bot_base.X`。**模組層不准碰 engine 與假人殼**（bot 模組層 import 這個檔）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import bot_base, economy
from tianxia.core.option import Option

if TYPE_CHECKING:
    from tianxia.engine import Game


def score(option: Option) -> float | None:
    """選項的分數；None＝假人不會按。"""
    kind, _, arg = option.id.partition(":")
    if kind == "dadian":  # 萬一停在打點那一間店裡：只會離開
        return 0.0
    # 萬一停在軍需官那一串裡（捐軍備）：只會離開；捐由 look_after 的 bot.donate_spare 直接捐，不按這一串的鈕
    return 0.0 if arg == "back" else None


def donate_want(game: Game) -> tuple[str, int] | None:
    """在自家大本營捐什麼（素材與經濟計畫 B5）：今天還有點數時，一階、二階多過留的量（TRADE_KEEP）的部分，一階先；三階不捐。
    回 (素材, 個數)（個數已經照今天剩的點數切過），沒事是 None。人在不在大本營由 donate_spare 問。"""
    s, c = game.state, game.content
    if not c.config.economy.donate:
        return None
    room = economy.donate_room(s, c, game.econ_day())
    keep = bot_base.trade_keep(c)
    for tier in sorted(keep):
        for mid, n in sorted(s.player.materials.items()):
            material = c.materials.get(mid)
            points = economy.donate_points(c, mid)
            if material is None or material.tier != tier or points <= 0:
                continue
            count = min(n - keep[tier], room // points)
            if count > 0:
                return mid, count
    return None


def donate_spare(game: Game) -> None:
    """人在自家大本營、閒著時，照 donate_want 捐到沒事為止（Game.donate，跟真人同一條）；不在大本營什麼都不做：不為了它繞路。"""
    for _ in range(bot_base.TRADE_MOVES):
        if not game.can_donate_here():
            return
        move = donate_want(game)
        if move is None:
            return
        before = dict(game.state.player.materials)
        game.donate(*move)
        if game.state.player.materials == before:
            return
