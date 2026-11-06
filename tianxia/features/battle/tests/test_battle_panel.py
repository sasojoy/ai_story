"""決戰的戰場面板（Joy 2026-11-06「大決戰優化：要更讓玩家投入在決戰中」，設計稿 JsNAYuqgMn3JJoTENCKza6 方案甲）。

引擎給 main.battle_panel（features/battle/panel.py：一個倒數、兩邊上陣人物的血條、主將令、自己的陣中氣血、一回合一行的戰報、
關鍵時刻），網頁（web/battle.js）畫在江湖頁最上面、出招鈕緊接在底下；狀態列的氣血在決戰裡換成陣中氣血（Joy 11/6「決戰時顯示的血量
跟決戰內實際血量不一致」）。"""
# 樣式在 web/battle_panel.css（排在 legacy.css 後面）；寫在這裡 test_for 改包檔時才挑得到
from __future__ import annotations

import random

import pytest
from test_battle_gauge import node, showdown  # noqa: F401（showdown 是 fixture）
from test_prologue_web import run

import server
from tianxia.core.battle_base import Commander
from tianxia.engine import Game


def _open(a):
    a.world.mutate_battle(lambda x: setattr(x, "muster_deadline_real", -1.0))
    a.options()


def _chiefs(game):
    """測試內容的決戰沒有上陣人物：兩邊各派一位主將、一位副將（照 generals.on_muster 派上來的樣子）。"""
    def put(x):
        x.commanders = [Commander(fid=fid, name=name, faction=side, rank=rank, neili=1000, neili_cap=1000)
                        for fid, name, side, rank in (("huangfusong", "皇甫嵩", "guan", 0), ("zhujun", "朱儁", "guan", 1),
                                                      ("bocai", "波才", "huang", 0), ("liupi", "劉辟", "huang", 1))]
    game.world.mutate_battle(put)


def _panel(game):
    return server.main_view(game)["battle_panel"]


# ── 資料 ──────────────────────────────────────────────


def test_no_panel_without_a_battle(on):
    g = Game.new(on, "丙", rng=random.Random(0))
    g.client = None
    assert server.main_view(g).get("battle_panel") is None


def test_the_muster_panel_counts_down_and_shows_my_battle_hp(showdown):
    _, a, b = showdown
    p = _panel(a)
    battle = a.world.get_battle()
    me = battle.participants["甲"]
    assert p["phase"] == "muster" and 0 < p["due"] <= p["span"] and p["feed"] == [] and p["beats"] == []
    assert p["left"]["name"] == "官軍" and _panel(b)["left"]["name"] == "黃巾軍"
    assert p["me"] == {"hp": round(me.neili), "cap": round(me.neili_cap), "out": False, "sent": None, "side": "left"}
    chiefs = {c.fid: c for c in battle.commanders}
    for key, side in (("left", "guan"), ("right", "huang")):
        assert [c["fid"] for c in p["chiefs"][key]] == [c.fid for c in sorted(battle.commanders, key=lambda c: c.rank) if c.faction == side]
    for c in p["chiefs"]["left"] + p["chiefs"]["right"]:
        assert c["hp"] == round(chiefs[c["fid"]].neili) and c["cap"] == round(chiefs[c["fid"]].neili_cap) and not c["fallen"]


def test_an_active_round_says_what_i_sent_and_opens_with_a_beat(showdown):
    _, a, _ = showdown
    _open(a)
    p = _panel(a)
    assert p["phase"] == "active" and p["round"] == 1 and p["me"]["sent"] is None and p["sent"] == 0
    assert [x["kind"] for x in p["beats"]] == ["open"] and "say" not in p["beats"][0]  # 沒有上陣人物：開打那一下沒人喊話
    _chiefs(a)
    beat = _panel(a)["beats"][0]
    assert beat["name"] == "皇甫嵩" and beat["say"] and beat["foe"] == {"fid": "bocai", "name": "波才"}
    a.choose("battle:act:guan_raid")
    p = _panel(a)
    assert p["me"]["sent"] == "奇襲" and p["sent"] == 1 and p["present"] >= 2


def test_the_feed_has_one_line_per_round_newest_first(showdown):
    _, a, b = showdown
    _open(a)
    for _ in range(2):
        battle = a.world.get_battle()
        n = battle.round_number
        a.choose("battle:act:guan_strong")
        b.choose("battle:act:huang_hold")  # 兩個人都出完了：當場結算
        assert a.world.get_battle().round_number == n + 1
    feed = _panel(a)["feed"]
    assert [r["n"] for r in feed] == [2, 1] and all(r["lead"] in ("left", "right", "tie") for r in feed)
    assert all("：" not in r["text"] for r in feed) and feed[0]["mine"]


