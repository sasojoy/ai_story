"""same_behavior 一軌一檔：inkstone（這一檔登記 inkstone）。"""
from __future__ import annotations

from sb.base import Scenario
from sb.harness import emit, register_track

# ── identity（帳號與客服第 204 批：帳號四，綁定頁、近期驗證、解綁、補設與忘記密碼、門號回收、管理者工具；開關預設關）──────────

BIND_ROUTES = (
    ("GET", "/api/identity/me", None),
    ("GET", "/api/identity/session", None),  # 第 209 批「請用密碼重新登入」：base 沒有這條、head 關著，兩邊都 404
    ("POST", "/api/identity/reauth", {"password": "secret-pw"}),
    ("POST", "/api/identity/unbind", {"provider": "phone"}),
    ("POST", "/api/identity/password/set", {"login": "mo_qiao", "new": "inkstone-1", "again": "inkstone-1"}),
    ("POST", "/api/identity/password/reset", {"new": "inkstone-2", "again": "inkstone-2"}),
    ("POST", "/api/identity/code/release", {}),
    ("POST", "/api/identity/admin/accounts", {"q": "mo"}),
    ("POST", "/api/identity/code/send", {"channel": "phone", "to": "0912345678", "turnstile": "ok", "purpose": "bind"}),
    ("POST", "/api/identity/start", {"provider": "line", "purpose": "bind"}),
    ("POST", "/api/do/identity_view", {"target": "墨喬"}),
    ("POST", "/api/do/identity_unbind", {"target": "墨喬", "provider": "phone"}),
    ("POST", "/api/do/identity_delete", {"target": "墨喬"}),
)


class InkstoneScenario(Scenario):
    """帳號四的一軌（帳號與客服第 204 批；--track inkstone，自己一個資料庫）。班底的名字都是原創（PM 11/04）。
    三種設定的帳號綁定開關都關著（Config.identity.enabled 預設 False，金鑰檔也不在）：登入的人（按過略過教學的墨喬、沒按的溫硯秋）
    打第 204 批的七條新路由、綁定用途的寄碼與第三方開單、三個管理者工具（/api/do/identity_*），再讀 /api/me 與 /api/main 的 identity 開頭的鍵。
    base 沒有這七條路由與三個工具、head 有但關著：兩邊都是 404 {"detail": "Not Found"}（工具：base 不認得這個 op 回 404，head 先 gate 回 404）；
    綁定用途的寄碼與開單：兩邊都是 404（base 不認得 bind 用途，head 關著）。/api/me、/api/main 關著不帶 identity 格，兩邊一樣；
    登入照舊不寫旁檔（_start_session 開著才記 session_auth）。半舊半新：關著時不寫任何東西，切在前半打完之後；後半第一件事重新登入，再打一輪。
    這一軌走不到的：沒登入的人打這些路由（head 先認 cookie、回 401，base 沒有這條路、回 404：新包的路由本來就不同，照第 211 批認定不打，
    由包的 test_identity_gate_off.py::test_new_routes_401_without_login 守）；開著的路由、設定抽屜的「帳號綁定」與驗證碼那一頁
    （開著的行為由 tianxia/features/identity/tests/ 守；identity.js、identity.css 由 --new 扣，admin.js 改的行由 facade 的 IDENTITY_ADMIN_TOUCHED 放行）。
    假人：碰不到（假人沒有帳號，也不打 /api/identity/*），所以沒有假人段。"""

    PLAYERS = {"墨喬": None}
    NEWBIE = "溫硯秋"
    PHASES_FIRST = ["setup", "closed"]
    PHASES_SECOND = ["resume", "closed_again"]
    GUEST = "墨喬"

    def sweep(self, who: str) -> None:
        for method, url, body in BIND_ROUTES:
            self.request(who, method, url, body)

    def keys(self) -> None:
        _status, me = self.request(self.GUEST, "GET", "/api/me")
        emit("/api/me 的 identity 鍵", sorted(k for k in me if k.startswith("identity")) if isinstance(me, dict) else me)
        emit("/api/main 的 identity 鍵", sorted(k for k in self.main(self.GUEST) if k.startswith("identity")))

    def closed(self) -> None:
        for who in (self.GUEST, self.NEWBIE):
            self.sweep(who)
        self.keys()

    def resume(self) -> None:
        self.login_all()

    def closed_again(self) -> None:
        self.sweep(self.GUEST)
        self.keys()


# 改一個字（selftest）：本人綁定那一條的 gate 拿掉，關著的季 /api/identity/me 不再 404
register_track("inkstone", InkstoneScenario, (("tianxia/features/identity/routes.py",), (
    "        gate()\n        return me_info(request, token, account, shell.time.time())",
    "        return me_info(request, token, account, shell.time.time())",
)), "season21",
               covers=("identity",))
