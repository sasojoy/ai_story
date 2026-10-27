"""輿圖第三版第 3 批：天下圖的網頁（輿圖簡化設計 5.1、3.3、5.6；第九章第 5、8 條）。環形版 dev/map-2 的畫法搬回真實地形。
打開輿圖第一眼是天下圖：同一張底圖換一個固定的取景（worldFit）、上面疊一層拖與縮放（企劃者 2026-10-22，tests/test_map_pan_web.py）；#mk 畫大區地面（一方一色、沒人佔一色，顏色照劇本）、
紅線（任兩方相接）、細墨線（有主與沒人佔相接）、金點、大區名與各方幾處、你；「正在翻」「激戰」疊層有資料才畫（dev/flip-1 補資料）。
點一區換到區圖那一層（第 4 批之前是現在那張可縮放的地圖）。在 node 裡跑整支 app.js（tests/webharness.py），餵伺服器真的會給的
底圖與疊層；沒有 node 就略過。"""
from __future__ import annotations

import math
import random
import re
from pathlib import Path

import pytest
import test_prologue_web

import server
import webharness
from conftest import classic_rules, real_content
from tianxia import calendar, territory
from tianxia.engine import Game
from tianxia.models import FactionDef, FactionInk
from tianxia.sqlite_world import open_world
from tianxia.state import TerritoryState

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]
# 輿圖第三版第 4 批：點一區進的是區圖（regionFit，tests/test_region_map_web.py），「天下」那一條（hudHtml）拿掉了
NAMES = ["S", "pageMap", "mapChrome", "mapxClass", "drawerHtml", "worldFit", "worldParts", "worldLabels", "worldCounts",
         "worldDrawerHtml", "regionFit", "sideInk", "timelineHtml", "chartHtml", "graphSvg", "controlAt", "textW", "worldArea"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
APP = webharness.APP  # 三個檔（main.js、map.js、app.js）接起來的那一份
CSS = Path(server.WEB) / "style.css"


def _game(content=None, faction="guan", at="yingchuan", conquest=True):
    from conquest_kit import conquest_rules

    c = content or real_content("week7")
    if conquest:
        conquest_rules(c)
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    territory.update(game.state.world, c)
    game.state.player.faction, game.state.player.location = faction, at
    return game


def run(game, script, st=None, **S):
    payload = {"m": server.main_view(game), "script": script,
               "S": {"mapBase": game.map_base(), "mapState": st or game.map_state(), **S},
               "menxia": None, "stored": {}, "responses": {}}
    return webharness.run(DRIVER, payload)


NOW = "{ k: 2.5, week: H.S.mapState.now_week, tl: false, sel: null }"


def parts(game, o=NOW, st=None, **S):
    return run(game, f"return H.worldParts(H.S.mapBase, H.S.mapState, {o});", st=st, **S)


def _group(low, cls):
    """畫好的那一組（<g class="w-front" …>…</g>）裡的字。"""
    part = low[low.index(f'class="{cls}"'):]
    return part[: part.index("</g>")]


def _expected_edges(game, st=None):
    """照疊層的控制方算：每一條邊兩邊是不同的兩方（紅線）、一邊有主一邊沒人（細墨線）各幾條。"""
    world, st = game.map_base()["world"], st or game.map_state()
    owner = {cell["id"]: st["places"][cell["id"]]["control"] for cell in world["cells"]}
    front = rim = 0
    pairs = set()
    for e in world["edges"]:
        a, b = owner.get(e["a"]) if e["a"] else None, owner.get(e["b"]) if e["b"] else None
        if a == b:
            continue
        if a and b:
            front += 1
            pairs.add(frozenset((a, b)))
        else:
            rim += 1
    return front, rim, pairs


def test_world_parts_paint_each_cell_with_its_holder():
    game = _game()
    low, _ = parts(game)
    world, st = game.map_base()["world"], game.map_state()
    assert low.count("<clipPath") == len(world["regions"]) == len(game.content.map.regions)
    for cell in world["cells"]:
        side = st["places"][cell["id"]]["control"]
        colour = next(s["soft"] for s in world["sides"] if s["id"] == side) if side else world["unheld"]
        assert re.search(rf'data-cell="{cell["id"]}" d="[^"]+" fill="{colour}"', low), cell["id"]
    assert 'fill="#9DB4D3"' in low and 'fill="#E7C778"' in low and f'fill="{world["unheld"]}"' in low  # 開季：官、巾、中立地沒人
    assert "璽" not in low and "w-seal" not in low  # 核心的「璽」是環形版的，作廢


def test_fronts_are_red_only_between_two_sides_and_ink_between_held_and_unheld():
    """真實地形的大區互不相接：前線都在同一區裡兩格之間，照那一區的輪廓裁。"""
    game = _game()
    low, _ = parts(game)
    front, rim, _ = _expected_edges(game)
    assert front >= 1 and rim >= 1
    assert _group(low, "w-front").count("<path") == front and _group(low, "w-rim").count("<path") == rim
    assert _group(low, "w-front").count('clip-path="url(#wc-') == front
    w = game.state.world
    w.territory.control["yingchuan_wilds"] = "huang"  # 潁川郊野被黃巾佔下：跟潁川郡相接的那一條是紅線
    low2, _ = parts(game)
    front2, rim2, _ = _expected_edges(game)
    assert front2 > front and _group(low2, "w-front").count("<path") == front2
    assert 'clip-path="url(#wc-yingru)"' in _group(low2, "w-front")


def test_rich_places_get_gold_dots_solid_when_held():
    game = _game()
    rich = [x for x, p in game.map_state()["places"].items() if p["rich"]]
    low, _ = parts(game)
    assert rich and low.count('class="w-rich"') == len(rich) and low.count('class="w-rich held"') == 0
    game.state.world.territory.control[rich[0]] = "guan"
    low2, _ = parts(game)
    assert low2.count('class="w-rich held"') == 1


def _lines(game, st=None):
    """照疊層算每一區的大區名底下那一行（只寫不是 0 的、寶照寫）。"""
    world, st = game.map_base()["world"], st or game.map_state()
    short = {s["id"]: s["short"] for s in world["sides"]}
    out = {}
    for r in world["regions"]:
        cells = [c["id"] for c in world["cells"] if c["region"] == r["id"]]
        n = {sd: sum(1 for x in cells if st["places"][x]["control"] == sd) for sd in st["sides"]}
        rich = sum(1 for x in cells if st["places"][x]["rich"])
        out[r["id"]] = "・".join([f"{short[sd]} {n[sd]}" for sd in st["sides"] if n[sd]] + ([f"寶 {rich}"] if rich else []))
    return out


LABELS = "return H.worldLabels(H.S.mapBase, H.S.mapState, H.controlAt(H.S.mapState, H.S.mapState.now_week), 2.5);"


def test_region_labels_show_name_and_counts_from_the_sides():
    """大區名底下只寫不是 0 的（企劃者 2026-10-20 從對比圖選乙）：照疊層算的每一區那一行一字不差（區塊表重排之後照樣成立）。"""
    game = _game()
    by = {x["id"]: x for x in run(game, LABELS)}
    want = _lines(game)
    assert {k: v["line"] for k, v in by.items()} == want and all(want.values())  # 領地爭奪開著：每一區都有東西可寫
    assert by["luoyang"]["name"] == "洛陽" and by["yingru"]["name"] == "潁川汝南"
    low, _ = parts(game)
    assert f">{by['luoyang']['line']}<" in low and ">洛陽<" in low and " 0・" not in low and "寶 0" not in low


def test_a_region_with_nothing_to_count_has_no_second_line():
    """全是 0 那一行就不畫（企劃者 2026-10-20）：地盤關著（整張沒人佔）時沒有高級資源地的大區只寫名字，框也矮一截。"""
    game = _game(content=classic_rules(real_content("week7")), conquest=False)
    by = {x["id"]: x for x in run(game, LABELS)}
    want = _lines(game)
    bare = [k for k, v in want.items() if not v]
    rich = [k for k, v in want.items() if v]
    assert bare and rich and all(by[k]["line"] == "" for k in bare) and all(by[k]["line"].startswith("寶 ") for k in rich)
    assert by[bare[0]]["h"] < by[rich[0]]["h"]
    low, _ = parts(game)
    name = low.index(f'paint-order="stroke">{by[bare[0]]["name"]}</text>')  # 大區名那一行（點擊區的 <title> 也寫大區名）
    group = low[low.rindex('<g class="w-label"', 0, name):]
    assert group[: group.index("</g>")].count("<text") == 1


# 地圖框的大小（寬 × 高）：實機量的（2026-10-21，world3.localhost 預覽、狀態列底下多一行心得提示時最矮）：375×812 → 375×624、
# 375×667 → 375×479、360×640 → 360×452、320×568 → 320×344（320 寬的狀態列折成好幾行，天下圖只剩約 0.17 倍）。收尾那一次
# （2026-10-21，world3b.localhost、翻地合進來之後）360×640 量到 360×436（狀態列折幾行跟著那一刻的字長短變），一起守
SIZES = [(375, 624), (375, 479), (360, 452), (360, 436), (320, 344)]
FIT = """
const wd = H.S.mapBase.world, v = H.worldFit({vw}, {vh}, wd.frame, 54, 58, {W}, {H});
const labels = H.worldLabels(H.S.mapBase, H.S.mapState, H.controlAt(H.S.mapState, H.S.mapState.now_week), 1 / v.s);
const scr = (x, y) => [{vw} / 2 + (x - v.cx) * v.s, {vh} / 2 + (y - v.cy) * v.s];
const boxes = labels.map((l) => {{ const [x, y] = scr(l.x - l.w / 2, l.y - l.h / 2); return [l.id, x, y, l.w * v.s, l.h * v.s]; }});
const [fx, fy] = scr(wd.frame[0], wd.frame[1]), [gx, gy] = scr(wd.frame[0] + wd.frame[2], wd.frame[1] + wd.frame[3]);
const here = H.S.mapBase.places.find((p) => p.id === H.S.mapState.here), [ux, uy] = scr(here.x, here.y);
return {{ boxes, frame: [fx, fy, gx, gy], map: [scr(0, 0)[1], scr({W}, {H})[1]], you: [ux - 10, uy - 24, 24, 34] }};
"""


@pytest.mark.parametrize("vw,vh", SIZES)
def test_region_labels_do_not_overlap_on_a_phone(vw, vh):
    """375 寬（與 360、320）：天下圖整張在地圖框裡（不橫捲），大區名框兩兩不相交、都在框裡（設計第十二章）；360 寬以上也不壓到
    你（紅點與紅旗畫在上面那一張，會蓋住字）。320 寬的天下圖只剩約 0.17 倍，五個大區名擠不開時先讓彼此、再讓你。"""
    game = _game()
    m = game.content.map
    out = run(game, FIT.format(vw=vw, vh=vh, W=m.width, H=m.height))
    fx, fy, gx, gy = out["frame"]
    assert fx >= 0 and gx <= vw and fy >= 58 - 1 and gy <= vh - 54 + 1  # 取景框整個在露出來的那一塊（不橫捲、不被抽屜蓋）
    top, bottom = out["map"]
    assert top <= 58 + 0.5 or bottom <= vh - 54 + 0.5  # 地圖比露出來的那一塊高時，上面不留一條空白的紙
    boxes = out["boxes"] + ([["你", *out["you"]]] if vw >= 360 else [])
    for i, (a, ax, ay, aw, ah) in enumerate(boxes):
        assert ax >= 0 and ax + aw <= vw, a
        for b, bx, by, bw, bh in boxes[i + 1:]:
            assert ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay, (a, b)


# FB-630、631（輿圖第三版第 4 批順手修）：實機量的地圖框（2026-10-21 map4.localhost，無頭 Chromium）——正常的天下圖（上面讓開 58、
# 底下讓開收著的抽屜 54）、版圖變化開著（地圖框縮到 320 高的抽屜上面，上面只讓開 36、底下不讓）、橫放的手機
FRAMES = {
    "375x812": (375, 604, 58, 54), "375x667": (375, 459, 58, 54), "360x640": (360, 416, 58, 54), "320x568": (320, 323, 58, 54),
    "375x812-tl": (375, 284, 36, 0), "375x667-tl": (375, 207, 36, 0), "360x640-tl": (360, 187, 36, 0), "320x568-tl": (320, 145, 36, 0),
    "667x375": (667, 187, 58, 54), "568x320": (568, 132, 58, 54), "667x375-tl": (667, 84, 36, 0), "568x320-tl": (568, 59, 36, 0),
    # 第 3 批量的四種（狀態列折幾行跟著那一刻的字長短變）
    "375x812b": (375, 624, 58, 54), "360x640b": (360, 452, 58, 54), "360x640c": (360, 436, 58, 54), "320x568b": (320, 344, 58, 54),
}
LAYOUT = """
const wd = H.S.mapBase.world, v = H.worldFit({vw}, {vh}, wd.frame, {pad}, {top}, {W}, {H}), area = H.worldArea(v, {vw}, {vh}, {top}, {pad});
const labels = H.worldLabels(H.S.mapBase, H.S.mapState, H.controlAt(H.S.mapState, H.S.mapState.now_week), 1 / v.s, area);
const scr = (x, y) => [{vw} / 2 + (x - v.cx) * v.s, {vh} / 2 + (y - v.cy) * v.s];
const boxes = labels.map((l) => {{ const [x, y] = scr(l.x - l.w / 2, l.y - l.h / 2); return [l.id, x, y, l.w * v.s, l.h * v.s, l.line]; }});
const dots = H.S.mapBase.places.filter((p) => H.S.mapState.places[p.id] && H.S.mapState.places[p.id].rich).map((p) => {{ const [x, y] = scr(p.x, p.y); return [p.id, x - 5, y - 5, 10, 10]; }});
return {{ boxes, dots }};
"""


def _layout(game, key):
    vw, vh, top, pad = FRAMES[key]
    m = game.content.map
    return run(game, LAYOUT.format(vw=vw, vh=vh, top=top, pad=pad, W=m.width, H=m.height))


def _hit(a, b):
    return not (a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1] or a[2] + a[4] <= b[2] or b[2] + b[4] <= a[2])


