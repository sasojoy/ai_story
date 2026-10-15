"""名聲草圖：拿真的 web/app.js、web/style.css 改，在 node 裡（tests/webharness.py）照真的引擎資料畫出每一種，組成一頁。
資料：build.py 用正式內容建的示範角色（views.json）。改過的 app.js 只放在草圖資料夾，不動遊戲程式。"""
from __future__ import annotations

import copy
import tempfile
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[5]  # repo 的根
MOCK = Path(__file__).parent  # mock.js、mock.css
HERE = Path(tempfile.gettempdir()) / "renown-sketch"  # build.py 的 views.json；這裡寫 mock_app.js、data.json、game.css
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import webharness  # noqa: E402
from test_prologue_web import DRIVER  # noqa: E402
from tianxia.journal import CSS as JOURNAL_CSS  # noqa: E402

V = json.loads((HERE / "views.json").read_text(encoding="utf-8"))

# ── 示範角色的名聲（照設計第二、四、五節；週末季，倍數 1）──
FAME = [("無名小卒", 0, []),
        ("小有名氣", 10, ["店家九七折", "狀態列、玩家卡寫你的稱號", "頭目遇上的機會多一成"]),
        ("名動一方", 25, ["九四折", "掛重賞的懸賞揭得到", "決戰名單標你的稱號", "頭目多兩成、打贏的賞也多兩成"]),
        ("威震州郡", 50, ["九折", "名將見面時情誼 +5", "天下大事傳開你的名號", "敵方陣營每週通緝你"]),
        ("天下聞名", 90, ["八五折", "打大場面天下大事點名", "通緝的賞更高", "擂台上排在你後面五名內的人挑得到你"])]
XIA = [("江湖遊俠", 5, ["敬俠的人見面情誼 +3", "書院教守義劍", "要江湖遊俠的俠選項"]),
       ("一方豪俠", 15, ["情誼 +6", "醫館療傷八五折", "百姓送糧、報信", "書院教養浩訣", "揭得了官府通緝", "要一方豪俠的俠選項"]),
       ("州郡大俠", 30, ["情誼 +9"]),
       ("天下名俠", 50, ["情誼 +12"])]
KOU = [("綠林好漢", 5, ["喜狠的人見面情誼 +3", "鐵匠鋪收購一階 3 兩、二階 8 兩（黑市價）", "綠林山寨教剪徑刀", "要綠林好漢的寇選項", "敬俠的人對你冷淡"]),
       ("江湖巨寇", 15, ["情誼 +6", "山寨教嘯林功", "要江湖巨寇的寇選項", "官府每週貼你的海捕文書（賞 30 兩）"]),
       ("州郡大盜", 30, ["情誼 +9", "官府的賞 50 兩"]),
       ("天下大盜", 50, ["情誼 +12", "官府的賞 80 兩"])]
LADDERS = {k: [{"title": t, "at": a, "perks": p} for t, a, p in rows] for k, rows in (("fame", FAME), ("xia", XIA), ("kou", KOU))}
SOURCES = {
    "fame": "事件的選擇；出陣攻打贏 +1；挑戰大勢人物本人打贏 +2；決戰自己出手 +2，自己那一邊大勝再 +2；首功、頭目戰、擂台、首創被人照著合。檢定失手、做了丟臉的事會掉。",
    "virtue": "事件的選擇（俠、寇才有的選項給得多）；散人交懸賞照你走的路記善名或惡名。稱號看兩個誰高，一樣多算俠。善名到 15、走俠的路悟「浩然」；惡名到 15、走寇的路悟「血煞」（不看第幾段）。",
}


def tier(n, rows):
    t = 0
    for i, (_, at, _) in enumerate(rows):
        if n >= at:
            t = i
    return t


