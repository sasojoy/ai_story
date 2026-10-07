"""FB-087：江湖頁「此地還能做 N 件事」摺疊被重畫收起來（QA 驗 FB-077，2026-10-06，375×812）。

摺疊裡的按鈕（例：求見盧植）被擋下來（「對方還沒答話，稍等。」、排太久）之後，choose() 重畫整頁、摺疊就收起來了；輪詢帶來新畫面時
renderPage() 也一樣。現在摺疊的開合記在 S.here（玩家自己開關的、這一處），重畫照它補回。附帶 guide-3b 審查 Minor 11：入伍段第一道軍令
那一步（框上帶 glow act:duty）摺疊本來每次重畫都自動打開、跟收起它的玩家打架——現在每一處只在那一步開頭自動打開一次，之後照玩家的。

網頁沒有建置步驟也沒有瀏覽器：照 tests/test_prologue_web.py 的做法，把整支 app.js 放進 node 的假瀏覽器，餵它真的引擎給的 /api/main，
用假的 toggle 事件當玩家點開、收起摺疊，看重畫出來的 HTML。假 DOM 裡 details 的開合就是 HTML 裡有沒有 open：驗的是「重畫畫出什麼」。"""
from __future__ import annotations

import json

import pytest
from test_fb092_095 import _enlist_main
from test_prologue_web import run

import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

# 驅動程式共用的小工具：fold() 讀頁面上那個摺疊現在畫成開著（true）、收著（false）、沒畫（null）；toggle(open) 送一個玩家點開／收起
# 的 toggle 事件；refuse() 讓下一個 /api/choose 被伺服器擋下來（400）、並讓 choose() 失敗後會重畫（按下去的那顆鈕還標著 busy）
HELPERS = """
const fold = () => { const hit = T.els.page.innerHTML.match(/<details class="fold here"( open)?>/); return hit ? !!hit[1] : null; };
const toggle = (open) => T.docListeners.toggle[0]({ target: Object.assign(Object.create(T.Element.prototype), { matches: (sel) => sel === "details.here", open }) });
const redraw = () => { T.els.page.innerHTML = ""; H.renderPage(); return fold(); };
const press = (id) => T.docListeners.click[0]({ target: { closest: () => ({ dataset: { act: "choose", id }, classList: { contains: () => false, add() {}, remove() {} } }) } });
const refuse = (error) => {
  T.ctx.setTimeout = () => 0; // toast() 的計時器不要拖住這個請求
  T.ctx.fetch = (url, opts) => { T.calls.push([url, JSON.parse(opts.body)]); return Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({ error }) }); };
  T.qs[".options .btn.busy, .act-ink.busy"] = {};
};
"""


def _script(body: str) -> str:
    return HELPERS + body


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _quiet(m):
    """框上沒有 glow：入伍段別的時候（或別的玩家）平常的樣子，「此地還能做」收著。"""
    return {**m, "guide": {k: v for k, v in m["guide"].items() if k != "glow"}}


def _at(m, place):
    return {**m, "status": {**m["status"], "location": place}}


@pytest.fixture
def glowing(on):
    """入伍段第一道軍令那一步：框上帶 glow（act:duty），「此地還能做」裡有發光的巡哨。"""
    m = _enlist_main(on)
    assert m["guide"]["glow"] == ["act:duty"] and any(o["id"] == "act:duty" for o in m["options"])
    return m


@pytest.fixture
def quiet(glowing):
    return _quiet(glowing)


def test_a_fold_nobody_touched_stays_shut_and_no_fold_is_drawn_without_extras(quiet):
    out = run(quiet, _script("""
      H.renderPage();
      const shut = fold();
      H.S.main = { ...H.S.main, options: H.S.main.options.filter((o) => ["act:explore", "act:train", "act:rest", "act:socialize"].includes(o.id)) };
      return { shut, none: redraw() };"""))
    assert out == {"shut": False, "none": None}


def test_a_fold_the_player_opened_stays_open_after_a_refused_actions_redraw(quiet):
    """摺疊裡的鈕被伺服器擋下來（400：「對方還沒答話，稍等。」；排太久也是這一種），choose() 重畫整頁：摺疊照樣開著，剛按的那一顆還在。"""
    out = run(quiet, _script("""return (async () => {
      H.renderPage();
      const before = fold();
      toggle(true); // 玩家點開「此地還能做」
      refuse("對方還沒答話，稍等。");
      T.els.page.innerHTML = ""; // 確認接下來的畫面是被擋下來之後重畫出來的
      await press("act:duty");
      return { before, redrawn: T.els.page.innerHTML !== "", after: fold(), calls: T.calls.map((c) => [c[0], c[1].id]),
               button: T.els.page.innerHTML.includes('data-id="act:duty"') };
    })();"""))
    assert out["before"] is False and out["calls"] == [["/api/choose", "act:duty"]]
    assert out["redrawn"] is True and out["after"] is True and out["button"] is True


