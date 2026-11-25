"""新江湖頁上線（Joy 2026-11-25「上線」）前的最後一關：舊江湖頁的網頁測試（場景卡、本週卡、此地可為、點人物、感悟、集結……）
測的那一件玩家該有的事，在新頁上各有同一條。舊頁的版面照舊在原本的檔裡測（conftest.old_page 關掉新頁）；這一檔是新頁上的那一半。
真的引擎（正式內容）給的 /api/main，開關照 week7、season21 打開。"""
from __future__ import annotations

import re

import pytest
from test_prologue_web import run
from test_revamp_web import wan  # noqa: F401  站在大將軍府、投靠官軍、閒著

import server
import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _on(game):
    game.content.config.jianghu.enabled = True
    return game


def test_idle_page_people_places_and_the_four_plaques(wan):  # noqa: F811
    """同 test_revamp_web 閒著那一頁：人物一排點得開、招募不在去處（搬去酒肆）、護衛在點了人物之後、探索牌有圖。"""
    m = server.main_view(_on(wan))
    page = run(m, "return H.pageJianghu();")
    assert page.startswith('<div class="jh-page')
    people = page.split('class="jh-blk jh-people"')[1]
    assert 'data-act="fig-open" data-id="hejin"' in people
    places = page.split('class="jh-blk jh-places"')[1]
    assert "hire:" not in places and "aid:guard:" not in places
    assert "/static/img/acts/explore.webp" in page.split('class="jh-acts')[1]


def test_figure_card_talk_guard_log_and_who_they_are(wan):  # noqa: F811
    """同 test_revamp_web 點人物：交談、護衛、往來紀錄；身分、是誰、本性（Joy 11/6），性子變了才多「如今」與紀錄。"""
    m = server.main_view(_on(wan))
    hejin = next(f for f in m["figures_here"] if f["id"] == "hejin")
    card = run(m, 'H.S.fig = "hejin"; return H.pageJianghu();').split('class="sheet jh-card jh-fig"')[1]
    assert 'data-act="fig-talk" data-id="hejin"' in card and 'data-act="fig-log" data-id="hejin"' in card and "護衛" in card
    assert hejin["intro"]["who"] in card and "<b>本性</b>" in card and "vi-now" not in card and "vi-hist" not in card
    assert "/static/img/figures/full/hejin.webp" in card
    hejin["intro"].update(now="如今的樣子", history=["第 1 週・週五 起，沒那麼優柔了"])
    card = run(m, 'H.S.fig = "hejin"; return H.pageJianghu();').split('class="sheet jh-card jh-fig"')[1]
    assert "<b>如今</b><span>如今的樣子</span>" in card and "<li>第 1 週・週五 起，沒那麼優柔了</li>" in card


def test_same_kind_actions_fold_into_one_row(wan):  # noqa: F811
    """同 test_revamp_web 設伏收一顆（Joy 11/10「同類型的 例如設伏 應該只有一個按鈕，點開才選設伏在哪」）：新頁在軍務清單裡收成一列，點開才列每一條路。"""
    wan.state.player.location = "yingshui"
    wan.state.player.joined_at = -10.0 ** 7
    m = server.main_view(_on(wan))
    roads = [o["id"] for o in m["options"] if o["id"].startswith("ambush:set:")]
    assert len(roads) >= 2
    page = run(m, "return H.pageJianghu();")
    assert not any(f'data-id="{r}"' in page for r in roads)  # 頁上不一條路一顆
    sheet = run(m, 'H.S.jhSheet = "duty"; return H.pageJianghu();').split('class="sheet jh-sheet"')[1]
    group = re.search(r'<details class="jh-group">.*?</details>', sheet, re.S).group(0)
    assert group.count("<summary") == 1 and "<b>設伏</b>" in group and all(f'data-id="{r}"' in group for r in roads)
    assert sum(sheet.count(f'data-id="{r}"') for r in roads) == len(roads)


def test_peer_card_has_title_chips(wan):  # noqa: F811
    """同 test_renown_web：玩家卡頭銜底下一排稱號小籤，點了才攤開說明、不寫數字。"""
    m = server.main_view(_on(wan))
    card = {"name": "乙", "affiliation": "散人", "level": 7, "record": "", "arts": [], "actions": [],
            "renown": {"titles": ["小有名氣", "江湖巨寇"], "path": "寇"}}
    html = run(m, "return H.peerHtml();", S={"peer": {"name": "乙", "card": card}})
    assert "jh-pcard" in html and 'class="rn-chips"' in html and '<span class="rn-chip rn-kou">江湖巨寇</span>' in html
    assert "rn-peer-help" not in html
    html = run(m, "return H.peerHtml();", S={"peer": {"name": "乙", "card": card, "renownOpen": True}})
    assert "rn-peer-help" in html and "27" not in html


def test_the_now_line_keeps_the_result_stamp(wan):  # noqa: F811
    """同 test_week_card_web（Joy 2026-10-27「看不出是成功還是失敗」）：地名底下那一句收成一行，結果小章排在最右邊、成功綠失敗紅；標題不印。"""
    head = '<div class="tx-when">剛剛　第 1 天</div><div class="tx-head"><span class="tx-title">田埂設卡・繞過去</span><span class="tx-tag">{}</span></div>'
    m = server.main_view(_on(wan))
    for tag, tone in (("失敗", " bad"), ("成功", " ok")):
        m["now"] = f'<div class="tx-now">{head.format(tag)}<div class="tx-line">你在泥裡陷到腰。</div></div>'
        prose = run(m, "return H.pageJianghu();").split('class="jh-prose')[1].split("</section>")[0]
        assert f'<span class="now-stamp{tone}">{tag}</span>' in prose and "你在泥裡陷到腰。" in prose and "田埂設卡" not in prose


