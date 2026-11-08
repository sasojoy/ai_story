"""same_behavior 一軌一檔：facade（這一檔登記 facade）。"""
from __future__ import annotations

import hashlib
import re

from sb.base import Scenario
from sb.harness import ADMIN, emit, new_web, note_new, register_track
from sb.tracks.map import MapScenario

# ── shell_web（全部拆包第 64 批：網頁殼化）────────────────────────────────────────

# 以前就在 / 上的 js：照現在的先後。殼化切出來的新檔（base 沒有）從 / 的比對裡拿掉，它們的內容算進「所有 js 的行」。
FACADE_SCRIPTS = ("main.js", "map.js", "outing.js", "mall.js", "legacy.js", "arena_anim.js", "arena_scene.js", "admin.js", "app.js")
LOOM_OLD_SHEETS = ("style.css", "mall.css", "zhuan.css", "legacy.css")  # 以前就在 / 上的樣式：照現在的先後（第 67 批切出去的新檔排在 style.css 與 mall.css 之間）
FACADE_SHELL_FILES = {"shell.js"}  # 殼的掛鉤本身（新加的，不是切出來的）：base 沒有這一支，由網頁測試守
# 殼化本來就要改的那幾行（renderPage 那張分頁表、包檔尾的登記）：兩邊都不算，其餘每一行要一樣多
# 第 84 批：包的點擊框（registerClicks 那一行、函式頭、switch、兩個帶 // <包>Click 的收尾）與 app.js 查表的兩行，只認字面，單獨的 } 不放行
# 第 85 批：包的表單與 change 框（登記那一行、函式頭、帶 // <包>Form、// <包>Change 的收尾）與 app.js 查表的三行，同樣只認字面；
# 每包鏈的第一行（base 是 } else if、head 是 if）只認這 9 個；battle.js 清掉舊註解與恆真守衛的那兩行，有沒有被清掉的那一段都放行（這兩行寫進預期差異）
# 第 104 批：main.js、admin.js 拿掉恆真守衛的三行與 cultivation.js、companions.js、app.js 改舊註解的四行，同樣認整行字面、新舊兩種寫法都放行（這七行寫進預期差異）
# 第 105 批：faction 的畫法從 main.js 搬進 faction.js、頂層名字帶包名前綴：改名碰到的 10 行舊字與 11 行新字（main.js 那一行常數拆成兩行），認整行字面、新舊兩種寫法都放行（這幾行寫進預期差異）
FACTION_RENAMED_LINES = (
    '  const WK_JOIN = "先投一方", WK_JOIN_NOTE = "，才有章回、軍令和戰功", WK_JOIN_BTN = "投{side}", WK_HERE = "就在這"; // 待 joy 潤',
    '  function wkJoinHtml(m) {',
    '      const sub = near ? `${esc(near.name)}・${near.minutes | 0 ? `${near.minutes | 0} 分` : WK_HERE}` : esc(c.where[0] || "");',
    '      return `<button class="btn wk-join-btn side-${esc(c.id)}" ${act}>${WK_JOIN_BTN.replace("{side}", esc(c.name))}<small>${sub}</small></button>`;',
    '    return `<div class="wk-mid"><p class="ch-next"><b>${WK_JOIN}</b>${WK_JOIN_NOTE}</p><div class="wk-join">${two.map(btn).join("")}</div></div>`;',
    '  function wkSidesSheetHtml(sc) {',
    '      : `<details class="side side-${esc(c.id)}"><summary><h4>${esc(c.name)}<small>${esc([c.now, c.bar ? WK_SIDE_BAR.replace("{verb}", c.id === "guan" ? "壓" : "推").replace("{bar}", c.bar).replace("{title}", c.bar_title || "") : ""].filter(Boolean).join("・"))}</small></h4></summary>${dl(c)}</details>`)).join("")}</div>`;',
    '    const ch = chapterCardHtml(m, true), join = ch ? "" : wkJoinHtml(m);',
    '      return `${m.sides_card ? wkSidesSheetHtml(m.sides_card) : ""}${locked}${next}${nb ? `<h4 class="wk-sub">${esc(s.newbie.title)}</h4>${nb.panel}` : ""}` // 簽到改成每天第一次登入跳小窗（ckPopHtml），這裡不重複',
    '  const WK_SHEET = "這一季在打什麼", WK_RULES = "玩法說明・可能的結局", WK_SIDE_BAR = "{verb}到 {bar} 就是「{title}」"; // 待 joy 潤',
    '  const FACTION_JOIN = "先投一方", FACTION_JOIN_NOTE = "，才有章回、軍令和戰功", FACTION_JOIN_BTN = "投{side}", FACTION_HERE = "就在這"; // 待 joy 潤',
    '  function factionJoinHtml(m) {',
    '      const sub = near ? `${esc(near.name)}・${near.minutes | 0 ? `${near.minutes | 0} 分` : FACTION_HERE}` : esc(c.where[0] || "");',
    '      return `<button class="btn wk-join-btn side-${esc(c.id)}" ${act}>${FACTION_JOIN_BTN.replace("{side}", esc(c.name))}<small>${sub}</small></button>`;',
    '    return `<div class="wk-mid"><p class="ch-next"><b>${FACTION_JOIN}</b>${FACTION_JOIN_NOTE}</p><div class="wk-join">${two.map(btn).join("")}</div></div>`;',
    '  function factionSidesSheetHtml(sc) {',
    '      : `<details class="side side-${esc(c.id)}"><summary><h4>${esc(c.name)}<small>${esc([c.now, c.bar ? FACTION_SIDE_BAR.replace("{verb}", c.id === "guan" ? "壓" : "推").replace("{bar}", c.bar).replace("{title}", c.bar_title || "") : ""].filter(Boolean).join("・"))}</small></h4></summary>${dl(c)}</details>`)).join("")}</div>`;',
    '    const ch = chapterCardHtml(m, true), join = ch ? "" : factionJoinHtml(m);',
    '      return `${m.sides_card ? factionSidesSheetHtml(m.sides_card) : ""}${locked}${next}${nb ? `<h4 class="wk-sub">${esc(s.newbie.title)}</h4>${nb.panel}` : ""}` // 簽到改成每天第一次登入跳小窗（ckPopHtml），這裡不重複',
    '  const WK_SHEET = "這一季在打什麼", WK_RULES = "玩法說明・可能的結局"; // 待 joy 潤',
    '  const FACTION_SIDE_BAR = "{verb}到 {bar} 就是「{title}」"; // 待 joy 潤',
)
FACADE_SHELL_LINES = re.compile(r"\bregisterPage\(|^\s*const fn = \{ jianghu: pageJianghu\b"
                                r"|\bregisterClicks\(|^  async function \w+Click\(act, el, ev\) \{$|^    switch \(act\) \{$|^\s*\} // \w+Click$"
                                r"|^      const clicked = CLICKS\[act\];$|^      if \(clicked\) return await clicked\(act, el, ev\);"
                                r"|\bregisterForms\(|\bregisterChanges\(|^  async function \w+Form\(form, data\) \{$|^  async function \w+Change\(ev\) \{$|^\s*\} // \w+(?:Form|Change)$"
                                r'|^      const filed = FORMS\[form\.id\] \|\| \(form\.dataset && FORMS\["op:" \+ form\.dataset\.op\]\);$|^      if \(filed\) return await filed\(form, data\);$'
                                r"|^    await Promise\.all\(CHANGES\.map\(\(fn\) => fn\(ev\)\)\);$"
                                r'|^      (?:\} else )?if \(form\.id === "(?:peer-amount|say-form|own-name-form|gather-say-form|tav-ask|name-art|ad-mall-form|ad-player-form)"\) \{$'
                                r'|^      (?:\} else )?if \(form\.dataset && form\.dataset\.op === "shop-name-divine"\) \{$'
                                r"|^  // 場景卡只留面板沒寫的（這一幕的字、點名、職位、完整戰報），重複的拿掉（bpTrim）(?:；只切 main\.js 的網頁測試沒有 battle\.js：照舊)?$"
                                r"""|^    if \((?:typeof bpOn === "function" && )?bpOn\(m\) && m\.battle_panel\.me && !base\.startsWith\('<p class="battle-fold"'\)\) return bpTrim\(siegeStrip\(battleMvpHtml\(m\) \+ base, m\.siege\), m\);$"""
                                r"""|^    const bp = (?:typeof bpOn === "function" && )?bpOn\(m\);$"""
                                r"""|^    const bp = (?:typeof bpOn === "function" && )?bpOn\(m\) \? bpPanelHtml\(m, myTurn \? free : ""\) : "";$"""
                                r"""|^    const was = \(id\) => (?:\(typeof adTrendNow === "function" \? adTrendNow\(id\) : null\)|adTrendNow\(id\));$"""
                                r"""|^    sceneAsMe\(hm && hm\.worn \? hm\.worn\.style : ""\); // 台上站的是自己（(?:mall|looks)\.js）$"""
                                r"|^  // 「換一招」：萬寶閣絕招那一頁、招式庫開那一種打法的分頁（(?:mall|looks)\.js 的 openMallMoves）。$"
                                r"|^  // 人物簡介（Joy 11/6「不是所有玩家都那麼了解三國裡面的角色」；(?:server\.figure_intro|socialize 包 intro\.py 的 figure_intro)）：身分、是誰、本性；性子隨互動變了（設計稿「人物性子會變」，$"
                                r"|^  // 電腦上整片寬的 \.shop-body 照舊捲，內容照遊戲那一欄排（(?:style|shop)\.css 的 FB-225 那一段；手機上 \.shop-col 沒有樣式）$"
                                + "".join(f"|^{re.escape(line)}$" for line in FACTION_RENAMED_LINES)
                                # identity（帳號與客服第 201 批）：殼的登入頁掛格（shell.js 三行）與 renderGate 畫完叫格的那一行，只認字面
                                + r'|^  const GATE_SLOTS = \[\]; //|^  function registerGateSlot\(fn\) \{ GATE_SLOTS\.push\(fn\); \} //'
                                + r'|^  function drawGateSlots\(gate\) \{ for \(const fn of GATE_SLOTS\) fn\(gate, S\); \} //'
                                + r'|^    drawGateSlots\(\$app\.querySelector\("\.gate"\)\);$')
