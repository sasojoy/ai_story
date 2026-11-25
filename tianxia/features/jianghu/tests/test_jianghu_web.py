"""江湖頁重排第一批（骨架）的網頁那一半：開關開著、江湖頁閒著時換成新排法（web/jianghu.js）：滿版場景圖、圖上的狀態一行與設定鈕、
地名大字與小印、旁白、四顆行動牌（移動改叫行路）；關著照舊。真的引擎（正式內容 week7）給的 /api/main。"""
from __future__ import annotations

import pytest
from test_prologue_web import run
from test_revamp_web import wan  # noqa: F401  站在大將軍府、投靠官軍、閒著

import server
import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def test_off_keeps_the_old_page(wan):  # noqa: F811
    m = server.main_view(wan)
    assert "jianghu" not in m
    page = run(m, "return H.pageJianghu();")
    assert "jh-page" not in page and 'class="card scene rv' in page


def test_on_draws_the_new_skeleton(wan):  # noqa: F811
    wan.content.config.jianghu.enabled = True
    m = server.main_view(wan)
    assert m["jianghu"]["on"] is True and "road" not in m["jianghu"]  # 閒著：沒有墨條，有遠路的步行時間（第五批）
    assert m["jianghu"]["ways"] and all(v.startswith("約") for v in m["jianghu"]["ways"].values())
    page = run(m, "return H.pageJianghu();")
    assert page.startswith('<div class="jh-page">')
    hero = page.split('class="jh-prose"')[0]
    assert 'class="jh-art"' in hero and m["art"]["src"] in hero  # 場景圖滿版
    assert 'data-act="sheet"' in hero and 'data-act="hero-attrs"' in hero  # 設定鈕、名號印在圖上那一行
    assert "<h1>大將軍府</h1>" in hero
    assert 'class="card scene rv' not in page  # 舊的場景卡不畫
    acts = page.split('class="jh-acts"')[1]
    assert acts.count('class="act-ink') == 4 and "<b>行路</b>" in acts and "<b>移動</b>" not in acts and "<b>軍務</b>" in acts and "<b>交友</b>" not in acts
    assert 'class="jh-blk jh-places"' in page and 'class="jh-blk jh-people"' in page and 'class="here-row"' not in page  # 這裡的人（第三批）、去處（第四批）


def test_on_but_on_the_road_keeps_the_road_page(wan):  # noqa: F811
    wan.content.config.jianghu.enabled = True
    m = server.main_view(wan)
    m["on_road"] = True
    assert "jh-page" not in run(m, "return H.pageJianghu();")


def test_bots_get_no_switch(wan):  # noqa: F811
    wan.content.config.jianghu.enabled = True
    wan.state.player.bot = True
    assert "jianghu" not in server.main_view(wan)


def test_eye_card_one_thing_and_the_rest_in_the_sheet(wan):  # noqa: F811
    """第二批：眼下卡只擺一件、其餘收進「另有 N 件」；屬性點也算一件；按「另有」打開清單。"""
    wan.content.config.jianghu.enabled = True
    wan.state.player.stat_points = 6
    m = server.main_view(wan)
    page = run(m, "return H.pageJianghu();")
    assert len(__import__("re").findall(r'class="jh-eye[ "]', page)) == 1
    eye = page.split('aria-label="眼下"')[1].split('class="jh-acts"')[0]
    assert "data-act=" in eye  # 那一件有鈕可按
    sheet = run(m, 'H.S.jhSheet = "eye"; return H.pageJianghu();')
    assert "屬性" in sheet and "眼下的事" in sheet
    assert "○" not in page and "？" not in page


