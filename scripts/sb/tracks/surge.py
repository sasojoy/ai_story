"""same_behavior 一軌一檔：surge（這一檔登記 surge）。"""
from __future__ import annotations

import random
from collections import Counter

from sb.harness import ADMIN, CLOCK, STEP, emit, register_track
from sb.tracks.strip import StripScenario

# ═══════════════════════════ surge：推大勢與回體丹走不到的岔路（第二輪第 80 批，dev/pushing） ════════════
# 第 80 批把 Game 上的推大勢（push_trend 那一群 12 個）與回體丹（take_stamina_pill 那一群 6 個）搬進 tianxia/core/pushing.py、pills.py。
# 開工量過全部 63 軌三種設定（189 格）走到這 18 個方法的哪幾行：回體丹的沒有丹、今天服滿、序章裡、一鍵補滿（整支 _refill_stamina），
# 推大勢的 _carry（整支）、傳檄（push_trend、_push_progress 各一行）、規則關著的季的零頭、不會動的推動、盡頭阻力關著、不是 21 天季的上限與季長倍數，
# 還有 _top_up_pills 手上夠多那一下。這一軌專走那些。
# **半舊半新切在 half**：今天服過一顆（pill_day、pills_today 是舊程式寫的）、線上有零頭、今天這條線的帳與文字的事那一本記到一半、舊角色的回體丹還沒補；
# 後半第一件事是新程式接著服、接著推、讀檔那一刻才補。
# 假人：strip 那一套 bots（BotRunner＋bot_policy.take_turn，推大勢的出陣、遊歷、事件），再加體力見底的一輪（bot.take_pill → take_stamina_pill(pill_only=True)，
# 一鍵補滿開著也只吃丹）。
# 這一軌自己走不到的（量過）：集火那兩行（_push_progress 的 focus，sortie 那一軌走到）。測試內容沒有陣營、玉璽、地盤、21 天季：傳檄、進度、文字的事、21 天季的上限只有
# season21、week7 走到；新手期的上限（pill_cap）測試內容也沒有。writ 段按完的那則事件，week7 沒走到 _event_progress 推進度那一行（season21 走到，events 等軌也走到）。
# 角色與名字都是原創的（PM 11/04）。


