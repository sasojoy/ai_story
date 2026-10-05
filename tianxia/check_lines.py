"""檢定選項上的「心裡話」（週末試玩 A：推翻 9/29 交鋒統一的「不顯示成功率」）。

選項標籤寫「（出手者・屬性 數值：一句心裡話）」，不寫成功率也不寫難度；成功率照下面五段分，
每一段在 content/check_lines.json 有幾句話。純文字與雜湊：不碰引擎的亂數，每次畫選單都不會閃。
"""
from __future__ import annotations

import zlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import CheckLines

# (檔案裡的鍵, 這一段的成功率下限 %)：由高到低
BUCKETS: tuple[tuple[str, int], ...] = (("80+", 80), ("60-79", 60), ("40-59", 40), ("20-39", 20), ("0-19", 0))
BUCKET_KEYS: tuple[str, ...] = tuple(key for key, _ in BUCKETS)

_EPSILON = 1e-6  # 浮點數誤差：臂力 5 對難度 8 算出 0.19999999999999996，它是整整 20%


def bucket_of(chance: float) -> str:
    """成功率（0～1）落在哪一段。"""
    percent = chance * 100 + _EPSILON
    for key, low in BUCKETS:
        if percent >= low:
            return key
    return BUCKETS[-1][0]


def pick_line(lines: CheckLines, stat: str, chance: float, seed: str) -> str:
    """這個成功率、這個屬性的心裡話：該屬性自己寫了這一段就用它，沒有就用通用的；一段有好幾句時，
    照 seed（事件 id＋選項序號）與段位的雜湊挑一句——同一個選項永遠是同一句，也不動引擎的亂數。"""
    bucket = bucket_of(chance)
    pool = lines.by_stat.get(stat, {}).get(bucket) or lines.generic[bucket]
    if len(pool) == 1:
        return pool[0]
    return pool[zlib.crc32(f"{seed}|{bucket}".encode("utf-8")) % len(pool)]
