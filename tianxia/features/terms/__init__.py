"""條款（功能包；開發規範手冊 3.2）：使用條款與隱私權條款兩頁、登入後按同意、改版時重新同意。這一包做什麼、設計稿是哪一份：README.md。

沒有選項、沒有 PlayerState 欄位：同意紀錄認帳號，記在 <db>-terms.sqlite 小檔（store.py），不進遊戲資料庫。只接 routes、check_content 兩個掛鉤。
內容檔 content/terms.json 由這一包自己讀（rules.load），content.py 不讀它。不在最上層 import routes：FEATURES 登記不拖進 fastapi。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class TermsFeature(Feature):
    name = "terms"
    prefix = None  # 沒有選項：條款是登入頁、設定頁與同意那一層的事
    web: tuple[str, ...] = ("terms.js", "terms.css")  # 同意那一層、登入頁與設定頁底下的兩個連結
    content: tuple[str, ...] = ("terms.json",)
    player_fields: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return ctx.content.config.terms.enabled  # 數字在 tianxia/core/tuning/terms.py（Config.terms）

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只有殼掛路由時才 import（routes 要 fastapi）

        return routes.router(shell)

    def check_content(self, content, need) -> None:
        from . import rules  # noqa: PLC0415

        for problem in rules.check(rules.load()):
            need(False, problem)


FEATURE = TermsFeature()