def test_people_row_and_figure_card(wan):  # noqa: F811
    """第三批：這裡的人一排（大勢人物立繪方格），人物的護衛、犒軍、挑戰收進他的卡，不散在此地可為；點人物拉起人物卡。"""
    wan.content.config.jianghu.enabled = True
    m = server.main_view(wan)
    figs = m["figures_here"]
    assert figs
    page = run(m, "return H.pageJianghu();")
    assert 'class="jh-blk jh-people"' in page and 'class="people-row"' not in page
    for f in figs:
        assert f'data-act="fig-open" data-id="{f["id"]}"' in page.split('class="jh-blk jh-people"')[1]
    aid = [i for f in figs for i in f["aid"]]
    here = page.split('class="here-row"')[1] if 'class="here-row"' in page else ""
    assert not any(f'data-id="{i}"' in here for i in aid)
    card = run(m, f'H.S.fig = "{figs[0]["id"]}"; return H.pageJianghu();')
    assert 'class="sheet jh-card jh-fig"' in card and 'class="vn-layer pick"' not in card
    assert f"<h2>{figs[0]['name']}" in card and 'data-act="fig-log"' in card


def _peer_card():
    a = dict(confirm="", amount=0, amount_min=1, choices=[], group="", pick="", text=0, note="", enabled=True)
    return {"name": "柳七", "affiliation": "官軍・鄉勇", "level": 20, "arts": [], "title": {}, "actions": [
        {**a, "action": "greet", "label": "挑釁", "arg": "taunt", "note": "可以附一句話（20 字內）", "text": 20},
        {**a, "action": "jieyi", "label": "邀他結義", "arg": "ask", "note": "要先跟他互換過名帖", "enabled": False},
        {**a, "action": "spar", "label": "答應切磋", "arg": "yes", "note": "體力 6"},
        {**a, "action": "spar", "label": "婉拒", "arg": "no"},
        {**a, "action": "discuss", "label": "論武・以「風」", "arg": "invite:insight:feng", "group": "論武", "pick": "「風」"},
        {**a, "action": "discuss", "label": "論武・以「火」", "arg": "invite:insight:huo", "group": "論武", "pick": "「火」"},
    ]}


def test_peer_card_answer_on_top_one_cell_a_kind(wan):  # noqa: F811
    """第三批補（PM 2026-11-25）：點俠客拉起同一種卡；他邀你的墨底排最上面，其餘一類一格，同類收一顆（不攤下拉選單），不能做的寫人話的原因。"""
    wan.content.config.jianghu.enabled = True
    m = server.main_view(wan)
    card = run(m, f"H.S.peer = {{ name: '柳七', card: {__import__('json').dumps(_peer_card(), ensure_ascii=False)} }}; return H.peerHtml();")
    assert "jh-pcard" in card and "peer-card" in card and "<select" not in card
    top = card.split('class="jh-dos"')[0]
    assert 'data-answer="spar"' in top and "答應切磋" in top and "婉拒" in top
    cells = card.split('class="jh-dos"')[1]
    assert cells.count('data-act="jh-peer-pick"') == 1 and "論武" in cells  # 兩樣論武收成一顆
    assert "還沒跟他換過名帖" in cells and "20 字內" not in card
    off = run(m, "H.S.peer = { name: '柳七', card: null, gone: '走了' }; H.S.main.jianghu = null; return H.peerHtml();")
    assert "jh-pcard" not in off  # 新排法關著：舊的玩家卡


def test_peers_here_marks_same_sect_only_when_on(wan):  # noqa: F811
    from tianxia.features.peers import actions

    wan.state.player.sect = "yingchuan_academy"
    assert all("kin" not in x for x in actions.peers_here(wan))
    wan.content.config.jianghu.enabled = True
    assert all(x.get("kin") in (None, True) for x in actions.peers_here(wan))


def test_no_pill_button_and_the_stamina_sheet(wan):  # noqa: F811
    """丹鈕拿掉（Joy 2026-11-25「可以」）：狀態行沒有丹，點體力條拉起體力的小卡，卡上服一顆；體力不夠灰著的牌點了也拉起它。"""
    wan.content.config.jianghu.enabled = True
    wan.state.player.stamina_pills = 5
    wan.state.player.stamina = 1
    m = server.main_view(wan)
    assert m["status"]["pills"]
    page = run(m, "return H.pageJianghu();")
    hero = page.split('class="jh-prose"')[0]
    assert 'data-act="pill"' not in hero and 'data-sheet="stam"' in hero
    assert 'data-act="jh-stam"' in page.split('class="jh-acts"')[1].split("</div>")[0]
    sheet = run(m, 'H.S.jhSheet = "stam"; return H.pageJianghu();')
    assert 'data-act="pill"' in sheet and "還有 5 顆" in sheet


