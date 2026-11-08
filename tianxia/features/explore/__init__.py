"""探索（減法季的「探索」那一格：探索一顆〔出門一趟只碰上一件事〕與走一趟〔一次走一、三、五段〕；功能包，開發規範手冊 3.2；
主動搬六包第 3＋4 批搬進來）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫、名字陷阱。

- checks.py：內容驗證（探索表、段落句子；原本是核心 content.py 的 check_explore_one、check_outing_lines）
- explore_rules.py：探索一顆的純規則（原 tianxia/explore_one.py）
- explore_actions.py：原本 Game 上探索一顆的 15 個方法與 OutingPlan（Game 留 9 個一行委派）——名字帶 outing 的那幾個是探索一顆的
- outing_rules.py：走一趟的純規則（原 tianxia/outing.py）
- outing_actions.py：原本 Game 上走一趟的 12 個方法（Game 留 9 個一行委派）
- explore_base.py：原本 Game 上舊探索的底 8 個方法（_explore、_explore_outcome 含序章草廬四景、_explore_weights、_explore_can、_wild_foes、
  _here_squads、撿破境丹 _legend_find、練功分級 _practice_tier；Game 留 6 個一行委派，全部拆包第 18 批）

這一批不拿選項前綴（prefix 是 None）：那一格的 id 照留核心的 act:explore（IDLE_MARK；跟扣體力、晉升奇遇、序章的舊探索、
探索三選一纏在一起），分派留在 Game._act；走一趟沒有自己的選項，走 /api/do/outing。所以這一包只接 enabled、欄位、內容驗證與網頁檔，
假人：act:explore 的分數在 bots.py（第 60 批，Verb.bot 問），挑幾段、走完那一句照舊在 bot.py。
"""
from __future__ import annotations

from tianxia.core.features import Feature, HowtoHook, StatusHook, Verb, WorldHook


