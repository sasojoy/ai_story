"""酒肆（帶「酒肆」標籤的城鎮裡的一間：打聽、題壁、請酒、藏行跡、反查、買殺手、問酒家、鄰桌閒談）。功能包，開發規範手冊 3.2；
主動搬六包第 10 批搬進來（引擎那一半；網頁那一半 app.js、style.css 第 3 階才切）。README.md 寫這一包做什麼、導覽與設計稿、
認領的欄位、還留在原位的接縫。

- rules.py：純規則（原 tianxia/tavern.py；那個名字留成指到這裡的別名）
- ask.py：問酒家照問句找事實（原 tianxia/tavern_ask.py；同上）
- actions.py：原本 Game 上酒肆的 43 個方法（Game 留一行委派）
- bots.py：假人的分數（原本 bot_policy.score 的 tavern 那一段）

選單接管那一格（坐在酒肆裡）、act:tavern 入口、sync 的下線殺手與三個 deliver、choose 最後那一下殺手檢查照舊留在 Game 原位
（位置算行為，批次表第二節）；這一包接 tavern:* 的 choose（互斥前綴）與假人分數。
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome


class TavernFeature(Feature):
    name = "tavern"
    prefix = "tavern"  # tavern:news、tavern:treat、tavern:hide、tavern:trace、tavern:board、tavern:back；入口 act:tavern 是核心的前綴
    bot_always = ("tavern:",)  # 坐在酒肆裡一直按得下去：整季機器人不按（bot.py 的排除清單原本就有這一個，重複無害，第 11 批收）
    # 酒肆開著沒、酒家最近幾則回話、聽過的傳聞、查到過的名號、哪一天請過酒、收到的風聲、藏行跡到幾時、託酒家留意的人、
    # 保鏢跟到幾時、剛被殺手得手的護身：換季全部跟著新角色重來（季上的牆、風聲、請酒、殺手單、閒談照季存）
    player_fields = ("picking_tavern", "tavern_notes", "tavern_heard", "tavern_known", "tavern_treat_day", "whispers", "hidden_until",
                     "tavern_watches", "tavern_guard_until", "tavern_shield_until")
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        """酒肆開著（Config.tavern.enabled、內容有帶「酒肆」標籤的地點），或此刻還坐在酒肆裡：開關在坐著的時候被關掉（沒經過 sync
        收店）照樣按得到「出酒肆」、假人照樣只按它——搬包之前 choose 的 tavern 那一支、bot_policy.score 的那一段都不看開關。"""
        from . import rules  # noqa: PLC0415

        return rules.on(ctx.content) or ctx.state.player.picking_tavern

    def choose(self, ctx, kind, arg):
        """tavern:* 那幾顆（選單接管那一格給的，只在坐在酒肆裡時有）：標題照招牌與動作（原 Game._action_title 的 tavern 那一支），
        動作照原 Game._tavern_choice（出酒肆、看牆上的懸賞榜、其餘照店面那一頁的動作）。"""
        if kind != self.prefix:
            return None
        from . import actions, rules  # noqa: PLC0415

        return Outcome(title=rules.title_of(ctx.state, ctx.content, arg), run=lambda: actions.tavern_choice(ctx, arg))

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(option)


FEATURE = TavernFeature()
