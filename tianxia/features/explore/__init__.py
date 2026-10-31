"""探索（減法季的「探索」那一格：探索一顆〔出門一趟只碰上一件事〕與走一趟〔一次走一、三、五段〕；功能包，開發規範手冊 3.2；
主動搬六包第 3＋4 批搬進來）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫、名字陷阱。

- checks.py：內容驗證（探索表、段落句子；原本是核心 content.py 的 check_explore_one、check_outing_lines）
- outing_rules.py：走一趟的純規則（原 tianxia/outing.py；那個名字留成指到這裡的別名）
- outing_actions.py：原本 Game 上走一趟的 12 個方法（Game 留 9 個一行委派）

這一批不拿選項前綴（prefix 是 None）：那一格的 id 照留核心的 act:explore（IDLE_MARK；跟扣體力、晉升奇遇、序章的舊探索、
探索三選一纏在一起），分派留在 Game._act；走一趟沒有自己的選項，走 /api/do/outing。所以這一包只接 enabled、欄位、內容驗證與網頁檔，
假人照舊走 bot_policy、bot.py。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class ExploreFeature(Feature):
    name = "explore"
    prefix: str | None = None  # act:explore 是核心的 act 前綴；走一趟沒有選項（/api/do/outing、outing_say、outing_tale、outing_erase）
    web = ("outing.js",)  # 走一趟的畫面（本來就是獨立的檔；這一輪不切網頁，位置不動、index.html 照舊手寫）
    content = ("outing_lines.json",)  # 出門一趟回來那一段的句子（content.py 照舊讀；檔名照舊，批次表第二節）
    # 走一趟這一趟（outing）、探索一顆上一趟要選的那件事（outing_last）、第幾次探索（explore_seq：跟還留在 engine 的探索三選一共用）、
    # 遭遇的疲勞那一天與場數（fight_day、fights_today：三道閘的前一道）；換季全部跟著新角色重來
    player_fields = ("outing", "outing_last", "explore_seq", "fight_day", "fights_today")
    carried: tuple[str, ...] = ()

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


FEATURE = ExploreFeature()
