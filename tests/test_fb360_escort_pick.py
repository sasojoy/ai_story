"""FB-360（歷史武將同行 QA，2026-10-19，375×812）：名下有同伴的人按場景卡上的「加入」之後，挑同伴的四顆（battle:escort:*）
收在「此地還能做」的摺疊裡，第一屏看起來什麼都沒變——還沒加入，卻以為報名了（FB-105 那個坑換了一個地方）。

現在 web/app.js 的 musterJoins 也認 battle:escort:，挑同伴那一步畫在場景卡戰場名字那一行底下（跟加入同一個位置），一顆一行
（鈕上寫份量與氣血，四顆擠一排放不下），旁邊那一小句說挑了才算加入（MUSTER_NOTE.escort，待 joy 潤）；摺疊裡不再列。
晚到（battle:join_late）挑同伴也一樣。網頁照 tests/test_fb105_muster_join.py 的做法用真實內容、真的 /api/main。"""
from __future__ import annotations

import re

from test_fb105_muster_join import ROW_ATTRS, _css_rule, _fold, _muster, _note_html, _page, _scene, _start_fighting, node

import server

PICK = re.compile(r'data-id="(battle:escort:\w+)"')


def _owner(on, game):
    p = game.state.player
    for cid in ("liubei", "guanyu"):
        assert game.world.try_recruit(cid, p.name, cap=3)
    return p


def _row(scene):
    return re.search(rf'<div class="options muster-join pick" {ROW_ATTRS}>(.*?)</div></div>', scene, re.S)


@node
def test_after_join_the_escort_pick_sits_by_the_battles_name(on):
    game = _muster(on, "guan")
    _owner(on, game)
    game.choose("battle:join:guan")
    m = server.main_view(game)
    picks = [o["id"] for o in m["options"] if o["id"].startswith("battle:escort:")]
    assert set(picks) == {"battle:escort:liubei", "battle:escort:guanyu", "battle:escort:none", "battle:escort:back"}
    page = _page(m)
    scene = _scene(page)
    assert _note_html("escort") in scene  # 那一小句說挑了才算加入
    row = _row(scene)
    assert row is not None and PICK.findall(row.group(1)) == picks  # 照選單的順序，一顆都不少
    labels = {o["id"]: o["label"] for o in m["options"]}
    assert all(f"<span>{labels[i]}</span>" in row.group(1) for i in picks)  # 份量與氣血照寫（挑誰要看）
    assert "battle:escort" not in _fold(page) and all(page.count(f'data-id="{i}"') == 1 for i in picks)


def test_the_pick_row_stacks_one_button_per_line():
    """鈕上寫「派某某隨你出陣（份量 N・氣血 N）」，375 寬四顆擠一排放不下：另起一行、一顆一行、佔滿寬度。"""
    row = _css_rule(".scene .muster-join.pick")
    assert row["flex-basis"] == "100%" and row["flex-direction"] == "column"
    assert _css_rule(".scene .muster-join.pick .btn")["width"] == "100%"


@node
def test_a_late_comer_picks_by_the_name_too(on):
    game = _muster(on, "guan")
    _owner(on, game)
    _start_fighting(game)
    game.choose("battle:join_late")
    m = server.main_view(game)
    picks = [o["id"] for o in m["options"] if o["id"].startswith("battle:escort:")]
    assert len(picks) == 4
    page = _page(m)
    row = _row(_scene(page))
    assert row is not None and PICK.findall(row.group(1)) == picks
    assert all(page.count(f'data-id="{i}"') == 1 for i in picks)
