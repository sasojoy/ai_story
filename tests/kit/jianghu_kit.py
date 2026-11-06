"""tests/web/test_jianghu_page_web.py 拆走的測試與留下的測試共用的小工具（全部拆包第 61 批，只搬位置、不改內容）。"""
from __future__ import annotations
import re
from pathlib import Path
import pytest
import server
import webharness
import random
from tianxia.engine import Game
from test_prologue_web import _enlist_main
import html as htmllib
from conftest import real_content, renown_unscaled
from tianxia.engine import Game
from conftest import real_content
from test_prologue_web import run as run_prologue_web


# ── 原 test_fb107_first_screen.py（整檔搬進來） ──
# FB-107（QA 93e7037，2026-10-08，375×812）：師父「碰到才說」的框、兩行的 💡、決戰集結（戰場、「此地還有」、結伴）在畫面上時，
# 行動列掉到分頁列底下。企劃者 10/5：框留在行動列上面、話不切。
#
# 網頁現在畫好之後量一次（web/app.js 的 fitFirstScreen）：行動列（一組選項時是最後一顆）的下緣離分頁列不到 FIT_MARGIN，就照
# FIT_STEPS 的順序一步一步收，放得下就停——放得下的畫面一點都不動。順序：間距 → 框收緊（話不切）→ 💡 收成一行 → 戰鬥卡片底下的補充
# 收成一行 → 第一回合收進「展開過程」→「剛剛」只露三行 → 決戰時所在地的描述收成一行 → 集結那一句收成一行 → 一組選項的鈕縫與鈕高。
# 每一樣點得開；「得失」與結果那幾行、框裡的話不收。
#
# 這裡把那幾個函式從 app.js 切出來，在 node 裡接一個假的頁面跑：假頁面的行動列下緣照「哪幾個元素身上掛了哪個 class」算（每一樣省多少 px
# 寫在 SAVE），量的是收的順序、停在哪、點開過的不收、重量之前先還原、在路上與序章不收。真的 px 是 375×812 估出來的（fix-1008 的交接報告）。
# 樣式另外釘住：每一步只動它該動的東西。

ROOT = Path(__file__).parents[2]


node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


GUIDE_DRIVER = r"""
// 說書人那一段（GUIDE_KEY 到 guideHtml）切出來：決戰集結時入伍、步驟的框預設收成一行（企劃者 2026-10-08，FB-107 修正輪）
const a = src.indexOf("\n  const GUIDE_KEY");
const b = src.indexOf("\n  }\n", src.indexOf("\n  function guideHtml(")) + 4;
const store = {};
globalThis.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } };
const S = { guideRoad: null, guideFull: null, guidePage: null, main: { scene: input.scene || "" } };
const esc = (s) => String(s);
const pro = () => input.pro || null;
const H = new Function("S", "esc", "pro", src.slice(a, b) + "\nreturn { guideHtml, openGuide, shutGuide };")(S, esc, pro);
const kind = (g, onRoad = false) => { const html = H.guideHtml(g, onRoad); return html.includes('class="guide-line"') ? "line" : html.includes("card guide") ? "card" : ""; };
const step = { speaker: "老石", key: "r3_battle", text: "要打大仗了。\n\n先按戰場名字旁的『加入』報名。", line: "去報名", done: [], end: false, paged: true, full: true };
const ack = { speaker: "師父", key: "h_injury", text: "打一場掉的氣血，大半會自己回來。", done: [], end: true };
finish(new Function("H", "S", "kind", "step", "ack", input.script)(H, S, kind, step, ack));
"""


MUSTER_SCENE = "<p><strong>長社火攻</strong></p>\n<p>集結中，還剩現實 {} 秒。選擇陣營加入；集結期間照常行動。</p>\n<hr />\n<p>【長社】危險 ★★</p>"


def _guide(script, scene="", **extra):
    return webharness.run(GUIDE_DRIVER, {"script": script, "scene": scene, **extra})


