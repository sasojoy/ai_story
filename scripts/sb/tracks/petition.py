"""same_behavior 一軌一檔：petition（這一檔登記 petition）。"""
from __future__ import annotations

from sb.base import Scenario
from sb.harness import emit, register_track

# ── support（帳號與客服第 211 批：客服一，新包、開關預設關）──────────────────────

SUPPORT_ROUTES = (
    ("POST", "/api/support/ticket", {"category": "account", "body": "登不進去"}),
    ("GET", "/api/support/mine", None),
    ("POST", "/api/support/reply", {"id": 1, "body": "還是不行"}),
    ("GET", "/api/support/queue", None),
    ("GET", "/api/support/ticket/1", None),
    ("POST", "/api/support/answer", {"id": 1, "body": "好了", "then": "wait"}),
    ("POST", "/api/support/close", {"id": 1}),
    ("POST", "/api/support/lookup", {"id": 1, "kind": "login", "text": "zhuwuya"}),  # 第 212 批：客服二（查帳號）
    ("GET", "/api/support/mailbox", None),  # 第 214 批：登入頁的客服信箱（不用登入）
)
MAILBOX = "/api/support/mailbox"


class PetitionScenario(Scenario):
    """客服的一軌（帳號與客服第 211 批；--track petition，自己一個資料庫）。班底的名字都是原創（PM 11/04）。
    三種設定的客服開關都關著（Config.support.enabled 預設 False）：登入的人（按過略過教學的祝無涯、沒按的練晚舟各一位）打九條 /api/support/*（第 212 批加查帳號那一條，第 214 批加 mailbox），
    再讀 /api/main（列出 support 開頭的鍵）與 /api/push。base 沒有這幾條路由、head 有但關著：登入的人兩邊都是 404 {"detail": "Not Found"}。
    半舊半新：客服關著時不寫任何東西，切在前半打完之後；後半第一件事無條件重新登入，再打一輪。
    沒登入的人只打一次 mailbox（第 214 批：唯一不用登入的那一條；base 沒有這條路、head 關著，兩邊都是 404 Not Found），前半、後半各一次。
    這一軌走不到的：沒登入的人打其餘八條（第 212 批起 head 關著也先 404，不打；由包的 test_support_gate.py 守）；壞 JSON 與 ticket/abc（base 回 422、
    head 關著回 404：gate 先於參數解析是要的改變，不放進軌，由 test_support_gate.py 守）；
    首頁 index.html（多一支 support.js、一條 support.css：facade、drape 兩軌照 --new 扣）；開著的路由（開著的行為由 tianxia/features/support/tests/ 守）；
    旁檔 <db>-support.sqlite 不會出現（段落雜湊照比）。假人：碰不到（假人沒有帳號，打不了 /api/support/*），所以沒有假人段。"""

    PLAYERS = {"祝無涯": None, "秋聽松": None}
    NEWBIE = "練晚舟"
    PHASES_FIRST = ["setup", "closed", "pages"]
    PHASES_SECOND = ["resume", "closed_again"]
    GUEST = "祝無涯"

    def closed(self) -> None:
        for who in (self.GUEST, self.NEWBIE):
            for method, url, body in SUPPORT_ROUTES:
                self.request(who, method, url, body)
        self.passerby()

    def passerby(self) -> None:
        """沒登入的人打 mailbox（不放進 self.clients：login_all 會拿它去重新登入）。"""
        self.begin()
        r = self.TestClient(self.server.app).get(MAILBOX)
        emit(f"沒登入 GET {MAILBOX} {r.status_code}", r.json())

    def pages(self) -> None:
        main = self.main(self.GUEST)
        emit("support 的鍵", sorted(k for k in main if k.startswith("support")))
        self.request(self.GUEST, "GET", "/api/push")

    def resume(self) -> None:
        self.login_all()

    def closed_again(self) -> None:
        for method, url, body in SUPPORT_ROUTES:
            self.request(self.GUEST, method, url, body)
        self.passerby()
        self.main(self.GUEST)


# 改一個字（selftest）：開關的那一道 gate 反過來，關著的季每條路由都不再 404
register_track("petition", PetitionScenario, (("tianxia/features/support/routes.py",), ("if not shell.CONTENT.config.support.enabled:", "if shell.CONTENT.config.support.enabled:")), "season21",
               # 第 I 波合併時補（第 107 批要每軌寫 covers；這一軌是 J 波新加的，沒量過）：/api/main 跟別軌一樣叫到每一包的掛鉤，再加客服的路由
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "hire", "legacy", "looks", "mall", "map",
                       "military", "notify", "outlets", "peers", "persona", "seal", "seclusion", "sense", "smithy", "socialize",
                       "sortie", "stamina_plays", "story", "support", "tale", "tavern", "territory_acts", "travel", "zhuan"))
