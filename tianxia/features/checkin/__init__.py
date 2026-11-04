"""簽到（功能包；開發規範手冊 3.2）：21 天季每天簽一次（丹的日子給回體丹、第 6、13、20 天自己挑一個四階，其餘輪流銀兩與一階素材）。
全部拆包第 30 批搬進來。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- checkin.py：簽到的規則（原 tianxia/checkin.py，舊名留成別名；`on`、`PILL_FOUND` 是核心 core/services.py 的 checkin_on、PILL_FOUND，這裡 re-export）
- actions.py：原本 Game 上的 3 個方法（check_in、_auto_checkin、checkin_view；Game 留 3 個一行委派）的本體

沒有選項前綴（簽到不放鈕：江湖頁的小標，/api/do/checkin 在殼的 MAIN_ACTIONS，照舊叫 Game.check_in）、沒有路由、沒有假人分數（假人叫的是 Game.checkin_view、check_in）。
"""
from __future__ import annotations

from tianxia.core.features import Feature
from tianxia.core.services import checkin_on


class CheckinFeature(Feature):
    name = "checkin"
    prefix = None  # 沒有選項 id（簽到是江湖頁的小標）
    # 認領的 PlayerState 欄位（手冊 3.5：留在原地）：這一季簽過的是第幾天、第 6、13、20 天自己挑的四階。換季跟著新角色清空
    player_fields = ("checkin_days", "checkin_picks")
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        """簽到開著沒（設定打開、21 天季、還沒收季）。沒有任何掛鉤吃這個開關：Game.check_in、_auto_checkin、checkin_view 本來就各自問 checkin.on。"""
        return checkin_on(ctx.content, ctx.state.world)


FEATURE = CheckinFeature()