# ── 原 test_fb120_battle_fold.py（整檔搬進來） ──
# FB-120（QA 32efa2c6，2026-10-09，375×812）：全服決戰開打的那段時間，戰場那一塊把每個人的第一屏都佔掉。
#
# Game.scene_text 有全服決戰時大家都看得到戰場：只能觀戰的人是戰場＋分隔線＋自己眼前的事。開打後每回合多一句開頭、放手一搏的原文與
# 模型的故事，最近 5 段都在；QA 量到宛城開打、官軍站在潁川時師父的框在 1130、行動列 1226～1324（分頁列頂 756）。
#
# 現在（只改網頁，web/app.js 的 battleScene）：沒在打這一場的人（人不在決戰的大區、沒加入、沒臨時投效），場景裡開打中的戰場收成一行
# 「宛城之戰　第 N 回合・點開看」（待 joy 潤，字在 app.js 的 BATTLE_PEEK），點了攤開、底下多一顆「收起戰場」（BATTLE_SHUT）；
# 攤開記的是戰場的名字（S.battleOpen），回合往下走、輪詢重畫都不收回去，自己按收起或這一場打完才算。參戰的人照舊。
#
# 認的是伺服器給的場景（Markdown 轉好的 HTML）：分隔線（<hr />）之前那一段有開打後的回合數（「（第 N／M 回合」）、而且不是參戰者的那一句
# （離開大區的「這回合不出手」、倒下的「你已經倒下」）。兩個正規式（BATTLE_ROUND、BATTLE_MINE）寫在 app.js、這裡用真的戰場驗：
# 戰鬥那條線（FB-109、FB-113）改了 _battle_scene_text 的寫法，這裡就紅。
#
# 網頁用真實內容（週末設定）的宛城之戰、真的 /api/main，照 tests/web/test_prologue_web.py 的做法把整支 app.js 放進 node
# （scripts/test_for.py 改到 app.js 時靠這個檔名挑到這裡）。

BATTLE = "wancheng_jia"  # 宛城之戰（南陽）


def _player(on, name, faction, place):
    game = Game.new(on, name, rng=random.Random(0))
    game.client = None
    game.set_hints_off(True)
    game.state.player.faction, game.state.player.location = faction, place
    return game


def _fight_round(fighter):
    """參戰的那一個送出這一回合（場上只有他，送出就結算）。對面沒人、一回合推滿 push_max（正式 20），戰局先拉回中線，免得兩回合就收場。"""
    fighter.world.mutate_battle(lambda b: setattr(b, "trend", 50))
    move = next(o.id for o in fighter.options(odds=False) if o.enabled and o.id.startswith("battle:act:"))
    fighter.choose(move)


def _text(html):
    """拿掉標籤與空白只比字：戰況一回合一段（app.js 的 roundBlocks）會把伺服器的回合標題與清單換成自己的標記，字一個不少（收成一行的舊回合多寫一次摘要，不算）。"""
    html = re.sub(r"<summary><b>(.*?)</b><span>.*?</span></summary>", r"\1", html)  # 收成一行的舊回合：那一句摘要底下清單裡還有
    return re.sub(r"\s+", "", re.sub(r"<[^>]*>", "", html))


@pytest.fixture
def battle(on):
    """宛城之戰開打、打過一回合：一個臨時投效官軍的散人在宛城打，一個官軍的人站在潁川（QA 那一場）。"""
    watcher = _player(on, "觀戰甲", "guan", "yingchuan")
    fighter = _player(on, "參戰乙", None, "wan_city")
    watcher.world.start_battle(on.battles[BATTLE], now=watcher.now)
    fighter.choose("battle:enlist:guan")
    fighter.world.mutate_battle(lambda b: setattr(b, "muster_deadline_real", -1.0))
    fighter.options()
    assert fighter.world.get_battle().phase == "active"
    _fight_round(fighter)
    return watcher, fighter


def _consts():
    driver = ('finish(new Function(konst("BATTLE_PEEK") + "\\n" + konst("BATTLE_SHUT") + '
              '"\\nreturn { peek: BATTLE_PEEK, shut: BATTLE_SHUT };")());')
    return webharness.run(driver, {})


def _div_inner(html, head):
    """html 裡開頭是 head 的那一個 <div …> 的內容（數 div 的層數找對應的收尾）；沒有這個 div 就原樣回傳。"""
    start = html.find(head)
    if start < 0:
        return html
    open_end = html.index(">", start) + 1
    depth = 0
    for tag in re.finditer(r"<(/?)div\b", html[start:]):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return html[open_end:start + tag.start()]
    return html[open_end:]


