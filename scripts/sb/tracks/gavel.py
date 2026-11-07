"""same_behavior 一軌一檔：gavel（這一檔登記 gavel）。"""
from __future__ import annotations

from sb.harness import ADMIN, CLOCK, emit, register_track
from sb.tracks.switchboard import SwitchboardScenario

# ═══════════════════════════ 管理者一軌（第二輪第 90 批：管理者開包）═══════════════════════════


class GavelScenario(SwitchboardScenario):
    """管理者的季與時刻表工具（第二輪第 90 批；--track gavel，自己一個資料庫；班底沿用 switchboard 那一批原創的名字）。switchboard 只走到成功的那一條與壞值，這一軌專打每一句拒絕與
    switchboard 走不到的成功路；每一下記回話與畫面的雜湊（同 switchboard 的 probe），季的時刻表欄位（facts）與管理頁（admin_page）整份記。

    前半：setup 籌備中建人（test 開局就開季）；gates 沒登入、玩家打每一條管理者路由（/admin 跟首頁同一張網頁、/api/admin* 401／403、reset_password 玩家回「只有管理者」）；before_open 開季之前按季的工具；
    opened 開季、再按開季與開下一季、查人（查無此人、真的人）；wrong_times 排時間：不能排的、不存在的、過去的、排過下一項、排到上一項前面、版本還不知道（week7；season21 那一件開季就結算了）、
    對齊整點避開同一刻的大事、排過季曆最後一刻、開打時排隊中的改時間就拿出隊伍（再取消那一場）；half 寫到一半：鎖定與後到名單擺好、季暫停、再按暫停回一句——舊程式停在這裡。
    後半是重開的伺服器：resume 重新登入；still_paused 接手舊程式暫停的季，每一個工具回「先按繼續」，管理頁照看；locks_off 繼續、再按回一句、清鎖定成功那一條、再清、不存在的；
    fires 觸發：選單上的照常發生、再按「已經發生過」（第一季規則的季選單是空的，只有 test 走到發生）；trends 合成的線、不存在的、推 0、定到現在的值、定過上下限；
    verdicts 定結果每一句：不存在的、季末、版本還不知道、不認得的結果、成功、已經結算、決戰正在打，天命之爭（這一季立刻蓋章）連天命一起定；bots 假人若干輪；
    jumps 一路跳到季末：開了集結的再跳（決戰還沒收場）、再排（已經開打）、取消了接著跳；season 再收回一句、休季按暫停與繼續、開下一季、再按開季與開下一季。

    這一軌走不到的：「時刻表上沒有下一件大事了」（跳到季末就收季，先回賽季沒有在進行）；神器用完那一句（test_divine_rotation）；test 設定沒有時刻表，排時間、清鎖定、定結果、跳下一件都回「沒有時刻表」；
    真的收季那一下在 week7、season21 是跳到季末收的（立刻收季的成功路在 switchboard、battle）；/api/admin/accounts、reset_password 管理者那一邊在 switchboard 的 accounts 段。"""

    PHASES_FIRST = ["setup", "gates", "before_open", "opened", "wrong_times", "half"]
    PHASES_SECOND = ["resume", "still_paused", "locks_off", "fires", "trends", "verdicts", "bots", "jumps", "season"]

    # ── 小工具 ──

    def tool(self, op: str, body: dict | None = None) -> None:
        self.probe(ADMIN, f"/api/do/{op}", body, keep=True)

    def page(self) -> dict:
        self.begin()
        return self.clients[ADMIN].get("/api/admin").json()

    def facts(self, tag: str) -> None:
        """這一季時刻表那幾個欄位此刻的樣子（工具寫進去的東西照實記）。"""
        s = self.world.get_season()
        emit(f"季 {tag}", {
            "phase": self.world.season_phase(), "paused": self.world.paused_at(), "time": s.time, "ended": s.ended, "schedule": dict(sorted(s.schedule.items())),
            "timeline": sorted(s.timeline), "locks": {k: v.name for k, v in sorted(s.locks.items())},
            "losers": {k: [x.name for x in v] for k, v in sorted(s.lock_losers.items())}, "waiting": list(s.showdowns_waiting),
            "opened": dict(sorted(s.showdowns_opened.items())), "fired": sorted(s.fired_thresholds), "mandate": s.mandate,
        })

    def movable(self) -> list:
        """管理者排得了時間的大事（三場決戰與季末，照時刻表的順序）；測試內容沒有時刻表是空的。"""
        from tianxia import rules, timetable

        s = self.world.get_season()
        return timetable.schedulable(self.c, s) if rules.season_one(self.c, s) else []

    def admin_state(self):
        """管理者的存檔接上此刻的共用賽季（timetable.when、_pending 照它算；存檔裡的 world 不是真的那一份）。"""
        state = self.chars.load(ADMIN)
        state.world = self.world.get_season()
        return state

    # ── 前半 ──

    def gates(self) -> None:
        """不是管理者打每一條管理者路由：/admin 是同一張網頁（資料都在 /api/admin* 那幾條）；/api/admin* 沒登入、玩家都進不去（reset_password 回一句、不是 403）。"""
        for who in (None, self.MO):
            client = self.clients[who] if who else self.TestClient(self.server.app)
            self.begin()
            root, page = client.get("/"), client.get("/admin")
            emit(f"{who or '沒登入'} GET /admin", [page.status_code, page.headers.get("content-type"), page.headers.get("cache-control"), page.text == root.text])
            self.begin()
            r = client.get("/api/admin")
            emit(f"{who or '沒登入'} GET /api/admin {r.status_code}", r.json())
            for path, body in (("/api/admin/player", {"name": self.WEN}), ("/api/admin/accounts", {"q": self.WEN}), ("/api/admin/reset_password", {"target": self.WEN, "temp": "temp-pass-1"})):
                self.probe(who, path, body)

    def before_open(self) -> None:
        """開季之前（test 開局就開季，那一邊是進行中）按季的工具：收季、暫停只在沒開季時按（test 不按，不然後面都走不到）；其餘照階段回一句。"""
        phase = self.world.season_phase()
        emit("開季之前", phase)
        if phase != "running":
            self.tool("end_season")
            self.tool("pause_clock")
        self.tool("next_season")
        self.tool("resume_clock")
        for op, body in (("fire", {"id": "x"}), ("push_trend", {"id": "x", "amount": 1}), ("set_trend", {"id": "x", "value": 1}), ("schedule", {"id": "x", "at": CLOCK[0] + 3600.0}),
                         ("jump_next", None), ("resolve_event", {"id": "x", "key": "y"}), ("clear_lock", {"id": "x"})):
            self.tool(op, body)

    def opened(self) -> None:
        """開季（同 switchboard：過教學、兩軍擺好）；再按一次開季、按開下一季，都只回一句。"""
        super().opened()
        self.tool("open_season")
        self.tool("next_season")
        self.probe(ADMIN, "/api/admin/player", {"name": "沒有這個人"}, keep=True)
        self.probe(ADMIN, "/api/admin/player", {"name": self.WEN}, keep=True)
        self.facts("開季")

    def wrong_times(self) -> None:
        """排時間的每一句（測試內容每一下都回「沒有時刻表」）：不能排的那一件、不存在的、過去的、排過下一項、排到上一項前面、版本還不知道（前一項先挪到它前面，順序那一關才過得去）、
        對齊整點避開同一刻的大事、排過季曆最後一刻（照現實的日期寫）；第一項開打時第二項在排隊，改時間就拿出隊伍。"""
        from tianxia import calendar, timetable

        page = self.page()
        rows = page.get("timetable") or []
        items = self.movable()
        emit("排得了的", [[e.id, e.kind, e.version_from, next((r["schedulable"] for r in rows if r["id"] == e.id), None)] for e in items])
        items = [e for e in items if next((r["schedulable"] for r in rows if r["id"] == e.id), False)]  # 頁面上寫得了時間的（season21 的第一場開季就開過了，不算）
        fixed = next((r["id"] for r in rows if not r["schedulable"]), "沒有這一件")
        first = items[0].id if items else "沒有這一件"
        self.tool("schedule", {"id": fixed, "at": CLOCK[0] + 7200.0})
        self.tool("schedule", {"id": "沒有這一件", "at": CLOCK[0] + 7200.0})
        self.tool("schedule", {"id": first, "at": CLOCK[0] - 7200.0})
        if not items:
            return
        state = self.admin_state()
        world = state.world
        hour = calendar.cal_hour_seconds(self.c, world)
        when = {e.id: timetable.when(state, self.c, e) for e in items}
        at = {r["id"]: r["at_real"] for r in rows if r["schedulable"]}

        def real(world_time: float) -> float:  # 世界秒對到的現實時間（基準在排任何東西之前抓好，同 timetable_choices 的換算）
            return at[items[0].id] + (world_time - when[items[0].id]) / self.c.config.time_scale

        self.tool("schedule", {"id": items[0].id, "at": at[items[1].id] + 7200.0})  # 排過下一項
        self.tool("schedule", {"id": items[1].id, "at": real(when[items[0].id] - 2 * hour)})  # 排到上一項前面
        versioned = next((e for e in items if e.version_from), None)
        source = timetable.find(self.c, versioned.version_from) if versioned else None
        emit("要等版本的", source and [versioned.id, source.id, source.id in world.timeline])
        if source is not None and source.id not in world.timeline:
            before = timetable.when(state, self.c, source)
            place = items.index(versioned)
            if place:
                self.tool("schedule", {"id": items[place - 1].id, "at": real(before - 3 * hour)})
            self.tool("schedule", {"id": versioned.id, "at": real(before - hour)})
            if place:
                self.tool("schedule", {"id": items[place - 1].id, "at": at[items[place - 1].id]})  # 放回去
        state = self.admin_state()
        regular = [e for e in timetable._pending(state, self.c) if e.kind not in timetable.NOT_BY_SEASON_HOUR  # noqa: SLF001
                   and world.time < timetable.when(state, self.c, e) < timetable.when(state, self.c, items[1]) - 2 * hour]
        emit("第二項之前的一般大事", [[e.id, timetable.when(state, self.c, e)] for e in regular])
        if regular:  # 排到一件一般大事同一刻：對齊整點、往後挪開
            self.tool("schedule", {"id": items[0].id, "at": real(timetable.when(state, self.c, regular[-1]) - hour / 2)})
        finale = items[-1]
        self.tool("schedule", {"id": finale.id, "at": at[finale.id] + 86400.0 * 60})  # 排過季曆最後一刻
        self.tool("schedule", {"id": finale.id, "at": at[finale.id]})  # 放回去（後面跳到季末才跳得完）
        self.facts("排過")
        self.tool("start_showdown", {"id": items[0].id})
        queued = items[1].id

        def queue(s) -> None:
            if queued not in s.showdowns_waiting:
                s.showdowns_waiting.append(queued)

        self.world.mutate_season(queue)
        self.facts("排隊")
        self.tool("schedule", {"id": queued, "at": at[queued] + 60.0})
        self.facts("拿出隊伍")
        self.tool("cancel_battle")

    def half(self) -> None:
        """前半停在管理者寫到一半：有人鎖定一件大事（還有後到的名單）、排過時間、季暫停著，再按一次暫停回一句；接手的程式要接得起來。"""
        from tianxia.state import Lock

        items = self.movable()
        if items:
            event = items[0].id

            def lock(s) -> None:
                s.locks[event] = Lock(side="guan", name=self.MO, time=s.time)
                s.lock_losers[event] = [Lock(side="huang", name=self.WEN, time=s.time)]

            self.world.mutate_season(lock)
        self.do(ADMIN, "pause_clock")
        self.tool("pause_clock")
        self.facts("暫停")
        self.admin_page("暫停")

    # ── 後半 ──

    def still_paused(self) -> None:
        """接手舊程式暫停的季：收季、觸發、推動、定戰況、排時間、跳下一件、定結果、清鎖定、快轉都回「先按繼續」那一類；管理頁照看。"""
        items = self.movable()
        first = items[0].id if items else "沒有這一件"
        trend = next((t["id"] for t in self.page().get("trends") or []), "")
        for op, body in (("end_season", None), ("fire", {"id": "x"}), ("push_trend", {"id": trend, "amount": 1}), ("set_trend", {"id": trend, "value": 1}),
                         ("schedule", {"id": first, "at": CLOCK[0] + 7200.0}), ("jump_next", None), ("resolve_event", {"id": first, "key": "y"}), ("clear_lock", {"id": first}),
                         ("fast_forward", {"hours": 1})):
            self.tool(op, body)
        self.admin_page("暫停中")

    def locks_off(self) -> None:
        """繼續（停的這一段不算進賽季），再按一次回一句；清鎖定走成功那一條（鎖與後到名單一起清），再清一次回「沒有人鎖定」，不存在的回一句。"""
        self.do(ADMIN, "resume_clock")
        self.tool("resume_clock")
        items = self.movable()
        first = items[0].id if items else "沒有這一件"
        self.facts("繼續")
        self.tool("clear_lock", {"id": first})
        self.tool("clear_lock", {"id": first})
        self.tool("clear_lock", {"id": "沒有這一件"})
        self.facts("清過鎖定")
        self.admin_page("清過鎖定")

    def fires(self) -> None:
        """觸發大事：選單上第一件不開戰、不收季的照常發生，再按一次「已經發生過」，不存在的回一句。第一季規則的季選單是空的（三下都是「沒有這件大事」，引擎也不認選單外的）；發生的那一條只有 test 走得到。"""
        menu = {x["id"] for x in self.page().get("events") or []}
        emit("觸發大事的選單", sorted(menu))
        pick = next((x.id for x in [*self.c.scenario.world_events, *self.c.scenario.thresholds] if x.id in menu and not x.starts_battle and not x.ends_season), "沒有這件")
        emit("按哪一件", pick)
        self.tool("fire", {"id": pick})
        self.tool("fire", {"id": pick})
        self.tool("fire", {"id": "沒有這件"})
        self.facts("觸發過")

    def trends(self) -> None:
        """推動大勢與定戰況：合成的線兩邊都拒絕、不存在的回一句、推 0、定到現在的值（紋絲不動）、定過上下限（夾在 0～100），最後放回 50。"""
        from tianxia import rules

        s = self.world.get_season()
        derived = [t.id for t in self.c.scenario.trends if rules.trend_shown(self.c, s, t.id) and not rules.pushable(self.c, s, t.id)]
        pushable = next((t.id for t in self.c.scenario.trends if rules.pushable(self.c, s, t.id)), "")
        emit("大勢線", [derived, pushable])
        for trend in derived:
            self.tool("push_trend", {"id": trend, "amount": 3})
            self.tool("set_trend", {"id": trend, "value": 30})
        self.tool("push_trend", {"id": "沒有這條", "amount": 3})
        self.tool("set_trend", {"id": "沒有這條", "value": 30})
        self.tool("push_trend", {"id": pushable, "amount": 0})
        self.tool("set_trend", {"id": pushable, "value": rules.world_trend_value(self.world.get_season(), self.c, pushable)})
        self.tool("set_trend", {"id": pushable, "value": 150})
        self.tool("set_trend", {"id": pushable, "value": -20})
        self.tool("set_trend", {"id": pushable, "value": 50})
        self.facts("推過")

    def verdicts(self) -> None:
        """定結果的每一句：不存在的、季末、不認得的結果、版本還不知道、成功一件、已經結算、決戰正在打；天命之爭（這一季立刻蓋章）定結果連天命一起定。"""
        from tianxia import timetable
        from tianxia.core import seal_base

        page = self.page()
        results = [x["value"].split("|") for x in page.get("results") or []]
        emit("定得了的結果", results)
        self.tool("resolve_event", {"id": "沒有這件", "key": "y"})
        if not results:
            return
        s = self.world.get_season()
        events = timetable.events(s, self.c)
        finale = next((e.id for e in events if e.kind == "finale"), None)
        if finale:
            self.tool("resolve_event", {"id": finale, "key": "y"})
        waiting = next((e.id for e in events if e.version_from and e.version_from not in s.timeline), None)
        emit("還不知道版本的", waiting)
        if waiting:
            self.tool("resolve_event", {"id": waiting, "key": "y"})
        event, key = results[0]
        self.tool("resolve_event", {"id": event, "key": "不是這個結果"})
        self.tool("resolve_event", {"id": event, "key": key})
        self.tool("resolve_event", {"id": event, "key": key})
        self.facts("定過結果")
        s = self.world.get_season()
        showdowns = [e.id for e in self.movable() if e.kind == "showdown" and e.id not in s.timeline and e.id not in s.showdowns_opened]
        emit("還沒打的決戰", showdowns)
        if showdowns:  # 最後一場開起來（第一場開過了、第二場看版本）：正在打的不能定結果
            self.tool("start_showdown", {"id": showdowns[-1]})
            self.tool("resolve_event", {"id": showdowns[-1], "key": "guan:險勝"})
            self.tool("cancel_battle")
        mandate = seal_base.mandate_event(self.c)
        emit("天命之爭", mandate.id if mandate else None)
        if mandate is not None:
            self.tool("seal_mandate", {"when": "now"})
            keys = [v for x in self.page().get("results") or [] if (v := x["value"].split("|"))[0] == mandate.id]
            emit("天命之爭的結果", keys)
            if keys:
                self.tool("resolve_event", {"id": mandate.id, "key": keys[0][1]})
            self.facts("定過天命")
        self.admin_page("定過結果")

    def jumps(self) -> None:
        """跳到下一件，一路跳到季末：開了集結的再跳一次（決戰還沒收場）、再排一次時間（已經開打，不能再排），取消了接著跳。"""
        for i in range(24 if self.movable() else 1):
            self.tool("jump_next")
            b = self.world.get_battle()
            emit(f"跳 {i}", [self.world.season_phase(), b and b.phase])
            if b is not None and b.phase != "ended":
                self.tool("jump_next")
                definition = self.c.battles.get(b.battle_id)
                if definition is not None and definition.timetable_event:
                    self.tool("schedule", {"id": definition.timetable_event, "at": CLOCK[0] + 7200.0})
                self.tool("cancel_battle")
            if self.world.season_phase() != "running":
                break
        self.tool("jump_next")
        self.facts("跳完")

    def season(self) -> None:
        """收季（還沒收的話）、再收回一句、休季按暫停與繼續各回一句、開下一季（這一季現世的神器寫在回話裡）、再按開季與開下一季各回一句。"""
        if self.world.season_phase() == "running":
            self.do(ADMIN, "end_season")
        self.tool("end_season")
        self.tool("pause_clock")
        self.tool("resume_clock")
        self.admin_page("休季")
        self.do(ADMIN, "next_season")
        self.tool("next_season")
        self.tool("open_season")
        self.main(self.MO)
        self.facts("下一季")
        self.admin_page("下一季")


# 改一個字（selftest）：清鎖定成功那一句（本體在 admin_clear_lock：第 90 批搬進包的檔、engine 兩處找）；只有這一軌走得到（switchboard 只走到「沒有人鎖定」）
register_track("gavel", GavelScenario, (("tianxia/features/admin/actions.py", "tianxia/engine.py"),
                                        ("已清掉{event.title}的鎖定。", "已清除{event.title}的鎖定。")), "week7")
