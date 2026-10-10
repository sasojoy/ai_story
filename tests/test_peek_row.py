"""江湖頁最上面的一排小標：態勢｜大事｜主線（正式版辛第三輪，PM 2026-10-06）。
web/app.js 沒有建置步驟、也沒有前端測試框架：這裡把畫小標的函式與真的 pageJianghu 從原始碼切出來交給 node 跑
（其他不相干的畫法換成一行的假貨），檢查出來的 HTML：小標的字與數字、點了之後的內容、展開與已看過的記憶、
在各種選單上排在哪裡。沒有 node 就略過。"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

import pytest

import webharness
from conftest import real_content
from tianxia.engine import Game

ROOT = Path(__file__).parent.parent
pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = r"""
const dom = { peek: null };
const store = new Map();
if (input.storage === "throw") { // 存不了瀏覽器的儲存空間（隱私模式、被封鎖）：讀寫都丟例外，畫面也要照樣畫出來
  for (const name of ["localStorage", "sessionStorage"]) {
    Object.defineProperty(globalThis, name, { get() { throw new Error("storage denied"); }, configurable: true });
  }
} else {
  for (const [k, v] of Object.entries(input.stored || {})) store.set(k, v);
  Object.defineProperty(globalThis, "localStorage", {
    value: { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => { store.set(k, String(v)); }, removeItem: (k) => { store.delete(k); } },
    configurable: true, writable: true,
  });
}
globalThis.document = {
  getElementById: (id) => (id === "peek" ? { set outerHTML(v) { dom.peek = v; } } : null),
  querySelector: () => ({ focus() {} }),
};
const S = { nowOpen: null, sceneOpen: false, moveMode: "walk", answering: false, peekOpen: null, boardSeen: null, main: input.m, ...input.S };
const parts = [
  // pro、shown：序章（新手引導計畫一）把小標一塊一塊藏起來要看的；這裡的 m 沒有 prologue，所以全亮
  ...["esc", "pct", "pro", "shown", "STANCE_NAMES", "idleMenu", "BATTLE_MOVE_LABEL", "optLabelHtml", "PEEK_SEEN_KEY", "peekWeek",
    "peekSeason", "peekParts", "peekBlock", "optParts", "MUSTER_JOIN", "MUSTER_NOTE", "MUSTER_ARROW", "masterTalksOf",
    "BATTLE_ROUND", "BATTLE_MINE", "BATTLE_PEEK", "BATTLE_SHUT"].map(konst),
  // musterJoins、musterScene：決戰集結時還沒參戰的加入鈕畫在場景卡上（FB-105）；battleWatch、battleScene：只能觀戰的人，開打中的
  // 戰場收成一行（FB-120）；gaugeHtml、withGauge：決戰的戰局條；pageJianghu 用它們排場景卡與選項
  ...["stanceBars", "boardSeen", "markBoardSeen", "boardUnseen", "warHelp", "stancePeek", "boardPeek", "questPeek",
    "peekHtml", "peekTap", "musterJoins", "musterScene", "battleWatch", "battleScene", "gaugeHtml", "withGauge",
    "pageJianghu"].map(fn),
  // 不相干的畫法換成一行的假貨：要驗的是排在哪裡，不是它們自己長什麼樣
  `const splitChips = (html) => [html, ""], nowMore = () => "展開全文", followsMode = (id) => id.startsWith("move:");
   const fightCard = () => '<div class="fight-card"></div>', actionBar = () => '<div class="actbar"></div>';
   const MOVE_MODES = [], ROAD_LINKS = [], ROAD_TASKS = /^road:task/, FREE_TEXT_OPTION = "choice:free", SAY_OPTION = "talk:say";
   const guideHtml = () => "", frontsBlock = () => '<div class="fronts-block"></div>', ordersHtml = () => "", resultHtml = () => '<section class="result"></section>';`,
  "return { pageJianghu, peekBlock, peekTap, peekParts, peekHtml };",
];
const H = new Function("S", parts.join("\n"))(S);
H.S = S; H.dom = dom; H.store = store;
finish(new Function("H", "m", input.script)(H, input.m));
"""


def run(m, script="return H.peekBlock(m);", *, S=None, storage="memory", stored=None):
    """在 node 裡跑 app.js 的小標與 pageJianghu（tests/webharness.py）：m 是 /api/main 回的那份（S.main），script 是函式本體（可用 H 與 m）。"""
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "storage": storage, "stored": stored or {}})


@pytest.fixture
def on():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.season_one, c.config.season_days, c.config.server_max_players = True, 2.5, 2
    return c


def _status(content):
    return Game.new(content, "甲", rng=random.Random(0)).status_data()


EVENTS = ["<p><strong>甲事</strong></p>\n<p>甲事的公告。</p>", "<p><strong>乙事</strong></p>\n<p>乙事的公告。</p>"]
IDLE = ["act:explore", "act:train", "act:rest", "act:call", "move:luoyang"]


def _opts(*ids):
    return [{"id": i, "label": i, "enabled": True} for i in ids]


def view(status, *, options=IDLE, on_road=False, bulletin=None, quest="<h3>主線</h3><p>QUESTMARK</p>", **over):
    """/api/main 回的那份，只放 pageJianghu 與小標會讀的欄位。"""
    m = {
        "status": status, "options": _opts(*options), "on_road": on_road, "scene": "<p>SCENEMARK</p>", "now": "<p>NOWMARK</p>",
        "card": None, "card_id": None, "free_text": None, "quest": quest, "bulletin": EVENTS if bulletin is None else bulletin,
        "minimap": "", "guide": None, "fronts": None, "season_result": None, "orders": None, "convoy": None,
    }
    m.update(over)
    return m


def chips(html: str) -> list[dict]:
    """小標一排：(id, 開著嗎, aria-label, 裡面的字, 裡面的 HTML)。"""
    found = re.findall(
        r'<button class="peek-chip (\w+)( on)?" data-act="peek" data-id="\1" aria-expanded="(true|false)" aria-label="([^"]*)">(.*?)</button>',
        html, re.S,
    )
    return [{"id": i, "on": bool(on), "label": label, "text": re.sub(r"<[^>]+>", "", inner), "html": inner, "expanded": exp == "true"}
            for i, on, exp, label, inner in found]


def open_panel_id(page: str) -> str | None:
    """整頁裡展開著的是哪一塊（沒有展開是 None）。"""
    got = re.search(r'<div class="peek-panel (\w+)">', page)
    return got.group(1) if got else None


def panel(html: str) -> tuple[str, str] | None:
    """展開著的那一塊：(id, 裡面的 HTML)；沒有展開是 None。"""
    got = re.search(r'<div class="peek-panel (\w+)">(.*)</div></div>\s*$', html, re.S)
    return (got.group(1), got.group(2)) if got else None


# ── 小標一排：字與數字 ──────────────────────────────────────────


def test_the_row_has_the_three_chips_in_order_with_the_stance_numbers(on):
    status = _status(on)
    got = chips(run(view(status)))
    assert [c["id"] for c in got] == ["stance", "board", "quest"]
    stance, board, quest = got
    nums = [status["stances"][side] for side in ("guan", "huang", "haoqiang")]
    assert stance["text"] == "態勢" + "·".join(str(n) for n in nums)
    for side in ("guan", "huang", "haoqiang"):  # 三個數字各用自己陣營的顏色
        assert f'<b class="side-{side}">{status["stances"][side]}</b>' in stance["html"]
    assert "官軍 %d、黃巾 %d、豪強 %d" % tuple(nums) in stance["label"]  # 只靠顏色分不出誰是誰：讀的人聽得到名字
    assert board["text"] == "大事2" and "2 則" in board["label"]  # 只有「大事 N」（有新的才多一個點），不寫標題
    assert quest["text"] == "主線"


def test_the_board_chip_carries_no_title_text_but_the_panel_keeps_titles_and_bodies(on):
    """大事的標題放在小標裡，428～440px 的手機上一行放不下、整排折成兩行，點掉亮點又跳回一行（輪三審查 Important 1）：
    小標一律只有「大事 N」加一個點，不分螢幕寬窄；標題與內文都在點開的面板裡。"""
    status = _status(on)
    board = next(c for c in chips(run(view(status))) if c["id"] == "board")
    assert "甲事" not in board["html"] and "乙事" not in board["html"] and "peek-titles" not in board["html"]
    assert board["text"] == "大事2" and "甲事" not in board["label"]
    _pid, body = panel(_open(view(status), "board"))
    assert "<strong>甲事</strong>" in body and "<strong>乙事</strong>" in body and "甲事的公告。" in body and "乙事的公告。" in body


def test_the_numbers_follow_the_status_not_a_fixed_text(on):
    status = _status(on)
    status["stances"] = {"guan": 12, "huang": 88, "haoqiang": 7}
    stance = chips(run(view(status)))[0]
    assert stance["text"] == "態勢12·88·7" and "官軍 12、黃巾 88、豪強 7" in stance["label"]


@pytest.mark.parametrize("drop, missing", [
    ({"stances": None}, "stance"), ({"bulletin": []}, "board"), ({"quest": "  \n "}, "quest"), ({"quest": ""}, "quest"),
])
def test_each_chip_is_optional(on, drop, missing):
    status = _status(on)
    over = {k: v for k, v in drop.items() if k != "stances"}
    if "stances" in drop:
        status = {k: v for k, v in status.items() if k != "stances"}
    ids = [c["id"] for c in chips(run(view(status, **over)))]
    assert missing not in ids and len(ids) == 2


def test_no_chips_no_row(on):
    status = {k: v for k, v in _status(on).items() if k != "stances"}
    assert run(view(status, bulletin=[], quest="")) == ""


def test_the_season_rest_draws_no_stance_chip(on):
    """休季：態勢由結算卡取代（卡上有最終態勢），小標只剩大事與主線有東西時才畫。"""
    status = _status(on)
    got = chips(run(view(status, season_result={"title": "x"}, bulletin=[])))
    assert [c["id"] for c in got] == ["quest"]


# ── 點開的內容：跟以前摺疊卡裡的一樣，同一時間只開一個 ──────────────


def _open(m, *ids):
    """依序點小標，回最後一次畫出來的小標區（一整塊）。"""
    return run(m, "for (const id of %s) H.peekTap(id); return H.dom.peek;" % json.dumps(list(ids)))


def test_closed_by_default_with_no_panel(on):
    html = run(view(_status(on)))
    assert all(not c["on"] and not c["expanded"] for c in chips(html)) and panel(html) is None


def test_the_stance_panel_has_the_bars_the_rule_and_the_how_line(on):
    status = _status(on)
    html = _open(view(status), "stance")
    assert [c["id"] for c in chips(html) if c["on"]] == ["stance"]
    pid, body = panel(html)
    assert pid == "stance"
    for side in ("guan", "huang", "haoqiang"):
        assert f"front-bar stance side-{side}" in body  # 跟結算卡共用的 stanceBars
    assert re.search(r'<p class="stance-rule">%s</p>' % re.escape(status["stance_rule"]), body)
    assert 'class="stance-how"' in body and status["stance_notes"]["sum"] in body
    assert "收場" not in chips(html)[0]["text"]  # 收著的小標只有名稱與數字，規則在面板裡


def test_the_board_panel_lists_this_weeks_events_and_the_quest_panel_the_quest(on):
    status = _status(on)
    pid, body = panel(_open(view(status), "board"))
    assert pid == "board" and body.count('class="bulletin-item"') == 2 and "甲事的公告。" in body and "乙事的公告。" in body
    pid, body = panel(_open(view(status), "quest"))
    assert pid == "quest" and "QUESTMARK" in body and "<h3>主線</h3>" in body


def test_only_one_panel_is_open_at_a_time(on):
    status = _status(on)
    html = _open(view(status), "stance", "board")  # 開著態勢再點大事：換過去
    assert [c["id"] for c in chips(html) if c["on"]] == ["board"] and panel(html)[0] == "board"
    assert html.count("peek-panel") == 1
    html = _open(view(status), "stance", "board", "board")  # 再點一次收起
    assert not any(c["on"] for c in chips(html)) and panel(html) is None


def test_the_rule_line_follows_the_content(on):
    for ending in on.scenario.endings:
        if ending.stance_min:
            ending.stance_min = {side: 80 for side in ending.stance_min}
        if ending.stance_max:
            ending.stance_max = {side: 20 for side in ending.stance_max}
    on.config.decisive_from_week = 9
    _pid, body = panel(_open(view(_status(on)), "stance"))
    assert "第 9 週起，哪一方的態勢一到 80" in body


def test_no_rule_paragraph_without_a_rule_and_the_notes_are_escaped(on):
    status = _status(on)
    status["stance_rule"] = ""
    status["stance_notes"] = {"sum": "<b>x</b>", "haoqiang": ""}
    _pid, body = panel(_open(view(status), "stance"))
    assert "stance-rule" not in body and "<b>x</b>" not in body and "&lt;b&gt;x&lt;/b&gt;" in body


# ── 展開與已看過的記憶（寫的那一邊）──────────────────────────────


def test_an_open_panel_survives_a_poll_redraw_and_closes_in_a_new_week(on):
    status = _status(on)
    week = status["calendar"]["week"]
    script = """
      H.peekTap("stance");
      const redraw = H.pageJianghu();                       // 輪詢重畫整頁：不能把開著的面板關掉
      H.S.main = { ...m, status: { ...m.status, calendar: { ...m.status.calendar, week: m.status.calendar.week + 1 } } };
      return { redraw, nextWeek: H.pageJianghu() };
    """
    got = run(view(status), script)
    assert [c["id"] for c in chips(got["redraw"]) if c["on"]] == ["stance"] and open_panel_id(got["redraw"]) == "stance"
    assert not any(c["on"] for c in chips(got["nextWeek"])) and open_panel_id(got["nextWeek"]) is None
    assert week >= 1


def test_the_remembered_panel_goes_away_when_its_block_does(on):
    """開著的那一塊沒了（例如大事清空）：不畫面板，也不留一顆亮著的小標。"""
    status = _status(on)
    script = "H.peekTap('board'); H.S.main = { ...m, bulletin: [] }; return H.pageJianghu();"
    html = run(view(status), script)
    assert [c["id"] for c in chips(html)] == ["stance", "quest"] and open_panel_id(html) is None


def test_the_board_chip_carries_a_dot_until_it_is_opened(on):
    status = _status(on)
    script = """
      const first = H.peekBlock(m);
      H.peekTap("board");
      const opened = H.dom.peek;
      H.peekTap("board");
      const closed = H.dom.peek;
      return { first, opened, closed, redraw: H.pageJianghu(), stored: [...H.store.entries()] };
    """
    got = run(view(status), script)
    board = lambda html: next(c for c in chips(html) if c["id"] == "board")  # noqa: E731
    assert 'class="peek-dot"' in board(got["first"])["html"] and "還沒看過" in board(got["first"])["label"]
    assert 'class="peek-dot"' not in board(got["opened"])["html"]
    assert 'class="peek-dot"' not in board(got["closed"])["html"] and 'class="peek-dot"' not in board(got["redraw"])["html"]
    week = status["calendar"]["week"]
    assert got["stored"] == [[f"tx-board-seen:{status['name']}", f"{status['season']}:{week}:2"]]  # 這個瀏覽器的方便：季、週次與看過幾則


def test_a_new_week_or_a_new_event_lights_the_dot_again(on):
    status = _status(on)
    week = status["calendar"]["week"]
    script = """
      H.peekTap("board"); H.peekTap("board");
      const seen = H.peekBlock(H.S.main);
      H.S.main = { ...m, bulletin: [...m.bulletin, "<p><strong>丙事</strong></p>"] };   // 同一週又發生一件
      const another = H.peekBlock(H.S.main);
      H.S.main = { ...m, status: { ...m.status, calendar: { ...m.status.calendar, week: m.status.calendar.week + 1 } } };
      return { seen, another, nextWeek: H.peekBlock(H.S.main) };
    """
    got = run(view(status), script)
    dot = lambda html: 'class="peek-dot"' in next(c for c in chips(html) if c["id"] == "board")["html"]  # noqa: E731
    assert not dot(got["seen"]) and dot(got["another"]) and dot(got["nextWeek"])
    assert week >= 1


def test_events_that_arrive_while_the_board_is_open_count_as_seen_when_you_leave(on):
    status = _status(on)
    script = """
      H.peekTap("board");
      H.S.main = { ...m, bulletin: [...m.bulletin, "<p><strong>丙事</strong></p>"] };
      const whileOpen = H.pageJianghu();            // 開著的時候不亮點
      H.peekTap("quest");                           // 換去別的面板：離開大事就算看過新的這一件
      return { whileOpen, after: H.dom.peek };
    """
    got = run(view(status), script)
    board = lambda html: next(c for c in chips(html) if c["id"] == "board")  # noqa: E731
    assert 'class="peek-dot"' not in board(got["whileOpen"])["html"] and 'class="peek-dot"' not in board(got["after"])["html"]


def test_a_remembered_seen_count_comes_back_from_storage(on):
    status = _status(on)
    week, season = status["calendar"]["week"], status["season"]
    key = f"tx-board-seen:{status['name']}"
    quiet = chips(run(view(status), stored={key: f"{season}:{week}:2"}))
    assert 'class="peek-dot"' not in next(c for c in quiet if c["id"] == "board")["html"]
    for stored in (
        {key: f"{season}:{week}:1"}, {key: f"{season}:{week - 1}:2"}, {key: f"{season - 1}:{week}:2"}, {key: f"{week}:2"},  # 少看一則、別的週、別的季、舊格式
        {f"tx-board-seen:別人": f"{season}:{week}:2"}, {key: "亂碼"},
    ):
        lit = chips(run(view(status), stored=stored))
        assert 'class="peek-dot"' in next(c for c in lit if c["id"] == "board")["html"], stored


def test_a_new_season_does_not_inherit_last_seasons_seen_count(on):
    """週次每一季都從 1 起：上一季第 1 週看過的，下一季第 1 週的大事不能因此沒有點（輪三審查 Minor 1）。
    記憶體裡的與 localStorage 裡的都一樣，記的是（季、週、則數）。"""
    status = _status(on)
    week, season = status["calendar"]["week"], status["season"]
    key = f"tx-board-seen:{status['name']}"
    script = """
      H.peekTap("board"); H.peekTap("board");                        // 這一季看過了
      const sameSeason = H.peekBlock(H.S.main);
      H.S.main = { ...m, status: { ...m.status, season: m.status.season + 1 } };    // 下一季，週次一樣
      const nextSeason = H.peekBlock(H.S.main);
      H.peekTap("board");                                            // 下一季也打開看
      return { sameSeason, nextSeason, opened: H.dom.peek, stored: [...H.store.entries()] };
    """
    got = run(view(status), script)
    dot = lambda html: 'class="peek-dot"' in next(c for c in chips(html) if c["id"] == "board")["html"]  # noqa: E731
    assert not dot(got["sameSeason"]) and dot(got["nextSeason"]) and not dot(got["opened"])
    assert got["stored"] == [[key, f"{season + 1}:{week}:2"]]
    # 重新載入頁面（記憶體沒了，只剩 localStorage）：上一季留下的值在下一季也不算看過
    reloaded = run(view({**status, "season": season + 1}), stored={key: f"{season}:{week}:2"})
    assert dot(reloaded)


def test_everything_still_works_when_storage_throws(on):
    status = _status(on)
    script = """
      const first = H.peekBlock(m);
      H.peekTap("board");
      const opened = H.dom.peek;
      H.peekTap("board");
      return { first, opened, closed: H.dom.peek, page: H.pageJianghu() };
    """
    got = run(view(status), script, storage="throw")
    board = lambda html: next(c for c in chips(html) if c["id"] == "board")  # noqa: E731
    assert [c["id"] for c in chips(got["first"])] == ["stance", "board", "quest"] and 'class="peek-dot"' in board(got["first"])["html"]
    assert panel(got["opened"])[0] == "board"
    assert 'class="peek-dot"' not in board(got["closed"])["html"] and 'class="peek-dot"' not in board(got["page"])["html"]  # 記在這一頁的記憶裡


# ── 排在哪：除了在路上，每一種選單都排在最上面 ──────────────────────


MENUS = {
    "idle": IDLE, "event": ["choice:0", "choice:1", "choice:free"], "dialogue": ["talk:0", "talk:1", "talk:leave"],
    "battle": ["battle:guan", "battle:huang"], "audience": ["call:luzhi", "call:cancel"],
    "faction-confirm": ["faction:confirm", "faction:cancel"], "resting": ["act:stand"],
}


def _positions(html: str, menu_marker: str) -> dict[str, int]:
    return {"peek": html.find('id="peek"'), "now": html.find("NOWMARK"), "scene": html.find("SCENEMARK"), "menu": html.find(menu_marker)}


@pytest.mark.parametrize("name", list(MENUS))
def test_the_row_tops_the_page_for_every_menu_but_the_road(on, name):
    html = run(view(_status(on), options=MENUS[name]), "return H.pageJianghu();")
    pos = _positions(html, 'class="actbar"' if name == "idle" else 'class="options"')
    assert html.count('id="peek"') == 1
    assert 0 <= pos["peek"] < pos["now"] < pos["scene"] and pos["peek"] < pos["menu"], (name, pos)


def test_the_battle_menu_puts_each_moves_score_on_the_right_of_its_button(on):
    """決戰三招（決戰改版一 Task 4）：真的 pageJianghu 畫出來，三顆出招按鈕各有名字與右邊的小字，一顆一行。"""
    m = view(_status(on), options=[])
    m["options"] = [
        {"id": "battle:act:guan_strong", "label": "架起雲梯，強攻城牆（強攻・82 分）", "enabled": True},
        {"id": "battle:act:guan_hold", "label": "築圍挖塹，步步緊逼（固守・100 分）", "enabled": True},
        {"id": "battle:act:guan_raid", "label": "夜遣輕兵，探城中虛實（奇襲・41 分）", "enabled": True},
    ]
    html = run(m, "return H.pageJianghu();")
    assert html.count('<span class="b-name">') == 3 and html.count('<span class="b-move">') == 3
    assert '<span class="b-move">固守・100 分</span>' in html and "（強攻・82 分）" not in html


@pytest.mark.parametrize("options, marker", [
    (["road:back", "road:task:ask", "road:task:think"], 'class="options"'),
    (["act:rest", "road:back"], 'class="actbar"'),  # 就算選單上剛好有打坐，在路上照舊排在選項底下
])
def test_on_the_road_the_row_goes_below_the_options(on, options, marker):
    html = run(view(_status(on), options=options, on_road=True), "return H.pageJianghu();")
    pos = _positions(html, marker)
    assert html.count('id="peek"') == 1 and 0 <= pos["now"] < pos["scene"] < pos["menu"] < pos["peek"], pos


def test_the_season_rest_puts_the_result_card_on_top_and_no_stance_chip(on):
    m = view(_status(on), season_result={"title": "x"}, bulletin=[])
    html = run(m, "return H.pageJianghu();")
    assert html.index('<section class="result">') < html.index('id="peek"')
    assert [c["id"] for c in chips(html)] == ["quest"]


def test_the_page_draws_no_row_when_there_is_nothing_for_it(on):
    status = {k: v for k, v in _status(on).items() if k != "stances"}
    html = run(view(status, bulletin=[], quest=""), "return H.pageJianghu();")
    assert 'id="peek"' not in html and "peek-row" not in html


# ── 樣式與沒用的東西 ──────────────────────────────────────────


def _css() -> str:
    return re.sub(r"/\*.*?\*/", "", (ROOT / "web" / "style.css").read_text(encoding="utf-8"), flags=re.S)


def test_every_chip_is_at_least_44px_tall_and_the_row_never_cuts_a_number():
    css = _css()
    chip = re.search(r"(?m)^\.peek-chip \{([^}]*)\}", css).group(1)
    assert "min-height: 44px" in chip and "white-space: nowrap" in chip
    row = re.search(r"(?m)^\.peek-row \{([^}]*)\}", css).group(1)
    assert "flex-wrap: wrap" in row  # 再窄的螢幕寧可折行，也不截斷態勢的數字
    # 最窄（≤340px）連小箭頭也不畫；大事的標題不在小標裡（428～440px 會折行），所以沒有依螢幕寬度顯示它的規則
    assert re.search(r"@media \(max-width: 340px\) \{[^}]*\.peek-chip::after \{[^}]*display: none", css, re.S)
    assert not re.search(r"\.peek-nums \{[^}]*overflow: hidden", css)  # 態勢的數字不能被截
    assert "peek-titles" not in css
    # 小標不依螢幕寬度多畫東西：任何 @media (min-width: …) 區塊裡都不能有 .peek 的規則（別的元素愛開什麼斷點都行）
    wide = [query for query, body in _media_blocks(css) if re.search(r"\(min-width:", query) and re.search(r"\.peek", body)]
    assert wide == [], wide


def _media_blocks(css: str) -> list[tuple[str, str]]:
    """樣式表裡每一個 @media 區塊：(條件, 區塊裡的文字)。一路數大括號找到對得上的那個收尾，區塊裡的規則本身也有大括號，
    用 [^}]* 會在第一條內層規則就停下。"""
    blocks, at = [], 0
    while (start := css.find("@media", at)) != -1:
        open_at = css.index("{", start)
        depth, i = 1, open_at + 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        blocks.append((css[start + len("@media"):open_at].strip(), css[open_at + 1:i - 1]))
        at = i
    return blocks


def test_the_media_block_walker_reads_nested_rules_to_the_matching_brace():
    css = "@media (min-width: 420px) { .a { x: 1; } .peek-chip { y: 2; } } @media (max-width: 340px) { .b { z: 3; } } .c { w: 4; }"
    assert _media_blocks(css) == [
        ("(min-width: 420px)", " .a { x: 1; } .peek-chip { y: 2; } "), ("(max-width: 340px)", " .b { z: 3; } "),
    ]
    assert _media_blocks(".only { a: b; }") == []


def test_the_old_folds_and_their_helpers_are_gone():
    js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    for dead in ("stanceBelowMenu", "stanceCardHtml", "S.boardOpen", "S.stanceOpen", "details.bulletin", "details.stances",
                 'class="fold bulletin"', 'class="fold quest"', "lowCard", "topCard", "peek-titles", "bulletinTitle"):
        assert dead not in js, dead
    for dead in ("details.fold.bulletin", "details.fold.stances", ".bulletin-head", ".bulletin-titles", ".stances-head", ".stances-nums"):
        assert dead not in css, dead
    assert not re.search(r"(?m)^\.quest[ .]", re.sub(r"/\*.*?\*/", "", css, flags=re.S))  # 主線的摺疊卡樣式
