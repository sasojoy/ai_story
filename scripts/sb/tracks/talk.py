"""same_behavior 一軌一檔：talk（這一檔登記 talk）。"""
from __future__ import annotations

import contextlib
from pathlib import Path

from sb.harness import ADMIN, MODEL, emit, register_track
from sb.tracks.companions import CompanionsScenario, GameStateHolder

# ═══════════════════════════ talk：人物對話二軌（全部拆包第 20 批，dev/companions-2） ═══════════════════════════
# 人物對話（鎖外三段式 A、B、C：dialogue_request／prepare_dialogue／choose 的重驗）、NPC 智能 2.0（開口求人、開條件、先做後付與食言、
# 他主動開口求你、帶路、陪你出陣與商量打法）的本體從 engine.py 與 tianxia/companion_agent.py、parley.py 搬進 tianxia/features/companions/
# （舊名留成別名；計畫 docs/superpowers/plans/2026-11-04-人物情誼包-第2批.md）。這一段整塊是這一批的：接在檔尾、最後一行登記
# （register_track），PM 合的時候不跟別人的行穿插。角色的名字都是原創的（第 22 批 PM 認定第 3 條）。

TALK_REPLY = "他沉吟了一會，緩緩開口。"
TALK_TERMS = "他想了想：「這事不難，只是你得先拿出一點誠意。」"
TALK_NO = "他搖了搖頭：「這件事，恕我難以從命。」"
TALK_PLAN_NO = "他皺起眉頭：「這個打法行不通。」"
_TALK_CLIENTS: dict[type, type] = {}


def _talk_block(text: str, head: str) -> list[tuple[str, int]]:
    """提示裡「【…head】」底下的一串「- id：說明（份量 N）」→ [(id, 份量)]。"""
    i = text.find(head)
    if i < 0:
        return []
    rows = []
    for line in text[i + len(head):].split("\n")[1:]:
        if not line.startswith("- "):
            break
        ident, _, rest = line[2:].partition("：")
        weight = rest.rsplit("份量 ", 1)[-1].rstrip("）") if "份量" in rest else "0"
        rows.append((ident, int(weight) if weight.isdigit() else 0))
    return rows


def _talk_pick(spec: str, rows: list[tuple[str, int]]) -> str:
    """MODEL["parley"] 裡的 id：寫 'escort:*' 這種星號結尾的取清單上第一個對得上的，其餘照字面（寫清單外的 id 也是一種測法）。"""
    if spec.endswith("*"):
        return next((ident for ident, _ in rows if ident.startswith(spec[:-1])), "")
    return spec


def _talk_client(base: type) -> type:
    """人物對話二軌的假模型（疊在 _companions_client 上）：MODEL["parley"] 給了（{ask、willing、condition、narrative_terms、narrative_no、want、reward…}）
    時，那一輪 CompanionTurn 的 NPC 智能 2.0 欄位換成它；ask、condition、want 的 id 可以寫 'escort:*' 這種星號結尾（照提示裡的清單取第一個）。"""
    if base not in _TALK_CLIENTS:
        class TalkClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                got = super().chat_structured(messages, schema, *a, **k)
                spec = MODEL.get("parley")
                if spec is None or not hasattr(got, "ask"):
                    return got
                text = messages[-1]["content"]
                asks, conds = _talk_block(text, "此刻做得到的事】"), _talk_block(text, "可以開的條件】")
                wants, rewards = _talk_block(text, "想請玩家做的事】"), _talk_block(text, "可以回報的事】")
                update: dict = {}
                for key, value in spec.items():
                    if key == "ask":
                        update[key] = _talk_pick(value, asks)
                    elif key == "condition":
                        update[key] = _talk_pick(value, conds)
                    elif key == "want":
                        update[key] = _talk_pick(value, wants)
                    elif key == "reward":  # 'fit'：第一個份量不比請託大的回報
                        weight = dict(wants).get(update.get("want", ""), 0)
                        update[key] = next((ident for ident, w in rewards if w <= weight), "") if value == "fit" else value
                    else:
                        update[key] = value
                return got.model_copy(update=update)

        _TALK_CLIENTS[base] = TalkClient
    return _TALK_CLIENTS[base]


