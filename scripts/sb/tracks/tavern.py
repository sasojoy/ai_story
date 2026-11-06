"""same_behavior 一軌一檔：tavern（這一檔登記 tavern）。"""
from __future__ import annotations

import contextlib
import hashlib
import os
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, CLOCK0, MODEL, STEP, STEP_SECONDS, emit, register_track

# ═══════════════════════════ tavern：酒肆一軌（主動搬六包第 10 批，dev/tavern-1） ═══════════════════════════
# 酒肆的引擎那一半搬進 tianxia/features/tavern/（計畫 docs/superpowers/plans/2026-10-31-酒肆包-第1批.md）。這一段整塊是酒肆的：
# 三條拆包線並行，接在檔尾、最後一行登記（register_track），PM 合的時候不跟別人的行穿插。

# develop 0425589a 之後才要的兩個固定（註冊限流、資料庫第 9 版 sessions 的 token_hash 抹掉）：這一塊原本自己套一份（換掉 Scenario.__init__、
# 模組層的 db_text），合 develop（2026-11-01）時 develop 已經放在共用那一層（Scenario.__init__、db_text），只留那一份。


TAVERN_CHATTER = ["靠窗的腳夫：「今兒這酒倒是沒摻水。」", "喝悶酒的老卒：「城外又不太平了。」"]  # 假模型寫的鄰桌閒談
TAVERN_UNSURE = "客官，這事我不清楚。"  # 假模型的酒家：說不上來（退一半、指一條路）
TAVERN_REPLY = "客官，潁川一帶近來還算太平，城外倒是常有人走動。"  # 假模型的酒家：正常回話
_TAVERN_CLIENTS: dict[type, type] = {}


def _tavern_client(base: type) -> type:
    """問酒家、鄰桌閒談的假模型（base 是 _setup_child 那一層換好的 client 類別）：AskReply 回 MODEL["tavern"] 那一句、ChatterReply 回
    TAVERN_CHATTER，其餘照 base（丟連線錯誤、大場面判讀）。"""
    if base not in _TAVERN_CLIENTS:
        class TavernClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                if schema.__name__ == "AskReply":
                    return schema(reply=MODEL["tavern"])
                if schema.__name__ == "ChatterReply":
                    return schema(lines=list(TAVERN_CHATTER))
                return super().chat_structured(messages, schema, *a, **k)

        _TAVERN_CLIENTS[base] = TavernClient
    return _TAVERN_CLIENTS[base]


