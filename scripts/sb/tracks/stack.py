"""same_behavior 一軌一檔：stack（這一檔登記 stack）。"""
from __future__ import annotations

import random
from pathlib import Path

from sb.harness import ADMIN, CLOCK, emit, register_track
from sb.tracks.map import MapScenario
from sb.tracks.reckon import ReckonScenario

# core_seams（全部拆包第 56 批「選單收接縫」；計畫 docs/superpowers/plans/2026-11-06-選單收接縫-第56批.md 第七節）：這一段整段是第 56 批加的——
# 情境 StackScenario（--track stack，自己一個資料庫、自己切一半），最後一行登記。現有軌每一包只走自己那一層：兩層以上同時擺著誰排前面（選單接管、動身被擋那一句、閒著、哪一間店）
# 只有 map 一軌碰過最後五格，這一軌把它們一層一層疊滿再剝。角色的名字都是原創的（PM 11/04）；既有的軌一個字不動。


class StackScenario(MapScenario):
    """選單的先後一軌（全部拆包第 56 批；--track stack，自己一個資料庫）。借 map 的 setup、seat 與小工具。站的地方是自家大本營（測試內容是起點），
    記憶體裡補上城鎮、馬市、酒肆、醫館四個標籤、關掉照週解鎖、組一條答題的線（兩份程式同一步補，不寫輸出）：不然清失效參照一讀就把店收了，疊不起來。

    前半切在 pile：甄牧雲、殷照川、喬問樵疊滿了還沒有任何一下請求讀過。後半新程式第一次讀（實跑讀過輸出）：
    - take_order：甄牧雲照選單接管的先後一層一層剝，每一層看 /api/main、按前往（/api/travel、/api/map/state）、鎖裡讀閒著、哪一間店、選單、行動列底下那幾行、走不走得成。
      season21 走到事件 → 頭目戰 → 擂台 → 有所感 → 答題 → 談著 → 投靠 → 叛投 → 求見 → 懸賞榜 → 鐵匠鋪 → 馬市 → 酒肆 → 軍需官 → 打點 → 擂台邊 → 答話（前往那一句照另一張先後，下一段才一句一句看）。
      剝到閉關再疊上「跟著別人走在路上」：閉關 → 跟著（分道揚鑣那一顆）→ 自己走（折返、帶路的跟他說一句、喊停）→ 到了守著埋伏 → 全部拿掉。
    - block_order：殷照川照動身被擋的先後一層一層剝（擂台邊、談著、求見……的先後跟選單接管不一樣，一次剝看不出來）：頭目戰 → 擂台 → 擂台邊 → 談著 → 求見 → 懸賞榜 →
      鐵匠鋪 → 馬市 → 打點 → 軍需官 → 酒肆 → 投靠 → 叛投 → 答話 → 閉關，每一句都讀過。
    - gentry：聶停雲三格都在（選單是空的：待投靠的那一邊沒有可依附的，空的也算接管，選單接管不能拿「不是空的」判斷）→ 還沒挑邊 → 叛投 → 都了結（閒著與選單上有探索不一樣的那一層也在這裡）。
    - draft：鐵匠鋪單子開著時哪一間店回 None、選單是那一步的兩顆；拿掉單子回鐵匠鋪（只有武器開著的內容）。
    - doors：只有不是一類一顆的內容（測試內容）：此地一位人物的「求見某某」見得到、閉門不見、談滿了、名望不夠與行動列底下那一行，兩位人物的「求見」。
    - leave_town：不坐在店裡、身上留著舊的掌櫃那一句、停在哪一頁、挑到哪一張、帶路的人，動身之後一起清掉（出發那幾行不看坐不坐在店裡）。
    - machines：兩位假人也疊著（談著、求見、懸賞榜、鐵匠鋪、馬市、酒肆、答話），BotRunner 三輪照先後一層一層按掉（正式內容才上線）。ended：喬問樵疊著收季：休季的選單、賽季已結束那一句。

    **這一軌走不到的**（實跑數過）：序章那三支（測試內容與正式內容都不在序章：前往的「師父的話」、行動列底下回空、此地還能做的調息與體力玩法回空；tianxia/features/guide/tests/test_prologue.py 守）；
    宴席那一層（features_core.menu 這一批不動，宴客的軌走到）；休季用列傳的票（zhuan 一軌走到）；測試內容沒有頭目戰、有所感、陣營、懸賞榜、鐵匠鋪、馬市、軍需官、打點、答話，
    擺了也一讀就收（「疊上去的」那一行照寫，下一層看得到）；week7 馬市關著（同上）。"""

    TAKER, BLOCKED, ENDER = "甄牧雲", "殷照川", "喬問樵"
    DRAFTER, DOORS, ALLIED, LEAVER = "閔書硯", "溫叔夜", "聶停雲", "杜若衡"
    BOT_SEATS = ["疊甲", "疊乙"]
    QUIZ = "sb_stack"
    PHASES_FIRST = ["setup", "seat", "pile"]
    PHASES_SECOND = ["resume", "take_order", "block_order", "gentry", "draft", "doors", "leave_town", "machines", "ended"]
    TAKE_ORDER = ("event", "duel", "arena", "sense", "story", "talk", "faction", "defect", "audience", "bounty", "smith", "market",
                  "tavern", "donate", "dadian", "ring", "asking", "busy")
    BLOCK_ORDER = ("event", "duel", "arena", "ring", "talk", "audience", "bounty", "smith", "market", "dadian", "donate", "tavern",
                   "faction", "defect", "asking", "busy")
    FLAT = {"audience": "picking_audience", "bounty": "picking_bounty", "smith": "picking_smith", "market": "picking_market",
            "tavern": "picking_tavern", "donate": "picking_donate", "dadian": "picking_dadian", "ring": "picking_arena"}
    SINGLE = {"duel": "duel", "arena": "arena", "sense": "sensing", "talk": "pending_companion", "faction": "pending_faction",
              "defect": "pending_defect", "asking": "fs_asking", "busy": "busy_until"}

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import clinic, equipment, mounts
        from tianxia.features.tavern import rules as tavern_rules

        guan = next((f for f in self.c.scenario.factions if f.id == "guan"), None)
        self.spot = guan.join_at[0] if guan is not None and guan.join_at else self.hub()
        loc = self.c.locations[self.spot]
        tags = list(loc.tags or [])
        for tag in (equipment.TOWN_TAG, mounts.MARKET_TAG, tavern_rules.TAG, clinic.CLINIC_TAG):
            if tag not in tags:
                tags.append(tag)
        self.c.locations[self.spot] = loc.model_copy(update={"tags": tags})
        self.c.config.jianfa.week_unlock = False  # 懸賞榜與擂台照週解鎖：關掉才疊得上（同 bout 一軌；兩個行程都關，不寫輸出）
        self.c.storylines[self.QUIZ] = self.quiz_line()  # 答題那一段：正式內容沒有這一種，自己組一條（同 story 一軌；start 是 None，只有這裡擺得上）

    def quiz_line(self):
        from tianxia.models import StoryAnswer, StoryDef, StoryEnding, StoryQuestion, StoryStage

        question = StoryQuestion(text="疊到這一層，你如何？", answers=[StoryAnswer(text="往前", marks={"攻": 1}), StoryAnswer(text="往後", marks={"守": 1})])
        ending = StoryEnding(id="done", title="收場", text="這一問就這樣收了。", annal="{name}答完了那一問。", weight=3)
        return StoryDef(id=self.QUIZ, title="疊層一問", intro="有人攔路問你一件事。", endings=[ending],
                        stages=[StoryStage(id="ask", kind="quiz", hint="答這一問", next="done", questions=[question])])

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            fn(state)
            self.chars.save(state)

    # ── 一層一層 ──

    def other_side(self) -> str | None:
        return "huang" if self.factions_on() else None

    def value_of(self, who: str, name: str):
        """這一層要擺的值；這份內容沒有這一層回 None。"""
        from tianxia import insights
        from tianxia.state import ArenaFight, ArenaSide, DuelState, Sensing

        c = self.c
        if name == "duel":
            return DuelState(boss=sorted(c.duels)[0], foe=0, hp=100.0, hp_cap=100.0, hp_start=100.0, power=50.0) if c.duels else None
        if name == "arena":
            side = {"power": 50.0, "hp": 100.0, "hp_cap": 100.0}
            return ArenaFight(id=1, foe_key="無此人", me=ArenaSide(name=who, **side), foe=ArenaSide(name="無此人", **side))
        if name == "sense":
            scenes = insights.scenes_for(c.locations[self.spot], c)
            if not scenes:
                return None
            return Sensing(location=self.spot, scene=scenes[0].id, order=list(range(len(scenes[0].methods))))
        if name == "talk":
            return sorted(c.characters)[0] if c.characters else None
        if name in ("faction", "defect"):
            return self.other_side()
        if name == "asking":
            return self.chain_id()
        if name == "busy":
            return 4.0e9
        return True

    def event_of(self) -> str | None:
        return sorted(self.c.events)[0] if self.c.events else None

    def put(self, who: str, name: str) -> bool:
        """擺上一層；這份內容擺不上回 False（寫進輸出）。"""
        from tianxia.state import StoryProgress

        if name == "event":
            event = self.event_of()
            if event is None:
                return False
            self.edit_state(who, lambda s: setattr(s, "pending_event", event))
        elif name == "story":
            def open_quiz(p):
                p.storylines[self.QUIZ] = StoryProgress(line=self.QUIZ, stage="ask", opened=True)
                p.story_open = self.QUIZ

            self.edit(who, open_quiz)
        else:
            value = self.value_of(who, name)
            if value is None:
                return False
            field = self.FLAT.get(name) or self.SINGLE[name]
            self.edit(who, lambda p, field=field, value=value: setattr(p, field, value))
        return True

    def take_off(self, who: str, name: str) -> None:
        if name == "event":
            self.edit_state(who, lambda s: setattr(s, "pending_event", None))
        elif name == "story":
            self.edit(who, lambda p: setattr(p, "story_open", None))
        elif name in self.FLAT:
            self.edit(who, lambda p, field=self.FLAT[name]: setattr(p, field, False))
        else:
            self.edit(who, lambda p, field=self.SINGLE[name]: setattr(p, field, None))

    def stack(self, who: str, order: tuple[str, ...]) -> None:
        """由下往上疊（直接改資料庫，這一下之後沒有請求讀過）。"""
        placed = [name for name in reversed(order) if self.put(who, name)]
        emit(f"{who} 疊上去的（下面的先擺）", placed)

    def inner(self, who: str, tag: str, other: str | None) -> None:
        """鎖裡讀：閒著（_idle、is_idle）、哪一間店、那一串是不是眼前的選單、行動列底下那幾行（五種 id 都問，不只選單上有的）、走不走得成。"""
        self.begin()
        game = self.server.game_for(who)
        ids = ["act:explore", "act:train", "act:socialize", "act:call", *(f"call:{cid}" for cid in sorted(self.c.characters)[:1])]
        with self.server._locked(game):
            emit(f"{who} {tag} 鎖裡", {"idle": game._idle(), "is_idle": game.is_idle(), "shop": game._shop_open(), "live": game._shop_live(),
                                     "ids": [o.id for o in game.options(odds=False, tick=False)],
                                     "notes": list(game.action_notes(ids).items()),
                                     "refusal": None if other is None else game.travel_refusal(other)})
        self.server.GAMES.clear()

    def view(self, who: str, tag: str, other: str | None) -> None:
        self.main(who)
        self.go_to(who, other)
        self.inner(who, tag, other)

    def enroll_at(self, who: str, side: str | None) -> None:
        self.enroll(who, side, self.spot)
        self.edit(who, lambda p: p.stats.update({"silver": 200}))

    # ── 前半 ──

    def pile(self) -> None:
        """切點：疊滿了，後面沒有任何一下請求讀過。"""
        for who in (self.TAKER, self.BLOCKED, self.ENDER, self.DRAFTER, self.DOORS, self.ALLIED, self.LEAVER):
            self.enroll_at(who, "guan")
        self.stack(self.TAKER, self.TAKE_ORDER)
        self.stack(self.BLOCKED, self.BLOCK_ORDER)
        self.stack(self.ENDER, ("event", "talk", "audience", "bounty", "smith", "market", "tavern", "ring", "asking"))

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def peel(self, who: str, order: tuple[str, ...], tag: str) -> str | None:
        other = next((i for i in sorted(self.c.locations) if i != self.spot and not self.c.locations[i].prologue_only and not self.c.locations[i].unlock_flag), None)
        for name in order:
            self.view(who, f"{tag} 最上面是 {name}", other)
            self.take_off(who, name)
        return other

    def take_order(self) -> None:
        other = self.peel(self.TAKER, self.TAKE_ORDER[:-1], "照選單接管的先後")
        self.road_tail(self.TAKER, other)

    def road_tail(self, who: str, other: str | None) -> None:
        """閉關還擺著，疊上跟著別人走在路上：閉關 → 跟著 → 自己走（帶路的那一顆）→ 到了守著埋伏 → 全部拿掉。"""
        from tianxia.state import Journey

        path = sorted(i for i in self.c.locations[self.spot].connections)[:1]
        path = [*path, next(i for i in sorted(self.c.locations) if i not in (self.spot, *path) and not self.c.locations[i].prologue_only)]
        escort = sorted(self.c.characters)[0] if self.c.characters else None

        def walking(p):
            p.journey = Journey(mode="walk", path=path, arrive_at=[4.0e9, 4.1e9])
            p.parley_escort = escort

        self.edit(who, walking)
        self.follow(who, self.GUAN)
        self.view(who, "閉關又跟著人走在路上", other)
        self.take_off(who, "busy")
        self.view(who, "跟著人走在路上", other)
        self.edit(who, lambda p: setattr(p, "tagalong", None))
        self.view(who, "自己走在路上（帶路的人在）", other)

        def arrived(p):
            p.journey, p.parley_escort = None, None

        self.edit(who, arrived)
        self.lay_ambush(who)
        self.view(who, "到了守著埋伏", other)
        self.edit(who, lambda p: setattr(p, "ambush", None))
        self.main(who)
        self.inner(who, "全部拿掉", other)

    def block_order(self) -> None:
        other = self.peel(self.BLOCKED, self.BLOCK_ORDER, "照動身被擋的先後")
        self.main(self.BLOCKED)
        self.inner(self.BLOCKED, "全部拿掉", other)

    def gentry(self) -> None:
        """投靠待確認 → 拜入了還沒挑邊 → 叛投待確認（動身被擋的先後在陣營那一格裡；選單接管的先後是還沒挑邊在前）。"""
        gentry = next((f for f in self.c.scenario.factions if f.allies), None)
        if gentry is None:
            emit("這份內容沒有要依附的陣營", None)
            return
        who = self.ALLIED
        other = next(i for i in sorted(self.c.locations) if i != self.spot and not self.c.locations[i].prologue_only)

        def pending(p):
            p.faction, p.ally = gentry.id, None
            p.pending_faction, p.pending_defect = self.other_side(), self.other_side()

        self.edit(who, pending)
        self.view(who, "三格都在", other)
        self.take_off(who, "faction")
        self.view(who, "還沒挑邊與叛投", other)
        self.edit(who, lambda p: setattr(p, "ally", "guan"))
        self.view(who, "叛投", other)
        self.take_off(who, "defect")
        self.view(who, "都了結", other)

    def draft(self) -> None:
        """鐵匠鋪的單子開著：哪一間店回 None（店面上的鈕在單子那一步不在選單上）；拿掉單子回鐵匠鋪。"""
        from tianxia.state import SmithDraft

        who = self.DRAFTER

        def sit(p):
            p.picking_smith, p.smith_draft = True, SmithDraft(kind="劍")

        self.edit(who, sit)
        self.main(who)
        self.inner(who, "鐵匠鋪單子開著", None)
        self.edit(who, lambda p: setattr(p, "smith_draft", None))
        self.main(who)
        self.inner(who, "鐵匠鋪單子拿掉", None)

    def doors(self) -> None:
        """此地一位人物（不是一類一顆的內容才有這一顆）：見得到、閉門不見、名望不夠、談滿了；兩位人物是「求見」打開名單。人物表照內容補在記憶體裡。"""
        from tianxia import precise, rules
        from tianxia.engine import Game

        who = self.DOORS
        if precise.on(self.c, self.world.get_season()):
            emit("一類一顆開著，沒有單人求見那一顆", None)
            return
        chars = sorted(self.c.characters)
        one = chars[0]
        self.c.characters[one] = self.c.characters[one].model_copy(update={"deep_interaction": True, "talk_at": self.spot, "audience_fame": 0})
        self.main(who)
        self.inner(who, "一位人物見得到", None)
        snubbed = Game._snubbed_character  # 測試內容沒有大勢人物表，閉門不見只能這樣擺（同 tests/core/test_engine.py 那一條）
        Game._snubbed_character = lambda self, character_id: True
        try:
            self.main(who)
            self.inner(who, "一位人物閉門不見", None)
        finally:
            Game._snubbed_character = snubbed
        day = rules.game_day(self.c, self.world.get_season())
        self.edit(who, lambda p: setattr(p, "talks_today", {one: [day, 99]}))
        self.main(who)
        self.inner(who, "一位人物談滿了", None)
        self.edit(who, lambda p: setattr(p, "talks_today", {}))
        self.c.characters[one] = self.c.characters[one].model_copy(update={"audience_fame": 10 ** 6})
        self.main(who)
        self.inner(who, "一位人物名望不夠", None)
        self.c.characters[one] = self.c.characters[one].model_copy(update={"audience_fame": 0})
        if len(chars) > 1:
            self.c.characters[chars[1]] = self.c.characters[chars[1]].model_copy(update={"deep_interaction": True, "talk_at": self.spot})
            self.main(who)
            self.inner(who, "兩位人物", None)

    def leave_town(self) -> None:
        """不坐在店裡、身上留著舊的掌櫃那一句、停在哪一頁、挑到哪一張、帶路的人：動身之後一起清掉（出發那幾行不看坐不坐在店裡）。"""
        who = self.LEAVER
        fields = ("shop_line", "shop_clue", "shop_hold", "smith_page", "smith_rule", "bounty_pick", "parley_escort", "picking_bounty", "picking_smith", "picking_market")
        other = next(i for i in sorted(self.c.locations) if i != self.spot and not self.c.locations[i].prologue_only and not self.c.locations[i].unlock_flag)

        def leftovers(p):
            p.shop_line, p.shop_clue, p.shop_hold = "舊話", "舊線索", "舊留話"
            p.smith_page, p.smith_rule, p.bounty_pick = "armor", "舊規矩", "沒有這一張"
            p.parley_escort = sorted(self.c.characters)[0] if self.c.characters else None

        self.edit(who, leftovers)
        ReckonScenario.looks(self, who, "動身之前", fields)
        self.go_to(who, other)
        ReckonScenario.looks(self, who, "動身之後", fields)

    def machines(self) -> None:
        """假人碰得到：兩位假人也疊著（談著、求見、三間店、酒肆、答題），BotRunner 三輪；看選單與欄位。"""
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        if not self.factions_on():
            emit("這份內容沒有陣營，假人不上線", None)
            return
        season = self.world.get_season_number()
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            side = "guan" if i == 0 else "huang"
            p.bot = BotProfile(personality="普通", seed=91 + i, faction=side, season_number=season)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = side, self.spot, None
            p.visited.add(self.spot)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            self.chars.save(g.state)
        ReckonScenario.bot_rounds(self, 2)  # 先輪兩輪：剛上線那幾下（入伍的事件）過掉，疊起來的才是眼前的選單

        def back_here(s):
            s.pending_event, s.player.location, s.player.journey = None, self.spot, None
            s.player.busy_until, s.player.stamina = None, float(self.c.config.stamina_max)

        for name in self.BOT_SEATS:
            self.edit_state(name, back_here)
            self.stack(name, ("talk", "audience", "bounty", "smith", "market", "tavern", "asking"))
        ReckonScenario.bot_rounds(self, 3)
        for name in self.BOT_SEATS:
            ReckonScenario.looks(self, name, f"假人 {name} 輪過之後", ("pending_companion", *self.FLAT.values(), "fs_asking", "location", "journey", "stamina"))
            self.begin()
            game = Game(self.c, self.chars.load(name), random.Random(5), self.world)  # 同 BotRunner 建 Game（server.game_for 認不得假人的名號）
            emit(f"假人 {name} 此刻的選單", {"ids": [o.id for o in game.options(odds=False, tick=False)], "idle": game._idle(), "shop": game._shop_open()})

    def ended(self) -> None:
        """喬問樵還疊著就收季：休季的選單、賽季已結束那一句；_idle 照舊是假的。"""
        other = next(i for i in sorted(self.c.locations) if i != self.spot and not self.c.locations[i].prologue_only and not self.c.locations[i].unlock_flag)
        self.view(self.ENDER, "收季之前", other)
        self.do(ADMIN, "end_season")
        self.view(self.ENDER, "收季之後", other)


# 改一個字（selftest）：投靠待確認時動身被擋的那一句（第 2 段搬進陣營包 join_actions.py，這一句一字不動；搬到別的檔就補這裡的檔清單）
register_track("stack", StackScenario, (("tianxia/atlas.py", "tianxia/features/faction/join_actions.py"),
                                        ("投靠還沒決定，先決定再安排前往", "投靠還沒決定，先決定再安排前往！")), "season21",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "hire", "legacy", "looks", "mall", "map",
                       "military", "notify", "outlets", "peers", "persona", "seal", "seclusion", "sense", "smithy", "socialize",
                       "sortie", "stamina_plays", "story", "tale", "tavern", "territory_acts", "travel", "zhuan"))
