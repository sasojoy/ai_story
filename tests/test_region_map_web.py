"""輿圖第三版第 4 批：區圖與卡（輿圖簡化設計 5.2、5.3、5.4、5.6、第十二章；計畫 docs/superpowers/plans/2026-10-21-輿圖v3-區圖與卡.md）。
點一區進的是區圖：同一張底圖換一個固定的取景（regionFit），只畫這一區的地點——墨筆小圖、印章框（框色＝誰的，顏色照劇本）、框下的進度條
（攻方的顏色；剛易手灰掉寫冷卻）、朱印「寶」、名字底下的意境字、你的朱圈與旗、鄰區出口；「塗層」開了多一層淡彩。點一處抽屜半開那一處的卡。
在 node 裡跑整支 app.js（tests/webharness.py），餵伺服器真的會給的底圖、疊層與 main_view（翻地那一份）；沒有 node 就略過。"""
from __future__ import annotations

import math
import random
import re
from pathlib import Path

import pytest
import test_prologue_web
from conftest import classic_rules, real_content
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
         "flipSection", "drawerHtml", "worldDrawerHtml", "sideInk"]
DRIVER = re.sub(r"wholeApp\(\[.*?\]\)", "wholeApp(" + repr(NAMES).replace("'", '"') + ")", test_prologue_web.DRIVER, count=1, flags=re.S)
APP = Path(server.WEB) / "app.js"
# 地圖框（寬 × 高）：實機量的。375×812 → 375×604（2026-10-21 map4.localhost，狀態列多一行心得提示、商城開著）、375×624（第 3 批量的）、
# 375×667 → 375×479、360×640 → 360×452／360×436
PHONES = [(375, 604), (375, 624), (375, 479), (360, 452), (360, 436)]


def _game(content=None, faction="guan", at="yingchuan", conquest_on=True, profile="weekend"):
    c = content or real_content(profile)
    if conquest_on:
        conquest_rules(c)
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    territory.update(game.state.world, c)
    game.state.player.faction, game.state.player.location = faction, at
    return game


def run(game, script, st=None, m=None, **S):
    payload = {"m": m or server.main_view(game), "script": script,
               "S": {"mapBase": game.map_base(), "mapState": st or game.map_state(), "mapLayer": "region", "mapRegion": "yingru", **S},
               "menxia": None, "stored": {}, "responses": {}}
    return webharness.run(DRIVER, payload)


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


def test_progress_bars_show_the_top_attacker_and_cooling_is_grey():
    """框下的進度條（設計 5.2、4.1）：進度最高的那一方的顏色、長度照進度；守方自己的不畫；剛易手整條灰、寫冷卻幾分。"""
    from test_world_map import flipping

    game = flipping(_game())
    st = game.map_state()
    ink = {s["id"]: s for s in game.map_base()["world"]["sides"]}
    low, _ = parts(game)
    wilds = _label(low, "runan_wilds")  # 中立地：官軍 60、黃巾 25 → 畫官軍那一條、六成
    track = float(re.search(r'class="r-bar"[^>]*width="([\d.]+)"', wilds).group(1))
    fill = re.search(r'class="r-bar-fill" data-side="([a-z]+)"[^>]*width="([\d.]+)"[^>]*fill="(#[0-9A-F]{6})"', wilds)
    assert fill.group(1) == "guan" and float(fill.group(2)) == pytest.approx(track * 0.6, abs=0.15) and fill.group(3) == ink["guan"]["color"]
    assert 'data-side="huang"' in _label(low, "yingchuan_wilds")  # 官軍的地被黃巾推：畫黃巾那一條
    cool = _label(low, "hilltop_wilds")
    assert 'class="r-bar"' in cool and "r-bar-fill" not in cool and f"冷卻 {st['places']['hilltop_wilds']['cool']} 分" in cool
    assert "r-bar" not in _label(low, "yingchuan")  # 沒人推、沒冷卻：沒有進度條


def test_no_progress_bars_when_conquest_is_off():
    """領地爭奪關著的季（設計 5.6）：照新畫法畫，沒有進度條與冷卻（疊層沒有 tug／cool）；框色照控制方。"""
    game = _game(content=classic_rules(real_content("weekend")), conquest_on=False)
    low, _ = parts(game)
    assert "r-bar" not in low and "r-cool" not in low and 'class="r-frame"' in low


def test_you_get_a_red_ring_and_flag_in_your_region_only():
    game = _game()
    _, high = parts(game, "yingru")
    assert 'class="r-you"' in high and 'class="pulse"' in high
    _, other = parts(game, "nanyang")
    assert other == ""


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
    """上面一排（設計 5.2）：‹ 天下、大區名下拉（每一區一個、這一區選著）、塗層、⏱ 版圖；搜尋不在這一排（天下圖才有）。"""
    game = _game()
    out = run(game, "return H.regionTopHtml();")
    assert 'data-act="map-world"' in out and "‹ 天下" in out and 'data-act="map-timeline"' in out and 'data-act="map-wash"' in out
    options = re.findall(r'<option value="([a-z]+)"( selected)?>', out)
    assert [x for x, _ in options] == [r.id for r in game.content.map.regions] and [x for x, s in options if s] == ["yingru"]
    assert "map-search" not in out and out.index("map-world") < out.index("region-pick") < out.index("map-wash") < out.index("map-timeline")


