"""擂台形象（功能包；開發規範手冊 3.2）。這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

- rules.py：純規則（買到哪幾套、穿哪一套、假人挑哪一套）；actions.py：Game 叫的（擂台記形象、萬寶閣換裝）；routes.py：/api/looks/…
- 賣是商城包的事（商品 kind look、效果 look，購買那一列記 look_id）；兩包共用的「買到哪幾套」在核心 core.services.look_ids
"""
from __future__ import annotations

from tianxia.core.features import Feature


class LooksFeature(Feature):
    name = "looks"
    prefix = None  # 換裝走 /api/looks/…，選單上沒有 looks: 的選項；假人不換
    content = ("looks.json",)
    player_fields: tuple[str, ...] = ()  # 穿哪一套記在錢包那一側（mall_entitlements），帳號的、換季照帶，不在角色上
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        from . import rules  # noqa: PLC0415

        return rules.on(ctx.content)

    def status(self, ctx) -> dict:
        """管理者的設定頁多一組「自建形象」（main.looks_admin）：賣自建形象、而且是管理者才有。
        另外送 main.looks_ver：自建的圖（looks/ 底下）此刻的版本，網頁把它接在圖的網址後面當 ?v=，
        圖一換網址就換、手機不必清快取（同 server.versioned_page 對自家檔案那一套）。"""
        from . import actions, orders  # noqa: PLC0415

        out: dict = {"looks_ver": actions.images_version()}
        if ctx.is_admin() and orders.item_of(ctx.content) is not None:
            out["looks_admin"] = True
        return out

    def admin_tools(self, shell) -> dict:
        from . import routes  # noqa: PLC0415

        return routes.admin_tools(shell)

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)

    def check_content(self, content, need) -> None:
        from . import rules  # noqa: PLC0415
        from tianxia import naming  # noqa: PLC0415

        for problem in rules.problems(content):
            need(False, problem)
        for look in content.looks.values():
            problem = naming.name_problem(look.name, content)
            need(problem is None, f"形象 {look.id}：名字「{look.name}」{problem}")


FEATURE = LooksFeature()
