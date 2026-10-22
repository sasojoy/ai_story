"""輿圖第三版第 5 批：攻城戰的三種時刻在輿圖上（企劃者 2026-10-22 從對比圖 docs/superpowers/specs/2026-10-20-輿圖簡化-草圖/v5-接縫/
挑 A 乙、B 甲、C 甲；計畫 docs/superpowers/plans/2026-10-22-輿圖v3-接縫.md 第六節）：
- A 戰書下了、還沒開集結：區圖名字框旁（寶的右邊）一枚「戰」字印、名字框跟著寬一格；天下圖那一格一圈朱紅虛線框。
- B 集結・交戰中：天下圖那一格借激戰的紅光、區圖名字框外一圈紅（一閃一閃）。
- C 打完（到換天）：地圖不另畫（剛易手本來就畫）。
- 三種時刻卡上第 2 段底下一段「戰書／攻城／攻城戰果」；攻城那一顆鈕照看的人站哪一格（攻方、守方、散人與不是兩軍的人、另一軍站不進去）。
資料：疊層 places[id].siege（mapdata.flip_marks：letter／fight），main_view 的 conquest.today（sides、you、margin）與 conquest.muster。
「戰」字印擠名字框：FB-648 那一套掃描（五區、你站每一處與在路上、五個手機地圖框，名字框 0 對互壓）帶著戰書重跑。"""
from __future__ import annotations

import re

import pytest
import test_region_map_web as R
import test_world_map_web as Wd
from conftest import classic_rules, real_content
from conquest_kit import announce

import server
import webharness
from tianxia import conquest, conquest_day
from tianxia.state import DayNote, SiegeSlot

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]
CARD = 'return Object.fromEntries(["runan_wilds", "yingchuan_wilds", "hilltop_wilds", "changshe"].map((id) => [id, H.placeCard(H.S.mapBase, H.S.mapState, id)]));'


def _moments(game):
    """三種時刻各擺一處（同對比圖）：A 汝南荒野（中立）官軍推 65 下了戰書；B 潁川郊野（官軍的）黃巾推 62、集結・交戰中；
    C 荒丘（中立）官軍的攻城戰打贏（大勝）、剛易手。回三場（時程表那一筆）。"""
    w, c = game.state.world, game.content
    conquest.push(w, c, "runan_wilds", "guan", "映雪", 65, "attack")
    a = announce(game, "runan_wilds", "guan")
    conquest.push(w, c, "yingchuan_wilds", "huang", "黃天客", 62, "attack")
    b = announce(game, "yingchuan_wilds", "huang", minute=20 * 60)
    b.status = "open"
    key = w.conquest.settled_key
    d = SiegeSlot(id="done-hilltop", key=key, loc="hilltop_wilds", minute=12 * 60, at=w.time - 600, muster_at=w.time - 2400,
                  attackers=["guan"], by={"guan": conquest_day.LETTER}, reasons={"guan": "官帥"}, status="done", winner="guan")
    w.conquest.schedule.append(d)
    conquest.flip(w, c, "hilltop_wilds", "guan", note=False)
    w.conquest.day_log.append(DayNote(key=key, side="guan", loc="hilltop_wilds", minute=12 * 60, by=conquest_day.LETTER, reason="官帥",
                                      result="taken", taken="guan", margin="大勝", keeper="guard", attackers=["guan"]))
    return a, b, d


# ── 伺服器給的資料 ──
def test_the_map_overlay_says_which_siege_moment_each_block_is_in():
    """疊層 places[id].siege：戰書下了、還沒開集結是 letter，集結・交戰中是 fight，打完、沒有戰書是 None；不是區塊的地點沒有這個鍵。"""
    game = R._game(profile="season21")
    _moments(game)
    places = game.map_state()["places"]
    assert places["runan_wilds"]["siege"] == "letter" and places["yingchuan_wilds"]["siege"] == "fight"
    assert places["hilltop_wilds"]["siege"] is None and places["yingchuan"]["siege"] is None
    assert "siege" not in places["cao_manor"]


@pytest.mark.parametrize("profile", ["weekend", None, "season21"])
def test_no_siege_mark_when_conquest_is_off(profile):
    game = R._game(content=classic_rules(real_content(profile)), conquest_on=False)
    assert not any("siege" in p for p in game.map_state()["places"].values())
    assert server.main_view(game).get("conquest") is None


