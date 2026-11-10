"""same_behavior 一軌一檔：military（這一檔登記 military）。"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, emit, register_track

# ═══════════════════════════ military：軍情一軌（全部拆包第 33 批，dev/military-1） ═══════════════════════════
# 軍情（軍令卡與應召、押糧、第 2 階行動、第 3／4 階行動、席次輪替與召見：Game 上 17 個方法與 rank_actions.py）搬進新包 tianxia/features/military/
# （計畫 docs/superpowers/plans/2026-11-05-軍情包-第1批.md）。角色的名字都是原創的（PM 11/04）。


class MilitaryScenario(Scenario):
    """軍情一軌（--track military，自己一個資料庫）。
    軍令卡：管理者重發本週軍令（natural 的發法）後各陣營看卡；再各擺一道護糧軍令（湊兩次就達成）。押糧：糧草不夠按灰鈕、有糧接下糧車（第二次按已押著一車）、
    散人與不在起點的按了被擋；**前半停在押糧走到一半**（糧車在路上、軍令還沒交）；後半快轉到抵達：官軍的人沒遇上截糧隊、黃巾的人撞上截糧隊打輸（糧車被劫）、
    官軍第二個人送到把軍令湊滿（達成、軍情）。第 2 階行動：官軍黃巾各一人，按到今天做滿變灰、體力不夠、散人按了被擋。第 3、4 階行動：照內容挑做得了的地點，
    按到這週做滿；有資格的人抄帳補缺（席次，第 4 階在任）。召見與應召：貢獻夠了同步自然發召見（**前半停在召見還沒去應**，後半走到召見地點應召、演晉升奇遇）；
    管理者替他發召見（散人、已有召見、已有資格、不存在的名號）、輪替席次（第 1 週沒有上一週、快轉到第 2 週之後輪替）、重發軍令。換季。
    假人：BotRunner 兩個（官軍，站在有戰線的地方；bot_policy 的 act: 那幾顆）；整季機器人眼前的選單。
    沒有軍令的內容（測試內容）同一串 API 照打，寫「沒有」。"""

    G_RUN, G_RUN2, H_RUN = "蕭鐵崖", "顧長庚", "雷驚瀾"
    G_R2, H_R2 = "沈孤鴻", "祁連山"
    G_R3, H_R3 = "宋斷虹", "嚴寒江"
    G_SEAT, H_SEAT = "洛雲歸", "燕無歸"
    G_CALL, H_CALL = "戚望舒", "范潛龍"
    LONE = "白無相"
    PLAYERS = {G_RUN: "guan", G_RUN2: "guan", H_RUN: "huang", G_R2: "guan", H_R2: "huang", G_R3: "guan", H_R3: "huang",
               G_SEAT: "guan", H_SEAT: "huang", G_CALL: "guan", H_CALL: "huang", LONE: None}
    BOT_SEATS = ["營甲", "營乙"]
    PHASES_FIRST = ["setup", "seat", "orders", "convoy_take", "rank2", "rank34", "summons_open", "half"]
    PHASES_SECOND = ["resume", "answer", "convoy_arrive", "admin", "bots", "season"]

    PICKS = ("slots", "hub", "act3")
    slots: dict = {}
    hub = "nobody"
    act3: dict = {}

    # ── 小工具 ──

    @contextlib.contextmanager
    def tuned(self, **values):
        """這一下把設定改成這幾個值（同一個行程裡共用 CONTENT，出來要還原）。"""
        owner = self.c.config
        before = {k: getattr(owner, k) for k in values}
        for k, v in values.items():
            setattr(owner, k, v)
        emit("這一下的設定", dict(values))
        try:
            yield
        finally:
            for k, v in before.items():
                setattr(owner, k, v)

    @contextlib.contextmanager
    def fights(self, tier: str):
        """這幾下的仗照寫好的 tier（同 Scenario.winning：威力、難度、亂數照算，只換結果）。"""
        from tianxia import team

        real = team.fight

        def fight(*args, **kwargs):
            if kwargs.get("tier") is None:
                kwargs["tier"] = tier
            return real(*args, **kwargs)

        team.fight = fight
        try:
            yield
        finally:
            team.fight = real

    def options(self, who: str) -> dict:
        return self.ids(self.main(who))

    def press(self, who: str, option_id: str, tag: str) -> None:
        """按選單上的一顆（灰著照按，被擋的那一句也要寫出來；選單上沒有也照按〔清單外〕）。"""
        have = self.options(who).get(option_id)
        emit(f"{who} {tag} 按 {option_id}", None if have is None else {"label": have.get("label"), "enabled": have.get("enabled")})
        self.choose(who, option_id)

    def menu(self, who: str, tag: str, *prefixes: str) -> dict:
        opts = self.options(who)
        emit(f"{who} {tag} 選單上", [[i, o.get("label"), o.get("enabled")] for i, o in opts.items() if i.startswith(prefixes)])
        return opts

    def me(self, who: str, tag: str) -> None:
        """存檔裡這一包碰得到的那幾格：所在、陣營、體力、貢獻與每週貢獻、階與資格、押著的糧車、手上的召見、第 2 階今天做了幾次、第 3 4 階這週做了幾次、
        捐獻、最新三則紀錄。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "loc": p.location, "journey": None if p.journey is None else p.journey.model_dump(mode="json"), "faction": p.faction,
            "stamina": p.stamina, "contrib": p.contrib, "weeks": dict(sorted(p.contrib_weeks.items())), "rank": p.rank, "qualified": p.qualified,
            "convoy": None if p.convoy is None else p.convoy.model_dump(mode="json"),
            "summons": None if p.summons is None else p.summons.model_dump(mode="json"),
            "rank2_days": dict(sorted(p.rank2_days.items())), "rank_weeks": dict(sorted(p.rank_action_weeks.items())),
            "donations": dict(sorted(p.donations.items())), "pushed": dict(sorted(p.pushed.items())),
            "journal": [[e.title, e.tag, list(e.lines)[:4]] for e in state.journal[:3]]})

    def world_view(self, tag: str) -> None:
        """全服這一包碰得到的帳：軍令、席次與帳、陣營軍情與天下大事的尾巴、戰線的值。"""
        w = self.world.get_season()
        emit(f"世界 {tag}", {
            "orders": [o.model_dump(mode="json") for o in w.orders], "seats": {k: list(v) for k, v in sorted(w.seats.items())},
            "ledger": {k: {n: dict(sorted(x.items())) for n, x in sorted(v.items())} for k, v in sorted(w.seat_ledger.items())},
            "rumors": [r.text for r in w.rumors][-5:], "chronicle": [r.text for r in w.chronicle][-3:], "hooked": getattr(w, "hooked_week", None)})

    def week_of(self) -> int:
        from tianxia import calendar

        s = self.world.get_season()
        return calendar.point(s.time, self.c, s).week

    def forward_to_week(self, week: int) -> None:
        for _ in range(40):
            if self.week_of() >= week:
                break
            self.do(ADMIN, "fast_forward", {"hours": 24})
        emit("季曆第幾週", self.week_of())

    def grain(self, who: str, n: int) -> None:
        """背包裡放 n 份糧草（慢屬性的素材，從最低階的那一種放）。"""
        mats = sorted((m for m in self.c.materials.values() if m.attribute == "慢"), key=lambda m: (m.tier, m.id))
        if mats:
            self.edit(who, lambda p: p.materials.__setitem__(mats[0].id, n))

    def hop(self, who: str) -> None:
        """走一步（選單上第一個能走的地方）；押著糧車的人，終點先改成這一步（這樣一步就抵達，不必走完一整條路）。"""
        move = next((i for i, o in self.options(who).items() if i.startswith("move:") and o.get("enabled")), None)
        emit(f"{who} 走的那一步", move)
        if move is None:
            return
        dest = move.split(":")[1]
        self.edit(who, lambda p: setattr(p.convoy, "to_loc", dest) if p.convoy is not None else None)
        self.choose(who, move)

    def spot(self, side: str | None, key: int) -> str:
        """這一陣營押糧的起點（0）、終點（1）、截糧的地點（2）；沒有這一道（測試內容）就用 hub。"""
        got = self.slots.get(side)
        return self.hub if got is None else got[1 + key]

    # ── 前半 ──

    def seat(self) -> None:
        """挑地點：每個陣營押糧的起點與終點（內容的插槽表第一條有這個陣營的戰線）、有戰線的地方（hub）、第 3 4 階行動做得了的地方。"""
        from tianxia.features.military import rank_rules as rank_actions
        from tianxia.rules import front_of

        c = self.c
        self.slots = {}
        for front, by in sorted(c.orders.slots.items()):
            for side, sl in sorted(by.items()):
                self.slots.setdefault(side, (front, sl.escort[0], sl.escort[1], sl.intercept))
        fronted = [loc for loc in sorted(c.locations) if front_of(c, loc) is not None]
        self.hub = self.slots["guan"][1] if "guan" in self.slots else (fronted[0] if fronted else sorted(c.locations)[0])
        state = self.chars.load(ADMIN)
        state.world = self.world.get_season()
        self.act3 = {}
        for side in ("guan", "huang"):
            state.player.faction = side
            for a in c.orders.rank_actions:
                if a.faction != side:
                    continue
                for loc in sorted(c.locations):
                    if rank_actions.where_ok(state, c, a, loc):
                        self.act3.setdefault(side, loc)
                        break
        emit("挑的地點", {"slots": {k: list(v) for k, v in sorted(self.slots.items())}, "hub": self.hub, "act3": self.act3,
                         "orders_on": bool(c.orders.templates), "rank2": sorted(c.orders.rank2), "rank_actions": [a.id for a in c.orders.rank_actions]})
        for who, side in self.PLAYERS.items():
            home = self.spot(side, 0) if who in (self.G_RUN, self.G_RUN2, self.H_RUN) else self.hub
            self.place(who, home, side)
            self.edit(who, lambda p: p.stats.update({"silver": 500}))
        self.world_view("開場")

    def orders(self) -> None:
        """軍令卡：管理者重發本週軍令（兩次，第二次換掉沒達成的）、各看一遍；再把各陣營的軍令換成一道護糧（湊兩次達成）。"""
        from tianxia import orders
        from tianxia.engine import Game
        from tianxia.state import Order

        self.do(ADMIN, "issue_orders")
        for who in (self.G_RUN, self.H_RUN, self.LONE):
            self.main(who)
        self.do(ADMIN, "issue_orders")
        self.world_view("重發之後")
        shell = Game.for_world(self.c, self.world)
        week = orders.period_of(shell.state, self.c)

        def put(s) -> None:
            s.orders[:] = [o for o in s.orders if not o.id.startswith("mb:")]
            for side, (front, start, end, _icp) in sorted(self.slots.items()):
                s.orders.append(Order(id=f"mb:{side}:escort", template="escort", faction=side, week=week, front=front, start=start, end=end,
                                      location=start, quota=2, text=f"（對照）{side}護糧"))

        self.world.mutate_season(put)
        for who in (self.G_RUN, self.H_RUN, self.LONE):
            self.main(who)
        self.world_view("擺護糧之後")

    def convoy_take(self) -> None:
        """押糧：顧長庚沒糧草（灰鈕）；蕭鐵崖與雷驚瀾放糧草接下糧車，蕭鐵崖再按一次（已押著一車）；散人按了被擋；接了的兩個人各走一步（前半停在路上）。"""
        self.menu(self.G_RUN2, "沒有糧草", "act:convoy")
        self.press(self.G_RUN2, "act:convoy", "沒有糧草")
        need = self.c.config.convoy_grain
        for who in (self.G_RUN, self.H_RUN):
            self.grain(who, need + 2)
            self.menu(who, "有糧草", "act:convoy")
            self.press(who, "act:convoy", "接糧車")
        self.menu(self.G_RUN, "已押著一車", "act:convoy")
        self.press(self.G_RUN, "act:convoy", "再接一車")
        self.press(self.LONE, "act:convoy", "散人")
        for who in (self.G_RUN, self.H_RUN):
            self.hop(who)
            self.me(who, "押糧走到一半")

    def rank2(self) -> None:
        """第 2 階行動：官軍黃巾各一人在有戰線的地方，按到今天做滿（灰）；再按一次被擋；體力不夠的人；階不夠的人按了被擋。"""
        for who in (self.G_R2, self.H_R2):
            self.place(who, self.hub)
            self.edit(who, lambda p: setattr(p, "rank", 2))
            self.menu(who, "第 2 階", "act:rank2")
            for k in range(max(1, int(self.c.config.rank2_daily)) + 1):
                self.press(who, "act:rank2", f"第 {k + 1} 次")
            self.me(who, "做滿之後")
        self.place(self.G_R2, None)
        self.edit(self.G_R2, lambda p: (p.rank2_days.clear(), setattr(p, "stamina", 0.0)))  # 今天的次數清掉，才輪得到「體力不夠」那一句（審查：原本被「今天做滿」擋在前面）
        self.menu(self.G_R2, "體力沒了", "act:rank2")
        self.press(self.G_R2, "act:rank2", "體力沒了")
        self.press(self.LONE, "act:rank2", "散人")

    def rank34(self) -> None:
        """第 3、4 階行動：宋斷虹、嚴寒江第 3 階在做得了的地方，每顆按到這週做滿再多按一次；洛雲歸、燕無歸有資格（貢獻帳在第 1 週），同步抄帳補缺、在任是第 4 階。"""
        for who, side in ((self.G_R3, "guan"), (self.H_R3, "huang")):
            self.place(who, self.act3.get(side, self.hub))
            self.edit(who, lambda p: setattr(p, "rank", 3))
            opts = self.menu(who, "第 3 階", "act:rank:")
            for oid in [i for i in opts if i.startswith("act:rank:")][:2]:
                for k in range(4):
                    self.press(who, oid, f"第 {k + 1} 次")
            self.me(who, "第 3 階做完")
        for who, side in ((self.G_SEAT, "guan"), (self.H_SEAT, "huang")):
            self.place(who, self.act3.get(side, self.hub))
            self.edit(who, lambda p: (setattr(p, "rank", 3), setattr(p, "qualified", True), p.contrib_weeks.update({1: 40 if p.faction == "guan" else 30})))
            self.main(who)
            self.menu(who, "有資格", "act:rank:")
            self.me(who, "抄帳補缺之後")
        self.world_view("席次之後")

    def summons_open(self) -> None:
        """召見：戚望舒貢獻夠了，同步自然發召見（前半停在還沒去應）；范潛龍留給管理者；管理者在第 1 週輪替席次（沒有上一週）。"""
        self.edit(self.G_CALL, lambda p: setattr(p, "contrib", 10 ** 6))
        self.main(self.G_CALL)
        self.me(self.G_CALL, "發了召見")
        self.do(ADMIN, "rotate_seats")

    def half(self) -> None:
        for who in self.PLAYERS:
            self.me(who, "前半停在這裡")
        self.world_view("前半停在這裡")
        Path(str(self.db) + ".military.json").write_text(json.dumps({k: getattr(self, k) for k in self.PICKS}, ensure_ascii=False), encoding="utf-8")

    # ── 後半 ──

    def resume(self) -> None:
        for k, v in json.loads(Path(str(self.db) + ".military.json").read_text(encoding="utf-8")).items():  # 前半挑的地點（後半是新的行程）
            setattr(self, k, v)
        for who in list(self.clients):  # 登入就同步：路上的糧車在這一刻抵達（雷驚瀾撞上截糧隊打輸、蕭鐵崖沒遇上），機率與仗的結果先調好
            if who == self.H_RUN:
                with self.tuned(convoy_ambush_chance=1.0), self.fights("落敗"):
                    self.relogin(who)
            elif who == self.G_RUN:
                with self.tuned(convoy_ambush_chance=0.0), self.fights("大勝"):
                    self.relogin(who)
            else:
                self.relogin(who)
        for who in self.PLAYERS:
            self.main(who)
            self.me(who, "接手")

    def answer(self) -> None:
        """應召：戚望舒走到召見的地點，按應召、把晉升奇遇演完。"""
        state = self.chars.load(self.G_CALL)
        summons = None if state is None else state.player.summons
        if summons is None:
            emit("戚望舒沒有召見", None)
            self.press(self.G_CALL, "act:summons", "沒有召見")
            return
        self.place(self.G_CALL, summons.location)
        self.menu(self.G_CALL, "在召見的地點", "act:summons")
        self.press(self.G_CALL, "act:summons", "應召")
        self.settle_choices(self.G_CALL, 10)
        self.me(self.G_CALL, "應召之後")

    def convoy_arrive(self) -> None:
        """押糧抵達：蕭鐵崖沒遇上截糧隊、軍令記一次；雷驚瀾撞上截糧隊打輸（糧車被劫）；顧長庚補糧草接下糧車、走一步、抵達，把官軍這道護糧湊滿（達成）。"""
        need = self.c.config.convoy_grain
        self.grain(self.G_RUN2, need + 2)
        self.press(self.G_RUN2, "act:convoy", "接糧車")
        self.hop(self.G_RUN2)
        for who, chance, tier in ((self.G_RUN, 0.0, "大勝"), (self.H_RUN, 1.0, "落敗"), (self.G_RUN2, 1.0, "大勝")):  # 顧長庚撞上截糧隊、打贏、照樣送到（審查：原本機率 0.0，一場仗都沒打）
            for _ in range(10):
                self.do(ADMIN, "fast_forward", {"hours": 1})
                with self.tuned(convoy_ambush_chance=chance), self.fights(tier):
                    self.main(who)
                state = self.chars.load(who)
                if state is None or state.player.convoy is None:
                    break
            self.me(who, "抵達之後")
        self.world_view("抵達之後")

    def admin(self) -> None:
        """管理者：替范潛龍發召見（再發一次〔已有〕、替散人、替有資格的人、不存在的名號）；快轉到第 2 週之後輪替席次；重發軍令；看席次後的第 4 階選單。"""
        for who in (self.H_CALL, self.H_CALL, self.LONE, self.G_SEAT, "無此人"):
            self.do(ADMIN, "summon", {"name": who})
        self.main(self.H_CALL)
        self.me(self.H_CALL, "管理者發了召見")
        self.forward_to_week(2)
        self.do(ADMIN, "rotate_seats")
        self.do(ADMIN, "issue_orders")
        self.world_view("輪替之後")
        for who in (self.G_SEAT, self.H_SEAT, self.G_R3):
            self.main(who)
            self.menu(who, "輪替之後", "act:rank:")
            self.me(who, "輪替之後")
        for who in (self.H_CALL, self.G_CALL, self.LONE, self.G_SEAT, "無此人"):  # 管理頁「玩家個人劇情」查名號（召見的計畫經它回給管理頁）
            self.call(ADMIN, "POST", "/api/admin/player", {"name": who})
        self.pause()

    def pause(self) -> None:
        """賽季時鐘暫停中：發軍令、輪替席次、發召見、有資格的人同步（抄帳什麼都不做）、走一步、答事件；繼續之後再同步一次（審查：這一路原本沒人走到）。"""
        self.do(ADMIN, "pause_clock")
        self.edit(self.G_R3, lambda p: (setattr(p, "qualified", True), p.contrib_weeks.update({1: 55})))
        self.do(ADMIN, "issue_orders")
        self.do(ADMIN, "rotate_seats")
        self.do(ADMIN, "summon", {"name": self.G_R3})
        for who in (self.G_R3, self.G_SEAT, self.H_SEAT):
            self.main(who)
            self.me(who, "暫停中")
        self.hop(self.G_R3)
        self.settle_choices(self.G_R3, 3)
        self.me(self.G_R3, "暫停中走了一步")
        self.world_view("暫停中")
        self.do(ADMIN, "resume_clock")
        for who in (self.G_R3, self.G_SEAT):
            self.main(who)
            self.me(who, "繼續之後")

    def bots(self) -> None:
        """假人：BotRunner 兩個（官軍，站在有戰線的地方、體力滿）若干輪；整季機器人眼前的選單挑哪一顆。"""
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
            p.bot = BotProfile(personality="普通", seed=91 + i, faction="guan" if "guan" in sides else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, self.spot("guan", 0), None
            p.visited.add(p.location)
            p.rank = 2 if i == 0 else 1
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.stats["silver"] = 300
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(23), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {91 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_MILITARY_TICKS", "8"))):
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
            emit(f"假人 {name}", {"loc": p.location, "stamina": p.stamina, "rank2_days": dict(sorted(p.rank2_days.items())), "convoy": p.convoy is not None,
                                  "journal": [[e.title, list(e.lines)[:3]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.world_view("假人之後")
        self.begin()
        solo = Game.new(self.c, "營丙", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        p = solo.state.player
        p.faction, p.location, p.journey, p.rank = "guan" if "guan" in sides else None, self.spot("guan", 0), None, 2
        p.visited.add(p.location)
        p.tutorial_step = len(self.c.tutorial.steps)
        p.stamina = float(self.c.config.stamina_max)
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單", [o.id for o in opts])
        emit("整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))

    def season(self) -> None:
        """收季、開下一季：手上的召見、押著的糧車、每週貢獻帳、席次怎麼帶。"""
        self.place(self.G_RUN2, self.spot("guan", 0))  # 收季時押著一車、不交（審查：休季時有車也回 None、換季帶不帶，原本沒人走到）
        self.grain(self.G_RUN2, self.c.config.convoy_grain + 2)
        self.press(self.G_RUN2, "act:convoy", "收季前接車")
        self.main(self.G_RUN2)
        self.me(self.G_RUN2, "收季前押著")
        self.do(ADMIN, "end_season")
        for who in (self.G_SEAT, self.G_CALL, self.H_CALL, self.G_RUN2):
            self.main(who)
        self.do(ADMIN, "next_season")
        for who in (self.G_SEAT, self.G_CALL, self.H_CALL, self.G_RUN2, self.H_RUN):
            self.main(who)
            self.me(who, "換季之後")
        self.world_view("換季之後")


# 改一個字（selftest）：糧車被劫那一句（搬之前在 engine.py 的 _convoy_arrives、之後在 tianxia/features/military/convoy_actions.py；第 2 項是之後的檔名，
# 搬的人照實際的檔名改這一個字串）
register_track("military", MilitaryScenario, (("tianxia/features/military/convoy_actions.py", "tianxia/engine.py"),
                                              ('"糧車被劫走了，這一趟不算數。"', '"糧車被劫走了，這一趟不算數！"')), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "jieyi", "legacy", "looks", "mall", "map",
                       "military", "outlets", "peers", "seal", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story",
                       "tavern", "territory_acts", "travel", "zhuan", "zongmen"))
