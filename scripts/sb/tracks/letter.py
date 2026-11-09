"""same_behavior 一軌一檔：letter（這一檔登記 letter）。"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from sb.harness import ADMIN, db_text, emit, register_track
from sb.tracks.peers import PeersScenario

# ── mail（帖友書信，Joy 2026-11-09 PR #196；開關 Config.mail.enabled 預設關；小檔 <db>-mail.sqlite）：測試流程優化第 113 批 ──────────────

MAIL_ROUTES = (
    ("GET", "/api/mail", None),
    ("GET", "/api/mail/thread?name=沈眉山", None),
    ("POST", "/api/mail/send", {"name": "沈眉山", "text": "久未通信"}),
    ("POST", "/api/mail/block", {"name": "沈眉山", "value": True}),
    ("POST", "/api/mail/report", {"id": 1}),
    ("POST", "/api/mail/nope", {}),
)


class LetterScenario(PeersScenario):
    """帖友書信的一軌（測試流程優化第 113 批；--track letter，自己一個資料庫）。借 peers 一軌的小工具（act、card_of、begin 清榜單快取）。班底的名字都是原創（PM 11/04）。
    關著段（三種設定的 Config.mail.enabled 都關著）：白芷汀打六條 /api/mail*（兩邊都是 404）、三位管理者工具（/api/do/mail_*，關著也 404），讀 /api/main 的 mail 鍵。
    換帖段（還關著）：白芷汀與沈眉山定稿名帖、互換（遞帖、卡上回帖）；顧遠帆有名帖但不換。
    開著段（記憶體裡打開開關，兩個行程都開）：沒換過帖的寄不了（兩個方向；寄給不存在的名號也是這一句，先問名帖匣）、寄給自己、空信、寄成、信匣與紅點、往來（打開記成看過）、回信、
    連寫三封之後被擋（等他回信）。前半停在白芷汀又寄了一封、沈眉山還沒看的那一刻。後半第一件事無條件重新登入：沈眉山看信匣與往來、不收白芷汀的信
    （他照樣寄成、信記成 dropped）、解開、檢舉一封與檢舉不存在的一封；管理者沒事、撤下、停寄一天（白芷汀寄不了）。每一段結束另寫小檔 <db>-mail.sqlite 的段落雜湊。
    假人：這一包沒有 bots.py（假人不寄信、照樣收信），所以沒有假人段。"""

    A, B, C = "白芷汀", "沈眉山", "顧遠帆"
    PLAYERS = {A: None, B: None, C: None}
    NEWBIE = "未識者"
    PHASES_FIRST = ["setup", "seat", "closed", "cards", "open", "half"]
    PHASES_SECOND = ["resume", "read", "guard"]

    def switch_on(self) -> None:
        self.c.config.mail.enabled = True

    def side(self) -> Path:
        return self.db.with_name(f"{self.db.stem}-mail.sqlite")

    def phase_end(self, name: str) -> None:
        super().phase_end(name)
        path = self.side()
        emit(f"段落 {name} 書信小檔", hashlib.sha256(db_text(path).encode("utf-8")).hexdigest() if path.is_file() else "不在")

    def send(self, who: str, to: str, text: str):
        return self.call(who, "POST", "/api/mail/send", {"name": to, "text": text})[1]

    def mail_of(self, who: str, tag: str) -> None:
        main = self.main(who)
        emit(f"{who} {tag}：mail 的鍵與 main.mail", [sorted(k for k in main if k.startswith("mail")), main.get("mail")] if isinstance(main, dict) else None)

    def last_letter(self) -> int:
        """最後一封收件人看得到的信（不收那段時間寄的記成 dropped，檢舉不到）。"""
        con = sqlite3.connect(f"file:{self.side()}?mode=ro", uri=True)
        try:
            row = con.execute("SELECT max(id) FROM letters WHERE dropped = 0").fetchone()
        finally:
            con.close()
        return int(row[0] or 0)

    # ── 段落 ──

    def seat(self) -> None:
        for who in self.PLAYERS:
            self.place(who, self.hub())
        for who in self.PLAYERS:
            self.main(who)

    def closed(self) -> None:
        for method, url, body in MAIL_ROUTES:
            self.request(self.A, method, url, body)
        for op, body in (("mail_remove", {"id": 1}), ("mail_keep", {"id": 1}), ("mail_mute", {"name": self.A, "days": 1})):
            self.do(ADMIN, op, body)
        self.mail_of(self.A, "關著")

    def cards(self) -> None:
        for who in self.PLAYERS:
            self.call(who, "POST", "/api/mingtie/save", {"strokes": self.STROKES, "titles": [], "motto": "見字如面"})
        self.act(self.A, self.B, "mingtie", arg="send")
        self.act(self.B, self.A, "mingtie", arg="yes")

    def open(self) -> None:
        self.switch_on()
        self.call(self.A, "GET", "/api/mail")
        self.send(self.C, self.A, "冒昧來信")  # 沒換過帖
        self.send(self.A, self.C, "冒昧回信")  # 他有名帖、我沒收著他的
        self.send(self.A, self.A, "寫給自己")
        self.send(self.A, self.B, "")
        self.send(self.A, "查無此人", "有人嗎")
        self.send(self.A, self.B, "久未通信，近來可好")
        self.mail_of(self.B, "收到一封")
        self.call(self.B, "GET", "/api/mail")
        self.call(self.B, "GET", f"/api/mail/thread?name={self.A}")
        self.mail_of(self.B, "看過之後")
        self.send(self.B, self.A, "一切都好，勿念")
        for i in range(4):  # 第四封：等他回信
            self.send(self.A, self.B, f"再寫第{i + 1}封")
        self.call(self.A, "GET", f"/api/mail/thread?name={self.B}")

    def half(self) -> None:
        """前半停在這裡：白芷汀寄給沈眉山的信還沒看（紅點亮著）。"""
        self.call(self.B, "POST", "/api/mail/send", {"name": self.A, "text": "又收到你的信"})
        self.send(self.A, self.B, "路上小心")
        self.mail_of(self.B, "前半停在這裡")

    def resume(self) -> None:
        self.switch_on()
        self.login_all()

    def read(self) -> None:
        self.mail_of(self.B, "後半")
        self.call(self.B, "GET", "/api/mail")
        self.call(self.B, "GET", f"/api/mail/thread?name={self.A}")
        self.call(self.B, "POST", "/api/mail/block", {"name": self.A, "value": True})
        self.send(self.A, self.B, "怎麼不回")  # 照樣說寄出去了
        self.mail_of(self.B, "不收之後")
        self.call(self.B, "POST", "/api/mail/block", {"name": self.A, "value": False})
        self.call(self.B, "GET", "/api/mail")

    def guard(self) -> None:
        lid = self.last_letter()
        self.call(self.B, "POST", "/api/mail/report", {"id": lid})
        self.call(self.B, "POST", "/api/mail/report", {"id": 99999})
        self.call(self.B, "GET", f"/api/mail/thread?name={self.A}")
        self.do(ADMIN, "mail_keep", {"id": lid})
        self.do(ADMIN, "mail_remove", {"id": lid})
        self.do(ADMIN, "mail_mute", {"name": self.A, "days": 1})
        self.send(self.A, self.B, "還寄得出去嗎")
        self.call(self.A, "GET", "/api/mail")


# 改一個字（selftest）：開關的那一道 gate 反過來，關著的季每條路由都不再 404、開著的季每條都 404
register_track("letter", LetterScenario, (("tianxia/features/mail/routes.py",), ("if shell.CONTENT.config.mail.enabled:", "if not shell.CONTENT.config.mail.enabled:")), "season21",
               covers=("bounties", "figure_acts", "jieyi", "mail", "peers", "socialize"))
