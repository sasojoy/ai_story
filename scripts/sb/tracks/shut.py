"""same_behavior 一軌一檔：shut（這一檔登記 shut）。"""
from __future__ import annotations

from pathlib import Path

from sb.harness import ADMIN, CLOCK, CLOCK0, emit, register_track
from sb.tracks.strip import StripScenario

# ═══════════════════════════ shut（全部拆包第 14 批「拿掉二」，dev/strip-2）：shut 一軌 ═══════════════════════════
# 週末設定、不帶設定的 14 天季只關門（計畫 docs/superpowers/plans/2026-11-04-拿掉二-第14批.md）。這一批不是純搬：week7、season21、test
# 三種設定要一個字都不變，none、weekend 之後不再是可以選的設定（same_behavior 的 PROFILES 跟著改）。這一軌盯的是「關門之後 week7、season21、
# test 還在讀」的那幾處：設定那一行與季長分岔的季曆（calendar、timetable：照現實天的程式碰上開季時沒蓋章的舊季，weekend_style）、
# 初入江湖兩步（e2_drill、e4_field）與舊步數的對應、新手目標 field2 的兩種字、h_field_lose 的提示、懸賞與序章裡「尋敵」「操練」的字。
# 名字一律原創（第 22 批認定第 3 條）。


class ShutScenario(StripScenario):
    """拿掉二（全部拆包第 14 批；--track shut，自己一個資料庫）。小工具借拿掉一那一軌的（game、me、look_here、field、town）。
    半舊半新切在 half 之後：三位新人的初入江湖寫到一半（舊步數 12 對到 e2_drill、e4_field 那一步、e6_shops 之後的一步）、一位練功輸了兩場
    等著提示，後半第一件事（answer）是新程式接著走。"""

    PLAYERS = {"閆臨淵": "guan", "秦明月": "huang", "魏無涯": None, "蕭半夏": None, "仲孫澈": "guan", "杜遠山": None}  # 杜遠山：field() 借拿掉一那一軌的小工具，要有這一位
    NEWBIE = "祁雪衣"
    NEWBIES = ["鄒白露", "宓清和", "祝融山"]  # 初入江湖寫到一半的三位（half 擺局面）
    BOT_SEATS = [("關甲", "yingshui"), ("關乙", "yingchuan"), ("關丙", "julu_altar"), ("關丁", "guangzong")]
    PHASES_FIRST = ["setup", "settings", "calendar_view", "old_season", "tutorial", "goals", "field_lose", "boards", "half"]
    PHASES_SECOND = ["resume", "answer", "again", "bots", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        # 合回 develop 第 1 段之三：城裡操練第 13 批拿掉了（主幹 8eb13295），初入江湖 e2_drill 在主幹探索一下就過、develop 要操練一下。
        # 這一軌的新人按的是探索，develop 根在記憶體裡換成主幹的條件才比得起來；主幹根本來就是 explore，一步都不多。
        for step in self.c.tutorial.steps:
            if step.id == "e2_drill" and step.done_when.action == "drill":
                step.done_when.action = "explore"

    def fresh(self, who: str, gender: str = "男") -> None:
        """註冊一位新人、建角色（不略過引導）。"""
        self.clients[who] = self.TestClient(self.server.app)
        self.passwords[who] = "pw-" + self.login_of(who)
        self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                "again": self.passwords[who]})
        self.call(who, "POST", "/api/character", {"name": who, "gender": gender})

    # ── 前半 ──

    def settings(self) -> None:
        """設定那一行與季長分岔的設定值；季上蓋的章。"""
        from tianxia import content as content_rules

        cfg = self.c.config
        emit("設定那一行", content_rules.profile_line(self.c, None if self.profile in ("none", "test") else self.profile))
        emit("設定值", {k: getattr(cfg, k, None) for k in ("season_one", "season_days", "season21", "season_segments", "server_max_players",
                                                           "late_exp_step", "affinity_gain_scale", "beta_free_refill", "season_weeks")})
        season = self.world.get_season()
        emit("這一季的章", {k: getattr(season, k, None) for k in ("season_one", "season21", "ended", "season_number")})

    def calendar_view(self) -> None:
        """季曆與時刻表：這一季，各個時刻怎麼寫、時刻表每一件排在哪、開季設定對不上時的警告。"""
        from tianxia import calendar, timetable

        season = self.world.get_season()
        emit("季曆", {"weeks": calendar.weeks(self.c, season), "days": calendar.total_days(self.c, season),
                      "weekend_style": calendar.weekend_style(season, self.c), "warning": calendar.profile_warning(self.c, season),
                      "orders_daily": calendar.orders_daily(season, self.c), "words": calendar.week_words(self.c, season)})
        emit("每個時刻", [calendar.stamp_text(d * 86400 + h * 3600, self.c, season) for d in (0, 1, 2, 3, 5, 8, 13, 20) for h in (2, 15)])
        emit("每一週的字", [calendar.week_label(w, self.c, season) for w in range(1, calendar.weeks(self.c, season) + 1)])
        emit("時刻表", [(e.id, e.kind, e.week, round(timetable.when_in(season, self.c, e) - CLOCK0, 1)) for e in timetable.events(season, self.c)])
        emit("時刻表說明", [timetable.default_dates_note(self.c), timetable.mandate_note(self.c, season)])

    def old_season(self) -> None:
        """照現實天的程式碰上開季時沒蓋章的舊季（FB-635、FB-654：休季的舊季照它自己的季曆畫）：記憶體裡複製這一季，換掉章、標休季，
        問一遍季曆、時刻怎麼寫、時刻表每一件的發生時刻與週次（calendar.weekend_style、timetable.happened_at）。"""
        from tianxia import calendar, timetable

        season = self.world.get_season()
        for tag, update in (("舊季休季", {"season21": False, "ended": True}), ("舊季還在跑", {"season21": False, "ended": False}),
                            ("新季休季", {"ended": True})):
            old = season.model_copy(update=update)
            emit(f"{tag} 季曆", {"weekend_style": calendar.weekend_style(old, self.c), "weeks": calendar.weeks(self.c, old),
                                "days": calendar.total_days(self.c, old), "warning": calendar.profile_warning(self.c, old)})
            emit(f"{tag} 每個時刻", [calendar.stamp_text(d * 86400, self.c, old) for d in (0, 1, 3, 6, 9, 14)])
            emit(f"{tag} 時刻表", [(e.id, round(timetable.happened_at(old, self.c, e) - CLOCK0, 1), timetable.happened_week(old, self.c, e))
                                 for e in timetable.events(old, self.c)])

    def tutorial(self) -> None:
        """新人從頭走：第一眼的選單與說明，照第一個可按的選項往下走幾步（初入江湖的字）。內容裡的初入江湖步驟與提示也各列一遍。"""
        emit("引導的步驟", [(s.id, getattr(s, "kind", None)) for s in self.c.tutorial.steps])
        emit("提示", sorted(self.c.hints) if isinstance(self.c.hints, dict) else [h.id for h in self.c.hints.hints] if hasattr(self.c.hints, "hints")
             else None)
        who = "新客"  # NEWBIE 在 setup 註冊過了，再註冊會 400、後面全 401
        self.fresh(who)
        self.call(who, "GET", "/api/howto")
        for step in range(8):
            opts = self.ids(self.main(who))
            pick = next((i for i, o in sorted(opts.items()) if o.get("enabled") and not i.startswith(("act:rest", "move", "map"))), None)
            if pick is None:
                break
            self.choose(who, pick)
            self.settle_choices(who)
        self.me(who, "走了幾步")

    def goals(self) -> None:
        """新手目標：什麼都沒做、做了 field2、全做了；任務卡（/api/main 的 newbie）與 newbie_view 的字。"""
        who = "仲孫澈"
        for name in (who, "魏無涯", "蕭半夏"):  # 新手期裡才有這一塊（place 把加入時刻擺到很久以前，這裡擺回此刻）
            self.edit(name, lambda p: setattr(p, "joined_at", CLOCK[0]))
        emit(f"{who} 目標 開頭", self.game(who).newbie_view())
        self.edit(who, lambda p: (p.newbie_marks.add("field2"), p.newbie_done.add("field2")))
        emit(f"{who} 目標 field2", self.game(who).newbie_view())
        self.edit(who, lambda p: (p.newbie_marks.update(["level5", "merge", "create", "bounty", "tavern", "side", "arena"]),
                                  p.newbie_done.update(["level5", "merge", "create", "bounty", "tavern", "side", "arena"])))
        emit(f"{who} 目標 全做", self.game(who).newbie_view())
        self.main(who)
        for other in ("魏無涯", "蕭半夏"):
            emit(f"{other} 目標", self.game(other).newbie_view())
            self.call(other, "GET", "/api/howto")

    def field_lose(self) -> None:
        """h_field_lose（練功連輸兩場，僵持不算）：0、1、2 場落敗、再多一場僵持。每一步看 _hint_triggers，也走 /api/main 看提示框。"""
        from tianxia import training
        from tianxia.state import BattleRecord

        who = "蕭半夏"
        spot = self.field() or self.town()
        self.place(who, spot)

        def lose(tier: str):
            def fn(state):
                state.battles.insert(0, BattleRecord(id=len(state.battles) + 1, time=CLOCK[0], location="某處", kind="wild", label=training.PRACTICE,
                                                     opponent="某隊", ours=[], tier=tier, our_power=1.0, difficulty=2.0))
            return fn
        emit("沒輸", self.game(who)._hint_triggers({"h_field_lose", "h_lose"}))
        for tag, tier in (("輸一場", "落敗"), ("輸兩場", "落敗"), ("再一場僵持", "僵持")):
            self.edit_state(who, lose(tier))
            emit(tag, self.game(who)._hint_triggers({"h_field_lose", "h_lose"}))
            view = self.main(who)
            emit(f"{tag} 提示框", [view.get("guide") if isinstance(view, dict) else None, self.game(who).guide_box()])

    def boards(self) -> None:
        """榜（懸賞榜的「尋敵」「操練」字）：城裡、城外各看一次；有陣營的、散人。"""
        for who in ("閆臨淵", "魏無涯"):
            for where in filter(None, (self.town(), self.field())):
                self.place(who, where)
                self.call(who, "GET", "/api/boards")
                self.look_here(who, f"在{where}")

    def half(self) -> None:
        """切點：三位新人把 tutorial_step 手擺到 e2_drill、e4_field、e3_cultivate（步數 13）寫到一半，只看第一眼；後半再往下走。舊步數對應表（onboarding < 5）這一軌沒走到，真的新人建角色直接是 18。"""
        steps = [s.id for s in self.c.tutorial.steps]
        picks = [12, steps.index("e4_field") if "e4_field" in steps else len(steps) - 1, 13]
        for who, step in zip(self.NEWBIES, picks):
            self.fresh(who, "女")
            self.edit_state(who, lambda st: setattr(st, "pending_event", None))  # 開局端出來的那張卡先放掉
            self.edit(who, lambda p, step=step: (setattr(p, "tutorial_step", step), setattr(p, "location", self.town() or p.location),
                                                 p.visited.add(p.location)))  # 出了草廬（初入江湖的步驟在城裡才算）
            view = self.main(who)
            emit(f"{who} 切點", {"step": self.chars.load(who).player.tutorial_step, "options": sorted(self.ids(view)),
                               "guide": self.game(who).guide_box()})

    # ── 後半 ──

    def answer(self) -> None:
        """新程式接著走完那三位的初入江湖：第一個可按的選項往下，最多六步。"""
        for who in self.NEWBIES:
            for _ in range(6):
                opts = self.ids(self.main(who))
                pick = next((i for i, o in sorted(opts.items()) if o.get("enabled") and not i.startswith(("act:rest", "move", "map"))), None)
                if pick is None:
                    break
                self.choose(who, pick)
                self.settle_choices(who)
            self.me(who, "接手之後")

    def again(self) -> None:
        """接手之後再走一遍：設定那一行、季曆、新手目標、提示。"""
        self.settings()
        self.calendar_view()
        self.goals()
        self.field_lose()

    def season(self) -> None:
        """收季、開下一季：新的一季蓋章之後的設定、季曆與說明；新人的目標與選單。"""
        self.do(ADMIN, "end_season")
        self.main("魏無涯")
        self.do(ADMIN, "next_season")
        self.settings()
        self.calendar_view()
        for who in ("魏無涯", "仲孫澈", self.NEWBIE):
            self.look_here(who, "換季之後")
            self.call(who, "GET", "/api/howto")
            emit(f"{who} 換季之後的目標", self.game(who).newbie_view())


register_track("shut", ShutScenario, (("tianxia/features/guide/newbie.py",),
                                      ("到匪寇橫行的地方出門探索，打贏一場", "到匪寇橫行的地方出門探索，打贏兩場")), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "hire", "legacy", "looks", "mall", "map",
                       "military", "notify", "outlets", "peers", "persona", "seal", "seclusion", "sense", "smithy", "socialize",
                       "sortie", "stamina_plays", "story", "tale", "tavern", "territory_acts", "travel", "zhuan"))
