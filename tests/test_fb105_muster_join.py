"""FB-105（QA 7cc1fd7，2026-10-08，375×812）：決戰集結時「加入」收在「此地還能做」的摺疊裡。

投靠官軍、站在盧植營，廣宗決戰集結中：選單第一顆是「加入【官軍】」，可是行動列（web/app.js 的 actionBar）把五格以外的選項都收進
摺疊，它跟求見、拜師、巡哨擠在一起、不發光；場景只寫「選擇陣營加入」，老石那一則提示排在三則別的後面、也沒說按哪裡。集結只有
現實 30 分鐘，沒打開摺疊的人整場不在名單上。

現在：還沒參戰、按得下去的「加入」（自己陣營那一邊）或散人的「臨時投效」放在場景卡戰場名字那一行（加入一顆在名字旁邊，
投效兩顆在名字底下另起一行），不再收進摺疊；鈕旁邊一小句說在這裡報名（第二、三場決戰也看得到，不靠只說一次的提示）；老石、青禾、
季伯平那一則多一句。打不了這場仗的人（不是交戰的一方、已經加入或投效、不在決戰的大區、在路上）畫面不變；場景卡沒畫的時候
（在路上、序章師父說話的那幾步）鈕照舊留在選單上，不會不見。

集結那一句（「選擇陣營加入；集結期間照常行動。」）是戰鬥引擎寫的（Game._battle_scene_text），另一條線正在改戰鬥那一段：
fix-1008 裁示不動它，「在哪裡加入」寫在網頁上、鈕的旁邊（web/app.js 的 MUSTER_NOTE），集結那一句照伺服器給的原樣畫。

網頁用真實內容（週末設定）的廣宗決戰、真的 /api/main，照 tests/test_prologue_web.py 的做法把整支 app.js 放進 node
（scripts/test_for.py 改到 app.js 時靠這個檔名挑到這裡）。句子待 joy 潤：那一小句照 app.js 的 MUSTER_NOTE、MUSTER_ARROW 比對，
不在這裡再寫一次字面；這裡只認事實（哪一顆、在哪、指向哪）。"""
from __future__ import annotations

import html as htmllib
import random
import re

import pytest
from test_prologue import _to_step
from test_prologue_web import run

import server
import webharness
from tianxia.engine import Game

ROOT = webharness.ROOT
node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


# ── 共用 ─────────────────────────────────────────────


def _muster(on, who="guan", place="luzhi_camp", battle="guangzong", name="甲"):
    """廣宗決戰集結中（真實內容、週末設定）：who 是陣營或 None（散人），人在 place；提示關掉（框不在這個測試裡）。"""
    game = Game.new(on, name, rng=random.Random(0))
    game.client = None
    game.set_hints_off(True)
    p = game.state.player
    p.faction, p.location = who, place
    if battle is not None:  # None：同一個世界裡已經開著的那一場
        game.world.start_battle(on.battles[battle], now=game.now)
    return game


def _start_fighting(game):
    """集結時間撥到過去，再讀一次選單：options() 把全服戰鬥追到現在，這一場就開打。main_view 先讀場景（不推進戰鬥）、
    最後才讀選單，所以要在它之前先推進，不然場景還寫著集結、選單已經是開打的。"""
    game.world.mutate_battle(lambda b: setattr(b, "muster_deadline_real", -1.0))
    game.options()
    assert game.world.get_battle().phase == "active"


def _page(m):
    return run(m, "return H.pageJianghu();")


def _scene(page):
    return re.search(r'<section class="card scene">(.*?)</section>', page, re.S).group(1)


def _fold(page):
    hit = re.search(r'<details class="fold here"[^>]*>(.*?)</details>', page, re.S)
    return hit.group(1) if hit else ""


def _consts():
    """app.js 裡那一小句與箭頭（MUSTER_NOTE、MUSTER_ARROW）：joy 潤了字，這裡跟著讀，不必改測試。"""
    driver = 'finish(new Function(konst("MUSTER_NOTE") + "\\n" + konst("MUSTER_ARROW") + "\\nreturn { note: MUSTER_NOTE, arrow: MUSTER_ARROW };")());'
    return webharness.run(driver, {})