# support（帳號與客服第 211 批；設計第七節「殼多的行寫進 FACADE_SHELL_LINES」，企劃者 2026-11-08 點頭第 2 版）：客服在殼上接的那幾行。
# 改過的行原樣與改過的都放行（base、head 各去掉自己那一份），head 才有的兩行接縫只放行 head 那一行；開關關著時畫出來的不變，由 page 段與包的網頁測試比。
SUPPORT_SHELL_TOUCHED = (
    '    if (!S.main.admin && S.main.support_staff) return renderSupportDesk(); // 客服身分（support.js）：畫客服頁，不叫 /api/admin',
    '      if (S.main && S.main.admin) return renderAdmin();',
    '      if (S.main && (S.main.admin || S.main.support_staff)) return renderAdmin();',
    '    if (S.supportPage && typeof supportPageHtml === "function") return supportPageHtml(); // 客服自己一頁（support.js；開關關著時進不來）',
    '        <div class="top-row"><h3 style="flex:1">設定</h3>${S.main.admin ? `<a class="btn small ghost ad-entry" href="/admin">管理者工具 ›</a>` : ""}<button class="btn small ghost" data-act="sheet-close">關閉</button></div>',
    '        <div class="top-row"><h3 style="flex:1">設定</h3>${S.main.admin ? `<a class="btn small ghost ad-entry" href="/admin">管理者工具 ›</a>` : supportDeskLink()}<button class="btn small ghost" data-act="sheet-close">關閉</button></div>',
    '        ${pushRow()}',
    '        ${pushRow()}${supportRow()}',
    '  const PUSH_KIND_NAMES = [["letter", "來信"], ["duel", "約戰"], ["rally", "決戰集結"], ["raid", "被截殺"], ["xingshi", "被〈天下形勢〉提到"]];',
    '  const PUSH_KIND_NAMES = [["letter", "來信"], ["duel", "約戰"], ["rally", "決戰集結"], ["raid", "被截殺"], ["xingshi", "被〈天下形勢〉提到"], ["support", "客服"]]; // 客服（帳號與客服第 211 批）：伺服器的 kinds 有這個鍵才畫（客服關著沒有）。待 joy 潤',
    '    const list = on ? `<div class="push-kinds">${PUSH_KIND_NAMES.map(([k, name]) =>',
    '    const list = on ? `<div class="push-kinds">${PUSH_KIND_NAMES.filter(([k]) => k !== "support" || k in kinds).map(([k, name]) =>',
)
FACADE_SHELL_LINES = re.compile(FACADE_SHELL_LINES.pattern + "".join(f"|^{re.escape(line)}$" for line in SUPPORT_SHELL_TOUCHED))
# map.js 檔尾第 84 批多的點擊框：搬進去的 case 由 facade 軌「所有 js 的行」比，map 軌比的是框以外的部分（base 沒有這一塊，不變）
MAP_CLICK_FRAME = re.compile(rb"  async function mapClick\(.*?registerClicks\(mapClick, [^\n]*\n", re.S)


