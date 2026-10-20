"""輿圖重製第 2 批：天下圖的網頁（輿圖簡化設計 4.1、3.6、4.6；第七章第 4、7、8 條）。
打開輿圖第一眼是天下圖：同一張底圖換一個固定的取景（worldFit）、不拖不縮；#mk 畫州郡地面（一方一色、沒人佔一色，顏色照劇本）、
紅線（任兩方相接）、細墨線（有主與沒人佔相接）、金點、璽、州名與各方幾處、你。點一州換到區圖那一層。
在 node 裡跑整支 app.js（tests/webharness.py），餵伺服器真的會給的底圖與疊層；沒有 node 就略過。"""
from __future__ import annotations

import random
import re
from pathlib import Path

import pytest
import test_prologue_web

import server
import webharness
from conftest import real_content
from tianxia import calendar, territory
from tianxia.engine import Game
from tianxia.models import FactionDef, FactionInk
from tianxia.sqlite_world import open_world
from tianxia.state import TerritoryState

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]
NAMES = ["S", "pageMap", "mapChrome", "mapxClass", "drawerHtml", "worldFit", "worldParts", "worldLabels", "worldCounts",
         "worldDrawerHtml", "regionView", "sideInk", "timelineHtml", "chartHtml", "graphSvg", "hudHtml", "controlAt", "textW"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
APP = Path(server.WEB) / "app.js"


def _game(content=None, faction="guan", at="yingchuan", conquest=True):
    from conquest_kit import conquest_rules

    c = content or real_content("weekend")
    if conquest:
        conquest_rules(c)
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    territory.update(game.state.world, c)
    game.state.player.faction, game.state.player.location = faction, at
    return game


def run(game, script, **S):
    payload = {"m": server.main_view(game), "script": script,
               "S": {"mapBase": game.map_base(), "mapState": game.map_state(), **S},
               "menxia": None, "stored": {}, "responses": {}}
    return webharness.run(DRIVER, payload)


NOW = "{ k: 2.5, week: H.S.mapState.now_week, tl: false, sel: null }"


def parts(game, o=NOW, **S):
    return run(game, f"return H.worldParts(H.S.mapBase, H.S.mapState, {o});", **S)


def test_world_parts_paint_each_cell_with_its_holder():
    game = _game()
    low, _ = parts(game)
    world, st = game.map_base()["world"], game.map_state()
    assert low.count("<clipPath") == len(world["regions"]) == 9
    for cell in world["cells"]:
        side = st["places"][cell["id"]]["control"]
        colour = next(s["soft"] for s in world["sides"] if s["id"] == side) if side else world["unheld"]
        assert re.search(rf'data-cell="{cell["id"]}" d="[^"]+" fill="{colour}"', low), cell["id"]
    assert 'fill="#9DB4D3"' in low and 'fill="#E7C778"' in low and f'fill="{world["unheld"]}"' in low  # 開季：官、巾、中原沒人


def test_fronts_are_red_only_between_two_sides_and_ink_between_held_and_unheld():
    game = _game()
    low, _ = parts(game)
    front = low[low.index('class="w-front"'):]
    front = front[: front.index("</g>")]
    rim = low[low.index('class="w-rim"'):]
    rim = rim[: rim.index("</g>")]
    assert front.count("<path") >= 2  # 外環路兩個口子：洛陽↔冀州、南陽↔青州
    assert rim.count("<path") >= 8  # 外圈四州的地面跟中原沒人佔的地面相接
    assert "clip-path" not in front  # 開季的前線都在州界上（跨州的邊不裁）
    w = game.state.world
    w.territory.control["yingchuan"] = "guan"  # 潁川郡被官軍佔下：它跟同一州裡沒人佔的格子之間多細墨線
    w.territory.control["yingshui"] = "huang"  # 潁水河畔被黃巾佔下：跟潁川郡相接的那一條是紅線（同一州裡的邊照州的輪廓裁）
    low2, _ = parts(game)
    front2 = low2[low2.index('class="w-front"'):]
    assert 'clip-path="url(#wc-yingchuan)"' in front2[: front2.index("</g>")]


def test_rich_places_get_gold_dots_solid_when_held():
    game = _game()
    rich = [x for x, p in game.map_state()["places"].items() if p["rich"]]
    low, _ = parts(game)
    assert low.count('class="w-rich"') == len(rich) and low.count('class="w-rich held"') == 0
    game.state.world.territory.control["changshe"] = "guan"
    low2, _ = parts(game)
    assert low2.count('class="w-rich held"') == 1


def test_the_seal_sits_in_the_core_only_when_on():
    game = _game()
    low, _ = parts(game)
    assert low.count('class="w-seal"') == 1 and ">璽<" in low
    c = real_content("weekend")
    c.config.seal.enabled = False
    low2, _ = parts(_game(content=c))
    assert 'class="w-seal"' not in low2


def test_region_labels_show_name_and_counts_from_the_sides():
    """州名底下只寫不是 0 的（企劃者 2026-10-20 從對比圖選乙）：開季洛陽「官 6」、冀州「巾 8」、潁川「寶 9」、核心「寶 2」。"""
    game = _game()
    labels = run(game, "return H.worldLabels(H.S.mapBase, H.S.mapState, H.controlAt(H.S.mapState, H.S.mapState.now_week), 2.5);")
    by = {x["id"]: x for x in labels}
    assert by["luoyang"]["name"] == "洛陽" and by["luoyang"]["line"] == "官 6"
    assert by["jizhou"]["line"] == "巾 8" and by["yingchuan"]["line"] == "寶 9" and by["core"]["line"] == "寶 2"
    game.state.world.territory.control["changshe"] = "guan"
    by = {x["id"]: x for x in run(game, "return H.worldLabels(H.S.mapBase, H.S.mapState, H.controlAt(H.S.mapState, H.S.mapState.now_week), 2.5);")}
    assert by["yingchuan"]["line"] == "官 1・寶 9"  # 佔下一塊：那一方寫在前、寶照寫
    low, _ = parts(game)
    assert ">官 6<" in low and ">洛陽<" in low and "・巾 0" not in low and "寶 0" not in low


def test_a_region_with_nothing_to_count_has_no_second_line():
    """全是 0 那一行就不畫（企劃者 2026-10-20）：地盤關著（整張沒人佔）時外圈的州只寫州名，框也矮一截。"""
    from conftest import classic_rules

    game = _game(content=classic_rules(real_content("weekend")), conquest=False)
    labels = run(game, "return H.worldLabels(H.S.mapBase, H.S.mapState, H.controlAt(H.S.mapState, H.S.mapState.now_week), 2.5);")
    by = {x["id"]: x for x in labels}
    assert by["luoyang"]["line"] == "" and by["yingchuan"]["line"] == "寶 9"
    assert by["luoyang"]["h"] < by["yingchuan"]["h"]
    low, _ = parts(game)
    name = low.index('paint-order="stroke">洛陽</text>')  # 州名那一行（點擊區的 <title> 也寫州名）
    group = low[low.rindex('<g class="w-label"', 0, name):]
    group = group[: group.index("</g>")]
    assert group.count("<text") == 1


# 地圖框的大小（寬 × 高）：手機的畫面減掉上面的狀態列（約 89）與底下的分頁列（約 56）。375×812、375×667、360×640、320×568（實機量的
# 320 寬 iPhone SE 地圖框是 320×423：天下圖只剩約 0.27 倍，州名字會縮）
SIZES = [(375, 667), (375, 522), (360, 495), (320, 423)]


@pytest.mark.parametrize("vw,vh", SIZES)
def test_region_labels_do_not_overlap_on_a_phone(vw, vh):
    """375 寬（與 360、320）：天下圖整張在地圖框裡（不橫捲），州名框兩兩不相交、都在框裡（設計第十一章）。"""
    out = run(_game(), f"""
const wd = H.S.mapBase.world, v = H.worldFit({vw}, {vh}, wd.frame, 54, 58, 900, 1340);
const labels = H.worldLabels(H.S.mapBase, H.S.mapState, H.controlAt(H.S.mapState, H.S.mapState.now_week), 1 / v.s);
const scr = (x, y) => [{vw} / 2 + (x - v.cx) * v.s, {vh} / 2 + (y - v.cy) * v.s];
const boxes = labels.map((l) => {{ const [x, y] = scr(l.x - l.w / 2, l.y - l.h / 2); return [l.id, x, y, l.w * v.s, l.h * v.s]; }});
const [fx, fy] = scr(wd.frame[0], wd.frame[1]), [gx, gy] = scr(wd.frame[0] + wd.frame[2], wd.frame[1] + wd.frame[3]);
return {{ boxes, frame: [fx, fy, gx, gy], map: [scr(0, 0)[1], scr(900, 1340)[1]] }};
""")
    fx, fy, gx, gy = out["frame"]
    assert fx >= 0 and gx <= vw and fy >= 58 - 1 and gy <= vh - 54 + 1  # 取景框整個在露出來的那一塊（不橫捲、不被抽屜蓋）
    top, bottom = out["map"]
    assert top <= 58 + 0.5 or bottom <= vh - 54 + 0.5  # 地圖比露出來的那一塊高時，上面不留一條空白的紙
    boxes = out["boxes"]
    for i, (a, ax, ay, aw, ah) in enumerate(boxes):
        assert ax >= 0 and ax + aw <= vw, a
        for b, bx, by, bw, bh in boxes[i + 1:]:
            assert ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay, (a, b)


def test_tapping_a_region_enters_it():
    low, _ = parts(_game())
    hits = re.findall(r'data-act="world-region" data-id="([a-z]+)"', low)
    assert sorted(hits) == sorted(["luoyang", "nanyang", "jizhou", "qingzhou", "yingchuan", "dongjun", "chenliu", "runan", "core"])


def test_region_view_frames_that_regions_places():
    game = _game()
    out = run(game, "return H.regionView(H.S.mapBase, 'luoyang', 375, 650, 900, 1340, 230);")
    places = [p for p in game.map_base()["places"] if p["region"] == "luoyang"]
    for p in places:
        x = 375 / 2 + (p["x"] - out["cx"]) * out["s"]
        y = 650 / 2 + (p["y"] - out["cy"]) * out["s"]
        assert 0 <= x <= 375 and 0 <= y <= 650 - 230, p["id"]
    assert out["s"] >= 0.62  # 不掉進看大局那一檔


def test_the_world_drawer_line_says_where_you_are_and_offers_to_enter():
    game = _game()
    out = run(game, "return H.worldDrawerHtml(H.S.mapBase, H.S.mapState);", mapDrawer="min")
    assert "你在 <b>潁川</b>・潁川郡（陽翟）" in out and 'data-act="world-enter"' in out and "進入此區" in out
    assert 'data-act="map-open"' in out and "誰佔著" not in out
    full = run(game, "return H.worldDrawerHtml(H.S.mapBase, H.S.mapState);", mapDrawer="half")
    assert "誰佔著" in full and 'data-act="world-enter"' in full  # 拉開：你腳下這一處的卡（第 3 批之前是 placeHtml）


def test_on_the_road_you_are_drawn_on_the_road_and_the_drawer_says_where():
    game = _game()
    game.travel("yingchuan_wilds", "walk")
    st = game.map_state()
    assert st["journey"]
    out = run(game, "return H.worldDrawerHtml(H.S.mapBase, H.S.mapState);", mapDrawer="min")
    assert "往 <b>潁川郊野</b>" in out and "分鐘" in out and "你在" not in out
    _, high = parts(game)
    assert f'cx="{st["journey"]["x"]:g}"' in high and 'class="w-you"' in high


def test_the_timeline_repaints_the_ground_for_that_week():
    game = _game(conquest=False)  # 舊拔河：推線就會易手
    w, c = game.state.world, game.content
    territory.update(w, c)
    w.time = calendar.week_start(2, c, w) + 60
    w.trends["yingru"] = 95
    territory.update(w, c)
    w.time = calendar.week_start(3, c, w) + 60
    territory.update(w, c)
    st = game.map_state()
    changed = next(x for x in st["weeks"] if x["week"] == 2)["changed"]
    assert {"id": "guan_camp", "from": "guan", "to": "huang"} in changed
    week1, _ = parts(game, "{ k: 2.5, week: 1, tl: true, sel: null }")
    week2, high2 = parts(game, "{ k: 2.5, week: 2, tl: true, sel: null }")
    assert re.search(r'data-cell="guan_camp" d="[^"]+" fill="#9DB4D3"', week1)
    assert re.search(r'data-cell="guan_camp" d="[^"]+" fill="#E7C778"', week2)
    assert high2.count('class="pulse"') == len(changed) + 1  # 易手的那幾處閃一圈，加上你的那一圈


def _four_sides():
    """四方的測試劇本（設計第十一章）：官軍、黃巾之外加兩方，各自的顏色；外圈四州各一方。"""
    c = real_content("weekend")
    c.scenario.factions = [f for f in c.scenario.factions if f.id != "haoqiang"] + [
        FactionDef(id="wei", name="魏", join_at=["linzi"], ink=FactionInk(color="#6A3D7A", soft="#C3A6CC", short="魏", label="魏")),
        FactionDef(id="wu", name="吳", join_at=["xinye"], ink=FactionInk(color="#2E7D5B", soft="#9FD1B8", short="吳", label="吳")),
    ]
    c.scenario.territory.lines = {}  # 中原不拔河：只有外圈四州有主，內圈與核心整片沒人佔
    game = _game(content=c, conquest=False)
    owners = {"luoyang": "guan", "jizhou": "huang", "qingzhou": "wei", "nanyang": "wu"}
    region = {cell["id"]: cell["region"] for cell in game.map_base()["world"]["cells"]}
    game.state.world.territory = TerritoryState(control={x: owners[r] for x, r in region.items() if r in owners})
    return game


def test_three_and_four_sides_each_get_a_colour_and_every_pair_a_front():
    game = _four_sides()
    st = game.map_state()
    assert st["sides"] == ["guan", "huang", "wei", "wu"]
    low, _ = parts(game)
    for soft in ("#9DB4D3", "#E7C778", "#C3A6CC", "#9FD1B8"):
        assert f'fill="{soft}"' in low
    world = game.map_base()["world"]
    region = {cell["id"]: cell["region"] for cell in world["cells"]}
    owners = {x: st["places"][x]["control"] for x in region}
    fronts = {frozenset((owners[e["a"]], owners[e["b"]])) for e in world["edges"]
              if e["a"] and e["b"] and owners[e["a"]] and owners[e["b"]] and owners[e["a"]] != owners[e["b"]]}
    assert fronts == {frozenset(p) for p in (("guan", "huang"), ("huang", "wei"), ("wei", "wu"), ("wu", "guan"))}  # 外環四個口子
    front = low[low.index('class="w-front"'):]
    assert front[: front.index("</g>")].count("<path") >= 4
    labels = run(game, "return H.worldLabels(H.S.mapBase, H.S.mapState, H.controlAt(H.S.mapState, H.S.mapState.now_week), 2.5);")
    assert next(x for x in labels if x["id"] == "qingzhou")["line"] == "魏 5"
    assert next(x for x in labels if x["id"] == "nanyang")["line"] == "吳 6"
    assert run(game, "return [H.sideInk('wei').color, H.sideInk('wu').name];") == ["#6A3D7A", "吳"]


def test_page_map_opens_on_the_world_with_its_top_row():
    out = run(_game(), "return [H.pageMap(), H.S.mapLayer];")
    page, layer = out
    assert layer == "world" and 'class="mapx world' in page
    top = page[page.index('class="w-top"'):]
    top = top[: top.index("</div>")]
    assert top.index("天下") < top.index("找地點") < top.index("版圖")
    assert 'data-act="map-timeline"' in top and 'data-act="map-search"' in top


def test_the_region_layer_has_a_way_back_to_the_world():
    page = run(_game(), "return H.pageMap();", mapLayer="region")
    assert 'class="mapx"' in page or 'class="mapx ' in page
    assert "world" not in page[page.index('class="mapx'):page.index(">", page.index('class="mapx'))]
    row = page[page.index('class="map-top"'):]
    assert 'data-act="map-world"' in row[: row.index('class="map-chips"')] and "天下" in row[: row.index('class="map-chips"')]


def test_the_roads_show_faintly_through_the_world_ground():
    """天下圖的路淡淡透上來（企劃者 2026-10-20 從對比圖選乙）：路照舊在底圖裡（烤進點陣那張圖），天下圖那一層不藏它；
    地面不是全不透明的，底下的路與山水看得到。"""
    svg = _game().map_base()["svg"]
    assert 'class="tx-roads"' not in svg and svg.count(" Q") > 20  # 路是底圖裡的二次曲線
    css = re.sub(r"/\*.*?\*/", "", (Path(server.WEB) / "style.css").read_text(encoding="utf-8"), flags=re.S)
    assert "tx-roads" not in css
    low, _ = parts(_game())
    ground = re.search(r'class="w-ground" opacity="([\d.]+)"', low)
    assert ground and 0.5 <= float(ground.group(1)) < 1


def test_world_layer_ignores_drag_and_wheel():
    src = APP.read_text(encoding="utf-8").replace("\r\n", "\n")
    down = src[src.index("  function gripDown("):]
    down = down[: down.index("\n  }\n")]
    assert 'S.mapLayer === "world"' in down
    wheel = src[src.index("  function mapWheel("):]
    wheel = wheel[: wheel.index("\n  }\n")]
    assert 'S.mapLayer === "world"' in wheel


def test_the_tallies_read_the_scenario_sides():
    """各方佔幾處（版圖變化、看大局那一條）照劇本的幾方與顏色：四方的劇本四方都寫（以前只認官、巾、豪三個鍵，第四方是 undefined）。"""
    game = _four_sides()
    out = run(game, "return H.hudHtml(H.S.mapBase, H.S.mapState, H.S.mapState.now_week);")
    assert "#6A3D7A" in out and "魏 <b>5</b>" in out and "吳 <b>6</b>" in out and "undefined" not in out


def test_the_curve_names_its_ends_from_the_rope():
    game = _game(conquest=False)
    st = game.map_state()
    rope = st["ropes"][0]
    st["ropes"][0] = {**rope, "low": "huang", "high": "guan"}  # 兩頭換過來：曲線上下寫的字跟著換
    out = webharness.run(DRIVER, {"m": server.main_view(game), "script": "return H.graphSvg(H.S.mapState, 1);",
                                  "S": {"mapBase": game.map_base(), "mapState": st}, "menxia": None, "stored": {}, "responses": {}})
    top = out.index(">官軍<")
    assert top < out.index(">黃巾<")  # 往 100 推的那一方寫在上面
