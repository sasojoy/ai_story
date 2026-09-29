"""遊戲門面：介面層唯一需要呼叫的類別。負責行動、選項、時間流逝與畫面文字。"""
from __future__ import annotations

import random

from pydantic import BaseModel

from . import atlas, battlelog, journal, skillview, team
from .events import choice_label, has_events_here, pick_event, visible_choices
from .guide import note_action, quest_text, tutorial_intro
from .journal import LOG_BREAK, Draft
from .mapview import render_map, render_minimap
from .models import Choice, Content, Effect, Event, Location, Squad
from .rules import apply_effect, change_trend, check_who, learn_skill, roll_check
from .state import PLAYER, BattleRecord, GameState, JournalEntry, Member, Rumor, new_game_state
from .world import check_thresholds, end_season, sim_tick

HOUR = 3600
DAY = 86400


class Option(BaseModel):
    id: str
    label: str
    enabled: bool = True


class Game:
    FREE_SLOTS = team.FREE_SLOTS
    MAP_LAYERS = atlas.LAYERS  # 大地圖的圖層：id → 名稱

    def __init__(self, content: Content, state: GameState, rng: random.Random | None = None):
        self.content = content
        self.state = state
        self.rng = rng or random.Random()
        self._odds: dict[str, str] = {}  # 勝算快取，見 team.estimate
        self._draft: Draft | None = None  # choose() 進行中那次行動的江湖紀錄草稿
        self._drop_stale_references()

    @classmethod
    def new(cls, content: Content, name: str, rng: random.Random | None = None) -> Game:
        game = cls(content, new_game_state(content, name), rng)
        cfg, p = content.config, game.state.player
        for skill_id in cfg.starter_skills:
            learn_skill(game.state, content, skill_id)
        if cfg.player_innate:
            learn_skill(game.state, content, cfg.player_innate)
        free = [s for s in cfg.starter_skills if s != cfg.player_innate]
        p.loadouts[PLAYER] = (free + [None] * team.FREE_SLOTS)[: team.FREE_SLOTS]
        p.visited.add(p.location)
        game._log(
            [f"══ {content.scenario.name} ══", content.scenario.intro, game.location_text()]
            + tutorial_intro(content)
        )
        game._write(content.scenario.name, [content.scenario.intro] + tutorial_intro(content), tag="賽季開始")
        return game

    def _drop_stale_references(self) -> None:
        """內容檔改版後，舊存檔可能引用已刪除的事件、地點、武學或人物；丟掉這些引用以免當機。"""
        s, c = self.state, self.content
        p = s.player
        if s.pending_event and s.pending_event not in c.events:
            s.pending_event = None
        if p.location not in c.locations:
            p.location = c.scenario.start_location
        p.skills = {k: v for k, v in p.skills.items() if k in c.skills}
        p.members = {k: m for k, m in p.members.items() if k == PLAYER or k in c.characters}
        p.members.setdefault(PLAYER, Member())
        p.team = [k for k in p.team if k in p.members][:3] or [PLAYER]
        p.loadouts = {
            k: [sid if sid in p.skills else None for sid in slots][: team.FREE_SLOTS]
            for k, slots in p.loadouts.items() if k in p.members
        }
        line_ids = [line.id for line in c.scenario.storylines]
        if s.world.storyline not in line_ids:
            s.world.storyline, s.world.act = line_ids[0], 0
        acts = next(line for line in c.scenario.storylines if line.id == s.world.storyline).acts
        s.world.act = min(s.world.act, len(acts) - 1)
        if "tutorial_step" not in p.model_fields_set:
            # 舊存檔在新手引導功能上線前就存在，沒有這個欄位；視為引導已完成，不強塞新手引導。
            p.tutorial_step = len(c.tutorial.steps)
        p.tutorial_step = min(p.tutorial_step, len(c.tutorial.steps))
        p.visited = {loc_id for loc_id in p.visited if loc_id in c.locations}
        p.visited.add(p.location)
        for rumor in s.world.rumors:
            if rumor.location is not None and rumor.location not in c.locations:
                rumor.location = None  # 傳聞的發生地已從內容裡刪掉：傳聞留著，只是不再標在地圖上
        for flag in s.world.flags:
            if flag not in s.world.flag_times:
                s.world.flag_times[flag] = s.world.time
        if battlelog.find(s, s.battle_card) is None:
            s.battle_card = None
        if not s.journal and s.log:
            # 江湖紀錄上線前的存檔只有原始訊息：轉一次成簡單的紀錄，之後照新的方式寫。
            s.journal = journal.from_legacy_log(s.log)

    # ── 時間 ──────────────────────────────────────────────

    def sync(self, now: float) -> list[str]:
        """把現實經過的時間（乘上 time_scale）推進到遊戲裡。第一次呼叫只記錄時間點。"""
        if self.state.last_real is None:
            self.state.last_real = now
            return []
        elapsed = max(0.0, now - self.state.last_real) * self.content.config.time_scale
        self.state.last_real = now
        return self.advance(elapsed)

    def advance(self, seconds: float) -> list[str]:
        """時間流逝。平常不寫江湖紀錄；發生江湖大事或主線變化時寫一則「江湖大事」（連續的併成一則），
        閉關時間到了寫一則「出關」（見 _finish_seclusion）。"""
        msgs: list[str] = []
        remaining = seconds
        while remaining > 0 and not self.state.world.ended:
            step = min(remaining, HOUR)
            remaining -= step
            msgs += self._advance_step(step)
        news = journal.news_entry(self.state.world.time, msgs)
        if news is not None:
            journal.add_entry(self.state, news, merge=True)
        return self._log(msgs)

    def _advance_step(self, seconds: float) -> list[str]:
        cfg, p, w = self.content.config, self.state.player, self.state.world
        w.time += seconds
        p.stamina = min(cfg.stamina_max, p.stamina + seconds / cfg.stamina_regen_seconds)
        rate = seconds / (cfg.neili_regen_hours * HOUR)
        if p.busy_until is not None:
            rate *= 2  # 閉關時內力回復加倍
        if w.time <= cfg.newbie_days * DAY:
            rate *= 2  # 新手期加倍
        team.regen_neili(self.state, self.content, rate)
        msgs: list[str] = []
        if p.busy_until is not None and w.time >= p.busy_until:
            msgs += self._finish_seclusion(p.busy_until)
        w.sim_accum += seconds
        hours = int(w.sim_accum // HOUR)
        if hours:
            w.sim_accum -= hours * HOUR
            msgs += sim_tick(self.state, self.content, hours, self.rng)
        if not w.ended and w.time >= cfg.season_days * DAY:
            msgs += end_season(self.state, self.content)
        return msgs

    # ── 選項 ──────────────────────────────────────────────

    def options(self, odds: bool = True) -> list[Option]:
        """目前可選的行動。odds=False 時不附勝算、也就不必模擬（choose() 與機器人只看 id）。"""
        s, c = self.state, self.content
        if s.world.ended:
            return [Option(id="season:new", label="開啟新的賽季")]
        if s.pending_event:
            event = c.events[s.pending_event]
            return [Option(id=f"choice:{i}", label=self._choice_label(ch, odds)) for i, ch in visible_choices(event, s)]
        if s.player.busy_until is not None:
            return [Option(id="act:break", label="提前出關")]
        loc = c.locations[s.player.location]
        cost = c.config.action_cost
        opts = []
        if loc.enemies:
            opts.append(self._cost_option("act:train", "歷練", cost["train"], self._train_note(loc) if odds else ""))
        opts.append(self._cost_option("act:explore", "探索", cost["explore"]))
        if has_events_here(c, loc, "socialize"):
            opts.append(self._cost_option("act:socialize", "交遊", cost["socialize"]))
        for dest_id in loc.connections:
            dest = c.locations[dest_id]
            if dest.unlock_flag and dest.unlock_flag not in s.world.flags:
                continue
            opts.append(self._cost_option(f"move:{dest_id}", f"前往 {dest.name}", dest.move_cost))
        return opts

    def _cost_option(self, option_id: str, label: str, cost: int, note: str = "") -> Option:
        extra = f"・{note}" if note else ""
        return Option(
            id=option_id, label=f"{label}（體力 {cost}{extra}）", enabled=self.state.player.stamina >= cost
        )

    def _train_note(self, loc: Location) -> str:
        """歷練按鈕上的戰前情報，例如「可能遇到：地痞無賴 穩勝、劫道山賊 穩勝」。"""
        foes = [f"{self.content.squads[sid].name} {self.odds(sid)}" for sid in dict.fromkeys(loc.enemies)]
        return "可能遇到：" + "、".join(foes)

    def _choice_label(self, choice: Choice, odds: bool) -> str:
        """動手的選項寫出對手與勝算，例如「拔劍闖進去（對手：太湖水寇・有把握）」；其餘見 choice_label。"""
        if choice.combat and odds:
            squad = self.content.squads[choice.combat]
            return f"{choice.text}（對手：{squad.name}・{self.odds(squad.id)}）"
        return choice_label(choice, self.state, self.content)

    def odds(self, squad_id: str) -> str:
        """出戰隊伍對上這支敵方隊伍的勝算：穩勝／有把握／五五波／凶險／必敗。"""
        return team.estimate(self.state, self.content, squad_id, self._odds)

    def choose(self, option_id: str) -> list[str]:
        option = {o.id: o for o in self.options(odds=False)}.get(option_id)
        if option is None or not option.enabled:
            return self._log(["（此刻無法這麼做。）"])
        self.state.battle_card = None  # 上一場的戰鬥卡片只留到下一次行動
        kind, _, arg = option_id.partition(":")
        if kind == "season":  # 新賽季的開場紀錄由 Game.new 寫好
            return self._log(self.new_season() + check_thresholds(self.state, self.content))
        self._draft = Draft(self._action_title(kind, arg))
        try:
            if kind == "act":
                msgs = self._act(arg)
            elif kind == "move":
                msgs = self._move(arg)
            else:
                msgs = self._choose(int(arg))
            if kind == "act" and arg != "break":
                msgs += note_action(self.state, self.content, arg)
            elif kind == "move":
                msgs += note_action(self.state, self.content, "move")
            msgs += check_thresholds(self.state, self.content)
            journal.add_entry(self.state, self._draft.entry(self.state.world.time, msgs))
        finally:
            self._draft = None
        return self._log(msgs)

    def _action_title(self, kind: str, arg: str) -> str:
        """這次行動在江湖紀錄裡的標題：「前往 揚州城」「探索揚州城」「交遊・揚州城」「歷練・揚州城郊」、
        「酒樓鬥毆・上前勸架」（事件標題・選項）或「提前出關」。"""
        s, c = self.state, self.content
        if kind == "move":
            return f"前往 {c.locations[arg].name}"
        if kind == "choice":
            event = c.events[s.pending_event]
            return f"{event.title}・{event.choices[int(arg)].text}"
        here = c.locations[s.player.location].name
        return {"explore": f"探索{here}", "socialize": f"交遊・{here}", "train": f"歷練・{here}"}.get(arg, "提前出關")

    def _hide(self, msg: str) -> None:
        """這則訊息不寫進江湖紀錄（場景已經顯示，或已經寫在標題裡）。"""
        if self._draft is not None:
            self._draft.hide(msg)

    def _outcome(self, text: str, msg: str) -> None:
        """這則訊息是這次行動的結果，在江湖紀錄裡寫成 text（見 journal.Draft.outcome）。"""
        if self._draft is not None:
            self._draft.outcome(text, msg)

    def _write(self, title: str, msgs: list[str], tag: str = "") -> None:
        """不經過 choose() 的行動（開場、閉關、系統訊息……）直接寫一則江湖紀錄。"""
        journal.add_entry(self.state, Draft(title, tag).entry(self.state.world.time, msgs))

    # ── 行動 ──────────────────────────────────────────────

    def _act(self, what: str) -> list[str]:
        cost = self.content.config.action_cost
        if what == "break":
            return self._finish_seclusion(self.state.world.time)
        self.state.player.stamina -= cost[what]
        if what == "train":
            return self._train()
        if what == "explore":
            return self._encounter("explore", "你四處走走，一無所獲。")
        return self._encounter("socialize", "此地無人可訪，你只好悻悻離去。")

    def _encounter(self, action: str, nothing: str) -> list[str]:
        event = pick_event(self.state, self.content, action, self.rng)
        return self._present(event) if event else [nothing]

    def _present(self, event: Event) -> list[str]:
        self.state.pending_event = event.id
        self.state.player.seen_events.add(event.id)
        head = f"✦ 奇遇：{event.title}" if event.qiyu else f"【{event.title}】"
        self._outcome(journal.event_marker(event.title, event.qiyu), head)
        self._hide(event.text)  # 事件的開場由場景顯示
        return [head, event.text]

    def _train(self) -> list[str]:
        """歷練：勝得對手獎勵、屬性機會與大勢變化；敗失落一成銀兩；平手無獎懲。"""
        s, c = self.state, self.content
        p = s.player
        loc = c.locations[p.location]
        squad = c.squads[self.rng.choice(loc.enemies)]
        result = team.fight(s, c, squad.id, self.rng)
        record = battlelog.new_record(s, c, squad, result, "train")
        msgs: list[str] = []
        if result.outcome == "win":
            msgs += self._battle_rewards(squad, record)
            extra: list[str] = []
            if self.rng.random() < c.config.train_stat_chance:
                key = self.rng.choice(["str", "agi", "con"])
                p.stats[key] += 1
                extra.append(f"{c.config.stat_names[key]} +1")
            for trend_id, delta in loc.train_trend.items():
                extra += change_trend(s, c, trend_id, delta)
            changes, notes = battlelog.split_changes(extra)
            record.changes += changes
            record.notes += notes
            msgs += extra
        elif result.outcome == "lose":
            loss = p.stats["silver"] // 10
            p.stats["silver"] -= loss
            record.silver = -loss
            if loss:
                msgs.append(f"銀兩 -{loss}")
        msgs.insert(0, self._file_battle(record))
        if self.rng.random() < c.config.train_event_chance:
            event = pick_event(s, c, "train", self.rng)
            if event:
                msgs += self._present(event)
        return msgs

    def _battle_rewards(self, squad: Squad, record: BattleRecord) -> list[str]:
        """打贏時發對手獎勵（銀兩、心得、每人經驗），同時記進戰鬥紀錄。"""
        p = self.state.player
        msgs = []
        if squad.reward_silver:
            p.stats["silver"] += squad.reward_silver
            record.silver = squad.reward_silver
            msgs.append(f"銀兩 +{squad.reward_silver}")
        if squad.reward_xinde:
            p.stats["xinde"] = p.stats.get("xinde", 0) + squad.reward_xinde
            record.xinde = squad.reward_xinde
            msgs.append(f"心得 +{squad.reward_xinde}")
        record.exp = squad.exp
        levels = team.add_exp(self.state, self.content, squad.exp)
        record.notes += levels
        return msgs + levels

    def _file_battle(self, record: BattleRecord) -> str:
        """把戰鬥紀錄存進歷史、場景顯示它的卡片；回傳紀錄裡的一行摘要。
        江湖紀錄裡這一則的結果標記寫成「擊退劫道山賊（4 回合）」，並補上每人獲得的經驗。"""
        battlelog.add_record(self.state, record)
        self.state.battle_card = record.id
        line = battlelog.summary_line(record)
        if self._draft is not None:
            self._draft.outcome(battlelog.outcome_text(record), line)
            self._draft.battle_id = record.id
            if record.exp:
                self._draft.changes.append(f"經驗 +{record.exp}（每人）")  # 寫法和卡片的獲得與損失一致
        return line

    def _move(self, dest_id: str) -> list[str]:
        dest = self.content.locations[dest_id]
        self.state.player.stamina -= dest.move_cost
        self.state.player.location = dest_id
        self.state.player.visited.add(dest_id)
        text = self.location_text()
        self._hide(text)  # 地點描述由場景顯示
        return [text]

    def travel(self, dest_id: str) -> list[str]:
        """大地圖的「安排前往」：沿最省體力的路一站一站走，每站照常扣體力、檢查新手引導的移動步驟與大勢門檻；
        下一站體力不夠就停在已抵達的地方。整趟只寫一則江湖紀錄：「前往 高郵湖（途經 揚州城郊）」，
        中途停下時寫「前往 太湖水寨（體力不足，停在 鎮江渡口）」。不能前往時只回傳原因，不動、也不寫紀錄。"""
        s, c = self.state, self.content
        button = atlas.travel_button(s, c, dest_id) if dest_id in c.locations else None
        if button is None or not button[1]:
            return self._log([f"（{button[0] if button else '無法安排前往這裡'}。）"])
        route = atlas.routes(s, c)[dest_id]
        s.battle_card = None  # 和其他行動一樣，上一場的戰鬥卡片到此為止
        self._draft = Draft(f"前往 {c.locations[dest_id].name}")
        try:
            msgs: list[str] = []
            for hop in route.path:
                if s.player.stamina < c.locations[hop].move_cost:
                    break
                msgs += self._move(hop)
                msgs += note_action(s, c, "move")
                msgs += check_thresholds(s, c)
            self._draft.title = self._travel_title(dest_id, route)
            journal.add_entry(s, self._draft.entry(s.world.time, msgs))
        finally:
            self._draft = None
        return self._log(msgs)

    def _travel_title(self, dest_id: str, route: atlas.Route) -> str:
        c, here = self.content, self.state.player.location
        title = f"前往 {c.locations[dest_id].name}"
        if here != dest_id:
            return f"{title}（體力不足，停在 {c.locations[here].name}）"
        if route.via:
            return f"{title}（途經 {'、'.join(c.locations[loc_id].name for loc_id in route.via)}）"
        return title

    def _choose(self, index: int) -> list[str]:
        s, c = self.state, self.content
        event = c.events[s.pending_event]
        choice = event.choices[index]
        s.pending_event = None
        msgs = [f"▸ {choice.text}"]
        self._hide(msgs[0])  # 選項已經寫在標題裡
        if choice.combat:
            return msgs + self._event_battle(event, choice)
        if choice.check:
            who = check_who(choice.check, s, c)
            success = roll_check(choice.check, s, c, self.rng)
            word = "成功" if success else "失敗"
            msgs.append(f"（{who}——{word}）")
            self._outcome(f"{who}・{word}", msgs[-1])
            return msgs + self._apply(choice.effect if success else choice.fail_effect)
        return msgs + self._apply(choice.effect)

    def _event_battle(self, event: Event, choice: Choice) -> list[str]:
        """劇情戰：勝得對手獎勵並走該選項的劇情結果；敗或平手（沒打贏）走失敗分支。"""
        s, c = self.state, self.content
        squad = c.squads[choice.combat]
        result = team.fight(s, c, squad.id, self.rng)
        record = battlelog.new_record(s, c, squad, result, "event", event.title)
        won = result.outcome == "win"
        rewards = self._battle_rewards(squad, record) if won else []
        effect = choice.effect if won else choice.fail_effect
        story = apply_effect(effect, s, c)
        changes, notes = battlelog.split_changes(story)
        record.changes += changes
        record.notes += notes
        msgs = [self._file_battle(record)] + rewards + story
        if effect.next_event:
            msgs += self._present(c.events[effect.next_event])
        return msgs

    def _apply(self, effect: Effect) -> list[str]:
        msgs = apply_effect(effect, self.state, self.content)
        if effect.next_event:
            msgs += self._present(self.content.events[effect.next_event])
        return msgs

    # ── 閉關、門下、設定 ─────────────────────────────────

    def _idle(self) -> bool:
        s = self.state
        return not s.world.ended and s.pending_event is None and s.player.busy_until is None

    def seclude(self, hours: int) -> list[str]:
        p = self.state.player
        if not self._idle():
            msgs = ["你現在無法閉關。"]
            self._write("閉關", msgs)
            return self._log(msgs)
        hours = max(1, min(12, int(hours)))
        self.state.battle_card = None
        p.busy_until = self.state.world.time + hours * HOUR
        p.seclusion_start = self.state.world.time
        msgs = [f"你閉關靜修，預計 {hours} 小時後出關；閉關期間內力回復加倍。"]
        self._write("閉關", msgs, tag=f"{hours} 小時")
        return self._log(msgs)

    def _finish_seclusion(self, end_time: float) -> list[str]:
        """出關並發心得。按「提前出關」時寫進那次行動的紀錄；時間到了自己出關時另寫一則「出關」。"""
        p, cfg = self.state.player, self.content.config
        hours = (end_time - p.seclusion_start) / HOUR
        amount = round(hours * cfg.seclusion_xinde_per_hour * (1 + p.stats["wis"] / 20))
        p.busy_until = None
        p.stats["xinde"] = p.stats.get("xinde", 0) + amount
        msg = f"你結束閉關（{hours:.1f} 小時），心得 +{amount}。"
        tag, change = f"{hours:.1f} 小時", f"心得 +{amount}"
        if self._draft is not None:
            self._draft.outcome(tag, msg)
            self._draft.changes.append(change)
        else:
            journal.add_entry(self.state, JournalEntry(time=end_time, title="出關", tag=tag, changes=[change]))
        return [msg]

    # 門下的操作只有真的改了東西才寫江湖紀錄，連續幾次併成一則；「心得不足」這類失敗訊息由門下頁面自己顯示。

    def upgrade(self, target: str) -> list[str]:
        level, xinde = team.target_level(self.state, self.content, target), self._xinde()
        msgs = self._log(team.upgrade(self.state, self.content, target))
        now = team.target_level(self.state, self.content, target)
        if now != level:
            self._menxia_entry(f"【{team.target_name(self.state, self.content, target)}】精進至第{now}成", xinde)
        return msgs

    def dispel(self, target: str) -> list[str]:
        level, xinde = team.target_level(self.state, self.content, target), self._xinde()
        msgs = self._log(team.dispel(self.state, self.content, target))
        if team.target_level(self.state, self.content, target) != level:
            self._menxia_entry(f"【{team.target_name(self.state, self.content, target)}】散功，退回第一成", xinde)
        return msgs

    def set_loadout(self, member: str, slot: int, skill_id: str | None) -> list[str]:
        before = {key: list(slots) for key, slots in self.state.player.loadouts.items()}
        msgs = self._log(team.set_loadout(self.state, self.content, member, slot, skill_id))
        if self.state.player.loadouts != before:
            self._menxia_entry(msgs[0], self._xinde())
        return msgs

    def _xinde(self) -> int:
        return self.state.player.stats.get("xinde", 0)

    def _menxia_entry(self, tag: str, xinde_before: int) -> None:
        delta = self._xinde() - xinde_before
        changes = [f"心得 {delta:+d}"] if delta else []
        entry = JournalEntry(time=self.state.world.time, title=journal.MENXIA, tag=tag, changes=changes)
        journal.add_entry(self.state, entry, merge=True)

    def upgrade_options(self) -> list[tuple[str, str]]:
        return team.upgrade_options(self.state, self.content)

    def team_members(self) -> list[tuple[str, str]]:
        return [(team.member_name(self.state, self.content, key), key) for key in self.state.player.team]

    # ── 門下頁面 ──────────────────────────────────────────

    def skill_library(self) -> list[tuple[str, str]]:
        return skillview.library(self.state, self.content)

    def skill_detail(self, target: str | None) -> str:
        return skillview.detail(self.state, self.content, target)

    def member_card(self, key: str) -> str:
        return skillview.member_card(self.state, self.content, key)

    def slot_label(self, key: str, slot: int | None) -> str:
        return skillview.slot_label(self.state, self.content, key, slot)

    def menxia_rules(self) -> str:
        return skillview.rules_line(self.content)

    def innate_target(self, key: str) -> str | None:
        return team.innate_target(self.state, self.content, key)

    def is_innate(self, target: str) -> bool:
        return team.is_innate(self.content, target)

    def slot_skill(self, key: str, slot: int) -> str | None:
        return team.slot_skill(self.state, key, slot)

    def upgrade_cost(self, target: str) -> int | None:
        """升一成要花的心得；已達第十成或沒有這門武學時回傳 None。"""
        level = team.target_level(self.state, self.content, target)
        if level is None or level >= team.MAX_SKILL_LEVEL:
            return None
        return team.upgrade_cost(self.content, level)

    def dispel_refund(self, target: str) -> int | None:
        """散功會返還的心得；本命、第一成或沒有這門武學（散不了功）時回傳 None。"""
        level = team.target_level(self.state, self.content, target)
        if level is None or level <= 1 or team.is_innate(self.content, target):
            return None
        return team.dispel_refund(self.content, level)

    # ── 戰鬥紀錄 ──────────────────────────────────────────

    def battle_card(self) -> str | None:
        """場景裡的戰鬥卡片（Markdown）；這次行動沒有打仗時為 None。"""
        record = battlelog.find(self.state, self.state.battle_card)
        return battlelog.card_text(record) if record else None

    def battle_card_id(self) -> int | None:
        """卡片上那一場的流水號；沒有卡片時為 None。"""
        record = battlelog.find(self.state, self.state.battle_card)
        return record.id if record else None

    def latest_battle_id(self) -> int | None:
        return self.state.battles[0].id if self.state.battles else None

    def battle_list(self) -> list[tuple[str, int]]:
        """戰報列表：（「勝　第1天 08:30　揚州城郊　vs 劫道山賊　4 回合」, 流水號），最新的在前。"""
        return [(battlelog.list_label(r), r.id) for r in self.state.battles]

    def battle_detail(self, record_id: int | None = None) -> str:
        """某一場的完整戰報（Markdown）；沒指定或找不到時顯示最新一場。"""
        s = self.state
        record = battlelog.find(s, record_id) or (s.battles[0] if s.battles else None)
        return battlelog.detail_text(record) if record else battlelog.NO_RECORD

    def notice(self, text: str, title: str = "提醒") -> list[str]:
        """介面層要告訴玩家的系統訊息（例如舊存檔已備份）；title 是江湖紀錄裡這一則的標題。"""
        self._write(title, [text])
        return self._log([text])

    def set_anonymous(self, value: bool) -> None:
        self.state.player.anonymous = bool(value)

    def skip_tutorial(self) -> list[str]:
        """設定裡的「略過新手引導」：直接跳到引導結束。引導早就結束時什麼都不做。"""
        steps = len(self.content.tutorial.steps)
        if self.state.player.tutorial_step >= steps:
            return []
        self.state.player.tutorial_step = steps
        self._write("新手引導", [], tag="已略過")
        return self._log(["（已略過新手引導。）"])

    def view_map(self) -> list[str]:
        """介面打開大地圖時呼叫。不論新手引導是否還在「按『大地圖』看看」那一步，都先記下玩家看過地圖。
        平常看地圖不寫江湖紀錄；只有剛好完成一步新手引導時，才記下引導的獎勵與下一步。"""
        self.state.player.flags.add("看過地圖")
        msgs = note_action(self.state, self.content, "view_map")
        if msgs:
            self._write("翻看地圖", msgs)
        return self._log(msgs)

    def quest_text(self) -> str:
        return quest_text(self.state, self.content)

    # ── 大地圖 ────────────────────────────────────────────

    def world_map_svg(self, layer: str = "situation", selected: str | None = None) -> str:
        """大地圖（SVG）。只有敵情層會算勝算（摸清地點的對手，快取在 Game._odds）；其餘圖層與平常重畫都不模擬。"""
        odds = self.odds if layer == "enemies" else None
        return render_map(self.state, self.content, layer, selected, odds)

    def minimap_svg(self) -> str:
        """場景旁的大區小地圖（SVG）；地圖沒有大區時是空字串。"""
        return render_minimap(self.state, self.content)

    def map_header(self) -> str:
        """大地圖頁面上方的時間與體力。"""
        return atlas.header_text(self.state, self.content)

    def map_places(self) -> list[tuple[str, str]]:
        """大地圖下拉選單：（顯示文字, 地點 id），只列摸清的地點與畫出名字的未知地點。"""
        return atlas.place_choices(self.state, self.content)

    def place_detail(self, loc_id: str) -> str:
        """詳情欄（Markdown）。摸清而且有敵人的地點會算勝算（快取在 Game._odds）。"""
        return atlas.detail_text(self.state, self.content, loc_id, self.odds)

    def travel_button(self, loc_id: str) -> tuple[str, bool] | None:
        """「安排前往」按鈕的（文字, 按得下去）；不該顯示按鈕時為 None。"""
        return atlas.travel_button(self.state, self.content, loc_id)

    def new_season(self) -> list[str]:
        last_real = self.state.last_real
        tutorial_step = self.state.player.tutorial_step
        self.state = Game.new(self.content, self.state.player.name, self.rng).state
        self.state.last_real = last_real
        self.state.player.tutorial_step = tutorial_step
        return []

    # ── 畫面文字 ──────────────────────────────────────────

    def location_text(self) -> str:
        loc = self.content.locations[self.state.player.location]
        return f"【{loc.name}】危險 {'★' * loc.danger}\n\n{loc.description}"

    def scene_text(self) -> str:
        s, c = self.state, self.content
        if s.world.ended:
            return f"## {s.world.ending_title}\n\n{s.world.ending_text}"
        if s.pending_event:
            event = c.events[s.pending_event]
            return f"**{event.title}**\n\n{event.text}"
        return self.location_text()

    def status_text(self) -> str:
        s, c = self.state, self.content
        p, w = s.player, s.world
        names = c.config.stat_names
        sect = c.sects[p.sect].name if p.sect else "散人"
        day = int(w.time // DAY) + 1
        clock = f"{int(w.time % DAY // HOUR):02d}:{int(w.time % HOUR // 60):02d}"
        lines = [
            f"### {p.name}　·　{sect}" + ("（匿名行走）" if p.anonymous else ""),
            f"📍 {c.locations[p.location].name}　⏳ 第 {day} 天 {clock}（本季共 {c.config.season_days:g} 天）",
            f"**體力** {int(p.stamina)} / {c.config.stamina_max}",
            "　".join(f"{names[k]} {p.stats[k]}" for k in ("str", "agi", "con", "wis")),
            "　".join(f"{names[k]} {p.stats.get(k, 0)}" for k in ("silver", "good", "evil", "fame", "xinde")),
            "**隊伍**",
        ]
        for i, key in enumerate(p.team):
            now, cap = team.member_neili(s, c, key)
            leader = "（隊長）" if i == 0 else ""
            lines.append(
                f"- {team.member_name(s, c, key)}{leader}　第{p.members[key].level}級　內力 {int(now)}/{int(cap)}"
            )
        if p.busy_until is not None:
            lines.append(f"🧘 閉關中，約 {(p.busy_until - w.time) / HOUR:.1f} 小時後出關")
        return "\n\n".join(lines)

    def trends_text(self) -> str:
        w = self.state.world
        parts = []
        for trend in self.content.scenario.trends:
            if trend.id not in w.revealed:
                continue
            value = w.trends[trend.id]
            bar = "█" * (value // 5) + "░" * (20 - value // 5)
            parts.append(f"**{trend.name}** {value}/100\n\n`{bar}`\n\n{trend.desc}")
        if w.ended:
            parts.append(f"## 結局：{w.ending_title}\n\n{w.ending_text}")
        return "\n\n".join(parts) or "（江湖暫時風平浪靜。）"

    def rumors_text(self, limit: int = 30) -> str:
        return _timeline(self.state.world.rumors[-limit:][::-1]) or "（尚無傳聞。）"

    def chronicle_text(self) -> str:
        return _timeline(self.state.world.chronicle) or "（江湖史尚無記載。）"

    # ── 江湖紀錄 ──────────────────────────────────────────

    def latest_entry_html(self) -> str:
        """左欄「剛剛」卡片：最新一則紀錄的完整內容（HTML）；還沒有紀錄時是空字串。"""
        entries = self.state.journal
        return journal.card_html(entries[0]) if entries else ""

    def journal_html(self, start: int = 1, limit: int = 5, heading: str = "", empty: str = "") -> str:
        """紀錄列（HTML）：從第 start 則（0＝最新）起最多 limit 則，一則一列；沒有東西可顯示時是空字串。"""
        return journal.rows_html(self.state.journal[start:start + limit], heading, empty)

    def shows_battle_card(self) -> bool:
        """「剛剛」那一格改放戰鬥卡片：卡片還在，而且最新一則紀錄就是打那一場的行動。"""
        s = self.state
        return self.battle_card_id() is not None and bool(s.journal) and s.journal[0].battle_id == s.battle_card

    def battle_extra_html(self) -> str:
        """顯示戰鬥卡片時放在卡片底下的補充（HTML）：同一次行動裡卡片沒寫到的敘事與數值變化，
        例如打完仗剛好完成的新手引導與它的獎勵；沒有顯示戰鬥卡片或沒有補充時是空字串。"""
        if not self.shows_battle_card():
            return ""
        record = battlelog.find(self.state, self.state.battle_card)
        lines, changes = journal.card_leftovers(self.state.journal[0], record.notes, battlelog.gains_list(record))
        return journal.extra_html(lines, changes)

    def _log(self, msgs: list[str]) -> list[str]:
        if not msgs:
            return msgs
        log = self.state.log
        log.extend(msgs)
        log.append(LOG_BREAK)
        overflow = len(log) - self.content.config.max_log
        if overflow > 0:
            del log[:overflow]
        return msgs


def _timeline(entries: list[Rumor]) -> str:
    return "\n\n".join(f"第{int(e.time // DAY) + 1}天　{e.text}" for e in entries)
