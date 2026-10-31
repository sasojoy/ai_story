"""減法季批 6 的伺服器那一半（主機側計畫 1.3 的 figure.stances、figure.errands、main.errands）：江湖畫面的 figure（正在跟他談的那一位）、
GET /api/figure、託付的 main.errands 與勸降的三段式（/api/do/persuade_text）。正式內容；模型一律是假的，不打 11434。"""
from __future__ import annotations

import random
from unittest import mock

import pytest
from fastapi.testclient import TestClient

import server
from tianxia import errands
from tianxia.characters import open_characters
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

LUZHI = "luzhi"


@pytest.fixture(autouse=True)
def _server_state(monkeypatch):
    """同 tests/test_outcomes_server.py：一季已經開打、排程不開、佇列關著、斷路器關著、伺服器記憶體從空的開始。"""
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)
    monkeypatch.setattr(server.CONTENT.config, "world_tick_seconds", 0)
    monkeypatch.setattr(server, "_breaker_until", None, raising=False)
    monkeypatch.setattr(server, "QUEUE", None)
    for store in (server.SESSIONS, server.GAMES, server.LOGIN_FAILURES):
        store.clear()
    yield
    for store in (server.SESSIONS, server.GAMES, server.LOGIN_FAILURES):
        store.clear()


def _jianfa(monkeypatch, on=True):
    monkeypatch.setattr(server.CONTENT.config.jianfa, "enabled", on)


def _talking(monkeypatch, on=True, name="測試") -> Game:
    """正式內容的伺服器上開一個站在盧植營、正在跟盧植談的官軍；on：減法季（總開關＋這一季的章）。"""
    _jianfa(monkeypatch, on)
    game = Game.new(server.CONTENT, name, rng=random.Random(0))
    game.client = None
    game.state.world.jianfa_on = on
    game._save_season()
    p = game.state.player
    p.location, p.faction = "luzhi_camp", "guan"
    p.pending_companion = LUZHI
    p.last_offered_dialogue[LUZHI] = [["勸他速攻廣宗", "告辭"], ["真誠請教", "尋常寒暄"]]
    open_characters().save(game.state)
    return game


def test_main_view_has_his_page_only_while_talking_to_him(monkeypatch):
    game = _talking(monkeypatch)
    view = server.main_view(game)
    figure = view["figure"]
    assert figure["id"] == LUZHI and figure["name"] == "盧植"
    assert [x["id"] for x in figure["stances"]] == ["suzhan", "chizhong", "xumin"] and figure["my_stance_today"] is None
    game.state.player.pending_companion = None
    assert "figure" not in server.main_view(game)


def test_closed_seasons_have_no_figure_key(monkeypatch):
    game = _talking(monkeypatch, on=False)
    assert "figure" not in server.main_view(game)


def test_main_view_lists_the_errands_only_when_on(monkeypatch):
    game = _talking(monkeypatch)
    game.state.player.affinities[LUZHI] = 50
    errands.give(game.state, game.content, LUZHI, "luzhi_scout")
    e = game.state.player.errands[-1]
    view = server.main_view(game)
    assert [r["id"] for r in view["errands"]] == [e.id] and view["errands"][0]["kind"] == "scout"
    assert view["figure"]["errands"][0]["id"] == e.id  # 人物頁也列他託的
    assert "errands" not in server.main_view(_talking(monkeypatch, on=False, name="測試二"))


def _persuading(monkeypatch, floor_cap=100):
    game = _talking(monkeypatch)
    monkeypatch.setattr(server.CONTENT.config.jianfa, "persuade_floor", floor_cap)
    monkeypatch.setattr(server.CONTENT.config.jianfa, "persuade_cap", floor_cap)
    p = game.state.player
    p.pending_companion, p.affinities[LUZHI] = None, 50
    errands.give(game.state, game.content, LUZHI, "luzhi_persuade")
    e = p.errands[-1]
    p.location = e.target
    open_characters().save(game.state)
    return game, e.id


def test_persuade_goes_through_three_stages(monkeypatch):
    """A 開單（只讀）→ B 鎖外評那一句（event_llm.rate_persuasion，假的）→ C 進鎖重驗、擲骰、立痕跡、獎勵。"""
    game, eid = _persuading(monkeypatch)
    asked = []

    def rate(client, request):
        asked.append((request.errand, request.text, request.who))
        return 70

    with mock.patch.object(server.event_llm, "rate_persuasion", side_effect=rate):
        server.persuade_text(game, eid, "放下刀槍回家種田")
    assert asked == [(eid, "放下刀槍回家種田", "下曲陽的黃巾小頭目")]
    assert errands.find(game.state, eid).status == "done" and game.state.world.marks["xiaquyang:band_turned"] == 1


def test_persuade_without_the_model_changes_nothing(monkeypatch):
    game, eid = _persuading(monkeypatch)
    stamina = game.state.player.stamina
    with mock.patch.object(server.event_llm, "rate_persuasion", return_value=None):
        msgs = server.persuade_text(game, eid, "放下刀槍回家種田")
    assert msgs == [errands.PERSUADE_SILENT]
    assert errands.find(game.state, eid).status == "open" and game.state.player.stamina == stamina


def test_persuade_refusals_never_call_the_model(monkeypatch):
    game, eid = _persuading(monkeypatch)
    with mock.patch.object(server.event_llm, "rate_persuasion", side_effect=AssertionError("A 段就擋下來，不叫模型")):
        assert server.persuade_text(game, eid, "") == [errands.PERSUADE_ASK]
        assert server.persuade_text(game, "e999", "放下刀槍") == [errands.NOT_HERE]


def test_get_api_figure_reads_his_page(monkeypatch):
    _jianfa(monkeypatch)
    client = TestClient(server.app)
    client.post("/api/register", json={"login": "fig_01", "password": "secret-pw", "again": "secret-pw"})
    client.post("/api/character", json={"name": "沈青衫"})
    client.post("/api/do/skip_tutorial", json={})
    open_world().mutate(lambda st: setattr(st.season, "jianfa_on", True))
    server.GAMES.clear()
    figure = client.get("/api/figure", params={"id": LUZHI}).json()["figure"]
    assert figure["name"] == "盧植" and len(figure["stances"]) == 3
    assert client.get("/api/figure", params={"id": "zhangjiao"}).json() == {"figure": None}  # 沒有心意也沒有託付
    assert client.get("/api/figure", params={"id": "nosuch"}).json() == {"figure": None}
