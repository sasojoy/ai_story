"""玩家互動一（此地還有、玩家卡、邀請框、打招呼、贈物、名帖）。功能包，開發規範手冊 3.2；全部拆包第 37 批搬進來
（計畫 docs/superpowers/plans/2026-11-06-玩家互動包-第1批.md）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- social.py：玩家卡與卡上動作的登記表（ACTIONS、CardAction、CardButton）、贈物、打招呼（原 tianxia/social.py；那個名字留成指到這裡的別名）。
  「此地還有」的判斷與狀態列的身分字不在這裡：核心的查詢服務 tianxia/core/presence.py（social 從那裡 re-export 同一批函式物件）
- invites.py：邀請的帳（原 tianxia/invites.py，別名）；mingtie.py：名帖的規則（原 tianxia/mingtie.py，別名）；
  mingtie_card.py：遞名帖掛上玩家卡（原 tianxia/mingtie_card.py，別名；載入這一包時登記進 social.ACTIONS）
- actions.py：此地還有、玩家卡、卡上的鈕按下去；invite_actions.py：邀請框（invite: 前綴、choose 掛鉤）；pair_actions.py：同一對人的帳與贈物一天的次數；
  mingtie_actions.py：名帖的動作與管理者看檢舉、撤下、放回——原本是 Game 上的 31 個方法（Game 留一行委派）
- routes.py：/api/peer、/api/peer/act、/api/mingtie、/api/mingtie/{op}；bots.py：假人收到打招呼、結伴邀請、名帖的回法與做名帖、遞名帖

邀請框是一個前綴三種意思：invite:yes|no|cancel:<編號> 是打招呼（挑釁）、名帖、切磋、論武、結伴同行共用的選項。這一包拿前綴與 choose，
答應時照邀請的種類分派；切磋 Game._spar、論武 Game._discuss（第 38 批）、結伴同行（移動包 party.join，Game._join 留一行委派）經 ctx 叫。
enabled 一直是 True（沒有整包的總開關：名帖開關 Config.mingtie.enabled 只管名帖那幾顆）。選單上怎麼排（Game._everyday_options 的 _invite_options）
位置固定，留原位叫委派。
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome

from . import mingtie_card as _mingtie_card  # noqa: F401  遞名帖登記進玩家卡的動作表（social.ACTIONS）；載入這一包就登記（原本 engine.py 頂端 import 它；scripts/test_for.py 認這個寫法）


class PeersFeature(Feature):
    name = "peers"
    prefix = "invite"  # invite:yes|no|cancel:<編號>：打招呼的回禮（invite:cold|retort|…）也是同一個前綴
    web = ()  # app.js 的 MT_INKS 等歸這一包，網頁第 3 階才切
    content = ("mingtie.json",)  # 名帖現成的畫與假人的自題句庫；content.py 照舊讀（MingtieContent）
    bot_always = ("invite:",)  # 邀請的選項一直按得下去（收回、回禮）：整季機器人不按（bot.py 的排除清單原本也寫了一個，拿掉那一個，只剩這裡）
    # 名帖與贈物一天的次數：自己那一張、收到的、檢舉過的、不接誰的挑釁話、定稿與遞帖的次數記在哪一天、贈物的次數——全部跨季帶走
    # （Game._reset_player_for_new_season 照抄；title_book 也是名帖的，但換季時要加上這一季掙到的頭銜，由 on_season_start 接，不算原樣帶走）
    player_fields = ("mingtie", "mingtie_box", "mingtie_day", "mingtie_made", "mingtie_sent", "mingtie_hidden", "taunt_muted", "gift_day", "gifts_today")
    carried = player_fields

    def enabled(self, ctx) -> bool:
        return True

    def choose(self, ctx, kind, arg):
        """invite:yes|no|cancel:<編號>（原 Game.choose 的 invite 那一支、_action_title 的 invite 那一格）：標題在動作之前先拿。"""
        if kind != "invite":
            return None
        from . import invite_actions  # noqa: PLC0415

        return Outcome(title=invite_actions.title(ctx, arg), run=lambda: invite_actions.invite(ctx, arg))

    def on_season_start(self, ctx, old) -> None:
        """換季：這一季值得留名的頭銜寫進 title_book（「第N季 天下第一」；原本在 Game._reset_player_for_new_season 的名帖那一段）。
        算的是上一季那一份（old），不看新的存檔，所以挪到新存檔接上之後做結果一樣。"""
        from . import mingtie  # noqa: PLC0415

        p = ctx.state.player
        book_titles = mingtie.season_book(old, ctx.content, old.player.season_number)
        p.title_book = old.player.title_book + [t for t in book_titles if t not in old.player.title_book]

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)


FEATURE = PeersFeature()
