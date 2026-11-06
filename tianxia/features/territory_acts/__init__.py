"""地盤的行動與畫面（功能包；開發規範手冊 3.2）：戰書與攻城時段、22:00 換天、〈天下形勢〉三段式的 A、C 兩段、地盤畫面的資料、分紅與守城功補送、管理者五個救場工具。
全部拆包第 46 批搬進來（計畫 docs/superpowers/plans/2026-11-06-地盤包-第1批.md）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

包名叫 territory_acts、不叫 territory：tianxia/territory.py（誰控制、駐軍、大本營）是共用規則層，這一批不搬，同名不准。

- letter_actions.py：下戰書；day_actions.py：22:00 換天的掛鉤、分紅與守城功送到；xingshi_actions.py：〈天下形勢〉開單到收下；
  view.py：地盤畫面的資料與管理者頁的下拉選單；admin_actions.py：四個救場工具
- conquest_day.py、xingshi.py：原本的 tianxia/conquest_day.py、tianxia/xingshi.py（舊名留成別名）；void、note_void、today 先搬進共用規則層 conquest
- routes.py：/api/xingshi 與管理者五個工具（conquest_set、conquest_progress、admin_conquest_letter、conquest_cancel、xingshi_now）

沒有選項前綴（戰書走 /api/do/conquest_letter，不在選單上；假人不下戰書）。enabled 一直是 True（戰書看 conquest.on、〈天下形勢〉看 xingshi.on，各在動作裡驗）。
22:00 換天沒有掛鉤可接（Game.sync、world_tick、advance 三處把它排在別的結算之間，順序就是行為），所以 conquest_tick、deliver_conquest 在 Game 上留委派。
"""
from __future__ import annotations

from tianxia.core.features import Feature, SeamHook


class TerritoryActsFeature(Feature):
    name = "territory_acts"
    prefix = None  # 地盤的動作走 /api/do/conquest_letter 與管理者工具，選單上沒有這一包的選項
    # 沒有 PlayerState 欄位：WorldState.conquest、xingshi、xingshi_ticket、xingshi_mark 是全服的帳，留在 state.py
    player_fields: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()
    content = ("xingshi_lines.json",)  # 〈天下形勢〉的句型；content.py 照舊讀，驗證在下面的 check_content

    def enabled(self, ctx) -> bool:
        return True

    def admin_tools(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.admin_tools(shell)

    def routes(self, shell):
        from . import routes  # noqa: PLC0415

        return routes.router(shell)

    def check_content(self, content, need) -> None:
        """〈天下形勢〉的句型（content/xingshi_lines.json）：寫了這個檔每一組都要齊、每一句填得進去、不能有阿拉伯數字。開關關著也照驗。原本是 content.check_xingshi_lines。"""
        from . import xingshi  # noqa: PLC0415

        xingshi.check_lines(content, need)

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """補算與換季的五格（順序在 SEAM_ORDER；不問 enabled：22:00 換天不是世界層的 day 格）：sync、advance、排程那一下換天（day_actions.conquest_tick；
        sync 的回傳丟掉、advance 的存檔留給它自己那一下一起存）；sync、advance 補翻地的分紅與守城功（day_actions.deliver_conquest）。"""
        if self._seams is None:
            from . import day_actions  # noqa: PLC0415

            self._seams = (
                SeamHook("sync.deliver", "conquest", _turn_in_sync),
                SeamHook("sync.deliver", "conquest.deliver", lambda ctx: day_actions.deliver_conquest(ctx)),
                SeamHook("advance.turn", "conquest", lambda ctx: day_actions.conquest_tick(ctx, False)),
                SeamHook("advance.turn", "conquest.deliver", lambda ctx: day_actions.deliver_conquest(ctx)),
                SeamHook("tick", "conquest", lambda ctx: day_actions.conquest_tick(ctx, True)),
            )
        return self._seams


def _turn_in_sync(ctx) -> None:
    """sync 那一下換天（第一個看到新的一天的人觸發）：回的那幾句不進回話（照原位不接）。"""
    from . import day_actions  # noqa: PLC0415

    day_actions.conquest_tick(ctx, True)


FEATURE = TerritoryActsFeature()
