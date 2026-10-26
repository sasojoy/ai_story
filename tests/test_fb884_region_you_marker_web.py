"""FB-884（企劃者 2026-10-26 決定：「全區看別區時也畫出你站的位置（朱圈），跟本區一樣」）：全區選甲之後別區拖得過來、點得到，
可是你站的那一處在別區時，畫面上只有一個淡墨小圖，沒有朱圈與旗，從你出發的金路線起點也是個淡墨小圖。

現在：你站在別區，那一處不畫成淡墨小圖（不跟朱圈疊成兩個），照本區的小圖畫（g.r-here，控制方的顏色）、朱圈與旗在上面那一張（跟本區同一份）；
朱圈的點擊區（rect.r-hit-you）疊在名字框、出口與別處小圖的點擊區上面，點了開你腳下那一處的卡（FB-877 的規則）。在路上時畫在路上，不看取景框。
本區的畫法逐位元組不變（test_fb876_region_neighbours_web 的本區比對）；天下圖、第一層不動。

在 node 裡跑整支 app.js（tests/webharness.py）；假地圖框照 tests/test_map_pan_web.py。沒有 node 就略過。"""
from __future__ import annotations

import re

import pytest
import test_prologue_web
from test_fb876_region_neighbours_web import FRAMES, PARTS, _hits, _parts, _top
from test_map_pan_web import READY, _dom, _game

