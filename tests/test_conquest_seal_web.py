"""領地爭奪第三批 B（計畫 Task 14）的網頁那一半：管理者「玉璽」一組，領地爭奪的季「強制現世」換成「現在藏一片」。
餵 Game.admin_seal_choices 給的 hide 旗標給 app.js（tests/test_seal_web.py 的假瀏覽器）。沒有 node 就略過。"""
from __future__ import annotations

import json

import pytest
from test_seal_web import DRIVER, _seal_admin, _sheet, m  # noqa: F401  m 是夾具

import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _admin(hide: bool) -> dict:
    admin = _seal_admin()
    admin["seal"]["hide"] = hide
    return admin


def test_the_admin_button_says_hide_now_in_a_conquest_season(m):  # noqa: F811
    sheet = _sheet(m, _admin(True))
    assert "現在藏一片" in sheet and 'data-op="seal_emerge" data-hide="1"' in sheet and "強制現世" not in sheet
    old = _sheet(m, _admin(False))
    assert "強制現世（下一場）" in old and "data-hide" not in old and "現在藏一片" not in old


def test_the_hide_button_asks_its_own_question_then_posts_the_same_route(m):  # noqa: F811
    from test_admin_triggers_web import CLICK

    clicks = [{"act": "admin", "op": "seal_emerge", "hide": "1"}, {"act": "admin", "op": "seal_emerge"}]
    script = CLICK.replace("input.clicks", json.dumps(clicks))
    out = webharness.run(DRIVER, {"m": {**m, "admin": True}, "script": script, "S": {"admin": _admin(True), "sheet": True},
                                  "menxia": None, "stored": {}, "responses": {"/api/do/": {"main": m, "message": "好了"}}})
    assert "藏進一塊開季中立的區塊" in out["asked"][0] and "不公開" in out["asked"][0] and "決戰" not in out["asked"][0]
    assert "現世" in out["asked"][1] and "下一場" in out["asked"][1]  # 舊的問句一個字沒動
    assert [c[0] for c in out["calls"] if c[0].startswith("/api/do/")] == ["/api/do/seal_emerge", "/api/do/seal_emerge"]
