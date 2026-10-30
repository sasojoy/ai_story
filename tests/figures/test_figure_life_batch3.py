"""大勢人物擴充第三批「大家一起」（Joy 2026-10-19「第三批開始做」）：月旦評（yuedan）、求援委託
（bounties 的 rallies）。用真實內容（content/，figure_life 預設開著）；每個測試拿自己的一份複本。
宴客那一段搬進功能包 tianxia/features/feast/tests/test_feast.py（開發規範手冊 4.6，測試本身一個字不改）。"""
from __future__ import annotations

import pytest

from conftest import real_content
from tianxia import bounties, calendar, figure_life, figures, yuedan
from tianxia.state import GameState, PlayerState
from tianxia.world_state import fresh_season


@pytest.fixture
def c():
    return real_content()


def _season(content, location: str | None = None) -> GameState:
    player = PlayerState(name="甲", location=location or content.scenario.start_location, stats={}, stamina=0)
    return GameState(player=player, world=fresh_season(content))


# ── 月旦評 ────────────────────────────────────────────


def test_the_picks_take_turns_across_the_boards():
    board = {"名人": [("甲", (9,), "名望 9"), ("乙", (8,), "名望 8")], "善人": [("甲", (5,), "善名 5"), ("丙", (4,), "善名 4")],
             "惡人": [("丁", (3,), "惡名 3")]}
    assert yuedan.pick(board, 6) == [("甲", "名人", "名望 9"), ("丙", "善人", "善名 4"), ("丁", "惡人", "惡名 3"),
                                     ("乙", "名人", "名望 8")]
    assert len(yuedan.pick(board, 2)) == 2


def test_a_new_week_brings_a_review_that_goes_out_after_the_wait(c, monkeypatch):
    from tianxia import leaderboard

    monkeypatch.setattr(leaderboard, "compute_boards", lambda content, world: {
        "名人": [("甲", (9,), "名望 9")], "善人": [], "惡人": [("乙", (3,), "惡名 3")]})
    s = _season(c)
    s.world.time = calendar.WEEK / calendar.cal_scale(c, s.world) * (c.config.figure_life.yuedan_from_week - 1) + 1
    yuedan.tick(s, c, object())
    assert [e.name for e in s.world.yuedan] == ["甲", "乙"] and not any(e.published for e in s.world.yuedan)
    assert yuedan.request(s, c) is not None
    s.world.time += c.config.figure_life.yuedan_wait_seconds
    yuedan.tick(s, c, object())
    assert all(e.published for e in s.world.yuedan)
    assert any("月旦評" in r.text and "甲「" in r.text for r in s.world.rumors)
    assert any("月旦評" in r.text for r in s.world.chronicle)
    assert yuedan.line_for(s, c, "甲").startswith("月旦評：「")
    assert yuedan.line_for(s, c, "丙") == ""
    yuedan.tick(s, c, object())  # 同一週不再評
    assert len(s.world.yuedan) == 2


def test_the_model_lines_replace_the_fixed_ones(c):
    s = _season(c)
    s.world.yuedan = [yuedan.YuedanEntry(week=2, name="甲", board="名人", line="固定句", at=0.0)]
    note = yuedan.request(s, c)
    assert yuedan.clean("治世之能臣，亂世之奸雄") == "治世之能臣，亂世之奸雄"
    assert yuedan.clean("太短") == "" and yuedan.clean("一二三四五六七八九十一二三四五六七八九") == ""
    assert yuedan.clean("甲乃天下英雄也", "甲") == ""  # 不寫名號本身
    assert yuedan.apply(s, c, note, {"甲": "少有大志，可託大事"})
    assert s.world.yuedan[0].line == "少有大志，可託大事" and s.world.yuedan[0].published
    assert not yuedan.apply(s, c, note, {})  # 發過了


def test_the_review_writer_runs_outside_the_lock(monkeypatch):
    import server
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world

    content = server.CONTENT
    monkeypatch.setattr(content.config.figure_life, "enabled", True)
    game = Game.new(content, "測試")
    game.world.open_season(content, 0.0)
    game.client = type("Fake", (), {})()
    game.now = 0.0
    game.sync(0.0)
    game.state.world.yuedan = [yuedan.YuedanEntry(week=2, name="測試", board="名人", line="名動四方，一時無兩", at=0.0)]
    game._save_season()
    seen = []

    def write(client, note):
        seen.append(open_world().db.writing())
        return {"測試": "少年英發，前程無量"}

    monkeypatch.setattr(yuedan, "write", write)
    assert server.yuedan_once(game)
    assert seen == [False]
    assert game.world.get_season().yuedan[0].line == "少年英發，前程無量"
    assert not server.yuedan_once(game)