@pytest.mark.parametrize("faction,expect", [
    ("guan", {"runan_wilds": "attack", "yingchuan_wilds": "defend"}),  # 官軍：自己下的戰書、自家的塊被打
    ("huang", {"runan_wilds": "", "yingchuan_wilds": "attack"}),  # 黃巾：官軍單方攻中立地站不進去
    (None, {"runan_wilds": "help", "yingchuan_wilds": "help"}),  # 散人：臨時投效或助守
])
def test_today_rows_say_where_the_viewer_stands(faction, expect):
    """conquest.today 每一場多 sides（攻方的陣營 id）、you（看的人站得進哪一格，siege.slots 同一套）、margin（打完的大勝／險勝）；muster 是開打前幾分鐘集結。"""
    game = R._game(profile="season21", faction=faction)
    _moments(game)
    view = game.conquest_view()
    rows = {r["loc"]: r for r in view["today"]}
    assert {loc: rows[loc]["you"] for loc in expect} == expect
    assert rows["runan_wilds"]["sides"] == ["guan"] and rows["yingchuan_wilds"]["sides"] == ["huang"]
    assert rows["hilltop_wilds"]["margin"] == "大勝" and rows["runan_wilds"]["margin"] == "" and rows["hilltop_wilds"]["status_text"] == "官軍拿下"
    assert view["muster"] == game.content.config.conquest.muster_minutes == 30


# ── 卡 ──
def test_the_card_has_a_section_for_each_siege_moment():
    """官軍看：A「戰書」誰約戰、幾點、開打前幾分鐘集結、凍結；B「攻城」狀態字、幾點開打、「去守城」回江湖頁；C「攻城戰果」誰拿下、大勝、
    「看戰報」開見聞的戰報。「正在翻」底下不再多一行「已下戰書」（寫在上面那一段）。沒有攻城的地方沒有這一段。"""
    game = R._game(profile="season21")
    a, b, _ = _moments(game)
    cards = R.run(game, CARD)
    letter, fight, done = cards["runan_wilds"], cards["yingchuan_wilds"], cards["hilltop_wilds"]
    assert 'data-siege="letter"' in letter and "<h4>戰書</h4>" in letter
    assert f"官軍約戰 <b>{game.stamp(a.at)}</b>；開打前 30 分鐘在這一帶集結，人要在這一區才加得進去。這一塊的進度凍結到打完。" in letter
    assert 'data-siege="fight"' in fight and "<h4>攻城</h4>" in fight
    assert f"黃巾軍攻潁川郊野：<b>集結・交戰中</b>（{game.stamp(b.at)} 開打）。這一區的人加得進去。" in fight
    assert re.search(r'<button type="button" class="main" data-act="tab" data-tab="jianghu">去守城<small>回江湖頁</small></button>', fight)
    assert 'data-siege="done"' in done and "<h4>攻城戰果</h4>" in done and "那一仗：<b>官軍拿下</b>（大勝）。" in done
    assert 'data-act="map-report">看戰報' in done
    for card in (letter, fight, done):
        assert "已下戰書" not in card and card.index('class="m-line"') < card.index("m-siege") < card.index('class="m-foes"')
        if "正在翻" in card:
            assert card.index("m-siege") < card.index("正在翻")
    assert "m-siege" not in cards["changshe"]


def test_the_fight_button_follows_where_the_viewer_stands():
    """攻城那一顆鈕：攻方「去加入攻城」、散人「去助陣」；另一軍站不進去（官軍單方攻中立地時的黃巾）不畫鈕、寫站不進去。"""
    huang = R._game(profile="season21", faction="huang")
    _moments(huang)
    cards = R.run(huang, CARD)
    assert ">去加入攻城<small>" in cards["yingchuan_wilds"]
    assert "這一場你這一邊站不進去。" in cards["runan_wilds"] and "人要在這一區才加得進去" not in cards["runan_wilds"]
    loner = R._game(profile="season21", faction=None)
    _moments(loner)
    assert ">去助陣<small>" in R.run(loner, CARD)["yingchuan_wilds"]


def test_a_void_siege_has_no_section():
    game = R._game(profile="season21")
    a, _, _ = _moments(game)
    a.status = "void"
    assert "m-siege" not in R.run(game, CARD)["runan_wilds"]


