"""輿圖的網頁：一張到底（企劃者 2026-10-30「可以 這樣改」，示意稿第四版）——整個天下一張能自由拖、縮的地圖，字照倍率分三段
（遠看大區與各方幾處、中間小圖與名字、近看能悟與勝算），上面浮著搜尋列與篩選，底下一張抽屜（附近能去一排卡片、一處的卡、版圖變化）。
以前的天下圖、區圖、第一層三張固定取景的圖與它們的測試檔一起拿掉了。在 node 裡跑整支網頁（tests/kit/webharness.py），餵伺服器真的會給的
底圖與疊層；沒有 node 就略過。"""
from __future__ import annotations

import json
import random
import re

import pytest
import test_prologue_web

import server
import webharness
from conftest import real_content
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
import html as htmllib
from tianxia import terrain

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES = ["S", "pageMap", "controlAt", "drawerHtml", "placeCard", "cardExtras", "searchHtml", "searchResults", "timelineHtml", "graphSvg",
         "chartHtml", "mapDrawerPx", "setMapDrawer", "insightRow", "redrawDrawer", "journeyHtml", "nearHtml", "nearList", "chipList", "chipsHtml",
         "mapFilter", "marksHtml", "groundSvg", "camClamp", "camFit", "zMin", "mapPick", "mapBack", "mapFind", "routeD", "camSet", "mapFirst", "mapGoto", "camFirst", "planHtml"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
APP = webharness.APP  # 三個檔（main.js、map.js、app.js）接起來的那一份
# 一個夠大的地圖框：整張天下都在「畫面附近」，字一處都不會因為在畫面外被略過
WIDE = "{ vw: 2400, vh: 3600 }"


def _game(faction="guan", at="yingchuan", profile="week7", content=None):
    c = content or real_content(profile)
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location = faction, at
    return game


def run(game, script, stored=None, st=None, m=None, timeout=60, **S):
    payload = {"m": m or server.main_view(game), "script": script,
               "S": {"mapBase": game.map_base(), "mapState": st or game.map_state(), **S},
               "menxia": None, "stored": stored or {}, "responses": {}}
    return webharness.run(DRIVER, payload, timeout=timeout)


def marks(game, z, st=None, **S):
    """照倍率 z 排好的那一層字與小圖（地圖左上角貼著地圖框左上角）。"""
    return run(game, f"return H.marksHtml(H.S.mapBase, H.S.mapState, {{ z: {z}, x: 0, y: 0 }}, {WIDE});", st=st, **S)


def _lab(out, loc):
    """那一處的名字（<button class="mv-lab…" data-id="loc">…</button>）；沒寫名字回空字串。"""
    m = re.search(rf'<button type="button" class="mv-lab[^"]*"[^>]*data-id="{loc}">.*?</button>', out)
    return m.group(0) if m else ""


# ── 整頁 ──
def test_the_map_page_is_one_world_with_floating_search_chips_buttons_and_a_drawer():
    """整頁一層：地圖框裡一張天下（#mvw：地面 #mk、路線 #mkr，大小是地圖本身的寬高）與照螢幕寫的字那一層（#mkt）；外面浮著搜尋列、
    篩選、回到我與看整張兩顆、抽屜。以前三張圖的上面那一排（‹ 天下、大區、看大局）都沒有了。"""
    game = _game()
    out = run(game, "return H.pageMap();")
    b = game.map_base()
    assert f'<div class="mv-world" id="mvw" style="width:{b["w"]}px;height:{b["h"]}px">' in out
    assert 'id="mk"' in out and 'id="mkr"' in out and 'class="mv-marks" id="mkt"' in out and 'id="mdrawer"' in out
    assert 'data-act="map-search"' in out and 'id="mv-chips"' in out and 'data-act="map-home"' in out and 'data-act="map-fit"' in out
    assert 'data-act="map-timeline"' in out and 'data-act="map-wash"' in out
    assert 'id="mv-find"' not in out  # 找地點那一頁開著才畫
    for gone in ("r-top", "w-top", "world-enter", "region-go", "map-world", "map-full", "map-ctl", "map-legend"):
        assert gone not in out, gone
    found = run(game, "return H.pageMap();", mapMode="search")
    assert 'class="mapx find-mode"' in found and 'id="mv-find"' in found and 'id="map-q"' in found


def test_the_card_extras_answer_where_to_sortie_today():
    """輿圖升級設計第五節那三樣（今天去哪裡出陣、戰線、本週大事）挪到卡底下（設計 5.3、第九章第 6 條）。"""
    out = run(_game(), "return H.cardExtras(H.S.mapBase, H.S.mapState);")
    assert "今天去哪裡出陣" in out and out.count('data-act="map-pick"') >= 1 and "潁川汝南" in out


def test_the_extras_without_sortie_skip_the_suggestions():
    out = run(_game(faction=None), "return H.cardExtras(H.S.mapBase, H.S.mapState);")
    assert "今天去哪裡出陣" not in out


def test_a_card_reads_top_down_then_the_actions():
    """卡由上往下（設計 5.3）：印與名字、一句話、動作、此地的對手（減法季第七章：動作在前）；不在這裡是步行與疾行。
    半開量到 .m-peek-end（動作那一排底下）。"""
    out = run(_game(), 'return H.placeCard(H.S.mapBase, H.S.mapState, "runan_wilds");')
    assert out.index("汝南荒野") < out.index('class="m-line"') < out.index('data-act="map-travel"') < out.index("m-peek-end") < out.index("此地的對手")
    assert 'data-mode="walk"' in out and 'data-mode="dash"' in out and "步行" in out[: out.index('class="m-line"')]  # 距離寫在名字那一行


def test_your_own_place_offers_sortie_and_explore_back_on_jianghu():
    out = run(_game(faction="huang", at="huangjin_camp"), 'return H.placeCard(H.S.mapBase, H.S.mapState, "huangjin_camp");')
    assert 'data-act="map-jianghu"' in out and "探索" in out and 'data-act="map-travel"' not in out and "黃巾別部營寨（你）" in out


# ── 找地點 ──
def test_search_finds_a_place_by_person():
    out = run(_game(), 'return H.searchResults(H.S.mapBase, H.S.mapState, "波才");')
    assert 'data-act="map-pick" data-id="huangjin_camp"' in out and "<h4>人物</h4>" in out and "<h4>地點</h4>" not in out


def test_search_finds_places_by_name_region_and_service():
    game = _game()
    st = game.map_state()
    name = run(game, 'return H.searchResults(H.S.mapBase, H.S.mapState, "長社");', st=st)
    assert 'data-act="map-pick" data-id="changshe"' in name
    region = run(game, 'return H.searchResults(H.S.mapBase, H.S.mapState, "南陽");', st=st)
    nanyang = [p["id"] for p in game.map_base()["places"] if p["region"] == "nanyang" and p["id"] in st["places"]]
    assert nanyang and all(f'data-id="{x}"' in region for x in nanyang[:12])
    service = next(s for q in st["places"].values() for s in q["services"])
    shop = run(game, f'return H.searchResults(H.S.mapBase, H.S.mapState, "{service}");', st=st)
    assert shop.count('class="m-sr"') == min(12, sum(service in q["services"] for q in st["places"].values()))
    none = run(game, 'return H.searchResults(H.S.mapBase, H.S.mapState, "沒有這個地方");', st=st)
    assert "找不到「沒有這個地方」" in none and "m-sr" not in none


def test_search_with_nothing_typed_offers_the_week_people_and_every_region():
    game = _game()
    out = run(game, 'return H.searchResults(H.S.mapBase, H.S.mapState, "");')
    assert "<h4>附近的人物</h4>" in out and "<h4>跳到大區</h4>" in out
    assert out.count('data-act="map-region"') == len(game.map_base()["regions"])


def test_a_search_result_flies_there_and_opens_its_card():
    """點一筆結果（map-pick）：找地點那一頁收起來、抽屜開那一處的卡（半開）、字清掉。"""
    out = run(_game(), "H.mapFind(); H.S.mapQuery = '長'; H.mapPick('changshe', true); return [H.S.mapMode, H.S.mapSel, H.S.mapDrawer, H.S.mapQuery];")
    assert out == ["place", "changshe", "peek", ""]


def test_the_journey_line_offers_halt():
    """在路上：抽屜第一行就是「往 X・還有 N 分鐘・喊停」，底下是「沿路能去」那一排。"""
    game = _game()
    game.travel("changshe", "walk")
    m = server.main_view(game)
    out = run(game, "return H.nearHtml(H.S.mapBase, H.S.mapState);")
    assert out.index("m-journey") < out.index("沿路能去") and "長社" in out and "分鐘" in out and "從" not in out.split("m-cards")[0]
    assert ('data-id="act:halt"' in out) == any(o["id"] == "act:halt" for o in m["options"])


# ── 附近能去 ──
def test_the_near_row_lists_places_by_minutes_and_your_own_card_below():
    """平常抽屜：「從某處出發」一排卡片（不含你腳下這一處，近的在前、本週要去的排第一），半開量到那一排底下，往上拉是你腳下這一處的卡。"""
    game = _game()
    st = game.map_state()
    out = run(game, "return [H.nearHtml(H.S.mapBase, H.S.mapState), H.nearList(H.S.mapBase, H.S.mapState).map((b) => b.id)];", st=st)
    html, ids = out
    assert "從潁川郡（陽翟）出發" in html and "yingchuan" not in ids and len(ids) <= 24
    week = st["week"]["id"] if st.get("week") and st["week"]["id"] in st["places"] and st["week"]["id"] != "yingchuan" else None
    rest = [x for x in ids if x != week]
    assert [st["places"][x]["minutes"] for x in rest] == sorted(st["places"][x]["minutes"] for x in rest)
    if week:
        assert ids[0] == week
    assert html.index('class="m-cards"') < html.index("m-peek-end") < html.index('class="m-mine"')
    assert 'data-act="map-place" data-id="' + ids[0] + '"' in html


def test_a_chip_filters_the_near_row_and_fades_the_rest_on_the_map():
    """篩選（寶）：附近那一排只列有寶的、標題寫「寶・N 處」；地圖上其餘的地點淡掉、不寫名字。再按一次回全部。"""
    game = _game()
    st = game.map_state()
    rich = {x for x, q in st["places"].items() if q.get("rich")}
    assert rich
    out = run(game, """H.mapFilter('rich');
const ids = H.nearList(H.S.mapBase, H.S.mapState).map((b) => b.id), head = H.nearHtml(H.S.mapBase, H.S.mapState);
const mk = H.marksHtml(H.S.mapBase, H.S.mapState, { z: 1, x: 0, y: 0 }, """ + WIDE + """);
const chips = H.chipsHtml(H.S.mapBase, H.S.mapState);
H.mapFilter('rich');
return { ids, head, mk, chips, back: H.S.mapFilter };""", st=st)
    assert out["ids"] and set(out["ids"]) <= rich
    assert f"寶・{len(out['ids'])} 處" in out["head"]
    assert 'data-act="map-filter" data-id="rich" aria-pressed="true"' in out["chips"]
    plain = next(x for x in st["places"] if x not in rich and x != "yingchuan")
    assert re.search(rf'class="mv-pin [a-z]+ dim"[^>]*data-id="{plain}"', out["mk"]) and not _lab(out["mk"], plain)
    assert out["back"] == "all"


def test_the_chips_are_the_kinds_of_place_and_what_you_can_sense():
    game = _game()
    chips = run(game, "return H.chipList(H.S.mapBase, H.S.mapState).map(([k]) => k);")
    assert chips[0] == "all" and "rich" in chips and any(k.startswith("most:") for k in chips) and any(k.startswith("ins:") for k in chips)


# ── 地圖上的字（三段） ──
def test_far_away_shows_regions_with_counts_and_coloured_dots():
    """遠看（倍率 0.72 以下）：大區名＋各方幾處、寶幾處；地點是一顆照誰佔著上色的點，名字只寫你在的、選的、本週的。"""
    game = _game()
    out = marks(game, 0.5)
    regions = game.map_base()["regions"]
    assert out.count('class="mv-reg"') == len(regions) and 'class="mv-cnt"' in out
    assert re.search(r'class="mv-cnt"[^>]*>[^<]*官 \d+', out)
    assert 'class="mv-dot' in out and 'class="mv-pin' not in out and 'class="mv-geo' not in out
    assert "你在這裡" in _lab(out, "yingchuan") and out.count('class="mv-you"') == 1


def test_middle_distance_shows_icons_names_and_seals():
    """中間：每一處的小圖與名字、誰佔著的小印、寶；山河名。不寫幾分與勝算（近看才有）。"""
    game = _game()
    out = marks(game, 1)
    assert 'class="mv-pin' in out and 'class="mv-dot' not in out and 'class="mv-reg"' not in out and 'class="mv-geo' in out
    assert 'class="mv-side"' in out and 'class="mv-rich"' in out
    assert "<small>" not in _lab(out, "changshe")


def test_close_up_adds_minutes_and_insights():
    game = _game()
    out = marks(game, 2)
    assert re.search(r"<small>\d+ 分", _lab(out, "changshe")) and 'class="ins"' in out


def test_the_selected_place_gets_a_ring_a_route_and_a_minutes_bubble():
    game = _game()
    out = run(game, f"""H.S.mapMode = 'place'; H.S.mapSel = 'changshe';
return [H.marksHtml(H.S.mapBase, H.S.mapState, {{ z: 1, x: 0, y: 0 }}, {WIDE}), H.routeD(H.S.mapBase, H.S.mapState, 'changshe')];""")
    mk, d = out
    minutes = game.map_state()["places"]["changshe"]["minutes"]
    assert 'class="mv-ring"' in mk and f'class="mv-eta"' in mk and f">{minutes} 分</i>" in mk and "sel" in _lab(mk, "changshe")
    assert d.startswith("M") and ("L" in d or "Q" in d)


def test_names_never_overlap():
    """名字撞在一起時讓開，讓不開的不寫：每一段倍率排出來的名字框兩兩不重疊（照字數估的寬）。"""
    game = _game()
    for z in (1, 1.6, 2.4):
        out = run(game, f"""const html = H.marksHtml(H.S.mapBase, H.S.mapState, {{ z: {z}, x: 0, y: 0 }}, {WIDE});
return [...html.matchAll(/class="mv-lab[^"]*" style="left:([-\\d.]+)px;top:([-\\d.]+)px" data-act="map-place" data-id="([^"]+)"/g)].map((m) => [m[3], +m[1], +m[2]]);""")
        assert len(out) > 10
        spots = {(round(x), round(y)) for _, x, y in out}
        assert len(spots) == len(out), z  # 沒有兩個名字擺在同一點


# ── 看哪裡 ──
def test_the_camera_is_clamped_between_the_whole_world_and_three_times():
    """倍率在「整張天下放得下」到 3.2 倍之間；圖比畫面大時拖到最遠，圖的邊貼著畫面的邊（不露出圖外，Joy 10/30「滑到邊邊會破圖」）。"""
    out = run(_game(), f"""const g = {{ vw: 390, vh: 700 }};
const lo = H.zMin(g), small = H.camClamp({{ z: 0.01, x: 0, y: 0 }}, g), big = H.camClamp({{ z: 99, x: 0, y: 0 }}, g);
const far = H.camClamp({{ z: 1, x: 99999, y: 99999 }}, g), fit = H.camFit(g);
const back = H.camClamp({{ z: 1, x: -99999, y: -99999 }}, g);
return {{ lo, small: small.z, big: big.z, farLeft: far.x, farRight: back.x + H.S.mapBase.w * back.z, fitZ: fit.z }};""")
    assert out["small"] == out["lo"] == out["fitZ"] and out["big"] == 3.2 and 0 < out["lo"] < 1
    assert out["farLeft"] == 0 and out["farRight"] == 390  # 左邊、右邊都貼著畫面的邊


def test_the_view_moves_the_world_layer_not_the_marks_root():
    """拖縮每一幀只換地圖那一層（#mvw）的 transform；字那一層照上一次排字的倍率先跟著縮放，不重排。"""
    src = APP.read_text(encoding="utf-8")
    body = src[src.index("function camSet("):]
    body = body[: body.index("\n  }\n")]
    assert 'w.style.transform = `translate(' in body and "innerHTML" not in body


def test_opening_the_map_centres_on_you_with_the_near_row():
    out = run(_game(), "H.S.mapSel = 'changshe'; H.S.mapMode = 'place'; H.mapFirst(); return [H.S.mapMode, H.S.mapSel, H.S.mapCam, H.S.mapDrawer];")
    assert out == ["overview", None, None, "peek"]


def test_travel_stays_on_the_map():
    js = APP.read_text(encoding="utf-8")
    body = js[js.index("async function travel(mode)"):]
    body = body[: body.index("\n  }\n") + 4]
    assert 'S.tab = "jianghu"' not in body and "loadMap()" in body and "S.mapSel" in body


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
    assert marks(game, 0.5, mapMode="timeline", mapWeek=1).count('class="mv-pulse"') == 1  # 地圖上那一塊閃一圈


def test_the_timeline_without_territory_says_so():
    out = run(_game(), "return H.timelineHtml(H.S.mapBase, H.S.mapState, 1);")
    assert "這一季沒有地盤易手" in out and "<polyline" not in out


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
    """FB-264：第 1 週的易手（跟開季比）在年表上有白點、選第 1 週時地圖上閃一圈、那一週的清單列得出來。"""
    from tianxia import territory

    game = _game()
    w, c = game.state.world, game.content
    territory.update(w, c)
    territory.assign(w, c, {"runan_wilds": "guan"})
    chart = run(game, "return H.chartHtml(H.S.mapBase, H.S.mapState, 1);")
    assert 'class="cell now flip"' in chart
    assert marks(game, 0.5, mapMode="timeline", mapWeek=1).count('class="mv-pulse"') == 1  # 汝南荒野閃一圈
    tl = run(game, "return H.timelineHtml(H.S.mapBase, H.S.mapState, 1);")
    assert "汝南荒野" in tl[tl.index("第 1 段（"):]


def test_the_timeline_drawer_is_320_high_on_a_phone():
    """對比 3 選乙（企劃者 10/15）：版圖變化時抽屜 320 高，地圖大一截，年表往下捲。"""
    assert run(_game(), 'return H.mapDrawerPx("tl");') == 320


def test_a_losing_suggestion_is_faded():
    """對比 4 選乙（企劃者 10/15）：必敗的照樣列、排在最後、整列淡一點（挪到卡底下照舊）。
    約戰開著時推薦只列貼得了約戰的地方（FB-855），新角色那幾處全是必敗的，下一條另鎖；這一條量的是舊出陣的推薦（約戰子開關關掉，同 conquest_kit）。"""
    game = _game()
    game.content.config.jianfa.sortie_duel = False
    st = game.map_state()
    out = run(game, "return H.cardExtras(H.S.mapBase, H.S.mapState);")
    assert [g["lose"] for g in st["suggest"]] == [False, False, False, True]  # 官軍在潁川：三處打得過，再一處必敗的
    assert out.count('class="m-go lose"') == 1 and out.count('class="m-go"') == 3
    assert out.index('class="m-go lose"') > out.rindex('class="m-go"')


def test_with_duels_on_the_suggestions_are_only_places_that_can_post_and_a_new_hand_sees_them_all_faded():
    """FB-855 之後：約戰開著，開季官軍新角色的推薦只剩貼得了約戰的三處，威力不夠全是必敗的，照樣整列淡一點。"""
    game = _game()
    st = game.map_state()
    rows = st["suggest"]
    assert rows and all(g["lose"] for g in rows)
    assert len(rows) <= 3 and all(g["sortie"] == "attack" for g in rows)
    out = run(game, "return H.cardExtras(H.S.mapBase, H.S.mapState);")
    assert out.count('class="m-go lose"') == len(rows) and out.count('class="m-go"') == 0


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


def test_fb905_a_passing_convoy_makes_the_card_button_say_intercept_without_the_attack_odds():
    """FB-9005（PM 照 QA 驗收順帶開，2026-10-28）：這週截糧的運糧隊正打這裡經過，行動列那一格是「出陣・截糧」、按了打運糧隊；輿圖卡上的鈕照舊寫
    「出陣・攻 必敗」，跟行動列對不上。現在寫「出陣・截糧」、小字只剩今日還能幾次（不掛攻的勝算；卡下面的「此地的對手」照舊列運糧隊與它的勝算）。"""
    from tianxia import orders
    from tianxia.state import Order

    game = _game(faction="guan", at="runan_wilds")
    game.state.world.orders.append(Order(id="t:guan:intercept", template="intercept", faction="guan", week=orders.period_of(game.state, game.content),
                                         location="runan_wilds", quota=4, text="（測試）"))
    st = game.map_state()
    p = st["places"]["runan_wilds"]
    assert p["sortie"] == "attack" and p["convoy"] is True and p["odds"]
    out = run(game, 'return H.placeCard(H.S.mapBase, H.S.mapState, "runan_wilds");', st=st)
    sortie = out[out.index('data-key="sortie"'):]
    button = sortie[:sortie.index("</button>")]
    assert "出陣・截糧" in button and "出陣・攻" not in button and p["odds"]["word"] not in button and "今日還能" in button
    foes = out[out.index("此地的對手"):out.index('class="m-foes"') + 400]
    assert p["odds"]["word"] in foes  # 對手那一段照舊寫運糧隊與勝算


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
const drawer = { style: {} }, fab = { style: {} }, props = {};
const body = { innerHTML: '', dataset: {} }, box = { clientHeight: 650, style: { setProperty: (k, v) => { props[k] = v; } } };
const els = { mapx: box, mdrawer: drawer, mbody: body, 'mv-fab': fab };
const orig = T.ctx.document.getElementById;
T.ctx.document.getElementById = (id) => els[id] || orig(id);
"""


def test_the_drawer_heights_and_the_buttons_follow_it():
    """半開量不到 .m-peek-end（還沒排版）時：附近那一排 196、一處的卡至少 200（三分之一）；拉高六成、全開九成四；右下兩顆圓鈕跟著抽屜上下。"""
    out = run(_game(), DRAWER_DOM + """
H.setMapDrawer('peek');
const near = [drawer.style.height, fab.style.bottom];
H.S.mapMode = 'place'; H.S.mapSel = 'changshe'; H.setMapDrawer('peek');
const place = drawer.style.height;
H.setMapDrawer('half'); const half = drawer.style.height;
H.setMapDrawer('full'); const full = drawer.style.height;
return { near, place, half, full, props };
""")
    assert out["near"] == ["196px", "208px"]
    assert out["place"] == f"{round(650 / 3)}px" and out["half"] == f"{round(650 * 0.6)}px" and out["full"] == f"{round(650 * 0.94)}px"
    assert out["props"] == {}  # --md-h 只有版圖變化才寫


def test_picking_and_going_back():
    """點一處：抽屜開那一處的卡（半開）；點地圖的空白、卡上的 ✕：回附近那一排。"""
    out = run(_game(), DRAWER_DOM + """
H.mapPick('changshe');
const card = [H.S.mapMode, H.S.mapSel, H.S.mapDrawer, body.innerHTML.includes('長社'), body.innerHTML.includes('m-peek-end')];
H.mapBack();
return { card, back: [H.S.mapMode, H.S.mapSel, H.S.mapDrawer, body.innerHTML.includes('m-cards')] };
""")
    assert out["card"] == ["place", "changshe", "peek", True, True]
    assert out["back"] == ["overview", None, "peek", True]


def test_the_drawer_height_variable_is_only_written_while_watching_the_timeline():
    js = APP.read_text(encoding="utf-8")
    body = js[js.index("function setMapDrawer("):]
    body = body[: body.index("\n  }\n")]
    assert 'if (S.mapMode === "timeline") box.style.setProperty("--md-h"' in body


def test_status_bar_redraws_do_not_rewrite_inherited_variables_when_nothing_changed():
    src = APP.read_text(encoding="utf-8")
    frame = src[src.index("function mapFrame()"):]
    frame = frame[:frame.index("\n  }\n")]
    assert "setVar(box, \"--map-top\"" in frame and "style.setProperty" not in frame
    assert 'setVar(document.documentElement, "--top-h"' in src


# ── 原 test_fb470_terrain_line_wrap.py（整檔搬進來） ──
# FB-470（第 36 項「武學隨地理環境」QA，2026-10-19）：輿圖抽屜「地利」那一句（26 字）在 375 寬斷成「…施展不／開。」、
# 360 與桌面斷成「…施展／不開。」——照 FB-433 掮客那一句（sayHtml）切在「：」「，」後面包成不折行的小段，字一個不改。

DRIVER_fb470 = r"""
const H = new Function([konst("esc"), konst("LEDGER_NB"), konst("SAY_AFTER"), fn("sayHtml"), fn("terrainArtsRow"),
  "return { terrainArtsRow };"].join("\n"))();
finish(input.lines.map((t) => H.terrainArtsRow({ terrain_arts: t })));
"""


HEAD = '<div class="m-sec"><h4>地利</h4>'


SPAN = re.compile(r'<span class="nb">([^<]*)</span>')


@pytest.mark.slow
def test_the_terrain_line_breaks_only_after_its_commas():
    c = real_content()
    lines = sorted({terrain.place_line(c, loc) for loc in c.locations} - {""})
    assert len(lines) == 4  # 火、水、山、風
    rows = webharness.run(DRIVER_fb470, {"lines": lines})
    for line, row in zip(lines, rows):
        assert row.startswith(HEAD) and row.endswith("</div>")
        body = row[len(HEAD):-len("</div>")]
        assert htmllib.unescape(re.sub(r"<[^>]+>", "", body)) == line  # 字一個不改
        assert SPAN.sub("", body) == ""  # 每一個字都在不折行的小段裡
        chunks = SPAN.findall(body)
        assert "".join(chunks) == line and len(chunks) == 3
        assert [chunk[-1] for chunk in chunks] == ["：", "，", "。"]  # 只在「：」「，」後面換行
        assert chunks[-1].endswith("的施展不開。")  # 「施展不開」整個在同一段


def test_no_terrain_draws_nothing():
    assert webharness.run(DRIVER_fb470, {"lines": [""]}) == [""]


def test_go_to_map_opens_on_the_target_with_both_ends_of_an_escort():
    """江湖頁「去輿圖」帶著目標（Joy 2026-10-31「應該直接點到目標地點」）：輿圖開在那一處、抽屜開它的卡；
    護糧多一個終點：兩點都框進露出來的那一塊，下一站、終點各標一個字。"""
    game = _game(at="yingchuan")
    out = run(game, f"""H.mapGoto('nanyang_wilds', 'nanyang_huangjin_camp');
const g = {{ vw: 390, vh: 700 }}, c = H.camFirst(g), at = (id) => {{ const b = H.S.mapBase.places.find((x) => x.id === id); return [c.x + b.x * c.z, c.y + b.y * c.z]; }};
H.S.mapCam = c;
return {{ mode: H.S.mapMode, sel: H.S.mapSel, keep: H.S.mapKeep, a: at('nanyang_wilds'), b: at('nanyang_huangjin_camp'), html: H.marksHtml(H.S.mapBase, H.S.mapState, c, {WIDE}) }};""")
    assert (out["mode"], out["sel"], out["keep"]) == ("place", "nanyang_wilds", True)
    for x, y in (out["a"], out["b"]):
        assert 0 < x < 390 and 0 < y < 700
    assert "下一站" in _lab(out["html"], "nanyang_wilds") and "終點" in _lab(out["html"], "nanyang_huangjin_camp")


def test_the_plan_card_button_carries_its_place():
    game = _game()
    x = {"head": "曹操的打算", "text": "", "place": "長社", "location": "changshe", "when": "", "minutes": 6, "help": 0, "block": 0,
         "help_side": "官軍", "mine": None, "acts": []}
    out = run(game, "return H.planHtml(" + json.dumps(x, ensure_ascii=False) + ");")
    assert 'data-goto="changshe"' in out
