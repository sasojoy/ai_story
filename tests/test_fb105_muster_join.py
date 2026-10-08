"""FB-105（QA 7cc1fd7，2026-10-08，375×812）：決戰集結時「加入」收在「此地還能做」的摺疊裡。

投靠官軍、站在盧植營，廣宗決戰集結中：選單第一顆是「加入【官軍】」，可是行動列（web/app.js 的 actionBar）把五格以外的選項都收進
摺疊，它跟求見、拜師、巡哨擠在一起、不發光；場景只寫「選擇陣營加入」，老石那一則提示排在三則別的後面、也沒說按哪裡。集結只有
現實 30 分鐘，沒打開摺疊的人整場不在名單上。

現在：還沒參戰、按得下去的「加入」（自己陣營那一邊）或散人的「臨時投效」放在場景卡戰場名字那一行（加入一顆在名字旁邊，
投效兩顆在名字底下另起一行），不再收進摺疊；鈕旁邊一小句說在這裡報名（第二、三場決戰也看得到，不靠只說一次的提示）；老石、青禾、
季伯平那一則多一句。打不了這場仗的人（不是交戰的一方、已經加入或投效、不在決戰的大區、在路上）畫面不變。

集結那一句（「選擇陣營加入；集結期間照常行動。」）是戰鬥引擎寫的（Game._battle_scene_text），另一條線正在改戰鬥那一段：
fix-1008 裁示不動它，「在哪裡加入」寫在網頁上、鈕的旁邊（web/app.js 的 MUSTER_NOTE），集結那一句照伺服器給的原樣畫。

網頁用真實內容（週末設定）的廣宗決戰、真的 /api/main，照 tests/test_prologue_web.py 的做法把整支 app.js 放進 node
（scripts/test_for.py 改到 app.js 時靠這個檔名挑到這裡）。句子待 joy 潤：這裡只認事實（哪一顆、在哪、指向哪），不鎖死字句。"""
from __future__ import annotations

import random
import re

import pytest
from test_prologue_web import run

import server
import webharness
from tianxia.engine import Game

ROOT = webharness.ROOT
node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


# ── 網頁：加入的鈕在場景卡戰場名字那一行，不在摺疊裡 ───────────────────────


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


def _page(m):
    return run(m, "return H.pageJianghu();")


def _scene(html):
    return re.search(r'<section class="card scene">(.*?)</section>', html, re.S).group(1)


def _fold(html):
    hit = re.search(r'<details class="fold here"[^>]*>(.*?)</details>', html, re.S)
    return hit.group(1) if hit else ""


@node
def test_the_join_button_sits_by_the_battles_name_and_leaves_the_fold(on):
    m = server.main_view(_muster(on, "guan"))
    assert any(o["id"] == "battle:join:guan" and o["enabled"] for o in m["options"]) and "act:rest" in [o["id"] for o in m["options"]]
    html = _page(m)
    scene = _scene(html)
    head = re.search(r'<div class="muster-head">(.*?</div>)</div>', scene, re.S).group(1)
    # 同一行：戰場名字、說在這裡報名的那一小句（指向右邊的鈕）、加入的鈕
    title, note, join = re.fullmatch(r'<p>(.*?)</p><span class="muster-note">(.*?)</span>(<div class="options muster-join".*)', head, re.S).groups()
    assert title == "<strong>廣宗決戰</strong>"
    assert "報名" in note and "這裡" in note and note.endswith("→")
    assert re.fullmatch(r'<div class="options muster-join"[^>]*><button class="btn small primary" data-act="choose" data-id="battle:join:guan">'
                        r"<span>加入【官軍】</span></button></div>", join)
    assert "battle:join:guan" not in _fold(html) and html.count('data-id="battle:join:guan"') == 1
    assert "此地還能做" in html  # 摺疊照樣在（求見、拜師、巡哨），只是少了加入那一顆
    # 集結那一句（戰鬥引擎寫的）照伺服器給的原樣跟在名字那一行後面：網頁只換掉第一段（名字），其餘一個字不動
    rest = m["scene"].split("</p>\n", 1)[1]
    assert "集結中，還剩現實" in rest and scene.endswith(rest)


@node
def test_a_drifters_two_enlist_buttons_get_their_own_row_under_the_name(on):
    m = server.main_view(_muster(on, None))
    html = _page(m)
    scene = _scene(html)
    title, note, row = re.search(
        r'<div class="muster-head"><p>(.*?)</p><span class="muster-note">(.*?)</span><div class="options muster-join wide"[^>]*>(.*?)</div></div>',
        scene, re.S).groups()
    assert title == "<strong>廣宗決戰</strong>"
    assert "臨時投效" in note and "只算這一場" in note and note.endswith("↓")  # 在名字右邊、往下指那兩顆
    assert re.findall(r'data-id="(battle:enlist:\w+)"', row) == ["battle:enlist:guan", "battle:enlist:huang"]
    assert re.findall(r"<span>(.*?)</span>", row) == ["臨時投效【官軍】", "臨時投效【黃巾軍】"]  # 「只算這一場」寫在那一小句裡
    assert "battle:enlist" not in _fold(html)
    assert scene.endswith(m["scene"].split("</p>\n", 1)[1])  # 集結那一句照伺服器給的原樣


@node
def test_once_you_joined_the_page_is_what_it_was(on):
    """已經加入（或投效過）：「已加入」是灰的那一顆，照舊收在摺疊裡，場景卡就是伺服器給的那一段，一個字不多。"""
    for who, first in (("guan", "battle:join:guan"), (None, "battle:enlist:guan")):
        game = _muster(on, who)
        game.choose(first)
        m = server.main_view(game)
        html = _page(m)
        assert "muster-" not in html, who
        assert _scene(html) == m["scene"], who
        assert first in _fold(html), who  # 灰的「已加入」／「已臨時投效」還在摺疊裡


@node
def test_someone_who_cannot_join_sees_no_change(on):
    """不是交戰的一方（黃巾決戰沒有第三方：豪強只能觀戰）、不在決戰的大區：選單上沒有加入，場景卡照伺服器給的。"""
    off_side = _muster(on, "haoqiang", place="yingchuan", battle="huangjin_showdown")
    elsewhere = _muster(on, "guan", place="luzhi_camp", battle=None, name="乙")  # 黃巾決戰在潁川汝南，人在冀州
    for game in (off_side, elsewhere):
        m = server.main_view(game)
        assert not any(o["id"].startswith("battle:") for o in m["options"])
        html = _page(m)
        assert "muster-" not in html and _scene(html) == m["scene"]


@node
def test_with_an_event_open_the_join_button_still_sits_by_the_name_and_only_once(on):
    """集結時碰上事件（選單是一排選項、不是行動列）：加入照樣在名字那一行，不在選項裡再列一次；事件的選項照舊。"""
    game = _muster(on, "guan")
    game.state.pending_event = "jz_altar_talisman"
    m = server.main_view(game)
    assert [o["id"] for o in m["options"]][0] == "battle:join:guan" and "act:rest" not in [o["id"] for o in m["options"]]
    html = _page(m)
    assert html.count('data-id="battle:join:guan"') == 1 and 'muster-join' in _scene(html)
    assert 'data-id="choice:0"' in html


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
