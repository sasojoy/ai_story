"""「此地還有」的窗口（Joy 2026-10-19「遊戲裡能真的碰到面的只有 10 分鐘內在線的人 這不好吧 至少拉長」）。

以前 presence_seconds 是 600 秒：在線密度這麼低（一天 16 個真人、同時多半 1～3 個）的時候，
兩個人幾乎碰不到面，連酒肆花錢查到的人也多半是「在那裡但已經離線」的。正式內容拉到 1800 秒。
"""
from __future__ import annotations

from pathlib import Path

from conftest import real_content

ROOT = Path(__file__).resolve().parent.parent


def test_the_live_window_is_half_an_hour():
    c = real_content("weekend").config
    assert c.presence_seconds == 1800


def test_an_invite_lives_at_least_as_long_as_you_can_see_him():
    """看得到他 30 分鐘、邀請卻 10 分鐘就過期的話，玩家會對著看得到的人發出一堆默默失效的邀請。"""
    c = real_content("weekend").config
    assert c.invite_ttl_seconds >= c.presence_seconds


def test_the_monitor_page_reads_the_same_number():
    """監控頁的「在線」要跟遊戲同一個定義（它刻意用標準庫直接讀 content/config.json，不 import tianxia）。"""
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import monitor

    assert monitor._presence() == real_content("weekend").config.presence_seconds
    label = monitor._windows()[monitor.ONLINE_ROW][1]
    assert "在線" in label and "30" in label  # 標籤照數字寫，不寫死「10 分鐘內」