def _facade_page(html: str) -> str:
    """/ 的 HTML 除了多出來的 script 標籤與版本號之外一個字不變：?v= 抹掉（檔案變了版本本來就變，對不對另外驗），新檔的標籤連那一行拿掉。
    第 67 批：從 style.css 切出去的樣式同樣（新檔的 link 與它們上面那一行註解拿掉，它們的內容與先後由 drape 軌比）。"""
    html = re.sub(r"\?v=[0-9a-f]{10}", "", html)
    html = re.sub(r"<!-- 第 67 批從 style\.css 切出去的樣式[^\n]*-->\r?\n", "", html)
    html = re.sub(r'<link rel="stylesheet" href="/static/([^"]+)">\r?\n', lambda m: m[0] if m[1] in LOOM_OLD_SHEETS else "", html)
    return re.sub(r'<script src="/static/([^"]+)"></script>\r?\n', lambda m: m[0] if m[1] in FACADE_SCRIPTS else "", html)


class FacadeScenario(Scenario):
    """網頁的門面一軌（全部拆包第 64 批；--track facade，自己一個資料庫）。班底的名字都是原創（PM 11/04）。
    這一批搬的是網頁（web/app.js 切出修練、煉製）與 / 怎麼生出來；API 一條都沒動，別的軌比的是 API，走不到這裡。
    page 三種人（沒登入、玩家、管理者）各打 / 與 /admin：狀態碼、型別、快取標頭、整份 HTML（照 _facade_page，連行尾都比）、/admin 跟 / 是不是同一份。
    scripts 照 / 真的載入的那幾支一支一支抓：以前就有的（FACADE_SCRIPTS）寫狀態碼、型別、快取標頭；每一支的 ?v= 是不是那支檔內容的前十碼；
    「所有 js 的行」：每一支去掉檔頭（"use strict"; 以前的說明）之後的每一行（不含空行與 FACADE_SHELL_LINES）排序取 sha256，加上行數——
    切檔只換位置，所以這一個數字兩邊要一樣；改到任何一行就紅（selftest 的改一個字就是這一條抓的）。只驗每一行還在，不驗先後：先後由切檔腳本的逐段比對與網頁測試守。
    第 84 批把點擊的 case 從 app.js 搬進各包：case 行照舊算在這一條，放行的只有框與查表的字面（FACADE_SHELL_LINES）；map 軌比的 map.js 去掉框（MAP_CLICK_FRAME）。
    第 85 批把表單與 change 的分支從 app.js 搬進各包：分支的行照舊算在這一條，放行的只有框、查表的三行、每包鏈的第一行（只認那 9 個）與 battle.js 清掉舊註解、恆真守衛的那兩行。
    第 104 批把 sayLine、gatherSay 從 app.js 搬進 companions.js、explore.js：函式的行照舊算在這一條；放行的只有拿掉恆真守衛的三行與改舊註解的四行。
    第 105 批把 wkJoinHtml、wkSidesSheetHtml 從 main.js 搬進 faction.js 並改名（factionJoinHtml、factionSidesSheetHtml，常數帶 FACTION 前綴）：其餘的行照舊算在這一條；放行的只有改名碰到的 10 行舊字＋11 行新字（FACTION_RENAMED_LINES）。
    半舊半新：這一包沒有寫到一半的狀態（/ 開機時算一次、不碰存檔）。切在玩家登入著、/ 已經拿過的那一刻；後半是新程式重新開機，同樣三種人再打一遍。
    這一軌走不到的：瀏覽器真的執行這些檔（切檔之後的載入順序由網頁測試與波末實機驗）；/static/index.html 這個沒有人連的裸檔。
    假人：碰不到（假人只透過 Game 的公開行動做事，不抓網頁），所以沒有假人段；web/ 掃字另有測試。"""

    PLAYERS = {"簷下客": "guan"}
    NEWBIE = "叩門人"
    PHASES_FIRST = ["setup", "page", "scripts", "half"]
    PHASES_SECOND = ["resume", "page_again", "scripts_again"]
    GUEST = "簷下客"

    def viewers(self) -> list[tuple[str, object]]:
        return [("沒登入", self.TestClient(self.server.app)), (self.GUEST, self.clients[self.GUEST]), (ADMIN, self.clients[ADMIN])]

    def page(self) -> None:
        for who, client in self.viewers():
            self.begin()
            root, admin = client.get("/"), client.get("/admin")
            emit(f"{who} GET /", [root.status_code, root.headers.get("content-type"), root.headers.get("cache-control"), _facade_page(root.text)])
            emit(f"{who} GET /admin", [admin.status_code, admin.headers.get("content-type"), admin.headers.get("cache-control"), admin.text == root.text])

    def page_again(self) -> None:
        self.page()

    def scripts(self) -> None:
        self.begin()
        client = self.clients[self.GUEST]
        html = client.get("/").text
        lines: list[str] = []
        versions_ok = True
        for name, version in re.findall(r'<script src="/static/([^"?]+)\?v=([0-9a-f]{10})"></script>', html):
            r = client.get(f"/static/{name}")
            versions_ok &= hashlib.sha256(r.content).hexdigest()[:10] == version
            if name in FACADE_SCRIPTS:
                emit(f"GET /static/{name}", [r.status_code, r.headers.get("content-type"), r.headers.get("cache-control")])
            if name in new_web():  # compare --new（第 106 批）：新包的 js 不算進 lines，版本號照驗
                note_new("js", name)
            elif name not in FACADE_SHELL_FILES:
                body = r.text.replace("\r\n", "\n").split('"use strict";', 1)[1]
                lines += [ln for ln in body.split("\n") if ln.strip() and not FACADE_SHELL_LINES.search(ln)]
        emit("每一支的版本號都是內容的前十碼", versions_ok)
        emit("所有 js 的行（排序）", [len(lines), hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()])
        emit("/ 沒帶版本號的 script", re.findall(r'<script src="([^"?]+)"></script>', html))

    def scripts_again(self) -> None:
        self.scripts()

    def half(self) -> None:
        """切點：玩家登入著、/ 拿過了（這一包沒有別的半途狀態）；存檔裡有什麼照資料庫雜湊比。"""
        self.main(self.GUEST)

    def resume(self) -> None:
        self.login_all()


