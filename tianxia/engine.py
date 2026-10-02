"""遊戲門面：介面層唯一需要呼叫的類別。負責行動、選項、時間流逝與畫面文字。

sanguo-companions 合併大幅重寫：拿掉 battle.py 的 3v3 全自動戰鬥、多隊派遣、招賢抽卡、
收徒系統，改成單次判定遭遇（encounter.py）、單一隊伍（最多 4 位同伴）、唯一同伴的
招募（roster.py）、練功兩種模式（team.py：自創功法／鍛鍊）。
"""
from __future__ import annotations

import random
import time

from pydantic import BaseModel

from . import atlas, battle_instance, battlelog, companion_agent, encounter, flavor, journal, roster, skillview, team
from .events import choice_label, has_events_here, pick_event, visible_choices
from .guide import note_action, quest_text, tutorial_intro
from .journal import LOG_BREAK, Draft
from .mapview import render_map, render_minimap
from .models import BattleDef, Choice, Content, Effect, Event, Location, Squad
from .ollama_client import OllamaClient
from .rules import apply_effect, change_trend, check_who, roll_check
from .state import GameState, JournalEntry, Rumor, new_game_state
from .world import advance_world_state, check_thresholds, end_season, sim_tick, start_pending_battle
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
        self.client = OllamaClient(
            base_url=content.config.ollama_url, model=content.config.ollama_model, timeout=content.config.ollama_timeout,
        )  # companion_agent.py 用；連不上時每次呼叫各自優雅退回保底反應，這裡不用先健檢
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

    def _reconcile_season(self) -> None:
        """把 self.state.world 對齊到目前的共用賽季（設計文件「真正共享賽季」討論，取代
        原本每個玩家各自獨立的 WorldState）。全服第一次開局（還沒有任何共用賽季）在這裡
        種出第一季，預設停在籌備中等管理者開季；共用賽季已經換過一輪（不管是自己剛開下一季，
        還是連線期間別的玩家觸發的）時，幫這個玩家的角色也開新的一季——角色本身（等級/位置/隊伍）
        重新開始，但跟同伴的好感度/關係現況/對話歷史是「我跟他的交情」，不是賽季道具，
        保留下來。__init__ 時（讀存檔／新角色）要呼叫，之後每次 sync() 也要呼叫，這樣連線
        途中別人把賽季推到下一輪時，我才不會一直停在上一季的畫面。"""
        shared = self.world.get_season()
        if not shared.storyline:  # 全服第一次開局：種出第一季（要不要直接開季看內容設定）
            shared = self.world.seed_first_season(self.content)
        shared_number = self.world.get_season_number()
        if self.state.player.season_number < shared_number:
            self._reset_player_for_new_season(shared_number)
        self.state.world = shared

    def _reset_player_for_new_season(self, season_number: int) -> None:
        """新一季：玩家整個 GameState 重新開始（角色、江湖紀錄、戰報都是上一季的事了），
        只保留現實時間同步點（last_real，不然下次 sync 會把一整季沒上線的時間都當成
        流逝掉）跟幾項明確認定「跟賽季無關、是我自己的」的東西——新手引導進度、跟同伴的
        好感度/關係現況/對話歷史（見設計討論：好感度跨季保留，只重組隊伍）。world 欄位
        這裡不用管，呼叫端（_reconcile_season）緊接著就會把它指向共用賽季。"""
        old = self.state
        fresh = new_game_state(self.content, old.player.name)
        fresh.last_real = old.last_real
        fresh.player.tutorial_step = old.player.tutorial_step
        fresh.player.affinities = old.player.affinities
        fresh.player.relationship_notes = old.player.relationship_notes
        fresh.player.dialogue_history = old.player.dialogue_history
        fresh.player.used_dialogue_options = old.player.used_dialogue_options
        fresh.player.turns_since_consolidation = old.player.turns_since_consolidation
        fresh.player.bot = old.player.bot  # 伺服器假人的身分與作息跨季保留
        fresh.player.season_number = season_number
        self.state = fresh
        self.state.player.visited.add(self.state.player.location)
        self._write(
            self.content.scenario.name, [self.content.scenario.intro] + tutorial_intro(self.content), tag="賽季開始",
        )

    def _drop_stale_references(self) -> None:
        """內容檔改版後，舊存檔可能引用已刪除的事件、地點、武學或人物；丟掉這些引用以免當機。"""
        self._reconcile_season()
        s, c = self.state, self.content
        p = s.player
        if s.pending_event and s.pending_event not in c.events:
            s.pending_event = None
        if p.pending_companion and p.pending_companion not in c.characters:
            p.pending_companion = None
        if p.pending_faction and p.pending_faction not in {f.id for f in c.scenario.factions}:
            p.pending_faction = None
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
        """把現實經過的時間推進到遊戲裡。玩家自己的體力/氣血照自己上次連線以來的步調追趕；
        共用賽季的時間/大勢則照「距離上次有人追趕過了多久現實時間」追趕——不管是誰觸發、
        隔多久觸發一次，一份共用時鐘永遠只走一次，不會因為好幾個玩家同時在線就重複推進
        （見 world_state.py::catch_up_season）。也會順便偵測共用賽季是不是已經被別人推到
        下一輪了（見 _reconcile_season）。"""
        self._reconcile_season()
        msgs = list(self.world.catch_up_season(self.content, now, self.rng))
        self.state.world = self.world.get_season()  # 剛才的追趕可能進一步推進了賽季，拉回最新的一份
        self._record_faction()
        if self.state.last_real is None:
            self.state.last_real = now
        else:
            elapsed = max(0.0, now - self.state.last_real) * self.content.config.time_scale
            self.state.last_real = now
            msgs += self._advance_player_local(elapsed)
        news = journal.news_entry(self.state.world.time, msgs)
        if news is not None:
            journal.add_entry(self.state, news, merge=True)
        return self._log(msgs)

    def advance(self, seconds: float) -> list[str]:
        """玩家主動「等待」固定一段遊戲時間（快轉按鈕）：進行中時，直接在 self.state.world
        （剛同步過的共用賽季副本）上往前推進 seconds，再存回共用儲存——跟 choose()/travel()
        同一套「本地修改、行動結束後存回」模式，不是用現實時間反推（那是 sync() 的事）。
        籌備中、休季時共用賽季不動，只推進玩家自己的部分。推進途中跨過開戰門檻的戰鬥，
        存回之後才開（見 world.start_pending_battle），再拉回最新的共用賽季。"""
        msgs: list[str] = []
        if self.world.season_phase() == "running":
            msgs += advance_world_state(self.state.world, self.content, seconds, self.rng, self.world)
        msgs += self._advance_player_local(seconds)
        self._save_season()
        msgs += start_pending_battle(self.world, self.content)
        self.state.world = self.world.get_season()
        news = journal.news_entry(self.state.world.time, msgs)
        if news is not None:
            journal.add_entry(self.state, news, merge=True)
        return self._log(msgs)

    def _advance_player_local(self, seconds: float) -> list[str]:
        """玩家自己的部分：體力/氣血回復、閉關出關、新立門戶福緣——這些是「我」的進度，
        不是共用賽季的一部分，照自己經過的時間算，不受共用賽季時鐘怎麼走影響。"""
        cfg, p, w = self.content.config, self.state.player, self.state.world
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
        return msgs

    # ── 選項 ──────────────────────────────────────────────

    def options(self, odds: bool = True) -> list[Option]:
        s, c = self.state, self.content
        battle_status = self._battle_status()
        if battle_status is not None and not self._watching_battle(*battle_status):
            return self._battle_options(*battle_status)
        if self.world.season_phase() == "preparing":
            return [Option(id="season:preparing", label="賽季籌備中，等待管理者開季", enabled=False)]
        if s.world.ended:
            return [Option(id="season:resting", label="休季中，等待管理者開啟下一季", enabled=False)]
        if s.pending_event:
            event = c.events[s.pending_event]
            return [Option(id=f"choice:{i}", label=self._choice_label(ch, odds)) for i, ch in visible_choices(event, s)]
        if s.player.pending_companion:
            dialogue_options, _ = s.player.last_offered_dialogue.get(s.player.pending_companion, [[], []])
            talk_cost = c.config.talk_stamina
            opts = [self._cost_option(f"talk:{i}", text, talk_cost) for i, text in enumerate(dialogue_options)]
            opts.append(Option(id="talk:leave", label="告辭"))
            return opts
        if s.player.pending_faction:
            faction = self._faction(s.player.pending_faction)
            return [
                Option(id="faction:confirm", label=f"確定投靠{faction.name}"),
                Option(id="faction:cancel", label="再想想"),
            ]
        if s.player.busy_until is not None:
            return [Option(id="act:break", label="提前出關")]
        loc = c.locations[s.player.location]
        cost = c.config.action_cost
        opts = [self._cost_option("act:explore", "探索", cost["explore"])]
        if has_events_here(c, loc, "socialize") or self._deep_interaction_target() is not None:
            opts.append(self._cost_option("act:socialize", "交遊", cost["socialize"]))
        target = self._recruit_target()
        if target is not None:
            cfg = c.config
            chance = roster.recruit_chance(c, s, target)
            opts.append(self._cost_option(
                "act:recruit", f"招募【{c.characters[target].name}】", cfg.recruit_stamina,
                note=f"成功率約 {chance * 100:.0f}%",
            ))
        for dest_id in loc.connections:
            dest = c.locations[dest_id]
            if dest.unlock_flag and dest.unlock_flag not in s.world.flags:
                continue
            opts.append(self._cost_option(f"move:{dest_id}", f"前往 {dest.name}", dest.move_cost))
        if s.player.faction is None:
            for faction in c.scenario.factions:
                if s.player.location in faction.join_at:
                    opts.append(Option(id=f"faction:{faction.id}", label=f"投靠{faction.name}"))
        opts.append(Option(id="act:rest", label="打坐歇息（恢復體力，約一個時辰）"))
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

    def _save_season(self) -> None:
        """choose()/travel() 直接在 self.state.world 上就地修改（check_thresholds、
        apply_effect 的 trend 變動等既有程式碼都是這樣寫的，沒有、也不需要特別改寫成
        認得共用儲存的樣子），行動結束後這裡統一寫回共用賽季一次。"""
        self.world.save_season(self.state.world)

    def choose(self, option_id: str) -> list[str]:
        option = {o.id: o for o in self.options(odds=False)}.get(option_id)
        if option is None or not option.enabled:
            return self._log(["（此刻無法這麼做。）"])
        self.state.battle_card = None
        kind, _, arg = option_id.partition(":")
        if kind == "battle":
            return self._log(self._battle_choose(arg))
        self._draft = Draft(self._action_title(kind, arg))
        try:
            if kind == "act":
                msgs = self._act(arg)
            elif kind == "move":
                msgs = self._move(arg)
            elif kind == "talk":
                msgs = self._talk(arg)
            elif kind == "faction":
                msgs = self._faction_step(arg)
            else:
                msgs = self._choose(int(arg))
            if kind == "act" and arg != "break":
                msgs += note_action(self.state, self.content, self.world, arg)
            elif kind == "move":
                msgs += note_action(self.state, self.content, self.world, "move")
            msgs += check_thresholds(self.state, self.content, self.world, self.client)
            journal.add_entry(self.state, self._draft.entry(self.state.world.time, msgs))
        finally:
            self._draft = None
        self._record_faction()
        self._save_season()
        return self._log(msgs)

    def _action_title(self, kind: str, arg: str) -> str:
        s, c = self.state, self.content
        if kind == "faction":
            if arg == "confirm":
                return f"投靠{self._faction(s.player.pending_faction).name}"
            if arg == "cancel":
                return "再想想"
            return f"考慮投靠{self._faction(arg).name}"
        if kind == "move":
            return f"前往 {c.locations[arg].name}"
        if kind == "choice":
            event = c.events[s.pending_event]
            return f"{event.title}・{event.choices[int(arg)].text}"
        if kind == "talk":
            character = c.characters[s.player.pending_companion]
            return f"交談・{character.name}"
        here = c.locations[s.player.location].name
        titles = {
            "explore": f"探索{here}", "socialize": f"交遊・{here}",
            "recruit": f"招募・{here}", "rest": f"打坐歇息・{here}",
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
        if what == "rest":
            return self._rest()
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
        companion_id = self._deep_interaction_target()
        if companion_id is not None:
            return companion_agent.start_dialogue(self.client, self.state, self.content, self.world, companion_id, self.rng)
        return self._encounter("socialize", "此地無人可訪，你只好悻悻離去。")

    def _rest(self) -> list[str]:
        """原地打坐歇息一個時辰：只推進玩家自己的進度（體力/氣血），不碰共用賽季時鐘
        （跟 advance() 不同，advance() 連共用賽季一起快轉，玩家自己缺體力時不該連帶
        把全服的大勢/倒數也推走）。保證選單上永遠有一個不受體力門檻限制的行動，玩家
        不會因為體力見底就被晾在原地，每個按鈕都是 disabled（實機 playtest 發現的
        卡死情境：體力歸零後原本沒有任何選項能點，只能乾等現實時間過去或翻到「門下」
        頁的閉關分頁，新玩家完全不會知道要這樣做）。"""
        before = self.state.player.stamina
        msgs = self._advance_player_local(HOUR)
        gained = self.state.player.stamina - before
        return [f"你就地打坐歇息了一個時辰，體力恢復了 {gained:.0f} 點。"] + msgs

    def _deep_interaction_target(self) -> str | None:
        """這個地點目前能深度對話的人物 id：可招募的 7 位在 recruit_at，鎖定的 8 位龍頭
        人物在 talk_at（不可招募，見「還要改進」第 5 點）；沒有就是 None。"""
        s, c = self.state, self.content
        for cid, ch in c.characters.items():
            if ch.deep_interaction and s.player.location in (ch.recruit_at, ch.talk_at):
                return cid
        return None

    def socialize_starts_dialogue(self) -> bool:
        """在這裡交遊會直接跟大勢人物對話（伺服器假人不閒聊大勢人物，見 bot_policy）。"""
        return self._deep_interaction_target() is not None

    def _talk(self, arg: str) -> list[str]:
        companion_id = self.state.player.pending_companion
        if companion_id is None:
            return ["（此刻無法這麼做。）"]
        if arg == "leave":
            return companion_agent.leave_dialogue(self.state)
        self.state.player.stamina -= self.content.config.talk_stamina  # 每一輪對話都要花體力（伺服器假人設計第八節第 4 項）
        return companion_agent.continue_dialogue(
            self.client, self.state, self.content, self.world, companion_id, int(arg), self.rng
        )

    def _faction(self, faction_id: str):
        return next(f for f in self.content.scenario.factions if f.id == faction_id)

    def _faction_step(self, arg: str) -> list[str]:
        """投靠分兩步（伺服器假人設計第八節第 3 項）：按「投靠某陣營」先出確認畫面（寫明這一季
        不能改投、三方目前各有幾人），「確定」才真的投靠，「再想想」就作罷。"""
        p = self.state.player
        if arg == "cancel":
            p.pending_faction = None
            return ["你決定再想想。"]
        if arg == "confirm":
            faction = self._faction(p.pending_faction)
            p.pending_faction = None
            if p.location not in faction.join_at:
                return ["（你已經不在投靠的地方了。）"]
            p.faction = faction.id
            return [f"你投靠了{faction.name}。"]
        faction = self._faction(arg)
        p.pending_faction = faction.id
        return [self._faction_prompt(faction)]

    def _faction_prompt(self, faction) -> str:
        return f"投靠後這一季不能改投（叛投另論）。{self.faction_counts_text()}。確定投靠{faction.name}？"

    def faction_counts_text(self) -> str:
        """「目前官軍 N 人、黃巾軍 M 人、地方豪強 K 人」：照全服投靠名冊（真人與假人一起算）。"""
        counts = self.world.faction_counts()
        return "目前" + "、".join(f"{f.name} {counts.get(f.id, 0)} 人" for f in self.content.scenario.factions)

    def _record_faction(self) -> None:
        """把自己的陣營記進全服投靠名冊（陣營人數看這份）；已經記過就不再寫。choose() 結束時
        與 sync() 都會呼叫，名冊出現之前就投靠了的人（或拜入門派而投靠的人）也會補記進去。"""
        p = self.state.player
        if p.faction is not None and self.world.read().faction_rolls.get(p.name) != p.faction:
            self.world.record_faction(p.name, p.faction)

    # ── 全服即時多人戰鬥（設計討論：集結選陣營→逐幕逐回合鎖步）──────────

    def _battle_power(self) -> float:
        """玩家自己目前的武學威力快照，加入戰鬥時存一份進 BattleParticipant.power，
        之後戰鬥結算的威力抵銷只讀這份快照，不會、也不能臨時去查任何人的角色資料
        （見 battle_instance.py::BattleParticipant 的欄位註解）。"""
        arts = team.team_arts(self.state, self.content, self.world)
        return encounter.member_power(self.state.player.member, arts)

    def _battle_neili_cap(self) -> float:
        _, cap = team.member_neili(self.content, self.state.player.member)
        return cap

    def _battle_status(self, tick: bool = True) -> tuple[battle_instance.BattleInstance, BattleDef] | None:
        """目前這場全服戰鬥的最新狀態。tick=True 時順便處理所有「只要時間到了就該自動
        發生」的事（集結逾時自動分配、回合逾時代選保守行動、機器人立刻選、全員選完就
        結算）——不管是誰的畫面刷新到這裡，都會把戰鬥狀態追趕到跟現實時間一致，誰先連線
        誰先看到，別人下次連線也會看到同一份結果（跟 _reconcile_season 同一套精神）。
        tick=False 只單純讀取，不會推進任何東西——options()/scene_text() 同一次畫面刷新
        都會各呼叫一次這個方法，只讓其中一個（options()）真的推進，避免同一次刷新裡
        推進兩次（純機器人對戰、沒有人類卡著等行動時，兩次推進會在一次畫面刷新裡偷跑
        兩回合，而不是一回合）。沒有進行中的戰鬥，或戰鬥已經結束，回傳 None。"""
        raw = self.world.get_battle()
        if raw is None:
            return None
        definition = self.content.battles.get(raw.battle_id)
        if definition is None:
            return None
        if not tick:
            return None if raw.phase == "ended" else (raw, definition)
        was_ended = raw.phase == "ended"
        battle, _ = self._run_battle_tick(definition)
        battle = battle or raw
        if battle.phase == "ended":
            if not was_ended:
                self._apply_battle_outcome(battle)
            return None
        return battle, definition

    def _advance_battle_round(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> list[str]:
        """核心推進邏輯（在呼叫端已經握有 mutate_battle 鎖的前提下原地修改 battle）：
        集結逾時自動分配、機器人補位、場上沒人能打又逾時就用保底結果收場、回合逾時代選
        保守行動、全員到齊就結算並請 LLM 潤色。回傳這次呼叫如果真的結算了一回合（或收場）
        的敘事訊息，沒有結算就是空清單。這是
        _run_battle_tick()（被動追趕，options()/scene_text() 用）跟 _battle_choose()
        的 act 分支（玩家自己送出行動，可能剛好湊滿全員）共用的同一份邏輯，確保兩條
        路徑的推進規則完全一致——只是呼叫的時間點跟是否先 submit_action 不同。"""
        now = time.time()
        if battle.phase == "muster" and now >= battle.muster_deadline_real:
            battle_instance.close_muster(battle, definition, self.rng, now)
        if battle.phase != "active":
            return []
        for p in list(battle.participants.values()):
            if p.is_bot and not p.eliminated and p.name not in battle.round.pending_actions:
                tag = battle_instance.bot_choose_action(battle, definition, p.name, self.rng)
                if tag:
                    battle_instance.submit_action(battle, p.name, tag)
        ended = battle_instance.end_without_fighters(battle, definition, now)  # 沒人能打、回合逾時：用保底結果收場
        if ended:
            return ended
        if now - battle.round.opened_real >= definition.round_seconds and not battle_instance.round_is_complete(battle):
            default_tag = min(definition.action_tags, key=lambda t: definition.action_tags[t].neili_damage)
            battle_instance.fill_timed_out_actions(battle, definition, default_tag)
        if not battle_instance.round_is_complete(battle):
            return []
        msgs = battle_instance.resolve_round(battle, definition, self.rng, now=now)
        narration = battle_instance.narrate_round(self.client, definition, battle, msgs)
        if narration:
            battle.narrative_log.append(narration)
        return [narration] if narration else msgs

    def _run_battle_tick(self, definition: BattleDef) -> tuple[battle_instance.BattleInstance | None, list[str]]:
        """在鎖保護下跑一次 _advance_battle_round，給被動追趕（options()/scene_text()）用。"""
        captured: dict[str, list[str]] = {"msgs": []}

        def _apply(b: battle_instance.BattleInstance) -> None:
            captured["msgs"] = self._advance_battle_round(b, definition)

        battle = self.world.mutate_battle(_apply)
        return battle, captured["msgs"]

    def _apply_battle_outcome(self, battle: battle_instance.BattleInstance) -> None:
        """戰鬥剛結束這一刻，把結果套用到共用賽季（大勢推動／世界旗標），順便留一筆
        江湖史——這裡故意不在 mutate_battle 的 callback 裡面做（兩者用同一把檔案鎖，
        不是可重入的，巢狀呼叫 mutate_season 會自我鎖死），所以是呼叫端在拿到
        mutate_battle 的結果、確定鎖已經釋放之後才呼叫，順序上一定晚於戰鬥本身的結算。"""
        if not (battle.outcome_world_flags or battle.outcome_trend_delta or battle.outcome_title):
            return

        def _apply(season) -> None:
            for trend_id, delta in battle.outcome_trend_delta.items():
                season.trends[trend_id] = max(0, min(100, season.trends.get(trend_id, 0) + delta))
            for flag in battle.outcome_world_flags:
                if flag not in season.flags:
                    season.flags.add(flag)
                    season.flag_times[flag] = season.time
            if battle.outcome_title:
                season.chronicle.append(Rumor(time=season.time, text=f"【{battle.outcome_title}】{battle.outcome_text}"))

        self.world.mutate_season(_apply)

    def _watching_battle(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> bool:
        """劇本分陣營時，這個人打不了這場仗、只能觀戰：自己的陣營（散人沒有陣營）不是交戰的
        任何一方，而且還在集結、或已經開打但他不在場上。觀戰的人照常遊玩（options() 不會
        回傳戰鬥選項），場景上仍看得到這場戰鬥——全服決戰不能把打不了仗的人鎖住。劇本不分
        陣營時誰都能加入，永遠回傳 False。"""
        if not self.content.scenario.factions:
            return False
        if self.state.player.faction in {f.id for f in definition.factions}:
            return False
        return battle.phase == "muster" or self.state.player.name not in battle.participants

    def _battle_scene_text(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> str:
        header = f"**{definition.name}**"
        watching = self._watching_battle(battle, definition)
        watch_line = "你不屬於交戰的任何一方，在一旁觀戰。"
        if battle.phase == "muster":
            remaining = max(0, int(battle.muster_deadline_real - time.time()))
            countdown = f"集結中，還剩 {remaining // 60} 分 {remaining % 60} 秒"
            return f"{header}\n\n{countdown}。{watch_line}" if watching else f"{header}\n\n{countdown}選擇陣營。"
        act = battle_instance.current_act(battle, definition)
        lines = [header, f"【{act.title}】{act.text}"] + battle.narrative_log[-5:]
        p = battle.participants.get(self.state.player.name)
        if p is not None and p.eliminated:
            lines.append("（你已經倒下，只能在一旁觀戰。）")
        if watching:
            lines.append(watch_line)
        return "\n\n".join(lines)

    def _battle_options(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> list[Option]:
        """打得了這場仗的人的戰鬥選項（只能觀戰的人不會走到這裡，見 _watching_battle）。"""
        name = self.state.player.name
        if battle.phase == "muster":
            sides = definition.factions
            if self.content.scenario.factions:  # 劇本分陣營：只能站在自己陣營那邊
                sides = [f for f in definition.factions if f.id == self.state.player.faction]
            return [Option(id=f"battle:join:{f.id}", label=f"加入【{f.name}】") for f in sides]
        p = battle.participants.get(name)
        if p is None:
            return [Option(id="battle:join_late", label="加入戰局")]
        if p.eliminated:
            return [Option(id="battle:spectate", label="（觀戰中，無法行動）", enabled=False)]
        if name in battle.round.pending_actions:
            return [Option(id="battle:waiting", label="（已選擇，等待其他人……）", enabled=False)]
        return [
            Option(id=f"battle:act:{o.tag}", label=o.text)
            for o in battle_instance.options_for(battle, definition, name) if not o.free_text
        ]

    def battle_free_text_prompt(self) -> str | None:
        """這回合是否有自訂行動的輸入框可以用，有的話回傳提示語（見 BattleOption.free_text
        ——設計討論：魯莽這類選項該是玩家自己想出來的招，不是從清單挑一個）；沒有（不在
        戰鬥中、集結期、已經出局、這回合已經選過）就回傳 None，app.py 用這個決定輸入框
        要不要顯示。"""
        status = self._battle_status(tick=False)
        if status is None:
            return None
        battle, definition = status
        name = self.state.player.name
        p = battle.participants.get(name)
        if battle.phase != "active" or p is None or p.eliminated or name in battle.round.pending_actions:
            return None
        option = next((o for o in battle_instance.options_for(battle, definition, name) if o.free_text), None)
        return option.text if option else None

    def submit_battle_custom_action(self, text: str) -> list[str]:
        """自訂行動輸入框的送出：截到 20 字，查到這回合對應的 free_text 選項，機制效果
        還是走它的 tag（跟按按鈕完全一樣的查表邏輯），玩家打的字只會被餵給 LLM 潤色。
        這裡用 tick=True（不是 tick=False）——跟 _battle_choose() 不一樣，這個方法不是
        透過 choose() 進來的，choose() 開頭那次 self.options(odds=False) 呼叫順便推進
        過一次集結逾時/回合逾時的保護在這裡沒有發生過，這個方法是自己的入口，必須自己
        負責先追趕一次，不然集結剛好逾時的那一刻送出的行動會在 submit_action() 裡被
        「battle.phase 還是 muster」悄悄吃掉（見那次遇到的真實 bug）。"""
        status = self._battle_status()
        if status is None:
            return ["（此刻無法這麼做。）"]
        battle, definition = status
        name = self.state.player.name
        p = battle.participants.get(name)
        if p is None or p.eliminated or name in battle.round.pending_actions:
            return ["（此刻無法這麼做。）"]
        option = next((o for o in battle_instance.options_for(battle, definition, name) if o.free_text), None)
        if option is None:
            return ["（此刻無法這麼做。）"]
        text = text.strip()[:20]
        if not text:
            return ["（請先輸入你想做的事。）"]
        act = battle_instance.current_act(battle, definition)
        faction_name = next((f.name for f in definition.factions if f.id == p.faction), p.faction)
        success_rate = battle_instance.assess_action_success_rate(self.client, act, faction_name, text)
        return self._submit_battle_action(name, definition, option.tag, text, success_rate)

    def _battle_choose(self, arg: str) -> list[str]:
        """choose() 分派進這裡之前，已經透過自己開頭那次 self.options(odds=False) 呼叫
        推進過一次了（options() 內部會 tick），這裡用 tick=False 只讀，避免同一次請求裡
        重複推進兩次。"""
        status = self._battle_status(tick=False)
        if status is None:
            return ["（此刻無法這麼做。）"]
        _, definition = status
        name = self.state.player.name
        kind, _, rest = arg.partition(":")
        if kind == "join":
            if self.content.scenario.factions and rest != self.state.player.faction:
                return ["（你只能站在自己陣營這一邊。）"]
            self.world.mutate_battle(
                lambda b: battle_instance.join_faction(b, name, rest, self._battle_neili_cap(), self._battle_power())
            )
            return ["你加入了這場戰局。"]
        if kind == "join_late":
            own = self.state.player.faction if self.content.scenario.factions else None
            self.world.mutate_battle(
                lambda b: battle_instance.auto_assign_latecomer(
                    b, definition, name, self._battle_neili_cap(), self.rng, self._battle_power(), faction=own,
                )
            )
            return ["你加入了戰局，這回合先觀戰，下回合開始可以行動。"]
        if kind == "act":
            return self._submit_battle_action(name, definition, rest)
        return ["（此刻無法這麼做。）"]

    def _submit_battle_action(
        self, name: str, definition: BattleDef, tag: str, text: str | None = None, success_rate: int | None = None,
    ) -> list[str]:
        """送出一個行動（按鈕選的固定 tag，或自訂輸入框的 free_text 選項，連同 LLM 先評好
        的成功率）並嘗試結算這回合；呼叫端已經確認過戰鬥還在進行（還沒結束），所以這裡
        如果結算完變成 ended，一定是這次送出的行動剛好造成的，不用再跟「結算前是不是
        已經 ended」比對。"""
        captured: dict[str, list[str]] = {"msgs": []}

        def _apply(b: battle_instance.BattleInstance) -> None:
            battle_instance.submit_action(b, name, tag, text, success_rate)
            captured["msgs"] = self._advance_battle_round(b, definition)

        battle = self.world.mutate_battle(_apply)
        if battle is not None and battle.phase == "ended":
            self._apply_battle_outcome(battle)
        return captured["msgs"] or ["你選擇了行動，等待其他人……"]

    def _recruit(self) -> list[str]:
        target = self._recruit_target()
        if target is None:
            return ["（此地此刻沒有能招募的人。）"]
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
        is_repeat = event.id in self.state.player.seen_events
        self.state.pending_event = event.id
        self.state.player.seen_events.add(event.id)
        head = f"✦ 奇遇：{event.title}" if event.qiyu else f"【{event.title}】"
        text = event.text
        if is_repeat:
            flourish = flavor.polish_event_repeat(self.client, event.title, event.text)
            if flourish:
                text = f"{event.text}\n\n{flourish}"
        self._outcome(journal.event_marker(event.title, event.qiyu), head)
        self._hide(text)
        return [head, text]

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
        is_revisit = dest_id in self.state.player.visited
        self.state.player.stamina -= dest.move_cost
        self.state.player.location = dest_id
        self.state.player.visited.add(dest_id)
        text = self.location_text()
        if is_revisit and not dest.important:
            flourish = flavor.polish_revisit(self.client, dest.name, dest.description)
            if flourish:
                text = f"{text}\n\n{flourish}"
        self._hide(text)
        return [text]

    def travel(self, dest_id: str) -> list[str]:
        if self._preparing():
            return self._log(["（賽季籌備中，等待管理者開季。）"])
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
                msgs += check_thresholds(s, c, self.world, self.client)
            self._draft.title = self._travel_title(dest_id, route)
            journal.add_entry(s, self._draft.entry(s.world.time, msgs))
        finally:
            self._draft = None
        self._save_season()
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

    def _preparing(self) -> bool:
        """賽季籌備中（管理者還沒開季）：玩家什麼都不能做。"""
        return self.world.season_phase() == "preparing"

    def _idle(self) -> bool:
        s = self.state
        return (
            not self._preparing() and not s.world.ended and s.pending_event is None and s.player.busy_until is None
        )

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
        if self._preparing():
            return self._log(["（賽季籌備中，等待管理者開季。）"])
        xinde = self._xinde()
        art, msg = team.create_skill(self.state, self.content, self.world, name, kind)
        msgs = self._log([msg])
        if art is not None:
            self._menxia_entry(msg, xinde)
            msgs += note_action(self.state, self.content, self.world, "practice")
        return msgs

    def practice(self, kind: str) -> list[str]:
        """鍛鍊：目前已學會的內功或武學加深一成，累積受傷風險。"""
        if self._preparing():
            return self._log(["（賽季籌備中，等待管理者開季。）"])
        xinde = self._xinde()
        msgs = self._log(team.practice(self.state, self.content, self.world, kind, self.rng))
        self._menxia_entry(msgs[0] if msgs else "練功", xinde)
        msgs += note_action(self.state, self.content, self.world, "practice")
        return msgs

    def heal(self) -> list[str]:
        if self._preparing():
            return self._log(["（賽季籌備中，等待管理者開季。）"])
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
        if self._preparing():
            return self._log(["（賽季籌備中，等待管理者開季。）"])
        return self._log(team.add_to_team(self.state, companion_id))

    def remove_from_team(self, companion_id: str) -> list[str]:
        if self._preparing():
            return self._log(["（賽季籌備中，等待管理者開季。）"])
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

    # ── 管理者 ────────────────────────────────────────────

    def is_admin(self) -> bool:
        """暫時用名號認管理者（content/config.json 的 admins）；線上架構會換成帳號權限。"""
        return self.state.player.name in self.content.config.admins

    def admin_open_season(self, now: float) -> list[str]:
        """管理者開季：籌備中 → 進行中。"""
        if not self.is_admin():
            return self._log(["（只有管理者能開季。）"])
        if not self.world.open_season(now):
            return self._log(["（現在不是籌備期，無法開季。）"])
        msgs = [f"══ {self.content.scenario.name}・開季 ══"]
        self._write("開季", msgs, tag="管理者")
        return self._log(msgs)

    def admin_next_season(self, now: float) -> list[str]:
        """管理者開下一季：只在休季時有效；管理者自己的角色跟著換季（其他玩家下次同步時換）。"""
        if not self.is_admin():
            return self._log(["（只有管理者能開啟下一季。）"])
        if not self.world.next_season(self.content, now):
            return self._log(["（這一季還沒結束，無法開啟下一季。）"])
        self._reconcile_season()
        return self._log([f"══ 第 {self.world.get_season_number()} 季開始 ══"])

    # ── 畫面文字 ──────────────────────────────────────────

    def location_text(self) -> str:
        loc = self.content.locations[self.state.player.location]
        return f"【{loc.name}】危險 {'★' * loc.danger}\n\n{loc.description}"

    def scene_text(self) -> str:
        """有全服戰鬥時大家都看得到戰場；只能觀戰的人照常遊玩，自己眼前的事（事件、對話、
        地點）接在戰場底下，不然遇到事件時只看得到選項、看不到事件本身。"""
        battle_status = self._battle_status(tick=False)
        if battle_status is None:
            return self._own_scene_text()
        battle_scene = self._battle_scene_text(*battle_status)
        if not self._watching_battle(*battle_status):
            return battle_scene
        return f"{battle_scene}\n\n---\n\n{self._own_scene_text()}"

    def _own_scene_text(self) -> str:
        s, c = self.state, self.content
        if s.world.ended:
            return f"## {s.world.ending_title}\n\n{s.world.ending_text}"
        if s.pending_event:
            event = c.events[s.pending_event]
            return f"**{event.title}**\n\n{event.text}"
        if s.player.pending_companion:
            character = c.characters[s.player.pending_companion]
            history = s.player.dialogue_history.get(s.player.pending_companion, [])
            last = next((m["content"] for m in reversed(history) if m.get("role") == "assistant"), "")
            return f"**{character.name}**\n\n{last}"
        if s.player.pending_faction:
            faction = self._faction(s.player.pending_faction)
            return f"**投靠{faction.name}**\n\n{self._faction_prompt(faction)}"
        return self.location_text()

    def status_text(self) -> str:
        s, c = self.state, self.content
        p, w = s.player, s.world
        names = c.config.stat_names
        sect = c.sects[p.sect].name if p.sect else None
        faction = next((f.name for f in c.scenario.factions if f.id == p.faction), None)
        affiliation = "・".join(name for name in (sect, faction) if name) or "散人"
        day = int(w.time // DAY) + 1
        clock = f"{int(w.time % DAY // HOUR):02d}:{int(w.time % HOUR // 60):02d}"
        lines = [
            f"### {p.name}　·　{affiliation}" + ("（匿名行走）" if p.anonymous else ""),
            f"📍 {c.locations[p.location].name}　⏳ 第 {day} 天 {clock}（本季共 {c.config.season_days:g} 天）",
            f"**體力** {int(p.stamina)} / {c.config.stamina_max}",
            "　".join(f"{names[k]} {p.stats[k]}" for k in ("str", "agi", "con", "wis")),
            "　".join(f"{names[k]} {p.stats.get(k, 0)}" for k in ("silver", "good", "evil", "fame", "xinde")),
        ]
        hint = skillview.practice_hint(s, c)  # 心得擱著沒用、又還有功夫沒練滿時才有這一行
        if hint is not None:
            lines.append(hint)
        lines.append("**隊伍**")
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
        text = _timeline(self.state.world.chronicle) or "（江湖史尚無記載。）"
        return f"{text}\n\n---\n\n{self.world.jade_seal_summary()}"

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
