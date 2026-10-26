"""輿圖的網頁（輿圖升級設計第一～八節的版面）：整頁一層、抽屜（一處的卡、找地點、收著那一行）、天下怎麼變（曲線、年表、處數）。
輿圖第三版起地圖本身是天下圖與區圖兩張固定取景的圖（tests/test_world_map_web.py、tests/test_region_map_web.py；企劃者 2026-10-22 起兩張都
能拖、能捏合縮放，tests/test_map_pan_web.py）；第 4 批拿掉了可以拖縮的
那一張、濾鏡、名字底下的小牌子、⚔、看大局、「天下」那一條（輿圖簡化設計 5.4），這一檔照新的畫面改寫：測那些東西本身的條目拿掉了
（資訊搬去哪裡見 tests/test_region_map_web.py 的 test_the_card_carries_everything_the_chips_used_to），抽屜與版圖變化的照舊。
在 node 裡跑整支 app.js（tests/webharness.py），餵伺服器真的會給的底圖與疊層；沒有 node 就略過。"""
from __future__ import annotations

import random
import re
from pathlib import Path

import pytest
import test_prologue_web

import server
import webharness
from conftest import classic_rules, real_content, third_party_gentry
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES = ["S", "pageMap", "controlAt", "drawerHtml", "placeCard", "cardExtras", "searchHtml", "timelineHtml", "graphSvg", "chartHtml",
         "mapDrawerPx", "setMapDrawer", "insightRow", "redrawDrawer", "regionLineHtml", "worldParts", "worldLabels", "journeyHtml", "regionPick"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
APP = webharness.APP  # 三個檔（main.js、map.js、app.js）接起來的那一份


def _game(faction="guan", at="yingchuan", classic=False, third_party=False):
    c = real_content("week7")
    c.config.auto_open_first_season = True
    if classic:
        classic_rules(c)
    if third_party:
        third_party_gentry(c)  # 豪強是第三方、有割據的規則（豪強分屬兩軍之前）
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location = faction, at
    return game


def run(game, script, stored=None, st=None, **S):
    # 停在區圖那一層（潁川汝南）：輿圖第三版第 3 批起打開輿圖第一眼是天下圖（S.mapLayer "world"）
    payload = {"m": server.main_view(game), "script": script,
               "S": {"mapBase": game.map_base(), "mapState": st or game.map_state(), "mapLayer": "region", "mapRegion": "yingru", **S},
               "menxia": None, "stored": stored or {}, "responses": {}}
    return webharness.run(DRIVER, payload)


def world_parts(game, week="H.S.mapState.now_week", tl="false"):
    return run(game, f"return H.worldParts(H.S.mapBase, H.S.mapState, {{ k: 2.5, week: {week}, tl: {tl}, sel: null }});", mapLayer="world")


def test_the_map_page_is_a_full_page_layer_without_chips():
    """整頁一層：地圖框、#mk、抽屜；上面一排（天下圖：天下・找地點・版圖；區圖：‹ 天下・大區・塗層・版圖）。濾鏡那一排、右上角那一欄、
    「天下」那一條、圖例都拿掉了（輿圖簡化設計 5.4）。"""
    out = run(_game(), "return H.pageMap();")
    assert 'class="mapx' in out and 'id="map"' in out and '<g id="mk">' in out and 'id="mdrawer"' in out
    assert "找地點" in out and "版圖" in out and 'class="r-top"' in out and 'class="w-top"' in out
    for gone in ("map-chips", "map-ctl", "map-hud", 'data-act="map-layer"', 'data-act="map-zoom"', "map-legend", "travel-row", "勢力</button>", "敵情"):
        assert gone not in out, gone


def test_the_card_extras_answer_where_to_sortie_today():
    """輿圖升級設計第五節那三樣（今天去哪裡出陣、戰線、本週大事）挪到卡底下（設計 5.3、第九章第 6 條）。"""
    out = run(_game(), "return H.cardExtras(H.S.mapBase, H.S.mapState);")
    assert "今天去哪裡出陣" in out and out.count('data-act="map-pick"') >= 1 and "潁川汝南" in out


def test_the_extras_without_sortie_skip_the_suggestions():
    out = run(_game(faction=None), "return H.cardExtras(H.S.mapBase, H.S.mapState);")
    assert "今天去哪裡出陣" not in out


def test_a_card_reads_top_down_then_the_actions():
    """卡由上往下（設計 5.3）：印與名字、一句話、動作、此地的對手（減法季第七章：動作在前）；不在這裡是步行與疾行。"""
    out = run(_game(), 'return H.placeCard(H.S.mapBase, H.S.mapState, "runan_wilds");')
    # 減法季整合設計第七章第 2 條：卡只佔三分之一，名字、誰的、步行與疾行在前，往上拉才有對手
    assert out.index("汝南荒野") < out.index('class="m-line"') < out.index('data-act="map-travel"') < out.index("此地的對手")
    assert 'data-mode="walk"' in out and 'data-mode="dash"' in out and "步行" in out[: out.index('class="m-line"')]  # 距離寫在名字那一行


def test_your_own_place_offers_sortie_and_explore_back_on_jianghu():
    out = run(_game(faction="huang", at="huangjin_camp"), 'return H.placeCard(H.S.mapBase, H.S.mapState, "huangjin_camp");')
    assert 'data-act="map-jianghu"' in out and "探索" in out and 'data-act="map-travel"' not in out and "黃巾別部營寨（你）" in out


def test_search_finds_a_place_by_person():
    out = run(_game(), 'return H.searchHtml(H.S.mapBase, H.S.mapState, "波才");')
    assert 'data-act="map-pick" data-id="huangjin_camp"' in out and "長社" not in out


def test_search_with_nothing_typed_lists_every_place_by_region():
    game = _game()
    out = run(game, 'return H.searchHtml(H.S.mapBase, H.S.mapState, "");')
    assert out.count('data-act="map-pick"') == len(game.map_base()["places"]) and "你在這裡" in out


def test_the_journey_line_offers_halt():
    """在路上：區圖收著那一行就是「往 X・還有 N 分鐘・喊停」（設計 5.3：在路上抽屜第一行照舊）。"""
    game = _game()
    game.travel("changshe", "walk")
    m = server.main_view(game)
    out = run(game, "return H.regionLineHtml(H.S.mapBase, H.S.mapState);")
    assert "m-journey" in out and "長社" in out and "分鐘" in out and "你在" not in out  # 路上不寫「你在」哪一站
    assert ('data-id="act:halt"' in out) == any(o["id"] == "act:halt" for o in m["options"])


def test_the_region_line_says_where_you_are_only_in_your_region():
    game = _game()
    mine = run(game, "return H.regionLineHtml(H.S.mapBase, H.S.mapState);")
    other = run(game, "return H.regionLineHtml(H.S.mapBase, H.S.mapState);", mapRegion="nanyang")
    assert "你在 <b>潁川郡（陽翟）</b>" in mine and 'data-act="map-open"' in mine
    assert "你在" not in other and "點一處地點" in other


def test_travel_stays_on_the_map():
    js = APP.read_text(encoding="utf-8")
    body = js[js.index("async function travel(mode)"):]
    body = body[: body.index("\n  }\n") + 4]
    assert 'S.tab = "jianghu"' not in body and "loadMap()" in body and "S.mapSel" in body


def _timeline_game():
    """第 1 週記一筆，第 2 週把潁川汝南推到黃巾那頭（官軍大營易手）再記一筆，現在是第 3 週。豪強是第三方的規則（有割據曲線）。"""
    from tianxia import calendar, territory

    game = _game(third_party=True)
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
    """版圖變化在天下圖上播（輿圖第三版第 3 批）：看以前的某一週，那一週易手的地點閃一圈（加上你的那一圈）。"""
    game = _timeline_game()
    changed = next(x for x in game.map_state()["weeks"] if x["week"] == 2)["changed"]
    assert {"id": "guan_camp", "from": "guan", "to": "huang"} in changed
    _, high = world_parts(game, week=2)
    assert high.count('class="pulse"') == len(changed) + 1
    assert world_parts(game)[1].count('class="pulse"') == 1  # 平常看現在：只有你的那一圈
    assert world_parts(game, tl="true")[1].count('class="pulse"') == 1  # 版圖變化停在現在這一週：這一週沒有易手


def test_the_chart_draws_unknown_weeks_as_blank():
    from tianxia import calendar, territory

    game = _game()
    w, c = game.state.world, game.content
    w.time = calendar.week_start(2, c, w) + 60
    territory.update(w, c)  # 第一次算在第 2 段：第 1 段沒記（7 天季的年表三段）
    out = run(game, "return H.chartHtml(H.S.mapBase, H.S.mapState, H.S.mapState.now_week);")
    assert 'class="cell blank' in out and 'class="cell future' in out


def test_fb632_a_neutral_block_taken_shows_in_the_timeline_and_the_chart():
    """FB-632：開季中立的地第一次被佔下，版圖變化那一週的清單寫「中立 → 官軍」、年表那一格打白點（以前寫「沒有地點易手」、沒有白點）。"""
    from conquest_kit import conquest_game

    from tianxia import calendar, conquest, territory

    game = conquest_game("week7")
    w, c = game.state.world, game.content
    spots = [x for g in game.map_state()["chart"] for x in g["spots"]]
    spot = next(x for x in spots if conquest.start_kind(w, c, x) == conquest.NEUTRAL)  # 年表上的一塊中立地
    conquest.assign(w, c, {spot: "guan"})
    w.time = calendar.week_start(2, c, w) + 60
    territory.update(w, c)
    tl, chart = run(game, "return [H.timelineHtml(H.S.mapBase, H.S.mapState, 1), H.chartHtml(H.S.mapBase, H.S.mapState, 1)];")
    week1 = tl[tl.index("第 1 段（"):]  # 7 天季的年表寫「第 1 段（第 1～2 天）」
    assert f"{c.locations[spot].name}：" in week1 and ">中立</span> → " in week1 and "沒有地點易手" not in week1
    row = chart[chart.index(f'data-id="{spot}"'):]
    assert row[row.index("<span class=\"cell"):].startswith('<span class="cell now flip"')  # 那一格（第 1 週）打白點
    _, high = world_parts(game, week=1, tl="true")
    assert high.count('class="pulse"') == 2  # 那一塊閃一圈，加上你的那一圈


def test_the_timeline_without_territory_says_so():
    out = run(_game(classic=True), "return H.timelineHtml(H.S.mapBase, H.S.mapState, 1);")
    assert "這一季沒有地盤易手" in out and "<polyline" not in out


def test_the_tally_compares_with_the_season_start():
    """版圖變化的處數跟開季那一刻比（FB-264：第一次算地盤就在第 1 週時有開季的基準），看第 1 週也比得出來。"""
    game = _timeline_game()
    out = run(game, "return [H.timelineHtml(H.S.mapBase, H.S.mapState, 3), H.timelineHtml(H.S.mapBase, H.S.mapState, 1)];")
    assert "比開季" in out[0] and "比開季" in out[1] and "比第" not in out[0]


def test_the_tally_without_a_season_start_compares_with_the_first_recorded_week():
    """中途上線（第一次算在第 2 段）：沒有開季的基準，比第一筆記到的那一段、照實寫第幾段；看的就是那一段時不比。"""
    from tianxia import calendar, territory

    game = _game()
    w, c = game.state.world, game.content
    w.time = calendar.week_start(2, c, w) + 60
    territory.update(w, c)
    w.time = calendar.week_start(3, c, w) + 60
    territory.update(w, c)
    out = run(game, "return [H.timelineHtml(H.S.mapBase, H.S.mapState, 3), H.timelineHtml(H.S.mapBase, H.S.mapState, 2)];")
    assert "比第 2 段" in out[0] and "開季" not in out[0]
    assert "比第" not in out[1] and "開季" not in out[1]


def test_fb264_week_one_flips_show_in_the_chart_and_flash_on_the_map():
    """FB-264：第 1 週的易手（跟開季比）在年表上有白點、選第 1 週時天下圖閃一圈、那一週的清單列得出來。"""
    from tianxia import territory

    game = _game()
    w, c = game.state.world, game.content
    territory.update(w, c)
    territory.assign(w, c, {"runan_wilds": "guan"})
    chart = run(game, "return H.chartHtml(H.S.mapBase, H.S.mapState, 1);")
    assert 'class="cell now flip"' in chart
    _, high = world_parts(game, week=1, tl="true")
    assert high.count('class="pulse"') == 2  # 汝南荒野，加上你的那一圈
    tl = run(game, "return H.timelineHtml(H.S.mapBase, H.S.mapState, 1);")
    assert "汝南荒野" in tl[tl.index("第 1 段（"):]


def test_the_timeline_drawer_is_320_high_on_a_phone():
    """對比 3 選乙（企劃者 10/15）：版圖變化時抽屜 320 高，地圖大一截，年表往下捲。"""
    assert run(_game(), 'return H.mapDrawerPx("tl");') == 320


def test_a_losing_suggestion_is_faded():
    """對比 4 選乙（企劃者 10/15）：必敗的照樣列、排在最後、整列淡一點（挪到卡底下照舊）。"""
    game = _game()
    st = game.map_state()
    out = run(game, "return H.cardExtras(H.S.mapBase, H.S.mapState);")
    assert [g["lose"] for g in st["suggest"]] == [False, False, False, True]  # 官軍在潁川：三處打得過，再一處必敗的
    assert out.count('class="m-go lose"') == 1 and out.count('class="m-go"') == 3
    assert out.index('class="m-go lose"') > out.rindex('class="m-go"')


def test_fb262_standing_there_still_shows_the_odds():
    """FB-262：站在那個地點時此地的對手照那裡的對手寫勝算，出陣・攻那一顆也寫勝算；沒有對手才寫沒有對手。"""
    game = _game(faction="guan", at="runan_wilds")
    p = game.map_state()["places"]["runan_wilds"]
    assert p["sortie"] == "attack" and p["odds"]
    out = run(game, 'return H.placeCard(H.S.mapBase, H.S.mapState, "runan_wilds");')
    foes = out[out.index("此地的對手"):out.index('class="m-foes"') + 400]
    assert p["odds"]["word"] in foes
    sortie = out[out.index('data-key="sortie"'):]
    assert p["odds"]["word"] in sortie[: sortie.index("</button>")]
    calm = run(_game(faction="guan", at="yingchuan"), 'return H.placeCard(H.S.mapBase, H.S.mapState, "yingchuan");')
    assert "沒有對手" in calm[calm.index("此地的對手"):calm.index("此地的對手") + 200]


def test_the_card_says_what_you_can_sense_with_the_strongest_filled():
    out = run(_game(), 'return H.placeCard(H.S.mapBase, H.S.mapState, "changshe");')
    assert "此地能悟" in out and 'class="ig strong"' in out and "最濃" in out
    # 減法季整合設計第七章第 2 條：卡只佔三分之一，動作在前、往上拉才有能悟、對手
    assert out.index('class="m-line"') < out.index('class="m-acts"') < out.index("此地能悟") < out.index("此地的對手")


def test_the_card_line_stays_with_the_switch_off_but_nothing_is_strongest():
    game = _game()
    game.content.config.insight_strong.enabled = False
    out = run(game, 'return H.placeCard(H.S.mapBase, H.S.mapState, "changshe");')
    assert "此地能悟" in out and "最濃" not in out and 'class="ig strong"' not in out


# ── 抽屜 ──
DRAWER_DOM = """
const cls = new Set(); const drawer = { style: {}, offsetHeight: 0, classList: { contains: (c) => cls.has(c), toggle: (c, on) => (on ? cls.add(c) : cls.delete(c)) } };
const body = { innerHTML: '' }, box = { clientHeight: 650, style: { setProperty() {} } };
const els = { mapx: box, mdrawer: drawer, mbody: body };
const orig = T.ctx.document.getElementById;
T.ctx.document.getElementById = (id) => els[id] || orig(id);
"""


def test_the_folded_line_and_the_half_open_card():
    """收著是一行（54）；點了一處抽屜半開那一處的卡（regionPick），點空白收回那一行；地圖不動（regionPick 不碰取景）。"""
    out = run(_game(), DRAWER_DOM + """
H.setMapDrawer('min');
const folded = [drawer.style.height, cls.has('min'), body.innerHTML.includes('m-wline')];
H.regionPick('changshe');
const card = [H.S.mapDrawer, H.S.mapSel, H.S.mapMode, body.innerHTML.includes('長社'), cls.has('min')];
H.regionPick(null);
return { folded, card, back: [H.S.mapDrawer, H.S.mapSel, H.S.mapMode] };
""")
    assert out["folded"] == ["54px", True, True]
    assert out["card"] == ["peek", "changshe", "place", True, False]
    assert out["back"] == ["min", None, "overview"]
    pick = APP.read_text(encoding="utf-8").replace("\r\n", "\n")
    body = pick[pick.index("  function regionPick("):]
    assert "applyMapView" not in body[: body.index("\n  }\n")]  # 點一處地圖不動（設計 5.2）


def test_the_peek_card_leaves_the_region_uncovered():
    """卡半開多高照區圖取景框底下還空著多少（地圖不動，卡不蓋到地點；設計 5.2）：最矮 200、最高六成；沒有區圖的取景照 240。"""
    out = run(_game(), DRAWER_DOM + """
const none = H.mapDrawerPx('peek');
H.S.regionView = { s: 0.6, cx: 0, cy: 0, frame: [0, 0, 1, 1], bottom: 330 };
const room = H.mapDrawerPx('peek');
H.S.regionView.bottom = 560;
const short = H.mapDrawerPx('peek');
H.S.regionView.bottom = 60;
const tall = H.mapDrawerPx('peek');
return [none, room, short, tall];
""")
    assert out == [240, 650 - 330 - 4, 200, round(650 * 0.6)]


def test_the_drawer_height_variable_is_only_written_while_watching_the_timeline():
    js = APP.read_text(encoding="utf-8")
    body = js[js.index("function setMapDrawer("):]
    body = body[: body.index("\n  }\n")]
    assert 'if (S.mapMode === "timeline") box.style.setProperty("--md-h"' in body


# ── 輿圖卡頓（Joy 2026-10-17）：固定取景之後照舊守住的兩條 ──
def test_the_view_moves_the_wrapper_not_the_svg_root():
    """svg 根元素的 transform 一變，Chrome 每一幀重排每一個地名、重畫整張底圖；取景套在外框上（換層、換區滑一下也只動合成層）。"""
    src = APP.read_text(encoding="utf-8")
    body = src[src.index("function applyMapView("):src.index("// 輿圖頁每次畫好")]
    assert "g.world.style.transform = " in body and "svg.style.transform" not in body


def test_status_bar_redraws_do_not_rewrite_inherited_variables_when_nothing_changed():
    src = APP.read_text(encoding="utf-8")
    frame = src[src.index("function mapFrame()"):]
    frame = frame[:frame.index("\n  }\n")]
    assert "setVar(box, \"--map-top\"" in frame and "style.setProperty" not in frame
    assert 'setVar(document.documentElement, "--top-h"' in src