def _note_html(kind):
    """那一小句畫出來的樣子：字照常唸，箭頭藏起來不唸，id 給那一排鈕的 aria-describedby 用。"""
    c = _consts()
    return (f'<span class="muster-note" id="muster-note">{htmllib.escape(c["note"][kind], quote=False)}'
            f'<span aria-hidden="true"> {c["arrow"][kind]}</span></span>')


ROW_ATTRS = 'role="group" aria-label="參戰" aria-describedby="muster-note"'


# ── 加入的鈕在場景卡戰場名字那一行，不在摺疊裡 ───────────────────────


@node
def test_the_join_button_sits_by_the_battles_name_and_leaves_the_fold(on):
    m = server.main_view(_muster(on, "guan"))
    assert any(o["id"] == "battle:join:guan" and o["enabled"] for o in m["options"]) and "act:rest" in [o["id"] for o in m["options"]]
    page = _page(m)
    scene = _scene(page)
    head = re.search(r'<div class="muster-head">(.*?</div>)</div>', scene, re.S).group(1)
    # 同一行：戰場名字、說在這裡報名的那一小句（箭頭指向右邊的鈕）、加入的鈕
    assert head == ('<p><strong>廣宗決戰</strong></p>' + _note_html("join")
                    + f'<div class="options muster-join" {ROW_ATTRS}><button class="btn small primary" data-act="choose" '
                    'data-id="battle:join:guan"><span>加入【官軍】</span></button></div>')
    assert _consts()["arrow"]["join"] == "→"  # 鈕在右邊
    assert "battle:join:guan" not in _fold(page) and page.count('data-id="battle:join:guan"') == 1
    assert "此地還能做" in page  # 摺疊照樣在（求見、拜師、巡哨），只是少了加入那一顆
    # 集結那一句（戰鬥引擎寫的）照伺服器給的原樣跟在名字那一行後面：網頁只換掉第一段（名字），其餘一個字不動
    rest = m["scene"].split("</p>\n", 1)[1]
    assert "集結中，還剩現實" in rest and scene.startswith('<div class="muster-head">') and rest in scene


@node
def test_a_drifters_two_enlist_buttons_get_their_own_row_under_the_name(on):
    m = server.main_view(_muster(on, None))
    page = _page(m)
    scene = _scene(page)
    title, note, row = re.search(
        r'<div class="muster-head"><p>(.*?)</p>(<span class="muster-note".*?</span></span>)'
        rf'<div class="options muster-join wide" {ROW_ATTRS}>(.*?)</div></div>', scene, re.S).groups()
    assert title == "<strong>廣宗決戰</strong>"
    assert note == _note_html("enlist") and _consts()["arrow"]["enlist"] == "↓"  # 在名字右邊、往下指那兩顆
    assert re.findall(r'data-id="(battle:enlist:\w+)"', row) == ["battle:enlist:guan", "battle:enlist:huang"]
    # 鈕上只寫括號前那一段（「只算這一場」在那一小句裡）
    labels = {o["id"]: o["label"] for o in m["options"]}
    assert re.findall(r"<span>(.*?)</span>", row) == [labels[i].split("（")[0] for i in ("battle:enlist:guan", "battle:enlist:huang")]
    assert all("（" in labels[i] for i in ("battle:enlist:guan", "battle:enlist:huang"))
    assert "battle:enlist" not in _fold(page)
    assert scene.endswith(m["scene"].split("</p>\n", 1)[1])  # 集結那一句照伺服器給的原樣


@node
def test_a_drifter_who_arrives_after_the_fighting_started_still_gets_the_row(on):
    """開打了還沒投效的散人（臨時投效照樣按得下去，試玩回饋 2026-10-08）：那兩顆一樣畫在名字底下，不收進摺疊。"""
    game = _muster(on, None)
    _start_fighting(game)
    m = server.main_view(game)
    assert "集結中" not in m["scene"] and "回合" in m["scene"]  # 場景是開打之後的戰場
    assert [o["id"] for o in m["options"] if o["id"].startswith("battle:")] == ["battle:enlist:guan", "battle:enlist:huang"]
    page = _page(m)
    assert re.search(rf'<div class="options muster-join wide" {ROW_ATTRS}>', _scene(page))
    assert "battle:enlist" not in _fold(page) and page.count('data-id="battle:enlist:guan"') == 1


