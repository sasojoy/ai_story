"""same_behavior 一軌一檔：world（這一檔登記 world）。"""
from __future__ import annotations

import hashlib
import json
import os
import random

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, emit, register_track

# ═══════════════════════════ world：世界層一軌（全部拆包第 25 批，dev/core-world-1） ═══════════════════════════
# 世界層掛鉤（世界一步、每週、每天；世界層的開季與換季；全服收季；開集結）：world.py、sqlite_world.py 裡直接叫包與舊模組的地方改叫核心的
# 掛鉤，world.py 收進核心本體（計畫 docs/superpowers/plans/2026-11-05-世界層掛鉤-第25批.md）。角色的名字都是原創的（PM 11/04）。


class WorldScenario(Scenario):
    """世界層一軌（全部拆包第 25 批；--track world，自己一個資料庫）。順序就是行為：每一段都把世界層這一下動到的帳（季曆、週初與每天的掛鉤跑到哪、
    軍令與懸賞、宴席、擂台名次、題壁、決戰、天下大事與江湖史的尾巴）寫出來，同一步裡誰先推誰後推，天下大事與江湖史的先後就看得出來。
    開季（setup：管理者開季、開季那一刻結算第 1 週；21 天季第一件決戰在開季那一刻自然開集結）；擺局面：宴席兩桌（三個世界時之後散、四百天之後才散）、
    擂台五個人（四個打過、一個沒打過）、題壁兩則（花錢的、預設的）；一次快轉跨過下一個週一再進四成（同一個請求裡跨好幾個季曆天與一個週一；
    快散的那一桌散席）；照時刻表開集結（管理者開第一件還沒開過的決戰：起點照戰線、屯糧、玉璽、龍頭上陣那四格）再取消；**前半停在世界一步推到一半**
    （週初與每天的掛鉤跑到這一週的中間；一連串的宴席剛擺、後半那一次快轉的每一個世界時散一桌；季上記下一場待開的仗；擂台還沒排名次；題壁在）。
    後半：接手那一下同步處理待開的仗；再一次快轉跨過下一個週一再進四成（週初與每天的掛鉤；那一連串的宴席一步散一桌）；大勢門檻開集結（管理者觸發標了開戰的門檻）
    再取消；假人（BotRunner 兩個、整季機器人眼前的選單）；管理者立刻收季（擂台前三名、榜單、四勝利）；開下一季（題壁照帶、玉璽、神器、開季結算）；
    新的一季再擺擂台與兩桌宴席，一次快轉從開季推到季末自然收季（同一個請求裡跨過每一個週一與每一個季曆天；同一步裡先散席、再收季、再排擂台）；
    再開下一季。
    沒有時刻表、沒有門檻開戰的內容（測試內容）同一串 API 照打，寫「沒有」。"""

    G1, G2, H1, H2, LONE = "穆遠舟", "賀青崖", "邵寒汀", "童晚照", "柯半山"
    PLAYERS = {G1: "guan", G2: "guan", H1: "huang", H2: "huang", LONE: None}
    BOT_SEATS = ["世甲", "世乙"]
    PHASES_FIRST = ["setup", "seat", "stage", "days", "muster_table", "half"]
    PHASES_SECOND = ["resume", "weeks", "muster_trend", "bots", "close_now", "next_one", "close_due", "next_two"]

    # ── 小工具 ──

    def hub(self) -> str:
        return self.c.scenario.start_location

    def point(self) -> dict:
        from tianxia import calendar

        s = self.world.get_season()
        at = calendar.point(s.time, self.c, s)
        return {"time": round(s.time, 3), "week": at.week, "weekday": at.weekday, "hour": at.hour, "cal_day": at.cal_day}

    @staticmethod
    def _digest_of(items) -> str:
        return hashlib.sha256(json.dumps([i.model_dump(mode="json") for i in items], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]

    def season_view(self, tag: str) -> None:
        """世界層這一下動到的帳：季曆與掛鉤跑到哪、軍令與懸賞（雜湊）、宴席、擂台、題壁、決戰、時刻表、天下大事與江湖史的尾巴。"""
        w = self.world.get_season()
        b = self.world.get_battle()
        emit(f"世界 {tag}", {
            "season": self.world.get_season_number(), "phase": self.world.season_phase(), "at": self.point(),
            "hooked_week": w.hooked_week, "hooked_day": w.hooked_day, "ended": w.ended, "ending": w.ending_id,
            "timeline": list(w.timeline), "waiting": list(w.showdowns_waiting), "opened": dict(w.showdowns_opened),
            "pending": w.pending_battle, "fired": sorted(w.fired_thresholds),
            "orders": [len(w.orders), self._digest_of(w.orders)], "bounties": [len(w.bounties), self._digest_of(w.bounties)],
            "seats": {k: list(v) for k, v in sorted(w.seats.items())},
            "feasts": [[f.id, f.settled, f.best] for f in w.feasts],
            "arena": [[e.name, e.rank, e.place, e.bouts] for e in sorted(w.arena.values(), key=lambda e: (e.rank, e.name))],
            "arena_closed": w.arena_closed,
            "inscriptions": [[i.id, i.preset, i.text] for i in w.inscriptions], "inscription_seq": w.inscription_seq,
            "battle": None if b is None else [b.battle_id, b.phase, hashlib.sha256(b.model_dump_json().encode("utf-8")).hexdigest()[:16]],
            "rumors": [r.text for r in w.rumors][-8:], "chronicle": [r.text for r in w.chronicle][-8:]})

    def me(self, who: str, tag: str) -> None:
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {"loc": p.location, "faction": p.faction, "stamina": p.stamina, "silver": p.stats.get("silver"),
                              "journal": [[e.title, e.tag, list(e.lines)[:4]] for e in state.journal[:4]]})

    def forward(self, hours: int, tag: str) -> None:
        """管理者快轉 hours 個世界時（Game.advance：同一個請求裡一步一步推，跨過的季曆天、週一都在這一下）。"""
        emit(f"快轉 {tag}", {"hours": hours, "before": self.point()})
        self.do(ADMIN, "fast_forward", {"hours": hours})
        self.season_view(f"快轉之後 {tag}")

    def hours_to(self, target: float) -> int:
        import math

        return max(1, math.ceil((target - self.world.get_season().time) / 3600))

    def stage_feasts(self, tag: str, ends: list[tuple[float, bool]]) -> None:
        """擺宴席（設宴是宴客包的事；這裡只要散席：ends 是 [(距現在幾個世界秒散, 有沒有人敬酒)]）。主人是內容的第一個對話人物。"""
        from tianxia.state import Feast, Toast

        host = sorted(self.c.characters)[0] if self.c.characters else "nobody"
        names = [self.G1, self.H1, self.LONE]

        def fn(s) -> None:
            for span, toasted in ends:
                s.feast_seq += 1
                toasts = [Toast(name=n, text=f"敬{n}一杯，願江湖太平{i}。", score=60 + 7 * i, at=s.time + i) for i, n in enumerate(names)] if toasted else []
                s.feasts.append(Feast(id=s.feast_seq, host=host, place=self.hub(), start=s.time, end=s.time + span, toasts=toasts))

        self.world.mutate_season(fn)
        emit(f"擺宴席 {tag}", {"host": host, "ends": ends})

    def stage_arena(self, tag: str) -> None:
        """擺擂台（報名、挑擂是單挑包的事；這裡只要收季那一刻排前三名）：四個打過的、一個沒打過的。"""
        from tianxia.characters import name_key
        from tianxia.state import ArenaEntry

        rows = [(self.G1, 1, 5, 1), (self.H1, 2, 3, 2), (self.G2, 3, 2, 2), (self.H2, 4, 1, 3), (self.LONE, 5, 0, 0)]

        def fn(s) -> None:
            s.arena = {}
            s.arena_closed = False
            for name, rank, wins, losses in rows:
                s.arena[name_key(name)] = ArenaEntry(name=name, power=100.0 + wins, hp_cap=120.0, rank=rank, wins=wins, losses=losses,
                                                     joined=float(rank))

        self.world.mutate_season(fn)
        emit(f"擺擂台 {tag}", [list(r) for r in rows])

    def stage_inscriptions(self) -> None:
        """題壁兩則（走一趟的路牌；花錢的換季照帶、預設的一季一清）。"""
        from tianxia.state import Inscription

        def fn(s) -> None:
            s.inscription_seq += 1
            s.inscriptions.append(Inscription(id=s.inscription_seq, place=self.hub(), text="路遠莫愁前無知己", author=self.G1, preset=False, time=s.time))
            s.inscription_seq += 1
            s.inscriptions.append(Inscription(id=s.inscription_seq, place=self.hub(), text="此路通往前方", author="", preset=True, time=s.time))

        self.world.mutate_season(fn)
        emit("擺題壁", None)

    def showdowns(self) -> list[str]:
        from tianxia import timetable

        return [e.id for e in timetable.events(self.world.get_season(), self.c) if e.kind == "showdown"]

    def cancel(self, tag: str) -> None:
        self.do(ADMIN, "cancel_battle")
        self.season_view(f"取消之後 {tag}")

    # ── 前半 ──

    def setup(self) -> None:
        super().setup()
        self.season_view("開季之後")

    def seat(self) -> None:
        for who, side in self.PLAYERS.items():
            self.place(who, self.hub(), side)
            self.edit(who, lambda p: p.stats.update({"silver": 300}))
        for who in self.PLAYERS:
            self.main(who)
        self.season_view("坐定")

    def into_next_week(self, weeks: int) -> float:
        """從現在往後跨過 weeks 個週一、再進那一週的四成（季曆的週照這一季蓋的章；7 天的季一週不到兩個季曆天，21 天季一週七天）。"""
        from tianxia import calendar

        s = self.world.get_season()
        week = calendar.point(s.time, self.c, s).week
        start, after = calendar.week_start(week + weeks, self.c, s), calendar.week_start(week + weeks + 1, self.c, s)
        return start + 0.4 * (after - start)

    def stage(self) -> None:
        """宴席兩桌（一桌散在下一個週一 00:00〔同一步裡週初的掛鉤、月旦評、人物行事也寫〕、一桌四百天之後才散〔兩次收季都還沒散〕；第三桌前半最後才擺）、
        擂台、題壁。"""
        from tianxia import calendar

        s = self.world.get_season()
        monday = calendar.week_start(calendar.point(s.time, self.c, s).week + 1, self.c, s)
        self.stage_feasts("前半", [(max(3600.0, monday - 1.0 - s.time), True), (400 * 86400.0, True)])
        self.stage_arena("前半")
        self.stage_inscriptions()
        self.season_view("擺好")

    def days(self) -> None:
        """一次快轉跨過下一個週一、再進那一週的四成：同一個請求裡跨過好幾個季曆天（21 天季每天 00:00 的掛鉤跑好幾次）與一個週一；快散的那一桌散席。"""
        self.forward(self.hours_to(self.into_next_week(1)), "跨天")
        self.main(self.G1)
        self.me(self.G1, "跨天之後")

    def muster_table(self) -> None:
        """照時刻表開集結（管理者開第一件還沒開過的決戰：world.open_showdown → _open_claimed，起點照戰線、屯糧、玉璽、龍頭上陣），看一眼再取消。
        21 天季開季那一刻第一件就自然開了集結（settle_season_start → 等著開 → start_pending_battle → open_waiting_showdown）：先看一眼、取消，再開下一件。"""
        ids = self.showdowns()
        emit("時刻表的決戰", ids)
        if self.world.get_battle() is not None and self.world.get_battle().phase != "ended":
            self.season_view("自然開的集結")
            self.cancel("自然開的")
        w = self.world.get_season()
        left = [i for i in ids if i not in w.showdowns_opened and i not in w.timeline]
        if not left:
            return
        # 兩軍屯的糧，屯糧這一下打開（三種設定都關著：關著的話屯糧那一格什麼都不寫，跟起點、龍頭上陣對調看不出來）
        self.world.mutate_season(lambda s: setattr(s, "supply", {"guan": 30, "huang": 12}))
        stock = self.c.config.stockpile
        before, stock.enabled = stock.enabled, True
        emit("擺屯糧", {"guan": 30, "huang": 12, "enabled_before": before})
        try:
            self.do(ADMIN, "start_showdown", {"id": left[0]})
        finally:
            stock.enabled = before
        self.season_view("時刻表開集結")
        self.main(self.H1)
        self.cancel("時刻表")

    def half(self) -> None:
        """前半停在世界一步推到一半：週初與每天的掛鉤跑到這一週的中間；擺一連串的宴席（後半那一次快轉一步散一桌）；季上記下一場待開的仗
        （背景推進跨過開戰門檻那樣：base 記下、head 下一次同步開——第一季規則的季照 season_one_off 不開，照樣寫出來）。"""
        s = self.world.get_season()
        # 一連串的宴席，後半那一次快轉的每一個世界時散一桌（單數有人敬酒、雙數冷清）：世界一步裡人物行事、盤算、月旦評寫傳聞的那幾步，同一步都有一桌
        # 散席，誰先誰後寫進天下大事的先後（宴客包那一格跟它前後的格對調看得出來）
        span = self.hours_to(self.into_next_week(1)) + 2
        self.stage_feasts("前半最後（一連串）", [(k * 3600.0 - 1.0, k % 2 == 1) for k in range(1, span + 1)])
        battle = next(iter(sorted({th.starts_battle for th in self.c.scenario.thresholds if th.starts_battle})), None) or next(iter(sorted(self.c.battles)), None)
        emit("記下待開的那一場", battle)
        if battle is not None:
            self.world.mutate_season(lambda s: setattr(s, "pending_battle", battle))
        for who in self.PLAYERS:
            self.me(who, "前半停在這裡")
        self.season_view("前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()
        for who in self.PLAYERS:
            self.main(who)
        self.season_view("接手")

    def weeks(self) -> None:
        """再一次快轉跨過下一個週一、再進那一週的四成（7 天的季與 21 天季都只有三週：前半進第 2 週、這裡進第 3 週，季末留給自然收季那一段
        一次推完）：週初的掛鉤（席次、軍令、懸賞、心意歸零）與每天的掛鉤在同一個請求裡跑；那一連串的宴席一步散一桌。前半記下的那一場仗在接手那一下同步
        （start_pending_battle）就處理了，這裡先收掉還開著的。"""
        if self.world.get_battle() is not None and self.world.get_battle().phase != "ended":
            self.cancel("接手開的")
        self.forward(self.hours_to(self.into_next_week(1)), "跨週")
        for who in (self.G1, self.H1, self.LONE):
            self.main(who)
            self.me(who, "跨週之後")

    def muster_trend(self) -> None:
        """大勢門檻開集結：管理者觸發標了開戰的門檻（_fire → _open_battle；第一季規則的季不開 beta 那一場，照樣寫出來），開了就取消。
        背景推進那一條（記下待開、下一次同步開）在切點那一下走過。沒有標開戰的門檻就什麼都不按。"""
        marked = sorted(th.id for th in self.c.scenario.thresholds if th.starts_battle)
        emit("標了開戰的門檻", marked)
        for fid in marked:
            self.do(ADMIN, "fire", {"id": fid})
            self.season_view(f"觸發 {fid}")
            self.cancel(f"觸發 {fid}")

    def bots(self) -> None:
        """假人：BotRunner 兩個（官軍，站在開局的地方、體力滿）若干輪（每一輪同步都推世界一步）；整季機器人眼前的選單。"""
        from collections import Counter

        from tianxia import bot, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        sides = [f.id for f in self.c.scenario.factions]
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=81 + i, faction="guan" if "guan" in sides else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, self.hub(), None
            p.visited.add(p.location)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.stats["silver"] = 300
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(29), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {81 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_WORLD_TICKS", "8"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"假人 {name}", {"loc": p.location, "stamina": p.stamina, "journal": [[e.title, list(e.lines)[:3]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.season_view("假人之後")
        self.begin()
        solo = Game.new(self.c, "世丙", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        p = solo.state.player
        p.faction, p.location, p.journey = "guan" if "guan" in sides else None, self.hub(), None
        p.visited.add(p.location)
        p.tutorial_step = len(self.c.tutorial.steps)
        p.stamina = float(self.c.config.stamina_max)
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單", [o.id for o in opts])
        emit("整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))

    def close_now(self) -> None:
        """管理者立刻收季（world.end_season：結局、痕跡、四勝利、擂台前三名、榜單；收兵）：第三桌宴席還沒散。"""
        self.do(ADMIN, "end_season")
        self.season_view("立刻收季之後")
        for who in (self.G1, self.H1, self.LONE):
            self.main(who)
            self.me(who, "收季之後")

    def next_one(self) -> None:
        """開下一季（sqlite_world.next_season：玉璽、首創、題壁照帶、神器、天命、藏碎片、挪開半夜；開季那一刻結算）。"""
        self.do(ADMIN, "next_season")
        self.season_view("開下一季之後")
        for who in (self.G1, self.H2):
            self.main(who)
            self.me(who, "換季之後")

    def close_due(self) -> None:
        """新的一季：擺擂台與兩桌宴席（一桌在季末之前散、一桌季末還沒散），一次快轉推到季末自然收季（同一步裡先散席、再收季、再排擂台）。"""
        from tianxia import world as world_module

        s = self.world.get_season()
        end = world_module.season_end_time(s, self.c)
        self.stage_arena("新的一季")
        self.stage_feasts("新的一季", [(max(1.0, end - s.time), True), (end - s.time + 86400.0, True)])  # 第一桌剛好在收季那一步散
        self.forward(self.hours_to(end) + 2, "推到季末")
        for who in (self.G1, self.H1, self.LONE):
            self.main(who)
            self.me(who, "自然收季之後")

    def next_two(self) -> None:
        self.do(ADMIN, "next_season")
        self.season_view("再開下一季之後")
        self.main(self.G1)
        self.me(self.G1, "再換季之後")


# 改一個字（selftest）：集結號角那一句（world._open_battle：時刻表與大勢門檻兩條開集結的路都寫它；world.py 收進核心本體不搬家）
register_track("world", WorldScenario, (("tianxia/world.py",), ("的集結號角已經吹響！", "的集結號角已經吹響。")), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "hire", "legacy", "looks", "mall", "military",
                       "outlets", "peers", "seal", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story", "tavern",
                       "territory_acts", "travel", "zhuan"))