@pytest.mark.parametrize("key", sorted(FRAMES))
def test_fb630_fb631_region_names_never_overlap_and_leave_the_gold_dots(key):
    """FB-631：大區名在小螢幕（版圖變化開著、320 寬、橫放）互相壓住——名字可以擺到取景框外面露出來的空處（worldArea；svg overflow 照畫）、
    挪的範圍大一點，大區名兩兩不相交、都在畫面裡、底下那一行數字照寫；FB-630：名字讓開高級資源地的金點。"""
    vw, vh, top, pad = FRAMES[key]
    out = _layout(_game(), key)
    boxes = out["boxes"]
    roomy = vh - top - pad >= 60  # 568×320 橫放：上面那一排與收著的抽屜之間只剩 20px 上下，名字只能疊在那一排上（照樣不互壓）
    for i, a in enumerate(boxes):
        assert a[1] >= 0 and a[1] + a[3] <= vw, (key, a)
        assert not roomy or (a[2] >= top - 0.5 and a[2] + a[4] <= vh - pad + 0.5), (key, a)
        assert a[5], (key, a[0])  # 底下那一行數字照寫（擺不下才收：這幾種都擺得下）
        for b in boxes[i + 1:]:
            assert not _hit(a, b), (key, a[0], b[0])
        for d in out["dots"]:
            assert not _hit(a, d), (key, a[0], d[0])


