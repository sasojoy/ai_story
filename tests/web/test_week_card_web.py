"""江湖頁減法（減法季批 1，整合設計第六章；本週卡照 Joy 2026-10-24 挑的乙案）的網頁部分：本週卡（灰線＋只剩「你這一步」的卡）、
還沒投靠的人的三方卡、「剛剛」收成一行、事件選項前的小圖示、灰掉的主鈕點了浮出為什麼。照 tests/test_prologue_web.py 的做法把整支網頁放進 node 的假瀏覽器，餵它真的引擎給的 /api/main；
沒有 node 就略過。（以前那一排小標的測試 test_peek_row.py 跟著小標一起拿掉了）"""
from __future__ import annotations

import random
import re
from pathlib import Path

import pytest
from conftest import real_content
from test_prologue_web import run

import server
import webharness
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

ROOT = Path(__file__).resolve().parents[2]


def _main(*, faction=None, event=None, **over):
    content = real_content("week7")
    content.config.auto_open_first_season = True
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.client = None
    game.state.player.faction = faction
    if event:
        game.state.pending_event = event
    m = server.main_view(game)
    m.update(over)
    return m


def _why(m):
    return {"wkOpen": {"key": m["week_card"]["label"] + m["week_card"]["when"], "id": "why"}}


def _title(step):
    return step["text"].split("：", 1)[0]


def test_the_week_card_is_a_step_card_and_a_strip():
    """「眼下要事」（Joy 2026-10-26 改名，以前叫「你這一步」）平常收成兩行：標題（點了攤說明）、做完得什麼與去輿圖；右上一顆 ×。
    灰線（第幾段、主題、兩軍態勢，整條是「為什麼」的鈕）右邊也一顆 ×。幾塊是江湖頁的兄弟（灰線那一組 data-wk="top"、卡那一組 "low"），不包一層。"""
    m = _main()
    w = m["week_card"]
    html = run(m, "return H.weekCardHtml(H.S.main);")
    strip = re.search(r'<button id="week" class="wk-strip"[^>]*>.*?</button>', html, re.S).group(0)
    assert 'data-act="wk" data-id="why"' in strip and w["when"] in strip and w["theme"] in strip
    assert "官 " in strip and "黃 " in strip and "豪強" not in strip
    card = re.search(r'<section data-wk="low" class="card wk-card".*?</section>', html, re.S).group(0)
    assert '<span class="wk-lab">眼下要事</span>' in card and f'<b class="wk-title">{_title(w["steps"][0])}</b>' in card
    assert "你這一步" not in html
    go = 'data-act="newbie-go"' if w["steps"][0]["kind"] == "newbie" else 'data-act="tab" data-tab="map"'  # 新手目標是「去做」，其餘「去輿圖」
    assert go in card and 'data-act="wk-next"' not in card and "wk-detail" not in card  # 說明與換一件收著
    assert 'data-act="wk-hide" data-id="card"' in card and 'data-act="wk-hide" data-id="strip"' in html
    assert html.index("wk-strip") < html.index("wk-card")  # 兩組接在一起時灰線那一組在前（江湖頁上分開排：灰線在行動列上面）
    for word in ("為什麼</button>", "換一件事", "輿圖 ›</button>", "簽到", "wk-links"):
        assert word not in html
    assert "wk-panel" not in html


def test_tapping_the_title_opens_the_detail_and_another_thing():
    m = _main()
    w = m["week_card"]
    step = {"wkOpen": {"key": w["label"] + w["when"], "id": "step"}}
    card = re.search(r'<section data-wk="low" class="card wk-card on".*?</section>', run(m, "return H.weekCardHtml(H.S.main);", S=step), re.S).group(0)
    assert 'data-act="wk-next"' in card and ("wk-detail" in card) == ("：" in w["steps"][0]["text"])  # 說明是冒號後那一截


def test_each_step_says_what_you_get_for_it():
    """每一件後面寫做完得什麼（伺服器的 reward：新手目標、懸賞、託付原本的賞；軍令寫記功幾次）；沒有 reward 的那一件不寫。"""
    m = _main()
    w = m["week_card"]
    assert w["steps"][0].get("reward")
    html = run(m, "return H.weekCardHtml(H.S.main);")
    assert f'<span class="wk-gain">{w["steps"][0]["reward"]}</span>' in html
    w["steps"][0].pop("reward")
    assert '<span class="wk-gain"></span>' in run(m, "return H.weekCardHtml(H.S.main);")


