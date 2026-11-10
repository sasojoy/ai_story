"""same_behavior 一軌一檔：guard（這一檔登記 guard）。"""
from __future__ import annotations

from sb.harness import ADMIN, emit, register_track
from sb.tracks.peers import PeersScenario

# ── guard（親衛隊長，Joy 2026-11-09 PR #212；開關 Config.guard.enabled，week7、season21 打開，測試內容關著）：親衛隊長第四批 ──────────────


class GuardScenario(PeersScenario):
    """親衛隊長的一軌（親衛隊長第四批，Joy 2026-11-10「全部做完一起上」；--track guard，自己一個資料庫）。借 peers 一軌的小工具（card_of、edit_state、begin 清榜單快取）。班底的名字都是原創。
    關著段（記憶體裡把三種設定的開關都關掉）：等級到了照樣探索、不撞見；親衛隊長那一頁的鈕（guard:open、guard:study）回「沒有這件事」、/api/do/guard_along 也是；讀 /api/main 的 guard 鍵。
    開著段（記憶體裡打開，兩個行程都開；等模型的時限縮成 60 秒：同一個假時鐘一步一分鐘，下一步就換固定事件）：探索撞見、救下、收養（少女）、每天那一件家裡的事、攤開、挑做法、
    每天教他、帶不帶出門、改名；前半停在第二段（相熟）走到一半、眼前攤著一件還沒答的那一刻。
    後半第一件事無條件重新登入：答完那一件、三段走完、送去求學（銀兩不夠的那一處、夠的那一處）、學成回來的信、出師考驗、出師結算（叫不到模型換固定的）、跪誓投效；
    投效之後：名帖頭銜那一行（自己看與對手看玩家卡）、列傳（行狀）、狀態裡的專長與心性；收季、開下一季：照帶、心性起算、開季那一封、酒肆不再招（下一季才蓋章）。
    這一軌走不到的：真的模型（生事件、自己寫的那一句、出師結算都是固定的那一份）；截殺與決戰裡他的那一句（要兩個人在野地、要開決戰；包的 test_guard_seen.py 守）；
    假人養的那一位（假人照包的 bots.py 走，BotRunner 幾輪內走不到撞見）。"""

    LEAD, RIVAL = "沈霜序", "顧臨川"
    PLAYERS = {LEAD: None, RIVAL: None}
    NEWBIE = "遠客"
    PHASES_FIRST = ["setup", "seat", "closed", "meet", "grow", "half"]
    PHASES_SECOND = ["resume", "finish", "study", "sworn", "seen", "season"]

    def switch(self, on: bool) -> None:
        t = self.c.config.guard
        t.enabled = on
        t.wait_seconds = 60.0

    def guard_of(self, who: str, tag: str) -> None:
        main = self.main(who)
        st = main.get("status", {}) if isinstance(main, dict) else {}
        emit(f"{who} {tag}：main.guard", main.get("guard") if isinstance(main, dict) else None)
        emit(f"{who} {tag}：status 的 guard", st.get("guard") if isinstance(st, dict) else None)
        b = self.chars.load(who).player.guard
        emit(f"{who} {tag}：存檔", b.model_dump(mode="json", exclude={"log"}) if b is not None else None)

    def explore(self, who: str, times: int = 3) -> None:
        for _ in range(times):
            ids = self.ids(self.main(who))
            if "act:explore" not in ids:
                emit(f"{who} 選單上沒有探索", sorted(ids)[:20])
                return
            self.choose(who, "act:explore")
            self.settle_choices(who)
            self.edit(who, lambda p: setattr(p, "stamina", float(self.c.config.stamina_max)))
            if self.chars.load(who).player.guard is not None:
                return

    def answer(self, who: str, pick: int = 0) -> None:
        self.choose(who, "guard:open")
        self.choose(who, f"guard:pick:{pick}")

    def next_day(self, who: str) -> None:
        """換一天（家裡的事、每天教他都看季曆的天）：世界時間往後撥一天，再同步一下。"""
        def fn(s) -> None:
            s.player.guard.home_day -= 1
            s.player.guard.teach_day -= 1
            s.player.guard.phase_day -= 1
        self.edit_state(who, fn)
        self.main(who)

    # ── 段落 ──

    def seat(self) -> None:
        for who in self.PLAYERS:
            self.place(who, self.hub())
        self.edit(self.LEAD, lambda p: setattr(p.member, "level", self.c.config.guard.meet_level))
        for who in self.PLAYERS:
            self.main(who)

    def closed(self) -> None:
        self.switch(False)
        self.explore(self.LEAD, 1)
        for oid in ("guard:open", "guard:study", "guard:adopt:女"):
            self.choose(self.LEAD, oid)
        self.do(self.LEAD, "guard_along", {"on": False})
        self.guard_of(self.LEAD, "關著")

    def meet(self) -> None:
        self.switch(True)
        self.explore(self.LEAD)
        if self.chars.load(self.LEAD).player.guard is None:  # 這份內容的探索被別的事接走了：照撞見的樣子擺好
            from tianxia.state import GuardBook

            self.edit(self.LEAD, lambda p: setattr(p, "guard", GuardBook(stage="met", opening="river", place=p.location)))
        self.guard_of(self.LEAD, "撞見")
        self.choose(self.LEAD, "guard:save")
        self.choose(self.LEAD, "guard:adopt:女")
        self.guard_of(self.LEAD, "收養")

    def grow(self) -> None:
        self.main(self.LEAD)
        self.main(self.LEAD)  # 等模型的時限過了：換固定事件
        self.answer(self.LEAD, 0)
        teach = sorted(i for i in self.ids(self.main(self.LEAD)) if i.startswith("guard:teach"))
        emit("選單上的教他", teach)
        self.choose(self.LEAD, "guard:teach:read")
        self.choose(self.LEAD, "guard:teach:read")  # 一天一次
        self.do(self.LEAD, "guard_along", {"on": False})
        self.do(self.LEAD, "guard_along", {"on": True})
        self.do(self.LEAD, "guard_rename", {"name": "青禾"})
        self.do(self.LEAD, "guard_rename", {"name": "再改"})  # 只能改一次
        for i in range(3):
            self.next_day(self.LEAD)
            self.main(self.LEAD)
            self.answer(self.LEAD, i % 3)
        self.edit_state(self.LEAD, lambda s: setattr(s.player.guard, "phase", 1))
        self.guard_of(self.LEAD, "相熟")

    def half(self) -> None:
        """前半停在這裡：第二段走到一半，眼前攤著一件還沒答。"""
        self.next_day(self.LEAD)
        self.main(self.LEAD)
        self.main(self.LEAD)
        self.choose(self.LEAD, "guard:open")
        self.guard_of(self.LEAD, "前半停在這裡")

    def resume(self) -> None:
        self.switch(True)
        self.login_all()

    def finish(self) -> None:
        self.choose(self.LEAD, "guard:pick:1")
        self.edit_state(self.LEAD, lambda s: setattr(s.player.guard, "phase", 3))
        self.guard_of(self.LEAD, "三段走完")

    def study(self) -> None:
        self.edit(self.LEAD, lambda p: p.stats.__setitem__("silver", 1))
        self.choose(self.LEAD, "guard:study")
        self.choose(self.LEAD, "guard:school:gensui")  # 銀兩不夠
        self.edit(self.LEAD, lambda p: p.stats.__setitem__("silver", 2000))
        self.choose(self.LEAD, "guard:school:gensui")
        self.guard_of(self.LEAD, "送去求學")

        def back(s) -> None:
            b = s.player.guard
            b.study_until = s.world.time - 1
            b.letters = self.c.config.guard.letters
        self.edit_state(self.LEAD, back)
        self.main(self.LEAD)
        self.guard_of(self.LEAD, "學成")

    def sworn(self) -> None:
        for _ in range(3):  # 出師考驗、結算（叫不到模型換固定的）、跪誓
            self.main(self.LEAD)
            self.main(self.LEAD)
            self.answer(self.LEAD, 0)
        self.guard_of(self.LEAD, "投效")

    def seen(self) -> None:
        emit("對手看他的卡", self.card_of(self.RIVAL, self.LEAD))
        p = self.chars.load(self.LEAD).player
        emit("列傳的行狀", [a.text for a in p.annals if "收養" in a.text or "親衛隊長" in a.text])

    def season(self) -> None:
        self.do(ADMIN, "end_season")
        self.main(self.LEAD)
        self.do(ADMIN, "next_season")
        self.guard_of(self.LEAD, "下一季")
        emit("下一季的章 guard_on", getattr(self.world.get_season(), "guard_on", None))
        view = self.main(self.LEAD)
        emit("下一季的 hire:", sorted(i for i in self.ids(view) if i.startswith("hire:")) if isinstance(view, dict) else None)


# 改一個字（selftest）：投效之後名帖那一行的開關判斷反過來，開著的季寫不出那一行，season21 seen 那一段抓到
register_track("guard", GuardScenario, (("tianxia/core/guard_base.py",), ('if b is not None and b.name else ""', 'if b is not None and not b.name else ""')), "season21",
               covers=("guard", "explore", "hire", "peers", "zhuan"))
