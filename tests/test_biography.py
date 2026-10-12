"""玩家傳第二批：季末把行狀寫成《某某傳》（tianxia/biography.py、Game.biography_*）、背景寫傳與公開分享（server.py、zhuan_html.py）、
網頁的傳（web/app.js 的 zhuanHtml）。"""
from __future__ import annotations

import random
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
import webharness
import zhuan_html
from conftest import next_season
from tianxia import annals, biography
from tianxia.engine import Game

ROOT = Path(__file__).parent.parent


@pytest.fixture
def on(content):
    content.config.biography.enabled = True
    content.config.admins = ["管理者"]
    return content


def _game(content, world, name="沈浪"):
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    game.sync(0.0)
    return game


def _close(content, world, *players):
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    admin.admin_end_season(now=200.0)
    for p in players:
        p.sync(210.0)


def _request(**kw) -> biography.BiographyRequest:
    base = dict(
        season=1, name="沈浪", scenario="黃巾之亂", era_note="", profile={"level": 12, "faction": "官軍", "good": 9, "evil": 1},
        annals=(
            {"kind": "deed", "when": "第 1 週・週一 08:00", "text": "投靠官軍。", "weight": 4},
            {"kind": "showdown", "when": "第 6 週・週三 20:00", "text": "長社火攻，你站在官軍以先鋒出陣，出手 4 回合，在 12／30 人中排第 3／12。",
             "quote": "點火燒糧", "reply": "沈浪一把火燒了糧車", "weight": 5},
            {"kind": "figure", "when": "第2天 09:00", "text": "跟皇甫嵩的情誼到了 40。", "quote": "久仰", "reply": "好說。", "weight": 3},
        ),
    )
    base.update(kw)
    return biography.BiographyRequest(**base)


# ── 規則版、清理、數字 ──


def test_chinese_numbers():
    assert [biography._cn(n) for n in (0, 7, 10, 15, 20, 21, 105, 1200, 30000)] == [
        "〇", "七", "十", "十五", "二十", "二十一", "一百零五", "一千二百", "三〇〇〇〇"]


def test_the_rule_text_reads_like_a_biography_with_no_arabic_digits_and_no_you():
    text = biography.rule_text(_request())
    paras = text.split("\n\n")
    assert paras[0].startswith("沈浪者，") and paras[-1].startswith("評曰：")
    assert "第一週，投靠官軍。" in paras[0]
    assert "出手四回合" in text and "在十二人中排第三" in text and "沈浪曰：「點火燒糧」" in text
    assert not any(ch.isdigit() for ch in text if ch.isascii()) and "你" not in text
    assert "行事近俠" in text and "至第十二級" in text
    assert biography.clean(text, _request()) == text  # 規則版自己也過得了清理的檢查


def test_a_quiet_season_still_gets_a_biography():
    text = biography.rule_text(_request(annals=({"kind": "deed", "text": "拜入流雲派門下。", "weight": 4},), profile={}))
    assert "未嘗與於天下大戰" in text and "生逢黃巾之亂，" in text and text.count("\n\n") == 3


def test_clean_keeps_good_model_text_and_rejects_the_bad():
    req = _request()
    good = "# 沈浪傳\n\n**沈浪者**，潁川人也。" + "少負奇氣，" * 40 + "\n\n評曰：沈浪雖起於草莽，亦一時之選。"
    out = biography.clean(good, req)
    assert out.startswith("沈浪者，潁川人也。") and out.endswith("亦一時之選。") and "#" not in out and "*" not in out
    assert out.count("\n\n") == 1  # 標題那一行拿掉，剩兩段
    assert biography.clean("沈浪者，" + "简体字很多，" * 40, req).find("簡體") >= 0  # 轉成繁體
    assert biography.clean("太短了。沈浪", req) is None
    assert biography.clean("某人者，" + "無名，" * 100, req) is None  # 沒寫到名號
    assert biography.clean("沈浪者，" + "戰了3回合，" * 40, req) is None
    assert biography.clean("沈浪者，" + "ござる，" * 60, req) is None
    assert biography.clean(None, req) is None


