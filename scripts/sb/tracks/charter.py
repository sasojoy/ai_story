"""same_behavior 一軌一檔：charter（這一檔登記 charter）。"""
from __future__ import annotations

import hashlib
from pathlib import Path

from sb.base import Scenario
from sb.harness import db_text, emit, register_track

# ── terms（條款，Joy 2026-11-09 PR #193，第 206 批接註冊；開關 Config.terms.enabled 預設關；旁檔 <db>-terms.sqlite）：測試流程優化第 113 批 ──────────────

PAGES = ("/terms", "/privacy")
VERSION = "/api/terms/version"
LATE = "晚簽者"  # 開著段才註冊的那一位（兩個勾選、版號都對）


class CharterScenario(Scenario):
    """條款的一軌（測試流程優化第 113 批；--track charter，自己一個資料庫）。班底的名字都是原創（PM 11/04）。
    關著段（三種設定的 Config.terms.enabled 都關著）：沒登入的人看兩頁（開關關著也看得到，200，寫全文的雜湊）、打 /api/terms/version（404）；
    登入的嚴守約打 GET /api/terms、POST /api/terms/agree（404），讀 /api/main 的 terms 鍵；沒勾選照樣註冊得了（setup 那一輪就是）。
    開著段（記憶體裡打開開關，兩個行程都開）：沒登入的人拿版號；註冊沒勾、只勾一個、勾了版號不對都被擋（同一句、不算一次註冊），兩個勾選加現行版才開得了帳號（記一筆 register）；
    關著時註冊的嚴守約 GET /api/terms 的 need 是 must、帶舊版號同意回 409、帶現行版同意之後 need 空；剛註冊的那一位 need 一開始就是空的；沒登入打 /api/terms。
    前半停在嚴守約按過同意、溫如故還沒按的那一刻。後半第一件事無條件重新登入：三位再讀 /api/terms（同意紀錄在旁檔，換了行程照樣在）、溫如故按同意（source update 照記、
    不認得的 source 記成 gate）、兩頁再看一次。每一段結束另寫旁檔 <db>-terms.sqlite 的段落雜湊。
    這一軌走不到的：條款改版的考慮期（need 是 ask；要換內容檔的 version 與 published，由包的 test_terms.py 守）；identity 建角色那一步的勾選（identity 開著的軌是 A 案，企劃者 11/09「等要開帳號功能再做」）。
    假人：碰不到（假人沒有帳號，不註冊、不打 /api/terms），這一包也沒有 bots.py，所以沒有假人段。"""

    KEEPER, SECOND = "嚴守約", "溫如故"
    PLAYERS = {KEEPER: None, SECOND: None}
    NEWBIE = "方入門"
    PHASES_FIRST = ["setup", "closed", "open", "half"]
    PHASES_SECOND = ["resume", "again"]

    def switch_on(self) -> None:
        self.c.config.terms.enabled = True

    def side(self) -> Path:
        return self.db.with_name(f"{self.db.stem}-terms.sqlite")

    def phase_end(self, name: str) -> None:
        super().phase_end(name)
        path = self.side()
        emit(f"段落 {name} 條款旁檔", hashlib.sha256(db_text(path).encode("utf-8")).hexdigest() if path.is_file() else "不在")

    def anon(self, method: str, url: str, body: dict | None = None):
        """沒登入的人（不放進 self.clients：login_all 會拿它去重新登入）。頁面寫狀態、長度與全文雜湊。"""
        self.begin()
        client = self.TestClient(self.server.app)
        r = client.post(url, json=body if body is not None else {}) if method == "POST" else client.get(url)
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            data = {"len": len(r.text), "sha": hashlib.sha256(r.text.encode("utf-8")).hexdigest()}
        emit(f"沒登入 {method} {url} {r.status_code}", data)
        return r.status_code, data

    def pages(self) -> None:
        for url in PAGES:
            self.anon("GET", url)

    def register(self, name: str, extra: dict, keep: bool) -> None:
        """開帳號（同 setup 那一輪的表單，多帶 extra）；keep 才放進 self.clients（後半要重新登入），被擋的不放。"""
        self.begin()
        client = self.TestClient(self.server.app)
        login, password = self.login_of(name), "pw-" + self.login_of(name)
        r = client.post("/api/register", json={"login": login, "password": password, "again": password, **extra})
        emit(f"{name} 註冊 {sorted(extra)} {r.status_code}", r.json())
        if keep and r.status_code == 200:
            self.clients[name], self.passwords[name] = client, password
            self.call(name, "POST", "/api/character", {"name": name, "gender": "女"})

    # ── 段落 ──

    def closed(self) -> None:
        self.pages()
        self.anon("GET", VERSION)
        self.request(self.KEEPER, "GET", "/api/terms")
        self.request(self.KEEPER, "POST", "/api/terms/agree", {"version": "x", "source": "gate"})
        main = self.main(self.KEEPER)
        emit("terms 的鍵", sorted(k for k in main if k.startswith("terms")) if isinstance(main, dict) else None)

    def open(self) -> None:
        self.switch_on()
        _, data = self.anon("GET", VERSION)
        version = data.get("version", "") if isinstance(data, dict) else ""
        self.register("未勾者", {}, keep=False)
        self.register("半勾者", {"age_ok": True, "terms_version": version}, keep=False)
        self.register("舊版者", {"age_ok": True, "terms_agree": "on", "terms_version": "1999-01-01"}, keep=False)
        self.register(LATE, {"age_ok": "on", "terms_agree": True, "terms_version": version}, keep=True)
        self.request(LATE, "GET", "/api/terms")
        self.anon("GET", "/api/terms")
        self.request(self.KEEPER, "GET", "/api/terms")
        self.request(self.KEEPER, "POST", "/api/terms/agree", {"version": "1999-01-01", "source": "gate"})
        self.request(self.KEEPER, "POST", "/api/terms/agree", {"version": version, "source": "gate"})
        self.request(self.KEEPER, "GET", "/api/terms")

    def half(self) -> None:
        """前半停在這裡：溫如故還沒按同意（need 是 must）。"""
        self.request(self.SECOND, "GET", "/api/terms")

    def resume(self) -> None:
        self.switch_on()
        self.login_all()

    def again(self) -> None:
        _, data = self.anon("GET", VERSION)
        version = data.get("version", "") if isinstance(data, dict) else ""
        for who in (self.KEEPER, self.SECOND, LATE):
            self.request(who, "GET", "/api/terms")
        self.request(self.SECOND, "POST", "/api/terms/agree", {"version": version, "source": "update"})
        self.request(self.SECOND, "POST", "/api/terms/agree", {"version": version, "source": "什麼都不是"})
        self.request(self.SECOND, "GET", "/api/terms")
        self.pages()


# 改一個字（selftest）：沒同意過的帳號 need 從 must 改成空的（不跳同意層），season21 open 那一段嚴守約的 GET /api/terms 抓到
register_track("charter", CharterScenario, (("tianxia/features/terms/rules.py",), ("        return MUST", "        return NONE")), "season21",
               covers=("terms",))