def test_the_cross_hides_until_tomorrow():
    """× 收到換日：同一天收著的那一塊不畫；換了一天又回來。兩塊都收了留一個空記號（wkRepaint 找得到位置）。"""
    m = _main()
    day = str(m["status"].get("calendar", {}).get("day") or m["status"].get("day"))
    card_gone = run(m, "return H.weekCardHtml(H.S.main);", S={"wkHide": {"day": day, "parts": ["card"]}})
    assert "wk-card" not in card_gone and 'id="week"' in card_gone
    both = run(m, "return H.weekCardHtml(H.S.main);", S={"wkHide": {"day": day, "parts": ["card", "strip"]}})
    assert "wk-card" not in both and 'id="week"' not in both and "wk-note" not in both and 'class="wk-none"' in both
    stale = run(m, "return H.weekCardHtml(H.S.main);", S={"wkHide": {"day": "上一天", "parts": ["card", "strip"]}})
    assert "wk-card" in stale and 'id="week"' in stale


def test_the_action_bar_sits_between_the_strip_and_the_step_card():
    """Joy 2026-10-26：四顆行動鈕一定在第一屏。行動列上面只留灰線（一行），「眼下要事」與師父的話排在行動列底下。"""
    m = _main(faction="guan")
    m["guide"] = {"speaker": "想起師父說過", "text": "多學一門。", "end": True, "done": [], "pending": False}
    page = run(m, "return H.pageJianghu();")
    bar = page.index("act-bar")
    assert page.index('id="week"') < bar < page.index("wk-card") < page.index('class="card guide"')
    assert 'data-act="guide-ack" aria-label="知道了"' in page  # 序章以外右上角一顆 ×，做的事同「知道了」


def test_another_thing_steps_through_the_candidates():
    m = _main()
    steps = m["week_card"]["steps"]
    assert len(steps) > 1
    key = m["week_card"]["label"] + m["week_card"]["when"]
    second = run(m, "return H.weekCardHtml(H.S.main);", S={"wkStep": {"key": key, "i": 1}})
    assert _title(steps[1]) in second and _title(steps[0]) not in second
    stale = run(m, "return H.weekCardHtml(H.S.main);", S={"wkStep": {"key": "上一週", "i": 1}})  # 換了一週：從第一件重來
    assert _title(steps[0]) in stale


def test_why_opens_the_sides_table_the_next_event_and_the_howto_entry():
    m = _main()
    closed = run(m, "return H.weekCardHtml(H.S.main);")
    assert "wk-panel" not in closed
    panel = run(m, "return H.weekCardHtml(H.S.main);", S=_why(m))
    assert 'class="card wk-panel why"' in panel and 'class="sides"' in panel and 'class="wk-strip on"' in panel
    for col in m["sides_card"]["cols"]:
        assert col["name"] in panel and col["where"][0] in panel
    assert 'data-act="howto-open"' in panel


def test_a_loner_gets_the_sides_card_first_and_a_member_does_not():
    loner = run(_main(), "return H.pageJianghu();")
    assert '<details class="card sides-first">' in loner and loner.index("sides-first") < loner.index("wk-card")  # 收著：不把行動列推出第一屏
    assert "官軍在長社" in loner
    assert '<details class="card sides-first" open>' in run(_main(), "return H.pageJianghu();", S={"sidesOpen": True})
    member = run(_main(faction="guan"), "return H.pageJianghu();")
    assert "sides-first" not in member and "wk-card" in member


def test_the_old_peek_row_fronts_and_minimap_are_gone_from_the_jianghu_page():
    page = run(_main(faction="guan"), "return H.pageJianghu();")
    assert 'class="peek"' not in page and 'class="fronts"' not in page and 'class="mini"' not in page


