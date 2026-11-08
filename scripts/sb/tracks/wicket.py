"""same_behavior 一軌一檔：wicket（這一檔登記 wicket）。"""
from __future__ import annotations

from sb.base import Scenario
from sb.harness import emit, register_track

# ── identity（帳號與客服第 202 批：帳號二，LINE、Google 登入；開關預設關）──────────────

IDENTITY_ROUTES = (
    ("GET", "/api/identity/gate", None),
    ("POST", "/api/identity/start", {"provider": "line", "purpose": "login"}),
    ("POST", "/api/identity/start", {"provider": "google", "purpose": "login"}),
    ("GET", "/auth/line/callback?code=c1&state=s1", None),
    ("GET", "/auth/google/callback?error=access_denied&state=s2", None),
)
CHARACTER = ("POST", "/api/identity/character", {"name": "葉觀瀾二", "gender": "女"})
ANON = "過路客"


class WicketScenario(Scenario):
    """帳號二的一軌（帳號與客服第 202 批；--track wicket，自己一個資料庫）。班底的名字都是原創（PM 11/04）。
    三種設定的帳號綁定開關都關著（Config.identity.enabled 預設 False，金鑰檔也不在）：沒登入的過路客打 /api/me 與四條不用登入的
    （gate、兩家的 start、兩種回呼）；登入的人（按過略過教學的葉觀瀾、沒按的方拾一）打 /api/me、同樣那幾條，再加建角色那一條。
    base 沒有 start、callback、character 這三條、head 有但關著：兩邊都是 404 {"detail": "Not Found"}；/api/me 關著不帶 identity 旗標，兩邊一樣。
    半舊半新：關著時不寫任何東西（旁檔不建），切在前半打完之後；後半第一件事重新登入、過路客換一個新的瀏覽器，再打一輪。
    這一軌走不到的：沒登入的人打建角色那一條（head 先認 cookie、回 401，base 沒有這條路、回 404：新包的路由本來就不同，
    照第 211 批認定不打，由包的 test_character_without_pending_is_401_and_double_submit_is_idempotent 守）；首頁 index.html 與 app.js 多的那一行
    （facade、drape 兩軌照 --new 扣與 FACADE_SHELL_LINES 放行）；開著的路由與登入頁（開著的行為由 tianxia/features/identity/tests/ 守）。
    假人：碰不到（假人沒有帳號，也不會走第三方登入），所以沒有假人段。"""

    PLAYERS = {"葉觀瀾": None, "簡清秋": None}
    NEWBIE = "方拾一"
    PHASES_FIRST = ["setup", "closed"]
    PHASES_SECOND = ["resume", "closed_again"]
    GUEST = "葉觀瀾"

    def anon(self) -> None:
        self.clients[ANON] = self.TestClient(self.server.app)

    def sweep(self, who: str, character: bool) -> None:
        self.request(who, "GET", "/api/me")
        for method, url, body in IDENTITY_ROUTES:
            self.request(who, method, url, body)
        if character:
            self.request(who, *CHARACTER)

    def closed(self) -> None:
        self.anon()
        self.sweep(ANON, character=False)
        for who in (self.GUEST, self.NEWBIE):
            self.sweep(who, character=True)
        emit("identity 的鍵", sorted(k for k in self.main(self.GUEST) if k.startswith("identity")))

    def resume(self) -> None:
        self.clients.pop(ANON, None)
        self.login_all()
        self.anon()

    def closed_again(self) -> None:
        self.sweep(ANON, character=False)
        self.sweep(self.GUEST, character=True)
        self.main(self.GUEST)


# 改一個字（selftest）：開關的那一道 gate 反過來，關著的季每條路由都不再 404
register_track("wicket", WicketScenario, (("tianxia/features/identity/routes.py",), ("if not identity_base.on(shell.CONTENT):", "if identity_base.on(shell.CONTENT):")), "season21",
               covers=("identity",))
