"""伺服器假人程式的核心（伺服器假人設計第三、四、六節）：一輪一輪地補人、讓在線的假人做事。

run_bots.py 只負責每隔 bot_tick_seconds 呼叫一次 tick()。每個假人做一個動作都跟真人按一次
按鈕一樣：開一筆寫入交易 → 讀角色 → 補算時間 → 做動作 → 存角色 → 交易結束。拿不到寫入權（真人正在
等 LLM）就跳過這個假人的這一輪，不卡住真人。

補人：每個陣營（投靠名冊上的真人與假人，加上這一季已派去、還在路上的假人）不到最少人數，就補
一個——先叫醒退隱的假人（沿用名號），沒有才新建；同一個陣營每 bot_fill_seconds 最多補一個。
換季時所有假人自動算退隱（BotProfile.season_number 對不上），新的一季再照缺額叫醒。

模型：假人在鎖內的 Game 沒有 client，鎖內一個模型都不叫。唯一的例外是首創配方的取名與絕學定名（企劃者 2026-10-05、10-06），
走跟真人一樣的三段式：A 在鎖內開單（bot_policy.tend_arts）、B 在鎖外由這支程式自己的 client 叫 naming.generate
（_name_and_apply；一次一件、兩件之間隔 bot_naming_gap_seconds、一件最多 bot_naming_budget_seconds）、
C 再拿鎖交給 bot_policy.apply_job。
"""
from __future__ import annotations

import logging
import random
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass

from . import battle_instance, bot_policy, gender, insight_llm, naming, seal, server_bots, team
from .characters import CharacterStore, open_characters
from .engine import Game
from .models import Content
from .ollama_client import OllamaClient
from .sqlite_world import open_world
from .state import BotProfile, GameState
from .world_state import WorldStateStore

LOCK_WAIT = 2.0  # 假人等行動鎖最多幾秒；等不到就跳過這一輪
BATTLE_TICK_SECONDS = 2.0  # 決戰開打時 run_bots 多久看一次在場的假人出招了沒（battle_tick）
BATTLE_DELAY = (3.0, 12.0)  # 回合開了幾秒假人才出招：每個假人每回合擲一次，跟真人看完場景再按差不多；真人都送出了就不再等
FEMALE_SAMPLE = 5  # 真人選過性別的不到這麼多個，假人的女性比例照 gender.BOT_FEMALE_SHARE（太少的樣本照抄會整批偏一邊）

log = logging.getLogger(__name__)


def log_failure(exc: BaseException) -> None:
    """記一筆出錯，但不留下任何認得出誰是假人的東西（伺服器假人設計第五節：連開伺服器的人也不能
    從主控台或 log 看出誰是假人）。只寫例外的類別名稱與呼叫堆疊（程式碼位置與原始碼那幾行）；
    例外訊息（常夾著存檔路徑或名號）、路徑、名號一概不寫。"""
    frames = "".join(traceback.format_tb(exc.__traceback__))
    log.error("假人程式出錯：%s\n%s", type(exc).__name__, frames)


@dataclass
class TickReport:
    """一輪的摘要：只有數字，不列名號（主控台也不透露誰是假人）。"""

    online: int = 0
    acted: int = 0
    added: int = 0
    skipped: int = 0  # 等不到行動鎖而跳過的次數
    failed: int = 0  # 出錯而跳過的假人（錯誤寫進 log）
    named: int = 0  # 請模型取名的次數
    naming_skipped: int = 0  # 想開首創的爐或定名、這一輪輪不到取名而作罷的次數