def test_the_now_card_is_one_line_until_tapped():
    now = '<div class="tx-now"><div class="tx-when">剛剛　第 1 天</div><div class="tx-head">甲事</div><p>第一句 &amp; 第二句</p></div>'
    m = _main(now=now)
    shut = run(m, "return H.pageJianghu();")
    one = re.search(r'<button class="now-one".*?</button>', shut, re.S).group(0)
    assert '<span class="tx-when">剛剛　第 1 天</span>' in one and "甲事　第一句 &amp; 第二句" in one
    opened = run(m, "return H.pageJianghu();", S={"nowOpen": now})
    assert "now-one" not in opened and 'class="now open' in opened


def _now_shut(now):
    shut = run(_main(now=now), "return H.pageJianghu();")
    return re.search(r'<div class="now one">.*?(?=<section|<div class="card|$)', shut, re.S).group(0)


def test_the_result_stamp_stays_outside_the_cut_line():
    # Joy 2026-10-27「看不出是成功還是失敗」：結果標記拿出來排在那一行最右邊，不跟著被「…」切掉；成功綠、失敗紅
    head = '<div class="tx-when">剛剛　第 1 天</div><div class="tx-head"><span class="tx-title">田埂設卡・脫了鞋，涉過旁邊的爛泥溝繞過去</span><span class="tx-tag">{}</span></div>'
    for tag, tone in (("失敗", " bad"), ("成功", " ok"), ("韓鐵出手・失敗", " bad"), ("得料", "")):
        box = _now_shut(f'<div class="tx-now">{head.format(tag)}<div class="tx-line">你在泥裡陷到腰。</div></div>')
        text = re.search(r'<span class="now-text-one">(.*?)</span>', box).group(1)
        assert tag not in text and "田埂設卡" in text
        assert f'<span class="now-stamp{tone}">{tag}</span>' in box
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    assert re.search(r"\.now-one \.now-text-one \{[^}]*text-overflow: ellipsis", css)
    assert re.search(r"\.now-one \.now-stamp \{[^}]*flex: none", css)


def test_the_items_you_got_show_without_opening():
    # Joy 2026-10-27「材料事件，第二行…顯示獲得的物品跟數量，不用展開」：「得：」那一行的物品排成小籤；數值得失那一排本來就有，不重複
    lines = ("你出了大路。", "得：驚羽 ×2、銀兩 +5", "獲得 驚羽 ×1", "自家地盤，多撿了一份。", "獲得 驚羽 ×1")
    body = "".join(f'<div class="tx-line">{x}</div>' for x in lines)
    head = '<div class="tx-when">剛剛　第 1 天</div><div class="tx-head"><span class="tx-title">出門一趟</span><span class="tx-tag">得料</span></div>'
    box = _now_shut(f'<div class="tx-now">{head}{body}</div>')
    assert re.findall(r'<span class="tx-chg tx-up now-item">(.*?)</span>', box) == ["驚羽 ×2"]  # 銀兩是數值，在得失那一排
    # 沒有「得：」那一行：照「獲得 X ×N」加總
    body = "".join(f'<div class="tx-line tx-new">{x}</div>' for x in ("獲得 精鐵砂 ×1", "獲得 精鐵砂 ×2", "獲得 柳絲綿 ×1"))
    box = _now_shut(f'<div class="tx-now">{head}{body}</div>')
    assert re.findall(r'now-item">(.*?)</span>', box) == ["精鐵砂 ×3", "柳絲綿 ×1"]
    # 什麼都沒拿到：不多一排
    assert "tx-chgs" not in _now_shut(f'<div class="tx-now">{head}<div class="tx-line">一路無事。</div></div>')


def test_event_options_get_an_icon_and_keep_only_the_action():
    m = _main(event="jz_altar_roster")
    opts = m["event_opts"]
    page = run(m, "return H.pageJianghu();")
    kinds = {v["kind"] for v in opts.values()}
    assert "fight" in kinds
    for oid, ev in opts.items():
        button = re.search(rf'<button[^>]*data-id="{oid}".*?</button>', page, re.S).group(0)
        assert f'class="k ev ev-{ev["kind"] or "plain"}"' in button and ev["act"] in button
        assert ("ev-odds" in button) is bool(ev["worry"]) and ("ev-worry" in button) is (not ev["sure"])
        if ev["worry"]:
            assert f'<small class="opt-note ev-odds' in button and ev["worry"] in button