def test_fb631_four_sides_on_a_small_phone():
    """FB-631：四方劇本那一行比兩方長三成（「官 2・巾 6・魏 4・吳 3・寶 2」），320×568 正常畫面照樣不互壓。"""
    game = _four_sides()
    for key in ("320x568", "320x568b", "360x640", "375x667-tl"):
        out = _layout(game, key)
        boxes = out["boxes"]
        assert any("魏" in b[5] for b in boxes)
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                assert not _hit(a, b), (key, a[0], b[0])


def test_world_svg_draws_outside_its_viewbox():
    """名字擺到地圖外面的空處要畫得出來（FB-631）：底圖與上面那一張 svg 不裁在自己的 viewBox（框本身照舊裁在 .map-wrap）。"""
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    assert re.search(r"\.map-wrap \.tx-world-map > svg \{[^}]*overflow: visible", css)
    assert re.search(r"\.mapx \.map-wrap \{[^}]*overflow: clip", css)


def test_tapping_a_region_enters_it():
    game = _game()
    low, _ = parts(game)
    hits = re.findall(r'data-act="world-region" data-id="([a-z]+)"', low)
    assert sorted(hits) == sorted(r.id for r in game.content.map.regions)


def test_region_fit_frames_that_regions_places():
    """點一區進區圖（第 4 批：regionFit 固定取景，不再是可以縮放的那一張的替身）：那一區每一個地點都在畫面裡、整區不切掉。"""
    game = _game()
    for r in game.content.map.regions:
        out = run(game, f"return H.regionFit(H.S.mapBase, '{r.id}', 375, 624);")
        for p in (x for x in game.map_base()["places"] if x["region"] == r.id):
            x = 375 / 2 + (p["x"] - out["cx"]) * out["s"]
            y = 624 / 2 + (p["y"] - out["cy"]) * out["s"]
            assert 0 <= x <= 375 and 58 <= y <= 624 - 54, (r.id, p["id"])


