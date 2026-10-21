"""FB-609（QA 驗輿圖第三版第 1 批）：玩家下戰書的 API 被管理者的同名動作蓋掉，沒有一個玩家下得了戰書。

server.MAIN_ACTIONS 與 ADMIN_ACTIONS 都有 conquest_letter（玩家的 Game.conquest_letter、管理者的「立刻下戰書」），/api/do/{op} 先查
ADMIN_ACTIONS：在任第 4 階的玩家打 POST /api/do/conquest_letter 回 400「只有管理者能這麼做。」。修法（PM 2026-10-21）：管理者那一個改名
admin_conquest_letter（同 Game.admin_conquest_letter），兩張表不准重名。

伺服器用正式內容的 21 天季、打開領地爭奪，自己的一份（不碰別的測試的 server.CONTENT）。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import server
from conftest import real_content
from conquest_kit import conquest_rules
from tianxia import accounts, conquest
from tianxia.characters import open_characters

pytestmark = pytest.mark.slow  # 開伺服器、載正式內容

ADMIN = "掌門"
PLAYER = "沈青衫"
# /api/do 在查 MAIN_ACTIONS 之前先接走的那幾個（server.api_do）：管理者的動作也不能叫這幾個名字
SPECIAL_OPS = {"battle_text", "seal_text", "duel_text", "tavern_ask", "feast_text", "gather_text"}


@pytest.fixture(autouse=True)
def conquest_server(monkeypatch):
    content = conquest_rules(real_content("season21"))
    content.config.auto_open_first_season = True
    content.config.admins = [ADMIN]
    monkeypatch.setattr(server, "CONTENT", content)
    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})  # 這裡測的不是密碼
    monkeypatch.setattr(server, "_breaker_until", None, raising=False)
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    yield content
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()


def _player(client):
    client.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    client.post("/api/character", json={"name": PLAYER})
    client.post("/api/do/skip_tutorial", json={})
    return server.game_for(PLAYER)


def _seated_rank4(content):
    """存檔裡的這個玩家改成官軍、站在荒丘、這一週在任的第 4 階；官軍在荒丘的進度推到戰書的門檻。"""
    state = open_characters().load(PLAYER)
    p = state.player
    p.faction, p.location, p.journey, p.qualified = "guan", "hilltop_wilds", None, True
    p.visited.add("hilltop_wilds")
    open_characters().save(state)
    game = server.game_for(PLAYER)

    def _season(s):
        s.seats["guan"] = [PLAYER]
        conquest.push(s, content, "hilltop_wilds", "guan", "先鋒", content.config.conquest.letter_at, "attack")

    game.world.mutate_season(_season)


def _admin(client):
    boss = server.open_game(ADMIN)
    open_characters().save(boss.state)
    store = server.account_store()
    store.register("boss", "secret-pw")
    store.bind_character("boss", ADMIN)
    client.post("/api/login", json={"login": "boss", "password": "secret-pw"})
    return server.game_for(ADMIN)


def test_a_seated_rank4_player_letters_through_the_route(conquest_server):
    client = TestClient(server.app)
    _player(client)
    _seated_rank4(conquest_server)
    out = client.post("/api/do/conquest_letter", json={"loc": "hilltop_wilds"})
    assert out.status_code == 200, out.json()  # 修前 400「只有管理者能這麼做。」
    assert "下了戰書" in out.json()["message"]
    season = server.game_for(PLAYER).world.get_season()
    (slot,) = season.conquest.schedule
    assert (slot.loc, slot.attackers, slot.reasons) == ("hilltop_wilds", ["guan"], {"guan": PLAYER})


def test_the_admin_letter_has_its_own_name_and_players_are_refused(conquest_server):
    player = TestClient(server.app)
    _player(player)
    refused = player.post("/api/do/admin_conquest_letter", json={"id": "runan_wilds", "side": "huang"})
    assert refused.status_code == 400 and refused.json() == {"error": "只有管理者能這麼做。"}
    boss = TestClient(server.app)
    _admin(boss)
    done = boss.post("/api/do/admin_conquest_letter", json={"id": "runan_wilds", "side": "huang"})
    assert done.status_code == 200, done.json()
    assert "汝南荒野" in done.json()["message"]
    (slot,) = server.game_for(ADMIN).world.get_season().conquest.schedule
    assert (slot.loc, slot.attackers) == ("runan_wilds", ["huang"])


def test_player_and_admin_action_names_never_collide():
    """/api/do 先查管理者那一張：同名的玩家動作永遠走不到（FB-609）。兩張表、以及 api_do 先接走的那幾個，名字都不能重。"""
    assert set(server.MAIN_ACTIONS) & set(server.ADMIN_ACTIONS) == set()
    assert set(server.ADMIN_ACTIONS) & SPECIAL_OPS == set()
    assert set(server.MAIN_ACTIONS) & SPECIAL_OPS == set()
    assert "admin_conquest_letter" in server.ADMIN_ACTIONS and "conquest_letter" in server.MAIN_ACTIONS
