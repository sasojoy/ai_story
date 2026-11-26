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


def test_season_moments_and_seclusion(wan):  # noqa: F811
    """第六批・全服的時刻（設計稿 r、s）與閉關：籌備中、休季、閉關各是一頁；行動、人、去處都不畫。"""
    wan.content.config.jianghu.enabled = True
    m = server.main_view(wan)
    prep = run({**m, "options": [{"id": "season:preparing", "label": "籌備中", "enabled": False, "note": ""}]}, "return H.pageJianghu();")
    assert prep.startswith('<div class="jh-page jh-ev jh-season">') and "<h1>江湖未開</h1>" in prep and 'data-tab="hero"' in prep
    result = {"title": "官軍平了黃巾", "text": "<p>張角病死廣宗。</p><p>第二段。</p>", "stances": [{"side": "guan", "name": "官軍", "value": 62}, {"side": "huang", "name": "黃巾", "value": 38}],
              "fronts": [], "timeline": [], "rankings": []}
    rest_m = {**m, "options": [{"id": "season:resting", "label": "休季中", "enabled": False, "note": ""}], "season_result": result, "zhuan": {"season": 1, "title": "傳", "written": True}}
    rest = run(rest_m, "return H.pageJianghu();")
    assert "jh-rest" in rest and "<h3>官軍平了黃巾</h3>" in rest and "第二段" not in rest and "guan_win.webp" in rest and 'data-act="zhuan-open"' in rest
    assert "jh-acts" not in rest and "休季中" not in rest
    assert "最終態勢" in run(rest_m, 'H.S.jhSheet = "result"; return H.pageJianghu();')
    busy = {**m, "options": [{"id": "act:break", "label": "提前出關", "enabled": True, "note": ""}], "status": {**m["status"], "busy_hours": 2.4}}
    page = run(busy, "return H.pageJianghu();")
    assert "jh-busy" in page and "還要約 2 小時出關" in page and 'data-id="act:break"' in page and "jh-acts" not in page


def test_muster_page_then_the_strip(wan):  # noqa: F811
    """第六批・決戰集結（設計稿 q）：還沒投入時整頁是這一場（倒數、主將、投入與先不去）；先不去回到閒著的頁，集結那一條在眼下上面。"""
    wan.content.config.jianghu.enabled = True
    m = server.main_view(wan)
    m["battle_panel"] = {"name": "宛城之戰", "phase": "muster", "due": 2400, "span": 3600, "round": 0, "total": 6, "sent": 0, "present": 0, "feed": [], "beats": [], "key": "k",
                         "paused": False, "left": {"id": "guan", "name": "官軍", "mine": True}, "right": {"id": "huang", "name": "黃巾", "mine": False},
                         "chiefs": {"left": [], "right": []}, "me": None}
    m["options"] = [{"id": "battle:join:wancheng_yi", "label": "加入宛城之戰", "enabled": True, "note": ""}, *m["options"]]
    page = run(m, "return H.pageJianghu();")
    assert page.startswith('<div class="jh-page jh-ev jh-war">') and "<h1>宛城之戰</h1>" in page and 'data-id="battle:join:wancheng_yi"' in page and 'data-act="jh-muster-skip"' in page
    idle = run(m, 'H.S.jhMusterSkip = "宛城之戰"; return H.pageJianghu();')
    assert idle.startswith('<div class="jh-page') and "jh-war-strip" in idle and 'class="jh-acts' in idle


def test_guide_words_are_the_eye_card(wan):  # noqa: F811
    """第六批（新角色那一包說好）：說書人、老石的話排在眼下最前面，不另畫一個框。"""
    wan.content.config.jianghu.enabled = True
    m = server.main_view(wan)
    m["guide"] = {"speaker": "老石", "text": "城門口人多。先去探索一趟，看看這一帶。", "line": "", "end": False, "done": [], "key": "qa-step"}
    page = run(m, "return H.pageJianghu();")
    eye = page.split('aria-label="眼下"')[1].split('class="jh-acts')[0]
    assert "老石" in eye and "城門口人多。" in eye and 'data-act="guide-shut"' in eye
    assert 'class="guide' not in page  # 舊的說書人框不畫
    assert "稍後" not in eye  # 兩顆都是關掉的鈕不要（PM 11/25）
    m["guide"]["glow"] = ["act:explore"]  # 那件事本身當主鈕，旁邊一顆「知道了」
    eye = run(m, "return H.pageJianghu();").split('aria-label="眼下"')[1].split('class="jh-acts')[0]
    assert '<button class="btn jh-eye-go" data-act="choose" data-id="act:explore">去探索</button>' in eye and "知道了" in eye