def test_the_model_is_asked_with_the_facts_and_failures_fall_back_to_none():
    class Fake:
        timeout, retry = 99, True

        def __init__(self, reply):
            self.reply, self.asked = reply, None

        def chat_text(self, messages, **kw):
            self.asked = (messages, self.timeout, self.retry)
            if isinstance(self.reply, Exception):
                raise self.reply
            return self.reply

    req = _request(rewrite=True)
    fake = Fake("沈浪者，" + "起於潁川，" * 50)
    assert biography.write(fake, req, 30).startswith("沈浪者")
    assert fake.asked is None and fake.timeout == 99  # 原本那一份不動：叫的是複本
    msgs = biography.messages(req)
    assert "沈浪者，" in msgs[0]["content"] and "長社火攻" in msgs[1]["content"] and "【大戰】" in msgs[1]["content"]
    assert "換一種起筆" in msgs[1]["content"]
    assert biography.write(Fake(RuntimeError("down")), req, 30) is None
    assert biography.write(Fake("太短"), req, 30) is None
    assert biography.write(None, req, 30) is None and biography.write(fake, req, 0) is None


def test_lead_is_the_first_paragraph_clipped():
    assert biography.lead("甲乙。\n\n丙丁。") == "甲乙。"
    assert biography.lead("長" * 150, 100) == "長" * 99 + "…"


# ── 引擎：開單、寫、看、分享 ──


def test_nothing_can_be_written_while_the_season_runs_or_the_switch_is_off(on, world):
    game = _game(on, world)
    annals.note(game.state, on, annals.DEED, "投靠官軍。", 4)
    assert game.biography_request(1) is None and game.biography_entry() is None and game.biography_view(1) is None
    on.config.biography.enabled = False
    _close(on, world, game)
    assert game.biography_request(1) is None and game.biography_entry() is None


def test_a_closed_season_is_written_once_and_rewritten_once(on, world):
    game = _game(on, world)
    annals.note(game.state, on, annals.DEED, "投靠官軍。", 4)
    _close(on, world, game)
    assert game.biography_entry() == {"season": 1, "title": "沈浪傳"}
    assert game.annals_view()["books"] == [{"season": 1, "title": "沈浪傳", "written": False, "public": False}]
    view = game.biography_view(1)
    assert view["written"] is False and view["can_write"] is True
    assert game.biography_request(1, rewrite=True) is None  # 還沒寫過，不能重寫
    req = game.biography_request(1)
    assert req.annals[0]["text"] == "投靠官軍。" and req.profile["name"] == "沈浪"
    assert game.write_biography(req, None, 5.0) is True  # 模型寫不出來：照規則拼
    view = game.biography_view(1)
    assert view["written"] and view["by"] == biography.RULE and view["paragraphs"][0].startswith("沈浪者，")
    assert view["can_rewrite"] is True and view["public"] is False and view["code"] is None
    assert game.biography_request(1) is None  # 寫過了，不能再「寫」
    again = game.biography_request(1, rewrite=True)
    model_text = "沈浪者，" + "起於潁川，" * 50
    assert game.write_biography(again, model_text, 6.0) is True
    view = game.biography_view(1)
    assert view["by"] == biography.MODEL and view["paragraphs"] == [model_text] and view["can_rewrite"] is False
    assert game.biography_request(1, rewrite=True) is None and game.write_biography(again, model_text, 7.0) is False


def test_a_stale_request_is_dropped(on, world):
    game = _game(on, world)
    annals.note(game.state, on, annals.DEED, "投靠官軍。", 4)
    _close(on, world, game)
    req = game.biography_request(1)
    annals.note(game.state, on, annals.DEED, "又多了一件。", 4)  # 季收了之後才補進來的決戰
    assert game.write_biography(req, None, 5.0) is False and game.biography_view(1)["written"] is False


def test_sharing_hands_out_one_code_and_can_be_taken_back(on, world):
    game = _game(on, world)
    annals.note(game.state, on, annals.DEED, "投靠官軍。", 4)
    _close(on, world, game)
    assert game.share_biography(1, True, "abc") is None  # 還沒寫成
    game.write_biography(game.biography_request(1), None, 5.0)
    assert game.share_biography(1, True, "abc") == "abc"
    assert world.biography_by_code("abc")["name"] == "沈浪" and game.biography_view(1)["code"] == "abc"
    assert game.share_biography(1, False, "zzz") == "abc" and world.biography_by_code("abc") is None
    assert game.biography_view(1)["code"] is None
    assert game.share_biography(1, True, "zzz") == "abc"  # 再公開沿用同一個代碼，舊網址又能用
    assert world.biography_by_code("zzz") is None and world.biography_by_code("abc") is not None