import server
import webharness

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]
NAMES = ["S", "applyMapView", "panWire", "panBox", "enterRegion", "regionPick", "curView", "regionFit", "regionParts", "drawMarks", "drawSel",
         "homeFar", "placeCard", "PAN_MAX"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
# 同一個取景（home 那一區的）畫幾個不同的區：上面那一張只看你在哪、取景的倍率，跟畫的是哪一區無關
SAME_VIEW = """
const out = [];
for (const c of H.S.cases) {
  H.S.mapState = c.st;
  const v = H.regionFit(H.S.mapBase, c.home, c.vw, c.vh, 58, 54, 270);
  out.push(c.rids.map((rid) => H.regionParts(H.S.mapBase, c.st, { v, vw: c.vw, vh: c.vh, rid, wash: false })));
}
return out;
"""
RING = re.compile(r'<circle class="r-you" cx="([-\d.]+)" cy="([-\d.]+)" r="([-\d.]+)" fill="none"')
DOT = re.compile(r'<circle class="r-you" cx="([-\d.]+)" cy="([-\d.]+)" r="([-\d.]+)" fill="#')


def run(game, script, vw=375, vh=604, layer="region", region="yingru", **S):
    payload = {"m": server.main_view(game), "script": _dom(vw, vh) + script,
               "S": {"mapBase": game.map_base(), "mapState": game.map_state(), "mapLayer": layer, "mapRegion": region, "tab": "map", **S},
               "menxia": None, "stored": {}, "responses": {}}
    return webharness.run(DRIVER, payload)


def _where(game, at):
    game.state.player.location = at
    st, base = game.map_state(), game.map_base()
    region_of = {p["id"]: p["region"] for p in base["places"]}
    xy = {p["id"]: (p["x"], p["y"]) for p in base["places"]}
    return st, base, region_of[at], xy[at]


def test_another_region_draws_your_ring_flag_and_pulse_just_like_your_own():
    """你站在別區：同一個取景畫你那一區與別的區，上面那一張一字不差——朱圈（半徑 17 的空心圈）、跳的圈、旗，都在你腳下那一處。
    修前別區的上面那一張是空的。"""
    game = _game("yingchuan")
    cases = []
    for at in ("yingchuan", "luoyang_road", "zhuo_county"):
        st, base, home, _ = _where(game, at)
        others = [r["id"] for r in base["regions"] if r["id"] != home]
        cases.append({"st": st, "home": home, "rids": [home, *others], "vw": 375, "vh": 604})
    seen = 0
    for case, parts in zip(cases, run(game, SAME_VIEW, cases=cases)):
        at_home = parts[0][1]
        assert at_home.count('class="r-you"') == 1 and at_home.count('class="pulse"') == 1 and "<path" in at_home
        for rid, (_, high) in zip(case["rids"][1:], parts[1:]):
            assert high == at_home, f"{case['home']} → {rid}"
            seen += 1
    assert seen == 3 * 4


def test_your_place_is_drawn_once_not_as_a_faint_twin_under_the_ring():
    """你站的那一處不在這一區：下面那一張裡它是一個 g.r-here（照本區的小圖畫，控制方的顏色）加朱圈的點擊區，不再有淡墨的 g.r-faint 疊在朱圈底下；
    別的別區地點照舊是淡墨小圖。你站在這一區（本區）時沒有 g.r-here。"""
    game = _game("yingchuan")
    st, base, home, _ = _where(game, "luoyang_road")
    cases = [{"st": st, "vw": 375, "vh": 604, "rid": r["id"], "wash": False} for r in base["regions"]]
    seen = 0
    for case, (low, high) in zip(cases, _parts(game, cases)):
        faint = set(re.findall(r'<g class="r-faint" data-act="region-place" data-id="([^"]+)"', low))
        if case["rid"] == home:
            assert "r-here" not in low and "r-hit-you" not in low
            continue
        assert re.findall(r'<g class="r-here" data-act="region-place" data-id="([^"]+)"', low) == ["luoyang_road"]
        assert "luoyang_road" not in faint
        assert re.findall(r'<rect class="r-hit-you" data-act="region-place" data-id="([^"]+)"', low) == ["luoyang_road"]
        assert 'r-icon" data-act="region-place" data-id="luoyang_road"' not in low
        others = {p["id"] for p in base["places"] if p["region"] != case["rid"] and p["id"] in st["places"] and p["id"] != "luoyang_road"}
        assert faint == others, case["rid"]
        assert RING.search(high), case["rid"]
        seen += 1
    assert seen == len(base["regions"]) - 1


def test_the_ring_taps_open_your_place_and_nothing_eats_them():
    """五區 × 三處站位 × 幾種地圖框：照畫出來的 SVG 疊點擊區，朱圈的中心與圈上、圈裡的幾個點都落在 r-hit-you（你腳下那一處），
    不會被別區小圖、名字框、出口、點空白吃掉（FB-877 的規則）。"""
    game = _game("yingchuan")
    cases, meta = [], []
    for at in ("yingchuan", "luoyang_road", "zhuo_county"):
        st, base, home, (hx, hy) = _where(game, at)
        for r in base["regions"]:
            if r["id"] != home:
                for vw, vh in FRAMES:
                    cases.append({"st": st, "vw": vw, "vh": vh, "rid": r["id"], "wash": False})
                    meta.append((at, hx, hy))
    seen = 0
    for case, (at, hx, hy), (low, high) in zip(cases, meta, _parts(game, cases)):
        ring = RING.search(high)
        k = float(ring.group(3)) / 17  # 取景的倍率反算（半徑 17×k）
        hits, _ = _hits(low)
        for dx, dy in [(0, 0), (12, 0), (-12, 0), (0, 12), (0, -12), (8, 8), (-8, -8)]:
            x, y = hx + dx * k, hy + dy * k
            assert _top(hits, x, y) == ("r-hit-you", at), f"{at} 看 {case['rid']} {case['vw']}×{case['vh']}：({dx}, {dy}) 點到 {_top(hits, x, y)}"
            seen += 1
    assert seen == 7 * 3 * 4 * len(FRAMES)


def test_the_ring_never_eats_another_icons_tap_wherever_you_stand():
    """你站每一處（疊層裡有的全部）× 每個別區 × 三種地圖框：每一個小圖（本區的、別區的淡墨小圖、你腳下那一處）的中心點下去都選到它自己——
    朱圈的點擊區比小圖的大，不准把鄰近的小圖吃掉。"""
    game = _game("yingchuan")
    base = game.map_base()
    region_of = {p["id"]: p["region"] for p in base["places"]}
    cases, at_of = [], []
    for p in base["places"]:
        game.state.player.location = p["id"]
        st = game.map_state()
        if p["id"] not in st["places"]:
            continue
        for r in base["regions"]:
            if r["id"] != region_of[p["id"]]:
                for vw, vh in FRAMES:
                    cases.append({"st": st, "vw": vw, "vh": vh, "rid": r["id"], "wash": False})
                    at_of.append(p["id"])
    seen = 0
    for case, at, (low, _) in zip(cases, at_of, _parts(game, cases)):
        hits, icons = _hits(low)
        assert at in icons  # 你腳下那一處也是一個小圖
        for pid, (x, y) in icons.items():
            assert _top(hits, x, y)[1] == pid, f"站 {at} 看 {case['rid']} {case['vw']}×{case['vh']}：點 {pid} 選到 {_top(hits, x, y)}"
            seen += 1
    assert seen > 15000


def test_a_name_frame_under_the_ring_does_not_eat_the_tap():
    """你腳下那一處（不在這一區）擺到這一區某個名字框的正中（同 FB-876 的別區小圖疊名字框）：點那一點選到你腳下那一處；
    點名字框其餘地方照舊是它自己。"""
    game = _game("yingchuan")
    st, base, home, _ = _where(game, "luoyang_road")
    case = {"st": st, "vw": 375, "vh": 604, "rid": "yingru", "wash": False}
    low = _parts(game, [case])[0][0]
    label = re.search(r'<g class="r-label" data-act="region-place" data-id="([^"]+)"[^>]*>(?:<rect class="r-fight[^>]*/>)?'
                      r'<rect class="r-frame" x="([-\d.]+)" y="([-\d.]+)" width="([-\d.]+)" height="([-\d.]+)"', low)
    pid, x, y, w, h = label.group(1), *(float(n) for n in label.groups()[1:])
    cx, cy = x + w / 2, y + h / 2
    moved = dict(base, places=[dict(p, x=cx, y=cy) if p["id"] == "luoyang_road" else p for p in base["places"]])
    out = run(game, PARTS, cases=[case], mapBase=moved)[0]
    hits, _ = _hits(out[0])
    assert out[0].count(f'<g class="r-label" data-act="region-place" data-id="{pid}"') == 1  # 名字框照舊在
    assert _top(hits, cx, cy) == ("r-hit-you", "luoyang_road")
    assert _top(hits, x + 1, y + 1) == ("r-label", pid)  # 名字框的角（朱圈外面）照舊是它自己


def test_tapping_the_ring_opens_your_card_and_keeps_the_region():
    """點朱圈（region-place 你腳下那一處）：開你腳下那一處的卡，抽屜半開、地圖不動，全區與上面那一排的大區名照舊是看的這一區。"""
    out = run(_game("yingchuan"), READY + """
const t0 = world.style.transform;
const opened = click('region-place', 'yingchuan');
return { opened, sel: H.S.mapSel, mode: H.S.mapMode, drawer: H.S.mapDrawer, layer: H.S.mapLayer, region: H.S.mapRegion,
         still: world.style.transform === t0, card: H.placeCard(H.S.mapBase, H.S.mapState, H.S.mapSel) };
""", region="luoyang")
    assert out["opened"] and (out["sel"], out["mode"], out["drawer"]) == ("yingchuan", "place", "peek")
    assert (out["layer"], out["region"], out["still"]) == ("region", "luoyang", True)
    assert "潁川郡" in out["card"]


def test_the_gold_route_starts_at_the_ring():
    """全區看洛陽、你站潁川郡，點洛陽的一處：從你出發的金路線（m-route）起點就是朱圈的圓心（修前那裡只有一個淡墨小圖，沒有朱圈）。"""
    out = run(_game("yingchuan"), READY + """
H.S.mapSel = 'luoyang_road'; H.S.mapMode = 'place';
H.drawMarks();
return { top: els.mkt.innerHTML, sel: els.msel.innerHTML };
""", region="luoyang")
    ring = RING.search(out["top"])
    assert ring, "全區看別區的上面那一張沒有朱圈"
    route = re.search(r'class="m-route" d="M([-\d.]+),([-\d.]+)', out["sel"])
    assert route, "沒有金路線"
    assert (float(route.group(1)), float(route.group(2))) == (float(ring.group(1)), float(ring.group(2)))


def test_dragging_to_where_you_stand_shows_you_there():
    """QA 的重現：站潁川郡、全區看洛陽，往東南拖到潁川一帶——朱圈在你腳下那一處（畫面裡看得到），旗與跳的圈跟著。"""
    out = run(_game("yingchuan"), READY + """
const step = (x, y) => { move(1, x, y); flush(); };
down(1, 200, 200); step(150, 300); step(60, 420); up(1, 60, 420); flush();
const here = H.S.mapBase.places.find((p) => p.id === 'yingchuan');
return { screen: toScreen(here.x, here.y), pan: pan(), top: els.mkt.innerHTML, here: [here.x, here.y] };
""", region="luoyang")
    ring = RING.search(out["top"])
    assert ring and (float(ring.group(1)), float(ring.group(2))) == tuple(out["here"])
    x, y = out["screen"]
    assert 0 <= x <= 375 and 58 <= y <= 604  # 拖過去之後朱圈真的在地圖框裡
    assert 'class="pulse"' in out["top"] and "<path" in out["top"]


def test_on_the_road_you_are_drawn_where_you_are_whatever_region_is_shown():
    """在路上（journey）：畫在路上那一點（小圓點），不看取景框、也不看是哪一區——看別區也畫（修前取景框外不畫）。"""
    game = _game("yingchuan")
    st, base, home, (hx, hy) = _where(game, "yingchuan")
    luo = next(p for p in base["places"] if p["region"] == "luoyang")
    jst = dict(st, journey={"x": luo["x"], "y": luo["y"], "to": luo["id"]})
    cases = [{"st": jst, "vw": 375, "vh": 604, "rid": rid, "wash": False} for rid in ("yingru", "luoyang")]
    for case, (low, high) in zip(cases, _parts(game, cases)):
        dot = DOT.search(high)
        assert dot and (float(dot.group(1)), float(dot.group(2))) == (luo["x"], luo["y"]), case["rid"]
        assert "r-here" not in low and "r-hit-you" not in low  # 在路上沒有「腳下那一處」
        assert RING.search(high) is None


def test_the_world_map_and_the_near_layer_do_not_change():
    """天下圖、第一層不動：這一批只動 regionParts（全區）——同一份 mapBase、mapState，兩層畫出來沒有 r-here、r-hit-you。"""
    out = run(_game("luoyang_road"), READY + """
const v = H.curView();
return { layer: H.S.mapLayer, top: els.mkt.innerHTML };
""", layer="near")
    assert "r-here" not in out["top"] and "r-hit-you" not in out["top"]
