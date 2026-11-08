"""same_behavior 一軌一檔：aftermath（這一檔登記 aftermath）。"""
from __future__ import annotations

import contextlib

from sb.base import Scenario
from sb.harness import ADMIN, emit, register_track
from sb.tracks.events import EventScenario
from sb.tracks.explore import _explore_rules
from sb.tracks.roam import RoamScenario

# ═══════════════════════════ aftermath：單打服務打完之後那幾條岔路（第二輪第 79 批，dev/combat） ═══════════════════════════
# 第 79 批把 Game 上的單打服務（大場面、收場、操練與立功、戰力快照、本人對本人）搬進 tianxia/core/combat.py。開工量過全部的軌
# 三種設定走到這 40 個方法的哪幾行：39 個都有軌走到，只差 _fight_gone（一次都沒有）與一串岔路。這一軌專走那些岔路：
# 等判讀的時候選項沒了（「你離開了」「情勢變了」）、大場面按不下去、滿級與 45 級的經驗換心得（戰報那一支、守那一支）、
# 落敗保住銀兩（金角、策馬脫身）、厚的演出句、天下聞名點名、遭遇拍掉落打折、寶物多掉一個、三階關著、立功關著、江湖水漲。
# **半舊半新切在大場面的事件卡擺在眼前、還沒打的那一刻**（一位帶傷、一位滿級）：舊程式擺卡、新程式打。
# 假人走事件那一軌的 bots（要打的卡也在裡面，假人 client=None，走同一批方法）。
# 這一軌走不到的（量過）：fight_request 的序章雪恥（三種設定都沒有序章）；_record_exp 沒滿級卻換心得（現在叫它的來源全是仗）；_tier3 發素材失敗。
# 角色與名字都是原創的（PM 11/04）。


def _combat_choice(ch) -> bool:
    return ch.combat is not None


