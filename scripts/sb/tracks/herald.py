"""same_behavior 一軌一檔：herald（這一檔登記 herald）。"""
from __future__ import annotations

import contextlib
import hashlib
import os
import random

from sb.base import Scenario, _three_way_off
from sb.harness import ADMIN, CLOCK, STEP, emit, register_track
from sb.tracks.explore import ExploreScenario, _explore_rules

# ═══════════════════════════ herald：事件機制一軌（全部拆包第 26 批，dev/core-eventbus-1） ═══════════════════════════
# 事件機制（核心批）：一包發生的事、別包跟著動——懸賞交差的四種（打贏一場、探索一趟、抵達某地、截殺打贏）與玉璽的兩種（決戰收場、
# 集結開始）。計畫 docs/superpowers/plans/2026-11-06-事件機制-第26批.md。這一段整塊是這一批的：接在檔尾、最後一行登記（register_track），
# PM 合的時候不跟別人的行穿插。角色的名字都是原創的（PM 11/04）。懸賞單直接寫進季上的榜（HD_PREFIX 開頭、揭的人寫好），玉璽碎片用管理者工具
# （指定持有者、強制璽動、強制現世〔領地爭奪的季是現在藏一片〕），其餘只打公開的 API 按下去。

HD_PREFIX = "hd_"


