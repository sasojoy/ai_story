"""same_behavior 一軌一檔：sense（這一檔登記 sense）。"""
from __future__ import annotations

import contextlib
import hashlib
import os
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, MODEL, STEP, emit, register_track
from sb.tracks.explore import ExploreScenario, _explore_rules

# ═══════════════════════════ sense：有所感與頓悟一軌（全部拆包第 24 批，dev/sense-1） ═══════════════════════════
# 有所感（探索撞上、選做法、擲中、畫一筆或順其自然）、自己畫字的意境（看圖取名的三段式）、特殊頓悟（拷問、小試、心魔、取名）的本體從
# engine.py 與 tianxia/sensing.py、epiphany.py、glyph.py、insight_llm.py 搬進新包 tianxia/features/sense/（舊名留成別名；計畫
# docs/superpowers/plans/2026-11-01-有所感包-第1批.md）。這一段整塊是這一批的：接在檔尾、最後一行登記（register_track），
# PM 合的時候不跟別人的行穿插。角色的名字都是原創的（PM 11/04：新開的軌不用既有作品的人名）。

SENSE_NAME = ("寒潭孤月", "像深夜的潭水，冷而圓滿。")  # 假模型替自己悟的意境取的名字與一句說明（insight_llm.name 的 B 段）
SENSE_GODS = ["雲外天心", "孤峰雪意", "滄海潮生"]  # 假模型替神品意境一次取的三個名字（epiphany.propose_names 的 B 段）
SENSE_OWN = ("靜水流深", "空山聽雨")  # 自己替神品意境寫的名字（dunwu:own 帶 text）
_SENSE_CLIENTS: dict[type, type] = {}


def _sense_client(base: type) -> type:
    """取名的假模型（base 是 _setup_child 那一層換好的 client 類別）：MODEL["sense"] 開著時，替自己悟的意境取名（naming.NameReply）回
    SENSE_NAME、替神品意境取名（epiphany.GodNames）回 SENSE_GODS；其餘照 base（丟連線錯誤、大場面判讀）。"""
    if base not in _SENSE_CLIENTS:
        class SenseClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                if MODEL.get("sense") and schema.__name__ == "NameReply":
                    return schema(name=SENSE_NAME[0], description=SENSE_NAME[1])
                if MODEL.get("sense") and schema.__name__ == "GodNames":
                    return schema(names=list(SENSE_GODS))
                return super().chat_structured(messages, schema, *a, **k)

        _SENSE_CLIENTS[base] = SenseClient
    return _SENSE_CLIENTS[base]


def _sense_test_scene():
    """測試內容沒有有所感的場景：湖邊補一段（同 tianxia/features/sense/tests/test_sensing.py 的湖風；湖邊悟得到柔〔水〕與快〔風〕）。"""
    from tianxia.models import InsightScene, SenseMethod

    return InsightScene(
        id="sb_lake_wind", title="湖風", text="風吹過湖面，停過腳的{痕跡}。", tags=["湖畔"], hints=["柔"],
        methods=[SenseMethod(attribute=a, text=t) for a, t in (("柔", "看水"), ("剛", "打水"), ("快", "追風"), ("慢", "靜坐"))],
    )