class BotRunner:
    def __init__(
        self, content: Content, world: WorldStateStore | None = None, characters: CharacterStore | None = None,
        rng: random.Random | None = None, clock: Callable[[], float] = time.time,
        client: OllamaClient | None = None,
    ):
        self.content = content
        self.world = world or open_world()
        self.characters = characters or open_characters()
        self.rng = rng or random.Random()
        self.clock = clock
        self.last_added: dict[str, float] = {}  # 陣營 id -> 上次補人的現實時間
        # 只在鎖外替首創的配方與絕學定名取名用（_name_and_apply）；None＝假人不開要取名的爐、也不定名
        self.client = client
        self.last_naming: float | None = None  # 上一次請模型取名的現實時間
        self.seal_season: int | None = None  # 持碎片的退隱假人這一季擲過回不回來了（玉璽碎片設計 7.6）
        # 勝算的記憶（同 server.ODDS_MEMO，FB-321）：假人每一下都重建 Game，不共用的話每一個勝算都重跑四十場模擬；領地爭奪的季
        # 假人挑出陣地點要問好幾處的勝算（bot_policy._outmatched，7 天季調整），沒有這一份一個假人動作的時間多一倍。輸入一樣才拿記住的字，結果不變
        self.odds_memo = team.OddsMemo()

    def tick(self) -> TickReport:
        report = TickReport()
        if self.world.season_phase() != "running" or self.world.paused_at() is not None:  # 籌備、休季、暫停中都不出手
            return report
        now = self.clock()
        try:
            with self.world.action_lock(timeout=LOCK_WAIT):
                self._fill(now, report)
        except TimeoutError:
            report.skipped += 1
        except Exception as exc:  # 補人出錯不能讓整個程式倒下：記下來，這一輪照樣讓在線的假人做事
            log_failure(exc)
            report.failed += 1
        season = self.world.get_season_number()
        battle = self._battle_sides()  # 決戰與攻城戰（領地爭奪第二批）每一場一筆
        owes = self._battle_owes()
        for state in self.characters.all(bots_only=True):
            profile = state.player.bot
            if profile is None or not server_bots.active(profile, season):
                continue
            if not self._online(profile, state, now, battle):
                continue
            report.online += 1
            # 決戰的回合正在等這個假人：這一輪一定讓他出手，不照平常的步調擲骰。
            # 平常每個在線假人一輪只有 act_chance（20÷60～20÷180，約 0.18）的機率動一下，七個在線假人每 20 秒
            # 總共才動一個；而回合要名單上每個還在場的人都送出才結算（battle_instance.round_is_complete），
            # 所以回合實務上一定拖到 round_seconds（300 秒）逾時才由 fill_timed_out_actions 代選。真人看到的是
            # 「大家都選完了卻還要等滿五分鐘」（joy 2026-10-13；10-08 那場五個回合全部剛好 300 秒也是這個原因）。
            # 招式照舊由 bot_policy 挑（設計：伺服器假人是一般參戰者，不走 battle_instance.bot_choose_action）。
            owes_round = state.player.name in owes
            if not owes_round and self.rng.random() >= server_bots.act_chance(profile, self.content.config):
                continue
            slot = bot_policy.NamingSlot(open=self._naming_open())
            try:
                with self.world.action_lock(timeout=LOCK_WAIT):
                    # 拿到寫入權之後才看錶：上一個假人做完到現在，真人可能已經把共用時鐘對到更晚了
                    acted = self._take_turn(state.player.name, self.clock(), slot)
                if acted:
                    report.acted += 1
                report.naming_skipped += slot.skipped
                if slot.job is not None:  # 這個假人有一件要取名的：放掉鎖之後在鎖外做完，才換下一個假人（一次一件）
                    self._name_and_apply(state.player.name, slot.job, report)
            except TimeoutError:
                report.skipped += 1
            except Exception as exc:
                log_failure(exc)
                report.failed += 1
        return report

    def battle_tick(self) -> TickReport:
        """決戰回合裡，在場還沒出招的假人第一時間出招（Joy 2026-10-13：「機器人是不是都不會第一時間選擇行動，這樣很拖時間」）。
        平常的 tick 隔 bot_tick_seconds 才巡一輪、在線的假人還要擲 act_chance，回合常常等到逾時；run_bots 在決戰開打時
        每 BATTLE_TICK_SECONDS 叫這裡一次。還沒出招的假人等回合開了 BATTLE_DELAY 那幾秒（每個假人每回合擲一次）才出手；
        場上沒在掛機的真人都送出了就不再等，馬上出手，回合不必等逾時。只出決戰的招（bot_policy.battle_move），別的事照舊歸 tick。"""
        report = TickReport()
        if self.world.season_phase() != "running" or self.world.paused_at() is not None:
            return report
        battles = [b for b in self._battles() if b.phase == "active" and b.battle_id in self.content.battles]
        if not battles:
            return report
        bots = {state.player.name: state.player.bot for state in self.characters.all(bots_only=True)}
        now = self.clock()
        for battle in battles:  # 決戰與攻城戰（領地爭奪第二批）各自看這一回合在等誰
            present = [p for p in battle.participants.values() if not p.eliminated and not p.away]
            pending = [p for p in present if p.name not in battle.round.pending_actions]
            humans_done = not any(p.name not in bots and not p.is_bot and not battle_instance.idle(p) for p in pending)
            for p in pending:
                profile = bots.get(p.name)
                if profile is None:
                    continue
                delay = random.Random(f"{profile.seed}|{battle.battle_id}|{battle.round_number}|{battle.round.opened_real}").uniform(*BATTLE_DELAY)
                if not humans_done and now - battle.round.opened_real < delay:
                    continue
                report.online += 1
                try:
                    with self.world.action_lock(timeout=LOCK_WAIT):
                        if self._battle_turn(p.name, self.clock()):
                            report.acted += 1
                except TimeoutError:
                    report.skipped += 1
                except Exception as exc:
                    log_failure(exc)
                    report.failed += 1
        return report

    def _battles(self) -> list[battle_instance.BattleInstance]:
        """全服此刻的每一場：決戰那一格加上攻城戰（領地爭奪第二批；沒開時是空的），一次讀完。"""
        shared = self.world.read()
        return ([shared.active_battle] if shared.active_battle is not None else []) + list(shared.sieges)

    def _battle_turn(self, name: str, now: float) -> bool:
        """在寫入交易裡替一個假人出決戰的一招（battle_tick）；季不在跑、暫停中、不是這一季的假人就什麼都不做。"""
        state = self.characters.load(name)
        shared = self.world.read()
        if state is None or shared.season_phase() != "running" or shared.paused_at is not None:
            return False
        profile = state.player.bot
        if profile is None or not server_bots.active(profile, shared.season_number):
            return False
        game = self._bot_game(state)
        game.sync(now)
        game.state.player.seen_real = now
        game.own_turn_checks()  # 假人自己那一輪：系統通緝照樣掛（名聲 4.6、5.4；跟真人一樣，看不出誰是假人）
        if game.state.world.ended:
            self.characters.save(game.state)
            return False
        acted = bool(bot_policy.battle_move(game, profile, self.rng))
        self.characters.save(game.state)
        return acted

    def battle_on(self) -> bool:
        """有一場決戰（或攻城戰）正在開打（run_bots 照它決定要不要每 BATTLE_TICK_SECONDS 叫 battle_tick）。"""
        return any(b.phase == "active" for b in self._battles())

    def _naming_open(self) -> bool:
        """這一輪輪不輪得到請模型取名：有 client、設定開著、離上一次夠久（一次一件，PM 10/5）。"""
        cfg = self.content.config
        if self.client is None or not cfg.bot_naming:
            return False
        return self.last_naming is None or self.clock() - self.last_naming >= cfg.bot_naming_gap_seconds

    def _bot_game(self, state: GameState) -> Game:
        """假人這一次拿鎖用的 Game：不接 LLM（鎖內一個模型都不叫，伺服器假人設計第三節），鎖內模型額度歸零（同 server._locked）。"""
        game = Game(self.content, state, self.rng, self.world)
        game.client = None
        game.reset_model_budget()
        game.odds_memo = self.odds_memo
        return game

    def _take_turn(self, name: str, now: float, slot: bot_policy.NamingSlot | None = None) -> bool:
        """在寫入交易裡做一個動作，真的出手才回傳 True。這一輪開頭查過的賽季可能已經變了（各個假人之間
        會結束交易）：季已經結束、或管理者開了下一季（這個假人就算退隱了），就什麼都不做、也不存檔；
        自己補算時間時走到季末，存下補算的結果，但不在休季時做事。
        slot 是這一輪的取名名額：要取名的爐或定名開成單子放進 slot.job，由呼叫端在鎖外做完（見 _name_and_apply）。"""
        state = self.characters.load(name)
        shared = self.world.read()
        if state is None or shared.season_phase() != "running" or shared.paused_at is not None:
            return False
        profile = state.player.bot
        if profile is None or not server_bots.active(profile, shared.season_number):
            return False
        game = self._bot_game(state)
        game.sync(now)
        game.state.player.seen_real = now  # 假人自己上線（隱沒看它）；不設 own_request：假人在奪璽單挑裡永遠不在場（14.1）
        game.own_turn_checks()  # 假人自己那一輪：系統通緝照樣掛（名聲 4.6、5.4）
        if game.state.world.ended:
            self.characters.save(game.state)
            return False
        bot_policy.take_turn(game, game.state.player.bot, self.rng, slot)
        self.characters.save(game.state)
        return True

    def _name_and_apply(
        self, name: str, job: bot_policy.ForgeJob | bot_policy.MasterJob | bot_policy.SenseJob | bot_policy.DiscussJob,
        report: TickReport,
    ) -> None:
        """假人取名的 B、C 段：首創配方（企劃者 2026-10-05）與絕學定名（2026-10-06）都請模型取，不然名字是字表的樣子、
        或江湖史同一個名字出現兩次，看得出是假人。B 在行動鎖外請模型取名或挑一個（這個迴圈一個一個來，所以同時只有一件）；
        C 再拿鎖、重讀角色、交給 bot_policy.apply_job 重驗再套用。拿不到鎖就放掉這一件（名字丟掉：首創的話之後誰先合到誰取名，
        定名的話下次再來）。
        模型沒取到名字（連不上、逾時、取壞了）：首創的爐不開（C 段不做、不收費）——走字表名字搶下首創就是看得出是假人的樣子；
        下一次要等 bot_naming_gap_seconds 之後。挑一個的單（有候選）沒挑到照常進 C 段，由規則挑，不產生新名字；
        絕學定名照常進 C 段，用字表另組一個跟原名不同的（見 bot_policy.apply_job）。"""
        cfg = self.content.config
        self.last_naming = self.clock()
        if isinstance(job, bot_policy.SenseJob):  # 有所感：只看文字特徵（假人的筆畫是現成的那幾筆，不送圖）
            got = insight_llm.name(
                self.client, self.content, job.request.facts, budget=cfg.bot_naming_budget_seconds,
                person=self.world.is_character_name,
            )
            proposed = (got[0], got[1])
        else:
            proposed = naming.generate(
                self.client, self.content, job.request, budget=cfg.bot_naming_budget_seconds,
                person=self.world.is_character_name,
            )
        report.named += 1
        if isinstance(job, (bot_policy.ForgeJob, bot_policy.DiscussJob)) and proposed[0] is None and not job.request.choices:
            return
        try:
            with self.world.action_lock(timeout=LOCK_WAIT):
                state = self.characters.load(name)
                shared = self.world.read()
                # 暫停中不做事（跟 tick、_take_turn 一樣；取名的時候管理者可能按了暫停）：名字丟掉，繼續之後再取
                if state is None or shared.season_phase() != "running" or shared.paused_at is not None:
                    return
                profile = state.player.bot
                if profile is None or not server_bots.active(profile, shared.season_number):
                    return
                game = self._bot_game(state)
                game.sync(self.clock())
                if not game.state.world.ended:
                    bot_policy.apply_job(game, job, proposed)
                self.characters.save(game.state)
        except TimeoutError:
            report.skipped += 1

    def _online(
        self, profile: BotProfile, state: GameState, now: float,
        battles: list[tuple[float, set[str], set[str]]],
    ) -> bool:
        """照作息在線；或者自己的陣營正在打全服戰鬥（或攻城戰），而這個假人擲中了趕來參戰，且還沒出局
        （趕來的假人在線到戰鬥結束或自己出局，設計第六節）。每一場各擲一次（識別值是那一場的集結截止時間）。"""
        if server_bots.is_online(profile, now):
            return True
        return any(
            state.player.faction in sides and state.player.name not in out and server_bots.attends_battle(profile, key)
            for key, sides, out in battles
        )

    def _battle_owes(self) -> frozenset[str]:
        """進行中的全服戰鬥這一回合還在等誰出手：還在場（沒出局、沒離開大區）而且還沒送出行動的參戰者名號。
        集結中、已經收場、沒有戰鬥時是空的。只用來決定「這一輪要不要讓這個假人動」，不改任何狀態。決戰與攻城戰（領地爭奪第二批）都算。"""
        return frozenset(
            p.name for battle in self._battles() if battle.phase == "active" for p in battle.participants.values()
            if not p.eliminated and not p.away and p.name not in battle.round.pending_actions
        )

    def _battle_sides(self) -> list[tuple[float, set[str], set[str]]]:
        """進行中的每一場（決戰、攻城戰）：（這場的識別值＝集結截止時間, 會趕來的陣營, 已經出局的參戰者名號）；沒有是空的。"""
        rows = []
        for battle in self._battles():
            if battle.phase == "ended":
                continue
            definition = self.content.battles.get(battle.battle_id)
            if definition is None:
                continue
            out = {p.name for p in battle.participants.values() if p.eliminated}
            if battle.siege is not None:
                # 攻城戰（領地爭奪第二批）：攻方、佔著的那一方，加上要依附別人的陣營（豪強分屬兩軍的季依附那一軍，到了照 rally_region 判）；
                # 另一軍站不進守將那一格（裁決 8），不趕來
                sides = set(battle.siege.attackers) | ({battle.siege.holder} if battle.siege.holder else set())
                sides |= {f.id for f in self.content.scenario.factions if f.allies}
            else:
                # 會趕來的陣營：兩軍，加上劇本其他的陣營（豪強的假人也擲趕來，到了臨時投效人少的一軍，bot.enlist_pick；豪強分屬兩軍的季
                # 站依附的那一軍，Game._free_agent）；散人不趕來
                sides = set(battle_instance.sides(definition)) | {f.id for f in self.content.scenario.factions}
            rows.append((battle.muster_deadline_real, sides, out))
        return rows

    def _fill(self, now: float, report: TickReport) -> None:
        """補人；補成一個就記一個進 report.added（中途出錯時，已經補成的仍算數）。
        tick 開頭看過暫停了，但等這把行動鎖的時候管理者的暫停可能先寫進去：拿到鎖之後再看一次，暫停中不補人。"""
        if self.world.read().paused_at is not None:  # 欄位，不是方法（world.paused_at() 才是方法）
            return
        self._wake_seal_bots(now, report)
        cfg = self.content.config
        season = self.world.get_season_number()
        bots = self.characters.all(bots_only=True)
        counts = self.world.faction_counts()
        for state in bots:  # 已派去、還在路上沒投靠的假人也算，免得同一個缺額一直重複補
            bot = state.player.bot
            if bot is not None and server_bots.active(bot, season) and state.player.faction is None:
                counts[bot.faction] = counts.get(bot.faction, 0) + 1
        for faction in self.content.scenario.factions:
            if counts.get(faction.id, 0) >= cfg.bots_min_per_faction:
                continue
            last = self.last_added.get(faction.id)
            if last is not None and now - last < cfg.bot_fill_seconds:
                continue
            bots = self._add_bot(faction.id, season, bots, now)
            self.last_added[faction.id] = now
            report.added += 1

    def _wake_seal_bots(self, now: float, report: TickReport) -> None:
        """每季開季後第一次補人：持碎片、退隱的假人各擲一次回不回來（Config.seal.bot_return_chance），不看缺額——缺額不出現就不會叫
        _add_bot，退隱的持碎片假人永遠不會被叫醒、必然隱沒，看得出是假人（7.6）。回來的派到名冊人數最少的陣營。
        種子照密鹽、季別與名號（重開假人程式也是同一個結果），不用 self.rng。"""
        if not seal.on(self.content):
            return
        view = self.world.seal_state()
        if self.seal_season == view.season:
            return
        self.seal_season = view.season
        holders = seal.holders(view.registry)
        bots = self.characters.all(bots_only=True)
        for state in list(bots):
            profile = state.player.bot
            if profile is None or server_bots.active(profile, view.season) or seal.key(state.player.name) not in holders:
                continue
            if random.Random(f"{view.registry.salt}|{view.season}|seal-return|{state.player.name}").random() >= self.content.config.seal.bot_return_chance:
                continue
            counts = self.world.faction_counts()
            faction = min(self.content.scenario.factions, key=lambda f: (counts.get(f.id, 0), f.id))
            bots = self._add_bot(faction.id, view.season, bots, now, state=state)
            report.added += 1

    def _female_share(self) -> float:
        """真人裡選了女的比例（建角色或設定頁選過的才算）；選過的真人不到 FEMALE_SAMPLE 個時用 gender.BOT_FEMALE_SHARE。
        假人跟著真人的比例走，才看不出誰是假人（伺服器假人設計）。"""
        chosen = [st.player for st in self.characters.all() if st.player.bot is None and st.player.gender_chosen]
        if len(chosen) < FEMALE_SAMPLE:
            return gender.BOT_FEMALE_SHARE
        return sum(gender.female(p) for p in chosen) / len(chosen)

    def _add_bot(
        self, faction_id: str, season: int, bots: list[GameState], now: float, state: GameState | None = None,
    ) -> list[GameState]:
        """先叫醒一位退隱的假人（沿用名號，像老玩家回鍋），沒有才新建一位；回傳更新後的假人清單。
        給了 state 就叫醒那一位（持碎片的退隱假人，_wake_seal_bots）。"""
        retired = [s for s in bots if s.player.bot is not None and not server_bots.active(s.player.bot, season)]
        if state is not None:
            game = Game(self.content, state, self.rng, self.world)
        elif retired:
            game = Game(self.content, self.rng.choice(retired), self.rng, self.world)
        else:
            # 名號不能撞到任何一個角色，包括讀不出來（損毀、舊格式）的存檔——不然新假人會把它蓋掉
            taken = self.characters.names() | server_bots.reserved_names(self.content)
            name = server_bots.make_name(self.rng, taken)
            # graduated：內容有序章時，新假人離開起點的樣子跟走完草廬的真人一樣（Game._graduate）；沒有序章什麼都不變
            game = Game.new(self.content, name, rng=self.rng, world=self.world, graduated=True)
            game.state.player.bot = BotProfile(
                personality=server_bots.pick_personality(self.rng), seed=self.rng.randrange(2**31),
            )
            # 性別建立時就定好（PM 2026-10-12）：照真人選的比例、照名號雜湊擲（不動 self.rng，後面的擲骰不位移）；
            # 跟建角色時選過的真人一樣記成選過了，設定頁不會冒出「選一次」
            game.state.player.gender = gender.for_bot(name, self._female_share())
            game.state.player.gender_chosen = True
        game.client = None
        bot = game.state.player.bot
        bot.faction, bot.season_number = faction_id, season
        game.sync(now)
        game.state.player.seen_real = now  # 假人自己上線（隱沒看它）；不設 own_request：假人在奪璽單挑裡永遠不在場（14.1）
        self.characters.save(game.state)
        name = game.state.player.name
        return [s for s in bots if s.player.name != name] + [game.state]
