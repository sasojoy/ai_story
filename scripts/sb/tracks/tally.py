"""same_behavior 一軌一檔：tally（這一檔登記 tally）。"""
from __future__ import annotations

import random

from sb.harness import ADMIN, CLOCK, STEP, emit, register_track
from sb.tracks.companions import CompanionsScenario

# ═══════════════════════════ 假人殼收尾（全部拆包第 60 批）：--track tally ═══════════════════════════


class TallyScenario(CompanionsScenario):
    """假人的分數與「不按」現有的軌走不到的那幾支一軌（全部拆包第 60 批；--track tally，自己一個資料庫）。借 companions 的 setup、seat 與小工具。
    開工那一筆量過（sys.monitoring 記 bot_policy.score、bot.pick 走到的行與遞進去的 id；54 軌＋三支假人子命令 × season21、week7，計畫第六節）：act: 那一段
    內傷走不動不出陣、守城記功、沒有走一趟時的打探懸賞、接下糧車、應召沒有一軌走到；挑戰本人一直是 None、守勢一直是 0.5、療傷一直是 20、出陣只有 None 與 11.6；
    bot.pick 的排除清單裡 act:rest、act:halt、arena:yield、talk:*、parley:* 這幾種沒有一軌遞進去過；_tavern 打手得手那一支沒有一軌走到。

    這一軌不靠運氣走到：照舊叫公開的 bot_policy.score、bot_policy.pick、bot.pick，每一格直接問；條件用 mock 換掉（dials 那張表）。換的名字兩份程式都叫得到：
    Game 的公開方法、orders、precise、bounties 的模組屬性、bot_policy.wants_heal、鐵匠鋪包的 bots.want；第二輪第 89 批搬走的（_crippled、_cannot_push、_outmatched、_train_value、_bounty_here、injury_share、forge_ready、market_want）
    compare 是拿 head 的腳本跑 base 與 head，舊位置在 head 上打不到讀者：dials 的 moved 把 bot、bot_policy、bot_base、鐵匠鋪與馬市的 bots 裡有這個名字的全部換掉。
    前半切在 half：假人坐在店裡（鐵匠鋪、馬市、酒肆，week7 還有懸賞榜；season21 那一位的選單上沒有亮的 act:bounties），那幾格是舊程式按開、寫進存檔的。後半新程式接手（實跑讀過輸出）：
    - sitting：坐在店裡的選單每一顆的分數、兩種 pick 各挑四次；BotRunner 兩輪之後再看一次（鐵匠鋪、馬市坐著的走出來了，籌丁走進別間；week7 懸賞榜那一位還在揭）。
    - scores：三個位子（官軍在大本營、黃巾在中立地、散人在路上）× 每一格條件 × 全部 act:<子動詞>（含沒有主人的 act:heal、act:on_road、不認得的、帶後綴的）；別人的名牌（profile 不是存檔那一份）；
      season:、nokind 這些落到最後的前綴。挑戰本人 None、1.5、31.5，守勢 0.5、30.5，療傷 None、20、100，探索 None、0.7、1.0、1.3、8.0、17.0，出陣十種值都有。
    - picks：bot.pick 一次只遞一顆（全部前綴），回那一顆是會按、None 是排除：名望不夠的 call:<人物> 排除、夠的不排除；看過的 sect:zz 排除、沒看過的 sect:yy 不排除；凶險的挑戰本人排除，等契機時五五波整張都挑它；
      整張遞進去挑八次（先後與亂數）。
    - tavern_walk：bot_policy._tavern（TAVERN_CHANCE 換成 1）三種局面 × 種子：打聽、查人、問素材，查到過人時打手那一支（「你把銀子推過去」）；沒查過人時打手改打聽；沒錢回 None。
    - machines：大家站回開酒肆的城，BotRunner 八輪。

    **這一軌走不到的**（實跑讀過）：測試內容沒有陣營與店：「走到開…的地方」都是 null、坐店那一段是一般選單、tavern_walk 全是 None、假人不上線（一輪全是 0）、call:<人物> 一直見得到；season21 沒有坐懸賞榜那一位。
    bot.pick 的選邊、投效、結識、開季準備卡、有所感（allied.pick_side、enlist_pick、effect.recruit、growth:、sense:）這一批不動，不在這一軌（整季機器人那幾軌走到）。duel_play 的應戰與同去是 bots --seats duel 走到。"""

    PLAYERS = {"陸少游": "guan", "馮敬亭": "huang", "葛長風": None}
    PREP = "程子安"
    BOT_SEATS = [("籌甲", "guan", "act:smith"), ("籌乙", "huang", "act:market"), ("籌丙", None, "act:bounties"), ("籌丁", "guan", "act:tavern")]
    PHASES_FIRST = ["setup", "seat", "bot_seats", "half"]
    PHASES_SECOND = ["resume", "sitting", "scores", "picks", "tavern_walk", "machines"]
    ROUNDS = 8

    # ── 小工具 ──

    def game_of(self, name: str):
        """照假人程式的做法建一份（鎖裡讀存檔、同步）；這一軌大多只問不存。"""
        from tianxia.engine import Game

        g = Game(self.c, self.chars.load(name), random.Random(STEP[0]), self.world)
        g.client = None
        g.sync(CLOCK[0])
        return g

    @staticmethod
    def safe(fn):
        """問到不認得的 id（例：測試內容沒有的人物）丟例外也照寫：兩份程式要丟一樣的。"""
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            return f"!{type(e).__name__}"

    def act_ids(self) -> list[str]:
        """全部 act:<子動詞>：有主人的那幾格（第 57 批那張表）、沒有主人的 act:heal 與 act:on_road、不認得的、帶後綴的。"""
        fid = next(iter(sorted(self.c.figures)), "nobody")
        return ["act:explore", "act:train", "act:duty", "act:rank2", "act:rank:x", "act:convoy", "act:summons", "act:bounties", "act:smith", "act:market",
                "act:heal", "act:socialize", "act:call", "act:tavern", "act:arena", "act:donate", "act:dadian", "act:rest", "act:halt", "act:part", "act:break",
                "act:silver_donate", "act:mentor", "act:furnace", "act:buy_legend", "act:bribe:x", "act:recruit", "act:recruit:x", f"act:challenge:{fid}",
                "act:on_road", "act:nosuch"]

    def pick_ids(self) -> list[str]:
        """bot.pick 一次遞一顆：每種前綴都有，排除清單上的與長得很像、不該排除的並排。"""
        cid = next(iter(sorted(self.c.characters)), "nobody")
        return [*self.act_ids(), "duel:flee", "duel:a", "arena:yield", "arena:a", "arena:join", "dunwu:own", "dunwu:think", "dunwu:0", "story:x", "story:x:a0", "story:x:later",
                "sect:zz", "sect:yy", "call:back", f"call:{cid}", "fs:x", "opp:x", "talk:clue:x", "talk:opp:x", "talk:say", "talk:plan", "talk:leave", "talk:x", "parley:road", "parley:x",
                "defect:x", "invite:x", "errand:x", "feast:x", "road:x", "tavern:x", "donate:x", "dadian:x", "smith:page:x", "smith:x", "ambush:x", "works:x", "aid:x", "plan:x",
                "legacy:skip", "legacy:x", "hire:x", "seal:x", "bounty:x", "market:x", "move:x", "learn:x", "battle:x", "faction:lean:x", "faction:x", "sense:x", "choice:free", "nokind"]

    def dials(self):
        """一格條件：（名字, [換掉的東西], 這一份存檔另外改的）。每一格新建一份 Game、新開一組 mock。"""
        from types import SimpleNamespace as NS
        from unittest import mock

        from tianxia import bot, bot_policy as bp, bounties, orders, precise
        from tianxia.engine import Game
        from tianxia.features.gear import bots as gear_bots
        from tianxia.features.smithy import bots as smithy_bots

        try:
            from tianxia import bot_base
        except ImportError:  # 第 89 批之前的程式
            bot_base = None

        patch = mock.patch.object
        homes = [m for m in (bot, bp, bot_base, smithy_bots, gear_bots) if m is not None]

        class moved:  # noqa: N801  第 89 批搬走的名字：有這個名字的模組全部換（用法同 mock.patch.object 回的物件）
            def __init__(self, name, **how):
                self.patches = [patch(m, name, **how) for m in homes if hasattr(m, name)]

            def start(self):
                for p in self.patches:
                    p.start()

            def stop(self):
                for p in reversed(self.patches):
                    p.stop()

        def odds(word):
            return patch(Game, "challenge_odds", return_value=word)

        def here(kind):
            return moved("_bounty_here", side_effect=lambda game, k: k == kind)

        def trip(how, **weights):
            return patch(Game, "outing_plan", return_value=NS(weights=weights, how=how))

        def plenty(g):
            g.state.player.materials = {m: 99 for m, x in self.c.materials.items() if x.tier == 1}

        crippled = lambda: moved("_crippled", return_value=True)  # noqa: E731
        return [
            ("照實", [], None),
            ("內傷走不動", [crippled()], None),
            *[(f"勝算 {w}", [odds(w)], None) for w in ("穩勝", "有把握", "五五波", "難分勝負", "凶險", "必敗")],
            ("打擊軍令＋五五波", [patch(orders, "strike_on", return_value=True), odds("五五波")], None),
            ("打擊軍令＋凶險", [patch(orders, "strike_on", return_value=True), odds("凶險")], None),
            ("內傷走不動＋穩勝", [crippled(), odds("穩勝")], None),
            ("沒有走一趟", [patch(Game, "outing_plan", return_value=None)], None),
            ("沒有走一趟＋打探懸賞", [patch(Game, "outing_plan", return_value=None), here("scout")], None),
            ("走一趟多半遇敵", [trip("plain", encounter=3, material=1, event=1), patch(Game, "fatigue_next", return_value=0.5)], None),
            ("走一趟多半遇敵＋內傷走不動", [trip("plain", encounter=3, material=1, event=1), crippled()], None),
            ("走一趟討伐懸賞＋打探懸賞", [trip("bounty", encounter=1), here("scout")], None),
            ("走一趟素材多", [trip("plain", encounter=1, material=2)], None),
            ("走一趟素材多＋背包滿", [trip("plain", encounter=1, material=2)], plenty),
            ("走一趟空的", [trip("plain")], None),
            ("醫館輕傷", [patch(bp, "wants_heal", return_value=True), moved("injury_share", return_value=0.1)], None),
            ("醫館重傷", [patch(bp, "wants_heal", return_value=True), moved("injury_share", return_value=0.9)], None),
            ("交友開口是對話", [patch(Game, "socialize_starts_dialogue", return_value=True)], None),
            ("交友白跑", [patch(Game, "socialize_is_futile", return_value=True)], None),
            ("交友照常", [patch(Game, "socialize_starts_dialogue", return_value=False), patch(Game, "socialize_is_futile", return_value=False)], None),
            ("推不動", [moved("_cannot_push", return_value=True)], None),
            ("推不動＋截糧", [moved("_cannot_push", return_value=True), patch(Game, "duel_on", return_value=True), patch(Game, "duel_convoy_here", return_value=True)], None),
            ("贏面太低", [moved("_outmatched", return_value=True)], None),
            ("出陣能打", [moved("_cannot_push", return_value=False), moved("_outmatched", return_value=False)], None),
            ("軍令記功", [moved("_cannot_push", return_value=False), moved("_outmatched", return_value=False), patch(orders, "win_counts", return_value=True)], None),
            ("守城記功", [moved("_cannot_push", return_value=False), moved("_outmatched", return_value=False), patch(Game, "sortie_mode", return_value="hold"),
                       patch(orders, "duty_counts", return_value=True)], None),
            ("不是守城", [moved("_cannot_push", return_value=False), moved("_outmatched", return_value=False), patch(Game, "sortie_mode", return_value="attack"),
                       patch(orders, "duty_counts", return_value=True)], None),
            ("討伐懸賞", [moved("_cannot_push", return_value=False), moved("_outmatched", return_value=False), here("strike")], None),
            ("一類一顆開", [moved("_cannot_push", return_value=False), moved("_outmatched", return_value=False), patch(precise, "on", return_value=True)], None),
            ("一類一顆關", [moved("_cannot_push", return_value=False), moved("_outmatched", return_value=False), patch(precise, "on", return_value=False)], None),
            ("大勢分", [moved("_cannot_push", return_value=False), moved("_outmatched", return_value=False), moved("_train_value", return_value=2.5)], None),
            ("守勢記功", [patch(orders, "duty_counts", return_value=True), patch(Game, "duel_on", return_value=False)], None),
            ("守勢記功＋約戰開著", [patch(orders, "duty_counts", return_value=True), patch(Game, "duel_on", return_value=True)], None),
            ("鐵匠有事", [patch(smithy_bots, "want", return_value="smith:repair")], None),
            ("鐵匠有事＋爐開得成", [patch(smithy_bots, "want", return_value="smith:repair"), moved("forge_ready", return_value=True)], None),
            ("鐵匠沒事＋爐開得成", [patch(smithy_bots, "want", return_value=None), moved("forge_ready", return_value=True)], None),
            ("馬市有事", [moved("market_want", return_value="market:buy")], None),
            ("馬市沒事", [moved("market_want", return_value=None)], None),
            ("榜上交得出", [patch(bounties, "give_choice", return_value=("a", "b"))], None),
            ("榜上沒事", [patch(bounties, "give_choice", return_value=None), patch(bounties, "open_bounties", return_value=[])], None),
        ]

    def view_seat(self, name: str, tag: str) -> None:
        """這個人此刻的選單：每一顆亮不亮、分數；兩種 pick 各挑四次。"""
        from tianxia import bot, bot_policy as bp

        self.begin()
        g = self.game_of(name)
        profile = g.state.player.bot
        options = g.options(odds=False, tick=False)
        enabled = [o for o in options if o.enabled]
        emit(f"{name} {tag}：選單", [[o.id, o.enabled, self.safe(lambda o=o: bp.score(g, o, profile))] for o in options])
        emit(f"{name} {tag}：bot.pick", [self.safe(lambda i=i: bot.pick(g, options, random.Random(i))) for i in range(4)])
        emit(f"{name} {tag}：bot_policy.pick", [self.safe(lambda i=i: bp.pick(g, enabled, profile, random.Random(i))) for i in range(4)])

    # ── 情境 ──

    def bot_seats(self) -> None:
        """四個假人：照 bot_runner._add_bot 的先後（建好就標成假人），序章與開季準備卡按掉，站好、銀兩補夠（打不打得開店看選單）。"""
        from tianxia import bot
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        self.do(ADMIN, "cancel_battle")  # 開季那一場決戰（season21、week7 的長社之火）的集結與開打會接管選單，店按不開
        sides = {f.id: f for f in self.c.scenario.factions}
        season = self.world.get_season_number()
        for i, (name, side, _) in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            side = side if side in sides else None
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=91 + i, faction=side, season_number=season)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(8):
                ids = [o.id for o in g.options(odds=False) if o.enabled]
                step = next((x for x in ids if x.startswith("choice:") and x != "choice:free"), None)
                if step is None and any(x.startswith("growth:") for x in ids):
                    step = f"growth:{bot.growth_key(g)}"
                if step is None and "legacy:skip" in ids:
                    step = "legacy:skip"
                if step is None:
                    break
                g.choose(step)
            p.faction, p.journey = side, None
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.stats["silver"] = 5000
            self.chars.save(g.state)

    @staticmethod
    def stand_up(p) -> None:
        p.picking_smith = p.picking_market = p.picking_bounty = p.picking_tavern = False

    def spot_for(self, name: str, press: str) -> str | None:
        """照地點名排第一個這顆亮著的地方（拿一份不存的 Game 換地點問選單；後半接手時他可能還坐在店裡，選單照站著的算）。"""
        g = self.game_of(name)
        self.stand_up(g.state.player)
        for loc in sorted(self.c.locations):
            g.state.player.location, g.state.player.journey = loc, None
            if press in {o.id for o in g.options(odds=False, tick=False) if o.enabled}:
                return loc
        return None

    def tavern_town(self) -> str:
        return self.spot_for(self.BOT_SEATS[3][0], "act:tavern") or sorted(self.c.locations)[0]

    def half(self) -> None:
        """前半切在這裡：四個假人坐在店裡（picking_smith、picking_market、picking_bounty、picking_tavern），那幾格是舊程式按開、寫進存檔的。"""
        for name, _, press in self.BOT_SEATS:
            self.begin()
            spot = self.spot_for(name, press)
            emit(f"{name} 走到開 {press} 的地方", spot)
            if spot is None:  # 測試內容沒有的店
                continue
            self.place(name, spot)
            with self.world.action_lock():
                g = self.game_of(name)
                emit(f"{name} 按 {press}", g.choose(press))
                self.chars.save(g.state)

    def resume(self) -> None:
        self.login_all()

    def sitting(self) -> None:
        """舊程式按開的店：每一顆的分數、兩種 pick；BotRunner 兩輪，新程式替他們按（走 Feature.bot_pick 那幾支）。"""
        for name, _, _ in self.BOT_SEATS:
            self.view_seat(name, "坐在店裡")
        self.bot_rounds(2)
        for name, _, _ in self.BOT_SEATS:
            self.view_seat(name, "兩輪之後")

    def scores(self) -> None:
        """三個位子 × 每一格條件 × 全部 act:<子動詞>；官軍站大本營、黃巾站中立地、散人站路上（這一格只讀，不存）。"""
        from tianxia import bot_policy as bp
        from tianxia.core.option import Option
        from tianxia.state import BotProfile

        sides = {f.id: f for f in self.c.scenario.factions}
        home = sides["guan"].join_at[0] if "guan" in sides and sides["guan"].join_at else None
        spots = [("籌甲", home), ("籌乙", "runan_wilds"), ("籌丙", "nanyang_road")]
        for name, loc in spots:
            self.place(name, loc)
            self.edit(name, self.stand_up)
            self.begin()
            for tag, patches, tweak in self.dials():
                g = self.game_of(name)
                if tweak is not None:
                    tweak(g)
                profile = g.state.player.bot
                for p in patches:
                    p.start()
                try:
                    row = {i: self.safe(lambda i=i: bp.score(g, Option(id=i, label=""), profile)) for i in self.act_ids()}
                finally:
                    for p in reversed(patches):
                        p.stop()
                emit(f"{name} 分數 {tag}", row)
            g = self.game_of(name)
            stranger = BotProfile(personality="普通", seed=1, faction="huang" if "huang" in sides else None)
            emit(f"{name} 分數 別人的名牌", {i: self.safe(lambda i=i: bp.score(g, Option(id=i, label=""), stranger)) for i in self.act_ids()})
            others = {i: self.safe(lambda i=i: bp.score(g, Option(id=i, label=""), g.state.player.bot)) for i in (*self.pick_ids(), "season:paused", "growth:x")}
            emit(f"{name} 分數 別的前綴", others)
            options = [Option(id=i, label="") for i in self.act_ids()]
            emit(f"{name} bot_policy.pick 整張", [self.safe(lambda i=i: bp.pick(g, options, g.state.player.bot, random.Random(i))) for i in range(8)])

    def picks(self) -> None:
        """bot.pick 一次只遞一顆：回那一顆是會按、None 是排除。名望夠不夠（call:）、看過沒（sect:zz 看過、sect:yy 沒有）、挑戰本人的勝算與等契機；整張遞進去挑八次（先後與亂數）。"""
        from unittest import mock

        from tianxia import bot
        from tianxia.core.option import Option
        from tianxia.engine import Game

        def one(g) -> dict:
            return {i: self.safe(lambda i=i: bot.pick(g, [Option(id=i, label="")], random.Random(0))) for i in self.pick_ids()}

        def seen(g) -> None:
            g.state.player.seen_events.add("zz")

        def famous(g) -> None:
            g.state.player.stats["fame"] = 10 ** 6
            g.state.player.seen_events.add("zz")

        for name in ("籌甲", "籌丙"):
            self.begin()
            for tag, tweak, odds, chance in (("照實", seen, "凶險", False), ("名望夠", famous, "穩勝", False), ("等契機＋五五波", seen, "五五波", True), ("等契機＋凶險", seen, "凶險", True)):
                g = self.game_of(name)
                tweak(g)
                with mock.patch.object(Game, "challenge_odds", return_value=odds), mock.patch.object(bot, "awaits_chance", return_value=chance):
                    emit(f"{name} 一次一顆 {tag}", one(g))
                    full = [Option(id=i, label="") for i in self.pick_ids()]
                    emit(f"{name} 整張挑 {tag}", [self.safe(lambda i=i: bot.pick(g, full, random.Random(i))) for i in range(8)])

    def tavern_walk(self) -> None:
        """bot_policy._tavern（TAVERN_CHANCE 換成 1，照舊是 bot_policy 的模組屬性）：站在開酒肆的城，三種局面（查到過那三位真人、沒查過人、沒錢）。問到什麼、扣多少、走不走得出來；只問不存。"""
        from unittest import mock

        from tianxia import bot_policy as bp

        name = self.BOT_SEATS[3][0]
        town = self.tavern_town()
        emit("開酒肆的城", town)
        for tag, silver, known, seeds in (("查到過人", 10 ** 5, list(self.PLAYERS), 30), ("沒查過人", 10 ** 5, [], 30), ("沒錢", 0, list(self.PLAYERS), 3)):
            for seed in range(seeds):
                self.begin()
                with self.world.action_lock():
                    g = self.game_of(name)
                    p = g.state.player
                    self.stand_up(p)
                    p.location, p.journey = town, None
                    p.stats["silver"] = silver
                    p.tavern_known = list(known)
                    with mock.patch.object(bp, "TAVERN_CHANCE", 1.0):
                        got = self.safe(lambda seed=seed: bp._tavern(g, random.Random(seed)))
                    emit(f"{name} 酒肆 {tag} 種子 {seed}", {"got": got, "silver": p.stats["silver"], "open": p.picking_tavern})

    def bot_rounds(self, rounds: int) -> None:
        """BotRunner 跑幾輪（四位一定在線；同 reckon 的 bot_rounds）。"""
        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner

        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(53 + rounds), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {91 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        try:
            for _ in range(rounds):
                STEP[0] += 3
                self.begin()
                report = runner.tick()
                emit("假人一輪", [report.acted, report.added, report.skipped, report.failed])
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online

    def machines(self) -> None:
        """假人碰得到：大家站回開酒肆的城，BotRunner 再跑幾輪；每個人最後在哪、哪一間店還開著、最新三則紀錄。"""
        town = self.tavern_town()
        for name, _, _ in self.BOT_SEATS:
            self.place(name, town)
        self.bot_rounds(self.ROUNDS)
        for name, _, _ in self.BOT_SEATS:
            state = self.chars.load(name)
            p = state.player
            emit(f"{name} 幾輪之後", {"at": p.location, "shops": [p.picking_smith, p.picking_market, p.picking_bounty, p.picking_tavern],
                                 "journal": [e.title for e in state.journal[:3]]})
            self.view_seat(name, "幾輪之後")
        self.season_view("假人之後")


# 改一個字（selftest）：守勢行動替守城記功的那一道分（第 60 批第 2 段從 bot_policy.score 搬進出陣包的 bots.py，那一句照寫，兩處找）。
register_track("tally", TallyScenario, (("tianxia/bot_policy.py", "tianxia/features/sortie/bots.py"), ("if counts else 0.0", "if not counts else 0.0")), "season21")