def test_a_hurt_chief_and_a_felled_one_each_get_a_beat(showdown):
    _, a, _ = showdown
    _open(a)
    _chiefs(a)
    hurt, felled = "bocai", "liupi"

    def put(x):
        for c in x.commanders:
            if c.fid == hurt:
                c.neili = c.neili_cap * 0.4
            if c.fid == felled:
                c.neili, c.fallen_round, c.felled_by = 0, x.round_number, "甲"
    a.world.mutate_battle(put)
    beats = {b["id"]: b for b in _panel(a)["beats"]}
    assert f"hurt:{hurt}:50" in beats and beats[f"hurt:{hurt}:50"]["pct"] == 40
    fall = beats[f"fall:{felled}"]
    assert fall["mine"] and fall["by"] == "甲" and fall["side"] == "right" and fall["say"]
    chief = next(c for c in _panel(a)["chiefs"]["right"] if c["fid"] == felled)
    assert chief["fallen"] and chief["by"] == "甲"


# ── 網頁 ──────────────────────────────────────────────


@node
def test_the_panel_sits_on_top_with_the_moves_right_under_it(showdown):
    _, a, _ = showdown
    _open(a)
    m = server.main_view(a)
    page = run(m, "return H.pageJianghu();")
    assert page.index('<section class="bp"') < page.index('class="bp-moves"') < page.index('<section class="card scene">')
    moves = [o for o in m["options"] if o["id"].startswith("battle:act:")]
    assert moves and all(page.count(f'data-id="{o["id"]}"') == 1 for o in moves)  # 出招鈕只畫一次（面板裡）
    assert 'class="bp-clock' in page and "官軍（我方）" in page


@node
def test_the_status_bar_shows_battle_hp_while_fighting(showdown):
    _, a, _ = showdown
    m = server.main_view(a)
    me = m["battle_panel"]["me"]
    top = run(m, "return H.topHtml();")
    assert f"陣中氣血 </em>{me['hp']}/{me['cap']}" in top and "bp-hpbar" in top


@node
def test_other_tabs_get_a_mini_bar_back_to_the_battle(showdown):
    _, a, _ = showdown
    _open(a)
    m = server.main_view(a)
    assert "bp-mini" not in run(m, 'H.S.tab = "jianghu"; return H.tabsHtml();')
    mini = run(m, 'H.S.tab = "map"; return H.tabsHtml();')
    assert 'class="bp-mini" data-act="tab" data-tab="jianghu"' in mini and "去出招" in mini


@node
def test_no_panel_bits_without_a_battle(on):
    g = Game.new(on, "丙", rng=random.Random(0))
    g.client = None
    m = server.main_view(g)
    page = run(m, 'H.S.tab = "map"; return H.pageJianghu() + H.topHtml() + H.tabsHtml();')
    assert "bp-" not in page


@pytest.mark.parametrize("fid", ["huangfusong", "bocai"])
def test_chiefs_have_a_face(fid):
    """面板與覆蓋用的立繪（web/img/figures/full/<人物>.webp）；沒有圖的人物網頁照第一個字畫（bpFace 的 em）。"""
    assert (server.WEB / "img" / "figures" / "full" / f"{fid}.webp").exists()


@node
def test_the_week_strip_drops_its_two_army_numbers_during_a_battle(showdown):
    """PM 2026-11-06 看截圖：戰局條「官軍 50／50 黃巾軍」跟本週條「官 53・黃 47」玩家分不清——決戰期間本週條不寫那兩個數字。"""
    _, a, _ = showdown
    m = server.main_view(a)
    week = {"key": "w1", "label": "本週", "when": "第 1 週", "theme": "黃巾起事", "sides": {"guan": 53, "huang": 47}, "steps": [], "notes": []}
    on = run({**m, "week_card": week}, 'return H.weekCardHtml(m, "strip");')
    off = run({**m, "week_card": week, "battle_panel": None}, 'return H.weekCardHtml(m, "strip");')
    assert 'class="wk-sides"' in off and 'class="wk-sides"' not in on and 'class="wk-strip' in on


def test_every_free_text_move_is_called_the_same(on):
    """同一個輸入框只用一個名字（PM 2026-11-06：「開打」那張寫放手一搏、「回合中」那張寫孤注一擲）。"""
    from tianxia.content import load_content

    for content in (on, load_content(server.ROOT / "content")):
        texts = {o.text for b in content.battles.values() for act in b.acts for o in act.options if o.free_text}
        assert texts and all(t.startswith("放手一搏") for t in texts), texts


@node
def test_after_sending_the_panel_says_it_once(showdown):
    """PM 2026-11-06 看截圖：出完招面板寫「你這一回合：奇襲」，選單上那顆灰的「（已選擇，等其他人…）」不再畫第二次。"""
    _, a, _ = showdown
    _open(a)
    a.choose("battle:act:guan_raid")
    m = server.main_view(a)
    assert any(o["id"] == "battle:waiting" for o in m["options"])
    page = run(m, "return H.pageJianghu();")
    assert "你這一回合：奇襲" in page and "battle:waiting" not in page and "已選擇，等其他人" not in page
