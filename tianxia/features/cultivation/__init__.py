"""修練（改練、練成、意境裝卸、熔煉、絕學與破境丹、破境卡、傳功、配點、拜師學藝）。功能包，開發規範手冊 3.2；全部拆包第 23 批搬進來
（計畫 docs/superpowers/plans/2026-11-01-修練包-第1批.md）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- cultivation.py、chuangong.py、ascend.py：純規則（原 tianxia/ 底下同名的三個模組；那三個名字留成指到這裡的別名）——絕學的契機與服丹衝關、
  舊存檔的絕學定名；傳功門下；破境（破境卡與卡上那一句的三段式）
- actions.py：原本 Game 上修練頁的動作與拜師學藝（learn:；Game 留一行委派給 server、假人、測試與核心原位）
- view.py：修練頁的唯讀資料（server.menxia_view 叫的那幾個；Game 留一行委派）
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome, StatusHook, slot_some


class CultivationFeature(Feature):
    name = "cultivation"
    # 拜師學藝（武學與成長設計附錄 B）：learn:<武學 id>。鈕照舊在 Game._everyday_options 原位畫（移動鈕之後、投靠之前，位置算行為；
    # 只叫共用規則層的 library），按下去由這一包接走（choose 掛鉤，標題在動作之前先拿）。假人：bot_policy.score 沒有 learn 那一段
    # （落到最後的 return None），拿了前綴之後 bot_pick 照預設回 None＝不按，跟原本一樣；學藝是 bot_policy.tend_arts 的 _learn_here
    # 直接 choose 的。不開 bots.py
    prefix = "learn"
    web = ("cultivation.js",)  # 俠客頁的畫法（全部拆包第 64 批從 app.js 切出來）；點擊分派的 case 照舊在 app.js（殼）。css 第 67 批才切
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


FEATURE = CultivationFeature()
