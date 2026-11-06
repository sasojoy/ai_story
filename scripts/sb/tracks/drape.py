"""same_behavior 一軌一檔：drape（這一檔登記 drape）。"""
from __future__ import annotations

import hashlib
import json
import re

from sb.harness import emit, register_track
from sb.tracks.facade import FacadeScenario, LOOM_OLD_SHEETS

# ── shell_web（全部拆包第 67 批：style.css 照包分）─────────────────────────────────────
LOOM_HEAD = re.compile(r"^/\* 天下大勢：.*全部拆包第 67 批從 style\.css 切出來.*\*/$")  # 新檔第一行的說明（base 沒有）


def _drape_rules(css: str, media: str, sink: dict) -> None:
    """照瀏覽器讀的順序把樣式攤平：(media 條件, 選擇器, 屬性) → [值, ...]。多一個 } 不吃掉（瀏覽器會把它算進下一條的選擇器、那一條作廢），所以指紋連這種作廢也比。"""
    i, n = 0, len(css)
    while i < n:
        brace = css.find("{", i)
        if brace < 0:
            return
        semi = css.find(";", i, brace)  # 頂層的 @import 這種
        if semi >= 0 and css[i:semi].lstrip().startswith("@"):
            i = semi + 1
            continue
        depth, j = 1, brace + 1
        while j < n and depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        head, body = " ".join(css[i:brace].split()), css[brace + 1:j - 1]
        if head.startswith(("@media", "@supports")):
            _drape_rules(body, f"{media} & {head}" if media else head, sink)
        elif head.startswith("@"):
            sink.setdefault((media, head, ""), []).append(" ".join(body.split()))  # @keyframes 同名後蓋前、@font-face：整段當一個值
        else:
            for sel in re.split(r",(?![^()]*\))", head):
                for decl in re.split(r";(?![^()\"']*[\"')])", body):
                    if ":" in decl:
                        prop, value = decl.split(":", 1)
                        sink.setdefault((media, sel.strip(), prop.strip().lower()), []).append(" ".join(value.split()))
        i = j


class DrapeScenario(FacadeScenario):
    """樣式的一軌（全部拆包第 67 批；--track drape，自己一個資料庫）。班底的名字都是原創（PM 11/04）。
    別的軌比的是 API 與 js，樣式一個字都走不到；這一批把 web/style.css 切到各包的 web/<包>.css，同權重後蓋前，先後就是行為，所以另開這一軌。
    sheets 照 / 真的載入的 link 一支一支抓：
    以前就有的（LOOM_OLD_SHEETS）寫狀態碼、型別、快取標頭與先後；每一支的 ?v= 是不是內容的前十碼；
    「所有 css 的行」：每一支去掉新檔第一行說明之後的每一行（不含空行）排序取 sha256，加上行數——切檔只換位置，這個數字兩邊要一樣，改到任何一行就紅（selftest 改一個字就是這一條抓的）；
    「同選擇器同屬性的值」：照載入順序把規則攤平，(media, 選擇器, 屬性) → 值的序列，整張取 sha256——同一個選擇器在兩處寫同一個屬性、搬完誰蓋誰反了就紅，多一個 } 作廢的那一條也算在裡面。
    這一軌走不到的：兩個不同的選擇器打到同一個元素時誰蓋誰（要看畫面，切檔時由 scripts/css_order_check.py 與波末實機守）；瀏覽器真的算出來的樣子。
    半舊半新：樣式沒有寫到一半的狀態（/ 開機時算一次、不碰存檔）。切在玩家登入著、/ 已經拿過的那一刻；後半是新程式重新開機，同樣再抓一遍。
    假人：碰不到（假人只透過 Game 的公開行動做事，不抓網頁），所以沒有假人段；web/ 掃字另有測試。"""

    PLAYERS = {"織機客": "guan"}
    NEWBIE = "穿梭人"
    PHASES_FIRST = ["setup", "sheets", "half"]
    PHASES_SECOND = ["resume", "sheets_again"]
    GUEST = "織機客"

    def sheets(self) -> None:
        self.begin()
        client = self.clients[self.GUEST]
        html = client.get("/").text
        found = re.findall(r'<link rel="stylesheet" href="/static/([^"?]+)\?v=([0-9a-f]{10})">', html)
        emit("/ 載入的舊樣式（先後）", [name for name, _ in found if name in LOOM_OLD_SHEETS])
        lines: list[str] = []
        rules: dict = {}
        versions_ok = True
        for name, version in found:
            r = client.get(f"/static/{name}")
            versions_ok &= hashlib.sha256(r.content).hexdigest()[:10] == version
            if name in LOOM_OLD_SHEETS:
                emit(f"GET /static/{name}", [r.status_code, r.headers.get("content-type"), r.headers.get("cache-control")])
            body = r.text.replace("\r\n", "\n")
            lines += [ln for ln in body.split("\n") if ln.strip() and not LOOM_HEAD.match(ln)]
            _drape_rules(re.sub(r"/\*.*?\*/", "", body, flags=re.S), "", rules)
        emit("每一支的版本號都是內容的前十碼", versions_ok)
        emit("所有 css 的行（排序）", [len(lines), hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()])
        flat = json.dumps(sorted((list(k), v) for k, v in rules.items()), ensure_ascii=False)
        emit("同選擇器同屬性的值（照載入順序）", [len(rules), hashlib.sha256(flat.encode("utf-8")).hexdigest()])
        emit("/ 沒帶版本號的樣式", re.findall(r'<link rel="stylesheet" href="(/static/[^"?]+)">', html))

    def sheets_again(self) -> None:
        self.sheets()


# 改一個字（selftest）：簽到第四階小字的字級（第 67 批從 style.css 切到 checkin.css，兩處找）
register_track("drape", DrapeScenario, (("web/checkin.css", "web/style.css"), (".ck-p4 small { font: 10.5px", ".ck-p4 small { font: 10.6px")), "week7")
