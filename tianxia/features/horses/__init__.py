"""馬的來路（功能包；開發規範手冊 3.2）。這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

Joy 2026-11-10 在選擇卡上選「奪馬＋馴野馬＋論功賜馬」：打贏騎馬的那幾路奪馬（事件 win）、北方野馬群連三步馴馬（horses:tame）、
決戰得勝論功前三賜馬（事件 showdown_pay）。開關 Config.horses.enabled，預設關。規則在 actions.py，字在 rules.py。
"""
from __future__ import annotations

from tianxia.core.features import BusHook, Feature, Outcome


class HorsesFeature(Feature):
    name = "horses"
    prefix = "horses"  # 選項 id 的前綴：horses:…（核心只把這個前綴的 id 交給這一包）
    web: tuple[str, ...] = ()
    content: tuple[str, ...] = ()
    player_fields: tuple[str, ...] = ("horses_seized", "horses_tamed", "horses_tame", "horses_tame_at")  # 換季跟著新角色歸零
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return ctx.content.config.horses.enabled  # 預設關：讀 Config.horses.enabled；數字在 tianxia/core/tuning/horses.py

    def options(self, ctx):
        from . import actions  # noqa: PLC0415

        return actions.options(ctx)

    def choose(self, ctx, kind, arg):
        if kind != self.prefix:
            return None
        from . import actions, rules  # noqa: PLC0415

        return Outcome(title=rules.TITLE, run=lambda: actions.choose(ctx, arg))

    def bus(self) -> tuple[BusHook, ...]:
        """奪馬（win）、論功賜馬（showdown_pay）。在叫的那一下才照模組屬性找 actions 的函式。"""
        from . import actions  # noqa: PLC0415

        return (
            BusHook("win", "horses", lambda ctx, loc_id, squad_id: actions.win(ctx, loc_id, squad_id)),
            BusHook("showdown_pay", "horses", lambda ctx, battle, me, lines: actions.showdown_pay(ctx, battle, me, lines)),
        )

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(ctx, option)

    def check_content(self, content, need) -> None:
        cfg = content.config.horses
        if not cfg.enabled:  # 名單是正式內容的隊伍與地點，測試內容沒有：開著才驗
            return
        for squad_id in cfg.seize_squads:
            need(squad_id in content.squads, f"Config.horses.seize_squads：沒有 {squad_id} 這一路")
        for loc_id in cfg.pastures:
            need(loc_id in content.locations, f"Config.horses.pastures：沒有 {loc_id} 這個地點")


FEATURE = HorsesFeature()