def test_on_the_road_one_ink_bar_dash_and_back(wan):  # noqa: F811
    """第五批・趕路中：圖、「往某地的路上」、墨條（中間各站是刻痕，不畫圓圈）、疾行與折返；行動、人、去處都不畫。"""
    wan.content.config.jianghu.enabled = True
    far = next(loc for loc, w in server.main_view(wan)["jianghu"]["ways"].items() if w != "約 1 分鐘")
    wan.travel(far, "walk")
    m = server.main_view(wan)
    road = m["jianghu"]["road"]
    assert road["to"] == wan.content.locations[far].name and 0 <= road["done"] <= 1 and road["left"] >= 1
    assert road["dash"]["label"].startswith("疾行") and road["art"].startswith("/static/img/")
    page = run(m, "return H.pageJianghu();")
    assert page.startswith('<div class="jh-page jh-rd">') and f"往{road['to']}的路上" in page
    assert 'class="jh-road-bar"' in page and page.count('class="jh-tick"') == len(road["stops"])
    assert 'data-act="jh-go"' in page and f'data-dest="{far}"' in page and 'data-mode="dash"' in page
    assert 'data-id="road:back' in page and "jh-acts" not in page and "jh-people" not in page and "jh-signs" not in page
    assert "●" not in page and "○" not in page


def test_event_page_only_the_event(wan):  # noqa: F811
    """第五批・事件選擇中：圖、標題與小印、最後一段字（前文收起來）、選項；行動、人、去處、眼下都不畫。"""
    wan.content.config.jianghu.enabled = True
    wan.state.pending_event = "yz_market_salt"
    m = server.main_view(wan)
    assert m["jianghu"]["event"] == "遭遇"  # 不是哪條線的一段（章回寫主線、奇事寫奇事）
    page = run(m, "return H.pageJianghu();")
    assert page.startswith('<div class="jh-page jh-ev">') and "私鹽擔子" in page and ">遭遇<" in page
    assert "ev-odds" in page and not any(ch.isdigit() for ch in "".join(page.split("ev-odds")[1:]).split("</small>")[0])  # 屬性數字拿掉、只留那句話
    assert 'data-id="choice:0"' in page and "jh-acts" not in page and "jh-eye" not in page and "jh-people" not in page
    assert 'data-act="jh-ev-more"' in page and "jh-ev-before" not in page
    opened = run(m, "H.S.jhEvMore = true; return H.pageJianghu();")
    assert "jh-ev-before" in opened


def test_road_sheet_lists_a_far_errand_first(wan):  # noqa: F811
    """第五批補第四批：有事要去、卻不在鄰近的地方也列進行路清單、排最上面、掛那件事的小印，按了照輿圖出發（jh-go）。"""
    wan.content.config.jianghu.enabled = True
    m = server.main_view(wan)
    near = {o["id"][5:] for o in m["options"] if o["id"].startswith("move:")}
    far = next(loc for loc in m["jianghu"]["ways"] if loc not in near)
    m["codex"] = {**(m.get("codex") or {}), "track": [{"key": "x", "kind": "主線", "title": "某一回", "where": "某地", "loc": far}]}
    body = run(m, "H.S.jhSheet = 'road'; return H.pageJianghu();").split('role="dialog" aria-label="行路"')[1]
    first = body.split('class="jh-row"')[1]
    assert "主線" in first and "某地" in first and f'data-dest="{far}"' in first and "步行約" in first


_CARD = ("<h3>⚔ 汝南荒野・對陣 潰營悍卒</h3>\n<p>第 1 週・週五 12:08　出門一趟・遭遇<br />\n<strong>僵持</strong>　我方威力 15　對手難度 65</p>\n"
         "<p><strong>過程</strong></p>\n<ul>\n<li>第1回合　你氣血 -25</li>\n</ul>")
