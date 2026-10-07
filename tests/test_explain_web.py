"""玩法說明（explain-1）的網頁部分：行動列底下那幾行、體力條點開的說明、設定抽屜的「玩法說明」。
照 tests/test_prologue_web.py 的做法把整支 app.js 放進 node 的假瀏覽器，餵它真的引擎給的 /api/main；沒有 node 就略過。"""
from __future__ import annotations

import random
import re

import pytest
from test_prologue_web import run

import server
import webharness
from conftest import real_content
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _main(game=None, **over):
    if game is None:
        content = real_content()
        content.config.auto_open_first_season = True
        game = Game.new(content, "沈浪", rng=random.Random(0))  # 不走序章：跟略過序章的人一樣站在起點
        game.client = None
    m = server.main_view(game)
    m.update(over)
    return m


# ── 行動列底下那幾行 ─────────────────────────────────────────


def test_the_notes_sit_under_the_action_row_in_cell_order():
    m = _main()
    notes = m["action_notes"]
    assert notes["act:explore"].startswith("這裡")  # 伺服器照規則寫好的
    page = run(m, "return H.pageJianghu();")
    bar_end = page.index("</div>", page.index('class="act-bar"'))
    block = re.search(r'<div class="act-notes">(.*?)</div>', page)
    assert block and page.index('class="act-notes"') > page.index('class="act-bar"')
    rows = re.findall(r"<p><b>(.*?)</b>(.*?)</p>", block.group(1))
    assert rows[0] == ("探索", notes["act:explore"])  # 照格子的順序、冠格子上的名字
    for name, text in rows:
        assert text in notes.values() and name in ("探索", "遊歷", "操練", "交友", "求見")
    assert page.index('class="act-notes"') > bar_end  # 在行動列後面：不推動「剛剛」、場景與整排行動


def test_the_notes_give_way_to_the_move_card():
    m = _main()
    page = run(m, "return H.pageJianghu();", S={"wheelSel": "move"})
    assert 'class="card act-move"' in page and 'class="act-notes"' not in page


def test_the_notes_give_way_when_the_guide_points_into_the_here_fold():
    """入伍段要按的鈕收在「此地還能做」裡（guide.glow）：說明不畫，不把那一顆往下推。"""
    m = _main()
    extra = next(o["id"] for o in m["options"] if o["id"].startswith("move:"))  # 隨便一顆不在行動列格子裡的（這裡用前往）
    m["options"] = [o for o in m["options"] if not o["id"].startswith("move:")] + [{"id": "act:duty", "label": "巡哨", "enabled": True}]
    m["guide"] = {"glow": ["act:duty"]}
    bar = run(m, "return H.actionBar(H.S.main);")
    assert 'class="act-notes"' not in bar and "此地還能做" in bar
    m["guide"] = {"glow": [extra]}  # 發光的不在摺疊裡：說明照畫
    assert 'class="act-notes"' in run(m, "return H.actionBar(H.S.main);")


def test_no_notes_without_server_notes():
    """伺服器沒給（舊版、序章裡是空的）：不畫那一塊。"""
    m = _main()
    m.pop("action_notes")
    assert 'class="act-notes"' not in run(m, "return H.pageJianghu();")
    m["action_notes"] = {}
    assert 'class="act-notes"' not in run(m, "return H.pageJianghu();")


def test_the_conversation_view_shows_the_bond(content):
    """談話畫面（場景卡）名字旁寫著情誼：伺服器把引擎的 Markdown 轉成 HTML，網頁照放（explain-1 第二項）。"""
    from unittest import mock

    from test_engine import FAKE_TURN

    from tianxia import companion_agent

    content.characters["mate"].deep_interaction = True
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.state.player.affinities["mate"] = 12
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
    page = run(_main(game), "return H.pageJianghu();")
    assert re.search(r'<section class="card scene"><p><strong>韓鐵</strong>（情誼 12）</p>', page)


# ── 點體力條看體力怎麼回 ─────────────────────────────────────────


