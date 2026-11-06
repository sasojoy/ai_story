"""same_behavior 一軌一檔：strip（這一檔登記 strip）。"""
from __future__ import annotations

import hashlib
import os
import random

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, emit, register_track
from sb.tracks.events import EventScenario
from sb.tracks.explore import _explore_rules

# ═══════════════════════════ strip（全部拆包第 13 批「拿掉一」，dev/strip-1）：strip 一軌 ═══════════════════════════
# 探索三選一、找素材「自己說」、城裡操練拿掉（計畫 docs/superpowers/plans/2026-11-04-拿掉一-第13批.md）。這一批不是純搬：week7、season21、test
# 三種設定要一個字都不變，none、weekend 只照拿掉的範圍變。這一軌盯的是「三選一的開關關掉之前還有人在讀」的那幾處（總表第 13 列「先做」）：
# 一類一顆（precise.on）、可重複的事件推大勢的五折、捐軍備推大勢、觀山石（擲中加成與卡上那一句）、討伐懸賞的說法、玩法說明的探索那幾行，
# 活著的小工具（找素材 gather_finds、補料 one_of、領地多給一份的亂數、is_town）、尋敵分級（training 留著的那一半），與舊的 id
# 按下去的回話。名字一律原創（第 22 批認定第 3 條）。