def renown(fame, good, evil, sanren=False):
    ft = tier(fame, FAME)
    f = {"n": fame, "tier": ft, "title": FAME[ft][0], "from": FAME[ft][1]}
    if ft + 1 < len(FAME):
        f.update(next=FAME[ft + 1][0], at=FAME[ft + 1][1], gap=FAME[ft + 1][1] - fame)
    path = "寇" if evil > good else "俠"
    rows = KOU if path == "寇" else XIA
    n = evil if path == "寇" else good
    vt = sum(1 for _, at, _ in rows if n >= at)  # 0～4，0 沒有稱號
    v = {"good": good, "evil": evil, "path": path, "by": "惡名" if path == "寇" else "善名", "tier": vt,
         "title": rows[vt - 1][0] if vt else "", "from": rows[vt - 1][1] if vt else 0}
    if vt < len(rows):
        v.update(next=rows[vt][0], at=rows[vt][1], gap=rows[vt][1] - n)
    out = {"fame": f, "virtue": v, "ladders": LADDERS, "sources": SOURCES, "scale_note": None, "sanren": None}
    if sanren:
        out["sanren"] = [["求見門檻", f"每段抵 3，你現在抵 {3 * vt}"], ["打贏的經驗", f"每段 +5%，你現在 +{5 * vt}%"],
                         ["招募", f"第 2 段起每段 +5%，你現在 +{max(0, 5 * (vt - 1))}%"], ["散人奇遇", "第 3 段起遇得上"],
                         ["懸賞的銀兩", "第 4 段 ×1.25"]]
    return out


HERO_RN = renown(27, 18, 3)
KOU_RN = renown(12, 4, 22, sanren=True)
CARD_RN = {"韓七": {"titles": ["小有名氣", "江湖巨寇"], "path": "寇"}, "顧長風": {"titles": ["名動一方", "一方豪俠"], "path": "俠"}}
# 決戰名單：善惡第 1 段起、名望名動一方起；加入決戰時快照（名望優先排前面）
MERIT_RN = {"林驍": ["江湖遊俠"], "蘇硯": ["名動一方"], "顧長風": ["名動一方", "一方豪俠"],
            "葛三娘": ["綠林女傑"], "褚大石": ["威震州郡", "江湖巨寇"], "馬奎": []}


def with_renown(view, rn, fame, good, evil):
    m = copy.deepcopy(view)
    s = m["status"]
    s["renown"] = rn
    s["ranger"] = None  # 換成 renown 那一份（設計 2.5）
    s["minor"] = [["名望", fame], ["善名", good], ["惡名", evil]]
    return m


HERO = with_renown(V["hero"], HERO_RN, 27, 18, 3)
KOUV = with_renown(V["kou"], KOU_RN, 12, 4, 22)
CROSS = with_renown(V["cross"], renown(25, 18, 3), 25, 18, 3)
BATTLE = with_renown(V["battle"], HERO_RN, 27, 18, 3)
for side in ("left", "right"):
    for row in BATTLE["battle_gauge"]["merit"][side]:
        row["renown"] = MERIT_RN.get(row["name"], [])
EVENT = with_renown(V["event_kou"], KOU_RN, 12, 4, 22)

# ── 改過的 app.js（草圖專用）──
src = (ROOT / "web" / "app.js").read_text(encoding="utf-8").replace("\r\n", "\n")


def rep(s, old, new, count=1):
    assert s.count(old) == count, (s.count(old), old[:80])
    return s.replace(old, new)


src = rep(src, "\n  function whoNameHtml(s) {", "\n  function whoNameHtml_orig(s) {")
src = rep(src, '${s.minor.map(([k, v]) => `${esc(k)} ${v}`).join("　")}　｜　${s.attrs',
          '${s.renown ? "" : s.minor.map(([k, v]) => `${esc(k)} ${v}`).join("　") + "　｜　"}${s.attrs')
src = rep(src, '${S.sheet ? sheetHtml() : S.peer ? peerHtml() : ""}',
          '${S.sheet ? sheetHtml() : S.peer ? peerHtml() : S.renownSheet ? renownSheetHtml() : ""}')
src = rep(src, '<div class="peer-title">${[...c.affiliation.split("・"), `第${c.level}級`].map((t) => `<span class="peer-seg">${esc(t)}</span>`).join("・")}</div>',
          '<div class="peer-title">${peerSegs(c).map(peerSeg).join("・")}</div>${peerRenown(c)}')
src = rep(src, '<span>${esc(r.name)}</span><b>${r.merit}</b>', '${meritName(r)}<b>${r.merit}</b>')
src = rep(src, '<div class="g-mcols">', '<div class="g-mcols${RV().merit === "C" ? " sx-stack" : ""}">')
src = rep(src, 'const senseTag = (o) => (m.sense_help', 'const senseTag = (o) => o.sx_tag || (m.sense_help')
src = rep(src, '<span class="k sense">${esc(senseTag(o))}</span>', '<span class="k sense${o.sx_tag ? " sx-tag" : ""}">${esc(senseTag(o))}</span>')
src = rep(src, '<button class="btn ${followsMode(o.id) ? "go" : ""}" data-act="choose"', '<button class="btn ${followsMode(o.id) ? "go" : ""}${o.sx_mark ? " sx-mark" : ""}" data-act="choose"')
src = rep(src, 'nbHtml(o.label) : esc(o.label)}</span>`; };', 'nbHtml(o.label) : esc(o.label)}${o.sx_note ? `<small class="sx-note">${esc(o.sx_note)}</small>` : ""}</span>`; };')
src = rep(src, "${free}${menu}${senseNotes}", "${free}${menu}${sxAfterMenu()}${senseNotes}")
src = rep(src, 'aria-label="設定">⚙</button>\n      </div>\n      ${inPro ? "" : subs}',
          'aria-label="設定">⚙</button>\n      </div>\n      ${sxPanel()}\n      ${inPro ? "" : subs}')
