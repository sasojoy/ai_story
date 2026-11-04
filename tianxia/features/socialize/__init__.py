"""交友求見（功能包；開發規範手冊 3.2）：交友（act:socialize）、指名求見（act:call 打開名單、call:<人物>）、被打發、每位人物每個遊戲日談幾輪、結識奇遇（福緣）。
全部拆包第 21 批搬進來（計畫 docs/superpowers/plans/2026-11-04-交友求見包-第1批.md）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

選項前綴 `call:`（`call:<人物 id>`、`call:back`）；`act:socialize`、`act:call` 兩格是核心 act 子動詞（總表第 57 批才接 Verb），留在核心原位叫這一包的委派。
`call:` 的 choose 接掛鉤（鎖外生成好的一輪 prepared 經 `ctx._talk_turn` 寄放，第 20 批人物對話寫的；標題在動作之前拿）；進鎖後的重驗 `_checked_prepared`
與做完之後的引導 `_note_action("socialize")` 仍在 `Game.choose` 原位（位置算行為）。enabled 一直是 True（沒有自己的總開關；一類一顆 precise、福緣 roster 各有自己的開關）。
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome


class SocializeFeature(Feature):
    name = "socialize"
    prefix = "call"  # 指名求見：call:<人物>、call:back（假人只按返回，見 bots.py）
    content = (  # 交友事件（總表附錄甲）；content.py 照舊讀（第 62 批起照它載）；檔名照舊。recruit.json 招募的事件檔歸誰交 PM 定（計畫「交 PM 定的」第 1 條）
        "events/social_nanyang_yingchuan.json", "events/social_north.json", "events/social_runan.json",
    )
    # 認領的 PlayerState 欄位（手冊 3.5：留在原地）：每位人物這個遊戲日談了幾輪、求見名單開著。換季全部跟著新角色重來
    player_fields = ("talks_today", "picking_audience")
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return True

    def choose(self, ctx, kind, arg):
        """指名求見（call:<人物>、call:back）；一開頭就收起名單，名望不夠被打發、夠了開口對話（動作在 actions.call）。"""
        if kind != "call":
            return None
        from . import actions  # noqa: PLC0415

        return Outcome(title=actions.call_title(ctx, arg), run=lambda: actions.call(ctx, arg, ctx._talk_turn))

    def bot_pick(self, ctx, option):
        """假人看到 call: 的選項怎麼按（原本 bot_policy.score 的 call 那一段）：只按返回。"""
        from . import bots  # noqa: PLC0415

        return bots.score(option)


FEATURE = SocializeFeature()
