"""稱號與官職（設計稿 v5）：每週結算頒名號、名號簿、自動戴最高檔、自己挑、易手的那一句、結算的江湖傳聞。"""
from __future__ import annotations

import random

from conftest import real_content

from tianxia.engine import Game
from tianxia.features.titles import actions, rules
from tianxia.sqlite_world import open_world

HOUR, DAY = 3600, 86400
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）


def _game(name="沈浪", store=None, content=None):
    c = content or real_content("season21")
    c.config.titles.enabled = True
    c.config.train_event_chance = 0.0
    if store is None:
        store = open_world()
        store.seed_first_season(c)
        store.open_season(c, MON + 10 * HOUR)
    game = Game.new(c, name, rng=random.Random(0), world=store, prologue=False)
    game.client = None
    game.state.player.tutorial_step = len(c.tutorial.steps)
    _at(game, MON + 10 * HOUR)
    return game


def _at(game, now):
    game.world.catch_up_season(game.content, now, random.Random(0))
    game.sync(now)


def _day(game, n):
    _at(game, MON + (n - 1) * DAY + 10 * HOUR)


def _board(monkeypatch, top):
    monkeypatch.setattr(actions, "_board", lambda ctx: {"宗師": [(top, (3, 0), "")]})


def test_first_week_is_not_settled(monkeypatch):
    g = _game()
    _board(monkeypatch, "沈浪")
    _day(g, 3)
    assert g.state.world.titles_week == 0 and g.state.world.titles_holders == {}
    assert g.state.player.titles_worn == {}


def test_week_change_settles_and_files_the_book(monkeypatch):
    g = _game()
    _board(monkeypatch, "沈浪")
    _day(g, 8)
    w, p = g.state.world, g.state.player
    assert w.titles_week == 2 and w.titles_holders == {"zongshi": ["沈浪"]}
    assert g.world.get_season().titles_holders == {"zongshi": ["沈浪"]}  # 存回共用賽季
    assert p.titles_worn == {"id": "zongshi", "name": "一代宗師", "grade": rules.GOLD}
    assert rules.book_entry(p.season_number, "一代宗師") in p.title_book
    assert any("接下「一代宗師」" in r.text for r in w.rumors)
    assert any(rules.GOT_LINE.format(title="一代宗師") in " ".join(e.lines + e.changes) for e in g.state.journal)
    # 同一週再同步：不再結算、不再寫
    mine = lambda: sum(1 for e in g.state.journal if e.title == rules.JOURNAL_TITLE)  # noqa: E731
    count = mine()
    _at(g, MON + 7 * DAY + 14 * HOUR)
    assert mine() == count and g.state.world.titles_week == 2


def test_holder_changes_hands_next_week(monkeypatch):
    g = _game()
    _board(monkeypatch, "沈浪")
    _day(g, 8)
    _board(monkeypatch, "楚留香")
    _day(g, 15)
    p = g.state.player
    assert g.state.world.titles_holders == {"zongshi": ["楚留香"]}
    assert p.titles_worn == {}
    assert rules.book_entry(p.season_number, "一代宗師") in p.title_book  # 名號簿照留
    lost = rules.LOST_LINE.format(old="一代宗師", now=rules.NOW_NONE)
    assert any(lost in " ".join(e.lines + e.changes) for e in g.state.journal)


def test_auto_wears_highest_and_pin_picks_one(monkeypatch):
    g = _game()
    _board(monkeypatch, "沈浪")
    g.state.player.top_merits = 1
    _day(g, 8)
    p = g.state.player
    assert p.titles_worn["id"] == "zongshi"  # 金 > 朱
    assert actions.set_pin(g, "merit") == [rules.PIN_OK.format(title="破陣首功")]
    assert p.titles_worn["id"] == "merit" and p.titles_pin == "merit"
    assert actions.set_pin(g, "arena1") == [rules.PIN_BAD]
    assert p.titles_pin == "merit"
    assert actions.set_pin(g, "") == [rules.PIN_AUTO]
    assert p.titles_worn["id"] == "zongshi"
    rows = {r["id"]: r for r in actions.view(g)["rows"]}
    assert rows["zongshi"]["mine"] and rows["zongshi"]["worn"] and not rows["arena1"]["mine"]
    assert "divine" not in rows


