"""sense 這一包的測試，從 tests/server/test_server.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
from unittest import mock
import pytest
import server
from tianxia import insights
from tianxia.engine import Game
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    _forger, _no_landing, _no_preset_recipes, _player, cheap_password_hashing, client, fresh_server_memory, game,
    model_breaker_closed, save_dir, scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content


# ── 有所感的畫布（悟意境設計 0.2、0.2a）────────────────────

def _into_draw(game):
    """把這個角色放進感悟狀態（選對做法、擲中了）：站到一個探索悟得到意境的地點，開一張有所感的卡。"""
    import random as _random

    from tianxia import insights
    from tianxia.features.sense import sensing

    def setup(g):
        loc = next(l for l in g.content.locations.values() if insights.explore_gives(l, g.content) and not l.prologue_only)
        g.state.player.location = loc.id
        scene = sensing.pick_scene(loc, g.content, _random.Random(0))
        sensing.start(g.state, g.content, scene, _random.Random(0))
        pool = insights.pool_attributes(loc, g.content)
        g.state.player.sensing.stage = "draw"
        g.state.player.sensing.method = next(m.attribute for m in scene.methods if m.attribute in pool)

    server.act(game, setup)


def _new_shape(game):
    """一筆會悟出自己新意境（要取名）的現成筆畫；這一處每一筆都落回基本意境時是 None。"""
    from tianxia.features.sense import glyph

    for points in glyph.SAMPLES.values():
        req = game.sense_request(points)
        if not isinstance(req, str) and req.needs_name:
            return points
    return None


def test_drawing_a_new_shape_asks_the_model_outside_the_lock_with_the_picture(client):
    _player(client)
    game = next(iter(server.GAMES.values()))
    _into_draw(game)
    main = client.get("/api/main").json()
    assert [o["id"] for o in main["options"]] == ["sense:draw", "sense:let"]
    points = _new_shape(game)
    assert points is not None
    seen = {}

    def fake_name(client_, content, facts, image="", budget=None, person=None):
        seen["image"], seen["locked"] = image, game.world.db.writing()
        return "湖心月", "如一泓靜水，綿柔不盡。", "看圖"

    with mock.patch.object(server.insight_llm, "name", fake_name):
        r = client.post("/api/sense", json={"points": points, "png": "AAAA"})
    assert r.status_code == 200
    assert seen == {"image": "AAAA", "locked": False}
    assert not any(o["id"].startswith("sense:") for o in r.json()["main"]["options"])
    own = game.state.player.own_insights
    assert [i.name for i in own.values()] == ["湖心月"] and list(own.values())[0].glyph
    assert list(own.values())[0].note == "如一泓靜水，綿柔不盡。"
    assert game.state.journal[0].title.startswith("有所感・")


def test_a_stroke_that_cannot_be_read_is_refused_and_keeps_the_state(client):
    _player(client)
    game = next(iter(server.GAMES.values()))
    _into_draw(game)
    r = client.post("/api/sense", json={"points": [[1, 1, 0]], "png": ""})
    assert r.status_code == 400 and "點了一下" in r.json()["error"]
    assert game.state.player.sensing is not None and game.state.player.sensing.stage == "draw"


def test_sending_a_stroke_without_sensing_is_refused(client):
    _player(client)
    from tianxia.features.sense import glyph

    assert client.post("/api/sense", json={"points": glyph.SAMPLES["剛"]}).status_code == 400


def test_the_canvas_line_reads_the_stroke_without_touching_the_game(client):
    _player(client)
    from tianxia.features.sense import glyph

    assert client.post("/api/sense_read", json={"points": glyph.SAMPLES["柔"]}).json() == {"ok": True}
    assert client.post("/api/sense_read", json={"points": "x"}).json()["problem"]


def test_the_canvas_warms_the_model(client):
    _player(client)
    with mock.patch.object(server.insight_llm, "warm", return_value=True) as warm:
        assert client.post("/api/sense_warm").json() == {"ok": True}
    warm.assert_called_once()


def test_epiphany_think_names_outside_the_lock(monkeypatch):
    """特殊頓悟的「靜心思名」走三段式：A 鎖內開單、B 鎖外請模型（model_call：在鎖裡被叫到會丟錯）、C 鎖內交回 Game.epiphany_names；不在等著取名照一般的按鈕走。"""
    from tianxia.features.sense import epiphany

    game = _forger()
    ask = epiphany.NameAsk("頓悟1", "god_x", [])
    seen = {}

    def propose(client, content, request, budget=None, person=None):
        seen["request"] = request
        return ["寒潭映月"]

    monkeypatch.setattr(Game, "epiphany_request", lambda self: ask)
    monkeypatch.setattr(epiphany, "propose_names", propose)
    monkeypatch.setattr(Game, "epiphany_names", lambda self, request, names: [f"{request.god}:{names[0]}"])
    assert server.choose(game, server.EPIPHANY_THINK) == ["god_x:寒潭映月"]
    assert seen["request"] is ask
    monkeypatch.setattr(Game, "epiphany_request", lambda self: None)
    monkeypatch.setattr(epiphany, "propose_names", mock.Mock(side_effect=AssertionError("不該叫模型")))
    server.choose(game, server.EPIPHANY_THINK)
