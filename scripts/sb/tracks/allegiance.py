"""same_behavior 一軌一檔：allegiance（這一檔登記 allegiance）。"""
from __future__ import annotations

import hashlib
import os
import random

from sb.base import Scenario, _three_way_off
from sb.harness import ADMIN, CLOCK, STEP, emit, register_track
from sb.tracks.effects import EffectsScenario, FX_PREFIX

# ═══════════════════════════ faction：陣營一軌 allegiance（全部拆包第 35 批，dev/faction-1；計畫 docs/superpowers/plans/2026-11-06-陣營包-第1批.md） ════


class AllegianceScenario(EffectsScenario):
    """陣營一軌（全部拆包第 35 批；--track allegiance，自己一個資料庫）。借效果與叛投那一軌的擺法（stage_defector：叛投之前手上擺滿會被清的進度）。
    投靠（faction:<id> → faction:confirm）：確認畫面（寫明這一季不能改投、各方人數）、再想想（faction:cancel）、確定、按了之後走開再確定
    （寫「你已經不在投靠的地方了」）、豪強分屬兩軍的季投靠豪強（四勝利開著時照投靠點直接給傾向；pick_side 把四勝利暫時關掉，走 faction:ally:<id> 自己挑依附哪一軍；那一段只有投靠豪強的人，沒有人拜門派）。
    改幫（faction:lean:<軍>，三陣營四勝利）：改幫、再改同一軍（灰或清單外）、有事件待選時被擋（FB-820）、在路上照樣收（lean_actions.stale_cell）。
    拜入門派（sect:<事件>）：進去、婉拒；測試內容只有流雲派一個。拜入曹氏莊院之後「挑依附哪一軍」這一步在四勝利開著時由 join_lean 直接給傾向（回「你依附了官軍。」），不經選單，見下面「沒走到的」。
    叛投（defect:<陣營>[:<依附>] → defect:confirm）：確認畫面（身份歸零、糧車、密謀、懸賞、同伴……）、再想想、按了之後走開再確定（叛投不成）、
    已叛投過再按、豪強以叛投換陣營；叛投之後欠著的、清進度那幾格由效果與叛投那一軌擺局面（defect_full）。
    三方卡與結局卡（main 的 sides_card、week_card.tier_hint、收季之後的 ending）、新的一季開局的起手資源與稱號（_season_grant）。
    **前半停在三件寫到一半的事**：一個人按了投靠還沒確定、一個人按了叛投還在確認畫面上、一位豪強按了投靠並已經挑好依附（pending_faction=haoqiang、pending_ally=guan，畫面是「確定投靠地方豪強（依附官軍）？」）；後半新程式接著確定。
    假人：BotRunner 三個（一個站在別人的投靠點、一個站在門派所在地、一個還沒投靠站在投靠點照 bot_policy 投靠）；整季機器人在投靠點與門派眼前的選單與挑法。
    沒有陣營的內容（測試內容）：投靠、改幫、叛投、三方卡寫「這份內容沒有兩軍」，同一串 API 照打；拜入門派的鈕（sect:）要「一類一顆」開著才有，測試內容關著，
    走不到（選單上是空的）。**沒走到的**：名字還在沒打完的決戰參戰名單上不能叛投（defection.refusal 的 enlisted 那一條；決戰那一軌的人物才擺得出來）；四勝利關著時拜入曹氏莊院之後挑依附（faction_step 的 ally 支在 pending_faction 是 None 的那一段、join_actions.pending_options 的 needs_ally 第一支、p.ally 與 ALLY_DONE；pick_side 關掉四勝利那一小段沒有人拜門派）；豪強換依附的那一邊（defect:<陣營>:<依附>：「考慮改投／改依附」標題、p.pending_ally、defection.refusal／defect 帶依附、slot_label 的改依附；選單上有 defect:haoqiang:huang 但沒有人按）；豪強按了投靠但還沒挑依附（pending_ally 為空）的前半停點與接著挑依附。這幾處的本體搬過去前後用 ast 比過是一樣的，沒有 same_behavior 的軌證明；集結中投靠豪強之後名單換邊（_ally_follows_battle）由集結那一軌 muster 證明。
    曹氏莊院要先接護院三招：這一軌把「曹家護院」的難度暫時壓到 1，讓拜入走得到。"""

    G, H, Q, X = "戚承光", "樊既白", "邵雲岫", "祁望舒"
    ACCEPT, DECLINE = ("穆澄江", "習景行"), ("向晚晴", "尉遲鴻")
    RUN, CAN, GD, HOLD, HG, GU, HU, PS = "葛臨川", "宗和風", "晏棲遲", "翟忘機", "盛洛川", "裴映川", "藺秋原", "屈子遲"
    PLAYERS = {who: None for who in (G, H, Q, X, *ACCEPT, *DECLINE, RUN, CAN, GD, HOLD, HG, GU, HU, PS, "殷照野", "談秋聲", "范清和", "閔遠帆")}
    DF1, DF2, LEAD, LONE = "殷照野", "談秋聲", "范清和", "閔遠帆"
    BOT_SEATS = ["陣甲", "陣乙", "陣丙"]
    PHASES_FIRST = ["setup", "seat", "join", "lean", "pick_side", "sect", "refuse", "defect_full", "defected_again", "cards", "half"]
    PHASES_SECOND = ["resume", "finish", "bots", "close", "season"]

    def setup(self) -> None:
        Scenario.setup(self)

    # ── 小工具 ──

    def faction_of(self, fid: str):
        return next((f for f in self.c.scenario.factions if f.id == fid and f.join_at), None)

    def press(self, who: str, option_id: str, tag: str) -> dict:
        """按選單上的一顆（灰著照按，被擋的那一句也要寫出來；選單上沒有也照按〔清單外〕）；回按之前的選單。"""
        opts = self.ids(self.main(who))
        have = opts.get(option_id)
        emit(f"{who} {tag} 按 {option_id}", None if have is None else {"label": have.get("label"), "enabled": have.get("enabled")})
        self.choose(who, option_id)
        return opts

    def menu(self, who: str, tag: str, *prefixes: str) -> list[str]:
        opts = self.ids(self.main(who))
        emit(f"{who} {tag} 選單上", [[i, o.get("label"), o.get("enabled")] for i, o in opts.items() if i.startswith(prefixes)])
        return [i for i in opts if i.startswith(prefixes)]

    def pick_ally(self, who: str, tag: str) -> None:
        """眼前有挑依附哪一軍的兩顆（faction:ally:<軍>）就按第一顆（照劇本的順序）。"""
        ally = [i for i in self.menu(who, tag, "faction:ally:") if self.ids(self.main(who))[i].get("enabled")]
        if ally:
            self.press(who, ally[0], tag)

    def join_gentry(self, who: str) -> None:
        """豪強的投靠點投靠豪強：按、（挑依附哪一軍）、確定。"""
        f = self.faction_of("haoqiang")
        if f is None:
            return
        self.place(who, f.join_at[0])
        self.press(who, "faction:haoqiang", "投靠豪強")
        self.pick_ally(who, "挑依附")
        self.press(who, "faction:confirm", "確定投靠豪強")
        self.settle_choices(who)

    def me(self, who: str, tag: str) -> None:
        super().me(who, tag)
        state = self.chars.load(who)
        if state is not None:
            p = state.player
            emit(f"{who} {tag}（陣營這一包）", {"pending_faction": p.pending_faction, "pending_defect": p.pending_defect,
                                          "pending_ally": p.pending_ally, "season_title": p.season_title,
                                          "sect": p.sect, "seen_sects": sorted(e for e in p.seen_events if "join" in e)})

    def world_view(self, tag: str) -> None:
        super().world_view(tag)
        w = self.world.get_season()
        emit(f"世界 {tag}（陣營這一包）", {"roll": dict(sorted(self.world.roll_counts().items())),
                                        "ended": w.ended, "final_tiers": {k: (v.model_dump(mode="json") if hasattr(v, "model_dump") else repr(v)) for k, v in sorted(w.final_tiers.items())}})

    # ── 前半 ──

    def seat(self) -> None:
        on = self.factions_on()
        sides = {self.DF1: "guan", self.DF2: "guan", self.LEAD: "guan", self.GU: "guan", self.HU: "huang", self.RUN: "guan", self.CAN: "guan"}
        for who in self.PLAYERS:
            self.place(who, self.hub(), sides.get(who) if on else None)
            self.edit(who, lambda p: p.stats.update({"silver": 500}))
            self.main(who)
        emit("這份內容有兩軍", on)
        from tianxia import wins

        emit("四勝利開著", wins.on(self.c, self.world.get_season()))
        self.world_view("坐定")

    def join(self) -> None:
        """官軍：按、再想想、再按、確定；黃巾：按、確定；一位按了就走開再確定；豪強：按、挑依附或直接給傾向、確定。"""
        if not self.factions_on():
            emit("投靠：這份內容沒有兩軍", None)
            return
        guan, huang = self.faction_of("guan"), self.faction_of("huang")
        self.place(self.G, guan.join_at[0])
        self.menu(self.G, "投靠點", "faction:")
        self.press(self.G, "faction:guan", "投靠官軍")
        self.menu(self.G, "確認畫面", "faction:")
        self.press(self.G, "faction:cancel", "再想想")
        self.press(self.G, "faction:guan", "再投靠官軍")
        self.press(self.G, "faction:confirm", "確定投靠官軍")
        self.settle_choices(self.G)
        self.me(self.G, "投靠官軍之後")
        self.place(self.H, huang.join_at[0])
        self.press(self.H, "faction:huang", "投靠黃巾")
        self.press(self.H, "faction:confirm", "確定投靠黃巾")
        self.settle_choices(self.H)
        self.me(self.H, "投靠黃巾之後")
        self.place(self.X, guan.join_at[0])
        self.press(self.X, "faction:guan", "按了投靠")
        self.place(self.X, self.hub())
        self.press(self.X, "faction:confirm", "走開了才確定")
        self.press(self.X, "faction:confirm", "確認畫面已經沒了還按確定")
        self.me(self.X, "走開了才確定之後")
        self.join_gentry(self.Q)
        self.me(self.Q, "投靠豪強之後")
        self.world_view("投靠之後")

    def lean(self) -> None:
        """豪強改幫：改幫、再改同一軍、有事件待選時被擋、在路上照樣收。"""
        if not self.factions_on():
            emit("改幫：這份內容沒有兩軍", None)
            return
        from tianxia.state import Journey

        who = self.Q
        sides = [i for i in self.menu(who, "改幫之前", "faction:lean:")]
        if not sides:
            emit("改幫：這一季沒有改幫的鈕（四勝利關著）", None)
            return
        self.press(who, sides[0], "改幫")
        self.me(who, "改幫之後")
        self.press(who, sides[0], "再改同一軍")
        back = (self.menu(who, "改回去的鈕", "faction:lean:") or sides)[0]  # 現在幫的那一軍不列，剩下的是能改回去的
        self.card(who, f"{FX_PREFIX}all")
        self.menu(who, "有事件待選", "faction:lean:")
        self.press(who, back, "有事件待選時改幫")
        self.edit_state(who, lambda s: setattr(s, "pending_event", None))
        far = next(i for i in sorted(self.c.locations) if i != self.chars.load(who).player.location)
        self.edit(who, lambda p: setattr(p, "journey", Journey(mode="walk", path=[far], arrive_at=[10 ** 9])))
        self.menu(who, "在路上", "faction:lean:", "road:")
        self.press(who, back, "在路上改幫（改回去）")
        self.me(who, "在路上改幫之後")
        self.place(who, self.hub())
        self.world_view("改幫之後")

    def pick_side(self) -> None:
        """三陣營四勝利關著的那一種季（兩種有章的設定都開著，這一下把 Config.jianfa.enabled 暫時關掉）：投靠豪強要自己挑依附哪一軍（faction:ally:<軍>），
        結局卡、三方卡的階都沒有；出來還原。"""
        if not self.factions_on():
            emit("挑依附：這份內容沒有兩軍", None)
            return
        jianfa = self.c.config.jianfa
        before, jianfa.enabled = jianfa.enabled, False
        emit("這一下的設定", {"jianfa.enabled": jianfa.enabled, "before": before})
        try:
            with _three_way_off(self.c.config):
                self.join_gentry(self.PS)
                self.me(self.PS, "挑依附之後")
                self.menu(self.PS, "四勝利關著", "faction:lean:")
        finally:
            jianfa.enabled = before
        self.world_view("挑依附之後")

    def sect(self) -> None:
        """每個門派：一位拜入（有事件選那個拜入的選項；拜入曹氏莊院之後挑依附哪一軍）、一位婉拒（不拜的那個選項）。"""
        for i, (sid, sect) in enumerate(sorted(self.open_sects().items())[:2]):
            for who, accept in ((self.ACCEPT[i], True), (self.DECLINE[i], False)):
                if not self.place(who, sect.location):
                    continue
                squad = self.c.squads.get("xuantie_dizi") if accept else None
                before = None if squad is None else squad.difficulty
                if accept:  # 曹氏莊院要先接護院三招：屬性補滿、護院的難度這一下壓到 1（讓拜入走得到），接不下來（還是散人）再試，最多四回
                    self.edit(who, lambda p: p.stats.update({"str": 15, "agi": 15, "con": 15}))
                    if squad is not None:
                        squad.difficulty = 1
                        emit("曹家護院這一下的難度", {"before": before, "now": squad.difficulty})
                for oid in self.menu(who, f"{sid} 門派所在地", "sect:"):
                    eid = oid.partition(":")[2]
                    picks = [k for k, ch in enumerate(self.c.events[eid].choices) if bool(ch.effect.join_sect or ch.fail_effect.join_sect) == accept]
                    for _try in range(4 if accept else 1):
                        self.press(who, oid, "拜入門派" if accept else "看門派")
                        if picks:
                            self.choose(who, f"choice:{picks[0]}")
                        if not accept or self.chars.load(who).player.sect is not None:
                            break
                    self.pick_ally(who, "拜入之後挑依附")
                    self.settle_choices(who)
                    self.menu(who, "之後", "sect:", "faction:")
                if squad is not None:
                    squad.difficulty = before
                self.me(who, f"{sid} {'拜入' if accept else '婉拒'}之後")
        self.world_view("門派之後")

    def refuse(self) -> None:
        """叛投的幾條路：按了走開再確定（叛投不成）、按了再想想、豪強換邊（叛投或改投）；同一個人沒投靠就按叛投。"""
        if not self.factions_on():
            emit("叛投：這份內容沒有兩軍", None)
            return
        self.stage_defector(self.RUN, 1)
        oid = self.to_target(self.RUN)
        if oid is not None:
            self.choose(self.RUN, oid)
            self.menu(self.RUN, "確認畫面", "defect:")
            self.place(self.RUN, self.hub())
            self.press(self.RUN, "defect:confirm", "走開了才確定")
            self.me(self.RUN, "走開了才確定之後")
        oid = self.to_target(self.CAN)
        if oid is not None:
            self.choose(self.CAN, oid)
            self.press(self.CAN, "defect:cancel", "再想想")
            self.me(self.CAN, "再想想之後")
        self.press(self.X, "defect:huang", "沒投靠就按叛投")
        self.join_gentry(self.GD)
        f = self.faction_of("haoqiang")
        self.place(self.GD, f.join_at[0])
        self.menu(self.GD, "豪強自己的投靠點", "defect:", "faction:")
        oid = self.to_target(self.GD)
        if oid is not None:
            self.choose(self.GD, oid)
            self.menu(self.GD, "確認畫面", "defect:")
            self.press(self.GD, "defect:confirm", "確定")
        self.me(self.GD, "豪強叛投之後")
        self.world_view("叛投幾條路之後")

    def defected_again(self) -> None:
        """叛投過的人（效果與叛投那一軌的叛投）眼前不再有叛投的鈕，硬按寫「此刻無法這麼做」。"""
        if not self.factions_on():
            return
        target = self.faction_of("huang")
        self.place(self.DF1, target.join_at[0])
        self.menu(self.DF1, "叛投過了", "defect:")
        self.press(self.DF1, "defect:guan", "叛投過了再按")
        self.place(self.DF1, self.hub())

    def cards(self) -> None:
        """記幾筆貢獻與兩本帳之後看三方卡（sides_card、tier_hint）：官軍、黃巾、豪強、散人各一位。"""
        if not self.factions_on():
            emit("三方卡：這份內容沒有兩軍", None)
            return

        def give(p, n) -> None:
            p.contrib = n
            p.contrib_weeks = {1: n}
            if p.ally:
                p.ledgers = {"guan": n, "huang": n // 2}

        for who, n in ((self.GU, 60), (self.HU, 90), (self.Q, 40), (self.G, 25), (self.H, 10)):
            self.edit(who, lambda p, n=n: give(p, n))
        for who in (self.GU, self.HU, self.Q, self.LONE):
            self.main(who)
        self.world_view("三方卡")

    def half(self) -> None:
        """前半停在三處：一位按了投靠還沒確定、一位按了叛投停在確認畫面上、一位豪強按了投靠並已挑好依附還沒確定（不是「還沒挑依附」，那一段沒走到）。"""
        if not self.factions_on():
            emit("前半停在這裡：這份內容沒有兩軍", None)
            return
        self.place(self.HOLD, self.faction_of("guan").join_at[0])
        self.press(self.HOLD, "faction:guan", "按了投靠")
        self.me(self.HOLD, "前半停在這裡")
        self.stage_defector(self.DF2, 2)
        oid = self.to_target(self.DF2)
        if oid is not None:
            self.choose(self.DF2, oid)
        self.me(self.DF2, "前半停在這裡")
        self.place(self.HG, self.faction_of("haoqiang").join_at[0])
        self.press(self.HG, "faction:haoqiang", "按了投靠豪強")
        self.me(self.HG, "前半停在這裡")
        self.world_view("前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()
        for who in (self.HOLD, self.DF2, self.HG):
            self.main(who)

    def finish(self) -> None:
        """新程式接著按：確定投靠、挑依附再確定、確定叛投。"""
        if not self.factions_on():
            return
        emit(f"{self.HOLD} 確認畫面上", sorted(self.ids(self.main(self.HOLD))))
        self.press(self.HOLD, "faction:confirm", "接著確定投靠")
        self.settle_choices(self.HOLD)
        self.me(self.HOLD, "確定之後")
        self.pick_ally(self.HG, "接著挑依附")
        self.press(self.HG, "faction:confirm", "接著確定投靠豪強")
        self.settle_choices(self.HG)
        self.me(self.HG, "確定之後")
        emit(f"{self.DF2} 確認畫面上", sorted(self.ids(self.main(self.DF2))))
        self.press(self.DF2, "defect:confirm", "接著確定叛投")
        self.me(self.DF2, "確定之後")
        self.world_view("接著按之後")

    def bots(self) -> None:
        """假人：BotRunner 三個（陣甲是官軍站在黃巾的投靠點、陣乙站在門派所在地、陣丙還沒投靠站在官軍的投靠點照分數投靠）若干輪；
        整季機器人在投靠點與門派眼前的選單與挑法（叛投那幾顆、sect: 照排除）。"""
        from collections import Counter

        from tianxia import bot, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        on = self.factions_on()
        huang, guan = self.faction_of("huang"), self.faction_of("guan")
        sect_at = next(iter(sorted(self.open_sects().values(), key=lambda s: s.id))).location
        spots = [(huang.join_at[0] if on else self.hub(), "guan" if on else None, "guan" if on else None),
                 (sect_at, "guan" if on else None, "guan" if on else None),
                 (guan.join_at[0] if on else self.hub(), None, "guan" if on else None)]
        for i, (name, (loc, side, lean)) in enumerate(zip(self.BOT_SEATS, spots)):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=191 + i, faction=lean, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = side, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.stats["silver"] = 300
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(41), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {191 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_ALLEGIANCE_TICKS", "6"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            emit(f"假人 {name}", {"loc": s.player.location, "faction": s.player.faction, "ally": s.player.ally, "sect": s.player.sect,
                                  "pending": [s.player.pending_faction, s.player.pending_defect],
                                  "journal": [[e.title, list(e.lines)[:4]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.world_view("假人之後")
        for k, (loc, side) in enumerate(((spots[0][0], spots[0][1]), (sect_at, None), (spots[2][0], None))):
            self.begin()
            solo = Game.new(self.c, f"陣丁{k}", rng=random.Random(7 + k), world=self.world, graduated=True)
            solo.client = None
            solo.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                solo.choose(first)
            p = solo.state.player
            p.faction, p.location, p.journey = side, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.stamina = float(self.c.config.stamina_max)
            opts = solo.options(odds=False)
            emit(f"整季機器人眼前的選單（{loc}）", [o.id for o in opts])
            emit(f"整季機器人挑的（{loc}）", sorted({str(bot.pick(solo, opts, random.Random(j))) for j in range(40)}))

    def close(self) -> None:
        """收季：結局卡（winner、condition、my_tier、title、reward）；官軍、黃巾、豪強、散人各一位。"""
        self.do(ADMIN, "end_season")
        for who in (self.GU, self.HU, self.Q, self.G, self.LONE):
            self.main(who)
            self.me(who, "收季之後")
        self.world_view("收季之後")

    def season(self) -> None:
        """開下一季：上一季論了功的人起手資源與稱號（_season_grant）。"""
        self.do(ADMIN, "next_season")
        for who in (self.GU, self.HU, self.Q, self.G, self.LONE):
            self.main(who)
            self.me(who, "換季之後")
        self.world_view("換季之後")


# 改一個字（selftest）：按了投靠走開再確定那一句（原 Game._faction_step 確定那一支，第 35 批搬進 features/faction/join_actions.py；舊名的檔與包裡的檔兩處找）
register_track("allegiance", AllegianceScenario, (("tianxia/engine.py", "tianxia/features/faction/join_actions.py"), ("（你已經不在投靠的地方了。）", "（你已經不在投靠的地方了！）")), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "figure_acts", "gear", "guide", "heroines", "hire", "legacy", "looks", "mall", "map", "military",
                       "outlets", "peers", "seal", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story", "tavern",
                       "territory_acts", "travel", "zhuan"))