def test_tapping_the_stamina_bar_opens_the_help_and_the_pill_keeps_its_own_target():
    m = _main()
    help_lines = m["status"]["stamina_help"]
    assert help_lines and m["status"]["pills"]  # 新角色有內測贈送的丹：體力條上有那顆鈕
    closed = run(m, "return H.topHtml();")
    bar = re.search(r'<div class="bar stam"[^>]*>', closed).group(0)
    assert 'data-act="stam-help"' in bar and 'aria-expanded="false"' in bar
    # 丹的鈕在體力條裡面、自己帶 data-act="pill"：點它時 closest("[data-act]") 先碰到它，不會走到攤開說明
    inside = closed[closed.index(bar):closed.index("</div>", closed.index(bar))]
    assert 'class="pill-btn" data-act="pill"' in inside
    assert 'class="more-stats stam-help"' not in closed
    out = run(m, """return (async () => {
      const el = { dataset: { act: "stam-help" }, classList: { contains: () => false } };
      await T.docListeners.click[0]({ target: { closest: () => el } });
      const opened = H.topHtml();
      const first = H.S.stamOpen;
      await T.docListeners.click[0]({ target: { closest: () => el } });
      return { first, opened, second: H.S.stamOpen };
    })();""")
    assert out["first"] is True and out["second"] is False
    block = re.search(r'<div class="more-stats stam-help" id="stam-help">(.*?)</div>', out["opened"]).group(1)
    assert re.findall(r"<p>(.*?)</p>", block) == help_lines  # 伺服器寫好的幾行，一行一段
    assert 'aria-expanded="true"' in out["opened"]


def test_the_pill_click_still_takes_a_pill():
    m = _main()
    out = run(m, """return (async () => {
      const el = { dataset: { act: "pill" }, classList: { contains: () => false } };
      await T.docListeners.click[0]({ target: { closest: () => el } });
      return { calls: T.calls.map((c) => c[0]), open: H.S.stamOpen };
    })();""", responses={"/api/do/pill": {"main": m, "message": ""}})
    assert any(url.startswith("/api/do/pill") for url in out["calls"]) and out["open"] is False


def test_no_help_from_an_old_server_means_a_plain_bar():
    m = _main()
    m["status"].pop("stamina_help")
    bar = re.search(r'<div class="bar stam"[^>]*>', run(m, "return H.topHtml();")).group(0)
    assert "data-act" not in bar


def test_the_help_lines_are_escaped():
    m = _main()
    m["status"]["stamina_help"] = ["<b>x</b>"]
    assert "&lt;b&gt;x&lt;/b&gt;" in run(m, "return H.topHtml();", S={"stamOpen": True})


# ── 設定抽屜的「玩法說明」 ─────────────────────────────────────────

HOWTO = "<h4>行動</h4><ul><li>探索</li></ul>"

OPEN_HOWTO = """return (async () => {
  let sheet = { scrollTop: 0 };
  Object.defineProperty(T.qs, ".sheet", { get: () => sheet, configurable: true, enumerable: true });
  let html = "";
  Object.defineProperty(T.els.app, "innerHTML", { get: () => html, set(v) { html = v; sheet = { scrollTop: 0 }; }, configurable: true });
  const tap = async (act) => {
    const el = { dataset: { act }, classList: { contains: () => false } };
    await T.docListeners.click[0]({ target: { closest: () => el } });
  };
  await tap("sheet");  // 齒輪：打開設定抽屜
  const drawer = html;
  sheet.scrollTop = 120;  // 人往下捲了一點才按
  await tap("howto");
  const opened = html, kept = sheet.scrollTop;
  await tap("howto");  // 收起
  const closed = html;
  await tap("howto");  // 再打開：再問一次伺服器（換季、第一季的開關換了都跟著對，審查 M5）
  return { drawer, opened, kept, closed, again: html, calls: T.calls.map((c) => c[0]).filter((u) => u.startsWith("/api/howto")) };
})();"""

