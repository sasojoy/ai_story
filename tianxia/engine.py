"""遊戲門面：介面層唯一需要呼叫的類別。負責行動、選項、時間流逝與畫面文字。

sanguo-companions 合併大幅重寫：拿掉 battle.py 的 3v3 全自動戰鬥、多隊派遣、招賢抽卡、
收徒系統，改成單次判定遭遇（encounter.py）、單一隊伍（最多 4 位同伴）、唯一同伴的
招募（roster.py）、練功兩種模式（team.py：自創功法／鍛鍊）。
"""
from __future__ import annotations

import random

from pydantic import BaseModel

from . import (
    atlas, battle_instance, battlelog, companion_agent, craft, encounter, flavor, journal, materials, roster,
    skillview, team,
)
from .events import choice_label, has_events_here, pick_event, visible_choices
from .guide import note_action, quest_text, tutorial_intro
from .journal import LOG_BREAK, Draft
from .mapview import render_map, render_minimap
from .models import BattleDef, Choice, Content, Effect, Event, Location, Squad, TravelMode
from .ollama_client import OllamaClient
from .rules import apply_effect, change_trend, check_who, current_day, roll_check
from .sqlite_world import open_world
from .state import GameState, JournalEntry, Journey, Rumor, WorldState, new_game_state
from .world import advance_world_state, check_thresholds, end_season, fire_by_id, sim_tick, start_pending_battle
from .world_state import WorldStateStore

