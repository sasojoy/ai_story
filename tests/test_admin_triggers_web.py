"""管理者觸發鈕的伺服器路由與網頁（brief 2026-10-07-管理者觸發鈕）：

- 路由：每一顆鈕走 /api/do/<op>（管理者以外 400「只有管理者能這麼做。」），查玩家個人劇情走 /api/admin/player（管理者以外 403）。
- 網頁：設定抽屜的管理者工具只在管理者的畫面上畫新的鈕；按了先問一次，確定才送到對的路由（照 tests/test_prologue_web.py 的做法把整支
  app.js 放進 node 的假瀏覽器跑；沒有 node 就略過那幾個）。

伺服器用正式內容的週末設定（第一季的規則開著）、自己的一份（不碰別的測試的 server.CONTENT）。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_prologue_web import run

import server
import webharness
from conftest import real_content
from tianxia import accounts
from tianxia.characters import open_characters

needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
ADMIN = "掌門"


@pytest.fixture(autouse=True)
def weekend_server(monkeypatch):
    """server.CONTENT 換成這個測試自己的一份週末設定（季自己開、「掌門」是管理者）；伺服器記憶體裡的登入與角色從空的開始。"""
    content = real_content("weekend")
    content.config.auto_open_first_season = True
    content.config.train_event_chance = 0.0
    content.config.admins = [ADMIN]
    monkeypatch.setattr(server, "CONTENT", content)
    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})  # 這裡測的不是密碼
    monkeypatch.setattr(server, "_breaker_until", None, raising=False)
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    yield content
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()


@pytest.fixture
def client():
    return TestClient(server.app)


def _admin(client):
    """管理者的帳號（主機端腳本綁的，照 tests/test_server.py 的 _admin）登入；回傳他的 Game。"""
    boss = server.open_game(ADMIN)
    open_characters().save(boss.state)
    store = server.account_store()
    store.register("boss", "secret-pw")
    store.bind_character("boss", ADMIN)
    client.post("/api/login", json={"login": "boss", "password": "secret-pw"})
    return server.game_for(ADMIN)


def _player(client, login="shen_01", name="沈青衫"):
    client.post("/api/register", json={"login": login, "password": "secret-pw", "again": "secret-pw"})
    client.post("/api/character", json={"name": name})
    client.post("/api/do/skip_tutorial", json={})
    return server.game_for(name)


NEW_OPS = (
    ("issue_orders", {}), ("rotate_seats", {}),
)


# ── 路由 ─────────────────────────────────────────────


def test_players_are_refused_at_the_route(client):
    game = _player(client)
    before = game.world.get_season().model_dump()
    for op, body in NEW_OPS:
        out = client.post(f"/api/do/{op}", json=body)
        assert out.status_code == 400 and out.json() == {"error": "只有管理者能這麼做。"}, op
    assert game.world.get_season().model_dump() == before


def test_weekly_ops_reach_the_engine(client):
    game = _admin(client)
    assert client.get("/api/admin").json()["season_one"] is True
    out = client.post("/api/do/issue_orders", json={}).json()
    assert "已照週一的做法重發第 1 週的軍令" in out["message"]
    assert any(o.week == 1 for o in game.world.get_season().orders)
    out = client.post("/api/do/rotate_seats", json={}).json()
    assert "第 1 週沒有上一週的貢獻可排" in out["message"]


# ── 網頁 ─────────────────────────────────────────────


def _views(client):
    game = _admin(client)
    main = server.look(game, server.main_view)
    return game, main, client.get("/api/admin").json()


@needs_node
def test_the_new_controls_are_drawn_only_for_admins(client):
    _, main, admin = _views(client)
    sheet = run(main, "return H.sheetHtml();", S={"admin": admin})
    for text in ('data-op="issue_orders"', 'data-op="rotate_seats"', "立刻發本週軍令", "立刻輪替第 4 階席次"):
        assert text in sheet, text
    player = run({**main, "admin": False}, "return H.sheetHtml();", S={"admin": admin})
    for text in ("管理者工具", "issue_orders", "rotate_seats"):
        assert text not in player, text
    beta = run(main, "return H.sheetHtml();", S={"admin": {**admin, "season_one": False}})
    assert "issue_orders" not in beta  # 開關關著：沒有每週的事


CLICK = """return (async () => {
  T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
  const target = (dataset) => ({ dataset, classList: { contains: () => false, add() {}, remove() {} } });
  const click = (dataset) => T.docListeners.click[0]({ target: { closest: () => target(dataset) } });
  const asked = [];
  for (const dataset of input.clicks) {
    await click(dataset);
    asked.push(T.bodyHtml.length ? T.bodyHtml[T.bodyHtml.length - 1] : "");
    await click({ act: "ask-yes" });
  }
  return { asked, calls: T.calls.map((c) => [c[0], c[1]]) };
})();"""


def _click(main, admin, clicks, responses, S=None):
    import json

    script = CLICK.replace("input.clicks", json.dumps(clicks, ensure_ascii=False))
    return run(main, script, S={"admin": admin, "sheet": True, **(S or {})}, responses=responses)


@needs_node
def test_weekly_buttons_ask_then_post_to_their_routes(client):
    _, main, admin = _views(client)
    done = {"main": main, "message": "好了"}
    out = _click(main, admin, [{"act": "admin", "op": "issue_orders"}, {"act": "admin", "op": "rotate_seats"}],
                 {"/api/do/": done})
    assert "立刻發本週軍令" in out["asked"][0] and "立刻輪替第 4 階席次" in out["asked"][1]
    posts = [c for c in out["calls"] if c[0].startswith("/api/do/")]
    assert [c[0] for c in posts] == ["/api/do/issue_orders", "/api/do/rotate_seats"]
