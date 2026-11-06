"""same_behavior 一軌一檔：facade（這一檔登記 facade）。"""
from __future__ import annotations

import hashlib
import re

from sb.base import Scenario
from sb.harness import ADMIN, emit, register_track
from sb.tracks.map import MapScenario

# ── shell_web（全部拆包第 64 批：網頁殼化）────────────────────────────────────────

# 以前就在 / 上的 js：照現在的先後。殼化切出來的新檔（base 沒有）從 / 的比對裡拿掉，它們的內容算進「所有 js 的行」。
FACADE_SCRIPTS = ("main.js", "map.js", "outing.js", "mall.js", "legacy.js", "arena_anim.js", "arena_scene.js", "admin.js", "app.js")
LOOM_OLD_SHEETS = ("style.css", "mall.css", "zhuan.css", "legacy.css")  # 以前就在 / 上的樣式：照現在的先後（第 67 批切出去的新檔排在 style.css 與 mall.css 之間）
FACADE_SHELL_FILES = {"shell.js"}  # 殼的掛鉤本身（新加的，不是切出來的）：base 沒有這一支，由網頁測試守
# 殼化本來就要改的那幾行（renderPage 那張分頁表、包檔尾的登記）：兩邊都不算，其餘每一行要一樣多
FACADE_SHELL_LINES = re.compile(r"\bregisterPage\(|^\s*const fn = \{ jianghu: pageJianghu\b")


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
            if name not in FACADE_SHELL_FILES:
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
    以前還比 /static/app.js 整檔與 / 的每一支 script：殼化每一批都切 app.js、加新檔，那兩樣改由 facade 軌比（整份 HTML、所有 js 的行）。"""
    who = self.GUAN
    self.begin()
    client = self.clients[who]
    for url in ("/static/map.js", "/static/沒有這個檔.js"):
        r = client.get(url)
        emit(f"GET {url}", [r.status_code, len(r.content), hashlib.sha256(r.content).hexdigest(),
                            r.headers.get("content-type"), r.headers.get("cache-control")])
    page = client.get("/")
    # 第 67 批起 style.css 會變、也切出新的樣式：link 只比以前就有的那幾支、版本號抹掉（樣式的內容與先後由 drape 軌比）
    links = [re.sub(r"\?v=[0-9a-f]{10}$", "", h) for h in re.findall(r'<link rel="stylesheet" href="([^"]+)"', page.text)]
    emit("GET / 載入的檔", [page.status_code, [s for s in re.findall(r'<script src="([^"]+)"', page.text) if s.startswith("/static/map.js")],
                             [h for h in links if not h.startswith("/static/") or h[len("/static/"):] in LOOM_OLD_SHEETS]])


MapScenario.web = _facade_map_web


# 改一個字（selftest）：修練頁換一門的那一句（swapListHtml；第 64 批從 app.js 切到 cultivation.js，兩處找）
register_track("facade", FacadeScenario, (("web/cultivation.js", "web/app.js"), ("功法庫裡沒有別的", "功法庫裡沒有其他的")), "week7")
