"""玩法說明二（explain-2）的網頁部分：點戰況圖卡、態勢、大事、主線看的說明。
照 tests/test_explain_web.py 的做法把整支 app.js 放進 node 的假瀏覽器，餵它真的引擎給的 /api/main；沒有 node 就略過。"""
from __future__ import annotations

import random
import re

import pytest
from conftest import real_content
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
      const closed = H.pageJianghu();
      {_click("fronts-help")}
      const opened = H.pageJianghu();
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
    # 攤開只動到圖卡底下：圖卡以前的整頁一個字都沒變（「剛剛」、場景、行動列、軍令卡）
    assert opened[:opened.index('<div class="war"')] == closed[:closed.index('<div class="war"')]


def test_the_front_cards_are_not_a_button_without_the_server_explanation():
    """伺服器沒給說明（舊版）：照舊只是一排圖卡，不能點。"""
    m = _season_one()
    m["status"].pop("war_help")
    page = run(m, "return H.pageJianghu();", S={"frontsOpen": True})
    cards = re.search(r'<div class="fronts"[^>]*>', page).group(0)
    assert 'data-act' not in cards and 'role="group"' in cards and "war-help" not in page


def test_the_explanation_lines_are_escaped():
    m = _season_one()
    m["status"]["war_help"]["fronts"] = ["<b>粗</b>"]
    page = run(m, "return H.pageJianghu();", S={"frontsOpen": True})
    assert "&lt;b&gt;粗&lt;/b&gt;" in page and "<b>粗</b>" not in page


# ── 一、態勢、大事、主線：小標點開的面板最後接一小段說明 ─────────────────


@pytest.mark.parametrize("chip", ["stance", "board", "quest"])
def test_each_peek_panel_ends_with_its_explanation(chip):
    m = _season_one(bulletin=["<p><strong>三十六方起義</strong></p>"])
    week = m["status"]["calendar"]["week"]
    closed = run(m, "return H.peekBlock(H.S.main);")
    assert f'data-id="{chip}"' in closed and "war-help" not in closed  # 小標在、說明要點開才有
    panel = run(m, "return H.peekBlock(H.S.main);", S={"peekOpen": {"id": chip, "week": week}})
    block = re.search(rf'<div class="war-help {chip}-help">(.*?)</div>', panel).group(1)
    assert re.findall(r"<p>(.*?)</p>", block) == m["status"]["war_help"][chip]
    assert panel.rindex("war-help") > panel.index('class="peek-panel')  # 接在面板最後


# ── 二、新手期江湖頁的「玩法說明」入口 ─────────────────────────────


def test_the_newbie_entry_is_the_last_line_under_the_action_row():
    m = _season_one()
    assert m["status"]["howto_entry"] is True
    page = run(m, "return H.pageJianghu();")
    block = re.search(r'<div class="act-notes">(.*?)</div>', page).group(1)
    rows = re.findall(r"<p[^>]*>.*?</p>", block)
    assert 'data-act="howto-open"' in rows[-1] and "玩法說明" in rows[-1]  # 最後一行
    assert sum('data-act="howto-open"' in r for r in rows) == 1
    # 第一屏不動：入口以前的整頁（剛剛、場景、整排行動、說明那幾行）跟沒有入口時一個字都不差
    m["status"]["howto_entry"] = False
    without = run(m, "return H.pageJianghu();")
    assert 'data-act="howto-open"' not in without
    cut = page.index('<p class="howto-entry">')
    assert page[:cut] == without[:cut]


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


def test_the_xinde_hint_steps_aside_while_a_choice_card_is_up():
    """心得一付得起就提示（explain-2）：新人幾乎一直有那一行。事件、有所感這類一次一組的選項在眼前時不畫，不把最後一個選項擠下去；
    平常閒著（行動列）照畫，在路上照舊收成一行。"""
    hint = "💡 你已攢下 20 點心得。去「修練」練成內功、武學。"
    idle = _season_one()
    idle["status"]["hint"] = hint
    assert hint in run(idle, "return H.topHtml();")
    feeling = _feeling_view()
    feeling["status"]["hint"] = hint
    assert hint not in run(feeling, "return H.topHtml();")
    road = _season_one()
    road["status"].update(hint=hint, journey="往潁川郊野，還要 3 分鐘")
    road["options"] = [{"id": "act:on_road", "label": "趕路中", "enabled": False}]
    assert "road-hint" in run(road, "return H.topHtml();")


def test_the_xinde_hint_shows_while_resting_or_in_seclusion():
    """審查 I2：打坐（選單只剩「起身」）與閉關（只剩「提前出關」）是最長的空檔，修練、煉製照樣做得了，也沒有選項會被擠下去：提示照畫。"""
    content = real_content("weekend")
    content.config.auto_open_first_season = True
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.client = None
    game.state.player.stats["xinde"] = 20
    game.choose("act:rest")
    resting = server.main_view(game)
    assert [o["id"] for o in resting["options"]] == ["act:stand"] and resting["status"]["hint"]
    assert resting["status"]["hint"] in run(resting, "return H.topHtml();")
    secluded = _season_one()
    secluded["status"]["hint"] = "💡 你已攢下 20 點心得。去「修練」練成內功、武學。"
    secluded["options"] = [{"id": "act:break", "label": "提前出關", "enabled": True}]
    assert secluded["status"]["hint"] in run(secluded, "return H.topHtml();")


def test_the_drill_row_reads_drill_once():
    """FB-101：投靠黃巾、在黃巾別部營寨，行動列底下那一行以前是「操練　操練不冒險：…」。"""
    content = real_content("weekend")
    content.config.auto_open_first_season = True
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.client = None
    game.state.player.faction = "huang"
    game.state.player.location = "huangjin_camp"
    page = run(server.main_view(game), "return H.pageJianghu();")
    row = next(r for r in re.findall(r"<p><b>(.*?)</b>(.*?)</p>", page) if r[0] == "操練")
    assert (row[0] + row[1]).count("操練") == 1 and row[1].startswith("不冒險：")


def test_the_entry_line_keeps_the_notes_line_height():
    """版面釘子：入口那顆鈕跟說明同一個字級，按的範圍用內距撐大、再用同樣大小的負外距收回，所以那一行跟其他行一樣高（12px×1.5）。"""
    css = (webharness.ROOT / "web" / "style.css").read_text(encoding="utf-8")
    notes = re.search(r"^\.act-notes \{([^}]*)\}", css, re.M).group(1)
    entry = re.search(r"^\.act-notes \.howto-entry button \{([^}]*)\}", css, re.M).group(1)
    assert "font-size: 12px" in notes and "font-size: 12px" in entry and "line-height: inherit" in entry
    pad = re.search(r"padding: (\d+)px", entry).group(1)
    top, _, bottom, _ = re.search(r"margin: ([^;]+);", entry).group(1).split()
    assert top == bottom == f"-{pad}px"  # 上下的內距＝上下的負外距
