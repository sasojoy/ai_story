"""same_behavior 一軌一檔：oath（這一檔登記 oath）。"""
from __future__ import annotations

import os
import random

from sb.harness import CLOCK, STEP, emit, register_track
from sb.tracks.peers import PeersScenario

# ── jieyi（結義，Joy 2026-11-09 PR #195；開關 Config.jieyi.enabled 預設關）：測試流程優化第 113 批 ──────────────


class OathScenario(PeersScenario):
    """結義的一軌（測試流程優化第 113 批；--track oath，自己一個資料庫）。借 peers 一軌的小工具（act、reply、card_of、edit_state、begin 清榜單快取）。班底的名字都是原創（PM 11/04）。
    關著段（三種設定的 Config.jieyi.enabled 都關著）：柳拂衣看杜衡舟的玩家卡（沒有結義那一顆）、照樣送 /api/peer/act jieyi ask、打 /api/do/jieyi_leave，讀 /api/main 的 jieyi 鍵。
    換帖段（還關著）：六個人定稿名帖，柳拂衣跟其餘五位互換（遞帖、卡上回帖）；石不語不換。
    開著段（記憶體裡打開開關，兩個行程都開）：沒換帖的被拒、提起、再提（等他回話）、對方卡上的「他邀你結義」、選單上答應（開義）、婉拒、第三、第四人入義；
    前半停在柳拂衣向晏歸舟提起、還沒回的那一刻。後半第一件事無條件重新登入：晏歸舟答應（滿 5 人）、第 6 人（簡素心）卡上灰掉、硬按被拒、舊的邀請答不了；
    杜衡舟割袍斷義（冷卻、卡上的冷卻、再提被拒、再割一次「還沒有結義」、義譜）；假人：兩位假人跟石不語換過名帖（直接放進名帖匣），石不語向他們提起、擺成早收到；假人眼前的打分數（bots.score）與整季機器人的挑法（bot.pick）；各輪到自己一步（bot_policy.take_turn）：season21、week7 一位答應（開義）、一位擲到不理，測試內容兩位都答應（第二位入義）——照名號｜邀請編號擲，邀請編號跟著時刻變；再跑 BotRunner 幾輪、看全服的結義帳。
    這一軌走不到的：BotRunner 自己答到結義之邀（一開動假人就先清開季準備卡、接委託上路，幾輪內輪不到；所以另叫 take_turn）；換季不散（換季由包的 test_jieyi.py 守）；江湖頁的結義之邀與俠客頁門下那一段的畫面（web/jieyi.js，沒有實機）。"""

    LEAD, B, C, D, E, F, LONER = "柳拂衣", "杜衡舟", "葛青崖", "聞笛生", "晏歸舟", "簡素心", "石不語"
    BOT_SEATS = ["盟甲", "盟乙"]
    PLAYERS = {LEAD: None, B: None, C: None, D: None, E: None, F: None, LONER: None}
    NEWBIE = "初來客"
    PHASES_FIRST = ["setup", "seat", "closed", "cards", "open", "half"]
    PHASES_SECOND = ["resume", "fill", "leave", "machines"]

    def switch_on(self) -> None:
        self.c.config.jieyi.enabled = True

    def book(self, tag: str) -> None:
        bk = self.world.read().jieyi
        emit(f"結義帳 {tag}", bk.model_dump(mode="json") if bk is not None else None)

    def jieyi_of(self, who: str, tag: str) -> None:
        main = self.main(who)
        emit(f"{who} {tag}：jieyi 的鍵", sorted(k for k in main if k.startswith("jieyi")) if isinstance(main, dict) else None)
        emit(f"{who} {tag}：main.jieyi", main.get("jieyi") if isinstance(main, dict) else None)
        emit(f"{who} {tag}：選單上的 jieyi:", sorted(i for i in self.ids(main) if i.startswith("jieyi:")) if isinstance(main, dict) else None)

    def offer_id(self, sender: str, target: str) -> str | None:
        bk = self.world.read().jieyi
        return next((o.id for o in bk.offers if o.sender == sender and o.target == target), None) if bk is not None else None

    def respond(self, who: str, sender: str, verb: str) -> None:
        oid = self.offer_id(sender, who)
        if oid is None:
            emit(f"{who} 沒有 {sender} 的結義之邀", None)
            return
        self.main(who)
        self.choose(who, f"jieyi:{verb}:{oid}")

    def ask(self, who: str, him: str):
        return self.act(who, him, "jieyi", arg="ask")

    # ── 段落 ──

    def seat(self) -> None:
        hub = self.hub()
        for who in self.PLAYERS:
            self.place(who, hub)
        for who in self.PLAYERS:
            self.main(who)

    def closed(self) -> None:
        self.card_of(self.LEAD, self.B)
        self.ask(self.LEAD, self.B)
        self.do(self.LEAD, "jieyi_leave")
        self.jieyi_of(self.LEAD, "關著")
        self.jieyi_of(self.B, "關著")

    def cards(self) -> None:
        for who in (self.LEAD, self.B, self.C, self.D, self.E, self.F):
            self.call(who, "POST", "/api/mingtie/save", {"strokes": self.STROKES, "titles": [], "motto": "肝膽相照"})
        for him in (self.B, self.C, self.D, self.E, self.F):
            self.act(self.LEAD, him, "mingtie", arg="send")
            self.act(him, self.LEAD, "mingtie", arg="yes")
        self.card_of(self.LEAD, self.B)  # 還關著：換過帖也沒有結義那一顆

    def open(self) -> None:
        self.switch_on()
        self.card_of(self.LEAD, self.B)
        self.card_of(self.LEAD, self.LONER)  # 沒換過名帖：灰的
        self.ask(self.LEAD, self.LONER)
        self.ask(self.LEAD, self.B)
        self.ask(self.LEAD, self.B)  # 等他回話
        self.card_of(self.B, self.LEAD)
        self.jieyi_of(self.B, "收到邀請")
        self.respond(self.B, self.LEAD, "yes")
        self.ask(self.LEAD, self.F)
        self.respond(self.F, self.LEAD, "no")
        for him in (self.C, self.D):
            self.ask(self.LEAD, him)
            self.respond(him, self.LEAD, "yes")
        self.jieyi_of(self.LEAD, "四人")
        self.card_of(self.LEAD, self.C)  # 同一組：你們同為某某
        self.book("四人")

    def half(self) -> None:
        """前半停在這裡：柳拂衣向晏歸舟提起、還沒回。"""
        self.ask(self.LEAD, self.E)
        self.jieyi_of(self.E, "前半停在這裡")
        self.book("前半停在這裡")

    def resume(self) -> None:
        self.switch_on()
        self.login_all()

    def fill(self) -> None:
        stale = self.offer_id(self.LEAD, self.E)
        self.respond(self.E, self.LEAD, "yes")  # 滿 5 人
        self.choose(self.E, f"jieyi:yes:{stale}")  # 舊的邀請答不了
        self.card_of(self.LEAD, self.F)  # 第 6 人：灰的
        self.ask(self.LEAD, self.F)
        self.card_of(self.F, self.LEAD)
        self.jieyi_of(self.LEAD, "五人")
        self.book("五人")

    def leave(self) -> None:
        self.do(self.B, "jieyi_leave")
        self.jieyi_of(self.B, "割袍斷義之後")
        self.card_of(self.B, self.LEAD)
        self.ask(self.B, self.LEAD)
        self.do(self.B, "jieyi_leave")  # 已經不在組裡
        self.jieyi_of(self.LEAD, "少一人")
        self.book("割袍斷義之後")

    def machines(self) -> None:
        """假人：兩位假人跟石不語換過名帖（直接放進名帖匣），石不語向他們提起；擺成早收到，BotRunner 幾輪之後看結義帳。"""
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile, Mingtie, MingtieCopy

        hub = self.hub()
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=71 + i, faction=None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            prep = (f"growth:{self.c.config.attributes.v2.default_preset}", "legacy:skip")  # 開季準備卡（五項屬性的季）同 clear_prep 按掉
            for _ in range(6):
                ids = [o.id for o in g.options(odds=False) if o.enabled]
                first = next((i for i in ids if i.startswith("choice:")), next((i for i in prep if i in ids), None))
                if first is None:
                    break
                g.choose(first)
            p.location, p.journey = hub, None
            p.visited.add(p.location)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.mingtie_box.append(MingtieCopy(name=self.LONER, card=Mingtie(version=1), when="", place="", season=1))
            self.chars.save(g.state)
            self.edit(self.LONER, lambda q, n=name: q.mingtie_box.append(MingtieCopy(name=n, card=Mingtie(version=1), when="", place="", season=1)))
        for name in self.BOT_SEATS:
            self.card_of(self.LONER, name)
            self.ask(self.LONER, name)

        def back(shared) -> None:
            for o in shared.jieyi.offers:
                if o.sender == self.LONER:
                    o.sent_at -= 600.0
        self.world.mutate(back)
        from tianxia import bot, bot_policy

        for name in self.BOT_SEATS:  # 假人眼前的結義之邀：打分數（bots.score，等 bot_reply_seconds 之後才回）與整季機器人的挑法
            self.begin()
            g = Game(self.c, self.chars.load(name), random.Random(0), self.world)  # 不存（server.game_for 不開假人的名號）
            g.client = None
            g.sync(CLOCK[0])
            opts = g.options(odds=False)
            emit(f"{name} 眼前的 jieyi:", {o.id: bot_policy.score(g, o, g.state.player.bot) for o in opts if o.id.startswith("jieyi:")})
            emit(f"{name} 整季機器人挑的", sorted({str(bot.pick(g, opts, random.Random(k))) for k in range(12)}))
        for name in self.BOT_SEATS:  # 伺服器假人輪到自己的那一步（bot_policy.take_turn，同 BotRunner 一輪裡做的；BotRunner 一開動假人就上路，輪不到這一顆）
            self.begin()
            with self.world.action_lock():
                g = Game(self.c, self.chars.load(name), random.Random(5), self.world)
                g.client = None
                g.sync(CLOCK[0])
                emit(f"{name} 輪到自己", bot_policy.take_turn(g, g.state.player.bot, random.Random(9)))
                self.chars.save(g.state)
        self.book("假人答過之後")
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(43), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {71 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_OATH_TICKS", "6"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        self.jieyi_of(self.LONER, "假人之後")
        self.book("假人之後")


# 改一個字（selftest）：一組的人數上限那一句反過來（>= 改 >），第 6 人照樣邀得到，season21 fill 那一段抓到
register_track("oath", OathScenario, (("tianxia/features/jieyi/rules.py",), ("if mine is not None and len(mine.members) >= cfg.max_members:", "if mine is not None and len(mine.members) > cfg.max_members:")), "season21",
               covers=("jieyi", "peers"))
