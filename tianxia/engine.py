"""遊戲門面：介面層唯一需要呼叫的類別。負責行動、選項、時間流逝與畫面文字。

sanguo-companions 合併大幅重寫：拿掉 battle.py 的 3v3 全自動戰鬥、多隊派遣、招賢抽卡、
收徒系統，改成單次判定遭遇（encounter.py）、單一隊伍（最多 4 位同伴）、唯一同伴的
招募（roster.py）、練功（team.py：鍛鍊；開局送兩門基礎武學，自創武學已作廢）。
"""
from __future__ import annotations

import contextlib
import functools
import hashlib
import math
import random
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from . import (
    atlas, battle_instance, battlelog, calendar, companion_agent, cultivation, defection, encounter, enlist, event_llm, fight_llm,
    figures, flavor, foreshadow, front_lines, fusion, insights, journal, library, martial_arts, materials, naming, opportunities, orders,
    push, rank_actions, ranks, roster, rounds, seats, sensing, skillview, styles, team, timetable, traits,
)
from . import events as event_rules  # note_round 走模組屬性（測試要能換掉它，確認只有 _present 會叫）
from . import hints as hint_rules  # 碰到才說（新手引導計畫三）；叫 hint_rules：這個檔裡有幾處區域變數也叫 hints
from . import prologue as prologue_rules  # Game.new 有個參數也叫 prologue，所以模組在這裡一律叫 prologue_rules
from . import rumor_view  # 傳聞分層的畫面：見聞頁的四層、你不在的時候（計畫 2026-10-06 傳聞分層一）
from .events import (
    choice_label, event_candidates, free_text_note, has_events_here, pick_event, stamina_note, visible_choices,
)
from .guide import HutReward, base_step_count, note_action, pending_line, quest_text, step_text, tutorial_active, tutorial_intro
from .guide import speaker_of as guide_speaker_of
from .guide import speakers as guide_speakers
from .guide import steps as tutorial_steps
from .journal import LOG_BREAK, Draft
from .mapview import legend_data, render_map, render_minimap
from .martial_arts import QUALITIES, is_renamed
from .models import (
    EXPLORE_BRANCHES, FREE_TEXT_MAX, MOVES, BattleDef, Check, Choice, Content, Effect, Event, ExploreBranch, FactionDef, Location,
    RoadKind, Squad, Threshold, TimetableEvent, TravelMode, TutorialStep, WorldEvent,
)
from .ollama_client import ModelBudget, OllamaClient, quick_client
from .rules import (
    GEJU, HUANGJIN, add_marks, add_rumor, apply_effect, audible, audience_bar, can_meet, change_trend, check_result_line, current_day,
    ears_of, failed, fill_marks, free_text_rate, here_regions,
    can_draw_side_change, chaos_fronts, chaos_note, front_chip, front_ids, front_of, front_text, humanize, in_chaos,
    is_revealed, pushable, rate_words, recompute_trends, resolve_goals, resolve_trend, resolve_trends, roll_check,
    season_one, season_one_off, stance_rule_note, stance_sum_note, stances, trend_name, trend_shown, trend_value,
    world_trend_value,
)
from .sqlite_world import open_world
from .state import (
    ONBOARDING_VERSION, PLAYER, BattleRecord, Convoy, GameState, HintNote, JournalEntry, Journey, Rumor, WorldState, new_game_state,
)
from .world import (
    _season_vehicle, advance_world_state, check_thresholds, end_season, fire_by_id, open_showdown, open_waiting_showdown,
    resume_season_clock, settle_season_start, showdown_battle, showdown_key, start_pending_battle,
)
from .world_state import WorldStateStore, season_length_days

HOUR = 3600
DAY = 86400
BULLETIN_MAX = 3  # 江湖頁那排小標「大事」點開的面板最多放這一週的幾則大事（計畫 T2；以前是公告卡）
AUDIENCE_HALL_FIGURES = 2  # 一個地點有幾位以上的大勢人物，交友就不直接找人、改按「求見」指名（企劃者 2026-10-03 決定）
OFF_FRONT_NOTE = "沒在戰線上領兵，不受挑戰"  # 戰線空著的人物（董卓、趙弘、重挫退下的人）：挑戰按鈕寫這一句（PM 2026-10-05 定）
SNUB_NOTE = "剛吃了敗仗，閉門不見"  # 挑戰本人打贏之後，他對打贏的人關上門（軍令文件 4.5）：求見、交友、挑戰的按鈕寫這一句
# 路上小事（路上設計第四節）：road:<id> → (名稱, 這一段做過之後寫的「這段路已經……」)；按鈕上的補充見 _road_task_options
ROAD_TASKS: dict[str, tuple[str, str]] = {
    "think": ("邊走邊想", "想過了"),
    "ask": ("沿途打聽", "打聽過了"),
    "survey": ("留意地形", "留意過了"),
    "gather": ("路邊採集", "找過了"),
}
ROAD_REWARD_TASKS = ("think", "gather")  # 有經濟收穫、受每天上限管的路上小事（Config.road_reward_daily_cap）


class Option(BaseModel):
    id: str
    label: str
    enabled: bool = True
    wait: str = ""  # 按下去要等模型時，按鈕上換上的字（大場面「兩人對峙……」，武學與成長設計 8.3）；不必等是空的
    confirm: str = ""  # 按下去之前先問一次的話（FB-095：必敗的遊歷）；網頁照它跳確認層，空的直接送


@dataclass(frozen=True)
class TollFacts:
    """寫功效演出句要知道的氣血的事（_take_toll 與劇情戰量好、_play_rounds 讀；武學與成長設計 13.6：只在功效真的改到結果時才演）。"""

    wounded: bool = False  # 開打前氣血就低於上限（厚才有用：它把氣血係數的下限拉高，滿血時沒有東西可拉；內傷讓「滿血」的上蓋低於上限，也算）
    low_hp: bool = False  # 開打前氣血低到「見底」（剩 LOW_HP_RATIO 以下，含）：厚那句「氣血見底」才挑得到
    healed: tuple[str, ...] = ()  # 真的回了血（有一行「氣血 +N」）的功效掛點：win_heal（吸取）、heal_after（回春）；劇情戰不回血
    # 下面三個是功效演出句後面括號裡的數字（FB-084）：跟戰報上的「氣血 -N」「氣血 +N」「內傷 +N」是同一批算的
    saved: int = 0  # 化勁這一場少扣的氣血（team.toll_saved）
    spared: int = 0  # 不動這一場免掉的內傷（team.toll_saved）
    gained: tuple[tuple[str, int], ...] = ()  # 回血的功效掛點 → 回了多少氣血（「氣血 +N」那一行的 N），順序同 healed


def _rank_action_id(arg: str) -> str | None:
    """選項 act:rank:<id> 去掉 act: 之後的那一段（_act、_action_title 收到的 arg）：是第 3、4 階的行動就回行動 id，不是回 None。
    前綴只在 RANK_ACTION_PREFIX 寫一次。"""
    head = RANK_ACTION_PREFIX.partition(":")[2]
    return arg.removeprefix(head) if arg.startswith(head) else None


def _points(lines: list[str]) -> int:
    """heal_fraction 回的「氣血 +N」那一行的 N：功效演出句的括號（FB-084）寫的跟戰報上那一行是同一個數，不另外算一份。"""
    return next((int(m.removeprefix("氣血 +")) for m in lines if m.startswith("氣血 +")), 0)


LOW_HP_RATIO = 0.3  # 開打前氣血剩上限的三成以下（含）算「氣血見底」：厚的那一句「氣血見底，……硬撐」（battlelog.LOW_HP_MARKS）才挑得到

RANK_ACTION_PREFIX = "act:rank:"  # 第 3、4 階行動的選項 id 前綴（act:rank:<行動 id>，正式版戊一）；models.ALLOW_FAMILIES 也列它，原始碼裡要真的有
FREE_TEXT_OPTION = "choice:free"  # 事件的「隨口應對」：按下去只是叫出輸入框，真正送出走 free_text_request／answer_event
# 必敗的遊歷按下去先問一次（FB-095；待 joy 潤）：「一成銀兩」跟 _lose_silver 的 silver // 10 是同一件事
TRAIN_CONFIRM = "這裡的對手你現在打不過。輸了要掉氣血、受內傷，還要丟一成銀兩。還是要打？"
BIG_FIGHT_WAIT = "兩人對峙……"  # 大場面按下去、等模型判讀時按鈕上的字（武學與成長設計 8.3）
# 賽季時鐘暫停（線上架構設計第四節、8.3）：選單上那一顆灰的，伺服器擋動作也回這一句（server._refuse_while_paused）。待 S1／joy 潤
PAUSED_TEXT = "賽季暫停中（停機維護）：這段時間不能行動，畫面照常可看"
PAUSE_LINE = (  # 待 S1／joy 潤
    "賽季時鐘停了：季的時間不走、決戰不推，全服暫時不能行動，畫面照常可看；"
    "排好的決戰繼續之後照原本的時間開。做完記得按「繼續」。"
)
RESUME_LINE = (  # 待 S1／joy 潤；{skip} 是實際扣了多少（world.resume_skip_text：停不到一個季曆鐘頭就說不另外扣）
    "賽季時鐘接著走了（停了 {minutes} 分鐘）：{skip}；"
    "排好的決戰照原本的時間開，時間在暫停裡過了的現在就開始集結。"
)
PAUSED_REFUSAL = "（賽季時鐘暫停中，先按「繼續」。）"  # 暫停中的管理者動作；待 S1／joy 潤
# 等模型判讀的時候選項沒了（另一個分頁把人帶走、事件被了結、體力花光）：這一仗不打，回這一句話代替一句看不出所以然的「無法這麼做」
FIGHT_LEFT = "你離開了，這一仗沒打成。"
FIGHT_CHANGED = "情勢變了，這一仗沒打成。"
FIGHT_GONE_LINES = (FIGHT_LEFT, FIGHT_CHANGED)
# 賽季籌備中（管理者還沒開季）：選單上那一顆灰的、安排前往被擋的原因寫 PREPARING_TEXT；動作被擋回一句 PREPARING_REFUSAL
PREPARING_TEXT = "賽季籌備中，等待管理者開季"
PREPARING_REFUSAL = f"（{PREPARING_TEXT}。）"
# 測試期間一鍵補滿體力（Config.beta_free_refill，企劃者 2026-10-07）。以下四句與鈕上的字（Config.beta_free_refill_label）全是新寫的，待 joy 潤：
REFILL_TITLE = "補滿體力"  # 江湖紀錄那一則的標題（joy 的丹是「服下回體丹」）
REFILL_LINE = "你運了口氣，體力回滿了。"  # 補滿成功時寫進紀錄的那一句
REFILL_FULL = "體力是滿的，用不著補。"  # 體力本來就是滿的：跟丹的「這時候服丹是糟蹋」一樣，只回一句話、不寫紀錄
REFILL_HUT = "草廬裡先照師父說的做，體力等出了草廬再補。"  # 序章裡不能補（序章的體力是照步驟算好的），跟丹的「出了草廬再吃」同一個道理


def _not_while_preparing(action: Callable) -> Callable:
    """Game 的動作：籌備中什麼都不能做，只回一句 PREPARING_REFUSAL（照一般的拒絕寫進紀錄，_log）；不然照常做。"""
    @functools.wraps(action)
    def guarded(self: Game, *args, **kwargs):
        if self._preparing():
            return self._log([PREPARING_REFUSAL])
        return action(self, *args, **kwargs)

    return guarded


class FreeTextRequest(BaseModel):
    """隨口應對鎖外評估的單子（server.py 的 A 段拿到、B 段送模型、C 段交回 answer_event 重驗）。"""
    event_id: str
    text: str