class StripScenario(EventScenario):
    """拿掉一（全部拆包第 13 批；--track strip，自己一個資料庫）。小工具借事件那一軌的（card、press）與探索那一軌的（draws、tweak、settle、
    kind_places、first_event、edit_state）。半舊半新切在 half 之後：三張牌寫到一半——舊程式端出來的事件卡（等回答）、有所感（等選做法）、
    今天按過一次操練（只有不帶設定與 weekend 按得到，存檔留著 drill_day、drills_today）；後半第一件事（answer）是新程式接著答完。"""

    PLAYERS = {"韓墨川": "guan", "蘇映秋": "huang", "杜遠山": None, "程聽雪": None, "裴寒舟": "guan", "顧行之": None, "沈晚舟": None}
    NEWBIE = "阮青禾"
    BOT_SEATS = [("寒甲", "yingshui"), ("寒乙", "yingchuan"), ("寒丙", "julu_altar"), ("寒丁", "guangzong")]
    PHASES_FIRST = ["setup", "howto", "menus", "old_ids", "precise", "push_event", "donate", "stone", "strike", "tiers", "home", "half"]
    PHASES_SECOND = ["resume", "answer", "again", "bots", "season"]

    # ── 小工具 ──

    def game(self, who: str):
        """這個人此刻的 Game（只讀：算完不存，同伺服器每個請求重建）。"""
        from tianxia.engine import Game

        self.begin()
        return Game(self.c, self.chars.load(who), world=self.world)

    def side(self, who: str) -> str | None:
        want = self.PLAYERS.get(who)
        return want if want in {f.id for f in self.c.scenario.factions} else None

    def base_of(self, who: str) -> str | None:
        """這個人陣營的大本營（第一個投靠點）；沒有陣營是 None。"""
        side = self.side(who)
        faction = next((f for f in self.c.scenario.factions if f.id == side), None)
        return faction.join_at[0] if faction is not None and faction.join_at else None

    def field(self) -> str | None:
        """城外、有對手的地方（照 id 排第一處）；這份內容沒有是 None。"""
        from tianxia.engine import Game

        game = Game(self.c, self.chars.load("杜遠山"), world=self.world)
        cfg = self.c.config
        spots = [i for i, x in sorted(self.c.locations.items()) if cfg.explore_mix_of(x.tags).kind != "town" and game._wild_foes(x)]
        return "yingshui" if "yingshui" in spots else spots[0] if spots else None

    def town(self) -> str | None:
        cfg = self.c.config
        spots = [i for i, x in sorted(self.c.locations.items()) if cfg.explore_mix_of(x.tags).kind == "town"]
        return "yingchuan" if "yingchuan" in spots else spots[0] if spots else None

    def look_here(self, who: str, tag: str) -> None:
        """選單、行動列底下那幾行、四格那一格、main.training（尋敵分級開著沒）、輿圖詳情的那一句與分級。"""
        view = self.main(who)
        emit(f"{who} {tag}", {"options": view.get("options"), "notes": view.get("action_notes"), "training": view.get("training"),
                              "mostly": view.get("mostly")})
        game = self.game(who)
        loc = game.content.locations[game.state.player.location]
        emit(f"{who} {tag} 分級與詳情", {"tier": game._practice_tier(loc), "fierce": game._fierce_line(loc), "detail": game.place_detail(loc.id)})

    # ── 前半 ──

    def setup(self) -> None:
        Scenario.setup(self)
        for who in self.PLAYERS:
            self.place(who, None, faction=self.side(who))
        self.begin()

    def howto(self) -> None:
        """玩法說明（探索那幾行、殘譜、有所感的「靜心感悟」、交友的事在哪）：有陣營的與散人各看一次；序章裡的新人也看一次。"""
        for who in ("韓墨川", "杜遠山", self.NEWBIE):
            self.call(who, "GET", "/api/howto")

    def menus(self) -> None:
        """各種地點的選單：地點種類各站一次（有陣營的、散人）。"""
        for kind, loc in self.kind_places():
            for who in ("韓墨川", "杜遠山"):
                self.place(who, loc)
                self.look_here(who, f"在{kind}")

    def old_ids(self) -> None:
        """舊的 id 按下去：三選一的幾顆、分支、自己說、操練（week7、season21、test 本來就不在選單上，照 choose 既有的回法回；
        不帶設定與 weekend 的 base 真的做事，head 同樣照 choose 既有的回法回）。"""
        who = "顧行之"
        for spot in (self.field(), self.town()):
            self.place(who, spot)
            for oid in ("explore:gather", "explore:gather:mine", "explore:gather:say", "explore:seek", "explore:sense", "explore:practice",
                        "explore:", "act:drill"):
                self.place(who, spot)
                self.choose(who, oid)
                self.settle(who)
        self.me(who, "按過舊的 id")

    def me(self, who: str, tag: str) -> None:
        state = self.chars.load(who)
        p = state.player
        latest = state.journal[0] if state.journal else None
        emit(f"{who} {tag}", {
            "stamina": p.stamina, "silver": p.stats.get("silver"), "xinde": p.stats.get("xinde"), "exp": p.member.exp, "level": p.member.level,
            "materials": dict(sorted(p.materials.items())), "explore_seq": p.explore_seq, "drill": [p.drill_day, p.drills_today],
            "pending": state.pending_event, "sensing": p.sensing is not None, "marks": sorted(p.newbie_marks),
            "latest": None if latest is None else latest.model_dump(mode="json"),
        })

    def precise(self) -> None:
        """一類一顆還開著（precise.on 不再看三選一的開關）：交友只談話、拜入門派另成一顆、找事件的併池看得出來的地方（選單、紀錄）。"""
        who = "沈晚舟"
        town = self.town()
        self.place(who, town)
        self.look_here(who, "城裡的交友")
        opts = self.options(who)
        for oid in ("act:socialize", "act:call"):
            if opts.get(oid, {}).get("enabled"):
                self.choose(who, oid)
                self.settle(who)
                break
        self.me(who, "交友之後")
        sect = self.first_event(lambda e: any(ch.effect.join_sect for ch in e.choices) and bool(e.locations))
        if sect is not None:
            self.place(who, self.c.events[sect].locations[0])
            self.look_here(who, "門派所在地")
        game = self.game(who)
        from tianxia import events as event_rules
        from tianxia import precise as precise_rules

        emit("這一季一類一顆", {"on": precise_rules.on(self.c, game.state.world),
                              "explore_common": sorted(e.id for e in event_rules.event_candidates(game.state, self.c, "explore", "common"))[:30],
                              "social_common": sorted(e.id for e in event_rules.event_candidates(game.state, self.c, "socialize", "common"))[:30]})

    def push_event(self) -> None:
        """事件推大勢的五折：可重複的打折、一次性的全額（/api/choose 真的按；另外直接問 _shaped 每一條線、每一種來源的量）。"""
        self.trends("事件之前")
        repeat = self.first_event(lambda e: not e.once and not e.qiyu and any(ch.effect.trend for ch in e.choices))
        once = self.first_event(lambda e: e.once and any(ch.effect.trend for ch in e.choices))
        for who, eid in (("韓墨川", repeat), ("蘇映秋", once)):
            if self.card(who, eid):
                self.press(who, lambda ch: bool(ch.effect.trend), f"{eid} 推大勢那一顆")
                self.settle_choices(who)
                self.trends(f"{eid} 之後")
        game = self.game("韓墨川")
        lines = sorted(game._resisted_lines())
        emit("每一條線的量", {line: {src: list(game._shaped(line, 2.0, src)) for src in ("event", "event_once", "donate", "sortie", "duty")}
                             for line in lines})

    def trends(self, tag: str) -> None:
        s = self.world.get_season()
        emit(f"大勢 {tag}", {"trends": dict(sorted(s.trends.items())), "accum": dict(sorted(s.trend_accum.items()))})

    def donate(self) -> None:
        """捐軍備推大勢（economy.donate_push 也乘事件那一折）：自家大本營按軍需官那一串。沒有陣營的內容寫沒有。"""
        from tianxia import economy

        emit("捐十點推多少", economy.donate_push(self.c, 10))
        who = "裴寒舟"
        base = self.base_of(who)
        if base is None:
            emit("這份內容沒有大本營", None)
            return
        first = next((m for m in sorted(self.c.materials.values(), key=lambda m: (m.tier, m.id)) if economy.donate_points(self.c, m.id) > 0), None)
        if first is None:
            emit("這份內容沒有捐得了的素材", None)
            return
        self.place(who, base)

        def fn(p):
            p.materials[first.id] = 12
        self.edit(who, fn)
        self.trends("捐之前")
        opts = self.options(who)
        if opts.get("act:donate", {}).get("enabled"):
            opts = self.ids(self.choose(who, "act:donate"))
            pick = next((i for i, o in opts.items() if i.startswith("donate:") and o.get("enabled") and i != "donate:back"), None)
            if pick is not None:
                self.choose(who, pick)
            self.choose(who, "donate:back")
        self.trends("捐之後")
        self.me(who, "捐之後")

    def stone(self) -> None:
        """觀山石：卡上那一句、靜心感悟擲中多幾個百分點（寶物表裡沒有它的內容照效果直接換 treasures.amount）、真的戴上看修練頁與探索。"""
        from tianxia import sensing, treasures
        from tianxia.state import Equipment

        who = "程聽雪"
        spot = self.field()
        self.place(who, spot)
        emit("觀山石那一句", treasures.effect_text(self.c, "insight"))
        game = self.game(who)
        loc = game.content.locations[game.state.player.location]
        emit("沒戴的擲中", sensing.rate(game.state, self.c, loc))
        fake = lambda st, ct, key: 1.5 if key == "insight" else 1.0  # noqa: E731
        with self.tweak(treasures, amount=fake):
            emit("戴著的擲中", sensing.rate(game.state, self.c, loc))
        stone = next((g for g in self.c.gear.treasures.values() if g.effect == "insight"), None)
        if stone is None:
            emit("這份內容沒有觀山石", None)
            return

        def fn(p):
            p.treasure = Equipment(id="寶:觀山", slot="treasure", name=stone.name, template=stone.id)
        self.edit(who, fn)
        self.call(who, "GET", "/api/menxia")
        game = self.game(who)
        emit("真的戴著的擲中", {"rate": sensing.rate(game.state, self.c, loc), "weights": game._explore_weights(loc)})

    def strike(self) -> None:
        """討伐懸賞的說法：有陣營的、散人；一類一顆關著的那一支（沒蓋章的舊季）。"""
        from tianxia import bounties
        from tianxia.state import Bounty

        spot = self.field()
        game = self.game("韓墨川")
        squad = next((f.id for f in game._wild_foes(self.c.locations[spot])), None) if spot else None
        if squad is None:
            emit("這份內容沒有討伐得了的", None)
            return
        strike = Bounty(id="b-strike", kind="strike", faction=None, week=1, expires=1e12, silver=20, deeds=1, location=spot, squad=squad)
        scout = Bounty(id="b-scout", kind="scout", faction=None, week=1, expires=1e12, silver=20, deeds=1, location=spot)
        for who in ("韓墨川", "杜遠山"):
            state = self.game(who).state  # Game 上那一份才接著這一季（chars.load 的 world 是空的、沒蓋章）
            emit(f"{who} 討伐怎麼交差", bounties.how(self.c, strike, state))
            emit(f"{who} 打探怎麼交差", bounties.how(self.c, scout, state))
        world = self.world.get_season()
        emit("傳聞的說法", bounties.how(self.c, strike, None, world))
        with self.tweak(self.c.config, precise_actions=False):
            emit("一類一顆關著的說法", {who: bounties.how(self.c, strike, self.game(who).state) for who in ("韓墨川", "杜遠山")})

    def tiers(self) -> None:
        """尋敵分級留著的那一半（training.on、tier_of、TIER_WORDS、PLACE_LINE）：輿圖的舊 API、探索一顆打贏的 field2、新手目標「去做」帶去哪。"""
        who = "杜遠山"
        status, view = self.call(who, "GET", f"/api/map?place={self.field() or ''}")
        emit("輿圖詳情", view.get("detail") if isinstance(view, dict) else status)
        game = self.game(who)
        emit("每一處的分級", {i: game._practice_tier(x) for i, x in sorted(self.c.locations.items())})
        emit("新手目標去哪", {go: game._newbie_go(go) for go in ("practice0", "practice1", "practice2", "bounties", "tavern")})
        emit("新手目標", game.newbie_view())

    def home(self) -> None:
        """領地多給一份（_home_gather 用三選一那一顆亂數的名字「探索|…|領地」）、素材那一拍（gather_finds、one_of）：站自家領地，機會定成必中。"""
        explore_one = _explore_rules()

        who = "韓墨川"
        spot = self.base_of(who) or self.field()
        if spot is None:
            return
        self.place(who, spot)
        game = self.game(who)
        with self.tweak(self.c.config.conquest, gather_bonus_chance=1.0):
            emit("領地多給的", game._home_gather(self.c.locations[spot], []))
        from tianxia import conquest

        block = next((i for i, x in sorted(self.c.locations.items()) if conquest.home(self._at(who, i), self.c)), None)
        emit("自家領地", block)
        for where in filter(None, (block, self.field(), self.town())):
            self.place(who, where)
            with self.tweak(self.c.config.conquest, gather_bonus_chance=1.0), self.draws(explore_one.MATERIAL):
                self.explore(who)
            self.me(who, f"在 {where} 探索之後")
        self.place("沈晚舟", self.field())
        with self.draws(explore_one.ENCOUNTER), self.fights("大勝"):
            self.explore("沈晚舟")
        self.me("沈晚舟", "遭遇打贏之後")

    def _at(self, who: str, loc: str):
        state = self.chars.load(who)
        state.player.location = loc
        return state

    def half(self) -> None:
        """切點：蘇映秋等著回答一張事件卡（舊程式探索端出來的）、裴寒舟等著選有所感的做法、杜遠山今天按過一次操練（不帶設定、weekend）。"""
        explore_one = _explore_rules()

        self.place("蘇映秋", self.field())
        with self.draws(explore_one.EVENT):
            self.seek("蘇映秋")
        self.me("蘇映秋", "切點")
        self.place("裴寒舟", self.field())
        with self.draws(explore_one.INSIGHT):
            self.choose("裴寒舟", "act:explore")
            opts = self.options("裴寒舟")
            if opts.get("explore:sense", {}).get("enabled"):
                self.choose("裴寒舟", "explore:sense")
        self.me("裴寒舟", "切點")
        self.place("杜遠山", self.town())
        opts = self.options("杜遠山")
        if opts.get("act:drill", {}).get("enabled"):
            self.choose("杜遠山", "act:drill")
        self.me("杜遠山", "切點")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def answer(self) -> None:
        for who in ("蘇映秋", "裴寒舟"):
            self.settle(who)
            self.me(who, "答完")
        self.main("杜遠山")
        self.me("杜遠山", "接手之後")

    def again(self) -> None:
        """接手之後再走一遍：說明、選單、舊的 id。"""
        self.howto()
        for who in ("韓墨川", "杜遠山"):
            self.place(who, self.field())
            self.look_here(who, "接手之後")
            self.explore(who)
            self.me(who, "接手之後探索")

    def bots(self) -> None:
        """假人：BotRunner＋bot_policy.take_turn（random.Random(17)，時鐘一輪推四分）四個擺在城外、城裡、兩軍的地方；整季機器人讀的那兩處
        （bot.explore_choice、bot.pick）在真的選單上問一次。"""
        from collections import Counter

        from tianxia import bot, bot_policy, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        sides = [f.id for f in self.c.scenario.factions]
        spare = sorted(self.c.locations)
        names = [name for name, _ in self.BOT_SEATS]
        for i, (name, loc) in enumerate(self.BOT_SEATS):
            loc = loc if loc in self.c.locations else spare[i % len(spare)]
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p = g.state.player
            side = sides[i % len(sides)] if sides else None
            p.bot = BotProfile(personality="普通", seed=61 + i, faction=side, season_number=self.world.get_season_number())
            p.faction, p.location, p.journey = side, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stats["silver"] = 200
            self.chars.save(g.state)
        for name in names:
            self.begin()
            g = Game(self.c, self.chars.load(name), world=self.world)
            opts = g.options(odds=False)
            ids = [o.id for o in opts]
            emit(f"{name} 整季機器人", {"choice": bot.explore_choice(ids), "exp": bot.explore_choice(ids, "exp"),
                                     "pick": bot.pick(g, opts, random.Random(0))})
            emit(f"{name} 假人的分數", {o.id: bot_policy.score(g, o, g.state.player.bot) for o in opts
                                     if o.id.startswith(("act:explore", "act:train", "act:drill", "explore:"))})
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(17), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {61 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_STRIP_TICKS", "30"))):
                STEP[0] += 3
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        states = [s for s in self.chars.all(bots_only=True) if s.player.name in names]
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        emit("假人 紀錄標題", {s.player.name: sorted(Counter(e.title for e in s.journal).items()) for s in states})
        emit("假人 第幾次探索", {s.player.name: s.player.explore_seq for s in states})
        emit("假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})

    def season(self) -> None:
        """收季、開下一季：操練的記號照帶（舊季）、新的一季蓋章（一類一顆、減法季）之後的說明與選單。"""
        self.do(ADMIN, "end_season")
        self.main("杜遠山")
        self.do(ADMIN, "next_season")
        self.me("杜遠山", "換季之後")
        for who in ("杜遠山", "韓墨川"):
            self.look_here(who, "換季之後")
            self.call(who, "GET", "/api/howto")


register_track("strip", StripScenario, (("tianxia/treasures.py",), ("靜心感悟擲中的機會 +", "靜心感悟擲中的機會＋")), "week7")
