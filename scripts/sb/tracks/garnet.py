"""same_behavior 一軌一檔：garnet（這一檔登記 garnet）。"""
from __future__ import annotations

import random

from sb.harness import ADMIN, CLOCK, STEP, emit, register_track
from sb.tracks.carve import CarveScenario

# ═══════════════════════════ garnet：玉璽三軌（全部拆包第 51 批「玉璽三」，dev/seal-3） ═══════════════════════════
# 玉璽二軌（carve）走到七種獨門行動的起用與碎片卡，但起用之後的「效果」沒有一處寫進輸出：頒詔多幾分的感悟、衝絕學的倍數、承露的體力與療傷、
# 傳檄的推力倍數、收心的情誼倍數、鎮地的那一塊（誰都推不動、那一天不回）、引將釘住的人物與期滿回原處（期滿那一句天下大事）。
# 這一軌專走這些璽效查詢：七片各起用一次，每一次之後把共用規則層的查詢（edict_sense、edict_cultivate、dew_factor、dew_clinic、writ_factor、
# heart_open、warmer、held、held_during、pinned、next_end、region_of、ends）照季上現在的樣子問一遍寫進輸出；
# **半舊半新切在引將、鎮地、承露都生效中、還沒期滿的那一刻**（舊程式起用、新程式接著問、快轉到期滿）；
# 後半：快轉過引將的期滿（回原處、天下大事一句）、鎮地期滿、換季前的終點；假人（BotRunner）在生效中的季裡跑幾輪（人物活起來、走動問 pinned）。
# 角色與名字都是原創的（PM 11/04）。