def test_guide_not_doable_here_goes_last(wan):  # noqa: F811
    """PM 11/25：老石說的那件此地做不了（軍務暗著）不排第一則，排到最後；排到它時句子說去哪裡做，卡上只有「知道了」。"""
    wan.content.config.jianghu.enabled = True
    m = server.main_view(wan)
    m["guide"] = {"speaker": "老石", "text": "上頭每天發幾道軍令，自己挑一道。", "line": "看看「今日軍令」", "end": False, "done": [], "key": "qa-duty", "glow": []}
    m["options"] = [o for o in m["options"] if o["id"] != "act:duty"] + [{"id": "act:duty", "label": "巡哨", "enabled": False, "note": ""}]
    eye = lambda h: h.split('aria-label="眼下"')[1].split("</section>")[0]  # noqa: E731
    first = eye(run(m, "return H.pageJianghu();"))
    assert "看看「今日軍令」" not in first and "jh-eye-go" in first  # 別的那一則在前
    sheet = run(m, 'H.S.jhSheet = "eye"; return H.pageJianghu();')
    rows = sheet.split('<div class="jh-row">')[1:]
    assert len(rows) > 1 and "看看「今日軍令」" in rows[-1]  # 排在最後
    assert "回到自家的地盤" in rows[-1] and ">知道了<" in rows[-1] and "看今日軍令" not in rows[-1]


def test_duel_round_not_twice(wan):  # noqa: F811
    """PM 11/25：單挑卡頭寫了第 N 回合，底下那一句句首不再寫一次。"""
    wan.content.config.jianghu.enabled = True
    m = server.main_view(wan)
    m["art"] = {"kind": "bout", "src": "/static/img/events/fight.webp", "title": "黃巾渠帥・韓忠"}
    m["scene"] = "<p><strong>黃巾渠帥・韓忠</strong></p>\n<p>韓忠提刀繞著你走。</p>"
    m["card"] = "<p><strong>黃巾渠帥・韓忠</strong>（頭目戰 第 2／4 回合）</p>\n<ul><li>第 2 回合：你一記快拳打在他肩上。</li></ul>"
    m["card_id"] = 9
    m["jianghu"] = {**m.get("jianghu", {}), "take": {"slot": "duel", "seal": "單挑", "place": "/static/img/places/nanyang.webp"}}
    page = run(m, "return H.pageJianghu();")
    assert page.count("第 2") == 1 and "你一記快拳" in page


def test_free_agent_third_plaque_is_join(wan):  # noqa: F811
    """Joy 11/25「可以改」：還沒投靠的人第三顆是「投靠」；此地投得了就亮、按了走投靠確認，投不了暗著說去哪裡；投靠之後變回軍務。"""
    wan.content.config.jianghu.enabled = True
    m = server.main_view(wan)
    m["status"] = {**m["status"], "affiliation": ""}
    m["sides_card"] = {"joined": False, "cols": [{"id": "guan", "name": "官軍", "where": ["宛城"]}, {"id": "huang", "name": "黃巾", "where": ["廣宗"]}]}
    cell = lambda h: h.split('data-key="duty"')[0].rsplit("<button", 1)[1] + h.split('data-key="duty"')[1].split("</button>")[0]  # noqa: E731
    away = cell(run(m, "return H.pageJianghu();"))
    assert "投靠" in away and "off" in away and "官軍最近在宛城、黃巾最近在廣宗" in away and "軍務" not in away
    m["options"] = [*m["options"], {"id": "faction:guan", "label": "投靠官軍", "enabled": True, "note": ""}]
    here = cell(run(m, "return H.pageJianghu();"))
    assert 'data-act="choose" data-id="faction:guan"' in here and "此地可投官軍" in here and "off" not in here
    m["status"] = {**m["status"], "affiliation": "官軍"}
    m["sides_card"] = {**m["sides_card"], "joined": True}
    assert "軍務" in cell(run(m, "return H.pageJianghu();"))


def test_only_peers_here_draw_a_crowd_card_not_plus_n(wan):  # noqa: F811
    """Joy 2026-11-25「那個+2好醜」：此地沒有人物、俠客也都跟你無關時，不畫「＋N」方格，畫一張俠客卡（墨印＋「兩位俠客在此」），點了照舊拉起名單；
    前面畫了人才有「＋N」。"""
    wan.content.config.jianghu.enabled = True
    m = server.main_view(wan)
    m["figures_here"] = []
    m["here"] = [{"name": "柳七", "side": ""}, {"name": "白無垢", "side": ""}]
    people = run(m, "return H.pageJianghu();").split('class="jh-blk jh-people"')[1].split("</section>")[0]
    assert 'class="jh-crowd" data-act="jh-sheet" data-sheet="people"' in people and "兩位俠客在此" in people
    assert "jh-ic all" not in people and "＋2" not in people and "<span>柳</span><span>白</span>" in people
    m["figures_here"] = server.main_view(wan)["figures_here"][:2]
    assert m["figures_here"]
    people = run(m, "return H.pageJianghu();").split('class="jh-blk jh-people"')[1].split("</section>")[0]
    assert "jh-crowd" not in people and "jh-ic all" not in people and 'data-name="柳七"' in people and 'data-name="白無垢"' in people  # 放得下就一位一位畫
    m["here"] = [{"name": f"俠{i}", "side": ""} for i in range(9)]
    people = run(m, "return H.pageJianghu();").split('class="jh-blk jh-people"')[1].split("</section>")[0]
    assert "jh-crowd" not in people and '<button class="jh-ic all" data-act="jh-sheet" data-sheet="people">' in people and "＋9 俠客" in people
