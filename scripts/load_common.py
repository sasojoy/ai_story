"""壓測的共用工具：百分位數與摘要（線上架構設計 9.2 的目標都用九成五的回應時間講）。"""
from __future__ import annotations

import math


def percentiles(samples: list[float]) -> dict[str, float | None]:
    """取最接近的那一筆（nearest-rank：第 ceil(q × 筆數) 小的那一筆），樣本少也不內插；空的回 None。
    不用 round：Python 的 round 是四捨六入五成雙，5 筆取中位數會落到第 2 小而不是第 3 小。
    乘出來的數字帶一點浮點誤差（例如 0.07 × 100 ＝ 7.000000000000001），所以先減一個很小的數再進位。"""
    if not samples:
        return {"count": 0, "p50": None, "p95": None, "p99": None, "max": None}
    ordered = sorted(samples)

    def rank(q: float) -> float:
        index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered) - 1e-9) - 1))
        return ordered[index]

    return {"count": len(ordered), "p50": rank(0.50), "p95": rank(0.95), "p99": rank(0.99), "max": ordered[-1]}


def summarize(name: str, samples: list[float], errors: int) -> str:
    p = percentiles(samples)
    if not p["count"]:
        return f"{name}：0 次，錯誤 {errors}"
    return (
        f"{name}：{p['count']} 次，錯誤 {errors}，p50 {p['p50']:.3f} 秒，p95 {p['p95']:.3f} 秒，"
        f"p99 {p['p99']:.3f} 秒，最慢 {p['max']:.3f} 秒"
    )
