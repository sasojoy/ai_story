"""玩法說明二（explain-2）的網頁部分：點戰況圖卡、態勢、大事、主線看的說明。
減法季批 1 起戰況圖卡在見聞・大事・大勢的最上面（trendsTopHtml）、態勢與主線的說明在本週卡「為什麼」裡、大事的說明接在本週江湖大事後面。
照 tests/test_explain_web.py 的做法把整支 app.js 放進 node 的假瀏覽器，餵它真的引擎給的 /api/main；沒有 node 就略過。"""
from __future__ import annotations

import random
import re

import pytest
from conftest import classic_rules, real_content
from test_prologue_web import run

import server
import webharness
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _season_one(**over):
    """週末設定（第一季濃縮版）的新角色、略過序章的樣子：伺服器給的 /api/main。"""
    content = real_content("weekend")
    content.config.auto_open_first_season = True
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.client = None
    m = server.main_view(game)
    m.update(over)
    return m


def _click(act):
    """在 node 裡送一次點擊：目標的 closest("[data-act]") 是一個 data-act＝act 的元素。"""
    return f'await T.docListeners.click[0]({{ target: {{ closest: () => ({{ dataset: {{ act: "{act}" }}, classList: {{ contains: () => false }} }}) }} }});'


# ── 一、戰況圖卡：點了在底下攤開說明 ─────────────────────────────


def test_tapping_the_front_cards_opens_their_explanation_below_them():
    m = _season_one()
    lines = m["status"]["war_help"]["fronts"]
    out = run(m, f"""return (async () => {{
      const closed = H.trendsTopHtml(H.S.main);
      {_click("fronts-help")}
      const opened = H.trendsTopHtml(H.S.main);
      const first = H.S.frontsOpen;
      {_click("fronts-help")}
      return {{ closed, opened, first, second: H.S.frontsOpen }};
    }})();""")
    assert out["first"] is True and out["second"] is False
    closed, opened = out["closed"], out["opened"]
    cards = re.search(r'<div class="fronts"[^>]*>', closed).group(0)
    assert 'data-act="fronts-help"' in cards and 'role="button"' in cards and 'aria-expanded="false"' in cards
    assert "war-help" not in closed  # 點開之前什麼都不多：第一屏照舊
    block = re.search(r'<div class="war-help fronts-help" id="fronts-help">(.*?)</div>', opened).group(1)
    assert re.findall(r"<p>(.*?)</p>", block) == lines  # 伺服器寫好的幾行，一行一段
    assert opened.index('id="fronts-help"') > opened.index('class="fronts"')  # 排在圖卡底下
    # 攤開只動到圖卡底下：圖卡以前的一個字都沒變
    assert opened[:opened.index('<div class="war"')] == closed[:closed.index('<div class="war"')]


def test_enter_or_space_on_the_front_cards_opens_their_explanation():
    """審查 Minor 3：圖卡是 role="button" 的 div，鍵盤也點得開（Enter、空白鍵），再按一次收起；別的鍵、別的元素不動。"""
    m = _season_one()
    out = run(m, """return (async () => {
      const cards = new T.Element();
      cards.matches = (sel) => sel === '.fronts[data-act="fronts-help"]';
      const other = new T.Element();
      other.matches = () => false;
      let prevented = 0;
      const press = (key, target) => T.docListeners.keydown.forEach((fn) => fn({ key, target, preventDefault: () => { prevented += 1; } }));
      press("Enter", cards);
      const afterEnter = H.S.frontsOpen;
      const opened = H.trendsTopHtml(H.S.main);
      press(" ", cards);
      const afterSpace = H.S.frontsOpen;
      press("a", cards);
      press("Enter", other);
      return { afterEnter, afterSpace, still: H.S.frontsOpen, opened, prevented };
    })();""")
    assert out["afterEnter"] is True and out["afterSpace"] is False and out["still"] is False
    assert 'id="fronts-help"' in out["opened"] and out["prevented"] == 2