def test_renown_titles_need_the_top_bar():
    c = real_content("season21")
    store = open_world()
    store.seed_first_season(c)
    season = store.get_season()
    bar = rules.renown.fame_bars(c, season)[-1]
    low = {"名人": [("甲", (bar - 1,), "")]}
    high = {"名人": [("甲", (bar,), "")]}
    assert "fame" not in rules.holders_from(c, season, low)
    assert rules.holders_from(c, season, high)["fame"] == ["甲"]


def test_season_title_grades():
    c = real_content("season21")
    tiers = c.config.jianfa.tiers.titles
    grades = {int(k.split(":")[0]): rules.season_grade(c, v) for k, v in tiers.items()}
    assert all(grades[t] == rules.ZHU for t in grades if t <= 2)
    assert all(grades[t] is None for t in grades if t >= 4)


def test_titles_show_up_in_card_battle_board_and_mingtie(monkeypatch):
    from tianxia import leaderboard
    from tianxia.core import combat
    from tianxia.features.battle import instance as bi
    from tianxia.features.peers import mingtie

    g = _game()
    _board(monkeypatch, "沈浪")
    _day(g, 8)
    worn = dict(g.state.player.titles_worn)
    # 名帖：大印是戴的那一個；尋常的（名聲、某某門下、帖友）不印，名號簿照印
    assert mingtie.seal_of(g.state, g.content) == worn
    pool = mingtie.earned(g.state, g.content)
    assert rules.book_entry(g.state.player.season_number, "一代宗師") in pool
    assert not any(t.endswith("的帖友") or t.endswith("門下") for t in pool)
    assert mingtie.season_book(g.state, g.content, 1) == []
    # 決戰：加入那一刻的快照、戰功榜第二行、將旗、戴名號的人加入時一句戰報
    marks = combat.battle_marks(g)
    assert marks["title"] == worn
    b = bi.BattleInstance(battle_id="t", phase="muster")
    bi.join_faction(b, "沈浪", "guan", 100.0, 5.0, **marks)
    bi.join_faction(b, "甲", "guan", 100.0, 9.0)
    assert any("「一代宗師」沈浪" in line for line in b.narrative_log)
    assert bi.title_flags(b, "guan", "huangjin") == {"left": [{"name": "沈浪", "title": worn}]}
    assert "title" not in b.participants["甲"].model_dump()  # 沒戴不寫這個鍵
    # 榜單：名字後面的小印
    board = {"宗師": [("沈浪", (3, 0), "絕學 3 門")], leaderboard.WORN: {"沈浪": worn}}
    rows = next(e for e in leaderboard.view(board, me="沈浪") if e["id"] == "宗師")["rows"]
    assert rows[0]["title"] == worn


def test_switch_off_adds_nothing():
    from tianxia.core import combat, presence

    c = real_content("season21")
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, MON + 10 * HOUR)
    g = Game.new(c, "沈浪", rng=random.Random(0), world=store, prologue=False)
    _at(g, MON + 7 * DAY + 10 * HOUR)
    assert "title" not in combat.battle_marks(g)
    assert g.state.world.titles_week == 0 and g.state.player.titles_worn == {}
    dumped = g.state.player.model_dump()
    assert "titles_pin" not in dumped and "titles_worn" not in dumped
    g.state.player.season_title = "有功之臣"
    assert presence.affiliation(g.state, c).endswith("有功之臣")


def test_wear_route_needs_login_and_is_404_while_off(monkeypatch):
    from fastapi.testclient import TestClient

    import server

    client = TestClient(server.app, raise_server_exceptions=False)
    assert client.post("/api/titles/wear", json={"id": ""}).status_code == 401
    monkeypatch.setattr(server, "_account", lambda request: "k")
    assert client.post("/api/titles/wear", json={"id": ""}).status_code == 404
