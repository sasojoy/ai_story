"""same_behavior 一軌一檔：censer（這一檔登記 censer）。"""
from __future__ import annotations

import random
from pathlib import Path

from sb.harness import ADMIN, CLOCK, MODEL, STEP, emit, register_track
from sb.tracks.talk import TalkScenario

# ═══════════════════════════ censer：心神與問酒家的次數（架構收尾第 105 批，dev/fold-back） ═══════════════════════════
# 心神的本體從 Game 搬進 tianxia/core/xinshen.py、問酒家的次數從核心搬回酒肆包（計畫 docs/superpowers/plans/2026-11-08-架構收尾-第105批.md）。
# talk 軌只走到免費那一份、tavern 軌只問到剛好用完：存著的、月卡、次數用完被擋、換日補回，這一軌才走到。班底的名字都是原創（第 22 批 PM 認定第 3 條）。

CENSER_REPLY = "客官，這一帶近來還算太平，城外倒是常有人走動。"
_CENSER_CLIENTS: dict[type, type] = {}


def _censer_client(base: type) -> type:
    """問酒家的假模型（疊在人物對話那一層上）：MODEL["censer"] 給了時 AskReply 回那一句，沒給照 base（丟連線錯誤，就是叫不動）。
    MODEL["censer_between"] 給了時回話之前先叫一次：A 段過了、C 段還沒到的那一下，次數被別的視窗用完。"""
    if base not in _CENSER_CLIENTS:
        class CenserClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                if schema.__name__ == "AskReply" and MODEL.get("censer") is not None:
                    between = MODEL.pop("censer_between", None)
                    if between is not None:
                        between()
                    return schema(reply=MODEL["censer"])
                return super().chat_structured(messages, schema, *a, **k)

        _CENSER_CLIENTS[base] = CenserClient
    return _CENSER_CLIENTS[base]


