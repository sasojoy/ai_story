"""same_behavior 一軌一檔：story（這一檔登記 story）。"""
from __future__ import annotations

import contextlib
import hashlib
import os
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, emit, register_track

# ═══════════════════════════ story：一條線＋簽到一軌（全部拆包第 30 批，dev/story-1） ═══════════════════════════
# 一條線（tianxia/storyline.py 與 Game 上 story_*、_story_*、_mirror_squad 十個方法、story: 前綴）與每日簽到（tianxia/checkin.py 與
# Game 上 check_in、_auto_checkin、checkin_view 三個方法）搬進新包 tianxia/features/story/ 與 tianxia/features/checkin/（舊名留成別名；計畫
# docs/superpowers/plans/2026-11-04-一條線簽到-第30批.md）。角色的名字都是原創的（PM 11/04：新開的軌不用既有作品的人名）。

_STORY_CHECKIN_DAY = 6  # 簽到要挑四階的第一天（Config.checkin.tier4_days 的第一個）；前半快轉到這一天、人都還沒領


class StoryScenario(Scenario):
    """一條線＋簽到（全部拆包第 30 批；--track story，自己一個資料庫）。程式組的線（story_start）自己寫五條，內容寫的長篇奇事走真的那一條（賣兒契）：
    - 答題：宋問津開山徑三問，答第一題——**前半停在答到一半**（story_open 還開著）；後半答第二題、先擱著（later）、再按回來、答完（照記號走結局、
      文字照記號換段落）、收卡（story_seen）、答不在選單上的（story:…:a9）。
    - 打一場：呂臨淵打渡口一戰落敗（灰著寫還要等多久、按灰的被擋、行狀與卡）——**前半停在等著再試**；後半時候到了打贏入傳。桑弄潮打鏡中人
      （自己的影子，難度照輸過幾次削弱）輸兩次、第三次贏。
    - 期限：魏守拙的答題段有期限，前半只開線，後半把期限擺成過了，同步時往 late 走、失敗的結局入傳。
    - 長篇奇事（內容寫的線，走事件、多日段、站到各段的地點）：周問舟在汝南荒野遇上賣兒契，前半走幾步停在半路（簽到的快轉排在最前面，等的段與期限都還沒過就跨過切點），後半接著走完；
      杜歸舟後半才在潁川書院遇上臥龍岡的地，一路走完。
    - 季末未了：衛未央、蔡留白各開一條答題線不答，收季之後衛未央同步一次（寫此事未了）、蔡留白不同步（換季那一刻補寫）。
    - 簽到（season21、week7 開著；其餘寫「這一季沒有簽到」，同一串 API 照打）：祝延年、范長歌第 1 天自動領了，快轉到要挑四階的那一天——
      **前半停在當天還沒領**；後半：祝延年沒挑（回要先挑）、挑錯、挑對領了、再領一次（簽過了）；范長歌直接挑對；隔天（普通日）自動領、過了最後一天畫面沒有簽到。
    - 章回主線、探索擲中（審查修正）：韓承業投靠官軍、照 walk 走章回的事件段；陸尋蹤把長篇奇事開頭的機率擺成 1、站到開頭的地方按探索。
    - 假人：BotRunner 兩個（一個眼前有答題、一個閒著；簽到是同步時自動簽的，假人開工那天通常已經領了）；整季機器人站在答題的選單上挑哪一顆。沒有一條線的設定（none、weekend、
      test 的線關著）寫「沒有」，同一串 API 照打。"""

    QUIZ, DUELER, MIRROR, LATE, WALKER = "宋問津", "呂臨淵", "桑弄潮", "魏守拙", "周問舟"
    REST_A, REST_B, SIGNER, LAPSER, WALKER2 = "衛未央", "蔡留白", "祝延年", "范長歌", "杜歸舟"
    PLAYERS = {name: None for name in (QUIZ, DUELER, MIRROR, LATE, WALKER, REST_A, REST_B, SIGNER, LAPSER, WALKER2, "韓承業", "陸尋蹤")}
    NEWBIE = "穆安然"
    BOT_SEATS = ["線甲", "線乙"]
    REAL = "maier"
    # 審查修正（第 30 批）：投靠官軍走章回主線的人、探索擲中內容寫的線的人
    CHAPTER, EXPLORER = "韓承業", "陸尋蹤"
    PHASES_FIRST = ["setup", "sign_first", "quiz_first", "duel_first", "mirror_first", "late_first", "walk_first", "rest_open", "half"]
    PHASES_SECOND = ["resume", "quiz_on", "duel_on", "mirror_on", "late_on", "walk_on", "sign_on", "chapter_on", "explore_on", "bots", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        self.defs = self.story_defs()

    # ── 自己組的幾條線 ──

    def story_defs(self) -> dict:
        from tianxia.models import StoryAnswer, StoryDef, StoryEnding, StoryFail, StoryQuestion, StoryRoute, StoryStage

        squad = sorted(self.c.squads)[0] if self.c.squads else None

        def ask(text: str, left: str, right: str, marks=("攻", "守")):
            return StoryQuestion(text=text, answers=[StoryAnswer(text=left, marks={marks[0]: 1}), StoryAnswer(text=right, marks={marks[1]: 1})])

        def end(line: str, key: str, failed: bool = False, tail: str = ""):
            return StoryEnding(id=key, title=f"{key}的收場", text=f"{{?{line}.攻:你出手得多|你收手得多}}{{!{line}.守:，一路沒有退過}}。{tail}",
                               annal=f"{{name}}在{line}這件事上，{key}地收了場。", failed=failed, weight=3)

        def fail(line: str):
            return StoryFail(title="敗了一陣", card="你落敗退下，{days}後再來。", log="（落敗了，{days}後再試。）", annal=f"{{name}}在{line}落敗了一場。")

        return {
            "quiz": StoryDef(id="sb_quiz", title="山徑三問", intro="山徑口有人攔路，說要問你三件事。",
                             stages=[StoryStage(id="ask", kind="quiz", hint="答完山徑上的三問", next="calm", routes=[StoryRoute(when={"攻": 2}, go="bold")],
                                                questions=[ask("第一問：路遇不平，你如何？", "拔刀相助", "繞道而行"),
                                                           ask("第二問：有人託你送一封信，你如何？", "當場拆開", "原封送到"),
                                                           ask("第三問：夜裡有人敲門，你如何？", "開門去看", "吹燈裝睡")])],
                             endings=[end("sb_quiz", "bold"), end("sb_quiz", "calm")]),
            "duel": StoryDef(id="sb_duel", title="渡口一戰", intro="渡口有人等你比劃一場。",
                             stages=[StoryStage(id="fight", kind="fight", squad=squad, retries=2, hint="去渡口打一場", win="won", lose="lost", fail=fail("渡口"))],
                             endings=[end("sb_duel", "won"), end("sb_duel", "lost", failed=True)]),
            "mirror": StoryDef(id="sb_mirror", title="鏡中人", intro="水裡的人跟你長得一模一樣。",
                               stages=[StoryStage(id="fight", kind="fight", mirror=0.4, mirror_name="鏡中人", mirror_weaken=0.05, mirror_floor=0.1, retries=4,
                                                  hint="面對鏡中人", win="won", lose="lost", fail=fail("鏡邊"))],
                               endings=[end("sb_mirror", "won"), end("sb_mirror", "lost", failed=True)]),
            "late": StoryDef(id="sb_late", title="限期之約", intro="對方說，過了期限就不候了。",
                             stages=[StoryStage(id="ask", kind="quiz", hint="趕在期限之前", days=0.5, late="gone", next="done",
                                                questions=[ask("你赴約嗎？", "赴約", "不赴")])],
                             endings=[end("sb_late", "done"), end("sb_late", "gone", failed=True)]),
            "open": StoryDef(id="sb_open", title="未了之事", intro="有一件事擱在心上。", unfinished="{name}擱在心上的一件事，到季末還沒有了結。",
                             stages=[StoryStage(id="ask", kind="quiz", hint="想一想", next="done", questions=[ask("你怎麼想？", "放下", "不放")])],
                             endings=[end("sb_open", "done")]),
        }

    # ── 小工具 ──

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            state.world = self.world.get_season()
            fn(state)
            self.chars.save(state)

    @contextlib.contextmanager
    def fights(self, tier: str | None):
        """這幾下的仗照寫好的 tier（同 Scenario.winning：威力、難度、亂數照算，只換結果）。"""
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

    def options(self, who: str) -> dict:
        return self.ids(self.main(who))

    def lines_on(self) -> bool:
        from tianxia.rules import jianfa

        return bool(jianfa(self.c, self.world.get_season(), "storylines"))

    def signing_on(self) -> bool:
        from tianxia.features.checkin import checkin

        return bool(checkin.on(self.c, self.world.get_season()))

    def me(self, who: str, tag: str) -> None:
        """存檔裡這兩包碰得到的那幾格：所在、一條線的進度與跳出來的卡、答題開著的那一條、紀念物與跨季旗標、簽過的日子與挑的四階、丹與銀兩、體力、
        行狀、最新三則紀錄、眼前的事件。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "loc": p.location, "lines": {k: v.model_dump(mode="json", exclude={"custom"}) | {"custom": None if v.custom is None else v.custom.kind}
                      for k, v in sorted(p.storylines.items())}, "open": p.story_open,
            "cards": [x.model_dump(mode="json") for x in p.story_cards], "keepsakes": list(p.keepsakes), "lasting": list(p.lasting),
            "checkin": [list(p.checkin_days), dict(sorted(p.checkin_picks.items()))], "pills": p.stamina_pills, "silver": p.stats.get("silver", 0),
            "stamina": p.stamina, "event": state.pending_event, "annals": [[a.kind, a.text] for a in p.annals],
            "journal": [[e.title, e.tag, list(e.lines)[:4]] for e in state.journal[:3]]})

    def begin_line(self, who: str, key: str) -> None:
        """程式組的線從 Game.story_start 開（鎖裡讀存檔、開、存回；線關著的設定回空的什麼都不動）。"""
        from tianxia.engine import Game

        self.begin()
        with self.world.action_lock():
            state = self.chars.load(who)
            state.world = self.world.get_season()
            game = Game(self.c, state, world=self.world)
            msgs = game.story_start(self.defs[key])
            self.chars.save(game.state)
        emit(f"{who} 開線 {key}", msgs)

    def press(self, who: str, line: str, tag: str) -> None:
        """按選單上「未了之事」那一顆（story:<線>；灰著照按，被擋的那一句也要寫出來）。"""
        opts = self.options(who)
        emit(f"{who} {tag} 選單上", [[i, o.get("label"), o.get("enabled")] for i, o in opts.items() if i.startswith("story:")])
        if f"story:{line}" in opts:
            self.choose(who, f"story:{line}")
        else:
            emit(f"{who} {tag} 選單上沒有 story:{line}", None)

    def answer(self, who: str, line: str, arg: str, tag: str) -> None:
        self.choose(who, f"story:{line}:{arg}")
        self.me(who, tag)

    def seen(self, who: str, tag: str) -> None:
        self.do(who, "story_seen")
        self.me(who, tag)

    def retry_now(self, who: str, line: str) -> None:
        """打輸了要等的時候擺成到了（retry_at 回到過去）。"""
        def fn(s):
            progress = s.player.storylines.get(line)
            if progress is not None:
                progress.retry_at = 0.0
        self.edit_state(who, fn)

    def mirror_power(self, who: str) -> None:
        """影子此刻的難度（Game._mirror_squad，輸過幾次削幾次）。"""
        from tianxia.features.story import storyline
        from tianxia.engine import Game

        self.begin()
        state = self.chars.load(who)
        state.world = self.world.get_season()
        progress = state.player.storylines.get("sb_mirror")
        pair = None if progress is None else storyline.current(self.c, progress)
        if pair is None:
            emit(f"{who} 影子難度", None)
            return
        emit(f"{who} 影子難度", Game(self.c, state, world=self.world)._mirror_squad(progress, pair[1]).difficulty)

    def walk(self, who: str, rounds: int) -> None:
        """長篇奇事往下走：多日段等完（entered 往前挪）、站到這一段做得了的地方、眼前有事件就選第一個亮的、沒有就按「未了之事」那一顆。"""
        from tianxia.features.story import storyline

        for _ in range(rounds):
            state = self.chars.load(who)
            live = storyline.active(state)
            if not live:
                emit(f"{who} 沒有還沒收的線", None)
                return

            def age(s):
                for pr in storyline.active(s):
                    if pr.entered is not None:
                        pr.entered -= 1.0e9
            self.edit_state(who, age)
            pair = storyline.current(self.c, live[0])
            where = pair[1].where.locations if pair is not None else []
            if where and not state.pending_event and state.player.location not in where:
                self.place(who, where[0])
            opts = self.options(who)
            pick = next((i for i, o in opts.items() if i.startswith("choice:") and o.get("enabled")), None) or next(
                (i for i, o in opts.items() if i.startswith("story:") and o.get("enabled")), None)
            if pick is None:
                emit(f"{who} 此刻沒有可按的", [[i, o.get("enabled")] for i, o in opts.items()])
                return
            self.choose(who, pick)
        self.me(who, f"走了 {rounds} 步")

    def forward_to(self, day: int) -> None:
        """管理者快轉（一天一天），快轉到簽到的第 day 天（沒有簽到的設定快轉同樣的天數）。"""
        from tianxia.features.checkin import checkin

        for _ in range(day):
            s = self.world.get_season()
            if checkin.on(self.c, s) and checkin.day_of(self.c, s) >= day:
                break
            self.do(ADMIN, "fast_forward", {"hours": 24})
        s = self.world.get_season()
        emit("簽到第幾天", checkin.day_of(self.c, s) if checkin.on(self.c, s) else None)

    def sign(self, who: str, attribute: str | None, tag: str) -> None:
        """/api/do/checkin（attribute 是四階挑的屬性；None 不帶），前後各看一次江湖頁的簽到小標。"""
        view = self.main(who)
        view = view.get("main", view) if isinstance(view, dict) else {}
        emit(f"{who} {tag} 之前的簽到小標", (view.get("status") or {}).get("checkin"))
        self.do(who, "checkin", {} if attribute is None else {"attribute": attribute})
        self.me(who, tag)

    # ── 前半 ──

    def quiz_first(self) -> None:
        """宋問津開山徑三問，答第一題停在答到一半。"""
        who = self.QUIZ
        self.begin_line(who, "quiz")
        self.main(who)
        self.press(who, "sb_quiz", "開頭")
        self.answer(who, "sb_quiz", "a0", "答了第一題")

    def duel_first(self) -> None:
        """呂臨淵打渡口落敗：灰著寫還要等多久、按灰的被擋。"""
        who = self.DUELER
        self.begin_line(who, "duel")
        self.main(who)
        with self.fights("落敗"):
            self.press(who, "sb_duel", "第一場")
        self.me(who, "落敗之後")
        self.press(who, "sb_duel", "還在等")
        self.me(who, "按灰的之後")

    def mirror_first(self) -> None:
        """桑弄潮打鏡中人，輸第一次。"""
        who = self.MIRROR
        self.begin_line(who, "mirror")
        self.main(who)
        self.mirror_power(who)
        with self.fights("落敗"):
            self.press(who, "sb_mirror", "第一次")
        self.me(who, "輸了第一次")
        self.mirror_power(who)

    def late_first(self) -> None:
        who = self.LATE
        self.begin_line(who, "late")
        self.main(who)
        self.me(who, "只開了線")

    def walk_first(self) -> None:
        """周問舟在潁川荒野遇上賣兒契（內容寫的線）：走幾步停在半路。"""
        from tianxia.features.story import storyline

        who = self.WALKER
        line = self.c.storylines.get(self.REAL)
        if line is None or not self.lines_on():
            emit(f"{who} 這一季沒有長篇奇事", None)
            return
        self.place(who, "runan_wilds")
        self.edit_state(who, lambda s: storyline.start(s, self.c, line, custom=False))
        self.me(who, "開了線")
        self.walk(who, 5)

    def rest_open(self) -> None:
        for who in (self.REST_A, self.REST_B):
            self.begin_line(who, "open")
            self.main(who)

    def sign_first(self) -> None:
        """祝延年、范長歌第 1 天自動領（先同步一下）、同一天再領一次（簽過了）；快轉到要挑四階的那一天，人都還沒領。"""
        for who in (self.SIGNER, self.LAPSER):
            self.main(who)
            self.sign(who, None, "第一天再領一次")
        self.forward_to(_STORY_CHECKIN_DAY)

    def half(self) -> None:
        for who in self.PLAYERS:
            self.me(who, "前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def quiz_on(self) -> None:
        who = self.QUIZ
        self.answer(who, "sb_quiz", "a0", "答了第二題")
        self.answer(who, "sb_quiz", "later", "先擱著")
        self.main(who)
        self.press(who, "sb_quiz", "按回來")
        self.answer(who, "sb_quiz", "a1", "答完")
        self.seen(who, "收卡")
        self.choose(who, "story:sb_quiz:a9")
        self.choose(who, "story:nope")
        self.me(who, "答不在選單上的")

    def duel_on(self) -> None:
        who = self.DUELER
        self.retry_now(who, "sb_duel")
        with self.fights("大勝"):
            self.press(who, "sb_duel", "再打")
        self.me(who, "打贏之後")
        self.seen(who, "收卡")

    def mirror_on(self) -> None:
        who = self.MIRROR
        for tier in ("落敗", "大勝"):
            self.retry_now(who, "sb_mirror")
            self.mirror_power(who)
            with self.fights(tier):
                self.press(who, "sb_mirror", f"再打（{tier}）")
            self.me(who, f"{tier}之後")
        self.seen(who, "收卡")

    def late_on(self) -> None:
        """限期的線：先按一下看選單、把期限擺成過了，下一次同步往 late 走（失敗的結局入傳）。"""
        who = self.LATE

        def fn(s):
            progress = s.player.storylines.get("sb_late")
            if progress is not None:
                progress.due = 0.0
        self.edit_state(who, fn)
        self.main(who)
        self.me(who, "期限過了")
        self.seen(who, "收卡")

    def walk_on(self) -> None:
        """前半停在半路的周問舟過了期限（快轉了五天，賣兒契的期限早過了：往 late 走、收卡）；杜歸舟後半才在潁川書院遇上臥龍岡的地（內容寫的線），
        一路走完。"""
        from tianxia.features.story import storyline

        who, line = self.WALKER2, self.c.storylines.get("wolong")
        if line is None or not self.lines_on():
            emit(f"{who} 這一季沒有長篇奇事", None)
            return
        self.walk(self.WALKER, 40)  # 前半停在半路（還在等的段、期限都跨過切點，審查修正），後半接著走完
        self.seen(self.WALKER, "收卡")
        self.place(who, "yingchuan_academy")
        self.edit_state(who, lambda s: storyline.start(s, self.c, line, custom=False))
        self.walk(who, 40)
        self.seen(who, "收卡")

    def chapter_on(self) -> None:
        """章回主線（審查修正）：投靠官軍、章回的線開了，照 walk 的走法按「未了之事」走事件段到 task 段（記帳、存季、chapter_beat 的登記時機）。
        沒有陣營的設定寫「沒有」。"""
        who = self.CHAPTER
        factions = {f.id: f for f in self.c.scenario.factions}
        side = factions.get("guan")
        if side is None or not side.join_at or not self.lines_on():
            emit(f"{who} 這一季沒有章回主線", None)
            return
        self.place(who, side.join_at[0])
        self.choose(who, "faction:guan")
        self.choose(who, "faction:confirm")
        self.settle_choices(who)
        self.place(who, None)
        self.me(who, "投靠之後")
        self.walk(who, 24)
        self.seen(who, "收卡")

    def explore_on(self) -> None:
        """探索擲中內容寫的線（審查修正，Game._story_begin 的委派）：把長篇奇事開頭的機率擺成 1，站到開頭的地方按探索（三選一開著的季再挑一顆）。"""
        who = self.EXPLORER
        line = self.c.storylines.get(self.REAL)
        if line is None or line.start is None or not self.lines_on():
            emit(f"{who} 這一季沒有長篇奇事", None)
            return
        where = line.start.where
        spot = next(iter(where.locations), None) if where is not None else None
        if spot is None or not self.place(who, spot):
            emit(f"{who} 開頭的地方站不到", None)
            return
        chance = line.start.chance
        line.start.chance = 1.0
        try:
            self.choose(who, "act:explore")
            modes = [i for i, o in self.options(who).items() if i.startswith("explore:") and o.get("enabled")]
            if modes:
                self.choose(who, next((m for m in modes if m == "explore:seek"), modes[0]))
        finally:
            line.start.chance = chance
        self.me(who, "探索之後")

    def sign_on(self) -> None:
        """要挑四階的那一天：祝延年不帶屬性（要先挑）、帶錯的、挑對的領了、再領（簽過了）；范長歌直接挑對；隔一天（普通日）自動領；過了最後一天。"""
        self.sign(self.SIGNER, None, "沒挑")
        self.sign(self.SIGNER, "無", "挑錯")
        self.sign(self.SIGNER, "剛", "挑對")
        self.sign(self.SIGNER, "剛", "再領一次")
        self.sign(self.LAPSER, "快", "直接挑對")
        self.do(ADMIN, "fast_forward", {"hours": 24})
        for who in (self.SIGNER, self.LAPSER):
            self.main(who)
            self.me(who, "隔天")

    def bots(self) -> None:
        """假人：BotRunner 兩個（線甲按過「未了之事」、眼前是答題，線乙閒著；簽到是同步時自動簽的）若干輪；整季機器人站在答題的選單上挑哪一顆。"""
        from collections import Counter

        from tianxia import bot, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        sides = [f.id for f in self.c.scenario.factions]
        start = next((i for i in ("yingchuan", "town") if i in self.c.locations), sorted(self.c.locations)[0])
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=81 + i, faction=sides[i % 2] if sides else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, start, None
            p.visited.add(start)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            if i == 0:
                emit(f"{name} 開線", g.story_start(self.defs["open"]))
                emit(f"{name} 按了未了之事（眼前是答題）", g.choose("story:sb_open"))
            self.chars.save(g.state)
        emit("假人開工時的賽季", self.world.season_phase())
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(19), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {81 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_STORY_TICKS", "6"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("線假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"線假人 {name}", {"lines": {k: [v.stage, v.ending, v.step] for k, v in sorted(p.storylines.items())}, "open": p.story_open,
                                    "checkin": list(p.checkin_days), "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.begin()
        solo = Game.new(self.c, "線丙", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        solo.state.player.tutorial_step = len(self.c.tutorial.steps)
        emit("整季機器人開線", solo.story_start(self.defs["quiz"]))
        emit("整季機器人先按未了之事", solo.choose("story:sb_quiz"))  # 眼前是第一題：選單只剩三個答案（先擱著機器人不按）
        for step in range(8):
            opts = solo.options(odds=False)
            emit("整季機器人眼前的選單", [o.id for o in opts])
            emit("整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))
            picked = bot.pick(solo, opts, random.Random(step))
            if picked is None or picked == "act:on_road":
                break
            solo.choose(picked)
            emit("整季機器人按了", [picked, sorted(solo.state.player.storylines), solo.state.player.story_open])

    def season(self) -> None:
        """再快轉兩天（七天的季過了最後一天、二十一天的季只是第 9 天：簽到小標沒有或照常），收季、開下一季：衛未央收季之後同步一次（休季時寫此事未了、
        排卡）、蔡留白不同步（換季那一刻 close_season 補寫）；簽到的帳換季清掉。"""
        for _ in range(2):
            self.do(ADMIN, "fast_forward", {"hours": 24})
        for who in (self.SIGNER, self.LAPSER):
            self.sign(who, None, "又隔兩天")
        self.do(ADMIN, "end_season")
        self.main(self.REST_A)
        self.me(self.REST_A, "休季時同步過")
        self.do(ADMIN, "next_season")
        for who in self.PLAYERS:
            self.main(who)
            self.me(who, "換季之後")


# 改一個字（selftest）：選單上「未了之事」那一行的開頭（搬之前在 tianxia/storyline.py、之後在 tianxia/features/story/storyline.py）
register_track("story", StoryScenario, (("tianxia/features/story/storyline.py",),
                                        ('PENDING_HEAD = "未了之事"', 'PENDING_HEAD = "未了之事！"')), "week7")
