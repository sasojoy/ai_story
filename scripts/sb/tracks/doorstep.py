"""same_behavior 一軌一檔：doorstep（這一檔登記 doorstep）。"""
from __future__ import annotations

import hashlib
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, db_text, emit, register_track

# ── terms（條款第 249 批：必須同意而沒同意的帳號，會改遊戲狀態的請求由伺服器拒絕；企劃者 2026-11-21「照這個做，兩處可以動」）──

VERSION = "/api/terms/version"


class DoorstepScenario(Scenario):
    """伺服器端擋條款同意的一軌（第 249 批開；--track doorstep，自己一個資料庫）。班底的名字都是原創（PM 11/04）。
    setup 照 charter、amend 先在記憶體裡把 Config.terms.enabled 關掉（不然註冊會帶勾選、記一筆現行版），掌門（管理者，直接建、從沒同意過）開季，
    褚未署照 API 註冊（沒勾選）、建角色、略過引導：開關打開之後他就是「必須同意而沒同意」的老帳號。
    closed 段（開關關著）：褚未署打一輪會改東西的請求（選項、/api/do 一個 MAIN_ACTIONS 與一個鎖外的 op、門下、商城購買、帖友書信、移動），
    再打一輪不擋的（GET /api/main、/api/me、/api/terms、客服開單）——關著的季兩邊要一個位元組都一樣。
    open 段（記憶體裡打開開關）：褚未署同樣兩輪；掌門（沒同意過）讀褚未署、按「不再提示」；范新簽照 API 註冊（兩個勾選、現行版號）、建角色、略過引導，打會改東西的那一輪。
    half：前半停在褚未署被擋過、還沒按同意的那一刻（讀一次 /api/terms）。
    後半第一件事無條件重新登入：褚未署再打一輪、登出、重新登入、按同意（現行版）、再打一輪；范新簽再按一次「不再提示」。
    每一段結束另寫旁檔 <db>-terms.sqlite 的段落雜湊。
    這一軌走不到的：同意過舊版的人（ask、考慮期過後、update_must 打開；amend 的班底只打條款自己的路由，包的 tests/ 守）；旁檔讀不到放行（包的 tests/ 守）。
    假人：碰不到（假人沒有帳號、不經伺服器），這一包也沒有 bots.py，所以沒有假人段。"""

    OLD, NEW = "褚未署", "范新簽"
    PLAYERS = {OLD: None}
    NEWBIE = "門外客"
    PHASES_FIRST = ["setup", "closed", "open", "half"]
    PHASES_SECOND = ["resume", "again"]

    def switch_on(self) -> None:
        self.c.config.terms.enabled = True

    def setup(self) -> None:
        self.c.config.terms.enabled = False
        super().setup()

    def side(self) -> Path:
        return self.db.with_name(f"{self.db.stem}-terms.sqlite")

    def phase_end(self, name: str) -> None:
        super().phase_end(name)
        path = self.side()
        emit(f"段落 {name} 條款旁檔", hashlib.sha256(db_text(path).encode("utf-8")).hexdigest() if path.is_file() else "不在")

    def version(self) -> str:
        self.begin()
        r = self.TestClient(self.server.app).get(VERSION)
        data = r.json() if r.status_code == 200 else {}
        emit(f"沒登入 GET {VERSION} {r.status_code}", data)
        return data.get("version", "") if isinstance(data, dict) else ""

    def writes(self, who: str) -> None:
        """會改東西的那一輪（沒同意的必同意帳號在新程式回 403）。"""
        self.call(who, "POST", "/api/choose", {"id": "act:doorstep_none"})
        self.call(who, "POST", "/api/do/hints_off", {})
        self.call(who, "POST", "/api/do/tavern_ask", {"text": "近來可好"})
        self.call(who, "POST", "/api/menxia/heal", {})
        self.call(who, "POST", "/api/mall/buy", {"item": "doorstep_none", "ref": f"doorstep-{who}"})
        self.call(who, "POST", "/api/mail/send", {"name": ADMIN, "text": "久仰"})
        self.call(who, "POST", "/api/travel", {"place": "doorstep_none", "mode": "walk"})

    def reads(self, who: str) -> None:
        """不擋的那一輪：讀畫面、條款自己、客服開單。"""
        self.call(who, "GET", "/api/main")
        self.call(who, "GET", "/api/me")
        self.call(who, "GET", "/api/terms")
        self.call(who, "POST", "/api/support/ticket", {"category": "account", "body": "條款要先按同意嗎"})

    # ── 段落 ──

    def closed(self) -> None:
        self.writes(self.OLD)
        self.reads(self.OLD)

    def open(self) -> None:
        self.switch_on()
        self.version()
        self.writes(self.OLD)
        self.reads(self.OLD)
        self.call(ADMIN, "POST", "/api/admin/player", {"name": self.OLD})
        self.call(ADMIN, "POST", "/api/do/hints_off", {})
        self.clients[self.NEW] = self.TestClient(self.server.app)
        self.passwords[self.NEW] = "pw-" + self.login_of(self.NEW)
        self.sign_up(self.NEW)
        self.call(self.NEW, "POST", "/api/character", {"name": self.NEW, "gender": "女"})
        self.do(self.NEW, "skip_tutorial")
        self.writes(self.NEW)

    def half(self) -> None:
        """前半停在這裡：褚未署被擋過、還沒按同意。"""
        self.call(self.OLD, "GET", "/api/terms")

    def resume(self) -> None:
        self.switch_on()
        self.login_all()

    def again(self) -> None:
        version = self.version()
        self.writes(self.OLD)
        self.call(self.OLD, "POST", "/api/logout", {})
        self.relogin(self.OLD)
        self.call(self.OLD, "POST", "/api/do/hints_off", {})
        self.call(self.OLD, "POST", "/api/terms/agree", {"version": version, "source": "gate"})
        self.writes(self.OLD)
        self.call(self.OLD, "GET", "/api/terms")
        self.call(self.NEW, "POST", "/api/do/hints_off", {})


# 改一個字（selftest）：旁檔查不到任何人同意過（人人 need 是 must），season21 again 那一段褚未署按過同意的回應與之後的 GET /api/terms 抓到
register_track("doorstep", DoorstepScenario, (("tianxia/features/terms/store.py",), ('        return None if row is None else row["version"]', "        return None")),
               "season21", covers=("terms",))