def test_a_fold_the_player_left_shut_stays_shut_after_a_refused_actions_redraw(quiet):
    out = run(quiet, _script("""return (async () => {
      H.renderPage();
      toggle(true);
      toggle(false); // 開了又收
      refuse("這會兒人多，沒輪到你，稍後再試一次。");
      await press("act:duty");
      return { after: fold(), redrawn: T.els.page.innerHTML.includes("此地還能做") };
    })();"""))
    assert out == {"after": False, "redrawn": True}


def test_a_fold_the_player_opened_stays_open_after_a_poll_redraw(quiet):
    """輪詢帶來新的畫面（拿到有變的 main 之後 refreshPage → renderPage）：以前也把摺疊收起來。摺疊裡的件數變了（標題的字不同）也一樣。"""
    out = run(quiet, _script("""return (async () => {
      H.renderPage();
      toggle(true);
      const was = H.S.main;
      const fewer = was.options.filter((o) => o.id !== "act:duty");
      H.setMain({ ...was, now: "天色漸暗，營裡升起了炊煙。", options: fewer }); // 世界動了、此地少了一件事
      T.els.page.innerHTML = "";
      await H.refreshPage(was);
      return { redrawn: T.els.page.innerHTML !== "", open: fold(), title: (T.els.page.innerHTML.match(/此地還能做 (\\d+) 件事/) || [])[1] };
    })();"""))
    assert out["redrawn"] is True and out["open"] is True
    before = run(quiet, _script("H.renderPage(); return (T.els.page.innerHTML.match(/此地還能做 (\\d+) 件事/) || [])[1];"))
    assert int(out["title"]) == int(before) - 1  # 標題照新的件數寫，摺疊照樣開著


def test_the_fold_is_remembered_for_this_place_only(quiet):
    """記的是這一處：走到別處，那裡的摺疊從收著開始（不然開過一次，每個城鎮都攤著一排按鈕）；回到原處、中間沒開關過別處，還是原樣。"""
    out = run(quiet, _script("""
      H.renderPage();
      toggle(true);
      const here = redraw();
      H.S.main = %s;
      const elsewhere = redraw();
      H.S.main = %s;
      return { here, elsewhere, back: redraw() };""" % (_json(_at(quiet, "別處")), _json(quiet))))
    assert out == {"here": True, "elsewhere": False, "back": True}


# ── 入伍段第一道軍令那一步（guide-3b 審查 Minor 11）──────────────────────────────


def test_the_glowing_step_opens_the_fold_once_and_the_glow_stays_on_the_button(glowing):
    out = run(glowing, _script("""
      H.renderPage();
      const html = T.els.page.innerHTML;
      return { open: fold(), glowButton: /data-id="act:duty" >/.test(html), auto: Object.keys(H.S.hereAuto) };"""))
    assert out["open"] is True and out["glowButton"] is True  # 開頭自動打開、發光的鈕還在（applyGlow 照 guide.glow 的 id 找它）
    assert len(out["auto"]) == 1  # 記下「這一步、這一處」打開過了


def test_any_glowing_button_in_the_fold_opens_it_once_and_one_on_the_action_bar_does_not(glowing):
    """joy 的 guide.glow 不只守勢行動：接糧車、挑戰那位人物收在「此地還能做」裡也一樣——開頭打開一次、之後照玩家的。發光的是行動列上的
    遊歷（攻城、截糧）時摺疊裡沒有要露出來的東西，不打開。"""
    convoy = {"id": "act:convoy", "label": "接下糧車（交出 4 份糧草）", "enabled": True, "wait": "", "confirm": ""}
    cart = {**glowing, "guide": {**glowing["guide"], "glow": ["act:convoy"]}, "options": glowing["options"] + [convoy]}
    out = run(cart, _script("""
      const begin = redraw();
      toggle(false);
      return { begin, after: [redraw(), redraw()], auto: Object.keys(H.S.hereAuto).length };"""))
    assert out == {"begin": True, "after": [False, False], "auto": 1}
    train = {**glowing, "guide": {**glowing["guide"], "glow": ["act:train"]}}
    assert run(train, _script("return { open: redraw(), auto: Object.keys(H.S.hereAuto).length };")) == {"open": False, "auto": 0}