@node
def test_a_late_comer_on_your_own_side_keeps_the_ordinary_join_late_button(on):
    """開打了才到的自己人：選單只有一顆「加入戰局」（battle:join_late），本來就看得到，照舊畫成一般的鈕；不搬到名字那一行。"""
    game = _muster(on, "guan")
    _start_fighting(game)
    m = server.main_view(game)
    assert "集結中" not in m["scene"]
    assert [o["id"] for o in m["options"]] == ["battle:join_late"]
    page = _page(m)
    assert "muster-" not in page and _scene(page) == m["scene"]
    assert re.search(r'<button class="btn " data-act="choose" data-id="battle:join_late" >', page)


@node
def test_once_you_joined_the_page_is_what_it_was(on):
    """已經加入（或投效過）：「已加入」是灰的那一顆，照舊收在摺疊裡，場景卡就是伺服器給的那一段，一個字不多。"""
    for who, first in (("guan", "battle:join:guan"), (None, "battle:enlist:guan")):
        game = _muster(on, who)
        game.choose(first)
        m = server.main_view(game)
        page = _page(m)
        assert "muster-" not in page, who
        assert _scene(page) == m["scene"], who
        assert first in _fold(page), who  # 灰的「已加入」／「已臨時投效」還在摺疊裡


@node
def test_someone_who_cannot_join_sees_no_change(on):
    """不是交戰的一方（黃巾決戰沒有第三方：豪強只能觀戰）、不在決戰的大區：選單上沒有加入，場景卡照伺服器給的。"""
    off_side = _muster(on, "haoqiang", place="yingchuan", battle="huangjin_showdown")
    elsewhere = _muster(on, "guan", place="luzhi_camp", battle=None, name="乙")  # 黃巾決戰在潁川汝南，人在冀州
    for game in (off_side, elsewhere):
        m = server.main_view(game)
        assert not any(o["id"].startswith("battle:") for o in m["options"])
        page = _page(m)
        assert "muster-" not in page and _scene(page) == m["scene"]


@node
def test_with_an_event_open_the_join_button_still_sits_by_the_name_and_only_once(on):
    """集結時碰上事件（選單是一排選項、不是行動列）：加入照樣在名字那一行，不在選項裡再列一次；事件的選項照舊。"""
    game = _muster(on, "guan")
    game.state.pending_event = "jz_gz_forge"
    m = server.main_view(game)
    assert [o["id"] for o in m["options"]][0] == "battle:join:guan" and "act:rest" not in [o["id"] for o in m["options"]]
    page = _page(m)
    assert page.count('data-id="battle:join:guan"') == 1 and "muster-join" in _scene(page)
    assert 'data-id="choice:0"' in page


# ── 場景卡沒畫的時候，鈕照舊留在選單上 ─────────────────────────────


@node
def test_on_the_road_a_join_option_stays_in_the_menu(on):
    """在路上加入不了（引擎在路上不給這幾顆）；萬一選單上有，路上的場景卡收成兩行、不畫名字那一行：鈕照舊畫在選項裡，不搬、不見。"""
    m = server.main_view(_muster(on, "guan"))
    road = {**m, "on_road": True, "options": [o for o in m["options"] if o["id"] == "battle:join:guan"]}
    page = _page(road)
    assert "muster-" not in page
    assert re.search(r'<div class="options">\s*<button class="btn " data-act="choose" data-id="battle:join:guan" >', page)


