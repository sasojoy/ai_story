"""修練（改練、練成、意境裝卸、熔煉、絕學與破境丹、破境卡、傳功、配點、拜師學藝）。功能包，開發規範手冊 3.2；全部拆包第 23 批搬進來
（計畫 docs/superpowers/plans/2026-11-01-修練包-第1批.md）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- cultivation.py、chuangong.py、ascend.py：純規則（原 tianxia/ 底下同名的三個模組；那三個名字留成指到這裡的別名）——絕學的契機與服丹衝關、
  舊存檔的絕學定名；傳功門下；破境（破境卡與卡上那一句的三段式）
- actions.py：原本 Game 上修練頁的動作與拜師學藝（learn:；Game 留一行委派給 server、假人、測試與核心原位）
- view.py：修練頁的唯讀資料（server.menxia_view 叫的那幾個；Game 留一行委派）
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome


class CultivationFeature(Feature):
    name = "cultivation"
    # 拜師學藝（武學與成長設計附錄 B）：learn:<武學 id>。鈕照舊在 Game._everyday_options 原位畫（移動鈕之後、投靠之前，位置算行為；
    # 只叫共用規則層的 library），按下去由這一包接走（choose 掛鉤，標題在動作之前先拿）。假人：bot_policy.score 沒有 learn 那一段
    # （落到最後的 return None），拿了前綴之後 bot_pick 照預設回 None＝不按，跟原本一樣；學藝是 bot_policy.tend_arts 的 _learn_here
    # 直接 choose 的。不開 bots.py
    prefix = "learn"
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


FEATURE = CultivationFeature()