class GarnetScenario(CarveScenario):
    """玉璽三軌（--track garnet，自己一個資料庫）。借 carve 的設定（碎片卡、card_of）與 relic 的 setup、seat。"""

    PHASES_FIRST = ["setup", "seat", "shards", "queries", "half"]
    PHASES_SECOND = ["resume", "queries_again", "bots_walk", "advance", "last"]
    KINDS = ("yinjiang", "chenglu", "chuanxi", "shouxin", "banzhao", "zhendi", "bujue")

    def shard_of_kind(self, kind: str) -> str:
        return next(k for k in sorted(self.c.seal) if getattr(self.c.seal[k], "act", None) == kind)

    def query_state(self):
        """帶著現在這一季的世界的玩家存檔（問承露的體力與療傷要 GameState）。"""
        state = self.chars.load(self.WORKER)
        state.world = self.world.get_season()
        return state

    def shards(self) -> None:
        """七片各由藺秋禾拿一次（管理者指定），照碎片卡上第一個能選的目標與第一軍起用；起用之後收回（一人一片）。"""
        for kind in self.KINDS:
            shard = self.shard_of_kind(kind)
            self.do(ADMIN, "seal_assign", {"id": shard, "name": self.WORKER, "state": "held"})
            act = self.card_of(self.WORKER).get("act") or {}
            rows = act.get("targets") or []
            free = [r for r in rows if not r.get("why")]
            row = (free[-1] if kind == "yinjiang" else free[0]) if free else None  # 引將挑最後一位：時刻表不動他，期滿才回原處
            sides = act.get("sides") or []
            side = (sides[0].get("id", "") if isinstance(sides[0], dict) else str(sides[0])) if sides else ""
            target = row.get("id", "") if row else ""
            emit(f"起用前 {kind}", [shard, act.get("ok"), act.get("why"), target, side, len(rows)])
            self.do(self.WORKER, "seal_use", {"target": target, "side": side})
            self.do(ADMIN, "seal_assign", {"id": shard, "name": "", "state": "hidden"})
            STEP[0] += 2

    def queries(self) -> None:
        self.garnet_queries("起用之後")

    def garnet_queries(self, tag: str) -> None:
        """共用規則層的璽效查詢，照季上現在生效的每一筆問一遍。"""
        from tianxia import conquest, figures, seal_acts

        c, w = self.c, self.world.get_season()
        state = self.query_state()
        acts = [[a.kind, a.target, a.side, a.place, a.origin, round(a.start, 1), round(a.until, 1), a.ended, round(seal_acts.ends(a), 1)]
                for a in w.seal_acts]
        lines = [a.target for a in w.seal_acts if a.kind == "chuanxi"]
        sides = [f.id for f in c.scenario.factions] if getattr(c.scenario, "factions", None) else []
        locs = [a.target for a in w.seal_acts if a.kind in ("zhendi", "bujue")]
        folks = [a.target for a in w.seal_acts if a.kind in ("shouxin", "yinjiang")]
        emit(f"璽效 {tag}", {
            "on": seal_acts.on(c), "now": round(w.time, 1), "acts": acts, "next_end": seal_acts.next_end(w),
            "sense": seal_acts.edict_sense(w, c), "cultivate": seal_acts.edict_cultivate(w, c),
            "dew": [round(seal_acts.dew_factor(state, c, s), 4) for s in (0.0, 600.0, 3600.0, 86400.0)],
            "clinic": seal_acts.dew_clinic(state, c), "region": seal_acts.region_of(c, state.player.location),
            "writ": {f"{ln}/{sd}": [seal_acts.writ_factor(w, c, ln, sd), seal_acts.writ_factor(w, c, ln, sd, 1.0),
                                    seal_acts.writ_factor(w, c, ln, sd, -1.0)] for ln in lines for sd in sides},
            "heart": {f: [seal_acts.heart_open(w, c, f), seal_acts.warmer(w, c, f, 4), seal_acts.warmer(w, c, f, -3)] for f in folks},
            "held": {loc: [None if (a := seal_acts.held(w, c, loc, sd)) is None else round(seal_acts.ends(a), 1)
                           for sd in (None, *sides)] for loc in locs},
            "held_why": {loc: conquest._held_why(w, c, loc) for loc in locs},  # noqa: SLF001  conquest 問的那一句
            "held_during": {loc: [seal_acts.held_during(w, c, loc, w.time - 100, w.time + 100),
                                  seal_acts.held_during(w, c, loc, w.time + 10 ** 9, w.time + 10 ** 9 + 1)] for loc in locs},
            "pinned": {f: seal_acts.pinned(w, f) is not None for f in folks},
            "figure_at": {f: figures.state_of(state, c, f).location for f in folks},
            "rumors": [r.text for r in w.rumors][-4:], "chronicle": [r.text for r in w.chronicle][-3:]})

    def half(self) -> None:
        self.card_of(self.WORKER)
        self.relic_me(self.WORKER, "前半停在這裡（引將、鎮地、承露都還生效中）")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()
        self.card_of(self.WORKER)

    def queries_again(self) -> None:
        self.garnet_queries("新程式接手")

    def bots_walk(self) -> None:
        """假人（BotRunner）在生效中的季裡跑幾輪：人物活起來的走動、跟隨、趕往都問 pinned；假人自己不起用碎片。"""
        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        season = self.world.get_season_number()
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=91 + i, faction="guan" if i == 0 else "huang", season_number=season)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, self.hub(), None
            p.visited.add(self.hub())
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(47), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {91, 92}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        try:
            for _ in range(3):
                STEP[0] += 3
                self.begin()
                report = runner.tick()
                emit("假人一輪", [report.acted, report.added, report.skipped, report.failed])
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        self.garnet_queries("假人跑過之後")

    def advance(self) -> None:
        """快轉過去：每半日一段，引將期滿回原處（天下大勢一句）、鎮地期滿、承露期滿；每段之後問一遍。"""
        for n in range(8):
            self.do(ADMIN, "fast_forward", {"hours": 12})
            self.garnet_queries(f"快轉第 {n + 1} 段")

    def last(self) -> None:
        self.relic_me(self.WORKER, "最後")
        self.relic_view("最後")
        self.call(ADMIN, "GET", "/api/admin")


# 改一個字（selftest）：引將期滿回原處那一句天下大事（seal_acts 的 BACK，進共用規則層之後還在 tianxia/seal_acts.py），advance 那幾段抓到
register_track("garnet", GarnetScenario, (("tianxia/seal_acts.py",), ("坐鎮期滿，回到了{place}。", "坐鎮期滿，回到了{place}！")), "week7")
