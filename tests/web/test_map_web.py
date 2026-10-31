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
         "groundShow", "landAt", "mapLand", "mvDown", "mvUp", "mvMove", "mvWheel", "camFly", "drawMarks", "mv"]
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
    """整頁一層：地圖框裡一張天下（#mvw：地面 #mk、路線 #mkr，大小是地圖本身的寬高）與照螢幕寫的字那一層（#mkt）；外面浮著搜尋列、
    篩選、回到我與看整張兩顆、抽屜。以前三張圖的上面那一排（‹ 天下、大區、看大局）都沒有了。
    輿圖表現第二版 W1：地常駐，「塗層」那一顆拿掉了；地（#mk）是一張向量的 SVG（不再是點陣）。"""
    game = _game()
    out = run(game, "return H.pageMap();")
    b = game.map_base()
    assert f'<div class="mv-world" id="mvw" style="width:{b["w"]}px;height:{b["h"]}px">' in out
    assert 'id="mk"' in out and 'id="mkr"' in out and 'class="mv-marks" id="mkt"' in out and 'id="mdrawer"' in out
    assert f'<svg class="mv-ground" id="mk" width="{b["w"]}" height="{b["h"]}" viewBox="0 0 {b["w"]} {b["h"]}"' in out and "<canvas" not in out
    assert 'data-act="map-search"' in out and 'id="mv-chips"' in out and 'data-act="map-home"' in out and 'data-act="map-fit"' in out
    assert 'data-act="map-timeline"' in out and 'data-act="map-wash"' not in out and "塗層" not in out
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
    """近看（輿圖表現第二版 W1）：名字只有名字——分鐘・多半・勝算那一行、悟字都在抽屜的卡與一排卡裡，不畫在圖上。"""
    game = _game()
    out = marks(game, 2)
    assert _lab(out, "changshe") and "<small>" not in _lab(out, "changshe") and 'class="ins"' not in out


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
    """近、中景：名字只有名字——沒有官／巾小印（.mv-side）、名字後的「寶」「戰」「本週」字條、名字底下那一行、進度條（.mv-bar）、悟字（.ins）。"""
    game = _game(profile="season21")
    st = game.map_state()
    st["places"]["yingchuan_wilds"]["tug"] = {"huang": 40}  # 以前會畫進度條
    st["places"]["runan_wilds"]["siege"] = "letter"  # 以前會接「戰」
    st["week"] = {"id": "changshe", "why": "軍令・守城", "minutes": 6}  # 以前會接「本週」
    out = marks(game, z, st=st)
    for gone in ('class="mv-side"', 'class="mv-bar"', 'class="ins"', 'class="mv-rich"', 'class="mv-wk"', "<small>"):
        assert gone not in out, gone
    labs = re.findall(r'<button type="button" class="mv-lab[^"]*"[^>]*>(.*?)</button>', out)
    assert len(labs) > 10 and all(re.fullmatch(r'<span class="t"><span class="nm">[^<]+</span></span>', x) for x in labs)


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
  H.camSet({{ z: 1.6, x: 10 - {p['x']} * 1.6, y: 400 - {p['y']} * 1.6 }}); H.mapBack(); settle();
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
    assert out["pinX"] < 30 and out["z0"] == 1.6  # 長社的小圖在畫面左緣（以前第一下會 mvNudge 飛一下）
    assert out["before"] == ["overview", None, "peek", True, ""]
    assert out["zoomed"]["look"] == out["before"] and out["zoomed"]["z"] == 3.2
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