# ── 求援委託 ──────────────────────────────────────────


def _anxious(s, c, fid: str) -> None:
    figures._ensure(s, c, fid).prestige = 1  # 聲威不到開季的一半：焦慮


def test_an_anxious_figure_calls_his_whole_side(c):
    c.config.figure_life.rally_chance = 1.0
    s = _season(c)
    _anxious(s, c, "qinjie")
    figure_life._maybe_rally(s, c, "qinjie", 1)
    assert len(s.world.rallies) == 1
    b = s.world.rallies[0]
    assert b.motive == "求援" and b.faction == "guan" and b.figure == "qinjie" and b.quota == c.config.figure_life.rally_quota
    assert bounties.title(c, b).startswith("求援・") and "護衛、犒軍秦頡" in bounties.how(c, b)
    assert any(r.layer == "faction" and r.faction == "guan" and "求援" in r.text for r in s.world.rumors)
    figure_life._maybe_rally(s, c, "qinjie", 2)  # 一次一件
    assert len(s.world.rallies) == 1
    assert b not in s.world.bounties  # 不上懸賞榜


def test_a_rally_rumor_says_practice_or_sortie_where_precise_is_on():
    """FB-435：一類一顆的季，求援的陣營傳聞寫「尋敵或出陣攻打贏」（以前寫練功），不寫找素材撞上（那種季找素材不打仗）；沒蓋章的季照舊。"""
    from tianxia.world_state import stamp_season

    c = real_content("week7")  # 有地盤、有出陣的季

    c.config.figure_life.rally_chance = 1.0
    for precise_on in (True, False):
        s = _season(c)
        stamp_season(s.world, c)
        s.world.precise_actions = precise_on
        _anxious(s, c, "qinjie")
        figure_life._maybe_rally(s, c, "qinjie", 1)
        b = s.world.rallies[0]
        assert b.kind == "strike"
        text = next(r.text for r in s.world.rumors if r.layer == "faction" and "求援" in r.text)
        if precise_on:
            assert "或出陣攻打贏" in text and "找素材" not in text  # 減法季探索一顆開著：寫「出門探索或出陣攻打贏」
        else:
            assert "找素材撞上" in text


def test_only_his_side_sees_it_and_the_first_three_get_paid(c):
    c.config.figure_life.rally_chance = 1.0
    s = _season(c)
    _anxious(s, c, "qinjie")
    figure_life._maybe_rally(s, c, "qinjie", 1)
    b = s.world.rallies[0]
    assert bounties.rallies(s, c) == []  # 散人看不到
    s.player.faction = "huang"
    assert bounties.rallies(s, c) == []
    s.player.faction = "guan"
    assert bounties.rallies(s, c) == [b]
    assert any(row.get("commission") and row["title"].startswith("求援・") for row in bounties.status(s, c, None))
    silver = s.player.stats.get("silver", 0)
    msgs = (bounties.on_win(s, c, None, b.location, b.squad) if b.kind == "strike" else bounties.on_explore(s, c, None, b.location))
    assert any("求援你辦成了" in m for m in msgs)
    assert s.player.stats["silver"] == silver + c.config.figure_life.rally_silver
    assert s.player.affinities["qinjie"] == c.config.figure_life.rally_affinity
    assert s.player.letters[-1].kind == "道謝"
    assert bounties.rallies(s, c) == []  # 辦過了
    b.done_by += ["乙", "丙"]
    s.player.name = "丁"
    assert bounties.rallies(s, c) == []  # 名額滿了


def test_guarding_or_rallying_him_counts(c):
    c.config.figure_life.rally_chance = 1.0
    s = _season(c)
    _anxious(s, c, "qinjie")
    figure_life._maybe_rally(s, c, "qinjie", 1)
    s.player.faction = "guan"
    assert any("求援你辦成了" in m for m in bounties.on_aid(s, c, "qinjie"))
    assert bounties.on_aid(s, c, "qinjie") == []


def test_a_calm_figure_does_not_call(c):
    c.config.figure_life.rally_chance = 1.0
    s = _season(c)
    figure_life._maybe_rally(s, c, "qinjie", 1)
    assert s.world.rallies == []
    c.config.figure_life.rallies = False
    _anxious(s, c, "qinjie")
    figure_life._maybe_rally(s, c, "qinjie", 1)
    assert s.world.rallies == []
