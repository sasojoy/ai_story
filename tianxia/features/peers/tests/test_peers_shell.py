"""peers 這一包的測試，從 tests/server/test_server.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import random
import pytest
from fastapi.testclient import TestClient
import server
from tianxia.features.peers import social
from tianxia.characters import open_characters
from tianxia.engine import Game
from tianxia.ollama_client import OllamaClient
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, _player, cheap_password_hashing, client, fresh_server_memory, game,
    model_breaker_closed, save_dir, scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content


# ── 玩家之間的互動（第一層）────────────────────────────────


def test_two_players_in_the_same_place_see_each_other_and_open_a_card(client):
    """兩個人都略過序章、站在同一個起點：江湖畫面的 here 列出對方（陣營括號），/api/peer 給玩家卡；人不在了 card 是 None。"""
    _player(client, "shen_01", "沈青衫")
    other = TestClient(server.app)
    _player(other, "lin_01", "林小竹")
    here = client.get("/api/main").json()["here"]
    assert here == [{"name": "林小竹", "side": "散人"}]
    got = client.get("/api/peer", params={"name": "林小竹"}).json()
    assert got["card"]["name"] == "林小竹" and got["card"]["level"] >= 1 and isinstance(got["card"]["actions"], list)
    assert client.get("/api/peer", params={"name": "沒這個人"}).json() == {"card": None, "gone": social.GONE}
    out = client.post("/api/peer/act", json={"name": "林小竹", "action": "no-such", "amount": "x"}).json()
    assert "沒有這個動作" in out["message"] and out["card"]["name"] == "林小竹"


def test_a_greeting_and_a_gift_go_through_the_endpoints(client):
    """第二層：甲向乙挑釁（附一句話）、送素材；乙的江湖畫面 calls 有那一行，按回應鈕之後兩邊都清掉。"""
    _player(client, "shen_02", "沈青衫")
    other = TestClient(server.app)
    _player(other, "lin_02", "林小竹")
    out = client.post("/api/peer/act", json={"name": "林小竹", "action": "greet", "arg": "taunt", "text": "改天見識見識"}).json()
    assert "你向林小竹斜眼打量，出言挑釁：「改天見識見識」" in out["message"]
    state = open_characters().load("沈青衫")
    state.player.materials = {next(iter(server.CONTENT.materials)): 5}
    open_characters().save(state)
    mid = next(iter(server.CONTENT.materials))
    gift = client.post("/api/peer/act", json={"name": "林小竹", "action": "gift", "arg": "material", "choice": mid, "amount": 2}).json()
    assert "送給了林小竹" in gift["message"]
    [call] = other.get("/api/main").json()["calls"]
    assert call["text"] == "沈青衫斜眼打量你，出言挑釁：「改天見識見識」"
    other.post("/api/choose", json={"id": call["options"][0]["id"]})
    main = other.get("/api/main").json()
    assert main["calls"] == [] and main["party"] is None
    assert any("冷眼以對" in line for e in open_characters().load("沈青衫").journal for line in e.lines)
    left = other.post("/api/party/leave", json={}).json()
    assert "沒有跟著誰" in left["message"]


def test_fb245_answering_a_discussion_while_he_is_busy_does_not_call_the_model(content, world, client, monkeypatch):
    """FB-245：/api/peer/act 答應論武，發邀請的那個人正忙（這一張邀請已經成不了）：prepare_peer 的 A 段不開取名單子，模型一次都不叫，
    直接回「他此刻正忙」那一句、邀請作廢；他閒下來之後再邀、再答，照舊叫一次模型取名。測試內容的兩個角色（同 test_discuss），
    端點的拿鎖、存檔那一套（act、look、_open_request）換成直接做，prepare_peer、peer_act 照真的走。"""
    from test_discuss import NAME, NOW, CountingClient, _change, _invite, _load, _make

    from conftest import install_season_one
    from tianxia.characters import CharacterStore

    monkeypatch.setattr(OllamaClient, "from_config", classmethod(lambda cls, cfg: None))  # 不准碰模型的 port
    install_season_one(content)
    content.config.auto_open_first_season = True
    _make(content, world, "甲", insights=("feng",))
    _make(content, world, "乙", wugong="fist", insights=("huo",))
    _invite(content, world, item="insight:feng")  # 甲出「風」；乙出「火」是新配方（合併），成得了就要取名
    _change(world, "甲", lambda p: setattr(p, "busy_until", 1e9))  # 閉關中：選單上沒有探索，同進了鐵匠鋪
    fake = CountingClient()
    game = Game(content, CharacterStore(world.db).load("乙"), random.Random(0), world)
    game.client = fake
    game.sync(NOW)
    monkeypatch.setattr(server, "_game", lambda request: game)
    monkeypatch.setattr(server, "act", lambda g, action, **k: action(g))
    monkeypatch.setattr(server, "look", lambda g, view: view(g) if view is not server.main_view else None)
    monkeypatch.setattr(server, "_open_request", lambda g, open_it: (server._monotonic(), open_it()))
    monkeypatch.setattr(server, "_tell_tabs", lambda g: None)
    answer = {"name": "甲", "action": "discuss", "arg": "yes:insight:huo"}
    r = client.post("/api/peer/act", json=answer).json()
    assert fake.calls == [] and r["brief"] == "甲此刻正忙，騰不出手來論武。" and r["message"] == f"<p>{r['brief']}</p>\n"
    assert world.get_season().invites == [] and _load(world, "甲").journal[0].title == "論武不成・乙"
    _change(world, "甲", lambda p: setattr(p, "busy_until", None))  # 他閒下來了：再邀、再答，這一次照舊取名
    game.state.world = world.get_season()
    _invite(content, world, item="insight:feng")
    game.state.world = world.get_season()
    r = client.post("/api/peer/act", json=answer).json()
    assert len(fake.calls) == 1 and NAME[0] in r["message"]
