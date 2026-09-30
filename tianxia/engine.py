"""遊戲門面：介面層唯一需要呼叫的類別。負責行動、選項、時間流逝與畫面文字。

sanguo-companions 合併大幅重寫：拿掉 battle.py 的 3v3 全自動戰鬥、多隊派遣、招賢抽卡、
收徒系統，改成單次判定遭遇（encounter.py）、單一隊伍（最多 4 位同伴）、唯一同伴的
招募（roster.py）、練功兩種模式（team.py：自創功法／鍛鍊）。
"""
from __future__ import annotations

import random

from pydantic import BaseModel

from . import atlas, battlelog, journal, roster, skillview, team
from .events import choice_label, has_events_here, pick_event, visible_choices
from .guide import note_action, quest_text, tutorial_intro
from .journal import LOG_BREAK, Draft
from .mapview import render_map, render_minimap
from .models import Choice, Content, Effect, Event, Location, Squad
from .rules import apply_effect, change_trend, check_who, roll_check
from .state import GameState, JournalEntry, Rumor, new_game_state
from .world import check_thresholds, end_season, sim_tick
from .world_state import WorldStateStore

HOUR = 3600
DAY = 86400


class Option(BaseModel):
    id: str
    label: str
    enabled: bool = True


class Game:
    MAP_LAYERS = atlas.LAYERS  # 大地圖的圖層：id → 名稱

    def __init__(
        self, content: Content, state: GameState, rng: random.Random | None = None,
        world: WorldStateStore | None = None,
    ):
        self.content = content
        self.state = state
        self.rng = rng or random.Random()
        self.world = world or WorldStateStore()
        self._draft: Draft | None = None  # choose() 進行中那次行動的江湖紀錄草稿
        self._drop_stale_references()

    @classmethod
    def new(
        cls, content: Content, name: str, rng: random.Random | None = None, world: WorldStateStore | None = None,
    ) -> Game:
        game = cls(content, new_game_state(content, name), rng, world)
        p = game.state.player
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
        p.team = [k for k in p.team if k in c.characters][: team.MAX_TEAM_COMPANIONS]
        if p.member.neigong_id and p.member.neigong_id not in c.skills and not self.world.is_skill_name_taken(p.member.neigong_id):
            p.member.neigong_id = None
        if p.member.wugong_id and p.member.wugong_id not in c.skills and not self.world.is_skill_name_taken(p.member.wugong_id):
            p.member.wugong_id = None
        line_ids = [line.id for line in c.scenario.storylines]
        if s.world.storyline not in line_ids:
            s.world.storyline, s.world.act = line_ids[0], 0
        acts = next(line for line in c.scenario.storylines if line.id == s.world.storyline).acts
        s.world.act = min(s.world.act, len(acts) - 1)
        s.world.act_reached = max(s.world.act_reached, s.world.act)
        if "tutorial_step" not in p.model_fields_set:
            p.tutorial_step = len(c.tutorial.steps)
        p.tutorial_step = min(p.tutorial_step, len(c.tutorial.steps))
        p.visited = {loc_id for loc_id in p.visited if loc_id in c.locations}
        p.visited.add(p.location)
        for rumor in s.world.rumors:
            if rumor.location is not None and rumor.location not in c.locations:
                rumor.location = None
        for flag in s.world.flags:
            if flag not in s.world.flag_times:
                s.world.flag_times[flag] = s.world.time
        if battlelog.find(s, s.battle_card) is None:
            s.battle_card = None
        if not s.journal and s.log:
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
            rate *= 2
        if w.time <= cfg.newbie_days * DAY:
            rate *= 2
        team.regen_neili(self.content, p.member, rate)
        for cid in p.team:
            self.world.update_companion(cid, lambda progress: team.regen_neili(self.content, progress, rate))
        msgs: list[str] = []
        if p.busy_until is not None and w.time >= p.busy_until:
            msgs += self._finish_seclusion(p.busy_until)
        if roster.fortune_overdue(self.state, self.content):
            msgs += self._deliver_fortune()
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
        opts = [self._cost_option("act:practice", "練功", cost.get("train", 10))]
        opts.append(self._cost_option("act:explore", "探索", cost["explore"]))
        if has_events_here(c, loc, "socialize"):
            opts.append(self._cost_option("act:socialize", "交遊", cost["socialize"]))
        target = self._recruit_target()
        if target is not None:
            cfg = c.config
            opts.append(self._cost_option("act:recruit", f"招募【{c.characters[target].name}】", cfg.recruit_stamina))
        for dest_id in loc.connections:
            dest = c.locations[dest_id]
            if dest.unlock_flag and dest.unlock_flag not in s.world.flags:
                continue
            opts.append(self._cost_option(f"move:{dest_id}", f"前往 {dest.name}", dest.move_cost))
        return opts

    def _recruit_target(self) -> str | None:
        """這個地點目前能嘗試招募的人（自由之身、recruit_at 是這裡）；沒有就是 None。"""
        s, c = self.state, self.content
        for cid, ch in c.characters.items():
            if ch.kind == "recruitable" and ch.recruit_at == s.player.location and roster.owned_by(self.world, cid) is None:
                return cid
        return None

    def _cost_option(self, option_id: str, label: str, cost: int, note: str = "") -> Option:
        extra = f"・{note}" if note else ""
        return Option(
            id=option_id, label=f"{label}（體力 {cost}{extra}）", enabled=self.state.player.stamina >= cost
        )

    def _choice_label(self, choice: Choice, odds: bool) -> str:
        if choice.combat and odds:
            squad = self.content.squads[choice.combat]
            return f"{choice.text}（對手：{squad.name}・{self.odds(squad.id)}）"
        return choice_label(choice, self.state, self.content, self.world)

    def odds(self, squad_id: str) -> str:
        return team.estimate(self.state, self.content, self.world, squad_id)

    def choose(self, option_id: str) -> list[str]:
        option = {o.id: o for o in self.options(odds=False)}.get(option_id)
        if option is None or not option.enabled:
            return self._log(["（此刻無法這麼做。）"])
        self.state.battle_card = None
        kind, _, arg = option_id.partition(":")
        if kind == "season":
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
                msgs += note_action(self.state, self.content, self.world, arg)
            elif kind == "move":
                msgs += note_action(self.state, self.content, self.world, "move")
            msgs += check_thresholds(self.state, self.content)
            journal.add_entry(self.state, self._draft.entry(self.state.world.time, msgs))
        finally:
            self._draft = None
        return self._log(msgs)

    def _action_title(self, kind: str, arg: str) -> str:
        s, c = self.state, self.content
        if kind == "move":
            return f"前往 {c.locations[arg].name}"
        if kind == "choice":
            event = c.events[s.pending_event]
            return f"{event.title}・{event.choices[int(arg)].text}"
        here = c.locations[s.player.location].name
        titles = {
            "explore": f"探索{here}", "socialize": f"交遊・{here}", "practice": f"練功・{here}",
            "recruit": f"招募・{here}",
        }
        return titles.get(arg, "提前出關")

    def _hide(self, msg: str) -> None:
        if self._draft is not None:
            self._draft.hide(msg)

    def _outcome(self, text: str, msg: str) -> None:
        if self._draft is not None:
            self._draft.outcome(text, msg)

    def _write(self, title: str, msgs: list[str], tag: str = "") -> None:
        journal.add_entry(self.state, Draft(title, tag).entry(self.state.world.time, msgs))

    # ── 行動 ──────────────────────────────────────────────

    def _act(self, what: str) -> list[str]:
        cost = self.content.config.action_cost
        if what == "break":
            return self._finish_seclusion(self.state.world.time)
        if what == "recruit":
            return self._recruit()
        if what == "practice":
            return ["（請在「門下」頁選擇自創功法或鍛鍊。）"]
        self.state.player.stamina -= cost[what]
        if what == "explore":
            return self._encounter("explore", "你四處走走，一無所獲。")
        if roster.fortune_due(self.state, self.content):
            candidates = [cid for cid, ch in self.content.characters.items() if ch.kind == "recruitable"]
            if candidates and roster.owned_by(self.world, candidates[0]) is None:
                self.state.player.fortune = True
                cid = candidates[0]
                msgs = [f"你新立門戶不久，【{self.content.characters[cid].name}】主動前來結識。"]
                msgs += roster.recruit(self.state, self.content, self.world, cid)
                return msgs
            if self._draft is not None:
                self._draft.title, self._draft.tag = "福緣", "賀禮"
            return self._fortune_gift()
        return self._encounter("socialize", "此地無人可訪，你只好悻悻離去。")

    def _recruit(self) -> list[str]:
        target = self._recruit_target()
        if target is None:
            return ["（此地此刻沒有能招募的人。）"]
        self.state.player.stamina -= self.content.config.recruit_stamina
        return roster.attempt_recruit(self.state, self.content, self.world, target, self.rng)

    def _fortune_gift(self) -> list[str]:
        p = self.state.player
        amount = self.content.config.recruit_consolation_xinde
        p.fortune = True
        p.stats["xinde"] = p.stats.get("xinde", 0) + amount
        return ["江湖朋友聽說你新立門戶，送來一份賀禮。", f"心得 +{amount}"]

    def _deliver_fortune(self) -> list[str]:
        s, c = self.state, self.content
        s.player.fortune = True
        candidates = [cid for cid, ch in c.characters.items() if ch.kind == "recruitable"]
        free = [cid for cid in candidates if roster.owned_by(self.world, cid) is None]
        if not free:
            msgs = self._fortune_gift()
            self._write("福緣", msgs, tag="賀禮")
            return msgs
        cid = free[0]
        msgs = roster.recruit(s, c, self.world, cid)
        journal.add_entry(s, Draft(f"結識【{c.characters[cid].name}】", "福緣").entry(s.world.time, msgs))
        return msgs

    def _encounter(self, action: str, nothing: str) -> list[str]:
        event = pick_event(self.state, self.content, action, self.rng)
        if event:
            return self._present(event)
        loc = self.content.locations[self.state.player.location]
        if action == "explore" and loc.enemies and self.rng.random() < self.content.config.train_event_chance:
            return self._squad_encounter(self.rng.choice(loc.enemies))
        return [nothing]

    def _present(self, event: Event) -> list[str]:
        self.state.pending_event = event.id
        self.state.player.seen_events.add(event.id)
        head = f"✦ 奇遇：{event.title}" if event.qiyu else f"【{event.title}】"
        self._outcome(journal.event_marker(event.title, event.qiyu), head)
        self._hide(event.text)
        return [head, event.text]

    def _squad_encounter(self, squad_id: str) -> list[str]:
        """遭遇一支敵方隊伍：單次判定，勝得對手獎勵與屬性機會，落敗失落一成銀兩。"""
        s, c = self.state, self.content
        p = s.player
        loc = c.locations[p.location]
        squad = c.squads[squad_id]
        result = team.fight(s, c, self.world, squad.id, self.rng)
        record = battlelog.new_record(s, c, self.world, squad, result, "train")
        msgs: list[str] = []
        if result.tier in team.WIN_TIERS:
            rewards = self._battle_rewards(squad, record)
            msgs += rewards
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
        elif result.tier == "落敗":
            loss = p.stats["silver"] // 10
            p.stats["silver"] -= loss
            record.silver = -loss
            if loss:
                msgs.append(f"銀兩 -{loss}")
        msgs.insert(0, self._file_battle(record))
        return msgs

    def _battle_rewards(self, squad: Squad, record) -> list[str]:
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
        levels = team.add_exp(self.content, p.member, squad.exp, p.name)
        record.notes += levels
        return msgs + levels

    def _file_battle(self, record) -> str:
        battlelog.add_record(self.state, record)
        self.state.battle_card = record.id
        line = battlelog.summary_line(record)
        if self._draft is not None:
            self._draft.outcome(battlelog.outcome_text(record), line)
            self._draft.battle_id = record.id
            if record.exp:
                self._draft.changes.append(f"經驗 +{record.exp}（每人）")
        return line

    def _move(self, dest_id: str) -> list[str]:
        dest = self.content.locations[dest_id]
        self.state.player.stamina -= dest.move_cost
        self.state.player.location = dest_id
        self.state.player.visited.add(dest_id)
        text = self.location_text()
        self._hide(text)
        return [text]

    def travel(self, dest_id: str) -> list[str]:
        s, c = self.state, self.content
        button = atlas.travel_button(s, c, dest_id) if dest_id in c.locations else None
        if button is None or not button[1]:
            return self._log([f"（{button[0] if button else '無法安排前往這裡'}。）"])
        route = atlas.routes(s, c)[dest_id]
        s.battle_card = None
        self._draft = Draft(f"前往 {c.locations[dest_id].name}")
        try:
            msgs: list[str] = []
            for hop in route.path:
                if s.world.ended or s.player.stamina < c.locations[hop].move_cost:
                    break
                msgs += self._move(hop)
                msgs += note_action(s, c, self.world, "move")
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
            why = "賽季落幕" if self.state.world.ended else "體力不足"
            return f"{title}（{why}，停在 {c.locations[here].name}）"
        if route.via:
            return f"{title}（途經 {'、'.join(c.locations[loc_id].name for loc_id in route.via)}）"
        return title

    def _choose(self, index: int) -> list[str]:
        s, c = self.state, self.content
        event = c.events[s.pending_event]
        choice = event.choices[index]
        s.pending_event = None
        msgs = [f"▸ {choice.text}"]
        self._hide(msgs[0])
        if choice.combat:
            return msgs + self._event_battle(event, choice)
        if choice.check:
            who = check_who(choice.check, s, c, self.world)
            success = roll_check(choice.check, s, c, self.world, self.rng)
            word = "成功" if success else "失敗"
            msgs.append(f"（{who}——{word}）")
            self._outcome(f"{who}・{word}", msgs[-1])
            return msgs + self._apply(choice.effect if success else choice.fail_effect)
        return msgs + self._apply(choice.effect)

    def _event_battle(self, event: Event, choice: Choice) -> list[str]:
        s, c = self.state, self.content
        squad = c.squads[choice.combat]
        result = team.fight(s, c, self.world, squad.id, self.rng)
        record = battlelog.new_record(s, c, self.world, squad, result, "event", event.title)
        won = result.tier in team.WIN_TIERS
        rewards = self._battle_rewards(squad, record) if won else []
        effect = choice.effect if won else choice.fail_effect
        story = apply_effect(effect, s, c, self.world)
        changes, notes = battlelog.split_changes(story)
        record.changes += changes
        record.notes += notes
        msgs = [self._file_battle(record)] + rewards + story
        if effect.next_event:
            msgs += self._present(c.events[effect.next_event])
        return msgs

    def _apply(self, effect: Effect) -> list[str]:
        msgs = apply_effect(effect, self.state, self.content, self.world)
        if effect.next_event:
            msgs += self._present(self.content.events[effect.next_event])
        return msgs

    # ── 閉關、練功、療傷、設定 ────────────────────────────

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
        msgs = [f"你閉關靜修，預計 {hours} 小時後出關；閉關期間氣血回復加倍。"]
        self._write("閉關", msgs, tag=f"{hours} 小時")
        return self._log(msgs)

    def _finish_seclusion(self, end_time: float) -> list[str]:
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

    def create_skill(self, name: str, kind: str) -> list[str]:
        """自創功法：取名決定屬性/威力/成長性，全服不能重名（設計文件六.2）。"""
        xinde = self._xinde()
        art, msg = team.create_skill(self.state, self.content, self.world, name, kind)
        msgs = self._log([msg])
        if art is not None:
            self._menxia_entry(msg, xinde)
            msgs += note_action(self.state, self.content, self.world, "practice")
        return msgs

    def practice(self, kind: str) -> list[str]:
        """鍛鍊：目前已學會的內功或武學加深一成，累積受傷風險。"""
        xinde = self._xinde()
        msgs = self._log(team.practice(self.state, self.content, self.world, kind, self.rng))
        self._menxia_entry(msgs[0] if msgs else "練功", xinde)
        msgs += note_action(self.state, self.content, self.world, "practice")
        return msgs

    def heal(self) -> list[str]:
        xinde = self._xinde()
        msgs = self._log(team.heal(self.state, self.content, self.state.player.member))
        self._menxia_entry(msgs[0] if msgs else "療傷", xinde)
        return msgs

    def _xinde(self) -> int:
        return self.state.player.stats.get("xinde", 0)

    def _menxia_entry(self, tag: str, xinde_before: int) -> None:
        delta = self._xinde() - xinde_before
        changes = [f"心得 {delta:+d}"] if delta else []
        entry = JournalEntry(time=self.state.world.time, title=journal.MENXIA, tag=tag, changes=changes)
        journal.add_entry(self.state, entry, merge=True)

    # ── 門下與隊伍 ────────────────────────────────────────

    def team_members(self) -> list[tuple[str, str]]:
        return [(team.member_name(self.state, self.content, key), key) for key in team.team_keys(self.state)]

    def roster_lines(self) -> list[tuple[str, str]]:
        return roster.roster_lines(self.state, self.content, self.world)

    def owned_companions(self) -> list[str]:
        return roster.owned_companions(self.world, self.state.player.name)

    def add_to_team(self, companion_id: str) -> list[str]:
        return self._log(team.add_to_team(self.state, companion_id))

    def remove_from_team(self, companion_id: str) -> list[str]:
        return self._log(team.remove_from_team(self.state, companion_id))

    # ── 門下頁面：武學說明 ──────────────────────────────────

    def skill_library(self) -> list[tuple[str, str]]:
        return skillview.library(self.state, self.content, self.world)

    def skill_detail(self, kind: str) -> str:
        return skillview.detail(self.state, self.content, self.world, kind)

    def member_card(self, key: str) -> str:
        return skillview.member_card(self.state, self.content, self.world, key)

    def menxia_rules(self) -> str:
        return skillview.rules_line(self.content)

    # ── 戰鬥紀錄 ──────────────────────────────────────────

    def battle_card(self) -> str | None:
        record = battlelog.find(self.state, self.state.battle_card)
        return battlelog.card_text(record) if record else None

    def battle_card_id(self) -> int | None:
        record = battlelog.find(self.state, self.state.battle_card)
        return record.id if record else None

    def latest_battle_id(self) -> int | None:
        return self.state.battles[0].id if self.state.battles else None

    def battle_list(self) -> list[tuple[str, int]]:
        return [(battlelog.list_label(r), r.id) for r in self.state.battles]

    def battle_detail(self, record_id: int | None = None) -> str:
        s = self.state
        record = battlelog.find(s, record_id) or (s.battles[0] if s.battles else None)
        return battlelog.detail_text(record) if record else battlelog.NO_RECORD

    def notice(self, text: str, title: str = "提醒") -> list[str]:
        self._write(title, [text])
        return self._log([text])

    def set_anonymous(self, value: bool) -> None:
        self.state.player.anonymous = bool(value)

    def skip_tutorial(self) -> list[str]:
        steps = len(self.content.tutorial.steps)
        if self.state.player.tutorial_step >= steps:
            return []
        self.state.player.tutorial_step = steps
        self._write("新手引導", [], tag="已略過")
        return self._log(["（已略過新手引導。）"])

    def view_map(self) -> list[str]:
        self.state.player.flags.add("看過地圖")
        msgs = note_action(self.state, self.content, self.world, "view_map")
        if msgs:
            self._write("翻看地圖", msgs)
        return self._log(msgs)

    def quest_text(self) -> str:
        return quest_text(self.state, self.content)

    # ── 大地圖 ────────────────────────────────────────────

    def world_map_svg(self, layer: str = "situation", selected: str | None = None) -> str:
        odds = self.odds if layer == "enemies" else None
        return render_map(self.state, self.content, layer, selected, odds)

    def minimap_svg(self) -> str:
        return render_minimap(self.state, self.content)

    def map_header(self) -> str:
        return atlas.header_text(self.state, self.content)

    def map_places(self) -> list[tuple[str, str]]:
        return atlas.place_choices(self.state, self.content)

    def place_detail(self, loc_id: str) -> str:
        return atlas.detail_text(self.state, self.content, loc_id, self.odds)

    def travel_button(self, loc_id: str) -> tuple[str, bool] | None:
        return atlas.travel_button(self.state, self.content, loc_id)

    def new_season(self) -> list[str]:
        """玩家自己的狀態重新開始（現實時間同步點、新手引導進度跨季保留）；同伴的等級/
        武學/招募狀態是共用世界狀態，不歸這個方法管，不會因為某個玩家開新季就重置。"""
        old = self.state
        self.state = Game.new(self.content, old.player.name, self.rng, self.world).state
        self.state.last_real = old.last_real
        self.state.player.tutorial_step = old.player.tutorial_step
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
        now, cap = team.member_neili(c, p.member)
        lines.append(f"- {p.name}（隊長）　第{p.member.level}級　氣血 {int(now)}/{int(cap)}")
        for cid in p.team:
            progress = self.world.get_companion(cid)
            now, cap = team.member_neili(c, progress)
            lines.append(f"- {c.characters[cid].name}　第{progress.level}級　氣血 {int(now)}/{int(cap)}")
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
        entries = self.state.journal
        return journal.card_html(entries[0]) if entries else ""

    def journal_html(self, start: int = 1, limit: int = 5, heading: str = "", empty: str = "") -> str:
        return journal.rows_html(self.state.journal[start:start + limit], heading, empty)

    def shows_battle_card(self) -> bool:
        s = self.state
        return self.battle_card_id() is not None and bool(s.journal) and s.journal[0].battle_id == s.battle_card

    def battle_extra_html(self) -> str:
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