def test_the_world_drawer_line_says_where_you_are_and_offers_to_enter():
    game = _game()
    out = run(game, "return H.worldDrawerHtml(H.S.mapBase, H.S.mapState);", mapDrawer="min")
    assert "你在 <b>潁川汝南</b>・潁川郡（陽翟）" in out and 'data-act="world-enter"' in out and "進入此區" in out
    assert 'data-act="map-open"' in out and "誰佔著" not in out
    full = run(game, "return H.worldDrawerHtml(H.S.mapBase, H.S.mapState);", mapDrawer="half")
    assert 'class="m-line"' in full and "此地的對手" in full and 'data-act="world-enter"' in full  # 拉開：你腳下這一處的卡（placeCard）


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
    flip = next(e for e in changed if e["id"] == "guan_camp")
    assert flip["to"] == "huang" and flip["from"] not in (None, "huang")
    soft = {s["id"]: s["soft"] for s in game.map_base()["world"]["sides"]}
    week1, _ = parts(game, "{ k: 2.5, week: 1, tl: true, sel: null }")
    week2, high2 = parts(game, "{ k: 2.5, week: 2, tl: true, sel: null }")
    assert re.search(rf'data-cell="guan_camp" d="[^"]+" fill="{soft[flip["from"]]}"', week1)
    assert re.search(rf'data-cell="guan_camp" d="[^"]+" fill="{soft["huang"]}"', week2)
    assert high2.count('class="pulse"') == len(changed) + 1  # 易手的那幾處閃一圈，加上你的那一圈


