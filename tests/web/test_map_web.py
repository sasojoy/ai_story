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
from conftest import real_content, third_party_gentry
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
import html as htmllib
import math
from tianxia import terrain

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES = ["S", "pageMap", "controlAt", "drawerHtml", "placeCard", "cardExtras", "searchHtml", "searchResults", "timelineHtml", "graphSvg",
         "chartHtml", "mapDrawerPx", "setMapDrawer", "insightRow", "redrawDrawer", "journeyHtml", "nearHtml", "nearList", "chipList", "chipsHtml",
         "mapFilter", "marksHtml", "groundSvg", "camClamp", "camFit", "zMin", "mapPick", "mapBack", "mapFind", "routeD", "camSet", "mapFirst",
         "groundShow", "landAt", "mapLand", "mvDown", "mvUp", "mvMove", "mvWheel", "camFly", "drawMarks", "mv", "mapGoto", "camFirst", "planHtml",
         "camOpen", "camAt", "mapRoom", "mvZ0", "mvLevel", "mvLayout", "mvArea", "miniHtml", "mapMini", "mapHome", "mapFit", "drawerStops", "drawerTap",
         "mapStop", "mapSortie", "mapRegionFly", "mapPreviewTo", "drawerGrab", "mapGeom", "mvBusy"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
APP = webharness.APP  # 三個檔（main.js、map.js、app.js）接起來的那一份
# 一個夠大的地圖框：整張天下都在「畫面附近」，字一處都不會因為在畫面外被略過
WIDE = "{ vw: 2400, vh: 3600 }"


def _game(faction="guan", at="yingchuan", third_party=False, profile="week7", content=None):
    c = content or real_content(profile)
    c.config.auto_open_first_season = True
    if third_party:
        third_party_gentry(c)  # 豪強是第三方、有割據的規則（豪強分屬兩軍之前）
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
    """整頁一層：地圖框裡一張天下（#mvw：地面 #mk、路線 #mkr，大小是地圖本身的寬高）與照螢幕寫的字那一層（#mkt）；外面浮著
    回到我與看整張兩顆、抽屜。以前三張圖的上面那一排（‹ 天下、大區、看大局）都沒有了。
    輿圖表現第二版 W1：地常駐，「塗層」那一顆拿掉了；地（#mk）是一張向量的 SVG（不再是點陣）。
    W2：上面的搜尋列與篩選那一排（.mv-top）換成左上區名 chip＋右上 🔍 圓鈕、小地圖與箭頭牌的位子（#mv-hud）；篩選籤與 ⏱ 版圖 W3 搬進 🔍 那一頁。"""
    game = _game()
    out = run(game, "return H.pageMap();")
    b = game.map_base()
    assert f'<div class="mv-world" id="mvw" style="width:{b["w"]}px;height:{b["h"]}px">' in out
    assert 'id="mk"' in out and 'id="mkr"' in out and 'class="mv-marks" id="mkt"' in out and 'id="mdrawer"' in out
    assert f'<svg class="mv-ground" id="mk" width="{b["w"]}" height="{b["h"]}" viewBox="0 0 {b["w"]} {b["h"]}"' in out and "<canvas" not in out
    assert 'data-act="map-search"' in out and 'data-act="map-home"' in out and 'data-act="map-fit"' in out
    assert 'class="mv-hud" id="mv-hud"' in out and 'data-act="map-area"' in out and 'id="mv-mini"' in out and 'id="mv-pills"' in out
    assert 'class="mv-top"' not in out and 'id="mv-chips"' not in out and 'data-act="map-wash"' not in out and "塗層" not in out
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


def test_middle_distance_shows_icons_names_and_badges():
    """中間：每一處的小圖與名字、山河名；寶是小圖左上角的徽（輿圖表現第二版 W1：誰佔著看地的顏色，名字旁不再蓋小印、不接「寶」字條）。
    不寫幾分與勝算；沒有危險度徽（設計 2.2「中：沒有危險度徽」，近景才有）。"""
    game = _game()
    out = marks(game, 1)
    assert 'class="mv-pin' in out and 'class="mv-dot' not in out and 'class="mv-reg"' not in out and 'class="mv-geo' in out
    assert 'class="mv-side"' not in out and 'class="mv-rich"' not in out and 'class="mv-bd mv-bd-rich"' in out and 'class="mv-dg' not in out
    assert "<small>" not in _lab(out, "changshe")


def test_close_up_names_are_only_names():
    """近看（輿圖表現第二版 W1）：名字只有名字——分鐘・多半・勝算那一行、悟字都在抽屜的卡與一排卡裡，不畫在圖上。
    W2：兩步內的名字後面接一小段「N 分」（設計 2.1「名字」；長社離潁川郡兩步）。"""
    game = _game()
    out = marks(game, 2)
    minutes = game.map_state()["places"]["changshe"]["minutes"]
    lab = _lab(out, "changshe")
    assert lab and "<small>" not in lab and f'<small class="mv-min">{minutes} 分</small>' in lab and 'class="ins"' not in out


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
return [...html.matchAll(/class="mv-lab[^"]*" style="left:([-\\d.]+)px;top:([-\\d.]+)px[^"]*" data-act="map-place" data-id="([^"]+)"/g)].map((m) => [m[3], +m[1], +m[2]]);""")  # W2 的名字在 style 上多寫框寬
        assert len(out) > 10
        spots = {(round(x), round(y)) for _, x, y in out}
        assert len(spots) == len(out), z  # 沒有兩個名字擺在同一點


# ── 輿圖表現第二版 W1：地與徽（docs/superpowers/specs/2026-10-30-輿圖表現-design.md 2.1、第六章 W1、第七章；企劃者 2026-10-30「照丙定」）──
# 地是每一處的地塊裁到區界、填主人色（沒人佔淡灰）、正在翻斜紋、可出陣橘虛框、你紅框、兩方相接白邊；沒有地塊的拿圓。常駐、三段都畫。
# 近、中景的名字只有名字，小圖角上掛危險度、⚔、寶、本週旗；點一塊地開那一處的卡。資料照伺服器真的給的（season21 開季），要的局面直接改疊層。
UNHELD = "#B9B2A0"
LAND = re.compile(r'<(path|circle) class="ld-fill" data-cell="([^"]+)" [^>]*?fill="([^"]+)" fill-opacity="([\d.]+)"/>')


def _ground(game, st=None, k=1, week=None, **S):
    w = "H.S.mapState.now_week" if week is None else str(week)
    return run(game, f"return H.groundSvg(H.S.mapBase, H.S.mapState, {k}, {w});", st=st, **S)


def _poly(d):
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", d)]
    return list(zip(nums[0::2], nums[1::2]))


