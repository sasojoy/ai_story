"""輿圖第三版第 4 批：區圖與卡（輿圖簡化設計 5.2、5.3、5.4、5.6、第十二章；計畫 docs/superpowers/plans/2026-10-21-輿圖v3-區圖與卡.md）。
點一區進的是區圖：同一張底圖換一個固定的取景（regionFit），只畫這一區的地點——墨筆小圖、印章框（框色＝誰的，顏色照劇本）、框裡下緣的進度條
（攻方的顏色；剛易手整條灰、不寫字：FB-648 第二段乙）、朱印「寶」、名字底下的意境字、你的朱圈與旗、鄰區出口；「塗層」開了多一層淡彩；
擠不下時這一區的名字縮一號。點一處抽屜半開那一處的卡。
在 node 裡跑整支 app.js（tests/webharness.py），餵伺服器真的會給的底圖、疊層與 main_view（翻地那一份）；沒有 node 就略過。
FB-711（QA 2026-10-22）：FB-648 的掃描那一條（test_fb648_no_name_frame_overlaps_or_moves_while_blocks_flip）一組單跑最久約 41 秒，
webharness 預設 60 秒逾時在有負載的機器上會紅：那一條的逾時給 FLIP_TIMEOUT（240 秒），掃描本身不拆、不改。"""
from __future__ import annotations

import math
import random
import re
from pathlib import Path

import pytest
import test_prologue_web
from conftest import classic_rules, no_conquest, real_content
from conquest_kit import conquest_game, conquest_rules

