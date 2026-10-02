"""陣營規模的換算（第一季設計 5.4、十二；伺服器假人設計第八節第 5 項）。

伺服器從試玩的幾十人長到兩三千人，每陣營的第四階席次（之後還有軍令的陣營總額度）都照
「伺服器人數上限」等比例換算：小伺服器不會永遠坐不滿，大伺服器也不會人人都是第四階。
"""
from __future__ import annotations

from .models import Config


def rank4_seats(config: Config) -> int:
    """每陣營第四階席次：人數上限 × rank4_seat_ratio，四捨五入，最少 1 席。"""
    return max(1, round(config.server_max_players * config.rank4_seat_ratio))
