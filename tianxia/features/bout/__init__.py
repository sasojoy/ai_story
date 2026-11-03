"""單挑（單人頭目戰、擂台與台下的場邊事件）。功能包，開發規範手冊 3.2；全部拆包第 12 批搬進來（計畫
docs/superpowers/plans/2026-11-03-單挑包-第1批.md）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

單挑底層（剋、推力、挨打、防具、放手一搏、勝負：頭目戰、擂台、奪璽單挑共用）在核心 tianxia/core/duel_base.py；擂台的名次與稱號
（酒肆、名帖、玩家卡、榜單都讀）在核心 tianxia/core/arena_ranks.py——這一包的規則模組從那兩份 re-export。

拿 duel、arena 兩個前綴：假人看到這兩種選項怎麼按問這一包（bot_pick → bots.py，原本是 bot_policy.score 的那兩段）。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class BoutFeature(Feature):
    name = "bout"
    prefix = ("duel", "arena")  # duel:<招>、duel:flee；arena:<招>、arena:yield、arena:join、arena:fight:<名號鍵>、arena:back、arena:none
    content = ("duels.json", "arena_crowd.json")  # 頭目、場邊事件的固定句（content.py 照舊讀）
    # 頭目戰：正在打的那一場、這一季（與這一週）遇上幾次的帳、上一場開打的時刻；擂台：正在打的那一場、剛打完的收場卡、坐在擂台邊、
    # 今天挑了幾次（記在哪一天）、場邊事件每一種落在自己身上是哪一天、還等著模型重寫的那一句——換季都跟著新角色重來
    player_fields = ("duel", "duel_tally", "duel_last", "arena", "arena_last", "picking_arena", "arena_day", "arena_today",
                     "arena_crowd_seen", "arena_crowd_note")
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        """內容裡有頭目（duels.json）、或擂台開著（Config.arena.enabled），或此刻還在頭目戰、擂台上、坐在擂台邊：開關在坐著、打著的時候
        被關掉（沒經過 sync 收店）照樣按得到返回與三招、假人照樣只按返回（同酒肆）——搬包之前 choose 的那幾支、bot_policy.score 的那兩段
        都不看開關。"""
        from tianxia.core import arena_ranks  # noqa: PLC0415

        p = ctx.state.player
        return bool(ctx.content.duels) or arena_ranks.on(ctx.content) or p.duel is not None or p.arena is not None or p.picking_arena

    def bot_pick(self, ctx, option):
        """假人看到 duel:、arena: 那一顆的分數（原本 bot_policy.score 的那兩段）。"""
        from . import bots  # noqa: PLC0415

        return bots.score(option)


FEATURE = BoutFeature()
