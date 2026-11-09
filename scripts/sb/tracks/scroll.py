"""same_behavior 一軌一檔：scroll（這一檔登記 scroll）。"""
from __future__ import annotations

import contextlib
import random
from urllib.parse import quote

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, emit, register_track

# ═══════════════════════════ scroll（第二輪第 88 批：skillview 切開；core_shared） ═══════════════════════════
# 為什麼另開一軌：切開之前量過每一軌、三種設定走到 skillview 的哪幾行（計畫第四節）。榜單點開的功法卡（shown_art）、舊配點的數字（stat_lines、stat_step）、
# 同效果第二份起（_high_word、stack_parts 後半）、正邪共鳴（_echo_part）、功法卡的來歷（師門、合成、煉製、本命）、神器譜照神器配方畫的那一支，一軌都走不到。
# 這幾段只讀，存檔裡沒有「寫到一半」，所以情境直接把存檔擺成那個局面。


class ScrollScenario(Scenario):
    """門下頁與榜單的唯讀卡片（第二輪第 88 批；--track scroll，自己一個資料庫）。班底的名字都是原創。下面寫走到的，都在 head 上實跑、讀過輸出。
    - stacks：素帛身上兩門擺滿同一個效果與同一個真意：格子上寫「先手不加」「先手算五成・崩山多一半」（測試內容沒有真意，只有「先手算五成」），
      功法卡寫「三份：第二份算五成、第三份不加・到頂」；散著的那一份再裝會到頂；同一門兩條秘方特效，第二條寫「不發動」；舊存檔記模板的那一份照真意的說明。
    - echoes：丹砂正派吃善名（名聲說明開著「正派，吃善名」、關著「共鳴」）、內外同屬性「內外搭配 +20%」；一門上的第一份、散著的第二份。
    - shelfwork：苔痕的功法庫每一種來歷：師門、合成（有首創、沒首創）、煉製（有首創、沒首創）、本命；身上那門自創練成絕學，招後面接「稀有路數」與後勁（測試內容沒有後勁）。
    - boards：/api/board_card 的武學、內功：榜上的、自己、沒這個人、不認得的榜；直接問 leaderboard.art_card：只看第一名、自己不在前幾名也看得到。
      新人那一門：week7、season21 回基礎拳腳的卡，測試內容身上是空的回 null。
    - divine：神器譜兩筆（原品在丹砂手上的照原品畫、主人不在的照譜上記的畫）、季對不上回 null。
    - numbers：蕉窗在舊配點的季（old_points，season21、week7 在記憶體裡擺）：狀態列 stat_uses 寫數字（「武學威力 +6%」），配一點「臂力 5 → 6：武學威力 +6%」。
      測試內容沒有減法季，照舊是用途那一句。
    - half：**前半停在這裡**：配點配到一半（還有兩點），局面都在存檔裡。
    - 後半：resume 重新登入；pages 四個人的修練頁、煉製頁、狀態列再讀一次；allot 配完（第三點回沒有點）；boards_again 再點一次榜單與神器譜；
      bots 兩個假人（一軍一個）BotRunner 跑 4 輪（week7、season21 真的在動，測試內容沒有上線），再讀他們榜上那一列的卡，跟真人同一條路；
      season 換季：卡回 null（主人還在上一季那一支直接問 art_card），神器譜跨季照讀。

    這一軌走不到的：序章那幾句（art_rows、insight_rows 的 glow，forge_line 的拒絕：三種設定新人身上都沒有開著的序章）；承露不收錢那一句（heal_note）；
    身上那一門查不到的防呆（_art_label、detail、slot_rows、_stack_cells、roster_cards、forge_preview、member_card 的 follower 找不到）；背包全空（新人身上有東西）。
    這幾行只用 team、prologue、insights 這些別條路也叫到的名字，切開時靠 undef_scan 看。"""

    PLAYERS = {"青簡": "guan", "素帛": "huang", "丹砂": "guan", "苔痕": "huang", "蕉窗": "guan"}
    NEWBIE = "初摹"
    BOT_SEATS = [("簡甲", "guan"), ("簡乙", "huang")]
    TOP, STACKER, ECHO, SHELF, ALLOT = "青簡", "素帛", "丹砂", "苔痕", "蕉窗"
    PHASES_FIRST = ["setup", "seat", "stacks", "echoes", "shelfwork", "boards", "divine", "numbers", "half"]
    PHASES_SECOND = ["resume", "pages", "allot", "boards_again", "bots", "season"]

    def begin(self) -> None:
        """榜單的快取在行程裡（server.BOARDS_CACHE）：每個請求前清掉，整段與半舊半新才一樣。"""
        super().begin()
        self.server.BOARDS_CACHE.clear()

    def factions_on(self) -> bool:
        return {"guan", "huang"} <= {f.id for f in self.c.scenario.factions}

    # ── 擺局面 ──

    def seat(self) -> None:
        for who, side in self.PLAYERS.items():
            self.place(who, self.c.scenario.start_location, side if self.factions_on() else None)

    def art(self, name: str, kind: str = "武學", attribute: str = "快", **over):
        """一門登記進這一季的武學（名字原創；origin 預設合成）。"""
        from tianxia.martial_arts import generate_from_name

        art = generate_from_name(name, kind, name, attribute=attribute).model_copy(update={"origin": "fused", **over})
        self.world.claim_skill_name(art)
        return art

    @staticmethod
    def own(p, n: int, attribute: str = "快", general=None, grand=None, **over) -> str:
        """一份自己悟的意境，效果照 general／grand 寫死（不擲）。"""
        from tianxia.martial_arts import Insight
        from tianxia.state import InsightFx

        ins = Insight(id=f"悟:{n}", name=f"悟{n}", attribute=attribute, **over)
        p.own_insights[ins.id] = ins
        p.insights.append(ins.id)
        p.insight_fx[ins.id] = InsightFx(general=general if general is not None else {attribute: 3}, grand=grand)
        return ins.id

    def high_id(self):
        high = self.c.traits.high
        return high[0].id if high else None

    def stacks(self) -> None:
        """同效果好幾份：身上兩門擺滿一樣的效果，還有散著的幾份；第三份起到頂。秘方特效兩條，第二條不發動。"""
        wugong = self.art("霜痕掌")
        neigong = self.art("雪竇功", kind="內功")
        grand = self.high_id()
        specials = [s.id for s in self.c.traits.special][:2]

        def arrange(p) -> None:
            slots = [self.own(p, i, general={"快": 3}, grand=grand if i < 3 else None) for i in range(1, 7)]
            p.member.wugong_id, p.member.neigong_id = wugong.id, neigong.id
            p.art_quality[wugong.id] = p.art_quality[neigong.id] = "上品"
            p.art_slots[wugong.id], p.art_slots[neigong.id] = slots[:3], slots[3:]
            self.own(p, 7, general={"快": 3}, grand=grand)  # 散著的：再裝一份到頂
            self.own(p, 8, attribute="剛", general={"剛": 1})  # 散著的：別的效果
            spare = self.art("蘆花掌", attribute="剛", quality="上品")
            p.arts.append(spare.id)
            p.art_quality[spare.id] = "中品"
            secret = [self.own(p, 10 + i, attribute="虛", general={}, secret_special=sid) for i, sid in enumerate(specials)]
            p.art_slots[spare.id] = ["huo" if "huo" in self.c.insights else None, *secret][:3]
            god = self.own(p, 20, general={"快": 1}, grand=grand, note="{stun_pct}")  # 舊存檔記的模板
            emit("模板那一份", god)

        self.edit(self.STACKER, arrange)
        self.page(self.STACKER)
        self.call(self.STACKER, "GET", "/api/menxia?person=follower:9")
        self.page(self.NEWBIE)

    def echoes(self) -> None:
        """正邪共鳴：正派功法吃善名、內外同屬性；名聲說明開著與關著兩種寫法。身上一份、散著一份，第二份只算半。"""
        wugong = self.art("守拙劍", attribute="剛", lean="正")
        neigong = self.art("抱樸訣", kind="內功", attribute="剛", lean="邪")

        def arrange(p) -> None:
            p.member.wugong_id, p.member.neigong_id = wugong.id, neigong.id
            p.art_quality[wugong.id] = p.art_quality[neigong.id] = "中品"
            p.stats["good"], p.stats["evil"] = 30, 10
            grand = self.high_id()
            p.art_slots[wugong.id] = [self.own(p, 1, attribute="剛", general={"剛": 3}, grand=grand), None, None]
            self.own(p, 2, attribute="剛", general={"剛": 3}, grand=grand)
            self.own(p, 3, attribute="剛", general={"剛": 1})

        self.edit(self.ECHO, arrange)
        self.page(self.ECHO)
        cfg = self.c.config.renown
        before = cfg.explain
        cfg.explain = not before
        try:
            self.page(self.ECHO)
        finally:
            cfg.explain = before

    def shelfwork(self) -> None:
        """功法庫裡每一種來歷的卡：師門、合成（有首創、沒首創）、煉製、自創（稀有路數、練成絕學接後勁）、本命。"""
        from tianxia import moves

        rows = {
            "師門": self.art("墨痕拳", preset=True),
            "合成": self.art("松濤掌", creator="松下客", creator_shown="松下客"),
            "合成無名": self.art("竹影掌"),
            "煉製": self.art("鐵硯手", origin="crafted", creator="硯旁人", creator_shown="硯旁人"),
            "煉製無名": self.art("石鼓手", origin="crafted"),
            "本命": self.art("孤山槍", origin="native"),
        }
        made = self.art("雲根手", origin="created", creator=self.SHELF, creator_shown=self.SHELF, move_rare=True, move_fire="透",
                        slot_colors=[["快"], ["快"], ["快"]], move_name="雲根一式", move_stance="攻勢")
        key = next((t.key for t in self.c.traits.general if t.ultimate is not None), "快")

        def arrange(p) -> None:
            for art in rows.values():
                p.arts.append(art.id)
                p.art_quality[art.id] = "中品"
            p.member.wugong_id = made.id
            p.art_quality[made.id] = moves.MASTERED
            p.art_slots[made.id] = [self.own(p, 1, general={key: 3}), None, None]
            p.member.wugong_level = 10
            p.art_levels[made.id] = 10
            p.stats["xinde"] = 200

        self.edit(self.SHELF, arrange)
        self.page(self.SHELF)

    def page(self, who: str, person: str | None = None):
        """修練頁一次、煉製頁放兩份（合得了與合不了都照存檔）、狀態列一次。"""
        self.call(who, "GET", "/api/menxia" + (f"?person={quote(person)}" if person else ""))
        have = self.chars.load(who).player.insights
        self.call(who, "POST", "/api/forge_line", {"insights": have[:1]})
        self.call(who, "POST", "/api/forge_line", {"insights": have[:2]})
        self.call(who, "POST", "/api/forge_line", {"insights": have[-1:] * 2})
        self.main(who)

    # ── 榜單 ──

    def card(self, who: str, board: str, name: str) -> None:
        self.call(who, "GET", f"/api/board_card?board={quote(board)}&name={quote(name)}")

    def boards(self) -> None:
        """榜單點開的功法卡：榜上看得到的、自己、不在榜上的、不認得的榜；只看第一名、自己不在前幾名、新人那一門，直接照整張榜問。"""
        from tianxia import leaderboard

        self.call(self.TOP, "GET", "/api/boards")
        for board in ("武學", "內功"):
            for name in (self.STACKER, self.ECHO, self.SHELF, self.TOP, "沒這個人"):
                self.card(self.TOP, board, name)
        self.card(self.TOP, "善人", self.STACKER)
        board = leaderboard.compute_boards(self.c, self.world, top=None, characters=self.chars)
        emit("只看第一名", leaderboard.art_card(self.c, self.world, board, "武學", self.ECHO, top=1, characters=self.chars) is None)
        emit("自己在榜上", (leaderboard.art_card(self.c, self.world, board, "武學", self.ECHO, me=self.ECHO, top=1, characters=self.chars) or {}).get("owner"))
        emit("新人那一門", leaderboard.art_card(self.c, self.world, {"武學": [(self.NEWBIE, 1)]}, "武學", self.NEWBIE, characters=self.chars))

    def divine(self) -> None:
        """神器譜：神器配方登記一筆，原品還在主人手上的照原品畫、不在的照譜上記的畫；季對不上回 null。"""
        from tianxia.state import Equipment, GearFind

        season = self.world.get_season_number()
        rows = {"秘:鎮海": ("鎮海甲", self.ECHO), "秘:流沙": ("流沙劍", "早已不在")}
        for secret, (name, owner) in rows.items():
            find = GearFind(secret=secret, slot="weapon", kind="劍", attribute="剛", tier=3, title=name, creator=owner, creator_shown=owner,
                            divine=True, owner=owner, master_shown=owner, divine_name=name, copies=1)
            with self.world.db.transaction() as conn:
                conn.execute("INSERT INTO gear_recipes (season, key, name, creator, data) VALUES (?, ?, ?, ?, ?)",
                             (season, f"鑄|{secret}", name, owner, find.model_dump_json()))
        self.edit(self.ECHO, lambda p: p.rack.append(Equipment(slot="weapon", id="兵:九", name="鎮海甲", kind="劍", attribute="剛", tier=3, quality="上品",
                                                               original=True, secret="秘:鎮海")))
        for secret in rows:
            ref = quote(f"鑄|{secret}")
            self.call(self.TOP, "GET", f"/api/board_card?board={quote('神器')}&season={season}&ref={ref}")
            self.call(self.TOP, "GET", f"/api/board_card?board={quote('神器')}&season={season + 1}&ref={ref}")
        self.call(self.TOP, "GET", "/api/boards")

    # ── 屬性五段與舊配點 ──

    @contextlib.contextmanager
    def old_points(self):
        """舊配點的季：減法季屬性五段開著、五項屬性關著（season21、week7 在記憶體裡這樣擺，兩份程式同一套）。test 沒有減法季，照舊走用途那一句。"""
        cfg = self.c.config
        jf, v2 = cfg.jianfa, cfg.attributes.v2
        before = jf.stat_milestones, v2.enabled
        jf.stat_milestones, v2.enabled = True, False
        try:
            yield
        finally:
            jf.stat_milestones, v2.enabled = before

    def numbers(self) -> None:
        """狀態列寫「現在給你什麼」的數字（stat_uses → stat_lines）。"""
        self.edit(self.ALLOT, lambda p: setattr(p, "stat_points", 3))
        with self.old_points():
            self.main(self.ALLOT)
            self.do(self.ALLOT, "allocate", {"stat": "str"})
            self.main(self.ALLOT)

    def half(self) -> None:
        """前半停在這裡：配點配到一半（還有兩點）、爐前兩份合得了的還沒開爐、神器譜登記好了。"""
        p = self.chars.load(self.ALLOT).player
        emit("前半停下來", {"還可以配": p.stat_points, "配過": {k: p.stats.get(k) for k in ("str", "con", "agi")}})

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()
        self.main(self.TOP)

    def pages(self) -> None:
        for who in (self.STACKER, self.ECHO, self.SHELF, self.TOP):
            self.page(who)

    def allot(self) -> None:
        with self.old_points():
            for stat in ("con", "agi", "wis"):
                self.do(self.ALLOT, "allocate", {"stat": stat})
            self.main(self.ALLOT)

    def boards_again(self) -> None:
        self.call(self.TOP, "GET", "/api/boards")
        self.card(self.TOP, "武學", self.STACKER)
        self.card(self.TOP, "內功", self.ECHO)
        self.call(self.TOP, "GET", f"/api/board_card?board={quote('神器')}&season={self.world.get_season_number()}&ref={quote('鑄|秘:鎮海')}")

    def bots(self) -> None:
        """假人照常跑：兩個（一軍一個）擺好之後 BotRunner 跑 4 輪；再讀他們的修練頁資料與榜上那一列的卡（跟真人同一條路）。"""
        from collections import Counter

        from tianxia import leaderboard, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        on = self.factions_on()
        for i, (name, side) in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=197 + i, faction=side if on else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, self.c.scenario.start_location, None
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.stats["xinde"] = 300
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(59), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {197 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(4):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        board = leaderboard.compute_boards(self.c, self.world, top=None, characters=self.chars)
        for name, _ in self.BOT_SEATS:
            emit(f"{name} 的卡", leaderboard.art_card(self.c, self.world, board, "武學", name, characters=self.chars))

    def season(self) -> None:
        """換季：主人的季對不上，卡回 null；神器譜跨季照讀。"""
        from tianxia import leaderboard

        season = self.world.get_season_number()
        self.do(ADMIN, "end_season")
        self.main(self.TOP)
        self.do(ADMIN, "next_season")
        self.main(self.TOP)
        self.card(self.TOP, "武學", self.STACKER)
        emit("主人還在上一季", leaderboard.art_card(self.c, self.world, {"武學": [(self.STACKER, 1)]}, "武學", self.STACKER, characters=self.chars))
        self.call(self.TOP, "GET", f"/api/board_card?board={quote('神器')}&season={season}&ref={quote('鑄|秘:流沙')}")


# 改一個字（selftest）：同一個真意第二份那一句（搬之前在 tianxia/skillview.py、搬之後在共用層 tianxia/art_cards.py）。抓到的地方：素帛身上的第二份
register_track("scroll", ScrollScenario, (("tianxia/art_cards.py",), ('HIGH_MORE = "多一半"', 'HIGH_MORE = "多一半！"')), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "figure_acts", "gear", "guide", "heroines", "jieyi", "legacy", "looks", "mall", "military", "outlets",
                       "peers", "seal", "seclusion", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story", "tavern",
                       "travel", "zhuan", "zongmen"))
