"""商城（萬寶閣）：元寶錢包的賣與記帳、月卡、易名帖、管理者工具（功能包；開發規範手冊 3.2、3.10）。README.md 寫這一包做什麼、導覽與設計稿。

- rules.py：純規則（原 tianxia/mall.py）；rename.py：易名帖換名號的規矩
- actions.py：原本 Game 上的 mall_*（全部拆包第 58 批起 Game 不留委派）；routes.py：/api/mall/…（殼照 FEATURES 掛）
- 錢包（tianxia/wallet.py）與票的庫存、消耗（ctx.wallet）是核心的服務：別的功能用票叫核心，不叫這一包
"""
from __future__ import annotations

from tianxia.core.features import Feature, HowtoHook, SeamHook


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

    def on_own_turn(self, ctx) -> None:
        """本人這一輪（接縫掛鉤，全部拆包第 11 批；原本 Game.own_turn_checks 最前面叫 Game._mall_grant 的那一行）：封測元寶——錢包第一次
        進來的那一下發，真人假人一樣；暫停中照發（帳跟世界無關）。不問 enabled：原位本來就不看，商城關著時錢包是 None、什麼都不做。"""
        from . import actions  # noqa: PLC0415

        actions.grant(ctx)

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

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """season.carry 的 mall 那一格（順序在 SEAM_ORDER；不看開關：on_season_start 只問開著的包，花元寶買的不能換季就不見）。"""
        if self._seams is None:
            self._seams = (SeamHook("season.carry", "mall", _carry_season),)
        return self._seams

    # howto（全部拆包第 59 批「引導二」）
    def howto(self) -> tuple[HowtoHook, ...]:
        """玩法說明的mall 那一格：順序在核心 HOWTO_ORDER，不問 enabled；在叫的那一下才照模組屬性找。"""
        from . import howto as words  # noqa: PLC0415

        return (HowtoHook("mall", lambda content, season, page: words.mall_section(content)),)


def _carry_season(ctx, old, fresh) -> None:
    # 破境丹、重悟帖萬寶閣賣（花元寶買的不能換季就不見），同回體丹剩下的帶著走（Joy 2026-10-21「再研究一下有沒有什麼瑕疵」）
    fresh.player.legend_items = old.player.legend_items
    fresh.player.create_rerolls = old.player.create_rerolls


FEATURE = MallFeature()
