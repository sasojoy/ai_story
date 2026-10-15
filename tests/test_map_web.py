"""輿圖升級的網頁（設計第一～八節）：整頁地圖、地圖上的記號、看大局、濾鏡小牌子、抽屜、天下怎麼變。
在 node 裡跑整支 app.js（tests/webharness.py），餵伺服器真的會給的底圖與疊層；沒有 node 就略過。"""
from __future__ import annotations

import random
import re
from pathlib import Path

import pytest
import test_prologue_web

import server
import webharness
from conftest import classic_rules, real_content
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES = ["S", "pageMap", "marksSvg", "regionTint", "controlAt", "hudHtml", "chipsHtml", "drawerHtml",
         "overviewHtml", "placeHtml", "searchHtml", "timelineHtml", "graphSvg", "chartHtml", "mapDrawerPx"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
NOW = "{ k: 1, far: false, layers: new Set(%s), sel: null, week: H.S.mapState.now_week }"


def _game(faction="guan", at="yingchuan", classic=False):
    c = real_content("weekend")
    c.config.auto_open_first_season = True
    if classic:
        classic_rules(c)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location = faction, at
    return game


def run(game, script, **S):
    payload = {"m": server.main_view(game), "script": script,
               "S": {"mapBase": game.map_base(), "mapState": game.map_state(), **S},
               "menxia": None, "stored": {}, "responses": {}}
    return webharness.run(DRIVER, payload)


def marks(game, layers='["control"]', **o):
    extra = "".join(f", {k}: {v}" for k, v in o.items())
    return run(game, f"return H.marksSvg(H.S.mapBase, H.S.mapState, Object.assign({NOW % layers}, {{{extra[2:]}}}));")


def test_marks_draw_every_open_place_with_its_glyph():
    game = _game()
    out = marks(game)
    assert out.count("data-loc=") == len(game.map_base()["places"])
    assert "潁川郊野" in out and ">城<" in out and "（你）" in out


def test_marks_paint_halos_and_fronts_when_territory_is_on():
    out = marks(_game())
    assert "url(#mk-halo-guan)" in out and 'class="front"' in out


def test_marks_without_territory_have_no_halos_or_fronts():
    out = marks(_game(classic=True))
    assert "url(#mk-halo-" not in out.split("</defs>", 1)[1] and 'class="front"' not in out


def test_the_far_view_shows_regions_and_tallies_without_place_names():
    out = marks(_game(), k=2.5, far="true")
    assert "潁川汝南" in out and re.search(r"官 \d", out) and "潁川郊野" not in out


def test_badges_stack_under_the_name():
    out = marks(_game(), layers='["control", "enemy", "route"]')
    assert "分</text>" in out and any(f">{w}</text>" in out for w in ("穩勝", "有把握", "五五波", "難分勝負", "凶險", "必敗"))


def test_the_map_page_is_a_full_page_layer_with_chips():
    out = run(_game(), "return H.pageMap();")
    assert 'class="mapx' in out and 'id="map"' in out and '<g id="mk">' in out and 'id="mdrawer"' in out
    assert all(word in out for word in ("勢力", "軍令", "敵情", "路程", "劇情", "版圖變化", "找地點"))
    assert "<select" not in out and "travel-row" not in out and "map-legend" not in out


def test_region_tint_follows_the_majority():
    out = run(_game(), "return H.regionTint(H.S.mapBase, H.S.mapState, H.S.mapState.now_week, true);")
    assert out["yingru"] in ("#DCE5F0", "#F4E7C2", "#DFEBDD")
    assert run(_game(), "return H.regionTint(H.S.mapBase, H.S.mapState, H.S.mapState.now_week, false);") == {}


def test_the_overview_answers_where_to_sortie_today():
    out = run(_game(), "return H.overviewHtml(H.S.mapBase, H.S.mapState);")
    assert "今天去哪裡出陣" in out and out.count('data-act="map-pick"') >= 1 and "潁川汝南" in out


def test_the_overview_without_sortie_skips_the_suggestions():
    out = run(_game(faction=None), "return H.overviewHtml(H.S.mapBase, H.S.mapState);")
    assert "今天去哪裡出陣" not in out and "潁川" in out


def test_a_place_shows_three_cells_then_the_actions():
    out = run(_game(), 'return H.placeHtml(H.S.mapBase, H.S.mapState, "runan_wilds");')
    assert out.index("誰佔著") < out.index("打得過嗎") < out.index("多遠") < out.index('data-act="map-travel"')
    assert 'data-mode="walk"' in out and 'data-mode="dash"' in out and "汝南荒野" in out


def test_your_own_place_offers_sortie_and_explore_back_on_jianghu():
    out = run(_game(faction="huang", at="huangjin_camp"), 'return H.placeHtml(H.S.mapBase, H.S.mapState, "huangjin_camp");')
    assert 'data-act="map-jianghu"' in out and "探索" in out and 'data-act="map-travel"' not in out


def test_search_finds_a_place_by_person():
    out = run(_game(), 'return H.searchHtml(H.S.mapBase, H.S.mapState, "波才");')
    assert 'data-act="map-pick" data-id="huangjin_camp"' in out and "長社" not in out


def test_search_with_nothing_typed_lists_every_place_by_region():
    game = _game()
    out = run(game, 'return H.searchHtml(H.S.mapBase, H.S.mapState, "");')
    assert out.count('data-act="map-pick"') == len(game.map_base()["places"]) and "你在這裡" in out


def test_the_journey_line_offers_halt():
    game = _game()
    game.travel("changshe", "walk")
    m = server.main_view(game)
    out = run(game, "return H.overviewHtml(H.S.mapBase, H.S.mapState);")
    assert "m-journey" in out and "長社" in out and "分鐘" in out and "你在" not in out  # 路上不寫「你在」哪一站
    assert ('data-id="act:halt"' in out) == any(o["id"] == "act:halt" for o in m["options"])


def test_travel_stays_on_the_map():
    js = (Path(server.WEB) / "app.js").read_text(encoding="utf-8")
    body = js[js.index("async function travel(mode)"):]
    body = body[: body.index("\n  }\n") + 4]
    assert 'S.tab = "jianghu"' not in body and "loadMap()" in body and "S.mapSel" in body


def _timeline_game():
    """第 1 週記一筆，第 2 週把潁川汝南推到黃巾那頭（官軍大營易手）再記一筆，現在是第 3 週。"""
    from tianxia import calendar, territory

    game = _game()
    w, c = game.state.world, game.content
    territory.update(w, c)
    w.time = calendar.week_start(2, c, w) + 60
    w.trends["yingru"] = 90
    territory.update(w, c)
    w.time = calendar.week_start(3, c, w) + 60
    territory.update(w, c)
    return game


def test_the_timeline_has_the_curve_the_tallies_and_the_chart():
    game = _timeline_game()
    out = run(game, "return H.timelineHtml(H.S.mapBase, H.S.mapState, H.S.mapState.now_week);")
    assert "天下怎麼變" in out and out.count("<polyline") >= 4  # 三條戰線＋割據
    assert all(name in out for name in ("官軍", "黃巾", "豪強"))
    st = game.map_state()
    assert len(re.findall(r'class="cell[ "]', out)) == sum(len(g["spots"]) for g in st["chart"]) * st["weeks_total"]
    assert "官軍大營" in out  # 第 3 週易手的那一處照地點的名字寫
    assert 'data-act="map-play"' in out and 'data-act="map-now"' in out


def test_picking_an_earlier_week_flashes_what_changed():
    game = _timeline_game()
    changed = next(x for x in game.map_state()["weeks"] if x["week"] == 2)["changed"]
    assert {"id": "guan_camp", "from": "guan", "to": "huang"} in changed
    out = marks(game, week=2)
    assert out.count('class="pulse"') == len(changed) + 1  # 易手的那幾處，加上你的那一圈
    assert marks(game).count('class="pulse"') == 1  # 平常看現在：只有你的那一圈
    assert marks(game, tl="true").count('class="pulse"') == 1  # 版圖變化停在現在這一週：這一週沒有易手


def test_the_chart_draws_unknown_weeks_as_blank():
    from tianxia import calendar, territory

    game = _game()
    w, c = game.state.world, game.content
    w.time = calendar.week_start(3, c, w) + 60
    territory.update(w, c)  # 第一次算在第 3 週：前兩週沒記
    out = run(game, "return H.chartHtml(H.S.mapBase, H.S.mapState, H.S.mapState.now_week);")
    assert 'class="cell blank' in out and 'class="cell future' in out


def test_the_timeline_without_territory_says_so():
    out = run(_game(classic=True), "return H.timelineHtml(H.S.mapBase, H.S.mapState, 1);")
    assert "這一季沒有地盤易手" in out and "<polyline" not in out


def test_the_tally_compares_with_the_first_recorded_week():
    """「天下」那一條比的是第一筆記到的那一週（第 1 週週末；中途上線是上線那一週），照實寫是第幾週，不寫「開季」。"""
    game = _timeline_game()
    out = run(game, "return [H.hudHtml(H.S.mapBase, H.S.mapState, 3), H.hudHtml(H.S.mapBase, H.S.mapState, 1)];")
    assert "比第 1 週" in out[0] and "開季" not in out[0]
    assert "比第" not in out[1]  # 看的就是第 1 週：沒得比
    tl = run(game, "return H.timelineHtml(H.S.mapBase, H.S.mapState, 3);")
    assert "比第 1 週" in tl and "開季" not in tl


def test_the_timeline_button_sits_under_the_zoom_buttons():
    """對比 2 選丙（企劃者 10/15）：「⏱ 版圖」是右上角第四顆圓鈕，濾鏡那一排只剩五顆濾鏡。"""
    out = run(_game(), "return [H.pageMap(), H.chipsHtml()];")
    ctl = out[0][out[0].index('class="map-ctl"'):]
    ctl = ctl[: ctl.index("</div>")]
    assert 'data-act="map-timeline"' in ctl and "版圖" in ctl
    assert "map-timeline" not in out[1] and out[1].count('data-act="map-layer"') == 5


def test_the_timeline_drawer_is_320_high_on_a_phone():
    """對比 3 選乙（企劃者 10/15）：版圖變化時抽屜 320 高，地圖大一截，年表往下捲。"""
    assert run(_game(), 'return H.mapDrawerPx("tl");') == 320


def test_a_losing_suggestion_is_faded():
    """對比 4 選乙（企劃者 10/15）：必敗的照樣列、排在最後、整列淡一點。"""
    game = _game()
    st = game.map_state()
    out = run(game, "return H.overviewHtml(H.S.mapBase, H.S.mapState);")
    assert [g["lose"] for g in st["suggest"]] == [False, False, False, True]  # 官軍在潁川：三處打得過，再一處必敗的
    assert out.count('class="m-go lose"') == 1 and out.count('class="m-go"') == 3
    assert out.index('class="m-go lose"') > out.rindex('class="m-go"')
