"""江湖輿圖的資料（純資料，不依賴介面框架）：大區歸屬。"""
from __future__ import annotations

import math

from .models import Content, MapRegion


def _inside(x: float, y: float, points: list[list[int]]) -> bool:
    """射線法：點是否在多邊形內。"""
    inside = False
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _edge_distance(x: float, y: float, points: list[list[int]]) -> float:
    """點到多邊形邊界的最短距離。"""
    best = math.inf
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        dx, dy = x2 - x1, y2 - y1
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)))
    return best


def region_of(content: Content, loc_id: str) -> MapRegion | None:
    """地點所屬的大區：座標落在哪個大區的多邊形內（依 map.json 的順序取第一個）；
    落在所有大區外時歸給邊界最近的大區（同樣近取排在前面的）。地圖沒有大區時為 None。"""
    regions = content.map.regions
    if not regions:
        return None
    loc = content.locations[loc_id]
    for region in regions:
        if _inside(loc.x, loc.y, region.points):
            return region
    return min(regions, key=lambda region: _edge_distance(loc.x, loc.y, region.points))
