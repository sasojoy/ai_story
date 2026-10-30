"""商城（萬寶閣）：元寶錢包的賣與記帳、月卡、易名帖、管理者工具（功能包；開發規範手冊 3.2、3.10）。README.md 寫這一包做什麼、導覽與設計稿。

- rules.py：純規則（原 tianxia/mall.py；那個名字留成指到這裡的別名）；rename.py：易名帖換名號的規矩
- actions.py：原本 Game 上的 mall_*（Game 留一行委派）；routes.py：/api/mall/…（殼照 FEATURES 掛）
- 錢包（tianxia/wallet.py）與票的庫存、消耗（ctx.wallet）是核心的服務：別的功能用票叫核心，不叫這一包
"""
from __future__ import annotations

from tianxia.core.features import Feature


class MallFeature(Feature):
    name = "mall"
    prefix = None  # 商城的動作全走 /api/mall/…，選單上沒有 mall: 的選項；假人從不買
    web = ("mall.js", "mall.css")
    content = ("mall.json",)
    # 萬寶閣賣的、記在角色身上的：功法庫擴充只這一季；重悟帖、破境丹換季帶著走（核心的換季照抄；破境丹打點也賣）
    player_fields = ("holding_bonus", "create_rerolls", "legend_items")
    carried = ("create_rerolls", "legend_items")

    def enabled(self, ctx) -> bool:
        return ctx.content.config.mall.enabled

    def status(self, ctx) -> dict:
        from . import actions  # noqa: PLC0415

        entry = actions.entry(ctx)  # 齒輪旁的錠子鈕＋餘額、底部第六格、月卡今日份、易名帖（main.mall）
        return {"mall": entry} if entry is not None else {}

    def admin_tools(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.admin_tools(shell)

    def routes(self, shell):
        from . import routes  # noqa: PLC0415

        return routes.router(shell)

    def check_content(self, content, need) -> None:
        """商城的商品（content/mall.json，商城架構設計 4.3）：每一件照 rules.item_problems（效果在允許的效果表裡、種類對得上、數量、
        名字過命名過濾、上架日期與季的格式）；商品之間不同名。開關關著也照驗（檔案寫壞了早點知道）。原本是 content.check_mall。"""
        from . import rules  # noqa: PLC0415

        for item in content.mall.values():
            for problem in rules.item_problems(item, content):
                need(False, problem)
        seen: dict[str, str] = {}
        for item in content.mall.values():
            if item.name in seen:
                need(False, f"商城 {item.id}：跟 {seen[item.name]} 同名「{item.name}」")
            seen.setdefault(item.name, item.id)


FEATURE = MallFeature()