def test_the_report_button_opens_the_reports_page():
    """「看戰報」：換到見聞、戰報那一頁（S.news）。"""
    src = R.APP.read_text(encoding="utf-8")
    assert re.search(r'case "map-report": S\.news = "reports"; await goTab\("news"\);', src)


# ── 區圖 ──
def test_region_map_seal_for_a_letter_and_a_ring_for_a_fight():
    """A 乙：汝南荒野的名字框旁（寶的右邊）一枚「戰」字印——不算進名字框（名字不挪）；B 甲：潁川郊野的名字框外一圈紅（.w-melee 一閃一閃），
    畫在印章框底下；C 甲：荒丘不另畫。顏色是前線那一種朱紅，不照哪一方。"""
    game = R._game(profile="season21")
    labels = "const v = H.regionFit(H.S.mapBase, 'yingru', 375, 604); return H.regionLabels(H.S.mapBase, H.S.mapState, 'yingru', v, 375, 604).map((l) => [l.id, l.l, l.t, l.w1, l.letter, l.fight, l.seal || null, l.rows[0]]);"
    plain = R.run(game, labels)
    _moments(game)
    low, _ = R.parts(game)
    seal = R._label(low, "runan_wilds")
    assert '<g class="r-seal">' in seal and '<g class="r-letter">' in seal and ">戰</text>" in seal
    assert seal.index('<g class="r-seal">') < seal.index('<g class="r-letter">')
    fight = R._label(low, "yingchuan_wilds")
    assert 'class="r-fight w-melee"' in fight and fight.index("r-fight") < fight.index("r-frame") and "r-letter" not in fight
    done = R._label(low, "hilltop_wilds")
    assert "r-letter" not in done and "r-fight" not in done
    red = re.search(r'const FRONT_RED = "(#[0-9A-Fa-f]{6})"', R.APP.read_text(encoding="utf-8")).group(1)
    assert f'stroke="{red}"' in seal and f'fill="{red}">戰' in seal and f'stroke="{red}"' in fight
    after = R.run(game, labels)
    assert [x[:4] for x in after] == [x[:4] for x in plain]  # 名字一個都不挪、框不變寬
    marks = {x[0]: x for x in after}
    assert marks["runan_wilds"][4] is True and marks["yingchuan_wilds"][5] is True
    assert marks["hilltop_wilds"][4] is False and marks["hilltop_wilds"][5] is False and marks["hilltop_wilds"][6] is None
    seal_box, row = marks["runan_wilds"][6], marks["runan_wilds"][7]
    gap = max(row[0] - seal_box[2], seal_box[0] - row[2], row[1] - seal_box[3], seal_box[1] - row[3])
    assert 0 <= gap <= 10, (seal_box, row)  # 貼著自己的名字框、不壓它（這一個擺法寶的右邊沒有空位，字印在別的一邊）


def test_the_fight_ring_stays_inside_the_row_gap():
    """B 甲那一圈紅的外緣離印章框不到 R_ROW_GAP（FB-651 兩列之間留的那一圈）：不壓別處的名字框。"""
    src = R.APP.read_text(encoding="utf-8")
    out = float(re.search(r"R_FIGHT_OUT = ([\d.]+)", src).group(1))
    line = float(re.search(r"R_FIGHT_LINE = ([\d.]+)", src).group(1))
    assert out + line / 2 < R.ROW_GAP


# ── 天下圖 ──
def test_world_map_dashed_frame_for_a_letter_and_the_clash_glow_for_a_fight():
    """A 乙：天下圖汝南荒野那一格一圈朱紅虛線框（.w-letter）；B 甲：潁川郊野那一格借激戰的紅光（.w-melee）；C 甲：荒丘不另畫。
    看以前的週（版圖變化）不畫。"""
    game = Wd._game(content=real_content("season21"))
    _moments(game)
    low, _ = Wd.parts(game)
    assert re.search(r'<path class="w-letter" data-cell="runan_wilds"[^>]*stroke-dasharray', low)
    assert '<path class="w-melee" data-cell="yingchuan_wilds"' in low
    assert 'data-cell="hilltop_wilds"' not in "".join(re.findall(r'<path class="w-(?:letter|melee)"[^>]*>', low))
    past, _ = Wd.parts(game, o="{ k: 2.5, week: 0, tl: true, sel: null }")
    assert "w-letter" not in past and 'w-melee" data-cell="yingchuan_wilds"' not in past


