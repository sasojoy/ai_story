"""7 天季領地爭奪調整（2026-10-22，計畫 docs/superpowers/plans/2026-10-22-7天季領地爭奪調整.md 第五節）：week7 一打贏推的量 ×6
（progress_scale 2 → 12；設定覆寫檔是淺層合併，`conquest` 那一塊連 enabled 一起寫）；第 4 階門檻 870 → 600（企劃者 2026-10-22 選甲：
戰書要季中就下得了）。週末、21 天、14 天的這幾個數字一個都不動。"""
from __future__ import annotations

import pytest

from conftest import real_content
from tianxia.models import ConquestRules

pytestmark = pytest.mark.slow  # 載正式內容（四份）


def test_week7_only_pushes_harder():
    defaults = ConquestRules(enabled=True)  # content/config.json 只寫 enabled，三種設定覆寫檔照它
    week7 = real_content("week7").config.conquest
    assert week7.enabled is True and week7.progress_scale == 12
    assert week7.model_copy(update={"progress_scale": defaults.progress_scale}) == defaults  # 只差這一個鍵
    for profile in (None, "season21"):
        assert real_content(profile).config.conquest == defaults, profile


def test_week7_rank4_comes_sooner_and_only_there():
    """第 4 階（在任才下得了戰書）門檻：7 天季 600（第 2、3 階照舊 130／430）；14 天、週末照 Config 預設 1800，21 天 2600。"""
    cfg = real_content("week7").config
    assert (cfg.rank2_contrib, cfg.rank3_contrib, cfg.rank4_contrib) == (130, 430, 600)
    assert [real_content(p).config.rank4_contrib for p in (None, "season21")] == [1800, 2600]
