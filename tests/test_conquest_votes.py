"""領地爭奪第二批 Task 8：每天投票（裁決 9：不論有沒有第 4 階都投，第 4 階的票合起來佔 55%；第 4 階不再直接下令；
假人照樣投）、畫面資料不露名號（設計 4.9）。"""
from __future__ import annotations

import json

import pytest

import server
from conquest_kit import conquest_game, join, plain_game
from tianxia import bot_policy, conquest, conquest_day
from tianxia.state import BotProfile

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOW = 1_792_000_000.0  # 2026-10 某一天的現實時間（不碰電腦時鐘）


def _pair():
    """同一個世界裡兩個黃巾的人（甲在前、乙在後）。"""
    a = join(conquest_game("season21", name="甲某"), "huang")
    b = join(conquest_game("season21", name="乙某", world=a.world), "huang")
    for g in (a, b):
        g.now = NOW
    return a, b


def _refresh(game):
    game.state.world = game.world.get_season()
    return game


def _target(game):
    return conquest.targets(game.state.world, game.content, "huang")[0]


def _slot(game):
    key = conquest_day.day_key(game.pill_now(), game.content.config) + 1
    return conquest_day.slots(game.state.world, game.content, key, game.pill_now())[-1]


def test_vote_records_and_can_change():
    a, _ = _pair()
    t1, t2 = conquest.targets(a.state.world, a.content, "huang")[:2]
    msgs = a.conquest_vote(t1, _slot(a))
    assert any(a.content.locations[t1].name in m for m in msgs)
    a.conquest_vote(t2, _slot(a))
    state = _refresh(a).state.world.conquest
    assert {name: p.loc for name, p in state.votes["huang"].items()} == {"甲某": t2}  # 一人一票，改了就覆蓋
    assert state.votes_for == conquest_day.day_key(NOW, a.content.config) + 1  # 替明天投的
    view = a.conquest_view()
    assert view["mine"]["loc"] == t2 and view["can_vote"]


def test_view_hides_names_and_shows_weighted_shares():
    a, b = _pair()
    target = _target(a)
    a.conquest_vote(target, _slot(a))
    _refresh(b).conquest_vote(conquest.targets(b.state.world, b.content, "huang")[1], _slot(b))
    view = _refresh(a).conquest_view()
    blob = json.dumps(view, ensure_ascii=False)
    assert "甲某" not in blob and "乙某" not in blob  # 不公開誰投了什麼
    assert view["tomorrow"]["how"] == "vote"
    assert sorted(r["share"] for r in view["tomorrow"]["rows"]) == [50, 50]
    a.state.world.seats["huang"] = ["甲某"]  # 甲在任第 4 階：他那一票合起來 55%
    rows = {r["loc"]: r["share"] for r in a.conquest_view()["tomorrow"]["rows"]}
    assert rows[target] == 55
    assert "下令" not in blob  # 第 4 階不再直接下令（裁決 9）


def test_vote_rejects_non_target_and_bad_slot():
    a, _ = _pair()
    assert any("打不到" in m for m in a.conquest_vote("changshe", _slot(a)))  # 官軍大本營：搶不下來
    assert any("時辰" in m for m in a.conquest_vote(_target(a), 3 * 60))  # 半夜三點不開打
    assert a.state.world.conquest.votes.get("huang", {}) == {}


def test_ranger_cannot_vote_but_sees_the_schedule():
    game = join(conquest_game("season21"), None)
    game.now = NOW
    assert any("投靠" in m for m in game.conquest_vote(_target(game), 21 * 60))
    view = game.conquest_view()
    assert view is not None and view["can_vote"] is False and view["why"] and view["tomorrow"] is None


def test_bot_votes_the_commander_pick_once_per_day():
    game = join(conquest_game("season21", name="假某"), "huang")
    game.now = NOW
    game.state.player.bot = BotProfile(personality="普通", seed=1, faction="huang", season_number=1)
    bot_policy._conquest_vote(game)
    votes = _refresh(game).state.world.conquest.votes["huang"]
    key = conquest_day.day_key(NOW, game.content.config) + 1
    want = conquest_day.commander_picks(
        game.state.world, game.content, "huang", 1, key, set(), conquest_day.slots(game.state.world, game.content, key, NOW),
    )[0][0]
    assert votes["假某"] == want
    game.state.world.conquest.votes["huang"]["假某"] = want.model_copy(update={"minute": 12 * 60})
    bot_policy._conquest_vote(game)  # 投過了：這一天不再投
    assert game.state.world.conquest.votes["huang"]["假某"].minute == 12 * 60


def test_main_view_carries_conquest_and_vote_action():
    a, _ = _pair()
    assert "conquest_vote" in server.MAIN_ACTIONS and "conquest_order" not in server.MAIN_ACTIONS
    server.MAIN_ACTIONS["conquest_vote"](a, {"loc": _target(a), "minute": _slot(a)})
    assert server.main_view(_refresh(a))["conquest"]["mine"]["loc"] == _target(a)


def test_switch_off_no_view_no_vote():
    game = join(plain_game("season21"), "huang")
    game.now = NOW
    assert game.conquest_view() is None
    assert any("沒有" in m for m in game.conquest_vote("nanyang_road", 21 * 60))
    assert game.state.world.conquest is None
    assert "conquest" not in server.main_view(game)