def test_event_options_keep_the_icon_and_the_odds_in_words(wan):  # noqa: F811
    """同 test_week_card_web 事件選項：小圖示、做什麼；有檢定、要動手的每一顆都寫成算的那一句（Joy 10/27「每顆都寫回來」），
    屬性與數字拿掉、只留話（Joy 11/10 不把數字寫給玩家讀，第五批）。"""
    wan.state.pending_event = "jz_altar_roster"
    m = server.main_view(_on(wan))
    page = run(m, "return H.pageJianghu();")
    assert "jh-ev" in page.split(">")[0]
    seen = 0
    for oid, ev in m["event_opts"].items():
        button = re.search(rf'<button[^>]*data-id="{oid}".*?</button>', page, re.S).group(0)
        assert f'class="k ev ev-{ev["kind"] or "plain"}"' in button and ev["act"] in button
        if ev["worry"]:
            said = ev["worry"].split("：", 1)[-1]
            assert said in button and "ev-odds" in button and not re.search(r"\d", said if "：" in ev["worry"] else "")
            assert not re.search(r'ev-odds[^>]*>[^<]*\d[^<]*：', button)  # 「身法 50：」那一截不寫
            seen += 1
    assert seen


def test_the_tracker_items_live_in_the_eye_card():
    """同 codex test_the_page_top_keeps_only_the_tracker_line、test_quest_rows_are_not_listed_twice：新頁頂上沒有本週卡與進行中那一行，
    進行中的事在眼下一張卡與「另有 N 件」裡；未了之事不另列一排。"""
    from jianfa_kit import jianfa_game, ready  # noqa: PLC0415
    from test_codex import FORD, _start  # noqa: PLC0415

    game = ready(jianfa_game(), side="guan", loc=FORD)
    game.content.config.codex.enabled = True
    game.content.config.codex.tracker = True
    _on(game)
    game.sync(game.now)
    _start(game)
    game.choose("choice:0")
    m = server.main_view(game)
    page = run(m, "return H.pageJianghu();")
    assert 'aria-label="眼下"' in page and "cx-track" not in page and "wk-box" not in page and "ch-card" not in page
    m["options"] = list(m["options"]) + [{"id": "story:yesanniang", "label": "渡口帳（未了之事：到北邙山）", "enabled": False, "note": ""}]
    page = run(m, "return H.pageJianghu();")
    assert "quest-row" not in page and page.count("渡口帳") <= 1


def test_sense_methods_keep_numbers_notes_and_the_ground():
    """同 guide test_the_methods_keep_their_numbers…：感悟那一頁做法寫 1～4、底下兩行小字、標題後面的地形；正文是這一幕，不是剛剛那一句。"""
    from test_explain2_web import _feeling_view  # noqa: PLC0415

    m = _feeling_view()
    m["jianghu"] = {"on": True, "take": {"slot": "sense", "seal": "感悟", "place": "/static/img/places/yingru.webp"}}
    page = run(m, "return H.pageJianghu();")
    assert "jh-tk-sense" in page.split(">")[0]
    for n, option in enumerate(m["options"], 1):
        assert re.search(rf'data-id="{option["id"]}"[^>]*>\s*<span class="k">{n}</span>', page)
    block = re.search(r'<div class="act-notes sense-notes">(.*?)</div>', page).group(1)
    assert re.findall(r"<p>(.*?)</p>", block) == m["sense_help"]["lines"]
    assert page.index('class="act-notes sense-notes"') > max(page.index(f'data-id="{o["id"]}"') for o in m["options"])
    assert "<h1>有所感・鐵匠鋪（城鎮）</h1>" in page
    txt = page.split('class="jh-ev-txt">')[1].split('<div class="jh-ev-opts">')[0]
    shown = re.sub(r'<button class="jh-ev-more".*?</button>', "", txt, flags=re.S)  # 前文收著
    assert "街口的鐵匠鋪" in shown and "選錯了做法" not in shown


def test_two_siege_joins_one_per_line():
    """同 territory_acts test_fb553：兩場攻城同時集結，一場一顆、一顆一列（新頁是集結那一頁）。"""
    from test_conquest_web import _sieges_view  # noqa: PLC0415

    m = _sieges_view(["nanyang_road", "nanyang_wilds"], old=False)
    page = run(m, "return H.pageJianghu();")
    dos = re.findall(r'<div class="jh-dos">(.*?)</div>', page, re.S)
    row = next(d for d in dos if "battle:join:" in d)
    assert row.count('data-act="choose" data-id="battle:join:') == 2 and "jh-dos one" not in page


def test_own_name_opens_a_box_after_the_fight_report():
    """同 sense test_pressing_own_name…：打贏心魔先看戰報，往下看之後「自己取一個名字」按了不送、就地換成六字的輸入框。"""
    from test_epiphany_name_web import OWN, _naming_game  # noqa: PLC0415
    from test_epiphany_name_web import run as run_named  # noqa: PLC0415

    game = _on(_naming_game())
    m = server.main_view(game)
    first = run_named(m, "return H.pageJianghu();")
    assert "jh-fight" in first.split(">")[0] and 'data-act="jh-card-on"' in first  # 先看戰報
    out = run_named(m, f"""return (async () => {{
      await H.choose({{ classList: {{ add() {{}} }} }}, "{OWN}");
      return {{ calls: T.calls.filter((c) => c[0].startsWith("/api/")).map((c) => c[0]), naming: H.S.godNaming, page: H.pageJianghu() }};
    }})();""", S={"jhCardSeen": m["card_id"]})
    assert "/api/choose" not in out["calls"] and out["naming"] is True
    assert 'id="own-name-form"' in out["page"] and 'maxlength="6"' in out["page"] and f'data-id="{OWN}"' not in out["page"]
