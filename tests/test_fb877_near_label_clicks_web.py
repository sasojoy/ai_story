"""FB-877（企劃者 2026-10-26 試玩新輿圖：「文字甚至會直接擋到地點的選取」）：輿圖第一層、第二層（nearParts）的名字只讓開走得到的那幾處，
擠的時候會壓到別處的淡墨小圖（站潁川郡、地圖框 375×667：潁水河畔的名字蓋著長社，點長社開的是潁水河畔的卡）；你（朱圈、「你・地名」畫在上面
那一張，不收點擊）底下是別處的名字就點到別處，不是就什麼都沒反應。

修法（不改畫面）：小圖與你的點擊區（透明的 rect.n-hit）另外疊在名字上面一層；名字的點擊區照字分兩行（名字、底下那一行）。
不變量：點小圖、點你、點「你・地名」選到的就是那一處；點名字選到的是它自己、或疊在那一點上面的小圖（底下那一處）、或畫在它上面的名字
（看得到的是那一個），不會是別處、也不會沒反應（落到點空白）。

在 node 裡跑整支 app.js（tests/webharness.py）；點擊照畫出來的 SVG 算：每一塊透明的點擊區照畫的先後疊（後畫的在上面），點一下落在最上面
那一塊。沒有 node 就略過。"""
from __future__ import annotations

import random
import re

import pytest
import test_prologue_web
from conftest import real_content