class CenserScenario(TalkScenario):
    """心神與問酒家（架構收尾第 105 批；--track censer，自己一個資料庫）。小工具借人物對話那一軌的（stand、talking、say）。
    前半：焚香客談盧植，按選項扣 1、自己說扣 2，把免費那一份用完（灰掉、寫明早補回來）；買凝神香，交談動存著的（購買那一列記用掉幾點）。
    佩卡翁買月卡，當天就有那一份、狀態列上限變高、先扣月卡。問酒人在潁川問酒家：叫不動不算、問秘密不算、答上來才算，問掉兩次。
    **切在寫到一半**：焚香客存著的用了一部分、還在談；佩卡翁月卡用了一部分；問酒人今天的次數記了兩次、還坐在酒肆裡。
    後半（新程式）：resume 重新登入；burn_on 接著談，把存著的用完、再買一支；不經路由叫 Game 上留的委派（一口氣扣太多回 False、free_only 不動存著的與月卡）；
    asks_on 問第三次（剩 0）、第四次 A 段就擋；next_day 時鐘推過台灣 00:00：免費、月卡補滿，存著的還在，次數回來；A 段過了之後次數被用完，C 段重驗擋下、不收錢。
    bots 假人（人物對話那一軌的 BotRunner 十輪）、第一位擺成談著，假人那一輪照樣算選單上的心神；season 換季：存著的帶走、其餘重來。
    test 設定心神關著，同一串 API 照打（扣體力、問酒家不限次數、商城 404）。
    這一軌走不到的：free_only 的路由（現在沒有路由叫，只走 at_hand）；存著的跨兩筆扣、退款收回（use_bank 這一批沒搬，tests/core/test_xinshen.py 守）；
    網頁與樣式（第 105 批搬的 js、css 由 facade、drape 兩軌比）。"""

    BURNER, CARDED, ASKER = "焚香客", "佩卡翁", "問酒人"
    TALKER = BURNER  # 借人物對話那一軌的 bots（假人眼中的分數）
    PLAYERS = {BURNER: "guan", CARDED: "guan", ASKER: "guan"}
    NEWBIE = "添炷人"
    BOT_SEATS = ["爐甲", "爐乙", "爐丙"]
    ASK = "潁川城外近來太平嗎？"
    PHASES_FIRST = ["setup", "seat", "burn", "incense", "card", "asks", "half"]
    PHASES_SECOND = ["resume", "burn_on", "asks_on", "next_day", "bots", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # 人物對話那一軌換好的那一層

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            client.__class__ = _censer_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

    # ── 小工具 ──

    def saved(self, who: str, tag: str) -> None:
        """存檔與帳上心神碰得到的：免費、月卡兩份與它們的日子、問酒家的次數、體力、銀兩、今天聊幾輪；帳上每一筆買的與用掉的點數。"""
        from tianxia.characters import name_key
        from tianxia.wallet import Wallet

        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "free": [p.xinshen_free, p.xinshen_free_day], "card": [p.xinshen_card, p.xinshen_card_day], "asks": p.tavern_asks,
            "stamina": p.stamina, "silver": p.stats.get("silver", 0), "talks_today": dict(sorted(p.talks_today.items())), "talking": p.pending_companion,
            "bought": [[x.item, x.data] for x in Wallet(self.world.db).purchases(name_key(who))]})

    def look(self, who: str, tag: str) -> None:
        """/api/main 整份（輸出裡有狀態列那一格 status.xinshen、選單上的心神幾點、酒肆那一頁的 shop.asks_left），再加存檔那幾格。"""
        self.main(who)
        self.saved(who, tag)

    def fund(self, who: str, ref: str, amount: int = 900) -> None:
        self.do(ADMIN, "mall_reissue", {"name": who, "amount": amount, "note": "香爐", "ref": ref})

    def buy(self, who: str, item: str, ref: str) -> None:
        self.call(who, "POST", "/api/mall/buy", {"item": item, "ref": ref})

    def at_hand(self, who: str, tag: str, fn) -> None:
        """不經路由叫 Game 上留的委派（free_only 現在沒有路由叫；一口氣扣太多選單本來就擋）：照伺服器那樣拿鎖、同步、做、存。"""
        from tianxia.engine import Game

        self.begin()
        with self.world.action_lock():
            g = Game(self.c, self.chars.load(who), world=self.world)
            g.client = None
            g.sync(CLOCK[0])
            out = fn(g)
            g._save_season()
            self.chars.save(g.state)
        emit(f"{who} {tag}", out)

    def ask_keeper(self, text: str = "") -> None:
        self.do(self.ASKER, "tavern_ask", {"text": text or self.ASK})

    # ── 前半 ──

    def burn(self) -> None:
        """免費那一份：按選項扣 1、自己說扣 2；剩 1 點時自己說灰掉；用完灰掉、寫明早補回來，灰掉了再按一下什麼都不動。"""
        who, cid = self.BURNER, self.fig
        if cid is None:
            emit("這份內容沒有人物", None)
            return
        self.stand(who, cid)
        self.talking(who, cid)
        MODEL["talk"] = {"stance": "suzhan"}
        self.look(who, "開談之前")
        self.choose(who, "talk:0")
        self.look(who, "按了一顆")
        self.say(who, "願聞其詳")
        self.say(who, "再請教一事")
        self.look(who, "自己說了兩句，剩一點")
        self.say(who, "還想再問")
        self.choose(who, "talk:0")
        self.look(who, "免費用完")
        self.choose(who, "talk:0")
        self.saved(who, "用完了再按一下")

    def incense(self) -> None:
        """凝神香：買一支（status.xinshen.bank）、交談動存著的（購買那一列的 xinshen_spent），切點前留一部分沒用。"""
        who = self.BURNER
        self.fund(who, "censer-burner")
        self.buy(who, "xinshen_5", "censer-stick")
        self.look(who, "買了一支")
        if self.fig is None:
            return
        self.choose(who, "talk:0")
        self.say(who, "香燃著，且再談")
        self.look(who, "用了存著的三點")

    def card(self) -> None:
        """月卡：買卡當天就有那一份、上限變高；一般交談先扣月卡。"""
        who, cid = self.CARDED, self.fig
        if cid is None:
            return
        self.stand(who, cid)
        self.talking(who, cid)
        self.look(who, "還沒買卡")
        self.fund(who, "censer-carded")
        self.buy(who, "card_30", "censer-card")
        self.look(who, "買了月卡")
        self.choose(who, "talk:0")
        self.look(who, "扣了月卡一點")

    def asks(self) -> None:
        """問酒家：叫不動不算、問秘密不算（不叫模型）、答上來才算；切點前問掉兩次。"""
        who = self.ASKER
        self.place(who, "yingchuan")
        self.edit(who, lambda p: p.stats.update({"silver": 900}))
        self.choose(who, "act:tavern")
        self.look(who, "坐進酒肆")
        MODEL.pop("censer", None)
        self.ask_keeper()
        self.saved(who, "叫不動")
        MODEL["censer"] = CENSER_REPLY
        self.ask_keeper("神器配方怎麼湊？")
        self.saved(who, "問秘密")
        self.ask_keeper()
        self.ask_keeper()
        self.look(who, "問掉兩次")

    def half(self) -> None:
        MODEL["talk"] = None  # 假模型的設定不跨行程：後半每一段自己設，整段與前半＋後半才一樣
        MODEL.pop("censer", None)
        for who in self.PLAYERS:
            self.saved(who, "前半停在這裡")

    # ── 後半 ──

    def burn_on(self) -> None:
        """新程式接著談：存著的用完、灰掉、再買一支；佩卡翁扣完月卡再扣免費；不經路由叫委派：扣太多回 False、free_only 不動存著的與月卡。"""
        MODEL["talk"] = {"stance": "xumin"}
        if self.fig is not None:
            self.say(self.BURNER, "再添一炷香")
            self.look(self.BURNER, "存著的用完")
            self.choose(self.BURNER, "talk:0")
            self.saved(self.BURNER, "沒有了再按一下")
            self.buy(self.BURNER, "xinshen_5", "censer-stick-2")
            self.look(self.BURNER, "再買一支")
            for _ in range(3):
                self.say(self.CARDED, "還請賜教")
            self.choose(self.CARDED, "talk:0")
            self.look(self.CARDED, "月卡用完、動了免費")
        self.at_hand(self.CARDED, "扣太多、只扣免費", lambda g: [g.xinshen_spend(99), g.xinshen_spend(1, free_only=True), g.xinshen_view()])
        self.saved(self.CARDED, "只扣免費之後")
        self.at_hand(self.BURNER, "沒有免費的時候只扣免費", lambda g: [g.xinshen_spend(1, free_only=True), g.xinshen_view()])

    def asks_on(self) -> None:
        """新程式接著數舊程式記的兩次：第三次剩 0、第四次 A 段就擋（不收錢）。"""
        MODEL["censer"] = CENSER_REPLY
        self.ask_keeper()
        self.look(self.ASKER, "第三次")
        self.ask_keeper()
        self.look(self.ASKER, "第四次被擋")

    def next_day(self) -> None:
        """時鐘推過台灣 00:00（CLOCK0 是 12:00，一步一分）：免費、月卡補滿，存著的還在，次數回來；A 段過了之後次數被用完，C 段重驗擋下、退錢。"""
        STEP[0] += 720
        emit("時鐘推過 720 分", None)
        for who in self.PLAYERS:
            self.look(who, "隔天")
        self.at_hand(self.BURNER, "隔天只扣免費", lambda g: [g.xinshen_spend(1, free_only=True), g.xinshen_view()])
        self.ask_keeper()
        self.saved(self.ASKER, "隔天問一次")

        def use_up() -> None:
            self.edit(self.ASKER, lambda p: setattr(p, "tavern_asks", [p.tavern_asks[0], 3]))

        MODEL["censer_between"] = use_up
        try:
            self.ask_keeper()
        finally:
            MODEL.pop("censer_between", None)
        self.look(self.ASKER, "C 段重驗擋下")
        MODEL.pop("censer", None)
        MODEL["talk"] = None

    def bots(self) -> None:
        """假人：人物對話那一軌的 BotRunner 十輪；第一位擺成談著，再跑三輪，假人那一輪照樣算選單上的心神（假人只按告辭）。"""
        super().bots()
        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner

        first = self.BOT_SEATS[0]
        if self.fig is not None:
            self.talking(first, self.fig)
        self.saved(first, "假人擺成談著")
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(19), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {71 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        try:
            for _ in range(3):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                emit("假人那一輪", [report.acted, report.added, report.skipped, report.failed, report.online])
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        self.saved(first, "假人那幾輪之後")

    def season(self) -> None:
        """收季、開下一季：存著的在帳號上帶走，免費、月卡的格子與問酒家的次數跟著新角色重來。"""
        self.do(ADMIN, "end_season")
        self.main(self.BURNER)
        self.do(ADMIN, "next_season")
        for who in self.PLAYERS:
            self.look(who, "換季之後")


# 改一個字（selftest）：次數用完那一句（xinshen.ASKS_DONE，第 105 批留在核心）；week7 問酒人第四次、C 段重驗都抓得到
register_track("censer", CenserScenario, (("tianxia/core/xinshen.py",), ("今天問得夠多了，明天再來吧。", "今天問得夠多了，明日再來吧。")), "week7")