class ExploreFeature(Feature):
    name = "explore"
    prefix: str | None = None  # act:explore 是核心的 act 前綴；走一趟沒有選項（/api/do/outing、outing_say、outing_tale、outing_erase）
    web = ("outing.js", "explore.js", "explore.css")  # 走一趟的畫面 outing.js（本來就是獨立的檔）；找素材的分支輪 explore.js 與樣子 explore.css（全部拆包第 67 批從 main.js、style.css 切出來）
    content = (  # content.py 照它到這一包的 content/ 載；檔名照舊（批次表第二節）
        "outing_lines.json",  # 出門一趟回來那一段的句子
        # 探索補寫的事件池（全部拆包第 63 批）
        "events/explore_jizhou.json", "events/explore_luoyang.json", "events/explore_nanyang.json",
        "events/explore_runan.json", "events/explore_yingchuan.json", "events/explore_youzhou.json",
    )
    # 走一趟這一趟（outing）、探索一顆上一趟要選的那件事（outing_last）、第幾次探索（explore_seq）、
    # 遭遇的疲勞那一天與場數（fight_day、fights_today：三道閘的前一道）；換季全部跟著新角色重來
    player_fields = ("outing", "outing_last", "explore_seq", "fight_day", "fights_today")
    carried: tuple[str, ...] = ()

    def scratch(self) -> dict:
        """寄放在 Game 上的旗標（第二輪第 92 批；原本在 Game.__init__：核心建 Game 時照 registry.DECLARED 擺上去〔features.scratch_init〕，不進存檔）。每次回新的：_outing_close 兩份 Game 不能共用。"""
        return {
            "_outing_busy": False,  # 走一趟正在走（outing_actions.outing_walk）或正在記一件事選完的得失（_outing_watched）：不再套一層
            "_loot_scale": 1.0,  # 打贏的心得與銀兩倍數：探索包遭遇那一場（城裡的地痞 town_loot_scale）才不是 1
            # 減法季探索一顆（批 2）：遭遇拍那一場掉的素材打幾成（城裡的地痞 town_loot_scale、三道閘的倍數）；其餘的仗都是 1，一個字不變
            "_drop_scale": 1.0,
            "_gate_scale": 1.0,  # 減法季三道閘（批 2）：遭遇拍那一場的經驗、心得、銀兩乘疲勞與對手兩道閘（explore_actions.fight_gate）；其餘是 1
            "_outing_close": set(),  # 這一趟出門打了折的那幾道閘（explore_actions.fight_gate 記、explore_one 寫段落結尾那一句）
            "_beat": None,  # 走一趟：剛剛那一次探索抽到什麼（explore_actions.explore_one 寫、outing_actions.outing_walk 讀）
            "_outing_upset": False,  # 走一趟這一場遭遇開打前勝算凶險以下（_outing_fight 寫、探索包的 explore_one 讀）
        }

    def enabled(self, ctx) -> bool:
        """減法季探索一顆開著（Config.jianfa 的 explore_one＋開季的章，rules.jianfa；走一趟另要 outing 子開關）。不擲骰、不碰存檔。
        這一包沒有遊戲當下的掛鉤（選項、選單、狀態……），開關只決定那幾個叫不叫；動作本身各自先問一次開關（搬包之前就是這樣）。"""
        from tianxia.rules import jianfa  # noqa: PLC0415

        return jianfa(ctx.content, ctx.state.world, "explore_one")

    def check_content(self, content, need) -> None:
        """探索表（每個地點歸得到一張、城裡的地痞、旅人事件）與段落句子（content/outing_lines.json）：原本是 content.check_explore_one、
        check_outing_lines（核心不 import 包，搬進來）。開關關著也照驗（兩個驗證自己看 Config.jianfa）。"""
        from . import checks  # noqa: PLC0415

        checks.check_explore_one(content, need)
        checks.check_outing_lines(content, need)

    _verbs: tuple[Verb, ...] | None = None

    def verbs(self) -> tuple[Verb, ...]:
        """act:explore 那一格的主人（act 子動詞，全部拆包第 11 批；原本 Game 上四處叫 _outing_on 的那幾行，判斷照抄）：探索一顆開著
        （outing_on：減法季 explore_one、不在序章裡）時，按下去是出門一趟（_act 最前面）、紀錄標題「出門一趟・某地」、行動列只剩那一顆
        「探索」、底下那一行寫這一處多半給什麼；關著時按下去、標題、那一格回 None，核心照舊（舊探索、序章寫好的那幾步），底下那一行回舊探索那一行（outing_note，第 59 批併進來，核心不再寫）。建一次就留著，
        每一格在叫的那一下才照模組屬性找 explore_actions 的函式（monkeypatch 照樣有效；tests/core/test_contract_features.py 守）。"""
        if self._verbs is None:
            from tianxia import journal  # noqa: PLC0415

            from . import bots, explore_actions  # noqa: PLC0415

            def on(ctx):
                return explore_actions.outing_on(ctx)

            def title(ctx):
                return f"{journal.OUTING}・{ctx.content.locations[ctx.state.player.location].name}" if on(ctx) else None

            self._verbs = (Verb(
                "explore",
                run=lambda ctx, prepared: explore_actions.explore_one(ctx) if on(ctx) else None,
                title=title,
                cell=lambda ctx, loc, cost, odds: [explore_actions.outing_option(ctx, loc)] if on(ctx) else None,
                note=lambda ctx, loc: explore_actions.outing_note(ctx, loc),
                bot=lambda ctx, profile: bots.score(ctx),
            ),)
        return self._verbs

    # core_world（全部拆包第 25 批「世界層掛鉤」）
    _world: tuple[WorldHook, ...] | None = None

    def world(self) -> tuple[WorldHook, ...]:
        """世界層 next 的 inscriptions 那一格（題壁照帶；原本寫在 sqlite_world.next_season 的兩行）：不問 enabled（原位不看開關：
        花錢題的字關著也照帶）。建一次就留著，在叫的那一下才照模組屬性找 outing_rules.world_next（monkeypatch 照樣有效）。"""
        if self._world is None:
            from . import outing_rules  # noqa: PLC0415

            self._world = (WorldHook("next", "inscriptions", lambda *args: outing_rules.world_next(*args)),)
        return self._world

    # howto（全部拆包第 59 批「引導二」）
    def howto(self) -> tuple[HowtoHook, ...]:
        """玩法說明的explore 那一格：順序在核心 HOWTO_ORDER，不問 enabled；在叫的那一下才照模組屬性找。"""
        from . import howto as words  # noqa: PLC0415

        return (HowtoHook("explore", lambda content, season, page: words.explore_section(content, season)),)

    # shell_web（全部拆包第 66 批：狀態列與江湖畫面的格，先後在 STATUS_ORDER；不問 enabled，原位那幾行本來就不看包的開關）
    _status_slots: tuple[StatusHook, ...] | None = None

    def status_slots(self) -> tuple[StatusHook, ...]:
        """建一次就留著，在叫的那一下才照模組屬性找（monkeypatch 照樣有效）；frame 見 core/features.py 的 StatusHook。"""
        if self._status_slots is None:
            from . import explore_actions, outing_actions  # noqa: PLC0415

            self._status_slots = (
                # 走一趟：探索鈕的段數選單（picker）與這一趟（trip）；關著是 None、網頁照舊一顆探索
                StatusHook("main", "outing", lambda ctx, frame: {"outing": outing_actions.outing_view(ctx)}),
                # 四格探索那一格的小字「城裡多事」（整合設計 6.3，批 5）；在路上沒有這個鍵。減法季探索一顆開著時照出門一趟那一張表（批 2）
                StatusHook("main", "mostly", lambda ctx, frame: {"mostly": mostly} if (mostly := explore_actions.mostly_here(ctx)) else {}),
            )
        return self._status_slots

    def main_actions(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼建動作表時才 import（同 routes 掛鉤）

        return routes.main_actions(shell)

    def admin_tools(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼建動作表時才 import（同 routes 掛鉤）

        return routes.admin_tools(shell)

    def outlock(self, shell):
        from . import routes  # noqa: PLC0415  只在殼建鎖外工作時才 import（同 routes 掛鉤）

        return routes.outlock(shell)


FEATURE = ExploreFeature()