def _scene(page):
    """場景卡的內容，拿掉戰局條（它自己的測試在 test_battle_gauge.py）：這裡比的是伺服器給的那一段文字。"""
    scene = re.search(r'<section class="card scene(?: rv)?">(.*?)</section>', page, re.S).group(1)
    scene = _div_inner(scene, '<div class="rv-scene')  # 介面重整：場景文字包在 rv-scene 裡（上面是「剛剛」那一條，下面是結伴與邀請）
    start = scene.find('<div class="gauge"')
    if start < 0:
        return scene
    depth = 0
    for tag in re.finditer(r"<(/?)div\b", scene[start:]):  # 戰局條裡還有好幾層 div：數到對應的那一個收尾
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            end = scene.index(">", start + tag.start()) + 1
            return scene[:start] + scene[end:]
    return scene


def _round(m):
    return int(re.search(r"（第 (\d+)／\d+ 回合", m["scene"]).group(1))


def _folded(m):
    return (f'<p class="battle-fold" data-act="battle-open" role="button" tabindex="0" aria-expanded="false">'
            f'宛城之戰　第 {_round(m)} 回合・{_consts()["peek"]}</p>')


CLICK = """const tap = async (act) => { const el = { dataset: { act }, classList: { contains: () => false } };
  await T.docListeners.click[0]({ target: { closest: () => el } }); return T.els.page.innerHTML; };"""


def _sided(html):
    """戰報裡「〔官軍〕」開頭的那一句（有人發動戰法；開局的【基礎吐納】就帶小戰法），網頁畫成陣營的小章（觀戰的是官軍：官軍・我方）。"""
    import re
    # 網頁把「〔招名〕某某……」畫成「某某……〔招名〕」（app.js 的 trailMoves，招式與絕學稿案第一節）
    return re.sub(r"〔官軍〕〔([^〕]+)〕([^〔]*?)(?=【|$)", r"官軍・我方\2〔\1〕", _text(html))


# ── 原 test_fb087_here_fold.py（整檔搬進來） ──
# FB-087：江湖頁「此地還能做 N 件事」摺疊被重畫收起來（QA 驗 FB-077，2026-10-06，375×812）。
#
# 摺疊裡的按鈕（例：求見盧植）被擋下來（「對方還沒答話，稍等。」、排太久）之後，choose() 重畫整頁、摺疊就收起來了；輪詢帶來新畫面時
# renderPage() 也一樣。現在摺疊的開合記在 S.here（玩家自己開關的、這一處），重畫照它補回。附帶 guide-3b 審查 Minor 11：入伍段第一道軍令
# 那一步（框上帶 glow act:duty）摺疊本來每次重畫都自動打開、跟收起它的玩家打架——現在每一處只在那一步開頭自動打開一次，之後照玩家的。
#
# 網頁沒有建置步驟也沒有瀏覽器：照 tests/web/test_prologue_web.py 的做法，把整支 app.js 放進 node 的假瀏覽器，餵它真的引擎給的 /api/main，
# 用假的 toggle 事件當玩家點開、收起摺疊，看重畫出來的 HTML。假 DOM 裡 details 的開合就是 HTML 裡有沒有 open：驗的是「重畫畫出什麼」。

# 驅動程式共用的小工具：fold() 讀頁面上那個摺疊現在畫成開著（true）、收著（false）、沒畫（null）；toggle(open) 送一個玩家點開／收起
# 的 toggle 事件；refuse() 讓下一個 /api/choose 被伺服器擋下來（400）、並讓 choose() 失敗後會重畫（按下去的那顆鈕還標著 busy）
HELPERS = """
const fold = () => { const hit = T.els.page.innerHTML.match(/<details class="fold here"( open)?>/); return hit ? !!hit[1] : null; };
const toggle = (open) => T.docListeners.toggle[0]({ target: Object.assign(Object.create(T.Element.prototype), { matches: (sel) => sel === "details.here", open }) });
const redraw = () => { T.els.page.innerHTML = ""; H.renderPage(); return fold(); };
const press = (id) => T.docListeners.click[0]({ target: { closest: () => ({ dataset: { act: "choose", id }, classList: { contains: () => false, add() {}, remove() {} } }) } });
const refuse = (error) => {
  T.ctx.setTimeout = () => 0; // toast() 的計時器不要拖住這個請求
  T.ctx.fetch = (url, opts) => { T.calls.push([url, JSON.parse(opts.body)]); return Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({ error }) }); };
  T.qs[".options .btn.busy, .act-ink.busy"] = {};
};
"""


def _script(body: str) -> str:
    return HELPERS + body


@pytest.fixture
def glowing(on):
    """入伍段第一道軍令那一步：框上帶 glow（act:duty），「此地還能做」裡有發光的巡哨。"""
    m = _enlist_main(on)
    assert m["guide"]["glow"] == ["act:duty"] and any(o["id"] == "act:duty" for o in m["options"])
    return m


