"""「此地還有」的窗口（Joy 2026-10-19「遊戲裡能真的碰到面的只有 10 分鐘內在線的人 這不好吧 至少拉長」
→「就是要可以殺得到啊 延長到24小時怕被殺去城鎮」）。

舊的 600 秒等於兩個人幾乎碰不到面（一天 16 個真人、同時多半 1～3 個），連酒肆花錢查到的人也多半是
「在那裡但已經離線」。現在是 24 小時：下線也看得到、互動得到、**截殺得到**，不想被殺就在城鎮下線
（城鎮類地點不能動手，Game.raid_refusal）。

這一份另外守住「哪些東西刻意不跟著拉長」：主機端那兩支（暖機看守、監控頁）要的是「真的在線」，
拿 24 小時當在線的話，省電模式永遠不卸模型、監控頁永遠寫著幾十人在線。
"""
from __future__ import annotations

import sys
from pathlib import Path

from conftest import real_content

ROOT = Path(__file__).resolve().parent.parent


def test_you_can_be_reached_for_a_day():
    assert real_content("week7").config.presence_seconds == 86400


def test_the_town_is_the_safe_place_so_the_long_window_has_an_answer():
    """拉長的代價由「城鎮不能動手」擋：正式內容裡城鎮類的地點要真的存在、而且夠多。"""
    c = real_content("week7")
    towns = [loc for loc in c.locations.values() if c.config.explore_mix_of(loc.tags).kind == "town"]
    assert len(towns) >= 5, [loc.name for loc in towns]


def test_an_invite_does_not_live_a_whole_day():
    """邀請不跟著拉到 24 小時：切磋、論武要兩個人都在，隔一天才被接受的邀請只會變成一堆作廢訊息。"""
    c = real_content("week7").config
    assert c.invite_ttl_seconds <= 3600 < c.presence_seconds


def test_the_warm_keeper_keeps_its_own_short_window():
    """暖機看守照 presence 判就等於永遠有人在玩，模型永遠不卸、省電模式白做。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    import warm_keeper

    assert warm_keeper.ONLINE_SECONDS == 600
    source = (ROOT / "scripts" / "warm_keeper.py").read_text(encoding="utf-8")
    assert "config.presence_seconds" not in source


def test_the_monitor_page_still_means_online_by_online():
    sys.path.insert(0, str(ROOT / "scripts"))
    import monitor

    assert monitor.PRESENCE == 600
    assert "在線" in monitor.WINDOWS[monitor.ONLINE_ROW][1] and "10 分鐘" in monitor.WINDOWS[monitor.ONLINE_ROW][1]
    reach = monitor.WINDOWS[-1]
    assert reach[0] == real_content("week7").config.presence_seconds  # 最後一行照設定寫
    assert "互動得到" in reach[1] and "24 小時" in reach[1]
