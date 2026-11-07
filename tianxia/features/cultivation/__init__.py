"""修練（改練、練成、意境裝卸、熔煉、絕學與破境丹、破境卡、傳功、配點、拜師學藝）。功能包，開發規範手冊 3.2；全部拆包第 23 批搬進來
（計畫 docs/superpowers/plans/2026-11-01-修練包-第1批.md）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- cultivation.py、chuangong.py、ascend.py：純規則（原 tianxia/ 底下同名的三個模組；那三個名字留成指到這裡的別名）——絕學的契機與服丹衝關、
  舊存檔的絕學定名；傳功門下；破境（破境卡與卡上那一句的三段式）
- actions.py：原本 Game 上修練頁的動作與拜師學藝（learn:；Game 留一行委派給 server、假人、測試與核心原位）
- view.py：修練頁的唯讀資料（server.menxia_view 叫的那幾個；Game 留一行委派）
"""
from __future__ import annotations

from tianxia.core.features import Feature, HowtoHook, MenuHook, Outcome, SeamHook, StatusHook, slot_some


class CultivationFeature(Feature):
    name = "cultivation"
    # 拜師學藝（武學與成長設計附錄 B）：learn:<武學 id>。鈕照舊在 Game._everyday_options 原位畫（移動鈕之後、投靠之前，位置算行為；
    # 只叫共用規則層的 library），按下去由這一包接走（choose 掛鉤，標題在動作之前先拿）。假人：bot_policy.score 沒有 learn 那一段
    # （落到最後的 return None），拿了前綴之後 bot_pick 照預設回 None＝不按，跟原本一樣；學藝是 bot_policy.tend_arts 的 _learn_here
    # 直接 choose 的。不開 bots.py
    prefix = "learn"
    web = ("cultivation.js", "cultivation.css")  # 俠客頁的畫法（全部拆包第 64 批從 app.js 切出來）。熔煉的問句與樣子第 67 批從 main.js、style.css 切出來（卷軸卡與功法庫跟引導的 .onb-dim 同權重，留 style.css）
    # 等著定名的那一門、定名通知過的、剛破境還沒看過的破境卡、每一門服丹沒衝開幾次、境界卡記的那一級：換季都跟著新角色重來
    player_fields = ("naming", "renames_told", "ascension", "legend_fails", "milestone_due")
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        """一直開著：修練頁與拜師學藝每一季都有（沒有自己的開關；傳功、破境丹、境界卡各自先問自己的設定）。"""
        return True

    def choose(self, ctx, kind, arg):
        """learn:<武學 id>（原本 Game.choose 的 learn 那一支與 _action_title 的「學藝・<武學名>」）：照模組屬性叫。"""
        if kind != self.prefix:
            return None
        from . import actions  # noqa: PLC0415

        return Outcome(title=actions.learn_title(ctx, arg), run=lambda: actions.learn(ctx, arg))

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """補算與換季的兩格（順序在 SEAM_ORDER；不問 enabled）：別人替手上那一門定了名，同步補一則（actions.deliver_renames：玉璽補送之後、首創名望回饋之前）；
        讀檔拿掉追風步的舊品質（actions.drop_old_zhuifeng：要在 arts.migrate 之前）。"""
        if self._seams is None:
            from . import actions  # noqa: PLC0415

            self._seams = (
                SeamHook("sync.deliver", "renames", lambda ctx: actions.deliver_renames(ctx)),
                SeamHook("stale.early", "cultivation", lambda ctx: actions.drop_old_zhuifeng(ctx)),
            )
        return self._seams

    # core_seams（全部拆包第 56 批「選單收接縫」）
    _menus: tuple[MenuHook, ...] | None = None

    def menus(self) -> tuple[MenuHook, ...]:
        """選單的一格（順序在 MENU_ORDER；不問 enabled）：此地的拜師學藝。"""
        if self._menus is None:
            from . import actions  # noqa: PLC0415

            self._menus = (
                MenuHook("here", "lessons", lambda ctx, loc, cost, odds: actions.lesson_options(ctx)),
            )
        return self._menus

    # howto（全部拆包第 59 批「引導二」）
    def howto(self) -> tuple[HowtoHook, ...]:
        """玩法說明的xinde、pages 兩格：順序在核心 HOWTO_ORDER，不問 enabled；在叫的那一下才照模組屬性找。"""
        from . import howto as words  # noqa: PLC0415

        return (
            HowtoHook("xinde", lambda content, season, page: words.xinde_section(content)),
            HowtoHook("pages", lambda content, season, page: words.pages_section()),
        )

    # shell_web（全部拆包第 66 批：狀態列與江湖畫面的格，先後在 STATUS_ORDER；不問 enabled，原位那幾行本來就不看包的開關）
    _status_slots: tuple[StatusHook, ...] | None = None

    def status_slots(self) -> tuple[StatusHook, ...]:
        """建一次就留著，在叫的那一下才照模組屬性找（monkeypatch 照樣有效）；frame 見 core/features.py 的 StatusHook。"""
        if self._status_slots is None:
            from . import actions  # noqa: PLC0415

            self._status_slots = (
                # 剛破境、還沒看過的破境卡
                StatusHook("status", "ascension", lambda ctx, frame: {"ascension": actions.ascend_view(ctx)}),
                # 減法季屬性五段的境界卡（主機側計畫欄位表 main.milestone）：到了境界、點還沒配完才有這個鍵
                StatusHook("main", "milestone", lambda ctx, frame: slot_some("milestone", actions.milestone_card(ctx))),
            )
        return self._status_slots

    def main_actions(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼建動作表時才 import（同 routes 掛鉤）

        return routes.main_actions(shell)

    def menxia_actions(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼建動作表時才 import（同 routes 掛鉤）

        return routes.menxia_actions(shell)

    def outlock(self, shell):
        from . import routes  # noqa: PLC0415  只在殼建鎖外工作時才 import（同 routes 掛鉤）

        return routes.outlock(shell)


FEATURE = CultivationFeature()
