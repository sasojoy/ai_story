"""宴客（功能包 tianxia/features/feast/；大勢人物擴充第三批「大家一起」，Joy 2026-10-19「第三批開始做」）。
原本是 tests/figures/test_figure_life_batch3.py 的「宴客」那一段（開發規範手冊 4.6：測試跟著包走；測試本身一個字不改，
開頭的 fixture 與兩個小工具照那個檔抄一份）。用真實內容（content/，figure_life 預設開著）；每個測試拿自己的一份複本。"""
from __future__ import annotations

import pytest

from conftest import real_content
from tianxia import feasts, figure_life, letters
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


@pytest.mark.smoke
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
