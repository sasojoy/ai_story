"""FB-501 的網頁那一半（7 天濃縮季 QA 第 7 件清單）：軍令卡、大事小標、季末結算卡、輿圖（天下怎麼變、總覽、地點的易手、正在看第幾段、
比第幾段）、管理者（每週的事、立刻發軍令、開季、暫停、繼續、重發軍令、輪替席次）在 7 天季照段（或今日）寫；21 天季、週末照原本的字。
在 node 裡跑整支 app.js（tests/webharness.py），餵伺服器真的會給的資料；沒有 node 就略過。"""
from __future__ import annotations

import random
import re

import pytest
import test_prologue_web

import server
import webharness
from conftest import real_content
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]
# 輿圖第三版第 4 批：總覽（overviewHtml）挪到卡底下（cardExtras）、地點的卡換成 placeCard、「天下」那一條（hudHtml）拿掉了，
# 比第幾段改看版圖變化那一格（timelineHtml 的處數底下）
NAMES = ["S", "ordersHtml", "boardPeek", "resultHtml", "timelineHtml", "cardExtras", "placeCard", "mapChrome",
         "sheetHtml", "adminAsk"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
HOUR, DAY = 3600, 86400
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
ORDERS = [{"title": "守城", "text": "守住", "progress": 1, "quota": 5, "done": False, "mine": 0, "deadline": "第 2 天 00:00"}]
RESULT = {"title": "黃天當立", "text": "<p>終</p>", "stances": [], "fronts": [], "rankings": [],
          "timeline": [{"week": 1, "title": "三十六方起義", "text": "<p>起</p>", "locked_by": None},
                       {"week": 3, "title": "廣宗決戰", "text": "<p>戰</p>", "locked_by": None}]}


def _game(profile):
    content = real_content(profile)
    content.config.admins = ["甲"]
    content.config.train_event_chance = 0.0
    store = open_world()
    store.seed_first_season(content)
    game = Game.new(content, "甲", rng=random.Random(0), world=store)
    game.client = None
    game.admin_open_season(MON)
    game.state.player.faction = "guan"
    game.sync(MON + DAY + HOUR)  # 第 2 天：第 1 段
    return game


def _map_state(game):
    """輿圖的疊層：照伺服器給的，再補第 1、2 段的快照與一次易手、一則大事（開季第 2 天還沒有易手），看段的字。"""
    st = game.map_state()
    control = {p: "guan" for p in st["places"]}
    st.update(now_week=2, start=None, events=["三十六方起義"], territory=True,
              weeks=[{"week": 1, "control": control, "ropes": {}, "geju": None, "events": ["三十六方起義"], "changed": []},
                     {"week": 2, "control": control, "ropes": {}, "geju": None, "events": [], "changed": []}])
    place = next(iter(st["places"]))
    st["places"][place]["flips"] = [{"week": 1, "from": "huang", "to": "guan"}]
    return st, place


def _render(game, monkeypatch, app=None):
    """畫一輪這一季的那幾處，回一個 dict（名字 → 字）。app 給了就用那一份 app.js（對照舊版用）。"""
    monkeypatch.setattr(server, "CONTENT", game.content)
    st, place = _map_state(game)
    m = {**server.main_view(game), "admin": True, "bulletin": ["<p>甲事</p>"]}
    script = """
      const st = H.S.mapState, base = H.S.mapBase, fb = H.S.fb501;
      H.S.mapMode = "timeline"; H.S.mapWeek = 1;
      return {
        orders: H.ordersHtml(fb.orders, 1, null),
        board: H.boardPeek(m, 1).label,
        result: H.resultHtml(fb.result),
        timeline: H.timelineHtml(base, st, 1),
        overview: H.cardExtras(base, st),
        place: H.placeCard(base, st, fb.place),
        hud: H.timelineHtml(base, st, 2),
        chrome: H.mapChrome(),
        sheet: H.sheetHtml(),
        open: H.adminAsk("open_season", {})[0],
        next: H.adminAsk("next_season", {})[0],
        pause: H.adminAsk("pause_clock", {})[0],
        resume: H.adminAsk("resume_clock", {})[0],
        issue: H.adminAsk("issue_orders", {})[0],
        rotate: H.adminAsk("rotate_seats", {})[0],
      };"""
    payload = {"m": m, "script": script, "menxia": None, "stored": {}, "responses": {},
               "S": {"mapBase": game.map_base(), "mapState": st, "admin": server.admin_choices(game),
                     "fb501": {"orders": ORDERS, "result": RESULT, "place": place}}}
    if app is not None:
        payload["app"] = str(app)
    return webharness.run(DRIVER, payload)


def test_week7_pages_say_segments_and_today(monkeypatch):
    out = _render(_game("week7"), monkeypatch)
    assert "📜 今日軍令（1）" in out["orders"]
    assert out["board"] == "這一段江湖大事 1 則"
    assert "<b>第 1 段（第 1～2 天）・三十六方起義</b>" in out["result"] and "<b>第 3 段（第 5～7 天）・廣宗決戰</b>" in out["result"]
    assert "<small>第 1 段末（第 2 天）</small>" in out["timeline"] and "<h4>第 1 段（第 1～2 天）</h4>" in out["timeline"]
    assert "<h4>這一段大事</h4>" in out["overview"]
    assert "易手：第 1 段（第 1～2 天） " in out["place"]
    assert "比第 1 段（第 1～2 天）" in out["hud"]
    assert "正在看第 1 段（第 1～2 天）" in out["chrome"]
    assert "每天、每段的事（照 00:00 的做法立刻再做一次；之後照常）" in out["sheet"] and "立刻發今日軍令" in out["sheet"]
    assert "（預設在第 2、4、7 天 20:00、季末第 7 天過完）" in out["open"] and "（預設在第 2、4、7 天 20:00、季末第 7 天過完）" in out["next"]
    assert "7 天的季：繼續時季曆會對回現實的日子" in out["pause"] and "7 天的季的季曆對回現實的日子" in out["resume"]
    assert out["issue"].startswith("立刻發今日軍令：今天還沒達成的軍令") and "明天 00:00 照常發令" in out["issue"]
    assert "照上一段的貢獻" in out["rotate"] and "下一段第一天 00:00 照常再排" in out["rotate"]
    assert not any("週" in v for v in out.values() if isinstance(v, str) and v is not out["sheet"])


def test_the_timeline_head_keeps_the_segment_end_on_one_line():
    """實機 375 寬：「第 1 段末（第 2 天）」拆在括號裡（「（第」／「2 天）」）；那一小行不折行，整段換到下一行（CSS，幾何在瀏覽器量過）。"""
    css = (webharness.ROOT / "web" / "style.css").read_text(encoding="utf-8")
    rule = re.search(r"\.m-tl-head small \{([^}]*)\}", css)
    assert rule and "white-space: nowrap" in rule.group(1)


@pytest.mark.parametrize("profile", ["season21", "weekend"])
def test_other_seasons_keep_the_week_words(profile, monkeypatch):
    out = _render(_game(profile), monkeypatch)
    assert out["board"] == "本週江湖大事 1 則"
    assert "<b>第 1 週・三十六方起義</b>" in out["result"]
    assert "<small>第 1 週週末</small>" in out["timeline"] and "<h4>第 1 週</h4>" in out["timeline"]
    assert "<h4>本週大事</h4>" in out["overview"] and "易手：第 1 週 " in out["place"]
    assert "比第 1 週" in out["hud"] and "正在看第 1 週" in out["chrome"]
    # 開季問句括號裡的預設時刻照這一種季自己的時刻表寫：21 天季「週六 20:00」三場、週末「週中」（dev/small-1020 改了 21 天這一句，FB-560）
    default_dates = "（預設在第 1、2、3 週週六 20:00、季末第 3 週週日過完）" if profile == "season21" else "（預設在第 6、9、11 週中、第 12 週末）"
    assert default_dates in out["open"]
    assert "照上一週的貢獻" in out["rotate"]
    if profile == "weekend":  # 21 天季的軍令每天一道：軍令卡、管理者那幾句照「今日」寫（FB-502，test_fb502_season21_order_words）
        assert "📜 本週軍令（1）" in out["orders"]
        assert "每週的事（照週一的做法立刻再做一次；下週一照常）" in out["sheet"] and "立刻發本週軍令" in out["sheet"]
        assert out["issue"].startswith("立刻發本週軍令：這一週還沒達成的軍令照週一的做法重挑")
    if profile == "season21":
        assert "21 天的季：繼續時季曆會對回現實的星期" in out["pause"] and "21 天的季的季曆對回現實的星期" in out["resume"]
    else:
        assert "天的季" not in out["pause"] and "天的季" not in out["resume"]
