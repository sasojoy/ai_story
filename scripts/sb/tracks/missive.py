"""same_behavior 一軌一檔：missive（這一檔登記 missive）。"""
from __future__ import annotations

import json

from sb.base import Scenario
from sb.harness import emit, register_track

# ── identity（帳號與客服第 203 批：帳號三，Email、手機驗證碼登入；開關預設關）──────────────────────

CODE_ROUTES = (
    ("POST", "/api/identity/code/send", {"channel": "phone", "to": "0912345678", "turnstile": "ok"}),
    ("POST", "/api/identity/code/send", {"channel": "email", "to": "qinghe@example.com", "turnstile": "ok"}),
    ("POST", "/api/identity/code/verify", {"code": "123456"}),
)


class MissiveScenario(Scenario):
    """驗證碼登入的一軌（帳號與客服第 203 批；--track missive，自己一個資料庫）。班底的名字都是原創（PM 11/04）。
    三種設定的 identity 開關都關著（Config.identity.enabled 預設 False，情境的副本也沒有 .local 的金鑰）：沒登入的人、登入的岑望舒、
    沒按略過教學的穆晴川，各打兩條 /api/identity/code/*（手機、Email 各送一次，再驗一次）；沒登入的人再帶一個偽造的 tx_code cookie 打一輪。
    base 沒有這兩條路由、head 有但關著：兩邊都是 404 {"detail": "Not Found"}。前半最後讀岑望舒的 /api/me（列出 identity 開頭的鍵：空的）。
    半舊半新：關著時不寫任何東西（不建旁檔），切在前半打完之後；後半第一件事無條件重新登入，再由沒登入（偽造單）與岑望舒各打一輪。
    這一軌走不到的：開著的路由（開著的行為由 tianxia/features/identity/tests/ 守；寄送與 Turnstile 只有假的）；
    旁檔 <db>-identity.sqlite 不會出現（段落雜湊照比）。假人：碰不到（假人沒有帳號，也不打 /api/identity/*），所以沒有假人段。"""

    PLAYERS = {"岑望舒": None}
    NEWBIE = "穆晴川"
    PHASES_FIRST = ["setup", "closed"]
    PHASES_SECOND = ["resume", "closed_again"]
    GUEST = "岑望舒"

    def _anon(self, forged: bool) -> None:
        client = self.TestClient(self.server.app)
        if forged:
            client.cookies.set("tx_code", "forged-challenge-id")
        label = "沒登入（偽造單）" if forged else "沒登入"
        for method, url, body in CODE_ROUTES:
            self.begin()
            r = client.post(url, json=body)
            emit(f"{label} {method} {url} {json.dumps(body, ensure_ascii=False)} {r.status_code}", r.json())

    def closed(self) -> None:
        self._anon(False)
        self._anon(True)
        for who in (self.GUEST, self.NEWBIE):
            for method, url, body in CODE_ROUTES:
                self.request(who, method, url, body)
        _status, me = self.request(self.GUEST, "GET", "/api/me")
        emit("identity 的鍵", sorted(k for k in me if k.startswith("identity")) if isinstance(me, dict) else me)

    def resume(self) -> None:
        self.login_all()

    def closed_again(self) -> None:
        self._anon(True)
        for method, url, body in CODE_ROUTES:
            self.request(self.GUEST, method, url, body)


# 改一個字（selftest）：驗證碼的 gate 一進來就放行，關著的季兩條路由都不再 404（送碼回「請先完成真人驗證」、驗碼回「驗證碼不對」）
register_track("missive", MissiveScenario, (("tianxia/features/identity/routes.py",), (
    "def _code_gate(shell, channel: str | None = None) -> bytes:",
    'def _code_gate(shell, channel: str | None = None) -> bytes:\n    return b"k" * 32',
)), "season21",
               covers=("identity",))