class TavernScenario(Scenario):
    """酒肆（主動搬六包第 10 批；--track tavern，自己一個資料庫）。照調查 survey_tavern.json 的 behavior_check：進酒肆、看（main.shop）、
    聽消息、查人（確切、託付留意、查無此人、自己、人物）、交情、素材、題壁、請酒（換日再請）、藏行跡、反查、保鏢、問酒家（鎖外三段式，
    假模型）、鄰桌閒談（server.chatter_once，假模型）、牆上的懸賞榜、買殺手；被打聽的人收風聲、殺手在城外做一件事時找上（得手）、
    站在城外下線回來時找上（失手）、同一對人連著失手（加價五成、威力 +0.1、最多 3 次）、雇主收結果、過期退一半、託付留意捎信與到期；
    得手之後的護身期內殺手不擲、藏了行跡的人殺手的打聽度少一截、酒肆關著時殺手不擲（審查之後補的：原本只走到買與欄位）；
    同一次同步收到風聲、殺手單的結果、託付到期與書信（sync 裡三個 deliver 的先後與位置，crossing）；酒肆開關關著時（記憶體裡關）坐著的人照樣出得去、三個 deliver 照樣送；伺服器假人（BotRunner）進酒肆；換季。
    殺手那一場用 killer(tier)：tavern.find_chance 換成 1（或 0）、單次判定照 tier（本人這一邊的結果）。
    四種正式設定都站潁川一帶；測試內容沒有酒肆、沒有陣營，同一串 API 照打（證明關著一個字都不變），假人那一段略過。
    半舊半新切在 hire 之後：四張殺手單沒結、風聲沒送到、託付沒回音（批次表第二節「還沒結的殺手單」）。"""

    PLAYERS = {"葉開": None, "阿飛": None, "丁鵬": None, "孟星魂": None, "郭大路": None}  # 都是散人
    NEWBIE = "燕七"  # 不略過引導（none、weekend 還在序章：不在酒肆、沒有入口）
    # 葉開打聽、阿飛雇主（都坐在潁川）；丁鵬被打聽、被殺手得手（潁川郊野）；孟星魂被通緝、連著失手（潁水河畔）；
    # 郭大路被託付留意、站在城外下線時殺手失手（長社）
    SEATS = {"葉開": "yingchuan", "阿飛": "yingchuan", "丁鵬": "yingchuan_wilds", "孟星魂": "yingshui", "郭大路": "changshe"}
    FAME = {"丁鵬": 300, "孟星魂": 120, "郭大路": 0}
    BOT_SEATS = [("柳長街", "guan", "yingchuan"), ("卓東來", "huang", "wan_city"), ("王動", "guan", "runan"), ("鐵中棠", "huang", "zhuo_county")]
    PHASES_FIRST = ["setup", "seat", "enter", "ops", "keeper", "chatter", "board", "hire"]
    PHASES_SECOND = ["resume", "whispers", "strike", "away", "streak", "lapse", "watch", "crossing", "trace", "depart", "closed", "bots",
                     "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            if MODEL.get("tavern") is not None:
                client.__class__ = _tavern_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

    # ── 小工具 ──

    def begin(self) -> None:
        """同約戰那一軌：每個請求換一份空的勝算記憶（前半＋後半是兩個行程，城外那幾位選單上的勝算字才對得上）。"""
        super().begin()
        from tianxia import team

        self.server.ODDS_MEMO = team.OddsMemo()

    def skip(self, steps: int) -> None:
        STEP[0] += steps
        emit(f"時鐘推過 {steps} 分", None)

    def now(self) -> float:
        """下一個請求之前的現實時刻（同 begin 的算法）。"""
        return CLOCK0 + STEP[0] * STEP_SECONDS

    def tav(self, who: str, op: str, target: str = "", text: str = ""):
        """店面那一頁的動作（/api/do/tavern → MAIN_ACTIONS["tavern"] → Game.tavern_do）。"""
        return self.do(who, "tavern", {"op": op, "target": target, "text": text})

    def me(self, who: str, tag: str) -> None:
        """存檔裡酒肆那幾格（酒肆包認領的十個欄位），加上銀兩、名望、惡名、氣血。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "silver": p.stats.get("silver", 0), "fame": p.stats.get("fame", 0), "evil": p.stats.get("evil", 0), "neili": p.member.neili,
            "picking_tavern": p.picking_tavern, "tavern_notes": [n.model_dump() for n in p.tavern_notes], "tavern_heard": p.tavern_heard,
            "tavern_known": p.tavern_known, "tavern_treat_day": p.tavern_treat_day, "whispers": [w.model_dump() for w in p.whispers],
            "hidden_until": p.hidden_until, "tavern_watches": [w.model_dump() for w in p.tavern_watches],
            "tavern_guard_until": p.tavern_guard_until, "tavern_shield_until": p.tavern_shield_until})

    def hits(self, tag: str) -> None:
        s = self.world.get_season()
        emit(f"季上的殺手單 {tag}", [h.model_dump() for h in s.tavern_hits])
        emit(f"季上還沒送的風聲 {tag}", {k: [w.model_dump() for w in v] for k, v in sorted(s.tavern_whispers.items())})

    @contextlib.contextmanager
    def killer(self, tier: str | None):
        """殺手那一場定死：tier 給了，tavern.find_chance 換成 1、單次判定照 tier（本人這一邊的結果，照樣用掉那一場的一個亂數），
        記下殺手威力 ÷ 本人威力；tier 是 None，find_chance 換成 0（擲了、找不到）。換的都是模組屬性（tianxia.tavern 是包裡 rules 的別名）。
        也記下殺手擲的那一下的打聽度（find_chance 拿到的 reach：藏行跡扣 hide_reach；一個都沒有＝殺手沒擲）。"""
        from tianxia import encounter, tavern

        real_find, real_resolve = tavern.find_chance, encounter.resolve_encounter
        seen: list[float] = []
        reaches: list[int] = []

        def fake(mine, theirs, rng, *a, **k):
            rng.random()
            seen.append(round(theirs / mine, 6) if mine else None)  # 選單上的勝算也走這裡（照樣換成 tier）
            return encounter.EncounterResult(tier=tier, margin=0.0, our_power=mine, difficulty=theirs)

        def find(c, reach):
            reaches.append(reach)
            return 1.0 if tier else 0.0

        tavern.find_chance = find
        if tier:
            encounter.resolve_encounter = fake
        try:
            yield seen
        finally:
            tavern.find_chance, encounter.resolve_encounter = real_find, real_resolve
            emit(f"殺手那一場（{tier or '找不到'}）殺手威力 ÷ 本人威力", seen)
            emit(f"殺手那一場（{tier or '找不到'}）殺手擲的打聽度", reaches)

    def act_outside(self, who: str) -> None:
        """在城外做一件事（choose 最後那一下是殺手檢查）：體力補滿，選單上第一個按得下去的 act:explore／act:train／act:socialize；
        都沒有（出門一趟碰上的事件待選）就選那一則事件第一個按得下去的選項。"""
        self.place(who, None)
        ids = self.ids(self.main(who))
        pick = next((i for i in ("act:explore", "act:train", "act:socialize") if (ids.get(i) or {}).get("enabled")), None)
        pick = pick or next((i for i, o in ids.items() if i.startswith("choice:") and o.get("enabled")), None)
        emit(f"{who} 在城外做的事", pick)
        if pick is not None:
            self.choose(who, pick)

    def unpair(self, client: str, target: str) -> None:
        """錯開同一對人 hit_pair_hours 一次的限制、清掉截殺那一道護身（時鐘推不了那麼遠）：直接改季上的單子與 raided。"""
        from tianxia.characters import name_key

        gap = self.c.config.tavern.hit_pair_hours * 3600 + 10

        def fn(s) -> None:
            for h in s.tavern_hits:
                if name_key(h.client) == name_key(client) and name_key(h.target) == name_key(target):
                    h.placed_real -= gap
            s.raided.pop(name_key(target), None)

        self.world.mutate_season(fn)
        emit(f"錯開 {client}→{target} 的冷卻、清掉護身", None)

    # ── 前半 ──

    def seat(self) -> None:
        """站好位置、給銀兩與名望（直接改資料庫）；季上擺兩張通緝（孟星魂、郭大路：揭了的通緝不必先查也雇得了殺手、名氣 +1）。"""
        from tianxia import tavern
        from tianxia.state import Bounty

        for who, loc in self.SEATS.items():
            self.place(who, loc)
            fame = self.FAME.get(who)

            def fn(p, fame=fame) -> None:
                p.stats["silver"] = 900
                if fame is not None:
                    p.stats["fame"] = fame

            self.edit(who, fn)
        emit("城外嗎", {loc: tavern.town(self.c, loc) for loc in self.SEATS.values() if loc in self.c.locations})

        def post(s) -> None:
            for poster, target in (("阿飛", "孟星魂"), ("葉開", "郭大路")):
                s.bounty_seq += 1
                s.bounties.append(Bounty(id=f"b{s.bounty_seq}", kind="wanted", faction=None, week=1, expires=s.time + 30 * 86400,
                                         silver=50, deeds=0, quota=1, poster=poster, target=target))

        self.world.mutate_season(post)
        emit("擺兩張通緝：孟星魂、郭大路", None)
        for who in [*self.PLAYERS, self.NEWBIE]:
            emit(f"{who} 的 act:tavern", self.ids(self.main(who)).get("act:tavern"))

    def enter(self) -> None:
        """入口：還沒進店的 tavern_do 被拒；act:tavern 打開店面（main.shop）；阿飛也進同一間。"""
        self.tav("葉開", "news")
        out = self.choose("葉開", "act:tavern")
        emit("葉開 酒肆裡的選單", sorted(self.ids(out)))
        self.choose("阿飛", "act:tavern")

    def ops(self) -> None:
        """店面那一頁的動作一樣一樣做（成的與被拒的各一次）；選單上那幾顆（tavern:news、treat、hide、trace）走 /api/choose，
        是酒肆包的 choose 掛鉤接走的那一條。"""
        c = self.c
        self.choose("葉開", "tavern:news")
        self.tav("葉開", "news")
        self.tav("葉開", "seek", "丁鵬")
        self.tav("葉開", "seek", "郭大路", "watch")  # 問不清楚：多付一點託酒家留意
        self.tav("葉開", "seek", "郭大路", "watch")  # 同一個人再託
        self.tav("葉開", "seek", "查無此人")
        self.tav("葉開", "seek", "葉開")
        self.tav("葉開", "seek", "")
        figure = next((f for f in c.figures.values() if f.character in c.characters), None)
        fname = c.characters[figure.character].name if figure is not None else "曹操"
        self.tav("葉開", "seek", fname, "watch")  # 人物一問就清楚：不託
        self.tav("葉開", "ties", "丁鵬")
        self.tav("葉開", "ties", fname)
        mats = sorted(c.materials.values(), key=lambda m: (m.tier, m.id))
        for tier in (1, 3):
            m = next((m for m in mats if m.tier == tier), None)
            if m is not None:
                self.tav("葉開", "material", m.id)
        self.tav("葉開", "material", "沒有這樣東西")
        self.tav("葉開", "wall", "", "潁川城頭月，照我一壺酒。")
        self.tav("葉開", "wall", "", "假人寫的字")
        self.tav("葉開", "wall", "", "字" * (c.config.tavern.wall_chars + 1))
        self.tav("葉開", "wall", "", "")
        self.choose("葉開", "tavern:treat")
        self.tav("葉開", "treat")  # 今天請過了
        self.edit("葉開", lambda p: setattr(p, "tavern_treat_day", p.tavern_treat_day - 1))  # 換日（請酒照回體丹那一天）
        emit("葉開 請酒那一天擺成昨天", None)
        self.tav("葉開", "treat")
        self.choose("葉開", "tavern:hide")
        self.tav("葉開", "hide")
        self.choose("葉開", "tavern:trace")  # 沒人打聽：不收錢
        self.tav("葉開", "guard")
        self.tav("葉開", "guard")
        self.tav("葉開", "bogus")
        self.me("葉開", "店面做完")

    def keeper(self) -> None:
        """問酒家（/api/do/tavern_ask：A 鎖內開單 → B 鎖外請模型 → C 鎖內重驗才收錢）：叫不動模型退全額、問秘密收一半（不叫模型）、
        說不清楚退一半、正常回話、空的、太長。"""
        q = "潁川城外近來太平嗎？"
        self.do("葉開", "tavern_ask", {"text": q})
        self.do("葉開", "tavern_ask", {"text": "神器配方怎麼湊？"})
        try:
            MODEL["tavern"] = TAVERN_UNSURE
            self.do("葉開", "tavern_ask", {"text": "精鐵砂好不好用？"})
            MODEL["tavern"] = TAVERN_REPLY
            self.do("葉開", "tavern_ask", {"text": q})
            self.do("葉開", "tavern_ask", {"text": ""})
            self.do("葉開", "tavern_ask", {"text": "問" * (self.c.config.tavern.ask_chars + 1)})
        finally:
            MODEL.pop("tavern", None)

    def chatter(self) -> None:
        """鄰桌閒談（server.chatter_once：A 鎖內開單、B 鎖外請模型寫〔假模型〕、C 鎖內重驗才記）；第二次這一陣子不再寫。"""
        try:
            MODEL["tavern"] = TAVERN_REPLY
            for _ in range(2):
                self.begin()
                emit("鄰桌閒談 chatter_once", self.server.chatter_once(self.server.game_for("葉開")))
        finally:
            MODEL.pop("tavern", None)
        self.main("葉開")

    def board(self) -> None:
        """牆上的懸賞榜：tavern:board 收起酒肆、打開懸賞榜；返回之後再進酒肆、出酒肆、再進（葉開接下來一直坐在酒肆裡）。"""
        if "tavern:board" in self.ids(self.main("葉開")):
            out = self.choose("葉開", "tavern:board")
            if "bounty:back" in self.ids(out):
                self.choose("葉開", "bounty:back")
        else:
            emit("牆上沒有懸賞榜", None)
        self.choose("葉開", "act:tavern")
        self.choose("葉開", "tavern:back")
        self.choose("葉開", "act:tavern")

    def hire(self) -> None:
        """買殺手：阿飛沒查過就雇（要先查到過）、壞的檔次、查了雇丁鵬、再雇被拒（身上已有別人的單）、雇被通緝的郭大路加封口；
        葉開雇被通緝的孟星魂、查了雇坐在城裡的阿飛（殺手等著，之後擺成過期）。切在這裡：四張單沒結、風聲沒送、託付沒回音。"""
        self.tav("阿飛", "hit", "丁鵬", "0")
        self.tav("阿飛", "seek", "丁鵬")
        self.tav("阿飛", "hit", "丁鵬", "9")
        self.tav("阿飛", "hit", "丁鵬", "0")
        self.tav("阿飛", "hit", "丁鵬", "1")
        self.tav("阿飛", "hit", "郭大路", "2:hush")
        self.tav("葉開", "hit", "孟星魂", "0")
        self.tav("葉開", "seek", "阿飛")
        self.tav("葉開", "hit", "阿飛", "0")
        self.hits("前半最後")

    # ── 後半 ──

    def resume(self) -> None:
        """重新登入每一個帳號（登入也同步：被雇的人下線那一段殺手照樣擲一次，find_chance 換成 0：找不到，殺手留到後面那幾段）。"""
        with self.killer(None):
            self.login_all()

    def whispers(self) -> None:
        """被打聽、被雇的人自己同步時收風聲；下線那一段殺手照樣擲一次（find_chance 換成 0：找不到）。"""
        with self.killer(None):
            for who in ("丁鵬", "孟星魂"):
                self.main(who)
        self.me("丁鵬", "收了風聲")

    def strike(self) -> None:
        """丁鵬在城外做完一件事：殺手找上門，這一場殺手贏（氣血剩 1、銀兩照丟、之後一陣子殺手找不上）；雇主阿飛同步收「得手」與惡名。
        阿飛同一對人 hit_pair_hours 內再雇被拒（審查：HIT_PAIR 原本沒有走到）。
        護身（審查：原本只寫了欄位，沒走到效果）：清掉截殺那一道護身（不然它先擋），葉開雇一張找丁鵬，丁鵬在 tavern_shield_until 之內
        再到城外做一件事——殺手不擲（killer 記不到打聽度）。這一張留著（後面那幾段丁鵬都在城裡）。"""
        from tianxia.characters import name_key

        with self.killer("落敗"):
            self.act_outside("丁鵬")
        self.me("丁鵬", "殺手得手之後")
        self.main("阿飛")
        self.me("阿飛", "收了得手")
        self.tav("阿飛", "hit", "丁鵬", "0")  # 同一對人 hit_pair_hours 內再雇：被拒（HIT_PAIR；上一張結了，不是 HIT_TAKEN 擋的）
        self.world.mutate_season(lambda s: s.raided.pop(name_key("丁鵬"), None))
        emit("清掉丁鵬截殺那一道護身（只留殺手得手的護身）", None)
        self.tav("葉開", "hit", "丁鵬", "0")
        with self.killer("落敗"):
            self.act_outside("丁鵬")
        self.me("丁鵬", "護身期內在城外做完一件事")

    def away(self) -> None:
        """郭大路站在城外下線（seat 那一下之後就沒同步過），時鐘再推過十二分：回來同步時殺手照下線那一段擲，這一場對方贏
        （撿到銀兩、名望、雇主可能被供出）；阿飛同步收「失手」。"""
        self.skip(12)
        with self.killer("大勝"):
            self.main("郭大路")
        self.me("郭大路", "打退殺手之後")
        self.main("阿飛")

    def streak(self) -> None:
        """同一個雇主找同一個人連著失手：孟星魂先進潁川雇保鏢（殺手威力照 guard_scale 打折）、藏行跡（殺手的打聽度扣 hide_reach，
        killer 記下打聽度）再回城外；四輪平手——每一輪孟星魂在城外做一件事、葉開同步收「平手」、錯開冷卻與護身、再雇一張：價錢 +五成、
        威力 +0.1，第三次之後不再加（第五張在 crossing 出手，威力跟第四張一樣）。"""
        self.place("孟星魂", "yingchuan")
        self.choose("孟星魂", "act:tavern")
        self.tav("孟星魂", "guard")
        self.tav("孟星魂", "hide")
        self.choose("孟星魂", "tavern:back")
        self.place("孟星魂", "yingshui")
        for _ in range(4):
            with self.killer("僵持"):
                self.act_outside("孟星魂")
            self.main("葉開")
            self.unpair("葉開", "孟星魂")
            self.tav("葉開", "hit", "孟星魂", "0")
        self.hits("連著失手之後")

    def lapse(self) -> None:
        """葉開雇去找坐在城裡的阿飛的那一張擺成已經到期：阿飛同步時收成過期，葉開同步領回一半。"""
        until = self.now() - 1

        def fn(s) -> None:
            for h in s.tavern_hits:
                if h.target == "阿飛" and not h.done:
                    h.until_real = until

        self.world.mutate_season(fn)
        emit("葉開找阿飛的那一張擺成到期", None)
        self.main("阿飛")
        self.main("葉開")
        self.me("葉開", "領了退款")

    def watch(self) -> None:
        """託付留意：郭大路走進潁川、名望到頂（直接改資料庫），葉開同步時捎信「打聽到了」；再託一個查無此人的、擺成到期：捎一句沒聽到準信。"""
        self.place("郭大路", "yingchuan")
        self.edit("郭大路", lambda p: p.stats.__setitem__("fame", 100000))
        self.main("郭大路")
        self.main("葉開")
        self.tav("葉開", "seek", "查無此人", "watch")
        until = self.now() - 1

        def fn(p) -> None:
            p.tavern_watches = [w.model_copy(update={"until_real": until}) if w.target == "查無此人" else w for w in p.tavern_watches]

        self.edit("葉開", fn)
        emit("查無此人那一筆託付擺成到期", None)
        self.main("葉開")
        self.me("葉開", "託付收尾")

    def crossing(self) -> None:
        """sync 裡三個 deliver 的先後與位置（審查：之前沒有一次同步同時收到兩樣，換順序、整段挪到 on_sync 前面都抓不到）：
        葉開先託酒家留意一個查無此人的；孟星魂在城外做一件事，葉開連著失手三次之後的那一張出手、平手（價錢與威力停在上限）；阿飛在潁川的
        酒肆查藏了行跡的葉開（風聲記在季上）；葉開那一筆託付擺成到期、身上擺一封委託過期的信（letters.deliver 排在三個 deliver 後面，
        寫「書信」那一則）。然後葉開同步一次：風聲、殺手單的結果、託付到期、書信四則在同一下，江湖紀錄的先後照 sync 的順序。
        三個 deliver 的前後再各夾一格會寫紀錄的：前一格護衛補帳（_deliver_guard_credits）、後面翻地的守城分紅（_deliver_conquest，有領地
        爭奪的季）——三行整段挪過它們（例：挪到 _deliver_big_events 前面、挪到 _marks_tick 之後）也看得出來。_marks_tick、
        _stance_annals、_zhuan_tick 只寫行狀、不讀惡名，跟三個 deliver 的先後只能靠這兩格看。"""
        from tianxia import figure_aid
        from tianxia.state import Bounty, ConquestPayout, Letter

        c = self.c
        self.tav("葉開", "seek", "查無此人", "watch")
        with self.killer("僵持"):
            self.act_outside("孟星魂")
        self.unpair("葉開", "孟星魂")  # 錯開冷卻、清掉截殺那一道護身（closed 那一段再雇一張找他）
        self.tav("阿飛", "seek", "葉開")
        figure = next((f for f in c.figures.values() if f.character in c.characters), None)
        world_now = self.world.get_season().time
        until = self.now() - 1

        def fn(p) -> None:
            p.tavern_watches = [w.model_copy(update={"until_real": until}) if w.target == "查無此人" else w for w in p.tavern_watches]
            if figure is not None:
                task = Bounty(id="letter-crossing", kind="strike", faction=None, week=1, expires=world_now - 1, silver=0, deeds=0,
                              figure=figure.character, motive="委託")
                p.letters.append(Letter(id=900, kind="求援", sender=figure.character, at=world_now - 60, text="（求援）", task=task))

        self.edit("葉開", fn)
        emit("葉開 查無此人那一筆託付擺成到期、身上擺一封委託過期的信", figure.character if figure is not None else None)

        def bracket(s) -> None:  # 三個 deliver 前後緊鄰、會寫江湖紀錄的兩格：前面的護衛補帳、後面的翻地分紅（有領地爭奪的季）
            who = figure.name if figure is not None else "某人"
            s.guard_credits.setdefault("葉開", []).append(figure_aid.CREDIT_LINE.format(name=who, who="郭大路"))
            if s.conquest is not None and c.scenario.factions and "yingchuan" in c.locations:
                s.conquest.payouts.append(ConquestPayout(name="葉開", kind="guard", loc="yingchuan", side=c.scenario.factions[0].id,
                                                         silver=5, share=0.5, time=s.time))

        self.world.mutate_season(bracket)
        emit("季上擺葉開的護衛補帳與一筆守城分紅（三個 deliver 的前一格與後面那一格）", None)
        self.main("葉開")
        emit("葉開 同一下同步收到的（江湖紀錄新的在前）", [e.title for e in self.chars.load("葉開").journal[:8]])
        self.hits("同一下同步之後")

    def trace(self) -> None:
        """丁鵬進潁川的酒肆反查（有沒有問不出名號的風聲，照前半雇殺手那一下聽到風聲的是不是生面孔）。"""
        self.place("丁鵬", "yingchuan")
        self.choose("丁鵬", "act:tavern")
        self.choose("丁鵬", "tavern:trace")
        self.choose("丁鵬", "tavern:back")

    def depart(self) -> None:
        """坐在酒肆裡動身（核心收接縫，全部拆包第 11 批：Game._depart 收店那一行換成店面登記的收店，排在擂台之後）。丁鵬坐進潁川的酒肆：
        從輿圖安排前往被擋（atlas.travel_block「還坐在酒肆裡」）；Game._depart 本身（輿圖、移動、折返、人物帶路都從它出發，坐在店裡的人
        平常走不到這一行）在鎖裡直接叫一次：酒肆跟擂台、鐵匠鋪那幾間一起收起來、動身上路。之後擺回潁川。測試內容沒有潁川：同一串照打。"""
        from tianxia import atlas
        from tianxia.engine import Game

        start = "yingchuan" if "yingchuan" in self.c.locations else self.c.scenario.start_location
        dest = self.c.locations[start].connections[0] if self.c.locations[start].connections else start
        self.place("丁鵬", start)
        self.settle_choices("丁鵬")  # 前面出門碰上的事件還在待選：選掉（不然選單是那一則事件，沒有進酒肆那一顆）
        self.place("丁鵬", start)
        self.choose("丁鵬", "act:tavern")
        self.me("丁鵬", "動身之前")
        self.call("丁鵬", "POST", "/api/travel", {"place": dest, "mode": "walk"})
        self.me("丁鵬", "從輿圖安排前往之後")
        self.begin()
        with self.world.action_lock():
            game = Game(self.c, self.chars.load("丁鵬"), world=self.world)
            game.sync(CLOCK[0])
            route = atlas.way_to(game.state, self.c, dest)
            emit("丁鵬 直接動身", game._depart(route, "walk") if route is not None else None)
            self.chars.save(game.state)
        self.me("丁鵬", "動身之後")
        emit("丁鵬 動身之後的選單", sorted(self.ids(self.main("丁鵬"))))
        self.place("丁鵬", start)

    def closed(self) -> None:
        """酒肆開關關掉（記憶體裡，做完開回來）。開著時郭大路先坐進潁川的酒肆、照那一刻建一份 Game（建的時候開著，沒有收店）；
        關掉之後不 sync：選單照舊是酒肆那一串、假人看「出酒肆」照舊 0 分、按得出去（搬包之前 choose 那一支不看開關）。
        季上擺一則給丁鵬的風聲、一張阿飛找丁鵬的過期單子：關著照樣送到、照樣退一半（三個 deliver 不看開關）。
        坐在酒肆裡的葉開同步就收店、入口沒了、店面的動作與 tavern:news 都被拒。
        殺手不擲（審查：原本沒有人帶著活單站在城外）：開著時葉開再雇一張找孟星魂，關著時孟星魂在城外做一件事——killer 記不到打聽度。"""
        from tianxia import bot_policy
        from tianxia.characters import name_key
        from tianxia.engine import Game
        from tianxia.state import BotProfile, TavernHit, Whisper

        self.tav("葉開", "hit", "孟星魂", "0")
        self.choose("郭大路", "act:tavern")
        self.begin()
        game = Game(self.c, self.chars.load("郭大路"), world=self.world)
        cfg = self.c.config.tavern
        before = cfg.enabled
        cfg.enabled = False
        try:
            menu = game.options(odds=False)
            emit("關掉那一刻 郭大路的選單（沒有 sync）", [o.id for o in menu])
            back = next((o for o in menu if o.id == "tavern:back"), None)
            if back is not None:
                emit("關掉那一刻 假人看出酒肆", bot_policy.score(game, back, BotProfile(personality="普通", seed=1)))
                emit("關掉那一刻 出酒肆", game.choose("tavern:back"))
            now = self.now()

            def fn(s) -> None:
                s.tavern_whispers.setdefault(name_key("丁鵬"), []).append(
                    Whisper(kind="seek", who="葉開", place="yingchuan", time=s.time, named=True))
                s.tavern_hit_seq += 1
                s.tavern_hits.append(TavernHit(id=s.tavern_hit_seq, client="阿飛", target="丁鵬", tier=0, price=20, place="yingchuan",
                                               placed_real=now - 7200, until_real=now - 60))

            self.world.mutate_season(fn)
            emit("關著時季上擺一則風聲、一張過期的單子", None)
            view = self.main("葉開")
            emit("關著 葉開的 act:tavern", self.ids(view).get("act:tavern"))
            self.tav("葉開", "news")
            self.choose("葉開", "tavern:news")
            self.main("丁鵬")
            self.main("阿飛")
            self.me("丁鵬", "關著收了風聲")
            with self.killer("落敗"):
                self.act_outside("孟星魂")
            self.hits("關著")
        finally:
            cfg.enabled = before

    def bots(self) -> None:
        """伺服器假人（BotRunner＋bot_policy.take_turn，random.Random(7)、時鐘一輪推五分）：同一個資料庫補四個坐在有酒肆的城裡的假人
        （第一個已經坐在酒肆裡：bot_policy.score 問酒肆包「出酒肆」那一顆），bot_policy.TAVERN_CHANCE 換成 0.5（照舊是 bot_policy 的
        模組屬性，_tavern 那一步照舊在 bot_policy），跑 SB_TAVERN_TICKS 輪。整季機器人的 bot.pick 在酒肆的選單上不按 tavern:。
        測試內容沒有酒肆、沒有陣營：略過。"""
        from collections import Counter

        from tianxia import bot, bot_policy, server_bots, tavern
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        if not tavern.on(self.c) or not self.c.scenario.factions:
            emit("這份內容沒有酒肆或陣營：假人那一段略過", None)
            return
        for i, (name, side, loc) in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):  # 開局待選的事件：選掉（不然選單是那一則事件，不是酒肆）
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=31 + i, faction=side, season_number=self.world.get_season_number())
            p.faction, p.location, p.journey = side, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stats["silver"] = 600
            p.picking_tavern = i == 0
            self.chars.save(g.state)
        self.begin()
        first = Game(self.c, self.chars.load(self.BOT_SEATS[0][0]), world=self.world)
        emit("整季機器人在酒肆的選單上挑", bot.pick(first, first.options(odds=False), random.Random(0)))
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(7), clock=lambda: CLOCK[0])
        chance, tick, online = bot_policy.TAVERN_CHANCE, self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {31 + i for i in range(len(self.BOT_SEATS))}
        bot_policy.TAVERN_CHANCE, self.c.config.bot_tick_seconds = 0.5, 10 ** 6  # 在線的假人每一輪都動
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)  # 擺好的四個一直在線（作息照種子，傍晚多半不在）
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_TAVERN_TICKS", "40"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            bot_policy.TAVERN_CHANCE, self.c.config.bot_tick_seconds, server_bots.is_online = chance, tick, online
        states = self.chars.all(bots_only=True)
        emit("酒肆假人 一輪一輪", dict(sorted(totals.items())))
        emit("酒肆假人 紀錄標題", dict(sorted(Counter(e.title for s in states for e in s.journal).items())))
        emit("酒肆假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
        self.hits("假人之後")

    def season(self) -> None:
        """收季：坐在酒肆裡的人照坐（休季也能喝酒、題壁），雇殺手被擋、畫面的 hits.ended；開下一季：酒肆那十個欄位跟著新角色重來、
        季上的酒肆欄位是空的。"""
        self.place("阿飛", "yingchuan")
        self.choose("阿飛", "act:tavern")
        self.do(ADMIN, "end_season")
        self.main("阿飛")
        self.tav("阿飛", "hit", "丁鵬", "0")
        self.tav("阿飛", "wall", "", "收季了，再喝一壺。")
        self.do(ADMIN, "next_season")
        for who in ("葉開", "丁鵬"):
            self.main(who)
            self.me(who, "換季之後")
        s = self.world.get_season()
        emit("換季之後季上的酒肆", {"walls": {k: [w.model_dump() for w in v] for k, v in sorted(s.tavern_walls.items())},
                                   "whispers": {k: [w.model_dump() for w in v] for k, v in sorted(s.tavern_whispers.items())},
                                   "treats": dict(sorted(s.tavern_treats.items())), "hits": [h.model_dump() for h in s.tavern_hits],
                                   "seq": s.tavern_hit_seq, "chatter": dict(sorted(s.tavern_chatter.items()))})


register_track("tavern", TavernScenario, (("tianxia/features/tavern/rules.py", "tianxia/tavern.py"), ("滿堂叫好。", "滿堂叫好！")), "week7")