def _four_sides():
    """四方的測試劇本（設計 3.3、第十二章）：官軍、黃巾之外加兩方（各自的顏色）；潁川汝南照方位切成四塊、一方一塊，其餘四區各一方。"""
    c = real_content("week7")
    c.scenario.factions = [f for f in c.scenario.factions if f.id != "haoqiang"] + [
        FactionDef(id="wei", name="魏", ink=FactionInk(color="#6A3D7A", soft="#C3A6CC", short="魏", label="魏")),
        FactionDef(id="wu", name="吳", ink=FactionInk(color="#2E7D5B", soft="#9FD1B8", short="吳", label="吳")),
    ]
    c.scenario.territory.lines = {}
    game = _game(content=c, conquest=False)
    sides = ["guan", "huang", "wei", "wu"]
    world = game.map_base()["world"]
    middle = [cell["id"] for cell in world["cells"] if cell["region"] == "yingru"]
    cx = sum(c.locations[x].x for x in middle) / len(middle)
    cy = sum(c.locations[x].y for x in middle) / len(middle)

    def quarter(x):  # 照方位分四塊（右、下、左、上）
        angle = math.atan2(c.locations[x].y - cy, c.locations[x].x - cx)
        return sides[int(((angle + math.pi / 4) % (2 * math.pi)) // (math.pi / 2))]

    owners = {"luoyang": "guan", "youzhou": "huang", "jizhou": "wei", "nanyang": "wu"}
    control = {cell["id"]: quarter(cell["id"]) if cell["region"] == "yingru" else owners[cell["region"]] for cell in world["cells"]}
    game.state.world.territory = TerritoryState(control=control)
    return game


def test_three_and_four_sides_each_get_a_colour_and_every_touching_pair_a_front():
    game = _four_sides()
    st = game.map_state()
    assert st["sides"] == ["guan", "huang", "wei", "wu"]
    low, _ = parts(game)
    for soft in ("#9DB4D3", "#E7C778", "#C3A6CC", "#9FD1B8"):
        assert f'fill="{soft}"' in low
    front, _, pairs = _expected_edges(game)
    assert len(pairs) >= 4 and {s for p in pairs for s in p} == {"guan", "huang", "wei", "wu"}
    assert _group(low, "w-front").count("<path") == front  # 每兩方相接的每一條邊都是紅線
    by = {x["id"]: x for x in run(game, LABELS)}
    assert by["jizhou"]["line"].startswith("魏 ") and by["nanyang"]["line"].startswith("吳 ")
    assert all(f"{s} " in by["yingru"]["line"] for s in ("官", "巾", "魏", "吳"))
    assert run(game, "return [H.sideInk('wei').color, H.sideInk('wu').name];") == ["#6A3D7A", "吳"]


def test_tug_and_melee_draw_only_with_data():
    """「正在翻」「激戰」的掛鉤（計畫 1.3；資料由翻地規則那一批 dev/flip-1 補）：疊層沒有 tug／melee 就一筆都不畫；
    有了，攻方的顏色照進度泛進那一格（斜紋，照那一區的輪廓裁），激戰的那一格一圈紅光。不寫死陣營：顏色照 sideInk。"""
    game = _game()
    low, _ = parts(game)
    assert "w-tug" not in low and "w-melee" not in low and "<pattern" not in low
    st = game.map_state()
    st["places"]["yingchuan"]["tug"] = {"huang": 60, "haoqiang": 20}  # 進度最高的那一方的顏色泛進來六成
    st["places"]["changshe"]["melee"] = True
    st["places"]["guan_camp"]["tug"] = {}
    low2, _ = parts(game, st=st)
    tug = re.findall(r'<path class="w-tug" data-cell="([a-z_]+)" d="[^"]+" fill="url\(#wt-([a-z]+)\)" opacity="([\d.]+)"', low2)
    assert [(a, b) for a, b, _ in tug] == [("yingchuan", "huang")]
    assert abs(float(tug[0][2]) - 0.6 * float(re.search(r"WORLD_TUG_MAX = ([\d.]+)", APP.read_text(encoding="utf-8")).group(1))) < 0.01
    assert re.search(r'<pattern id="wt-huang"[^>]*>.*?stroke="#B9821A"', low2)  # 斜紋的顏色照劇本（黃巾的 color）
    assert re.search(r'<g clip-path="url\(#wc-yingru\)"><path class="w-tug"', low2)
    assert len(re.findall(r'class="w-melee" data-cell="changshe"', low2)) == 1 and "w-melee" not in low


def test_real_flip_data_draws_tug_melee_and_cooling():
    """收尾：翻地那一份資料真的接上了（mapdata.flip_marks 照 conquest.block_view 換名字）——兩塊正在翻照進度最高的那一方上斜紋、
    激戰那一格一圈紅、剛易手的那一格【開發定】換成新主人的淡色（tint）＋一圈新主人顏色的虛線，不閃。版圖變化看以前的週都不畫。"""
    from test_world_map import flipping

    game = flipping(_game())
    world = game.map_base()["world"]
    ink = {s["id"]: s for s in world["sides"]}
    low, _ = parts(game)
    tug = re.findall(r'<path class="w-tug" data-cell="([a-z_]+)" d="[^"]+" fill="url\(#wt-([a-z]+)\)" opacity="([\d.]+)"', low)
    tug_max = float(re.search(r"WORLD_TUG_MAX = ([\d.]+)", APP.read_text(encoding="utf-8")).group(1))
    assert sorted((a, b) for a, b, _ in tug) == [("runan_wilds", "guan"), ("yingchuan_wilds", "huang")]
    assert {a: float(v) for a, _, v in tug} == pytest.approx({"runan_wilds": 0.6 * tug_max, "yingchuan_wilds": 0.3 * tug_max}, abs=0.01)
    assert re.findall(r'class="w-melee" data-cell="([a-z_]+)"', low) == ["runan"]
    cool = re.findall(r'<path class="w-cool" data-cell="([a-z_]+)" d="[^"]+" fill="none" stroke="([^"]+)"[^>]*stroke-dasharray="[\d.]+ [\d.]+"', low)
    assert cool == [("hilltop_wilds", ink["guan"]["color"])]
    assert re.search(rf'data-cell="hilltop_wilds" d="[^"]+" fill="{ink["guan"]["tint"]}"', low)  # 地面是官軍的淡色，不是 soft
    assert re.search(rf'data-cell="yingchuan_wilds" d="[^"]+" fill="{ink["guan"]["soft"]}"', low)  # 正在被翻的照守方的地面
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    assert ".w-cool" not in css  # 冷卻不閃
    # 前線照樣畫在冷卻的虛線上面
    assert low.index('class="w-cool"') < low.index('class="w-front"')
    st = {**game.map_state(), "now_week": 2}  # 當成第 2 週在看第 1 週的版圖
    old, _ = parts(game, "{ k: 2.5, week: 1, tl: true, sel: null }", st=st)
    assert "data-cell=" in old and "w-tug" not in old and "w-melee" not in old and "w-cool" not in old


def test_conquest_off_draws_no_tug_melee_or_cooling():
    """領地爭奪關著的季：疊層沒有那三個鍵，天下圖一筆都不畫（舊拔河照控制方上色）。"""
    game = _game(conquest=False)
    low, _ = parts(game)
    assert "w-tug" not in low and "w-melee" not in low and "w-cool" not in low and "<pattern" not in low


def test_melee_blinks_but_not_for_reduced_motion():
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    assert re.search(r"\.w-melee\s*\{[^}]*animation:", css)
    reduced = [m for m in re.finditer(r"@media \(prefers-reduced-motion: reduce\)\s*\{", css)]
    assert any(".w-melee" in css[m.end(): m.end() + 600] for m in reduced)


def test_page_map_opens_on_the_world_with_its_top_row():
    # 減法季整合設計第七章起打開輿圖第一眼是第一層（S.mapLayer "near"，tests/test_map_layers_web.py）；天下圖是第四層，按「天下」才到
    page, layer = run(_game(), "return [H.pageMap(), H.S.mapLayer];", mapLayer="world")
    assert layer == "world" and 'class="mapx world' in page
    top = page[page.index('class="w-top"'):]
    top = top[: top.index("</div>")]
    assert top.index("天下") < top.index("找地點") < top.index("版圖")
    assert 'data-act="map-timeline"' in top and 'data-act="map-search"' in top


def test_the_region_layer_has_a_way_back_to_the_world():
    page = run(_game(), "return H.pageMap();", mapLayer="region", mapRegion="yingru")
    head = page[page.index('class="mapx'):page.index(">", page.index('class="mapx'))]
    assert "world" not in head and "region" in head
    row = page[page.index('class="r-top"'):]
    row = row[: row.index("</div>")]
    assert 'data-act="map-world"' in row and "天下" in row


def test_the_roads_show_faintly_through_the_world_ground():
    """天下圖的路淡淡透上來（企劃者 2026-10-20 從對比圖選乙）：路照舊在底圖裡、樣子不變（官道雙線、路虛線、山路點線），天下圖那一層不藏它；
    地面不是全不透明的，底下的路與山水看得到。輿圖第三版第 4 批起路包成一組（.tx-roads）、不烤進點陣那張圖：區圖照 CSS 換成一種淡實線
    （設計 5.2），天下圖不套那幾條（只在 .mapx.region 底下）。"""
    svg = _game().map_base()["svg"]
    roads = svg[svg.index('<g class="tx-roads">'):]
    roads = roads[: roads.index("</g>")]
    assert roads.count(" Q") > 20 and 'stroke-dasharray="5 4"' in roads and 'class="rd-core"' in roads  # 路是底圖裡的二次曲線，照舊的畫法
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    assert all(m.group(0).startswith(".mapx.region") for m in re.finditer(r"[^\n{}]*\.tx-roads[^{]*", css))
    low, _ = parts(_game())
    ground = re.search(r'class="w-ground" opacity="([\d.]+)"', low)
    assert ground and 0.5 <= float(ground.group(1)) < 1


def test_both_layers_drag_and_zoom():
    """企劃者 2026-10-22 改：兩張圖都能拖、能捏合縮放（推翻設計第五章「不自由縮放」那一半；第 4 批到這一天以前這一條守的是手勢、滾輪、
    縮放鈕整套拿掉）。兩層照舊；縮放鈕照舊沒有。手勢本身的行為在 tests/test_map_pan_web.py。"""
    src = APP.read_text(encoding="utf-8")
    for name in ("function panDown(", "function panWheel(", 'addEventListener("wheel", panWheel, { passive: false })', "PAN_MAX = { world: 4, region: 3 }"):
        assert name in src, name
    assert "function mapZoom(" not in src and "map-ctl" not in src  # 縮放鈕（右上角那一欄）照舊拿掉


def test_no_two_sides_or_side_names_are_hardcoded_in_the_world_map_code():
    """設計 3.3：天下圖那一段不寫死陣營 id、陣營名與藍黃灰（顏色一律 sideInk、地面沒人佔照底圖的 unheld）。"""
    src = APP.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = src.index("  // ── 天下圖")
    block = src[start: src.index("  // ── 底圖烤成一張圖", start)]
    for word in ('"guan"', '"huang"', '"haoqiang"', "官軍", "黃巾", "豪強", "MAP_SIDES", "#9DB4D3", "#E7C778", "#D2CBBC"):
        assert word not in block, word


def test_the_curve_names_its_ends_from_the_rope():
    game = _game(conquest=False)
    st = game.map_state()
    st["ropes"][0] = {**st["ropes"][0], "low": "huang", "high": "guan"}  # 兩頭換過來：曲線上下寫的字跟著換
    out = run(game, "return H.graphSvg(H.S.mapState, 1);", st=st)
    assert out.index(">官軍<") < out.index(">黃巾<")  # 往 100 推的那一方寫在上面
