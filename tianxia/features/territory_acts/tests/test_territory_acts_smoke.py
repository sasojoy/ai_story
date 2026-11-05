"""地盤的行動的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：21 天季、〈天下形勢〉開著，第一次同步只記下今天，晚上下一張戰書，
過了 22:00 換天——前一天排的作罷、新的一天開一張〈天下形勢〉的單；管理者取消不存在的一場攻城回「找不到」；殼掛了 /api/xingshi 與五個救場工具。"""
import calendar as pycal
from datetime import datetime

import pytest

from conquest_kit import conquest_game, join
from tianxia.core.registry import FEATURES
from tianxia.features.territory_acts import admin_actions, conquest_day


def _tw(y, mo, d, h, mi=0) -> float:
    return float(pycal.timegm(datetime(y, mo, d, h, mi).timetuple())) - 8 * 3600


@pytest.mark.smoke
def test_the_daily_turn_opens_a_xingshi_ticket_after_a_letter():
    feature = next(f for f in FEATURES if f.name == "territory_acts")
    game = join(conquest_game("season21", name="沈浪", xingshi=True), "huang")
    assert feature.enabled(game) and feature.prefix is None and feature.player_fields == ()
    game.now = _tw(2026, 10, 20, 10)
    game._conquest_tick()  # 第一次：只記下今天
    w = game.state.world
    assert w.xingshi_ticket is None and w.xingshi_mark is not None
    game.now = _tw(2026, 10, 20, 21, 45)
    placed = conquest_day.place_letter(w, game.content, "huang", "nanyang_road", "沈浪", game.pill_now())
    assert placed is not None
    game._save_season()
    game.now = _tw(2026, 10, 20, 22, 1)
    game._conquest_tick()
    ticket = game.world.get_season().xingshi_ticket
    assert ticket is not None and ticket.n == 1 and not ticket.taken
    assert admin_actions.conquest_cancel(game, "no-such-slot")  # 不是管理者：被擋，回一句話