# 玩法說明的請求由測試控制（審查 M5）：T.ctx.fetch 換成假的，/api/howto 的每一次都記下來、由測試決定什麼時候回、回什麼（或連不上）
HOWTO_HARNESS = """
  let sheet = { scrollTop: 0 };
  Object.defineProperty(T.qs, ".sheet", { get: () => sheet, configurable: true, enumerable: true });
  let html = "";
  Object.defineProperty(T.els.app, "innerHTML", { get: () => html, set(v) { html = v; sheet = { scrollTop: 0 }; }, configurable: true });
  const pending = [];  // 每一次 /api/howto：{ ok(text), fail() }
  const base = T.ctx.fetch;
  T.ctx.fetch = (url, opts) => {
    if (!url.startsWith("/api/howto")) return base(url, opts);
    return new Promise((resolve, reject) => pending.push({
      ok: (text) => resolve({ ok: true, status: 200, json: () => Promise.resolve({ text }) }),
      fail: () => reject(new TypeError("Failed to fetch")),
    }));
  };
  const tap = (act) => {
    const el = { dataset: { act }, classList: { contains: () => false } };
    return T.docListeners.click[0]({ target: { closest: () => el } });
  };
  const settle = () => new Promise((r) => setTimeout(r, 0));
  H.S.sheet = true;
  H.render();
"""


def test_the_howto_page_is_fetched_again_on_each_open_showing_the_last_one_meanwhile():
    """每次攤開都再問一次（換季、第一季的開關換了，說明跟著對；一個 GET，按了才問）：問的時候先放著上一次的那一頁，回來了換新的。"""
    out = run(_main(), "return (async () => {" + HOWTO_HARNESS + """
      const first = tap("howto"); await settle();
      const loading = html;
      pending[0].ok("<p>第一版</p>"); await first;
      const shown = html;
      await tap("howto");  // 收起
      const second = tap("howto"); await settle();
      H.render();  // 等的時候別的東西讓抽屜整個重畫（輪詢、管理者資料回來）：照樣放著上一頁
      const meanwhile = html;
      pending[1].ok("<p>第二版</p>"); await second;
      return { loading, shown, meanwhile, after: html, asked: pending.length };
    })();""")
    assert "正在翻書……" in out["loading"]
    assert "<p>第一版</p>" in out["shown"]
    assert "<p>第一版</p>" in out["meanwhile"] and "正在翻書" not in out["meanwhile"]
    assert "<p>第二版</p>" in out["after"] and "第一版" not in out["after"] and out["asked"] == 2


def test_a_failed_howto_request_offers_a_retry():
    """要不到（連不上）：卡上寫一句、給「再試一次」，不是一直停在「正在翻書……」；再試一次要到了就照常畫。"""
    out = run(_main(), "return (async () => {" + HOWTO_HARNESS + """
      const first = tap("howto"); await settle();
      pending[0].fail(); await first;
      const failed = html;
      const retry = tap("howto-retry"); await settle();
      const retrying = html;
      pending[1].ok("<p>說明</p>"); await retry;
      return { failed, retrying, after: html, open: H.S.howtoOpen };
    })();""")
    card = re.search(r'<div class="howto card" id="howto">(.*?)</div>', out["failed"], re.S).group(1)
    assert "正在翻書" not in card and "說明沒拿到" in card and 'data-act="howto-retry"' in card
    assert "正在翻書……" in out["retrying"]
    assert "<p>說明</p>" in out["after"] and "howto-retry" not in out["after"] and out["open"] is True


def test_an_older_howto_answer_does_not_overwrite_a_newer_one():
    """先按的那一次比後按的晚回來：照後按的那一次（換季前後各問一次，不能被舊的蓋回去）。"""
    out = run(_main(), "return (async () => {" + HOWTO_HARNESS + """
      const first = tap("howto"); await settle();
      await tap("howto");  // 還沒回來就收起
      const second = tap("howto"); await settle();
      pending[1].ok("<p>新</p>"); await second;
      pending[0].ok("<p>舊</p>"); await first;
      return { html, cached: H.S.howto };
    })();""")
    assert out["cached"] == "<p>新</p>" and "<p>新</p>" in out["html"] and "<p>舊</p>" not in out["html"]


