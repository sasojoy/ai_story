"""same_behavior 一軌一檔：afterglow（這一檔登記 afterglow）。"""
from __future__ import annotations

from sb.base import Scenario
from sb.harness import emit, register_track

# ── core_rest（第二輪第 99 批：有主的零碎歸位與 engine 收尾）──────────────────


class AfterglowScenario(Scenario):
    """第 99 批搬的方法裡別的軌走不到的那幾支（--track afterglow，自己一個資料庫）。班底的名字都是原創（PM 11/04）。
    71 軌三種設定逐行量過（sys.monitoring）：其餘的方法與分支別的軌都走到（首創回饋 craft、crossblade、smithy，鎖定的大事 omen、progress，你不在的時候 59 軌），
    只差三樣，這一軌補：痕跡過門檻出過力的行狀（season21、week7 讀到「這裡頭有你出的一分力」兩人各一筆，一條規則被內容拿掉的跳過）、
    人物原字原句引出口訣（「說到了」回「這句話你記進了武學譜」；情誼不夠、沒說到、第二次都是空的）、動作裡跨過威震州郡（「最新一則」多那兩句、天下大事傳一句）。
    半舊半新：切在痕跡的名單還剩一個人的那一刻（前半 FIRST 記了、SECOND 沒記），後半 SECOND 同步、名單空了鍵拿掉；跨段在後半走新程式。
    模型不連網路、沒有路由給得出夠大的一筆名望：口訣與跨段同 lantern，拿 Game 在鎖裡叫（_overhear、_write、_log 都是 Game 上留著的名字，新舊都叫得到）。
    這一軌走不到的：測試內容沒有痕跡規則、沒有口訣、名聲關著，只走到各自關著的那一下（「痕跡規則條數」0、「口訣認得的人物」null、跨段沒有多的句子）。
    假人：這一軌沒有假人段，搬的東西假人只經 sync 碰到，sortie 那一組假人段走得到。"""

    PLAYERS = {"鍾離岫": None, "聞人硯": None}
    NEWBIE = "桑晚舟"
    PHASES_FIRST = ["setup", "seat", "marks", "clue", "half"]
    PHASES_SECOND = ["resume", "marks_rest", "fame_up", "wrap"]
    FIRST = "鍾離岫"
    SECOND = "聞人硯"

    def in_lock(self, who: str):
        """沒有路由走得到的那幾句（模型回的話、這一下跨段）：同 lantern，拿 Game 在鎖裡叫。"""
        self.begin()
        game = self.server.game_for(who)
        return game, self.server._locked(game)

    def seat(self) -> None:
        for who in (self.FIRST, self.SECOND):
            self.main(who)  # 第一次同步：名聲只記段、寫那一則說明，之後的跨段才接在紀錄上

    def marks(self) -> None:
        """痕跡過了門檻、兩個人出過力：FIRST 記行狀，名單還剩 SECOND（後半才空）；再擺一條規則被內容拿掉的、一條這一下才過門檻的。"""
        rules = list(self.c.mark_rules)
        emit("痕跡規則條數", len(rules))
        if len(rules) < 2:
            return

        def fn(s) -> None:
            s.marks_fired[rules[0].mark] = s.time
            s.mark_helpers[rules[0].mark] = [self.FIRST, self.SECOND]
            s.marks_fired["afterglow:拿掉了"] = s.time
            s.mark_helpers["afterglow:拿掉了"] = [self.FIRST]
            s.marks[rules[1].mark] = rules[1].threshold

        self.world.mutate_season(fn)
        self.main(self.FIRST)

    def clue(self) -> None:
        """人物原字原句引出口訣：模型不連網路（harness 固定層），話直接餵給 Game._overhear（第 99 批搬進人物情誼包，測試也這樣叫）。"""
        from tianxia import secret_recipes

        game, lock = self.in_lock(self.FIRST)
        with lock:
            tianji = secret_recipes.tianji_of(game.world)
            cid = next((x for x in sorted(self.c.characters) if secret_recipes.talk_clue(self.c, tianji, x) is not None), None)
            emit("口訣認得的人物", cid)
            if cid is None:
                return
            said = f"他嘆道：「{secret_recipes.talk_clue(self.c, tianji, cid).clues[secret_recipes.TALK]}」"
            emit("情誼不夠", game._overhear(cid, [said]))
            game.state.player.affinities[cid] = self.c.config.secrets.talk_affinity
            emit("沒說到", game._overhear(cid, ["他只是笑了笑。"]))
            emit("說到了", game._overhear(cid, [said]))
            emit("第二次", game._overhear(cid, [said]))
            self.chars.save(game.state)
        self.main(self.FIRST)

    def half(self) -> None:
        self.main(self.NEWBIE)

    def resume(self) -> None:
        self.login_all()

    def marks_rest(self) -> None:
        self.main(self.SECOND)  # 前半留下的名單：SECOND 記行狀，名單空了鍵也拿掉

    def fame_up(self) -> None:
        """動作裡跨過威震州郡（名聲 4.5）：接在這一下那一則紀錄的最後、天下大事傳一句、自己存季。沒有路由給得出夠大的一筆名望，同 clue 在鎖裡叫。"""
        from tianxia import renown

        game, lock = self.in_lock(self.FIRST)
        with lock:
            state = game.state
            for _ in range(60):
                if not renown.on(self.c) or renown.fame_tier(state, self.c) >= self.c.config.renown.news_tier:
                    break
                renown.gain(state, self.c, "fame", 20)
            game._write("餘響", ["這一下名聲傳開了。"])
            emit("跨段", game._log(["這一下名聲傳開了。"]))
            emit("最新一則", [state.journal[0].title, state.journal[0].lines, state.journal[0].changes])
            self.chars.save(state)
        self.main(self.FIRST)

    def wrap(self) -> None:
        self.main(self.SECOND)
        self.main(self.NEWBIE)


# 改一個字（selftest）：痕跡行狀那一句（第 99 批從 engine.py 搬進共用層 marks，兩處找），marks 那一段抓到
register_track("afterglow", AfterglowScenario, (("tianxia/marks.py", "tianxia/engine.py"), ("這裡頭有你出的一分力。", "這裡頭有你出的一分力！")), "season21")
