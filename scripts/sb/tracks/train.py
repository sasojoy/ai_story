"""same_behavior 一軌一檔：train（這一檔登記 train）。"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import random
from pathlib import Path

from sb.base import DUEL_PROFILES, Scenario
from sb.harness import ADMIN, BUF, CLOCK, CLOCK0, MODEL, _setup_child, db_text, emit, register_bots, register_track

# ═══════════════════════════ sortie（全部拆包第 17 批「出陣三」，dev/sortie-3）：train 一軌 ═══════════════════════════
# 序章雪恥、舊遊歷、跟自家隊伍操練、守勢（act:duty）、遊歷推大勢收進出陣包（計畫 docs/superpowers/plans/2026-11-01-出陣包-第3批.md）。


class TrainScenario(Scenario):
    """出陣三（--track train，自己一個資料庫）：act:train 那一格的另一半與守勢。
    - 序章雪恥（none、weekend 有序章）：照寫好的險勝；另一個新人把那一步的結果在記憶體裡換成落敗（打輸那一支）。
    - 舊遊歷（地盤關著的 none、test）：散人在長社（必敗先問、打輸、照寫好的打贏推大勢與戰後事件）、潁水河畔（不推大勢）；地盤開著的季是灰格。
    - 跟自家隊伍操練：none 的官軍大營（全是自己人「操練・零風險」）、南陽郊野（兩種都有）、黃巾別部營寨；test 把湖邊的水寇記憶體裡換成官軍；
      地盤開著的季（weekend 倍數 1、season21、week7 小於 1）把汝南荒野的對手記憶體裡換成自家的，出陣攻打撞上自己人改操練（推大勢走 _drill_push）；
      兩種都有：汝南荒野的中立駐軍在記憶體裡多塞一路自家的（原本那一路照舊是外人）。
    - 遊歷推大勢：官軍照寫好的打贏兩下（減法季關著的 none、test；減法季開著的 season21、week7 由上面的操練推），每一下寫各線與零頭。
    - 並肩出陣（_act 的 train 那一支包在外面的）：沒商量、商量沒成、商量成了。
    - 大場面判讀：舊遊歷的 _train_pick、操練不判、約戰開著不判、出陣照判。
    - 守勢（weekend、season21、week7）：一天第一次（前半）、同一天第二次（後半第一件事：新程式接舊程式記到一半的那一天）、中立地灰著、
      weekend 次數用完灰著、約戰開著隔天照記。約戰開著的季按一次出陣那一格（卡）。
    半舊半新切在雪恥打完、還沒配點，與守勢一天記了一次的那一刻。"""

    PLAYERS = {"官甲": "guan", "官乙": "guan", "黃甲": "huang"}
    RANGER = "遊俠"
    NEWBIES = ("雪恥甲", "雪恥乙")
    PHASES_FIRST = ["setup", "hut_win", "hut_lose", "duty_first"]
    PHASES_SECOND = ["duty_second", "hut_after", "resume", "wander", "drill", "push", "backed", "judge", "duty_more", "card"]

    def setup(self) -> None:
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
        self.do(ADMIN, "open_season")
        for who in [*self.NEWBIES, self.RANGER, *self.PLAYERS]:
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                    "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
        for who in [self.RANGER, *self.PLAYERS]:
            self.do(who, "skip_tutorial")
            self.settle_choices(who)
        factions = {f.id: f for f in self.c.scenario.factions}
        for who, side in self.PLAYERS.items():
            if side not in factions or not factions[side].join_at or not self.place(who, factions[side].join_at[0]):
                continue
            self.choose(who, f"faction:{side}")
            self.choose(who, "faction:confirm")
            self.settle_choices(who)
        for who in [self.RANGER, *self.PLAYERS]:
            self.place(who, None)  # 體力補滿、過了新手期

    # ── 小工具 ──

    def state_of(self, who: str, tag: str) -> None:
        """存檔裡跟遊歷、操練、守勢有關的那幾格與最新那一則紀錄。"""
        state = self.chars.load(who)
        p = state.player
        latest = state.journal[0] if state.journal else None
        emit(f"{who} {tag}", {
            "stamina": p.stamina, "silver": p.stats.get("silver"), "xinde": p.stats.get("xinde"), "exp": p.member.exp,
            "level": p.member.level, "injury": p.member.injury, "sortie_day": p.sortie_day, "sorties_today": p.sorties_today,
            "duty_day": p.duty_day, "duties_today": p.duties_today, "contrib": p.contrib, "pushed": dict(sorted(p.pushed.items())),
            "pending": state.pending_event, "step": p.tutorial_step, "battles": len(state.battles),
            "latest": None if latest is None else latest.model_dump(mode="json"),
        })

    def trends(self, tag: str) -> None:
        s = self.world.get_season()
        emit(f"大勢 {tag}", {"trends": dict(sorted(s.trends.items())), "accum": dict(sorted(s.trend_accum.items()))})

    def today(self) -> int:
        """此刻的回體丹那一天（Game._pill_day；台灣 00:00 換日）。"""
        from tianxia.engine import Game

        shell = Game.for_world(self.c, self.world)
        shell.now = CLOCK[0]
        return shell._pill_day()

    def train(self, who: str, tag: str, times: int = 1, win: bool = False) -> None:
        """按 act:train（先看鈕與底下那一行；每一下補滿體力、今天出陣的次數歸零〔出陣開著的季：這一軌要的是遊歷、操練那幾支，
        次數用完在 duty_more 另外擺〕、之後把戰後事件照第一個選項選掉）。win：照寫好的打贏（winning）。"""
        for i in range(times):
            self.place(who, None)
            self.edit(who, lambda p: setattr(p, "sorties_today", 0))
            view = self.main(who)
            emit(f"{tag} 的 act:train（第 {i + 1} 下）", self.ids(view).get("act:train"))
            emit(f"{tag} 那一行", (view.get("action_notes") or {}).get("act:train"))
            option = self.ids(view).get("act:train")
            if not option or not option.get("enabled"):
                return
            if win:
                with self.winning():
                    self.choose(who, "act:train")
            else:
                self.choose(who, "act:train")
            self.settle_choices(who)
            self.state_of(who, f"{tag} 之後（第 {i + 1} 下）")

    def duty(self, who: str, tag: str) -> None:
        view = self.main(who)
        option = self.ids(view).get("act:duty")
        emit(f"{tag} 的 act:duty", option)
        if option and option.get("enabled"):
            self.choose(who, "act:duty")
            self.settle_choices(who)
        self.state_of(who, f"{tag} 之後")

    def with_duty(self) -> bool:
        from tianxia import orders
        from tianxia.engine import Game

        shell = Game.for_world(self.c, self.world)
        return orders.active(shell.state, self.c)

    @contextlib.contextmanager
    def factions_of(self, **changes):
        """記憶體裡把幾支隊伍換成別的陣營（做完換回來；兩份程式同一套）。"""
        before = {sid: self.c.squads[sid].faction for sid in changes if sid in self.c.squads}
        for sid in before:
            self.c.squads[sid].faction = changes[sid]
        emit("換陣營的隊伍", {sid: changes[sid] for sid in sorted(before)})
        try:
            yield
        finally:
            for sid, faction in before.items():
                self.c.squads[sid].faction = faction

    # ── 序章雪恥 ──

    def walk_hut(self, who: str) -> bool:
        """序章走到雪恥那一步（同 Scenario.prologue，全走 API）；沒有序章的季回 False。"""
        from tianxia.features.sense import sensing

        view = self.main(who)
        if not view.get("prologue"):
            emit(f"{who}：這一季沒有序章", None)
            self.settle_choices(who)
            return False
        self.choose(who, "choice:0")
        self.choose(who, "choice:0")
        self.do(who, "view_tab", {"tab": "practice"})
        self.choose(who, "act:explore")
        senses = [i for i, o in self.ids(self.main(who)).items() if i.startswith("sense:") and i != sensing.LET_GO and o.get("enabled")]
        if senses:
            self.choose(who, senses[0])
        self.choose(who, sensing.LET_GO)
        got = [i for i in self.chars.load(who).player.insights if i in ("feng", "shan", "shui", "huo")]
        if got:
            self.call(who, "POST", "/api/menxia/slot", {"art": "jichu_quanjiao", "insight": got[0]})
            self.call(who, "POST", "/api/menxia/practice", {"kind": "武學"})
            self.call(who, "POST", "/api/menxia/practice", {"kind": "武學"})
            self.call(who, "POST", "/api/menxia/forge", {"insights": [got[0], f"{got[0]}~2"]})
        self.do(who, "pill")
        return True

    def hut_fight(self, who: str, tag: str) -> None:
        view = self.main(who)
        emit(f"{tag} 的 act:train", self.ids(view).get("act:train"))
        emit(f"{tag} 那一行", (view.get("action_notes") or {}).get("act:train"))
        self.choose(who, "act:train")
        self.state_of(who, f"{tag} 之後")

    def hut_win(self) -> None:
        if self.walk_hut(self.NEWBIES[0]):
            self.hut_fight(self.NEWBIES[0], "雪恥（照寫好的險勝）")

    def hut_lose(self) -> None:
        if not self.walk_hut(self.NEWBIES[1]):
            return
        step = next(s for s in self.c.tutorial.steps if s.force_tier)
        before, step.force_tier = step.force_tier, "落敗"
        try:
            self.hut_fight(self.NEWBIES[1], "雪恥（換成落敗）")
        finally:
            step.force_tier = before

    def hut_after(self) -> None:
        """後半：雪恥打完、還沒配點的那兩位接著走（新程式接舊程式的序章）：配點、熔蠻牛拳。"""
        for who in self.NEWBIES:
            self.relogin(who)
        for who in self.NEWBIES:
            if not self.main(who).get("prologue"):
                continue
            self.do(who, "allocate", {"stat": "str"})
            self.call(who, "POST", "/api/menxia/melt", {"art": "manniu_quan"})
            self.state_of(who, "配點、熔煉之後")

    # ── 守勢 ──

    def duty_first(self) -> None:
        """官甲在自家的涿郡守勢（這一天第一次）。約戰開著（season21、week7）：記一點貢獻；weekend：佔一次出陣、推所在戰線、記守城。"""
        if not self.with_duty():
            emit("這一季沒有守勢", None)
            return
        if self.place("官甲", "zhuo_county"):
            self.duty("官甲", "守勢第一次")

    def duty_second(self) -> None:
        """後半第一件事：同一天再守一次（約戰開著不再記貢獻；weekend 再佔一次出陣）。"""
        self.relogin("官甲")
        if not self.with_duty():
            return
        if self.place("官甲", "zhuo_county"):
            self.duty("官甲", "守勢第二次（同一天）")

    def duty_more(self) -> None:
        """中立地灰著（領地爭奪：不是自家的區塊）；weekend 次數用完灰著；約戰開著的季隔天照記一點。"""
        if not self.with_duty():
            return
        from tianxia import territory

        self.set_duel(self.duel_default is not None)
        if self.place("官甲", "runan_wilds"):
            self.duty("官甲", "中立地的守勢")
            self.choose("官甲", "act:duty")
        if territory.on(self.c) and self.profile not in DUEL_PROFILES and self.place("官乙", "zhuo_county"):
            today = self.today()
            self.edit("官乙", lambda p: (setattr(p, "sortie_day", today), setattr(p, "sorties_today", self.c.config.sortie.per_day)))
            self.duty("官乙", "次數用完的守勢")
            self.choose("官乙", "act:duty")
        if self.profile in DUEL_PROFILES and self.place("官甲", "zhuo_county"):
            self.edit("官甲", lambda p: setattr(p, "duty_day", p.duty_day - 1))  # 昨天記的：今天照記
            self.duty("官甲", "隔天的守勢")

    # ── 舊遊歷、操練、推大勢 ──

    def wander(self) -> None:
        """散人的遊歷：長社（必敗先問、打輸、照寫好的打贏推大勢、戰後事件）、潁水河畔（不推大勢）；地盤開著的季是灰的「散人不能出陣」。"""
        self.set_duel(False)
        if self.place(self.RANGER, "changshe"):
            self.train(self.RANGER, "長社", times=2)
            self.train(self.RANGER, "長社（照寫好的打贏）", times=2, win=True)
        if self.place(self.RANGER, "yingshui"):
            self.train(self.RANGER, "潁水河畔")
        self.trends("散人遊歷之後")

    def drill(self) -> None:
        """跟自家隊伍操練（_drill、_drill_push、drill_scale）。"""
        from tianxia import territory

        self.set_duel(False)
        if self.profile == "test":
            self.place("官乙", "lake", faction="guan")  # 測試內容沒有陣營：記一個「官軍」、湖邊的水寇在記憶體裡也記成官軍
            with self.factions_of(thug="guan"):
                self.train("官乙", "湖邊的自己人", times=3)
            self.place("官乙", None, faction=None)
        elif not territory.on(self.c):
            if self.place("官乙", "guan_camp"):
                self.train("官乙", "官軍大營", times=2)
            if self.place("官乙", "nanyang_wilds"):
                self.train("官乙", "南陽郊野（兩種都有）", times=3)
            if self.place("黃甲", "huangjin_camp"):
                self.train("黃甲", "黃巾別部營寨")
        else:  # 汝南荒野（開季中立）站的那幾路（territory.squads_at：中立駐軍與流寇野獸）在記憶體裡換成官軍
            foes = sorted(territory.squads_at(self.world.get_season(), self.c, "runan_wilds"))
            with self.factions_of(**{sid: "guan" for sid in foes}):
                if self.place("官乙", "runan_wilds"):
                    self.train("官乙", "汝南荒野全是自己人（出陣）", times=2)
            # 兩種都有（修正輪）：汝南荒野只站一路（nz_kuibing），換第一路就是全部，跟「全是自己人」一模一樣、鈕上沒有「或與自己人操練」。
            # 改成 nz_kuibing 照舊是外人，中立駐軍那一格在記憶體裡多塞一路自家的（官軍最弱、不是大場面的那一路）：出陣攻打的池子兩路，
            # rng 在自己人與外人之間挑。（不能拿站兩路的區塊換一路的陣營：Location.enemies 裡的換了陣營就不算中立的流寇，
            # conquest.neutral_squads 把它濾掉，池子又剩一路。）
            with self.neutral_plus("runan_wilds", self.weakest("guan")):
                if self.place("官乙", "runan_wilds"):
                    self.train("官乙", "汝南荒野兩種都有（出陣）", times=8)
        self.trends("操練之後")

    def weakest(self, side: str) -> str:
        """這一邊最弱、不是大場面的那一路隊伍（兩份程式同一份內容，挑到的一樣）。"""
        from tianxia import styles

        return min((q.difficulty, sid) for sid, q in self.c.squads.items() if q.faction == side and not styles.is_big(self.c, q))[1]

    @contextlib.contextmanager
    def neutral_plus(self, loc: str, sid: str):
        """記憶體裡在開季中立的這一塊的中立駐軍（Scenario.territory.neutral_garrison）多塞一路（做完拿掉；兩份程式同一套）。"""
        garrison = self.c.scenario.territory.neutral_garrison
        before = garrison.get(loc)
        garrison[loc] = [*(before or []), sid]
        emit(f"{loc} 的中立駐軍多一路", {"squad": sid, "garrison": garrison[loc]})
        try:
            yield
        finally:
            if before is None:
                garrison.pop(loc, None)
            else:
                garrison[loc] = before

    def push(self) -> None:
        """遊歷推大勢（減法季關著：none、test）：官甲照寫好的打贏兩下，長社（test 是湖邊）推往自己陣營的目標（test 沒有陣營：照地點的方向）。"""
        from tianxia import territory

        if territory.on(self.c):
            return
        if self.place("官甲", "changshe"):
            self.train("官甲", "長社（官軍打贏）", times=2, win=True)
        self.trends("遊歷打贏之後")

    def backed(self) -> None:
        """並肩出陣（Game._act 的 train 那一支包在外面的）：今天答應陪你、你在他那一帶——沒商量 +30%、商量沒成打空、商量成了 +60%。"""
        from tianxia.rules import game_day
        from tianxia.state import ParleyBacking

        self.set_duel(False)
        figure = next(iter(self.c.characters))
        loc = "changshe" if self.profile in ("none", "test") else "runan_wilds"
        for plan in (None, False, True):
            if not self.place("官甲", loc):
                return
            self.main("官甲")
            # 這一季此刻是第幾天：讀全服的季（同 Game.for_world）。角色檔裡的 world 是殘根（time 0、season21 的章 False），
            # 照它算永遠是第 1 天——season21 開季那天是第 7 天，並肩那一支在 season21 一次都走不到（修正輪）
            day = game_day(self.c, self.world.get_season())
            self.edit("官甲", lambda p, plan=plan, day=day: setattr(p, "parley_backing", ParleyBacking(figure=figure, region=None, day=day, plan=plan)))
            self.train("官甲", f"並肩出陣（打法 {plan}）")

    @contextlib.contextmanager
    def judge_calls(self, tag: str):
        """這一段伺服器在鎖外叫了哪幾路大場面判讀（server.prepare_fight → fight_llm.judge），段落結束寫出來。修正輪加的：操練、
        約戰開著時那張卡都不寫判讀的字（判讀回來之後操練照樣操練、約戰照樣只回卡），JudgeClient 又是立刻回，叫沒叫光看回應與資料庫
        看不出來——train_squad 的約戰那道關拿掉、操練那道關拿掉都比不出差（審查員量的）。"""
        from tianxia import fight_llm

        real, calls = fight_llm.judge, []

        def judge(client, request, *args, **kwargs):
            calls.append(request.squad_id)
            return real(client, request, *args, **kwargs)

        fight_llm.judge = judge
        try:
            yield
        finally:
            fight_llm.judge = real
            emit(f"{tag} 叫了大場面判讀", calls)

    def judge(self) -> None:
        """大場面判讀（server.may_judge_fight → prepare_fight → Game._fight_squad）：舊遊歷照 _train_pick 挑的那一路判；操練不判；
        約戰開著時出陣那一格是卡、不判；出陣照判。每一下寫叫了哪幾路（judge_calls）。"""
        from tianxia import territory

        self.c.config.big_fight_difficulty = 1
        MODEL["judge"] = True
        try:
            if not territory.on(self.c):
                if self.place(self.RANGER, "yingshui"):
                    with self.judge_calls("大場面的舊遊歷"):
                        self.train(self.RANGER, "大場面的舊遊歷")
                if self.profile == "none" and self.place("官乙", "guan_camp"):
                    with self.judge_calls("大場面的操練"):
                        self.train("官乙", "大場面的操練")
            else:
                if self.profile in DUEL_PROFILES:
                    self.set_duel(True)
                    if self.place("官甲", "runan_wilds"):
                        with self.judge_calls("大場面、約戰開著"):
                            self.train("官甲", "大場面、約戰開著")
                self.set_duel(False)
                if self.place("官甲", "runan_wilds"):
                    with self.judge_calls("大場面的出陣"):
                        self.train("官甲", "大場面的出陣")
        finally:
            MODEL["judge"] = False
            self.c.config.big_fight_difficulty = self.big_default

    def card(self) -> None:
        """約戰開著的季（season21、week7）按一次出陣那一格：打開出陣前那張卡（不寫紀錄）。"""
        if self.profile not in DUEL_PROFILES:
            return
        self.set_duel(True)
        if self.place("官乙", "runan_wilds"):
            self.train("官乙", "約戰開著的出陣那一格")

    def resume(self) -> None:
        self.set_duel(False)
        self.login_all()


# 舊遊歷與操練（none）、守勢與出陣（weekend）、約戰開著的守勢（week7）。測試內容的 BotRunner 一個都不上線（acted 0），不跑
TRAIN_BOT_PROFILES = ("week7",)
TRAIN_SEATS = [("操兵甲", "guan", "guan_camp"), ("操兵乙", "guan", "changshe"), ("操兵丙", "huang", "huangjin_camp"),
               ("操兵丁", "huang", "nanyang_wilds"), ("操兵戊", "guan", "zhuo_county")]
# 修正輪：weekend（地盤開著、約戰關著）照原樣擺，BotRunner 336 次行動一則出陣、守勢都沒有（只有城裡操練），三軌的假人也沒有一個按過非約戰的
# 守勢。這兩位那一顆照原本的分數再加一道軍令的分（bot_policy.ORDER_SCORE；原本是 None〔不會按〕的照舊不按）：涿郡（官軍自家的區塊）的守勢走
# 非約戰那一支（佔出陣次數、推線、記守城、次數用完灰掉），南陽郊野的黃巾出陣經 train_fight。兩份程式同一套。
TRAIN_FOCUS = {"weekend": {"操兵戊": "act:duty", "操兵丁": "act:train"}}


@contextlib.contextmanager
def _train_focus(profile: str):
    from tianxia import bot_policy

    focus = TRAIN_FOCUS.get(profile, {})
    real = bot_policy.score

    def score(game, option, bot_profile):
        value = real(game, option, bot_profile)
        if value is not None and focus.get(game.state.player.name) == option.id:
            value += bot_policy.ORDER_SCORE
        return value

    if focus:
        bot_policy.score = score
    try:
        yield
    finally:
        bot_policy.score = real


def train_bots_run(root: Path, profile: str, out: Path, tmp: Path) -> None:
    """出陣三的假人（--seats train）：整季機器人（bot.play_season，種子 3、SB_PLAY_STEPS 步）與伺服器假人（BotRunner＋bot_policy.take_turn，
    random.Random(7)、假時鐘、每一輪 +300 秒）五個擺在官軍大營、長社、黃巾別部營寨、南陽郊野、涿郡（測試內容擺在湖邊、小鎮）跑 N 輪：
    寫存檔、戰報、紀錄標題（遊歷、操練、守勢、出陣各幾則）、大勢與資料庫的雜湊。"""
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

    def content_of():
        if profile == "test":
            return load_content(root / "tests" / "fixtures" / "content")
        return load_content(root / "content", profile=None if profile == "none" else profile)

    def titles(states) -> dict:
        return dict(sorted(Counter(e.title.partition("・")[0] for s in states for e in s.journal).items()))

    def tagged(states) -> dict:
        """這一包的那幾種紀錄照（標題頭、標籤）數（修正輪）：標題頭分不出兩種操練——城裡操練（act:drill，training 那一包）是標題頭「操練」、
        標籤「校場過招」，這一包跟自家隊伍操練是標題頭「遊歷」或「出陣」、標籤「操練」；打仗的標籤是勝負加對手。"""
        heads = ("遊歷", "出陣", "雪恥", "操練", "巡哨", "傳道", "保境安民")
        found = Counter(f"{e.title.partition('・')[0]}／{e.tag}" for s in states for e in s.journal if e.title.partition("・")[0] in heads)
        return dict(sorted(found.items()))

    content = content_of()
    world = open_world(tmp / "play.db")
    game = bot.play_season(content, seed=3, max_steps=int(os.environ.get("SB_PLAY_STEPS", "700")), world=world, now=CLOCK0)
    emit("出陣三整季機器人 存檔", hashlib.sha256(game.state.model_dump_json().encode("utf-8")).hexdigest())
    emit("出陣三整季機器人 紀錄標題", titles([game.state]))
    emit("出陣三整季機器人 這一包的紀錄（標題頭／標籤）", tagged([game.state]))
    emit("出陣三整季機器人 戰報", hashlib.sha256(json.dumps([r.model_dump(mode="json") for r in game.state.battles], ensure_ascii=False)
                                               .encode("utf-8")).hexdigest())
    emit("出陣三整季機器人 大勢", dict(sorted(world.get_season().trends.items())))
    emit("出陣三整季機器人 資料庫", hashlib.sha256(db_text(tmp / "play.db").encode("utf-8")).hexdigest())

    content = content_of()
    content.config.bot_tick_seconds = 10 ** 6  # 在線的假人每一輪都動（act_chance 夾到 1）
    world = open_world(tmp / "runner.db")
    world.seed_first_season(content)
    world.open_season(content, now=CLOCK0)
    chars = open_characters(tmp / "runner.db")
    seats = [("操兵甲", None, "lake"), ("操兵乙", None, "town")] if profile == "test" else TRAIN_SEATS
    for i, (name, side, loc) in enumerate(seats):
        g = Game.new(content, name, rng=random.Random(i), world=world, graduated=True)
        g.client = None
        g.sync(CLOCK0)
        p = g.state.player
        p.bot = BotProfile(personality="普通", seed=31 + i, faction=side, season_number=world.get_season_number())
        p.faction, p.location, p.journey = side, loc, None
        p.visited.add(loc)
        p.tutorial_step = len(content.tutorial.steps)
        p.joined_at = -1.0e9
        chars.save(g.state)
    clock = [CLOCK0]
    runner = BotRunner(content, world, chars, rng=random.Random(7), clock=lambda: clock[0])
    totals = Counter()
    emit("出陣三假人 偏好", TRAIN_FOCUS.get(profile, {}))
    with _train_focus(profile):
        for _ in range(int(os.environ.get("SB_RUNNER_TICKS", "120"))):
            clock[0] += 300.0
            report = runner.tick()
            totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
    states = chars.all(bots_only=True)
    emit("出陣三假人 一輪一輪", dict(sorted(totals.items())))
    emit("出陣三假人 紀錄標題", titles(states))
    emit("出陣三假人 這一包的紀錄（標題頭／標籤）", tagged(states))
    emit("出陣三假人 戰報", {s.player.name: hashlib.sha256(json.dumps([r.model_dump(mode="json") for r in s.battles], ensure_ascii=False)
                                                           .encode("utf-8")).hexdigest() for s in states})
    emit("出陣三假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
    emit("出陣三假人 大勢", dict(sorted(world.get_season().trends.items())))
    emit("出陣三假人 資料庫", hashlib.sha256(db_text(tmp / "runner.db").encode("utf-8")).hexdigest())
    out.write_text(BUF.getvalue(), encoding="utf-8", newline="\n")
    print(profile, "出陣三假人", dict(totals), tagged(states), "整季機器人", tagged([game.state]))


# 改一個字（selftest）：操練那一句（搬之前在 engine.py 的 _drill、之後在 features/sortie/train_actions.py），none 的官軍大營操練到
register_track("train", TrainScenario, (("tianxia/features/sortie/train_actions.py", "tianxia/engine.py"),
                                        ("軍心為之一振。", "軍心為之一振！")), "week7",
               covers=("battle", "bounties", "bout", "companions", "cultivation", "explore", "faction", "figure_acts", "gear", "guide",
                       "military", "peers", "seal", "sense", "socialize", "sortie", "stamina_plays", "story", "tavern", "travel",
                       "zhuan"))
register_bots("train", TRAIN_BOT_PROFILES, train_bots_run)  # 出陣三那一軌的假人（--seats train）