def test_last_seasons_biography_can_still_be_written_after_the_new_season_starts(on, world):
    game = _game(on, world)
    annals.note(game.state, on, annals.DEED, "上一季的事。", 4)
    next_season(on, world, game)
    assert game.biography_entry() is None  # 新的一季在跑
    assert [b["season"] for b in game.annals_view()["books"]] == [1]
    req = game.biography_request(1)
    assert req is not None and req.annals[0]["text"] == "上一季的事。"
    assert game.write_biography(req, None, 500.0) is True and game.biography_view(1)["written"]


def test_bots_never_get_a_biography(on, world):
    from tianxia.state import BotProfile

    game = _game(on, world)
    game.state.player.bot = BotProfile(personality="普通", seed=1)
    annals.note(game.state, on, annals.DEED, "投靠官軍。", 4)
    _close(on, world, game)
    assert game.biography_entry() is None and game.biography_request(1) is None and game.share_biography(1, True, "x") is None


# ── 伺服器：背景寫傳、分享、公開頁 ──


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)
    monkeypatch.setattr(server.CONTENT.config, "admins", list(server.CONTENT.config.admins))
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    server.WORLD_GAME = None
    server.QUEUE = None
    server.ZHUAN_JOBS.clear()
    yield TestClient(server.app)
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    server.WORLD_GAME = None


def _closed_player(client):
    client.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    client.post("/api/character", json={"name": "沈青衫"})
    client.post("/api/do/skip_tutorial", json={})
    game = server.game_for("沈青衫")
    game.client = None
    server.act(game, lambda g: annals.note(g.state, server.CONTENT, annals.DEED, "投靠官軍。", 4))
    server.CONTENT.config.admins = ["沈青衫"]  # 名號建好之後才當管理者（玩家不能取管理者的名號）；client 那一份 fixture 收回
    server.act(game, lambda g: g.admin_end_season(now=g.now), paused_ok=True)
    assert game.world.season_phase() == "resting"
    return game


def _wait_written(client):
    for _ in range(200):
        view = client.get("/api/zhuan?season=1").json()
        if view["written"] and not view["writing"]:
            return view
        time.sleep(0.02)
    raise AssertionError("寫不完")


def test_the_server_writes_in_the_background_shares_and_serves_the_public_page(client, monkeypatch):
    from tianxia import accounts

    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})
    monkeypatch.delenv(server.PUBLIC_URL_ENV, raising=False)
    _closed_player(client)
    main = client.get("/api/main").json()
    assert main["zhuan"] == {"season": 1, "title": "沈青衫傳"}
    assert client.post("/api/zhuan/share", json={"season": 1, "public": True}).status_code == 400  # 還沒寫成
    out = client.post("/api/zhuan/write", json={"season": 1})
    assert out.status_code == 200
    view = _wait_written(client)
    assert view["paragraphs"][0].startswith("沈青衫者，") and view["by"] == "rule" and view["can_rewrite"]
    assert client.post("/api/zhuan/write", json={"season": 1}).status_code == 400  # 寫過了
    shared = client.post("/api/zhuan/share", json={"season": 1, "public": True}).json()
    code = shared["code"]
    assert shared["public"] and shared["url"] == f"http://testserver/zhuan/{code}"
    page = TestClient(server.app).get(f"/zhuan/{code}", headers={"x-forwarded-proto": "https"})  # 不用登入
    assert page.status_code == 200
    html = page.text
    assert '<meta property="og:title" content="沈青衫傳">' in html
    assert f'<meta property="og:url" content="https://testserver/zhuan/{code}">' in html
    assert 'content="https://testserver/static/zhuan-og.png"' in html and "沈青衫者，" in html
    monkeypatch.setenv(server.PUBLIC_URL_ENV, "https://tianxia.example/")
    assert client.get("/api/zhuan?season=1").json()["url"] == f"https://tianxia.example/zhuan/{code}"
    taken = client.post("/api/zhuan/share", json={"season": 1, "public": False}).json()
    assert taken["public"] is False and "url" not in taken
    gone = TestClient(server.app).get(f"/zhuan/{code}")
    assert gone.status_code == 404 and "查無此傳" in gone.text
    assert TestClient(server.app).get("/zhuan/nope").status_code == 404