def test_the_front_cards_button_names_the_three_values():
    """審查 Minor 4：圖卡變成 role="button" 之後，裡面的 meter 不再念得出來；鈕的名字自己帶三條戰線的值（同一份資料），畫面不變。"""
    m = _season_one()
    m["fronts"][0]["chaos"] = True
    page = run(m, "return H.trendsTopHtml(H.S.main);")
    cards = re.search(r'<div class="fronts"[^>]*>', page).group(0)
    label = re.search(r'aria-label="([^"]*)"', cards).group(1)
    for f in m["fronts"]:
        assert f"{f['name']} {f['value']}" in label
    assert f"{m['fronts'][0]['name']} {m['fronts'][0]['value']}（亂局）" in label and label.endswith("點開看說明）")
    m["status"].pop("war_help")  # 沒有說明時：照舊是一組，meter 自己念得出來
    plain = re.search(r'<div class="fronts"[^>]*>', run(m, "return H.trendsTopHtml(H.S.main);")).group(0)
    assert 'role="group"' in plain and "點開看說明" not in plain


def test_the_front_cards_are_not_a_button_without_the_server_explanation():
    """伺服器沒給說明（舊版）：照舊只是一排圖卡，不能點。"""
    m = _season_one()
    m["status"].pop("war_help")
    page = run(m, "return H.trendsTopHtml(H.S.main);", S={"frontsOpen": True})
    cards = re.search(r'<div class="fronts"[^>]*>', page).group(0)
    assert 'data-act' not in cards and 'role="group"' in cards and "war-help" not in page


def test_the_explanation_lines_are_escaped():
    m = _season_one()
    m["status"]["war_help"]["fronts"] = ["<b>粗</b>"]
    page = run(m, "return H.trendsTopHtml(H.S.main);", S={"frontsOpen": True})
    assert "&lt;b&gt;粗&lt;/b&gt;" in page and "<b>粗</b>" not in page


# ── 一、態勢、大事、主線：小標點開的面板最後接一小段說明 ─────────────────


@pytest.mark.parametrize("chip", ["stance", "quest"])
def test_the_why_panel_carries_the_stance_and_quest_explanations(chip):
    m = _season_one()
    key = m["week_card"]["label"] + m["week_card"]["when"]
    closed = run(m, "return H.weekCardHtml(H.S.main);")
    assert 'data-id="why"' in closed and "war-help" not in closed  # 要點開「為什麼」才有
    panel = run(m, "return H.weekCardHtml(H.S.main);", S={"wkOpen": {"key": key, "id": "why"}})
    block = re.search(rf'<div class="war-help {chip}-help">(.*?)</div>', panel).group(1)
    assert re.findall(r"<p>(.*?)</p>", block) == m["status"]["war_help"][chip]


def test_the_board_explanation_follows_the_weeks_news():
    m = _season_one(bulletin=["<p><strong>三十六方起義</strong></p>"])
    page = run(m, "return H.trendsTopHtml(H.S.main);")
    block = re.search(r'<div class="war-help board-help">(.*?)</div>', page).group(1)
    assert re.findall(r"<p>(.*?)</p>", block) == m["status"]["war_help"]["board"]
    assert page.index("board-help") > page.index("三十六方起義")


# ── 二、新手期江湖頁的「玩法說明」入口 ─────────────────────────────


def test_the_newbie_entry_is_the_last_line_of_the_why_panel():
    """減法季批 1：「玩法說明」入口從行動列底下搬到本週卡「為什麼」攤開的最後一行；江湖頁平常不多一行。"""
    m = _season_one()
    key = m["week_card"]["label"] + m["week_card"]["when"]
    assert 'data-act="howto-open"' not in run(m, "return H.pageJianghu();")
    panel = run(m, "return H.weekCardHtml(H.S.main);", S={"wkOpen": {"key": key, "id": "why"}})
    assert panel.count('data-act="howto-open"') == 1
    assert panel.index('data-act="howto-open"') > panel.rindex("war-help")


def test_the_newbie_entry_gives_way_with_the_notes():
    """展開移動時說明那一塊讓位（explain-1），入口跟著讓位：不把走法那張卡往下推。"""
    page = run(_season_one(), "return H.pageJianghu();", S={"wheelSel": "move"})
    assert 'class="card act-move"' in page and "howto-open" not in page


