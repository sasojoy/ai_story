"""全服池上限到了通知管理者（帳號與客服第 208 批；第 203 批留下的；設計 4.6）：codes.send 的 check_all_and_record 回了滿的那一格，
是全服池（pool: 開頭）才通知：旁檔 cap_alerts 記一筆（同一格一小時一次）、經 shell.WEB_PUSH 推給管理者名單上的帳號（None 跳過）、
管理頁 /api/admin 多一格 identity_alerts（這 24 小時內每格一行；identity 關著、沒有通知都沒有這個鍵）。回給寄碼的人的位元組不變。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_identity_server import fresh_server, key_file  # noqa: F401
from test_identity_session import clock, on, register, send, side_rows  # noqa: F401

import server
from tianxia.features.identity import alerts, senders


class FakePush:
    def __init__(self):
        self.sent = []

    def send(self, account, title, body, *, tag="", url="/", now=None, endpoint=None):
        self.sent.append((account, title, body, tag))
        return 1


@pytest.fixture
def capped(clock, monkeypatch):
    cfg = server.CONTENT.config.identity
    monkeypatch.setattr(cfg, "sms_caps", {"login": [400, 100], "bind": [300, 75], "anon": [100, 1]})  # 沒綁的新號碼一小時一則
    push = FakePush()
    monkeypatch.setattr(server, "WEB_PUSH", push)
    admin = TestClient(server.app)
    register(admin, "admin_01", name="沈管事")  # 玩家不能取管理者的名號：先建角色再放上名單
    monkeypatch.setattr(server.CONTENT.config, "admins", ["沈管事"])
    return push, admin


def test_pool_full_reply_same_and_admin_pushed_once_an_hour(capped, clock):
    push, _admin = capped
    first = send(TestClient(server.app), to="0911111111")
    full = send(TestClient(server.app), to="0922222222")
    assert full.status_code == first.status_code == 200 and full.content == first.content
    assert len(senders.FAKES.sms.outbox) == 1  # 第二則沒寄
    assert side_rows("SELECT bucket FROM cap_alerts") == [("pool:phone:anon:hour",)]
    assert push.sent == [("admin_01", server.NOTICE_TITLE, alerts.line("pool:phone:anon:hour", clock.now), "identity")]
    clock.now += 1800
    send(TestClient(server.app), to="0933333333")
    assert len(push.sent) == 1  # 一小時內同一格不再推
    clock.now += 1801
    send(TestClient(server.app), to="0944444444")  # 前一則出了一小時的窗：寄得出去，不通知
    send(TestClient(server.app), to="0955555555")  # 又滿了：過了一小時，再推一次
    assert len(push.sent) == 2


def test_web_push_none_does_not_break(capped, monkeypatch):
    monkeypatch.setattr(server, "WEB_PUSH", None)
    send(TestClient(server.app), to="0911111111")
    r = send(TestClient(server.app), to="0922222222")
    assert r.status_code == 200
    assert side_rows("SELECT bucket FROM cap_alerts") == [("pool:phone:anon:hour",)]


def test_only_pool_buckets_alert(capped):
    push, _admin = capped
    c = TestClient(server.app)
    send(c, to="0911111111")
    monkeypatch_caps = server.CONTENT.config.identity.sms_caps
    monkeypatch_caps["anon"] = [100, 50]
    assert send(c, to="0911111111").status_code == 200  # 一號 60 秒內第二次：滿的是 resend 那一格
    assert side_rows("SELECT bucket FROM cap_alerts") == [] and push.sent == []


def test_admin_page_line_only_when_on(capped, monkeypatch, clock):
    _push, admin = capped
    before = admin.get("/api/admin").json()
    assert "identity_alerts" not in before
    send(TestClient(server.app), to="0911111111")
    send(TestClient(server.app), to="0922222222")
    data = admin.get("/api/admin").json()
    assert data["identity_alerts"] == [alerts.line("pool:phone:anon:hour", clock.now)]
    assert list(data)[-1] == "identity_alerts" and list(data)[:-1] == list(before)  # 表外格接在表尾，其餘的鍵不動
    assert "identity_alerts" not in admin.get("/api/main").json()
    monkeypatch.setattr(server.CONTENT.config.identity, "enabled", False)
    assert "identity_alerts" not in admin.get("/api/admin").json()
    clock.now += 86400 + 1
    monkeypatch.setattr(server.CONTENT.config.identity, "enabled", True)
    admin.get("/api/main")  # /api/admin 是 look（不同步）：「現在」是這個角色上一次同步的 Game.now
    assert "identity_alerts" not in admin.get("/api/admin").json()  # 24 小時前的不列


def test_line_words():
    assert alerts.line("pool:phone:anon:hour", 0) is not None
    assert alerts.line("resend:phone:x", 0) is None
    for channel in alerts.CHANNEL:
        for pool in alerts.POOL:
            for span in alerts.SPAN:
                text = alerts.line(f"pool:{channel}:{pool}:{span}", 0)
                assert alerts.CHANNEL[channel] in text and alerts.POOL[pool] in text and alerts.SPAN[span] in text
