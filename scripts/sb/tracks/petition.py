"""same_behavior 一軌一檔：petition（這一檔登記 petition）。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from sb.base import Scenario
from sb.harness import db_text, emit, register_track

# ── support（帳號與客服第 211 批：客服一，新包；第 235 批：開關那一筆起 week7、season21 開著，這一軌關著段、開著段都在記憶體裡設）──────

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
    ("POST", "/api/support/file?id=1", {"x": 1}),  # 第 215 批：截圖上傳（關著 404 先於讀內文，帶 JSON 也一樣）
    ("GET", "/api/support/file/1/1", None),  # 第 215 批：看圖
    ("POST", "/api/support/human", {"id": 1}),  # 第 216 批：找真人
    ("POST", "/api/support/sweep", {}),  # 第 216 批：自動結單
)
DESK_ROUTES = tuple(r for r in SUPPORT_ROUTES if r[1].split("?")[0] in (  # 客服才打得到的那幾條（不是客服一律 404）
    "/api/support/queue", "/api/support/ticket/1", "/api/support/answer", "/api/support/close", "/api/support/lookup", "/api/support/sweep"))
MAILBOX = "/api/support/mailbox"
QUEUE = "/api/support/queue"
SUPPORT_ENV = "TIANXIA_SUPPORT"  # 同 tianxia.core.identity_base.SUPPORT_ENV（這一檔頂層不 import tianxia）


class PetitionScenario(Scenario):
    """客服的一軌（帳號與客服第 211 批；--track petition，自己一個資料庫）。班底的名字都是原創（PM 11/04）。
    名單（第 235 批）：從頭到尾只認記憶體裡的 Config.support.staff——環境變數 TIANXIA_SUPPORT 拿掉、tianxia.content.LOCAL_DIR 指到不存在的資料夾
    （identity_base.support_file 每次現讀它），每一半最後一段結束還原；開關與名單在 setup、resume 都重新設。
    關著段（test 設定本來就關著；開關那一筆起 week7、season21 開著，setup 先在記憶體裡關掉，同第 232 批 charter）：登入的人（按過略過教學的祝無涯、
    沒按的練晚舟各一位）打十三條 /api/support/*，沒登入的人打 mailbox，再讀 /api/main（列出 support 開頭的鍵）與 /api/push：全是 404 {"detail": "Not Found"}。
    開著段（記憶體裡打開；客服是司燈，不是管理者，名單裡只有他的登入名）：訴長亭讀 /api/main（support_unread 0）、寫 account、mall、game 三張單，
    第四張 other 被擋（還沒結的滿 3 張），空的、1001 字、沒有的類別各被擋；/mine、回一句、回別人的單號 99（404）；訴長亭與祝無涯打客服那六條（404）；
    客服每一下之前先重新密碼登入、再打 queue（不是 200 情境直接丟錯：identity 關著時 staff_session_ok 看這次登入多久以前），看佇列、看第 1 張單（帶帳號卡）、
    回覆並等玩家、內部註記（then admin）。前半停在客服回了、訴長亭還沒讀的那一刻（印存檔江湖紀錄裡「客服」的則數）。
    後半第一件事無條件重新登入；再打一輪關著的（祝無涯十三條、沒登入 mailbox、/api/main），然後打開：訴長亭讀 /api/main（未讀亮著、輪到自己那一回合江湖紀錄多一則
    「客服」）、/mine 之後未讀歸零、對自己的第 1 張單找真人（沒有客服官時照實印）、上傳一小段不是圖的本體（被拒，在建資料夾之前：不會留下 -support-files/）；
    客服回覆並結第 2 張、結第 3 張、查帳號（查得到、查無）、sweep；訴長亭結單之後再寫第四張 other（這次收）；帶 Authorization: Bearer x 打十三條
    （客服那六條與看圖走 token 路，token 沒設一律 404；玩家那幾條不看 Authorization、照 cookie 走，照實印）；客服讀 /api/main（support_staff）。
    單、回覆、查帳、sweep 的時間是 shell.time.time()：harness 換掉的假時鐘蓋得到，輸出照比、不剝欄位。每一段結束另寫旁檔 <db stem>-support.sqlite 的段落雜湊（不在寫「不在」）。
    這一軌走不到的：真的存截圖、看圖（存了會多一個 -support-files/ 資料夾，_wipe_db 不清它；由包的測試守）；客服官 token（Config.support.bot_account 空的）
    與自動回覆、找真人之後客服官那一側；推播真的送出；identity 開著時的重驗；沒登入的人打其餘八條（第 212 批起關著也先 404，由 test_support_gate.py 守）；
    壞 JSON 與 ticket/abc（由 test_support_gate.py 守）；自動結單的三天（sweep 有打，答過的單沒放滿三天）；一天 5 張的上限；
    首頁 index.html（多一支 support.js、一條 support.css：facade、drape 兩軌）。假人：碰不到（假人沒有帳號，打不了 /api/support/*），所以沒有假人段。"""

    STAFF, PLAINT = "司燈", "訴長亭"
    PLAYERS = {"祝無涯": None, "秋聽松": None, STAFF: None, PLAINT: None}
    NEWBIE = "練晚舟"
    PHASES_FIRST = ["setup", "closed", "pages", "open", "half"]
    PHASES_SECOND = ["resume", "closed_again", "desk"]
    GUEST = "祝無涯"

    # ── 開關與名單 ──

    def switch_off(self) -> None:
        self.c.config.support.enabled = False
        self.c.config.support.staff = []

    def switch_on(self) -> None:
        self.c.config.support.enabled = True
        self.c.config.support.staff = [self.login_of(self.STAFF)]

    def isolate(self) -> None:
        """客服名單另外兩個來源隔掉（環境變數 TIANXIA_SUPPORT、LOCAL_DIR/support.txt：identity_base.support_file 每次現讀 LOCAL_DIR），
        名單只剩記憶體裡的 Config.support.staff。LOCAL_DIR 指到不存在的資料夾（不建）；管理者名單在 import 時就讀好了，不受影響。"""
        from tianxia import content as content_module

        if not hasattr(self, "_saved"):
            cfg = self.c.config.support
            self._saved = (os.environ.pop(SUPPORT_ENV, None), content_module.LOCAL_DIR, cfg.enabled, list(cfg.staff))
        content_module.LOCAL_DIR = self.db.with_name("no-local")

    def restore(self) -> None:
        """isolate 之前的樣子（環境變數、LOCAL_DIR、開關、名單）。"""
        from tianxia import content as content_module

        if hasattr(self, "_saved"):
            env, content_module.LOCAL_DIR, self.c.config.support.enabled, self.c.config.support.staff = self._saved
            if env is not None:
                os.environ[SUPPORT_ENV] = env
            del self._saved

    def setup(self) -> None:
        """關著段從這裡起：開關那一筆之後 week7、season21 的客服開著，這一軌要比關著，先在記憶體裡關掉（第 235 批，照第 232 批 charter 的寫法）。"""
        self.isolate()
        self.switch_off()
        super().setup()

    def side(self) -> Path:
        return self.db.with_name(f"{self.db.stem}-support.sqlite")

    def phase_end(self, name: str) -> None:
        super().phase_end(name)
        path = self.side()
        emit(f"段落 {name} 客服旁檔", hashlib.sha256(db_text(path).encode("utf-8")).hexdigest() if path.is_file() else "不在")
        if name in (self.PHASES_FIRST[-1], self.PHASES_SECOND[-1]):
            self.restore()

    # ── 小工具 ──

    def passerby(self) -> None:
        """沒登入的人打 mailbox（不放進 self.clients：login_all 會拿它去重新登入）。"""
        self.begin()
        r = self.TestClient(self.server.app).get(MAILBOX)
        emit(f"沒登入 GET {MAILBOX} {r.status_code}", r.json())

    def at_desk(self) -> None:
        """客服每一下之前：重新密碼登入（新的 session，建立時間是現在），再打 queue；不是 200 直接丟錯，不空走。"""
        self.relogin(self.STAFF)
        status, data = self.request(self.STAFF, "GET", QUEUE)
        if status != 200:
            raise RuntimeError(f"客服打不到 queue：{status} {data}")

    def journal_count(self, who: str) -> None:
        """存檔江湖紀錄裡標題「客服」的則數（不打請求，不動步數）。"""
        state = self.chars.load(who)
        emit(f"{who} 江湖紀錄「客服」則數", sum(1 for e in state.journal if e.title == "客服") if state is not None else None)

    def unread(self, who: str) -> None:
        main = self.main(who)
        emit(f"{who} 客服的鍵", {k: v for k, v in sorted(main.items()) if k.startswith("support")} if isinstance(main, dict) else None)

    def raw(self, who: str, url: str, data: bytes) -> None:
        """上傳本體（不是 JSON）。"""
        self.begin()
        r = self.clients[who].post(url, content=data)
        emit(f"{who} POST {url} <{len(data)} 位元組> {r.status_code}", r.json())

    def bearer(self, who: str, method: str, url: str, body: dict | None) -> None:
        """帶 Authorization: Bearer x（客服官 token 沒設）；cookie 照帶。"""
        self.begin()
        client, headers = self.clients[who], {"Authorization": "Bearer x"}
        r = client.post(url, json=body if body is not None else {}, headers=headers) if method == "POST" else client.get(url, headers=headers)
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            data = {"len": len(r.content), "sha": hashlib.sha256(r.content).hexdigest()}
        emit(f"{who} Bearer {method} {url} {json.dumps(body, ensure_ascii=False) if body else ''} {r.status_code}", data)

    # ── 段落 ──

    def closed(self) -> None:
        for who in (self.GUEST, self.NEWBIE):
            for method, url, body in SUPPORT_ROUTES:
                self.request(who, method, url, body)
        self.passerby()

    def pages(self) -> None:
        main = self.main(self.GUEST)
        emit("support 的鍵", sorted(k for k in main if k.startswith("support")))
        self.request(self.GUEST, "GET", "/api/push")

    def open(self) -> None:
        self.switch_on()
        self.unread(self.PLAINT)
        for category, text in (("account", "登不進去"), ("mall", "元寶沒到"), ("game", "地圖打不開")):
            self.request(self.PLAINT, "POST", "/api/support/ticket", {"category": category, "body": text})
        self.request(self.PLAINT, "POST", "/api/support/ticket", {"category": "other", "body": "還有一件事"})  # 第四張：還沒結的滿 3 張
        self.request(self.PLAINT, "POST", "/api/support/ticket", {"category": "account", "body": ""})
        self.request(self.PLAINT, "POST", "/api/support/ticket", {"category": "account", "body": "長" * 1001})
        self.request(self.PLAINT, "POST", "/api/support/ticket", {"category": "nope", "body": "沒有這一類"})
        self.request(self.PLAINT, "GET", "/api/support/mine")
        self.request(self.PLAINT, "POST", "/api/support/reply", {"id": 1, "body": "還是不行"})
        self.request(self.PLAINT, "POST", "/api/support/reply", {"id": 99, "body": "這張不是我的"})
        for who in (self.PLAINT, self.GUEST):
            for method, url, body in DESK_ROUTES:
                self.request(who, method, url, body)
        self.at_desk()
        self.request(self.STAFF, "GET", "/api/support/ticket/1")
        self.at_desk()
        self.request(self.STAFF, "POST", "/api/support/answer", {"id": 1, "body": "請重新登入一次看看", "then": "wait"})
        self.at_desk()
        self.request(self.STAFF, "POST", "/api/support/answer", {"id": 2, "body": "請管理者查帳", "then": "admin"})

    def half(self) -> None:
        """前半停在這裡：客服回了第 1 張，訴長亭還沒讀（江湖紀錄還沒寫那一則）。"""
        self.journal_count(self.PLAINT)

    def resume(self) -> None:
        self.isolate()
        self.switch_off()
        self.login_all()

    def closed_again(self) -> None:
        for method, url, body in SUPPORT_ROUTES:
            self.request(self.GUEST, method, url, body)
        self.passerby()
        self.main(self.GUEST)
        self.switch_on()

    def desk(self) -> None:
        """後半開著的那一段：玩家讀到回覆、客服結單與查帳。"""
        self.unread(self.PLAINT)
        self.journal_count(self.PLAINT)
        self.request(self.PLAINT, "GET", "/api/support/mine")
        self.unread(self.PLAINT)
        self.request(self.PLAINT, "POST", "/api/support/human", {"id": 1})
        self.raw(self.PLAINT, "/api/support/file?id=1", b"not an image")
        self.at_desk()
        self.request(self.STAFF, "POST", "/api/support/answer", {"id": 2, "body": "查過了，元寶已補上", "then": "close"})
        self.at_desk()
        self.request(self.STAFF, "POST", "/api/support/close", {"id": 3})
        self.at_desk()
        self.request(self.STAFF, "POST", "/api/support/lookup", {"id": 1, "kind": "login", "text": self.login_of(self.PLAINT)})
        self.at_desk()
        self.request(self.STAFF, "POST", "/api/support/lookup", {"id": 1, "kind": "login", "text": "nobody0000"})
        self.at_desk()
        self.request(self.STAFF, "POST", "/api/support/sweep", {})
        self.request(self.PLAINT, "POST", "/api/support/ticket", {"category": "other", "body": "還有一件事"})
        self.request(self.PLAINT, "GET", "/api/support/mine")
        for method, url, body in SUPPORT_ROUTES:
            self.bearer(self.PLAINT, method, url, body)
        self.relogin(self.STAFF)
        self.unread(self.STAFF)


# 改一個字（selftest）：還沒結的單滿 3 張那一句（只有開著段走得到：season21 open 那一段訴長亭的第四張單抓到）
register_track("petition", PetitionScenario, (("tianxia/features/support/rules.py",), ('TOO_MANY_OPEN = "已經有 {n} 張還沒結的單', 'TOO_MANY_OPEN = "已經有 {n} 張沒結的單')), "season21",
               covers=("notify", "support"))