def _inside(x, y, pg):
    ins, j = False, len(pg) - 1
    for i in range(len(pg)):
        (xi, yi), (xj, yj) = pg[i], pg[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            ins = not ins
        j = i
    return ins


def _patches(base):
    """拿圓當地的地點（設計 2.1「沒有地塊的地點」）：world.cells 裡沒有它、或它自己的座標落在所屬區的多邊形之外。照底圖自己算一次，不借網頁的。"""
    regions = {r["id"]: _poly(r["d"]) for r in base["world"]["regions"]}
    cells = {c["id"]: c for c in base["world"]["cells"]}
    return {p["id"] for p in base["places"] if p["id"] not in cells or not _inside(p["x"], p["y"], regions[cells[p["id"]]["region"]])}


def _sides(game):
    return {s["id"]: s["color"] for s in game.map_base()["world"]["sides"]}


def _xy(pairs):
    return {(float(x), float(y)) for x, y in pairs}


@pytest.mark.slow  # 單一條超過一秒
def test_w1_every_place_is_land_in_its_holders_colour():
    """每一塊地的填色＝疊層 control 那一方的顏色（34%）；沒人佔淡灰（10%）。地塊裁在它那一區的區界裡（clipPath），一處一塊、不多不少。"""
    game = _game(profile="season21")
    st = game.map_state()
    st["places"]["runan_wilds"]["control"] = "huang"  # 換一塊主人：顏色照疊層，不照開季
    out = _ground(game, st=st)
    sides, base = _sides(game), game.map_base()
    land = {m[1]: (m[0], m[2], float(m[3])) for m in LAND.findall(out)}
    assert set(land) == set(st["places"]) and len(LAND.findall(out)) == len(st["places"])
    held = {q["control"] for q in st["places"].values()}
    assert {"guan", "huang", None} <= held
    for pid, q in st["places"].items():
        want = (sides[q["control"]], 0.34) if q["control"] else (UNHELD, 0.1)
        assert land[pid][1:] == want, pid
    patches = _patches(base)
    cells = {c["id"]: c["region"] for c in base["world"]["cells"]}
    for pid in set(st["places"]) - patches:
        assert f'<g clip-path="url(#lr-{cells[pid]})"><path class="ld-fill" data-cell="{pid}"' in out, pid
    assert out.count('<clipPath id="lr-') == len(base["world"]["regions"])


def test_w1_a_block_being_taken_is_striped_in_both_colours():
    """正在翻：那一塊 45° 斜紋兩色（推的那一方＋現在的主人；沒人佔的是淡灰）50%。看以前的週（版圖變化）不畫斜紋。"""
    game = _game(profile="season21")
    st = game.map_state()
    sides = _sides(game)
    assert st["places"]["yingchuan_wilds"]["control"] == "guan"
    st["places"]["yingchuan_wilds"]["tug"] = {"huang": 40}
    st["places"]["runan_wilds"].update(control=None, tug={"guan": 65})
    out = _ground(game, st=st)
    for pid, a, b in (("yingchuan_wilds", sides["huang"], sides["guan"]), ("runan_wilds", sides["guan"], UNHELD)):
        assert re.search(rf'<path class="ld-fill" data-cell="{pid}" d="[^"]*" fill="url\(#ls-{pid}\)" fill-opacity="0.5"/>', out), pid
        pattern = re.search(rf'<pattern id="ls-{pid}"[^>]*patternTransform="rotate\(45\)">(.*?)</pattern>', out).group(1)
        assert re.findall(r'fill="(#[0-9A-Fa-f]{6})"', pattern) == [a, b]
    assert out.count("<pattern ") == 2
    past = _ground(game, st=st, week=0)
    assert "<pattern " not in past and "url(#ls-" not in past


def _rim(out, pid):
    """那一處的內框（ld-rim，或冷卻的 w-cool）那一個標記。"""
    return re.search(rf'<(?:path|circle) class="(?:ld-rim|w-cool)" data-cell="{pid}" [^>]*?/>', out).group(0)


def test_w1_a_neutral_block_being_taken_has_a_red_rim_as_in_bing():
    """正在翻的中立地：內框照丙畫紅框（企劃者 2026-10-31「照丙用紅框」；草圖 tools/slg5.js 的 txGround：有主人是主人色，沒主人而正在翻是紅
    #C0392B，跟有主的內框一樣粗——stroke 5 裁到塊內、可見 2.5px、0.85、實線、在塊內）。丙跟「你的那一塊」的紅框就差在這裡：你那一塊 stroke 6
    （可見 3px）、不透明，照舊。沒在翻的中立地照舊淡灰細框；有主的地正在翻，內框照舊是主人色；看以前的週（版圖變化）不畫紅框。"""
    game = _game(profile="season21")
    st = game.map_state()
    sides = _sides(game)
    st["places"]["runan_wilds"].update(control=None, tug={"guan": 55})
    st["places"]["yingchuan_wilds"]["tug"] = {"huang": 40}
    calm = next(x for x, q in sorted(st["places"].items()) if not q["control"] and not q.get("tug") and x != "runan_wilds")
    out = _ground(game, st=st)
    red = _rim(out, "runan_wilds")
    assert 'stroke="#C0392B" stroke-width="5" stroke-opacity="0.85"' in red, red
    assert "stroke-dasharray" not in red and 'clip-path="url(#lc-runan_wilds)"' in red
    assert 'stroke="#8F8B82" stroke-width="2.5" stroke-opacity="0.45"' in _rim(out, calm)
    assert f'stroke="{sides["guan"]}" stroke-width="5" stroke-opacity="0.85"' in _rim(out, "yingchuan_wilds")
    here = re.search(rf'<path class="ld-here" data-cell="{st["here"]}" [^>]*?/>', out).group(0)
    assert 'stroke="#C0392B" stroke-width="6"' in here and "stroke-opacity" not in here  # 你那一塊：粗一點、不透明
    assert 'stroke="#8F8B82"' in _rim(_ground(game, st=st, week=0), "runan_wilds")


def test_w1_orange_frames_are_where_you_can_sortie_and_the_hopeless_ones_are_faint():
    """可出陣：那一塊內側橘虛框，框數＝疊層 sortie 不是 null 的數；引擎說必敗的（suggest 的 lose，不在 suggest 裡的照同一個字）畫淡一半。"""
    game = _game(profile="season21")
    st = game.map_state()
    can = {x for x, q in st["places"].items() if q["sortie"]}
    calm = next(x for x in sorted(can) if x not in {g["id"] for g in st["suggest"]})
    st["places"][calm]["odds"] = {"word": "穩勝", "tone": "safe"}  # 打得過的那一處：框不淡
    out = _ground(game, st=st)
    frames = re.findall(r'<(?:path|circle) class="ld-sortie" data-cell="([^"]+)" [^>]*?stroke="#F0A640" stroke-width="6" stroke-dasharray="8 5"( stroke-opacity="0.5")?', out)
    assert len(can) >= 3 and sorted(x for x, _ in frames) == sorted(can)
    lose = {g["id"] for g in st["suggest"] if g["lose"]} | {x for x in can if st["places"][x]["sortie"] == "attack" and not st["places"][x].get("convoy")
                                                             and st["places"][x]["odds"] and st["places"][x]["odds"]["word"] == "必敗"}
    faint = {x for x, f in frames if f}
    assert faint == lose & can and faint and calm not in faint


@pytest.mark.slow  # 單一條超過一秒（走一段路）
def test_w1_your_block_has_a_red_frame_but_not_while_on_the_road():
    game = _game()
    st = game.map_state()
    assert re.findall(r'class="ld-here" data-cell="([^"]+)" [^>]*?stroke="#C0392B" stroke-width="6"', _ground(game, st=st)) == [st["here"]]
    game.travel("changshe", "walk")
    road = game.map_state()
    assert road["journey"] and "ld-here" not in _ground(game, st=road)


def test_w1_the_front_is_every_edge_between_two_holders():
    """戰線：相接的兩塊主人不同，那一段共用邊亮白 3.2（world.edges）；拿圓當地的不算戰線。換一塊主人，戰線跟著換。"""
    game = _game(profile="season21")
    base = game.map_base()
    patches = _patches(base)
    for flip in (None, ("yingchuan_wilds", "huang")):
        st = game.map_state()
        if flip:
            st["places"][flip[0]]["control"] = flip[1]
        ctrl = {x: q["control"] for x, q in st["places"].items()}
        want = sorted((e["a"], e["b"]) for e in base["world"]["edges"] if e["a"] not in patches and e["b"] not in patches
                      and ctrl.get(e["a"]) and ctrl.get(e["b"]) and ctrl[e["a"]] != ctrl[e["b"]])
        out = _ground(game, st=st)
        assert sorted(re.findall(r'<path class="ld-front" data-a="([^"]+)" data-b="([^"]+)"', out)) == want and want, flip
        assert '<g fill="none" stroke="#FFF6E0" stroke-width="3.2" stroke-linecap="round">' in out
    assert any("yingchuan_wilds" in e for e in want)  # 換了主人的那一塊多出戰線


def test_w1_places_without_a_block_stand_on_a_round_patch():
    """沒有地塊（曹氏莊院這類不是區塊的）或座標在區外（官軍大營：地塊裁到區界會裁光）的地點：半徑 view.patch_radius 的圓當它的地，
    一樣填色上框、不裁區界。"""
    game = _game(profile="season21")
    base, st = game.map_base(), game.map_state()
    patches = _patches(base)
    assert {"guan_camp", "cao_manor"} <= patches
    out = _ground(game, st=st)
    r = base["view"]["patch_radius"]
    for p in (b for b in base["places"] if b["id"] in patches):
        circle = re.search(rf'(<g [^>]*>)?<circle class="ld-fill" data-cell="{p["id"]}" cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"', out)
        assert circle and circle.group(1) is None, p["id"]  # 不包在區界的 clip 裡
        assert (float(circle.group(2)), float(circle.group(3)), float(circle.group(4))) == (p["x"], p["y"], r)
        assert f'<clipPath id="lc-{p["id"]}"><circle ' in out


def test_w1_where_a_round_patch_overlaps_a_block_the_round_patch_wins():
    """圓照舊半徑 view.patch_radius 60（企劃者 2026-10-31「照舊 60」）。圓跟地塊重疊的那一截，點了開圓的那一處（PM 2026-10-31 定「圓優先」：
    圓是官軍大營、綠林山寨、南華觀這些沒有地塊的地點，畫得小；landAt 先問圓）。畫的時候圓的填色與內框也排在地塊後面（蓋在上面）；
    地塊的框（可出陣、戰書、你）照舊畫在最上面、會穿過那一截（框只有 3px，W1 審查 2026-10-31 記下、沒改），這一條只比填色。
    每一個圓 × 每一塊跟它重疊的地拿一點（不在別的圓上的）。"""
    game = _game(profile="season21")
    base, st = game.map_base(), game.map_state()
    patches = _patches(base)
    regions = {r["id"]: _poly(r["d"]) for r in base["world"]["regions"]}
    r = base["view"]["patch_radius"]
    assert r == 60
    pos = {b["id"]: b for b in base["places"]}
    spots = []
    for pid in sorted(patches):
        p = pos[pid]
        for c in base["world"]["cells"]:
            if c["id"] in patches or c["id"] not in st["places"]:
                continue
            cell = _poly(c["d"])
            ring = ((f, a) for f in (0.5, 0.8, 0.95) for a in range(0, 360, 10))
            hit = next(((x, y) for x, y in ((p["x"] + f * r * math.cos(math.radians(a)), p["y"] + f * r * math.sin(math.radians(a))) for f, a in ring)
                        if _inside(x, y, cell) and _inside(x, y, regions[c["region"]])
                        and all(q == pid or (x - pos[q]["x"]) ** 2 + (y - pos[q]["y"]) ** 2 > r * r for q in patches)), None)
            if hit:
                spots.append((pid, c["id"], round(hit[0], 2), round(hit[1], 2)))
    pairs = {(p, c) for p, c, _, _ in spots}
    assert ("guan_camp", "yingchuan_wilds") in pairs and len(pairs) >= 5  # 官軍大營的圓蓋到潁川郊野；鄉里結社、曹氏莊院這些也都蓋到鄰塊
    got = run(game, "return [" + ", ".join(f"H.landAt(H.S.mapBase, H.S.mapState, {x}, {y})" for _, _, x, y in spots) + "];", st=st)
    assert got == [p for p, _, _, _ in spots]
    out = _ground(game, st=st)
    for p, c, _, _ in spots:
        assert out.index(f'<circle class="ld-fill" data-cell="{p}"') > out.index(f'<path class="ld-fill" data-cell="{c}"'), (p, c)


@pytest.mark.parametrize("z", [1, 2])
def test_w1_near_and_middle_names_have_no_seal_line_bar_or_insight(z):
    """近、中景：名字只有名字——沒有官／巾小印（.mv-side）、名字後的「寶」「戰」「本週」字條、名字底下那一行、進度條（.mv-bar）、悟字（.ins）。
    W2：近景兩步內的名字後面接一小段「N 分」（.mv-min，設計 2.1「名字」），只有它。"""
    game = _game(profile="season21")
    st = game.map_state()
    st["places"]["yingchuan_wilds"]["tug"] = {"huang": 40}  # 以前會畫進度條
    st["places"]["runan_wilds"]["siege"] = "letter"  # 以前會接「戰」
    st["week"] = {"id": "changshe", "why": "軍令・守城", "minutes": 6}  # 以前會接「本週」
    out = marks(game, z, st=st)
    for gone in ('class="mv-side"', 'class="mv-bar"', 'class="ins"', 'class="mv-rich"', 'class="mv-wk"', "<small>"):
        assert gone not in out, gone
    labs = re.findall(r'<button type="button" class="mv-lab[^"]*"[^>]*data-id="([^"]+)">(.*?)</button>', out)
    near = z == 2  # 這一條用的大地圖框：Z0＝480／250，z＝2 是近景、1 是中景
    hops = _hops(game.map_base(), st["here"])
    assert len(labs) > 10 and all(re.fullmatch(r'<span class="t"><span class="nm">[^<]+(<small class="mv-min">\d+ 分</small>)?</span></span>', x) for _, x in labs)
    assert all(("mv-min" in x) == (near and 0 < hops[pid] <= 2) for pid, x in labs)


def test_w1_every_icon_but_yours_wears_its_danger():
    """危險度徽（右下，1～3）只在近景（設計 2.2「中：沒有危險度徽」、第七章「危險度徽只在近」；W1 審查 2026-10-30）：近景的數目＝畫出來的
    小圖數減一（你腳下那一處不掛），數字照疊層的 danger；在路上每一處都掛。中景一顆都沒有（⚔、寶、本週旗中景照掛，下一條與中景那一條）。
    近、中照 mvLevel 分（W2 換成照 Z0 的三段門檻，這一條不必改）。"""
    game = _game()
    assert 'class="mv-dg' not in marks(game, 1) and 'class="mv-bd mv-bd-rich"' in marks(game, 1)  # z＝1 是中景
    for st in (game.map_state(), None):
        if st is None:
            game.travel("changshe", "walk")
            st = game.map_state()
        out = marks(game, 2, st=st)  # z＝2 是近景
        pins = re.findall(r'class="mv-pin [a-z]+" style="left:([-\d.]+)px;top:([-\d.]+)px[^"]*" data-act="map-place" data-id="([^"]+)"', out)
        dg = re.findall(r'<i class="mv-dg" style="left:([-\d.]+)px;top:([-\d.]+)px">(\d)</i>', out)
        mine = None if st["journey"] else st["here"]
        assert len(pins) == len(st["places"]) and len(dg) == len(pins) - (1 if mine else 0)
        assert sorted((float(x), float(y), d) for x, y, d in dg) == sorted(
            (float(x) + 10, float(y) + 9, str(st["places"][pid]["danger"])) for x, y, pid in pins if pid != mine)


def test_w1_corner_badges_for_a_fight_a_treasure_and_this_week():
    """⚔（右上）：正在翻、激戰；寶（左上）：疊層的 rich；本週（頂上一面紅旗）：疊層的 week。"""
    game = _game(profile="season21")
    st = game.map_state()
    pts = {p["id"]: (p["x"], p["y"]) for p in game.map_base()["places"]}
    st["places"]["yingchuan_wilds"]["tug"] = {"huang": 40}
    st["places"]["changshe"]["melee"] = True
    st["week"] = {"id": "songshan_foot", "why": "軍令・守城", "minutes": 9}
    z = 2  # 近看：地圖座標 × 2 是螢幕座標
    out = marks(game, z, st=st)
    swords = _xy(re.findall(r'<i class="mv-bd mv-bd-x" style="left:([-\d.]+)px;top:([-\d.]+)px">⚔</i>', out))
    assert swords == {(pts[x][0] * z + 11, pts[x][1] * z - 10) for x in ("yingchuan_wilds", "changshe")}
    rich = _xy(re.findall(r'<i class="mv-bd mv-bd-rich" style="left:([-\d.]+)px;top:([-\d.]+)px">寶</i>', out))
    assert rich == {(pts[x][0] * z - 11, pts[x][1] * z - 10) for x, q in st["places"].items() if q["rich"]} and rich
    flags = _xy(re.findall(r'<svg class="mv-flag" width="16" height="24" viewBox="0 0 16 24" style="left:([-\d.]+)px;top:([-\d.]+)px"', out))
    assert flags == {(pts["songshan_foot"][0] * z, pts["songshan_foot"][1] * z - 12)}


@pytest.mark.slow  # 單一條超過一秒（兩下之間要隔開，免得算成雙擊）
def test_w1_tapping_the_land_opens_that_place_and_tapping_it_again_closes_the_card():
    """整塊地都是那一處的熱區（設計 2.3）：點長社那一塊地（不是小圖）開長社的卡、再點一次收回；點圓（曹氏莊院）開它的卡；點區外是空地。
    照畫出來的那一塊算（landAt：圓先、地塊要在區界裡）。點地要等 MV_TAP2 過了才開卡（雙擊只放大，下面那一條），所以每一下之後等一下再看。"""
    game = _game(profile="season21")
    base = game.map_base()
    cell = next(c for c in base["world"]["cells"] if c["id"] == "changshe")
    region = next(r for r in base["world"]["regions"] if r["id"] == cell["region"])
    p = next(b for b in base["places"] if b["id"] == "changshe")
    patches = [b for b in base["places"] if b["id"] in _patches(base)]
    spot = next((p["x"] + dx, p["y"] + dy) for dx, dy in ((30, 0), (-30, 0), (0, 30), (0, -30), (25, 25), (-25, -25), (25, -25), (-25, 25))
                if _inside(p["x"] + dx, p["y"] + dy, _poly(cell["d"])) and _inside(p["x"] + dx, p["y"] + dy, _poly(region["d"]))
                and all((p["x"] + dx - q["x"]) ** 2 + (p["y"] + dy - q["y"]) ** 2 > base["view"]["patch_radius"] ** 2 for q in patches))
    manor = next(b for b in base["places"] if b["id"] == "cao_manor")
    # 地塊伸出區界外的那一截（裁掉、沒畫的）不算那一處的地
    regions = {r["id"]: _poly(r["d"]) for r in base["world"]["regions"]}
    cut = next((x, y) for c in base["world"]["cells"] for x in range(0, base["w"], 7) for y in range(0, base["h"], 7)
               if _inside(x, y, _poly(c["d"])) and not any(_inside(x, y, rg) for rg in regions.values())
               and all((x - q["x"]) ** 2 + (y - q["y"]) ** 2 > base["view"]["patch_radius"] ** 2 for q in patches))
    out = run(game, DRAWER_DOM + f"""
const map = {{ clientWidth: 375, clientHeight: 700, clientLeft: 0, clientTop: 0, getBoundingClientRect: () => ({{ left: 0, top: 0 }}) }};
els.map = map;
H.S.mapCam = {{ z: 1, x: 0, y: 0 }};
const wait = () => new Promise((r) => setTimeout(r, 360));
const tap = async (x, y, id) => {{
  const ev = {{ pointerType: 'touch', button: 0, pointerId: id, clientX: x, clientY: y, target: {{ closest: () => null }} }};
  H.mvDown({{ ...ev, type: 'pointerdown' }}); H.mvUp({{ ...ev, type: 'pointerup' }});
  await wait();
  return [H.S.mapMode, H.S.mapSel, body.innerHTML.includes('data-act="map-back"') && !body.innerHTML.includes('m-cards')];  // 抽屜是那一處的卡
}};
return (async () => {{
  const look = [H.landAt(H.S.mapBase, H.S.mapState, {spot[0]}, {spot[1]}), H.landAt(H.S.mapBase, H.S.mapState, {manor['x']}, {manor['y']}),
    H.landAt(H.S.mapBase, H.S.mapState, -50, -50), H.landAt(H.S.mapBase, H.S.mapState, {cut[0]}, {cut[1]})];
  const open = await tap({spot[0]}, {spot[1]}, 1);
  const shut = await tap({spot[0]}, {spot[1]}, 2);
  const round = await tap({manor['x'] + 20}, {manor['y']}, 3);
  const blank = await tap(-50, -50, 4);
  return {{ look, open, shut, round, blank }};
}})();""")
    assert out["look"] == ["changshe", "cao_manor", None, None]
    assert out["open"] == ["place", "changshe", True]
    assert out["shut"] == ["overview", None, False]
    assert out["round"] == ["place", "cao_manor", True]
    assert out["blank"] == ["overview", None, False]  # 點空地照舊收回


def test_w1_no_stylesheet_rule_overrides_the_lands_own_colours_and_widths():
    """地的顏色、線寬、虛線寫在 SVG 的屬性上；樣式表的規則會蓋過屬性，所以地用到的 class 在 style.css 一條規則都不能有
    （實機踩過：一開始取名 .w-rim、.w-seam，撞到煉爐那一塊的全域樣式，內框整圈變成 1px 的金線）。"""
    from pathlib import Path

    out = _ground(_game(profile="season21"))
    used = set(re.findall(r'class="([\w-]+)"', out))
    assert {"ld-fill", "ld-rim", "ld-seam", "ld-front", "ld-here"} <= used
    css = re.sub(r"/\*.*?\*/", "", (Path(server.WEB) / "style.css").read_text(encoding="utf-8"), flags=re.S)
    selectors = " ".join(sel for sel, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", css))
    for cls in used | {"ld-sortie", "w-cool", "w-letter"}:
        assert not re.search(rf"\.{re.escape(cls)}(?![\w-])", selectors), cls


def test_w1_the_melee_ground_is_gone_from_the_stylesheet_too():
    """激戰的紅底（.w-melee）W1 拿掉了（設計 2.1「激戰」）：網頁不再畫這個 class，樣式表也不留它的規則（藏起來停動畫、減少動態那兩條一起拿掉，
    W1 審查 2026-10-30）；動畫的名字 w-melee 還是激戰那一圈（.mv-fight）在用。"""
    from pathlib import Path

    css = re.sub(r"/\*.*?\*/", "", (Path(server.WEB) / "style.css").read_text(encoding="utf-8"), flags=re.S)
    selectors = " ".join(sel for sel, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", css))
    assert not re.search(r"\.w-melee(?![\w-])", selectors)
    assert "@keyframes w-melee" in css and re.search(r"\.mv-fight \{[^}]*animation: w-melee ", css)
    assert 'class="w-melee' not in webharness.app_source()


def test_w1_the_land_is_always_drawn_and_only_redrawn_per_third_of_a_zoom_octave():
    """地常駐（不再只在遠看、塗層、版圖時畫）：近看也畫；拖縮的途中不重寫（下一條），停下來照倍率的三分之一級
    （log2(z)×3 取整）換線寬，同一級不重寫；換了週次（版圖變化）重寫。線寬照螢幕（k＝1／倍率）。"""
    out = run(_game(profile="season21"), """
const writes = [], mk = {};
Object.defineProperty(mk, 'innerHTML', { set: (v) => { writes.push(v); }, get: () => writes[writes.length - 1] || '' });
const doc = T.ctx.document, byId = doc.getElementById;
doc.getElementById = (id) => (id === 'mk' ? mk : byId(id));
for (const z of [0.4, 0.41, 1, 1.05, 1.3, 2.4]) H.groundShow({ z, x: 0, y: 0 });
const before = writes.length;
H.S.mapMode = 'timeline'; H.S.mapWeek = H.S.mapState.now_week + 1; H.groundShow({ z: 2.4, x: 0, y: 0 });
return { before, after: writes.length, land: writes.map((w) => (w.match(/class="ld-fill"/g) || []).length),
  front: writes.map((w) => w.match(/stroke="#FFF6E0" stroke-width="([\\d.]+)"/)[1]) };""")
    assert out["before"] == 4 and out["after"] == 5
    assert len(set(out["land"])) == 1 and out["land"][0] > 30
    assert out["front"][:4] == ["8.06", "3.2", "2.54", "1.27"]  # 3.2 × 2^(4/3)、×1、×2^(-1/3)、×2^(-4/3)


# 拖縮的途中地不重寫（設計第七章「不能變卡：地塊常駐、每一級距重畫一次，拖縮中只換 transform」、2.2「手勢中凍住、放手重排」）。
# W1 審查（2026-10-30）抓到的：camSet 在捏、滾輪、飛過去的途中照 MV_RELAYOUT 排 drawMarks，drawMarks 又叫 groundShow，跨了三分之一級就把
# #mk 整張重寫（每次約 31KB、47 個 clipPath）。照真的路走：mvDown／mvMove／mvUp、mvWheel、camFly，每一幀跑完排進來的 rAF（接在 DRAWER_DOM 後面）
GESTURE_DOM = """
let seq = 0, extra = 0;
const q = new Map();
T.ctx.requestAnimationFrame = (f) => { q.set(++seq, f); return seq; };
T.ctx.cancelAnimationFrame = (id) => { q.delete(id); };
const frame = () => { extra += 16; const fs = [...q.values()]; q.clear(); for (const f of fs) f(T.ctx.performance.now() + extra); };
const writes = [], mk = {};
Object.defineProperty(mk, 'innerHTML', { set: (v) => { writes.push(v); }, get: () => writes[writes.length - 1] || '' });
const map = { clientWidth: 375, clientHeight: 700, clientLeft: 0, clientTop: 0, getBoundingClientRect: () => ({ left: 0, top: 0 }), setPointerCapture() {} };
Object.assign(els, { map, mk, mkt: { style: {}, innerHTML: '' }, mvw: { style: {} }, mkr: { innerHTML: '' } });
const pt = (type, id, x, y) => ({ type, pointerType: 'touch', button: 0, pointerId: id, clientX: x, clientY: y, target: { closest: () => null } });
const front = (w) => (String(w || '').match(/stroke="#FFF6E0" stroke-width="([\\d.]+)"/) || [])[1];
"""


@pytest.mark.slow  # 單一條超過一秒（三種手勢各走一遍）
def test_w1_the_land_is_not_rewritten_while_pinching_wheeling_or_flying():
    """捏（1 → 3.2）、滾輪（拉遠）、飛過去（拉近）的途中都跨了好幾個三分之一級，#mk 一次都不重寫：地是向量的、本來就跟著 #mvw 的
    transform 縮放（線寬暫時跟著粗細）；放手、滾輪停、飛完的那一次 drawMarks 才照新的倍率重寫一次，線寬回到照螢幕。"""
    out = run(_game(profile="season21"), DRAWER_DOM + GESTURE_DOM + """
return (async () => {
  H.camSet({ z: 1, x: -400, y: -400 }); H.drawMarks(); frame();
  const res = {}, z = () => H.S.mapCam.z;
  let n = writes.length;
  H.mvDown(pt('pointerdown', 1, 150, 350)); H.mvDown(pt('pointerdown', 2, 220, 350));
  for (let i = 1; i <= 40; i++) { H.mvMove(pt('pointermove', 1, 150 - i * 4, 350)); H.mvMove(pt('pointermove', 2, 220 + i * 4, 350)); frame(); }
  res.pinch = { during: writes.length - n, z: z() };
  H.mvUp(pt('pointerup', 1, -10, 350)); H.mvUp(pt('pointerup', 2, 380, 350)); frame();
  Object.assign(res.pinch, { after: writes.length - n, front: front(writes[writes.length - 1]) });
  n = writes.length;
  for (let i = 0; i < 20; i++) { H.mvWheel({ deltaY: 60, deltaMode: 0, clientX: 180, clientY: 350, preventDefault() {} }); frame(); }
  res.wheel = { during: writes.length - n, z: z() };
  await new Promise((r) => setTimeout(r, 240)); frame();
  Object.assign(res.wheel, { after: writes.length - n, front: front(writes[writes.length - 1]) });
  n = writes.length; extra = 0;
  H.camFly({ z: 3, x: -1500, y: -1500 });
  let during = 0, frames = 0;
  while (q.size && frames < 300) { frame(); frames++; if (H.mv.anim) during = writes.length - n; }
  res.fly = { during, frames, z: z(), after: writes.length - n, front: front(writes[writes.length - 1]) };
  return res;
})();""")
    for name, start in (("pinch", 1), ("wheel", out["pinch"]["z"]), ("fly", out["wheel"]["z"])):
        g = out[name]
        assert g["during"] == 0 and g["after"] == 1, (name, g)
        assert abs(math.log2(g["z"] / start)) > 1, (name, g)  # 真的跨了好幾個三分之一級
        assert abs(float(g["front"]) * g["z"] / 3.2 - 1) < 0.13, (name, g)  # 放手那一次照新的倍率：白邊 3.2 照螢幕（差不到三分之一級）
    assert out["fly"]["frames"] > 5


# ── FB-9070、FB-9071（W1 第二輪，2026-10-31；QA qa/map-view-w1 開的兩張）──
# FB-9070：框（內框、正在翻的中立紅框、冷卻虛內框、可出陣橘框、戰書框、你的紅框）要沿著看得到的那一塊（塊 ∩ 區）描一整圈。以前只描塊的
# 多邊形、裁到塊內再裁到區界，塊伸出區界的那一截被裁掉，區界上那一段沒有框（36 塊有 30 塊缺 5% 以上，下曲陽缺七成）。
# 量法照 QA（scratchpad qa-w1/p4.js）：沿著每一塊看得到的外框取樣——塊的邊落在區內的那幾段、區界落在塊內的那幾段，每一點往那一塊裡面
# 挪半個框寬，看有沒有一條框畫在那裡：離那一條框的路徑（每一段子路徑）不到半個線寬、而且在它的每一層裁切裡面（自己的 clip-path 與
# 外面每一層 <g> 的）。虛線當實線算（量的是那一邊有沒有框）。在 node 裡照 groundSvg 吐出來的標記算，不靠瀏覽器排版。
COVER_JS = r"""
function landCover(base, svg, want) {
  const pts = (d) => { const n = (String(d).match(/-?\d+(?:\.\d+)?/g) || []).map(Number), o = []; for (let i = 0; i + 1 < n.length; i += 2) o.push([n[i], n[i + 1]]); return o; };
  const subs = (d) => String(d || "").split(/(?=M)/).map(pts).filter((p) => p.length > 2);
  const inside = (x, y, pg) => { let r = false; for (let i = 0, j = pg.length - 1; i < pg.length; j = i++) { const a = pg[i], e = pg[j]; if ((a[1] > y) !== (e[1] > y) && x < ((e[0] - a[0]) * (y - a[1])) / (e[1] - a[1]) + a[0]) r = !r; } return r; };
  const seg = (x, y, a, b) => { const dx = b[0] - a[0], dy = b[1] - a[1], L = dx * dx + dy * dy; let t = L ? ((x - a[0]) * dx + (y - a[1]) * dy) / L : 0; t = t < 0 ? 0 : t > 1 ? 1 : t; return Math.hypot(a[0] + t * dx - x, a[1] + t * dy - y); };
  const near = (x, y, sp, r) => sp.some((pg) => pg.some((a, i) => seg(x, y, a, pg[(i + 1) % pg.length]) <= r));
  const attr = (s, k) => { const m = s.match(new RegExp(`(?:^|\\s)${k}="([^"]*)"`)); return m ? m[1] : null; };
  const clipOf = (s) => { const c = attr(s, "clip-path"); return c ? c.match(/#([^)]+)\)/)[1] : null; };
  const clips = {}, els = [], stack = [];
  for (const m of svg.matchAll(/<(\/?)([a-zA-Z]+)([^>]*?)(\/?)>/g)) {
    const [, close, tag, rest, self] = m;
    if (close) { stack.pop(); continue; }
    const open = stack.find((s) => s.tag === "clipPath");
    if (open && tag === "path") (clips[attr(open.rest, "id")] = clips[attr(open.rest, "id")] || []).push(...subs(attr(rest, "d")));
    else if (!open && tag === "path" && attr(rest, "fill") === "none" && attr(rest, "data-cell")) {
      els.push({ cls: attr(rest, "class"), cell: attr(rest, "data-cell"), sp: subs(attr(rest, "d")), half: Number(attr(rest, "stroke-width")) / 2,
        chain: [clipOf(rest), ...stack.map((s) => clipOf(s.rest))].filter(Boolean) });
    }
    if (!self) stack.push({ tag, rest });
  }
  const cells = Object.fromEntries(base.world.cells.map((c) => [c.id, c])), regs = Object.fromEntries(base.world.regions.map((r) => [r.id, pts(r.d)]));
  return want.map(([id, classes]) => {
    const cell = pts(cells[id].d), reg = regs[cells[id].region], mine = els.filter((e) => e.cell === id && classes.includes(e.cls));
    if (!mine.length) return { id, classes, n: 0, cover: 0, region: null };
    const dep = Math.min(...mine.map((e) => e.half)) / 2;
    let total = 0, covered = 0, onRegion = 0;
    const walk = (pg, other, isRegion) => {
      for (let i = 0; i < pg.length; i++) {
        const a = pg[i], b = pg[(i + 1) % pg.length], L = Math.hypot(b[0] - a[0], b[1] - a[1]);
        if (!L) continue;
        const n = Math.max(1, Math.round(L)), nx = -(b[1] - a[1]) / L, ny = (b[0] - a[0]) / L;
        for (let s = 0; s < n; s++) {
          const t = (s + 0.5) / n, x = a[0] + (b[0] - a[0]) * t, y = a[1] + (b[1] - a[1]) * t;
          if (!inside(x, y, other)) continue;
          const q = [[x + nx * dep, y + ny * dep], [x - nx * dep, y - ny * dep]].find(([qx, qy]) => inside(qx, qy, pg));
          if (!q || !inside(q[0], q[1], other)) continue;  // 塊的邊與區界交會的那一角
          total += L / n;
          if (isRegion) onRegion += L / n;
          if (mine.some((e) => near(q[0], q[1], e.sp, e.half) && e.chain.every((c) => clips[c] && clips[c].some((pg) => inside(q[0], q[1], pg))))) covered += L / n;
        }
      }
    };
    walk(cell, reg, false);
    walk(reg, cell, true);
    return { id, classes, n: mine.length, cover: covered / total, region: onRegion / total };
  });
}
"""
FRAME_KINDS = {"rim": ["ld-rim", "w-cool"], "sortie": ["ld-sortie"], "letter": ["w-letter"], "here": ["ld-here"]}


def _cover_state(game):
    """量框的局面：開季（season21，官軍站潁川郡）再加正在翻的中立地（汝南荒野，紅框）、剛易手（荒丘，虛內框）、戰書（潁川書院）。"""
    st = game.map_state()
    st["places"]["runan_wilds"].update(control=None, tug={"guan": 55})
    st["places"]["hilltop_wilds"].update(control="huang", cool=40)
    st["places"]["yingchuan_academy"]["siege"] = "letter"
    return st


def _covers(game, st, want, k=1):
    """want：[(地點, 哪一種框), …] → 每一項 {id, classes, n（幾條）, cover（框涵蓋看得到的外框幾成）, region（外框有幾成落在區界上）}。"""
    pairs = json.dumps([[x, FRAME_KINDS[kind]] for x, kind in want])
    return run(game, COVER_JS + f"return landCover(H.S.mapBase, H.groundSvg(H.S.mapBase, H.S.mapState, {k}, H.S.mapState.now_week), {pairs});", st=st)


@pytest.mark.slow  # 單一條超過一秒（36 塊 × 每一單位取一點）
def test_fb9070_every_frame_runs_round_the_whole_block_you_can_see():
    """FB-9070：每一塊的框涵蓋看得到的外框（塊 ∩ 區的邊）九成五以上——每一塊的內框（36 塊；含正在翻的中立紅框、冷卻虛內框）、你那一塊的
    紅框（潁川郡）、每一處可出陣的橘框（開季五塊中立寶地：南陽官道、拒馬河畔……）、戰書框；伸出區界最多的下曲陽外框有一半以上落在區界上，
    修之前它的內框只描到三成。線寬照倍率（k）換，涵蓋率不跟著變：k＝1 與 k＝0.5（倍率 2）各量一次。"""
    game = _game(profile="season21")
    base = game.map_base()
    st = _cover_state(game)
    blocks = sorted(set(st["places"]) - _patches(base))
    sortie = [x for x in blocks if st["places"][x]["sortie"]]
    assert {"nanyang_road", "juma_river", "yu_river", "baima_ford", "nanyang_wilds"} <= set(sortie)
    assert all(st["places"][x]["control"] is None and st["places"][x]["rich"] for x in ("nanyang_road", "juma_river"))  # 中立寶地
    want = [(x, "rim") for x in blocks] + [(st["here"], "here"), ("yingchuan_academy", "letter")] + [(x, "sortie") for x in sortie]
    assert len(blocks) == 36 and st["here"] == "yingchuan"
    for k in (1, 0.5):
        got = _covers(game, st, want, k)
        assert all(g["n"] >= 1 for g in got), [g for g in got if not g["n"]]
        thin = [(g["id"], g["classes"][0], round(g["cover"], 3)) for g in got if g["cover"] < 0.95]
        assert not thin, (k, thin)
        xq = next(g for g in got if g["id"] == "xiaquyang" and g["classes"] == FRAME_KINDS["rim"])
        assert xq["region"] > 0.5, xq  # 這一條咬得到：下曲陽看得到的外框一半以上在區界上


# FB-9071：地的 key 以前是「抓疊層的時間」（S.mapStateAt），輪詢每重抓一次（在路上每 10 秒、平常每 30 秒）#mk 就整張重寫一次。現在 key 是地
# 真的會畫的那幾樣（groundLook）＋級距：疊層重抓了、地上畫的沒變就不重寫；該換的每一樣都換。每一種改法都比 groundSvg 吐出來的變了沒有：
# 「重寫了」要等於「畫出來的變了」——漏了一欄就會該換不換，多看一欄就會白寫。
def _ground_writes(game, st, cases):
    """cases：[(名字, 先改什麼, 再改什麼, 看哪一週〔None＝現在〕)]，改法是 [(路徑, 值)]，值 "__del__" 是刪掉那一欄。每一種：疊層照「先改」
    畫一次地、換成「再改」的疊層（像輪詢重抓了一次：loadMap 換掉 S.mapState、S.mapStateAt 記成此刻）再叫一次 groundShow，
    回 {名字: [重寫了幾次, groundSvg 吐出來的變了沒有]}。"""
    return run(game, """
const writes = [], mk = {};
Object.defineProperty(mk, 'innerHTML', { set: (v) => { writes.push(v); }, get: () => writes[writes.length - 1] || '' });
const doc = T.ctx.document, byId = doc.getElementById;
doc.getElementById = (id) => (id === 'mk' ? mk : byId(id));
const orig = JSON.stringify(H.S.mapState), cam = { z: 1.2, x: 0, y: 0 };
const edit = (st, changes) => { for (const [path, v] of changes) { let o = st; for (const p of path.slice(0, -1)) o = o[p]; if (v === '__del__') delete o[path[path.length - 1]]; else o[path[path.length - 1]] = JSON.parse(JSON.stringify(v)); } return st; };
const out = {};
for (const [name, before, after, week] of CASES) {
  H.S.mapWeek = week;
  const a = edit(JSON.parse(orig), before), b = edit(edit(JSON.parse(orig), before), after), wk = (st) => week || st.now_week;
  H.S.mapState = a; H.S.mapStateAt += 1; H.groundShow(cam);
  const n = writes.length;
  H.S.mapState = b; H.S.mapStateAt += 1; H.groundShow(cam);
  out[name] = [writes.length - n, H.groundSvg(H.S.mapBase, a, 1, wk(a)) !== H.groundSvg(H.S.mapBase, b, 1, wk(b))];
}
return out;""".replace("CASES", json.dumps(cases, ensure_ascii=False)), st=st)


@pytest.mark.slow  # 單一條超過一秒（三十幾種改法）
def test_fb9071_the_land_is_rewritten_when_what_it_draws_changes_and_only_then():
    """地讀的每一欄（主人、正在翻的那一方、冷卻、戰書、可出陣、必敗〔suggest 的 lose、不在 suggest 裡的勝算字、護糧車〕、你在哪、在不在路上、
    哪些地點開著、現在第幾週〔看的是某一週時〕、以前那一週的主人）改了都重寫一次；地不讀的（分鐘、危險度、寶、路、激戰、人物、懸賞、
    翻到幾成、冷卻還剩幾分鐘、在路上還剩幾分鐘與紅點的位置、必敗以外的勝算字、本週軍令、體力……）改了不重寫。"""
    game = _game(profile="season21")
    st = _cover_state(game)
    P = lambda *path: ["places", *path]  # noqa: E731
    road = [(["journey"], {"to": "changshe", "x": 400, "y": 1000, "minutes": 9})]
    past = [(["now_week"], 2), (["weeks"], [{"week": 1, "control": {x: q["control"] for x, q in st["places"].items()}}])]
    used = [
        ("control", [], [(P("changshe", "control"), "huang")], None),
        ("control to nobody", [], [(P("changshe", "control"), None)], None),
        ("tug starts", [], [(P("changshe", "tug"), {"huang": 10})], None),
        ("tug ends", [], [(P("runan_wilds", "tug"), None)], None),
        ("tug side", [(P("yu_river", "tug"), {"guan": 30})], [(P("yu_river", "tug"), {"huang": 30})], None),
        ("cool starts", [], [(P("changshe", "cool"), 50)], None),
        ("cool ends", [], [(P("hilltop_wilds", "cool"), None)], None),
        ("letter", [], [(P("changshe", "siege"), "letter")], None),
        ("letter to fight", [], [(P("yingchuan_academy", "siege"), "fight")], None),
        ("sortie", [], [(P("changshe", "sortie"), "attack")], None),
        ("sortie ends", [], [(P("nanyang_road", "sortie"), None)], None),
        ("lose in suggest", [(P("hilltop_wilds", "odds"), {"word": "穩勝", "tone": "safe"})], [(["suggest"], [])], None),
        ("odds word of a sortie", [], [(P("nanyang_wilds", "odds"), {"word": "穩勝", "tone": "safe"})], None),
        ("convoy", [], [(P("nanyang_wilds", "convoy"), {"side": "huang"})], None),
        ("here", [], [(["here"], "changshe")], None),
        ("journey", [], road, None),
        ("place closed", [], [(P("changshe"), "__del__")], None),
        ("now week while looking at one", [], [(["now_week"], 2)], 1),
        ("past week control", past, [(["weeks", 0, "control", "changshe"], "huang")], 1),
    ]
    unused = [
        ("refetched, nothing changed", [], [], None),
        ("refetched on the road, nothing changed", road, [], None),
        ("minutes", [], [(P("changshe", "minutes"), 99)], None),
        ("danger", [], [(P("changshe", "danger"), 3)], None),
        ("rich", [], [(P("changshe", "rich"), True)], None),
        ("path", [], [(P("changshe", "path"), ["yingchuan", "changshe"])], None),
        ("melee", [], [(P("changshe", "melee"), True)], None),
        ("people", [], [(P("changshe", "people"), ["某人"])], None),
        ("bounty", [], [(P("changshe", "bounty"), 5)], None),
        ("tug progress", [], [(P("runan_wilds", "tug"), {"guan": 70})], None),
        ("cool minutes", [], [(P("hilltop_wilds", "cool"), 39)], None),
        ("odds word not lose", [(P("nanyang_wilds", "odds"), {"word": "穩勝", "tone": "safe"})], [(P("nanyang_wilds", "odds"), {"word": "有把握", "tone": "safe"})], None),
        ("odds of a place you cannot sortie", [], [(P("changshe", "odds"), {"word": "必敗", "tone": "risk"})], None),
        ("siege fight", [], [(P("changshe", "siege"), "fight")], None),
        ("on the road", road, [(["journey", "minutes"], 5), (["journey", "x"], 420), (["journey", "y"], 990)], None),
        ("suggest minutes", [], [(["suggest", 0, "minutes"], 30), (["suggest", 0, "score"], -30)], None),
        ("week order", [], [(["week"], {"id": "changshe", "why": "軍令・守城", "minutes": 6})], None),
        ("stamina", [], [(["stamina"], 1)], None),
        ("past weeks while looking at now", [], [(["weeks"], [{"week": 1, "control": {}}])], None),
    ]
    got = _ground_writes(game, st, [list(c) for c in used + unused])
    assert {name: got[name] for name, *_ in used} == {name: [1, True] for name, *_ in used}
    assert {name: got[name] for name, *_ in unused} == {name: [0, False] for name, *_ in unused}
    # 每一處、每一欄、疊層每一個鍵：拿掉（設成 null）之後，重寫了 ⇔ 畫出來的變了
    keys = sorted({k for q in st["places"].values() for k in q})
    generic = [[f"places.{x}.{k}", [], [[P(x, k), None]], None] for k in keys for x in [x for x in sorted(st["places"]) if st["places"][x].get(k)][:3]]
    generic +=[[f"top.{k}", [], [[[k], None]], None] for k in sorted(st) if k not in {"places", "now_week", "key"} and st[k]]
    got = _ground_writes(game, st, generic)
    assert {n: (w == 1) == ch and w <= 1 for n, (w, ch) in got.items()} == {n: True for n in got}, {n: v for n, v in got.items() if (v[0] == 1) != v[1]}
    assert sum(ch for _, ch in got.values()) >= 10  # 拿掉之後真的會變的不少（主人、可出陣、你在哪……）


def _land_spot(base, loc, dxs, dys):
    """那一處的地上（地塊裡、區界裡、不在任何圓上）離小圖 (dx, dy) 的第一個點（地圖座標）。"""
    cell = next(c for c in base["world"]["cells"] if c["id"] == loc)
    region = next(r for r in base["world"]["regions"] if r["id"] == cell["region"])
    p = next(b for b in base["places"] if b["id"] == loc)
    patches = [b for b in base["places"] if b["id"] in _patches(base)]
    r = base["view"]["patch_radius"]
    return p, next((p["x"] + dx, p["y"] + dy) for dx in dxs for dy in dys
                   if _inside(p["x"] + dx, p["y"] + dy, _poly(cell["d"])) and _inside(p["x"] + dx, p["y"] + dy, _poly(region["d"]))
                   and all((p["x"] + dx - q["x"]) ** 2 + (p["y"] + dy - q["y"]) ** 2 > r * r for q in patches))


@pytest.mark.slow  # 單一條超過一秒（要等 MV_TAP2 過去）
def test_w1_a_double_tap_on_the_land_only_zooms():
    """雙擊（Joy 的：以手指為中心放大兩倍）落在地上只放大：不開卡、不換抽屜、不畫路線，也不先為了露出小圖把鏡頭挪走（mvNudge）——
    放大完手指底下還是同一點。卡開著時雙擊別處的地也一樣，開著的那一張不換。點一下的地等 MV_TAP2 過了、確定沒有第二下才開卡。
    （W1 審查 2026-10-30：地鋪滿之後，雙擊的第一下就開了那一處的卡、畫了路線；小圖在畫面邊上時還先飛一下，放大的中心偏了約 25px。）"""
    game = _game(profile="season21")
    p, spot = _land_spot(game.map_base(), "changshe", range(30, 46, 3), (0, -6, 6, -12, 12))
    out = run(game, DRAWER_DOM + GESTURE_DOM + f"""
const tapAt = (id, mx, my) => {{ const c = H.S.mapCam, x = c.x + mx * c.z, y = c.y + my * c.z;
  H.mvDown(pt('pointerdown', id, x, y)); H.mvUp(pt('pointerup', id, x, y)); return [x, y]; }};
const settle = () => {{ let i = 0; extra = 0; while (q.size && i++ < 300) frame(); }};
// 兩下之間：跑八幀（約 130ms 的動畫），也真的讓出去 60ms（計時器在這時候到的話就會開卡）——還在 MV_TAP2 之內
const gap = async () => {{ extra = 0; for (let i = 0; i < 8; i++) frame(); await new Promise((r) => setTimeout(r, 60)); }};
const wait = () => new Promise((r) => setTimeout(r, 360));
const look = () => [H.S.mapMode, H.S.mapSel, H.S.mapDrawer, body.innerHTML.includes('m-cards'), els.mkr.innerHTML];
const under = ([x, y]) => [(x - H.S.mapCam.x) / H.S.mapCam.z, (y - H.S.mapCam.y) / H.S.mapCam.z];
return (async () => {{
  H.camSet({{ z: 1.2, x: 10 - {p['x']} * 1.2, y: 400 - {p['y']} * 1.2 }}); H.mapBack(); settle();
  const pinX = H.S.mapCam.x + {p['x']} * H.S.mapCam.z, z0 = H.S.mapCam.z, before = look();
  const finger = tapAt(1, {spot[0]}, {spot[1]}); await gap(); tapAt(2, {spot[0]}, {spot[1]}); settle(); await wait(); settle();
  const zoomed = {{ look: look(), z: H.S.mapCam.z, under: under(finger) }};
  Object.assign(H.S, {{ mapMode: 'place', mapSel: 'yingchuan' }}); H.redrawDrawer();
  const open = look();
  tapAt(3, {spot[0]}, {spot[1]}); await gap(); tapAt(4, {spot[0]}, {spot[1]}); settle(); await wait(); settle();
  const kept = look();
  H.mapBack(); settle();
  tapAt(5, {spot[0]}, {spot[1]});
  const pending = look();
  await wait(); settle();
  return {{ pinX, z0, before, zoomed, open, kept, pending, single: look() }};
}})();""")
    # 從 1.2 放大兩倍到 2.4（W2：最大是 Z0 × zoom_max，375 寬的框是 1.5 × 1.6＝2.4；以前從 1.6 放到 3.2）
    assert out["pinX"] < 30 and out["z0"] == 1.2  # 長社的小圖在畫面左緣（以前第一下會 mvNudge 飛一下）
    assert out["before"] == ["overview", None, "peek", True, ""]
    assert out["zoomed"]["look"] == out["before"] and out["zoomed"]["z"] == pytest.approx(2.4)
    assert out["zoomed"]["under"] == pytest.approx(list(spot), abs=0.5)
    assert out["kept"] == out["open"] and out["open"][:2] == ["place", "yingchuan"]
    assert out["pending"] == out["before"]  # 點一下：還在等第二下
    assert out["single"][:2] == ["place", "changshe"] and not out["single"][3] and out["single"][4]


@pytest.mark.slow  # 單一條超過一秒（每一下之間要隔開）
def test_w1_tapping_the_same_place_again_by_its_icon_or_name_closes_the_card_too():
    """再點同一處收回（設計 2.3「點小圖、名字、或那一塊地……點空地、✕、再點同一處：收卡回底條」）：點小圖、名字、遠看的小點
    （data-act="map-place"）跟點那一塊地同一條——第一下開卡、過一會兒再點同一處收回；開著時點別處換那一處的卡。雙擊小圖（兩下在 MV_TAP2
    之內）照 Joy 的只開卡、第二下不收回。附近那一排的卡（同一個 data-act）照舊開卡。（W1 審查 2026-10-30：以前點地會收、點小圖名字只重開卡。）"""
    out = run(_game(profile="season21"), DRAWER_DOM + """
const target = (id) => ({ dataset: { act: 'map-place', id }, classList: { contains: () => false, add() {}, remove() {} } });
const click = (id) => T.docListeners.click[0]({ target: { closest: () => target(id) } });
const wait = (ms = 360) => new Promise((r) => setTimeout(r, ms));
const look = () => [H.S.mapMode, H.S.mapSel, body.innerHTML.includes('m-cards')];
return (async () => {
  H.mapBack();
  await click('changshe'); const open = look(); await wait();
  await click('changshe'); const shut = look(); await wait();
  await click('changshe'); await wait(); await click('yingshui'); const other = look(); await wait();
  await click('yingshui'); const shut2 = look(); await wait();
  await click('changshe'); await wait(60); await click('changshe'); const dbl = look(); await wait();
  H.mapBack(); await click('changshe'); const card = look();
  return { open, shut, other, shut2, dbl, card };
})();""")
    assert out["open"] == ["place", "changshe", False] and out["shut"] == ["overview", None, True]
    assert out["other"] == ["place", "yingshui", False] and out["shut2"] == ["overview", None, True]
    assert out["dbl"] == ["place", "changshe", False]  # 雙擊小圖：第二下不收回
    assert out["card"] == ["place", "changshe", False]


# ── 看哪裡 ──
def test_the_camera_is_clamped_between_the_whole_world_and_three_times():
    """倍率在「整張天下放得下」到 Z0 × zoom_max 之間（W2；以前是 3.2 倍：390 寬的框 Z0＝390／250，乘 1.6）；圖比畫面大時拖到最遠，
    圖的邊貼著畫面的邊（不露出圖外，Joy 10/30「滑到邊邊會破圖」）。"""
    out = run(_game(), f"""const g = {{ vw: 390, vh: 700 }};
const lo = H.zMin(g), small = H.camClamp({{ z: 0.01, x: 0, y: 0 }}, g), big = H.camClamp({{ z: 99, x: 0, y: 0 }}, g);
const far = H.camClamp({{ z: 1, x: 99999, y: 99999 }}, g), fit = H.camFit(g);
const back = H.camClamp({{ z: 1, x: -99999, y: -99999 }}, g);
return {{ lo, small: small.z, big: big.z, farLeft: far.x, farRight: back.x + H.S.mapBase.w * back.z, fitZ: fit.z }};""")
    assert out["small"] == out["lo"] == out["fitZ"] and out["big"] == pytest.approx(390 / 250 * 1.6) and 0 < out["lo"] < 1
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
    """量不到（還沒排版）時：沒點地點的三格（輿圖表現第二版 W2，設計 2.1 底條）——一行（底條）68、一排卡（附近那一排，Joy 原本的半開）196、
    全開九成四；一處的卡至少 200（三分之一）；拉高六成、全開九成四；右下兩顆圓鈕跟著抽屜上下。"""
    out = run(_game(), DRAWER_DOM + """
H.setMapDrawer('peek');
const line = [drawer.style.height, fab.style.bottom];
H.setMapDrawer('row');
const near = [drawer.style.height, fab.style.bottom];
H.S.mapMode = 'place'; H.S.mapSel = 'changshe'; H.setMapDrawer('peek');
const place = drawer.style.height;
H.setMapDrawer('half'); const half = drawer.style.height;
H.setMapDrawer('full'); const full = drawer.style.height;
return { line, near, place, half, full, props };
""")
    assert out["line"] == ["68px", "80px"] and out["near"] == ["196px", "208px"]
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


# ── 輿圖表現第二版 W2：取景、密度、名字、HUD、底條（docs/superpowers/specs/2026-10-30-輿圖表現-design.md 2.1、2.2、2.3、第四章、第六章 W2、
# 第七章；企劃者 2026-10-30「照丙定」）──
# 打開倍率 Z0 ＝ min(地圖框寬, open_width_max) ／ open_units、中心＝你兩票＋腳下每一站一票；最大 Z0 × zoom_max；三段門檻是 Z0 的幾倍；點一處 < Z0 才飛；
# 近、中景名字只寫跟我有關的；上面是區名 chip＋🔍、右上小地圖、框外一步的箭頭牌；抽屜沒點地點時三格，最低那一格是底條。資料照 season21 開季
# （官軍站潁川郡）。地圖框照實機量的（375×812、360×780、320×568 的地圖框高；W2 審查 2026-10-31 修正輪重量：667、635、402，底條那一行 68）。
FRAMES = {375: 667, 360: 635, 320: 402}


def _w2(profile="season21", **kw):
    return _game(profile=profile, **kw)


def _hops(base, start):
    adj = {}
    for a, b in base["edges"]:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    h, q = {start: 0}, [start]
    for u in q:
        for v in adj.get(u, []):
            if v not in h:
                h[v] = h[u] + 1
                q.append(v)
    return h


def _view(game):
    v = game.map_base()["view"]
    return v, (lambda vw: min(vw, v["open_width_max"]) / v["open_units"])


def test_w2_the_view_numbers_replace_joys_constants():
    """數字改讀底圖的 view（設計第四章的取代表）：Joy 寫死的 MV_OPEN_Z、MV_PICK_Z、MV_HOME_Z、MV_PREVIEW_Z、MV_ZMAX、MV_LV1、MV_LV2 一個都不留。"""
    code = re.sub(r"//[^\n]*", "", APP.read_text(encoding="utf-8"))  # 註解裡寫著取代了誰，不算
    for gone in ("MV_OPEN_Z", "MV_PICK_Z", "MV_HOME_Z", "MV_PREVIEW_Z", "MV_ZMAX", "MV_LV1", "MV_LV2"):
        assert not re.search(rf"\b{gone}\b", code), gone
    for key in ("open_units", "open_width_max", "zoom_max", "near_from", "mid_from", "named_hops_near", "named_hops_mid", "switch_zoom"):
        assert f"v.{key}" in code or f"mvView().{key}" in code, key  # 九個數字都有人讀（patch_radius 是 W1 的地在讀）


@pytest.mark.parametrize("vw", [375, 1100])
def test_w2_opening_zoom_is_the_frame_width_over_open_units(vw):
    """打開倍率＝min(框寬, open_width_max)／open_units：375 寬是 1.5；1100 寬（桌機）跟 480 一樣是 1.92，只多看一圈。沒帶目標的打開（camFirst）就是它。"""
    game = _w2()
    v, z0 = _view(game)
    out = run(game, f"const g = {{ vw: {vw}, vh: 700 }}; return [H.camFirst(g).z, H.camOpen(g).z, H.mvZ0(g)];")
    assert out[0] == out[1] == out[2] == pytest.approx(z0(vw))
    assert z0(1100) == z0(480) == pytest.approx(1.92) and z0(375) == pytest.approx(1.5)


def test_w2_opening_centre_is_you_twice_and_each_neighbour_once():
    """打開的中心＝你（算兩票）＋腳下每一站（各一票）的平均（設計 2.2）：露出來那一塊（區名那一排底下、底條上面）的正中對著那一點。"""
    game = _w2()
    base, st = game.map_base(), game.map_state()
    pos = {p["id"]: (p["x"], p["y"]) for p in base["places"]}
    near = [x for x, h in _hops(base, st["here"]).items() if h == 1 and x in st["places"]]
    assert len(near) == 5
    pts = [pos[st["here"]]] * 2 + [pos[x] for x in near]
    want = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    out = run(game, "const g = { vw: 375, vh: 668 }, c = H.camOpen(g), r = H.mapRoom(g); return [(g.vw / 2 - c.x) / c.z, ((r.top + r.bottom) / 2 - c.y) / c.z, r.top, r.bottom];")
    assert out[:2] == pytest.approx(list(want), abs=0.01)
    assert out[2:] == [56, 668 - 68]  # 上面讓開區名那一排、底下是底條那一行


@pytest.mark.slow  # 單一條超過一秒（要一幀一幀飛）
def test_w2_home_goes_back_to_the_opening_view_and_fit_shows_the_whole_world():
    """◎（mapHome）＝回到打開的取景（不是「以你為中心、至少 1.2 倍」）；全（mapFit）＝整張天下放進露出來的那一塊（倍率＝zMin）。"""
    out = run(_w2(), DRAWER_DOM + GESTURE_DOM + """
const settle = () => { let i = 0; extra = 0; while (q.size && i++ < 400) frame(); };
const g = { vw: 375, vh: 700 };
H.camSet({ z: 0.7, x: -100, y: -300 }); H.drawMarks(); settle();
H.mapHome(); settle();
const home = H.S.mapCam, open = H.camOpen(g);
H.mapFit(); settle();
const fit = H.S.mapCam, b = H.S.mapBase;
return { home, open, fit, zmin: H.zMin(g), w: b.w * fit.z, h: b.h * fit.z, room: H.mapRoom(g) };""")
    assert out["home"] == pytest.approx(out["open"], abs=0.01)
    assert out["fit"]["z"] == pytest.approx(out["zmin"]) and out["w"] <= 375 and out["h"] <= out["room"]["bottom"] - out["room"]["top"]


@pytest.mark.parametrize("vw", [375, 1100])
def test_w2_zoom_tops_out_at_z0_times_zoom_max(vw):
    """最大＝Z0 × zoom_max（取代 Joy 的 3.2）；最小照舊是整張天下放得下。"""
    game = _w2()
    v, z0 = _view(game)
    out = run(game, f"const g = {{ vw: {vw}, vh: 800 }}; return [H.camClamp({{ z: 99, x: 0, y: 0 }}, g).z, H.camClamp({{ z: 0.001, x: 0, y: 0 }}, g).z, H.zMin(g)];")
    assert out[0] == pytest.approx(z0(vw) * v["zoom_max"]) and out[1] == out[2]


def test_w2_the_three_levels_are_fractions_of_z0():
    """三段門檻（設計 2.2）：近 ≥ Z0 × near_from、中 ≥ Z0 × mid_from、再小是遠——375 寬（Z0＝1.5）是 1.2 與 0.675。"""
    game = _w2()
    v, z0 = _view(game)
    zs = [0.6, 0.674, 0.676, 1.19, 1.21, 2.4]
    out = run(game, "const g = { vw: 375, vh: 700 }; return " + json.dumps(zs) + ".map((z) => H.mvLevel(z, g));")
    near, mid = z0(375) * v["near_from"], z0(375) * v["mid_from"]
    assert out == [2 if z >= near else 1 if z >= mid else 0 for z in zs] == [0, 0, 1, 1, 2, 2]


@pytest.mark.slow  # 單一條超過一秒（要一幀一幀飛）
def test_w2_picking_flies_to_z0_from_the_middle_and_stays_put_up_close():
    """點一處（設計 2.2，三種地方一條規則）：此刻倍率 < Z0（中景）飛到那一處、倍率到 Z0；≥ Z0（近景）倍率不動、露著就不挪。
    圖上點的（mapLand）、🔍 的結果與出陣建議（map-pick，以前 fly＝true 一律飛到至少 1.4）都一樣。"""
    game = _w2()
    out = run(game, DRAWER_DOM + GESTURE_DOM + """
const settle = () => { let i = 0; extra = 0; while (q.size && i++ < 400) frame(); };
const g = { vw: 375, vh: 700 }, z0 = H.mvZ0(g), at = (id) => H.S.mapBase.places.find((p) => p.id === id);
const centre = () => { const c = H.S.mapCam, r = H.mapRoom(g); return [(g.vw / 2 - c.x) / c.z, ((r.top + r.bottom) / 2 - c.y) / c.z]; };
const res = {};
for (const [name, pick] of [["land", (id) => H.mapLand(id)], ["pick", (id) => H.mapPick(id, true)]]) {
  H.mapBack(); settle();
  const y = at('yingchuan');
  H.camSet(H.camAt(g, y.x, y.y, z0 * 0.6)); H.drawMarks(); settle();
  pick('changshe'); settle();
  const mid = { z: H.S.mapCam.z, c: centre() };
  H.mapBack(); settle();
  const before = { ...H.camAt(g, y.x, y.y, z0 * 1.2) };
  H.camSet(before); H.drawMarks(); settle();
  pick('songshan_foot'); settle(); // 嵩山腳：近景露在卡上面，不必挪
  res[name] = { z0, mid, near: H.S.mapCam, before, sel: H.S.mapSel };
}
const c = at('changshe');
return { res, changshe: [c.x, c.y] };""")
    for name, r in out["res"].items():
        assert r["mid"]["z"] == pytest.approx(r["z0"]) and r["mid"]["c"] == pytest.approx(out["changshe"], abs=0.5), name
        assert r["near"] == pytest.approx(r["before"]) and r["sel"] == "songshan_foot", name


def _labs(html):
    """近、中景的名字：[(地點, 名字, 幾分, 字條, class, left, top, 寫在 style 上的寬)]。"""
    out = []
    for m in re.finditer(r'<button type="button" class="mv-lab([^"]*)" style="left:([-\d.]+)px;top:([-\d.]+)px;width:([-\d.]+)px" data-act="map-place" data-id="([^"]+)">(.*?)</button>', html):
        cls, l, t, w, pid, inner = m.groups()
        name = re.search(r'<span class="nm">([^<]+)', inner).group(1)
        mins = re.search(r'<small class="mv-min">([^<]+)</small>', inner)
        leg = re.search(r'<span class="mv-wk leg">([^<]+)</span>', inner)
        out.append((pid, htmllib.unescape(name), mins.group(1) if mins else "", leg.group(1) if leg else "", cls, float(l), float(t), float(w)))
    return out


def _text_w(text, px):
    """Joy 的 textW 照抄（中日韓一個字寬、空白三成、其餘六成）：測試自己估，不借網頁的。"""
    return sum(0.3 if ch == " " else 0.6 if ord(ch) < 0x2E80 else 1 for ch in text) * px


def _lab_box(lab):
    """名字的框：照估的字寬加 15% 餘裕（設計第七章），字級照 class（大地方 16、縮小 11、其餘 14），高 1.2 行加 2。"""
    pid, name, mins, leg, cls, l, t, w = lab
    fs = 11 if "tiny" in cls else 16 if "big" in cls else 14
    W = 1.15 * (_text_w(name, fs) + (3 + _text_w(mins, 11) if mins else 0)) + (46 if leg else 0)
    return (l, t, l + W, t + fs * 1.2 + 2), W


def _ratios():
    """畫的小圖的高／寬（照 web/img/map 那幾張 webp 的檔頭讀，不借網頁的常數）。"""
    import struct
    from pathlib import Path

    out = {}
    for f in (Path(server.WEB) / "img" / "map").glob("*.webp"):
        b = f.read_bytes()[:30]
        if b[12:16] == b"VP8X":
            w, h = 1 + int.from_bytes(b[24:27], "little"), 1 + int.from_bytes(b[27:30], "little")
        elif b[12:16] == b"VP8 ":
            w, h = (v & 0x3FFF for v in struct.unpack("<HH", b[26:30]))
        else:
            bits = int.from_bytes(b[21:25], "little")
            w, h = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        out[f.stem] = h / w
    return out


RATIOS = _ratios()


def _icons(html):
    """畫出來的小圖與它角上的徽、圈各佔的框（照標記與 style.css 的大小算）：{地點: [框…]}（徽、圈不知道是哪一處的，放在 "" 底下）。"""
    out = {"": []}
    for m in re.finditer(r'<button type="button" class="mv-pin (paint|ink)[^"]*" style="left:([-\d.]+)px;top:([-\d.]+)px(?:;width:(\d+)px)?" data-act="map-place" data-id="([^"]+)"[^>]*>(?:<img src="/static/img/map/(\w+)\.webp")?', html):
        kind, x, y, w, pid, key = m.groups()
        x, y = float(x), float(y)
        if kind == "paint":
            w = float(w)
            h = w * RATIOS[key]
            out[pid] = [(x - w / 2, y - 0.62 * h, x + w / 2, y + 0.38 * h)]
        else:
            # 墨筆那一張 svg 是行內的，實機畫出來比錨點高 3～4px（開發第一輪在實機量到洛陽官道的箭頭牌壓到嵩山深處的小圖 2px）：上緣照 y − 19
            # （W2 審查 2026-10-31：以前照 y − 15，網頁的 pinBox 改回 y − 15 這裡也抓不到）
            out[pid] = [(x - 15, y - 19, x + 15, y + 15)]
    for x, y in re.findall(r'<i class="mv-dg[^"]*" style="left:([-\d.]+)px;top:([-\d.]+)px">', html):
        out[""].append((float(x) - 7.5, float(y) - 7.5, float(x) + 7.5, float(y) + 7.5))
    for x, y in re.findall(r'<i class="mv-bd [^"]*" style="left:([-\d.]+)px;top:([-\d.]+)px">', html):
        out[""].append((float(x) - 8, float(y) - 8, float(x) + 8, float(y) + 8))
    for x, y in re.findall(r'<svg class="mv-flag[^"]*" width="16" height="24" viewBox="0 0 16 24" style="left:([-\d.]+)px;top:([-\d.]+)px"', html):
        out[""].append((float(x) - 3, float(y) - 24, float(x) + 13, float(y)))
    for x, y, r in re.findall(r'<i class="mv-ring" style="left:([-\d.]+)px;top:([-\d.]+)px;--r:(\d+)px">', html):
        out[""].append((float(x) - int(r), float(y) - int(r), float(x) + int(r), float(y) + int(r)))
    for x, y in re.findall(r'<i class="mv-fight" style="left:([-\d.]+)px;top:([-\d.]+)px">', html):
        out[""].append((float(x) - 20, float(y) - 20, float(x) + 20, float(y) + 20))
    return out


def _pills(html):
    """箭頭牌點得到的那一塊：畫出來 24 高，點擊範圍上下各撐開 8px（style.css 的 .mv-pill::before，40 高；W2 審查 2026-10-31）。"""
    return [(pid, (float(l), float(t) - 8, float(l) + float(w), float(t) + 24 + 8)) for l, t, w, pid in
            re.findall(r'<button type="button" class="mv-pill" style="left:([-\d.]+)px;top:([-\d.]+)px;width:([-\d.]+)px" data-act="map-place" data-id="([^"]+)"', html)]


def _hud(vw, bottom, lvl, area, mini):
    """浮著的那幾樣（照 style.css 的位置與大小）：區名 chip（左上 10，高 34，點擊範圍上下各撐開 4px＝42；寬＝左右內距 10、14px 的字、間隔 6 與 ▾，
    字照估的寬加 15%）、🔍（右上 12、46 見方）、小地圖（🔍 底下、右 12、上 62，連 1px 的框）、右下兩顆（46 見方、間隔 10，底下離抽屜 12）。"""
    out = [(10, 6, 10 + 20 + 1.15 * _text_w(area, 14) + 6 + 11, 48), (vw - 58, 8, vw - 12, 54), (vw - 58, bottom - 12 - 102, vw - 12, bottom - 12)]
    if lvl > 0:
        out.append((vw - 12 - mini[0] - 2, 62, vw - 12, 62 + mini[1] + 2))
    return out


def _cross(a, b):
    return a[0] < b[2] - 1e-6 and a[2] > b[0] + 1e-6 and a[1] < b[3] - 1e-6 and a[3] > b[1] + 1e-6


SWEEP_JS = """
const out = [];
for (const [vw, vh] of FRAMES) {
  const g = { vw, vh }, z0 = H.mvZ0(g);
  for (const [i, st] of STATES.entries()) {
    Object.assign(H.S, { mapState: st, mapMode: 'overview', mapSel: null, mapPreview: null, mapDrawer: 'peek', mapFilter: 'all', mapWeek: null, mapThen: null });
    const open = H.camOpen(g), r = H.mapRoom(g);
    const cx = (g.vw / 2 - open.x) / open.z, cy = ((r.top + r.bottom) / 2 - open.y) / open.z;
    for (const [level, c] of [['near', open], ['mid', H.camAt(g, cx, cy, z0 * 0.6)]]) {
      const lay = H.mvLayout(H.S.mapBase, st, c, g);
      out.push({ i, vw, vh, here: st.here, level, c, lvl: lay.lvl, area: lay.area, room: r, html: lay.html, pills: lay.pills.map((p) => p.html).join(''), mini: H.miniHtml(H.S.mapBase, st, c, g).match(/width:(\\d+)px;height:(\\d+)px/).slice(1).map(Number) });
    }
  }
}
return out;
"""


def _sweep_states(game, scene=False):
    """每一處各站一次的疊層（伺服器真的會給的：分鐘、可出陣、本週都照站的那一處算）。scene：每一站再塞本週軍令（兩步外的一處：小圖頂上插旗、
    名字一定要寫）、一處鄰居正在翻（右上 ⚔）、另一處兩步外激戰（⚔＋閃圈）——開季那一刻這三樣都沒有，旗與 ⚔ 從來沒跟名字比過、「本週一定有」
    也沒驗到（W2 審查 2026-10-31）。"""
    base = game.map_base()
    out = []
    for loc in [p["id"] for p in base["places"]]:
        game.state.player.location = loc
        st = game.map_state()
        if scene:
            hops = _hops(base, loc)
            ring = lambda n: sorted(x for x, h in hops.items() if h == n and x in st["places"])  # noqa: E731
            one, two = ring(1), ring(2)
            if two:
                st["week"] = {"id": two[0], "why": "軍令・守城", "minutes": st["places"][two[0]]["minutes"]}
            if one:
                q = st["places"][one[0]]
                q["tug"] = {("guan" if q["control"] == "huang" else "huang"): 40}
            if len(two) > 1:
                st["places"][two[-1]]["melee"] = True
        out.append(st)
    return out


# 名字讓步（縮到 11px，拉線的也是）的上限：小圖在畫面裡的名字裡最多幾成，照寬、密度各一條（W2 審查 2026-10-31：以前近中景、三種寬合在一起算、
# 又把拉線的重算一次〔拉線的名字本來就縮了〕，開發回報的 8.6% 把打開那一眼的代價稀釋掉）。修正輪量到的（開季那一刻＋本週、正在翻、激戰各 42 處）：
# 近景 375 8.3%（42／505）、360 9.3%（46／497）、320 17.6%（76／431）；中景 375 0.5%、360 0.9%、320 5.3%（拉線的 140 條都在縮了的裡面）。
# 上限照量到的再留三、四個百分點，擋住「大半都在讓步」的退步；320 寬的邊角是 W3 的事，到時候再收緊
YIELD_CAPS = {(375, "near"): 0.12, (360, "near"): 0.13, (320, "near"): 0.22, (375, "mid"): 0.04, (360, "mid"): 0.04, (320, "mid"): 0.08}


@pytest.mark.slow  # 單一條超過一秒（42 處 × 2 種局面 × 3 種寬 × 2 個密度）
def test_w2_names_never_overlap_icons_pills_or_the_hud_and_stay_on_the_screen():
    """名字不互壓、不壓小圖（連徽）、不壓箭頭牌與浮著的那幾樣、不出畫面（設計第六章 W2「測」、第七章「名字」）：375／360／320 三種寬 × 近（打開的取景）
    中（同一個中心、Z0 × 0.6）兩個密度 × 42 處各站一次 × 兩種局面（開季那一刻；再加本週、正在翻、激戰，_sweep_states）。框照估的字寬加 15% 餘裕
    （測試自己估）。畫面＝露出來那一塊（左右是地圖框、上面到框頂、
    底下到底條）：小圖在裡面的名字整個在裡面，小圖在外面的名字整個在外面（不會切一半）。同一輪也驗：
    名字都在「近：兩步內 ∪ 大地方 ∪ 本週 ∪ 寶 ∪ 翻 ∪ 可出陣；中：一步內 ∪ 大地方 ∪ 本週 ∪ 寶 ∪ 翻」（加你）裡，小圖在畫面裡的兩步內（中景一步內）與本週
    一定有；近景兩步內的接「N 分」；箭頭牌只在近景、數目＝腳下一步而小圖整個在畫面外的，牌在畫面裡、互不相交、不壓小圖與浮著的那幾樣。"""
    game = _w2()
    base = game.map_base()
    states = _sweep_states(game) + _sweep_states(game, scene=True)  # 開季那一刻、加上本週＋正在翻＋激戰（W2 審查 2026-10-31）
    pos = {p["id"]: p for p in base["places"]}
    out = run(game, SWEEP_JS.replace("FRAMES", json.dumps(sorted(FRAMES.items()))).replace("STATES", json.dumps(states, ensure_ascii=False)), timeout=600)
    assert len(out) == 3 * 2 * len(states) == 504
    assert sum('class="mv-flag' in c["html"] for c in out) > 200 and sum('class="mv-fight"' in c["html"] for c in out) > 100  # 旗與 ⚔ 真的進了掃描
    yields = {}  # (寬, 密度) → [縮字, 拉線, 小圖在畫面裡的名字數]
    for case in out:
        st = states[case["i"]]
        key = (case["vw"], case["here"], case["level"], "scene" if case["i"] >= len(states) // 2 else "open")
        tally = yields.setdefault((case["vw"], case["level"]), [0, 0, 0])
        vw, bottom, c = case["vw"], case["room"]["bottom"], case["c"]
        vis = (0, 0, vw, bottom)
        lvl = case["lvl"]
        assert lvl == (2 if case["level"] == "near" else 1), key
        hops = _hops(base, st["here"])
        reach = 2 if lvl == 2 else 1
        labs, icons, pills = _labs(case["html"]), _icons(case["html"]), _pills(case["pills"])
        hud = _hud(vw, bottom, lvl, case["area"], case["mini"])
        blocks = [b for bs in icons.values() for b in bs]
        anchor = {pid: (c["x"] + pos[pid]["x"] * c["z"], c["y"] + pos[pid]["y"] * c["z"]) for pid in pos}
        inside = lambda pid: 0 <= anchor[pid][0] <= vw and 0 <= anchor[pid][1] <= bottom  # noqa: E731
        boxes = []
        for lab in labs:
            box, W = _lab_box(lab)
            assert W <= lab[7] + 0.15, (key, lab)  # 網頁留的寬不比估的小
            if inside(lab[0]):
                assert box[0] >= -1e-6 and box[1] >= -1e-6 and box[2] <= vw + 1e-6 and box[3] <= bottom + 1e-6, (key, lab, box)
            else:
                assert not _cross(box, vis), (key, lab, box)
            for other in blocks:
                assert not _cross(box, other), (key, lab, other)
            for pid, p in pills:
                assert not _cross(box, p), (key, lab, pid)
            for h in hud:
                assert not _cross(box, h) or not inside(lab[0]), (key, lab, h)
            for o, ob in boxes:
                assert not _cross(box, ob), (key, lab, o)
            boxes.append((lab[0], box))
            if inside(lab[0]):
                tally[0] += "tiny" in lab[4]
                tally[2] += 1
        tally[1] += case["html"].count('class="mv-lead"')
        named = {lab[0] for lab in labs}
        q = st["places"]
        wk = st["week"]["id"] if st.get("week") and st["week"]["id"] in q else None
        allowed = {x for x in q if (hops.get(x, 99) <= reach or pos[x]["big"] or q[x].get("rich") or x == wk or x == st["here"]
                                    or any(int(v) > 0 for sd, v in (q[x].get("tug") or {}).items() if sd != q[x]["control"])
                                    or (lvl == 2 and q[x].get("sortie")))}
        assert named <= allowed, (key, named - allowed)
        must = {x for x in q if (hops.get(x, 99) <= reach or x == wk or x == st["here"]) and inside(x)}
        assert must <= named, (key, must - named)
        for lab in labs:
            h = hops.get(lab[0], 99)
            want = f'{q[lab[0]]["minutes"]} 分' if lvl == 2 and 0 < h <= 2 and q[lab[0]]["minutes"] is not None else ""
            assert lab[2] == want, (key, lab)
        # 箭頭牌
        far = set()
        if lvl == 2:
            for x, h in hops.items():
                if h == 1 and x in q:
                    icon = icons.get(x)  # 沒畫小圖的是在畫面附近（一個畫面的 0.8）更外面：小圖當然整個在畫面外
                    if not icon or not _cross(icon[0], vis):
                        far.add(x)
        assert sorted(p for p, _ in pills) == sorted(far), key
        for i, (pid, p) in enumerate(pills):
            assert p[0] >= 0 and p[1] >= 0 and p[2] <= vw and p[3] <= bottom, (key, pid, p)
            for _, o in pills[i + 1:]:
                assert not _cross(p, o), (key, pid)
            for h in hud:
                assert not _cross(p, h), (key, pid, h)
            for other in blocks:
                assert not _cross(p, other) or not _cross(other, vis), (key, pid, other)
    # 讓步（縮到 11px；往外找、拉線回小圖的也是 11px，算在裡面）是少數：每一種寬的近景（打開那一眼）與中景各算一條，上限見 YIELD_CAPS
    for (vw, level), cap in YIELD_CAPS.items():
        tiny, leads, total = yields[(vw, level)]
        assert total > 250 and leads <= tiny + 5 and tiny / total < cap, (vw, level, yields[(vw, level)], round(tiny / total, 3))


def test_w2_near_names_are_the_ones_about_you_with_minutes():
    """近景（打開的取景）：名字都在「兩步內 ∪ 大地方 ∪ 本週 ∪ 寶 ∪ 翻 ∪ 可出陣」裡，兩步內與本週一定有；兩步內的接「N 分」（你腳下那一處不接）；
    名字底下沒有那一行、沒有小印與悟字。中景：一步內、大地方、本週、寶、翻；不接幾分。篩選開著時合的照寫（三步外也寫），不合的不寫。"""
    game = _w2()
    st = game.map_state()
    st["week"] = {"id": "deep_mountain", "why": "軍令・守城", "minutes": 7}
    st["places"]["jade_cave"]["people"] = ["左慈"]  # 三步外、不是兩步內：篩「有人物」時照寫
    out = run(game, """const g = { vw: 375, vh: 668 }, c = H.camOpen(g), z0 = H.mvZ0(g), r = H.mapRoom(g);
const mid = H.camAt(g, (g.vw / 2 - c.x) / c.z, ((r.top + r.bottom) / 2 - c.y) / c.z, z0 * 0.6), wide = H.camAt(g, 330, 960, z0);
const near = H.marksHtml(H.S.mapBase, H.S.mapState, c, g), midHtml = H.marksHtml(H.S.mapBase, H.S.mapState, mid, g);
H.S.mapFilter = 'people'; const filt = H.marksHtml(H.S.mapBase, H.S.mapState, wide, g); H.S.mapFilter = 'all';
return { near, mid: midHtml, filt };""", st=st)
    hops = _hops(game.map_base(), "yingchuan")
    near = {lab[0]: lab for lab in _labs(out["near"])}
    assert {"yingchuan", "yingshui", "yingchuan_wilds", "songshan_foot", "yingchuan_academy", "deep_mountain"} <= set(near)
    for pid, lab in near.items():
        assert lab[2] == (f'{st["places"][pid]["minutes"]} 分' if 0 < hops[pid] <= 2 else ""), lab
    assert "<small>" not in out["near"] and 'class="mv-side"' not in out["near"] and 'class="ins"' not in out["near"]
    mid = {lab[0]: lab for lab in _labs(out["mid"])}
    assert all(lab[2] == "" for lab in mid.values())
    assert all(hops[x] <= 1 or x == "deep_mountain" or st["places"][x]["rich"] or next(p for p in game.map_base()["places"] if p["id"] == x)["big"] for x in mid)
    assert "changshe" not in mid and "changshe" in near  # 長社兩步：近景寫、中景不寫
    filt = {lab[0] for lab in _labs(out["filt"])}
    assert "jade_cave" in filt and "songshan_foot" not in filt  # 篩到的照寫（三步外），沒篩到的兩步內也不寫


def test_w2_selected_end_and_next_stop_are_always_named():
    """PM 2026-10-31：選中的那一處、護糧的終點、標了下一站的那一處一定寫名字（跟你腳下、本週同一級）；下一站、終點照 Joy 的寫成名字後的字條。"""
    game = _w2()
    out = run(game, """H.mapGoto('changshe', 'runan_wilds'); const g = { vw: 375, vh: 668 }; H.S.mapCam = H.camFirst(g);
return H.marksHtml(H.S.mapBase, H.S.mapState, H.S.mapCam, g);""")
    labs = {lab[0]: lab for lab in _labs(out)}
    assert labs["changshe"][3] == "下一站" and labs["runan_wilds"][3] == "終點" and "sel" in labs["changshe"][4]


def test_w2_far_is_joys_far_view_with_no_minimap_or_pills():
    """遠景照 Joy 的（大區名、各方幾處、小點，名字只有你、選的、本週），比 Joy 的多一樣：護糧的終點也寫名字（Joy 的遠景只掛圈；W2 Task 0 合 Joy 的
    「去輿圖帶終點」時加的：test_go_to_map_opens_on_the_target_with_both_ends_of_an_escort 在大框裡畫，落在遠景）；區名 chip 寫「天下」、沒有小地圖、沒有箭頭牌。"""
    game = _w2()
    out = run(game, """const g = { vw: 375, vh: 668 }, c = H.camFit(g), lay = H.mvLayout(H.S.mapBase, H.S.mapState, c, g);
return { lay, z: c.z, z0: H.mvZ0(g) };""")
    lay = out["lay"]
    assert lay["lvl"] == 0 and lay["area"] == "天下" and lay["pills"] == []
    assert 'class="mv-reg"' in lay["html"] and 'class="mv-dot' in lay["html"] and 'class="mv-pin' not in lay["html"]
    assert [lab for lab in re.findall(r'class="mv-lab[^"]*"[^>]*data-id="([^"]+)"', lay["html"])] == ["yingchuan"]


def test_w2_the_area_chip_names_the_region_in_the_middle_of_the_screen():
    """左上的區名 chip（設計 2.1 HUD）：寫畫面中心此刻在哪一區（打開＝你所在的區；拖過去跟著換；遠景寫「天下」）；點了開找地點那一頁、捲到跳到大區。"""
    game = _w2()
    out = run(game, """const g = { vw: 375, vh: 668 }, z0 = H.mvZ0(g);
const open = H.mvArea(H.S.mapBase, H.S.mapState, H.camOpen(g), g), luoyang = H.mvArea(H.S.mapBase, H.S.mapState, H.camAt(g, 150, 800, z0), g);
const far = H.mvArea(H.S.mapBase, H.S.mapState, H.camFit(g), g);
const chrome = H.pageMap();
T.docListeners.click[0]({ target: { closest: () => ({ dataset: { act: 'map-area' }, classList: { contains: () => false, add() {}, remove() {} } }) } });
return { open, luoyang, far, chrome, mode: H.S.mapMode };""")
    assert (out["open"], out["luoyang"], out["far"]) == ("潁川汝南", "洛陽", "天下")
    assert 'data-act="map-area"' in out["chrome"] and ">潁川汝南</span>" in out["chrome"]
    assert out["mode"] == "search"


def test_w2_the_minimap_frame_is_the_current_view():
    """右上的小地圖（設計 2.1）：整個天下、每一塊地照主人上色、白框＝此刻地圖框看到的那一塊（地圖座標）、你紅點；寬 100，窄螢幕（< 360）64；
    近中景才有。點小地圖＝中心移到那一帶、倍率不變。"""
    game = _w2()
    base = game.map_base()
    out = run(game, DRAWER_DOM + GESTURE_DOM + """const res = {};
for (const vw of [375, 320]) {
  const g = { vw, vh: 600 }, c = H.camOpen(g);
  res[vw] = { html: H.miniHtml(H.S.mapBase, H.S.mapState, c, g), c, g };
}
const g = { vw: 375, vh: 700 }, settle = () => { let i = 0; extra = 0; while (q.size && i++ < 400) frame(); };
const open = H.camOpen(g), r0 = H.mapRoom(g);
// 從中景（Z0 × 0.6）點：打開的取景本來就是 Z0，從那裡點測不出「倍率不變」（W2 審查 2026-10-31：改成一律飛到 Z0 照樣綠）
H.camSet(H.camAt(g, (g.vw / 2 - open.x) / open.z, ((r0.top + r0.bottom) / 2 - open.y) / open.z, H.mvZ0(g) * 0.6)); H.drawMarks(); settle();
const z = H.S.mapCam.z, el = { getBoundingClientRect: () => ({ left: 263, top: 62, width: 100, height: 149 }) };
H.mapMini(el, { clientX: 263 + 50, clientY: 62 + 75 }); settle();
const c = H.S.mapCam, r = H.mapRoom(g);
res.click = { z, z0: H.mvZ0(g), after: c.z, centre: [(g.vw / 2 - c.x) / c.z, ((r.top + r.bottom) / 2 - c.y) / c.z] };
return res;""")
    fx, fy, fw, fh = base["world"]["frame"]
    for vw, mw in ((375, 100), (320, 64)):
        r = out[str(vw)]
        assert f'style="width:{mw}px;height:{round(mw * fh / fw)}px"' in r["html"]
        rect = re.search(r'<rect id="mv-mini-view" x="([-\d.]+)" y="([-\d.]+)" width="([-\d.]+)" height="([-\d.]+)"', r["html"]).groups()
        c, g = r["c"], r["g"]
        assert [float(v) for v in rect] == pytest.approx([-c["x"] / c["z"], -c["y"] / c["z"], g["vw"] / c["z"], g["vh"] / c["z"]], abs=0.06)
        assert r["html"].count("<path clip-path=") == len(set(game.map_state()["places"]) - _patches(base))  # 拿圓當地的不畫
    click = out["click"]
    assert click["after"] == pytest.approx(click["z"]) and click["z"] == pytest.approx(click["z0"] * 0.6)
    want = (fx + 0.5 * fw, fy + 75 / 149 * fh)
    assert click["centre"][0] == pytest.approx(want[0], abs=1) and click["centre"][1] == pytest.approx(want[1], abs=1)


def test_w2_arrow_pills_point_at_neighbours_off_the_screen():
    """箭頭牌（設計 2.1）：近景、沒點地點、不在路上時，腳下一步而小圖整個在畫面外的各掛一顆「‹ 地名 N分」；按了＝點那一處（data-act="map-place"）。
    打開時是洛陽官道一顆（丙1 那一顆）；鏡頭移到別處（腳下五處都在外面）五顆互不相交、都在畫面裡。點了一處、中景都沒有。"""
    game = _w2()
    out = run(game, """const g = { vw: 375, vh: 668 }, z0 = H.mvZ0(g), base = H.S.mapBase, st = H.S.mapState;
const open = H.mvLayout(base, st, H.camOpen(g), g), away = H.mvLayout(base, st, H.camAt(g, 700, 1200, z0), g);
const midz = H.mvLayout(base, st, H.camAt(g, 424, 943, z0 * 0.6), g);
H.S.mapDrawer = 'full'; const full = H.mvLayout(base, st, H.camAt(g, 700, 1200, z0), g); H.S.mapDrawer = 'peek';
H.S.mapMode = 'place'; H.S.mapSel = 'changshe'; const picked = H.mvLayout(base, st, H.camOpen(g), g);
return { open: open.pills, away: away.pills, midz: midz.pills, full: full.pills, picked: picked.pills };""")
    assert [p["id"] for p in out["open"]] == ["luoyang_road"]
    assert re.search(r'data-act="map-place" data-id="luoyang_road"[^>]*><b aria-hidden="true">‹</b><span>洛陽官道 8分</span>', out["open"][0]["html"])
    away = out["away"]
    assert sorted(p["id"] for p in away) == ["luoyang_road", "songshan_foot", "yingchuan_academy", "yingchuan_wilds", "yingshui"]
    for i, p in enumerate(away):
        assert 0 <= p["box"][0] and p["box"][2] <= 375 and 0 <= p["box"][1] and p["box"][3] <= 668 - 68
        assert not any(_cross(p["box"], o["box"]) for o in away[i + 1:])
    assert out["midz"] == [] and out["picked"] == [] and out["full"] == []  # 中景、點了一處、抽屜全開（地圖只剩一條）都不掛


@pytest.mark.slow  # 單一條超過一秒（走一段路）
def test_w2_no_tray_and_no_pills_on_the_road():
    """在路上（W3 才換底條）：抽屜照 Joy 的（往哪裡、喊停＋沿路能去那一排、兩格），沒有底條、沒有箭頭牌。"""
    game = _w2()
    game.travel("changshe", "walk")
    out = run(game, """const g = { vw: 375, vh: 668 }; return { near: H.nearHtml(H.S.mapBase, H.S.mapState), stops: H.drawerStops(),
  pills: H.mvLayout(H.S.mapBase, H.S.mapState, H.camOpen(g), g).pills };""")
    assert "m-tray" not in out["near"] and "m-journey" in out["near"] and out["stops"] == ["peek", "full"] and out["pills"] == []


def test_w2_the_tray_says_this_weeks_order_and_how_many_places_you_can_sortie():
    """底條（設計 2.1）：「本週」章＋地名＋軍令內容＋步行 N 分（按了＝點那一處）｜右邊朱字「可出陣 N ›」（N＝可出陣的地數＝地上的橘框數，腳下那一處
    不算：test_w2_the_sortie_count_on_the_tray_is_the_row_it_opens）；
    沒有本週寫「本週沒有軍令」；窄螢幕只留軍令的第一個詞（其餘包在 .m-tray-more，style.css 在 < 360 藏起來）。"""
    game = _w2()
    st = game.map_state()
    n = sum(1 for q in st["places"].values() if q["sortie"])
    assert n == 8  # 開季八塊中立寶地
    st["week"] = {"id": "changshe", "why": "軍令・護糧・新野→宛城", "minutes": 6}
    out = run(game, "return H.nearHtml(H.S.mapBase, H.S.mapState);", st=st)
    tray = out[: out.index('<i class="m-tray-end">')]
    assert tray.startswith('<div class="m-tray"><button type="button" class="m-tray-wk" data-act="map-pick" data-id="changshe">')
    assert '<span class="m-tray-tag">本週</span><b>長社</b><span class="m-tray-sub">護糧<span class="m-tray-more">・新野→宛城</span>・步行 6 分</span>' in tray
    assert f'<button type="button" class="m-tray-go" data-act="map-sortie">可出陣 {n} ›</button>' in tray
    assert out.index("m-tray-end") < out.index('class="m-nhead"') < out.index("m-peek-end")
    st["week"] = None
    none = run(game, "return H.nearHtml(H.S.mapBase, H.S.mapState);", st=st)
    assert '<span class="m-tray-none">本週沒有軍令</span>' in none
    css = re.sub(r"/\*.*?\*/", "", (server.WEB / "style.css").read_text(encoding="utf-8"), flags=re.S)
    narrow = [m.group(1) for m in re.finditer(r"@media \(max-width: 359px\) \{\n(.*?)\n\}", css, flags=re.S)]
    assert any(".m-tray-more { display: none; }" in block for block in narrow)
    assert "可出陣" not in run(_w2(faction=None), "return H.nearHtml(H.S.mapBase, H.S.mapState);")  # 散人：一處都不能出陣，不寫那一顆


@pytest.mark.slow  # 單一條超過一秒（等點地點的 MV_TAP2）
def test_w2_the_three_parts_of_the_tray_each_do_their_one_thing():
    """底條按下去（設計 2.1 底條）：本週那一塊＝點那一處（開它的卡）；「可出陣 N ›」＝抽屜拉到一排卡那一格、那一排只列可出陣的、地圖上不合的淡掉；
    拉回那一行（把手、✕ 收回）那個篩選就清掉。（在路上的「沿路做小事 ›」是 W3。）"""
    game = _w2()
    st = game.map_state()
    st["week"] = {"id": "changshe", "why": "軍令・守城", "minutes": 6}
    sortie = sorted(x for x, q in st["places"].items() if q["sortie"])
    out = run(game, DRAWER_DOM + """
const click = (act, id) => T.docListeners.click[0]({ target: { closest: () => ({ dataset: { act, id }, classList: { contains: () => false, add() {}, remove() {} } }) } });
return (async () => {
  H.mapBack();
  await click('map-pick', 'changshe');
  const week = [H.S.mapMode, H.S.mapSel, body.innerHTML.includes('data-act="map-back"')];
  H.mapBack();
  await click('map-sortie');
  const row = { filter: H.S.mapFilter, drawer: H.S.mapDrawer, ids: H.nearList(H.S.mapBase, H.S.mapState).map((b) => b.id), head: body.innerHTML.match(/<div class="m-nhead"><b>([^<]+)/)[1],
    marks: H.marksHtml(H.S.mapBase, H.S.mapState, { z: 1.5, x: -450, y: -1100 }, { vw: 375, vh: 668 }) };
  H.mapStop('peek');
  const back = [H.S.mapFilter, H.S.mapDrawer];
  return { week, row, back };
})();""", st=st)
    assert out["week"] == ["place", "changshe", True]
    row = out["row"]
    assert row["filter"] == "sortie" and row["drawer"] == "row" and sorted(row["ids"]) == [x for x in sortie if x != "yingchuan"] and row["ids"]
    assert row["head"] == f"可出陣・{len(row['ids'])} 處"
    assert re.search(r'class="mv-pin [a-z]+ dim"[^>]*data-id="yingshui"', row["marks"])  # 不能出陣的淡掉
    assert out["back"] == ["all", "peek"]


def test_w2_the_drawer_has_three_stops_without_a_place():
    """抽屜沒點地點時三格（設計 2.1 底條）：一行（底條，量不到照 68）、一排卡（Joy 原本量 .m-peek-end 的那一高，量不到 196）、全開九成四；
    把手點一下在一行與一排卡之間換，再拉才到全開。點了一處照舊 peek／half／full、點一下在第一格與最後一格之間換。"""
    out = run(_w2(), DRAWER_DOM + """const res = {};
res.stops = H.drawerStops();
for (const h of ['peek', 'row', 'full']) { H.setMapDrawer(h); res[h] = [drawer.style.height, fab.style.bottom]; res[h + 'Fab'] = fab.style.visibility; }
H.S.mapDrawer = 'peek'; res.tap1 = H.drawerTap(H.drawerStops()); H.S.mapDrawer = 'row'; res.tap2 = H.drawerTap(H.drawerStops());
H.S.mapDrawer = 'full'; res.tap3 = H.drawerTap(H.drawerStops());
H.S.mapMode = 'place'; H.S.mapSel = 'changshe'; res.place = H.drawerStops(); H.S.mapDrawer = 'peek'; res.tap4 = H.drawerTap(H.drawerStops());
return res;""")
    assert out["stops"] == ["peek", "row", "full"]
    assert out["peek"] == ["68px", "80px"] and out["row"] == ["196px", "208px"] and out["full"] == [f"{round(650 * 0.94)}px", f"{round(650 * 0.94) + 12}px"]
    assert (out["peekFab"], out["rowFab"], out["fullFab"]) == ("", "", "hidden")  # 全開時地圖只剩一條：右下兩顆收起來（不疊在 🔍 上）
    assert (out["tap1"], out["tap2"], out["tap3"]) == ("row", "peek", "peek")
    assert out["place"] == ["peek", "half", "full"] and out["tap4"] == "full"


def test_w2_going_to_a_target_frames_both_ends_at_most_at_z0():
    """帶著目標進來（江湖頁「去輿圖」，Joy 2026-10-31；PM 10/31 定的接法）：照 Joy 的把你與目標（護糧是下一站與終點）一起框進來，倍率最多 Z0
    （Joy 的 MV_PICK_Z 換成 Z0）；框進來會成遠景（< Z0 × mid_from）才只看目標、倍率 Z0。"""
    game = _w2()
    out = run(game, """const g = { vw: 375, vh: 668 }, z0 = H.mvZ0(g), res = { z0 };
H.mapGoto('yingshui'); res.close = H.camFirst(g);
H.mapGoto('zhuo_county'); res.far = H.camFirst(g); res.farAt = H.camAt(g, 584, 118, z0);
H.mapGoto('nanyang_wilds', 'nanyang_huangjin_camp'); res.leg = H.camFirst(g);
return res;""")
    z0 = out["z0"]
    assert out["close"]["z"] <= z0 + 1e-9 and out["leg"]["z"] <= z0 + 1e-9 and out["leg"]["z"] >= z0 * 0.45
    assert out["far"] == pytest.approx(out["farAt"])


# ── W2 審查修正（2026-10-31，三位審查員對 dev/map-view-w2 c4140079 的發現）──
SETTLE = "const settle = () => { let i = 0; extra = 0; while (q.size && i++ < 400) frame(); };\n"


@pytest.mark.parametrize("vw", [375, 320])
def test_w2_a_selected_name_is_not_crowded_out_by_its_own_ring(vw):
    """選中的（點了的、附近那一排滑到的）那一處小圖外一圈（.mv-ring，半徑 22）不擋它自己的名字：名字擺在圈外、照原本的字級（14／16px）。
    W2 審查（2026-10-31）：那一圈先佔了位，名字的八個位置都貼著小圖、全落在圈裡，打開的取景裡兩步內每一處當選中的都縮成 11px（常常還拉細線），
    丙是 14px。11px 是四個位置都撞到別的東西才用的退路（設計 2.2）。名字也不壓那一圈。"""
    game = _w2()
    hops = _hops(game.map_base(), "yingchuan")
    ids = sorted(x for x, h in hops.items() if 0 < h <= 2 and x in game.map_state()["places"])
    out = run(game, f"""const g = {{ vw: {vw}, vh: {FRAMES[vw]} }}, res = {{}};
for (const id of {json.dumps(ids)}) {{
  for (const [mode, key] of [['place', 'mapSel'], ['overview', 'mapPreview']]) {{
    Object.assign(H.S, {{ mapMode: mode, mapSel: null, mapPreview: null, mapDrawer: 'peek' }}); H.S[key] = id;
    const c = H.camOpen(g), r = H.mapRoom(g), b = H.S.mapBase.places.find((p) => p.id === id), x = c.x + b.x * c.z, y = c.y + b.y * c.z;
    if (x < 30 || x > g.vw - 30 || y < r.top + 30 || y > r.bottom - 30) continue;
    res[mode + ':' + id] = {{ x, y, html: H.marksHtml(H.S.mapBase, H.S.mapState, c, g) }};
  }}
}}
return res;""")
    assert len(out) >= (8 if vw == 375 else 4), sorted(out)
    for key, case in out.items():
        lab = next(lab for lab in _labs(case["html"]) if lab[0] == key.split(":")[1])
        assert "sel" in lab[4] and "tiny" not in lab[4], (key, lab)
        ring = (case["x"] - 22, case["y"] - 22, case["x"] + 22, case["y"] + 22)
        assert not _cross(_lab_box(lab)[0], ring), (key, lab)


@pytest.mark.slow  # 單一條超過一秒（要一幀一幀飛）
def test_w2_switching_region_flies_to_its_centre_at_z0_times_switch_zoom():
    """換區（找地點那一頁「跳到大區」那一排，map-region；設計 2.2、第七章「換區＝那一區中心、Z0 × switch_zoom」）：倍率＝Z0 × switch_zoom（中景），
    露出來那一塊的正中＝那一區的中心（regions[].cx／cy）；貼著天下框邊的那幾區照夾框（camAt）。W2 審查（2026-10-31）：以前沒有行為測試，
    倍率改成固定 2（Joy 以前的「最多兩倍」）照樣綠。"""
    game = _w2()
    v, z0 = _view(game)
    out = run(game, DRAWER_DOM + GESTURE_DOM + SETTLE + """
const click = (act, id) => T.docListeners.click[0]({ target: { closest: () => ({ dataset: { act, id }, classList: { contains: () => false, add() {}, remove() {} } }) } });
const g = { vw: 375, vh: 700 }, res = {};
for (const r of H.S.mapBase.regions) {
  H.camSet(H.camOpen(g)); H.drawMarks(); settle();
  click('map-region', r.id); settle();
  const c = H.S.mapCam, room = H.mapRoom(g);
  res[r.id] = { c, centre: [(g.vw / 2 - c.x) / c.z, ((room.top + room.bottom) / 2 - c.y) / c.z], want: H.camAt(g, r.cx, r.cy, H.mvZ0(g) * H.S.mapBase.view.switch_zoom),
    r: [r.cx, r.cy], mode: H.S.mapMode };
}
return res;""")
    assert len(out) >= 5
    free = 0
    for rid, r in out.items():
        assert r["mode"] == "overview" and r["c"]["z"] == pytest.approx(z0(375) * v["switch_zoom"]), rid
        assert [r["c"]["z"], r["c"]["x"], r["c"]["y"]] == pytest.approx([r["want"]["z"], r["want"]["x"], r["want"]["y"]], abs=0.05), rid
        if r["centre"] == pytest.approx(r["r"], abs=0.5):
            free += 1  # 沒夾到框邊的：正中就是那一區的中心
    assert free >= 1, out  # 375×700 的中景看得到 417×651 個單位，多半的區貼著框邊、照夾框


@pytest.mark.slow  # 單一條超過一秒（要一幀一幀飛）
def test_w2_sliding_the_near_row_flies_at_least_to_z0():
    """附近那一排左右滑、停在一張（mapPreviewTo）：地圖飛到那一處，倍率至少到 Z0（第四章取代表：Joy 的 MV_PREVIEW_Z 1.1 換成 Z0）；已經比 Z0 近就
    照現在的倍率。W2 審查（2026-10-31）：以前沒有測試守，改回 1.1 照樣綠。"""
    out = run(_w2(), DRAWER_DOM + GESTURE_DOM + SETTLE + """
const g = { vw: 375, vh: 700 }, z0 = H.mvZ0(g), at = (id) => H.S.mapBase.places.find((p) => p.id === id);
const centre = () => { const c = H.S.mapCam, r = H.mapRoom(g); return [(g.vw / 2 - c.x) / c.z, ((r.top + r.bottom) / 2 - c.y) / c.z]; };
const y = at('yingchuan'), res = { z0 };
H.camSet(H.camAt(g, y.x, y.y, z0 * 0.6)); H.drawMarks(); settle();
H.mapPreviewTo('changshe'); settle();
res.mid = { z: H.S.mapCam.z, c: centre(), prev: H.S.mapPreview };
H.camSet(H.camAt(g, y.x, y.y, z0 * 1.3)); H.drawMarks(); settle();
H.mapPreviewTo('songshan_foot'); settle();
res.near = { z: H.S.mapCam.z, c: centre() };
res.at = { changshe: [at('changshe').x, at('changshe').y], songshan_foot: [at('songshan_foot').x, at('songshan_foot').y] };
return res;""")
    z0 = out["z0"]
    assert out["mid"]["prev"] == "changshe" and out["mid"]["z"] == pytest.approx(z0) and out["mid"]["c"] == pytest.approx(out["at"]["changshe"], abs=0.5)
    assert out["near"]["z"] == pytest.approx(z0 * 1.3) and out["near"]["c"] == pytest.approx(out["at"]["songshan_foot"], abs=0.5)


def test_w2_folding_the_drawer_back_to_the_tray_scrolls_it_to_the_top():
    """抽屜收回底條那一行、一排卡那一格時捲回頂上（W2 審查 2026-10-31）：以前全開捲到下面再收回、點了一處往下捲卡再收回（mapBack 整塊換掉），
    scrollTop 照留，那一行露的是「這一季誰佔過…」或腳下那張卡，底條（本週、可出陣）看不到。全開照留（拉上來接著看）；一處的卡照 Joy 的。"""
    out = run(_w2(), DRAWER_DOM + """const res = {};
H.setMapDrawer('full'); body.scrollTop = 420; H.mapStop('peek'); res.peek = body.scrollTop;
H.setMapDrawer('full'); body.scrollTop = 420; H.mapStop('row'); res.row = body.scrollTop;
H.mapPick('changshe'); H.setMapDrawer('half'); body.scrollTop = 260; H.mapBack(); res.back = body.scrollTop;
H.setMapDrawer('row'); body.scrollTop = 30; H.setMapDrawer('full'); res.full = body.scrollTop;
H.mapPick('changshe'); H.setMapDrawer('half'); body.scrollTop = 120; H.setMapDrawer('peek'); res.card = body.scrollTop;
return res;""")
    assert out == {"peek": 0, "row": 0, "back": 0, "full": 30, "card": 120}


def _css_rules(css):
    """style.css 的每一條規則：[(選擇器清單, {屬性: 值})]（@media 裡的也算進來；註解先拿掉）。"""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        sels = [s.strip() for s in m.group(1).split(",")]
        decls = dict((k.strip(), v.strip()) for k, v in (d.split(":", 1) for d in m.group(2).split(";") if ":" in d))
        out.append((sels, decls))
    return out


def _css_px(rules, sel, prop):
    vals = [d[prop] for sels, d in rules if sel in sels and prop in d]
    assert vals, (sel, prop)
    return float(re.fullmatch(r"(-?[\d.]+)px", vals[-1]).group(1))


def test_w2_the_hud_and_the_tray_are_big_enough_to_tap():
    """點得到（W2 審查 2026-10-31：區名 chip 高 34、箭頭牌 24、底條的「本週」「可出陣 N ›」25～29，浮著的圓鈕與 🔍 是 46，tests/server/test_server.py）：
    這四樣的點擊範圍至少 40px 高。chip 與箭頭牌的樣子照丙不變，點擊範圍用 ::before 上下撐開（chip 42、箭頭牌 40；箭頭牌排的時候照撐開的那一塊讓開
    別的牌、小圖、名字，_pills）；底條那兩塊本身就 40 高（那一行多 4px）。"""
    css = re.sub(r"/\*.*?\*/", "", (server.WEB / "style.css").read_text(encoding="utf-8"), flags=re.S)
    rules = _css_rules(css)
    for sel, h in ((".mv-area", 34), (".mv-pill", 24)):
        assert _css_px(rules, sel, "height") == h  # 樣子照丙
        assert [d.get("position") for s, d in rules if sel in s and "position" in d][-1] == "absolute"
        before = sel + "::before"
        assert [d.get("content") for s, d in rules if before in s and "content" in d] == ['""']
        assert [d.get("position") for s, d in rules if before in s and "position" in d] == ["absolute"]
        assert h - _css_px(rules, before, "top") - _css_px(rules, before, "bottom") >= 40, sel
    for sel in (".m-tray-wk", ".m-tray-go"):
        assert _css_px(rules, sel, "min-height") >= 40, sel
    assert "MV_PILL_HIT = 40" in APP.read_text(encoding="utf-8")  # 排箭頭牌照撐開的那一塊（24 ＋ 上下各 8）


def test_w2_the_sortie_count_on_the_tray_is_the_row_it_opens():
    """底條「可出陣 N ›」的 N＝按下去那一排的張數（W2 審查 2026-10-31）：那一排不列你腳下那一處（腳下的卡接在後面），N 也不算它。站在自己也能
    出陣的地方（南陽郊野），以前寫「可出陣 8 ›」、按下去標題「可出陣・7 處」。"""
    game = _w2(at="nanyang_wilds")
    st = game.map_state()
    assert st["places"]["nanyang_wilds"]["sortie"]  # 腳下那一處也能出陣
    out = run(game, DRAWER_DOM + """const tray = H.nearHtml(H.S.mapBase, H.S.mapState);
H.mapSortie();
return { tray, ids: H.nearList(H.S.mapBase, H.S.mapState).map((b) => b.id), head: body.innerHTML.match(/<div class="m-nhead"><b>([^<]+)/)[1] };""")
    n = int(re.search(r'data-act="map-sortie">可出陣 (\d+) ›<', out["tray"]).group(1))
    assert n == len(out["ids"]) == sum(1 for x, q in st["places"].items() if q["sortie"] and x != "nanyang_wilds") and "nanyang_wilds" not in out["ids"]
    assert out["head"] == f"可出陣・{n} 處"


# ── W2 第二輪（2026-10-31，QA qa/map-view-w2 開的 FB-9090～FB-9095；PM 10/31 定 9090、9091、9092、9093、9095 在 W2 修）──
# 把手（#mgrab）照瀏覽器真的順序點：pointerdown → pointerup →（版面照 pointerup 做的事換了）→ 瀏覽器照新的版面在同一點找元素送 click
# （觸控的 click 是放手之後才照那一點命中的：CDP Input.dispatchTouchEvent 量到的，QA 的 FB-9090）。elementFromPoint 照抽屜此刻的高算：
# 抽屜上面是地圖、抽屜頂上 22px 是把手、把手底下是抽屜的內文——一排卡那一格時，內文那一帶是附近那一排的卡（點了開那一處）。
GRAB_DOM = """
const L = {}, FRAME = 650;
const grab = { dataset: {}, addEventListener: (t, f) => { (L[t] = L[t] || []).push(f); }, setPointerCapture() {}, closest: () => null };
drawer.classList = { add() {}, remove() {} };
Object.defineProperty(drawer, 'offsetHeight', { get: () => parseFloat(drawer.style.height) || 0 });
els.mgrab = grab;
const card = { dataset: { act: 'map-place', id: 'changshe' }, classList: { contains: () => false } }; card.closest = () => card;
const inner = { closest: () => null }, land = { closest: () => null };
const hitAt = (y) => { const top = FRAME - (parseFloat(drawer.style.height) || 0); return y < top ? land : y < top + 22 ? grab : H.S.mapDrawer === 'row' ? card : inner; };
const send = (type, y, extra = {}) => { const ev = { type, pointerId: 1, pointerType: 'touch', button: 0, clientX: 187, clientY: y, ...extra }; for (const f of L[type] || []) f(ev); };
// 瀏覽器的 click：照此刻的版面命中，先給命中的那一個（把手自己的監聽），再冒泡到 document（app.js 那一大串 case）
const click = (y) => {
  const t = hitAt(y), ev = { type: 'click', target: t, clientX: 187, clientY: y, stopped: false, stopPropagation() { this.stopped = true; }, preventDefault() {} };
  if (t === grab) for (const f of L.click || []) f(ev);
  if (!ev.stopped) for (const f of T.docListeners.click || []) f(ev);
  return t === card ? 'card' : t === grab ? 'grab' : t === land ? 'land' : 'inner';
};
const tap = (y) => { send('pointerdown', y); send('pointerup', y); return click(y); };
const grabY = () => FRAME - (parseFloat(drawer.style.height) || 0) + 11;
"""


def test_fb9090_tapping_the_handle_opens_the_row_without_the_click_landing_on_a_card():
    """FB-9090：把手點一下（沒點地點時一行 ⇄ 一排卡）不能讓那一下的 click 落到換格之後滑到手指底下的卡上。以前 pointerup 就換格，瀏覽器接著照新的
    版面在同一點送 click，那裡此刻是附近那一排的卡（長社），開了長社的卡、一排卡從頭到尾沒露出來。現在點一下在把手的 click 換格（命中的還是把手），
    拖照舊在 pointer 事件裡；拖完（滑鼠按放都在把手上）多出來的那一個 click 不算點一下，可是下一次按下去的 click 照算。"""
    out = run(_w2(), DRAWER_DOM + GRAB_DOM + """const res = {};
H.setMapDrawer('peek'); H.drawerGrab();
for (const k of ['one', 'two', 'three']) res[k] = { hit: tap(grabY()), drawer: H.S.mapDrawer, mode: H.S.mapMode, sel: H.S.mapSel, h: drawer.style.height };
// 拖：按下、往上拖 130px、放開（靠到一排卡）；滑鼠的話按放都在把手上，瀏覽器還會送一個 click——不算點一下（不再換回一行）
H.mapBack(); H.setMapDrawer('peek');
let y = grabY(); send('pointerdown', y); send('pointermove', y - 60); send('pointermove', y - 130); send('pointerup', y - 130);
const dragged = H.S.mapDrawer; for (const f of L.click || []) f({ type: 'click', target: grab, stopPropagation() {}, preventDefault() {} });
res.drag = { stop: dragged, after: H.S.mapDrawer };
// 拖完之後真的再點一下：照算
res.next = { hit: tap(grabY()), drawer: H.S.mapDrawer };
return res;""")
    assert [out[k]["drawer"] for k in ("one", "two", "three")] == ["row", "peek", "row"], out
    for k in ("one", "two", "three"):
        assert out[k]["hit"] == "grab" and out[k]["mode"] == "overview" and out[k]["sel"] is None, (k, out[k])
    assert out["drag"] == {"stop": "row", "after": "row"} and out["next"] == {"hit": "grab", "drawer": "peek"}


def test_fb9093_a_drag_that_lets_go_exactly_on_a_stop_still_relays_the_names_and_pills():
    """FB-9093：拖把手放手時剛好就是那一格的高（一行拖上剛好到一排卡、拖到頂一定被夾在全開），以前 setMapDrawer 拿拖動中一路寫進去的高度比、
    判成沒換格，名字與箭頭牌照一行的時候排著（右下兩顆卻跟著抽屜上去，蓋住名字；全開時舊的箭頭牌留在抽屜底下）。現在照拖動開始那一刻的高比：
    放手之後字那一層＝照新的底邊重排的那一份、名字不壓右下兩顆；全開不掛箭頭牌。放手不是剛好那一格的照舊重排。"""
    game = _w2()
    out = run(game, DRAWER_DOM + GRAB_DOM + GESTURE_DOM + SETTLE + """map.clientHeight = FRAME;
const pills = { style: {}, innerHTML: '' }; els['mv-pills'] = pills;
const g = { vw: 375, vh: FRAME }, res = {};
const fresh = () => H.mvLayout(H.S.mapBase, H.S.mapState, H.S.mapCam, H.mapGeom(map));
for (const [name, dy] of [['exact', () => H.mapDrawerPx('row') - H.mapDrawerPx('peek')], ['top', () => 2000], ['near', () => 100]]) {
  H.mapBack(); H.setMapDrawer('peek'); H.drawerGrab(); H.camSet(H.camOpen(H.mapGeom(map))); H.drawMarks(); settle();
  const before = els.mkt.innerHTML, d = dy(), y = grabY();
  send('pointerdown', y); send('pointermove', y - d / 2); send('pointermove', y - d); send('pointerup', y - d); settle();
  const lay = fresh();
  res[name] = { stop: H.S.mapDrawer, px: drawer.style.height, fab: fab.style.bottom, same: els.mkt.innerHTML === lay.html, moved: els.mkt.innerHTML !== before,
    pills: pills.innerHTML, freshPills: lay.pills.map((p) => p.html).join(''), html: els.mkt.innerHTML };
}
return res;""")
    assert (out["exact"]["stop"], out["top"]["stop"], out["near"]["stop"]) == ("row", "full", "row")
    for name, r in out.items():
        assert r["same"] and r["moved"] and r["pills"] == r["freshPills"], (name, {k: v for k, v in r.items() if k != "html"})
        fb = 650 - float(r["fab"][:-2])  # 右下兩顆：46 見方、間隔 10，底下離抽屜 12（fab.style.bottom＝抽屜高＋12）
        fab = (375 - 58, fb - 102, 375 - 12, fb)
        for lab in _labs(r["html"]):
            assert r["stop"] == "full" or not _cross(_lab_box(lab)[0], fab), (name, lab)
    assert out["top"]["pills"] == ""  # 全開：地圖只剩一條，不掛箭頭牌


def test_fb9092_the_arrow_pills_stay_hidden_through_a_pinch_even_when_the_names_are_relaid():
    """FB-9092：捏的途中箭頭牌一直藏著。camSet 在手勢途中把 #mv-pills 藏起來，可是捏的途中倍率差過 MV_RELAYOUT 會照 Joy 的規矩重排字
    （marksSoon → drawMarks），drawMarks → hudDraw 以前無條件把 visibility 設回來，牌就露出來一兩幀、下一個 touchmove 又藏。現在途中（mvBusy）
    hudDraw 不設回來，放手那一次 drawMarks 才露。捏開、捏回、選了一處再捏都一樣；途中真的重排過字（不然測不到）。"""
    out = run(_w2(), DRAWER_DOM + GESTURE_DOM + SETTLE + """
const pills = { style: {}, innerHTML: '' }; els['mv-pills'] = pills;
let laid = 0; const mkt = els.mkt; let html = ''; Object.defineProperty(mkt, 'innerHTML', { set: (v) => { laid++; html = v; }, get: () => html });
const g = H.mapGeom(map), res = {};
const pinch = (name, d0, d1) => {
  H.camSet(H.camOpen(g)); H.drawMarks(); settle();
  const start = { vis: pills.style.visibility, pills: pills.innerHTML.length }, seen = [], n0 = laid;
  H.mvDown(pt('pointerdown', 1, 187 - d0 / 2, 300)); H.mvDown(pt('pointerdown', 2, 187 + d0 / 2, 300));
  for (let i = 1; i <= 40; i++) {
    const d = d0 + (d1 - d0) * i / 40;
    H.mvMove(pt('pointermove', 1, 187 - d / 2, 300)); H.mvMove(pt('pointermove', 2, 187 + d / 2, 300)); frame(); frame();
    seen.push(pills.style.visibility);
  }
  const during = laid - n0;
  H.mvUp(pt('pointerup', 1, 187 - d1 / 2, 300)); H.mvUp(pt('pointerup', 2, 187 + d1 / 2, 300)); settle();
  res[name] = { start, shown: seen.filter((v) => v !== 'hidden').length, during, after: pills.style.visibility, z: H.S.mapCam.z };
};
pinch('open', 90, 240);
pinch('close', 240, 90);
H.mapPick('yingshui'); settle(); pinch('picked', 90, 200);
return res;""")
    for name, r in out.items():
        assert r["during"] >= 1, (name, r)  # 途中真的重排過字
        assert r["shown"] == 0 and r["after"] == "", (name, r)
    assert out["open"]["start"]["pills"] > 0  # 打開的取景有箭頭牌（洛陽官道）


# FB-9095 用的假 DOM：浮著的那幾樣各一個元素（記 style.visibility），地圖框照實機的寬高（FRAMES），抽屜照 DRAWER_DOM
HUD_DOM = """
const hudEl = (extra = {}) => Object.assign({ style: {}, dataset: {}, innerHTML: '' }, extra);
const areaT = { textContent: '' };
Object.assign(els, { 'mv-area': hudEl({ querySelector: () => areaT }), 'mv-q': hudEl(), 'mv-mini': hudEl(), 'mv-pills': hudEl() });
const look = () => ({ area: els['mv-area'].style.visibility || '', q: els['mv-q'].style.visibility || '', mini: els['mv-mini'].style.visibility || '',
  fab: fab.style.visibility || '', fabBottom: fab.style.bottom, drawer: drawer.style.height, text: areaT.textContent, lvl: H.mvLevel(H.S.mapCam.z, H.mapGeom(map)),
  miniSize: (els['mv-mini'].innerHTML.match(/width:(\\d+)px;height:(\\d+)px/) || []).slice(1).map(Number) });
"""


def _hud_look(vw, case):
    """浮著的那幾樣畫出來的框（照 style.css，跟 _hud 同一套位置，只是不含 chip 撐開的點擊範圍）：區名 chip（左上 10、高 34）、🔍（右上 12、上 8、
    46 見方）、小地圖（近中景；右 12、上 62，連 1px 的框）、右下兩顆（46 見方、間隔 10，底下＝fab.style.bottom）。收起來的（visibility hidden）不算。"""
    vh = case["vh"]
    out = {"area": (10, 10, 10 + 20 + 1.15 * _text_w(case["text"], 14) + 6 + 11, 44), "q": (vw - 58, 8, vw - 12, 54)}
    if case["lvl"] > 0 and case["miniSize"]:
        mw, mh = case["miniSize"]
        out["mini"] = (vw - 12 - mw - 2, 62, vw - 12, 62 + mh + 2)
    fb = vh - float(case["fabBottom"][:-2])
    out["fab"] = (vw - 58, fb - 102, vw - 12, fb)
    return {k: b for k, b in out.items() if case[k] != "hidden"}


def test_fb9095_the_round_buttons_and_the_hud_never_overlap_each_other_or_sit_under_the_drawer():
    """FB-9095：右下兩顆（◎、全）跟著抽屜上移，小地圖固定在右上，以前兩樣不互相讓——卡拉到六成（375、360）、320 寬一排卡那一格（還有點了一處的那一行）
    ◎ 整顆被小地圖蓋住，點下去點到的是小地圖；全開時區名、🔍、小地圖的下緣被抽屜蓋住一截。現在：右下兩顆跟任何一樣浮著的會疊到就跟全開一樣收起來
    （不是挪位置），被抽屜蓋住（哪怕一截）的區名、🔍、小地圖也收起來。375／360／320 × 沒點地點的三格 × 點了一處的三格（含拉到六成）：
    看得到的那幾樣兩兩不相交、都在抽屜上面；一行那一格五樣都在（不亂收）。"""
    game = _w2()
    out = run(game, DRAWER_DOM + GESTURE_DOM + HUD_DOM + SETTLE + """const res = [];
for (const [vw, vh] of FRAMES) {
  Object.assign(map, { clientWidth: vw, clientHeight: vh }); box.clientHeight = vh;
  const g = H.mapGeom(map);
  for (const [mode, stops] of [['overview', ['peek', 'row', 'full']], ['place', ['peek', 'half', 'full']]]) {
    H.mapBack(); H.setMapDrawer('peek'); H.camSet(H.camOpen(g)); H.drawMarks(); settle();
    if (mode === 'place') { H.mapPick('yingshui'); settle(); }
    for (const h of stops) { H.setMapDrawer(h); settle(); H.drawMarks(); res.push({ vw, vh, mode, h, ...look() }); }
  }
}
return res;""".replace("FRAMES", json.dumps(sorted(FRAMES.items()))))
    assert len(out) == 3 * 6
    hidden = set()
    for case in out:
        key = (case["vw"], case["mode"], case["h"])
        top = case["vh"] - float(case["drawer"][:-2])
        boxes = _hud_look(case["vw"], case)
        names = sorted(boxes)
        for i, a in enumerate(names):
            assert boxes[a][3] <= top + 1e-6, (key, a, boxes[a], top)  # 不被抽屜蓋住
            for b in names[i + 1:]:
                assert not _cross(boxes[a], boxes[b]), (key, a, b, boxes[a], boxes[b])
        hidden |= {(key, k) for k in ("area", "q", "mini", "fab") if case[k] == "hidden"}
        if case["h"] == "peek" and case["mode"] == "overview":
            assert set(boxes) == {"area", "q", "mini", "fab"}, (key, boxes)  # 一行那一格不亂收
    # 真的收了該收的：拉到六成（375、360）與 320 一排卡的 ◎；全開時上面那一排與小地圖
    for vw in (375, 360):
        assert ((vw, "place", "half"), "fab") in hidden
    assert ((320, "overview", "row"), "fab") in hidden
    for vw in (375, 360, 320):
        assert {((vw, "overview", "full"), k) for k in ("area", "q", "mini", "fab")} <= hidden