def test_a_fold_the_player_closed_at_the_glowing_step_stays_closed_on_the_next_redraws(glowing):
    out = run(glowing, _script("""return (async () => {
      H.renderPage();
      const begin = fold();
      toggle(false); // 玩家把它收起來
      const redraws = [redraw(), redraw(), redraw()];
      const was = H.S.main;
      H.setMain({ ...was, now: "營裡的鼓聲停了。" });
      T.els.page.innerHTML = "";
      await H.refreshPage(was); // 輪詢
      const poll = fold();
      refuse("對方還沒答話，稍等。");
      await press("act:duty"); // 被擋下來
      return { begin, redraws, poll, refused: fold(), auto: Object.keys(H.S.hereAuto).length };
    })();"""))
    assert out == {"begin": True, "redraws": [False, False, False], "poll": False, "refused": False, "auto": 1}


def test_the_glowing_step_opens_the_fold_once_not_on_every_redraw(glowing):
    """「每次重畫都打開」的舊做法下，玩家收起來之後的每一次重畫都會再開；現在只在這一步開頭開一次：之後開著是玩家沒收（記在 S.here），
    不是又自動打開——所以收起來、再重畫幾次都是收著，S.hereAuto 也始終只有一筆。"""
    out = run(glowing, _script("""
      const seen = [];
      for (let i = 0; i < 4; i++) { seen.push(redraw()); }
      toggle(false);
      for (let i = 0; i < 4; i++) { seen.push(redraw()); }
      return { seen, auto: Object.keys(H.S.hereAuto).length };"""))
    assert out == {"seen": [True] * 4 + [False] * 4, "auto": 1}


def test_a_player_who_closed_the_fold_before_the_step_began_gets_it_opened_once_when_it_begins(glowing, quiet):
    out = run(quiet, _script("""
      H.renderPage();
      toggle(true); toggle(false); // 這一步還沒開始：玩家自己收著
      const before = redraw();
      H.S.main = %s; // 入伍段走到第一道軍令那一步：框上帶了 glow
      const begin = redraw();
      toggle(false);
      return { before, begin, after: redraw() };""" % _json(glowing)))
    assert out == {"before": False, "begin": True, "after": False}


def test_the_next_glowing_step_or_place_opens_it_again_once(glowing):
    """「開頭」是這一步（框的 key）在這一處第一次發光：別的步驟、或走到別處（那裡的摺疊裡也有發光的鈕）各開一次，開過就不再自動開。"""
    other_step = {**glowing, "guide": {**glowing["guide"], "key": "another_glowing_step"}}
    out = run(glowing, _script("""
      H.renderPage(); toggle(false);
      const closed = redraw();
      H.S.main = %s;
      const nextStep = redraw(); toggle(false);
      const nextStepAgain = redraw();
      H.S.main = %s;
      const elsewhere = redraw(); toggle(false);
      const elsewhereAgain = redraw();
      return { closed, nextStep, nextStepAgain, elsewhere, elsewhereAgain, auto: Object.keys(H.S.hereAuto).length };"""
                              % (_json(other_step), _json(_at(glowing, "別處")))))
    assert out == {"closed": False, "nextStep": True, "nextStepAgain": False, "elsewhere": True, "elsewhereAgain": False, "auto": 3}


def test_the_fold_without_a_glowing_duty_button_is_not_opened_by_the_step(glowing):
    """框上帶 glow、但這一處沒有發光的那顆鈕（沒有 act:duty）：沒有東西要露出來，摺疊不自動打開，也不記成自動打開過。"""
    other = {"id": "learn:cuquan", "label": "學粗淺拳腳（學費 0 兩）", "enabled": True, "wait": "", "confirm": ""}  # 摺疊裡留一顆別的鈕，摺疊還畫得出來
    m = {**glowing, "options": [o for o in glowing["options"] if o["id"] != "act:duty"] + [other]}
    out = run(m, _script("H.renderPage(); return { open: fold(), auto: Object.keys(H.S.hereAuto) };"))
    assert out == {"open": False, "auto": []}


def test_logging_in_again_starts_the_fold_over(glowing):
    out = run(glowing, _script("""
      H.renderPage(); toggle(true);
      const remembered = H.S.here;
      H.enter({ stage: "gate" });
      return { remembered, here: H.S.here, auto: Object.keys(H.S.hereAuto) };"""))
    assert out["remembered"]["open"] is True and out["here"] is None and out["auto"] == []