# ── 共用 ─────────────────────────────────────────────


def _muster(on, who="guan", place="luzhi_camp", battle="guangzong", name="甲"):
    """廣宗決戰集結中（真實內容、週末設定）：who 是陣營或 None（散人），人在 place；提示關掉（框不在這個測試裡）。"""
    game = Game.new(on, name, rng=random.Random(0))
    game.client = None
    game.set_hints_off(True)
    p = game.state.player
    p.faction, p.location = who, place
    if battle is not None:  # None：同一個世界裡已經開著的那一場
        game.world.start_battle(on.battles[battle], now=game.now)
    return game


def _page(m):
    # 介面重整：「此地還能做」的摺疊換成此地可為那一排圓章與「全部」清單；這裡打開「全部」，每一顆（灰的也是）都畫成一顆有 data-id 的鈕
    return run_prologue_web(m, "H.S.hereAll = true; return H.pageJianghu();")


def _consts_fb105():
    """app.js 裡那一小句與箭頭（MUSTER_NOTE、MUSTER_ARROW）：joy 潤了字，這裡跟著讀，不必改測試。"""
    driver = 'finish(new Function(konst("MUSTER_NOTE") + "\\n" + konst("MUSTER_ARROW") + "\\nreturn { note: MUSTER_NOTE, arrow: MUSTER_ARROW };")());'
    return webharness.run(driver, {})


def _note_html(kind):
    """那一小句畫出來的樣子：字照常唸，箭頭藏起來不唸，id 給那一排鈕的 aria-describedby 用。"""
    c = _consts_fb105()
    return (f'<span class="muster-note" id="muster-note">{htmllib.escape(c["note"][kind], quote=False)}'
            f'<span aria-hidden="true"> {c["arrow"][kind]}</span></span>')


ROW_ATTRS = 'role="group" aria-label="參戰" aria-describedby="muster-note"'


# ── 原 test_fb664_grey_cell_sub_web.py（整檔搬進來） ──
# FB-664（練功入口對比圖開發回報，PM 2026-10-21 給號）：行動列「交友」灰著時，格子小字是整句「這裡沒有能說上話的人」
# （10 個字、100 px），四格時兩頭被格子切掉。灰格小字最多六個字（一行約 60 px、10 px 的字）：格子寫短的，整句放行動列底下那一行
# （actNotesHtml）。談滿了的交友（一類一顆開著時，單人地點的交友是 act:socialize 不是 call:）同一個毛病，一併改。沒有 node 就略過。
# node 排不了版：這裡看格子裡寫什麼、底下那一行寫什麼；375／320 寬有沒有被切在瀏覽器裡量（Range 對格子的矩形），數字寫在試玩回饋 FB-664 那一列。

def _game(at, faction=None):
    content = renown_unscaled(real_content("week7"))  # 一類一顆開著（開季蓋章）；求見門檻照原數（名望 15）
    content.config.auto_open_first_season = True
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.client = None
    p = game.state.player
    p.location, p.faction, p.stamina = at, faction, float(content.config.stamina_max)
    return game


def _bar(game):
    return run_prologue_web(server.main_view(game), "return H.actionBar(H.S.main);")


def _cell(bar, key):
    return re.search(rf'<button class="act-ink[^"]*" data-key="{key}".*?</button>', bar, re.S).group(0)


def _face(cell):
    """格子上看得到的那一截（開頭標籤裡 data-why 那一句不算）。"""
    return cell[cell.index(">") + 1:]


# ── 原 test_fb_batch_b.py ──

# ── FB-136：決戰開打那一刻看不到三招的鈕 → 輪到出招的回合，三招緊接在場景底下，放手一搏的輸入框與說書人的框排在三招後面 ──
# 在 d2827139 上重現（14 天、官軍、騎著馬上陣、老石「要打大仗了」的框還在，375×812）：框 608～738、輸入框與底下那句 746～843、
# 三招 855～999，分頁列頂 756——第一屏一顆都看不到（QA 那時是 733 起）。照在路上的排法（FB-055）：輪到你按的排前面。
# node 裡沒有版面，這裡只比先後；量到的位置寫在試玩回饋那一列

SHOWDOWN_BOX = {"speaker": "老石", "key": "h_showdown", "scene": "", "text": "「要打大仗了。」", "line": "", "done": [], "end": True,
                "pending": False, "full": True, "hint": True}