# 假瀏覽器沒有 <template>：數值變化那一排照字串切（真的瀏覽器裡它被搬到敘事外面、收著也看得到）
src = rep(src, "\n  function splitChips(html) {", """
  function splitChips(html) {
    const m = html.match(/<div class="tx-chgs[^>]*>(?:(?!<\\/div>)[\\s\\S])*<\\/div>(?=<\\/div>\\s*$)/);
    return m ? [html.replace(m[0], ""), m[0]] : [html, ""];
  }
  function splitChips_orig(html) {""")
src = rep(src, "\n  function topHtml() {", (MOCK / "mock.js").read_text(encoding="utf-8") + "\n  function topHtml() {")
MOCK_APP = HERE / "mock_app.js"
MOCK_APP.write_text(src, encoding="utf-8")


def shot(m, S=None):
    """跑一次 render()，把 #page 放回 #app 裡，回整個畫面的 HTML。"""
    out = webharness.run(DRIVER, {"app": str(MOCK_APP), "m": m, "S": S or {}, "menxia": None, "stored": {}, "responses": {},
                                  "script": "H.render(); return {app: T.els.app.innerHTML, page: T.els.page.innerHTML};"})
    html = out["app"].replace('<main class="page" id="page"></main>', f'<main class="page" id="page">{out["page"]}</main>')
    assert out["page"], "頁面沒畫出來"
    return html


def fits(html):
    """「剛剛」短到放得下時，真的瀏覽器會拿掉「展開全文」（afterPage 量的）；假瀏覽器量不到，照示範內容手動標"""
    return html.replace('<div class="now clamp">', '<div class="now fits">')


GROUPS: dict[str, list] = {}


def add(group, vid, name, html, notes, rec=False, focus="", h=812, sub=None):
    GROUPS.setdefault(group, []).append({"id": vid, "name": name, "html": html, "notes": notes, "rec": rec, "focus": focus, "h": h, "sub": sub})


def top_only(html):
    """第一處底下的小條：只留狀態列（走寇的散人那一份）"""
    a = html.index('<header class="top"')
    b = html.index("</header>", a) + len("</header>")
    return '<div class="shell">' + html[a:b] + "</div>"


# 一：收起時
for v, name, rec, notes in (
    ("A", "接在頭銜後面，放不下先收名望稱號", True,
     ["設計的預設：散人收起時看得到的遊俠名號照舊在原位，換成善惡稱號",
      "顧長風（官軍・屯長）放不下兩個，收掉「名動一方」只留「一方豪俠」；韓七（散人）兩個都放得下",
      "一行不變，第一屏不多佔；字不縮",
      "缺點：陣營的人有頭銜，名望稱號多半被收掉，要點開才看得到"]),
    ("B", "稱號自己一行（換行）", False,
     ["名號那一行照舊，底下多一行兩個稱號，名望金色、俠青、寇赭",
      "兩個都看得到，不用估寬度",
      "缺點：狀態列多一行（約 19 px），每一頁的第一屏都少一截；江湖頁本來就擠（FB-107）"]),
    ("C", "放不下時整行縮字", False,
     ["放不下時頭銜那一行從 12px 縮到 10.5px，兩個稱號都留著",
      "缺點：手機上 10.5px 很小，長頭銜的人再加門派還是放不下，最後照樣省略號"]),
):
    S = {"rv": {"top": v}}
    add("A", f"1{v}", name, fits(shot(HERO, S)), notes, rec=rec,
        sub={"label": "走寇的散人（韓七）", "html": top_only(fits(shot(KOUV, S))), "h": 132})

