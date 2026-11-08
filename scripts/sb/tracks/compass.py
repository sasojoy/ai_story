"""same_behavior 一軌一檔：compass（這一檔登記 compass）。"""
from __future__ import annotations

import hashlib
import random

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, emit, register_track

# ═══════════════════════════ compass：「你這一步」一軌（全部拆包第 36 批，dev/core-step-1） ═══════════════════════════
# 「你這一步」與本週卡（核心批）：本週卡的「眼下要事」（main.week_card.steps）照 託付 → 軍令 → 揭了的懸賞 → 伏筆 → 新手目標 → 去投靠 排，
# 四勝利開著的季每一件補 target、id（護糧還沒接糧車多 then），「換一件事」（step:next，不在選單上、Game.choose 先接走）照今天按了幾次從那一件排起、
# 隔天從頭。計畫 docs/superpowers/plans/2026-11-06-你這一步-第36批.md 1.8、1.9。角色的名字都是原創的（PM 11/04）。懸賞單直接寫進季上的榜（CP_PREFIX 開頭、
# 揭的人寫好），糧車直接擺進存檔，其餘只打公開的 API 按下去。

CP_PREFIX = "cp_"


class CompassScenario(Scenario):
    """「你這一步」一軌（全部拆包第 36 批；--track compass，自己一個資料庫）。既有的軌已經走到每一種「眼下要事」與本週卡每一格（計畫 1.8），
    沒有一軌按過「換一件事」：這一軌補 step:next 與幾件疊在一起的先後——
    向晚舟（官軍）手上同時有開局那封信的委託、本週軍令（這一週沒有護糧軍令時擺一道：目標是起點、多 then）、四張揭了的懸賞（打探、討伐、護送、
    通緝）與伏筆片段：委託 → 軍令 → 懸賞 → 伏筆 排在同一張卡上；季聞簫（散人、新手期裡）揭一張討伐：委託 → 懸賞 → 新手目標 → 去投靠；
    閔素秋（豪強、還沒挑依附、開局那封信的委託作罷）眼下要事只剩章回。
    三個人各按「換一件事」（向晚舟兩下、季聞簫一下、閔素秋一下：清單是空的那一支）；測試內容與收了的季按了照舊當成不在選單上。
    **前半停在寫到一半的事**：向晚舟今天按了三下「換一件事」（PlayerState.step_day／step_skip 存在檔裡）、剛揭了一張新的打探還沒做、
    押著護糧軍令的糧車還沒送到（目標換成終點、不再有 then）。
    後半：新程式接著排（同一天照存檔的次數）、再按一下；季聞簫走到官軍的投靠點投靠（去投靠那一件換成軍令），新手期裡再拿伏筆片段
    （伏筆 → 新手目標）；隔天從頭、再按一下；假人（BotRunner 兩個官軍各揭一張打探，step:next 不在選單上、碰不到）；
    收季（本週卡沒有了、按了照舊不在選單上）、開下一季。
    沒有陣營、懸賞、四勝利的內容（測試內容）同一串 API 照打，寫「沒有」。"""

    STACK, DRIFT, QUIET = "向晚舟", "季聞簫", "閔素秋"
    PLAYERS = {STACK: "guan", DRIFT: None, QUIET: "haoqiang"}
    NEWBIE = "初臨渡口"
    BOT_SEATS = ["羅盤甲", "羅盤乙"]
    PHASES_FIRST = ["setup", "seat", "stack", "spin", "half"]
    PHASES_SECOND = ["resume", "spin_on", "settle", "next_day", "bots", "season"]

    # ── 小工具 ──

    def factions_on(self) -> bool:
        return {"guan", "huang"} <= {f.id for f in self.c.scenario.factions}

    def side(self, who: str) -> str | None:
        side = self.PLAYERS.get(who)
        return side if self.factions_on() and side in {f.id for f in self.c.scenario.factions} else None

    def hub(self) -> str:
        return self.c.scenario.start_location

    def spots(self, n: int) -> list[str]:
        """城外打得到人的地方（照 id 排；懸賞的地點用）。"""
        return sorted(i for i, x in self.c.locations.items() if x.enemies)[:n]

    def post(self, *bounties) -> None:
        """懸賞單直接寫進季上的榜（揭的人已經寫好）。"""
        def fn(s) -> None:
            s.bounties[:] = [b for b in s.bounties if b.id not in {x.id for x in bounties}] + list(bounties)

        self.world.mutate_season(fn)
        emit("掛上的懸賞", [[b.id, b.kind, b.faction, b.location, b.end, b.target, list(b.takers)] for b in bounties])

    def bounty(self, bid: str, kind: str, who: str, faction: str | None, **kw):
        from tianxia.state import Bounty

        far = self.world.get_season().time + 30 * 86400.0
        return Bounty(id=f"{CP_PREFIX}{bid}", kind=kind, faction=faction, week=1, expires=far, silver=20, deeds=1, takers=[who], **kw)

    def steps(self, who: str, tag: str) -> list:
        """看一次江湖頁（GET /api/main，整份照寫進輸出），另外把「眼下要事」縮成一行：[kind, id, 目標地點, then 的地點]（沒有本週卡寫 None）。"""
        view = self.main(who)
        card = view.get("week_card") if isinstance(view, dict) else None
        rows = None if card is None else [[s.get("kind"), s.get("id"), (s.get("target") or {}).get("location"),
                                           (s.get("then") or {}).get("location")] for s in card.get("steps", [])]
        emit(f"{who} 眼下要事 {tag}", rows)
        return rows or []

    def spin_steps(self, who: str, n: int, tag: str) -> None:
        """按 n 下「換一件事」（step:next：不在選單上，Game.choose 先接走），每一下之後看一次。"""
        for i in range(n):
            self.choose(who, "step:next")
            self.steps(who, f"{tag} 第 {i + 1} 下之後")
        state = self.chars.load(who)
        emit(f"{who} 換一件事的次數 {tag}", None if state is None else [state.player.step_day, state.player.step_skip])

    def orders_of(self, side: str | None) -> list:
        if side is None:
            return []
        w = self.world.get_season()
        return [o for o in w.orders if o.faction == side]

    def give_fragments(self, who: str, side: str) -> None:
        """管理者把這一方每一條伏筆鏈的片段都給他（伏筆那一件要聽過片段、時間窗開著才有）。"""
        chains = sorted((ch for ch in self.c.foreshadows.chains if ch.side == side), key=lambda ch: ch.id) if self.factions_on() else []
        emit(f"{who} 拿的伏筆片段", [ch.id for ch in chains])
        for ch in chains:
            for i in range(len(ch.fragments)):
                self.do(ADMIN, "give_fragment", {"name": who, "id": f"{ch.id}:{i}"})

    def add_escort(self, start: str, end: str) -> None:
        """向晚舟的陣營這一週沒有護糧軍令時擺一道（模板是內容裡官軍那一份護糧）：還沒接糧車時目標是起點、多一個 then（終點）；
        前半最後接了糧車，目標換成終點、不再有 then（step._order_places、_then 的兩支）。"""
        from tianxia import orders
        from tianxia.engine import Game
        from tianxia.state import Order

        with self.world.action_lock():
            state = self.chars.load(self.STACK)
        g = Game(self.c, state, world=self.world)
        week = orders.period_of(g.state, g.content)
        o = Order(id=f"{week}:guan:escort:{CP_PREFIX}", template="escort", faction="guan", week=week, location=start, start=start, end=end,
                  quota=2, text="（對照）護糧軍令")
        self.world.mutate_season(lambda s: s.orders.append(o))
        emit("擺上的護糧軍令", [o.id, o.start, o.end, o.week])

    # ── 前半 ──

    def setup(self) -> None:
        Scenario.setup(self)

    def seat(self) -> None:
        """向晚舟、閔素秋過了新手期站到起點（閔素秋是豪強、還沒挑依附；開局那封信附的委託作罷）；季聞簫照新手期、散人。"""
        self.place(self.STACK, self.hub(), self.side(self.STACK))
        self.place(self.QUIET, self.hub(), self.side(self.QUIET))

        def lapse(p) -> None:
            for x in p.letters:
                if x.task is not None:
                    x.lapsed = True

        self.edit(self.QUIET, lapse)
        emit("向晚舟陣營本週的軍令", [[o.id, o.template, o.location, o.start, o.end, o.front, o.figure, o.done] for o in self.orders_of(self.side(self.STACK))])
        for who in (self.STACK, self.DRIFT, self.QUIET):
            self.steps(who, "坐定")

    def stack(self) -> None:
        """幾件疊在一起：向晚舟揭四張懸賞（打探、討伐、護送、通緝）、拿伏筆片段；季聞簫揭一張討伐。"""
        a, b = (self.spots(2) + [self.hub(), self.hub()])[:2]
        side = self.side(self.STACK) or "guan"
        self.post(self.bounty("scout", "scout", self.STACK, side, location=a),
                  self.bounty("strike", "strike", self.STACK, side, location=b),
                  self.bounty("escort", "escort", self.STACK, side, location=self.hub(), end=a),
                  self.bounty("wanted", "wanted", self.STACK, side, poster="（對照）掛單人", target=self.QUIET),
                  self.bounty("drift", "strike", self.DRIFT, "guan", location=b))
        if self.factions_on() and not any(o.template == "escort" for o in self.orders_of(side)):
            self.add_escort(self.hub(), a)
        self.give_fragments(self.STACK, side)
        for who in (self.STACK, self.DRIFT, self.QUIET):
            self.steps(who, "疊在一起")

    def spin(self) -> None:
        """三個人各按「換一件事」：向晚舟兩下、季聞簫一下、閔素秋一下（清單是空的那一支）。"""
        self.spin_steps(self.STACK, 2, "向晚舟")
        self.spin_steps(self.DRIFT, 1, "季聞簫")
        self.spin_steps(self.QUIET, 1, "閔素秋（什麼都沒有）")

    def half(self) -> None:
        """前半停在寫到一半：向晚舟今天再按一下（三下）、剛揭了一張新的打探還沒做、押著護糧軍令的糧車還沒送到。"""
        from tianxia.state import Convoy

        spot = (self.spots(3) + [self.hub()] * 3)[2]
        self.post(self.bounty("scout_new", "scout", self.STACK, self.side(self.STACK) or "guan", location=spot))
        escort = next((o for o in self.orders_of(self.side(self.STACK)) if o.template == "escort" and not o.done), None)
        emit("向晚舟押的那一道護糧軍令", None if escort is None else [escort.id, escort.start, escort.end])
        if escort is not None:
            self.edit(self.STACK, lambda p: setattr(p, "convoy", Convoy(order=escort.id, grain=3, from_loc=escort.start, to_loc=escort.end)))
        self.spin_steps(self.STACK, 1, "向晚舟（前半最後）")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()
        for who in (self.STACK, self.DRIFT, self.QUIET):
            self.steps(who, "接手")

    def spin_on(self) -> None:
        self.spin_steps(self.STACK, 1, "向晚舟（接手之後）")

    def settle(self) -> None:
        """季聞簫走到官軍的投靠點投靠（去投靠那一件換成軍令）；投靠之前、之後各看一次。"""
        factions = {f.id: f for f in self.c.scenario.factions}
        if "guan" not in factions or not factions["guan"].join_at:
            emit("投靠：這份內容沒有陣營", None)
            return
        where = factions["guan"].join_at[0]

        def go(p) -> None:
            p.location, p.journey = where, None
            p.visited.add(where)

        self.edit(self.DRIFT, go)
        self.steps(self.DRIFT, "到了投靠點")
        self.choose(self.DRIFT, "faction:guan")
        self.choose(self.DRIFT, "faction:confirm")
        self.settle_choices(self.DRIFT)
        self.steps(self.DRIFT, "投靠之後")
        self.give_fragments(self.DRIFT, "guan")  # 新手期裡又有伏筆：伏筆 → 新手目標排在同一張卡上
        self.steps(self.DRIFT, "拿了伏筆片段之後")

    def next_day(self) -> None:
        """隔天（回體丹那一套的台灣 00:00 換日）：從頭排；再按一下記成新的一天。"""
        STEP[0] += 1440
        self.steps(self.STACK, "隔天")
        self.spin_steps(self.STACK, 1, "向晚舟（隔天）")

    def bots(self) -> None:
        """假人：BotRunner 兩個（官軍，站在起點、各揭一張打探）若干輪；step:next 不在選單上，假人碰不到。"""
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        on = self.factions_on()
        spot = (self.spots(1) + [self.hub()])[0]
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=71 + i, faction="guan" if on else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, self.hub(), None
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            self.chars.save(g.state)
            self.post(self.bounty(f"bot_scout_{i}", "scout", name, p.faction or "guan", location=spot))
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(43), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {71 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(6):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            emit(f"假人 {name}", {"loc": s.player.location, "step": [s.player.step_day, s.player.step_skip], "done": s.player.bounties_done,
                                  "journal": [[e.title, list(e.lines)[:4]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.steps(self.STACK, "假人之後")

    def season(self) -> None:
        """收季：本週卡沒有了，按「換一件事」照舊當成不在選單上；開下一季再看一次。"""
        self.do(ADMIN, "end_season")
        self.steps(self.STACK, "收季之後")
        self.spin_steps(self.STACK, 1, "向晚舟（收季之後）")
        self.do(ADMIN, "next_season")
        self.steps(self.STACK, "換季之後")


# 改一個字（selftest）：「換一件事」一下記一次（step.skip；核心的 tianxia/step.py，第 36 批之後照舊在那裡）
register_track("compass", CompassScenario, (("tianxia/step.py",), ("else 0) + 1\n", "else 0) + 2\n")), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "hire", "legacy", "looks", "mall", "map",
                       "military", "notify", "outlets", "peers", "persona", "seal", "seclusion", "sense", "smithy", "socialize",
                       "sortie", "stamina_plays", "story", "tale", "tavern", "territory_acts", "travel", "zhuan"))
