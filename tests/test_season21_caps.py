"""正式季整合第 6 批：軍階、每週上限、人物回復（設計 3.7～3.9；12.3 第 17、18 條）。只在 21 天季（season21 設定），週末與 14 天一個字都不變。"""
from __future__ import annotations

from conftest import real_content

from tianxia import ranks


def test_season21_rank_thresholds():
    c21 = real_content("season21")
    assert [ranks.threshold(c21, r) for r in (2, 3, 4)] == [400, 1300, 2600]
    for profile in ("weekend", None):
        assert [ranks.threshold(real_content(profile), r) for r in (2, 3, 4)] == [300, 900, 1800]
