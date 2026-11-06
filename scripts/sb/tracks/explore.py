"""same_behavior 一軌一檔：explore（不登記軌，explore-compare 那一組子命令走這裡，別的軌繼承它的情境）。"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import os
import random
import shutil
import sys
import time
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, BUF, CLOCK0, PROFILES, SUBCOMMANDS, _digest, _first_diff, _run_set, _setup_child, _wipe_db, db_text, emit

# ═══════════════════════════ explore（主動搬六包第 3＋4 批：走一趟、探索一顆） ═══════════════════════════
# 第 3＋4 批加的：情境 ExploreScenario（自己一個資料庫、自己切一半）、
# 假人 explore_bots_run，與四個子命令 explore-run、explore-bots、explore-compare、explore-selftest。上面原本的 run、compare、selftest、
# bots 一個字不動（出陣那一軌照舊用它們）；dev/sortie-2 把那幾個改成分軌（--track），合併之後可以把這一段收成 --track explore。
#
# 抽到哪一類（explore_one.draw）、仗打成怎樣（team.fight 的 tier）、幾個機率（rare_explore_chance、explore_legend_chance、
# duel.explore_chance、outing_trace_chance）在要的那幾步照寫好的換掉（模組屬性與記憶體裡的設定，兩份程式同一步換、同一步換回）；
# 換掉的 draw 把引擎算給它的比重寫進輸出（head 算錯比重照樣抓得到）。其餘照固定的亂數自己走。

EXPLORE_BOT_PROFILES = ("season21", "week7")  # 走一趟、探索一顆開著的兩種（不帶、weekend、測試內容關著）
EXPLORE_MUTANT_PROFILE = "week7"
# selftest 故意改的一個字：走一趟（同一趟留第二句那一句）、探索一顆（紀錄的結果標記「得料」）各一句；舊名的檔、搬進包的檔兩處找。
# 那兩處在整檔照搬的規則模組裡；動作模組（本體從 Game 搬過去、self 換成 ctx 的那兩個檔）另各改一處（審查修正）：探索一顆每一下少扣
# 1 體力、走一趟中途離開不收成「中途離開」——搬之前在 engine.py，搬進包之後在 explore_actions.py、outing_actions.py
EXPLORE_MUTATIONS = {
    "outing": (("tianxia/features/explore/outing_rules.py", "tianxia/outing.py"),
               ('SAY_AGAIN = "這一趟已經留過一句了。"', 'SAY_AGAIN = "這一趟已經留過一句了！"')),
    "explore_one": (("tianxia/features/explore/explore_rules.py", "tianxia/explore_one.py"),
                    ('MATERIAL: "得料"', 'MATERIAL: "得料！"')),
    "explore_actions": (("tianxia/features/explore/explore_actions.py", "tianxia/engine.py"),
                        ("p.stamina -= cfg.explore_stamina\n", "p.stamina -= cfg.explore_stamina - 1\n")),
    "outing_actions": (("tianxia/features/explore/outing_actions.py", "tianxia/engine.py"),
                       ("if trip.place != p.location:", "if trip.place != p.location and False:")),
}



def _gather_finds_hosts() -> list:
    """gather_finds 住在哪幾個模組：第 13 批之前是 tianxia/explore_modes.py，之後是探索包的 explore_rules（舊名 explore_one 是它的別名）；
    第 13 批做到一半（探索一顆已經改叫 explore_rules、三選一還在）是兩個都有。"""
    hosts = [_explore_rules()] if hasattr(_explore_rules(), "gather_finds") else []
    try:
        from tianxia import explore_modes
    except ImportError:
        return hosts
    return [*hosts, explore_modes] if hasattr(explore_modes, "gather_finds") else hosts


def _explore_rules():
    """探索一顆的純規則模組：base 是 tianxia/explore_one.py，head 是指到探索包 explore_rules 的別名（同一個模組物件；換掉它的屬性兩邊都打得到）。"""
    from tianxia import explore_one

    return explore_one


class ExploreScenario(Scenario):
    """走一趟與探索一顆（第 3＋4 批）。照調查 plan.json order 3、6 的 behavior_check：各種地點按探索、事件卡等回答、遭遇、稀有、
    分級事件、隨口應對分岔（假模型）、45 級閘、掉落與破境丹、頭目、自家營寨比劃；走一趟一、三、五段、停下來、結算卡、題壁留言與
    預設三句、題壁墨（萬寶閣）、別人看得到痕跡、管理者抹掉、拒絕的情況。不帶、weekend、測試內容裡這兩樣關著：main.outing 是 None、
    四個 op 都回「此刻無法」、act:explore 走舊探索與三選一。
    半舊半新兩個切點都在前半的最後一段（half）：胡鐵花開一趟五段走到第二段停（等選事件）、姬冰雁探索出一張事件卡等回答；
    後半第一件事（answer）是新程式接著選完、走完、回答。"""

    PLAYERS = {"葉開": None, "丁靈琳": None, "路小佳": None, "燕南飛": None, "孟星魂": None, "高寄萍": "guan", "姬冰雁": None,
               "胡鐵花": None}
    NEWBIE = "初出茅廬"
    PHASES_FIRST = ["setup", "prologue", "places", "beats", "trip", "ink", "seen", "refuse", "half"]
    PHASES_SECOND = ["resume", "answer", "fight", "rare", "tiered", "freetext", "capped", "drops", "boss", "spar", "erase", "maps",
                     "season"]

    # ── 小工具 ──

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            fn(state)
            self.chars.save(state)

    @contextlib.contextmanager
    def draws(self, *kinds: str):
        """探索一顆這幾下抽到的類別照 kinds 的順序（用完了照真的抽）；每一次都把引擎給的比重、上一趟的類別寫進輸出。"""
        explore_one = _explore_rules()

        real, queue = explore_one.draw, list(kinds)

        def draw(rng, weights, *, last_choice=None):
            forced = queue.pop(0) if queue else None
            emit("抽", {"weights": dict(weights), "last": last_choice, "forced": forced})
            return forced if forced is not None else real(rng, weights, last_choice=last_choice)

        explore_one.draw = draw
        try:
            yield
        finally:
            explore_one.draw = real

    @contextlib.contextmanager
    def fights(self, tier: str | None):
        """這幾下的仗照寫好的 tier（同 Scenario.winning：威力、難度、亂數照算，只換結果）；None 照打。"""
        from tianxia import team

        real = team.fight

        def fight(*args, **kwargs):
            if kwargs.get("tier") is None and tier is not None:
                kwargs["tier"] = tier
            return real(*args, **kwargs)

        team.fight = fight
        try:
            yield
        finally:
            team.fight = real

    @contextlib.contextmanager
    def finds(self, *mids: str):
        """素材拍這幾下找到的照 mids（一下一顆；用完了照真的找）：gather_finds 換掉（模組屬性；第 13 批之前在 explore_modes、
        之後在探索包的 explore_rules，兩份程式各換自己有的那幾個，同一條佇列），每一次都寫進輸出。"""
        hosts = _gather_finds_hosts()
        reals = [(host, host.gather_finds) for host in hosts]
        queue = list(mids)

        def patched(real):
            def gather_finds(*args, **kwargs):
                if not queue:
                    return real(*args, **kwargs)
                found = [queue.pop(0)]
                emit("找到", found)
                return found

            return gather_finds

        for host, real in reals:
            host.gather_finds = patched(real)
        try:
            yield
        finally:
            for host, real in reals:
                host.gather_finds = real

    @contextlib.contextmanager
    def tweak(self, obj, **values):
        """記憶體裡的設定這幾步換掉（兩份程式同一步換、同一步換回）。"""
        old = {k: getattr(obj, k) for k in values}
        for k, v in values.items():
            setattr(obj, k, v)
        try:
            yield
        finally:
            for k, v in old.items():
                setattr(obj, k, v)

    @contextlib.contextmanager
    def answer_model(self):
        """隨口應對的假模型：歸類回清單上的第一種、成算 70；判善惡回預設（中）；其餘照舊不連網路。"""
        import requests

        from tianxia import ollama_client

        wrapped = ollama_client.OllamaClient.from_config.__func__

        def chat_structured(client, messages, schema, *a, **k):
            fields = getattr(schema, "model_fields", {})
            if "outcome" in fields:
                ids = (fields["outcome"].json_schema_extra or {}).get("enum") or [""]
                return schema(outcome=ids[0], success_rate=70)
            if schema.__name__ == "SuccessRateJudgment":
                return schema(success_rate=70)
            if schema.__name__ == "MoralJudgment":
                return schema()
            raise requests.ConnectionError("same_behavior：不連模型")

        def from_config(cls, cfg):
            client = wrapped(cls, cfg)
            client.__class__ = type("AnswerClient", (type(client),), {"chat_structured": chat_structured})
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)
        try:
            yield
        finally:
            ollama_client.OllamaClient.from_config = classmethod(wrapped)

    def options(self, who: str) -> dict[str, dict]:
        return self.ids(self.main(who))

    def settle(self, who: str, rounds: int = 10) -> None:
        """這一下端出來要選的（事件、有所感、頭目戰的招）：照第一顆按得下去的選掉，直到探索回到選單上（或選不動）。"""
        from tianxia import sensing

        for _ in range(rounds):
            opts = self.options(who)
            if "act:explore" in opts:
                return
            pick = next((i for pre in ("choice:", "sense:", "duel:") for i, o in opts.items()
                         if i.startswith(pre) and o.get("enabled") and i not in (sensing.LET_GO, "duel:flee")), None)
            pick = pick or (sensing.LET_GO if sensing.LET_GO in opts else None)
            if pick is None:
                return
            self.choose(who, pick)

    def explore(self, who: str, nth: int = 0) -> None:
        """按一下探索：探索一顆開著是出門一趟；三選一開著（weekend）只回展開的那一句，再照 nth 輪流按一顆；接著選掉端出來的。"""
        self.choose(who, "act:explore")
        modes = [i for i, o in self.options(who).items() if i.startswith("explore:") and o.get("enabled")]
        if modes:
            self.choose(who, modes[nth % len(modes)])
        self.settle(who)

    def walk(self, who: str, n: int, rounds: int = 10) -> None:
        """走一趟 n 段：出發，停在要選的事上就選掉、接著走，直到收了（關著的季只回一句「此刻無法」）。"""
        out = self.do(who, "outing", {"n": n})
        for _ in range(rounds):
            main = out.get("main") if isinstance(out, dict) else None
            trip = ((main or {}).get("outing") or {}).get("trip") if isinstance(main, dict) else None
            if not trip or trip.get("end"):
                return
            if trip.get("waiting"):
                self.settle(who)
            out = self.do(who, "outing", {})

    def kind_places(self) -> list[tuple[str, str]]:
        """（地點種類, 這一種照 id 排的第一個地點）：城、寺、渡、野、山、營。"""
        explore_one = _explore_rules()

        cfg = self.c.config.jianfa
        out = []
        for kind in (explore_one.TOWN, explore_one.TEMPLE, explore_one.FORD, explore_one.WILD, explore_one.HILL, explore_one.CAMP):
            loc = next((i for i, x in sorted(self.c.locations.items()) if explore_one.kind_of(cfg, x).kind == kind), None)
            if loc is not None:
                out.append((kind, loc))
        return out

    def first_event(self, test) -> str | None:
        """照 id 排第一則合 test 的事件（探索抽得到的優先）。"""
        evs = sorted(self.c.events.values(), key=lambda e: ("explore" not in e.actions, e.id))
        return next((e.id for e in evs if test(e)), None)

    def player_view(self, who: str, tag: str) -> None:
        p = self.chars.load(who).player
        emit(tag, {"outing": None if p.outing is None else p.outing.model_dump(), "outing_last": p.outing_last,
                   "explore_seq": p.explore_seq, "fights": [p.fight_day, p.fights_today], "stamina": p.stamina})

    # ── 前半 ──

    def setup(self) -> None:
        super().setup()
        self.place("高寄萍", None, faction="guan")  # 自家營寨比劃要有陣營（直接擺：投靠那一段是出陣那一軌驗的）

    def prologue(self) -> None:
        """序章的舊探索（草廬四景，_explore_outcome），接著按一下走一趟一段。有序章的只有不帶、weekend，那兩種走一趟本來就關著
        （回「此刻無法」是因為關著，不是因為在序章裡）；season21、week7 沒有序章，那一下是真的出發。所以 outing_go 的「序章裡不走」
        那一條在這五種設定裡都碰不到（審查修正：原本這裡寫成驗到了）。"""
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
        self.do(who, "outing", {"n": 1})

    def places(self) -> None:
        """各種地點各按兩下探索（照固定的亂數自己抽）：鈕上的小字、行動列底下那一行、四格那一格的 mostly、結果那一段與帳。"""
        who = ["葉開", "丁靈琳", "路小佳", "燕南飛", "孟星魂", "姬冰雁"]
        for i, (kind, loc) in enumerate(self.kind_places()):
            name = who[i % len(who)]
            for k in range(2):
                self.place(name, loc)
                view = self.main(name)
                emit(f"{kind} {loc} 的探索", {"option": self.ids(view).get("act:explore"),
                                            "note": (view.get("action_notes") or {}).get("act:explore"),
                                            "mostly": view.get("mostly"), "outing": view.get("outing")})
                self.explore(name, i + k)
                self.player_view(name, f"{name} 探索之後")

    def beats(self) -> None:
        """四類各一下（照寫好的抽）：事件卡等你回答、有所感、素材、遭遇打贏與打輸。"""
        explore_one = _explore_rules()

        for kind, tier in ((explore_one.EVENT, None), (explore_one.INSIGHT, None), (explore_one.MATERIAL, None),
                           (explore_one.ENCOUNTER, "大勝"), (explore_one.ENCOUNTER, "落敗")):
            if not self.place("燕南飛", "yingshui"):
                return
            with self.draws(kind), self.fights(tier):
                out = self.choose("燕南飛", "act:explore")
            emit(f"{kind} {tier or ''} 那一下", (out.get("main") or {}).get("latest") if isinstance(out, dict) else None)
            self.settle("燕南飛")
        self.player_view("燕南飛", "燕南飛 四類之後")

    def trip(self) -> None:
        """走一趟：段數選單、n=2 不收、五段（第二段停在事件上、選完接著走；有一段打贏）、結算卡、預設句留言、同一趟再留一句被擋。"""
        explore_one = _explore_rules()

        if not self.place("葉開", "yingshui"):
            return
        emit("段數選單", self.main("葉開").get("outing"))
        self.do("葉開", "outing", {"n": 2})
        with self.draws(explore_one.MATERIAL, explore_one.EVENT, explore_one.MATERIAL, explore_one.ENCOUNTER, explore_one.MATERIAL), \
                self.fights("大勝"):
            self.walk("葉開", 5)
        self.player_view("葉開", "葉開 走完五段")
        self.do("葉開", "outing_say", {"preset": 0})
        self.do("葉開", "outing_say", {"preset": 1})
        with self.draws(explore_one.MATERIAL):
            self.place("葉開", "yingshui")
            self.walk("葉開", 1)  # 第二趟（Outing.n 加一）：一段

    def ink(self) -> None:
        """自己寫的一句要一張題壁墨：沒有回 NO_INK → 管理者補發元寶 → 萬寶閣買題壁墨 → 再寫；遊記（模型不在，照模板）。"""
        explore_one = _explore_rules()

        if not self.place("丁靈琳", "yingshui"):
            return
        with self.draws(explore_one.MATERIAL, explore_one.MATERIAL, explore_one.MATERIAL):
            self.walk("丁靈琳", 3)
        line = "江湖路遠，後會有期"
        self.do("丁靈琳", "outing_say", {"text": line})
        self.do(ADMIN, "mall_reissue", {"name": "丁靈琳", "amount": 200, "note": "對照", "ref": "sb-reissue-1"})  # 不給編號伺服器會產一個隨機的
        self.call("丁靈琳", "POST", "/api/mall/buy", {"item": "inscribe_ink", "ref": "sb-ink-1"})
        self.do("丁靈琳", "outing_say", {"text": line})
        self.do("丁靈琳", "outing_tale")
        self.do("丁靈琳", "outing_tale")  # 請過了：不再開單

    def seen(self) -> None:
        """別人看得到痕跡：路小佳在同一處走五段，路上的那一行一定擲中（outing_trace_chance 換成 1），一趟最多兩行（outing_trace_cap
        換成 2；正式是 1）：這一處有人，第一行一定是遠處有人揮手，第二行才輪得到刻在石頭上的別人的留言（葉開、丁靈琳剛在這裡留過）。"""
        explore_one = _explore_rules()

        if not self.place("路小佳", "yingshui"):
            return
        with self.draws(*[explore_one.MATERIAL] * 5), \
                self.tweak(self.c.config.jianfa, outing_trace_chance=1.0, outing_trace_cap=2):
            self.walk("路小佳", 5)
        self.player_view("路小佳", "路小佳 路上看到的")

    def refuse(self) -> None:
        """拒絕：體力不夠、在路上、走到一半人離開（收成「中途離開」）。"""
        explore_one = _explore_rules()

        if not self.place("燕南飛", "yingshui"):
            return
        self.edit("燕南飛", lambda p: setattr(p, "stamina", 5.0))
        self.do("燕南飛", "outing", {"n": 5})
        self.place("燕南飛", None)
        move = next((i for i, o in self.options("燕南飛").items() if i.startswith("move:") and o.get("enabled")), None)
        if move is not None:
            self.choose("燕南飛", move)
            self.do("燕南飛", "outing", {"n": 1})
        if self.place("孟星魂", "yingshui"):
            with self.draws(explore_one.MATERIAL, explore_one.EVENT):
                self.do("孟星魂", "outing", {"n": 3})
            self.place("孟星魂", "yingchuan")
            self.do("孟星魂", "outing", {})
            self.do("孟星魂", "outing_say", {"preset": 0})  # 中途離開的那一趟不能留言
            self.settle("孟星魂")
            self.player_view("孟星魂", "孟星魂 中途離開")

    def half(self) -> None:
        """前半的最後一段（半舊半新的切點）：胡鐵花開一趟五段走到第二段停（等選事件）；姬冰雁出門一趟抽到事件、卡等回答。"""
        explore_one = _explore_rules()

        if self.place("胡鐵花", "yingshui"):
            with self.draws(explore_one.MATERIAL, explore_one.EVENT):
                self.do("胡鐵花", "outing", {"n": 5})
            self.player_view("胡鐵花", "胡鐵花 停在第二段")
        if self.place("姬冰雁", "nanyang_wilds"):
            with self.draws(explore_one.EVENT):
                self.choose("姬冰雁", "act:explore")
            modes = [i for i, o in self.options("姬冰雁").items() if i.startswith("explore:") and o.get("enabled")]
            if modes:  # 三選一的季：找事件那一顆
                self.choose("姬冰雁", next((m for m in modes if m == "explore:seek"), modes[0]))
            emit("姬冰雁 等回答", self.chars.load("姬冰雁").pending_event)

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def answer(self) -> None:
        """新程式接手：姬冰雁回答舊程式端出來的事件卡；胡鐵花選完那件事（走一趟記下那一下的得失）、接著走完。"""
        explore_one = _explore_rules()

        self.settle("姬冰雁")
        self.player_view("姬冰雁", "姬冰雁 回答之後")
        self.settle("胡鐵花")
        self.player_view("胡鐵花", "胡鐵花 選完")
        with self.draws(explore_one.MATERIAL, explore_one.MATERIAL, explore_one.MATERIAL):
            out = self.do("胡鐵花", "outing", {})
            for _ in range(6):
                trip = (((out.get("main") or {}).get("outing") or {}).get("trip") if isinstance(out, dict) else None) or {}
                if not trip or trip.get("end"):
                    break
                if trip.get("waiting"):
                    self.settle("胡鐵花")
                out = self.do("胡鐵花", "outing", {})
        self.player_view("胡鐵花", "胡鐵花 走完")

    def fight(self) -> None:
        """遭遇：散人在官軍大營撞上北軍五校（必敗）照寫好的打贏＝以弱勝強（行狀、世界記事）；走一趟裡也打贏一次；城裡的地痞照打。"""
        explore_one = _explore_rules()

        if self.place("燕南飛", "guan_camp"):
            emit("必敗的探索", self.options("燕南飛").get("act:explore"))
            with self.draws(explore_one.ENCOUNTER), self.fights("大勝"):
                self.choose("燕南飛", "act:explore")
            self.place("燕南飛", "guan_camp")
            with self.draws(explore_one.ENCOUNTER), self.fights("大勝"):
                self.walk("燕南飛", 1)
            self.player_view("燕南飛", "燕南飛 以弱勝強")
        town = next((loc for kind, loc in self.kind_places() if kind == "town"), None)
        if town is not None and self.place("丁靈琳", town):
            with self.draws(explore_one.ENCOUNTER, explore_one.ENCOUNTER):
                self.choose("丁靈琳", "act:explore")
                self.settle("丁靈琳")
                self.place("丁靈琳", None)
                with self.fights("僵持"):
                    self.choose("丁靈琳", "act:explore")
            self.settle("丁靈琳")

    def rare(self) -> None:
        """稀有與稀世：
        - 一次性奇遇必中（rare_explore_chance 換成 1）：站在此刻有一次性奇遇可抽的地點（白馬寺：鎮山塔；深山：飛瀑）出門一趟抽到事件，
          走的是事件拍的稀有那一支（outing_event）。路小佳按一下探索；葉開走一趟一段，那一段記成稀有（"rare": true）。
        - 稀世的素材：丁靈琳走一趟一段抽到素材，找到的換成一顆 FEAT_TIER 階以上的（finds；gather_finds 只給一、二階，自己走不到），
          收的時候記一則行狀與世界記事。
        - 五段的一趟照固定的亂數自己抽（段數越多稀有的越容易來）。"""
        explore_one = _explore_rules()
        from tianxia import outing

        if self.place("路小佳", "baima_temple"):
            with self.draws(explore_one.EVENT), self.tweak(self.c.config, rare_explore_chance=1.0):
                self.choose("路小佳", "act:explore")
            emit("路小佳 稀有的事件", self.chars.load("路小佳").pending_event)
            self.settle("路小佳")
        if self.place("葉開", "deep_mountain"):
            with self.draws(explore_one.EVENT), self.tweak(self.c.config, rare_explore_chance=1.0):
                self.walk("葉開", 1)
            self.player_view("葉開", "葉開 稀有的一段")
        top = sorted(m.id for m in self.c.materials.values() if m.tier >= outing.FEAT_TIER)
        emit("稀世的素材", top[:1])
        if top and self.place("丁靈琳", "yingshui"):
            with self.draws(explore_one.MATERIAL), self.finds(top[0]):
                self.walk("丁靈琳", 1)
            self.player_view("丁靈琳", "丁靈琳 稀世的一段")
        if self.place("葉開", "nanyang_wilds"):
            self.walk("葉開", 5)
            self.player_view("葉開", "葉開 自己抽的五段")

    def tiered(self) -> None:
        """分級事件經探索一顆抽出來：武事那一道門開到第二階（等級拉到門檻）的人，站在一則第二階武事事件掛的地點（不是野類：野類先抽旅人）
        出門一趟抽到事件——事件分級挑第二階（tier_mix 換成只有第二階）、一次性奇遇不擲（rare_explore_chance 換成 0）——走的是
        outing_event → pick_event 端出來（場景卡上那一行），選第一個。三選一的季照找事件那一顆按。"""
        explore_one = _explore_rules()

        cfg = self.c.config.jianfa

        def fits(e) -> bool:
            loc = self.c.locations.get(e.locations[0]) if e.locations else None
            return e.tier == 2 and e.door == "武事" and "explore" in e.actions and loc is not None \
                and explore_one.kind_of(cfg, loc).kind != explore_one.WILD

        ev = self.first_event(fits)
        emit("分級事件", ev)
        if ev is None or not self.place("孟星魂", self.c.events[ev].locations[0]):
            return
        need = (cfg.tier_doors.get("武事") or [1])[0]
        self.edit("孟星魂", lambda p: setattr(p.member, "level", max(p.member.level, need)))
        mix = {**cfg.tier_mix, 2: [0.0, 1.0], 3: [0.0, 1.0, 0.0]}
        with self.draws(explore_one.EVENT), self.tweak(self.c.config, rare_explore_chance=0.0), self.tweak(cfg, tier_mix=mix):
            self.choose("孟星魂", "act:explore")
            modes = [i for i, o in self.options("孟星魂").items() if i.startswith("explore:") and o.get("enabled")]
            if modes:  # 三選一的季：找事件那一顆
                self.choose("孟星魂", next((m for m in modes if m == "explore:seek"), modes[0]))
        emit("孟星魂 抽到的分級事件", self.chars.load("孟星魂").pending_event)
        self.settle("孟星魂")

    def freetext(self) -> None:
        """隨口應對的分岔（假模型）：走一趟停在事件上，換成一則寫了後果的事件，回一句話；接著走完。"""
        explore_one = _explore_rules()

        ev = self.first_event(lambda e: e.free_text is not None and bool(e.free_text.outcomes)) or \
            self.first_event(lambda e: e.free_text is not None)
        emit("隨口應對的事件", ev)
        if ev is None or not self.place("路小佳", "yingshui"):
            return
        with self.draws(explore_one.EVENT):
            self.do("路小佳", "outing", {"n": 3})
        self.edit_state("路小佳", lambda s: setattr(s, "pending_event", ev))
        emit("隨口應對那一顆", {i: o for i, o in self.options("路小佳").items() if not i.startswith(("move:", "act:"))})
        with self.answer_model():
            self.call("路小佳", "POST", "/api/answer", {"text": "我上前扶他一把，問他要往哪裡去。"})
        self.settle("路小佳")
        with self.draws(explore_one.MATERIAL, explore_one.MATERIAL):
            self.do("路小佳", "outing", {})
        self.player_view("路小佳", "路小佳 隨口應對之後")

    def capped(self) -> None:
        """45 級閘：45 級的人出門一趟打贏一場、撿一次素材（經驗換心得、段落結尾「境界已到」）。"""
        explore_one = _explore_rules()

        if not self.place("孟星魂", "nanyang_wilds"):
            return
        self.edit("孟星魂", lambda p: setattr(p.member, "level", 45))
        with self.draws(explore_one.ENCOUNTER), self.fights("大勝"):
            self.choose("孟星魂", "act:explore")
        self.settle("孟星魂")
        self.place("孟星魂", None)
        with self.draws(explore_one.MATERIAL):
            self.choose("孟星魂", "act:explore")
        self.settle("孟星魂")
        self.player_view("孟星魂", "孟星魂 45 級")

    def drops(self) -> None:
        """掉落與破境丹：破境丹必中（explore_legend_chance 換成 1）出門兩趟。"""
        explore_one = _explore_rules()

        if not self.place("姬冰雁", "yingshui"):
            return
        with self.draws(explore_one.MATERIAL, explore_one.ENCOUNTER), self.tweak(self.c.config, explore_legend_chance=1.0), \
                self.fights("大勝"):
            self.choose("姬冰雁", "act:explore")
            self.settle("姬冰雁")
            self.place("姬冰雁", None)
            self.choose("姬冰雁", "act:explore")
        self.settle("姬冰雁")
        self.player_view("姬冰雁", "姬冰雁 掉落")

    def boss(self) -> None:
        """頭目：長社（只有頭目、沒有一般對手）出門一趟抽到遭遇，頭目擋路、頭目戰照第一招打完；頭目機率換成 1 再擲一次。"""
        explore_one = _explore_rules()

        if not self.place("燕南飛", "changshe"):
            return
        emit("長社的探索", self.options("燕南飛").get("act:explore"))
        with self.draws(explore_one.ENCOUNTER), self.tweak(self.c.config.duel, explore_chance=1.0), self.fights("大勝"):
            self.choose("燕南飛", "act:explore")
            self.settle("燕南飛", rounds=14)
        self.player_view("燕南飛", "燕南飛 頭目之後")

    def spar(self) -> None:
        """自家營寨：官軍的人在官軍大營出門一趟抽到遭遇是跟同袍比劃（出陣包的 _sortie_host 那一路的三成，不打、不掉東西）。"""
        explore_one = _explore_rules()

        if not self.place("高寄萍", "guan_camp"):
            return
        view = self.main("高寄萍")
        emit("自家營寨的探索", {"option": self.ids(view).get("act:explore"), "note": (view.get("action_notes") or {}).get("act:explore")})
        with self.draws(explore_one.ENCOUNTER):
            self.choose("高寄萍", "act:explore")
        self.settle("高寄萍")
        self.player_view("高寄萍", "高寄萍 比劃之後")

    def erase(self) -> None:
        """管理者抹掉一則留言（不是管理者按到回「只有管理者能這麼做」）；抹過的再抹一次回「此刻無法」。"""
        from tianxia.engine import Game

        shell = Game.for_world(self.c, self.world)
        ids = [i.id for i in shell.state.world.inscriptions]
        emit("留言", [i.model_dump() for i in shell.state.world.inscriptions])
        target = ids[0] if ids else 1
        self.do("葉開", "outing_erase", {"id": target})
        self.do(ADMIN, "outing_erase", {"id": target})
        self.do(ADMIN, "outing_erase", {"id": target})

    def maps(self) -> None:
        """輿圖名字旁的兩個字（map_mostly：替每一處假裝站過去）：底圖與疊層。"""
        if self.place("葉開", "yingshui"):
            self.call("葉開", "GET", "/api/map/base")
            self.call("葉開", "GET", "/api/map/state")

    def season(self) -> None:
        """收季、開下一季：走一趟、探索一顆認領的欄位跟著新角色重來。"""
        self.do(ADMIN, "end_season")
        self.main("葉開")
        self.do(ADMIN, "next_season")
        view = self.main("葉開")
        emit("換季之後", {"outing": view.get("outing"), "option": self.ids(view).get("act:explore")})
        self.player_view("葉開", "葉開 換季之後")


def explore_bots_run(root: Path, profile: str, out: Path, tmp: Path) -> None:
    """走一趟、探索一顆的假人：整季機器人（bot.play_season，種子 5）與伺服器假人（BotRunner＋bot_policy.take_turn，random.Random(9)、
    假時鐘，八個站在不在爭奪之列的地點的假人：take_turn 的走一趟那兩段——停著的先接著走、挑到探索就挑段數出發——只有它走得到）
    各跑 N 輪：寫存檔、世界與資料庫的雜湊、各種紀錄標題的次數（看得出「走一趟・某地」「出門一趟・某地」有沒有走到）。"""
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("*.db*"):
        f.unlink()
    _setup_child(root, profile, tmp / "unused.db")
    from collections import Counter

    from tianxia import bot
    from tianxia.bot_runner import BotRunner
    from tianxia.characters import open_characters
    from tianxia.content import load_content
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world
    from tianxia.state import BotProfile

    def titles(states) -> dict:
        return dict(sorted(Counter(e.title for s in states for e in s.journal).items()))

    content = load_content(root / "content", profile=profile)
    world = open_world(tmp / "play.db")
    game = bot.play_season(content, seed=5, max_steps=int(os.environ.get("SB_PLAY_STEPS", "700")), world=world, now=CLOCK0)
    emit("探索 整季機器人 存檔", hashlib.sha256(game.state.model_dump_json().encode("utf-8")).hexdigest())
    emit("探索 整季機器人 紀錄標題", titles([game.state]))
    emit("探索 整季機器人 資料庫", hashlib.sha256(db_text(tmp / "play.db").encode("utf-8")).hexdigest())

    content = load_content(root / "content", profile=profile)
    content.config.bot_tick_seconds = 10 ** 6  # 在線的假人每一輪都動（act_chance 夾到 1）
    world = open_world(tmp / "runner.db")
    world.seed_first_season(content)
    world.open_season(content, now=CLOCK0)
    chars = open_characters(tmp / "runner.db")
    seats = [("探甲", "guan", "yingshui"), ("探乙", "guan", "yingchuan"), ("探丙", "huang", "yingshui"), ("探丁", "huang", "nanyang_road"),
             ("探戊", "guan", "changshe"), ("探己", "huang", "guan_camp"), ("探庚", "guan", "guan_camp"), ("探辛", "huang", "nanyang_wilds")]
    for i, (name, side, loc) in enumerate(seats):
        if loc not in content.locations:
            continue
        g = Game.new(content, name, rng=random.Random(i), world=world, graduated=True)
        g.client = None
        g.sync(CLOCK0)
        p = g.state.player
        p.bot = BotProfile(personality="普通", seed=31 + i, faction=side, season_number=world.get_season_number())
        p.faction, p.location, p.journey = side, loc, None
        p.visited.add(loc)
        p.tutorial_step = len(content.tutorial.steps)
        p.joined_at = -1.0e9
        p.stamina = float(content.config.stamina_max)
        chars.save(g.state)
    clock = [CLOCK0]
    runner = BotRunner(content, world, chars, rng=random.Random(9), clock=lambda: clock[0])
    totals = Counter()
    for _ in range(int(os.environ.get("SB_EXPLORE_TICKS", "160"))):
        clock[0] += 300.0
        report = runner.tick()
        totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
    states = chars.all(bots_only=True)
    trips = Counter((s.player.outing.total, s.player.outing.end) for s in states if s.player.outing is not None)
    emit("探索 假人程式 一輪一輪", dict(sorted(totals.items())))
    emit("探索 假人程式 紀錄標題", titles(states))
    emit("探索 假人程式 最後一趟", {f"{t}段 {e or '還在路上'}": n for (t, e), n in sorted(trips.items())})
    emit("探索 假人程式 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
    emit("探索 假人程式 資料庫", hashlib.sha256(db_text(tmp / "runner.db").encode("utf-8")).hexdigest())
    out.write_text(BUF.getvalue(), encoding="utf-8", newline="\n")
    print(profile, "探索假人", dict(totals), dict(trips))


def _explore_mutant(base: Path, tmp: Path, which: str) -> Path:
    files, (old, new) = EXPLORE_MUTATIONS[which]
    dest = tmp / f"mutant_{which}"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(base, dest, ignore=shutil.ignore_patterns(".git", "saves", ".local", "__pycache__", "node_modules", ".venv", "docs"))
    for rel in files:
        path = dest / rel
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if text.count(old) == 1:
            path.write_text(text.replace(old, new), encoding="utf-8")
            return dest
    raise RuntimeError(f"找不到要改的那一句（{which}）")


def explore_compare(base: Path, head: Path, tmp: Path, profiles: list[str], workers: int, bots: bool, label: str = "ecompare") -> bool:
    """同 compare，跑的是 ExploreScenario（explore-run）與 explore_bots_run（explore-bots）。"""
    tmp.mkdir(parents=True, exist_ok=True)
    chains, outputs = [], {}
    for p in profiles:
        o = {k: tmp / f"{label}_{k}_{p}.txt" for k in ("base", "head", "base1", "head2")}
        dbs = {k: tmp / f"{label}_{k}_{p}.db" for k in ("base", "head", "half")}
        outputs[p] = o
        chains.append([(["explore-run", str(base), p, str(o["base"]), "--tmp", str(tmp), "--db", str(dbs["base"])], tmp / f"{label}_base_{p}.log")])
        chains.append([(["explore-run", str(head), p, str(o["head"]), "--tmp", str(tmp), "--db", str(dbs["head"])], tmp / f"{label}_head_{p}.log")])
        chains.append([
            (["explore-run", str(base), p, str(o["base1"]), "--tmp", str(tmp), "--db", str(dbs["half"]), "--part", "first"],
             tmp / f"{label}_base1_{p}.log"),
            (["explore-run", str(head), p, str(o["head2"]), "--tmp", str(tmp), "--db", str(dbs["half"]), "--part", "second"],
             tmp / f"{label}_head2_{p}.log"),
        ])
    bot_out = {}
    if bots:
        for p in EXPLORE_BOT_PROFILES:
            bot_out[p] = {k: tmp / f"{label}_bots_{k}_{p}.txt" for k in ("base", "head")}
            for k, root in (("base", base), ("head", head)):
                chains.append([(["explore-bots", str(root), p, str(bot_out[p][k]), "--tmp", str(tmp / f"{label}_bots_{k}_{p}")],
                                tmp / f"{label}_bots_{k}_{p}.log")])
    started = time.time()
    _run_set(chains, workers)
    print(f"跑完 {time.time() - started:.0f} 秒")
    ok = True
    for p, o in outputs.items():
        hb, nb, bb = _digest(o["base"])
        hh, _, _ = _digest(o["head"])
        hx, _, _ = _digest(o["base1"], o["head2"])
        same, half = hb == hh, hb == hx
        ok &= same and half
        print(f"explore {p:9} 整段 base {nb} 行 {bb} 位元組 {hb[:16]}｜head {hh[:16]} {'一樣' if same else '不一樣'}"
              f"｜base 前半＋head 後半 {hx[:16]} {'一樣' if half else '不一樣'}")
        if not same:
            print("  " + _first_diff(o["base"].read_bytes(), o["head"].read_bytes()))
        if not half:
            print("  半舊半新：" + _first_diff(o["base"].read_bytes(), o["base1"].read_bytes() + o["head2"].read_bytes()))
    for p, o in bot_out.items():
        hb, nb, bb = _digest(o["base"])
        hh, _, _ = _digest(o["head"])
        ok &= hb == hh
        print(f"探索假人 {p:9} {nb} 行 {bb} 位元組 base {hb[:16]}｜head {hh[:16]} {'一樣' if hb == hh else '不一樣'}")
        if hb != hh:
            print("  " + _first_diff(o["base"].read_bytes(), o["head"].read_bytes()))
    return ok


def explore_selftest(base: Path, tmp: Path, profiles: list[str], workers: int) -> bool:
    """同 selftest：同一份跑兩次一樣、前半＋後半（base 接 base）＝整段、改一個字（走一趟、探索一顆各一份 mutant，跑 week7）抓得到差；
    假人跑兩次一樣。"""
    tmp.mkdir(parents=True, exist_ok=True)
    mutants = {w: _explore_mutant(base, tmp, w) for w in EXPLORE_MUTATIONS}
    chains, outs = [], {}
    for p in profiles:
        o = {k: tmp / f"eself_{k}_{p}.txt" for k in ("a", "b", "first", "second", *(f"mut_{w}" for w in mutants))}
        outs[p] = o
        for k in ("a", "b"):
            chains.append([(["explore-run", str(base), p, str(o[k]), "--tmp", str(tmp), "--db", str(tmp / f"eself_{k}_{p}.db")],
                            tmp / f"eself_{k}_{p}.log")])
        chains.append([
            (["explore-run", str(base), p, str(o["first"]), "--tmp", str(tmp), "--db", str(tmp / f"eself_half_{p}.db"), "--part", "first"],
             tmp / f"eself_first_{p}.log"),
            (["explore-run", str(base), p, str(o["second"]), "--tmp", str(tmp), "--db", str(tmp / f"eself_half_{p}.db"), "--part", "second"],
             tmp / f"eself_second_{p}.log"),
        ])
        if p == EXPLORE_MUTANT_PROFILE:
            for w, root in mutants.items():
                chains.append([(["explore-run", str(root), p, str(o[f"mut_{w}"]), "--tmp", str(tmp), "--db", str(tmp / f"eself_mut_{w}_{p}.db")],
                                tmp / f"eself_mut_{w}_{p}.log")])
    bot_out = {}
    for p in EXPLORE_BOT_PROFILES:
        bot_out[p] = {k: tmp / f"eself_bots_{k}_{p}.txt" for k in ("a", "b")}
        for k in ("a", "b"):
            chains.append([(["explore-bots", str(base), p, str(bot_out[p][k]), "--tmp", str(tmp / f"eself_bots_{k}_{p}")],
                            tmp / f"eself_bots_{k}_{p}.log")])
    started = time.time()
    _run_set(chains, workers)
    print(f"跑完 {time.time() - started:.0f} 秒")
    ok = True
    for p, o in outs.items():
        ha, na, ba = _digest(o["a"])
        hb, _, _ = _digest(o["b"])
        hx, _, _ = _digest(o["first"], o["second"])
        ok &= ha == hb and ha == hx
        line = f"explore {p:9} {na} 行 {ba} 位元組 跑兩次 {'一樣' if ha == hb else '不一樣'}｜前半＋後半 {'一樣' if ha == hx else '不一樣'}"
        if p == EXPLORE_MUTANT_PROFILE:
            for w in mutants:
                hm, _, _ = _digest(o[f"mut_{w}"])
                caught = hm != ha
                ok &= caught
                line += f"｜改一個字（{w}）{'抓得到' if caught else '抓不到'}"
                if caught:
                    line += "（" + _first_diff(o["a"].read_bytes(), o[f"mut_{w}"].read_bytes()).split("：")[0] + "）"
        print(line)
        if ha != hb:
            print("  " + _first_diff(o["a"].read_bytes(), o["b"].read_bytes()))
        if ha != hx:
            print("  " + _first_diff(o["a"].read_bytes(), o["first"].read_bytes() + o["second"].read_bytes()))
    for p, o in bot_out.items():
        ha, na, ba = _digest(o["a"])
        hb, _, _ = _digest(o["b"])
        ok &= ha == hb
        print(f"探索假人 {p:9} {na} 行 {ba} 位元組 跑兩次 {'一樣' if ha == hb else '不一樣'}")
        if ha != hb:
            print("  " + _first_diff(o["a"].read_bytes(), o["b"].read_bytes()))
    return ok


def _explore_main(args: list[str]) -> int:
    """explore 的四個子命令（走一趟、探索一顆，第 3＋4 批）：整串引數進來，入口的 main 查 SUBCOMMANDS 叫到這裡。"""
    ap = argparse.ArgumentParser(description="走一趟、探索一顆的前後一字不變（主動搬六包第 3＋4 批）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("explore-run")
    r.add_argument("root")
    r.add_argument("profile", choices=PROFILES)
    r.add_argument("out")
    r.add_argument("--tmp", required=True)
    r.add_argument("--db")
    r.add_argument("--part", choices=("all", "first", "second"), default="all")
    b = sub.add_parser("explore-bots")
    b.add_argument("root")
    b.add_argument("profile", choices=PROFILES)
    b.add_argument("out")
    b.add_argument("--tmp", required=True)
    for name in ("explore-compare", "explore-selftest"):
        x = sub.add_parser(name)
        x.add_argument("--base", required=True)
        if name == "explore-compare":
            x.add_argument("--head", required=True)
            x.add_argument("--no-bots", action="store_true")
        x.add_argument("--tmp", required=True)
        x.add_argument("--profiles", default=",".join(PROFILES))
        x.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args(args)
    if a.cmd == "explore-run":
        tmp = Path(a.tmp)
        tmp.mkdir(parents=True, exist_ok=True)
        db = Path(a.db) if a.db else tmp / f"sbx_{a.profile}.db"
        if a.part in ("all", "first"):
            _wipe_db(db)
        _setup_child(Path(a.root).resolve(), a.profile, db)
        ExploreScenario(Path(a.root).resolve(), a.profile, db).run(a.part, Path(a.out))
        sys.stdout.flush()
        os._exit(0)  # TestClient 留下的執行緒不等
    if a.cmd == "explore-bots":
        explore_bots_run(Path(a.root).resolve(), a.profile, Path(a.out), Path(a.tmp))
        sys.stdout.flush()
        os._exit(0)
    sys.stdout.reconfigure(encoding="utf-8")
    profiles = [p for p in a.profiles.split(",") if p]
    if a.cmd == "explore-compare":
        ok = explore_compare(Path(a.base).resolve(), Path(a.head).resolve(), Path(a.tmp), profiles, a.jobs, not a.no_bots)
    else:
        ok = explore_selftest(Path(a.base).resolve(), Path(a.tmp), profiles, a.jobs)
    print("全部一樣" if ok else "有不一樣的")
    return 0 if ok else 1


SUBCOMMANDS.update(dict.fromkeys(("explore-run", "explore-bots", "explore-compare", "explore-selftest"), _explore_main))
