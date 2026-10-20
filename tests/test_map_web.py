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
from conftest import classic_rules, real_content, third_party_gentry
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES = ["S", "pageMap", "marksSvg", "regionTint", "controlAt", "hudHtml", "chipsHtml", "drawerHtml",
         "overviewHtml", "placeHtml", "searchHtml", "timelineHtml", "graphSvg", "chartHtml", "mapDrawerPx", "firstScale", "clampView", "focusView", "setMapDrawer", "mapPad", "toggleLayer", "insightRow", "homeDrawer", "drawerNow", "drawerTo", "redrawDrawer", "miniHtml"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
NOW = "{ k: 1, far: false, layers: new Set(%s), sel: null, week: H.S.mapState.now_week }"


def _game(faction="guan", at="yingchuan", classic=False, third_party=False):
    c = real_content("weekend")
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


def run(game, script, stored=None, **S):
    # 這一檔測的是區圖那一層（輿圖升級那一張、可以拖縮）：輿圖重製第 2 批起打開輿圖第一眼是天下圖（S.mapLayer "world"，
    # tests/test_world_map_web.py），這裡照舊停在區圖
    payload = {"m": server.main_view(game), "script": script,
               "S": {"mapBase": game.map_base(), "mapState": game.map_state(), "mapLayer": "region", **S},
               "menxia": None, "stored": stored or {}, "responses": {}}
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
    assert "東郡" in out and re.search(r"官 \d", out) and "潁川郊野" not in out  # 大區名（輿圖重製第 1 批：九州）


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
    assert out["yingchuan"] in ("#DCE5F0", "#F4E7C2", "#DFEBDD")
    assert run(_game(), "return H.regionTint(H.S.mapBase, H.S.mapState, H.S.mapState.now_week, false);") == {}


def test_the_overview_answers_where_to_sortie_today():
    out = run(_game(), "return H.overviewHtml(H.S.mapBase, H.S.mapState);")
    assert "今天去哪裡出陣" in out and out.count('data-act="map-pick"') >= 1 and "中原" in out


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


def test_the_tally_compares_with_the_season_start():
    """「天下」那一條跟開季那一刻比（FB-264：第一次算地盤就在第 1 週時有開季的基準），看第 1 週也比得出來。"""
    game = _timeline_game()
    out = run(game, "return [H.hudHtml(H.S.mapBase, H.S.mapState, 3), H.hudHtml(H.S.mapBase, H.S.mapState, 1)];")
    assert "比開季" in out[0] and "比開季" in out[1] and "比第" not in out[0]
    tl = run(game, "return H.timelineHtml(H.S.mapBase, H.S.mapState, 3);")
    assert "比開季" in tl


def test_the_tally_without_a_season_start_compares_with_the_first_recorded_week():
    """中途上線（第一次算在第 3 週）：沒有開季的基準，比第一筆記到的那一週、照實寫第幾週；看的就是那一週時不比。"""
    from tianxia import calendar, territory

    game = _game()
    w, c = game.state.world, game.content
    w.time = calendar.week_start(3, c, w) + 60
    territory.update(w, c)
    w.time = calendar.week_start(4, c, w) + 60
    territory.update(w, c)
    out = run(game, "return [H.hudHtml(H.S.mapBase, H.S.mapState, 4), H.hudHtml(H.S.mapBase, H.S.mapState, 3)];")
    assert "比第 3 週" in out[0] and "開季" not in out[0]
    assert "比第" not in out[1] and "開季" not in out[1]


def test_fb264_week_one_flips_show_in_the_chart_and_flash_on_the_map():
    """FB-264：第 1 週的易手（跟開季比）在年表上有白點、選第 1 週時地圖閃一圈、那一週的清單列得出來。"""
    from tianxia import territory

    game = _game()
    w, c = game.state.world, game.content
    territory.update(w, c)
    territory.assign(w, c, {"nanyang_huangjin_camp": "guan"})  # 開季歸黃巾（輿圖重製第 1 批：中原那一條線的第 7 處）
    chart = run(game, "return H.chartHtml(H.S.mapBase, H.S.mapState, 1);")
    assert 'class="cell now flip"' in chart
    out = marks(game, week=1, tl="true")
    assert out.count('class="pulse"') == 2  # 南陽黃巾營，加上你的那一圈
    tl = run(game, "return H.timelineHtml(H.S.mapBase, H.S.mapState, 1);")
    assert "南陽黃巾營" in tl[tl.index("第 1 週</h4>"):]


def test_the_timeline_button_sits_under_the_zoom_buttons():
    """對比 2 選丙（企劃者 10/15）：「⏱ 版圖」是右上角第四顆圓鈕，濾鏡那一排只放濾鏡：五顆。意境提示開著時「意境」也在右上角那一欄
    （FB-325，企劃者 10/17 從對比圖選丙：六顆時 375 寬「劇情」超出畫面），濾鏡那一排照舊五顆。"""
    out = run(_game(), "return [H.pageMap(), H.chipsHtml()];")
    ctl = out[0][out[0].index('class="map-ctl"'):]
    ctl = ctl[: ctl.index("</div>")]
    assert 'data-act="map-timeline"' in ctl and "版圖" in ctl
    assert "map-timeline" not in out[1] and out[1].count('data-act="map-layer"') == 5
    game = _game()
    game.content.config.insight_strong.enabled = False
    assert run(game, "return H.chipsHtml();").count('data-act="map-layer"') == 5


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


def test_the_sword_sits_on_places_you_can_attack():
    """企劃者 10/15 對比 1 選乙：⚔ 是地點旁的紅色小圓章，只標在疊層說能出陣攻的地方；兩頭歸不同人的鋸齒前線照留。"""
    game = _game()
    n = sum(p["armed"] for p in game.map_state()["places"].values())
    out = marks(game)
    assert n and out.count('class="armed"') == n and out.count("⚔") == n and 'class="front"' in out


def test_no_sword_for_a_ranger_or_the_strongmen():
    for faction in (None, "haoqiang"):
        out = marks(_game(faction=faction))
        assert 'class="armed"' not in out and "⚔" not in out, faction


def test_the_far_view_has_no_sword():
    out = marks(_game(), k=2.5, far="true")
    assert "⚔" not in out


def test_fb260_discs_and_glyphs_keep_their_size_on_screen():
    """FB-260：圓盤與圓盤裡的字照設計固定螢幕大小——倍率加倍（k 減半）時，地圖單位裡的半徑、字級、框線都剛好減半。"""
    game = _game()

    def disc(k):
        out = marks(game, k=k)
        g = out[out.index('<g data-loc="yingchuan_wilds"'):]
        g = g[: g.index("</g>")]
        r = float(re.search(r'r="([\d.]+)" fill="#FBF6EA" stroke="[^"]+" stroke-width="([\d.]+)"', g).group(1))
        w = float(re.search(r'fill="#FBF6EA" stroke="[^"]+" stroke-width="([\d.]+)"', g).group(1))
        size = float(re.search(r'font-size="([\d.]+)"[^>]*>野<', g).group(1))
        return r, w, size

    big, small = disc(1), disc(0.5)
    for a, b in zip(big, small):
        assert abs(b - a / 2) <= 0.1, (big, small)


def test_fb261_the_timeline_folds_the_search_and_chips_away():
    """FB-261：版圖變化時搜尋框與濾鏡收起來（不佔位置、點不到），「天下」那一條才不疊在搜尋框上。"""
    css = re.sub(r"/\*.*?\*/", "", (Path(server.WEB) / "style.css").read_text(encoding="utf-8"), flags=re.S)
    assert re.search(r"\n\.mapx\.tl-mode \.map-top \{[^}]*display: none", css)


def test_fb261_far_view_tallies_are_drawn_over_the_dots():
    """FB-261：看大局時大區的「官 N・巾 N・豪 N」畫在地點小點之後，不被蓋掉。"""
    out = marks(_game(), k=2.5, far="true")
    tally = re.search(r"官 \d", out).start()
    assert tally > out.rindex("<g data-loc=")


def test_fb262_standing_there_still_shows_the_odds():
    """FB-262：站在那個地點時「打得過嗎」照那裡的對手寫勝算（不寫「—」），出陣・攻那一顆也寫勝算；沒有對手才寫沒有對手。"""
    game = _game(faction="guan", at="nanyang_huangjin_camp")  # 開季歸黃巾（輿圖重製第 1 批：v1 是汝南荒野）
    p = game.map_state()["places"]["nanyang_huangjin_camp"]
    assert p["sortie"] == "attack" and p["odds"]
    out = run(game, 'return H.placeHtml(H.S.mapBase, H.S.mapState, "nanyang_huangjin_camp");')
    cell = out[out.index("打得過嗎"):out.index("多遠")]
    assert p["odds"]["word"] in cell and "<b>—</b>" not in cell
    sortie = out[out.index('data-key="sortie"'):]
    assert p["odds"]["word"] in sortie[: sortie.index("</button>")]
    calm = run(_game(faction="guan", at="yingchuan"), 'return H.placeHtml(H.S.mapBase, H.S.mapState, "yingchuan");')
    assert "沒有對手" in calm[calm.index("打得過嗎"):calm.index("多遠")]


def test_fb263_a_wide_desktop_fills_the_map_area():
    """FB-263：桌機寬螢幕第一次打開輿圖，地圖佔滿抽屜左邊整塊（1920 寬地圖區約 1545px，不再照原尺寸 900px 留 640px 空白）；
    1280 寬照舊約原尺寸、手機照舊原尺寸。倍率最多 MAP_MAX（2）。"""
    out = run(_game(), "return [H.firstScale(1545, 640, 900, 1340, false), H.firstScale(905, 640, 900, 1340, false), H.firstScale(375, 470, 900, 1340, true), H.firstScale(2600, 900, 900, 1340, false)];")
    wide, desk, phone, huge = out
    assert 1545 / 900 - 0.01 <= wide <= 1545 / 900 + 0.01 and 900 * wide >= 1544
    assert 0.99 <= desk <= 1.01 and phone == 1 and huge == 2


# ── 下緣的地點被抽屜蓋住（PM 2026-10-15 定要修）：地圖底下可以多捲一個抽屜的高度，選了的地點對準抽屜上面露出來的那一塊 ──
SHOT = "const vw = 375, vh = 650, MW = 900, MH = 1340, pad = 240;"
SCREEN_Y = "(v, p) => vh / 2 + (p[1] - v.cy) * v.s"


def test_a_place_at_the_bottom_edge_is_focused_above_the_drawer():
    out = run(_game(), SHOT + f"const y = {SCREEN_Y}; const p = [600, 1320];"
              "const old = H.clampView({ s: 1, cx: p[0], cy: p[1] }, vw, vh, MW, MH);"
              "const now = H.focusView({ s: 1, cx: 450, cy: 600 }, p, vw, vh, MW, MH, pad);"
              "return [y(old, p), y(now, p), now.cy];")
    covered, shown, cy = out
    assert covered > 650 - 240  # 以前：夾在地圖邊上，落在抽屜底下
    assert 0 <= shown <= 650 - 240 - 10  # 現在：地圖底下多捲一個抽屜高，最下緣的地點也在抽屜上面
    assert cy > 1340 - 650 / 2  # 以前最多捲到 H − vh／2
    middle = run(_game(), SHOT + f"const y = {SCREEN_Y}; const p = [600, 1000]; return y(H.focusView({{ s: 1, cx: 450, cy: 600 }}, p, vw, vh, MW, MH, pad), p);")
    assert abs(middle - (650 - 240) / 2) <= 1  # 不靠邊的地點：對準露出來那一塊的正中間


def test_the_drawer_pad_changes_nothing_when_it_is_zero():
    out = run(_game(), SHOT + "return [H.clampView({ s: 1, cx: 600, cy: 1320 }, vw, vh, MW, MH), H.clampView({ s: 1, cx: 600, cy: 1320 }, vw, vh, MW, MH, 0),"
              "H.clampView({ s: 0.3, cx: 10, cy: 10 }, vw, vh, MW, MH)];")
    assert out[0] == out[1] and out[0]["cy"] == 1340 - 650 / 2
    assert out[2]["cx"] == 450 and out[2]["cy"] == 670  # 比視窗小：照舊置中


def test_a_small_map_is_centered_in_the_part_above_the_drawer():
    """整張比露出來那一塊還矮（高的框、縮到最小）：置中在抽屜上面那一塊。"""
    out = run(_game(), "const vw = 375, vh = 1200, MW = 900, MH = 1340, pad = 240;"
              "const v = H.clampView({ s: 0.1, cx: 0, cy: 0 }, vw, vh, MW, MH, pad); return vh / 2 + (MH / 2 - v.cy) * v.s;")
    assert abs(out - (1200 - 240) / 2) <= 1


def test_choosing_or_raising_the_drawer_refocuses_a_covered_place():
    """選地點（找地點、建議）一律對準露出來那一塊；抽屜拉高、點在地圖上的地點被蓋住時也重新對準（源碼對得上）。"""
    js = (Path(server.WEB) / "app.js").read_text(encoding="utf-8")
    center = js[js.index("function mapCenterOn("):]
    assert "focusView(" in center[: center.index("\n  }\n")]
    drawer = js[js.index("function setMapDrawer("):]
    assert "keepSelVisible(" in drawer[: drawer.index("\n  }\n")]
    pick = js[js.index("function mapPick("):]
    assert "keepSelVisible(" in pick[: pick.index("\n  }\n")]


def test_the_drawer_pad_uses_the_height_it_is_going_to():
    """抽屜換高度有動畫：量 offsetHeight 會拿到舊的高度（從找地點全開挑一處時量到九成四、地圖被捲過頭），照 mapDrawerPx 算要變成的高度。"""
    js = (Path(server.WEB) / "app.js").read_text(encoding="utf-8")
    body = js[js.index("function mapPad("):]
    body = body[: body.index("\n  }\n")]
    assert "mapDrawerPx(S.mapDrawer)" in body and "offsetHeight" not in body


# ── FB-267：抽屜拉高再放回原高，地圖要照較小的 pad 當下夾回去（不露空白、下一次拖動照手指方向走）──
FAKE_DOM = """
const svg = { viewBox: { baseVal: { width: 900, height: 1340 } }, style: {} };
const wrap = { clientWidth: 375, clientHeight: 650, clientLeft: 0, clientTop: 0, getBoundingClientRect: () => ({ left: 0, top: 0 }),
  querySelector: () => svg, classList: { toggle() {}, add() {}, remove() {} }, style: { getPropertyValue: () => '', setProperty() {} } };
const box = { clientHeight: 650, style: { setProperty() {} } };
const drawer = { style: {}, offsetHeight: 0 };
const els = { map: wrap, mapx: box, mdrawer: drawer };
const orig = T.ctx.document.getElementById;
T.ctx.document.getElementById = (id) => els[id] || orig(id);
"""


def test_fb267_lowering_the_drawer_clamps_the_view_back_at_once():
    out = run(_game(), FAKE_DOM + """
const vh = 650, MH = 1340;
const p = H.S.mapBase.places.find((x) => x.id === 'xinye');
const y = (v) => vh / 2 + (p.y - v.cy) * v.s;
const bottom = (v) => vh / 2 + (MH - v.cy) * v.s;
H.S.mapMode = 'place'; H.S.mapSel = 'xinye'; H.S.mapView = { s: 1, cx: p.x, cy: p.y };
H.setMapDrawer('peek');
H.setMapDrawer('half');  // 拉到一半：新野對準露出來那一塊（地圖可以多捲）
const half = { ...H.S.mapView };
H.setMapDrawer('peek');  // 放回 240
const peek = { ...H.S.mapView };
const pad = H.mapPad();
const v = H.S.mapView;
const dragged = H.clampView({ s: v.s, cx: v.cx, cy: v.cy + 10 / v.s }, 375, vh, 900, MH, pad);  // 手指往上拖 10px（同 gripStep 的算法）
return { pad, halfY: y(half), peekY: y(peek), gap: (vh - pad) - bottom(peek), drag: y(dragged) - y(peek) };
""")
    assert out["pad"] == 240
    assert out["gap"] <= 0.5, out  # 放回原高：地圖下緣不在抽屜上面留空白
    assert -10.5 <= out["drag"] <= 0, out  # 往上拖：地點往上走（到邊就不動），不會往反方向跳


# ── 意境提示（設計第四、五節）──
def test_the_insight_layer_recolours_discs_and_drops_the_territory():
    out = marks(_game(), layers='["insight", "control"]')  # 兩顆都記著也是意境贏（正常互斥，不會同時開）
    assert "url(#mk-halo-" not in out.split("</defs>", 1)[1] and 'class="front"' not in out
    assert 'fill="#DCE8F6"' in out and ">水<" in out and ">城<" not in out  # 潁水河畔的水；城鎮的「城」換成意境的字
    assert 'class="ins-seal"' in out  # 長社悟得到火、風：風掛在右下


def test_without_the_insight_layer_the_discs_are_as_before():
    out = marks(_game())
    assert ">城<" in out and 'class="ins-seal"' not in out and 'fill="#DCE8F6"' not in out


def test_a_stale_insight_layer_with_the_switch_off_is_ignored():  # Review Focus 1
    game = _game()
    game.content.config.insight_strong.enabled = False
    out = marks(game, layers='["control", "insight"]')
    assert "url(#mk-halo-guan)" in out and ">城<" in out and 'class="ins-seal"' not in out


def test_a_place_without_a_strongest_keeps_its_glyph():  # Review Focus 2
    script = ('H.S.mapBase.places.forEach((p) => { p.strong = null; }); '
              'return H.marksSvg(H.S.mapBase, H.S.mapState, ' + NOW % '["insight"]' + ');')
    out = run(_game(), script)
    assert ">城<" in out and 'class="ins-seal"' not in out


def test_the_far_view_dots_take_the_strongest_colour():
    out = marks(_game(), layers='["insight"]', k=2.5, far="true")
    assert 'fill="#2C68B0"' in out and 'fill="#8A5A33"' in out and not re.search(r"官 \d", out)


def test_the_insight_button_sits_under_the_timeline_button_only_when_the_switch_is_on():
    """FB-325（企劃者 10/17 選丙）：意境不在濾鏡那一排，是右上角那一欄版圖下面那一顆（色點＋「意境」，跟版圖同一個樣子）；
    開著時跟濾鏡一樣墨底。開關關著沒有這一顆。"""
    out = run(_game(), "return [H.chipsHtml(), H.pageMap()];")
    assert "意境" not in out[0] and 'data-layer="insight"' not in out[0]
    ctl = out[1][out[1].index('class="map-ctl"'):]
    ctl = ctl[: ctl.index("</div>")]
    assert ctl.index('data-act="map-timeline"') < ctl.index('data-layer="insight"') and "意境" in ctl and "conic-gradient" in ctl
    assert 'class="ins"' in ctl and 'aria-pressed="false"' in ctl[ctl.index('data-layer="insight"') - 120:]
    on = run(_game(), "return H.pageMap();", mapLayers=["insight"])
    assert 'class="ins on"' in on and 'data-layer="insight" aria-pressed="true"' in on
    game = _game()
    game.content.config.insight_strong.enabled = False
    page = run(game, "return H.pageMap();")
    assert "意境" not in page[page.index('class="map-ctl"'):]


def test_territory_and_insight_turn_each_other_off():
    out = run(_game(), 'return [H.toggleLayer(["control", "order"], "insight"), H.toggleLayer(["insight"], "control"), '
                       'H.toggleLayer(["insight", "order"], "insight"), H.toggleLayer(["order"], "enemy")];')
    assert out == [["order", "insight"], ["control"], ["order"], ["order", "enemy"]]


def test_the_drawer_says_what_you_can_sense_with_the_strongest_filled():
    out = run(_game(), 'return H.placeHtml(H.S.mapBase, H.S.mapState, "changshe");')
    assert "此地能悟" in out and 'class="ig strong"' in out and "最濃" in out
    assert out.index("多遠") < out.index("此地能悟") < out.index('class="m-acts"')


def test_the_drawer_line_stays_with_the_switch_off_but_nothing_is_strongest():
    game = _game()
    game.content.config.insight_strong.enabled = False
    out = run(game, 'return H.placeHtml(H.S.mapBase, H.S.mapState, "changshe");')
    assert "此地能悟" in out and "最濃" not in out and 'class="ig strong"' not in out


def test_the_terrain_shows_next_to_the_name_only_with_the_insight_layer():
    on = run(_game(), 'return H.placeHtml(H.S.mapBase, H.S.mapState, "baima_temple");', mapLayers=["insight"])
    off = run(_game(), 'return H.placeHtml(H.S.mapBase, H.S.mapState, "baima_temple");')
    assert '<span class="terrain">寺院</span>' in on and 'class="terrain"' not in off


# ── 抽屜收起（Joy 2026-10-17「今天去哪裡出陣能不能真的縮起來，手機版受影響很大」）──
DRAWER_DOM = FAKE_DOM.replace("const drawer = { style: {}, offsetHeight: 0 };",
    "const cls = new Set(); const drawer = { style: {}, offsetHeight: 0, classList: { contains: (c) => cls.has(c), toggle: (c, on) => (on ? cls.add(c) : cls.delete(c)) } };\n"
    "const body = { innerHTML: '' };").replace("mdrawer: drawer };", "mdrawer: drawer, mbody: body };")


def _drawer(stored=None, left=None, script=""):
    game = _game()
    st = game.map_state()
    if left is not None:
        st["sorties_left"] = left
    payload = {"m": server.main_view(game), "S": {"mapBase": game.map_base(), "mapState": st, "mapLayer": "region"}, "menxia": None, "stored": stored or {}, "responses": {},
               "script": DRAWER_DOM + script}
    return webharness.run(DRIVER, payload)


def test_the_drawer_starts_folded_when_no_sorties_are_left_and_open_otherwise():
    assert _drawer(left=0, script="return [H.homeDrawer(), H.mapDrawerPx('home')];") == ["min", 54]
    assert _drawer(left=3, script="return [H.homeDrawer(), H.mapDrawerPx('home')];") == ["rest", 230]


def test_what_the_player_chose_wins_over_the_default_and_is_remembered():
    assert _drawer(left=0, stored={"tx-map-drawer": "open"}, script="return H.homeDrawer();") == "rest"
    assert _drawer(left=3, stored={"tx-map-drawer": "min"}, script="return H.homeDrawer();") == "min"
    out = _drawer(left=3, script="""
H.drawerTo('min');
const folded = [H.S.mapDrawer, T.ctx.localStorage.getItem('tx-map-drawer'), drawer.style.height, body.innerHTML];
H.drawerTo('rest');
return { folded, opened: [H.S.mapDrawer, T.ctx.localStorage.getItem('tx-map-drawer'), drawer.style.height] };
""")
    assert out["folded"][:3] == ["home", "min", "54px"]
    assert 'class="m-mini"' in out["folded"][3] and "今日還能 3 次" in out["folded"][3] and "▴" in out["folded"][3]
    assert out["opened"] == ["home", "open", "230px"]


def test_polling_never_reopens_a_folded_drawer():
    out = _drawer(left=3, stored={"tx-map-drawer": "min"}, script="""
H.setMapDrawer(H.S.mapDrawer);
H.redrawDrawer(); H.redrawDrawer();  // 輪詢、loadMap 換疊層都只叫這兩個
H.setMapDrawer(H.S.mapDrawer);
return [drawer.style.height, body.innerHTML.includes('m-mini')];
""")
    assert out == ["54px", True]


def test_running_out_of_sorties_folds_the_drawer_when_the_player_never_chose():
    out = _drawer(left=1, script="""
H.setMapDrawer(H.S.mapDrawer);
const before = drawer.style.height;
H.S.mapState = Object.assign({}, H.S.mapState, { sorties_left: 0 });
H.redrawDrawer();
return [before, drawer.style.height];
""")
    assert out == ["230px", "54px"]


def test_picking_a_place_from_the_folded_drawer_opens_its_card():
    src = Path("web/app.js").read_text(encoding="utf-8")
    pick = src[src.index("function mapPick(target)"):src.index("// 滾輪以游標為準縮放")]
    assert '["home", "min", "rest"].includes(S.mapDrawer)' in pick and 'setMapDrawer("peek")' in pick


# ── 輿圖卡頓（Joy 2026-10-17「輿圖這邊還是很 lag」）──
def test_the_hit_area_width_rides_on_each_circle_not_on_an_inherited_variable():
    """--hit 寫在地圖框上會繼承到整棵（約 1,500 個元素）：縮放每一下都重算樣式。改成每一個點擊圓自己寫外框寬。"""
    out = marks(_game(), k="1")
    assert re.search(r'r="16" fill="#000000" fill-opacity="0" stroke-width="12"', out)  # 倍率 1：R=22 → 2×(22−16)
    far = marks(_game(), k="2.5")
    assert 'fill-opacity="0" stroke-width="36"' in far  # 倍率 0.4：R=34（夾上限）→ 36
    src, css = Path("web/app.js").read_text(encoding="utf-8"), Path("web/style.css").read_text(encoding="utf-8")
    assert "--hit" not in src and "--hit" not in css


def test_panning_moves_the_wrapper_not_the_svg_root():
    """svg 根元素的 transform 一變，Chrome 每一幀重排每一個地名、重畫整張底圖；套在外框上拖移只動合成層。"""
    src = Path("web/app.js").read_text(encoding="utf-8")
    body = src[src.index("function applyMapView("):src.index("const firstScale")]
    assert "g.world.style.transform = shift" in body and "svg.style.transform" not in body
    css = Path("web/style.css").read_text(encoding="utf-8")
    assert ".map-wrap.moving .tx-world-map { will-change: transform; }" in css


def test_status_bar_redraws_do_not_rewrite_inherited_variables_when_nothing_changed():
    src = Path("web/app.js").read_text(encoding="utf-8")
    frame = src[src.index("function mapFrame()"):]
    frame = frame[:frame.index("\n  }\n")]
    assert "setVar(box, \"--map-top\"" in frame and "style.setProperty" not in frame
    assert 'setVar(document.documentElement, "--top-h"' in src
