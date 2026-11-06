"""same_behavior 一軌一檔：events（這一檔登記 events）。"""
from __future__ import annotations

import contextlib
import hashlib
import os
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, MODEL, STEP, emit, register_track
from sb.tracks.explore import ExploreScenario, _explore_rules

# ═══════════════════════════ core-events：事件檢定一軌（全部拆包第 16 批，dev/core-events-1） ═══════════════════════════
# 事件檢定（端出事件卡、選項的檢定與結果、效果套用、事件裡打一場、隨口應對的三段式）的本體從 engine.py 搬進核心本體
# tianxia/core/event_check.py（計畫 docs/superpowers/plans/2026-11-01-事件檢定進核心.md）。探索那一軌（ExploreScenario）已經走到的：各種地點按探索、事件卡等回答
# （半舊半新）、分級事件經探索抽出來、隨口應對的分岔（假模型、第一種）——這一軌補它沒走到的：檢定成與敗（rules.check_chance 定死）、
# 串接（成了串、敗了串）、付錢的選項、事件裡打一場（贏、輸、大場面判讀）、一次性事件不再出現、走一趟途中的事件、隨口應對（模型擋著退回、
# 假模型成與敗、潤色插回、判成惡行、分岔四條、錢不夠）、第二階事件的那一行、說書的口訣、交友碰上事件、伺服器假人在事件卡上挑、換季。

EVENT_NARRATION = "你照著心裡的盤算行事，旁人看得目瞪口呆。"  # 假模型的潤色（server.answer_event 的 D 段；不寫數字、成敗都是這一句）
EVENT_TEXT = "我上前好言相勸，請他先把話說清楚。"  # 隨口應對寫的那一句（20 字以內）
_EVENT_CLIENTS: dict[type, type] = {}


def _event_client(base: type) -> type:
    """隨口應對的假模型（base 是 _setup_child 那一層換好的 client 類別）：MODEL["event"] 給了（{rate, moral, outcome, narrate}）時，
    評分回 rate、判善惡回 moral、歸類回 outcome（不在清單上回第一種）、潤色回 narrate；其餘照 base（丟連線錯誤、大場面判讀）。"""
    if base not in _EVENT_CLIENTS:
        class EventClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                say = MODEL.get("event")
                fields = getattr(schema, "model_fields", {})
                if say is not None and "outcome" in fields:
                    ids = (fields["outcome"].json_schema_extra or {}).get("enum") or [""]
                    return schema(outcome=say["outcome"] if say.get("outcome") in ids else ids[0], success_rate=say["rate"])
                if say is not None and schema.__name__ == "SuccessRateJudgment":
                    return schema(success_rate=say["rate"])
                if say is not None and schema.__name__ == "MoralJudgment":
                    return schema(moral=say["moral"])
                return super().chat_structured(messages, schema, *a, **k)

            def chat_text(self, messages, *a, **k):
                say = MODEL.get("event")
                if say is not None and say.get("narrate"):
                    return say["narrate"]
                return super().chat_text(messages, *a, **k)

        _EVENT_CLIENTS[base] = EventClient
    return _EVENT_CLIENTS[base]