def test_every_checked_or_fought_option_shows_its_odds():
    """Joy 2026-10-27 在決定卡上選「每顆都寫回來」：有檢定的選項一定看得到「屬性 數值：心裡話」、動手的一定看得到對手與勝算，
    有把握的也寫（批 1 原本只在沒把握時才寫）。"""
    from tianxia import events as event_rules  # noqa: PLC0415

    m = _main(event="jz_altar_roster")
    content = real_content("week7")
    ev = content.events["jz_altar_roster"]
    page = run(m, "return H.pageJianghu();")
    names = set(content.config.stat_names.values())
    seen = set()
    for oid, view in m["event_opts"].items():
        ch = ev.choices[int(oid.split(":")[1])]
        button = re.search(rf'<button[^>]*data-id="{oid}".*?</button>', page, re.S).group(0)
        if ch.check:
            stat = content.config.stat_names[ch.check.stat]
            assert view["worry"].startswith(f"{stat} ") and "：" in view["worry"] and view["worry"] in button
            seen.add("check")
        elif ch.combat:
            assert view["worry"].startswith("對手：") and "・" in view["worry"] and view["worry"] in button
            seen.add("fight")
        else:
            assert view["worry"] == "" and "ev-odds" not in button
    assert {"fight"} <= seen and names


def test_a_greyed_cell_says_why_when_tapped():
    m = _main()
    page = run(m, "return H.actionBar(H.S.main);")
    for cell in re.findall(r'<button class="act-ink off"[^>]*>', page):
        assert 'data-act="opt-why"' in cell and re.search(r'data-why="[^"]+"', cell) and 'aria-disabled="true"' in cell


def _chapter_main(loc: str):
    """章回主線（chapters.card）：投靠官軍、站在 loc，同步過一次（第一回開了）的 /api/main。"""
    from jianfa_kit import ready

    content = real_content("week7")
    content.config.auto_open_first_season = True
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.client = None
    ready(game, side="guan", loc=loc, level=20)
    game._story_tick()  # noqa: SLF001
    return server.main_view(game)


def test_the_chapter_card_says_which_chapter_what_next_and_where_to_go():
    m = _chapter_main("luoyang_palace")
    c = m["week_card"]["chapter"]
    html = run(m, "return H.chapterCardHtml(H.S.main);")
    assert '<span class="ch-no">第一回</span><b class="ch-title">投軍長社</b>' in html
    assert f"波才大敗朱儁・{c['at']}" in html and "下一步：到長社北門</p>" in html  # 說明裡已經有地名：不再補（長社・幾分）
    assert 'data-act="tab" data-tab="map"' in html and "官軍已有 0 人做完這一回" in html
    m = _chapter_main("changshe")  # 人就在長社：卡上一顆「去做」（按未了之事那一顆），不叫人去輿圖
    html = run(m, "return H.chapterCardHtml(H.S.main);")
    assert 'data-act="choose" data-id="story:ch_guan_1">去做 ›' in html and 'data-tab="map"' not in html
    m["week_card"]["chapter"].update(scene=True, here=False, hint="眼前這一幕：北門")  # 那一幕端出來了：沒有按鈕
    html = run(m, "return H.chapterCardHtml(H.S.main);")
    assert "眼前這一幕：北門" in html and "下一步" not in html and "ch-go" not in html
    m["week_card"].pop("chapter")
    assert run(m, "return H.chapterCardHtml(H.S.main);") == ""


def test_the_chapter_card_writes_the_battles_state_once_it_is_mustering_or_fighting():
    """U-17（手機介面自檢 2026-10-31）：那一件大事的決戰提早開了，右上角寫「集結中」「開打了」，不再寫排定的時刻。"""
    m = _chapter_main("luoyang_palace")
    c = m["week_card"]["chapter"]
    for live, word in (("muster", "集結中"), ("active", "開打了")):
        c["live"] = live
        html = run(m, "return H.chapterCardHtml(H.S.main);")
        assert f'<span class="ch-at">波才大敗朱儁・{word}</span>' in html and c["at"] not in html
    c["live"] = None
    assert f"波才大敗朱儁・{c['at']}" in run(m, "return H.chapterCardHtml(H.S.main);")