def test_logout_forgets_the_howto_page():
    """登出就清掉（換帳號、換角色不帶著上一個人的那一頁、也不停在攤開的樣子）；登出前還沒回來的那一次也不算。"""
    out = run(_main(), "return (async () => {" + HOWTO_HARNESS + """
      const first = tap("howto"); await settle();
      pending[0].ok("<p>上一個人的</p>"); await first;
      const before = H.S.howto;
      const late = tap("howto"); await settle();  // 收起
      const again = tap("howto"); await settle();  // 再打開：又問了一次，還沒回來
      await tap("logout");
      pending[1].ok("<p>登出後才回來</p>"); await again; await late;
      return { before, after: H.S.howto === undefined ? null : H.S.howto, open: H.S.howtoOpen, failed: !!H.S.howtoFailed };
    })();""", responses={"/api/logout": {}})
    assert out["before"] == "<p>上一個人的</p>"
    assert out == {"before": "<p>上一個人的</p>", "after": None, "open": False, "failed": False}


def _skipped(prologue_content, world):
    """走序章的新角色按了「略過序章」：站在起點，狀態列整條都在（齒輪也在）。"""
    game = Game.new(prologue_content, "沈浪", rng=random.Random(0), world=world, prologue=True)
    game.skip_tutorial()
    game.client = None
    return _main(game)


def test_the_howto_page_is_reachable_with_the_prologue_skipped(prologue_content, world):
    m = _skipped(prologue_content, world)
    assert m["prologue"] is None
    assert 'data-act="sheet"' in run(m, "return H.topHtml();")  # 右上角的齒輪
    out = run(m, OPEN_HOWTO, responses={"/api/howto": {"text": HOWTO}, "/api/prologue": {"text": ""}})
    assert 'data-act="howto"' in out["drawer"] and "玩法說明" in out["drawer"] and 'class="howto card"' not in out["drawer"]
    assert f'<div class="howto card" id="howto">{HOWTO}</div>' in out["opened"] and 'aria-expanded="true"' in out["opened"]
    assert out["kept"] == 120  # 抽屜停在原地（renderKeepingSheet），沒有被丟回頂上
    assert 'class="howto card"' not in out["closed"] and HOWTO in out["again"]
    assert out["calls"] == ["/api/howto", "/api/howto"]  # 每次攤開問一次（審查 M5）；收起不問


def test_the_howto_button_sits_at_the_top_of_the_drawer_for_everyone():
    m = _main()
    drawer = run(m, "return H.sheetHtml();", S={"sheet": True})
    assert drawer.index('data-act="howto"') < drawer.index('data-op="skip_tutorial"')  # 一般設定的第一顆
    assert "admin-zone" not in drawer  # 一般玩家也有（不是管理者工具）


def test_the_howto_endpoint_serves_the_page_as_html():
    from fastapi.testclient import TestClient

    client = TestClient(server.app)
    client.post("/api/register", json={"login": "howto_01", "password": "secret-pw", "again": "secret-pw"})
    client.post("/api/character", json={"name": "說明人"})
    client.post("/api/do/skip_tutorial", json={})
    text = client.get("/api/howto").json()["text"]
    cfg = server.CONTENT.config
    assert "<h4>行動</h4>" in text and "<h4>背包</h4>" in text
    assert f"<strong>探索</strong>（體力 {cfg.action_cost['explore']}）" in text and "<script" not in text


def test_notes_are_escaped():
    m = _main()
    m["action_notes"] = {"act:explore": "<b>x</b>"}
    page = run(m, "return H.pageJianghu();")
    assert "&lt;b&gt;x&lt;/b&gt;" in page
