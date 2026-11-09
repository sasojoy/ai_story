"""same_behavior 一軌一檔：reckon（這一檔登記 reckon）。"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

from sb.harness import ADMIN, CLOCK, STEP, emit, register_track
from sb.tracks.carve import CarveScenario

# core_seams（全部拆包第 55 批「補算與換季收接縫」；計畫 docs/superpowers/plans/2026-11-06-補算換季收接縫-第55批.md 第七節）：這一段整段是第 55 批加的——
# 情境 ReckonScenario（--track reckon，自己一個資料庫、自己切一半），最後一行登記。現有 51 軌逐行量過（計畫第七節那張表）：sync、advance、world_tick 的主幹都走到了，
# 走不到的是髒存檔那幾支（收鐵匠鋪、收馬市、舊的同伴確認、所在地被拿掉）、同一份 Game 裡的收店、換季帶走的欄位（別軌帶的多半是預設值，帶丟了也看不出來）、
# 排程那一下推奪璽單挑。角色的名字都是原創的（PM 11/04）；既有的軌一個字不動。


class ReckonScenario(CarveScenario):
    """補算與換季一軌（全部拆包第 55 批；--track reckon，自己一個資料庫）。借 carve 的 setup、seat（固定密鹽、七片、單挑節奏縮短）。
    前半切在 smear：舊程式存下來的髒存檔沒有人讀過，新程式第一次讀（半舊半新）。後半：接手那一次清失效參照、同一份 Game 裡收店、
    管理者快轉（advance：抵達、跨 22:00、補送寄放）、排程那一下（world_tick：奪璽單挑）、假人輪一輪、把換季帶走的欄位都擺成非預設、收季與開下一季。"""

    BOT_SEATS = ["晏歸舟", "岑照影"]
    PHASES_FIRST = ["setup", "seat", "smear"]
    PHASES_SECOND = ["wake", "same_game", "pace", "watch", "machines", "marks", "turnover", "read_back"]
    LEFT = ("location", "journey", "picking_smith", "smith_draft", "picking_market", "picking_bounty", "bounty_pick", "pending_companion",
            "snubbed_until", "leg_actions", "recent_sights", "busy_until", "fortune")
    CARRIED = ("tutorial_step", "guide_skipped", "enlist_step", "hints_seen", "hints_off", "hint_queue", "newbie_marks", "newbie_done", "renown_told",
               "affinities", "past_notes", "dialogue_history", "history_start", "used_dialogue_options", "turns_since_consolidation", "gender",
               "gender_chosen", "stamina_pills", "legend_items", "create_rerolls", "pills_topped_to", "pill_day", "pills_today", "sortie_day",
               "sorties_today", "drill_day", "drills_today", "upgrade_day", "upgrades_today", "donate_day", "donated_today", "battle_results_seen",
               "heirloom", "seal_seen", "rack", "weapon_serial", "divine_solved", "mingtie", "mingtie_box", "mingtie_hidden", "taunt_muted", "mingtie_day",
               "mingtie_made", "mingtie_sent", "gift_day", "gifts_today", "keepsakes", "lasting", "flags", "legacy", "season_number")

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        if profile == "test":  # 福緣送上門：只有測試內容有可招募的人（正式內容沒人可給、一類一顆回空）；季短，等不到第 7 天，這裡讓它一補算就到期
            self.c.config.fortune_day_max = 0

    def looks(self, who: str, tag: str, fields: tuple[str, ...]) -> None:
        """資料庫裡這個人的這幾個欄位（集合排序，輸出才穩）。"""
        dump = self.chars.load(who).player.model_dump(include=set(fields))
        emit(tag, json.loads(json.dumps(dump, ensure_ascii=False, default=sorted)))

    def tick_world(self, tag: str) -> None:
        """伺服器排程的一下（server.world_step：沒有玩家的 Game；同 DuelScenario 的那一下）。"""
        self.begin()
        msgs = self.server.world_step(time.time)
        self.server.GAMES.clear()
        emit(f"排程 {tag}", msgs)

    # ── 前半 ──

    def smear(self) -> None:
        """切點：直接改資料庫，後面沒有任何一下請求讀過。藺秋禾站在野地還開著三間店、帶著舊的同伴確認與找不到的人物、景、路上的事；
        聞岫川的所在地與路都被內容拿掉了；季聽瀾在此地開著鐵匠鋪、單子上的料沒了；符靜淵的閉關到期了（下一次同步出關，紀錄自己寫一則）。"""
        from tianxia.core.services import ROAD_TASKS
        from tianxia.state import Journey, SmithDraft

        spot = self.wild_spot() or self.hub()
        figure = sorted(self.c.figures)[:1]
        sights = sorted(self.c.road_sights)[:1]

        def dirty(p):
            p.location, p.journey = spot, None
            p.picking_smith, p.smith_draft = True, SmithDraft(kind="劍")
            p.picking_market = True
            p.picking_bounty, p.bounty_pick = True, "沒有這一張"
            p.pending_companion = "沒有這個人"
            p.snubbed_until = {"沒有這一位": 1.0, **{f: 2.0 for f in figure}}
            p.recent_sights = ["沒有這一景", *sights]
            p.leg_actions = {"沒有這件事", *sorted(ROAD_TASKS)[:1]}

        def lost(p):
            p.location = "沒有這個地方"
            p.journey = Journey(mode="walk", path=["沒有這一站"], arrive_at=[1.0e12])
            p.leg_actions = {"沒有這件事"}

        def stale_order(p):
            p.picking_smith, p.smith_draft = True, SmithDraft(kind="劍", main="沒有這一料")

        def retreat(p):
            p.busy_until = 0.0

        self.edit(self.WORKER, dirty)
        self.edit(self.HUNTER, lost)
        self.edit(self.RIVAL, stale_order)
        self.edit(self.ABSENT, retreat)

    # ── 後半 ──

    def wake(self) -> None:
        """新程式第一次讀（建 Game 清失效參照、接著同步）：每一位看選單、再看資料庫裡那幾個欄位。"""
        self.login_all()
        for who in (self.WORKER, self.HUNTER, self.RIVAL, self.ABSENT):
            self.main(who)
            self.looks(who, f"{who} 接手第一次同步之後", self.LEFT)

    def same_game(self) -> None:
        """同一份 Game 裡店才開著、人不在那裡（管理者挪人、開關關了：建 Game 那一次清失效參照已經過了，只有同步那幾行收得到）：
        三樣都開著；只有單子。照 server 的做法拿鎖、重讀，只叫 sync，再存回。"""
        from tianxia.state import SmithDraft

        for tag, smith, market in (("三樣都開著", True, True), ("只有單子", False, False)):
            self.begin()
            game = self.server.game_for(self.WORKER)
            with self.server._locked(game):
                p = game.state.player
                p.picking_smith, p.smith_draft, p.picking_market = smith, SmithDraft(kind="劍"), market
                msgs = game.sync(time.time())
                emit(f"同一份 Game 同步 {tag}", [msgs, p.picking_smith, p.smith_draft is None, p.picking_market])
                self.server.open_characters().save(game.state)
            self.server.GAMES.clear()

    def pace(self) -> None:
        """管理者在路上、寄放著一匹馬：快轉（/api/do/fast_forward → Game.advance）一下抵達、寄放補上（正式內容；測試內容坐騎關著，留著），
        再一下跨過 22:00（正式內容：季時間 96 小時約合現實 11 小時，領地爭奪換天）。"""
        from tianxia import mounts
        from tianxia.state import Journey

        when = self.world.get_season().time + 3.0 * 3600

        def go(state):
            p = state.player
            dest = next(loc for loc in sorted(self.c.locations) if loc != p.location)
            p.journey = Journey(mode="walk", path=[dest], arrive_at=[when])
            p.held_gear.append(mounts.new_mount(state, name="寄放馬", tier=2, quality="中品"))

        self.edit_state(ADMIN, go)
        self.do(ADMIN, "fast_forward", {"hours": 4})
        self.looks(ADMIN, "管理者抵達之後", ("location", "journey", "held_gear"))
        self.do(ADMIN, "fast_forward", {"hours": 24 if self.profile == "test" else 96})  # 測試內容的季短，96 小時整季就收了
        self.looks(ADMIN, "管理者跨日之後", ("location", "journey", "held_gear"))

    def watch(self) -> None:
        """排程那一下（world_tick）推奪璽單挑：沒有人同步，一回合一回合等到期；剩下的照 carve 同步推到收場。"""
        shard = sorted(self.c.seal)[0]
        self.do(ADMIN, "seal_assign", {"id": shard, "name": self.KEEPER, "state": "held"})
        self.do(ADMIN, "seal_duel", {"id": shard, "name": self.FOE, "factor": 1.0})
        for n in range(4):
            STEP[0] += 60
            self.tick_world(f"第 {n} 下")
            emit(f"排程第 {n} 下之後的單挑", [d.model_dump() for d in self.world.seal_state().duels])
            self.relic_view(f"排程第 {n} 下之後")
        self.duel_out((self.KEEPER, self.FOE))

    def bot_rounds(self, rounds: int) -> None:
        """BotRunner 跑幾輪（那兩位一定在線；同 carve 的 bot_duel）。"""
        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner

        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(47), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {91, 92}
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
        """假人碰得到：兩位假人的存檔也髒（店開著、舊的同伴確認、路上的事）；輪一輪（建 Game 清失效參照、同步、系統通緝那一輪）。"""
        from tianxia.engine import Game
        from tianxia.state import BotProfile, SmithDraft

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
            p.picking_smith, p.smith_draft, p.picking_market = True, SmithDraft(kind="劍", main="沒有這一料"), True
            p.pending_companion, p.leg_actions = "沒有這個人", {"沒有這件事"}
            self.chars.save(g.state)
        self.bot_rounds(3)
        for name in self.BOT_SEATS:
            self.looks(name, f"假人 {name} 輪過之後", self.LEFT)

    def marks(self) -> None:
        """換季帶走的每一樣都擺成非預設（別軌帶的多半是預設值，帶丟了看不出來）：藺秋禾與第一位假人。序章走完、後面的步驟還沒做完的人（卓遠岑；第二位假人多跳過初入江湖）。
        裝備庫放一把收藏的神器（綁了招、流水號接著走）。"""
        from tianxia import weapons
        from tianxia.state import LegacyBook, Mingtie, MingtieCopy

        cid = sorted(self.c.characters)[0]

        def everything(state):
            p = state.player
            p.renown_told, p.affinities = True, {cid: 87}
            p.past_notes, p.relationship_notes = {"舊識": "舊事"}, {cid: "新事"}
            p.hints_seen, p.hints_off = {"沒有這一句"}, True
            p.newbie_marks, p.newbie_done = {"沒有這一步"}, {"沒有這一項"}
            p.dialogue_history = {cid: [{"role": "user", "content": "久仰"}, {"role": "assistant", "content": "幸會"}]}
            p.used_dialogue_options, p.turns_since_consolidation = {cid: ["甲"]}, {cid: 3}
            p.gender, p.gender_chosen = "女", True
            p.stamina_pills, p.legend_items, p.create_rerolls, p.pills_topped_to = 7, 3, 2, 5
            p.pill_day, p.pills_today = 11, 2
            p.sortie_day, p.sorties_today, p.drill_day, p.drills_today = 12, 3, 13, 4
            p.upgrade_day, p.upgrades_today, p.donate_day, p.donated_today = 14, {3: 1}, 15, 5
            p.battle_results_seen = [901, 902]
            p.divine_solved = {"沒有這一譜": "沒有這一器"}
            p.mingtie, p.mingtie_hidden, p.taunt_muted = Mingtie(motto="此帖不換", version=2), ["路人甲"], ["路人乙"]
            p.mingtie_box = [MingtieCopy(name="路人丙", card=Mingtie(motto="後會有期", version=1), when="第 1 週", place="此地", season=1)]
            p.mingtie_day, p.mingtie_made, p.mingtie_sent, p.gift_day, p.gifts_today = 21, 1, 2, 22, 3
            p.keepsakes, p.lasting = ["沒有這一物"], ["沒有這一旗"]
            p.legacy = LegacyBook(zheng=1.5, xie=0.5, luck=0.25)
            item = weapons.new_weapon(state, name="收著的劍", kind="劍", attribute="剛", tier=2, quality="中品", collected=True)
            item.bound_art = "沒有這一門"
            p.rack.append(item)

        tutorial = self.c.tutorial

        def half_way(p):
            p.tutorial_step = tutorial.prologue_steps

        for who in (self.WORKER, self.BOT_SEATS[0]):
            self.edit_state(who, everything)
            self.looks(who, f"{who} 換季之前", self.CARRIED)
        for who in (self.FOE, self.BOT_SEATS[1]):
            self.edit(who, half_way)
            self.looks(who, f"{who} 換季之前", ("tutorial_step", "onboarding", "bot"))

    def turnover(self) -> None:
        """收季、開下一季；每一位第一次同步換成新角色（真人經 API、假人經 BotRunner），看資料庫裡帶走的那幾樣。"""
        self.do(ADMIN, "end_season")
        self.do(ADMIN, "next_season")
        for who in (self.WORKER, self.FOE, self.KEEPER, self.ABSENT):
            self.main(who)
            self.looks(who, f"{who} 換季之後", self.CARRIED)
        self.bot_rounds(2)
        for name in self.BOT_SEATS:
            self.looks(name, f"假人 {name} 換季之後", self.CARRIED)

    def read_back(self) -> None:
        self.call(ADMIN, "GET", "/api/admin")
        self.tick_world("換季之後")
        self.relic_view("最後")


# 改一個字（selftest）：換季帶走的一天贈物次數（Game._reset_player_for_new_season；換成掛鉤之後在玩家互動包，第 2 段搬的時候這一句一字不動、檔名照實補）：marks 擺的 3 帶丟了
register_track("reckon", ReckonScenario, (("tianxia/engine.py", "tianxia/features/peers/actions.py"),
                                          ("fresh.player.gift_day, fresh.player.gifts_today = old.player.gift_day, old.player.gifts_today",
                                           "fresh.player.gift_day, fresh.player.gifts_today = old.player.gift_day, 0")), "season21",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "identity", "legacy", "looks", "mail", "mall",
                       "military", "outlets", "peers", "seal", "seclusion", "sense", "smithy", "socialize", "sortie", "stamina_plays",
                       "story", "tavern", "territory_acts", "travel", "zhuan", "zongmen"))
