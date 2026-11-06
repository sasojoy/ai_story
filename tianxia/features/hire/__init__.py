"""招募同伴（功能包；開發規範手冊 3.2）：五項屬性的季，在城裡的酒肆花銀兩招一般 NPC 同伴（屬性與跨季架構 v2 第九節；
企劃者 2026-11-04 照建議：五型在酒肆花銀兩招、名字隨機）。README.md 寫這一包做什麼、導覽與設計稿。

- actions.py：「此地還能做」裡每一型一顆（此地酒肆還沒有主的第一位）、按下去付錢入隊
- 人在 content/hire.json（scripts/make_hirelings.py 照 Config.hire 生；載進人物表、標 hire_type／hire_at）
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome

BOT_SCORE = 6.0  # 假人：銀兩夠、名下沒滿，路過酒肆偶爾招一位（低過軍令與懸賞）


class HireFeature(Feature):
    name = "hire"
    prefix = "hire"  # hire:<人物 id>
    content = ("hire.json",)  # content.py 照舊讀進人物表
    player_fields: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        from . import actions  # noqa: PLC0415

        return actions.on(ctx)

    def options(self, ctx):
        from . import actions  # noqa: PLC0415

        return actions.options(ctx)

    def choose(self, ctx, kind, arg):
        if kind != self.prefix:
            return None
        from . import actions  # noqa: PLC0415

        return Outcome(title=actions.TITLE, run=lambda: actions.act(ctx, arg))

    def status(self, ctx):
        """坐在酒肆裡時，此地能招的那幾位（介面重整 2026-11-05：網頁把招募畫在酒肆的聽消息那一頁；坐進酒肆後選單只剩酒肆那幾顆，
        按下去時網頁先出酒肆再按 hire:<id>）。沒坐在酒肆裡不給這個鍵。"""
        if not ctx.state.player.picking_tavern:
            return {}
        from . import actions  # noqa: PLC0415

        hires = [{"id": o.id, "label": o.label, "enabled": o.enabled} for o in actions.options(ctx)]
        return {"hires": hires} if hires else {}

    def bot_pick(self, ctx, option):
        return BOT_SCORE if option.enabled else None


FEATURE = HireFeature()