def test_the_rewrite_uses_the_model_when_it_answers(client, monkeypatch):
    from tianxia import accounts

    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})
    game = _closed_player(client)
    client.post("/api/zhuan/write", json={"season": 1})
    _wait_written(client)
    text = "沈青衫者，" + "起於潁川，" * 50

    class Fake:
        timeout, retry = 10, True

        def chat_text(self, messages, **kw):
            return text

    game.client = Fake()
    assert client.post("/api/zhuan/write", json={"season": 1, "rewrite": True}).status_code == 200
    for _ in range(200):
        view = client.get("/api/zhuan?season=1").json()
        if view["by"] == "model":
            break
        time.sleep(0.02)
    assert view["paragraphs"] == [text] and view["can_rewrite"] is False
    assert client.post("/api/zhuan/write", json={"season": 1, "rewrite": True}).status_code == 400


def test_the_public_page_escapes_and_marks_the_verdict():
    row = {"name": "<b>沈</b>", "season": 2, "text": "<b>沈</b>者，<script>x</script>。\n\n評曰：好。"}
    html = zhuan_html.page(row, "黃巾之亂", "https://x/zhuan/a", "https://x/static/zhuan-og.png")
    assert "<script>x</script>" not in html and "&lt;script&gt;" in html
    assert '<p class="ping">評曰：好。</p>' in html and "第 2 季・黃巾之亂" in html
    assert '<meta name="robots" content="noindex">' in html


def test_the_share_image_is_a_1200_by_630_png():
    data = (ROOT / "web" / "zhuan-og.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(data[16:20], "big") == 1200 and int.from_bytes(data[20:24], "big") == 630


# ── 網頁：江湖頁的入口、傳的書頁 ──

DRIVER = r"""
const S = { zhuanVertical: !!input.vertical };
const parts = [konst("esc"), konst("ZHUAN_VERTICAL"), fn("bookIcon"), fn("sealSvg"), fn("zhuanVertical"), fn("zhuanHtml"), fn("zhuanEntry"),
  "return { zhuanHtml, zhuanEntry };"];
const H = new Function("S", parts.join("\n"))(S);
finish(input.entry ? H.zhuanEntry(input.entry, "副題") : H.zhuanHtml(input.z));
"""


def _web(**inp):
    return webharness.run(DRIVER, inp)


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_reader_draws_each_state():
    written = {"season": 1, "title": "沈<浪>傳", "written": True, "paragraphs": ["沈浪者，<i>x</i>。", "評曰：好。"],
               "public": False, "can_rewrite": True, "scenario": "黃巾之亂"}
    html = _web(z={"season": 1, "view": written})
    assert "沈&lt;浪&gt;傳" in html and "&lt;i&gt;x" in html and '<p class="ping">評曰：好。</p>' in html
    assert 'data-act="zhuan-share" data-public="1"' in html and 'data-act="zhuan-rewrite"' in html and "第 1 季・黃巾之亂" in html
    assert 'aria-pressed="false"' in html and "zhuan-text vertical" not in html
    shared = _web(z={"season": 1, "view": {**written, "public": True, "url": "https://x/zhuan/<a>", "can_rewrite": False}}, vertical=True)
    assert "https://x/zhuan/&lt;a&gt;" in shared and 'data-act="zhuan-send"' in shared and 'data-public="0"' in shared
    assert 'data-act="zhuan-rewrite"' not in shared and "zhuan-text vertical" in shared
    waiting = _web(z={"season": 1, "view": {"season": 1, "title": "沈浪傳", "written": False, "can_write": True, "writing": True}})
    assert "史官正在落筆" in waiting and 'data-act="zhuan-write"' not in waiting
    ready = _web(z={"season": 1, "view": {"season": 1, "title": "沈浪傳", "written": False, "can_write": True}})
    assert 'data-act="zhuan-write"' in ready
    assert "翻開史冊" in _web(z={"season": 1, "view": None})
    entry = _web(entry={"season": 3, "title": "沈浪傳", "written": False})
    assert 'data-act="zhuan-open" data-season="3"' in entry and "立傳 ›" in entry


def test_the_page_wires_the_entries_and_the_handlers():
    src = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    for needle in ('case "zhuan-open"', 'case "zhuan-write"', 'case "zhuan-share"', 'case "zhuan-send"', 'case "zhuan-rewrite"',
                   "m.zhuan ? zhuanEntry(", "歷季列傳", 'api(`/api/zhuan?season='):
        assert needle in src, needle