class FreeTextOutcome(BaseModel):
    """擲完骰的結果：server.py 拿它在鎖外請模型潤色，再交回 add_gamble_narration 插進那一則江湖紀錄。"""
    event_id: str
    text: str
    success: bool
    effect_text: str
    time: float  # 那一則紀錄的遊戲時間與標題，插潤色前用來認是不是同一則
    title: str


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
        self.client = OllamaClient.from_config(cfg)  # companion_agent.py 用；連不上時那輪對話取消，這裡不用先健檢
        self._model_budget = ModelBudget()  # 鎖內的模型呼叫這一次拿鎖期間還有沒有額度（見 _quick_client）
        self._preparing_memo: list[bool] | None = None  # 一次畫面建構裡記住的「籌備中嗎」；None＝不在範圍裡（見 phase_memo）
        self._draft: Draft | None = None  # choose() 進行中那次行動的江湖紀錄草稿
        # choose() 進行中那次行動、鎖外先判讀好的大場面（重驗過的，見 _checked_fight）；打那一場時用掉（_judged）
        self._fight: fight_llm.PreparedFight | None = None
        self.last_gamble: FreeTextOutcome | None = None  # 上一次 answer_event 擲完骰的結果（server.py 拿去潤色）
        # 主畫面「走法」切換選的走法（步行／趕路／疾行），選單上的「前往」照它出發（見 _move_option）。只是畫面狀態：
        # 不在 GameState 裡、不進存檔。網頁伺服器的同一個角色只有一份 Game（各分頁共用、重新整理也還在），所以走法
        # 由頁面記著、每個請求帶上，server.py 在行動鎖裡逐次 set_move_mode（見 server.MOVE_MODE）；機器人與假人從不改它。
        self.move_mode: TravelMode = "walk"
        # 現在的現實時間（秒）：由 sync(now) 傳進來，引擎自己不讀電腦時鐘（線上架構設計第四節）。
        # 讀進來的存檔先用上次同步的時間；開戰的集結截止、回合逾時都看它。
        self.now: float = state.last_real if state.last_real is not None else 0.0
        self._drop_stale_references()

    def _quick_client(self) -> OllamaClient | None:
        """行動鎖裡叫模型用的 client：self.client 的複本，HTTP 逾時最多 Config.in_lock_model_timeout 秒（預設 15）、不重問
        （retry=False），所以鎖內任何一步模型呼叫最多佔住鎖那麼久。行動鎖拿著的時候全服玩家與假人都在等，模型慢或冷的時候
        照 ollama_timeout（120 秒）會凍住整台伺服器。所有在鎖內叫模型的地方都用它（大事與決戰回合的潤色、重複事件與重遊的
        點綴句、決戰自訂行動的評分、鎖內才備料的對話與記憶整理、鎖內才取名的開爐）；逾時或失敗各處本來就退回固定的文字。
        引擎不讀時鐘，上限靠 HTTP 的逾時（見 ollama_client.quick_client）。
        一次拿鎖期間只容忍一次失敗：有一次鎖內的模型呼叫逾時或失敗之後（_model_budget.gave_up），這裡回 None，同一次行動裡
        後面的鎖內呼叫都不叫模型、直接用固定文字。旗子由 server._locked 與 bot_runner._bot_game 每次拿到鎖先歸零（reset_model_budget）；
        直接用 Game 的測試與腳本（沒有鎖）自己決定什麼時候歸零。self.client 本身不動，鎖外的路徑（server.py 的對話備料、開爐取名、
        隨口應對的評分與潤色，都拿 game.client）照舊用它自己的逾時與重問。沒有 client（伺服器假人鎖內的 Game：bot_runner 把
        game.client 設成 None）就回 None，這些地方一個模型都不會叫。假人程式替首創配方與絕學定名取名是鎖外的另一條路：
        用 bot_runner 自己的 client 叫 naming.generate（_name_and_apply），不經過這裡。"""
        return quick_client(self.client, self.content.config.in_lock_model_timeout, self._model_budget)

    def reset_model_budget(self) -> None:
        """新的一次拿鎖：鎖內的模型呼叫重新有額度（見 _quick_client）。server._locked 與 bot_runner._bot_game 每次拿到行動鎖先呼叫。"""
        self._model_budget.gave_up = False

    @classmethod
    def new(
        cls, content: Content, name: str, rng: random.Random | None = None, world: WorldStateStore | None = None,
        prologue: bool = False, graduated: bool = False,
    ) -> Game:
        """prologue：走序章（新手引導計畫一）。只有網頁上建立角色（server.create_character）傳 True；假人、整季機器人、
        腳本與測試不傳，直接站在起點、序章算走過（沒有序章的內容兩種都一樣）。
        graduated：假人與整季機器人傳 True（bot_runner、bot.play_season）：不進草廬，但離開起點時的樣子要跟走完草廬的真人一樣
        （等級、一門師門功夫、盤纏、一點內傷：不然新人頭一個鐘頭就看得出誰是假人）——內容有序章才有作用，做法是把序章用真的
        行動走一遍（_graduate）。內容沒有序章（正式內容現在就是）什麼都不做，連亂數都不多用一次。"""
        game = cls(content, new_game_state(content, name), rng, world)
        if prologue:
            prologue_rules.begin(game.state, content)
        elif graduated and prologue_rules.has(content):
            game._graduate()
        else:
            # 第二季起建的角色，__init__ 的換季重來已經把新角色放進序章（體力也換成序章的）：這裡拉回起點、滿體力
            prologue_rules.finish(game.state, content, game.world, purse=False)
            if prologue_rules.has(content):
                game.state.player.stamina = float(content.config.stamina_max)
        p = game.state.player
        p.visited.add(p.location)
        if content.config.beta_gift:  # 內測贈送（企劃者 2026-10-07）：真人、假人、整季機器人建角色時一樣拿到
            p.stamina_pills += content.config.beta_gift_stamina_pills
        game._log(
            [f"══ {content.scenario.name} ══", content.scenario.intro, game.location_text()]
            + tutorial_intro(content)
        )
        if not game.state.journal:  # 第二季起建的角色：__init__ 的換季重來已經寫了開場那一則，不再寫一次（FB-052）
            game._write(content.scenario.name, [content.scenario.intro], tag=journal.SEASON_START, guide=tutorial_intro(content))
        return game

    GRADUATE_TRIES = 12  # _graduate 每一步最多試幾次；照著走卻一直前進不了（內容改版、賽季籌備中）就放棄、直接出師

    def _graduate(self) -> None:
        """假人與整季機器人的序章（Game.new(graduated=True)）：把草廬前面的步驟用真的行動走一遍（遇險、拜師、探索悟意境、
        合成、換上練到第三成、修練、打坐、雪恥、配點、熔雜學），最後一步「出師」跟略過一樣交給 prologue.finish(purse=True)
        （站到起點、盤纏、體力補滿）。每一步做什麼照那一步的完成條件（TutorialStep.done_when）與寫好的欄位走，選項與屬性
        用 self.rng 挑（四門師門功夫、擋或喊，種子決定）；等級、功夫的品質與成數、內傷、銀兩都是真的打出來、練出來的，所以
        永遠跟真人走完草廬一模一樣，不是另外抄一份清單。
        走不下去就放棄：某一步連試 GRADUATE_TRIES 次沒前進（內容改版讓這一步照著走不通、賽季還在籌備中什麼都不能做），
        直接 finish，等於一個略過序章的人；假人不會卡在草廬。
        不叫模型（師門配方有寫好的名字、雪恥的結果是寫好的，用不到；self.client 先收起來，結束還回去）；也不碰共用賽季
        的時鐘（序章裡的行動只推玩家自己的進度）。走序章留下的江湖紀錄、戰報、對話框都清掉，假人看起來跟沒走序章時一樣乾淨。"""
        t, s, p = self.content.tutorial, self.state, self.state.player
        prologue_rules.begin(s, self.content)
        client, self.client = self.client, None
        try:
            tries, last = 0, p.tutorial_step
            while prologue_rules.active(s, self.content) and p.tutorial_step < t.prologue_steps - 1:  # 出師那一步由 finish 給
                tries = tries + 1 if p.tutorial_step == last else 1
                last = p.tutorial_step
                if tries > self.GRADUATE_TRIES or not self._graduate_pass(t.steps[p.tutorial_step]):
                    break
        finally:
            self.client = client
        prologue_rules.finish(s, self.content, self.world, purse=True)
        s.journal, s.log, s.battles, s.battle_card = [], [], [], None
        p.guide_done, p.guide_outro = [], False

    def _graduate_pass(self, step: TutorialStep) -> bool:
        """序章裡照這一步的完成條件做一個行動；這一步沒有可以做的（不認得的條件）回 False。"""
        s, c, p = self.state, self.content, self.state.player
        goal = step.done_when
        if s.pending_event is not None:  # 事件擋著：挑一個走得到這一步旗標的選項（四景之類的，哪一個看種子）
            event = c.events[s.pending_event]
            needed = set(goal.condition.flags_all)
            options = [o for o in self.options(odds=False) if o.enabled and o.id.removeprefix("choice:").isdigit()]
            good = [
                o for o in options if needed <= prologue_rules.choice_flags(c, event.id, int(o.id.removeprefix("choice:")))
            ] or options
            if not good:
                return False
            self.choose(self.rng.choice(good).id)
            return True
        if p.sensing is not None:  # 草廬的有所感：做法都選得對；不畫，順其自然落回那個基本意境（假人不叫模型）
            if p.sensing.stage == "choose":
                self.choose(f"{sensing.PREFIX}{self.rng.randrange(len(sensing.current(s, c)[1].methods))}")
            else:
                self.choose(sensing.LET_GO)
            return True
        fused = prologue_rules.fused_arts(s, c, self.world)
        if goal.action == "view_tab":
            tab = next((flag.removeprefix("看過:") for flag in goal.condition.flags_all if flag.startswith("看過:")), "")
            self.view_tab(tab)
        elif step.explore_event is not None or step.explore_scene is not None:
            self.choose("act:explore")
        elif goal.fused:
            if not p.insights or step.fuse_base is None:
                return False
            self.forge(step.fuse_base, [self.rng.choice(p.insights)])
        elif goal.fused_level and fused:
            art = fused[0]
            if art.id not in (p.member.wugong_id, p.member.neigong_id):
                self.switch_art(art.id)
            else:
                self.practice(art.kind)
        elif goal.fused_quality and fused:
            self.cultivate(fused[0].id)
        elif goal.action in ("rest", "train", "explore"):
            self.choose(f"act:{goal.action}")
        elif goal.action == "allocate":
            open_stats = [k for k in team.COMBAT_STATS if p.stats.get(k, 0) < c.config.stat_cap]
            if not open_stats:
                return False
            self.allocate_stat(self.rng.choice(open_stats))
        elif goal.action == "melt" and step.melt_only:
            self.melt_art(step.melt_only)
        else:
            return False
        return True

    def _reconcile_season(self) -> None:
        """把 self.state.world 對齊到目前的共用賽季（設計文件「真正共享賽季」討論，取代
        原本每個玩家各自獨立的 WorldState）。全服第一次開局（還沒有任何共用賽季）在這裡
        種出第一季，預設停在籌備中等管理者開季；共用賽季已經換過一輪（不管是自己剛開下一季，
        還是連線期間別的玩家觸發的）時，幫這個玩家的角色也開新的一季——角色本身（等級/位置/隊伍）
        重新開始；跟同伴的關係現況/對話歷史是「我跟他的交情」，不是賽季道具，保留下來，
        好感度只帶一成（見 _reset_player_for_new_season）。__init__ 時（讀存檔／新角色）要呼叫，之後每次 sync() 也要呼叫，這樣連線
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
        流逝掉）跟幾項明確認定「跟賽季無關、是我自己的」的東西——跟同伴的對話歷史（整份保留，但記下這一季從第幾則
        開始，模型只看這一季的）；關係現況搬到 past_notes 當「上一季的交情」，這一季的從頭寫；好感度則只帶一成
        （Config.affinity_carry_ratio、無條件捨去，80→8、5→0：第一季設計第十四節，下一季最多從 10 起步，交情要重新經營）。
        新手引導：做完或略過的人照舊不再出現；還沒做完的人跟著新角色從起始步重來——
        新角色只剩開局那兩門第一成的基礎武學，接著上一季做到一半的下一步（例如出城遊歷）會把他推進
        打不過的路（FB-034）。入伍段（新手引導計畫二）同理：走完（或略過）的人帶到下一季、再投靠不重走；沒走完的下一季投靠時從頭走。
        碰到才說（計畫三）：說過的（hints_seen）與「不再提示」帶到下一季，排著還沒上框的不帶；引導走完（不是略過）的回鍋玩家開季多一句師父送行。
        world 欄位這裡不用管，呼叫端（_reconcile_season）緊接著就會把它指向共用賽季。
        之後新增的 PlayerState 欄位預設就跟著新角色重來；要跨季保留的才加進下面這份清單。"""
        old = self.state
        fresh = new_game_state(self.content, old.player.name)
        fresh.last_real = old.last_real
        # 做完或略過（skip_tutorial 也是設成步數）：看不分季的那幾步；第一季多的兩步排在後面，回鍋的人接著做（計畫 T6）。
        # 舊存檔先換算成新引導的步數（設計 7.2）
        step = prologue_rules.migrated_step(old.player, self.content)
        carried = step >= base_step_count(self.content)
        if carried:
            fresh.player.tutorial_step = step
            fresh.player.guide_skipped = old.player.guide_skipped  # 略過的人換季也不畫對話框（畫面批次審查 I4）
        elif prologue_rules.has(self.content):
            if step < self.content.tutorial.prologue_steps and not old.player.bot:
                prologue_rules.begin(fresh, self.content)  # 序章沒走完就換季：回草廬從第一步重來（Review Focus 5）
            else:
                # 序章走完了、後面的步驟還沒做完（或是假人、腳本）：從序章之後的起始步重來，不再回草廬
                fresh.player.tutorial_step = self.content.tutorial.prologue_steps
        if enlist.done(old, self.content):
            fresh.player.enlist_step = old.player.enlist_step  # 入伍段只走一次（設計 7.1）；沒走完的下一季投靠時從頭走
        # 碰到才說（新手引導計畫三）：說過的與「不再提示」的開關帶到下一季，排著還沒上框的不帶（沒說過，下一季碰到還會說）。
        # 引導走完的回鍋玩家，開季時師父送你下山一句（設計 7.1）；略過引導的人沒有要誰帶（控制者裁示），假人、關了提示的、內容沒寫的也不送
        fresh.player.hints_seen = set(old.player.hints_seen)
        fresh.player.hints_off = old.player.hints_off
        book = self.content.hints
        if carried and not old.player.guide_skipped and not old.player.bot and not old.player.hints_off and book.season_return:
            fresh.player.hint_queue = [HintNote(id="s_return", speaker=book.head, text=book.season_return)]
        ratio = self.content.config.affinity_carry_ratio
        fresh.player.affinities = {key: int(value * ratio) for key, value in old.player.affinities.items()}
        # 上一季的交情另外留著（這一季的關係從頭寫），好感度只剩一成時提示才不會說「親如兄弟」（正式版辛）；
        # 這一季沒聊過的人物留著更早的那一句
        fresh.player.past_notes = {**old.player.past_notes, **old.player.relationship_notes}
        fresh.player.dialogue_history = old.player.dialogue_history
        fresh.player.history_start = {cid: len(h) for cid, h in old.player.dialogue_history.items()}
        fresh.player.used_dialogue_options = old.player.used_dialogue_options
        fresh.player.turns_since_consolidation = old.player.turns_since_consolidation
        fresh.player.bot = old.player.bot  # 伺服器假人的身分與作息跨季保留
        fresh.player.stamina_pills = old.player.stamina_pills  # 回體丹是建角色時送的，換季不再送，剩下的帶著走
        fresh.player.battle_results_seen = old.player.battle_results_seen  # 補送過的決戰不再補一次（FB-027）
        fresh.player.season_number = season_number
        self.state = fresh
        self.state.world = self.world.get_season()  # 開場那一則記此刻的季時間（FB-052：以前記成新存檔的 0）
        self.state.player.visited.add(self.state.player.location)
        self._write(
            self.content.scenario.name, [self.content.scenario.intro], tag=journal.SEASON_START, guide=tutorial_intro(self.content),
        )

    def _drop_stale_references(self) -> None:
        """內容檔改版後，舊存檔可能引用已刪除的事件、地點、武學或人物；丟掉這些引用以免當機。"""
        # 入伍段上線之前就投靠了的老手蓋成走完（設計 7.2）：要在換季之前，換季會把陣營清掉、之後就認不出他是老手
        enlist.mark_veteran(self.state, self.content)
        self._reconcile_season()
        s, c = self.state, self.content
        p = s.player
        for key in team.COMBAT_STATS:  # 舊存檔沒有後來加的屬性（博聞，武學與成長設計 6.3）：照開局的數字補上
            p.stats.setdefault(key, c.config.start_stats.get(key, team.BASE_STAT))
        if s.pending_event and s.pending_event not in c.events:
            s.pending_event = None
        sensing.drop_stale(s, c)  # 有所感的場景被拿掉、人不在那裡了：作廢（悟意境設計第零節）
        if p.pending_companion and p.pending_companion not in c.characters:
            p.pending_companion = None
        if p.pending_faction and p.pending_faction not in {f.id for f in c.scenario.factions}:
            p.pending_faction = None
        if p.pending_defect and p.pending_defect not in {f.id for f in c.scenario.factions}:
            p.pending_defect = None
        lost_place = p.location not in c.locations
        if lost_place:
            p.location = c.scenario.start_location
        if p.picking_audience and not self._audience_hall():
            p.picking_audience = False  # 內容改版後這裡不再有兩位以上的人物：收起求見選單
        j = p.journey
        if j is not None and (
            lost_place  # 所在地被拿掉、改回起點：腳下這段路已經不存在
            or any(loc_id not in c.locations for loc_id in j.path)
            or (j.origin is not None and j.origin not in c.locations)  # 改道後半段路的起點（見 atlas.road_spot）
        ):
            p.journey = None
            p.leg_actions = set()  # 這段路不在了：下次出發是新的一段
        p.surveyed = {loc_id for loc_id in p.surveyed if loc_id in c.locations}
        p.leg_actions &= set(ROAD_TASKS)
        p.recent_sights = [sight_id for sight_id in p.recent_sights if sight_id in c.road_sights]
        p.team = [k for k in p.team if k in c.characters][: team.MAX_TEAM_COMPANIONS]
        # 身上的武學要真的有這一門：is_skill_name_taken 連改過的名字、意境名都算，不能拿來判斷「武學存在」，要用 get_skill
        if p.member.neigong_id and p.member.neigong_id not in c.skills and self.world.get_skill(p.member.neigong_id) is None:
            p.member.neigong_id = None
        if p.member.wugong_id and p.member.wugong_id not in c.skills and self.world.get_skill(p.member.wugong_id) is None:
            p.member.wugong_id = None
        # 武學欄不會空（開局送兩門、身上的熔不掉，也不能再自創）。改版前存的角色欄位空著，讀檔時補回開局那一門；
        # 它已經在功法庫裡就拿出來配上，熟練度沿用庫裡記的，否則從第一成起（沒有 starter_skills 的內容什麼都不做）
        for starter in c.config.starter_skills:
            slot = "neigong" if c.skills[starter].kind == "內功" else "wugong"
            if getattr(p.member, f"{slot}_id") is None:
                setattr(p.member, f"{slot}_id", starter)
                setattr(p.member, f"{slot}_level", p.art_levels.get(starter, 1) if starter in p.arts else 1)
        # 功法庫與素材：內容檔改版（或換季）後可能指到不存在的東西
        equipped = {p.member.neigong_id, p.member.wugong_id}
        seen: set[str] = set()
        p.arts = [  # 去重，並把已經配在身上的從庫裡移除（舊版重煉同一配方會造成這種髒狀態）
            a for a in p.arts
            if team.resolve_art(a, c, self.world) is not None and a not in equipped and not (a in seen or seen.add(a))
        ]
        p.art_levels = {k: v for k, v in p.art_levels.items() if team.resolve_art(k, c, self.world) is not None}
        p.materials = {k: v for k, v in p.materials.items() if k in c.materials and v > 0}
        # 武學與成長（設計第三、四節）：意境去重、去掉找不到的；品質、熟練度只留還擁有的武學；
        # 等著取名的那一門要真的是自己第一個練成的（換季、熔掉、內容改版後都可能對不上）
        p.insights = [i for i in dict.fromkeys(p.insights) if insights.resolve(i, c, self.world, s) is not None]
        p.own_insights = {k: v for k, v in p.own_insights.items() if k in p.insights}  # 熔掉的私有意境本體跟著拿掉
        owned = set(library.owned_arts(s))
        p.art_quality = {k: v for k, v in p.art_quality.items() if k in owned and v in QUALITIES}
        p.art_mastery = {k: v for k, v in p.art_mastery.items() if k in owned and v > 0}
        p.art_rolled = {k: v for k, v in p.art_rolled.items() if k in owned and v in QUALITIES}
        if p.naming is not None and (p.naming not in owned or self.world.master_of(p.naming) != p.name):
            p.naming = None
        chains = {ch.id for ch in c.foreshadows.chains}  # 伏筆：內容改版後拿掉的鏈與物品
        items = {item.id for item in c.foreshadows.items}
        p.clue_items = {k: v for k, v in p.clue_items.items() if k in items and v > 0}
        p.fragments = {k: v for k, v in p.fragments.items() if k in chains}
        p.snubbed_until = {k: v for k, v in p.snubbed_until.items() if k in c.figures}  # 內容改版拿掉的大勢人物（T4）
        if p.fs_asking is not None and p.fs_asking not in chains:
            p.fs_asking, p.fs_asked = None, 0
        line_ids = [line.id for line in c.scenario.storylines]
        if s.world.storyline not in line_ids:
            s.world.storyline, s.world.act = line_ids[0], 0
        acts = next(line for line in c.scenario.storylines if line.id == s.world.storyline).acts
        s.world.act = min(s.world.act, len(acts) - 1)
        s.world.act_reached = max(s.world.act_reached, s.world.act)
        if "tutorial_step" not in p.model_fields_set:
            p.tutorial_step = len(c.tutorial.steps)  # 最舊的存檔連這一欄都沒有：引導當作做完
        elif prologue_rules.has(c) and p.onboarding < ONBOARDING_VERSION:
            # 舊存檔：當作走過序章，舊的第一季兩步往後挪（新手引導設計 7.2）
            p.tutorial_step = prologue_rules.migrated_step(p, c)
        if prologue_rules.has(c):
            p.onboarding = ONBOARDING_VERSION  # 內容沒有序章時步數還是舊編號，不蓋章（preflight F6）
        p.tutorial_step = min(p.tutorial_step, len(c.tutorial.steps))
        t = c.tutorial
        if (t.location is not None and p.tutorial_step < t.prologue_steps and p.location != t.location
                and p.journey is None):
            prologue_rules.finish(s, c, self.world, purse=False)  # 序章沒走完卻不在草廬（內容改版）：當作走過，不卡住
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

    @classmethod
    def for_world(
        cls, content: Content, world: WorldStateStore, rng: random.Random | None = None,
    ) -> Game:
        """沒有玩家的 Game：給伺服器的排程推全服的事用（線上架構設計第四節，見 world_tick）。state 是共用賽季的空殼
        （world._season_vehicle：名號空白、不存檔），所以收場補送戰報、季終收兵那些「補給自己」的步驟對它都是空的。"""
        return cls(content, _season_vehicle(content, world.get_season()), rng, world)

    def world_tick(self, now: float) -> list[str]:
        """伺服器排程的一下：全服的事推到 now。跟玩家 sync 加上 options() 裡全服的那一半一樣，所以有沒有人在線都一致：
        1. 補算共用賽季（catch_up_season：大勢、季的事、時刻表、時間到了開決戰、季末收季）；
        2. 推一次決戰（_battle_status：集結與回合逾時、機器人補位、結算、收場套結果、季終收兵、開等著的決戰）。
        兩邊都是「追到 now 為止」，排程與玩家的請求誰先誰後都只推一次。不存角色、不寫任何人的江湖紀錄：
        大事公告與決戰戰報照舊在每個人同步時補（FB-038、W13）。回傳的訊息只給排程印紀錄用。"""
        self.now = now
        self._reconcile_season()
        msgs = list(self.world.catch_up_season(self.content, now, self.rng))
        self.state.world = self.world.get_season()
        self._battle_status(tick=True)
        return msgs

    def sync(self, now: float) -> list[str]:
        """把現實經過的時間推進到遊戲裡。玩家自己的體力/氣血照自己上次連線以來的步調追趕；
        共用賽季的時間/大勢則照「距離上次有人追趕過了多久現實時間」追趕——不管是誰觸發、
        隔多久觸發一次，一份共用時鐘永遠只走一次，不會因為好幾個玩家同時在線就重複推進
        （見 world_state.py::catch_up_season）。也會順便偵測共用賽季是不是已經被別人推到
        下一輪了（見 _reconcile_season）。在路上時，抵達時間已經到了的站接著一站一站抵達（見 _arrivals）。"""
        self.now = now
        away_from = self.state.last_real  # 上次同步的現實時間，下面就換成 now（「你不在的時候」看它，見 _deliver_away）
        self._reconcile_season()
        msgs = list(self.world.catch_up_season(self.content, now, self.rng))
        self.state.world = self.world.get_season()  # 剛才的追趕可能進一步推進了賽季，拉回最新的一份
        self._stamp_join()  # 新角色、換季重來的角色：補算完賽季才記下加入的那一刻
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
        news = journal.news_entry(self.state.world.time, self._without_timetable(msgs))
        if news is not None:
            journal.add_entry(self.state, news, merge=True)
        self._deliver_big_events()  # 這一季的時刻表大事人人有份：沒看過的補上，推進的人也走這一條（FB-038）
        self._backfill_battle_scores()  # 場上沒有份量快照的自己（上線前就在決戰裡）：補上；排程的 world_tick 不走這裡
        self._deliver_battle_results()  # 下線時收場的決戰，回來第一次同步就補上（休季、籌備中也一樣，FB-027）
        self._deliver_renames()  # 手上的絕學被人定了名：下一次同步補一則紀錄（FB-083）
        self._deliver_echoes()  # 別人照著你首創的配方合了出來：補名望（首創名望回饋）
        settled = self._settle_plots()  # 不在線時收場的密謀，回來第一次同步就結算（正式版乙二）
        if settled:
            self._write("密謀", settled)
            self._save_season()  # 逾期的密謀在這裡改成作罷，那是共用賽季的一份
        summons = ranks.check_summons(self.state, self.content)  # 行動之外記到的貢獻（抵達、別人觸發的結算）：同步時補發召見（計畫 T5）
        if summons:
            self._write("召見", summons)
        # 第四階席次：抄帳、補缺（正式版丁）。輪詢只同步、只存角色（server.poll_main → act_look），所以帳或名單變了要自己把共用賽季存回去，
        # 不然補上的缺、那一則陣營軍情都會丟掉，下一次輪詢又補一次、又寫一則紀錄
        watching = self.state.player.qualified or seats.on_the_books(self.state)  # 沒資格、帳上也沒有名字的人，同步不碰共用賽季
        ledger_before = self.state.world.model_dump(include={"seat_ledger", "seats"}) if watching else None
        seated = self._report_seat()
        if ledger_before is not None and self.state.world.model_dump(include={"seat_ledger", "seats"}) != ledger_before:
            self._save_season()
        if seated:
            self._write("席次", seated)  # 新寫，待 joy 潤：紀錄的標題
        self._guide(enlist.expire(self.state, self.content))  # 第一道軍令一週還沒做完：引薦人照樣說結語（FB-094）；說的話記進江湖紀錄
        self._check_hints()  # 抵達、大事揭曉、決戰集結這些不靠行動的改變，加上籌備中、休季之後第一次同步、換季後的開季那一句：新的排一條、輪到的上框（新手引導計畫三；只改 guide，不另起一則）
        self._deliver_away(away_from)  # 最後寫：江湖頁的「剛剛」先放這一份摘要（要跟別的計畫合併時，這一行維持在 return 的前一句）
        return self._log(msgs + arrived + settled + summons + seated)

    def _report_seat(self) -> list[str]:
        """第四階席次的抄帳與補缺（seats.report）：賽季時鐘暫停中不做（丁 N5 的裁決：暫停凍結世界的變化，
        不補缺、不發軍情、帳也不抄；繼續之後的第一次同步補上，只補一次）。暫停時畫面照常可看、同步照常走，所以這裡要自己擋。"""
        if self.world.paused_at() is not None:
            return []
        return seats.report(self.state, self.content)

    def _settle_plots(self) -> list[str]:
        """集體密謀的結算（正式版乙二；opportunities.settle）：賽季時鐘暫停中不結算。暫停時畫面照常可看、計時器的同步照常走
        （sync 不經 _refuse_while_paused），動作被擋；結算會記貢獻、完成機緣，那是動作的結果，所以也等繼續之後的第一次同步。"""
        if self.world.paused_at() is not None:
            return []
        return opportunities.settle(self.state, self.content)

    def _deliver_away(self, away_from: float | None) -> None:
        """「你不在的時候」（傳聞分層設計第八節）：上次同步到這一次隔了 Config.away_hours 個「現實」小時以上（PM 2026-10-06：
        這一項看現實時間；網頁開著時每 10 秒同步一次，所以這就是沒開著畫面的時間），江湖紀錄最前面放一則摘要——這段期間
        聽得到的天下大事、陣營軍情的要點、所在大區的地方傳聞（rumor_view.away_lines，最多 away_max 則）。時刻表大事照舊由
        _deliver_big_events 補成「江湖大事」那一則，摘要不寫第二次。什麼都沒有就不寫。
        只在第一季的規則開著時；伺服器假人不寫（沒有人看，畫面上也不會出現）；剛建好的角色（還沒同步過）不寫。
        不管寫不寫，都記下這一刻的賽季時間（GameState.last_world），下一次從這裡往後算。"""
        s, c = self.state, self.content
        since, s.last_world = s.last_world, s.world.time
        if away_from is None or s.player.bot is not None or not season_one(c, s.world):
            return
        if self.now - away_from < c.config.away_hours * HOUR:
            return
        lines, total = rumor_view.away_lines(s, c, since, self.stamp)
        if lines:
            tag = rumor_view.AWAY_TAG.format(n=total)
            journal.add_entry(s, JournalEntry(time=s.world.time, title=journal.AWAY, tag=tag, lines=lines))

    def advance(self, seconds: float) -> list[str]:
        """玩家主動「等待」固定一段遊戲時間（快轉按鈕）：進行中時，直接在 self.state.world
        （剛同步過的共用賽季副本）上往前推進 seconds，再存回共用儲存——跟 choose()/travel()
        同一套「本地修改、行動結束後存回」模式，不是用現實時間反推（那是 sync() 的事）。
        籌備中、休季時共用賽季不動，只推進玩家自己的部分。推進途中跨過開戰門檻的戰鬥，
        存回之後才開（見 world.start_pending_battle），再拉回最新的共用賽季。在路上時，同 sync 補算
        抵達時間已經到了的站（見 _arrivals）。"""
        if self.world.paused_at() is not None:  # 管理者的快轉：時鐘停著時不推，先按「繼續」
            return self._log(["（賽季時鐘暫停中，不能快轉；先按「繼續」。）"])  # 待 S1／joy 潤
        self._stamp_join()  # 同 sync：推進之前先記下加入的那一刻（沒同步過就直接快轉的測試與整季機器人）
        msgs: list[str] = []
        if self.world.season_phase() == "running":
            msgs += advance_world_state(self.state.world, self.content, seconds, self.rng, self.world)
        msgs += self._advance_player_local(seconds)
        arrived = self._arrivals()  # 同 sync：抵達自己寫紀錄
        self._save_season()
        msgs += start_pending_battle(self.world, self.content, self.now)
        self.state.world = self.world.get_season()
        news = journal.news_entry(self.state.world.time, self._without_timetable(msgs))
        if news is not None:
            journal.add_entry(self.state, news, merge=True)
        self._deliver_big_events()
        return self._log(msgs + arrived)

    def _stamp_join(self) -> None:
        """記下這個角色加入這一季的那一刻（PlayerState.joined_at，新手福利從這裡起算，第一季設計第十四節）：
        新角色與換季重來的角色是 None，第一次 sync（補算完賽季之後）或 advance 才蓋；蓋過就不再動。"""
        p = self.state.player
        if p.joined_at is None:
            p.joined_at = self.state.world.time

    def _advance_player_local(self, seconds: float) -> list[str]:
        """玩家自己的部分：體力（打坐中加倍）／氣血回復、打坐回滿起身、閉關出關、新立門戶福緣——
        這些是「我」的進度，不是共用賽季的一部分，照自己經過的時間算，不受共用賽季時鐘怎麼走影響。"""
        cfg, p, w = self.content.config, self.state.player, self.state.world
        regen = seconds / cfg.stamina_regen_seconds
        if p.resting_since is not None:
            regen *= cfg.rest_regen_multiplier  # 打坐中回復加倍
        if roster.newbie(self.state, self.content, cfg.newbie_stamina_days):
            regen *= cfg.newbie_stamina_multiplier  # 新手期體力回復加快，跟打坐疊乘（體力平衡提案第〇節）
        p.stamina = min(cfg.stamina_max, p.stamina + regen)
        rate = seconds / (cfg.neili_regen_hours * HOUR)
        if p.busy_until is not None:
            rate *= 2
        if roster.newbie(self.state, self.content):  # 第一季從自己加入那天起算（roster.since_join），beta 照舊從季初
            rate *= 2
        team.regen_neili(self.content, p.member, rate, team.con_of(self.state, self.content, self.world, PLAYER))
        for cid in p.team:
            con = team.con_of(self.state, self.content, self.world, cid)  # 同伴回到他自己的上限（人物資質設計 14.3）
            self.world.update_companion(cid, lambda progress, con=con: team.regen_neili(self.content, progress, rate, con))
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
        battle_status = self._battle_status(tick=tick)
        if self.world.paused_at() is not None:  # 賽季時鐘暫停（線上架構 8.3「擋住所有動作」）：選單只剩一顆灰的
            return [Option(id="season:paused", label=PAUSED_TEXT, enabled=False)]
        if battle_status is not None and not self._watching_battle(*battle_status):
            battle, definition = battle_status
            if battle.phase == "muster":
                # 集結那段時間照常遊玩，加入的按鈕（已經加入就是灰的「已加入」）放在平常的選單前面
                # （企劃者 2026-10-03 決定，FB-009）；走出決戰的大區就照 _watching_battle 算不在場
                return self._battle_options(battle, definition) + self._everyday_options(odds)
            battle_menu = self._battle_options(battle, definition)
            if self.state.player.resting_since is not None:
                battle_menu.append(self._stand_option())  # 戰鬥選單取代整份選單，隨時可以起身這條規則不能因此掉了
            if self.state.player.pending_defect:  # 同理：開著的叛投確認畫面不能因為開打就卡到整場打完（最終審查 Minor 1）
                battle_menu.append(Option(id="defect:cancel", label="再想想"))
            return battle_menu
        return self._everyday_options(odds)

    def _everyday_options(self, odds: bool) -> list[Option]:
        """平常的選單（沒有要親身參與、已經開打的決戰時；集結時接在加入的按鈕後面）：籌備或休季、事件、對話、
        投靠確認、求見名單、閉關、在路上、打坐，都不是就是在地點上能做的事。"""
        s, c = self.state, self.content
        if self._preparing():
            return [Option(id="season:preparing", label=PREPARING_TEXT, enabled=False)]
        if s.world.ended:
            return [Option(id="season:resting", label="休季中，等待管理者開啟下一季", enabled=False)]
        if s.pending_event:
            event = c.events[s.pending_event]
            opts = [
                Option(
                    id=f"choice:{i}", label=self._choice_label(ch, odds),
                    wait=BIG_FIGHT_WAIT if ch.combat and self.is_big(c.squads[ch.combat]) else "",
                )
                for i, ch in visible_choices(event, s, c)
            ]
            if event.free_text is not None:
                opts.append(Option(id=FREE_TEXT_OPTION, label=event.free_text.prompt + free_text_note(event.free_text, c)))
            return opts
        if s.player.sensing is not None:  # 有所感（悟意境設計第零節）：卡上的做法，或感悟狀態的「畫下來／順其自然」
            menu = sensing.menu(s, c)
            if menu:
                return [Option(id=option_id, label=label) for option_id, label in menu]
        if s.player.pending_companion:
            dialogue_options, _ = s.player.last_offered_dialogue.get(s.player.pending_companion, [[], []])
            talk_cost = c.config.talk_stamina
            opts = [self._cost_option(f"talk:{i}", text, talk_cost) for i, text in enumerate(dialogue_options)]
            opts += foreshadow.talk_options(s, c, s.player.pending_companion)  # 伏筆的片段：固定文字、不花體力（計畫 T7）
            opts += opportunities.talk_options(s, c, s.player.pending_companion)  # 機緣的話題（正式版乙一）：不花體力
            opts.append(Option(id="talk:leave", label="告辭"))
            return opts
        if s.player.pending_faction:
            faction = self.content.scenario.faction(s.player.pending_faction)
            return [
                Option(id="faction:confirm", label=f"確定投靠{faction.name}"),
                Option(id="faction:cancel", label="再想想"),
            ]
        if s.player.pending_defect:
            target = self.content.scenario.faction(s.player.pending_defect)
            return [
                Option(id="defect:confirm", label=f"確定叛投{target.name}"),
                Option(id="defect:cancel", label="再想想"),
            ]
        if s.player.picking_audience:
            return self._audience_options()
        if s.player.fs_asking is not None:
            return foreshadow.asking_options(s, c)  # 伏筆的最後一步正在答題：只有答案與「作罷」
        if s.player.busy_until is not None:
            return [Option(id="act:break", label="提前出關")]
        j = s.player.journey
        if j is not None:
            end = c.locations[j.path[j.last]].name
            opts = [Option(id="act:on_road", label=f"（在路上，{self.stamp(j.arrive_at[j.last])} 抵達{end}）", enabled=False)]
            opts.append(self._back_option())  # 折返（路上設計 3.2）；改去別處在大地圖上安排
            if j.stop_at is None and j.reached < j.last:
                opts.append(Option(id="act:halt", label=f"喊停（到{c.locations[j.path[j.reached]].name}就停下）"))
            return opts + self._road_task_options(j)
        if s.player.resting_since is not None:
            return [self._stand_option()]
        loc = c.locations[s.player.location]
        cost = self._action_costs()
        opts = [self._cost_option("act:explore", "探索", cost["explore"])]
        if self._train_squad_ids(loc):
            # 遊歷：這個地點的敵人，必定開打（見 _train）。sanguo-companions 合併時這個行動被
            # 整個拿掉，於是 Location.enemies／action_cost["train"]／train_event_chance 三個設定
            # 一起變成死的，而遭遇戰只剩劇情事件的 combat 選項——實測整季只打 3 場。
            #
            # 標籤要顯示勝算（跟劇情戰的選項同一套慣例，見 _choice_label）：實機試玩發現
            # 新角色沒有武學時威力是 0，在任何地點遊歷都**必敗**，而落敗現在真的要付氣血與
            # 內傷的代價——不顯示勝算的話，玩家會在開局連輸三場、氣血見底才知道自己不該打。
            opts.append(self._train_option(loc, cost["train"], odds))
        opts += self._challenge_options(odds)  # 挑戰本人（T4）：第一季、有陣營、這裡站著敵方的大勢人物時才有
        if ranks.summons_event(s, c) is not None:
            opts.append(Option(id="act:summons", label="應召"))  # 晉升奇遇（計畫 T5）：人在召見的地點才有，不花體力
        people = self._figures_here()
        # 只有一位大勢人物、沒有交友事件、他又見不到（名望不夠、閉門不見、今天談滿）、福緣也沒到、也不在召見的地點：
        # 交友只會花 5 點體力換同一句打發，所以不給，這條路只剩不花體力的求見（下面）
        only_the_door = len(people) == 1 and ranks.summons_event(s, c) is None and self.socialize_is_futile()
        if (has_events_here(c, loc, "socialize") or 0 < len(people) < AUDIENCE_HALL_FIGURES) and not only_the_door:
            # 兩位以上大勢人物的地點，交友只走福緣與地點事件、從不開口對話（見 _socialize_figure），
            # 所以只在有交友事件時才給；人物改由下面的「求見」指名
            opts.append(self._socialize_option(people, cost["socialize"]))
        if len(people) == 1:  # 只有一位：直接求見他，一直按得下去（武學與成長設計 9.1）
            cid = people[0]
            ch = c.characters[cid]
            if self._snubbed_character(cid):
                opts.append(Option(id=f"call:{cid}", label=f"求見{ch.name}（{SNUB_NOTE}）", enabled=False))
            elif not self._can_meet(cid):
                opts.append(Option(id=f"call:{cid}", label=f"求見{ch.name}（名望還差 {self._fame_gap(cid)}）"))  # 按下去走打發，見 _brush_off
            elif self._talks_left(cid) == 0:  # 求見一直都在：談滿了也留著、灰掉，說法跟求見名單一樣
                opts.append(Option(
                    id=f"call:{cid}", enabled=False,
                    label=f"求見{ch.name}（今天已經談滿 {c.config.talk_turns_per_day} 輪，明天再來）",
                ))
            else:
                opts.append(self._cost_option(f"call:{cid}", f"求見{ch.name}", cost["socialize"]))
        if len(people) >= AUDIENCE_HALL_FIGURES:
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
            if not atlas.is_unlocked(c.locations[dest_id], s):  # 世界旗標沒開、序章的草廬（只給站在那裡的人）
                continue
            opts.append(self._move_option(loc.id, dest_id))
        for skill, problem in library.lessons_here(s, c):  # 拜師學藝（武學與成長設計附錄 B）：不花體力
            note = library.lesson_note(skill) if problem is None else problem
            opts.append(Option(id=f"learn:{skill.id}", label=f"學{skill.name}（{note}）", enabled=problem is None))
        if s.player.faction is None:
            for faction in c.scenario.factions:
                if s.player.location in faction.join_at:
                    opts.append(Option(id=f"faction:{faction.id}", label=f"投靠{faction.name}"))
        for target in self._defect_targets():  # 叛投（計畫甲）：別的陣營的投靠點、一季一次、不在沒打完的決戰的參戰名單上
            opts.append(Option(id=f"defect:{target.id}", label=f"叛投{target.name}"))
        opts += self._order_options(loc)  # 軍令（計畫 T6）：守勢行動、接糧車；開關關著、散人沒有
        opts += self._rank2_options(loc)  # 第 2 階行動（正式版乙一）
        opts += self._rank_action_options(loc)  # 第 3、4 階的行動（正式版戊一）
        opts += opportunities.place_options(s, c, loc.id)  # 機緣：交東西、天時地利（正式版乙一）
        opts += foreshadow.final_options(s, c, loc.id)  # 伏筆的最後一步（計畫 T7）：做得了的人在那個地點才有
        opts.append(Option(id="act:rest", label="打坐（坐下來回體力，隨時可以起身）"))
        return prologue_rules.allowed(opts, s, c)  # 序章裡在草廬閒著時只留這一步要的（新手引導計畫一）

    @staticmethod
    def _stand_option() -> Option:
        return Option(id="act:stand", label="起身")

    def _move_option(self, here: str, dest_id: str) -> Option:
        """選單上的「前往 相鄰地點」，照主畫面選的走法（move_mode）：標籤寫這種走法的時間與體力，體力不夠就按不下去、
        寫明原因（跟大地圖的「安排前往」按鈕同一個說法）。步行的 id 維持 move:<地點>（機器人、假人與舊的呼叫端
        只認這個）；趕路、疾行是 move:<地點>:<走法>，所以 choose() 照樣只認選單上真的有的 id。"""
        c, mode = self.content, self.move_mode
        dest = c.locations[dest_id]
        minutes = atlas.leg_minutes(c, here, dest_id)
        option_id = f"move:{dest_id}" if mode == "walk" else f"move:{dest_id}:{mode}"
        cost = atlas.travel_stamina(c, minutes, mode)
        if self.state.player.stamina < cost:
            return Option(id=option_id, label=f"前往 {dest.name}（{atlas.MODES[mode]}・體力不足，要 {cost}）", enabled=False)
        return Option(id=option_id, label=f"前往 {dest.name}（{atlas.mode_text(c, minutes, mode)}）")

    def _back_way(self) -> atlas.Route:
        """折返的路：從路上回到身後那一站（路上設計 3.2：折返就是「改去」那一站，見 atlas.way_to）。
        掉頭那一種走法到身後那一站一定算得出來，所以在路上時不會是 None。"""
        spot = atlas.road_spot(self.state, self.content)
        return atlas.way_to(self.state, self.content, spot.behind)

    def _back_option(self) -> Option:
        """路上的「折返 某站」，照主畫面選的走法（move_mode）：標籤寫這種走法的時間與體力，體力不夠就按不下去、寫明原因
        （跟「前往」同一個說法，見 _move_option）。id 也跟「前往」一樣：步行是 road:back，趕路、疾行是 road:back:<走法>，
        所以 choose() 照樣只認選單上真的有的 id。"""
        c, mode = self.content, self.move_mode
        way = self._back_way()
        name = c.locations[way.path[-1]].name
        option_id = "road:back" if mode == "walk" else f"road:back:{mode}"
        cost = atlas.route_stamina(self.state, c, way, mode)
        if self.state.player.stamina < cost:
            return Option(id=option_id, label=f"折返 {name}（{atlas.MODES[mode]}・體力不足，要 {cost}）", enabled=False)
        return Option(id=option_id, label=f"折返 {name}（{atlas.route_text(self.state, c, way, mode)}）")

    def _road_task_options(self, j: Journey) -> list[Option]:
        """路上小事（路上設計第四節）：步行、趕路時四樣各一顆，不花體力；這一段路做過的灰掉、寫「這段路已經……」。
        疾行一站一站立刻抵達，沒有。今天的收穫拿滿了（每天上限）的邊走邊想、路邊採集照樣按得下去，補充改寫「今天沒有收穫了」。"""
        if j.mode == "dash":
            return []
        hints = {
            "think": f"心得 +{self.content.config.road_think_xinde}",
            "ask": "聽一則這一帶的傳聞",
            "survey": "摸清附近的地點",
            "gather": "有機會撿到素材",
        }
        if not self._road_reward_due("task"):
            for what in ROAD_REWARD_TASKS:
                hints[what] = "今天沒有收穫了"  # 不留「心得 +3」：拿滿了就沒有
        done = self.state.player.leg_actions
        return [
            Option(id=f"road:{what}", label=f"{name}（{did}，到下一站再說）", enabled=False) if what in done
            else Option(id=f"road:{what}", label=f"{name}（{hints[what]}）")
            for what, (name, did) in ROAD_TASKS.items()
        ]

    def set_move_mode(self, mode: str) -> None:
        """主畫面的「走法」切換：之後選單上的「前往」用這種走法；不認得的走法當成步行。不存檔（見 __init__ 的 move_mode）。"""
        self.move_mode = mode if mode in atlas.MODES else "walk"

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

    def _socialize_option(self, people: list[str], cost: int) -> Option:
        """交友的按鈕。這裡只有一位大勢人物、沒有交友事件、福緣也還沒到，而他剛被你打敗、閉門不見（T4）時，交友只會
        撲空——按不下去、寫明原因。其他時候照舊。"""
        s, c = self.state, self.content
        if (
            len(people) == 1 and self._snubbed_character(people[0])
            and not has_events_here(c, c.locations[s.player.location], "socialize") and not roster.fortune_due(s, c)
        ):
            return Option(id="act:socialize", label=f"交友（{SNUB_NOTE}）", enabled=False)
        return self._cost_option("act:socialize", "交友", cost)

    def _train_option(self, loc: Location, cost: int, odds: bool) -> Option:
        """遊歷的按鈕。遇上自己陣營的隊伍是操練、不會輸（見 _drill），所以只有自己人的地盤寫成「操練・零風險」，
        不拿自己人去算勝算「必敗」（試玩回饋 FB-008）；自己人與外人都有的地方，勝算只看真的會打的那幾路。
        這一趟會是大場面（備料挑到的那一路，見 _train_pick）時，按下去要等模型判讀：wait 寫「兩人對峙……」。"""
        squads = [self.content.squads[sid] for sid in self._train_squad_ids(loc)]
        foes = [squad for squad in squads if not self._drills_with(squad)]
        if not foes:
            return self._cost_option("act:train", "操練", cost, note="零風險")
        note = self._train_note(foes, odds and prologue_rules.fight_tier(self.state, self.content) is None)  # 序章的勝負寫好了，不標勝算
        if len(foes) < len(squads):
            note += "・或與自己人操練"
        option = self._cost_option("act:train", "遊歷", cost, note=note)
        if "必敗" in note.split("・"):  # FB-095：剛出師的人疾行到敵營按遊歷，三場就掉三分之一的銀兩
            option.confirm = TRAIN_CONFIRM
        pick = self._train_pick(loc)
        if (pick is not None and not self._drills_with(pick) and self.is_big(pick)
                and prologue_rules.fight_tier(self.state, self.content) is None):  # 寫好的那一場不等模型
            option.wait = BIG_FIGHT_WAIT
        return option

    def _train_note(self, squads: list[Squad], odds: bool) -> str:
        """遊歷按鈕上的補充說明：對手是誰、勝算多少（勝算的計算比較貴，所以照既有慣例吃 odds 旗標）。"""
        who = squads[0].name if len(squads) == 1 else f"{len(squads)} 路對手"
        if not odds:
            return who
        # 多路對手時以**最強的**那個當參考（真的開打平常是用 Game.rng 隨機挑；池子裡有大場面對手的地方照 _train_pick 挑，
        # 見 _train）：這個標籤的用途是警告玩家，寧可低估也不要給出過度樂觀的承諾。
        hardest = max(squads, key=lambda s: s.difficulty)
        return f"{who}・{self.odds(hardest.id)}"

    def _choice_label(self, choice: Choice, odds: bool) -> str:
        """動手的選項寫對手與勝算，後面照樣接體力的代價（輸了多扣的，企劃者裁決 E6；events.stamina_note）；
        有檢定的寫一行「（屬性 數值：心裡話）」（events.choice_label）。"""
        if choice.combat and odds:
            squad = self.content.squads[choice.combat]
            return f"{choice.text}（對手：{squad.name}・{self.odds(squad.id)}）{stamina_note(choice, self.content)}"
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
          （兩位以上的地點交友不開口，見 _socialize_figure）；玩家這一步固定是 GENERIC_OPENING。
        - `call:<人物>`：求見選單上按得下去、而且見得到（名望或階級夠、或結識過）的那位人物（今天還沒談滿、體力夠）；
          名望不夠的求見也按得下去，但那是被打發、不生成。玩家這一步固定是 GENERIC_OPENING。`call:back` 不生成。
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
            if roster.fortune_due(self.state, self.content) or ranks.summons_event(self.state, self.content) is not None:
                return None  # 福緣先發；在召見的地點交友端出晉升奇遇（計畫 T5，審查 I1）——都不開口對話
            companion_id = self._socialize_figure()
            if companion_id is None:
                return None
            player_action = companion_agent.GENERIC_OPENING
        elif kind == "call" and arg != "back":
            if not self._can_meet(arg):
                return None  # 門檻不夠：被打發，不叫模型（見 _call、_brush_off）
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

    # ── 大場面：鎖外請模型判讀（武學與成長設計 8.3、計畫三 Task 2）────────────

    def is_big(self, squad: Squad) -> bool:
        """大場面：對手標了頭目、是大勢人物本人（figures 的 squad），或難度到 big_fight_difficulty（武學與成長設計 8.3）。
        只看對手本身：遊歷遇上自己陣營的隊伍是操練、不打架，那是遊歷那一條路自己擋（_fight_squad、_train_option）；
        劇情戰從來不操練（_event_battle 不看陣營），黃巾的人打黃巾的頭目照樣是大場面（Task 2 審查修正 1）。"""
        return styles.is_big(self.content, squad)

    def _big_trip(self, loc: Location) -> bool:
        """這裡遊歷可能撞上大場面：池子（_train_squad_ids）裡有不是自己人的大場面對手。這種地點的遊歷一律照 _train_pick 挑對手
        （Task 2 審查修正 3）；正式內容目前沒有這種地點，所以每一處遊歷照舊用 Game.rng 挑。"""
        squads = (self.content.squads[sid] for sid in self._train_squad_ids(loc))
        return any(self.is_big(squad) and not self._drills_with(squad) for squad in squads)

    def _train_pick(self, loc: Location) -> Squad | None:
        """池子裡有大場面對手（_big_trip）的地點，這一趟遊歷遇上哪一路（計畫三 G1、Task 2 審查修正 3）：照（名號、地點、戰報流水號）
        雜湊，從 _train_squad_ids 挑一路；沒有對手是 None。按鈕的「兩人對峙」、備料（A 段）、套用（C 段）、判讀失敗照平常打，
        看的都是它：A、C 之間流水號不動（模型那一分鐘裡沒有打別的仗），兩邊挑到同一路；打過一場流水號就變，對手照樣輪替。
        池子裡沒有大場面對手的地點不用它，照舊用 Game.rng 隨機挑（亂數序列、整季模擬與好玩度量表的對手組成都不變）。"""
        ids = self._train_squad_ids(loc)
        if not ids:
            return None
        key = f"{self.state.player.name}|{loc.id}|{self.state.battle_seq}".encode()
        return self.content.squads[ids[int.from_bytes(hashlib.sha256(key).digest()[:4], "big") % len(ids)]]

    def _fight_squad(self, option_id: str) -> Squad | None:
        """這個選項按下去會打哪一路（遊歷、挑戰大勢人物本人、劇情戰的戰鬥選項）；不會打仗是 None。
        隨口應對（choice:free）不是數字，不是仗。"""
        s, c = self.state, self.content
        kind, _, arg = option_id.partition(":")
        if option_id == "act:train":
            pick = self._train_pick(c.locations[s.player.location])
            return None if pick is None or self._drills_with(pick) else pick  # 遇上自己人是操練，不打架
        if option_id.startswith("act:challenge:"):
            fid = option_id.removeprefix("act:challenge:")
            return figures.squad_of(s, c, fid) if fid in c.figures else None  # 難度照他此刻的聲威（T4）
        if kind == "choice" and arg.isdecimal() and s.pending_event:
            choices = c.events[s.pending_event].choices
            combat = choices[int(arg)].combat if int(arg) < len(choices) else None
            return c.squads[combat] if combat else None
        return None

    def fight_request(self, option_id: str) -> fight_llm.FightRequest | None:
        """大場面的 A 段（server.prepare_fight 在行動鎖內、很快地呼叫）：這個選項按下去會打一場大場面，就回傳送模型判讀的單子；
        不會（不是大場面、按不下去、自己陣營的操練、這個角色不叫模型——伺服器假人的 client 是 None）就是 None，伺服器在
        同一次拿鎖裡直接做完（計畫三 G14）。C 段進鎖重驗也呼叫它（_checked_fight），要一模一樣才採用。
        只讀、不改狀態，也不推進戰鬥（理由同 dialogue_request）。先看是不是大場面、再排選單：一般的仗不多排一次選單。"""
        if self.client is None:
            return None
        squad = self._fight_squad(option_id)
        if squad is None or not self.is_big(squad):
            return None
        if prologue_rules.fight_tier(self.state, self.content) is not None:
            return None  # 序章雪恥那一場勝負是寫好的：不叫模型判讀、不排佇列（斷眉難度再高、標了頭目也一樣）
        option = {o.id: o for o in self.options(odds=False, tick=False)}.get(option_id)
        if option is None or not option.enabled:
            return None
        s = self.state
        theirs = f"{squad.name}（屬{squad.attribute or '不明'}，難度 {squad.difficulty:.0f}"
        theirs += styles.fight_line(self.content, styles.style_of(s, self.content, self.world, squad)) + "）"  # 一門打不遍
        return fight_llm.FightRequest(
            option_id=option_id, squad_id=squad.id, location=s.player.location, battle_seq=s.battle_seq,
            event=s.pending_event,
            ours=[fight_llm.member_line(name, arts) for name, *arts in team.lineup(s, self.content, self.world)],
            theirs=theirs + (f"：{squad.desc}" if squad.desc else ""),  # 有來歷的對手多一句描述（設計 8.3「對手的描述」）
        )

    def _checked_fight(self, option_id: str, fight: fight_llm.PreparedFight | None) -> fight_llm.PreparedFight | None:
        """大場面 C 段的重驗（鎖內）：現在重算一張單子（fight_request），要跟鎖外判讀的那一張一模一樣才採用——同一個選項、
        同一路對手、同一個地點與事件、戰報流水號沒動（等模型的時候沒有打過別的仗）、雙方陣容一字不差（換了武學、帶的人，
        或對手的聲威被別人推動了，都算變了；Review Focus 3）。對不上就丟掉、照平常打（優勢 0）。"""
        if fight is None:
            return None
        return fight if self.fight_request(option_id) == fight.request else None

    def _fight_gone(self, fight: fight_llm.PreparedFight) -> str:
        """大場面 C 段：選項已經不在了。人不在備料時的地點了、或已經在路上就說「你離開了」；其他（事件被了結、體力花光……）
        認不出是哪一種變動，說得中性一點。備料（fight_request）一定是選項還按得下去才開單、而路上不開單，所以這裡只可能是等判讀的
        時候變的；步行、趕路出發之後 location 要到抵達才換（Journey 在路上時還是出發地），所以也要看 journey。"""
        player = self.state.player
        return FIGHT_LEFT if player.journey is not None or player.location != fight.request.location else FIGHT_CHANGED

    def _judged(self, squad: Squad) -> fight_llm.Judgment | None:
        """這一場有沒有鎖外判讀好的優勢：有、而且是同一路對手，就拿出來用掉——一次行動只用一次，同一次行動再打一場
        同一路也不會再吃一次（計畫三 G8）。"""
        fight = self._fight
        if fight is None or fight.request.squad_id != squad.id:
            return None
        self._fight = None
        return fight.judgment

    def _fight_with(self, squad: Squad, judged: fight_llm.Judgment | None, **kw) -> encounter.EncounterResult:
        """打一場單次判定（kw 照傳給 team.fight，挑戰本人的 difficulty）：有判讀就把優勢換成判定差距的平移
        （encounter.advantage_shift，照這一場真的用的難度、沒有功效的運氣範圍算；本人的功效改了運氣範圍時，單次判定裡會把它
        等比例縮放，推的百分點不變）；沒有是 0。優勢在這裡再夾一次 ±big_fight_swing 個百分點：
        fight_llm.judge 夾過了，但判讀不一定都經過它（之後的模型佇列也會交判讀進來），模型不能直接決定勝負（Task 2 審查修正 4）。"""
        shift = 0.0
        if judged is not None:
            swing = self.content.config.big_fight_swing
            shift = encounter.advantage_shift(squad.difficulty, max(-swing, min(swing, judged.advantage)))
        return team.fight(self.state, self.content, self.world, squad.id, self.rng, shift=shift, **kw)

    def _style_note(self, squad: Squad, result: encounter.EncounterResult) -> list[str]:
        """大場面對手的路數（styles，一門打不遍）在戰報裡含蓄的一句：打贏、用的剛好是他怕的那一路；或沒打贏、用的是他拿手對付的
        那一路。其他時候（不是大場面、第一季沒開、不相干的一路）什麼都不說。"""
        style = styles.style_of(self.state, self.content, self.world, squad)
        return styles.note(self.content, style, team.worn_attribute(self.state, self.content, self.world), result.tier)

    @staticmethod
    def _narrate(record, result: encounter.EncounterResult, judged: fight_llm.Judgment | None) -> None:
        """大場面的過程照結果挑一版：大勝、險勝是佔上風那一版，僵持、落敗是落下風那一版（計畫三 G15）。"""
        if judged is not None:
            record.narration = judged.winning if result.tier in team.WIN_TIERS else judged.losing

    def choose(
        self, option_id: str, prepared: companion_agent.PreparedTurn | None = None,
        fight: fight_llm.PreparedFight | None = None,
    ) -> list[str]:
        """prepared 是 server.py 在鎖外先生成好的一輪對話（見 dialogue_request／companion_agent.prepare_turn）；
        只有對話選項用得到，進來先重驗，驗不過就忽略。
        fight 是 server.py 在鎖外先判讀好的大場面（見 fight_request／fight_llm.judge）：一樣先重驗（_checked_fight），
        驗不過就忽略、照平常打（優勢 0）。假人、整季機器人不帶，大場面也是優勢 0、照平常演出（武學與成長設計 8.3）。
        不過等判讀的時候這個選項已經不在選單上了（人被帶走、事件被了結）就不打：回一句話說這一仗沒打成（_fight_gone），
        不寫戰報也不寫江湖紀錄（跟其他的拒絕一樣）。"""
        option = {o.id: o for o in self.options(odds=False)}.get(option_id)
        if option is None or not option.enabled:
            return self._log([self._fight_gone(fight) if fight is not None else "（此刻無法這麼做。）"])
        faction_before = self.state.player.faction  # 這一下才投靠的人才開始入伍段（見 _begin_enlistment）
        self.state.battle_card = None
        self.state.player.guide_done = []  # 對話框上一次完成的那幾行，下一次行動就清掉
        kind, _, arg = option_id.partition(":")
        if kind == "battle":  # 決戰選項不走 Draft：加入與趕到由 _battle_choose 自己寫一則紀錄，每回合的出招不寫（FB-030）
            return self._log(self._battle_choose(arg))
        if option_id == FREE_TEXT_OPTION:
            return self._log([f"（寫下你的做法，{FREE_TEXT_MAX} 字以內。）"])  # 選項本身只叫出輸入框，不消耗事件
        if option_id == sensing.DRAW:
            return self._log(["（在畫布上一筆畫下心中的形。）"])  # 只叫出畫布；畫完送出走 sense_request／sense_draw
        prepared = self._checked_prepared(option_id, prepared) if kind in ("act", "talk", "call") else None
        self._fight = self._checked_fight(option_id, fight)
        self._draft = Draft(self._action_title(kind, arg))
        stamina = self.state.player.stamina
        try:
            if kind == "act":
                msgs = self._act(arg, prepared)
            elif kind == "move":
                msgs = self._move(arg)
            elif kind == "talk":
                msgs = self._talk(arg, prepared)
            elif kind == "faction":
                msgs = self._faction_step(arg)
            elif kind == "defect":
                msgs = self._defect_step(arg)
            elif kind == "call":
                msgs = self._call(arg, prepared)
            elif kind == "road":
                msgs = self._road(arg)
            elif kind == "learn":
                msgs = library.learn(self.state, self.content, arg)
            elif kind == "opp":
                msgs = opportunities.act(self.state, self.content, self.world, arg, self.rng)
            elif kind == "fs":
                msgs = self._foreshadow(arg)
            elif kind == "sense":
                msgs = self._sense(arg)
            else:
                msgs = self._choose(int(arg))
            self._begin_enlistment(faction_before)  # 投靠（或拜入陣營名下的門派）那一下：入伍段開始，同一下不算完成任何一步
            self._greet_rejoin(faction_before)  # 入伍段早就走完的人再投靠：引薦人打個招呼（新手引導計畫三）
            msgs += self._hear_after_stamina(stamina)
            if kind == "choice":  # 選了事件的選項：序章的遇險、拜師、四景（新手引導計畫一）
                msgs += self._guide(note_action(self.state, self.content, self.world, "choice"))
            if kind == "act" and arg != "break":
                msgs += self._guide(note_action(self.state, self.content, self.world, arg))
            if kind == "call" and arg != "back":
                msgs += self._guide(note_action(self.state, self.content, self.world, "socialize"))  # 指名求見算一次交友
            msgs += check_thresholds(self.state, self.content, self.world, self._quick_client(), now=self.now)
            msgs += self._settle_plots()  # 參與過的密謀收場了：各自結算一次（正式版乙二）
            msgs += ranks.check_summons(self.state, self.content)  # 貢獻跨過門檻就發召見（計畫 T5）
            msgs += self._report_seat()  # 第四階席次：抄帳、補缺（正式版丁）；這個動作結束時 _save_season 一起存
            self._check_hints()  # 這一下碰到的新玩法排一條提示；事件了結、引導或入伍段走完的這一下，排著的上框。記在這一則的 guide（新手引導計畫三）
            journal.add_entry(self.state, self._draft.entry(self.state.world.time, msgs))
        finally:
            self._draft = None
            self._fight = None
        self._record_faction()
        self._save_season()
        return self._log(msgs)

    def free_text_request(self, text: str) -> FreeTextRequest | None:
        """隨口應對的階段 A（server.py 在行動鎖內、很快地呼叫）：眼前的事件可以隨口應對、寫的字是 1～20 字，
        就回傳要在鎖外送模型評估的單子；不行就是 None。只讀、不改狀態，也不推進戰鬥（理由同 dialogue_request）。"""
        text = text.strip()
        event_id = self.state.pending_event
        if not text or len(text) > FREE_TEXT_MAX or event_id is None:
            return None
        if FREE_TEXT_OPTION not in {o.id for o in self.options(odds=False, tick=False) if o.enabled}:
            return None
        return FreeTextRequest(event_id=event_id, text=text)

    def answer_event(self, request: FreeTextRequest, llm_rate: int | None = None) -> list[str]:
        """隨口應對的階段 C（鎖內）：重驗還停在同一則事件、寫的是同一句話，才算成功率、擲骰、套用效果。
        llm_rate 是鎖外評好的 0～100；沒給（直接呼叫的測試、腳本）就在這裡評（行動鎖內，用 _quick_client 的短逾時複本），
        評不到一樣退回 40。
        成功率＝LLM 評分加屬性修正、夾在 5～85（rules.free_text_rate）；擲骰用引擎自己的 rng。"""
        s, c = self.state, self.content
        self.last_gamble = None
        current = self.free_text_request(request.text)
        if current is None or current.event_id != request.event_id:
            return self._log(["（事情已經過去了，這句話沒派上用場。）"])
        event = c.events[request.event_id]
        choice = event.free_text
        if llm_rate is None:
            llm_rate = event_llm.assess_event_success_rate(self._quick_client(), event, request.text)
        self.state.battle_card = None
        faction_before = s.player.faction
        self._draft = Draft(f"{event.title}・隨口應對")
        try:
            s.pending_event = None
            rate = free_text_rate(llm_rate, choice, s, c, self.world)
            success = self.rng.random() * 100 < rate
            tag, line = check_result_line(success)  # 一律是本人：不寫誰出手
            msgs = [f"你：「{request.text}」（{rate_words(rate)}）", line]
            self._outcome(tag, line)
            effect = choice.effect if success else failed(choice.fail_effect, c)  # 失手另扣的體力減半（體力平衡提案）
            msgs += self._apply(effect)
            self._begin_enlistment(faction_before)  # 隨口應對的結果也可能拜入門派
            self._greet_rejoin(faction_before)  # 同樣：入伍段早就走完的人拜入門派，引薦人打個招呼（新手引導計畫三）
            msgs += check_thresholds(s, c, self.world, self._quick_client(), now=self.now)
            msgs += self._report_seat()  # 隨口應對的效果也可能推大勢、記貢獻：第四階席次的帳在這裡也抄（正式版丁）
            self._check_hints()  # 隨口應對了結了事件：同選項一樣，碰到的新玩法排一條、排著的上框（新手引導計畫三）
            journal.add_entry(s, self._draft.entry(s.world.time, msgs))
            self.last_gamble = FreeTextOutcome(
                event_id=event.id, text=request.text, success=success, effect_text=fill_marks(effect.text, s),
                time=s.world.time, title=self._draft.title,
            )
        finally:
            self._draft = None
        self._record_faction()
        self._save_season()
        return self._log(msgs)

    def add_gamble_narration(self, outcome: FreeTextOutcome, narration: str) -> None:
        """隨口應對的潤色（鎖外生成）插回那一則江湖紀錄：接在「你：「…」」那一行後面、結果文字前面。
        認不到那一則（紀錄已經被後來的事併掉或擠到後面）就不插，潤色本來就是錦上添花。"""
        journal_entries = self.state.journal
        if not narration or not journal_entries:
            return
        entry = journal_entries[0]
        if entry.time != outcome.time or entry.title != outcome.title:
            return
        lines = list(entry.lines)
        said = next((i for i, line in enumerate(lines) if line.startswith(f"你：「{outcome.text}」")), None)
        lines.insert(0 if said is None else said + 1, narration)
        journal_entries[0] = entry.model_copy(update={"lines": lines})

    # ── 有所感（悟意境設計第零節）────────────────────────────────

    def _sense(self, arg: str) -> list[str]:
        """有所感選單上的選擇：做法（數字）或「順其自然」（不畫了，落回做法那個基本意境）。「畫下來」在 choose 開頭就回了。"""
        s, c = self.state, self.content
        if arg == "let":
            req = sensing.request(s, c, self.world, None)
            return [req] if isinstance(req, str) else self._sense_apply(req, None)
        got = sensing.current(s, c)
        prologue = got is not None and got[1].prologue
        rng = prologue_rules.SureRandom() if prologue else self.rng  # 序章草廬：必中（悟意境設計第七節）
        return sensing.choose(s, c, int(arg), rng) if arg.isdecimal() else ["（此刻無法這麼做。）"]

    def sense_request(self, points: list | None, png: str = "") -> sensing.SenseRequest | str:
        """畫完那一筆的 A 段（server.py 在行動鎖內、很快地呼叫）：還在感悟狀態才開單；讀不出那一筆回一句話（字串）。
        只讀、不改狀態。單子的 needs_name 是 True 才要在鎖外叫模型看圖取名（insight_llm.name）。"""
        if self._preparing():
            return PREPARING_REFUSAL
        return sensing.request(self.state, self.content, self.world, points, png)

    def sense_draw(self, req: sensing.SenseRequest, proposed: tuple[str | None, str] | None = None) -> list[str]:
        """畫完那一筆的 C 段（鎖內）：重驗還是同一次感悟、同一筆讀出同一個屬性才套用（sensing.finish）。proposed 是鎖外取好的
        （名字, 說明）；沒給（整季機器人、腳本、測試）而且要取名，就在這裡用 _quick_client 只看文字特徵問一次，取不到走退路字表。
        悟成才寫江湖紀錄（標題「有所感・場景」，附上畫的那一筆）；對不上只回一句話。"""
        s, c = self.state, self.content
        got = sensing.current(s, c)
        if got is None or got[0].stage != "draw" or got[0].serial != req.serial:
            return self._log([sensing.STALE])
        self.state.battle_card = None
        self.state.player.guide_done = []
        self._draft = Draft(f"有所感・{got[1].title}")
        self._draft.glyph = list(req.points)
        try:
            msgs = self._sense_apply(req, proposed)
            self._check_hints()  # 畫完悟到意境（可能是第二個）：看一遍、排著的提示上框，記在這一則（新手引導計畫三；這條路不走 choose）
            journal.add_entry(s, self._draft.entry(s.world.time, msgs))
        finally:
            self._draft = None
        self._save_season()
        return self._log(msgs)

    def _sense_apply(self, req: sensing.SenseRequest, proposed: tuple[str | None, str] | None) -> list[str]:
        """畫完（或順其自然）之後真的悟：sensing.finish 改狀態；悟成就在這一處留一筆痕跡（一人一天只算一次）、序章那一段加旗標、
        記新手引導；悟到自己的新意境而且名字是模型取的，記全服的首悟紀錄（0.2b 第 5 點：第一個在這裡這樣悟到的人）。
        名字走退路字表的不記：伺服器假人不叫模型，記了就會露出「首悟者的名字都是字表風格」（同 2026-10-05 合成首創的決定）。"""
        s, c = self.state, self.content
        got = sensing.current(s, c)
        scene = got[1] if got is not None else None
        client = self._quick_client() if proposed is None else None
        msgs, own, by_model = sensing.finish(s, c, self.world, req, proposed, client)
        if msgs == [sensing.STALE]:
            return msgs
        add_marks({sensing.mark_key(req.location): 1}, s)
        if scene is not None and scene.flags_add:
            s.player.flags.update(scene.flags_add)
        if own is not None and by_model and self.world.claim_insight_first(
            sensing.first_key(req), own.name, s.player.name, c.locations[req.location].name, s.world.time,
        ):
            msgs.append(f"江湖上還沒有人在{c.locations[req.location].name}這樣悟過——你是第一個。")
        msgs += self._guide(note_action(s, c, self.world, "sense"))
        return msgs

    def _action_title(self, kind: str, arg: str) -> str:
        s, c = self.state, self.content
        if kind == "faction":
            if arg == "confirm":
                return f"投靠{self.content.scenario.faction(s.player.pending_faction).name}"
            if arg == "cancel":
                return "再想想"
            return f"考慮投靠{self.content.scenario.faction(arg).name}"
        if kind == "defect":
            if arg == "confirm":
                return f"叛投{self.content.scenario.faction(s.player.pending_defect).name}"
            if arg == "cancel":
                return "再想想"
            return f"考慮叛投{self.content.scenario.faction(arg).name}"
        if kind == "move":
            return f"前往 {c.locations[arg.partition(':')[0]].name}"
        if kind == "choice":
            event = c.events[s.pending_event]
            return f"{event.title}・{event.choices[int(arg)].text}"
        if kind == "talk":
            character = c.characters[s.player.pending_companion]
            return f"交談・{character.name}"
        if kind == "call":
            return "收回名帖" if arg == "back" else f"求見・{c.characters[arg].name}"
        if kind == "sense":
            scene = c.insight_scenes.get(s.player.sensing.scene) if s.player.sensing else None
            return f"有所感・{scene.title}" if scene else "有所感"
        if kind == "learn":
            return f"學藝・{c.skills[arg].name}"
        if kind == "fs":
            here = c.locations[s.player.location].name
            return "作罷" if arg == "leave" else f"{foreshadow.trip_label(s, c, arg.partition(':')[0])}・{here}"
        if kind == "road":
            what = arg.partition(":")[0]
            if what == "back":
                return atlas.journey_title(c, self._back_way().path)  # 折返：跟「前往」同一個標題，抵達時才併得進同一則
            return ROAD_TASKS[what][0]
        if kind == "opp":
            return opportunities.title(s, c, arg)
        if kind == "act" and arg.startswith("challenge:"):
            return f"挑戰・{figures.name_of(c, arg.partition(':')[2])}"
        rank_action = _rank_action_id(arg) if kind == "act" else None  # 第 3、4 階的行動（正式版戊一）寫它自己的名字
        if rank_action is not None:
            name = next(a.name for a in c.orders.rank_actions if a.id == rank_action)  # choose 已經驗過選項在選單上，一定找得到
            return f"{name}・{c.locations[s.player.location].name}"
        here = c.locations[s.player.location].name
        duty = c.orders.duties.get(s.player.faction or "")  # 守勢行動的標題寫陣營自己的名字（巡哨、傳道、保境安民）
        action2 = opportunities.rank2_action(s, c)  # 第 2 階行動的標題也寫它自己的名字（招降黃巾散兵、施符水收人心）
        titles = {
            "explore": f"探索{here}", "socialize": f"交友・{here}", "call": f"求見・{here}", "train": f"遊歷・{here}",
            "recruit": f"招募・{here}", "rest": f"打坐・{here}", "summons": f"應召・{here}", "stand": "起身", "halt": "喊停",
            "duty": f"{duty.name if duty else '守勢'}・{here}", "convoy": f"接下糧車・{here}",
            "rank2": f"{action2.name if action2 else '第二階行動'}・{here}",
        }
        return titles.get(arg, "提前出關")

    def _hide(self, msg: str) -> None:
        if self._draft is not None:
            self._draft.hide(msg)

    def _outcome(self, text: str, msg: str) -> None:
        if self._draft is not None:
            self._draft.outcome(text, msg)

    def _write(self, title: str, msgs: list[str], tag: str = "", guide: list[str] | None = None) -> None:
        draft = Draft(title, tag)
        draft.guide = list(guide or [])
        journal.add_entry(self.state, draft.entry(self.state.world.time, msgs))

    def _note_guide(self, notes: list[str]) -> None:
        """新手引導這次完成了（note_action 回傳的那幾行）：「✔ 引導完成」與獎勵記在 guide_done 給對話框。走完最後一步、
        有結語時對話框改顯示結語、等按「知道了」（引導重做設計 8.1）：那個旗標（guide_outro）由 note_action 在這一次真的走完最後一步時設——
        入伍段（新手引導計畫二）也會讓 notes 不是空的，不能再一有 notes 就把已經按掉的結語叫回來。"""
        if not notes:
            return
        heads = tuple(f"【{name}】" for name in guide_speakers(self.content))  # 每一步可以是不同的人說（新手引導計畫一）
        shown = [n for n in notes if not n.startswith(heads)]
        if shown:  # 只有引薦人的話（入伍段的 ✔ 在它的框不是框上那一個時不回傳）：框上原本的完成列不動
            self.state.player.guide_done = shown

    def _begin_enlistment(self, faction_before: str | None) -> None:
        """這一下才投靠的人開始入伍段（新手引導計畫二，設計 4.1）：動作之前還沒有陣營、現在有了（投靠，或拜入陣營名下的門派）。
        已經有陣營的人不開始——換版當下就投靠了的舊存檔不走入伍段（設計 7.2）、叛投也不重來（preflight F1，所以也不需要存檔遷移）。
        框換成引薦人：剛投靠這一下不算完成任何一步（Review Focus 1）——框上若還是說書人的步驟或結語，它們的「✔」照舊留著。"""
        if faction_before is not None or not enlist.begin_if_joined(self.state, self.content):
            return
        p = self.state.player
        if not tutorial_active(self.state, self.content) and not p.guide_outro:
            p.guide_done = []
        self._journal_guide(enlist.told(self.state, self.content))  # 引薦人迎你進營的話，記在這一則（設計 6.2）；不進「剛剛」、不進完成列

    def _greet_rejoin(self, faction_before: str | None) -> None:
        """第二季起再投靠：入伍段早就走完（所以不重走），引薦人只打個招呼（設計 7.1、10.6；話寫在 tutorial.json 入伍段的 rejoin）。
        這一下才從散人變成有陣營（叛投不算，faction_before 不是 None）、入伍段走完、沒略過引導、不是假人、沒關提示才有——
        第一次投靠走的是入伍段；略過的人沒有要誰帶，跟開季那一句（s_return）一樣不打招呼。走提示的佇列（hints.queue_note）：
        同樣上框、按「知道了」收起、記進江湖紀錄；每季都要說，所以不記進 hints_seen；by 記哪一邊，叛投時作廢。事件型的，當場排。"""
        p = self.state.player
        if faction_before is not None or p.faction is None or p.guide_skipped or not enlist.done(self.state, self.content):
            return
        who = enlist.recruiter(self.state, self.content)
        if who is not None and who.rejoin:
            hint_rules.queue_note(self.state, HintNote(id="s_rejoin", speaker=who.name, text=who.rejoin, by=p.faction))

    def _journal_guide(self, notes: list[str]) -> None:
        """引導的話記進江湖紀錄：在行動裡記進這一則的 guide；不在行動裡（例如打開輿圖）時接在最新一則的 guide。"""
        if self._draft is not None:
            self._draft.guide += notes
        else:
            journal.add_guide(self.state, notes)

    def _guide(self, notes: list[str]) -> list[str]:
        """新手引導的訊息不接進這次行動的訊息（「剛剛」只放行動的結果，引導重做設計 8.1.3）：記進這一則江湖紀錄的 guide、
        給對話框；不在行動裡（例如打開輿圖）時接在最新一則的 guide。回傳空串列，呼叫端照舊 `msgs += …`。"""
        rewards = [str(n) for n in notes if isinstance(n, HutReward)]  # 序章的獎勵：是這次行動的結果，不是對話框的一列
        notes = [n for n in notes if not isinstance(n, HutReward)]
        if notes:
            self._note_guide(notes)
            self._journal_guide(notes)
        if rewards and self._draft is None:  # 不在行動裡完成的（打開修練頁之類）：接在最新一則的引導後面
            journal.add_guide(self.state, rewards)
            return []
        return rewards

    def enlist_glow(self, option_ids: list[str]) -> list[str]:
        """入伍段「出一次力」那一步，選單上能完成它的那幾顆（FB-093，enlist.glow）；網頁讓它們發光。"""
        return enlist.glow(self.state, self.content, option_ids)

    def guide_box(self) -> dict | None:
        """行動列上方的對話框（引導重做設計 8.1、6.2）：引導還沒做完是目前這一步的話；剛走完、結語還沒按「知道了」是結語；
        其他（略過、早就做完的舊角色）是 None。done 是上一次行動完成的那幾行（✔ 與獎勵）。框上寫的人照這一步
        （TutorialStep.speaker），沒寫就是 Tutorial.speaker；這一步沒有話（序章第一步）時不畫框。
        還有事件待處理時，這一步的話換成「先把眼前的「事件名」了結」（每一步都一樣，步驟本身不動；結語照舊）。
        key 認的是「哪一步」（TutorialStep.id，結語是 "outro"），不看那一句話：網頁記玩家收起的那一步記的是它（FB-076）——
        事件的句子每遇到新事件就換一句，記句子的話收起的框每個新事件都會自己又展開。
        pending 標這一句是不是「先把眼前的「…」了結」：它只是重複底下事件卡片已經寫的話，展開時事件的最後一個選項被擠出第一屏，
        所以網頁預設把這一句收成一行（玩家沒按過「收起」也一樣；框上有要看的完成列〔done〕時不收；只有這一句，新的一步照舊展開，
        玩家仍可點開，FB-076）。結語永遠是 False。
        碰到才說（新手引導計畫三）排在最後：步驟 → 結語 → 入伍段（進行中或結尾）→ 提示，一次一條（_hint_box）。略過新手引導的人
        不畫前面那三段，但提示照樣有（設計 7.3：「不再提示」是另一個開關）。"""
        s, c, p = self.state, self.content, self.state.player
        t = c.tutorial
        todo = tutorial_steps(s, c)
        if self._preparing() or s.world.ended:  # 籌備中、休季什麼都不能做，不叫人去探索（FB-045～052 審查 I1）
            return None
        if p.guide_skipped:  # 略過的人不再畫引導的框，換季、第一季多出的步驟也一樣（8.1.4；畫面批次審查 I4）；提示不受影響
            return self._hint_box()
        if p.tutorial_step < len(todo):
            step = todo[p.tutorial_step]
            if not step.text or (prologue_rules.active(s, c) and (s.pending_event or s.player.sensing is not None)):
                return None  # 序章第一步（還沒遇到師父）、序章的事件或草廬四景的有所感端出來的時候：畫面就是那一張（新手引導計畫一）
            def fill(text: str) -> str:  # 序章的話裡的 {武學}：換成合成出來的那一門
                return prologue_rules.fill(text, s, c, self.world)

            # 眼前有事件還沒了結時是 guide.pending_line，不推這一步；了結後原樣回來（FB-063；「下一步」也用同一句）
            pending = pending_line(s, c) is not None
            box = {
                "speaker": guide_speaker_of(c, step), "key": step.id, "scene": fill(step.scene), "text": fill(step_text(s, c)),
                # 收起來那一行（網頁用 line || text）：待處理時話已經換成「先把眼前的「…」了結」，這一步自己的短提示不能留著
                # ——收著的框寫著短提示、跟事件擋著路互相矛盾（序章之外的步驟也可能有 line；序章自己在事件出現時整個框不畫，見上）
                "line": "" if pending else fill(step.line), "done": list(p.guide_done), "end": False, "pending": pending,
            }
            if step.paged:  # 話太長的序章步驟：網頁照空一行切成幾頁（只有分頁的步驟才帶這個鍵）
                box["paged"] = True
            return box
        if p.guide_outro and t.outro:
            return {
                "speaker": t.speaker, "key": "outro", "scene": "", "text": t.outro, "line": "", "done": list(p.guide_done), "end": True,
                "pending": False,
            }
        # 引導與結語都過去了：入伍段（新手引導計畫二），再來是碰到才說（計畫三）。順序固定是 步驟 → 結語 → 入伍段 → 提示，「知道了」只收框上那一個
        return enlist.box(s, c) or self._hint_box()

    def _hint_box(self) -> dict | None:
        """碰到才說的框：排著的第一條。眼前有事件或有所感還沒了結時不出（F3）：提示的框是 end 的、網頁不會收成一行，擺在事件的選項上面會把最後
        一個選項擠出第一屏（FB-076）；它排著等，事件了結之後上框。key 是那一條的 id，pending 永遠是 False；full：話不被切掉（設計 6.2）；
        hint：這是碰到才說的框（結語、入伍段的框沒有這個鍵）——網頁認它，在修練頁、煉製頁也畫（在那兩頁做的事觸發的提示不必切回江湖頁才看到）。"""
        p = self.state.player
        # 有所感（悟意境設計第零節）的卡也一樣：選做法、畫一筆都佔著畫面，跟事件待處理同一種等法
        if not p.hint_queue or self.state.pending_event is not None or p.sensing is not None:
            return None
        note = p.hint_queue[0]
        return {
            "speaker": note.speaker, "key": note.id, "scene": "", "text": note.text, "line": "", "done": [], "end": True,
            "pending": False, "full": True, "hint": True,
        }

    def _hint_up(self) -> HintNote | None:
        """對話框此刻顯示的就是排著的第一條提示（前面沒有引導的步驟、結語、入伍段，也沒有事件擋著）時，那一條；不然是 None。"""
        p = self.state.player
        if not p.hint_queue:
            return None
        box = self.guide_box()
        note = p.hint_queue[0]
        return note if box is not None and box["end"] and box["key"] == note.id else None

    def _surface_hint(self) -> None:
        """提示上框的那一刻（第一次）才算說過：記進 hints_seen、把說的話記進江湖紀錄（設計 6.2「說過的話都記進見聞」，控制者裁示 N1、N12）。
        排進佇列時還不算：前面有別的框、事件擋著、不再提示或換季把它清掉了，之後碰到還有機會聽到。冪等（一條只記一次），
        所以可以放心地在每個可能讓框換成提示的地方叫：排進去之後（_hint）、按「知道了」之後（下一條上框）、行動與同步的最後（事件了結、
        引導走完、入伍段走完）。在行動裡寫進這一則的 guide，不在行動裡（同步、按「知道了」）接在最新一則的 guide 後面。"""
        note = self._hint_up()
        if note is not None and hint_rules.show(self.state, self.content, note):
            self._journal_guide([f"【{note.speaker}】{note.text}"])

    def _hint(self, hint_id: str) -> None:
        """碰到某個玩法：排一條提示（序章裡不排，序章本身在教；新手引導計畫三）。說過的、已經排著的、關了提示的、假人都不排；
        輪得到上框就當場上框（_surface_hint）。"""
        if not prologue_rules.active(self.state, self.content):
            hint_rules.queue(self.state, self.content, [hint_id])
            self._surface_hint()

    def _refine_failed(self) -> bool:
        """有一門往下一品修練失敗過、還沒練成（art_mastery 記失敗幾次）：h_refine_fail 的條件。joy 的加難方案 C 衝絕學時，art_mastery
        記的是火候（cultivation._temper）：添火候不擲骰、不是失敗，不算（服丹強行衝關沒成也留著火候，那也沒有越修越容易，一樣不算）。"""
        s, c = self.state, self.content
        for art_id, count in s.player.art_mastery.items():
            art = team.resolve_art(art_id, c, self.world) if count > 0 else None
            if art is not None and not cultivation.heat_mode(c, martial_arts.next_quality(team.art_quality(s, art))):
                return True
        return False

    def _hint_triggers(self, only: set[str] | None = None) -> list[str]:
        """此刻成立的碰到才說（設計 5.2）：看的都是角色現在的狀態（修練失敗留下熟練度、戰報裡有一場沒打贏的、路上見聞真的發生過……），
        「第一次」由 hints_seen 管。順序照設計的表：師父的在前、引薦人的在後。h_snubbed（被名將打發）與 h_mandate（玉璽碎片的秘密
        揭開）不看狀態，是事件發生時自己叫 _hint，不在這裡。only 給了就只算裡面的條：_check_hints 只算書裡有、還沒說過、也還沒排著的，
        其餘每次行動與每次同步都是白算一遍（決戰要讀資料庫、大勢人物要算此刻的所在）。"""
        s, c, p = self.state, self.content, self.state.player

        def want(hint_id: str) -> bool:
            return only is None or hint_id in only

        on: list[str] = []
        if want("h_merge") and len(p.insights) >= 2:
            on.append("h_merge")
        if want("h_clash"):
            wugong = team.player_art(s, c, self.world, p.member.wugong_id) if p.member.wugong_id else None
            neigong = team.player_art(s, c, self.world, p.member.neigong_id) if p.member.neigong_id else None
            if wugong and neigong and martial_arts.counters(wugong.attribute, neigong.attribute):  # 相剋是一對一對的，兩個方向都一樣
                on.append("h_clash")
        if want("h_refine_fail") and self._refine_failed():  # 修練失敗才會累積熟練度，成功就歸零（往絕學添的火候不算）
            on.append("h_refine_fail")
        # 第一場沒打贏的仗：僵持與落敗都算（以前只算落敗：身法閃成僵持的人師父不開口）；決戰與挑戰本人不在這三種裡
        if want("h_lose") and any(r.tier not in team.WIN_TIERS for r in s.battles if r.kind in ("train", "wild", "event")):
            on.append("h_lose")
        if want("h_injury") and p.member.injury > 0:
            on.append("h_injury")
        # 「這裡能學新的底」：只算現在學得了的（learn 擋下的——名望、學費、門派、陣營、持有滿了——都不算，不然師父說能學、按下去卻是「學不了」）
        if want("h_basic_art") and any(problem is None for _, problem in library.lessons_here(s, c)):
            on.append("h_basic_art")
        if want("h_recruit") and self._recruit_target() is not None:
            on.append("h_recruit")
        if want("h_free_text") and s.pending_event:
            event = c.events.get(s.pending_event)
            if event is not None and event.free_text is not None:
                on.append("h_free_text")
        if want("h_road") and p.recent_sights:  # 路上見聞真的發生過才會記
            on.append("h_road")
        if want("h_cap") and library.held_count(s) >= library.cap_of(s, c) - 5:
            on.append("h_cap")
        status = self._battle_status(tick=False) if want("h_spectator") or want("h_showdown") else None
        watching = status is not None and self._watching_battle(*status)
        # 散人只在決戰所在的大區才說（N3）：_watching_battle 對散人在集結時永遠是 True，人在別處不算「遇上」
        if want("h_spectator") and status is not None and p.faction is None and watching and self._at_battle(status[1]):
            on.append("h_spectator")
        if want("h_foreshadow") and any(p.fragments.values()):
            on.append("h_foreshadow")
        if want("h_event_reveal") and p.events_seen:
            on.append("h_event_reveal")
        if want("h_promotion") and p.summons is not None:
            on.append("h_promotion")
        if want("h_showdown") and status is not None and p.faction is not None and status[0].phase == "muster" and not watching:
            on.append("h_showdown")
        # 大勢人物本人（人物表上的人，第一季的規則開著才有）：不是「這裡有可以交友的人物」（_figures_here 連陶謙、曹操、劉備也列，F1）
        if want("h_figure") and season_one(c, s.world) and figures.present_at(s, c, p.location):
            on.append("h_figure")
        return on

    def _queue_triggered_hints(self) -> None:
        """成立的狀態提示排一條進佇列（N2，控制者裁示）：同一時間最多一條狀態提示在框上或排著——佇列裡還有一條沒按「知道了」的狀態提示時，
        不管是行動還是同步都不再排新的（伺服器每個動作都是先 sync 再做動作，兩次檢查各排一條就變成連著兩個框；人閒著不動、
        同步每十秒問一次也不會排成一長串）；按過「知道了」之後的下一次檢查，條件還成立才排下一條（開局一排「知道了」是引導重做
        要拿掉的）。事件型的（h_snubbed、h_mandate、開季那一句、再投靠的招呼）當場排，不吃這個限速，也不算在裡面。
        排不進去的（散人碰到沒有散人版的陣營提示）不算名額，接著看後面的。不看的時候：假人、關了提示、籌備中與休季（框不畫，
        排進去就算說過會白白丟掉，F7）、序章。"""
        s, c, p = self.state, self.content, self.state.player
        if p.bot or p.hints_off or any(n.id in hint_rules.STATE for n in p.hint_queue):
            return
        # 只算書裡有的狀態提示（事件型的不看狀態，留在 waiting 裡也沒東西可算，只會讓下面的提早返回永遠用不上），還沒說過、也還沒排著的（N10）
        waiting = {h.id for h in c.hints.hints if h.id in hint_rules.STATE} - p.hints_seen
        if not waiting or self._preparing() or s.world.ended or prologue_rules.active(s, c):
            return
        for hint_id in self._hint_triggers(waiting):
            queued = len(p.hint_queue)
            hint_rules.queue(s, c, [hint_id])
            if len(p.hint_queue) > queued:
                return

    def _check_hints(self) -> None:
        """每次行動、修練頁與配點的動作、出發、同步做完之後看一遍（新手引導計畫三）：該說的排進佇列，輪到的上框（_surface_hint）。
        呼叫的位置都在記進江湖紀錄之前，說的話才記在這一次行動那一則。"""
        self._queue_triggered_hints()
        self._surface_hint()

    def set_hints_off(self, value: bool) -> None:
        """設定頁的「不再提示」：打開時排著的清掉（沒上過框的不算說過，關掉再打開還聽得到）；對話框的引導與入伍段不受影響。"""
        self.state.player.hints_off = bool(value)
        if value:
            self.state.player.hint_queue = []

    def guide_ack(self) -> list[str]:
        """對話框的「知道了」：只收框上看得到的那一個（順序見 guide_box）——提示就是排著的第一條（接著下一條上框）；結語還沒按、入伍段
        已經走完時，按下去是結語，入伍段的結尾留到下一個框（F8）；引導的步驟還在框上時沒有「知道了」可按，什麼都不收。
        收之前先讓框上的提示上框（_surface_hint）：框是別的狀態改變（引導走完、事件了結）讓它輪到的、還沒有任何呼叫把它記成說過時，
        不能憑空吞掉一條（記說過、記進江湖紀錄都要在它被收掉之前）。"""
        p = self.state.player
        self._surface_hint()
        if self._hint_up() is not None:
            p.hint_queue.pop(0)
        elif p.guide_outro:
            p.guide_outro = False
        elif not tutorial_active(self.state, self.content):
            p.enlist_end = False
        p.guide_done = []
        self._surface_hint()  # 結語、入伍段的結尾、上一條提示收掉之後，後面等著的提示輪到上框
        return []

    # ── 行動 ──────────────────────────────────────────────

    def _action_costs(self) -> dict[str, int]:
        """各行動花的體力：照 Config.action_cost，身上帶【輕身】時遊歷（含挑戰本人）少花一點（武學與成長設計 13.4）。
        按鈕上寫的與真的扣的都讀這一個。"""
        costs = dict(self.content.config.action_cost)
        light = traits.loadout(self.state, self.content, self.world).specials.get("train_stamina")
        if light is not None:
            costs["train"] = max(0, costs["train"] - int(light.amount))
        return costs

    def _act(self, what: str, prepared: companion_agent.PreparedTurn | None = None) -> list[str]:
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
        if what == "duty":
            return self._duty()
        if what == "rank2":
            return self._rank2()
        action_id = _rank_action_id(what)  # 第 3、4 階的行動（正式版戊一）
        if action_id is not None:
            return self._rank_action(action_id)
        if what == "convoy":
            return self._take_convoy()
        if what == "call":
            self.state.player.picking_audience = True  # 打開求見選單（見 _audience_options），不花體力
            return [f"你遞上名帖，準備求見{self.content.locations[self.state.player.location].name}的人物。"]
        if what.startswith("challenge:"):
            return self._challenge(what.partition(":")[2])
        promotion = ranks.summons_event(self.state, self.content)
        if what == "summons":
            return self._present(self.content.events[promotion])
        self.state.player.stamina -= self._action_costs()[what]  # 不花體力的行動（上面那些）不必算（要翻武學的資料）
        if promotion is not None and what in ("explore", "socialize"):  # 在召見的地點探索、交友：端出晉升奇遇（計畫 T5）
            return self._present(self.content.events[promotion])
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
        return self._encounter("socialize", self._no_audience_line)  # 惰性：抽到事件就不挑打發話、不白花亂數

    def _foreshadow(self, arg: str) -> list[str]:
        """伏筆的最後一步（計畫 T7）：fs:<鏈> 看題（沒有題的直接做）、fs:<鏈>:<選項> 答題、fs:leave 作罷。"""
        if arg == "leave":
            return foreshadow.leave(self.state)
        chain_id, _, option_id = arg.partition(":")
        return foreshadow.attempt(
            self.state, self.content, chain_id, option_id or None, self.state.world.time, self.rng, self.world,
        )

    def _hear_after_stamina(self, before: float) -> list[str]:
        """每次花體力的行動之後抽一次伏筆片段（計畫 T7）：選單的每一個行動（choose）與輿圖的安排前往（travel）都經過這裡，
        體力比行動前少了才抽（探索、遊歷、交友、求見、對話、招募、趕路、疾行；打坐、步行、生成不出對話退回體力的都不算）。
        抽的是行動後所在地點的大區；沒有伏筆在跑（開關關著、沒有鏈）就什麼都不做。
        伏筆先抽、天時地利型機緣的線索（正式版乙一）後抽：伏筆的擲骰順序不變。
        序章（新手引導計畫一）在草廬裡什麼都不抽：那是真實世界的事。"""
        s, c = self.state, self.content
        if s.player.stamina >= before or prologue_rules.active(s, c):
            return []
        region = atlas.region_of(c, s.player.location)
        region_id = region.id if region is not None else None
        msgs = foreshadow.hear_after_action(s, c, region_id, self.rng, self.world) if foreshadow.active(s, c) else []
        if opportunities.active(s, c):  # 天時地利型機緣的線索（正式版乙一）
            msgs += opportunities.hear_clues(s, c, region_id, self.rng, world=self.world)  # 內鬼的特徵要讀本季天機
        return msgs

    def _call(self, arg: str, prepared: companion_agent.PreparedTurn | None = None) -> list[str]:
        """求見選單上的選擇：「返回」收起選單；選了一位人物就跟他開口對話，跟交友碰上人物時一模一樣——
        花交友的體力、生成不出對話就退回（見 _open_dialogue）。福緣不在這裡發：指名求見就是要見這個人
        （福緣照舊由交友先發，或到期自己送上門，見 _advance_player_local）。
        門檻不夠（名望與階級都不到、也沒結識過）就被打發：不花體力、不叫模型，見 _brush_off。"""
        self.state.player.picking_audience = False
        if arg == "back":
            return ["你收回名帖，暫且不求見了。"]
        if not self._can_meet(arg):
            return self._brush_off(arg)
        self.state.player.stamina -= self.content.config.action_cost["socialize"]
        return self._open_dialogue(arg, prepared)

    def _open_dialogue(self, companion_id: str, prepared: companion_agent.PreparedTurn | None) -> list[str]:
        """跟一位大勢人物開口對話（呼叫端已經扣了交友的體力）：生成不出對話時退回那份體力，對話不開始。"""
        try:
            return companion_agent.start_dialogue(
                self._quick_client(), self.state, self.content, self.world, companion_id, self.rng,
                turn=self._prepared_turn(prepared),
            )
        except companion_agent.DialogueUnavailable:
            self.state.player.stamina += self.content.config.action_cost["socialize"]  # 生成不出對話：這次不花體力
            return self._dialogue_unavailable(companion_id)

    def _explore(self) -> list[str]:
        """探索三選一（FB-013，docs/superpowers/specs/2026-10-03-探索三選一-design.md）。

        1. 奇遇判定最優先：這裡有還能遇上的一次性或奇遇事件時，先滾 `rare_explore_chance`，中了就是它。
        2. 沒中就照地點類型（`Config.explore_mix`）的比例抽悟意境、野怪、事件三支之一；做不了的那一支
           （沒有會打的對手、沒有可重複的事件）從候選裡拿掉，用剩下的比例重抽——等於把它的比例按比例分給另外兩支。
        3. 三支都做不了才是一無所獲。
        4. 不論走哪一支，結束後再擲一次有沒有撿到破境丹（`_legend_find`）。

        以前是「先滾三成素材，再一定撞到一個事件」：40 個地點有 38 個探索 100% 跳事件，荒郊野外跟
        城裡的手感一樣（QA 量過）。奇遇事件只走第 1 步、不進事件那一支，所以一直是稀有的。
        """
        if prologue_rules.active(self.state, self.content):
            return self._explore_outcome()  # 序章裡不撿破境丹（新手引導計畫一）
        return self._explore_outcome() + self._legend_find()

    def _legend_find(self) -> list[str]:
        """探索不論走哪一支，結束後擲一次有沒有撿到破境丹（企劃者 2026-10-05：到處探索都有約 2% 的機會）。
        機率是 0 就不擲骰（先判斷機率，亂數序列一個都不動：測試內容把它設成 0，既有的固定種子序列才不會位移）。
        兩行：「獲得」開頭的敘事（江湖紀錄給它掃光，journal._NEW_THING）與「破境丹 +1」（寫進紀錄的數值變化）。"""
        cfg = self.content.config
        if cfg.explore_legend_chance <= 0 or self.rng.random() >= cfg.explore_legend_chance:
            return []
        self.state.player.legend_items += 1
        return [f"獲得 【{cfg.legend_item_name}】一枚——{cfg.legend_item_note}", f"{cfg.legend_item_name} +1"]

    def _explore_outcome(self) -> list[str]:
        s, c = self.state, self.content
        loc = c.locations[s.player.location]
        sight = prologue_rules.explore_event(s, c)
        if sight is not None:  # 序章第 3 步：草廬四景四選一（新手引導設計 3.2），不抽奇遇、不分三支
            return self._present(c.events[sight], "explore")
        scene = prologue_rules.explore_scene(s, c)
        if scene is not None:  # 序章第 3 步的有所感版（悟意境設計第七節）：草廬四景就是四個做法，都對、必中
            return sensing.start(s, c, c.insight_scenes[scene], self.rng)
        if event_candidates(s, c, "explore", "rare") and self.rng.random() < c.config.rare_explore_chance:
            return self._present(pick_event(s, c, "explore", self.rng, "rare"), "explore")
        mix = c.config.explore_mix_of(loc.tags).weights
        branches = [b for b in EXPLORE_BRANCHES if mix.get(b, 0) > 0 and self._explore_can(b, loc)]
        if not branches:
            return ["你四處走走，一無所獲。"]
        # 悟性：落在「悟意境」那一支的比重 ×（1＋3%×（悟性−5））；另外兩支不動（武學與成長設計 6.1）
        wis = team.stat_factor(c, s.player.stats.get("wis", team.BASE_STAT))
        branch = self.rng.choices(branches, weights=[mix[b] * (wis if b == "insight" else 1) for b in branches])[0]
        if branch == "insight":
            if sensing.can_sense(s, c, loc):  # 有場景：有所感，要選做法、畫一筆才悟得到（悟意境設計第零節）
                return sensing.start(s, c, sensing.pick_scene(loc, c, self.rng), self.rng)
            found = insights.roll_explore(loc, c, self.rng)  # 沒有場景的內容（測試內容）照舊直接悟
            return [f"你在{loc.name}靜下心來，看了好一陣。"] + insights.learn(s, c, self.world, found)
        if branch == "wild":
            squad = min(self._wild_foes(loc), key=lambda foe: foe.difficulty)  # 同分取這裡列的第一路
            return [f"你在{loc.name}走著，{squad.name}突然殺出！"] + self._squad_encounter(squad.id, wild=True)
        return self._present(pick_event(s, c, "explore", self.rng, "common"), "explore")

    def _explore_can(self, branch: ExploreBranch, loc: Location) -> bool:
        """探索三選一的這一支在這裡做不做得了。"""
        if branch == "insight":
            if sensing.missed_today(self.state, loc):
                return False  # 今天在這裡選錯過做法：這裡今天悟不出什麼（Q2）
            return bool(insights.explore_gives(loc, self.content))  # 輿圖詳情欄「這裡能悟」用同一個判斷（W3）
        if branch == "wild":
            return bool(self._wild_foes(loc))
        return bool(event_candidates(self.state, self.content, "explore", "common"))

    def _wild_foes(self, loc: Location) -> list[Squad]:
        """探索時可能殺出來的野怪：這裡的敵人裡不是自己陣營的那幾路（自己人不會突然殺出來，也不在這裡操練）。"""
        squads = [self.content.squads[sid] for sid in loc.enemies]
        return [squad for squad in squads if not self._drills_with(squad)]

    def _train(self) -> list[str]:
        """遊歷：找這個地點的敵人打一場，**必定開打**；打完有機率接一段戰後的餘韻事件。

        這個行動在 sanguo-companions 合併時被整個移除，後果是整條隨機遭遇戰的路斷掉：
        `pick_event()` 只在「完全沒有合格候選」時才回 None，而有三個事件是「任何地點、
        可重複、探索觸發」，所以實測 22 個地點探索都是 100% 撞到事件，掛在 explore 後面的
        遭遇戰分支一次都沒執行過（整季只有劇情事件的 combat 選項那 3 場）。

        打完之後的 `train_event_chance` 機率是給 `actions: ["train"]` 的事件用的——「拆招頓悟」
        與「錦衣少年」的文字本來就是戰後餘韻（「一番苦戰之後…」「打鬥剛歇…」），合併時被改掛
        到 explore，於是在集市散步也會冒出來。現在它們回到正確的位置。
        """
        loc = self.content.locations[self.state.player.location]
        # 池子裡有大場面的對手：照 _train_pick 挑，跟按鈕、備料、套用、判讀失敗的退路都是同一路（鎖外判讀過的單子就是它，
        # _squad_encounter 照對手對上判讀）；沒有就照舊用 Game.rng 隨機挑——正式內容每一處都是這樣（Task 2 審查修正 3）
        if self._big_trip(loc):
            squad = self._train_pick(loc)
        else:
            squad = self.content.squads[self.rng.choice(self._train_squad_ids(loc))]
        msgs = self._squad_encounter(squad.id)
        if prologue_rules.active(self.state, self.content):
            return msgs  # 序章裡打完不接戰後事件（新手引導計畫一）
        if self._drills_with(squad):
            return msgs  # 操練沒有打架，不接「一番苦戰之後」這類戰後事件（試玩回饋 FB-001）
        if self.rng.random() < self.content.config.train_event_chance:
            event = pick_event(self.state, self.content, "train", self.rng)
            if event is not None:
                msgs += self._present(event, "train")
        return msgs

    def _train_squad_ids(self, loc: Location) -> list[str]:
        """遊歷可能遇上的對手：地點的敵人，加上軍令帶來的（截糧時那一帶的敵方運糧隊，計畫 T6）。
        開關關著、沒有截糧軍令時就是 loc.enemies 本身，亂數的抽法跟以前一樣。
        序章（新手引導計畫一）：只有這一步寫的對手（雪恥那一步才有斷眉），草廬自己沒有敵人。"""
        if prologue_rules.active(self.state, self.content):
            return prologue_rules.enemies(self.state, self.content)
        extra = orders.extra_enemies(self.state, self.content, loc.id, self.state.player.faction)
        return loc.enemies + [sid for sid in extra if sid not in loc.enemies] if extra else loc.enemies

    def _order_options(self, loc: Location) -> list[Option]:
        """軍令的兩個行動（計畫 T6）：在有戰線的地方做第 1 階守勢行動；在護糧的起點接糧車。開關關著、散人沒有。"""
        s, c = self.state, self.content
        p = s.player
        if not orders.active(s, c) or p.faction is None:
            return []
        opts: list[Option] = []
        duty = c.orders.duties.get(p.faction)
        if duty is not None and front_of(c, loc.id) is not None:
            opts.append(self._cost_option("act:duty", duty.name, c.config.duty_stamina))
        escort = orders.escort_at(s, c, p.faction, loc.id)
        if escort is not None and p.convoy is not None:  # 一次押一車：寫明手上那一車要送去哪（T6 審查 I3）
            dest = c.locations[p.convoy.to_loc].name
            opts.append(Option(id="act:convoy", enabled=False, label=f"接下糧車（你還押著一車糧，要送到{dest}）"))
        elif escort is not None:
            need, have = c.config.convoy_grain, materials.grain_of(s, c)
            dest = c.locations[escort.end].name
            if have < need:
                opts.append(Option(
                    id="act:convoy", enabled=False,
                    label=f"接下糧車（送到{dest}・糧草不夠：要 {need} 份，你有 {have} 份；糧草是慢屬性的素材）",
                ))
            else:
                used = "、".join(f"{c.materials[mid].name} ×{n}" for mid, n in materials.grain_plan(s, c, need))
                opts.append(Option(id="act:convoy", label=f"接下糧車（送到{dest}・交出糧草 {need} 份：{used}）"))
        return opts

    def _rank2_options(self, loc: Location) -> list[Option]:
        """第 2 階行動（設計 5.5；正式版乙一）：第 2 階以上、在有戰線的地方；今天做滿了就變灰、寫明。"""
        s, c = self.state, self.content
        action = opportunities.rank2_action(s, c)
        if action is None or front_of(c, loc.id) is None:
            return []
        if opportunities.rank2_left(s, c) <= 0:
            return [Option(id="act:rank2", enabled=False, label=f"{action.name}（今天已經做滿 {c.config.rank2_daily} 次）")]
        note = self._check_cost_note(action.check, c.config.rank2_stamina)
        return [self._cost_option("act:rank2", action.name, c.config.rank2_stamina, note=note)]

    def _check_cost_note(self, check: Check | None, cost: int) -> str:
        """有檢定的行動（第 2 階行動、第 3 階煽動起事）括號裡體力後面接的那一段：照事件選項的寫法寫檢定（企劃者裁決 E5.3：
        「{行動}（體力 N・{屬性名} {數值}：{心裡話}）」，標籤的樣子待 joy 潤）。體力不夠時不寫（審查 I1）：這些行動在「此地還能做」
        裡，網頁照原文印灰掉的標籤，帶著心裡話會讀成是屬性不夠才灰的，所以照舊只寫「{行動}（體力 N）」。沒有檢定是空字串。"""
        if check is None or self.state.player.stamina < cost:
            return ""
        return event_rules.check_note(check, self.state, self.content, self.world)

    def _rank2(self) -> list[str]:
        """做一次第 2 階行動：扣體力、記今天一次；過檢定才成功——成功往己方推所在戰線 rank2_push 點（push_trend），
        再替累積型的機緣記一次。軍令的記功是計畫戊的事。"""
        s, c = self.state, self.content
        p = s.player
        action = opportunities.rank2_action(s, c)
        loc = c.locations[p.location]
        front = front_of(c, loc.id)
        p.stamina -= c.config.rank2_stamina
        opportunities.count_rank2(s, c)
        if not roll_check(action.check, s, c, self.world, self.rng):
            return [action.fail.replace("{地點}", loc.name)]
        msgs = [action.ok.replace("{地點}", loc.name)]
        goal = self._goals().get(front)
        if goal:
            msgs += self.push_trend(front, goal * c.config.rank2_push, source="rank2")
        return msgs + opportunities.after_success(s, c, "rank2", loc.id, self.rng)

    def _rank_action_options(self, loc: Location) -> list[Option]:
        """第 3、4 階的行動（正式版戊一）：做得了（陣營、階；第 4 階是這一週在任）、這裡做得了（戰線、標籤、亂局）才出現，
        不是按了才說不行；這週做滿就灰掉、寫明。這個行動推的那條線今天已經推滿（每人每曆日上限，按下去只會推 +0）也灰掉、
        寫明（企劃者裁決 E1）；一次只寫一個原因，這週做滿先寫。還推得動一點的照常按、照常付。choose 照這份選單重驗，
        所以推滿之前拿到的舊選單按下去也一樣被拒絕、不扣體力、不記次數。"""
        s, c = self.state, self.content
        opts: list[Option] = []
        line = self._rank_action_line(loc.id)
        for action in rank_actions.mine(s, c):
            if not rank_actions.where_ok(s, c, action, loc.id):
                continue
            option_id = f"{RANK_ACTION_PREFIX}{action.id}"
            if rank_actions.left(s, c, action) <= 0:
                opts.append(Option(id=option_id, enabled=False, label=f"{action.name}（這週已經做滿 {action.weekly} 次）"))
            elif line is not None and self._push_room(line) <= 0:
                opts.append(Option(id=option_id, enabled=False, label=f"{action.name}（今天這條線已經推滿）"))  # 新寫，待 joy 潤
            else:  # 有檢定的（煽動起事）照事件選項的寫法接在體力後面，體力不夠時不寫（裁決 E5.3、審查 I1，同 _rank2_options）
                note = self._check_cost_note(action.check, action.stamina)
                opts.append(self._cost_option(option_id, action.name, action.stamina, note=note))
        return opts

    def _rank_action_line(self, loc_id: str) -> str | None:
        """第 3、4 階行動在這裡推哪一條線：自己陣營有割據的目標就推割據（豪強的修築塢堡、占據郡縣），否則推所在的戰線
        （黃巾的煽動起事）；都沒有目標是 None（不推）。選單看推滿了沒、_rank_action 真的推，都照這一個判斷。"""
        goals = self._goals()
        if goals.get(GEJU):
            return GEJU
        front = front_of(self.content, loc_id)
        return front if front is not None and goals.get(front) else None

    def _push_room(self, trend_id: str) -> float:
        """自己今天在這條線上還推得動多少（每人每曆日上限，緩衝後的量）：跟 push_trend 走 push.py 的同一個算法（push.room）。
        第一季的規則沒開時 push_trend 不設上限，這裡也是無限。"""
        s, c = self.state, self.content
        if not calendar.season_one_on(s.world, c):
            return math.inf
        day = calendar.point(s.world.time, c, s.world).cal_day
        return push.room(s.player.pushed, day, trend_id, c.config.daily_push_cap)

    def _rank_action(self, action_id: str) -> list[str]:
        """做一次第 3、4 階的行動：扣體力、記這週一次（不論成敗）；有檢定的過了才算——推動走 push_trend（黃巾推所在戰線往己方，
        豪強推割據，都乘自己陣營的目標），再替軍令記功（第 3 階 5 次、第 4 階 10 次；收哪幾種由計畫戊二定，現在沒有軍令收，記不到）。
        choose 已經驗過選項在選單上，所以 mine 裡一定找得到。"""
        s, c = self.state, self.content
        p = s.player
        action = next(a for a in rank_actions.mine(s, c) if a.id == action_id)
        loc = c.locations[p.location]
        front = front_of(c, loc.id)
        p.stamina -= action.stamina
        rank_actions.count(s, c, action)
        if action.check is not None and not roll_check(action.check, s, c, self.world, self.rng):
            return [action.fail.replace("{地點}", loc.name)]
        msgs = [action.ok.replace("{地點}", loc.name)]
        line = self._rank_action_line(loc.id)
        if line is not None:
            msgs += self.push_trend(line, self._goals()[line] * action.push, source="rank")
        return msgs + self._order_credit(kind=action.id, location=loc.id, front=front, weight=rank_actions.weight(action))

    def _order_credit(self, **kw) -> list[str]:
        """替自己記一次軍令（orders.credit）；真的記到了就推新手引導的「完成一次軍令的個人部分」（計畫 T6 Task 8）。
        達成時陣營軍情列的前三名一律寫名號（傳聞分層第七節：陣營軍情一律具名），所以不給 shown。"""
        s, c = self.state, self.content
        msgs = orders.credit(s, c, s.player.faction, s.player.name, **kw)
        if msgs:
            msgs += self._guide(note_action(s, c, self.world, "order"))
        return msgs

    def _duty(self) -> list[str]:
        """第 1 階守勢行動（官軍巡哨、黃巾傳道、豪強保境安民；軍令文件 3.2、濃縮版內容表 2.6）：體力 duty_stamina，
        往己方推所在戰線 1 點（豪強在亂局時推割據，不在亂局什麼都不推），算守城的個人部分。推力走 push_trend
        （緩衝、上限、貢獻）。"""
        s, c = self.state, self.content
        p = s.player
        loc = c.locations[p.location]
        duty = c.orders.duties[p.faction]
        front = front_of(c, loc.id)
        p.stamina -= c.config.duty_stamina
        text = duty.text.replace("{地點}", loc.name)
        msgs = [text]
        goals = self._goals()
        if goals.get(front):
            msgs += self.push_trend(front, goals[front], source="duty")
        elif goals.get(GEJU) and in_chaos(s, c, front):
            msgs += self.push_trend(GEJU, 1, source="duty")
        msgs += opportunities.after_success(s, c, "duty", loc.id, self.rng)  # 收容流民（正式版乙一）
        credit = self._order_credit(kind="duty", front=front)
        # 入伍段第 2 步「出一次力」：守勢行動不在這週軍令裡也算（FB-094：豪強第一週只有打擊，新人打不過；FB-093：巡哨、傳道就在營裡）
        return msgs + (credit or self._guide(note_action(s, c, self.world, "order")))

    def _take_convoy(self) -> list[str]:
        """接下糧車（護糧，軍令文件 3.4）：交出 convoy_grain 份糧草（從低階的慢屬性素材用起，多的不找），記下要送到哪裡。
        不花體力；抵達終點才算數（見 _convoy_arrives）。"""
        s, c = self.state, self.content
        p = s.player
        escort = orders.escort_at(s, c, p.faction, p.location)
        need = c.config.convoy_grain
        if escort is None or p.convoy is not None or not materials.take_grain(s, c, need):
            return ["（這裡沒有糧車可接。）"]
        p.convoy = Convoy(order=escort.id, grain=need, from_loc=p.location, to_loc=escort.end)
        text = f"你把 {need} 份糧草裝上車，要送到{c.locations[escort.end].name}。路上當心截糧的。"
        return [text]

    def _convoy_arrives(self, loc_id: str) -> list[str]:
        """糧車到了終點（路過也算）：先有 convoy_ambush_chance 機率撞上敵方截糧隊（探索撞上野怪的打法：不推大勢、
        扣氣血打折），打輸糧車被劫、不算數；打贏或沒遇上就交進營中——記捐獻（軍備文件 4.1）、記一次推動的貢獻、
        替它自己那一道護糧記一次（RF4：已經換週清掉就不算）。"""
        s, c = self.state, self.content
        p = s.player
        convoy = p.convoy
        if convoy is None or convoy.to_loc != loc_id:
            return []
        p.convoy = None
        msgs: list[str] = []
        enemy = orders.ambusher(c, p.faction)
        if enemy is not None and self.rng.random() < c.config.convoy_ambush_chance:
            msgs.append("快到營門時，半路殺出一隊截糧的人馬！")
            msgs += self._squad_encounter(enemy, wild=True)
            if s.battles[0].tier not in team.WIN_TIERS:
                return msgs + ["糧車被劫走了，這一趟不算數。"]
        key = f"{loc_id}:糧草"
        p.donations[key] = p.donations.get(key, 0) + convoy.grain
        # 護糧沒有推動，另記一次第 1 階推動的貢獻（總計畫 T6）
        push.add_contribution(p, orders.week_of(s, c), c.config.contrib_per_push)
        msgs.append(f"糧車送進了{c.locations[loc_id].name}，一粒不少。")
        return msgs + self._order_credit(kind="convoy", location=loc_id, front=front_of(c, loc_id), order=convoy.order)

    def _rest(self) -> list[str]:
        """坐下來打坐（地圖擴充設計第二節）：進入「打坐中」，之後時間過去時體力回復是平常的
        rest_regen_multiplier 倍；期間不能做別的事，隨時可以起身。跟閉關同一種做法：狀態記在玩家身上，
        回復由 _advance_player_local 照經過的時間算，不碰共用賽季時鐘。原本按一下立刻補一個時辰的回復、
        又不延後自然回復，連按就能無限回體力。選單上永遠有這個選項、不受體力門檻限制——實機 playtest
        發現過體力歸零後整排按鈕都按不下去、新玩家卡死的情況。"""
        line = prologue_rules.instant_rest(self.state, self.content)
        if line:  # 序章第 7 步：一坐就回滿，不用等（新手引導設計 3.1）
            self.state.player.stamina = float(self.content.config.stamina_max)
            return [line]
        self.state.player.resting_since = self.state.world.time
        multiplier = self.content.config.rest_regen_multiplier
        return [f"你就地坐下打坐，體力回復是平常的 {multiplier:g} 倍；隨時可以起身。"]

    def _stand_up(self, full: bool = False) -> list[str]:
        """起身：打坐結束，體力回復恢復平常的速度。按「起身」時寫在這次行動的紀錄裡；體力回滿自己起身
        （sync／advance 裡，沒有進行中的行動）或加入戰局時起身，另寫一則「起身」。"""
        p = self.state.player
        minutes = max(0, round((self.state.world.time - p.resting_since) / 60))
        p.resting_since = None
        if full:
            msg = "體力已經回滿，你收功起身。"
        elif minutes < 1:  # 剛坐下就起身：不寫「打坐了約 0 分鐘」（FB-049）
            msg = "你收功起身。"
        else:
            msg = f"你收功起身（打坐了約 {minutes} 分鐘）。"
        if self._draft is None:
            self._write("起身", [msg])
        return [msg]

    def _figures_here(self) -> list[str]:
        """這個地點的大勢人物（不管見不見得到）：可招募的 7 位在 recruit_at，鎖定的龍頭人物在 talk_at（不可招募，見
        「還要改進」第 5 點）。第一季的規則開著時，人物表上的人照他此刻的所在與狀態（figures.placed_characters，T4）：
        轉往冀州的皇甫嵩、到任的董卓在盧植營；下獄、退場、重創的不在任何地方。規則沒開時一個字都不變。"""
        s, c = self.state, self.content
        here = s.player.location
        placed = figures.placed_characters(s, c)
        return [
            cid for cid, ch in c.characters.items()
            if ch.deep_interaction and (placed[cid] == here if cid in placed else here in (ch.recruit_at, ch.talk_at))
        ]

    def _can_meet(self, companion_id: str) -> bool:
        """見得到這位人物：名望到了他的求見門檻，或是透過他的「結識」事件認識過（企劃者 2026-10-02 決定）。
        判斷在 rules.can_meet，伏筆的偷聽也用它。"""
        return can_meet(self.state, self.content, companion_id)

    def can_meet_figure(self, companion_id: str) -> bool:
        """見得到這位人物嗎（名望與陣營階級、或結識過）；機器人用來避開會被打發的求見。"""
        return self._can_meet(companion_id)

    def _fame_gap(self, companion_id: str) -> int:
        """離這位人物的求見門檻還差多少名望（門檻已含同陣營的階級折抵，見 rules.audience_bar）；見得到時不會拿來用。"""
        return audience_bar(self.state, self.content, companion_id) - self.state.player.stats.get("fame", 0)

    def _brush_off(self, companion_id: str) -> list[str]:
        """門檻不夠時被打發（武學與成長設計 9.1）：他自己口吻的一句（內容沒寫就用通用的），附上還差多少。
        後面只在「第一季的規則開著（才有晉升）、真的有下一階可升（會升階的：第 4 階只是資格，不算）、而且升一階抵掉的點數補得上差距」時才提在他那個陣營再升一階。
        企劃者裁決 E4：門檻照 rank_of，在任的第 4 階才多抵一階；候缺的人下一步是席次（每週照貢獻輪替，不是被召去的晉升），
        照規則不許諾——next_rank_up 在第 3 階以上本來就是 None，這裡不用另外判斷。
        不叫模型、不花體力、不加情誼。"""
        s, c = self.state, self.content
        self._hint("h_snubbed")  # 第一次被名將打發（新手引導計畫三）：不看狀態，打發的當下排；在行動裡，說的話記在這一則
        ch = c.characters[companion_id]
        line = self.rng.choice(ch.brush_off) if ch.brush_off else f"{ch.name}連見都不見你，門口的人把你請了出去。"
        short = self._fame_gap(companion_id)
        figure = next((f for f in c.figures.values() if f.character == companion_id), None)
        hint = f"名望還差 {short}"
        p = s.player
        if (
            season_one(c, s.world)  # 規則沒開（beta 那一季）沒有人晉升
            and figure is not None and p.faction == figure.faction
            and short <= c.config.audience_rank_discount  # 再升一階抵掉的點數補得上這個差距
            and ranks.next_rank_up(s, c) is not None  # 而且下一次晉升真的會升階：第 4 階只是資格（rank 停在 3、在任才降門檻），不許諾
        ):
            faction = c.scenario.faction_name(figure.faction, figure.faction)
            hint += f"，或在{faction}再升一階"
        return [f"{line}（{hint}）"]

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
        """這個地點此刻能深度對話的人物 id：見得到（名望或結識）、今天還沒聊滿，也沒在對你閉門不見（T4）；沒有就是 None。"""
        for companion_id in self._figures_here():
            if self._can_meet(companion_id) and self._talks_left(companion_id) > 0 and not self._snubbed_character(companion_id):
                return companion_id
        return None

    def _audience_hall(self) -> bool:
        """這裡有兩位以上的大勢人物：交友不再直接找第一位見得到的人，改按「求見」指名（企劃者 2026-10-03 決定）。"""
        return len(self._figures_here()) >= AUDIENCE_HALL_FIGURES

    def _socialize_figure(self) -> str | None:
        """交友會直接開口對話的那位人物：只有這裡至多一位大勢人物時才有（見得到、今天還沒談滿，見
        _deep_interaction_target）；兩位以上的地點交友只走福緣與地點事件，人物要按「求見」指名。"""
        if self._audience_hall():
            return None
        return self._deep_interaction_target()

    def _audience_options(self) -> list[Option]:
        """求見的第二層選單：這裡每一位大勢人物一個選項，最後是永遠按得下去的「返回」。名望不夠（也沒結識過）的人
        也按得下去，只是會被打發（見 _brush_off）；今天已經跟他談滿、或剛吃了敗仗閉門不見的人按不下去並寫明原因；
        每天的輪數上限是每位人物各算各的（talk_turns_per_day）。"""
        c = self.content
        cost = c.config.action_cost["socialize"]
        per_day = c.config.talk_turns_per_day
        opts = []
        for companion_id in self._figures_here():
            ch = c.characters[companion_id]
            option_id = f"call:{companion_id}"
            left = self._talks_left(companion_id)
            if self._snubbed_character(companion_id):
                opts.append(Option(id=option_id, label=f"{ch.name}（{SNUB_NOTE}）", enabled=False))
            elif not self._can_meet(companion_id):
                opts.append(Option(id=option_id, label=f"{ch.name}（名望還差 {self._fame_gap(companion_id)}）"))  # 按下去走打發，見 _brush_off
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
        return f"{here}有好幾位人物，挑一位求見。每位人物每天最多談 {per_day} 輪，各算各的；名望不夠的會被打發，談滿的明天再來。"

    def _no_audience_line(self) -> str:
        """交友時見不到這裡的大勢人物時的說明；這裡沒有大勢人物就是原本的「此地無人可訪」；
        兩位以上大勢人物的地點交友不找人，提醒要按「求見」。"""
        if self._audience_hall():
            return "你四處結交了一番，沒遇上什麼事；想拜會此地的人物，請按「求見」指名。"
        for companion_id in self._figures_here():
            ch = self.content.characters[companion_id]
            if self._snubbed_character(companion_id):
                return f"{ch.name}{SNUB_NOTE}。"
            if not self._can_meet(companion_id):
                return self._brush_off(companion_id)[0]  # 交友時遇上見不到的人物，用求見同一套打發的話
            if self._talks_left(companion_id) == 0:
                return f"{ch.name}今日事忙，改日再來拜會吧。"
        return "此地無人可訪，你只好悻悻離去。"

    def socialize_starts_dialogue(self) -> bool:
        """在這裡交友會直接跟大勢人物對話（伺服器假人不閒聊大勢人物，見 bot_policy）。在召見的地點不會：交友端出晉升奇遇。"""
        return ranks.summons_event(self.state, self.content) is None and self._socialize_figure() is not None

    def socialize_is_futile(self) -> bool:
        """在這裡交友注定白跑一趟（伺服器假人不該去按）：這個地點沒有交友事件、沒有見得到的大勢人物，
        而且福緣還沒到期（交友最先發福緣，見 _act）。"""
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
        if arg.startswith("clue:"):  # 伏筆的片段：固定文字，不經模型、不扣體力、不算對話輪數（計畫 T7）
            chain_id, _, index = arg.removeprefix("clue:").rpartition(":")
            heard = foreshadow.hear_talk(self.state, self.content, companion_id, chain_id, int(index), self.world)
            return heard or ["（此刻無法這麼做。）"]
        if arg.startswith("opp:"):  # 機緣的話題：固定文字，不經模型、不扣體力、不算對話輪數（正式版乙一）
            heard = opportunities.hear_topic(self.state, self.content, companion_id, arg.removeprefix("opp:"))
            return heard or ["（此刻無法這麼做。）"]
        try:
            msgs = companion_agent.continue_dialogue(
                self._quick_client(), self.state, self.content, self.world, companion_id, int(arg), self.rng,
                turn=self._prepared_turn(prepared),
            )
        except companion_agent.DialogueUnavailable:
            return self._dialogue_unavailable(companion_id)
        self.state.player.stamina -= self.content.config.talk_stamina  # 每一輪對話都要花體力（伺服器假人設計第八節第 4 項）；生成不出來的那輪不算
        msgs += self._count_talk(companion_id)
        return msgs

    def _faction_step(self, arg: str) -> list[str]:
        """投靠分兩步（伺服器假人設計第八節第 3 項）：按「投靠某陣營」先出確認畫面（寫明這一季
        不能改投、三方目前各有幾人），「確定」才真的投靠，「再想想」就作罷。"""
        p = self.state.player
        if arg == "cancel":
            p.pending_faction = None
            return ["你決定再想想。"]
        if arg == "confirm":
            faction = self.content.scenario.faction(p.pending_faction)
            p.pending_faction = None
            if p.location not in faction.join_at:
                return ["（你已經不在投靠的地方了。）"]
            p.faction = faction.id
            # 投靠這一刻就推一次新手引導：第一季「投靠、看一眼本週軍令」那一步只看陣營（計畫 T6）；beta 照舊等下一個行動
            msgs = [f"你投靠了{faction.name}。"]
            if season_one(self.content, self.state.world):
                msgs += self._guide(note_action(self.state, self.content, self.world, "join"))  # 走對話框（畫面批次審查 I2）
            return msgs
        faction = self.content.scenario.faction(arg)
        p.pending_faction = faction.id
        prompt = self._faction_prompt(faction)
        self._hide(prompt)  # 場景已經寫著這一問（_own_scene_text），江湖紀錄那一則只留標題（FB-046）
        return [prompt]

    def _defect_step(self, arg: str) -> list[str]:
        """叛投分兩步（同投靠）：按「叛投某陣營」先出確認畫面（寫明代價、一季一次、三方人數），「確定」才真的叛投。
        確定時再驗一次（defection.refusal，跟選單挑對象的 targets_here 同一套規則：還在那個投靠點、還能叛投、不是自己的陣營、
        名字不在沒打完的決戰的參戰名單上）：中間走開了、規則關了、另一個分頁已經叛投過、報了名參戰，都不叛投，
        而且把真正的原因說給玩家聽；那一則江湖紀錄也不寫成「叛投某某」（沒叛成）。
        投靠名冊由 choose() 結尾的 _record_faction 改記，這裡不碰。"""
        p = self.state.player
        if arg == "cancel":
            p.pending_defect = None
            return ["你決定再想想。"]
        if arg == "confirm":
            target = self.content.scenario.faction(p.pending_defect)
            p.pending_defect = None
            reason = defection.refusal(self.state, self.content, target, self.world.get_battle())
            if reason is not None:
                if self._draft is not None:
                    self._draft.title = "叛投不成"
                return [f"（{reason}）"]
            return defection.defect(self.state, self.content, target)
        target = self.content.scenario.faction(arg)
        p.pending_defect = target.id
        prompt = defection.prompt(self.state, self.content, target, self.faction_counts_text())
        self._hide(prompt)  # 場景已經寫著這一問（_own_scene_text），江湖紀錄那一則只留標題（同投靠，FB-046）
        return [prompt]

    def _defect_targets(self) -> list[FactionDef]:
        """這一刻選單上能叛投去的陣營。先用不碰資料庫的條件擋掉大多數人（散人、開關關著、叛投過），
        剩下的才讀目前的決戰、看名字在不在參戰名單上（defection.enlisted）。"""
        if not defection.can_defect(self.state, self.content):
            return []
        return defection.targets_here(self.state, self.content, self.world.get_battle())

    def _faction_prompt(self, faction) -> str:
        return f"投靠後這一季不能改投（叛投另論）。{self.faction_counts_text()}。確定投靠{faction.name}？"

    def faction_counts_text(self) -> str:
        """「目前官軍 N 人、黃巾軍 M 人、地方豪強 K 人」：照全服投靠名冊（真人與假人一起算）。"""
        counts = self.world.faction_counts()
        return "目前" + "、".join(f"{f.name} {counts.get(f.id, 0)} 人" for f in self.content.scenario.factions)

    def _roster_players(self) -> int:
        """這一季投靠了陣營的人數（全服投靠名冊，真人與假人一樣算）：跟 world.advance_world_state 查來縮放割據漲速的是
        同一個算式，割據的說明（rules.chaos_note）才說得準現在是在漲還是不動（FB-065 M1）。每次畫面現查，只是讀。"""
        return sum(self.world.faction_counts().values())

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
        （見 battle_instance.py::BattleParticipant 的欄位註解）。快照吃本人的加成（臂力、根骨，武學與成長設計 8.4）。
        同伴不進決戰（人物資質設計 14.5），這裡照舊只算本人。"""
        arts = team.team_arts(self.state, self.content, self.world)
        return encounter.member_power(
            self.state.player.member, arts, boost=team.player_boost(self.state, self.content, self.world),
        )

    def _battle_scores(self) -> dict[str, float]:
        """加入戰局時的每招份量快照（戰鬥系統 3.4）：實力看武學威力（_battle_power），適性看身上武學與內功的屬性。
        只有加入戰局的那個玩家自己的 Game 能算（排程的 Game.for_world 玩家是空白的，不能在 world_tick 裡呼叫）。"""
        p = self.state.player
        outer = team.player_art(self.state, self.content, self.world, p.member.wugong_id)
        inner = team.player_art(self.state, self.content, self.world, p.member.neigong_id)
        return battle_instance.move_scores(
            self.content.config.battle, self._battle_power(),
            outer.attribute if outer else None, inner.attribute if inner else None,
        )

    def _battle_road(self) -> str:
        """加入戰局時快照的武學屬性（決戰的隊伍多樣性，一門打不遍）：只有第一季開著時才記，關著時是空的、不算一路。"""
        if not season_one(self.content, self.state.world):
            return ""
        return team.worn_attribute(self.state, self.content, self.world) or ""

    def _backfill_battle_scores(self) -> None:
        """自己在戰局上的份量快照是空的（決戰打到一半上線這一版：上線前就在場上的人沒有 scores），補上現在的；
        已經有快照的人不動（加入之後換武學不影響這一場）。只在玩家自己的請求路徑呼叫（sync、_battle_choose）：
        份量只有那個玩家自己的 Game 算得出來，排程的 Game（Game.for_world）玩家是空白的，絕不能呼叫、
        world_tick 裡也沒有人呼叫它。倒下的人不補（用不到）。"""
        status = self._battle_status(tick=False)
        if status is None:
            return
        battle, _ = status
        name = self.state.player.name
        me = battle.participants.get(name)
        if me is None or me.scores or me.eliminated:
            return
        scores, road = self._battle_scores(), self._battle_road()

        def _fill(b: battle_instance.BattleInstance) -> None:
            mine = b.participants.get(name)
            if mine is not None and not mine.scores:  # 鎖裡再看一次：別的路徑剛補過就不蓋掉
                mine.scores = dict(scores)
                mine.attribute = mine.attribute or road

        self.world.mutate_battle(_fill)

    def _battle_neili_cap(self) -> float:
        _, cap = team.member_neili(
            self.content, self.state.player.member, team.con_of(self.state, self.content, self.world, PLAYER),
        )
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
        if self.state.world.ended:
            # 季結束了：沒打完的決戰直接收掉、不套用結果（這一季勝負已經定了），參戰者回到休季畫面（試玩回饋 FB-015）；
            # 參戰者各補一則「沒打完、不算勝負」的江湖紀錄（FB-035）
            if tick and raw.phase != "ended":
                self._shelve_unfinished_battle()
            return None
        definition = self.content.battles.get(raw.battle_id)
        if definition is None:
            return None
        if not tick or self.world.paused_at() is not None:  # 暫停中只讀：集結截止、回合逾時、補位、結算都等繼續之後
            return None if raw.phase == "ended" else (raw, definition)
        was_ended = raw.phase == "ended"
        battle, _ = self._run_battle_tick(definition)
        battle = battle or raw
        if battle.phase == "ended":
            if not was_ended:
                self._apply_battle_outcome(battle)
            return None
        return battle, definition

    def _shelve_unfinished_battle(self, text: str = "") -> None:
        """季終時還沒打完的決戰收起來（自然收季見 _battle_status、管理者收季見 admin_end_season；呼叫端先確認
        有一場還沒收場的）。不算結果：不動大勢、不寫旗標、不寫江湖史、不加戰報（FB-015）；但每個參戰者要有交代（FB-035）。

        做法是先在 battles 表把它標成 ended＋unfinished、end_time 記收季那一刻，再從共用狀態拿掉：
        ended_battles 讀得到它，參戰者各自同步時用 _deliver_battle_results 補一則江湖紀錄（下線的、跨季才回來的也補得到）。
        兩步不能併成一次 mutate：決戰拿掉之後，存檔就不再寫那一列了，標記會丟掉。
        標成 ended 不會被當成「剛打完」套結果：_battle_status 對本來就 ended 的不再套（was_ended）、
        _apply_battle_outcome 認得 unfinished 直接不動，而且拿掉之後 get_battle 本來就看不到它。
        最後也補給自己，跟 _apply_battle_outcome 一樣：收場那一下的那個人當場就看得到。"""
        end_time = self.state.world.time

        def _mark(b: battle_instance.BattleInstance) -> None:
            b.phase = "ended"
            b.unfinished = True
            b.unfinished_text = text  # 空的照季終收兵那一句（管理者取消決戰另外寫，T10 審查 I3）
            b.outcome_title = battle_instance.UNFINISHED_TITLE
            b.end_time = end_time

        self.world.mutate_battle(_mark)
        self.world.clear_battle()
        self._deliver_battle_results()

    def _advance_battle_round(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> list[str]:
        """核心推進邏輯（在呼叫端的 mutate_battle callback 裡原地修改 battle）：
        集結逾時自動分配、機器人補位、場上沒人能打又逾時就用保底結果收場、回合逾時代選
        保守行動、全員到齊就結算並請 LLM 潤色。回傳這次呼叫如果真的結算了一回合（或收場）
        的敘事訊息，沒有結算就是空清單。這是
        _run_battle_tick()（被動追趕，options()/scene_text() 用）跟 _battle_choose()
        的 act 分支（玩家自己送出行動，可能剛好湊滿全員）共用的同一份邏輯，確保兩條
        路徑的推進規則完全一致——只是呼叫的時間點跟是否先 submit_action 不同。"""
        now = self.now
        tuning = self.content.config.battle  # 三招的數字（排程的 Game 與玩家的 Game 讀同一份內容，所以結算一致）
        if battle.phase == "muster" and now >= battle.muster_deadline_real:
            battle_instance.close_muster(battle, definition, self.rng, now)
        if battle.phase != "active":
            return []
        for p in list(battle.participants.values()):
            if p.is_bot and not p.eliminated and not p.away and p.name not in battle.round.pending_actions:
                tag = battle_instance.bot_choose_action(battle, definition, p.name, self.rng, tuning=tuning)
                if tag:
                    battle_instance.submit_action(battle, p.name, tag)
        ended = battle_instance.end_without_fighters(battle, definition, now, tuning=tuning)  # 兩軍沒人能打、回合逾時：用保底結果收場
        if ended:
            battle.end_time = self.state.world.time  # 收場時的賽季時間：參戰者的戰報用（FB-027）
            return ended
        if now - battle.round.opened_real >= definition.round_seconds and not battle_instance.round_is_complete(battle):
            battle_instance.fill_timed_out_actions(battle, definition, tuning=tuning)
        if not battle_instance.round_is_complete(battle):
            return []
        msgs = battle_instance.resolve_round(battle, definition, self.rng, now=now, tuning=tuning)
        if battle.phase == "ended":
            battle.end_time = self.state.world.time
        # 每回合最前面那一行出招比例只留在回合紀錄（戰報）與給模型的判定裡：潤色退回系統訊息時（沒有模型、逾時、或在假人的
        # Game 裡結算）不放進場景的記錄，場景上的比例只由「對面上一回合」那一段寫一次（審查 I1）
        shown = battle_instance.without_mix_line(battle, msgs)
        narration = battle_instance.narrate_round(self._quick_client(), definition, battle, msgs, fallback=shown)
        if narration:
            battle.narrative_log.append(narration)
            battle.rounds[-1].narration = narration  # resolve_round 剛記下這一回合
        return [narration] if narration else (shown or ["這一回合結算了。"])

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
        不寫記憶體，免得存兩次。

        最後把結果補送給自己（收場那一下的那個人當場就看得到）；別的參戰者各自同步時補（FB-027）。

        季終收兵的決戰（unfinished，見 _shelve_unfinished_battle）沒有結果可套，不會走到這裡；萬一走到，直接不動。

        時刻表決戰（第一季的三場大戲，計畫 T8）不套保底的 BattleOutcome，改走 _settle_showdown。不論哪一種，收場之後
        都看有沒有時間到了、在等這一場打完的決戰，有就立刻開（見 _open_waiting_showdown）。"""
        if battle.unfinished:
            return
        definition = self.content.battles.get(battle.battle_id)
        if definition is not None and definition.third is not None and battle.third_push:
            # 第三方（地方豪強）收場的割據推動：一般收場與時刻表收場都推（時刻表那一支不套保底的大勢變化，所以要在分支之前）
            self.world.mutate_season(lambda season: self._apply_third_push(season, battle, definition))
            self._apply_third_push(self.state.world, battle, definition)
        if definition is not None and definition.timetable_event is not None and season_one(self.content, self.state.world):
            self._settle_showdown(battle, definition)
        else:
            if battle.outcome_world_flags or battle.outcome_trend_delta or battle.outcome_title:

                def _apply(season: WorldState) -> None:
                    self._apply_outcome_trends_and_flags(season, battle)
                    if battle.outcome_title:
                        season.chronicle.append(Rumor(time=season.time, text=f"【{battle.outcome_title}】{battle.outcome_text}"))

                self.world.mutate_season(_apply)
                self._apply_outcome_trends_and_flags(self.state.world, battle)
            self._deliver_battle_results()
        self._open_waiting_showdown()

    def _apply_third_push(self, season: WorldState, battle: battle_instance.BattleInstance, definition: BattleDef) -> None:
        """第三方收場推的大勢線（戰鬥系統第六節）：一般收場與時刻表收場都推；資料庫那份與記憶體那份共用這一段。
        battle.third_push 是收場時 battle_instance.settle_third 算好的（最多 Config.battle.third_cap）；季終沒打完收起來的決戰
        不會走到這裡（_apply_battle_outcome 一開頭就擋掉）。"""
        trend_id = definition.third.trend
        season.trends[trend_id] = max(0, min(100, world_trend_value(season, self.content, trend_id) + battle.third_push))
        recompute_trends(season, self.content)

    def _settle_showdown(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> None:
        """時刻表決戰收場（計畫 T8）：照 battle_instance.decide_result 判誰贏、大勝或險勝——這一刻才讀
        WorldState.locks（鎖定只在這裡看，起點、推力、選項都不看，戰鬥系統 4.3）——再交給 timetable.resolve 結算那一格
        （它自己加宛城的版本前綴，公告、江湖史、戰況、人物都照時刻表）。保底的 BattleOutcome 不套、不寫江湖史。

        戰鬥那一列的結果改成時刻表那一格（標題「官軍大勝」、文字是公告、大勢變化是那一格的戰況），參戰者的戰報照
        W13／FB-027 補送時就寫這個；公告進每個人的江湖紀錄走 _deliver_big_events（FB-038）。

        resolve 改的是資料庫裡的那一份賽季（mutate_season），手上的 self.state.world 跟著讀回來：結算發生在 options() 的
        推進裡，接下來 choose() 收尾的 _save_season 會把手上那一份整份寫回去，不讀回來就把結果蓋掉了。這一刻手上那一份
        跟資料庫一致（每個動作開頭的 sync 剛讀過、推進戰鬥之前還沒改它），讀回來不會丟東西。"""
        event = next((e for e in self.content.timetable if e.id == definition.timetable_event), None)
        result: dict[str, object] = {}

        def _resolve(season: WorldState) -> None:
            lock = season.locks.get(definition.timetable_event)
            winner, margin = battle_instance.decide_result(
                battle, definition, lock.side if lock is not None else None, definition.defender or definition.factions[0].id,
            )
            result["title"] = f"{timetable.SIDE_NAMES.get(winner, winner)}{margin}"
            if event is None:
                return
            key = showdown_key(definition, winner, margin)  # 帶上實際打的那一版（審查 M-1）
            timetable.resolve(_season_vehicle(self.content, season), self.content, event, self.rng, key=key)
            done = season.timeline.get(event.id)
            outcome = event.outcomes.get(done.key) if done is not None else None
            result["text"] = done.text if done is not None else ""
            result["trends"] = dict(outcome.trends) if outcome is not None else {}

        self.world.mutate_season(_resolve)

        def _relabel(b: battle_instance.BattleInstance) -> None:
            if b.record_id != battle.record_id:
                return
            b.outcome_title = str(result["title"])
            b.outcome_text = str(result.get("text") or b.outcome_text or "")
            b.outcome_trend_delta = dict(result.get("trends") or {})  # 只給戰報顯示：已經由 resolve 套過了
            b.outcome_world_flags = []

        self.world.mutate_battle(_relabel)
        self.state.world = self.world.get_season()
        self._deliver_big_events()
        self._deliver_battle_results()

    def _open_waiting_showdown(self) -> None:
        """時間到了、在等前一場打完的時刻表決戰，前一場一收場就開（Review Focus 2：開不成時留著記號，等它收場立刻開）。
        開了的話手上的那一份賽季跟著讀回來（季上記了「開過了」，之後存檔不能蓋掉它）。集結的消息不另外寫紀錄：
        場景上每個人都看得到集結。"""
        if not self.state.world.showdowns_waiting:
            return
        if open_waiting_showdown(self.world, self.content, self.now):
            self.state.world = self.world.get_season()

    def _apply_outcome_trends_and_flags(self, season: WorldState, battle: battle_instance.BattleInstance) -> None:
        """決戰結果的大勢變化與世界旗標，套到 season 上（資料庫裡的那份與記憶體裡的那份共用這一段）。
        內容寫的是戰線：照 rules.resolve_trends 換鍵（開關關著時是黃巾聲勢）；存檔沒有那條線時從起始值算起。"""
        for trend_id, delta in resolve_trends(self.content, season, battle.outcome_trend_delta).items():
            season.trends[trend_id] = max(0, min(100, world_trend_value(season, self.content, trend_id) + delta))
        recompute_trends(season, self.content)  # 開關開著時推了戰線，黃巾聲勢跟著重算（這裡不經 change_trend）
        for flag in battle.outcome_world_flags:
            if flag not in season.flags:
                season.flags.add(flag)
                season.flag_times[flag] = season.time

    def _without_timetable(self, msgs: list[str]) -> list[str]:
        """推進的訊息拿掉時刻表大事的公告（world.timetable.resolve 回的「【江湖大事】＋公告全文」）：那些由
        _deliver_big_events 補進每個人的江湖紀錄，不再只進剛好推進到那一刻的人的那一則。
        大勢門檻與世界事件也是「【江湖大事】」開頭，但文字不在時間軸上，照舊留著。"""
        announced = {f"【江湖大事】{r.text}" for r in self.state.world.timeline.values() if r.text}
        return [m for m in msgs if m not in announced]

    def _deliver_big_events(self) -> None:
        """這一季時刻表上已經發生、自己還沒看過的大事補進江湖紀錄（FB-038）：每個人各一次，不管有沒有剛好在線、
        是不是推進時間的那個人，離線的回來第一次同步補到，這一季中途才建立的角色也補到這一季已經發生的。
        一次補到好幾件就合成一則「江湖大事」，每件一行、照時間先後、前面標季曆時間；只補到一件時標籤就是公告全文。
        跳過的大事（沒有公告文字）不補。看過的記在 PlayerState.events_seen，換季時新角色自然是空的。
        做法比照 _deliver_battle_results：資料庫（時間軸）才是真實來源，每個人自己的 Game 同步時在鎖裡自己補，
        不去改別人的角色。開關關著（或這一季開季時沒開）時時間軸本來就是空的，什麼都不補。"""
        w, c, p = self.state.world, self.content, self.state.player
        if not calendar.season_one_on(w, c):
            return
        fresh = [(i, eid, r) for i, (eid, r) in enumerate(w.timeline.items()) if r.text and eid not in p.events_seen]
        if not fresh:
            return
        fresh.sort(key=lambda item: (item[2].time, item[0]))  # 先看時間，同一刻照時間軸記下的順序
        p.events_seen += [eid for _, eid, _ in fresh]
        last = fresh[-1][2]
        if len(fresh) == 1:
            entry = JournalEntry(time=last.time, title=journal.WORLD_NEWS, tag=last.text)
        else:
            lines = [f"{self.stamp(r.time)}　{r.text}" for _, _, r in fresh]
            entry = JournalEntry(time=last.time, title=journal.WORLD_NEWS, tag=f"共 {len(fresh)} 件", lines=lines)
        journal.add_entry(self.state, entry)

    def _deliver_echoes(self) -> None:
        """首創名望回饋（Config.first_echo）：這一季別人照著你首創的武學或意境合了出來（fusion.echo 記在 WorldState.echoes），
        你同步時補名望——每多一個人 +fame_per，補到第幾個人記在 Echo.paid，所以一個人只算一次。好幾門一起補就合成一則紀錄。
        做法同 _deliver_renames：合的那一下不動別人的角色，每個人自己的 Game 同步時自己補。第一季沒開著時 echoes 是空的。"""
        p = self.state.player
        rule = self.content.config.first_echo
        lines, gained = [], 0
        for entry in self.state.world.echoes.values():
            due = len(entry.followers) - entry.paid
            if entry.creator != p.name or due <= 0:
                continue
            entry.paid = len(entry.followers)
            gained += due * rule.fame_per
            lines.append(f"江湖上又有 {due} 人照著你首創的{entry.name}練了出來。")
        if not lines:
            return
        p.stats["fame"] = p.stats.get("fame", 0) + gained
        self._write(journal.ECHO, lines + ([f"名望 +{gained}"] if gained else []))
        self._save_season()  # 補到第幾個人記在共用賽季裡

    def _deliver_renames(self) -> None:
        """手上（身上或功法庫）的武學被全服第一個練成絕學的人定了正式的名字，每個人下一次同步補一則江湖紀錄（FB-083）：
        「你手上的【舊名】已由{名號}定名為【新名】。」——絕學定名改的是全服的顯示名字，別人手上那一門也跟著改，不通知的話
        玩家只會看到武學莫名其妙換了名字。一次補到好幾門就合成一則（比照 _deliver_big_events）。

        做法同 _deliver_battle_results：資料庫（全服登記的武學）才是真實來源，改名那一下不去動別人的角色，每個人自己的 Game
        同步時自己補。誰通知過記在自己的 PlayerState.renames_told（武學 id），所以一個人一次改名只通知一次：自己定的名、
        拿到的時候就已經是定過名的（library.store_art）一開始就記成通知過。舊名就是登記時的 id（絕學定名只改顯示的名字，id 不動）。
        名號照登記時記下的那一個（MartialArt.master_shown，沒有就照 masters 表的名號），不另外去查；全服第一個練成的人寫的
        一律是他的名號，匿名行走的人在登記當下記成「某位少俠」，照寫。內容手寫的武學（本命、基礎）不會被改名，也就不會在這裡出現。"""
        p = self.state.player
        held = [a for a in library.owned_arts(self.state) if a not in p.renames_told and a not in self.content.skills]
        if not held:
            return
        renamed = self.world.renamed_skill_ids()  # 一次查完這一季改過名的；沒有就不必一門一門去查
        lines = []
        for art_id in held:
            art = self.world.get_skill(art_id) if art_id in renamed else None
            if art is None or not is_renamed(art):
                continue
            p.renames_told.append(art_id)
            namer = art.master_shown or self.world.master_of(art_id)
            if namer is None or self.world.master_of(art_id) == p.name:  # 自己定的名（舊存檔沒記到）：定名那一句已經說過了
                continue
            lines.append(f"你手上的【{art.id}】已由{namer}定名為【{art.name}】。")
        if len(lines) == 1:
            entry = JournalEntry(time=self.state.world.time, title=journal.RENAMED, tag=lines[0])
        elif lines:
            entry = JournalEntry(time=self.state.world.time, title=journal.RENAMED, tag=f"共 {len(lines)} 則", lines=lines)
        else:
            return
        journal.add_entry(self.state, entry)

    def _deliver_battle_results(self) -> None:
        """收場的全服決戰補送到自己手上（FB-027）：自己的名號在參戰名單上（含下線的、中途倒下的；觀戰的不在名單上）、
        還沒補過的，每一場寫一則江湖紀錄、加一筆戰報。

        為什麼是「下次同步時補」、不是收場那一下去改每個參戰者的角色：那會在一筆交易裡改幾十列，而且跟伺服器、假人
        程式記憶體裡各自的 Game 打架（它們之後存檔會把別人寫進去的蓋掉）。資料庫是唯一的真實來源，戰鬥也一直留在
        battles 表裡，所以每個人自己的 Game 在 sync（伺服器每個請求、假人每一輪）與自己收場的那一下自己補。
        不分季別：決戰的結果常常就把季收掉，休季、下一季才回來的人也要補到。不是自己參戰的那幾場也記成處理過，
        之後不必再讀（收場的決戰名單不會再變）。只讀處理過的最大流水號之後收場的：決戰照開戰的先後收場，比它小的
        不會再有新收場的（見 WorldStateStore.ended_battles）。季終沒打完就收起來的決戰（unfinished）也在這裡補，
        內容只是一則「不算勝負」的江湖紀錄（FB-035，見 _file_showdown）。"""
        p = self.state.player
        fresh = self.world.ended_battles(after=max(p.battle_results_seen, default=0))
        if not fresh:
            return
        current = self.world.get_season_number()
        for season, battle in fresh:
            me = battle.participants.get(p.name)
            if me is not None:
                self._file_showdown(battle, me, None if season == current else season)
            p.battle_results_seen.append(battle.record_id)

    def _file_showdown(
        self, battle: battle_instance.BattleInstance, me: battle_instance.BattleParticipant, earlier: int | None,
    ) -> None:
        """一場收場的決戰寫成自己的一則江湖紀錄與一筆戰報（kind 是 showdown），「剛剛」放這一場的卡片。
        earlier 是上一季（或更早）打的那一季的編號，這一季打的是 None：上一季的標明季別，大勢的增減寫進敘事、
        不放進數值變化——數值變化看起來像剛發生在你身上的。

        季終收兵的決戰（unfinished，FB-035）沒有結果：只寫一則江湖紀錄交代一聲，不加戰報、不放「剛剛」的戰鬥卡片。"""
        c, s = self.content, self.state
        definition = c.battles.get(battle.battle_id)
        sides = self._sides(definition) if definition is not None else {}  # 自己站哪一方：兩軍加第三方（地方豪強）
        armies = {f.id: f.name for f in definition.factions} if definition is not None else {}
        name = definition.name if definition is not None else battle.battle_id
        side = sides.get(me.faction, me.faction)  # 待 joy 潤：第三方的那一則寫成「你站在地方豪強」（劇本陣營的名字）
        foes = "、".join(n for fid, n in armies.items() if fid != me.faction) or "敵軍"  # 對手只算兩軍：兩軍打不到豪強
        where = self._battle_region_name(definition) if definition is not None and definition.region else name
        outcome = battle.outcome_title or "收場"
        label = "" if earlier is None else f"第 {earlier} 季・"
        time = battle.end_time if battle.end_time is not None else s.world.time
        if battle.unfinished:
            lines = [battle.unfinished_text or battle_instance.UNFINISHED_TEXT]
            lines += [f"你出手 {me.acted_rounds} 回合"] if me.acted_rounds else []
            journal.add_entry(s, JournalEntry(time=time, title=f"{label}{name}・{outcome}", tag=f"你站在{side}", lines=lines))
            return
        lines = ([battle.outcome_text] if battle.outcome_text else []) + [f"你出手 {me.acted_rounds} 回合"]
        if me.fell_round is not None:
            lines.append(f"你在第 {me.fell_round} 回合倒下，轉為觀戰")
        rule = c.config.breakthrough
        if earlier is None and me.acted_rounds >= rule.showdown_rounds:  # 絕學的契機（方案 C）：這一季的決戰裡真的出過手
            lines += cultivation.seize(s, c, self.world, rule.showdown_ratio, self.rng)
        trends = {t.id: t.name for t in c.scenario.trends}
        moved = resolve_trends(c, s.world, battle.outcome_trend_delta)  # 開關關著時戰線都寫成黃巾聲勢
        if definition is not None and definition.third is not None and battle.third_push:  # 割據的增減也列進每個參戰者的戰報
            moved = {**moved, definition.third.trend: moved.get(definition.third.trend, 0) + battle.third_push}
        # 第一季規則開著時，戰線與豪強割據的增減不寫數字（FB-064，同 change_trend）：這一季的是機器可讀的標籤，畫在戰鬥卡片
        # 底下、照看的人的陣營上色，戰報不收（「大勢」那一行不寫，跟遊歷的戰鬥卡片一樣）；上一季的寫進敘事，就直接是那一句話
        # （敘事沒有顏色）。其他的線、開關關著時照舊是帶正負號的數字。
        moves = {tid: d for tid, d in moved.items() if d}
        in_words = season_one(c, s.world)

        def plain(tid: str) -> str:
            return f"{trends.get(tid, tid)} {moves[tid]:+d}"

        if earlier is None:
            changes = [front_lines.mark(tid, d) if in_words and can_draw_side_change(c, tid) else plain(tid) for tid, d in moves.items()]
            record_changes = [plain(tid) for tid in moves if not (in_words and can_draw_side_change(c, tid))]
        else:
            changes, record_changes = [], []
            lines += [
                f"（第 {earlier} 季）" + (front_text(c, tid, d, str(time)) if in_words and can_draw_side_change(c, tid) else plain(tid))
                for tid, d in moves.items()
            ]
        record = BattleRecord(
            id=s.battle_seq + 1, time=time, location=f"{label}{where}", kind="showdown", event=name, opponent=foes,
            ours=[], tier=outcome, our_power=0.0, difficulty=0.0, side=side, notes=list(lines), changes=list(record_changes),
        )
        battlelog.add_record(s, record)
        s.battle_card = record.id
        journal.add_entry(s, JournalEntry(
            time=time, title=f"{label}{name}・{outcome}", tag=f"你站在{side}", lines=lines, changes=changes,
            battle_id=record.id,
        ))

    def _watching_battle(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> bool:
        """這個人此刻打不了這場仗、只能在一旁看（options() 照常給平常的選項，場景上仍看得到戰場）：
        - 劇本分陣營時，自己的陣營不是這場決戰能站的任何一方（兩軍或第三方），而且還在集結、或已經開打但他不在場上；
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

    def _sides(self, definition: BattleDef) -> dict[str, str]:
        """這場決戰能站的每一方（id → 名字）：交戰的兩軍，加上第三方（戰鬥系統第六節；名字照劇本的陣營）。"""
        names = {f.id: f.name for f in definition.factions}
        if definition.third is not None:
            names[definition.third.faction] = self.content.scenario.faction_name(
                definition.third.faction, definition.third.faction,
            )
        return names

    def _off_side(self, definition: BattleDef) -> bool:
        """劇本分陣營、而自己的陣營（散人沒有）不是這場決戰能站的任何一方（兩軍或第三方）。"""
        return bool(self.content.scenario.factions) and self.state.player.faction not in self._sides(definition)

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
            paused = self.world.paused_at()  # 暫停中集結不倒數：停在按下暫停那一刻剩下的
            remaining = max(0, int(battle.muster_deadline_real - (self.now if paused is None else paused)))
            left = f"{remaining // 60} 分 {remaining % 60} 秒"
            if watching:
                return f"{header}\n\n集結中，還剩現實 {left}。{watch_line}"
            me = battle.participants.get(self.state.player.name)
            if me is not None:
                side = self._sides(definition).get(me.faction, me.faction)
                leaving = "；走出這一區就不算在場" if definition.region is not None else ""
                return f"{header}\n\n你已加入【{side}】，集結還剩現實 {left}。集結結束就開打，在那之前照常行動{leaving}。"
            return f"{header}\n\n集結中，還剩現實 {left}。選擇陣營加入；集結期間照常行動。"
        act = battle_instance.current_act(battle, definition)
        # 第幾回合／一共幾回合（戰鬥系統設計 3.2）：讓人知道還要打多久；收場的決戰不會走到這裡
        count = f"（第 {battle.round_number + 1}／{battle_instance.total_rounds(definition)} 回合）"
        lines = [header, f"【{act.title}】{count}{battle_instance.act_text(battle, definition)}"] + battle.narrative_log[-5:]
        p = battle.participants.get(self.state.player.name)
        if p is not None:
            last = []  # 上一回合的兩句併成一段 markdown 引用（「> 」、段內換行）：網頁在 .scene blockquote 底下縮成小字、淡色
            if battle_instance.is_third(definition, p):  # 第三方：兩軍各一行，再加膠著程度（戰鬥系統第六節；全是公開的戰局）
                for f in definition.factions:
                    seen = battle.last_mix.get(f.id)
                    if seen:
                        last.append(f"> {f.name}上一回合：" + "・".join(f"{m} {round(seen[m] * 100)}%" for m in MOVES))
                # 說「膠著」、不說「亂局」：亂局是第一季戰線（戰況 35～65）的說法，撞名會讓人以為是同一件事
                last.append(f"> 兩軍相持：膠著 {round(battle_instance.stalemate(battle.trend) * 10)} 成（越膠著，你趁亂收穫越多）")  # 待 joy 潤
            else:
                enemy = next((f for f in definition.factions if f.id != p.faction), None)
                seen = battle.last_mix.get(enemy.id) if enemy is not None else None
                if seen:  # 這回合的比例要到結算才揭曉，畫面只寫上一回合（設計 3.4）
                    parts = "・".join(f"{m} {round(seen[m] * 100)}%" for m in MOVES)
                    last.append(f"> 對面上一回合（{enemy.name}）：{parts}")
            if p.last_result:
                last.append(f"> 你上一回合：{p.last_result}")
            if last:
                lines.append("\n".join(last))
        if p is not None and p.eliminated:
            lines.append("（你已經倒下，只能在一旁觀戰。）")
        elif watching:  # 倒下的人不會再出手，不必再說「回到大區就能再出手」
            lines.append(watch_line)
        return "\n\n".join(lines)

    def _battle_options(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> list[Option]:
        """打得了這場仗的人的戰鬥選項（只能觀戰的人不會走到這裡，見 _watching_battle）。"""
        name = self.state.player.name
        p = battle.participants.get(name)
        tuning = self.content.config.battle
        if battle.phase == "muster":
            sides = list(self._sides(definition).items())  # 兩軍加第三方（id, 名字）
            if self.content.scenario.factions:  # 劇本分陣營：只能站在自己陣營那邊（第三方的人只看到自己那一方）
                sides = [(fid, fname) for fid, fname in sides if fid == self.state.player.faction]
            return [  # 已經加入的那一邊換成灰的「已加入」；不分陣營的劇本集結時還能換到另一邊
                Option(id=f"battle:join:{fid}", label=f"已加入【{fname}】", enabled=False)
                if p is not None and p.faction == fid else Option(id=f"battle:join:{fid}", label=f"加入【{fname}】")
                for fid, fname in sides
            ]
        if p is None:
            return [Option(id="battle:join_late", label="加入戰局")]
        if p.eliminated:
            return [Option(id="battle:spectate", label="（觀戰中，無法行動）", enabled=False)]
        if name in battle.round.pending_actions:
            return [Option(id="battle:waiting", label="（已選擇，等待其他人……）", enabled=False)]
        out = []
        for o in battle_instance.options_for(battle, definition, name):
            if o.free_text:
                continue
            label = o.text
            if o.move is not None and p.scores:  # 三招：寫招與這個人現在的份量（設計 3.4：按鈕上直接寫）
                share = tuning.third_keep_share if o.tag == battle_instance.THIRD_KEEP else 1.0  # 第三方「保存實力」只算一半
                score = round(p.scores.get(o.move, 0.0) * battle_instance.condition(p) * share)
                label = f"{o.text}（{o.move}・{score} 分）"
            elif o.move is not None:  # 還沒有份量快照（上線前就在場上、下一次同步才補）：不寫「0 分」，那是假的
                label = f"{o.text}（{o.move}）"
            out.append(Option(id=f"battle:act:{o.tag}", label=label))
        return out

    def event_free_text_prompt(self) -> str | None:
        """眼前的事件可以隨口應對時回傳提示語（選單上那一顆的標籤），否則 None；server.py 用它決定輸入框。"""
        event_id = self.state.pending_event
        if event_id is None or self.content.events[event_id].free_text is None:
            return None
        return self.content.events[event_id].free_text.prompt

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
        「battle.phase 還是 muster」悄悄吃掉（見那次遇到的真實 bug）。
        成功率的評分在行動鎖內（server.py 的 battle_text 走 act），所以用 _quick_client 的短逾時複本；評不到就是保底值。"""
        if self.world.paused_at() is not None:  # 不走 choose()：暫停中自己擋，不然送出去會把這一回合結算掉
            return [f"（{PAUSED_TEXT}。）"]
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
        success_rate = battle_instance.assess_action_success_rate(self._quick_client(), act, faction_name, text)
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
            scores = self._battle_scores()  # 在 mutate_battle 之前算好：快照的是加入這一刻、這個玩家自己的份量
            self.world.mutate_battle(
                lambda b: battle_instance.join_faction(
                    b, name, rest, self._battle_neili_cap(), self._battle_power(), scores=scores, attribute=self._battle_road(),
                )
            )
            msgs = stood + ["你加入了這場戰局。"]
            side = self._sides(definition).get(rest, rest)
            # 待 joy 潤：「…・加入地方豪強」是用劇本陣營的名字組出來的（兩軍照舊「…・加入官軍」）
            self._write(f"{definition.name}・{'改選' if changing_sides else '加入'}{side}", msgs)  # 加入與改選各留一則（FB-030）
            return msgs
        if kind == "join_late":
            own = self.state.player.faction if self.content.scenario.factions else None
            stood = self._stand_up() if self.state.player.resting_since is not None else []  # 加入戰局就起身
            scores = self._battle_scores()
            self.world.mutate_battle(
                lambda b: battle_instance.auto_assign_latecomer(
                    b, definition, name, self._battle_neili_cap(), self.rng, self._battle_power(), faction=own,
                    scores=scores, attribute=self._battle_road(),
                )
            )
            msgs = stood + ["你趕到了戰場，這一回合就能出手。"]  # 晚到的人當回合就能出招（FB-028）
            self._write(f"{definition.name}・趕到戰場", msgs)  # 趕到也留一則（FB-030）；每回合的出招不寫，太吵
            return msgs
        if kind == "act":
            self._backfill_battle_scores()  # 還沒有份量快照的自己，出招之前先補（結算要讀）
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

    def _encounter(self, action: str, nothing: str | Callable[[], str]) -> list[str]:
        """交友沒碰上人物時：抽一則事件，沒有就是 nothing（探索另有三選一，見 _explore）。
        nothing 可以是函式：真的用到才呼叫（打發話要挑一句，不該在抽到事件時白花一次亂數）。"""
        event = pick_event(self.state, self.content, action, self.rng)
        if event:
            return self._present(event, action)
        return [nothing() if callable(nothing) else nothing]

    def _present(self, event: Event, action: str | None = None) -> list[str]:
        """把事件端到玩家眼前。action 是抽中它的行動（探索、交友、遊歷）：這時才記進 joy 的防重複輪替
        （events.note_round；pick_event 本身不改狀態，預覽怎麼抽都不算）。next_event 串接、晉升召見不是從池子抽的，不給 action。"""
        if action is not None:
            event_rules.note_round(self.state, self.content, event, action)
        is_repeat = event.id in self.state.player.seen_events
        self.state.pending_event = event.id
        self.state.player.seen_events.add(event.id)
        head = f"✦ 奇遇：{event.title}" if event.qiyu else f"【{event.title}】"
        text = fill_marks(event.text, self.state)
        if is_repeat:
            flourish = flavor.polish_event_repeat(self._quick_client(), event.title, event.text)
            if flourish:
                text = f"{text}\n\n{flourish}"
        self._outcome(journal.event_marker(event.title, event.qiyu), head)
        self._hide(text)
        return [head, text] + foreshadow.hear_from_event(self.state, self.content, event.id, self.world)  # 片段事件（計畫 T7）

    def _squad_encounter(self, squad_id: str, wild: bool = False) -> list[str]:
        """遭遇一支敵方隊伍：單次判定，勝得對手獎勵，落敗失落一成銀兩；自己陣營的隊伍改成操練（見 _drill）。

        wild：探索時撞上的野怪（探索三選一設計 4.2）——扣氣血打折（`wild_neili_loss_factor`，內傷照比例）、
        打贏**不推大勢**（遊歷推大勢的量已經讓黃巾早早稱霸，探索不能再加碼）；獎勵、掉落、落敗的
        一成銀兩都照常。戰後事件本來就只在 _train 裡接，野怪不走那裡。遊歷不帶這個旗標，一點都不變。
        野怪是當下擲出來的，不問模型、也不吃判讀（武學與成長設計 8.3）；遊歷的大場面吃鎖外的判讀（_judged）。"""
        s, c = self.state, self.content
        p = s.player
        loc = c.locations[p.location]
        squad = c.squads[squad_id]
        if self._drills_with(squad):
            return self._drill(squad)
        scripted = prologue_rules.fight_tier(s, c)  # 序章雪恥那一場：結果照寫好的，不吃模型的判讀
        judged = None if wild or scripted is not None else self._judged(squad)
        result = self._fight_with(squad, judged, tier=scripted)
        record = battlelog.new_record(s, c, self.world, squad, result, "wild" if wild else "train")
        if scripted is None:
            record.notes += self._style_note(squad, result)
        self._narrate(record, result, judged)
        msgs: list[str] = []
        if result.tier in team.WIN_TIERS:
            rewards = self._battle_rewards(squad, record)
            msgs += rewards
            extra: list[str] = []
            if not wild and not prologue_rules.active(s, c):  # 序章打贏不推大勢、不抽伏筆、不記軍令
                for trend_id, delta in self.train_trend_push(loc.id).items():  # 換算過的線，照舊交給 T3 的 push_trend
                    extra += self.push_trend(trend_id, delta, source="train")
                region = atlas.region_of(c, p.location)  # 官銀（伏筆，濃縮版內容表 4.0）：只有遊歷打贏才擲
                extra += foreshadow.after_win(s, c, squad, self.rng, region.id if region is not None else None)
                extra += self._order_credit(  # 軍令（計畫 T6）：攻城看戰線與敵方陣營，截糧看地點與運糧隊
                    kind="win", location=loc.id, front=front_of(c, loc.id), squad=squad.id, squad_faction=squad.faction,
                )
                extra += opportunities.on_win(s, c, front_of(c, loc.id), squad.faction)  # 三路並進（正式版乙二）
            changes, notes = battlelog.split_changes(extra, for_record=True)
            record.changes += changes
            record.notes += notes
            msgs += extra
        elif result.tier == "落敗":
            msgs += self._lose_silver(record)
        toll, hp_lost, facts = self._take_toll(result.tier, wild=wild)
        record.changes += toll
        msgs += toll
        self._play_rounds(record, squad, result.tier, hp_lost, facts)
        msgs += self._seize(record)
        msgs.insert(0, self._file_battle(record))
        if squad.desc:  # 有來歷的對手（運糧隊）多一句描述，接在戰鬥那一行後面
            msgs.insert(1, f"（{squad.name}：{squad.desc}）")
        return msgs

    def _drills_with(self, squad: Squad) -> bool:
        """這支隊伍是自己陣營的：遇上了不打，改成一起操練（見 _drill）。"""
        return squad.faction is not None and squad.faction == self.state.player.faction

    def _drill(self, squad: Squad) -> list[str]:
        """在自己陣營的地方遊歷：不打自己人，一起操軍擺陣（企劃者 2026-10-02 決定）。不會輸、不扣氣血；
        給經驗與心得，但只給對手的三成（Config.drill_reward_share，戰鬥系統第八節）；不給銀兩、不掉素材（不搶自己人）；地點的大勢推動往自己陣營有利的方向推。"""
        s, c = self.state, self.content
        p = s.player
        loc = c.locations[p.location]
        msgs = [f"你與{squad.name}一同操軍擺陣，軍心為之一振。"]
        self._outcome("操練", msgs[0])
        share = c.config.drill_reward_share
        xinde = int(squad.reward_xinde * share + 0.5)  # 四捨五入（round 是銀行家進位）
        exp = int(squad.exp * share + 0.5)
        xinde_line = None
        if xinde:
            p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
            xinde_line = f"心得 +{xinde}"
            msgs.append(xinde_line)
            if self._draft is not None:
                self._draft.hide(xinde_line)
                self._draft.changes.append(xinde_line)
        msgs += team.add_team_exp(s, c, self.world, exp)  # 本人與帶著的同伴都拿（FB-002）
        if self._draft is not None and exp > 0:
            self._draft.changes.append(f"經驗 +{exp}（每人）")
        for trend_id, delta in self.train_trend_push(loc.id).items():
            msgs += self.push_trend(trend_id, delta, source="drill")
        return msgs

    def _lose_silver(self, record) -> list[str]:
        """落敗失落一成銀兩（遊歷與挑戰本人共用），記在戰報上。"""
        p = self.state.player
        loss = p.stats["silver"] // 10
        p.stats["silver"] -= loss
        record.silver = -loss
        return [f"銀兩 -{loss}"] if loss else []

    def _player_hp_and_cap(self) -> tuple[float, float]:
        """本人此刻的氣血與上限（上限吃根骨：con_of 認 key，所以傳 PLAYER，不傳 Member）。"""
        return team.member_neili(
            self.content, self.state.player.member, team.con_of(self.state, self.content, self.world, PLAYER),
        )

    def _player_hp(self) -> float:
        return self._player_hp_and_cap()[0]

    def _hp_facts(self, healed: tuple[str, ...] = ()) -> TollFacts:
        """此刻的氣血在寫功效演出句看來是什麼樣子（開打前量；劇情戰不扣氣血，開打前就是整場的樣子）。"""
        now, cap = self._player_hp_and_cap()
        return TollFacts(wounded=now < cap, low_hp=now <= LOW_HP_RATIO * cap, healed=healed)

    def _take_toll(self, tier: str, *, wild: bool = False) -> tuple[list[str], int, TollFacts]:
        """照結果扣這一場的氣血（team.take_encounter_toll），回傳（訊息, 本人真的掉了多少氣血, 寫演出句要的事實）。掉的量緊貼著
        扣氣血的前後量（計畫三 G4）：打贏升級會讓上限變高，開打前量的話回合裡寫的跟戰報「氣血 -N」對不上。四捨五入跟訊息的
        「:.0f」是同一個數（兩者都對同一個浮點數做銀行家捨入）。
        扣完之後本人身上的吸取（打贏）與回春（不論勝負）才回氣血（武學與成長設計 13.2、13.4）：回的那一行「氣血 +N」接在
        訊息後面、一起寫進戰報；掉的量在回血之前量，回合裡寫的「你氣血 -N」照舊加得起來。劇情戰不走這裡（不扣氣血，也就不回）。
        事實（TollFacts）是 _play_rounds 寫功效的演出句用的：開打前氣血是不是低於上限（厚），哪幾個回血的功效真的回了血
        （沒回到 1 點、沒有「氣血 +N」那一行就不算）。"""
        before, cap = self._player_hp_and_cap()
        saved, spared = team.toll_saved(self.state, self.content, self.world, tier, wild=wild)  # 扣之前量：化勁、不動這一場改了多少
        toll = team.take_encounter_toll(self.state, self.content, self.world, tier, wild=wild)
        hp_lost = round(before - self._player_hp())  # 回血之前量：回合裡寫的扣血不受吸取與回春影響
        lo = traits.loadout(self.state, self.content, self.world)
        healed: list[str] = []
        gained: list[tuple[str, int]] = []
        if tier in team.WIN_TIERS and traits.has(lo, "win_heal"):  # 吸取（13.2）
            heal = team.heal_fraction(self.state, self.content, self.world, traits.amount(self.content, lo, "win_heal"))
            toll += heal
            if heal:
                healed.append("win_heal")
                gained.append(("win_heal", _points(heal)))
        heal_after = lo.specials.get("heal_after")  # 回春（13.4）：不論勝負
        if heal_after is not None:
            heal = team.heal_fraction(self.state, self.content, self.world, heal_after.amount)
            toll += heal
            if heal:
                healed.append("heal_after")
                gained.append(("heal_after", _points(heal)))
        return toll, hp_lost, TollFacts(
            wounded=before < cap, low_hp=before <= LOW_HP_RATIO * cap, healed=tuple(healed),
            saved=saved, spared=spared, gained=tuple(gained),
        )

    def _play_rounds(
        self, record, squad: Squad, tier: str, hp_lost: int | None, facts: TollFacts | None = None,
    ) -> None:
        """照結果演出回合寫進戰報（武學與成長設計 8.2）。hp_lost 是這一場本人真的扣掉的氣血（_take_toll），回合裡寫的
        「你氣血 -N」加起來剛好等於它；None 是這一場本來就不扣氣血（劇情戰），對手的出手不寫數字（計畫三 G5）。
        亂數是自己一份、用「名號｜戰報流水號」當種子（計畫三 G3）：不碰 Game.rng，接下來的擲骰不會位移，
        同一筆戰報每次演出來都一樣。
        輸了（含僵持）卻一滴氣血都沒掉（本來就見底，內傷照樣累積）時，跟劇情戰一樣不寫打中沒有：每一下都寫「被你閃開了」，
        讀起來是對方沒碰到你、你卻輸了、損失裡還有內傷（最後審查 Minor 2）；贏了沒掉血（打得漂亮）寫閃開是通的，不動。
        帶【先手】的人回合裡一定先出手、不看身法（13.2）；功效的演出句寫進 trait_before／trait_after（13.6，_trait_lines），
        護命的那一句寫進 notes 最前面（跟閃避的那一句同一個位置）。facts 是 _take_toll 量好的（劇情戰不給，氣血的功效就不演）。"""
        s, c, p = self.state, self.content, self.state.player
        if hp_lost == 0 and tier not in team.WIN_TIERS:
            hp_lost = None
        rng = random.Random(f"{p.name}|{record.id}")
        lo = traits.loadout(s, c, self.world)
        foe = rounds.Foe(name=squad.name, attribute=squad.attribute, agility=rounds.foe_agility(squad.difficulty))
        our_agility = math.inf if traits.has(lo, "big_win") else float(p.stats.get("agi", team.BASE_STAT))  # 先手
        played = rounds.play(tier, team.fighters(s, c, self.world), foe, our_agility, hp_lost, rng)
        record.rounds = battlelog.round_lines(c, played, rng)
        record.trait_before, record.trait_after = self._trait_lines(lo, record, squad, hp_lost, facts or TollFacts(), rng)
        if record.guarded and (guard := lo.specials.get("no_loss")) is not None:  # 護命（13.4）：結果那一段，不在過程裡
            record.notes.insert(0, self._trait_say(lo, guard.name, squad, rng))

    def _trait_say(self, lo: traits.Loadout, name: str, squad: Squad, rng: random.Random, low_hp: bool = True) -> str:
        """一句功效的演出：本人、帶這個功效的那一門（lo.source，層數最多的）、對手的名字填進 S1 的句子。"""
        return battlelog.trait_line(
            self.content, name, self.state.player.name, lo.source.get(name, ""), squad.name, rng, low_hp=low_hp,
        )

    def _trait_lines(
        self, lo: traits.Loadout, record, squad: Squad, hp_lost: int | None, facts: TollFacts, rng: random.Random,
    ) -> tuple[list[str], list[str]]:
        """（開打前, 之後）的功效演出句。只在功效真的改到結果時才演（13.6）：開打前的四個一般功效與連環、借力一帶就算
        （它們改的是判定本身）；化勁、不動要這一場真的掉了氣血；厚要開打前氣血低於上限（它拉高的氣血係數下限這一場真的起了作用，
        見底、一滴氣血都沒得扣、或是不扣氣血的劇情戰也算；「氣血見底」那一句只在氣血剩三成以下才挑，Task 4 審查 M3）；
        乘勝要打贏、而且對手隊伍有東西可以多給（看 squad.exp、squad.reward_xinde：劇情戰先演回合、後發獎勵，戰報上的欄位這時還是 0，
        Task 4 審查 M2），悟招要打贏；吸取、回春要真的回了血（有「氣血 +N」，F10）；輕身只在遊歷。護命的那一句在 _play_rounds
        另外寫進 notes。"""
        names = {t.hook: t.name for t in self.content.traits.general}

        def say(name: str, low_hp: bool = True, note: str = "") -> str:
            """演出句；note 是這一場改了多少（FB-084，「（少扣了 12 點氣血）」），沒有數字可寫的功效不給。"""
            return self._trait_say(lo, name, squad, rng, low_hp=low_hp) + note

        gained = dict(facts.gained)
        won = record.tier in team.WIN_TIERS
        before = [say(names[h]) for h in ("big_win", "luck_narrow", "difficulty_cut", "luck_widen") if lo.layers.get(h)]
        before += [say(lo.specials[h].name) for h in ("double_luck", "power_from_difficulty") if h in lo.specials]
        after: list[str] = []
        if hp_lost and lo.layers.get("toll_cut"):
            after.append(say(names["toll_cut"], note=f"（少扣了 {facts.saved} 點氣血）" if facts.saved > 0 else ""))
        if lo.layers.get("condition_floor") and facts.wounded:
            after.append(say(names["condition_floor"], low_hp=facts.low_hp))
        if hp_lost and "no_injury" in lo.specials:
            after.append(say(lo.specials["no_injury"].name, note=f"（免了 {facts.spared} 點內傷）" if facts.spared > 0 else ""))
        if won and lo.layers.get("win_reward") and (squad.exp or squad.reward_xinde):  # 乘勝：對手有東西可以多給
            more = traits.amount(self.content, lo, "win_reward")  # 跟 _battle_rewards 同一個乘法、同一個四捨五入
            extra = [
                f"{round(base * (1 + more)) - base} 點{what}" for base, what in ((squad.reward_xinde, "心得"), (squad.exp, "經驗"))
                if round(base * (1 + more)) > base
            ]
            after.append(say(names["win_reward"], note=f"（多得 {'、'.join(extra)}）" if extra else ""))
        if "win_heal" in facts.healed:  # 吸取：真的回了血
            after.append(say(names["win_heal"], note=f"（回了 {gained['win_heal']} 點氣血）" if gained.get("win_heal") else ""))
        if won and "win_xinde" in lo.specials:  # 悟招
            after.append(say(lo.specials["win_xinde"].name, note=f"（多得 {int(lo.specials['win_xinde'].amount)} 點心得）"))
        if "heal_after" in facts.healed:  # 回春
            after.append(say(lo.specials["heal_after"].name, note=f"（回了 {gained['heal_after']} 點氣血）" if gained.get("heal_after") else ""))
        if record.kind == "train" and "train_stamina" in lo.specials:  # 輕身：只在遊歷
            saved = self.content.config.action_cost["train"] - self._action_costs()["train"]  # 按鈕上寫的與真的扣的少了多少
            after.append(say(lo.specials["train_stamina"].name, note=f"（少花了 {saved} 點體力）" if saved > 0 else ""))
        return before, after

    # ── 挑戰大勢人物本人（計畫 T4、軍令文件 4.5）─────────────

    def _snubbed(self, fid: str) -> bool:
        """這位人物剛被你打敗、還在閉門不見（snub_hours 個現實小時內）。看的是現實時間（self.now，sync 傳進來的），
        不是賽季時鐘：管理者快轉、補算時間都不會讓他提早見你；紀錄存在角色存檔，伺服器重開也照樣記得。
        第一季的規則沒開（beta 那一季）就沒有閉門不見這回事。"""
        return season_one(self.content, self.state.world) and self.now < self.state.player.snubbed_until.get(fid, 0.0)

    def _snubbed_character(self, character_id: str) -> bool:
        """這個對話人物（求見、交友用的 id）是不是剛被你打敗、還在閉門不見的大勢人物。"""
        fid = figures.of_character(self.content, character_id)
        return fid is not None and self._snubbed(fid)

    def _challenge_options(self, odds: bool) -> list[Option]:
        """挑戰本人：第一季的規則開著、自己有陣營時，這裡每一位在場的敵方大勢人物一個選項（體力照遊歷；odds 時寫勝算，
        難度跟著聲威走）。剛被你打敗、閉門不見的那幾位，以及戰線空著的人物（人物表標了 challenge_off_front 的何進除外），
        按不下去、寫明原因；求見、交友照常。散人沒有；同陣營的人不打。"""
        s, c = self.state, self.content
        p = s.player
        if p.faction is None or not season_one(c, s.world):
            return []
        cost = self._action_costs()["train"]
        opts = []
        for fid in figures.present_at(s, c, p.location):
            fig = c.figures[fid]
            if fig.faction == p.faction:
                continue
            option_id = f"act:challenge:{fid}"
            if not figures.can_challenge(s, c, fid):
                opts.append(Option(id=option_id, label=f"挑戰{fig.name}（{OFF_FRONT_NOTE}）", enabled=False))
            elif self._snubbed(fid):
                opts.append(Option(id=option_id, label=f"挑戰{fig.name}（{SNUB_NOTE}）", enabled=False))
            else:
                note = self.challenge_odds(fid) if odds else ""
                option = self._cost_option(option_id, f"挑戰{fig.name}", cost, note=note)
                option.wait = BIG_FIGHT_WAIT  # 挑戰本人一律是大場面：按下去先等模型判讀（武學與成長設計 8.3）
                opts.append(option)
        return opts

    def challenge_odds(self, fid: str) -> str:
        """挑戰這位人物的勝算（跟遊歷同一套說法）：對手是代表本人的隊伍，難度照他此刻的聲威（figures.difficulty）。"""
        squad = self.content.figures[fid].squad
        return team.estimate(self.state, self.content, self.world, squad, difficulty=figures.difficulty(self.state, self.content, fid))

    def _challenge(self, fid: str) -> list[str]:
        """挑戰本人（軍令文件 4.5，企劃者 2026-10-04 改定）：跟他本人打一場單次判定，花遊歷的體力。打贏他敗走（_rout），
        拿那支隊伍的獎勵；落敗失落一成銀兩；不論勝負都照結果扣氣血（同遊歷）。可以重複打，只是打贏的人要等他消氣。
        不推戰線（推戰線的是遊歷；打擊人物削的是聲威），也不擲官銀（那是遊歷打贏官軍隊伍才有）。"""
        s, c = self.state, self.content
        fig = c.figures[fid]
        squad = figures.squad_of(s, c, fid)
        s.player.stamina -= self._action_costs()["train"]
        judged = self._judged(squad)  # 挑戰本人一律是大場面：有鎖外的判讀就用（武學與成長設計 8.3）
        result = self._fight_with(squad, judged, difficulty=squad.difficulty)
        record = battlelog.new_record(s, c, self.world, squad, result, "event", event=f"挑戰{fig.name}")
        record.notes += self._style_note(squad, result)
        self._narrate(record, result, judged)
        msgs: list[str] = []
        if result.tier in team.WIN_TIERS:
            msgs += self._battle_rewards(squad, record)
            extra = self._rout(fid)
            changes, notes = battlelog.split_changes(extra, for_record=True)
            record.changes += changes
            record.notes += notes
            msgs += extra
        elif result.tier == "落敗":
            msgs += self._lose_silver(record)
        toll, hp_lost, facts = self._take_toll(result.tier)
        record.changes += toll
        msgs += toll
        self._play_rounds(record, squad, result.tier, hp_lost, facts)  # squad 是照聲威的那一份：對手的身法跟著難度走
        msgs += self._seize(record)
        msgs.insert(0, self._file_battle(record))
        return msgs

    def _rout(self, fid: str) -> list[str]:
        """打贏了，他敗走：
        1. 聲威扣 figure_defeat_prestige，照陣營人數緩衝（push.buffered，n＝自己陣營活躍時窗內推過大勢的人，含自己）；
           扣到 0 退場或重創、由接位的人接手（figures.defeat）；
        2. 打贏的人跟他的情誼扣 figure_defeat_affinity（沒有對話人物的彭脫、韓忠沒有情誼）；
        3. snub_hours 個現實小時內他不見你、也不跟你交手（其他人照常）；
        4. 記貢獻：照推 figure_defeat_prestige 點大勢算（contrib_per_push，不打人數緩衝的折），記在這一週。"""
        s, c = self.state, self.content
        p, w, cfg = s.player, s.world, c.config
        fig = c.figures[fid]
        window = cfg.active_window_days * DAY / calendar.cal_scale(c, w)
        n = push.active_count(s, p.faction, w.time, window)
        msgs = [f"{fig.name}敗走。"]
        msgs += figures.defeat(s, c, fid, push.buffered(cfg.figure_defeat_prestige, n))
        if fig.character is not None:
            before = p.affinities.get(fig.character, 0)
            p.affinities[fig.character] = max(0, before - cfg.figure_defeat_affinity)
            if p.affinities[fig.character] != before:
                msgs.append(f"{fig.name}情誼 {p.affinities[fig.character] - before:+d}")
        p.snubbed_until[fid] = self.now + cfg.snub_hours * HOUR
        push.add_contribution(p, calendar.point(w.time, c, w).week, cfg.figure_defeat_prestige * cfg.contrib_per_push)
        msgs += self._order_credit(  # 「打擊大勢人物」軍令（計畫 T6）：只算目標本人
            kind="challenge", location=p.location, front=figures.state_of(s, c, fid).front, figure=fid,
        )
        return msgs

    def _train_push(self, trend_id: str, delta: int) -> int:
        """遊歷（打贏或操練）推大勢：量照地點設定；自己陣營對這條線有目標就往目標方向推，散人和
        沒有這條線目標的陣營照地點原本的方向（企劃者 2026-10-02 決定）。trend_id 是換算過、真的會動的那條線：
        豪強（目標只有割據）在亂局的戰線上遊歷時換成豪強割據（delta 已取絕對值、往漲的方向，見 train_trend_push），
        所以這裡乘上的是割據的目標；不在亂局的戰線上，豪強根本不會走到這裡（什麼都不推）。"""
        goal = self._goals().get(trend_id, 0)
        return abs(delta) * goal if goal else delta

    def _goals(self) -> dict[str, int]:
        """自己陣營的目標，照 rules.resolve_goals 換過鍵（開關關著時三條戰線都算黃巾聲勢）；散人是空的。"""
        faction = self.content.scenario.find_faction(self.state.player.faction)
        return resolve_goals(self.content, self.state.world, faction.goals) if faction is not None else {}

    def train_trend_push(self, loc_id: str | None = None) -> dict[str, int]:
        """在這個地點（預設所在地）遊歷打贏或操練時，各條大勢線會被推多少（照自己的陣營，見 _train_push）。
        鍵是真的會動的那條線：內容寫的戰線或 front 先照 rules.resolve_trend 換過（開關關著時一律是黃巾聲勢）。
        第一季濃縮版的豪強（目標只有割據、對這條戰線沒有目標，見 _backs_the_chaos）不推戰線本身：這個地點的戰線
        在亂局（戰況 chaos_low～chaos_high）時改推豪強割據（往漲的方向、量取絕對值），戰線已經穩下來（不在亂局）
        時什麼都不推，所以那一趟遊歷或操練不會出現在回傳裡。散人與官軍、黃巾照舊推戰線。"""
        loc = self.content.locations[loc_id or self.state.player.location]
        pushes: dict[str, int] = {}
        for key, delta in loc.train_trend.items():
            target = resolve_trend(self.content, self.state.world, key, loc.id)
            if target is not None and self._backs_the_chaos(target):
                # 第一季濃縮版的豪強：那條戰線在亂局才推割據，不在亂局什麼都不推（第一季設計第七節）
                target, delta = (GEJU, abs(delta)) if in_chaos(self.state, self.content, target) else (None, 0)
            if target is not None:
                pushes[target] = pushes.get(target, 0) + self._train_push(target, delta)
        return pushes

    def _backs_the_chaos(self, trend_id: str) -> bool:
        """開關開著、這是一條戰線，而自己的陣營對它沒有目標、只想推割據（第一季濃縮版的豪強）。"""
        goals = self._goals()
        return (
            season_one(self.content, self.state.world) and trend_id in front_ids(self.content)
            and trend_id not in goals and GEJU in goals
        )

    def push_trend(self, trend_id: str, delta: int, *, source: str) -> list[str]:
        """玩家自己造成的大勢推動一律走這裡（遊歷、操練、事件效果；sim_tick、時刻表、決戰、管理者不是個人推動，不走）。
        第一季設計第七節的規則，掛在第一季開關後面——開關關著（或這一季開季時是關的）就是 change_trend，一個字都不變：
        1. 陣營人數緩衝：推力 ÷ √n，n＝自己陣營 active_window_days 個曆日內推過大勢的成員（含自己這一次、含假人，最少 1）；
        2. 每人每曆日對每條線的上限（緩衝後算）：超過的部分不推大勢；
        3. 貢獻帳：替自己陣營的目標方向推才記，contrib_per_push × 推力（不打緩衝的折），超過上限的部分只記 over_cap_contrib_ratio；
        4. 散人照推、照受上限，n 當 1，不記貢獻也不進活躍名單。
        緩衝後常有小數：不足一點的記在全服的 trend_accum（每條線一個），滿一點才真的推；回傳 change_trend 的訊息
        （第一季規則開著時戰線是機器可讀的戰況變化，畫面上換成一句話，見 front_lines；開關關著是既有的「（黃巾聲勢 +2）」），
        只有整數真的動了才有。source 先只當註記（"train"、"drill"、"event"），不存檔。"""
        s, c = self.state, self.content
        w, p = s.world, s.player
        if not calendar.season_one_on(w, c):
            return change_trend(s, c, trend_id, delta)
        if delta == 0 or (delta < 0 and not is_revealed(w, c, trend_id)):  # 開季時才補蓋章的季沒記到新加的公開線，照樣算浮現
            return []  # change_trend 也不會動的推動：不能拿來刷貢獻、也不算活躍
        cfg = c.config
        now = w.time
        at = calendar.point(now, c, w)
        window = cfg.active_window_days * DAY / calendar.cal_scale(c, w)
        key = f"{at.cal_day}:{trend_id}"
        pushed = push.buffered(abs(delta), push.active_count(s, p.faction, now, window))
        used = push.used_today(p.pushed, at.cal_day, trend_id)
        moved, _ = push.split_by_cap(pushed, used, cfg.daily_push_cap)  # 還推得動多少只在 push.room_left 算（_push_room 也走它）
        p.pushed = push.recent_days(p.pushed, at.cal_day)
        p.pushed[key] = used + moved

        msgs: list[str] = []
        if moved > 0:
            whole, rest = push.take_whole(w.trend_accum.get(trend_id, 0.0), moved if delta > 0 else -moved)
            if rest:
                w.trend_accum[trend_id] = rest
            else:
                w.trend_accum.pop(trend_id, None)
            if whole:
                msgs = change_trend(s, c, trend_id, whole)

        if p.faction is not None:  # 散人：照推，但不記貢獻、不進活躍名單
            faction = c.scenario.find_faction(p.faction)
            goal = faction.goals.get(trend_id, 0) if faction is not None else 0
            if goal and (goal > 0) == (delta > 0):  # 替自己陣營的目標方向推；逆著推、這條線沒有目標都不記
                gained = push.contribution(abs(delta), pushed, moved, cfg.contrib_per_push, cfg.over_cap_contrib_ratio)
                push.add_contribution(p, at.week, gained)
            w.active_pushers.setdefault(p.faction, {})[p.name] = now
        w.active_pushers = push.drop_stale(w.active_pushers, now, window)  # 順手清掉超過時窗的人，名單不會一直長
        return msgs

    def _battle_rewards(self, squad: Squad, record) -> list[str]:
        p = self.state.player
        msgs = []
        if squad.reward_silver:
            p.stats["silver"] += squad.reward_silver
            record.silver = squad.reward_silver
            msgs.append(f"銀兩 +{squad.reward_silver}")
        lo = traits.loadout(self.state, self.content, self.world)
        more = 1 + traits.amount(self.content, lo, "win_reward")  # 乘勝（13.2）：心得與經驗一起多拿
        insight = lo.specials.get("win_xinde")  # 悟招（13.4）：再多固定的心得
        xinde = round(squad.reward_xinde * more) + (int(insight.amount) if insight is not None else 0)
        if xinde:
            p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
            record.xinde = xinde
            msgs.append(f"心得 +{xinde}")
        if not prologue_rules.active(self.state, self.content):  # 序章不掉素材（新手引導計畫一）
            for material_id, count in materials.roll_squad_drops(squad, self.content, self.rng):
                line = materials.grant(self.state, self.content, material_id, count)
                if line:
                    record.materials.append(line.removeprefix(materials.GRANT_PREFIX))
                    msgs.append(line)
        exp = round(squad.exp * more)  # 經驗本來就是每人拿一樣多（FB-002），乘勝整隊一起乘
        record.exp = exp
        levels, record.levelups = team.grant_team_exp(self.state, self.content, self.world, exp)  # 每人都拿（FB-002）
        record.notes += levels  # 完整的句子留著（戰報頁、江湖紀錄）；戰鬥卡片畫 levelups 那一行簡短的（FB-074）
        return msgs + levels

    def _seize(self, record) -> list[str]:
        """絕學的契機（方案 C，cultivation.seize）：打贏了（險勝以上）、序章外，照這一場的難度比擲一次頓悟。
        說出來的話也記進這一場戰報的敘事（戰鬥卡片「結果」那一段）。"""
        if record.tier not in team.WIN_TIERS or record.our_power <= 0 or prologue_rules.active(self.state, self.content):
            return []
        msgs = cultivation.seize(self.state, self.content, self.world, record.difficulty / record.our_power, self.rng)
        record.notes += msgs
        return msgs

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

    def _move(self, arg: str) -> list[str]:
        """選單上的「前往 某地」：沿直接相連的那條路出發。arg 是 move: 後面那段——只有地點就是步行，
        「地點:走法」是主畫面「走法」切換選的趕路或疾行（見 _move_option）。"""
        dest_id, _, mode = arg.partition(":")
        legs = atlas.path_legs(self.content, self.state.player.location, [dest_id])
        return self._depart(atlas.Route((dest_id,), tuple(legs)), mode or "walk")

    def _road(self, arg: str) -> list[str]:
        """路上的選項（路上設計第三、四節）。road:back[:<走法>] 是折返：回身後那一站，跟大地圖改道走同一條路（見 _depart）。
        其餘是路上小事（ROAD_TASKS）：記進這一段做過的，結果照既有慣例寫成「心得 +3」這種變化量。"""
        what, _, mode = arg.partition(":")
        if what == "back":
            return self._depart(self._back_way(), mode or "walk")
        self.state.player.leg_actions.add(what)
        tasks = {"think": self._road_think, "ask": self._road_ask, "survey": self._road_survey, "gather": self._road_gather}
        return tasks[what]()

    def _road_ends(self) -> tuple[str, str]:
        """這段路的兩頭：身後那一站、前面那一站。"""
        spot = atlas.road_spot(self.state, self.content)
        return spot.behind, spot.ahead

    def _road_rewards_used(self, kind: str, day: int | None = None) -> int:
        """這一天（遊戲日，跟每天對話輪數同一個算法；不給就是今天）路上已經拿過幾次收穫；kind 是 "task"（路上小事）或
        "sight"（見聞）。紀錄是別天的就當沒拿過。"""
        record = self.state.player.road_rewards_today.get(kind)
        return record[1] if record and record[0] == (day or current_day(self.state)) else 0

    def _road_reward_due(self, kind: str, day: int | None = None) -> bool:
        """這一天路上這一種收穫還沒拿滿（企劃者 2026-10-03 決定的每天上限 road_reward_daily_cap）。"""
        return self._road_rewards_used(kind, day) < self.content.config.road_reward_daily_cap

    def _count_road_reward(self, kind: str, day: int | None = None) -> None:
        """記一次真的給出去的收穫（沒撿到東西的採集不算）。"""
        day = day or current_day(self.state)
        self.state.player.road_rewards_today[kind] = [day, self._road_rewards_used(kind, day) + 1]

    def _road_think(self) -> list[str]:
        """邊走邊想：心得（一次遊歷大約 12～20，這裡刻意少很多）。今天的收穫拿滿了就照樣想，只是沒有心得。"""
        if not self._road_reward_due("task"):
            return ["你邊走邊想，今天想得夠多了，沒有新的心得。"]
        p, amount = self.state.player, self.content.config.road_think_xinde
        p.stats["xinde"] = p.stats.get("xinde", 0) + amount
        self._count_road_reward("task")
        return ["你邊走邊想，把這幾天的見聞在心裡過了一遍。", f"心得 +{amount}"]

    def _road_ask(self) -> list[str]:
        """沿途打聽：這段路兩頭所在大區（Rumor.region；兩頭不同區時兩區都算）最近幾則傳聞裡隨機挑一則；沒有就寫一句，
        仍算做過。聽得到的才挑（rules.audible：別的陣營的軍情、寫給別人的個人線索聽不到）；第一季只挑傳聞板上的
        （最近 rumor_board_days 個季曆天，天下大事也一樣——打聽的是「這一帶最近」的事）。"""
        s, c = self.state, self.content
        ears, regions = ears_of(s, c), here_regions(s, c)  # 在路上時 here_regions 就是這段路兩頭的大區（beta 的 ears.regions 是空的）
        heard = [
            r for r in s.world.rumors if r.region in regions and r.time >= ears.since and audible(r, ears)
        ][-c.config.road_rumor_pool:]
        if not heard:
            return ["你沿途問了幾個人，這一帶最近沒什麼新鮮事。"]
        return [f"你沿途向人打聽，聽說：{self.rng.choice(heard).text}"]

    def _road_survey(self) -> list[str]:
        """留意地形：這段路兩頭一站以內、還沒摸清（也已開放）的地點，標成摸清（PlayerState.surveyed，大地圖上跟去過一樣
        算記得）。沒有可標的就寫一句，仍算做過。"""
        s, c = self.state, self.content
        views = atlas.views(s, c)
        found: list[str] = []
        for end in self._road_ends():
            for loc_id in (end, *(str(dest) for dest in c.locations[end].connections)):
                if views[loc_id] in ("outline", "dot") and loc_id not in found:
                    found.append(loc_id)
        if not found:
            return ["你留意了一路的地形，附近沒有什麼沒摸清的地方。"]
        s.player.surveyed |= set(found)
        return [f"你留意沿路的地形，摸清了{'、'.join(c.locations[loc_id].name for loc_id in found)}的位置。"]

    def _road_gather(self) -> list[str]:
        """路邊採集：一定機率撿到一樣一階素材；屬性照這段路兩頭的地點寫的素材（Location.materials），兩頭都沒寫就隨機。
        今天的收穫拿滿了就不翻（也不擲骰）；撿到了才算一次收穫。"""
        s, c = self.state, self.content
        if not self._road_reward_due("task"):
            return ["你留心路邊，今天已經撿夠了，沒再去翻。"]
        if self.rng.random() >= c.config.road_gather_chance:
            return ["你在路邊翻找了一陣，沒找到什麼能用的。"]
        kinds = {c.materials[m].attribute for end in self._road_ends() for m in c.locations[end].materials if m in c.materials}
        pool = [m for m in materials.by_tier(c, 1) if m.attribute in kinds] or materials.by_tier(c, 1)
        if not pool:  # 內容裡沒有一階素材：當成沒找到
            return ["你在路邊翻找了一陣，沒找到什麼能用的。"]
        self._count_road_reward("task")
        return ["你在路邊翻找了一陣。", materials.grant(s, c, self.rng.choice(pool).id)]

    def _depart(self, route: atlas.Route, mode: TravelMode) -> list[str]:
        """出發（地圖擴充設計 3.2、3.3）：趕路、疾行的體力出發時一次扣，照走法排好每一站的抵達時間。
        疾行立刻一站一站抵達；步行、趕路就在路上，之後由 sync／advance 補算抵達（見 _arrivals）。
        在路上改道、折返（路上設計 3.1）也從這裡出發：route 的第一段是半段路（origin、share 記著是哪條路、走掉幾成），
        新路程整個取代原本那一趟；原本已經扣的趕路體力不退。剛出發就折返（見 atlas.returns_at_once）不扣體力、當下就回到原地。"""
        s, c = self.state, self.content
        rerouting = s.player.journey is not None
        minutes = route.minutes
        at_once = atlas.returns_at_once(s, c, route)  # 要在換掉原本那一趟之前看：它看的是現在在路上的位置
        cost = atlas.route_stamina(s, c, route, mode)
        s.player.stamina -= cost
        legs = [0.0] if at_once else list(route.legs)
        s.player.journey = Journey(
            mode=mode, path=list(route.path), arrive_at=atlas.arrival_times(s.world.time, legs, mode),
            origin=route.origin, share=route.share,
        )
        if self._draft is not None:
            self._draft.tag = "立刻折返" if at_once else atlas.MODES[mode] + atlas.mode_when(minutes, mode)
            if cost:
                self._draft.changes.append(f"體力 -{cost}")
        if mode == "dash" or at_once:
            return self._arrivals()
        left = self._real_minutes(s.player.journey.arrive_at[-1] - s.world.time)
        verb = "改道" if rerouting else "動身"
        msg = f"你{verb}{atlas.MODES[mode]}前往{c.locations[route.path[-1]].name}，現實約 {left} 分鐘後抵達。"  # 只寫現實的倒數（FB-062）
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
        client = None if own else self._quick_client()  # sync／advance 的抵達（計時器、備料都拿著行動鎖）不叫模型；只有疾行在玩家自己這次行動裡
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
                stop = j.path[j.reached]
                came_from = j.origin if j.reached == 0 and j.origin is not None else s.player.location
                j.reached += 1
                # 到了另一站：換段，路上小事重新可做，也可能看見路上見聞。掉頭回到剛離開的那一站不算換段、也不擲見聞
                # （剛出發就折返不花時間也不花體力，不能拿來刷見聞）
                new_leg = stop != s.player.location
                if new_leg:
                    s.player.leg_actions = set()
                msgs += self._arrive(stop, final=j.reached > j.last, client=client)
                if new_leg and not c.locations[came_from].prologue_only:  # 出師那段路不抽路上見聞
                    msgs += self._road_sight(c.locations[came_from].road_to(stop), stop, when)
            done = j.reached > j.last or s.world.ended
            if done:
                s.player.journey = None
                if s.player.location != j.path[-1]:
                    reason = "賽季落幕" if s.world.ended else "喊停"
                    self._draft.tag = f"{reason}，停在 {c.locations[s.player.location].name}"
            if own:
                entry = self._draft.entry(when, msgs)
                if done or entry.lines or entry.changes or entry.guide:  # 只到了中途的站、又沒有別的事（連引導也沒有），不另寫一則
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
        before = s.player.tutorial_step
        s.player.location = loc_id
        s.player.visited.add(loc_id)
        text = self.location_text()
        if final and is_revisit and not dest.important and client is not None:
            flourish = flavor.polish_revisit(client, dest.name, dest.describe(s.world.flags))
            if flourish:
                text = f"{text}\n\n{flourish}"
        self._hide(text)
        # 糧車到了終點（路過也算）先交糧，再照原本的新手引導與門檻（計畫 T6）；呼叫的先後不能換
        convoy = self._convoy_arrives(loc_id)
        guide = self._guide(note_action(s, c, self.world, "move"))  # 出師的盤纏（序章步驟的獎勵）是這一趟路的結果，回在這裡
        thresholds = check_thresholds(s, c, self.world, client, now=self.now)
        t = c.tutorial
        left = [t.leave_text] if t.location is not None and before < t.prologue_steps <= s.player.tutorial_step and t.leave_text else []
        # 出師、抵達起點：「剛剛」先接一句草廬已經看不見了（新手引導設計 10.3），再寫盤纏（T7 審查 M4）
        return [text] + convoy + left + guide + thresholds

    def _road_sight(self, road: RoadKind, loc_id: str, when: float | None = None) -> list[str]:
        """路上見聞（路上設計第五節）：抵達一站時有 road_sight_chance 的機會，從符合這段路的種類、剛抵達那一站所在大區的
        見聞裡平均挑一則（最近看過的 road_sight_recent 則先排除，池子不夠才重複）。文字寫進這次抵達的紀錄，小收穫照慣例
        接在後面。寫好的文字、不呼叫模型，下線補算時照樣發生。機率是 0 或池子是空的時候連骰子都不擲。
        有收穫的見聞受每天上限管（企劃者 2026-10-03 決定，跟路上小事各算各的）：抵達那一天（when，下線補算時是當時的
        抵達時間）的 "sight" 收穫拿滿了，給銀兩、素材的見聞就不挑（文字寫的就是拿到東西），給心得的照寫文字、不給心得；
        真的給了才算一次。沒有收穫的見聞不算次數。"""
        s, c = self.state, self.content
        day = int(when // DAY) + 1 if when is not None else current_day(s)
        capped = not self._road_reward_due("sight", day)
        region = atlas.region_of(c, loc_id)
        area = region.id if region is not None else None
        pool = [
            sight for sight in c.road_sights.values()
            if (not sight.roads or road in sight.roads) and (not sight.regions or area in sight.regions)
            and not (capped and (sight.effect.materials or sight.effect.stats.get("silver")))
        ]
        chance = c.config.road_sight_chance
        if not pool or chance <= 0 or self.rng.random() >= chance:
            return []
        recent = s.player.recent_sights
        sight = self.rng.choice([x for x in pool if x.id not in recent] or pool)
        keep = c.config.road_sight_recent
        s.player.recent_sights = (recent + [sight.id])[-keep:] if keep else []
        rewarded = bool(sight.effect.stats or sight.effect.materials)  # 載入檢查保證見聞只會有這兩種效果
        if not rewarded or capped:
            return [sight.text]
        self._count_road_reward("sight", day)
        return [sight.text] + apply_effect(sight.effect, s, c, self.world, push=self.push_trend)

    def _real_minutes(self, world_seconds: float) -> int:
        """世界時鐘的一段秒數，換成給玩家看的「現實」整分鐘（至少 1 分，.5 進位）：世界秒 ÷ time_scale ＝ 現實秒（FB-062）。"""
        return atlas.whole_minutes(max(0.0, world_seconds) / self.content.config.time_scale / 60)

    def _journey_line(self) -> str:
        """在路上的那一句（狀態列）：「往寶洞（步行），現實約 8 分鐘後抵達；下一站湖邊」。
        只寫現實的倒數，不寫抵達的季曆時刻（FB-062）：季曆跑得比現實快，「第 8 週・週五 12:19 抵達」配上「還要約 1 分鐘」
        兩種時間混在一行，玩家算不出來；季曆時刻已經在狀態列上一行。"""
        s, c = self.state, self.content
        j = s.player.journey
        left = self._real_minutes(j.arrive_at[j.last] - s.world.time)
        line = f"往{c.locations[j.path[j.last]].name}（{atlas.MODES[j.mode]}），現實約 {left} 分鐘後抵達"
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
        """安排前往（大地圖詳情欄的按鈕）：照路程最短的路線出發，走法見 _depart。在路上也行（路上設計 3.1）：
        取掉頭與繼續兩種走法裡路程短的（見 atlas.way_to），新路程從路中間出發。"""
        refusal = self.travel_refusal(dest_id, mode)
        if refusal is not None:
            return self._log([f"（{refusal}。）"])
        s, c = self.state, self.content
        route = atlas.way_to(s, c, dest_id)
        s.battle_card = None
        s.player.guide_done = []
        self._draft = Draft(atlas.journey_title(c, route.path))
        stamina = s.player.stamina
        try:
            msgs = self._depart(route, mode)
            msgs += self._hear_after_stamina(stamina)
            msgs += ranks.check_summons(s, c)  # 疾行送到糧車也記貢獻（計畫 T5）
            msgs += self._report_seat()  # 同上：第四階席次的帳也要抄（正式版丁）
            self._check_hints()  # 出發之後看一遍（疾行立刻到：抵達的地方教基礎武學、站著大勢人物，新手引導計畫三）
            journal.add_entry(s, self._draft.entry(s.world.time, msgs))
        finally:
            self._draft = None
        self._save_season()
        return self._log(msgs)

    def travel_refusal(self, loc_id: str, mode: TravelMode = "walk") -> str | None:
        """用這種走法安排前往這裡，不行的原因；可以時為 None。server.py 拿它分辨「沒能出發」。"""
        if self._preparing():
            return PREPARING_TEXT
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
            success = roll_check(choice.check, s, c, self.world, self.rng)
            tag, line = check_result_line(success)  # 一律是本人：不寫誰出手（企劃者 2026-10-05）
            msgs.append(line)
            self._outcome(tag, line)
            return msgs + self._apply(choice.effect if success else failed(choice.fail_effect, c))
        return msgs + self._apply(choice.effect)

    def _event_battle(self, event: Event, choice: Choice) -> list[str]:
        s, c = self.state, self.content
        squad = c.squads[choice.combat]
        judged = self._judged(squad)  # 打頭目這種大場面：有鎖外的判讀就用（武學與成長設計 8.3）
        result = self._fight_with(squad, judged, dodge=False)  # 劇情戰的勝敗是人寫好的：不閃（最終審查 I1）
        record = battlelog.new_record(s, c, self.world, squad, result, "event", event.title)
        record.notes += self._style_note(squad, result)
        self._narrate(record, result, judged)
        # 回合照開打時的陣容與身法演，所以要在發獎勵、套效果之前：效果可能加身法、教武學、給同伴或部下，
        # 不能回頭改寫這一場（例如 wolves 打贏身法 +1，不能變成「因為獎勵才先出手」）。
        # 劇情戰不扣氣血：對手的出手不寫數字（計畫三 G5）
        self._play_rounds(record, squad, result.tier, None, self._hp_facts())  # 氣血照開打時的樣子：厚拉高的下限這一場也起了作用
        won = result.tier in team.WIN_TIERS
        rewards = self._battle_rewards(squad, record) if won else []
        effect = choice.effect if won else failed(choice.fail_effect, c)  # 打輸另扣的體力減半，同檢定失敗（企劃者裁決 E6）
        story = apply_effect(effect, s, c, self.world, push=self.push_trend)
        changes, notes = battlelog.split_changes(story, for_record=True)
        record.changes += changes
        record.notes += notes
        story += self._seize(record)
        msgs = [self._file_battle(record)] + rewards + story
        if effect.next_event:
            msgs += self._present(c.events[effect.next_event])
        return msgs

    def _apply(self, effect: Effect) -> list[str]:
        msgs = apply_effect(effect, self.state, self.content, self.world, push=self.push_trend)
        if effect.text and prologue_rules.active(self.state, self.content):
            for msg in msgs:  # 草廬四景的結果文字已經寫了「你悟到了「…之意境」」，引擎的「你悟得了「…」的意境」是同一件事：紀錄只留前一句
                if msg.startswith("你悟得了「"):
                    self._hide(msg)
        if effect.next_event:
            msgs += self._present(self.content.events[effect.next_event])
        return msgs

    # ── 閉關、練功、療傷、設定 ────────────────────────────

    @contextlib.contextmanager
    def phase_memo(self):
        """一次畫面建構（server.main_view）的範圍：這一段裡「賽季籌備中嗎」只向共用狀態讀一次。season_phase() 要把整份
        全服狀態（含進行中的決戰）讀出來，而狀態列、選單、「剛剛」、說書人的對話框建一次畫面各問一次；輪詢（每個在線的人
        每 10 秒一次）人一多就吃掉行動鎖的時間（壓測 2026-10-06）。
        記住的只活在這個範圍裡，出了範圍（含畫面建到一半丟例外）就丟掉，所以下一個動作、下一次畫面都讀最新的：
        籌備中只會被管理者開季、換季改掉，那兩個是動作，不會發生在一次畫面建構的中間。範圍可以巢狀，用最外層那一份。
        只有 _preparing 讀這份記住的；動作要的階段（running、resting）照舊直接問共用狀態。"""
        outermost = self._preparing_memo is None
        if outermost:
            self._preparing_memo = []  # 空的＝範圍開了、還沒讀過
        try:
            yield
        finally:
            if outermost:
                self._preparing_memo = None

    def _preparing(self) -> bool:
        """賽季籌備中（管理者還沒開季）：玩家什麼都不能做。在 phase_memo 的範圍裡只讀一次。"""
        memo = self._preparing_memo
        if memo is None:
            return self.world.season_phase() == "preparing"
        if not memo:
            memo.append(self.world.season_phase() == "preparing")
        return memo[0]

    def _idle(self) -> bool:
        s = self.state
        return (
            not self._preparing() and not s.world.ended and s.pending_event is None and s.player.busy_until is None
            and s.player.resting_since is None and s.player.journey is None and not s.player.picking_audience
            and s.player.fs_asking is None  # 伏筆的最後一步正在答題：跟事件待處理一樣，先答完或作罷
            and s.player.sensing is None  # 有所感、還沒了結：跟事件待處理一樣
        )

    def seclusion_refusal(self) -> str | None:
        """閉關現在做不做得了（序章裡不閉關，prologue.seclude_problem）：修練頁的閉關鈕灰掉、寫它，跟 seclude 的拒絕同一個判斷。"""
        return prologue_rules.seclude_problem(self.state, self.content)

    def seclude(self, hours: int) -> list[str]:
        p = self.state.player
        refusal = self.seclusion_refusal()
        if refusal is not None:
            return self._log([refusal])  # 跟練成、熔煉的序章拒絕一樣：只回一句話，不寫紀錄
        if not self._idle():
            msgs = ["你現在無法閉關。"]
            self._write("閉關", msgs)
            return self._log(msgs)
        hours = max(1, min(12, int(hours)))
        self.state.battle_card = None
        p.busy_until = self.state.world.time + hours * HOUR
        p.seclusion_start = self.state.world.time
        real_hours = hours / self.content.config.time_scale  # 閉關的小時是世界時鐘的小時；寫給玩家看的是現實小時（FB-062）
        msgs = [f"你閉關靜修，預計現實 {real_hours:g} 小時後出關；閉關期間氣血回復加倍。"]
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

    def forge_request(
        self, art_id: str | None, insight_ids: list[str], other_art: str | None = None, named_outside: bool = False,
    ) -> naming.NamingRequest | None:
        """開爐首次取名或挑選的 A 段（呼叫端在行動鎖內、很快地呼叫；server.prepare_forge、bot_policy.tend_arts）：這一爐要不要模型？
        要就回送模型的單子（naming.NamingRequest），由呼叫端在鎖外交給 naming.generate（B 段），再進鎖把結果交給
        forge(..., proposed=...)（C 段）。單子有兩種：沒人合過、長新的 → 取名（choices 是空的）；合到舊的、候選兩個以上
        → 從候選挑一個（choices 是候選的名字，見 fusion.forge_request）。不要的時候是 None：這個 Game 沒有 client
        （例如伺服器假人鎖內的 Game）而且呼叫端不會自己叫模型、賽季籌備中、這一爐會被拒絕、配方已經有人登記、合到舊的而且
        只有一個候選。只讀、不改狀態——跟 dialogue_request 同一個做法。other_art 有、insight_ids 空的是武學＋武學。
        named_outside：呼叫端會在鎖外自己叫模型（伺服器假人程式：它的 Game 沒有 client，B 段用 bot_runner 自己的 client
        叫 naming.generate），照樣開單。"""
        if (self.client is None and not named_outside) or self._preparing():
            return None
        if prologue_rules.fuse_problem(self.state, self.content, art_id, insight_ids, other_art) is not None:
            return None  # 序章裡會被擋下的一爐：不開取名的單子（forge 照常回那句話）
        return fusion.forge_request(self.state, self.content, self.world, art_id, insight_ids, other_art=other_art)

    @_not_while_preparing
    def forge(
        self, art_id: str | None, insight_ids: list[str], proposed: tuple[str | None, str] | None = None,
        other_art: str | None = None,
    ) -> list[str]:
        """煉製頁的開爐：一門武學＋一個意境、兩門武學＝合成，兩個意境（可以是同一個）＝合併（見 fusion.py）。
        proposed 是鎖外先取好的（名字, 說明）（C 段，見 forge_request）：這裡整個重驗（A 段之後意境可能熔掉、心得或體力
        可能花掉、配方可能被別人或同一個人的另一個請求登記了），名字再過一次過濾、登記時原子判斷重名，過不了走退路字表；
        給了 proposed 就不會在這裡叫模型（伺服器與假人程式一律給，不需要模型時是 (None, "")）。沒給（整季機器人、腳本、測試）
        首次出現的配方照舊在這裡叫模型，那是在行動鎖內，所以用 _quick_client 的短逾時複本，取不到名字就走退路字表。
        江湖紀錄的標題照煉製頁寫「煉製」（FB-047），做成了才寫，被拒絕只回一句話、什麼都不收。
        三種合成都花心得與體力（設計 12.1）：花了的體力跟心得一起寫在這一則的數值變化上。"""
        refusal = prologue_rules.fuse_problem(self.state, self.content, art_id, insight_ids, other_art)  # 序章只准照劇本合成
        if refusal is not None:
            return self._log([refusal])
        xinde, stamina = self._xinde(), self.state.player.stamina
        # 新武學自己那一份的品質照機率擲（Config.fuse_quality_odds）；序章那一爐照劇本固定下品，不擲
        rng = None if prologue_rules.fuse_base(self.state, self.content) is not None else self.rng
        if art_id and other_art and not insight_ids:
            art, msgs = fusion.blend(
                self.state, self.content, self.world, self._quick_client(), art_id, other_art, proposed=proposed, rng=rng,
            )
            tag = f"合成【{art.name}】" if art is not None else None
        elif art_id and not other_art and len(insight_ids) == 1:
            art, msgs = fusion.fuse(
                self.state, self.content, self.world, self._quick_client(), art_id, insight_ids[0], proposed=proposed, rng=rng,
            )
            tag = f"合成【{art.name}】" if art is not None else None
            if art is not None:  # 草廬這一步寫了結果那一句（設計 10.3「合成之後」）就用它，後面接武學自己的說明（T7 審查 M1）
                insight = insights.resolve(insight_ids[0], self.content, self.world)
                line = prologue_rules.after_line(self.state, self.content, 意境=insight.name if insight else "", 武學=art.name)
                if line is not None:
                    msgs[0] = line + (f"\n{art.note}" if art.note else "")
        elif not art_id and not other_art and len(insight_ids) == 2:
            insight, msgs = fusion.merge(self.state, self.content, self.world, self._quick_client(), *insight_ids, proposed=proposed)
            tag = f"合併「{insight.name}」" if insight is not None else None
        else:
            return self._log(["放一門武學和一個意境、或放兩門武學（合成），或放兩個意境（合併）。"])
        out = self._log(msgs)
        if tag is not None:
            self._save_season()  # 第一次合出帶特別功效的武學會記一則傳聞（fusion._special_rumor，13.4）；傳聞在共用賽季裡，要存回去
            spent = round(stamina - self.state.player.stamina)  # 三種合成都花體力：數值變化寫在紀錄上，跟修練一樣
            out += self._menxia_entry(  # 結果那一句（第一則訊息）也寫進這一則的敘事，拿到新東西的那一行才配得到 journal._NEW_THING（FB-073）
                tag, xinde, guide=True, title=journal.CRAFT, extra=[f"體力 -{spent}"] if spent > 0 else None,
                lines=out[:1],
            )
        return out

    def forge_line(self, art_id: str | None, insight_ids: list[str], other_art: str | None = None) -> str:
        return skillview.forge_line(self.state, self.content, self.world, art_id, insight_ids, other_art=other_art)

    @_not_while_preparing
    def cultivate(self, art_id: str, use_legend: bool = False) -> list[str]:
        """修練：武學＋它融的意境，衝下一品（見 cultivation.py）。花體力。真的擲了骰（成功或失敗）才寫江湖紀錄；
        被拒絕（意境熔掉了、沒融過意境、已經絕學、體力不足、沒有這門武學）只回一句話（武學與成長計畫 F12）。
        use_legend：玩家勾了「服下破境丹」；真的服了才在紀錄裡寫「破境丹 -1」（丹沒了、下一步不是絕學都照一般的機率擲）。"""
        sure = prologue_rules.sure_rng(self.state, self.content)  # 序章第 6 步：第一次修練一定升品，也不看成數門檻（劇本只練到第三成）
        problem = prologue_rules.cultivate_problem(self.state, self.content) or cultivation.cultivate_problem(
            self.state, self.content, self.world, art_id, gate=sure is None, use_legend=use_legend,
        )
        if problem is not None:
            return self._log([problem])
        xinde, stamina, pills = self._xinde(), self.state.player.stamina, self.state.player.legend_items
        msgs = cultivation.cultivate(
            self.state, self.content, self.world, art_id, sure or self.rng, use_legend, gate=sure is None,
        )
        spent = round(stamina - self.state.player.stamina)  # 輸了也花了體力：數值變化寫在紀錄上，跟別的行動一樣
        taken = pills - self.state.player.legend_items
        extra = ([f"體力 -{spent}"] if spent > 0 else []) + (
            [f"{self.content.config.legend_item_name} -{taken}"] if taken > 0 else []
        )
        # 結果標記是擲骰的結果（「【X】修練…」，一定以【開頭）；前面服丹、沒服的提示與後面定名的話都不是
        tag = next((m for m in msgs if m.startswith("【")), msgs[0])
        won = next((i for i, m in enumerate(msgs) if "修練有成，從" in m), None)
        art = team.resolve_art(art_id, self.content, self.world)
        line = prologue_rules.after_line(self.state, self.content, 武學=art.name if art else "") if won is not None else None
        if line is not None:  # 草廬這一步寫了結果那一句（設計 10.3「修練之後」）：它就是結果標記，也是敘事那一句（T7 審查 M1）
            msgs[won] = tag = line
        msgs = self._log(msgs)
        self._menxia_entry(tag, xinde, guide=True, action="cultivate", extra=extra or None)
        return msgs

    def mastery_request(self) -> naming.NamingRequest | None:
        """定名的 A 段（伺服器假人程式在行動鎖內呼叫，見 cultivation.master_request）：只讀。賽季籌備中是 None。"""
        if self._preparing():
            return None
        return cultivation.master_request(self.state, self.content, self.world)

    @_not_while_preparing
    def name_mastered(self, name: str) -> list[str]:
        """替第一個練成絕學的武學取正式名字；定成了才寫江湖紀錄，江湖史寫進共用賽季所以要存回
        （名字不合格、被用掉、沒有等著取名的武學都只回一句話）。"""
        xinde, pending = self._xinde(), self.state.player.naming
        msgs = self._log(cultivation.name_mastered(self.state, self.content, self.world, name))
        if pending is not None and self.state.player.naming is None:
            self._menxia_entry(msgs[0], xinde)
            self._save_season()
        return msgs

    @_not_while_preparing
    def switch_art(self, art_id: str) -> list[str]:
        """改練：把功法庫裡的一門換上身（見 team.switch_art）。"""
        xinde = self._xinde()
        msgs = self._log(team.switch_art(self.state, self.content, self.world, art_id))
        # 江湖紀錄的標記是「你改練【…】」那一句；換上後內外搭配變了時最後多一句（FB-088），不拿它當標記
        tag = next((m for m in reversed(msgs) if m.startswith("你改練")), msgs[-1] if msgs else "改練")
        self._menxia_entry(tag, xinde)
        return msgs

    @_not_while_preparing
    def melt_art(self, art_id: str) -> list[str]:
        """熔煉：功法庫裡的一門熔成心得（見 library.melt_art）；身上正在練的不能熔。熔成了才寫江湖紀錄，
        被拒絕（身上正在練的、庫裡沒有）只回一句話（武學與成長計畫 F12）。"""
        xinde, held = self._xinde(), library.held_count(self.state)
        only = prologue_rules.melt_only(self.state, self.content)  # 序章只准熔師父說的那一門（None＝不限）
        msgs = library.melt_art(self.state, self.content, self.world, art_id, only=only)
        if library.held_count(self.state) < held:  # 看有沒有真的少一門，不看心得：下品第一成的武學熔了只退 0 點
            line = prologue_rules.after_line(self.state, self.content, 心得=self._xinde() - xinde)  # 草廬這一步寫了結果那一句（設計 10.3「熔了之後」）就用它（T7 審查 M1）
            if line is not None:
                msgs[0] = line
            relearn = skillview.relearn_note(self.state, self.content, art_id)  # 基礎武學熔了還能重學：結果最後一句指路（FB-081）
            msgs = self._log(msgs + [relearn] if relearn else msgs)
            self._menxia_entry(msgs[0], xinde, guide=True, action="melt")  # 序章第 10 步（新手引導計畫一）
            return msgs
        return self._log(msgs)

    @_not_while_preparing
    def melt_insight(self, insight_id: str) -> list[str]:
        """把一個意境化成心得（見 library.melt_insight）；同 melt_art，熔成了才寫江湖紀錄。"""
        refusal = prologue_rules.melt_insight_problem(self.state, self.content)  # 序章的意境是合成要用的，熔了後面就走不下去
        if refusal is not None:
            return self._log([refusal])
        xinde, held = self._xinde(), library.held_count(self.state)
        msgs = self._log(library.melt_insight(self.state, self.content, self.world, insight_id))
        if library.held_count(self.state) < held:
            self._menxia_entry(msgs[0], xinde)
        return msgs

    def practice_refusal(self, kind: str) -> str | None:
        """練成這一欄現在做不做得了（序章只准練新得的那一門，prologue.practice_problem）：不能時回寫給玩家看的原因，
        修練頁的練成鈕灰掉、寫它；跟 practice 的拒絕同一個判斷。序章外是 None（心得夠不夠、練滿了沒由網頁照 slot_cards 自己看）。"""
        return prologue_rules.practice_problem(self.state, self.content, self.world, kind)

    @_not_while_preparing
    def practice(self, kind: str) -> list[str]:
        """練成：身上這一門加深一成，花心得、累積受傷風險（見 team.practice）。"""
        refusal = prologue_rules.practice_problem(self.state, self.content, self.world, kind)  # 序章只准練新得的那一門
        if refusal is not None:
            return self._log([refusal])
        xinde = self._xinde()
        member = self.state.player.member
        level_slot = "neigong_level" if kind == "內功" else "wugong_level"
        has_art = getattr(member, "neigong_id" if kind == "內功" else "wugong_id") is not None
        before = getattr(member, level_slot)
        msgs = self._log(team.practice(
            self.state, self.content, self.world, kind, self.rng, safe=prologue_rules.active(self.state, self.content),
        ))
        # FB-007：引導那一步要的是「真的練了一成」：沒學過就練不到、心得不夠沒練成，都不算；
        # 已經第十成（練無可練）也算（可能在走到這一步前就練滿了，只認「真的加一成」會永遠卡住）。
        counted = has_art and (getattr(member, level_slot) > before or before >= team.MAX_LEVEL)
        if not counted:  # 練不成（還沒學、心得不足）：什麼都沒變，只回那一句話，不寫「修練」紀錄（武學與成長計畫 F12）
            return msgs
        return msgs + self._menxia_entry(msgs[0], xinde, guide=True)

    @_not_while_preparing
    def heal(self) -> list[str]:
        xinde = self._xinde()
        msgs = self._log(team.heal(self.state, self.content, self.state.player.member))
        self._menxia_entry(msgs[0] if msgs else "療傷", xinde)
        return msgs

    @_not_while_preparing
    def take_stamina_pill(self, *, pill_only: bool = False) -> list[str]:
        """服一顆回體丹（企劃者 2026-10-07）：體力回 stamina_pill_restore，夾在上限。沒有丹、體力是滿的、還在草廬序章裡
        （序章的體力是照步驟算好的：探索、合成、修練剛好用完，接著才教打坐，prologue.start_stamina）都只回一句話、不收丹。
        吃了才寫江湖紀錄（數值變化寫體力與丹）。打坐中也能吃：只是多回一截，打坐照舊。
        測試期間 Config.beta_free_refill 打開時，同一個入口改成免費補滿（_refill_stamina），不收丹。pill_only 是給假人與
        整季機器人的：他們照舊只吃丹（bot.take_pill），不吃這份測試期間的免費補滿；開關關著時 pill_only 沒有作用。"""
        p, cfg = self.state.player, self.content.config
        if cfg.beta_free_refill and not pill_only:
            return self._refill_stamina()
        name = cfg.stamina_pill_name
        if p.stamina_pills <= 0:
            return self._log([f"你身上沒有{name}了。"])
        if prologue_rules.active(self.state, self.content):
            return self._log([f"草廬裡先照師父說的做，{name}留著出了草廬再吃。"])
        if p.stamina >= cfg.stamina_max:
            return self._log(["體力是滿的，這時候服丹是糟蹋。"])
        before = p.stamina
        p.stamina = min(float(cfg.stamina_max), p.stamina + cfg.stamina_pill_restore)
        p.stamina_pills -= 1
        msgs = [f"你服下一顆{name}，一股暖意自丹田散開，精神為之一振。"]
        journal.add_entry(self.state, JournalEntry(
            time=self.state.world.time, title=f"服下{name}", lines=msgs,
            changes=[f"體力 +{round(p.stamina - before)}", f"{name} -1"],
        ))
        return self._log(msgs + [f"體力 +{round(p.stamina - before)}（{name}還剩 {p.stamina_pills} 顆）"])

    def _refill_stamina(self) -> list[str]:
        """測試期間一鍵補滿體力（Config.beta_free_refill，企劃者 2026-10-07；take_stamina_pill 在開關打開時走這裡）：
        補到 stamina_max（狀態列顯示的那個上限），不收丹、不收銀兩、不限次數。規矩跟丹一模一樣：還在草廬序章裡、體力已經是滿的
        都只回一句話（不寫紀錄、不動東西）；籌備中由 take_stamina_pill 的 _not_while_preparing 擋；其餘不看——打坐中、閉關中、
        在路上都照補、不動那個狀態（丹也不看 resting_since、busy_until、journey）。打坐中補滿：下一次同步看到體力滿了才收功起身
        （_advance_player_local），跟丹把體力吃到頂一樣。補成了寫一則江湖紀錄（數值變化只寫體力，沒有丹的那一項）。"""
        p, cfg = self.state.player, self.content.config
        if prologue_rules.active(self.state, self.content):
            return self._log([REFILL_HUT])
        if p.stamina >= cfg.stamina_max:
            return self._log([REFILL_FULL])
        gained = f"體力 +{int(cfg.stamina_max) - int(p.stamina)}"  # 狀態列顯示 int(體力)：寫的數字就是條子實際走的那一段（體力有小數是常態）
        p.stamina = float(cfg.stamina_max)
        journal.add_entry(self.state, JournalEntry(
            time=self.state.world.time, title=REFILL_TITLE, lines=[REFILL_LINE], changes=[gained],
        ))
        return self._log([REFILL_LINE, gained])

    @_not_while_preparing
    def allocate_stat(self, stat: str) -> list[str]:
        """把升級得到的屬性點分配到一項（武學與成長設計 6.2）：每項最高 stat_cap，這個版本不能洗點。
        配成了才寫江湖紀錄，連按幾次（玩家、假人都一樣）併成一則「配點」；被拒絕（沒有點、到頂、沒這項屬性）
        只回一句話，不留紀錄（武學與成長計畫 F12）。"""
        p, cfg = self.state.player, self.content.config
        name = cfg.stat_names.get(stat, stat)
        if stat not in team.COMBAT_STATS:
            return self._log(["（沒有這項屬性。）"])
        if p.stat_points <= 0:
            return self._log(["沒有可以分配的屬性點，升級才會有。"])
        if p.stats.get(stat, 0) >= cfg.stat_cap:
            return self._log([f"{name}已經到頂（{cfg.stat_cap}）。"])
        p.stat_points -= 1
        p.stats[stat] = p.stats.get(stat, 0) + 1
        journal.add_entry(
            self.state, JournalEntry(time=self.state.world.time, title=journal.ALLOCATE, changes=[f"{name} +1"]),
            merge=True,
        )
        left = f"（還有 {p.stat_points} 點可以分配）" if p.stat_points else ""  # 最後一點不寫「還有 0 點」
        self._guide(note_action(self.state, self.content, self.world, "allocate"))  # 序章第 9 步（新手引導計畫一）
        self._check_hints()  # 博聞加了持有上限會變（h_cap 的條件）：配成了之後看一遍（新手引導計畫三）
        return self._log([f"{name} +1{left}"])

    def _xinde(self) -> int:
        return self.state.player.stats.get("xinde", 0)

    def _menxia_entry(
        self, tag: str, xinde_before: int, guide: bool = False, title: str = journal.PRACTICE,
        extra: list[str] | None = None, lines: list[str] | None = None, action: str = "practice",
    ) -> list[str]:
        """修練頁、煉製頁的動作寫進江湖紀錄（同一種連續的併成一則）。標題照底部分頁的名字：煉製寫「煉製」，
        鍛鍊、療傷、改練寫「修練」（FB-047；以前都寫「門下」，煉製會併進前面那則鍛鍊）。
        lines：這個動作要留在敘事裡的話（煉製的結果那一句，FB-073）；不給就只有結果標記，結果標記本身就是那句話（修練、療傷……）。

        guide=True：這個動作算一次「練功」（煉製、鍛鍊；序章裡還有修練、熔煉，action 是 cultivate、melt），順便看新手引導有沒有完成（FB-024）。完成了，
        note_action 回來的「✔ 引導完成」、獎勵與說書人的下一步記在這一則的 guide（江湖紀錄看得到），給對話框
        （guide_done），不進修練、煉製頁的訊息與「剛剛」（引導重做設計 8.1.3）。回傳一律是空串列。"""
        delta = self._xinde() - xinde_before
        changes = ([f"心得 {delta:+d}"] if delta else []) + (extra or [])  # extra：心得以外的數值變化（修練花的體力）
        self.state.player.guide_done = []
        notes = note_action(self.state, self.content, self.world, action) if guide else []
        changes += [str(n) for n in notes if isinstance(n, HutReward)]  # 序章步驟的獎勵是這次動作的結果（T7 審查 M4）
        notes = [n for n in notes if not isinstance(n, HutReward)]
        self._note_guide(notes)  # 引導的訊息記在這一則的 guide、給對話框，不進修練頁的訊息（引導重做設計 8.1.3）
        entry = JournalEntry(
            time=self.state.world.time, title=title, tag=tag, lines=list(lines or []), changes=changes, guide=notes,
        )
        journal.add_entry(self.state, entry, merge=True)
        self._check_hints()  # 修練頁、煉製頁的動作做完看一遍（新手引導計畫三）：修練失敗留下熟練度、合成、熔煉改變持有，說的話接在這一則的 guide
        return []

    # ── 門下與隊伍 ────────────────────────────────────────

    def roster_lines(self) -> list[tuple[str, str]]:
        return roster.roster_lines(self.state, self.content, self.world)

    def owned_companions(self) -> list[str]:
        return roster.owned_companions(self.world, self.state.player.name)

    # 名冊第一列是本人（PLAYER）：本人永遠出戰，加入、移出都只回一句話，隊伍裡不會多出一個 "player"
    SELF_IN_TEAM = "本人一直都在隊伍裡，不用加入，也不能移出。"
    FOLLOWER_IN_TEAM = "部下一直跟著你出戰，不用加入，也不能移出。"  # 計畫 T5

    @_not_while_preparing
    def add_to_team(self, companion_id: str) -> list[str]:
        if companion_id == PLAYER:
            return self._log([self.SELF_IN_TEAM])
        if companion_id.startswith(team.FOLLOWER_KEY):
            return self._log([self.FOLLOWER_IN_TEAM])
        return self._log(team.add_to_team(self.state, companion_id))

    @_not_while_preparing
    def remove_from_team(self, companion_id: str) -> list[str]:
        if companion_id == PLAYER:
            return self._log([self.SELF_IN_TEAM])
        if companion_id.startswith(team.FOLLOWER_KEY):
            return self._log([self.FOLLOWER_IN_TEAM])
        return self._log(team.remove_from_team(self.state, companion_id))

    # ── 門下頁面：武學說明 ──────────────────────────────────

    def skill_detail(self, kind: str) -> str:
        return skillview.detail(self.state, self.content, self.world, kind)

    def art_detail(self, art_id: str) -> str:
        """這個角色擁有的一門功法的功法卡（FB-006；功法庫先看卡再改練）。熟練度：配在身上的看身上
        那一欄，功法庫裡的看換下來時存的 art_levels（沒存過從第一成算，跟 team.switch_art 一致）。
        不是自己的、或內容與共用世界裡都找不到時回一句話。"""
        level = library.level_of(self.state, art_id)
        art = None if level is None else team.player_art(self.state, self.content, self.world, art_id)
        if art is None:
            return "（找不到這門功法。）"
        return skillview.art_card(
            art, level, parent_names=skillview.parent_names(art, self.content, self.world),
            trait_line=traits.card_line(self.content, art),
            compare_line=team.compare_with_worn(self.state, self.content, self.world, art),  # W6
        )

    def member_card(self, key: str) -> str:
        return skillview.member_card(self.state, self.content, self.world, key)

    def menxia_rules(self) -> str:
        return skillview.rules_line(self.content)

    def attribute_note(self) -> str:
        """修練頁與煉製頁摺起來的「屬性有什麼用」那一句（W2）。"""
        return skillview.attribute_line(self.content)

    def bag_text(self) -> str:
        return skillview.bag_text(self.state, self.content)

    def holdings(self) -> dict:
        """武學與意境的持有數與上限（武學與成長設計 4.5）。"""
        return {
            "count": library.held_count(self.state),
            "cap": library.cap_of(self.state, self.content),
        }

    def art_rows(self) -> list[dict]:
        return skillview.art_rows(self.state, self.content, self.world)

    def insight_rows(self) -> list[dict]:
        return skillview.insight_rows(self.state, self.content, self.world)

    def heal_button(self) -> dict:
        """修練頁療傷鈕按不按得下去與不能按的原因（FB-082，見 skillview.heal_button）。"""
        return skillview.heal_button(self.state, self.content)

    def naming_row(self) -> dict | None:
        """等著自己取正式名字的那一門（第一個練成絕學）；沒有是 None。"""
        art_id = self.state.player.naming
        art = team.resolve_art(art_id, self.content, self.world) if art_id else None
        return None if art is None else {"id": art_id, "name": art.name}

    # ── 戰鬥紀錄 ──────────────────────────────────────────

    def battle_card(self) -> str | None:
        record = battlelog.find(self.state, self.state.battle_card)
        # 升級那一行的「可配 N 點」照現在的點數寫（配了就少），跟狀態列同一個數（FB-074）；
        # 打完接著有事件待處理時不畫那一行（事件的選項要留在第一屏，FB-076）
        return battlelog.card_text(
            record, self.stamp, points=self.state.player.stat_points, event_waiting=self.state.pending_event is not None,
        ) if record else None

    def battle_card_id(self) -> int | None:
        record = battlelog.find(self.state, self.state.battle_card)
        return record.id if record else None

    def latest_battle_id(self) -> int | None:
        return self.state.battles[0].id if self.state.battles else None

    def battle_list(self) -> list[tuple[str, int]]:
        return [(battlelog.list_label(r, self.stamp), r.id) for r in self.state.battles]

    def battle_detail(self, record_id: int | None = None) -> str:
        s = self.state
        record = battlelog.find(s, record_id) or (s.battles[0] if s.battles else None)
        return battlelog.detail_text(record, self.stamp) if record else battlelog.NO_RECORD

    def notice(self, text: str, title: str = "提醒") -> list[str]:
        self._write(title, [text])
        return self._log([text])

    def set_anonymous(self, value: bool) -> None:
        self.state.player.anonymous = bool(value)

    def skip_tutorial(self) -> list[str]:
        steps = len(tutorial_steps(self.state, self.content))
        if (self.state.player.tutorial_step >= steps and not enlist.active(self.state, self.content)
                and not enlist.waiting(self.state, self.content)):
            return []  # 引導走完了、入伍段也沒在進行、也不會再開始（beta 季、內容沒有入伍段、早就走完、略過過）：沒有什麼好略過的
        # 在序章裡略過：站到起點、拿出師的盤纏（設計 7.3）；序章外略過照舊
        purse = prologue_rules.finish(
            self.state, self.content, self.world, purse=prologue_rules.active(self.state, self.content),
        )
        self.state.player.tutorial_step = steps
        self.state.player.guide_done, self.state.player.guide_outro = [], False  # 略過後對話框不再出現（8.1.4）
        self.state.player.guide_skipped = True
        enlist.skip(self.state, self.content)  # 入伍段也略過（設計 7.3），之後投靠不開始
        self._write("新手引導", purse, tag="已略過")
        self._surface_hint()  # 略過讓框換成排在引導後面的提示：同一下上框（記說過、記進江湖紀錄），不等下一次同步
        return self._log(["（已略過新手引導。）"] + purse)

    def view_orders(self) -> list[str]:
        """軍令卡出現在畫面上（網頁在入伍段第一步、卡片真的進了畫面才送，F5）：看入伍段這一步有沒有完成；不寫紀錄、不換「剛剛」。"""
        self._guide(note_action(self.state, self.content, self.world, "view_orders"))
        return []

    def view_map(self) -> list[str]:
        self.state.player.flags.add("看過地圖")
        self._guide(note_action(self.state, self.content, self.world, "view_map"))  # 接在最新一則，「剛剛」不換
        return []

    PROLOGUE_TABS = ("practice", "craft")

    def view_tab(self, tab: str) -> list[str]:
        """打開修練或煉製頁（網頁在序章裡才送）：記一個旗標（看過:practice），看引導這一步有沒有完成；不寫紀錄、不換「剛剛」。"""
        if tab not in self.PROLOGUE_TABS:
            return []
        self.state.player.flags.add(f"看過:{tab}")
        self._guide(note_action(self.state, self.content, self.world, "view_tab"))
        return []

    def prologue_view(self) -> dict | None:
        """序章的畫面要亮什麼、發光什麼（prologue.view）；不在序章是 None。"""
        return prologue_rules.view(self.state, self.content)

    def prologue_recap(self) -> str:
        """設定頁的「重看序章」（設計 7.1）：序章的事件與師父的話照順序排成一頁，只能讀。沒有序章是空字串。
        只看內容、不看這個角色走到哪一步（{武學} 寫成「新武學」，每個人合出來的不一樣的話不寫死）。"""
        t = self.content.tutorial
        if t.location is None:
            return ""
        events = self.content.events
        parts: list[str] = []
        event_id = t.start_event
        seen: set[str] = set()
        while event_id is not None and event_id in events and event_id not in seen:  # 開場那一則一路接下去（遇險、拜師）
            seen.add(event_id)
            event = events[event_id]
            parts.append(f"**{event.title}**\n\n{event.text}")
            # 走下去的那個選項（有接下一則的、沒有就第一個）的結果文字：遇險的下場、師父收徒之後那一段（T7 審查 M5）
            choice = next((ch for ch in event.choices if ch.effect.next_event), event.choices[0])
            if choice.effect.text:
                parts.append(choice.effect.text)
            event_id = choice.effect.next_event
        for step in t.steps[: t.prologue_steps]:
            text = "\n\n".join(x for x in (step.scene, step.text) if x)
            if text:
                parts.append(text.replace("{武學}", "新武學"))
            sights = events.get(step.explore_event) if step.explore_event else None
            if sights is not None:  # 探索那一步之後：四景的引子與每一景悟到的那一句
                parts.append("\n\n".join([f"**{sights.title}**\n\n{sights.text}"] + [ch.effect.text for ch in sights.choices if ch.effect.text]))
            scene = self.content.insight_scenes.get(step.explore_scene) if step.explore_scene else None
            if scene is not None:  # 草廬四景是有所感的場景：場景的引子與卡上的每一個做法（悟到的句子是引擎照屬性寫的，不寫死）
                parts.append("\n\n".join([f"**{scene.title}**\n\n{scene.text}"] + [m.text for m in scene.methods]))
        if t.leave_text:
            parts.append(t.leave_text)
        return "\n\n---\n\n".join(parts)

    def quest_text(self) -> str:
        return quest_text(self.state, self.content, self.world)

    # ── 大地圖 ────────────────────────────────────────────

    def world_map_svg(self, layer: str = "situation", selected: str | None = None) -> str:
        odds = self.odds if layer == "enemies" else None
        return render_map(self.state, self.content, layer, selected, odds)

    def minimap_svg(self) -> str:
        return render_minimap(self.state, self.content)

    def map_legend(self, layer: str = "situation") -> dict:
        """大地圖的圖例（資料，見 mapview.legend_data）：不畫進 SVG，網頁自己疊在地圖框角落。"""
        return legend_data(self.state, self.content, layer)

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
        if not self.world.open_season(self.content, now):
            return self._log(["（現在不是籌備期，無法開季。）"])
        msgs = [f"══ {self.content.scenario.name}・開季 ══"]
        self._write("開季", msgs, tag="管理者")
        return self._log(msgs + self._settle_season_start())

    def _settle_season_start(self) -> list[str]:
        """開季那一刻（世界秒 0）結算第 1 週週一 00:00 的大事（FB-040，見 world.settle_season_start），開季的人那一次
        請求就跑；之後每曆時的交界才跑每曆時的事。放在 open_season／next_season 之後、不在任何 mutate 裡（mutate 不能巢狀）。
        開關關著或舊季什麼都不會發生。公告進自己的江湖紀錄走 _deliver_big_events，跟別人一樣。"""
        msgs: list[str] = []
        self.world.mutate_season(lambda season: msgs.extend(settle_season_start(season, self.content, self.rng)))
        self.state.world = self.world.get_season()
        self._deliver_big_events()
        return msgs

    def admin_end_season(self, now: float) -> list[str]:
        """管理者立刻收季：進行中 → 休季（之後再由 admin_next_season 開下一季）。照自然收季的做法算結局、
        寫江湖史、附武學榜（world.end_season），只是不必等季末或快轉十幾天——試玩伺服器要收掉這一季用的。
        不推進時間：季的時間停在收季那一刻。now 跟 admin_open_season／admin_next_season 同一種簽名，收季本身用不到。"""
        if not self.is_admin():
            return self._log(["（只有管理者能收季。）"])
        if self.world.season_phase() != "running":
            return self._log(["（賽季不在進行中，沒有可以收的。）"])
        if self.world.paused_at() is not None:
            return self._log([PAUSED_REFUSAL])
        msgs: list[str] = []
        self.world.mutate_season(
            lambda s: msgs.extend(end_season(_season_vehicle(self.content, s), self.content, self.world))
        )
        self.state.world = self.world.get_season()  # 讀回完整的一份（mutate_season 回傳的不含傳聞與江湖史）
        # 沒打完的決戰直接收掉、不套用結果（這一季勝負已經定了，跟自然收季一樣，見 _battle_status，FB-015），
        # 參戰者各補一則「不算勝負」的江湖紀錄（FB-035）。放在 mutate_season 外面：mutate 不能巢狀，
        # 內層寫的會被外層整份存檔蓋掉；放在讀回賽季之後：收場時間記的是收季那一刻的季時間
        battle = self.world.get_battle()
        if battle is not None and battle.phase != "ended":
            self._shelve_unfinished_battle()
        # 收季前結算的、從沒開成的決戰（world.settle_waiting_showdowns）：公告跟別的大事一樣走 _deliver_big_events，
        # 收季那一則不再重複一次
        self._deliver_big_events()
        self._write("收季", self._without_timetable(msgs), tag="管理者")  # 跟開季一樣，管理者自己的江湖紀錄留一則
        return self._log(msgs)

    def admin_next_season(self, now: float) -> list[str]:
        """管理者開下一季：只在休季時有效；管理者自己的角色跟著換季（其他玩家下次同步時換）。"""
        if not self.is_admin():
            return self._log(["（只有管理者能開啟下一季。）"])
        battle = self.world.get_battle()
        if self.world.season_phase() == "resting" and battle is not None and battle.phase != "ended":
            # 季自然結束之後沒有人同步過、沒人走到 _battle_status 收掉它：換季會直接清掉，先收起來，
            # 參戰者才補得到「不算勝負」那一則（FB-035）。收場時間記收掉的那一季的時間，所以先讀回賽季
            self.state.world = self.world.get_season()
            self._shelve_unfinished_battle()
        if not self.world.next_season(self.content, now):
            return self._log(["（這一季還沒結束，無法開啟下一季。）"])
        self._reconcile_season()
        return self._log([f"══ 第 {self.world.get_season_number()} 季開始 ══"] + self._settle_season_start())

    def admin_pause_clock(self, now: float) -> list[str]:
        """管理者暫停賽季時鐘（線上架構設計第四節、8.3：公告停機時賽季時鐘暫停，季末跟著往後延）：只在進行中有效。
        暫停中季的時間不走、決戰不推、玩家不能行動、假人不出手、不能快轉，別的管理者動作也先擋著；畫面照常可看。
        停機前按，開回來按「繼續」（主機端也可以用 scripts/season_clock.py）。"""
        if not self.is_admin():
            return self._log(["（只有管理者能暫停賽季。）"])  # 待 S1／joy 潤
        if self.world.season_phase() != "running":
            return self._log(["（賽季不在進行中，沒有時鐘可以停。）"])  # 待 S1／joy 潤
        if not self.world.pause_clock(now):
            return self._log(["（賽季時鐘已經停著了。）"])  # 待 S1／joy 潤
        self._write("暫停賽季", [PAUSE_LINE], tag="管理者")
        return self._log([PAUSE_LINE])

    def admin_resume_clock(self, now: float) -> list[str]:
        """管理者讓賽季時鐘繼續走：停的這一段不算進賽季、季末往後延，進行中的決戰剩下的時間不變；排好、還沒開的決戰照原本的
        現實時間開（企劃者 2026-10-06 定 B3），原本的時間落在暫停裡的這一刻就開集結（B11；另一場還在打就排隊）。
        繼續、補算、開集結三步都在 world.resume_season_clock（順序只寫在那一個地方，主機端腳本與模擬也走它）；
        這裡把回傳的訊息（繼續的那一行、補算的、集結號角）寫進管理者自己的江湖紀錄。"""
        if not self.is_admin():
            return self._log(["（只有管理者能讓賽季繼續。）"])  # 待 S1／joy 潤
        msgs = resume_season_clock(self.world, self.content, now, self.rng, RESUME_LINE)
        if msgs is None:
            return self._log(["（賽季時鐘沒有暫停。）"])  # 待 S1／joy 潤
        self.state.world = self.world.get_season()
        self._deliver_big_events()  # 補算結算的大事，管理者自己的江湖紀錄馬上補上（別人下次同步補）
        self._write("繼續賽季", self._without_timetable(msgs), tag="管理者")
        return self._log(msgs)

    def paused_minutes(self) -> int | None:
        """賽季時鐘停了幾分鐘（照 Game.now）；沒有暫停是 None。江湖頁與設定頁用（server.main_view 的 paused）。"""
        at = self.world.paused_at()
        return None if at is None else int(max(0.0, self.now - at) // 60)

    def _admin_refusal(self, action: str) -> list[str] | None:
        """管理者觸發的共同檢查：不是管理者、或賽季沒有在進行，回傳要顯示的拒絕訊息；可以做就回傳 None。"""
        if not self.is_admin():
            return [f"（只有管理者能{action}。）"]
        if self.world.season_phase() != "running":
            return ["（賽季沒有在進行，無法觸發。）"]
        if self.world.paused_at() is not None:  # 開戰、觸發、推動、排時間、跳到下一件、救場：都等「繼續」之後
            return [PAUSED_REFUSAL]
        return None

    def admin_battles(self) -> list[BattleDef]:
        """管理者「立刻開戰」的選單，照內容的順序（計畫 T8）：
        - 第一季不觸發的 beta 決戰不列；
        - 時刻表決戰只在第一季列（開關關著時 beta 那一季沒有時刻表），而且只列還沒開過、還沒收場的，分版本的只列這一季
          該開的那一版（宛城照第 3 週的結果）——開出來跟時間到了自動開的一樣（見 admin_start_battle）。"""
        w = self.state.world
        off = season_one_off(self.content, w, "battles")
        showdowns = [
            showdown_battle(self.state, self.content, e) for e in self.content.timetable
            if season_one(self.content, w) and e.kind == "showdown" and e.id not in w.timeline and e.id not in w.showdowns_opened
            and (e.version_from is None or e.version_from in w.timeline)  # 宛城：第 3 週結算前不知道是哪一版，不列（PM 2026-10-05）
        ]
        openable = {b.id for b in showdowns if b is not None}
        return [b for b in self.content.battles.values() if b.id not in off and (b.timetable_event is None or b.id in openable)]

    def admin_fires(self) -> list[Threshold | WorldEvent]:
        """管理者「觸發大事」的選單：大勢門檻與世界事件，第一季不觸發的 beta 門檻不列（計畫 T8）。"""
        off = season_one_off(self.content, self.state.world, "thresholds")
        return [x for x in [*self.content.scenario.thresholds, *self.content.scenario.world_events] if x.id not in off]

    def admin_start_battle(self, battle_id: str, now: float) -> list[str]:
        """管理者直接開一場全服戰鬥（試玩時人少、大勢推不到門檻也能開戰）。選單上沒有的（第一季不觸發的 beta 決戰）開不了。"""
        refusal = self._admin_refusal("開戰")
        if refusal:
            return self._log(refusal)
        definition = next((b for b in self.admin_battles() if b.id == battle_id), None)
        if definition is None:
            return self._log(["（沒有這場戰鬥。）"])
        current = self.world.get_battle()
        if current is not None and current.phase != "ended":
            return self._log(["（已經有一場戰鬥在進行。）"])
        if definition.timetable_event is not None:  # 時刻表決戰：跟時間到了一樣開（起點照戰況、記下開過了，之後不再開）
            msgs = open_showdown(self.world, self.content, definition.timetable_event, now)
            self.state.world = self.world.get_season()
        else:
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
        msgs = fire_by_id(self.state, self.content, fire_id, self.world, self._quick_client(), now=self.now)
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
        if not trend_shown(self.content, self.state.world, trend_id):
            return self._log(["（沒有這條大勢線。）"])
        if not pushable(self.content, self.state.world, trend_id):  # 開關開著時的黃巾聲勢由三條戰線合成，change_trend 推它會丟 ValueError
            return self._log([f"（{trend_name(self.content, trend_id)}由三條戰線合成，不能直接推；請推其中一條戰線。）"])
        msgs = change_trend(self.state, self.content, trend_id, delta)
        msgs += check_thresholds(self.state, self.content, self.world, self._quick_client(), now=self.now)
        self._write("推動大勢", msgs or ["大勢紋絲不動。"], tag="管理者")
        self._save_season()
        return self._log(msgs)

    # ── 管理者：時刻表與救場（計畫 T10）──────────────────────

    def _timetable_refusal(self, action: str) -> list[str] | None:
        """時刻表類的管理者動作：先照 _admin_refusal，再要這一季有時刻表（第一季；beta 那一季沒有）。"""
        refusal = self._admin_refusal(action)
        if refusal:
            return refusal
        if not season_one(self.content, self.state.world):
            return ["（這一季沒有時刻表。）"]
        return None

    def _timetable_event(self, event_id: str) -> TimetableEvent | None:
        return next((e for e in self.content.timetable if e.id == event_id), None)

    def admin_schedule(self, item: str, at_real: float, now: float) -> list[str]:
        """把三場決戰或季末排在現實時間 at_real：換成世界秒（world.time ＋ (at_real − now) × time_scale）寫進 schedule。
        已經結算或開過集結的不能再排；不能排在過去；三場決戰與季末要照時刻表的順序（嚴格在前一項之後、後一項之前）。"""
        refusal = self._timetable_refusal("排時間")
        if refusal:
            return self._log(refusal)
        s, c = self.state, self.content
        w = s.world
        items = timetable.schedulable(c)
        event = next((e for e in items if e.id == item), None)
        if event is None:
            return self._log(["（只有三場決戰與季末能排時間。）"])
        if event.id in w.timeline or event.id in w.showdowns_opened:
            return self._log([f"（{event.title}已經結算或開打了，不能再排。）"])
        at = w.time + (at_real - now) * c.config.time_scale
        if at <= w.time + calendar.EPS_SECONDS:
            return self._log(["（不能排在已經過去的時間。）"])
        wanted, avoided = at, None
        if event.kind == "showdown":
            at, avoided = self._showdown_mark(at)
        i = items.index(event)
        prev = items[i - 1] if i > 0 else None
        nxt = items[i + 1] if i + 1 < len(items) else None
        order = []
        if prev is not None and at <= timetable.when(s, c, prev):
            order.append(f"要排在{prev.title}之後")
        if nxt is not None and at >= timetable.when(s, c, nxt):
            order.append(f"要排在{nxt.title}之前")
        if order:
            return self._log(["（三場決戰與季末要照順序：" + "、".join(order) + "。）"])
        source = self._timetable_event(event.version_from) if event.version_from else None
        if source is not None and source.id not in w.timeline and wanted <= timetable.when(s, c, source):  # 照管理者要的時間判
            return self._log([f"（{event.title}要看{source.title}的結果決定版本：要排在它之後。）"])  # 宛城（PM 2026-10-05）
        w.schedule[timetable.schedule_key(event)] = at
        if event.id in w.showdowns_waiting:  # 時間到了在排隊（前一場還在打）：改到之後就拿出隊伍，到了新的時間才開（T10 審查 I2）
            w.showdowns_waiting.remove(event.id)
        self._save_season()
        moved = "，對齊整點" if abs(at - wanted) > calendar.EPS_SECONDS else ""
        moved += f"、避開同一刻的{avoided}" if avoided else ""
        msg = f"已把{event.title}排在{calendar.stamp_text(at, c, w)}（季曆{moved}）。"
        self._write("排時間", [msg], tag="管理者")
        return self._log([msg])

    def _showdown_mark(self, at: float) -> tuple[float, str | None]:
        """排定的決戰時間對齊到下一個曆時交界（季的事只在交界把時間到了的決戰記下來，T10 審查 I1）；那一刻剛好有還沒結算的
        一般大事時再往後挪一個曆時——不然同一刻那件大事先結算，排在它前面、還沒開成的決戰會照起點判掉（settle_waiting_showdowns）。"""
        s, c = self.state, self.content
        cal_hour = calendar.cal_hour_seconds(c, s.world)
        mark = math.ceil((at - calendar.EPS_SECONDS) / cal_hour) * cal_hour
        return timetable.clear_of_events(s, c, mark)

    def admin_jump_next(self, now: float) -> list[str]:
        """跳到下一件大事：推進到最早那一件還沒結算的大事的時間（決戰是排定的集結開始；開過集結的不算），取整到下一個
        曆時交界（季的事只在交界跑），照常結算、開集結（走 advance）。同一刻的幾件一起結算。決戰還在集結或開打時拒絕。"""
        refusal = self._timetable_refusal("跳到下一件大事")
        if refusal:
            return self._log(refusal)
        self.now = now
        battle = self.world.get_battle()
        if battle is not None and battle.phase != "ended":
            return self._log(["（決戰還沒收場，先等它打完或取消。）"])
        s, c = self.state, self.content
        w = s.world
        pending = [e for e in timetable._pending(s, c) if e.id not in w.showdowns_opened]  # noqa: SLF001  同一個套件的排序
        if not pending:
            return self._log(["（時刻表上沒有下一件大事了。）"])
        cal_hour = calendar.cal_hour_seconds(c, w)
        target = max(timetable.when(s, c, pending[0]), w.time)
        mark = math.ceil((target - calendar.EPS_SECONDS) / cal_hour) * cal_hour
        if mark <= w.time + calendar.EPS_SECONDS:
            mark += cal_hour
        return [f"跳到{pending[0].title}。"] + self.advance(mark - w.time)

    def admin_set_trend(self, trend_id: str, value: int) -> list[str]:
        """定戰況：把一條大勢線直接推到 value（夾在 0～100）；檢查同「推動大勢」（衍生線拒絕），推過門檻照常觸發。"""
        refusal = self._admin_refusal("定戰況")
        if refusal:
            return self._log(refusal)
        if not trend_shown(self.content, self.state.world, trend_id):
            return self._log(["（沒有這條大勢線。）"])
        if not pushable(self.content, self.state.world, trend_id):
            return self._log([f"（{trend_name(self.content, trend_id)}由三條戰線合成，不能直接推；請推其中一條戰線。）"])
        delta = max(0, min(100, value)) - trend_value(self.state, self.content, trend_id)
        msgs = change_trend(self.state, self.content, trend_id, delta) if delta else []
        msgs += check_thresholds(self.state, self.content, self.world, self._quick_client(), now=self.now)
        self._write("定戰況", msgs or ["大勢紋絲不動。"], tag="管理者")
        self._save_season()
        return self._log(msgs)

    def admin_resolve_event(self, event_id: str, key: str) -> list[str]:
        """定結果：管理者直接定一件大事的結果（不含版本的鍵，例如「成」「guan:險勝」），照時刻表結算（公告、江湖史、
        效果都照內容），人人的江湖紀錄照 FB-038 補上。季末用「立刻收季」；決戰正在打的先取消。"""
        refusal = self._timetable_refusal("定結果")
        if refusal:
            return self._log(refusal)
        s, c = self.state, self.content
        event = self._timetable_event(event_id)
        if event is None:
            return self._log(["（沒有這件大事。）"])
        if event.kind == "finale":
            return self._log(["（季末請用「立刻收季」。）"])
        if event.id in s.world.timeline:
            return self._log([f"（{event.title}已經結算了。）"])
        battle = self.world.get_battle()
        running = battle is not None and battle.phase != "ended" and battle.battle_id in c.battles
        if running and c.battles[battle.battle_id].timetable_event == event.id:
            return self._log([f"（{event.title}正在打，先取消決戰。）"])
        if event.version_from is not None and event.version_from not in s.world.timeline:
            source = self._timetable_event(event.version_from)
            return self._log([f"（{event.title}要等{source.title if source else event.version_from}結算了才知道是哪一版。）"])
        if key not in timetable.result_keys(s, c, event):
            return self._log([f"（{event.title}沒有「{key}」這個結果。）"])
        msgs = timetable.resolve(s, c, event, self.rng, key=key)
        self._save_season()
        self._deliver_big_events()
        return self._log(msgs)

    def admin_clear_lock(self, event_id: str) -> list[str]:
        """清鎖定：拿掉一件大事的伏筆鎖定（第一個做完的人）與之後才做完的名單，結算時照沒人鎖定擲骰。"""
        refusal = self._timetable_refusal("清鎖定")
        if refusal:
            return self._log(refusal)
        w = self.state.world
        event = self._timetable_event(event_id)
        if event is None:
            return self._log(["（沒有這件大事。）"])
        if event_id not in w.locks:
            return self._log([f"（{event.title}沒有人鎖定。）"])
        del w.locks[event_id]
        w.lock_losers.pop(event_id, None)
        self._save_season()
        msg = f"已清掉{event.title}的鎖定。"
        self._write("清鎖定", [msg], tag="管理者")
        return self._log([msg])

    def admin_cancel_battle(self) -> list[str]:
        """取消決戰：正在集結或開打的那一場收起來、不算結果（參戰者各補一則「不算勝負」，同收季，FB-035），發一則天下大事。
        時刻表決戰取消後不會自己再開（開過的記號留著）；要收尾用「定結果」。"""
        refusal = self._admin_refusal("取消決戰")
        if refusal:
            return self._log(refusal)
        battle = self.world.get_battle()
        if battle is None or battle.phase == "ended":
            return self._log(["（沒有進行中的決戰。）"])
        definition = self.content.battles.get(battle.battle_id)
        name = definition.name if definition else battle.battle_id
        line = f"{name}臨時取消，這一仗沒有打成。"
        self.state.world = self.world.get_season()  # 收場時間記此刻的季時間（同 admin_end_season）
        self._shelve_unfinished_battle(f"{name}臨時取消，這一仗沒有打成，不算勝負。")
        add_rumor(self.state, line, content=self.content, layer="world")
        self._save_season()
        self._write("取消決戰", [line], tag="管理者")
        return self._log([line])

    # ── 畫面文字 ──────────────────────────────────────────

    def location_text(self) -> str:
        loc = self.content.locations[self.state.player.location]
        return f"【{loc.name}】危險 {'★' * loc.danger}\n\n{loc.describe(self.state.world.flags)}"  # 宛城的描寫隨版本換

    def scene_text(self) -> str:
        """有全服戰鬥時大家都看得到戰場；只能觀戰的人照常遊玩，自己眼前的事（事件、對話、
        地點）接在戰場底下，不然遇到事件時只看得到選項、看不到事件本身。"""
        battle_status = self._battle_status(tick=False)
        if battle_status is None:
            return self._own_scene_text()
        battle_scene = self._battle_scene_text(*battle_status)
        if not self._watching_battle(*battle_status) and battle_status[0].phase != "muster":
            return battle_scene  # 開打後戰場取代整個畫面；集結時照常遊玩，自己眼前的事接在底下
        return f"{battle_scene}\n\n---\n\n{self._own_scene_text()}"

    def _own_scene_text(self) -> str:
        s, c = self.state, self.content
        if s.world.ended:
            if season_one(c, s.world):  # 第一季：結局寫在江湖頁最上面的結算卡（season_result），場景寫所在的地方（FB-046）
                return self.location_text()
            return f"## {s.world.ending_title}\n\n{s.world.ending_text}"
        if s.pending_event:
            event = c.events[s.pending_event]
            return f"**{event.title}**\n\n{fill_marks(event.text, s)}"
        sense_card = sensing.scene_text(s, c) if s.player.sensing is not None else ""
        if sense_card:
            return sense_card
        if s.player.pending_companion:
            character = c.characters[s.player.pending_companion]
            history = s.player.dialogue_history.get(s.player.pending_companion, [])
            last = next((m["content"] for m in reversed(history) if m.get("role") == "assistant"), "")
            return f"**{character.name}**\n\n{last}"
        if s.player.pending_faction:
            faction = self.content.scenario.faction(s.player.pending_faction)
            return f"**投靠{faction.name}**\n\n{self._faction_prompt(faction)}"
        if s.player.pending_defect:
            target = self.content.scenario.faction(s.player.pending_defect)
            return f"**叛投{target.name}**\n\n{defection.prompt(s, c, target, self.faction_counts_text())}"
        if s.player.picking_audience:
            return f"**求見**\n\n{self._audience_intro()}"
        asking = foreshadow.asking_text(s, c, self.world) if s.player.fs_asking is not None else None
        if asking is not None:
            return asking
        if s.player.journey is not None:
            # 往哪、幾時抵達只寫在狀態列（status_data 的 journey，每一頁都看得到），場景不再寫一次（FB-046）
            halted = "（已經喊停）" if s.player.journey.stop_at is not None else ""
            return (
                f"**在路上**{halted}\n\n"
                "路上可以折返，也可以打開輿圖改去別處，或去修練、煉製；邊走邊想、沿途打聽、留意地形、路邊採集，"
                "到下一站之前各能做一次。可以先下線，到了會自己抵達。"
            )
        return self.location_text()

    def status_data(self) -> dict:
        """狀態列的資料（數字與短字串），網頁前端照這份自己排版；status_text 是同一份資料的文字版。"""
        s, c = self.state, self.content
        p, w = s.player, s.world
        names = c.config.stat_names
        sect = c.sects[p.sect].name if p.sect else None
        faction = c.scenario.faction_name(p.faction)
        now, cap = team.member_neili(c, p.member, team.con_of(s, c, self.world, PLAYER))
        mates = []
        for cid in p.team:
            progress = self.world.get_companion(cid)
            mate_now, mate_cap = team.member_neili(c, progress, team.con_of(s, c, self.world, cid))
            mates.append({"name": c.characters[cid].name, "level": progress.level,
                          "hp": round(mate_now), "hp_max": round(mate_cap)})
        data = {
            "name": p.name,
            "affiliation": "・".join(name for name in (sect, faction, ranks.title(c, s)) if name) or "散人",
            "anonymous": p.anonymous,
            "hints_off": p.hints_off,  # 設定頁「不再提示」的勾（新手引導計畫三）
            "level": p.member.level,
            "location": c.locations[p.location].name,
            "season": p.season_number,  # 第幾季；週次每一季都從 1 起，網頁記「看過哪一季哪一週的大事」要帶它
            "day": int(w.time // DAY) + 1,
            "clock": f"{int(w.time % DAY // HOUR):02d}:{int(w.time % HOUR // 60):02d}",
            "season_days": season_length_days(w, c),  # 這一季蓋章的季長（舊季照它自己的章，不跟著設定變）
            "stamina": int(p.stamina),
            "stamina_max": c.config.stamina_max,
            # 回體丹（企劃者 2026-10-07）：有丹、而且不在草廬序章裡才給，網頁照它在體力條旁畫「服丹」鈕（體力滿了鈕是灰的）
            # 測試期間一鍵補滿（Config.beta_free_refill）打開時：沒有丹也給（鈕照樣畫），多一個鍵 refill＝鈕上的字，網頁見它就寫
            # 「補滿」不寫「丹 N」；關著時這個鍵不存在，整份跟 joy 的一個字不差
            "pills": None if (p.stamina_pills <= 0 and not c.config.beta_free_refill) or prologue_rules.active(s, c) else {
                "name": c.config.stamina_pill_name, "count": p.stamina_pills, "restore": c.config.stamina_pill_restore,
                "full": p.stamina >= c.config.stamina_max,
                **({"refill": c.config.beta_free_refill_label} if c.config.beta_free_refill else {}),
            },
            "hp": round(now),  # 跟角色卡（skillview.member_card 的 {:.0f}）同一種進位：兩邊寫出來的數字一樣
            "hp_max": round(cap),
            "injury": int(p.member.injury),
            "silver": p.stats.get("silver", 0),
            "xinde": p.stats.get("xinde", 0),
            "minor": [(names[k], p.stats.get(k, 0)) for k in ("fame", "good", "evil")],
            "attrs": [(names[k], p.stats[k], k) for k in team.COMBAT_STATS],  # 第三項是鍵：配點鈕送它（allocate_stat）
            "stat_points": p.stat_points,
            "stat_cap": c.config.stat_cap,
            # ＋鈕底下那一行：五項各管什麼、事件檢定也看它們（計畫二最終審查 M2）；網頁只在有點可配時畫
            "stat_uses": skillview.stat_uses(c),
            "stat_uses_note": skillview.STAT_CHECK_NOTE,
            "hint": skillview.practice_hint(s, c),  # 心得擱著沒用、又還有功夫沒練滿時才有
            "team": mates,
            "busy_hours": None if p.busy_until is None else round((p.busy_until - w.time) / HOUR / c.config.time_scale, 1),  # 現實小時
            "resting": None if p.resting_since is None else c.config.rest_regen_multiplier,  # 打坐時體力回復的倍數
            "journey": None if p.journey is None else self._journey_line(),
            **self._calendar_status(),  # 第一季：季曆與下一件大事的倒數；開關關著時沒有這兩欄
        }
        if season_one(c, w):  # 第一季濃縮版：江湖頁的三條戰況與三方態勢；開關關著時沒有這兩個鍵，畫面照舊
            # FB-065：圖卡畫亂局帶（兩端讀設定，跟 in_chaos 同一份、含兩端）、標出在亂局裡的戰線；態勢那一行的說明也由這裡給，
            # 前端不寫死 35／65，也不自己數條數。全服公開的戰況，誰看都一樣
            in_the_chaos = set(chaos_fronts(s, c))
            data["fronts"] = [
                {"id": tid, "name": trend_name(c, tid), "value": trend_value(s, c, tid), "chaos": tid in in_the_chaos}
                for tid in front_ids(c)
            ]
            data["chaos_band"] = {"low": c.config.chaos_low, "high": c.config.chaos_high}
            data["stances"] = stances(s, c)
            data["stance_notes"] = {"sum": stance_sum_note(c), "haoqiang": chaos_note(s, c, self._roster_players())}
            data["stance_rule"] = stance_rule_note(s, c)  # 態勢卡底下的收季規則（正式版辛）
        return data

    def _calendar_status(self) -> dict:
        """狀態列的季曆（第 N 週、週幾、幾點）與下一件大事：季曆時刻 at，加上倒數 in_seconds。倒數是現實秒：(大事時刻 − 世界秒) ÷ time_scale。"""
        w, c = self.state.world, self.content
        if not calendar.season_one_on(w, c):
            return {}
        at = calendar.point(w.time, c, w)
        # 休季時沒有下一件（計畫 T9）；籌備中時鐘沒走，也不倒數（FB-049）
        upcoming = None if w.ended or self._preparing() else timetable.next_event(self.state, c)
        return {
            "calendar": {
                "week": at.week, "weekday": at.weekday, "clock": f"{at.hour:02d}:{at.minute:02d}",
                "weeks": c.config.season_weeks, "text": calendar.point_text(at),  # 畫面第二行直接用這一句，不自己拼
            },
            "next_event": None if upcoming is None else {
                "title": upcoming.title,
                "at": self.stamp(timetable.when(self.state, c, upcoming)),  # 季曆時刻「第 9 週・週四 20:44」，畫面寫在倒數前面（FB-062）
                "in_seconds": round((timetable.when(self.state, c, upcoming) - w.time) / c.config.time_scale),
            },
        }

    def bulletin(self) -> list[str]:
        """江湖頁那排小標「大事」點開的本週大事（Markdown）：這一週已經發生的大事，新的在前、最多 BULLETIN_MAX 則。
        江湖紀錄裡的「江湖大事」只寫進剛好在場同步到的那個人，這張卡讓每個人都看得到。開關關著時是空的；
        休季時也是空的：結算卡已經列著這一季的每一件大事與結局（FB-046）。"""
        return [f"**{title}**\n\n{text}" for title, text in self._bulletin_events()]

    def _bulletin_events(self) -> list[tuple[str, str]]:
        """本週大事面板上的（標題, 公告全文），新的在前、最多 BULLETIN_MAX 則。"""
        w, c = self.state.world, self.content
        if not calendar.season_one_on(w, c) or w.ended:
            return []
        start = calendar.week_start(calendar.point(w.time, c, w).week, c, w) - calendar.EPS_SECONDS
        titles = {e.id: e.title for e in c.timetable}
        done = [(i, eid, r) for i, (eid, r) in enumerate(w.timeline.items()) if r.text and r.time >= start]
        done.sort(key=lambda item: (item[2].time, item[0]), reverse=True)
        return [(titles.get(eid, eid), r.text) for _, eid, r in done[:BULLETIN_MAX]]

    def _news_on_cards(self) -> set[str]:
        """江湖頁的卡片上已經寫著全文的時刻表公告：平常是本週大事（那排小標「大事」點開的面板），休季時是結算卡（結局與這一季的每一件大事）。"""
        w = self.state.world
        if w.ended and season_one(self.content, w):
            shown = {r.text for r in w.timeline.values()} | {w.ending_text}
        else:
            shown = {text for _, text in self._bulletin_events()}
        shown.discard("")
        return shown

    def convoy_line(self) -> str | None:
        """押著的糧車要送去哪（江湖頁軍令卡上的一行；T6 審查 I3）：那一道軍令已經達成或換週清掉了也照樣寫，
        送到了照樣記捐獻與貢獻。沒有押車、或這一季已經收了（休季，FB-045）時是 None。"""
        convoy = self.state.player.convoy
        if convoy is None or self.state.world.ended:
            return None
        return f"你押著一車糧（{convoy.grain} 份），要送到{self.content.locations[convoy.to_loc].name}。"

    def orders_view(self) -> list[dict]:
        """江湖頁的「本週軍令」卡（計畫 T6）：自己陣營這週的軍令，只給自己陣營看；散人、開關關著是空的。
        截止是下週一 00:00（最後一週寫成季末那一刻，calendar.point 會夾住）。休季時也是空的（FB-045）：
        收季那一週的軍令截止已經過了，休季什麼都不能做，結算畫面底下不該還有一張叫人去做事的卡。
        沒達成的軍令多一個 how：怎麼出力（atlas.order_how，FB-093；打擊另寫他在哪，FB-072）；打完的沒有這個鍵。"""
        s, c = self.state, self.content
        if s.world.ended:
            return []
        name = s.player.name
        views = []
        for o in orders.current(s, c, s.player.faction):
            total = sum(o.progress.values())
            view = {
                "id": o.id, "title": orders.title(c, o), "text": o.text, "mine": o.progress.get(name, 0),
                "progress": min(total, o.quota), "quota": o.quota, "done": o.done,
                "deadline": self.stamp(calendar.week_start(o.week + 1, c, s.world)),
            }
            if not o.done and (o.template != "strike" or o.figure is not None):
                view["how"] = atlas.order_how(s, c, o)  # 怎麼出力（FB-093；打擊另寫他在哪，FB-072）；打完的沒有這個鍵
            views.append(view)
        return views

    def season_result(self) -> dict | None:
        """休季時江湖頁最上面的結算卡（計畫 T9）：結局與季末公告、最終三方態勢與三條戰況、時刻表每一件的結果（誰改寫的）、
        各陣營出力前五。只有第一季（開關開著＋這一季的章）收季之後才有；資料在收季那一刻存好（world.end_season），這裡只讀。
        時刻表那一列：結算過的是公告全文；跳過的寫「這一季沒有發生」；季提前收束、還沒輪到的寫「季已落幕，沒有發生」。
        改寫的人寫公告上的名字（timetable.shown：一律名號；只有這一版之前匿名鎖定的，照記下的「某位少俠」寫）。"""
        s, c = self.state, self.content
        w = s.world
        if not w.ended or not season_one(c, w):
            return None
        values = dict(w.final_trends)
        huangjin, geju = values.get(HUANGJIN, 0), values.get(GEJU, 0)
        standing = {"guan": 100 - huangjin, "huang": huangjin, "haoqiang": geju}
        names = {f.id: f.name for f in c.scenario.factions}
        timeline = []
        for event in c.timetable:
            result = w.timeline.get(event.id)
            if result is None:
                text = "（季已落幕，沒有發生。）"
            elif not result.text:
                text = "（這一季沒有發生。）"
            else:
                text = result.text
            lock = w.locks.get(event.id) if result is not None and result.locked_by else None
            timeline.append({
                "week": event.week, "title": event.title, "text": text,
                "locked_by": timetable.shown(lock) if lock is not None else None,
            })
        return {
            "title": w.ending_title, "text": w.ending_text,
            "stances": [{"side": side, "name": names.get(side, side), "value": value} for side, value in standing.items()],
            "fronts": [{"id": f, "name": trend_name(c, f), "value": values.get(f, 0)} for f in front_ids(c)],
            "timeline": timeline,
            "rankings": [
                {"faction": f.id, "name": f.name, "rows": [list(row) for row in w.final_rankings.get(f.id, [])]}
                for f in c.scenario.factions
            ],
        }

    def stamp(self, time: float, clock: bool = True) -> str:
        """玩家看得到的遊戲時間（江湖紀錄、江湖史、傳聞、戰報、路上）：第一季寫成季曆，其他時候照舊（calendar.stamp_text）。"""
        return calendar.stamp_text(time, self.content, self.state.world, clock=clock)

    @staticmethod
    def _when_text(d: dict) -> str:
        cal = d.get("calendar")
        if cal is None:
            return f"第 {d['day']} 天 {d['clock']}（本季共 {d['season_days']:g} 天）"
        return cal["text"]

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
        attrs = "　".join(f"{k} {v}" for k, v, _ in d["attrs"])
        lines = [
            f"### {d['name']}　·　{d['affiliation']}" + ("（匿名行走）" if d["anonymous"] else "")
            + f"　第{d['level']}級",
            f"📍 {d['location']}　⏳ {self._when_text(d)}",
            vitals,
            f"{minor}　｜　{attrs}",
        ]
        if d["hint"] is not None:
            lines.append(d["hint"])
        for mate in d["team"]:  # 只有真的帶了同伴才列隊伍，一個人時不佔版面
            lines.append(f"🧍 {mate['name']}　第{mate['level']}級　氣血 {mate['hp']}/{mate['hp_max']}")
        if d["busy_hours"] is not None:
            lines.append(f"🧘 閉關中，現實約 {d['busy_hours']:.1f} 小時後出關")
        if d["resting"] is not None:
            lines.append(f"🧘 打坐中：體力回復是平常的 {d['resting']:g} 倍，隨時可以起身")
        if d["journey"] is not None:
            lines.append(f"🧭 在路上：{d['journey']}")
        return "\n\n".join(lines)

    def trends_text(self) -> str:
        w = self.state.world
        parts = []
        for trend in self.content.scenario.trends:
            if not trend_shown(self.content, w, trend.id) or not is_revealed(w, self.content, trend.id):
                continue
            value = trend_value(self.state, self.content, trend.id)
            bar = "█" * (value // 5) + "░" * (20 - value // 5)
            note = (
                f"\n\n現況：{chaos_note(self.state, self.content, self._roster_players())}。"
                if trend.id == GEJU and season_one(self.content, w) else ""
            )
            parts.append(f"**{trend.name}** {value}/100\n\n`{bar}`\n\n{trend.desc}{note}")  # 割據：說明後面接現在漲或落（FB-065，同江湖頁態勢那一行）
        if w.ended:
            parts.append(f"## 結局：{w.ending_title}\n\n{w.ending_text}")
        return "\n\n".join(parts) or "（江湖暫時風平浪靜。）"

    def rumors_text(self, limit: int = 30) -> str:
        """見聞頁的傳聞（一條清單，main_view 的 rumors）：只列聽得到的（rules.audible——陣營軍情只給那個陣營、個人線索只給
        那個人；第一季的地方傳聞只給此刻人在那個大區的人、只留傳聞板上最近幾天的）。開關關著時跟以前一樣。"""
        ears = ears_of(self.state, self.content)
        heard = [r for r in self.state.world.rumors if audible(r, ears)]
        return _timeline(heard[-limit:][::-1], self._day_stamp) or "（尚無傳聞。）"

    def rumor_layers(self) -> list[dict[str, str]] | None:
        """見聞頁的傳聞分四層（天下大事、陣營軍情、所在大區、個人線索；rumor_view.layers），每層 {id, title, body}，body 是
        Markdown。只在第一季的規則開著時分：開關關著（或這一季開季時沒開）是 None，頁面照舊畫 rumors_text 那一條清單。"""
        if not season_one(self.content, self.state.world):
            return None
        return rumor_view.layers(self.state, self.content, self.world, self._day_stamp)

    def chronicle_text(self) -> str:
        """江湖史：這一季在最前面，往前每一季各一段（線上架構設計 3.2：江湖史跨季保留），最後是玉璽碎片。"""
        number = self.world.get_season_number()
        current = _timeline(self.state.world.chronicle, self._day_stamp) or "（江湖史尚無記載。）"
        past = self.world.chronicle_before(number)
        parts = [f"### 第 {number} 季（本季）\n\n{current}" if past else current]
        parts += [f"### 第 {n} 季\n\n{_timeline(entries, calendar.day_text)}" for n, entries in past]  # 上一季照舊寫「第N天」
        parts.append(self.world.jade_seal_summary())
        return "\n\n---\n\n".join(parts)

    # ── 江湖紀錄 ──────────────────────────────────────────

    def _day_stamp(self, time: float) -> str:
        """江湖史與傳聞的時間：沒有季曆時只寫天數（「第2天」），第一季寫季曆。"""
        return self.stamp(time, clock=False)

    def _chip(self, change: str, seed: str) -> tuple[str, int] | None:
        """江湖紀錄畫數值標籤時，戰況變化的換法（FB-064，journal.ChipFn）：紀錄裡存的是機器可讀的寫法，這裡照內容換成一句話、
        照「現在看的人」的陣營算對他是好事還是壞事（顏色在畫的那一刻才定，換了陣營再畫就跟著變）。"""
        return front_chip(self.content, self.state.player.faction, change, seed)

    def latest_entry_html(self) -> str:
        entries = self.state.journal
        return journal.card_html(entries[0], self.stamp, self._chip) if entries else ""

    def journal_top_html(self) -> str:
        """江湖紀錄頁的第一則（伺服器的 latest，底下接 journal_html(1, …)）：最新一則就是「剛剛」那張戰鬥卡片那一場時，
        放卡片沒寫到的補充（照舊）；其他時候畫最新一則——包括「剛剛」越過的那則配點（_now_start），它在江湖紀錄裡照樣列在最前面。"""
        if self.shows_battle_card() and self._now_start() == 0:
            return self.battle_extra_html()
        return self.latest_entry_html()

    def now_entry_html(self) -> str:
        """江湖頁「剛剛」那一則（FB-046）：最新一則；最新的幾則若只是時刻表大事的公告（_deliver_big_events 補的），
        而且每一件的全文江湖頁的卡片上已經有了（_news_on_cards），就往前找第一則不是的——同一段公告不在「剛剛」
        再寫一次，剛做完的事也不會因為一件大事發生就被擠掉。江湖紀錄頁照舊從最新一則列起（latest_entry_html）。
        一次補好幾件時每一行是「季曆時間　公告全文」。
        配點那一則也越過（計畫二最終審查 M1，見 _now_start）；越過之後什麼都不剩（只有配點）時才放它，不讓「剛剛」空著。
        籌備中不放（FB-049）：那時最新一則是開場那一則，寫著「賽季開始」、叫人先去探索，選單卻只有「等待管理者開季」。
        草廬裡（序章，T7 審查 I2、I3）只放自己做的事的結果：江湖大事、你不在的時候、賽季開場（journal.is_world_entry）都不放，
        草廬的事件在眼前時整張卡不放（它只是重複事件的標題，還把選項擠到分頁列底下）。紀錄裡照舊都有。"""
        if self._preparing():
            return ""
        hut = prologue_rules.active(self.state, self.content)
        if hut and (self.state.pending_event is not None or self.state.player.sensing is not None):
            return ""  # 草廬的事件或草廬四景的有所感（做法、畫下來）在眼前：整張卡不放
        shown = self._news_on_cards()

        def repeated(entry: JournalEntry) -> bool:
            story = entry.lines or [entry.tag]
            return entry.title == journal.WORLD_NEWS and all(
                line in shown or line.partition("　")[2] in shown for line in story
            )

        fresh = [e for e in self.state.journal if not repeated(e) and not (hut and journal.is_world_entry(e))]
        entry = next((e for e in fresh if e.title != journal.ALLOCATE), fresh[0] if fresh else None)
        return journal.card_html(entry, self.stamp, self._chip) if entry is not None else ""

    def journal_html(self, start: int = 1, limit: int = 5, heading: str = "", empty: str = "") -> str:
        return journal.rows_html(self.state.journal[start:start + limit], heading, empty, self.stamp, self._chip)

    def _now_start(self) -> int:
        """「剛剛」從江湖紀錄的第幾則看起：最新的幾則若是配點就越過（計畫二最終審查 M1）。配點是點名號展開、在狀態列上按的，
        跟 journal.add_guide 一樣不換「剛剛」——升級那一仗打完照著「你有 N 點屬性可以分配」去配點，那一場的戰鬥卡片
        不會因此不見。全都是配點時從最新一則看起。江湖紀錄頁照舊從最新一則列起（journal_top_html／journal_html）。"""
        return next((i for i, e in enumerate(self.state.journal) if e.title != journal.ALLOCATE), 0)

    def shows_battle_card(self) -> bool:
        s, i = self.state, self._now_start()
        return self.battle_card_id() is not None and len(s.journal) > i and s.journal[i].battle_id == s.battle_card

    def battle_extra_html(self, for_card: bool = False) -> str:
        """「剛剛」那張戰鬥卡片底下的補充：那一場那一則裡卡片沒寫到的（越過最新的配點，跟 shows_battle_card 看同一則）。
        for_card（江湖頁的「剛剛」用）：打完接著有事件待處理時，「你聽到一件事」那一行讓出來——事件的最後一個選項要留在第一屏
        （FB-076）；江湖紀錄頁最上面（journal_top_html）不給，照舊列出，那一行也還在紀錄那一則裡。"""
        if not self.shows_battle_card():
            return ""
        record = battlelog.find(self.state, self.state.battle_card)
        entry = self.state.journal[self._now_start()]
        lines, changes = journal.card_leftovers(entry, battlelog.told_lines(record), battlelog.gains_list(record))
        if for_card and self.state.pending_event is not None:
            lines = journal.without_fragments(lines)
        return journal.extra_html(lines, changes, self._chip, str(entry.time))

    def _log(self, msgs: list[str]) -> list[str]:
        """回給呼叫端、也存進 GameState.log 的訊息。戰況變化（機器可讀的寫法）在這裡換成一句話——這些話玩家（管理者工具列的
        提示）看得到，數字不外露（FB-064）；江湖紀錄那邊在畫的時候換（見 _chip），兩邊用同一個 seed（現在的時間），是同一句。"""
        msgs = humanize(self.content, msgs, str(self.state.world.time))
        if not msgs:
            return msgs
        log = self.state.log
        log.extend(msgs)
        log.append(LOG_BREAK)
        overflow = len(log) - self.content.config.max_log
        if overflow > 0:
            del log[:overflow]
        return msgs


def _timeline(entries: list[Rumor], when: Callable[[float], str]) -> str:
    return "\n\n".join(f"{when(e.time)}　{e.text}" for e in entries)