@node
def test_while_the_master_talks_in_the_hut_the_enlist_buttons_stay_in_the_menu(on):
    """序章：師父在說話（框在、眼前沒有事件）時草廬那張場景卡不畫（masterTalks）。這時集結的投效鈕不搬（搬了就沒地方畫、整個不見），
    照舊收在「此地還能做」的摺疊裡，跟以前一樣。草廬在潁川汝南，長社火攻集結時新角色在序章第 2 步就有這兩顆（審查 M2 的情形）。"""
    game = Game.new(on, "沈浪", rng=random.Random(0), prologue=True)
    game.client = None
    _to_step(game, 1)
    game.world.start_battle(on.battles["changshe_fire"], now=game.now)
    m = server.main_view(game)
    enlist = [o["id"] for o in m["options"] if o["id"].startswith("battle:enlist:")]
    assert m["prologue"] is not None and m["guide"] is not None and enlist
    assert not any(o["id"].startswith("choice:") for o in m["options"]) and not m["on_road"]
    page = _page(m)
    assert '<section class="card scene">' not in page and "muster-" not in page  # 場景卡沒畫
    for oid in enlist:
        assert page.count(f'data-id="{oid}"') == 1 and oid in _fold(page)


@node
def test_a_scene_without_a_first_paragraph_puts_the_row_on_top(on):
    """認不出第一段（伺服器的場景不是 <p> 開頭）：那一小句與鈕排在卡片最上面，場景照原樣接在後面。"""
    m = server.main_view(_muster(on, "guan"))
    odd = {**m, "scene": "<h3>戰場</h3>\n<p>集結中。</p>\n"}
    scene = _scene(_page(odd))
    assert scene.startswith('<div class="muster-head">' + _note_html("join") + f'<div class="options muster-join" {ROW_ATTRS}>')
    assert scene.endswith("</div></div>\n" + odd["scene"])


@node
def test_the_button_label_is_escaped(on):
    m = server.main_view(_muster(on, "guan"))
    odd = {**m, "options": [{**o, "label": "加入【<b>官軍</b>】"} if o["id"] == "battle:join:guan" else o for o in m["options"]]}
    scene = _scene(_page(odd))
    assert "<span>加入【&lt;b&gt;官軍&lt;/b&gt;】</span>" in scene and "<b>官軍" not in scene


# ── 樣式：名字那一行不因為那顆鈕變高 ─────────────────────────────


def _css_rule(selector):
    css = re.sub(r"/\*.*?\*/", "", (ROOT / "web" / "style.css").read_text(encoding="utf-8"), flags=re.S)
    found = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert found, f"style.css 裡找不到 {selector}"
    return {k.strip(): v.strip() for k, v in (part.split(":", 1) for part in found.group(1).split(";") if ":" in part)}


def test_the_join_button_does_not_make_the_name_line_taller():
    """375×812 估過（盧植營、剛到、沒有框）：行動列下緣 666 → 加入在名字旁邊 666（鈕 38px 高，上下各 −8px，佔的高度 22px，
    不高過名字那一行；那一小句 12px 一行、放不下就省略號，不折行）；散人兩顆另起一行 693 → 737（6px 的縫＋38px）。
    這是估出來的數字，改樣式表時要重估。"""
    head = _css_rule(".scene .muster-head")
    assert head["display"] == "flex" and head["flex-wrap"] == "wrap" and head["align-items"] == "center"
    assert _css_rule(".scene .muster-head > p")["margin"] == "0"
    note = _css_rule(".scene .muster-note")
    assert note["flex"] == "1 1 0" and note["min-width"] == "0"  # 基準寬度 0：這一句永遠不會把鈕擠到下一行
    assert note["white-space"] == "nowrap" and note["text-overflow"] == "ellipsis" and note["overflow"] == "hidden"
    assert _css_rule(".scene .muster-join")["flex"] == "none"
    btn = _css_rule(".scene .muster-join .btn")
    assert btn["margin"] == "-8px 0"  # 點擊範圍 38px，佔的高度只有 22px
    wide = _css_rule(".scene .muster-join.wide")
    assert wide["flex-basis"] == "100%"
    assert _css_rule(".scene .muster-join.wide .btn")["margin"] == "0"  # 另起一行時不往上吃，免得蓋到名字