def test_the_newbie_entry_opens_the_drawer_on_the_howto_page():
    m = _season_one()
    out = run(m, f"""return (async () => {{
      {_click("howto-open")}
      return {{ sheet: H.S.sheet, open: H.S.howtoOpen, html: T.els.app.innerHTML, calls: T.calls.map((c) => c[0]) }};
    }})();""", responses={"/api/howto": {"text": "<h4>行動</h4>"}})
    assert out["sheet"] is True and out["open"] is True
    assert "/api/howto" in out["calls"]  # 跟齒輪＋「玩法說明」一樣去要那一頁
    assert 'class="howto card" id="howto"' in out["html"] and "<h4>行動</h4>" in out["html"]


def _feeling_view():
    """週末設定的新角色在潁川探索落在有所感、選做法那一步：伺服器給的 /api/main。"""
    from tianxia import insights, sensing

    content = real_content("weekend")
    content.config.auto_open_first_season = True
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.client = None
    loc = content.locations[game.state.player.location]
    sensing.start(game.state, content, insights.scenes_for(loc, content)[0], random.Random(0))
    return server.main_view(game)


def test_the_methods_keep_their_numbers_and_the_notes_sit_under_the_methods():
    """審查 I1：做法鈕照舊寫 1～4，不寫心意（輿圖「這裡能悟」加上心意，卡就成了查表）；做法底下兩行小字照舊。"""
    m = _feeling_view()
    help_ = m["sense_help"]
    assert "tags" not in help_
    page = run(m, "return H.pageJianghu();")
    assert 'class="k sense"' not in page
    for n, option in enumerate(m["options"], 1):
        assert re.search(rf'data-id="{option["id"]}"[^>]*>\s*<span class="k">{n}</span>', page)
    block = re.search(r'<div class="act-notes sense-notes">(.*?)</div>', page).group(1)
    assert re.findall(r"<p>(.*?)</p>", block) == help_["lines"]
    last = max(page.index(f'data-id="{o["id"]}"') for o in m["options"])
    assert page.index('class="act-notes sense-notes"') > last  # 排在做法後面：不把做法往下推
    assert "（城鎮）" in page  # 標題後面的地形（潁川郡是城鎮）


def test_the_kind_labels_are_drawn_when_the_server_sends_them():
    """一行恢復（sensing.SHOW_KINDS）時網頁照 tags 畫在那一小格：這一段畫法留著。"""
    m = _feeling_view()
    m["sense_help"]["tags"] = {o["id"]: kind for o, kind in zip(m["options"], "剛柔快慢")}
    page = run(m, "return H.pageJianghu();")
    for option, kind in zip(m["options"], "剛柔快慢"):
        assert re.search(rf'data-id="{option["id"]}"[^>]*>\s*<span class="k sense">{kind}</span>', page)


def test_without_the_server_help_the_methods_keep_their_numbers():
    m = _feeling_view()
    m["sense_help"] = None
    page = run(m, "return H.pageJianghu();")
    assert 'class="k sense"' not in page and "sense-notes" not in page
    assert re.search(r'<span class="k">1</span>', page)


def test_the_xinde_hint_left_the_status_bar():
    """減法季批 1（整合設計 6.2）：狀態列剩三行，心得那一句提示搬到「自己」頁（心得底下）；閒著、選項、在路上都不在狀態列。"""
    hint = "💡 你已攢下 20 點心得。點上面身上的武學練成內功、武學。"
    for over in ({}, {"journey": "往潁川郊野，還要 3 分鐘"}):
        m = _season_one()
        m["status"].update(hint=hint, **over)
        assert hint not in run(m, "return H.topHtml();")


def test_the_newbie_entry_refreshes_the_admin_view_like_the_gear():
    """審查 Nit：管理者從入口打開抽屜，跟按齒輪一樣重抓 /api/admin 與查過的那位玩家（/api/admin/player）。"""
    m = _season_one(admin=True)
    out = run(m, f"""return (async () => {{
      {_click("howto-open")}
      return T.calls.map((c) => c[0]);
    }})();""", S={"adPlayerName": "沈青衫"}, responses={"/api/howto": {"text": "<p>x</p>"}, "/api/admin/player": {"name": "沈青衫"},
                                                    "/api/admin": {}})
    assert "/api/admin" in out and "/api/admin/player" in out
