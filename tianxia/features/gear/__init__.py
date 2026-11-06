"""裝備（修練頁的換上、拆解〔含批量〕、餵馬，馬市的買餵換上，寄放補送，名將贈禮，名將本命兵器，神器譜）。功能包，開發規範手冊 3.2；
全部拆包第 42 批搬進來（引擎那一半；網頁那一半 web/ 第 3 階才切）。包名 gear 跟測試資料夾 tests/gear/、內容欄位 Content.gear（content/gear.json 讀進來的
GearBook）同字，不是同一件事：這裡是功能包，另兩個是舊的名字。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- signature_arms.py：名將本命兵器的規則（原 tianxia/signature_arms.py；那個名字留成指到這裡的別名）
- market_actions.py：馬市的第二層選單、選單上的選擇、進門（原本 Game 上的 2 個方法與 _act 的 act:market 三行）
- bench_actions.py：修練頁的換上、餵馬、拆解、批量拆解（4 個）
- gift_actions.py：寄放補送、名將贈禮、此刻在身邊的人物、贈禮另起的紀錄、本命兵器（5 個）
- views.py：修練頁裝備那一塊、見聞榜單的神器譜（2 個）
- bots.py：假人的分數（原本 bot_policy.score 的 market 那兩行）

接縫掛鉤：choose（market:*）、verbs（act:market 進門與紀錄標題）、content、bot_pick。沒有 APIRouter（/api/menxia 的四個動作在 routes.py 的 menxia_actions，全部拆包第 68 批；/api/boards、/api/board_card 留在殼，叫 Game 的委派）。
店面登記（Shop）這一批不登記（計畫 1.9，同鐵匠鋪：入口順序 懸賞榜 → 鐵匠鋪 → 馬市、選單與收店都留在 Game 原位，第 45 批三間一起排）。
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome, Verb


class GearFeature(Feature):
    name = "gear"
    prefix = "market"  # market:buy、market:feed、market:wield:<id>、market:back；入口 act:market 是核心的前綴
    content = ("gear.json",)  # content.py 照舊讀（check_gear、check_signature_arms 留在 content.py，不接 check_content）
    player_fields = ("picking_market",)  # 馬市第二層選單開著沒：換季跟著新角色重來。held_gear 核心與共用層也讀、figure_wins 是大勢人物包的，不認領
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        """兵器、防具、坐騎、寶物四欄各看自己的 enabled（不看第一季開關；裝備四欄設計 2.6），或此刻還坐在馬市裡：開關在坐著的時候被關掉（沒經過 sync 收店）
        照樣按得到離開、假人照樣只按它——搬包之前 choose 的 market 那一支、bot_policy.score 的那一段都不看開關。"""
        c = ctx.content.config
        return c.weapons.enabled or c.armor.enabled or c.mounts.enabled or c.treasures.enabled or ctx.state.player.picking_market

    def choose(self, ctx, kind, arg):
        """market:*（馬市第二層選單上的每一顆）：標題「馬市」（原 Game._action_title 的 market 那一支），動作照原 Game._market。
        FB-195（選單上沒有或灰掉的 market: 回為什麼不成）仍在 Game.choose 原位，在這個掛鉤之前。"""
        if kind != self.prefix:
            return None
        from tianxia import mounts  # noqa: PLC0415

        from . import market_actions  # noqa: PLC0415

        return Outcome(title=mounts.MARKET, run=lambda: market_actions.market(ctx, arg))

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(ctx, option)

    # ── 接縫掛鉤（全部拆包第 11 批；不問 enabled，原位本來就不看開關）──

    _verbs: tuple[Verb, ...] | None = None

    def verbs(self) -> tuple[Verb, ...]:
        """act:market 的主人（act 子動詞）：按下去走進馬市（market_actions.enter：不花體力、馬販那一句；原本 Game._act 中段那幾行）、
        紀錄標題「馬市・此地」（原本 Game._action_title 那張表的 market）。進店那一顆（此地還能做）在 Game._everyday_options 原位（計畫 1.9）。"""
        if self._verbs is None:
            from tianxia import mounts  # noqa: PLC0415

            from . import market_actions  # noqa: PLC0415

            self._verbs = (Verb("market", run=lambda ctx, prepared: market_actions.enter(ctx),
                                title=lambda ctx: f"{mounts.MARKET}・{ctx.content.locations[ctx.state.player.location].name}"),)
        return self._verbs

    def menxia_actions(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼建動作表時才 import（同 routes 掛鉤）

        return routes.menxia_actions(shell)


FEATURE = GearFeature()