class SurgeScenario(StripScenario):
    """推大勢與回體丹的岔路（--track surge，自己一個資料庫）。小工具借 strip、事件、探索那幾軌的（card、press、first_event、tweak、edit_state、trends）。
    直接叫 Game 的那幾下（poke、peek）是 API 走不到的岔路（序章、換掉設定才走得到）：Game 上的名字搬之前、之後都在。"""

    EATER, FREE, HUT, TOPPED = "齊硯冰", "葛聽濤", "連翹生", "舒半夏"  # 散人：服丹、一鍵補滿、序章裡、讀檔補丹
    GUAN, HUANG, WRIT, RANGER = "陶朗月", "韋澹之", "房牧雲", "苗采薇"
    HALF_EATER = "岑望舟"  # 切在今天服過一顆
    PLAYERS = {EATER: None, FREE: None, HUT: None, TOPPED: None, HALF_EATER: None, GUAN: "guan", HUANG: "huang", WRIT: "huang", RANGER: None}
    NEWBIE = "鍾小禾"
    BOT_SEATS = [("潮甲", "yingshui"), ("潮乙", "julu_altar"), ("潮丙", "guangzong"), ("潮丁", "market_town")]
    PHASES_FIRST = ["setup", "pills", "refill", "hut", "topped", "pushes", "writ", "ruleless", "unresisted", "not21", "deeds", "half"]
    PHASES_SECOND = ["resume", "pills_on", "pushes_on", "taken_over", "tomorrow", "bots", "drained", "season"]

    # ── 小工具 ──

    def book(self, who: str, tag: str) -> None:
        """這一群碰得到的帳：體力、丹、今天服幾顆、線上的數與零頭、今天推的帳、貢獻、文字的事那一本、最新一則紀錄。"""
        state = self.chars.load(who)
        p = state.player
        s = self.world.get_season()
        emit(f"{who} {tag} 的帳", {
            "stamina": p.stamina, "pills": [p.stamina_pills, p.pill_day, p.pills_today, p.pills_topped_to],
            "pushed": dict(sorted(p.pushed.items())), "contrib": [p.contrib, dict(sorted(p.contrib_weeks.items()))],
            "deed": [p.deed_day, p.deed_today], "trends": dict(sorted(s.trends.items())), "accum": dict(sorted(s.trend_accum.items())),
            "active": {side: sorted(names) for side, names in sorted(s.active_pushers.items())},
            "journal": [[e.title, list(e.lines), list(e.changes)] for e in state.journal[:1]]})

    def peek(self, who: str):
        """這個人此刻的 Game（對過時鐘，只讀：不存）。"""
        from tianxia.engine import Game

        self.begin()
        game = Game(self.c, self.chars.load(who), world=self.world)
        game.sync(CLOCK[0])
        return game

    def poke(self, who: str, tag: str, fn) -> None:
        """在鎖裡對這個人的 Game 做一下（同伺服器的三步：對時鐘、做、存），寫下回傳與帳。"""
        from tianxia.engine import Game

        self.begin()
        with self.world.action_lock():
            game = Game(self.c, self.chars.load(who), world=self.world)
            game.sync(CLOCK[0])
            out = fn(game)
            game._save_season()
            self.chars.save(game.state)
        emit(f"{who} {tag}", out)
        self.book(who, tag)

    def reads(self, who: str, tag: str) -> None:
        """這一群的查詢：季長倍數、上限、線、目標、還推得動多少、_shaped 每一條線每一種來源、今天還能服幾顆、上限。"""
        g = self.peek(who)
        lines = self.lines(g)
        emit(f"{who} {tag} 查", {
            "scale": g.season_scale(), "cap": g.daily_push_cap(), "resisted": sorted(g._resisted_lines()), "goals": dict(sorted(g._goals().items())),
            "room": {line: g._push_room(line) for line in lines},
            "shaped": {line: {src: list(g._shaped(line, 2.0, src)) for src in ("event", "event_once", "donate", "sortie", "train", "drill")} for line in lines},
            "pill": [g.pill_now(), g.pill_cap(), g.pills_left_today()]})

    def lines(self, game) -> list[str]:
        """推得動的線：盡頭阻力管的那幾條（第一季三條戰線、規則關著的季合成的那一條）；測試內容沒有戰線，照季上有的。"""
        return sorted(game._resisted_lines()) or sorted(game.state.world.trends)

    def line(self, who: str) -> str:
        return self.lines(self.peek(who))[0]

    def low(self, who: str, stamina: float = 3.5, pills: int | None = None) -> None:
        """體力見底；pills 給了就把手上的丹也擺好（不讓讀檔補丹碰到）。"""
        def fn(p):
            p.stamina = stamina
            if pills is not None:
                p.stamina_pills, p.pills_topped_to = pills, 10 ** 6
        self.edit(who, fn)

    def setup(self) -> None:
        StripScenario.setup(self)
        self.main(self.NEWBIE)

    # ── 前半 ──

    def pills(self) -> None:
        """/api/do/pill（狀態列上的「丹」）：滿的、服得下、今天服滿（兩顆、五顆、十一顆的字）、不限、沒有丹。"""
        who, cfg = self.EATER, self.c.config
        self.reads(who, "開場")
        self.do(who, "pill")
        self.book(who, "滿的")
        with self.tweak(cfg, stamina_pills_per_day=2):
            self.low(who, pills=5)
            for tag in ("第一顆", "第二顆", "今天服滿"):
                self.do(who, "pill")
                self.book(who, tag)
                self.low(who)
        for cap in (5, 11):
            with self.tweak(cfg, stamina_pills_per_day=cap):
                self.edit(who, lambda p, cap=cap: setattr(p, "pills_today", cap))
                self.do(who, "pill")
                self.reads(who, f"上限 {cap}")
        with self.tweak(cfg, stamina_pills_per_day=0):
            self.do(who, "pill")
            self.reads(who, "不限")
        self.low(who, pills=0)
        self.do(who, "pill")
        self.book(who, "沒有丹")
        self.low(self.NEWBIE, pills=3)
        self.do(self.NEWBIE, "pill")
        self.reads(self.NEWBIE, "新手期")

    def refill(self) -> None:
        """一鍵補滿開著（Config.beta_free_refill）：滿的、補滿（不收丹、寫一則紀錄）；假人那一條（pill_only）照舊吃丹。"""
        from tianxia import bot

        who, cfg = self.FREE, self.c.config
        with self.tweak(cfg, beta_free_refill=True):
            self.do(who, "pill")
            self.book(who, "補滿 滿的")
            self.low(who, 37.5, pills=4)
            self.do(who, "pill")
            self.book(who, "補滿")
            self.low(who)
            self.poke(who, "pill_only", lambda g: g.take_stamina_pill(pill_only=True))
            self.low(who)
            self.poke(who, "整季機器人的 take_pill", lambda g: bot.take_pill(g))

    def hut(self) -> None:
        """序章裡：三種設定都沒有序章（season21、week7 是開局第一分鐘），內容的 tutorial 換一步（記憶體裡，同一步換回），人站在草廬。
        還沒教到服丹（不收丹，一鍵補滿開著回另一句）、教到服丹那一步（照真的服，一鍵補滿開著也是）。"""
        from tianxia.models import TutorialGoal, TutorialStep

        who, cfg, t = self.HUT, self.c.config, self.c.tutorial
        here = self.chars.load(who).player.location
        walked = self.chars.load(who).player.tutorial_step

        def steps(action: str) -> list:
            return [TutorialStep(id="surge_step", text="", done_when=TutorialGoal(action=action))]

        def first_step(p):
            p.tutorial_step = 0

        self.edit(who, first_step)
        self.low(who, pills=4)
        with self.tweak(t, location=here, prologue_steps=9, steps=steps("explore")):
            self.poke(who, "序章裡還沒教到服丹", lambda g: g.take_stamina_pill())
            with self.tweak(cfg, beta_free_refill=True):
                self.poke(who, "序章裡的一鍵補滿", lambda g: g.take_stamina_pill())
        with self.tweak(t, location=here, prologue_steps=9, steps=steps("pill")):
            with self.tweak(cfg, beta_free_refill=True):
                self.poke(who, "序章教到服丹，一鍵補滿開著", lambda g: g.take_stamina_pill())
        self.edit(who, lambda p: setattr(p, "tutorial_step", walked))

    def topped(self) -> None:
        """讀檔補丹（_top_up_pills）：手上夠多（只記補到哪）、不夠（補、寫一行）；測試內容的贈送關著，換一下。"""
        who, cfg = self.TOPPED, self.c.config
        with self.tweak(cfg, beta_gift=True, beta_gift_stamina_pills=max(cfg.beta_gift_stamina_pills, 3)):
            self.low(who, pills=99)
            self.edit(who, lambda p: setattr(p, "pills_topped_to", 0))
            self.main(who)
            self.book(who, "手上夠多")
            self.edit(who, lambda p: (setattr(p, "pills_topped_to", 0), setattr(p, "stamina_pills", 1)))
            self.main(who)
            self.book(who, "補到")

    def pushes(self) -> None:
        """/api/choose 真的按（可重複的事件、一次性的事件）；直接叫的：不會動的推動、每一種來源、三種人（替自己陣營、逆著推、散人）、頂到每人每日上限。"""
        from tianxia import territory
        from tianxia.rules import is_revealed

        who, foe, ranger, cfg = self.GUAN, self.HUANG, self.RANGER, self.c.config
        self.trends("開場")
        hidden = next((t.id for t in self.c.scenario.trends if t.hidden and not is_revealed(self.world.get_season(), self.c, t.id)), None)
        emit("還沒浮現的線", hidden)
        if hidden:
            self.poke(who, "還沒浮現的線往回推", lambda g: g.push_trend(hidden, -2, source="event"))
        repeat = self.first_event(lambda e: not e.once and not e.qiyu and any(ch.effect.trend for ch in e.choices))
        once = self.first_event(lambda e: e.once and any(ch.effect.trend for ch in e.choices))
        for person, eid in ((who, repeat), (foe, once)):
            if self.card(person, eid):
                self.press(person, lambda ch: bool(ch.effect.trend), f"{eid} 推大勢那一顆")
                self.settle_choices(person)
                self.book(person, f"{eid} 之後")
        line = self.line(who)
        self.poke(who, "不會動的推動", lambda g: g.push_trend(line, 0, source="train"))
        for src in ("train", "event", "event_once", "drill", "duty"):
            self.poke(who, f"推一下 {src}", lambda g, src=src: g.push_trend(line, 2, source=src))
        self.poke(foe, "往回推", lambda g: g.push_trend(line, -3, source="event_once"))
        self.poke(ranger, "散人照推", lambda g: g.push_trend(line, 3, source="event_once"))
        with self.tweak(cfg, daily_push_cap=1):
            self.reads(foe, "上限 1")
            for i in range(2):
                self.poke(foe, f"頂到上限 {i}", lambda g: g.push_trend(line, 2, source="event_once"))
        w = self.world.get_season()
        home = next((loc for loc in sorted(self.c.locations) if territory.on(self.c) and territory.controller(w, self.c, loc) == "huang"), None)
        emit("自家控制的地方", home)
        if home is not None:  # 打了阻力的那一下接另一句（_resisted_line）
            self.place(foe, home)
            self.poke(foe, "站在自家地方推過頭", lambda g: g.push_trend(line, 3, source="event_once"))

    def writ(self) -> None:
        """傳檄（玉璽碎片）生效時：一軍往自家目標推乘上去（push_trend，_shaped 之後）、逆著推不乘、地盤的進度也乘（_push_progress）；按完一則事件；出陣那一支（混戰得勝、記一筆）。
        測試內容沒有玉璽，也沒有地盤。"""
        from tianxia import conquest, seal_acts
        from tianxia.state import SealAct

        who = self.WRIT
        line = self.line(who)

        def stand(g):
            w = g.state.world
            w.seal_acts.append(SealAct(kind="chuanxi", shard="chizhang", start=w.time, until=w.time + 10 ** 7, target=line, side="huang"))
            return [seal_acts.on(self.c), seal_acts.writ_factor(w, self.c, line, "huang"), seal_acts.writ_factor(w, self.c, line, "guan")]

        self.poke(who, "傳檄", stand)
        self.poke(who, "傳檄之下往自家推", lambda g: g.push_trend(line, 3, source="event_once"))
        self.poke(who, "傳檄之下逆著推（不乘）", lambda g: g.push_trend(line, -3, source="event_once"))
        side = "huang"
        w = self.world.get_season()
        spot = next((loc for loc in sorted(self.c.locations) if conquest.on(self.c) and conquest.line_of(w, self.c, loc) == line
                     and conquest.push_problem(w, self.c, side, loc, "attack") is None), None)
        emit("傳檄那條線上攻得動的地方", spot)
        if spot is None:
            return
        self.place(who, spot)
        self.poke(who, "傳檄之下的進度", lambda g: g._push_progress(spot, 2.0, "event", "attack"))
        self.poke(who, "沒說攻守的進度", lambda g: g._push_progress(spot, 2.0, "event"))
        plain = self.first_event(lambda e: not e.once and not e.qiyu and bool(e.choices))
        self.edit_state(who, lambda s: setattr(s, "pending_event", plain))
        self.press(who, lambda ch: True, f"{plain} 了結")
        self.settle_choices(who)
        self.book(who, "事件了結")

        def sortie(g):  # 出陣那一支：混戰得勝的加成、記一筆出陣、這一下推動了多少（Game 上的欄位，出陣回報讀）
            g._clash_won = True
            out = g._push_progress(spot, 2.0, "sortie", "attack")
            return [out, g._sortie_marked, g._sortie_moved, g._sortie_flipped]

        self.poke(who, "出陣那一支", sortie)

    def ruleless(self) -> None:
        """規則關著的季（Config.season_one 換成關，同一步換回；測試內容本來就關）：季長縮放之後的零頭、滿一點才推（_carry）、隱藏線照原本的量；零頭正好滿的那一下。"""
        who, cfg = self.GUAN, self.c.config
        with self.tweak(cfg, season_one=False, drill_push_base_days=0.5):
            self.reads(who, "規則關著")
            line = self.line(who)
            for src, amount in (("event", 3), ("train", 3), ("train", 40), ("sortie", 2), ("donate", 2), ("event_once", 2), ("event_once", 2.5), ("drill", 1)):
                self.poke(who, f"規則關著 {src} {amount}", lambda g, src=src, amount=amount: g.push_trend(line, amount, source=src))
            self.poke(who, "零頭記著", lambda g: g._carry(line, 0.25))
            self.poke(who, "零頭滿一點（清掉）", lambda g: g._carry(line, 1.0 - g.state.world.trend_accum.get(line, 0.0)))

    def unresisted(self) -> None:
        """盡頭阻力關著（Config.push_resistance.enabled）：_shaped 在那裡就回傳；上限不乘季長倍數。"""
        who, cfg = self.HUANG, self.c.config
        with self.tweak(cfg.push_resistance, enabled=False):
            self.reads(who, "阻力關著")
            self.poke(who, "阻力關著推一下", lambda g: g.push_trend(self.lines(g)[0], 2, source="event"))

    def not21(self) -> None:
        """不是 21 天季（Config.season21 換成關）：每人每日上限照 daily_push_cap（阻力開著乘季長倍數）、出陣與捐軍備乘季長倍數。測試內容規則本來就關，只走得到上限那一行。"""
        who, cfg = self.HUANG, self.c.config
        with self.tweak(cfg, season21=False):
            self.reads(who, "不是 21 天季")
            with self.tweak(cfg.push_resistance, enabled=True):
                self.reads(who, "不是 21 天季，阻力開著")
                self.poke(who, "不是 21 天季捐軍備", lambda g: g.push_trend(self.lines(g)[0], 4, source="donate"))

    def deeds(self) -> None:
        """文字的事那一本（_deed_points）：記、一天的上限、capped=False 不佔額度、0 點、散人不記。"""
        who, cfg = self.GUAN, self.c.config
        self.poke(who, "文字的事 0 點", lambda g: g._deed_points(0))
        self.poke(who, "文字的事 2 點", lambda g: g._deed_points(2))
        self.poke(who, "文字的事超過上限", lambda g: g._deed_points(10 ** 4))
        self.poke(who, "文字的事頂滿了", lambda g: g._deed_points(1))
        self.poke(who, "託付辦成了", lambda g: g._deed_points(5, capped=False))
        self.poke(self.RANGER, "散人不記", lambda g: g._deed_points(2))
        emit("文字的事一天上限", getattr(getattr(cfg, "jianfa", None), "deed_contribution_cap", None))

    def half(self) -> None:
        """切在寫到一半：今天服過一顆、線上有零頭、今天的帳與文字的事記到一半、舊角色的丹還沒補。"""
        who = self.HALF_EATER
        with self.tweak(self.c.config, stamina_pills_per_day=2):
            self.low(who, pills=5)
            self.do(who, "pill")
        self.book(who, "切之前")
        line = self.line(self.HUANG)
        self.poke(self.HUANG, "切之前的零頭", lambda g: g.push_trend(line, 1.5, source="event_once"))
        self.poke(self.RANGER, "切之前的零頭（散人）", lambda g: g.push_trend(line, 1.25, source="event_once"))
        self.poke(self.WRIT, "切之前的文字的事", lambda g: g._deed_points(1))
        self.edit(self.TOPPED, lambda p: (setattr(p, "pills_topped_to", 0), setattr(p, "stamina_pills", 0)))

    # ── 後半 ──

    def pills_on(self) -> None:
        """新程式接著服：今天第二顆（舊程式記的第一顆算數）、服滿。"""
        who, cfg = self.HALF_EATER, self.c.config
        with self.tweak(cfg, stamina_pills_per_day=2):
            self.low(who)
            self.do(who, "pill")
            self.book(who, "接手第二顆")
            self.low(who)
            self.do(who, "pill")
            self.book(who, "接手服滿")
            self.reads(who, "接手")

    def pushes_on(self) -> None:
        """新程式接著推（同一天）：舊程式留的零頭滿一點、今天這條線的帳接著記、文字的事接著記。"""
        line = self.line(self.HUANG)
        self.trends("接手")
        for i, who in enumerate((self.HUANG, self.RANGER)):
            self.poke(who, f"接著推 {i}", lambda g: g.push_trend(line, 1.5, source="event_once"))
        self.poke(self.WRIT, "接著記文字的事", lambda g: g._deed_points(1))
        self.reads(self.HUANG, "接手")

    def taken_over(self) -> None:
        """讀檔那一刻才補丹：舊程式留的角色、新程式補、寫那一行。"""
        with self.tweak(self.c.config, beta_gift=True, beta_gift_stamina_pills=max(self.c.config.beta_gift_stamina_pills, 3)):
            self.main(self.TOPPED)
            self.book(self.TOPPED, "接手補丹")

    def tomorrow(self) -> None:
        """過一天（一步 60 秒）：今天服幾顆、今天推的帳、文字的事那一本都換日。"""
        who, cfg = self.HALF_EATER, self.c.config
        STEP[0] += 1441
        with self.tweak(cfg, stamina_pills_per_day=2):
            self.main(who)  # 先對時鐘（這一天回的體力補算完），不然下面擺的見底被補算蓋掉
            self.low(who)
            self.do(who, "pill")
            self.book(who, "隔天")
        line = self.line(self.HUANG)
        self.poke(self.HUANG, "隔天推", lambda g: g.push_trend(line, 1.5, source="event_once"))
        self.poke(self.WRIT, "隔天的文字的事", lambda g: g._deed_points(1))
        self.reads(self.HUANG, "隔天")

    def drained(self) -> None:
        """假人體力見底：bot_policy.take_turn 開頭的 bot.take_pill 服一顆（一鍵補滿開著也只吃丹，不補滿）；紀錄標題與丹數寫下來。"""
        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner

        names = [name for name, _ in self.BOT_SEATS]
        for name in names:
            self.low(name, pills=2)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(23), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {61 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            with self.tweak(self.c.config, beta_free_refill=True):
                for _ in range(4):
                    STEP[0] += 3
                    self.begin()
                    report = runner.tick()
                    totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        states = [s for s in self.chars.all(bots_only=True) if s.player.name in names]
        emit("體力見底的假人 一輪一輪", dict(sorted(totals.items())))
        emit("體力見底的假人", {s.player.name: [s.player.stamina_pills, s.player.pills_today, sorted(Counter(e.title for e in s.journal).items())] for s in states})

    def season(self) -> None:
        """收季：休季按「丹」。開下一季：線上的零頭、今天的帳照換季清，丹照帶。"""
        self.do(ADMIN, "end_season")
        self.low(self.EATER, pills=2)
        self.do(self.EATER, "pill")
        self.book(self.EATER, "休季")
        self.do(ADMIN, "next_season")
        self.main(self.EATER)
        self.settle_choices(self.EATER)
        self.low(self.EATER)
        self.do(self.EATER, "pill")
        self.book(self.EATER, "下一季")
        self.reads(self.HUANG, "下一季")


# 改一個字（selftest）：今天服滿那一句（搬之前在 engine.py、之後在 tianxia/core/pills.py），pills 那一段抓到
register_track("surge", SurgeScenario, (("tianxia/core/pills.py", "tianxia/engine.py"),
                                        ("今天已服{n}顆，明日 00:00 後再服。", "今天已服{n}顆，明日 00:00 後再服！")), "week7")