class AftermathScenario(EventScenario):
    """單打服務的岔路（--track aftermath，自己一個資料庫）。小工具借事件那一軌（card、press、me、judged、combat）與探索那一軌（draws、fights、tweak）。"""

    GUARD_MAXED = "溫苓"  # 黃巾：滿級守大本營
    GUARD_GATED = "季懷章"  # 黃巾：46 級守大本營（減法季 45 級的閘）
    PLAYERS = {"岑遠山": None, "柏雲舟": None, "顧霜橋": None, "裴硯秋": None, "邵寒汀": None, "甘棠影": None, "喬聽松": None,
               GUARD_MAXED: "huang", GUARD_GATED: "huang", "寧子衿": None, "駱清和": None, "聞人棹": None, "左丘禾": None}
    NEWBIE = "白露生"
    BOT_SEATS = [("後甲", "yingshui"), ("後乙", "julu_altar"), ("後丙", "guangzong"), ("後丁", "market_town")]
    PHASES_FIRST = ["setup", "gone", "capped", "half"]
    PHASES_SECOND = ["resume", "wake", "thick", "keep_silver", "bolt", "famed", "thin", "extra", "no_tier3", "no_deed", "tide",
                     "snapshots", "bots", "season"]
    only = RoamScenario.only

    # ── 小工具 ──

    def field(self) -> str:
        """打一場隊伍的地方：同絕學契機那一段（arts）：地盤季的中立荒野，沒有地盤的季遊歷打得到人的地方。"""
        from tianxia import territory

        return "runan_wilds" if territory.on(self.c) else ("lake" if self.profile == "test" else "changshe")

    def town(self) -> str | None:
        """探索抽到遭遇一定打得起來的地方：城裡的地痞（地盤季）；舊探索的城裡沒有野怪，站到遊歷打得到人的地方。"""
        from tianxia import territory

        return next((loc for kind, loc in self.kind_places() if kind == _explore_rules().TOWN), None) if territory.on(self.c) else self.field()

    @contextlib.contextmanager
    def no_duel(self):
        """約戰關著（開著的季按出陣只打開那張卡）：做完擺回，前半、後半接得上。"""
        self.set_duel(False)
        try:
            yield
        finally:
            self.set_duel(True)

    @contextlib.contextmanager
    def meddled(self, fn):
        """鎖外判讀的那一下（server.prepare_fight 的 B 段）順手改存檔：等模型的時候別的分頁把人帶走、事件被了結。"""
        from tianxia import fight_llm

        real = fight_llm.judge

        def judge(*args, **kwargs):
            out = real(*args, **kwargs)
            fn()
            return out

        fight_llm.judge = judge
        try:
            yield
        finally:
            fight_llm.judge = real

    @contextlib.contextmanager
    def dropping(self):
        """這幾下一定掉一種素材（五個）：打折、寶物多掉一個都要這一場真的掉了東西；掉哪一種照 id 排第一個。"""
        from tianxia import materials

        real, mid = materials.roll_squad_drops, sorted(self.c.materials)[0]

        def roll(*args, **kwargs):
            return [(mid, 5)]

        materials.roll_squad_drops = roll
        try:
            yield
        finally:
            materials.roll_squad_drops = real

    def fight_field(self, who: str, tier: str | None) -> None:
        """打一場隊伍（_squad_encounter）：地盤季散人不能出陣，站到官軍那邊；沒有陣營的內容照舊。"""
        with self.no_duel():
            if self.place(who, self.field(), faction="guan" if self.c.scenario.factions else "keep"):
                with self.fights(tier):
                    self.choose(who, "act:train")
        self.me(who, f"打一場（{tier}）之後")

    def fight_card(self, who: str, tag: str, tier: str | None = "大勝") -> None:
        if self.card(who, self.combat()):
            with self.fights(tier):
                self.press(who, _combat_choice, tag)
        self.me(who, f"{tag}之後")

    def wild_fight(self, who: str, where: str | None, tier: str | None = "大勝") -> None:
        """探索抽到遭遇（野怪：record.kind 是 wild）；舊探索的季落在野怪那一支。"""
        explore_one = _explore_rules()

        if self.place(who, where):
            with self.only("wild"), self.draws(explore_one.ENCOUNTER), self.fights(tier), self.dropping(), self.tweak(self.c.config, rare_explore_chance=0.0):
                self.seek(who)
        self.me(who, "遭遇之後")

    # ── 前半 ──

    def setup(self) -> None:
        Scenario.setup(self)
        if self.c.scenario.factions:
            self.place(self.GUARD_MAXED, None, faction="huang")
            self.place(self.GUARD_GATED, None, faction="huang")

    def gone(self) -> None:
        """大場面 C 段（Game._fight_gone）：判讀的那一下人被帶走（選項沒了、地點變了：你離開了）、事件被了結（地點沒變：情勢變了）。
        /api/choose 回的那一句（server.api_choose 看 FIGHT_GONE_LINES）。"""
        ev = self.combat()
        with self.judged():
            who = "寧子衿"
            if self.card(who, ev):
                here = self.chars.load(who).player.location
                away = next(i for i in sorted(self.c.locations) if i != here)

                def carried(state):
                    state.pending_event = None
                    state.player.location = away

                with self.meddled(lambda: self.edit_state(who, carried)):
                    self.press(who, _combat_choice, "等判讀的時候人走了")
            self.me(who, "人走了之後")
            who = "駱清和"
            if self.card(who, ev):
                with self.meddled(lambda: self.edit_state(who, lambda s: setattr(s, "pending_event", None))):
                    self.press(who, _combat_choice, "等判讀的時候事件了結了")
            self.me(who, "事件了結之後")

    def capped(self) -> None:
        """經驗換心得：滿級打一場（_record_exp 滿級那一支）；滿級、46 級守黃巾大本營（只有那裡駐著自家那一路：_drill_gains、
        _exp_changes，守不是仗，過 45 級的閘）。"""
        cap = self.c.config.max_level
        who = "甘棠影"
        self.edit(who, lambda p: setattr(p.member, "level", cap))
        self.fight_card(who, "滿級打一場")
        if not self.contested("huangjin_camp"):
            emit("這一季沒有地盤，不守", None)
            return
        with self.no_duel():
            for name, level in ((self.GUARD_MAXED, cap), (self.GUARD_GATED, min(46, cap - 1))):
                self.edit(name, lambda p, n=level: setattr(p.member, "level", n))
                if self.place(name, "huangjin_camp"):
                    emit(f"{name} 大本營的 act:train", self.ids(self.main(name)).get("act:train"))
                    self.choose(name, "act:train")
                self.me(name, f"{level} 級守之後")

    def half(self) -> None:
        """半舊半新的切點：兩張要打的大場面事件卡擺在眼前，邵寒汀帶傷，裴硯秋滿級。"""
        ev = self.combat()
        self.edit("邵寒汀", lambda p: setattr(p.member, "neili", 1.0))
        self.card("邵寒汀", ev)
        self.edit("裴硯秋", lambda p: setattr(p.member, "level", self.c.config.max_level))
        self.card("裴硯秋", ev)

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def wake(self) -> None:
        """新程式接手前半擺好的卡：帶傷的大場面（判讀、落敗）、滿級的（判讀、打贏）。"""
        with self.judged():
            for who, tier in (("邵寒汀", "落敗"), ("裴硯秋", "大勝")):
                with self.fights(tier):
                    self.press(who, _combat_choice, f"接著打（{tier}）")
                self.me(who, f"接著打（{tier}）之後")

    def thick(self) -> None:
        """厚的演出句（_trait_lines：身上的武學帶 condition_floor、開打前氣血低於上限）。
        造法同 tests/core/test_engine.py 的 _wear_trait_art：全服登記一門、穿上。"""
        from tianxia import arts as arts_mod
        from tianxia.martial_arts import Insight, generate_from_name

        who = "柏雲舟"

        def wear(state):
            p = state.player
            iid = "悟:柏氏厚土"
            p.own_insights[iid] = Insight(id=iid, name="柏氏厚土", attribute="實")
            p.insight_strength[iid] = 1
            p.insights = [*p.insights, iid]
            art = generate_from_name("柏氏厚土拳", "武學", "柏氏厚土拳", attribute="實").model_copy(
                update={"origin": "fused", "affinity": ["實"], "slot_adjust": max(0, 1 - arts_mod.slot_count(self.c, "下品"))})
            self.world.claim_skill_name(art)
            p.art_slots[art.id] = [iid]
            p.member.wugong_id = art.id
            p.art_quality[art.id] = "下品"
            p.member.neili = 1.0

        self.edit_state(who, wear)
        self.fight_field(who, "落敗")

    def keep_silver(self) -> None:
        """金角落敗不失銀兩（_lose_silver 第一支）：管理者把這一片指給他、改版開著。"""
        who = "邵寒汀"
        if "jinjiao" not in self.c.seal:
            emit("這份內容沒有金角", None)
            return
        self.do(ADMIN, "seal_assign", {"id": "jinjiao", "name": who, "state": "held"})
        self.edit(who, lambda p: p.stats.__setitem__("silver", 100))
        with self.tweak(self.c.config.seal, enabled=True), self.tweak(self.c.config.seal.revamp, enabled=True):
            self.fight_field(who, "落敗")
        self.do(ADMIN, "seal_assign", {"id": "jinjiao", "name": "", "state": "hidden"})

    def bolt(self) -> None:
        """策馬脫身（_lose_silver 第二支；自己一份亂數）：騎著馬、脫身的機會換成 1。"""
        from tianxia import mounts

        who = "顧霜橋"

        def ride(state):
            state.player.mount = mounts.new_mount(state, name="試蹄", tier=3, quality="中品")
            state.player.stats["silver"] = 100

        self.edit_state(who, ride)
        with self.tweak(self.c.config.mounts, enabled=True, escape={"1": 1.0, "2": 1.0, "3": 1.0}):
            self.fight_field(who, "落敗")

    def famed(self) -> None:
        """天下聞名打大場面點名（_famed_news）：名望擺到頂，打一張大場面的卡。"""
        who = "岑遠山"
        self.edit(who, lambda p: p.stats.__setitem__("fame", 10 ** 6))
        with self.judged():
            self.fight_card(who, "天下聞名打大場面")

    def thin(self) -> None:
        """遭遇拍掉的素材打折（_thin_drops：城裡的地痞）。"""
        self.wild_fight("聞人棹", self.town())

    def extra(self) -> None:
        """寶物多掉一個素材（_battle_rewards 那一支：拾遺囊，機會換成 1）。"""
        from tianxia import treasures

        who = "左丘禾"
        tid = next((t for t, d in sorted(self.c.gear.treasures.items()) if d.effect == "win_material"), None)
        if tid is None:
            emit("這份內容沒有多掉素材的寶物", None)
            return
        self.edit_state(who, lambda s: setattr(s.player, "treasure", treasures.new_treasure(s, self.c, tid)))
        cfg = self.c.config.treasures
        with self.tweak(cfg, enabled=True, effects={**cfg.effects, "win_material": 1.0}):
            self.wild_fight(who, self.town())

    def no_tier3(self) -> None:
        """大場面另擲三階，機會是 0（_tier3 第一句就回）。"""
        with self.judged(), self.tweak(self.c.config.forge_secrets, big_tier3=0.0):
            self.fight_card("裴硯秋", "三階關著的大場面")

    def no_deed(self) -> None:
        """立功給名望，那一項寫 0（_deed_fame 第一句就回）：地盤季在中立地出陣打贏。"""
        with self.tweak(self.c.config.renown, deeds={}):
            self.fight_field("喬聽松", "大勝")

    def tide(self) -> None:
        """江湖水漲開著的劇情戰（_story_squad：大場面照水漲浮上來；五項屬性的季水漲是關著的，走不到那一句）。"""
        with self.judged(), self.tweak(self.c.config.rise, enabled=True):
            self.fight_card("甘棠影", "水漲的大場面")

    def snapshots(self) -> None:
        """加入決戰那一刻的戰力快照與本人對本人（只讀，直接問 Game）：騎馬的、帶部下的、帶傷的各問一遍。"""
        fid = next(iter(sorted(self.c.followers)), None)
        if fid is not None:
            self.edit("寧子衿", lambda p: setattr(p, "followers", [fid, fid]))
        for who in ("顧霜橋", "寧子衿", "柏雲舟"):
            self.begin()
            g = self.server.game_for(who)
            emit(f"{who} 戰力快照", {
                "power": [g._battle_power(), g._battle_power(seal=False)],
                "scores": [g._battle_scores(), g._battle_scores(mounted=False), g._battle_scores(seal=False)],
                "role": g._battle_role(), "troops": g._battle_troops(), "gear": str(g._battle_gear()), "marks": str(g._battle_marks()),
                "road": g._battle_road(), "cap": g._battle_neili_cap(), "hp": list(g._player_hp_and_cap()), "facts": str(g._hp_facts()),
            })
        self.begin()
        a, b = self.server.game_for("顧霜橋"), self.server.game_for("柏雲舟")
        emit("本人對本人", [a._spar_power(a, b), a._spar_power(b, a), a._spar_power(a, b, seal=False)])
        client, a.client = a.client, None  # 不叫模型的角色（假人）：大場面的單子一律不開
        emit("不叫模型的角色的單子", a.fight_request("act:train"))
        a.client = client

    def season(self) -> None:
        """收季、開下一季：單打服務沒有換季的帳，看的是換季之後照舊打得起來。"""
        self.do(ADMIN, "end_season")
        self.main("岑遠山")
        self.do(ADMIN, "next_season")
        self.main("岑遠山")
        self.settle_choices("岑遠山")
        self.fight_field("岑遠山", "大勝")


# 改一個字（selftest）：等判讀的時候人被帶走那一句（搬之前在 engine.py、之後在 tianxia/core/combat.py），gone 那一段抓到
register_track("aftermath", AftermathScenario, (("tianxia/core/combat.py", "tianxia/engine.py"),
                                                 ("你離開了，這一仗沒打成。", "你離開了，這一仗沒打成！")), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "figure_acts", "gear", "guide", "heroines", "hire", "legacy", "looks", "mall", "military", "outlets",
                       "peers", "seal", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story", "tavern", "travel",
                       "zhuan"))
