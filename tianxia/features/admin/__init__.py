"""管理者包（第二輪第 90 批）：管理頁（/admin）與它的資料（/api/admin*）、重設密碼、季與時刻表的工具。
本包的細節與還留在殼、留在 Game 的接縫看 README.md；計畫 docs/superpowers/plans/2026-11-07-第二輪-第90批.md。

- actions.py：開季、收季、開下一季、暫停與繼續、觸發大事、推動大勢、排時間、跳到下一件、定戰況、定結果、清鎖定（Game 上原本的 17 個方法）。
- game_api.py：Game 上掛的名字。
- routes.py：/admin、/api/admin、/api/admin/player、/api/admin/accounts、/api/admin/reset_password，管理頁的選單 admin_choices（鍵的先後在 STATUS_ORDER["admin"]），13 個管理者工具。

沒有選項前綴、沒有 PlayerState 欄位、沒有內容檔、沒有開關。假人不碰管理者。
不在最上層 import actions 與 routes：FEATURES 登記不拖進 fastapi；Game 上的表由 game_api.py 接。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class AdminFeature(Feature):
    name = "admin"
    prefix = None  # 沒有選項：全是管理頁與 /api/do 的工具
    web = ("admin.js",)  # 管理頁的畫法與表單；它在 WEB_ORDER 裡（state.js 不能排在它前面），script 的先後不變
    content: tuple[str, ...] = ()
    player_fields: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return True  # 沒有開關；管理者認的是 Game.is_admin

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只有殼掛路由時才 import（routes 要 fastapi）

        return routes.router(shell)

    def admin_tools(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼建動作表時才 import（同 routes 掛鉤）

        return routes.admin_tools(shell)


FEATURE = AdminFeature()