# 二：展開時
for v, name, rec, notes, S, m in (
    ("A", "就地攤開在狀態列裡", False,
     ["點「名聲」那一行，就在底下攤開名望、善惡兩段的表（限高、自己捲）",
      "缺點：狀態列是黏在頂上的，攤開之後整個畫面只剩它；表要在小框裡捲，五段加八段字很多"],
     {"rv": {"card": "A"}, "showMore": True}, HERO),
    ("B", "底部抽屜，名望、善惡分兩頁", True,
     ["點「名聲」那一行，從底下拉出一張抽屜（同玩家卡、設定）；這一張停在名望頁",
      "一段一列：打勾的是已經有的，框起來的是現在這一段，往上的淡一點；進度條寫再幾點到下一段",
      "玩家卡上點別人的名聲開同一張，只是不寫他的數字",
      "原本那一行「名望 27・善名 18・惡名 3」拿掉，數字移到抽屜裡"],
     {"rv": {"card": "B"}, "showMore": True, "renownSheet": "fame"}, HERO),
    ("C", "兩條段落條，只寫這一段與下一段", False,
     ["名望、善惡各一條圓點，現在這一段給什麼、下一段再幾點給什麼各一句；點圓點看別段",
      "比 A 短，一眼看得到位置",
      "缺點：只寫兩段，其他段要一段一段點；寇的路、散人的好處要另外點開"],
     {"rv": {"card": "C"}, "showMore": True}, HERO),
    ("D", "B 換成走寇的散人（善惡頁）", False,
     ["同 B，韓七點到「善惡」那一頁：照惡名算，江湖巨寇",
      "俠的路收成一行（善名比惡名高就換過去）",
      "散人另列遊俠名號留下來的好處（求見、經驗、招募、奇遇、懸賞），照善惡稱號的段"],
     {"rv": {"card": "B"}, "showMore": True, "renownSheet": "virtue"}, KOUV),
):
    add("B", f"2{v}", name, fits(shot(m, S)), notes, rec=rec)

# 三：玩家卡（顧長風點「此地還有」的韓七）
for v, name, rec, notes in (
    ("A", "跟自己狀態列同一行「名聲」", True,
     ["頭銜底下一行「名聲　小有名氣・江湖巨寇　›」，跟自己的狀態列一模一樣",
      "學一次就看得懂別人的；點了開同一張說明抽屜（通用的，不寫他的數字）",
      "只寫稱號、不寫數字"]),
    ("B", "兩個小籤，照路上色", False,
     ["名望金色、俠青、寇赭，一眼看得出他走俠還是寇（截殺、揭官府通緝前看一眼）",
      "缺點：多一種只有這裡才有的樣子；顏色要跟 joy 對"]),
    ("C", "併進頭銜那一行", False,
     ["散人・小有名氣・江湖巨寇・第12級，一段一段不折斷",
      "最省地方；缺點：跟門派、陣營、頭銜混在一起，看不出哪兩個是名聲，也沒有地方點開說明"]),
):
    card = copy.deepcopy(V["card_kou"])
    card["renown"] = CARD_RN["韓七"]
    S = {"rv": {"peer": v}, "peer": {"name": "韓七", "card": card}}
    add("C", f"3{v}", name, fits(shot(HERO, S)), notes, rec=rec)

# 四：本場戰功
for v, name, rec, notes in (
    ("A", "名字後面同一行，只寫一個", True,
     ["欄寬只放得下一個稱號：有名動一方以上寫名望，沒有寫善惡稱號",
      "不加高度，三招不被往下推",
      "缺點：褚大石的「江湖巨寇」、你的「一方豪俠」被名望蓋過去"]),
    ("B", "名字底下一行，兩個都寫", False,
     ["兩個都看得到", "缺點：每一列變兩行，本場戰功高了 41px，三招跟著往下推"]),
    ("C", "兩軍上下排，一人一整列", False,
     ["一列夠寬，兩個稱號跟名字同一行", "缺點：從三列變六列，高了 76px，比 B 還多"]),
):
    add("D", f"4{v}", name, shot(BATTLE, {"rv": {"merit": v}}), notes, rec=rec)

