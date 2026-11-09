"""same_behavior 一軌一檔：growth（這一檔登記 growth、legacy）。"""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, TRACK_REQUIRES, emit, register_track

# ═══════════════════════════ growth、legacy（合回 develop 第 0 段） ═══════════════════════════
# 主幹合回 develop（手冊第十五節「develop 合回的 PM 認定」；盤點 docs/superpowers/handoff/2026-11-06-develop合回盤點/）第 1 段拿這兩軌驗
# FEATURES 的位置與換季帶走的東西。
# 這兩軌只有 develop（與合回之後的主幹）起得來：五項屬性、傳承都是 develop 的功能。根上沒有那個檔時 compare、selftest 照 TRACK_REQUIRES 略過，
# 直接 run 這兩軌會停下來寫理由，不會空跑。角色與意境的名字都是原創的。


class _SeqRng:
    """照順序吐出給的亂數，吐完一律給 0.99（頓悟那一下：第一下沒中、機緣的門路再擲一次）。"""

    def __init__(self, *values):
        self.values = list(values)

    def random(self):
        return self.values.pop(0) if self.values else 0.99


class _PrepTrack(Scenario):
    """growth、legacy 共用：自己走開季準備卡（auto_prep 關掉），管理者開季由各軌自己決定時機。"""

    auto_prep = False
    TRACK_FILE = ""

    def __init__(self, root: Path, profile: str, db: Path):
        if not (root / self.TRACK_FILE).exists():
            raise SystemExit(f"{type(self).__name__}：這個根沒有 {self.TRACK_FILE}（合回 develop 第 1 段之前的主幹本來就沒有這一軌）")
        super().__init__(root, profile, db)

    def admin_up(self) -> None:
        from tianxia.accounts import AccountStore
        from tianxia.engine import Game

        store = AccountStore(self.world.db)
        self.passwords[ADMIN] = "pw-admin-123456"
        with self.world.db.transaction():
            store.register(self.login_of(ADMIN), self.passwords[ADMIN])
            game = Game.new(self.c, ADMIN, world=self.world)
            self.chars.save(game.state)
            store.bind_character(self.login_of(ADMIN), ADMIN)
        self.clients[ADMIN] = self.TestClient(self.server.app)
        self.call(ADMIN, "POST", "/api/login", {"login": self.login_of(ADMIN), "password": self.passwords[ADMIN]})

    def enroll(self, who: str) -> None:
        """註冊、建角色（真人從網頁建的那一條：序章外沒有預設配比，第一次看到畫面就是開季準備卡）。"""
        self.clients[who] = self.TestClient(self.server.app)
        self.passwords[who] = "pw-" + self.login_of(who)
        self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who], "again": self.passwords[who]})
        self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})

    def past_card(self, who: str) -> None:
        """這個人的卡照預設按掉（這一軌不看他的那張卡時用）。"""
        view = self.main(who)
        if self.prep_of(view) is not None:
            self.clear_prep(who, view)

    def v2(self):
        return self.c.config.attributes.v2

    def default(self) -> str:
        return self.v2().default_preset

    def seats(self, names: list[str], fn=None) -> None:
        """假人坐上去（同 compass 那一軌的寫法），fn(state) 擺他們的局面；挑配比那一步留著給他們自己按。"""
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        for i, name in enumerate(names):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=91 + i, faction=None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            p.growth_preset, p.tutorial_step, p.joined_at = None, len(self.c.tutorial.steps), -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            if fn is not None:
                fn(g.state)
            self.chars.save(g.state)

    def tick(self, names: list[str], rounds: int, tag: str) -> None:
        """BotRunner 跑幾輪（只有這幾個假人上線），寫每個人的配比、配點、傳承與整份存檔的雜湊。"""
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner

        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(47), clock=lambda: CLOCK[0])
        old_tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {91 + i for i in range(len(names))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds
        totals = Counter()
        try:
            for _ in range(rounds):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = old_tick, online
        emit(f"假人 {tag} 一輪一輪", dict(sorted(totals.items())))
        for name in names:
            s = self.chars.load(name)
            p = s.player
            emit(f"假人 {name} {tag}", {
                "preset": p.growth_preset, "alloc": p.attr_alloc, "points": p.stat_points,
                "book": None if p.legacy is None else p.legacy.model_dump(mode="json"),
                "journal": [[e.title, list(e.lines)[:3]] for e in s.journal[:4]],
                "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})


class GrowthScenario(_PrepTrack):
    """配比與屬性 v2（合回 develop 第 0 段；--track growth，自己一個資料庫）。
    籌備中也寫著 main.prep、但挑不了；開季後第一個畫面是開季準備卡：別的動作按不動、growth:custom 只回一句、沒這一套回理由、挑了就鎖
    （按鈕與 /api/do/growth 兩條路都回「定了」）；自己配的七種錯法與對的；五套預設各一個人；升級拿送的點（bonus_every）、配點（沒點、沒這項、舊的鍵）；
    事件給屬性是歷練（新尺度、每季上限、滿了化成心得）、博聞全給心得。
    **前半停在寫到一半的事**：程晚晴的卡還開著（按過「自己配」、沒定）；石懷遠手上還有送的點、歷練只差一點到頂、事件卡擺在面前沒回答。
    後半新程式接著：程晚晴定下自己配的；石懷遠回答（這一下過頂）、再答一次（滿了只給心得）、把點配完；五套配比各打一趟（同一個對手、配比不同）；
    假人照名號挑配比、送的點配在最重的那一項；收季（已定的回「定了」、休季才建的人照樣挑得了）；開下一季：配比、送的點、歷練都歸零、卡再出現，
    不按的人照預設長；假人再挑一次。測試內容沒有五項屬性：同一串 API 照打，寫「這一季沒有」。"""

    TRACK_FILE = "tianxia/attrset.py"
    PICKERS = ("陶硯之", "賀聽松", "溫如晦", "鄭觀瀾", "蘇慕遠")  # 五套預設各一個（照 Config.attributes.v2.presets 的順序）
    CRAFTER, WAITER, LEAPER, EARLY, LATECOMER = "裴青禾", "程晚晴", "石懷遠", "趙初開", "孟遲歸"
    NOT_AT_ALL = "魏不擇"  # 第二季也不挑：照預設長
    BOT_SEATS = ["衡一", "衡二"]
    PHASES_FIRST = ["setup", "card", "locked", "custom", "presets", "points", "lilian", "half"]
    PHASES_SECOND = ["resume", "custom_on", "lilian_on", "points_on", "fights", "bots", "rest", "turn", "card_again", "bots_again"]

    # ── 小工具 ──

    def sheet(self, who: str, tag: str) -> None:
        """這個人存檔裡的配比與屬性（不經 API，讀資料庫）：五項的值、魅力每個鉤子、舊公式讀到的值。"""
        from tianxia import attrset, team

        s = self.chars.load(who)
        s.world = self.world.get_season()  # 存檔裡沒有季上的章（attrs_v2）：同 FigActScenario.game
        p = s.player
        on = attrset.on(self.c, s.world)
        emit(f"{who} {tag}", {
            "preset": p.growth_preset, "custom": p.growth_custom, "event": p.attr_event, "alloc": p.attr_alloc, "points": p.stat_points,
            "level": p.member.level, "xinde": p.stats.get("xinde", 0), "values": attrset.values(s, self.c) if on else None,
            "charm": {h: round(attrset.charm(s, self.c, h), 6) for h in sorted(self.v2().charm)} if on else None,
            "old": {k: round(attrset.legacy(s, self.c, k), 6) for k in team.COMBAT_STATS} if on else None,
            "journal": [[e.title, list(e.lines)[:2], list(e.changes)[:2]] for e in s.journal[:3]]})

    def good_split(self) -> dict[str, int]:
        """對的自己配（每項至少 custom_min、最多 custom_max、合計 per_level；照鍵的順序從頭填）。"""
        cfg = self.v2()
        out = dict.fromkeys(cfg.keys, cfg.custom_min)
        left = cfg.per_level - cfg.custom_min * len(cfg.keys)
        for k in cfg.keys:
            add = min(left, cfg.custom_max - cfg.custom_min)
            out[k] += add
            left -= add
        return out

    def stage_event(self, who: str) -> bool:
        """事件卡擺在他面前（train_insight 第一個選項：沒有檢定、臂力 +1）；這份內容沒有這一則回 False。"""
        if "train_insight" not in self.c.events:
            emit(f"{who} 這份內容沒有 train_insight", None)
            return False
        with self.world.action_lock():
            state = self.chars.load(who)
            state.pending_event = "train_insight"
            self.chars.save(state)
        emit(f"{who} 擺上事件卡", "train_insight")
        return True

    # ── 前半 ──

    def setup(self) -> None:
        """籌備中（管理者還沒開季）：main.prep 寫著、選單是籌備中，挑不了；開季之後才是卡。"""
        self.admin_up()
        self.enroll(self.EARLY)
        self.choose(self.EARLY, f"growth:{self.default()}")
        self.do(self.EARLY, "growth", {"preset": self.default()})
        self.do(ADMIN, "open_season")
        self.past_card(ADMIN)
        self.main(self.EARLY)
        self.do(self.EARLY, "skip_tutorial")
        self.sheet(self.EARLY, "開季之後、卡還開著")
        for who in (*self.PICKERS, self.CRAFTER, self.WAITER, self.LEAPER, self.NOT_AT_ALL):
            self.enroll(who)

    def card(self) -> None:
        """卡接管選單：別的動作按不動、配點回一句、自己配只回一句、沒這一套回理由；挑預設那一套之後才接開局三選一。"""
        who = self.PICKERS[0]
        self.do(who, "skip_tutorial")
        for oid in ("act:train", "act:socialize", "growth:custom", "growth:沒這一套"):
            self.choose(who, oid)
        self.do(who, "allocate", {"stat": "str"})
        self.do(who, "growth", {"preset": "沒這一套"})
        self.sheet(who, "卡還開著")
        self.choose(who, f"growth:{self.v2().presets[0].key}")
        self.settle_choices(who)
        self.sheet(who, "定了之後")

    def locked(self) -> None:
        """挑了就鎖：按鈕與 /api/do/growth 都回「定了」。"""
        who = self.PICKERS[0]
        other = self.v2().presets[1].key
        self.choose(who, f"growth:{other}")
        self.do(who, "growth", {"preset": other})
        self.do(who, "growth", {"preset": "custom", "split": self.good_split()})
        self.choose(who, "growth:custom")
        self.sheet(who, "鎖了之後")

    def custom(self) -> None:
        """自己配：七種錯法都只回一句、卡還開著；對的那一份定下來。"""
        who = self.CRAFTER
        self.do(who, "skip_tutorial")
        cfg, good = self.v2(), self.good_split()
        first, last = cfg.keys[0], cfg.keys[-1]
        for split in (None, "不是表", {first: cfg.per_level}, {**good, first: str(good[first])}, {**good, first: float(good[first])},
                      {**good, first: cfg.custom_max + 1, last: good[last] - 1}, {**good, first: cfg.custom_min - 1, last: good[last] + 1},
                      {**good, first: good[first] + 1}):
            self.do(who, "growth", {"preset": "custom", "split": split})
        self.sheet(who, "錯法之後")
        self.do(who, "growth", {"preset": "custom", "split": good})
        self.settle_choices(who)
        self.sheet(who, "自己配定了")

    def presets(self) -> None:
        """其餘四套各一個人（同一條路：跳過教學、按卡上的鈕、開局三選一）。"""
        for who, row in zip(self.PICKERS[1:], self.v2().presets[1:]):
            self.do(who, "skip_tutorial")
            self.choose(who, f"growth:{row.key}")
            self.settle_choices(who)
            self.sheet(who, f"挑了 {row.key}")

    def points(self) -> None:
        """升級拿送的點（team.level_points 走 bonus_between）：先配兩點，舊的鍵、沒這項都回一句；剩下的留到後半。"""
        from tianxia import team

        who = self.LEAPER
        self.do(who, "skip_tutorial")
        self.choose(who, f"growth:{self.v2().presets[-1].key}")
        self.settle_choices(who)
        self.do(who, "allocate", {"stat": self.v2().keys[0]})  # 還沒有點
        with self.world.action_lock():
            state = self.chars.load(who)
            state.world = self.world.get_season()
            msgs, _ = team.grant_team_exp(state, self.c, self.world, 700)
            self.chars.save(state)
        emit(f"{who} 升級", msgs)
        self.main(who)
        for stat in (self.v2().keys[0], self.v2().keys[1], "沒這項", "agi", "lore"):
            self.do(who, "allocate", {"stat": stat})
        self.sheet(who, "配了兩點")

    def lilian(self) -> None:
        """事件給屬性：第一次照給（歷練幾／上限）；接著擺到只差一點到頂、事件卡擺在面前不回答（前半停在這裡）。"""
        who = self.LEAPER
        if self.stage_event(who):
            self.main(who)
            self.choose(who, "choice:0")
            self.sheet(who, "第一次歷練")
        self.edit(who, lambda p: setattr(p, "attr_event", {"spd": self.v2().event_cap - 1}))
        self.stage_event(who)
        self.main(who)

    def half(self) -> None:
        """程晚晴的卡還開著：按過「自己配」，沒定。"""
        who = self.WAITER
        self.do(who, "skip_tutorial")
        self.choose(who, "growth:custom")
        self.sheet(who, "前半停在這裡")
        self.sheet(self.LEAPER, "前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def custom_on(self) -> None:
        """舊程式開著的卡，新程式接著定。"""
        self.do(self.WAITER, "growth", {"preset": "custom", "split": self.good_split()})
        self.settle_choices(self.WAITER)
        self.sheet(self.WAITER, "接著定了")

    def lilian_on(self) -> None:
        """回答前半擺著的事件卡（這一下過頂：多的化成心得、多一句到火候）；再來一次（滿了只給心得）；博聞對不到新的一項，全給心得。"""
        from tianxia import attrset

        who = self.LEAPER
        self.choose(who, "choice:0")
        self.sheet(who, "過頂那一下")
        if self.stage_event(who):
            self.choose(who, "choice:0")
            self.sheet(who, "滿了之後")
        with self.world.action_lock():
            state = self.chars.load(who)
            state.world = self.world.get_season()
            msgs = attrset.grant_event(state, self.c, "lore", 1) + attrset.grant_event(state, self.c, "str", -1)
            self.chars.save(state)
        emit(f"{who} 博聞、扣的", msgs)
        self.sheet(who, "博聞之後")

    def points_on(self) -> None:
        """把前半留著的點配完（沒有上限），再配一下回「沒有點」。"""
        who = self.LEAPER
        left = self.chars.load(who).player.stat_points
        keys = self.v2().keys
        for i in range(left):
            self.do(who, "allocate", {"stat": keys[i % len(keys)]})
        self.do(who, "allocate", {"stat": keys[0]})
        self.sheet(who, "配完之後")
        self.main(who)

    def fights(self) -> None:
        """五套配比都拉到 20 級、站同一處各打一趟（出陣、探索各一下）：配比不同、仗打出來不同（比對抓得到讀值的改動）。"""
        side = "guan" if "guan" in {f.id for f in self.c.scenario.factions} else None
        self.set_duel(False)
        for who in self.PICKERS:
            self.edit(who, lambda p: setattr(p.member, "level", 20))
            self.place(who, "nanyang_wilds", side)
            for oid in ("act:train", "act:explore"):
                self.choose(who, oid)
                self.settle_choices(who)
            self.sheet(who, "打了一趟")
        self.set_duel(True)

    def bots(self) -> None:
        """假人照名號挑配比（bot.growth_key）、送的點配在最重的那一項。"""
        self.seats(self.BOT_SEATS, lambda s: setattr(s.player, "stat_points", 10))
        self.tick(self.BOT_SEATS, 4, "這一季")

    def rest(self) -> None:
        """收季：定了的照舊回「定了」；休季才建的人卡也寫著，鈕與 /api/do/growth 各按一下（pick_growth 只擋籌備中）。"""
        self.do(ADMIN, "end_season")
        self.main(self.LEAPER)
        self.do(self.LEAPER, "growth", {"preset": self.v2().presets[0].key})
        self.enroll(self.LATECOMER)
        self.main(self.LATECOMER)
        self.choose(self.LATECOMER, f"growth:{self.default()}")
        self.sheet(self.LATECOMER, "休季才建的、按過鈕")
        self.do(self.LATECOMER, "growth", {"preset": self.default()})
        self.sheet(self.LATECOMER, "休季才建的、走過 API")

    def turn(self) -> None:
        self.do(ADMIN, "next_season")
        self.past_card(ADMIN)

    def card_again(self) -> None:
        """換季：配比、送的點、歷練都歸零，卡再出現。有人挑、有人自己配、魏不擇不挑（照預設長）、別的動作照樣按不動。"""
        everyone = (*self.PICKERS, self.CRAFTER, self.LEAPER, self.WAITER, self.EARLY, self.LATECOMER, self.NOT_AT_ALL)
        for who in everyone:
            self.main(who)
            self.sheet(who, "換季之後")
        self.choose(self.PICKERS[0], "act:train")
        self.choose(self.PICKERS[0], f"growth:{self.v2().presets[3].key}")
        self.do(self.CRAFTER, "growth", {"preset": "custom", "split": self.good_split()})
        self.choose(self.LEAPER, f"growth:{self.default()}")
        self.do(self.WAITER, "growth", {"preset": self.v2().presets[2].key})
        for who in (self.PICKERS[0], self.CRAFTER, self.LEAPER, self.WAITER):
            self.settle_choices(who)
            self.sheet(who, "第二季定了")
        self.sheet(self.NOT_AT_ALL, "第二季不挑")

    def bots_again(self) -> None:
        self.tick(self.BOT_SEATS, 3, "第二季")


class LegacyScenario(_PrepTrack):
    """傳承（合回 develop 第 0 段；--track legacy，自己一個資料庫）。第一季把正氣、邪氣、機緣的評比與神品意境擺好，換季：
    on_season_start 結算（留七成＋增量）、立門路的旗標、敬俠喜狠的起始好感、寫一則紀錄；開季準備卡兩步（配比 → 識海）；
    封第一份、封第二份、不帶、錯的編號；九道門路讀到的地方（俠寇選項、正邪武學、潁川書院、奇遇、頓悟再擲、長篇奇事）；
    解封的三道封印（一天、15 級、心得）一道一道過；撞名換候選。
    **前半停在寫到一半的事**：段聽雨的識海撞了名、三個候選還沒挑；薛問樵的識海候選還開著；顧長汀連配比都還沒挑；奚照影封著一份、身上又有一份，解不開。
    後半新程式接著：段聽雨挑候選（錯的編號先按一次）；薛問樵封、顧長汀配比接不帶；奚照影放掉身上那一份、解封；假人（封第一份、條件到了解封）；
    再換季：舊的留七成、沒解封的那一份不再帶、解封過的算身上的又列進候選、門路掉了的旗標收回。
    測試內容傳承關著、沒有神品：同一串 API 照打，寫「沒有」。"""

    TRACK_FILE = "tianxia/features/legacy/__init__.py"
    RIGHT, DARK, LUCKY, KEEPER, CLASH, TAKER, WAITER, LATE, HOLDER = "韓松濤", "厲冬青", "計長庚", "封雲歸", "段聽雨", "冷秋白", "薛問樵", "顧長汀", "奚照影"
    EVERYONE = (RIGHT, DARK, LUCKY, KEEPER, CLASH, TAKER, WAITER, LATE, HOLDER)
    GODS = {RIGHT: ("萬壑松聲",), KEEPER: ("松風入定", "斷雲歸鴻"), CLASH: ("空庭落雪",), WAITER: ("暮江遠火",), LATE: ("青燈照壁",), HOLDER: ("一葦橫江",)}
    SECOND_GOD = "寒砧夜永"  # 奚照影封了一份之後身上又有的那一份
    BOT_SEATS = ["識一", "識二"]
    BOT_GODS = {"識一": "秋池照影", "識二": "長河落照"}
    PHASES_FIRST = ["setup", "seed", "before", "turn", "sheets", "card", "doors", "gates", "clash", "half"]
    PHASES_SECOND = ["resume", "clash_on", "offers_on", "holder_on", "bots", "bots_open", "second_season", "turn_two", "sheets_two", "card_two", "bots_two"]

    # ── 小工具 ──

    def give_god(self, state, name: str) -> None:
        """身上多一份神品意境（同 legacy_kit.give_god）；這份內容沒有神品就不給。"""
        from tianxia import insight_fx, insights
        from tianxia.martial_arts import Insight
        from tianxia.state import InsightFx

        gods = self.c.traits.god if self.c.traits is not None else []
        if not gods:
            return
        god, p = gods[0], state.player
        p.own_serial += 1
        iid = f"{insights.OWN_PREFIX}{p.own_serial}"
        p.own_insights[iid] = Insight(id=iid, name=name, attribute=god.attribute, lean=god.lean, note=god.desc, creator=p.name)
        p.insights.append(iid)
        p.insight_fx[iid] = InsightFx(quality=insight_fx.QUALITIES[-1], general={god.general: insight_fx.MAX_LAYERS}, grand=god.id)

    def edit_state(self, who: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(who)
            fn(state)
            self.chars.save(state)

    def book(self, who: str, tag: str) -> None:
        """傳承在存檔裡的樣子：LegacyBook 整份、門路的旗標、身上的神品、在意俠寇的人物的好感。"""
        s = self.chars.load(who)
        p = s.player
        regard = {cid: p.affinities.get(cid, 0) for cid, ch in sorted(self.c.characters.items()) if ch.regard is not None}
        emit(f"{who} {tag}", {
            "book": None if p.legacy is None else p.legacy.model_dump(mode="json"), "flags": sorted(f for f in p.flags if f.startswith("legacy_")),
            "gods": [[i.name, i.attribute] for i in p.own_insights.values()], "xinde": p.stats.get("xinde", 0), "level": p.member.level,
            "preset": p.growth_preset, "regard": regard, "god_names": dict(sorted(self.world.get_season().god_names.items())),
            "journal": [list(e.lines) for e in s.journal if e.title == "傳承"][:2]})

    def unsealable(self, who: str) -> None:
        def fn(p) -> None:
            p.member.level = max(p.member.level, self.c.config.legacy.shihai_level)
            p.stats["xinde"] = max(p.stats.get("xinde", 0), self.c.config.legacy.shihai_xinde + 30)
        self.edit(who, fn)

    # ── 前半 ──

    def setup(self) -> None:
        self.admin_up()
        self.do(ADMIN, "open_season")
        self.past_card(ADMIN)
        for who in self.EVERYONE:
            self.enroll(who)
            self.do(who, "skip_tutorial")
            self.past_card(who)
            self.settle_choices(who)
            self.place(who, self.c.scenario.start_location)

    def seed(self) -> None:
        """第一季的傳（擺進存檔）：韓松濤善名高（正氣三道）、厲冬青惡名（邪氣兩道）、計長庚任務貢獻名望情誼（機緣三道）；神品意境各幾份。"""
        from tianxia.state import ErrandState

        known = next(iter(sorted(self.c.figures)), None)

        def lucky(s) -> None:
            p = s.player
            p.bounties_done, p.contrib, p.showdowns, p.top_merits = 2, 400, 2, 1
            p.errands.append(ErrandState(id="lg1", figure=known or "無", errand="無", kind="letter", target=self.c.scenario.start_location, week=1, at=0,
                                         expires=1, letter=1, status="done"))
            p.stats["fame"] = 300
            if known is not None:
                p.affinities[known] = 50

        self.edit_state(self.RIGHT, lambda s: s.player.stats.__setitem__("good", 484))
        self.edit_state(self.DARK, lambda s: s.player.stats.__setitem__("evil", 144))
        self.edit_state(self.LUCKY, lucky)
        for who, names in self.GODS.items():
            self.edit_state(who, lambda s, names=names: [self.give_god(s, n) for n in names])
        self.seats(self.BOT_SEATS, lambda s: self.give_god(s, self.BOT_GODS[s.player.name]))

    def before(self) -> None:
        """還沒結算過：main.legacy 不畫；四個動詞都不在選單上。"""
        who = self.KEEPER
        self.main(who)
        for oid in ("legacy:seal:0", "legacy:skip", "legacy:open", "legacy:name:0"):
            self.choose(who, oid)
        self.book(who, "還沒結算過")

    def turn(self) -> None:
        self.do(ADMIN, "end_season")
        self.main(self.KEEPER)  # 休季
        self.do(ADMIN, "next_season")
        self.past_card(ADMIN)

    def sheets(self) -> None:
        """換季後每個人第一個畫面：結算過了、門路立了、紀錄寫了；卡的第一步是配比（有候選的 steps 有兩步）。"""
        for who in self.EVERYONE:
            self.main(who)
            self.book(who, "換季結算之後")

    def card(self) -> None:
        """卡兩步：配比 → 識海。封第二份（錯的編號先按一次）、封第一份、不帶（再按一次回一句）；沒候選的只有配比一步；薛問樵停在識海那一步、顧長汀連配比都沒挑。"""
        key = self.default()
        for who in (self.RIGHT, self.DARK, self.LUCKY, self.KEEPER, self.CLASH, self.TAKER, self.WAITER, self.HOLDER):
            self.choose(who, f"growth:{key}")
        self.choose(self.KEEPER, "act:train")  # 識海那一步也接管選單
        self.choose(self.KEEPER, "legacy:seal:9")
        self.choose(self.KEEPER, "legacy:seal:1")
        self.choose(self.CLASH, "legacy:seal:0")
        self.choose(self.HOLDER, "legacy:seal:0")
        self.choose(self.RIGHT, "legacy:skip")
        self.choose(self.RIGHT, "legacy:skip")
        self.choose(self.LUCKY, "legacy:skip")  # 沒候選
        for who in self.EVERYONE:
            self.settle_choices(who)
            self.book(who, "卡之後")

    def doors_of(self, who: str, tag: str) -> None:
        """門路讀到的地方（模組函式直接叫，不存檔）：俠寇選項、正邪武學、奇遇倍率、潁川書院的條件、頓悟再擲、長篇奇事。"""
        from tianxia.features.sense import epiphany
        from tianxia import events, renown
        from tianxia.rules import check_condition

        try:
            from tianxia.story_base import _luck_again
        except (ImportError, AttributeError):  # develop：還在舊的 storyline
            from tianxia.features.story.storyline import _luck_again
        s, c = self.chars.load(who), self.c
        out = {"doors": {d: renown.legacy_door(s, c, d) for d in sorted(c.config.legacy.doors)},
               "open": {f"{k}_{w}_{t}": renown.open_to(s, c, k, w, t) for k in ("choices", "lessons") for w in ("俠", "寇") for t in (1, 2)},
               "qiyu": round(events.qiyu_multiplier(s, c), 6), "tales": _luck_again(s, c)}
        if "yingchuan_join" in c.events:
            out["academy"] = check_condition(c.events["yingchuan_join"].condition, s, c)
        if epiphany.on(c, s):
            out["epiphany"] = epiphany.roll(s, c, _SeqRng(0.99, epiphany.chance(s, c) / 2))
        emit(f"{who} 門路 {tag}", out)

    def doors(self) -> None:
        for who in (self.RIGHT, self.DARK, self.LUCKY, self.TAKER):
            self.doors_of(who, "第二季")

    def gates(self) -> None:
        """解封的三道封印一道一道過（鈕灰著寫差什麼、按不下去）：15 級、心得、開季滿一天；過了才解得開（名字照這一季登記、扣心得）。"""
        who = self.KEEPER
        self.main(who)
        self.choose(who, "legacy:open")
        self.edit(who, lambda p: setattr(p.member, "level", self.c.config.legacy.shihai_level))
        self.main(who)
        self.edit(who, lambda p: p.stats.__setitem__("xinde", self.c.config.legacy.shihai_xinde + 30))
        self.main(who)
        self.do(ADMIN, "fast_forward", {"hours": 24})
        self.main(who)
        self.choose(who, "legacy:open")
        self.book(who, "解封之後")

    def clash(self) -> None:
        """段聽雨解封時，這一季已經有人先取了同名（冷秋白）：換三個候選。奚照影封著一份、身上又有一份：鈕灰著。前半停在這裡。"""
        names = self.GODS[self.CLASH]
        self.world.mutate_season(lambda s: s.god_names.__setitem__(names[0], self.TAKER))
        self.unsealable(self.CLASH)
        self.main(self.CLASH)
        self.choose(self.CLASH, "legacy:open")
        self.book(self.CLASH, "撞名")
        self.unsealable(self.HOLDER)
        self.edit_state(self.HOLDER, lambda s: self.give_god(s, self.SECOND_GOD))
        self.main(self.HOLDER)
        self.choose(self.HOLDER, "legacy:open")
        self.book(self.HOLDER, "身上還有一份")

    def half(self) -> None:
        self.main(self.WAITER)
        self.choose(self.WAITER, "act:train")
        self.book(self.WAITER, "前半停在識海那一步")
        self.main(self.LATE)
        self.book(self.LATE, "前半連配比都沒挑")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def clash_on(self) -> None:
        self.main(self.CLASH)
        self.choose(self.CLASH, "legacy:name:9")
        self.choose(self.CLASH, "legacy:name:0")
        self.book(self.CLASH, "挑了候選")

    def offers_on(self) -> None:
        """舊程式開著的卡，新程式接著按。"""
        self.choose(self.WAITER, "legacy:seal:0")
        self.choose(self.LATE, f"growth:{self.v2().presets[0].key}")
        self.choose(self.LATE, "legacy:skip")
        for who in (self.WAITER, self.LATE):
            self.settle_choices(who)
            self.book(who, "接著按完")

    def holder_on(self) -> None:
        """奚照影放掉身上那一份，解得開了。"""
        def drop(s) -> None:
            p = s.player
            for iid in list(p.own_insights):
                p.insights.remove(iid)
                del p.own_insights[iid]
                del p.insight_fx[iid]

        self.edit_state(self.HOLDER, drop)
        self.main(self.HOLDER)
        self.choose(self.HOLDER, "legacy:open")
        self.book(self.HOLDER, "解封之後")

    def bots(self) -> None:
        """假人換季後：照名號挑配比、封第一份。"""
        self.tick(self.BOT_SEATS, 4, "第二季開季")

    def bots_open(self) -> None:
        """條件到了假人解封。"""
        for name in self.BOT_SEATS:
            self.unsealable(name)
        self.tick(self.BOT_SEATS, 4, "條件到了")

    def second_season(self) -> None:
        """第二季的傳：韓松濤這一季沒做善事（落回去、第三道門路收回），厲冬青又作惡（往上爬）。"""
        self.edit_state(self.DARK, lambda s: s.player.stats.__setitem__("evil", 400))

    def turn_two(self) -> None:
        self.do(ADMIN, "end_season")
        self.do(ADMIN, "next_season")
        self.past_card(ADMIN)

    def sheets_two(self) -> None:
        for who in self.EVERYONE:
            self.main(who)
            self.book(who, "第二次結算")
            self.doors_of(who, "第三季")

    def card_two(self) -> None:
        """第三季：解封過的算身上的，又列進候選；封著沒解的那一份不再帶。"""
        for who in self.EVERYONE:
            self.past_card(who)
            self.settle_choices(who)
            self.book(who, "第三季卡之後")

    def bots_two(self) -> None:
        self.tick(self.BOT_SEATS, 3, "第三季開季")


TRACK_REQUIRES.update({"growth": GrowthScenario.TRACK_FILE, "legacy": LegacyScenario.TRACK_FILE})


# 改一個字（selftest）：歷練到頂那一句（核心的 attrset，合回之後照舊在那裡）、識海不帶那一句（傳承包，develop 上已經是包）
register_track("growth", GrowthScenario, (("tianxia/attrset.py",), ("這一季的歷練已到火候", "這一季的歷練已達火候")), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "figure_acts", "gear", "guide", "heroines", "legacy", "looks", "mall", "military", "outlets", "peers",
                       "seal", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story", "tavern", "travel", "zhuan",
                       "zongmen"))
register_track("legacy", LegacyScenario, (("tianxia/features/legacy/actions.py",), ("這一季識海不帶上一季的神品意境。", "這一季識海不帶上一季的神品意境！")), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "figure_acts", "gear", "guide", "heroines", "jieyi", "legacy", "looks", "mall", "military", "outlets",
                       "peers", "seal", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story", "tavern", "territory_acts",
                       "travel", "zhuan", "zongmen"))
