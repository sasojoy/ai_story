"""伺服器假人程式的核心（伺服器假人設計第三、四、六節）：一輪一輪地補人、讓在線的假人做事。

run_bots.py 只負責每隔 bot_tick_seconds 呼叫一次 tick()。每個假人做一個動作都跟真人按一次
按鈕一樣：開一筆寫入交易 → 讀角色 → 補算時間 → 做動作 → 存角色 → 交易結束。拿不到寫入權（真人正在
等 LLM）就跳過這個假人的這一輪，不卡住真人。

補人：每個陣營（投靠名冊上的真人與假人，加上這一季已派去、還在路上的假人）不到最少人數，就補
一個——先叫醒退隱的假人（沿用名號），沒有才新建；同一個陣營每 bot_fill_seconds 最多補一個。
換季時所有假人自動算退隱（BotProfile.season_number 對不上），新的一季再照缺額叫醒。
"""
from __future__ import annotations

import logging
import random
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass

from . import bot_policy, server_bots
from .characters import CharacterStore, open_characters
from .engine import Game
from .models import Content
from .sqlite_world import open_world
from .state import BotProfile, GameState
from .world_state import WorldStateStore

LOCK_WAIT = 2.0  # 假人等行動鎖最多幾秒；等不到就跳過這一輪

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


class BotRunner:
    def __init__(
        self, content: Content, world: WorldStateStore | None = None, characters: CharacterStore | None = None,
        rng: random.Random | None = None, clock: Callable[[], float] = time.time,
    ):
        self.content = content
        self.world = world or open_world()
        self.characters = characters or open_characters()
        self.rng = rng or random.Random()
        self.clock = clock
        self.last_added: dict[str, float] = {}  # 陣營 id -> 上次補人的現實時間

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
        battle = self._battle_sides()
        for state in self.characters.all(bots_only=True):
            profile = state.player.bot
            if profile is None or not server_bots.active(profile, season):
                continue
            if not self._online(profile, state, now, battle):
                continue
            report.online += 1
            if self.rng.random() >= server_bots.act_chance(profile, self.content.config):
                continue
            try:
                with self.world.action_lock(timeout=LOCK_WAIT):
                    # 拿到寫入權之後才看錶：上一個假人做完到現在，真人可能已經把共用時鐘對到更晚了
                    acted = self._take_turn(state.player.name, self.clock())
                if acted:
                    report.acted += 1
            except TimeoutError:
                report.skipped += 1
            except Exception as exc:
                log_failure(exc)
                report.failed += 1
        return report

    def _take_turn(self, name: str, now: float) -> bool:
        """在寫入交易裡做一個動作，真的出手才回傳 True。這一輪開頭查過的賽季可能已經變了（各個假人之間
        會結束交易）：季已經結束、或管理者開了下一季（這個假人就算退隱了），就什麼都不做、也不存檔；
        自己補算時間時走到季末，存下補算的結果，但不在休季時做事。"""
        state = self.characters.load(name)
        shared = self.world.read()
        if state is None or shared.season_phase() != "running" or shared.paused_at is not None:
            return False
        profile = state.player.bot
        if profile is None or not server_bots.active(profile, shared.season_number):
            return False
        game = Game(self.content, state, self.rng, self.world)
        game.client = None  # 假人不呼叫 LLM（伺服器假人設計第三節）
        game.sync(now)
        if game.state.world.ended:
            self.characters.save(game.state)
            return False
        bot_policy.take_turn(game, game.state.player.bot, self.rng)
        self.characters.save(game.state)
        return True

    def _online(
        self, profile: BotProfile, state: GameState, now: float,
        battle: tuple[float, set[str], set[str]] | None,
    ) -> bool:
        """照作息在線；或者自己的陣營正在打全服戰鬥，而這個假人擲中了趕來參戰，且還沒出局
        （趕來的假人在線到戰鬥結束或自己出局，設計第六節）。"""
        if server_bots.is_online(profile, now):
            return True
        if battle is None:
            return False
        key, sides, out = battle
        return (
            state.player.faction in sides and state.player.name not in out
            and server_bots.attends_battle(profile, key)
        )

    def _battle_sides(self) -> tuple[float, set[str], set[str]] | None:
        """進行中的全服戰鬥：（這場的識別值＝集結截止時間, 交戰陣營, 已經出局的參戰者名號）；
        沒有或已經結束回傳 None。"""
        battle = self.world.get_battle()
        if battle is None or battle.phase == "ended":
            return None
        definition = self.content.battles.get(battle.battle_id)
        if definition is None:
            return None
        out = {p.name for p in battle.participants.values() if p.eliminated}
        return battle.muster_deadline_real, {f.id for f in definition.factions}, out

    def _fill(self, now: float, report: TickReport) -> None:
        """補人；補成一個就記一個進 report.added（中途出錯時，已經補成的仍算數）。"""
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

    def _add_bot(self, faction_id: str, season: int, bots: list[GameState], now: float) -> list[GameState]:
        """先叫醒一位退隱的假人（沿用名號，像老玩家回鍋），沒有才新建一位；回傳更新後的假人清單。"""
        retired = [s for s in bots if s.player.bot is not None and not server_bots.active(s.player.bot, season)]
        if retired:
            game = Game(self.content, self.rng.choice(retired), self.rng, self.world)
        else:
            # 名號不能撞到任何一個角色，包括讀不出來（損毀、舊格式）的存檔——不然新假人會把它蓋掉
            taken = self.characters.names() | server_bots.reserved_names(self.content)
            name = server_bots.make_name(self.rng, taken)
            game = Game.new(self.content, name, rng=self.rng, world=self.world)
            game.state.player.bot = BotProfile(
                personality=server_bots.pick_personality(self.rng), seed=self.rng.randrange(2**31),
            )
        game.client = None
        bot = game.state.player.bot
        bot.faction, bot.season_number = faction_id, season
        game.sync(now)
        self.characters.save(game.state)
        name = game.state.player.name
        return [s for s in bots if s.player.name != name] + [game.state]