# 五：事件選項（韓七是江湖巨寇，碰上米價一日三漲；俠的選項要一方豪俠）
OPT_A = {"id": "choice:3", "label": "當眾揭穿米商的斗，逼他照舊價開倉（要一方豪俠才做得來）", "enabled": False, "sx_mark": True}
OPT_B = {"id": "choice:3", "label": "當眾揭穿米商的斗，逼他照舊價開倉", "enabled": False, "sx_mark": True, "sx_tag": "俠", "sx_note": "要一方豪俠才做得來"}
for v, name, rec, notes in (
    ("A", "照原位灰掉，括號寫要什麼稱號", False,
     ["設計的預設：跟其他按不下去的選項同一個樣子",
      "缺點：括號接在長長的選項後面，375 寬折成兩三行；有稱號的人按得下去時，看不出這一顆是稱號換來的"]),
    ("B", "編號那一格寫「俠」，原因寫在第二行", True,
     ["編號換成一個「俠」字（寇的選項寫「寇」），有沒有稱號都這樣標",
      "有稱號的人看得出這一顆是名聲換來的；沒有的人第二行小字寫差什麼",
      "選項的字不變長"]),
    ("C", "不畫那一顆，選單底下一行小字", False,
     ["只寫「還有一種做法，要一方豪俠才做得來。」，不露做法",
      "缺點：設計寫「稱號不夠的人也看得到這一顆」，這樣看不到是什麼做法，少了往那條路走的理由"]),
):
    m = copy.deepcopy(EVENT)
    opts = m["options"]
    at = next(i for i, o in enumerate(opts) if o["id"] == "choice:free")
    if v == "A":
        opts.insert(at, OPT_A)
    elif v == "B":
        opts.insert(at, OPT_B)
    else:
        m["sx_hint"] = "還有一種做法，要一方豪俠才做得來。"
    add("E", f"5{v}", name, shot(m, {"rv": {}}), notes, rec=rec, focus=".options")

# 六：跨段那一刻（名望 24 → 25，名動一方）
CROSS_LINES = ('<div class="tx-line sx-mark">你的名號傳開了，江湖上漸漸有人稱你「名動一方」。</div>'
               '<div class="tx-line sx-mark">店家九四折；懸賞榜上的重賞揭得到了；決戰名單上標你的稱號；頭目找上門多兩成，賞也多兩成。</div>')


def cross_now(v):
    m = copy.deepcopy(CROSS)
    html = m["now"]
    html = rep(html, '<div class="tx-chgs">', '<div class="tx-chgs sx-mark">')
    html = rep(html, "善名 +2</span>", "善名 +2<small>（離「州郡大俠」還差 12）</small></span>")
    html = rep(html, "名望 +1</span>", "名望 +1<small>（離「威震州郡」還差 25）</small></span>")
    if v in ("A", "B"):
        html = rep(html, '<div class="tx-chgs sx-mark">', CROSS_LINES + '<div class="tx-chgs sx-mark">')
    if v == "B":
        html = rep(html, '<div class="tx-chgs sx-mark">', '<div class="tx-chgs sx-mark"><span class="tx-chg sx-rn-chip">名號傳開・名動一方 ›</span>')
    if v == "C":
        box = ('<div class="sx-rn-box sx-mark"><b>名號傳開了：名動一方</b>江湖上漸漸有人稱你「名動一方」。'
               '<small>這一段多了：店家九四折・重賞的懸賞揭得到・決戰名單標你的稱號・頭目多兩成、賞也多兩成</small></div>')
        html = re.sub(r'(<div class="tx-head">.*?</div>)', lambda mm: mm.group(1) + box, html, count=1)
    m["now"] = html
    return m


for v, name, rec, notes in (
    ("A", "照設計：兩行接在這一則最後", False,
     ["「剛剛」收著只露開頭幾行，這兩行落在「展開全文」底下，常常看不到",
      "得失那一排接差距：「名望 +1（離「威震州郡」還差 25）」"]),
    ("B", "得失那一排多一顆金色的「名號傳開」", True,
     ["得失那一排收著也看得到（它本來就搬在敘事外面），多一顆金色的籤，點了開名聲抽屜",
      "兩行照設計接在最後，展開全文看得到這一段多了什麼",
      "敘事不被擠掉"]),
    ("C", "名聲框排在最前面", False,
     ["標題底下先一個金框寫升到哪一段、多了什麼，一定看得到",
      "缺點：事件本身的敘事被擠到「展開全文」底下"]),
):
    add("F", f"6{v}", name, shot(cross_now(v), {"rv": {}}), notes, rec=rec)

print({k: len(v) for k, v in GROUPS.items()})

game_css = JOURNAL_CSS + "\n" + (ROOT / "web" / "style.css").read_text(encoding="utf-8").replace("\r\n", "\n") + "\n" + (MOCK / "mock.css").read_text(encoding="utf-8")
(HERE / "data.json").write_text(json.dumps(GROUPS, ensure_ascii=False), encoding="utf-8")
(HERE / "game.css").write_text(game_css, encoding="utf-8")