def _facade_map_web(self: MapScenario) -> None:
    """map 軌的網頁檔段（取代 MapScenario.web）：map.js 照舊比整檔 sha256、/ 載入它的那一行與 link 的版本號。
    以前還比 /static/app.js 整檔與 / 的每一支 script：殼化每一批都切 app.js、加新檔，那兩樣改由 facade 軌比（整份 HTML、所有 js 的行）。
    第 84 批起 map.js 多一塊點擊框（case 從 app.js 搬來）：整檔 sha256 算去掉那一塊的內容，/ 上那一行的 ?v= 抹掉（版本號對不對由 facade 軌比）。"""
    who = self.GUAN
    self.begin()
    client = self.clients[who]
    for url in ("/static/map.js", "/static/沒有這個檔.js"):
        r = client.get(url)
        body = MAP_CLICK_FRAME.sub(b"", r.content) if url == "/static/map.js" else r.content
        emit(f"GET {url}", [r.status_code, len(body), hashlib.sha256(body).hexdigest(),
                            r.headers.get("content-type"), r.headers.get("cache-control")])
    page = client.get("/")
    # 第 67 批起 style.css 會變、也切出新的樣式：link 只比以前就有的那幾支、版本號抹掉（樣式的內容與先後由 drape 軌比）
    links = [re.sub(r"\?v=[0-9a-f]{10}$", "", h) for h in re.findall(r'<link rel="stylesheet" href="([^"]+)"', page.text)]
    emit("GET / 載入的檔", [page.status_code, [re.sub(r"\?v=[0-9a-f]{10}$", "", s) for s in re.findall(r'<script src="([^"]+)"', page.text) if s.startswith("/static/map.js")],
                             [h for h in links if not h.startswith("/static/") or h[len("/static/"):] in LOOM_OLD_SHEETS]])


MapScenario.web = _facade_map_web


# 改一個字（selftest）：修練頁換一門的那一句（swapListHtml；第 64 批從 app.js 切到 cultivation.js，兩處找）
register_track("facade", FacadeScenario, (("web/cultivation.js", "web/app.js"), ("功法庫裡沒有別的", "功法庫裡沒有其他的")), "week7")
