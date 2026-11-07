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

from tianxia.core.features import Feature, HowtoHook, SeamHook, StatusHook, slot_some


class TerritoryActsFeature(Feature):
    name = "territory_acts"
    web = ("territory_acts.js", "territory_acts.css")  # 見聞的〈天下形勢〉（全部拆包第 66 批從 app.js 切出來；樣子第 67 批從 style.css 切出來）
    prefix = None  # 地盤的動作走 /api/do/conquest_letter 與管理者工具，選單上沒有這一包的選項
    # 沒有 PlayerState 欄位：WorldState.conquest、xingshi、xingshi_ticket、xingshi_mark 是全服的帳，留在 state.py
    player_fields: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()
    content = ("xingshi_lines.json",)  # 〈天下形勢〉的句型；content.py 照它到這一包的 content/ 載，驗證在下面的 check_content

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

    # howto（全部拆包第 59 批「引導二」）
    def howto(self) -> tuple[HowtoHook, ...]:
        """玩法說明的land 那一格：順序在核心 HOWTO_ORDER，不問 enabled；在叫的那一下才照模組屬性找。"""
        from . import howto as words  # noqa: PLC0415

        return (HowtoHook("land", lambda content, season, page: words.land_section(content, season)),)

    # shell_web（全部拆包第 66 批：狀態列與江湖畫面的格，先後在 STATUS_ORDER；不問 enabled，原位那幾行本來就不看包的開關）
    _status_slots: tuple[StatusHook, ...] | None = None

    def status_slots(self) -> tuple[StatusHook, ...]:
        """建一次就留著，在叫的那一下才照模組屬性找（monkeypatch 照樣有效）；frame 見 core/features.py 的 StatusHook。"""
        if self._status_slots is None:
            from . import view, xingshi, xingshi_actions  # noqa: PLC0415

            self._status_slots = (
                # 領地爭奪：戰書排的攻城、每一塊的翻地資料、能不能下戰書（開關關著、季收了沒有這個鍵）
                StatusHook("main", "conquest", lambda ctx, frame: slot_some("conquest", view.conquest_view(ctx))),
                # 〈天下形勢〉開著的季：見聞多一顆「形勢」（文章另外讀 /api/xingshi）；FB-578 xingshi_mark：最新一篇的篇次＋有沒有一張還在寫，變了停在「形勢」頁的網頁就重抓
                StatusHook("main", "xingshi", lambda ctx, frame: {"xingshi": True, "xingshi_mark": xingshi_actions.mark(ctx)} if xingshi.on(ctx.content, ctx.state.world) else {}),
            )
        return self._status_slots

    def main_actions(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼建動作表時才 import（同 routes 掛鉤）

        return routes.main_actions(shell)

    def outlock(self, shell):
        from . import routes  # noqa: PLC0415  只在殼建鎖外工作時才 import（同 routes 掛鉤）

        return routes.outlock(shell)


def _turn_in_sync(ctx) -> None:
    """sync 那一下換天（第一個看到新的一天的人觸發）：回的那幾句不進回話（照原位不接）。"""
    from . import day_actions  # noqa: PLC0415

    day_actions.conquest_tick(ctx, True)


FEATURE = TerritoryActsFeature()
