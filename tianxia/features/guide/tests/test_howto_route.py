"""/api/howto 搬進新手引導包（全部拆包第 59 批）之後：殼照 FEATURES 掛得到，回的就是這個角色的 howto_text 轉成 HTML。"""
from __future__ import annotations

from fastapi.testclient import TestClient

import server
from tianxia.content import load_content


def test_the_howto_route_lives_in_the_guide_package_and_serves_the_page(monkeypatch):
    content = load_content(server.ROOT / "content")
    content.config.auto_open_first_season = True
    monkeypatch.setattr(server, "CONTENT", content)
    client = TestClient(server.app)
    assert client.get("/api/howto").status_code != 404  # 沒登入照舊回殼的那一句，不是找不到
    client.post("/api/register", json={"login": "howto_route", "password": "secret-pw", "again": "secret-pw"})
    client.post("/api/character", json={"name": "問路人"})
    got = client.get("/api/howto")
    assert got.status_code == 200
    assert got.json() == {"text": server.md(server.game_for("問路人").howto_text())}
    assert "<h4>行動</h4>" in got.json()["text"]