class HeraldScenario(ExploreScenario):
    """事件機制一軌（全部拆包第 26 批；--track herald，自己一個資料庫）。每一種事件都擺到「有人聽、聽的人真的動了」的那一刻：
    打贏一場（出陣／遊歷打贏、出門一趟的遭遇打贏，手上揭著那裡的討伐）、探索一趟（出門一趟收尾：手上揭著那裡的打探、那一塊藏著一片碎片——
    同一下兩個訂閱者；測試內容走舊探索）、舊探索（有陣營的季在記憶體裡關掉探索一顆、揭著那裡的另一張打探按一次）、抵達某地（押著糧車、揭著到那裡的護送——同一下兩個訂閱者）、截殺打贏（揭著通緝他的懸賞）、
    集結開始（手上有碎片的人、管理者強制璽動：開標了璽動、這一季還沒打過的那一場，開集結那一刻璽動）、決戰收場（那一場璽動過、持有者還拿著那一片）。
    **前半停在三件寫到一半的事**：時刻表決戰集結到一半（璽動過、兩軍各有人加入）；押著糧車又揭著護送的人走在路上還沒到；揭了討伐還沒打。
    後半：新程式接著走到、打贏、決戰開打到收場；假人（BotRunner 兩個揭著自己那裡的討伐與打探）；收季、開下一季。
    沒有陣營、玉璽、地盤的（測試內容）同一串 API 照打，寫「沒有」。"""

    WINNER, LONE, SCOUT, CARRY, RAIDER, PREY = "甘望岳", "嚴暮帆", "祁梧聲", "尹照川", "邵臨江", "喬聽松"
    HOLDER, FOE, LATE, LATE2 = "杭遠汀", "柏寒溪", "溫若谷", "鄔淺川"
    PLAYERS = {WINNER: "guan", LONE: None, SCOUT: "guan", CARRY: "guan", RAIDER: "huang", PREY: "guan",
               HOLDER: "guan", FOE: "huang", LATE: "guan", LATE2: "guan"}
    NEWBIE = "初來乍到"
    BOT_SEATS = ["傳甲", "傳乙"]
    PHASES_FIRST = ["setup", "seat", "win", "outing", "arrive", "raid", "muster", "half"]
    PHASES_SECOND = ["resume", "deliver", "aftermath", "bots", "season"]

    # ── 小工具 ──

    def factions_on(self) -> bool:
        return any(f.id == "huang" for f in self.c.scenario.factions) and any(f.id == "guan" for f in self.c.scenario.factions)

    def side(self, who: str) -> str | None:
        return self.PLAYERS.get(who) if self.factions_on() else None

    def hub(self) -> str:
        return self.c.scenario.start_location

    def wild_spot(self) -> str | None:
        """出門一趟打得到有陣營的對手的地方（照 id 排第一個；每一個野怪都是官軍或黃巾的優先）：遭遇打贏才交得了討伐。"""
        g = self.game(self.LONE)
        best = None
        for loc_id, loc in sorted(self.c.locations.items()):
            if self.c.config.explore_mix_of(loc.tags).kind == "town":  # precise.is_town（develop 的 precise 沒有這一個名字）
                continue
            foes = list(g._wild_foes(loc))
            sides = [f.faction for f in foes]
            if foes and all(s in ("guan", "huang") for s in sides):
                return loc_id
            if best is None and any(s in ("guan", "huang") for s in sides):
                best = loc_id
        return best

    def strike_spot(self, who: str) -> str | None:
        """出陣攻得到黃巾的兵的地方（敵方的陣營區塊打控制方的兵；中立地的駐軍、流寇沒有陣營，交不了討伐）：照 id 排第一個、出陣是「攻」、
        對手全是黃巾的。出陣關著的季（測試內容）回一個這份內容沒有的地點，place 照舊換成遊歷打得到人的地方。"""
        from tianxia import territory

        if not territory.on(self.c) or not self.factions_on():
            return "runan_wilds"
        from tianxia.engine import Game

        with self.world.action_lock():
            state = self.chars.load(who)  # 只在記憶體裡換地點問（不寫回：去過的地方不多記）
        for lid in sorted(self.c.locations):
            state.player.location = lid
            g, loc = Game(self.c, state, world=self.world), self.c.locations[lid]
            foes = g._sortie_foes(loc)
            if g._sortie_mode(loc) == "attack" and foes and all(f in self.c.squads and self.c.squads[f].faction == "huang" for f in foes):
                emit(f"{who} 出陣打得到黃巾的地方", [lid, foes])
                return lid
        emit(f"{who} 出陣打得到黃巾的地方", None)
        return None

    def game(self, who: str):
        from tianxia.engine import Game

        with self.world.action_lock():
            state = self.chars.load(who)
        return Game(self.c, state, world=self.world)

    def post(self, *bounties) -> None:
        """懸賞單直接寫進季上的榜（揭的人已經寫好）。"""
        def fn(s) -> None:
            s.bounties[:] = [b for b in s.bounties if b.id not in {x.id for x in bounties}] + list(bounties)

        self.world.mutate_season(fn)
        emit("掛上的懸賞", [[b.id, b.kind, b.faction, b.location, b.end, b.target, list(b.takers)] for b in bounties])

    def bounty(self, bid: str, kind: str, who: str, faction: str | None, **kw):
        from tianxia.state import Bounty

        far = self.world.get_season().time + 30 * 86400.0
        return Bounty(id=f"{HD_PREFIX}{bid}", kind=kind, faction=faction, week=1, expires=far, silver=20, deeds=1, takers=[who], **kw)

    def me(self, who: str, tag: str) -> None:
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "loc": p.location, "journey": None if p.journey is None else p.journey.model_dump(mode="json"), "faction": p.faction,
            "convoy": None if p.convoy is None else p.convoy.model_dump(mode="json"), "donations": dict(sorted(p.donations.items())),
            "contrib": p.contrib, "silver": p.stats.get("silver", 0), "done": p.bounties_done, "deeds": getattr(p, "deeds", None),
            "seal_seen": p.seal_seen, "card": state.battle_card,
            "battles": [[r.kind, r.tier, r.changes, r.notes] for r in state.battles[:2]],
            "journal": [[e.title, e.tag, list(e.lines)[:8]] for e in state.journal[:3]]})

    def world_view(self, tag: str) -> None:
        w = self.world.get_season()
        view = self.world.seal_state()
        reg = view.registry
        b = self.world.get_battle()
        emit(f"世界 {tag}", {
            "bounties": [[x.id, list(x.takers), list(x.done_by)] for x in w.bounties if x.id.startswith(HD_PREFIX)],
            "shards": {k: [v.state, v.holder, v.stirred_season] for k, v in sorted(reg.shards.items())},
            "cache": None if reg.cache is None else reg.cache.model_dump(mode="json"),
            "force": [reg.force_emerge, reg.force_stir], "last": [reg.last_showdown, reg.last_showdown_dueled],
            "battle": None if b is None else [b.battle_id, b.phase, b.round_number, b.seal_shard, b.seal_holder, b.seal_emerge,
                                               b.outcome_title, sorted(b.participants)],
            "rumors": [r.text for r in w.rumors][-6:], "chronicle": [r.text for r in w.chronicle][-3:]})

    def fight_here(self, who: str) -> None:
        """出陣（約戰關著；打完照設定還原，不然整段跑的行程後面都關著、後半新開的行程開著）／舊遊歷，這一下照寫好的打贏。"""
        self.set_duel(False)
        try:
            view = self.main(who)
            emit(f"{who} 的 act:train", self.ids(view).get("act:train"))
            with self.winning():
                self.choose(who, "act:train")
        finally:
            self.set_duel(True)

    @contextlib.contextmanager
    def raid_wins(self):
        """截殺這一下發起的人一定打贏：判定照算、亂數照用，只把發起的人的威力放大（resolve_encounter 換掉，兩份程式同一步換、同一步換回）。"""
        from tianxia import encounter

        real = encounter.resolve_encounter

        def forced(our, difficulty, rng, *a, **k):
            return real(our * 100 + 10 ** 4, difficulty, rng, *a, **k)

        encounter.resolve_encounter = forced
        try:
            yield
        finally:
            encounter.resolve_encounter = real

    def step_to(self, who: str) -> str | None:
        move = next((i for i, o in self.ids(self.main(who)).items() if i.startswith("move:") and o.get("enabled")), None)
        emit(f"{who} 走的那一步", move)
        return move

    def wait_arrive(self, who: str, rounds: int = 40) -> None:
        n = 0
        while n < rounds and self.chars.load(who).player.journey is not None:
            STEP[0] += 5
            self.main(who)
            n += 1
        emit(f"{who} 同步了 {n} 次抵達", self.chars.load(who).player.location)

    def load_convoy(self, who: str, dest: str) -> None:
        from tianxia.state import Convoy

        here = self.chars.load(who).player.location
        self.edit(who, lambda p: setattr(p, "convoy", Convoy(order=f"{HD_PREFIX}escort", grain=3, from_loc=here, to_loc=dest)))
        self.post(self.bounty(f"escort_{who}", "escort", who, self.side(who), location=here, end=dest))

    def showdown(self) -> str | None:
        """時刻表上標了璽動（seal: stir）、這一季還沒打過的第一場（season21 的長社火攻開季沒多久就照時刻表自己打掉了，改開下一場）。"""
        done = self.world.get_season().timeline
        return next((e.id for e in self.c.timetable if e.seal == "stir" and e.id in self.c.battles and e.id not in done), None)

    def spot(self, battle_id: str) -> str | None:
        from tianxia import atlas

        definition = self.c.battles.get(battle_id)
        if definition is None or definition.region is None:
            return None
        spots = sorted(i for i in self.c.locations if (r := atlas.region_of(self.c, i)) is not None and r.id == definition.region)
        return "changshe" if "changshe" in spots else (spots[0] if spots else None)

    def join(self, who: str) -> None:
        ids = self.ids(self.main(who))
        live = sorted(i for i, o in ids.items() if i.startswith(("battle:join:", "battle:enlist:")) and o.get("enabled"))
        want = f"battle:join:{self.side(who)}"
        pick = next((i for i in live if i.split("@")[0] == want), live[0] if live else None)
        emit(f"{who} 集結時按的", pick)
        if pick is not None:
            self.choose(who, pick)
            if "battle:escort:none" in self.ids(self.main(who)):
                self.choose(who, "battle:escort:none")

    def seal_live(self) -> bool:
        from tianxia import seal

        return seal.on(self.c) and self.factions_on()

    # ── 前半 ──

    def setup(self) -> None:
        Scenario.setup(self)  # 不接 ExploreScenario.setup（那一軌擺的人這一軌沒有）；借它的只有小工具（draws、fights、tweak、explore）

    def seat(self) -> None:
        for who in self.PLAYERS:
            self.place(who, self.hub(), self.side(who))
            self.edit(who, lambda p: p.stats.update({"silver": 200}))
        for who in self.PLAYERS:
            self.main(who)
        self.world_view("坐定")

    def win(self) -> None:
        """打贏一場（兩個發布點）：出陣／舊遊歷打贏（核心的單打服務）、出門一趟的遭遇打贏（探索包）；兩個人手上都揭著那裡的討伐。"""
        loc = self.strike_spot(self.WINNER)
        if self.place(self.WINNER, loc):
            here = self.chars.load(self.WINNER).player.location
            self.post(self.bounty(f"strike_{self.WINNER}", "strike", self.WINNER, self.side(self.WINNER) or "guan", location=here))
            self.fight_here(self.WINNER)
            self.me(self.WINNER, "打贏之後")
        spot = self.wild_spot()
        emit("出門一趟打得到有陣營對手的地方", spot)
        if spot is not None and self.place(self.LONE, spot):
            explore_one = _explore_rules()
            self.post(*[self.bounty(f"strike_{self.LONE}_{f}", "strike", self.LONE, f, location=spot) for f in ("guan", "huang")])
            with self.draws(explore_one.ENCOUNTER), self.fights("大勝"):
                self.explore(self.LONE)
            self.me(self.LONE, "遭遇打贏之後")
        self.world_view("打贏之後")

    def outing(self) -> None:
        """探索一趟：手上揭著那裡的打探；領地爭奪的季管理者先藏一片碎片、站到藏處（撿到的機會這一下定成必中）——同一下兩個訂閱者。
        測試內容（沒有探索一顆）走舊探索。"""
        from tianxia import seal

        hidden = None
        if seal.on(self.c) and seal.conquest_season(self.c, self.world.get_season()):
            self.do(ADMIN, "seal_emerge", {"id": ""})
            cache = self.world.seal_state().registry.cache
            hidden = cache.loc if cache is not None else None
        emit("藏著碎片的地方", hidden)
        where = hidden or self.wild_spot() or self.hub()
        if not self.place(self.SCOUT, where):
            return
        where = self.chars.load(self.SCOUT).player.location
        self.post(self.bounty(f"scout_{self.SCOUT}", "scout", self.SCOUT, self.side(self.SCOUT) or "guan", location=where))
        explore_one = _explore_rules()
        with self.tweak(self.c.config.seal.cache, find_chance=1.0), self.draws(explore_one.MATERIAL):
            self.explore(self.SCOUT)
        self.me(self.SCOUT, "探索之後")
        self.world_view("探索之後")
        self.old_explore()

    def old_explore(self) -> None:
        """舊探索（事件 explore；修正輪補的：審查發現沒有一軌走到舊探索「聽的人真的動了」，_BUS_CORE 那一格漏了也比不出來）：
        有陣營的季探索一顆開著、act:explore 是出門一趟，這一下在記憶體裡關掉探索一顆（兩份程式同一步關、同一步開），祁梧聲揭著
        這裡的另一張打探、按一次舊探索——打探交差。測試內容上面那一下就是舊探索（沒有陣營、懸賞榜關著：叫到、沒人動），不再按。"""
        if not self.factions_on():
            emit("舊探索：這份內容上面那一下就是", None)
            return
        where = self.chars.load(self.SCOUT).player.location
        self.post(self.bounty(f"scout_old_{self.SCOUT}", "scout", self.SCOUT, self.side(self.SCOUT) or "guan", location=where))
        with self.tweak(self.c.config.jianfa, explore_one=False), _three_way_off(self.c.config):
            self.explore(self.SCOUT)
        self.me(self.SCOUT, "舊探索之後")
        self.world_view("舊探索之後")

    def arrive(self) -> None:
        """抵達某地：押著糧車（終點）、揭著到那裡的護送，走一步到（先交糧車、再交護送：同一下兩個訂閱者）。"""
        self.place(self.CARRY, self.hub())
        move = self.step_to(self.CARRY)
        if move is None:
            return
        self.load_convoy(self.CARRY, move.split(":")[1])
        self.me(self.CARRY, "出發之前")
        self.choose(self.CARRY, move)
        self.wait_arrive(self.CARRY)
        self.me(self.CARRY, "抵達之後")
        self.world_view("抵達之後")

    def raid(self) -> None:
        """截殺打贏：黃巾的人揭著通緝官軍那一位的懸賞，在城外截殺他（這一下一定打贏）。"""
        spot = self.wild_spot()
        if spot is None:
            emit("截殺：這份內容沒有城外的地方", None)
            return
        self.place(self.PREY, spot)
        self.place(self.RAIDER, spot)
        self.post(self.bounty(f"wanted_{self.PREY}", "wanted", self.RAIDER, self.side(self.RAIDER), poster="（對照）掛單人", target=self.PREY))
        self.main(self.PREY)
        emit(f"{self.RAIDER} 看 {self.PREY} 的玩家卡", self.call(self.RAIDER, "GET", f"/api/peer?name={self.PREY}")[1])
        with self.raid_wins():
            self.call(self.RAIDER, "POST", "/api/peer/act", {"name": self.PREY, "action": "raid"})
        self.me(self.RAIDER, "截殺之後")
        self.me(self.PREY, "被截殺之後")
        self.world_view("截殺之後")

    def muster(self) -> None:
        """集結開始：管理者把一片碎片記到杭遠汀名下、強制璽動，開標了璽動的時刻表決戰；兩軍各一人加入。"""
        which = self.showdown() if self.seal_live() else None
        emit("開哪一場", which)
        if which is None:
            emit("集結：這份內容沒有玉璽或那一場", None)
            return
        shard = sorted(self.c.seal)[0]
        self.do(ADMIN, "seal_assign", {"id": shard, "name": self.HOLDER, "state": "held"})
        self.do(ADMIN, "seal_stir", {"id": shard})
        self.do(ADMIN, "start_showdown", {"id": which})
        self.world_view("開集結之後")
        spot = self.spot(which)
        for who in (self.HOLDER, self.FOE):
            self.place(who, spot)
            self.join(who)
        self.me(self.HOLDER, "集結中")
        self.world_view("集結中")

    def half(self) -> None:
        """前半停在三件寫到一半的事：集結到一半（muster 段）；溫若谷押著糧車又揭著護送、走在路上；鄔淺川揭了討伐還沒打。"""
        self.place(self.LATE, self.hub())
        move = self.step_to(self.LATE)
        if move is not None:
            self.load_convoy(self.LATE, move.split(":")[1])
            self.choose(self.LATE, move)
        loc = self.strike_spot(self.LATE2)
        if self.place(self.LATE2, loc):
            here = self.chars.load(self.LATE2).player.location
            self.post(self.bounty(f"strike_{self.LATE2}", "strike", self.LATE2, self.side(self.LATE2) or "guan", location=here))
        for who in (self.LATE, self.LATE2):
            self.me(who, "前半停在這裡")
        self.world_view("前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()
        for who in (self.LATE, self.LATE2, self.HOLDER):
            self.main(who)

    def deliver(self) -> None:
        """新程式接著走到（糧車與護送）、打贏（討伐）。"""
        self.wait_arrive(self.LATE)
        self.me(self.LATE, "接手抵達之後")
        if self.chars.load(self.LATE2) is not None:
            self.fight_here(self.LATE2)
            self.me(self.LATE2, "接手打贏之後")
        self.world_view("接手之後")

    def aftermath(self) -> None:
        """決戰收場：時鐘一段一段往前推、持有者每一下同步，直到那一場收場（回合逾時照代為固守）。"""
        b = self.world.get_battle()
        if not self.seal_live() or b is None or b.phase == "ended":
            emit("收場：沒有還沒收的那一場", None)
            return
        n = 0
        while n < 80:
            b = self.world.get_battle()
            if b is None or b.phase == "ended":
                break
            STEP[0] += 15
            self.main(self.HOLDER)
            n += 1
        emit("推了幾下到收場", n)
        for who in (self.HOLDER, self.FOE):
            self.main(who)
            self.me(who, "收場之後")
        self.world_view("收場之後")

    def bots(self) -> None:
        """假人：BotRunner 兩個（官軍，站在城外、揭著那裡的討伐與打探）若干輪。"""
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        spot = self.wild_spot() or self.hub()
        on = self.factions_on()
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=61 + i, faction="guan" if on else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, spot, None
            p.visited.add(spot)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            self.chars.save(g.state)
            self.post(self.bounty(f"bot_strike_{i}", "strike", name, p.faction or "guan", location=spot),
                      self.bounty(f"bot_scout_{i}", "scout", name, p.faction or "guan", location=spot))
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(41), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {61 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_HERALD_TICKS", "8"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            emit(f"假人 {name}", {"loc": s.player.location, "done": s.player.bounties_done,
                                  "journal": [[e.title, list(e.lines)[:4]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.world_view("假人之後")

    def season(self) -> None:
        self.do(ADMIN, "end_season")
        self.world_view("收季之後")
        self.do(ADMIN, "next_season")
        self.main(self.WINNER)
        self.me(self.WINNER, "換季之後")


# 改一個字（selftest）：懸賞交差那一句（bounties._complete；第 45 批懸賞榜成包時那一行搬進包，這裡要多寫包裡的檔）
register_track("herald", HeraldScenario, (("tianxia/features/bounties/rules.py", "tianxia/bounties.py"), ("」交差了，", "」交差了！")), "week7")
