"""遊戲門面：介面層唯一需要呼叫的類別。負責行動、選項、時間流逝與畫面文字。"""
from __future__ import annotations

import random

from pydantic import BaseModel

from .combat import (
    TACTICS, auto_battle, battle_round, battle_status, enemy_fighter, player_fighter, start_battle,
)
from .events import choice_label, has_events_here, pick_event, visible_choices
from .guide import note_action, quest_text, tutorial_intro
from .mapview import render_map
from .models import Content, Effect, Event
from .rules import add_skill_exp, apply_effect, change_trend, learn_skill, roll_check
from .state import EQUIP_SLOTS, GameState, Rumor, new_game_state
from .world import check_thresholds, end_season, sim_tick

HOUR = 3600
DAY = 86400


class Option(BaseModel):
    id: str
    label: str
    enabled: bool = True


class Game:
    def __init__(self, content: Content, state: GameState, rng: random.Random | None = None):
        self.content = content
        self.state = state
        self.rng = rng or random.Random()
        self._drop_stale_references()

    @classmethod
    def new(cls, content: Content, name: str, rng: random.Random | None = None) -> Game:
        game = cls(content, new_game_state(content, name), rng)
        for skill_id in content.config.starter_skills:
            learn_skill(game.state, content, skill_id)
        game.state.player.visited.add(game.state.player.location)
        game._log(
            [f"══ {content.scenario.name} ══", content.scenario.intro, game.location_text()]
            + tutorial_intro(content)
        )
        return game

    def _drop_stale_references(self) -> None:
        """內容檔改版後，舊存檔可能引用已刪除的事件、地點或武學；丟掉這些引用以免當機。"""
        s, c = self.state, self.content
        p = s.player
        if s.pending_event and s.pending_event not in c.events:
            s.pending_event = None
        if s.battle and (s.battle.enemy_id not in c.enemies or s.battle.event_id not in c.events):
            s.battle = None
        if s.battle and s.battle.choice_index >= len(c.events[s.battle.event_id].choices):
            s.battle = None
        if p.location not in c.locations:
            p.location = c.scenario.start_location
        p.skills = {k: v for k, v in p.skills.items() if k in c.skills}
        p.equipped = [sid if sid in p.skills else None for sid in p.equipped]
        if p.seclusion_skill and p.seclusion_skill not in p.skills:
            p.busy_until = None
            p.seclusion_skill = None
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
        for flag in s.world.flags:
            if flag not in s.world.flag_times:
                s.world.flag_times[flag] = s.world.time

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
        return self._log(msgs)

    def _advance_step(self, seconds: float) -> list[str]:
        cfg, p, w = self.content.config, self.state.player, self.state.world
        w.time += seconds
        p.stamina = min(cfg.stamina_max, p.stamina + seconds / cfg.stamina_regen_seconds)
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

    def options(self) -> list[Option]:
        s, c = self.state, self.content
        if s.world.ended:
            return [Option(id="season:new", label="開啟新的賽季")]
        if s.battle:
            return [
                Option(id=f"tactic:{t}", label=t, enabled=not (t == "絕招" and s.battle.ultimate_used))
                for t in TACTICS
            ]
        if s.pending_event:
            event = c.events[s.pending_event]
            return [Option(id=f"choice:{i}", label=choice_label(ch, s)) for i, ch in visible_choices(event, s)]
        if s.player.busy_until is not None:
            return [Option(id="act:break", label="提前出關")]
        loc = c.locations[s.player.location]
        cost = c.config.action_cost
        opts = []
        if loc.enemies:
            opts.append(self._cost_option("act:train", "歷練", cost["train"]))
        opts.append(self._cost_option("act:explore", "探索", cost["explore"]))
        if has_events_here(c, loc, "socialize"):
            opts.append(self._cost_option("act:socialize", "交遊", cost["socialize"]))
        for dest_id in loc.connections:
            dest = c.locations[dest_id]
            if dest.unlock_flag and dest.unlock_flag not in s.world.flags:
                continue
            opts.append(self._cost_option(f"move:{dest_id}", f"前往 {dest.name}", dest.move_cost))
        return opts

    def _cost_option(self, option_id: str, label: str, cost: int) -> Option:
        return Option(
            id=option_id, label=f"{label}（體力 {cost}）", enabled=self.state.player.stamina >= cost
        )

    def choose(self, option_id: str) -> list[str]:
        option = {o.id: o for o in self.options()}.get(option_id)
        if option is None or not option.enabled:
            return self._log(["（此刻無法這麼做。）"])
        kind, _, arg = option_id.partition(":")
        if kind == "act":
            msgs = self._act(arg)
        elif kind == "move":
            msgs = self._move(arg)
        elif kind == "choice":
            msgs = self._choose(int(arg))
        elif kind == "tactic":
            msgs = self._tactic(arg)
        else:
            msgs = self.new_season()
        if kind == "act" and arg != "break":
            msgs += note_action(self.state, self.content, arg)
        elif kind == "move":
            msgs += note_action(self.state, self.content, "move")
        msgs += check_thresholds(self.state, self.content)
        return self._log(msgs)

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
        return [head, event.text]

    def _train(self) -> list[str]:
        s, c = self.state, self.content
        p = s.player
        loc = c.locations[p.location]
        enemy = c.enemies[self.rng.choice(loc.enemies)]
        won, rounds = auto_battle(player_fighter(s, c), enemy_fighter(enemy), self.rng)
        if won:
            msgs = [f"你在{loc.name}與{enemy.name}交手 {rounds} 回合，將其擊退。"]
            if enemy.reward_silver:
                p.stats["silver"] += enemy.reward_silver
                msgs.append(f"銀兩 +{enemy.reward_silver}")
            if self.rng.random() < c.config.train_stat_chance:
                key = self.rng.choice(["str", "agi", "con"])
                p.stats[key] += 1
                msgs.append(f"{c.config.stat_names[key]} +1")
            for skill_id in p.equipped:
                if skill_id and c.skills[skill_id].slot == "外功":
                    msgs += add_skill_exp(s, c, skill_id, c.config.train_skill_exp)
            for trend_id, delta in loc.train_trend.items():
                msgs += change_trend(s, c, trend_id, delta)
        else:
            loss = p.stats["silver"] // 10
            p.stats["silver"] -= loss
            msgs = [f"你在{loc.name}與{enemy.name}交手 {rounds} 回合，不敵敗走，失落銀兩 {loss}。"]
        if self.rng.random() < c.config.train_event_chance:
            event = pick_event(s, c, "train", self.rng)
            if event:
                msgs += self._present(event)
        return msgs

    def _move(self, dest_id: str) -> list[str]:
        dest = self.content.locations[dest_id]
        self.state.player.stamina -= dest.move_cost
        self.state.player.location = dest_id
        self.state.player.visited.add(dest_id)
        return [self.location_text()]

    def _choose(self, index: int) -> list[str]:
        s, c = self.state, self.content
        event = c.events[s.pending_event]
        choice = event.choices[index]
        s.pending_event = None
        msgs = [f"▸ {choice.text}"]
        if choice.combat:
            return msgs + start_battle(s, c, choice.combat, event.id, index)
        if choice.check:
            success = roll_check(choice.check, s, self.rng)
            msgs.append("（檢定成功）" if success else "（檢定失敗）")
            return msgs + self._apply(choice.effect if success else choice.fail_effect)
        return msgs + self._apply(choice.effect)

    def _tactic(self, tactic: str) -> list[str]:
        s, c = self.state, self.content
        event_id, index = s.battle.event_id, s.battle.choice_index
        outcome, msgs = battle_round(s, c, tactic, self.rng)
        if outcome is None or outcome in ("flee", "draw"):
            return msgs
        choice = c.events[event_id].choices[index]
        return msgs + self._apply(choice.effect if outcome == "win" else choice.fail_effect)

    def _apply(self, effect: Effect) -> list[str]:
        msgs = apply_effect(effect, self.state, self.content)
        if effect.next_event:
            msgs += self._present(self.content.events[effect.next_event])
        return msgs

    # ── 閉關、武學、設定 ─────────────────────────────────

    def _idle(self) -> bool:
        s = self.state
        return (
            not s.world.ended and s.battle is None and s.pending_event is None
            and s.player.busy_until is None
        )

    def seclude(self, hours: int, skill_id: str) -> list[str]:
        p = self.state.player
        if not self._idle():
            return self._log(["你現在無法閉關。"])
        if skill_id not in p.skills:
            return self._log(["你尚未習得這門武學。"])
        hours = max(1, min(12, int(hours)))
        p.busy_until = self.state.world.time + hours * HOUR
        p.seclusion_start = self.state.world.time
        p.seclusion_skill = skill_id
        return self._log([f"你閉關苦修【{self.content.skills[skill_id].name}】，預計 {hours} 小時後出關。"])

    def _finish_seclusion(self, end_time: float) -> list[str]:
        p, cfg = self.state.player, self.content.config
        hours = (end_time - p.seclusion_start) / HOUR
        amount = round(hours * cfg.seclusion_exp_per_hour * (1 + p.stats["wis"] / 20))
        skill_id = p.seclusion_skill
        p.busy_until = None
        p.seclusion_skill = None
        msgs = [f"你結束閉關（{hours:.1f} 小時），【{self.content.skills[skill_id].name}】修為 +{amount}。"]
        return msgs + add_skill_exp(self.state, self.content, skill_id, amount)

    def equip(self, slot: int, skill_id: str | None) -> list[str]:
        p, c = self.state.player, self.content
        if self.state.battle is not None:
            return self._log(["戰鬥中無法更換武學。"])
        if skill_id:
            if skill_id not in p.skills:
                return self._log(["你尚未習得這門武學。"])
            if c.skills[skill_id].slot != EQUIP_SLOTS[slot]:
                return self._log([f"【{c.skills[skill_id].name}】不能放在{EQUIP_SLOTS[slot]}欄位。"])
            for i, other in enumerate(p.equipped):
                if other == skill_id and i != slot:
                    p.equipped[i] = None
        p.equipped[slot] = skill_id or None
        label = c.skills[skill_id].name if skill_id else "（空）"
        return self._log([f"{EQUIP_SLOTS[slot]}欄位：{label}"])

    def set_anonymous(self, value: bool) -> None:
        self.state.player.anonymous = bool(value)

    def skip_tutorial(self) -> list[str]:
        """設定裡的「略過新手引導」：直接跳到引導結束。"""
        self.state.player.tutorial_step = len(self.content.tutorial.steps)
        return self._log(["（已略過新手引導。）"])

    def view_map(self) -> list[str]:
        """介面打開地圖時呼叫。不論新手引導是否還在「看地圖」那一步，都先記下玩家看過地圖。"""
        self.state.player.flags.add("看過地圖")
        return self._log(note_action(self.state, self.content, "view_map"))

    def quest_text(self) -> str:
        return quest_text(self.state, self.content)

    def map_svg(self) -> str:
        return render_map(self.state, self.content)

    def new_season(self) -> list[str]:
        last_real = self.state.last_real
        tutorial_step = self.state.player.tutorial_step
        self.state = Game.new(self.content, self.state.player.name, self.rng).state
        self.state.last_real = last_real
        self.state.player.tutorial_step = tutorial_step
        return []

    def skill_choices(self, slot_type: str) -> list[tuple[str, str]]:
        return [
            (f"{self.content.skills[sid].name} 第{prog.level}成", sid)
            for sid, prog in self.state.player.skills.items()
            if self.content.skills[sid].slot == slot_type
        ]

    # ── 畫面文字 ──────────────────────────────────────────

    def location_text(self) -> str:
        loc = self.content.locations[self.state.player.location]
        return f"【{loc.name}】危險 {'★' * loc.danger}\n\n{loc.description}"

    def scene_text(self) -> str:
        s, c = self.state, self.content
        if s.world.ended:
            return f"## {s.world.ending_title}\n\n{s.world.ending_text}"
        if s.battle:
            return f"⚔ {battle_status(s, c)}"
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
            "　".join(f"{names[k]} {p.stats[k]}" for k in ("silver", "good", "evil", "fame")),
            "**武學**",
        ]
        for slot, skill_id in zip(EQUIP_SLOTS, p.equipped):
            if skill_id:
                skill = c.skills[skill_id]
                lines.append(f"- {slot}：{skill.name}（{skill.style}）第{p.skills[skill_id].level}成")
            else:
                lines.append(f"- {slot}：（空）")
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

    def _log(self, msgs: list[str]) -> list[str]:
        log = self.state.log
        log.extend(msgs)
        overflow = len(log) - self.content.config.max_log
        if overflow > 0:
            del log[:overflow]
        return msgs


def _timeline(entries: list[Rumor]) -> str:
    return "\n\n".join(f"第{int(e.time // DAY) + 1}天　{e.text}" for e in entries)
