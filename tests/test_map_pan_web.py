"""輿圖的拖與縮放（企劃者 2026-10-22：試玩新輿圖「輿圖沒辦法拖曳移動了」「不順手」，選「兩張都能拖、能捏合縮放」；
計畫 docs/superpowers/plans/2026-10-22-輿圖拖曳縮放.md）。推翻輿圖簡化設計第五章「不自由縮放」那一半，兩層照舊。

以前（輿圖第三版第 4 批起）的測試守的是「沒有手勢、圖一個像素都不動」，照企劃者這次的決定反過來：拖會動、縮放會放大、點一下開卡、
拖過不開卡、夾邊、換區回 1 倍；整張圖連字一起動（記號不重畫、擺字不重算，只換 .tx-world-map 的 transform）。
在 node 裡跑整支 app.js（tests/webharness.py），地圖框是假的（收監聽、量得到大小），餵伺服器真的會給的底圖與疊層；沒有 node 就略過。"""
from __future__ import annotations

import random
import re
from pathlib import Path

import pytest
import test_prologue_web
from conftest import real_content
from conquest_kit import conquest_rules

import server
import webharness
from tianxia import territory
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]
NAMES = ["S", "applyMapView", "mapReady", "mapTransform", "panClamp", "panZoom", "panBox", "panWire", "enterRegion", "toWorld",
         "mapTimeline", "mapWeekTo", "regionPick", "curView", "PAN_MAX", "PAN_SLOP", "renderTop", "mapFrame"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
APP = webharness.APP  # 三個檔（main.js、map.js、app.js）接起來的那一份
CSS = Path(server.WEB) / "style.css"


def _game(at="yingchuan"):
    c = real_content("week7")
    conquest_rules(c)
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    territory.update(game.state.world, c)
    game.state.player.faction, game.state.player.location = "guan", at
    return game


def _dom(vw, vh):
    """假的地圖框（#map）、記號（#mk 數寫了幾次）、整頁一層（#mapx）、抽屜；requestAnimationFrame 排進一個佇列，flush() 才跑；
    fire(type, …) 照瀏覽器的順序送事件給地圖框的監聽，click(id) 先過地圖框捕獲階段的監聽、沒被吃掉才交給 document 的 click。"""
    return f"""
const VW = {vw}, VH = {vh};
const listeners = {{}}, captured = [], wcls = new Set();
const world = {{ style: {{}} }};
const svg = {{ viewBox: {{ baseVal: {{ width: H.S.mapBase.w || 900, height: H.S.mapBase.h || 1340 }} }}, parentNode: world, dataset: {{}} }};
const wrap = {{
  id: 'map', clientWidth: VW, clientHeight: VH, clientLeft: 0, clientTop: 0, dataset: {{}},
  getBoundingClientRect: () => ({{ left: 0, top: 0 }}),
  querySelector: (sel) => (sel === '.tx-world-map > svg' ? svg : null), querySelectorAll: () => [],
  classList: {{ add: (c) => wcls.add(c), remove: (c) => wcls.delete(c), contains: (c) => wcls.has(c), toggle: (c, on) => (on ? wcls.add(c) : wcls.delete(c)) }},
  setPointerCapture: (id) => captured.push(id),
  addEventListener: (t, f, o) => {{ (listeners[t] = listeners[t] || []).push({{ f, o }}); }},
}};
let mkWrites = 0, mkHtml = '';
const mk = {{}};
Object.defineProperty(mk, 'innerHTML', {{ get: () => mkHtml, set: (v) => {{ mkWrites += 1; mkHtml = v; }} }});
const dcls = new Set();
const drawer = {{ style: {{}}, offsetHeight: 0, classList: {{ contains: (c) => dcls.has(c), toggle: (c, on) => (on ? dcls.add(c) : dcls.delete(c)) }} }};
const props = {{}};
let topBottom = 60;
const els = {{ map: wrap, mk, mkt: {{ innerHTML: '' }}, msel: {{ innerHTML: '', firstChild: null }}, mbody: {{ innerHTML: '' }}, mdrawer: drawer,
  mapx: {{ clientHeight: VH, className: '', children: [], style: {{ setProperty: (k, v) => {{ props[k] = v; }}, getPropertyValue: (k) => props[k] || '' }}, insertAdjacentHTML() {{}} }},
  top: {{ hidden: false, innerHTML: '', offsetHeight: 60, getBoundingClientRect: () => ({{ bottom: topBottom }}), querySelector: () => null, querySelectorAll: () => [],
    classList: {{ add() {{}}, remove() {{}}, toggle() {{}}, contains: () => false }} }} }};
// 狀態列變高（dh > 0）或變矮：地圖框跟著換高（框的上緣是狀態列的下緣），只改大小、不叫 applyMapView（FB-710 的情形）
const frameTo = (h) => {{ topBottom = 60 + (VH - h); wrap.clientHeight = h; els.mapx.clientHeight = h; }};
const orig = T.ctx.document.getElementById;
T.ctx.document.getElementById = (id) => els[id] || orig(id);
let rafN = 0;
const rafQ = new Map();
T.ctx.requestAnimationFrame = (f) => {{ rafQ.set(++rafN, f); return rafN; }};
T.ctx.cancelAnimationFrame = (id) => {{ rafQ.delete(id); }};
const flush = () => {{ for (const [id, f] of [...rafQ]) {{ rafQ.delete(id); f(); }} }};
const fire = (type, o = {{}}) => {{
  const ev = {{ type, pointerId: 1, pointerType: 'touch', button: 0, clientX: 0, clientY: 0, deltaY: 0, deltaMode: 0, currentTarget: wrap,
    prevented: false, stopped: false, preventDefault() {{ this.prevented = true; }}, stopPropagation() {{ this.stopped = true; }}, ...o }};
  for (const l of listeners[type] || []) l.f(ev);
  return ev;
}};
const down = (id, x, y, o = {{}}) => fire('pointerdown', {{ pointerId: id, clientX: x, clientY: y, ...o }});
const move = (id, x, y, o = {{}}) => fire('pointermove', {{ pointerId: id, clientX: x, clientY: y, ...o }});
const up = (id, x, y, o = {{}}) => fire('pointerup', {{ pointerId: id, clientX: x, clientY: y, ...o }});
const wheel = (x, y, dy, o = {{}}) => fire('wheel', {{ clientX: x, clientY: y, deltaY: dy, ...o }});
// 點地圖上的一處（區圖的名字框、天下圖的一區、「天下」鈕）：先過地圖框捕獲階段的監聽（panEat），沒被吃掉才交給 document 的 click
const click = (act, id, inMap = true) => {{
  const el = {{ dataset: {{ act, id }}, classList: {{ contains: () => false }}, closest: () => el }};
  const ev = {{ type: 'click', target: el, clientX: 0, clientY: 0, stopped: false, stopPropagation() {{ this.stopped = true; }}, preventDefault() {{}} }};
  if (inMap) for (const l of listeners.click || []) if (l.o === true) l.f(ev);
  if (!ev.stopped) for (const f of T.docListeners.click || []) f(ev);
  return !ev.stopped;
}};
// 此刻的 transform 拆成數字；地圖座標 (x, y) 在螢幕上哪裡、螢幕上 (px, py) 底下是哪一個地圖座標
const tf = () => {{
  const m = world.style.transform.match(/translate\\((-?[\\d.e+-]+)px, (-?[\\d.e+-]+)px\\) scale\\(([\\d.e+-]+)\\)/);
  return {{ x: +m[1], y: +m[2], s: +m[3] }};
}};
const toScreen = (x, y) => {{ const t = tf(); return [t.x + x * t.s, t.y + y * t.s]; }};
const toMap = (px, py) => {{ const t = tf(); return [(px - t.x) / t.s, (py - t.y) / t.s]; }};
// 內容框（夾邊照它：天下圖與全區都是整張圖 world.frame——全區以前是這一區的取景框，FB-876 企劃者 2026-10-26 選甲改成整張圖）此刻在螢幕上的四邊
const content = () => {{
  const f = H.S.mapBase.world.frame;
  return [...toScreen(f[0], f[1]), ...toScreen(f[0] + f[2], f[1] + f[3])];
}};
// 這一區的取景框（全區）此刻在螢幕上的四邊
const regionBox = () => {{ const f = H.S.regionView.frame; return [...toScreen(f[0], f[1]), ...toScreen(f[2], f[3])]; }};
const pan = () => H.S.mapPan && {{ z: +H.S.mapPan.z.toFixed(6), x: +H.S.mapPan.x.toFixed(3), y: +H.S.mapPan.y.toFixed(3) }};
// 用滾輪（小步、對著地圖框中間）放大到至少 zt 倍
const zoomTo = (zt) => {{ for (let i = 0; i < 300 && (!H.S.mapPan || H.S.mapPan.z < zt); i++) {{ wheel(VW / 2, 330, -20); flush(); }} return pan(); }};
"""


def run(game, script, vw=375, vh=604, layer="region", region="yingru", **S):
    payload = {"m": server.main_view(game), "script": _dom(vw, vh) + script,
               "S": {"mapBase": game.map_base(), "mapState": game.map_state(), "mapLayer": layer, "mapRegion": region, "tab": "map", **S},
               "menxia": None, "stored": {}, "responses": {}}
    return webharness.run(DRIVER, payload)


# 準備好：取景套上、監聽掛上（mapReady 做的那兩件）
READY = "H.applyMapView(false); H.panWire(wrap);\n"


def test_the_one_times_view_writes_the_same_transform_as_the_fixed_framing():
    """1 倍（還沒拖縮）時 transform 跟以前固定取景的寫法一字不差（第 4、5 批的畫面一個像素都不變）。"""
    out = run(_game(), READY + """
const v = H.curView(), base = `translate(${VW / 2 - v.cx * v.s}px, ${VH / 2 - v.cy * v.s}px) scale(${v.s})`;
const w = { s: 0.4123, cx: 455.5, cy: 612.25 };
return [world.style.transform === base, H.mapTransform(w, 360, 452) === `translate(${180 - w.cx * w.s}px, ${226 - w.cy * w.s}px) scale(${w.s})`, H.S.mapPan];
""")
    assert out == [True, True, None]


def test_mapready_wires_the_map_frame_once():
    out = run(_game(), """
H.mapReady(); H.mapReady();
return Object.fromEntries(Object.entries(listeners).map(([k, v]) => [k, v.map((l) => l.o === true ? 'capture' : l.o && l.o.passive === false ? 'active' : 'plain')]));
""")
    assert out["pointerdown"] == ["plain"] and out["pointermove"] == ["plain"] and out["pointerup"] == ["plain"] and out["pointercancel"] == ["plain"]
    assert out["wheel"] == ["active"]  # 滾輪要 preventDefault（不捲頁、不放大整頁）：不能是被動的監聽
    assert out["click"] == ["capture"]  # 拖過放開的那一下 click 在 document 分派之前吃掉
    assert set(out) >= {"gesturestart", "gesturechange", "dragstart"}


def test_a_tap_still_opens_the_card_and_does_not_move_the_map():
    """點一下（按下到放開沒移過 PAN_SLOP）：地圖不動、click 照常送到那一處（抽屜半開那一處的卡）。"""
    out = run(_game(), READY + """
const t0 = world.style.transform;
down(1, 200, 300); move(1, 203, 302); flush(); up(1, 203, 302); flush();
const opened = click('region-place', 'changshe');
return [world.style.transform === t0, H.S.mapPan, opened, H.S.mapSel, H.S.mapMode, captured.length, world.style.willChange || ''];
""")
    assert out == [True, None, True, "changshe", "place", 0, ""]  # 點一下不抓指標（抓了 Chrome 會把 click 送到地圖框，點不到地點）


def test_a_drag_moves_the_map_with_the_finger_and_does_not_open_a_card():
    """先放大到 2.5 倍（滾輪），再一指拖：地圖跟著手指走一樣的距離；放開那一下的 click 被吃掉、卡不開（企劃者「拖動不要誤開卡」）。"""
    out = run(_game(), READY + """
zoomTo(2.5);
const before = pan(), spot = toMap(150, 300);
down(1, 150, 300); move(1, 160, 310); move(1, 190, 335); flush();
const during = [world.style.willChange, captured.slice()];
up(1, 190, 335); flush();
const after = pan(), there = toScreen(...spot);
const opened = click('region-place', 'changshe');
return { before, after, there, opened, sel: H.S.mapSel, during, will: world.style.willChange };
""")
    b, a = out["before"], out["after"]
    assert a["z"] == b["z"] and a["x"] == pytest.approx(b["x"] + 40) and a["y"] == pytest.approx(b["y"] + 35)
    assert out["there"] == pytest.approx([190, 335])  # 手指底下那一點的地圖跟著手指走
    assert out["opened"] is False and out["sel"] is None  # 拖過：不開卡
    assert out["during"] == ["transform", [1]] and out["will"] == ""  # 拖的時候合成層，放開才拿掉（照最後的倍率重畫一次）


def test_the_wheel_zooms_around_the_cursor_between_one_and_three_on_the_region_map():
    """滾輪以游標為中心縮放（游標底下的地圖不動；放大到內容框蓋滿露出來的那一塊之後），區圖最多 3 倍、最少 1 倍（不准比現在的取景小）；
    ctrl＋滾輪（觸控板捏合）一樣；滾輪要 preventDefault（圖上不捲頁）。"""
    out = run(_game(), READY + """
flush(); mkWrites = 0; // 取景第一次套上時排的那一次畫記號不算
for (let i = 0; i < 6; i++) { wheel(VW / 2, 330, -100); flush(); }
const z1 = pan().z, spot = toMap(120, 220);
const ev = wheel(120, 220, -100, { ctrlKey: true }); flush();
const z2 = pan().z, there = toScreen(...spot);
for (let i = 0; i < 60; i++) { wheel(300, 500, -100); flush(); }
const top = pan().z;
for (let i = 0; i < 80; i++) { wheel(30, 100, 120); flush(); }
const bottom = H.S.mapPan, c = content();
return { z1, z2, there, top, bottom, prevented: ev.prevented, c, mk: mkWrites };
""")
    assert 1.5 < out["z1"] < 3 and out["z2"] == pytest.approx(out["z1"] * 2.718281828 ** 0.15, rel=1e-6)
    assert out["there"] == pytest.approx([120, 220])  # 游標底下那一點沒動
    assert out["top"] == 3 and out["bottom"] is None  # 最多 3 倍；縮回去停在 1 倍（mapPan 是 null＝1 倍、沒有位移）
    assert out["prevented"] is True
    assert out["mk"] == 0  # 記號一次都沒重畫


def test_zooming_out_walks_back_to_the_fixed_framing():
    """縮小時位移照倍率收回去（像看照片：縮回最小就置中）——縮到 1 倍剛好是現在的取景；放大不收（游標底下那一點不動）。
    捏合縮回 1 倍也一樣（mapPan 是 null，transform 跟固定取景一字不差）。"""
    out = run(_game(), READY + """
const a = H.panZoom({ z: 3, x: -600, y: -400 }, 2, 100, 100, 3), b = H.panZoom({ z: 2, x: -100, y: -50 }, 3, 100, 100, 3);
const c = H.panZoom({ z: 2, x: -100, y: -50 }, 0.8, 100, 100, 3);
zoomTo(2);
down(1, 120, 300); down(2, 260, 300); move(1, 150, 300); move(2, 230, 300); flush(); move(1, 180, 300); move(2, 200, 300); flush(); up(1, 180, 300); up(2, 200, 300); flush();
return [a, b, c, H.S.mapPan, world.style.transform === H.mapTransform(H.curView(), VW, VH)];
""")
    a, b, c, after, same = out
    assert a["z"] == 2 and a["x"] == pytest.approx((100 - 2 / 3 * 700) / 2) and a["y"] == pytest.approx((100 - 2 / 3 * 500) / 2)
    assert b == {"z": 3, "x": -200, "y": -125}
    assert c == {"z": 1, "x": 0, "y": 0}
    assert after is None and same is True


def test_the_world_map_zooms_up_to_four():
    out = run(_game(), READY + """
for (let i = 0; i < 80; i++) { wheel(VW / 2, 300, -100); flush(); }
return [pan().z, H.PAN_MAX];
""", layer="world")
    assert out[0] == 4 and out[1] == {"world": 4, "region": 3}


def test_a_pinch_zooms_around_the_fingers_and_eats_the_click():
    """兩指捏合：倍率照兩指距離的比、兩指中點底下的地圖跟著中點走；放開一指剩下那一指接著拖；捏過放開的 click 吃掉。"""
    out = run(_game(), READY + """
zoomTo(2);
const z0 = pan().z, mid0 = [180, 300], spot = toMap(...mid0);
down(1, 140, 300); down(2, 220, 300);
const capturedAtSecond = captured.slice();
move(1, 130, 290); move(2, 230, 290); flush(); // 兩指距離 80 → 100（1.25 倍），中點 (180, 300) → (180, 290)
const z1 = pan().z, there = toScreen(...spot), mid1 = pan();
up(2, 230, 290); move(1, 140, 300); flush(); // 放開一指：剩下那一指接著拖（往右下 10、10）
const after = pan();
up(1, 140, 300); flush();
const opened = click('region-place', 'changshe');
return { z0, z1, there, mid1, after, opened, capturedAtSecond, will: world.style.willChange };
""")
    assert out["z1"] == pytest.approx(out["z0"] * 1.25, rel=1e-6)
    assert out["there"] == pytest.approx([180, 290])  # 中點底下那一點跟著中點走
    assert out["after"]["z"] == pytest.approx(out["z1"], rel=1e-6)
    assert [out["after"]["x"] - out["mid1"]["x"], out["after"]["y"] - out["mid1"]["y"]] == pytest.approx([10, 10])
    assert out["opened"] is False
    assert out["capturedAtSecond"] == [1, 2]  # 第二指按下就是捏合：兩指都抓住
    assert out["will"] == ""


@pytest.mark.parametrize("dx,dy,edge", [(3000, 0, "left"), (-3000, 0, "right"), (0, 3000, "top"), (0, -3000, "bottom")])
def test_dragging_hard_stops_at_the_edges(dx, dy, edge):
    """夾邊（企劃者「圖不能完全拖出框外」）：放大之後往一個方向拖到底，內容框那一邊剛好貼齊露出來的那一塊——
    左右是地圖框、上面是那一排底下（58）、底下是抽屜上面（收著 54）。整張不會拖出框外。
    FB-876（企劃者 2026-10-26 選甲）：全區的內容框從這一區的取景框改成整張圖，看洛陽（在整張圖中間，四邊都拖得到整張圖的邊；
    潁川汝南貼著整張圖的南緣，1 倍時南緣就露在框裡，軟夾照規則不往外，新規則另見 tests/test_fb876_region_neighbours_web.py）。"""
    out = run(_game(), READY + f"""
zoomTo(3);
down(1, 180, 300); move(1, 180 + {dx} / 2, 300 + {dy} / 2); flush(); move(1, 180 + {dx}, 300 + {dy}); flush(); up(1, 180 + {dx}, 300 + {dy}); flush();
return content();
""", region="luoyang")
    x0, y0, x1, y1 = out
    want = {"left": (x0, 0), "right": (x1, 375), "top": (y0, 58), "bottom": (y1, 604 - 54)}[edge]
    assert want[0] == pytest.approx(want[1], abs=1e-6)
    assert x0 <= 0 + 1e-6 and x1 >= 375 - 1e-6 and y0 <= 58 + 1e-6 and y1 >= 550 - 1e-6  # 3 倍時內容框照樣蓋滿露出來的那一塊


def test_at_one_times_the_region_map_drags_out_of_its_region():
    """FB-876（企劃者 2026-10-26 選甲）推翻以前這一條（「1 倍時這一區的取景框整個在露出來的那一塊裡，拖只能在空隙裡挪，挪不出去」）：
    全區照整張圖夾，1 倍時也拖得出這一區——往右拖 400，這一區的取景框左緣離開框邊一大截（看得到西邊的鄰區）；整張圖的四邊照樣不拖進露出來的
    那一塊（1 倍時就已經露在框裡的那一邊照軟夾不再往裡）；縮回 1 倍時回到 1 倍的取景。新規則另見 tests/test_fb876_region_neighbours_web.py。"""
    out = run(_game(), READY + """
const start = content(), startRegion = regionBox(), res = [];
for (const [dx, dy] of [[400, 0], [-400, 0], [0, 400], [0, -400]]) {
  H.S.mapPan = null; H.S.panFrom = null; H.applyMapView(false);
  down(1, 180, 300); move(1, 180 + dx, 300 + dy); flush(); up(1, 180 + dx, 300 + dy); flush();
  res.push({ whole: content(), region: regionBox(), pan: pan() });
}
for (let i = 0; i < 30; i++) { wheel(VW / 2, 330, -100); flush(); }
down(1, 180, 300); move(1, 3000, 300); flush(); up(1, 3000, 300); flush(); // 3 倍拖到最左邊
for (let i = 0; i < 80; i++) { wheel(20, 330, 100); flush(); }
return { start, startRegion, res, back: H.S.mapPan };
""")
    start, (right, left, down, up), back = out["start"], out["res"], out["back"]
    assert right["region"][0] > 150 and right["whole"][0] <= 1e-6  # 拖得出這一區（修前 1 倍時一點都不動），整張圖的西緣不拖進框裡
    assert left["region"][2] < out["startRegion"][2] - 20 and left["whole"][2] == pytest.approx(375)  # 往左拖到整張圖的東緣停住
    assert down["pan"]["y"] == pytest.approx(400) and down["whole"][1] <= 58 + 1e-6  # 往下拖看北邊
    assert up["whole"][3] == pytest.approx(start[3])  # 潁川汝南貼著整張圖的南緣：1 倍時南緣已經露在框裡，往上拖不再往外（軟夾）
    assert back is None  # 縮回 1 倍：1 倍的取景


def test_the_soft_edge_never_jumps():
    """軟夾：此刻已經在範圍外（卡拉高之後，1 倍的取景照規則要貼齊上緣）時，按下去拖不會先跳一下；往外拖不動、往裡拖照常。"""
    out = run(_game(), READY + """
const c = { b: [0, 70, 375, 500], a: [0, 58, 375, 300] }; // 內容框比露出來的那一塊高，上緣多留 12px（照規則 y 要 ≤ −12）
const p0 = { z: 1, x: 0, y: 0 };
return [H.panClamp(p0, c, p0), H.panClamp({ z: 1, x: 0, y: 5 }, c, p0), H.panClamp({ z: 1, x: 0, y: -30 }, c, p0),
        H.panClamp({ z: 1, x: 0, y: -400 }, c, p0), H.panClamp({ z: 2, x: 0, y: -100 }, c, p0)];
""")
    assert out[0] == {"z": 1, "x": 0, "y": 0}  # 在外面的那一下不跳
    assert out[1]["y"] == 0  # 往外（往下）拖不動
    assert out[2]["y"] == -30  # 往裡拖照常
    assert out[3]["y"] == pytest.approx(300 - 500)  # 往上拖到底：下緣貼齊露出來的那一塊的下緣
    assert out[4]["y"] == -100  # 換了倍率：照新的倍率夾（2 倍時上緣 58 − 2·70 = −82 以內都行，多准的那 12px 照帶著）


def test_changing_region_going_back_to_the_world_and_the_timeline_reset_to_one():
    """換區、回天下圖、進區圖、打開或收起版圖變化回 1 倍；同一個取景再套一次（切分頁回來、輿圖頁重畫）照留。"""
    out = run(_game(), READY + """
const zoom = () => { for (let i = 0; i < 5; i++) { wheel(VW / 2, 330, -100); flush(); } return !!H.S.mapPan; };
const res = [];
zoom(); H.applyMapView(false); res.push(['same view', !!H.S.mapPan]);
H.mapReady(); res.push(['mapReady', !!H.S.mapPan]);
H.enterRegion('nanyang'); res.push(['other region', H.S.mapPan, world.style.transform === H.mapTransform(H.curView(), VW, VH)]);
zoom(); H.enterRegion('nanyang'); res.push(['same region again', H.S.mapPan]);
zoom(); H.toWorld(); res.push(['world', H.S.mapPan]);
zoom(); H.mapTimeline(true); res.push(['timeline open', H.S.mapPan]);
zoom(); H.mapWeekTo(1); res.push(['timeline week', !!H.S.mapPan, mkWrites > 0]);
H.mapTimeline(false); res.push(['timeline closed', H.S.mapPan]);
zoom(); click('map-world', '', false); res.push(['world button', H.S.mapPan]);
frameTo(VH - 40); zoom(); H.applyMapView(false); res.push(['frame height', !!H.S.mapPan]); // 只換框高（狀態列變高變矮）：帶過去（FB-710）
wrap.clientWidth = VW - 40; H.applyMapView(false); res.push(['frame width', H.S.mapPan]); // 換寬（轉向、拉視窗）：取景換了，回 1 倍
return res;
""")
    assert out == [["same view", True], ["mapReady", True], ["other region", None, True], ["same region again", None], ["world", None],
                   ["timeline open", None], ["timeline week", True, True], ["timeline closed", None], ["world button", None],
                   ["frame height", True], ["frame width", None]]


# ── FB-710（QA 2026-10-22）：狀態列變高變矮（卡上按「步行」、點體力條攤開說明、輪詢多一行少一行）之後，renderTop 只叫了 mapFrame、
# 沒重套取景，下一次拖縮拿新的框高配舊的取景，地圖先跳 z×框高差÷2（2 倍按步行：往下拖 20 卻往上走 23）。PM 定：同一層、同一區只換框高時，
# 把目前的倍率與位置帶過去、照新的可見區重夾一次（不清回 1 倍、不跳）；層或區換了才回 1 倍。修法：renderTop 在 mapFrame 真的改了兩條邊時
# 叫 applyMapView（panCarry 帶過去、夾一次）；手勢一開始發現框換了大小也先帶過去（不經 renderTop 的路，這一次不挪）
FB710 = """
if (Z > 1) zoomTo(Z);
const before = content(), s0 = tf().s;
frameTo(H2);
if (VIA_TOP) { H.S.tab = 'map'; H.renderTop(); }
const after = content(), s1 = tf().s, a1 = H2 - 54, pan1 = H.S.mapPan;
down(1, 150, 300); move(1, 150, 310); move(1, 150, 320); flush(); up(1, 150, 320); flush();
const dragged = content();
return { before, after, dragged, s0, s1, a1, pan1 };
"""


@pytest.mark.parametrize("via_top", [True, False], ids=["renderTop", "first-gesture"])
@pytest.mark.parametrize("z,h2", [(1, 561), (1, 490), (1, 647), (2, 561), (2, 490), (2, 647)])
def test_fb710_the_first_drag_after_the_frame_changes_height_follows_the_finger(z, h2, via_top):
    """1、2 倍下讓地圖框變矮（狀態列多兩行 43px、攤開體力說明 114px）與變高（少一行）：倍率不清、畫面上的地圖不跳，
    下一次往下拖 20px，內容就往下 20px（修之前 2 倍框矮 43px 時往上走 23）。經 renderTop（狀態列重畫）與「手勢一開始才發現框換了」兩條路都一樣。"""
    out = run(_game(), READY + f"const Z = {z}, H2 = {h2}, VIA_TOP = {str(via_top).lower()};\n" + FB710)
    b, a, d = out["before"], out["after"], out["dragged"]
    assert out["s1"] == pytest.approx(out["s0"], rel=1e-9)  # 畫面上的倍率帶過去（不清回 1 倍）
    if via_top:  # 潁川汝南的取景照寬度定倍率、不看框高：1 倍帶過去還是 1 倍（null），2 倍照留
        assert (out["pan1"] is None) == (z == 1)
    assert a == pytest.approx(b)  # 框換高的那一下，地圖在框裡一個像素不動
    # 往下拖 20 就往下走 20（不跳）；只有夾邊擋住的那一截例外：內容框比可見區矮（1 倍）時下緣不能過可見區的下緣，
    # 比可見區高時上緣不能過那一排底下（58）。修之前是反方向（往上）走
    fits = a[3] - a[1] <= out["a1"] - 58
    room = out["a1"] - a[3] if fits else 58 - a[1]
    dy = d[1] - a[1]
    assert dy > 0 and dy == pytest.approx(min(20, room)), (dy, room)
    assert [d[0] - a[0], d[2] - a[2], d[3] - a[3]] == pytest.approx([0, 0, dy])


def test_fb710_render_top_reapplies_the_view_only_when_the_frame_moved():
    """renderTop 每一次輪詢都叫：兩條邊沒變（mapFrame 回 false）就不重套取景；變了才 applyMapView。"""
    out = run(_game(), READY + """
H.S.tab = 'map'; H.renderTop();
const writes = [];
let tr = world.style.transform;
Object.defineProperty(world.style, 'transform', { get: () => tr, set: (v) => { writes.push(v); tr = v; } });
H.renderTop(); H.renderTop();
const same = writes.length;
frameTo(VH - 30); H.renderTop();
return [same, writes.length, H.mapFrame()];
""")
    assert out == [0, 1, False]


def test_fb710_the_frame_growing_reclamps_once_through_the_status_bar():
    """框變高（狀態列少一行）時照新的可見區夾一次（PM 定「重夾一次」）：2 倍拖到下緣貼著可見區下緣（550），狀態列少 43px，
    經 renderTop 時內容的下緣跟著到新的下緣（593），上緣照舊在那一排上面；手勢一開始才發現框換了的那一條路不挪（只准不再往外）。
    內容框是整張圖（FB-876 企劃者選甲，以前是這一區的取景框）：看洛陽（潁川汝南貼著整張圖的南緣，2 倍時南緣拖不到可見區的下緣）。"""
    out = run(_game(), READY + """
const go = (viaTop) => {
  frameTo(VH); H.S.tab = 'map'; H.renderTop(); H.enterRegion('luoyang'); H.regionPick(null);
  zoomTo(2);
  down(1, 150, 400); move(1, 150, 200); flush(); move(1, 150, -600); flush(); up(1, 150, -600); flush(); // 往上拖到底：下緣貼著 550
  const pinned = content();
  frameTo(VH + 43);
  if (viaTop) H.renderTop(); else { down(1, 150, 300); up(1, 150, 300); flush(); }
  return { pinned, after: content() };
};
return { top: go(true), gesture: go(false) };
""")
    t, g = out["top"], out["gesture"]
    assert t["pinned"][3] == pytest.approx(550) and g["pinned"][3] == pytest.approx(550)
    assert t["after"][3] == pytest.approx(604 + 43 - 54) and t["after"][1] < 58  # 重夾：下緣到新的可見區下緣
    assert g["after"] == pytest.approx(g["pinned"])  # 手勢一開始才發現：不挪


def test_fb710_the_world_map_carries_its_zoom_too():
    """天下圖的取景照框高定倍率（框矮了，取景的倍率跟著變小）：帶過去的是畫面上的倍率（z × 取景的倍率），z 的數字可以變。"""
    out = run(_game(), READY + """
zoomTo(2);
const before = content(), s0 = tf().s;
frameTo(VH - 43); H.S.tab = 'map'; H.renderTop();
const after = content(), s1 = tf().s;
down(1, 150, 300); move(1, 150, 320); flush(); up(1, 150, 320); flush();
return { before, after, dragged: content(), s0, s1 };
""", layer="world")
    assert out["s1"] == pytest.approx(out["s0"]) and out["after"] == pytest.approx(out["before"])
    assert out["dragged"][1] - out["after"][1] == pytest.approx(20)


def test_a_gesture_never_redraws_the_marks_and_only_writes_the_transform():
    """效能（Joy 10/18「輿圖滑動的時候還是很卡」）：拖、捏、滾輪的整段時間記號一次都不重畫（#mk 沒被寫）、擺字不重算，
    每一幀只寫 .tx-world-map 的 transform；拖的時候掛 will-change、放開拿掉；框上的 class 不動（FB-322：游標、class 會逼整棵重算樣式）。"""
    out = run(_game(), READY + """
flush(); const marks = mkWrites, cls0 = [...wcls].sort().join(',');
const writes = [];
let tr = world.style.transform;
Object.defineProperty(world.style, 'transform', { get: () => tr, set: (v) => { writes.push(v); tr = v; } });
for (let i = 0; i < 5; i++) { wheel(VW / 2, 330, -100); flush(); }
const wheelFrames = writes.length;
down(1, 150, 300); for (let i = 1; i <= 20; i++) { move(1, 150 + i * 3, 300 + i * 2); flush(); } up(1, 210, 340); flush();
down(1, 140, 300); down(2, 220, 300); for (let i = 1; i <= 10; i++) { move(1, 140 - i, 300); move(2, 220 + i, 300); flush(); } up(1, 130, 300); up(2, 230, 300); flush();
return { redrawn: mkWrites - marks, wheelFrames, writes: writes.length, classes: [...wcls].sort().join(',') === cls0 };
""")
    assert out["redrawn"] == 0
    # 一幀一次，不多寫：拖的第一步只移 3.6px（不到 PAN_SLOP，還可能是點一下），之後 19 步各一幀；捏合 10 幀
    assert out["wheelFrames"] == 5 and out["writes"] == 5 + 19 + 10
    assert out["classes"] is True


def test_the_mouse_only_drags_with_the_left_button_and_a_cancel_does_not_eat_a_click():
    out = run(_game(), READY + """
for (let i = 0; i < 5; i++) { wheel(VW / 2, 330, -100); flush(); }
const p0 = pan();
down(1, 150, 300, { pointerType: 'mouse', button: 2 }); move(1, 200, 340, { pointerType: 'mouse' }); flush(); up(1, 200, 340, { pointerType: 'mouse' }); flush();
const right = pan();
down(1, 150, 300, { pointerType: 'mouse' }); move(1, 200, 340, { pointerType: 'mouse' }); flush(); fire('pointercancel', { pointerId: 1 }); flush();
const cancelled = click('region-place', 'changshe');
return [JSON.stringify(right) === JSON.stringify(p0), cancelled, H.S.mapSel];
""")
    assert out == [True, True, "changshe"]


def test_the_map_frame_blocks_page_gestures_but_keeps_the_hand_cursor_still():
    """圖上的手勢不捲頁、不放大整頁（touch-action: none）；游標一直是 grab，拖的時候不換（FB-322：沒有 grabbing 那一套）。"""
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    rule = re.search(r"\n\.mapx \.map-wrap \{([^}]*)\}", css).group(1)
    assert "touch-action: none" in rule and "cursor: grab" in rule
    src = APP.read_text(encoding="utf-8")
    assert '"grabbing"' not in src and ".map-wrap.grabbing" not in css and ".map-wrap.moving" not in css
    block = src[src.index("  // ── 輿圖的拖與縮放"):src.index("  // 輿圖頁每次畫好")]
    assert "classList.add(" not in block and "classList.toggle(" not in block  # 拖縮中不在框上加 class
    assert "drawMarks" not in block.replace("記號不重畫", "") and "scheduleMarks" not in block  # 拖縮不排重畫