import server
import webharness
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]
NAMES = ["S", "nearFit", "nearParts"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
FRAMES = [(375, 604), (375, 667), (360, 560), (414, 700), (900, 640)]  # 地圖框（#map）的大小：手機幾種、桌機（抽屜在右欄，底下不讓）

TAG = re.compile(r"<(/?)(g|rect|text)\b([^>]*?)/?>")
ATTR = re.compile(r'([\w-]+)="([^"]*)"')
MOVE = re.compile(r"translate\(([-\d.e]+),([-\d.e]+)\) scale\(([-\d.e]+)\)")


def _game(faction: str):
    c = real_content("week7")
    c.config.auto_open_first_season = True
    game = Game.new(c, "陸乙", rng=random.Random(0), world=open_world())
    game.client = None
    game.state.player.faction = faction
    return game


def _cases(game, places):
    """每一處各站一次（腳下＝那一處）的疊層；沒點、點了走得到的第一處（第二層）各一種，每一種照 FRAMES 各畫一次。"""
    out = []
    for loc in places:
        game.state.player.location = loc
        st = game.map_state()
        near = [b if a == loc else a for a, b in game.map_base()["edges"] if loc in (a, b) and (b if a == loc else a) in st["places"]]
        for sel in [None, *near[:1]]:
            for vw, vh in FRAMES:
                out.append({"st": st, "vw": vw, "vh": vh, "sel": sel, "here": loc})
    return out


def _draw(game, cases):
    """一次跑完：每一種畫一張第一層（nearFit 的取景、nearParts 的上下兩張）。"""
    script = """
const out = [];
for (const c of H.S.cases) {
  H.S.mapState = c.st;
  const v = H.nearFit(H.S.mapBase, c.st, c.vw, c.vh, 58, c.vw >= 900 ? 0 : 54);
  out.push(v ? { k: 1 / v.s, parts: H.nearParts(H.S.mapBase, c.st, { v, vw: c.vw, vh: c.vh, sel: c.sel }) } : null);
}
return out;
"""
    payload = {"m": server.main_view(game), "script": script,
               "S": {"mapBase": game.map_base(), "mapState": game.map_state(), "mapLayer": "near", "mapRegion": "yingru", "cases": cases},
               "menxia": None, "stored": {}, "responses": {}}
    return webharness.run(DRIVER, payload)


def _scan(svg: str):
    """畫出來的那一張：點得到的透明框照畫的先後 [(種類, 地點, 框)]（框是地圖座標 [x0, y0, x1, y1]；小圖那一組照它的 translate／scale 換算）、
    小圖 {地點: 中心}、名字 {地點: [那幾行的框]}。"""
    stack, hits, icons, labels = [], [], {}, {}
    for m in TAG.finditer(svg):
        close, tag, attrs = m.group(1), m.group(2), dict(ATTR.findall(m.group(3)))
        if tag == "g":
            if close:
                stack.pop()
                continue
            stack.append(attrs)
            if attrs.get("class") in ("n-faint", "n-icon"):
                tx, ty, _ = (float(n) for n in MOVE.search(attrs["transform"]).groups())
                icons[attrs["data-id"]] = (tx, ty)
            continue
        if tag != "rect" or close or attrs.get("fill-opacity") != "0":
            continue
        owner = attrs if "data-act" in attrs else next((g for g in reversed(stack) if "data-act" in g), None)
        if owner is None:
            continue
        x, y, w, h = (float(attrs[n]) for n in ("x", "y", "width", "height"))
        box = [x, y, x + w, y + h]
        for g in reversed(stack):
            mv = MOVE.search(g.get("transform", ""))
            if mv:
                gx, gy, s = (float(n) for n in mv.groups())
                box = [gx + box[0] * s, gy + box[1] * s, gx + box[2] * s, gy + box[3] * s]
        kind = owner.get("class") or owner["data-act"]
        hits.append((kind, owner.get("data-id"), box))
        if kind == "n-label":
            labels.setdefault(owner["data-id"], []).append(box)
    return hits, icons, labels


def _inside(box, x, y) -> bool:
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def _top(hits, x, y):
    """點 (x, y) 落在哪一塊：最上面（最後畫的）那一塊。"""
    return next(((kind, pid) for kind, pid, box in reversed(hits) if _inside(box, x, y)), (None, None))


def _you(high: str, k: float):
    """上面那一張的你：朱圈的中心、「你・地名」的中間（基線往上半個字）。在路上沒有。"""
    ring = re.search(r'<circle class="r-you" cx="([-\d.]+)" cy="([-\d.]+)" r="[-\d.]+" fill="#F7F1E3"', high)
    name = re.search(r'<text class="n-you-name" x="([-\d.]+)" y="([-\d.]+)" font-size="([-\d.]+)"', high)
    if not ring:
        return []
    fs = float(name.group(3))
    return [(float(ring.group(1)), float(ring.group(2))), (float(name.group(1)), float(name.group(2)) - 0.4 * fs)]


def _check(case, out):
    """一張圖的不變量；回 [壓到別處小圖的名字（那一處, 名字）…]（測試有沒有牙）。"""
    low, high = out["parts"]
    hits, icons, labels = _scan(low)
    here, where = case["here"], f"站{case['here']}・{case['vw']}×{case['vh']}・點{case['sel']}"
    for pid, (x, y) in icons.items():
        assert _top(hits, x, y)[1] == pid, f"{where}：點 {pid} 的小圖，選到的是 {_top(hits, x, y)}"
    you = _you(high, out["k"])
    if you:  # 朱圈選你腳下；「你・地名」選你腳下，字壓著別處的小圖時那一點是小圖（點地點優先於點字）
        (rx, ry), (nx, ny) = you
        assert _top(hits, rx, ry)[1] == here, f"{where}：點你（腳下 {here}），選到的是 {_top(hits, rx, ry)}"
        icon_under = {owner for kind, owner, b in hits if kind == "n-hit" and owner != here and _inside(b, nx, ny)}
        assert _top(hits, nx, ny) in {("n-hit", pid) for pid in {here} | icon_under}, f"{where}：點「你・地名」，選到的是 {_top(hits, nx, ny)}"
    covered = []
    for pid, rows in labels.items():
        mine = [b for kind, owner, b in hits if kind == "n-label" and owner == pid]
        later = {owner for kind, owner, b in hits[hits.index(next(h for h in hits if h[0] == "n-label" and h[1] == pid)) + 1:] if kind == "n-label"}
        for box in rows:
            for fx in (0.1, 0.3, 0.5, 0.7, 0.9):
                for fy in (0.25, 0.75):
                    x, y = box[0] + (box[2] - box[0]) * fx, box[1] + (box[3] - box[1]) * fy
                    kind, got = _top(hits, x, y)
                    under = {owner for kd, owner, b in hits if kd == "n-hit" and _inside(b, x, y)}
                    over = {owner for owner in later if any(_inside(b, x, y) for kd, o, b in hits if kd == "n-label" and o == owner)}
                    assert got in {pid} | under | over, f"{where}：點 {pid} 的名字 ({x:.0f},{y:.0f})，選到的是 {got}"
                    assert kind not in (None, "region-blank"), f"{where}：點 {pid} 的名字沒反應"
        assert mine, pid
        covered += [(other, pid) for other, (x, y) in icons.items() if other != pid and any(_inside(b, x, y) for b in rows)]
    return covered


@pytest.mark.parametrize("faction", ["guan", "huang"])
def test_a_name_never_swallows_another_places_tap(faction):
    """每一處各站一次、幾種地圖框、沒點與第二層：點小圖、你、名字都照上面的不變量。這一批裡要真的有名字壓在別處小圖上的情形（不然測不到）。"""
    game = _game(faction)
    places = sorted(game.map_state()["places"])
    cases = _cases(game, places)
    covered = []
    for case, out in zip(cases, _draw(game, cases)):
        if out is not None:
            covered += _check(case, out)
    assert len(covered) >= 10, covered  # 修之前這幾十處點小圖選到的都是壓在上面的名字


def test_fb877_the_reported_spot_changshe_under_the_yingshui_name():
    """回報那一例：黃巾站潁川郡（陽翟），地圖框 375×667：潁水河畔的名字蓋著長社的小圖——點長社選到長社，點你選到你腳下。"""
    game = _game("huang")
    game.state.player.location = "yingchuan"
    case = {"st": game.map_state(), "vw": 375, "vh": 667, "sel": None, "here": "yingchuan"}
    out = _draw(game, [case])[0]
    hits, icons, labels = _scan(out["parts"][0])
    x, y = icons["changshe"]
    assert any(_inside(b, x, y) for b in labels["yingshui"])  # 名字真的壓在長社的小圖上（畫面沒改）
    assert _top(hits, x, y) == ("n-hit", "changshe")  # 修前：("n-label", "yingshui")
    for x, y in _you(out["parts"][1], out["k"]):  # 朱圈、「你・地名」
        assert _top(hits, x, y) == ("n-hit", "yingchuan")  # 修前：底下沒有東西（點空白，收起卡）或別處的名字
    _check(case, out)
