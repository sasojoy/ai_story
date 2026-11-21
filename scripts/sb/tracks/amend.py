"""same_behavior 一軌一檔：amend（這一檔登記 amend）。"""
from __future__ import annotations

import hashlib
from pathlib import Path

from sb.base import Scenario
from sb.harness import CLOCK, db_text, emit, register_track

# ── terms（條款換版號之後，同意過舊版的人；客服上線補件第 243 批，企劃者 2026-11-21「改成強制按同意」）──────────────

OLD = "2026-11-v1"  # 旁檔裡先寫一筆「同意過這一版」：現行版（內容檔）換過號，這一版就是舊版
VERSION = "/api/terms/version"


class AmendScenario(Scenario):
    """條款改版的一軌（第 243 批；--track amend，自己一個資料庫）。班底的名字都是原創（PM 11/04）。
    setup 照 charter 先在記憶體裡把 Config.terms.enabled 關掉（不然註冊會帶勾選、記一筆現行版），開好四個帳號。
    seed 段打開開關，直接在旁檔 <db>-terms.sqlite 替柳前諾、易新章各寫一筆同意 OLD（source register；同意過舊版的人只能這樣造：
    註冊的勾選只認現行版）。三位讀 /api/terms：柳前諾、易新章同意過舊版，初見客從沒同意過；柳前諾帶舊版號按同意（409）；
    Config.terms 有 update_must 這一格時（第 243 批起）在記憶體裡關掉、易新章再讀一次、再打開（沒有這一格的程式跳過，三下都照讀）。
    half 段：柳前諾再讀一次——前半停在他看過改版、還沒按同意的那一刻。
    後半第一件事無條件重新登入；柳前諾按同意（source update）、再讀；初見客按同意（source gate）、再讀；易新章再讀；沒登入拿版號。
    每一段結束另寫旁檔的段落雜湊。
    這一軌走不到的：註冊頁的兩個勾選與 identity 建角色（charter 守）；過了考慮期的那一頭（假的鐘停在 2026-10-25 前後，比內容檔的 published 早）。
    假人：碰不到（假人沒有帳號，不打 /api/terms），這一包也沒有 bots.py，所以沒有假人段。"""

    FIRST, SECOND, FRESH = "柳前諾", "易新章", "初見客"
    PLAYERS = {FIRST: None, SECOND: None, FRESH: None}
    NEWBIE = "方寸心"
    PHASES_FIRST = ["setup", "seed", "half"]
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

    def set_must(self, on: bool) -> bool:
        """第 243 批的 Config.terms.update_must；沒有這一格的程式回 False、什麼都不動。"""
        cfg = self.c.config.terms
        if "update_must" not in type(cfg).model_fields:
            return False
        cfg.update_must = on
        return True

    def seed_old(self, who: str) -> None:
        from tianxia.features.terms.store import ConsentStore

        self.begin()
        ConsentStore(self.side()).record(self.login_of(who), OLD, "register", CLOCK[0])
        emit(f"{who} 旁檔先寫同意 {OLD}", True)

    def version(self) -> str:
        self.begin()
        r = self.TestClient(self.server.app).get(VERSION)
        data = r.json() if r.status_code == 200 else {}
        emit(f"沒登入 GET {VERSION} {r.status_code}", data)
        return data.get("version", "") if isinstance(data, dict) else ""

    # ── 段落 ──

    def seed(self) -> None:
        self.switch_on()
        self.set_must(True)
        version = self.version()
        for who in (self.FIRST, self.SECOND):
            self.seed_old(who)
        for who in (self.FIRST, self.SECOND, self.FRESH):
            self.request(who, "GET", "/api/terms")
        self.request(self.FIRST, "POST", "/api/terms/agree", {"version": OLD, "source": "update"})
        emit("現行版不是舊版", version != OLD)
        if self.set_must(False):
            self.request(self.SECOND, "GET", "/api/terms")
            self.set_must(True)
        emit("有 update_must 這一格", "update_must" in type(self.c.config.terms).model_fields)

    def half(self) -> None:
        """前半停在這裡：柳前諾看過改版、還沒按同意。"""
        self.request(self.FIRST, "GET", "/api/terms")

    def resume(self) -> None:
        self.switch_on()
        self.set_must(True)
        self.login_all()

    def again(self) -> None:
        version = self.version()
        self.request(self.FIRST, "GET", "/api/terms")
        self.request(self.FIRST, "POST", "/api/terms/agree", {"version": version, "source": "update"})
        self.request(self.FIRST, "GET", "/api/terms")
        self.request(self.FRESH, "POST", "/api/terms/agree", {"version": version, "source": "gate"})
        self.request(self.FRESH, "GET", "/api/terms")
        self.request(self.SECOND, "GET", "/api/terms")


# 改一個字（selftest）：要按同意時回應不帶三句重點，season21 seed 那一段三位的 GET /api/terms 抓到（第 243 批改 rules.need 之後這一句照舊在）
register_track("amend", AmendScenario, (("tianxia/features/terms/routes.py",), ('        out["summary"] = data["change_summary"]', '        out["summary"] = []')),
               "season21", covers=("terms",))
