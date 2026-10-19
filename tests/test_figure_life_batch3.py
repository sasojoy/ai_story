"""大勢人物擴充第三批「大家一起」（Joy 2026-10-19「第三批開始做」）：宴客（feasts）、月旦評（yuedan）、求援委託
（bounties 的 rallies）。用真實內容（content/，figure_life 預設開著）；每個測試拿自己的一份複本。"""
from __future__ import annotations

import pytest

from conftest import real_content
from tianxia import bounties, calendar, feasts, figure_life, figures, letters, yuedan
from tianxia.state import Feast, GameState, PlayerState, Toast
from tianxia.world_state import fresh_season


@pytest.fixture
def c():
    return real_content()


def _season(content, location: str | None = None) -> GameState:
    player = PlayerState(name="甲", location=location or content.scenario.start_location, stats={}, stamina=0)
    return GameState(player=player, world=fresh_season(content))


def _feast(s: GameState, host: str = "xushao", place: str | None = None) -> Feast:
    s.world.feast_seq += 1
    f = Feast(id=s.world.feast_seq, host=host, place=place or s.player.location, start=s.world.time,
              end=s.world.time + 2 * feasts.HOUR)
    s.world.feasts.append(f)
    return f


# ── 宴客 ──────────────────────────────────────────────


def test_a_figure_opens_a_feast_when_the_roll_hits(c):
    c.config.figure_life.feast_chance = 1.0
    s = _season(c)
    feasts.maybe_open(s, c, "xushao", 1)
    assert len(s.world.feasts) == 1
    f = s.world.feasts[0]
    assert f.host == "xushao" and f.place == figure_life.where(s, c, "xushao")
    assert any("設宴" in r.text for r in s.world.rumors)
    feasts.maybe_open(s, c, "xunyu", 1)  # 同時最多一場
    assert len(s.world.feasts) == 1
    s.world.time = f.end + 1
    feasts.settle(s, c)
    feasts.maybe_open(s, c, "xunyu", 2)  # 上一場開席之後 feast_gap_hours 內不再開
    assert len(s.world.feasts) == 1


def test_the_feast_roll_misses_at_zero(c):
    c.config.figure_life.feast_chance = 0.0
    s = _season(c)
    feasts.maybe_open(s, c, "xushao", 1)
    assert s.world.feasts == []


def test_toasting_warms_the_host_by_the_score(c):
    s = _season(c)
    f = _feast(s)
    assert feasts.toast_problem(s, c, f) is None
    msgs = feasts.toast(s, c, f, "好酒", 100, fixed=False)
    assert s.player.affinities["xushao"] == c.config.figure_life.feast_affinity_max
    assert any("情誼 +" in m for m in msgs)
    assert feasts.toast_problem(s, c, f) == feasts.TOASTED_BEFORE  # 一人一場一句
    assert feasts.affinity_of(c, 0) == 1 and feasts.affinity_of(c, feasts.FIXED_SCORE) == 2


def test_away_from_the_feast_you_cannot_toast(c):
    s = _season(c)
    f = _feast(s, place=next(x for x in c.locations if x != s.player.location))
    assert feasts.toast_problem(s, c, f) == feasts.NOT_HERE
    s.world.time = f.end
    assert feasts.toast_problem(s, c, f) == feasts.GONE


def test_the_best_toast_goes_out_and_its_author_gains_fame(c):
    s = _season(c)
    f = _feast(s)
    f.toasts += [Toast(name="乙", text="平平", score=40, at=1.0), Toast(name="甲", text="妙語", score=90, at=2.0),
                 Toast(name="丙", text="也妙", score=90, at=3.0)]
    s.world.time = f.end
    feasts.settle(s, c)
    assert f.settled and f.best == "甲"  # 一樣高看先說的
    assert any("妙語" in r.text for r in s.world.rumors)
    fame = s.player.stats.get("fame", 0)
    assert feasts.deliver(s, c)
    assert s.player.stats["fame"] == fame + c.config.figure_life.feast_fame
    assert feasts.deliver(s, c) == []  # 只領一次


def test_an_empty_feast_closes_quietly(c):
    s = _season(c)
    f = _feast(s)
    s.world.time = f.end
    feasts.settle(s, c)
    assert f.settled and not f.best
    assert all(r.layer == "local" for r in s.world.rumors)


def test_a_friend_hosting_sends_an_invitation(c):
    s = _season(c)
    loc = next(x for x in c.locations if x != s.player.location)
    _feast(s, place=loc)
    s.player.affinities["xushao"] = 40
    msgs = letters.deliver(s, c)
    assert msgs and s.player.letters[-1].kind == "邀宴"
    s.player.letter_day = -1
    assert letters.deliver(s, c) == [] or s.player.letters[-1].kind != "邀宴"  # 同一場不邀兩次


def test_the_score_model_is_clamped_and_falls_back(c):
    s = _season(c)
    f = _feast(s)
    req = feasts.request(s, c, f, "敬天下")
    assert feasts.score(None, req) == feasts.DEFAULT_SCORE

    class Fake:
        def chat_structured(self, messages, model, **kw):
            return model(score=250)

    assert feasts.score(Fake(), req) == 100


def test_the_game_seats_you_and_takes_a_fixed_toast(monkeypatch):
    import server
    from tianxia.engine import Game

    content = server.CONTENT
    monkeypatch.setattr(content.config.figure_life, "enabled", True)
    game = Game.new(content, "測試")
    game.world.open_season(content, 0.0)
    game.state.player.tutorial_step = len(content.tutorial.steps)
    game.now = 0.0
    game.sync(0.0)
    f = _feast(game.state)
    game._save_season()
    ids = [o.id for o in game.options()]
    assert f"feast:join:{f.id}" in ids
    game.choose(f"feast:join:{f.id}")
    menu = [o.id for o in game.options()]
    assert menu[:3] == ["feast:toast:0", "feast:toast:1", "feast:toast:2"] and "feast:leave" in menu
    assert game.feast_free_text_prompt() == feasts.FREE_PROMPT
    assert "的宴席" in game.scene_text()
    game.choose("feast:toast:1")
    assert game.state.player.feasting is None
    assert game.state.player.affinities["xushao"] == feasts.affinity_of(content, feasts.FIXED_SCORE)
    joined = next(o for o in game.options() if o.id == f"feast:join:{f.id}")
    assert not joined.enabled  # 敬過了


def test_writing_your_own_toast_is_scored_outside_the_lock(monkeypatch):
    import server
    from tianxia.characters import open_characters
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world

    content = server.CONTENT
    monkeypatch.setattr(content.config.figure_life, "enabled", True)
    import time

    game = Game.new(content, "測試")
    game.world.open_season(content, time.time())  # feast_text 照現實時間同步：開季在此刻，宴才還擺著
    game.state.player.tutorial_step = len(content.tutorial.steps)
    game.client = type("Fake", (), {})()
    game.sync(time.time())
    f = _feast(game.state)
    game._save_season()
    game.state.player.feasting = f.id
    open_characters().save(game.state)
    view = server.main_view(game)
    assert view["free_op"] == "feast_text" and view["free_text"] == feasts.FREE_PROMPT
    seen = []

    def score(client, req):
        seen.append(open_world().db.writing())
        return 90

    monkeypatch.setattr(feasts, "score", score)
    msgs = server.feast_text(game, "願天下太平")
    assert seen == [False]
    assert any("情誼 +" in m for m in msgs)
    assert game.state.player.affinities["xushao"] == feasts.affinity_of(content, 90)
    assert game.world.get_season().feasts[-1].toasts[-1].text == "願天下太平"


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