def _four_sides():
    """四方的測試劇本（設計 3.3、第十二章）：官軍、黃巾之外加魏、吳（各自的顏色）；潁川汝南的區塊照方位分給四方。"""
    c = real_content("weekend")
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
@pytest.mark.parametrize("profile", ["weekend", "season21"])
def test_region_labels_do_not_overlap_on_a_phone(profile, vw, vh):
    """375／360 寬：每一區的名字框兩兩不相交、不壓別處的小圖與鄰區出口、不出畫面（潁川汝南 17 處最擠）。名字框只貼著小圖擺、不拉線
    （企劃者 2026-10-21 從對比圖選乙）。320 寬（地圖框 320×344）潁川汝南放不開，先這樣（PM 2026-10-21，同企劃者「320 寬先這樣」）。"""
    game = _game(profile=profile)
    assert run(game, OVERLAP.replace("VW", str(vw)).replace("VH", str(vh))) == []


# FB-648：開季那一刻量不到的局面——翻地中名字框會變大（攻方在推多一條進度條、剛易手多一行「冷卻 N 分」），你站的那一處多朱圈與旗。
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
@pytest.mark.parametrize("profile", ["weekend", "season21"])
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


@pytest.mark.parametrize("vw,vh", [(360, 452), (360, 436)])
def test_fb648_when_the_crowded_corner_cannot_fit_the_rest_stays_clean(vw, vh):
    """FB-648 還沒解的那一種（等企劃者挑畫法，見試玩回饋 FB-648）：360 寬、你站潁川郡、潁川郡自己被推（框下多一條進度條）、潁水河畔在冷卻——
    嵩山、潁川那一角照現在的畫法怎麼擺都放不下（第二輪一起找把每一種擺法試完）。擺不開時反覆把壓到東西的那幾處換位置，壓到的只留在那一角，
    汝南那一頭不受連累（修前汝南集市壓譙縣）。"""
    game = _game(profile="season21")
    w, c = game.state.world, game.content
    conquest.push(w, c, "yingchuan", "huang", "推甲", 40, "attack")
    conquest.push(w, c, "yingshui", "huang", "推乙", 100, "attack")
    bad = run(game, OVERLAP.replace("VW", str(vw)).replace("VH", str(vh)))
    corner = {"yingchuan", "yingshui", "songshan_foot", "deep_mountain", "jade_cave", "yingchuan_academy"}
    assert bad and all(x in corner for _, a, b in bad for x in (a, b.split(":")[-1])), bad


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


def test_card_line_in_a_season_without_conquest():
    """領地爭奪關著的季（設計 5.6）：不寫基礎、高級資源領地（那是翻地的區塊），照控制方寫。"""
    game = _game(content=classic_rules(real_content("weekend")), conquest_on=False)
    lines = run(game, "return ['yingchuan', 'cao_manor'].map((id) => H.placeLine(H.S.mapState, id));")
    assert all("資源領地" not in x for x in lines)


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


def test_no_flipping_section_when_conquest_is_off():
    game = _game(content=classic_rules(real_content("weekend")), conquest_on=False)
    assert server.main_view(game).get("conquest") is None
    card = run(game, 'return H.placeCard(H.S.mapBase, H.S.mapState, "runan_wilds");')
    assert "正在翻" not in card and "下戰書" not in card


def test_the_card_says_today_s_yield():
    game = _game()
    st = game.map_state()
    assert st["places"]["runan_wilds"]["yield"].startswith("今日產出：")
    card = run(game, 'return H.placeCard(H.S.mapBase, H.S.mapState, "runan_wilds");')
    assert st["places"]["runan_wilds"]["yield"] in card and card.index("此地的對手") < card.index("今日產出") < card.index('class="m-acts"')


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


def test_the_removed_pieces_are_gone():
    """設計 5.4 那一表：濾鏡、意境鈕與意境濾鏡、小牌子、⚔、前線鋸齒、中立地虛線圈、圓盤裡一個字、自由縮放、看大局、「天下」那一條——真的刪了。"""
    src = APP.read_text(encoding="utf-8")
    for name in ("MAP_CHIPS", "function chipsHtml", "function insightButton", "INSIGHT_DOT", "function mapBadges", "NEUTRAL_INK", "MAP_FAR",
                 "function hudHtml", "function marksParts", "function marksSvg", "function regionTint", "function gripDown", "function mapWheel",
                 "function mapZoom", "function mapHome", "function toggleLayer", "function clampView", "function firstScale", "class=\"armed\"",
                 "<path class=\"front\"", "map-hud", "map-ctl", "S.mapLayers"):
        assert name not in src, name
    css = (Path(server.WEB) / "style.css").read_text(encoding="utf-8")
    for rule in (".map-chips", ".map-ctl", ".map-hud", ".m-three", ".map-wrap.grabbing", ".map-wrap.moving"):
        assert rule not in css, rule


def test_conquest_off_seasons_draw_the_new_map_too():
    """設計 5.6：同一個劇本、規則開關不同的季也用新畫法（印章框、小圖、意境字），沒有翻地資料的那幾段不出現。"""
    for profile in ("weekend", None, "season21"):
        game = _game(profile=profile, conquest_on=False)
        assert not conquest.on(game.content, game.state.world)
        low, _ = parts(game)
        assert 'class="r-frame"' in low and 'class="r-icon"' in low and "r-bar" not in low, profile
        card = run(game, 'return H.placeCard(H.S.mapBase, H.S.mapState, "runan_wilds");')
        assert "正在翻" not in card and "此地的對手" in card, profile
