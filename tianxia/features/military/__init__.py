"""軍情（功能包；開發規範手冊 3.2）：軍令卡與押糧（接下糧車、走到終點交軍令）、第 2 階行動、第 3／4 階行動（煽動起事、修築塢堡、趁亂占據郡縣）、
第 4 階席次的抄帳、管理者重發軍令／輪替席次／發召見。全部拆包第 33 批搬進來（計畫 docs/superpowers/plans/2026-11-05-軍情包-第1批.md）。
README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

包名不叫 `orders`：`tianxia/orders.py`（軍令的規則）、`ranks.py`、`seats.py` 這一批不搬（共用規則層，總表第 40 批收），包裡照 `# 過渡：待搬` 或 `registry.SHARED` import。

沒有選項前綴：`act:rank2`、`act:convoy`、`act:summons`、`act:rank:<行動>` 都是核心 `_act` 的 act 子動詞（行動列），選單那三段、按下去、抄帳、管理者的鈕都在核心原位叫
Game 上的一行委派（理由在 tests/core/test_feature_boundaries.py 的 `# military` 那一段）；沒有掛鉤、沒有路由（server.py 的 `orders`、`convoy` 兩個鍵與管理者三顆鈕照舊叫 Game）。
假人分數（`act:rank2`、`act:convoy`、`act:summons`）留在 bot_policy.score 的 act 分支原位。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class MilitaryFeature(Feature):
    name = "military"
    prefix = None  # 沒有自己的選項前綴（act: 是核心的行動列）
    # 認領的 PlayerState 欄位（手冊 3.5：留在原地）：押著的糧車、第 2 階今天做了幾次、第 3／4 階這週做了幾次。換季全部跟著新角色重來
    player_fields = ("convoy", "rank2_days", "rank_action_weeks")
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return True


FEATURE = MilitaryFeature()