HOUR = 3600
DAY = 86400
AUDIENCE_HALL_FIGURES = 2  # 一個地點有幾位以上的大勢人物，交遊就不直接找人、改按「求見」指名（企劃者 2026-10-03 決定）


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
        self.world = world or open_world()
        cfg = content.config
        self.client = OllamaClient(
            base_url=cfg.ollama_url, model=cfg.ollama_model, timeout=cfg.ollama_timeout, think=cfg.ollama_think,
            keep_alive=cfg.ollama_keep_alive, repeat_penalty=cfg.ollama_repeat_penalty,
            presence_penalty=cfg.ollama_presence_penalty, frequency_penalty=cfg.ollama_frequency_penalty,
        )  # companion_agent.py 用；連不上時那輪對話取消，這裡不用先健檢
        self._draft: Draft | None = None  # choose() 進行中那次行動的江湖紀錄草稿
        # 現在的現實時間（秒）：由 sync(now) 傳進來，引擎自己不讀電腦時鐘（線上架構設計第四節）。
        # 讀進來的存檔先用上次同步的時間；開戰的集結截止、回合逾時都看它。
        self.now: float = state.last_real if state.last_real is not None else 0.0
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
        if p.picking_audience and not self._audience_hall():
            p.picking_audience = False  # 內容改版後這裡不再有兩位以上的人物：收起求見選單
        if p.journey is not None and any(loc_id not in c.locations for loc_id in p.journey.path):
            p.journey = None
        p.team = [k for k in p.team if k in c.characters][: team.MAX_TEAM_COMPANIONS]
        if p.member.neigong_id and p.member.neigong_id not in c.skills and not self.world.is_skill_name_taken(p.member.neigong_id):
            p.member.neigong_id = None
        if p.member.wugong_id and p.member.wugong_id not in c.skills and not self.world.is_skill_name_taken(p.member.wugong_id):
            p.member.wugong_id = None
        # 功法庫與素材：內容檔改版（或換季）後可能指到不存在的東西
        equipped = {p.member.neigong_id, p.member.wugong_id}
        seen: set[str] = set()
        p.arts = [  # 去重，並把已經配在身上的從庫裡移除（舊版重煉同一配方會造成這種髒狀態）
            a for a in p.arts
            if team.resolve_art(a, c, self.world) is not None and a not in equipped and not (a in seen or seen.add(a))
        ]
        p.art_levels = {k: v for k, v in p.art_levels.items() if team.resolve_art(k, c, self.world) is not None}
        p.materials = {k: v for k, v in p.materials.items() if k in c.materials and v > 0}
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
        下一輪了（見 _reconcile_season）。在路上時，抵達時間已經到了的站接著一站一站抵達（見 _arrivals）。"""
        self.now = now
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
        arrived = self._arrivals()  # 抵達的站自己寫一則江湖紀錄（途中觸發的大事也寫在那裡），不併進下面的「江湖大事」
        if arrived:
            self._save_season()  # 抵達時觸發的大勢門檻改了共用賽季
        news = journal.news_entry(self.state.world.time, msgs)
        if news is not None:
            journal.add_entry(self.state, news, merge=True)
        return self._log(msgs + arrived)

    def advance(self, seconds: float) -> list[str]:
        """玩家主動「等待」固定一段遊戲時間（快轉按鈕）：進行中時，直接在 self.state.world
        （剛同步過的共用賽季副本）上往前推進 seconds，再存回共用儲存——跟 choose()/travel()
        同一套「本地修改、行動結束後存回」模式，不是用現實時間反推（那是 sync() 的事）。
        籌備中、休季時共用賽季不動，只推進玩家自己的部分。推進途中跨過開戰門檻的戰鬥，
        存回之後才開（見 world.start_pending_battle），再拉回最新的共用賽季。在路上時，同 sync 補算
        抵達時間已經到了的站（見 _arrivals）。"""
        msgs: list[str] = []
        if self.world.season_phase() == "running":
            msgs += advance_world_state(self.state.world, self.content, seconds, self.rng, self.world)
        msgs += self._advance_player_local(seconds)
        arrived = self._arrivals()  # 同 sync：抵達自己寫紀錄
        self._save_season()
        msgs += start_pending_battle(self.world, self.content, self.now)
        self.state.world = self.world.get_season()
        news = journal.news_entry(self.state.world.time, msgs)
        if news is not None:
            journal.add_entry(self.state, news, merge=True)
        return self._log(msgs + arrived)

    def _advance_player_local(self, seconds: float) -> list[str]:
        """玩家自己的部分：體力（打坐中加倍）／氣血回復、打坐回滿起身、閉關出關、新立門戶福緣——
        這些是「我」的進度，不是共用賽季的一部分，照自己經過的時間算，不受共用賽季時鐘怎麼走影響。"""
        cfg, p, w = self.content.config, self.state.player, self.state.world
        regen = seconds / cfg.stamina_regen_seconds
        if p.resting_since is not None:
            regen *= cfg.rest_regen_multiplier  # 打坐中回復加倍
        p.stamina = min(cfg.stamina_max, p.stamina + regen)
        rate = seconds / (cfg.neili_regen_hours * HOUR)
        if p.busy_until is not None:
            rate *= 2
        if w.time <= cfg.newbie_days * DAY:
            rate *= 2
        team.regen_neili(self.content, p.member, rate)
        for cid in p.team:
            self.world.update_companion(cid, lambda progress: team.regen_neili(self.content, progress, rate))
        msgs: list[str] = []
        if p.resting_since is not None and p.stamina >= cfg.stamina_max:
            msgs += self._stand_up(full=True)
        if p.busy_until is not None and w.time >= p.busy_until:
            msgs += self._finish_seclusion(p.busy_until)
        if roster.fortune_overdue(self.state, self.content):
            msgs += self._deliver_fortune()
        return msgs

    # ── 選項 ──────────────────────────────────────────────

    def options(self, odds: bool = True, tick: bool = True) -> list[Option]:
        """tick 照 _battle_status 的規則往下傳：預設 True，這個呼叫順便把全服戰鬥追趕到現實時間；
        只想讀選單、不該推進戰鬥的呼叫端（dialogue_request）傳 False——一次請求只能推進一次。"""
        s, c = self.state, self.content
        battle_status = self._battle_status(tick=tick)
        if battle_status is not None and not self._watching_battle(*battle_status):
            battle_menu = self._battle_options(*battle_status)
            if s.player.resting_since is not None:
                battle_menu.append(self._stand_option())  # 戰鬥選單取代整份選單，隨時可以起身這條規則不能因此掉了
            return battle_menu
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
        if s.player.picking_audience:
            return self._audience_options()
        if s.player.busy_until is not None:
            return [Option(id="act:break", label="提前出關")]
        j = s.player.journey
        if j is not None:
            end = c.locations[j.path[j.last]].name
            opts = [Option(id="act:on_road", label=f"（在路上，{battlelog.clock_text(j.arrive_at[j.last])} 抵達{end}）", enabled=False)]
            if j.stop_at is None and j.reached < j.last:
                opts.append(Option(id="act:halt", label=f"喊停（到{c.locations[j.path[j.reached]].name}就停下）"))
            return opts
        if s.player.resting_since is not None:
            return [self._stand_option()]
        loc = c.locations[s.player.location]
        cost = c.config.action_cost
        opts = [self._cost_option("act:explore", "探索", cost["explore"])]
        if loc.enemies:
            # 歷練：這個地點的敵人，必定開打（見 _train）。sanguo-companions 合併時這個行動被
            # 整個拿掉，於是 Location.enemies／action_cost["train"]／train_event_chance 三個設定
            # 一起變成死的，而遭遇戰只剩劇情事件的 combat 選項——實測整季只打 3 場。
            #
            # 標籤要顯示勝算（跟劇情戰的選項同一套慣例，見 _choice_label）：實機試玩發現
            # 新角色沒有武學時威力是 0，在任何地點歷練都**必敗**，而落敗現在真的要付氣血與
            # 內傷的代價——不顯示勝算的話，玩家會在開局連輸三場、氣血見底才知道自己不該打。
            opts.append(self._cost_option("act:train", "歷練", cost["train"], note=self._train_note(loc, odds)))
        figures = self._figures_here()
        if has_events_here(c, loc, "socialize") or 0 < len(figures) < AUDIENCE_HALL_FIGURES:
            # 兩位以上大勢人物的地點，交遊只走福緣與地點事件、從不開口對話（見 _socialize_figure），
            # 所以只在有交遊事件時才給；人物改由下面的「求見」指名
            opts.append(self._cost_option("act:socialize", "交遊", cost["socialize"]))
        if len(figures) >= AUDIENCE_HALL_FIGURES:
            opts.append(Option(id="act:call", label="求見"))  # 只是打開第二層選單，不花體力（見 _audience_options）
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
            minutes = atlas.leg_minutes(c, loc.id, dest_id)
            opts.append(Option(id=f"move:{dest_id}", label=f"前往 {dest.name}（{atlas.mode_text(c, minutes, 'walk')}）"))
        if s.player.faction is None:
            for faction in c.scenario.factions:
                if s.player.location in faction.join_at:
                    opts.append(Option(id=f"faction:{faction.id}", label=f"投靠{faction.name}"))
        opts.append(Option(id="act:rest", label="打坐（坐下來回體力，隨時可以起身）"))
        return opts

    @staticmethod
    def _stand_option() -> Option:
        return Option(id="act:stand", label="起身")

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

    def _train_note(self, loc: Location, odds: bool) -> str:
        """歷練按鈕上的補充說明：對手是誰、勝算多少（勝算的計算比較貴，所以照既有慣例吃 odds 旗標）。"""
        squads = [self.content.squads[sid] for sid in loc.enemies]
        who = squads[0].name if len(squads) == 1 else f"{len(squads)} 路對手"
        if not odds:
            return who
        # 多路對手時以**最強的**那個當參考（真的開打是隨機挑）：這個標籤的用途是警告玩家，
        # 寧可低估也不要給出過度樂觀的承諾。
        hardest = max(squads, key=lambda s: s.difficulty)
        return f"{who}・{self.odds(hardest.id)}"

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

    def dialogue_request(self, option_id: str) -> companion_agent.DialogueRequest | None:
        """鎖外生成的階段 A（server.py 在行動鎖內、很快地呼叫）：現在選這個選項，會不會生成一輪對話？
        會就回傳要送給模型的單子（選項、人物、玩家這一步、messages），不會就是 None。只讀、不改狀態。
        - `talk:N`：N 是上一輪提供的選項、手上有對話、選項沒停用；`talk:leave` 不生成。
        - `act:socialize`：選項沒停用、福緣還沒到（福緣先發，見 _act）、這裡只有一位大勢人物而且見得到
          （兩位以上的地點交遊不開口，見 _socialize_figure）；玩家這一步固定是 GENERIC_OPENING。
        - `call:<人物>`：求見選單上按得下去的那位人物（選項沒停用＝見得到、今天還沒談滿、體力夠）；
          玩家這一步固定是 GENERIC_OPENING。`call:back` 不生成。
        其他選項都不呼叫對話模型。
        只讀：選單用 tick=False 取，不推進戰鬥（推進可能結算一回合並呼叫 LLM 潤色，而且備料與
        進鎖重驗各會呼叫這個方法一次；一次請求的那一次推進留給 choose() 開頭）。"""
        option = {o.id: o for o in self.options(odds=False, tick=False)}.get(option_id)
        if option is None or not option.enabled:
            return None
        kind, _, arg = option_id.partition(":")
        if kind == "talk":
            companion_id = self.state.player.pending_companion
            if companion_id is None or not arg.isdecimal():
                return None
            offered, _ = self.state.player.last_offered_dialogue.get(companion_id, [[], []])
            if int(arg) >= len(offered):
                return None
            player_action = offered[int(arg)]
        elif option_id == "act:socialize":
            if roster.fortune_due(self.state, self.content):
                return None
            companion_id = self._socialize_figure()
            if companion_id is None:
                return None
            player_action = companion_agent.GENERIC_OPENING
        elif kind == "call" and arg != "back":
            companion_id, player_action = arg, companion_agent.GENERIC_OPENING
        else:
            return None
        return companion_agent.build_request(
            self.state, self.content, self.world, companion_id, option_id, player_action,
        )

    def _checked_prepared(
        self, option_id: str, prepared: companion_agent.PreparedTurn | None,
    ) -> companion_agent.PreparedTurn | None:
        """進鎖後重驗鎖外生成的結果：選項、人物、玩家這一步都要跟「現在」重算出來的單子一致才採用；
        對不上（連點兩下、選項清單已換）就當沒給，走一般路徑在鎖內生成——很少發生，慢一點可以接受。
        對不上時連它的失敗（turn=None）一起丟掉，不能讓別張單子的失敗結束現在這段對話。"""
        if prepared is None:
            return None
        request = self.dialogue_request(option_id)
        if request is None:
            return None
        same = (prepared.option_id, prepared.companion_id, prepared.player_action) == (
            request.option_id, request.companion_id, request.player_action,
        )
        return prepared if same else None

    @staticmethod
    def _prepared_turn(prepared: companion_agent.PreparedTurn | None) -> companion_agent.CompanionTurn | None:
        """採用鎖外生成的結果：有 turn 就交給 companion_agent 套用；生成失敗（turn=None）等同鎖內的
        DialogueUnavailable；沒有 prepared 就回 None（讓 companion_agent 自己在鎖內生成）。"""
        if prepared is None:
            return None
        if prepared.turn is None:
            raise companion_agent.DialogueUnavailable("鎖外生成失敗")
        return prepared.turn

    def choose(self, option_id: str, prepared: companion_agent.PreparedTurn | None = None) -> list[str]:
        """prepared 是 server.py 在鎖外先生成好的一輪對話（見 dialogue_request／companion_agent.prepare_turn）；
        只有對話選項用得到，進來先重驗，驗不過就忽略。"""
        option = {o.id: o for o in self.options(odds=False)}.get(option_id)
        if option is None or not option.enabled:
            return self._log(["（此刻無法這麼做。）"])
        self.state.battle_card = None
        kind, _, arg = option_id.partition(":")
        if kind == "battle":
            return self._log(self._battle_choose(arg))
        prepared = self._checked_prepared(option_id, prepared) if kind in ("act", "talk", "call") else None
        self._draft = Draft(self._action_title(kind, arg))
        try:
            if kind == "act":
                msgs = self._act(arg, prepared)
            elif kind == "move":
                msgs = self._move(arg)
            elif kind == "talk":
                msgs = self._talk(arg, prepared)
            elif kind == "faction":
                msgs = self._faction_step(arg)
            elif kind == "call":
                msgs = self._call(arg, prepared)
            else:
                msgs = self._choose(int(arg))
            if kind == "act" and arg != "break":
                msgs += note_action(self.state, self.content, self.world, arg)
            if kind == "call" and arg != "back":
                msgs += note_action(self.state, self.content, self.world, "socialize")  # 指名求見算一次交遊（新手引導、任務）
            msgs += check_thresholds(self.state, self.content, self.world, self.client, now=self.now)
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
        if kind == "call":
            return "收回名帖" if arg == "back" else f"求見・{c.characters[arg].name}"
        here = c.locations[s.player.location].name
        titles = {
            "explore": f"探索{here}", "socialize": f"交遊・{here}", "call": f"求見・{here}", "train": f"歷練・{here}",
            "recruit": f"招募・{here}", "rest": f"打坐・{here}", "stand": "起身", "halt": "喊停",
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

    def _act(self, what: str, prepared: companion_agent.PreparedTurn | None = None) -> list[str]:
        cost = self.content.config.action_cost
        if what == "break":
            return self._finish_seclusion(self.state.world.time)
        if what == "stand":
            return self._stand_up()
        if what == "halt":
            return self._halt()
        if what == "recruit":
            return self._recruit()
        if what == "rest":
            return self._rest()
        if what == "call":
            self.state.player.picking_audience = True  # 打開求見選單（見 _audience_options），不花體力
            return [f"你遞上名帖，準備求見{self.content.locations[self.state.player.location].name}的人物。"]
        self.state.player.stamina -= cost[what]
        if what == "explore":
            return self._explore()
        if what == "train":
            return self._train()
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
        companion_id = self._socialize_figure()
        if companion_id is not None:
            return self._open_dialogue(companion_id, prepared)
        return self._encounter("socialize", self._no_audience_line())

    def _call(self, arg: str, prepared: companion_agent.PreparedTurn | None = None) -> list[str]:
        """求見選單上的選擇：「返回」收起選單；選了一位人物就跟他開口對話，跟交遊碰上人物時一模一樣——
        花交遊的體力、生成不出對話就退回（見 _open_dialogue）。福緣不在這裡發：指名求見就是要見這個人
        （福緣照舊由交遊先發，或到期自己送上門，見 _advance_player_local）。"""
        self.state.player.picking_audience = False
        if arg == "back":
            return ["你收回名帖，暫且不求見了。"]
        self.state.player.stamina -= self.content.config.action_cost["socialize"]
        return self._open_dialogue(arg, prepared)

    def _open_dialogue(self, companion_id: str, prepared: companion_agent.PreparedTurn | None) -> list[str]:
        """跟一位大勢人物開口對話（呼叫端已經扣了交遊的體力）：生成不出對話時退回那份體力，對話不開始。"""
        try:
            return companion_agent.start_dialogue(
                self.client, self.state, self.content, self.world, companion_id, self.rng,
                turn=self._prepared_turn(prepared),
            )
        except companion_agent.DialogueUnavailable:
            self.state.player.stamina += self.content.config.action_cost["socialize"]  # 生成不出對話：這次不花體力
            return self._dialogue_unavailable(companion_id)

    def _explore(self) -> list[str]:
        """探索：先滾一次煉製素材，再走一般的遭遇流程（事件／敵人／一無所獲）。

        素材的判定**刻意放在事件之前、而且不管接下來發生什麼都會滾**：原本照設計文件
        §4.2 掛在「一無所獲」那條分支上，但用真實內容跑完整季實測，100 次探索有 100 次
        都撞到手寫事件或敵人，那條分支一次都沒執行到（整季只拿到打贏掉的 3 個素材）。
        改成探索本身就有機會撿到東西，一季約 30 個，對得上設計文件 §4.4 的產出目標。
        """
        loc = self.content.locations[self.state.player.location]
        found = materials.roll_explore_drop(loc, self.content, self.rng)
        line = materials.grant(self.state, self.content, found) if found is not None else None
        nothing = "你四處走走，一無所獲。" if line is None else f"你在{loc.name}翻找了一陣。"
        msgs = self._encounter("explore", nothing)
        return msgs + [line] if line is not None else msgs

    def _train(self) -> list[str]:
        """歷練：找這個地點的敵人打一場，**必定開打**；打完有機率接一段戰後的餘韻事件。

        這個行動在 sanguo-companions 合併時被整個移除，後果是整條隨機遭遇戰的路斷掉：
        `pick_event()` 只在「完全沒有合格候選」時才回 None，而有三個事件是「任何地點、
        可重複、探索觸發」，所以實測 22 個地點探索都是 100% 撞到事件，掛在 explore 後面的
        遭遇戰分支一次都沒執行過（整季只有劇情事件的 combat 選項那 3 場）。

        打完之後的 `train_event_chance` 機率是給 `actions: ["train"]` 的事件用的——「拆招頓悟」
        與「錦衣少年」的文字本來就是戰後餘韻（「一番苦戰之後…」「打鬥剛歇…」），合併時被改掛
        到 explore，於是在集市散步也會冒出來。現在它們回到正確的位置。
        """
        loc = self.content.locations[self.state.player.location]
        squad = self.content.squads[self.rng.choice(loc.enemies)]
        msgs = self._squad_encounter(squad.id)
        if self._drills_with(squad):
            return msgs  # 操練沒有打架，不接「一番苦戰之後」這類戰後事件（試玩回饋 FB-001）
        if self.rng.random() < self.content.config.train_event_chance:
            event = pick_event(self.state, self.content, "train", self.rng)
            if event is not None:
                msgs += self._present(event)
        return msgs

    def _rest(self) -> list[str]:
        """坐下來打坐（地圖擴充設計第二節）：進入「打坐中」，之後時間過去時體力回復是平常的
        rest_regen_multiplier 倍；期間不能做別的事，隨時可以起身。跟閉關同一種做法：狀態記在玩家身上，
        回復由 _advance_player_local 照經過的時間算，不碰共用賽季時鐘。原本按一下立刻補一個時辰的回復、
        又不延後自然回復，連按就能無限回體力。選單上永遠有這個選項、不受體力門檻限制——實機 playtest
        發現過體力歸零後整排按鈕都按不下去、新玩家卡死的情況。"""
        self.state.player.resting_since = self.state.world.time
        multiplier = self.content.config.rest_regen_multiplier
        return [f"你就地坐下打坐，體力回復是平常的 {multiplier:g} 倍；隨時可以起身。"]

    def _stand_up(self, full: bool = False) -> list[str]:
        """起身：打坐結束，體力回復恢復平常的速度。按「起身」時寫在這次行動的紀錄裡；體力回滿自己起身
        （sync／advance 裡，沒有進行中的行動）或加入戰局時起身，另寫一則「起身」。"""
        p = self.state.player
        minutes = max(0, round((self.state.world.time - p.resting_since) / 60))
        p.resting_since = None
        msg = "體力已經回滿，你收功起身。" if full else f"你收功起身（打坐了約 {minutes} 分鐘）。"
        if self._draft is None:
            self._write("起身", [msg])
        return [msg]

    def _figures_here(self) -> list[str]:
        """這個地點的大勢人物（不管見不見得到）：可招募的 7 位在 recruit_at，鎖定的 8 位龍頭
        人物在 talk_at（不可招募，見「還要改進」第 5 點）。"""
        s, c = self.state, self.content
        return [
            cid for cid, ch in c.characters.items()
            if ch.deep_interaction and s.player.location in (ch.recruit_at, ch.talk_at)
        ]

    def _can_meet(self, companion_id: str) -> bool:
        """見得到這位人物：名望到了他的求見門檻，或是透過他的「結識」事件認識過（企劃者 2026-10-02 決定）。"""
        p = self.state.player
        return f"結識:{companion_id}" in p.flags or p.stats.get("fame", 0) >= self.content.characters[companion_id].audience_fame

    def _talks_used(self, companion_id: str) -> int:
        """今天（遊戲日，跟福緣用同一個算法）已經跟這位人物聊了幾輪；紀錄是前幾天的就當沒聊過。"""
        record = self.state.player.talks_today.get(companion_id)
        return record[1] if record and record[0] == current_day(self.state) else 0

    def _talks_left(self, companion_id: str) -> int:
        """今天（遊戲日）還能跟這位人物聊幾輪。"""
        return max(0, self.content.config.talk_turns_per_day - self._talks_used(companion_id))

    def _count_talk(self, companion_id: str) -> list[str]:
        """記一輪；今天聊滿了就自動告辭。"""
        self.state.player.talks_today[companion_id] = [current_day(self.state), self._talks_used(companion_id) + 1]
        if self._talks_left(companion_id) > 0:
            return []
        self.state.player.pending_companion = None
        return [f"天色已晚，{self.content.characters[companion_id].name}起身送客，改日再敘。"]

    def _deep_interaction_target(self) -> str | None:
        """這個地點此刻能深度對話的人物 id：見得到（名望或結識），而且今天還沒聊滿；沒有就是 None。"""
        for companion_id in self._figures_here():
            if self._can_meet(companion_id) and self._talks_left(companion_id) > 0:
                return companion_id
        return None

    def _audience_hall(self) -> bool:
        """這裡有兩位以上的大勢人物：交遊不再直接找第一位見得到的人，改按「求見」指名（企劃者 2026-10-03 決定）。"""
        return len(self._figures_here()) >= AUDIENCE_HALL_FIGURES

    def _socialize_figure(self) -> str | None:
        """交遊會直接開口對話的那位人物：只有這裡至多一位大勢人物時才有（見得到、今天還沒談滿，見
        _deep_interaction_target）；兩位以上的地點交遊只走福緣與地點事件，人物要按「求見」指名。"""
        if self._audience_hall():
            return None
        return self._deep_interaction_target()

    def _audience_options(self) -> list[Option]:
        """求見的第二層選單：這裡每一位大勢人物一個選項，最後是永遠按得下去的「返回」。名望不夠（也沒結識過）、
        或今天已經跟他談滿的人按不下去並寫明原因；每天的輪數上限是每位人物各算各的（talk_turns_per_day）。"""
        c = self.content
        cost = c.config.action_cost["socialize"]
        per_day = c.config.talk_turns_per_day
        opts = []
        for companion_id in self._figures_here():
            ch = c.characters[companion_id]
            option_id = f"call:{companion_id}"
            left = self._talks_left(companion_id)
            if not self._can_meet(companion_id):
                opts.append(Option(id=option_id, label=f"{ch.name}（名望 {ch.audience_fame} 以上才見得到）", enabled=False))
            elif left == 0:
                opts.append(Option(id=option_id, label=f"{ch.name}（今天已經談滿 {per_day} 輪，明天再來）", enabled=False))
            else:
                opts.append(self._cost_option(option_id, ch.name, cost, note=f"今天還能談 {left}/{per_day} 輪"))
        opts.append(Option(id="call:back", label="返回"))
        return opts

    def _audience_intro(self) -> str:
        """求見畫面的說明（場景上的那一段）：挑一位拜會；每位人物每天最多談幾輪，各算各的。"""
        here = self.content.locations[self.state.player.location].name
        per_day = self.content.config.talk_turns_per_day
        return f"{here}有好幾位人物，挑一位求見。每位人物每天最多談 {per_day} 輪，各算各的；名望不夠的見不到，談滿的明天再來。"

    def _no_audience_line(self) -> str:
        """交遊時見不到這裡的大勢人物時的說明；這裡沒有大勢人物就是原本的「此地無人可訪」；
        兩位以上大勢人物的地點交遊不找人，提醒要按「求見」。"""
        if self._audience_hall():
            return "你四處結交了一番，沒遇上什麼事；想拜會此地的人物，請按「求見」指名。"
        for companion_id in self._figures_here():
            ch = self.content.characters[companion_id]
            if not self._can_meet(companion_id):
                return f"你想求見{ch.name}，但人微言輕，被擋在門外（名望 {ch.audience_fame} 以上才見得到）。"
            if self._talks_left(companion_id) == 0:
                return f"{ch.name}今日事忙，改日再來拜會吧。"
        return "此地無人可訪，你只好悻悻離去。"

    def socialize_starts_dialogue(self) -> bool:
        """在這裡交遊會直接跟大勢人物對話（伺服器假人不閒聊大勢人物，見 bot_policy）。"""
        return self._socialize_figure() is not None

    def socialize_is_futile(self) -> bool:
        """在這裡交遊注定白跑一趟（伺服器假人不該去按）：這個地點沒有交遊事件、沒有見得到的大勢人物，
        而且福緣還沒到期（交遊最先發福緣，見 _act）。"""
        s, c = self.state, self.content
        return (
            not has_events_here(c, c.locations[s.player.location], "socialize")
            and self._socialize_figure() is None
            and not roster.fortune_due(s, c)
        )

    def _dialogue_unavailable(self, companion_id: str) -> list[str]:
        """這一輪生成不出對話（模型叫不動）：這輪不算數、對話結束（企劃者決定：不要卡在同一句
        保底反應裡白扣體力）。"""
        self.state.player.pending_companion = None
        return [f"{self.content.characters[companion_id].name}似乎無心多談，你只好先行告辭。"]

    def _talk(self, arg: str, prepared: companion_agent.PreparedTurn | None = None) -> list[str]:
        companion_id = self.state.player.pending_companion
        if companion_id is None:
            return ["（此刻無法這麼做。）"]
        if arg == "leave":
            return companion_agent.leave_dialogue(self.state)
        try:
            msgs = companion_agent.continue_dialogue(
                self.client, self.state, self.content, self.world, companion_id, int(arg), self.rng,
                turn=self._prepared_turn(prepared),
            )
        except companion_agent.DialogueUnavailable:
            return self._dialogue_unavailable(companion_id)
        self.state.player.stamina -= self.content.config.talk_stamina  # 每一輪對話都要花體力（伺服器假人設計第八節第 4 項）；生成不出來的那輪不算
        msgs += self._count_talk(companion_id)
        return msgs

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
        if p.faction is not None and self.world.faction_of(p.name) != p.faction:
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
        """核心推進邏輯（在呼叫端的 mutate_battle callback 裡原地修改 battle）：
        集結逾時自動分配、機器人補位、場上沒人能打又逾時就用保底結果收場、回合逾時代選
        保守行動、全員到齊就結算並請 LLM 潤色。回傳這次呼叫如果真的結算了一回合（或收場）
        的敘事訊息，沒有結算就是空清單。這是
        _run_battle_tick()（被動追趕，options()/scene_text() 用）跟 _battle_choose()
        的 act 分支（玩家自己送出行動，可能剛好湊滿全員）共用的同一份邏輯，確保兩條
        路徑的推進規則完全一致——只是呼叫的時間點跟是否先 submit_action 不同。"""
        now = self.now
        if battle.phase == "muster" and now >= battle.muster_deadline_real:
            battle_instance.close_muster(battle, definition, self.rng, now)
        if battle.phase != "active":
            return []
        for p in list(battle.participants.values()):
            if p.is_bot and not p.eliminated and not p.away and p.name not in battle.round.pending_actions:
                tag = battle_instance.bot_choose_action(battle, definition, p.name, self.rng)
                if tag:
                    battle_instance.submit_action(battle, p.name, tag)
        ended = battle_instance.end_without_fighters(battle, definition, now)  # 沒人能打、回合逾時：用保底結果收場
        if ended:
            return ended
        if now - battle.round.opened_real >= definition.round_seconds and not battle_instance.round_is_complete(battle):
            battle_instance.fill_timed_out_actions(battle, definition)
        if not battle_instance.round_is_complete(battle):
            return []
        msgs = battle_instance.resolve_round(battle, definition, self.rng, now=now)
        narration = battle_instance.narrate_round(self.client, definition, battle, msgs)
        if narration:
            battle.narrative_log.append(narration)
            battle.rounds[-1].narration = narration  # resolve_round 剛記下這一回合
        return [narration] if narration else msgs

    def _run_battle_tick(self, definition: BattleDef) -> tuple[battle_instance.BattleInstance | None, list[str]]:
        """在 mutate_battle 裡跑一次 _advance_battle_round，給被動追趕（options()/scene_text()）用。"""
        captured: dict[str, list[str]] = {"msgs": []}

        def _apply(b: battle_instance.BattleInstance) -> None:
            captured["msgs"] = self._advance_battle_round(b, definition)

        battle = self.world.mutate_battle(_apply)
        return battle, captured["msgs"]

    def _apply_battle_outcome(self, battle: battle_instance.BattleInstance) -> None:
        """戰鬥剛結束這一刻，把結果套用到共用賽季（大勢推動／世界旗標），順便留一筆
        江湖史——這裡故意不在 mutate_battle 的 callback 裡面做（寫入交易雖然可以巢狀，但 mutate 的
        callback 裡再呼叫 mutate_season，內層寫的會被外層的整份存檔蓋掉，database.rewriting 會直接丟
        RuntimeError），所以是呼叫端在拿到 mutate_battle 的結果、callback 已經結束之後才呼叫，
        順序上一定晚於戰鬥本身的結算。

        結果也要套到自己手上的 self.state.world：結算可能發生在 choose()／travel() 的 options() tick 裡，
        而它們收尾的 _save_season 會把這份記憶體裡的賽季整份寫回去——不跟著改，剛寫進資料庫的大勢與旗標
        就被比較舊的那份蓋掉了（江湖史是另一張表，不受影響，所以只有它倖存）。江湖史那一則只寫資料庫，
        不寫記憶體，免得存兩次。"""
        if not (battle.outcome_world_flags or battle.outcome_trend_delta or battle.outcome_title):
            return

        def _apply(season: WorldState) -> None:
            self._apply_outcome_trends_and_flags(season, battle)
            if battle.outcome_title:
                season.chronicle.append(Rumor(time=season.time, text=f"【{battle.outcome_title}】{battle.outcome_text}"))

        self.world.mutate_season(_apply)
        self._apply_outcome_trends_and_flags(self.state.world, battle)

    @staticmethod
    def _apply_outcome_trends_and_flags(season: WorldState, battle: battle_instance.BattleInstance) -> None:
        """決戰結果的大勢變化與世界旗標，套到 season 上（資料庫裡的那份與記憶體裡的那份共用這一段）。"""
        for trend_id, delta in battle.outcome_trend_delta.items():
            season.trends[trend_id] = max(0, min(100, season.trends.get(trend_id, 0) + delta))
        for flag in battle.outcome_world_flags:
            if flag not in season.flags:
                season.flags.add(flag)
                season.flag_times[flag] = season.time

    def _watching_battle(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> bool:
        """這個人此刻打不了這場仗、只能在一旁看（options() 照常給平常的選項，場景上仍看得到戰場）：
        - 劇本分陣營時，自己的陣營不是交戰的任何一方，而且還在集結、或已經開打但他不在場上；
        - 參戰者離開了決戰的大區（人在區外，或這一趟路正要走出大區；區內站與站之間走動不算）：這回合不出手，
          照常遊玩，回來才回到戰場；
        - 還沒參戰的人不在決戰的大區、或在路上（地圖擴充設計第六節：人要在現場才能加入）。
        全服決戰不能把打不了仗的人鎖住。"""
        me = battle.participants.get(self.state.player.name)
        if self._off_side(definition):
            if battle.phase == "muster" or me is None:
                return True
        if me is not None:
            return me.away
        return not self._at_battle(definition)

    def _off_side(self, definition: BattleDef) -> bool:
        """劇本分陣營、而自己的陣營（散人沒有）不是這場決戰交戰的任何一方。"""
        return bool(self.content.scenario.factions) and self.state.player.faction not in {f.id for f in definition.factions}

    def _at_battle(self, definition: BattleDef) -> bool:
        """人在這場決戰的大區、而且不在路上，才算到了戰場（地圖擴充設計第六節）；決戰不限地點時只看在不在路上。
        這是「加入」的條件，也是還沒參戰的人算不算在場；已經參戰的人看 _in_battle_region。"""
        if self.state.player.journey is not None:
            return False
        if definition.region is None:
            return True
        region = atlas.region_of(self.content, self.state.player.location)
        return region is not None and region.id == definition.region

    def _in_battle_region(self, definition: BattleDef) -> bool:
        """參戰者還算不算在戰場（地圖擴充設計第六節：只有「離開大區」才讓人這回合不出手）：決戰不限地點時
        一律算在場；有大區時，所在地和這一趟還沒走到的站都在那個大區才算——在區內站與站之間走動仍在場上，
        要走出區外的路一出發就算離開。"""
        if definition.region is None:
            return True
        j = self.state.player.journey
        stops = [self.state.player.location] + ([] if j is None else j.path[j.reached:j.last + 1])
        return all(
            (region := atlas.region_of(self.content, stop)) is not None and region.id == definition.region for stop in stops
        )

    def _battle_region_name(self, definition: BattleDef) -> str:
        return next((r.name for r in self.content.map.regions if r.id == definition.region), "戰場")

    def _absent_reason(self, definition: BattleDef) -> str:
        """還沒到戰場、不能加入的原因（不含括號與句號）。"""
        if definition.region is None:
            return "你還在路上，到了才能加入戰局"
        return f"這場決戰在{self._battle_region_name(definition)}，人要到了那裡、不在路上才能加入"

    def _watch_line(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> str:
        """只能觀戰時，場景上說明為什麼：不是交戰的一方、參戰後離開了大區、或還沒到戰場。"""
        if self._off_side(definition):
            return "你不屬於交戰的任何一方，在一旁觀戰。"
        if self.state.player.name in battle.participants:
            region = self._battle_region_name(definition)
            return f"你離開了{region}，這回合不出手；人回到{region}就能再出手。"
        return f"{self._absent_reason(definition)}。"

    def _sync_battle_presence(self) -> None:
        """參戰者出發或抵達時，把「人還在不在決戰的大區」記到戰鬥上：離開大區的這回合不出手。"""
        status = self._battle_status(tick=False)
        if status is None:
            return
        battle, definition = status
        name = self.state.player.name
        me = battle.participants.get(name)
        if me is None:
            return
        away = not self._in_battle_region(definition)
        if me.away != away:
            self.world.mutate_battle(lambda b: battle_instance.set_away(b, name, away))

    def rally_region(self) -> str | None:
        """自己這一方正在集結或開打的全服決戰、而自己人不在現場時，回傳那場決戰的大區 id，給伺服器假人決定要不要
        趕路（地圖擴充設計 3.4）。不在現場的意思：還沒參戰的人不在那個大區或在路上；參戰者離開了大區
        （見 _in_battle_region）。沒有這種決戰、決戰不限地點、打不了這場、已經在場上或倒下了，都是 None。"""
        status = self._battle_status(tick=False)
        if status is None:
            return None
        battle, definition = status
        if definition.region is None:
            return None
        if self._off_side(definition):
            return None
        me = battle.participants.get(self.state.player.name)
        if me is not None:
            return definition.region if me.away and not me.eliminated else None
        return None if self._at_battle(definition) else definition.region

    def _battle_scene_text(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> str:
        header = f"**{definition.name}**"
        watching = self._watching_battle(battle, definition)
        watch_line = self._watch_line(battle, definition)
        if battle.phase == "muster":
            remaining = max(0, int(battle.muster_deadline_real - self.now))
            countdown = f"集結中，還剩 {remaining // 60} 分 {remaining % 60} 秒"
            return f"{header}\n\n{countdown}。{watch_line}" if watching else f"{header}\n\n{countdown}選擇陣營。"
        act = battle_instance.current_act(battle, definition)
        lines = [header, f"【{act.title}】{act.text}"] + battle.narrative_log[-5:]
        p = battle.participants.get(self.state.player.name)
        if p is not None and p.eliminated:
            lines.append("（你已經倒下，只能在一旁觀戰。）")
        elif watching:  # 倒下的人不會再出手，不必再說「回到大區就能再出手」
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
        戰鬥中、集結期、已經出局、這回合已經選過）就回傳 None，server.py 用這個決定輸入框
        要不要顯示。"""
        status = self._battle_status(tick=False)
        if status is None:
            return None
        battle, definition = status
        name = self.state.player.name
        p = battle.participants.get(name)
        if battle.phase != "active" or p is None or p.eliminated or p.away or name in battle.round.pending_actions:
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
        if p is None or p.eliminated or p.away or name in battle.round.pending_actions:
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
        battle, definition = status
        name = self.state.player.name
        kind, _, rest = arg.partition(":")
        # 已經報名的人在區內走動時改選陣營不是「加入」，不用再驗人在不在戰場（_at_battle 在路上一律是否）
        changing_sides = kind == "join" and name in battle.participants
        if kind in ("join", "join_late") and not changing_sides and not self._at_battle(definition):
            return [f"（{self._absent_reason(definition)}。）"]
        if kind == "join":
            if self.content.scenario.factions and rest != self.state.player.faction:
                return ["（你只能站在自己陣營這一邊。）"]
            stood = self._stand_up() if self.state.player.resting_since is not None else []  # 加入戰局就起身
            self.world.mutate_battle(
                lambda b: battle_instance.join_faction(b, name, rest, self._battle_neili_cap(), self._battle_power())
            )
            return stood + ["你加入了這場戰局。"]
        if kind == "join_late":
            own = self.state.player.faction if self.content.scenario.factions else None
            stood = self._stand_up() if self.state.player.resting_since is not None else []  # 加入戰局就起身
            self.world.mutate_battle(
                lambda b: battle_instance.auto_assign_latecomer(
                    b, definition, name, self._battle_neili_cap(), self.rng, self._battle_power(), faction=own,
                )
            )
            return stood + ["你加入了戰局，這回合先觀戰，下回合開始可以行動。"]
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
        """遭遇一支敵方隊伍：單次判定，勝得對手獎勵與屬性機會，落敗失落一成銀兩；自己陣營的隊伍改成操練（見 _drill）。"""
        s, c = self.state, self.content
        p = s.player
        loc = c.locations[p.location]
        squad = c.squads[squad_id]
        if self._drills_with(squad):
            return self._drill(squad)
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
                extra += change_trend(s, c, trend_id, self._train_push(trend_id, delta))
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
        toll = team.take_encounter_toll(s, c, self.world, result.tier)
        record.changes += toll
        msgs += toll
        msgs.insert(0, self._file_battle(record))
        return msgs

    def _drills_with(self, squad: Squad) -> bool:
        """這支隊伍是自己陣營的：遇上了不打，改成一起操練（見 _drill）。"""
        return squad.faction is not None and squad.faction == self.state.player.faction

    def _drill(self, squad: Squad) -> list[str]:
        """在自己陣營的地方歷練：不打自己人，一起操軍擺陣（企劃者 2026-10-02 決定）。不會輸、不扣氣血；
        給經驗與心得、有機會加屬性；不給銀兩、不掉素材（不搶自己人）；地點的大勢推動往自己陣營有利的方向推。"""
        s, c = self.state, self.content
        p = s.player
        loc = c.locations[p.location]
        msgs = [f"你與{squad.name}一同操軍擺陣，軍心為之一振。"]
        self._outcome("操練", msgs[0])
        xinde_line = None
        if squad.reward_xinde:
            p.stats["xinde"] = p.stats.get("xinde", 0) + squad.reward_xinde
            xinde_line = f"心得 +{squad.reward_xinde}"
            msgs.append(xinde_line)
            if self._draft is not None:
                self._draft.hide(xinde_line)
                self._draft.changes.append(xinde_line)
        msgs += team.add_team_exp(s, c, self.world, squad.exp)  # 本人與帶著的同伴都拿（FB-002）
        if self._draft is not None and squad.exp > 0:
            self._draft.changes.append(f"經驗 +{squad.exp}（每人）")
        if self.rng.random() < c.config.train_stat_chance:
            key = self.rng.choice(["str", "agi", "con"])
            p.stats[key] += 1
            msgs.append(f"{c.config.stat_names[key]} +1")
        for trend_id, delta in loc.train_trend.items():
            msgs += change_trend(s, c, trend_id, self._train_push(trend_id, delta))
        return msgs

    def _train_push(self, trend_id: str, delta: int) -> int:
        """歷練（打贏或操練）推大勢：量照地點設定；自己陣營對這條線有目標就往目標方向推，散人和
        沒有這條線目標的陣營照地點原本的方向（企劃者 2026-10-02 決定）。"""
        faction = next((f for f in self.content.scenario.factions if f.id == self.state.player.faction), None)
        goal = faction.goals.get(trend_id, 0) if faction is not None else 0
        return abs(delta) * goal if goal else delta

    def train_trend_push(self, loc_id: str | None = None) -> dict[str, int]:
        """在這個地點（預設所在地）歷練打贏或操練時，各條大勢線會被推多少（照自己的陣營，見 _train_push）。"""
        loc = self.content.locations[loc_id or self.state.player.location]
        return {trend_id: self._train_push(trend_id, delta) for trend_id, delta in loc.train_trend.items()}

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
        for material_id, count in materials.roll_squad_drops(squad, self.content, self.rng):
            line = materials.grant(self.state, self.content, material_id, count)
            if line:
                record.materials.append(line.removeprefix("獲得 "))
                msgs.append(line)
        record.exp = squad.exp
        levels = team.add_team_exp(self.state, self.content, self.world, squad.exp)  # 每人都拿（FB-002）
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
        """選單上的「前往 某地」：沿直接相連的那條路步行出發（趕路、疾行在大地圖的安排前往）。"""
        return self._depart([dest_id], "walk")

    def _depart(self, path: list[str], mode: TravelMode) -> list[str]:
        """出發（地圖擴充設計 3.2、3.3）：趕路、疾行的體力出發時一次扣，照走法排好每一站的抵達時間。
        疾行立刻一站一站抵達；步行、趕路就在路上，之後由 sync／advance 補算抵達（見 _arrivals）。"""
        s, c = self.state, self.content
        legs = atlas.path_legs(c, s.player.location, path)
        minutes = sum(legs)
        cost = atlas.travel_stamina(c, minutes, mode)
        s.player.stamina -= cost
        s.player.journey = Journey(mode=mode, path=path, arrive_at=atlas.arrival_times(s.world.time, legs, mode))
        if self._draft is not None:
            self._draft.tag = atlas.MODES[mode] + atlas.mode_when(minutes, mode)
            if cost:
                self._draft.changes.append(f"體力 -{cost}")
        if mode == "dash":
            return self._arrivals()
        arrive = s.player.journey.arrive_at[-1]
        left = atlas.whole_minutes((arrive - s.world.time) / 60)
        msg = f"你動身{atlas.MODES[mode]}前往{c.locations[path[-1]].name}，{battlelog.clock_text(arrive)} 抵達（約 {left} 分鐘後）。"
        self._hide(msg)  # 場景會顯示「在路上」，紀錄只留標題與走法
        self._sync_battle_presence()
        return [msg]

    def _arrivals(self) -> list[str]:
        """在路上：抵達時間已經到了的站，一站一站抵達（地圖擴充設計 3.3）。走到這一趟的最後一站（終點或喊停的
        那一站）就下馬。賽季已經落幕時，落幕前就該到的站照樣抵達（時鐘停在落幕那一刻，之後的站不會再到），
        然後停在當下那一站；抵達某一站時觸發了賽季落幕，就停在那一站。不在行動裡（sync、advance）時自己寫
        江湖紀錄（見 journal.add_arrival），而且不叫模型——它們在計時器裡、拿著全服行動鎖；疾行在
        travel() 的行動裡，寫在那次行動的紀錄，照原本的規則可以叫模型。"""
        s, c = self.state, self.content
        j = s.player.journey
        if j is None or (j.arrive_at[j.reached] > s.world.time and not s.world.ended):
            return []
        own = self._draft is None
        client = None if own else self.client  # sync／advance 的抵達（計時器、備料都拿著行動鎖）不叫模型；只有疾行在玩家自己這次行動裡
        if own:
            self._draft = Draft(atlas.journey_title(c, j.path))
        try:
            already_over = s.world.ended
            msgs: list[str] = []
            when = s.world.time
            while j.reached <= j.last and j.arrive_at[j.reached] <= s.world.time:
                if s.world.ended and not already_over:
                    break  # 剛抵達的那一站觸發了賽季落幕：停在那裡
                when = j.arrive_at[j.reached]
                j.reached += 1
                msgs += self._arrive(j.path[j.reached - 1], final=j.reached > j.last, client=client)
            done = j.reached > j.last or s.world.ended
            if done:
                s.player.journey = None
                if s.player.location != j.path[-1]:
                    reason = "賽季落幕" if s.world.ended else "喊停"
                    self._draft.tag = f"{reason}，停在 {c.locations[s.player.location].name}"
            if own:
                entry = self._draft.entry(when, msgs)
                if done or entry.lines or entry.changes:  # 只到了中途的站、又沒有別的事，不另寫一則
                    journal.add_arrival(s, entry, done)
        finally:
            if own:
                self._draft = None
        self._sync_battle_presence()
        return msgs

    def _arrive(self, loc_id: str, final: bool, client: OllamaClient | None = None) -> list[str]:
        """抵達一站：照原本走到一個地點的規則——地點描寫、新手引導、大勢門檻。終點是重遊的一般地點時才多請模型
        補一句此刻的小細節（中途的站不補，省得一趟路叫好幾次模型）。client 是這次抵達可以用的模型：
        None（計時器的抵達）就完全不叫模型，重遊點綴句與江湖大事的潤色都省掉；門檻照樣觸發。"""
        s, c = self.state, self.content
        dest = c.locations[loc_id]
        is_revisit = loc_id in s.player.visited
        s.player.location = loc_id
        s.player.visited.add(loc_id)
        text = self.location_text()
        if final and is_revisit and not dest.important and client is not None:
            flourish = flavor.polish_revisit(client, dest.name, dest.description)
            if flourish:
                text = f"{text}\n\n{flourish}"
        self._hide(text)
        return [text] + note_action(s, c, self.world, "move") + check_thresholds(s, c, self.world, client, now=self.now)

    def _journey_line(self) -> str:
        """在路上的那一句（狀態列、場景共用）：「往寶洞（步行），第1天 00:08 抵達，還要約 8 分鐘；下一站湖邊」。"""
        s, c = self.state, self.content
        j = s.player.journey
        end = j.arrive_at[j.last]
        left = atlas.whole_minutes(max(0.0, end - s.world.time) / 60)
        line = (
            f"往{c.locations[j.path[j.last]].name}（{atlas.MODES[j.mode]}），"
            f"{battlelog.clock_text(end)} 抵達，還要約 {left} 分鐘"
        )
        if j.reached < j.last:
            line += f"；下一站{c.locations[j.path[j.reached]].name}"
        return line

    def _halt(self) -> list[str]:
        """喊停（地圖擴充設計 3.3）：到下一站就停下，不走完全程。不花體力；趕路已經扣的體力也不退。"""
        s, c = self.state, self.content
        j = s.player.journey
        j.stop_at = j.reached
        msgs = [f"你喊停，到了{c.locations[j.path[j.reached]].name}就停下來。"]
        if j.mode == "hurry":
            msgs.append("（趕路已經花掉的體力不退。）")
        self._sync_battle_presence()  # 這一趟縮短了：最後一站落在決戰的大區內，就不再算離開
        return msgs

    def travel(self, dest_id: str, mode: TravelMode = "walk") -> list[str]:
        """安排前往（大地圖詳情欄的按鈕）：照路程最短的路線出發，走法見 _depart。"""
        refusal = self.travel_refusal(dest_id, mode)
        if refusal is not None:
            return self._log([f"（{refusal}。）"])
        s, c = self.state, self.content
        route = atlas.routes(s, c)[dest_id]
        s.battle_card = None
        self._draft = Draft(atlas.journey_title(c, route.path))
        try:
            msgs = self._depart(list(route.path), mode)
            journal.add_entry(s, self._draft.entry(s.world.time, msgs))
        finally:
            self._draft = None
        self._save_season()
        return self._log(msgs)

    def travel_refusal(self, loc_id: str, mode: TravelMode = "walk") -> str | None:
        """用這種走法安排前往這裡，不行的原因；可以時為 None。server.py 拿它分辨「沒能出發」。"""
        if self._preparing():
            return "賽季籌備中，等待管理者開季"
        if loc_id not in self.content.locations or mode not in atlas.MODES:
            return "無法安排前往這裡"
        return atlas.travel_refusal(self.state, self.content, loc_id, mode)

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
            and s.player.resting_since is None and s.player.journey is None and not s.player.picking_audience
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

    def craft(self, material_ids: list[str], kind: str) -> list[str]:
        """煉製：兩樣素材煉成一門功法，花心得（見 tianxia/craft.py）。

        LLM 只在「全服第一次煉出這個配方」時被呼叫一次，而且只負責取名字；配方命中就是純
        查表。呼叫在這裡而不是在 `craft.py` 裡拿 client，是為了跟其他門下動作一樣由 Game
        統一處理江湖紀錄。
        """
        if self._preparing():
            return self._log(["（賽季籌備中，等待管理者開季。）"])
        xinde = self._xinde()
        art, msgs = craft.craft(self.state, self.content, self.world, self.client, material_ids, kind)
        out = self._log(msgs)
        if art is not None:
            self._menxia_entry(f"煉製【{art.name}】", xinde)
            out += note_action(self.state, self.content, self.world, "practice")
        return out

    def craft_cost(self, material_ids: list[str]) -> int:
        return craft.cost(self.content, material_ids)

    def craft_line(self, material_ids: list[str], kind: str) -> str:
        return skillview.craft_line(self.state, self.content, material_ids, kind, self.world)

    def material_choices(self) -> list[tuple[str, str]]:
        """煉製選單的素材選項：（顯示文字, 素材 id），階高的排前面。"""
        return [
            (f"{m.name}（{materials.tier_label(m)}・屬{m.attribute}）×{n}", m.id)
            for m, n in materials.bag_contents(self.state, self.content)
        ]

    def art_library(self) -> list[tuple[str, str]]:
        return skillview.art_library(self.state, self.content, self.world)

    def switch_art(self, art_id: str) -> list[str]:
        """改練：把功法庫裡的一門換上身（見 team.switch_art）。"""
        if self._preparing():
            return self._log(["（賽季籌備中，等待管理者開季。）"])
        xinde = self._xinde()
        msgs = self._log(team.switch_art(self.state, self.content, self.world, art_id))
        self._menxia_entry(msgs[-1] if msgs else "改練", xinde)
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

    def bag_text(self) -> str:
        return skillview.bag_text(self.state, self.content)

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

    def travel_options(self, loc_id: str) -> list[atlas.TravelOption] | None:
        return atlas.travel_options(self.state, self.content, loc_id)

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

    def _admin_refusal(self, action: str) -> list[str] | None:
        """管理者觸發的共同檢查：不是管理者、或賽季沒有在進行，回傳要顯示的拒絕訊息；可以做就回傳 None。"""
        if not self.is_admin():
            return [f"（只有管理者能{action}。）"]
        if self.world.season_phase() != "running":
            return ["（賽季沒有在進行，無法觸發。）"]
        return None

    def admin_start_battle(self, battle_id: str, now: float) -> list[str]:
        """管理者直接開一場全服戰鬥（試玩時人少、大勢推不到門檻也能開戰）。"""
        refusal = self._admin_refusal("開戰")
        if refusal:
            return self._log(refusal)
        definition = self.content.battles.get(battle_id)
        if definition is None:
            return self._log(["（沒有這場戰鬥。）"])
        current = self.world.get_battle()
        if current is not None and current.phase != "ended":
            return self._log(["（已經有一場戰鬥在進行。）"])
        self.world.start_battle(definition, now)
        msgs = [f"🛡️ 【全服戰報】{definition.name}的集結號角已經吹響！"]
        self._write(f"開戰・{definition.name}", msgs, tag="管理者")
        return self._log(msgs)

    def admin_fire(self, fire_id: str) -> list[str]:
        """管理者直接觸發一則大勢門檻或世界事件：效果跟自然發生一樣，一季只會發生一次。"""
        refusal = self._admin_refusal("觸發大事")
        if refusal:
            return self._log(refusal)
        if fire_id in self.state.world.fired_thresholds:
            return self._log(["（這件大事已經發生過了。）"])
        msgs = fire_by_id(self.state, self.content, fire_id, self.world, self.client, now=self.now)
        if msgs is None:
            return self._log(["（沒有這件大事。）"])
        self._write("觸發大事", msgs, tag="管理者")
        self._save_season()
        return self._log(msgs)

    def admin_push_trend(self, trend_id: str, delta: int) -> list[str]:
        """管理者直接推一條大勢線（正數推高、負數壓低）；推過門檻就照常觸發大事。"""
        refusal = self._admin_refusal("推動大勢")
        if refusal:
            return self._log(refusal)
        if trend_id not in {t.id for t in self.content.scenario.trends}:
            return self._log(["（沒有這條大勢線。）"])
        msgs = change_trend(self.state, self.content, trend_id, delta)
        msgs += check_thresholds(self.state, self.content, self.world, self.client, now=self.now)
        self._write("推動大勢", msgs or ["大勢紋絲不動。"], tag="管理者")
        self._save_season()
        return self._log(msgs)

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
        if s.player.picking_audience:
            return f"**求見**\n\n{self._audience_intro()}"
        if s.player.journey is not None:
            halted = "（已經喊停）" if s.player.journey.stop_at is not None else ""
            return f"**在路上**{halted}\n\n{self._journey_line()}。\n\n路上不能做事；可以先下線，到了會自己抵達。"
        return self.location_text()

    def status_data(self) -> dict:
        """狀態列的資料（數字與短字串），網頁前端照這份自己排版；status_text 是同一份資料的文字版。"""
        s, c = self.state, self.content
        p, w = s.player, s.world
        names = c.config.stat_names
        sect = c.sects[p.sect].name if p.sect else None
        faction = next((f.name for f in c.scenario.factions if f.id == p.faction), None)
        now, cap = team.member_neili(c, p.member)
        mates = []
        for cid in p.team:
            progress = self.world.get_companion(cid)
            mate_now, mate_cap = team.member_neili(c, progress)
            mates.append({"name": c.characters[cid].name, "level": progress.level,
                          "hp": int(mate_now), "hp_max": int(mate_cap)})
        return {
            "name": p.name,
            "affiliation": "・".join(name for name in (sect, faction) if name) or "散人",
            "anonymous": p.anonymous,
            "level": p.member.level,
            "location": c.locations[p.location].name,
            "day": int(w.time // DAY) + 1,
            "clock": f"{int(w.time % DAY // HOUR):02d}:{int(w.time % HOUR // 60):02d}",
            "season_days": c.config.season_days,
            "stamina": int(p.stamina),
            "stamina_max": c.config.stamina_max,
            "hp": int(now),
            "hp_max": int(cap),
            "injury": int(p.member.injury),
            "silver": p.stats.get("silver", 0),
            "xinde": p.stats.get("xinde", 0),
            "minor": [(names[k], p.stats.get(k, 0)) for k in ("fame", "good", "evil")],
            "attrs": [(names[k], p.stats[k]) for k in ("str", "agi", "con", "wis")],
            "hint": skillview.practice_hint(s, c),  # 心得擱著沒用、又還有功夫沒練滿時才有
            "team": mates,
            "busy_hours": None if p.busy_until is None else round((p.busy_until - w.time) / HOUR, 1),
            "resting": None if p.resting_since is None else c.config.rest_regen_multiplier,  # 打坐時體力回復的倍數
            "journey": None if p.journey is None else self._journey_line(),
        }

    def status_text(self) -> str:
        d = self.status_data()
        names = self.content.config.stat_names
        # 排版刻意很緊：這一塊在手機上原本是 13 段 Markdown（每段一個 <p>），光狀態就吃掉
        # 半個螢幕，選項按鈕被推到摺線以下。現在把**玩家真的一直在看的四個數字**（體力、
        # 氣血、銀兩、心得）收成一行，其餘降級到第二行，隊伍只有帶人時才列出來。
        vitals = (
            f"⚡ 體力 {d['stamina']}/{d['stamina_max']}　"
            f"❤ 氣血 {d['hp']}/{d['hp_max']}　"
            f"💰 {names['silver']} {d['silver']}　"
            f"📘 {names['xinde']} {d['xinde']}"
        )
        if d["injury"] >= 1:
            vitals += f"　🩹 內傷 {d['injury']}"
        minor = "　".join(f"{k} {v}" for k, v in d["minor"])
        attrs = "　".join(f"{k} {v}" for k, v in d["attrs"])
        lines = [
            f"### {d['name']}　·　{d['affiliation']}" + ("（匿名行走）" if d["anonymous"] else "")
            + f"　第{d['level']}級",
            f"📍 {d['location']}　⏳ 第 {d['day']} 天 {d['clock']}（本季共 {d['season_days']:g} 天）",
            vitals,
            f"{minor}　｜　{attrs}",
        ]
        if d["hint"] is not None:
            lines.append(d["hint"])
        for mate in d["team"]:  # 只有真的帶了同伴才列隊伍，一個人時不佔版面
            lines.append(f"🧍 {mate['name']}　第{mate['level']}級　氣血 {mate['hp']}/{mate['hp_max']}")
        if d["busy_hours"] is not None:
            lines.append(f"🧘 閉關中，約 {d['busy_hours']:.1f} 小時後出關")
        if d["resting"] is not None:
            lines.append(f"🧘 打坐中：體力回復是平常的 {d['resting']:g} 倍，隨時可以起身")
        if d["journey"] is not None:
            lines.append(f"🧭 在路上：{d['journey']}")
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
        """江湖史：這一季在最前面，往前每一季各一段（線上架構設計 3.2：江湖史跨季保留），最後是玉璽碎片。"""
        number = self.world.get_season_number()
        current = _timeline(self.state.world.chronicle) or "（江湖史尚無記載。）"
        past = self.world.chronicle_before(number)
        parts = [f"### 第 {number} 季（本季）\n\n{current}" if past else current]
        parts += [f"### 第 {n} 季\n\n{_timeline(entries)}" for n, entries in past]
        parts.append(self.world.jade_seal_summary())
        return "\n\n---\n\n".join(parts)

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
