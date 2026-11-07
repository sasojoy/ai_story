"""same_behavior 一軌一檔：whetstone（這一檔登記 whetstone）。"""
from __future__ import annotations

import importlib
import random
from contextlib import contextmanager
from types import SimpleNamespace as NS
from unittest import mock

from sb.harness import emit, register_track
from sb.tracks.tally import TallyScenario

# ═══════════════════════════ 假人二（第二輪第 101 批）：--track whetstone ═══════════════════════════

PACKS = ("battle", "bounties", "checkin", "craft", "cultivation", "explore", "faction", "gear", "outlets", "peers", "sense", "smithy", "stamina_plays", "travel")


class WhetstoneScenario(TallyScenario):
    """假人的按法現有的軌走不到的那幾支一軌（第二輪第 101 批；--track whetstone，自己一個資料庫）。開工那一筆量過（sys.monitoring 記 bot、bot_policy 走到的行，100 次實跑）：
    熔最弱的一門整支沒有一軌走到；配點只走到五項屬性那一支；還有幾支各缺一兩行（自創的退路、神器原品定名、有所感與定名與頓悟沒名額的那幾支、投效怎麼挑、守著埋伏走不開）。

    前半切在 half：四個假人的武學事停在寫到一半，是舊程式寫進存檔的。後半新程式接手（實跑讀過輸出）：
    - handoff：BotRunner 兩輪接手那四樣（week7、season21）：磨甲的單子取好名、收進庫；磨乙的絕學定了名；磨丙的有所感畫完收到意境；磨丁的頓悟收到悟:1。
    - 其餘每一段照舊叫公開的 bot、bot_policy，每一格直接問，只問不存；條件用 mock 換掉。換的名字兩份程式都叫得到：Game 的公開方法、規則模組的屬性；bot、bot_policy 搬走的經 swapped 全部換。
    - machines：大家站回開酒肆的城，BotRunner 再跑幾輪。

    加上這一軌，開工那一筆量過搬的函式只剩 bot.visit_smith 三行沒有一軌走到（單子走到一半收掉、兩頁打造時下一顆按不下去的 break）。
    **這一軌走不到的**（實跑讀過）：測試內容的假人不上線（一輪全是 0，那四樣照舊停著）、磨乙沒有身上那一門（naming 是 null）、沒有場景與神品（磨丙、磨丁是 null）、自創開不了單（draft_ways 全是 false）、沒有可升的料。
    """

    BOT_SEATS = [("磨甲", "guan", "act:smith"), ("磨乙", "huang", "act:market"), ("磨丙", None, "act:bounties"), ("磨丁", "guan", "act:tavern")]
    PHASES_FIRST = ["setup", "seat", "bot_seats", "half"]
    PHASES_SECOND = ["resume", "handoff", "melt_ways", "point_ways", "draft_ways", "original_ways", "sense_ways", "master_ways", "god_ways",
                     "forge_ways", "enlist_ways", "rally_ways", "shop_ways", "machines"]
    ROUNDS = 3

    # ── 小工具 ──

    @contextmanager
    def swapped(self, **names):
        """換假人的名字：搬之前在 bot、bot_policy，搬之後在 bot_base、各包的 bots.py（舊名 re-export）。compare 拿 head 的腳本跑兩棵樹，有這個名字的全部換，兩邊都打得到。"""
        holders = []
        for name in ("tianxia.bot", "tianxia.bot_policy", "tianxia.bot_base", *(f"tianxia.features.{p}.bots" for p in PACKS)):
            try:
                holders.append(importlib.import_module(name))
            except ImportError:  # 搬之前還沒有這一檔
                pass
        saved = [(m, n, getattr(m, n)) for m in holders for n in names if hasattr(m, n)]
        for m, n, _ in saved:
            setattr(m, n, names[n])
        try:
            yield
        finally:
            for m, n, old in saved:
                setattr(m, n, old)

    @staticmethod
    def pressing():
        """Game.choose 換成只記按了哪一顆（回那一份清單與 patch）。"""
        from tianxia.engine import Game

        pressed: list[str] = []
        return pressed, mock.patch.object(Game, "choose", lambda self, oid: pressed.append(oid) or [f"按 {oid}"])

    def fresh(self, name: str, **player):
        """一份不存的 Game，站著、不在路上；player 是另外改的欄位。"""
        g = self.game_of(name)
        p = g.state.player
        self.stand_up(p)
        p.journey = None
        for key, value in player.items():
            setattr(p, key, value)
        return g, p

    @staticmethod
    def slot_view(slot):
        return None if slot is None else [type(slot.job).__name__, slot.skipped]

    @staticmethod
    def draft_view(p):
        return None if p.creating is None else [p.creating.kind, p.creating.step, p.creating.paid, p.creating.name_tries]

    def picture(self, tag: str) -> None:
        for name, _, _ in self.BOT_SEATS:
            p = self.chars.load(name).player
            emit(f"{name} {tag}", {"draft": self.draft_view(p), "naming": p.naming, "sensing": p.sensing and p.sensing.stage,
                                 "god": p.god_naming and [p.god_naming.asked, p.god_naming.candidates], "arts": list(p.arts), "insights": list(p.insights),
                                 "xinde": p.stats.get("xinde", 0)})

    # ── 情境 ──

    def half(self) -> None:
        """前半切在這裡（舊程式寫進存檔）：磨甲的自創單子付過心得、停在取名；磨乙的絕學等定名；磨丙的有所感等著畫那一筆；磨丁的頓悟等著取名。測試內容沒有的（形、場景、神品）照實寫 null。"""
        from tianxia.features.craft import create
        from tianxia.features.sense import sensing
        from tianxia.state import GodNaming

        self.begin()
        with self.world.action_lock():
            g = self.game_of("磨甲")
            p = g.state.player
            p.stats["xinde"] = 500
            forms = [f.key for f in create.forms_of(self.c, "武學")]
            emit("磨甲 開得了單", [create.allowed(g.state, self.c), forms[:1]])
            if forms and create.allowed(g.state, self.c) is None:
                names = [x.name for x in self.c.create_forms.presets] or [create.DEFAULT_PRESET]
                g.create_begin("武學", forms[0])
                if p.creating is not None:
                    g.create_pose(create.preset(self.c, names[0]))
                    g.create_intent("風過林梢，影不留痕")
            self.chars.save(g.state)
        self.edit("磨乙", lambda p: setattr(p, "naming", p.member.wugong_id))
        scene = next((s for _, s in sorted(self.c.insight_scenes.items())), None)
        if scene is not None:
            with self.world.action_lock():
                g = self.game_of("磨丙")
                sensing.start(g.state, self.c, scene, random.Random(0))
                g.state.player.sensing.stage, g.state.player.sensing.method = "draw", scene.methods[0].attribute
                self.chars.save(g.state)
        god = next(iter(sorted(t.id for t in self.c.traits.god)), None)
        if god is not None:
            self.edit("磨丁", lambda p: setattr(p, "god_naming", GodNaming(line="whetstone", god=god, attribute="柔", place=p.location)))
        self.picture("前半停在這裡")

    def handoff(self) -> None:
        """BotRunner 兩輪接手舊程式寫到一半的那四樣（沒有模型，走字表與靜心思名）。"""
        self.bot_rounds(2)
        self.picture("接手之後")

    def melt_ways(self) -> None:
        """熔最弱的一門：庫裡有兩三門熔第十成威力最低的；庫是空的化一個沒裝的意境；tend_arts 與 forge_and_cultivate 庫滿那一支（library.full 換掉）。"""
        from tianxia import bot, bot_policy as bp, library, team

        self.begin()
        with self.world.action_lock():
            g, p = self.fresh("磨甲", creating=None)
            ids = [a for a in sorted(self.c.skills) if team.player_art(g.state, self.c, self.world, a) is not None][:4]
            p.arts = list(ids)
            emit("庫裡", [[a, team.player_art(g.state, self.c, self.world, a).top_power] for a in ids])
            emit("熔一門", [self.safe(lambda: bot.melt_the_weakest(g)), list(p.arts)])
            p.arts = []
            p.insights = sorted(self.c.insights)[:2]
            emit("庫空了化意境", [self.safe(lambda: bot.melt_the_weakest(g)), list(p.insights)])
            p.insights = []
            emit("什麼都沒有", [self.safe(lambda: bot.melt_the_weakest(g)), list(p.insights)])
            p.arts = list(ids)
            with mock.patch.object(library, "full", return_value=True):
                emit("tend_arts 庫滿", [self.safe(lambda: bp.tend_arts(g, random.Random(3), bp.NamingSlot(open=True))), list(p.arts)])
                p.arts = list(ids)
                emit("forge_and_cultivate 庫滿", [self.safe(lambda: bot.forge_and_cultivate(g, random.Random(4))), list(p.arts)])

    def point_ways(self) -> None:
        """配點三支（五項屬性、五段、隨機）× 照常、被拒絕；隨機那一支全到頂。attrset.on、jianfa 換掉才走得到另外兩支。"""
        from tianxia import attrset, bot, team
        from tianxia.engine import Game

        real_on = attrset.on
        self.begin()
        rows = (("照設定", None, False, False, False), ("照設定 被拒絕", None, False, True, False),
                ("五段", False, True, False, False), ("五段 被拒絕", False, True, True, False),
                ("隨機", False, False, False, False), ("隨機 被拒絕", False, False, True, False), ("隨機 全到頂", False, False, False, True))
        with self.world.action_lock():
            for tag, on, miles, refuse, capped in rows:
                g, p = self.fresh("磨乙", naming=None, stat_points=3)
                if capped:
                    p.stats.update({k: self.c.config.stat_cap for k in team.COMBAT_STATS})
                refused = mock.patch.object(Game, "allocate_stat", lambda self, k: []) if refuse else mock.patch.object(Game, "allocate_stat", Game.allocate_stat)
                with mock.patch.object(attrset, "on", real_on if on is None else (lambda *a, **k: on)), refused, \
                        self.swapped(jianfa=lambda c, w, key: miles and key == "stat_milestones") if on is False else self.swapped():
                    got = self.safe(lambda: bot.allocate_points(g, random.Random(2)))
                emit(f"配點 {tag}", [got, p.stat_points, {k: p.stats.get(k, 0) for k in sorted(team.COMBAT_STATS)}])

    def draft_ways(self) -> None:
        """自創的退路：照常、沒有形、開不了單、立意不成、名字都撞、前一張單子沒付心得；換到最後每一張都看單子還在不在。測試內容沒有形：照實寫。"""
        from tianxia import bot
        from tianxia.features.craft import create
        from tianxia.engine import Game

        self.begin()
        rows = (("照常", None), ("沒有形", mock.patch.object(create, "forms_of", return_value=[])), ("開不了單", mock.patch.object(Game, "create_begin", lambda self, *a: [])),
                ("立意不成", mock.patch.object(Game, "create_intent", lambda self, *a: [])), ("名字都撞", mock.patch.object(Game, "create_name", lambda self, *a: [])))
        with self.world.action_lock():
            for tag, dial in rows:
                g, p = self.fresh("磨丙", sensing=None, creating=None)
                p.stats["xinde"] = 500
                if dial is None:
                    got = self.safe(lambda: bot.create_art(g, random.Random(5)))
                else:
                    with dial:
                        got = self.safe(lambda: bot.create_art(g, random.Random(5)))
                emit(f"自創 {tag}", [got, self.draft_view(p), p.stats.get("xinde", 0)])
            g, p = self.fresh("磨丙", sensing=None, creating=None)
            p.stats["xinde"] = 500
            forms = [f.key for f in create.forms_of(self.c, "武學")]
            if forms:
                g.create_begin("武學", forms[0])
            emit("自創 單子沒付", [self.draft_view(p), self.safe(lambda: bot.create_art(g, random.Random(6))), self.draft_view(p)])

    def original_ways(self) -> None:
        """神器原品定名：手上有等著定名的（unnamed_originals 換掉）一律按沿用譜名（Game.name_divine 換成只記這一下）。"""
        from tianxia import bot, bot_policy as bp, forge_secrets
        from tianxia.engine import Game

        self.begin()
        g, _ = self.fresh("磨丁", god_naming=None)
        with mock.patch.object(forge_secrets, "unnamed_originals", return_value=["甲件", "乙件"]), self.swapped(DIVINE_NAME_CHANCE=1.0), \
                mock.patch.object(Game, "name_divine", lambda self, item, keep=False: [f"定名 {item} {keep}"]):
            emit("_name_originals", self.safe(lambda: bp._name_originals(g, random.Random(0))))
            emit("keep_book_names", self.safe(lambda: bot.keep_book_names(g)))

    def sense_ways(self) -> None:
        """有所感：不在感悟裡；要畫的時候那一筆讀不出來、要取名（名額開著、關著、沒有 slot）、不必取名。整季機器人那一支（bot.sense_draw）讀不出來時順其自然。"""
        from tianxia import bot, bot_policy as bp
        from tianxia.features.sense import sensing
        from tianxia.engine import Game

        self.begin()
        with self.world.action_lock():
            g, _ = self.fresh("磨丙", sensing=None)
            emit("sense_pick 不在感悟裡", bot.sense_pick(g, random.Random(0)))
            emit("_sense 不在感悟裡", self.safe(lambda: bp._sense(g, random.Random(0), None)))
            pressed, press = self.pressing()
            stroke = (lambda game, rng, same=False: [[0.0, float(same)]])
            with press, self.swapped(sense_pick=lambda game, rng: sensing.DRAW, sense_stroke=stroke), \
                    mock.patch.object(Game, "sense_draw", lambda self, req, proposed=None: [f"畫 {proposed}"]):
                for tag, req in (("讀不出來", "讀不出來"), ("要取名", NS(needs_name=True)), ("不必取名", NS(needs_name=False))):
                    for way, slot in (("開著", bp.NamingSlot(open=True)), ("關著", bp.NamingSlot(open=False)), ("沒有", None)):
                        with mock.patch.object(Game, "sense_request", lambda self, points, png="", r=req: r):
                            got = self.safe(lambda: bp._sense(g, random.Random(1), slot))
                        emit(f"_sense {tag} 名額{way}", [got, self.slot_view(slot), list(pressed)])
                        pressed.clear()
                with mock.patch.object(Game, "sense_request", lambda self, points, png="": "讀不出來"):
                    emit("bot.sense_draw 讀不出來", [self.safe(lambda: bot.sense_draw(g, random.Random(1))), list(pressed)])

    def master_ways(self) -> None:
        """絕學定名的 A 段：沒有單（賽季籌備中那種）、名額開著、關著、沒有 slot。"""
        from tianxia import bot_policy as bp
        from tianxia.engine import Game

        self.begin()
        with self.world.action_lock():
            g, _ = self.fresh("磨乙", naming="whetstone_art")
            for tag, req in (("沒有單", None), ("有單", "單子")):
                for way, slot in (("開著", bp.NamingSlot(open=True)), ("關著", bp.NamingSlot(open=False)), ("沒有", None)):
                    with mock.patch.object(Game, "mastery_request", lambda self, r=req: r):
                        got = self.safe(lambda: bp._master(g, slot))
                    emit(f"_master {tag} 名額{way}", [got, self.slot_view(slot)])

    def god_ways(self) -> None:
        """頓悟取名：沒有單、不是假人程式來的、叫不到模型、名額關著、開著；想過了沒有候選、有候選。"""
        from tianxia import bot_policy as bp
        from tianxia.engine import Game
        from tianxia.state import GodNaming

        self.begin()
        with self.world.action_lock():
            g, p = self.fresh("磨丁", god_naming=GodNaming(line="whetstone", god="x", attribute="柔"))
            pressed, press = self.pressing()
            with press:
                for tag, req, slot in (("沒有單", None, bp.NamingSlot(open=True)), ("沒有 slot", "單子", None), ("叫不到模型", "單子", bp.NamingSlot(open=True, model=False)),
                                       ("名額關著", "單子", bp.NamingSlot(open=False)), ("名額開著", "單子", bp.NamingSlot(open=True))):
                    with mock.patch.object(Game, "epiphany_request", lambda self, r=req: r):
                        got = self.safe(lambda: bp._god_name(g, random.Random(0), slot))
                    emit(f"_god_name {tag}", [got, self.slot_view(slot), list(pressed)])
                    pressed.clear()
                p.god_naming.asked = True
                emit("_god_name 想過了沒有候選", self.safe(lambda: bp._god_name(g, random.Random(0), None)))
                p.god_naming.candidates = ["寒潭", "孤峰", "斷雲"]
                emit("_god_name 有候選", [self.safe(lambda: bp._god_name(g, random.Random(7), None)), list(pressed)])

    def forge_ways(self) -> None:
        """開一爐：要名字（名額開著、關著、沒有 slot）、不必名字（給 NO_NAME）；挑一爐（MERGE_SHARE 換成 1）：合得了、都合不了、體力不夠。"""
        from tianxia import bot, bot_policy as bp, fusion
        from tianxia.engine import Game

        self.begin()
        with self.world.action_lock():
            g, p = self.fresh("磨甲", creating=None)
            plan = bot.ForgePlan(("甲", "乙"))
            with mock.patch.object(Game, "forge", lambda self, art, ids, proposed=None: [f"開爐 {art} {ids} {proposed}"]):
                for tag, req in (("要名字", "單子"), ("不必名字", None)):
                    for way, slot in (("開著", bp.NamingSlot(open=True)), ("關著", bp.NamingSlot(open=False)), ("沒有", None)):
                        with mock.patch.object(Game, "forge_request", lambda self, art, ids, named_outside=False, r=req: r):
                            got = self.safe(lambda: bp._forge(g, plan, slot))
                        emit(f"_forge {tag} 名額{way}", [got, self.slot_view(slot)])
            p.insights, p.stamina = ["甲", "乙", "丙"], 100.0
            with self.swapped(MERGE_SHARE=1.0):
                for tag, problem in (("合得了", None), ("都合不了", "不行")):
                    with mock.patch.object(fusion, "merge_problem", return_value=problem):
                        emit(f"pick_forge {tag}", self.safe(lambda: bot.pick_forge(g, random.Random(8))))
                p.stamina = 0.0
                emit("pick_forge 體力不夠", self.safe(lambda: bot.pick_forge(g, random.Random(8))))

    def enlist_ways(self) -> None:
        """臨時投效怎麼挑：投人少的那一軍、一樣多照雜湊（帶流水號的鈕也算）；散人、沒有鈕、沒有決戰都是 None。"""
        from tianxia import bot
        from tianxia.engine import Game

        self.begin()
        ids = ["battle:enlist:guan", "battle:enlist:huang@2", "battle:join"]
        fights = (("官軍多", {"a": NS(faction="guan"), "b": NS(faction="guan"), "c": NS(faction="huang")}), ("一樣多", {"a": NS(faction="guan"), "c": NS(faction="huang")}))
        g, p = self.fresh("磨甲", faction="guan")
        for tag, who in fights:
            with mock.patch.object(Game, "battle_now", lambda self, w=who: NS(participants=w, battle_id="whetstone")):
                emit(f"enlist_pick {tag}", bot.enlist_pick(g, ids))
                emit(f"enlist_pick {tag} 沒有鈕", bot.enlist_pick(g, ids[2:]))
        with mock.patch.object(Game, "battle_now", lambda self: None):
            emit("enlist_pick 沒有決戰", bot.enlist_pick(g, ids))
        p.faction = None
        with mock.patch.object(Game, "battle_now", lambda self: NS(participants={}, battle_id="whetstone")):
            emit("enlist_pick 散人", bot.enlist_pick(g, ids))

    def rally_ways(self) -> None:
        """走向決戰：不必走、走不過去、守著埋伏先收伏、走得了、前往不成；不限地點的決戰照舊什麼都能走。"""
        from tianxia import atlas, bot_policy as bp
        from tianxia.engine import Game

        self.begin()
        g, p = self.fresh("磨甲")
        pressed, press = self.pressing()
        with press, mock.patch.object(atlas, "region_locations", return_value=["某地"]), mock.patch.object(Game, "travel", lambda self, hop, mode: [f"走 {hop} {mode}"]):
            with mock.patch.object(Game, "rally_region", lambda self: None):
                emit("_toward_battle 不必走", self.safe(lambda: bp._toward_battle(g)))
            with mock.patch.object(Game, "rally_region", lambda self: "某區"):
                with self.swapped(next_hop=lambda game, targets: None):
                    emit("_toward_battle 走不過去", self.safe(lambda: bp._toward_battle(g)))
                with self.swapped(next_hop=lambda game, targets: "下一站"):
                    p.ambush = object()
                    emit("_toward_battle 守著埋伏", [self.safe(lambda: bp._toward_battle(g)), list(pressed)])
                    p.ambush = None
                    for tag, ways in (("走得了", [NS(mode="walk", enabled=True)]), ("按不下去", [NS(mode="walk", enabled=False)]), ("沒有路", None)):
                        with mock.patch.object(Game, "travel_options", lambda self, hop, w=ways: w):
                            emit(f"_toward_battle {tag}", self.safe(lambda: bp._toward_battle(g)))
        options = [NS(id="move:某地"), NS(id="act:train")]
        emit("_staying 不限地點", [o.id for o in bp._staying_for_the_battle(g, "no_such_battle", options)])

    def shop_ways(self) -> None:
        """店面與雜項各缺一兩行的：換馬、升階、賣不掉、捐不掉、內傷不設伏、庫快滿不學藝、走一趟沒體力、榜上交不出手、功效表是空的、等定名時不等契機、庫裡有認不得的武學。"""
        from tianxia import bot, bot_policy as bp
        from tianxia.features.bounties import rules as bounties
        from tianxia import economy, library, mounts, treasures
        from tianxia.engine import Game

        self.begin()
        with self.world.action_lock():
            g, p = self.fresh("磨甲", creating=None)
            with mock.patch.object(mounts, "better_mount", return_value="快馬"), mock.patch.object(treasures, "wanted", return_value=None), \
                    mock.patch.object(Game, "wield_weapon", lambda self, item: [f"換上 {item}"]):
                emit("wear_better 換馬", self.safe(lambda: bot.wear_better(g)))
            p.stats["silver"] = 100000
            p.materials = {mid: 99 for mid, m in sorted(self.c.materials.items()) if m.tier == 1}
            with mock.patch.object(economy, "upgrade_problem", return_value=None):
                emit("trade_want 升階", self.safe(lambda: bot.trade_want(g)))
            p.picking_smith = True
            with self.swapped(trade_want=lambda game: ("upgrade", "柔", 1)), mock.patch.object(Game, "smith_upgrade", lambda self, attr, tier: []):
                emit("trade_at_smith 升不了", [self.safe(lambda: bot.trade_at_smith(g)), len(p.materials)])
            with self.swapped(trade_want=lambda game: ("sell", "甲", 1)), mock.patch.object(Game, "smith_sell", lambda self, mid, n: []):
                emit("trade_at_smith 賣不了", [self.safe(lambda: bot.trade_at_smith(g)), len(p.materials)])
            p.picking_smith = False
            donate = self.c.config.economy.donate
            self.c.config.economy.donate = False
            try:
                emit("donate_want 不收", bot.donate_want(g))
            finally:
                self.c.config.economy.donate = donate
            with self.swapped(donate_want=lambda game: ("甲", 1)), mock.patch.object(Game, "can_donate_here", lambda self: True), mock.patch.object(Game, "donate", lambda self, mid, n: []):
                emit("donate_spare 捐不掉", self.safe(lambda: bot.donate_spare(g)))
            pressed, press = self.pressing()
            plays = [NS(id="ambush:set:x", enabled=True), NS(id="works:y", enabled=True), NS(id="aid:z", enabled=True)]
            p.stamina = float(self.c.config.stamina_max)
            with press, mock.patch.object(Game, "options", lambda self, **k: plays), self.swapped(_crippled=lambda game: True, PLAY_CHANCE=1.0):
                emit("_stamina_play 內傷", [self.safe(lambda: bp._stamina_play(g, random.Random(0))), list(pressed)])
            with mock.patch.object(library, "cap_of", return_value=0):
                emit("_learn_here 庫快滿", self.safe(lambda: bp._learn_here(g)))
            p.stamina = 0.0
            emit("outing_segments 沒體力", self.safe(lambda: bot.outing_segments(g, random.Random(0))))
            p.stamina = float(self.c.config.stamina_max)
            pressed, press = self.pressing()
            board = [NS(id="act:bounties", enabled=True), NS(id="bounty:pick:甲", enabled=True)]
            with press, mock.patch.object(Game, "options", lambda self, **k: board), mock.patch.object(bounties, "board_here", return_value=True), \
                    mock.patch.object(bounties, "open_bounties", return_value=[]), mock.patch.object(bounties, "give_choice", return_value=("甲", "乙")):
                emit("take_bounties 交不出手", [self.safe(lambda: bot.take_bounties(g)), list(pressed)])
            emit("_worth 沒有功效表", bot._worth(NS(traits=NS(general=[])), NS(top_power=7)))
            p.naming = "whetstone_art"
            emit("awaits_chance 等定名", bot.awaits_chance(g))
            p.naming, p.arts = None, ["no_such_art"]
            emit("switch 認不得", self.safe(lambda: bot.switch_to_the_strongest(g)))


# 改一個字（selftest）：熔最弱的那一門（第 101 批搬進修練包的 bots.py，那一句照寫，兩處找）。
register_track("whetstone", WhetstoneScenario, (("tianxia/bot.py", "tianxia/features/cultivation/bots.py"), ("game.melt_art(min(spare)[1])", "game.melt_art(max(spare)[1])")), "week7")
