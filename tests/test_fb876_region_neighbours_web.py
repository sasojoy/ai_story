"""FB-876 全區那一層（企劃者 2026-10-26 選甲）：全區也拖得過區界——拖的範圍照整張圖（同第一層這次的修法），取景框外不再蓋紙，
別區的地點畫成第一層那種淡墨小圖（g.r-faint：點得到、不寫名，點了開那一處的卡，大區名與全區照舊是這一區）；別區小圖的點擊區（rect.r-hit）
疊在本區的名字框、出口上面（FB-877 的規則：名字不吃別處小圖的點擊）。本區的畫法、名字、點擊一個像素都不變（跟選甲之前那一版逐位元組比）。
天下圖不動。

在 node 裡跑整支 app.js（tests/webharness.py）；假地圖框、手勢照 tests/test_map_pan_web.py。沒有 node 就略過。"""
from __future__ import annotations

import re
import subprocess

import pytest
import test_prologue_web
from test_map_pan_web import READY, _dom, _game

import server
import webharness

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]
NAMES = ["S", "applyMapView", "panWire", "panBox", "enterRegion", "regionPick", "curView", "regionFit", "regionParts", "regionTopHtml",
         "placeCard", "PAN_MAX"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
BEFORE = "9158cb64"  # 選甲之前那一版（dev/map-6，FB-876 第一層、FB-877、FB-878 都在）：本區那一段跟它逐位元組比
FRAMES = [(375, 604), (360, 560), (900, 640)]
EDGES = """
const edges = () => { const f = H.S.mapBase.world.frame; return [...toScreen(f[0], f[1]), ...toScreen(f[0] + f[2], f[1] + f[3])]; };
const open = () => H.panBox(H.curView(), VW, VH).a;
const dragBy = (dx, dy) => { down(1, 180, 300); move(1, 180 + dx / 2, 300 + dy / 2); flush(); move(1, 180 + dx, 300 + dy); flush(); up(1, 180 + dx, 300 + dy); flush(); };
"""
PARTS = """
const out = [];
for (const c of H.S.cases) {
  H.S.mapState = c.st;
  const desk = c.vw >= 900, v = H.regionFit(H.S.mapBase, c.rid, c.vw, c.vh, 58, desk ? 0 : 54, desk ? 0 : 270);
  out.push(v ? H.regionParts(H.S.mapBase, c.st, { v, vw: c.vw, vh: c.vh, rid: c.rid, wash: c.wash }) : null);
}
return out;
"""


def run(game, script, vw=375, vh=604, layer="region", region="yingru", app=None, **S):
    payload = {"m": server.main_view(game), "script": _dom(vw, vh) + script,
               "S": {"mapBase": game.map_base(), "mapState": game.map_state(), "mapLayer": layer, "mapRegion": region, "tab": "map", **S},
               "menxia": None, "stored": {}, "responses": {}}
    if app is not None:
        payload["app"] = str(app)
    return webharness.run(DRIVER, payload)


# ── 拖 ──

def test_the_region_map_drags_out_of_its_region_at_one_times():
    """站潁川郡、全區潁川汝南，1 倍往右拖 300（看西邊的洛陽、南陽）：地圖跟著走（修前這一區的取景框比露出來的那一塊小，一點都不動），
    這一區的取景框左緣離開框邊，拖到整張圖的西緣停住。上面那一排照舊是潁川汝南。"""
    out = run(_game("yingchuan"), READY + EDGES + """
const r0 = regionBox();
dragBy(300, 0);
return { pan: pan(), r0, r1: regionBox(), whole: edges(), open: open(), layer: H.S.mapLayer, region: H.S.mapRegion,
         top: /<option value="([a-z_]+)" selected>/.exec(H.regionTopHtml())[1] };
""")
    assert out["pan"]["x"] > 150 and out["r1"][0] - out["r0"][0] == pytest.approx(out["pan"]["x"], abs=0.01)
    assert out["whole"][0] == pytest.approx(out["open"][0])  # 停在整張圖的西緣（潁川汝南西邊只剩這麼寬）
    assert (out["layer"], out["region"], out["top"]) == ("region", "yingru", "yingru")


@pytest.mark.parametrize(("dx", "dy", "side"), [(3000, 0, 0), (-3000, 0, 2), (0, 3000, 1), (0, -3000, 3)])
def test_dragging_hard_stops_at_the_edge_of_the_whole_map(dx, dy, side):
    """全區洛陽（在整張圖中間）放大 2 倍往一個方向拖到底：停在整張圖的那一邊，不是這一區的取景框；整張不會拖出框外。"""
    out = run(_game("yingchuan"), READY + EDGES + f"""
zoomTo(2);
dragBy({dx}, {dy});
return {{ whole: edges(), region: regionBox(), open: open() }};
""", region="luoyang")
    e, a, r = out["whole"], out["open"], out["region"]
    assert e[side] == pytest.approx(a[side], abs=1e-6)
    assert e[0] <= a[0] + 1e-6 and e[1] <= a[1] + 1e-6 and e[2] >= a[2] - 1e-6 and e[3] >= a[3] - 1e-6
    inside = [r[0] >= a[0] - 1e-6, r[1] >= a[1] - 1e-6, r[2] <= a[2] + 1e-6, r[3] <= a[3] + 1e-6][side]
    assert inside  # 這一區的取景框那一邊整個拖進框裡了（看得到外面的鄰區）——修前它停在框邊


def test_the_world_map_range_is_unchanged():
    """天下圖照舊：夾在 world.frame，1 倍時整張就在露出來的那一塊裡。"""
    out = run(_game("yingchuan"), READY + EDGES + "dragBy(300, 0); return [edges(), open()];", layer="world")
    e, a = out
    assert e[0] >= a[0] - 1e-6 and e[2] <= a[2] + 1e-6


# ── 別區的淡墨小圖 ──

def _parts(game, cases, app=None):
    return run(game, PARTS, app=app, cases=cases)


def test_neighbour_places_are_faint_icons_without_names():
    """全區潁川汝南：別區每一處（疊層裡有的）一個淡墨小圖（g.r-faint，點得到、不寫名），本區的不畫成淡的；取景框外不再蓋紙。"""
    game = _game("yingchuan")
    st, base = game.map_state(), game.map_base()
    low, _ = _parts(game, [{"st": st, "vw": 375, "vh": 604, "rid": "yingru", "wash": False}])[0]
    faint = re.findall(r'<g class="r-faint" data-act="region-place" data-id="([^"]+)"[^>]*>(.*?)</g>', low)
    others = {p["id"] for p in base["places"] if p["region"] != "yingru" and p["id"] in st["places"]}
    assert {pid for pid, _ in faint} == others and len(faint) == len(others) > 10
    assert not any("<text" in body for _, body in faint)
    assert set(re.findall(r'class="r-icon" data-act="region-place" data-id="([a-z_]+)"', low)).isdisjoint(others)
    assert "r-mask" not in low
    assert set(re.findall(r'<rect class="r-hit" data-act="region-place" data-id="([^"]+)"', low)) == others


def test_tapping_a_neighbour_icon_opens_its_card_and_keeps_this_region():
    """點別區的淡墨小圖：開那一處的卡（同全區點本區地點：抽屜半開、地圖不動），全區與上面那一排的大區名照舊是這一區。"""
    out = run(_game("yingchuan"), READY + """
const t0 = world.style.transform;
const opened = click('region-place', 'luoyang_road');
return { opened, sel: H.S.mapSel, mode: H.S.mapMode, drawer: H.S.mapDrawer, layer: H.S.mapLayer, region: H.S.mapRegion,
         still: world.style.transform === t0, top: /<option value="([a-z_]+)" selected>/.exec(H.regionTopHtml())[1],
         card: H.placeCard(H.S.mapBase, H.S.mapState, H.S.mapSel) };
""")
    assert out["opened"] and (out["sel"], out["mode"], out["drawer"]) == ("luoyang_road", "place", "peek")
    assert (out["layer"], out["region"], out["top"], out["still"]) == ("region", "yingru", "yingru", True)
    assert "洛陽官道" in out["card"]


# ── 點擊判定：照畫出來的 SVG 疊點擊區（後畫的在上面） ──

TAG = re.compile(r"<(/?)(g|rect)\b([^>]*?)/?>")
ATTR = re.compile(r'([\w-]+)="([^"]*)"')
MOVE = re.compile(r"translate\(([-\d.e]+),([-\d.e]+)\) scale\(([-\d.e]+)\)")


def _hits(svg: str):
    """點得到的框照畫的先後 [(種類, 地點, 框)]：帶 data-act 的透明 rect、帶 data-act 那一組裡的每一個 rect（名字框、寶、小圖的透明框；
    小圖那一組照它的 translate／scale 換算）。小圖中心 {地點: (x, y)}（本區 r-icon、別區 r-faint、你腳下不在這一區時的 r-here）。"""
    stack, out, icons = [], [], {}
    for m in TAG.finditer(svg):
        close, tag, attrs = m.group(1), m.group(2), dict(ATTR.findall(m.group(3)))
        if tag == "g":
            if close:
                stack.pop()
            else:
                stack.append(attrs)
                if attrs.get("class") in ("r-icon", "r-faint", "r-here"):
                    icons[attrs["data-id"]] = tuple(float(n) for n in MOVE.search(attrs["transform"]).groups()[:2])
            continue
        owner = attrs if "data-act" in attrs else next((g for g in reversed(stack) if "data-act" in g), None)
        if owner is None or ("data-act" in attrs and attrs.get("fill-opacity") != "0"):
            continue
        x, y, w, h = (float(attrs[n]) for n in ("x", "y", "width", "height"))
        box = [x, y, x + w, y + h]
        for g in reversed(stack):
            mv = MOVE.search(g.get("transform", ""))
            if mv:
                gx, gy, s = (float(n) for n in mv.groups())
                box = [gx + box[0] * s, gy + box[1] * s, gx + box[2] * s, gy + box[3] * s]
        out.append((owner.get("class") or owner["data-act"], owner.get("data-id"), box))
    return out, icons


def _top(hits, x, y):
    return next(((kind, pid) for kind, pid, b in reversed(hits) if b[0] <= x <= b[2] and b[1] <= y <= b[3]), (None, None))


def test_every_icon_gets_its_own_tap_in_every_region():
    """五區 × 幾處站位 × 幾種地圖框：點本區的小圖選到它自己、點別區的淡墨小圖選到那一處（不會是名字框、出口或點空白）。"""
    game = _game("yingchuan")
    base = game.map_base()
    cases = []
    for at in ("yingchuan", "luoyang_road", "zhuo_county"):
        game.state.player.location = at
        st = game.map_state()
        cases += [{"st": st, "vw": vw, "vh": vh, "rid": r["id"], "wash": False} for r in base["regions"] for vw, vh in FRAMES]
    seen = 0
    for case, out in zip(cases, _parts(game, cases)):
        hits, icons = _hits(out[0])
        for pid, (x, y) in icons.items():
            assert _top(hits, x, y)[1] == pid, f"{case['rid']} {case['vw']}×{case['vh']}：點 {pid} 選到 {_top(hits, x, y)}"
            seen += 1
    assert seen > 500


def test_a_neighbour_icon_under_a_name_frame_wins_the_tap():
    """別區的小圖疊到本區的名字框上（擺一處跟潁川汝南沒有路相連的別區地點到某個名字框正中）：點那一點選到別區那一處；點名字框其餘地方照舊是它自己。"""
    game = _game("yingchuan")
    base, st = game.map_base(), game.map_state()
    home = {p["id"] for p in base["places"] if p["region"] == "yingru"}
    linked = {a for a, b in base["edges"] if b in home} | {b for a, b in base["edges"] if a in home}
    far = next(p for p in base["places"] if p["region"] != "yingru" and p["id"] not in linked and p["id"] in st["places"])
    case = {"st": st, "vw": 375, "vh": 604, "rid": "yingru", "wash": False}
    low = _parts(game, [case])[0][0]
    label = re.search(r'<g class="r-label" data-act="region-place" data-id="([^"]+)"[^>]*>(?:<rect class="r-fight[^>]*/>)?'
                      r'<rect class="r-frame" x="([-\d.]+)" y="([-\d.]+)" width="([-\d.]+)" height="([-\d.]+)"', low)
    pid, x, y, w, h = label.group(1), *(float(n) for n in label.groups()[1:])
    cx, cy = x + w / 2, y + h / 2
    moved = dict(base, places=[dict(p, x=cx, y=cy) if p["id"] == far["id"] else p for p in base["places"]])
    out = run(game, PARTS, cases=[case], mapBase=moved)[0]
    hits, _ = _hits(out[0])
    assert re.sub(r'<g class="r-(?:faints|hits)">.*?</g>(?=<)', "", out[0]).count(f'data-id="{pid}"') >= 2  # 名字框照舊在（沒被挪開）
    assert _top(hits, cx, cy) == ("r-hit", far["id"])  # 小圖疊在名字框上：點小圖選到小圖那一處
    assert _top(hits, x + 2, y + 2) == ("r-label", pid)  # 名字框的角（小圖外面）照舊是它自己


# ── 本區一個位元組都不變 ──

def _old_app(tmp_path):
    """選甲之前那一版的整支 app.js（main.js、BEFORE 的 map.js、app.js 接起來，同 webharness.app_source）；git 拿不到（不在 repo 裡跑）就略過。"""
    got = subprocess.run(["git", "show", f"{BEFORE}:web/map.js"], cwd=webharness.ROOT, capture_output=True)
    if got.returncode != 0:
        pytest.skip(f"拿不到 {BEFORE} 的 web/map.js（{got.stderr.decode(errors='replace').strip()[:80]}）")
    old_map = got.stdout.decode("utf-8").replace("\r\n", "\n")
    parts = [(webharness.WEB / n).read_text(encoding="utf-8").replace("\r\n", "\n") if n != "map.js" else old_map for n in webharness.APP_FILES]
    path = tmp_path / "app_before_jia.js"
    path.write_text("(() => {\n" + "".join(parts) + "})();\n", encoding="utf-8")
    return path


def test_the_home_region_draws_byte_for_byte_as_before(tmp_path):
    """五區 × 三處站位 × 三種地圖框（另加塗層開著）：拿掉別區的淡墨小圖與點擊區（g.r-faints、g.r-hits）之後，跟選甲之前那一版拿掉取景框外
    那層紙（g.r-mask）逐位元組一樣；你站的那一區上面那一張（你、旗、跳的圈）整份一樣。
    你站在別區的那幾張（FB-884，企劃者 2026-10-26：全區看別區時也畫出你）多畫你腳下那一處（g.r-here，被拿掉的淡墨小圖換成它）與上面那一張的朱圈：
    拿掉 g.r-here 之後下面那一張一樣；選甲那一版看別區時上面那一張是空的。"""
    old_app = _old_app(tmp_path)
    game = _game("yingchuan")
    base = game.map_base()
    region_of = {p["id"]: p["region"] for p in base["places"]}
    cases = []
    for at in ("yingchuan", "luoyang_road", "zhuo_county"):
        game.state.player.location = at
        st = game.map_state()
        cases += [{"st": st, "vw": vw, "vh": vh, "rid": r["id"], "wash": False} for r in base["regions"] for vw, vh in FRAMES]
        cases += [{"st": st, "vw": 375, "vh": 604, "rid": r["id"], "wash": True} for r in base["regions"]]
    new, old = _parts(game, cases), _parts(game, cases, app=old_app)
    stripped = away = 0
    for case, (nl, nh), (ol, oh) in zip(cases, new, old):
        where = f"{case['rid']} {case['vw']}×{case['vh']} 塗層{case['wash']}"
        elsewhere = region_of[case["st"]["here"]] != case["rid"]
        n = re.sub(r'<g class="r-faints">(?:<g class="r-faint".*?</g>)*</g>|<g class="r-hits">(?:<rect [^>]*/>)*</g>', "", nl)
        n, here = re.subn(r'<g class="r-here".*?</g>', "", n)
        o, k = re.subn(r'<g class="r-mask"[^>]*>(?:<path [^>]*/>)*</g>', "", ol)
        assert k == 1 and "r-mask" not in nl, where
        assert here == (1 if elsewhere else 0), where  # 你腳下那一處不在這一區才多一個 r-here
        assert n == o, where
        if elsewhere:
            assert oh == "" and 'class="r-you"' in nh, where  # 選甲那一版看別區沒有你；現在有朱圈
            away += 1
        else:
            assert nh == oh, where
        stripped += nl != n
    assert stripped == len(cases)  # 每一張都真的有別區的小圖（拿掉了才一樣）
    assert 0 < away < len(cases)