import server
import webharness
from tianxia import conquest, territory
from tianxia.engine import Game
from tianxia.models import FactionDef, FactionInk
from tianxia.sqlite_world import open_world
from tianxia.state import TerritoryState

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]
NAMES = ["S", "pageMap", "regionFit", "regionLabels", "regionExits", "regionParts", "regionTopHtml", "placeCard", "placeLine",
         "flipSection", "drawerHtml", "worldDrawerHtml", "sideInk", "sideText", "regionCrowded"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
APP = webharness.APP  # 三個檔（main.js、map.js、app.js）接起來的那一份
# 地圖框（寬 × 高）：實機量的。375×812 → 375×604（2026-10-21 map4.localhost，狀態列多一行心得提示、商城開著）、375×624（第 3 批量的）、
# 375×667 → 375×479、360×640 → 360×452／360×436
PHONES = [(375, 604), (375, 624), (375, 479), (360, 452), (360, 436)]


def _game(content=None, faction="guan", at="yingchuan", conquest_on=True, profile="week7"):
    c = content or real_content(profile)
    if conquest_on:
        conquest_rules(c)
    else:
        no_conquest(c)  # PM 2026-10-22 起正式內容打開，關著的季要明講
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    territory.update(game.state.world, c)
    game.state.player.faction, game.state.player.location = faction, at
    return game


def run(game, script, st=None, m=None, timeout=60, **S):
    payload = {"m": m or server.main_view(game), "script": script,
               "S": {"mapBase": game.map_base(), "mapState": st or game.map_state(), "mapLayer": "region", "mapRegion": "yingru", **S},
               "menxia": None, "stored": {}, "responses": {}}
    return webharness.run(DRIVER, payload, timeout=timeout)


def parts(game, rid="yingru", vw=375, vh=604, wash=False, st=None, m=None):
    return run(game, f"const v = H.regionFit(H.S.mapBase, '{rid}', {vw}, {vh}); return H.regionParts(H.S.mapBase, H.S.mapState, {{ v, vw: {vw}, vh: {vh}, rid: '{rid}', wash: {str(wash).lower()} }});",
               st=st, m=m, mapRegion=rid)


def _group(low, loc, cls="r-label"):
    """那一處的名字框那一組（<g class="r-label" data-act="region-place" data-id="…">…</g>）。"""
    start = low.index(f'<g class="{cls}" data-act="region-place" data-id="{loc}"')
    return low[start:low.index("</g>", low.index(">", start) + 1 if cls == "r-icon" else start) + 4]


def _label(low, loc):
    start = low.index(f'<g class="r-label" data-act="region-place" data-id="{loc}"')
    depth, i = 0, start
    while True:  # 名字框裡還有朱印那一個 <g>：照深度找收尾
        nxt_open, nxt_close = low.find("<g", i + 1), low.find("</g>", i + 1)
        if nxt_open != -1 and nxt_open < nxt_close:
            depth, i = depth + 1, nxt_open
        elif depth:
            depth, i = depth - 1, nxt_close
        else:
            return low[start:nxt_close + 4]


# ── 取景 ──
@pytest.mark.parametrize("vw,vh", PHONES + [(320, 344), (1100, 700)])
def test_region_fit_frames_every_place_of_the_region(vw, vh):
    """每一區的地點都在畫面裡、上面那一排底下、收著的抽屜上面（設計 5.2：固定取景，這一區地點的外框加邊）；倍率最多 2。"""
    game = _game()
    out = run(game, f"return H.S.mapBase.regions.map((r) => [r.id, H.regionFit(H.S.mapBase, r.id, {vw}, {vh})]);")
    places = game.map_base()["places"]
    for rid, v in out:
        assert 0 < v["s"] <= 2, rid
        for p in (x for x in places if x["region"] == rid):
            x, y = vw / 2 + (p["x"] - v["cx"]) * v["s"], vh / 2 + (p["y"] - v["cy"]) * v["s"]
            assert 0 <= x <= vw and 58 <= y <= vh - 54, (rid, p["id"], x, y)


def test_region_fit_leaves_room_for_the_half_open_card_when_it_can():
    """手機上優先替半開的卡留位子（卡不蓋到地點，地圖不動）：留了倍率還不低於 REGION_READ 才留，不然照整塊放（矮的螢幕，卡會蓋到下緣）；
    潁川汝南在 375 寬是照寬度定的（約 0.68 倍），底下本來就空著。"""
    game = _game()
    read = float(re.search(r"REGION_READ = ([\d.]+)", APP.read_text(encoding="utf-8")).group(1))
    places = game.map_base()["places"]
    for vh in (604, 479):
        fits = dict(run(game, f"return H.S.mapBase.regions.map((r) => [r.id, H.regionFit(H.S.mapBase, r.id, 375, {vh})]);"))
        for rid, v in fits.items():
            ys = [p["y"] for p in places if p["region"] == rid]
            leave = (vh - 58 - 54 - 70 - 270) / max(1, max(ys) - min(ys))
            if leave >= read:
                assert vh - v["bottom"] >= 270 - 0.5, (vh, rid)
    tall = dict(run(game, "return H.S.mapBase.regions.map((r) => [r.id, H.regionFit(H.S.mapBase, r.id, 375, 604)]);"))
    peek = float(re.search(r"REGION_PEEK_MIN = ([\d.]+)", APP.read_text(encoding="utf-8")).group(1))
    # 潁川汝南照寬度定倍率（約 0.68），底下空著的放得下最矮的半開卡（卡的高度照空著多少，peekPx）
    assert tall["yingru"]["s"] == pytest.approx((375 - 16) / (813 - 285), abs=0.01) and 604 - tall["yingru"]["bottom"] - 4 >= peek
    assert any(604 - v["bottom"] >= 270 and rid != "yingru" for rid, v in tall.items())  # 小的大區真的有留


# ── 只畫這一區、印章框、寶、意境字、進度條、冷卻、你、出口 ──
def test_only_that_regions_places_are_drawn():
    game = _game()
    places = game.map_base()["places"]
    for rid in ("yingru", "luoyang", "nanyang"):
        low, _ = parts(game, rid)
        drawn = set(re.findall(r'class="r-icon" data-act="region-place" data-id="([a-z_]+)"', low))
        assert drawn == {p["id"] for p in places if p["region"] == rid}, rid
        assert set(re.findall(r'class="r-label" data-act="region-place" data-id="([a-z_]+)"', low)) == drawn


def test_stamp_frames_take_the_holders_colours_and_big_towns_are_thicker():
    """印章框的底色＝控制方的 tint、框線＝color（顏色照劇本 sideInk）；沒人佔照底圖的 unheld 調；大城框線粗一點。墨筆小圖的線色同框線。"""
    game = _game()
    st, base = game.map_state(), game.map_base()
    ink = {s["id"]: s for s in base["world"]["sides"]}
    low, _ = parts(game)
    frames = dict(re.findall(r'data-id="([a-z_]+)"[^>]*>\s*<rect class="r-frame"[^>]*fill="(#[0-9A-F]{6})"', low))
    strokes = {loc: float(w) for loc, w in re.findall(r'data-id="([a-z_]+)"[^>]*>\s*<rect class="r-frame"[^>]*stroke-width="([\d.]+)"', low)}
    held = [p for p in base["places"] if p["region"] == "yingru" and st["places"][p["id"]]["control"]]
    free = [p for p in base["places"] if p["region"] == "yingru" and not st["places"][p["id"]]["control"]]
    assert held and free
    for p in held:
        assert frames[p["id"]] == ink[st["places"][p["id"]]["control"]]["tint"], p["id"]
    unheld = {frames[p["id"]] for p in free}
    assert len(unheld) == 1 and unheld.isdisjoint({s["tint"] for s in ink.values()})
    big = next(p for p in held if p["big"]); small = next(p for p in held if not p["big"])
    assert strokes[big["id"]] > strokes[small["id"]]
    icon = _group(low, held[0]["id"], "r-icon")
    assert f'stroke="{ink[st["places"][held[0]["id"]]["control"]]["color"]}"' in icon


def test_rich_places_get_the_red_seal_whoever_holds_them():
    game = _game()
    st = game.map_state()
    rich = [x for x, p in st["places"].items() if p["rich"] and x in {q["id"] for q in game.map_base()["places"] if q["region"] == "yingru"}]
    low, _ = parts(game)
    assert rich and all('class="r-seal"' in _label(low, x) and ">寶<" in _label(low, x) for x in rich)
    assert low.count('class="r-seal"') == len(rich)


def test_insight_words_sit_under_the_name_strongest_first_at_most_two():
    game = _game()
    base = game.map_base()
    low, _ = parts(game)
    kinds = base["insight_kinds"]
    for p in (q for q in base["places"] if q["region"] == "yingru"):
        words = re.findall(r'class="r-ins"[^>]*>([^<]+)<', _label(low, p["id"]))
        assert words == [kinds[i]["name"] for i in p["insights"]][:2], p["id"]


def _rect(svg, cls):
    m = re.search(rf'<rect class="{cls}"[^>]*x="([\d.-]+)" y="([\d.-]+)" width="([\d.]+)" height="([\d.]+)"', svg)
    x, y, w, h = map(float, m.groups())
    return x, y, x + w, y + h


def test_progress_bars_show_the_top_attacker_and_cooling_is_grey():
    """進度條（設計 5.2、4.1）：進度最高的那一方的顏色、長度照進度；守方自己的不畫；剛易手整條灰。
    FB-648 第二段乙（企劃者 2026-10-22）：進度條收在印章框裡的下緣（在名字的字底下、框線裡面），冷卻不寫「冷卻 N 分」（幾分鐘寫在卡上）。"""
    from test_world_map import flipping

    game = flipping(_game())
    st = game.map_state()
    ink = {s["id"]: s for s in game.map_base()["world"]["sides"]}
    low, _ = parts(game)
    wilds = _label(low, "runan_wilds")  # 中立地：官軍 60、黃巾 25 → 畫官軍那一條、六成
    frame, track = _rect(wilds, "r-frame"), _rect(wilds, "r-bar")
    fill = re.search(r'class="r-bar-fill" data-side="([a-z]+)"[^>]*width="([\d.]+)"[^>]*fill="(#[0-9A-F]{6})"', wilds)
    assert fill.group(1) == "guan" and float(fill.group(2)) == pytest.approx((track[2] - track[0]) * 0.6, abs=0.15) and fill.group(3) == ink["guan"]["color"]
    baseline = float(re.search(r'<text x="[\d.]+" y="([\d.]+)"', wilds).group(1))
    assert frame[0] < track[0] and track[2] < frame[2] and baseline < track[1] and track[3] < frame[3]  # 框裡的下緣、名字底下
    assert frame[3] - track[3] < 1.5  # 貼著框線內側
    assert 'data-side="huang"' in _label(low, "yingchuan_wilds")  # 官軍的地被黃巾推：畫黃巾那一條
    cool = _label(low, "hilltop_wilds")
    assert 'class="r-bar"' in cool and "r-bar-fill" not in cool and "冷卻" not in cool and "r-cool" not in low
    assert _rect(cool, "r-bar")[3] < _rect(cool, "r-frame")[3]
    n = st["places"]["hilltop_wilds"]["cool"]
    assert f"{n} 分後才能再推" in run(game, 'return H.placeCard(H.S.mapBase, H.S.mapState, "hilltop_wilds");')  # 幾分鐘寫在卡上
    assert "r-bar" not in _label(low, "yingchuan")  # 沒人推、沒冷卻：沒有進度條


def test_you_get_a_red_ring_and_flag_in_every_region():
    """以前只有你站的那一區畫你（別區上面那一張是空的：取景框外蓋著紙、拖不出去）。全區選甲（FB-876）之後別區拖得過來，
    企劃者 2026-10-26（FB-884）決定「全區看別區時也畫出你站的位置（朱圈），跟本區一樣」：別區也畫朱圈、跳的圈與旗，圓心在你腳下那一處；
    斷言照翻過來，新規則的測試在 tests/web/test_fb884_region_you_marker_web.py。"""
    game = _game()
    _, high = parts(game, "yingru")
    assert 'class="r-you"' in high and 'class="pulse"' in high
    _, other = parts(game, "nanyang")
    assert 'class="r-you"' in other and 'class="pulse"' in other
    assert re.search(r'class="r-you" cx="464" cy="940"', other) and re.search(r'class="r-you" cx="464" cy="940"', high)  # 都在潁川郡（你站的地方）


def test_exits_name_the_neighbour_region_and_lead_there():
    """通到鄰區的路畫到框邊、寫「→ 南陽」（箭頭照出去的方向），點了換到那一區（data-act="region-go"）。"""
    game = _game()
    low, _ = parts(game)
    exits = re.findall(r'class="r-exit" data-act="region-go" data-id="([a-z]+)"[^>]*>.*?>([←→↑↓]) ([^<]+)</text>', low)
    names = {r["id"]: r["name"] for r in game.map_base()["regions"]}
    assert exits and all(names[rid] == name for rid, _, name in exits)
    assert {rid for rid, _, _ in exits} >= {"luoyang", "nanyang"}


def test_the_wash_toggle_only_adds_one_layer():
    """塗層開關前後只差那一層（設計第十二章）：開著多一組濾鏡與一層照歸屬的淡彩（每一處有控制方的地點一團 soft），其餘一個字不差。"""
    game = _game()
    plain, _ = parts(game)
    washed, _ = parts(game, wash=True)
    stripped = re.sub(r'<defs><filter id="r-wash".*?</filter></defs>', "", washed, count=1)
    stripped = re.sub(r'<g class="r-wash-layer".*?</g>', "", stripped, count=1)
    assert stripped == plain and washed != plain
    layer = re.search(r'<g class="r-wash-layer"[^>]*>(.*?)</g>', washed).group(1)
    st = game.map_state()
    held = [p for p in game.map_base()["places"] if p["region"] == "yingru" and st["places"][p["id"]]["control"]]
    assert layer.count("<circle") == len(held)


def test_the_region_top_row():
    """全區上面一排（減法季整合設計第七章：大區名、全區、天下）：大區名下拉（每一區一個、這一區選著）、塗層（只在全區）、全區（按著）、天下；
    搜尋與 ⏱ 版圖在天下圖那一排。"""
    game = _game()
    out = run(game, "return H.regionTopHtml();")
    assert 'data-act="map-world"' in out and 'data-act="map-full"' in out and 'data-act="map-wash"' in out and "map-timeline" not in out
    options = re.findall(r'<option value="([a-z]+)"( selected)?>', out)
    assert [x for x, _ in options] == [r.id for r in game.content.map.regions] and [x for x, s in options if s] == ["yingru"]
    assert "map-search" not in out and out.index("region-pick") < out.index("map-wash") < out.index("map-full") < out.index("map-world")


def _four_sides():
    """四方的測試劇本（設計 3.3、第十二章）：官軍、黃巾之外加魏、吳（各自的顏色）；潁川汝南的區塊照方位分給四方。"""
    c = real_content("week7")
    c.scenario.factions = [f for f in c.scenario.factions if f.id != "haoqiang"] + [
        FactionDef(id="wei", name="魏", ink=FactionInk(color="#6A3D7A", soft="#C3A6CC", tint="#EADCEF", short="魏", label="魏")),
        FactionDef(id="wu", name="吳", ink=FactionInk(color="#2E7D5B", soft="#9FD1B8", tint="#DCEFE5", short="吳", label="吳")),
    ]
    c.scenario.territory.lines = {}
    game = _game(content=c, conquest_on=False)
    sides = ["guan", "huang", "wei", "wu"]
    mine = [p["id"] for p in game.map_base()["places"] if p["region"] == "yingru"]
    cx = sum(c.locations[x].x for x in mine) / len(mine)
    cy = sum(c.locations[x].y for x in mine) / len(mine)
    control = {x: sides[int(((math.atan2(c.locations[x].y - cy, c.locations[x].x - cx) + math.pi / 4) % (2 * math.pi)) // (math.pi / 2))] for x in mine}
    game.state.world.territory = TerritoryState(control=control)
    return game, control


def test_four_sides_frames_and_bars_take_each_sides_colour():
    game, control = _four_sides()
    st = game.map_state()
    pusher = "wu" if control["changshe"] == "wei" else "wei"
    st["places"]["changshe"]["tug"] = {pusher: 40}  # 別的一方在推長社：進度條是那一方的顏色
    low, _ = parts(game, st=st)
    ink = {"guan": ("#3D5F8F", "#DCE5F0"), "huang": ("#B9821A", "#F4E7C2"), "wei": ("#6A3D7A", "#EADCEF"), "wu": ("#2E7D5B", "#DCEFE5")}
    for loc, side in control.items():
        assert re.search(rf'<rect class="r-frame"[^>]*fill="{ink[side][1]}"[^>]*stroke="{ink[side][0]}"', _label(low, loc)), loc
    assert len(set(control.values())) == 4
    assert f'data-side="{pusher}"' in _label(low, "changshe") and f'fill="{ink[pusher][0]}"' in _label(low, "changshe")


def test_no_sides_are_hardcoded_in_the_region_map_and_card_code():
    """設計 3.3：區圖與卡那一段不寫死陣營 id、陣營名與藍黃灰（顏色一律 sideInk、沒人佔照底圖的 unheld）。"""
    src = APP.read_text(encoding="utf-8").replace("\r\n", "\n")
    blocks = [src[src.index("  // ── 區圖（輿圖簡化設計 5.2"):src.index("  // ── 底圖烤成一張圖")],
              src[src.index("  // ── 卡（輿圖簡化設計 5.3）"):src.index("  // 找地點、找人物（設計第五節）")]]
    for block in blocks:
        for word in ('"guan"', '"huang"', '"haoqiang"', "官軍", "黃巾", "豪強", "MAP_SIDES", "#9DB4D3", "#E7C778", "#D2CBBC", "#DCE5F0", "#F4E7C2"):
            assert word not in block, word


# ── 名字框不互相壓（設計第十二章：375 寬每個地名框不互相壓到）──
OVERLAP = """
const inter = (a, b) => Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
const out = [];
for (const r of H.S.mapBase.regions) {
  const v = H.regionFit(H.S.mapBase, r.id, VW, VH);
  const L = H.regionLabels(H.S.mapBase, H.S.mapState, r.id, v, VW, VH), ex = H.regionExits(H.S.mapBase, r.id, v, VW, VH, L);
  const z = v.s >= 1 ? 12.5 : 10.5, zh = v.s >= 1 ? 11.5 : 10;
  for (let i = 0; i < L.length; i++) {
    for (const a of L[i].rows) if (a[0] < 0 || a[2] > VW) out.push([r.id, L[i].id, "screen"]);
    for (let j = 0; j < L.length; j++) {
      if (j > i) for (const a of L[i].rows) for (const b of L[j].rows) if (inter(a, b) > 0.5) out.push([r.id, L[i].id, L[j].id]);
      if (j !== i) for (const a of L[i].rows) if (inter(a, [L[j].X - z, L[j].Y - zh, L[j].X + z, L[j].Y + zh]) > 0.5) out.push([r.id, L[i].id, "icon:" + L[j].id]);
    }
    for (const e of ex) for (const a of L[i].rows) if (inter(a, e.box) > 2) out.push([r.id, L[i].id, "exit:" + e.text]);
  }
}
return out;
"""


@pytest.mark.parametrize("vw,vh", PHONES)
@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_region_labels_do_not_overlap_on_a_phone(profile, vw, vh):
    """375／360 寬：每一區的名字框兩兩不相交、不壓別處的小圖與鄰區出口、不出畫面（潁川汝南 17 處最擠）。名字框只貼著小圖擺、不拉線
    （企劃者 2026-10-21 從對比圖選乙）。320 寬（地圖框 320×344）潁川汝南放不開，先這樣（PM 2026-10-21，同企劃者「320 寬先這樣」）。"""
    game = _game(profile=profile)
    assert run(game, OVERLAP.replace("VW", str(vw)).replace("VH", str(vh))) == []


# FB-648：開季那一刻量不到的局面——第一段那一版翻地中名字框會變大（攻方在推多一條進度條、剛易手多一行「冷卻 N 分」；第二段照乙收進框裡、
# 不寫字，框的大小就不變了），你站的那一處多朱圈與旗。
# QA 量到的那幾組（試玩回饋 FB-648 與檔尾那一節，scratchpad 的 lbl.py、lbl2.py）：黃巾推潁川郊野 40（甲）、汝南荒野官軍 65／黃巾 12（乙）、
# 潁水河畔剛被黃巾推滿在冷卻（丙）；上一批開發的 test_world_map.flipping() 那一組也一起量
def _qa_push(game, combo):
    w, c = game.state.world, game.content
    pushes = {"甲": [("yingchuan_wilds", "huang", 40)], "乙": [("runan_wilds", "guan", 65), ("runan_wilds", "huang", 12)], "丙": [("yingshui", "huang", 100)]}
    for k in combo:
        for loc, side, n in pushes[k]:
            conquest.push(w, c, loc, side, "推" + k + side, n, "attack")
    return game


@pytest.mark.parametrize("vw,vh", PHONES)
@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_fb648_region_labels_do_not_overlap_while_flipping(profile, vw, vh):
    """FB-648：翻地進行中（潁川郊野有進度條、潁水河畔在冷卻）你站潁川郡，375／360 寬名字框互壓（修前 375 寬 4 對、360 寬 6 對）。
    名字框照樣只貼著小圖擺（企劃者選的乙）；第一輪的位置擺不開時第二輪沿著小圖四邊滑、你的朱圈照圓的算、鄰區出口原本的位置也讓開。
    QA 的幾組（甲丙、甲乙丙、只有甲、只有丙）與上一批的 flipping()，你站潁川郡、長社、汝南，每一個地圖框都 0 對。"""
    from test_world_map import flipping

    for at in ("yingchuan", "changshe", "runan"):
        for combo in ("甲丙", "甲乙丙", "甲", "丙", None):
            game = _game(profile=profile, at=at)
            game = _qa_push(game, combo) if combo else flipping(game)
            if combo and "丙" in combo:
                assert game.map_state()["places"]["yingshui"]["cool"]  # 剛易手：冷卻那一行在
            assert run(game, OVERLAP.replace("VW", str(vw)).replace("VH", str(vh))) == [], (at, combo)


GAPS = """
const v = H.regionFit(H.S.mapBase, 'yingru', VW, VH);
return H.regionLabels(H.S.mapBase, H.S.mapState, 'yingru', v, VW, VH).map((l) => {
  const f = l.rows[0], nx = Math.max(f[0], Math.min(f[2], l.X)), ny = Math.max(f[1], Math.min(f[3], l.Y));
  return Math.hypot(nx - l.X, ny - l.Y);
});
"""


@pytest.mark.parametrize("vw,vh", PHONES)
def test_fb648_names_stay_beside_their_own_icons_while_flipping(vw, vh):
    """FB-648：第二輪擺好的名字框不被擠到別處的小圖旁邊——QA 那一組（甲丙、你站潁川郡）每一個名字框離自己的小圖最遠的那一個，
    不比沒翻地時遠（第二輪先照「離自己的小圖多近」的先後一起找，往前挪也照近的挪）。"""
    plain = run(_game(profile="season21"), GAPS.replace("VW", str(vw)).replace("VH", str(vh)))
    flip = run(_qa_push(_game(profile="season21"), "甲丙"), GAPS.replace("VW", str(vw)).replace("VH", str(vh)))
    assert max(flip) <= max(plain) + 0.5, (round(max(flip)), round(max(plain)))


@pytest.mark.parametrize("vw,vh", PHONES[:3])
def test_fb648_your_ring_is_round_in_the_second_round(vw, vh):
    """FB-648 同一個原因：你站的那一處多了朱圈與旗。你站嵩山深處（左邊緊貼畫面、旁邊是嵩山腳、南華觀、潁川書院）時 375 寬第一輪擺不下
    （修前嵩山深處的框壓到潁川書院的小圖）；第二輪朱圈照圓的算，圓外那幾個角擺得進名字框。360 寬照樣擺不下（等企劃者挑畫法）。"""
    game = _game(profile="season21", at="deep_mountain")
    assert run(game, OVERLAP.replace("VW", str(vw)).replace("VH", str(vh))) == []


@pytest.mark.parametrize("vw,vh", [(375, 604), (375, 479)])
def test_fb648_a_neighbour_exit_never_lands_on_a_name_frame(vw, vh):
    """FB-648 同一個原因的另一種：第一輪擺得下名字框，可是鄰區出口（regionExits 在名字框擺好之後沿著邊滑）怎麼滑都會壓到名字框——
    洛陽、你站大將軍府、大將軍府被對面推（框下多一條進度條）。這種也當作第一輪沒擺好，第二輪把出口原本的位置讓開重擺。"""
    game = _game(profile="season21", at="dajiangjun_fu")
    w, c = game.state.world, game.content
    holder = game.map_state()["places"]["dajiangjun_fu"]["control"]
    conquest.push(w, c, "dajiangjun_fu", next(s for s in ("guan", "huang") if s != holder), "推甲", 40, "attack")
    assert game.map_state()["places"]["dajiangjun_fu"]["tug"]
    assert run(game, OVERLAP.replace("VW", str(vw)).replace("VH", str(vh))) == []


# FB-648 第二段（企劃者 2026-10-22 選乙）的掃描：每一區、你站每一處與在路上 × 沒人推／能推的塊一塊一塊有進度條或冷卻／全部有進度條／
# 全部冷卻／隨機配的，五個手機地圖框——名字框都不互壓（OVERLAP 同一套量法）、翻地不挪任何一個名字（擺的位置與字級跟沒翻地時一樣）、
# 名字離自己的小圖最遠的那一個不比上一輪（第一段那一版）沒翻地時量到的遠（GAP_LAST）。第一段那一版（甲）同一套掃描：潁川汝南 170＋146、
# 南陽 73＋21、洛陽 15＋27、冀州 0＋0、幽州 11＋4 種局面互壓（「＋」前是一塊一塊來的，後是沒人推與全部一起的）
FLIP_SWEEP = """
const inter = (a, b) => Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
const base = H.S.mapBase, st0 = H.S.mapState, rid = H.S.rid, capt = H.S.capt, sides = base.world.sides.map((s) => s.id);
function bad(L, ex, v, VW) {
  const out = [], z = v.s >= 1 ? 12.5 : 10.5, zh = v.s >= 1 ? 11.5 : 10;
  for (let i = 0; i < L.length; i++) {
    for (const a of L[i].rows) if (a[0] < 0 || a[2] > VW) out.push([L[i].id, "screen"]);
    for (let j = 0; j < L.length; j++) {
      if (j > i) for (const a of L[i].rows) for (const b of L[j].rows) if (inter(a, b) > 0.5) out.push([L[i].id, L[j].id]);
      if (j !== i) for (const a of L[i].rows) if (inter(a, [L[j].X - z, L[j].Y - zh, L[j].X + z, L[j].Y + zh]) > 0.5) out.push([L[i].id, "icon:" + L[j].id]);
    }
    for (const e of ex) for (const a of L[i].rows) if (inter(a, e.box) > 2) out.push([L[i].id, "exit:" + e.text]);
  }
  return out;
}
function variant(assign, here) {  // assign：{ 地點: "bar"（對面推了 40）| "cool"（剛易手，冷卻 59 分）}；here：你站哪（"@road"＝在路上）
  const st = JSON.parse(JSON.stringify(st0));
  for (const [id, kind] of Object.entries(assign)) {
    const q = st.places[id];
    if (kind === "bar") { q.tug = { [sides.find((s) => s !== q.control)]: 40 }; q.cool = null; }
    if (kind === "cool") { q.control = q.control || sides[0]; q.tug = null; q.cool = 59; }
  }
  if (here === "@road") st.journey = { x: 0, y: 0 }; else { st.journey = null; st.here = here; }
  return st;
}
const gapOf = (l) => { const f = l.rows[0], nx = Math.max(f[0], Math.min(f[2], l.X)), ny = Math.max(f[1], Math.min(f[3], l.Y)); return Math.hypot(nx - l.X, ny - l.Y); };
let seed = 7;
const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
const ids = base.places.filter((p) => p.region === rid).map((p) => p.id), heres = [...ids, "@road"];
const fails = [], moved = [], gaps = [];
for (const [VW, VH] of H.S.phones) {
  const v = H.regionFit(base, rid, VW, VH);
  let far = 0;
  for (const here of heres) {
    const cases = [{}, Object.fromEntries(capt.map((id) => [id, "bar"])), Object.fromEntries(capt.map((id) => [id, "cool"]))];
    for (const id of capt) cases.push({ [id]: "bar" }, { [id]: "cool" });
    for (let n = 0; n < 2; n++) {
      const a = {};
      for (const id of capt) { const x = rnd(); if (x < 0.3) a[id] = "bar"; else if (x < 0.5) a[id] = "cool"; }
      cases.push(a);
    }
    let ref = null;
    for (const assign of cases) {
      const L = H.regionLabels(base, variant(assign, here), rid, v, VW, VH), b = bad(L, H.regionExits(base, rid, v, VW, VH, L), v, VW);
      if (b.length) fails.push([VW, VH, here, assign, b]);
      const sig = JSON.stringify(L.map((l) => [l.id, l.l, l.t, l.fs, l.insPx]));
      if (ref === null) ref = sig; else if (sig !== ref) moved.push([VW, VH, here, assign]);
      for (const l of L) far = Math.max(far, gapOf(l));
    }
  }
  gaps.push(far);
}
return { fails, moved, gaps };
"""
# 名字離自己的小圖最遠的那一個（px），照 PHONES 的順序：上一輪（第一段那一版 f46d237a）沒翻地、你站每一處與在路上量到的最遠
GAP_LAST = {"yingru": (55.7, 55.7, 55.7, 55.7, 55.7), "nanyang": (31.4, 60.9, 31.4, 31.4, 31.4), "luoyang": (55.7, 56.9, 31.4, 31.4, 31.4),
            "jizhou": (39.3, 39.3, 39.3, 39.3, 39.3), "youzhou": (61.9, 60.9, 51, 51, 51)}
FLIP_TIMEOUT = 240  # 秒：FB-711，單跑最久約 41 秒（weekend-yingru），留六倍給有負載的機器


@pytest.mark.parametrize("rid", ["yingru", "nanyang", "luoyang", "jizhou", "youzhou"])
@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_fb648_no_name_frame_overlaps_or_moves_while_blocks_flip(profile, rid):
    """FB-648 第二段乙：進度條收進框裡、冷卻不寫字（框的大小翻不翻地都一樣），擠不下時這一區的名字縮一號。掃描見 FLIP_SWEEP 上面那一段。"""
    game = _game(profile=profile)
    mine = {p["id"] for p in game.map_base()["places"] if p["region"] == rid}
    capt = [k for k, b in server.main_view(game)["conquest"]["blocks"].items() if b["capturable"] and k in mine]
    assert capt
    # FB-711（QA 2026-10-22）：潁川汝南那一組單跑約 40 秒（node 的 vm 裡一種局面約 7ms × 幾千種），webharness 預設 60 秒逾時，
    # 機器同時有別的工作（-n 4、別的子代理）就紅。掃描整組留著不拆（拆了要另外證明每一塊加起來是同一套），逾時給到 FLIP_TIMEOUT
    out = run(game, FLIP_SWEEP, rid=rid, capt=capt, phones=PHONES, mapRegion=rid, timeout=FLIP_TIMEOUT)
    assert out["fails"] == [] and out["moved"] == []
    assert all(g <= last + 0.5 for g, last in zip(out["gaps"], GAP_LAST[rid])), (out["gaps"], GAP_LAST[rid])


def test_fb648_what_counts_as_crowded():
    """FB-648 第二段乙「擠不下」的判斷（regionCrowded）一樣一樣來：兩個名字框相交、壓到別處的小圖、壓到你的旗、碰到你的朱圈
    （照真的那一圈，圓外的角不算）、壓到鄰區出口（出口的框有留白，多過 2px² 才算）、出了取景框；自己的小圖不算（名字本來就貼著它）。"""
    game = _game()
    out = run(game, """
const lab = (id, l, t) => ({ id, rows: [[l, t, l + 40, t + 19]] });
const icons = [[100, 100, 121, 120], [300, 100, 321, 120]], bounds = [2, 60, 370, 600];
const C = (labels, o = {}) => H.regionCrowded(labels, icons, o.flag || null, o.you || null, o.exits || [], bounds);
const a = lab("a", 124, 101), b = lab("b", 324, 101);
return {
  clean: C([a, b]),
  labels: C([a, lab("b", 150, 110)]),
  icon: C([a, lab("b", 80, 110)]),
  ownIcon: C([lab("a", 110, 101), b]),
  flag: C([a, b], { flag: [150, 95, 174, 123] }),
  ringNear: C([a, b], { you: [110, 130] }),
  ringCorner: C([a, b], { you: [108, 133] }),
  exitBig: C([a, b], { exits: [[160, 115, 200, 130]] }),
  exitSliver: C([a, b], { exits: [[163, 119, 200, 130]] }),
  outside: C([lab("a", 124, 50), b]),
};""")
    assert out == {"clean": False, "labels": True, "icon": True, "ownIcon": False, "flag": True, "ringNear": True, "ringCorner": False,
                   "exitBig": True, "exitSliver": False, "outside": True}


# FB-651：不同地點的兩列（印章框＋朱印寶那一列、意境字那一列）之間至少隔 R_ROW_GAP px——QA：南陽 375×479 南陽官道的意境字「風火」
# 那一列貼著南陽郊野的朱印「寶」（模型的列只隔 1.4px，畫出來的字形框還交疊 0.35px），讀起來像「南陽郊野 寶 風火」。
# 量法：兩列在 x、y 兩個方向的間隔取大的（兩列錯開到對角也算隔開；x、y 都不到 R_ROW_GAP 才算貼著）
ROW_GAPS = """
const out = [];
const gap = (a, b) => Math.max(a[0] - b[2], b[0] - a[2], a[1] - b[3], b[1] - a[3]);
for (const rid of H.S.rids) {
  const ids = H.S.mapBase.places.filter((p) => p.region === rid).map((p) => p.id);
  for (const [VW, VH] of H.S.phones) {
    const v = H.regionFit(H.S.mapBase, rid, VW, VH);
    for (const here of H.S.heres ? [...ids, "@road"] : [H.S.mapState.here]) {
      const st = { ...H.S.mapState, journey: here === "@road" ? { x: 0, y: 0 } : null, here: here === "@road" ? H.S.mapState.here : here };
      const L = H.regionLabels(H.S.mapBase, st, rid, v, VW, VH);
      for (let i = 0; i < L.length; i++) for (let j = i + 1; j < L.length; j++) {
        let low = Infinity;
        for (const a of L[i].rows) for (const b of L[j].rows) low = Math.min(low, gap(a, b));
        if (low < H.S.need) out.push([rid, VW, VH, here, L[i].id, L[j].id, Math.round(low * 10) / 10]);
      }
    }
  }
}
return out;
"""
ROW_GAP = float(re.search(r"R_ROW_GAP = ([\d.]+)", APP.read_text(encoding="utf-8")).group(1)) if "R_ROW_GAP = " in APP.read_text(encoding="utf-8") else 3.0


def test_fb651_nanyang_road_insights_keep_clear_of_nanyang_wilds_seal():
    """FB-651 QA 那一處：南陽 375×479（375×667 狀態列兩行），南陽官道的意境字那一列與南陽郊野那一列（印章框＋寶）至少隔 R_ROW_GAP（修前 1.4px）。"""
    assert ROW_GAP >= 2
    game = _game(profile="season21")
    out = run(game, ROW_GAPS, rids=["nanyang"], phones=[(375, 479)], heres=False, need=ROW_GAP, mapRegion="nanyang")
    assert not [x for x in out if {x[4], x[5]} == {"nanyang_road", "nanyang_wilds"}], out
    assert out == []


# FB-651 照不相交擺好之後再找「隔得開」的擺法，名字不准因此離自己的小圖更遠 R_NEAR 以上、不為了留空縮字：照這個規矩還隔不開的局面
# （區, 地圖框寬, 高, 你站哪）——2026-10-22 量的，weekend、season21 一樣，修前 238 對、這裡 30 對；多半是你站嵩山深處、南陽 375×624（大一號的字）。
# 只准變少（交 PM：要不要為了留空縮一號，計畫第四節）
TIGHT_LEFT = {
    ("youzhou", 375, 604, "zhuo_militia_hall"),
    *(("yingru", 375, h, "deep_mountain") for h in (604, 624, 479)),
    *(("yingru", 360, h, here) for h in (452, 436) for here in ("yingshui", "deep_mountain", "huangjin_camp")),
    *(("nanyang", 375, 624, here) for here in ("nanyang_huangjin_camp", "yu_river", "lulin_zhai", "@road")),
}


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_fb651_rows_of_different_places_keep_apart(profile):
    """FB-651：每一區 × 你站每一處與在路上 × 五個手機地圖框（同 FB-648 掃描；名字框的大小不看翻地，沒翻地的這一套就是全部），
    不同地點的兩列之間都隔 R_ROW_GAP——只有 TIGHT_LEFT 那幾種照這個規矩隔不開（修前 238 對，這裡最多 30 對），QA 那一對（南陽官道、
    南陽郊野）哪一種都隔得開。"""
    game = _game(profile=profile)
    rids = [r["id"] for r in game.map_base()["regions"]]
    out = run(game, ROW_GAPS, rids=rids, phones=PHONES, heres=True, need=ROW_GAP - 0.05)
    assert {tuple(x[:4]) for x in out} <= TIGHT_LEFT, sorted({tuple(x[:4]) for x in out} - TIGHT_LEFT)
    assert len(out) <= 30
    assert not [x for x in out if {x[4], x[5]} == {"nanyang_road", "nanyang_wilds"}]


def test_fb651_keeping_apart_never_moves_a_name_farther_from_its_icon():
    """FB-651 的代價有上限：為了讓兩列隔開而換的位置，每一處的名字離自己的小圖不比照不相交擺的那一次遠 R_NEAR（8px）以上；
    掃描裡名字離自己的小圖最遠的那一個跟修前一樣（GAP_LAST 照舊）。"""
    game = _game(profile="season21")
    out = run(game, """
const hug = (l) => { const f = l.rows[0]; return Math.hypot(Math.max(f[0] - l.X, 0, l.X - f[2]), Math.max(f[1] - l.Y, 0, l.Y - f[3])); };
const out = [];
for (const r of H.S.mapBase.regions) for (const [VW, VH] of H.S.phones) {
  const v = H.regionFit(H.S.mapBase, r.id, VW, VH);
  out.push([r.id, VW, VH, Math.max(...H.regionLabels(H.S.mapBase, H.S.mapState, r.id, v, VW, VH).map(hug))]);
}
return out;""", phones=PHONES)
    last = {rid: dict(zip(PHONES, vals)) for rid, vals in GAP_LAST.items()}
    for rid, vw, vh, far in out:
        assert far <= last[rid][(vw, vh)] + 0.5, (rid, vw, vh, far)


LAYOUT = """
const v = H.regionFit(H.S.mapBase, 'RID', VW, VH);
return H.regionLabels(H.S.mapBase, H.S.mapState, 'RID', v, VW, VH).map((l) => [l.id, l.l, l.t, l.fs, l.insPx]);
"""


def _layout(game, rid, vw, vh):
    return run(game, LAYOUT.replace("RID", rid).replace("VW", str(vw)).replace("VH", str(vh)), mapRegion=rid)


@pytest.mark.parametrize("vw,vh", [(360, 452), (360, 436)])
def test_fb648_the_crowded_corner_fits_once_the_bar_sits_inside_the_frame(vw, vh):
    """FB-648 第一段擺不下的那一種：360 寬、你站潁川郡、潁川郡自己被推、潁水河畔在冷卻——照第一段的畫法（框下多一條進度條、多一行
    「冷卻 N 分」）嵩山、潁川那一角怎麼擺都放不下。第二段照企劃者選的乙（2026-10-22）：進度條收進框裡、冷卻不寫字，框的大小翻不翻地都一樣，
    名字擺的位置跟沒翻地時一模一樣（翻地的那一刻不跳），這一組也不壓了。"""
    plain = _game(profile="season21")
    game = _game(profile="season21")
    w, c = game.state.world, game.content
    conquest.push(w, c, "yingchuan", "huang", "推甲", 40, "attack")
    conquest.push(w, c, "yingshui", "huang", "推乙", 100, "attack")
    st = game.map_state()
    assert st["places"]["yingchuan"]["tug"] and st["places"]["yingshui"]["cool"]
    assert run(game, OVERLAP.replace("VW", str(vw)).replace("VH", str(vh))) == []
    assert _layout(game, "yingru", vw, vh) == _layout(plain, "yingru", vw, vh)


def test_fb648_a_crowded_region_takes_its_names_one_size_smaller():
    """FB-648 第二段乙：擺好了還互壓（擠不下）時，這一區的名字縮一號重擺——平常那一號 12／13（意境字 10）→ 11／12（9），
    大一號的區（倍率 1 以上：14／15、11.5）→ 平常那一號；小圖不變。擺得下的不縮（同一區、同一個地圖框，你站別處就照原本那一號）。
    量過的（第一段的畫法）：360 寬你站嵩山深處，嵩山深處的框壓到潁川書院的小圖；南陽 375×624 你站宛城，框壓到小圖、鄰區出口。"""
    game = _game(profile="season21", at="deep_mountain")
    small = _layout(game, "yingru", 360, 452)
    assert {(fs, ins) for _, _, _, fs, ins in small} <= {(11, 9), (12, 9)} and any(fs == 11 for _, _, _, fs, _ in small)
    assert run(game, OVERLAP.replace("VW", "360").replace("VH", "452")) == []
    plain = _layout(game, "yingru", 375, 604)  # 375 寬你站嵩山深處擺得下：不縮
    assert {(fs, ins) for _, _, _, fs, ins in plain} <= {(12, 10), (13, 10)}
    # 畫出來的字也縮了：同一個地圖框（倍率一樣）你站潁川郡（擺得下）對你站嵩山深處，同一處的名字字級是 12 比 11
    size = lambda low, loc: float(re.search(r'<text x="[\d.]+" y="[\d.]+" font-size="([\d.]+)"', _label(low, loc)).group(1))  # noqa: E731
    shrunk, _ = parts(game, vw=360, vh=452)
    roomy, _ = parts(_game(profile="season21", at="yingchuan"), vw=360, vh=452)
    assert size(shrunk, "songshan_foot") / size(roomy, "songshan_foot") == pytest.approx(11 / 12, abs=0.01)
    wan = _game(profile="season21", at="wan_city")
    assert run(wan, "return H.regionFit(H.S.mapBase, 'nanyang', 375, 624).s;", mapRegion="nanyang") >= 1
    big = _layout(wan, "nanyang", 375, 624)  # 南陽在 375×624 倍率剛好 1，用大一號（14／15）；你站宛城擠不下 → 平常那一號
    assert {(fs, ins) for _, _, _, fs, ins in big} <= {(12, 10), (13, 10)}
    assert run(wan, OVERLAP.replace("VW", "375").replace("VH", "624")) == []
    away = _layout(_game(profile="season21", at="yingchuan"), "nanyang", 375, 624)  # 你不在南陽：擺得下，照大一號
    assert {(fs, ins) for _, _, _, fs, ins in away} <= {(14, 11.5), (15, 11.5)}


def test_labels_hug_their_icons_without_leader_lines():
    """企劃者 2026-10-21 從對比圖選乙：名字框不拉細點線回小圖，只在緊貼小圖的那幾個位置挑（右、左、下、上與上下左右錯開）；
    畫出來沒有細線那一組，每一個名字框最近的那一點離自己的小圖不遠。"""
    game = _game()
    low, _ = parts(game)
    assert "r-lead" not in low and "stroke-dasharray" not in low.split('class="r-label"', 1)[1]
    gaps = run(game, """const v = H.regionFit(H.S.mapBase, 'yingru', 375, 604);
return H.regionLabels(H.S.mapBase, H.S.mapState, 'yingru', v, 375, 604).map((l) => {
  const f = l.rows[0], nx = Math.max(f[0], Math.min(f[2], l.X)), ny = Math.max(f[1], Math.min(f[3], l.Y));
  return ['lead' in l, Math.hypot(nx - l.X, ny - l.Y)];
});""")
    assert not any(has for has, _ in gaps)
    assert max(d for _, d in gaps) < 75  # 最遠的是往上下錯開兩格的那幾個位置（約 2×框高＋小圖半高）


# ── 卡（設計 5.3）──
def test_card_line_says_whose_land_and_which_kind():
    from test_world_map import flipping

    game = flipping(_game())
    w, c = game.state.world, game.content
    conquest.set_control(w, c, "nanyang_wilds", "guan")
    lines = run(game, "return Object.fromEntries(['yingchuan', 'runan_wilds', 'nanyang_wilds', 'changshe', 'cao_manor', 'hilltop_wilds', 'guangzong', 'baima_temple']"
                      ".map((id) => [id, H.placeLine(H.S.mapState, id)]));")
    assert lines["yingchuan"] == "官軍的基礎資源領地"
    assert lines["runan_wilds"] == "中立・高級資源領地，還沒有人佔"
    assert lines["nanyang_wilds"] == "官軍佔下的高級資源領地"
    assert lines["changshe"] == "官軍大本營"  # 投靠點
    assert lines["cao_manor"] == "不在戰線上"  # 豪強分屬兩軍的季：豪強的投靠點不算誰的地盤
    cool = game.map_state()["places"]["hilltop_wilds"]["cool"]
    assert lines["hilltop_wilds"] == f"官軍佔下的高級資源領地；剛易手，{cool} 分後才能再推、加成暫停"
    assert lines["guangzong"].startswith("只照大事易手")


def test_flipping_section_lists_who_pushes_and_how_far():
    """正在翻（設計 4.1、4.2）：每一個攻方一條進度、誰在推（照邊、攻守分、推了多少）、集火、激戰；不另寫判斷，照 main_view 的 conquest.blocks。"""
    from test_world_map import flipping

    game = flipping(_game())
    w, c = game.state.world, game.content
    conquest.mark(w, c, "runan_wilds", "映雪", "guan", "attack", 12)
    conquest.mark(w, c, "runan_wilds", "白衣客", "guan", "attack", 8)
    conquest.mark(w, c, "runan_wilds", "黃天客", "huang", "hold", 6)
    out = run(game, 'return H.flipSection("runan_wilds");')
    assert "正在翻" in out and out.count('class="m-fbar"') == 2 and ">60</b>" in out and ">25</b>" in out
    assert "2 人正在攻（映雪 +12、白衣客 +8）" in out and "1 人在守（黃天客 +6）" in out
    assert "集火 +" in out and "激戰" in out
    assert run(game, 'return H.flipSection("cao_manor");') == ""  # 不是區塊


def test_the_card_says_today_s_yield():
    game = _game()
    st = game.map_state()
    assert st["places"]["runan_wilds"]["yield"].startswith("今日產出：")
    card = run(game, 'return H.placeCard(H.S.mapBase, H.S.mapState, "runan_wilds");')
    # 減法季整合設計第七章第 2 條：動作在前，往上拉才有對手、今日產出
    assert st["places"]["runan_wilds"]["yield"] in card and card.index('class="m-acts"') < card.index("此地的對手") < card.index('class="m-yield"')


def test_the_letter_button_follows_the_server():
    """下戰書（設計 4.4）照伺服器的入口條件：conquest_view 的 letter 只給在任的第 4 階、只列自己那一邊進度到門檻的塊；why 是空字串才按得下。"""
    game = _game()
    m = server.main_view(game)
    assert m["conquest"]["letter"] is None  # 不是第 4 階：沒有這一顆
    assert "下戰書" not in run(game, 'return H.placeCard(H.S.mapBase, H.S.mapState, "runan_wilds");', m=m)
    m["conquest"]["letter"] = {"used": False, "at": 60, "ready": [{"id": "runan_wilds", "name": "汝南荒野", "why": ""}, {"id": "nanyang_road", "name": "南陽官道", "why": "這裡跟自家的領地不相連"}]}
    ok = run(game, 'return H.placeCard(H.S.mapBase, H.S.mapState, "runan_wilds");', m=m)
    assert 'data-act="map-letter" data-id="runan_wilds"' in ok and "進度到 60 了" in ok
    no = run(game, 'return H.placeCard(H.S.mapBase, H.S.mapState, "nanyang_road");', m=m)
    assert "map-letter" not in no and "<button type=\"button\" disabled>下戰書" in no and "下戰書：這裡跟自家的領地不相連" in no


def test_the_card_carries_everything_the_chips_used_to():
    """拿掉濾鏡與小牌子之後，卡上找得到它們給的每一項（設計第十二章）：軍令、懸賞、勝算（此地的對手）、路程（步行 N 分）、劇情、誰佔過。"""
    game = _game()
    st = game.map_state()
    p = st["places"]["runan_wilds"]
    p.update(order="攻城", bounty="討伐", goal=True, news=True, flips=[{"week": 1, "from": None, "to": "guan"}])
    out = run(game, 'return H.placeCard(H.S.mapBase, H.S.mapState, "runan_wilds");', st=st)
    assert "軍令「攻城」在這裡記功" in out and "懸賞「討伐」在這裡交差" in out
    assert p["squads"][0]["odds"] in out and f"步行 {p['minutes']} 分" in out
    assert "★ 這一幕主線的目標" in out and "✦ 最近有大事與傳聞" in out
    assert "這一季誰佔過" in out and "中立→官軍" in out


def test_the_world_drawer_pulled_up_is_your_card_and_the_road_line_comes_first():
    game = _game()
    out = run(game, "return H.worldDrawerHtml(H.S.mapBase, H.S.mapState);", mapLayer="world", mapDrawer="half")
    assert 'data-act="world-enter"' in out and "潁川郡（陽翟）（你）" in out and 'class="m-line"' in out
    game.travel("yingchuan_wilds", "walk")
    road = run(game, "return H.worldDrawerHtml(H.S.mapBase, H.S.mapState);", mapLayer="world", mapDrawer="half")
    assert road.startswith('<div class="m-journey">') and "往 <b>潁川郊野</b>" in road


def test_fb649_the_card_on_the_road_starts_with_where_you_are_going():
    """FB-649（計畫 1.2、設計 5.3）：在路上點開任何一處的卡（含目的地），第一行照舊是「往 X・還有 N 分鐘・喊停」（journeyHtml），
    只有一行；不在路上沒有那一行。"""
    game = _game()
    assert "m-journey" not in run(game, 'return H.placeCard(H.S.mapBase, H.S.mapState, "runan_wilds");')
    game.travel("runan", "walk")  # 走好幾站：選單上有「喊停」
    m = server.main_view(game)
    assert any(o["id"] == "act:halt" and o.get("enabled") is not False for o in m["options"])
    for loc in ("runan", "yingshui", "runan_wilds", "yingchuan"):
        card = run(game, f'return H.placeCard(H.S.mapBase, H.S.mapState, "{loc}");', m=m)
        assert card.startswith('<div class="m-journey">') and "往 <b>汝南</b>・還有 12 分鐘・下一站潁水河畔" in card, loc
        assert card.count('class="m-journey"') == 1 and 'data-act="choose" data-id="act:halt"' in card, loc


DARK_CARD_2 = "#2B251E"  # 深色主題抽屜裡最亮的底（style.css 的 --card-2；抽屜本身是 --card #211C17，更暗）


def _contrast(a, b):
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_fb650_side_coloured_card_text_reads_in_dark_mode():
    """FB-650：深色主題時卡上照陣營上色的字（第 2 段那一句、正在翻的名字、誰在推那一句、戰線的繩上「推進」那一句）對比 ≥ 4.5:1。
    深色那一版照劇本的顏色算（對比不夠的往那一方的 soft 調亮），本來就夠的（黃巾 5.0:1）不動；不寫死哪一方。修的時候淺色照劇本的 color
    一個字不變；FB-652（2026-10-22）淺色那一版也照同一個做法往墨色調深，見下一條。"""
    from test_world_map import flipping

    game = flipping(_game())
    w, c = game.state.world, game.content
    conquest.mark(w, c, "runan_wilds", "映雪", "guan", "attack", 12)
    conquest.mark(w, c, "runan_wilds", "黃天客", "huang", "attack", 6)
    color = {s["id"]: s["color"] for s in game.map_base()["world"]["sides"]}
    assert _contrast(color["guan"], DARK_CARD_2) < 4.5 <= _contrast(color["huang"], DARK_CARD_2)  # 修前：官軍的藍 2.6:1（QA 量的是 #211C17）
    cards = run(game, "return ['runan_wilds', 'yingchuan', 'hilltop_wilds'].map((id) => H.placeCard(H.S.mapBase, H.S.mapState, id)).join('');")
    pairs = set(re.findall(r'--sc:(#[0-9A-F]{6});--sd:(#[0-9A-F]{6})', cards))
    # FB-652（2026-10-22）之後淺色那一版（--sc）不一定是劇本的 color（黃巾在淺色調深了，見 test_fb652）：這裡只管深色那一版
    assert len(pairs) == 2
    for sc, sd in pairs:
        assert _contrast(sd, DARK_CARD_2) >= 4.5, (sc, sd)
    assert any(sd == color["huang"] for _, sd in pairs)  # 黃巾在深色本來就夠（5.0:1），不動
    assert not any(sd == color["guan"] for _, sd in pairs)  # 官軍的藍在深色調亮
    assert re.search(r'<div class="m-line" style="--sc:#[0-9A-F]{6};--sd:#[0-9A-F]{6}">官軍的基礎資源領地', cards)
    assert re.search(r'<span class="nm" style="--sc:', cards) and re.search(r'<span class="m-sc" style="--sc:[^"]+">官軍</span> 1 人正在攻', cards)
    assert all(f"color:{x}" not in cards for x in color.values())  # 照陣營上色的字都走 --sc／--sd（勝算的字照舊）
    css = (Path(server.WEB) / "style.css").read_text(encoding="utf-8").replace("\r\n", "\n")
    dark = re.findall(r"@media \(prefers-color-scheme: dark\) \{([^\n]*)\}", css)
    assert any(".m-line" in d and ".m-fbar .nm" in d and ".m-sc" in d and "var(--sd" in d for d in dark)
    assert re.search(r"\.m-line \{[^}]*color: var\(--sc, var\(--ink-2\)\)", css) and ".m-fbar .nm, .m-sc { color: var(--sc); }" in css  # 淺色照劇本
    # 四方的劇本：每一方深色那一版都夠
    four, _ = _four_sides()
    out = run(four, "return ['guan', 'huang', 'wei', 'wu'].map((k) => H.sideText(k));")
    for text in out:
        sc, sd = re.match(r"--sc:(#[0-9A-F]{6});--sd:(#[0-9A-F]{6})", text).groups()
        assert _contrast(sd, DARK_CARD_2) >= 4.5, text


LIGHT_CARD_2 = "#EFE6D5"  # 淺色主題抽屜裡最深的底（style.css 的 --card-2；抽屜本身是 --card #FBF7EF，更亮）
LIGHT_CARD = "#FBF7EF"


def test_fb652_side_coloured_card_text_reads_in_light_mode():
    """FB-652：淺色主題卡上照陣營上色的字也要 ≥ 4.5:1——QA 量到黃巾 #B9821A 在卡底 #FBF7EF 上只有 3.13:1（第 2 段整句、正在翻的名字、
    誰在推、戰線的繩、版圖變化）。照 sideText 深色那一版（FB-650）的做法：淺色那一版（--sc）在淺色最深的底（--card-2）上對比不到 4.5:1 的
    往墨色調深到夠，本來就夠的（官軍 #3D5F8F）不動；照劇本讀、不寫死哪一方（四方劇本每一方都夠）。進度條照舊用劇本的 color。"""
    from test_world_map import flipping

    game = flipping(_game())
    w, c = game.state.world, game.content
    conquest.mark(w, c, "runan_wilds", "映雪", "guan", "attack", 12)
    conquest.mark(w, c, "runan_wilds", "黃天客", "huang", "attack", 6)
    color = {s["id"]: s["color"] for s in game.map_base()["world"]["sides"]}
    assert _contrast(color["huang"], LIGHT_CARD) < 4.5 <= _contrast(color["guan"], LIGHT_CARD_2)  # 修前：黃巾 3.13:1
    cards = run(game, "return ['runan_wilds', 'yingchuan', 'hilltop_wilds'].map((id) => H.placeCard(H.S.mapBase, H.S.mapState, id)).join('');")
    light = {sc for sc, _ in re.findall(r'--sc:(#[0-9A-F]{6});--sd:(#[0-9A-F]{6})', cards)}
    assert light and all(_contrast(sc, LIGHT_CARD_2) >= 4.5 for sc in light), light
    assert color["guan"] in light and color["huang"] not in light  # 官軍本來就夠、不動；黃巾換深一點的那一版
    assert f"background:{color['huang']}" in cards  # 進度條照舊是劇本的顏色
    four, _ = _four_sides()
    out = run(four, "return ['guan', 'huang', 'wei', 'wu'].map((k) => [H.sideInk(k).color, H.sideText(k)]);")
    for raw, text in out:
        sc = re.match(r"--sc:(#[0-9A-F]{6});", text).group(1)
        assert _contrast(sc, LIGHT_CARD_2) >= 4.5, text
        assert sc == raw if _contrast(raw, LIGHT_CARD_2) >= 4.5 else sc != raw


def test_the_removed_pieces_are_gone():
    """設計 5.4 那一表：濾鏡、意境鈕與意境濾鏡、小牌子、⚔、前線鋸齒、中立地虛線圈、圓盤裡一個字、看大局、「天下」那一條——真的刪了。
    「自由縮放」那一項企劃者 2026-10-22 改回來了（兩張都能拖、能捏合縮放，tests/test_map_pan_web.py）：清單拿掉舊的手勢函式名，
    縮放鈕、回到所在地、看大局那幾樣照舊不准有。"""
    src = APP.read_text(encoding="utf-8")
    for name in ("MAP_CHIPS", "function chipsHtml", "function insightButton", "INSIGHT_DOT", "function mapBadges", "NEUTRAL_INK", "MAP_FAR",
                 "function hudHtml", "function marksParts", "function marksSvg", "function regionTint",
                 "function mapZoom", "function mapHome", "function toggleLayer", "function clampView", "function firstScale", "class=\"armed\"",
                 "<path class=\"front\"", "map-hud", "map-ctl", "S.mapLayers"):
        assert name not in src, name
    css = (Path(server.WEB) / "style.css").read_text(encoding="utf-8")
    for rule in (".map-chips", ".map-ctl", ".map-hud", ".m-three", ".map-wrap.grabbing", ".map-wrap.moving"):
        assert rule not in css, rule
