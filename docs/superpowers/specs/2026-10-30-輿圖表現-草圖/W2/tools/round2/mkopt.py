"""FB-9094 的三種做法：把工作樹現在的 web/map.js、style.css 抄進 w2b/opt-<甲乙丙>/web/，各自改成原型（只在 scratchpad，不進 web/）。
每一處替換斷言剛好一處；讀進來 CRLF→LF，寫回 CRLF（跟工作樹一樣）。改好的 map.js、style.css 對工作樹的 diff 另存 opt-<X>.patch。"""
import difflib
import os
import shutil
import sys

WT = r"C:\Ray\專案\天下大勢\.claude\worktrees\wf_1654dfc8-5ce-1"
W2B = r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\w2b"


def load(name):
    with open(os.path.join(WT, "web", name), encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n")


def sub(text, old, new, label):
    n = text.count(old)
    assert n == 1, (label, n)
    return text.replace(old, new)


OPEN_OLD = """    if (!st.journey) for (const b of mvNeighbors(base, st)) { sx += b.x; sy += b.y; n += 1; }
    return camAt(g, sx / n, sy / n, mvZ0(g));
  }
"""

# ── 甲：取景避開 HUD（打開的取景照 HUD 蓋不到的那一塊挪中心，倍率不動）──
JIA_OPEN = """    if (!st.journey) for (const b of mvNeighbors(base, st)) { sx += b.x; sy += b.y; n += 1; }
    return openDodge(g, sx / n, sy / n, mvZ0(g));
  }
  // 【FB-9094 選項甲，原型】取景避開 HUD：打開的中心算完（你兩票＋腳下每一站一票），再上下左右挪（螢幕上一次 16px，左右最多 96、上下最多 64），
  // 倍率最多拉遠到 Z0 × 0.82（還是近景）。照的是「原本的取景裡露著（哪怕一點）的兩步內（含腳下）的小圖」：每一個取法數其中有一半以上看不到的
  // ——看不到＝落在露出來那一塊外面、或被看得到的浮著的那幾樣（區名、🔍、小地圖、右下兩顆）蓋住；挑最少的，一樣少挑倍率大的、再挑挪得少的
  // （本來就 0 就不動）。原本就在畫面外的（腳下一步的掛箭頭牌）不算，免得一律拉遠。◎ 也回到這裡
  function openDodge(g, cx, cy, z0) {
    const st = S.mapState, base = S.mapBase, c0 = camAt(g, cx, cy, z0);
    if (!st || st.journey || !st.here) return c0;
    const hops = mvHops(base, st.here), lvl = mvLevel(z0, g), room = mapRoom(g), vis = [0, 0, g.vw, room.bottom];
    const inter = (a, b) => Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
    const box = (b, c) => pinBox(b, st.places[b.id], c.x + b.x * c.z, c.y + b.y * c.z, lvl, null);
    const ids = base.places.filter((b) => hops[b.id] !== undefined && hops[b.id] <= 2 && st.places[b.id] && inter(box(b, c0), vis) > 0);
    const score = (c) => {
      const parts = hudParts(base, g, lvl, mvArea(base, st, c, g)), hud = Object.values(parts).filter((p) => !p.hide).map((p) => p.look);
      let bad = 0;
      for (const b of ids) {
        const bx = box(b, c), area = (bx[2] - bx[0]) * (bx[3] - bx[1]);
        let hid = area - inter(bx, vis);
        for (const h of hud) hid += inter(bx, h);
        if (hid >= 0.5 * area) bad++;
      }
      return bad;
    };
    let best = c0, bs = score(c0), bz = z0, bd = 0;
    if (!bs) return c0;
    for (const k of [1, 0.94, 0.88, 0.82]) for (let dy = -64; dy <= 64; dy += 16) for (let dx = -96; dx <= 96; dx += 16) {
      const z = z0 * k, d = Math.hypot(dx, dy);
      if (k === 1 && !d) continue;
      const c = camAt(g, cx + dx / z, cy + dy / z, z), s = score(c);
      if (s < bs || (s === bs && (z > bz + 1e-9 || (Math.abs(z - bz) < 1e-9 && d < bd)))) { best = c; bs = s; bz = z; bd = d; }
    }
    return best;
  }
"""

# ── 乙：小地圖收成一顆、◎ 全併成一顆 ──
YI_FAB_OLD = """<button type="button" class="mv-me" data-act="map-home" aria-label="${MV_WORDS.me}">◎</button><button type="button" data-act="map-fit" aria-label="${MV_WORDS.fit}">全</button></div>`;"""
YI_FAB_NEW = """<button type="button" class="mv-me" data-act="map-home" aria-label="${MV_WORDS.me}">◎</button></div>`; // 【選項乙】◎ 與 全 併成一顆"""
YI_HOME_OLD = """  function mapHome() {
    const g = mapGeom(document.getElementById("map"));
    if (g && S.mapBase && S.mapState) camFly(camOpen(g));
  }"""
YI_HOME_NEW = """  // 【FB-9094 選項乙，原型】◎ 與 全 併成一顆：不在打開的取景時是 ◎（回到打開），已經在打開的取景時寫「全」（看整張天下）
  function mapHome() {
    const g = mapGeom(document.getElementById("map"));
    if (!g || !S.mapBase || !S.mapState) return;
    camFly(atOpen(g) ? camFit(g) : camOpen(g));
  }
  function atOpen(g) {
    const o = camOpen(g), c = S.mapCam;
    return !!c && Math.abs(c.z - o.z) < 1e-3 && Math.abs(c.x - o.x) < 1 && Math.abs(c.y - o.y) < 1;
  }"""
YI_MINI_OLD = """    if (mini) {
      const show = lay.lvl > 0 && S.mapMode !== "timeline", me = youXY(base, st);
      const key = show ? `${base.key}|${miniSize(base, g).join("x")}|${me ? me.join(",") : ""}|${JSON.stringify(controlAt(st, mapWeek()))}` : "";
      if (!mini.dataset || mini.dataset.key !== key) {
        mini.innerHTML = show ? miniHtml(base, st, c, g) : "";"""
YI_MINI_NEW = """    if (mini) {
      // 【FB-9094 選項乙，原型】小地圖平常收成 🔍 底下一顆 40px 的鈕，點了才展開（展開時點一處＝中心移過去、再收起來）
      const show = lay.lvl > 0 && S.mapMode !== "timeline", me = youXY(base, st), open = !!S.mapMiniOpen;
      const key = show ? `${open ? "o" : "c"}|${base.key}|${miniSize(base, g).join("x")}|${me ? me.join(",") : ""}|${JSON.stringify(controlAt(st, mapWeek()))}` : "";
      if (!mini.dataset || mini.dataset.key !== key) {
        mini.innerHTML = show ? (open ? miniHtml(base, st, c, g) : `<button type="button" class="mv-mini-c" data-act="map-mini" aria-label="${MV_LOOK.mini}">圖</button>`) : "";"""
YI_FABLABEL_OLD = """    hudShow(g, lay.lvl, lay.area);
  }"""
YI_FABLABEL_NEW = """    hudShow(g, lay.lvl, lay.area);
    const home = document.querySelector && document.querySelector("#mv-fab .mv-me");
    if (home && S.mapState) { const t = atOpen(g) ? "全" : "◎"; if (home.textContent !== t) home.textContent = t; }
  }"""
YI_MINICLICK_OLD = """  function mapMini(el, ev) {
    const g = mapGeom(document.getElementById("map")), c = S.mapCam, wd = S.mapBase && S.mapBase.world;"""
YI_MINICLICK_NEW = """  function mapMini(el, ev) {
    if (!S.mapMiniOpen) { S.mapMiniOpen = true; drawMarks(); return; } // 【選項乙】收著的那一顆：先展開
    S.mapMiniOpen = false;
    const g = mapGeom(document.getElementById("map")), c = S.mapCam, wd = S.mapBase && S.mapBase.world;"""
YI_PARTS_OLD = """      fab: { look: [g.vw - 58, fb - 102, g.vw - 12, fb], room: [g.vw - 60, fb - 104, g.vw - 10, fb + 2] },
    };
    if (lvl > 0) {"""
YI_PARTS_NEW = """      fab: { look: [g.vw - 58, fb - 46, g.vw - 12, fb], room: [g.vw - 60, fb - 48, g.vw - 10, fb + 2] }, // 【選項乙】一顆
    };
    if (lvl > 0 && !S.mapMiniOpen) parts.mini = { look: [g.vw - 55, MV_MINI_TOP, g.vw - 15, MV_MINI_TOP + 40], room: [g.vw - 57, MV_MINI_TOP - 2, g.vw - 13, MV_MINI_TOP + 42] };
    else if (lvl > 0) {"""
YI_CSS_OLD = """.mv-mini svg { display: block; }"""
YI_CSS_NEW = """.mv-mini svg { display: block; }
/* 【FB-9094 選項乙，原型】小地圖收成一顆：🔍 底下 40px 的圓鈕（置中在 🔍 底下），點了才展開成整張小地圖 */
.mv-mini-c { display: grid; place-items: center; width: 40px; height: 40px; margin-right: 3px; padding: 0; border-radius: 50%; border: 1px solid rgb(42 35 28 / 0.55);
  background: rgb(244 236 220 / 0.94); color: var(--mv-ink); font: 700 15px var(--kai); box-shadow: 0 1px 4px rgb(0 0 0 / 0.18); cursor: pointer; pointer-events: auto; }"""

# ── 丙：被 HUD 蓋住一半以上的當畫面外（兩步內的掛箭頭牌）──
BING_OLD = """    const taken = blocked.slice(), out = [];
    for (const b of mvNeighbors(base, st)) {
      const q = st.places[b.id], px = c.x + b.x * z, py = c.y + b.y * z;
      if (boxCross(pinBox(b, q, px, py, lvl, null), vis)) continue; // 小圖還露著一點：不掛"""
BING_NEW = """    const taken = blocked.slice(), out = [];
    // 【FB-9094 選項丙，原型】被看得到的浮著的那幾樣（區名、🔍、小地圖、右下兩顆）蓋住一半以上的小圖當成畫面外：兩步內的都掛一顆箭頭牌（腳下一步整個在
    // 畫面外的照舊掛）。牌照舊沿著你到它的那一條線擺在畫面邊上、讓開浮著的那幾樣
    const hops = mvHops(base, st.here), hudLook = Object.values(hudParts(base, g, lvl, mvArea(base, st, c, g))).filter((p) => !p.hide).map((p) => p.look);
    const inter = (a, b) => Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
    const cands = base.places.filter((b) => st.places[b.id] && (hops[b.id] === 1 || hops[b.id] === 2)).sort((a, b) => hops[a.id] - hops[b.id]);
    for (const b of cands) {
      const q = st.places[b.id], px = c.x + b.x * z, py = c.y + b.y * z, pb = pinBox(b, q, px, py, lvl, null), pa = (pb[2] - pb[0]) * (pb[3] - pb[1]);
      const off = !boxCross(pb, vis), covered = !off && hudLook.some((h) => inter(pb, h) >= 0.5 * pa);
      if (!(off && hops[b.id] === 1) && !covered) continue; // 腳下一步整個在畫面外、或被浮著的蓋住一半以上，才掛"""
BING_BOX_OLD = """      let box = null, side = first;
      for (const sd of [first, ...["l", "r", "t", "b"].filter((x) => x !== first)]) {"""
BING_BOX_NEW = """      let box = null, side = first;
      if (covered) { // 【選項丙】被蓋住的：牌貼在蓋住它的那一樣旁邊（左、右、下、上），箭頭指著那一樣（它在底下）；可以壓到它自己的小圖；都擺不下才照畫面邊上的擺法
        const hb = hudLook.reduce((a, o) => (inter(pb, o) > inter(pb, a) ? o : a), hudLook[0]);
        const own = (o) => o[0] <= px && o[2] >= px && o[1] <= py && o[3] >= py && o[2] - o[0] < 90;
        const my = Math.min(E[3] - h / 2, Math.max(E[1] + h / 2, py)), mx = Math.min(E[2] - w / 2, Math.max(E[0] + w / 2, px));
        for (const [sd, bx] of [["r", [hb[0] - 4 - w, my - h / 2, hb[0] - 4, my + h / 2]], ["l", [hb[2] + 4, my - h / 2, hb[2] + 4 + w, my + h / 2]],
          ["t", [mx - w / 2, hb[3] + 4, mx + w / 2, hb[3] + 4 + h]], ["b", [mx - w / 2, hb[1] - 4 - h, mx + w / 2, hb[1] - 4]]]) {
          if (bx[0] >= E[0] && bx[2] <= E[2] && bx[1] >= E[1] && bx[3] <= E[3] && !taken.some((o) => !own(o) && boxCross(bx, o))) { box = bx; side = sd; break; }
        }
      }
      if (!box) for (const sd of [first, ...["l", "r", "t", "b"].filter((x) => x !== first)]) {"""


def build(tag, edits_js, edits_css):
    js, css = load("map.js"), load("style.css")
    for old, new, label in edits_js:
        js = sub(js, old, new, label)
    for old, new, label in edits_css:
        css = sub(css, old, new, label)
    d = os.path.join(W2B, f"opt-{tag}", "web")
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    for name, text in (("map.js", js), ("style.css", css)):
        with open(os.path.join(d, name), "w", encoding="utf-8", newline="") as f:
            f.write(text.replace("\n", "\r\n"))
    patch = []
    for name, text in (("map.js", js), ("style.css", css)):
        patch += difflib.unified_diff(load(name).splitlines(True), text.splitlines(True), f"a/web/{name}", f"b/web/{name}")
    with open(os.path.join(W2B, f"opt-{tag}.patch"), "w", encoding="utf-8", newline="\n") as f:
        f.writelines(patch)
    print(tag, "ok", sum(1 for x in patch if x.startswith("+") and not x.startswith("+++")), "lines added")


build("甲", [(OPEN_OLD, JIA_OPEN, "camOpen")], [])
build("乙", [(YI_FAB_OLD, YI_FAB_NEW, "fab"), (YI_HOME_OLD, YI_HOME_NEW, "home"), (YI_MINI_OLD, YI_MINI_NEW, "mini"),
             (YI_FABLABEL_OLD, YI_FABLABEL_NEW, "fablabel"), (YI_MINICLICK_OLD, YI_MINICLICK_NEW, "miniclick"), (YI_PARTS_OLD, YI_PARTS_NEW, "parts")],
      [(YI_CSS_OLD, YI_CSS_NEW, "css")])
build("丙", [(BING_OLD, BING_NEW, "pills"), (BING_BOX_OLD, BING_BOX_NEW, "pillbox")], [])
sys.exit(0)
