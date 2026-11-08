"""same_behavior 一軌一檔：socialize（這一檔登記 socialize）。"""
from __future__ import annotations

import random

from sb.harness import ADMIN, MODEL, emit, register_track
from sb.tracks.companions import CompanionsScenario, GameStateHolder

# ═══════════════════════════ socialize（全部拆包第 21 批：交友求見） ═══════════════════════════


class SocializeScenario(CompanionsScenario):
    """交友求見（全部拆包第 21 批；--track socialize，自己一個資料庫）。
    交友（act:socialize）：人物在（只有一位的地點，名望夠〔開口、模型回了〕、名望不夠〔被打發或灰掉〕）、人物不在（幾處沒有大勢人物的地點：抽到交友事件就是事件；抽不到才是「此地無人可訪」，那一支這條軌讀不出走到沒有，pytest 換掉 pick_event 才守）。求見（act:call → call:<人物>）：兩位以上的地點打開名單，名望夠〔開口〕、名望不夠〔被打發，一類一顆開著時灰掉、結識事件走結識〕、
    返回、清單外的 id；只有一位時選單上直接列的「求見某某」。次數：前半談過一輪，後半把每日輪數調成 1（談滿，鈕灰掉、寫換日那一刻）、調成 2（談第二輪時自動告辭）。
    結識奇遇：福緣到了交友先發（入門的同伴），到期自己送上門，沒有同伴可給時送賀禮（心得）。**前半停在挑對象挑到一半**（picking_audience：求見名單開著、還沒按）：
    後半一位按人物、一位按返回、一位按了名望不夠的被打發。假人（BotRunner 十輪；bot_policy.score 問 call:、act:call、act:socialize；bot.pick 看求見名單）；換季。
    沒有大勢人物的內容（測試內容）只剩福緣與交友事件，同一串 API 照打。"""

    GREETER, LOWFAME, ABSENT = "雲棲遲", "白景行", "石臨川"
    CALLER, CALLER2, BRUSHED, BRUSHED2 = "趙明遠", "錢若水", "顧雲生", "冷霜降"
    WAITER, WAITER2, WAITER3 = "方子期", "宋寒江", "葉知秋"
    FORTUNE, OVERDUE, GIFT, GIFT2 = "蘇采薇", "秋無痕", "江映月", "夏候清"
    SNUB = "林雪衣"  # 剛被他打敗、他閉門不見
    PLAYERS = {GREETER: "guan", LOWFAME: "guan", ABSENT: "guan", CALLER: "guan", CALLER2: "guan", BRUSHED: "guan", BRUSHED2: "huang",
               WAITER: "guan", WAITER2: "guan", WAITER3: "guan", SNUB: "guan", FORTUNE: "guan", OVERDUE: "guan", GIFT: "guan", GIFT2: "guan"}
    FORTUNES = (FORTUNE, OVERDUE, GIFT, GIFT2)
    TALKER = WAITER  # 沿用人物情誼一軌的假人段落要的名字
    PHASES_FIRST = ["setup", "seat", "alone", "absent", "hall", "fortune", "list_open", "half"]
    PHASES_SECOND = ["resume", "list_on", "talked_out", "bots", "gift", "season"]

    # ── 小工具 ──

    def layout(self) -> dict[str, list[str]]:
        """大勢人物此刻各在哪一處（人物活起來的季他會走動）：地點 → 人物 id。"""
        from tianxia import figure_life

        holder = GameStateHolder(self.world.get_season())
        where: dict[str, list[str]] = {}
        for cid, ch in sorted(self.c.characters.items()):
            if not ch.deep_interaction:
                continue
            try:
                loc = figure_life.where(holder, self.c, cid)
            except Exception:  # noqa: BLE001
                loc = ch.talk_at or ch.recruit_at
            if loc is not None:
                where.setdefault(loc, []).append(cid)
        return where

    def hall_spot(self) -> tuple[str | None, list[str]]:
        """兩位以上大勢人物的地點（交友不直接找人、改按求見指名）；沒有是 (None, [])。"""
        halls = {loc: figs for loc, figs in self.layout().items() if len(figs) >= 2}
        if not halls:
            return None, []
        loc = sorted(halls, key=lambda x: (-len(halls[x]), x))[0]
        return loc, halls[loc]

    def alone_spot(self) -> tuple[str | None, str | None]:
        """只有一位大勢人物的地點（交友直接開口、選單上直接列「求見某某」）；沒有是 (None, None)。"""
        lone = {loc: figs[0] for loc, figs in self.layout().items() if len(figs) == 1}
        if not lone:
            return None, None
        loc = next((x for x, cid in sorted(lone.items()) if cid == "qinjie"), sorted(lone)[0])
        return loc, lone[loc]

    def fame(self, who: str, value: int) -> None:
        self.edit(who, lambda p: p.stats.update({"fame": value}))

    def you(self, who: str, tag: str) -> None:
        """存檔裡交友求見碰得到的格子：在哪、體力、名望、心得、銀兩、福緣、求見名單開著沒、談話對象、今天各聊幾輪、情誼、名下、結識旗標、行狀與最新兩則紀錄。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "location": p.location, "stamina": p.stamina, "fame": p.stats.get("fame", 0), "xinde": p.stats.get("xinde", 0),
            "silver": p.stats.get("silver", 0), "fortune": p.fortune, "picking": p.picking_audience, "pending": p.pending_companion,
            "talks_today": dict(sorted(p.talks_today.items())), "affinities": dict(sorted(p.affinities.items())), "team": list(p.team),
            "met": sorted(f for f in p.flags if f.startswith("結識:")), "offered": p.last_offered_dialogue,
            "annals": [[a.kind, a.text, a.figure] for a in p.annals][-3:],
            "journal": [[e.title, e.tag, list(e.lines)] for e in state.journal[:2]]})

    def asks(self, who: str, tag: str, cids: list[str]) -> None:
        """伺服器假人與鈕上用的幾個查詢（在這裡交友會不會直接開口、交友是不是白跑一趟、見不見得到某位人物）。"""
        self.begin()
        game = self.server.game_for(who)
        emit(f"{who} {tag} 查詢", {"starts_dialogue": game.socialize_starts_dialogue(), "futile": game.socialize_is_futile(),
                                  "can_meet": {cid: game.can_meet_figure(cid) for cid in cids}})

    def press(self, who: str, option_id: str) -> None:
        """按一顆；先碰上一件留在交友的事（福緣、結識事件之類）就了結它。"""
        view = self.choose(who, option_id)
        if any(i.startswith("choice:") for i in self.ids(view)):
            self.settle_choices(who)

    def leave(self, who: str) -> None:
        state = self.chars.load(who)
        if state is not None and state.player.pending_companion:
            self.choose(who, "talk:leave")

    def reach(self, who: str, cid: str) -> None:
        """只有一位的地點找他說話：選單上有直接的「求見某某」就按它；一類一顆開著時沒有（單人求見併進交友那一顆），改按交友。"""
        if f"call:{cid}" in self.ids(self.main(who)):
            self.press(who, f"call:{cid}")
        else:
            self.press(who, "act:socialize")

    def open_list(self, who: str) -> None:
        """打開求見的名單：行動列上有 act:call（兩位以上的地點）就按它，沒有（舊存檔、改版後）直接擺成挑到一半。"""
        if "act:call" in self.ids(self.main(who)):
            self.choose(who, "act:call")
        else:
            self.edit(who, lambda p: setattr(p, "picking_audience", True))
        self.main(who)

    def seat(self) -> None:
        """福緣先全部記成領過（不然 place 把加入的日子推到很久以前，同步一下就先送上門）；福緣那幾位入座之後再還原。"""
        for who in self.PLAYERS:
            self.edit(who, lambda p: setattr(p, "fortune", True))
        super().seat()
        for who in self.FORTUNES:
            self.edit_state(who, lambda s: (setattr(s.player, "fortune", False), setattr(s.player, "joined_at", s.world.time)))
        # GIFT、GIFT2 留到後半（同伴全被招走之後）才還原
        for who in (self.GIFT, self.GIFT2):
            self.edit(who, lambda p: setattr(p, "fortune", True))
        self.edit(self.OVERDUE, lambda p: setattr(p, "joined_at", -1.0e9))

    # ── 前半 ──

    def alone(self) -> None:
        """交友，人物在（只有一位的地點）：名望夠 → 開口；名望不夠 → 被打發話或灰掉。模型回了。"""
        loc, cid = self.alone_spot()
        if cid is None:
            emit("這份內容沒有只有一位大勢人物的地點", None)
            return
        # 模型叫不動：開口退回體力（先做：之後名望夠的那位要談滿一輪，後半次數用完那一段才真的談滿）
        self.place(self.GREETER, loc)
        self.fame(self.GREETER, 9999)
        self.reach(self.GREETER, cid)
        self.you(self.GREETER, "求見・模型叫不動")
        self.leave(self.GREETER)
        MODEL["talk"] = {"stance": "suzhan"}
        for who, value, tag in ((self.GREETER, 9999, "名望夠"), (self.LOWFAME, 0, "名望不夠")):
            self.place(who, loc)
            self.fame(who, value)
            self.main(who)
            self.asks(who, f"交友・{tag}", [cid])
            self.press(who, "act:socialize")
            self.you(who, f"交友・{tag}之後")
            if self.chars.load(who).player.pending_companion:
                self.choose(who, "talk:0")  # 談一輪：記一輪（後半次數用完那一段看它）
            self.leave(who)
        # 選單上直接列的「求見某某」：名望夠，按下去開口（今天談過一輪，後半看次數）
        self.place(self.CALLER2, loc)
        self.fame(self.CALLER2, 9999)
        self.reach(self.CALLER2, cid)
        self.you(self.CALLER2, "直接求見")
        if self.chars.load(self.CALLER2).player.pending_companion:
            self.choose(self.CALLER2, "talk:0")  # 談一輪：記一輪（後半看次數）
        self.you(self.CALLER2, "直接求見・談了一輪")
        self.leave(self.CALLER2)
        MODEL["talk"] = None

    def absent(self) -> None:
        """交友，人物不在：幾處沒有大勢人物的地點（抽到交友事件就是事件；「此地無人可訪」那一支只有抽不到時才出現，這裡不保證走到）。"""
        for loc in ("runan_wilds", "nanyang_road", "yu_river", "town"):
            if not self.place(self.ABSENT, loc):
                continue
            self.fame(self.ABSENT, 9999)
            self.main(self.ABSENT)
            self.asks(self.ABSENT, f"交友・{loc}", [])
            self.press(self.ABSENT, "act:socialize")
            self.you(self.ABSENT, f"交友・{loc}之後")

    def hall(self) -> None:
        """求見，兩位以上的地點：名單、名望夠按人物、名望不夠被打發（或灰掉）、返回、清單外的 id、沒有人可以按的 id。"""
        loc, figs = self.hall_spot()
        if loc is None:
            emit("這份內容沒有兩位以上大勢人物的地點", None)
            return
        fig = figs[0]
        MODEL["talk"] = {"stance": "suzhan"}
        self.place(self.CALLER, loc)
        self.fame(self.CALLER, 9999)
        self.main(self.CALLER)
        self.asks(self.CALLER, "求見・名望夠", figs)
        self.open_list(self.CALLER)
        self.press(self.CALLER, f"call:{fig}")
        self.you(self.CALLER, "求見・名望夠")
        if self.chars.load(self.CALLER).player.pending_companion:
            self.choose(self.CALLER, "talk:0")  # 談一輪：記一輪（後半看次數）
        self.you(self.CALLER, "求見・談了一輪")
        self.leave(self.CALLER)
        for who in (self.BRUSHED, self.BRUSHED2):
            self.place(who, loc)
            self.fame(who, 0)
            self.main(who)
            self.asks(who, "求見・名望不夠", figs)
            self.open_list(who)
            self.press(who, f"call:{fig}")
            self.you(who, "求見・名望不夠")
        self.open_list(self.BRUSHED)
        self.press(self.BRUSHED, "call:back")
        self.you(self.BRUSHED, "求見・返回")
        self.press(self.BRUSHED, "call:zhugeliang_not_here")
        self.press(self.BRUSHED, "call:back")
        self.snubbed(loc, figs)
        MODEL["talk"] = None

    def snubbed(self, hall: str, figs: list[str]) -> None:
        """閉門不見（剛被他打敗，現實時間內他不見）：兩位以上的名單裡灰掉、只有一位的地點直接求見與交友都灰掉；硬按也沒事。"""
        from tianxia import figures

        spot, lone = self.alone_spot()
        # 閉門名單只蓋得到大勢人物（figures.of_character）：兩位以上的地點挑「有兩位以上大勢人物」的那一處；找不到就照原本的
        real = {loc: [cid for cid in fs if figures.of_character(self.c, cid) is not None] for loc, fs in self.layout().items()}
        halls = {loc: fs for loc, fs in real.items() if len(fs) >= 2}
        if halls:
            hall = sorted(halls, key=lambda x: (-len(halls[x]), x))[0]
            figs = halls[hall]
        if lone is not None and figures.of_character(self.c, lone) is None:
            lone = None
        names = [cid for cid in [*figs, lone] if cid is not None]
        until = {figures.of_character(self.c, cid): 1.0e12 for cid in names if figures.of_character(self.c, cid) is not None}
        self.edit(self.SNUB, lambda p: p.snubbed_until.update(until))
        self.fame(self.SNUB, 9999)
        self.place(self.SNUB, hall)
        self.main(self.SNUB)
        self.open_list(self.SNUB)
        self.press(self.SNUB, f"call:{figs[0]}")
        self.you(self.SNUB, "閉門不見・名單")
        self.leave(self.SNUB)  # 沒灰掉的話他開口了：告辭，後面的按鈕才不被談話擋住
        self.press(self.SNUB, "call:back")
        if lone is not None:
            self.place(self.SNUB, spot)
            self.main(self.SNUB)
            self.asks(self.SNUB, "閉門不見・只有一位", [lone])
            self.press(self.SNUB, f"call:{lone}")
            self.press(self.SNUB, "act:socialize")
            self.you(self.SNUB, "閉門不見・只有一位")
            self.leave(self.SNUB)

    def fortune(self) -> None:
        """結識奇遇：福緣到了（第 0 天起必定先觸發）交友先發入門的同伴；到期沒發生的自己送上門（同步）。"""
        with self.tuned(self.c.config, fortune_day_min=0):
            self.place(self.FORTUNE, "runan_wilds")
            self.main(self.FORTUNE)
            self.press(self.FORTUNE, "act:socialize")
            self.you(self.FORTUNE, "福緣・交友先發")
        self.main(self.OVERDUE)
        self.you(self.OVERDUE, "福緣・到期自己送上門")
        self.season_view("福緣之後")

    def list_open(self) -> None:
        """挑對象挑到一半（前半切在這裡）：求見名單開著、還沒按；一位名望夠、一位名望不夠、一位站在只有一位的地點（直接求見那顆）。"""
        loc, figs = self.hall_spot()
        if loc is None:
            return
        MODEL["talk"] = None
        self.place(self.WAITER, loc)
        self.fame(self.WAITER, 9999)
        self.open_list(self.WAITER)
        self.place(self.WAITER2, loc)
        self.fame(self.WAITER2, 0)
        self.open_list(self.WAITER2)
        self.place(self.WAITER3, loc)
        self.fame(self.WAITER3, 9999)
        self.open_list(self.WAITER3)

    def half(self) -> None:
        for who in self.PLAYERS:
            self.you(who, "前半停在這裡")
        self.season_view("前半停在這裡")

    # ── 後半 ──

    def list_on(self) -> None:
        """接著挑：名望夠的按人物（每日輪數調成 2：談第二輪時聊滿、自動告辭）；名望不夠的按人物（被打發或灰掉）、再打開、按返回；還有一位直接按返回。"""
        loc, figs = self.hall_spot()
        if loc is None:
            return
        fig = figs[0]
        MODEL["talk"] = {"stance": "suzhan"}
        with self.tuned(self.c.config, talk_turns_per_day=2):
            self.main(self.WAITER)
            self.press(self.WAITER, f"call:{fig}")
            self.you(self.WAITER, "接著按人物")
            for turn in (1, 2):
                if self.chars.load(self.WAITER).player.pending_companion:
                    self.choose(self.WAITER, "talk:0")
                    self.you(self.WAITER, f"談第 {turn} 輪（每日 2 輪，聊滿自動告辭）")
            self.leave(self.WAITER)
        MODEL["talk"] = None
        self.main(self.WAITER2)
        self.press(self.WAITER2, f"call:{fig}")
        self.you(self.WAITER2, "名望不夠的接著按人物")
        self.open_list(self.WAITER2)
        self.press(self.WAITER2, "call:back")
        self.you(self.WAITER2, "接著按返回")
        self.main(self.WAITER3)
        self.press(self.WAITER3, "call:back")
        self.you(self.WAITER3, "直接返回")

    def talked_out(self) -> None:
        """次數用完：每日輪數調成 1，前半談過一輪的人（只有一位的地點直接求見、兩位以上的名單）鈕灰掉、寫換日的那一刻，硬按也沒事。"""
        with self.tuned(self.c.config, talk_turns_per_day=1):
            loc, cid = self.alone_spot()
            if cid is not None:
                self.place(self.CALLER2, loc)
                self.asks(self.CALLER2, "次數用完・只有一位", [cid])
                self.reach(self.CALLER2, cid)
                self.you(self.CALLER2, "次數用完・只有一位")
                self.place(self.GREETER, loc)
                self.main(self.GREETER)
                self.press(self.GREETER, "act:socialize")
                self.you(self.GREETER, "次數用完・交友")
            hall, figs = self.hall_spot()
            if hall is not None:
                self.place(self.CALLER, hall)
                self.main(self.CALLER)
                self.open_list(self.CALLER)
                self.press(self.CALLER, f"call:{figs[0]}")
                self.you(self.CALLER, "次數用完・名單")
                self.press(self.CALLER, "call:back")

    def bots(self) -> None:
        """假人（人物情誼一軌的 BotRunner 十輪與整季機器人）；加上 bot_policy.score 問 call:、act:call、act:socialize 的各幾顆，與整季機器人看求見名單怎麼挑。"""
        super().bots()
        from tianxia import bot, bot_policy
        from tianxia.core.option import Option
        from tianxia.state import BotProfile

        self.begin()
        game = self.server.game_for(self.WAITER)
        profile = BotProfile(personality="普通", seed=3, faction="guan", season_number=self.world.get_season_number())
        cid = (self.hall_spot()[1] or [self.alone_spot()[1] or "luzhi"])[0]
        emit("假人眼中的分數", {oid: bot_policy.score(game, Option(id=oid, label=oid), profile) for oid in (
            f"call:{cid}", "call:back", "call:nobody", "act:call", "act:socialize")})
        loc, figs = self.hall_spot()
        if loc is None:
            return
        for who, value in ((self.BRUSHED, 0), (self.CALLER, 9999)):
            self.place(who, loc)
            self.fame(who, value)
            self.edit(who, lambda p: setattr(p, "picking_audience", True))
            self.begin()
            solo = self.server.game_for(who)
            opts = solo.options(odds=False)
            emit(f"整季機器人眼前的選單（{who}）", [o.id for o in opts])
            emit(f"整季機器人挑的（{who}）", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(30)}))
            self.edit(who, lambda p: setattr(p, "picking_audience", False))

    def gift(self) -> None:
        """結識奇遇，沒有同伴可給：同伴全被招走（名下記到別人）之後，到期的送賀禮（心得）、福緣到了的交友也送賀禮。"""
        for cid, ch in sorted(self.c.characters.items()):
            if ch.kind == "recruitable":
                with self.world.action_lock():
                    self.world.update_companion(cid, lambda pr: setattr(pr, "owner", "某位江湖客"))
        self.edit(self.GIFT, lambda p: (setattr(p, "fortune", False), setattr(p, "joined_at", -1.0e9)))
        self.main(self.GIFT)
        self.you(self.GIFT, "賀禮・到期自己送上門")
        self.edit(self.GIFT2, lambda p: setattr(p, "fortune", False))
        with self.tuned(self.c.config, fortune_day_min=0):
            self.place(self.GIFT2, "runan_wilds")
            self.main(self.GIFT2)
            self.press(self.GIFT2, "act:socialize")
            self.you(self.GIFT2, "賀禮・交友")

    def season(self) -> None:
        """收季、開下一季：談話次數、求見名單、福緣都跟著新角色重來。"""
        self.do(ADMIN, "end_season")
        self.main(self.WAITER)
        self.do(ADMIN, "next_season")
        for who in self.PLAYERS:
            self.main(who)
            self.you(who, "換季之後")
        self.season_view("換季之後")


# 改一個字（selftest）：談滿了的鈕括號裡那一句（「已經談滿 N 輪，…」；搬之前在 engine.py 的 Game._talked_out_note，搬之後在包裡），week7 次數用完那一段抓到
register_track("socialize", SocializeScenario, (("tianxia/engine.py", "tianxia/features/socialize/actions.py", "tianxia/features/socialize/view.py"),
                                               ('輪，{when}"', '輪！{when}"')), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "figure_acts", "gear", "guide", "heroines", "legacy", "looks", "mall", "military", "outlets", "peers",
                       "seal", "seclusion", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story", "tavern", "travel",
                       "zhuan"))  # 只改「輪，」那一小段：搬之前是 self._talk_cap()、搬之後是 talk_cap(ctx)，前面的字不同、這一段一樣