# ── 收起來的摺疊裡有發光的鈕（FB-087 審查 M3）─────────────────────────────────
# 入伍段第一道軍令那一步，玩家把「此地還能做」收起來之後，發光的巡哨／傳道／保境安民藏在裡面：沒有光、也沒有「在下面 ↓」。
# 現在摺疊收著時光改給它的標題列（同一個 .glow），「在下面 ↓」把標題列當目標；打開之後光回到鈕上。
# 假 DOM 裡的摺疊：一個假摺疊（開著與否看 state.open）、一顆假的標題列、一顆發光的鈕；鈕的 closest("details:not([open])")
# 只在摺疊收著時才回摺疊（跟真的 DOM 一樣）；"#page .glow" 像真的 querySelector 一樣回第一個有 .glow 的元素，位置照 rects。
FAKE_FOLD = """
const state = { open: false };
const summary = T.el([]), duty = T.button("act:duty");
const box = { querySelector: (sel) => (sel === ":scope > summary" ? summary : null) };
duty.closest = (sel) => (sel === "details:not([open])" && !state.open ? box : null);
const rects = new Map([[summary, { top: 740, bottom: 802 }], [duty, { top: 0, bottom: 0 }]]); // 收著的鈕量不到位置：全是 0
Object.defineProperty(T.qs, "#page .glow", { configurable: true, get: () => {
  const lit = T.fake.list.find((e) => e.classes.has("glow"));
  return lit ? { getBoundingClientRect: () => rects.get(lit) || { top: 500, bottom: 560 } } : null;
} });
const inserted = [];
T.qs[".card.guide .guide-head"] = { firstElementChild: { insertAdjacentHTML: (pos, html) => inserted.push(html) }, querySelector: () => null };
T.qs[".tabs"] = { getBoundingClientRect: () => ({ top: 756 }) };
const glowing = () => ({ summary: summary.classes.has("glow"), button: duty.classes.has("glow") });
"""


def test_a_closed_fold_with_the_glowing_button_inside_glows_its_summary_instead(glowing):
    out = run(glowing, _script(FAKE_FOLD + """
      H.applyGlow();
      return glowing();"""))
    assert out == {"summary": True, "button": False}  # 看不到的鈕不發光，光改給摺疊的標題列


def test_opening_the_fold_moves_the_glow_back_to_the_button_and_closing_it_moves_it_again(glowing):
    """玩家點開、收起摺疊時 toggle 事件就重算光：不必等下一次重畫。"""
    out = run(glowing, _script(FAKE_FOLD + """
      H.applyGlow();
      const closed = glowing();
      state.open = true; toggle(true);
      const opened = glowing();
      state.open = false; toggle(false);
      return { closed, opened, closedAgain: glowing() };"""))
    assert out == {"closed": {"summary": True, "button": False}, "opened": {"summary": False, "button": True},
                   "closedAgain": {"summary": True, "button": False}}


def test_an_open_fold_keeps_the_glow_on_the_button(glowing):
    out = run(glowing, _script(FAKE_FOLD + """
      state.open = true;
      H.applyGlow();
      return glowing();"""))
    assert out == {"summary": False, "button": True}


def test_the_below_cue_points_at_the_summary_when_the_closed_fold_is_cut_off(glowing):
    """要按的東西整個在第一屏外時框上有「在下面 ↓」：目標是看得到的標題列（#page .glow 第一個有光的），不是量不到位置的鈕。"""
    out = run(glowing, _script(FAKE_FOLD + """
      H.applyGlow(); // 摺疊收著：標題列的底邊 802 在分頁列（756）底下
      const closed = inserted.length;
      inserted.length = 0;
      rects.set(duty, { top: 500, bottom: 560 }); // 打開之後鈕有了位置：整個在第一屏裡，不用再指
      state.open = true; toggle(true); // 打開之後光回到鈕
      const opened = inserted.length;
      rects.set(duty, { top: 740, bottom: 802 }); // 展開把鈕推到分頁列底下：照舊要有
      inserted.length = 0;
      toggle(true);
      return { closed, opened, pushedDown: inserted.length, html: inserted[0] };"""))
    assert out["closed"] == 1 and out["opened"] == 0 and out["pushedDown"] == 1
    assert 'data-act="guide-below"' in out["html"] and "在下面 ↓" in out["html"]


def test_a_closed_fold_whose_summary_is_on_the_first_screen_gets_no_cue(glowing):
    out = run(glowing, _script(FAKE_FOLD + """
      rects.set(summary, { top: 600, bottom: 650 });
      H.applyGlow();
      return { glowing: glowing(), cues: inserted.length };"""))
    assert out == {"glowing": {"summary": True, "button": False}, "cues": 0}


def test_a_glow_outside_any_fold_is_unchanged(glowing):
    """摺疊以外的鈕（closest 找不到收著的摺疊）：光照舊在鈕上。"""
    out = run(glowing, _script("""
      const e = T.button("act:duty");
      H.applyGlow();
      return [...e.classes];"""))
    assert out == ["glow"]