class TalkScenario(CompanionsScenario):
    """人物對話（全部拆包第 20 批；--track talk，自己一個資料庫）。
    沈鶴年在談盧植（直接擺成上一輪給了選項）：選選項、自己說，**前半停在還在談**。顧映雪模型叫不動：選選項、自己說都結束對話（「無心多談」）。
    葉知秋求見（call:）開口兩種（模型回了、模型叫不動退回體力），交友（act:socialize）一次（在只有秦頡一位的宛城：盧植營兩位以上、交友是名單，不開口）。
    言半山求「指點一招」、模型開條件（交銀）：**前半停在條件還沒答覆**（接、不接兩顆）。後半：接了（交銀、當場做）。
    紀行雲：照擲出來的結果一件一件求（指點、說說敵情、贈物當場做；婉拒；開條件不接；開條件接了打探掛成委託；欠他的那一件請他兌現）。
    燕回聲求贈物、先做後付（模型開條件、擲中）：**前半停在約定還欠著**；後半還他。霍斷橋同一件，後半過了期限（食言：情誼扣、那幾句併進書信）。
    路修遠求帶路（動身，一路不花體力）：**前半停在帶路的路上**；後半每到一站跟他說一句（parley:road）。衛承光求陪你出陣：**前半停在答應了**；
    後半商量打法（talk:plan）、在盧植那一帶（冀州）出陣。葉聽雪交友焦慮的秦頡（他主動開口求你）：**前半停在他開的請託還沒答覆**；後半接下，再去黃巾的投靠點叛投（欠著的都算食言）。冷千山是黃巾，求官軍的盧植（敵對）。
    假人（BotRunner 十輪；bot_policy.score 問 talk:、parley: 的各幾顆）；換季。這份內容沒有盧植的設定用第一位人物，同一串 API 照打。"""

    TALKER, BLOCKED, OPENER, ASKER, DOER = "沈鶴年", "顧映雪", "葉知秋", "言半山", "紀行雲"
    PAYER, LATE, WALKER, BACKER, PLEADER, FOE = "燕回聲", "霍斷橋", "路修遠", "衛承光", "葉聽雪", "冷千山"
    BACKER2 = "宗政遠"
    PLAYERS = {TALKER: "guan", BLOCKED: "guan", OPENER: "guan", ASKER: "guan", DOER: "guan", PAYER: "guan", LATE: "guan", WALKER: "guan",
               BACKER: "guan", BACKER2: "guan", PLEADER: "guan", FOE: "huang"}
    PLEAD_FIG = "qinjie"
    PHASES_FIRST = ["setup", "seat", "opening", "plain", "terms_open", "owe_open", "road_open", "backing_open", "plea_open", "half"]
    PHASES_SECOND = ["resume", "plain_on", "terms_on", "doer", "owe_on", "road_on", "backing_on", "plea_on", "forsake", "foe", "bots", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # 上一層（人物情誼一軌的假模型）換好的那一層

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            client.__class__ = _talk_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

    # ── 小工具 ──

    @property
    def fig(self) -> str | None:
        if self.LUZHI in self.c.characters:
            return self.LUZHI
        return sorted(self.c.characters)[0] if self.c.characters else None

    @contextlib.contextmanager
    def parley_on(self, **values):
        """NPC 智能 2.0 開著（正式內容本來就開；測試內容關著，這一下打開）、一天最多求九件、一天最多聊九輪，再加這幾個值（擲骰的 floor 等）。"""
        parley = self.c.config.parley
        with self.tuned(parley, enabled=True, asks_per_day=9, **values), self.tuned(self.c.config, talk_turns_per_day=9):
            yield

    def stand(self, who: str, cid: str | None = None) -> None:
        cid = cid or self.fig
        try:
            self.beside(who, cid)
        except Exception as e:  # noqa: BLE001  （測試內容的人物沒有住處）
            emit(f"{who} 站不到 {cid}", type(e).__name__)
            self.place(who, None)

    def talking(self, who: str, cid: str | None = None, affinity: int = 45) -> None:
        """直接擺成「正在跟他談、上一輪給了選項」（tests/kit/stances_kit.talking 同一個擺法），今天談過的輪數清掉。"""
        cid = cid or self.fig

        def fn(p) -> None:
            p.pending_companion = cid
            p.last_offered_dialogue[cid] = [["勸他速攻", "勸他持重", "告辭"], ["真誠請教", "坦誠相待", "尋常寒暄"]]
            p.affinities[cid] = affinity
            p.talks_today.pop(cid, None)

        self.edit(who, fn)

    def open_call(self, who: str, cid: str | None = None) -> None:
        """求見：站到他那裡、名望夠、打開求見的名單、按他的名字。"""
        cid = cid or self.fig
        self.stand(who, cid)

        def fn(p) -> None:
            p.stats["fame"] = 9999
            p.picking_audience = True

        self.edit(who, fn)
        self.choose(who, f"call:{cid}")

    def open_social(self, who: str, cid: str) -> None:
        """交友（act:socialize）：站到他那裡、按交友。只有他一位的地點才直接開口（兩位以上的地點交友是名單，按的是 call:，那一條走 open_call）。"""
        self.stand(who, cid)
        self.edit(who, lambda p: p.stats.update({"fame": 9999}))  # 名望夠才見得到（同 open_call）
        emit("交友那一顆", self.buttons(who, "act:socialize"))
        view = self.choose(who, "act:socialize")
        if any(i.startswith("choice:") for i in self.ids(view)):  # 先碰上一件留在交友的事（福緣之類）：了結它，再按一次
            self.settle_choices(who)
            self.choose(who, "act:socialize")

    def you(self, who: str, tag: str) -> None:
        """存檔裡對話與 NPC 智能 2.0 碰得到的格子：談話對象與上一輪的選項、情誼、今天聊了幾輪、開的條件、欠的、欠你的、今天求了什麼、守約紀錄、陪你出陣、
        帶路的路、體力銀兩心得、書信、行狀與最新兩則紀錄、對話記錄的尾巴。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "pending": p.pending_companion, "offered": p.last_offered_dialogue, "affinities": dict(sorted(p.affinities.items())),
            "talks_today": dict(sorted(p.talks_today.items())), "terms": {k: v.model_dump(mode="json") for k, v in sorted(p.parley_terms.items())},
            "debts": {k: v.model_dump(mode="json") for k, v in sorted(p.parley_debts.items())}, "owed": dict(sorted(p.parley_owed.items())),
            "days": {k: v.model_dump(mode="json") for k, v in sorted(p.parley_days.items())},
            "records": {k: v.model_dump(mode="json") for k, v in sorted(p.parley_records.items())},
            "backing": p.parley_backing.model_dump(mode="json") if p.parley_backing is not None else None,
            "escort": [p.parley_escort, p.parley_road_leg], "journey": p.journey.model_dump(mode="json") if p.journey is not None else None,
            "location": p.location, "stamina": p.stamina, "silver": p.stats.get("silver", 0), "xinde": p.stats.get("xinde", 0),
            "materials": dict(sorted(p.materials.items())) if hasattr(p, "materials") else None,
            "letters": [x.model_dump(mode="json") for x in p.letters], "annals": [[a.kind, a.text, a.figure] for a in p.annals],
            "journal": [[e.title, e.tag, list(e.lines)] for e in state.journal[:2]],
            "memos": {k: v.model_dump(mode="json") for k, v in sorted(p.talk_memos.items())},
            "history": {k: v[-2:] for k, v in sorted(p.dialogue_history.items())}, "stance_notes": {k: v.model_dump(mode="json") for k, v in sorted(p.stance_notes.items())}})

    def say(self, who: str, text: str, option: str = "talk:say") -> None:
        self.call(who, "POST", "/api/say", {"text": text, "option": option})

    def ask(self, who: str, text: str, tag: str, spec: dict | None, option: str = "talk:say", **tuning) -> None:
        """說一句話，模型的 NPC 智能 2.0 欄位是 spec（None 就是閒聊）；tuning 是這一下擲骰的設定（floor=100 一定中、floor=0 且 willing 0 一定不中）。"""
        MODEL["talk"], MODEL["parley"] = {"stance": "suzhan"}, spec
        try:
            with self.parley_on(**tuning):
                self.say(who, text, option)
        finally:
            MODEL["talk"] = MODEL["parley"] = None
        self.you(who, tag)

    # ── 前半 ──

    def opening(self) -> None:
        """求見開口兩種、交友一次：模型回了（對話開始、選項三顆）、模型叫不動（退回體力、「無心多談」）。"""
        cid = self.fig
        if cid is None:
            emit("這份內容沒有人物", None)
            return
        MODEL["talk"] = None
        self.open_call(self.BLOCKED, cid)
        self.you(self.BLOCKED, "求見、模型叫不動")
        MODEL["talk"] = {"stance": "suzhan"}
        self.open_call(self.OPENER, cid)
        self.you(self.OPENER, "求見、模型回了")
        emit("談話的選單", sorted(self.ids(self.main(self.OPENER))))
        self.choose(self.OPENER, "talk:leave")
        self.edit(self.OPENER, lambda p: setattr(p, "talks_today", {}))
        alone = self.PLEAD_FIG if self.PLEAD_FIG in self.c.characters else cid  # 宛城只有秦頡一位：交友直接開口（盧植營兩位以上、是求見名單）
        self.open_social(self.OPENER, alone)
        self.you(self.OPENER, "交友")
        self.choose(self.OPENER, "talk:leave")
        MODEL["talk"] = None

    def plain(self) -> None:
        """沈鶴年選選項、自己說（前半停在還在談）；顧映雪模型叫不動：選選項、自己說都結束對話。"""
        cid = self.fig
        if cid is None:
            return
        self.stand(self.TALKER, cid)
        self.talking(self.TALKER, cid)
        MODEL["talk"] = {"stance": "suzhan"}
        view = self.main(self.TALKER)
        emit("談話中的人物頁（main.figure）與選單", [view.get("figure") if isinstance(view, dict) else None, sorted(self.ids(view))])
        with self.tuned(self.c.config, talk_turns_per_day=9):
            self.choose(self.TALKER, "talk:0")
            self.you(self.TALKER, "選了第一顆")
            self.say(self.TALKER, "願聞其詳")
        self.you(self.TALKER, "自己說了一句（停在還在談）")
        MODEL["talk"] = None
        for who, how in ((self.BLOCKED, "選項"), (self.BLOCKED, "自己說")):
            self.stand(who, cid)
            self.talking(who, cid)
            if how == "選項":
                self.choose(who, "talk:0")
            else:
                self.say(who, "請問近況如何")
            self.you(who, f"模型叫不動、{how}")
        self.call(self.BLOCKED, "POST", "/api/say", {"text": "x" * 80})  # 太長
        self.call(self.BLOCKED, "POST", "/api/say", {"text": "沒有談話對象"})

    def terms_open(self) -> None:
        """言半山求指點一招、模型開條件（交銀）、擲不中：條件還沒答覆（前半停在接、不接兩顆）。"""
        cid = self.fig
        if cid is None:
            return
        self.stand(self.ASKER, cid)
        self.talking(self.ASKER, cid)
        self.ask(self.ASKER, "請你指點我一招", "開了條件", {"ask": "spar", "willing": 0, "condition": "silver", "narrative_terms": TALK_TERMS,
                                                        "narrative_no": TALK_NO}, floor=0)
        emit("接、不接兩顆", self.buttons(self.ASKER, "talk:terms"))

    def owe_open(self) -> None:
        """燕回聲、霍斷橋求贈物、模型開條件（交銀）、擲中：先做後付，他先給，你欠他一件（前半停在約定還欠著）。"""
        cid = self.fig
        if cid is None:
            return
        for who in (self.PAYER, self.LATE):
            self.stand(who, cid)
            self.talking(who, cid)
            self.ask(who, "能否送我些盤纏", "先做後付", {"ask": "gift", "willing": 100, "condition": "silver", "narrative": TALK_REPLY,
                                                        "narrative_terms": TALK_TERMS}, floor=100)
            emit("還他那一顆", self.buttons(who, "talk:repay"))

    def road_open(self) -> None:
        """路修遠求帶路：他親自帶你走一趟（體力不扣、走得慢一點讓前半停在路上）。"""
        cid = self.fig
        if cid is None:
            return
        self.stand(self.WALKER, cid)
        self.talking(self.WALKER, cid)
        self.ask(self.WALKER, "請帶我去別處", "帶路", {"ask": "escort:*", "willing": 100, "condition": "", "narrative": TALK_REPLY}, floor=100, escort_pace=40.0)
        view = self.main(self.WALKER)
        emit("在路上的選單", sorted(self.ids(view)))

    def backing_open(self) -> None:
        """衛承光求陪你出陣：他答應今天在他那一帶陪你出陣一回（前半停在答應了、還在談）。"""
        cid = self.fig
        if cid is None:
            return
        for who in (self.BACKER, self.BACKER2):
            self.stand(who, cid)
            self.talking(who, cid)
            self.ask(who, "陪我出陣一回", "答應陪你出陣", {"ask": "sortie", "willing": 100, "condition": "", "narrative": TALK_REPLY}, floor=100)
            emit("商量打法那一顆", self.buttons(who, "talk:plan"))

    def plea_open(self) -> None:
        """葉聽雪求見焦慮的秦頡：他主動開口求你（模型挑了請託與回報）：他開的請託還沒答覆（前半停在接、不接兩顆）。"""
        from tianxia import figures

        cid = self.PLEAD_FIG if self.PLEAD_FIG in self.c.characters else self.fig
        if cid is None:
            return
        if cid == self.PLEAD_FIG:
            self.world.mutate_season(lambda s: setattr(figures._ensure(GameStateHolder(s), self.c, cid), "prestige", 1))
            from tianxia import figure_life

            emit("他此刻的心事", figure_life.mood_any(GameStateHolder(self.world.get_season()), self.c, cid))
        MODEL["talk"], MODEL["parley"] = {"stance": "suzhan"}, {"want": "*", "reward": "fit", "narrative": TALK_TERMS}
        try:
            with self.parley_on():
                if cid == self.PLEAD_FIG:  # 只有他一位的地點：求見名單收起來了，開口走交友（act:socialize）
                    self.open_social(self.PLEADER, cid)
                else:
                    self.open_call(self.PLEADER, cid)
        finally:
            MODEL["talk"] = MODEL["parley"] = None
        self.you(self.PLEADER, "他先開口")
        emit("接下、不接", self.buttons(self.PLEADER, "talk:terms"))

    def half(self) -> None:
        for who in self.PLAYERS:
            self.you(who, "前半停在這裡")
        self.season_view("前半停在這裡")

    # ── 後半 ──

    def plain_on(self) -> None:
        """沈鶴年接著談（選下一顆）、告辭。"""
        if self.fig is None:
            return
        MODEL["talk"] = {"stance": "xumin"}
        with self.tuned(self.c.config, talk_turns_per_day=9):
            self.choose(self.TALKER, "talk:1")
            self.you(self.TALKER, "接著談")
            self.say(self.TALKER, "不如持重些")
        MODEL["talk"] = None
        self.you(self.TALKER, "又說了一句")
        self.choose(self.TALKER, "talk:leave")
        self.you(self.TALKER, "告辭")

    def terms_on(self) -> None:
        """言半山接了條件：交銀（手頭不夠先試一次）、當場指點。"""
        cid = self.fig
        if cid is None:
            return
        with self.parley_on():
            self.edit(self.ASKER, lambda p: p.stats.update({"silver": 0}))
            self.choose(self.ASKER, "talk:terms:yes")
            self.you(self.ASKER, "手頭不夠")
            self.edit(self.ASKER, lambda p: p.stats.update({"silver": 500}))
            self.choose(self.ASKER, "talk:terms:yes")
            self.you(self.ASKER, "交了銀兩")
            self.choose(self.ASKER, "talk:terms:yes")  # 沒有條件可接了
            self.choose(self.ASKER, "talk:leave")

    def doer(self) -> None:
        """紀行雲一件一件求：指點、說說敵情、贈物（都當場做）；婉拒；開條件不接；開條件接了打探掛成委託；欠他的那一件請他兌現；清單外的事當婉拒。"""
        cid = self.fig
        who = self.DOER
        if cid is None:
            return
        self.stand(who, cid)
        self.talking(who, cid)
        for text, ask in (("請指點我一招", "spar"), ("說說敵情吧", "intel"), ("送我點東西", "gift")):
            self.ask(who, text, f"求{ask}、當場做", {"ask": ask, "willing": 100, "condition": "", "narrative": TALK_REPLY}, floor=100)
        self.ask(who, "再指點我一招", "婉拒", {"ask": "spar", "willing": 0, "condition": "", "narrative_no": TALK_NO}, floor=0)
        self.ask(who, "天下大勢如何", "只是閒聊", {"ask": "", "willing": 0, "condition": "", "narrative": TALK_REPLY}, floor=0)
        self.ask(who, "把你的刀給我", "清單外的事", {"ask": "refuse", "willing": 100, "condition": "", "narrative_no": TALK_NO}, floor=100)
        self.choose(who, "talk:leave")
        self.edit(who, lambda p: p.talks_today.clear())
        self.talking(who, cid)
        self.ask(who, "指點我一招，我替你辦事", "開條件、打探", {"ask": "gift", "willing": 0, "condition": "scout:*", "narrative_terms": TALK_TERMS}, floor=0)
        self.choose(who, "talk:terms:no")
        self.you(who, "不接條件")
        self.ask(who, "送我些盤纏，我替你辦事", "又開條件", {"ask": "gift", "willing": 0, "condition": "scout:*", "narrative_terms": TALK_TERMS}, floor=0)
        self.choose(who, "talk:terms:yes")
        self.you(who, "接了打探（掛成委託）")
        self.edit(who, lambda p: p.parley_owed.update({cid: "gift"}))  # 今天還做得到的一件（指點今天婉拒過了：那一件只會回「改日」）
        emit("請他兌現那一顆", self.buttons(who, "talk:owed"))
        self.choose(who, "talk:owed")
        self.you(who, "他兌現了")
        self.choose(who, "talk:owed")  # 沒有欠了
        self.choose(who, "talk:leave")

    def owe_on(self) -> None:
        """燕回聲還他欠的銀兩（手頭不夠先試一次）；霍斷橋過了期限：食言（情誼扣、那幾句併進書信）。"""
        cid = self.fig
        if cid is None:
            return
        with self.parley_on():
            self.edit(self.PAYER, lambda p: p.stats.update({"silver": 0}))
            self.choose(self.PAYER, "talk:repay")
            self.you(self.PAYER, "手頭不夠")
            self.edit(self.PAYER, lambda p: p.stats.update({"silver": 500}))
            self.choose(self.PAYER, "talk:repay")
            self.you(self.PAYER, "還了")
            self.choose(self.PAYER, "talk:repay")  # 沒有債了
            self.choose(self.PAYER, "talk:leave")

            def expire(s) -> None:
                for debt in s.player.parley_debts.values():
                    debt.due = s.world.time - 1

            self.edit_state(self.LATE, expire)
            self.main(self.LATE)  # 同步：欠的過了期限
            self.you(self.LATE, "食言")

    def road_on(self) -> None:
        """路修遠在路上每到一站跟他說一句（parley:road）；同一站不能說兩次。"""
        if self.fig is None:
            return
        view = self.main(self.WALKER)
        emit("在路上的選單", sorted(self.ids(view)))
        for text in ("一路有勞", "再問一句"):
            self.ask(self.WALKER, text, "路上說一句", {"ask": "intel", "willing": 100, "condition": "", "narrative": TALK_REPLY}, "parley:road", floor=100)
        self.edit(self.WALKER, lambda p: setattr(p, "parley_road_leg", -1))
        MODEL["talk"] = None
        self.say(self.WALKER, "模型叫不動", "parley:road")
        self.you(self.WALKER, "路上模型叫不動")

    def backing_on(self) -> None:
        """衛承光商量打法（成、不成各一次〔雖然第二次打法已經商量過〕）、出陣。"""
        cid = self.fig
        if cid is None:
            return
        self.ask(self.BACKER, "我想從側翼包抄", "商量打法", {"willing": 100, "narrative": TALK_REPLY, "narrative_no": TALK_PLAN_NO}, "talk:plan", plan_floor=100)
        self.ask(self.BACKER2, "那就正面強攻", "商量不成", {"willing": 0, "narrative": TALK_REPLY, "narrative_no": TALK_PLAN_NO}, "talk:plan", plan_floor=0, plan_cap=0)
        self.ask(self.BACKER2, "再換個打法", "已經商量過了", {"willing": 100, "narrative": TALK_REPLY}, "talk:plan", plan_floor=100)
        self.set_duel(False)
        for who in (self.BACKER, self.BACKER2):
            self.choose(who, "talk:leave")
            self.place(who, self.backing_spot(who))
            emit("出陣那一顆", self.ids(self.main(who)).get("act:train"))
            with self.winning():
                self.choose(who, "act:train")
            self.you(who, "出陣之後")

    def backing_spot(self, who: str) -> str:
        """他那一帶（答應陪你出陣的那一區）裡出得了陣的地方：並肩那一句（BACKED_LINE）只在他那一帶出陣才有；找不到就退回中立地汝南荒野。"""
        from tianxia import figure_life

        state = self.chars.load(who)
        b = state.player.parley_backing if state is not None else None
        for spot in sorted(loc for loc in self.c.locations if b is not None and b.region is not None and figure_life._region(self.c, loc) == b.region):
            self.place(who, spot)
            if self.ids(self.main(who)).get("act:train", {}).get("enabled"):
                emit("他那一帶出陣的地方", spot)
                return spot
        emit("他那一帶沒有出得了陣的地方", None)
        return "runan_wilds"

    def plea_on(self) -> None:
        """葉聽雪接下他的請託：記成你欠他的一件（到期沒做是食言）；再不接的另一位（冷千山沒開口，這裡略）。"""
        if self.fig is None:
            return
        with self.parley_on():
            self.choose(self.PLEADER, "talk:terms:yes")
            self.you(self.PLEADER, "接下請託")
            self.choose(self.PLEADER, "talk:leave")

    def forsake(self) -> None:
        """葉聽雪還欠著秦頡的請託，去黃巾的投靠點叛投（defect:<陣營> → defect:confirm）：欠著的都算食言（情誼扣、那幾句併進書信）。"""
        if self.fig is None:
            return
        who = self.PLEADER
        target = next((f for f in self.c.scenario.factions if f.id != self.PLAYERS[who] and f.join_at), None)
        if target is None:
            emit("沒有別的陣營可叛投", None)
            return
        self.place(who, target.join_at[0])
        ids = [i for i in self.ids(self.main(who)) if i.startswith("defect:")]
        emit("叛投那幾顆", ids)
        if ids:
            self.choose(who, ids[0])
            self.choose(who, "defect:confirm")
        self.you(who, "叛投之後")

    def foe(self) -> None:
        """冷千山（黃巾）求官軍的人物：敵對（意願的天花板再減）；擲中、擲不中各一次。"""
        cid = self.fig
        if cid is None:
            return
        self.stand(self.FOE, cid)
        self.talking(self.FOE, cid)
        self.ask(self.FOE, "請指點我一招", "敵對、擲不中", {"ask": "spar", "willing": 100, "condition": "", "narrative": TALK_REPLY, "narrative_no": TALK_NO}, floor=0)
        self.ask(self.FOE, "說說敵情吧", "敵對、擲中", {"ask": "intel", "willing": 100, "condition": "", "narrative": TALK_REPLY}, floor=100)
        self.choose(self.FOE, "talk:leave")

    def bots(self) -> None:
        """假人（人物情誼一軌的 BotRunner 十輪與整季機器人）；加上 bot_policy.score 問 talk:、parley: 的各幾顆（假人只按告辭，其餘不按）。"""
        super().bots()
        from tianxia import bot_policy
        from tianxia.core.option import Option
        from tianxia.state import BotProfile

        self.begin()
        game = self.server.game_for(self.TALKER)
        profile = BotProfile(personality="普通", seed=3, faction="guan", season_number=self.world.get_season_number())
        emit("假人眼中的分數", {oid: bot_policy.score(game, Option(id=oid, label=oid), profile) for oid in (
            "talk:0", "talk:say", "talk:leave", "talk:plan", "talk:terms:yes", "talk:terms:no", "talk:repay", "talk:owed", "talk:clue:a:0",
            "talk:opp:x", "parley:road")})

    def season(self) -> None:
        """收季、開下一季：談話、條件、欠的都跟著新角色重來。"""
        self.do(ADMIN, "end_season")
        self.main(self.TALKER)
        self.do(ADMIN, "next_season")
        for who in self.PLAYERS:
            self.main(who)
            self.you(who, "換季之後")
        self.season_view("換季之後")


# 改一個字（selftest）：指點一招那一句（parley.SPAR_LINE；搬之前在 tianxia/parley.py、之後在包裡），week7 紀行雲求指點、當場做那一下抓到
register_track("talk", TalkScenario, (("tianxia/features/companions/parley.py", "tianxia/parley.py"),
                                      ('SPAR_LINE = "{name}陪你拆了幾招，隨手點出你的破綻。"', 'SPAR_LINE = "{name}陪你拆了幾招，隨手點出你的破綻！"')), "week7")