def test_four_sides_marks_do_not_take_any_sides_colour():
    """四方的測試劇本（設計 3.3）：魏攻吳佔著的長社那一格下了戰書——區圖照樣一枚「戰」、天下圖照樣一圈朱紅虛線；字印與框不照任何一方的顏色。
    名字框照四方的顏色（第 4 批的測試），卡上那一段的攻方名字照伺服器給的。"""
    game, control = R._four_sides()
    st = game.map_state()
    target = next(x for x, sd in control.items() if sd == "wu" and x in st["places"])
    st["places"][target]["siege"] = "letter"
    low, _ = R.parts(game, st=st)
    seal = R._label(low, target)
    assert '<g class="r-letter">' in seal
    for colour in ("#6A3D7A", "#2E7D5B", "#3D5F8F", "#B9821A"):
        assert colour not in seal[seal.index('<g class="r-letter">'):]
    world, _ = Wd.parts(game, st=st)
    assert f'data-cell="{target}"' in "".join(re.findall(r'<path class="w-letter"[^>]*>', world))


def test_the_siege_code_names_no_side():
    """設計 3.3：攻城那幾段（卡上那一段、字印、天下圖的框）不寫死陣營 id、名字與顏色；顏色只有前線那一種朱紅與字印的紙色。"""
    src = R.APP.read_text(encoding="utf-8").replace("\r\n", "\n")
    block = src[src.index("  function siegeOf(id)"):src.index("  // 第 7 段的「下戰書」")]
    for word in ('"guan"', '"huang"', '"haoqiang"', "官軍", "黃巾", "豪強", "MAP_SIDES", "#3D5F8F", "#B9821A"):
        assert word not in block, word


# ── 「戰」字印擠名字框：FB-648 那一套掃描帶著戰書重跑 ──
SIEGE_SWEEP = R.FLIP_SWEEP.replace(
    """    if (kind === "cool") { q.control = q.control || sides[0]; q.tug = null; q.cool = 59; }""",
    """    if (kind === "cool") { q.control = q.control || sides[0]; q.tug = null; q.cool = 59; }
    if (kind === "letter" || kind === "fight") { q.tug = { [sides.find((s) => s !== q.control)]: 62 }; q.cool = null; q.siege = kind; }""",
).replace(
    """    for (const id of capt) cases.push({ [id]: "bar" }, { [id]: "cool" });""",
    """    for (const id of capt) cases.push({ [id]: "letter" }, { [id]: "fight" });
    cases.push(Object.fromEntries(capt.map((id) => [id, "letter"])));""",
).replace(
    """if (x < 0.3) a[id] = "bar"; else if (x < 0.5) a[id] = "cool";""",
    """if (x < 0.2) a[id] = "letter"; else if (x < 0.35) a[id] = "bar"; else if (x < 0.5) a[id] = "cool";""",
).replace(
    """      if (ref === null) ref = sig; else if (sig !== ref) moved.push([VW, VH, here, assign]);""",
    """      if (ref === null) ref = sig; else if (sig !== ref) moved.push([VW, VH, here, assign]);
      const gap = (a, b) => Math.max(a[0] - b[2], b[0] - a[2], a[1] - b[3], b[1] - a[3]);
      const others = (l) => [...L.filter((m) => m !== l).flatMap((m) => [...m.rows, ...(m.seal ? [m.seal] : [])])];
      for (const l of L) if (l.letter) {
        seals.push(1);
        if (!l.sealFit) unfit.push([VW, VH, here, l.id]);
        else if (Math.min(...others(l).map((q) => gap(l.seal, q))) < H.S.need) tight.push([VW, VH, here, l.id]);
      }""",
).replace("const fails = [], moved = [], gaps = [];", "const fails = [], moved = [], gaps = [], tight = [], unfit = [], seals = [];").replace(
    "return { fails, moved, gaps };", "return { fails, moved, gaps, seals: seals.length, unfit, tight };")


def test_the_siege_sweep_script_is_built():
    """上面那幾處替換都換到了（FLIP_SWEEP 改了寫法，這裡就會紅，不會悄悄掃不到戰書）。"""
    for word in ('q.siege = kind', '{ [id]: "letter" }', 'a[id] = "letter"', "unfit.push", "tight.push", "seals: seals.length"):
        assert word in SIEGE_SWEEP, word


