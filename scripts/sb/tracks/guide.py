"""same_behavior 一軌一檔：guide（這一檔登記 guide）。"""
from __future__ import annotations

import hashlib
import os
import random

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, emit, register_track

# ═══════════════════════════ guide：新手引導一軌（全部拆包第 22 批，dev/guide-1） ═══════════════════════════
# 引導框、碰到才說、新手目標、開局第一分鐘、入伍段的本體從 engine.py 搬進新包 tianxia/features/guide/（tianxia/guide.py、hints.py、
# newbie.py、opening.py、enlist.py；計畫 docs/superpowers/plans/2026-11-01-新手引導包-第1批.md）。


class GuideScenario(Scenario):
    """新手引導（全部拆包第 22 批；--track guide，自己一個資料庫）。六個網頁上建的新角色（/api/character：Game.new(prologue=True)）——
    葉孤城從開局走：week7、season21 是城門口三選一（還沒選就簽到被擋那一句、選了之後人物的信與護送委託、收起信）；不帶與 weekend 是草廬
    （一步一步看框：遇險、拜師、看修練頁、四景、裝意境、練到第三成、揣摩、服丹，**前半停在這裡**，後半雪恥、配點、熔煉、出師、
    初入江湖的頭幾步、/api/prologue 重看序章）；測試內容是說書人三步（探索、去湖邊、看地圖）與結語「知道了」。
    江小魚碰到才說：擺出狀態（兩個意境、點數沒配、看過事件）一次觸發一串，一條一條上框、按「知道了」（前半最後一條上框沒按），
    後半再擺內傷＋眼前一則事件（排著不上框）、療好再同步（排著的拿掉）、交友（事件型的）。
    花無缺新手目標：就當散人（第一條，**切在這裡**），後半升到第 5 級（第二條）。燕南天、鐵心蘭入伍段：投靠、看軍令卡（**前半停在第一道
    軍令**），後半燕南天照選單發光的那一顆出一次力、按掉結尾；鐵心蘭一週沒做完被收。蘇櫻：不再提示、看地圖、看修練頁（序章外）、
    重看序章，後半略過新手引導（草廬裡略過拿出師的盤纏）、再按一次、打開提示、知道了。假人：Game.new(graduated=True)（草廬的季走
    _graduate、開局的季站在城門口挑一顆；標成假人才同步，第一位交友一次）＋BotRunner 三十輪。最後收季、開下一季（開季那一句 s_return、
    再投靠的 s_rejoin）。
    沒有開局、草廬、陣營、入伍段、提示的設定寫「沒有」略過，同一串 API 照打。"""

    WALKER, ENLIST, LATE, HINTS, GOALS, SKIP = "葉孤城", "燕南天", "鐵心蘭", "江小魚", "花無缺", "蘇櫻"
    BOT_SEATS = ["引甲", "引乙", "引丙"]
    PHASES_FIRST = ["setup", "gate", "hut", "hints", "goals", "enlist", "skip", "half"]
    PHASES_SECOND = ["resume", "hut_on", "hints_on", "goals_on", "enlist_on", "skip_on", "bots", "season"]

    def everyone(self) -> list[str]:
        return [self.WALKER, self.ENLIST, self.LATE, self.HINTS, self.GOALS, self.SKIP]

    # ── 小工具 ──

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            fn(state)
            self.chars.save(state)

    def me(self, who: str, tag: str) -> None:
        """存檔裡引導碰得到的那幾格：步數、所在、眼前的事件、完成列、結語、略過、入伍段、提示（說過、排著、關了沒）、新手目標的兩本帳、
        丹與銀兩、陣營、旗標、信、最新三則紀錄（標題、標記、引導那幾行）。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "step": p.tutorial_step, "loc": p.location, "journey": p.journey is not None, "pending": state.pending_event,
            "done": list(p.guide_done), "outro": p.guide_outro, "skipped": p.guide_skipped,
            "enlist": [p.enlist_step, p.enlist_end, p.enlist_since], "seen": sorted(p.hints_seen),
            "queue": [[n.id, n.speaker, n.text, n.shown] for n in p.hint_queue], "off": p.hints_off,
            "newbie": [sorted(p.newbie_marks), sorted(p.newbie_done)], "pills": p.stamina_pills, "silver": p.stats.get("silver", 0),
            "faction": p.faction, "flags": sorted(p.flags), "letters": [x.model_dump(mode="json") for x in p.letters],
            "journal": [[e.title, e.tag, list(e.guide)] for e in state.journal[:3]]})

    @staticmethod
    def view_of(view) -> dict:
        """GET /api/main 回的是畫面本身，POST 的動作回 {main, message}：兩種都拿到畫面。"""
        return (view.get("main", view) or {}) if isinstance(view, dict) else {}

    def in_hut(self, who: str) -> bool:
        return bool(self.view_of(self.main(who)).get("prologue"))

    def past(self, who: str) -> None:
        """引導走完（不是略過）：草廬的季直接擺到起點、步數擺到走完（草廬那幾步是葉孤城的事）；開局的季選掉城門口三選一；
        測試內容擺到走完。"""
        steps, start = len(self.c.tutorial.steps), self.c.scenario.start_location
        if self.in_hut(who):
            def fn(s) -> None:
                s.pending_event, s.player.sensing, s.player.journey = None, None, None
                s.player.location = start
                s.player.visited.add(start)
                s.player.tutorial_step = steps
            self.edit_state(who, fn)
        else:
            self.settle_choices(who)
            self.edit_state(who, lambda s: setattr(s.player, "tutorial_step", max(s.player.tutorial_step, steps)))
        self.me(who, "引導走完")

    def arrive(self, who: str, rounds: int = 40) -> None:
        """在路上的話一直同步到抵達（每一步推一分鐘）。"""
        n = 0
        while n < rounds and self.chars.load(who).player.journey is not None:
            self.main(who)
            n += 1
        emit(f"{who} 同步了 {n} 次抵達", self.chars.load(who).player.location)

    def ack(self, who: str, rounds: int, tag: str) -> None:
        """同步一次（排一條、上框）、按「知道了」，照 rounds 次。"""
        for k in range(rounds):
            self.main(who)
            self.me(who, f"{tag} 第 {k + 1} 條")
            self.do(who, "guide_ack")

    def sides(self) -> list:
        return [f for f in self.c.scenario.factions if f.join_at] if self.c.tutorial.enlist is not None else []

    def join(self, who: str, faction) -> None:
        self.place(who, faction.join_at[0])
        self.choose(who, f"faction:{faction.id}")
        self.choose(who, "faction:confirm")
        self.settle_choices(who)
        self.me(who, f"投靠 {faction.id} 之後")

    # ── 前半 ──

    def setup(self) -> None:
        from tianxia.accounts import AccountStore
        from tianxia.engine import Game

        store = AccountStore(self.world.db)
        self.passwords[ADMIN] = "pw-admin-123456"
        with self.world.db.transaction():
            store.register(self.login_of(ADMIN), self.passwords[ADMIN])
            game = Game.new(self.c, ADMIN, world=self.world)
            self.chars.save(game.state)
            store.bind_character(self.login_of(ADMIN), ADMIN)
        self.clients[ADMIN] = self.TestClient(self.server.app)
        self.call(ADMIN, "POST", "/api/login", {"login": self.login_of(ADMIN), "password": self.passwords[ADMIN]})
        self.do(ADMIN, "open_season")
        for who in self.everyone():
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                    "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
            self.me(who, "建好")

    def gate(self) -> None:
        """開局第一分鐘：三選一還沒選就簽到（opening.GATE）、選第二顆（那位人物的信到、附一件護送委託）、收起信。"""
        who = self.WALKER
        o = self.c.opening
        if o is None or self.chars.load(who).pending_event != o.event:
            emit("這一季沒有開局第一分鐘", None)
            return
        self.do(who, "checkin")
        self.choose(who, "choice:1")
        self.me(who, "選完三選一")
        for letter in self.chars.load(who).player.letters:
            self.do(who, "letter_read", {"id": letter.id})
        self.me(who, "收起信")

    def hut(self) -> None:
        """草廬前七步（照 Scenario.prologue，全走 API；每一下回的 /api/main 帶著框）；測試內容是說書人第一步（探索）。"""
        from tianxia.features.sense import sensing

        who = self.WALKER
        if not self.in_hut(who):
            if self.c.tutorial.location is None and self.chars.load(who).player.tutorial_step < len(self.c.tutorial.steps):
                self.choose(who, "act:explore")
                self.settle_choices(who)
                self.me(who, "說書人第一步之後")
            else:
                emit("這一季沒有草廬", None)
            return
        self.choose(who, "choice:0")
        self.choose(who, "choice:0")
        self.do(who, "view_tab", {"tab": "practice"})
        self.choose(who, "act:explore")
        senses = [i for i, o in self.ids(self.main(who)).items() if i.startswith("sense:") and i != sensing.LET_GO and o.get("enabled")]
        if senses:
            self.choose(who, senses[0])
        self.choose(who, sensing.LET_GO)
        self.me(who, "四景之後")
        got = [i for i in self.chars.load(who).player.insights if i in ("feng", "shan", "shui", "huo")]
        if got:
            self.call(who, "POST", "/api/menxia/slot", {"art": "jichu_quanjiao", "insight": got[0]})
            self.call(who, "POST", "/api/menxia/practice", {"kind": "武學"})
            self.call(who, "POST", "/api/menxia/practice", {"kind": "武學"})
            self.call(who, "POST", "/api/menxia/forge", {"insights": [got[0], f"{got[0]}~2"]})
        self.do(who, "pill")
        self.me(who, "服丹之後")

    def hints(self) -> None:
        """碰到才說：引導走完的江小魚擺出兩個意境（h_merge）、兩點沒配（h_points）、看過一則事件（h_event_reveal）——一次同步排一條、
        上框，按「知道了」換下一條；三條之後再同步一次，最後一條上了框沒按（前半停在這裡）。"""
        who = self.HINTS
        self.past(who)
        insights = [i for i, x in self.c.insights.items()][:2]
        event = next((e for e in sorted(self.c.events) if not e.startswith(("prologue", "opening"))), None)

        def fn(p) -> None:
            p.insights.extend(i for i in insights if i not in p.insights)
            p.stat_points = 2
            p.stats["xinde"] = 999  # 心得夠自創第一門（h_create）
            if event is not None:
                p.events_seen.append(event)
        self.edit(who, fn)
        self.ack(who, 3, "提示")
        self.main(who)
        self.me(who, "上了框還沒按")

    def goals(self) -> None:
        """新手目標：引導走完、新手期裡的花無缺按任務卡的「就當散人」（side 那一條：回體丹）。前半停在這裡（八條做了一條）。"""
        who = self.GOALS
        self.past(who)
        self.do(who, "newbie_drifter")
        self.me(who, "就當散人之後")

    def enlist(self) -> None:
        """入伍段：燕南天投靠第一軍、鐵心蘭投靠第二軍（引薦人迎進營）、看過軍令卡（第一步做完）；前半停在第一道軍令。"""
        sides = self.sides()
        if len(sides) < 2:
            emit("這份內容沒有陣營或入伍段", None)
            return
        for who, faction in ((self.ENLIST, sides[0]), (self.LATE, sides[1])):
            self.past(who)
            self.join(who, faction)
            self.do(who, "view_orders")
            self.me(who, "看過軍令卡")

    def skip(self) -> None:
        """設定頁的幾樣：不再提示、看地圖、看修練頁（序章外：只記旗標）、不認得的分頁、重看序章。"""
        who = self.SKIP
        self.do(who, "hints_off", {"value": True})
        self.do(who, "view_map")
        self.do(who, "view_tab", {"tab": "practice"})
        self.do(who, "view_tab", {"tab": "nope"})
        self.call(who, "GET", "/api/prologue")
        self.me(who, "設定頁之後")

    def half(self) -> None:
        for who in self.everyone():
            self.me(who, "前半停下")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def hut_on(self) -> None:
        """草廬後四步：雪恥、配點、熔蠻牛拳、出師（去潁川、一路同步到抵達）；初入江湖的頭幾步（療傷、操練、看地圖）；重看序章。
        測試內容：去湖邊（第二步）、看地圖（第三步）、結語按「知道了」。開局的季寫「沒有」。一開頭在鎖裡直接叫一次調息（rest_direct）。"""
        who = self.WALKER
        self.rest_direct(who)
        if self.in_hut(who):
            self.choose(who, "act:train")
            self.do(who, "allocate", {"stat": "str"})
            self.call(who, "POST", "/api/menxia/melt", {"art": "manniu_quan"})
            self.me(who, "熔煉之後")
            self.choose(who, "move:yingchuan")
            self.arrive(who)
            opts = self.ids(self.main(who))
            for oid in ("act:heal", "act:drill"):
                if opts.get(oid, {}).get("enabled"):
                    self.choose(who, oid)
                    self.settle_choices(who)
            self.do(who, "view_map")
            self.me(who, "初入江湖")
            self.call(who, "GET", "/api/prologue")
        elif self.c.tutorial.location is None and "move:lake" in self.ids(self.main(who)):
            self.choose(who, "move:lake")
            self.arrive(who)
            self.do(who, "view_map")
            self.me(who, "說書人走完")
            self.do(who, "guide_ack")
            self.me(who, "結語按掉")
        else:
            emit("這一季沒有草廬", None)

    def hints_on(self) -> None:
        """新程式接手前半那一條（按掉）、接著排的再按四條；擺內傷＋眼前一則事件（h_injury 排著、事件擋著不上框）、療好、清掉事件再同步
        （排著還沒上框、條件不成立的拿掉）；交友一次（事件型的碰到才說）。"""
        from tianxia import prologue

        who = self.HINTS
        self.do(who, "guide_ack")
        towns = [i for i, loc in sorted(self.c.locations.items()) if "酒肆" in (loc.tags or []) and i not in prologue.onboard_towns(self.c)]
        if towns:
            self.place(who, towns[-1])  # 第一次到有酒肆的城（h_tavern；老周教過酒肆的那幾城不算）
        self.ack(who, 4, "新程式的提示")
        event = next((e for e in sorted(self.c.events) if not e.startswith(("prologue", "opening")) and self.c.events[e].choices), None)

        def hurt(s) -> None:
            s.player.member.injury = 1
            s.pending_event = event
        self.edit_state(who, hurt)
        self.main(who)
        self.me(who, "內傷排著、事件擋著")

        def heal(s) -> None:
            s.player.member.injury = 0
            s.pending_event = None
        self.edit_state(who, heal)
        self.main(who)
        self.me(who, "療好之後")
        self.do(who, "guide_ack")
        if self.ids(self.main(who)).get("act:socialize", {}).get("enabled"):
            self.choose(who, "act:socialize")
            for _ in range(3):
                opts = self.ids(self.main(who))
                if "talk:leave" in opts:
                    self.choose(who, "talk:leave")
                elif any(i.startswith("choice:") for i in opts):
                    self.settle_choices(who)
                else:
                    break
        self.me(who, "交友之後")

    def goals_on(self) -> None:
        """新程式接手：升到第 5 級（level5 那一條：同步時發）、再按一次就當散人（記過了，什麼都不發）。"""
        who = self.GOALS
        self.edit(who, lambda p: setattr(p.member, "level", 5))
        self.main(who)
        self.me(who, "升到第 5 級之後")
        self.do(who, "newbie_drifter")
        self.me(who, "再按一次就當散人")

    def enlist_on(self) -> None:
        """新程式接手入伍段：燕南天照選單上發光的第一顆出一次力（沒有發光的照守勢、遊歷），按掉結尾；鐵心蘭的第一道軍令擺成一週前
        開始的（enlist.expire：引薦人照樣說結語）、按掉。"""
        if len(self.sides()) < 2:
            emit("這份內容沒有陣營或入伍段", None)
            return
        who = self.ENLIST
        self.place(who, None)
        view = self.main(who)
        glow = (self.view_of(view).get("guide") or {}).get("glow") or []
        emit(f"{who} 發光的", glow)
        opts = self.ids(view)
        press = next((i for i in [*glow, "act:duty", "act:train"] if opts.get(i, {}).get("enabled")), None)
        if press is not None:
            with self.winning():
                self.choose(who, press)
            self.settle_choices(who)
        self.me(who, "出一次力之後")
        self.do(who, "guide_ack")
        self.me(who, "結尾按掉")
        late = self.LATE
        self.edit(late, lambda p: setattr(p, "enlist_since", -1.0e9))
        self.main(late)
        self.me(late, "一週沒做完")
        self.do(late, "guide_ack")
        self.me(late, "結語按掉")

    def rest_direct(self, who: str) -> None:
        """act:rest 背後的 _rest（序章教體力那一步的調息）：正式內容的草廬已經沒有那一步，選單上不會有這一顆（序章裡選單只給這一步的
        動作，草廬外 choose 先擋「此刻無法這麼做」），公開的路走不到——在鎖裡直接叫，不存（同酒肆一軌在鎖裡直接叫 _depart，第 11 批
        PM 認定第 5 條）。在草廬裡：眼前這一步暫時寫成「一坐就回滿」（TutorialStep.instant_rest，叫完就拿掉）、體力擺到 0，叫一次（回滿、
        說那一句）；接著不寫，再叫一次（打坐已經拿掉那一句）。"""
        from tianxia import prologue
        from tianxia.engine import Game

        with self.world.action_lock():
            state = self.chars.load(who)
            step = prologue.step(state, self.c)
            if step is not None:
                g = Game(self.c, state, random.Random(0), self.world)
                g.state.player.stamina = 0.0
                step.instant_rest = "（調息：一坐就回滿。）"
                try:
                    emit(f"{who} 直接叫調息（這一步一坐就回滿）", [g._rest(), g.state.player.stamina])
                finally:
                    step.instant_rest = ""
            emit(f"{who} 直接叫調息", Game(self.c, self.chars.load(who), random.Random(0), self.world)._rest())

    def skip_on(self) -> None:
        """略過新手引導（草廬裡略過：站到起點、出師的盤纏；入伍段也算走完）、再按一次（沒有好略過的）、打開提示、知道了。"""
        who = self.SKIP
        self.do(who, "skip_tutorial")
        self.me(who, "略過之後")
        self.do(who, "skip_tutorial")
        self.do(who, "hints_off", {"value": False})
        self.main(who)
        self.do(who, "guide_ack")
        self.me(who, "打開提示之後")

    def bots(self) -> None:
        """伺服器假人：Game.new(graduated=True)（內容有草廬的走 _graduate：真的走一遍草廬；開局的季站在城門口，挑第一顆）三個，
        BotRunner＋bot_policy.take_turn 三十輪（random.Random(13)、時鐘一輪推四步）。假人的新手目標照拿、提示不排；整季機器人在城門口挑哪一顆
        也寫下來。照 bot_runner._add_bot 的先後：建好就標成假人（BotProfile、陣營、季數），才同步——先同步的話那一下排的狀態提示沒被
        「假人不排」擋住，佇列裡一直排著一條，之後的檢查走不到假人那道擋（審查 dev/guide-1 第 1 條）。第一位另外交友一次（_act 交友之後
        叫 _hint("h_bond")：事件型的碰到才說，只有 hints.queue_note 擋假人）。"""
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
            p.bot = BotProfile(personality="普通", seed=61 + i, faction=sides[i % len(sides)] if sides else None,
                               season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            if i == 0:
                emit("整季機器人在開局挑", bot.pick(g, g.options(odds=False), random.Random(0)))
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            if i == 0:
                self.bot_socialize(g, name)
            p.stats["silver"] = 200
            self.chars.save(g.state)
            emit(f"假人 {name} 建好", {"step": p.tutorial_step, "loc": p.location, "newbie": sorted(p.newbie_done),
                                     "queue": [n.id for n in p.hint_queue], "journal": [e.title for e in g.state.journal[:4]]})
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(13), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {61 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_GUIDE_TICKS", "30"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("引導假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"引導假人 {name}", {"step": p.tutorial_step, "faction": p.faction, "enlist": [p.enlist_step, p.enlist_end],
                                    "newbie": [sorted(p.newbie_marks), sorted(p.newbie_done)], "seen": sorted(p.hints_seen),
                                    "queue": [n.id for n in p.hint_queue], "guide": p.guide_done,
                                    "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})

    def bot_socialize(self, g, name: str) -> None:
        """假人交友一次（不經伺服器：假人只走 Game 的公開行動）：站到江小魚交友的那一城（有酒肆、老周沒教過的最後一城，同 hints_on），
        交友、告辭或了結接著的事件，寫下說過與排著的提示（假人兩樣都該是空的）。"""
        from tianxia import prologue

        p = g.state.player
        towns = [i for i, loc in sorted(self.c.locations.items()) if "酒肆" in (loc.tags or []) and i not in prologue.onboard_towns(self.c)]
        if towns:
            p.location = towns[-1]
            p.visited.add(towns[-1])
        on = {o.id for o in g.options(odds=False) if o.enabled}
        if "act:socialize" in on:
            emit(f"假人 {name} 交友", g.choose("act:socialize"))
        elif "act:call" in on:  # 探索三選一的季（不帶、weekend）：交友是打開求見名單，挑第一位見得到的（_open_dialogue 也叫 h_bond）
            g.choose("act:call")
            first = next((o.id for o in g.options(odds=False) if o.id.startswith("call:") and o.enabled), None)
            emit(f"假人 {name} 求見", [first, g.choose(first) if first is not None else None])
        else:
            emit(f"假人 {name} 此地不能交友", [p.location, sorted(on)])
            return
        for _ in range(3):
            opts = [o.id for o in g.options(odds=False) if o.enabled]
            if "talk:leave" in opts:
                g.choose("talk:leave")
            elif any(i.startswith("choice:") for i in opts):
                g.choose(next(i for i in opts if i.startswith("choice:")))
            else:
                break
        emit(f"假人 {name} 交友之後", {"seen": sorted(p.hints_seen), "queue": [n.id for n in p.hint_queue],
                                    "journal": [e.title for e in g.state.journal[:2]]})

    def season(self) -> None:
        """收季、開下一季：每個人換季之後的引導（做完的步數、略過、入伍段走完、說過的提示、新手目標照帶；開季那一句 s_return）；
        燕南天再投靠同一邊（入伍段早就走完：引薦人打個招呼 s_rejoin），兩句都按掉。"""
        self.do(ADMIN, "end_season")
        self.main(self.WALKER)
        self.do(ADMIN, "next_season")
        for who in self.everyone():
            self.main(who)
            self.me(who, "換季之後")
        self.do(self.HINTS, "guide_ack")
        self.me(self.HINTS, "開季那一句按掉")
        sides = self.sides()
        if sides:
            self.join(self.ENLIST, sides[0])
            for k in range(3):  # 開季那一句、碰到的人物、再投靠的招呼（照排的順序一條一條上框）
                self.do(self.ENLIST, "guide_ack")
                self.me(self.ENLIST, f"換季之後按掉第 {k + 1} 條")


# 改一個字（selftest）：任務卡「就當散人」那一句（newbie.DRIFTER_LINE；搬之前在 tianxia/newbie.py、之後在包裡）
register_track("guide", GuideScenario, (("tianxia/features/guide/newbie.py",),
                                         ("就當個散人，天下照樣走得。", "就當個散人，天下照樣走得！")), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "hire", "legacy", "looks", "mall", "map",
                       "military", "notify", "outlets", "peers", "persona", "seal", "seclusion", "sense", "smithy", "socialize",
                       "sortie", "stamina_plays", "story", "tale", "tavern", "territory_acts", "travel", "zhuan"))