class SenseScenario(ExploreScenario):
    """有所感與頓悟（全部拆包第 24 批；--track sense，自己一個資料庫）。小工具借探索那一軌的（draws、fights、tweak、edit_state）。
    二十三個網頁上建的散人與一個走草廬的新人（林聽松）：
    - 草廬（不帶、weekend）：序章第 3 步的有所感版（舊探索 _explore_outcome 開卡、做法都對、必中，做法底下沒有小字），順其自然悟到。
    - 探索撞上有所感（探索一顆開著抽到感悟；三選一按靜心感悟；舊探索只留悟意境那一支；測試內容補一段湖邊的場景）：石觀潮選對、擲中、
      順其自然（落回這一處的基本意境、紀錄「有所感・場景」）；晏棲遲選錯（這一處到換日之前悟不出：三選一的灰鈕、舊探索那一行；一類一顆
      給心得）、再探索一次；穆青梧選對、沒擲中（給一點心得）。擲中與否照 sense_rate_range 擺到頂或到底。
    - 自己畫一筆：韋寒汀按「畫下來」（只叫出畫布）、暖機、讀筆畫（讀得出、只點了一下、格式不對）、送一筆讀不出的（400）、畫一筆落回
      基本意境、畫完再送（那一刻已經過去，400）；江照晚畫一筆要取名的——模型擋著，走退路字表、不記首悟；祁問山（假模型取名：
      看圖拿到名字，記首悟「你是第一個」）、賀知秋（同一處、同一個做法、同一筆：不是第一個）。
    - 特殊頓悟（season21、week7 開著；其餘寫「沒有」、照樣有所感）：擲中感悟時保底（epiphany_dry 擺到 pity）、小試照寫好的那一種
      （epiphany._trial 換掉）。顧折柳：拷問四題、靜候（trial_wait_days 擺 0）、心魔打贏、靜心思名（模型擋著，字表）、自己寫沒帶字、挑第一個。
      蘇停雲：探訪三回、心魔打輸——**前半停在「心魔未破」的卡掛著**；後半收下卡、到了再打的時候（retry_at 擺回去）打贏、靜心思名
      （假模型取三個）、自己寫不合格的、合格的。陸聞箏：打贏一場（探索的遭遇）、心魔打贏——**前半停在等著取名**（還沒按靜心思名）；後半
      自己寫一個這一季已經有人用掉的、換一個。溫行簡：拷問答了一題，到季末沒了結（此事未了）。
    - 寫到一半的有所感：紀守拙停在選做法、裴映雪停在感悟狀態（前半停下）；後半紀守拙選對擲中順其自然；裴映雪先在鎖裡直接開單、人走開再
      交回（C 段重驗對不上），再照常畫一筆。
    - 走一趟停在有所感的卡上（season21、week7 開著；其餘寫「沒有」。審查補的：搬了 outing_watch，以前這一軌沒有 /api/do/outing）：
      岑望舒選對擲中、**前半停在感悟狀態**，後半畫一筆、接著走；杜聽瀾**前半停在卡上**，後半選對、畫一筆要取名的（假模型）；辛遠岫順其自然；
      俞照川保底中了頓悟、拷問、心魔打贏、**前半停在等著取名**，後半靜心思名、挑第一個、接著走。一般的一筆沒有數值變化、beat.after 是空的，
      所以計南枝、盧半溪再各走一次，讓悟的那一下（sensing.finish）、思名的那一下（epiphany.fill）多帶一行料：得失要記在那一段。
      method 每一次都把擲特殊頓悟乘多少寫進輸出（走一趟照這一趟幾段、不在路上是 1）。
    - 清失效參照與畫完清掉的（審查補的）：褚臨風**前半停在卡上**，後半人被帶走、下一次讀檔清掉；費疏影畫完清掉 guide_done 與 battle_card
      （畫之前擺一筆真的戰報，不然讀檔就清了、看不出差別）；籌備中（Game._preparing 換成真）阮晴川畫一筆被擋、涂松聲靜心思名不開單。
    - 假人：BotRunner 四個（一個停在有所感的卡、一個停在感悟狀態、一個等著取名〔頓悟開著的季〕、一個閒著），假模型接取名的 B 段
      （SenseJob、EpiphanyJob）；整季機器人在卡上挑哪一顆也寫下來。
    - 收季、開下一季：石觀潮又撞上一張卡沒了結、溫行簡的頓悟沒了結；換季之後看每個人。"""

    PLAYERS = {name: None for name in ("石觀潮", "晏棲遲", "穆青梧", "韋寒汀", "江照晚", "祁問山", "賀知秋", "顧折柳", "蘇停雲", "陸聞箏",
                                       "紀守拙", "裴映雪", "溫行簡",
                                       "岑望舒", "杜聽瀾", "辛遠岫", "俞照川", "計南枝", "盧半溪", "褚臨風", "費疏影", "阮晴川", "涂松聲")}
    NEWBIE = "林聽松"
    BOT_SEATS = ["悟甲", "悟乙", "悟丙", "悟丁"]
    PHASES_FIRST = ["setup", "prologue", "meet", "miss", "canvas", "named", "epiphany", "demon_lost", "pending", "trip_first", "half"]
    PHASES_SECOND = ["resume", "pending_on", "demon_on", "naming_on", "trip_on", "trip_gains", "stale_on", "clears", "preparing", "bots", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import insights, ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            if MODEL.get("sense"):
                client.__class__ = _sense_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)
        if profile == "test":  # 測試內容沒有有所感的場景：湖邊補一段（前半、後半是兩個行程，各自補；兩份程式同一份內容）
            scene = _sense_test_scene()
            self.c.insight_scenes = {scene.id: scene}

        def ok(loc_id: str) -> bool:
            loc = self.c.locations.get(loc_id)
            return loc is not None and bool(insights.scenes_for(loc, self.c)) and bool(insights.explore_gives(loc, self.c))

        self.spot = next((i for i in ("yingshui", "baima_ford", "lake", *sorted(self.c.locations)) if ok(i)), None)

    # ── 小工具 ──

    def epiphany_on(self) -> bool:
        return bool(self.c.config.epiphany.enabled)

    def me(self, who: str, tag: str) -> None:
        """存檔裡有所感與頓悟碰得到的那幾格：所在、那一份感悟、流水號、選錯的帳、意境與私有意境、頓悟的次數與保底、等著取名的那一個、
        一條線的進度與跳出來的卡、心得、體力、最新三則紀錄（標題、標記、頭幾行、畫的那一筆幾個點）。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "loc": p.location, "sensing": None if p.sensing is None else p.sensing.model_dump(mode="json"), "serial": p.sense_serial,
            "misses": dict(sorted(p.sense_misses.items())), "insights": list(p.insights),
            "own": {k: [v.name, v.attribute, v.note, v.place, len(v.glyph)] for k, v in sorted(p.own_insights.items())},
            "epiphanies": [p.epiphanies, p.epiphany_dry], "god": None if p.god_naming is None else p.god_naming.model_dump(mode="json"),
            "lines": {k: v.model_dump(mode="json") for k, v in sorted(p.storylines.items())}, "open": p.story_open,
            "cards": [x.model_dump(mode="json") for x in p.story_cards], "xinde": p.stats.get("xinde", 0), "stamina": p.stamina,
            "journal": [[e.title, e.tag, list(e.lines)[:4], len(e.glyph)] for e in state.journal[:3]]})

    @contextlib.contextmanager
    def insight_only(self):
        """舊探索（測試內容；序章以外三選一關著的那一種）這一下落在悟意境那一支：Game._explore_weights 只回悟意境（兩份程式都在 engine，
        同一步換、同一步換回）。"""
        from tianxia.engine import Game

        real = Game._explore_weights
        Game._explore_weights = lambda game, loc: [("insight", 1.0)]
        try:
            yield
        finally:
            Game._explore_weights = real

    def sensed(self, who: str) -> None:
        """探索撞上有所感（體力補滿、站到有場景的那一處）：探索一顆開著抽到感悟（draws）；三選一（不帶、weekend）按「靜心感悟」那一顆；
        舊探索（測試內容）只留悟意境那一支。奇遇與頭目這一下不擲（rare_explore_chance、duel.explore_chance 擺 0）。"""
        explore_one = _explore_rules()
        self.place(who, self.spot)
        with self.draws(explore_one.INSIGHT), self.insight_only(), self.tweak(self.c.config, rare_explore_chance=0.0), \
                self.tweak(self.c.config.duel, explore_chance=0.0):
            self.choose(who, "act:explore")
            sense = self.options(who).get("explore:sense")
            if sense is not None and sense.get("enabled"):
                self.choose(who, "explore:sense")
        self.me(who, "探索之後")

    def right_of(self, state, right: bool = True) -> str | None:
        """卡上第一個選得對（right）或選錯的做法（照洗過的順序；序章四景都對）；不在選做法是 None。只讀。"""
        from tianxia import insights

        s = state.player.sensing if state is not None else None
        if s is None or s.stage != "choose":
            return None
        scene, loc = self.c.insight_scenes.get(s.scene), self.c.locations.get(s.location)
        if scene is None or loc is None:
            return None
        pool = insights.pool_attributes(loc, self.c)
        return next((f"sense:{i}" for i, j in enumerate(s.order) if (scene.prologue or scene.methods[j].attribute in pool) == right), None)

    def method(self, who: str, right: bool = True, hit: bool | None = True) -> None:
        """選一個做法（right：選得對不對）；hit 是擲不擲中（sense_rate_range 擺到頂或到底、痕跡不加；None 照擲）。擲中時特殊頓悟的機率
        擺到極小（照樣擲那一顆骰、沒中記一次保底；要頓悟的人另外把保底擺滿，begin_line），不然照固定的亂數偶爾就中了、情境走岔。"""
        oid = self.right_of(self.chars.load(who), right)
        if oid is None:
            emit(f"{who} 卡上沒有{'對' if right else '錯'}的做法可選", None)
            return
        with contextlib.ExitStack() as stack:
            stack.enter_context(self.roll_boost(who))
            if hit is not None:
                stack.enter_context(self.tweak(self.c.config, sense_rate_range=(100, 100) if hit else (0, 0), sense_marks_bonus=0))
            if hit:
                stack.enter_context(self.tweak(self.c.config.epiphany, chances=[1e-9] * 3))
            self.choose(who, oid)
        self.me(who, "選了做法之後")

    @contextlib.contextmanager
    def roll_boost(self, who: str):
        """擲特殊頓悟乘多少寫進輸出（epiphany.roll 包一層，兩份程式同一步換、同一步換回；骰子照常擲）。"""
        from tianxia import epiphany

        real = epiphany.roll

        def roll(state, content, rng, boost: float = 1.0):
            emit(f"{who} 擲特殊頓悟的倍數", boost)
            return real(state, content, rng, boost=boost)

        epiphany.roll = roll
        try:
            yield
        finally:
            epiphany.roll = real

    def seen(self, who: str, tag: str) -> None:
        """走一趟那一份（每一段的 after 在裡面）與有所感碰得到的那幾格。"""
        self.player_view(who, tag)
        self.me(who, tag)

    def trip_out(self, who: str) -> bool:
        """走一趟三段出發、第一段就撞上有所感停下來（抽到感悟；奇遇與頭目這一下不擲）。沒有走一趟的季寫「沒有」、回假。"""
        if self.main(who).get("outing") is None:
            emit(f"{who} 這一季沒有走一趟", None)
            return False
        self.place(who, self.spot)
        with self.draws(_explore_rules().INSIGHT), self.tweak(self.c.config, rare_explore_chance=0.0), \
                self.tweak(self.c.config.duel, explore_chance=0.0):
            self.do(who, "outing", {"n": 3})
        self.seen(who, "出發之後")
        return True

    def god_waiting(self, who: str, start) -> None:
        """start（站到有場景的那一處、撞上卡）之後保底中了特殊頓悟、拷問四題、靜候、心魔打贏，停在等著取名（還沒按靜心思名）。"""
        pity = self.c.config.epiphany.pity
        self.edit(who, lambda p: setattr(p, "epiphany_dry", pity))
        start(who)
        with self.trial("wait"):
            self.method(who, right=True, hit=True)
        with self.tweak(self.c.config.epiphany, trial_wait_days=0.0):
            self.answers(who)
            self.main(who)
        self.demon(who, "大勝")

    def stroke(self, who: str, name: bool) -> list | None:
        """畫哪一筆（glyph.SAMPLES 照屬性排第一個合的）：name 是要悟一個自己的新意境（要取名），否則落回這一處的基本意境。A 段只讀。"""
        from tianxia import glyph, sensing

        state = self.chars.load(who)
        for attr in sorted(glyph.SAMPLES):
            req = sensing.request(state, self.c, self.world, glyph.SAMPLES[attr])
            if not isinstance(req, str) and req.needs_name == name:
                return glyph.SAMPLES[attr]
        return None

    def paint(self, who: str, name: bool, png: str = "AAAA") -> None:
        """畫完那一筆送出（/api/sense：殼的三段式 A、B、C）。"""
        points = self.stroke(who, name)
        if points is None:
            emit(f"{who} 沒有{'要取名' if name else '落回基本意境'}的那一筆", None)
            return
        self.call(who, "POST", "/api/sense", {"points": points, "png": png})
        self.me(who, "畫完之後")

    def finish(self, who: str, rounds: int = 6) -> None:
        """眼前端出來的（事件卡、有所感、頭目）照第一顆按得下去的了結；有所感的感悟狀態一律順其自然（不按「畫下來」）。"""
        from tianxia import sensing

        for _ in range(rounds):
            opts = self.options(who)
            if "act:explore" in opts:
                return
            pick = sensing.LET_GO if sensing.LET_GO in opts else next(
                (i for pre in ("choice:", "sense:", "duel:") for i, o in opts.items()
                 if i.startswith(pre) and o.get("enabled") and i not in (sensing.DRAW, "duel:flee")), None)
            if pick is None:
                return
            self.choose(who, pick)

    @contextlib.contextmanager
    def trial(self, name: str):
        """這一次頓悟的小試照寫好的那一種（epiphany._trial 換掉；同 tianxia/features/sense/tests/test_epiphany.py 的 _begin）。"""
        from tianxia import epiphany

        real = epiphany._trial
        epiphany._trial = lambda state, content: (name, epiphany.TRIALS[name][0], -1)
        try:
            yield
        finally:
            epiphany._trial = real

    def begin_line(self, who: str, trial: str) -> None:
        """有所感選對、擲中，擲特殊頓悟：保底（這一季擲中感悟 pity 次都沒中，下一次必中，不動亂數）、小試照 trial。頓悟關著的季就停在感悟狀態。"""
        pity = self.c.config.epiphany.pity
        self.edit(who, lambda p: setattr(p, "epiphany_dry", pity))
        self.sensed(who)
        with self.trial(trial):
            self.method(who, right=True, hit=True)

    def answers(self, who: str, n: int = 4) -> None:
        """心靈拷問：照選單上第一個答案答 n 題（三題問心、一題心中之形）。"""
        for _ in range(n):
            pick = next((i for i, o in self.options(who).items() if i.startswith("story:") and ":a" in i and o.get("enabled")), None)
            if pick is None:
                emit(f"{who} 沒有要答的", None)
                return
            self.choose(who, pick)

    def demon(self, who: str, tier: str) -> None:
        """去面對心魔（story:<線> 那一顆，fight 段）：仗照寫好的 tier 打。"""
        fight = next((i for i, o in self.options(who).items() if i.startswith("story:") and i.count(":") == 1 and o.get("enabled")), None)
        if fight is None:
            emit(f"{who} 沒有心魔可以面對", None)
            return
        with self.fights(tier):
            self.choose(who, fight)
        self.me(who, f"心魔{tier}之後")

    def own_name(self, who: str, text: str):
        """神品意境自己取一個名字：/api/choose 帶 text（被擋時那一句回給表單）。"""
        return self.call(who, "POST", "/api/choose", {"id": "dunwu:own", "text": text})

    # ── 前半 ──

    def setup(self) -> None:
        Scenario.setup(self)  # 探索那一軌的 setup 另外擺它自己的人（高寄萍），這一軌不要

    def prologue(self) -> None:
        """草廬（不帶、weekend）：遇險、拜師、看修練頁，按探索——序章第 3 步的有所感版（舊探索開卡、做法都對、必中）；選第一個做法、
        順其自然。沒有草廬的季寫「沒有」。"""
        from tianxia import sensing

        who = self.NEWBIE
        view = self.main(who)
        if not view.get("prologue"):
            emit("這一季沒有序章", None)
            self.settle_choices(who)
            return
        self.choose(who, "choice:0")
        self.choose(who, "choice:0")
        self.do(who, "view_tab", {"tab": "practice"})
        self.choose(who, "act:explore")
        self.me(who, "草廬的有所感")
        senses = [i for i, o in self.options(who).items() if i.startswith("sense:") and i != sensing.LET_GO and o.get("enabled")]
        if senses:
            self.choose(who, senses[0])
        self.main(who)
        self.choose(who, sensing.LET_GO)
        self.me(who, "草廬悟到之後")

    def meet(self) -> None:
        """探索撞上有所感：卡上的做法、做法底下的兩行小字（sense_help）、場景；選對、擲中（感悟狀態：畫下來、順其自然）、順其自然。"""
        from tianxia import sensing

        who = "石觀潮"
        self.sensed(who)
        self.main(who)
        self.method(who, right=True, hit=True)
        self.main(who)
        self.choose(who, sensing.LET_GO)
        self.me(who, "順其自然之後")

    def miss(self) -> None:
        """選錯做法（這一處到換日之前悟不出：三選一的「靜心感悟」灰掉、舊探索那一行補一句；一類一顆給心得）、再探索一次（照它自己抽）；
        選對沒擲中（給一點心得）。"""
        who = "晏棲遲"
        self.sensed(who)
        self.method(who, right=False, hit=None)
        self.place(who, self.spot)
        self.main(who)
        self.choose(who, "act:explore")
        self.finish(who)
        self.me(who, "選錯之後再探索")
        who = "穆青梧"
        self.sensed(who)
        self.method(who, right=True, hit=False)

    def canvas(self) -> None:
        """自己畫一筆：「畫下來」只叫出畫布、暖機、讀筆畫（讀得出、只點了一下、格式不對）、送一筆讀不出的、畫一筆落回基本意境、畫完再送；
        江照晚畫一筆要取名的（模型擋著：退路字表、不記首悟）。"""
        from tianxia import glyph, sensing

        who = "韋寒汀"
        self.sensed(who)
        self.method(who, right=True, hit=True)
        self.choose(who, sensing.DRAW)
        self.call(who, "POST", "/api/sense_warm")
        self.call(who, "POST", "/api/sense_read", {"points": glyph.SAMPLES[sorted(glyph.SAMPLES)[0]]})
        self.call(who, "POST", "/api/sense_read", {"points": [[1, 1, 0]]})
        self.call(who, "POST", "/api/sense_read", {"points": "x"})
        self.call(who, "POST", "/api/sense", {"points": [[1, 1, 0]], "png": ""})
        self.paint(who, name=False)
        self.call(who, "POST", "/api/sense", {"points": glyph.SAMPLES[sorted(glyph.SAMPLES)[0]], "png": ""})
        who = "江照晚"
        self.sensed(who)
        self.method(who, right=True, hit=True)
        self.paint(who, name=True)

    def named(self) -> None:
        """假模型取名：祁問山畫一筆要取名的（看圖拿到名字：記首悟「你是第一個」）；賀知秋同一處、同一個做法、同一筆（不是第一個）。"""
        MODEL["sense"] = True
        try:
            for who in ("祁問山", "賀知秋"):
                self.sensed(who)
                self.method(who, right=True, hit=True)
                self.paint(who, name=True)
        finally:
            MODEL["sense"] = False

    def epiphany(self) -> None:
        """顧折柳：保底中了特殊頓悟、拷問四題、靜候（trial_wait_days 擺 0）、心魔打贏、靜心思名（模型擋著：字表補三個）、自己寫沒帶字、挑第一個。"""
        from tianxia import sensing

        who = "顧折柳"
        self.begin_line(who, "wait")
        if not self.epiphany_on():
            emit("這一季沒有特殊頓悟", None)
            self.choose(who, sensing.LET_GO)
            return
        with self.tweak(self.c.config.epiphany, trial_wait_days=0.0):
            self.answers(who)
            self.main(who)
        self.demon(who, "大勝")
        self.choose(who, "dunwu:think")
        self.choose(who, "dunwu:own")
        self.choose(who, "dunwu:0")
        self.me(who, "取名之後")

    def demon_lost(self) -> None:
        """蘇停雲：拷問、探訪三回、心魔打輸（「心魔未破」的卡掛著——前半停在這裡）；陸聞箏：拷問、打贏一場（探索的遭遇）、心魔打贏，
        停在等著取名（還沒按靜心思名）。"""
        from tianxia import sensing

        explore_one = _explore_rules()
        for who, trial in (("蘇停雲", "roam"), ("陸聞箏", "win")):
            self.begin_line(who, trial)
            if not self.epiphany_on():
                emit("這一季沒有特殊頓悟", None)
                self.choose(who, sensing.LET_GO)
                continue
            self.answers(who)
            kinds, tier = ((explore_one.MATERIAL,) * 3, None) if trial == "roam" else ((explore_one.ENCOUNTER,), "大勝")
            for kind in kinds:
                self.place(who, self.spot)
                with self.draws(kind), self.fights(tier):
                    self.choose(who, "act:explore")
                self.finish(who)
            self.main(who)
            self.demon(who, "落敗" if trial == "roam" else "大勝")
            self.main(who)

    def pending(self) -> None:
        """寫到一半的：紀守拙停在選做法、裴映雪停在感悟狀態；溫行簡的頓悟答了一題就擱著（到季末沒了結）。"""
        self.sensed("紀守拙")
        self.sensed("裴映雪")
        self.method("裴映雪", right=True, hit=True)
        who = "溫行簡"
        self.begin_line(who, "wait")
        if self.epiphany_on():
            self.answers(who, 1)
        self.me(who, "答了一題")

    def trip_first(self) -> None:
        """走一趟寫到一半（舊程式存下那一趟、新程式接著做完）：岑望舒選對擲中停在感悟狀態、杜聽瀾停在卡上、俞照川等著取名（頓悟開著的季）；
        褚臨風閒著撞上一張卡停著（後半人被帶走）。"""
        if self.trip_out("岑望舒"):
            self.method("岑望舒", right=True, hit=True)
            self.seen("岑望舒", "選了做法")
        self.trip_out("杜聽瀾")
        if self.main("俞照川").get("outing") is not None and self.epiphany_on():
            self.god_waiting("俞照川", self.trip_out)
            self.seen("俞照川", "心魔之後")
        self.sensed("褚臨風")

    def half(self) -> None:
        for who in [self.NEWBIE, *self.PLAYERS]:
            self.me(who, "前半停下")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def trip_on(self) -> None:
        """新程式接手停著的一趟：畫一筆（sense_draw）、畫一筆要取名的（假模型）、順其自然、靜心思名（epiphany_names）；做完接著走。"""
        from tianxia import sensing

        who = "岑望舒"
        if self.main(who).get("outing") is None:
            emit("這一季沒有走一趟", None)
            return
        self.paint(who, name=False)
        self.seen(who, "畫完")
        self.do(who, "outing", {})
        self.seen(who, "接著走")
        who = "杜聽瀾"
        self.method(who, right=True, hit=True)
        MODEL["sense"] = True
        try:
            self.paint(who, name=True)
        finally:
            MODEL["sense"] = False
        self.seen(who, "畫完要取名")
        who = "辛遠岫"
        self.trip_out(who)
        self.method(who, right=True, hit=True)
        self.choose(who, sensing.LET_GO)
        self.seen(who, "順其自然")
        who = "俞照川"
        if not self.epiphany_on():
            emit("這一季沒有特殊頓悟", None)
            return
        MODEL["sense"] = True
        try:
            self.choose(who, "dunwu:think")
        finally:
            MODEL["sense"] = False
        self.seen(who, "思名之後")
        self.choose(who, "dunwu:0")
        self.seen(who, "取名之後")
        self.do(who, "outing", {})
        self.seen(who, "接著走")

    def trip_gains(self) -> None:
        """走一趟停在卡上，悟的那一下與思名的那一下多帶一行料（sensing.finish、epiphany.fill 包一層，兩份程式同一步換、同一步換回）：
        outing_watch 要把它記在那一段（beat.after）。沒有這一行的話一般的一筆與思名什麼都不記，看不出那一層在不在。"""
        from tianxia import epiphany, journal, materials, sensing

        who = "計南枝"
        if self.main(who).get("outing") is None:
            emit("這一季沒有走一趟", None)
            return
        self.trip_out(who)
        self.method(who, right=True, hit=True)
        real_finish = sensing.finish

        def finish(*args, **kwargs):
            msgs, own, by_model = real_finish(*args, **kwargs)
            return [*msgs, f"{materials.GRANT_PREFIX}寒鐵屑 ×1"], own, by_model

        sensing.finish = finish
        try:
            self.paint(who, name=False)
        finally:
            sensing.finish = real_finish
        self.seen(who, "畫完帶料")
        who = "盧半溪"
        if not self.epiphany_on():
            emit("這一季沒有特殊頓悟", None)
            return
        self.god_waiting(who, self.trip_out)
        real_fill = epiphany.fill

        def fill(state, *args, **kwargs):
            msgs = real_fill(state, *args, **kwargs)
            journal.add_entry(state, journal.Draft("思名").entry(state.world.time, [f"{materials.GRANT_PREFIX}寒鐵屑 ×1"]))
            return msgs

        epiphany.fill = fill
        MODEL["sense"] = True
        try:
            self.choose(who, "dunwu:think")
        finally:
            MODEL["sense"] = False
            epiphany.fill = real_fill
        self.seen(who, "思名帶料")

    def stale_on(self) -> None:
        """褚臨風手上一張卡（舊程式存下的）、人被帶走：下一次讀檔清掉作廢的卡（_drop_stale_references 中段），選單不卡。"""
        who = "褚臨風"
        other = next(i for i in sorted(self.c.locations) if i != self.spot)
        self.edit(who, lambda p: setattr(p, "location", other))
        self.main(who)
        self.me(who, "人被帶走之後")

    def clears(self) -> None:
        """費疏影畫完那一筆清掉上一次的引導行與戰報卡（這條路不走 choose）。戰報擺一筆真的（id 不在戰報裡的話讀檔就清掉了，看不出差別）。"""
        from tianxia.state import BattleRecord

        who = "費疏影"
        self.sensed(who)
        self.method(who, right=True, hit=True)

        def dirty(state) -> None:
            state.player.guide_done = ["上一次的引導行"]
            state.battles.insert(0, BattleRecord(id=987654, time=state.world.time, location="河畔", kind="wild", opponent="流寇", ours=[],
                                                 tier="大勝", our_power=1, difficulty=1))
            state.battle_card = 987654

        self.edit_state(who, dirty)
        self.paint(who, name=False)
        state = self.chars.load(who)
        emit(f"{who} 畫完清掉", {"guide_done": list(state.player.guide_done), "battle_card": state.battle_card})

    def preparing(self) -> None:
        """賽季籌備中（Game._preparing 換成真，兩份程式同一步換、同一步換回）：阮晴川畫一筆被擋（sense_request）、涂松聲靜心思名不開單（epiphany_request）。"""
        from tianxia import glyph
        from tianxia.engine import Game

        who, namer = "阮晴川", "涂松聲"
        self.sensed(who)
        self.method(who, right=True, hit=True)
        waiting = self.epiphany_on()
        if waiting:
            self.god_waiting(namer, self.sensed)
        real = Game._preparing
        Game._preparing = lambda game: True
        try:
            self.call(who, "POST", "/api/sense", {"points": glyph.SAMPLES[sorted(glyph.SAMPLES)[0]], "png": ""})
            if waiting:
                self.choose(namer, "dunwu:think")
        finally:
            Game._preparing = real
        self.me(who, "籌備中畫")
        if waiting:
            self.me(namer, "籌備中思名")

    def pending_on(self) -> None:
        """新程式接手寫到一半的：紀守拙選對、擲中、順其自然；裴映雪先在鎖裡直接開單、人走開再交回（C 段重驗對不上，不存），再照常畫一筆。"""
        from tianxia import glyph, sensing
        from tianxia.engine import Game

        who = "紀守拙"
        self.main(who)
        self.method(who, right=True, hit=True)
        self.choose(who, sensing.LET_GO)
        self.me(who, "新程式接手之後")
        who = "裴映雪"
        with self.world.action_lock():
            g = Game(self.c, self.chars.load(who), random.Random(0), self.world)
            req = g.sense_request(glyph.SAMPLES[sorted(glyph.SAMPLES)[0]])
            emit(f"{who} 直接開單", req if isinstance(req, str) else req.model_dump(mode="json"))
            if not isinstance(req, str):
                g.state.player.location = next(i for i in sorted(self.c.locations) if i != self.spot)
                emit(f"{who} 人走開了再交回", g.sense_draw(req, ("寒潭孤月", "")))
        self.paint(who, name=False)

    def demon_on(self) -> None:
        """蘇停雲：收下「心魔未破」的卡、到了再打的時候（retry_at 擺回去，同時間過了）、心魔打贏、靜心思名（假模型取三個）、
        自己寫不合格的（那一句回給表單）、合格的。"""
        who = "蘇停雲"
        if not self.epiphany_on():
            emit("這一季沒有特殊頓悟", None)
            return
        self.do(who, "story_seen")

        def due(s) -> None:
            for progress in s.player.storylines.values():
                if progress.retry_at is not None:
                    progress.retry_at = 0.0
        self.edit_state(who, due)
        self.main(who)
        self.demon(who, "大勝")
        MODEL["sense"] = True
        try:
            self.choose(who, "dunwu:think")
        finally:
            MODEL["sense"] = False
        self.own_name(who, "ab")
        self.own_name(who, SENSE_OWN[0])
        self.me(who, "取名之後")

    def naming_on(self) -> None:
        """陸聞箏：自己寫一個這一季已經有人用掉的名字（擋下來、那一句回給表單）、換一個。"""
        who = "陸聞箏"
        if not self.epiphany_on():
            emit("這一季沒有特殊頓悟", None)
            return
        self.main(who)
        self.own_name(who, SENSE_OWN[0])
        self.own_name(who, SENSE_OWN[1])
        self.me(who, "取名之後")

    def bots(self) -> None:
        """伺服器假人（BotRunner＋bot_policy.take_turn，random.Random(17)、時鐘一輪推四步）：四個站在有場景的那一處——悟甲停在有所感的卡、
        悟乙停在感悟狀態、悟丙等著取名（頓悟開著的季：模板挑第一個）、悟丁閒著。假人程式帶一個假模型（取名的 B 段：SenseJob、EpiphanyJob）。
        整季機器人（bot.pick）在悟甲那張卡上挑哪一顆也寫下來。"""
        from collections import Counter

        from tianxia import bot, ollama_client, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile, GodNaming

        loc = self.c.locations[self.spot]
        god = next(iter(self.c.traits.god), None) if self.epiphany_on() else None
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=71 + i, faction=None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):  # 開局待選的事件：選掉
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.location, p.journey = self.spot, None
            p.visited.add(self.spot)
            p.joined_at = -1.0e9
            p.stats["silver"] = 200
            if i in (0, 1):
                emit(f"假人 {name} 撞上有所感", g._sense_here(loc, random.Random(31 + i)))
            if i == 1:
                oid = self.right_of(g.state)
                if oid is not None:
                    with self.tweak(self.c.config, sense_rate_range=(100, 100), sense_marks_bonus=0), \
                            self.tweak(self.c.config.epiphany, chances=[1e-9] * 3):
                        emit(f"假人 {name} 選了做法", g.choose(oid))
            if i == 2 and god is not None:
                p.god_naming = GodNaming(line="頓悟1", god=god.id, attribute=god.attribute, lean=god.lean, place=loc.name)
            if i == 0:
                emit("整季機器人在有所感的卡上挑", bot.pick(g, g.options(odds=False), random.Random(0)))
            self.chars.save(g.state)
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {71 + i for i in range(len(self.BOT_SEATS))}
        MODEL["sense"] = True
        totals = Counter()
        try:
            client = ollama_client.OllamaClient.from_config(self.c.config)
            runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(17), clock=lambda: CLOCK[0], client=client)
            self.c.config.bot_tick_seconds = 10 ** 6  # 在線的假人每一輪都動
            server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
            for _ in range(int(os.environ.get("SB_SENSE_TICKS", "24"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online,
                              named=report.named)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
            MODEL["sense"] = False
        emit("有所感假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"有所感假人 {name}", {
                "sensing": None if p.sensing is None else p.sensing.model_dump(mode="json"), "insights": list(p.insights),
                "own": {k: v.name for k, v in sorted(p.own_insights.items())},
                "god": None if p.god_naming is None else p.god_naming.model_dump(mode="json"),
                "journal": [e.title for e in s.journal[:4]], "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})

    def season(self) -> None:
        """收季、開下一季：石觀潮又撞上一張卡沒了結、溫行簡的頓悟沒了結（此事未了）；換季之後有所感與頓悟的欄位跟著新角色重來。"""
        self.sensed("石觀潮")
        self.do(ADMIN, "end_season")
        for who in ("石觀潮", "溫行簡"):
            self.main(who)
        self.do(ADMIN, "next_season")
        for who in ("石觀潮", "溫行簡", "祁問山", "顧折柳", "蘇停雲"):
            self.main(who)
            self.me(who, "換季之後")


# 改一個字（selftest）：「畫下來」只叫出畫布那一句（搬之前在 engine.py 的 choose、之後在 features/sense/actions.py）
register_track("sense", SenseScenario, (("tianxia/features/sense/actions.py", "tianxia/engine.py"),
                                         ("（在畫布上一筆畫下心中的形。）", "（在畫布上一筆畫下心中的形！）")), "week7")