# 「戰」字印不算進名字框（框的大小下不下戰書都一樣，同 FB-648 第二段乙）：名字擺好之後才找空位。2026-10-22 量的（weekend、season21 一樣，
# 計畫第五節）：每一區五個手機地圖框、你站每一處與在路上 × 那幾種配法，字印一共 2807／487／517／163／421 枚（潁川汝南／南陽／洛陽／冀州／幽州），
# 找不到空位、只好蓋在自己名字框右上角的（unfit）12／0／6／0／0 枚，找得到空位但離別處的名字框不到 R_ROW_GAP 的（tight）40／2／3／0／3 枚——只准變少。
# 第一版把字印算進名字框（框寬一格）：潁川汝南 360 寬、南陽 375×624、洛陽 375 寬互壓（量到 15＋22＋4 種局面），名字跳開的幾百種，所以改成這樣
SEAL_LEFT = {"yingru": (12, 40), "nanyang": (0, 2), "luoyang": (6, 3), "jizhou": (0, 0), "youzhou": (0, 3)}


def _sweep(game, rid, phones, timeout=300):
    """SIEGE_SWEEP 跑一區（潁川汝南 320 寬一次跑超過一分鐘，照自己的逾時跑）。"""
    import json

    mine = {p["id"] for p in game.map_base()["places"] if p["region"] == rid}
    capt = [k for k, b in server.main_view(game)["conquest"]["blocks"].items() if b["capturable"] and k in mine]
    payload = {"m": server.main_view(game), "script": SIEGE_SWEEP, "menxia": None, "stored": {}, "responses": {},
               "S": {"mapBase": game.map_base(), "mapState": game.map_state(), "mapLayer": "region", "mapRegion": rid,
                     "rid": rid, "capt": capt, "phones": phones, "need": R.ROW_GAP - 0.05}}
    done = webharness.node(webharness.PRELUDE + R.DRIVER, json.dumps({"app": str(webharness.APP), **payload}), timeout)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.mark.parametrize("rid", ["yingru", "nanyang", "luoyang", "jizhou", "youzhou"])
@pytest.mark.parametrize("profile", ["weekend", "season21"])
def test_letter_seals_never_move_or_squeeze_the_names(profile, rid):
    """每一區、你站每一處與在路上、五個手機地圖框（375×604／624／479、360×452／436）× 沒人推／每一塊一塊一塊下了戰書或交戰中／
    全部下了戰書／隨機配（戰書、進度條、冷卻）：名字框 0 對互壓（不壓別處的小圖、鄰區出口、不出畫面）、名字一個都不挪（擺的位置與字級
    跟沒人推時一樣：字印與那一圈紅不算進名字框）；「戰」字印找不到空位的、離別處的名字框隔不開 R_ROW_GAP 的，照 SEAL_LEFT 只准變少。"""
    out = _sweep(R._game(profile=profile), rid, R.PHONES)
    assert out["fails"] == [], out["fails"][:5]
    assert out["moved"] == [], out["moved"][:5]
    assert out["seals"] > 0
    unfit, tight = SEAL_LEFT[rid]
    assert len(out["unfit"]) <= unfit and len(out["tight"]) <= tight, (len(out["unfit"]), out["unfit"][:5], len(out["tight"]), out["tight"][:5])


@pytest.mark.parametrize("rid", ["yingru", "nanyang", "luoyang", "jizhou", "youzhou"])
def test_letter_seals_on_the_narrowest_phone(rid):
    """320 寬（地圖框 320×344）：潁川汝南本來就擺不開（PM 2026-10-21 先這樣），下了戰書也不更擠——名字一個都不挪；別的四區 0 對互壓。
    字印找不到空位的（蓋在自己名字框右上角）2026-10-22 量到 潁川汝南 123／574、南陽 2／95、洛陽 1／100，冀州、幽州 0（只准變少）。"""
    out = _sweep(R._game(profile="season21"), rid, [(320, 344)], timeout=600)
    assert out["moved"] == [], out["moved"][:5]
    if rid != "yingru":
        assert out["fails"] == [], out["fails"][:5]
    assert len(out["unfit"]) <= {"yingru": 123, "nanyang": 2, "luoyang": 1, "jizhou": 0, "youzhou": 0}[rid]