_NOW = ('<div class="tx-extra"><div class="tx-line">半路撞上潰營悍卒，雙方相持不下，各自退開。</div>'
        '<div class="tx-line">得：沉淵石 ×1、【基礎拳腳】熟練 +4（第1成 4/10）　失：氣血 -12、內傷 +12</div>'
        '<div class="tx-line">渡口下游有東西在水裡翻。是個孩子，眼看就要沉下去。</div></div>')


def test_fight_report_page_words_not_numbers(wan):  # noqa: F811
    """第六批・戰報（設計稿 o）：勝負一枚大印、對手當標題、一句話、得失用字（數字只在完整戰報）；往下看之後回到這一刻該有的頁。"""
    wan.content.config.jianghu.enabled = True
    m = server.main_view(wan)
    m.update(card=_CARD, card_id=7, now=_NOW)
    page = run(m, "return H.pageJianghu();")
    assert page.startswith('<div class="jh-page jh-ev jh-fight">') and "<h1>潰營悍卒</h1>" in page and 'class="jh-stamp">僵持<' in page
    chips = page.split('class="jh-gains"')[1].split("</div>")[0]
    assert "得了沉淵石" in chips and "基礎拳腳 熟了些" in chips and "氣血少了一截" in chips and "內傷加重" in chips
    assert not any(ch.isdigit() for ch in chips) and "過程" not in page and 'data-act="jh-card-on"' in page
    sheet = run(m, 'H.S.jhSheet = "fight"; return H.pageJianghu();')
    assert "我方威力 15" in sheet  # 數字在完整戰報裡
    after = run(m, "H.S.jhSheet = null; H.S.jhCardSeen = 7; return H.pageJianghu();")
    assert "jh-fight" not in after and "battle-card" not in after


def test_take_menu_moment_uses_the_event_page(wan):  # noqa: F811
    """第六批・接管選單（撞見孩子）：跟事件頁同一種元件；小印、標題與圖照伺服器給的，那一幕的話是剛剛最後一行，得失那一行不收進前文。"""
    wan.content.config.jianghu.enabled = True
    m = server.main_view(wan)
    m.update(card=_CARD, card_id=7, now=_NOW, options=[{"id": "guard:save", "label": "跳下水把他撈上來", "enabled": True, "note": ""},
                                                       {"id": "guard:leave", "label": "水太急，不管了", "enabled": True, "note": ""}])
    m["jianghu"]["take"] = {"slot": "menu", "seal": "撞見", "pack": "guard", "title": "河裡的孩子", "art": "/static/img/guard/story/meet-river.webp", "place": ""}
    assert "jh-fight" in run(m, "return H.pageJianghu();")  # 戰報先
    page = run(m, "H.S.jhCardSeen = 7; return H.pageJianghu();")
    assert page.startswith('<div class="jh-page jh-ev jh-tk jh-tk-menu">') and "<h1>河裡的孩子</h1>" in page and ">撞見<" in page
    assert "meet-river.webp" in page and "水裡翻" in page.split('class="jh-ev-txt"')[1]
    assert 'data-id="guard:save"' in page and "jh-acts" not in page and "jh-people" not in page
    opened = run(m, "H.S.jhCardSeen = 7; H.S.jhEvMore = true; return H.pageJianghu();")
    assert "相持不下" in opened and "熟練" not in opened


def test_take_slot_from_the_server(wan):  # noqa: F811
    """伺服器照 MENU_ORDER["take"] 認出接管選單的那一格：投靠的確認畫面是「投靠」，店裡（懸賞榜）不算。"""
    wan.content.config.jianghu.enabled = True
    assert "take" not in server.main_view(wan)["jianghu"]
    wan.state.player.faction = None
    wan.state.player.pending_faction = "guan"
    took = server.main_view(wan)["jianghu"].get("take")
    assert took and took["slot"] == "faction" and took["seal"] == "投靠"
