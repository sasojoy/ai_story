"""same_behavior 一軌一檔：stamina（這一檔登記 stamina）。"""
from __future__ import annotations

import contextlib
import hashlib
import os
import random

from sb.harness import ADMIN, CLOCK, STEP, emit, register_track
from sb.tracks.world import WorldScenario

class StaminaScenario(WorldScenario):
    """體力玩法與閉關一軌（全部拆包第 39 批：設伏、屯糧進 stamina_plays，閉關進 seclusion；--track stamina，自己一個資料庫）。
    設伏（ambush:set／lift）：埋（扣體力、季上與角色身上各一筆、守著不能移動）、中伏（敵對陣營的人走過那一段：自然、伏兵必勝、伏兵必敗各一場；
    自己人、散人走過不打）、撤（自己收伏）、守滿到時刻自己收；不能設的幾種（散人沒揭通緝、守著還要再設、城鎮旁、設伏關著的季）灰著或寫原因。
    屯糧（works:stockpile）：設定關著（三種設定的預設）沒有鈕、硬按寫「此刻無法這麼做」；打開之後官軍、黃巾各在自己的大本營屯幾下，
    **開集結那一刻結算**（管理者開時刻表上第一件決戰：起點照戰線、屯糧、玉璽、龍頭上陣四格，屯糧換成起點的偏移、天下大事一句、屯的量清空）。
    閉關（/api/do/seclude 1～12 小時、act:break 提早出關）：越界的小時夾住、閉關中再閉寫「現在無法閉關」、閉關中只剩提前出關與擂台、
    自己滿時自然出關（sync 結算）、提前出關。
    **審查查出沒走到的**（說明不寫成涵蓋了）：新人的序章拒絕（新人按閉關回的是「你現在無法閉關。」，走 _idle 那一支，三種設定都沒有序章）、
    修練頁 /api/menxia 的 seclude_blocked（這一軌沒請求修練頁）、假人守著走不開先收伏（bot_policy 那一支要有決戰集結才走到）、
    硬按的拒絕（都被 Game.choose 的「此刻無法這麼做」擋在核心，到不了包裡的 set_problem）、平手、偏移不是 0 的開集結；這幾支靠 ast 逐條比對舊新相同。
    **前半停在三件寫到一半的事**：設伏埋了還沒人走過、閉關閉到一半（十二小時才過一小時不到）、兩軍屯了糧還沒開集結。
    後半：新程式接著讓人走過那一段、提前出關、開集結結算；假人（BotRunner 四個：路上兩個、大本營兩個，其中一個先埋好伏〔守著走不開，先收伏〕；
    整季機器人眼前的選單與挑法、bot_policy.score 對 ambush:／works: 的分數）；收季、開下一季。
    沒有陣營的內容（測試內容）同一串 API 照打：設伏、屯糧寫「沒有」，閉關照走。"""

    A, B1, B2, B3, C, D, E, F, G = "曲臨淵", "項疏影", "宗無咎", "霍青鸞", "尹遙岑", "屈寒松", "鄂南風", "樊聽雪", "裘半夏"
    NEWBIE = "初出茅廬"
    PLAYERS = {A: "guan", B1: "huang", B2: "huang", B3: "huang", C: "guan", D: "huang", E: "guan", F: "huang", G: None}
    BOT_SEATS = ["伏甲", "伏乙", "糧甲", "糧乙"]
    PHASES_FIRST = ["setup", "seat", "refuse", "stock_off", "stock_on", "ambush_set", "seclude_start", "half"]
    PHASES_SECOND = ["resume", "hits", "lift_expire", "seclude_end", "muster", "bots", "season"]

    # ── 小工具 ──

    def pair(self) -> tuple[str, str]:
        """（埋伏的人站的地方, 路的另一頭）：第一對兩頭都不是城鎮的路（照地點 id 排序，connections 的順序）。"""
        from tianxia import ambush

        for a in sorted(self.c.locations):
            for to in self.c.locations[a].connections:
                if ambush.road_ok(self.c, a, str(to)):
                    return a, str(to)
        return self.hub(), self.hub()

    def base_of(self, side: str) -> str:
        from tianxia import territory

        try:
            bases = territory.bases(self.c)
        except Exception:  # noqa: BLE001
            bases = {}
        return next((loc for loc, owner in sorted(bases.items()) if owner == side), self.hub())

    def set_stock(self, on: bool) -> None:
        """屯糧的開關（三種設定的預設都關著）：同一個行程裡共用 CONTENT，每個行程各自設。"""
        self.c.config.stockpile.enabled = on

    def kinds(self, who: str, tag: str) -> dict:
        """此刻選單上跟這一軌有關的那幾顆（設伏、屯糧、提前出關、移動），連同開著與否與標籤。"""
        view = self.main(who)
        mine = {i: [o.get("enabled"), o.get("label")] for i, o in self.ids(view).items()
                if i.startswith(("ambush:", "works:", "act:break")) or i.startswith("move:")}
        emit(f"{who} 選單 {tag}", mine)
        return mine

    def me(self, who: str, tag: str) -> None:
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        post = None if p.ambush is None else p.ambush.model_dump(mode="json")
        emit(f"{who} {tag}", {
            "loc": p.location, "journey": None if p.journey is None else p.journey.model_dump(mode="json"), "faction": p.faction,
            "stamina": p.stamina, "silver": p.stats.get("silver"), "xinde": p.stats.get("xinde"),
            "materials": dict(sorted(p.materials.items())), "ambush": post, "busy_until": p.busy_until,
            "seclusion": [p.seclusion_start, p.seclusion_done], "contrib": p.contrib,
            "journal": [[e.title, e.tag, list(e.lines)[:4], list(e.changes)[:3]] for e in state.journal[:4]]})

    def stock_view(self, tag: str) -> None:
        """季上跟體力玩法有關的帳：各軍屯了幾下、各段路上的埋伏、決戰（含起點偏移與快照的屯量）、天下大事的尾巴。"""
        w = self.world.get_season()
        b = self.world.get_battle()
        emit(f"世界 {tag}", {
            "supply": dict(sorted(w.supply.items())),
            "ambushes": {k: [[a.owner, a.at, a.to, a.set_at, a.until, a.lifted_at, a.caught, a.side] for a in v] for k, v in sorted(w.ambushes.items())},
            "raids": dict(sorted(w.raids.items())), "raided": dict(sorted(w.raided.items())),
            "battle": None if b is None else [b.battle_id, b.phase, b.trend, b.trend_start, dict(sorted(b.supply_lean.items()))],
            "opened": dict(w.showdowns_opened), "rumors": [r.text for r in w.rumors][-4:], "chronicle": [r.text for r in w.chronicle][-3:]})

    @contextlib.contextmanager
    def tilt(self, shift: float):
        """設伏打這一場的判定平移（encounter.resolve_encounter 的 shift：正的偏伏兵，負的偏路過的人；威力、亂數照算，只多一個平移）。"""
        from tianxia import encounter

        real = encounter.resolve_encounter

        def resolve(our_power, difficulty, rng, positional_shift=0.0, mods=None, **kw):
            own = kw.pop("shift", positional_shift)
            return real(our_power, difficulty, rng, shift=own + shift, mods=mods, **kw)

        encounter.resolve_encounter = resolve
        emit("這一下的判定平移", shift)
        try:
            yield
        finally:
            encounter.resolve_encounter = real

    def refill(self, who: str) -> None:
        self.edit(who, lambda p: setattr(p, "stamina", float(self.c.config.stamina_max)))

    # ── 前半 ──

    def seat(self) -> None:
        at, to = self.pair()
        emit("設伏的那一段路", [at, to])
        mats = sorted(self.c.materials)[:2]

        def purse(p) -> None:
            p.stats["silver"] = 400
            for mid in mats:
                p.materials[mid] = p.materials.get(mid, 0) + 6

        spots = {self.A: at, self.G: at, self.B1: to, self.B2: to, self.B3: to, self.C: self.base_of("guan"), self.D: self.base_of("huang"),
                 self.E: self.hub(), self.F: self.hub()}
        for who, side in self.PLAYERS.items():
            self.place(who, spots[who], side)
            self.edit(who, purse)
        for who in self.PLAYERS:
            self.main(who)
        self.stock_view("坐定")

    def refuse(self) -> None:
        """設不了伏的幾種：散人沒揭通緝（灰著或沒有鈕、硬按寫原因）、城鎮旁邊（硬按）、序章裡不閉關（新人）。"""
        at, to = self.pair()
        self.kinds(self.G, "散人")
        self.choose(self.G, f"ambush:set:{to}")
        town = next((i for i, loc in sorted(self.c.locations.items()) if i not in (at, to) and not loc.prologue_only), self.hub())
        self.place(self.C, town)
        self.kinds(self.C, "城裡")
        self.choose(self.C, f"ambush:set:{to}")
        self.place(self.C, self.base_of("guan"))
        self.kinds(self.NEWBIE, "新人")
        self.do(self.NEWBIE, "seclude", {"hours": 3})
        self.main(self.NEWBIE)

    def stock_off(self) -> None:
        """設定關著（預設）：C 站在自家大本營，沒有屯糧鈕、硬按寫「此刻無法這麼做」。"""
        self.set_stock(False)
        self.kinds(self.C, "屯糧關著")
        self.choose(self.C, "works:stockpile")
        self.stock_view("屯糧關著硬按之後")

    def stock_on(self) -> None:
        """打開之後：官軍 C、黃巾 D 各在自己的大本營屯幾下（官軍多一下）；散人 G 屯不了；在別人的地方屯不了（C 站到黃巾大本營）。"""
        self.set_stock(True)
        for who, n in ((self.C, 3), (self.D, 2)):
            for _ in range(n):
                self.refill(who)
                self.kinds(who, "屯糧開著")
                self.choose(who, "works:stockpile")
            self.me(who, "屯糧之後")
        self.refill(self.G)
        self.choose(self.G, "works:stockpile")
        away = self.base_of("huang")
        if away != self.base_of("guan"):
            self.place(self.C, away)
            self.kinds(self.C, "別人的地方")
            self.choose(self.C, "works:stockpile")
            self.place(self.C, self.base_of("guan"))
        self.stock_view("屯糧之後")

    def ambush_set(self) -> None:
        """A 在路上埋伏（官軍）：選單上的鈕、埋下去（體力、季上與身上各一筆）、再按一次設別段、守著想移動（灰掉、硬按）。**後半才有人走過**。"""
        at, to = self.pair()
        self.refill(self.A)
        self.kinds(self.A, "埋之前")
        self.choose(self.A, f"ambush:set:{to}")
        self.kinds(self.A, "埋了")
        self.choose(self.A, f"ambush:set:{to}")
        self.choose(self.A, f"move:{to}")
        self.me(self.A, "埋了之後")
        self.stock_view("埋了之後")

    def seclude_start(self) -> None:
        """E 閉關十二小時（99 夾成 12；**前半只過去一小時不到**）、閉關中再閉、閉關中想做別的；F 閉關一小時（0 夾成 1）。"""
        self.refill(self.E)
        self.do(self.E, "seclude", {"hours": 99})
        self.me(self.E, "閉關開始")
        self.kinds(self.E, "閉關中")
        self.do(self.E, "seclude", {"hours": 3})
        self.choose(self.E, "act:explore")
        self.do(self.F, "seclude", {"hours": 0})
        self.me(self.F, "閉關開始")

    def half(self) -> None:
        self.me(self.A, "前半最後")
        self.me(self.E, "前半最後")
        self.stock_view("前半最後（埋著、閉關著、兩軍屯著）")

    # ── 後半 ──

    def resume(self) -> None:
        self.set_stock(True)  # 設定是各行程自己的：先開，再登入（登入回的選單就有屯糧鈕）
        self.login_all()
        self.stock_view("後半開頭")

    def ensure_ambush(self) -> None:
        """A 沒有埋伏（被打退、守滿了）就補一個。"""
        at, to = self.pair()
        self.main(self.A)
        state = self.chars.load(self.A)
        if state is not None and state.player.ambush is None:
            self.refill(self.A)
            self.choose(self.A, f"ambush:set:{to}")

    def pass_by(self, who: str, tag: str) -> None:
        """who 從路的另一頭走過 A 站的那一頭（步行），快轉一小時走完，各看一眼。"""
        at, to = self.pair()
        self.place(who, to)
        self.choose(who, f"move:{at}")
        self.do(ADMIN, "fast_forward", {"hours": 1})
        self.main(who)
        self.main(self.A)
        self.me(who, f"走過 {tag}")
        self.me(self.A, f"被走過 {tag}")
        self.stock_view(f"走過 {tag}")

    def hits(self) -> None:
        """自己人（同軍的 C）、散人 G 走過不打；敵對的 B1 自然打、B2 伏兵必勝、B3 伏兵必敗（被打退，埋伏散了）。每一次先補好埋伏。"""
        for who, tag in ((self.C, "自己人"), (self.G, "散人")):
            self.ensure_ambush()
            self.pass_by(who, tag)
        self.ensure_ambush()
        self.pass_by(self.B1, "自然")
        self.ensure_ambush()
        with self.tilt(800.0):
            self.pass_by(self.B2, "伏兵勝")
        self.ensure_ambush()
        with self.tilt(-800.0):
            self.pass_by(self.B3, "伏兵敗")

    def lift_expire(self) -> None:
        """A 埋好之後自己收伏；再埋、守滿三小時沒人來（快轉四小時，自己同步時收起來）。"""
        self.ensure_ambush()
        self.kinds(self.A, "收伏之前")
        self.choose(self.A, "ambush:lift")
        self.kinds(self.A, "收伏之後")
        self.refill(self.A)
        self.ensure_ambush()
        self.do(ADMIN, "fast_forward", {"hours": 4})
        self.main(self.A)
        self.me(self.A, "守滿之後")
        self.stock_view("守滿之後")

    def seclude_end(self) -> None:
        """F 的一小時早滿了（同步時自然出關）；E 還在閉關：提前出關（心得照小時算）；出關之後再閉一次、十二小時快轉走完自然出關。"""
        self.me(self.F, "自然出關之前")
        self.main(self.F)
        self.me(self.F, "自然出關之後")
        self.kinds(self.E, "提前出關之前")
        self.choose(self.E, "act:break")
        self.me(self.E, "提前出關之後")
        self.refill(self.E)
        self.do(self.E, "seclude", {"hours": 2})
        self.do(ADMIN, "fast_forward", {"hours": 3})
        self.main(self.E)
        self.me(self.E, "第二次自然出關之後")

    def muster(self) -> None:
        """照時刻表開集結：兩軍屯的量換成起點的偏移（屯糧那一格；排在起點之後、玉璽之前）、天下大事一句、屯的量清空。
        開季自然開的集結先取消；屯糧關著的對照也看一次（設定關掉、屯的量留著，開集結什麼都不寫）。"""
        ids = self.showdowns()
        emit("時刻表的決戰", ids)
        if self.world.get_battle() is not None and self.world.get_battle().phase != "ended":
            self.cancel("自然開的")
        w = self.world.get_season()
        left = [i for i in ids if i not in w.showdowns_opened and i not in w.timeline]
        emit("開集結之前的屯量", dict(sorted(w.supply.items())))
        if not left:
            return
        self.do(ADMIN, "start_showdown", {"id": left[0]})
        self.stock_view("開集結")
        self.cancel("時刻表")
        self.stock_view("開集結取消之後")

    def bots(self) -> None:
        """假人：BotRunner 四個（路上官軍〔先埋好伏：守著走不開，先收伏〕、路上黃巾、自家大本營的官軍、黃巾；體力滿）若干輪；整季機器人站在大本營眼前的選單與挑法；
        bot_policy.score 對設伏、屯糧、收伏的分數。"""
        from collections import Counter

        from tianxia import bot, bot_policy, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.features.stamina_plays import bots as stamina_bots  # 第二輪第 101 批：_stamina_play 讀那一份；compare 用這個腳本跑兩棵樹，舊樹也有這一檔，兩邊都換
        from tianxia.state import BotProfile

        at, to = self.pair()
        spots = [("guan", at), ("huang", to), ("guan", self.base_of("guan")), ("huang", self.base_of("huang"))]
        on = bool(self.c.scenario.factions)
        for i, name in enumerate(self.BOT_SEATS):
            side, loc = spots[i]
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=71 + i, faction=side if on else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.stats["silver"] = 300
            if i == 0:
                opt = next((o for o in g.options(odds=False) if o.id.startswith("ambush:set:") and o.enabled), None)
                emit("伏甲先埋好", None if opt is None else opt.id)
                if opt is not None:
                    g.choose(opt.id)
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(41), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {71 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        chance = bot_policy.PLAY_CHANCE
        try:
            # 前一段照原樣（體力花不完時才 5% 的機會玩一下）；後一段把機會拉到 1，設伏、屯糧的挑選與守著走不開先收伏才一定走到
            for stage, rounds in (("照原樣", int(os.environ.get("SB_STAMINA_TICKS", "6"))), ("必玩", 8)):
                bot_policy.PLAY_CHANCE = stamina_bots.PLAY_CHANCE = chance if stage == "照原樣" else 1.0
                for _ in range(rounds):
                    STEP[0] += 4
                    self.begin()
                    report = runner.tick()
                    totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            bot_policy.PLAY_CHANCE = stamina_bots.PLAY_CHANCE = chance
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            emit(f"假人 {name}", {"loc": s.player.location, "stamina": s.player.stamina, "silver": s.player.stats.get("silver"),
                                  "ambush": None if s.player.ambush is None else s.player.ambush.model_dump(mode="json"),
                                  "journal": [[e.title, e.tag, list(e.lines)[:3]] for e in s.journal[:5]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.stock_view("假人之後")
        for name, (side, loc) in (("效丙", ("guan", at)), ("效丁", ("guan", self.base_of("guan")))):
            self.begin()
            solo = Game.new(self.c, name, rng=random.Random(7), world=self.world, graduated=True)
            solo.client = None
            solo.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                solo.choose(first)
            p = solo.state.player
            p.bot = BotProfile(personality="普通", seed=99, faction=side if on else None, season_number=self.world.get_season_number())
            p.faction, p.location, p.journey = p.bot.faction, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            opts = solo.options(odds=False)
            mine = [o for o in opts if o.id.startswith(("ambush:", "works:"))]
            emit(f"{name} 眼前的選單", [o.id for o in opts])
            emit(f"{name} 的分數", {o.id: bot_policy.score(solo, o, p.bot) for o in mine})
            emit(f"{name} 整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))
            emit(f"{name} 體力花不完時", [bot_policy._stamina_play(solo, random.Random(k)) for k in range(6)])
            class Prefer(random.Random):  # 擲骰一定過、挑清單時先挑屯糧（有就挑，沒有照第一顆）
                def random(self) -> float:
                    return 0.0

                def choice(self, seq):
                    return next((x for x in seq if x.startswith("works:")), seq[0])

            bot_policy.PLAY_CHANCE = stamina_bots.PLAY_CHANCE = 1.0  # 機會拉到 1：選單上按得下去的設伏、屯糧一顆顆挑（體力用完就不玩了）
            try:
                emit(f"{name} 先挑屯糧", [bot_policy._stamina_play(solo, Prefer(3)) for _ in range(2)])
                played = [bot_policy._stamina_play(solo, random.Random(k)) for k in range(6)]
            finally:
                bot_policy.PLAY_CHANCE = stamina_bots.PLAY_CHANCE = chance
            emit(f"{name} 必玩", played)

    def season(self) -> None:
        self.do(ADMIN, "end_season")
        self.stock_view("收季之後")
        self.me(self.A, "收季之後")
        self.me(self.E, "收季之後")
        self.do(ADMIN, "next_season")
        self.main(self.A)
        self.me(self.A, "換季之後")
        self.me(self.E, "換季之後")
        self.stock_view("換季之後")


# 改一個字（selftest）：收伏那一句（ambush.LIFTED；第 39 批設伏搬進包時規則檔換位置，這裡要多寫包裡的檔）
register_track("stamina", StaminaScenario, (("tianxia/features/stamina_plays/ambush_rules.py", "tianxia/ambush.py"),
                                             ("你收起埋伏，從路邊撤了回來。", "你收起埋伏，從路邊撤了回來！")), "week7")