class EventScenario(ExploreScenario):
    """事件檢定（全部拆包第 16 批；--track events，自己一個資料庫）。小工具借探索那一軌的（draws、fights、tweak、settle、walk、
    kind_places、first_event、edit_state）。事件多半直接擺到眼前（pending_event 寫進存檔，伺服器每次進鎖重讀；選項、檢定、效果、
    串接、打一場、隨口應對都是真的走 /api/choose、/api/answer），端出來那一下（_present）走探索、串接、序章、交友、走一趟。
    正式內容四種設定挑同一批事件（醉漢、乞丐、壇前講道、寒山鐘、逃卒、租債、白馬津押鏢、茶館）；測試內容沒有的（付錢、隨口應對、
    第二階、說書）寫「沒有」略過，同一串 API 照打。
    半舊半新切在 half 之後：五張事件卡等回答（舊程式串出來的、舊程式探索端出來的、有分岔的隨口應對、要打的、沒有分岔的隨口應對），
    後半第一件事（answer）是新程式接著回答。"""

    PLAYERS = {"沈勝衣": None, "白玉京": None, "風四娘": None, "連城璧": None, "柳若松": None, "司馬超群": "guan", "謝曉峰": None,
               "蕭秋雨": None}
    NEWBIE = "孫小紅"  # 不略過引導（不帶、weekend 走草廬；season21、week7 是開局第一分鐘）
    BOT_SEATS = [("事甲", "yingshui"), ("事乙", "julu_altar"), ("事丙", "guangzong"), ("事丁", "market_town")]
    PHASES_FIRST = ["setup", "prologue", "cards", "check", "pay", "fight", "once", "trip", "dead", "half"]
    PHASES_SECOND = ["resume", "answer", "said", "evil", "branches", "tiered", "tale", "social", "bots", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            if MODEL.get("event") is not None:
                client.__class__ = _event_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

    # ── 小工具 ──

    def begin(self) -> None:
        """同酒肆那一軌：每個請求換一份空的勝算記憶（前半＋後半是兩個行程，事件卡上動手那一顆的勝算字才對得上）。"""
        super().begin()
        from tianxia import team

        self.server.ODDS_MEMO = team.OddsMemo()

    def event_of(self, prefer: str, test) -> str | None:
        """正式內容挑 prefer 那一則（合 test 的話），否則照 id 排第一則合 test 的（探索抽得到的優先）；都沒有是 None。"""
        if prefer in self.c.events and test(self.c.events[prefer]):
            return prefer
        return self.first_event(test)

    def card(self, who: str, eid: str | None) -> bool:
        """把這則事件直接擺到他眼前（等回答）：站到事件的地點（沒寫地點的照舊站著），體力補滿。"""
        if eid is None:
            emit(f"{who}：這份內容沒有合適的事件", None)
            return False
        event = self.c.events[eid]
        if not self.place(who, event.locations[0] if event.locations else None):
            return False
        self.edit_state(who, lambda s: setattr(s, "pending_event", eid))
        return True

    def press(self, who: str, test, tag: str) -> bool:
        """眼前那一則照內容的順序，第一顆合 test、選單上有而且按得下去的按下去；沒有就寫下選單上有哪幾顆。"""
        state = self.chars.load(who)
        eid = state.pending_event if state is not None else None
        opts = self.options(who)
        if eid is None:
            emit(f"{who} {tag}：眼前沒有事件", None)
            return False
        for i, ch in enumerate(self.c.events[eid].choices):
            oid = f"choice:{i}"
            if test(ch) and opts.get(oid, {}).get("enabled"):
                self.choose(who, oid)
                return True
        emit(f"{who} {tag}：沒有合的那一顆", sorted(opts))
        return False

    def say(self, who: str, text: str = EVENT_TEXT):
        """隨口應對（/api/answer：server.answer_event 的 A、B、C 段，擲完骰有潤色的再 D、E 段）。"""
        return self.call(who, "POST", "/api/answer", {"text": text})

    def seek(self, who: str) -> None:
        """按一下探索：探索一顆開著就是出門一趟；三選一的季（weekend）按「找事件」那一顆；舊探索照它自己擲。"""
        self.choose(who, "act:explore")
        modes = [i for i, o in self.options(who).items() if i.startswith("explore:") and o.get("enabled")]
        if modes:
            self.choose(who, "explore:seek" if "explore:seek" in modes else modes[0])

    @contextlib.contextmanager
    def odds(self, value: float):
        """這幾下事件檢定的成功率定死（rules.check_chance 換成 value：roll_check 照樣用掉 Game.rng 那一顆骰，比的門檻換掉；
        選項上寫的心裡話照 check_gap，不動）。"""
        from tianxia import rules

        real = rules.check_chance
        rules.check_chance = lambda *a, **k: value
        try:
            yield
        finally:
            rules.check_chance = real

    @contextlib.contextmanager
    def model(self, **say):
        """這幾下的隨口應對換成假模型（_event_client）：預設 70 分、判「中」、歸類回第一種、潤色回 EVENT_NARRATION。"""
        MODEL["event"] = {"rate": 70, "moral": "中", "outcome": None, "narrate": EVENT_NARRATION, **say}
        try:
            yield
        finally:
            MODEL["event"] = None

    @contextlib.contextmanager
    def judged(self):
        """大場面判讀（同出陣那一軌的 judge）：難度門檻調低、模型換成回固定判讀的。"""
        self.c.config.big_fight_difficulty = 1
        MODEL["judge"] = True
        try:
            yield
        finally:
            MODEL["judge"] = False
            self.c.config.big_fight_difficulty = self.big_default

    def me(self, who: str, tag: str) -> None:
        """存檔裡事件檢定碰得到的那幾格：眼前的事件、看過的事件、體力、數值、旗標、戰報幾份、文字的事那一本的帳、最新三則紀錄的標題、
        最後三則行狀。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "pending": state.pending_event, "seen": sorted(p.seen_events), "stamina": p.stamina, "stats": dict(sorted(p.stats.items())),
            "flags": sorted(p.flags), "battles": len(state.battles), "deed": [p.deed_day, p.deed_today],
            "journal": [e.title for e in state.journal[:3]], "annals": [a.text for a in p.annals[-3:]]})

    def plain_free(self) -> str | None:
        return self.event_of("jz_gz_deserter", lambda e: e.free_text is not None and not e.free_text.outcomes
                             and not e.free_text.outcomes_only)

    def branch_free(self) -> str | None:
        return self.event_of("jz_hz_rentdebt", lambda e: e.free_text is not None and len({o.kind for o in e.free_text.outcomes}) >= 3)

    def checked(self) -> str | None:
        return self.event_of("drunk_token", lambda e: any(ch.check and not ch.combat for ch in e.choices) and bool(e.actions))

    def combat(self) -> str | None:
        return self.event_of("jizhou_altar_sermon", lambda e: any(ch.combat for ch in e.choices) and bool(e.actions))

    @staticmethod
    def paid(ch) -> bool:
        return bool(ch.condition.min_stats.get("silver")) and ch.effect.stats.get("silver", 0) < 0 and ch.check is None and ch.combat is None

    # ── 前半 ──

    def setup(self) -> None:
        Scenario.setup(self)
        if self.c.scenario.factions:
            self.place("司馬超群", None, faction="guan")  # 分岔成了要記貢獻（_deed_credit：散人不記）

    def prologue(self) -> None:
        """序章的草廬（不帶、weekend 才有）：開頭兩則事件選第一個（序章的 _apply 把「你悟得了…」那一句藏起來）、草廬四景
        （舊探索端出的事件，_present）選掉；season21、week7 是開局第一分鐘的事件卡（settle_choices 選掉）。"""
        who = self.NEWBIE
        view = self.main(who)
        if not view.get("prologue"):
            emit("這一季沒有序章", None)
            self.settle_choices(who)
        else:
            self.choose(who, "choice:0")
            self.choose(who, "choice:0")
            self.do(who, "view_tab", {"tab": "practice"})
            self.choose(who, "act:explore")
            self.settle(who)
        self.me(who, "序章之後")

    def cards(self) -> None:
        """探索一顆碰到事件卡（各種地點：城、寺、渡、野、山、營，各抽一次事件）：端出來那一下的選單、事件卡的樣子（event_opts）、
        隨口應對的提示語、分級的那一行（/api/main）；照第一顆選掉。舊探索與三選一照它自己擲（找事件那一顆）。"""
        explore_one = _explore_rules()

        names = ["沈勝衣", "白玉京", "風四娘", "連城璧", "柳若松", "謝曉峰"]
        for i, (kind, loc) in enumerate(self.kind_places()):
            who = names[i % len(names)]
            if not self.place(who, loc):
                continue
            with self.draws(explore_one.EVENT):
                self.seek(who)
            self.me(who, f"{kind} {loc} 端出來的")
            self.settle(who)
            self.me(who, f"{kind} {loc} 選完")

    def check(self) -> None:
        """要檢定的選項：成（rules.check_chance 定成 1）、敗（定成 0）各一次；成了串到下一則（effect.next_event：_apply 端出來）、
        敗了串到下一則（fail_effect.next_event）也各一次（醉漢那一則兩條都有）。"""
        ev = self.checked()
        emit("要檢定的事件", ev)
        alone = lambda ch: ch.check is not None and ch.combat is None and not ch.effect.next_event and not ch.fail_effect.next_event  # noqa: E731
        for who, value, tag in (("沈勝衣", 1.0, "成"), ("白玉京", 0.0, "敗")):
            if self.card(who, ev):
                with self.odds(value):
                    self.press(who, alone, f"檢定{tag}")
                self.me(who, f"檢定{tag}之後")
        for who, value, test, tag in (("風四娘", 1.0, lambda ch: ch.check is not None and bool(ch.effect.next_event), "成了串下去"),
                                      ("連城璧", 0.0, lambda ch: ch.check is not None and bool(ch.fail_effect.next_event), "敗了串下去")):
            if self.card(who, ev):
                with self.odds(value):
                    self.press(who, test, tag)
                self.me(who, tag)
                self.settle(who)

    def pay(self) -> None:
        """付錢的選項（condition.min_stats.silver＝價錢、effect 扣銀兩）：錢剛好夠，那一顆在、按下去扣錢；少一兩，那幾顆不在選單上，
        只按得到不花錢的。"""
        ev = self.event_of("beggar", lambda e: any(self.paid(ch) for ch in e.choices) and bool(e.actions))
        emit("付錢的事件", ev)
        if ev is None:
            return
        price = next(ch.condition.min_stats["silver"] for ch in self.c.events[ev].choices if self.paid(ch))
        for who, silver in (("謝曉峰", price), ("蕭秋雨", price - 1)):
            if self.card(who, ev):
                self.edit(who, lambda p, silver=silver: p.stats.__setitem__("silver", silver))
                if not self.press(who, self.paid, f"付錢（身上 {silver} 兩）"):
                    self.press(who, lambda ch: ch.check is None and ch.combat is None, "錢不夠，按不花錢的那一顆")
                self.me(who, f"付錢之後（原本 {silver} 兩）")

    def fight(self) -> None:
        """事件裡打一場（固定選項的 combat：_event_battle）：打贏、打輸各一次（team.fight 照 tier）；再一次大場面判讀（server.may_judge_fight
        認 choice:N → prepare_fight → 鎖內 _judged 用掉、_narrate 照勝負挑一版）。第三場照真的打（不定結果），那一位身法擺到 60
        （閃避的機會夾成 1，打完擺回 5）：劇情戰不閃（dodge=False；定了結果的那兩場 team.fight 在閃避之前就回了，看不出來），
        閃了的話落敗一定變僵持。"""
        ev = self.combat()
        emit("打一場的事件", ev)
        hit = lambda ch: ch.combat is not None  # noqa: E731
        self.edit("蕭秋雨", lambda p: p.stats.__setitem__("agi", 60))
        for who, tier in (("白玉京", "大勝"), ("風四娘", "落敗"), ("蕭秋雨", None)):
            if self.card(who, ev):
                with self.fights(tier):
                    self.press(who, hit, f"事件裡打一場（{tier or '照真的打'}）")
                self.me(who, f"打一場之後（{tier or '照真的打'}）")
        self.edit("蕭秋雨", lambda p: p.stats.__setitem__("agi", 5))
        with self.judged():
            if self.card("連城璧", ev):
                with self.fights("大勝"):
                    self.press("連城璧", hit, "大場面判讀")
                self.me("連城璧", "大場面之後")

    def once(self) -> None:
        """一次性事件（Event.once）：一次性奇遇必中（rare_explore_chance 換成 1）站在它的地點出門兩趟——第一趟端出來、選掉
        （_present 記進 seen_events、效果帶 once 推大勢），第二趟它不再出現（pick_event 跳過看過的一次性事件）。"""
        explore_one = _explore_rules()

        ev = self.event_of("hanshan_bell", lambda e: e.once and "explore" in e.actions and bool(e.locations))
        emit("一次性事件", ev)
        if ev is None:
            return
        for k in range(2):
            if not self.place("蕭秋雨", self.c.events[ev].locations[0]):
                return
            with self.draws(explore_one.EVENT), self.tweak(self.c.config, rare_explore_chance=1.0):
                self.seek("蕭秋雨")
            self.me("蕭秋雨", f"一次性事件那一處第 {k + 1} 趟")
            self.settle("蕭秋雨")
        emit("一次性事件看過了", ev in self.chars.load("蕭秋雨").player.seen_events)

    def trip(self) -> None:
        """走一趟途中的事件（探索一顆開著的季）：三段，第二段停在事件上（waiting），檢定定成 1、選掉，接著走完；關著的季回「此刻無法」。"""
        explore_one = _explore_rules()

        if not self.place("沈勝衣", "yingshui"):
            return
        with self.draws(explore_one.MATERIAL, explore_one.EVENT, explore_one.MATERIAL), self.odds(1.0):
            self.walk("沈勝衣", 3)
        self.me("沈勝衣", "走一趟之後")

    def dead(self) -> None:
        """隨口應對、模型擋著（DeadClient：評分、歸類、判善惡、潤色全丟連線錯誤）：沒有分岔的那一則退回 40、照屬性修正擲；有分岔的
        （分岔開著的季）退回最後一種、必成，關著的季照舊用 stat 擲。被擋下來的：寫太長（21 字）、眼前沒有事件、這一則沒有隨口應對。"""
        plain, branch = self.plain_free(), self.branch_free()
        emit("隨口應對的事件", {"plain": plain, "branch": branch})
        for who, ev in (("謝曉峰", plain), ("蕭秋雨", branch)):
            if self.card(who, ev):
                self.say(who, "一" * 21)
                self.say(who)
                self.me(who, "隨口應對（模型擋著）之後")
        self.edit_state("沈勝衣", lambda s: setattr(s, "pending_event", None))
        self.say("沈勝衣")
        if self.card("沈勝衣", self.event_of("beggar", lambda e: e.free_text is None)):
            self.say("沈勝衣")
            self.settle("沈勝衣")

    def half(self) -> None:
        """前半的最後一段（半舊半新的切點）：五張事件卡等回答——白玉京是舊程式串出來的（要檢定的那一顆成了、effect.next_event 由 _apply
        端出來；測試內容沒有的話擺不必檢定的串接）、柳若松是舊程式出門一趟抽到事件端出來的（_present）、風四娘有分岔的隨口應對、
        連城璧要打一場、謝曉峰沒有分岔的隨口應對（後三張直接擺上）。"""
        explore_one = _explore_rules()

        chain = self.event_of("drunk_token", lambda e: any(ch.check is not None and ch.effect.next_event for ch in e.choices)) or \
            self.first_event(lambda e: any(ch.effect.next_event for ch in e.choices))
        if self.card("白玉京", chain):
            with self.odds(1.0):
                self.press("白玉京", lambda ch: bool(ch.effect.next_event), "串出下一則")
        ev = self.combat()
        if self.place("柳若松", self.c.events[ev].locations[0] if ev and self.c.events[ev].locations else None):
            with self.draws(explore_one.EVENT):
                self.seek("柳若松")
        self.card("風四娘", self.branch_free())
        self.card("連城璧", self.combat())
        self.card("謝曉峰", self.plain_free())
        for who in ("白玉京", "柳若松", "風四娘", "連城璧", "謝曉峰"):
            self.me(who, "等回答")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def answer(self) -> None:
        """新程式接手前半留下的五張卡：串出來的那一則照第一顆選（檢定定成 0：敗）、探索端出來的照第一顆選、有分岔的那一則寫一句
        （假模型歸到掏錢那一種、身上錢夠）、要打的那一則打一場大場面（判讀、打贏）、沒有分岔的那一則寫一句（假模型 100 分、潤色）。"""
        with self.odds(0.0):
            self.settle("白玉京")
        self.me("白玉京", "新程式選完串出來的")
        self.settle("柳若松")
        self.me("柳若松", "新程式選完探索端出來的")
        self.edit("風四娘", lambda p: p.stats.__setitem__("silver", 40))
        branch = self.branch_free()
        cost = next((o.id for o in self.c.events[branch].free_text.outcomes if o.kind == "cost"), None) if branch else None
        with self.model(rate=70, outcome=cost):
            self.say("風四娘")
        self.me("風四娘", "新程式回答分岔")
        with self.judged(), self.fights("大勝"):
            self.press("連城璧", lambda ch: ch.combat is not None, "新程式打那一場")
        self.me("連城璧", "新程式打完")
        with self.model(rate=100):
            self.say("謝曉峰")
        self.me("謝曉峰", "新程式回答隨口應對")

    def said(self) -> None:
        """沒有分岔的隨口應對（假模型）：100 分（夾成 85）、0 分（夾成 5），潤色接在「你：「…」」後面；潤色把結果句整句寫進去了
        （FB-124：潤色＝固定的那一句＋成功的結果句）就拿掉引擎那一行。"""
        plain = self.plain_free()
        if plain is None:
            emit("這份內容沒有隨口應對", None)
            return
        told = EVENT_NARRATION + self.c.events[plain].free_text.effect.text
        for who, rate, narrate in (("沈勝衣", 100, EVENT_NARRATION), ("白玉京", 0, EVENT_NARRATION), ("柳若松", 100, told)):
            if self.card(who, plain):
                with self.model(rate=rate, narrate=narrate):
                    self.say(who)
                self.me(who, f"隨口應對 {rate} 分之後")

    def evil(self) -> None:
        """判成惡行而且擲中了（FB-223）：沒有分岔的那一則，假模型 100 分、判「惡」——成功效果換成惡行的版本、行狀寫「行了一件惡事」、
        潤色照惡行寫、換掉 EVIL_DONE 那一句；有分岔的那一則歸到最後一種（走開）、判「惡」（分岔關著的季照舊用 stat 擲）。"""
        from tianxia import event_llm

        plain, branch = self.plain_free(), self.branch_free()
        leave = self.c.events[branch].free_text.outcomes[-1].id if branch else None
        for who, ev, outcome in (("連城璧", plain, None), ("蕭秋雨", branch, leave)):
            if self.card(who, ev):
                with self.model(rate=100, moral=event_llm.MORAL_EVIL, outcome=outcome):
                    self.say(who)
                self.me(who, "判成惡行之後")

    def branches(self) -> None:
        """隨口應對的分岔四條（分岔開著的季；關著照舊用 stat 擲）：司馬超群（官軍：成了記貢獻 _deed_credit）——掏錢那一種身上錢不夠
        （回 NOT_ENOUGH_SILVER、事件還停著）、錢夠（必成）；檢定那一種 100 分、0 分；打仗那一種打贏、打輸。"""
        branch = self.branch_free()
        emit("分岔的事件", branch)
        if branch is None:
            return
        kinds = {}
        for o in self.c.events[branch].free_text.outcomes:
            kinds.setdefault(o.kind, o.id)
        who = "司馬超群"
        for silver in (0, 40):
            if self.card(who, branch):
                self.edit(who, lambda p, silver=silver: p.stats.__setitem__("silver", silver))
                with self.model(rate=70, outcome=kinds.get("cost")):
                    self.say(who)
                self.me(who, f"掏錢那一種（身上 {silver} 兩）")
        for rate in (100, 0):
            if self.card(who, branch):
                with self.model(rate=rate, outcome=kinds.get("check")):
                    self.say(who)
                self.me(who, f"檢定那一種（{rate} 分）")
        for tier in ("大勝", "落敗"):
            if self.card(who, branch):
                with self.model(rate=70, outcome=kinds.get("combat")), self.fights(tier):
                    self.say(who)
                self.me(who, f"打仗那一種（{tier}）")

    def tiered(self) -> None:
        """第二階事件（州郡大事）擺到眼前：/api/main 的 event_tier 寫那一行與框色；要檢定的那一顆成（check 的 tier 是 2：不吃減法季的放寬）。"""
        ev = self.event_of("t2_baima_escort", lambda e: e.tier == 2)
        emit("第二階事件", ev)
        if self.card("連城璧", ev):
            with self.odds(1.0):
                self.press("連城璧", lambda ch: ch.check is not None, "第二階的檢定")
            self.me("連城璧", "第二階之後")

    def tale(self) -> None:
        """說書的事件了結時多一句口訣（_tale_clue：Config.secrets.tale_chance、鑄器那一句 Config.forge_secrets.tale_chance 都換成 1，
        擲的是自己的雜湊、不動 Game.rng）。"""
        tales = [e for e in self.c.config.secrets.tale_events if e in self.c.events]
        ev = next((e for e in tales if any(ch.check for ch in self.c.events[e].choices)), tales[0] if tales else None)
        emit("說書的事件", ev)
        if self.card("風四娘", ev):
            with self.tweak(self.c.config.secrets, tale_chance=1.0), self.tweak(self.c.config.forge_secrets, tale_chance=1.0), \
                    self.odds(1.0):
                self.press("風四娘", lambda ch: ch.combat is None and not ch.condition.min_stats, "說書")
            self.me("風四娘", "說書之後")

    def social(self) -> None:
        """交友（舊的 _encounter 沒碰上人物、一類一顆的「一次性」「結識」那兩種 → _present(事件, "socialize")）：在四處按交友，
        端出事件就選掉、開了對話就告辭；按不了的寫下來（一類一顆的季，這裡沒有能說上話的人是灰的）。"""
        for who, loc in (("謝曉峰", "yingchuan"), ("蕭秋雨", "market_town"), ("沈勝衣", "zhuo_county"), ("白玉京", "wan_city"),
                         ("柳若松", "yingshui")):
            if not self.place(who, loc):
                continue
            if not self.options(who).get("act:socialize", {}).get("enabled"):
                emit(f"{who} 在 {loc} 按不了交友", None)
                continue
            self.choose(who, "act:socialize")
            for _ in range(4):
                opts = self.options(who)
                if "talk:leave" in opts:
                    self.choose(who, "talk:leave")
                elif any(i.startswith("choice:") for i in opts):
                    self.settle(who)
                else:
                    break
            self.me(who, f"{loc} 交友之後")

    def bots(self) -> None:
        """伺服器假人（BotRunner＋bot_policy.take_turn，random.Random(11)、時鐘一輪推五分）：同一個資料庫補四個假人，眼前各擺一張
        事件卡（要檢定的、付錢的、要打的、有隨口應對的：假人照 bot_policy.score 的 choice 那一段挑、不寫字），站在事件多的地點，
        跑 SB_EVENT_TICKS 輪（探索端出來的事件也一樣選）。整季機器人的 bot.pick 在事件卡上挑哪一顆也寫下來。"""
        from collections import Counter

        from tianxia import bot, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        paid = self.event_of("beggar", lambda e: any(self.paid(ch) for ch in e.choices) and bool(e.actions))
        cards = [self.checked(), paid, self.combat(), self.plain_free()]
        sides = [f.id for f in self.c.scenario.factions]
        spare = sorted(self.c.locations)
        names = [name for name, _ in self.BOT_SEATS]
        for i, (name, loc) in enumerate(self.BOT_SEATS):
            loc = loc if loc in self.c.locations else spare[i % len(spare)]
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):  # 開局待選的事件：選掉
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p = g.state.player
            side = sides[i % len(sides)] if sides else None
            p.bot = BotProfile(personality="普通", seed=41 + i, faction=side, season_number=self.world.get_season_number())
            p.faction, p.location, p.journey = side, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stats["silver"] = 200
            g.state.pending_event = cards[i]
            self.chars.save(g.state)
        self.begin()
        first = Game(self.c, self.chars.load(names[0]), world=self.world)
        emit("整季機器人在事件卡上挑", bot.pick(first, first.options(odds=False), random.Random(0)))
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(11), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {41 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6  # 在線的假人每一輪都動
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)  # 擺好的四個一直在線
        totals = Counter()
        try:
            for n in range(int(os.environ.get("SB_EVENT_TICKS", "40"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
                if n == 0:  # 第一輪之後就寫：四十輪跑完，第一輪那一則早被擠出江湖紀錄（只留 30 則），卡直接寫進存檔、不在看過的事件裡
                    emit("事件假人 第一輪答了眼前的卡", self.answered(names, cards))
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        states = self.chars.all(bots_only=True)
        emit("事件假人 一輪一輪", dict(sorted(totals.items())))
        emit("事件假人 紀錄標題", dict(sorted(Counter(e.title for s in states for e in s.journal).items())))
        emit("事件假人 看過的事件", {s.player.name: sorted(s.player.seen_events) for s in states})
        emit("事件假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})

    def answered(self, names: list[str], cards: list[str | None]) -> dict:
        """擺好的那幾個假人眼前那一張卡答了沒（dev/core-events-1 審查：輸出本身看不出四個假人答了卡）：卡還在不在眼前、
        江湖紀錄裡那一則事件的標題（「狼頭鐵牌・扶他起身，順手摸走鐵牌」：事件名・選了哪一顆）。只讀存檔。"""
        out = {}
        for name, card in zip(names, cards):
            s = self.chars.load(name)
            title = self.c.events[card].title if card in self.c.events else str(card)
            out[name] = {"卡": card, "還在眼前": s.pending_event == card,
                         "紀錄": [e.title for e in s.journal if e.title == title or e.title.startswith(title + "・")]}
        return out

    def season(self) -> None:
        """收季、開下一季：眼前擺著一張事件卡的人（休季時選單只剩休季那一顆、隨口應對被擋；開下一季之後那一張照換季的規矩）。"""
        self.card("沈勝衣", self.checked())
        self.do(ADMIN, "end_season")
        self.main("沈勝衣")
        self.say("沈勝衣")
        self.do(ADMIN, "next_season")
        self.main("沈勝衣")
        self.me("沈勝衣", "換季之後")


# 改一個字（selftest）：事件選項按下去那一行（_choose；搬之前在 engine.py、之後在 tianxia/core/event_check.py）
register_track("events", EventScenario, (("tianxia/core/event_check.py", "tianxia/engine.py"),
                                          ('msgs = [f"▸ {choice.text}"]', 'msgs = [f"▸ {choice.text}！"]')), "week7")
