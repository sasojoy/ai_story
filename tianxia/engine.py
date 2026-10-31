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
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from pydantic import BaseModel

from . import arts as arts_mod
from . import ascend  # 破境卡（招式與絕學稿案第三節）
from . import narration  # 事件旁白每週改寫（減法季批 10）
from . import chapters  # 章回主線（企劃者 2026-10-29）
from . import (
    allied, annals, arena, arena_crowd, armor, atlas, battle_instance, biography, battlelog, bounties, calendar, checkin, chuangong, clinic, companion_agent, conquest, conquest_day, create, cultivation, defection, divine, economy, encounter, enlist, equipment, event_llm, explore_modes, escorts,
    deeds, fight_llm, figure_aid, figure_life, figures, foreshadow, four_tiers, gather_llm, generals, forge_secrets, front_lines, fusion, gender, howto, insight_fx, insights, invites, journal, letters, library, mapdata, martial_arts, plans,
    materials, mounts, naming, newbie, server_bots, opportunities, orders, parley, precise, push, rank_actions, ranger, ranks, renown, rise, roster, rounds, seal, seal_acts, seal_duel, seats, secret_recipes, sensing,
    shopview, siege, signature, signature_arms, silver, skillview, smithing,
    social, sortie, styles, tactics, team, terrain, territory, timetable, traits, treasures, weapons, week_unlock, works, xingshi, zh, yuedan,
)
from . import sortie_duel  # 出陣約戰（減法季批 3b）
from . import tavern_ask  # 問酒家照問題找事實（企劃者 2026-10-27）
from . import storyline  # 一條線：特殊事件與特殊頓悟的底座（企劃者 2026-10-26）
from . import epiphany  # 特殊頓悟（登記一條線的鉤子；企劃者 2026-10-26）
from . import tiers  # 事件分級：場景卡上那一行「州郡大事」「天下大事」
from . import outing as outing_rules  # 走一趟（企劃者 2026-10-29～30）：探索一次走一、三、五段
from . import explore_one, growth  # 減法季批 2：探索一顆、三道閘、屬性五段的純規則（開關走 rules.jianfa）
from . import zhuan_end  # 減法季批 7b：列傳為終點（票、深交上限、人物評曰）
from . import ambush as ambush_rules  # 設伏劫道（後期體力玩法第一批）；叫 ambush_rules：這個檔裡有區域變數叫 ambush
from . import duel as duel_rules  # 單人頭目戰（Joy 2026-10-10）
from . import opening as opening_rules  # 開局第一分鐘（減法季批 7；叫 opening_rules：避免跟戰法的 opening 混）
from . import discuss as _discuss_card  # noqa: F401  論武登記進玩家卡的動作表（social.ACTIONS）
from . import raid as _raid_card  # noqa: F401  截殺登記進玩家卡的動作表（social.ACTIONS）
from . import wanted as _wanted_card  # noqa: F401  通緝登記進玩家卡的動作表（social.ACTIONS）
from . import spar as _spar_card  # noqa: F401  切磋登記進玩家卡的動作表（social.ACTIONS）
from . import mingtie as mingtie_rules  # 名帖（Joy 2026-10-19）
from . import mingtie_card as _mingtie_card  # noqa: F401  遞名帖登記進玩家卡的動作表（social.ACTIONS）
from . import speech
from . import events as event_rules  # note_round 走模組屬性（測試要能換掉它，確認只有 _present 會叫）
from . import hints as hint_rules  # 碰到才說（新手引導計畫三）；叫 hint_rules：這個檔裡有幾處區域變數也叫 hints
from . import tavern as tavern_rules  # 酒肆（企劃者 2026-10-18）；叫 tavern_rules：跟其他 *_rules 一樣避開區域變數
from . import prologue as prologue_rules  # Game.new 有個參數也叫 prologue，所以模組在這裡一律叫 prologue_rules
from . import rumor_view  # 傳聞分層的畫面：見聞頁的四層、你不在的時候（計畫 2026-10-06 傳聞分層一）
# 減法季批 4：隨口應對分岔、痕跡看得見、貢獻（三陣營四勝利的 wins.credit）；別名避開這個檔裡叫 marks、outcomes 的區域變數
from . import marks as marks_rules
from . import outcomes as outcome_rules
from . import stances as stance_rules  # 人物心意（減法季批 6）；叫 stance_rules：rules.stances 是陣營的態勢
from . import errands as errand_rules  # 託付與來信（減法季批 6）
from . import wins as wins_rules
from .models import FreeTextChoice, Outcome, StoryDef, StoryStage
from .rules import jianfa
from . import step as step_rules  # 本週卡「你這一步」（減法季批 3c）；叫 step_rules：這個檔裡有區域變數叫 step
from . import wins  # 三陣營四勝利（減法季批 3c）：豪強兩本帳、傾向、季末四階
from .accounts import AccountStore
from .characters import CharacterStore, name_key
from .events import (
    choice_label, event_candidates, free_text_note, has_events_here, pick_event, stamina_note, visible_choices,
)
from . import training
from .guide import HutReward, base_step_count, note_action, pending_line, quest_text, step_text, tutorial_active, tutorial_intro
from .guide import speaker_of as guide_speaker_of
from .guide import speakers as guide_speakers
from .guide import steps as tutorial_steps
from .journal import LOG_BREAK, Draft
from . import mapview  # 輿圖名字旁（map_mostly）問 mapview.open_places：哪些地點畫得出來，跟底圖、疊層同一個判斷
from .mapview import legend_data, render_map, render_minimap
from .martial_arts import QUALITIES, is_renamed
from .models import (
    EXPLORE_BRANCHES, FREE_TEXT_MAX, MOVES, BattleDef, Check, Choice, Content, Effect, Event, ExploreBranch, FactionDef, GatherBranch, Location,
    DuelBoss, PromotionDef, RoadKind, Squad, Threshold, TimetableEvent, TravelMode, TutorialStep, WorldEvent,
)
from .ollama_client import ModelBudget, OllamaClient, quick_client
from .rules import (
    GEJU, HUANGJIN, add_chronicle, add_marks, add_rumor, add_world_flags, display_name, apply_effect, audible, audience_bar, audience_hint, can_meet, change_trend,
    check_gap, check_result_line,
    day_turn, ears_of, evil_success, failed, fill_marks, free_text_rate, game_day, geju_resisted, here_regions,
    can_draw_side_change, chaos_fronts, chaos_note, front_chip, front_ids, front_of, front_text, humanize, in_chaos,
    is_revealed, learn_skill, pushable, rate_words, recompute_trends, resolve_goals, resolve_trend, resolve_trends, roll_check,
    season_one, season_one_off, stance_rule_note, stance_sum_note, stances, stat_rate, trend_name, trend_shown, trend_value,
    world_day, world_trend_value,
)
from .rules import jianfa  # 減法季（Config.jianfa＋開季的章；子開關照名字問）
from .sqlite_world import open_world
from .wallet import Wallet
from .core import features as features_core  # 核心照 FEATURES 問每一包（開發規範手冊 3.3）
from .core.option import Option  # 選單上的一顆（搬進核心：功能包要做選項）
from .core.services import NO_SUCH_PLAYER, PAUSED_TEXT, WalletService, drill_share, wallet_on  # 共用的字與小函式、錢包服務（3.10）
from .features.mall import actions as mall_actions  # 過渡：Game.mall_* 留一行委派（開發規範手冊 3.10）
from .features.feast import actions as feast_actions  # 過渡：Game.feast_*（server 的三段式）與場景卡留一行委派
from .features.sortie import actions as sortie_actions  # 過渡：Game 上出陣的 13 個一行委派（主動搬六包第 1 批）
from .features.sortie.rules import CLASH_OPEN, CLASH_THEIRS_WON, CLASH_WON  # noqa: F401  過渡：tests/ranger/test_raid.py 從 engine 拿
from .state import (
    ONBOARDING_VERSION, PLAYER, ArenaEntry, ArenaFight, ArenaReport, ArenaResult, ArenaSide, BattleRecord, Convoy, CrowdNote, DuelState, Equipment, Feast, Fighter, FrontReport, GameState, HintNote, JournalEntry, Journey, Letter, Mingtie, ParleyBacking, ParleyDebt, ParleyTerms, Rumor, Tagalong, TavernHit, TavernWatch, TimelineResult,
    Outing, OutingBeat, StoryCard, StoryProgress, TierResult, Whisper, WorldState, XingshiEssay, XingshiMark, XingshiTicket,
    new_game_state,
)
from .world import (
    _season_vehicle, advance_world_state, check_thresholds, end_season, evaluate_ending, fire_by_id, open_showdown, open_waiting_showdown,
    resume_season_clock, settle_season_start, showdown_battle, showdown_key, start_pending_battle,
)
from .world_state import SealDuel, SealSide, SortieDuel, SortieSide, WorldStateStore, season_length_days

HOUR = 3600
DAY = 86400
BULLETIN_MAX = 3  # 江湖頁那排小標「大事」點開的面板最多放這一週的幾則大事（計畫 T2；以前是公告卡）
AUDIENCE_HALL_FIGURES = 2  # 一個地點有幾位以上的大勢人物，交友就不直接找人、改按「求見」指名（企劃者 2026-10-03 決定）
OFF_FRONT_NOTE = "沒在戰線上領兵，不受挑戰"  # 戰線空著的人物（董卓、趙弘、重挫退下的人）：挑戰按鈕寫這一句（PM 2026-10-05 定）
SOCIAL_TALK = "跟{name}說話"  # 待 joy 潤：一類一顆的交友只有一位說得上話的人物時，鈕上那一格（正式季整合 2.8）
SOCIAL_NO_ONE = "這裡沒有能說上話的人"  # 待 joy 潤：一類一顆的交友沒有人物、也沒有結識事件時（鈕上不帶句號）
SOCIAL_LIST_TITLE = "交友"  # 待 joy 潤：一類一顆的交友打開的人物名單（FB-421）
SOCIAL_LIST_INTRO = "{here}有好幾位人物，挑一位說話。每位人物各算各的，最多談 {per_day} 輪，{again}；名望不夠的見不到。"  # 待 joy 潤（FB-421）
SECT_LABEL = "拜入{sect}"  # 待 joy 潤：拜入門派從交友搬到「此地還能做」的一顆（正式季整合 2.7）
AUDIENCE_MEET = "先設法結識"  # 待 joy 潤：一類一顆的求見名單上，名望不夠、但這裡有他的結識事件的那一位
SUMMONS_LABEL = "應召晉升（召見在此・不花體力）"  # 待 joy 潤：一類一顆的應召（設計 9.1 第 1 組乙，橫幅上的字）
SHOWDOWN_TIER4 = "論功行賞，另得四階料【{name}】一個。"  # 待 joy 潤：時刻表決戰得勝那一方出手夠的人（正式季整合 4.5）
SNUB_NOTE = "剛吃了敗仗，閉門不見"  # 挑戰本人打贏之後，他對打贏的人關上門（軍令文件 4.5）：求見、交友、挑戰的按鈕寫這一句
GENDER_SET = "往後江湖上以{word}相稱。"  # 設定頁選了性別（只能選一次）
GENDER_LOCKED = "性別已經定了，改不了。"
MELT_MANY_PROLOGUE = "這裡照師父說的，一門一門熔。"  # 序章裡不給批量熔煉（序章的熔煉是教學的一步）
# 路上小事（路上設計第四節）：road:<id> → (名稱, 這一段做過之後寫的「這段路已經……」)；按鈕上的補充見 _road_task_options
ROAD_TASKS: dict[str, tuple[str, str]] = {
    "think": ("邊走邊想", "想過了"),
    "ask": ("沿途打聽", "打聽過了"),
    "gather": ("路邊採集", "找過了"),
}
ROAD_REWARD_TASKS = ("think", "gather")  # 有經濟收穫、受每天上限管的路上小事（Config.road_reward_daily_cap）
# 玩家之間的邀請（FB-117；待 joy 潤）：答應了卻沒成、邀請作廢時，發邀請的那個人下次同步看到的一句（以前邀請悄悄不見）
INVITE_LAPSED = "{who}想答應你的{what}，沒能成局，這份邀請作廢了。"
INVITE_LAPSED_AWAY = "那時你已經不在場。"  # 答應的那一刻他不在這裡了（下線、走了）
DISCUSS_SAME = "兩個人出的是同一樣，論不出新東西。"
# 答應論武時對方那邊合不成：照他那一句的兩三個字（fusion.Refusal.short）換成從你這邊看的說法——他那一句原話是寫給他看的，
# 「你已經有了」的「你」是他（FB-243；待 joy 潤）。沒列到的只寫「某某那邊合不成。」
THEIR_SIDE = {
    "已經有了": "合出來的那一樣{him}已經有了",
    "持有滿了": "{him}的武學與意境已經滿了",
    "心得不足": "{him}的心得不夠",
    "體力不足": "{him}的體力不夠",
    "不能當料": "那一門的路數是寫死的，不能拿來合成",
}


def _refusal(text: str, short: str) -> str:
    """一句拒絕的話，帶兩三個字的 short（fusion.Refusal：論武答應的下拉清單上，合不成的那一項後面寫它，FB-117）。"""
    out = fusion.Refusal(text)
    out.short = short
    return out


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


@dataclass(frozen=True)
class OutingPlan:
    """減法季探索一顆（整合設計 4.1）：這一處此刻出門一趟會怎麼抽（Game._outing_plan；鈕上的小字、行動列底下那一行、真的出門、假人打分數
    都讀這一份，說的跟擲的不會走樣）。只讀，不擲骰。"""

    kind: str  # 這一處算哪一種地點（explore_one.kind_of：town、temple、ford、wild、hill、camp）
    weights: dict[str, int]  # 這一趟四類事的比重（explore_one.weights；這裡此刻抽不到事件、悟不出的那一類已經是 0；接了討伐懸賞只有遭遇）
    how: str | None  # 遭遇打誰：bounty 討伐懸賞那一路（對它必敗時不算，2e）、spar 自家營寨跟同袍比劃、foe 這裡最弱的對手、town 城裡的地痞；都沒有是 None
    foe: Squad | None  # 那一路
    boss: DuelBoss | None  # 遭遇有機會撞上的頭目（接了這裡的討伐懸賞不擲）
    hint: str  # 鈕上括號裡最後那一段小字，也是四格探索那一格的小字（/api/main 的 mostly；explore_one.hint_of：地點種類的字加上面 weights 最重的一類；有賞、同袍比劃）；最後兩個字是輿圖名字旁（map_mostly）

    @property
    def foe_note(self) -> str | None:
        """行動列底下那一行補的那一句（howto.OUTING_FOE 的鍵）；一般的對手不補。"""
        return self.how if self.how in ("town", "spar", "bounty") else None


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
EVIL_ANNAL = "，行了一件惡事，成了。"  # 行狀：隨口應對判成惡行而且成了（FB-223），接在「遇上【某事】，隨口應對」後面。待 joy 潤
# 跟人物對話時的「自己說」（企劃者 2026-10-08）：按下去只是叫出輸入框，真正送出帶著那句話走 choose(SAY_OPTION, text=…)（server.say）
SAY_OPTION = "talk:say"
# NPC 智能 2.1（parley.py）：同「自己說」要打一句話的兩顆——對話裡跟答應陪你出陣的人商量打法、他帶路的路上跟他說一句
PLAN_OPTION = "talk:plan"
ROAD_SAY = "parley:road"
TEXT_TALKS = (SAY_OPTION, PLAN_OPTION, ROAD_SAY)
DUEL_FLEE = "duel:flee"  # 頭目戰的抽身退走（整季機器人不按它：bot.pick）
ARENA_YIELD = arena.YIELD_ID  # 擂台的認輸下台（整季機器人不按它：bot.pick）
SAY_MAX = 20  # 「自己說」最多幾個字（跟隨口應對一樣）


def say_text(text: str | None, limit: int = SAY_MAX) -> str | None:
    """「自己說」那句話能不能送：先去頭尾空白、中間連著的空白併成一個，1～limit 字才算數，再轉繁體（zh.to_traditional）；
    不行就是 None。長度在轉繁體之前量（轉換不改字數，量的是玩家打的）。limit 平常是 SAY_MAX，NPC 智能 2.0開著時照 Game.say_max。"""
    if text is None:
        return None
    text = " ".join(text.split())
    if not text or len(text) > limit:
        return None
    return zh.to_traditional(text)
# 必敗的遊歷按下去先問一次（FB-095；待 joy 潤）：「一成銀兩」跟 _lose_silver 的 silver // 10 是同一件事。
# 騎著馬時改用 TRAIN_CONFIRM_RIDING（裝備四欄 5.11），TRAIN_CONFIRM 本身不動（三個測試檔拿它比全等）
TRAIN_CONFIRM = "這裡的對手你現在打不過。輸了要掉氣血、受內傷，還要丟一成銀兩。還是要打？"
TRAIN_CONFIRM_RIDING = "這裡的對手你現在打不過。輸了要掉氣血、受內傷，還要丟一成銀兩（騎著馬，{odds}能保住）。還是要打？"  # 待 joy 潤
BIG_FIGHT_WAIT = "兩人對峙……"  # 大場面按下去、等模型判讀時按鈕上的字（武學與成長設計 8.3）
ROUND_BLOCKS = 5  # 決戰場景上留最近幾段戰況（開打那一句也算一段）
GAMBLE_SAID = "放手一搏：「"  # battle_instance.resolve_round 寫「某某放手一搏：「…」（評估成功率 N%）」那一行的認法
SIDE_TAG = "〔{side}〕"  # 戰況每一條是哪一軍的（Joy 2026-10-14）；網頁 app.js 的 roundBlocks 認這個寫法
ROUND_HEAD = "##### 第 {n} 回合"  # 一回合一段的標題（Joy 2026-10-14）；網頁 app.js 的 ROUND_HEAD 認這個寫法
RESTORED_NOTE = "（這份戰報是後來補回來的；軍餉與名望當時已經發過。）"  # Game._restore_showdowns
RESULT_LOOKBACK = 50  # 補戰報往回讓幾場流水號（攻城戰同時打，先開的可能晚收場；一天最多四場，五十場是十來天）
# 決戰戰況裡一軍這一回合發動戰法的那幾句摺成一行（Joy 2026-10-30「一堆好像是武學的技能，有什麼實質的作用」）：照 kind 歸成看得懂的幾類，
# 點開才是逐人那幾句（網頁 roundBlocks 把巢狀的那一層畫成摺疊）；自己的那一句不摺。沒列到的 kind 歸「其他」
WAR_FOLD = "{side}本回合 {n} 人發動武學"
WAR_FOLD_KINDS = {
    "回氣血": ("mend", "drain", "rally", "cleanse"),
    "加重": ("heavy_blow", "tiger", "waver", "bloodrage", "marshal", "tide", "night_raid", "reinforce", "sacrifice", "momentum", "assault", "zhaoyi"),
    "連環": ("chase_disarm", "vanguard", "surge", "cavalry", "swift", "last_rally", "oath"),
    "化影": ("veil", "shadow"),
    "無隙": ("unbroken", "flawless", "streak"),
    "固守": ("steady", "hold_city"),
    "號令": ("order",),
}
WAR_FOLD_MIN = 2  # 一軍這一回合至少幾句才摺（只有一句照舊一行）
MY_MOVE = "**你**　{move}"  # 決戰戰報的完整戰況：每一回合最後一條，自己這一回合出了什麼（BattleParticipant.moves）
SLAY_LINE = "你陣前擊退了{name}，這一戰的頭功傳遍兩軍。"  # 待 joy 潤：龍頭上陣，最後一擊的人（戰報與紀錄）
# 歷史武將同行第五節（待 joy 潤）：加入決戰時挑一位隨你上陣、決戰畫面上自己的那一位
ESCORT_PICK = "挑一位隨你出陣的同伴，或不派、自己上陣（開打之後不能換）。"
ESCORT_OPTION = "派{name}隨你出陣（份量 {score}・氣血 {pool}）"
ESCORT_NONE = "不派，自己上陣"
ESCORT_BACK = "再想想"
ESCORT_BACK_LINE = "你還沒加入，再想想。"
ESCORT_MUSTER = "{name}隨你出陣。"
ESCORT_SCENE = "隨你出陣：{name}（氣血 {hp}/{cap}）"
ESCORT_FELL = "隨你出陣：{name}（敗走）"
TROOPS_LINE = "你帶著{names}上陣，強攻、奇襲多 {pct}"  # 待 joy 潤（PM 2026-10-12）：決戰畫面，接在騎兵那一句後面（加入時的快照）
TROOPS_REPORT = "{names}跟著你衝陣"  # 待 joy 潤（PM 2026-10-12）：決戰的戰報
# 領地爭奪：戰書（翻地與爭搶，輿圖簡化設計 4.4；投票與 22:00 公告結算拿掉了，PM 2026-10-20）。待 joy 潤
LETTER_TITLE = "下戰書"
LETTER_DONE = "你替{side}下了戰書：{time} 攻{place}。這一塊的進度凍結到那一場打完。"
LETTER_JOINED = "你替{side}下了戰書，併進{time} 那一場：跟{others}同時攻{place}。"
LETTER_RANK = "只有這一週在任的第 4 階才能下戰書"
LETTER_NO_SLOT = "今明兩天都排不出攻城的時段"
CONQUEST_OFF = "這一季沒有攻城戰。"
CONQUEST_ENDED = "這一季已經收了。"
CONQUEST_PAY_TITLE = "攻下{place}"  # 分紅送到的那一則江湖紀錄（Game._deliver_conquest）
CONQUEST_GUARD_TITLE = "守住{place}"
CONQUEST_PAY_LINE = "{place}易手，你這一輪替{side}出了 {pct}% 的力，分得："
CONQUEST_GUARD_LINE = "{place}守住了，你這一輪替{side}拉回 {pct}% 的進度，分得守城功："
CONQUEST_TOP_ANNAL = "率先攻入{place}"  # 行狀（annals.CONQUER）
CONQUEST_TOP_GUARD_ANNAL = "力保{place}不失"
# 撞過一場混戰之後，截殺的拒絕話照實寫（FB-607：混戰跟截殺共用冷卻與護身那一本，以前一律寫「截殺過」「被人截殺過」）。待 joy 潤
RAID_AFTER_CLASH = "你跟{them}不久前才在混戰裡交過手，過一陣子再說。"
RAID_SHIELD_CLASH = "{them}剛跟人混戰過，元氣未復，這時下手太不講江湖道義。"
# 領地爭奪第三批 A：管理者「現在就開一篇天下形勢」的回話（管理者看的，待 joy 潤）
XINGSHI_OFF = "這一季沒有〈天下形勢〉。"
XINGSHI_OPENED = "第 {n} 篇〈天下形勢〉開了單：伺服器在背景請模型寫，寫不出來或 {minutes} 分鐘沒交回就照固定段收。"
SIEGE_STATUS = {"planned": "未開", "waiting": "即將集結", "open": "集結・交戰中", "void": "作罷"}
SIEGE_TAKEN = "{side}拿下"
SIEGE_HELD = "守住了"


def siege_status_text(content: Content, slot) -> str:
    """時程表上一場攻城的狀態那幾個字（待 joy 潤）。"""
    if slot.status == "done":
        return SIEGE_TAKEN.format(side=content.scenario.faction_name(slot.winner, slot.winner)) if slot.winner else SIEGE_HELD
    return SIEGE_STATUS.get(slot.status, "")


# 賽季時鐘暫停（線上架構設計第四節、8.3）：選單上那一顆灰的，伺服器擋動作也回這一句（server._refuse_while_paused）；PAUSED_TEXT 在核心（core/services.py）。待 S1／joy 潤
PAUSE_LINE = (  # 待 S1／joy 潤
    "賽季時鐘停了：季的時間不走、決戰不推，全服暫時不能行動，畫面照常可看；"
    "排好的決戰繼續之後照原本的時間開。做完記得按「繼續」。"
)
RESUME_LINE = (  # 待 S1／joy 潤；{skip} 是實際扣了多少（world.resume_skip_text：停不到一個季曆鐘頭就說不另外扣）
    "賽季時鐘接著走了（停了 {minutes} 分鐘）：{skip}；"
    "排好的決戰照原本的時間開，時間在暫停裡過了的現在就開始集結。"
)
PAUSED_REFUSAL = "（賽季時鐘暫停中，先按「繼續」。）"  # 暫停中的管理者動作；待 S1／joy 潤
# 管理者「立刻發軍令」的回話照軍令多久一道（orders.daily：照週一發、每天 00:00 發；FB-502，待 joy 潤）
ADMIN_REISSUE_HOW = {False: "週一", True: " 00:00 "}  # 「已照週一的做法重發」「已照 00:00 的做法重發」
ADMIN_REISSUE_NONE = {False: "這一週沒有要重挑的軍令", True: "今天沒有要重挑的軍令"}
# 管理者「立刻輪替第 4 階席次」的回話：7 天濃縮季照段（calendar.week7_on；FB-503，待 joy 潤）
ADMIN_ROTATE_FIRST = {
    False: "（第 1 週沒有上一週的貢獻可排；空缺照常由有資格的人補上。）",
    True: "（第 1 段沒有上一段的貢獻可排；空缺照常由有資格的人補上。）",
}
ADMIN_ROTATE_AGAIN = {False: "下週一照常再排", True: "下一段第一天 00:00 照常再排"}
ADMIN_ROTATE_LAST = "這是最後一段，季末之前不再排"  # 7 天濃縮季的最後一段沒有下一段


@dataclass(frozen=True)
class RaidSpoils:
    """一場截殺分出勝負之後的帳（Config.raid）：誰贏、輸的人失了多少銀兩、贏的拿走多少、輸的人掉多少氣血、贏的記多少貢獻。"""

    winner: str
    lost: int
    taken: int
    hp: int
    contrib: int
    goods: tuple[tuple[str, int], ...] = ()  # 設伏劫道：贏的搶走的素材（素材 id, 個數）；截殺沒有
    evil: int = 0  # 名聲 5.4：贏的人揭著輸的人的官府通緝，輸的人惡名少幾點（Config.renown.official_evil_loss）
# 管理者給的伏筆片段、機緣線索在那個玩家江湖紀錄裡那一則的標題（自然聽到的時候句子夾在那次行動的紀錄裡，沒有自己的標題；
# 也不說是哪一個機緣、不說是管理者給的，審查 M-1）。玩家看得到：新寫，待 joy 潤
HEARD_TITLE = "聽聞"
# 等模型判讀的時候選項沒了（另一個分頁把人帶走、事件被了結、體力花光）：這一仗不打，回這一句話代替一句看不出所以然的「無法這麼做」
FIGHT_LEFT = "你離開了，這一仗沒打成。"
FIGHT_CHANGED = "情勢變了，這一仗沒打成。"
FIGHT_GONE_LINES = (FIGHT_LEFT, FIGHT_CHANGED)


class Refused(list):
    """choose() 回的話，而且這一下是被擋下來的：懸賞選項已經不在選單上（兩個分頁搶同一張，FB-162）、馬市的鈕已經灰掉（FB-195）。沒做事、沒寫江湖紀錄，
    所以伺服器要把這句話直接傳去網頁跳提示（server.api_choose 看 isinstance）。是 list 的子類，其他地方照一般的訊息清單用。
    不放在 Game 的欄位裡：同一個角色的兩個分頁共用同一個 Game，鎖放掉之後別的請求可能已經改掉欄位；回傳值跟著這一次請求走。"""


# 賽季籌備中（管理者還沒開季）：選單上那一顆灰的、安排前往被擋的原因寫 PREPARING_TEXT；動作被擋回一句 PREPARING_REFUSAL
PREPARING_TEXT = "賽季籌備中，等待管理者開季"
PREPARING_REFUSAL = f"（{PREPARING_TEXT}。）"
# 測試期間一鍵補滿體力（Config.beta_free_refill，企劃者 2026-10-07）。以下四句與鈕上的字（Config.beta_free_refill_label）全是新寫的，待 joy 潤：
REFILL_TITLE = "補滿體力"  # 江湖紀錄那一則的標題（joy 的丹是「服下回體丹」）
REFILL_LINE = "你運了口氣，體力回滿了。"  # 補滿成功時寫進紀錄的那一句
REFILL_FULL = "體力是滿的，用不著補。"  # 體力本來就是滿的：跟丹的「這時候服丹是糟蹋」一樣，只回一句話、不寫紀錄
# 閒著的選單（在地點上、沒有事件、對話、路上、閉關、開打的決戰）一定有這一顆，拿它認「此刻閒著」（切磋、論武、假人答論武）。
# 以前認「打坐」（永遠按得下去），打坐 2026-10-12 拿掉之後改認探索：_everyday_options 第一顆，體力不夠也在（灰的）
IDLE_MARK = "act:explore"
PROLOGUE_REST = "調息（照師父教的吐納，把體力調回來）"  # 序章教體力那一步（打坐 2026-10-12 拿掉，只留這一下）
NO_REST = "（打坐已經拿掉了：體力會隨時辰自己回來，急用就服回體丹。）"  # 舊分頁按到 act:rest
PILL_DAY_FULL = "今天已服{n}顆，明日 00:00 後再服。"  # 回體丹一天的上限（企劃者 2026-10-12）
CN_COUNTS = {1: "一", 2: "兩", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}


def _cn_count(n: int) -> str:
    return CN_COUNTS.get(n, str(n))


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
    # 減法季批 4：分岔開著、這則事件寫了後果時是可能的走向（outcomes.tags；B 段照它改叫 event_llm.judge_outcome）；其餘是空的
    outcomes: list[dict[str, str]] = []


class BattleTextRequest(BaseModel):
    """放手一搏鎖外評估的單子（server.py 的 A 段拿到、B 段送模型評成功率、C 段交回 submit_battle_custom_action 重驗才送出）。"""
    battle_id: str
    act_index: int  # 送出時是第幾幕：評分照這一幕的情境（C 段送出時換了幕也照這個評過的分）
    faction_name: str
    text: str
    name: str = ""  # 送出的人的名號：劇情以他開頭（試玩回饋 2026-10-08）
    sex: str = "男"  # 送出的人的性別（gender）：模型寫劇情時的稱呼
    target: str = ""  # 點名的對手與身手（battle_instance.target_line，Joy 2026-10-10）：給模型多一行；沒點名是空的


class BattleTaleRequest(BaseModel):
    """回合結算後補放手一搏劇情的單子（server.narrate_battle 的 A 段拿到、B 段一整批送模型寫、C 段交回 apply_battle_tales
    重驗同一場才補）。done 是這一批的（回合, 名號）：寫到沒寫到，C 段都從等著補的單子拿掉。"""
    battle_id: str
    record_id: int | None
    opened: float  # 這一場集結截止的時間：跟 battle_id、record_id 一起認同一場
    act_index: int
    items: list[battle_instance.TaleItem]
    done: list[tuple[int, str]]


class DuelTextRequest(BaseModel):
    """頭目戰放手一搏鎖外評估的單子（server.duel_text 的 A 段拿到、B 段送模型、C 段交回 duel_gamble 重驗：同一隻、同一回合、同一句才用）。"""
    boss: str
    round: int
    text: str
    name: str
    faction_name: str
    title: str
    scene: str
    sex: str = "男"  # 性別（gender）：模型寫劇情時的稱呼
    # 擂台（tianxia/arena.py）也走這張單子：boss 寫「arena:場次」，多帶對手那一行與擂台的場合（assess_gamble 的 target、setting、place）；
    # 頭目戰空著，server.duel_text 照舊用 duel.SETTING、duel.PLACE
    target: str = ""
    setting: str = ""
    place: str = ""


class FreeTextOutcome(BaseModel):
    """擲完骰的結果：server.py 拿它在鎖外請模型潤色，再交回 add_gamble_narration 插進那一則江湖紀錄。"""
    event_id: str
    text: str
    success: bool
    effect_text: str
    time: float  # 那一則紀錄的遊戲時間與標題，插潤色前用來認是不是同一則
    title: str
    evil: bool = False  # 判成惡行而且成了（FB-223）：effect_text 是 rules.EVIL_DONE，潤色照惡行寫、寫成了換掉那一句
    outcome: str = ""  # 減法季批 4：分岔開著時走的是哪一種後果（id）；關著是空的


ONBOARD_SEGMENT = 4  # 初入江湖上線的版本章（ONBOARDING_VERSION 升到 4 的那一版）：比它小、已經走出草廬的存檔讀檔時蓋成引導走完
ONBOARD_SEVEN = 5  # 新手引導重做（老周七步、草廬第 7 步改服丹）的版本章：章是 4 的存檔讀檔時照 prologue.seven_step 換步數
SHOP_ACTS = frozenset({"smith", "bounties", "market", "arena"})  # 初入江湖「進城裡的鋪子看看」認的幾間（act:<這些>）
LEAVE_SHOP_IDS = frozenset({"bounty:back", "smith:back", mounts.BACK, arena.BACK_ID, tavern_rules.BACK_ID})  # 出店的那一顆

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
        self._loot_scale = 1.0  # 打贏的心得與銀兩倍數：練功分級（_practice，Config.training）那一場才不是 1
        # 減法季探索一顆（批 2）：遭遇拍那一場掉的素材打幾成（城裡的地痞 town_loot_scale、三道閘的倍數）；其餘的仗都是 1，一個字不變
        self._drop_scale = 1.0
        self._gate_scale = 1.0  # 減法季三道閘（批 2）：遭遇拍那一場的經驗、心得、銀兩乘疲勞與對手兩道閘（_fight_gate）；其餘是 1
        self._outing_close: set[str] = set()  # 這一趟出門打了折的那幾道閘（_fight_gate 記、_explore_one 寫段落結尾那一句）
        self._beat: dict | None = None  # 走一趟：剛剛那一次探索抽到什麼（_explore_one 寫、_outing_walk 讀）
        self._outing_upset = False  # 走一趟這一場遭遇開打前勝算凶險以下（_outing_fight 寫、_explore_one 讀）
        self._affinity_before: dict[str, int] | None = None  # choose()、隨口應對進行中：這一下之前的情誼（_people_here 認這一下加了誰的情誼）
        # 歷史武將同行：挑好了隨你上陣的那一位、正在照它加入（_escort_step 開著、_escort_carry 讀）
        self._escort_picked = False
        self._escort_now: battle_instance.Escort | None = None
        self._battle_ref: int | None = None  # 領地爭奪第二批：這一下按的鈕指定的那一場（加入鈕帶 @流水號，_battle_choose 設、_battle_now 讀）
        self._last_wear: list[str] = []  # 最近一場戰報歸檔時兵器鈍了、防具破了的提醒（_file_battle，兵器先、防具後）；沒有草稿的呼叫端（切磋、截殺的另一邊）自己接到訊息裡
        # 這一個動作動到（或要通知）的別人的名號（玩家卡上的互動、邀請）：伺服器做完動作叫他們開著的分頁也刷新（server._tell_tabs）
        self.touched: set[str] = set()
        # 事件旁白每週改寫（減法季批 10，tianxia/narration.py）：伺服器塞進來的查詢函式；沒有（假人程式、測試）一律照內容原文
        self.narration: narration.Lookup | None = None
        # 翻地與爭搶（領地爭奪）：這一下出陣撞上對面、打贏了（_push_progress 乘 clash_scale）；這一下出陣記過一筆了沒（_sortie 補記 0 的那一筆）
        self._clash_won = False
        self._sortie_marked = False
        self._sortie_moved = 0.0  # 這一下出陣自己推（拉）動了多少（_push_progress 加；出陣回報讀）
        self._sortie_flipped = False  # 這一下出陣推滿、當場易手
        # choose() 進行中那次行動、鎖外先判讀好的大場面（重驗過的，見 _checked_fight）；打那一場時用掉（_judged）
        self._fight: fight_llm.PreparedFight | None = None
        self._road_gain: tuple | None = None  # 這一件路上小事的收穫（_road 填、_share_road 分給結伴同行的人）
        # 找素材的「自己說」（第 32 項）：C 段 gather_say 重驗過的（那一句, 模型的成算, 屬性），走 choose(SAY_ID) 那一下用掉
        self._gather_said: tuple[str, int, str] | None = None
        self.last_gamble: FreeTextOutcome | None = None  # 上一次 answer_event 擲完骰的結果（server.py 拿去潤色）
        self.smith_result: dict | None = None  # 上一次 smith_forge 的出爐卡（server 的 /api/do/smith_forge 回給網頁）；被拒絕是 None
        self.mall_bought: str | None = None  # 上一次 mall_buy 買成的商品 id（/api/mall/buy 回給網頁：成了換掌櫃道謝、不成換原因）；不成是 None
        # 上一次 mall_buy 送的編號早就買好了（第一次的回應沒收到、同一個編號再送）：那一筆的商品 id，網頁照成了的樣子講（FB-491）；其餘是 None
        self.mall_already: str | None = None
        # 上一次玩家卡動作的一句短話（peer_act 每次清掉；論武合成了才填，FB-242）：網頁等回應時卡已經關了或換了人，提示泡泡只講這一句
        self.peer_brief: str | None = None
        self.forged = False  # 上一次 forge() 真的合成了（被拒絕的是 False）：煉製頁拿它決定爐子要不要清空（server.api_menxia_do）
        self.forged_thing: tuple[str, str] | None = None  # 上一次 forge() 合出來的那一樣（"art"／"ins", id）：煉製頁在結果底下畫它的卡
        self.secret_solved: dict | None = None  # 上一次開爐或裝意境這一季第一次參透一條秘方：跳的那個視窗（secret_recipes.solved_card）
        # 勝算的記憶（team.OddsMemo，FB-321）：伺服器上的 Game 共用一份（server.game_for 掛上），輿圖疊層與按鈕上的勝算輸入一樣就不再模擬；
        # 直接建的 Game（測試、腳本、假人程式）是 None，照舊每次算
        self.odds_memo: team.OddsMemo | None = None
        # 主畫面「走法」切換選的走法（步行／疾行），選單上的「前往」照它出發（見 _move_option）。只是畫面狀態：
        # 不在 GameState 裡、不進存檔。網頁伺服器的同一個角色只有一份 Game（各分頁共用、重新整理也還在），所以走法
        # 由頁面記著、每個請求帶上，server.py 在行動鎖裡逐次 set_move_mode（見 server.MOVE_MODE）；機器人與假人從不改它。
        self.move_mode: TravelMode = "walk"
        # 現在的現實時間（秒）：由 sync(now) 傳進來，引擎自己不讀電腦時鐘（線上架構設計第四節）。
        # 讀進來的存檔先用上次同步的時間；開戰的集結截止、回合逾時都看它。
        self.now: float = state.last_real if state.last_real is not None else 0.0
        # advance（快轉、整季機器人）推過的現實秒數：只給回體丹換日用（pill_now）。整季機器人的 now 開季後就不動，
        # 不加這一截的話一整季都算同一天
        self.advanced_real: float = 0.0
        self.own_request = False  # 這一份 Game 是不是那個人自己的請求（伺服器的 act／act_look 由 mark_seen 設）：奪璽單挑的 last_seen 只看它
        # 本人這一輪（名聲 4.6、5.4）：伺服器的 act／act_look（mark_seen）與假人程式自己那一輪（bot_runner）設。系統通緝只在這一輪掛。
        # 不借 own_request：假人刻意不設它（奪璽單挑裡永遠不在場），借了的話假人永遠不被掛單、一看就知道是假人
        self.own_turn = False
        self._drop_stale_references()

    def _quick_client(self) -> OllamaClient | None:
        """行動鎖裡叫模型用的 client：self.client 的複本，HTTP 逾時最多 Config.in_lock_model_timeout 秒（預設 15）、不重問
        （retry=False），所以鎖內任何一步模型呼叫最多佔住鎖那麼久。行動鎖拿著的時候全服玩家與假人都在等，模型慢或冷的時候
        照 ollama_timeout（120 秒）會凍住整台伺服器。所有在鎖內叫模型的地方都用它（大事與決戰回合的潤色、
        決戰自訂行動的評分、鎖內才備料的對話與記憶整理、鎖內才取名的開爐）；逾時或失敗各處本來就退回固定的文字。
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
        prologue: bool = False, graduated: bool = False, sex: str | None = None,
    ) -> Game:
        """prologue：走序章（新手引導計畫一）。只有網頁上建立角色（server.create_character）傳 True；假人、整季機器人、
        腳本與測試不傳，直接站在起點、序章算走過（沒有序章的內容兩種都一樣）。
        graduated：假人與整季機器人傳 True（bot_runner、bot.play_season）：不進草廬，但離開起點時的樣子要跟走完草廬的真人一樣
        （等級、一門師門功夫、盤纏、一點內傷：不然新人頭一個鐘頭就看得出誰是假人）——內容有序章才有作用，做法是把序章用真的
        行動走一遍（_graduate）。內容沒有序章（正式內容現在就是）什麼都不做，連亂數都不多用一次。
        sex：建角色時選的性別（「男」／「女」，gender.GENDERS）：給了就定了（gender_chosen）；沒給是男、設定頁還能選一次。
        假人由 bot_runner 照比例給（gender.for_bot）。"""
        state = new_game_state(content, name)
        state.player.pills_topped_to = content.config.beta_gift_stamina_pills if content.config.beta_gift else 0  # 新角色照下面的贈送拿，不另補
        game = cls(content, state, rng, world)
        if sex in gender.GENDERS:
            game.state.player.gender, game.state.player.gender_chosen = sex, True
        if (prologue or graduated) and opening_rules.on(content, game.state.world):
            # 減法季的開局第一分鐘（整合設計 6.7）：真人與假人都不進草廬，站在起點看旁白、三選一；人物的信在選完那一下送到（choose）
            opening_rules.begin(game.state, content)
        elif prologue:
            prologue_rules.begin(game.state, content)
        elif graduated and prologue_rules.has(content):
            game._graduate()
        else:
            # 第二季起建的角色，__init__ 的換季重來已經把新角色放進序章（體力也換成序章的）：這裡拉回起點、滿體力
            prologue_rules.finish(game.state, content, game.world, purse=False)
            prologue_rules.skip_onboarding(game.state, content)  # 假人、機器人、腳本：初入江湖是給網頁上的真人看的
            if prologue_rules.has(content):
                game.state.player.stamina = float(content.config.stamina_max)
        p = game.state.player
        p.visited.add(p.location)
        gift = content.config.beta_gift and content.config.beta_gift_stamina_pills > 0
        if gift:  # 內測贈送（企劃者 2026-10-07）：真人、假人、整季機器人建角色時一樣拿到
            p.stamina_pills += content.config.beta_gift_stamina_pills
        game._log(
            [f"══ {content.scenario.name} ══", content.scenario.intro, game.location_text()]
            + tutorial_intro(content)
        )
        if not game.state.journal:  # 第二季起建的角色：__init__ 的換季重來已經寫了開場那一則，不再寫一次（FB-052）
            game._write(content.scenario.name, [content.scenario.intro], tag=journal.SEASON_START, guide=tutorial_intro(content))
        if gift:
            game._note_gift()
        return game

    def _note_gift(self) -> None:
        """建角色時送了回體丹：江湖紀錄開場那一則多一行（explain-1：以前送了二十顆卻沒有任何紀錄）。接在開場那一則裡、不另起一則：
        「剛剛」不換（序章第一屏照舊什麼都不放），江湖紀錄裡看得到。只寫字，不擲骰、不動數值（假人、整季機器人照樣有這一行）。"""
        entries = self.state.journal
        line = howto.gift_line(self.content)
        if entries and entries[0].tag == journal.SEASON_START:
            entries[0] = entries[0].model_copy(update={"lines": [*entries[0].lines, line]})
        else:
            self._write(self.content.scenario.name, [line], tag=journal.SEASON_START)

    def _top_up_pills(self) -> None:
        """拿掉一鍵補滿之後補回體丹（企劃者 2026-10-12；見 PlayerState.pills_topped_to）：讀檔那一刻，贈送的數比上次補到的多，
        手上不到那個數就補到那個數、江湖紀錄寫一行。真人、假人、整季機器人一樣（假人看不出來）。"""
        cfg, p = self.content.config, self.state.player
        target = cfg.beta_gift_stamina_pills if cfg.beta_gift else 0
        if target <= p.pills_topped_to:
            return
        p.pills_topped_to = target
        if p.stamina_pills >= target:
            return
        added = target - p.stamina_pills
        p.stamina_pills = target
        self._write(cfg.stamina_pill_name, [howto.top_up_line(self.content, added)])

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
        prologue_rules.skip_onboarding(s, self.content)  # 初入江湖（新手引導第四段）是給真人看的
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
        fused = prologue_rules.slotted_arts(s, c, self.world)
        if goal.action == "view_tab":
            tab = next((flag.removeprefix("看過:") for flag in goal.condition.flags_all if flag.startswith("看過:")), "")
            self.view_tab(tab)
        elif step.explore_event is not None or step.explore_scene is not None:
            self.choose("act:explore")
        elif goal.fused:  # 武學重構：把悟到的意境裝進師父點名的那一門
            if not p.insights or step.fuse_base is None:
                return False
            self.slot_insight(step.fuse_base, self.rng.choice(p.insights))
        elif goal.fused_level and fused:
            art = fused[0]
            if art.id not in (p.member.wugong_id, p.member.neigong_id):
                self.switch_art(art.id)
            else:
                self.practice(art.kind)
        elif goal.deepened and p.insights:  # 揣摩（意境效果池：同一種意境的兩份）
            base = insight_fx.base_id(p.insights[0])
            pair = insight_fx.pieces(self.state, base)[:2]
            if len(pair) < 2:
                return False
            self.forge(None, pair)
        elif goal.action in ("rest", "train", "explore"):
            self.choose(f"act:{goal.action}")
        elif goal.action == "pill":  # 序章服回體丹（新手引導重做）：假人也真的服一顆（同真人，看不出來）
            self.take_stamina_pill(pill_only=True)
        elif goal.action == "allocate":
            open_stats = [k for k in team.COMBAT_STATS if p.stats.get(k, 0) < c.config.stat_cap]
            if not open_stats:
                return False
            self.allocate_stat(self.rng.choice(open_stats))
        elif "melt" in (goal.action, *goal.any_action) and step.melt_only:
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
        past = self._zhuan_past(old)  # 列傳為終點（減法季批 7b）：收季之後沒回來過的人，存之前補季末論功與〈天下形勢〉
        storyline.close_season(old, self.content)  # 一條線：還沒收的寫「此事未了」進傳（休季時同步過的已經寫了）
        if old.player.annals:  # 行狀跟著角色重來：先把上一季的存起來，季末的傳照它寫（玩家傳）
            self.world.save_annals(
                old.player.season_number, old.player.name, [e.model_dump() for e in old.player.annals],
                annals.profile(old, self.content, season=past),
            )
        features_core.on_season_end(self)  # 功能包：舊的那一季要丟之前（self.state 還是舊的；開發規範手冊 3.3）
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
                # 序章走完了、後面的步驟還沒做完（或是假人、腳本）：從序章之後的起始步重來，不再回草廬；假人不走初入江湖
                t = self.content.tutorial
                fresh.player.tutorial_step = t.prologue_steps
                if old.player.bot:
                    prologue_rules.skip_onboarding(fresh, self.content)
        if enlist.done(old, self.content):
            fresh.player.enlist_step = old.player.enlist_step  # 入伍段只走一次（設計 7.1）；沒走完的下一季投靠時從頭走
        # 碰到才說（新手引導計畫三）：說過的與「不再提示」的開關帶到下一季，排著還沒上框的不帶（沒說過，下一季碰到還會說）。
        # 引導走完的回鍋玩家，開季時師父送你下山一句（設計 7.1）；略過引導的人沒有要誰帶（控制者裁示），假人、關了提示的、內容沒寫的也不送
        fresh.player.hints_seen = set(old.player.hints_seen)
        fresh.player.hints_off = old.player.hints_off
        fresh.player.renown_told = old.player.renown_told  # 名聲：兩個稱號說明過了就不再說（段 renown_seen 跟角色一起重來）
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
        fresh.player.gender, fresh.player.gender_chosen = old.player.gender, old.player.gender_chosen  # 性別跨季保留
        fresh.player.stamina_pills = old.player.stamina_pills  # 回體丹是建角色時送的，換季不再送，剩下的帶著走
        # 破境丹、重悟帖萬寶閣賣（花元寶買的不能換季就不見），同回體丹剩下的帶著走（Joy 2026-10-21「再研究一下有沒有什麼瑕疵」）
        fresh.player.legend_items = old.player.legend_items
        fresh.player.create_rerolls = old.player.create_rerolls
        fresh.player.pills_topped_to = old.player.pills_topped_to  # 補過的不再補（第二季起建的角色在這裡還沒拿贈送）
        fresh.player.pill_day, fresh.player.pills_today = old.player.pill_day, old.player.pills_today  # 換季不能多吃一輪
        fresh.player.drill_day, fresh.player.drills_today = old.player.drill_day, old.player.drills_today  # 換季不能多操練一輪
        fresh.player.newbie_marks, fresh.player.newbie_done = old.player.newbie_marks, old.player.newbie_done  # 新手目標只有一輪
        fresh.player.upgrade_day, fresh.player.upgrades_today = old.player.upgrade_day, old.player.upgrades_today  # 換季不能多升一輪三階
        fresh.player.donate_day, fresh.player.donated_today = old.player.donate_day, old.player.donated_today  # 換季不能多捐一輪
        fresh.player.battle_results_seen = old.player.battle_results_seen  # 補送過的決戰不再補一次（FB-027）
        fresh.player.heirloom = old.player.heirloom  # 玉璽碎片的抄本與補送的進度跨季帶走（玉璽碎片設計 7.5；同步時本來就照登記重抄）
        # 神器輪替與收集（正式季整合 5.8）：輪替季打的神器（collected）跨季帶走、放進裝備庫，以器配招清掉，品質淬煉磨損照舊；
        # 帶了東西過來流水號才接著走（帶過來的 id 不會跟新打的撞；沒帶的照上線前重來，FB-401）；鑄譜上打中過的神器記得（forge_secrets.divine_solved）
        carried = [item for item in forge_secrets.owned_gear(old.player) if item.collected and item.signature is None]
        for item in carried:
            item.bound_art = None
        fresh.player.rack = carried + fresh.player.rack
        if carried:
            fresh.player.weapon_serial = max(fresh.player.weapon_serial, old.player.weapon_serial)
        fresh.player.divine_solved = dict(old.player.divine_solved)
        fresh.player.seal_seen = old.player.seal_seen
        # 名帖（Joy 2026-10-19）：自己那一張、收到的、藏起來的、不接誰的挑釁話都是自己的東西，跨季保留；
        # 這一季值得留名的頭銜寫進 title_book（「第N季 天下第一」），一天的次數照回體丹不能換季多一輪
        fresh.player.mingtie, fresh.player.mingtie_box = old.player.mingtie, old.player.mingtie_box
        fresh.player.mingtie_hidden, fresh.player.taunt_muted = old.player.mingtie_hidden, old.player.taunt_muted
        fresh.player.mingtie_day, fresh.player.mingtie_made, fresh.player.mingtie_sent = (
            old.player.mingtie_day, old.player.mingtie_made, old.player.mingtie_sent)
        fresh.player.gift_day, fresh.player.gifts_today = old.player.gift_day, old.player.gifts_today
        book_titles = mingtie_rules.season_book(old, self.content, old.player.season_number)
        fresh.player.title_book = old.player.title_book + [t for t in book_titles if t not in old.player.title_book]
        fresh.player.seen_real = old.player.seen_real
        # 長篇奇事（企劃者 2026-10-27）：紀念物一輩子帶著；跨季的旗標（例：隆中藏書）在新角色身上再立一次
        fresh.player.keepsakes, fresh.player.lasting = list(old.player.keepsakes), list(old.player.lasting)
        fresh.player.flags |= set(old.player.lasting)
        fresh.player.season_number = season_number
        self.state = fresh
        self.state.world = self.world.get_season()  # 開場那一則記此刻的季時間（FB-052：以前記成新存檔的 0）
        self.state.player.visited.add(self.state.player.location)
        features_core.on_season_start(self, old)  # 功能包：新的存檔接上了、開場那一則之前（old 是上一季的）
        self._write(
            self.content.scenario.name, [self.content.scenario.intro], tag=journal.SEASON_START, guide=tutorial_intro(self.content),
        )
        self._season_grant(old)

    def _zhuan_past(self, old: GameState) -> WorldState | None:
        """換季那一刻（_reset_player_for_new_season）：上一季開著列傳為終點（zhuan_end）就回那一季（WorldStateStore.past_season），
        先替這個人補上收季之後還沒記的季末論功與〈天下形勢〉（同步時記的那兩種，annals.tier_note、xingshi_notes），身家照它多論功的那幾樣；
        關著（設定沒開就不讀資料庫）是 None，一個字都不變。old 是上一季的存檔，馬上就丟：old.world 換成上一季那一份才記得到正確的時刻。"""
        cfg = self.content.config.jianfa
        if not (cfg.enabled and cfg.zhuan_end):
            return None
        past = self.world.past_season(old.player.season_number)
        if past is None or not jianfa(self.content, past, "zhuan_end"):
            return None
        old.world = past
        annals.xingshi_notes(old, self.content, past)
        annals.tier_note(old, self.content, past)
        return past

    def _season_grant(self, old: GameState) -> None:
        """三陣營四勝利（減法季設計 3.3）：上一季收季時論了功的人（那一季的 WorldState.final_tiers），新的一季開局照那一階發起手資源
        （wins.start_grant）、掛上稱號（PlayerState.season_title，social.affiliation 接在後面），另寫一則江湖紀錄。
        上一季沒論功（四勝利關著、散人、不到門檻）什麼都不做，一個字都不變。不看新的一季開不開四勝利：獎勵是上一季掙的。"""
        past = self.world.past_season(old.player.season_number)
        result = past.final_tiers.get(old.player.name) if past is not None else None
        if result is None or not result.tier:
            return
        silver, xinde = wins.start_grant(wins.rules_of(self.content), result.tier)
        p = self.state.player
        p.stats["silver"] = p.stats.get("silver", 0) + silver
        p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
        p.season_title = result.title
        line = wins.GRANT_LINE.format(tier=wins.TIER_NAMES[result.tier], title=result.title)
        self._write(wins.GRANT_TITLE, [line] + [f"{name} +{n}" for name, n in (("銀兩", silver), ("心得", xinde)) if n])

    def _drop_old_zhuifeng(self) -> None:
        """追風步（PM 2026-10-14；企劃者跟玩家談過，玩家同意退回下品）：內容以前沒寫品質、照 SkillDef 的預設成了絕學，現在是下品。
        舊角色讀檔時照內容讀就是下品（沒有自己那一份的紀錄）；中間有一版（7f993d2）把絕學寫進了自己那一份
        （art_quality、art_rolled），這裡拿掉。追風步沒融意境、修練不了，自己那一份記成絕學只可能是那一版寫的，
        不會碰到自己修練上去的紀錄；絕學定名、江湖史只記修練上去的絕學，也碰不到它。"""
        p = self.state.player
        if p.art_quality.get("zhuifeng") == "絕學":
            del p.art_quality["zhuifeng"]

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
        self._top_up_pills()
        self._drop_old_zhuifeng()
        s.player.resting_since = None  # 打坐 2026-10-12 拿掉了：存檔時坐著的人讀檔就起身（只是不再回得比較快，沒有別的帳要算）
        sensing.drop_stale(s, c)  # 有所感的場景被拿掉、人不在那裡了：作廢（悟意境設計第零節）
        if p.pending_companion and p.pending_companion not in c.characters:
            p.pending_companion = None
        if p.pending_faction and p.pending_faction not in {f.id for f in c.scenario.factions}:
            p.pending_faction = None
        if p.pending_ally and p.pending_ally not in {f.id for f in c.scenario.factions}:
            p.pending_ally = None
        if p.pending_defect and p.pending_defect not in {f.id for f in c.scenario.factions}:
            p.pending_defect = None
        lost_place = p.location not in c.locations
        if lost_place:
            p.location = c.scenario.start_location
        if p.picking_audience and not self._audience_hall():
            p.picking_audience = False  # 內容改版後這裡不再有兩位以上的人物：收起求見選單
        if p.picking_bounty and not bounties.board_here(s, c):
            bounties.close_board(p)  # 懸賞榜關了（Config.bounties.enabled、劇本沒有陣營）、人不在城鎮了：收起懸賞榜，挑到哪一張與榜吏那一句一併清掉
        if p.picking_smith and not equipment.smith_open(s, c):
            equipment.close_smith(p)  # 武器、防具都關了、人不在城鎮了：收起鐵匠鋪，打造的單子與停在哪一頁一起清
        if p.smith_draft is not None and (
            not p.picking_smith or not smithing.draft_here(s, c, p.smith_draft) or smithing.draft_stale(c, p.smith_draft)
        ):
            p.smith_draft = None  # 單子只在鐵匠鋪開著、那一欄也開著時有意義（兵器的單子看武器、防具的單子看防具：一欄關了另一欄還開著，鐵匠鋪照開，那一欄的單子要清）；內容改版拿掉了單子上的種類或素材：選單畫不出來，從頭來
        if p.picking_market and not mounts.market_here(s, c):
            mounts.close_market(p)  # 坐騎關了、人不在馬市了：收起馬市（裝備四欄 5.5），馬販那一句一併清掉
        if p.picking_donate and not self._at_own_base():
            economy.close_donate(s)  # 捐軍備關了、人不在自家大本營了（叛投、管理者挪人）：收起軍需官那一串
        if p.picking_dadian and not self._silver_options():
            self._close_dadian()  # 銀兩出口關了、這裡一樣都做不了了：收起打點那一間店
        if p.picking_arena and not arena.here(s, c):
            p.picking_arena = False  # 擂台關了、季收了：收起擂台
        if p.picking_tavern and not tavern_rules.here(s, c):
            tavern_rules.close(s)  # 酒肆關了、人不在有酒肆的城鎮了：收起酒肆
        treasures.refresh_names(p, c)  # 寶物、名駒的名字照內容讀（裝備四欄 3.1）：joy 改了名字，存檔裡的跟著改；內容拿掉了留著舊名字
        forge_secrets.refresh_names(p, c, self.world)  # 名器的名字照內容讀（4.2）、神器的名字照全服那一列讀（5.2、5.3：原品定了名，仿品跟著改）
        signature_arms.refresh_names(p, c)  # 本命兵器的名字照內容讀（打造第三批）：joy 改了名，手上的跟著改
        self._copy_heirloom()  # 玉璽碎片的抄本照登記重抄（7.4）：建 Game（含 _kin、_load_kin）就對
        j = p.journey
        if j is not None and (
            lost_place  # 所在地被拿掉、改回起點：腳下這段路已經不存在
            or any(loc_id not in c.locations for loc_id in j.path)
            or (j.origin is not None and j.origin not in c.locations)  # 改道後半段路的起點（見 atlas.road_spot）
        ):
            p.journey = None
            p.leg_actions = set()  # 這段路不在了：下次出發是新的一段
        p.leg_actions &= set(ROAD_TASKS)
        p.recent_sights = [sight_id for sight_id in p.recent_sights if sight_id in c.road_sights]
        p.team = [k for k in p.team if k in c.characters][: team.MAX_TEAM_COMPANIONS]
        if roster.on(c):  # 歷史武將同行：出戰隊伍只放名下的（決戰後回江湖、放走、叛投帶不走的人，主人下次讀檔就不在隊伍裡）
            mine = set(roster.owned_companions(self.world, p.name))
            p.team = [k for k in p.team if k in mine]
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
        # 本命武學學到時直接第七成（企劃者 2026-10-15）：這一版之前學到的舊角色讀檔補上，已經練得更高的不動
        signature.lift_levels(s, c, signature.learned(s, c))
        p.materials = {k: v for k, v in p.materials.items() if k in c.materials and v > 0}
        # 武學與成長（設計第三、四節）：意境去重、去掉找不到的；品質、熟練度只留還擁有的武學；
        # 等著取名的那一門要真的是自己第一個練成的（換季、熔掉、內容改版後都可能對不上）
        p.insights = [i for i in dict.fromkeys(p.insights) if insights.resolve(i, c, self.world, s) is not None]
        p.own_insights = {k: v for k, v in p.own_insights.items() if k in p.insights}  # 熔掉的私有意境本體跟著拿掉
        owned = set(library.owned_arts(s))
        p.art_quality = {k: v for k, v in p.art_quality.items() if k in owned and v in QUALITIES}
        p.art_mastery = {k: v for k, v in p.art_mastery.items() if k in owned and v > 0}
        arts_mod.migrate(s, c, self.world)  # 武學重構：舊存檔的功效轉成槽（只做一次）
        arts_mod.prune(s, c, self.world)  # 槽只留自己還有的武學與意境
        create.prune(s, c)  # 自創的舊三步單子收掉（還沒付錢）
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
        if prologue_rules.has(c) and p.onboarding < ONBOARD_SEGMENT and p.tutorial_step >= c.tutorial.prologue_steps:
            # 初入江湖（新手引導第四段）上線之前就走出草廬的人不回頭走：跳過它（沒有框、不寫話）
            prologue_rules.skip_onboarding(s, c)
        elif prologue_rules.has(c) and p.onboarding < ONBOARD_SEVEN:
            p.tutorial_step = prologue_rules.seven_step(p.tutorial_step, c)  # 老周四步改七步：走到一半的接到對應的那一步
            if prologue_rules.pills_open(s, c) and p.stamina_pills < 1:  # 停在草廬服丹那一步（以前是調息）、身上沒丹：照那一步送的補上
                p.stamina_pills += max(st.give_pills for st in c.tutorial.steps)
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
        features_core.on_drop_stale(self)  # 功能包自己的失效參照（開發規範手冊 3.3）

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
        # 減法季批 4：痕跡過門檻的防漏（只發，不替任何人記行狀：排程那一份 Game 沒有自己的人；直接寫回、不經 _save_season）
        if jianfa(self.content, self.state.world, "marks_visible") and marks_rules.fire_due(self.state, self.content):
            self.world.save_season(self.state.world)
        self._sortie_duel_tick()  # 減法季批 3b：窗滿了的約戰沒人在線也照時結算（關著、沒有到時的什麼都不做、不寫）
        msgs += self._conquest_tick()  # 領地爭奪：22:00 沒人在線也照時換天
        self._battle_status(tick=True)
        self._seal_tick()
        return msgs

    def sync(self, now: float) -> list[str]:
        """把現實經過的時間推進到遊戲裡。玩家自己的體力/氣血照自己上次連線以來的步調追趕；
        共用賽季的時間/大勢則照「距離上次有人追趕過了多久現實時間」追趕——不管是誰觸發、
        隔多久觸發一次，一份共用時鐘永遠只走一次，不會因為好幾個玩家同時在線就重複推進
        （見 world_state.py::catch_up_season）。也會順便偵測共用賽季是不是已經被別人推到
        下一輪了（見 _reconcile_season）。在路上時，抵達時間已經到了的站接著一站一站抵達（見 _arrivals）。"""
        self.now = now
        away_from = self.state.last_real  # 上次同步的現實時間，下面就換成 now（「你不在的時候」看它，見 _deliver_away）
        before = {id(e) for e in self.state.journal}  # 名聲：這一次同步補進來的那幾則也接差距（_renown_after 的 fresh，FB-292）
        self._reconcile_season()
        msgs = list(self.world.catch_up_season(self.content, now, self.rng))
        self.state.world = self.world.get_season()  # 剛才的追趕可能進一步推進了賽季，拉回最新的一份
        # 減法季批 3b：排程關著（或還沒輪到）時，下一個同步的人替窗滿了的約戰結算（只往前走；手上這一份季剛讀回來，結算改的進度當場存）
        self._sortie_duel_tick()
        self._stamp_join()  # 新角色、換季重來的角色：補算完賽季才記下加入的那一刻
        self._week_unlock_tick()  # 減法季 6.6：第 2 週的功能對這個人開了的那一刻，寫一則紀錄
        self._record_faction()
        self._copy_heirloom()  # 排在 _advance_player_local 之前：承露照整段離線時間算體力回復（7.4）
        elapsed = 0.0  # 這一次補算的自己的秒數（功能包的 on_sync 拿它）
        if self.state.last_real is None:
            self.state.last_real = now
        else:
            elapsed = max(0.0, now - self.state.last_real) * self.content.config.time_scale
            self.state.last_real = now
            msgs += self._advance_player_local(elapsed)
            if away_from is not None and now - away_from >= self.content.config.tavern.hit_offline_minutes * 60:
                if self._tavern_hit_check(away_from):  # 酒肆：下線那一段殺手找上門（站在城外下線的人）；戰報與紀錄自己寫，不併進江湖大事
                    self._save_season()
        if self.state.player.picking_smith and not equipment.smith_open(self.state, self.content):
            equipment.close_smith(self.state.player)  # 開關關了、人不在城鎮了（內容改版、管理者挪人）：收起鐵匠鋪，單子與頁一起清
        if self.state.player.smith_draft is not None and not smithing.draft_here(self.state, self.content, self.state.player.smith_draft):
            self.state.player.smith_draft = None  # 單子那一欄關了、另一欄還開著：鐵匠鋪照開（另一頁），這張單子清掉
        if self.state.player.picking_market and not mounts.market_here(self.state, self.content):
            mounts.close_market(self.state.player)  # 開關關了、人不在馬市了（內容改版、管理者挪人）：收起馬市
        if self.state.player.picking_donate and not self._at_own_base():
            economy.close_donate(self.state)  # 捐軍備關了、人不在自家大本營了：收起軍需官那一串
        if self.state.player.picking_dadian and not self._silver_options():
            self._close_dadian()  # 銀兩出口關了、這裡一樣都做不了了：收起打點那一間店
        if self.state.player.picking_arena and not arena.here(self.state, self.content):
            self.state.player.picking_arena = False  # 擂台關了、季收了：收起擂台
        if self.state.player.picking_tavern and not tavern_rules.here(self.state, self.content):
            tavern_rules.close(self.state)  # 酒肆關了、人被挪走了：收起酒肆
        self._ambush_expire()  # 守著的埋伏到時刻了、或季上那一筆已經沒了（被打退、換季）：收起來
        arrived = self._arrivals()  # 抵達的站自己寫一則江湖紀錄（途中觸發的大事也寫在那裡），不併進下面的「江湖大事」
        if arrived:
            self._save_season()  # 抵達時觸發的大勢門檻改了共用賽季
        news = journal.news_entry(self.state.world.time, self._without_timetable(msgs))
        if news is not None:
            journal.add_entry(self.state, news, merge=True)
        self._deliver_big_events()  # 這一季的時刻表大事人人有份：沒看過的補上，推進的人也走這一條（FB-038）
        self._backfill_battle_scores()  # 場上沒有份量快照的自己（上線前就在決戰裡）：補上；排程的 world_tick 不走這裡
        self._deliver_battle_results()  # 下線時收場的決戰，回來第一次同步就補上（休季、籌備中也一樣，FB-027）
        self._deliver_seal_results()  # 玉璽碎片：現世、單挑收場、隱沒（5.9），下線時發生的回來補
        self._deliver_renames()  # 手上的絕學被人定了名：下一次同步補一則紀錄（FB-083）
        self._deliver_echoes()  # 別人照著你首創的配方合了出來：補名望（首創名望回饋）
        self._deliver_guard_credits()  # 護衛：下線時替人物擋下的挑戰，回來補名望與心得
        self._deliver_whispers()  # 酒肆：有人在酒肆打聽你（風聲），下線時的回來補
        self._deliver_hits()  # 酒肆：自己雇的殺手得手、失手、到期退錢
        self._deliver_watches()  # 酒肆：託酒家留意的人有了準信、或到期沒消息
        self._conquest_tick()  # 領地爭奪：換天（22:00）的掛鉤（前一天沒開成的攻城作罷；第一個看到新的一天的人觸發）
        self._deliver_conquest()  # 領地爭奪：翻地的分紅、守城功（下線時易手的回來補）
        self._deliver_arena()  # 擂台：被挑了的戰報、季末前三名的獎勵；季收了還沒打完的那一場作廢
        self._marks_tick()  # 減法季批 4：痕跡過門檻的防漏、替自己記出過力的行狀（關著什麼都不做）
        self._stance_annals()  # 減法季批 6：這一週勸過的心意到了門檻，記一則行狀（關著什麼都不做）
        self._zhuan_tick()  # 減法季批 7b：〈天下形勢〉寫到名號、季末論功各記一則行狀（關著什麼都不做）
        mail = parley.lapse(self.state, self.content)  # NPC 智能 2.1：欠人物的事過了期限是食言（附的委託先作罷，書信不再補一句）
        mail += letters.deliver(self.state, self.content, now)  # 書信（大勢人物擴充第二批）：人物來信、過期的委託作罷
        if mail:
            self._write(letters.TITLE, mail)
        settled = plans.deliver(self.state, self.content)  # 世界活起來：我插過手的盤算有了結果
        if settled:
            self._write(plans.TITLE, settled)
        # 功能包：回體丹那一天換了（台灣 00:00；上一次同步之後第一次）。同 _pill_day 照現實時間加快轉推過的那一截（advanced_real）比：
        # 快轉跨過的那一次 advance 自己報過了，這裡只比上一次同步到這一次同步那一段
        if away_from is None or self._day_of(away_from + self.advanced_real) != self._pill_day():
            features_core.on_day(self)
        features_core.on_sync(self, elapsed)  # 功能包的補算（開發規範手冊 3.3；宴客：散席時席間最佳補名望、宴散了收起敬酒的選單）
        self._deliver_held_gear()  # 寄放的重賞、贈禮：裝備庫有空位就補（裝備四欄 6.5）
        self._auto_checkin()  # 每日簽到自動領（Joy 2026-10-24 挑江湖頁乙案：簽到不放鈕）；要挑四階的日子留給玩家挑
        self._settle_partings()  # 歷史武將同行：從你身邊回江湖的人，情誼減半（9.6；補戰報時已經算過的不再算）
        refunds = bounties.deliver_refunds(self.state, self.content)  # 掛的通緝沒人揭成：押金退回
        if refunds:
            self._write(bounties.BOARD, refunds)
            self._save_season()
        lapses = bounties.deliver_lapses(self.state, self.content)  # 揭了的被別人交滿名額、或過了期限：拿掉名字、補一句（FB-121）
        if lapses:
            self._write(bounties.BOARD, lapses)
            self._save_season()
        settled = self._settle_plots()  # 不在線時收場的密謀，回來第一次同步就結算（正式版乙二）
        if settled:
            self._write("密謀", settled)
            self._save_season()  # 逾期的密謀在這裡改成作罷，那是共用賽季的一份
        summons = ranks.check_summons(self.state, self.content)  # 行動之外記到的貢獻（抵達、別人觸發的結算）：同步時補發召見（計畫 T5）
        if summons:
            self._write("召見", summons)
        story = self._story_tick()  # 一條線：不在線時過了的期限、休季時還沒收的（此事未了），回來第一次同步就走
        if story:
            self._write(storyline.JOURNAL, story)
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
        self._party_expires()  # 答應結伴之後帶頭的人遲遲沒動身：各走各的（玩家互動第二層）
        # 名聲：同步時發現的跨段另起一則「名聲」（設計 3.3）；這一次補進來的那幾則接差距
        self._renown_after(synced=True, fresh=[e for e in self.state.journal if id(e) not in before])
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
        self._week_unlock_tick()
        msgs: list[str] = []
        if self.world.season_phase() == "running":
            msgs += advance_world_state(self.state.world, self.content, seconds, self.rng, self.world)
        msgs += self._advance_player_local(seconds)
        day_before = self._pill_day()
        self.advanced_real += seconds / self.content.config.time_scale
        if self._pill_day() != day_before:
            features_core.on_day(self)  # 功能包：快轉跨過 00:00，回體丹那一天換了（同 sync；管理者快轉、整季機器人）
        arrived = self._arrivals()  # 同 sync：抵達自己寫紀錄
        msgs += self._conquest_tick(save=False)  # 領地爭奪：快轉跨過 22:00 也換天（下面一起存）
        self._deliver_conquest()  # 同 sync：快轉（與只 advance 的整季機器人）也補翻地的分紅
        self._sortie_duel_tick()  # 減法季批 3b：快轉不動現實時刻，約戰的窗照現實時間；快轉到季末時還沒打的作廢、退次數
        self._save_season()
        msgs += start_pending_battle(self.world, self.content, self.now)
        self.state.world = self.world.get_season()
        self._week_unlock_tick()  # 推完了再看一次：快轉跨過第 2 週（整季機器人、測試）那一下就寫
        news = journal.news_entry(self.state.world.time, self._without_timetable(msgs))
        if news is not None:
            journal.add_entry(self.state, news, merge=True)
        self._deliver_big_events()
        self._deliver_held_gear()  # 同 sync：快轉（與只 advance 的整季機器人）也補寄放的東西
        return self._log(msgs + arrived)

    def _stamp_join(self) -> None:
        """記下這個角色加入這一季的那一刻（PlayerState.joined_at，新手福利從這裡起算，第一季設計第十四節）：
        新角色與換季重來的角色是 None，第一次 sync（補算完賽季之後）或 advance 才蓋；蓋過就不再動。"""
        p = self.state.player
        if p.joined_at is None:
            p.joined_at = self.state.world.time

    def week_unlock_names(self) -> list[str]:
        """第 2 週才開的功能裡這一季真的有的（減法季 6.6；week_unlock.WEEK2 的順序）：擂台、懸賞榜。
        紀錄那一行、本週卡那一句照它列；一樣都沒有是空的。"""
        s, c = self.state, self.content
        have = {"arena": arena.on(c), "bounties": bounties.active(s, c)}
        return [name for key, name in week_unlock.WEEK2.items() if have.get(key)]

    def _week_unlock_tick(self) -> None:
        """第 2 週的功能對這個人開了的那一刻（減法季 6.6「開了的那一刻江湖紀錄一行、本週卡一句」）：蓋 PlayerState.week_unlocked_at、
        寫一則紀錄。規則關著不蓋、不寫；蓋過就不再動；季收了不寫。sync 與 advance 都叫（補算完賽季、記下加入那一刻之後）。"""
        p = self.state.player
        if p.week_unlocked_at is not None or self.state.world.ended or not week_unlock.unlocked_now(self.state, self.content):
            return
        p.week_unlocked_at = self.state.world.time
        names = self.week_unlock_names()
        if names:
            self._write(week_unlock.TITLE, [week_unlock.journal_line(names, self.content, self.state.world)])

    def mark_seen(self, now: float) -> None:
        """這是那個人自己的請求（伺服器的 act／act_look、假人程式自己那一輪寫 seen_real 另見 bot_runner）：記他自己上線的現實時間
        （PlayerState.seen_real，「這一季上線過」與隱沒看它，玉璽碎片設計 5.3），這一份 Game 之後推奪璽單挑時才記 last_seen。
        Game.sync 不寫，所以管理者的 _admin_target、_kin、_load_kin、peer_act 建的 Game 都碰不到它。"""
        self.state.player.seen_real = now
        self.own_request = True
        self.own_turn_checks()

    def own_turn_checks(self) -> None:
        """本人這一輪（mark_seen；假人程式自己那一輪也叫）：系統通緝這一週還沒掛就掛（bounties.post_auto，名聲 4.6、5.4），被掛的那幾句
        寫進一則「懸賞」紀錄。結伴同行的人、管理者查玩家、玩家卡動到別人建的 Game 都不叫、不掛。
        商城的封測元寶也在這裡發（_mall_grant）：錢包第一次進來的那一下，真人假人一樣；暫停中照發（帳跟世界無關）。"""
        self.own_turn = True
        self._mall_grant()
        if self.world.paused_at() is not None:  # 賽季時鐘暫停中世界不變（線上架構 8.3）：mark_seen 在 server.act 的暫停擋之前
            return
        posted = bounties.post_auto(self.state, self.content)
        if posted:
            self._write(bounties.BOARD, posted)
            self._save_season()

    def _copy_heirloom(self) -> None:
        """抄本照全服登記重抄（玉璽碎片設計 7.4）：只讀 world 那一列，不讀季。sync 與 _drop_stale_references 都叫，所以 _kin 也重抄。
        碎片關著（測試內容、主機關了開關）不讀資料庫：每次建 Game 都會走到這裡。"""
        reg = self.world.seal_state().registry if seal.on(self.content) else None
        seal.copy_heirloom(self.state, self.content, reg)

    def _talk_cap(self) -> int:
        """跟每位人物每個遊戲日能談的輪數：talk_turns_per_day ＋ 玄紐（玉璽碎片設計 7.1）。"""
        return self.content.config.talk_turns_per_day + round(treasures.amount(self.state, self.content, "talk_turns"))

    def _advance_player_local(self, seconds: float) -> list[str]:
        """玩家自己的部分：體力／氣血回復、閉關出關、新立門戶福緣——
        這些是「我」的進度，不是共用賽季的一部分，照自己經過的時間算，不受共用賽季時鐘怎麼走影響。"""
        cfg, p, w = self.content.config, self.state.player, self.state.world
        regen = seconds / cfg.stamina_regen_seconds
        if roster.newbie(self.state, self.content, cfg.newbie_stamina_days):
            regen *= cfg.newbie_stamina_multiplier  # 新手期體力回復加快（體力平衡提案第〇節）
        regen *= treasures.amount(self.state, self.content, "stamina_regen")  # 承露（玉璽碎片設計 7.1）：跟新手期疊乘
        if (dew := seal_acts.dew_factor(self.state, self.content, seconds)) != 1.0:  # 承露降在這一區（改版第 2 批，PM 五之一 4）
            regen *= dew
        p.stamina = min(cfg.stamina_max, p.stamina + regen)
        rate = seconds / (cfg.neili_regen_hours * HOUR)
        if p.busy_until is not None:
            rate *= 2
        if cfg.newbie_hp_double and roster.newbie(self.state, self.content):  # 第一季從自己加入那天起算（roster.since_join），beta 照舊從季初
            rate *= 2
        season = self.state.world  # 減法季每點加倍：氣血上限照這一季（team.neili_cap 的 season）
        team.regen_neili(self.content, p.member, rate, team.con_of(self.state, self.content, self.world, PLAYER), season=season)
        for cid in p.team:
            con = team.con_of(self.state, self.content, self.world, cid)  # 同伴回到他自己的上限（人物資質設計 14.3）
            self.world.update_companion(cid, lambda progress, con=con: team.regen_neili(self.content, progress, rate, con, season=season))
        msgs: list[str] = []
        if p.busy_until is not None and w.time >= p.busy_until:
            msgs += self._finish_seclusion(p.busy_until)
        if roster.fortune_overdue(self.state, self.content):
            msgs += self._deliver_fortune()
        return msgs

    # ── 選項 ──────────────────────────────────────────────

    def options(self, odds: bool = True, tick: bool = True) -> list[Option]:
        """tick 照 _battle_status 的規則往下傳：預設 True，這個呼叫順便把全服戰鬥追趕到現實時間；
        只想讀選單、不該推進戰鬥的呼叫端（dialogue_request）傳 False——一次請求只能推進一次。"""
        if tick:
            self._seal_tick()  # 奪璽單挑跟決戰一樣：誰輪詢誰推（5.4）
        battle_status = self._battle_for_me(tick=tick)
        if self.world.paused_at() is not None:  # 賽季時鐘暫停（線上架構 8.3「擋住所有動作」）：選單只剩一顆灰的
            return [Option(id="season:paused", label=PAUSED_TEXT, enabled=False)]
        if battle_status is not None and not self._watching_battle(*battle_status):
            battle, definition = battle_status
            if not self._fighting(battle, definition):
                # 集結那段時間照常遊玩，加入的按鈕（已經加入就是灰的「已加入」）放在平常的選單前面
                # （企劃者 2026-10-03 決定，FB-009）；走出決戰的大區就照 _watching_battle 算不在場。
                # 開打了還沒投效的散人也一樣：投效的按鈕接在平常的選單前面，不把散人鎖在戰場上（這場仗本來不是他的）
                return self._seal_options() + self._battle_menu(battle, definition) + self._everyday_options(odds)
            battle_menu = self._battle_menu(battle, definition)
            if self.state.player.pending_defect:  # 同理：開著的叛投確認畫面不能因為開打就卡到整場打完（最終審查 Minor 1）
                battle_menu.append(Option(id="defect:cancel", label="再想想"))
            return battle_menu
        return self._seal_options() + self._everyday_options(odds)

    def _everyday_options(self, odds: bool) -> list[Option]:
        """平常的選單（沒有要親身參與、已經開打的決戰時；集結時接在加入的按鈕後面）：籌備或休季、事件、對話、
        投靠確認、求見名單、閉關、在路上，都不是就是在地點上能做的事。"""
        s, c = self.state, self.content
        if self._preparing():
            return [Option(id="season:preparing", label=PREPARING_TEXT, enabled=False)]
        if s.world.ended:  # 休季：列傳為終點開著、手上有列傳的票時多幾顆用票的鈕（減法季批 7b；關著、沒票一顆不多）
            return [Option(id="season:resting", label="休季中，等待管理者開啟下一季", enabled=False)] + self._zhuan_options()
        if s.pending_event:
            event = c.events[s.pending_event]
            opts = []
            for i, ch in visible_choices(event, s, c):
                opt = Option(
                    id=f"choice:{i}", label=self._choice_label(ch, odds),
                    wait=BIG_FIGHT_WAIT if ch.combat and self.is_big(c.squads[ch.combat]) else "",
                )
                if ch.needs is not None:  # 名聲 5.3：俠寇選項——開關關著不出現；稱號不夠灰掉寫要什麼；按得下去照樣標俠寇（5B）
                    if not renown.on(c, "virtue_choices"):
                        continue
                    ok = renown.meets(s, c, ch.needs.path, ch.needs.tier)
                    opt.enabled, opt.tag = ok, ch.needs.path
                    opt.note = "" if ok else renown.needs_line(s, ch.needs.path, ch.needs.tier)
                opts.append(opt)
            free = self._free_text_of(event)
            if free is not None:
                branches = self._branches(event)
                opts.append(Option(
                    id=FREE_TEXT_OPTION, label=free.prompt + free_text_note(free, c, branching=bool(branches)),
                    outcomes=outcome_rules.tags(branches) if branches else None,
                ))
            return opts
        if s.player.duel is not None:  # 單人頭目戰：三招與抽身；放手一搏走輸入框（duel_free_text_prompt），選單上沒有
            held = tactics.locks(s.player.duel.bout).no_moves  # 本命戰法：卸勁出不了強攻、只攻不守出不了固守
            return [Option(id=f"duel:{move}", label=duel_rules.move_label(move) + (tactics.lock_note(move) if move in held else ""),
                           enabled=move not in held) for move in MOVES] + [
                Option(id=DUEL_FLEE, label="抽身退走（不分勝負，掉的氣血不回）"),
            ]
        taken = features_core.menu(self)  # 功能包此刻接管整個選單（坐在宴席上的敬酒詞與離席；開發規範手冊 3.3）
        if taken is not None:
            return taken
        if s.player.arena is not None:  # 擂台（tianxia/arena.py）：三招與認輸；放手一搏同頭目戰走輸入框
            held = tactics.locks(s.player.arena.bout).no_moves
            return [Option(id=f"arena:{move}", label=duel_rules.move_label(move) + (tactics.lock_note(move) if move in held else ""),
                           enabled=move not in held) for move in MOVES] + [
                Option(id=ARENA_YIELD, label=arena.YIELD),
            ]
        if s.player.sensing is not None:  # 有所感（悟意境設計第零節）：卡上的做法，或感悟狀態的「畫下來／順其自然」
            menu = sensing.menu(s, c)
            if menu:
                return [Option(id=option_id, label=label) for option_id, label in menu]
        if s.player.god_naming is not None:  # 特殊頓悟心魔過了：先取名（三個候選＋自己寫），取了才收進意境
            return [Option(id=option_id, label=label) for option_id, label in epiphany.menu(s)]
        if s.player.story_open is not None:  # 一條線的答題（storyline.quiz_menu）：只有這一題的答案與「先擱著」
            menu = storyline.quiz_menu(s, c)
            if menu:
                return [Option(id=option_id, label=label) for option_id, label in menu]
        if s.player.pending_companion:
            dialogue_options, _ = companion_agent.offered(s, s.player.pending_companion)
            talk_cost = c.config.talk_stamina
            opts = [self._cost_option(f"talk:{i}", text, talk_cost) for i, text in enumerate(dialogue_options)]
            if dialogue_options:  # 模型寫的選項之外，自己打一句話（企劃者 2026-10-08）：價錢、輪數跟按選項一樣
                opts.append(self._cost_option(SAY_OPTION, "自己說…", talk_cost))
            opts += foreshadow.talk_options(s, c, s.player.pending_companion)  # 伏筆的片段：固定文字、不花體力（計畫 T7）
            opts += opportunities.talk_options(s, c, s.player.pending_companion)  # 機緣的話題（正式版乙一）：不花體力
            opts += self._parley_options(s.player.pending_companion)  # NPC 智能 2.0：他開的條件、欠你的那一件（不花體力）
            opts.append(Option(id="talk:leave", label="告辭"))
            return opts
        if allied.needs_ally(s, c):  # 拜入要依附的門派之後還沒挑一邊（豪強分屬兩軍）：只剩選邊
            return self._ally_options(cancel=False)
        if s.player.pending_faction:
            faction = self.content.scenario.faction(s.player.pending_faction)
            if allied.on(c, s.world) and faction.allies and s.player.pending_ally is None:  # 投靠豪強：先挑依附哪一軍
                return self._ally_options(cancel=True)
            return [
                Option(id="faction:confirm", label=f"確定投靠{allied.label(c, faction.id, s.player.pending_ally)}"),
                Option(id="faction:cancel", label="再想想"),
            ]
        if s.player.pending_defect:
            target = self.content.scenario.faction(s.player.pending_defect)
            return [  # 「確定叛投X」；豪強分屬兩軍時也可能是「確定改投X」「確定改依附X」（defection.slot_label）
                Option(id="defect:confirm", label=f"確定{defection.slot_label(s, c, target, s.player.pending_ally)}"),
                Option(id="defect:cancel", label="再想想"),
            ]
        if s.player.picking_audience:
            return self._audience_options()
        if s.player.picking_bounty:
            return self._bounty_options()
        if s.player.picking_smith:
            return self._smith_options()
        if s.player.picking_market:
            return self._market_options()
        if s.player.picking_donate:
            return self._donate_options()  # 大本營的捐軍備（素材與經濟設計第六節）
        if s.player.picking_dadian:
            return self._silver_options() + [Option(id="dadian:back", label=silver.SHOP_BACK)]  # 打點（銀兩出口）：這裡做得了的幾樣與離開
        if s.player.picking_arena:
            return self._arena_options()
        if s.player.picking_tavern:
            return self._tavern_options()  # 酒肆（企劃者 2026-10-18）
        if s.player.fs_asking is not None:
            return foreshadow.asking_options(s, c)  # 伏筆的最後一步正在答題：只有答案與「作罷」
        if s.player.busy_until is not None:
            return [Option(id="act:break", label="提前出關")] + self._arena_entry()  # 閉關中也能上擂台（PM 轉述 Joy 2026-10-14）
        j = s.player.journey
        if j is not None:
            end = c.locations[j.path[j.last]].name
            opts = [Option(id="act:on_road", label=f"（在路上，{self.stamp(j.arrive_at[j.last])} 抵達{end}）", enabled=False)]
            if s.player.tagalong is not None:  # 跟著人結伴同行：路線由帶頭的人定，自己只能分道揚鑣（玩家互動第二層）
                opts.append(Option(id="act:part", label=f"分道揚鑣（不再跟著{s.player.tagalong.leader}，之後自己走）"))
                return opts + self._road_task_options(j) + self._arena_entry()
            opts.append(self._back_option())  # 折返（路上設計 3.2）；改去別處在大地圖上安排
            road = self._parley_road_option(j)
            if road is not None:  # NPC 智能 2.1：他帶你走的這一趟，每到一站跟他說一句
                opts.append(road)
            if j.stop_at is None and j.reached < j.last:
                opts.append(Option(id="act:halt", label=f"喊停（到{c.locations[j.path[j.reached]].name}就停下）"))
            return opts + self._road_task_options(j) + self._arena_entry()  # 路上也能上擂台
        loc = c.locations[s.player.location]
        cost = self._action_costs()
        outing = self._outing_on()  # 減法季探索一顆（整合設計 4.1）：只剩一顆「探索」，不畫三選一、尋敵、操練
        modes = [] if outing else self._explore_mode_options(loc, cost["explore"], odds)
        if outing:
            opts = [self._outing_option(loc)]
        elif modes:  # 探索三選一：「探索」只是展開三顆的入口、按了不花體力，鈕上不寫體力（三顆各自寫）；三顆都按不下去時入口也灰（PM 2026-10-14）
            opts = [Option(id="act:explore", label="探索", enabled=any(o.enabled for o in modes)), *modes]
        else:
            opts = [self._cost_option("act:explore", "探索", cost["explore"])]
        if training.on(c, s.world) and not prologue_rules.active(s, c) and not outing:  # 新手引導重做：城裡操練、城外練功，行動列自成一格
            opts.append(self._training_option(loc, cost["explore"], odds))
        if prologue_rules.active(s, c) or not sortie.on(c):
            if self._train_squad_ids(loc):
                # 遊歷：這個地點的敵人，必定開打（見 _train）。sanguo-companions 合併時這個行動被
                # 整個拿掉，於是 Location.enemies／action_cost["train"]／train_event_chance 三個設定
                # 一起變成死的，而遭遇戰只剩劇情事件的 combat 選項——實測整季只打 3 場。
                #
                # 標籤要顯示勝算（跟劇情戰的選項同一套慣例，見 _choice_label）：實機試玩發現
                # 新角色沒有武學時威力是 0，在任何地點遊歷都**必敗**，而落敗現在真的要付氣血與
                # 內傷的代價——不顯示勝算的話，玩家會在開局連輸三場、氣血見底才知道自己不該打。
                # 序章的雪恥照舊是遊歷那一套（不看出陣開關、不算次數），出陣開著時鈕上寫「雪恥」（出陣探索與地盤）
                name = sortie.PROLOGUE_FIGHT if sortie.on(c) else "遊歷"
                opts.append(self._train_option(loc, cost["train"], odds, name=name))
        else:
            option = self._sortie_option(loc, cost["train"], odds)  # 出陣（出陣探索與地盤設計第二節）：散人、不在戰線上的地點沒有
            if option is not None:
                opts.append(option)
            elif sortie.ranger_here(c, self._side(), loc.id, s.world):  # 散人站在戰線上：灰的一顆寫真正的原因（FB-250）
                opts.append(Option(id="act:train", label=f"{sortie.NAME}（{sortie.RANGER_NOTE}）", enabled=False))
            elif sortie.out_of_contest(c, s.world, self._side(), loc.id):  # 領地爭奪：別人的大本營、廣宗不給攻（裁決 18）
                opts.append(Option(id="act:train", label=f"{sortie.NAME}（{sortie.OUT_NOTE}）", enabled=False))
        opts += self._challenge_options(odds)  # 挑戰本人（T4；每季都有，figures.challenge_on）：有陣營、這裡站著敵方的大勢人物時才有
        if ranks.summons_event(s, c) is not None:
            # 晉升奇遇（計畫 T5）：人在召見的地點才有，不花體力。一類一顆開著時網頁畫成行動列上面一條金框橫幅（設計 9.1 第 1 組乙），
            # 鈕上寫它自己的名字與一行小字
            opts.append(Option(id="act:summons", label=SUMMONS_LABEL if precise.on(c, s.world) else "應召"))
        # 一條線（特殊事件）：此刻在這裡做得了的那一段一顆，不花體力（同應召）
        opts += [Option(id=option_id, label=label, enabled=ok) for option_id, label, ok in storyline.options(s, c)]
        people = self._figures_here()
        if precise.on(c, s.world):  # 一類一顆（正式季整合 2.8）：交友只談話、求見併進交友；拜入門派另成一顆（2.7）
            opts += self._sect_options() + [self._precise_social_option(cost["socialize"])]
            people = []  # 下面舊的交友、求見都不列
        # 只有一位大勢人物、沒有交友事件、他又見不到（名望不夠、閉門不見、這個遊戲日談滿）、福緣也沒到、也不在召見的地點：
        # 交友只會花 5 點體力換同一句打發，所以不給，這條路只剩不花體力的求見（下面）
        only_the_door = len(people) == 1 and ranks.summons_event(s, c) is None and self.socialize_is_futile()
        if (has_events_here(c, loc, "socialize") or 0 < len(people) < AUDIENCE_HALL_FIGURES) and not only_the_door                 and not precise.on(c, s.world):
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
                opts.append(Option(id=f"call:{cid}", enabled=False, label=f"求見{ch.name}（{self._talked_out_note()}）"))
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
        for cid in self._recruit_targets():  # 歷史武將同行：此地此刻站著、還沒有主的每一位一顆；招不了的灰掉寫原因
            problem = roster.recruit_problem(s, c, self.world, cid)
            name = c.characters[cid].name
            if problem is not None:
                opts.append(Option(id=f"act:recruit:{cid}", label=f"招募【{name}】（{problem}）", enabled=False))
            else:
                chance = roster.recruit_chance(c, s, cid)
                opts.append(self._cost_option(
                    f"act:recruit:{cid}", f"招募【{name}】", c.config.recruit_stamina, note=f"成功率約 {chance * 100:.0f}%",
                ))
        for dest_id in loc.connections:
            if not atlas.is_unlocked(c.locations[dest_id], s, c):  # 世界旗標沒開、序章的草廬（只給站在那裡的人）
                continue
            opts.append(self._move_option(loc.id, dest_id))
        for skill, problem in library.lessons_here(s, c):  # 拜師學藝（武學與成長設計附錄 B）：不花體力
            note = library.lesson_note(skill) if problem is None else problem
            opts.append(Option(id=f"learn:{skill.id}", label=f"學{skill.name}（{note}）", enabled=problem is None))
        if s.player.faction is None:
            for faction in c.scenario.factions:
                if s.player.location in faction.join_at:
                    opts.append(Option(id=f"faction:{faction.id}", label=f"投靠{faction.name}"))
        for target, ally in self._defect_targets():  # 叛投（計畫甲）：別的陣營的投靠點、一季一次、不在沒打完的決戰的參戰名單上
            option_id = f"defect:{target.id}" + (f":{ally}" if ally else "")  # 豪強分屬兩軍：豪強的投靠點每一軍一顆
            opts.append(Option(id=option_id, label=defection.slot_label(s, c, target, ally)))
        opts += self._lean_options()  # 三陣營四勝利：豪強改幫另一軍（隨時換、不算叛投；開關關著沒有）
        opts += self._order_options(loc)  # 軍令（計畫 T6）：守勢行動、接糧車；開關關著、散人沒有
        opts += self._rank2_options(loc)  # 第 2 階行動（正式版乙一）
        opts += self._rank_action_options(loc)  # 第 3、4 階的行動（正式版戊一）
        opts += opportunities.place_options(s, c, loc.id)  # 機緣：交東西、天時地利（正式版乙一）
        opts += foreshadow.final_options(s, c, loc.id)  # 伏筆的最後一步（計畫 T7）：做得了的人在那個地點才有
        opts += self._errand_options()  # 託付（減法季批 6）：人在託付的地點才有那一顆；關著是空的
        opts += self._invite_options()  # 玩家之間的邀請（切磋）：別人發給你的、你發出去還在等的
        shown = bounties.visible(s, c) if bounties.board_here(s, c) else []
        if shown:  # 懸賞榜：城鎮類的地點、有看得到的單才有（FB-121：張數只算看得到的，0 張不畫）；只是打開第二層選單，不花體力
            opts.append(Option(id="act:bounties", label=f"{bounties.BOARD}（{len(shown)} 張）"))
        if equipment.smith_open(s, c):  # 鐵匠鋪（兵器設計 4.1；裝備四欄 4.6：武器或防具開著就開門）：只是打開第二層選單，不花體力
            opts.append(Option(id="act:smith", label=weapons.SMITH))
        if mounts.market_here(s, c):  # 馬市（裝備四欄 5.5，帶「馬市」標籤的城鎮）：只是打開第二層選單，不花體力
            opts.append(Option(id="act:market", label=mounts.MARKET))
        if tavern_rules.on(c) and tavern_rules.here(s, c):  # 酒肆（帶「酒肆」標籤的城鎮）：只是打開酒肆，不花體力
            opts.append(Option(id="act:tavern", label=tavern_rules.TAVERN))
        opts += self._arena_entry()
        opts += self._stamina_play_options()  # 後期體力玩法：設伏劫道、修築工事、屯糧練兵
        heal = self._heal_option()
        if heal is not None:
            opts.append(heal)
        donate = self._donate_option()
        if donate is not None:
            opts.append(donate)
        if self._silver_options():  # 銀兩出口（21 天季，正式季整合 6.5）：五樣收進「打點」那一間店（第 9 批畫面乙），不花體力
            opts.append(Option(id="act:dadian", label=silver.SHOP))
        if prologue_rules.instant_rest(s, c):  # 打坐 2026-10-12 拿掉了（企劃者）；只剩序章教體力那一步的調息，一下回滿
            opts.append(Option(id="act:rest", label=PROLOGUE_REST))
        # 序章裡在草廬閒著時只留這一步要的（新手引導計畫一）；初入江湖時「此地還能做」只留教到的（新手引導第四段）
        return prologue_rules.onboard_allowed(prologue_rules.allowed(opts, s, c), s, c)

    def _heal_option(self) -> Option | None:
        """醫館裡、有內傷時的「醫館療傷」（企劃者 2026-10-12；跟修練頁的療傷鈕同一個動作、同一個價錢）；
        銀兩不夠灰掉寫原因。開關關著（哪裡都能療傷）、不在醫館、沒有內傷都不畫。不花體力。"""
        s, c = self.state, self.content
        member = s.player.member
        if not clinic.on(c) or not clinic.here(s, c) or int(member.injury) < 1:
            return None
        problem = team.heal_problem(s, c, member)
        note = skillview.heal_note(s, c)
        return Option(id="act:heal", label=f"{clinic.HEAL}（{note if problem is None else problem.rstrip('。')}）",
                      enabled=problem is None)

    def _heal_msgs(self) -> list[str]:
        return team.heal(self.state, self.content, self.state.player.member, clinic.problem(self.state, self.content))

    # ── 捐軍備（素材與經濟設計第六節）────────────────────────────

    def _at_own_base(self) -> bool:
        """人在自家陣營的大本營（territory.bases：投靠點，含不在戰線上的），開關（Config.economy.donate）開著、不在路上；散人沒有。
        豪強分屬兩軍的季，豪強自己的投靠點與依附那一軍的投靠點都算（設計第六節）。"""
        s, c = self.state, self.content
        p = s.player
        if not c.config.economy.donate or p.faction is None or p.journey is not None:
            return False
        return territory.bases(c).get(p.location) in {p.faction, self._side()}

    def econ_day(self) -> int:
        """素材與經濟的「一天」（升階的三階、捐軍備的上限）：同回體丹的換日（_pill_day，台灣 00:00）。機器人照它算。"""
        return self._pill_day()

    def can_donate_here(self) -> bool:
        """這一下捐得了軍備嗎（人在自家大本營、閒著或軍需官那一串開著）：Game.donate 收不收的同一個判斷，機器人照它。"""
        return self._at_own_base() and (self._idle() or self.state.player.picking_donate)

    def _donate_option(self) -> Option | None:
        """大本營「此地還能做」裡的「捐軍備（今天還能捐 N 點）」：只是打開軍需官那一串（不花體力）；今天捐滿了灰掉寫什麼時候再來。"""
        if not self._at_own_base():
            return None
        room = economy.donate_room(self.state, self.content, self._pill_day())
        if room <= 0:
            full = economy.DONATE_FULL.format(cap=self.content.config.economy.donate_daily_cap)
            return Option(id="act:donate", label=f"{economy.DONATE_TITLE}（{full}）", enabled=False)
        return Option(id="act:donate", label=f"{economy.DONATE_TITLE}（{economy.DONATE_LEFT.format(n=room)}）")

    def _donate_options(self) -> list[Option]:
        """軍需官那一串（店面關著、整季機器人與假人看的選單）：背包裡每一種素材一顆「捐這一種收得下的全部」（donate:<素材>:<個數>，
        寫份量與進哪一樣軍備；一個都收不下的灰掉寫為什麼），最上面一行灰字寫今天還能捐幾點，最後「離開」。都不花體力。"""
        s, c = self.state, self.content
        day = self._pill_day()
        room = economy.donate_room(s, c, day)
        opts = [Option(id="donate:room", label=economy.DONATE_LEFT.format(n=room), enabled=False)]
        # 一階排最前面（最該捐的）、三階排最後（要留著打神器，免得一按就捐掉）；同階照剛柔快慢
        held_by_tier = sorted(materials.bag_contents(s, c), key=lambda pair: (pair[0].tier, shopview.attribute_rank(pair[0].attribute)))
        for material, held in held_by_tier:
            if economy.donate_points(c, material.id) <= 0:
                continue
            problem = economy.donate_problem(s, c, material.id, day)
            if problem is not None:
                opts.append(Option(id=f"donate:{material.id}:0", enabled=False,
                                   label=economy.DONATE_REFUSED.format(name=material.name, problem=problem)))
                continue
            n = economy.donate_take(s, c, material.id, held, day)
            armament = economy.armament_of(c, material.attribute) or economy.DONATE_MISC
            opts.append(Option(id=f"donate:{material.id}:{n}", label=economy.DONATE_BUTTON.format(
                name=material.name, n=n, points=n * economy.donate_points(c, material.id), armament=armament)))
        return opts + [Option(id="donate:back", label=economy.DONATE_BACK)]

    def _donate_choice(self, arg: str) -> list[str]:
        """軍需官那一串上的選擇：donate:back 收起；donate:<素材>:<個數> 捐（_donate）。選單還開著，可以接著捐。"""
        if arg == "back":
            economy.close_donate(self.state)
            return [economy.DONATE_CLOSED]
        mid, _, count = arg.rpartition(":")
        return self._donate([(mid, int(count) if count.isdecimal() else 0)])

    def donate(self, mid: str, count: int) -> list[str]:
        """捐一種素材 count 個（MAIN_ACTIONS["donate"]；整季機器人與假人也走它）：見 donate_items。"""
        return self.donate_items([(str(mid), int(count))])

    def donate_items(self, items: list[tuple[str, int]]) -> list[str]:
        """捐軍備（MAIN_ACTIONS["donate"]，軍需帳那一頁一次送挑好的幾種）：人在自家大本營、閒著（或軍需官那一串開著）才收。
        捐成了寫一則「捐軍備」紀錄（幾種一起捐也是一則）；一樣都沒收下的什麼都不動、不寫紀錄。"""
        s = self.state
        if not self.can_donate_here():
            return self._log([equipment.NOT_NOW])
        p = s.player
        here = self.content.locations[p.location].name
        before = (p.donate_day, p.donated_today)
        msgs = self._donate([(str(mid), int(count)) for mid, count in items])
        if (p.donate_day, p.donated_today) != before:  # 真的收下了
            journal.add_entry(s, Draft(f"{economy.DONATE_TITLE}・{here}").entry(s.world.time, msgs))
            self._save_season()
        return self._log(msgs)

    def _donate(self, items: list[tuple[str, int]]) -> list[str]:
        """收下（設計第六節）：每一種照 economy.take_donation 扣背包、記今天的點數（上限切一半：收得下的收，其餘留著），照給的先後收；
        軍備存量照份量累積（economy.add_armament）；第一季規則開著時記貢獻（push.add_contribution，照份量）；推大本營那一條線（豪強推割據；
        economy.donate_target）往自己陣營，量是 economy.donate_push（每點 0.05、事件五折），走 push_trend(source="donate")：季長倍數、
        盡頭阻力、每人每日上限照出陣，推力不另記貢獻（幾種一起捐也只推一次，照合起來的點數）。一樣都沒收下回第一個原因、什麼都不動。
        軍需帳上掌櫃那一句照這一下（_shop_after）。"""
        s, c = self.state, self.content
        p, w = s.player, s.world
        day = self._pill_day()
        if not self._at_own_base():
            return [equipment.NOT_NOW]
        took: list[tuple[str, int, int]] = []  # (素材, 收下幾個, 幾點)
        kept: list[str] = []
        refused: list[str] = []
        for mid, count in items:
            problem = economy.donate_problem(s, c, mid, day)
            if problem is not None:
                refused.append(problem)
                continue
            wanted = max(0, min(count, materials.held(s, mid)))
            points = economy.take_donation(s, c, mid, wanted, day)
            if points <= 0:
                refused.append(economy.DONATE_TOO_BIG.format(points=economy.donate_points(c, mid), room=economy.donate_room(s, c, day)))
                continue
            taken = points // economy.donate_points(c, mid)
            took.append((mid, taken, points))
            if taken < wanted:
                kept.append(economy.DONATE_KEPT.format(n=wanted - taken, name=c.materials[mid].name))
        if not took:
            problem = refused[0] if refused else economy.DONATE_NONE
            self._shop_after(problem, "donate")
            return [problem]
        faction = c.scenario.faction(self._side())
        items_text = "、".join(materials.item_text(c, mid, taken) for mid, taken, _ in took)
        msgs = [economy.DONATE_DONE.format(items=items_text, faction=faction.name)]
        by_attribute: dict[str, int] = {}
        for mid, _, points in took:
            attribute = c.materials[mid].attribute
            by_attribute[attribute] = by_attribute.get(attribute, 0) + points
        msgs += self._credit_donation(by_attribute)
        self._shop_after(None, "donate")
        return msgs + kept

    def _credit_donation(self, by_attribute: dict[str, int]) -> list[str]:
        """捐軍備收下之後（捐素材、捐銀兩共用）：軍備存量照份量累積（economy.add_armament）；第一季規則開著時記貢獻（照份量）；
        推大本營那一條線（豪強推割據；economy.donate_target），量是 economy.donate_push，走 push_trend(source="donate")。"""
        s, c = self.state, self.content
        p, w = s.player, s.world
        side = self._side()  # 豪強分屬兩軍：軍備進依附那一軍的存量、推依附那一軍的目標（設計第六、十二節）
        msgs: list[str] = []
        for attribute, points in by_attribute.items():
            armament = economy.armament_of(c, attribute)
            if armament is not None:
                economy.add_armament(w, side, attribute, points)
                msgs.append(f"{armament} +{points}")
        total = sum(by_attribute.values())
        if season_one(c, w):  # 晉升只在第一季的規則下有：規則關著的季只記軍備
            wins.credit(p, c, w, calendar.point(w.time, c, w).week, total)  # 豪強另記此刻幫的那一軍那一本（減法季批 3c）
            msgs.append(f"貢獻 +{total}")
        target = economy.donate_target(c, w, side, p.location)
        if target is not None:
            trend_id, direction = target
            msgs += self.push_trend(trend_id, economy.donate_push(c, total) * direction, source="donate")
        return msgs

    # ── 銀兩出口（21 天季，正式季整合 6.5；tianxia/silver.py）：五樣都放在「此地還能做」，不花體力 ──

    def _silver_options(self) -> list[Option]:
        """銀兩出口的幾顆（silver.on 才有）：自家大本營的捐銀兩、醫館的名師指點與買破境丹、鐵匠鋪的看火候、此地談得上話的大勢人物
        每一位一顆打點門路。做不了的灰掉寫原因。"""
        s, c = self.state, self.content
        if not silver.on(c, s.world):
            return []
        opts: list[Option] = []
        if self._at_own_base():
            day, room = self._pill_day(), economy.donate_room(s, c, self._pill_day())
            problem = silver.donate_problem(s, c, day, room, c.config.economy.donate_daily_cap)
            if problem is None:
                amount = silver.donate_amount(s, c, day, room)
                opts.append(Option(id="act:silver_donate", label=silver.DONATE_LABEL.format(
                    silver=amount, points=amount // c.config.silver_outlets.donate_per_point)))
            else:
                opts.append(Option(id="act:silver_donate", label=silver.DONATE_REFUSED.format(problem=problem), enabled=False))
        if self._at_clinic_town():
            cfg = c.config.silver_outlets
            problem = silver.mentor_problem(s, c, self._pill_day())
            opts.append(Option(id="act:mentor", enabled=problem is None, label=silver.MENTOR_REFUSED.format(problem=problem)
                               if problem else silver.MENTOR_LABEL.format(silver=cfg.mentor_silver, bonus=cfg.mentor_bonus)))
            problem, pill = silver.legend_problem(s, c), c.config.legend_item_name
            opts.append(Option(id="act:buy_legend", enabled=problem is None, label=silver.LEGEND_REFUSED.format(name=pill, problem=problem)
                               if problem else silver.LEGEND_LABEL.format(name=pill, silver=cfg.legend_silver, left=silver.legend_left(s, c))))
        for fid in self._bribe_targets():
            name, problem = c.figures[fid].name, silver.bribe_problem(s, c, fid, self._pill_day())
            opts.append(Option(id=f"act:bribe:{fid}", enabled=problem is None, label=silver.BRIBE_REFUSED.format(name=name, problem=problem)
                               if problem else silver.BRIBE_LABEL.format(name=name, silver=c.config.silver_outlets.bribe_silver,
                                                                         gain=silver.bribe_gain(s, c, fid))))
        if equipment.smith_open(s, c):
            problem = silver.furnace_problem(s, c, self._pill_day(), prologue_rules.active(s, c))
            opts.append(Option(id="act:furnace", enabled=problem is None, label=silver.FURNACE_REFUSED.format(problem=problem)
                               if problem else silver.FURNACE_LABEL.format(silver=c.config.silver_outlets.furnace_silver)))
        return opts

    def _bribe_targets(self) -> list[str]:
        """此地打點得了門路的大勢人物（6.5）：在場、談得上話（有對話人物）；不在路上。"""
        s, c = self.state, self.content
        if s.player.journey is not None:
            return []
        return [fid for fid in figures.present_at(s, c, s.player.location) if c.figures[fid].character is not None]

    def _silver_act(self, what: str) -> list[str]:
        """銀兩出口的五樣（act:silver_donate、mentor、furnace、buy_legend、bribe:<人物>）。"""
        if what == "silver_donate":
            return self._silver_donate()
        if what == "mentor":
            return self._silver_mentor()
        if what == "furnace":
            return self._silver_furnace()
        if what.startswith("bribe:"):
            return self._silver_bribe(what.partition(":")[2])
        if not (silver.on(self.content, self.state.world) and self._at_clinic_town()):
            return [equipment.NOT_NOW]
        return silver.buy_legend(self.state, self.content)

    def _close_dadian(self) -> None:
        """收起「打點」那一間店與掮客那一句（同 economy.close_donate）。"""
        p = self.state.player
        p.picking_dadian = False
        p.shop_line, p.shop_clue, p.shop_hold = "", "", ""

    def _silver_bribe(self, fid: str) -> list[str]:
        s, c = self.state, self.content
        if not (silver.on(c, s.world) and fid in self._bribe_targets()):
            return [equipment.NOT_NOW]
        return silver.bribe(s, c, fid, self._pill_day())

    def _silver_furnace(self) -> list[str]:
        s, c = self.state, self.content
        if not (silver.on(c, s.world) and equipment.smith_open(s, c)):
            return [equipment.NOT_NOW]
        return silver.furnace(s, c, self._pill_day(), prologue_rules.active(s, c))

    def _at_clinic_town(self) -> bool:
        """名師指點、買破境丹的地方（6.5）：帶醫館標籤的地點、不在路上（看標籤，不看 Config.heal_at_clinic：那個開關關著時哪裡都能療傷）。"""
        p = self.state.player
        return p.journey is None and clinic.CLINIC_TAG in (self.content.locations[p.location].tags or [])

    def _silver_mentor(self) -> list[str]:
        s, c = self.state, self.content
        if not (silver.on(c, s.world) and self._at_clinic_town()):
            return [equipment.NOT_NOW]
        return silver.mentor(s, c, self._pill_day())

    def _silver_donate(self) -> list[str]:
        """捐銀兩進軍需帳（6.5）：每 donate_per_point 兩記 1 點、捐成糧秣（慢），跟捐素材共用每天的點數上限；寫一則「捐銀兩」紀錄。"""
        s, c = self.state, self.content
        if not (silver.on(c, s.world) and self._at_own_base()):
            return [equipment.NOT_NOW]
        day = self._pill_day()
        room = economy.donate_room(s, c, day)
        problem = silver.donate_problem(s, c, day, room, c.config.economy.donate_daily_cap)
        if problem is not None:
            return [f"（{problem}。）"]
        amount, points = silver.take_donation(s, c, day, room)
        faction = c.scenario.faction(self._side())
        msgs = [silver.DONATE_DONE.format(silver=amount, faction=faction.name), f"銀兩 -{amount}"]
        msgs += self._credit_donation({materials.GRAIN_ATTRIBUTE: points})
        self._save_season()
        return msgs

    def armament_view(self) -> dict | None:
        """江湖頁的陣營軍備存量（設計第六節第 3 點；status_data["armament"]）：投靠了陣營、捐軍備開著才有。
        {"faction": 陣營名, "stock": [{"name": 糧秣, "attribute": 慢, "points": n}, …]}，照 Config.economy.armaments 的順序（沒捐過的是 0）。
        在決戰怎麼起作用還沒定（第 2 塊），這裡只給存量。"""
        s, c = self.state, self.content
        p = s.player
        if not c.config.economy.donate or p.faction is None:
            return None
        side = self._side()  # 豪強分屬兩軍：看依附那一軍的存量
        stock = s.world.armaments.get(side, {})
        return {
            "faction": c.scenario.faction_name(side, side),
            "stock": [{"name": name, "attribute": attribute, "points": stock.get(attribute, 0)}
                      for attribute, name in c.config.economy.armaments.items()],
        }

    def _move_option(self, here: str, dest_id: str) -> Option:
        """選單上的「前往 相鄰地點」，照主畫面選的走法（move_mode）：標籤寫這種走法的時間與體力，體力不夠就按不下去、
        寫明原因（跟大地圖的「安排前往」按鈕同一個說法）。步行的 id 維持 move:<地點>（機器人、假人與舊的呼叫端
        只認這個）；趕路、疾行是 move:<地點>:<走法>，所以 choose() 照樣只認選單上真的有的 id。
        時間與體力走 atlas.route_text／route_stamina，跟 _move 出發時 _depart 實際扣的是同一條路（騎著馬照腳力省、步調照坐騎，
        裝備四欄 5.3；閒著時不在路上，不會是剛出發就折返）。"""
        c, mode = self.content, self.move_mode
        dest = c.locations[dest_id]
        route = atlas.Route((dest_id,), (atlas.leg_minutes(c, here, dest_id),))
        option_id = f"move:{dest_id}" if mode == "walk" else f"move:{dest_id}:{mode}"
        if self.state.player.ambush is not None:  # 守著埋伏不能移動（設伏劫道：沒有分身）
            return Option(id=option_id, label=f"前往 {dest.name}（{ambush_rules.MOVE_BLOCKED}）", enabled=False)
        cost = atlas.route_stamina(self.state, c, route, mode)
        if self.state.player.stamina < cost:
            return Option(id=option_id, label=f"前往 {dest.name}（{atlas.MODES[mode]}・體力不足，要 {cost}）", enabled=False)
        # 尋敵分級不寫在移動清單上（Joy 2026-10-22）：兇險程度只在輿圖的地點詳情寫一句（place_detail）
        return Option(id=option_id, label=f"前往 {dest.name}（{atlas.route_text(self.state, c, route, mode)}）")

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
        """路上小事（路上設計第四節）：步行、趕路時每樣一顆（四樣；全圖開放時沒有留意地形，三樣），不花體力；這一段路做過的灰掉、寫「這段路已經……」。
        疾行一站一站立刻抵達，沒有。這個遊戲日的收穫拿滿了（每天上限，遊戲日跟著季長縮）的邊走邊想、路邊採集照樣按得下去，
        補充改寫「收穫拿滿了」（待 joy 潤）。鈕上不寫換日的那一刻：375 px 上 2×2 格子一格的小字只有約 143 px，時刻本身就約 118 px，
        再加字就折成兩行、整個格子變高（day-scale 審查 M1）；時刻寫在按下去的那一句（_road_think、_road_gather）。"""
        if j.mode == "dash":
            return []
        hints = {
            "think": f"心得 +{self.content.config.road_think_xinde}",
            "ask": "聽一則這一帶的傳聞",
            "gather": "有機會撿到素材",
        }
        if not self._road_reward_due("task"):
            for what in ROAD_REWARD_TASKS:
                hints[what] = "收穫拿滿了"  # 不留「心得 +3」：拿滿了就沒有
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
        """這個地點目前能嘗試招募的人（自由之身、recruit_at 是這裡、情誼到門檻 roster.affinity_ok）；沒有就是 None。"""
        s, c = self.state, self.content
        for cid, ch in c.characters.items():
            if (ch.kind == "recruitable" and ch.recruit_at == s.player.location and roster.owned_by(self.world, cid) is None
                    and roster.affinity_ok(s, c, cid)):
                return cid
        return None

    def _recruit_targets(self) -> list[str]:
        """歷史武將同行（Config.companions）：此地此刻站著（_figures_here，照人物此刻的所在）、標了 recruitable、還沒有主、
        情誼到門檻（roster.affinity_ok，沒到的不畫鈕）的人。關著是空的（舊的 recruit_at 那一條照舊走 _recruit_target）。"""
        if not roster.on(self.content):
            return []
        return [
            cid for cid in self._figures_here()
            if self.content.characters[cid].recruitable and roster.owned_by(self.world, cid) is None
            and roster.affinity_ok(self.state, self.content, cid)
        ]

    def _recruitable_here(self) -> bool:
        """此地有人招得了你（_recruit_targets 裡陣營對、名下沒滿的）：h_recruit 照它說，灰掉的鈕不算（黃巾的人在涿郡不說）。"""
        s, c = self.state, self.content
        return any(roster.recruit_problem(s, c, self.world, cid) is None for cid in self._recruit_targets())

    def _cost_option(self, option_id: str, label: str, cost: int, note: str = "") -> Option:
        extra = f"・{note}" if note else ""
        return Option(
            id=option_id, label=f"{label}（體力 {cost}{extra}）", enabled=self.state.player.stamina >= cost
        )

    def _explore_mode_options(self, loc: Location, cost: int, odds: bool = False) -> list[Option]:
        """探索三選一的三顆（出陣探索與地盤設計第三節）：一樣的體力。悟不出的地方（insights.explore_gives 是空的）靜心感悟灰掉、
        寫「這裡悟不出什麼」；這個遊戲日在這裡選錯過做法也灰掉（sensing.missed_today）。開關關著、序章裡沒有（序章照舊按「探索」）。
        一類一顆開著（precise.on）時多一顆練功（_practice_option，正式季整合 2.5）。"""
        c = self.content
        if not explore_modes.on(c) or prologue_rules.active(self.state, c):
            return []
        name = explore_modes.NAMES
        opts = [self._cost_option(explore_modes.option_id(m), name[m], cost) for m in (explore_modes.GATHER, explore_modes.SEEK)]
        if precise.on(c, self.state.world):
            opts[1] = self._seek_option(cost)
        sense = explore_modes.option_id(explore_modes.SENSE)
        if not insights.explore_gives(loc, c):
            opts.append(Option(id=sense, label=f"{name[explore_modes.SENSE]}（{explore_modes.NO_SENSE}）", enabled=False))
        elif sensing.missed_today(self.state, c, loc):
            opts.append(Option(id=sense, label=f"{name[explore_modes.SENSE]}（{explore_modes.SENSE_LATER}）", enabled=False))
        else:
            opts.append(self._cost_option(sense, name[explore_modes.SENSE], cost))
        if precise.on(c, self.state.world) and not training.on(c, self.state.world):
            opts.append(self._practice_option(loc, cost, odds))  # 城裡操練開著時練功自成一格（_training_option），不在三選一裡
        branches = self._gather_branch_options(loc, cost)
        if branches:  # 找素材分支（第 32 項）：「找素材」變成入口（不寫體力、按了只回 GATHER_PICK），分支緊接在它後面
            opts[0] = Option(id=opts[0].id, label=name[explore_modes.GATHER], enabled=any(o.enabled for o in branches))
            opts[1:1] = branches
        return opts

    def _gather_branch_options(self, loc: Location, cost: int) -> list[Option]:
        """找素材分支的鈕（第 32 項）：這裡兩條以上才有（explore_modes.layered），每條「挖礦（體力 6・剛、慢）」，最後一顆「自己說…」
        （Config.gather_branches.say_enabled 關著不畫）。沒有分支層是空的，「找素材」照舊直接做。"""
        c = self.content
        here = explore_modes.layered(c, self.state.world, loc)
        if not here:
            return []
        opts = [
            self._cost_option(explore_modes.branch_option(b.id), b.name, cost, note="、".join(explore_modes.branch_attributes(c, loc, b)))
            for b in here
        ]
        if c.config.gather_branches.say_enabled:
            opts.append(self._cost_option(explore_modes.SAY_ID, explore_modes.SAY_LABEL, cost, note=explore_modes.SAY_NOTE))
        return opts

    def _seek_option(self, cost: int) -> Option:
        """一類一顆的找事件（正式季整合 2.7）：一次性奇遇與這裡可重複的事件都沒有時灰掉、寫「這一帶眼下沒什麼事」，不扣體力。
        鈕上不寫給什麼（企劃者 2026-10-19 推翻 2.11：「不需要寫，這本來就是探索的一部分」，設計 9.1）。"""
        s, c = self.state, self.content
        oid, name = explore_modes.option_id(explore_modes.SEEK), explore_modes.NAMES[explore_modes.SEEK]
        if not event_candidates(s, c, "explore", "rare") and not event_candidates(s, c, "explore", "common"):
            return Option(id=oid, label=f"{name}（{explore_modes.SEEK_EMPTY}）", enabled=False)
        return self._cost_option(oid, name, cost)

    def _practice_option(self, loc: Location, cost: int, odds: bool) -> Option:
        """練功的鈕（正式季整合 2.5）：「練功（體力 6・對手・勝算）」（不寫經驗：企劃者 2026-10-19 推翻 2.11，設計 9.1）；這裡只有頭目時寫頭目那一面、直接對上；
        頭目冷卻中灰掉寫還要等多久、次數用完灰掉寫他這一週（季）不再現身；都沒有灰掉寫最近的對手在哪。"""
        s, c = self.state, self.content
        oid, name = explore_modes.option_id(explore_modes.PRACTICE), explore_modes.NAMES[explore_modes.PRACTICE]
        foe = self._gather_foe(loc)
        if foe is not None:
            note = f"{foe.name}・{self.odds(foe.id)}" if odds else foe.name
            tier = self._practice_tier(loc)
            if tier is not None:  # 城外尋敵分級（Config.training）：「尋敵（體力 6・宵小出沒・河灘潑皮・穩勝）」
                note = f"{training.TIER_WORDS[tier]}・{note}"
            return self._cost_option(oid, name, cost, note=note)
        bosses = duel_rules.here(s, c)
        if not bosses:
            route = self._nearest_practice()
            place = explore_modes.NO_FOE_NEAR.format(place=c.locations[route.path[-1]].name) if route is not None else ""
            # note：行動列練功那一格的小字（FB-670，PM 2026-10-22）：城鎮「城外才有」、城外沒有對手的地方「這裡沒有」——網頁照它寫，不自己判斷
            cell = explore_modes.NO_FOE_CELL_TOWN if explore_modes.is_town(c, loc) else explore_modes.NO_FOE_CELL
            return Option(id=oid, label=f"{name}（{explore_modes.NO_FOE}{place}）", enabled=False, note=cell)
        boss = duel_rules.available(s, c)
        if boss is not None:
            return self._cost_option(oid, name, cost, note=f"{self._boss_face(boss)}・{explore_modes.BOSS_NOTE}")
        return Option(id=oid, label=f"{name}（{self._boss_away()}）", enabled=False)

    def _boss_face(self, boss: DuelBoss) -> str:
        """這一隻頭目對你露的那一面（照你的陣營，duel_rules.foe_index）的名字：練功鈕與行動列底下那一行同一個。"""
        return boss.foes[duel_rules.foe_index(boss, self.state.player.faction)].name

    def _boss_away(self) -> str:
        """這裡只有頭目、他此刻遇不上的原因（練功鈕括號裡與行動列底下那一行同一句）：冷卻中寫還要等多久，次數用完寫哪一位頭目不再現身
        （FB-672：帶名字，名字跟「這裡只有頭目某某」同一個，_boss_face；這裡不只一位時寫次數用完的第一位）。"""
        s, c = self.state, self.content
        wait = duel_rules.cooldown_left(s, c.config.duel)
        if wait > 0:
            return explore_modes.BOSS_COOLING.format(wait=arena.wait_text(wait / c.config.time_scale))
        bosses = duel_rules.here(s, c)
        gone = next((b for b in bosses if duel_rules.used_up(s, c, b.id)), bosses[0])
        return explore_modes.boss_gone(s, c, self._boss_face(gone))  # 7 天濃縮季寫「這一段…第 N 天 00:00 再來」（FB-501）

    def _practice_line(self, loc: Location) -> str:
        """行動列底下練功那一行（FB-670，企劃者 2026-10-22 選練功入口「丙」：練功在行動列自己一格）。跟練功鈕（_practice_option）
        同一個判斷、同一個次序：有對手寫打誰；這裡只有頭目、遇得上寫頭目；頭目不在寫鈕上同一句；都沒有寫最近的在哪、步行多久
        （_nearest_practice；時間走 atlas.route_text 的步行，跟移動那張卡的「前往」同一個算法）——城鎮開頭寫「城外才有對手」，
        城外沒有對手的地方（自家的大營、山洞）照鈕上那一句。句子在 howto。只讀，不擲骰。"""
        s, c = self.state, self.content
        foe = self._gather_foe(loc)
        if foe is not None:
            return howto.PRACTICE_NOTE.format(foe=foe.name)
        if not duel_rules.here(s, c):
            head = howto.PRACTICE_TOWN_NOTE if explore_modes.is_town(c, loc) else explore_modes.NO_FOE
            route = self._nearest_practice()
            if route is None:
                return head
            place = explore_modes.NO_FOE_NEAR.format(place=c.locations[route.path[-1]].name)
            return f"{head}{place}（{atlas.route_text(s, c, route, 'walk')}）"
        boss = duel_rules.available(s, c)
        if boss is not None:
            return howto.PRACTICE_BOSS_NOTE.format(foe=self._boss_face(boss))
        return self._boss_away()

    def _nearest_practice(self) -> atlas.Route | None:
        """離這裡最近、練得到的地點（有不是自己人的隊伍或此刻遇得上的頭目）：先照摸清的路找，都走不到照所有開放的地點找（同 clinic.nearest）。"""
        s, c = self.state, self.content
        bosses = {loc for b in c.duels.values() for loc in b.locations}
        targets = {loc.id for loc in c.locations.values() if self._wild_foes(loc) or loc.id in bosses}
        targets.discard(s.player.location)
        for found in (atlas.routes(s, c), atlas.shortest_routes(s, c)):
            reachable = [route for loc_id, route in found.items() if loc_id in targets and route.path]
            if reachable:
                return min(reachable, key=lambda route: (round(route.minutes, 6), len(route.path), route.path))
        return None

    def _practice_tier(self, loc: Location) -> int | None:
        """這裡練功是第幾級（0、1、2；Config.training）：照此刻這裡最弱、不是自己人的對手。城裡操練關著、這裡沒有對手是 None。"""
        if not training.on(self.content, self.state.world):
            return None
        foes = self._wild_foes(loc)
        return training.tier_of(self.content.config.training, min(f.difficulty for f in foes)) if foes else None

    def _training_option(self, loc: Location, cost: int, odds: bool) -> Option:
        """行動列「練功」那一格（新手引導重做）：城鎮裡是操練（act:drill，今天還剩幾次；用完了灰掉、寫最近的練功點），城外是練功
        （_practice_option，寫級數與勝算）。"""
        s, c = self.state, self.content
        if not training.is_town(c, loc):
            return self._practice_option(loc, cost, odds)
        left = training.drills_left(s.player, c.config.training, self._pill_day())
        if left > 0:
            return self._cost_option(training.DRILL_ID, training.DRILL, cost, note=training.DRILL_LEFT.format(n=left))
        route = self._nearest_practice()
        where = ""
        if route is not None:
            place = c.locations[route.path[-1]]
            tier = self._practice_tier(place)
            where = training.NEAREST.format(place=place.name, tier=training.TIER_WORDS[tier or 0])
        return Option(id=training.DRILL_ID, label=f"{training.DRILL}（{training.DRILL_FULL}{where}）", enabled=False)

    def _town_drill(self) -> list[str]:
        """城裡操練（act:drill，Config.training）：零風險，給心得（基數＋等級）與一點經驗（基數＋等級÷5），一天幾次。
        不打仗、不扣氣血、不掉東西；經驗本人與帶著的同伴都拿（同出陣守、操練）。"""
        s, c = self.state, self.content
        p, cfg = s.player, c.config.training
        today = self._pill_day()
        if not training.is_town(c, c.locations[p.location]) or training.drills_left(p, cfg, today) <= 0:
            return [training.DONE_TODAY]
        p.stamina -= self._action_costs()["explore"]
        training.spend(p, today)
        xinde, exp = training.gains(cfg, p.member.level)
        msgs = [training.line(p)]
        self._outcome(training.TAG, msgs[0])
        p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
        xinde_line = f"心得 +{xinde}"
        msgs.append(xinde_line)
        if self._draft is not None:
            self._draft.hide(xinde_line)
            self._draft.changes.append(xinde_line)
        keep = team.player_exp(s, c, exp, "drill")[0]  # 減法季三道閘：城裡操練不是仗，45 級以後換心得
        gained = team.maxed_xinde(s, c, exp, "drill")  # 滿級：本人的經驗照 5 換 1 換成心得，同伴照拿經驗
        if gained:
            msgs.append(team.xinde_line(c, p.member, gained))
        msgs += team.add_team_exp(s, c, self.world, exp, "drill")
        if self._draft is not None and exp > 0:
            self._draft.changes += self._exp_changes(exp, keep, gained)
        left = training.drills_left(p, cfg, today)
        if left == 0:
            self._hint("h_drill_done")
        return msgs

    def _precise_social_option(self, cost: int) -> Option:
        """一類一顆的交友（正式季整合 2.8）：照 _social_plan。兩位以上見得到的人物時是「交友」打開名單（act:call，不花體力）；
        一位就直接開口（act:socialize，鈕上寫跟誰說話）；福緣、留在交友的事件也走 act:socialize；沒有人可以說話時灰掉、寫原因、不扣體力。"""
        kind, arg = self._social_plan()
        if kind == "list":
            return Option(id="act:call", label="交友")
        if kind == "talk":
            return self._cost_option("act:socialize", "交友", cost, note=SOCIAL_TALK.format(name=self.content.characters[arg].name))
        if kind is not None:
            return self._cost_option("act:socialize", "交友", cost)
        return Option(id="act:socialize", label=f"交友（{arg}）", enabled=False)

    def _talkable(self, companion_id: str) -> bool:
        """說得上話：見得到（名望或結識）、這個遊戲日還沒談滿、沒對你閉門不見。"""
        return self._can_meet(companion_id) and self._talks_left(companion_id) > 0 and not self._snubbed_character(companion_id)

    def _why_not_talk(self, companion_id: str) -> str:
        if self._snubbed_character(companion_id):
            return SNUB_NOTE
        if not self._can_meet(companion_id):
            return f"名望還差 {self._fame_gap(companion_id)}"
        return self._talked_out_note()

    def _meet_event(self, companion_id: str | None = None) -> Event | None:
        """這裡此刻抽得到的結識事件（照內容順序第一則）；給了 companion_id 只要結識他的那一則。"""
        for event in event_candidates(self.state, self.content, "socialize", "common"):
            met = precise.meets(event)
            if met and (companion_id is None or companion_id in met):
                return event
        return None

    def _fortune_free(self) -> str | None:
        """福緣送得出的那一位（可招募、還沒被人招走的第一位）；沒有是 None。"""
        candidates = [cid for cid, ch in self.content.characters.items() if ch.kind == "recruitable"]
        return next((cid for cid in candidates if roster.owned_by(self.world, cid) is None), None)

    def _social_plan(self) -> tuple[str | None, str | None]:
        """一類一顆的交友這一下會做什麼（選單、動作、對話備料、假人讀同一份）：
        ("fortune", None) 福緣的同伴入門；("once", None) 留在交友的一次性事件；("talk", 人物) 直接開口；("list", None) 兩位以上、打開名單；
        ("meet", 人物或 None) 見不到人、走結識事件；(None, 原因) 沒有人可以說話。"""
        s, c = self.state, self.content
        if roster.fortune_due(s, c) and self._fortune_free() is not None:  # 沒有同伴可給時不再送 30 心得（2.8【PM】）
            return "fortune", None
        if event_candidates(s, c, "socialize", "rare"):
            return "once", None
        people = self._figures_here()
        if len(people) >= AUDIENCE_HALL_FIGURES:
            if any(self._talkable(cid) or self._meet_event(cid) is not None for cid in people):
                return "list", None
            gaps = [cid for cid in people if not self._snubbed_character(cid) and not self._can_meet(cid)]
            return None, self._why_not_talk(min(gaps, key=self._fame_gap) if gaps else people[0])
        if people and self._talkable(people[0]):
            return "talk", people[0]
        if self._meet_event() is not None:
            return "meet", None
        return None, self._why_not_talk(people[0]) if people else SOCIAL_NO_ONE

    def _sect_options(self) -> list[Option]:
        """拜入門派（一類一顆開著時從交友搬出來，正式季整合 2.7）：這裡抽得到的拜門派事件各一顆，不花體力（同投靠）。"""
        s, c = self.state, self.content
        opts = []
        for event in event_candidates(s, c, "sect"):
            sect = next((e.join_sect for ch in event.choices for e in (ch.effect, ch.fail_effect) if e.join_sect), None)
            if sect in c.sects:
                opts.append(Option(id=f"sect:{event.id}", label=SECT_LABEL.format(sect=c.sects[sect].name)))
        return opts

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

    def _train_option(self, loc: Location, cost: int, odds: bool, name: str = "遊歷", tail: str = "") -> Option:
        """遊歷的按鈕（name：出陣的攻寫「出陣・攻」、序章寫「雪恥」；tail：出陣的「今日還能 N 次」，接在體力後面）。遇上自己陣營的隊伍是操練、不會輸（見 _drill），所以只有自己人的地盤寫成「操練・零風險」，
        不拿自己人去算勝算「必敗」（試玩回饋 FB-008）；自己人與外人都有的地方，勝算只看真的會打的那幾路。
        這一趟會是大場面（備料挑到的那一路，見 _train_pick）時，按下去要等模型判讀：wait 寫「兩人對峙……」。"""
        squads = [self.content.squads[sid] for sid in self._train_squad_ids(loc)]
        foes = [squad for squad in squads if not self._drills_with(squad)]
        if not foes:
            return self._cost_option("act:train", "操練", cost, note="零風險")
        note = self._train_note(foes, odds and prologue_rules.fight_tier(self.state, self.content) is None)  # 序章的勝負寫好了，不標勝算
        if len(foes) < len(squads):
            note += "・或與自己人操練"
        option = self._cost_option("act:train", name, cost, note=f"{tail}・{note}" if tail else note)
        if "必敗" in note.split("・"):  # FB-095：剛出師的人疾行到敵營按遊歷，三場就掉三分之一的銀兩
            ride = mounts.escape(self.state, self.content)  # 騎著馬策馬脫身的機會（5.11）：_lose_silver 擲的就是它
            option.confirm = TRAIN_CONFIRM_RIDING.format(odds=mounts.odds_text(ride)) if ride > 0 else TRAIN_CONFIRM
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

    def action_notes(self, option_ids: Iterable[str]) -> dict[str, str]:
        """江湖頁行動列底下那幾行（explain-1）：選單上的探索、練功（FB-670，_practice_line）、遊歷、交友、求見這一下會怎樣，句子在 howto，事實照引擎的規則：
        探索的比重是擲骰用的那一份（_explore_weights），遊歷照這裡的對手與操練（_train_line），交友照會不會直接開口談話
        （_socialize_figure）與這裡有沒有交友事件。只給 option_ids 裡有的。序章裡是空的：探索、遊歷照那一步寫好的走（草廬四景、
        斷眉），師父自己會說。只讀，不擲骰。"""
        s, c = self.state, self.content
        if prologue_rules.active(s, c):
            return {}
        ids = set(option_ids)
        loc = c.locations[s.player.location]
        notes: dict[str, str] = {}
        if "act:explore" in ids and self._outing_on():  # 減法季探索一顆：這一處多半給什麼（比重照擲骰用的那一份，_outing_plan）
            plan = self._outing_plan(loc)
            notes["act:explore"] = howto.outing_line(plan.weights, plan.foe_note)
        elif "act:explore" in ids and explore_modes.on(c):  # 探索三選一：會不會撞上怪、悟不悟得出（設計第三節）
            # 一類一顆開著時找素材不撞仗（正式季整合 2.4），打一場在練功
            fight = not precise.on(c, s.world) and not explore_modes.is_town(c, loc) and bool(self._wild_foes(loc))
            notes["act:explore"] = howto.explore_modes_line(fight, bool(insights.explore_gives(loc, c)))
        elif "act:explore" in ids:
            legend = c.config.legend_item_name if c.config.explore_legend_chance > 0 else None
            blocked = self._insight_blocked(loc)
            kind, until = day_turn(c, s.world) if blocked else ("at", None)
            notes["act:explore"] = howto.explore_line(self._explore_weights(loc), legend, blocked, until, later=kind == "later")
        practice = explore_modes.option_id(explore_modes.PRACTICE)
        if practice in ids:  # 練功在行動列自己一格（FB-670）：灰著的城鎮寫最近的在哪、步行多久
            notes[practice] = self._practice_line(loc)
        if "act:train" in ids and self.duel_on():  # 減法季批 3b：出陣那一格是貼約戰（或截糧）
            notes["act:train"] = self._duel_line(loc)
        elif "act:train" in ids:
            notes["act:train"] = self._sortie_line(loc) if sortie.on(c) and not prologue_rules.active(s, c) else self._train_line(loc)
        if "act:socialize" in ids:
            figure = self._socialize_figure()
            notes["act:socialize"] = howto.social_line(
                None if figure is None else c.characters[figure].name, has_events_here(c, loc, "socialize"), self._audience_hall(),
            )
        if "act:call" in ids:
            notes["act:call"] = howto.CALL_LINE
        if not s.player.picking_audience:  # 只有一位人物時選單上直接列的「求見某某」（行動列交友那一格放它）
            for option_id in ids:
                cid = option_id.removeprefix("call:")
                if option_id.startswith("call:") and cid in c.characters:
                    # 跟選單上那一顆的判斷同一個次序、同一句話（FB-103：格子寫什麼，這一行就說什麼）：閉門不見寫整句（格子只放得下
                    # 「閉門不見」）；見不到寫還差幾點名望、會被打發；談滿了寫整句連同換日的那一刻（格子只放得下「已談滿」，day-scale 審查 I1）
                    name = c.characters[cid].name
                    if self._snubbed_character(cid):
                        notes[option_id] = SNUB_NOTE
                    elif not self._can_meet(cid):
                        notes[option_id] = howto.call_line(name, False, self._fame_gap(cid))
                    elif self._talks_left(cid) == 0:
                        notes[option_id] = self._talked_out_note()
                    else:
                        notes[option_id] = howto.call_line(name, True)
        return notes

    def _insight_blocked(self, loc: Location) -> bool:
        """探索那一行的悟意境那一支，是不是只因為這個遊戲日在這裡選錯過做法才拿掉（這裡本來悟得到、比重不是 0）：是的話那一行
        句尾補一句什麼時候才悟得出（howto.explore_line）。"""
        c = self.content
        return (
            sensing.missed_today(self.state, c, loc)
            and c.config.explore_mix_of(loc.tags).weights.get("insight", 0) > 0 and bool(insights.explore_gives(loc, c))
        )

    def _train_line(self, loc: Location) -> str:
        """遊歷那一行：這裡會打的對手打贏給什麼（Game._battle_rewards：銀兩、心得、經驗、掉素材），遇上自己人是操練
        （Game._drill：對手的 drill_reward_share、不給銀兩素材），打贏或操練推不推大勢：train_trend_push 會推的線裡，有一條今天
        還推得動（_push_room，跟 push_trend 同一個上限的算法；審查 M1：推滿了那一行就不說推動戰局）。第一季的規則沒開時沒有上限。"""
        c = self.content
        squads = [c.squads[sid] for sid in self._train_squad_ids(loc)]
        foes = [squad for squad in squads if not self._drills_with(squad)]
        own = [squad for squad in squads if self._drills_with(squad)]
        share = c.config.drill_reward_share
        gains = [word for word, on in (
            ("銀兩", any(q.reward_silver for q in foes)), ("心得", any(q.reward_xinde for q in foes)), ("經驗", any(q.exp for q in foes)),
        ) if on]
        drill_gains = [word for word, on in (
            ("心得", any(drill_share(q.reward_xinde, share) for q in own)), ("經驗", any(drill_share(q.exp, share) for q in own)),
        ) if on]
        drops = any(materials.may_drop(q, c) for q in foes)
        push = any(delta and self._push_room(line) > 0 for line, delta in self.train_trend_push(loc.id).items())
        return howto.train_line(bool(foes), gains, drops, push, drill_gains, bool(own))

    def _sortie_line(self, loc: Location) -> str:
        return sortie_actions.sortie_line(self, loc)

    def _choice_label(self, choice: Choice, odds: bool) -> str:
        """動手的選項寫對手與勝算，後面照樣接體力的代價（輸了多扣的，企劃者裁決 E6；events.stamina_note）；
        有檢定的寫一行「（屬性 數值：心裡話）」（events.choice_label）。拜入陣營名下的門派、而且手上有新陣營接不了的懸賞時，
        最後多一個括號講會作廢幾張（bounties.join_note，FB-159）。"""
        if choice.combat and odds:
            squad = self._story_squad(self.content.squads[choice.combat])
            odds_text = team.estimate(self.state, self.content, self.world, squad.id, difficulty=squad.difficulty)
            label = f"{choice.text}（對手：{squad.name}・{odds_text}）{stamina_note(choice, self.content)}"
        else:
            label = choice_label(choice, self.state, self.content, self.world)
        return label + bounties.join_note(self.state, self.content, choice)

    def event_option_view(self) -> dict[str, dict] | None:
        """江湖頁事件選項的樣子（減法季批 1，整合設計 6.4）：鈕上只留動作，底下一行小字寫成算，失手的代價不寫在鈕上。
        眼前沒有事件是 None；有的話每一顆 choice:N 一筆 {"act": 動作（拜入門派會作廢懸賞的那一句照樣接在後面）, "kind": 檢定的屬性鍵／
        "fight"／""（網頁照它畫鈕前的小圖示）, "worry": 檢定是「{屬性名} {數值}：{心裡話}」（events.check_note）、動手是「對手：{名字}・{勝算}」、
        不擲骰是空字串, "sure": 有把握（檢定不缺、勝算穩勝或有把握）——網頁照它決定那一行要不要標成擔心的顏色}。
        成算每一顆都寫（Joy 2026-10-27 在決定卡上選「每顆都寫回來」；批 1 原本只在「難說」以下才寫心裡話、不寫屬性與數值）。
        選單上的標籤一個字不改（假人與模擬照舊讀它）。
        只讀：勝算照 odds 的備忘，不擲骰。"""
        s, c = self.state, self.content
        if not s.pending_event or s.pending_event not in c.events:
            return None
        out: dict[str, dict] = {}
        for i, ch in visible_choices(c.events[s.pending_event], s, c):
            act = ch.text + bounties.join_note(s, c, ch)
            if ch.combat:
                squad = self._story_squad(c.squads[ch.combat])
                odds = team.estimate(s, c, self.world, squad.id, difficulty=squad.difficulty, memo=self.odds_memo)
                out[f"choice:{i}"] = {"act": act, "kind": "fight", "worry": f"對手：{squad.name}・{odds}", "sure": odds in ("穩勝", "有把握")}
            elif ch.check:
                gap = check_gap(ch.check, s, c, self.world)
                out[f"choice:{i}"] = {"act": act, "kind": ch.check.stat, "worry": event_rules.check_note(ch.check, s, c, self.world), "sure": gap >= 0}
            else:
                out[f"choice:{i}"] = {"act": act, "kind": "", "worry": "", "sure": True}
        return out

    def odds(self, squad_id: str, at: str | None = None) -> str:
        """勝算的字。at：照哪一處的地利算（輿圖替每一處算，武學隨地理環境計畫第六節）；不給是此刻腳下（在路上沒有）。"""
        return team.estimate(self.state, self.content, self.world, squad_id, memo=self.odds_memo, at=at)

    def _save_season(self) -> None:
        """choose()/travel() 直接在 self.state.world 上就地修改（check_thresholds、
        apply_effect 的 trend 變動等既有程式碼都是這樣寫的，沒有、也不需要特別改寫成
        認得共用儲存的樣子），行動結束後這裡統一寫回共用賽季一次。
        痕跡看得見（減法季批 4）：寫回之前先看有沒有痕跡過了門檻（痕跡只在有人記的那一下漲，記的那一下存季時發就夠；_marks_tick 防漏）。"""
        if jianfa(self.content, self.state.world, "marks_visible"):
            marks_rules.fire_due(self.state, self.content)
        self.world.save_season(self.state.world)

    MARK_ANNAL = "{rumor}這裡頭有你出的一分力。"  # 待 joy 潤：行狀（annals.MARK）——痕跡過了門檻、你在那之前出過力

    def _marks_tick(self) -> None:
        """痕跡看得見（減法季批 4）：同步時補發過了門檻還沒發的（防漏），再替自己記出過力的那幾則行狀（_mark_credits）；
        有改到季（發了、名號拿掉了）才存季。關著什麼都不做。"""
        if not jianfa(self.content, self.state.world, "marks_visible"):
            return
        fired = marks_rules.fire_due(self.state, self.content)
        if self._mark_credits() or fired:
            self._save_season()

    def _zhuan_tick(self) -> None:
        """列傳為終點（減法季批 7b-1）：同步時替自己記行狀——〈天下形勢〉上一次看到之後寫到名號的那幾篇（annals.xingshi_notes），
        季收了之後的季末論功（annals.tier_note）。只改自己的存檔，不存季。關著（zhuan_end）什麼都不做。"""
        s, c = self.state, self.content
        if not jianfa(c, s.world, "zhuan_end"):
            return
        annals.xingshi_notes(s, c, s.world)
        if s.world.ended:
            annals.tier_note(s, c, s.world)

    def _mark_credits(self) -> bool:
        """跨過門檻那一刻出過力的人（WorldState.mark_helpers）裡有自己的，各記一則行狀（annals.MARK：只寫那一句傳聞，不列名字、
        不寫玩家的句子），名號從名單拿掉（名單空了鍵也拿掉）。只在自己的同步裡叫：排程與替別人寫東西的那一份 Game 不記。
        回有沒有記到。"""
        s, c = self.state, self.content
        w, name = s.world, s.player.name
        mine = [mark for mark, names in w.mark_helpers.items() if mark in w.marks_fired and name in names]
        if not mine:
            return False
        by_mark = {r.mark: r for r in c.mark_rules}
        for mark in mine:
            names = w.mark_helpers[mark]
            names.remove(name)
            if not names:
                del w.mark_helpers[mark]
            rule = by_mark.get(mark)
            if rule is None:
                continue
            loc = c.locations.get(marks_rules.place_of(mark))
            annals.note(s, c, annals.MARK, self.MARK_ANNAL.format(rumor=rule.rumor), 2,
                        place=loc.name if loc is not None else "", time=w.marks_fired[mark])
        return True

    def dialogue_request(self, option_id: str, text: str | None = None) -> companion_agent.DialogueRequest | None:
        """鎖外生成的階段 A（server.py 在行動鎖內、很快地呼叫）：現在選這個選項，會不會生成一輪對話？
        會就回傳要送給模型的單子（選項、人物、玩家這一步、messages），不會就是 None。只讀、不改狀態。
        - `talk:N`：N 是上一輪提供的選項、手上有對話、選項沒停用；`talk:leave` 不生成。
        - `act:socialize`：選項沒停用、福緣還沒到（福緣先發，見 _act）、這裡只有一位大勢人物而且見得到
          （兩位以上的地點交友不開口，見 _socialize_figure）；玩家這一步固定是 GENERIC_OPENING。
        - `call:<人物>`：求見選單上按得下去、而且見得到（名望或階級夠、或結識過）的那位人物（這個遊戲日還沒談滿、體力夠）；
          名望不夠的求見也按得下去，但那是被打發、不生成。玩家這一步固定是 GENERIC_OPENING。`call:back` 不生成。
        - `talk:say`（SAY_OPTION，「自己說」）：手上有對話、選項沒停用、text 過得了 say_text；玩家這一步就是那句話。
        其他選項都不呼叫對話模型。
        只讀：選單用 tick=False 取，不推進戰鬥（推進可能結算一回合並呼叫 LLM 潤色，而且備料與
        進鎖重驗各會呼叫這個方法一次；一次請求的那一次推進留給 choose() 開頭）。"""
        option = {o.id: o for o in self.options(odds=False, tick=False)}.get(option_id)
        if option is None or not option.enabled:
            return None
        kind, _, arg = option_id.partition(":")
        if option_id in (SAY_OPTION, PLAN_OPTION):
            companion_id, said = self.state.player.pending_companion, say_text(text, self.say_max())
            if companion_id is None or said is None:
                return None
            extra = self._parley_prompt(companion_id) if option_id == SAY_OPTION else self._parley_plan_prompt(companion_id)
            fields = parley.ASK_FIELDS if option_id == SAY_OPTION else parley.PLAN_FIELDS
            return companion_agent.build_request(self.state, self.content, self.world, companion_id, option_id, said, free=True,
                                                 extra=extra, required=fields if extra else ())
        if option_id == ROAD_SAY:  # NPC 智能 2.1：他帶路的路上跟他說一句（可以是閒談，也可以求他沿路做得到的事）
            companion_id, said = self.state.player.parley_escort, say_text(text, self.say_max())
            if companion_id is None or said is None:
                return None
            extra = self._parley_prompt(companion_id, road=True)
            return companion_agent.build_request(self.state, self.content, self.world, companion_id, option_id, said, free=True,
                                                 extra=extra, required=parley.ASK_FIELDS if extra else ())
        if kind == "talk":
            companion_id = self.state.player.pending_companion
            if companion_id is None or not arg.isdecimal():
                return None
            shown, _ = companion_agent.offered(self.state, companion_id)
            if int(arg) >= len(shown):
                return None
            player_action = shown[int(arg)]
        elif option_id == "act:socialize" and precise.on(self.content, self.state.world):
            companion_id = self._socialize_figure()  # 一類一顆：只有 _social_plan 是 talk 才開口
            if companion_id is None:
                return None
            player_action = companion_agent.GENERIC_OPENING
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
        extra = self._parley_plea_prompt(companion_id) if player_action == companion_agent.GENERIC_OPENING else ""
        return companion_agent.build_request(
            self.state, self.content, self.world, companion_id, option_id, player_action,
            extra=extra, required=parley.PLEA_FIELDS if extra else (),
        )

    def _checked_prepared(
        self, option_id: str, prepared: companion_agent.PreparedTurn | None, text: str | None = None,
    ) -> companion_agent.PreparedTurn | None:
        """進鎖後重驗鎖外生成的結果：選項、人物、玩家這一步都要跟「現在」重算出來的單子一致才採用；
        對不上（連點兩下、選項清單已換）就當沒給，走一般路徑在鎖內生成——很少發生，慢一點可以接受。
        對不上時連它的失敗（turn=None）一起丟掉，不能讓別張單子的失敗結束現在這段對話。"""
        if prepared is None:
            return None
        request = self.dialogue_request(option_id, text)
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

    # ── 酒肆（企劃者 2026-10-18；設計稿 https://claude.ai/artifact/3CfrzfpT1HzCxy6S985Q5W）────────────
    # 規則全在 tavern.py（tavern_rules）；這裡只管接上選單、扣錢、讀別人的存檔、寫紀錄與季。

    def _tavern_open(self) -> bool:
        """酒肆那一串此刻開著、人也還在酒肆裡（MAIN_ACTIONS["tavern"] 收不收的判斷）。"""
        return self.state.player.picking_tavern and tavern_rules.here(self.state, self.content)

    def _tavern_enter(self) -> list[str]:
        s, c = self.state, self.content
        if not (tavern_rules.on(c) and tavern_rules.here(s, c)) or not self._idle():
            return [tavern_rules.NOT_HERE]
        s.player.picking_tavern, s.player.shop_clue = True, ""
        self._shop_say("enter")
        return [tavern_rules.ENTERED.format(sign=tavern_rules.sign(s, c))]

    def _tavern_price(self, base: int) -> int:
        return tavern_rules.price(self.content, self.state.world, base)

    def _tavern_options(self) -> list[Option]:
        """酒肆那一串（店面關著、假人與整季機器人看的選單）：聽消息、請酒、藏行跡、反查、懸賞榜、出酒肆。查人、交情、素材、題壁要打字或挑東西，
        只在店面上（MAIN_ACTIONS["tavern"]）。錢不夠的灰掉寫還差多少。都不花體力。"""
        s, c = self.state, self.content
        cfg = c.config.tavern
        opts = []
        for oid, label, base, problem in (
            (tavern_rules.NEWS_ID, tavern_rules.NEWS_LABEL, cfg.news_price, None),
            (tavern_rules.TREAT_ID, tavern_rules.TREAT_LABEL, cfg.treat_price, self._tavern_treat_problem()),
            ("tavern:hide", tavern_rules.HIDE_LABEL, cfg.hide_price, self._tavern_hide_problem()),
            ("tavern:trace", tavern_rules.TRACE_LABEL, cfg.trace_price, None),
        ):
            price = self._tavern_price(base)
            problem = problem or tavern_rules.pay_problem(s, price)
            text = label.format(price=price)
            opts.append(Option(id=oid, label=text if problem is None else f"{text}・{problem}", enabled=problem is None))
        if bounties.board_here(s, c) and bounties.visible(s, c):
            opts.append(Option(id=tavern_rules.BOARD_ID, label=tavern_rules.BOARD_LABEL))
        return opts + [Option(id=tavern_rules.BACK_ID, label=tavern_rules.BACK_LABEL)]

    def _tavern_choice(self, arg: str) -> list[str]:
        if arg == "back":
            tavern_rules.close(self.state)
            return [tavern_rules.LEFT]
        if arg == "board":  # 牆上的懸賞榜：收起酒肆、打開懸賞榜（同城裡的 act:bounties）
            tavern_rules.close(self.state)
            self.state.player.picking_bounty = True
            self._shop_say("enter")
            return [f"你走到牆邊，看起{bounties.BOARD}。"]
        return self._tavern_run(arg)

    def tavern_do(self, op: str, target: str = "", text: str = "") -> list[str]:
        """酒肆那一頁的動作（MAIN_ACTIONS["tavern"]）：news 聽消息、seek 查人在哪、ties 打聽交情、material 打聽素材（target 是素材 id）、
        wall 題壁（text）、treat 請酒、hide 藏行跡、trace 反查。酒肆開著才收；做成了寫一則紀錄（同一趟坐下來的併成一則）。"""
        if not self._tavern_open():
            return self._log([equipment.NOT_NOW])
        return self._log(self._tavern_run(str(op), str(target or "").strip(), str(text or "")))

    def _tavern_run(self, op: str, target: str = "", text: str = "") -> list[str]:
        s = self.state
        before = s.player.stats.get("silver", 0)
        handler = {
            "news": self._tavern_news, "treat": self._tavern_treat, "hide": self._tavern_hide, "trace": self._tavern_trace,
            "seek": lambda: self._tavern_seek(target, watch=text == "watch"), "ties": lambda: self._tavern_ties(target),
            "material": lambda: self._tavern_material(target), "wall": lambda: self._tavern_wall(text),
            "hit": lambda: self._tavern_hit(target, text), "guard": self._tavern_guard,
            "ask": lambda: self._tavern_ask(text),
        }.get(op)
        if handler is None:
            return ["（沒有這個動作。）"]
        msgs = handler()
        paid = before - s.player.stats.get("silver", 0)
        if paid:
            msgs = msgs + [f"銀兩 {-paid:+d}"]
        if paid:  # 真的花了錢（問不到退一半也算）才寫紀錄；被拒、沒收錢的只回一句
            s.player.newbie_marks.add("tavern")  # 新手目標：在酒肆打聽一件事
            self._write(tavern_rules.sign(s, self.content), msgs, merge=True)
            self._save_season()
        return msgs

    def _tavern_charge(self, base: int) -> int | None:
        """扣這一下的錢：付得起回價錢，付不起記掌櫃那一句、回 None。"""
        price = self._tavern_price(base)
        problem = tavern_rules.pay_problem(self.state, price)
        if problem is not None:
            self._shop_after(problem, "refused")
            return None
        tavern_rules.pay(self.state, price)
        return price

    def _tavern_short(self, base: int) -> list[str]:
        return [tavern_rules.pay_problem(self.state, self._tavern_price(base)) or ""]

    def _tavern_wanted(self) -> set[str]:
        """身上有通緝的名號鍵（名氣 +1）。"""
        return {name_key(b.target) for b in bounties.open_bounties(self.state, self.content) if b.kind == "wanted" and b.target}

    def _tavern_news(self) -> list[str]:
        s, c = self.state, self.content
        pick = tavern_rules.news_pick(s, c)
        region = tavern_rules.region_lines(s, c)
        if pick is None and not region:
            self._shop_say("nothing")
            return [tavern_rules.NOTHING_NEW]
        if self._tavern_charge(c.config.tavern.news_price) is None:
            return self._tavern_short(c.config.tavern.news_price)
        lines = []
        if pick is not None:
            lines.append(f"{tavern_rules.NEWS_HEAD}「{pick.text}」")
            s.player.tavern_heard = (s.player.tavern_heard + [tavern_rules.rumor_key(pick)])[-200:]
        lines += region
        tavern_rules.add_note(s, c, "news", tavern_rules.TITLES["news"], lines)
        self._shop_say("news")
        return lines

    def _tavern_find(self, target: str) -> tuple[str | None, Game | None]:
        """名號認人：先認人物（名字一模一樣），再認玩家存檔（不分大小寫）。回（人物 id, 玩家那一份）；都不是是 (None, None)。"""
        c = self.content
        for cid, ch in c.characters.items():
            if ch.name == target:
                return cid, None
        if name_key(target) == name_key(self.state.player.name):
            return None, None
        other = self._load_kin(target)
        if other is not None:
            other.state.world = self.state.world
        return None, other

    def _tavern_whisper(self, kind: str, other: Game) -> None:
        """被打聽的人收到風聲：記在季上，他下次同步時補（_deliver_whispers）。匿名行走的人只會是個生面孔。"""
        s, c = self.state, self.content
        w = tavern_rules.whisper(kind, s, c, s.player.location, s.world.time)
        if s.player.anonymous:
            w.named = False
        tavern_rules.post_whisper(s.world, other.state.player.name, w)
        self.touched.add(other.state.player.name)

    def _tavern_watch_problem(self, target: str) -> str | None:
        p, cfg = self.state.player, self.content.config.tavern
        mine = [w for w in p.tavern_watches if w.until_real > self.now]
        if any(name_key(w.target) == name_key(target) for w in mine):
            return tavern_rules.WATCH_SAME.format(name=target)
        if len(mine) >= cfg.watch_keep:
            return tavern_rules.WATCH_FULL.format(n=cfg.watch_keep)
        return None

    def _tavern_seek(self, target: str, watch: bool = False) -> list[str]:
        lines = self._tavern_seek_once(target)
        if not watch or not target or name_key(target) == name_key(self.state.player.name) or self._tavern_seek_exact is None:
            return lines
        if self._tavern_seek_exact:
            return lines + [tavern_rules.WATCH_CLEAR]
        return lines + self._tavern_watch(target)

    def _tavern_watch(self, target: str) -> list[str]:
        """託酒家留意：多付查人的 watch_share，記在自己身上；他自己同步時那個人打聽得到確切地點就捎信（_deliver_watches）。
        查無此人也照收（不讓人拿託付試出誰在不在），到期捎一句沒聽到準信。"""
        s, c, cfg = self.state, self.content, self.content.config.tavern
        problem = self._tavern_watch_problem(target)
        if problem is not None:
            return [problem]
        base = int(round(cfg.seek_price * cfg.watch_share))
        if self._tavern_charge(base) is None:
            return self._tavern_short(base)
        p = s.player
        p.tavern_watches = [w for w in p.tavern_watches if w.until_real > self.now]
        p.tavern_watches.append(TavernWatch(target=target, place=p.location, until_real=self.now + cfg.watch_hours * 3600))
        line = tavern_rules.WATCH_PLACED.format(name=target)
        if p.tavern_notes:
            p.tavern_notes[-1].lines.append(line)
        return [line]

    def _deliver_watches(self) -> None:
        """託的人自己同步時：留意的那個人打聽得到確切地點（從託的那一間算，打聽度 WATCH_AT 以上、沒下線太久）就捎信；到期的捎一句沒消息。"""
        s, c, cfg = self.state, self.content, self.content.config.tavern
        p = s.player
        if not p.tavern_watches:
            return
        lines, keep = [], []
        for w in p.tavern_watches:
            other = self._load_kin(w.target)
            if other is not None:
                other.state.world = s.world
                op = other.state.player
                seen = op.seen_real or 0.0
                online = not seen or self.now - seen <= cfg.offline_hours * 3600
                if online and tavern_rules.hit_reach(c, w.place, other.state) >= tavern_rules.WATCH_AT:
                    if op.journey is not None:
                        lines.append(tavern_rules.WATCH_ROAD.format(name=op.name, place=c.locations[op.journey.path[op.journey.last]].name))
                    else:
                        lines.append(tavern_rules.WATCH_FOUND.format(name=op.name, place=c.locations[op.location].name))
                    tavern_rules.remember(s, op.name)
                    continue
            if w.until_real <= self.now:
                lines.append(tavern_rules.WATCH_LAPSED.format(name=w.target))
                continue
            keep.append(w)
        if len(keep) != len(p.tavern_watches):
            p.tavern_watches = keep
        if lines:
            self._write(tavern_rules.WATCH_TITLE, lines)

    def _tavern_seek_once(self, target: str) -> list[str]:
        s, c = self.state, self.content
        cfg = c.config.tavern
        self._tavern_seek_exact = None  # 查人那一下問得多清楚（託酒家留意看它）：None 沒查成、True 確切地點、False 沒問清楚
        if not target:
            return [tavern_rules.ASK_EMPTY]
        if name_key(target) == name_key(s.player.name):
            return [tavern_rules.ASK_SELF]
        if self._tavern_charge(cfg.seek_price) is None:
            return self._tavern_short(cfg.seek_price)
        self._tavern_seek_exact = False
        price = self._tavern_price(cfg.seek_price)
        cid, other = self._tavern_find(target)
        if cid is not None:
            lines = tavern_rules.seek_figure_lines(s, c, cid)
            self._tavern_seek_exact = True  # 人物不託（他們走到哪都有人談）
        elif other is not None:
            lines, found = tavern_rules.seek_lines(s, c, other.state, self.now, self._tavern_wanted())
            seen = other.state.player.seen_real or 0.0
            self._tavern_seek_exact = found and (not seen or self.now - seen <= cfg.offline_hours * 3600) \
                and tavern_rules.person_reach(s, c, other.state, self._tavern_wanted()) >= tavern_rules.WATCH_AT
            self._tavern_whisper("seek", other)
            if not found:
                back = tavern_rules.refund(s, c, price)
                self._shop_say("missed")
                lines = [tavern_rules.HALF_MISS.format(refund=back) if tavern_rules.person_fame(other.state, c) >= 1
                         else tavern_rules.NOBODY.format(refund=back)]
                tavern_rules.add_note(s, c, "seek", f"{tavern_rules.TITLES['seek']}・{target}", lines)
                return lines
            tavern_rules.remember(s, other.state.player.name)
        else:  # 沒有這個人：跟默默無名的人問不到同一句（不讓人拿酒肆試出誰在不在）
            back = tavern_rules.refund(s, c, price)
            self._shop_say("missed")
            lines = [tavern_rules.NOBODY.format(refund=back)]
            tavern_rules.add_note(s, c, "seek", f"{tavern_rules.TITLES['seek']}・{target}", lines)
            return lines
        tavern_rules.add_note(s, c, "seek", f"{tavern_rules.TITLES['seek']}・{target}", lines)
        self._shop_say("asked")
        return lines

    def _tavern_ties(self, target: str) -> list[str]:
        s, c = self.state, self.content
        cfg = c.config.tavern
        if not target:
            return [tavern_rules.ASK_EMPTY]
        if name_key(target) == name_key(s.player.name):
            return [tavern_rules.ASK_SELF]
        if self._tavern_charge(cfg.ties_price) is None:
            return self._tavern_short(cfg.ties_price)
        price = self._tavern_price(cfg.ties_price)
        cid, other = self._tavern_find(target)
        wanted = self._tavern_wanted()
        found = True
        if cid is not None:
            holders = []
            if hasattr(self.world, "db"):
                for state in CharacterStore(self.world.db).all():
                    n = state.player.affinities.get(cid, 0)
                    if n > 0 and name_key(state.player.name) != name_key(s.player.name):
                        state.world = s.world
                        holders.append((state, n))
            holders.sort(key=lambda pair: (-pair[1], pair[0].player.name))
            lines = tavern_rules.ties_figure_lines(s, c, cid, holders, wanted)
        elif other is not None:
            mates = [c.characters[m].name for m in other.state.player.team if m in c.characters]
            lines, found = tavern_rules.ties_player_lines(s, c, other.state, mates, wanted)
            self._tavern_whisper("ties", other)
            if found:
                tavern_rules.remember(s, other.state.player.name)
        else:
            lines, found = [], False
        if not found:
            back = tavern_rules.refund(s, c, price)
            self._shop_say("missed")
            lines = [tavern_rules.NOBODY.format(refund=back)]
        else:
            self._shop_say("asked")
        tavern_rules.add_note(s, c, "ties", f"{tavern_rules.TITLES['ties']}・{target}", lines)
        return lines

    def _tavern_material(self, mid: str) -> list[str]:
        s, c = self.state, self.content
        material = c.materials.get(mid)
        if material is None:
            return [tavern_rules.MATERIAL_UNKNOWN]
        base = c.config.tavern.material_prices.get(material.tier, max(c.config.tavern.material_prices.values()))
        if self._tavern_charge(base) is None:
            return self._tavern_short(base)
        lines, found = tavern_rules.material_lines(s, c, material)
        if not found:
            back = tavern_rules.refund(s, c, self._tavern_price(base))
            lines = [tavern_rules.MATERIAL_NONE.format(name=material.name, refund=back)]
            self._shop_say("missed")
        else:
            self._shop_say("asked")
        tavern_rules.add_note(s, c, "material", f"{tavern_rules.TITLES['material']}・{material.name}", lines)
        return lines

    def _tavern_wall(self, text: str) -> list[str]:
        s, c = self.state, self.content
        problem = tavern_rules.wall_problem(c, text)
        if problem is not None:
            self._shop_after(problem, "wall")
            return [problem]
        if self._tavern_charge(c.config.tavern.wall_price) is None:
            return self._tavern_short(c.config.tavern.wall_price)
        tavern_rules.write_wall(s.world, c, s.player.location, display_name(s), text)
        self._shop_say("wall")
        return [tavern_rules.WALL_DONE, f"「{text.strip()}」"]

    def _tavern_treat_problem(self) -> str | None:
        return tavern_rules.TREAT_FULL if self.state.player.tavern_treat_day == self._pill_day() else None

    def _tavern_treat(self) -> list[str]:
        s, c = self.state, self.content
        cfg = c.config.tavern
        problem = self._tavern_treat_problem()
        if problem is not None:
            self._shop_after(problem, "treat")
            return [problem]
        if self._tavern_charge(cfg.treat_price) is None:
            return self._tavern_short(cfg.treat_price)
        p = s.player
        p.tavern_treat_day = self._pill_day()
        who = display_name(s)
        s.world.tavern_treats[p.location] = (who, s.world.time)
        add_rumor(s, tavern_rules.TREAT_LINE.format(name=who, place=c.locations[p.location].name), p.location,
                        content=c, layer="local", named=not p.anonymous)
        self._shop_say("treat")
        return [tavern_rules.TREAT_DONE] + renown.gain(s, c, "fame", cfg.treat_fame)

    def _tavern_hide_problem(self) -> str | None:
        p = self.state.player
        if p.hidden_until > self.state.world.time:
            return tavern_rules.HIDE_ALREADY.format(when=self.stamp(p.hidden_until))
        return None

    def _tavern_hide(self) -> list[str]:
        s, c = self.state, self.content
        problem = self._tavern_hide_problem()
        if problem is not None:
            self._shop_after(problem, "hide")
            return [problem]
        if self._tavern_charge(c.config.tavern.hide_price) is None:
            return self._tavern_short(c.config.tavern.hide_price)
        s.player.hidden_until = s.world.time + DAY
        self._shop_say("hide")
        return [tavern_rules.HIDE_DONE]

    def _tavern_trace(self) -> list[str]:
        s, c = self.state, self.content
        pending = [w for w in s.player.whispers if not (w.named or w.revealed)]
        if not pending:
            self._shop_say("nothing")
            return [tavern_rules.TRACE_NONE]
        if self._tavern_charge(c.config.tavern.trace_price) is None:
            return self._tavern_short(c.config.tavern.trace_price)
        others = {}
        last = pending[-1]
        other = self._load_kin(last.who)
        if other is not None:
            other.state.world = s.world
            others[name_key(last.who)] = other.state
        lines, _ = tavern_rules.trace_lines(s, c, others)
        tavern_rules.add_note(s, c, "trace", tavern_rules.TITLES["trace"], lines)
        self._shop_say("trace")
        return lines

    # ── 買殺手（設計第六節）：雇（_tavern_hit）、保鏢（_tavern_guard）、殺手出手（_tavern_hit_check，對方自己在城外做完一件事時）、
    # 雇主收結果（_deliver_hits，雇主自己同步時）。單子在季上（WorldState.tavern_hits），亂數用自己的種子，不動 Game.rng ──

    def _tavern_hit_problem(self, target: str, tier: int) -> tuple[str | None, Game | None]:
        """雇不雇得了（拒絕的話, 對方那一份）：要先在酒肆查到過這個人（不然查無此人與默默無名讀得出差別）、不是自己、
        截殺的緊急開關開著（Config.raid.enabled）；同陣營也接（企劃者 2026-10-27「不應該限制玩家」，以前要有仇）；雙方都過了新手期、對方身上沒有別人的單、同一對人 hit_pair_hours 內沒雇過、季還在跑。"""
        s, c, cfg = self.state, self.content, self.content.config.tavern
        if s.world.ended:
            return tavern_rules.HIT_ENDED, None
        if not 0 <= tier < len(cfg.hit_prices):
            return tavern_rules.HIT_BAD_TIER, None
        if not target or name_key(target) not in {name_key(n) for n in s.player.tavern_known} | self._tavern_wanted():
            return tavern_rules.HIT_NEED_KNOWN, None
        cid, other = self._tavern_find(target)
        if other is None:
            return tavern_rules.HIT_NEED_KNOWN, None
        them = other.state.player.name
        if name_key(them) == name_key(s.player.name):
            return tavern_rules.HIT_SELF, other
        if not c.config.raid.enabled:
            return tavern_rules.HIT_ENDED, other
        if roster.raid_newbie(s, c):
            return tavern_rules.HIT_NEWBIE_ME, other
        if roster.raid_newbie(other.state, c):
            return tavern_rules.HIT_NEWBIE_THEM.format(name=them), other
        if tavern_rules.active_hit(s.world, them, self.now) is not None:
            return tavern_rules.HIT_TAKEN.format(name=them), other
        recent = self.now - cfg.hit_pair_hours * 3600
        if any(name_key(h.client) == name_key(s.player.name) and name_key(h.target) == name_key(them) and h.placed_real > recent
               for h in s.world.tavern_hits):
            return tavern_rules.HIT_PAIR.format(name=them), other
        return None, other

    def _tavern_hit(self, target: str, spec: str) -> list[str]:
        """雇殺手：spec 是「檔次」或「檔次:hush」（多付封口錢）。付了錢掛單；對方擲一次聽不聽得到風聲（不說是誰）。"""
        s, c, cfg = self.state, self.content, self.content.config.tavern
        head, _, flag = str(spec or "").partition(":")
        tier = int(head) if head.strip().isdigit() else -1
        problem, other = self._tavern_hit_problem(target, tier)
        if problem is not None:
            self._shop_after(problem, "refused")
            return [problem]
        hush = flag == "hush"
        them = other.state.player.name
        w = s.world
        streak = tavern_rules.hit_streak(w, s.player.name, them, cfg.hit_fail_max)
        base = tavern_rules.hit_price_base(c, tier, streak) + (cfg.hush_price if hush else 0)
        price = self._tavern_charge(base)
        if price is None:
            return self._tavern_short(base)
        w.tavern_hit_seq += 1
        hit = TavernHit(id=w.tavern_hit_seq, client=s.player.name, target=them, tier=tier, price=price, place=s.player.location,
                        placed_real=self.now, until_real=self.now + cfg.hit_hours * 3600, hushed=hush, streak=streak)
        warn = cfg.hit_warn + 0.05 * renown.fame_tier(other.state, c)
        if tavern_rules.rng_for("酒肆殺手風聲", w.tavern_hit_seq, s.player.name, them, w.time).random() < warn:
            hit.warned = True
            note = Whisper(kind="hit", who=s.player.name, place=s.player.location, time=w.time,
                           hint=tavern_rules.side_hint(s, c), hushed=hush)
            tavern_rules.post_whisper(w, them, note)
            self.touched.add(them)
        w.tavern_hits.append(hit)
        name = tavern_rules.hit_tier_name(tier)
        lines = [tavern_rules.HIT_PLACED.format(name=them, tier=name, until=self._real_stamp(hit.until_real))]
        if streak:
            lines.append(tavern_rules.HIT_STREAK.format(name=them, n=streak, pct=round(cfg.hit_fail_price_step * streak * 100)))
        if hush:
            lines.append(tavern_rules.HIT_HUSHED)
        tavern_rules.add_note(s, c, "hit", f"{tavern_rules.TITLES['hit']}・{them}", lines)
        self._shop_say("asked")
        return lines

    def _real_stamp(self, real: float) -> str:
        """現實秒換成玩家看得到的時刻（季曆的寫法）：照此刻的世界時間往後推。"""
        w = self.state.world
        return self.stamp(w.time + (real - self.now) * self.content.config.time_scale)

    def _tavern_guard_problem(self) -> str | None:
        p = self.state.player
        if p.tavern_guard_until > self.now:
            return tavern_rules.GUARD_ALREADY.format(until=self._real_stamp(p.tavern_guard_until))
        return None

    def _tavern_guard(self) -> list[str]:
        s, c, cfg = self.state, self.content, self.content.config.tavern
        problem = self._tavern_guard_problem()
        if problem is not None:
            self._shop_after(problem, "refused")
            return [problem]
        if self._tavern_charge(cfg.guard_price) is None:
            return self._tavern_short(cfg.guard_price)
        s.player.tavern_guard_until = self.now + cfg.guard_hours * 3600
        line = tavern_rules.GUARD_DONE.format(until=self._real_stamp(s.player.tavern_guard_until))
        tavern_rules.add_note(s, c, "guard", tavern_rules.TITLES["guard"], [line])
        self._shop_say("hide")
        return [line]

    def _tavern_hit_check(self, away_from: float | None = None) -> list[str]:
        """自己（被盯上的人）剛做完一件事：有一張找你的單子、你人在城外、不在路上、不在決戰裡、沒剛被人截殺或設伏過、沒剛被殺手得手過
        （tavern_shield_until），殺手照打聽度擲一次找不找得到；找到了本人對本人打一場。到期的單子在這裡收（退款由雇主自己同步時領）。
        away_from 是同步時「上一次同步的現實秒」（下線那一段，企劃者 2026-10-27）：這一段跟單子的期限重疊、你下線那一刻站在城外，
        一樣擲一次（城鎮裡下線照舊安全）；在這一段裡到期的單子先擲再收。"""
        s, c = self.state, self.content
        w, me = s.world, s.player
        if not tavern_rules.on(c) or not w.tavern_hits:
            return []
        key = name_key(me.name)
        mine = [h for h in w.tavern_hits if not h.done and name_key(h.target) == key]
        if not mine:
            return []
        start = self.now if away_from is None else away_from
        live = [h for h in mine if h.until_real > start and h.placed_real < self.now]
        for h in mine:
            if h.until_real <= self.now:
                h.done, h.outcome = True, "過期"
        hit = next(iter(live), None)
        if hit is None or w.ended or me.journey is not None or tavern_rules.town(c, me.location) or roster.raid_newbie(s, c):
            return []
        if me.tavern_shield_until > self.now:
            return []
        battle = self._battle_now()  # 有攻城戰時是自己參戰的那一場（領地爭奪第二批）
        if battle is not None and me.name in battle.participants:
            return []
        shield = w.raided.get(key)
        if shield is not None and w.time - shield < c.config.raid.shield_seconds:
            return []
        rng = tavern_rules.rng_for("酒肆殺手", hit.id, me.name, w.time)
        reach = tavern_rules.hit_reach(c, hit.place, s, self._tavern_wanted_of(me.name))
        if rng.random() >= tavern_rules.find_chance(c, reach):
            return []
        hit.done = False  # 下線那一段裡到期的單子：上面先收成過期，擲中了照打
        return self._tavern_hit_fight(hit, rng, away=away_from is not None)

    def _tavern_wanted_of(self, name: str) -> set[str]:
        """這個人身上有沒有通緝（名氣 +1）：有就回只含他名號鍵的集合。"""
        return {name_key(name)} & self._tavern_wanted()

    def _tavern_hit_fight(self, hit, rng: random.Random, away: bool = False) -> list[str]:
        s, c, cfg = self.state, self.content, self.content.config.tavern
        w, me = s.world, s.player
        tier_name = tavern_rules.hit_tier_name(hit.tier)
        mine = self._spar_power(self, self)
        power = tavern_rules.hit_power_of(c, hit.tier, hit.streak)
        if me.tavern_guard_until > self.now:
            power *= cfg.guard_scale
        # 殺手照你自己的威力浮上來（同江湖水漲）：玉璽碎片的戰力不浮上去（改版），沒碎片時跟 mine 一樣
        killer = max(1.0, self._spar_power(self, self, seal=False) * power)
        result = encounter.resolve_encounter(mine, killer, rng)
        w.raided[name_key(me.name)] = w.time
        hit.done = True
        squad = Squad(id="assassin", name=tier_name, difficulty=killer)
        record = battlelog.new_record(s, c, self.world, squad, result, "assassin")
        record.ours = record.ours[:1]
        hp_lost: int | None = 0
        extra: list[str] = []
        if result.tier in team.WIN_TIERS:
            hit.outcome = "對方贏"
            found = math.floor(hit.price * cfg.hit_bounty_share)
            me.stats["silver"] = me.stats.get("silver", 0) + found
            record.silver = found
            story = tavern_rules.HIT_STORY_WON.format(tier=tier_name, n=found)
            record.changes += renown.gain(s, c, "fame", cfg.hit_win_fame)
            client = self._load_kin(hit.client)
            tier = renown.fame_tier(client.state, c) if client is not None else 0
            chance = (cfg.hit_reveal + 0.1 * tier) * (0.5 if hit.hushed else 1.0)
            if rng.random() < chance:
                extra.append(tavern_rules.HIT_REVEALED.format(who=hit.client))
                tavern_rules.remember(s, hit.client)
                hit.outcome = "對方贏・供出"
                add_rumor(s, tavern_rules.HIT_RUMOR.format(who=hit.client, name=me.name), hit.place, content=c, layer="local")
            else:
                extra.append(tavern_rules.HIT_SILENT)
        elif result.tier in team.DRAW_TIERS:
            hit.outcome = "平手"
            story = tavern_rules.HIT_STORY_DRAW.format(tier=tier_name)
        else:
            hit.outcome = "殺手贏"
            purse = me.stats.get("silver", 0)
            lost = min(cfg.hit_silver_cap, math.ceil(purse * cfg.hit_silver_share)) if purse > 0 else 0
            me.stats["silver"] = purse - lost
            record.silver = -lost
            con = team.con_of(s, c, self.world, PLAYER)
            now_hp, _ = team.member_neili(c, me.member, con, season=s.world)
            me.member.neili = min(now_hp, 1.0)  # 只剩一口氣（企劃者 2026-10-27）：防具、化勁都不擋，逼人去醫館
            hp_lost = max(0, round(now_hp - me.member.neili))
            record.changes.append(tavern_rules.HIT_HP_LEFT)
            me.tavern_shield_until = self.now + cfg.hit_shield_hours * 3600
            story = tavern_rules.HIT_STORY_LOST.format(tier=tier_name)
        if away:
            story = tavern_rules.HIT_AWAY.format(place=c.locations[me.location].name) + story
        record.notes.append(story)
        record.notes += extra
        annals.note(s, c, annals.FIGHT, story, 2)
        self._play_rounds(record, squad, result.tier, hp_lost)
        line = self._file_battle(record)
        msgs = [line, story, *extra, *battlelog.gains_list(record), *self._last_wear]
        self._write(tavern_rules.HIT_STRUCK, msgs, tag=battlelog.outcome_text(record))
        self.touched.add(hit.client)
        return msgs

    def _deliver_hits(self) -> None:
        """雇主自己同步時：收自己雇的單子的結果（得手、失手、平手、到期退一半），一張一句、一則紀錄；得手的記惡名。"""
        s, c, cfg = self.state, self.content, self.content.config.tavern
        w, me = s.world, s.player
        if not w.tavern_hits:
            return
        key = name_key(me.name)
        lines: list[str] = []
        for h in w.tavern_hits:
            if name_key(h.client) != key or h.refunded:
                continue
            if not h.done and h.until_real <= self.now:
                h.done, h.outcome = True, "過期"
            if not h.done:
                continue
            h.refunded = True
            tier = tavern_rules.hit_tier_name(h.tier)
            if h.outcome == "過期":
                back = int(h.price * cfg.refund_share)
                me.stats["silver"] = me.stats.get("silver", 0) + back
                lines.append(tavern_rules.HIT_REFUND.format(name=h.target, tier=tier, n=back))
            elif h.outcome == "殺手贏":
                lines.append(tavern_rules.HIT_WON_CLIENT.format(tier=tier, name=h.target))
                lines += renown.gain(s, c, "evil", cfg.hit_evil)
            elif h.outcome.startswith("對方贏"):
                lines.append(tavern_rules.HIT_LOST_CLIENT.format(tier=tier, name=h.target))
                if h.outcome.endswith("供出"):
                    lines.append(tavern_rules.HIT_LOST_NAMED)
            else:
                lines.append(tavern_rules.HIT_DRAW_CLIENT.format(tier=tier, name=h.target))
        if lines:
            self._write(tavern_rules.HIT_TITLE, lines)
            self._save_season()

    # ── 問酒家（設計第八節）：A tavern_ask_request（只讀）→ B 鎖外 tavern.ask_write → C tavern_ask（重驗同一間、同一句，再過一次 ask_clean）──

    def _tavern_ask_facts(self, question: str = "") -> tuple[tuple[str, ...], tuple[str, ...]]:
        """問酒家的事實清單與問到的是哪幾類：先照問句找（tavern_ask.topics：名號、地名、素材、武學、店面、玩法、季勢；問句裡的玩家名號
        從存檔載入），再接原本那幾條（這一區的局勢、最近的傳聞、這裡的出產、座上客、你自己）。A、C 兩段各算一次，同一句算出來一樣。"""
        s, c = self.state, self.content
        p = s.player
        players: dict[str, GameState] = {}
        if hasattr(self.world, "db") and question:
            for name in tavern_ask.name_hits(question, CharacterStore(self.world.db).names()):
                other = self._load_kin(name)
                if other is not None:
                    players[other.state.player.name] = other.state
        topic, kinds = tavern_ask.topics(s, c, question, players, self._tavern_wanted())
        extra = []
        guests = [o.player.name for o in social.here(self)][:6]
        if guests:
            extra.append(f"此刻也在{c.locations[p.location].name}的江湖人：{'、'.join(guests)}。")
        side = social.side(s, c)
        extra.append(f"問話的客官是{side}，名號{p.name}，此刻在{c.locations[p.location].name}。")
        base = [f for f in tavern_rules.ask_facts(s, c, extra) if f not in topic]
        return tuple(topic + base), tuple(kinds)

    def tavern_chatter_request(self) -> tavern_rules.ChatterRequest | None:
        """A 段（鎖內、只讀）：酒肆開著、這一間的閒談該換了，就開一張單（server.write_chatter 在背景請模型寫）。"""
        s, c = self.state, self.content
        loc = s.player.location
        if not self._tavern_open() or not tavern_rules.chatter_due(s.world, c, loc):
            return None
        return tavern_rules.ChatterRequest(place=loc, sign=tavern_rules.sign(s, c), asked_at=s.world.time,
                                           facts=tavern_rules.chatter_facts(s, c, loc))

    def apply_tavern_chatter(self, request: tavern_rules.ChatterRequest, lines: list[str]) -> bool:
        """C 段：這一間還是該換（沒有別人先寫好），就記下這一段；寫不出來記空清單，這一陣子照固定句、不再叫模型。記了回 True。"""
        s, c = self.state, self.content
        entry = s.world.tavern_chatter.get(request.place)
        if entry is not None and entry[0] >= request.asked_at and not tavern_rules.chatter_due(s.world, c, request.place):
            return False
        s.world.tavern_chatter[request.place] = (s.world.time, list(lines))
        self._save_season()
        return bool(lines)

    def tavern_ask_request(self, text: str) -> tavern_rules.AskRequest | list[str]:
        """A 段（鎖內、只讀）：酒肆開著、問句合格、付得起，就開一張單（問到秘密的單子標 secret，B 段不叫模型）；不然回那一句拒絕。"""
        s, c = self.state, self.content
        if not self._tavern_open():
            return [equipment.NOT_NOW]
        q = str(text or "").strip()
        problem = tavern_rules.ask_problem(c, q)
        if problem is None:
            problem = tavern_rules.pay_problem(s, self._tavern_price(c.config.tavern.ask_price))
        if problem is not None:
            return [problem]
        secret = tavern_rules.secret_asked(q)
        facts, kinds = ((), ()) if secret else self._tavern_ask_facts(q)
        return tavern_rules.AskRequest(name=s.player.name, place=s.player.location, sign=tavern_rules.sign(s, c), question=q,
                                       facts=facts, secret=secret, kinds=kinds)

    def tavern_ask(self, text: str, reply: str | None, request: tavern_rules.AskRequest | None = None) -> list[str]:
        """C 段：重驗（酒肆還開著、還在同一間、同一句），回話再過一次 ask_clean（照此刻的清單），然後收錢寫紀錄。"""
        if not self._tavern_open():
            return self._log([equipment.NOT_NOW])
        q = str(text or "").strip()
        ok = request is not None and request.place == self.state.player.location and request.question == q
        self._tavern_reply = reply if ok else None
        try:
            return self._log(self._tavern_run("ask", text=q))
        finally:
            self._tavern_reply = None

    def _tavern_ask(self, text: str) -> list[str]:
        s, c = self.state, self.content
        cfg = c.config.tavern
        q = text.strip()
        problem = tavern_rules.ask_problem(c, q)
        if problem is not None:
            self._shop_after(problem, "refused")
            return [problem]
        if tavern_rules.secret_asked(q):
            half = max(0, cfg.ask_price // 2)
            if self._tavern_charge(half) is None:
                return self._tavern_short(half)
            lines = [tavern_rules.ASK_YOU.format(q=q), tavern_rules.ASK_SECRET]
            tavern_rules.add_note(s, c, "ask", tavern_rules.ASK_TITLE, lines)
            self._shop_say("nothing")
            return lines
        if self._tavern_charge(cfg.ask_price) is None:
            return self._tavern_short(cfg.ask_price)
        facts, kinds = self._tavern_ask_facts(q)
        req = tavern_rules.AskRequest(name=s.player.name, place=s.player.location, sign=tavern_rules.sign(s, c), question=q,
                                      facts=facts, kinds=kinds)
        reply = getattr(self, "_tavern_reply", None)  # B 段寫好的（tavern_ask 放的）；直接呼叫沒有 B 段，當叫不動
        reply = tavern_rules.ask_clean(reply, req) if reply else None
        if reply is None:
            tavern_rules.pay(s, -self._tavern_price(cfg.ask_price))  # 叫不動模型：退全額
            self._shop_say("nothing")
            return [tavern_rules.ASK_BUSY]
        lines = [tavern_rules.ASK_YOU.format(q=q), tavern_rules.ASK_HIM.format(a=reply)]
        if tavern_rules.unsure(reply):  # 酒家說不上來：退一半，指一條路（企劃者 2026-10-27）
            refund = self._tavern_price(cfg.ask_price) // 2
            tavern_rules.pay(s, -refund)
            lines.append(tavern_rules.ASK_UNSURE.format(refund=refund, tip=tavern_ask.pointer(list(kinds))))
        tavern_rules.add_note(s, c, "ask", tavern_rules.ASK_TITLE, lines)
        self._shop_say("asked")
        return lines

    def _deliver_whispers(self) -> None:
        """酒肆的風聲（有人打聽你）：季上那幾則搬到身上，寫一則「風聲」紀錄。"""
        lines = tavern_rules.collect_whispers(self.state, self.content)
        if lines:
            self._write(tavern_rules.WHISPER_TITLE, lines)
            self._save_season()

    def tavern_view(self) -> dict:
        """酒肆那一頁（Game.shop_view 在酒肆開著時給）：招牌、銀兩、酒家那一句、出店、價錢、剛問到的、座上客、鄰桌閒談、題壁、
        請酒的人、記下的名號、素材清單、收到的風聲。只讀。"""
        s, c = self.state, self.content
        p, cfg = s.player, c.config.tavern
        loc = p.location
        guests = [o.player.name for o in social.here(self)]
        treat = tavern_rules.treat_shown(s.world, c, loc)
        prices = {k: self._tavern_price(getattr(cfg, f"{k}_price")) for k in ("news", "seek", "ties", "wall", "treat", "hide", "trace", "ask")}
        mats = []
        for m in sorted(c.materials.values(), key=lambda m: (m.tier, shopview.attribute_rank(m.attribute), m.id)):
            base = cfg.material_prices.get(m.tier, max(cfg.material_prices.values()))
            mats.append({"id": m.id, "name": m.name, "tier": m.tier, "attribute": m.attribute, "price": self._tavern_price(base)})
        hour = int(s.world.time // HOUR)
        me = name_key(p.name)
        hits = {
            "tiers": [{"tier": i, "name": tavern_rules.hit_tier_name(i), "price": self._tavern_price(base)}
                      for i, base in enumerate(cfg.hit_prices)],
            "hush": self._tavern_price(cfg.hush_price),
            "guard": self._tavern_price(cfg.guard_price),
            "guard_problem": self._tavern_guard_problem(),
            "mine": [tavern_rules.HIT_ACTIVE.format(name=h.target, tier=tavern_rules.hit_tier_name(h.tier), until=self._real_stamp(h.until_real))
                     for h in s.world.tavern_hits if not h.done and name_key(h.client) == me and h.until_real > self.now],
            "ended": bool(s.world.ended),
            "streaks": [tavern_rules.HIT_STREAK.format(name=n, n=k, pct=round(cfg.hit_fail_price_step * k * 100))
                        for n in p.tavern_known if (k := tavern_rules.hit_streak(s.world, p.name, n, cfg.hit_fail_max))],
        }
        return {
            "shop": "tavern",
            "hits": hits,
            "sign": tavern_rules.sign(s, c),
            "silver": p.stats.get("silver", 0),
            "line": shopview.line_text(s, c, "tavern"),
            "back": tavern_rules.BACK_ID,
            "prices": prices,
            "problems": {"treat": self._tavern_treat_problem(), "hide": self._tavern_hide_problem()},
            "notes": [{"kind": n.kind, "title": n.title, "lines": list(n.lines), "when": self.stamp(n.time)}
                      for n in reversed(p.tavern_notes)],
            "guests": guests[:6],
            "more_guests": max(0, len(guests) - 6),
            "treat": tavern_rules.TREAT_SEEN.format(name=treat) if treat else "",
            "chatter": [{"who": who, "said": said} for who, said in tavern_rules.chatter(c, loc, hour, s.world)],
            "walls": [{"who": w.who, "text": w.text, "when": self.stamp(w.time)} for w in reversed(s.world.tavern_walls.get(loc, []))],
            "wall_chars": cfg.wall_chars,
            "ask_chars": cfg.ask_chars,
            "watch": {"price": self._tavern_price(int(round(cfg.seek_price * cfg.watch_share))),
                      "mine": [tavern_rules.WATCH_ACTIVE.format(name=w.target, until=self._real_stamp(w.until_real))
                               for w in p.tavern_watches if w.until_real > self.now]},
            "known": list(reversed(p.tavern_known)),
            "materials": mats,
            "whispers": tavern_rules.whisper_view(c, s),
            "hidden": tavern_rules.HIDE_ALREADY.format(when=self.stamp(p.hidden_until)) if p.hidden_until > s.world.time else "",
            "board": tavern_rules.BOARD_ID if bounties.board_here(s, c) and bounties.visible(s, c) else "",
        }

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
        if option_id == "act:train" and self.duel_on():
            return None  # 約戰開著：出陣那一格是貼約戰（或截糧，不判大場面）
        if option_id == "act:train":
            pick = self._train_pick(c.locations[s.player.location])
            return None if pick is None or self._drills_with(pick) else pick  # 遇上自己人是操練，不打架
        if option_id.startswith("act:challenge:"):
            fid = option_id.removeprefix("act:challenge:")
            return self._figure_squad(fid) if fid in c.figures else None  # 難度照他此刻的聲威（T4）與江湖水漲
        if kind == "choice" and arg.isdecimal() and s.pending_event:
            choices = c.events[s.pending_event].choices
            combat = choices[int(arg)].combat if int(arg) < len(choices) else None
            return self._story_squad(c.squads[combat]) if combat else None
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
            # 本人那一行名號後面寫性別（女的寫「（女子）」，模型寫過程時稱呼跟著換；PM 2026-10-12），同伴照舊
            ours=[fight_llm.member_line(name + ("（女子）" if i == 0 and gender.female(s) else ""), arts)
                  for i, (name, *arts) in enumerate(team.lineup(s, self.content, self.world))],
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

    def _terrain_note(self) -> list[str]:
        """地利（武學隨地理環境）在戰報裡含蓄的一句：本人身上那兩門跟此地最濃的意境同一路或被它剋，或只有出戰同伴對上
        （terrain.note）；打贏打輸都寫，不寫倍數。開關關著、在路上、這裡沒有最濃的意境什麼都不說。"""
        strong = terrain.here(self.state, self.content)
        if strong is None:
            return []
        mine, mates = team.terrain_attributes(self.state, self.content, self.world)
        return terrain.note(self.content, strong, mine, mates)

    @staticmethod
    def _narrate(record, result: encounter.EncounterResult, judged: fight_llm.Judgment | None) -> None:
        """大場面的過程照結果挑一版：大勝、險勝是佔上風那一版，僵持、落敗是落下風那一版（計畫三 G15）。"""
        if judged is not None:
            record.narration = judged.winning if result.tier in team.WIN_TIERS else judged.losing

    def choose(
        self, option_id: str, prepared: companion_agent.PreparedTurn | None = None,
        fight: fight_llm.PreparedFight | None = None, text: str | None = None,
    ) -> list[str]:
        """text 只有「自己說」（SAY_OPTION）用：玩家打的那一句；沒給（或過不了 say_text）就只回一句叫他寫，不花體力、不算輪數。
        prepared 是 server.py 在鎖外先生成好的一輪對話（見 dialogue_request／companion_agent.prepare_turn）；
        只有對話選項用得到，進來先重驗，驗不過就忽略。
        fight 是 server.py 在鎖外先判讀好的大場面（見 fight_request／fight_llm.judge）：一樣先重驗（_checked_fight），
        驗不過就忽略、照平常打（優勢 0）。假人、整季機器人不帶，大場面也是優勢 0、照平常演出（武學與成長設計 8.3）。
        不過等判讀的時候這個選項已經不在選單上了（人被帶走、事件被了結）就不打：回一句話說這一仗沒打成（_fight_gone），
        不寫戰報也不寫江湖紀錄（跟其他的拒絕一樣）。"""
        if option_id == step_rules.NEXT and step_rules.on(self):  # 本週卡「換一件事」（減法季批 3c）：不在選單上（假人碰不到）、
            return step_rules.skip(self)  # 不花體力、不寫江湖紀錄；關著的季照舊當成不在選單上
        if option_id.startswith(sortie_duel.PREFIX) and self.duel_on():  # 出陣約戰（減法季批 3b）：貼、應戰、同去不在選單上（封招的組合放不進選單），
            return self._duel_choice(option_id)  # 各自在 world.mutate 裡重驗；關著的季照舊當成不在選單上
        if option_id.startswith(zhuan_end.PREFIX) and any(o.id == option_id and o.enabled for o in self.options(odds=False)):
            return self._log(self._zhuan_act(option_id))  # 休季用列傳的票（減法季批 7b）：不走行動那一串（季收了，不推大勢、不存季）
        option = {o.id: o for o in self.options(odds=False)}.get(option_id)
        if option is None and option_id.startswith(wins.LEAN_PREFIX):
            option = self._lean_anytime(option_id)  # 「改幫…」隨時都能換（設計 3.2）：在路上、決戰的大區選單上沒有它，照樣收
            if option is not None and self.state.pending_event is not None:
                # 唯一的例外：有事件待選時不收（FB-820，PM 2026-10-26）——不然同一則事件裡依陣營出現的選項兩邊都挑得到。
                # 回一句（Refused：伺服器傳去網頁跳提示），什麼都不動、不寫江湖紀錄
                return Refused(self._log([wins.LEAN_EVENT_PENDING]))
        if option is None and option_id.startswith("bounty:"):
            # FB-162：懸賞選項已經不在選單上（兩個分頁搶同一張，慢的那一頁）：回這一步為什麼不成的那一句，不寫江湖紀錄；
            # 回傳值是 Refused，伺服器照它把同一句傳去網頁跳提示（server.api_choose）
            return Refused(self._log([bounties.stale_line(self.state, self.content, self.world, option_id.partition(":")[2])]))
        if (option is None or not option.enabled) and option_id.startswith("market:"):
            # FB-195：馬市的選項已經不在選單上或灰掉了（兩個分頁搶，慢的那一頁的鈕還亮著）：同懸賞榜 FB-162，回為什麼不成的那一句
            # （Refused，伺服器傳去網頁跳提示），馬販那一句換成那個原因；不寫江湖紀錄
            problem = mounts.stale_problem(self.state, self.content, option_id.partition(":")[2])
            if self._shop_open() == "market":  # 已經出了馬市、進了別的店（另一個分頁）：不改那一間店掌櫃的話（終審 M1）
                self._shop_after(problem, "refused")
            return Refused(self._log([problem if problem == mounts.STALE else f"（{problem}。）"]))
        if option is None and option_id.startswith("act:recruit:"):
            # FB-363：兩個分頁搶，慢的那一頁的招募鈕還在、他已經被別人招走了：同懸賞榜 FB-162 回那一句（Refused，網頁跳提示），
            # 不扣體力、不寫江湖紀錄。不在這裡、陣營不合這類原因照舊「此刻無法這麼做」
            cid = option_id.removeprefix("act:recruit:")
            owner = roster.owned_by(self.world, cid) if cid in self.content.characters else None
            if owner is not None and not roster.owns(owner, self.state.player.name):
                return Refused(self._log([roster.TAKEN.format(name=self.content.characters[cid].name, owner=owner)]))
        if option is not None and not option.enabled and option_id.startswith("arena:fight:"):
            # Joy 2026-10-16「看不出還有多久才能打」：按到灰掉的挑擂鈕（兩個分頁、畫面還沒重抓）回為什麼不成、還要等多久，不寫江湖紀錄
            foe = self.state.world.arena.get(option_id.removeprefix("arena:fight:"))
            problem = foe and arena.challenge_problem(self.state.world, self.state.player.name, foe, self.content.config.arena,
                                                      self.arena_left(), self.content.config.time_scale)
            if problem:
                return Refused([f"（{problem}。）"])
        if option is None or not option.enabled:
            return self._log([self._fight_gone(fight) if fight is not None else "（此刻無法這麼做。）"])
        faction_before = self.state.player.faction  # 這一下才投靠的人才開始入伍段（見 _begin_enlistment）
        self.state.battle_card = None
        self.state.player.guide_done = []  # 對話框上一次完成的那幾行，下一次行動就清掉
        kind, _, arg = option_id.partition(":")
        if kind == "battle":  # 決戰選項不走 Draft：加入與趕到由 _battle_choose 自己寫一則紀錄，每回合的出招不寫（FB-030）
            return self._log(self._battle_choose(arg))
        if kind == "seal":  # 奪璽單挑：每回合的出招不寫紀錄，收場由 _deliver_seal_results 補一份戰報與一則紀錄（5.9）
            return self._log(self._seal_act(arg))
        if kind == "duel":  # 頭目戰同決戰：每回合的出招不寫紀錄，分出勝負那一下由 _duel_finish 寫一則、一份戰報
            return self._log(self._duel_act(arg))
        if kind == "arena" and (arg in MOVES or option_id == ARENA_YIELD):  # 擂台同頭目戰：收場那一下由 _arena_finish 寫一則、一份戰報
            return self._log(self._arena_act(arg))
        if option_id == FREE_TEXT_OPTION:
            return self._log([f"（寫下你的做法，{FREE_TEXT_MAX} 字以內。）"])  # 選項本身只叫出輸入框，不消耗事件
        if kind == "errand" and arg.startswith("persuade:") and self._persuade_said is None:
            return self._log([errand_rules.PERSUADE_ASK])  # 勸降（減法季批 6）：選項本身只叫出輸入框，送出走 persuade_request／persuade
        if option_id == sensing.DRAW:
            return self._log(["（在畫布上一筆畫下心中的形。）"])  # 只叫出畫布；畫完送出走 sense_request／sense_draw
        if option_id == explore_modes.SAY_ID and self._gather_said is None:
            return self._log([explore_modes.SAY_BAD])  # 找素材的「自己說」：選項本身只叫出輸入框，送出走 gather_text_request／gather_say
        said = say_text(text, self.say_max()) if option_id in TEXT_TALKS else None
        if option_id in TEXT_TALKS and said is None:
            return self._log([f"（寫下你想說的話，{self.say_max()} 字以內。）"])  # 選項本身只叫出輸入框
        prepared = self._checked_prepared(option_id, prepared, text) if kind in ("act", "talk", "call", "parley") else None
        self._fight = self._checked_fight(option_id, fight)
        was_opening = kind == "choice" and opening_rules.pending(self.state, self.content)  # 開局三選一（減法季批 7）：選完人物的信到
        # 搬成包的功能：那一包接走（只吃自己前綴的 id；這一下江湖紀錄的標題在動作之前先拿，同 _action_title；開發規範手冊 3.3）
        taken = features_core.choose(self, kind, arg)
        self._draft = Draft(taken.title if taken is not None else self._action_title(kind, arg))
        self._affinity_before = dict(self.state.player.affinities)
        stamina = self.state.player.stamina
        try:
            if taken is not None:
                msgs = taken.run()
            elif kind == "act":
                msgs = self._act(arg, prepared)
            elif kind == "move":
                msgs = self._move(arg)
            elif kind == "talk":
                msgs = self._talk(arg, prepared, said)
            elif option_id == ROAD_SAY:
                msgs = self._road_say(prepared, said)
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
            elif kind == "invite":
                msgs = self._invite(arg)
            elif kind == "bounty":
                msgs = self._bounty(arg)
            elif kind == "smith":
                msgs = self._smith(arg)
            elif kind == "market":
                msgs = self._market(arg)
            elif kind == "donate":
                msgs = self._donate_choice(arg)
            elif kind == "tavern":
                msgs = self._tavern_choice(arg)
            elif kind == "arena":
                msgs = self._arena(arg)
            elif kind == "explore":
                msgs = self._explore_mode(arg)
            elif kind == "sect":  # 拜入門派（一類一顆，_sect_options）：端出那一則事件，不花體力
                msgs = self._present(self.content.events[arg], "sect")
            elif kind == "dadian":  # 打點那一間店的「離開」
                self._close_dadian()
                msgs = [silver.SHOP_CLOSED]
            elif kind == "ambush":
                msgs = self._ambush_act(arg)
            elif kind == "works":
                msgs = self._works_act(arg)
            elif kind == "aid":
                msgs = self._aid_act(arg)
            elif kind == "plan":
                msgs = self._plan_act(arg)
            elif kind == "errand":
                msgs = self._errand_act(arg)
            elif kind == storyline.OPTION:
                msgs = self._story_act(arg)
            elif kind == epiphany.OPTION:
                msgs = self._epiphany_name(arg, text)
            else:
                msgs = self._choose(int(arg))
            # 三選一開著時按「探索」本身（_act 只回 PICK）：不算探索過、不寫紀錄。要在後面接上大勢門檻、召見那些訊息之前記
            # 找素材分支的入口（第 32 項）也一樣：按「找素材」本身只回 GATHER_PICK、展開分支
            picked_only = (kind == "act" and arg == "explore" and msgs == [explore_modes.PICK]) or (
                kind == "explore" and msgs == [explore_modes.GATHER_PICK]) or (
                kind == "act" and arg == "train" and msgs == [sortie_duel.PICK])  # 約戰開著時按出陣那一格只是打開出陣前那張卡（減法季批 3b）
            if faction_before is None and self.state.player.faction is not None:
                msgs += self._join_lean()  # 三陣營四勝利：拜入曹氏莊院而投靠的那一下照門派所在地給傾向（關著什麼都不做）
            self._begin_enlistment(faction_before)  # 投靠（或拜入陣營名下的門派）那一下：入伍段開始，同一下不算完成任何一步
            self._greet_rejoin(faction_before)  # 入伍段早就走完的人再投靠：引薦人打個招呼（新手引導計畫三）
            if faction_before is None and self.state.player.faction is not None:  # 這一下才投靠（確認，或拜入陣營名下的門派）：手上新陣營接不了的懸賞作廢、說一聲（FB-151）；叛投在 defection.defect 裡做
                msgs += bounties.drop_stranded(self.state, self.content, self._side())
            msgs += self._hear_after_stamina(stamina)
            if kind == "choice":  # 選了事件的選項：序章的遇險、拜師、四景（新手引導計畫一）
                msgs += self._guide(note_action(self.state, self.content, self.world, "choice"))
            if was_opening and not opening_rules.pending(self.state, self.content):  # 開局第一分鐘：那位人物開口、託付第一件事（信附委託）
                msgs += opening_rules.deliver(self.state, self.content)
            if kind == "act" and arg != "break" and not picked_only:
                msgs += self._guide(note_action(self.state, self.content, self.world, arg))
                if arg in SHOP_ACTS:  # 初入江湖「進城裡的鋪子看看」：進哪一間都算（新手引導第四段）
                    msgs += self._guide(note_action(self.state, self.content, self.world, "shop"))
            if kind == "explore" and not picked_only:  # 探索三選一的三種都算探索過（找素材分支的入口那一下不算）
                msgs += self._guide(note_action(self.state, self.content, self.world, "explore"))
                card = next((r for r in self.state.battles if r.id == self.state.battle_card), None)
                if arg == explore_modes.PRACTICE and card is not None and card.tier in team.WIN_TIERS:  # 城外練功打贏（新手引導重做）
                    msgs += self._guide(note_action(self.state, self.content, self.world, "field_win"))
            if option_id in LEAVE_SHOP_IDS:  # 出店（進了店再出來，新手引導重做：出了店下一步才不會被店面蓋住）
                msgs += self._guide(note_action(self.state, self.content, self.world, "leave_shop"))
            if kind == "call" and arg != "back":
                msgs += self._guide(note_action(self.state, self.content, self.world, "socialize"))  # 指名求見算一次交友
            # 名將贈禮（裝備四欄 6.4）與本命兵器（打造第三批）：這一下的情誼（對話、事件）到了門檻就送；另起一則「名將贈禮」，
            # 不接在當下這個動作的紀錄裡（FB-139、FB-149：名將多半不在場，也跟那件事無關），排在這一則之後（「剛剛」看得到）
            gifts = self._general_gifts() + self._signature_arms()
            msgs += check_thresholds(self.state, self.content, self.world, self._quick_client(), now=self.now)
            msgs += self._settle_plots()  # 參與過的密謀收場了：各自結算一次（正式版乙二）
            msgs += self._story_tick()  # 一條線：這一下做成的事、過了的期限往下走（關著是空的）
            msgs += ranks.check_summons(self.state, self.content)  # 貢獻跨過門檻就發召見（計畫 T5）
            msgs += self._report_seat()  # 第四階席次：抄帳、補缺（正式版丁）；這個動作結束時 _save_season 一起存
            if not picked_only:  # 只按「探索」展開三顆（什麼都沒做）：排著的提示留到下一個真的動作再上框，這一下才不必寫紀錄
                self._check_hints()  # 這一下碰到的新玩法排一條提示；事件了結、引導或入伍段走完的這一下，排著的上框。記在這一則的 guide（新手引導計畫三）
            # 打造的每一步（挑種類、主料、輔料、開爐、上一步、不打了）併成一則「打造」：一爐一則，不是一步一則。
            # 打開單子那一步（"forge"）不併、另起一則：_mergeable_head 只看最新一則是不是同標題，不然連打兩爐（或打開又不打了）
            # 會全部併進上一爐那一則。懸賞榜：打開榜那一則的標題是「懸賞榜・此地」，每次來都另起一則；挑一件、回到懸賞榜只是翻頁，
            # 只有那一句回話時不寫紀錄（bounties.is_browse_line）；交出、揭下、放棄、返回各一則（FB-161：交出不再跟挑、回併成一則，
            # 連交幾張時各寫各的得失）
            entry = self._draft.entry(self.state.world.time, msgs)
            # 鐵匠鋪切頁（裝備四欄設計 4.6）只是換一頁：沒有別的事（訊息、數值變化、引導）就不寫紀錄，不然每切一次多一則「鐵匠鋪」
            quiet = kind == "smith" and arg.startswith("page:") and not (entry.lines or entry.changes or entry.guide)
            quiet = quiet or (kind == "bounty" and arg.partition(":")[0] in bounties.BROWSE_VERBS and not (entry.changes or entry.guide)
                              and all(bounties.is_browse_line(line) for line in entry.lines))
            quiet = quiet or (picked_only and entry.lines in ([explore_modes.PICK], [explore_modes.GATHER_PICK], [sortie_duel.PICK])
                              and not (entry.changes or entry.guide))
            if not quiet:
                # FB-141：開爐成了（_smith_act 打完把單子收起來了）那一下併進「打造」那一則時只留結果——結果句排第一，375 寬「剛剛」
                # 收著時看得到；挑種類、主料、輔料的回報收掉（放了哪兩樣、哪一種，結果句「打出一把【…】（種類・屬…）」
                # 本身寫了）。開爐沒成（單子還在）、上一步、不打了照舊接在後面。收掉的只有單子自己的回話（smithing.is_step_line）：
                # 前幾步順便帶來的別的話（大勢門檻的消息、召見之類）接在結果句後面留著（終審 M3）
                forged = kind == "smith" and arg.partition(":")[0] == smithing.GO_VERB and self.state.player.smith_draft is None
                journal.add_entry(self.state, entry, merge=kind == "smith" and smithing.is_forge_step(arg) and arg != "forge",
                                  fold=smithing.is_step_line if forged else False)
            self._gift_entry(gifts)
            msgs += gifts
        finally:
            self._draft = None
            self._fight = None
            self._affinity_before = None
        self._record_faction()
        msgs += self._tavern_hit_check()  # 酒肆：有人雇了殺手找你，你剛在城外做完一件事（設計第六節）
        self._save_season()
        return self._log(msgs)

    def gather_text_request(self, text: str) -> explore_modes.GatherTextRequest | list[str]:
        """找素材「自己說」的 A 段（server.gather_text 在行動鎖內、很快地呼叫；只讀）：選單上「自己說…」按得下去（有分支層、
        體力夠、開關開著）、字是 1～20 字，就開單（地點、第幾次探索、那一句、模型可以挑的屬性）；不行回拒絕的話。"""
        if self.world.paused_at() is not None:
            return [f"（{PAUSED_TEXT}。）"]
        said = explore_modes.say_text(text)
        if said is None:
            return [explore_modes.SAY_BAD]
        option = {o.id: o for o in self.options(odds=False, tick=False)}.get(explore_modes.SAY_ID)
        if option is None or not option.enabled:
            return [explore_modes.SAY_NONE]
        c, p = self.content, self.state.player
        loc = c.locations[p.location]
        return explore_modes.GatherTextRequest(
            location=loc.id, place=loc.name, tags=list(loc.tags), seq=p.explore_seq, text=zh.to_traditional(said),
            choices=explore_modes.say_choices(c, loc),
        )

    def gather_say(
        self, request: explore_modes.GatherTextRequest, rate: int | None = None, attribute: str | None = None,
    ) -> list[str]:
        """找素材「自己說」的 C 段（鎖內）：重驗同一個地點、同一個 explore_seq（中間沒做別的探索）、同一句、還按得下去，才扣體力走
        找素材那一支（choose(SAY_ID)：殘譜、回體丹、打探、破境丹與紀錄照舊）。rate 是鎖外評好的 0～100（再夾一次），沒給
        （直接呼叫的測試、腳本）就在這裡用 _quick_client 評、評不到 40；屬性不在單子的清單裡換成第一個（第一條分支的第一種）。"""
        now = self.gather_text_request(request.text)
        if isinstance(now, list):
            return self._log(now)
        if (now.location, now.seq, now.text) != (request.location, request.seq, request.text):
            return self._log([explore_modes.SAY_GONE])
        if rate is None:
            rate, attribute = gather_llm.score(self._quick_client(), now)
        attribute = attribute if attribute in now.choices else now.choices[0]
        self._gather_said = (now.text, max(0, min(100, int(rate))), attribute)
        try:
            return self.choose(explore_modes.SAY_ID)
        finally:
            self._gather_said = None

    def free_text_request(self, text: str) -> FreeTextRequest | None:
        """隨口應對的階段 A（server.py 在行動鎖內、很快地呼叫）：眼前的事件可以隨口應對、寫的字是 1～20 字，
        就回傳要在鎖外送模型評估的單子；不行就是 None。只讀、不改狀態，也不推進戰鬥（理由同 dialogue_request）。"""
        text = text.strip()
        event_id = self.state.pending_event
        if not text or len(text) > FREE_TEXT_MAX or event_id is None:
            return None
        if FREE_TEXT_OPTION not in {o.id for o in self.options(odds=False, tick=False) if o.enabled}:
            return None
        branches = self._branches(self.content.events[event_id])
        return FreeTextRequest(event_id=event_id, text=text, outcomes=outcome_rules.tags(branches) if branches else [])

    def _free_text_of(self, event: Event) -> FreeTextChoice | None:
        """這則事件此刻有沒有「隨口應對」那一顆：寫了 free_text，而且不是只在分岔開著時才有的那一種（outcomes_only，人拉犁；PM 2026-10-25
        第 7 件）——那一種在關著的季沒有這一顆，選單、輸入框的提示語、新手提示都照沒有。"""
        free = event.free_text
        if free is None or (free.outcomes_only and not jianfa(self.content, self.state.world, "free_text_outcomes")):
            return None
        return free

    def _branches(self, event: Event) -> list[Outcome]:
        """這一則的隨口應對此刻照分岔走嗎（減法季批 4，整合設計 5.1）：子開關 free_text_outcomes 開著（加上這一季的章）、事件寫了後果，
        是那幾種後果（最後一種是 fallback）；其餘是空的，照舊用 stat、effect、fail_effect。"""
        free = self._free_text_of(event)
        if free is None or not free.outcomes or not jianfa(self.content, self.state.world, "free_text_outcomes"):
            return []
        return free.outcomes

    def answer_event(
        self, request: FreeTextRequest, llm_rate: int | None = None, moral: str | None = None, outcome: str | None = None,
    ) -> list[str]:
        """隨口應對的階段 C（鎖內）：重驗還停在同一則事件、寫的是同一句話，才算成功率、擲骰、套用效果。
        llm_rate 是鎖外評好的 0～100、moral 是同一次評出來的善惡（event_llm.MORALS）；llm_rate 沒給（直接呼叫的測試、腳本）
        就在這裡評（行動鎖內，用 _quick_client 的短逾時複本），評不到一樣退回 40、善惡當「中」。
        成功率＝LLM 評分加屬性修正、夾在 5～85（rules.free_text_rate）；擲骰用引擎自己的 rng。
        善惡再驗一次（event_llm.moral_of：不是那三個字當「中」）。判成「惡」而且擲中了（FB-223）：成功效果換成惡行的版本
        （rules.evil_success：善名換惡名、扣惡名與加情誼拿掉、結果句換成 rules.EVIL_DONE），潤色照惡行寫（FreeTextOutcome.evil）；
        「善」「中」、或「惡」沒擲中，一個字都不變。
        分岔開著、這則事件寫了後果（_branches）時改走 _answer_branch（outcome 是 B 段歸好的那一種的 id）；關著的季 outcome 不理。"""
        s, c = self.state, self.content
        self.last_gamble = None
        current = self.free_text_request(request.text)
        if current is None or current.event_id != request.event_id:
            return self._log(["（事情已經過去了，這句話沒派上用場。）"])
        event = c.events[request.event_id]
        storyline.heard(s, c, event.id, request.text)  # 一條線的段落：自己寫的那一句記進那條線（結尾與模型用）
        branches = self._branches(event)
        if branches:
            return self._answer_branch(event, request, branches, llm_rate, moral, outcome)
        choice = event.free_text
        if llm_rate is None:
            # 判善惡那一次照 _quick_client 的額度：評分失敗用掉了額度就不叫、當「中」
            verdict = event_llm.judge_event_gamble(self._quick_client(), event, request.text, moral_client=self._quick_client)
            llm_rate = verdict.rate
            moral = verdict.moral if moral is None else moral
        moral = event_llm.moral_of(moral)
        self.state.battle_card = None
        faction_before = s.player.faction
        self._draft = Draft(f"{event.title}・隨口應對")
        self._affinity_before = dict(s.player.affinities)
        try:
            s.pending_event = None
            rate = free_text_rate(llm_rate, choice, s, c, self.world)
            success = self.rng.random() * 100 < rate
            evil = success and moral == event_llm.MORAL_EVIL  # 惡行而且成了（FB-223）；善惡不碰 rng
            tag, line = check_result_line(success)  # 一律是本人：不寫誰出手
            msgs = [f"你：「{request.text}」（{rate_words(rate)}）", line]
            self._outcome(tag, line)
            # 行狀：隨口應對是自己的話，一律記；一次性的事、奇遇份量重一些。惡行成了照實寫（EVIL_ANNAL）
            done = EVIL_ANNAL if evil else "，成了。" if success else "，沒成。"
            annals.note(s, c, annals.DEED, f"遇上{'奇遇' if event.qiyu else ''}【{event.title}】，隨口應對{done}",
                        3 if event.once or event.qiyu else 1, quote=request.text)
            if evil:
                effect = evil_success(choice.effect)
            else:
                effect = choice.effect if success else failed(choice.fail_effect, c)  # 失手另扣的體力減半（體力平衡提案）
            msgs += self._apply(effect, once=event.once)
            msgs += self._event_progress()  # 領地爭奪：隨口應對了結也推一次進度（開關關著是空的）
            self._begin_enlistment(faction_before)  # 隨口應對的結果也可能拜入門派
            self._greet_rejoin(faction_before)  # 同樣：入伍段早就走完的人拜入門派，引薦人打個招呼（新手引導計畫三）
            gifts = self._general_gifts() + self._signature_arms()  # 隨口應對的效果也可能加情誼（同 choose：另起一則）
            msgs += check_thresholds(s, c, self.world, self._quick_client(), now=self.now)
            msgs += self._report_seat()  # 隨口應對的效果也可能推大勢、記貢獻：第四階席次的帳在這裡也抄（正式版丁）
            self._check_hints()  # 隨口應對了結了事件：同選項一樣，碰到的新玩法排一條、排著的上框（新手引導計畫三）
            journal.add_entry(s, self._draft.entry(s.world.time, msgs))
            self._gift_entry(gifts)
            msgs += gifts
            self.last_gamble = FreeTextOutcome(
                event_id=event.id, text=request.text, success=success, effect_text=fill_marks(effect.text, s),
                time=s.world.time, title=self._draft.title, evil=evil,
            )
        finally:
            self._draft = None
            self._affinity_before = None
        self._record_faction()
        self._save_season()
        return self._log(msgs)

    def _answer_branch(
        self, event: Event, request: FreeTextRequest, branches: list[Outcome], llm_rate: int | None, moral: str | None,
        outcome: str | None,
    ) -> list[str]:
        """隨口應對分岔的 C 段（減法季批 4；整合設計 5.1、5.9，主機側計畫 Task 4-2）：照 outcomes.plan 分四條走——
        check 照那一種的檢定擲骰（self.rng；成功率比的是那一種的難度，outcomes.rate）、成套 effect 敗套 fail_effect；combat 照固定選項開打
        （_event_battle），贏套 effect、輸套 fail_effect；cost 掏銀兩、必成（不夠就回 NOT_ENOUGH_SILVER、不做、不扣次數，事件還停著）；
        最後一種（fallback）只套那一句。outcome 是 B 段歸好的 id（不在清單一律最後一種）；llm_rate 沒給（直接呼叫的測試、腳本）就在鎖內
        自己歸類（event_llm.judge_outcome，_quick_client 的額度）。
        善惡（FB-223）只在歸到最後一種時照舊看模型的評分（判「惡」就是惡行成了：rules.evil_success）；選中別的後果時只看那一種自己的效果
        （作惡那一種本來就扣善名），同一句話不加兩次（PM 2026-10-25 第 8 件）。成了的後果記貢獻（_deed_credit）。
        行狀只寫後果的類名，不存玩家寫的句子（公開的只有後果與痕跡）；江湖紀錄是自己的，照舊寫那一句，括號裡多寫類名。"""
        s, c = self.state, self.content
        if llm_rate is None:
            verdict = event_llm.judge_outcome(self._quick_client(), event, branches, request.text, moral_client=self._quick_client)
            llm_rate, outcome = verdict.rate, verdict.outcome
            moral = verdict.moral if moral is None else moral
        plan = outcome_rules.plan(branches, outcome, llm_rate, s, c, self.world)
        chosen = plan.outcome
        problem = outcome_rules.cost_problem(chosen, s) if plan.way == "cost" else ""
        if problem:
            return self._log([problem])
        fallback = plan.way == "fallback"
        moral = event_llm.moral_of(moral) if fallback else event_llm.MORAL_NEUTRAL
        # 類名（短名）寫進紀錄的括號與行狀；歸到最後一種（走開）不寫類名，照關著時的寫法（FB-800，PM 2026-10-25：紀錄與行狀
        # 「隨口應對，行了一件惡事，成了。」不寫成「隨口應對：走開，…」；判善、判中也不寫）
        name = "" if fallback else outcome_rules.kind_name(chosen)
        s.battle_card = None
        faction_before = s.player.faction
        self._draft = Draft(f"{event.title}・隨口應對")
        self._affinity_before = dict(s.player.affinities)
        try:
            s.pending_event = None
            evil = False
            if plan.way == "check":
                success = self.rng.random() * 100 < plan.rate
                tag, line = check_result_line(success)  # 一律是本人：不寫誰出手
                msgs = [f"你：「{request.text}」（{name}・{rate_words(plan.rate)}）", line]
                self._outcome(tag, line)
                effect = chosen.effect if success else failed(chosen.fail_effect, c)
                msgs += self._apply(effect, once=event.once)
            elif plan.way == "combat":
                msgs = [f"你：「{request.text}」（{name}）"]
                msgs += self._event_battle(event, outcome_rules.as_choice(chosen))  # 效果在打完那一刻照勝負套
                success = s.battles[0].tier in team.WIN_TIERS
                effect = chosen.effect if success else failed(chosen.fail_effect, c)
            else:  # 掏錢的、最後一種：不擲骰、必成
                success = True
                evil = fallback and moral == event_llm.MORAL_EVIL
                effect = evil_success(chosen.effect) if evil else outcome_rules.paid(chosen)
                msgs = [f"你：「{request.text}」" + (f"（{name}）" if name else "")]
                msgs += self._apply(effect, once=event.once)
            self._deed_credit(chosen, success)
            done = EVIL_ANNAL if evil else "。" if fallback else "，成了。" if success else "，沒成。"
            annals.note(s, c, annals.DEED, f"遇上{'奇遇' if event.qiyu else ''}【{event.title}】，隨口應對{'：' + name if name else ''}{done}",
                        3 if event.once or event.qiyu else 1)  # 不存玩家的句子（quote 空著）
            msgs += self._event_progress()  # 領地爭奪：隨口應對了結也推一次進度（開關關著是空的）
            self._begin_enlistment(faction_before)
            self._greet_rejoin(faction_before)
            gifts = self._general_gifts() + self._signature_arms()
            msgs += check_thresholds(s, c, self.world, self._quick_client(), now=self.now)
            msgs += self._report_seat()
            self._check_hints()
            journal.add_entry(s, self._draft.entry(s.world.time, msgs))
            self._gift_entry(gifts)
            msgs += gifts
            self.last_gamble = FreeTextOutcome(
                event_id=event.id, text=request.text, success=success, effect_text=fill_marks(effect.text, s),
                time=s.world.time, title=self._draft.title, evil=evil, outcome=chosen.id,
            )
        finally:
            self._draft = None
            self._affinity_before = None
        self._record_faction()
        self._save_season()
        return self._log(msgs)

    def _deed_credit(self, outcome: Outcome, success: bool) -> None:
        """分岔的後果記貢獻（整合設計 5.3）：成了、不是作惡那一種（PM 2026-10-25 第 6 件）、有那一邊（散人照留痕跡、不記貢獻，同推線）。
        一天（季曆日，同推線的上限）最多 Config.jianfa.deed_contribution_cap，超過的不記（PlayerState.deed_day／deed_today）。
        走 wins.credit：兩軍照舊加 contrib 與那一週的帳，豪強另記此刻幫的那一軍那一本。"""
        self._deed_points(outcome.effect.contribution if success and not outcome.evil else 0)

    def _deed_points(self, points: int, *, capped: bool = True) -> int:
        """記 points 點陣營貢獻進「文字的事」那一本（整合設計 5.3：分岔的後果、心意一筆、託付辦成了；減法季批 4、6）：有那一邊才記
        （散人不記，同推線），一天（季曆日）最多 Config.jianfa.deed_contribution_cap，超過的不記（PlayerState.deed_day／deed_today）。
        capped=False（託付辦成了，PM 2026-10-26：一週才一件，共用的話分岔記滿那一天託付就記不到）：照數全記，也不佔那一天的額度。
        走 wins.credit：兩軍照舊加 contrib 與那一週的帳，豪強另記此刻幫的那一軍那一本。回實際記了幾點。"""
        s, c = self.state, self.content
        if not points or self._side() is None:
            return 0
        w, p = s.world, s.player
        at = calendar.point(w.time, c, w)
        if not capped:
            wins_rules.credit(p, c, w, at.week, points)
            return points
        if p.deed_day != at.cal_day:
            p.deed_day, p.deed_today = at.cal_day, 0
        room = outcome_rules.contribution_room(points, p.deed_today, c.config.jianfa.deed_contribution_cap)
        if room:
            p.deed_today += room
            wins_rules.credit(p, c, w, at.week, room)
        return room

    # ── 人物心意（減法季批 6；tianxia/stances.py）────────────

    def _stance_before(self, cid: str) -> str | None:
        """這一輪對話之前，你今天跟這位人物記過的那一筆（沒有心意、關著是 None）：跟之後比，看這一輪有沒有記到。"""
        fid = stance_rules.figure_of(self.content, cid)
        return stance_rules.heard_today(self.state, self.content, fid) if fid is not None else None

    def _stance_credit(self, cid: str, before: str | None) -> None:
        """這一輪對話記到一筆心意（之前今天沒記過、之後有了）：記 Config.jianfa.stance_contribution 點貢獻（整合設計 5.3，跟分岔同一本上限）。"""
        fid = stance_rules.figure_of(self.content, cid)
        if fid is not None and before is None and stance_rules.heard_today(self.state, self.content, fid) is not None:
            self._deed_points(self.content.config.jianfa.stance_contribution)

    def voice_stance(self, fid: str, sid: str) -> bool:
        """不說話、直接記一筆心意（只有伺服器假人叫：bot_policy 照 stances.bot_pick，企劃者 2026-10-24 第 5 件）：一人一天一筆的規則、
        到門檻、貢獻都跟真人說話那一輪一樣，只是沒有那一輪對話、不寫江湖紀錄。記到了存季，回有沒有記。"""
        if self.world.paused_at() is not None or self.state.world.ended:
            return False
        if not stance_rules.record(self.state, self.content, fid, sid):
            return False
        self._deed_points(self.content.config.jianfa.stance_contribution)
        self._save_season()
        return True

    def figure_view(self, cid: str) -> dict | None:
        """人物頁的資料（主機側計畫 1.3 的 figure.stances、figure.errands）：{"id", "name", "stances", "my_stance_today", "errands"}；
        心意關著（或他沒有心意）沒有前兩個鍵、託付關著（或他沒有託付池）沒有 errands。兩樣都沒有是 None。"""
        s, c = self.state, self.content
        fid = figures.of_character(c, cid)
        if fid is None:
            return None
        mind = stance_rules.view(s, c, fid)
        jobs = errand_rules.view(s, c, fid=fid) if errand_rules.on(c, s.world) and c.figures[fid].errands else None
        if mind is None and jobs is None:
            return None
        out: dict = {"id": cid, "name": c.figures[fid].name, **(mind or {})}
        if jobs is not None:
            out["errands"] = jobs
        return out

    # ── 託付與來信（減法季批 6；tianxia/errands.py）────────────

    _persuade_said: tuple[errand_rules.PersuadeRequest, int] | None = None  # 勸降的 C 段（persuade）交給 choose 的單子與模型的分數

    def errands_view(self) -> list[dict] | None:
        """江湖畫面的 main.errands（主機側計畫 1.3）：這一季人物託你的事；託付關著是 None（畫面沒有這個鍵）。"""
        s, c = self.state, self.content
        return errand_rules.view(s, c) if errand_rules.on(c, s.world) else None

    def _errand_options(self) -> list[Option]:
        """人在託付的地點：交信（不花體力）、探營、勸降（花 errand_stamina）。勸降按下去只叫出輸入框（choose 的早退）。"""
        s, c = self.state, self.content
        opts = []
        for e in errand_rules.here(s, c):
            option_id = f"errand:{errand_rules.VERBS[e.kind]}:{e.id}"
            label = f"{errand_rules.LABELS[e.kind]}（替{errand_rules.who(c, e)}{errand_rules.task_text(c, e)}）"
            if e.kind == "letter":
                opts.append(Option(id=option_id, label=label))
            else:
                opts.append(self._cost_option(option_id, label, c.config.jianfa.errand_stamina))
        return opts

    def _errand_act(self, arg: str) -> list[str]:
        """交信（errand:deliver:<id>）、探營（errand:scout:<id>）、勸降（errand:persuade:<id>，只從 persuade 的 C 段進來）：重驗那一件
        還在辦、人在那裡、是那一種，照種類做完、給獎勵。"""
        s, c = self.state, self.content
        verb, _, eid = arg.partition(":")
        e = errand_rules.find(s, eid)
        if e is None or e not in errand_rules.here(s, c) or errand_rules.VERBS[e.kind] != verb:
            return [errand_rules.NOT_HERE]
        if e.kind == "letter":
            d = errand_rules.find_def(c, e.figure, e.errand)
            msgs = [errand_rules.DELIVERED.format(to=d.to or errand_rules.place(c, e.target))]
            msgs += self._errand_reward(e)
            errand_rules.thank(s, c, e)
            return msgs
        s.player.stamina -= c.config.jianfa.errand_stamina
        if e.kind == "scout":
            lines = errand_rules.scout_lines(s, c, e)
            errand_rules.note_scout(s, c, e, lines)
            return [errand_rules.SCOUT_TITLE.format(place=errand_rules.place(c, e.target)), *lines, *self._errand_reward(e)]
        return self._errand_persuade(e)

    def _errand_reward(self, e) -> list[str]:
        """辦成了（整合設計 5.5）：他的情誼 +affinity（照寫的數字給、不照 affinity_gain_scale 放慢，夾在 0～100；PM 2026-10-26）、
        貢獻 +contribution（不吃每天的貢獻上限、也不佔那一本，PM 2026-10-26）、他的那個心意 +1、行狀一則（annals.ERRAND）。回紀錄的句子。"""
        s, c = self.state, self.content
        d = errand_rules.find_def(c, e.figure, e.errand)
        errand_rules.done(s, e)
        cid = errand_rules.cid_of(c, e)
        msgs = [errand_rules.DONE.format(who=errand_rules.who(c, e))]
        if d is not None:
            msgs += errand_rules.warm(s, c, cid, d.affinity)
            self._deed_points(d.contribution, capped=False)
            stance_rules.bump(s, c, e.figure, d.stance)
        annals.note(s, c, annals.ERRAND, f"替{errand_rules.who(c, e)}{errand_rules.task_text(c, e)}，辦成了。", 3, figure=cid)
        return msgs

    def _errand_persuade(self, e) -> list[str]:
        """勸降的結果（choose 的這一下，_persuade_said 是單子與模型的分數）：引擎加情誼名望的修正、夾、自己擲骰；成了立痕跡 band_turned
        （Effect.marks 走 _apply：一人一天一筆、恤民這類心意的倍數照算）、推那一條線（errands.turn_band：一次性的推法，照寫的量、不打事件五折、
        不另記推線的貢獻；FB-827）、給獎勵；敗了打一場遭遇（_squad_encounter，同探索撞上的野怪），那一件沒談成。"""
        s, c = self.state, self.content
        request, rate = self._persuade_said
        d = errand_rules.find_def(c, e.figure, e.errand)
        who = d.persuade.who if d is not None and d.persuade is not None else ""
        final = errand_rules.persuade_rate(s, c, e, rate)
        msgs = [f"你：「{request.text}」（{rate_words(final)}）"]
        if errand_rules.persuade_roll(s, e) < final:
            msgs.append(errand_rules.PERSUADE_WON.format(who=who))
            if d is not None and d.persuade is not None:
                msgs += self._apply(Effect(marks=dict(d.persuade.marks)))
                msgs += errand_rules.turn_band(s, c, d, e.target)
            return msgs + self._errand_reward(e)
        msgs.append(errand_rules.PERSUADE_LOST.format(who=who))
        errand_rules.done(s, e, "failed")
        if d is not None and d.persuade is not None and d.persuade.foe in c.squads:
            msgs += self._squad_encounter(d.persuade.foe, wild=True)
        return msgs

    def persuade_request(self, errand_id: str, text: str) -> errand_rules.PersuadeRequest | list[str]:
        """勸降的 A 段（server.persuade_text 在行動鎖內、很快地呼叫；只讀）：那一件按得下去（勸降、人在那裡、體力夠）、字是 1～20 字，
        就開單；不行回拒絕的話。"""
        if self.world.paused_at() is not None:
            return [f"（{PAUSED_TEXT}。）"]
        s, c = self.state, self.content
        problem = errand_rules.persuade_problem(s, c, errand_id)
        if problem is not None:
            return [problem]
        said = errand_rules.clean_text(text)
        option = {o.id: o for o in self.options(odds=False, tick=False)}.get(f"errand:persuade:{errand_id}")
        if said is None or option is None or not option.enabled:
            return [errand_rules.PERSUADE_ASK]
        e = errand_rules.find(s, errand_id)
        d = errand_rules.find_def(c, e.figure, e.errand)
        return errand_rules.PersuadeRequest(
            errand=errand_id, figure=errand_rules.who(c, e), who=d.persuade.who if d is not None and d.persuade else "",
            place=errand_rules.place(c, e.target), text=zh.to_traditional(said),
        )

    def persuade(self, request: errand_rules.PersuadeRequest, rate: int | None = None) -> list[str]:
        """勸降的 C 段（鎖內）：重驗同一件、同一句還按得下去才扣體力擲骰（choose 的 errand:persuade，紀錄、行狀照一般動作寫）。
        rate 是鎖外評好的 0～100；None＝模型叫不動：照批 4 的慣例落到最保守的結果——什麼都不發生（不扣體力、不打、那一件照舊在），
        回 PERSUADE_SILENT，不寫紀錄。"""
        now = self.persuade_request(request.errand, request.text)
        if isinstance(now, list):
            return self._log(now)
        if (now.errand, now.text) != (request.errand, request.text):
            return self._log([errand_rules.NOT_HERE])
        if rate is None:
            return self._log([errand_rules.PERSUADE_SILENT])
        self._persuade_said = (now, max(0, min(100, int(rate))))
        try:
            return self.choose(f"errand:persuade:{request.errand}")
        finally:
            self._persuade_said = None

    def _stance_annals(self) -> None:
        """同步時：這一週你勸過的心意到了門檻，記一則行狀（annals.STANCE：只寫他改做什麼，不列名字、不寫你說的話）。"""
        s, c = self.state, self.content
        for fid, d in stance_rules.annals_due(s, c):
            cid = c.figures[fid].character or fid
            annals.note(s, c, annals.STANCE, stance_rules.ANNAL.format(name=c.figures[fid].name, stance=d.name, rumor=d.rumor), 2,
                        figure=cid, time=s.world.stance_active[fid].at)

    def add_gamble_narration(self, outcome: FreeTextOutcome, narration: str) -> None:
        """隨口應對的潤色（鎖外生成）插回那一則江湖紀錄：接在「你：「…」」那一行後面、結果文字前面。
        認不到那一則（紀錄已經被後來的事併掉或擠到後面）就不插，潤色本來就是錦上添花。
        潤色那一段已經把結果句整句寫進去了（空白、標點不算，event_llm.tells_the_outcome）就拿掉後面引擎那一行結果句，
        不寫兩次（FB-124）；這時模型那一段不切（結果句常常接在它自己的半句後面，切了會留下斷掉的逗號）。
        只寫到結果句的頭半句、收在那一段的尾巴上（FB-222）：把尾巴重疊的那一截切掉（event_llm.trim_echo），結果句照接整句；
        整段都是重疊的就不插。
        惡行成了（FB-223，outcome.evil）：潤色那一段就是結果，換掉 rules.EVIL_DONE 那一句固定的話（那一句只在潤色沒寫成時收尾）。"""
        journal_entries = self.state.journal
        if not narration or not journal_entries:
            return
        entry = journal_entries[0]
        if entry.time != outcome.time or entry.title != outcome.title:
            return
        lines = list(entry.lines)
        said = next((i for i, line in enumerate(lines) if line.startswith(f"你：「{outcome.text}」")), None)
        at = 0 if said is None else said + 1
        if outcome.evil:
            fixed = next((i for i in range(at, len(lines)) if lines[i] == outcome.effect_text), None)
            if fixed is not None:
                del lines[fixed]
            lines.insert(at, narration)
            journal_entries[0] = entry.model_copy(update={"lines": lines})
            return
        told = event_llm.tells_the_outcome(narration, outcome.effect_text)
        if not told:
            narration = event_llm.trim_echo(narration, outcome.effect_text)
            if not narration:
                return
        lines.insert(at, narration)
        if told:
            echo = next((i for i in range(at + 1, len(lines)) if lines[i] == outcome.effect_text), None)
            if echo is not None:
                del lines[echo]
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
        if not arg.isdecimal():
            return ["（此刻無法這麼做。）"]
        msgs = sensing.choose(s, c, int(arg), rng)
        sense = s.player.sensing
        if not prologue and sense is not None and sense.stage == "draw" and epiphany.roll(s, c, self.rng, boost=outing_rules.rare_boost(s, c)):  # 特殊頓悟：不畫那一筆，開一條頓悟的線
            msgs += self._epiphany_begin(sense.method or "", c.locations[sense.location].name)
        return msgs

    def _epiphany_begin(self, method: str, place: str) -> list[str]:
        """特殊頓悟中了（epiphany.roll）：收掉那一份感悟、開線、直接端出第一題（心靈拷問）；江湖紀錄另起一則「頓悟」。"""
        s, c = self.state, self.content
        progress = epiphany.begin(s, c, method, place)
        if progress is None:
            return []
        s.player.sensing = None
        line = storyline.definition(c, progress)
        self._outcome(journal.event_marker(epiphany.TITLE, True), f"✦ {epiphany.TITLE}")
        return [f"✦ {epiphany.TITLE}", line.intro, f"【{line.title}】"] + storyline.open_quiz(s, c, progress)

    def _epiphany_name(self, arg: str, text: str | None) -> list[str]:
        """特殊頓悟心魔過了之後取名（epiphany.choose）：挑三個候選之一，或自己寫（dunwu:own，名字在 text）。"""
        return epiphany.choose(self.state, self.content, self.world, arg, text)

    def epiphany_request(self) -> epiphany.NameAsk | None:
        """特殊頓悟取名的 A 段（行動鎖內、只讀）：按「靜心思名」時開請模型取三個名字的單（server.epiphany_think、假人程式）。
        不在等著取名、已經想過了、賽季籌備中是 None。"""
        if self._preparing():
            return None
        return epiphany.name_request(self.state, self.content)

    def epiphany_names(self, ask: epiphany.NameAsk, names: list[str]) -> list[str]:
        """C 段（鎖內）：鎖外拿到的名字交回來，重驗、不夠三個用字表補（epiphany.fill）；單子對不上（已經想過、換了一條線）什麼都不做。"""
        msgs = epiphany.fill(self.state, self.content, self.world, ask, names)
        return self._log(msgs) if msgs else msgs

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
        """畫完（或順其自然）之後真的悟：sensing.finish 改狀態；悟成就在這一處留一筆痕跡（一人一個遊戲日只算一次）、序章那一段加旗標、
        記新手引導；悟到自己的新意境而且名字是模型取的，記全服的首悟紀錄（0.2b 第 5 點：第一個在這裡這樣悟到的人）。
        名字走退路字表的不記：伺服器假人不叫模型，記了就會露出「首悟者的名字都是字表風格」（同 2026-10-05 合成首創的決定）。"""
        s, c = self.state, self.content
        got = sensing.current(s, c)
        scene = got[1] if got is not None else None
        client = self._quick_client() if proposed is None else None
        msgs, own, by_model = sensing.finish(s, c, self.world, req, proposed, client)
        if msgs == [sensing.STALE]:
            return msgs
        add_marks({sensing.mark_key(req.location): 1}, s, c)
        if scene is not None and scene.flags_add:
            s.player.flags.update(scene.flags_add)
        if own is not None and by_model and self.world.claim_insight_first(
            sensing.first_key(req), own.name, s.player.name, c.locations[req.location].name, s.world.time,
        ):
            msgs.append(f"江湖上還沒有人在{c.locations[req.location].name}這樣悟過——你是第一個。")
        msgs += self._guide(note_action(s, c, self.world, "sense"))
        return msgs

    def _train_title(self) -> str:
        return sortie_actions.train_title(self)

    def _action_title(self, kind: str, arg: str) -> str:
        s, c = self.state, self.content
        if kind == "explore":  # 探索三選一：「找素材・潁水河畔」；找素材分支：「挖礦・嵩山深處」，「自己說」照找素材
            branch = c.gather_branches.get(arg.removeprefix(f"{explore_modes.GATHER}:")) if arg.startswith(f"{explore_modes.GATHER}:") else None
            name = branch.name if branch is not None else explore_modes.NAMES.get(arg.partition(":")[0], "探索")
            return f"{name}・{c.locations[s.player.location].name}"
        if kind == "faction":
            if arg == "confirm":
                return f"投靠{allied.label(c, s.player.pending_faction, s.player.pending_ally)}"
            if arg == "cancel":
                return "再想想"
            if arg.startswith("ally:"):  # 豪強分屬兩軍：挑依附哪一軍
                return f"依附{c.scenario.faction_name(arg[5:], arg[5:])}"
            if arg.startswith("lean:"):  # 三陣營四勝利：豪強改幫另一軍
                return wins.LEAN_BUTTON.format(side=c.scenario.faction_name(arg[5:], arg[5:]))
            return f"考慮投靠{self.content.scenario.faction(arg).name}"
        if kind == "defect":
            if arg == "confirm":
                return defection.slot_label(s, c, c.scenario.faction(s.player.pending_defect), s.player.pending_ally)
            if arg == "cancel":
                return "再想想"
            fid, _, ally = arg.partition(":")  # 豪強分屬兩軍：defect:<陣營>:<依附的那一軍>
            return f"考慮{defection.slot_label(s, c, c.scenario.faction(fid), ally or None)}"
        if kind == "move":
            return f"前往 {c.locations[arg.partition(':')[0]].name}"
        if kind == "choice":
            event = c.events[s.pending_event]
            return f"{event.title}・{event.choices[int(arg)].text}"
        if kind == "talk":
            character = c.characters[s.player.pending_companion]
            return f"交談・{character.name}"
        if kind == "parley" and s.player.parley_escort in c.characters:  # NPC 智能 2.1：帶路的路上跟他說一句
            return f"同行・{c.characters[s.player.parley_escort].name}"
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
        if kind == "bounty":
            return bounties.BOARD
        if kind == "smith":
            return smithing.title(arg)
        if kind == "market":
            return mounts.MARKET
        if kind == "donate":
            return f"{economy.DONATE_TITLE}・{c.locations[s.player.location].name}"
        if kind == "dadian":
            return f"{silver.SHOP}・{c.locations[s.player.location].name}"
        if kind == "tavern":
            return tavern_rules.title_of(s, c, arg)
        if kind == "ambush":
            return "收伏" if arg == "lift" else f"{ambush_rules.TITLE}・{c.locations[s.player.location].name}"
        if kind == "aid":
            verb, _, fid = arg.partition(":")
            title = {"guard": figure_aid.GUARD_TITLE, "rally": figure_aid.RALLY_TITLE, "visit": figure_aid.VISIT_TITLE}.get(verb, figure_aid.GUARD_TITLE)
            return f"{title}・{c.figures[fid].name}" if fid in c.figures else title
        if kind == "works":
            return f"{works.STOCK_TITLE}・{c.locations[s.player.location].name}"
        if kind == "plan":  # 盤算（世界活起來）：「盤算・劉備」
            plan = plans.find(s, arg.partition(":")[2])
            return f"{plans.TITLE}・{plans._name(c, plan.who)}" if plan is not None else plans.TITLE
        if kind == "errand":  # 託付（減法季批 6）：「交信・盧植」
            e = errand_rules.find(s, arg.partition(":")[2])
            return f"{errand_rules.LABELS[e.kind]}・{errand_rules.who(c, e)}" if e is not None else "託付"
        if kind == "arena":
            foe = arena.entry_of(s.world, arg.partition(":")[2]) if arg.startswith("fight:") else None
            return f"{arena.ARENA}・{foe.name}" if foe is not None else arena.ARENA
        if kind == "invite":
            inv = invites.find(s.world, arg.partition(":")[2])
            if inv is None:
                return "邀請"
            verb = arg.partition(":")[0]
            what = invites.kind_name(inv.kind)
            return {"yes": f"{what}・{inv.sender}", "no": f"婉拒{what}", "cancel": "收回邀請"}.get(verb, f"與{inv.sender}")
        if kind == storyline.OPTION:  # 一條線（答題、打一場、端事件）：寫線的名字
            progress = s.player.storylines.get(arg.partition(":")[0])
            line = storyline.definition(c, progress) if progress is not None else None
            return line.title if line is not None else "奇事"
        if kind == epiphany.OPTION:  # 特殊頓悟取名
            return epiphany.TITLE
        if kind == "act" and arg.startswith("challenge:"):
            return f"挑戰・{figures.name_of(c, arg.partition(':')[2])}"
        if kind == "act" and arg.startswith("bribe:"):  # 銀兩出口的打點門路（21 天季）
            return f"{silver.BRIBE_TITLE}・{figures.name_of(c, arg.partition(':')[2])}"
        silver_title = {"silver_donate": silver.DONATE_TITLE, "mentor": silver.MENTOR_TITLE, "furnace": silver.FURNACE_TITLE,
                        "buy_legend": silver.LEGEND_TITLE}.get(arg) if kind == "act" else None
        if silver_title is not None:
            return f"{silver_title}・{c.locations[s.player.location].name}"
        if kind == "act" and arg.startswith("recruit:") and arg.partition(":")[2] in c.characters:
            return f"招募・{c.characters[arg.partition(':')[2]].name}"
        rank_action = _rank_action_id(arg) if kind == "act" else None  # 第 3、4 階的行動（正式版戊一）寫它自己的名字
        if rank_action is not None:
            name = next(a.name for a in c.orders.rank_actions if a.id == rank_action)  # choose 已經驗過選項在選單上，一定找得到
            return f"{name}・{c.locations[s.player.location].name}"
        here = c.locations[s.player.location].name
        duty = c.orders.duties.get(s.player.faction or "")  # 守勢行動的標題寫陣營自己的名字（巡哨、傳道、保境安民）
        action2 = opportunities.rank2_action(s, c)  # 第 2 階行動的標題也寫它自己的名字（招降黃巾散兵、施符水收人心）
        titles = {
            "explore": f"{journal.OUTING}・{here}" if self._outing_on() else f"探索{here}", "socialize": f"交友・{here}", "call": f"求見・{here}", "train": f"{self._train_title()}・{here}",
            "recruit": f"招募・{here}", "rest": f"調息・{here}", "summons": f"應召・{here}", "halt": "喊停", "part": "分道揚鑣",
            "duty": f"{duty.name if duty else '守勢'}・{here}", "convoy": f"接下糧車・{here}",
            "rank2": f"{action2.name if action2 else '第二階行動'}・{here}",
            "bounties": f"{bounties.BOARD}・{here}",
            "smith": f"{weapons.SMITH}・{here}",
            "market": f"{mounts.MARKET}・{here}",
            "arena": f"{arena.ARENA}・{here}",
            "heal": f"療傷・{here}",
            "donate": f"{economy.DONATE_TITLE}・{here}",
            "dadian": f"{silver.SHOP}・{here}",
            "tavern": tavern_rules.sign(s, c),
            "drill": f"{training.DRILL}・{here}",
        }
        return titles.get(arg, "提前出關")

    def _hide(self, msg: str) -> None:
        if self._draft is not None:
            self._draft.hide(msg)

    def _outcome(self, text: str, msg: str) -> None:
        if self._draft is not None:
            self._draft.outcome(text, msg)

    def _write(
        self, title: str, msgs: list[str], tag: str = "", guide: list[str] | None = None, merge: bool = False,
        battle_id: int | None = None,
    ) -> None:
        """寫一則江湖紀錄。merge：最新一則同標題就併進去（journal.add_entry 的 merge；連著收同一個人的禮，FB-116）。
        battle_id：這一則連到哪一份戰報（替對方記的切磋，FB-244）。"""
        draft = Draft(title, tag)
        draft.guide = list(guide or [])
        draft.battle_id = battle_id
        journal.add_entry(self.state, draft.entry(self.state.world.time, msgs), merge=merge)

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
        if faction_before is None and self.state.player.faction is not None and prologue_rules.onboard_step(self.state, self.content):
            prologue_rules.skip_onboarding(self.state, self.content)  # 初入江湖還沒走完就投靠了：剩下的交給引薦人帶，不兩個人搶一個框
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
            text = enlist.line(who, "rejoin", self.state, self.content)  # 豪強分屬兩軍的季有另一版就照它
            hint_rules.queue_note(self.state, HintNote(id="s_rejoin", speaker=who.name, text=text, by=p.faction))

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
        """入伍段「出一次力」那一步，選單上能完成它的那幾顆（FB-093，enlist.glow）；初入江湖這一步要按的（prologue.onboard_glow）；
        網頁讓它們發光。"""
        return enlist.glow(self.state, self.content, option_ids) + prologue_rules.onboard_glow(self.state, self.content, option_ids)

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
            if prologue_rules.onboard_step(s, c) is not None:  # 初入江湖：老周的話不切成三行（同入伍段，要照著做的話整段看得到）
                box["full"] = True
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
        # 有所感（悟意境設計第零節）的卡也一樣：選做法、畫一筆都佔著畫面，跟事件待處理同一種等法。跟人物談話也是（explain-1）：
        # 對話的幾個選項跟事件的選項一樣佔著畫面，第一次談話說的 h_bond 擺在上面會把「告辭」擠出第一屏；告辭之後上框
        if not p.hint_queue or self.state.pending_event is not None or p.sensing is not None or p.pending_companion is not None:
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

    def _drop_stale_hints(self) -> None:
        """排著還沒上框、條件已經不成立的拿掉（新手引導重做：療好傷才輪到「內傷去醫館」那一條就不說；沒說過，之後再受傷還會說）。"""
        p = self.state.player
        p.hint_queue = [n for n in p.hint_queue if n.shown or not (n.id == "h_injury" and p.member.injury < 1)]

    def _hint(self, hint_id: str) -> None:
        """碰到某個玩法：排一條提示（序章裡不排，序章本身在教；新手引導計畫三）。說過的、已經排著的、關了提示的、假人都不排；
        輪得到上框就當場上框（_surface_hint）。"""
        if not prologue_rules.active(self.state, self.content):
            hint_rules.queue(self.state, self.content, [hint_id])
            self._surface_hint()

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
        # 第一場沒打贏的仗：僵持與落敗都算（以前只算落敗：身法閃成僵持的人師父不開口）；決戰與挑戰本人不在這三種裡
        if want("h_lose") and any(r.tier not in team.WIN_TIERS for r in s.battles if r.kind in ("train", "sortie", "wild", "event")):
            on.append("h_lose")
        if want("h_injury") and p.member.injury > 0:
            on.append("h_injury")
        # 新手引導重做（2026-10-22）：練功連輸兩場（僵持不算輸）、心得第一次夠自創、第一次到有酒肆的城、點數沒配又升了一級
        if want("h_field_lose") and sum(1 for r in s.battles if r.label == training.PRACTICE and r.tier not in team.WIN_TIERS
                                        and r.tier != "僵持") >= 2:
            on.append("h_field_lose")
        if want("h_create") and create.on(c) and p.created_count == 0 and create.allowed(s, c) is None \
                and p.stats.get("xinde", 0) >= create.price(s, c):
            on.append("h_create")
        if want("h_tavern") and tavern_rules.on(c) and tavern_rules.here(s, c) and p.location not in prologue_rules.onboard_towns(c):  # 老周在那裡教過酒肆
            on.append("h_tavern")
        if want("h_points") and p.stat_points >= 2:
            on.append("h_points")
        # 「這裡能學新的底」：只算現在學得了的（learn 擋下的——名望、學費、門派、陣營、持有滿了——都不算，不然師父說能學、按下去卻是「學不了」）
        if want("h_basic_art") and any(problem is None for _, problem in library.lessons_here(s, c)):
            on.append("h_basic_art")
        if want("h_recruit") and (self._recruit_target() is not None or self._recruitable_here()):
            on.append("h_recruit")
        if want("h_free_text") and s.pending_event:
            event = c.events.get(s.pending_event)
            if event is not None and self._free_text_of(event) is not None:
                on.append("h_free_text")
        if want("h_road") and p.recent_sights:  # 路上見聞真的發生過才會記
            on.append("h_road")
        if want("h_cap") and library.held_count(s) >= library.cap_of(s, c) - 5:
            on.append("h_cap")
        status = self._battle_status(tick=False) if want("h_spectator") or want("h_showdown") else None
        watching = status is not None and self._watching_battle(*status)
        # 散人只在決戰所在的大區、還沒投效時才說（N3）：人在別處不算「遇上」；說的是可以臨時投效（試玩回饋 2026-10-08）
        if want("h_spectator") and status is not None and p.faction is None and p.name not in status[0].participants \
                and self._at_battle(status[1]):
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
        self._drop_stale_hints()
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
        self._check_newbie()
        self._queue_triggered_hints()
        self._surface_hint()

    # ── 新手目標（新手引導重做；tianxia/newbie.py）──

    def _check_newbie(self) -> None:
        """做到的新手目標發獎勵，那一句記進這一則江湖紀錄的引導那幾行（不另起一則；假人一樣拿：畫面上看不出誰是假人）。"""
        got = newbie.grant(self.state, self.content)
        if got:
            self._journal_guide([f"{line}{change}" for line, change in got])

    def _nearest_to(self, targets: set[str]) -> str | None:
        """離這裡最近的那一個地點（先照摸清的路，都走不到照所有開放的地點，同 _nearest_practice）；這裡就是的話回這裡。"""
        s, c = self.state, self.content
        if s.player.location in targets:
            return s.player.location
        for found in (atlas.routes(s, c), atlas.shortest_routes(s, c)):
            reachable = [route for loc_id, route in found.items() if loc_id in targets and route.path]
            if reachable:
                return min(reachable, key=lambda route: (round(route.minutes, 6), len(route.path), route.path)).path[-1]
        return None

    def _newbie_go(self, go: str) -> dict:
        """「去做」：{"tab": 分頁} 或 {"move": 地點 id, "place": 名字}（網頁打開移動清單、把那一個亮起來；人就在那裡是 {"tab": "jianghu"}）。"""
        c = self.content
        if go in ("craft", "practice", "map"):
            return {"tab": go}
        if go.startswith("practice"):
            tier = int(go[-1])
            targets = {loc.id for loc in c.locations.values() if self._practice_tier(loc) == tier}
        elif go == "tavern":
            targets = {loc.id for loc in c.locations.values() if tavern_rules.tavern_at(c, loc.id)}
        else:  # 懸賞榜、擂台都在城鎮類的地點
            targets = {loc.id for loc in c.locations.values() if training.is_town(c, loc)}
        where = self._nearest_to(targets)
        if where is None or where == self.state.player.location:
            return {"tab": "jianghu"}
        return {"move": where, "place": c.locations[where].name}

    def newbie_view(self) -> dict | None:
        """任務卡上「新手目標」那一塊：引導（序章、初入江湖）走完、新手期裡、還有沒做完的才有。一次亮最上面三條。"""
        s, c = self.state, self.content
        if not newbie.active(s, c) or prologue_rules.onboard_step(s, c) is not None:
            return None
        rows = [{"key": g.key, "text": newbie.text_of(s, c, g), "reward": newbie.reward_text(c, g), "go": self._newbie_go(g.go),
                 "drifter": g.key == "side" and s.player.faction is None} for g in newbie.todo(s)]
        return {"title": newbie.TITLE, "rows": rows, "done": len(s.player.newbie_done), "total": len(newbie.GOALS)}

    def newbie_drifter(self) -> list[str]:
        """任務卡「就當散人」：記下這一條（投靠一方或就當散人）。只改自己的記號，獎勵照平常的檢查發。"""
        p = self.state.player
        if p.faction is not None or not newbie.active(self.state, self.content):
            return []
        p.newbie_marks.add(newbie.DRIFTER)
        self._check_newbie()
        return [newbie.DRIFTER_LINE]

    # ── 書信與委託（大勢人物擴充第二批；tianxia/letters.py）──

    def letter_view(self) -> dict | None:
        """江湖頁「剛剛」上面那張小卡：最新一封沒看過的信；沒有是 None。"""
        return letters.view(self.state, self.content)

    def read_letter(self, letter_id: int) -> list[str]:
        """小卡上的「收起」：記成看過了（委託照樣在身上，懸賞卡上看得到）。"""
        return letters.read(self.state, letter_id)

    def decline_letter(self, letter_id: int) -> list[str]:
        """小卡上的「婉拒」：這封信附的委託作罷（不扣情誼），信記成看過了。"""
        msgs = letters.decline(self.state, self.content, letter_id)
        if msgs and msgs[0] != letters.NO_LETTER:
            self._write(letters.TITLE, msgs)
        return msgs

    def morning_mail(self, now: float) -> bool:
        """減法季「09:00 來信」（整合設計第十章，批 9）：伺服器的看守替開了推播的人送今天的信，不必等他上線（送了手機才跳得出
        「某某來信」）。只做同步裡書信那一格（letters.deliver），不補算體力、不算上線、不動「此地還有」；他下次同步照常，同一個
        送信日不會再送第二封。角色還停在上一季（換季後還沒上線過）、或這一季沒開 morning_mail 時什麼都不做。
        呼叫端拿著行動鎖、事後存角色；送了一封回 True。"""
        self.now = now
        if self.state.player.season_number < self.world.get_season_number():
            return False
        self.state.world = self.world.get_season()
        if letters.mail_day(self.content, self.state.world, now) is None:
            return False
        seq = self.state.player.letter_seq
        mail = letters.deliver(self.state, self.content, now)
        if mail:
            self._write(letters.TITLE, mail)
        return self.state.player.letter_seq != seq

    def letter_request(self) -> letters.LetterNote | None:
        """還等著模型照他的口氣重寫的那一封（server 鎖外寫；A 段，只讀）。"""
        return letters.request(self.state, self.content)

    # ── 人物的行程與盤算（世界活起來；tianxia/plans.py、deeds.py）──

    def _plan_options(self) -> list[Option]:
        """人在盤算的地點：助他一臂、壞他的事（花 Config.plans.stamina）；插過手的留一顆灰的。"""
        cost = self.content.config.plans.stamina
        return [self._cost_option(oid, label, cost) if ok else Option(id=oid, label=label, enabled=False)
                for oid, label, ok in plans.options(self.state, self.content)]

    def _plan_act(self, arg: str) -> list[str]:
        """助一臂（plan:help:<站>）、壞他的事（plan:block:<站>）：重驗還開著、人在那裡、站的邊對、還沒插過手、體力夠。"""
        s, c = self.state, self.content
        verb, _, stop = arg.partition(":")
        problem = plans.problem(s, c, verb, stop)
        if problem is not None:
            return [problem]
        cost = c.config.plans.stamina
        if s.player.stamina < cost:
            return [f"體力不足（需要 {cost}）。"]
        s.player.stamina -= cost
        return plans.join(s, c, verb, stop, self.stamp(plans.find(s, stop).due))

    def plan_view(self) -> dict | None:
        """江湖頁的盤算卡（main.plan）：全服開著的盤算裡最切身的一件；沒有開著的、開關關著是 None。"""
        s, c = self.state, self.content
        plan = plans.pick(s, c)
        if plan is None:
            return None
        view = plans.card(s, c, plan, when=self.stamp(plan.due), minutes=self.place_minutes(plan.place))
        for act in view["acts"]:  # 卡上的鈕跟「此地還能做」那一顆同一個字（帶體力）
            act["label"] = f"{act['label']}（體力 {c.config.plans.stamina}）"
        return view

    def place_deeds_view(self) -> list[dict] | None:
        """此地舊事（main.place_deeds）：這裡最近的幾筆世界記事；在路上、沒有、開關關著是 None。"""
        s, c = self.state, self.content
        if s.player.journey is not None:
            return None
        found = deeds.at_place(s, c, s.player.location)
        return [{"when": self.stamp(d.time), "text": d.text} for d in found] or None

    # ── 宴客（搬進功能包 tianxia/features/feast/；server 的三段式照舊叫 Game 的這三個，過渡留一行委派）──

    def feast_free_text_prompt(self) -> str | None:
        return feast_actions.free_text_prompt(self)

    def feast_text_request(self, text: str) -> feast_actions.feasts.ToastRequest | list[str]:
        return feast_actions.text_request(self, text)

    def feast_toast(self, text: str, score: int, request: feast_actions.feasts.ToastRequest | None = None) -> list[str]:
        return feast_actions.toast(self, text, score, request)

    # ── 月旦評（第三批；tianxia/yuedan.py）──

    def yuedan_request(self) -> yuedan.YuedanNote | None:
        """A 段（只讀）：這一週還沒發、還沒寫過評語的那一批。"""
        return yuedan.request(self.state, self.content)

    def apply_yuedan(self, note: yuedan.YuedanNote, lines: dict[str, str]) -> bool:
        """C 段：同一批才換上評語並發出去（天下大事、江湖史），存回共用賽季。"""
        done = yuedan.apply(self.state, self.content, note, lines)
        if done:
            self._save_season()
        return done

    def apply_letter(self, note: letters.LetterNote, text: str) -> bool:
        """C 段：還是同一封才換；寫不出來照固定句。"""
        return letters.apply(self.state, note, text)

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
        """各行動花的體力：照 Config.action_cost。按鈕上寫的與真的扣的都讀這一個。（輕身以前少花遊歷的體力；本命戰法第三批起
        改成回合裡的化影，tactics.py）"""
        return dict(self.content.config.action_cost)

    def _act(self, what: str, prepared: companion_agent.PreparedTurn | None = None) -> list[str]:
        if what == "explore" and self._outing_on():  # 減法季探索一顆：出門一趟（體力在裡面扣）
            return self._explore_one()
        if what == "explore" and explore_modes.on(self.content) and not prologue_rules.active(self.state, self.content):
            return [explore_modes.PICK]  # 三選一開著：「探索」只是展開三顆的入口，按了不花體力、不做事（網頁在行動列底下展開）
        if what == "break":
            return self._finish_seclusion(self.state.world.time)
        if what == "halt":
            return self._halt()
        if what == "part":
            return self._part_ways()
        if what == "recruit":
            return self._recruit()
        if what.startswith("recruit:"):
            return self._recruit_one(what.partition(":")[2])
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
        if what == "bounties":
            p = self.state.player
            # 打開懸賞榜（見 _bounty_options），不花體力；每次打開都從第二層開始（第三層是替一張求兵挑東西）
            p.picking_bounty, p.bounty_pick, p.shop_clue = True, None, ""
            self._shop_say("enter")  # 店面上榜吏那一句（店面獨立介面設計 1.4）
            return [f"你擠到{bounties.BOARD}前，看上面貼了些什麼。"]
        if what == "smith":
            equipment.open_smith(self.state.player, self.content)  # 打開鐵匠鋪（見 _smith_options），不花體力；單子從頭開始（Review Focus 4）、停在第一個開著的那一頁
            self.state.player.shop_clue = ""
            self._shop_say("enter")  # 店面上掌櫃那一句（店面獨立介面設計 1.4）
            self.state.player.smith_rule = shopview.next_rule(self.state, self.content)  # 背包有四階時鐵匠講一句神器的規矩（正式季整合 5.10）
            return [f"你走進{weapons.SMITH}，爐火燒得正旺。"]
        if what == "market":
            p = self.state.player
            p.picking_market, p.shop_clue = True, ""  # 打開馬市（見 _market_options），不花體力
            self._shop_say("enter")  # 店面上馬販那一句（1.4）
            return [mounts.ENTERED]
        if what == "arena":
            self.state.player.picking_arena = True  # 打開擂台（見 _arena_options），不花體力
            self.state.player.arena_last = None
            return arena.standing(self.state.world, self.state.player.name, self.content.config.arena)
        if what == "heal":  # 醫館療傷（企劃者 2026-10-12）：同修練頁的療傷鈕，不花體力
            return self._heal_msgs()
        if what == "dadian":  # 打點（銀兩出口收成一間店，第 9 批畫面乙）：打開那一間店（見 options 的 picking_dadian），不花體力
            p = self.state.player
            p.picking_dadian, p.shop_clue = True, ""
            self._shop_say("enter")
            return [silver.SHOP_ENTERED]
        if what in ("silver_donate", "mentor", "furnace", "buy_legend") or what.startswith("bribe:"):
            msgs = self._silver_act(what)  # 銀兩出口（21 天季，正式季整合 6.5）：都不花體力
            if self.state.player.picking_dadian:
                self._shop_say("done")  # 打點那一間店裡記了一筆：掮客換一句
            return msgs
        if what == "donate":  # 大本營捐軍備（素材與經濟設計第六節）：打開軍需官那一串（見 _donate_options），不花體力
            self.state.player.picking_donate, self.state.player.shop_clue = True, ""
            self._shop_say("enter")  # 軍需帳上軍需官那一句（店面同一套）
            return [economy.DONATE_OPEN.format(faction=self.content.scenario.faction_name(self.state.player.faction, ""))]
        if what == "tavern":  # 酒肆（企劃者 2026-10-18）：打開酒肆（見 _tavern_options），不花體力
            return self._tavern_enter()
        if what == "drill":  # 城裡操練（新手引導重做，Config.training）：體力在裡面扣
            return self._town_drill()
        if what == "call":
            self.state.player.picking_audience = True  # 打開求見選單（見 _audience_options），不花體力
            return [f"你遞上名帖，準備求見{self.content.locations[self.state.player.location].name}的人物。"]
        if what.startswith("challenge:"):
            return self._challenge(what.partition(":")[2])
        promotion = ranks.summons_event(self.state, self.content)
        if what == "summons":
            return self._present(self.content.events[promotion])
        if what == "train" and self.duel_on() and not prologue_rules.active(self.state, self.content):
            return self._duel_entry()  # 減法季批 3b：出陣那一格打開出陣前那張卡（不花體力）；截糧的運糧隊經過時照舊攻打（體力在裡面扣）
        self.state.player.stamina -= self._action_costs()[what]  # 不花體力的行動（上面那些）不必算（要翻武學的資料）
        if promotion is not None and what in ("explore", "socialize") and not precise.on(self.content, self.state.world):
            # 在召見的地點探索、交友：端出晉升奇遇（計畫 T5）；一類一顆開著時不再換掉（正式季整合 2.10），應召照舊在「此地還能做」
            return self._present(self.content.events[promotion])
        if what == "explore":
            return self._explore()
        if what == "train":  # 出陣（出陣探索與地盤設計第二節）；序章的雪恥照舊是遊歷
            backing = self._parley_backing_here()  # NPC 智能 2.0的並肩出陣：今天答應陪你的人在這一帶，這一仗本人威力多幾成
            share = self.content.config.parley.backing_share
            plan = self.state.player.parley_backing.plan if backing else None  # 第二批：商量過打法，成了加倍、沒成打空
            share = share * 2 if plan else 0.0 if plan is False else share
            with team.backed(1 + share if backing else 1.0):
                msgs = self._sortie() if sortie.on(self.content) and not prologue_rules.active(self.state, self.content) else self._train()
            if backing:
                self.state.player.parley_backing = None
                name = self.content.characters[backing].name
                msgs.insert(0, parley.BACKED_LINE.format(name=name, pct=round(share * 100)) if share else parley.PLAN_MISS.format(name=name))
            return msgs
        msgs = self._socialize(prepared)
        self._hint("h_bond")  # 第一次交友：情誼有什麼用（explain-1，碰到才說；說過就不再說，眼前有事件、對話時排著等）
        return msgs

    def _socialize(self, prepared: companion_agent.PreparedTurn | None = None) -> list[str]:
        """交友（act:socialize，體力呼叫端已經扣了）：福緣到了先發福緣；這裡至多一位人物、見得到就開口對話；不然抽一則
        這裡的交友事件，沒有就是打發話。一類一顆開著時照 _social_plan（_precise_socialize）。"""
        if precise.on(self.content, self.state.world):
            return self._precise_socialize(prepared)
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

    def _precise_socialize(self, prepared: companion_agent.PreparedTurn | None) -> list[str]:
        """一類一顆的交友（正式季整合 2.8）：照 _social_plan 做那一件事；沒有人可以說話（鈕是灰的，舊分頁按到）退回體力。"""
        s, c = self.state, self.content
        kind, arg = self._social_plan()
        if kind == "fortune":
            s.player.fortune = True
            cid = self._fortune_free()
            return [f"你新立門戶不久，【{c.characters[cid].name}】主動前來結識。"] + roster.recruit(s, c, self.world, cid)
        if kind == "once":
            return self._present(pick_event(s, c, "socialize", self.rng, "rare"), "socialize")
        if kind == "talk":
            return self._open_dialogue(arg, prepared)
        if kind == "meet":
            return self._present(self._meet_event(), "socialize")
        s.player.stamina += c.config.action_cost["socialize"]
        if kind == "list":
            s.player.picking_audience = True
            return [f"你遞上名帖，準備求見{c.locations[s.player.location].name}的人物。"]
        return [f"{arg}。"]

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
            if precise.on(self.content, self.state.world):  # 一類一顆（2.8）：不再打發；結識得到的走結識事件，見不到的在名單上是灰的
                event = self._meet_event(arg)
                if event is None:
                    return [f"{self._why_not_talk(arg)}。"]
                self.state.player.stamina -= self.content.config.action_cost["socialize"]
                return self._present(event, "socialize")
            return self._brush_off(arg)
        self.state.player.stamina -= self.content.config.action_cost["socialize"]
        return self._open_dialogue(arg, prepared)

    def _open_dialogue(self, companion_id: str, prepared: companion_agent.PreparedTurn | None) -> list[str]:
        """跟一位大勢人物開口對話（呼叫端已經扣了交友的體力）：生成不出對話時退回那份體力，對話不開始。"""
        extra = self._parley_plea_prompt(companion_id)
        try:
            msgs = companion_agent.start_dialogue(
                self._quick_client(), self.state, self.content, self.world, companion_id, self.rng,
                turn=self._prepared_turn(prepared), extra=extra,
                decide=lambda turn: self._parley_plea(companion_id, turn), required=parley.PLEA_FIELDS if extra else (),
            )
        except companion_agent.DialogueUnavailable:
            self.state.player.stamina += self.content.config.action_cost["socialize"]  # 生成不出對話：這次不花體力
            return self._dialogue_unavailable(companion_id)
        self._hint("h_bond")  # 第一次跟人物談話（求見也算）：情誼有什麼用（explain-1）；對話還開著，框等告辭之後才上（_hint_box）
        return msgs + self._overhear(companion_id, msgs)

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
        scouted = bounties.on_explore(self.state, self.content, self.world, self.state.player.location)  # 懸賞榜的打探：探索一次就算
        return self._explore_outcome() + self._legend_find() + self._scrap_find() + scouted

    def _seal_find(self, loc_id: str) -> list[str]:
        """領地爭奪的季，探索撿玉璽碎片（領地爭奪設計 3.9、4.8；計畫 Task 14）：探索的四種（找素材、找事件、靜心感悟、練功）收尾各叫一次。
        只在這一季藏著一片、人就站在藏碎片的那一塊、那一塊不在剛易手的冷卻期（conquest.cooling）、手上還沒有碎片（一人一片）時擲 seal.find
        （那一塊此刻歸你的陣營機率高一點）；
        別的塊、沒藏碎片的季一律不擲、不碰任何登記。擲中就把那一片記到自己名下（登記記一筆 emerge，所以補紀錄、同一季學會混元一氣、
        天命之季的判斷都照現世的老路），清掉藏處；接著 _deliver_seal_results 馬上補送。天下大事與江湖史都不寫是在哪裡撿到的。
        骰子是密鹽的亂數，不碰 Game.rng；寫登記用一次 world.mutate、寫入時整個重驗（別人搶先撿走了就落空）。回要接在探索結果後面的句子。"""
        c, s = self.content, self.state
        if not seal.on(c) or not conquest.on(c, s.world):
            return []
        view = self.world.seal_state()
        cache = seal.live_cache(view.registry, view.season)
        p = s.player
        if cache is None or cache.loc != loc_id or seal.shard_of(view.registry, p.name) is not None:
            return []
        if conquest.cooling(s.world, c, loc_id):  # 翻地與爭搶：剛易手還在冷卻的那一塊加成暫停，碎片也不擲（輿圖簡化設計 4.1）
            return []
        side = self._side()  # allied.side_of（＝rules.side_of）：豪強依附一軍就是那一軍（FB-571，同地盤折扣）；散人沒有自家、不乘（PM 裁決）：side 是 None，不能跟沒人佔的 None 湊成自家
        own = side is not None and conquest.holder(s.world, c, loc_id) == side
        if not seal.find(view.registry, view.tianji, p.name, p.explore_seq, own, c.config.seal):
            return []
        found = {"ok": False}

        def _apply(shared) -> None:
            reg = seal.filled(shared.seal, c)
            now = seal.live_cache(reg, shared.season_number)
            if now is None or now.loc != loc_id or seal.key(p.name) in seal.holders(reg):  # 寫入時重驗：被別人搶先、或自己剛有了一片
                return
            shard = reg.shards[now.shard]
            season = shared.season_number
            shard.state, shard.holder, shard.since_season, shard.emerged_round = "held", p.name, season, reg.round
            reg.emerge_season, reg.cache = season, None
            text = seal.FIND_GOT.format(name=p.name, shard=c.seal[shard.id].name)
            seal.log(reg, season, "emerge", shard=shard.id, holder=p.name, text=text)
            seal.rumor(shared.season, text)
            seal.chronicle(shared.season, text)
            found["ok"] = True

        self.world.mutate(_apply)
        if not found["ok"]:
            return []
        self._deliver_seal_results()  # 傳承那一格、混元一氣、紀錄一則、行狀一筆（同現世的得主）
        return [seal.FIND_SCENE]

    def _legend_find(self, rng: random.Random | None = None) -> list[str]:
        """探索不論走哪一支，結束後擲一次有沒有撿到破境丹（企劃者 2026-10-05：到處探索都有約 2% 的機會；帶著「探索撿破境丹」的寶物時門檻 ×2）。
        機率是 0 就不擲骰（先判斷機率，亂數序列一個都不動：測試內容把它設成 0，既有的固定種子序列才不會位移）。
        兩行：「獲得」開頭的敘事（江湖紀錄給它掃光，journal._NEW_THING）與「破境丹 +1」（寫進紀錄的數值變化）。
        rng：探索三選一傳自己的亂數；舊的探索不傳，照舊用 Game.rng。"""
        cfg = self.content.config
        # 寶物「探索撿破境丹」（裝備四欄 6.2）：只放大門檻（夾在 1 以下），擲的還是同一顆 self.rng.random()——帶不帶都只擲一次，
        # 序列不位移；基本機率是 0 照舊不擲（測試內容）
        chance = min(1.0, cfg.explore_legend_chance * treasures.amount(self.state, self.content, "legend"))
        if cfg.explore_legend_chance <= 0 or (rng or self.rng).random() >= chance:
            return []
        self.state.player.legend_items += 1
        return [f"獲得 【{cfg.legend_item_name}】一枚——{cfg.legend_item_note}", f"{cfg.legend_item_name} +1"]

    def _pill_find(self, rng: random.Random) -> list[str]:
        """找素材、練功掉一顆回體丹（21 天季，正式季整合 6.4；Config.checkin.pill_drop）：用探索三選一自己的亂數（用途「回體丹」），
        不碰別的骰。兩行同破境丹：「獲得」開頭的敘事與「回體丹 +1」（寫進紀錄的數值變化）。"""
        c = self.content
        chance = c.config.checkin.pill_drop
        if chance <= 0 or not checkin.on(c, self.state.world) or rng.random() >= chance:
            return []
        self.state.player.stamina_pills += 1
        name = c.config.stamina_pill_name
        return [checkin.PILL_FOUND.format(name=name), f"{name} +1"]

    def _explore_outcome(self) -> list[str]:
        s, c = self.state, self.content
        loc = c.locations[s.player.location]
        sight = prologue_rules.explore_event(s, c)
        if sight is not None:  # 序章第 3 步：草廬四景四選一（新手引導設計 3.2），不抽奇遇、不分三支
            return self._present(c.events[sight], "explore")
        scene = prologue_rules.explore_scene(s, c)
        if scene is not None:  # 序章第 3 步的有所感版（悟意境設計第七節）：草廬四景就是四個做法，都對、必中
            return sensing.start(s, c, c.insight_scenes[scene], self.rng)
        boss = duel_rules.available(s, c)  # 單人頭目戰：只有這裡有頭目時才擲（沒有頭目的地點、測試內容，亂數序列一個都不動）
        # 名聲 4.4：名望高、頭目找上門的機會乘 renown.duel_chance（只放大門檻，擲的還是同一顆骰）
        if boss is not None and self.rng.random() < c.config.duel.explore_chance * renown.duel_chance(s, c):
            return self._duel_start(boss)
        if event_candidates(s, c, "explore", "rare") and self.rng.random() < c.config.rare_explore_chance:
            return self._present(pick_event(s, c, "explore", self.rng, "rare"), "explore")
        weighted = self._explore_weights(loc)
        if not weighted:
            return ["你四處走走，一無所獲。"]
        branch = self.rng.choices([b for b, _ in weighted], weights=[w for _, w in weighted])[0]
        if branch == "insight":
            if sensing.can_sense(s, c, loc):  # 有場景：有所感，要選做法、畫一筆才悟得到（悟意境設計第零節）
                return sensing.start(s, c, sensing.pick_scene(loc, c, self.rng), self.rng)
            found = insights.roll_explore(loc, c, self.rng)  # 沒有場景的內容（測試內容）照舊直接悟
            return [f"你在{loc.name}靜下心來，看了好一陣。"] + insights.learn(s, c, self.world, found, at=loc)
        if branch == "wild":
            squad = min(self._wild_foes(loc), key=lambda foe: foe.difficulty)  # 同分取這裡列的第一路
            return [f"你在{loc.name}走著，{squad.name}突然殺出！"] + self._squad_encounter(squad.id, wild=True)
        return self._present(pick_event(s, c, "explore", self.rng, "common"), "explore")

    def _explore_weights(self, loc: Location) -> list[tuple[ExploreBranch, float]]:
        """探索三選一此刻在這裡的候選與比重（探索三選一設計第三節）：照地點類型（Config.explore_mix），比例是 0 的與做不了的
        （_explore_can）拿掉；悟意境那一支的比重 ×（1＋3%×（悟性−5））× 寶物（treasures.amount 的 insight，裝備四欄 6.2），另外兩支不動（武學與成長設計 6.1）。
        探索真的擲骰（_explore_outcome）與行動列底下那一行（action_notes，explain-1）讀同一份：說的跟擲的不會走樣。"""
        s, c = self.state, self.content
        mix = c.config.explore_mix_of(loc.tags).weights
        wis = team.stat_factor(c, s.player.stats.get("wis", team.BASE_STAT), s.world)
        sharp = wis * treasures.amount(s, c, "insight")  # 寶物「探索悟意境」跟悟性疊乘（裝備四欄 6.2）
        return [
            (b, mix[b] * (sharp if b == "insight" else 1))
            for b in EXPLORE_BRANCHES if mix.get(b, 0) > 0 and self._explore_can(b, loc)
        ]

    def _explore_can(self, branch: ExploreBranch, loc: Location) -> bool:
        """探索三選一的這一支在這裡做不做得了。"""
        if branch == "insight":
            if sensing.missed_today(self.state, self.content, loc):
                return False  # 這個遊戲日在這裡選錯過做法：換日之前這裡悟不出什麼（Q2）
            return bool(insights.explore_gives(loc, self.content))  # 輿圖詳情欄「這裡能悟」用同一個判斷（W3）
        if branch == "wild":
            return bool(self._wild_foes(loc))
        return bool(event_candidates(self.state, self.content, "explore", "common"))

    def _wild_foes(self, loc: Location) -> list[Squad]:
        """探索時可能殺出來的野怪：這裡此刻站的隊伍（地盤易手照控制方，_here_squads）裡不是自己陣營的那幾路
        （自己人不會突然殺出來，也不在這裡操練）。"""
        squads = [self.content.squads[sid] for sid in self._here_squads(loc.id)]
        return [squad for squad in squads if not self._drills_with(squad)]

    def _here_squads(self, loc_id: str) -> list[str]:
        """這個地點此刻站的隊伍（territory.squads_at；地盤易手的開關關著就是 loc.enemies）。"""
        return territory.squads_at(self.state.world, self.content, loc_id)

    # ── 探索三選一（出陣探索與地盤設計第三節）────────────────────────────

    def _explore_mode(self, mode: str) -> list[str]:
        """探索三選一的一種（explore:gather|seek|sense）：體力同探索；在召見的地點端出晉升奇遇（同舊的探索）。三種都擲破境丹、
        都算打探懸賞的交差（設計 3.4）。擲骰都用自己的亂數（explore_modes.rng_for），不碰 Game.rng。
        找素材分支（第 32 項）：有分支層時「找素材」本身只回 GATHER_PICK（不花體力、不做事）；gather:<分支>、gather:say 照找素材那一支走，
        殘譜、回體丹、打探、破境丹一個不少。"""
        s, c = self.state, self.content
        p = s.player
        gather_mode, _, branch_id = mode.partition(":")
        if mode == explore_modes.GATHER and explore_modes.layered(c, s.world, c.locations[p.location]):
            return [explore_modes.GATHER_PICK]
        p.stamina -= self._action_costs()["explore"]
        promotion = None if precise.on(c, s.world) else ranks.summons_event(s, c)  # 一類一顆（2.10）：不再被晉升奇遇換掉，應召照舊
        if promotion is not None:
            return self._present(c.events[promotion])
        p.explore_seq += 1
        roll = functools.partial(explore_modes.rng_for, self.world.get_season_number(), p.name, p.explore_seq)
        loc = c.locations[p.location]
        if mode == explore_modes.PRACTICE:  # 練功（正式季整合 2.5）：不算打探（7.3），破境丹、殘譜照擲，用途另取「練功」
            msgs = self._practice(loc, roll("練功")) + self._pill_find(roll("回體丹"))
            if c.config.forge_secrets.scrap_every_mode:
                msgs += self._scrap_find()
            return msgs + self._legend_find(roll("破境丹")) + self._seal_find(loc.id)
        if gather_mode == explore_modes.GATHER and branch_id == explore_modes.SAY:  # 「自己說」（C 段走 choose 進來，_gather_said 帶著）
            msgs = self._gather_say(loc, roll("找素材"), roll(explore_modes.SAY_ROLL)) + self._pill_find(roll("回體丹"))
        elif gather_mode == explore_modes.GATHER:
            branch = c.gather_branches.get(branch_id) if branch_id else None
            msgs = self._gather(loc, roll("找素材"), branch) + self._pill_find(roll("回體丹"))
        elif mode == explore_modes.SEEK:
            msgs = self._seek(roll("找事件"))
        else:
            msgs = self._sense_here(loc, roll("靜心感悟"))
        if c.config.forge_secrets.scrap_every_mode:  # 殘譜三種探索都擲（素材與經濟設計第三節；關著只在找事件擲，_seek）
            msgs += self._scrap_find()
        scouted = bounties.on_explore(s, c, self.world, p.location)  # 打探：三種都算（設計 3.4）
        return msgs + self._legend_find(roll("破境丹")) + scouted + self._seal_find(loc.id)

    def _gather(self, loc: Location, rng: random.Random, branch: GatherBranch | None = None) -> list[str]:
        """找素材（設計 3.1）：有頭目的地點先擲頭目戰（Config.duel.explore_chance）；撿素材（explore_modes.gather_finds）；
        城鎮以外 encounter_chance 撞上一場（_gather_fight）。
        branch（找素材分支，第 32 項；只在一類一顆開著時有）：第一句換成那條分支的，屬性的池子換成它的（深入照這裡的素材），
        數量照一定給的那一套；深入另擲一次悟意境（explore_modes.deep_insight，同一顆 rng）。"""
        s, c = self.state, self.content
        sure = precise.on(c, s.world)  # 一類一顆（2.4）：一定給、不擲頭目戰、不撞仗（頭目與那一場搬到練功）
        if branch is not None:
            msgs = [branch.line.format(place=loc.name)]
            attrs = None if branch.deep else branch.attributes
            mids = explore_modes.gather_finds(c, loc, rng, sure=True, attributes=attrs)
            found = [line for mid in mids if (line := materials.grant(s, c, mid))]
            msgs += (found or [explore_modes.GATHER_NONE]) + self._home_gather(loc, mids)
            if branch.deep:
                sensed = explore_modes.deep_insight(c, loc, rng)
                if sensed is not None:
                    msgs += [explore_modes.DEEP_LINE] + insights.learn(s, c, self.world, sensed, at=loc)
            return msgs
        boss = None if sure else duel_rules.available(s, c)
        if boss is not None and rng.random() < c.config.duel.explore_chance * renown.duel_chance(s, c):  # 名聲 4.4
            return self._duel_start(boss)
        msgs = [explore_modes.GATHER_LINE.format(place=loc.name)]
        mids = explore_modes.gather_finds(c, loc, rng, sure=sure)
        found = [line for mid in mids if (line := materials.grant(s, c, mid))]
        msgs += (found or [explore_modes.GATHER_NONE]) + self._home_gather(loc, mids)
        if not sure and explore_modes.encounter_due(c, loc, rng):
            msgs += self._gather_fight(loc, rng)
        return msgs

    def _home_gather(self, loc: Location, mids: list[str]) -> list[str]:
        """領地爭奪：人站在自家領地找素材，Config.conquest.gather_bonus_chance 的機會多一個同屬性的一階（設計 4.5；散人在開季中立的區塊也算）。
        屬性照這一下找到的第一個素材，沒找到照地點寫的第一種素材；擲骰用這一次探索自己的亂數（用途「領地」），不碰 Game.rng。
        開關關著、不在自家是空的，一個字都不變。"""
        s, c = self.state, self.content
        if not conquest.home(s, c):
            return []
        rng = explore_modes.rng_for(self.world.get_season_number(), s.player.name, s.player.explore_seq, "領地")
        if rng.random() >= c.config.conquest.gather_bonus_chance:
            return []
        pool = [m for m in [*mids, *loc.materials] if m in c.materials]
        attribute = c.materials[pool[0]].attribute if pool else None
        mid = explore_modes.one_of(c, {attribute} if attribute else set(), 1, rng)
        line = materials.grant(s, c, mid) if mid is not None else None
        return [conquest.HOME_GATHER_LINE, line] if line else []

    def _gather_say(self, loc: Location, rng: random.Random, say_rng: random.Random) -> list[str]:
        """找素材的「自己說」（第 32 項，計畫 2.3）：照模型挑的屬性一定給一份（同分支），成算＝模型分數＋悟性修正、夾 5～85
        （rules.stat_rate）；擲中了多一個同屬性一階、再照危險度擲一次二階（explore_modes.say_bonus，【預設】）。擲骰用「自己說」那一份亂數。
        紀錄寫你那一句與成算、（成功）／（失敗），不另外叫模型潤色。"""
        s, c = self.state, self.content
        text, llm_rate, attribute = self._gather_said
        rate = stat_rate(llm_rate, "wis", s, c, self.world)
        success = say_rng.random() * 100 < rate
        tag, line = check_result_line(success)
        msgs = [explore_modes.SAY_SAID.format(text=text, rate=rate_words(rate)), line]
        self._outcome(tag, line)
        mids = explore_modes.gather_finds(c, loc, rng, sure=True, attributes=[attribute])
        if success:
            mids += explore_modes.say_bonus(c, loc, say_rng, attribute)
        found = [granted for mid in mids if (granted := materials.grant(s, c, mid))]
        return msgs + (found or [explore_modes.GATHER_NONE]) + self._home_gather(loc, mids)

    def _practice(self, loc: Location, rng: random.Random) -> list[str]:
        """練功（正式季整合 2.5）：一定打一場。有頭目時先擲頭目戰（5% × 名聲倍數，renown.duel_chance）；這裡只有頭目、沒有一般對手時
        直接對上他（次數與冷卻在鈕上擋）。否則打 _gather_foe 那一路，照找素材以前撞上的那一場打（_gather_fight），不接戰後事件。"""
        s, c = self.state, self.content
        boss = duel_rules.available(s, c)
        foe = self._gather_foe(loc)
        if boss is not None and (foe is None or rng.random() < c.config.duel.explore_chance * renown.duel_chance(s, c)):
            return self._duel_start(boss)
        if foe is None:
            return [explore_modes.NO_FOE + "。"]
        tier = self._practice_tier(loc)  # 練功分級（Config.training）：心得與銀兩照級數乘，經驗不加成
        self._loot_scale = training.loot_scale(c.config.training, tier) if tier is not None else 1.0
        card = s.battle_card
        try:
            msgs = self._gather_fight(loc, rng, line=explore_modes.PRACTICE_LINE, aftermath=False)
        finally:
            self._loot_scale = 1.0
        record = next((r for r in s.battles if r.id == s.battle_card), None) if s.battle_card != card else None
        if record is not None:
            record.label = training.PRACTICE  # 戰報寫「練功」，不寫「探索遇敵」
        if tier is not None and tier >= 1 and record is not None and record.tier in team.WIN_TIERS:
            s.player.newbie_marks.add("field2")  # 新手目標：在二級以上的地方打贏一場練功
        return msgs

    def _gather_foe(self, loc: Location) -> Squad | None:
        """找素材撞上的那一路（設計 3.1）：手上有這裡的討伐懸賞、那一路不是自己人時就是它（散人不能出陣，討伐靠這裡；地點易手之後
        那一路不站在這裡也找得到，Review Focus 5）；否則是這裡不是自己陣營的隊伍裡最弱的一路（同分取先列的）。都沒有是 None。"""
        s, c = self.state, self.content
        for b in bounties.mine(s, c):
            if b.kind == "strike" and b.location == loc.id and b.squad in c.squads and not self._drills_with(c.squads[b.squad]):
                return c.squads[b.squad]
        foes = self._wild_foes(loc)
        return min(foes, key=lambda foe: foe.difficulty) if foes else None

    def _gather_fight(
        self, loc: Location, rng: random.Random, line: str = explore_modes.FOE_LINE, aftermath: bool = True
    ) -> list[str]:
        """撞上一場（設計 3.1）：照探索的野怪打（扣氣血減半、不問模型、不推大勢：_squad_encounter(wild=True)），打贏給全額的經驗、
        心得、銀兩、掉落，也算討伐懸賞的交差（寫進這一場戰報的得失，同遊歷）；打完 train_event_chance 接一則戰後事件
        （從遊歷搬過來，設計 2.4；事件池照舊叫 train）。練功（_practice）也走這裡：line 換開場那一句、aftermath=False 不接戰後事件。"""
        s, c = self.state, self.content
        squad = self._gather_foe(loc)
        if squad is None:
            return []
        msgs = [line.format(foe=squad.name, place=loc.name)] + self._squad_encounter(squad.id, wild=True)
        record = next((r for r in s.battles if r.id == s.battle_card), None)
        if record is not None and record.tier in team.WIN_TIERS:
            done = bounties.on_win(s, c, self.world, loc.id, squad.id)
            changes, notes = battlelog.split_changes(done, for_record=True)
            record.changes += changes
            record.notes += notes
            msgs += done
        if aftermath and rng.random() < c.config.train_event_chance:
            event = pick_event(s, c, "train", rng)
            if event is not None:
                msgs += self._present(event, "train")
        return msgs

    def _seek(self, rng: random.Random) -> list[str]:
        """找事件（設計 3.2）：一次性奇遇先擲 rare_explore_chance，沒中照防重複輪替抽這裡可重複的事件；殘譜與半張鑄譜在這裡擲
        （_scrap_find；Config.forge_secrets.scrap_every_mode 開著時三種探索都擲，在 _explore_mode）。事件推戰線的五折在 push_trend（source="event"）。"""
        s, c = self.state, self.content
        if event_candidates(s, c, "explore", "rare") and rng.random() < c.config.rare_explore_chance:
            msgs = self._present(pick_event(s, c, "explore", rng, "rare"), "explore")
        else:
            event = pick_event(s, c, "explore", rng, "common")
            msgs = self._present(event, "explore") if event is not None else [explore_modes.SEEK_NONE]
        return msgs if c.config.forge_secrets.scrap_every_mode else msgs + self._scrap_find()

    def _sense_here(self, loc: Location, rng: random.Random) -> list[str]:
        """靜心感悟（設計 3.3）：就是有所感（sensing.start）；沒有場景的內容照舊直接悟（同舊探索的悟意境那一支）。"""
        s, c = self.state, self.content
        if sensing.can_sense(s, c, loc):
            return sensing.start(s, c, sensing.pick_scene(loc, c, rng), rng)
        found = insights.roll_explore(loc, c, rng)
        return [f"你在{loc.name}靜下心來，看了好一陣。"] + insights.learn(s, c, self.world, found, at=loc)

    # ── 減法季探索一顆（整合設計 4.1，批 2；Config.jianfa 的 explore_one）────────────────

    def _outing_on(self) -> bool:
        """探索一顆在這一季開著（Config.jianfa 的 explore_one＋開季的章，rules.jianfa），而且不在序章裡（序章照舊按「探索」走寫好的那幾步）。
        開著時選單上只剩一顆「探索」（act:explore，出門一趟），不畫三選一（explore:*）、尋敵、城裡操練。"""
        return jianfa(self.content, self.state.world, "explore_one") and not prologue_rules.active(self.state, self.content)

    def _outing_foe(self, loc: Location, kind: str) -> tuple[str | None, Squad | None]:
        """遭遇拍打誰（設計 4.1，PM 2026-10-25 第 3 件）：手上有這裡的討伐懸賞、那一路不是自己人，就是它（bounty；易手了也找得到，同
        _gather_foe）；**可是對那一路的勝算是必敗時不算**（2e，FB-880，企劃者 2026-10-26「勝算是必敗時不強制打懸賞，照原本的表抽」）：
        問的是鈕上寫勝算的同一個函式（odds，固定種子、不碰 Game.rng），必敗就當這一處沒有這張懸賞，往下照沒有懸賞時挑；變強到不再必敗
        就又是它。自家營寨（營類、此刻歸自己這一邊、有自家的隊伍）是跟同袍比劃（spar，_sortie_host 那一路）；否則這裡此刻站的、
        不是自家的隊伍裡最弱的一路（foe）；城類的地點自己沒有對手才換成地痞（town，Config.jianfa.town_foes 的第一路）。都沒有是 (None, None)。"""
        s, c = self.state, self.content
        for b in bounties.mine(s, c):
            if b.kind == "strike" and b.location == loc.id and b.squad in c.squads and not self._drills_with(c.squads[b.squad]):
                if self.odds(b.squad) == mapdata.LOSE_WORD:
                    continue  # 打不贏的懸賞不強制：這一處當作沒有它（沒有放棄，手上還揭著）
                return "bounty", c.squads[b.squad]
        side = self._side()
        if kind == explore_one.CAMP and side is not None and territory.controller(s.world, c, loc.id) == side:
            host = self._sortie_host(loc)
            if host is not None:
                return "spar", host
        foes = self._wild_foes(loc)
        if foes:
            return "foe", min(foes, key=lambda foe: foe.difficulty)  # 同分取這裡列的第一路
        if kind == explore_one.TOWN:
            sid = next((sid for sid in c.config.jianfa.town_foes if sid in c.squads), None)
            if sid is not None:
                return "town", c.squads[sid]
        return None, None

    def _outing_weights(self, loc: Location, *, has_foes: bool, bounty_here: bool, hidden: set[str] | None = None) -> dict[str, int]:
        """這一處這一趟四類事的比重（explore_one.weights：表照標籤或 explore_mix、危險度、懸賞、有沒有對手），再把此刻做不到的歸 0：
        抽不到事件（一次性、可重複的都沒有）事件是 0，悟不出（insights.explore_gives 是空的，或這個遊戲日在這裡選錯過做法）感悟是 0——
        那一份照比重分給其餘的。只讀，不擲骰。hidden：藏起來的事件（events.hidden_events），替好幾處一起問時（map_mostly）先算好給。"""
        s, c = self.state, self.content
        weights = explore_one.weights(c.config.jianfa, loc, has_foes=has_foes, bounty_here=bounty_here)
        # 一次性與奇遇（rare）加可重複的（common）就是全部（pool=None），一趟只問一次，找到一則就夠
        if not event_rules.has_event_candidates(s, c, "explore", hidden=hidden):
            weights[explore_one.EVENT] = 0
        if not insights.explore_gives(loc, c) or sensing.missed_today(s, c, loc):
            weights[explore_one.INSIGHT] = 0
        return weights

    def _outing_plan(self, loc: Location, *, hidden: set[str] | None = None) -> OutingPlan:
        """這一處此刻出門一趟怎麼抽（OutingPlan）：比重照 _outing_weights。這裡沒有一般對手（也沒有討伐懸賞）遭遇就是 0，那一份分給其餘三類；
        頭目不算對手（FB-815：只有頭目的地點不是一定撞上他）——他是這一趟另外擲的（_explore_one：5% × 名聲倍數），擲中那一趟才是
        遭遇。接了討伐懸賞：這一趟就是遭遇（weights 只有遭遇，explore_one.encounter_only）；對懸賞那一路是必敗時不算（_outing_foe，2e），
        整份（對手、頭目、比重、小字）跟沒有這張懸賞時一樣。只讀，不擲骰（判勝算也不碰 Game.rng）。"""
        s, c = self.state, self.content
        cfg = c.config.jianfa
        kind = explore_one.kind_of(cfg, loc).kind
        how, foe = self._outing_foe(loc, kind)
        boss = None if how == "bounty" else duel_rules.available(s, c)  # 接了懸賞：遭遇就是懸賞那一路，不擲頭目
        weights = self._outing_weights(loc, has_foes=foe is not None, bounty_here=how == "bounty", hidden=hidden)
        return OutingPlan(kind=kind, weights=weights, how=how, foe=foe, boss=boss, hint=explore_one.hint_of(kind, how, weights))

    def mostly_here(self) -> str:
        """四格探索那一格的小字（/api/main 的 mostly；雲端批 5 的欄位，網頁 m.mostly）：探索一顆開著時是出門一趟的那一份
        （_outing_plan 的 hint：地點種類的字，招牌類此刻的比重是 0 才改寫比重最高的那一類；接了討伐懸賞「…有賞」、自家營寨「同袍比劃」，跟鈕上括號那一段同一個字）；
        關著照雲端的 mapdata.mostly_here（照地點的小圖）。在路上是空字串。"""
        plan = self.outing_plan()
        if plan is not None:
            return plan.hint
        return mapdata.mostly_here(self.state, self.content)

    def outing_plan(self) -> OutingPlan | None:
        """探索一顆開著時，這裡此刻出門一趟怎麼抽（假人打分數、量表讀；同 _outing_plan）；關著、序章裡、在路上是 None。"""
        p = self.state.player
        if not self._outing_on() or p.journey is not None:
            return None
        return self._outing_plan(self.content.locations[p.location])

    def map_mostly(self) -> dict[str, str] | None:
        """輿圖第一層名字旁的兩個字（2f，FB-886；PM 2026-10-26「照這一處自己的比重寫，跟鈕上同一套」）：每一個畫得出來的地點，這個人**站過去之後**
        鈕上小字的最後兩個字（explore_one.tail_of：多事、多敵、多料、多悟、參半，接了這裡的討伐懸賞「有賞」、自家營寨「比劃」）。
        替每一處「假裝站過去」叫 _outing_plan（鈕、四格、行動列那一行讀的同一個函式，不另寫一份判斷）：危險度、有沒有對手（看的人是哪一邊、
        這一處此刻歸誰）、懸賞、自家營寨、抽不到事件、悟不出感悟都算進去，也就不看他現在站在哪。探索一顆沒開著、序章裡（探索鈕是寫好的幾步，
        沒有比重可看）是 None，名字旁照舊（mapdata.place_mostly）。只讀，不擲骰、不動存檔（站回原處），在路上也算得出。"""
        if not self._outing_on():
            return None
        out: dict[str, str] = {}
        hidden = event_rules.hidden_events(self.state, self.content)  # 藏起來的事件不看站在哪，四十幾處共用一份，不必每處重算
        for loc_id in mapview.open_places(self.state, self.content):
            with self._standing_at(loc_id):
                plan = self._outing_plan(self.content.locations[loc_id], hidden=hidden)
            out[loc_id] = explore_one.tail_of(plan.how, plan.weights)
        return out

    @contextlib.contextmanager
    def _standing_at(self, loc_id: str):
        """裡面的讀取都當作這個人已經站在 loc_id（沒有在路上）：state 換成一份淺拷貝（只有 player 的位置與路上換掉，其餘還是同一批物件，不動它們），
        出了範圍（含丟例外）換回原來那一份。給「站過去之後會怎樣」的只讀查詢用（map_mostly）：事件抽得到嗎、對手是誰、勝算的地利都看
        state.player.location，一處一處改函式簽名既費事又會漏，換一份 state 才跟真的站過去一樣。範圍裡不准寫。"""
        home = self.state
        self.state = home.model_copy(update={"player": home.player.model_copy(update={"location": loc_id, "journey": None})})
        try:
            yield
        finally:
            self.state = home

    def _outing_option(self, loc: Location) -> Option:
        """探索一顆的鈕：「探索（體力 15・城裡多事）」，括號裡最後那一段是這一處多半給什麼（同 /api/main 的 mostly，mostly_here）。"""
        return self._cost_option("act:explore", "探索", self.content.config.jianfa.explore_stamina, note=self._outing_plan(loc).hint)

    def _explore_one(self) -> list[str]:
        """出門一趟（減法季探索一顆，整合設計 4.1）：扣 explore_stamina（15），照這一處的比重（_outing_plan）抽**一件事**
        （explore_one.draw；2d，企劃者 2026-10-26「只抽一件事情」，同天體力改 15）：遭遇、事件、素材、感悟其中一件，感悟不連兩趟，
        接了討伐懸賞這一趟就是遭遇（打懸賞那一路，交了差回原表）。素材與遭遇當場結算；事件或感悟端出來等玩家選；遭遇上撞到頭目時，
        那一趟收在頭目戰。回來寫成一段（content/outing_lines.json：出門那一句加這一件事的一句），後面一行「得：…　失：…」；
        這一趟沒收穫補一個一階素材；收尾照舊擲回體丹、殘譜、破境丹、打探懸賞、玉璽碎片。
        擲骰都用自己的亂數（explore_one.rng_for），不碰 Game.rng（頭目戰與仗本身照它們原本的）。"""
        s, c = self.state, self.content
        p, cfg = s.player, c.config.jianfa
        loc = c.locations[p.location]
        plan = self._outing_plan(loc)
        p.stamina -= cfg.explore_stamina
        p.explore_seq += 1
        roll = functools.partial(explore_one.rng_for, self.world.get_season_number(), p.name, p.explore_seq)
        last_loc, _, last_kind = p.outing_last.partition(":")
        weights = plan.weights
        if plan.boss is not None and plan.foe is None and plan.how != "bounty":
            # 這裡只有頭目、沒有一般對手（官軍在長社，FB-815）：這一趟照 5% × 名聲倍數擲一次他；擲中了這一趟就是遭遇（頭目擋路），
            # 沒擲中就當這裡沒有對手——遭遇那一格已經分給其餘三類（plan.weights 的遭遇是 0）
            if roll("頭目").random() < c.config.duel.explore_chance * renown.duel_chance(s, c):
                weights = explore_one.encounter_only()
        beat = explore_one.draw(roll("拍"), weights, last_choice=last_kind if last_loc == loc.id else None)
        # 一條線（特殊事件）：在開頭的地方擲中了，這一趟就是那條線的第一段（關著、沒有線不擲；用自己的亂數，不動拍子）
        boost = outing_rules.rare_boost(s, c)  # 走一趟：段數越多，稀有的越容易來（不在路上是 1）
        strand = storyline.roll_start(s, c, roll("奇事"), boost=boost)
        if strand is not None:
            beat = explore_one.EVENT
        say, lines = roll("段落"), c.outing_lines
        story = [explore_one.line(lines, "open", plan.kind, say, place=loc.name)]
        if self._draft is not None and not self._draft.tag:
            self._draft.tag = explore_one.BEAT_WORDS[beat]
        before = len(self._draft.changes) if self._draft is not None else 0
        out: list[str] = []
        got_any, boss, choice = False, None, ""
        self._outing_close = set()
        self._beat = {"kind": beat, "rare": strand is not None, "won": None}  # 走一趟讀這一段是什麼（_outing_walk）
        rng = roll("結算")
        if beat == explore_one.MATERIAL:  # 素材：找素材一定給的那一套（不展開分支；屬性照這裡的素材）
            mids = explore_modes.gather_finds(c, loc, rng, sure=True, boost=boost)
            self._beat["rare"] = any(c.materials[m].tier >= 2 for m in mids if m in c.materials)
            top = next((c.materials[m].name for m in mids if m in c.materials and c.materials[m].tier >= outing_rules.FEAT_TIER), "")
            if top:  # 稀世的素材：這一趟收的時候記一則行狀（outing.FEAT_ANNAL）
                self._beat["feat"], self._beat["feat_kind"] = top, outing_rules.FEAT_TREASURE
            found = [granted for mid in mids if (granted := materials.grant(s, c, mid))]
            found += self._home_gather(loc, mids)  # 領地爭奪：站在自家領地多給的那一個
            items = explore_one.items_of(found, materials.GRANT_PREFIX)
            if items:
                story.append(explore_one.line(lines, "material", "found", say, place=loc.name, item=items))
                got_any = True
            out += found
        elif beat == explore_one.ENCOUNTER:
            if plan.boss is not None and (plan.foe is None or rng.random() < c.config.duel.explore_chance * renown.duel_chance(s, c)):
                boss = plan.boss  # 頭目擋路（5% × 名聲倍數；這裡只有頭目時直接對上）：頭目戰收在這一趟最後
                story.append(explore_one.line(lines, "encounter", "boss", say, place=loc.name, foe=self._boss_face(boss)))
                got_any = True
            elif plan.foe is not None:
                msgs, key, won = self._outing_fight(loc, plan)
                self._beat["won"], self._beat["lost"] = won, key in ("lose", "town_lose")
                self._beat["foe"] = outing_rules.foe_look(plan.foe)  # 畫面照它挑對手的圖（黃巾、官兵、家丁、盜匪、猛獸）
                if won and self._outing_upset:  # 開打前勝算凶險以下還打贏：以弱勝強，這一趟收的時候記一則行狀
                    self._beat["feat"], self._beat["feat_kind"] = plan.foe.name, outing_rules.FEAT_UPSET
                story.append(explore_one.line(lines, "encounter", key, say, place=loc.name, foe=plan.foe.name))
                out += msgs
                got_any = won
        elif beat == explore_one.EVENT:  # 要選的：事件（野類偏旅人那一類）；擲中了一條線就是那條線的第一段
            msgs = self._story_begin(strand) if strand is not None else self._outing_event(loc, plan.kind, rng, boost)
            if msgs:
                story.append(explore_one.line(lines, "event", "lead", say, place=loc.name))
                out += msgs
                got_any, choice = True, beat
        elif beat == explore_one.INSIGHT:  # 要選的：感悟（有所感）
            story.append(explore_one.line(lines, "insight", "lead", say, place=loc.name))
            out += self._sense_here(loc, rng)
            got_any, choice = True, beat
        if boss is not None:
            out += self._duel_start(boss)
        if not got_any:  # 這一趟沒收穫（素材找不到料、遭遇打輸或沒對手）：補一個一階素材（設計 4.1【PM】）
            kinds = {c.materials[m].attribute for m in loc.materials if m in c.materials}
            mid = explore_modes.one_of(c, kinds, 1, roll("補"))
            granted = materials.grant(s, c, mid) if mid is not None else None
            if granted:
                story.append(explore_one.line(lines, "close", "empty", say, place=loc.name,
                                              item=explore_one.items_of([granted], materials.GRANT_PREFIX)))
                out.append(granted)
        # 收尾的幾樣先算（打探懸賞交差在 45 級換成心得時，那一句「境界已到」也在這裡面，段落結尾要看得到它，FB-818）
        extras = self._pill_find(roll("回體丹")) + self._scrap_find() + self._legend_find(roll("破境丹"))
        extras += bounties.on_explore(s, c, self.world, loc.id) + self._seal_find(loc.id)  # 打探懸賞：出門一趟就算
        if any(line.startswith(team.CAPPED_XINDE.partition("，")[0]) for line in out + extras):
            self._outing_close.add("capped")
        for key in explore_one.LINE_KEYS["close"]:  # 段落結尾：疲勞打了折、對手配不上你、境界已到（三道閘，設計 4.2）
            if key in self._outing_close:
                story.append(explore_one.line(lines, "close", key, say, place=loc.name))
        p.outing_last = f"{loc.id}:{choice}" if choice else ""
        ledger = self._outing_ledger(out + extras, before)
        return ["".join(story)] + ([ledger] if ledger else []) + out + extras

    def _outing_fight(self, loc: Location, plan: OutingPlan) -> tuple[list[str], str, bool]:
        """遭遇拍打的那一場：回（訊息, outing_lines 的 encounter 鍵, 打贏了沒）。自家營寨跟同袍比劃：不打、不掉東西，照 _sortie_host 那一路
        的心得經驗 camp_spar_share（三成，_drill_gains；算仗）。其餘照探索的野怪打（_squad_encounter(wild=True)：扣氣血減半、不問模型、不推大勢），戰報標
        「出門一趟・遭遇」；城裡的地痞戰利（銀兩、心得、掉的素材）乘 town_loot_scale、不算討伐；其餘打贏算討伐懸賞的交差。"""
        s, c = self.state, self.content
        cfg, foe = c.config.jianfa, plan.foe
        self._outing_upset = False
        gate = self._fight_gate(foe)  # 三道閘的前兩道（疲勞、對手配不配得上你）：這一場的經驗、心得、銀兩、掉的素材一起乘
        if plan.how == "spar":  # 對手那一路心得、經驗的 camp_spar_share（三成）乘三道閘的倍數（PM 2026-10-26：以前全額）
            return self._drill_gains(foe, cfg.camp_spar_share * gate, "camp_spar", echo=False), "spar", True  # 心得只由草稿記（FB-830）
        town = plan.how == "town"
        self._loot_scale = cfg.town_loot_scale if town else 1.0
        self._gate_scale = gate
        self._drop_scale = gate * self._loot_scale
        card = s.battle_card
        try:
            msgs = self._squad_encounter(foe.id, wild=True)
        finally:
            self._loot_scale = self._drop_scale = self._gate_scale = 1.0
        record = next((r for r in s.battles if r.id == s.battle_card), None) if s.battle_card != card else None
        won = record is not None and record.tier in team.WIN_TIERS
        # 以弱勝強：打贏了才回頭看開打那一刻的威力對這一路的勝算（team.odds_word，固定種子、不碰 Game.rng；沒打贏、沒懸賞的趟都不算勝算，2e）
        self._outing_upset = won and team.odds_word(record.our_power, foe) in outing_rules.FEAT_ODDS
        if not won:
            self._outing_close.discard("outlevel")  # FB-881：「對手配不上你，所得有限」只在打贏、真的因為對手檔打了折才寫；輸了、平手不寫
        if record is not None:
            record.label = battlelog.OUTING_LABEL
        if won and not town:
            done = bounties.on_win(s, c, self.world, loc.id, foe.id)
            changes, notes = battlelog.split_changes(done, for_record=True)
            record.changes += changes
            record.notes += notes
            msgs += done
        if won and not town and (self._practice_tier(loc) or 0) >= 1:
            s.player.newbie_marks.add("field2")  # 新手目標：在二級以上的地方打贏一場（這一季沒有尋敵，遭遇拍打贏也算，FB-816）
        tier = record.tier if record is not None else "落敗"
        if town:
            return msgs, "town_win" if won else "town_draw" if tier == "僵持" else "town_lose", won  # 平手有自己的句子（FB-819）
        return msgs, "win" if won else "draw" if tier == "僵持" else "lose", won

    def _fight_gate(self, foe: Squad) -> float:
        """遭遇拍這一場的倍數（減法季三道閘的前兩道，整合設計 4.2；Config.jianfa 的 drill_gates）：今天第幾場（PlayerState.fights_today，
        台灣 00:00 換日、照 _pill_day）的疲勞（growth.fatigue_factor：前 drill_full_per_day 場 1，之後每場 ×drill_decay，最低 drill_floor）
        乘對手的檔（growth.outlevel_factor：對手難度的檔比自己等級的檔低一檔 0.5、兩檔 0.1）。關著是 1、也不記場數（存檔一個鍵都不多）。
        打了折的那一道記進 _outing_close（段落結尾那一句：tired、outlevel）；outlevel 在 _outing_fight 看到這一場沒打贏時收回（FB-881：
        輸了、平手沒拿到東西，不是因為對手檔）。"""
        s, c = self.state, self.content
        if not jianfa(c, s.world, "drill_gates"):
            return 1.0
        cfg, p = c.config.jianfa, s.player
        today = self._pill_day()
        n = growth.nth_fight(fight_day=p.fight_day, fights_today=p.fights_today, today=today)
        p.fight_day, p.fights_today = today, n
        tired = growth.fatigue_factor(cfg, n)
        matched = growth.outlevel_factor(cfg, p.member.level, foe.difficulty)
        if tired < 1:
            self._outing_close.add("tired")
        if matched < 1:
            self._outing_close.add("outlevel")
        return tired * matched

    def fatigue_next(self) -> float:
        """下一場遭遇的疲勞倍數（同 _fight_gate 的第一道，只讀、不記場數）：假人打探索的分數、量表讀；三道閘關著是 1。"""
        s, c = self.state, self.content
        if not jianfa(c, s.world, "drill_gates"):
            return 1.0
        p = s.player
        n = growth.nth_fight(fight_day=p.fight_day, fights_today=p.fights_today, today=self._pill_day())
        return growth.fatigue_factor(c.config.jianfa, n)

    def _outing_event(self, loc: Location, kind: str, rng: random.Random, boost: float = 1.0) -> list[str]:
        """事件拍（設計 4.1）：一次性奇遇先擲 rare_explore_chance（可重複的一則都沒有時直接是它）；沒中照防重複輪替抽這裡可重複的事件，
        野類的地點有標了「旅人」的就在那幾則裡抽（救助旅人那一類）。抽到就端出來（pending_event），一則都沒有是空的。"""
        s, c = self.state, self.content
        common = event_candidates(s, c, "explore", "common")
        if event_candidates(s, c, "explore", "rare") and (rng.random() < c.config.rare_explore_chance * boost or not common):
            if self._beat is not None:
                self._beat["rare"] = True
            return self._present(pick_event(s, c, "explore", rng, "rare"), "explore")
        travelers = [e for e in common if explore_one.TRAVELER in e.tags] if kind == explore_one.WILD else []
        event = event_rules.pick_from(s, c, travelers, "explore", rng) if travelers else None
        event = event or pick_event(s, c, "explore", rng, "common")
        return self._present(event, "explore") if event is not None else []

    def _outing_ledger(self, msgs: list[str], since: int) -> str:
        """出門一趟最後那一行「得：…　失：…」：這一趟的訊息裡撿到的東西（「獲得 精鐵砂 ×1」，只列這種「名 ×數量」的；破境丹、回體丹
        那一句說明不是一樣東西，帳上只列它後面的「破境丹 +1」，FB-831）與數值變化，加上草稿裡另外補的（仗的經驗，since 之後那幾筆）；
        同一個標籤加總，增加的寫在「得」、減少的（與內傷）寫在「失」。"""
        extra = self._draft.changes[since:] if self._draft is not None else []
        changes, notes = battlelog.split_changes(msgs)
        totals = journal.combine_changes(changes + extra)
        grants = (note.removeprefix(materials.GRANT_PREFIX) for note in notes if note.startswith(materials.GRANT_PREFIX))
        items = explore_one.merge_items(item for item in grants if explore_one.is_item(item))
        gains = items + [ch for ch in totals if journal.change_class(ch) == "tx-up"]
        losses = [ch for ch in totals if journal.change_class(ch) == "tx-down"]
        return explore_one.ledger(gains, losses)

    # ── 走一趟（tianxia/outing.py；企劃者 2026-10-29～30）──

    def outing_go(self, total: int = 0) -> list[str]:
        """走一趟：total 是段數（Config.jianfa.outing_segments）就出發；0 是停在要選的事上、選完之後接著走。
        出發要閒著（選單上的探索按得下去）、體力夠走完這麼多段；每一段照舊扣一次探索的體力，沒走的段不扣。
        回的訊息只有拒絕的那一句：沿路發生的事都在 PlayerState.outing（outing.view）與每一段自己的江湖紀錄裡。"""
        s, c = self.state, self.content
        p = s.player
        if not outing_rules.on(c, s) or prologue_rules.active(s, c) or p.journey is not None:
            return ["（此刻無法這麼做。）"]
        if total:
            if total not in outing_rules.segments(c):
                return ["（此刻無法這麼做。）"]
            if self._explore_ready() is None:
                return ["（此刻無法這麼做。）"]
            if p.stamina < outing_rules.cost(c, total):
                return ["（體力不夠走這麼多段。）"]
            p.outing = Outing(place=p.location, total=total, n=(p.outing.n + 1) if p.outing is not None else 1)
        else:
            trip = p.outing
            if trip is None or trip.end:
                return ["（此刻無法這麼做。）"]
            if trip.place != p.location:
                trip.end = outing_rules.LEFT
                return [outing_rules.END_LINES[outing_rules.LEFT]]
        return self._outing_walk()

    def _explore_ready(self) -> Option | None:
        """選單上的探索此刻按得下去就回那一顆（閒著、體力夠一段）；不然是 None。"""
        option = {o.id: o for o in self.options(odds=False, tick=False)}.get(IDLE_MARK)
        return option if option is not None and option.enabled else None

    def outing_view(self) -> dict | None:
        """/api/main 的 outing（outing.view）加 can_go：停在要選的事上的那一趟，事情選完了、可以接著走（網頁照它自己送「接著走」；
        最後一段是要選的事時，接著走只是把這一趟收成「走完」）。關著是 None。"""
        view = outing_rules.view(self.state, self.content)
        if view is not None and view["trip"] is not None:
            trip = view["trip"]
            trip["can_go"] = self.outing_can_go()
            if trip["can_say"]:
                trip["ink"] = self.outing_ink_left()
                trip["ink_item"] = self.wallet.item_for(outing_rules.INK)
                trip["people"] = [o.player.name for o in social.here(self)]  # 結算卡的「此地還有」：點名字開玩家卡打招呼、邀結伴
            trip["admin"] = self.is_admin()
        return view

    def outing_can_go(self) -> bool:
        """停下來的那一趟可以接著走了：事情選完了（探索回到選單上；體力不夠一段也算，接著走會把它收成「累了」）。"""
        if outing_rules.active(self.state) is None:
            return False
        return IDLE_MARK in {o.id for o in self.options(odds=False, tick=False)}

    def _outing_walk(self) -> list[str]:
        """一段一段走（每一段是一次 choose(act:explore)，各寫各的江湖紀錄）：端出要選的事就停；打輸、氣血低於 outing_turn_back
        回頭；體力不夠一段也回頭。走完了寫 end。"""
        s, c = self.state, self.content
        p, cfg = s.player, c.config.jianfa
        trip = p.outing
        while trip.done < trip.total and not trip.end:
            if self._explore_ready() is None:
                if IDLE_MARK in {o.id for o in self.options(odds=False, tick=False)}:
                    trip.end = outing_rules.TIRED  # 探索在選單上但灰了：體力不夠一段
                break  # 不在選單上：還有事要選（不該走到這裡；保險）
            self._beat = None
            msgs = self.choose(IDLE_MARK)
            beat, self._beat = self._beat or {"kind": explore_one.MATERIAL, "rare": False, "won": None}, None
            lines = [m for m in msgs if isinstance(m, str)]
            ledger = lines[1] if len(lines) > 1 and lines[1].startswith(("得：", "失：")) else ""
            stop = IDLE_MARK not in {o.id for o in self.options(odds=False, tick=False)}
            trip.done += 1
            trip.beats.append(OutingBeat(kind=beat["kind"], text=lines[0] if lines else "", ledger=ledger, rare=bool(beat["rare"]),
                                         won=beat["won"], stop=stop, feat=beat.get("feat", ""), feat_kind=beat.get("feat_kind", ""),
                                         foe=beat.get("foe", "")))
            now, cap = team.member_neili(c, p.member, team.con_of(s, c, self.world, PLAYER), season=s.world)
            if beat.get("lost"):
                trip.end = outing_rules.LOST
            elif cap > 0 and now < cap * cfg.outing_turn_back:
                trip.end = outing_rules.HURT
            if stop:
                break
            if trip.end != outing_rules.LOST:
                self._outing_trace(trip)
        if not trip.end and trip.done >= trip.total and IDLE_MARK in {o.id for o in self.options(odds=False, tick=False)}:
            trip.end = outing_rules.DONE  # 最後一段端出要選的事時先不收：選完、接著走那一下才收
        if trip.end:  # 撿到稀世的東西、以弱勝強（Joy 10/30：只有這種才值得記）：一段一則行狀、世界記事一筆（此地舊事、人物對話讀得到）
            place = c.locations[trip.place].name if trip.place in c.locations else trip.place
            for b in trip.beats:
                if b.feat:
                    annals.note(s, c, annals.DEED, outing_rules.FEAT_ANNAL[b.feat_kind].format(place=place, what=b.feat), 3, place=place)
                    deeds.record(s, c, outing_rules.DEED_KIND, outing_rules.FEAT_DEED[b.feat_kind].format(name=p.name, place=place, what=b.feat),
                                 place=trip.place, actors=[p.name])
        return []

    def _outing_trace(self, trip: Outing) -> None:
        """一段走完、沒停下：擲一下路上有沒有看到東西（outing_trace_chance）——這一處有別人、這一趟還沒揮過手的話先是遠處有人揮手，
        不然是一則別人的留言。一趟最多 outing_trace_cap 行，不佔段數。亂數另起（outing.trace_rng），Game.rng 一個都不動。"""
        c = self.content
        if outing_rules.traces_left(trip, c) <= 0:
            return
        rng = outing_rules.trace_rng(self.state, trip)
        if rng.random() >= c.config.jianfa.outing_trace_chance:
            return
        beat = None
        if not trip.waved:
            beat = outing_rules.wave_beat([o.player.name for o in social.here(self)], rng)
            trip.waved = beat is not None
        if beat is None:
            beat = outing_rules.seen_beat(self.state, c, trip, rng)
        if beat is not None:
            trip.beats.append(beat)

    def outing_say(self, preset: int = -1, text: str = "", verdict: str = "") -> list[str]:
        """走完一趟在這一處留一句（outing.say_ok）：preset 是預設句的第幾句（免費）；不然是自己寫的 text（伺服器量過長度、
        鎖外審過，verdict 是模型的判斷），過字表（speech.problem，同名帖自題那一套），用掉一張題壁墨（商城 inscribe）。
        成了刻進這一處（outing.inscribe）、寫一則江湖紀錄；不成只回一句、什麼都不動。"""
        s, c = self.state, self.content
        if not outing_rules.on(c, s):
            return ["（此刻無法這麼做。）"]
        trip = outing_rules.say_ok(s)
        if trip is None:
            p = s.player
            return [outing_rules.SAY_AGAIN if p.outing is not None and p.outing.said else outing_rules.SAY_NOT_HERE]
        token = None
        if 0 <= preset < len(outing_rules.PRESETS):
            line, is_preset = outing_rules.PRESETS[preset], True
        else:
            line, is_preset = speech.clean(text), False
            if not line:
                return [outing_rules.SAY_EMPTY]
            problem = speech.problem(line, c, speech.MOTTO, c.config.jianfa.outing_say_max, verdict)
            if problem is None and any(word in line for word in tavern_rules.BANNED_WORDS):
                problem = speech.BLOCKED  # 同酒肆題壁：牆上不寫這幾個字
            if problem:
                return [problem]
            left = self.wallet.tokens(outing_rules.INK)
            if not left:
                return [outing_rules.NO_INK]
            token = left[0]
        place = c.locations[trip.place].name if trip.place in c.locations else trip.place
        item = outing_rules.inscribe(s, c, line, preset=is_preset)
        self._save_season()  # 留言刻在全服這一季（WorldState.inscriptions），不寫回共用賽季的話下一次重讀就沒了
        if token is not None:
            self.wallet.consume(outing_rules.INK, place=trip.place, inscription=item.id)  # 用掉的就是上面查到的那一張（最舊的）
        said = outing_rules.SAY_DONE.format(place=place, text=line)
        journal.add_entry(s, JournalEntry(time=s.world.time, title=outing_rules.SAY_TITLE, lines=[said],
                                          changes=[] if token is None else ["題壁墨 -1"]))
        return self._log([said])

    def outing_tale_request(self) -> outing_rules.TaleRequest | list[str]:
        """遊記的 A 段（只讀）：這一趟收了、還沒請過模型就開單；不然回一句（不叫模型）。"""
        req = outing_rules.tale_request(self.state, self.content)
        return ["（此刻無法這麼做。）"] if req is None or not outing_rules.on(self.content, self.state) else req

    def outing_set_tale(self, text: str | None, request: outing_rules.TaleRequest) -> list[str]:
        """遊記的 C 段：還是同一趟（outing.same_trip）才收；text 是 None（叫不動、不合用）就記成請過了、畫面照用模板。"""
        trip = outing_rules.same_trip(self.state, request)
        if trip is None:
            return []
        trip.tale, trip.tale_done = text or "", True
        return []

    def outing_ink_left(self) -> int:
        """手上還沒用掉的題壁墨幾張；商城關著是 0。"""
        return len(self.wallet.tokens(outing_rules.INK))

    def admin_erase_inscription(self, ins_id: int) -> list[str]:
        """管理者抹掉一則留言（路上那一行的 ref）。不是管理者、沒有這一則都回同一句「此刻無法」。"""
        if not self.is_admin() or not outing_rules.erase(self.state, ins_id):
            return ["（此刻無法這麼做。）"]
        self._save_season()
        return self._log([outing_rules.ERASED])

    def is_idle(self) -> bool:
        """此刻閒著（切磋、論武、假人答論武都問它）：選單上有探索（IDLE_MARK）——不在路上、沒有事件、對話、店面的選單擋著、不在開打的決戰裡。
        減法季探索一顆開著時「探索」照舊是 act:explore、出現在同樣的那幾種選單上，判斷不必換訊號；序章另外擋（呼叫端）。"""
        return IDLE_MARK in {o.id for o in self.options(odds=False, tick=False)}

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
        if sortie.on(self.content):  # 出陣：只有攻才打，對手是 _sortie_foes；守、散人沒有對手
            loc_mode = self._sortie_mode(loc)
            return self._sortie_foes(loc) if loc_mode == "attack" else []
        base = territory.squads_at(self.state.world, self.content, loc.id)  # 地盤易手：站的照控制方（關著時就是 loc.enemies）
        extra = orders.extra_enemies(self.state, self.content, loc.id, self._side())
        return base + [sid for sid in extra if sid not in base] if extra else base

    def _order_options(self, loc: Location) -> list[Option]:
        """軍令的兩個行動（計畫 T6）：在有戰線的地方做第 1 階守勢行動；在護糧的起點接糧車。開關關著、散人沒有。"""
        s, c = self.state, self.content
        p = s.player
        if not orders.active(s, c) or p.faction is None:
            return []
        opts: list[Option] = []
        duty = c.orders.duties.get(p.faction)
        if duty is not None and front_of(c, loc.id) is not None:
            opts.append(self._duty_option(duty.name))
        escort = orders.escort_at(s, c, self._side(), loc.id)  # 豪強分屬兩軍：依附那一軍的護糧
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

    def _duty_option(self, name: str) -> Option:
        """守勢行動的鈕。出陣開著時每用一次扣一次出陣次數（PM 2026-10-14：跟攻、守共用每日的次數），鈕上寫今天還能幾次、
        用完灰掉、寫跟出陣同一句；關著照舊。領地爭奪在這一季生效時，站在不是自家的區塊（別人的、沒佔下的中立地）灰掉寫原因，
        按下去不扣體力與次數、不推線、不記守城（裁決 24；choose 照選單驗，灰的按不下去）。"""
        c = self.content
        cost = c.config.duty_stamina
        problem = sortie.duty_problem(c, self.state.world, self._side(), self.state.player.location)
        if problem:
            return Option(id="act:duty", label=f"{name}（{problem}）", enabled=False)
        if not sortie.on(c) or self.duel_on():  # 約戰開著（減法季批 3b）：收進此地、不佔出陣的次數
            return self._cost_option("act:duty", name, cost)
        left = self.sorties_left()
        if left <= 0:
            return Option(id="act:duty", label=f"{name}（{sortie.USED_UP.format(n=c.config.sortie.per_day)}）", enabled=False)
        return self._cost_option("act:duty", name, cost, note=sortie.LEFT_NOTE.format(n=left))

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
            if rank_actions.left(s, c, action) <= 0:  # 7 天濃縮季照段記、寫「這一段」（calendar.week_word，FB-503）
                this = calendar.week_word("this_short", c, s.world)
                opts.append(Option(id=option_id, enabled=False, label=f"{action.name}（{this}已經做滿 {action.weekly} 次）"))
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
        return push.room(s.player.pushed, day, trend_id, self.daily_push_cap())

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

    def _order_credit(self, *, side: str | None = None, **kw) -> list[str]:
        """替自己記一次軍令（orders.credit）；真的記到了就推新手引導的「完成一次軍令的個人部分」（計畫 T6 Task 8）。
        達成時陣營軍情列的前三名一律寫名號（傳聞分層第七節：陣營軍情一律具名），所以不給 shown。
        side 不給就是此刻的陣營；約戰結算（FB-856）給貼（應）約戰那一刻替哪一軍出力，豪強窗內改幫也不搬帳。"""
        s, c = self.state, self.content
        msgs = orders.credit(s, c, side or self._side(), s.player.name, **kw)  # 豪強分屬兩軍：記在依附那一軍的軍令上
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
        duel = self.duel_on()  # 約戰開著（減法季批 3b；企劃者 2026-10-24 第 2 件）：收進此地——不佔出陣、不推線、不算守城，一天記一點貢獻
        if sortie.on(c) and not duel:  # 出陣開著：守勢行動算一次出陣（PM 2026-10-14，_duty_option）
            sortie.spend(p, self._pill_day())
        text = duty.text.replace("{地點}", loc.name)
        msgs = [text]
        goals = {} if duel else self._goals()  # 約戰開著：線只在約戰結算、軍令、大勢人物、事件的痕跡這幾處動（設計 4.3）
        if goals.get(front):
            msgs += self.push_trend(front, goals[front], source="duty")
        elif goals.get(GEJU) and in_chaos(s, c, front):
            msgs += self.push_trend(GEJU, 1, source="duty")
        msgs += opportunities.after_success(s, c, "duty", loc.id, self.rng)  # 收容流民（正式版乙一）
        if precise.on(c, s.world):  # 一類一顆（正式季整合 2.6）：再加跟守一樣的經驗心得（這裡自家那一路的全額；沒有自家隊伍不給，只推線）
            host = self._sortie_host(loc)
            if host is not None:
                msgs += self._drill_gains(host, 1.0)
        if duel:  # 守城軍令改成應戰守住才記（計畫 4.0 之三第 17 條）；入伍段「出一次力」照舊認它
            return msgs + self._duty_credit() + self._guide(note_action(s, c, self.world, "order"))
        credit = self._order_credit(kind="duty", location=loc.id, front=front)  # 地點：領地爭奪的守城認自家被推得最高的那一塊（裁決 11、翻地與爭搶）
        # 入伍段第 2 步「出一次力」：守勢行動不在這週軍令裡也算（FB-094：豪強第一週只有打擊，新人打不過；FB-093：巡哨、傳道就在營裡）
        return msgs + (credit or self._guide(note_action(s, c, self.world, "order")))

    def _duty_credit(self) -> list[str]:
        """約戰開著的季巡哨、傳道、保境安民那一點貢獻（企劃者 2026-10-24 第 2 件：Config.sortie.duty_contribution，一天 duty_per_day 次；
        duty_day／duties_today 照 _pill_day 換日）。第一季的規則關著（沒有貢獻）、今天記滿了是空的。"""
        s, c = self.state, self.content
        p, w, cfg = s.player, s.world, c.config.sortie
        today = self._pill_day()
        if p.duty_day != today:
            p.duty_day, p.duties_today = today, 0
        if cfg.duty_contribution <= 0 or p.duties_today >= cfg.duty_per_day or not calendar.season_one_on(w, c):
            return []
        p.duties_today += 1
        wins.credit(p, c, w, calendar.point(w.time, c, w).week, cfg.duty_contribution)
        return [f"貢獻 +{cfg.duty_contribution}"]

    def _take_convoy(self) -> list[str]:
        """接下糧車（護糧，軍令文件 3.4）：交出 convoy_grain 份糧草（從低階的慢屬性素材用起，多的不找），記下要送到哪裡。
        不花體力；抵達終點才算數（見 _convoy_arrives）。"""
        s, c = self.state, self.content
        p = s.player
        escort = orders.escort_at(s, c, self._side(), p.location)
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
        enemy = orders.ambusher(c, self._side())
        if enemy is not None and self.rng.random() < c.config.convoy_ambush_chance:
            msgs.append("快到營門時，半路殺出一隊截糧的人馬！")
            msgs += self._squad_encounter(enemy, wild=True)
            if s.battles[0].tier not in team.WIN_TIERS:
                return msgs + ["糧車被劫走了，這一趟不算數。"]
        key = f"{loc_id}:糧草"
        p.donations[key] = p.donations.get(key, 0) + convoy.grain
        # 護糧沒有推動，另記一次第 1 階推動的貢獻（總計畫 T6）
        wins.credit(p, c, s.world, orders.week_of(s, c), c.config.contrib_per_push)
        msgs.append(f"糧車送進了{c.locations[loc_id].name}，一粒不少。")
        return msgs + self._order_credit(kind="convoy", location=loc_id, front=front_of(c, loc_id), order=convoy.order)

    def _rest(self) -> list[str]:
        """序章教體力那一步的調息（新手引導設計 3.1）：一下回滿。打坐本身 2026-10-12 拿掉了（企劃者「打坐也拿掉」：體力只靠時間
        與一天有上限的回體丹），選單上只在這一步有這顆（_everyday_options）；不在這一步按到（舊分頁）只回一句。"""
        line = prologue_rules.instant_rest(self.state, self.content)
        if not line:
            return [NO_REST]
        self.state.player.stamina = float(self.content.config.stamina_max)
        return [line]

    def _figures_here(self) -> list[str]:
        """這個地點的大勢人物（不管見不見得到）：可招募的 7 位在 recruit_at，鎖定的龍頭人物在 talk_at（不可招募，見
        「還要改進」第 5 點）。有挑戰本人的季（figures.challenge_on，每季都有），人物表上的人照他此刻的所在與狀態
        （figures.placed_characters，T4）：轉往冀州的皇甫嵩、到任的董卓在盧植營；下獄、退場、重創的不在任何地方；14 天的季沒人退場時
        跟 talk_at 一樣。緊急開關關著（figure_challenge_every_season）時照 talk_at，一個字都不變。"""
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
        hint = audience_hint(s, c, companion_id)  # 名聲 explain 開著時另寫門檻與每一項折抵（設計 6.3）
        p = s.player
        step = int(c.config.audience_rank_discount * renown.scale(s.world) + 0.5)  # 名聲 2.4：升一階抵的點數也乘季長倍數
        if (
            season_one(c, s.world)  # 規則沒開（beta 那一季）沒有人晉升
            and figure is not None and p.faction == figure.faction
            and short <= step  # 再升一階抵掉的點數補得上這個差距
            and ranks.next_rank_up(s, c) is not None  # 而且下一次晉升真的會升階：第 4 階只是資格（rank 停在 3、在任才降門檻），不許諾
        ):
            faction = c.scenario.faction_name(figure.faction, figure.faction)
            hint += f"，或在{faction}再升一階"
        return [f"{line}（{hint}）"]

    def _talks_used(self, companion_id: str) -> int:
        """這個遊戲日（rules.game_day，跟著季長縮）已經跟這位人物聊了幾輪；紀錄是別的號碼（前幾天的，或縮放之前照 24 小時
        記的舊帳）就當沒聊過。"""
        record = self.state.player.talks_today.get(companion_id)
        return record[1] if record and record[0] == game_day(self.content, self.state.world) else 0

    def _talks_left(self, companion_id: str) -> int:
        """這個遊戲日還能跟這位人物聊幾輪。"""
        return max(0, self._talk_cap() - self._talks_used(companion_id))

    def _talks_reopen(self) -> tuple[str, str | None]:
        """談滿了的人物什麼時候再見得到：此刻所在的遊戲日結束的那一刻，照季的時間寫法（rules.day_turn）；None＝這一季之內
        不會再換日（最後一個遊戲日、季末提前），句子改寫「這一季之內」（day-scale 審查 M2）；季末延後、換日在名義季長之後寫不出那一刻
        時是 ("later", None)，句子寫「過一陣子」（FB-102）。回傳 rules.day_turn 的（哪一種, 時刻）。"""
        return day_turn(self.content, self.state.world)

    def _count_talk(self, companion_id: str) -> list[str]:
        """記一輪；這個遊戲日聊滿了就自動告辭，寫明什麼時候再來（待 joy 潤）。"""
        self.state.player.talks_today[companion_id] = [game_day(self.content, self.state.world), self._talks_used(companion_id) + 1]
        if self._talks_left(companion_id) > 0:
            return []
        self.state.player.pending_companion = None
        name, (kind, moment) = self.content.characters[companion_id].name, self._talks_reopen()
        if kind == "later":
            return [f"{name}起身送客，改日再敘：過一陣子再來拜會吧。"]  # FB-102，待 joy 潤
        if moment is None:
            return [f"{name}起身送客：這一季之內不能再來拜會了。"]
        return [f"{name}起身送客，改日再敘：要到 {moment} 之後才能再來拜會。"]

    def _deep_interaction_target(self) -> str | None:
        """這個地點此刻能深度對話的人物 id：見得到（名望或結識）、這個遊戲日還沒聊滿，也沒在對你閉門不見（T4）；沒有就是 None。"""
        for companion_id in self._figures_here():
            if self._can_meet(companion_id) and self._talks_left(companion_id) > 0 and not self._snubbed_character(companion_id):
                return companion_id
        return None

    def _audience_hall(self) -> bool:
        """這裡有兩位以上的大勢人物：交友不再直接找第一位見得到的人，改按「求見」指名（企劃者 2026-10-03 決定）。"""
        return len(self._figures_here()) >= AUDIENCE_HALL_FIGURES

    def _socialize_figure(self) -> str | None:
        """交友會直接開口對話的那位人物：只有這裡至多一位大勢人物時才有（見得到、這個遊戲日還沒談滿，見
        _deep_interaction_target）；兩位以上的地點交友只走福緣與地點事件，人物要按「求見」指名。"""
        if precise.on(self.content, self.state.world):  # 一類一顆：照 _social_plan
            kind, arg = self._social_plan()
            return arg if kind == "talk" else None
        if self._audience_hall():
            return None
        return self._deep_interaction_target()

    def _audience_options(self) -> list[Option]:
        """求見的第二層選單：這裡每一位大勢人物一個選項，最後是永遠按得下去的「返回」。名望不夠（也沒結識過）的人
        也按得下去，只是會被打發（見 _brush_off）；這個遊戲日已經跟他談滿、或剛吃了敗仗閉門不見的人按不下去並寫明原因
        （談滿的寫換日的那一刻）；每個遊戲日的輪數上限是每位人物各算各的（talk_turns_per_day）。"""
        c = self.content
        cost = c.config.action_cost["socialize"]
        per_day = self._talk_cap()
        opts = []
        for companion_id in self._figures_here():
            ch = c.characters[companion_id]
            option_id = f"call:{companion_id}"
            left = self._talks_left(companion_id)
            if self._snubbed_character(companion_id):
                opts.append(Option(id=option_id, label=f"{ch.name}（{SNUB_NOTE}）", enabled=False))
            elif not self._can_meet(companion_id) and precise.on(c, self.state.world):  # 一類一顆（2.8）：不再打發
                if self._meet_event(companion_id) is not None:
                    opts.append(self._cost_option(option_id, ch.name, cost, note=AUDIENCE_MEET))
                else:
                    opts.append(Option(id=option_id, label=f"{ch.name}（名望還差 {self._fame_gap(companion_id)}）", enabled=False))
            elif not self._can_meet(companion_id):
                opts.append(Option(id=option_id, label=f"{ch.name}（名望還差 {self._fame_gap(companion_id)}）"))  # 按下去走打發，見 _brush_off
            elif left == 0:
                opts.append(Option(id=option_id, label=f"{ch.name}（{self._talked_out_note()}）", enabled=False))
            else:
                opts.append(self._cost_option(option_id, ch.name, cost, note=f"還能談 {left}/{per_day} 輪"))
        opts.append(Option(id="call:back", label="返回"))
        return opts

    def _bounty_options(self) -> list[Option]:
        """懸賞榜的第二層選單（bounties.py）：交得出的求兵每張一顆「交出…」（按了到第三層挑一件；排最前面，當場就能交），
        手上的每一張一顆「放棄」，榜上其他看得到的每一張一顆「揭下」（揭不了的灰掉、寫為什麼），交不出的求兵收成一行灰掉的，
        最後是永遠按得下去的「返回」；上面全空（榜開著時單被別人交光）就多一行灰掉的 bounty:empty（FB-156）。都不花體力。列的是 bounties.visible（別的陣營的、自己交過的不列），跟閒著的選單寫的張數一樣
        （灰掉那一行照它包含幾張算）。bounty_pick 指著一張還交得出的求兵時整份換成第三層（bounties.hand_in_options）；
        那一張下榜了、交不出了就當它不存在，照第二層畫（懸賞榜設計 4.3、4.4）。"""
        s, c = self.state, self.content
        shown = bounties.visible(s, c)
        picked = next((b for b in shown if b.id == s.player.bounty_pick and b.kind in bounties.GIVE_KINDS), None)
        items = bounties.fitting(s, c, self.world, picked) if picked is not None else []
        if items:
            return bounties.hand_in_options(s, c, self.world, picked, items)
        mine = {b.id for b in bounties.mine(s, c)}
        ready, opts, stuck = [], [], []
        for b in shown:
            if b.kind in bounties.GIVE_KINDS:  # 求兵不用揭
                have = bounties.fitting(s, c, self.world, b)
                if have:
                    ready.append(Option(id=f"bounty:pick:{b.id}", label=bounties.pick_label(s, c, b, len(have))))
                else:
                    stuck.append(b)
                continue
            line = (f"{bounties.issuer(c, b)}・{bounties.title(c, b)}：{bounties.how(c, b, self.state)}"
                    f"（{bounties.reward_text(s, c, b)}；{bounties.due_line(s, c, b)}）")  # 期限與名額（FB-121 第 5 件）
            if b.id in mine:
                opts.append(Option(id=f"bounty:drop:{b.id}", label=f"放棄 {line}"))
                continue
            problem = bounties.take_problem(s, c, b)
            opts.append(Option(id=f"bounty:take:{b.id}", label=f"揭下 {line}" + (f"（{problem}）" if problem else ""),
                               enabled=problem is None))
        if stuck:
            kept = {b.id: tail for b in stuck if (tail := bounties.only_original(s, b))}  # 只有神器原品或本命兵器對得上的那幾張照實寫（FB-145）
            opts.append(Option(id="bounty:none", label=bounties.stuck_label(c, stuck, kept), enabled=False))
        if not ready and not opts:  # 榜開著的時候，看得到的單被別人交光了：不能只剩「返回」（FB-156）
            opts.append(Option(id="bounty:empty", label=bounties.BOARD_EMPTY, enabled=False))
        return ready + opts + [Option(id="bounty:back", label="返回")]

    def _bounty(self, arg: str) -> list[str]:
        """懸賞榜上的選擇：揭下、放棄、交出…（到第三層挑一件）、回到懸賞榜、交出，或返回（收起懸賞榜）。做完榜還開著，可以接著挑。
        交出的 id 是「give:懸賞 id:東西 id」：兵器 id「兵:3」帶冒號，懸賞 id（b17）沒有，所以只切一次。"""
        s, c = self.state, self.content
        verb, _, rest = arg.partition(":")
        if verb == "back":
            bounties.close_board(s.player)
            return ["你離開了懸賞榜。"]
        if verb == "take":
            b = next((x for x in bounties.open_bounties(s, c) if x.id == rest), None)
            self._shop_after(bounties.take_problem(s, c, b) if b is not None else bounties.GONE, "take", shopview.board_key)  # 1.4
            return bounties.take(s, c, rest)
        if verb == "drop":
            msgs = bounties.drop(s, c, rest)
            self._shop_say("refused" if msgs == [bounties.NOT_HELD] else "drop")
            return msgs
        if verb == "pick":
            b = next((x for x in s.world.bounties if x.id == rest), None)
            if b is None:
                self._shop_say("refused")
                return [bounties.GONE]
            s.player.bounty_pick = rest
            self._shop_say("pick")
            return [bounties.pick_line(c, b)]
        if verb == "unpick":
            s.player.bounty_pick = None
            return [bounties.UNPICKED]
        if verb == "give":
            bounty_id, _, item = rest.partition(":")
            msgs = bounties.give(s, c, self.world, bounty_id, item)
            if msgs[0].startswith(bounties.GIVEN_PREFIX):
                s.player.bounty_pick = None  # 交完回到第二層，可以接著交別張
                self._shop_say("give")
            else:
                self._shop_say("refused")
            return msgs
        return ["（此刻無法這麼做。）"]

    def _smith_options(self) -> list[Option]:
        """鐵匠鋪的第二層選單（兵器設計 4.1；裝備四欄設計 4.6）：分兵器、防具兩頁（equipment.page；兩欄都開著時預設兵器頁，
        「離開」前一顆切到另一頁；只開一欄就只有那一頁、沒有切頁鈕）。打造兵器…／打造防具…挑到一半（smith_draft）時整份換成那一步。
        兵器頁：架上六把各一顆「買」（買不了的灰掉、寫為什麼；種類對得上身上武學的那一把標出來），手上那把一顆「修」（寫明用掉哪一種素材）
        與「淬煉」（身上那把配不上身上的武學時，按得下去的「修」「淬煉」多一句提醒：白花料與銀兩，加成用不上），
        裝備庫裡配得上身上武學的每把一顆「換上」（配不上的到修練頁換），「打造兵器…」（排在換上與拆解中間：FB-125），
        拆解（_dismantle_options）。防具頁見 _armor_options。裝備庫都只看這一頁那一欄（3.3）。都不花體力。"""
        s, c = self.state, self.content
        art = team.player_art(s, c, self.world, s.player.member.wugong_id)
        fit_kind = weapons.art_weapon(art.id, c, self.world) if art is not None else None
        if s.player.smith_draft is not None:
            neigong = team.player_art(s, c, self.world, s.player.member.neigong_id)  # 防具的單子標跟內功同屬性的輔料
            return smithing.draft_options(s, c, self.world, art, neigong)  # 打造兵器…／打造防具…挑到一半：只畫這一步
        if s.player.smith_page == equipment.MATERIAL_PAGE and self._trade_on():
            return self._material_options()  # 素材頁：收購、升階（素材與經濟設計第四、五節）
        if equipment.page(s.player, c) == "armor":
            return self._armor_options()  # 防具頁（裝備四欄 4.6）
        opts = []
        for item in weapons.stock(s, c):
            problem = weapons.buy_problem(s, c, item.kind)
            note = problem or f"{c.config.weapons.shop_price} 兩"
            mark = weapons.FITS_MARK if c.config.weapons.enabled and item.kind == fit_kind else ""
            opts.append(Option(id=f"smith:buy:{item.kind}", label=f"買【{item.name}】（{weapons.noun(item.kind)}・一階・{note}）{mark}",
                               enabled=problem is None))
        # 身上那把配不上身上的武學（含沒有武學）：加成是 0，修與淬煉照樣按得下去，可是花的料與銀兩看不到回報，按鈕上提醒一句（PM 2026-10-11）
        unfit = weapons.unfit_note(s.player.weapon) if weapons.worn_unfit(s, art, c, self.world) else ""
        if s.player.weapon is not None:
            problem = weapons.repair_problem(s, c)
            material = weapons.repair_material(s, c)
            use = f"{c.materials[material].name}×1" if material is not None else "一個一階素材"
            note = problem or f"{use}＋{c.config.weapons.repair_silver} 兩"
            opts.append(Option(id="smith:repair", label=f"修【{s.player.weapon.name}】（鋒利度 {s.player.weapon.edge}・{note}）{unfit if problem is None else ''}",
                               enabled=problem is None))
        temper = smithing.temper_option(s, c)  # 淬煉身上那把（兵器設計 4.7）；空手沒有
        if temper is not None:
            if temper.enabled and unfit:  # 灰掉的（淬滿了、沒料、沒錢）照舊：沒有東西會白花
                temper = temper.model_copy(update={"label": temper.label + unfit})
            opts.append(temper)
        for w in equipment.in_slot(s.player, "weapon"):  # 裝備四欄 3.3：只看武器那一欄
            if weapons.usable(w, art, c, self.world) and equipment.wear_problem(s, c, w) is None:  # 穿不上的神器不列（正式季整合 5.8）
                opts.append(Option(id=f"smith:wield:{w.id}", label=f"換上【{w.name}】（{weapons.noun(w.kind)}・{weapons.grade_line(w)}・鋒利度 {w.edge}）"))
        if c.config.weapons.enabled:
            opts.append(smithing.forge_door(s, c))  # 打造兵器…（排在換上與拆解中間：FB-125，兩顆不相鄰）
        opts += self._dismantle_options("weapon")  # 拆解（只看武器那一欄；最多 DISMANTLE_LIST 顆、先問一次）
        return opts + self._smith_tail()

    def _dismantle_options(self, slot: str) -> list[Option]:
        """鐵匠鋪那一頁的拆解（兵器設計 4.7.1、裝備四欄 4.8）：裝備庫裡這一欄的，磨損最多、階最低的先、最多 DISMANTLE_LIST 顆，
        每顆先問一次（FB-125：confirm／confirm_yes「拆掉」），標籤寫階品質與淬煉次數（同一個配方好幾件才分得出來）；
        多的一行灰掉的說明指到修練頁。這一欄關著是空的。"""
        c = self.content
        if not equipment.on(c, slot):
            return []
        breakable = sorted(equipment.in_slot(self.state.player, slot), key=equipment.dismantle_order)
        opts = [
            Option(id=f"smith:dismantle:{w.id}", label=f"拆解【{w.name}】（{equipment.kept(w)}）", enabled=False)  # 5.4：灰掉寫原因
            if w.original else
            Option(id=f"smith:dismantle:{w.id}",
                   label=f"拆解【{w.name}】（{equipment.grade_line(w)}）→ {equipment.dismantle_material(c, w).name}×1",
                   confirm=equipment.dismantle_confirm(c, w), confirm_yes=equipment.DISMANTLE_YES)  # FB-125：先問一次
            for w in breakable[:equipment.DISMANTLE_LIST]
        ]
        if len(breakable) > equipment.DISMANTLE_LIST:
            opts.append(Option(id="smith:dismantle-more", enabled=False,
                               label=equipment.DISMANTLE_MORE.format(n=len(breakable) - equipment.DISMANTLE_LIST)))
        return opts

    def _armor_options(self) -> list[Option]:
        """鐵匠鋪的防具頁（裝備四欄設計 4.6）：架上剛柔快慢四件各一顆「買」（一階下品；寫這件給你少扣幾成氣血、對不對得上你的內功，
        買不了的灰掉寫為什麼），身上那件一顆「修」（寫明用掉哪一種素材）、一顆「淬煉」，裝備庫裡的防具「換上」（最多 DISMANTLE_LIST 件、最好的先，
        FB-134），「打造防具…」，拆解，兵器也開著時一顆切到兵器頁，最後「離開」。都不花體力。FB-125：打造入口隔開換上與拆解（同兵器頁），
        拆解另外先問一次（confirm／confirm_yes）擋誤按。"""
        s, c, p = self.state, self.content, self.state.player
        neigong = team.player_art(s, c, self.world, p.member.neigong_id)
        rule = c.config.armor
        opts = []
        # 買、修、換上三種鈕的寫法都待 joy 潤；磨損的叫法讀 armor.WEAR_WORD（3.1 的字表），不寫死
        for attribute in armor.SHOP_ATTRIBUTES:
            item = armor.shop_item(attribute)
            problem = armor.buy_problem(s, c, attribute)
            fit = armor.fit_note(item, neigong)
            note = problem or f"{rule.shop_price} 兩"
            opts.append(Option(
                id=f"{armor.BUY}{attribute}", enabled=problem is None,
                label=f"買【{item.name}】（屬{attribute}・一階・少扣 {armor.pct(armor.cut(item, neigong, c))} 氣血{'・' + fit if fit else ''}・{note}）",
            ))
        if p.armor is not None:
            problem = armor.repair_problem(s, c)
            material = equipment.repair_material(s, c)
            use = f"{c.materials[material].name}×1" if material is not None else "一個一階素材"
            note = problem or f"{use}＋{rule.repair_silver} 兩"
            opts.append(Option(id=armor.REPAIR, label=f"修【{p.armor.name}】（{armor.WEAR_WORD} {p.armor.edge}・{note}）", enabled=problem is None))
        temper = smithing.temper_option(s, c, "armor")  # 淬煉身上那件（四欄設計 4.1）；沒穿沒有
        if temper is not None:
            opts.append(temper)
        # FB-134：「換上」最多 DISMANTLE_LIST 件，修好之後減損高的先、同分 id 大的先——跟 armor.wanted 挑換上的鍵一樣，整季機器人與假人
        # 要按的那一顆一定列得出來；多的一行灰掉的說明指到修練頁（同拆解）。淬過的寫「・淬煉 N」（equipment.grade_line）
        spares = sorted((a for a in equipment.in_slot(p, "armor") if equipment.wear_problem(s, c, a) is None),  # 穿不上的神器不列（5.8）
                        key=lambda a: (armor.fresh_cut(a, neigong, c), a.id), reverse=True)
        for a in spares[:equipment.DISMANTLE_LIST]:
            opts.append(Option(id=f"smith:wield:{a.id}", label=f"換上【{a.name}】（屬{a.attribute}・{equipment.grade_line(a)}・{armor.WEAR_WORD} {a.edge}）"))
        if len(spares) > equipment.DISMANTLE_LIST:
            opts.append(Option(id="smith:wield-more", enabled=False,
                               label=equipment.WIELD_MORE.format(n=len(spares) - equipment.DISMANTLE_LIST)))
        opts.append(smithing.forge_door(s, c, "armor"))  # 打造防具…（排在換上與拆解中間：FB-125，同兵器頁）
        return opts + self._dismantle_options("armor") + self._smith_tail()

    def _smith_tail(self) -> list[Option]:
        """鐵匠鋪每一頁最後幾顆：收購或升階開著時一顆進素材頁（素材與經濟設計第四、五節），另一欄也開著時一顆切頁（裝備四欄設計 4.6），
        再來永遠按得下去的「離開」。"""
        other = equipment.other_page(self.state.player, self.content)
        door = [Option(id=f"smith:page:{equipment.MATERIAL_PAGE}", label=equipment.MATERIAL_LABEL)] if self._trade_on() else []
        tail = [Option(id=f"smith:page:{other}", label=equipment.PAGE_LABELS[other])] if other is not None else []
        return door + tail + [Option(id="smith:back", label="離開鐵匠鋪")]

    def _trade_on(self) -> bool:
        """鐵匠鋪的素材頁開不開（Config.economy 的收購或升階有一樣開著）。"""
        econ = self.content.config.economy
        return econ.sell or econ.upgrade

    def _material_options(self) -> list[Option]:
        """鐵匠鋪的素材頁（素材與經濟設計第四、五節；店面關著時、整季機器人與假人看的那一串）：背包裡收得了的每一種一顆「賣一個」，
        手上有低一階料的每個（屬性, 階）一顆「升一個」（三階寫今天還能換幾個；按不下去的灰掉寫為什麼），回兵器／防具頁，最後「離開」。
        字與按得下去與否都照店面的 shopview.trade_view（同一份規則）。都不花體力。"""
        s, c = self.state, self.content
        trade = shopview.trade_view(s, c, self._pill_day()) or {"sell": [], "upgrade": []}
        opts = [
            Option(id=f"smith:sell:{row['id']}", enabled=row["problem"] is None,
                   label=economy.SELL_LABEL.format(name=row["name"], price=row["price"], have=row["have"]) + row["dark"])  # 名聲 5.2：（黑市價）
            for row in trade["sell"]
        ]
        for row in trade["upgrade"]:
            if row["have"] <= 0:
                continue  # 選單只列手上有料的（店面四個屬性都列）
            option_id = f"smith:upgrade:{row['attribute']}:{row['tier']}"
            if row["problem"] is not None:
                opts.append(Option(id=option_id, enabled=False,
                                   label=economy.UPGRADE_REFUSED.format(low=row["from"], need=row["need"], problem=row["problem"])))
                continue
            left_line = economy.UPGRADE_SEASON_LEFT if row["tier"] == four_tiers.TIER else economy.UPGRADE_LEFT
            left = left_line.format(n=row["left"]) if row["left"] is not None else ""
            opts.append(Option(id=option_id, label=economy.UPGRADE_LABEL.format(
                low=row["from"], need=row["need"], cost=row["cost"], odds=row["odds"], left=left)))
        pages = [Option(id=f"smith:page:{slot}", label=equipment.PAGE_LABELS[slot]) for slot in equipment.SMITH_PAGES if equipment.on(c, slot)]
        return opts + pages + [Option(id="smith:back", label="離開鐵匠鋪")]

    def _market_options(self) -> list[Option]:
        """馬市的第二層選單（裝備四欄設計 5.5）：一顆「買」（駑馬下品，寫省幾成體力與價錢；買不了的灰掉寫為什麼），
        身上有馬時一顆「餵」（寫用哪一種素材；不餓、沒素材灰掉寫為什麼），裝備庫裡每一匹一顆「換上」，最後「離開」。都不花體力。"""
        s, c, p = self.state, self.content, self.state.player
        item = mounts.shop_item(s, c)
        problem = mounts.buy_problem(s, c)
        note = problem or f"{mounts.price(s, c)} 兩{territory.price_note(s, c)}"  # 名聲 4.1：馬價後面寫原因
        # 三種鈕的寫法都待 joy 潤；飽足度這個叫法讀 mounts.WEAR_WORD，不寫死。網頁照 FB-132 把 market: 的鈕切成不折行的小段
        opts = [Option(id=mounts.BUY, enabled=problem is None,
                       label=f"買【{mounts.name_of(item)}】（{mounts.grade(item)}・疾行省 {mounts.pct(mounts.fresh_power(c, item))} 體力・{note}）")]
        if p.mount is not None:
            opts.append(Option(id=mounts.FEED, enabled=mounts.feed_problem(s, c) is None,
                               label=f"餵【{mounts.name_of(p.mount)}】（{mounts.WEAR_WORD} {p.mount.edge}・{mounts.feed_note(s, c)}）"))
        for m in equipment.in_slot(p, "mount"):
            opts.append(Option(id=f"{mounts.WIELD}{m.id}",
                               label=f"換上【{mounts.name_of(m)}】（{mounts.grade(m)}・{mounts.WEAR_WORD} {m.edge}）"))
        opts.append(Option(id=mounts.BACK, label=mounts.LEAVE))
        return opts

    def _market(self, arg: str) -> list[str]:
        """馬市上的選擇：買、餵、換上，或離開（收起選單）。做完選單還開著，可以接著挑。店面上馬販那一句照這一下的擋法記（1.4）。"""
        s, c = self.state, self.content
        verb, _, rest = arg.partition(":")
        if verb == "back":
            mounts.close_market(s.player)
            return [mounts.LEFT]
        if verb == "buy":
            self._shop_after(mounts.buy_problem(s, c), "buy")
            return mounts.buy(s, c)
        if verb == "feed":
            self._shop_after(mounts.feed_problem(s, c), "feed")
            return mounts.feed(s, c)
        if verb == "wield":
            msgs = mounts.wield(s, c, rest)
            self._shop_say("wield" if msgs[0].startswith(equipment.WIELDED.partition("{")[0]) else "refused")
            return msgs
        return ["（此刻無法這麼做。）"]

    def _smith(self, arg: str) -> list[str]:
        """鐵匠鋪上的選擇（_smith_act）；這一下花了銀兩或素材（買、修、淬煉、開爐；拆解拿到素材不算），再擲一次鐵匠順口（_smith_clue；
        打造隱藏配方設計 6.2、計畫「要 PM 定的」第 3 條）。順口說出的那一句記成店面上這一下的話（shop_clue，店面獨立介面設計 1.4）。"""
        p = self.state.player
        p.shop_clue = ""
        silver, mats = p.stats.get("silver", 0), sum(p.materials.values())
        msgs = self._smith_act(arg)
        if arg.partition(":")[0] == "sell":
            return msgs  # 收購是鐵匠付你錢：沒花銀兩，不擲鐵匠順口（素材與經濟計畫 B3）
        if p.stats.get("silver", 0) < silver or sum(p.materials.values()) < mats:
            clue = self._smith_clue(paid=p.stats.get("silver", 0) < silver)
            if clue:
                p.shop_clue = clue[0]
            msgs = msgs + clue
        return msgs

    def _smith_act(self, arg: str) -> list[str]:
        """鐵匠鋪上的一下（_smith 包著它）：切頁、買、修、換上、拆解（兵器頁或防具頁）、打造與淬煉的每一步，或離開（收起選單、打造的單子
        與停在哪一頁）。做完選單還開著，可以接著挑。"""
        s, c = self.state, self.content
        verb, _, rest = arg.partition(":")
        if verb == "back":
            equipment.close_smith(s.player)
            return [f"你離開了{weapons.SMITH}。"]
        if verb == "page":  # 切到另一頁（裝備四欄 4.6）：只是換一頁，不回訊息（choose 照它不寫紀錄）
            from_material = s.player.smith_page == equipment.MATERIAL_PAGE
            if (
                rest == equipment.other_page(s.player, c)
                or (rest == equipment.MATERIAL_PAGE and self._trade_on())  # 進素材頁（素材與經濟設計第四、五節）
                or (from_material and rest in equipment.SMITH_PAGES and equipment.on(c, rest))  # 從素材頁回兵器或防具頁
            ):
                s.player.smith_page = rest
            return []
        if verb == "sell":  # 素材頁：賣一個（第五節）
            return self._trade_sell(rest, 1)
        if verb == "upgrade":  # 素材頁：升一個（第四節），rest 是「屬性:階」
            attribute, _, tier = rest.partition(":")
            return self._trade_upgrade(attribute, int(tier) if tier.isdecimal() else 0)
        if verb == smithing.GO_VERB:
            kind, main, aux = smithing.parse_go(f"smith:{arg}")
            return self._smith_forge_once(kind, main, aux)[1]
        if verb in smithing.STEP_VERBS:
            if verb in ("temper", "armor-temper"):  # 店面上掌櫃那一句（1.4）：照淬煉之前的擋法
                self._shop_after(smithing.temper_problem(s, c, "armor" if verb == "armor-temper" else "weapon"), "temper")
            return smithing.step(s, c, verb, rest)
        if verb == "buy":
            self._shop_after(weapons.buy_problem(s, c, rest), "buy")
            return weapons.buy(s, c, rest, team.player_art(s, c, self.world, s.player.member.wugong_id), self.world)  # 配得上就直接換上（FB-128）
        if verb == "repair":
            self._shop_after(weapons.repair_problem(s, c), "repair")
            return weapons.repair(s, c)
        if verb == "armor-buy":
            self._shop_after(armor.buy_problem(s, c, rest), "buy")
            return armor.buy(s, c, rest)
        if verb == "armor-repair":
            self._shop_after(armor.repair_problem(s, c), "repair")
            return armor.repair(s, c)
        # 換上與拆解兩頁共用 id 開頭（兵:N、甲:N 本來就全角色唯一），照停在哪一頁限定欄位
        if verb == "wield":
            return (armor.wield if equipment.page(s.player, c) == "armor" else weapons.wield)(s, c, rest)
        if verb == "dismantle":
            return (armor.dismantle if equipment.page(s.player, c) == "armor" else weapons.dismantle)(s, c, rest)
        return ["（此刻無法這麼做。）"]

    def _shop_say(self, key: str, problem: str | None = None) -> None:
        """店面上掌櫃那一句（店面獨立介面設計 1.4、6.1）：記下店裡最後一件事的情況鍵、挑句子的種子（這一刻的季的時間），與被拒的那一句
        撐到什麼時候（shopview.hold_for，FB-192：problem 是被拒的原因，錢不夠那一句照它記要多少銀兩）。"""
        p = self.state.player
        p.shop_line, p.shop_line_seed = key, int(self.state.world.time)
        p.shop_hold = shopview.hold_for(self.state, self.content, key, problem)

    def _shop_after(self, problem: str | None, done: str, keyer=None) -> None:
        """照這一下的擋法記掌櫃那一句：做成了是 done，被拒照 shopview.problem_key（懸賞榜照 board_key）換成情況鍵，連同被拒的原因（FB-192）。"""
        self._shop_say((keyer or shopview.problem_key)(problem, done), problem)

    def _smith_forge_once(self, kind: str, main: str, aux: str) -> tuple[Equipment | None, list[str], dict]:
        """開爐一次（一步一步單子的 forge-go 與店面的直接開爐共用）：防具的品質擲骰用自己的亂數（不動 Game.rng，FB-129；打造隱藏配方
        設計 9.3），兵器照舊用 Game.rng；不叫模型、一次做完（打造隱藏配方設計第八節）。打成了收起單子（同一顆連按兩下、兩個分頁，第二下
        已經不在選單上：Review Focus 1），掌櫃那一句照打出來的（品質、名器、神器）；被拒絕照原因。回（那一件, 訊息, report）。"""
        s, c = self.state, self.content
        problem = smithing.forge_problem(s, c, kind, main, aux)
        rng = smithing.own_rng(s, smithing.recipe_key(kind, main, aux)) if smithing.is_armor(kind) else self.rng
        report: dict = {}
        item, msgs = smithing.forge(s, c, self.world, kind, main, aux, rng=rng, report=report)
        if item is not None:
            s.player.smith_draft = None
            self._shop_say(shopview.forged_key(item))
        else:
            self._shop_after(problem, "refused")
        return item, msgs, report

    def _shop_open(self) -> str | None:
        """哪一間店開著（店面獨立介面設計 1.1；同 options() 的先後：懸賞榜、鐵匠鋪、馬市）。那個地方已經不開門了（同步之前）是 None；
        鐵匠鋪的一步一步單子還開著（開關關著時開的、舊存檔）也是 None，照舊畫那一串按鈕（店面上的鈕在單子那一步不在選單上）。"""
        s, c = self.state, self.content
        p = s.player
        if p.arena is not None:  # 擂台打到一半：擂台那一頁就是這一場（Joy 2026-10-14「擂台應該要是獨立的一頁」）
            return "arena"
        if p.picking_arena:
            return "arena" if arena.here(s, c) else None
        if p.picking_bounty:
            return "board" if bounties.board_here(s, c) else None
        if p.picking_smith:
            return "smith" if p.smith_draft is None and equipment.smith_open(s, c) else None
        if p.picking_market:
            return "market" if mounts.market_here(s, c) else None
        if p.picking_donate:  # 大本營的軍需帳（素材與經濟 B6，企劃者 2026-10-15 選 B3）
            return "donate" if self._at_own_base() else None
        if p.picking_dadian:  # 打點（21 天季的銀兩出口，第 9 批畫面乙）
            return "dadian" if self._silver_options() else None
        if p.picking_tavern:  # 酒肆（企劃者 2026-10-18）
            return "tavern" if tavern_rules.here(s, c) else None
        return None

    def _shop_live(self, option_ids=None, shop: str = "smith") -> bool:
        """這間店那一串此刻真的是眼前的選單（店面與直接開爐都問它）：選單上有這間店的離開鈕（shopview.BACKS：鐵匠鋪 smith:back、
        馬市 market:back、懸賞榜 bounty:back 或第三層的 bounty:unpick），而且前面沒有決戰、奪璽單挑的鈕。決戰開打、休季時選單換成三招
        或「休季中」，店裡那一串根本不在上面（picking_* 卻還是真的）：這時給店面，出店會被拒絕、人就困在店裡，休季還開得了爐
        （第一批終審 Critical 1）。集結時決戰的鈕排在店裡那一串前面：照舊畫那一串，加入、趕到的鈕不被蓋住。
        option_ids 是現在的選單（main_view 已經讀過就傳進來）；沒給就讀一次（不推進戰鬥）。"""
        ids = [o.id for o in self.options(odds=False, tick=False)] if option_ids is None else list(option_ids)
        return any(back in ids for back in shopview.BACKS[shop]) and not any(i.startswith(("battle:", "seal:")) for i in ids)

    def shop_view(self, option_ids=None) -> dict | None:
        """店面（店面獨立介面設計 6.1）：開關開著、有一間店開著（_shop_open）、那間店那一串是眼前的選單（_shop_live）才有；
        照哪一間店給 shopview 的 smith_view、market_view 或 board_view。"""
        s, c = self.state, self.content
        if not c.config.shop_screens:
            return None
        shop = self._shop_open()
        if shop is None or not self._shop_live(option_ids, shop):
            return None
        if shop == "arena":
            return shopview.arena_view(s, c, self.world, self._battle_power(), self.arena_left(), bare=self._battle_power(seal=False))
        if shop == "donate":
            return shopview.donate_view(s, c, self._pill_day())
        if shop == "dadian":
            day = self._pill_day()
            base = self._at_own_base()
            return shopview.dadian_view(s, c, day=day, room=economy.donate_room(s, c, day) if base else 0, base=base,
                                        clinic=self._at_clinic_town(), smith=equipment.smith_open(s, c), bribe=self._bribe_targets(),
                                        prologue=prologue_rules.active(s, c))
        if shop == "tavern":
            return self.tavern_view()
        view = {"smith": shopview.smith_view, "market": shopview.market_view, "board": shopview.board_view}[shop](s, c, self.world)
        if shop == "smith":  # 素材買賣（素材與經濟設計第四、五節）：收購、升階都關著是 None
            view["trade"] = shopview.trade_view(s, c, self._pill_day())
        return view

    def smith_line(self, kind: str, main: str | None = None, aux: str | None = None) -> dict:
        """店面打造頁爐裡放了什麼，這一爐會怎樣（shopview.smith_line；/api/smith_line）。只讀。"""
        return shopview.smith_line(self.state, self.content, self.world, str(kind), main or None, aux or None)

    def smith_forge(self, kind: str, main: str, aux: str) -> list[str]:
        """店面的直接開爐（店面獨立介面設計 2.3、6.3；MAIN_ACTIONS["smith_forge"]）：店開著（picking_smith、人在鐵匠鋪），
        smithing.forge_problem 整個重驗才打——打的是同一個 smithing.forge（隱藏配方、神器原品與仿品、首位發現、名望回饋、熟手次數都照現在），
        跟一步一步單子的開爐同一條（_smith_forge_once：防具自己的亂數、兵器 Game.rng），打完收起單子；鐵匠順口照擲（同 _smith）。
        一爐一則「打造」江湖紀錄（不併進上一則）；被拒絕的不收錢、不收料、不寫紀錄，掌櫃那一句換成原因。
        出爐卡給網頁：self.smith_result（shopview.forged_card；被拒絕是 None）。"""
        s, c = self.state, self.content
        p = s.player
        self.smith_result = None
        if not p.picking_smith or not equipment.smith_open(s, c) or not self._shop_live():
            return self._log([equipment.NOT_NOW])  # 鐵匠鋪那一串不在眼前的選單上（決戰開打、休季）：同一步一步的開爐，按不下去
        p.shop_clue = ""
        silver, mats = p.stats.get("silver", 0), sum(p.materials.values())
        item, msgs, report = self._smith_forge_once(str(kind), str(main), str(aux))
        if item is None:
            return self._log(msgs)
        if p.stats.get("silver", 0) < silver or sum(p.materials.values()) < mats:
            clue = self._smith_clue(paid=p.stats.get("silver", 0) < silver)
            if clue:
                p.shop_clue = clue[0]
            msgs = msgs + clue
        journal.add_entry(s, Draft(smithing.FORGE_TITLE).entry(s.world.time, msgs))
        self.smith_result = shopview.forged_card(s, c, self.world, item, report)
        self._save_season()
        return self._log(msgs)

    def _trade_sell(self, mid: str, count: int) -> list[str]:
        """鐵匠鋪收購（素材與經濟設計第五節；選單的 smith:sell 與店面的 smith_sell 共用）：economy.sell，掌櫃那一句照這一下的擋法。"""
        s, c = self.state, self.content
        if not c.config.economy.sell:
            return [equipment.NOT_NOW]
        material = c.materials.get(mid)
        dark = material is not None and economy.black_market(s, c, material.tier)  # 名聲 5.2：掌櫃換黑市那一句
        self._shop_after(economy.sell_problem(s, c, mid, count), "black_market" if dark else "sell")
        return economy.sell(s, c, mid, count)

    def _trade_upgrade(self, attribute: str, tier: int) -> list[str]:
        """鐵匠鋪升階（素材與經濟設計第四節；選單的 smith:upgrade 與店面的 smith_upgrade 共用）：economy.upgrade，「一天」照回體丹的換日。"""
        s, c = self.state, self.content
        if not c.config.economy.upgrade:
            return [equipment.NOT_NOW]
        day = self._pill_day()
        self._shop_after(economy.upgrade_problem(s, c, attribute, tier, day), "upgrade")
        return economy.upgrade(s, c, attribute, tier, day)

    def _trade_open(self, switch: bool) -> bool:
        """店面的素材買賣按得下去嗎：這一樣的開關開著、鐵匠鋪開著而且那一串是眼前的選單（同 smith_forge）。"""
        s, c = self.state, self.content
        return switch and s.player.picking_smith and equipment.smith_open(s, c) and self._shop_live()

    def smith_sell(self, mid: str, count: int = 1) -> list[str]:
        """店面的收購（素材與經濟設計第五節；MAIN_ACTIONS["smith_sell"]）：一次賣 count 個。賣成了寫一則「鐵匠鋪」紀錄；
        被拒絕的不動背包銀兩、不寫紀錄，掌櫃那一句換成原因。收購是鐵匠付錢，不擲鐵匠順口。"""
        s, c = self.state, self.content
        if not self._trade_open(c.config.economy.sell):
            return self._log([equipment.NOT_NOW])
        s.player.shop_clue = ""
        problem = economy.sell_problem(s, c, str(mid), count)
        msgs = self._trade_sell(str(mid), count)
        if problem is None:
            journal.add_entry(s, Draft(weapons.SMITH).entry(s.world.time, msgs))
            self._save_season()
        return self._log(msgs)

    def smith_upgrade(self, attribute: str, tier: int) -> list[str]:
        """店面的升階（素材與經濟設計第四節；MAIN_ACTIONS["smith_upgrade"]）：換一個。換成了寫一則「鐵匠鋪」紀錄、照舊擲鐵匠順口
        （花了銀兩與素材，同 _smith）；被拒絕的什麼都不動、不寫紀錄。"""
        s, c = self.state, self.content
        p = s.player
        if not self._trade_open(c.config.economy.upgrade):
            return self._log([equipment.NOT_NOW])
        p.shop_clue = ""
        problem = economy.upgrade_problem(s, c, str(attribute), int(tier), self._pill_day())
        msgs = self._trade_upgrade(str(attribute), int(tier))
        if problem is not None:
            return self._log(msgs)
        clue = self._smith_clue(paid=True)
        if clue:
            p.shop_clue = clue[0]
        msgs = msgs + clue
        journal.add_entry(s, Draft(weapons.SMITH).entry(s.world.time, msgs))
        self._save_season()
        return self._log(msgs)

    def wield_weapon(self, item_id: str) -> list[str]:
        """修練頁的「換上」（兵器設計 2.2、裝備四欄設計 2.3）：武器、防具、寶物哪裡都能換（含路上、閉關中；寶物不設限制，企劃者 2026-10-11），
        坐騎路上不能換（equipment.wield 擋）、不花體力，換進那一件自己的欄位；寫一則修練紀錄。網頁照舊送 weapon 這個鍵
        （MENXIA_ACTIONS["wield"]），防具（甲:N）、坐騎（騎:N）、寶物（寶:N）的 id 也走它。"""
        msgs = self._log(equipment.wield(self.state, self.content, item_id, equipment.WIELDABLE))
        if msgs and msgs[0].startswith("你換上了"):
            self._menxia_entry(msgs[0], self._xinde())
        return msgs

    def feed_mount(self) -> list[str]:
        """修練頁坐騎那一列的「餵」（裝備四欄 5.4，MENXIA_ACTIONS["feed"]）：閒著時哪裡都能餵（不在路上、不在閉關），
        一個一階素材餵滿、不花銀兩；寫一則修練紀錄。整季機器人與假人也走這裡（bot.feed_mount）。"""
        msgs = self._log(mounts.feed(self.state, self.content))
        if msgs and msgs[0].startswith(mounts.FED_PREFIX):
            self._menxia_entry(msgs[0], self._xinde())
        return msgs

    def dismantle_weapon(self, item_id: str) -> list[str]:
        """修練頁裝備庫的「拆解」（兵器設計 4.7.1、裝備四欄設計 4.8）：武器、防具哪裡都能拆、不花體力；坐騎、寶物不能拆；寫一則修練紀錄。"""
        msgs = self._log(equipment.dismantle(self.state, self.content, item_id, equipment.DISMANTLABLE))
        if msgs and msgs[0].startswith(equipment.DISMANTLE_PREFIX):
            self._menxia_entry(msgs[0], self._xinde())
        return msgs

    def _talked_out_note(self) -> str:
        """談滿了的求見鈕括號裡那一句（單人地點的「求見某某」與求見名單共用；待 joy 潤）：寫換日的那一刻，不寫「今天／明天」
        ——週末那一季的一天不是 24 小時（企劃者 2026-10-08）。開頭一律是「已經談滿」：網頁行動列的格子認它，只寫「已談滿」（審查 I1）。"""
        kind, moment = self._talks_reopen()
        when = f"{moment} 之後再來" if moment else "過一陣子再來" if kind == "later" else "這一季之內不能再來"  # 「過一陣子」：FB-102
        return f"已經談滿 {self._talk_cap()} 輪，{when}"

    def _audience_intro(self) -> str:
        """求見畫面的說明（場景上的那一段）：挑一位拜會；每位人物各算各的，一個遊戲日最多談幾輪、什麼時候重新算起。"""
        here = self.content.locations[self.state.player.location].name
        per_day = self._talk_cap()
        # 你跟這幾位的情誼（explain-1）：挑人之前看得到，跟談話時名字旁寫的是同一個數
        bonds = "、".join(f"{self.content.characters[cid].name} {self.state.player.affinities.get(cid, 0)}" for cid in self._figures_here())
        kind, moment = self._talks_reopen()
        again = f"到 {moment} 重新算起" if moment else "過一陣子重新算起" if kind == "later" else "這一季之內不再重算"  # FB-102
        if precise.on(self.content, self.state.world):  # 一類一顆：求見併進交友，名望不夠的灰著寫還差多少，不打發（FB-421）
            head = SOCIAL_LIST_INTRO.format(here=here, per_day=per_day, again=again)
        else:
            head = f"{here}有好幾位人物，挑一位求見。每位人物各算各的，最多談 {per_day} 輪，{again}；名望不夠的會被打發。"
        return head + (f"\n\n你跟他們的情誼：{bonds}。" if bonds else "")

    def howto_text(self) -> str:
        """設定抽屜的「玩法說明」（Markdown，explain-1 第四項；explain-2 加了這一季在打什麼、名望、投靠與軍令、三方、修練與煉製）：
        數字讀設定（howto.page）。序章略過的人也看得到（設定抽屜誰都打得開；新手期江湖頁另有一個入口）。招募那一句只在內容裡
        真的有人能招募時才寫。"""
        c = self.content
        rule = stance_rule_note(self.state, c) if season_one(c, self.state.world) else ""  # 「這一季在打什麼」那一節的收季規則（explain-2）
        return howto.page(
            c, self.state.world, recruitable=any(ch.kind == "recruitable" for ch in c.characters.values()), rule=rule,
        )

    def _last_talk_line(self, companion_id: str) -> str:
        """談話畫面名字底下的「上回」那一行（人物記得上次談了什麼，Joy 2026-10-23）：時刻、地點、談了什麼；第一次見面是空的。待 joy 潤"""
        memo = companion_agent.last_talk(self.state, companion_id)
        if memo is None:
            return ""
        loc = self.content.locations.get(memo.place)
        where = f"・{loc.name}" if loc is not None else ""
        return f"*上回（{self.stamp(memo.at)}{where}）：{memo.text}*\n\n"

    def affinity_text(self, companion_id: str) -> str:
        """「情誼 N」：你跟這位人物的情誼（PlayerState.affinities，0～100）。談話畫面、求見名單、輿圖的人物都寫這個詞（explain-1：
        玩家看得到的只叫「情誼」，程式裡照舊叫 affinity）。深交不限人數（企劃者 2026-10-28「不要限制深交名額」），不再接「已深交三位」。"""
        return f"情誼 {self.state.player.affinities.get(companion_id, 0)}"

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
            if self._talks_left(companion_id) == 0:  # 這個遊戲日談滿了：寫換日的那一刻（待 joy 潤）
                kind, moment = self._talks_reopen()
                if kind == "later":
                    return f"{ch.name}事忙，過一陣子才得空。"  # FB-102，待 joy 潤
                return f"{ch.name}事忙，要到 {moment} 之後才得空。" if moment else f"{ch.name}事忙，這一季之內都不得空。"
        return "此地無人可訪，你只好悻悻離去。"

    def socialize_starts_dialogue(self) -> bool:
        """在這裡交友會直接跟大勢人物對話（伺服器假人不閒聊大勢人物，見 bot_policy）。在召見的地點不會：交友端出晉升奇遇。"""
        if precise.on(self.content, self.state.world):
            return self._socialize_figure() is not None
        return ranks.summons_event(self.state, self.content) is None and self._socialize_figure() is not None

    def socialize_is_futile(self) -> bool:
        """在這裡交友注定白跑一趟（伺服器假人不該去按）：這個地點沒有交友事件、沒有見得到的大勢人物，
        而且福緣還沒到期（交友最先發福緣，見 _act）。"""
        s, c = self.state, self.content
        if precise.on(c, s.world):  # 一類一顆：沒有人可以說話時鈕是灰的
            return self._social_plan()[0] is None
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

    def _talk(self, arg: str, prepared: companion_agent.PreparedTurn | None = None, said: str | None = None) -> list[str]:
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
        if arg in ("terms:yes", "terms:no", "owed", "repay"):  # NPC 智能 2.0：接不接他的條件、請他兌現、還他（固定文字，不經模型、不扣體力、不算輪數）
            return self._parley_answer(companion_id, arg)
        if arg == "plan":  # NPC 智能 2.1：出陣前跟他商量打法（模型評成功率，不扣體力、不算輪數）
            return self._parley_plan(companion_id, prepared, said)
        affinity = self.state.player.affinities.get(companion_id, 0)
        heard = self._stance_before(companion_id)
        self._parley_decision = None
        try:
            if arg == "say":  # 自己說：said 是 choose 驗過、轉過繁體的那一句；江湖紀錄先寫你說了什麼（同隨口應對的「你：「…」」）
                extra = self._parley_prompt(companion_id)
                msgs = [f"你：「{said}」"] + companion_agent.say_dialogue(
                    self._quick_client(), self.state, self.content, self.world, companion_id, said,
                    turn=self._prepared_turn(prepared), extra=extra, required=parley.ASK_FIELDS if extra else (),
                    decide=lambda turn: self._parley_decide(companion_id, turn, said=said or ""),
                )
            else:
                msgs = companion_agent.continue_dialogue(
                    self._quick_client(), self.state, self.content, self.world, companion_id, int(arg), self.rng,
                    turn=self._prepared_turn(prepared),
                )
        except companion_agent.DialogueUnavailable:
            return self._dialogue_unavailable(companion_id)
        self._stance_credit(companion_id, heard)
        self._annal_talk(companion_id, self.state.player.affinities.get(companion_id, 0) - affinity, said)
        msgs += self._overhear(companion_id, msgs)
        self.state.player.stamina -= self.content.config.talk_stamina  # 每一輪對話都要花體力（伺服器假人設計第八節第 4 項）；生成不出來的那輪不算
        msgs += self._count_talk(companion_id)
        decision, self._parley_decision = self._parley_decision, None
        return msgs + self._parley_finish(companion_id, decision)

    def _parley_finish(self, cid: str, decision: parley.Decision | None) -> list[str]:
        """NPC 智能 2.0那一輪的收尾：結果那一句，答應了就當場做（帶路會在這裡動身）；先做後付另外記下你欠他的那一件。"""
        if decision is None or decision.kind is None:
            return []
        if decision.kind != "owe":
            msgs = [parley.result_line(self.content, cid, decision)]
            return msgs + (self._parley_do(cid, decision.ask.id) if decision.kind == "do" else [])
        due = self._parley_owe(cid, decision.condition, decision.ask)
        msgs = [parley.result_line(self.content, cid, decision, parley.due_text(self.state, self.content, due))]
        return msgs + self._parley_do(cid, decision.ask.id)

    def _parley_owe(self, cid: str, condition: parley.Item, ask: parley.Item, kind: str = "owe") -> float:
        """記下你欠他的一件（先做後付 owe、接了他的請託 plea）：打探、討伐掛成一件委託（書信小卡、懸賞卡上看得到），
        交銀、交素材等你見面「還他」。回期限（世界秒）。"""
        s, c = self.state, self.content
        p = s.player
        due = parley.due_of(s, c, ask.weight if kind == "owe" else condition.weight)
        task_id = None
        if condition.id.partition(":")[0] in ("scout", "strike"):
            p.letter_seq += 1
            task = parley.commission(s, c, cid, condition, ask if kind == "plea" else parley.Item("", ""), p.letter_seq)
            if task is not None:
                task.expires = due
                task.parley_ask = ask.id if kind == "plea" else None
                p.letters.append(Letter(id=p.letter_seq, kind="條件", sender=cid, at=s.world.time,
                                        text=c.characters[cid].name + "託你的事：" + condition.label, read=True, task=task))
                p.letters = p.letters[-c.config.figure_life.letters_keep:]
                task_id = task.id
        p.parley_debts[cid] = ParleyDebt(kind=kind, condition=condition.id, weight=condition.weight if kind == "plea" else ask.weight,
                                         due=due, task=task_id)
        parley.record(s, cid).promised += 1
        return due

    def _annal_talk(self, companion_id: str, delta: int, said: str | None) -> None:
        """對話的一輪寫進行狀（玩家傳）：自己說的那一句一律記（原句與他回的頭一兩句）；挑選項的只在情誼動得多時記。"""
        c, p = self.content, self.state.player
        history = p.dialogue_history.get(companion_id, [])
        reply = history[-1]["content"] if history and history[-1].get("role") == "assistant" else ""
        asked = history[-2]["content"] if len(history) >= 2 and history[-2].get("role") == "user" else ""
        name = annals.figure_name(c, companion_id)
        mood = f"，情誼 {delta:+d}" if delta else ""
        if said is not None:
            weight = 3 if abs(delta) >= c.config.biography.talk_swing else 2
            annals.note(self.state, c, annals.FIGURE, f"對{name}說了一句自己的話{mood}。", weight,
                        figure=companion_id, quote=said, reply=annals.first_sentence(reply))
        elif abs(delta) >= c.config.biography.talk_swing:
            how = "談得投機" if delta > 0 else "話不投機"
            annals.note(self.state, c, annals.FIGURE, f"跟{name}{how}{mood}。", 2,
                        figure=companion_id, quote=asked, reply=annals.first_sentence(reply))

    # ── NPC 智能 2.0（parley.py；Joy 2026-10-23「先做看看」）────────────

    _parley_decision: parley.Decision | None = None  # 這一輪「自己說」擲出來的結果（_parley_decide 記、_talk 收尾時拿去做事）

    def say_max(self) -> int:
        """「自己說」最多幾個字：NPC 智能 2.0開著時照 Config.parley.say_max（要講得清楚一點），關著照舊 SAY_MAX。"""
        return self.content.config.parley.say_max if parley.on(self.content) else SAY_MAX

    def _parley_lists(self, cid: str, road: bool = False) -> tuple[list[parley.Item], list[parley.Item]]:
        """他此刻做得到的事、他可以開的條件（A 段放進提示、C 段拿來驗，兩次要一樣：條件的亂數只看名號、人物、今天）。
        road：帶路的路上，只列沿路做得到的事（parley.road_items）。"""
        s, c = self.state, self.content
        asks = parley.ask_items(s, c, cid, self._side(), can_sortie=not prologue_rules.active(s, c))
        rng = random.Random(f"條件|{s.player.name}|{cid}|{game_day(c, s.world)}")
        return (parley.road_items(asks) if road else asks), parley.condition_items(s, c, cid, rng)

    def _parley_prompt(self, cid: str, road: bool = False) -> str:
        """「自己說」那一輪接在玩家原話後面的一段（NPC 智能 2.0）：關著、今天求滿了是空的，模型就只是談話。"""
        s, c = self.state, self.content
        if not parley.on(c) or parley.asks_left(s, c, cid) <= 0:
            return ""
        asks, conditions = self._parley_lists(cid, road)
        hostile = parley.enemy(s, c, cid, self._side())
        gift = parley.gift_text(parley.gift_of(s, c, cid)) if any(a.id == "gift" for a in asks) else ""
        return parley.prompt_block(c, cid, asks, conditions, s.player.affinities.get(cid, 0), hostile, gift)

    def _parley_decide(self, cid: str, turn: companion_agent.CompanionTurn, road: bool = False, said: str = "") -> companion_agent.CompanionTurn:
        """C 段：驗模型挑的那一件、夾意願、擲骰，記今天求了幾件／婉拒了哪件／開了什麼條件，換上那一版回話。
        關著、今天求滿了、模型沒挑事（只是閒聊）時原樣回去。贈物那一版話跟他真的給的對不上（parley.gift_slip）換固定句；said 是玩家那一句。"""
        s, c = self.state, self.content
        if not parley.on(c) or parley.asks_left(s, c, cid) <= 0 or not (turn.ask or "").strip():
            return turn
        asks, conditions = self._parley_lists(cid, road)
        hostile = parley.enemy(s, c, cid, self._side())
        decision = parley.decide(c, asks, conditions, turn.ask.strip(), turn.willing, (turn.condition or "").strip(),
                                 s.player.affinities.get(cid, 0), hostile, parley.roll(s, cid),
                                 broken=parley.broken_of(s, cid), can_owe=parley.can_owe(s, c, cid))
        record = parley.touch(s, c, cid)
        record.asks += 1
        self._parley_decision = decision
        name = c.characters[cid].name
        if decision.kind == "owe":  # 先做後付：他答應了、也說了要你之後做什麼——給玩家看開條件那一版（說得出條件）
            text = self._parley_gift_check(cid, decision, said, (turn.narrative_terms or "").strip() or turn.narrative)
            return turn.model_copy(update={"narrative": text})
        if decision.kind == "terms":
            cond = parley.condition_text(c, decision.condition, decision.ask.weight)
            text = (turn.narrative_terms or "").strip() or parley.TERMS_FALLBACK.format(name=name, cond=cond)
            text = self._parley_gift_check(cid, decision, said, text)
            s.player.parley_terms[cid] = ParleyTerms(ask=decision.ask.id, condition=decision.condition.id, text=text, at=s.world.time)
            return turn.model_copy(update={"narrative": text})
        if decision.kind == "no":
            if decision.ask.id not in record.refused:
                record.refused.append(decision.ask.id)
            text = (turn.narrative_no or "").strip() or parley.NO_FALLBACK.format(name=name)
            return turn.model_copy(update={"narrative": text})
        text = self._parley_gift_check(cid, decision, said, turn.narrative)
        return turn if text == turn.narrative else turn.model_copy(update={"narrative": text})

    def _parley_gift_check(self, cid: str, decision: parley.Decision, said: str, text: str) -> str:
        """贈物答應了（當場、先做後付、開條件）：話裡給的要是他真的給得出的那一樣，對不上換固定句。別的事原樣回去。"""
        if decision.ask is None or decision.ask.id != "gift":
            return text
        gift = parley.gift_of(self.state, self.content, cid)
        wanted = parley.gift_slip(self.content, gift, said, text)
        if wanted is None:
            return text
        cond = parley.condition_text(self.content, decision.condition, decision.ask.weight) if decision.condition is not None else ""
        return parley.gift_fix(self.content, cid, gift, wanted, decision.kind, cond)

    def _parley_do(self, cid: str, ask_id: str) -> list[str]:
        """他答應的那一件，引擎真的去做（模型只說了話，這裡才動數字與位置）。"""
        s, c = self.state, self.content
        name = c.characters[cid].name
        kind, _, rest = ask_id.partition(":")
        tuning = c.config.parley
        if kind == "escort":
            route = atlas.way_to(s, c, rest)
            if route is None or not parley.can_leave(s, c):
                return [parley.OWED_LATER.format(name=name)]
            s.player.pending_companion = None  # 跟他上路了：這段交談到此為止
            cost = atlas.route_stamina(s, c, route, "walk")
            msgs = [parley.ESCORT_LINE.format(name=name, place=c.locations[rest].name)] + self._depart(route, "walk", pace=tuning.escort_pace)
            s.player.stamina += cost  # 他帶的路：照他的腳程走（比步行快），體力一分不扣
            if self._draft is not None and f"體力 -{cost}" in self._draft.changes:
                self._draft.changes.remove(f"體力 -{cost}")
            if s.player.journey is not None:  # 第二批：路上每到一站可以跟他說一句（_parley_road_option）
                s.player.parley_escort, s.player.parley_road_leg = cid, -1
            return msgs
        if kind == "sortie":
            region = parley.region_of(s, c, cid)
            s.player.parley_backing = ParleyBacking(figure=cid, region=region, day=game_day(c, s.world))
            return [parley.BACKING_LINE.format(name=name, region=parley._region_name(c, region))]
        if kind == "spar":
            parley.touch(s, c, cid).spar = True
            s.player.stats["xinde"] = s.player.stats.get("xinde", 0) + tuning.spar_xinde
            return [parley.SPAR_LINE.format(name=name), f"心得 +{tuning.spar_xinde}"]
        if kind == "intel":
            facts = parley.intel_facts(s, c, cid)
            return [parley.INTEL_HEAD.format(name=name, facts="；".join(facts))] if facts else []
        if kind == "gift":  # 給的就是提示裡寫給模型的那一樣（parley.gift_of）
            gift = parley.gift_of(s, c, cid)
            line = materials.grant(s, c, gift.material, gift.count) if gift.material else None
            if line:
                return [parley.GIFT_LINE.format(name=name, gift=parley.gift_text(gift)), line]
            s.player.stats["silver"] = s.player.stats.get("silver", 0) + tuning.gift_silver
            return [parley.GIFT_LINE.format(name=name, gift=f"{tuning.gift_silver} 兩銀子"), f"銀兩 +{tuning.gift_silver}"]
        return []

    def _parley_options(self, cid: str) -> list[Option]:
        """對話選單上NPC 智能 2.0的鈕：他開了條件、還沒答覆（接、不接）；辦成委託之後他欠你的那一件（請他兌現）。"""
        s, c = self.state, self.content
        if not parley.on(c):
            return []
        opts: list[Option] = []
        terms = s.player.parley_terms.get(cid)
        if terms is not None and terms.plea:  # 他主動開口求你（第二批）：接不接
            opts.append(Option(id="talk:terms:yes", label=parley.PLEA_ACCEPT.format(
                cond=self._parley_cond_label(terms.condition), what=parley.ask_label(c, terms.ask))))
            opts.append(Option(id="talk:terms:no", label=parley.PLEA_DECLINE))
        elif terms is not None:
            weight = next((a.weight for a in self._parley_lists(cid)[0] if a.id == terms.ask), 1)
            cond = parley.condition_text(c, parley.Item(terms.condition, self._parley_cond_label(terms.condition)), weight)
            opts.append(Option(id="talk:terms:yes", label=parley.TERMS_ACCEPT.format(cond=cond)))
            opts.append(Option(id="talk:terms:no", label=parley.TERMS_DECLINE))
        debt = s.player.parley_debts.get(cid)
        if debt is not None and debt.task is None:  # 欠他銀兩、素材（第二批）：見面還
            opts.append(Option(id="talk:repay", label=parley.REPAY_BUTTON.format(name=c.characters[cid].name, cond=parley.debt_text(c, debt))))
        if self._parley_plan_open(cid):  # 答應陪你出陣了（第二批）：出陣前跟他商量打法
            opts.append(Option(id=PLAN_OPTION, label=parley.PLAN_BUTTON.format(name=c.characters[cid].name)))
        owed = s.player.parley_owed.get(cid)
        if owed:
            opts.append(Option(id="talk:owed", label=parley.OWED_BUTTON.format(name=c.characters[cid].name, what=parley.ask_label(c, owed))))
        return opts

    def _parley_cond_label(self, condition_id: str) -> str:
        """條件 id 給玩家看的字（存檔裡只存 id；清單換了也寫得出來）。"""
        kind, _, rest = condition_id.partition(":")
        c = self.content
        if kind == "material":
            return f"交三份{c.materials[rest].name}" if rest in c.materials else "交三份素材"
        if kind in ("scout", "strike"):
            loc = rest.partition(":")[0]
            place = c.locations[loc].name if loc in c.locations else loc
            return f"替他{'打探' if kind == 'scout' else '討伐'}{place}"
        return "交一筆銀兩"

    def _parley_answer(self, cid: str, arg: str) -> list[str]:
        """接不接他的條件（terms:yes／terms:no）、請他兌現欠你的那一件（owed）、還他欠著的銀兩素材（repay，第二批）。
        你求他、他開條件：交銀、交素材當場付、當場做；打探、討伐掛成一件委託（同書信的委託），辦成了他欠你那一件
        （bounties._complete_commission 記 parley_owed）。他主動開口求你（plea）：接了是一件委託、記成你欠他的（到期沒做是食言）。"""
        s, c = self.state, self.content
        p = s.player
        name = c.characters[cid].name
        if arg == "owed":
            owed = p.parley_owed.get(cid)
            if not owed:
                return ["（此刻無法這麼做。）"]
            asks = {a.id for a in parley.ask_items(s, c, cid, self._side(), can_sortie=not prologue_rules.active(s, c))}
            if owed not in asks:
                return [parley.OWED_LATER.format(name=name)]
            p.parley_owed.pop(cid)
            return [parley.OWED_DONE.format(name=name)] + self._parley_do(cid, owed)
        if arg == "repay":
            debt = p.parley_debts.get(cid)
            if debt is None or debt.task is not None:
                return ["（此刻無法這麼做。）"]
            paid = self._parley_pay(debt.condition, debt.weight)
            if paid is None:
                return [parley.TERMS_SHORT]
            del p.parley_debts[cid]
            text = parley.debt_text(c, debt)
            parley.keep(s, c, cid, text)
            return paid + [parley.REPAID.format(name=name, cond=text)]
        terms = p.parley_terms.pop(cid, None)
        if terms is None:
            return ["（此刻無法這麼做。）"]
        if arg == "terms:no":
            return [(parley.PLEA_DECLINED if terms.plea else parley.TERMS_DECLINED).format(name=name)]
        if terms.plea:
            want = parley.Item(terms.condition, self._parley_cond_label(terms.condition),
                               2 if terms.condition.startswith("strike:") else 1)
            due = self._parley_owe(cid, want, parley.Item(terms.ask, parley.ask_label(c, terms.ask)), kind="plea")
            return [parley.PLEA_TAKEN.format(name=name, cond=want.label, due=parley.due_text(s, c, due),
                                             what=parley.ask_label(c, terms.ask))]
        weight = next((a.weight for a in self._parley_lists(cid)[0] if a.id == terms.ask), 1)
        kind = terms.condition.partition(":")[0]
        if kind in ("silver", "material"):
            paid = self._parley_pay(terms.condition, weight)
            if paid is None:
                p.parley_terms[cid] = terms
                return [parley.TERMS_SHORT]
            found = parley.record(s, cid)
            found.promised += 1
            parley.keep(s, c, cid, parley.debt_text(c, ParleyDebt(kind="terms", condition=terms.condition, weight=weight, due=0)))
            return paid + self._parley_do(cid, terms.ask)
        item = parley.Item(terms.condition, self._parley_cond_label(terms.condition))
        p.letter_seq += 1
        task = parley.commission(s, c, cid, item, parley.Item(terms.ask, parley.ask_label(c, terms.ask), weight), p.letter_seq)
        if task is None:
            return ["（此刻無法這麼做。）"]
        p.letters.append(Letter(id=p.letter_seq, kind="條件", sender=cid, at=s.world.time, text=terms.text, read=True, task=task))
        p.letters = p.letters[-c.config.figure_life.letters_keep:]
        parley.record(s, cid).promised += 1
        return [f"你答應了{name}：{item.label}。辦成了，下回見到他，他兌現答應你的事。"]

    def _parley_pay(self, condition: str, weight: int) -> list[str] | None:
        """當場交銀、交素材（條件、還債共用）：手頭不夠回 None、什麼都不動；夠就扣掉，回那幾行變化。"""
        s, c = self.state, self.content
        p = s.player
        kind, _, rest = condition.partition(":")
        if kind == "silver":
            price = parley.silver_of(c, weight)
            if p.stats.get("silver", 0) < price:
                return None
            p.stats["silver"] -= price
            return [f"銀兩 -{price}"]
        need = c.config.parley.material_terms
        if rest not in c.materials or materials.held(s, rest) < need:
            return None
        materials.take(s, rest, need)
        return [f"{c.materials[rest].name} -{need}"]

    def _parley_plea_lists(self, cid: str) -> tuple[list[parley.Item], list[parley.Item]]:
        """他主動開口時的兩份清單：他想請你做的事、他可以回報的事（A、C 兩次要一樣：亂數只看名號、人物、今天）。"""
        s, c = self.state, self.content
        rng = random.Random(f"請託|{s.player.name}|{cid}|{game_day(c, s.world)}")
        rewards = [a for a in self._parley_lists(cid)[0] if a.id != "sortie"]  # 陪你出陣要你先開口，回報不給它
        return parley.wants(s, c, cid, rng), rewards

    def _parley_plea_prompt(self, cid: str) -> str:
        """求見開場那一輪接在提示後面的一段（他主動開口求你）：他此刻沒心事、今天開口過、你跟他還有沒了的事是空的。
        假人（client 是 None）不叫模型，這段放了也用不到。"""
        s, c = self.state, self.content
        if cid not in c.characters or prologue_rules.active(s, c):
            return ""
        mood = parley.pleading(s, c, cid)
        if mood is None:
            return ""
        wanted, rewards = self._parley_plea_lists(cid)
        if not wanted or not rewards:
            return ""
        return parley.plea_prompt(c, cid, mood, wanted, rewards)

    def _parley_plea(self, cid: str, turn: companion_agent.CompanionTurn) -> companion_agent.CompanionTurn:
        """C 段：開場那一輪模型挑了請託與回報，驗過了記成他開的條件（plea），對話選單上多「接下／不接」。今天開口過了就不再開。"""
        s, c = self.state, self.content
        if not self._parley_plea_prompt(cid):
            return turn
        wanted, rewards = self._parley_plea_lists(cid)
        picked = parley.plea_pick(wanted, rewards, turn.want, turn.reward)
        parley.touch(s, c, cid).plea = True
        if picked is None:
            return turn
        want, reward = picked
        s.player.parley_terms[cid] = ParleyTerms(ask=reward.id, condition=want.id, text=turn.narrative, at=s.world.time, plea=True)
        return turn

    def _parley_plan_open(self, cid: str) -> bool:
        """對話選單上「跟他商量打法…」：今天答應陪你出陣的就是他、這一仗還沒打、還沒商量過。"""
        b = self.state.player.parley_backing
        return (parley.on(self.content) and b is not None and b.figure == cid and b.plan is None
                and b.day == game_day(self.content, self.state.world))

    def _parley_plan_prompt(self, cid: str) -> str:
        b = self.state.player.parley_backing
        return parley.plan_prompt(self.content, cid, b.region if b is not None else None) if self._parley_plan_open(cid) else ""

    def _parley_plan(self, cid: str, prepared: companion_agent.PreparedTurn | None, said: str | None) -> list[str]:
        """出陣前跟他商量打法（同放手一搏）：模型只評成功率、寫成敗兩版，引擎夾在 plan_floor～plan_cap、自己擲。
        成了這一仗他的部曲出力加倍、沒成這一仗他幫不上忙（Game._act 的 train 那一支照 parley_backing.plan 算）。不扣體力、不算輪數。"""
        s, c = self.state, self.content
        if not self._parley_plan_open(cid) or said is None:
            return ["（此刻無法這麼做。）"]
        try:
            turn = self._prepared_turn(prepared)
            if turn is None:
                request = companion_agent.build_request(s, c, self.world, cid, PLAN_OPTION, said, free=True,
                                                        extra=self._parley_plan_prompt(cid), required=parley.PLAN_FIELDS)
                turn = companion_agent.generate_turn(self._quick_client(), request.messages, request.required)
        except companion_agent.DialogueUnavailable:
            return [f"{c.characters[cid].name}沉吟不語。"]
        if turn.willing is None:  # 模型沒評（schema 已經不准，以防萬一）：當這一輪沒談成、打法照舊可以再商量，不默默夾到 plan_floor
            return [f"{c.characters[cid].name}沉吟不語。"]
        cfg = c.config.parley
        chance = max(cfg.plan_floor, min(cfg.plan_cap, int(turn.willing)))
        hit = parley.plan_roll(s, cid) <= chance
        s.player.parley_backing.plan = hit
        name = c.characters[cid].name
        text = turn.narrative if hit else ((turn.narrative_no or "").strip() or f"{name}搖了搖頭，沒有照你說的布置。")
        companion_agent._record_turn(s, cid, said, turn.model_copy(update={"narrative": text}))  # 談話畫面寫他這一句、下一輪記得談過打法
        return [f"你：「{said}」", text, (parley.PLAN_HIT if hit else parley.PLAN_MISS).format(name=name)]

    def _parley_road_option(self, j: Journey) -> Option | None:
        """他帶你走的這一趟（parley_escort）：每到一站一次，「跟他說…」。"""
        s, c = self.state, self.content
        cid = s.player.parley_escort
        if not parley.on(c) or cid is None or cid not in c.characters or s.player.parley_road_leg == j.reached:
            return None
        return Option(id=ROAD_SAY, label=parley.ROAD_BUTTON.format(name=c.characters[cid].name))

    def _road_say(self, prepared: companion_agent.PreparedTurn | None, said: str | None) -> list[str]:
        """帶路的路上跟他說一句（第二批）：一輪不花體力的對話；也可以求他沿路做得到的事（parley.road_items），走同一套夾、擲。"""
        s, c = self.state, self.content
        cid, j = s.player.parley_escort, s.player.journey
        if cid is None or j is None or said is None or s.player.parley_road_leg == j.reached:
            return ["（此刻無法這麼做。）"]
        affinity = s.player.affinities.get(cid, 0)
        heard = self._stance_before(cid)
        self._parley_decision = None
        extra = self._parley_prompt(cid, road=True)
        try:
            msgs = [f"你：「{said}」"] + companion_agent.say_dialogue(
                self._quick_client(), s, c, self.world, cid, said, turn=self._prepared_turn(prepared),
                extra=extra, decide=lambda turn: self._parley_decide(cid, turn, road=True, said=said or ""),
                required=parley.ASK_FIELDS if extra else (),
            )
        except companion_agent.DialogueUnavailable:
            return [f"{c.characters[cid].name}沉吟不語。"]
        self._stance_credit(cid, heard)
        s.player.parley_road_leg = j.reached
        self._annal_talk(cid, s.player.affinities.get(cid, 0) - affinity, said)
        decision, self._parley_decision = self._parley_decision, None
        return msgs + self._parley_finish(cid, decision)

    def _parley_backing_here(self) -> str | None:
        """今天答應陪你出陣、而且你此刻就在他那一帶：回那位人物的 id。"""
        s, c = self.state, self.content
        b = s.player.parley_backing
        if b is None or b.day != game_day(c, s.world):
            return None
        here = figure_life._region(c, s.player.location)
        return b.figure if b.region is None or here == b.region else None

    def _side(self) -> str | None:
        """敵我的一個讀法（allied.side_of）：豪強分屬兩軍的季，豪強是依附的那一軍；其他人是自己的陣營（散人 None）。"""
        return allied.side_of(self.state, self.content)

    def _ally_options(self, cancel: bool) -> list[Option]:
        """選邊的兩顆（豪強分屬兩軍；照劇本 allies 的順序，鈕上寫那一軍此刻幾人，人數照 allied.side_totals）；
        投靠的確認畫面上多「再想想」，拜入門派之後那兩顆不能略過。"""
        sides = allied.side_totals(self.world.roll_counts())
        faction = self.state.player.pending_faction or self.state.player.faction
        opts = [
            Option(id=f"faction:ally:{a.id}", label=allied.ALLY_BUTTON.format(ally=a.name, n=sides.get(a.id, 0)))
            for a in allied.allies_of(self.content, faction)
        ]
        return opts + ([Option(id="faction:cancel", label="再想想")] if cancel else [])

    def _faction_step(self, arg: str) -> list[str]:
        """投靠分兩步（伺服器假人設計第八節第 3 項）：按「投靠某陣營」先出確認畫面（寫明這一季
        不能改投、各方目前各有幾人），「確定」才真的投靠，「再想想」就作罷。
        豪強分屬兩軍的季（allied.on），投靠豪強中間多一步挑依附哪一軍（ally:<id>）；拜入要依附的門派之後（allied.needs_ally）
        也按 ally:<id> 挑，挑了就算投靠完成。"""
        p = self.state.player
        if arg == "cancel":
            p.pending_faction = p.pending_ally = None
            return ["你決定再想想。"]
        kind, _, ally_id = arg.partition(":")
        if kind == "lean":  # 三陣營四勝利：豪強改幫另一軍（本週卡「改幫黃巾」；選單只在 _lean_options 給）
            return self._lean_step(ally_id)
        if kind == "ally":
            ally = self.content.scenario.faction(ally_id)
            if p.pending_faction is None:  # 拜入門派之後挑一邊（選單只在 needs_ally 時給這兩顆）
                p.ally = ally.id
                return [allied.ALLY_DONE.format(ally=ally.name)] + self._ally_follows_battle()
            p.pending_ally = ally.id
            prompt = self._faction_prompt(self.content.scenario.faction(p.pending_faction))
            self._hide(prompt)
            return [prompt]
        if arg == "confirm":
            faction = self.content.scenario.faction(p.pending_faction)
            ally, p.pending_faction, p.pending_ally = p.pending_ally, None, None
            if p.location not in faction.join_at:
                return ["（你已經不在投靠的地方了。）"]
            p.faction = faction.id
            p.ally = self._bot_lean(faction.id, ally) if allied.on(self.content, self.state.world) else None
            # 投靠這一刻就推一次新手引導：第一季「投靠、看一眼本週軍令」那一步只看陣營（計畫 T6）；beta 照舊等下一個行動
            msgs = [f"你投靠了{allied.label(self.content, p.faction, p.ally)}。"]
            if p.ally is not None:
                msgs += self._ally_follows_battle()  # 先臨時投效了另一邊的散人（FB-273）
            if season_one(self.content, self.state.world):
                msgs += self._guide(note_action(self.state, self.content, self.world, "join"))  # 走對話框（畫面批次審查 I2）
            return msgs
        faction = self.content.scenario.faction(arg)
        # 三陣營四勝利開著的季，投靠豪強照投靠點直接給傾向、不出選邊鈕（企劃者 2026-10-24 第 6 件；之後隨時改幫）
        lean = wins.join_lean(self.content, faction.id, p.location) if self._four_wins() and allied.on(self.content, self.state.world) else None
        p.pending_faction, p.pending_ally = faction.id, lean
        prompt = self._faction_prompt(faction)
        self._hide(prompt)  # 場景已經寫著這一問（_own_scene_text），江湖紀錄那一則只留標題（FB-046）
        return [prompt]

    def _bot_lean(self, faction_id: str, picked: str | None) -> str | None:
        """三陣營四勝利開著的季，伺服器假人投靠豪強那一下的傾向（FB-810）：依附豪強人數少的那一軍（wins.bot_lean，確認這一下才數），
        不看投靠點；真人、兩軍的人、開關關著（還有選邊鈕）都照 picked。假人投靠之後不按「改幫」，所以這一下就是它這一季幫誰。"""
        if self.state.player.bot is None or not self._four_wins():
            return picked
        season = self.world.get_season_number()
        return wins.bot_lean(self.state.player.name, season, self.content, faction_id, self.world.roll_counts()) or picked

    def _lean_options(self) -> list[Option]:
        """本週卡「改幫…」（三陣營四勝利，設計 3.2）：豪強能幫、此刻沒在幫的那幾軍各一顆，不花體力、隨時換、不算叛投。
        按不下去（wins.lean_problem）灰著寫原因。開關關著、不是豪強是空的。"""
        s, c = self.state, self.content
        if not self._four_wins() or not wins.is_gentry(s.player, c):
            return []
        opts = []
        for side in wins.lean_sides(s.player, c):
            label = wins.LEAN_BUTTON.format(side=c.scenario.faction_name(side, side))
            problem = wins.lean_problem(s.player, c, side)
            opts.append(Option(id=f"{wins.LEAN_PREFIX}{side}", label=f"{label}（{problem}）" if problem else label, enabled=not problem))
        return opts

    def _lean_anytime(self, option_id: str) -> Option | None:
        """「改幫…」不看此地的選單（設計 3.2「隨時換」，FB-812）：選單上沒有它的時候（在路上、人站在正在打決戰的大區，
        選單只剩那些事）照樣收（有事件待選是例外，choose 擋：FB-820），條件跟選單上的那一顆一樣（_lean_options：豪強、四勝利開著，按不下去的原因照 wins.lean_problem）。
        只有賽季不在跑（籌備中、休季、時鐘暫停，這幾種選單本來就只剩一顆灰的）才不收；開關關著、不是豪強、本來就幫它、
        不是它能幫的那一軍，都找不到那一顆，照舊「此刻無法這麼做」。決戰那一場的戰功照舊記參戰那一軍，開打了這一場照舊站原來那一邊
        （_lean_step 的 _ally_follows_battle）。"""
        if self.world.paused_at() is not None or self._preparing() or self.state.world.ended:
            return None
        return next((o for o in self._lean_options() if o.id == option_id), None)

    def _lean_step(self, side: str) -> list[str]:
        """豪強改幫 side（wins.set_lean：寫 ally、換邊次數 +1，不算叛投、帳不清）。跟著換的：活躍名單搬到新的那一邊（人數緩衝照新的
        那一邊算），決戰集結中參戰名單跟著換、開打了這一場照舊（_ally_follows_battle，FB-273），手上揭著、新的那一邊接不了的
        懸賞作廢、每張一句（不扣東西，PM 2026-10-25 第 4 件）。投靠名冊由 choose() 結尾的 _record_faction 改記。不發傳聞；
        江湖紀錄就是這一下的那一則（choose 寫）。"""
        s, c = self.state, self.content
        p, w = s.player, s.world
        old = p.ally
        if not self._four_wins() or not wins.set_lean(p, c, side):
            return ["（此刻無法這麼做。）"]
        names = w.active_pushers.get(old or "")
        if names is not None and p.name in names:
            w.active_pushers.setdefault(side, {})[p.name] = names.pop(p.name)
            if not names:
                del w.active_pushers[old]
        new_name = c.scenario.faction_name(side, side)
        msgs = [wins.LEAN_DONE.format(side=new_name, old=c.scenario.faction_name(old, old) if old else new_name)]
        return msgs + bounties.drop_stranded(s, c, side, lean=True) + self._ally_follows_battle()  # 作廢那一句寫「改幫」，不是投靠、叛投的「改投」（FB-811）

    def _join_lean(self) -> list[str]:
        """三陣營四勝利開著的季，拜入要依附一軍的門派而投靠（曹氏莊院）的那一下：照門派所在地直接給傾向（PM 2026-10-25 第 5 件），
        不出選邊鈕；先臨時投效了另一邊的照 _ally_follows_battle 換過去。其他時候什麼都不做（照舊 allied.needs_ally 出選邊鈕）。"""
        s, c = self.state, self.content
        p = s.player
        if not self._four_wins() or not allied.needs_ally(s, c):
            return []
        sect = c.sects.get(p.sect) if p.sect else None
        p.ally = wins.join_lean(c, p.faction, sect.location if sect is not None else p.location)
        return [allied.ALLY_DONE.format(ally=c.scenario.faction_name(p.ally, p.ally))] + self._ally_follows_battle()

    def _ally_follows_battle(self) -> list[str]:
        """選邊的那一刻（豪強分屬兩軍），人已經在這一場決戰的參戰名單上、站的是另一邊（先臨時投效了，FB-273）：集結時照新選的
        那一邊換過去（同改選：份量照這一刻重新快照），開打了照決戰的規則不能改投（同 _enlist），這一場照舊站原來那一邊；兩種都說一句。
        沒有決戰、不在名單上、本來就站這一邊，什麼都不做。"""
        status = self._battle_for_me(tick=False)
        if status is None:
            return []
        battle, definition = status
        name, side, sides = self.state.player.name, self._side(), self._sides(definition)
        me = battle.participants.get(name)
        if me is None or me.faction == side or side not in sides:
            return []
        if battle.phase != "muster":
            return [allied.ALLY_STAYS.format(battle=definition.name, ally=sides[side], old=sides.get(me.faction, me.faction))]
        scores = self._mandate_weight(definition, self._battle_scores())
        gear, marks = self._battle_gear(), self._battle_marks()
        self._mutate_battle_of(
            battle,
            lambda b: battle_instance.join_faction(
                b, name, side, self._battle_neili_cap(), self._battle_power(), scores=scores, attribute=self._battle_road(),
                role=self._battle_role(), **gear, **marks,
            ),
        )
        return [allied.ALLY_REJOINED.format(battle=definition.name, ally=sides[side])]

    def _defect_step(self, arg: str) -> list[str]:
        """叛投分兩步（同投靠）：按「叛投某陣營」先出確認畫面（寫明代價、一季一次、三方人數），「確定」才真的叛投。
        確定時再驗一次（defection.refusal，跟選單挑對象的 targets_here 同一套規則：還在那個投靠點、還能叛投、不是自己的陣營、
        名字不在沒打完的決戰的參戰名單上）：中間走開了、規則關了、另一個分頁已經叛投過、報了名參戰，都不叛投，
        而且把真正的原因說給玩家聽；那一則江湖紀錄也不寫成「叛投某某」（沒叛成）。
        投靠名冊由 choose() 結尾的 _record_faction 改記，這裡不碰。
        豪強分屬兩軍的季，arg 可以是「陣營:依附的那一軍」（defection.slots_here），挑的那一軍記在 pending_ally。"""
        p = self.state.player
        if arg == "cancel":
            p.pending_defect = p.pending_ally = None
            return ["你決定再想想。"]
        if arg == "confirm":
            target = self.content.scenario.faction(p.pending_defect)
            ally, p.pending_defect, p.pending_ally = p.pending_ally, None, None
            reason = defection.refusal(self.state, self.content, target, self._battle_now(), ally)
            if reason is not None:
                if self._draft is not None:
                    self._draft.title = "叛投不成"
                return [f"（{reason}）"]
            return (defection.defect(self.state, self.content, target, ally) + self._leave_behind(target.id)
                    + parley.forsake_all(self.state, self.content))  # NPC 智能 2.1：接了又叛投，欠著的都算食言
        fid, _, ally = arg.partition(":")
        target = self.content.scenario.faction(fid)
        p.pending_defect, p.pending_ally = target.id, ally or None
        prompt = defection.prompt(self.state, self.content, target, self.faction_counts_text(), p.pending_ally, self._left_names(target.id))
        self._hide(prompt)  # 場景已經寫著這一問（_own_scene_text），江湖紀錄那一則只留標題（同投靠，FB-046）
        return [prompt]

    def _left_names(self, side: str) -> list[str]:
        """叛投確認畫面「會失去」那一段的同伴（歷史武將同行 9.5）：寫了 side、跟新陣營不合的。按鈕回的那一份與場景那一段（FB-362）共用。"""
        return [self.content.characters[cid].name for cid in roster.left_behind(self.state, self.content, self.world, side)]

    def _leave_behind(self, side: str) -> list[str]:
        """叛投之後（歷史武將同行 9.5）：寫了 side、跟新陣營不合的同伴當場回江湖——全服放掉 owner、拿出隊伍、情誼照決戰後回江湖減半。"""
        c, p = self.content, self.state.player
        keep, out = c.config.companions.parted_keep, []
        for cid in roster.left_behind(self.state, c, self.world, side):
            self.world.release_companion(cid)
            team.remove_from_team(self.state, cid)
            before = p.affinities.get(cid, 0)
            p.affinities[cid] = math.floor(before * keep)
            out.append(roster.DEFECT_LEFT.format(name=c.characters[cid].name, before=before, after=p.affinities[cid]))
        return out

    def _defect_targets(self) -> list[tuple[FactionDef, str | None]]:
        """這一刻選單上能叛投去的（陣營, 依附的那一軍）。先用不碰資料庫的條件擋掉大多數人（散人、劇本沒有陣營、叛投過），
        剩下的才讀目前的決戰、看名字在不在參戰名單上（defection.enlisted）。豪強分屬兩軍的季見 defection.slots_here。"""
        if not defection.can_defect(self.state, self.content):
            return []
        return defection.slots_here(self.state, self.content, self._battle_now())

    def _faction_prompt(self, faction) -> str:
        p = self.state.player
        counts = self.faction_counts_text()
        if allied.on(self.content, self.state.world) and faction.allies and p.pending_ally is None:  # 豪強分屬兩軍：先挑一邊
            return allied.ALLY_PICK.format(counts=counts)
        side = p.pending_ally or faction.id  # 依附的豪強接的是那一軍的懸賞
        held = bounties.stranded(self.state, self.content, side)  # 手上揭著、投靠之後接不了的懸賞（FB-151）；沒有就一個字不多
        lost = bounties.STRANDED_JOIN.format(n=len(held)) if held else ""
        return f"投靠後這一季不能改投（叛投另論）。{lost}{counts}。確定投靠{allied.label(self.content, faction.id, p.pending_ally)}？"

    def faction_counts_text(self) -> str:
        """名冊那一句（allied.roster_text）：「目前官軍 N 人、黃巾軍 M 人、地方豪強 K 人」，照全服投靠名冊（真人與假人一起算）；
        豪強分屬兩軍的季照兩軍寫、括號寫豪強（「目前官軍 12 人（其中豪強 3 人）、黃巾軍 9 人」）。"""
        return allied.roster_text(self.content, self.state.world, self.world.roll_counts())

    def _roster_players(self) -> int:
        """這一季投靠了陣營的人數（全服投靠名冊，真人與假人一樣算）：跟 world.advance_world_state 查來縮放割據漲速的是
        同一個算式，割據的說明（rules.chaos_note）才說得準現在是在漲還是不動（FB-065 M1）。每次畫面現查，只是讀。"""
        return sum(self.world.roll_counts().values())

    def _record_faction(self) -> None:
        """把自己的陣營記進全服投靠名冊（陣營人數看這份；鍵是 allied.roll_key，依附的豪強寫「haoqiang@guan」）；已經記過同一個鍵
        就不再寫。choose() 結束時與 sync() 都會呼叫，名冊出現之前就投靠了的人（或拜入門派而投靠的人）也會補記進去。
        還沒挑依附哪一邊（allied.needs_ally，拜入曹氏莊院那一下）先不記。"""
        p = self.state.player
        if p.faction is None or allied.needs_ally(self.state, self.content):
            return
        key = allied.roll_key(p.faction, p.ally if allied.on(self.content, self.state.world) else None)
        if self.world.roll_of(p.name) != key:
            self.world.record_faction(p.name, key)

    # ── 全服即時多人戰鬥（設計討論：集結選陣營→逐幕逐回合鎖步）──────────

    def _battle_power(self, *, seal: bool = True) -> float:
        """玩家自己目前的武學威力快照，加入戰鬥時存一份進 BattleParticipant.power，
        之後戰鬥結算的威力抵銷只讀這份快照，不會、也不能臨時去查任何人的角色資料
        （見 battle_instance.py::BattleParticipant 的欄位註解）。快照吃本人的加成（臂力、根骨，武學與成長設計 8.4）。
        同伴不進決戰（人物資質設計 14.5），這裡照舊只算本人。seal=False 不含玉璽碎片的戰力（奪璽單挑、江湖水漲；team.player_boost）。"""
        arts = team.team_arts(self.state, self.content, self.world)
        return encounter.member_power(
            self.state.player.member, arts, boost=team.player_boost(self.state, self.content, self.world, seal=seal),
        )

    def _battle_scores(self, mounted: bool = True, *, seal: bool = True) -> dict[str, float]:
        """加入戰局時的每招份量快照（戰鬥系統 3.4）：實力看武學威力（_battle_power），適性看身上武學與內功的屬性；
        騎著馬時強攻、奇襲再乘（1＋騎兵）（裝備四欄 5.9，_battle_mount），帶著部下再乘（1＋部下）（_battle_troops）。
        mounted=False 不算馬也不算部下：單人頭目戰用同一份份量，騎兵與部下只在全服決戰（設計 2.1；PM 2026-10-12）。只有加入戰局的那個玩家自己的 Game 能算（排程的 Game.for_world 玩家是空白的，
        不能在 world_tick 裡呼叫）。seal 見 _battle_power。"""
        p = self.state.player
        outer = team.player_art(self.state, self.content, self.world, p.member.wugong_id)
        inner = team.player_art(self.state, self.content, self.world, p.member.neigong_id)
        return battle_instance.move_scores(
            self.content.config.battle, self._battle_power(seal=seal),
            outer.attribute if outer else None, inner.attribute if inner else None, role=self._battle_role(),
            cavalry=self._battle_mount()[1] if mounted else 0.0, troops=self._battle_troops()[1] if mounted else 0.0,
        )

    def _battle_role(self) -> str:
        """進場的職位（試玩回饋 2026-10-08）：本人最突出的屬性（battle_instance.role_for）。真人、散人臨時投效、假人都走這裡。"""
        stats = team.member_stats(self.state, self.content, self.world, team.PLAYER)
        return battle_instance.role_for(stats, team.COMBAT_STATS)

    def _battle_mount(self) -> tuple[str, float]:
        """加入決戰那一刻騎的馬（裝備四欄 5.9）：（馬名, 騎兵加成）；沒騎馬、坐騎關著是 ("", 0.0)。跟份量一起快照進
        BattleParticipant（mount、cavalry），之後換馬、馬餓了都不影響這一場。只在玩家自己的路徑呼叫（同 _battle_scores）。"""
        item = mounts.riding(self.state, self.content)
        bonus = mounts.cavalry(self.state, self.content)
        return (mounts.name_of(item), bonus) if item is not None and bonus > 0 else ("", 0.0)

    def _battle_troops(self) -> tuple[str, float]:
        """加入決戰那一刻帶的部下（PM 2026-10-12）：（「兩名持矛鄉勇」, 每名 Config.follower.battle_per 加起來）；沒有部下
        （第一季關著、還沒晉升）是 ("", 0.0)。跟份量一起快照進 BattleParticipant（troops、troop_bonus）。"""
        rows = team.follower_rows(self.state, self.content)
        if not rows:
            return "", 0.0
        return team.troop_names([f for _, f in rows]), len(rows) * self.content.config.follower.battle_per

    def _battle_gear(self) -> dict:
        """快照進 BattleParticipant 的坐騎與部下（join_faction／auto_assign_latecomer 的 mount、cavalry、troops、troop_bonus）。"""
        horse, cavalry = self._battle_mount()
        troops, bonus = self._battle_troops()
        return {"mount": horse, "cavalry": cavalry, "troops": troops, "troop_bonus": bonus}

    def _battle_marks(self) -> dict:
        """快照進 BattleParticipant 的「這一季叛投過」與「新手期」（玉璽碎片設計 4.6：挑挑戰者只讀快照），
        與稱號（名聲 2.5、4.5：本場戰功、論功那一句寫；名望名動一方起、善惡第 1 段起，開關關著是空的）。"""
        marks = {"turncoat": self.state.player.defected, "newbie": roster.newbie(self.state, self.content),
                 "kit": team.self_side(self.state, self.content, self.world, mounted=True, troops=True),  # 本命戰法（第二批）
                 "renown": renown.titles(self.state, self.content, fame_from=2),
                 "escort": self._escort_carry()}  # 隨你上陣的歷史武將（歷史武將同行第五節）
        bare = self._seal_bare()
        if bare is not None:  # 玉璽碎片改版：只有戴著碎片才多這一鍵（沒碎片、改版關著時這一包一個字不變）
            marks["seal_bare"] = bare
        return marks

    def _seal_bare(self) -> battle_instance.SealBare | None:
        """戴著玉璽碎片（改版開著，treasures.power_scale 不是 1）時，不含碎片戰力的威力與份量（快照進 BattleParticipant.seal_bare，
        奪璽單挑用）；沒有是 None。份量照加入那一刻的算法（騎兵、部下照乘，單挑時 seal_duel.unmounted 再拿掉）。"""
        if treasures.power_scale(self.state, self.content) == 1.0:
            return None
        return battle_instance.SealBare(power=self._battle_power(seal=False), scores=self._battle_scores(seal=False))

    def _escort_choices(self) -> list[str]:
        """加入決戰時挑得到的同伴：名下的（歷史武將同行第五節）。開關關著是空的（照舊一下就加入）。"""
        if not roster.on(self.content):
            return []
        return [cid for cid in roster.owned_companions(self.world, self.state.player.name) if cid in self.content.characters]

    def _escort_of(self, cid: str) -> battle_instance.Escort:
        """派他上陣的那一刻快照（第五節【預設】）：份量＝strength(他的威力) × escort_share（不吃你的職位、坐騎、部下），
        池子是他的氣血上限，戰法是他自己身上的兩門。"""
        s, c, w = self.state, self.content, self.world
        pool = team.mate_pool(s, c, w, cid)
        score = battle_instance.strength(c.config.battle, team.mate_power(s, c, w, cid)) * c.config.battle.generals.escort_share
        return battle_instance.Escort(
            cid=cid, name=c.characters[cid].name, score=round(score, 1), neili=pool, neili_cap=pool, kit=team.mate_side(s, c, w, cid),
        )

    def _escort_carry(self) -> battle_instance.Escort | None:
        """這一次加入要帶的同伴：剛在挑的那一位（_escort_step）；不然是已經在參戰名單上的那一位（集結時改選、依附那一軍重新快照，照舊跟著）。"""
        if self._escort_picked:
            return self._escort_now
        battle = self._battle_now()
        me = battle.participants.get(self.state.player.name) if battle is not None else None
        return me.escort if me is not None else None

    def _escort_options(self) -> list[Option]:
        """按了加入、還在挑誰隨你上陣：名下每一位一顆（寫份量與氣血），加上「不派」「再想想」。"""
        out = []
        for cid in self._escort_choices():
            e = self._escort_of(cid)
            out.append(Option(id=f"battle:escort:{cid}", label=ESCORT_OPTION.format(name=e.name, score=round(e.score), pool=round(e.neili_cap))))
        return out + [Option(id="battle:escort:none", label=ESCORT_NONE), Option(id="battle:escort:back", label=ESCORT_BACK)]

    def _escort_step(self, battle: battle_instance.BattleInstance, arg: str) -> list[str]:
        """挑好了（battle:escort:<id>／none）或「再想想」（back）：照記下的那一下（PlayerState.escort_pick）加入，帶著挑的那一位。
        集結時按的、挑的時候已經開打了，改成晚到（join_late）。"""
        p = self.state.player
        pick, p.escort_pick = p.escort_pick, ""
        if not pick:
            return ["（此刻無法這麼做。）"]
        if arg == "back":
            return [ESCORT_BACK_LINE]
        if arg != "none" and arg not in self._escort_choices():
            return ["（此刻無法這麼做。）"]
        pick, at, ref = pick.partition("@")  # 同一個大區兩場以上時記著是哪一場（領地爭奪第二批）
        kind, _, rest = pick.partition(":")
        if kind == "join" and battle.phase != "muster":
            kind, rest = "join_late", ""
        self._escort_picked, self._escort_now = True, (self._escort_of(arg) if arg != "none" else None)
        try:
            return self._battle_choose(f"{kind}:{rest}{at}{ref}")
        finally:
            self._escort_picked, self._escort_now = False, None

    def _escort_home(self, e: battle_instance.Escort) -> list[str]:
        """補這一場戰報時（_file_showdown）：他回江湖了——拿出出戰隊伍、寫一句，情誼照 _settle_partings 減半（同一則紀錄裡說）。"""
        team.remove_from_team(self.state, e.cid)
        line = (escorts.FELL_RETURN_LINE if e.fallen_round is not None else escorts.RETURN_LINE).format(name=e.name)
        return [line] + self._settle_partings(write=False)

    def _settle_partings(self, write: bool = True) -> list[str]:
        """歷史武將同行 9.6：決戰收場時從你身邊回江湖的人（CompanionProgress.parted_from 有你的名號），情誼乘 parted_keep（無條件捨去）。
        同步、按招募之前與補戰報時叫；write 時另起一則「同伴回江湖」紀錄（補戰報時併進那一則，不另寫）。開關關著什麼都不做。
        全服的記號不在減半那一下清（FB-361）：減了記進 PlayerState.parted_done，記號留到之後再叫到這裡、看到這一份角色已經減過才清
        （同一次同步裡補戰報先減、後面那一次清；收場在輪詢組畫面時發生、角色沒存的話，下一次同步照存檔裡沒減過的那一份再減一次）。"""
        c, p = self.content, self.state.player
        if not roster.on(c):
            return []
        keep = c.config.companions.parted_keep
        lines = []
        marked = set()
        for cid, progress in self.world.read().companions.items():
            if cid not in c.characters or not any(roster.owns(n, p.name) for n in progress.parted_from):
                continue
            marked.add(cid)
            if cid in p.parted_done:  # 這一份角色已經減過：清記號
                self.world.update_companion(
                    cid, lambda pr: setattr(pr, "parted_from", [n for n in pr.parted_from if not roster.owns(n, p.name)]),
                )
                p.parted_done.remove(cid)
                continue
            p.parted_done.append(cid)
            before = p.affinities.get(cid, 0)
            after = math.floor(before * keep)
            p.affinities[cid] = after
            if after != before:
                lines.append(escorts.PARTED_LINE.format(name=c.characters[cid].name, before=before, after=after))
        p.parted_done = [cid for cid in p.parted_done if cid in marked]  # 記號已經不在的（換季清掉了）不留
        if write and lines:
            journal.add_entry(self.state, JournalEntry(time=self.state.world.time, title=escorts.PARTED_TITLE, tag="", lines=lines))
        return lines

    def _escort_line(self, e: battle_instance.Escort) -> str:
        """決戰畫面上自己的那一位（別人的不列，第五節「讀得下去」）。"""
        if e.fallen_round is not None:
            return ESCORT_FELL.format(name=e.name)
        return ESCORT_SCENE.format(name=e.name, hp=round(e.neili), cap=round(e.neili_cap))

    def _mandate_weight(self, definition: BattleDef | None, scores: dict[str, float]) -> dict[str, float]:
        """天命之爭：手上有碎片的人到場，份量 × Config.seal.mandate.holder_weight（玉璽碎片設計 8.3；只在這一場，碎片本身不加威力）。
        真人、假人、臨時投效的散人都走這裡（_battle_choose、_enlist、_backfill_battle_scores）。"""
        c = self.content
        if not seal.on(c) or not seal.is_mandate_battle(c, definition):
            return scores
        if seal.shard_of(self.world.seal_state().registry, self.state.player.name) is None:
            return scores
        w = c.config.seal.mandate.holder_weight
        return {move: round(value * w, 1) for move, value in scores.items()}

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
        battle, definition = status
        name = self.state.player.name
        me = battle.participants.get(name)
        if me is None or me.scores or me.eliminated:
            return
        scores, road, role = self._mandate_weight(definition, self._battle_scores()), self._battle_road(), self._battle_role()
        gear, bare = self._battle_gear(), self._seal_bare()

        def _fill(b: battle_instance.BattleInstance) -> None:
            mine = b.participants.get(name)
            if mine is not None and not mine.scores:  # 鎖裡再看一次：別的路徑剛補過就不蓋掉
                mine.scores = dict(scores)
                mine.seal_bare = mine.seal_bare or bare  # 玉璽碎片改版：份量一起補的，不含碎片的那一份也補
                mine.attribute = mine.attribute or road
                mine.role = mine.role or role
                mine.mount, mine.cavalry = mine.mount or gear["mount"], mine.cavalry or gear["cavalry"]
                mine.troops, mine.troop_bonus = mine.troops or gear["troops"], mine.troop_bonus or gear["troop_bonus"]

        self._mutate_battle_of(battle, _fill)

    def _battle_neili_cap(self) -> float:
        """決戰的氣血池上限：決戰的池子不吃螭首（玉璽碎片設計 7.1：決戰一個字都不改）。"""
        _, cap = team.member_neili(
            self.content, self.state.player.member, team.con_of(self.state, self.content, self.world, PLAYER), plain=True,
            season=self.state.world,
        )
        return cap

    # ── 好幾場戰鬥並存（領地爭奪第二批 Task 10）：時刻表決戰一場（world.get_battle）＋攻城戰一串（world.get_sieges）──
    # 沒有攻城戰時一切照舊（這一季沒開領地爭奪時 _sieges 不讀資料庫、回空的）。有的時候每個人看「自己的那一場」（_battle_now）：
    # 選單、場景、出招、放手一搏都照它；全服的推進（_battle_status 的 tick）每一場各推一次。

    def _sieges(self) -> list[battle_instance.BattleInstance]:
        """還沒收場的攻城戰（照開集結的先後）；這一季沒開領地爭奪是空的、不讀資料庫。"""
        if not conquest.on(self.content, self.state.world):
            return []
        return [b for b in self.world.get_sieges() if b.phase != "ended"]

    def battles_now(self) -> list[battle_instance.BattleInstance]:
        """全服此刻的每一場：決戰那一格（收場了照舊在，同 get_battle）在前，再照開集結的先後是還沒收場的攻城戰。"""
        showdown = self.world.get_battle()
        return ([showdown] if showdown is not None else []) + self._sieges()

    def battle_now(self) -> battle_instance.BattleInstance | None:
        """這個人看的那一場（_battle_now；假人程式與 bot_policy 讀它，取代 world.get_battle）。"""
        return self._battle_now()

    def _battle_now(self) -> battle_instance.BattleInstance | None:
        """這個人看的那一場：沒有攻城戰時就是決戰那一格（world.get_battle，一個字都不變）。有攻城戰時照這個順序：按鈕指定的那一場
        （_battle_ref：加入鈕帶 @流水號）＞自己是參戰者的那一場＞自己站得進去的那一場（_joinable 的第一場，FB-566：同一個大區兩場同時
        集結、排在前面的那一場自己站不進去時，以前回排第一的那一場，選單沒有加入鈕、場景寫「插不上手」）＞自己大區裡集結中或開打的
        （決戰在前）＞決戰那一格——別處的攻城戰不畫在別人的場景上（全服都看會很吵；決戰照舊全服看得到）。"""
        showdown = self.world.get_battle()
        sieges = self._sieges()
        if not sieges:
            return showdown
        live = ([showdown] if showdown is not None and showdown.phase != "ended" else []) + sieges
        if self._battle_ref is not None:
            return next((b for b in live if b.record_id == self._battle_ref), None)
        name = self.state.player.name
        mine = next((b for b in live if name in b.participants), None)
        if mine is not None:
            return mine
        joinable = self._joinable()  # FB-566：自己站得進去的那一場先
        if joinable:
            return joinable[0]
        here = self._in_region(live)
        return here[0] if here else showdown

    def _in_region(self, battles: list[battle_instance.BattleInstance]) -> list[battle_instance.BattleInstance]:
        """這幾場裡，人此刻所在（在路上看最後一站）的大區就是它的大區的；不限地點的那一場也算。"""
        loc = self.state.player.location
        found = atlas.region_of(self.content, loc) if loc in self.content.locations else None
        out = []
        for b in battles:
            d = self._definition_of(b)
            if d is not None and (d.region is None or (found is not None and found.id == d.region)):
                out.append(b)
        return out

    def _joinable(self) -> list[battle_instance.BattleInstance]:
        """自己大區裡集結中或開打、加得進去的那幾場（決戰在前）：自己已經在某一場的名單上、或沒有攻城戰時是空的。"""
        sieges = self._sieges()
        if not sieges:
            return []
        showdown = self.world.get_battle()
        live = ([showdown] if showdown is not None and showdown.phase != "ended" else []) + sieges
        name = self.state.player.name
        if any(name in b.participants for b in live):
            return []
        out = []
        for b in live:
            d = self._definition_of(b)
            if d is not None and self._at_battle(d) and not self._watching_battle(b, d):
                out.append(b)
        return out

    def _definition_of(self, battle: battle_instance.BattleInstance) -> BattleDef | None:
        """這一場的定義：決戰照內容；攻城戰是那個大區的範本，名字換成「攻城・地點」（siege.title）。"""
        definition = self.content.battles.get(battle.battle_id)
        if definition is None or battle.siege is None:
            return definition
        return definition.model_copy(update={"name": siege.title(self.content, battle.siege)})

    def _mutate_battle_of(self, battle: battle_instance.BattleInstance, fn) -> battle_instance.BattleInstance | None:
        """改這一場（照它是決戰還是攻城走 store 的那一個；同 mutate_battle：fn 在交易裡改、回改完的那一場）。"""
        if battle.siege is not None and battle.record_id is not None:
            return self.world.mutate_siege(battle.record_id, fn)
        return self.world.mutate_battle(fn)

    def _mutate_battle_now(self, fn) -> battle_instance.BattleInstance | None:
        """改這個人看的那一場（_battle_now）；沒有就不動、回 None。"""
        battle = self._battle_now()
        return None if battle is None else self._mutate_battle_of(battle, fn)

    def _tick_siege(self, battle: battle_instance.BattleInstance) -> None:
        """推一場攻城（同決戰的 _run_battle_tick：集結截止、回合逾時、補位、結算），剛收場就套結果（_apply_battle_outcome）。"""
        definition = self._definition_of(battle)
        if definition is None:
            return
        after = self.world.mutate_siege(battle.record_id, lambda b: self._advance_battle_round(b, definition))
        if after is not None and after.phase == "ended":
            self._apply_battle_outcome(after)

    def _shelve_siege(self, battle: battle_instance.BattleInstance, text: str = "") -> None:
        """季終（或管理者取消）時還沒打完的攻城收起來：同 _shelve_unfinished_battle（不算勝負、不發軍餉、不易手），參戰者補一則交代。"""
        end_time = self.state.world.time

        def _mark(b: battle_instance.BattleInstance) -> None:
            b.phase, b.unfinished, b.unfinished_text = "ended", True, text
            b.outcome_title, b.end_time = battle_instance.UNFINISHED_TITLE, end_time
            if b.siege is not None:
                b.siege.settled = True

        self.world.mutate_siege(battle.record_id, _mark)
        self.world.drop_siege(battle.record_id)
        self._deliver_battle_results()

    def _cancel_siege(self, record_id: int, text: str) -> None:
        """管理者取消一場已經開了集結的攻城（admin_conquest_cancel）：照季終收兵收起來，參戰者那一則寫 text。"""
        battle = next((b for b in self._sieges() if b.record_id == record_id), None)
        if battle is not None:
            self._shelve_siege(battle, text)
            self.state.world = self.world.get_season()

    def _battle_status(self, tick: bool = True) -> tuple[battle_instance.BattleInstance, BattleDef] | None:
        """目前這場全服戰鬥的最新狀態（有攻城戰時是這個人看的那一場，_battle_now）。沒有攻城戰時照舊（_showdown_status）。
        有攻城戰時：季收了，決戰與每一場攻城都收兵；tick 時決戰與每一場攻城各推一次（同一次請求裡一場只推一次，見 _showdown_status
        的說明），再回這個人看的那一場（收場了是 None）。"""
        sieges = self._sieges()
        if not sieges:
            return self._showdown_status(tick)
        if self.state.world.ended:
            if tick:
                showdown = self.world.get_battle()
                if showdown is not None and showdown.phase != "ended":
                    self._shelve_unfinished_battle()
                for b in sieges:
                    self._shelve_siege(b)
            return None
        if tick and self.world.paused_at() is None:
            self._showdown_status(tick=True)
            for b in sieges:
                self._tick_siege(b)
        focus = self._battle_now()
        if focus is None or focus.phase == "ended":
            return None
        definition = self._definition_of(focus)
        return None if definition is None else (focus, definition)

    def _showdown_status(self, tick: bool = True) -> tuple[battle_instance.BattleInstance, BattleDef] | None:
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

    def _battle_for_me(self, tick: bool = True) -> tuple[battle_instance.BattleInstance, BattleDef] | None:
        """這個人的選單、場景、放手一搏、決戰的動作看的那一場：同 _battle_status（tick 照樣把戰鬥追到現在），只是序章裡一律當作
        沒有（FB-113）——草廬與序章開場都在潁川汝南，以前長社火攻集結時新人第一個畫面就是兩顆投效，按了之後序章被戰場蓋掉、
        又走不開。不給投效與加入、不畫戰場；修好之前就上了名單的人也一樣（只是被代選固守，收場不領軍餉，見 _showdown_pay）。"""
        status = self._battle_status(tick=tick)
        return None if prologue_rules.active(self.state, self.content) else status

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
            battle_instance.close_muster(battle, definition, self.rng, now, tuning=tuning)
            if siege.void_absent(self.content, battle):  # 攻城戰（領地爭奪第二批）：攻方一個人都沒到，這一場作罷
                battle.end_time = self.state.world.time
                return [battle.unfinished_text]
            siege.lone_army(self.content, battle, definition)  # 三方混戰只有一軍到場（裁決 23）：轉回單方攻中立地
            siege.size_melee_guard(self.content, battle)  # 三方混戰（裁決 22）：守將的池子照兩軍到場的人數定
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
        timed_out = now - battle.round.opened_real >= definition.round_seconds
        if timed_out and not battle_instance.round_is_complete(battle):
            battle_instance.fill_timed_out_actions(battle, definition, tuning=tuning)
        if not battle_instance.round_is_complete(battle, timed_out=timed_out):  # 只剩掛機的人：逾時代選完就結算（FB-173）
            return []
        battle_instance.fill_idle_actions(battle, definition, tuning=tuning)  # 不等掛機的人：其他人送齊了，替他們代選
        msgs = battle_instance.resolve_round(battle, definition, self.rng, now=now, tuning=tuning, tactic=self.content.config.tactics)
        if battle.phase == "ended":
            battle.end_time = self.state.world.time
        # 每回合最前面那一行出招比例只留在回合紀錄（戰報）裡，場景上的比例只由「對面上一回合」那一段寫一次（審查 I1）。
        # 場景的記錄就是系統判定的那幾句（第一句是 resolve_round 寫的「誰佔了上風、為什麼」），不叫模型潤色：結算在行動鎖裡，
        # 以前每回合在鎖內等模型最多 in_lock_model_timeout 秒，全服所有人的動作都跟著等（試玩回饋 2026-10-08）
        shown = battle_instance.without_mix_line(battle, msgs)
        narration = "\n".join(shown)
        if narration:
            battle.narrative_log.append(narration)
        return shown or ["這一回合結算了。"]

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
        if battle.siege is not None:  # 攻城戰（領地爭奪第二批）：易手、作罷、時程表另外收（_settle_siege）
            self._settle_siege(battle)
            return
        if battle.unfinished:
            return
        if any(c.fallen_round is not None and not c.settled for c in battle.commanders):  # 龍頭上陣：敗走的人扣聲威（只扣一次）
            generals.after_battle(self.world, self.content, battle)
            self.state.world = self.world.get_season()  # 這一刻手上那一份跟資料庫一致（同 _settle_showdown），讀回來免得被 _save_season 蓋掉
        if escorts.due(battle):  # 歷史武將同行：隨主人上陣的同伴收場那一刻全服放回江湖（只放一次）
            escorts.after_battle(self.world, self.content, battle)
        definition = self.content.battles.get(battle.battle_id)
        line = self._highlight_line(battle, definition)
        if line:  # 這一場最有戲的放手一搏，全服的天下大事傳聞（試玩回饋 2026-10-08）；收場只走這裡一次
            self.world.mutate_season(lambda season: season.rumors.append(Rumor(time=season.time, text=line, layer="world")))
        line = self._merit_line(battle, definition)
        if line:  # 兩軍各一位首功（Joy 2026-10-10 個人戰功），天下大事傳聞具名
            self.world.mutate_season(lambda season: season.rumors.append(Rumor(time=season.time, text=line, layer="world")))
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

    def _settle_siege(self, battle: battle_instance.BattleInstance) -> None:
        """攻城戰剛收場（_apply_battle_outcome 分進來；只做一次，SiegeInfo.settled）：龍頭上陣的留守敗走扣聲威（守將是隊伍，不扣）；
        最有戲的一搏與兩軍首功照決戰上天下大事；易手（conquest.flip：分紅、冷卻、「落入／收復」）、守住各一句天下大事（作罷不發，攻方沒人到記
        day_log，裁決 19）、打輸攻方的條砍半、時程表記 done 或 void
        （siege.settle）；戰鬥那一列寫上結果（贏的一方、大勝或險勝、「某某大勝，拿下某地」）；參戰者照決戰補戰報與軍餉（軍餉、貢獻乘
        Config.conquest.pay_share，_showdown_pay）。隨行同伴不放回江湖（裁決 14）。收場的那一場留在共用狀態裡到每天結算才拿掉
        （最後一回合的放手一搏劇情收場之後才寫好）。"""
        if battle.siege is None or battle.siege.settled:
            return
        c = self.content
        definition = self._definition_of(battle)
        if definition is None:
            return
        if not battle.unfinished:
            if any(x.fallen_round is not None and not x.settled and x.fid in c.figures for x in battle.commanders):
                generals.after_battle(self.world, c, battle, where=definition.name,
                                      mutate=lambda fn: self.world.mutate_siege(battle.record_id, fn))
            for line in (self._highlight_line(battle, definition), self._merit_line(battle, definition)):
                if line:
                    self.world.mutate_season(lambda season, line=line: season.rumors.append(Rumor(time=season.time, text=line, layer="world")))
        result: dict = {}
        guards = self._siege_guards(battle, definition)

        def _season(season: WorldState) -> None:
            if guards:  # FB-605：守方守住，替每一個守方的人記一次守城——那一塊還凍結著（siege.settle 之前），守城的清單照樣列它
                vehicle, line = _season_vehicle(c, season), conquest.line_of(season, c, battle.siege.loc)
                for name, side in guards:
                    orders.credit(vehicle, c, side, name, kind=orders.SIEGE_GUARD, location=battle.siege.loc, front=line)
            result.update(siege.settle(season, c, battle, definition))

        self.world.mutate_season(_season)

        def _relabel(b: battle_instance.BattleInstance) -> None:
            b.siege.settled = True
            if not b.unfinished:
                b.outcome_title = result["title"]
                b.outcome_side, b.outcome_margin = result["winner"], result["margin"]
                b.outcome_text = b.outcome_text or ""

        after = self.world.mutate_siege(battle.record_id, _relabel)
        battle.siege.settled = True
        self.state.world = self.world.get_season()
        if after is not None:
            battle.outcome_title, battle.outcome_side, battle.outcome_margin = after.outcome_title, after.outcome_side, after.outcome_margin
        self._deliver_battle_results()

    def _siege_guards(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> list[tuple[str, str]]:
        """攻城戰守方守住時，替守城軍令記一次的人（FB-605，PM 2026-10-21）：[(名號, 他自己那一邊)]。打的是陣營佔著的那一塊、照常打完
        （不是作罷、季終收兵）、沒被拿下；站守方那一格、而且自己那一邊（allied.side_of：豪強依附的那一軍）就是守方的人——臨時投效、助守的
        散人與別的陣營不算（只算這一場，不記貢獻）。讀別人的存檔只為了看他是哪一邊。"""
        info_ = battle.siege
        if info_ is None or battle.unfinished or info_.void or info_.holder not in conquest.SIDES:
            return []
        if siege.verdict(info_, battle, definition)[0] is not None:
            return []
        out: list[tuple[str, str]] = []
        for name, p in battle.participants.items():
            if p.faction != info_.holder:
                continue
            kin = self if name_key(name) == name_key(self.state.player.name) else self._load_kin(name)
            if kin is not None and allied.side_of(kin.state, self.content) == info_.holder:
                out.append((name, info_.holder))
        return out

    def _merit_line(self, battle: battle_instance.BattleInstance, definition: BattleDef | None) -> str:
        """收場時的論功那一則：兩軍各自戰功最高的人（battle_instance.top_merit；臨時投效的人算在投效的那一軍）；
        都沒人出過手就不寫。單方攻中立地時守將那一格寫守軍（battle_instance.side_names，FB-540）。"""
        if definition is None:
            return ""
        tuning = self.content.config.battle
        heads = [
            (side, top) for fid, side in battle_instance.side_names(battle, definition).items()
            if (top := battle_instance.top_merit(battle, tuning, fid)) is not None
        ]
        if not heads:
            return ""
        return f"{definition.name}論功：" + "，".join(
            f"{side}首功{p.name}" + (f"（{'・'.join(p.renown)}）" if p.renown else "") for side, p in heads) + "。"  # 名聲 4.5

    @staticmethod
    def _highlight_line(battle: battle_instance.BattleInstance, definition: BattleDef | None) -> str:
        """收場時那一則傳聞：這一場最有戲的放手一搏（battle.highlight）。天下大事傳聞照慣例具名（假人不寫放手一搏，不會出現）。"""
        h = battle.highlight
        if h is None:
            return ""
        where = definition.name if definition is not None else battle.battle_id
        head = f"{where}上，{h.name}放手一搏：「{h.text}」"
        if h.won:
            return f"{head}——成算不到{h.rate // 10 + 1}成，竟然成了。{h.story}".rstrip()
        return f"{head}——沒成，倒成了兩軍口中的笑談。{h.story}".rstrip()

    def _settle_showdown(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> None:
        """時刻表決戰收場（計畫 T8）：照 battle_instance.decide_result 判誰贏、大勝或險勝——這一刻才讀
        WorldState.locks（鎖定只在這裡看，起點、推力、選項都不看，戰鬥系統 4.3）——再交給 timetable.resolve 結算那一格
        （它自己加宛城的版本前綴，公告、江湖史、戰況、人物都照時刻表）。保底的 BattleOutcome 不套、不寫江湖史。

        戰鬥那一列的結果改成時刻表那一格（標題「官軍大勝」、文字是公告、大勢變化是那一格的戰況），參戰者的戰報照
        W13／FB-027 補送時就寫這個；公告進每個人的江湖紀錄走 _deliver_big_events（FB-038）。

        resolve 改的是資料庫裡的那一份賽季（mutate_season），手上的 self.state.world 跟著讀回來：結算發生在 options() 的
        推進裡，接下來 choose() 收尾的 _save_season 會把手上那一份整份寫回去，不讀回來就把結果蓋掉了。這一刻手上那一份
        跟資料庫一致（每個動作開頭的 sync 剛讀過、推進戰鬥之前還沒改它），讀回來不會丟東西。"""
        event = timetable.find(self.content, definition.timetable_event) if definition.timetable_event else None  # 天命之爭也找得到（玉璽二）
        result: dict[str, object] = {}
        unsettled = seal.is_mandate_battle(self.content, definition) and seal.deserted(battle, definition)  # 天命未定（玉璽二）

        def _resolve(season: WorldState) -> None:
            lock = season.locks.get(definition.timetable_event)
            winner, margin = battle_instance.decide_result(
                battle, definition, lock.side if lock is not None else None, definition.defender or definition.factions[0].id,
            )
            result["title"] = f"{timetable.SIDE_NAMES.get(winner, winner)}{margin}"
            result["side"], result["margin"] = winner, margin
            result["reason"] = battle_instance.overruled_reason(
                battle, definition, lock.side if lock is not None else None, definition.defender or definition.factions[0].id,
            )
            if event is None:
                return
            if unsettled:  # 天命之爭保底收場：天命未定（8.3；要 PM 定的第 4 條），時間軸記成跳過，不公告哪一軍勝、沒有勝方加給
                season.timeline[event.id] = TimelineResult(key=timetable.SKIPPED, time=season.time)
                result.update(title=seal.MANDATE_UNSETTLED_TITLE, side="", margin="", reason="", text="", trends={})
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
            b.outcome_side, b.outcome_margin = str(result.get("side") or ""), str(result.get("margin") or "")
            if result.get("reason"):  # 伏筆鎖定的一方贏了、戰場上卻是另一方佔上風：敗因不能寫成戰場那一邊贏
                b.outcome_reason = str(result["reason"])
            b.outcome_text = str(result.get("text") or b.outcome_text or "")
            b.outcome_trend_delta = dict(result.get("trends") or {})  # 只給戰報顯示：已經由 resolve 套過了
            b.outcome_world_flags = []

        self.world.mutate_battle(_relabel)
        self._seal_settle(battle, definition, result)  # 玉璽碎片：先挑挑戰者、再挑現世的得主（3.3、4.5）；只寫登記、天下大事、江湖史，接著讀回的賽季看得到
        self.state.world = self.world.get_season()
        self._deliver_big_events()
        self._deliver_battle_results()
        self._deliver_seal_results()

    def _deliver_seal_results(self) -> None:
        """玉璽碎片的事補送到自己手上（玉璽碎片設計 5.9、3.3）：全服登記流水號 > PlayerState.seal_seen、跟自己有關的每一筆——
        現世拿到（紀錄；同一季才學 emerge_skill）、單挑收場（戰報 kind seal＋紀錄；同一季才給名望）、沒打完、隱沒、管理者指定。
        收場那一下不改任何人的存檔（這一季沒上線過的持有者一同步就整個換成新角色，寫進去的會不見，FB-027），每個人自己同步時補；
        跨季才回來也補得到戰報與紀錄。補完照登記重抄抄本。"""
        c = self.content
        if not c.seal:
            return
        p = self.state.player
        reg = self.world.seal_state().registry
        fresh = [e for e in reg.history if e.seq > p.seal_seen]
        if not fresh:
            return
        p.seal_seen = max(e.seq for e in fresh)
        current, me = self.world.get_season_number(), seal.key(p.name)
        for e in fresh:
            if e.kind == "mandate":  # 天命之爭定下來（8.3）：那一刻手上有碎片的人以合璽之人留名；天命未定不寫
                mine = next((sid for sid, name in e.holders.items() if seal.key(name) == me and sid in c.seal), None)
                if mine is not None and e.result:
                    line = seal.MANDATE_MINE.format(shard=c.seal[mine].name)
                    self._write(seal.SEAL_TITLE, [line] + ([e.text] if e.text else []), tag=f"『{c.seal[mine].name}』")
                    if e.season == current:
                        annals.note(self.state, c, annals.DEED, line, 5, place=e.where)
                continue
            if me not in (seal.key(e.holder), seal.key(e.other)) or e.shard not in c.seal:
                continue
            shard = c.seal[e.shard].name
            same = e.season == current
            if e.kind == "emerge":
                lines = [seal.GOT.format(shard=shard, effect=seal.shard_text(c, e.shard))]
                skill = c.config.seal.emerge_skill
                if same and skill and skill in c.skills and skill not in library.owned_arts(self.state) and not library.full(self.state, c):
                    lines += learn_skill(self.state, c, skill)  # 混元一氣改給現世的得主（11.2 第 4 條）
                if same:
                    annals.note(self.state, c, annals.DEED, e.text or lines[0], 5, place="")
                self._write(seal.SEAL_TITLE, lines, tag=f"『{shard}』")
            elif e.kind in ("take", "keep"):
                self._file_seal(e, shard, same)
            elif e.kind == "unsettled":
                other = e.other if seal.key(e.holder) == me else e.holder
                self._write(seal.SEAL_TITLE, [seal.UNSETTLED_MINE.format(other=other, shard=shard)], tag=f"『{shard}』")
            elif e.kind == "sink" and seal.key(e.other) == me:
                self._write(seal.SEAL_TITLE, [seal.SUNK_MINE.format(shard=shard)], tag=f"『{shard}』")
            elif e.kind == "recall" and seal.key(e.holder) == me:  # 喚回（8.2）：只拿碎片，不學 emerge_skill（要 PM 定的第 5 條）
                line = seal.RECALLED_MINE.format(where=e.where or "", shard=shard, effect=seal.shard_text(c, e.shard))
                self._write(seal.SEAL_TITLE, [line], tag=f"『{shard}』")
            elif e.kind == "scatter" and seal.key(e.other) == me:  # 天命之季之後七片散去（8.4）：抄本在最後的 _copy_heirloom 照登記清掉
                self._write(seal.SEAL_TITLE, [seal.SCATTER_MINE.format(shard=shard)], tag=f"『{shard}』")
            elif e.kind == "assign" and seal.key(e.holder) == me:  # 管理者指定給你（公告不寫管理者，紀錄寫成拿到）
                self._write(seal.SEAL_TITLE, [seal.GOT.format(shard=shard, effect=seal.shard_text(c, e.shard))], tag=f"『{shard}』")
        self._copy_heirloom()

    def _file_seal(self, e, shard: str, same: bool) -> None:
        """一場奪璽單挑寫成自己的戰報（kind seal，回合一行一行；持有者的那份照挑戰者的翻過來寫）與一則紀錄；名望只在同一季才給（5.9）。"""
        c, s, cfg = self.content, self.state, self.content.config.seal
        challenger = e.holder if e.kind == "take" else e.other  # take：holder 是挑戰者、other 是失主；keep：holder 是持有者、other 是挑戰者
        mine = "challenger" if seal.key(challenger) == seal.key(s.player.name) else "holder"
        if mine == "challenger":
            other = e.other if e.kind == "take" else e.holder  # 挑戰者看的是持有者
        else:
            other = challenger  # 持有者看的是挑戰者
        won = e.result in seal_duel.WIN_VERDICTS
        if e.kind == "take":
            head, fame = (seal.WON, 0) if mine == "challenger" else (seal.LOST, cfg.fame["lose"])
        elif mine == "holder":
            head, fame = seal.KEPT, cfg.fame["keep"]
        else:
            head, fame = (seal.MISSED, cfg.fame["near"]) if won else (seal.FAILED, 0)
        notes = [head.format(other=other, shard=shard)] + ([e.text] if e.text else [])
        if mine in e.absent:  # 整場一手都沒自己出（FB-174）
            notes.append(seal.PROXY_LINE)
        elif mine in e.proxied:  # 自己出過手、只有幾回合逾時被代出；舊資料沒有 absent 也走這一句（比較溫和、一定是真的）
            notes.append(seal.PROXY_SOME_LINE)
        notes += [seal.FRESH_LINE] if mine == "holder" and e.fresh else []
        changes = []
        if same and fame:
            changes += renown.gain(s, c, "fame", fame)  # 加名望一律走 renown.gain（名聲設計 3.2）
        label = "" if same else f"第 {e.season} 季・"
        when = e.at if same and e.at is not None else s.world.time  # 單挑收場那一刻（FB-175）；跨季才回來照補送那一刻
        record = BattleRecord(
            id=s.battle_seq + 1, time=when, location=f"{label}{e.where or '陣前'}", kind="seal", event=f"『{shard}』",
            opponent=other, ours=[], tier=seal_duel.side_tier(e.result, e.edge, mine, c.config.duel), our_power=0.0, difficulty=0.0,
            notes=notes, changes=list(changes),
            rounds=list(e.lines),
        )
        battlelog.add_record(s, record)
        s.battle_card = record.id
        journal.add_entry(s, JournalEntry(time=when, title=f"{label}奪璽・『{shard}』", tag=notes[0], lines=notes[1:],
                                          changes=changes, battle_id=record.id))
        if same:
            annals.note(s, c, annals.DEED, notes[0], 5 if e.kind == "take" else 4, place=e.where, keep=[other])

    def _mandate_settle(self, winner: str, record: int | None, battle_name: str) -> None:
        """天命之爭定下來（8.3）：winner 是得天命的那一軍，"" 是天命未定（保底收場）。一次 world.mutate：這一季記下 mandate_result（季末
        的結局看它）、登記記一筆 mandate（這一刻每一片在誰手上＝合璽之人）、天下大事與江湖史各一句。不是天命之季、或已經定過，什麼都不做。
        _seal_settle 與管理者「定結果」叫它；可能跑在 Game.for_world，不碰 self.state.player。"""
        c = self.content
        if not seal.on(c):  # 主機中途關掉碎片：天命不定（季末照 world.end_season 寫天命未定），管理者「定結果」也一樣
            return
        names = {f.id: f.name for f in c.scenario.factions}

        def _apply(shared) -> None:
            season = shared.season
            if not season.mandate or season.mandate_result is not None:
                return
            reg = seal.filled(shared.seal, c)
            holders = {s.id: s.holder for s in reg.shards.values() if s.state == "held" and s.holder and s.id in c.seal}
            season.mandate_result = winner
            if winner:
                text = seal.MANDATE_WON.format(side=names.get(winner, winner))
                if holders:
                    text += seal.MANDATE_NAMES.format(names="、".join(holders[s] for s in c.seal if s in holders))
            else:
                text = seal.MANDATE_UNSETTLED.format(battle=battle_name)
            seal.log(reg, shared.season_number, "mandate", result=winner, holders=holders, record=record, where=battle_name, text=text)
            seal.rumor(season, text)
            seal.chronicle(season, text)

        self.world.mutate(_apply)

    def _seal_settle(self, battle: battle_instance.BattleInstance, definition: BattleDef, result: dict) -> None:
        """時刻表決戰收場時的玉璽碎片（_settle_showdown 呼叫；result 是算進伏筆鎖定的官方結果，不讀 battle.outcome_side，3.3）：
        璽動那一場決定要不要開奪璽單挑（Task 8），再從勝方挑現世的得主；後挑的排除前面挑中的人。
        只寫全服登記、單挑、天下大事、江湖史（一次 world.mutate），戰報那一行寫進這一場（mutate_battle 的 seal_notes）；
        兩人的存檔等各自同步時補（_deliver_seal_results，5.9）。可能跑在 Game.for_world（玩家是空白的），不碰 self.state.player。
        天命之季標了 seal 的前兩場另外喚回一片（8.2）；天命之爭只定天命（_mandate_settle）。亂數全是 seal.dice，不碰 self.rng。"""
        c = self.content
        if not seal.on(c):
            return
        if seal.is_mandate_battle(c, definition):  # 天命之爭（8.3）：不璽動、不現世、不喚回、不掛單挑，只定天命
            winner = "" if seal.deserted(battle, definition) else str(result.get("side") or "")
            self._mandate_settle(winner, battle.record_id, definition.name)
            return
        cfg = c.config.seal
        view = self.world.seal_state()
        reg = seal.filled(view.registry, c)
        winner, margin = str(result.get("side") or ""), str(result.get("margin") or "")
        need = seal.threshold(battle, cfg)
        held = seal.holders(reg)
        picked: set[str] = set()
        notes: list[str] = []
        # 保底收場（end_without_fighters：兩軍都沒人還能打）：不打單挑、現世落空（設計 4.5 邊界 3、3.3）；小伺服器的旁觀散人也不補
        deserted = seal.deserted(battle, definition)
        duel = None
        shard_now = reg.shards.get(battle.seal_shard or "")
        if (not deserted and shard_now is not None and battle.seal_holder
                and seal.key(shard_now.holder) == seal.key(battle.seal_holder)):
            duel = self._seal_challenge(battle, definition, reg, view.tianji, winner, margin, need, held)
            if duel is not None:
                picked.add(seal.key(duel.challenger.name))
                notes.append(seal.DUEL_NOTE.format(challenger=duel.challenger.name, holder=duel.holder.name))
        found = None
        emerge = reg.shards.get(battle.seal_emerge or "")
        if emerge is not None and emerge.state == "hidden" and not deserted:
            rows = seal.emerge_rows(battle, c, winner, need, held, picked)
            found = seal.weighted_pick(rows, seal.dice(reg.salt, view.tianji, "seal-emerge", battle.record_id), cfg.challenger_pool)
        recalled = None  # 喚回（8.2；PM 辛）：天命之季、標了 seal 的前兩場；排在挑戰者之後、排除剛挑去單挑的人；不算現世
        if seal.mandate_now(reg, view.season) and not deserted and definition.timetable_event in seal.recall_events(c):
            rows = seal.emerge_rows(battle, c, winner, need, held, picked)
            recalled = seal.roll_recall(reg, view.tianji, definition.timetable_event, rows, cfg.challenger_pool)
        shard_name = c.seal[battle.seal_emerge].name if battle.seal_emerge in c.seal else ""
        emerged = {"ok": False}

        def _apply(shared) -> None:
            reg_ = seal.filled(shared.seal, c)
            reg_.last_showdown, reg_.last_showdown_dueled, reg_.last_showdown_where = battle.record_id, False, definition.name
            if battle.seal_shard is not None and battle.seal_shard in c.seal:
                shard_label = c.seal[battle.seal_shard].name
                if duel is not None:
                    shared.seal_duels.append(duel)
                    reg_.last_showdown_dueled = True
                    call = seal_duel.CALL if duel.challenger.name in battle.participants else seal_duel.CALL_QA  # 旁觀散人沒有「戰功居前」
                    seal.rumor(shared.season, call.format(challenger=duel.challenger.name, holder=duel.holder.name, shard=shard_label))
                elif battle.seal_holder:
                    seal.rumor(shared.season, seal.no_duel_text(c, battle.seal_holder, shard_label))  # 改版：不點名
            if battle.seal_emerge is None:
                return
            shard = reg_.shards[battle.seal_emerge]
            if found is None or shard.state != "hidden" or seal.key(found) in seal.holders(reg_):  # 落空：照舊未現世，只寫天下大事
                seal.rumor(shared.season, seal.EMERGE_LOST.format(battle=definition.name))
                return
            season = shared.season_number
            shard.state, shard.holder, shard.since_season, shard.emerged_round = "held", found, season, reg_.round
            reg_.emerge_season = season
            text = seal.EMERGE_GOT.format(name=found, battle=definition.name, shard=shard_name)
            seal.log(reg_, season, "emerge", shard=shard.id, holder=found, record=battle.record_id, text=text)
            seal.rumor(shared.season, text)
            seal.chronicle(shared.season, text)
            emerged["ok"] = True

        self.world.mutate(_apply)
        if recalled is not None:
            shard_id, name = recalled

            def _recall(shared) -> None:
                reg_ = seal.filled(shared.seal, c)
                shard = reg_.shards[shard_id]
                if shard.state != "sunk" or seal.key(name) in seal.holders(reg_):  # 寫入時重驗：這一刻已經不是隱沒、或他已經有一片
                    return
                shard.state, shard.holder, shard.since_season, shard.absent = "held", name, shared.season_number, 0  # emerged_round 不動
                text = seal.RECALL.format(name=name, battle=definition.name, shard=c.seal[shard_id].name)
                seal.log(reg_, shared.season_number, "recall", shard=shard_id, holder=name, record=battle.record_id, where=definition.name,
                         text=text)
                seal.rumor(shared.season, text)
                seal.chronicle(shared.season, text)

            self.world.mutate(_recall)
        if emerged["ok"]:  # 寫入時重驗沒過（落空）就不寫戰報那一行
            notes.append(seal.EMERGE_NOTE.format(name=found))
        if notes:
            self.world.mutate_battle(lambda b: b.seal_notes.extend(notes) if b.record_id == battle.record_id else None)

    def _seal_challenge(
        self, battle, definition: BattleDef, reg, tianji: int, winner: str, margin: str, need: int, held: set[str],
    ) -> SealDuel | None:
        """璽動那一場收場：持有者那一方打得怎樣（照璽動那一刻的快照，4.5）；不是大勝就挑挑戰者（4.6）、照 5.3 抓雙方的快照、開一場
        下戰書的單挑（還沒寫進去，呼叫端的 world.mutate 寫）。挑不出人回 None（懷璽不失、算動過）。"""
        cfg = self.content.config.seal
        holder = battle.seal_holder
        snap = battle.seal_holder_side
        moved = snap is not None and self.world.faction_of(holder) != battle.seal_holder_faction  # 璽動之後陣營變了：算旁觀、不套過濾
        side = None if moved else snap
        tier = seal.tier_for(side, winner, margin)
        if tier == "大勝" or not winner:
            return None
        armies = [f.id for f in definition.factions]
        foe = winner if side is None else next((f for f in armies if f != side), winner)
        blocked = None if side is None else battle.seal_holder_faction  # 只在快照陣營沒變時擋「自己人合演轉手」
        rows = self._seal_challengers(battle, foe, need, holder, blocked, held)
        if len(battle.participants) < cfg.small_battle:
            rows += self._seal_spectators(definition, battle, held)
        shard = reg.shards[battle.seal_shard]
        name = seal.weighted_pick([(n, m) for n, m, _ in rows], seal.dice(reg.salt, tianji, "seal-duel", battle.record_id),
                                  cfg.challenger_pool, prefer=shard.former)
        if name is None:
            return None
        challenger = next(s for n, _, s in rows if n == name)
        me = battle.participants.get(holder)
        guarded = me is not None and me.acted_rounds >= need  # 護璽：自己出手滿門檻（臨時投效的散人也算，只多這一條，4.5）
        keeper = seal_duel.side_from_participant(me, battle.seal_holder_faction) if me is not None else self._seal_side_of(holder)
        cap = min(cfg.cap, cfg.cap * cfg.side_factor.get(tier, 0.0) * (cfg.guard if guarded else 1.0))
        return seal_duel.open_duel(
            f"{battle.record_id}:{shard.id}", shard.id, battle.record_id, definition.timetable_event, definition.name, tier, cap,
            challenger, keeper, self.now, cfg,
        )

    def _seal_challengers(self, battle, side: str, need: int, holder: str, blocked: str | None, held: set[str]) -> list:
        """挑戰者的候選（4.6）：那一邊（交戰兩軍之一）的參戰者、自己出手滿 need 回合、不是持有者、手上沒有碎片、這一季沒叛投過與
        不在新手期（加入時的快照）、此刻名冊上的陣營不跟持有者的快照陣營相同（blocked；None 不擋）。回（名號, 戰功, 快照）；不看假人。"""
        tuning = self.content.config.battle
        out = []
        for p in battle.participants.values():
            if p.faction != side or not seal.challenger_ok(p, need, held, holder):  # 同畫面那一句（hint_names，FB-177）
                continue
            now_faction = self.world.faction_of(p.name)
            if blocked is not None and now_faction == blocked:
                continue
            out.append((p.name, battle_instance.merit(tuning, p), seal_duel.side_from_participant(p, now_faction)))
        return out

    def _seal_spectators(self, definition: BattleDef, battle, held: set[str]) -> list:
        """小伺服器的退路（PM 癸；計畫「要 PM 定的」第 2 條）：收場那一刻人在決戰的大區、presence_seconds 內同步過、不在路上、名冊上
        不是交戰兩軍（散人、地方豪強：Joy 2026-10-13 起豪強在決戰跟散人一樣臨時投效）、不是參戰者也不是持有者、不在新手期與序章、這一季沒叛投過、手上沒有碎片的人。戰功當 0；身手照他的存檔算（不存回去）。"""
        if not hasattr(self.world, "db") or definition.region is None:
            return []
        store = CharacterStore(self.world.db)
        since = self.now - self.content.config.presence_seconds
        region = definition.region
        armies = {f.id for f in definition.factions}
        here = [loc for loc in self.content.locations if (r := atlas.region_of(self.content, loc)) is not None and r.id == region]
        out = []
        for loc in here:
            for state in store.present(loc, since):
                name = state.player.name
                if (name in battle.participants or seal.key(name) == seal.key(battle.seal_holder) or seal.key(name) in held
                        or state.player.journey is not None or state.player.defected or self.world.faction_of(name) in armies):
                    continue
                kin = self._kin(state)
                if roster.newbie(kin.state, self.content) or prologue_rules.active(kin.state, self.content):
                    continue
                out.append((name, 0, seal_duel.side_from(  # 不含玉璽碎片的戰力（改版：奪璽單挑不吃；手上有碎片的本來就擋掉了）
                    name, None, kin._battle_power(seal=False), kin._battle_scores(mounted=False, seal=False), kin._battle_role(),
                    kin._battle_neili_cap(), kit=team.self_side(kin.state, self.content, kin.world),
                )))
        return out

    def _seal_side_of(self, name: str) -> SealSide:
        """沒參戰的持有者的快照（5.3）：觸發結算的人就是他用 self；否則讀他的存檔建一份不叫模型的 Game（不 sync、不存回、不記 last_seen），
        讀不到（沒有資料庫）就照新角色。這一季沒上線過（seen_real，舊存檔退回 last_real，早於 opened_real；opened_real 是 None 一律當
        上線過）記成 fresh、身手照新角色。"""
        opened = self.world.seal_state().registry.opened_real
        game = self if seal.key(self.state.player.name) == seal.key(name) else (self._load_kin(name) or self._kin(new_game_state(self.content, name)))
        seen = game.state.player.seen_real if game.state.player.seen_real is not None else game.state.last_real
        fresh = opened is not None and (seen is None or seen < opened)
        if fresh and game is not self:
            game = self._kin(new_game_state(self.content, name))
        return seal_duel.side_from(  # 不含玉璽碎片的戰力（改版：奪璽單挑不吃，碎片才搶得走）
            name, self.world.faction_of(name), game._battle_power(seal=False), game._battle_scores(mounted=False, seal=False),
            game._battle_role(), game._battle_neili_cap(), fresh=fresh, kit=team.self_side(game.state, self.content, game.world),
        )

    def _my_seal_duel(self) -> tuple[SealDuel | None, str | None]:
        """排第一的那一場奪璽單挑，與自己是哪一邊（不在裡面是 None）。"""
        duels = self.world.seal_state().duels if seal.on(self.content) else []
        if not duels:
            return None, None
        return duels[0], seal_duel.side_of(duels[0], self.state.player.name)

    def _seal_tick(self) -> None:
        """把奪璽單挑推到現在（5.4）：options(tick=True) 與 world_tick 叫，一次最多結算一回合。自己的請求（own_request）而且自己是一方時
        順便記 last_seen（15 秒最多寫一次）。先讀一次 world 那一列，沒事做就不開 mutate（每 10 秒的輪詢不寫）。季、角色都不動；
        自己是一方就順便補給自己（_deliver_seal_results，Task 10）。"""
        if not seal.on(self.content):
            return
        view = self.world.seal_state()
        if not view.duels or view.paused:
            return
        duel = view.duels[0]
        me = self.state.player.name
        who = seal_duel.side_of(duel, me) if me else None
        cfg = self.content.config.seal
        if not seal_duel.needs_write(duel, who, self.now, cfg, own=self.own_request, ended=self.state.world.ended):
            return

        def _apply(shared) -> None:
            if self.own_request and who is not None and shared.seal_duels and shared.seal_duels[0].id == duel.id:
                seal_duel.note_seen(shared.seal_duels[0], who, self.now, cfg)
            seal_duel.advance(shared, self.content, self.now)

        self.world.mutate(_apply)
        self._deliver_seal_results()  # 自己是一方、剛好由自己收場時當場看得到（不是一方時什麼都不做）

    def _seal_options(self) -> list[Option]:
        """單挑的一方、這一場開打了：三招（寫剋哪一招）擺在選單最前面；送過了換成一顆灰的「已出招」；這一回合判成不在場的三招灰掉、
        寫中性的字（5.5，不寫代打）。放手一搏走輸入框（seal_free_text_prompt，Task 9），選單上沒有。"""
        duel, who = self._my_seal_duel()
        if duel is None or who is None or duel.phase != "active":
            return []
        cfg = self.content.config.seal
        problem = seal_duel.submit_problem(duel, who, cfg)
        if problem == seal_duel.SENT:
            left = max(0, int((duel.opened_real or self.now) + cfg.round_seconds - self.now))
            label = f"（{seal_duel.SENT}：已出招 {seal_duel.sent(duel)}／2，最遲 {left // 60} 分 {left % 60} 秒）"
            return [Option(id="seal:waiting", label=label, enabled=False)]
        late = f"（{problem}）" if problem else ""
        held = tactics.locks(duel.bout, seal_duel.BOUT_SIDE[who]).no_moves  # 本命戰法：卸勁、只攻不守
        return [Option(id=f"seal:{m}", label=duel_rules.move_label(m) + late + (tactics.lock_note(m) if m in held else ""),
                       enabled=problem is None and m not in held) for m in MOVES]

    def _seal_act(self, move: str) -> list[str]:
        """選單上的一招（seal:<招>）：在一次 world.mutate 裡重驗、記下這一手，然後推一步（湊齊了而且滿 20 秒才結算）。"""
        if move not in MOVES:
            return ["（此刻無法這麼做。）"]
        out: list[str] = []
        me, cfg = self.state.player.name, self.content.config.seal

        def _apply(shared) -> None:
            duel = shared.seal_duels[0] if shared.seal_duels else None
            who = seal_duel.side_of(duel, me) if duel is not None else None
            problem = seal_duel.GONE if who is None else seal_duel.submit_problem(duel, who, cfg)
            if not problem and move in tactics.locks(duel.bout, seal_duel.BOUT_SIDE[who]).no_moves:
                problem = tactics.NO_MOVE.strip("（）").format(move=move)
            if problem:
                out.append(f"（{problem}）")
                return
            seal_duel.submit(duel, who, move=move)
            seal_duel.note_seen(duel, who, self.now, cfg)
            out.append(f"你出了{move}。")
            out.extend(seal_duel.advance(shared, self.content, self.now))

        self.world.mutate(_apply)
        self._deliver_seal_results()
        return out

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
        territory.update(season, self.content)  # 決戰結果直接寫進季、不經 change_trend：地盤在這裡重算
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
        for _, _, r in fresh:
            if r.locked_by == p.name:  # 行狀：你暗中鎖定的伏筆左右了這件大事（揭曉這一刻才記，鎖定的當下不能露出來）
                annals.note(self.state, c, annals.DEED, f"你暗中布下的伏筆左右了這件大事：{r.text}", 5, place="", time=r.time)
        last = fresh[-1][2]
        if len(fresh) == 1:
            entry = JournalEntry(time=last.time, title=journal.WORLD_NEWS, tag=last.text)
        else:
            lines = [f"{self.stamp(r.time)}　{r.text}" for _, _, r in fresh]
            entry = JournalEntry(time=last.time, title=journal.WORLD_NEWS, tag=f"共 {len(fresh)} 件", lines=lines)
        journal.add_entry(self.state, entry)

    def _deliver_echoes(self) -> None:
        """首創名望回饋（Config.first_echo）：這一季別人照著你首創的武學或意境合了出來（兵器配方打了出來）（fusion.echo 記在 WorldState.echoes），
        你同步時補名望——每多一個人 +fame_per，補到第幾個人記在 Echo.paid，所以一個人只算一次。好幾門一起補就合成一則紀錄。
        做法同 _deliver_renames：合的那一下不動別人的角色，每個人自己的 Game 同步時自己補。第一季沒開著時 echoes 是空的。"""
        p = self.state.player
        rule = self.content.config.first_echo
        lines, gained = [], 0
        for entry in self.state.world.echoes.values():
            co = entry.co_creator == p.name  # 論武合出來的：另一個首創者照自己的帳補（co_paid）
            due = len(entry.followers) - (entry.co_paid if co else entry.paid)
            if p.name not in (entry.creator, entry.co_creator) or due <= 0:
                continue
            if co:
                entry.co_paid = len(entry.followers)
            else:
                entry.paid = len(entry.followers)
            gained += due * rule.fame_per
            lines.append(f"江湖上又有 {due} 人照著你首創的{entry.name}{entry.made}了出來。")
        if not lines:
            return
        self._write(journal.ECHO, lines + renown.gain(self.state, self.content, "fame", gained))  # 名聲設計 3.2
        self._save_season()  # 補到第幾個人記在共用賽季裡

    def _deliver_held_gear(self) -> None:
        """寄放的東西補發（裝備四欄 6.5）：懸賞的重賞、名將贈禮在裝備庫滿了時寄放在 PlayerState.held_gear；同步與快轉時那一欄開著、
        身上空著或裝備庫有空位就補，一次補到裝備庫滿為止，補不完的留著（treasures.deliver_held）。閉關中也補（寶物閉關中本來就能換，
        2.3【定】）。整季機器人只 advance、不 sync，所以 advance 也叫，不然整季模擬裡寄放的東西永遠補不回來。補了就寫一則江湖紀錄。"""
        lines = treasures.deliver_held(self.state, self.content)
        if lines:
            self._write(treasures.HELD_TITLE, lines)

    def _general_gifts(self) -> list[str]:
        """名將贈禮（裝備四欄 6.4）：情誼到 gift_affinity 的人物把贈禮交給你，每位名將每季全服只送一人（treasures.gifts_due 記進
        WorldState.general_gifts，這一下動作最後的 _save_season 存回去）。choose 與 answer_event 最後各叫一次：情誼從對話（companion_agent）、
        事件（Effect.affinity）、隨口應對來都走得到，不必在兩條路各寫一份。"""
        given = dict(self.state.world.general_gifts)
        msgs = treasures.gifts_due(self.state, self.content, self._people_here())
        for cid, who in self.state.world.general_gifts.items():
            if cid not in given and who == self.state.player.name:  # 行狀：哪一位名將送的（送的是什麼，annals.watch 照裝備記）
                annals.note(self.state, self.content, annals.FIGURE, f"{annals.figure_name(self.content, cid)}看重你，送了你一份贈禮。", 4, figure=cid)
        return msgs

    def _people_here(self) -> set[str]:
        """此刻站在你身邊的人物：同 _figures_here 的所在（人物表上的人照此刻的所在與狀態，其餘照 recruit_at、talk_at），不限深度互動；
        在路上一個都沒有。再加上這一下加了情誼的人（終審 F2：情誼只從當面的事來——對話、晉升事件、伏筆收尾——劉關張在婁桑村的晉升
        事件裡當面出現，不在他們平常站的地方）。名將贈禮與本命兵器照它寫當面交給你還是託人送來（FB-139、FB-149）。"""
        s, c = self.state, self.content
        before = self._affinity_before or {}
        raised = {cid for cid, v in s.player.affinities.items() if self._affinity_before is not None and v > before.get(cid, 0)}
        if s.player.journey is not None:
            return raised
        here, placed = s.player.location, figures.placed_characters(s, c)
        return raised | {cid for cid, ch in c.characters.items()
                         if (placed[cid] == here if cid in placed else here in (ch.recruit_at, ch.talk_at))}

    def _gift_entry(self, lines: list[str]) -> None:
        """名將贈禮與本命兵器（情誼那條路）另起一則江湖紀錄（FB-139、FB-149），排在當下那個動作的那一則之後。沒有就不寫。"""
        if lines:
            journal.add_entry(self.state, JournalEntry(time=self.state.world.time, title=treasures.GIFT_TITLE, tag=lines[0], lines=lines[1:]))

    def _signature_arms(self, record=None, beaten: str | None = None, later: list | None = None) -> list[str]:
        """名將本命兵器（兵器設計 4.10；打造第三批，signature_arms.due）：情誼到 signature_affinity 他送你，打贏他本人 signature_wins 次
        他讓你奪走；每位名將每季全服一人（WorldState.signature_arms，這一下動作最後的 _save_season 存回去，同名將贈禮）。choose 與
        answer_event 最後各叫一次（情誼從對話、事件、隨口應對來都走得到）；_challenge 打贏時帶 record、beaten 先叫一次，那一把寫進
        這一場戰報的「得失」（同寶物掉落）——只寫被打敗的那一位的那一把：同一下動作裡別位名將的情誼也到了、一起給的，不寫進這一場
        （終審 minor）。行狀記一筆（人物）；later 給了（_challenge）就先放進去，等那一場自己的行狀記完再記，行狀才照時間先後。
        不擲骰：不碰 Game.rng。"""
        s, c = self.state, self.content
        items, msgs = signature_arms.due(s, c, beaten=beaten, present=self._people_here())
        for item in items:
            arm = next((a for a in c.gear.signature_arms if a.character == item.signature), None)
            if record is not None and beaten is not None and arm is not None and arm.figure == beaten:
                record.materials.append(signature_arms.GAIN_LINE.format(name=item.name))
            note = (signature_arms.annal_line(c, item, s.world.signature_arms[item.signature].via), item.signature)
            if later is None:
                annals.note(s, c, annals.FIGURE, note[0], 4, figure=note[1])
            else:
                later.append(note)
        return msgs

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
        self._restore_showdowns()
        seen = p.battle_results_seen
        # 攻城戰跟決戰、別的攻城戰同時打（領地爭奪第二批）：先開的可能晚收場，往回讓 RESULT_LOOKBACK 場、補過的用流水號跳過
        fresh = self.world.ended_battles(after=max(0, max(seen, default=0) - RESULT_LOOKBACK), skip=set(seen))
        if not fresh:
            return
        current = self.world.get_season_number()
        for season, battle in fresh:
            me = battle.participants.get(p.name)
            if me is not None:
                self._file_showdown(battle, me, None if season == current else season)
            p.battle_results_seen.append(battle.record_id)

    def _restore_showdowns(self) -> None:
        """補回被洗掉的決戰戰報（PM 2026-10-14：以前決戰跟遊歷共用最近 20 場，收場兩小時就被十幾場遊歷擠掉）：這一季收場、自己參戰過、
        已經補過（battle_results_seen）卻不在戰報裡的決戰，照 battles 表重建一筆（_showdown_lines 那幾句與完整戰況）。只補戰報：
        軍餉、名望、江湖紀錄、行狀當時都發過了，不再發、不寫紀錄、不放「剛剛」的卡片。一季只查一次（showdowns_restored）。"""
        c, s, p = self.content, self.state, self.state.player
        season = self.world.get_season_number()
        if p.showdowns_restored == season:
            return
        p.showdowns_restored = season
        seen = set(p.battle_results_seen)
        have_refs = {r.battle_ref for r in s.battles if r.kind in battlelog.SHOWDOWN_KINDS}
        have_old = {(r.event, r.time): r for r in s.battles if r.kind == "showdown"}  # 這一版以前的戰報沒有 battle_ref：照戰名與收場時刻認
        added = False
        for battle in self.world.season_ended_battles(season):
            me = battle.participants.get(p.name)
            definition = self._definition_of(battle)
            if me is None or definition is None or battle.unfinished or battle.record_id not in seen or battle.record_id in have_refs:
                continue
            time = battle.end_time if battle.end_time is not None else s.world.time
            if (definition.name, time) in have_old:  # 還留著的舊戰報：補上 battle_ref，戰報頁就照 battles 表畫完整戰況
                kept = have_old[(definition.name, time)]
                kept.battle_ref = kept.battle_ref if kept.battle_ref is not None else battle.record_id
                continue
            sides = battle_instance.side_names(battle, definition)  # 守將那一格寫守軍（FB-540）
            side = sides.get(me.faction, me.faction)
            foes = "、".join(n for fid, n in sides.items() if fid != me.faction) or "敵軍"
            lines, *_ = self._showdown_lines(battle, me, side, sides)
            s.battle_seq += 1
            s.battles.append(BattleRecord(
                id=s.battle_seq, time=time, location=self._battle_region_name(definition) if definition.region else definition.name,
                kind="siege" if battle.siege is not None else "showdown", event=definition.name, opponent=foes, ours=[], tier=battle.outcome_title or "收場", our_power=0.0,
                difficulty=0.0, side=side, notes=[*lines, RESTORED_NOTE], gauge=self._gauge_of(battle, definition, me.faction),
                log=self._round_blocks(battle, definition, last=None, oldest_first=True, me=me), battle_ref=battle.record_id,
            ))
            added = True
        if added:
            s.battles.sort(key=lambda r: r.time, reverse=True)  # 補回來的照收場時刻排進去（sort 是穩定的：同一時刻照原本的先後）

    def _showdown_lines(
        self, battle: battle_instance.BattleInstance, me: battle_instance.BattleParticipant, side: str, sides: dict[str, str],
    ) -> tuple[list[str], str, int | None, list]:
        """決戰戰報裡跟自己有關的那幾句（結果、勝負的關鍵、職位、出手幾回合、帶頭、點名、倒下、戰功排第幾）：收場補戰報（_file_showdown）
        與補回被洗掉的戰報（_restore_showdowns）共用。回（那幾句, 職位名, 戰功名次, 名次表）。"""
        c = self.content
        tuning = c.config.battle
        lines = [t for t in (battle.outcome_text, battle.outcome_reason) if t]
        lines += battle.seal_notes  # 玉璽碎片：下戰書、現世的得主（5.9 最後一條、3.3）
        role = battle_instance.role_name(c.config.battle, me.role)
        lines.append(f"你以{role}出陣，出手 {me.acted_rounds} 回合" if role else f"你出手 {me.acted_rounds} 回合")
        if me.mount:
            lines.append(mounts.CAVALRY_REPORT.format(name=me.mount))  # 騎著馬出陣（裝備四欄 5.9）；原句「你以…出陣」不動
        if me.troops:
            lines.append(TROOPS_REPORT.format(names=me.troops))  # 帶著部下出陣（PM 2026-10-12）
        if me.led_rounds:  # 出固定招的人也有名字（Joy 2026-10-10）
            lines.append(f"你帶頭衝陣、替自己這一邊佔了上風 {me.led_rounds} 回合")
        if me.hurt_dealt >= 0.5:
            lines.append(f"你的放手一搏點名打傷了對手，打掉他們氣血 {round(me.hurt_dealt)}")
        if me.targeted_by:
            lines.append(f"{'、'.join(me.targeted_by)}在陣上點名要對付你" + (
                f"，你被打掉氣血 {round(me.hurt_taken)}" if me.hurt_taken >= 0.5 else "，卻沒能傷到你"))
        elif me.hurt_taken >= 0.5:
            lines.append(f"你太顯眼，被對面集火，打掉氣血 {round(me.hurt_taken)}")
        if me.fell_round is not None:
            lines.append(f"你在第 {me.fell_round} 回合倒下，轉為觀戰")
        mine = battle_instance.merit(tuning, me)
        ranking = battle_instance.merit_ranking(battle, tuning, me.faction) if me.faction in sides else []  # 豪強也排（Joy 2026-10-13）
        rank = next((i for i, (q, _) in enumerate(ranking, 1) if q.name == me.name), None)
        if rank is not None:  # 個人戰功（Joy 2026-10-10）：自己這一邊排第幾、怎麼來的
            parts = "、".join(battle_instance.merit_parts(me))
            lines.append(f"你的戰功 {mine}，在{side}排第 {rank}／{len(ranking)}" + (f"（{parts}）" if parts else ""))
        return lines, role, rank, ranking

    def _file_showdown(
        self, battle: battle_instance.BattleInstance, me: battle_instance.BattleParticipant, earlier: int | None,
    ) -> None:
        """一場收場的決戰寫成自己的一則江湖紀錄與一筆戰報（kind 是 showdown），「剛剛」放這一場的卡片。
        earlier 是上一季（或更早）打的那一季的編號，這一季打的是 None：上一季的標明季別，大勢的增減寫進敘事、
        不放進數值變化——數值變化看起來像剛發生在你身上的。

        季終收兵的決戰（unfinished，FB-035）沒有結果：只寫一則江湖紀錄交代一聲，不加戰報、不放「剛剛」的戰鬥卡片。"""
        c, s = self.content, self.state
        definition = self._definition_of(battle)  # 攻城戰的名字是「攻城・地點」（領地爭奪第二批）
        # 自己站哪一方（臨時投效的是投效的那一軍）；單方攻中立地時守將那一格寫守軍（battle_instance.side_names，FB-540）
        sides = battle_instance.side_names(battle, definition) if definition is not None else {}
        armies = dict(sides)
        name = definition.name if definition is not None else battle.battle_id
        side = sides.get(me.faction, me.faction)
        foes = "、".join(n for fid, n in armies.items() if fid != me.faction) or "敵軍"
        where = self._battle_region_name(definition) if definition is not None and definition.region else name
        outcome = battle.outcome_title or "收場"
        label = "" if earlier is None else f"第 {earlier} 季・"
        time = battle.end_time if battle.end_time is not None else s.world.time
        if battle.unfinished:
            lines = [battle.unfinished_text or battle_instance.UNFINISHED_TEXT]
            lines += [f"你出手 {me.acted_rounds} 回合"] if me.acted_rounds else []
            journal.add_entry(s, JournalEntry(time=time, title=f"{label}{name}・{outcome}", tag=f"你站在{side}", lines=lines))
            return
        lines, role, rank, ranking = self._showdown_lines(battle, me, side, sides)
        tuning = c.config.battle
        h = battle.highlight
        fame = 0
        highlight_changes = self._showdown_pay(battle, me, lines) if earlier is None else []
        if earlier is None and me.escort is not None and roster.on(c) and battle.siege is None:  # 歷史武將同行：隨你上陣的那一位回江湖了（攻城戰不放，裁決 14）
            lines += self._escort_home(me.escort)
        if earlier is None:
            s.player.showdowns += 1
            if h is not None and h.name == me.name and h.won and tuning.highlight_fame:  # 這一場最有戲的那一搏是自己的、而且成了
                fame += tuning.highlight_fame
                lines.append("你那一搏成了這一仗最令人印象深刻的一幕，江湖上傳開了。")
            top = battle_instance.top_merit(battle, tuning, me.faction) if me.faction in sides else None
            if top is not None and top.name == me.name:  # 這一邊的首功
                s.player.top_merits += 1
                fame += tuning.top_fame
                lines.append(f"你是{side}這一仗的首功，名字傳遍了江湖。")
            if fame:
                highlight_changes += renown.gain(s, c, "fame", fame)  # 名聲設計 3.2
            # 風聞（大勢人物擴充）：打贏的那一邊戰功前三名，那一區同一方的人物聽說了。助守中立地的守將（站的是另一軍那一格）
            # 不是替那一軍出戰，不加那一軍人物的情誼（PM 2026-10-21，FB-540）
            if (definition is not None and definition.region and battle.outcome_side == me.faction
                    and rank is not None and rank <= 3 and me.faction != battle_instance.neutral_guard(battle)):
                lines += figure_life.spread(s, c, "merit", str(battle.record_id), at=None, side=me.faction,
                                            text=f"在{name}立了戰功", region=definition.region)
        rule = c.config.breakthrough
        if earlier is None and me.acted_rounds >= rule.showdown_rounds:  # 絕學的契機（方案 C）：這一季的決戰裡真的出過手
            lines += cultivation.seize(s, c, self.world, rule.showdown_ratio, self.rng)
        trends = {t.id: t.name for t in c.scenario.trends}
        moved = resolve_trends(c, s.world, battle.outcome_trend_delta)  # 開關關著時戰線都寫成黃巾聲勢
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
            changes += highlight_changes
            record_changes += highlight_changes
        else:
            changes, record_changes = [], []
            lines += [
                f"（第 {earlier} 季）" + (front_text(c, tid, d, str(time)) if in_words and can_draw_side_change(c, tid) else plain(tid))
                for tid, d in moves.items()
            ]
        record = BattleRecord(
            id=s.battle_seq + 1, time=time, location=f"{label}{where}", kind="siege" if battle.siege is not None else "showdown",
            event=name, opponent=foes,
            ours=[], tier=outcome, our_power=0.0, difficulty=0.0, side=side, notes=list(lines), changes=list(record_changes),
            gauge=self._gauge_of(battle, definition, me.faction) if definition is not None else None,
            log=self._round_blocks(battle, definition, last=None, oldest_first=True, me=me) if definition is not None else [],
            battle_ref=battle.record_id,
        )
        battlelog.add_record(s, record)
        s.battle_card = record.id
        journal.add_entry(s, JournalEntry(
            time=time, title=f"{label}{name}・{outcome}", tag=f"你站在{side}", lines=lines, changes=changes,
            battle_id=record.id,
        ))
        self._annal_showdown(battle, me, name, side, role, rank, len(ranking), earlier, time)

    def _annal_showdown(
        self, battle: battle_instance.BattleInstance, me: battle_instance.BattleParticipant, name: str, side: str, role: str,
        rank: int | None, ranked: int, earlier: int | None, time: float,
    ) -> None:
        """一場決戰寫進行狀（玩家傳）：站哪邊、職位、出手幾回合、帶頭佔上風、首功或戰功排名、倒下、結果；每一次放手一搏另一則
        （原句、播出來的那一版劇情、成敗、點名了誰）。上一季的決戰（earlier）接在存起來的那一季後面（角色已經重來了）。"""
        c, s = self.content, self.state
        if not annals.on(c):
            return
        tuning = c.config.battle
        top = battle_instance.top_merit(battle, tuning, me.faction) if rank is not None else None
        parts = [f"{name}，你站在{side}" + (f"以{role}出陣" if role else ""), f"出手 {me.acted_rounds} 回合"]
        if me.led_rounds:
            parts.append(f"帶頭佔了 {me.led_rounds} 回合上風")
        if top is not None and top.name == me.name:
            parts.append("是這一邊的首功")
        elif rank is not None and rank <= 3:
            parts.append(f"戰功排第 {rank}／{ranked}")
        if me.fell_round is not None:
            parts.append(f"第 {me.fell_round} 回合倒下")
        parts.append(f"結果{battle.outcome_title or '收場'}")
        place = self._battle_region_name(c.battles[battle.battle_id]) if battle.battle_id in c.battles and c.battles[battle.battle_id].region else ""
        won = bool(battle.outcome_side) and battle.outcome_side == me.faction
        entries = [annals.entry(
            s, c, annals.SHOWDOWN, "，".join(parts) + "。", 5 if won or (top is not None and top.name == me.name) else 4,
            place=place, time=time, season=earlier is None,
        )]
        for g in me.gambles:
            what = f"在{name}陣上放手一搏" + ("，成了" if g.won else "，沒成") + (f"，點名{g.target}" if g.target else "") + "。"
            entries.append(annals.entry(
                s, c, annals.SHOWDOWN, what, 4 if g.won else 3, quote=g.text, reply=g.story, place=place, time=time, season=earlier is None,
                keep=[g.target],  # 點名的人（參戰的玩家）的名號原樣留，沒點名是空的（FB-9020）
            ))
        if earlier is None:
            s.player.annals += entries
            annals.trim(s, c)
        else:
            for e in entries:
                self.world.add_saved_annal(earlier, s.player.name, e.model_dump())

    def _showdown_pay(
        self, battle: battle_instance.BattleInstance, me: battle_instance.BattleParticipant, lines: list[str],
    ) -> list[str]:
        """決戰的軍餉（Config.showdown_pay）：照個人戰功發銀兩與經驗（最多 share_cap 倍），贏的一方另加；投靠了陣營、替自己陣營出戰的人另記本季貢獻
        （照推大勢的帳）。回傳要寫在「得失」的那幾樣（「銀兩 +N」的慣例），升級的話照 add_exp 的訊息接在 lines 後面。
        天命之爭得天命的那一軍：銀兩與經驗 × Config.seal.mandate.pay_scale、名望 +fame（貢獻不加倍，玉璽二）。
        序章裡的人不發（FB-113）：修好之前在序章裡投效、出手的新人，以前 1 級大勝拿 120 經驗、序章中途升到 5 級（FB-122）。"""
        c, s = self.content, self.state
        if prologue_rules.active(s, c):
            return []
        pay, p = c.config.showdown_pay, s.player
        full = pay.full_rounds * max(1, c.config.battle.merit_points.get("acted", 0))  # 只出手 full_rounds 回合的戰功算一倍
        share = max(pay.idle_share, min(pay.share_cap, battle_instance.merit(c.config.battle, me) / full))
        won = bool(battle.outcome_side) and me.faction == battle.outcome_side
        bonus = pay.win_bonus.get(battle.outcome_margin, 0.0) if won else 0.0
        destiny = won and seal.on(c) and seal.is_mandate_battle(c, c.battles.get(battle.battle_id))  # 得天命的那一軍（8.3；要 PM 定的第 3 條；碎片關著時天命不定，不加給）
        scale = c.config.seal.mandate.pay_scale if destiny else 1
        half = c.config.conquest.pay_share if battle.siege is not None else 1.0  # 攻城戰（領地爭奪第二批）：決戰的幾成（設計 4.4）
        silver = round(pay.silver * share * (1 + bonus) * half) * scale
        exp = round(pay.exp * share * (1 + bonus) * half) * scale
        changes = []
        if destiny and c.config.seal.mandate.fame:
            changes += renown.gain(s, c, "fame", c.config.seal.mandate.fame)  # 名聲設計 3.2
        if silver:
            p.stats["silver"] = p.stats.get("silver", 0) + silver
            changes.append(f"銀兩 +{silver}")
        if exp and team.maxed(c, p.member):  # 滿級：經驗照 5 換 1 換成心得（3.5）
            gained = team.maxed_xinde(s, c, exp, "showdown")
            if gained:
                lines.append(team.MAXED_XINDE.format(n=gained))  # 跟其他來源同一句（FB-452）
                changes.append(f"心得 +{gained}")
        elif exp:  # 同伴不進決戰（人物資質設計 14.5）：只給本人；升級給屬性點同切磋。決戰是仗（減法季 45 級以後照算）
            before = p.member.level
            lines += team.add_exp(c, p.member, exp, p.name, "showdown")
            if p.member.level > before:
                points = team.level_points(self.state, c, before, p.member.level)
                p.stat_points += points
                if points:
                    lines.append(f"你有 {p.stat_points} 點屬性可以分配（點名號展開）。")
            changes.append(f"經驗 +{exp}")
        for chief in battle.commanders:  # 龍頭上陣：最後一擊擊退大將的人
            if chief.felled_by == me.name and c.config.battle.generals.slay_fame:
                changes += renown.gain(s, c, "fame", c.config.battle.generals.slay_fame)
                lines.append(SLAY_LINE.format(name=chief.name))
        if me.acted_rounds >= 1:  # 名聲 3.1：自己出手至少 1 回合（同首功）；掛機被代為固守的回合不算
            rout = self._deed_fame("showdown_rout") if won and battle.outcome_margin == "大勝" else []
            changes += journal.combine_changes(self._deed_fame("showdown") + rout)
        if self._showdown_credits(me):  # 替自己這一方出戰才記（豪強分屬兩軍：依附那一軍）；臨時投效的不記
            push_points = pay.contrib_push + (pay.win_contrib_push.get(battle.outcome_margin, 0) if won else 0)
            contrib = round(c.config.contrib_per_push * push_points * share * half)
            if contrib and season_one(c, s.world):
                # 豪強記參戰那一刻那一邊那一本（計畫 5.0 第 12 條：中途改幫另一軍，這一場照舊記原來那一軍）
                wins.credit(p, c, s.world, calendar.point(s.world.time, c, s.world).week, contrib, side=me.faction)
                changes.append(f"貢獻 +{contrib}")
        if changes:
            lines.append(f"{'得勝的' if won else ''}軍餉發下來了。")
        return changes + self._showdown_tier4(battle, me, lines)

    def _showdown_credits(self, me: battle_instance.BattleParticipant) -> bool:
        """這一場的戰功記不記貢獻：站的是自己這一方（豪強分屬兩軍：依附那一軍）才記，臨時投效的不記。三陣營四勝利開著的季，
        豪強站的是它能幫的那一軍就記（記參戰那一刻那一邊那一本，_showdown_pay），不看此刻幫誰——中途改幫另一軍，這一場照舊算。"""
        side = self._side()
        if side is not None and me.faction == side:
            return True
        p = self.state.player
        return self._four_wins() and me.faction in wins.allies(p, self.content)

    def _four_wins(self) -> bool:
        """這一季三陣營四勝利開著嗎（wins.on：Config.jianfa 的 four_wins＋開季的章）。"""
        return wins.on(self.content, self.state.world)

    def _watching_battle(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> bool:
        """這個人此刻打不了這場仗、只能在一旁看（options() 照常給平常的選項，場景上仍看得到戰場）：
        - 參戰者離開了決戰的大區（人在區外，或這一趟路正要走出大區；區內站與站之間走動不算）：這回合不出手，
          照常遊玩，回來才回到戰場；
        - 還沒參戰的人不在決戰的大區、或在路上（地圖擴充設計第六節：人要在現場才能加入）。
        全服決戰不能把打不了仗的人鎖住。"""
        me = battle.participants.get(self.state.player.name)
        if me is not None:
            return me.away
        if battle.siege is not None and not siege.slots(battle.siege, self._conquest_side()):
            return True  # 攻城戰（領地爭奪第二批）：這一仗沒有自己站得進去的格（另一軍攻中立地，裁決 8），照常遊玩
        return not self._at_battle(definition)

    def _fighting(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> bool:
        """開打了、自己在場上打得了這一場：戰鬥選單取代整份選單（options），戰場取代整個場景（scene_text）。兩邊都問這一個，
        選單照常給的人場景上就看得到自己眼前的事。不是的人：集結中、只能觀戰（_watching_battle）、開打了還沒投效的散人與豪強
        （FB-109：以前選單照給、場景卻只剩戰場，事件內文、有所感、人物的回話、投靠的確認都看不到）。"""
        if battle.phase == "muster" or self._watching_battle(battle, definition):
            return False
        if self.state.player.name not in battle.participants and allied.needs_ally(self.state, self.content):
            return False  # 拜入曹氏莊院還沒挑一邊（FB-273）：先挑，選單只剩那兩顆
        return not (self._free_agent(definition) and self.state.player.name not in battle.participants)

    def _sides(self, definition: BattleDef) -> dict[str, str]:
        """這場決戰能站的每一方（id → 名字）：交戰的兩軍。"""
        return {f.id: f.name for f in definition.factions}

    def _free_agent(self, definition: BattleDef) -> bool:
        """劇本分陣營、自己不是交戰兩軍的人（散人、地方豪強）：決戰時可以臨時投效交戰的兩軍之一，只算這一場
        （散人：試玩回饋 2026-10-08；豪強：Joy 2026-10-13「豪強在大決戰還是要加入某一陣營，主軸還是官兵跟黃巾」）——
        不寫進投靠名冊、不改自己的陣營、不算叛投、不記貢獻。
        豪強分屬兩軍的季（企劃者 2026-10-15），豪強是依附那一軍的人（_side），跟兩軍的人一樣加入，不是臨時投效；
        拜入曹氏莊院還沒挑一邊（allied.needs_ally）也不給臨時投效，先挑一邊（FB-273）。"""
        if allied.needs_ally(self.state, self.content):
            return False
        return bool(self.content.scenario.factions) and self._side() not in self._sides(definition)

    def _own_side_name(self) -> str:
        """臨時投效的人打完照樣是誰：散人，或自己陣營的名字（豪強）。"""
        faction = self.state.player.faction
        return "散人" if faction is None else f"{self.content.scenario.faction_name(faction, faction)}的人"

    def _enlist_options(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> list[Option]:
        """散人的臨時投效按鈕（兩軍各一顆）：集結時已經投效的那一邊是灰的「已投效」、還能改投另一邊；開打了還沒參戰的照樣能投效。
        單方攻中立地時守將那一格（battle_instance.neutral_guard）寫「助守【守軍】」，不寫那一格的陣營（FB-540；鈕 id 照舊是那一格的 id）。"""
        me = battle.participants.get(self.state.player.name)
        guard, names = battle_instance.neutral_guard(battle), battle_instance.side_names(battle, definition)
        out = []
        for fid in battle_instance.fields(battle, definition):  # 三方混戰（裁決 22）多一顆助守【守軍】（GUARD）
            done = me is not None and me.faction == fid
            if fid == guard:
                label = (siege.HELPED_GUARD if done else siege.HELP_GUARD).format(side=names[fid])
            else:
                label = f"已臨時投效【{names[fid]}】" if done else f"臨時投效【{names[fid]}】（只算這一場）"
            out.append(Option(id=f"battle:enlist:{fid}", label=label, enabled=not done))
        return out

    def _enlist_sides(self, battle: battle_instance.BattleInstance | None, definition: BattleDef) -> dict[str, str]:
        """臨時投效站得了的格（id → 名字）：交戰的兩軍，三方混戰再加助守【守軍】（GUARD，裁決 22）。"""
        sides = self._sides(definition)
        if battle is not None and battle_instance.melee(battle):
            sides[battle_instance.GUARD] = battle_instance.GUARD_SIDE
        return sides

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
        """只能觀戰時，場景上說明為什麼：參戰後離開了大區、或還沒到戰場。"""
        if self.state.player.name in battle.participants:
            region = self._battle_region_name(definition)
            return f"你離開了{region}，這回合不出手；人回到{region}就能再出手。"
        if battle.siege is not None and not siege.slots(battle.siege, self._conquest_side()):
            return siege.watch_line(self.content, battle.siege)  # 攻城戰：另一軍站不進守將那一格（裁決 8）
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
            self._mutate_battle_of(battle, lambda b: battle_instance.set_away(b, name, away))

    def rally_region(self) -> str | None:
        """自己這一方正在集結或開打的全服決戰、而自己人不在現場時，回傳那場決戰的大區 id，給伺服器假人決定要不要
        趕路（地圖擴充設計 3.4）。不在現場的意思：還沒參戰的人不在那個大區或在路上；參戰者離開了大區
        （見 _in_battle_region）。沒有這種決戰、決戰不限地點、打不了這場、已經在場上或倒下了，都是 None。
        有攻城戰時（領地爭奪第二批）每一場都看（決戰在前、再照開集結的先後）：攻城認自己那一邊的攻方、守方（守將那一格不算，裁決 8）。"""
        if self._sieges():
            return self._rally_any()
        status = self._battle_status(tick=False)
        if status is None:
            return None
        battle, definition = status
        if definition.region is None:
            return None
        me = battle.participants.get(self.state.player.name)
        if me is None and self.state.player.faction is None and self._free_agent(definition):
            # 散人沒有自己的一方：不會為了投效趕過去，投效了才算自己這一方。豪強照樣趕過去臨時投效（bot.enlist_pick）
            return None
        if me is not None:
            return definition.region if me.away and not me.eliminated else None
        return None if self._at_battle(definition) else definition.region

    def _rally_any(self) -> str | None:
        """rally_region 在有攻城戰時：自己已經在某一場的名單上就只看那一場（離開了大區、還沒倒下才回它的大區）；不然照先後找第一場
        自己這一方打得進去、自己人又不在現場的那一場的大區。散人不為了投效趕過去（同決戰）；攻城戰另照 siege.slots。"""
        name = self.state.player.name
        showdown = self.world.get_battle()
        live = ([showdown] if showdown is not None and showdown.phase != "ended" else []) + self._sieges()
        mine = next((b for b in live if name in b.participants), None)
        if mine is not None:
            d = self._definition_of(mine)
            me = mine.participants[name]
            return d.region if d is not None and d.region is not None and me.away and not me.eliminated else None
        for b in live:
            d = self._definition_of(b)
            if d is None or d.region is None:
                continue
            if self.state.player.faction is None and self._free_agent(d):
                continue  # 散人沒有自己的一方：不會為了投效趕過去
            if b.siege is not None and not siege.slots(b.siege, self._conquest_side()):
                continue
            if not self._at_battle(d):
                return d.region
        return None

    def _gauge_of(self, battle: battle_instance.BattleInstance, definition: BattleDef, side: str | None) -> dict:
        """battle_instance.gauge 的參數：時刻表決戰（第一季開著）照偏離中線分大勝，其餘照 outcomes 的門檻。"""
        timetable = definition.timetable_event is not None and season_one(self.content, self.state.world)
        return battle_instance.gauge(battle, definition, side, timetable, self.content.config.battle, self.state.player.name)

    def battle_gauge(self) -> dict | None:
        """場景裡畫著的這場決戰（集結、開打）的戰局條（Joy 2026-10-10）；沒有、序章裡是 None。只讀，不推進戰鬥。
        自己在場上就站自己那一邊看；還沒加入的看自己陣營那一邊；散人、第三方看第一方在左。"""
        status = self._battle_for_me(tick=False)
        if status is None:
            return None
        battle, definition = status
        p = battle.participants.get(self.state.player.name)
        side = p.faction if p is not None else self._side()
        if p is None and battle.siege is not None and not siege.slots(battle.siege, self._conquest_side()):
            # FB-693：攻城戰裡自己站不進任何一格（另一軍看單方攻中立地：守將借的是那一軍的格），兩邊都不標「我方」、第一方在左
            side = None
        g = self._gauge_of(battle, definition, side)
        # 這一回合還剩幾秒逾時（同 _round_wait）：網頁每秒自己倒數「最遲 M 分 S 秒後結算」，不等十秒一次的輪詢（Joy 2026-10-13）。
        # 暫停中、集結中是 None（不倒數）
        if battle.phase == "active" and self.world.paused_at() is None:
            g["due"] = max(0, int(battle.round.opened_real + definition.round_seconds - self.now))
        return g

    def siege_banner(self) -> dict | None:
        """場景裡畫著的這一場是攻城戰時，畫面最上面那一條（領地爭奪第三批 A，企劃者挑甲：「攻城・地點｜守方：某某」，siege.banner）；
        決戰、沒有戰鬥、序章裡是 None。同 battle_gauge 看同一場（_battle_for_me），只讀。"""
        status = self._battle_for_me(tick=False)
        if status is None or status[0].siege is None:
            return None
        return siege.banner(self.content, status[0])

    def record_gauge(self, record_id: int | None) -> dict | None:
        """戰報頁那一筆是決戰時收場那一刻的戰局條；不是決戰、找不到是 None。"""
        record = battlelog.find(self.state, record_id) if record_id is not None else None
        return record.gauge if record is not None else None

    def card_gauge(self) -> dict | None:
        """「剛剛」那張戰鬥卡片是一場決戰時，收場那一刻的戰局條（BattleRecord.gauge）；不是就 None。"""
        if not self.shows_battle_card():
            return None
        record = battlelog.find(self.state, self.state.battle_card)
        return record.gauge if record is not None else None

    def _battle_scene_text(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> str:
        header = f"**{definition.name}**"
        # 攻城戰（領地爭奪第二批）：誰攻、守方是誰寫在畫面最上面那一條（siege_banner，第三批 A），場景不再寫一次（PM）；
        # 只留那一條沒說到的（三方混戰的規矩、沒到場的那一軍，siege.scene_note）
        if battle.siege is not None and (note := siege.scene_note(self.content, battle.siege, battle)):
            header += "\n\n" + note
        if front := conquest.front_scene(self.content, definition, battle.front_note):  # 起點照哪一條戰線（開集結那一刻的快照）
            header += "\n\n" + front
        if battle.seal_shard and battle.seal_shard in self.content.seal:  # 璽動（4.3）：參戰的人知道打完可能有單挑
            header += "\n\n" + seal.stir_text(self.content, battle.seal_holder or "", self.content.seal[battle.seal_shard].name, scene=True)
        if seal.on(self.content) and seal.is_mandate_battle(self.content, definition):  # 天命之爭（8.3）：碎片在哪一軍、懷璽的人份量加重
            shift = seal.lean_shift(battle.seal_lean, definition, self.content.config.seal)  # 同集結那一刻的算法（FB-186）
            weight = seal.MANDATE_WEIGHT if seal.holders(self.world.seal_state().registry) else ""  # 全服沒人持有就不寫（FB-189）
            header += "\n\n" + seal.MANDATE_SCENE.format(
                lean=seal.lean_text(battle.seal_lean, definition), weight=weight,
                shift=seal.shift_text(shift, battle.seal_lean, definition, extra=battle.front_note is not None),  # FB-687
            )
        names = battle_instance.side_names(battle, definition)  # 單方攻中立地時守將那一格寫守軍（FB-540）
        if battle.phase == "muster" and battle.commanders:  # 龍頭上陣：集結時就看得到誰親自上陣（三方混戰多一格守軍）
            header += "\n\n" + "\n".join(
                f"{names[fid]}：{text}" for fid in battle_instance.fields(battle, definition) if (text := generals.lineup(battle, fid)))
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
                side = names.get(me.faction, me.faction)
                leaving = "；走出這一區就不算在場" if definition.region is not None else ""
                joined = "臨時投效" if self._free_agent(definition) else "加入"
                if me.faction == battle_instance.neutral_guard(battle):
                    joined = siege.HELP_GUARD_TITLE  # 「你已助守【守軍】」（FB-540）
                role = battle_instance.role_text(self.content.config.battle, me.role)
                role = f"你的職位：{role}。" if role else ""
                ride = mounts.CAVALRY_LINE.format(name=me.mount, pct=mounts.pct(me.cavalry)) + "。" if me.mount else ""  # 騎著馬（5.9）：沒騎馬一個字都不多
                ride += TROOPS_LINE.format(names=me.troops, pct=mounts.pct(me.troop_bonus)) + "。" if me.troops else ""  # 帶著部下
                ride += ESCORT_MUSTER.format(name=me.escort.name) if me.escort is not None else ""  # 隨你出陣的同伴（歷史武將同行）
                return f"{header}\n\n你已{joined}【{side}】，集結還剩現實 {left}。{role}{ride}集結結束就開打，在那之前照常行動{leaving}。"
            if self._free_agent(definition):
                who = "你是散人" if self.state.player.faction is None else f"你是{self._own_side_name()}，不是交戰的兩軍"
                can = "可以臨時投效其中一方，只算這一場"
                if battle_instance.neutral_guard(battle) is not None:  # 單方攻中立地：一邊是攻方、一邊是助守（FB-540）
                    can = siege.FREE_AGENT_GUARD.format(
                        who="、".join(names.get(a, a) for a in battle.siege.attackers), place=self.content.locations[battle.siege.loc].name)
                return f"{header}\n\n集結中，還剩現實 {left}。{who}，{can}；集結期間照常行動。"
            return f"{header}\n\n集結中，還剩現實 {left}。選擇陣營加入；集結期間照常行動。"
        act = battle_instance.current_act(battle, definition)
        # 第幾回合／一共幾回合（戰鬥系統設計 3.2）：讓人知道還要打多久；收場的決戰不會走到這裡。
        # 已送出／在場：讓等待看起來是在等人，不是壞了（試玩回饋 2026-10-08）
        count = f"（第 {battle.round_number + 1}／{battle_instance.total_rounds(definition)} 回合・{self._round_wait(battle, definition)}）"
        lines = [header, *self._idle_note(battle), f"【{act.title}】{count}{battle_instance.act_text(battle, definition)}"]
        p = battle.participants.get(self.state.player.name)
        mine = p.faction if p is not None else self._side()
        if p is None and mine is not None and mine == battle_instance.neutral_guard(battle):
            mine = None  # FB-543：單方攻中立地，守將站的是這個人陣營的 id，人沒參戰（旁觀）：守將的令不是他這邊的令，不寫。助守的人（p 在守將那一格）照寫
        lines += self._chief_lines(battle, definition, mine)
        lines += self._round_blocks(battle, definition)
        if p is not None and (role := battle_instance.role_text(self.content.config.battle, p.role)):
            lines.append(f"你的職位：{role}")
        if p is not None and p.mount:
            lines.append(mounts.CAVALRY_LINE.format(name=p.mount, pct=mounts.pct(p.cavalry)))  # 騎著馬上陣（裝備四欄 5.9，加入時的快照）
        if p is not None and p.troops:
            lines.append(TROOPS_LINE.format(names=p.troops, pct=mounts.pct(p.troop_bonus)))  # 帶著部下上陣（加入時的快照）
        if p is not None and p.escort is not None:
            lines.append(self._escort_line(p.escort))  # 隨你出陣的同伴（氣血、敗走；別人的不列）
        if p is not None:
            last = []  # 上一回合的兩句併成一段 markdown 引用（「> 」、段內換行）：網頁在 .scene blockquote 底下縮成小字、淡色
            enemy = next((f for f in definition.factions if f.id != p.faction), None)
            seen = battle.last_mix.get(enemy.id) if enemy is not None else None
            if seen:  # 這回合的比例要到結算才揭曉，畫面只寫上一回合（設計 3.4）
                parts = "・".join(f"{m} {round(seen[m] * 100)}%" for m in MOVES)
                last.append(f"> 對面上一回合（{names.get(enemy.id, enemy.name)}）：{parts}")
            if p.last_result:
                last.append(f"> 你上一回合：{p.last_result}")
            if last:
                lines.append("\n".join(last))
            lines += self._battle_spotlight(battle, definition, p)
        if p is not None and p.eliminated:
            lines.append("（你已經倒下，只能在一旁觀戰。）")
        elif watching:  # 倒下的人不會再出手，不必再說「回到大區就能再出手」
            lines.append(watch_line)
        return "\n\n".join(lines)

    def _chief_lines(self, battle: battle_instance.BattleInstance, definition: BattleDef, side: str | None) -> list[str]:
        """龍頭上陣：兩邊上陣的人物（氣血、敗走），自己這一方這一回合的將令。沒有人物上陣是空的。"""
        if not battle.commanders:
            return []
        names = battle_instance.side_names(battle, definition)  # 單方攻中立地時守將那一格寫守軍（FB-540）
        rows = [f"{SIDE_TAG.format(side=names[fid])}{text}"  # 三方混戰多一格守軍（裁決 22）
                for fid in battle_instance.fields(battle, definition) if (text := generals.lineup(battle, fid))]
        order = battle_instance.order_text(battle, side, self.content.config.battle) if side is not None else ""
        return ["\n".join(rows)] + ([order] if order else [])

    def _round_blocks(
        self, battle: battle_instance.BattleInstance, definition: BattleDef, *, last: int | None = ROUND_BLOCKS,
        oldest_first: bool = False, me: battle_instance.BattleParticipant | None = None,
    ) -> list[str]:
        """場景上最近五段戰況，一回合一段、新的在上（Joy 2026-10-14「大決戰因為很多人，戰況文字沒有分回合，擠在一起玩家很難閱讀」）：
        每一段是「##### 第 N 回合」加一行一條的清單，網頁照標題把舊的幾回合收成一行（app.js 的 roundBlocks）。
        narrative_log 開打那一句之後一回合一筆（apply_battle_tales 也照這個算），所以倒數第 k 筆是第（round_number − k）回合；
        開打那一句（第 0 筆）照舊一段話。每一條是哪一軍的（Joy 2026-10-14「看不出誰是官軍誰是黃巾」）：開頭是參戰者的名號就照他
        站的那一邊，開頭是交戰一方的名字就是那一方，前面加「〔官軍〕」（SIDE_TAG；網頁 roundBlocks 換成那一軍顏色的小標籤）；
        誰佔上風、各路奇招互相牽扯、換幕這幾句不分邊，不加。
        收場時寫進自己戰報的那一份（Joy 2026-10-14「決戰能不能把完整戰報在戰報那邊可以展開」，_file_showdown）：last 是 None＝整場、
        oldest_first 照先後、me 是自己，每一段最後一條寫自己這一回合出了什麼（MY_MOVE）。"""
        log = battle.narrative_log
        sides = battle_instance.side_names(battle, definition)  # 單方攻中立地時守將那一格寫〔守軍〕（FB-540）
        owner = {c.name: c.faction for c in battle.commanders} | {n: q.faction for n, q in battle.participants.items()}
        names = sorted(owner, key=len, reverse=True)  # 名號長的先比：「沈浪」不能先認走「沈浪子」

        def side_of(item: str) -> str:
            if item.startswith(tactics.LEAD) and "〕" in item:  # 招那一句「〔招名〕某某……」：照招名後面的名號認
                item = item.split("〕", 1)[1]
            who = next((n for n in names if item.startswith(n)), None)
            fid = owner[who] if who is not None else next((f for f, nm in sides.items() if item.startswith(nm)), None)
            return SIDE_TAG.format(side=sides[fid]) if fid in sides else ""
        out = []
        for k, entry in enumerate(reversed(log if last is None else log[-last:])):
            n = battle.round_number - k
            rows = [line for line in entry.split("\n") if line.strip()]
            if n <= 0 or not rows:
                out.append(entry)
                continue
            items: list[str] = []
            for line in rows:  # 誰放手一搏寫了什麼、接著那一句成敗，併成同一條（人多時一眼看得出哪一句是誰的）
                if items and GAMBLE_SAID in items[-1] and "\n" not in items[-1] and GAMBLE_SAID not in line:
                    items[-1] += f"\n  {line}"
                else:
                    items.append(line)
            mine = [MY_MOVE.format(move=me.moves[n])] if me is not None and n in me.moves else []
            rows_md = self._fold_war_lines(battle, items, sides, owner, names, side_of)
            out.append(f"{ROUND_HEAD.format(n=n)}\n\n" + "\n".join([*rows_md, *(f"- {m}" for m in mine)]))
        return out[::-1] if oldest_first else out

    def _fold_war_lines(self, battle: battle_instance.BattleInstance, items: list[str], sides: dict[str, str],
                        owner: dict[str, str], names: list[str], side_of) -> list[str]:
        """一回合的每一條寫成清單的一列（「- 〔官軍〕……」）；一軍發動戰法的那幾句（〔招名〕開頭，自己的不算）有 WAR_FOLD_MIN 句以上就在
        第一句的位置換成一列摘要「官軍本回合 9 人發動武學：回氣血 4、加重 2」，那幾句縮排成它底下的一層（網頁畫成點開才看）。"""
        me = self.state.player.name
        label = {kind: name for name, kinds in WAR_FOLD_KINDS.items() for kind in kinds}
        # 這一場記下的（tactic_kinds）為準；這一版以前打的場沒記，照內容武學的戰法與功效補（玩家取了名的招認不出來，歸「其他」）
        book = self.content.traits
        known = {sk.tactic.name: sk.tactic.kind for sk in self.content.skills.values() if sk.tactic is not None}
        known |= {t.name: t.tactic.kind for t in [*book.general, *book.special, *book.high] if t.tactic is not None}
        known |= battle.tactic_kinds
        groups: dict[str, list[tuple[str, str]]] = {}  # 陣營 → [(誰, 那一句)]
        for item in items:
            if not item.startswith(tactics.LEAD) or "〕" not in item:
                continue
            body = item.split("〕", 1)[1]
            who = next((x for x in names if body.startswith(x)), None)
            if who is None or who == me or owner.get(who) not in sides:
                continue
            groups.setdefault(owner[who], []).append((who, item))
        folded = {fid: rows for fid, rows in groups.items() if len(rows) >= WAR_FOLD_MIN}
        taken = {item: fid for fid, rows in folded.items() for _, item in rows}
        out: list[str] = []
        for item in items:
            if item not in taken:
                out.append(f"- {side_of(item)}{item}")
                continue
            rows = folded.pop(taken[item], None)
            if rows is None:  # 這一軍的摘要已經寫過了
                continue
            kinds = [known.get(line[len(tactics.LEAD):].split("〕", 1)[0]) for _, line in rows]
            counts: dict[str, int] = {}
            for kind in kinds if any(kinds) else []:  # 一句都認不出來（舊的場、全是自創的招）：只寫幾個人，不分類
                name = label.get(kind or "", "其他")
                counts[name] = counts.get(name, 0) + 1
            order = [*WAR_FOLD_KINDS, "其他"]
            parts = "、".join(f"{k} {counts[k]}" for k in order if k in counts)
            fid = taken[item]
            head = WAR_FOLD.format(side=sides[fid], n=len({who for who, _ in rows})) + (f"：{parts}" if parts else "")
            out.append(f"- {SIDE_TAG.format(side=sides[fid])}{head}")
            out.extend(f"    - {line}" for _, line in rows)
        return out

    def _idle_note(self, battle: battle_instance.BattleInstance) -> list[str]:
        """掛機的人自己看到的那一句（Joy 2026-10-10 掛機懲罰），放在戰場名字底下第一行。"""
        p = battle.participants.get(self.state.player.name)
        if p is None or p.eliminated or battle.phase != "active":
            return []
        if battle_instance.idle(p):
            return ["**你上一回合沒出手**，系統替你固守了；這一回合大家不等你，按任何一招就不算掛機。"]
        return []

    def _battle_spotlight(
        self, battle: battle_instance.BattleInstance, definition: BattleDef, p: battle_instance.BattleParticipant,
    ) -> list[str]:
        """點名與顯眼（Joy 2026-10-10）：上一回合誰盯上了你、你被牽制了沒有、這一幕還能不能放手一搏、你是不是顯眼的人；倒下的人只剩
        璽動那一場「戰功居前」那一句（FB-177：挑挑戰者不看倒下，畫面照同一條），其餘跟倒下無關的不寫。"""
        if battle.phase != "active":
            return []
        merit = battle.seal_shard and p.name in seal.hint_names(battle, self.content, seal.holders(self.world.seal_state().registry))
        if p.eliminated:
            return [seal.merit_hint(self.content)] if merit else []
        out = []
        hunters = battle.last_targets.get(p.name)
        if hunters:
            out.append(f"{'、'.join(hunters)}盯上了你。")
        if battle_instance.pinned(battle, p):
            out.append("你被牽制住了，這一回合只能固守。")
        elif definition.free_text_gamble is not None and not battle_instance.can_gamble(battle, definition, p):
            out.append("這一幕你已經放手一搏過了，下一幕才能再搏。")
        if battle.marked.get(p.name) == battle.act_index:
            out.append("你在這一幕太顯眼了，對面的強攻會往你身上招呼。")
        if merit:
            out.append(seal.merit_hint(self.content))  # 璽動那一場戰功居前（4.3）：不露數字、不露名次；改版兩軍都給、字有條件
        return out

    def _round_wait(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> str:
        """「已送出 X／在場 Y，最遲 M 分 S 秒後結算」：在場的人都送出就提早結算，不然等這一回合逾時（暫停中停在按下暫停那一刻）。"""
        sent, present = battle_instance.round_progress(battle, definition)  # 跟結算等的是同一批人
        idlers = battle_instance.idle_count(battle, definition)  # 掛機的不等（Joy 2026-10-10），另外寫
        paused = self.world.paused_at()
        left = max(0, int(battle.round.opened_real + definition.round_seconds - (self.now if paused is None else paused)))
        due = f"最遲 {left // 60} 分 {left % 60} 秒後結算" if left else "時間到了，即將結算"
        return f"已送出 {sent}／在場 {present}" + (f"（掛機 {idlers} 人不等）" if idlers else "") + f"，{due}"

    def _battle_menu(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> list[Option]:
        """戰鬥那一段選單：自己大區裡打得進去的只有一場（或已經在名單上、在挑同伴）照舊（_battle_options，鈕 id 一字不變）；
        兩場以上（攻城戰與決戰、或兩場攻城，領地爭奪第二批 Review Focus 4）每一場各一組加入鈕，id 帶「@流水號」、字前面寫是哪一場。"""
        joinable = self._joinable()
        if len(joinable) < 2 or self.state.player.escort_pick:
            return self._battle_options(battle, definition)
        out = []
        for b in joinable:
            d = self._definition_of(b)
            for o in self._battle_options(b, d):
                out.append(o.model_copy(update={"id": f"{o.id}@{b.record_id}", "label": f"{d.name}：{o.label}"}))
        return out

    def _battle_options(self, battle: battle_instance.BattleInstance, definition: BattleDef) -> list[Option]:
        """打得了這場仗的人的戰鬥選項（只能觀戰的人不會走到這裡，見 _watching_battle）。"""
        name = self.state.player.name
        p = battle.participants.get(name)
        if p is None and allied.needs_ally(self.state, self.content):  # 拜入曹氏莊院還沒挑一邊（FB-273）：先挑一邊，不給加入也不給投效
            return []
        if p is None and self.state.player.escort_pick and self._escort_choices():  # 按了加入、在挑誰隨你上陣（歷史武將同行）
            return self._escort_options()
        if self._free_agent(definition):  # 散人、豪強：集結時、或開打了還沒參戰，給臨時投效的兩顆
            if battle.phase == "muster" or p is None:
                return self._enlist_options(battle, definition)
        if battle.phase == "muster":
            sides = list(self._sides(definition).items())  # 兩軍（id, 名字）
            if self.content.scenario.factions:  # 劇本分陣營：只能站在自己陣營那邊
                sides = [(fid, fname) for fid, fname in sides if fid == self._side()]  # 豪強分屬兩軍：依附那一軍
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
            return [Option(id="battle:waiting", label=f"（已選擇，等其他人：{self._round_wait(battle, definition)}）", enabled=False)]
        out = []
        for o in battle_instance.options_for(battle, definition, name):
            if o.free_text:
                continue
            label = o.text
            ordered = o.move is not None and o.move == battle.orders.get(p.faction) and battle_instance.caller(battle, p.faction) is not None
            if p.faction == battle_instance.GUARD and o.move is not None:  # 三方混戰助守的人：份量不推戰線，不寫分數與將令（裁決 22）
                label = f"{o.text}（{o.move}）"
            elif o.move is not None and p.scores:  # 三招：寫招與這個人現在的份量（設計 3.4：按鈕上直接寫）
                score = p.scores.get(o.move, 0.0) * battle_instance.condition(p)
                if ordered:  # 照將令出招（龍頭上陣）：份量照算進去
                    score *= 1 + self.content.config.battle.generals.order_bonus
                label = f"{o.text}（{o.move}・{round(score)} 分{battle_instance.ORDER_MARK if ordered else ''}）"
            elif o.move is not None:  # 還沒有份量快照（上線前就在場上、下一次同步才補）：不寫「0 分」，那是假的
                label = f"{o.text}（{o.move}）"
            out.append(Option(id=f"battle:act:{o.tag}", label=label))
        return out

    def event_free_text_prompt(self) -> str | None:
        """眼前的事件可以隨口應對時回傳提示語（選單上那一顆的標籤），否則 None；server.py 用它決定輸入框。"""
        event_id = self.state.pending_event
        free = None if event_id is None else self._free_text_of(self.content.events[event_id])
        return None if free is None else free.prompt

    def battle_free_text_prompt(self) -> str | None:
        """這回合是否有自訂行動的輸入框可以用，有的話回傳提示語（見 BattleOption.free_text
        ——設計討論：魯莽這類選項該是玩家自己想出來的招，不是從清單挑一個）；沒有（不在
        戰鬥中、集結期、已經出局、這回合已經選過）就回傳 None，server.py 用這個決定輸入框
        要不要顯示。序章裡沒有（_battle_for_me）。"""
        status = self._battle_for_me(tick=False)
        if status is None:
            return None
        battle, definition = status
        name = self.state.player.name
        p = battle.participants.get(name)
        if battle.phase != "active" or p is None or p.eliminated or p.away or name in battle.round.pending_actions:
            return None
        option = next((o for o in battle_instance.options_for(battle, definition, name) if o.free_text), None)
        return option.text if option else None

    # 放手一搏輸入框旁邊那一句（試玩回饋 2026-10-08）：成功率照舊不事前顯示（賭局的感覺），只講清楚賭的是什麼
    BATTLE_GAMBLE_NOTE = "寫得越險，成了戰果越大；失手時大局只會小小倒退，重傷的是你自己，氣血見底就倒下出局。"

    # 氣血池撐不過一次最壞的失手時多這一句（長社火攻 14 個真人倒下 12 個，都是自己放手一搏失手扣光的；PM 2026-10-15）。
    # 不寫數字
    BATTLE_GAMBLE_LAST = "你的氣血已經撐不住再一次失手——這一搏若是沒成，你就倒下了。"

    def battle_free_text_note(self) -> str | None:
        """有放手一搏輸入框時（battle_free_text_prompt 不是 None）回傳輸入框旁邊的說明，否則 None；
        再失手一次就會倒下時（battle_instance.one_miss_left）後面多 BATTLE_GAMBLE_LAST。"""
        if self.battle_free_text_prompt() is None:
            return None
        battle, definition = self._battle_for_me(tick=False)
        p = battle.participants[self.state.player.name]
        if definition.free_text_gamble is not None and battle_instance.one_miss_left(p, definition.free_text_gamble):
            return f"{self.BATTLE_GAMBLE_NOTE}{self.BATTLE_GAMBLE_LAST}"
        return self.BATTLE_GAMBLE_NOTE

    def _battle_text_check(self, text: str, tick: bool) -> tuple[BattleDef, str, str, str] | list[str]:
        """放手一搏現在送不送得出去：送得出去回傳（這場的定義, 選項的 tag, 截到 20 字的文字, 自己站的那一方的名字），
        不行回傳要給玩家看的那一句。tick 照 _battle_status。"""
        if self.world.paused_at() is not None:  # 不走 choose()：暫停中自己擋，不然送出去會把這一回合結算掉
            return [f"（{PAUSED_TEXT}。）"]
        status = self._battle_for_me(tick=tick)  # 序章裡送不出去（FB-113）
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
        faction_name = battle_instance.side_names(battle, definition).get(p.faction, p.faction)  # 助守中立地寫守軍（FB-540）
        return definition, option.tag, text, faction_name

    def battle_text_request(self, text: str) -> BattleTextRequest | list[str]:
        """放手一搏的階段 A（server.py 在行動鎖內、很快地呼叫）：送得出去就回傳要在鎖外送模型評成功率的單子，不行回傳那一句話。
        只讀，不推進戰鬥（同 free_text_request）。"""
        checked = self._battle_text_check(text, tick=False)
        if isinstance(checked, list):
            return checked
        definition, _, text, faction_name = checked
        battle = self._battle_now()
        return BattleTextRequest(
            battle_id=definition.id, act_index=battle.act_index, faction_name=faction_name, text=text,
            name=self.state.player.name, sex=gender.of(self.state),
            target=battle_instance.target_line(battle, definition, self.state.player.name, text, self.content.config.battle),
        )

    def submit_battle_custom_action(
        self, text: str, llm_rate: int | None = None, stories: tuple[str, str] | None = None,
    ) -> list[str]:
        """自訂行動輸入框的送出：截到 20 字，查到這回合對應的 free_text 選項，機制效果
        還是走它的 tag（跟按按鈕完全一樣的查表邏輯），玩家打的字只會被餵給 LLM 評成功率。
        這裡用 tick=True（不是 tick=False）——跟 _battle_choose() 不一樣，這個方法不是
        透過 choose() 進來的，choose() 開頭那次 self.options(odds=False) 呼叫順便推進
        過一次集結逾時/回合逾時的保護在這裡沒有發生過，這個方法是自己的入口，必須自己
        負責先追趕一次，不然集結剛好逾時的那一刻送出的行動會在 submit_action() 裡被
        「battle.phase 還是 muster」悄悄吃掉（見那次遇到的真實 bug）。
        llm_rate 是 server.py 在行動鎖外評好的成功率（battle_text_request 開的單子；試玩回饋 2026-10-08：鎖內等模型全服跟著等）；
        沒給（直接呼叫的測試、腳本）就在這裡評，用 _quick_client 的短逾時複本，評不到就是保底值。
        stories 是同一次模型呼叫寫好的（成功版, 失敗版）劇情（battle_instance.assess_gamble）；擲骰後播對應的那一版。"""
        checked = self._battle_text_check(text, tick=True)
        if isinstance(checked, list):
            return checked
        definition, tag, text, faction_name = checked
        if llm_rate is None:
            battle = self._battle_now()
            act = battle_instance.current_act(battle, definition)
            target = battle_instance.target_line(battle, definition, self.state.player.name, text, self.content.config.battle)
            verdict = battle_instance.assess_gamble(
                self._quick_client(), act, faction_name, text, self.state.player.name, target=target, sex=gender.of(self.state),
            )
            llm_rate, stories = verdict.rate, (verdict.win, verdict.lose)
        return self._submit_battle_action(
            self.state.player.name, definition, tag, text, llm_rate, stories, sex=gender.of(self.state),
        )

    def battle_tale_request(self) -> BattleTaleRequest | None:
        """回合結算後補放手一搏劇情的 A 段（server.narrate_battle 在行動鎖內、很快地呼叫）：這一場有等著補劇情的放手一搏，
        回傳最早那一回合的一批（battle_instance.tales_due）；沒有回 None。只讀。有攻城戰時（領地爭奪第二批）決戰先、再照攻城的先後，
        第一場有等著補的那一場（收場了、還沒在每天結算時拿掉的攻城也算：最後一回合的劇情收場之後才寫好）。"""
        battle = next((b for b in self._tale_battles() if b.tales and b.battle_id in self.content.battles), None)
        if battle is None:
            return None
        definition = self._definition_of(battle)
        due = battle_instance.tales_due(battle)
        names = battle_instance.side_names(battle, definition)  # 助守中立地寫守軍（FB-540）
        return BattleTaleRequest(
            battle_id=battle.battle_id, record_id=battle.record_id, opened=battle.muster_deadline_real,
            act_index=min(due[0].act_index, len(definition.acts) - 1),
            items=[battle_instance.TaleItem(
                name=t.name, faction_name=names.get(t.faction, t.faction), text=t.text, won=t.won, target=t.target, sex=t.sex,
            ) for t in due],
            done=[(t.round, t.name) for t in due],
        )

    def apply_battle_tales(self, request: BattleTaleRequest, stories: dict[str, str]) -> int:
        """補劇情的 C 段：還是同一場才補（battle_instance.apply_tales）；回傳補了幾句。換了一場（收場後開了下一場）什麼都不動。
        有攻城戰時照流水號找那一場（決戰或攻城）。"""
        battle = next((b for b in self._tale_battles() if b.record_id == request.record_id), None)
        if battle is None or (battle.battle_id, battle.record_id, battle.muster_deadline_real) != (
            request.battle_id, request.record_id, request.opened,
        ):
            return 0
        patched = {"n": 0}

        def _apply(b: battle_instance.BattleInstance) -> None:
            patched["n"] = battle_instance.apply_tales(b, request.done, stories)

        self._mutate_battle_of(battle, _apply)
        return patched["n"]

    def _tale_battles(self) -> list[battle_instance.BattleInstance]:
        """補放手一搏劇情看的那幾場：決戰那一格，加上共用狀態裡的攻城（收場了、還沒在每天結算時拿掉的也算）；沒開領地爭奪只有決戰。"""
        showdown = self.world.get_battle()
        sieges = self.world.get_sieges() if conquest.on(self.content, self.state.world) else []
        return ([showdown] if showdown is not None else []) + sieges

    def _battle_choose(self, arg: str) -> list[str]:
        """choose() 分派進這裡之前，已經透過自己開頭那次 self.options(odds=False) 呼叫
        推進過一次了（options() 內部會 tick），這裡用 tick=False 只讀，避免同一次請求裡
        重複推進兩次。序章裡一律擋下（_battle_for_me，FB-113）：選單上本來就沒有，直接送也不行。
        鈕 id 帶「@流水號」（同一個大區有兩場以上打得進去，領地爭奪第二批 Review Focus 4）：這一下照那一場；已經在別場的名單上不收。"""
        arg, at, ref = arg.partition("@")
        if not at:
            return self._battle_choose_in(arg)
        if not ref.isdigit():
            return ["（此刻無法這麼做。）"]
        name = self.state.player.name
        if any(name in b.participants and b.record_id != int(ref) for b in self.battles_now() if b.phase != "ended"):
            return ["（你已經在另一場戰局裡。）"]
        self._battle_ref = int(ref)
        try:
            return self._battle_choose_in(arg)
        finally:
            self._battle_ref = None

    def _battle_choose_in(self, arg: str) -> list[str]:
        """_battle_choose 的本體（看的那一場已經照 @流水號 定好）。"""
        status = self._battle_for_me(tick=False)
        if status is None:
            return ["（此刻無法這麼做。）"]
        battle, definition = status
        name = self.state.player.name
        kind, _, rest = arg.partition(":")
        # 已經報名的人在區內走動時改選陣營不是「加入」，不用再驗人在不在戰場（_at_battle 在路上一律是否）
        changing_sides = kind == "join" and name in battle.participants
        if kind == "enlist":
            changing_sides = name in battle.participants
        if kind in ("join", "join_late", "enlist") and not changing_sides and not self._at_battle(definition):
            return [f"（{self._absent_reason(definition)}。）"]
        if kind == "escort":
            return self._escort_step(battle, rest)
        guarding = kind == "enlist" and rest.partition("@")[0] == battle_instance.GUARD  # 三方混戰助守：同伴只在兩軍那兩格上陣（裁決 22）
        if (kind in ("join", "join_late", "enlist") and not changing_sides and not self._escort_picked and not guarding
                and self._escort_choices()):
            # 名下有同伴：先挑誰隨你上陣（或不派），挑了才加入（歷史武將同行 9.3：沒有預設值）
            refusal = self._join_refusal(kind, rest, definition, battle)
            if refusal is not None:
                return refusal
            self.state.player.escort_pick = f"{kind}:{rest}" + (f"@{self._battle_ref}" if self._battle_ref is not None else "")
            return [ESCORT_PICK]
        if kind == "enlist":
            return self._enlist(battle, definition, rest, changing_sides)
        if kind == "join":
            if self.content.scenario.factions and rest != self._side():
                return ["（你只能站在自己陣營這一邊。）"]
            if battle.siege is not None and (problem := siege.join_problem(self.content, battle.siege, self._conquest_side(), rest)):
                return [problem]
            scores = self._mandate_weight(definition, self._battle_scores())  # 在 mutate_battle 之前算好：快照的是加入這一刻、這個玩家自己的份量
            gear, marks = self._battle_gear(), self._battle_marks()
            self._mutate_battle_of(
                battle,
                lambda b: battle_instance.join_faction(
                    b, name, rest, self._battle_neili_cap(), self._battle_power(), scores=scores, attribute=self._battle_road(),
                    role=self._battle_role(), **gear, **marks,
                ),
            )
            msgs = ["你加入了這場戰局。"]
            side = self._sides(definition).get(rest, rest)
            self._write(f"{definition.name}・{'改選' if changing_sides else '加入'}{side}", msgs)  # 加入與改選各留一則（FB-030）
            return msgs
        if kind == "join_late":
            own = self._side() if self.content.scenario.factions else None
            if battle.siege is not None and (problem := siege.join_problem(self.content, battle.siege, self._conquest_side(), own or "")):
                return [problem]
            scores = self._mandate_weight(definition, self._battle_scores())
            gear, marks = self._battle_gear(), self._battle_marks()
            self._mutate_battle_of(
                battle,
                lambda b: battle_instance.auto_assign_latecomer(
                    b, definition, name, self._battle_neili_cap(), self.rng, self._battle_power(), faction=own,
                    scores=scores, attribute=self._battle_road(), role=self._battle_role(), **gear, **marks,
                ),
            )
            msgs = ["你趕到了戰場，這一回合就能出手。"]  # 晚到的人當回合就能出招（FB-028）
            self._write(f"{definition.name}・趕到戰場", msgs)  # 趕到也留一則（FB-030）；每回合的出招不寫，太吵
            return msgs
        if kind == "act":
            self._backfill_battle_scores()  # 還沒有份量快照的自己，出招之前先補（結算要讀）
            return self._submit_battle_action(name, definition, rest)
        return ["（此刻無法這麼做。）"]

    def _join_refusal(
        self, kind: str, rest: str, definition: BattleDef, battle: battle_instance.BattleInstance | None = None,
    ) -> list[str] | None:
        """加入、臨時投效這一下本身就不成的那一句（同 _battle_choose、_enlist 的擋法）：挑同伴之前先擋，免得挑完了才說不行。
        攻城戰（領地爭奪第二批）另照 siege.join_problem（另一軍站不進守將那一格）。"""
        if kind == "join" and self.content.scenario.factions and rest != self._side():
            return ["（你只能站在自己陣營這一邊。）"]
        if kind == "enlist" and (not self._free_agent(definition) or rest not in self._enlist_sides(battle, definition)):
            return ["（此刻無法這麼做。）"]
        if battle is not None and battle.siege is not None:
            slot = rest if kind != "join_late" else (self._side() or "")
            problem = siege.join_problem(self.content, battle.siege, self._conquest_side(), slot)
            if problem is not None:
                return [problem]
        return None

    def _enlist(
        self, battle: battle_instance.BattleInstance, definition: BattleDef, side: str, changing_sides: bool,
    ) -> list[str]:
        """散人、豪強臨時投效交戰的一方（_free_agent）：集結時跟加入一樣（還能改投另一邊），開打了照晚到的人算、當回合就能出手。
        參戰名單上記投效的那一方，自己的陣營照舊（散人照舊是散人、豪強照舊是豪強）。"""
        name = self.state.player.name
        armies = self._enlist_sides(battle, definition)  # 三方混戰多一格助守【守軍】（裁決 22）
        if not self._free_agent(definition) or side not in armies:
            return ["（此刻無法這麼做。）"]
        if battle.siege is not None and (problem := siege.join_problem(self.content, battle.siege, self._conquest_side(), side)):
            return [problem]
        if changing_sides and battle.phase != "muster":
            return ["（開打之後就不能改投了。）"]
        scores, cap, power, road = self._mandate_weight(definition, self._battle_scores()), self._battle_neili_cap(), self._battle_power(), self._battle_road()
        role = self._battle_role()
        gear, marks = self._battle_gear(), self._battle_marks()
        if side == battle_instance.GUARD:  # 三方混戰助守：同伴只在兩軍那兩格上陣，這一場不帶（裁決 22）
            marks["escort"] = None
        if battle.phase == "muster":
            self._mutate_battle_of(
                battle,
                lambda b: battle_instance.join_faction(
                    b, name, side, cap, power, scores=scores, attribute=road, role=role, **gear, **marks,
                ),
            )
            msgs = [f"你臨時投效了{armies[side]}，只算這一場：打完你照樣是{self._own_side_name()}。"]
        else:
            self._mutate_battle_of(
                battle,
                lambda b: battle_instance.auto_assign_latecomer(
                    b, definition, name, cap, self.rng, power, faction=side, scores=scores, attribute=road, role=role,
                    **gear, **marks,
                ),
            )
            msgs = [f"你臨時投效了{armies[side]}，趕到了戰場，這一回合就能出手；打完你照樣是{self._own_side_name()}。"]
        if side == battle_instance.neutral_guard(battle):  # 助守中立地的守將：不寫那一格的陣營（FB-540）
            place = self.content.locations[battle.siege.loc].name
            line = siege.HELP_GUARD_LINE if battle.phase == "muster" else siege.HELP_GUARD_LATE
            msgs = [line.format(place=place, own=self._own_side_name())]
            self._write(f"{definition.name}・{siege.HELP_GUARD_SWITCH if changing_sides else siege.HELP_GUARD_TITLE}", msgs)
            return msgs
        self._write(f"{definition.name}・{'改投' if changing_sides else '臨時投效'}{armies[side]}", msgs)
        return msgs

    def _submit_battle_action(
        self, name: str, definition: BattleDef, tag: str, text: str | None = None, success_rate: int | None = None,
        stories: tuple[str, str] | None = None, sex: str | None = None,
    ) -> list[str]:
        """送出一個行動（按鈕選的固定 tag，或自訂輸入框的 free_text 選項，連同 LLM 先評好
        的成功率）並嘗試結算這回合；呼叫端已經確認過戰鬥還在進行（還沒結束），所以這裡
        如果結算完變成 ended，一定是這次送出的行動剛好造成的，不用再跟「結算前是不是
        已經 ended」比對。"""
        captured: dict[str, list[str]] = {"msgs": []}

        def _apply(b: battle_instance.BattleInstance) -> None:
            battle_instance.submit_action(b, name, tag, text, success_rate, stories, sex=sex)
            captured["msgs"] = self._advance_battle_round(b, definition)

        battle = self._mutate_battle_now(_apply)  # 有攻城戰時是自己參戰的那一場（領地爭奪第二批）
        if battle is not None and battle.phase == "ended":
            self._apply_battle_outcome(battle)
        return captured["msgs"] or ["你選擇了行動，等待其他人……"]

    def _recruit(self) -> list[str]:
        target = self._recruit_target()
        if target is None:
            return ["（此地此刻沒有能招募的人。）"]
        return roster.attempt_recruit(self.state, self.content, self.world, target, self.rng)

    def _recruit_one(self, cid: str) -> list[str]:
        """歷史武將同行：招這一位（第三節，照現在的成功率；失敗照舊可能被要求決鬥）。選單上那一顆按得下去才會走到這裡，
        這裡再驗一次：人還在這裡、沒有主、陣營對、名下沒滿。"""
        if cid not in self._recruit_targets():
            return ["（此刻無法這麼做。）"]
        self._settle_partings()  # 9.6：原主人不會因為比別人先上線就用舊情誼搶回來
        problem = roster.recruit_problem(self.state, self.content, self.world, cid)
        if problem is not None:
            return [f"（{problem}。）"]
        return roster.attempt_recruit(self.state, self.content, self.world, cid, self.rng)

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
        if not free and precise.on(c, s.world):  # 一類一顆（2.8【PM】）：沒有同伴可給時不再送 30 心得
            return []
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
        （events.note_round；pick_event 本身不改狀態，預覽怎麼抽都不算）。next_event 串接、晉升召見不是從池子抽的，不給 action。
        重複的事件不請模型補點綴句（2026-10-12 拿掉）：那句在行動鎖裡等模型最多 15 秒、全服跟著等，探索幾乎每次都撞到重複的事件，
        寫出來卻只進 GameState.log（事件文字在紀錄裡是藏起來的、場景照內容原文畫），畫面上從來看不到。"""
        if action is not None:
            event_rules.note_round(self.state, self.content, event, action)
            stance_rules.met(self.state, self.content, event.id)  # 人物心意開的那一則：每人每天一則（減法季批 6 修正輪）
        self.state.pending_event = event.id
        self.state.player.seen_events.add(event.id)
        head = f"✦ 奇遇：{event.title}" if event.qiyu else f"【{event.title}】"
        text = fill_marks(self._event_text(event), self.state)
        self._outcome(journal.event_marker(event.title, event.qiyu), head)
        self._hide(text)
        return [head, text] + foreshadow.hear_from_event(self.state, self.content, event.id, self.world)  # 片段事件（計畫 T7）

    def _event_text(self, event: Event) -> str:
        """事件卡上的旁白（還沒套 fill_marks）：減法季這一週改寫好了就用改寫的（narration.text_of），否則照內容原文。"""
        return narration.text_of(self.content, self.state.world, event, self.state.player.season_number, self.narration)

    def _squad_encounter(self, squad_id: str, wild: bool = False, as_sortie: bool = False) -> list[str]:
        """遭遇一支敵方隊伍：單次判定，勝得對手獎勵，落敗失落一成銀兩；自己陣營的隊伍改成操練（見 _drill）。

        wild：探索時撞上的野怪（探索三選一設計 4.2）——扣氣血打折（`wild_neili_loss_factor`，內傷照比例）、
        打贏**不推大勢**（遊歷推大勢的量已經讓黃巾早早稱霸，探索不能再加碼）；獎勵、掉落、落敗的
        一成銀兩都照常。戰後事件本來就只在 _train 裡接，野怪不走那裡。遊歷不帶這個旗標，一點都不變。
        野怪是當下擲出來的，不問模型、也不吃判讀（武學與成長設計 8.3）；遊歷的大場面吃鎖外的判讀（_judged）。
        as_sortie：出陣的攻（出陣探索與地盤設計 2.2、2.4）——戰報類型 sortie、給自己的照 _sortie_rewards（三成、不給銀兩掉落）、
        不推線，推那一塊的進度（_push_progress）。"""
        s, c = self.state, self.content
        p = s.player
        loc = c.locations[p.location]
        squad = c.squads[squad_id]
        if self._drills_with(squad):
            return self._drill(squad)
        scripted = prologue_rules.fight_tier(s, c)  # 序章雪恥那一場：結果照寫好的，不吃模型的判讀
        judged = None if wild or scripted is not None else self._judged(squad)
        result = self._fight_with(squad, judged, tier=scripted)
        record = battlelog.new_record(s, c, self.world, squad, result, "wild" if wild else "sortie" if as_sortie else "train")
        if prologue_rules.active(s, c) and sortie.on(c):  # 戰報不寫舊名「遊歷」（新手引導重做）
            record.label = sortie.PROLOGUE_FIGHT
        if scripted is None:
            record.notes += self._style_note(squad, result) + self._terrain_note()
        self._narrate(record, result, judged)
        msgs: list[str] = []
        if result.tier in team.WIN_TIERS:
            rewards = self._sortie_rewards(squad, record) if as_sortie else self._battle_rewards(squad, record)
            msgs += rewards
            extra: list[str] = []
            if not wild and not prologue_rules.active(s, c):  # 序章打贏不推大勢、不抽伏筆、不記軍令
                if not as_sortie:  # 出陣不推線（領地爭奪：推那一塊的進度，下面 _push_progress）
                    for trend_id, delta in self.train_trend_push(loc.id).items():  # 換算過的線，照舊交給 T3 的 push_trend
                        extra += self.push_trend(trend_id, delta, source="train")
                credit: list[str] | None = None
                # 領地爭奪：出陣攻打贏推這一塊的進度、不推線（設計 3.7）；約戰開著時這裡只剩截糧（減法季批 3b：進度只在約戰結算動）
                if as_sortie and not self.duel_on():
                    # 軍令照推之前的清單記（FB-608：推滿易手的那一下，推完那一塊已經是自家的、在冷卻，不在攻的清單上）；那一句照舊排在後面
                    credit = self._order_credit(
                        kind="win", location=loc.id, front=front_of(c, loc.id), squad=squad.id, squad_faction=squad.faction,
                    )
                    extra += self._push_progress(loc.id, conquest.sortie_nominal(c, loc.id, "attack"), "sortie", "attack")
                region = atlas.region_of(c, p.location)  # 官銀（伏筆，濃縮版內容表 4.0）：只有遊歷打贏才擲
                extra += foreshadow.after_win(s, c, squad, self.rng, region.id if region is not None else None)
                extra += credit if credit is not None else self._order_credit(  # 軍令（計畫 T6）：攻城看戰線與敵方陣營，截糧看地點與運糧隊
                    kind="win", location=loc.id, front=front_of(c, loc.id), squad=squad.id, squad_faction=squad.faction,
                )
                extra += opportunities.on_win(s, c, front_of(c, loc.id), squad.faction)  # 三路並進（正式版乙二）
                extra += bounties.on_win(s, c, self.world, loc.id, squad.id)  # 懸賞榜的討伐
                if as_sortie:  # 名聲 3.1：出陣攻打贏 +1（遊歷、探索野怪不給）
                    extra += self._deed_fame("sortie")
            changes, notes = battlelog.split_changes(extra, for_record=True)
            record.changes += changes
            record.notes += notes
            msgs += extra
        elif result.tier == "落敗":
            msgs += self._lose_silver(record)
        toll, hp_lost, facts = self._take_toll(result.tier, wild=wild, clash=result.clash)
        record.changes += toll
        msgs += toll
        self._play_rounds(record, squad, result.tier, hp_lost, facts, clash=result.clash)
        msgs += self._seize(record)
        msgs.insert(0, self._file_battle(record))
        if squad.desc:  # 有來歷的對手（運糧隊）多一句描述，接在戰鬥那一行後面
            msgs.insert(1, f"（{squad.name}：{squad.desc}）")
        if not wild and self.is_big(squad):  # 名聲 4.5：天下聞名打大場面點名
            self._famed_news(loc.name, squad.name, result.tier)
        return msgs

    def _drills_with(self, squad: Squad) -> bool:
        """這支隊伍是自己陣營的：遇上了不打，改成一起操練（見 _drill）。"""
        return squad.faction is not None and squad.faction == self.state.player.faction

    def season_scale(self) -> float:
        """季長倍數（FB-165，企劃者 2026-10-12「要隨著賽季長度而調整」）：min(1, Config.drill_push_base_days ÷ 這一季的季長)。
        季長照開季時蓋的章（world_state.season_length_days，季曆用的同一個），不讀電腦時鐘：週末設定（2.5 天）是 1，14 天約 0.18，
        季越長越小。規則關著的季事件的大勢效果照它縮放（push_trend）；操練另見 drill_scale。"""
        days = season_length_days(self.state.world, self.content)
        return min(1.0, self.content.config.drill_push_base_days / days) if days > 0 else 1.0

    def daily_push_cap(self) -> float:
        """每人每曆日每條線推得動多少（第一季，push.split_by_cap 的上限）：Config.daily_push_cap；盡頭阻力開著時再乘季長倍數
        （設計 5.2：週末設定 1，7 天的季約 0.36）。push_trend 與 _push_room 都讀它。"""
        cfg = self.content.config
        if calendar.season21_on(self.state.world, self.content):  # 21 天季：自己的上限，不乘季長倍數（正式季整合設計 7.4）
            return cfg.season21_daily.push_daily_cap
        return cfg.daily_push_cap * (self.season_scale() if cfg.push_resistance.enabled else 1.0)

    def _resisted_lines(self) -> set[str]:
        """盡頭阻力與事件五折只管戰線（設計 5.1、3.2）：三條戰線照這一季的規則換成真的會動的線——第一季是三條戰線本身，
        規則關著的季是它們合成的那一條（黃巾聲勢）。豪強割據、玉璽線索不算。"""
        c, w = self.content, self.state.world
        return {line for front in front_ids(c) if (line := resolve_trend(c, w, front)) is not None}

    def _shaped(self, trend_id: str, delta: float, source: str) -> tuple[float, bool]:
        """玩家這一下真的要推多少（設計 3.2、5.1、5.2）：可重複的事件推戰線打 event_trend_share；第一季的出陣乘季長倍數（規則關著的季
        照舊在 push_trend 那一條縮）；再照推之前的戰線打盡頭阻力。回傳（推的量, 有沒有被阻力打折）。開關都關著時原樣回傳。
        豪強割據往上漲也打盡頭阻力（FB-254，rules.geju_resisted）；推動那一行不接「深入敵境」那一句（說的是戰線）。"""
        c, w = self.content, self.state.world
        cfg = c.config
        amount = float(delta)
        if trend_id == GEJU:
            return geju_resisted(self.state, c, amount), False
        if trend_id not in self._resisted_lines():
            return amount, False
        if source == "event" and cfg.explore_modes.enabled:
            amount *= cfg.explore_modes.event_trend_share
        season21 = calendar.season21_on(w, c)
        if season21 and source in ("sortie", "donate", "event"):  # 21 天季（7.4）：出陣、捐軍備、可重複的事件同一個速度，不乘季長倍數
            amount *= cfg.season21_daily.push_speed
        if not cfg.push_resistance.enabled:
            return amount, False
        if source in ("sortie", "donate") and calendar.season_one_on(w, c) and not season21:  # 捐軍備照出陣（素材與經濟設計第六節第 2 點）
            amount *= self.season_scale()
        share = push.resistance_share(world_trend_value(w, c, trend_id), amount, push.tuning_for(w, c))
        return amount * share, share < 1

    def drill_scale(self) -> float:
        """操練推大勢的倍數：季長倍數；季長倍數小於 1 時再乘 Config.drill_long_season_share（0.5，PM 2026-10-12：操練給的聲勢
        不該佔那麼大）——14 天的季約 0.09；週末設定照舊 1。"""
        scale = self.season_scale()
        return scale * self.content.config.drill_long_season_share if scale < 1 else scale

    def _carry(self, trend_id: str, amount: float) -> int:
        """把縮放後的推力 amount 加進這一季這條線的零頭（WorldState.trend_accum，同一條線一個值、正負抵銷），回傳滿了的整數點數。
        決定性，不擲骰、不動 Game.rng。"""
        w = self.state.world
        whole, rest = push.take_whole(w.trend_accum.get(trend_id, 0.0), amount)
        if rest:
            w.trend_accum[trend_id] = rest
        else:
            w.trend_accum.pop(trend_id, None)
        return whole

    def _drill_push(self, trend_id: str, delta: int) -> list[str]:
        """操練推一條線：照 drill_scale 縮放。倍數是 1（週末設定）時照舊交給 push_trend，一個字都不變；
        第一季的規則開著時縮放後的量照舊經過 push_trend 的人數緩衝、每人每曆日上限與零頭累積；規則關著的季零頭記在這一季的
        trend_accum（_carry），滿一點才真的推、才回推動那一行，沒推到整點的這一下什麼都不寫。"""
        scale = self.drill_scale()
        if scale >= 1:
            return self.push_trend(trend_id, delta, source="drill")
        amount = delta * scale
        if calendar.season_one_on(self.state.world, self.content):
            return self.push_trend(trend_id, amount, source="drill")
        whole = self._carry(trend_id, amount)
        return self.push_trend(trend_id, whole, source="drill") if whole else []

    def _drill(self, squad: Squad) -> list[str]:
        """在自己陣營的地方遊歷：不打自己人，一起操軍擺陣（企劃者 2026-10-02 決定）。不會輸、不扣氣血；
        給經驗與心得，但只給對手的三成（Config.drill_reward_share，戰鬥系統第八節）；不給銀兩、不掉素材（不搶自己人）；
        地點的大勢推動往自己陣營有利的方向推，推的量照季長縮放（_drill_push，FB-165）。"""
        s, c = self.state, self.content
        p = s.player
        loc = c.locations[p.location]
        msgs = [f"你與{squad.name}一同操軍擺陣，軍心為之一振。"]
        self._outcome("操練", msgs[0])
        msgs += self._drill_gains(squad)
        for trend_id, delta in self.train_trend_push(loc.id).items():
            msgs += self._drill_push(trend_id, delta)
        return msgs

    def _drill_gains(self, squad: Squad, share: float | None = None, source: str = "hold", echo: bool = True) -> list[str]:
        """跟這一路一起操練拿的：對手心得與經驗的 share（預設 drill_reward_share；不給銀兩、素材）；經驗本人與帶著的同伴都拿（FB-002）。
        操練（_drill）與出陣的守（_sortie_hold）、守勢行動（_duty）共用；一類一顆開著時守、守勢行動給全額（_hold_share）。
        source（growth.exp_source）：這幾樣都不打仗（hold，PM 2026-10-25 第 5 件）；減法季自家營寨跟同袍比劃算仗（camp_spar）。
        echo：「心得 +N」那一行要不要也放進回傳的訊息。江湖紀錄的標籤本來就由草稿（_draft.changes）記一顆、訊息那一行在敘事裡收掉；
        出門一趟的比劃（_outing_fight）自己有「得：」那一行，兩邊都有就被 _outing_ledger 加成兩倍、後面還多一則單獨的訊息
        （FB-830），所以它傳 False：只由草稿記。沒有草稿時（直接叫的）照樣放進訊息，帳才不會漏掉這一筆。"""
        s, c = self.state, self.content
        p = s.player
        share = c.config.drill_reward_share if share is None else share
        xinde, exp = drill_share(squad.reward_xinde, share), drill_share(squad.exp, share)
        msgs: list[str] = []
        if xinde:
            p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
            xinde_line = f"心得 +{xinde}"
            if echo or self._draft is None:
                msgs.append(xinde_line)
            if self._draft is not None:
                if echo:
                    self._draft.hide(xinde_line)
                self._draft.changes.append(xinde_line)
        keep = team.player_exp(s, c, exp, source)[0]  # 減法季三道閘：不是仗的 45 級以後換心得
        gained = team.maxed_xinde(s, c, exp, source)  # 滿級：本人的經驗照 5 換 1 換成心得（3.5），同伴照拿經驗
        if gained:
            msgs.append(team.xinde_line(c, p.member, gained))
        msgs += team.add_team_exp(s, c, self.world, exp, source)
        if self._draft is not None and exp > 0:
            self._draft.changes += self._exp_changes(exp, keep, gained)
        return msgs

    def _exp_changes(self, exp: int, keep: int, gained: int) -> list[str]:
        """操練這一類（不畫戰報的）經驗寫進江湖紀錄得失的那幾筆：滿級寫「心得 +N」、照常寫「經驗 +N（每人）」（同以前）；
        減法季 45 級的閘換了一截心得時，寫換到的心得與本人真的加的經驗（同伴照拿全額，不寫「每人」）。"""
        if team.maxed(self.content, self.state.player.member):
            return [f"心得 +{gained}"]
        if keep == exp:
            return [f"經驗 +{exp}（每人）"]
        return ([f"心得 +{gained}"] if gained else []) + ([f"經驗 +{keep}"] if keep else [])

    # ── 出陣（出陣探索與地盤設計第二節）：本體在功能包 tianxia/features/sortie/actions.py（主動搬六包第 1 批），這裡留一行委派 ──

    def sorties_left(self) -> int:
        return sortie_actions.sorties_left(self)

    def _sortie_foes(self, loc: Location) -> list[str]:
        return sortie_actions.sortie_foes(self, loc)

    def _sortie_mode(self, loc: Location) -> str | None:
        return sortie_actions.sortie_mode_of(self, loc)

    def sortie_mode(self) -> str | None:
        return sortie_actions.sortie_mode(self)

    def sortie_progress(self, loc_id: str | None = None, how: str | None = None) -> float:
        return sortie_actions.sortie_progress(self, loc_id, how)

    def _push_progress(self, loc_id: str, nominal: float, source: str, how: str | None = None) -> list[str]:
        """領地爭奪：推（攻：自己那一條往上）或拉（守：每一條往下）這一塊的進度（翻地與爭搶，輿圖簡化設計 4.1、4.2）。推多少＝nominal ×
        Config.conquest.progress_scale（出陣）÷ √n（n 同推線的人數緩衝），出陣再乘集火（conquest.focus_bonus）與混戰得勝（_clash_won）；
        事件（source="event"）推 event_progress、不乘 progress_scale、不吃集火、不記出陣那一筆。推不動（conquest.push_problem）是空的。
        出陣照推線那一本帳記貢獻（名目量）、記一筆出陣（conquest.mark：正在推的人、集火、混戰讀它）、進活躍名單。推滿當場易手（conquest.flip）。
        how 沒給照這裡此刻是不是自己的（自己的守、不是的攻）。回那幾句話。"""
        s, c = self.state, self.content
        w, p = s.world, s.player
        side = self._side()
        if side is None:
            return []
        how = how or ("hold" if conquest.holder(w, c, loc_id) == side else "attack")
        if conquest.push_problem(w, c, side, loc_id, how) is not None:
            return []
        cfg = c.config
        window = cfg.active_window_days * DAY / calendar.cal_scale(c, w)
        scale = cfg.conquest.progress_scale if source == "sortie" else 1.0
        # 傳檄（玉璽碎片改版第 2 批）：這一塊算進的那條線有照自家算的傳檄，進度同樣放大（人數緩衝之前）；沒有時一個字都不變
        if (writ := seal_acts.writ_factor(w, c, conquest.line_of(w, c, loc_id), side)) != 1.0:
            scale *= writ
        amount = push.buffered(nominal * scale, push.active_count(s, side, w.time, window))
        notes = ""
        if source == "sortie":
            focus = conquest.focus_bonus(w, c, loc_id, side, p.name)
            if focus:
                amount *= 1 + focus
                notes += conquest.FOCUS_NOTE.format(pct=round(focus * 100))
            if self._clash_won:
                amount *= cfg.conquest.clash_scale
                notes += conquest.CLASH_NOTE
        done = conquest.push(w, c, loc_id, side, p.name, amount, how, notes)
        conquest.tally(w, c, self._pill_day(), side, p.name, done.moved)  # 今天推了多少（出陣回報的小籤）
        if source == "sortie":
            conquest.mark(w, c, loc_id, p.name, side, how, done.moved)
            self._sortie_marked = True
            self._sortie_moved += done.moved
            self._sortie_flipped = self._sortie_flipped or done.flipped
            if calendar.season_one_on(w, c):
                gained = push.contribution(nominal, 1.0, 1.0, cfg.contrib_per_push, cfg.over_cap_contrib_ratio)
                wins.credit(p, c, w, calendar.point(w.time, c, w).week, gained)
        w.active_pushers.setdefault(side, {})[p.name] = w.time
        w.active_pushers = push.drop_stale(w.active_pushers, w.time, window)
        return done.lines

    def _event_progress(self) -> list[str]:
        """領地爭奪：在一塊區塊做完一則事件，往自己那一邊推一次進度（Config.conquest.event_progress；計畫 2.3）：自己的地方是拉、別人的與中立地是推。
        散人、在路上、事件還串著下一則、開關關著、此刻推不動都是空的。"""
        s, c = self.state, self.content
        p = s.player
        if s.pending_event is not None or p.journey is not None or not conquest.on(c, s.world) or p.location is None:
            return self._story_tick()  # 一條線：段落事件了結了，照記下的那一步往下走（下一段就在這裡時直接端出來）
        return self._push_progress(p.location, c.config.conquest.event_progress, "event") + self._story_tick()

    # ── 一條線（特殊事件與特殊頓悟的底座，tianxia/storyline.py；企劃者 2026-10-26）──

    def story_start(self, definition: StoryDef) -> list[str]:
        """程式組的線（例：特殊頓悟）從這裡開：整份 StoryDef 存進進度，第一段是事件、人又在那裡就直接端出來。
        關著、這一季開過同一個 id、這一種沒有空位（Config.jianfa.story_caps）時回空的、什麼都不動。呼叫端自己存檔。"""
        return self._story_begin(definition, custom=True)

    def story_cards(self) -> list[StoryCard]:
        """等著跳出來的卡（開頭、此事已了・入傳、此事未了），照發生的順序。"""
        return list(self.state.player.story_cards)

    def story_seen(self) -> None:
        storyline.seen(self.state)

    def story_card_view(self) -> list[dict]:
        """網頁跳顯框要的那幾張卡（特殊事件設計稿的跳顯框）：sort 是這條線的類別（奇事、頓悟），自訂的線照存檔裡那一份。
        image 是 web/img/ 底下不含副檔名的路徑，圖檔在不在是伺服器的事（同 scene_art）。"""
        p = self.state.player
        out = []
        for card in p.story_cards:
            progress = p.storylines.get(card.line)
            line = storyline.definition(self.content, progress) if progress is not None else self.content.storylines.get(card.line)
            out.append({
                "line": card.line, "kind": card.kind, "sort": line.kind if line is not None else storyline.JOURNAL,
                "title": card.title, "text": card.text, "image": card.image, "ending": card.ending, "failed": card.failed,
            })
        return out

    def event_tier(self) -> dict | None:
        """眼前這一則事件是第二、三階時，場景卡上那一行小字與框色（事件分級設計稿：州郡大事、天下大事）；第一階、沒有事件、
        全服戰鬥蓋著場景都是 None。"""
        s = self.state
        if not s.pending_event or s.world.ended or self._battle_for_me(tick=False) is not None:
            return None
        event = self.content.events.get(s.pending_event)
        if event is None or event.tier <= 1:
            return None
        return {"tier": event.tier, "name": tiers.NAMES[event.tier]}

    def _story_begin(self, definition: StoryDef, custom: bool = False) -> list[str]:
        progress = storyline.start(self.state, self.content, definition, custom=custom)
        if progress is None:
            return []
        head = f"✦ 奇事：{definition.title}"
        self._outcome(journal.event_marker(definition.title, True), head)
        intro = [fill_marks(definition.intro, self.state)] if definition.intro else []
        return [head] + intro + self._story_tick()

    def _story_tick(self) -> list[str]:
        """一條線往前走（storyline.tick）；剛進的那一段是事件、人就在那裡時直接端出來。關著是空的。
        章回主線（chapters）排在前後：先開該開的回、收錯過的回，走完之後把剛走進最後一段的回記成做成（世界的帳改了就存共用的季）。"""
        before = (dict(self.state.world.chapter_done), {k: dict(v) for k, v in self.state.world.chapter_weights.items()})
        head = chapters.tick(self.state, self.content, self.world)
        msgs, event_id = storyline.tick(self.state, self.content, self.world)
        msgs = head + msgs + chapters.after(self.state, self.content)
        if (self.state.world.chapter_done, self.state.world.chapter_weights) != before:
            self._save_season()
        if event_id is not None:
            msgs += self._present(self.content.events[event_id])
        return msgs

    def _story_act(self, arg: str) -> list[str]:
        """按「未了之事」那一顆（story:<線>）：事件段端出事件、答題段出第一題、打一場的段直接打；答題的答案是 story:<線>:a<序號>，
        先擱著是 story:<線>:later。選單上才有這幾顆（choose 先驗過），所以這裡不再驗地方。"""
        s, c = self.state, self.content
        line_id, _, sub = arg.partition(":")
        if sub:
            return storyline.answer(s, c, line_id, sub)
        progress = s.player.storylines[line_id]
        line, stage = storyline.current(c, progress)
        if stage.kind == "event":
            progress.opened = True
            return self._present(c.events[stage.event])
        if stage.kind == "quiz":
            return [f"【{line.title}】"] + storyline.open_quiz(s, c, progress)
        return self._story_fight(progress, stage)

    def _story_fight(self, progress: StoryProgress, stage: StoryStage) -> list[str]:
        """一條線的 fight 段：照劇情戰打（不閃、不扣氣血，同 _event_battle），打完交給 storyline.fought（鉤子寫記號、往 win 或 lose、輸了等再試）。"""
        s, c = self.state, self.content
        if stage.mirror is not None:  # 自己的影子不在內容的隊伍表裡：打這一場的時候借放一下（行動鎖裡，打完就拿掉）
            squad = self._mirror_squad(progress, stage)
            c.squads[squad.id] = squad
            try:
                return self._story_bout(progress, stage, squad)
            finally:
                c.squads.pop(squad.id, None)
        return self._story_bout(progress, stage, self._story_squad(c.squads[stage.squad]))

    def _story_bout(self, progress: StoryProgress, stage: StoryStage, squad: Squad) -> list[str]:
        s, c = self.state, self.content
        judged = self._judged(squad)
        result = self._fight_with(squad, judged, dodge=False, difficulty=squad.difficulty)
        line = storyline.definition(c, progress)
        record = battlelog.new_record(s, c, self.world, squad, result, "event", line.title)
        record.notes += self._style_note(squad, result) + self._terrain_note()
        self._narrate(record, result, judged)
        self._play_rounds(record, squad, result.tier, None, self._hp_facts(), clash=result.clash)
        won = result.tier in team.WIN_TIERS
        rewards = self._battle_rewards(squad, record) if won and stage.mirror is None else []  # 打自己的影子沒有東西掉
        after = storyline.fought(s, c, progress, won, record)  # 打輸、還能再打（心魔未破）：跳卡、記行狀，紀錄多一行
        return [self._file_battle(record)] + rewards + after

    def _mirror_squad(self, progress: StoryProgress, stage: StoryStage) -> Squad:
        """fight 段的對手是自己的影子（StoryStage.mirror，特殊頓悟的心魔）：難度＝你此刻的全隊威力（氣血當滿的、不算地利與碎片，同江湖水漲）
        × mirror，名字是 mirror_name。"""
        base = Squad(id=f"mirror:{progress.line}", name=stage.mirror_name, difficulty=1.0)
        power = team.power_vs(self.state, self.content, self.world, base, fresh=True, terrain=False, seal=False)
        scale = stage.mirror
        if stage.mirror_weaken:  # 重複挑戰時越打越弱（企劃者 2026-10-28）：輸過幾次就削幾次，削到 mirror_floor 為止
            scale = max(stage.mirror_floor, stage.mirror - stage.mirror_weaken * progress.tries)
        return base.model_copy(update={"difficulty": round(max(1.0, power * scale), 1)})

    # ── 混戰（翻地與爭搶，輿圖簡化設計 4.3）、出陣的鈕、出陣、獎勵、守：本體在 tianxia/features/sortie/actions.py，這裡留一行委派 ──

    def _melee_record(
        self, result: encounter.EncounterResult, rival: str, rival_power: float, rival_game: Game, story: str, title: str | None,
    ) -> list[str]:
        return sortie_actions.melee_record(self, result, rival, rival_power, rival_game, story, title)

    def _sortie_option(self, loc: Location, cost: int, odds: bool) -> Option | None:
        return sortie_actions.sortie_option(self, loc, cost, odds)

    def _sortie(self) -> list[str]:
        return sortie_actions.sortie(self)

    def _sortie_rewards(self, squad: Squad, record) -> list[str]:
        return sortie_actions.sortie_rewards(self, squad, record)

    def _famed_news(self, place: str, foe: str, tier: str) -> None:
        """名聲 4.5：天下聞名的人打完大場面（大勢人物本人、劇情裡的頭目、難度 100 以上；單人頭目戰不算），不論勝負，天下大事點名一句；
        一個遊戲日最多 famed_news_per_day 則（不能讓一個人一直打就洗掉別人的消息）。"""
        s, c = self.state, self.content
        if renown.famed_news_due(s, c, game_day(c, s.world)):
            add_rumor(s, renown.NEWS_BIG.format(name=s.player.name, place=place, foe=foe, tier=tier), content=c, layer="world")

    def _deed_fame(self, kind: str) -> list[str]:
        """立功給名望（名聲設計 3.1）：RenownTuning.deeds 的那一項；deed_fame 關著、寫 0 的不給；序章不給。"""
        c = self.content
        n = c.config.renown.deeds.get(kind, 0) if renown.on(c, "deed_fame") else 0
        if n <= 0 or prologue_rules.active(self.state, c):
            return []
        return renown.gain(self.state, c, "fame", n)

    def _sortie_host(self, loc: Location) -> Squad | None:
        return sortie_actions.sortie_host(self, loc)

    def _sortie_hold(self, loc: Location, how: str) -> list[str]:
        return sortie_actions.sortie_hold(self, loc, how)

    def _resisted_line(self) -> str:
        """盡頭阻力打了折的那一下接哪一句（FB-432）：人站在自家陣營控制的地方（守、巡哨、傳道、在自家地盤碰上的事）推過頭是
        STEADY_LINE，其餘（攻、散人、沒有控制方的地方）照舊 RESISTED_LINE。"""
        side, loc = self._side(), self.state.player.location
        mine = side is not None and loc is not None and territory.controller(self.state.world, self.content, loc) == side
        return push.STEADY_LINE if mine else push.RESISTED_LINE

    def _record_exp(self, record, exp: int, source: str = "battle") -> list[str]:
        """這一場本人的經驗寫進戰報（record.exp）：已經滿級時照 5 換 1 換成心得（team.maxed_xinde，3.5），戰報的得失寫心得、
        不寫經驗，回江湖紀錄那一句；沒滿級照舊寫經驗、回空的。經驗本身照舊交給 grant_team_exp／add_exp（滿級的本人不加，同伴照拿）。
        source（growth.exp_source）：減法季三道閘開著時不是仗的經驗過了 45 級那一截也換心得（戰報寫真的加的經驗，回 CAPPED_XINDE 那一句）；
        仗的經驗照舊。"""
        gained = team.maxed_xinde(self.state, self.content, exp, source)
        if not team.maxed(self.content, self.state.player.member):
            record.exp = team.player_exp(self.state, self.content, exp, source)[0]
            if not gained:
                return []
            record.xinde = (record.xinde or 0) + gained
            return [team.CAPPED_XINDE.format(n=gained), f"心得 +{gained}"]
        record.exp = 0
        record.xinde = (record.xinde or 0) + gained
        # 那一句之外另回「心得 +N」：江湖紀錄那一則的心得跟戰報得失對得上，「剛剛」卡片底下不多一顆「心得 -N」（FB-451）
        return [team.MAXED_XINDE.format(n=gained), f"心得 +{gained}"] if gained else []

    # ── 出陣約戰（減法季批 3b；整合設計 4.3，計畫第四節 4.0 之二、之三）──────────────
    # 貼（sortie_go）、應戰（sortie_answer）、同去（sortie_join）各在一次 world.mutate 裡重驗再寫（先按的那一位才進得去）；窗滿了伺服器排程、
    # 任何人的同步、假人程式誰先到誰結算（_sortie_duel_tick → sortie_duel.advance，只往前走），結算那一下就把季的進度與兩邊（含同去的）做完。

    def duel_on(self) -> bool:
        """約戰在這一季開著（sortie_duel.on：減法季的 sortie_duel 子開關、出陣、領地爭奪都在這一季生效）。關著一律照舊。"""
        return sortie_duel.on(self.content, self.state.world)

    def answers_left(self) -> int:
        """今天還能應戰幾次（Config.sortie.answer_per_day，跟出陣分開算；換日同出陣）。"""
        return sortie_duel.answers_left(self.state.player, self.content.config.sortie, self._pill_day())

    @staticmethod
    def _duel_power_of(state: GameState, content: Content, world: WorldStateStore) -> float:
        """約戰封招那一刻的威力快照：整隊（本人、出戰的同伴、部下，同出陣打駐軍的算法），對手的屬性不算（計畫 4.0 之三第 7 條）。"""
        members, conditions, boosts = team._fighters(state, content, world)
        return encounter.team_power(members, team.team_arts(state, content, world), None, conditions, boosts)

    def _duel_power(self) -> float:
        return self._duel_power_of(self.state, self.content, self.world)

    def _duel_region(self) -> tuple[str | None, str]:
        """此刻站在哪一個大區（id, 名字）；在路上、地圖沒有大區是 (None, "")。"""
        p = self.state.player
        if p.journey is not None or p.location is None:
            return None, ""
        region = atlas.region_of(self.content, p.location)
        return (region.id, region.name) if region is not None else (None, "")

    def duel_convoy_here(self) -> bool:
        """這週截糧的運糧隊正打這裡經過（orders.extra_enemies）：約戰開著時出陣那一格照舊攻打運糧隊、不貼約戰（設計 4.3）。"""
        p = self.state.player
        if p.journey is not None or p.location is None:
            return False
        return bool(orders.extra_enemies(self.state, self.content, p.location, self._side()))

    def _duel_squad(self, loc_id: str) -> Squad | None:
        """這一塊此刻的駐軍（conquest.sortie_foes，不含運糧隊）裡經驗最高的那一路（同 _sortie_host 的挑法，同分取先列的）：守軍迎戰的威力、
        打贏的戰利、守方贏的經驗心得都照它。貼的那一刻抄進 SortieDuel.report["squad"]。"""
        ids = conquest.sortie_foes(self.state.world, self.content, loc_id, self._conquest_side())
        squads = [self.content.squads[sid] for sid in ids]
        return max(squads, key=lambda q: q.exp) if squads else None

    def sortie_go_problem(self, moves: list[str] | None = None) -> str | None:
        """貼不了約戰的那一句（不含括號；貼得了是 None）：暫停、休季、三招不對（給了 moves 才驗）、散人、在路上、不是區塊、今天的次數、冷卻、
        這一塊推不動（自家的寫「等對面來約」，sortie_duel.open_problem）、體力。"""
        s, c = self.state, self.content
        p, cfg = s.player, c.config.sortie
        if self.world.paused_at() is not None:
            return PAUSED_TEXT
        if s.world.ended:
            return sortie_duel.WHY_RESTING
        if moves is not None and (why := sortie_duel.moves_problem(cfg, moves)) is not None:
            return why
        side = self._conquest_side()
        block_why = None
        if side is not None and p.journey is None:
            if p.location not in conquest.blocks(c):
                block_why = sortie_duel.WHY_NOT_BLOCK
            else:
                block_why = conquest.push_problem(s.world, c, side, p.location, "attack")
        return sortie_duel.open_problem(
            cfg, self.now, side=side, left=self.sorties_left(), cooldown_until=p.sortie_cooldown_until, block_why=block_why,
            stamina=p.stamina, traveling=p.journey is not None,
        )

    def _duel_option(self, loc: Location) -> Option | None:
        """約戰開著時出陣那一格（id 照留 act:train，計畫 4.0 之三第 2 條）：散人、不是區塊、別人搶不下來的區塊是 None（options 照舊寫散人、
        不在爭奪之列）；截糧的運糧隊經過時照舊攻打運糧隊；其餘按了只打開出陣前那張卡（不花體力），貼不了時灰著寫原因。"""
        s, c = self.state, self.content
        side = self._conquest_side()
        if side is None or loc.id not in conquest.blocks(c):
            return None
        cfg = c.config.sortie
        left = self.sorties_left()
        if self.duel_convoy_here():
            if left <= 0:
                return Option(id="act:train", label=f"{sortie.NAME}（{sortie.USED_UP.format(n=cfg.jianfa_per_day)}）", enabled=False)
            return self._cost_option("act:train", f"{sortie.NAME}・{sortie_duel.CONVOY_NAME}", cfg.jianfa_stamina,
                                     note=sortie.LEFT_NOTE.format(n=left))
        if not conquest.capturable(c, loc.id):
            if conquest.holder(s.world, c, loc.id) != side:
                return None
            return Option(id="act:train", label=f"{sortie.NAME}（{sortie.OUT_NOTE}）", enabled=False)  # 自家的大本營、廣宗
        problem = self.sortie_go_problem()
        if problem is not None and problem != sortie_duel.WHY_TIRED.format(n=cfg.jianfa_stamina):
            # 格子只放得下四個字（FB-670）：整句在行動列底下那一行（_duel_line）與卡上的 why_not
            return Option(id="act:train", label=f"{sortie.NAME}（{sortie_duel.cell_note(problem)}）", enabled=False)
        return self._cost_option("act:train", sortie.NAME, cfg.jianfa_stamina, note=sortie.LEFT_NOTE.format(n=left))  # 體力不夠照別格灰

    def _duel_line(self, loc: Location) -> str:
        """約戰開著時行動列底下出陣那一行（howto.duel_line）：散人、不在爭奪之列照舊；截糧、貼得了、等對面來約、其他原因各一句。"""
        if self._conquest_side() is None or (
                not conquest.capturable(self.content, loc.id) and conquest.holder(self.state.world, self.content, loc.id) != self._conquest_side()):
            return self._sortie_line(loc)
        if loc.id in conquest.blocks(self.content) and not conquest.capturable(self.content, loc.id) and not self.duel_convoy_here():
            return sortie.OUT_LINE  # 自家的大本營、廣宗：不在爭奪之列
        return howto.duel_line(self.content, self.sortie_go_problem(), self.sorties_left(), self.answers_left(),
                               convoy=self.duel_convoy_here())

    def _duel_entry(self) -> list[str]:
        """約戰開著時按出陣那一格（act:train）：截糧的運糧隊經過時攻打運糧隊（扣一次出陣與 jianfa_stamina，照舊打一場、算截糧，約戰開著時出陣
        不推進度）；其餘只打開出陣前那張卡（sortie_duel.PICK，不花體力、不寫紀錄，同探索的入口）。"""
        s, c = self.state, self.content
        if not self.duel_convoy_here():
            return [sortie_duel.PICK]
        p = s.player
        p.stamina -= c.config.sortie.jianfa_stamina
        sortie.spend(p, self._pill_day())
        squad = orders.extra_enemies(s, c, p.location, self._side())[0]
        return self._squad_encounter(squad, as_sortie=True) + self._guide(note_action(s, c, self.world, "order"))

    def _duel_choice(self, option_id: str) -> list[str]:
        """sortie:go:<三招>、sortie:answer:<約戰 id>:<三招>、sortie:join:<約戰 id>（choose 最前面接走的）。"""
        verb, _, rest = option_id.removeprefix(sortie_duel.PREFIX).partition(":")
        if verb == "go":
            return self.sortie_go(rest)
        if verb == "answer":
            duel_id, _, moves = rest.rpartition(":")
            return self.sortie_answer(duel_id, moves)
        if verb == "join":
            return self.sortie_join(rest)
        return self._log(["（此刻無法這麼做。）"])

    def _duel_who(self, side: str | None) -> str:
        return self.content.scenario.faction_name(side, side or "")

    def sortie_go(self, moves) -> list[str]:
        """貼約戰（MAIN_ACTIONS 的 sortie_go、選項 sortie:go:<三招>；設計 4.3）：重驗（sortie_go_problem）之後在 world.mutate 裡貼一張——攻方的快照
        （整隊威力、封好的三招、站的大區）、這一塊的駐軍抄成守軍、駐軍那一路與今天記進 report；扣一次出陣與 jianfa_stamina、寫冷卻、記一則江湖紀錄。"""
        s, c = self.state, self.content
        if not self.duel_on():
            return self._log(["（此刻無法這麼做。）"])
        moves = sortie_duel.parse_moves(moves)
        problem = self.sortie_go_problem(moves)
        if problem is not None:
            return self._log([f"（{problem}。）"])
        p, cfg = s.player, c.config.sortie
        loc = c.locations[p.location]
        side = self._conquest_side()
        region, region_name = self._duel_region()
        squad = self._duel_squad(loc.id)
        garrison = None
        if squad is not None:
            holder = conquest.holder(s.world, c, loc.id) or ""
            garrison = SortieSide(name=squad.name, side=holder, power=float(squad.difficulty), region=region, garrison=True)
        me = SortieSide(name=p.name, side=side, power=self._duel_power(), moves=moves, region=region)
        today = self._pill_day()
        tag = hashlib.sha256(name_key(p.name).encode()).hexdigest()[:8]
        duel_id = f"s{self.world.get_season_number()}-{int(self.now * 1000)}-{tag}"
        refused: list[str] = []

        def _apply(shared) -> None:
            if duel_id in shared.sorties:  # 同一刻按了兩次（兩個分頁）：第二張不貼
                refused.append(sortie_duel.WHY_COOL.format(n=c.config.sortie.cooldown_minutes))
                return
            duel = sortie_duel.open(shared, id=duel_id, block=loc.id, region=region, place=loc.name, region_name=region_name,
                                    attacker=me, now=self.now, cfg=cfg, garrison=garrison)
            duel.report.update({"squad": squad.id if squad is not None else "", "day": today})

        self.world.mutate(_apply)
        if refused:
            return self._log([f"（{refused[0]}。）"])
        sortie.spend(p, today)
        p.stamina -= cfg.jianfa_stamina
        p.sortie_cooldown_until = max(p.sortie_cooldown_until or 0.0, self.now + cfg.cooldown_minutes * 60)
        line = sortie_duel.GO_LINE.format(place=loc.name, side=self._duel_who(side), moves="、".join(moves), window=f"{cfg.window_minutes:g}")
        self._write(sortie_duel.GO_TITLE.format(place=loc.name), [line], tag=sortie_duel.LABEL)
        self._guide(note_action(s, c, self.world, "order"))  # 入伍段「出一次力」：貼一張約戰就算
        return self._log([line])

    def sortie_answer(self, duel_id: str, moves) -> list[str]:
        """應戰（MAIN_ACTIONS 的 sortie_answer、選項 sortie:answer:<id>:<三招>）：在 world.mutate 裡照 sortie_duel.answer_problem 重驗——先按的那一位
        是守方，第二位回「已有人應戰」、什麼都不扣（Review Focus 第 2 條）；成了扣一次應戰與 answer_stamina、記一則江湖紀錄。"""
        s, c = self.state, self.content
        if not self.duel_on():
            return self._log(["（此刻無法這麼做。）"])
        if self.world.paused_at() is not None:
            return self._log([f"（{PAUSED_TEXT}。）"])
        p, cfg = s.player, c.config.sortie
        moves = sortie_duel.parse_moves(moves)
        if (why := sortie_duel.moves_problem(cfg, moves)) is not None:
            return self._log([f"（{why}。）"])
        side = self._conquest_side()
        region, _ = self._duel_region()
        left = self.answers_left()
        power = self._duel_power()  # 封招那一刻的快照（在 mutate 外面算：裡面只讀寫 world 那一列）
        got: list[SortieDuel] = []
        refused: list[str] = []

        def _apply(shared) -> None:
            duel = shared.sorties.get(duel_id)
            why = sortie_duel.WHY_GONE if duel is None else sortie_duel.answer_problem(
                cfg, duel, self.now, name=p.name, side=side, region=region, answers_left=left, stamina=p.stamina,
                cooldown_until=p.answer_cooldown_until, traveling=p.journey is not None,
            )
            if why is not None:
                refused.append(why)
                return
            sortie_duel.answer(duel, SortieSide(name=p.name, side=side, power=power, moves=moves, region=region), self.now)
            got.append(duel.model_copy(deep=True))

        self.world.mutate(_apply)
        if refused:
            return self._log([f"（{refused[0]}。）"])
        duel = got[0]
        sortie_duel.spend_answer(p, self._pill_day())
        p.stamina -= cfg.answer_stamina
        line = sortie_duel.ANSWER_LINE.format(rival=duel.attacker.name, place=duel.place, side=self._duel_who(side), moves="、".join(moves))
        self._write(sortie_duel.GO_TITLE.format(place=duel.place), [line], tag=sortie_duel.LABEL)
        return self._log([line])

    def _duel_join_extra(self, duel: SortieDuel) -> str | None:
        """同去比 sortie_duel.join_problem 多驗的（PM 四之五第 6 件：同去算一次出陣、要站在那一塊所在的大區）：在路上、不在那個大區、
        今天的出陣次數、出陣的冷卻、體力。"""
        p, cfg = self.state.player, self.content.config.sortie
        region, _ = self._duel_region()
        if p.journey is not None:
            return sortie_duel.WHY_ROAD
        if duel.region is not None and region != duel.region:
            return sortie_duel.WHY_FAR.format(region=duel.region_name or duel.region).replace("應得了戰", "同得了去")
        if self.sorties_left() <= 0:
            return sortie.USED_UP.format(n=cfg.jianfa_per_day)
        if sortie_duel.cooling(p.sortie_cooldown_until, self.now):
            return sortie_duel.WHY_COOL.format(n=sortie_duel._minutes_left(p.sortie_cooldown_until, self.now))
        if p.stamina < cfg.jianfa_stamina:
            return sortie_duel.WHY_TIRED.format(n=cfg.jianfa_stamina)
        return None

    def sortie_join(self, duel_id: str) -> list[str]:
        """同去（MAIN_ACTIONS 的 sortie_join、選項 sortie:join:<id>；集火）：在 world.mutate 裡重驗（join_problem＋_duel_join_extra），記進攻方的
        allies；扣一次出陣與 jianfa_stamina、寫冷卻、在那一塊記一筆出陣（conquest.mark，結算時攻方的集火把它算進去）、記一則江湖紀錄。"""
        s, c = self.state, self.content
        if not self.duel_on():
            return self._log(["（此刻無法這麼做。）"])
        if self.world.paused_at() is not None:
            return self._log([f"（{PAUSED_TEXT}。）"])
        p, cfg = s.player, c.config.sortie
        side = self._conquest_side()
        got: list[SortieDuel] = []
        refused: list[str] = []

        def _apply(shared) -> None:
            duel = shared.sorties.get(duel_id)
            why = sortie_duel.WHY_GONE if duel is None else (
                sortie_duel.join_problem(duel, self.now, name=p.name, side=side) or self._duel_join_extra(duel))
            if why is not None:
                refused.append(why)
                return
            sortie_duel.join(duel, p.name)
            got.append(duel.model_copy(deep=True))

        self.world.mutate(_apply)
        if refused:
            return self._log([f"（{refused[0]}。）"])
        duel = got[0]
        sortie.spend(p, self._pill_day())
        p.stamina -= cfg.jianfa_stamina
        p.sortie_cooldown_until = max(p.sortie_cooldown_until or 0.0, self.now + cfg.cooldown_minutes * 60)
        conquest.mark(s.world, c, duel.block, p.name, side, "attack", 0.0)
        self._save_season()
        line = sortie_duel.JOIN_LINE.format(rival=duel.attacker.name, place=duel.place, side=self._duel_who(side))
        self._write(sortie_duel.GO_TITLE.format(place=duel.place), [line], tag=sortie_duel.LABEL)
        self._guide(note_action(s, c, self.world, "order"))
        return self._log([line])

    def _duel_mine(self, duel: SortieDuel) -> bool:
        me = name_key(self.state.player.name)
        if me in {name_key(duel.attacker.name), *(name_key(n) for n in duel.attacker.allies)}:
            return True
        return duel.defender is not None and not duel.defender.garrison and name_key(duel.defender.name) == me

    def sortie_cards(self) -> list[dict] | None:
        """main.sorties（欄位表 1.3；sortie_duel.card）：約戰關著、序章裡是 None；散人是空的。還沒打的約戰兩邊都列（對面的是應戰、同袍的是同去、
        自己的是 mine），結算完（或作廢）的只列自己有份的、留 keep_hours。同去那一顆照 _duel_join_extra 再驗；不同區的照 place_minutes 寫步行幾分。
        多一個 result：看的人這一場的結果（大勝、險勝、僵持、落敗；沒結算是 None）；sides（兩軍的名字，同 sortie_card.sides）與 answer_stamina（應戰的體力）
        每一張都帶：站的地方不是區塊時沒有 sortie_card，網頁的陣營名與底鈕的體力只能從這裡拿（FB-9003）。還沒打的另帶約戰那一塊此刻的樣子
        （holder、bars、to_flip、foe_pushing；應戰卡寫這一場牽動什麼，FB-9004）。"""
        s, c = self.state, self.content
        if not self.duel_on() or prologue_rules.active(s, c):
            return None
        side = self._conquest_side()
        if side is None:
            return []
        p, cfg, w = s.player, c.config.sortie, s.world
        region, _ = self._duel_region()
        keep = cfg.keep_hours * 3600
        left = self.answers_left()
        sides ={x: c.scenario.faction_name(x, x) for x in conquest.SIDES}
        duels = sorted(self.world.sortie_duels().values(),
                       key=lambda d: (d.status not in ("open", "answered"), -(d.settled_at or d.opened_at), d.id))
        out: list[dict] = []
        for duel in duels:
            live = duel.status in ("open", "answered")
            if not live and (not self._duel_mine(duel) or (duel.settled_at is not None and self.now - duel.settled_at >= keep)):
                continue
            far = duel.region is not None and region != duel.region
            card = sortie_duel.card(
                duel, p.name, side, region, self.now, cfg, answers_left=left, stamina=p.stamina, cooldown_until=p.answer_cooldown_until,
                traveling=p.journey is not None, travel_minutes=self.place_minutes(duel.block) if far else None,
            )
            if card["role"] == "join" and card["can_join"] and (extra := self._duel_join_extra(duel)) is not None:
                card["can_join"], card["why_not"] = False, extra
            card["result"] = sortie_duel.side_tier(duel, p.name)
            # 出陣約戰網頁（FB-9003）：站的地方不是區塊（豪族塢堡、南華觀……）就沒有 sortie_card，卡上的陣營名與應戰的體力要從每一張約戰卡自己帶
            card["sides"], card["answer_stamina"] = dict(sides), cfg.answer_stamina
            # 應戰卡寫的是這一場牽動的那一塊（FB-9004，不是看的人自己推這一塊）：還沒打的帶約戰那一塊此刻歸誰、兩條進度（mine 是看的人這一邊、
            # theirs 是約戰那一軍）、約戰那一軍離翻走還差多少、幾人在推——站在哪裡都一樣，守住了拉回的就是 theirs
            if card["status"] in ("open", "answered"):
                bars = conquest.bars(w, duel.block)
                foe = bars.get(duel.attacker.side, 0.0)
                card["holder"] = conquest.holder(w, c, duel.block)
                card["bars"] = {"mine": round(bars.get(side, 0.0)), "theirs": round(foe)}
                card["to_flip"] = max(0, round(conquest.FULL - foe))
                card["foe_pushing"] = sum(1 for row in conquest.pushers(w, c, duel.block) if row["side"] == duel.attacker.side)
            out.append(card)
        return out

    def _duel_amount(self, side: str, loc_id: str, base: float, name: str) -> tuple[float, float]:
        """約戰推（拉）的量（計畫 4.0 之三第 11 條）：base（名目量 × 結果倍率）× progress_scale × 傳檄 ÷ √n（side 這一邊的活躍人數，含 name）
        ×（1＋集火：side 一小時內在這一塊出陣過的別人，含同去的）。回（量, 集火）。"""
        s, c = self.state, self.content
        w, cfg = s.world, c.config
        amount = base * sortie_duel.progress_scale(c)
        if (writ := seal_acts.writ_factor(w, c, conquest.line_of(w, c, loc_id), side)) != 1.0:
            amount *= writ
        window = cfg.active_window_days * DAY / calendar.cal_scale(c, w)
        recent = {n for n, last in w.active_pushers.get(side, {}).items() if w.time - last <= window} | {name}
        amount = push.buffered(amount, len(recent))
        focus = conquest.focus_bonus(w, c, loc_id, side, name)
        return amount * (1 + focus), focus

    def _duel_loot(self, squad: Squad | None) -> str:
        """出陣前那張卡「贏了」那一段的戰利（一句話）：照 _sortie_full（一類一顆開著）或 _sortie_drill 的算法；沒有駐軍是空字串。"""
        if squad is None:
            return ""
        s, c = self.state, self.content
        cfg = c.config.sortie
        if precise.on(c, s.world):
            exp, xinde = round(squad.exp * cfg.reward_scale), round(squad.reward_xinde * cfg.reward_scale)
            silver = squad.reward_silver + s.player.member.level * cfg.merit_silver_per_level
        else:
            share = c.config.drill_reward_share
            exp, xinde = drill_share(squad.exp, share), drill_share(squad.reward_xinde, share)
            silver = int(squad.reward_silver * c.config.economy.sortie_silver_share + 0.5) if c.config.economy.sortie_silver else 0
        return sortie_duel.LOOT_LINE.format(exp=exp, xinde=xinde, silver=silver)

    def sortie_card(self) -> dict | None:
        """main.sortie_card（欄位表 1.3 的「出陣前那張卡」；main.sortie 是出陣開著的布林、照舊）：約戰關著、序章、散人、在路上、不是區塊是 None。
        這一塊（此刻歸誰、兩條各幾成與對面那一條是哪一軍、離易手、對面幾人在推、同袍幾人與集火、運糧隊）、贏了（推一程、貢獻、離下一階、戰利、
        翻了分紅、軍令對不對、戰書還差）、今天還能幾次、冷卻、能封的招、貼不了的原因、兩軍的名字、約戰窗幾分鐘、應戰的體力（出陣約戰網頁丙，
        2026-10-28：網頁不寫死陣營名、10 分、12）。自家的地方（搶得下來、此刻是自己這一邊的；按出陣只會「等對面來約」）：to_flip 是對面離翻走
        這裡還差多少、gain 是 None（守就是應戰，推不了自家的條）。"""
        s, c = self.state, self.content
        if not self.duel_on() or prologue_rules.active(s, c):
            return None
        p, w = s.player, s.world
        side = self._conquest_side()
        loc = p.location
        if side is None or p.journey is not None or loc not in conquest.blocks(c):
            return None
        cfg, qcfg = c.config.sortie, c.config.conquest
        bars = conquest.bars(w, loc)
        mine = bars.get(side, 0.0)
        theirs = max((v for k, v in bars.items() if k != side), default=0.0)
        foe = next((x for x in conquest.SIDES if x != side), None)  # 交戰兩軍只有兩邊：對面那一條就是另一軍的
        holder = conquest.holder(w, c, loc)
        own = conquest.capturable(c, loc) and holder == side
        nominal = conquest.sortie_nominal(c, loc, "attack")
        est, focus = self._duel_amount(side, loc, nominal * cfg.result_scale["win"], p.name)
        squad = self._duel_squad(loc)
        fight = conquest.fight_of(w, loc)
        pushed = dict(fight.bars[side].pushers) if fight is not None and side in fight.bars else {}
        total = sum(pushed.values()) + est
        part = (pushed.get(p.name, 0.0) + est) / total if total > 0 else 0.0
        pool = qcfg.take_silver * (1.0 if conquest.start_kind(w, c, loc) == conquest.NEUTRAL else qcfg.faction_pool_share)
        rank = ranks.rank_of(s)
        rank_next = max(0, ranks.threshold(c, rank + 1) - p.contrib) if 1 <= rank < 3 and calendar.season_one_on(w, c) else None
        line = conquest.line_of(w, c, loc)
        order_match = any(
            o.template == "siege" and not o.done and o.front == line and loc in orders.siege_places(c, side, line, w)
            for o in orders.current(s, c, side) if o.front is not None
        )
        convoy = orders.extra_enemies(s, c, loc, self._side()) if p.journey is None else []
        cooldown = p.sortie_cooldown_until if sortie_duel.cooling(p.sortie_cooldown_until, self.now) else None
        contribution = push.contribution(nominal, 1.0, 1.0, c.config.contrib_per_push, c.config.over_cap_contrib_ratio) \
            if calendar.season_one_on(w, c) else 0
        return {
            "block": loc, "place": c.locations[loc].name, "holder": holder,
            "sides": {x: c.scenario.faction_name(x, x) for x in conquest.SIDES},
            "bars": {"mine": round(mine), "theirs": round(theirs), "theirs_side": foe},
            "to_flip": max(0, round(conquest.FULL - (theirs if own else mine))),
            "foe_pushing": sum(1 for row in conquest.pushers(w, c, loc) if row["side"] != side),
            "allies": round(focus / qcfg.focus_step) if qcfg.focus_step > 0 else 0, "focus_bonus": round(focus, 2),
            "convoy_at": c.squads[convoy[0]].name if convoy else None,
            "gain": None if own else {
                "push": round(est), "contribution": contribution, "rank_next": rank_next, "loot": self._duel_loot(squad),
                "dividend": round(pool * part), "order_match": order_match, "letter_gap": max(0, round(qcfg.letter_at - mine)),
            },
            "left_today": self.sorties_left(), "cooldown_until": cooldown, "cost": cfg.jianfa_stamina,
            "moves": list(cfg.moves), "why_not": self.sortie_go_problem() or "",
            "window_minutes": cfg.window_minutes, "answer_stamina": cfg.answer_stamina,
        }

    # ── 約戰到時：結算（Review Focus 第 1 條）──

    def _duel_candidates_for(self) -> Callable[[SortieDuel], list[SortieSide]]:
        """到時沒有真人應戰時能補位的人（sortie_duel.advance 的 candidates_for；計畫 4.0 之三第 15 條）：這一季的假人裡跟攻方不同一軍（兩軍之一）、
        不在路上、今天還有應戰次數、體力夠、不在輸了的冷卻裡的。威力照 _duel_power_of 抄；同區優先由 sortie_duel.bot_answer 挑。真人不補位。"""
        if not hasattr(self.world, "db"):
            return lambda duel: []
        c, cfg = self.content, self.content.config.sortie
        season, today = self.world.get_season_number(), self._pill_day()
        pool: list[list[SortieSide]] = []

        def candidates(duel: SortieDuel) -> list[SortieSide]:
            if not pool:
                rows: list[SortieSide] = []
                for state in CharacterStore(self.world.db).all(bots_only=True):
                    p = state.player
                    if p.bot is None or not server_bots.active(p.bot, season) or p.journey is not None or p.location is None:
                        continue
                    state.world = self.state.world  # 存檔不帶季（exclude）：豪強依附哪一軍、威力都照手上這一份季算
                    side = allied.side_of(state, c)
                    if side not in conquest.SIDES:
                        continue
                    if sortie_duel.answers_left(p, cfg, today) <= 0 or p.stamina < cfg.answer_stamina \
                            or sortie_duel.cooling(p.answer_cooldown_until, self.now):
                        continue
                    rows.append(SortieSide(name=p.name, side=side, power=self._duel_power_of(state, c, self.world),
                                           region=seal_acts.region_of(c, p.location)))
                pool.append(rows)
            return [row for row in pool[0] if row.side != duel.attacker.side]

        return candidates

    def _sortie_duel_tick(self) -> list[SortieDuel]:
        """把到時的約戰結算掉（sortie_duel.advance）：world_tick（伺服器排程）、sync（排程關著時下一個同步的人替它收）、advance 都叫；假人程式另外
        每一輪叫 sortie_duel_tick。先只讀 world 那一列（sortie_duels）看有沒有到時的（季收了的、還沒打的也算），沒有就不開 world.mutate；advance
        只碰 open／answered 的（結算過的在 world 那一列已經是 settled），兩個程式輪流同步不重複、不倒退。標好結果之後在同一把鎖裡把季的進度與
        兩邊做完（_settle_duel）、存季。關著、暫停中什麼都不做。回這一下結算或作廢的那幾張。"""
        if not self.duel_on() or self.world.paused_at() is not None:
            return []
        ended = self.state.world.ended
        if not any(d.status in ("open", "answered") and (ended or sortie_duel.due(d, self.now))
                   for d in self.world.sortie_duels().values()):
            return []
        cfg = self.content.config.sortie
        candidates = self._duel_candidates_for()
        done: list[SortieDuel] = []

        def _apply(shared) -> None:
            waiting = {key for key, d in shared.sorties.items() if d.status == "open" and d.defender is None}
            for duel in sortie_duel.advance(shared, cfg, self.now, candidates):
                if duel.id in waiting and duel.defender is not None and not duel.defender.garrison:
                    duel.report["filled"] = True  # 補位的人：結算時扣他一次應戰與體力（同真人應戰）
                done.append(duel.model_copy(deep=True))

        self.world.mutate(_apply)
        for duel in done:
            self._settle_duel(duel)
        if done:
            self._save_season()
        return done

    def sortie_duel_tick(self, now: float) -> int:
        """假人程式每一輪替窗滿了的約戰結算（bot_runner.BotRunner.tick；伺服器排程關著、也沒有人同步時，十分鐘到了照樣收）：讀回這一季、推到 now。
        回這一下結算或作廢了幾張。"""
        self.now = now
        self.state.world = self.world.get_season()
        return len(self._sortie_duel_tick())

    def _duel_party(self, name: str) -> Game | None:
        """這一場的一方（自己就是那一位時是自己，不然照 _load_kin 讀出來、季接上手上這一份）。讀不到是 None。"""
        if name and name_key(name) == name_key(self.state.player.name):
            return self
        return self._load_kin(name)

    def _settle_duel(self, duel: SortieDuel) -> None:
        """一張約戰結算（或作廢）之後（計畫 4.0 之三第 8、11～16 條）：季的進度改在 self.state.world；攻方、同去的、應戰的人（含補位的）各一份戰報與
        一則江湖紀錄，自己就是那一方時改自己，別人改完存回（_save_kin）。守軍什麼都不拿。"""
        roles: list[tuple[str, str]] = [(duel.attacker.name, "attacker"), *((n, "ally") for n in duel.attacker.allies)]
        d = duel.defender
        if d is not None and not d.garrison:
            roles.append((d.name, "defender"))
        games: dict[str, Game] = {}
        for name, _ in roles:
            g = self._duel_party(name)
            if g is not None:
                games[name_key(name)] = g
        try:
            if duel.status == "void":
                for name, role in roles:
                    if (g := games.get(name_key(name))) is not None:
                        g._duel_void(duel, role)
                return
            self._duel_result(duel, roles, games)
        finally:
            for g in games.values():
                if g is not self:
                    self._save_kin(g)

    def _duel_void(self, duel: SortieDuel, role: str) -> None:
        """沒打成（季終、連守軍都沒有；PM 四之五第 5 件）：攻方與同去的退一次出陣（同一天才退次數）與 jianfa_stamina，應戰了的人退一次應戰與
        answer_stamina；冷卻不退。記一則江湖紀錄。"""
        s, c = self.state, self.content
        p, cfg = s.player, c.config.sortie
        today = self._pill_day()
        if role == "defender":
            sortie_duel.spend_answer(p, today, -1)
            p.stamina = min(float(c.config.stamina_max), p.stamina + cfg.answer_stamina)
        else:
            if p.sortie_day == today and duel.report.get("day") == today:
                p.sorties_today = max(0, p.sorties_today - 1)
            p.stamina = min(float(c.config.stamina_max), p.stamina + cfg.jianfa_stamina)
        self._write(sortie_duel.GO_TITLE.format(place=duel.place), [sortie_duel.VOID_LINE.format(place=duel.place)], tag=sortie_duel.LABEL)

    def _duel_result(self, duel: SortieDuel, roles: list[tuple[str, str]], games: dict[str, Game]) -> None:
        """結算了的那一張：軍令照推（拉）之前的清單記（FB-608）→ 推攻方那一條或拉回（守方贏）→ 貢獻 → 每一方的戰報、戰利或經驗心得、
        氣血內傷、冷卻、紀錄（_duel_report）。"""
        s, c = self.state, self.content
        w, cfg = s.world, c.config.sortie
        loc, side, d = duel.block, duel.attacker.side, duel.defender
        squad = c.squads.get(duel.report.get("squad") or "")
        how, scale = sortie_duel.scale_of(duel, cfg)
        tier = duel.result.tier
        nominal = conquest.sortie_nominal(c, loc, "attack")
        attacker = games.get(name_key(duel.attacker.name))
        defender = games.get(name_key(d.name)) if d is not None and not d.garrison else None
        drafts = {key: Draft(sortie_duel.GO_TITLE.format(place=duel.place)) for key in games}  # 結果標記照戰報（_file_battle 填）
        saved = {key: g._draft for key, g in games.items()}
        msgs: dict[str, list[str]] = {key: [] for key in games}
        for key, g in games.items():
            g._draft = drafts[key]
        try:
            # 軍令：推（拉）之前的清單（推滿易手、拉回歸零的那一下推完就不在清單上了）
            if tier in ("big", "win") and attacker is not None and squad is not None:
                msgs[name_key(duel.attacker.name)] += attacker._order_credit(
                    side=side, kind="win", location=loc, front=front_of(c, loc), squad=squad.id, squad_faction=squad.faction)
            if how == "pull" and defender is not None:
                msgs[name_key(d.name)] += defender._order_credit(side=d.side, kind="duty", location=loc, front=conquest.line_of(w, c, loc))
            moved, credited = self._duel_move(duel, how, scale, nominal)
            week = calendar.point(w.time, c, w).week
            points = push.contribution(nominal * scale, 1.0, 1.0, c.config.contrib_per_push, c.config.over_cap_contrib_ratio) \
                if credited and calendar.season_one_on(w, c) else 0
            for name, role in roles:
                g = games.get(name_key(name))
                if g is None:
                    continue
                if points and (role in ("attacker", "ally")) == (how == "push"):
                    # 帳記貼（應）約戰那一刻替的那一軍（FB-856）：攻方與同去的是攻方那一軍（同去要同一軍），應戰的是守方那一軍；
                    # 豪強窗內改幫，結算時 p.ally 已經是新的那一軍，不照它記
                    mine = side if role in ("attacker", "ally") else (d.side if d is not None else None)
                    wins.credit(g.state.player, c, w, week, points, side=mine)
                    msgs[name_key(name)].append(f"貢獻 +{points}")
                msgs[name_key(name)] += g._duel_report(duel, role, squad, moved)
            for key, g in games.items():
                journal.add_entry(g.state, g._draft.entry(w.time, msgs[key]))
        finally:
            for key, g in games.items():
                g._draft = saved[key]

    def _duel_move(self, duel: SortieDuel, how: str, scale: float, nominal: float) -> tuple[list[str], bool]:
        """這一塊怎麼動（季的進度，self.state.world）：攻方大勝、勝、僵持推攻方那一條（conquest.push；推不動照舊打完、不推、不記貢獻）；攻方敗拉攻方
        那一條（conquest.guard_pull，守城功照翻地設計 4.5）。回（寫給兩邊的句子，記不記貢獻）。"""
        s, c = self.state, self.content
        w = s.world
        loc, side, place = duel.block, duel.attacker.side, duel.place
        name = self._duel_who(side)
        if how == "push":
            if scale <= 0:
                return [], False
            why = conquest.push_problem(w, c, side, loc, "attack")
            if why is not None:
                return [sortie_duel.MOVE_STILL.format(place=place, why=why)], False
            amount, _ = self._duel_amount(side, loc, nominal * scale, duel.attacker.name)
            done = conquest.push(w, c, loc, side, duel.attacker.name, amount, "attack")
            conquest.mark(w, c, loc, duel.attacker.name, side, "attack", done.moved)
            conquest.tally(w, c, self._pill_day(), side, duel.attacker.name, done.moved)
            window = c.config.active_window_days * DAY / calendar.cal_scale(c, w)
            for who in (duel.attacker.name, *duel.attacker.allies):
                w.active_pushers.setdefault(side, {})[who] = w.time
            w.active_pushers = push.drop_stale(w.active_pushers, w.time, window)
            if done.flipped:
                return [sortie_duel.MOVE_FLIP.format(place=place, side=name), conquest.PAYOUT_NEXT], True
            return [sortie_duel.MOVE_LINES[duel.result.tier].format(place=place, side=name)], True
        d = duel.defender
        if conquest._still(w, c, loc):  # noqa: SLF001  剛易手、戰書凍結、碎片鎮住：誰都動不了（同 conquest.pull）
            return [sortie_duel.MOVE_STILL.format(place=place, why=conquest.push_problem(w, c, side, loc, "attack") or "")], False
        amount, _ = self._duel_amount(side, loc, nominal * scale, duel.attacker.name)
        holder = d.side if d is not None and d.side in conquest.SIDES else None
        pulled = conquest.guard_pull(w, c, loc, side, amount, name="" if d is None or d.garrison else d.name, holder_side=holder)
        key = "pull" if pulled.moved > 0 else "hold"
        return [sortie_duel.MOVE_LINES[key].format(place=place, side=name), *pulled.lines], d is not None and not d.garrison

    def _duel_toll(self, share: float, lost: bool) -> list[str]:
        """三回合扣的氣血（share 是氣血上限的幾成，照舊吃身法、根骨、防具減損，一部分變內傷：team._apply_toll）；輸的另加內傷 lose_injury。"""
        s, c = self.state, self.content
        p = s.player
        msgs: list[str] = []
        hurt = 0.0
        if share > 0:
            cut = min(c.config.armor.total_cap, team.armor_cut(s, c, self.world))
            lost_hp, hurt = team._apply_toll(c, p.member, share * (1 - cut), agi=p.stats.get("agi", team.BASE_STAT),
                                             con=team.con_of(s, c, self.world, PLAYER), injury=treasures.amount(s, c, "injury"))
            if round(lost_hp) > 0:
                msgs.append(f"氣血 -{lost_hp:.0f}")
        if lost and c.config.sortie.lose_injury > 0:
            p.member.injury += c.config.sortie.lose_injury
            hurt += c.config.sortie.lose_injury
        if hurt >= 1:
            msgs.append(f"內傷 +{hurt:.0f}")
        return msgs

    def _duel_hold_gains(self, squad: Squad, record) -> list[str]:
        """守方贏了（真人或補位的人）：跟攻方打贏一樣的經驗心得（那一塊駐軍那一路的 reward_scale 倍；一類一顆關著照三成），不給銀兩與掉落（PM）。"""
        s, c = self.state, self.content
        p, cfg = s.player, c.config.sortie
        if precise.on(c, s.world):
            xinde = round(squad.reward_xinde * cfg.reward_scale * (1 + treasures.amount(s, c, "win_xinde_pct")))
            exp = round(squad.exp * cfg.reward_scale * (1 + treasures.amount(s, c, "win_exp_pct")) * ranger.exp_factor(s, c))
        else:
            share = c.config.drill_reward_share
            xinde, exp = drill_share(squad.reward_xinde, share), drill_share(squad.exp, share)
        msgs: list[str] = []
        if xinde:
            p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
            record.xinde = (record.xinde or 0) + xinde
            msgs.append(f"心得 +{xinde}")
        msgs += self._record_exp(record, exp, "answer")  # 應戰是仗（growth.exp_source；45 級以後照樣升，不乘遭遇拍的兩道閘）
        levels, record.levelups = team.grant_team_exp(s, c, self.world, exp, "answer")
        record.notes += levels
        return msgs + levels

    def _duel_report(self, duel: SortieDuel, role: str, squad: Squad | None, moved: list[str]) -> list[str]:
        """這一方的戰報（kind sortie、label 約戰；三回合各一行、對面是誰、結果、這一塊怎麼動、離易手還差、離下一階、同去的、戰利或經驗心得、
        氣血內傷、截糧、下一次什麼時候）、行狀一筆、冷卻；補位的人扣一次應戰與體力。回寫進這一則江湖紀錄的話。"""
        s, c = self.state, self.content
        p, w, cfg = s.player, s.world, c.config.sortie
        result, d = duel.result, duel.defender
        fought = role != "ally"
        mine = d if role == "defender" else duel.attacker
        rival = duel.attacker if role == "defender" else d
        tier_word = sortie_duel.side_tier(duel, p.name) or sortie_duel.TIER_WORDS[result.tier]
        record = BattleRecord(
            id=s.battle_seq + 1, time=w.time, location=duel.place, kind="sortie", label=sortie_duel.LABEL,
            opponent=sortie_duel.GARRISON if rival is None or rival.garrison else rival.name, ours=[Fighter(name=p.name, level=p.member.level)],
            tier=tier_word, our_power=mine.power if mine is not None else 0.0, difficulty=rival.power if rival is not None else 0.0,
            rounds=sortie_duel.round_lines(duel),
        )
        record.notes.append(sortie_duel.vs_line(duel))
        if duel.attacker.allies:
            record.notes.append(sortie_duel.VS_ALLIES.format(names="、".join(duel.attacker.allies)))
        record.notes.append(sortie_duel.TALLY_LINE.format(wins=result.wins, losses=result.losses, draws=result.draws, attacker=duel.attacker.name))
        record.notes += moved
        bar = conquest.bar(w, duel.block, duel.attacker.side)
        who = self._duel_who(duel.attacker.side)
        if bar > 0:
            record.notes.append(sortie_duel.GAP_LINE.format(side=who, place=duel.place, value=round(bar), left=max(0, round(conquest.FULL - bar))))
        msgs: list[str] = []
        won = tier_word in team.WIN_TIERS
        if fought and won and squad is not None:
            rng, self.rng = self.rng, random.Random(f"約戰戰利|{duel.id}|{p.name}")  # 掉落用這一場自己的亂數（不碰 Game.rng）
            try:
                msgs += self._sortie_rewards(squad, record) if role == "attacker" else self._duel_hold_gains(squad, record)
            finally:
                self.rng = rng
            if role == "attacker":
                msgs += self._deed_fame("sortie")  # 名聲 3.1：出陣攻打贏 +1
        if role == "defender" and duel.report.get("filled"):
            sortie_duel.spend_answer(p, self._pill_day())  # 補位的人：同真人應戰扣一次應戰與體力
            p.stamina = max(0.0, p.stamina - cfg.answer_stamina)
        lost = fought and tier_word == "落敗"
        if fought:
            share = result.defender_toll if role == "defender" else result.attacker_toll
            toll = self._duel_toll(share, lost)
            record.changes += toll
            msgs += toll
            after = sortie_duel.cooldown_after(duel, p.name, cfg)
            if after.sortie is not None:
                p.sortie_cooldown_until = max(p.sortie_cooldown_until or 0.0, after.sortie)
            if after.answer is not None:
                p.answer_cooldown_until = max(p.answer_cooldown_until or 0.0, after.answer)
            if lost:
                record.notes.append(sortie_duel.LOSE_LINE.format(n=f"{cfg.lose_cooldown_minutes:g}"))
            annal_line = sortie_duel.ANNAL_ANSWER_LINE if role == "defender" else sortie_duel.ANNAL_LINE  # 應戰的人（含補位的）另一句（FB-897）
            annals.note(s, c, annals.DUEL, annal_line.format(  # 地點寫約戰的那一塊（結算時人可能已經走了）
                place=duel.place, rival=rival.name if rival is not None and not rival.garrison else sortie_duel.GARRISON, tier=tier_word), 2,
                place=duel.place, keep=[rival.name] if rival is not None and not rival.garrison else None)  # 對手是玩家：名號原樣留（FB-9020）；守軍不必
        rank = ranks.rank_of(s)
        if 1 <= rank < 3 and calendar.season_one_on(w, c):
            record.notes.append(sortie_duel.RANK_LINE.format(n=max(0, ranks.threshold(c, rank + 1) - p.contrib)))
        if orders.extra_enemies(s, c, duel.block, self._side()):
            record.notes.append(sortie_duel.CONVOY_LINE.format(place=duel.place))
        left, answers = self.sorties_left(), self.answers_left()
        record.notes.append(sortie_duel.NEXT_LINE.format(
            sortie=sortie_duel.NEXT_DONE if left <= 0 else sortie_duel.minutes_text(p.sortie_cooldown_until, self.now),
            answer=sortie_duel.NEXT_DONE if answers <= 0 else sortie_duel.minutes_text(p.answer_cooldown_until, self.now),
        ))
        if fought:
            line = self._file_battle(record)
        else:
            battlelog.add_record(s, record)
            line = battlelog.summary_line(record)
            if self._draft is not None:
                self._draft.outcome(battlelog.outcome_text(record), line)
                self._draft.battle_id = record.id
        return [line, sortie_duel.vs_line(duel), *moved, *msgs]

    def _lose_silver(self, record) -> list[str]:
        """落敗失落一成銀兩（遊歷、探索野怪、挑戰本人共用），記在戰報上。騎著馬有機會策馬脫身、保住這一成（裝備四欄 5.11）：
        只保銀兩，氣血、內傷、戰報結果照舊是落敗；擲骰用自己的亂數（「脫身|季數|名號|戰報流水號」：戰報流水號每季從頭算，少了季數
        每一季第 N 場的結果都一樣），不動 Game.rng，整季測試與量表的基準不位移。沒有銀兩可丟（一成是 0）就不擲。
        帶著金角（玉璽碎片改版，treasures.amount 的 keep_silver）落敗不失銀兩，寫一句 treasures.KEEP_SILVER（截殺、設伏、混戰、
        買兇的殺手各有自己的扣法，不走這裡，照舊）。"""
        p = self.state.player
        loss = p.stats["silver"] // 10
        if loss and treasures.amount(self.state, self.content, "keep_silver") > 0:  # 金角（玉璽碎片改版，PM 五之一 3）：落敗不失銀兩
            line = treasures.KEEP_SILVER.format(shard=p.heirloom.name if p.heirloom is not None else "")
            record.notes.append(line)
            return [line]  # 保住了就不擲策馬脫身（那一份亂數是自己的，不擲不會讓別的擲骰位移）
        chance = mounts.escape(self.state, self.content)
        seed = f"脫身|{self.world.get_season_number()}|{p.name}|{record.id}"
        if loss and chance > 0 and random.Random(seed).random() < chance:
            record.notes.append(mounts.ESCAPED_LOSS)
            return [mounts.ESCAPED_LOSS]
        p.stats["silver"] -= loss
        record.silver = -loss
        return [f"銀兩 -{loss}"] if loss else []

    def _player_hp_and_cap(self) -> tuple[float, float]:
        """本人此刻的氣血與上限（上限吃根骨：con_of 認 key，所以傳 PLAYER，不傳 Member）。"""
        return team.member_neili(
            self.content, self.state.player.member, team.con_of(self.state, self.content, self.world, PLAYER), season=self.state.world,
        )

    def _player_hp(self) -> float:
        return self._player_hp_and_cap()[0]

    def _hp_facts(self, healed: tuple[str, ...] = ()) -> TollFacts:
        """此刻的氣血在寫功效演出句看來是什麼樣子（開打前量；劇情戰不扣氣血，開打前就是整場的樣子）。"""
        now, cap = self._player_hp_and_cap()
        return TollFacts(wounded=now < cap, low_hp=now <= LOW_HP_RATIO * cap, healed=healed)

    def _take_toll(self, tier: str, *, wild: bool = False, clash: tactics.Clash | None = None) -> tuple[list[str], int, TollFacts]:
        """照結果扣這一場的氣血（team.take_encounter_toll），回傳（訊息, 本人真的掉了多少氣血, 寫演出句要的事實）。掉的量緊貼著
        扣氣血的前後量（計畫三 G4）：打贏升級會讓上限變高，開打前量的話回合裡寫的跟戰報「氣血 -N」對不上。四捨五入跟訊息的
        「:.0f」是同一個數（兩者都對同一個浮點數做銀行家捨入）。
        扣完之後本人身上的吸取（打贏）與回春（不論勝負）才回氣血（武學與成長設計 13.2、13.4）：回的那一行「氣血 +N」接在
        訊息後面、一起寫進戰報；掉的量在回血之前量，回合裡寫的「你氣血 -N」照舊加得起來。劇情戰不走這裡（不扣氣血，也就不回）。
        事實（TollFacts）是 _play_rounds 寫功效的演出句用的：開打前氣血是不是低於上限（厚），哪幾個回血的功效真的回了血
        （沒回到 1 點、沒有「氣血 +N」那一行就不算）。
        clash 是這一場一回合一回合打的樣子（tactics.Clash）：對手沒打到你的回合（定身、打空、打到自己、化影）照比例少扣，
        本命戰法回的與自扣的氣血（Clash.hp：本人與同伴）在最後改。"""
        before, cap = self._player_hp_and_cap()
        share = 1 - clash.blocked_share() if clash is not None else 1.0
        saved, spared = team.toll_saved(self.state, self.content, self.world, tier, wild=wild, share=share)  # 扣之前量：化勁、不動這一場改了多少
        toll = team.take_encounter_toll(self.state, self.content, self.world, tier, wild=wild, share=share)
        hp_lost = round(before - self._player_hp())  # 回血之前量：回合裡寫的扣血不受吸取與回春影響
        healed: list[str] = []  # 吸取、回春以前在這裡打完回血；本命戰法第三批起在回合裡回（Clash.hp）
        gained: list[tuple[str, int]] = []
        for key, fraction in (clash.hp.items() if clash is not None else ()):  # 本命戰法（tactics.py）回的、自扣的
            toll += team.shift_hp(self.state, self.content, self.world, key, fraction)
        return toll, hp_lost, TollFacts(
            wounded=before < cap, low_hp=before <= LOW_HP_RATIO * cap, healed=tuple(healed),
            saved=saved, spared=spared, gained=tuple(gained),
        )

    def _play_rounds(
        self, record, squad: Squad, tier: str, hp_lost: int | None, facts: TollFacts | None = None, clash: tactics.Clash | None = None,
    ) -> None:
        """照結果演出回合寫進戰報（武學與成長設計 8.2）。hp_lost 是這一場本人真的扣掉的氣血（_take_toll），回合裡寫的
        「你氣血 -N」加起來剛好等於它；None 是這一場本來就不扣氣血（劇情戰），對手的出手不寫數字（計畫三 G5）。
        亂數是自己一份、用「名號｜戰報流水號」當種子（計畫三 G3）：不碰 Game.rng，接下來的擲骰不會位移，
        同一筆戰報每次演出來都一樣。
        輸了（含僵持）卻一滴氣血都沒掉（本來就見底，內傷照樣累積）時，跟劇情戰一樣不寫打中沒有：每一下都寫「被你閃開了」，
        讀起來是對方沒碰到你、你卻輸了、損失裡還有內傷（最後審查 Minor 2）；贏了沒掉血（打得漂亮）寫閃開是通的，不動。
        帶【先手】的人回合裡一定先出手、不看身法（13.2）；功效的演出句寫進 trait_before／trait_after（13.6，_trait_lines），
        護命的那一句寫進 notes 最前面（跟閃避的那一句同一個位置）。facts 是 _take_toll 量好的（劇情戰不給，氣血的功效就不演）。
        clash 是 team.fight 一回合一回合打的那一場（tactics.Clash，Joy 2026-10-15「全部改回合制」）：回合數、兩邊出的招、氣勢、
        對手打沒打到你都照它，本命戰法的句子排在它發動的那一回合前面；大場面有模型寫的那一段話時，戰法的句子接在 trait_after。
        沒有 clash 的（切磋、截殺、序章寫好結果的那一場）照舊照結果拆。"""
        s, c, p = self.state, self.content, self.state.player
        if hp_lost == 0 and tier not in team.WIN_TIERS:
            hp_lost = None
        rng = random.Random(f"{p.name}|{record.id}")
        lo = traits.loadout(s, c, self.world)
        foe = rounds.Foe(name=squad.name, attribute=squad.attribute, agility=rounds.foe_agility(squad.difficulty))
        our_agility = float(p.stats.get("agi", team.BASE_STAT))
        fighters = team.fighters(s, c, self.world)
        if clash is not None:
            played = rounds.from_clash(clash, fighters, foe, our_agility, hp_lost, rng)
        else:
            played = rounds.play(tier, fighters, foe, our_agility, hp_lost, rng)
        record.rounds = battlelog.round_lines(c, played, rng)
        record.trait_before, record.trait_after = self._trait_lines(lo, record, squad, hp_lost, facts or TollFacts(), rng)
        if record.narration and clash is not None:  # 大場面：回合換成模型的那一段話，戰法的句子接在後面
            record.trait_after += [line for turn in clash.turns for line in turn.lines]

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

        # 本命戰法第三批起，其餘的功效在回合裡發動（tactics.py，句子在回合裡）；這裡只剩打完才算的兩個：化勁少扣的氣血、厚的氣血係數下限
        after: list[str] = []
        if hp_lost and lo.layers.get("toll_cut"):
            after.append(say(names["toll_cut"], note=f"（少扣了 {facts.saved} 點氣血）" if facts.saved > 0 else ""))
        if lo.layers.get("condition_floor") and facts.wounded:
            after.append(say(names["condition_floor"], low_hp=facts.low_hp))
        return [], after

    # ── 挑戰大勢人物本人（計畫 T4、軍令文件 4.5）─────────────

    def _snubbed(self, fid: str) -> bool:
        """這位人物剛被你打敗、還在閉門不見（snub_hours 個現實小時內）。看的是現實時間（self.now，sync 傳進來的），
        不是賽季時鐘：管理者快轉、補算時間都不會讓他提早見你；紀錄存在角色存檔，伺服器重開也照樣記得。
        沒有挑戰本人的季（figures.challenge_on 是假）就沒有閉門不見這回事。"""
        return figures.challenge_on(self.content, self.state.world) and self.now < self.state.player.snubbed_until.get(fid, 0.0)

    def _snubbed_character(self, character_id: str) -> bool:
        """這個對話人物（求見、交友用的 id）是不是剛被你打敗、還在閉門不見的大勢人物。"""
        fid = figures.of_character(self.content, character_id)
        return fid is not None and self._snubbed(fid)

    def _challenge_options(self, odds: bool) -> list[Option]:
        """挑戰本人：有挑戰本人的季（figures.challenge_on，每季都有）、自己有陣營時，這裡每一位在場的敵方大勢人物一個選項
        （體力照遊歷；odds 時寫勝算，難度跟著聲威走）。剛被你打敗、閉門不見的那幾位按不下去、寫明原因；戰線空著的人物（人物表
        標了 challenge_off_front 的何進除外）第一季也是灰鈕寫原因，沒有時刻表的季不畫。求見、交友照常。散人沒有；同陣營的人不打。"""
        s, c = self.state, self.content
        p = s.player
        if p.faction is None or not figures.challenge_on(c, s.world):
            return []
        cost = self._action_costs()["train"]
        opts = []
        for fid in figures.present_at(s, c, p.location):
            fig = c.figures[fid]
            if fig.faction == self._side():  # 同陣營（豪強分屬兩軍：依附那一軍）的人物不打
                continue
            option_id = f"act:challenge:{fid}"
            if not figures.can_challenge(s, c, fid):
                if figures.untimed(c, s.world):  # 沒有時刻表的季戰線空著的人不畫鈕：看不到戰線，整季掛著一顆按不下去的鈕（設計 3.2）
                    continue
                opts.append(Option(id=option_id, label=f"挑戰{fig.name}（{OFF_FRONT_NOTE}）", enabled=False))
            elif self._snubbed(fid):
                opts.append(Option(id=option_id, label=f"挑戰{fig.name}（{SNUB_NOTE}）", enabled=False))
            else:
                note = self.challenge_odds(fid) if odds else ""
                guards = len(figure_aid.posts(s, c, fid)) if figure_aid.on(c) else 0
                if guards:
                    note = "・".join(x for x in (note, figure_aid.GUARDED_NOTE.format(n=guards)) if x)
                option = self._cost_option(option_id, f"挑戰{fig.name}", cost, note=note)
                option.wait = BIG_FIGHT_WAIT  # 挑戰本人一律是大場面：按下去先等模型判讀（武學與成長設計 8.3）
                opts.append(option)
        return opts

    def challenge_odds(self, fid: str) -> str:
        """挑戰這位人物的勝算（跟遊歷同一套說法）：對手是代表本人的隊伍，難度照他此刻的聲威（figures.difficulty）與江湖水漲。"""
        squad = self._figure_squad(fid)
        return team.estimate(self.state, self.content, self.world, squad.id, difficulty=squad.difficulty,
                             draw_floor=rise.draw_floor(self.content))

    def _figure_squad(self, fid: str) -> Squad:
        """挑戰這位人物本人要打的那一路：難度照他此刻的聲威（figures.squad_of），再照江湖水漲浮上來——你此刻對他的全隊威力 ×
        倍數，倍數照你這一季打贏他幾次（figure_wins）往上加（rise.big）。勝算、備料（A、C 段）、打起來都照這一份。"""
        s, c = self.state, self.content
        squad = figures.squad_of(s, c, fid)
        if not rise.on(c):
            return squad
        # 地利不浮上去（武學隨地理環境 2.1）；玉璽碎片的戰力也不浮上去（改版 PM 五之一 2）
        power = team.power_vs(s, c, self.world, squad, fresh=True, terrain=False, seal=False)
        level = rise.big(c, squad.difficulty, power, s.player.figure_wins.get(fid, 0))
        return squad if level == squad.difficulty else squad.model_copy(update={"difficulty": round(level, 1)})

    def _story_squad(self, squad: Squad) -> Squad:
        """劇情戰的對手：大場面（is_big）照江湖水漲浮上來（全隊威力 × big_scale，不看打贏幾次：劇情戰多半一次性）；
        其餘、序章照內容寫的。勝算（_choice_label）、備料（_fight_squad）、打起來（_event_battle）都照這一份。"""
        s, c = self.state, self.content
        if not rise.on(c) or not self.is_big(squad) or prologue_rules.active(s, c):
            return squad
        level = rise.big(c, squad.difficulty, team.power_vs(s, c, self.world, squad, fresh=True, terrain=False, seal=False))  # 地利、碎片不浮
        return squad if level == squad.difficulty else squad.model_copy(update={"difficulty": round(level, 1)})

    def _challenge(self, fid: str) -> list[str]:
        """挑戰本人（軍令文件 4.5，企劃者 2026-10-04 改定）：跟他本人打一場單次判定，花遊歷的體力。打贏他敗走（_rout），
        拿那支隊伍的獎勵；落敗失落一成銀兩；不論勝負都照結果扣氣血（同遊歷）。可以重複打，只是打贏的人要等他消氣。
        不推戰線（推戰線的是遊歷；打擊人物削的是聲威），也不擲官銀（那是遊歷打贏官軍隊伍才有）。
        打贏另有機會掉一件寶物（_figure_treasure）。打贏記一次 figure_wins，第 signature_wins 次他讓你奪走本命兵器
        （_signature_arms，現在只有孫堅）。"""
        s, c = self.state, self.content
        fig = c.figures[fid]
        squad = self._figure_squad(fid)
        s.player.stamina -= self._action_costs()["train"]
        post, broke = figure_aid.contest(s, c, fid, s.player.name, self._battle_power()) if figure_aid.on(c) else (None, True)
        if not broke:  # 護衛擋下：這一次挑戰不成，不打他本人、不扣情誼（Joy 2026-10-17 第 6 條）
            return [figure_aid.BLOCKED_LINE.format(guard=post.name, name=fig.name)]
        judged = self._judged(squad)  # 挑戰本人一律是大場面：有鎖外的判讀就用（武學與成長設計 8.3）
        result = self._fight_with(squad, judged, difficulty=squad.difficulty, draw_floor=rise.draw_floor(c))
        record = battlelog.new_record(s, c, self.world, squad, result, "event", event=f"挑戰{fig.name}")
        record.notes += self._style_note(squad, result) + self._terrain_note()
        self._narrate(record, result, judged)
        msgs: list[str] = []
        arm_annals: list[tuple[str, str]] = []  # 本命兵器那一筆行狀：等這一場的行狀記完再記（照時間先後）
        if result.tier in team.WIN_TIERS:
            p, cfg = s.player, c.config
            first = p.figure_wins.get(fid, 0) == 0  # 丁 (c)：這一季第一次打贏他才有三階（預設表照擲；之後照擲、擲中不給）
            capped = bool(cfg.figure_rare_cap) and p.figure_rare_drops >= cfg.figure_rare_cap  # 一人一季上限，叛投不清
            p.figure_wins[fid] = p.figure_wins.get(fid, 0) + 1  # 本命兵器「打贏他本人三次」（兵器設計 4.10）：這一季累計
            reward = self._challenge_reward(fid, squad)
            held = self._held_tier3()
            msgs += self._battle_rewards(reward, record, max_tier=None if first and not capped else 2)
            p.figure_rare_drops += self._held_tier3() - held
            fame = self._deed_fame("challenge")  # 名聲 3.1：挑戰本人打贏 +2（推翻挑戰每季都有設計的「不給」）
            record.changes += fame
            msgs += fame
            extra = self._rout(fid)
            changes, notes = battlelog.split_changes(extra, for_record=True)
            record.changes += changes
            record.notes += notes
            msgs += extra
            msgs += self._figure_treasure(fid, record)  # 打贏本人掉寶物（裝備四欄 6.4）：只進江湖紀錄，戰報的「得失」寫 GAIN_LINE（同兵器掉落）
            msgs += self._figure_tier3(fid, squad, record)  # 打贏本人掉一個三階（兵器設計 4.9）：戰報「得失」與江湖紀錄
            msgs += self._figure_tier4(fid, squad, record)  # 這一季第一次打贏他另擲一個四階（正式季整合 4.5）
            msgs += self._signature_arms(record, beaten=fid, later=arm_annals)  # 第三次打贏那一刻他讓你奪走（寫進這一場戰報的「得失」）；_rout 把他打到重創的這一場照給
        elif result.tier == "僵持":
            msgs += self._challenge_draw(fid, squad, record)
        elif result.tier == "落敗":
            msgs += self._lose_silver(record)
        toll, hp_lost, facts = self._take_toll(result.tier, clash=result.clash)
        record.changes += toll
        msgs += toll
        self._play_rounds(record, squad, result.tier, hp_lost, facts, clash=result.clash)  # squad 是照聲威的那一份：對手的身法跟著難度走
        msgs += self._seize(record, draw=c.config.figure_draw_share > 0)  # 挑戰本人打成僵持也算一次頓悟的契機（企劃者 2026-10-16）
        msgs.insert(0, self._file_battle(record, wear=True, armor_wear=True))  # 挑戰本人的戰報 kind 是 event，但兵器、防具照磨（兵器設計 3.4、裝備四欄 4.4）
        self._famed_news(c.locations[s.player.location].name, fig.name, result.tier)  # 名聲 4.5：挑戰本人一律是大場面
        won = result.tier in team.WIN_TIERS
        annals.note(s, c, annals.FIGHT, f"挑戰{fig.name}本人，{result.tier}" + ("，他敗走。" if won else "。"), 4 if won else 3,
                    figure=fig.character or "")
        for text, who in arm_annals:
            annals.note(s, c, annals.FIGURE, text, 4, figure=who)
        if post is not None:
            msgs.insert(1, figure_aid.BROKE_LINE.format(guard=post.name, name=fig.name))
        return msgs

    def _challenge_reward(self, fid: str, squad: Squad) -> Squad:
        """挑戰本人打贏的那一份心得、經驗。戊 (b)：被打弱的人物照難度比例少給——照聲威的那一份算，江湖水漲浮上去的難度不多給。"""
        s, c = self.state, self.content
        ratio = min(1.0, figures.difficulty(s, c, fid) / figures.start_difficulty(c, fid))
        return squad.model_copy(update={"reward_xinde": int(squad.reward_xinde * ratio + 0.5), "exp": int(squad.exp * ratio + 0.5)})

    def _challenge_draw(self, fid: str, squad: Squad, record) -> list[str]:
        """挑戰本人打成僵持（企劃者 2026-10-16「僵持也給一點東西，讓重複挑戰不是純虧體力」）：險勝那一份心得、經驗的
        draw_share（一半），不乘寶物與遊俠名號的「打贏」加成；不給銀兩、素材、三階、寶物、碎片，聲威不動、不閉門不見、
        不算打贏（figure_wins、本命兵器、江湖水漲的倍數都不動）。情誼也不扣：扣情誼是把他打到敗走的代價（_rout），
        平手是堂堂正正過了招，不是折辱他。頓悟的契機在 _seize(draw=True)。"""
        p, share = self.state.player, self.content.config.figure_draw_share
        won = self._challenge_reward(fid, squad)
        xinde, exp = int(won.reward_xinde * share + 0.5), int(won.exp * share + 0.5)
        msgs = [figures.DRAW_LINE.format(name=self.content.figures[fid].name)]
        if xinde:
            p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
            record.xinde = xinde
            msgs.append(f"心得 +{xinde}")
        msgs += self._record_exp(record, exp, "challenge")
        levels, record.levelups = team.grant_team_exp(self.state, self.content, self.world, exp, "challenge")
        record.notes += levels
        return msgs + levels

    def _rout(self, fid: str) -> list[str]:
        """打贏了，他敗走：
        1. 聲威扣 figure_defeat_prestige，照陣營人數緩衝（push.buffered，n＝自己陣營活躍時窗內推過大勢的人，含自己）；
           扣到 0 退場或重創、由接位的人接手（figures.defeat）；
        2. 打贏的人跟他的情誼扣 figure_defeat_affinity（沒有對話人物的彭脫、韓忠沒有情誼）；
        3. snub_hours 個現實小時內他不見你、也不跟你交手（其他人照常）；
        4. 記貢獻（只在第一季：其他季沒有晉升，同截殺）：照推 figure_defeat_prestige 點大勢算（contrib_per_push，不打人數緩衝的折），
           記在這一週。"""
        s, c = self.state, self.content
        p, w, cfg = s.player, s.world, c.config
        fig = c.figures[fid]
        window = cfg.active_window_days * DAY / calendar.cal_scale(c, w)
        n = push.active_count(s, self._side(), w.time, window)
        msgs = [f"{fig.name}敗走。"]
        cap = figures.loss_cap(c, w)  # 甲 (d)：沒有時刻表的季與 21 天季（正式季整合 3.9）每位人物一天最多被打掉幾點；週末的第一季照人數緩衝
        today = world_day(c, w)  # 21 天季台灣 00:00 換日（正式季整合設計 1.3）
        if cfg.figure_dent_once_per_day and p.figure_dented.get(fid) == today:  # 同一個人同一位人物一天只有第一場扣聲威（PM 2026-10-16）
            msgs.append(figures.DENT_ONCE_LINE.format(name=fig.name))
        else:
            p.figure_dented[fid] = today
            msgs += figures.defeat(s, c, fid, push.buffered(cfg.figure_defeat_prestige, n), cap=cap)
        if fig.out_flag and figures.untimed(c, w) and figures.is_out(s, fid):  # 丙 (c)：沒有時刻表的季打退波才＝擊敗波才（第一季不記）
            add_world_flags(s, [fig.out_flag])
        if fig.character is not None:
            before = p.affinities.get(fig.character, 0)
            p.affinities[fig.character] = max(0, before - cfg.figure_defeat_affinity)
            if p.affinities[fig.character] != before:
                msgs.append(f"{fig.name}情誼 {p.affinities[fig.character] - before:+d}")
        msgs += figure_life.spread(  # 風聞（大勢人物擴充）：同一大區的人物聽說了，同一方的情誼掉、對頭的漲
            s, c, "beat", fid, at=p.location, side=fig.faction,
            text=f"在{c.locations[p.location].name}打退了{fig.name}")
        deeds.record(s, c, "beat", f"{p.name}在{c.locations[p.location].name}打退了{fig.name}。", place=p.location,  # 世界活起來
                     figures=[fig.character] if fig.character else [], actors=[p.name], side=self._side())
        p.snubbed_until[fid] = self.now + cfg.snub_hours * HOUR
        if season_one(c, w):
            wins.credit(p, c, w, calendar.point(w.time, c, w).week, cfg.figure_defeat_prestige * cfg.contrib_per_push)
        msgs += self._order_credit(  # 「打擊大勢人物」軍令（計畫 T6）：只算目標本人
            kind="challenge", location=p.location, front=figures.state_of(s, c, fid).front, figure=fid,
        )
        return msgs

    def _figure_treasure(self, fid: str, record) -> list[str]:
        """挑戰本人打贏掉寶物（裝備四欄 6.4；treasures.challenge_drop）：掉出來的那一件寫進這一場戰報的「得失」（record.materials），
        江湖紀錄寫撿到的那一句與放哪。不寫進 _battle_rewards：挑戰本人的戰報 kind 是 event，劇情戰也走那裡。"""
        item, lines = treasures.challenge_drop(self.state, self.content, fid, self.world.get_season_number(), record.id)
        if item is not None:
            record.materials.append(treasures.GAIN_LINE.format(name=item.name))
        return lines

    def _tier3(self, squad: Squad, record, chance: float, tag: str, source: str) -> list[str]:
        """三階素材的新來源（兵器設計 4.9；打造第二批）：擲 chance，中了照對手隊伍的屬性給一個三階素材（materials.tier3_pick），
        寫進這一場戰報的「得失」與江湖紀錄。自己一份亂數（「三階|季數|名號|戰報流水號|tag」；流水號每季從 1 起所以要季數，同
        treasures.challenge_drop），不碰 Game.rng：整季測試與量表的亂數序列不位移（FB-129）。序章不掉。
        source 寫在得失那一格的括號裡（挑戰本人、大場面；跟預設表掉的同一種合成一格，FB-147）。"""
        if chance <= 0 or prologue_rules.active(self.state, self.content):
            return []
        seed = f"三階|{self.world.get_season_number()}|{self.state.player.name}|{record.id}|{tag}"
        if random.Random(seed).random() >= chance:
            return []
        mid = materials.tier3_pick(self.content, squad.attribute, seed)
        line = materials.grant(self.state, self.content, mid) if mid is not None else None
        if not line:
            return []
        materials.add_cell(record.materials, self.content, mid, 1, source=source)
        return [materials.extra_line(self.content, mid, 1, source)]

    def _figure_tier3(self, fid: str, squad: Squad, record) -> list[str]:
        """挑戰本人打贏掉一個三階（兵器設計 4.9；challenge_tier3）：同一位人物對同一個人每季最多 tier3_per_figure 次（0＝不設限；
        正式值 1：這一季第一次打贏才有，挑戰每季都有設計丁 (c)；PlayerState.tier3_drops，角色每季重來自然清掉，同 treasure_drops）；
        挑戰本人掉的三階（連預設表那一條）一人一季最多 figure_rare_cap 個（figure_rare_drops）。"""
        rule, p, cap = self.content.config.forge_secrets, self.state.player, self.content.config.figure_rare_cap
        if rule.tier3_per_figure and p.tier3_drops.get(fid, 0) >= rule.tier3_per_figure:
            return []
        if cap and p.figure_rare_drops >= cap:
            return []
        got = self._tier3(squad, record, rule.challenge_tier3, f"挑戰|{fid}", materials.CHALLENGE_SOURCE)
        if got:
            p.tier3_drops[fid] = p.tier3_drops.get(fid, 0) + 1
            p.figure_rare_drops += 1
        return got

    def _figure_tier4(self, fid: str, squad: Squad, record) -> list[str]:
        """挑戰本人這一季第一次打贏某位人物另擲一個四階（正式季整合 4.5，第 4 批）：只看「這一季第一次」（PlayerState.tier4_wins，
        另一本帳，不讀三階的 tier3_drops；三階的 6 個滿了照擲），擲 Config.four_tiers.challenge_chance，一人一季最多 challenge_cap 個
        （tier4_challenge_drops，叛投不清）。屬性照他的隊伍（materials.tier_pick）。自己的亂數，不碰 Game.rng。素材四階關著、序章不擲。"""
        s, c = self.state, self.content
        p, cfg = s.player, c.config.four_tiers
        if not four_tiers.on(c) or prologue_rules.active(s, c) or fid in p.tier4_wins:
            return []
        p.tier4_wins.append(fid)
        if p.tier4_challenge_drops >= cfg.challenge_cap:
            return []
        seed = f"四階|{self.world.get_season_number()}|{p.name}|{record.id}|挑戰|{fid}"
        if random.Random(seed).random() >= cfg.challenge_chance:
            return []
        mid = materials.tier_pick(c, squad.attribute, seed, four_tiers.TIER)
        line = materials.grant(s, c, mid) if mid is not None else None
        if not line:
            return []
        p.tier4_challenge_drops += 1
        materials.add_cell(record.materials, c, mid, 1, source=materials.CHALLENGE_SOURCE)
        return [materials.extra_line(c, mid, 1, materials.CHALLENGE_SOURCE)]

    def _showdown_tier4(self, battle: battle_instance.BattleInstance, me: battle_instance.BattleParticipant, lines: list[str]) -> list[str]:
        """時刻表決戰得勝給一個四階（正式季整合 4.5，第 4 批）：長社、宛城、廣宗這種時刻表上的決戰，得勝那一方出手滿門檻的人各一個
        （門檻照奪璽單挑挑人那一條 seal.threshold：min(3, 實打回合)，參戰不到 small_battle 人放寬到 1）；臨時投效替得勝那一軍出手夠了也算。
        保底收場（沒有贏家）、天命之爭不給。屬性隨機（名號＋那一場的 record_id）。回要寫在得失的那一樣，戰報那一句接在 lines。"""
        c, s = self.content, self.state
        definition = c.battles.get(battle.battle_id)
        if (not four_tiers.on(c) or not c.config.four_tiers.showdown or definition is None or not definition.timetable_event
                or seal.is_mandate_battle(c, definition) or not battle.outcome_side or me.faction != battle.outcome_side
                or me.acted_rounds < seal.threshold(battle, c.config.seal)):
            return []
        rng = random.Random(f"決戰四階|{s.player.name}|{battle.record_id}")
        pool = sorted(m.id for m in c.materials.values() if m.tier == four_tiers.TIER)
        if not pool:
            return []
        mid = rng.choice(pool)
        line = materials.grant(s, c, mid)
        if not line:
            return []
        lines.append(SHOWDOWN_TIER4.format(name=c.materials[mid].name))
        return [f"{c.materials[mid].name} ×1"]

    def _held_tier3(self) -> int:
        """背包裡的三階素材合計（_challenge 照它算挑戰本人這一場的預設表掉了幾個三階，記進 figure_rare_drops）。"""
        mats = self.content.materials
        return sum(n for mid, n in self.state.player.materials.items() if n > 0 and mid in mats and mats[mid].tier == 3)

    def _train_push(self, trend_id: str, delta: int) -> int:
        """遊歷（打贏或操練）推大勢：量照地點設定；自己陣營對這條線有目標就往目標方向推，散人和
        沒有這條線目標的陣營照地點原本的方向（企劃者 2026-10-02 決定）。trend_id 是換算過、真的會動的那條線：
        豪強（目標只有割據）在亂局的戰線上遊歷時換成豪強割據（delta 已取絕對值、往漲的方向，見 train_trend_push），
        所以這裡乘上的是割據的目標；不在亂局的戰線上，豪強根本不會走到這裡（什麼都不推）。"""
        goal = self._goals().get(trend_id, 0)
        return abs(delta) * goal if goal else delta

    def _goals(self) -> dict[str, int]:
        """自己陣營的目標，照 rules.resolve_goals 換過鍵（開關關著時三條戰線都算黃巾聲勢）；散人是空的。
        照那一邊（_side）：豪強分屬兩軍的季是依附那一軍的目標，所以豪強的守勢行動、修築塢堡、遊歷也往那一軍推。"""
        faction = self.content.scenario.find_faction(self._side())
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

    def push_trend(self, trend_id: str, delta: float, *, source: str) -> list[str]:
        """玩家自己造成的大勢推動一律走這裡（遊歷、出陣、操練、事件效果；sim_tick、時刻表、決戰、管理者不是個人推動，不走）。
        第一季設計第七節的規則，掛在第一季開關後面——開關關著（或這一季開季時是關的）就是 change_trend，一個字都不變：
        1. 陣營人數緩衝：推力 ÷ √n，n＝自己陣營 active_window_days 個曆日內推過大勢的成員（含自己這一次、含假人，最少 1）；
        2. 每人每曆日對每條線的上限（緩衝後算）：超過的部分不推大勢；
        3. 貢獻帳：替自己陣營的目標方向推才記，contrib_per_push × 推力（不打緩衝的折），超過上限的部分只記 over_cap_contrib_ratio；
        4. 散人照推、照受上限，n 當 1，不記貢獻也不進活躍名單。
        緩衝後常有小數：不足一點的記在全服的 trend_accum（每條線一個），滿一點才真的推；回傳 change_trend 的訊息
        （第一季規則開著時戰線是機器可讀的戰況變化，畫面上換成一句話，見 front_lines；開關關著是既有的「（黃巾聲勢 +2）」），
        只有整數真的動了才有。
        出陣探索與地盤（2026-10-14）：推之前先照 _shaped 打事件五折、第一季出陣的季長倍數、盡頭阻力（三個開關都關著時一個字都不變），
        打了阻力的那一下後面多一句 push.RESISTED_LINE（站在自家控制的地方是 STEADY_LINE，_resisted_line）；每人每曆日上限讀 daily_push_cap；
        貢獻照收到的 delta（名目量）全額記。
        source 是註記（"train"、"sortie"、"drill"、"event"、"event_once"……），不存檔。"""
        s, c = self.state, self.content
        w, p = s.world, s.player
        amount, resisted = self._shaped(trend_id, delta, source)
        # 傳檄（玉璽碎片改版第 2 批）：那一軍的人在那條線上往自家目標推，乘在盡頭阻力與季長倍數之後、人數緩衝與每人每日上限之前（上限照舊）；
        # 貢獻照收到的 delta（名目量）記、不跟著放大。沒有傳檄時一個字都不變（不乘 1.0：int 會變成 float）
        if (writ := seal_acts.writ_factor(w, c, trend_id, self._side(), amount)) != 1.0:
            amount *= writ
        tail = [self._resisted_line()] if resisted else []
        if not calendar.season_one_on(w, c):
            # 規則關著的季，事件的大勢效果照季長縮放（FB-165，PM 2026-10-12：季長是週末的 5.6 倍、門檻不變，每一下照舊推就一定提早
            # 收季）：零頭跟操練記在同一個 trend_accum，滿一點才推、才寫推動那一行。隱藏線浮現的那一下照原本的量（浮現的規則不變）。
            # 遊歷打贏（source="train"）也照季長縮放（企劃者 2026-10-13，FB-168：不縮放的話兩天裡兩邊的遊歷就能把黃巾聲勢從 25
            # 推到 60 或砸到 0，決戰「要嘛第一天開、要嘛整季不開」）。決戰收場不走這裡、不縮放；操練的縮放在 _drill_push 先算好，
            # 傳進來的已經是整數點數。一季只會發生一次的事件（source="event_once"：事件標了 once，或這一下新立世界旗標，
            # rules.apply_effect 判斷）照原本的量（FB-166）。出陣（source="sortie"）跟遊歷打贏一樣照季長縮放；打過折
            # （事件五折、盡頭阻力）的量有零頭，一律記進 trend_accum。
            scale = self.season_scale() if source in ("event", "train", "sortie", "donate") else 1.0
            if (scale < 1 or amount != int(amount)) and is_revealed(w, c, trend_id):
                whole = self._carry(trend_id, amount * scale)
                return (change_trend(s, c, trend_id, whole) if whole else []) + tail
            return change_trend(s, c, trend_id, int(amount)) + tail
        if amount == 0 or (amount < 0 and not is_revealed(w, c, trend_id)):  # 開季時才補蓋章的季沒記到新加的公開線，照樣算浮現
            return []  # change_trend 也不會動的推動：不能拿來刷貢獻、也不算活躍
        cfg = c.config
        now = w.time
        at = calendar.point(now, c, w)
        window = cfg.active_window_days * DAY / calendar.cal_scale(c, w)
        key = f"{at.cal_day}:{trend_id}"
        side = self._side()  # 人數緩衝、貢獻、活躍名單都照那一邊（豪強分屬兩軍：依附的那一軍）
        pushed = push.buffered(abs(amount), push.active_count(s, side, now, window))
        used = push.used_today(p.pushed, at.cal_day, trend_id)
        moved, _ = push.split_by_cap(pushed, used, self.daily_push_cap())  # 還推得動多少只在 push.room_left 算（_push_room 也走它）
        p.pushed = push.recent_days(p.pushed, at.cal_day)
        p.pushed[key] = used + moved

        msgs: list[str] = []
        if moved > 0:
            whole, rest = push.take_whole(w.trend_accum.get(trend_id, 0.0), moved if amount > 0 else -moved)
            if rest:
                w.trend_accum[trend_id] = rest
            else:
                w.trend_accum.pop(trend_id, None)
            if whole:
                msgs = change_trend(s, c, trend_id, whole)

        if side is not None:  # 散人：照推，但不記貢獻、不進活躍名單
            faction = c.scenario.find_faction(side)
            goal = faction.goals.get(trend_id, 0) if faction is not None else 0
            # 捐軍備（source="donate"）的貢獻照捐的份量在 _donate 記，推力不另記（PM 2026-10-15）
            if source != "donate" and goal and (goal > 0) == (amount > 0):  # 替自己陣營的目標方向推；逆著推、這條線沒有目標都不記
                gained = push.contribution(abs(delta), pushed, moved, cfg.contrib_per_push, cfg.over_cap_contrib_ratio)
                wins.credit(p, c, w, at.week, gained)
            w.active_pushers.setdefault(side, {})[p.name] = now
        w.active_pushers = push.drop_stale(w.active_pushers, now, window)  # 順手清掉超過時窗的人，名單不會一直長
        return msgs + tail

    def _battle_rewards(self, squad: Squad, record, max_tier: int | None = None) -> list[str]:
        p = self.state.player
        msgs = []
        scale = self._loot_scale  # 練功分級的倍數（_practice 打的那一場才不是 1；Config.training）
        gate = self._gate_scale  # 減法季三道閘（遭遇拍那一場才不是 1）：經驗、心得、銀兩一起乘（乘 1 一個位元都不動）
        silver_won = round(squad.reward_silver * scale * gate)
        if silver_won:
            p.stats["silver"] += silver_won
            record.silver = silver_won
            msgs.append(f"銀兩 +{silver_won}")
        # 寶物「打贏的心得／經驗」（裝備四欄 6.2）；兩種數字不同，拆成兩個倍數。乘勝、悟招以前多給獎勵，本命戰法第三批起改成回合裡的戰法
        more_xinde = 1 + treasures.amount(self.state, self.content, "win_xinde_pct")
        more_exp = 1 + treasures.amount(self.state, self.content, "win_exp_pct")
        xinde = round(squad.reward_xinde * more_xinde * scale * gate)
        if xinde:
            p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
            record.xinde = xinde
            msgs.append(f"心得 +{xinde}")
        if not prologue_rules.active(self.state, self.content):  # 序章不掉素材（新手引導計畫一）
            got: list[str] = []  # 這一場掉到的素材（寶物「多掉一個素材」從這裡挑）
            if max_tier is None and record.kind in ("train", "wild"):  # 領地爭奪：剛易手的中立地，駐軍只掉一階（翻地與爭搶，冷卻期高階回饋暫停）
                max_tier = conquest.drop_cap(self.state.world, self.content, self.state.player.location)
            drops = materials.roll_squad_drops(squad, self.content, self.rng, max_tier=max_tier)  # 挑戰本人丁 (c) 才給 max_tier
            if self._drop_scale < 1:  # 減法季探索一顆的遭遇拍（城裡的地痞、三道閘）：掉的素材打折，用自己的亂數（不碰 Game.rng）
                drops = self._thin_drops(drops, record)
            for material_id, count in drops:
                line = materials.grant(self.state, self.content, material_id, count)
                if line:
                    got.append(material_id)
                    materials.add_cell(record.materials, self.content, material_id, count)  # 同一種合成一格（FB-140）
                    msgs.append(line)
            # 大場面對手的掉落表加三階（兵器設計 4.9）：另擲一次 big_tier3（自己的亂數）；大勢人物本人那支隊伍的那一個在 _challenge，不重複擲；
            # 探索野怪不算大場面（同大場面判讀：_squad_encounter 對野怪不問模型；CLAUDE.md「大場面」那一條）
            figure_squads = {fig.squad for fig in self.content.figures.values()}
            if record.kind != "wild" and self.is_big(squad) and squad.id not in figure_squads:
                msgs += self._tier3(squad, record, self.content.config.forge_secrets.big_tier3, "大場面", materials.BIG_SOURCE)
            if record.kind in ("train", "wild"):  # 兵器掉落與寶物多掉的素材（兵器設計 4.8、裝備四欄 6.2）：只有遊歷與探索野怪；劇情戰、挑戰本人（都是 kind=event）不掉
                extra = treasures.extra_drop(self.state, self.content, got, self.world.get_season_number(), record.id)  # 自己的亂數
                line = materials.grant(self.state, self.content, extra) if extra is not None else None
                if line:  # 照實多寫那一個：戰報的得失、江湖紀錄（設計 6.2）；跟掉到的同一種合成一格、寫是寶物多給的（FB-140）
                    source = self.state.player.treasure.name if self.state.player.treasure is not None else "寶物"
                    materials.add_cell(record.materials, self.content, extra, 1, source=source)
                    msgs.append(materials.extra_line(self.content, extra, 1, source))
                weapon, dropped_lines = weapons.drop(self.state, self.content, self.rng)
                if weapon is not None:
                    record.materials.append(weapons.GAIN_LINE.format(name=weapon.name))
                    msgs += dropped_lines
        # 經驗本來就是每人拿一樣多（FB-002），乘勝與寶物整隊一起乘；散人的遊俠名號每一階再多一成（ranger.exp_factor，陣營的人是 1）
        factor = ranger.exp_factor(self.state, self.content)
        exp = round(squad.exp * more_exp * factor * gate)
        exp_from = "encounter" if record.kind == "wild" else "battle"  # 都是仗（growth.BATTLE_KINDS）：減法季 45 級以後照算
        msgs += self._record_exp(record, exp, exp_from)
        levels, record.levelups = team.grant_team_exp(self.state, self.content, self.world, exp, exp_from)  # 每人都拿（FB-002）
        record.notes += levels  # 完整的句子留著（戰報頁、江湖紀錄）；戰鬥卡片畫 levelups 那一行簡短的（FB-074）
        why = renown.ranger_exp_note(self.state, self.content, factor)  # 名聲 6.3：散人的經驗加成說出原因
        record.notes += why
        return msgs + levels + why

    def _thin_drops(self, drops, record) -> list[tuple[str, int]]:
        """遭遇拍那一場掉的素材打 _drop_scale 折（減法季探索一顆：城裡的地痞、三道閘）：每一種的數量乘倍數，零頭照機率進位；
        亂數是自己的（「出門掉落|季數|名號|戰報流水號」），不碰 Game.rng。打到 0 的那一種不給。"""
        rng = random.Random(f"出門掉落|{self.world.get_season_number()}|{self.state.player.name}|{record.id}")
        out = []
        for material_id, count in drops:
            kept = int(count * self._drop_scale + rng.random())
            if kept > 0:
                out.append((material_id, kept))
        return out

    def _seize(self, record, draw: bool = False) -> list[str]:
        """絕學的契機（方案 C，cultivation.seize）：打贏了（險勝以上）、序章外，照這一場的難度比擲一次頓悟。
        draw：僵持也算（挑戰大勢人物本人，企劃者 2026-10-16），難度比照打贏的算法。
        說出來的話也記進這一場戰報的敘事（戰鬥卡片「結果」那一段）。"""
        tiers = (*team.WIN_TIERS, "僵持") if draw else team.WIN_TIERS
        if record.tier not in tiers or record.our_power <= 0 or prologue_rules.active(self.state, self.content):
            return []
        msgs = cultivation.seize(self.state, self.content, self.world, record.difficulty / record.our_power, self.rng)
        record.notes += msgs
        return msgs

    def _file_battle(self, record, wear: bool | None = None, armor_wear: bool | None = None, team_exp: bool = True) -> str:
        """歸檔一場戰報。wear：這一場要不要磨兵器（兵器設計 3.4）；None＝照戰報類型，劇情戰（kind=event）不磨，
        挑戰本人雖然也是 event，由 _challenge 明說要磨。armor_wear：要不要磨防具（裝備四欄設計 4.5）；None＝照 armor.wears
        （遊歷、探索野怪、截殺自己這一邊落敗才磨；切磋、頭目戰、劇情戰不磨），挑戰本人由 _challenge 明說要磨。全服決戰不走這裡。
        兩樣的提醒合在 _last_wear（兵器先、防具後），進戰鬥卡片也進江湖紀錄（防具照兵器的做法；設計第九節「戰報不寫防具」指的是
        不每一場寫一句省了多少，這一句只在低於 edge_warn 時出現一次）。截殺輸的一方先扣血（_raid_spoils）、後磨，
        所以那一場用的是磨之前的耐久（同兵器的時序）。team_exp：草稿的得失補「經驗 +N（每人）」（整隊拿經驗的仗）；
        切磋只有本人拿、經驗自己寫在訊息裡（FB-244），不補。"""
        self._last_wear = []
        if (record.kind != "event") if wear is None else wear:
            self._last_wear += weapons.wear(self.state, self.content, record.tier)
        if armor.wears(record.kind, record.tier) if armor_wear is None else armor_wear:
            self._last_wear += armor.wear(self.state, self.content, record.tier)
        record.notes += self._last_wear
        battlelog.add_record(self.state, record)
        self.state.battle_card = record.id
        line = battlelog.summary_line(record)
        if self._draft is not None:
            self._draft.outcome(battlelog.outcome_text(record), line)
            self._draft.battle_id = record.id
            self._draft.notes += self._last_wear
            if record.exp and team_exp:
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
        tasks = {"think": self._road_think, "ask": self._road_ask, "gather": self._road_gather}
        self._road_gain = None  # 這件小事的收穫（分給結伴同行的人，_share_road）；各個小事真的給了東西才填
        msgs = tasks[what]()
        return msgs + self._share_road(what, self._road_gain)

    def _road_ends(self) -> tuple[str, str]:
        """這段路的兩頭：身後那一站、前面那一站。"""
        spot = atlas.road_spot(self.state, self.content)
        return spot.behind, spot.ahead

    def _road_rewards_used(self, kind: str, day: int | None = None) -> int:
        """這一個遊戲日（rules.game_day，跟每天對話輪數同一個算法、跟著季長縮；不給就是此刻的）路上已經拿過幾次收穫；
        kind 是 "task"（路上小事）或 "sight"（見聞）。紀錄是別的號碼就當沒拿過。"""
        record = self.state.player.road_rewards_today.get(kind)
        return record[1] if record and record[0] == (day or game_day(self.content, self.state.world)) else 0

    def _road_reward_due(self, kind: str, day: int | None = None) -> bool:
        """這一個遊戲日路上這一種收穫還沒拿滿（企劃者 2026-10-03 決定的每天上限 road_reward_daily_cap）。"""
        return self._road_rewards_used(kind, day) < self.content.config.road_reward_daily_cap

    def _count_road_reward(self, kind: str, day: int | None = None) -> None:
        """記一次真的給出去的收穫（沒撿到東西的採集不算）。"""
        day = day or game_day(self.content, self.state.world)
        self.state.player.road_rewards_today[kind] = [day, self._road_rewards_used(kind, day) + 1]

    def _road_reopen(self, after: str) -> str:
        """路上收穫拿滿了那兩句括號裡的話：「〔換日的那一刻〕 {after}」；這一季之內不會再換日（rules.day_turn 是 "season"，
        day-scale 審查 M2）時是「這一季之內不會再有」（待 joy 潤）。"""
        kind, moment = day_turn(self.content, self.state.world)
        if kind == "later":  # 季末延後、換日寫不出那一刻（FB-102，待 joy 潤）：「之後才會再有」→「過一陣子才會再有」
            return "過一陣子" + after.removeprefix("之後")
        return f"{moment} {after}" if moment else "這一季之內不會再有"

    def _road_think(self) -> list[str]:
        """邊走邊想：心得（一次遊歷大約 12～20，這裡刻意少很多）。這個遊戲日的收穫拿滿了就照樣想，只是沒有心得
        （寫換日的那一刻，待 joy 潤）。"""
        if not self._road_reward_due("task"):
            return [f"你邊走邊想，這陣子想得夠多了，沒有新的心得（{self._road_reopen('之後才會再有')}）。"]
        p, amount = self.state.player, self.content.config.road_think_xinde
        p.stats["xinde"] = p.stats.get("xinde", 0) + amount
        self._count_road_reward("task")
        self._road_gain = ("xinde", amount)
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
        text = self.rng.choice(heard).text
        self._road_gain = ("rumor", text)
        return [f"你沿途向人打聽，聽說：{text}"]

    def _road_gather(self) -> list[str]:
        """路邊採集：一定機率撿到一樣一階素材；屬性照這段路兩頭的地點寫的素材（Location.materials），兩頭都沒寫就隨機。
        這個遊戲日的收穫拿滿了就不翻（也不擲骰，寫換日的那一刻，待 joy 潤）；撿到了才算一次收穫。"""
        s, c = self.state, self.content
        if not self._road_reward_due("task"):
            return [f"你留心路邊，這陣子已經撿夠了，沒再去翻（{self._road_reopen('之後再說')}）。"]
        if self.rng.random() >= c.config.road_gather_chance:
            return ["你在路邊翻找了一陣，沒找到什麼能用的。"]
        kinds = {c.materials[m].attribute for end in self._road_ends() for m in c.locations[end].materials if m in c.materials}
        pool = [m for m in materials.by_tier(c, 1) if m.attribute in kinds] or materials.by_tier(c, 1)
        if not pool:  # 內容裡沒有一階素材：當成沒找到
            return ["你在路邊翻找了一陣，沒找到什麼能用的。"]
        self._count_road_reward("task")
        found = self.rng.choice(pool).id
        self._road_gain = ("material", found)
        return ["你在路邊翻找了一陣。", materials.grant(s, c, found)]

    def _depart(self, route: atlas.Route, mode: TravelMode, pace: float | None = None) -> list[str]:
        """出發（地圖擴充設計 3.2、3.3）：趕路、疾行的體力出發時一次扣，照走法排好每一站的抵達時間。
        疾行立刻一站一站抵達；步行、趕路就在路上，之後由 sync／advance 補算抵達（見 _arrivals）。
        在路上改道、折返（路上設計 3.1）也從這裡出發：route 的第一段是半段路（origin、share 記著是哪條路、走掉幾成），
        新路程整個取代原本那一趟；原本已經扣的趕路體力不退。剛出發就折返（見 atlas.returns_at_once）不扣體力、當下就回到原地。
        騎著馬的體力與步調照出發這一刻的坐騎（裝備四欄 5.3）。"""
        s, c = self.state, self.content
        bounties.close_board(s.player)  # 動身了：城鎮的第二層選單（懸賞榜、鐵匠鋪）收起來，不留在路上
        s.player.parley_escort = None  # NPC 智能 2.1：自己動身就不是誰帶的路了（帶路那一支出發之後再寫回去）
        equipment.close_smith(s.player)  # 鐵匠鋪連同打造到一半的單子、停在哪一頁一起收
        mounts.close_market(s.player)  # 馬市也收起來（裝備四欄 5.5）
        if s.player.picking_donate:
            economy.close_donate(s)  # 軍需官那一串也收起來（素材與經濟設計第六節）
        if s.player.picking_dadian:
            self._close_dadian()  # 打點那一間店也收起來
        s.player.picking_arena = False  # 擂台也收起來
        if s.player.picking_tavern:
            tavern_rules.close(s)  # 酒肆也收起來
        rerouting = s.player.journey is not None
        start = None if rerouting else s.player.location
        parted = self._part_ways() if s.player.tagalong is not None and not rerouting else []  # 答應了結伴卻自己先走：散了
        minutes = route.minutes
        at_once = atlas.returns_at_once(s, c, route)  # 要在換掉原本那一趟之前看：它看的是現在在路上的位置
        pace = mounts.pace(s, c) if pace is None else pace  # 出發這一刻的步調（大勢人物帶路照他的腳程，parley）（裝備四欄 5.3）：寫進 Journey、排抵達時刻、紀錄的標籤都用這一個數；路上餓了、換了馬都不回頭改
        cost = atlas.route_stamina(s, c, route, mode)
        foot = atlas.route_foot_stamina(s, c, route, mode)  # 不算坐騎的那一份：結伴同行時跟著的人照自己的坐騎再省（_lead，5.8）
        s.player.stamina -= cost
        legs = [0.0] if at_once else list(route.legs)
        s.player.journey = Journey(
            mode=mode, path=list(route.path), arrive_at=atlas.arrival_times(s.world.time, legs, mode, pace=pace),
            origin=route.origin, share=route.share, pace=pace,
        )
        if self._draft is not None:
            self._draft.tag = "立刻折返" if at_once else atlas.MODE_NAMES[mode] + atlas.mode_when(minutes, mode, pace=pace)
            if cost:
                self._draft.changes.append(f"體力 -{cost}")
        verb = "改道" if rerouting else "動身"
        told = f"{s.player.name}{verb}{atlas.MODE_NAMES[mode]}前往{c.locations[route.path[-1]].name}，你跟著走。"
        party = parted + self._lead(start, foot, told)  # 結伴同行：跟著的人照抄這一趟（玩家互動第二層），體力各付各的
        if mode == "dash" or at_once:
            return party + self._arrivals()
        left = self._real_minutes(s.player.journey.arrive_at[-1] - s.world.time)
        msg = f"你{verb}{atlas.MODE_NAMES[mode]}前往{c.locations[route.path[-1]].name}，現實約 {left} 分鐘後抵達。"  # 只寫現實的倒數（FB-062）
        self._hide(msg)  # 場景會顯示「在路上」，紀錄只留標題與走法
        self._sync_battle_presence()
        return [msg] + party

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
                    msgs += self._ambush_check(came_from, stop, when)  # 設伏劫道：這一段路上有沒有埋伏（字典查一次，疾行也算）
                msgs += self._arrive(stop, client=client)
                if new_leg:
                    msgs += mounts.hunger(s, c, j.mode)  # 騎著馬走完一段（裝備四欄 5.4）：扣飽足度，第一次低到 30 以下提醒一次；掉頭回原地不扣
                if new_leg and not c.locations[came_from].prologue_only:  # 出師那段路不抽路上見聞
                    msgs += self._road_sight(c.locations[came_from].road_to(stop), stop, when)
            done = j.reached > j.last or s.world.ended
            if done:
                s.player.journey = None
                if s.player.tagalong is not None:  # 結伴同行到這一趟的最後一站就散了（玩家互動第二層）
                    msgs.append(f"一路同行到此，你與{s.player.tagalong.leader}拱手作別。")
                    s.player.tagalong = None
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

    def _arrive(self, loc_id: str, client: OllamaClient | None = None) -> list[str]:
        """抵達一站：照原本走到一個地點的規則——地點描寫、新手引導、大勢門檻。client 是這次抵達可以用的模型（只給江湖大事潤色）：
        None（計時器的抵達）就完全不叫模型；門檻照樣觸發。以前重遊的終點還在鎖內請模型補一句點綴，那句只進 GameState.log、
        畫面上看不到，卻佔著全服的行動鎖（2026-10-12 拿掉，見 _present）。"""
        s, c = self.state, self.content
        before = s.player.tutorial_step
        s.player.location = loc_id
        s.player.visited.add(loc_id)
        text = self.location_text()
        self._hide(text)
        # 糧車到了終點（路過也算）先交糧，再照原本的新手引導與門檻（計畫 T6）；呼叫的先後不能換
        convoy = self._convoy_arrives(loc_id) + bounties.on_arrive(s, c, self.world, loc_id)  # 懸賞榜的護送：走到終點就交差（路過也算）
        guide = self._guide(note_action(s, c, self.world, "move"))  # 出師的盤纏（序章步驟的獎勵）是這一趟路的結果，回在這裡
        if not explore_modes.is_town(c, c.locations[loc_id]):  # 走到城外（初入江湖逛鋪子那一步：沒進鋪子、直接出城也算過，Joy 2026-10-22）
            guide += self._guide(note_action(s, c, self.world, "leave_town"))
        thresholds = check_thresholds(s, c, self.world, client, now=self.now)
        t = c.tutorial
        left = [t.leave_text] if t.location is not None and before < t.prologue_steps <= s.player.tutorial_step and t.leave_text else []
        # 出師、抵達起點：「剛剛」先接一句草廬已經看不見了（新手引導設計 10.3），再寫盤纏（T7 審查 M4）
        return [text] + convoy + left + guide + thresholds

    def _road_sight(self, road: RoadKind, loc_id: str, when: float | None = None) -> list[str]:
        """路上見聞（路上設計第五節）：抵達一站時有 road_sight_chance 的機會，從符合這段路的種類、剛抵達那一站所在大區的
        見聞裡平均挑一則（最近看過的 road_sight_recent 則先排除，池子不夠才重複）。文字寫進這次抵達的紀錄，小收穫照慣例
        接在後面。寫好的文字、不呼叫模型，下線補算時照樣發生。機率是 0 或池子是空的時候連骰子都不擲。
        有收穫的見聞受每天上限管（企劃者 2026-10-03 決定，跟路上小事各算各的）：抵達那一個遊戲日（when，下線補算時是當時的
        抵達時間；遊戲日跟著季長縮，rules.game_day）的 "sight" 收穫拿滿了，給銀兩、素材的見聞就不挑（文字寫的就是拿到東西），
        給心得的照寫文字、不給心得；真的給了才算一次。沒有收穫的見聞不算次數。"""
        s, c = self.state, self.content
        day = game_day(c, s.world, when)
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
        line = f"往{c.locations[j.path[j.last]].name}（{atlas.MODE_NAMES[j.mode]}），現實約 {left} 分鐘後抵達"
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
            msgs.append("（趕路已經花掉的體力不退。）")  # 拿掉趕路之前出發、還在路上的那一趟
        msgs += self._lead(None, 0, f"{s.player.name}喊停，到了{c.locations[j.path[j.reached]].name}就停下來。")
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
        rare = event.once or event.qiyu  # 行狀：一次性的事、奇遇記下你怎麼選的（平常的事件太多，不記）
        what = f"遇上{'奇遇' if event.qiyu else ''}【{event.title}】，你選了「{choice.text}」"
        if choice.combat:
            if rare:
                annals.note(s, c, annals.DEED, what + "。", 3)
            msgs += self._event_battle(event, choice)
            return msgs + self._event_progress()  # 領地爭奪：在區塊了結一則事件推一次進度（開關關著是空的）
        if choice.check:
            success = roll_check(choice.check, s, c, self.world, self.rng)
            tag, line = check_result_line(success)  # 一律是本人：不寫誰出手（企劃者 2026-10-05）
            msgs.append(line)
            self._outcome(tag, line)
            if rare:
                annals.note(s, c, annals.DEED, what + ("，成了。" if success else "，沒成。"), 3)
            msgs += self._apply(choice.effect if success else failed(choice.fail_effect, c), once=event.once) + self._tale_clue(event)
            return msgs + self._event_progress()
        if rare:
            annals.note(s, c, annals.DEED, what + "。", 3)
        msgs += self._apply(choice.effect, once=event.once) + self._tale_clue(event)
        return msgs + self._event_progress()

    def _tale_clue(self, event: Event) -> list[str]:
        """說書的事件了結時，偶爾多一句說書版的口訣（武學，Config.secrets，tianxia/secret_recipes.py），記進武學譜；鑄器另擲一次
        （Config.forge_secrets，打造隱藏配方設計 6.2，兩句都中兩句都寫）。擲骰用自己的亂數，不動 self.rng。"""
        s, cfg = self.state, self.content.config.secrets
        if event.id not in cfg.tale_events:
            return []
        out = []
        seed = f"說書|{s.player.name}|{s.world.time}|{event.id}"
        if secret_recipes.roll(cfg.tale_chance, seed):
            clue = secret_recipes.hear(s, self.content, secret_recipes.tianji_of(self.world), secret_recipes.TALE, seed)
            if clue:
                out.append(cfg.tale_frame.format(clue=clue))
        return out + self._forge_clue(forge_secrets.TALE, f"鑄說書|{s.player.name}|{s.world.time}|{event.id}")

    def _scrap_find(self) -> list[str]:
        """探索最後再擲一次有沒有撿到殘譜（殘譜版的口訣），記進武學譜；再擲一次半張鑄譜（打造隱藏配方設計 6.2），記進鑄譜。
        同 _tale_clue 用自己的亂數。"""
        s, cfg = self.state, self.content.config.secrets
        out = []
        seed = f"殘譜|{s.player.name}|{s.world.time}|{s.player.location}"
        if secret_recipes.roll(cfg.scrap_chance, seed):
            clue = secret_recipes.hear(s, self.content, secret_recipes.tianji_of(self.world), secret_recipes.SCRAP, seed)
            if clue:
                out.append(cfg.scrap_frame.format(clue=clue))
        return out + self._forge_clue(forge_secrets.SCRAP, f"鑄殘譜|{s.player.name}|{s.world.time}|{s.player.location}")

    def _forge_clue(self, source: int, seed: str) -> list[str]:
        """說書與殘譜的鑄器口訣（打造隱藏配方設計 6.2）：擲 tale_chance／scrap_chance（自己的亂數），中了照 forge_secrets.hear 挑一句、
        記進鑄譜。"""
        rule = self.content.config.forge_secrets
        chance, frame = (rule.tale_chance, rule.tale_frame) if source == forge_secrets.TALE else (rule.scrap_chance, rule.scrap_frame)
        if not secret_recipes.roll(chance, seed):
            return []
        clue = forge_secrets.hear(self.state, self.content, secret_recipes.tianji_of(self.world), source, seed)
        return [frame.format(clue=clue)] if clue else []

    def _smith_clue(self, paid: bool = True) -> list[str]:
        """鐵匠順口（打造隱藏配方設計 6.2；計畫「要 PM 定的」第 3 條）：鐵匠鋪的動作不花時間，種子多帶這一下之後的銀兩與素材數，
        同一刻連按也各擲各的；中了說出這家知道的那一句（已經聽過不再說）。自己的亂數，不動 self.rng。
        paid：這一下有沒有收銀兩（一階淬煉只收素材）——沒收的那一句不寫「收錢」（smith_frame_free，FB-142）。"""
        s, rule = self.state, self.content.config.forge_secrets
        p = s.player
        seed = f"鐵匠|{p.name}|{s.world.time}|{p.location}|{p.stats.get('silver', 0)}|{sum(p.materials.values())}"
        if not secret_recipes.roll(rule.smith_chance, seed):
            return []
        clue = forge_secrets.hear_smith(s, self.content, secret_recipes.tianji_of(self.world))
        return [(rule.smith_frame if paid else rule.smith_frame_free).format(clue=clue)] if clue else []

    def _overhear(self, companion_id: str, msgs: list[str]) -> list[str]:
        """人物這一輪原字原句引出了他知道的那句口訣：記進武學譜，多一句提醒（第一次聽到才寫）。"""
        if secret_recipes.overheard(self.state, self.content, self.world, companion_id, "\n".join(msgs)):
            return [self.content.config.secrets.overheard]
        return []

    def _event_battle(self, event: Event, choice: Choice) -> list[str]:
        s, c = self.state, self.content
        squad = self._story_squad(c.squads[choice.combat])  # 大場面照江湖水漲浮上來
        judged = self._judged(squad)  # 打頭目這種大場面：有鎖外的判讀就用（武學與成長設計 8.3）
        result = self._fight_with(squad, judged, dodge=False, difficulty=squad.difficulty)  # 劇情戰的勝敗是人寫好的：不閃（最終審查 I1）
        record = battlelog.new_record(s, c, self.world, squad, result, "event", event.title)
        record.notes += self._style_note(squad, result) + self._terrain_note()  # 劇情戰不扣氣血，地利照寫：威力真的有算
        self._narrate(record, result, judged)
        # 回合照開打時的陣容與身法演，所以要在發獎勵、套效果之前：效果可能加身法、教武學、給同伴或部下，
        # 不能回頭改寫這一場（例如 wolves 打贏身法 +1，不能變成「因為獎勵才先出手」）。
        # 劇情戰不扣氣血：對手的出手不寫數字（計畫三 G5）
        self._play_rounds(record, squad, result.tier, None, self._hp_facts(), clash=result.clash)  # 氣血照開打時的樣子：厚拉高的下限這一場也起了作用
        won = result.tier in team.WIN_TIERS
        rewards = self._battle_rewards(squad, record) if won else []
        effect = choice.effect if won else failed(choice.fail_effect, c)  # 打輸另扣的體力減半，同檢定失敗（企劃者裁決 E6）
        story = apply_effect(effect, s, c, self.world, push=self.push_trend, once=event.once)
        changes, notes = battlelog.split_changes(story, for_record=True)
        record.changes += changes
        record.notes += notes
        story += self._seize(record)
        msgs = [self._file_battle(record)] + rewards + story
        if self.is_big(squad) and not prologue_rules.active(s, c):  # 名聲 4.5：天下聞名打大場面點名
            self._famed_news(c.locations[s.player.location].name, squad.name, result.tier)
        if effect.next_event:
            msgs += self._present(c.events[effect.next_event])
        return msgs

    def _apply(self, effect: Effect, once: bool = False) -> list[str]:
        """套用事件選項的效果；once＝事件標了 once（推大勢不照季長縮放，FB-166，rules.apply_effect）。"""
        msgs = apply_effect(effect, self.state, self.content, self.world, push=self.push_trend, once=once)
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
            and s.player.journey is None and not s.player.picking_audience
            and not s.player.picking_bounty and not s.player.picking_smith  # 懸賞榜、鐵匠鋪開著：選單卡在第二層，先離開（FB-121 第 4 件）
            and s.player.fs_asking is None  # 伏筆的最後一步正在答題：跟事件待處理一樣，先答完或作罷
            and s.player.sensing is None  # 有所感、還沒了結：跟事件待處理一樣
            and s.player.duel is None  # 單人頭目戰打到一半：同上
            and not s.player.picking_market  # 馬市開著：選單卡在第二層，先離開（同 FB-121 第 4 件的懸賞榜、鐵匠鋪）
            and not s.player.picking_donate  # 軍需官那一串開著：同馬市
            and not s.player.picking_dadian  # 打點那一間店開著：同馬市
            and not s.player.picking_tavern  # 酒肆開著：同馬市
            and not s.player.picking_arena and s.player.arena is None  # 擂台開著、打到一半：同上
            and not allied.needs_ally(s, self.content)  # 拜入之後還沒挑依附哪一邊（豪強分屬兩軍）：先挑
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
        # 寶物「閉關心得」（裝備四欄 6.2）：照出關那一刻身上那件算——寶物隨時能換（2.3【定】，企劃者 2026-10-11），閉關到一半換上也算
        bonus = 1 + treasures.amount(self.state, self.content, "seclusion")
        amount = round(hours * cfg.seclusion_xinde_per_hour * (1 + p.stats["wis"] / 20) * bonus)
        p.busy_until = None
        p.seclusion_done = end_time  # 天時地利的「心靜」：出關之後一陣子開爐（fusion.setting_points）
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
        self, art_id: str | None, insight_ids: list[str], named_outside: bool = False,
    ) -> naming.NamingRequest | None:
        """開爐首次取名或挑選的 A 段（呼叫端在行動鎖內、很快地呼叫；server.prepare_forge、bot_policy.tend_arts）：這一爐要不要模型？
        要就回送模型的單子（naming.NamingRequest），由呼叫端在鎖外交給 naming.generate（B 段），再進鎖把結果交給
        forge(..., proposed=...)（C 段）。單子有兩種：沒人合過、長新的 → 取名（choices 是空的）；合到舊的、候選兩個以上
        → 從候選挑一個（choices 是候選的名字，見 fusion.forge_request）。不要的時候是 None：這個 Game 沒有 client
        （例如伺服器假人鎖內的 Game）而且呼叫端不會自己叫模型、賽季籌備中、這一爐會被拒絕、配方已經有人登記、合到舊的而且
        只有一個候選。只讀、不改狀態——跟 dialogue_request 同一個做法。煉製只剩意境＋意境（Joy 2026-10-21），art_id 有就是 None。
        named_outside：呼叫端會在鎖外自己叫模型（伺服器假人程式：它的 Game 沒有 client，B 段用 bot_runner 自己的 client
        叫 naming.generate），照樣開單。"""
        if (self.client is None and not named_outside) or self._preparing():
            return None
        if art_id or prologue_rules.fuse_problem(self.state, self.content, insight_ids) is not None:
            return None  # 會被擋下的一爐：不開取名的單子（forge 照常回那句話）
        return fusion.forge_request(self.state, self.content, self.world, art_id, insight_ids)

    @_not_while_preparing
    def forge(
        self, art_id: str | None, insight_ids: list[str], proposed: tuple[str | None, str] | None = None,
    ) -> list[str]:
        """煉製頁的開爐：只剩兩個意境（不同的＝合成、同一種的兩份＝揣摩；見 fusion.py）。武學＋武學、武學＋意境 Joy 2026-10-21
        拿掉了：art_id 有就回 ART_IN_FURNACE（意境到修練頁裝進武學的槽）。
        proposed 是鎖外先取好的（名字, 說明）（C 段，見 forge_request）：這裡整個重驗（A 段之後意境可能熔掉、心得或體力
        可能花掉、配方可能被別人或同一個人的另一個請求登記了），名字再過一次過濾、登記時原子判斷重名，過不了走退路字表；
        給了 proposed 就不會在這裡叫模型（伺服器與假人程式一律給，不需要模型時是 (None, "")）。沒給（整季機器人、腳本、測試）
        首次出現的配方照舊在這裡叫模型，那是在行動鎖內，所以用 _quick_client 的短逾時複本，取不到名字就走退路字表。
        江湖紀錄的標題照煉製頁寫「煉製」（FB-047），做成了才寫，被拒絕只回一句話、什麼都不收。
        合成花心得與體力（設計 12.1）：花了的體力跟心得一起寫在這一則的數值變化上。"""
        self.forged = False
        self.forged_thing = None
        self.secret_solved = None
        if art_id or len(insight_ids) != 2:
            return self._log([fusion.ART_IN_FURNACE if art_id else fusion.TWO_INSIGHTS])
        refusal = prologue_rules.fuse_problem(self.state, self.content, insight_ids)  # 序章只准照劇本合成
        if refusal is not None:
            return self._log([refusal])
        xinde, stamina = self._xinde(), self.state.player.stamina
        solved = self._solved_secrets()
        mixed = insight_fx.base_id(insight_ids[0]) != insight_fx.base_id(insight_ids[1])  # 兩種不同的意境（合成；同一種是揣摩）
        insight, msgs = fusion.merge(self.state, self.content, self.world, self._quick_client(), *insight_ids, proposed=proposed)
        tag = f"合併「{insight.name}」" if insight is not None else None
        if insight is not None:
            self.forged_thing = ("ins", insight.id)
            if mixed:
                self.state.player.newbie_marks.add("merge")  # 新手目標：在煉製合出一個新的意境
        out = self._log(msgs)
        self.forged = tag is not None
        if tag is not None:
            self._save_season()  # 首創秘方會記一則傳聞（fusion._secret_lines）；傳聞在共用賽季裡，要存回去
            spent = round(stamina - self.state.player.stamina)  # 三種合成都花體力：數值變化寫在紀錄上，跟修練一樣
            out += self._menxia_entry(  # 結果那一句（第一則訊息）也寫進這一則的敘事，拿到新東西的那一行才配得到 journal._NEW_THING（FB-073）
                tag, xinde, guide=True, title=journal.CRAFT, extra=[f"體力 -{spent}"] if spent > 0 else None,
                lines=out[:1],
            )
            self._note_solved(solved)
        return out

    def _solved_secrets(self) -> list[str]:
        """這一季已經參透的秘方（開爐、裝意境之前記一份，做完跟 _note_solved 比）。"""
        return list(secret_recipes.manual(self.state, secret_recipes.tianji_of(self.world)).solved)

    def _note_solved(self, before: list[str]) -> None:
        """這一下動作參透了新的秘方：另寫一則標題「武學譜」的江湖紀錄（煉製那一則只收結果第一句，參透那句會被丟掉；
        玩家回報 2026-10-25），記下要跳的視窗（secret_solved）。"""
        fresh = [r for r in secret_recipes.manual(self.state, secret_recipes.tianji_of(self.world)).solved if r not in before]
        recipe = next((r for r in secret_recipes.active(self.content, secret_recipes.tianji_of(self.world)) if r.id in fresh), None)
        if recipe is None:
            return
        card = secret_recipes.solved_card(self.state, self.content, self.world, recipe)
        self.secret_solved = card
        journal.add_entry(self.state, JournalEntry(
            time=self.state.world.time, title=journal.MANUAL, tag=f"參透「{card['name']}」",
            lines=[card["note"]] if card["note"] else [],
        ))

    def forge_line(self, insight_ids: list[str]) -> str:
        return skillview.forge_line(self.state, self.content, self.world, insight_ids)

    def forge_preview(self, insight_ids: list[str]) -> dict | None:
        """兩格都放好時煉製頁的預覽卡（skillview.forge_preview）。只讀。"""
        return skillview.forge_preview(self.state, self.content, self.world, insight_ids)

    def forge_picks(self, insight_ids: list[str]) -> dict | None:
        """爐裡只放了一個意境時，另一格放得進來的每一個合不合得了（skillview.forge_picks）。只讀。"""
        return skillview.forge_picks(self.state, self.content, self.world, insight_ids)

    @_not_while_preparing
    def cultivate(self, art_id: str, use_legend: bool = False) -> list[str]:
        """修練（武學重構，Joy 2026-10-20）：品級不靠修練衝，這裡只剩上品到了極處（第十成）服一枚破境丹強行衝絕學
        （見 cultivation.py）。花體力與一枚丹。真的擲了骰才寫江湖紀錄；被拒絕（還沒到極處、沒有丹、體力不足、沒有這門武學）只回一句話。
        use_legend：玩家按的是「服丹衝關」；沒有就只回「等契機或服丹」那一句。"""
        problem = cultivation.cultivate_problem(self.state, self.content, self.world, art_id, use_legend=use_legend)
        if problem is not None:
            return self._log([problem])
        xinde, stamina, pills = self._xinde(), self.state.player.stamina, self.state.player.legend_items
        msgs = cultivation.cultivate(self.state, self.content, self.world, art_id, self.rng, use_legend)
        spent = round(stamina - self.state.player.stamina)  # 沒衝開也花了體力：數值變化寫在紀錄上，跟別的行動一樣
        taken = pills - self.state.player.legend_items
        extra = ([f"體力 -{spent}"] if spent > 0 else []) + (
            [f"{self.content.config.legend_item_name} -{taken}"] if taken > 0 else []
        )
        # 結果標記是擲骰的結果（「【X】衝開了…」「【X】撞在…」，一定以【開頭）；前面服丹那一句與後面定名的話都不是
        # 自創的那一門衝開了是「閉門衝關，〔招〕撞開了…【X】破境」（ascend.FORCED_LINE），不以【開頭，另外認
        tag = next((m for m in msgs if m.startswith("【") or m.startswith(ascend.FORCED_LINE.split("〔")[0])), msgs[0])
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
            shown = self._art_name(pending)
            annals.note(self.state, self.content, annals.DEED, f"江湖上第一個把【{pending}】練成絕學的人，定名【{shown}】。", 5)
        return msgs

    @_not_while_preparing
    def name_divine(self, item_id: str, name: str = "", keep: bool = False) -> list[str]:
        """神器原品定名（smithing.name_divine；修練頁裝備庫那一列的表單，或「沿用譜名」那一顆）：定成了才寫江湖紀錄，
        江湖史與傳聞寫進共用賽季所以要存回（不合格、被用掉、不是你的都只回一句話）。"""
        xinde = self._xinde()
        ok, msgs = smithing.name_divine(self.state, self.content, self.world, item_id, name, keep=keep)
        msgs = self._log(msgs)
        if ok:
            self._menxia_entry(msgs[0], xinde)
            self._save_season()
        return msgs

    @_not_while_preparing
    def bind_art(self, item_id: str, art_id: str) -> list[str]:
        """以器配招（玩家武學追上本命定案 四；smithing.bind_art）：神器原品綁自己一門有絕招的絕學。綁成了才寫江湖紀錄。"""
        xinde = self._xinde()
        ok, msgs = smithing.bind_art(self.state, self.content, self.world, item_id, art_id)
        msgs = self._log(msgs)
        if ok:
            self._menxia_entry(msgs[0], xinde)
        return msgs

    @_not_while_preparing
    def switch_art(self, art_id: str) -> list[str]:
        """改練：把功法庫裡的一門換上身（見 team.switch_art）。"""
        xinde = self._xinde()
        msgs = self._log(team.switch_art(self.state, self.content, self.world, art_id))
        # 江湖紀錄的標記是「你改練【…】」那一句；換上後內外搭配變了時最後多一句（FB-088），不拿它當標記
        tag = next((m for m in reversed(msgs) if m.startswith("你改練")), msgs[-1] if msgs else "改練")
        switched = any(m.startswith("你改練") for m in msgs)  # 真的換上了才算序章「比一比，換上或熔掉」那一步（新手引導重做）
        self._menxia_entry(tag, xinde, guide=switched, action="switch")
        return msgs

    # ── 自創武學（五步：執器、擺式、立意、成形、立名；tianxia/create.py）──────────────────

    @_not_while_preparing
    def create_begin(self, kind: str, form: str) -> list[str]:
        """執器：內功或武學、兵器種類或行功之法。只開單、不收錢、不寫紀錄。"""
        return self._log(create.begin(self.state, self.content, kind, form))

    @_not_while_preparing
    def create_pose(self, pose: dict) -> list[str]:
        """擺式：火柴人的九個角度（create.POSE_KEYS）。只改單子。"""
        return self._log(create.set_pose(self.state, self.content, pose))

    def create_request(self, text: str) -> create.IntentRequest | list[str]:
        """立意的 A 段（鎖內、只讀）：送得出去回傳要在鎖外請模型讀的單子，不行回傳那一句話。"""
        if self._preparing():
            return [PREPARING_REFUSAL]
        problem = create.intent_problem(self.state, self.content, text)
        if problem is not None:
            return [problem]
        return create.request(self.state, text)

    @_not_while_preparing
    def create_intent(self, text: str, reading: create.IntentReading | None = None) -> list[str]:
        """立意（C 段，或直接呼叫）：reading 是鎖外讀好的；沒給（假人、整季機器人、腳本）照關鍵字表讀。
        記下之後馬上成形（擲四格顏色），心得在這一刻收（一張單子一次，Joy 2026-10-21）：收了寫一則煉製紀錄。"""
        xinde = self._xinde()
        msgs = self._log(create.set_intent(self.state, self.content, self.world, text, reading))
        if self._xinde() != xinde:
            self._menxia_entry(msgs[0], xinde, title=journal.CRAFT, action="forge")
        return msgs

    def create_reread_request(self, text: str) -> create.IntentRequest | list[str]:
        """重讀這句意的 A 段（鎖內、只讀）：送得出去回傳要在鎖外請模型讀的單子，不行回傳那一句話。"""
        if self._preparing():
            return [PREPARING_REFUSAL]
        problem = create.reread_problem(self.state, self.content, text)
        if problem is not None:
            return [problem]
        return create.request(self.state, text)

    @_not_while_preparing
    def create_reread(self, text: str, reading: create.IntentReading | None) -> list[str]:
        """重悟帖：重讀這句意（C 段，create.reread）。reading 是 None（模型叫不動）什麼都不改、不扣帖。"""
        return self._log(create.reread(self.state, self.content, self.world, text, reading))

    @_not_while_preparing
    def create_reroll(self) -> list[str]:
        """重悟帖：成了形直接重骰（create.reroll）。只改單子與帖數。"""
        return self._log(create.reroll(self.state, self.content, self.world))

    @_not_while_preparing
    def create_back(self, to: str) -> list[str]:
        """回頭重擺式或重立意（成形之後回頭用掉一次重來）。"""
        return self._log(create.back(self.state, self.content, to))

    @_not_while_preparing
    def create_name(self, name: str, move: str | None = None) -> list[str]:
        """立名：付心得、登記（create.finish，一律上品）；move 是招名（空的照模型起的）。做成了寫一則煉製紀錄，被拒絕只回一句。"""
        xinde = self._xinde()
        art, msgs = create.finish(self.state, self.content, self.world, name, move)
        self.forged = art is not None
        self.forged_thing = ("art", art.id) if art is not None else None
        msgs = self._log(msgs)
        if art is not None:
            self._menxia_entry(msgs[0], xinde, guide=True, title=journal.CRAFT, action="forge", lines=msgs[1:])
        return msgs

    @_not_while_preparing
    def create_cancel(self) -> list[str]:
        return self._log(create.cancel(self.state))

    def ascend_request(self):
        """破境卡那一句的 A 段（鎖內、只讀）：有一張還沒寫那一句的卡，回請模型寫的單子；沒有是 None。"""
        return ascend.request(self.state)

    def ascend_line(self, req, line: str) -> list[str]:
        """破境卡那一句的 C 段：卡還是同一張才存。"""
        return ascend.set_line(self.state, req, line)

    def ascend_dismiss(self) -> list[str]:
        """看過破境卡了，收掉。"""
        return ascend.dismiss(self.state)

    def create_view(self) -> dict:
        """煉製頁「自創」那一塊（create.view）。只讀。"""
        return create.view(self.state, self.content, self.world)

    @_not_while_preparing
    def slot_insight(self, art_id: str, insight_id: str, index: int | None = None) -> list[str]:
        """把一個意境裝進一門武學的意境槽（武學重構；修練頁與煉製頁都走這裡，MENXIA_ACTIONS["slot"]）：不花心得體力，
        裝成了寫一則「裝意境」江湖紀錄，被拒絕只回一句。"""
        xinde = self._xinde()
        self.secret_solved = None
        problem = prologue_rules.slot_problem(self.state, self.content, art_id) or arts_mod.slot_problem(
            self.state, self.content, self.world, art_id, insight_id, index)
        if problem is not None:
            self.forged = False
            return self._log([problem])
        solved = self._solved_secrets()
        msgs = self._log(arts_mod.slot(self.state, self.content, self.world, art_id, insight_id, index))
        self.forged = True
        self.forged_thing = None
        self._menxia_entry(msgs[0], xinde, guide=True, action="slot")
        self._note_solved(solved)
        return msgs

    @_not_while_preparing
    def unslot_insight(self, art_id: str, insight_id: str) -> list[str]:
        """把一個意境從武學的槽上拆下來（MENXIA_ACTIONS["unslot"]）：不花東西；拆成了寫一則江湖紀錄。"""
        xinde = self._xinde()
        problem = prologue_rules.slot_problem(self.state, self.content, art_id)
        if problem is not None:
            return self._log([problem])
        slots = self.state.player.art_slots.get(art_id, [])
        msgs = self._log(arts_mod.unslot(self.state, self.content, self.world, art_id, insight_id))
        if insight_id in slots:
            self._menxia_entry(msgs[0], xinde)
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
    def melt_many(self, art_ids: list[str], insight_ids: list[str]) -> list[str]:
        """批量熔煉（見 library.melt_many）：修練頁勾好的武學與意境一次熔完，寫一則江湖紀錄。
        序章裡一門一門照師父說的熔（序章的熔煉是教學的一步），這裡直接回一句。"""
        if prologue_rules.melt_only(self.state, self.content) is not None or (
            insight_ids and prologue_rules.melt_insight_problem(self.state, self.content) is not None
        ):
            return self._log([MELT_MANY_PROLOGUE])
        xinde, held = self._xinde(), library.held_count(self.state)
        msgs = self._log(library.melt_many(self.state, self.content, self.world, art_ids, insight_ids))
        if library.held_count(self.state) < held:
            self._menxia_entry(msgs[0], xinde)
        return msgs

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
        """修練頁的療傷鈕：只在醫館做得了（clinic.py；不在醫館回「這裡沒有醫館，最近的在…」，什麼都不動）。"""
        xinde = self._xinde()
        msgs = self._log(self._heal_msgs())
        self._menxia_entry(msgs[0] if msgs else "療傷", xinde, guide=True, action="heal")  # 初入江湖「去醫館療傷」（新手引導第四段）
        return msgs

    @_not_while_preparing
    def take_stamina_pill(self, *, pill_only: bool = False) -> list[str]:
        """服一顆回體丹（企劃者 2026-10-07）：體力回 stamina_pill_restore，夾在上限。沒有丹、體力是滿的、還在草廬序章裡
        （序章的體力是照步驟算好的：探索、合成、修練剛好用完，接著才教調息，prologue.start_stamina）、今天已經服滿
        （stamina_pills_per_day，pills_left_today）都只回一句話、不收丹。吃了才寫江湖紀錄（數值變化寫體力與丹）。
        測試期間 Config.beta_free_refill 打開時，同一個入口改成免費補滿（_refill_stamina），不收丹。pill_only 是給假人與
        整季機器人的：他們照舊只吃丹（bot.take_pill），不吃這份測試期間的免費補滿；開關關著時 pill_only 沒有作用。"""
        p, cfg = self.state.player, self.content.config
        hut_pill = prologue_rules.pills_open(self.state, self.content)  # 序章教服丹那一步起（新手引導重做）：照真的服一顆
        if cfg.beta_free_refill and not pill_only and not hut_pill:
            return self._refill_stamina()
        name = cfg.stamina_pill_name
        if p.stamina_pills <= 0:
            return self._log([f"你身上沒有{name}了。"])
        if prologue_rules.active(self.state, self.content) and not hut_pill:
            return self._log([f"草廬裡先照師父說的做，{name}留著出了草廬再吃。"])
        if self.pills_left_today() == 0:
            return self._log([PILL_DAY_FULL.format(n=_cn_count(self.pill_cap()))])
        if p.stamina >= cfg.stamina_max:
            return self._log(["體力是滿的，這時候服丹是糟蹋。"])
        before = p.stamina
        p.stamina = min(float(cfg.stamina_max), p.stamina + cfg.stamina_pill_restore)
        p.stamina_pills -= 1
        today = self._pill_day()
        p.pills_today = (p.pills_today if p.pill_day == today else 0) + 1
        p.pill_day = today
        msgs = [f"你服下一顆{name}，一股暖意自丹田散開，精神為之一振。"]
        journal.add_entry(self.state, JournalEntry(
            time=self.state.world.time, title=f"服下{name}", lines=msgs,
            changes=[f"體力 +{round(p.stamina - before)}", f"{name} -1"],
        ))
        p.guide_done = []
        rewards = self._guide(note_action(self.state, self.content, self.world, "pill"))  # 序章「服一顆回體丹」（新手引導重做）
        return self._log(msgs + [f"體力 +{round(p.stamina - before)}（{name}還剩 {p.stamina_pills} 顆）"] + rewards)

    @_not_while_preparing
    def check_in(self, attribute: str = "") -> list[str]:
        """每日簽到（21 天季，正式季整合 6.2；tianxia/checkin.py）：領今天的份，四階的日子帶 attribute（剛柔快慢）。草廬序章裡不簽
        （同回體丹）；關著、簽過了、沒挑或挑錯四階都只回一句、什麼都不動。成了寫一則「簽到」江湖紀錄（數值變化寫丹、銀兩、素材）。"""
        s, c = self.state, self.content
        if checkin.on(c, s.world) and opening_rules.pending(s, c):  # 開局第一分鐘：三選一還沒選，福利之後寫進紀錄、不當第一張卡
            return self._log([opening_rules.GATE])
        if checkin.on(c, s.world) and prologue_rules.active(s, c):
            return self._log([checkin.HUT])
        result = checkin.claim(s, c, s.world, attribute)
        if isinstance(result, str):
            return self._log([result])
        lines, changes = result
        journal.add_entry(s, JournalEntry(time=s.world.time, title=checkin.TITLE, lines=lines, changes=changes))
        return self._log(lines + changes)

    def _auto_checkin(self) -> None:
        """每日簽到自動領（減法季批 1；Joy 2026-10-24 挑了江湖頁乙案：簽到不放鈕）：每天第一次同步時，今天的份不必挑的就直接領、
        寫一則「簽到」江湖紀錄（同 check_in，「剛剛」那一行會寫出來）；要挑四階的日子不動，江湖頁冒一張挑屬性的小卡（status.checkin.pick），
        挑了才領（check_in）。草廬序章裡不簽（同 check_in）。假人照舊在 bot.check_in 自己簽，先同步到的這裡順手領了也只是同一份。"""
        s, c = self.state, self.content
        if prologue_rules.active(s, c) or opening_rules.pending(s, c):
            return
        day = checkin.due(s, c, s.world)
        if day is None or checkin.needs_pick(c, day):
            return
        result = checkin.claim(s, c, s.world)
        if isinstance(result, str):
            return
        lines, changes = result
        journal.add_entry(s, JournalEntry(time=s.world.time, title=checkin.TITLE, lines=lines, changes=changes))

    def checkin_view(self) -> dict | None:
        """江湖頁「簽到」小標的資料（checkin.view）：簽到關著、草廬序章裡、過了這一季最後一天（管理者把季末往後排）是 None。"""
        s, c = self.state, self.content
        if not checkin.on(c, s.world) or not checkin.in_season(c, s.world) or prologue_rules.active(s, c) or opening_rules.pending(s, c):
            return None
        return checkin.view(s, c, s.world)

    # ── 領地爭奪：翻地與爭搶（輿圖簡化設計第四章）——戰書、換天的掛鉤、分紅送到、畫面資料。投票與 22:00 公告結算拿掉了（PM 2026-10-20）──

    def _conquest_side(self) -> str | None:
        """替哪一軍推進度、下戰書、打攻城（豪強分屬兩軍：依附的那一軍）；散人、不是兩軍是 None。"""
        side = allied.side_of(self.state, self.content)
        return side if side in conquest.SIDES else None

    def _letter_key(self) -> int:
        """今天是第幾天（conquest_day.day_key：當地 22:00 換天；一邊一天一張戰書照它算）。"""
        return conquest_day.day_key(self.pill_now(), self.content.config)

    def letter_problem(self, loc: str) -> str | None:
        """下不了戰書的那一句（不含括號）；下得了是 None（設計 4.4、第九章第 13 條）：這一週在任的第 4 階（ranks.rank_of）、自己那一邊在這一塊的
        進度到 letter_at、這一塊推得動、這一邊今天還沒下過（conquest.letter_problem），排得出時段。假人不下（bot_policy 不按），規則本身不看。"""
        c, w = self.content, self.state.world
        if not conquest.on(c, w) or w.conquest is None:
            return CONQUEST_OFF
        if w.ended:
            return CONQUEST_ENDED
        side = self._conquest_side()
        if side is None or ranks.rank_of(self.state) != ranks.SEAT_RANK:
            return LETTER_RANK
        if loc not in c.locations:
            return conquest.WHY_OUT
        problem = conquest.letter_problem(w, c, side, loc, self._letter_key())
        if problem is not None:
            return problem
        slot = conquest.frozen(w, loc)
        if slot is None and conquest_day.next_slot(w, c, self.pill_now()) is None:
            return LETTER_NO_SLOT
        return None

    def conquest_letter(self, loc: str) -> list[str]:
        """下戰書（MAIN_ACTIONS["conquest_letter"]；輿圖的卡上那一顆，第 4 批畫）：照 conquest_day.place_letter 排一場攻城（最近的時段；同一塊
        別一邊下了、還沒開集結就併進那一場），那一塊凍結到打完。天下大事一句（具名）、江湖紀錄一則、存季。"""
        problem = self.letter_problem(loc)
        if problem is not None:
            return self._log([f"（{problem}。）"])
        c, w = self.content, self.state.world
        side = self._conquest_side()
        before = list(conquest.frozen(w, loc).attackers) if conquest.frozen(w, loc) is not None else []
        placed = conquest_day.place_letter(w, c, side, loc, self.state.player.name, self.pill_now())
        if placed is None:
            return self._log([f"（{LETTER_NO_SLOT}。）"])
        slot, _ = placed
        names = {f.id: f.name for f in c.scenario.factions}
        when, place = self.stamp(slot.at), c.locations[loc].name
        if before:
            line = LETTER_JOINED.format(side=names.get(side, side), time=when, others="、".join(names.get(a, a) for a in before), place=place)
        else:
            line = LETTER_DONE.format(side=names.get(side, side), time=when, place=place)
        self._write(LETTER_TITLE, [line])
        self._save_season()
        return self._log([line])

    def _conquest_tick(self, save: bool = True) -> list[str]:
        """領地爭奪：換天（當地 22:00，conquest_day.day_key 照 pill_now）的掛鉤——前幾天排的、到現在還沒開集結的攻城作罷（conquest_day.day_turn），
        收場的攻城戰從共用狀態拿掉。第一個看到新的一天的人觸發（sync、伺服器的排程 world_tick、快轉 advance 都叫）；**日子只准往前走**
        （ConquestState.settled_key，同 arena.roll_day 的教訓：快轉過的 Game 與照現實時間的 Game 輪流同步不重排、不倒退）。這一季第一次只記下今天。
        開關關著、季收了、暫停中什麼都不做（不碰 WorldState）。save 是假時不存季（advance 自己存）。
        第三批 A〈天下形勢〉（開著時，xingshi.on）：一開頭先看還在等模型的那一張單過了 grace_seconds 沒有（照固定段收，季收了也收）；
        第一次只記下起點（_xingshi_start），之後每一次換天（day_turn）之後開一張新的（_xingshi_open）。"""
        c, w = self.content, self.state.world
        if not conquest.on(c, w) or w.conquest is None:
            return []
        late = self._xingshi_grace()  # 沒人上線也收得掉：伺服器排程的 world_tick 也走這裡
        key = conquest_day.day_key(self.pill_now(), c.config)
        if w.ended or key <= w.conquest.settled_key or self.world.paused_at() is not None:
            if late and save:
                self._save_season()
            return []
        if w.conquest.settled_key < 0:
            w.conquest.settled_key, msgs = key, []
            self._xingshi_start()
        else:
            msgs = conquest_day.day_turn(w, c, key)
            for done in [b for b in self.world.get_sieges() if b.phase == "ended"]:  # 收場的攻城戰留到這時才從共用狀態拿掉
                self.world.drop_siege(done.record_id)
            self._xingshi_open(key)
        if save:
            self._save_season()
        return msgs

    def _deliver_conquest(self) -> None:
        """翻地的分紅送到（輿圖簡化設計 4.5；conquest._payout 記在 ConquestState.payouts）：自己同步（與快轉）時拿走自己的那幾筆——銀兩、經驗
        （只給本人；滿級照 5 換 1 換成心得，同決戰軍餉）、名望（renown.gain）；推（拉）最多的那一個記一筆行狀（annals.CONQUER）。一筆一則江湖紀錄。
        下線的人回來照樣拿得到。沒有自己的什麼都不做（不碰共用賽季）。"""
        s, c = self.state, self.content
        state = s.world.conquest
        if state is None or not state.payouts:
            return
        me = name_key(s.player.name)
        mine = [pay for pay in state.payouts if name_key(pay.name) == me]
        if not mine:
            return
        state.payouts = [pay for pay in state.payouts if name_key(pay.name) != me]
        p = s.player
        names = {f.id: f.name for f in c.scenario.factions}
        # 出陣回報：最新一則就是推滿（拉回歸零）那一下出陣的話，分紅那一則接著畫同一塊——不然一同步「剛剛」就換成分紅、看不到易手那一條
        last = s.journal[0].front if s.journal else None
        for pay in mine:
            place = c.locations[pay.loc].name if pay.loc in c.locations else pay.loc
            side = names.get(pay.side, pay.side)
            head = (CONQUEST_PAY_LINE if pay.kind == "take" else CONQUEST_GUARD_LINE).format(place=place, side=side, pct=round(pay.share * 100))
            lines: list[str] = [head]
            if pay.silver:
                p.stats["silver"] = p.stats.get("silver", 0) + pay.silver
                lines.append(f"銀兩 +{pay.silver}")
            if pay.exp and team.maxed(c, p.member):
                gained = team.maxed_xinde(s, c, pay.exp, "dividend")
                if gained:
                    lines += [team.MAXED_XINDE.format(n=gained), f"心得 +{gained}"]
            elif pay.exp:  # 翻地分紅算仗（地是打下來的，growth.BATTLE_KINDS）
                before = p.member.level
                lines.append(f"經驗 +{pay.exp}")
                lines += team.add_exp(c, p.member, pay.exp, p.name, "dividend")
                if p.member.level > before:
                    points = team.level_points(self.state, c, before, p.member.level)
                    p.stat_points += points
                    if points:
                        lines.append(f"你有 {p.stat_points} 點屬性可以分配（點名號展開）。")
            if pay.fame:
                lines += renown.gain(s, c, "fame", pay.fame)
            if pay.top:
                text = (CONQUEST_TOP_ANNAL if pay.kind == "take" else CONQUEST_TOP_GUARD_ANNAL).format(place=place)
                annals.note(s, c, annals.CONQUER, text, 4, place=place, time=pay.time)
            self._write((CONQUEST_PAY_TITLE if pay.kind == "take" else CONQUEST_GUARD_TITLE).format(place=place), lines)
            if last is not None and last.loc == pay.loc:
                s.journal[0].front = last
        self._save_season()
    # ── 〈天下形勢〉（領地爭奪第三批 A；tianxia/xingshi.py，計畫第五章 Task 16、17）──

    def _xingshi_start(self) -> None:
        """這一季第一次結算（只記下 key 的那一下）：記〈天下形勢〉的起點——三條線此刻的值、day_log 與天下大事讀到哪裡（XingshiMark）。
        已經記過、或〈天下形勢〉關著不動。"""
        c, w = self.content, self.state.world
        if not xingshi.on(c, w) or w.xingshi_mark is not None:
            return
        w.xingshi_mark = XingshiMark(log=len(w.conquest.day_log), rumors=len(w.rumors), lines=xingshi.line_values(w, c))

    def _xingshi_open(self, key: int) -> None:
        """結算完那一下開一張新的單（WorldState.xingshi_ticket）：事實是上一篇以來的 day_log、三條線比上一篇的動向、天下大事（xingshi.facts），
        「是日：…」照收場的那幾筆（summary_line）。上一張還沒收的先照固定段收（一天一篇，不會兩張單並存）；讀到哪裡往前挪（XingshiMark）。"""
        c, w = self.content, self.state.world
        if not xingshi.on(c, w):
            return
        if w.xingshi_ticket is not None:
            self._xingshi_finish(None)
        mark = w.xingshi_mark or XingshiMark()
        notes = w.conquest.day_log[mark.log:]
        n = max([e.n for e in w.xingshi], default=0) + 1
        w.xingshi_ticket = XingshiTicket(
            n=n, key=key, opened_real=self.now,  # 現實時鐘（FB-577）
            facts=xingshi.facts(w, c, notes, mark.lines, mark.rumors, night=xingshi.is_night(self.pill_now(), c),  # 白天開的不寫「打到入夜」
                                marks_from=mark.fired),  # 減法季批 4：上一篇開單以後過門檻的痕跡（PM 2026-10-25 修正輪：不再靠世界層傳聞補）
            line=xingshi.summary_line(notes, c),
        )
        w.xingshi_mark = XingshiMark(log=len(w.conquest.day_log), rumors=len(w.rumors), lines=xingshi.line_values(w, c),
                                     fired=len(w.marks_fired))  # 這一篇開單那一刻讀到哪裡：開單到收下之間過門檻的，下一篇寫

    def _xingshi_finish(self, essay: str | None) -> XingshiEssay:
        """收下還在等的那一張：模型寫的過得了 xingshi.clean 就用，不然照固定段（by_rule，畫面上看不出差別）；天下大事一則、江湖史一筆，
        這一季最多留 Config.xingshi.keep 篇。呼叫端確認有單、自己存季。"""
        c, w = self.content, self.state.world
        ticket = w.xingshi_ticket
        text = xingshi.clean(essay) if essay else None
        done = XingshiEssay(
            key=ticket.key, time=w.time, n=ticket.n, line=ticket.line, by_rule=text is None,
            essay=text if text is not None else xingshi.rule_text(ticket.facts, c, f"{w.tianji}|{ticket.key}|{ticket.n}"),
        )
        w.xingshi = (w.xingshi + [done])[-c.config.xingshi.keep:]
        news = xingshi.rumor_text(ticket.line)
        add_rumor(self.state, news, content=c, layer="world")
        add_chronicle(self.state, news)
        w.xingshi_ticket = None
        return done

    def _xingshi_grace(self) -> bool:
        """還在等模型的那一張單開了 Config.xingshi.grace_seconds（現實秒）還沒交回：照固定段收（伺服器關著、模型壞了，照樣每天一篇）。
        暫停中不收（暫停凍結世界的變化）。收了回 True（呼叫端存季）。開單、寬限、重試一律照現實時鐘 self.now（FB-577：管理者快轉推的
        advanced_real 只活在那一個 Game 裡，拿 pill_now 開的單，沒快轉過的 Game 要等現實追上十幾個小時才收得掉）；換天照舊認 pill_now。"""
        c, w = self.content, self.state.world
        ticket = w.xingshi_ticket
        if ticket is None or not xingshi.on(c, w) or self.world.paused_at() is not None:
            return False
        if self.now - ticket.opened_real < c.config.xingshi.grace_seconds:
            return False
        self._xingshi_finish(None)
        return True

    def xingshi_waiting(self) -> bool:
        """有一張單等著伺服器拿去請模型寫（server._xingshi_waiting 問；還沒被拿走、上一趟沒輪到的隔過 retry_seconds 了）。只讀。"""
        ticket = self.state.world.xingshi_ticket
        return (ticket is not None and not ticket.taken and self.now >= ticket.retry_at
                and xingshi.on(self.content, self.state.world))

    def release_xingshi(self, request: xingshi.XingshiRequest) -> bool:
        """B 段沒叫成模型（佇列裡假人的名額被佔、排不到）：同一張單放回去（taken 清掉），隔 Config.xingshi.retry_seconds 再拿；
        寬限到了還沒寫成，照舊由 _xingshi_grace 照固定段收（PM，第三批 A 回報之後：不要一被擋就退回固定段）。放了回 True、存季。"""
        ticket = self.state.world.xingshi_ticket
        if ticket is None or ticket.n != request.n or ticket.key != request.key:
            return False
        ticket.taken, ticket.retry_at = False, self.now + self.content.config.xingshi.retry_seconds
        self._save_season()
        return True

    def xingshi_request(self) -> xingshi.XingshiRequest | None:
        """A 段（server.xingshi_once 在行動鎖內叫）：拿走還在等的那一張單（記 taken、存季，同一張不再拿第二次），回請模型寫要的東西；
        沒有、已經被拿走是 None。"""
        w = self.state.world
        if not self.xingshi_waiting():
            return None
        ticket = w.xingshi_ticket
        ticket.taken = True
        self._save_season()
        return xingshi.XingshiRequest(n=ticket.n, key=ticket.key, line=ticket.line, facts=list(ticket.facts))

    def settle_xingshi(self, request: xingshi.XingshiRequest, essay: str | None) -> bool:
        """C 段：還是同一張單（篇次與 key 都對得上、還沒收）才收；文章過不了 xingshi.clean 照固定段。收了回 True、存季。
        單子換了（過了 grace 已經照固定段收、隔天開了新的）就丟掉。"""
        ticket = self.state.world.xingshi_ticket
        if ticket is None or ticket.n != request.n or ticket.key != request.key:
            return False
        self._xingshi_finish(essay)
        self._save_season()
        return True

    def xingshi_view(self) -> dict:
        """見聞「形勢」頁（/api/xingshi）：這一季收下的每一篇（新的在前；標題、時刻、「是日：…」、文章），pending＝今天這一篇還在寫。
        不寫是不是模型寫的（by_rule 不送）。〈天下形勢〉關著是 {"on": False}。"""
        c, w = self.content, self.state.world
        if not xingshi.on(c, w):
            return {"on": False}
        essays = [{"n": e.n, "title": xingshi.HEAD.format(n=e.n), "time": self.stamp(e.time), "line": e.line, "essay": e.essay}
                  for e in reversed(w.xingshi)]
        return {"on": True, "pending": w.xingshi_ticket is not None, "essays": essays}

    def xingshi_mark(self) -> str:
        """見聞「形勢」頁要不要重抓（FB-578；server.main_view 的 xingshi_mark）：收下的最新一篇的篇次，有一張還在寫就多一個「+」。
        開了新單、寫好了都會變，網頁停在那一頁時看到它變了就重抓 /api/xingshi。只讀。"""
        w = self.state.world
        latest = max((e.n for e in w.xingshi), default=0)
        return f"{latest}{'+' if w.xingshi_ticket is not None else ''}"

    def admin_xingshi_now(self) -> list[str]:
        """管理者（測試與試玩用）：現在就開一篇〈天下形勢〉——照上一篇以來的事實開一張單，效果跟每天結算那一下一樣（還在等的那一張先照
        固定段收）。伺服器照常在背景請模型寫，寫不出來照固定段。"""
        refusal = self._admin_refusal("現在就開一篇天下形勢")
        if refusal:
            return self._log(refusal)
        c, w = self.content, self.state.world
        if not xingshi.on(c, w) or w.conquest is None or w.ended:
            return self._log([f"（{XINGSHI_OFF}）"])
        self._xingshi_open(w.conquest.settled_key)
        line = XINGSHI_OPENED.format(n=w.xingshi_ticket.n, minutes=round(c.config.xingshi.grace_seconds / 60))
        self._write("天下形勢", [line], tag="管理者")
        self._save_season()
        return self._log([line])

    def conquest_view(self) -> dict | None:
        """領地爭奪的畫面資料（server.main_view 的 conquest；輿圖第 3、4 批畫）：today 是時程表（戰書排的攻城：地點、攻方、時刻、狀態、誰下的），
        blocks 是每一塊的翻地資料（conquest.block_view：誰佔著、開季的種類、每一條進度、冷卻幾分、被哪一場戰書凍結〔時刻照 stamp_text〕、正在推的人、
        激戰、每一邊的集火、看的人攻或守推不推得動與原因），here 是自己腳下那一塊（不是區塊是 None），letter 是自己能不能下戰書（只有在任的第 4 階
        有 can／why 與自己那一邊進度到門檻的塊）。開關關著、季收了是 None。誰推的只寫名號，真人假人一樣。"""
        c, w = self.content, self.state.world
        if not conquest.on(c, w) or w.ended or w.conquest is None:
            return None
        side = self._conquest_side()
        names = {f.id: f.name for f in c.scenario.factions}
        live = self._siege_live() if any(slot.status == "open" for slot in w.conquest.schedule) else None
        today = [{
            "id": slot.id, "loc": slot.loc, "place": c.locations[slot.loc].name,
            "attackers": [names.get(a, a) for a in slot.attackers], "time": self.stamp(slot.at), "minute": slot.minute,
            "status": slot.status, "status_text": siege_status_text(c, slot),
            "by": {names.get(a, a): conquest_day.BY_WORDS.get(slot.by.get(a, ""), "") for a in slot.attackers},
            # 輿圖第三版第 5 批（卡上「戰書／攻城／攻城戰果」那一段）：sides 是攻方的陣營 id；you 是看的人站得進哪一格（siege.slots 同一套：
            # 攻方 attack、被打的那一方 defend、散人與不是兩軍的人 help〔臨時投效或助守〕、另一軍站不進去是空的）；margin 是打完那一場的大勝／險勝
            "sides": list(slot.attackers), "you": self._siege_you(slot, side), "margin": self._siege_margin(slot),
            # FB-690：region 是那一塊的大區名（加入要人在那一區）；join 是集結・交戰中那一場看的人此刻加不加得進去（_siege_join）
            "region": self._region_name(slot.loc), "join": self._siege_join(slot, side, live),
        } for slot in w.conquest.schedule]
        blocks: dict[str, dict] = {}
        for loc in conquest.blocks(c):
            row = conquest.block_view(w, c, loc, side)
            if row["frozen"] is not None:
                row["frozen"]["time"] = self.stamp(row["frozen"].pop("at"))
            row["holder_name"] = names.get(row["holder"], "") if row["holder"] else ""
            for line in row["bars"]:
                line["name"] = names.get(line["side"], line["side"])
            blocks[loc] = row
        p = self.state.player
        here = blocks.get(p.location) if p.journey is None else None
        letter = None
        if side is not None and ranks.rank_of(self.state) == ranks.SEAT_RANK:
            ready = [loc for loc in conquest.blocks(c) if conquest.bar(w, loc, side) >= c.config.conquest.letter_at]
            letter = {"used": w.conquest.letter_days.get(side) == self._letter_key(), "at": c.config.conquest.letter_at,
                      "ready": [{"id": loc, "name": c.locations[loc].name, "why": self.letter_problem(loc) or ""} for loc in ready]}
        return {"today": today, "blocks": blocks, "here": here, "letter": letter, "muster": c.config.conquest.muster_minutes}

    def _siege_you(self, slot, side: str | None) -> str:
        """看的人站得進這一場攻城的哪一格（卡上那顆鈕寫什麼；siege.slots 同一套）：攻方 attack、此刻佔著那一塊的那一軍 defend、
        散人與不是兩軍的人 help（臨時投效攻方或助守）、另一軍站不進去是空字串。打完、作罷的也照算（卡上那時不畫鈕）。"""
        if side is None:
            return "help"
        if side in slot.attackers:
            return "attack"
        return "defend" if conquest.holder(self.state.world, self.content, slot.loc) == side else ""

    def _region_name(self, loc_id: str) -> str:
        region = atlas.region_of(self.content, loc_id) if loc_id in self.content.locations else None
        return region.name if region is not None else ""

    def _siege_live(self) -> tuple[list[battle_instance.BattleInstance], set[int]]:
        """此刻集結或開打的全服戰鬥（決戰與攻城）與自己此刻加得進去的那幾場的流水號（_joinable：人在那一區、不在路上、站得進去、
        還沒在任何一場的名單上）。conquest_view 有集結・交戰中的攻城時才讀一次。"""
        showdown = self.world.get_battle()
        live = ([showdown] if showdown is not None and showdown.phase != "ended" else []) + self._sieges()
        return live, {b.record_id for b in self._joinable()}

    def _siege_join(self, slot, side: str | None, live) -> str:
        """FB-690：集結・交戰中那一場看的人此刻加不加得進去（卡上那顆鈕照它畫，跟江湖頁的加入鈕同一套 _joinable）：go＝加得進去、
        in＝已經在這一場、busy＝已經在別的一場、far＝站得進去但人不在那一區（或在路上）、空字串＝站不進去（另一軍）或不是集結・交戰中。"""
        if slot.status != "open" or live is None or not self._siege_you(slot, side):
            return ""
        battles, joinable = live
        battle = next((b for b in battles if b.siege is not None and slot.record_id is not None and b.record_id == slot.record_id), None)
        if battle is None:
            return ""
        name = self.state.player.name
        if name in battle.participants:
            return "in"
        if any(name in b.participants for b in battles):
            return "busy"
        return "go" if battle.record_id in joinable else "far"

    def _siege_margin(self, slot) -> str:
        """打完那一場的大勝／險勝（收場那一下 siege._note_result 記在 day_log）；還沒打完、作罷、找不到是空字串。"""
        if slot.status != "done" or self.state.world.conquest is None:
            return ""
        return next((n.margin for n in reversed(self.state.world.conquest.day_log)
                     if n.result and n.key == slot.key and n.loc == slot.loc and n.minute == slot.minute), "")

    def pill_now(self) -> float:
        """回體丹換日看的現實時間：sync 給的 now，加上 advance 推過的那一截（advanced_real）。"""
        return self.now + self.advanced_real

    def _pill_day(self) -> int:
        """現在是第幾天（Config.pill_day_utc_offset_hours 的時區、00:00 換日；從 1970-01-01 起算）。"""
        return self._day_of(self.pill_now())

    def _day_of(self, t: float) -> int:
        """現實時間 t 是回體丹那一套的第幾天（_pill_day 照它算；sync 拿它比上一次同步是不是換了一天）。"""
        return int((t + self.content.config.pill_day_utc_offset_hours * HOUR) // (24 * HOUR))

    def pill_cap(self) -> int:
        """一天最多服幾顆：新手期照 newbie_pills_per_day（有寫才算），其餘照 stamina_pills_per_day；0 是不限。
        商城的月卡（錢包服務的 card_bonus）讓有上限的那一個多 Config.mall.card_pill_bonus 顆（平常 2→3、新手期 5→6）；不限照舊不限。"""
        cfg = self.content.config
        if cfg.stamina_pills_per_day > 0 and cfg.newbie_pills_per_day > 0 and roster.newbie(self.state, self.content):
            cap = cfg.newbie_pills_per_day
        else:
            cap = cfg.stamina_pills_per_day
        return cap if cap <= 0 else cap + self._pill_card_bonus()

    def _pill_card_bonus(self) -> int:
        """今天月卡讓回體丹上限多幾顆（ctx.wallet.card_bonus，開發規範手冊 3.10）；商城關著、沒有卡、今天不在卡的期間裡是 0。
        pill_cap 與體力條的說明（howto.stamina_lines 的 card，FB-480）都讀這一份，兩邊寫的上限才對得上。"""
        return self.wallet.card_bonus()

    # ── 錢包（核心；開發規範手冊 3.10）與商城的一行委派（商城搬進功能包 tianxia/features/mall/：規則 rules.py、動作 actions.py）──

    @property
    def wallet(self) -> WalletService:
        """核心的錢包服務（開發規範手冊 3.10）：票的庫存與消耗、月卡加的上限、哪一件商品賣這種效果。走一趟、列傳、自創要用票的地方叫它，不叫商城。"""
        return WalletService(self)

    def _wallet(self) -> Wallet | None:
        """商城開著時這個資料庫的錢包；關著（或這個 world 沒有資料庫）是 None，呼叫端什麼都不讀不寫。"""
        db = getattr(self.world, "db", None)
        return Wallet(db) if wallet_on(self.content) and db is not None else None

    def _mall_owner(self) -> str:
        """錢包的主人：角色名號的 casefold（同 characters.key、真人的 accounts.character_key；假人沒有帳號也有錢包）。"""
        return name_key(self.state.player.name)

    # 過渡：server 與測試照舊叫 Game 的這幾個；第 2 階那一包的線再碰到時呼叫端改成直接叫包、委派拿掉（手冊 3.10）
    def _mall_grant(self) -> None:
        mall_actions.grant(self)

    def mall_buy(self, item_id: str, ref: str, qty: int = 1) -> list[str]:
        return mall_actions.buy(self, item_id, ref, qty)

    def mall_entry(self) -> dict | None:
        return mall_actions.entry(self)

    def mall_rename_left(self) -> int:
        return mall_actions.rename_left(self)

    def mall_rename(self, new: str, taken: Callable[[str], bool] | None = None) -> list[str]:
        return mall_actions.rename_self(self, new, taken)

    def mall_claim(self) -> list[str]:
        return mall_actions.claim(self)

    def mall_view(self) -> dict | None:
        return mall_actions.view(self)

    def mall_records(self) -> dict | None:
        return mall_actions.records(self)

    def admin_mall_reissue(self, name: str, amount: int, note: str, ref: str) -> list[str]:
        return mall_actions.admin_reissue(self, name, amount, note, ref)

    def admin_mall_revoke(self, name: str, amount: int, note: str, ref: str) -> list[str]:
        return mall_actions.admin_revoke(self, name, amount, note, ref)

    def admin_mall_refund(self, name: str, purchase_id: int, note: str) -> list[str]:
        return mall_actions.admin_refund(self, name, purchase_id, note)

    def admin_mall_ledger(self, name: str) -> dict:
        return mall_actions.admin_ledger(self, name)

    def pills_left_today(self) -> int | None:
        """今天還能服幾顆回體丹（pill_cap）；不限是 None。不看手上有幾顆。"""
        cap = self.pill_cap()
        if cap <= 0:
            return None
        p = self.state.player
        return max(0, cap - (p.pills_today if p.pill_day == self._pill_day() else 0))

    def _refill_stamina(self) -> list[str]:
        """測試期間一鍵補滿體力（Config.beta_free_refill，企劃者 2026-10-07；take_stamina_pill 在開關打開時走這裡）：
        補到 stamina_max（狀態列顯示的那個上限），不收丹、不收銀兩、不限次數。規矩跟丹一模一樣：還在草廬序章裡、體力已經是滿的
        都只回一句話（不寫紀錄、不動東西）；籌備中由 take_stamina_pill 的 _not_while_preparing 擋；其餘不看——閉關中、
        在路上都照補、不動那個狀態（丹也不看 busy_until、journey）。補成了寫一則江湖紀錄（數值變化只寫體力，沒有丹的那一項）。"""
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
        seen = jianfa(self.content, self.state.world, "stat_milestones")  # 減法季屬性五段：配點那一刻寫實際變了多少（設計 4.5「看得見」）
        was = p.stats.get(stat, 0)
        power = team.fresh_power(self.state, self.content, self.world) if seen else 0.0
        p.stat_points -= 1
        p.stats[stat] = p.stats.get(stat, 0) + 1
        said = self._allocate_line(stat, was, power) if seen else ""
        if seen and p.stat_points <= 0:
            p.milestone_due = 0  # 境界卡（main.milestone）：配完就收
        journal.add_entry(
            self.state, JournalEntry(time=self.state.world.time, title=journal.ALLOCATE, changes=[f"{name} +1"],
                                     lines=[said] if said else []),
            merge=True,
        )
        left = f"（還有 {p.stat_points} 點可以分配）" if p.stat_points else ""  # 最後一點不寫「還有 0 點」
        self._guide(note_action(self.state, self.content, self.world, "allocate"))  # 序章第 9 步（新手引導計畫一）
        self._check_hints()  # 博聞加了持有上限會變（h_cap 的條件）：配成了之後看一遍（新手引導計畫三）
        return self._log([f"{said or f'{name} +1'}{left}"])

    def _allocate_line(self, stat: str, was: float, power: float) -> str:
        """配點那一句（減法季屬性五段，設計 4.5）：「臂力 8 → 9：武學威力 +6%，此刻全隊 182 → 193」——前後威力用 team.fresh_power
        （滿血、不看對手）各算一次，沒變（身法、悟性、博聞）就不寫全隊那一段。待 joy 潤。"""
        s, c = self.state, self.content
        name = c.config.stat_names.get(stat, stat)
        after = team.fresh_power(s, c, self.world)
        tail = f"，此刻全隊 {power:.0f} → {after:.0f}" if round(after) != round(power) else ""
        return f"{name} {was:.0f} → {was + 1:.0f}：{skillview.stat_step(s, c, stat, was)}{tail}"

    def milestone_card(self) -> dict | None:
        """境界卡（減法季屬性五段，設計 4.5；欄位表 main.milestone）：升到境界那一級、手上還有點沒配時是
        {"level": 20, "points": 5, "title": "筋骨大成"}；配完了、關著的季是 None。名字照 growth.MILESTONE_TITLES（待 joy 潤）。"""
        s, c = self.state, self.content
        p = s.player
        if not p.milestone_due or p.stat_points <= 0 or not jianfa(c, s.world, "stat_milestones"):
            return None
        return {"level": p.milestone_due, "points": p.stat_points, "title": growth.milestone_title(p.milestone_due)}

    # ── 玩家之間的邀請與切磋（玩家互動第二層，企劃者 2026-10-08「互動的兩層也可以派下去做了」）──────────
    # 切磋掛在玩家卡上（spar.py 登記進 social.ACTIONS）：發邀請、答應、婉拒、收回都是按的那個人自己的動作，在他自己那一把行動鎖裡做；
    # 對方那一份照 social 的做法拿（_peer：此刻在這裡的人、不補算時間、賽季接上這一份），做完存回去。收到的邀請也列在選單上
    # （invite:yes|no|cancel:<編號>，走 choose；假人照這條路答，bot_policy._answer_invite）。邀請存在這一季的 WorldState.invites。
    # 「是假人」不影響任何一句話。

    def _spar_problem(self, who: Game, *, me: bool, what: str = "切磋", cost: int | None = None) -> str | None:
        """這個人此刻能不能切磋（論武也問這一個，what 換成「論武」）：拒絕的話；能是 None。不在序章、閒著（Game.is_idle：
        不在事件、路上、閉關、決戰裡）、體力付得起（cost 沒給是一次遊歷）。me 是說話的人自己（「你」），不然寫對方的名號。"""
        s, c = who.state, self.content
        name = "你" if me else s.player.name
        if prologue_rules.active(s, c):
            return f"{name}還在草廬學藝，下山之後才能{what}。"
        if not who.is_idle():
            return f"{name}此刻正忙，騰不出手來{what}。"
        cost = c.config.action_cost["train"] if cost is None else cost
        if s.player.stamina < cost:
            return f"{name}體力不夠（{what}要 {cost} 點）。"
        return None

    def _spar_pair(self, other: str) -> str:
        """同一對人的帳本鍵：兩個名號（不分大小寫）排序後接起來，誰發的都記在同一本。"""
        return "|".join(sorted((name_key(self.state.player.name), name_key(other))))

    def _pair_left(self, tally: dict[str, list[int]], cap: int, other: str) -> int:
        """這一對人這個遊戲日在這本帳上還剩幾次（切磋、贈物、論武各一本，都在這一季的 WorldState；帳記的是別的遊戲日就當沒用過）。"""
        day, count = tally.get(self._spar_pair(other), (0, 0))
        used = count if day == game_day(self.content, self.state.world) else 0
        return max(0, cap - used)

    def _pair_tick(self, tally: dict[str, list[int]], other: str) -> None:
        """這一對人這個遊戲日在這本帳上記一次。呼叫端自己 _save_season。"""
        day, key = game_day(self.content, self.state.world), self._spar_pair(other)
        last_day, count = tally.get(key, (0, 0))
        tally[key] = [day, (count if last_day == day else 0) + 1]

    def _spars_left(self, other: str) -> int:
        """這一對人這個遊戲日還能切磋幾場（Spar.per_pair_day）。"""
        return self._pair_left(self.state.world.spar_tally, self.content.config.spar.per_pair_day, other)

    def gifts_left(self, other: str) -> int:
        """這一對人這個遊戲日還能贈物幾次（Config.gift_per_pair_day，不分誰送誰；FB-116）。"""
        return self._pair_left(self.state.world.gift_tally, self.content.config.gift_per_pair_day, other)

    def discusses_left(self, other: str) -> int:
        """這一對人這個遊戲日還能論武幾回（Config.discuss_per_pair_day；FB-116）。"""
        return self._pair_left(self.state.world.discuss_tally, self.content.config.discuss_per_pair_day, other)

    def spar_refusal(self, other: Game) -> str | None:
        """玩家卡上「切磋」按不按得下去（拒絕的話；能是 None）：規則開著、兩個人都閒著、付得起體力、今天這一對還沒打滿、
        之間沒有一張還在等的邀請。休季（這一季收了）卡上不畫，直接打 API 也是這一句（FB-169）。"""
        s, c = self.state, self.content
        if not season_one(c, s.world) or s.world.ended:
            return "（此刻無法這麼做。）"
        for who, me in ((self, True), (other, False)):
            problem = self._spar_problem(who, me=me)
            if problem is not None:
                return problem
        if self._spars_left(other.state.player.name) <= 0:
            return social.pair_full(self, "spar")
        if invites.between(s.world, s.player.name, other.state.player.name, "spar") is not None:
            return "已經有一張切磋的邀請在等回覆了。"
        return None

    def spar_invite(self, other: Game) -> list[str]:
        """玩家卡上的「切磋」：向這個人發一張邀請，他在 invite_ttl_seconds 內答應才打。被拒絕只回一句話。"""
        s = self.state
        problem = self.spar_refusal(other)
        if problem is not None:
            return [problem]
        name = other.state.player.name
        invites.expire(s.world)
        invites.send(s.world, self.content, "spar", s.player.name, name, s.player.location)
        self._save_season()
        self.touched.add(name)  # 他的選單、他看你的那張卡要多出答應、婉拒
        him = gender.pronoun(other.state)
        return [f"你向{name}抱拳，邀{him}過幾招；等{him}回覆。"]

    def _invite_options(self) -> list[Option]:
        """閒著的時候：別人發給你、而且就在你這個地點的邀請（答應、婉拒），你發出去還在等的（收回）。逾時的不列。"""
        s, c = self.state, self.content
        p = s.player
        opts: list[Option] = []
        for inv in invites.incoming(s.world, p.name):
            if inv.location != p.location:
                continue
            what = invites.kind_name(inv.kind)
            gesture = social.gesture_of(inv)
            if gesture is not None:  # 打招呼：固定的幾種回禮，不理就等它逾時（玩家互動第二層）
                opts += [Option(id=f"invite:{r}:{inv.id}", label=f"回{inv.sender}：{did}") for r, did in gesture.replies]
                continue
            if inv.kind == "travel":  # 結伴同行：答應不花體力（趕路、疾行的體力出發時各付各的）
                opts.append(Option(id=f"invite:yes:{inv.id}", label=f"答應{inv.sender}的{what}"))
            elif inv.kind == "mingtie":  # 回帖不花什麼；自己還沒做名帖回不了（灰的寫為什麼）
                opts.append(Option(id=f"invite:yes:{inv.id}", label=f"回{inv.sender}的名帖", enabled=p.mingtie is not None,
                                   note="" if p.mingtie is not None else mingtie_rules.NO_CARD))
            elif inv.kind == "discuss":
                # 論武要挑自己出哪一樣：在他的玩家卡上答（discuss.buttons）；選單上這一顆引擎不收（灰的，整季機器人與假人不會按到），
                # 網頁把它畫成「打開他的玩家卡、捲到答應那一格」的鈕（social.calls 帶 peer，FB-117），字照舊寫去哪裡答
                opts.append(Option(id=f"invite:yes:{inv.id}", enabled=False, label=f"答應{inv.sender}的{what}（在對方的玩家卡上挑你要出的）"))
            else:
                opts.append(self._cost_option(f"invite:yes:{inv.id}", f"答應{inv.sender}的{what}", c.config.action_cost["train"]))
            opts.append(Option(id=f"invite:no:{inv.id}", label=f"婉拒{inv.sender}的{what}"))
        for inv in invites.outgoing(s.world, p.name):
            if inv.kind in ("greet", "mingtie"):
                continue  # 打招呼、名帖不用收回：等回禮、回帖，沒回就過去了
            opts.append(Option(id=f"invite:cancel:{inv.id}", label=f"收回給{inv.target}的{invites.kind_name(inv.kind)}邀請"))
        return opts

    def _invite(self, arg: str) -> list[str]:
        """選單上的邀請選項：invite:yes|no|cancel:<編號>。對方那一份照玩家卡的做法拿（_peer），做完存回去。"""
        verb, _, invite_id = arg.partition(":")
        inv = invites.find(self.state.world, invite_id)
        if inv is None:
            return ["這份邀請已經不在了。"]
        other = None if verb == "cancel" else self._peer(inv.sender)
        msgs = self.answer_invite(inv, other, verb)
        if other is not None:
            CharacterStore(self.world.db).save(other.state)
        return msgs

    def answer_invite(
        self, inv, other: Game | None, verb: str, item: str = "", proposed: tuple[str | None, str] | None = None,
    ) -> list[str]:
        """答應（yes）、婉拒（no）、收回（cancel）一張邀請。other 是另一個人那一份（_peer；他不在這裡了是 None）；
        呼叫端負責把 other 存回去（玩家卡走 peer_act，選單走 _invite）。論武答應時 item 是你出的那一樣，proposed 是鎖外取好的名字
        （discuss_request 的 C 段；沒給才在鎖裡叫模型，整季腳本與測試）。"""
        s = self.state
        what = invites.kind_name(inv.kind)
        if verb == "yes" and inv.kind == "discuss" and other is not None and self.discuss_invite_problem(inv, other) is None:
            problem = self.discuss_item_problem(inv, other, item)
            if problem is not None:  # 是你挑的那一樣不行（同一樣、合不成）：換一樣再答就好，邀請留著（FB-117）
                return [problem]
        invites.drop(s.world, inv.id)
        self._save_season()
        if verb == "cancel":
            self.touched.add(inv.target)  # 他畫面上那兩顆答應、婉拒要拿掉
            self._outcome("收回邀請", f"你收回了給{inv.target}的{what}邀請。")
            return [f"你收回了給{inv.target}的{what}邀請。"]
        if other is None:
            if verb == "yes":
                self._tell_sender(inv, None, INVITE_LAPSED_AWAY)
            return [social.GONE]
        self.touched.add(other.state.player.name)
        gesture = social.gesture_of(inv)
        if gesture is not None:
            return self._greet_back(inv, other, gesture, verb)
        if verb == "no":
            other._write(f"{s.player.name}婉拒了{what}", [f"{s.player.name}拱手婉拒了你的邀請。"])
            self._outcome("婉拒", f"你婉拒了{inv.sender}的{what}。")
            return [f"你婉拒了{inv.sender}的{what}。"]
        if inv.kind == "travel":
            return self._join(inv, other)
        if inv.kind == "mingtie":
            return self._mingtie_swap(inv, other)
        if inv.kind == "discuss":
            return self._discuss(inv, other, item, proposed)
        return self._spar(inv, other)

    def answer_on_card(self, inv, other: Game, verb: str) -> list[str]:
        """玩家卡上回應他遞來的打招呼、結伴（social 的回禮、答應、婉拒那幾顆，FB-117）：跟場景底下那一顆（選單的 invite: 選項，
        走 choose）同一個結果、同一則江湖紀錄（標題照 _action_title，草稿同 choose）。other 是 peer_act 那一份，由它存回去。"""
        self._draft = Draft(self._action_title("invite", f"{verb}:{inv.id}"))
        try:
            msgs = self.answer_invite(inv, other, verb)
            journal.add_entry(self.state, self._draft.entry(self.state.world.time, msgs))
        finally:
            self._draft = None
        return msgs

    def _greet_back(self, inv, other: Game, gesture: social.Gesture, verb: str) -> list[str]:
        """回禮（打招呼）：兩邊各記一則。"""
        me = self.state.player.name
        did = dict(gesture.replies).get(verb)
        if did is None:
            return ["（沒有這種回禮。）"]
        line = social.taunt_line(inv, None)
        said = f"：「{line}」" if line else ""
        other._write(f"與{me}", [f"你向{me}{gesture.did}{said}，{me}{did}。"])
        heard = social.taunt_line(inv, self.state)  # 不接他的挑釁話的人，自己的紀錄也不寫那一句
        return [f"{inv.sender}{gesture.got}：「{heard}」" if heard else f"{inv.sender}{gesture.got}。", f"你{did}。"]

    def _join(self, inv, other: Game) -> list[str]:
        """答應結伴同行：重驗（還在發邀請的那個地點、兩個人都沒在跟別人、你身後也沒有人跟著你），記下跟著誰；兩邊各記一則。"""
        p = self.state.player
        refusal = self.join_refusal(inv.sender) if inv.location == p.location else social.GONE.rstrip("。")
        if refusal is not None:
            self._tell_sender(inv, other)
            return [f"（{refusal}。）"]
        p.tagalong = Tagalong(leader=inv.sender, since=self.now)
        other._write(f"結伴同行・{p.name}", [f"{p.name}答應與你結伴同行：由你定去哪、怎麼走，出發時{gender.pronoun(p)}跟著走。"])
        return [f"你答應與{inv.sender}結伴同行，等{gender.pronoun(other.state)}動身。"]

    def _tell_sender(self, inv, other: Game | None, why: str | None = None) -> None:
        """答應了卻沒成、邀請已經收掉：發邀請的那個人下次同步在江湖紀錄裡看到一句（FB-117：以前邀請悄悄不見）。why 是寫給他看的原因
        （「你」是他）；other 是 None（他不在這裡了）時從資料庫讀他那一份、寫完存回去。"""
        me, what = self.state.player.name, invites.kind_name(inv.kind)
        sender = other if other is not None else self._load_kin(inv.sender)
        if sender is None:
            return
        sender._write(f"{what}不成・{me}", [INVITE_LAPSED.format(who=me, what=what)] + ([why] if why else []))
        if other is None:
            self._save_kin(sender)
        self.touched.add(sender.state.player.name)

    def _spar_answer_problem(self, inv, other: Game, *, for_sender: bool = False) -> str | None:
        """答應切磋時這一場還打不打得成：還在發邀請的那個地點、兩個人都閒著付得起體力、這一對這個遊戲日還沒打滿。
        for_sender：寫給發邀請的那個人看（「你」是他，_tell_sender 用）。"""
        if inv.location != self.state.player.location:
            return social.GONE
        for who in (self, other):
            problem = self._spar_problem(who, me=(who is self) != for_sender)
            if problem is not None:
                return problem
        if self._spars_left(other.state.player.name) <= 0:
            return social.pair_full(self, "spar")
        return None

    def _spar(self, inv, other: Game) -> list[str]:
        """答應一場切磋：重驗（還在發邀請的那個地點、兩個人都閒著、體力付得起、今天這一對還沒打滿），雙方各花一次遊歷的體力，
        用本人的威力照單次判定打一場（從發邀請的那一方算，收的一方照鏡像），不扣氣血、不掉銀兩；雙方各一份戰報（回合演出不帶數字）
        與一則江湖紀錄，經驗與心得照 Config.spar。驗不過就把邀請收掉（answer_invite 已經收了）、說一句為什麼，發邀請的那個人也收到一句。"""
        c = self.content
        me, them = self.state.player, other.state.player
        problem = self._spar_answer_problem(inv, other)
        if problem is not None:
            self._tell_sender(inv, other, self._spar_answer_problem(inv, other, for_sender=True))
            return [problem]
        cost = c.config.action_cost["train"]
        me.stamina -= cost
        them.stamina -= cost
        self._pair_tick(self.state.world.spar_tally, them.name)
        self._save_season()
        ours, theirs = self._spar_power(self, other), self._spar_power(other, self)
        ours_shown, theirs_shown = self._spar_power(self, other, seal=False), self._spar_power(other, self, seal=False)  # 戰報給對方看的（先算：記完戰報可能升級）
        result = encounter.resolve_encounter(theirs, ours, self.rng)  # 從發邀請的那一方看：他的威力對上你的
        other._spar_record(result, me.name, ours, self, shown=ours_shown)
        return self._spar_record(self._spar_mirror(result, ours), them.name, theirs, other, shown=theirs_shown)

    # ── 論武（玩家互動第二層）：兩個人各出一個意境合成一個新的，兩人都拿到；首創算兩人共有，價錢各付一半 ──
    # 走 fusion.merge（fusion.Partner：對方出的那一個不必是你的、不佔你的持有）；持有上限、「已經有了」照舊各自擋。
    # 武學不再拿來合（Joy 2026-10-21），論武跟著只剩意境。
    # 開爐的是答應的那一方（discuss_request 是 A 段，伺服器在鎖外取名，_discuss 是 C 段），發邀請的那一方接著照配方合出同一門。

    def discuss_items(self) -> list[tuple[str, str]]:
        """論武時你出得了的：悟得的全服意境（「insight:<id>」；自己畫圖悟的私有意境不行）。回傳（鍵, 寫給人看的名字）。"""
        s, c = self.state, self.content
        out: list[tuple[str, str]] = []
        for insight_id in s.player.insights:
            insight = None if insights.is_own(insight_id) else insights.resolve(insight_id, c, self.world, s)
            if insight is not None:
                out.append((f"insight:{insight_id}", f"「{insight.name}」"))
        return out

    def _discuss_cost(self) -> tuple[int, int]:
        """論武這一邊付的（心得, 體力）：一爐意境合成的一半（fusion.half_price）。"""
        cfg = self.content.config
        return fusion.half_price(cfg.merge_xinde, cfg.merge_stamina)

    def discuss_refusal(self, other: Game) -> str | None:
        """玩家卡上「論武」按不按得下去：規則開著、兩個人都閒著、付得起一半的體力、之間沒有一張還在等的論武邀請。
        休季（這一季收了）卡上不畫，直接打 API 也是這一句（FB-169）。"""
        s, c = self.state, self.content
        if not season_one(c, s.world) or s.world.ended:
            return "（此刻無法這麼做。）"
        cost = self._discuss_cost()[1]
        for who, me in ((self, True), (other, False)):
            problem = self._spar_problem(who, me=me, what="論武", cost=cost)
            if problem is not None:
                return problem
        if self.discusses_left(other.state.player.name) <= 0:
            return social.pair_full(self, "discuss")
        if invites.between(s.world, s.player.name, other.state.player.name, "discuss") is not None:
            return "已經有一張論武的邀請在等回覆了。"
        return None

    def discuss_invite(self, other: Game, item: str) -> list[str]:
        """玩家卡上的「論武・以 X」：帶著你要出的那一樣發一張邀請，對方在卡上挑他出的那一樣答應才開爐。"""
        s = self.state
        problem = self.discuss_refusal(other)
        if problem is not None:
            return [problem]
        label = dict(self.discuss_items()).get(item)
        if label is None:
            return ["你身上沒有這一樣。"]
        name = other.state.player.name
        invites.expire(s.world)
        invites.send(s.world, self.content, "discuss", s.player.name, name, s.player.location, {"item": item})
        self._save_season()
        self.touched.add(name)
        return [f"你拿出{label}，邀{name}一起論武；等{gender.pronoun(other.state)}回覆。"]

    def _discuss_partner(self, mine: str, theirs: str, other_name: str, fresh: bool = False):
        """兩樣東西排成一爐意境合成：（兩個意境的 id, 借來的那一份）。舊邀請上的「art:」交給 discuss_problem 擋。"""
        mid, tid = mine.partition(":")[2], theirs.partition(":")[2]
        return [mid, tid], fusion.Partner(lent=tid, name=other_name, price=self._discuss_cost(), fresh=fresh)

    def discuss_request(self, inv, other: Game, item: str) -> naming.NamingRequest | None:
        """論武的 A 段（鎖內、只讀）：答應的那一方出 item、發邀請的那一方出邀請上那一樣，這一爐要不要模型取名或挑？
        要就回單子（伺服器在鎖外交給 naming.generate，假人程式交給 bot_runner），不要是 None。
        C 段（_discuss）一定會擋的先問（discuss_invite_problem、discuss_item_problem：他正忙、論滿了、你挑的那一樣合不成……）：
        成不了就不開單、不叫模型，呼叫端照「不必取名」直接走 C 段，回的話、邀請作廢與通知都同以前，只是不等模型（FB-245）。
        C 段照樣重驗（A 到 C 之間狀態可能變）。"""
        if inv is None or inv.kind != "discuss":
            return None
        if self.discuss_invite_problem(inv, other) is not None or self.discuss_item_problem(inv, other, item) is not None:
            return None
        insight_ids, partner = self._discuss_partner(item, inv.payload.get("item", ""), other.state.player.name)
        return fusion.forge_request(self.state, self.content, self.world, None, insight_ids, partner=partner)

    def _discuss_forge(self, mine: str, theirs: str, other_name: str, proposed, fresh: bool = False):
        """這一邊開一爐（意境合成，對方那一個當作借來的）：（合出來的那個意境, 訊息）；沒合成是 None。
        fresh：對方剛剛在這一次論武裡首創了這個配方（發邀請的那一方接著合，FB-243）。"""
        problem = self.discuss_problem(mine, theirs, other_name)
        if problem is not None:
            return None, [problem]
        insight_ids, partner = self._discuss_partner(mine, theirs, other_name, fresh)
        return fusion.merge(self.state, self.content, self.world, self._quick_client(), *insight_ids, proposed, partner)

    def discuss_problem(self, mine: str, theirs: str, other_name: str) -> str | None:
        """這一邊合不合得成（拒絕的話；fusion.merge_problem，對方那一個當作借來的、價錢是一半）。只讀；假人挑要出哪一樣也問它。"""
        if not (mine.startswith("insight:") and theirs.startswith("insight:")):
            return fusion.DISCUSS_ARTS_GONE
        insight_ids, partner = self._discuss_partner(mine, theirs, other_name)
        return fusion.merge_problem(self.state, self.content, self.world, *insight_ids, partner)

    def discuss_invite_problem(self, inv, other: Game, *, for_sender: bool = False) -> str | None:
        """答應論武時，這一張邀請本身還成不成（不看你挑哪一樣）：還在發邀請的那個地點、兩個人都閒著付得起一半的體力、
        這一對這個遊戲日還沒論滿（FB-116）、他要出的那一樣還在他身上。不成就作廢：answer_invite 收掉、發邀請的人收到一句（FB-117）。
        for_sender：寫給發邀請的那個人看（「你」是他，_tell_sender 用）。"""
        them = other.state.player
        if inv.location != self.state.player.location:
            return social.GONE
        cost = self._discuss_cost()[1]
        for who in (self, other):
            problem = self._spar_problem(who, me=(who is self) != for_sender, what="論武", cost=cost)
            if problem is not None:
                return problem
        if self.discusses_left(them.name) <= 0:  # 邀請在等的時候，這一對人今天的帳被別處用滿了（FB-116）
            return social.pair_full(self, "discuss")
        if inv.payload.get("item", "") not in dict(other.discuss_items()):
            return "你身上已經沒有要出的那一樣了。" if for_sender else f"{them.name}身上已經沒有{gender.pronoun(them)}要出的那一樣了。"
        return None

    def discuss_item_problem(self, inv, other: Game, item: str) -> str | None:
        """答應論武時你出 item 這一樣合不合得成：身上還有沒有、是不是跟他出的同一樣、兩邊各自合不合得成（fusion 的 *_problem）；
        合得成是 None。這一種不成是你挑的那一樣不行，換一樣再答就好，邀請留著（FB-117）。回的話帶 short（兩三個字），
        玩家卡上答應的下拉清單在合不成的那一項後面寫它（discuss.buttons）。先問過 discuss_invite_problem 才準。"""
        them = other.state.player
        theirs = inv.payload.get("item", "")
        if item not in dict(self.discuss_items()):
            return _refusal("你身上沒有這一樣。", "身上沒有")
        if item == theirs:
            return _refusal(DISCUSS_SAME, "同一樣")
        problem = self.discuss_problem(item, theirs, them.name)
        if problem is not None:
            return problem
        theirs_problem = other.discuss_problem(theirs, item, self.state.player.name)
        if theirs_problem is None:
            return None
        short, him = getattr(theirs_problem, "short", "") or "合不成", gender.pronoun(them)
        side = THEIR_SIDE.get(short)
        text = f"{them.name}那邊合不成：{side.format(him=him)}。" if side else f"{them.name}那邊合不成。"
        return _refusal(text, f"{him}那邊{short}")

    def _discuss(self, inv, other: Game, item: str, proposed) -> list[str]:
        """答應論武（C 段）：重驗（discuss_invite_problem、discuss_item_problem：還在發邀請的那個地點、兩個人都閒著、兩樣東西都還在
        各自手上、兩邊各自合得成），你先開爐（新配方的名字照 proposed），他接著照配方合出同一門；各付一半，各記一則江湖紀錄。
        驗不過就說一句為什麼（邀請已經收了），發邀請的那個人也收到一句（FB-117）。"""
        me, them = self.state.player, other.state.player
        theirs = inv.payload.get("item", "")
        problem = self.discuss_invite_problem(inv, other) or self.discuss_item_problem(inv, other, item)
        if problem is not None:
            self._tell_sender(inv, other, self.discuss_invite_problem(inv, other, for_sender=True))
            return [problem]
        made, msgs = self._discuss_forge(item, theirs, them.name, proposed)
        if made is None:
            self._tell_sender(inv, other)
            return msgs
        self.peer_brief = social.DISCUSS_BRIEF.format(thing=social.thing_label(made))
        # 配方剛登記：他照查表合出同一門，不取名；這一爐首創了的話，他那一句寫跟你一起首創（FB-243）
        _, their_msgs = other._discuss_forge(theirs, item, me.name, (None, ""), fresh=fusion.made_first(msgs))
        self._pair_tick(self.state.world.discuss_tally, them.name)
        self._save_season()
        other._write(f"論武・{me.name}", their_msgs)
        if self._draft is None:
            self._write(f"論武・{them.name}", msgs)
        else:
            self._outcome("論武", msgs[0])
        return msgs

    @staticmethod
    def _spar_power(who: Game, against: Game, *, seal: bool = True) -> float:
        """這個人切磋時的威力：只算本人（同伴、部下不上場），照對手身上那一門武學的屬性算相剋，吃自己的氣血係數與加成。
        seal=False 不含玉璽碎片的戰力（買兇的殺手照它浮上來，同江湖水漲）。"""
        s, c, w = who.state, who.content, who.world
        members, conditions, boosts = team._fighters(s, c, w, seal=seal)
        return encounter.member_power(
            members[0], team.team_arts(s, c, w), team.worn_attribute(against.state, c, against.world), conditions[0], boosts[0],
        )

    @staticmethod
    def _spar_mirror(result: encounter.EncounterResult, power: float) -> encounter.EncounterResult:
        """從另一邊看同一場：他贏就是你輸，他輸了你贏（差距夠大算大勝，門檻照你自己的威力當難度），平手照舊平手。"""
        if result.tier in team.WIN_TIERS:
            tier = "落敗"
        elif result.tier in team.DRAW_TIERS:
            tier = result.tier
        else:
            big = dict(encounter.tier_thresholds(result.our_power))["大勝"]  # 你的難度是他的威力
            tier = "大勝" if -result.margin >= big else "險勝"
        return result.model_copy(update={"tier": tier, "margin": -result.margin, "our_power": power, "difficulty": result.our_power})

    def _spar_record(self, result: encounter.EncounterResult, rival: str, rival_power: float, rival_game: Game,
                     *, shown: float | None = None) -> list[str]:
        """這一邊的戰報、獎勵與紀錄。對手寫成一支只為這一場存在的隊伍（名號、威力、身上那一門的屬性），戰報只列本人。
        shown：戰報上「對手威力 N」寫的數字＝對手不含玉璽碎片的威力（改版 FB-615；打起來照 result，含碎片）；不給就照 result。"""
        s, c, cfg = self.state, self.content, self.content.config.spar
        p = s.player
        squad = Squad(
            id=f"spar:{rival}", name=rival, difficulty=rival_power,
            attribute=team.worn_attribute(rival_game.state, c, rival_game.world),
        )
        record = battlelog.new_record(s, c, self.world, squad, result, "spar")
        if shown is not None:
            record.difficulty = shown
        record.ours = record.ours[:1]
        xinde = cfg.win_xinde if result.tier in team.WIN_TIERS else cfg.draw_xinde if result.tier in team.DRAW_TIERS else cfg.lose_xinde
        p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
        record.xinde = xinde
        before = p.member.level
        maxed_note = self._record_exp(record, cfg.exp, "spar")  # 先換（滿級才換）；升到滿級那一下剩下的不換
        ups = team.add_exp(c, p.member, cfg.exp, p.name, "spar")  # 切磋是仗（減法季 45 級以後照算）
        if p.member.level > before:
            points = team.level_points(self.state, c, before, p.member.level)
            p.stat_points += points
            if points:
                ups.append(f"你有 {p.stat_points} 點屬性可以分配（點名號展開）。")
        record.notes += [n for n in maxed_note if not n.startswith("心得 +")]  # 戰報敘事只留那一句；心得算在得失
        record.notes += ups
        self._play_rounds(record, squad, result.tier, None)
        line = self._file_battle(record, team_exp=False)
        # 兩邊對稱（FB-244）：各寫各自拿到的經驗與心得（只有本人拿，不寫「（每人）」）、各連自己的戰報
        msgs = [line] + ([f"經驗 +{cfg.exp}"] if record.exp else []) + [f"心得 +{xinde}"] + maxed_note + ups + self._last_wear  # 滿級不寫經驗（FB-451）
        if self._draft is None:  # 對方那一邊（或從玩家卡答應、沒有草稿）：替他記一則，連到這一份戰報
            self._write(f"切磋・{rival}", msgs, tag=battlelog.outcome_text(record), battle_id=record.id)
        else:  # 答應的那一方（自己按的，這次行動的草稿寫這一則）：結果那一句照樣寫進敘事，跟發邀請的那一方一樣（FB-117）
            self._draft.keep(line)
        return msgs

    # ── 截殺（Config.raid；企劃者 2026-10-08 在決策卡選「有限制地開」）：玩家卡上的一顆鈕，不必對方同意 ──
    # 每季都有、不看第一季開關（企劃者 2026-10-10，懸賞榜設計 2.2）；Config.raid.enabled 是主機的緊急開關，關著時通緝一起收。
    # 兩個人都投靠了陣營、而且是不同陣營時才有（三個陣營彼此都是敵對）；散人只能截殺自己揭了通緝的那個人。對方下線、在忙也照打：
    # 他在「此地還有」的名單上（presence_seconds 內同步過、不在路上）就行，他回來在戰報與江湖紀錄裡看得到。真人假人一樣。

    def raid_shown(self, other: Game) -> bool:
        """卡上要不要畫「截殺」：截殺開著（Config.raid.enabled）、這一季還沒收、兩個人都投靠了陣營、而且不同陣營；或是你揭了通緝他的懸賞
        （散人、同陣營的人也行）。每季都有，不看第一季開關（懸賞榜設計 2.2 第 3 點）；休季（這一季收了）不畫，跟通緝鈕、懸賞榜一樣
        （FB-163：以前還畫著灰的，原因寫成「城裡耳目眾多」「你此刻正忙」）；raid_targets 與 raid_refusal 都先問這裡。"""
        mine, theirs = self._side(), other._side()  # 豪強分屬兩軍：同一邊的不能截殺
        if not self.content.config.raid.enabled or self.state.world.ended:
            return False
        if mine is not None and theirs is not None and mine != theirs:
            return True
        return bounties.hunting(self.state, self.content, other.state.player.name)

    @staticmethod
    def _raid_key(attacker: str, target: str) -> str:
        return f"{name_key(attacker)}>{name_key(target)}"

    def raid_refusal(self, other: Game) -> str | None:
        """「截殺」按不按得下去（拒絕的話；能是 None）：不在城鎮類的地點、兩個人都過了新手期、你閒著付得起體力、
        你上一次截殺他已經過了冷卻、他沒有剛被人截殺過。對方忙不忙不看（截殺不必他同意）。"""
        s, c, cfg = self.state, self.content, self.content.config.raid
        if not self.raid_shown(other):
            return "（此刻無法這麼做。）"
        loc = c.locations[s.player.location]
        if c.config.explore_mix_of(loc.tags).kind == "town":
            return "城裡耳目眾多，不便動手。"
        if roster.raid_newbie(s, c):  # 新手期從各自加入的那一刻算，不看第一季開關（懸賞榜設計 14.1 丁）
            return "你初入江湖，還在新手期，先別結這種仇。"
        them = other.state.player.name
        if roster.raid_newbie(other.state, c):
            return f"{them}初入江湖，還在新手期，下不了這個手。"
        problem = self._spar_problem(self, me=True, what="截殺", cost=cfg.stamina)
        if problem is not None:
            return problem
        w = s.world
        key = self._raid_key(s.player.name, them)
        last = w.raids.get(key)
        if last is not None and w.time - last < cfg.pair_cooldown_seconds:
            if w.clashes.get(key) == last:  # 那一筆是混戰寫的（翻地與爭搶）：照實寫交過手，不寫截殺過（FB-607）
                return RAID_AFTER_CLASH.format(them=them)
            return f"你不久前才截殺過{them}，過一陣子再說。"
        hit = w.raided.get(name_key(them))
        if hit is not None and w.time - hit < cfg.shield_seconds:
            if w.clashed.get(name_key(them)) == hit:
                return RAID_SHIELD_CLASH.format(them=them)
            return f"{them}剛被人截殺過，元氣未復，這時下手太不講江湖道義。"
        return None

    def raid_odds(self, other: Game) -> str:
        """截殺的勝算（「有把握」這種字，同遊歷的按鈕）：本人對本人的威力，照固定種子模擬。兩邊都照**不含玉璽碎片**的威力算
        （改版 FB-625：給別人看的字不能讓人對同一個人看出他有沒有碎片，持有者自己看也照這一份，免得畫面對不上；
        打起來 raid() 照含碎片的威力擲，勝負不變）。"""
        theirs = self._spar_power(other, self, seal=False)
        squad = Squad(id=f"raid:{other.state.player.name}", name=other.state.player.name, difficulty=theirs)
        return team.odds_word(self._spar_power(self, other, seal=False), squad)

    def raid_targets(self) -> list[tuple[str, str]]:
        """此地截殺得了的人與勝算：[(名號, 勝算)]，照名號排序（假人挑對象用；真人看卡上的鈕）。截殺關著時是空的（raid_shown 擋）；
        散人只有揭了通緝的那個人。"""
        out = []
        for state in social.here(self):
            other = self._kin(state)
            if self.raid_shown(other) and self.raid_refusal(other) is None:
                out.append((state.player.name, self.raid_odds(other)))
        return out

    def raid(self, other: Game) -> list[str]:
        """截殺 other：重驗、付體力、記冷卻，用本人的威力照單次判定打一場（從發起的人看）。輸的一方失一點銀兩（贏的拿走一部分）
        與一點氣血（不變成內傷）；他身上的防具照減損少扣、也只有他磨（裝備四欄 4.4、4.5）；贏的一方記一點本季貢獻；平手誰都不失什麼。
        雙方各一份戰報與一則江湖紀錄。被截殺的人騎的馬比較快時，開打之前先擲策馬脫身（raid_flee_odds、_raid_fled）。"""
        problem = self.raid_refusal(other)
        if problem is not None:
            return [problem]
        s, c, cfg = self.state, self.content, self.content.config.raid
        me, them = s.player, other.state.player
        me.stamina -= cfg.stamina
        s.world.raids[self._raid_key(me.name, them.name)] = s.world.time
        s.world.raided[name_key(them.name)] = s.world.time
        # 策馬脫身（裝備四欄 5.10）：付完體力、記完冷卻才擲（跑掉了冷卻照算，不然可以一直按到追上），用自己的亂數、不動 Game.rng
        flee = self.raid_flee_odds(other)
        if flee > 0 and random.Random(f"截殺脫身|{me.name}|{them.name}|{s.world.time}").random() < flee:
            return self._raid_fled(other)
        ours, theirs = self._spar_power(self, other), self._spar_power(other, self)
        ours_shown, theirs_shown = self._spar_power(self, other, seal=False), self._spar_power(other, self, seal=False)  # 戰報給對方看的（FB-615）
        result = encounter.resolve_encounter(ours, theirs, self.rng)
        mirrored = self._spar_mirror(result, theirs)
        if result.tier in team.WIN_TIERS:
            winner, loser = self, other
        elif mirrored.tier in team.WIN_TIERS:
            winner, loser = other, self
        else:
            winner = loser = None
        # 名聲 5.4：交差之前先判會不會交到官府通緝（打贏了、手上揭著他的官府通緝），把惡名少的那一點算進輸的那一邊，兩邊的戰報才寫得到
        official = winner is self and renown.on(c, "official_wanted") and bounties.official_hit(s, c, them.name)
        spoils = winner._raid_spoils(loser, evil=c.config.renown.official_evil_loss if official else 0) if winner is not None else None
        self.touched.add(them.name)
        other._raid_record(mirrored, me.name, ours, self, spoils, attacker=False, shown=ours_shown)
        msgs = self._raid_record(result, them.name, theirs, other, spoils, attacker=True, shown=theirs_shown)
        if winner is self:
            msgs += self._raid_bounty(them.name)
            heard = figure_life.spread(s, c, "raid", name_key(them.name), at=me.location, side=them.faction,
                                       text=f"在{c.locations[me.location].name}截殺了{them.name}")
            if heard and self._draft is None:
                self._write(figure_life.HEARSAY_TITLE, heard)
            msgs += heard
        # 冷卻與交差（通緝那一張的 done_by／takers）都在共用賽季：最後存一次。玩家卡走 peer_act、server.act 都只存角色，
        # 以前在打之前就存了季，交差改的沒存回去，同一張可以一直揭、一直領，過期還照退押金（FB-119）
        self._save_season()
        return msgs

    def raid_flee_odds(self, other: Game) -> float:
        """被截殺的 other 策馬脫身的機會（裝備四欄 5.10）：他的腳力減你的腳力，夾在 0～raid_escape_cap；坐騎關著是 0。
        截殺鈕的確認句（raid.buttons）與 raid() 真正擲的都讀這一個。"""
        return mounts.raid_flee(self.content, self.state, other.state)

    def _raid_fled(self, other: Game) -> list[str]:
        """截殺時被截殺的人策馬脫身（裝備四欄 5.10）：不打、誰都不失銀兩與氣血、不寫戰報、不磨兵器防具、不扣飽足；發起的人的體力
        已經付了、冷卻已經記了（raid 在擲之前做完）。雙方各一則江湖紀錄。冷卻在共用賽季，最後存一次（FB-119：玩家卡走 peer_act、
        server.act 都只存角色）。scripts/sim_season_one.py 照這個函式數跑掉幾次。"""
        s, c = self.state, self.content
        me, them = s.player, other.state.player
        horse = mounts.name_of(them.mount)
        self.touched.add(them.name)
        other._write(f"遭{me.name}截殺", [mounts.RAID_ESCAPED.format(rival=me.name, horse=horse)], tag=mounts.RAID_ESCAPED_TAG)
        msgs = [f"體力 -{c.config.raid.stamina}", mounts.RAID_FLED.format(rival=them.name, horse=horse)]
        if self._draft is None:
            self._write(f"截殺・{them.name}", msgs, tag=mounts.RAID_FLED_TAG.format(him=gender.pronoun(them)))
        self._save_season()
        return msgs

    def post_wanted(self, other: Game, amount: int) -> list[str]:
        """通緝 other（玩家卡的「通緝」）：押金從你身上扣、掛上懸賞榜（bounties.post）；成了寫一則江湖紀錄、存季。"""
        msgs = bounties.post(self.state, self.content, other.state, amount)
        if msgs and msgs[0].startswith("你押了"):
            self._write(bounties.BOARD, msgs)
            self._save_season()
        return msgs

    def _raid_bounty(self, target: str) -> list[str]:
        """截殺打贏、揭了通緝他的懸賞：交差（賞銀、散人的俠名），補進這一則江湖紀錄。"""
        msgs = bounties.on_raid_win(self.state, self.content, self.world, target)
        if msgs and self._draft is None:
            self._write(bounties.BOARD, msgs)
        return msgs

    def _raid_spoils(self, loser: Game, evil: int = 0) -> RaidSpoils:
        """贏的是 self：loser 失銀兩（比例、有上限）與氣血（上限的一成弱，乘 1−他身上防具的減損；不吃化勁、不變成內傷，裝備四欄 4.4），
        self 拿走一部分銀兩、記一點貢獻。evil 是 loser 惡名少幾點（名聲 5.4：贏的人揭著他的官府通緝；夾在 0）。"""
        c, cfg = self.content, self.content.config.raid
        lp, wp = loser.state.player, self.state.player
        purse = lp.stats.get("silver", 0)
        lost = min(cfg.silver_cap, math.ceil(purse * cfg.silver_share)) if purse > 0 else 0
        taken = math.ceil(lost * cfg.take_share)
        lp.stats["silver"] = purse - lost
        wp.stats["silver"] = wp.stats.get("silver", 0) + taken
        con = team.con_of(loser.state, c, loser.world, PLAYER)
        cut = team.armor_cut(loser.state, c, loser.world)  # 截殺輸的一方只吃防具（裝備四欄 4.4）：不吃化勁，也就不必夾合計上限
        hp, _ = team._apply_toll(c, lp.member, cfg.hp_loss * (1 - cut), agi=lp.stats.get("agi", team.BASE_STAT), con=con, injury=0.0,
                                 season=loser.state.world)
        # 散人（揭了通緝）不記貢獻；第一季規則關著的季沒有晉升，也不記（懸賞榜設計 2.2 第 4 點，寫法同軍餉 _showdown_pay）
        contrib = c.config.contrib_per_push * cfg.win_contrib_push if wp.faction is not None and season_one(c, self.state.world) else 0
        if contrib:
            wins.credit(wp, c, self.state.world, calendar.point(self.state.world.time, c, self.state.world).week, contrib)
        cut = min(evil, lp.stats.get("evil", 0))
        if cut > 0:
            lp.stats["evil"] = lp.stats.get("evil", 0) - cut
        return RaidSpoils(winner=wp.name, lost=lost, taken=taken, hp=round(hp), contrib=contrib, evil=cut)

    def _raid_record(
        self, result: encounter.EncounterResult, rival: str, rival_power: float, rival_game: Game,
        spoils: RaidSpoils | None, *, attacker: bool, shown: float | None = None,
    ) -> list[str]:
        """這一邊的戰報與紀錄。對手寫成一支只為這一場存在的隊伍（同切磋），戰報只列本人。shown 同 _spar_record。"""
        s, c = self.state, self.content
        p = s.player
        squad = Squad(
            id=f"raid:{rival}", name=rival, difficulty=rival_power,
            attribute=team.worn_attribute(rival_game.state, c, rival_game.world),
        )
        record = battlelog.new_record(s, c, self.world, squad, result, "raid")
        if shown is not None:
            record.difficulty = shown
        record.ours = record.ours[:1]
        won = spoils is not None and name_key(spoils.winner) == name_key(p.name)
        hp_lost: int | None = 0
        if spoils is None:
            story = f"你攔下{rival}動手，兩人鬥了半天不分高下，各自退開。" if attacker else \
                f"{rival}半路攔下你動手，兩人鬥了半天不分高下，各自退開。"
        elif won:
            record.silver = spoils.taken
            if spoils.contrib:
                record.changes.append(f"貢獻 +{spoils.contrib}")
            story = f"你攔下{rival}動手，{rival}不敵，丟下銀兩走了。" if attacker else \
                f"{rival}半路截殺你，反被你打退，丟下銀兩走了。"
        else:
            record.silver = -spoils.lost
            hp_lost = spoils.hp
            if spoils.hp > 0:
                record.changes.append(f"氣血 -{spoils.hp}")
            if spoils.evil:  # 名聲 5.4
                record.changes.append(bounties.BEATEN_OFFICIAL.format(n=spoils.evil, winner=spoils.winner))
            story = f"你攔下{rival}動手，卻不是{gender.pronoun(rival_game.state)}的對手，只得丟下銀兩脫身。" if attacker else \
                f"{rival}半路截殺你，你不敵，丟下銀兩脫身。"
        record.notes.append(story)
        annals.note(s, c, annals.FIGHT, story, 3 if won else 2, keep=[rival])  # 行狀：截殺與被截殺（兩邊各記自己的；對手的名號原樣留，FB-9020）
        self._play_rounds(record, squad, result.tier, hp_lost)
        line = self._file_battle(record)
        msgs = [line, story, *battlelog.gains_list(record), *self._last_wear]
        if attacker:
            msgs.insert(0, f"體力 -{c.config.raid.stamina}")
        if self._draft is None:
            self._write(f"截殺・{rival}" if attacker else f"遭{rival}截殺", msgs, tag=battlelog.outcome_text(record))
        return msgs

    # ── 後期體力玩法第一批（Joy 2026-10-16）：設伏劫道（ambush.py）、屯糧練兵（works.py；修築工事 2026-10-27 跟著舊拔河拿掉）──

    def _stamina_play_options(self) -> list[Option]:
        """「此地還能做」裡的體力玩法：守著埋伏時只有「收伏」；否則這裡設得了伏的每一段路一顆、屯糧一顆。
        劫不到人的（散人沒揭通緝、新手期）不畫設伏鈕；序章裡沒有。"""
        s, c = self.state, self.content
        if prologue_rules.active(s, c) or s.world.ended:
            return []
        p = s.player
        opts: list[Option] = []
        if p.ambush is not None:
            to = c.locations[p.ambush.to].name
            opts.append(Option(id="ambush:lift", label=ambush_rules.LIFT_LABEL.format(to=to, until=self.stamp(p.ambush.until))))
        elif ambush_rules.on(c) and ambush_rules.has_prey(s, c) and not roster.raid_newbie(s, c):
            for to in ambush_rules.roads(s, c):
                label = ambush_rules.SET_LABEL.format(to=c.locations[to].name)
                opts.append(self._cost_option(f"ambush:set:{to}", label, c.config.ambush.stamina))
        stock = works.stock_spot(s, c)
        if stock is not None:
            name = c.scenario.faction_name(stock, stock)
            label = works.STOCK_LABEL.format(side=name, n=s.world.supply.get(stock, 0))
            opts.append(self._cost_option("works:stockpile", label, c.config.stockpile.stamina))
        # 功能包的選項（FEATURES 照順序）接在護衛那一串之後、盤算之前；序章裡、休季不問（同上面的體力玩法）
        return opts + self._aid_options() + features_core.options(self) + self._plan_options()

    def _aid_options(self) -> list[Option]:
        """護著同陣營的大勢人物（figure_aid）：這裡在場的同陣營人物各一顆護衛、一顆犒軍；在自己陣營的大本營，被挑戰打退、
        還在等回來的人物各一顆探望。按不下去的灰掉寫原因。"""
        s, c = self.state, self.content
        p = s.player
        if not figure_aid.on(c) or p.faction is None or p.journey is not None:
            return []
        cfg = c.config.figure_aid
        side = self._side()
        opts: list[Option] = []
        for fid in figures.present_at(s, c, p.location):
            fig = c.figures[fid]
            if fig.faction != side:
                continue
            post = figure_aid.guarding(s, c, p.name, fid)
            if post is not None:
                opts.append(Option(id=f"aid:guard:{fid}", enabled=False,
                                   label=figure_aid.GUARD_ON_LABEL.format(name=fig.name, until=self.stamp(post.until))))
            else:
                label = figure_aid.GUARD_LABEL.format(name=fig.name)
                problem = figure_aid.guard_problem(s, c, fid)
                opts.append(Option(id=f"aid:guard:{fid}", label=f"{label}（{problem}）", enabled=False) if problem
                            else self._cost_option(f"aid:guard:{fid}", label, cfg.guard_stamina))
            now = figures.state_of(s, c, fid)
            label = figure_aid.RALLY_LABEL.format(name=fig.name, now=now.prestige, cap=fig.start_prestige, silver=cfg.rally_silver)
            problem = figure_aid.rally_problem(s, c, fid)
            opts.append(Option(id=f"aid:rally:{fid}", label=f"{label}（{problem}）", enabled=False) if problem
                        else self._cost_option(f"aid:rally:{fid}", label, cfg.rally_stamina))
        for fid in figure_aid.visiting(s, c):
            name = c.figures[fid].name
            label = figure_aid.VISIT_LABEL.format(name=name, left=figure_aid.left_text(s, c, fid))
            problem = figure_aid.visit_problem(s, c, fid)
            opts.append(Option(id=f"aid:visit:{fid}", label=f"{label}（{problem}）", enabled=False) if problem
                        else self._cost_option(f"aid:visit:{fid}", label, cfg.visit_stamina))
        return opts

    def _aid_act(self, arg: str) -> list[str]:
        """護衛（aid:guard:<id>）、犒軍（aid:rally:<id>）、探望（aid:visit:<id>）：重驗、扣體力（犒軍另扣銀兩）、記進這一季；
        第一季規則開著時記 contrib_push 點推力的貢獻。"""
        s, c = self.state, self.content
        p = s.player
        cfg = c.config.figure_aid
        verb, _, fid = arg.partition(":")
        refuse = ["（此刻無法這麼做。）"]
        if not figure_aid.on(c) or p.faction is None or fid not in c.figures or p.journey is not None:
            return refuse
        fig = c.figures[fid]
        if verb in ("guard", "rally"):
            if fig.faction != self._side() or fid not in figures.present_at(s, c, p.location):
                return refuse
            if verb == "guard":
                cost, problem = cfg.guard_stamina, figure_aid.guard_problem(s, c, fid)
            else:
                cost, problem = cfg.rally_stamina, figure_aid.rally_problem(s, c, fid)
        elif verb == "visit":
            if fid not in figure_aid.visiting(s, c):
                return refuse
            cost, problem = cfg.visit_stamina, figure_aid.visit_problem(s, c, fid)
        else:
            return refuse
        if problem is None and p.stamina < cost:
            problem = f"體力不夠（要 {cost} 點）"
        if problem is not None:
            return [problem if problem.startswith("（") else f"（{problem}。）"]
        p.stamina -= cost
        changes = [f"體力 -{cost}"]
        if verb == "guard":
            post = figure_aid.guard(s, c, fid, self._battle_power())
            msgs = [figure_aid.GUARD_DONE.format(name=fig.name, until=self.stamp(post.until))]
        elif verb == "rally":
            p.stats["silver"] = p.stats.get("silver", 0) - cfg.rally_silver
            changes.append(f"銀兩 -{cfg.rally_silver}")
            n = figure_aid.rally(s, c, fid)
            now = figures.state_of(s, c, fid)
            msgs = [figure_aid.RALLY_DONE.format(silver=cfg.rally_silver, name=fig.name, n=n, now=now.prestige, cap=fig.start_prestige)]
        else:
            hours = figure_aid.visit(s, c, fid)
            msgs = [figure_aid.VISIT_DONE.format(name=fig.name, hours=figure_aid.hours_text(hours))]
        if verb in ("guard", "rally") and fig.character:  # 求援委託（第三批）：護衛、犒軍他也算辦成
            msgs += bounties.on_aid(s, c, fig.character)
        if self._draft is not None:
            self._draft.changes += changes
        if season_one(c, s.world) and cfg.contrib_push:
            contrib = c.config.contrib_per_push * cfg.contrib_push
            wins.credit(p, c, s.world, calendar.point(s.world.time, c, s.world).week, contrib)
            msgs.append(f"貢獻 +{contrib}")
        return msgs

    def _deliver_guard_credits(self) -> None:
        """護衛替人物擋下的挑戰（figure_aid.contest 記在 WorldState.guard_credits）：自己同步時補名望 guard_fame、心得 guard_xinde
        （每擋一次），一則紀錄。做法同 _deliver_echoes：擋下的那一下不動護衛的角色。"""
        s, c = self.state, self.content
        lines = s.world.guard_credits.pop(s.player.name, None)
        if not lines:
            return
        cfg = c.config.figure_aid
        n = len(lines)
        out = list(lines)
        if cfg.guard_xinde:
            s.player.stats["xinde"] = s.player.stats.get("xinde", 0) + cfg.guard_xinde * n
            out.append(f"心得 +{cfg.guard_xinde * n}")
        if cfg.guard_fame:
            out += renown.gain(s, c, "fame", cfg.guard_fame * n)
        self._write(figure_aid.CREDIT_TITLE, out)
        self._save_season()

    def _ambush_act(self, arg: str) -> list[str]:
        """設伏（ambush:set:<另一頭>）或收伏（ambush:lift）。設伏：重驗、扣體力、季上與角色身上各記一筆。收伏：季上那一筆記收起的時刻。"""
        s, c = self.state, self.content
        p = s.player
        verb, _, to = arg.partition(":")
        if verb == "lift":
            if p.ambush is None:
                return ["（此刻無法這麼做。）"]
            ambush_rules.lift(s.world, p.ambush, p.name, s.world.time)
            p.ambush = None
            return [ambush_rules.LIFTED]
        cost = c.config.ambush.stamina
        problem = ambush_rules.set_problem(s, c, to)
        if problem is None and p.stamina < cost:
            problem = f"體力不夠（要 {cost} 點）"
        if problem is not None:
            return [problem if problem.startswith("（") else f"（{problem}。）"]
        p.stamina -= cost
        a = ambush_rules.place(s, c, to)
        if self._draft is not None:
            self._draft.changes.append(f"體力 -{cost}")
        return [ambush_rules.SET_DONE.format(to=c.locations[to].name, until=self.stamp(a.until))]

    def _ambush_expire(self) -> None:
        """同步時：守著的埋伏到了時刻、或季上那一筆已經不在了（被路過的人打退時季上記了收起、角色那一筆一起清；換季的新季沒有這一筆），
        收起來。到時刻的寫一則江湖紀錄。"""
        s = self.state
        post = s.player.ambush
        if post is None:
            return
        if ambush_rules.mine_now(s.world, post, s.player.name) is None:
            s.player.ambush = None
            return
        if ambush_rules.expired(s):
            s.player.ambush = None
            self._write(ambush_rules.TITLE, [ambush_rules.EXPIRED.format(to=self.content.locations[post.to].name)])

    def _ambush_check(self, a: str, b: str, when: float) -> list[str]:
        """路過的人（self）在 when 那一刻走完 a—b 那一段：這一段當時有沒有敵對的伏兵。每換一段只查一次字典（WorldState.ambushes[路段鍵]），
        真的要打才讀伏兵的存檔。保護照截殺：雙方過了新手期、同一個伏兵劫同一個人的冷卻、剛被截過的護身（照 when 比）。一段只打一場。"""
        s, c = self.state, self.content
        w = s.world
        if not w.ambushes or not ambush_rules.on(c):
            return []
        found = w.ambushes.get(ambush_rules.key(a, b))
        if not found:
            return []
        me = s.player
        if prologue_rules.active(s, c) or roster.raid_newbie(s, c):
            return []
        cfg, shield = c.config.ambush, c.config.raid.shield_seconds
        hit = w.raided.get(name_key(me.name))
        if hit is not None and abs(when - hit) < shield:
            return []
        side = self._side()
        for amb in sorted(found, key=lambda x: x.set_at):
            if not (amb.set_at <= when < ambush_rules.end_of(amb)) or name_key(amb.owner) == name_key(me.name):
                continue
            if not ambush_rules.maybe_hostile(w, amb, side, me.name):  # 自己人：不必讀他的存檔
                continue
            last = w.raids.get(self._raid_key(amb.owner, me.name))
            if last is not None and abs(when - last) < cfg.pair_cooldown_seconds:
                continue
            owner = self._load_kin(amb.owner)
            if owner is None or roster.raid_newbie(owner.state, c):
                continue
            if not ambush_rules.hostile(owner.state, s, c):
                continue
            return self._ambush_fight(owner, amb, when)
        return []

    def _ambush_fight(self, owner: Game, amb, when: float) -> list[str]:
        """路過的人（self）中了 owner 的埋伏：記冷卻與護身、用本人的威力照單次判定打一場（從伏兵看；亂數用自己的種子，不動 Game.rng），
        贏的搶走輸的一點銀兩與素材、輸的扣氣血（_ambush_spoils）。伏兵輸了，埋伏散了。雙方各一份戰報；伏兵的存檔在這裡寫回，
        季（冷卻、埋伏的紀錄、通緝交差）由路過的人的 sync／travel 最後一起存。"""
        s, c = self.state, self.content
        w, me = s.world, s.player
        key = self._raid_key(amb.owner, me.name)
        w.raids[key] = max(w.raids.get(key, when), when)
        w.raided[name_key(me.name)] = max(w.raided.get(name_key(me.name), when), when)
        amb.caught += 1
        ours, theirs = self._spar_power(owner, self), self._spar_power(self, owner)
        ours_shown, theirs_shown = self._spar_power(owner, self, seal=False), self._spar_power(self, owner, seal=False)  # 戰報給對方看的（FB-615）
        result = encounter.resolve_encounter(ours, theirs, random.Random(f"設伏|{amb.owner}|{me.name}|{when}"))
        mirrored = self._spar_mirror(result, theirs)
        if result.tier in team.WIN_TIERS:
            winner, loser = owner, self
        elif mirrored.tier in team.WIN_TIERS:
            winner, loser = self, owner
        else:
            winner = loser = None
        spoils = winner._ambush_spoils(loser) if winner is not None else None
        broke = loser is owner
        if broke:  # 伏兵被打退：埋伏散了（身上那一筆是這一處才清：下線的人晚補算時，伏兵可能已經另設了一處）
            post = owner.state.player.ambush
            if post is not None and ambush_rules.mine_now(w, post, amb.owner) is amb:
                owner.state.player.ambush = None
            amb.lifted_at = max(amb.set_at, when)
        self.touched.add(amb.owner)
        owner._ambush_record(result, me.name, theirs, self, spoils, as_owner=True, shown=theirs_shown,
                             extra=[ambush_rules.BROKEN.format(rival=me.name, to=c.locations[amb.to].name)] if broke else [])
        msgs = self._ambush_record(mirrored, owner.state.player.name, ours, owner, spoils, as_owner=False, shown=ours_shown)
        if winner is owner:
            owner._raid_bounty(me.name)  # 伏兵揭了通緝他：交差（寫在伏兵自己的紀錄）
        elif winner is self:
            msgs += self._raid_bounty(owner.state.player.name)
        self._save_kin(owner)
        return msgs

    def _ambush_spoils(self, loser: Game) -> RaidSpoils:
        """贏的是 self：loser 失銀兩（比例、有上限）、幾個素材（手上最多的、一階先），self 拿走（Joy：輸的東西被搶走）；loser 扣氣血上限的
        hp_loss（乘 1−他身上防具的減損；不吃化勁、不變成內傷，同截殺）；第一季規則開著時 self 記一點貢獻。"""
        c, cfg = self.content, self.content.config.ambush
        lp, wp = loser.state.player, self.state.player
        purse = lp.stats.get("silver", 0)
        lost = min(cfg.silver_cap, math.ceil(purse * cfg.silver_share)) if purse > 0 else 0
        taken = math.ceil(lost * cfg.take_share)
        lp.stats["silver"] = purse - lost
        wp.stats["silver"] = wp.stats.get("silver", 0) + taken
        goods: list[tuple[str, int]] = []
        left = cfg.materials
        held = sorted(  # 四階搶不走（正式季整合 4.6：四階不在人與人之間轉手）
            ((mid, n) for mid, n in lp.materials.items() if n > 0 and mid in c.materials and not four_tiers.tier4_id(c, mid)),
            key=lambda item: (c.materials[item[0]].tier, -item[1], item[0]),
        )
        for mid, n in held:
            if left <= 0:
                break
            got = min(n, left)
            lp.materials[mid] = n - got
            if lp.materials[mid] <= 0:
                del lp.materials[mid]
            wp.materials[mid] = wp.materials.get(mid, 0) + got
            goods.append((mid, got))
            left -= got
        con = team.con_of(loser.state, c, loser.world, PLAYER)
        cut = team.armor_cut(loser.state, c, loser.world)
        hp, _ = team._apply_toll(c, lp.member, cfg.hp_loss * (1 - cut), agi=lp.stats.get("agi", team.BASE_STAT), con=con, injury=0.0,
                                 season=loser.state.world)
        contrib = c.config.contrib_per_push * cfg.win_contrib_push if wp.faction is not None and season_one(c, self.state.world) else 0
        if contrib:
            wins.credit(wp, c, self.state.world, calendar.point(self.state.world.time, c, self.state.world).week, contrib)
        return RaidSpoils(winner=wp.name, lost=lost, taken=taken, hp=round(hp), contrib=contrib, goods=tuple(goods))

    def _ambush_record(
        self, result: encounter.EncounterResult, rival: str, rival_power: float, rival_game: Game,
        spoils: RaidSpoils | None, *, as_owner: bool, extra: list[str] | None = None, shown: float | None = None,
    ) -> list[str]:
        """這一邊的戰報與紀錄（同截殺，戰報只列本人）。伏兵這一邊不在行動裡，寫一則「設伏・對手」；路過的人併進這一趟路的那一則。
        shown 同 _spar_record。"""
        s, c = self.state, self.content
        p = s.player
        squad = Squad(
            id=f"ambush:{rival}", name=rival, difficulty=rival_power,
            attribute=team.worn_attribute(rival_game.state, c, rival_game.world),
        )
        record = battlelog.new_record(s, c, self.world, squad, result, "ambush")
        if shown is not None:
            record.difficulty = shown
        record.ours = record.ours[:1]
        won = spoils is not None and name_key(spoils.winner) == name_key(p.name)
        hp_lost: int | None = 0
        him = gender.pronoun(rival_game.state)
        if spoils is None:
            story = (ambush_rules.OWNER_DRAW if as_owner else ambush_rules.PASSER_DRAW).format(rival=rival, him=him)
        elif won:
            record.silver = spoils.taken
            record.materials += [f"{c.materials[mid].name} ×{n}" for mid, n in spoils.goods]
            if spoils.contrib:
                record.changes.append(f"貢獻 +{spoils.contrib}")
            story = (ambush_rules.OWNER_WON if as_owner else ambush_rules.PASSER_WON).format(rival=rival, him=him)
        else:
            record.silver = -spoils.lost
            record.changes += [f"{c.materials[mid].name} -{n}" for mid, n in spoils.goods]
            hp_lost = spoils.hp
            if spoils.hp > 0:
                record.changes.append(f"氣血 -{spoils.hp}")
            story = (ambush_rules.OWNER_LOST if as_owner else ambush_rules.PASSER_LOST).format(rival=rival, him=him)
        record.notes.append(story)
        annals.note(s, c, annals.FIGHT, story, 3 if won else 2, keep=[rival])
        self._play_rounds(record, squad, result.tier, hp_lost)
        line = self._file_battle(record)
        msgs = [line, story, *battlelog.gains_list(record), *self._last_wear, *(extra or [])]
        if self._draft is None:
            self._write(f"{ambush_rules.TITLE}・{rival}" if as_owner else f"中伏・{rival}", msgs, tag=battlelog.outcome_text(record))
        return msgs

    def _works_act(self, arg: str) -> list[str]:
        """屯糧練兵（works:stockpile）：重驗、扣體力、記進這一季；第一季規則開著時記一點貢獻（同捐軍備的寫法）。"""
        s, c = self.state, self.content
        p = s.player
        if arg == "stockpile":
            side = works.stock_spot(s, c)
            cfg = c.config.stockpile
            if side is None or p.stamina < cfg.stamina:
                return ["（此刻無法這麼做。）"]
            p.stamina -= cfg.stamina
            n = works.stockpile(s, side)
            msgs = [works.STOCK_DONE.format(side=c.scenario.faction_name(side, side), n=n)]
            cost = cfg.stamina
        else:
            return ["（此刻無法這麼做。）"]
        if self._draft is not None:
            self._draft.changes.append(f"體力 -{cost}")
        if p.faction is not None and season_one(c, s.world):
            contrib = c.config.contrib_per_push
            wins.credit(p, c, s.world, calendar.point(s.world.time, c, s.world).week, contrib)
            msgs.append(f"貢獻 +{contrib}")
        return msgs

    # ── 單人頭目戰（tianxia/duel.py；Joy 2026-10-10：「有種打小 boss 的感覺，也可以算是大事件的單人體驗版，可以放手一搏自訂行動」）──

    def _duel_start(self, boss: DuelBoss) -> list[str]:
        """探索遇上頭目：快照份量、職位與氣血池（同加入決戰），記這一季遇上幾次與冷卻，擲他第一回合的招。"""
        s, c = self.state, self.content
        p, cfg = s.player, c.config.duel
        now, cap = self._player_hp_and_cap()
        key = duel_rules.season_key(s, boss.id)
        power = self._battle_power()
        duel = DuelState(
            boss=boss.id, foe=duel_rules.foe_index(boss, p.faction), edge=cfg.start, hp=now, hp_cap=cap, hp_start=now,
            power=power, scores=self._battle_scores(mounted=False), role=self._battle_role(),
            # 頭目戰不算騎兵：設計 2.1 的三個用途沒有頭目戰
            # 江湖水漲：照你的武學威力浮上來；玉璽碎片的戰力不浮上去（改版 PM 五之一 2），沒碎片時跟 power 一樣
            difficulty=rise.duel(c, boss.difficulty, self._battle_power(seal=False), p.duel_tally.get(key, 0)),
        )
        p.duel_tally[key] = p.duel_tally.get(key, 0) + 1
        if cfg.per_boss_week:  # 21 天季另記這一週的帳（正式季整合 2.5）；季的帳照記，江湖水漲照它算
            week = duel_rules.week_key(s, c, boss.id)
            p.duel_tally[week] = p.duel_tally.get(week, 0) + 1
        p.duel_last = [float(p.season_number), s.world.time]
        foe = boss.foes[duel.foe]
        duel.bout = tactics.open_bout(  # 本命戰法（第二批）：只算你身上的兩門；頭目沒有本命戰法
            team.self_side(s, c, self.world), None, "你", foe.name, a_faction=p.faction, b_faction=foe.side,
            b_agility=rounds.foe_agility(duel_rules.foe_difficulty(duel, boss)),
        )
        duel_rules.roll_next(duel, foe, cfg, self.rng)
        p.duel = duel
        self._outcome(f"遇上{foe.title}{foe.name}", "")
        role = battle_instance.role_name(c.config.battle, duel.role)
        meet = renown.duel_meet_line(s, c)  # 名聲 4.4：名望高、攔路的也多，說出原因
        return [f"你在{c.locations[p.location].name}走著，{foe.title}{foe.name}攔住了去路！", foe.intro] + (
            [f"你以{role}的架勢迎上去。"] if role else []
        ) + ([meet] if meet else [])

    def _duel_scene(self) -> str:
        duel = self.state.player.duel
        boss, foe = duel_rules.foe_of(self.content, duel)
        lines = [
            f"**{foe.title}・{foe.name}**（頭目戰 第 {duel.round + 1}／{boss.rounds} 回合）",
            foe.intro if duel.round == 0 else duel.lines[-1],
            f"氣勢：{duel_rules.edge_words(duel.edge)}（{duel.edge:.0f}／100）　你的氣血：{duel.hp:.0f}／{duel.hp_cap:.0f}",
            *self._bout_lines(duel.bout),
            f"{duel.tell}{tactics.SEEN_NOTE if tactics.locks(duel.bout).sees else '（架勢不一定是真的。）'}",
            "固守剋強攻、強攻剋奇襲、奇襲剋固守；也可以在下面寫一句，放手一搏。",
        ]
        return "\n\n".join(lines)

    def duel_free_text_prompt(self) -> str | None:
        """頭目戰打到一半時輸入框的提示語，否則 None（server.py 照它決定輸入框，送出走 duel_text）。"""
        if self.state.player.arena is not None:
            return arena.PROMPT
        return "放手一搏：寫下你要怎麼對付他（20 字以內）" if self.state.player.duel is not None else None

    DUEL_GAMBLE_NOTE = "寫得越險，成了越能扭轉局面；失手時氣勢倒退，重傷的是你自己。這一回合他的招不算。"

    def duel_free_text_note(self) -> str | None:
        return self.DUEL_GAMBLE_NOTE if self.state.player.duel is not None or self.state.player.arena is not None else None

    def _duel_text_check(self, text: str) -> str | list[str]:
        if self.world.paused_at() is not None:
            return [f"（{PAUSED_TEXT}。）"]
        if self.state.player.duel is None and self.state.player.arena is None:
            return ["（此刻無法這麼做。）"]
        text = text.strip()[:FREE_TEXT_MAX]
        if not text:
            return ["（請先輸入你想做的事。）"]
        p = self.state.player
        if tactics.locks(p.arena.bout if p.arena is not None else p.duel.bout).no_gamble:
            return [tactics.NO_GAMBLE]
        return text

    def _bout_lines(self, bout: tactics.Bout | None) -> list[str]:
        """頭目戰、擂台的場景：兩邊身上的本命戰法狀態各一行（沒有就不寫）。"""
        return [line for line in (tactics.status_text(bout, "a"), tactics.status_text(bout, "b")) if line]

    def _bout_rng(self, kind: str, key: object, round_: int) -> random.Random:
        """本命戰法這一回合的亂數（不碰 Game.rng）：種類｜季數｜名號｜哪一場｜第幾回合。"""
        p = self.state.player
        return random.Random(f"{kind}|{p.season_number}|{p.name}|{key}|{round_}|戰法")

    def duel_text_request(self, text: str) -> DuelTextRequest | list[str]:
        """頭目戰放手一搏的 A 段（鎖內、只讀）：送得出去回傳要在鎖外送模型的單子，不行回傳那一句話。"""
        checked = self._duel_text_check(text)
        if isinstance(checked, list):
            return checked
        s, c = self.state, self.content
        fight = s.player.arena
        if fight is not None:  # 擂台：對手那一行寫分身的身手（同奪璽單挑），場合寫擂台
            here = arena.scene(fight)
            return DuelTextRequest(
                boss=f"arena:{fight.id}", round=fight.round, text=checked, name=s.player.name, faction_name=self._duel_side(),
                title=here.title, scene=here.text, sex=gender.of(s), target=arena.foe_line(fight.me, fight.foe, c),
                setting=arena.SETTING, place=arena.PLACE,
            )
        duel = s.player.duel
        here = duel_rules.scene(c, duel)
        return DuelTextRequest(
            boss=duel.boss, round=duel.round, text=checked, name=s.player.name, faction_name=self._duel_side(),
            title=here.title, scene=here.text, sex=gender.of(s),
        )

    def seal_free_text_prompt(self) -> str | None:
        """奪璽單挑的放手一搏輸入框（5.7）：自己是一方、這一回合在場、還沒出手、這一場還沒搏滿兩次才有。"""
        duel, who = self._my_seal_duel()
        if duel is None or who is None or seal_duel.submit_problem(duel, who, self.content.config.seal, text=True):
            return None
        return seal_duel.PROMPT

    def seal_free_text_note(self) -> str | None:
        return seal_duel.GAMBLE_NOTE if self.seal_free_text_prompt() is not None else None

    def seal_text_request(self, text: str) -> seal_duel.TextRequest | list[str]:
        """奪璽放手一搏的 A 段（鎖內、只讀，5.7）：驗證他是這場單挑的一方、這一回合開始時判他在場、還沒送出、還能搏、文字 20 字以內，
        開單子（單挑 id、回合、哪一邊、文字、名號、場景、對手那一行）。判成不在場的這一回合不開單。"""
        if self.world.paused_at() is not None:
            return [f"（{PAUSED_TEXT}。）"]
        duel, who = self._my_seal_duel()
        if duel is None or who is None:
            return ["（此刻無法這麼做。）"]
        problem = seal_duel.submit_problem(duel, who, self.content.config.seal, text=True)
        if problem:
            return [f"（{problem}）"]
        text = text.strip()[:FREE_TEXT_MAX]
        if not text:
            return ["（請先輸入你想做的事。）"]
        me, foe = getattr(duel, who), getattr(duel, seal_duel.other(who))
        title, scene_text = seal_duel.scene(duel, who, self.content)
        return seal_duel.TextRequest(
            duel=duel.id, round=duel.round, side=who, text=text, name=me.name, faction_name=self._duel_side(),
            title=title, scene=scene_text, target=seal_duel.foe_line(me, foe, self.content), sex=gender.of(self.state),
        )

    def seal_gamble(
        self, text: str, rate: int | None = None, stories: tuple[str, str] | None = None,
        request: seal_duel.TextRequest | None = None,
    ) -> list[str]:
        """奪璽放手一搏的 C 段（5.7）：鎖內重驗，同一場、同一回合、同一邊、同一句才採用，記進 pending（送出不等於結算，湊齊而且滿 20 秒才算）。
        回合對不上直接回「這一回合已經結算」，不重評、不套用（不照抄 duel_gamble 的鎖內重評：會把第 r 回合寫的那一句套到第 r＋1 回合）。
        沒給 request（腳本、測試）就在這裡開單；沒給分數就用 _quick_client 在鎖內評，評不到是 40。"""
        if request is None:
            request = self.seal_text_request(text)
            if isinstance(request, list):
                return self._log(request)
        if rate is None:
            verdict = battle_instance.assess_gamble(
                self._quick_client(), duel_rules.Scene(request.title, request.scene), request.faction_name, request.text, request.name,
                setting=seal_duel.SETTING, place=seal_duel.PLACE, target=request.target, sex=request.sex,
            )
            rate, stories = verdict.rate, (verdict.win, verdict.lose)
        checked = text.strip()[:FREE_TEXT_MAX]
        me, cfg = self.state.player.name, self.content.config.seal
        out: list[str] = []

        def _apply(shared) -> None:
            duel = shared.seal_duels[0] if shared.seal_duels else None
            if duel is None or duel.id != request.duel or duel.round != request.round or duel.phase != "active":
                out.append(f"（{seal_duel.GONE}）")
                return
            who = seal_duel.side_of(duel, me)
            if who != request.side or checked != request.text:
                out.append(f"（{seal_duel.RESEND}）")
                return
            problem = seal_duel.submit_problem(duel, who, cfg, text=True)
            if problem:
                out.append(f"（{problem}）")
                return
            seal_duel.submit(duel, who, text=checked, rate=rate, stories=stories)
            seal_duel.note_seen(duel, who, self.now, cfg)
            out.append(f"你放手一搏：「{checked}」")
            out.extend(seal_duel.advance(shared, self.content, self.now))

        self.world.mutate(_apply)
        self._deliver_seal_results()
        return self._log(out)

    def seal_view(self) -> dict | None:
        """持有者的碎片卡（第十節，status_data["seal"]）：哪一片與效果、這一季動過沒（新得之季此季不動／此季已動過／此季可能被牽動）、
        此刻被牽動時那一句、這一季標了 seal 還沒到的決戰時刻（Game.stamp）。不寫機率。不是持有者是 None。"""
        c = self.content
        if not seal.on(c):
            return None
        view = self.world.seal_state()
        shard = seal.shard_of(view.registry, self.state.player.name)
        if shard is None or shard.id not in c.seal:
            return None
        if seal.mandate_now(view.registry, view.season):  # 天命之季沒有新主保護（8.2）
            state = seal.CARD_STIRRED if shard.stirred_season == view.season else seal.CARD_MANDATE
        else:
            state = seal.CARD_NEW if shard.since_season == view.season else seal.CARD_STIRRED if shard.stirred_season == view.season else seal.CARD_CALM
        status = self._showdown_status(tick=False)  # 璽動只在時刻表決戰（攻城戰不璽動）
        stir = seal.STIR_MINE.format(shard=c.seal[shard.id].name) if status is not None and status[0].seal_shard == shard.id else ""
        w = self.state.world
        dates = [
            self.stamp(timetable.when(_season_vehicle(c, w), c, e)) for e in timetable.events(w, c)
            if (e.seal or e.mandate_only) and e.id not in w.timeline and e.id not in w.showdowns_opened
        ] if season_one(c, w) else []
        out = {"name": c.seal[shard.id].name, "effect_text": seal.shard_text(c, shard.id), "state": seal.card_state(c, state),
               "stir": stir, "dates": dates}
        if seal_acts.on(c):  # 獨門行動（改版第 2、3 批）：改版關著不多這一鍵（一個字都不變）；這一片沒有行動是 None
            out["act"] = seal_acts.view(self.state, c, seal.filled(view.registry, c), view.season, **self._seal_act_season())
        return out

    def _seal_act_season(self) -> dict:
        """seal_acts.problem／view 要的季況：季在跑（籌備、休季都不是）、賽季時鐘停著、時刻怎麼寫（Game.stamp）。"""
        return {"running": self.world.season_phase() == "running" and not self.state.world.ended,
                "paused": self.world.paused_at() is not None, "stamp": self.stamp}

    def seal_use(self, target: str = "", side: str = "") -> list[str]:
        """起用懷中那一片的獨門行動（玉璽碎片改版第 2、3 批；MAIN_ACTIONS["seal_use"]）：target 是指定的目標（引將的大勢人物、傳檄的戰線、
        收心的人物、鎮地與補缺的區塊；頒詔、承露不用），side 是散人挑的那一軍（傳檄、鎮地、補缺）。不花體力、不花銀兩（PM 五之一 7）。
        補缺當場把那一塊退回原主（conquest.restore，照翻地的規則記一次易手）；鎮地只記在季上（conquest.push_problem 讀）。
        先照 seal_acts.problem／target_problem 驗（按不下去回原因、什麼都不動）；登記那一筆在 world.mutate 裡整個重驗（碎片剛被搶走、
        次數剛用完就落空），記次數與一筆 use（只給管理者看：有名號）；季上記一筆生效中的（不記是誰）、引將把人物搬過來；天下大事與
        江湖史各一句（不寫是誰，企劃者）；自己一則江湖紀錄與一則行狀。戰報不寫。假人不叫這裡（設計第四章【PM】）。"""
        c, s = self.content, self.state
        if not seal_acts.on(c):
            return self._log(["（此刻無法這麼做。）"])
        view = self.world.seal_state()
        reg = seal.filled(view.registry, c)
        why = seal_acts.problem(s, c, reg, view.season, **self._seal_act_season())
        held = seal_acts.mine(s, c, reg)
        if why is None and held is not None:
            why = seal_acts.target_problem(s, c, held[1], target, side)
        if why is not None or held is None:
            return self._log([f"（{why or seal_acts.NO_SHARD}）"])
        shard_id, kind = held[0].id, held[1]
        act = seal_acts.plan(s, c, shard_id, kind, target, side)
        what = seal_acts.what_text(c, act)
        me, w = s.player.name, s.world
        left: list[int] = []

        def _apply(shared) -> None:
            r = seal.filled(shared.seal, c)
            now = seal.shard_of(r, me)
            number = shared.season_number
            if now is None or now.id != shard_id or seal_acts.left(now, number, c) <= 0:
                return
            ready = seal_acts.ready_at(now, number, c, w)
            if ready is not None and w.time + seal_acts.EPS < ready:
                return
            seal_acts.note_use(now, number, w.time)
            seal.log_use(r, number, shard=shard_id, holder=me, act=kind, what=what, at=w.time)  # 另記一欄（FB-695）
            left.append(seal_acts.left(now, number, c))

        self.world.mutate(_apply)
        if not left:
            return self._log(["（此刻無法這麼做。）"])
        if kind == "yinjiang":
            seal_acts.pull(s, c, act)
        w.seal_acts.append(act)
        public = seal_acts.public_text(c, act)
        seal.rumor(w, public)  # 天下大事（world 層、不帶地點與人）
        seal.chronicle(w, public)
        if kind == "bujue":  # 補缺：當場退回原主（「收復」那一句天下大事與江湖史照易手寫，排在起用那一句之後）
            conquest.restore(w, c, act.target, act.side)
        name = c.seal[shard_id].name
        line = seal_acts.MINE.format(shard=name, what=what, left=left[0])
        self._write(seal.SEAL_TITLE, [line], tag=f"『{name}』")
        annals.note(s, c, annals.SEAL, seal_acts.ANNAL.format(shard=name, what=what), 4)  # 酒肆打聽不到這一類（FB-643）
        self._save_season()
        return self._log([line])

    def seal_duel_card(self) -> dict | None:
        """江湖頁的「奪璽」卡（5.10）：排第一的那一場，全服看得到；沒有是 None。"""
        duels = self.world.seal_state().duels if seal.on(self.content) else []
        if not duels:
            return None
        paused = self.world.paused_at()  # 暫停中倒數停在按下暫停的那一刻（同決戰那一格，FB-179）
        return seal_duel.card(duels[0], self.state.player.name or None, self.now if paused is None else paused, self.content)

    def seal_watch(self) -> bool:
        """網頁在背景也要輪詢（5.5）：自己是單挑的一方；或此刻有一場被璽動、還沒收場的決戰，自己是那一片的持有者或那一場的參戰者
        （挑戰者要到收場才確定）。"""
        if not seal.on(self.content):
            return False
        _, who = self._my_seal_duel()
        if who is not None:
            return True
        status = self._showdown_status(tick=False)  # 璽動只在時刻表決戰（攻城戰不璽動）
        if status is None or not status[0].seal_shard:
            return False
        battle, me = status[0], self.state.player.name
        return seal.key(battle.seal_holder) == seal.key(me) or me in battle.participants

    def _duel_side(self) -> str:
        faction = self.state.player.faction
        return self.content.scenario.faction_name(faction, faction) if faction else "散人"

    def duel_gamble(
        self, text: str, llm_rate: int | None = None, stories: tuple[str, str] | None = None,
        request: DuelTextRequest | None = None, crowd: str = "",
    ) -> list[str]:
        """頭目戰放手一搏的 C 段（擂台也走這裡：crowd 是鎖外判的觀眾反應，arena_crowd.judge_gamble）：llm_rate 是鎖外評好的成功率，request 是當時開的單子——還是同一隻、同一回合才用，
        對不上（這一回合已經出過招、換了一場）就丟掉重評。沒給分數（假人不寫自由文字；腳本、測試）在這裡用 _quick_client 評，
        評不到是保底的 40。擲骰、推進、損耗全在 duel.gamble。"""
        checked = self._duel_text_check(text)
        if isinstance(checked, list):
            return self._log(checked)
        s, c = self.state, self.content
        if s.player.arena is not None:
            return self._log(self._arena_gamble(checked, llm_rate, stories, request, crowd))
        duel = s.player.duel
        if request is not None and (request.boss, request.round, request.text) != (duel.boss, duel.round, checked):
            llm_rate, stories = None, None
        if llm_rate is None:
            verdict = battle_instance.assess_gamble(
                self._quick_client(), duel_rules.scene(c, duel), self._duel_side(), checked, s.player.name,
                setting=duel_rules.SETTING, place=duel_rules.PLACE, sex=gender.of(s),
            )
            llm_rate, stories = verdict.rate, (verdict.win, verdict.lose)
        s.battle_card = None
        s.player.guide_done = []
        boss, _ = duel_rules.foe_of(c, duel)
        fired: list[str] = []
        won, delta, hp, _ = duel_rules.gamble(duel, int(llm_rate), c.config.duel, c.config.battle, self.rng,
                                              c.config.tactics, self._bout_rng("頭目戰", duel.boss, duel.round), fired)
        story = (stories or ("", ""))[0 if won else 1]
        if not story:
            story = f"你放手一搏：「{checked}」——{'成了！' if won else '沒成，反倒露了破綻。'}"
        line = tactics.round_line(f"第 {duel.round + 1} 回合：{story}（氣勢 {delta:+d}，你氣血 {-hp:+d}）", fired)
        return self._log(self._duel_after(line))

    def _duel_act(self, arg: str) -> list[str]:
        """選單上的一招，或抽身退走。"""
        s, c = self.state, self.content
        duel = s.player.duel
        if duel is None:
            return ["（此刻無法這麼做。）"]
        boss, foe = duel_rules.foe_of(c, duel)
        if arg == "flee":
            return self._duel_finish(None, "你虛晃一招，抽身退走。")
        if arg not in MOVES:
            return ["（此刻無法這麼做。）"]
        if arg in tactics.locks(duel.bout).no_moves:
            return [tactics.NO_MOVE.format(move=arg)]
        out = duel_rules.exchange_full(duel, boss, arg, c.config.duel, c.config.battle, self.rng,
                                       c.config.tactics, self._bout_rng("頭目戰", duel.boss, duel.round))
        line = tactics.round_line(
            f"第 {duel.round + 1} 回合：你{out.mine or '出不了手'}，{foe.name}{out.his or '出不了手'}——{duel_rules.COUNTER_WORDS[out.beat]}。"
            f"（氣勢 {out.delta:+d}，你氣血 {-out.hp:+d}）", out.lines,
        )
        return self._duel_after(line)

    def _duel_after(self, line: str) -> list[str]:
        """出完一招（或放手一搏）之後：記這一回合，分出勝負就收場，否則擲他下一回合的招。"""
        s, c = self.state, self.content
        duel = s.player.duel
        boss, foe = duel_rules.foe_of(c, duel)
        duel.lines.append(line)
        duel.round += 1
        tier = duel_rules.verdict(duel, boss, c.config.duel)
        if tier is not None:
            return self._duel_finish(tier, line)
        duel_rules.roll_next(duel, foe, c.config.duel, self.rng)
        return [line]

    def _duel_finish(self, tier: str | None, line: str) -> list[str]:
        """收場：池子掉的氣血扣回本人（兩成變內傷，根骨減，同遊歷）、照結果發獎勵、一份戰報與一則江湖紀錄。tier 是 None 是抽身退走
        （不寫戰報，沒有獎勵）。"""
        s, c = self.state, self.content
        p, cfg = s.player, c.config.duel
        duel = p.duel
        boss, foe = duel_rules.foe_of(c, duel)
        p.duel = None
        lost = max(0.0, duel.hp_start - duel.hp)
        now, _ = self._player_hp_and_cap()
        if lost > 0:
            con = team.con_of(s, c, self.world, PLAYER)
            injury = treasures.amount(s, c, "injury")  # 螭首（玉璽碎片改版）：變成內傷的減半；沒帶是 1
            p.member.injury += lost * c.config.injury_share * max(0.0, 1 - team.stat_bonus(c, con, s.world)) * injury
            p.member.neili = max(0.0, now - lost)
        title = f"頭目戰・{foe.name}"
        if tier is None:
            msgs = [line] + ([f"氣血 -{round(lost)}"] if round(lost) else [])
            self._write(title, msgs, tag="抽身退走")
            return msgs
        level = duel_rules.foe_difficulty(duel, boss)
        squad = Squad(id=f"duel:{boss.id}", name=f"{foe.title}{foe.name}", difficulty=level, attribute=boss.attribute)
        result = encounter.EncounterResult(tier=tier, margin=duel.edge - cfg.start, our_power=duel.power, difficulty=level)
        record = battlelog.new_record(s, c, self.world, squad, result, "duel", event=title)
        record.ours = record.ours[:1]  # 同伴不上場：比的是你一個人
        record.rounds = list(duel.lines)
        won = tier in team.WIN_TIERS
        record.notes.append(foe.win if won else foe.lose if tier == "落敗" else f"{foe.name}見討不了好，虛晃一招退走了。")
        share = cfg.reward_share.get(tier, 0.0)
        extra: list[str] = []
        more = renown.duel_reward(s, c) if won else 1.0  # 名聲 4.4：名動一方以上打贏，經驗、銀兩、心得多兩成（名望、素材照舊）
        share *= more
        if more > 1.0:
            record.notes.append(renown.duel_paid_line(s, c))
        exp = round(boss.exp * share)
        if exp:  # 同伴不上場：只給本人；升級給屬性點同決戰的軍餉
            before = p.member.level
            # 滿級換心得（先換，升到滿級那一下剩下的不換）：extra 會進戰報敘事、紀錄另接得失（已含換來的那一份），所以只留那一句，
            # 「心得 +N」不接（同切磋；FB-453：以前紀錄寫心得 +39、實際 +27）
            extra += [n for n in self._record_exp(record, exp, "boss") if not n.startswith("心得 +")]
            extra += team.add_exp(c, p.member, exp, p.name, "boss")  # 頭目戰是仗（減法季 45 級以後照算）
            if p.member.level > before:
                points = team.level_points(self.state, c, before, p.member.level)
                p.stat_points += points
                if points:
                    extra.append(f"你有 {p.stat_points} 點屬性可以分配（點名號展開）。")
        silver = round(boss.silver * share)
        if silver:
            p.stats["silver"] = p.stats.get("silver", 0) + silver
            record.silver = silver
        xinde = round(boss.xinde * share)
        if xinde:
            p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
            record.xinde = (record.xinde or 0) + xinde  # 滿級換來的那一份已經在裡面（_record_exp，FB-450）
        if won:
            for material_id in boss.drops:
                if materials.grant(s, c, material_id) is not None:
                    materials.add_cell(record.materials, c, material_id)  # 同一種合成一格（FB-140）
            if boss.fame:
                record.changes += renown.gain(s, c, "fame", boss.fame)  # 名聲設計 3.2
            chance = cfg.legend_chance.get(tier, 0.0)
            if chance > 0 and self.rng.random() < chance:
                p.legend_items += 1
                record.changes.append(f"{c.config.legend_item_name} +1")
                extra.append(f"他身上掉出一枚【{c.config.legend_item_name}】——{c.config.legend_item_note}")
        if round(lost):
            record.changes.append(f"氣血 -{round(lost)}")
        record.notes += extra
        summary = self._file_battle(record)
        msgs = [line, summary, *record.notes, *battlelog.gains_list(record)]
        self._write(title, msgs, tag=battlelog.outcome_text(record))
        annals.note(s, c, annals.FIGHT, f"獨力對上{foe.title}{foe.name}，{tier}。", 3 if won else 2)
        return msgs

    # ── 擂台（tianxia/arena.py；Joy 2026-10-14 選「隨時挑擂」：報名留分身，別人隨時來挑，照積分排名，只算本季）──

    def _arena_side(self) -> ArenaSide:
        """此刻的身手（同頭目戰的快照：威力、不算騎兵與部下的份量、職位）；池子從滿的開始。"""
        _, cap = self._player_hp_and_cap()
        return ArenaSide(
            name=self.state.player.name, power=self._battle_power(), scores=self._battle_scores(mounted=False),
            role=self._battle_role(), hp=cap, hp_cap=cap, bare=self._arena_bare(),
        )

    def _arena_bare(self) -> float | None:
        """戴著玉璽碎片（改版開著，treasures.power_scale 不是 1）時，不含碎片戰力的威力；沒有是 None（威力本身就是給別人看的那一份）。
        擂台挑人的「身手」與四種戰報的「對手威力」照它寫（FB-625、FB-615）；打起來照 power（含碎片）。"""
        if treasures.power_scale(self.state, self.content) == 1.0:
            return None
        return self._battle_power(seal=False)

    def _arena_arts(self) -> list[str]:
        s, c, m = self.state, self.content, self.state.player.member
        arts = (team.player_art(s, c, self.world, m.wugong_id), team.player_art(s, c, self.world, m.neigong_id))
        return [a.name for a in arts if a is not None]

    def arena_board(self) -> list[dict]:
        """擂台榜（見聞「榜單」分頁的一張；arena.board）：照名次前 board_size 名，帶稱號。擂台關著是空的。"""
        return arena.board(self.state.world, self.content.config.arena) if arena.on(self.content) else []

    def arena_power(self) -> float:
        """此刻上擂台的威力（假人照它決定報名、更新分身；bot_policy._arena）。"""
        return self._battle_power()

    def arena_left(self) -> int:
        """今天還能挑幾次擂（ArenaTuning.per_day；同回體丹的現實時間換日）。"""
        return arena.left_today(self.state, self.content.config.arena, self._pill_day())

    def _arena_entry(self) -> list[Option]:
        """「擂台」那一顆：哪裡都有（地點上、路上、閉關中），只是打開第二層選單，不花體力。"""
        return [Option(id="act:arena", label=arena.ARENA)] if arena.here(self.state, self.content) else []

    def _arena_options(self) -> list[Option]:
        """擂台的第二層選單：報名（報過了是更新分身）、排在你前面 reach 名內的人一人一顆（挑不了的灰掉寫為什麼）、返回。都不花體力，
        挑擂一天 per_day 次。"""
        s, c, p = self.state, self.content, self.state.player
        cfg = c.config.arena
        mine = arena.entry_of(s.world, p.name)
        power = self._battle_power()
        shown = self._battle_power(seal=False)  # 身手兩邊都照不含玉璽碎片的算（FB-625）：自己看自己也一樣，畫面才跟別人看到的對得上
        left = self.arena_left()
        opts = [Option(id=arena.JOIN_ID, label=arena.UPDATE if mine is not None else arena.JOIN, enabled=power > 0)]
        others = arena.challengers(s.world, c, p.name, left)
        for e, problem in others:
            note = problem or arena.LEFT.format(n=left)
            title = arena.title_for(e.rank)
            label = (f"挑{e.name}（第 {e.rank} 名{'・' + title if title else ''}・{arena.record_text(e)}・"
                     f"身手{arena.strength_words(c, shown, e.shown)}・{note}）")
            opts.append(Option(id=f"arena:fight:{name_key(e.name)}", label=label, enabled=problem is None))
        if mine is not None and not others:
            opts.append(Option(id="arena:none", label=arena.NOBODY if mine.rank == 1 else arena.NOBODY_AHEAD, enabled=False))
        opts.append(Option(id=arena.BACK_ID, label=arena.BACK))
        return opts

    def _arena(self, arg: str) -> list[str]:
        """擂台第二層的選擇：報名或更新分身、挑一個人（開打）、返回（收起選單）。"""
        verb, _, rest = arg.partition(":")
        if verb == "back":
            self.state.player.picking_arena = False
            self.state.player.arena_last = None
            return ["你離開了擂台。"]
        if verb == "join":
            return self._arena_join()
        if verb == "fight":
            return self._arena_start(rest)
        return ["（此刻無法這麼做。）"]

    def _arena_join(self) -> list[str]:
        s, p = self.state, self.state.player
        side = self._arena_side()
        if side.power <= 0:
            return [arena.NO_ARTS]
        arts = self._arena_arts()
        text = "、".join(arts)
        entry = arena.entry_of(s.world, p.name)
        famed = renown.arena_famed(s, self.content)  # 名聲 4.7
        if entry is not None:
            entry.name, entry.power, entry.scores, entry.role, entry.hp_cap, entry.arts, entry.famed = (
                p.name, side.power, side.scores, side.role, side.hp_cap, arts, famed)
            entry.bare = side.bare  # 碎片沒了再更新分身：不含碎片的那一份跟著清掉
            entry.kit = team.self_side(s, self.content, self.world)
            entry.crowd = arena_crowd.snapshot(s, self.content, self.world)  # 場邊事件看的底細（照更新這一刻）
            return [arena.UPDATED.format(arts=text)]
        entry = arena.join(s.world, ArenaEntry(
            name=p.name, power=side.power, bare=side.bare, scores=side.scores, role=side.role, hp_cap=side.hp_cap, arts=arts, joined=s.world.time,
            kit=team.self_side(s, self.content, self.world), famed=famed, crowd=arena_crowd.snapshot(s, self.content, self.world),
        ))
        return [arena.JOINED.format(rank=entry.rank, arts=text)]

    def _arena_start(self, key: str) -> list[str]:
        """挑一個守擂的人：記今天挑了幾次、冷卻與他今天被挑了幾場，快照兩邊，擲分身第一回合的招。不花體力。"""
        s, c, p = self.state, self.content, self.state.player
        cfg = c.config.arena
        foe = s.world.arena.get(key)
        if foe is None or name_key(foe.name) == name_key(p.name):
            return ["（此刻無法這麼做。）"]
        problem = arena.challenge_problem(s.world, p.name, foe, cfg, self.arena_left(), c.config.time_scale)
        if problem is not None:
            return [f"（{problem}。）"]
        arena.spend(s, self._pill_day())
        arena.note_challenge(s.world, p.name, foe)
        p.newbie_marks.add("arena")  # 新手目標：上一次擂台
        s.world.arena_seq += 1
        fight = ArenaFight(
            id=s.world.arena_seq, foe_key=key, me=self._arena_side(), rounds=cfg.rounds,
            foe=ArenaSide(name=foe.name, power=foe.power, scores=dict(foe.scores), role=foe.role, hp=foe.hp_cap, hp_cap=foe.hp_cap,
                          bare=foe.bare),
            edge=c.config.duel.start,
            crowd_me=arena_crowd.snapshot(s, c, self.world), crowd_foe=foe.crowd,  # 場邊事件看的底細（arena_crowd）
        )
        p.arena_crowd_note = None
        arena.roll_next(fight, arena.rng_for(p.season_number, p.name, fight, "招"), cfg, c.config.duel)
        p.arena = fight
        p.picking_arena = False
        p.arena_last = None
        lines = [arena.OPENING.format(foe=foe.name)]
        if foe.arts:
            lines.append(arena.FOE_ARTS.format(arts="、".join(foe.arts)))
        fight.bout = tactics.open_bout(  # 本命戰法（第二批）：兩邊身上的兩門（他的是報名那一刻的）
            team.self_side(s, c, self.world), foe.kit, "你", foe.name, a_faction=p.faction, pvp=True,
        )
        return lines

    def _arena_scene(self) -> str:
        fight = self.state.player.arena
        lines = [
            f"**{arena.ARENA}・{fight.foe.name}的分身**（第 {fight.round + 1}／{fight.rounds} 回合）",
            arena.OPENING.format(foe=fight.foe.name) if fight.round == 0 else "\n\n".join(self._arena_last_round()),
            f"氣勢：{duel_rules.edge_words(fight.edge)}（{fight.edge:.0f}／100）　"
            f"你的氣血：{fight.me.hp:.0f}／{fight.me.hp_cap:.0f}　他：{fight.foe.hp:.0f}／{fight.foe.hp_cap:.0f}",
            *self._bout_lines(fight.bout),
            f"{fight.tell}{tactics.SEEN_NOTE if tactics.locks(fight.bout).sees else arena.TELL_NOTE}",
            arena.HOWTO,
        ]
        return "\n\n".join(lines)

    def _arena_last_round(self) -> list[str]:
        """上一回合那一行，後面跟著那一回合的場邊事件（有的話）。"""
        lines = self.state.player.arena.lines
        if len(lines) >= 2 and lines[-1].startswith(arena_crowd.PREFIX):
            return lines[-2:]
        return lines[-1:]

    def _arena_crowd(self, label: str = "", move: str = "", his: str = "") -> str | None:
        """這一回合有沒有場邊事件（tianxia/arena_crowd.py）：一場最多一件，擲中了套效果、記這一種今天落在誰身上，回那一行（〔場邊〕…）。
        模型叫得到時（伺服器）記一張單子，伺服器在鎖外重寫那一句（Game.apply_arena_crowd）。亂數另開用途「場邊」，不碰 Game.rng。"""
        s, c, p = self.state, self.content, self.state.player
        fight = p.arena
        if fight is None or not arena_crowd.on(c):
            return None
        cfg = c.config.arena.crowd
        today = self._pill_day()
        foe = s.world.arena.get(fight.foe_key)
        rng = arena.rng_for(p.season_number, p.name, fight, "場邊")
        happening = arena_crowd.roll(fight, s.world, p.name, cfg, today, p.arena_crowd_seen,
                                     foe.crowd_seen if foe is not None else {}, rng, label)
        if happening is None:
            return None
        applied = arena_crowd.apply(fight, happening, cfg)
        if happening.side == "me":
            p.arena_crowd_seen[happening.kind] = today
        elif foe is not None:
            foe.crowd_seen[happening.kind] = today
            self._save_season()  # 守的人那一本帳在這一季的 WorldState
        name, rival = arena_crowd.names(fight, p.name, happening.side)
        text = arena_crowd.fixed_text(c, happening, name, rival, rng)
        line = arena_crowd.line_of(text, applied)
        p.arena_crowd_note = CrowdNote(
            fight_id=fight.id, round=fight.round, kind=happening.kind, side=happening.side, name=name, rival=rival,
            helper=happening.helper, title=happening.title, battle=happening.battle, move=move, his=his, fixed=line, text=text,
        ) if self.client is not None else None
        return line

    def arena_crowd_request(self) -> CrowdNote | None:
        """還等著模型重寫的那一句場邊事件（server 鎖外寫；A 段，只讀）。"""
        return self.state.player.arena_crowd_note

    def apply_arena_crowd(self, note: CrowdNote, text: str) -> bool:
        """C 段：還是同一張單子才換。句子那一截換成模型寫的（括號的數字照舊），擂台這一場、收場卡、戰報、江湖紀錄裡的那一行都換；
        寫不出來（空字串）就收掉單子、照固定句。換了是 True。"""
        p = self.state.player
        if p.arena_crowd_note is None or p.arena_crowd_note != note:
            return False
        p.arena_crowd_note = None
        if not text:
            return False
        new = note.fixed.replace(note.text, text, 1)

        def swap(lines: list[str]) -> None:
            for i, line in enumerate(lines):
                if line == note.fixed:
                    lines[i] = new

        if p.arena is not None and p.arena.id == note.fight_id:
            swap(p.arena.lines)
        if p.arena_last is not None and p.arena_last.id == note.fight_id:
            swap(p.arena_last.lines)
        for record in self.state.battles[-3:]:
            if record.kind == "arena":
                swap(record.rounds)
        for entry in self.state.journal[-5:]:
            swap(entry.lines)
        return True

    def _arena_act(self, arg: str) -> list[str]:
        """擂台上的一招，或認輸。"""
        s, c, p = self.state, self.content, self.state.player
        fight = p.arena
        if fight is None:
            return ["（此刻無法這麼做。）"]
        if arg == "yield":
            return self._arena_finish("落敗", arena.YIELDED)
        if arg not in MOVES:
            return ["（此刻無法這麼做。）"]
        if arg in tactics.locks(fight.bout).no_moves:
            return [tactics.NO_MOVE.format(move=arg)]
        out = arena.exchange_full(fight, arg, c, arena.rng_for(p.season_number, p.name, fight, "交手"),
                                  arena.rng_for(p.season_number, p.name, fight, "戰法"))
        line = tactics.round_line(
            f"第 {fight.round + 1} 回合：你{out.mine or '出不了手'}，他{out.his or '出不了手'}——{duel_rules.COUNTER_WORDS[out.beat]}。"
            f"（氣勢 {out.delta:+d}，你氣血 {-out.mine_hp:+d}，他氣血 {-out.foe_hp:+d}）", out.lines,
        )
        return self._arena_after(line, self._arena_crowd(move=out.mine or "", his=out.his or ""))

    def _arena_gamble(
        self, text: str, rate: int | None, stories: tuple[str, str] | None, request: DuelTextRequest | None, crowd: str = "",
    ) -> list[str]:
        """擂台的放手一搏（C 段）：同一場、同一回合、同一句才用鎖外評好的分，對不上就在鎖內重評（同頭目戰）。"""
        s, c, p = self.state, self.content, self.state.player
        fight = p.arena
        if request is not None and (request.boss, request.round, request.text) != (f"arena:{fight.id}", fight.round, text):
            rate, stories, crowd = None, None, ""
        if rate is None:
            verdict = battle_instance.assess_gamble(
                self._quick_client(), arena.scene(fight), self._duel_side(), text, p.name,
                setting=arena.SETTING, place=arena.PLACE, target=arena.foe_line(fight.me, fight.foe, c), sex=gender.of(s),
            )
            rate, stories = verdict.rate, (verdict.win, verdict.lose)
        s.battle_card = None
        p.guide_done = []
        fired: list[str] = []
        won, delta, hp, _ = arena.gamble(fight, int(rate), c, arena.rng_for(p.season_number, p.name, fight, "搏"),
                                         arena.rng_for(p.season_number, p.name, fight, "戰法"), fired)
        story = (stories or ("", ""))[0 if won else 1]
        moment = battle_instance.GambleMoment(name=p.name, faction=self._duel_side(), text=text, story=story, rate=int(rate), won=won)
        old = (battle_instance.GambleMoment(name=p.name, faction="", text=fight.best_text, rate=fight.best_rate, won=fight.best_won)
               if fight.best_set else None)
        if battle_instance.more_dramatic(moment, old):
            fight.best_text, fight.best_story, fight.best_rate, fight.best_won, fight.best_set = text, story, int(rate), won, True
        if not story:
            story = f"你放手一搏：「{text}」——{'成了！' if won else '沒成，反倒露了破綻。'}"
        line = tactics.round_line(f"第 {fight.round + 1} 回合：{story}（氣勢 {delta:+d}，你氣血 {-hp:+d}）", fired)
        return self._arena_after(line, self._arena_crowd(label=crowd, move=text))

    def _arena_after(self, line: str, crowd: str | None = None) -> list[str]:
        """出完一招（或放手一搏）之後：記這一回合（與這一回合的場邊事件），分出勝負就收場，否則擲分身下一回合的招。"""
        s, c, p = self.state, self.content, self.state.player
        fight = p.arena
        fight.lines.append(line)
        if crowd:
            fight.lines.append(crowd)
        fight.round += 1
        tier = arena.verdict(fight, c.config.duel)
        if tier is not None:
            msgs = self._arena_finish(tier, line)
            return msgs[:1] + [crowd] + msgs[1:] if crowd else msgs
        arena.roll_next(fight, arena.rng_for(p.season_number, p.name, fight, "招"), c.config.arena, c.config.duel)
        return [line, crowd] if crowd else [line]

    def _arena_finish(self, tier: str, line: str) -> list[str]:
        """收場：兩邊的積分與戰績、留給守的人一筆（他下次同步補戰報）、挑的人的戰報與一則江湖紀錄、天下大事（爆冷、連勝、最精彩的一搏）。
        不扣氣血、不磨兵器防具（池子是快照）。"""
        s, c, p = self.state, self.content, self.state.player
        cfg, w = c.config.arena, s.world
        fight = p.arena
        p.arena = None
        mine, foe = arena.entry_of(w, p.name), w.arena.get(fight.foe_key)
        score = arena.SCORES[tier]
        squad = Squad(id=f"arena:{fight.foe_key}", name=f"{fight.foe.name}的分身", difficulty=fight.foe.power)
        result = encounter.EncounterResult(tier=tier, margin=fight.edge - c.config.duel.start, our_power=fight.me.power,
                                           difficulty=fight.foe.shown)  # 戰報的「對手威力」不含玉璽碎片（FB-615）；打是照 power 打的
        title = f"{arena.ARENA}・{fight.foe.name}"
        record = battlelog.new_record(s, c, self.world, squad, result, "arena", event=title)
        record.ours = record.ours[:1]
        record.rounds = list(fight.lines)
        news: list[str] = []
        if mine is not None and foe is not None:
            before_me, before_foe = mine.rank, foe.rank
            was_first = foe.rank == 1
            moved = score >= 1 and arena.swap(mine, foe)
            arena.note_result(mine, score)
            arena.note_result(foe, 1 - score)
            record.changes.append(arena.SWAPPED.format(before=before_me, after=mine.rank) if moved else arena.KEPT.format(rank=mine.rank))
            foe.inbox.append(ArenaReport(
                challenger=p.name, tier=arena.defender_tier(tier, fight.edge, c.config.duel), time=w.time,
                rank=foe.rank, before=before_foe, power=fight.me.power, bare=fight.me.bare,
            ))
            if moved and was_first:
                news.append(arena.NEW_FIRST.format(winner=p.name, loser=foe.name))
            for who in (mine, foe):
                if who.streak and who.streak % cfg.streak_news == 0 and (who is mine) == (score >= 1):
                    news.append(arena.STREAK.format(name=who.name, n=who.streak))
        if fight.best_set and fight.best_won and fight.best_rate <= cfg.highlight_rate:
            news.append(arena.HIGHLIGHT.format(name=p.name, text=fight.best_text))
            record.changes += renown.gain(s, c, "fame", cfg.highlight_fame)  # 名聲設計 3.2
        for text in news:
            add_rumor(s, text, content=c, layer="world")
        summary = self._file_battle(record, wear=False, armor_wear=False)
        msgs = [line, summary, *battlelog.gains_list(record)]
        self._write(title, msgs, tag=battlelog.outcome_text(record))
        # 收場之後回到擂台那一頁（擂台獨立一頁，Joy 2026-10-14「擂台應該要是獨立的一頁」）：收場卡照 arena_last 畫
        p.arena_last = ArenaResult(id=fight.id, foe=fight.foe.name, tier=tier, lines=list(fight.lines), changes=list(record.changes))
        p.picking_arena = arena.here(s, c)
        won = tier in team.WIN_TIERS
        annals.note(s, c, annals.FIGHT, f"上擂台挑{fight.foe.name}，{tier}。", 2 if won else 1, keep=[fight.foe.name])
        self._save_season()  # 名次、戰績、留給守的人那一筆都在這一季的 WorldState
        return msgs

    def _deliver_arena(self) -> None:
        """同步時補擂台的事：季收了還沒打完的那一場作廢；換日記俸（arena.roll_day）；被挑了的每一場一份戰報與一則「守擂・挑的人」；
        領俸；休季時季末前三名的獎勵。"""
        s, c, p = self.state, self.content, self.state.player
        w, cfg = s.world, c.config.arena
        if p.arena is not None and w.ended:
            p.arena = None
            self._write(arena.ARENA, [arena.UNSETTLED])
        rolled = arena.on(c) and arena.roll_day(w, cfg, self._pill_day())  # 擂台關著不動 WorldState（同步什麼都沒有時不存季）
        entry = arena.entry_of(w, p.name)
        if entry is not None and not w.ended and entry.famed != renown.arena_famed(s, c):  # 名聲 4.7：照此刻的名望段重寫
            entry.famed = not entry.famed
            rolled = True
        if entry is None or not (entry.inbox or entry.wages or (w.ended and entry.place and not entry.prized)):
            if rolled:
                self._save_season()
            return
        for report in entry.inbox:
            squad = Squad(id=f"arena:{name_key(report.challenger)}", name=report.challenger, difficulty=report.power)
            result = encounter.EncounterResult(tier=report.tier, margin=0.0, our_power=entry.power, difficulty=report.shown)  # 不含碎片（FB-615）
            title = f"守擂・{report.challenger}"
            record = battlelog.new_record(s, c, self.world, squad, result, "arena", event=title)
            record.time = report.time
            record.ours = record.ours[:1]
            record.notes.append(arena.DEFENDED.format(name=report.challenger))
            record.changes.append(arena.SWAPPED.format(before=report.before, after=report.rank) if report.rank != report.before
                                  else arena.KEPT.format(rank=report.rank))
            battlelog.add_record(s, record)
            self._write(title, [arena.DEFENDED.format(name=report.challenger), battlelog.summary_line(record),
                                *battlelog.gains_list(record)], tag=battlelog.outcome_text(record))
        entry.inbox = []
        for _, rank in entry.wages:
            if not 1 <= rank <= len(cfg.wages):
                continue
            silver, fame = cfg.wages[rank - 1]
            p.stats["silver"] = p.stats.get("silver", 0) + silver
            renown.gain(s, c, "fame", fame)  # 名聲設計 3.2；俸那一句自己寫了名望
            self._write(arena.ARENA, [arena.WAGE.format(rank=rank, title=arena.title_for(rank) or "", silver=silver, fame=fame)])
        entry.wages = []
        if w.ended and entry.place and not entry.prized:
            entry.prized = True
            fame = cfg.prizes[entry.place - 1]
            renown.gain(s, c, "fame", fame)  # 名聲設計 3.2；季末那一句自己寫了名望
            lines = [arena.PRIZE.format(place=entry.place, fame=fame)]
            if cfg.prize_treasure:
                lines += treasures.arena_prize(s, c, p.season_number, entry.place)
            self._write(arena.ARENA, lines)
        self._save_season()

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

    @_not_while_preparing
    def release_companion(self, companion_id: str) -> list[str]:
        """放他回江湖（歷史武將同行第四節【PM】）：修練頁名冊上那一顆（網頁先問一次）。全服放掉 owner、拿出出戰隊伍、
        江湖紀錄一則；情誼、他的進度都不動。開關關著、不是你名下的只回一句話。"""
        c, cid = self.content, str(companion_id)
        if not roster.on(c) or cid not in c.characters or not roster.owns(roster.owned_by(self.world, cid), self.state.player.name):
            return self._log([roster.RELEASE_NOT_YOURS])
        self.world.release_companion(cid)
        team.remove_from_team(self.state, cid)
        name = c.characters[cid].name
        msgs = [roster.RELEASE_DONE.format(name=name)]
        self._write(roster.RELEASE_TITLE.format(name=name), msgs)
        return self._log(msgs)

    def release_view(self, companion_id: str | None) -> dict | None:
        """修練頁人物卡的「放他回江湖」：開關開著、這個人在你名下才有（問句照 roster.RELEASE_CONFIRM），否則 None。"""
        c = self.content
        if not roster.on(c) or companion_id not in c.characters:
            return None
        if not roster.owns(roster.owned_by(self.world, companion_id), self.state.player.name):
            return None
        return {"confirm": roster.RELEASE_CONFIRM.format(name=c.characters[companion_id].name)}

    @_not_while_preparing
    def chuangong(self, key: str, what: str) -> list[str]:
        """傳功門下（Config.chuangong）：用心得替名冊上的同伴或部下練武學、加屬性（chuangong.teach）。
        傳成了寫進江湖紀錄（併進「修練」那一則）；傳不了只回那一句話，不寫紀錄。"""
        xinde = self._xinde()
        msgs = self._log(chuangong.teach(self.state, self.content, self.world, str(key), str(what)))
        if self._xinde() == xinde:  # 沒花到心得：被拒絕了
            return msgs
        return msgs + self._menxia_entry(msgs[0], xinde)

    def chuangong_lessons(self, key: str | None) -> list[dict]:
        """修練頁人物卡底下的傳功鈕（server.menxia_view 的 lessons）：每一項的 what、鈕上的字、效果、按不下去的原因。"""
        return [
            {"what": row.what, "label": row.label, "effect": row.effect, "problem": row.problem}
            for row in chuangong.lessons(self.state, self.content, self.world, key)
        ]

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
            gen_word=skillview.gen_word(art, self.content, self.world),
        )

    def member_card(self, key: str) -> str:
        return skillview.member_card(self.state, self.content, self.world, key)

    def roster_cards(self) -> list[dict]:
        return skillview.roster_cards(self.state, self.content, self.world)

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

    def gear_rows(self) -> dict:
        """修練頁「裝備」那一塊的資料（skillview.gear_rows；裝備四欄設計 2.5）。"""
        return skillview.gear_rows(self.state, self.content, self.world)

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

    def big_battle_ids(self) -> set[int]:
        """戰報列表裡決戰、奪璽單挑那幾場（battlelog.BIG_KINDS）：另外排在最上面一組，不跟一般的仗混在一起（Joy 2026-10-14）。"""
        return {r.id for r in self.state.battles if r.kind in battlelog.BIG_KINDS}

    def battle_detail(self, record_id: int | None = None) -> str:
        s = self.state
        record = battlelog.find(s, record_id) or (s.battles[0] if s.battles else None)
        if record is not None and record.battle_ref is not None:  # 決戰：照 battles 表重讀完整戰況（收場之後才補上的放手一搏劇情也在）
            battle = self.world.ended_battle(record.battle_ref)
            me = battle.participants.get(s.player.name) if battle is not None else None
            definition = self.content.battles.get(battle.battle_id) if battle is not None else None
            if me is not None and definition is not None:
                record = record.model_copy(update={"log": self._round_blocks(battle, definition, last=None, oldest_first=True, me=me)})
        return battlelog.detail_text(record, self.stamp) if record else battlelog.NO_RECORD

    def notice(self, text: str, title: str = "提醒") -> list[str]:
        self._write(title, [text])
        return self._log([text])

    def set_anonymous(self, value: bool) -> None:
        self.state.player.anonymous = bool(value)

    def set_gender(self, value: str) -> list[str]:
        """設定頁的「性別」：還沒選過的角色（舊角色，PM 2026-10-12）改一次，改完就定了；建角色時選過的、選過一次的不能再改。
        不影響任何數值；不寫江湖紀錄（設定頁的事），回一句給網頁跳提示。"""
        p = self.state.player
        if value not in gender.GENDERS:
            return ["沒有這個選項。"]
        if p.gender_chosen:
            return [GENDER_LOCKED]
        p.gender, p.gender_chosen = value, True
        return [GENDER_SET.format(word=value)]

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

    def onboard_view(self) -> dict | None:
        """初入江湖的畫面要亮什麼、發光什麼（prologue.onboard_view）；不在初入江湖是 None。"""
        return prologue_rules.onboard_view(self.state, self.content)

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

    def map_base(self, *, viewer: bool = True) -> dict:
        """輿圖升級的底圖與清單（mapdata.base）：伺服器照 mapdata.base_key 快取。名字旁的兩個字是看的人的（map_mostly，2f）；viewer=False 是跟人無關
        的那一份（名字旁照地點種類的表），伺服器快取這一份、每個人再換上自己的（mapdata.with_mostly）。"""
        return mapdata.base(self.state, self.content, self.map_mostly() if viewer else None)

    def map_state(self) -> dict:
        """輿圖升級的疊層（mapdata.state）：勝算、出陣、分鐘換算由這裡傳進去。只讀，不擲骰。"""
        s, c = self.state, self.content
        faction = self._side()  # 豪強分屬兩軍：照依附那一軍畫出陣與地盤
        on = sortie.on(c) and faction is not None
        duel = self.duel_on()
        judged: dict[str, tuple[str | None, bool]] = {}

        def judge(loc_id: str) -> tuple[str | None, bool]:
            """（出陣那一格是哪一種, 攻被約戰擋下）：同一處只算一次。"""
            if loc_id in judged:
                return judged[loc_id]
            how = sortie.mode(c, s.world, faction, loc_id, bool(self._sortie_foes(c.locations[loc_id]))) if on else None
            # 約戰開著（減法季批 3b）：沒有零風險的守，自家的地方出陣那一格灰著「等對面來約」——輿圖不畫「出陣・守」、不推薦去那裡出陣
            # 攻也一樣（FB-855）：貼不了約戰的敵方地方（跟自家領地不相連、冷卻、戰書凍結、碎片鎮地……）不標「攻」、不推薦——問的跟貼約戰
            # （sortie_go_problem）同一個 conquest.push_problem；截糧的運糧隊正打那裡經過的，出陣照舊攻打運糧隊（_duel_option），照舊是攻
            shut = duel and how == "attack" and not orders.extra_enemies(s, c, loc_id, faction) \
                and conquest.push_problem(s.world, c, self._conquest_side(), loc_id, "attack") is not None
            judged[loc_id] = (None if shut or (duel and how == "hold") else how, shut)
            return judged[loc_id]

        def foes(loc_id: str) -> list[str] | None:
            # 地點卡的對手與勝算照出陣真的會打的那一路（_map_foes）：標攻的地方（FB-858，3d），還有約戰開著、此刻攻不了的敵方與中立區塊
            # （FB-878：不相連、冷卻、戰書凍結——卡上照舊寫攻不了的原因，對手照貼約戰時會迎戰的守軍那一路寫，不再列站在那裡的隊伍）
            how, shut = judge(loc_id)
            return self._map_foes(loc_id) if how == "attack" or shut else None

        out = mapdata.state(
            s, c, odds=self.odds, sortie_mode=lambda loc_id: judge(loc_id)[0], sorties_left=self.sorties_left() if on else None,
            real_minutes=self._real_minutes, sortie_foes=foes, mostly=self.map_mostly(),
            # 截糧的運糧隊正打那裡經過：出陣那一格是「出陣・截糧」、打運糧隊（_duel_option），輿圖卡上的鈕也寫截糧、不掛攻的勝算（FB-9005）
            convoy=(lambda loc_id: bool(orders.extra_enemies(s, c, loc_id, faction))) if duel else None,
        )
        for loc_id, info in out["places"].items():  # 地點卡上那一句這一帶多兇（尋敵分級，Joy 2026-10-22：不寫幾級）；沒有是空字串
            info["fierce"] = self._fierce_line(c.locations[loc_id])
        return out

    def _map_foes(self, loc_id: str) -> list[str] | None:
        """輿圖地點卡的對手與勝算照「出陣真的會打的那一路」列（FB-858，減法季 3d；mapdata.state 的 sortie_foes，在那一處的出陣是攻時問，
        約戰開著、此刻攻不了〔不相連、冷卻、戰書凍結〕的敵方與中立區塊也問，FB-878）：
        領地爭奪開著，約戰關著是出陣擲的那一批（_sortie_foes：conquest.sortie_foes——中立地那裡站的全部、別人的陣營區塊控制方的兵、那裡沒兵時
        退回 Scenario.territory.side_garrison——加上截糧的運糧隊），約戰開著是貼約戰時守軍迎戰挑的那一路（_duel_squad，經驗最高的一路）；
        截糧的運糧隊正打那裡經過的，出陣那一格照舊攻打運糧隊（_duel_entry），就只有運糧隊。領地爭奪關著、散人、不是區塊、沒有對手是 None＝
        照舊列站的隊伍（atlas.foes）。只讀，不擲骰。"""
        s, c = self.state, self.content
        side = self._side()
        if side is None or not sortie.on(c) or not conquest.on(c, s.world) or loc_id not in conquest.blocks(c):
            return None
        if not self.duel_on() or self._conquest_side() is None:
            return self._sortie_foes(c.locations[loc_id]) or None
        extra = orders.extra_enemies(s, c, loc_id, side)
        if extra:
            return extra[:1]
        squad = self._duel_squad(loc_id)
        return None if squad is None else [squad.id]

    def _fierce_line(self, loc: Location) -> str:
        """輿圖地點卡與舊地點詳情的那一句（training.PLACE_LINE）：城外尋敵得到的地方照分級寫「此地宵小出沒。」，城鎮、沒有對手、
        城裡操練關著是空字串。只讀。"""
        tier = None if training.is_town(self.content, loc) else self._practice_tier(loc)
        return "" if tier is None else training.PLACE_LINE.format(tier=training.TIER_WORDS[tier])

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
        text = atlas.detail_text(self.state, self.content, loc_id, lambda squad_id: self.odds(squad_id, at=loc_id))  # 照那一處的地利
        loc = self.content.locations.get(loc_id)
        fierce = self._fierce_line(loc) if loc is not None else ""  # 尋敵分級：一句這一帶多兇（Joy 2026-10-22）
        return f"{text}\n\n{fierce}" if fierce else text

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
        msgs += timetable.quiet_notes(self.world.get_season(), self.content, now)  # 挪不開半夜、照原時間的決戰（企劃者 2026-10-15）
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
        for siege_battle in self._sieges():  # 攻城戰同上（領地爭奪第二批）
            self._shelve_siege(siege_battle)
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
        if self.world.season_phase() == "resting":
            self.state.world = self.world.get_season()
            for siege_battle in self._sieges():  # 攻城戰同上（領地爭奪第二批）：換季前收起來，參戰者補得到交代
                self._shelve_siege(siege_battle)
        if not self.world.next_season(self.content, now):
            return self._log(["（這一季還沒結束，無法開啟下一季。）"])
        self._reconcile_season()
        quiet = timetable.quiet_notes(self.world.get_season(), self.content, now)  # 同開季
        lineup = divine.lineup_note(self.content, self.world.get_season())  # 這一季現世了哪幾件神器（只回給管理者，FB-400）
        if lineup is not None:
            quiet = [*quiet, lineup]
        if divine.exhausted_now(self.world.divine_state(), self.world.get_season_number()):  # 新神器用完了（正式季整合 5.6）：提醒管理者
            quiet = [*quiet, divine.EXHAUSTED]
        return self._log([f"══ 第 {self.world.get_season_number()} 季開始 ══", *quiet] + self._settle_season_start())

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

    def admin_fallen(self) -> list[str]:
        """管理者「叫回人物」的選單：這一季退場、重創的大勢人物（人物表的順序）。"""
        s, c = self.state, self.content
        return [fid for fid in c.figures if figures.is_out(s, fid)]

    def admin_revive_figure(self, fid: str) -> list[str]:
        """叫回人物（PM 2026-10-16，救二十人試玩被打光的官軍）：一位退場、重創的大勢人物現在就以 figure_return_share × 開季聲威
        回到他原本的戰線與所在（同 figures.revive：接位的人交還戰線），天下大事一句；公告不寫管理者。時刻表寫死的也叫得回來。"""
        refusal = self._admin_refusal("叫回人物")
        if refusal:
            return self._log(refusal)
        s, c = self.state, self.content
        if fid not in c.figures or not figures.is_out(s, fid):
            return self._log(["（這位人物此刻沒有退場。）"])
        now = s.world.figures[fid]
        now.back_at, now.back_front = s.world.time, now.back_front or now.front
        msgs = figures.revive(s, c)
        self._write("叫回人物", msgs, tag="管理者")
        self._save_season()
        return self._log(msgs)

    def admin_battles(self) -> list[BattleDef]:
        """管理者「立刻開戰」的選單，照內容的順序（計畫 T8）：
        - 第一季不觸發的 beta 決戰不列；
        - 時刻表決戰只在第一季列（開關關著時 beta 那一季沒有時刻表），而且只列還沒開過、還沒收場的，分版本的只列這一季
          該開的那一版（宛城照第 3 週的結果）——開出來跟時間到了自動開的一樣（見 admin_start_battle）。"""
        w = self.state.world
        off = season_one_off(self.content, w, "battles")
        showdowns = [
            showdown_battle(self.state, self.content, e) for e in timetable.events(w, self.content)
            if season_one(self.content, w) and e.kind == "showdown" and e.id not in w.timeline and e.id not in w.showdowns_opened
            and (e.version_from is None or e.version_from in w.timeline)  # 宛城：第 3 週結算前不知道是哪一版，不列（PM 2026-10-05）
        ]
        openable = {b.id for b in showdowns if b is not None}
        return [b for b in self.content.battles.values()  # 攻城範本（領地爭奪第二批）不列：照時程表開
                if b.id not in off and not b.siege and (b.timetable_event is None or b.id in openable)]

    def admin_fires(self) -> list[Threshold | WorldEvent]:
        """管理者「觸發大事」的選單：大勢門檻與世界事件，第一季不觸發的 beta 門檻與世界事件不列（計畫 T8；玉璽碎片設計 11.2）。"""
        w = self.state.world
        off = season_one_off(self.content, w, "thresholds") | season_one_off(self.content, w, "world_events")
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
        """管理者定結果、清鎖定、開戰、排時間與伏筆鏈的查表入口：照這一季的時刻表（一般季送天命之爭的 id 也是「沒有這件大事」，玉璽二）。"""
        return next((e for e in timetable.events(self.state.world, self.content) if e.id == event_id), None)

    def admin_schedule(self, item: str, at_real: float, now: float) -> list[str]:
        """把三場決戰或季末排在現實時間 at_real：換成世界秒（world.time ＋ (at_real − now) × time_scale）寫進 schedule。
        已經結算或開過集結的不能再排；不能排在過去；三場決戰與季末要照時刻表的順序（嚴格在前一項之後、後一項之前）。"""
        refusal = self._timetable_refusal("排時間")
        if refusal:
            return self._log(refusal)
        s, c = self.state, self.content
        w = s.world
        items = timetable.schedulable(c, w)
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
        if at >= calendar.calendar_end(c, w) and calendar.season_one_on(w, c):
            # FB-439：排到季曆最後一刻之後，季曆時刻停在最後一週週日 23:59，照舊寫會像沒排過去：寫之後多久與現實的日期時刻
            real = at_real + (at - wanted) / c.config.time_scale
            note = moved.lstrip("，、")
            msg = f"已把{event.title}排在{calendar.schedule_text(at, real, c, w)}{f'（{note}）' if note else ''}。"
        else:
            msg = f"已把{event.title}排在{calendar.stamp_text(at, c, w)}（季曆{moved}）。"
        self._write("排時間", [msg], tag="管理者")
        return self._log([msg])

    def _showdown_mark(self, at: float) -> tuple[float, str | None]:
        """排定的決戰時間對齊到下一個曆時交界（季的事只在交界把時間到了的決戰記下來，T10 審查 I1）；那一刻剛好有還沒結算的
        一般大事時再往後挪一個曆時——不然同一刻那件大事先結算，排在它前面、還沒開成的決戰會照起點判掉（settle_waiting_showdowns）。"""
        s, c = self.state, self.content
        mark = calendar.hour_ceil(at, c, s.world)  # 季曆的整點（FB-331：21 天季開季不在整點時，世界秒的整點對不到季曆）
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
        mark = calendar.hour_ceil(target, c, w)  # 季曆的整點（FB-331）
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

    def admin_conquest_set(self, loc_id: str, side: str | None) -> list[str]:
        """領地爭奪（第 38 項改版）：管理者把一塊改成某一軍的（side None 或空字串＝放回中立）。第一批沒有攻城戰，地圖只能靠這裡與時刻表
        指定易手動；易手的天下大事、江湖史、三條線的重算跟自然易手一樣（conquest.set_control）。只收搶得下來的區塊、官軍或黃巾。"""
        refusal = self._admin_refusal("定一塊歸誰")
        if refusal:
            return self._log(refusal)
        c, w = self.content, self.state.world
        if not conquest.on(c, w):
            return self._log(["（這一季沒有開領地爭奪。）"])
        side = side or None
        if not conquest.capturable(c, loc_id):
            return self._log(["（這裡不是搶得下來的區塊：大本營、廣宗、不是區塊的地點都不收。）"])
        if side is not None and side not in conquest.SIDES:
            return self._log(["（只能定給官軍或黃巾。）"])
        before = territory.controller(w, c, loc_id)
        if before == side:
            return self._log(["（這一塊本來就是這樣。）"])
        conquest.set_control(w, c, loc_id, side)
        msgs = check_thresholds(self.state, c, self.world, self._quick_client(), now=self.now)
        name = c.locations[loc_id].name
        line = f"{name}改歸{c.scenario.faction_name(side, side)}。" if side else f"{name}放回中立。"  # 管理者看的，不是天下大事
        self._write("定一塊歸誰", [line] + msgs, tag="管理者")
        self._save_season()
        return self._log([line] + msgs)

    def admin_conquest_progress(self, loc_id: str, side: str, value: float) -> list[str]:
        """領地爭奪（救場，QA 用；翻地與爭搶）：直接把 side 在這一塊的那一條定成 value（0～100）；到 100 照推滿當場易手（分紅給這一輪推過的人、
        冷卻起算）。不看推不推得動、不記誰推的。只收搶得下來的區塊、劇本的陣營、而且不是此刻佔著的那一方。"""
        refusal = self._admin_refusal("定一塊的進度")
        if refusal:
            return self._log(refusal)
        c, w = self.content, self.state.world
        if not conquest.on(c, w) or w.conquest is None or w.ended:
            return self._log([f"（{CONQUEST_OFF}）"])
        if not conquest.capturable(c, loc_id):
            return self._log(["（這裡不是搶得下來的區塊：大本營、廣宗、不是區塊的地點都不收。）"])
        if c.scenario.find_faction(side) is None or conquest.holder(w, c, loc_id) == side:
            return self._log(["（只能替不是此刻佔著的那一方定進度。）"])
        value = max(0.0, min(conquest.FULL, float(value)))
        fight = conquest._fight(w, c, loc_id)
        line = fight.bars.setdefault(side, conquest.Bar())
        line.value = value
        fight.last_push = w.time
        name = c.locations[loc_id].name
        msgs = [f"{name}：{c.scenario.faction_name(side, side)}的進度定成 {round(value)}。"]  # 管理者看的
        if value >= conquest.FULL:
            msgs += conquest.flip(w, c, loc_id, side)
            msgs += check_thresholds(self.state, c, self.world, self._quick_client(), now=self.now)
        elif value <= 0:
            fight.bars.pop(side, None)
        self._write("定一塊的進度", msgs, tag="管理者")
        self._save_season()
        return self._log(msgs)

    def admin_conquest_letter(self, loc_id: str, side: str) -> list[str]:
        """領地爭奪（救場，QA 用）：替 side 立刻對這一塊下一張戰書——不看階、門檻、一天一張，開打在「此刻＋集結」、集結馬上開（QA 不必等到下午）。
        同一塊別一邊下了、還沒開集結就併進那一場。天下大事照戰書寫、不寫管理者；不算進那一邊今天的那一張。"""
        refusal = self._admin_refusal("立刻下戰書")
        if refusal:
            return self._log(refusal)
        c, w = self.content, self.state.world
        if not conquest.on(c, w) or w.conquest is None or w.ended:
            return self._log([f"（{CONQUEST_OFF}）"])
        if side not in conquest.SIDES or not conquest.capturable(c, loc_id) or conquest.holder(w, c, loc_id) == side:
            return self._log(["（只能替官軍或黃巾、對不是自己的、搶得下來的區塊下。）"])
        found = conquest.frozen(w, loc_id)
        if found is not None and (found.status == "open" or side in found.attackers):
            return self._log(["（這一塊已經有一場攻城了。）"])
        text = conquest_day.place_now(w, c, side, loc_id, self.pill_now())
        self._write("立刻下戰書", [text], tag="管理者")
        self._save_season()
        return self._log([text])

    def admin_conquest_cancel(self, slot_id: str) -> list[str]:
        """領地爭奪（救場）：取消一場攻城（照作罷處理：那一塊解凍、進度照留、天下大事一句，公告不寫管理者）；已經開了集結的那一場照決戰的
        取消收兵（不算勝負、不發軍餉、不易手）。"""
        refusal = self._admin_refusal("取消一場攻城")
        if refusal:
            return self._log(refusal)
        c, w = self.content, self.state.world
        if not conquest.on(c, w) or w.conquest is None:
            return self._log([f"（{CONQUEST_OFF}）"])
        slot = next((s for s in w.conquest.schedule if s.id == slot_id), None)
        if slot is None or slot.status in ("done", "void"):
            return self._log(["（找不到這一場，或已經打完、作罷了。）"])
        text = conquest_day.VOID_CANCEL.format(who=conquest_day._names(c, slot.attackers), place=c.locations[slot.loc].name)
        if slot.status == "open" and slot.record_id is not None:
            self._cancel_siege(slot.record_id, text)
            w = self.state.world
            slot = next(s for s in w.conquest.schedule if s.id == slot_id)
        conquest_day.void(w, c, slot, text)
        self._write("取消一場攻城", [text], tag="管理者")
        self._save_season()
        return self._log([text])

    def admin_conquest_choices(self) -> dict | None:
        """設定頁管理者工具「領地爭奪」那一組的下拉選單（server.admin_choices 的 conquest；打開領地爭奪，PM 2026-10-22）：只在領地爭奪開著、
        季還沒收的季有，其餘 None（網頁不畫）。blocks 是搶得下來的區塊（字寫此刻歸誰、每一條進度、冷卻、被戰書凍結），sides 是交戰兩軍
        （admin_conquest_set／progress／letter 只收這兩軍），sieges 是時程表上還沒打完、沒作罷的攻城（admin_conquest_cancel 的 id）。
        只給管理者看；字待 joy 潤。"""
        c, w = self.content, self.state.world
        if not conquest.on(c, w) or w.ended or w.conquest is None:
            return None
        names = {f.id: f.name for f in c.scenario.factions}
        blocks = []
        for loc in conquest.blocks(c):
            if not conquest.capturable(c, loc):
                continue
            held = conquest.holder(w, c, loc)
            bits = [names.get(held, held) if held else "沒人佔"]
            bits += [f"{names.get(s, s)} {conquest._int(v)}" for s, v in sorted(conquest.bars(w, loc).items(), key=lambda kv: (-kv[1], kv[0]))]
            if conquest.cooling(w, c, loc):
                bits.append(f"冷卻 {conquest.cooling_minutes(w, c, loc)} 分")
            if conquest.frozen(w, loc) is not None:
                bits.append("戰書凍結")
            name = c.locations[loc].name  # 問句寫地名（label 後面的括號不能拿來切：潁川郡（陽翟）自己就有括號）
            blocks.append({"id": loc, "name": name, "label": f"{name}（{'・'.join(bits)}）"})
        sides = [{"id": s, "label": names.get(s, s)} for s in conquest.SIDES]
        sieges = [{
            "id": slot.id,
            "label": f"{c.locations[slot.loc].name}：{'、'.join(names.get(a, a) for a in slot.attackers)}攻・{siege_status_text(c, slot)}・{self.stamp(slot.at)}",
        } for slot in w.conquest.schedule if slot.status not in ("done", "void")]
        return {"blocks": blocks, "sides": sides, "sieges": sieges}

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
        mandate = seal.mandate_event(c)
        if mandate is not None and event.id == mandate.id:  # 管理者替天命之爭定結果：也定天命（8.3）
            battle = seal.mandate_battle(c)
            self._mandate_settle(key.split(":")[0], None, battle.name if battle is not None else event.title)
            self.state.world = self.world.get_season()
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
        event_id = definition.timetable_event if definition else None
        w = self.state.world
        if event_id and event_id in w.showdowns_opened and event_id not in w.timeline and event_id not in w.showdowns_cancelled:
            w.showdowns_cancelled.append(event_id)  # 取消的時刻表決戰：輿圖不列（FB-563；之後「定結果」了才照有結果的寫法列）
        add_rumor(self.state, line, content=self.content, layer="world")
        self._save_season()
        self._write("取消決戰", [line], tag="管理者")
        return self._log([line])

    # ── 管理者：每週的事（管理者觸發鈕第 1 組，企劃者 2026-10-07）────────────
    # 「效果跟自然發生一樣」：每一顆都叫週一掛鉤（world.WEEK_HOOKS）用的同一個函式，不另寫一份。

    # ── 管理者：玉璽碎片（玉璽碎片設計第十二節；公告不寫管理者，效果跟自然發生一樣）──────────

    def admin_seal_emerge(self, shard_id: str = "") -> list[str]:
        """下一場標 emerge 的時刻表決戰必定現世（略過 35%）；可以指定哪一片（還沒現世的），空的照亂數挑。給誰照 3.3 從勝方抽。"""
        refusal = self._admin_refusal("強制現世")
        if refusal:
            return self._log(refusal)
        if shard_id and shard_id not in self.content.seal:
            return self._log(["（沒有這一片。）"])
        if seal.on(self.content) and seal.conquest_season(self.content, self.state.world):  # 領地爭奪的季沒有宛城現世：改成現在藏一片
            return self._admin_seal_hide(shard_id)
        self.world.mutate(lambda st: setattr(seal.filled(st.seal, self.content), "force_emerge", shard_id or "*"))
        self._write("強制現世", ["下一場標了現世的決戰，碎片必定現世。"], tag="管理者")
        return self._log(["（下一場標了現世的決戰，碎片必定現世。）"])

    def _admin_seal_hide(self, shard_id: str) -> list[str]:
        """領地爭奪的季「強制現世」的替身（領地爭奪設計 3.9）：現在就藏一片（略過 hide_chance，可以指定哪一片），藏在哪一塊照開季的藏法
        （權重、亂數同自然擲中）；回話與紀錄都不寫藏在哪裡。這一季已經藏著、已經現世過一片、沒有可藏的都不藏。"""
        c = self.content
        out: list[str] = []

        def _apply(shared) -> None:
            reg = seal.filled(shared.seal, c)
            season = shared.season_number
            if seal.mandate_now(reg, season):
                out.append(seal.HIDE_MANDATE)
            elif reg.emerge_season == season:
                out.append(seal.HIDE_EMERGED)
            elif seal.live_cache(reg, season) is not None:
                out.append(seal.HIDE_HAS)
            else:
                spots = seal.hide_spots(c, shared.season)
                cache = seal.hide(reg, c, season, shared.tianji, spots, force=True, shard=shard_id or None)
                if cache is None:
                    out.append(seal.HIDE_NO_SPOT if not spots else seal.HIDE_NONE)
                else:
                    reg.cache = cache
                    out.append(seal.HIDE_DONE)

        self.world.mutate(_apply)
        self._write("現在藏一片", out, tag="管理者")
        return self._log([f"（{line}）" for line in out])

    def admin_seal_stir(self, shard_id: str) -> list[str]:
        """下一場標了 seal 的決戰必定牽動這一片（略過 7%、新主保護與次數上限；那一片要有主）。"""
        refusal = self._admin_refusal("強制璽動")
        if refusal:
            return self._log(refusal)
        shard = self.world.seal_state().registry.shards.get(shard_id)
        if shard is None or shard.state != "held":
            return self._log(["（這一片現在沒有主人，牽動不了。）"])
        self.world.mutate(lambda st: setattr(st.seal, "force_stir", shard_id))
        self._write("強制璽動", [f"下一場標了璽動的決戰，必定牽動『{self.content.seal[shard_id].name}』。"], tag="管理者")
        return self._log(["（下一場標了璽動的決戰，必定牽動這一片。）"])

    def admin_seal_assign(self, shard_id: str, name: str, state: str = "held") -> list[str]:
        """把一片直接記到某個名號名下（held，一人一片照擋、這一季有新主保護），或收回成未現世（hidden）、改成隱沒（sunk）。
        只改登記，不讀、不存他的存檔（「這一季上線過」看 seen_real，管理者工具碰不到它）；抄本與紀錄等他同步時補（登記記一筆 assign）。"""
        refusal = self._admin_refusal("指定持有者")
        if refusal:
            return self._log(refusal)
        if shard_id not in self.content.seal or state not in ("held", "hidden", "sunk") or (state == "held" and not name.strip()):
            return self._log(["（看不懂要怎麼改。）"])
        out: list[str] = []

        def _apply(shared) -> None:
            reg = seal.filled(shared.seal, self.content)
            shard = reg.shards[shard_id]
            if state == "held":
                other = seal.shard_of(reg, name)
                if other is not None and other.id != shard_id:
                    out.append(f"（{name}手上已經有『{self.content.seal[other.id].name}』了：一人一片。）")
                    return
            before = shard.holder
            shard.state, shard.holder = state, (name.strip() if state == "held" else None)
            shard.since_season = shared.season_number if state == "held" else shard.since_season
            if state == "held":
                shard.emerged_round = shard.emerged_round or reg.round
            seal.log(reg, shared.season_number, "assign", shard=shard_id, holder=shard.holder, other=before)
            out.append(f"（『{self.content.seal[shard_id].name}』改成{seal.BOOK_STATES[state].format(holder=shard.holder or '')}。）")

        self.world.mutate(_apply)
        self._write("指定持有者", out, tag="管理者")
        return self._log(out)

    def admin_seal_duel(self, shard_id: str, challenger: str, factor: float, now: float) -> list[str]:
        """立刻對這一片開一場奪璽單挑，指定挑戰者，局勢係數可選（預設 1.0，上限照舊 25%）。正式伺服器只能掛在最近一場剛收場、
        還沒開過單挑的時刻表決戰上（SealRegistry.last_showdown，公告照那一場寫）；Config.seal.qa_tools 開著時不必有決戰。
        雙方的快照照 5.3「沒參戰」那一列（_seal_side_of）；挑戰者也要過一人一片。"""
        refusal = self._admin_refusal("強制開單挑")
        if refusal:
            return self._log(refusal)
        c, cfg = self.content, self.content.config.seal
        view = self.world.seal_state()
        reg = seal.filled(view.registry, c)
        shard = reg.shards.get(shard_id)
        if shard is None or shard.state != "held" or not challenger.strip() or seal.key(challenger) in seal.holders(reg):
            return self._log(["（這一片沒有主人，或挑戰者手上已經有碎片。）"])
        hung = reg.last_showdown is not None and not reg.last_showdown_dueled
        if not hung and not cfg.qa_tools:
            return self._log(["（正式伺服器的奪璽單挑只能掛在剛收場的時刻表決戰上；那一場不在、或已經開過單挑。）"])
        if view.duels:
            return self._log(["（已經有一場奪璽單挑在打。）"])
        self.now = now
        cap = min(cfg.cap, cfg.cap * max(0.0, min(1.0, factor)))
        duel_id = f"{reg.last_showdown}:{shard_id}" if hung else f"qa{reg.seq + 1}:{shard_id}"
        duel = seal_duel.open_duel(
            duel_id, shard_id, reg.last_showdown if hung else None, None, reg.last_showdown_where if hung else "", "旁觀", cap,
            self._seal_side_of(challenger), self._seal_side_of(shard.holder), now, cfg,
        )
        line = (seal_duel.CALL if hung else seal_duel.CALL_QA).format(
            challenger=duel.challenger.name, holder=duel.holder.name, shard=c.seal[shard_id].name)

        def _apply(shared) -> None:
            shared.seal_duels.append(duel)
            seal.filled(shared.seal, c).last_showdown_dueled = True
            seal.rumor(shared.season, line)

        self.world.mutate(_apply)
        self._write("強制開單挑", [line], tag="管理者")
        return self._log([line])

    def admin_seal_fix(self, take: bool) -> list[str]:
        """正在打的那一場，指定再擲中或不中（QA 用，同時刻表的「定結果」）；公告照常。"""
        refusal = self._admin_refusal("定單挑的結果")
        if refusal:
            return self._log(refusal)
        if not self.world.seal_state().duels:
            return self._log(["（沒有奪璽單挑在打。）"])
        self.world.mutate(lambda st: setattr(st.seal_duels[0], "fixed", bool(take)))
        return self._log([f"（這一場收場時{'易主' if take else '懷璽不失'}。）"])

    def admin_seal_cancel(self) -> list[str]:
        """取消正在打（或下戰書中）的那一場：記成未分勝負，碎片留在原主；只寫天下大事。"""
        refusal = self._admin_refusal("取消單挑")
        if refusal:
            return self._log(refusal)
        if not self.world.seal_state().duels:
            return self._log(["（沒有奪璽單挑在打。）"])
        out: list[str] = []
        self.world.mutate(lambda st: out.append(seal_duel.finish(st, st.seal_duels[0], self.content, None, self.now).text))
        self._deliver_seal_results()
        self._write("取消單挑", out, tag="管理者")
        return self._log(out)

    def admin_seal_sink_check(self, now: float) -> list[str]:
        """照 7.6 的條件現在判一次（下一次換季會沉哪幾片），只印結果、不改。只要是管理者就能按：休季（換季之前）、暫停中照樣看得到（FB-178）。"""
        if not self.is_admin():
            return self._log(["（只有管理者能隱沒判斷。）"])
        reg = seal.filled(self.world.seal_state().registry.model_copy(deep=True), self.content)
        store = CharacterStore(self.world.db) if hasattr(self.world, "db") else None
        seen = {}
        for s in reg.shards.values():
            if s.state == "held" and s.holder:
                state = store.load(s.holder) if store is not None else None
                seen[s.holder] = None if state is None else (state.player.seen_real if state.player.seen_real is not None else state.last_real)
        sunk = seal.sink(reg, self.world.get_season_number(), seen, now, self.content.config.seal)
        lines = [f"（下一次換季會隱沒：{seal.SINK.format(holder=name, shard=self.content.seal[s.id].name)}）" for s, name in sunk]
        return self._log(lines or ["（下一次換季沒有碎片會隱沒。）"])

    def admin_seal_mandate(self, when: str) -> list[str]:
        """蓋天命之季（第十二節；玉璽二）：when 是 "next"（下一季蓋章，不看七片現世過沒）、"cancel"（收回「下一季」：只清延後的記號，
        七片這一輪都現世過的話換季照樣蓋；審查 I2）或 "now"（這一季立刻蓋：還沒打的標了 seal 的決戰照天命之季的規則璽動，天命之爭排在
        預設時刻——已經過了就馬上到期——也可以用「立刻開戰」）。「下一季」與收回只要是管理者就按得了（休季正是要決定下一季的時候，同
        FB-178）；「這一季」要季在跑。公告照自然發生寫、不寫管理者。"""
        refusal = self._admin_refusal("蓋天命之季") if when == "now" else None if self.is_admin() else ["（只有管理者能蓋天命之季。）"]
        if refusal:
            return self._log(refusal)
        c = self.content
        event = seal.mandate_event(c)
        if not seal.on(c) or event is None or seal.mandate_battle(c) is None:
            return self._log(["（這個劇本沒有天命之爭。）"])
        season = self.state.world  # 每個動作開頭的 sync 剛讀過（不用 get_season：它會把整季的傳聞與江湖史讀回來）
        if season.mandate:
            return self._log(["（這一季已經是天命之季；收季之後七片散去。）"])
        if when == "next":
            self.world.mutate(lambda st: setattr(seal.filled(st.seal, c), "mandate_pending", True))
            msg = "下一季蓋天命之季的章。"
        elif when == "cancel":
            if not seal.filled(self.world.seal_state().registry, c).mandate_pending:
                return self._log(["（下一季沒有要蓋天命之季的章。）"])
            self.world.mutate(lambda st: setattr(seal.filled(st.seal, c), "mandate_pending", False))
            msg = "收回下一季的天命之季章（七片這一輪都現世過的話，換季時照樣會蓋）。"
        elif when == "now":
            if season.ended or not season_one(c, season):
                return self._log(["（這一季沒有時刻表，蓋不了天命之季。）"])
            def _stamp(st) -> None:
                seal.stamp_mandate(st, c, timetable.default_time(event, c, st.season))
                timetable.avoid_quiet_hours(st.season, c, self.now)  # 天命之爭照季曆排的時刻挪開半夜（企劃者 2026-10-15）

            self.world.mutate(_stamp)
            self.state.world = self.world.get_season()
            msg = "這一季蓋上天命之季的章。"
            # 挪不開半夜、照原時間的決戰：同開季、開啟下一季那一行（FB-265）
            kept = timetable.quiet_notes(self.state.world, c, self.now)
            self._write("蓋天命之季", [msg, *kept], tag="管理者")
            return self._log([f"（{msg}）", *kept])
        else:
            return self._log(["（看不懂要怎麼蓋。）"])
        self._write("蓋天命之季", [msg], tag="管理者")
        return self._log([f"（{msg}）"])

    def admin_seal_choices(self) -> dict | None:
        """設定頁「玉璽」一組要的：七片與狀態、有沒有單挑在打、剛收場的決戰還能不能掛單挑、qa_tools、天命之季蓋了沒（mandate：
        "now" 這一季、"next" 下一季、"" 沒有）與劇本有沒有天命之爭（mandate_ok，玉璽二）。碎片關著是 None。"""
        c = self.content
        if not seal.on(c):
            return None
        view = self.world.seal_state()
        reg = seal.filled(view.registry, c)
        out = {
            "shards": [{"id": s, "name": c.seal[s].name, "state": reg.shards[s].state, "holder": reg.shards[s].holder or ""} for s in c.seal],
            "duel": bool(view.duels), "hung": reg.last_showdown is not None and not reg.last_showdown_dueled,
            "where": reg.last_showdown_where, "qa": c.config.seal.qa_tools,
            "mandate": "now" if seal.mandate_now(reg, view.season) else "next" if reg.mandate_pending else "",  # 兩個章一起蓋，讀登記那一份（不必 get_season）
            "mandate_ok": seal.mandate_event(c) is not None and seal.mandate_battle(c) is not None,
            # 領地爭奪的季「強制現世」是「現在藏一片」（網頁換鈕上的字）；只給有沒有，不給藏在哪
            "hide": seal.conquest_season(c, self.state.world),
        }
        if seal_acts.on(c):  # 獨門行動（改版第 2 批）：這一季誰起用了哪一片、什麼時候、指定了什麼（救場用，設計【PM】5）；改版關著不多這一鍵
            out["uses"] = [
                {"shard": c.seal[e.shard].name if e.shard in c.seal else e.shard, "who": e.holder,
                 "act": seal_acts.NAMES.get(e.act, e.act), "when": self.stamp(e.at) if e.at is not None else "",
                 "what": e.what}
                for e in reg.uses if e.season == view.season  # FB-695：起用另記在 uses（舊資料讀進來時從 history 搬過來）
            ]
        return out

    def admin_issue_orders(self) -> list[str]:
        """立刻發本週軍令：這一週還沒達成的軍令換成照週一的做法（orders.issue，週一掛鉤用的同一個函式，redraw）此刻重新挑的一批，
        各陣營照常發「本週軍令：…」的陣營軍情。換掉的那幾道進度不算了；已經達成的原封不動、不會再達成一次（審查 I-1：重挑的 id
        是決定性的，不留著的話同一道會達成兩次、效果套兩次）。不動 hooked_week：下週一照常發令。"""
        refusal = self._admin_refusal(f"發{calendar.week_word('order_this', self.content, self.state.world)}軍令")
        if refusal:
            return self._log(refusal)
        s, c = self.state, self.content
        if not orders.active(s, c):
            return self._log(["（這一季沒有軍令。）"])
        week = orders.period_of(s, c)  # 21 天季是季曆第幾天（每天一期）
        daily = orders.daily(s, c)
        replaced = sum(1 for o in s.world.orders if o.week == week and not o.done)
        kept = {o.id for o in s.world.orders if o.week == week and o.done}
        if daily:
            orders.issue_day(s, c, week, self.rng, redraw=True)
        else:
            orders.issue(s, c, week, self.rng, redraw=True)
        self._save_season()
        issued = [o for o in s.world.orders if o.week == week and o.id not in kept]
        listing = "；".join(
            f"{f.name}：{'、'.join(orders.title(c, o) for o in issued if o.faction == f.id)}"
            for f in c.scenario.factions if any(o.faction == f.id for o in issued)
        ) or ADMIN_REISSUE_NONE[daily]
        label = f"第 {week} 天" if daily else f"第 {week} 週"
        msg = (f"已照{ADMIN_REISSUE_HOW[daily]}的做法重發{label}的軍令，換掉沒達成的 {replaced} 道（進度不算了；已達成的 {len(kept)} 道照舊）"
               f"——{listing}。")
        self._write("重發軍令", [msg], tag="管理者")
        return self._log([msg])

    def admin_rotate_seats(self) -> list[str]:
        """立刻輪替第 4 階席次：照上一週的貢獻重排各陣營在任的人、發一則名單軍情（seats.rotate，週一掛鉤用的同一個函式）。
        不動 hooked_week：下週一照常再排。賽季時鐘暫停中不排（_admin_refusal；自然的路暫停時也不補缺、不輪替）；
        第 1 週沒有上一週可排（seats.rotate 自己也什麼都不做），說一聲。"""
        refusal = self._admin_refusal("輪替第 4 階席次")
        if refusal:
            return self._log(refusal)
        s, c = self.state, self.content
        if not season_one(c, s.world):
            return self._log(["（這一季沒有第 4 階席次。）"])
        week = calendar.point(s.world.time, c, s.world).week
        segments = calendar.week7_on(s.world, c)  # 7 天濃縮季照段寫（FB-503，待 joy 潤）
        if week < 2:
            return self._log([ADMIN_ROTATE_FIRST[segments]])
        seats.rotate(s, c, week)
        self._save_season()
        held = s.world.seats
        listing = "；".join(
            f"{f.name}{ranks.TITLES[f.id][seats.SEAT_RANK]}：{'、'.join(held.get(f.id, [])) or '沒有人'}"
            for f in c.scenario.factions if f.id in s.world.seat_ledger and f.id in ranks.TITLES
        ) or "帳上還沒有人有第 4 階的資格"
        last = segments and week >= len(c.config.season_segments)
        again = ADMIN_ROTATE_LAST if last else ADMIN_ROTATE_AGAIN[segments]
        msg = f"已照{calendar.week_label(week - 1, c, s.world)}的貢獻輪替第 4 階席次（{again}）——{listing}。"
        self._write("輪替席次", [msg], tag="管理者")
        return self._log([msg])

    # ── 管理者：三場大戲（管理者觸發鈕第 3 組）──────────────────────
    # 「立刻開戰」（admin_start_battle）早就照時刻表開時刻表決戰（world.open_showdown：照版本挑那一筆、照前線戰況定起點、
    # 在 WorldState.showdowns_opened 記下開過了，時間到了不再開）。這裡只是每一場一顆鈕、照時刻表的大事認，按不下去時說清楚為什麼。

    def admin_showdowns(self) -> list[tuple[TimetableEvent, str | None]]:
        """三場大戲那三顆鈕：時刻表上的每一件決戰，與此刻按下去會被拒絕的原因（開得了是 None）。這一季沒有時刻表時是空的。"""
        if not season_one(self.content, self.state.world):
            return []
        return [(e, self._showdown_refusal(e)) for e in timetable.events(self.state.world, self.content) if e.kind == "showdown"]

    def _showdown_refusal(self, event: TimetableEvent) -> str | None:
        """這一件決戰此刻開不開得了：已經結算、已經開過（時刻表那一份記號，開過就不再開）、要看別的大事定版本而那件還沒結算
        （宛城，PM 2026-10-05）、另一場還在集結或開打，都開不了。"""
        w = self.state.world
        if event.id in w.timeline:
            return f"（{event.title}已經結算了。）"
        if event.id in self.cancelled_showdowns():  # FB-099：開過、被取消、還沒有結果——照舊開不了，說清楚怎麼收尾
            return f"（{event.title}開打後被取消，還沒有結果；要收尾請用「定結果」。）"
        if event.id in w.showdowns_opened:
            return f"（{event.title}已經開打過了。）"
        if event.version_from is not None and event.version_from not in w.timeline:
            source = self._timetable_event(event.version_from)
            return f"（{event.title}要等{source.title if source else event.version_from}結算了才知道是哪一版。）"
        battle = self.world.get_battle()
        if battle is not None and battle.phase != "ended":
            return "（已經有一場戰鬥在進行。）"
        if showdown_battle(self.state, self.content, event) is None:
            return f"（內容裡沒有{event.title}這一場的戰鬥。）"
        return None

    def cancelled_showdowns(self) -> set[str]:
        """開打後被取消、時間軸上還沒有結果的時刻表決戰（FB-099；管理者工具的三場大戲與時刻表那兩列照它寫）：開過集結
        （showdowns_opened，記號照舊留著、不會再開），時間軸上沒有它，此刻也不是在打的那一場（取消決戰把它從共用狀態拿掉了）。
        真的打完的時間軸上有結果，不算；還在集結、開打或剛收場的那一場是此刻的那一場，也不算。"""
        w = self.state.world
        battle = self.world.get_battle()
        live = battle.battle_id if battle is not None else None
        return {eid for eid, battle_id in w.showdowns_opened.items() if eid not in w.timeline and battle_id != live}

    def admin_start_showdown(self, event_id: str, now: float) -> list[str]:
        """立刻開時刻表上這一場決戰：照時刻表開（admin_start_battle → world.open_showdown，跟時間到了一樣：同一個函式、同一句集結
        號角），開過就記在 showdowns_opened，排定的時間到了不再開。版本照此刻的規則（宛城看第 3 週的結果）。"""
        refusal = self._timetable_refusal("開這一場決戰")
        if refusal:
            return self._log(refusal)
        event = self._timetable_event(event_id)
        if event is None or event.kind != "showdown":
            return self._log(["（時刻表上沒有這一場決戰。）"])
        why = self._showdown_refusal(event)
        if why:
            return self._log([why])
        return self.admin_start_battle(showdown_battle(self.state, self.content, event).id, now)

    # ── 玩家之間的互動（social.py，企劃者 2026-10-08）────────────────────
    # 同一個地點的人看得到彼此：場景底下一行「此地還有誰」、點名字打開玩家卡、卡上的動作鈕（social.ACTIONS）。
    # 替對方寫東西（收到的禮、邀請、招呼）在同一把行動鎖裡讀他的存檔、改完存回去；不替他補算時間——補算會把他的
    # last_real 推到此刻，下了線的人就會一直掛在名單上。真人假人一樣對待（伺服器假人設計第五節）。

    def peers_here(self) -> list[dict]:
        """場景底下「此地還有誰」：[{name, side}]，照名號排序。路上、序章裡看不到人（social.here）。"""
        return [{"name": o.player.name, "side": social.side(o, self.content)} for o in social.here(self)]

    def _peer(self, name: str) -> Game | None:
        """此刻在你這裡的那個人那一份 Game（不叫模型、不補算時間，賽季接上你這一份）；不在這裡是 None。"""
        key = name_key(name)
        for state in social.here(self):
            if name_key(state.player.name) == key:
                other = Game(self.content, state, self.rng, self.world)
                other.client = None
                other.state.world = self.state.world
                return other
        return None

    def peer_card(self, name: str) -> dict | None:
        """玩家卡（social.card）；他不在這裡了是 None（網頁照 social.GONE 那一句說）。"""
        other = self._peer(name)
        return None if other is None else social.card(self, other)

    def peer_request(self, name: str, action: str, params: dict | None = None) -> naming.NamingRequest | None:
        """玩家卡上的鈕按下去之前要不要先請模型（social.CardAction.request；論武的首創取名）：三段式的 A 段，只讀。
        對方不在這裡、這一種互動沒有登記或不需要模型，是 None。"""
        handler = social.ACTIONS.get(action)
        other = None if handler is None or handler.request is None else self._peer(name)
        return None if other is None else handler.request(self, other, dict(params or {}))

    def peer_act(self, name: str, action: str, params: dict | None = None) -> list[str]:
        """按了玩家卡上的一顆鈕：對方還在這裡、這一種互動有登記，才交給它做（social.CardAction.run），做完存回對方的存檔。
        按的人的江湖紀錄由各個互動自己寫（拒絕的話只回給按的人，不記）。"""
        self.peer_brief = None
        other = self._peer(name)
        if other is None:
            return self._log([social.GONE])
        handler = social.ACTIONS.get(action)
        if handler is None:
            return self._log(["（沒有這個動作。）"])
        msgs = handler.run(self, other, dict(params or {}))
        CharacterStore(self.world.db).save(other.state)
        self.touched.add(other.state.player.name)  # 他開著的分頁也刷新（server._tell_tabs）
        return self._log(msgs)

    # ── 名帖（Joy 2026-10-19；tianxia/mingtie.py 的說明）與贈物一天的次數 ──

    def _shared_or_none(self):
        """全服的狀態（名帖的檢舉、撤下）：測試用的記憶體世界沒有就是 None（照畫）。"""
        try:
            return self.world.read()
        except (AttributeError, NotImplementedError):
            return None

    def gift_day_left(self) -> int:
        """今天（回體丹的換日）還能送幾次東西（Config.gift_per_day；0＝不限）。"""
        cap, p = self.content.config.gift_per_day, self.state.player
        if cap <= 0:
            return 1
        return max(0, cap - (p.gifts_today if p.gift_day == self._pill_day() else 0))

    def gift_day_tick(self) -> None:
        p, day = self.state.player, self._pill_day()
        p.gifts_today = (p.gifts_today if p.gift_day == day else 0) + 1
        p.gift_day = day

    def mingtie_face(self, state: GameState) -> dict | None:
        """這個人的名帖給你看的樣子：還沒做是 None；被檢舉藏起來、管理者撤下、你檢舉過的只剩頭銜（mingtie.shown）。"""
        card = state.player.mingtie
        if card is None:
            return None
        if mingtie_rules.shown(self._shared_or_none(), state.player.name, card.version, self.state, self.content):
            return mingtie_rules.view(card)
        return mingtie_rules.blank_view(card)

    def mingtie_view(self, board: dict | None = None) -> dict:
        """見聞「名帖匣」：自己那一張、掙到的頭銜、今天還能定稿幾次遞幾張、畫布的規矩、現成的畫、收到的那幾張（新的在前）。
        board 是這一季的榜單（伺服器的 boards_now；頭銜「某某榜第N」照它）。"""
        p, c, cfg = self.state.player, self.content, self.content.config.mingtie
        day, shared = self._pill_day(), self._shared_or_none()
        box = []
        for copy in reversed(p.mingtie_box):
            seen = mingtie_rules.shown(shared, copy.name, copy.card.version, self.state, c)
            box.append({
                "name": copy.name, "when": copy.when, "place": copy.place, "season": copy.season,
                "card": mingtie_rules.view(copy.card) if seen else mingtie_rules.blank_view(copy.card),
            })
        return {
            "mine": mingtie_rules.view(p.mingtie),
            "pool": mingtie_rules.earned(self.state, c, self.world, board),
            "made_left": mingtie_rules.made_left(self.state, c, day),
            "sent_left": mingtie_rules.sent_left(self.state, c, day),
            "limits": {
                "titles": cfg.titles, "motto": cfg.motto_max, "strokes": cfg.max_strokes, "points": cfg.max_points,
                "width": mingtie_rules.WIDTH, "height": mingtie_rules.HEIGHT, "inks": list(mingtie_rules.INKS),
                "ink_names": list(mingtie_rules.INK_NAMES), "pens": list(mingtie_rules.PENS),
            },
            "presets": [{"id": a.id, "name": a.name, "strokes": a.strokes} for a in c.mingtie.arts],
            "box": box,
        }

    def mingtie_screen(self, motto: str) -> str | None:
        """定稿之前要不要先請模型審自題那一句（三段式的 A 段）：字表先擋得下的、空的都不必問，回 None；要問回那一句（已整理過）。"""
        line = speech.clean(motto)
        cfg = self.content.config.mingtie
        if not line or speech.word_problem(line, self.content, speech.MOTTO, cfg.motto_max):
            return None
        return line

    def make_mingtie(self, strokes, titles, motto: str = "", verdict: str = "", board: dict | None = None) -> list[str]:
        """名帖定稿：筆劃照 parse_strokes 驗、頭銜要從掙到的那一串裡挑（最多 MingtieTuning.titles 個）、自題一句過 speech
        （verdict 是 B 段模型的判斷）。不花錢；一天最多定稿 made_per_day 次；定稿一次版本 +1（別人收著的舊版不變）。"""
        p, c, cfg = self.state.player, self.content, self.content.config.mingtie
        if not cfg.enabled:
            return self._log(["（此刻無法這麼做。）"])
        if mingtie_rules.made_left(self.state, c, self._pill_day()) <= 0:
            return self._log([mingtie_rules.MADE_FULL.format(n=cfg.made_per_day)])
        lines = mingtie_rules.parse_strokes(strokes, c)
        if lines is None:
            return self._log([mingtie_rules.BAD_DRAWING])
        picked = [str(t) for t in (titles or [])]
        pool = set(mingtie_rules.earned(self.state, c, self.world, board))
        if len(picked) > cfg.titles or len(set(picked)) != len(picked) or not set(picked) <= pool:
            return self._log([mingtie_rules.BAD_TITLE])
        line = speech.clean(motto)
        problem = speech.problem(line, c, speech.MOTTO, cfg.motto_max, verdict)
        if problem:
            return self._log([problem])
        if not lines and not picked and not line:
            return self._log([mingtie_rules.EMPTY])
        version = (p.mingtie.version if p.mingtie else 0) + 1
        p.mingtie = Mingtie(strokes=lines, titles=picked, motto=line, version=version)
        p.mingtie_made += 1
        self._write("名帖", [mingtie_rules.MADE], merge=True)
        return self._log([mingtie_rules.MADE])

    def mingtie_send_problem(self, other: Game) -> str | None:
        """遞名帖給他按不按得下去：要有自己的名帖、今天還能遞、他手上還沒有你這一版、你們之間沒有一張還在等的名帖。"""
        s, c = self.state, self.content
        me, him = s.player, gender.pronoun(other.state)
        if me.mingtie is None:
            return mingtie_rules.NO_CARD
        if invites.between(s.world, me.name, other.state.player.name, "mingtie") is not None:
            return mingtie_rules.WAITING.format(him=him)
        if mingtie_rules.given(self.state, other.state.player.name) >= me.mingtie.version:
            return mingtie_rules.SAME_CARD.format(him=him)
        if mingtie_rules.sent_left(self.state, c, self._pill_day()) <= 0:
            return mingtie_rules.SENT_FULL.format(n=c.config.mingtie.send_per_day)
        return None

    def mingtie_send(self, other: Game) -> list[str]:
        """遞名帖：一張邀請，他回帖才兩邊各收一張（_mingtie_swap）。不理就等它逾時，不退今天的次數。"""
        problem = self.mingtie_send_problem(other)
        if problem is not None:
            return [problem]
        s, name = self.state, other.state.player.name
        renew = mingtie_rules.given(self.state, name) > 0
        invites.expire(s.world)
        invites.send(s.world, self.content, "mingtie", s.player.name, name, s.player.location)
        s.player.mingtie_sent += 1
        self._save_season()
        self.touched.add(name)
        return [f"你遞上{'新' if renew else ''}名帖，等{name}回帖。"]

    def _mingtie_swap(self, inv, other: Game) -> list[str]:
        """回帖：兩邊各收對方此刻的那一張（存遞出那一刻的樣子），兩邊的江湖紀錄各一則。你得有自己的名帖、他也還有。"""
        me, them, c = self.state.player, other.state.player, self.content
        if me.mingtie is None or them.mingtie is None:
            self._tell_sender(inv, other)
            return [f"（{mingtie_rules.NO_CARD}。）" if me.mingtie is None else "（對方的名帖不在了。）"]
        mingtie_rules.file_copy(self.state, other.state, c, gave=me.mingtie.version)
        mingtie_rules.file_copy(other.state, self.state, c, gave=them.mingtie.version)
        other._write(f"名帖・{me.name}", [f"{me.name}回了帖，你們互換了名帖。"])
        return [f"你回了帖，與{them.name}互換了名帖。"]

    def report_mingtie(self, name: str, version: int) -> list[str]:
        """檢舉一張名帖：你馬上就看不到（mingtie_hidden）；全服記一筆，滿 report_hide 個人藏起來等管理者看。
        要是你看得到的那一張（名帖匣裡收著的、或他此刻就在這裡）。"""
        p, c = self.state.player, self.content
        try:
            version = int(version)
        except (TypeError, ValueError):
            return self._log(["（找不到這張名帖。）"])
        copy = mingtie_rules.copy_of(self.state, name)
        here = self._peer(name)
        card = here.state.player.mingtie if here is not None else None
        if not ((copy and copy.card.version == version) or (card and card.version == version)):
            return self._log(["（找不到這張名帖。）"])
        if name_key(name) == name_key(p.name):
            return self._log(["（這是你自己的名帖。）"])
        k = mingtie_rules.key(name, version)
        if k not in p.mingtie_hidden:
            p.mingtie_hidden.append(k)
        self.world.mutate(lambda shared: mingtie_rules.report(shared, name, version, p.name))
        return self._log([mingtie_rules.REPORTED])

    def admin_mingtie_reports(self) -> list[dict]:
        """管理者「名帖檢舉」：被檢舉、還沒處理的（名號、第幾版、幾個人檢舉、那一張的樣子〔只有此刻還是那一版才看得到畫〕）。"""
        if not self.is_admin():
            return []
        shared = self._shared_or_none()
        if shared is None:
            return []
        rows = []
        for nk, version, count in mingtie_rules.pending_reports(shared, self.content):
            target = self._admin_target(nk, sync=False)
            card = target.state.player.mingtie if target is not None else None
            rows.append({
                "name": target.state.player.name if target is not None else nk, "version": version, "count": count,
                "card": mingtie_rules.view(card) if card is not None and card.version == version else None,
            })
        return rows

    def admin_mingtie_remove(self, name: str, version: int) -> list[str]:
        """撤下一張名帖：那一版以前的都不畫（別人名帖匣裡收著的也是）；他此刻那一張就是這一版的話，畫與自題清掉、頭銜照留、版本 +1，
        他的江湖紀錄一句（不寫是誰撤的）。"""
        refusal = self._admin_refusal("撤下名帖")
        if refusal:
            return self._log(refusal)
        target = self._admin_target(name, sync=False)
        if target is None:
            return self._log([NO_SUCH_PLAYER.format(name=name.strip())])
        version, tp = int(version), target.state.player
        nk = name_key(tp.name)
        self.world.mutate(lambda shared: shared.mingtie_removed.__setitem__(nk, max(shared.mingtie_removed.get(nk, 0), version)))
        if tp.mingtie is not None and tp.mingtie.version <= version:
            tp.mingtie = mingtie_rules.wipe(tp.mingtie.model_copy(update={"version": version}))
            target._write("名帖", [mingtie_rules.REMOVED_LINE])
        self._save_target(target)
        msg = f"已撤下{tp.name}的名帖（第 {version} 版）。"
        self._write("撤下名帖", [msg], tag="管理者")
        return self._log([msg])

    def admin_mingtie_restore(self, name: str, version: int) -> list[str]:
        """放回：檢舉再多也照畫（管理者看過、沒事）。"""
        refusal = self._admin_refusal("放回名帖")
        if refusal:
            return self._log(refusal)
        k = mingtie_rules.key(name, int(version))
        self.world.mutate(lambda shared: None if k in shared.mingtie_cleared else shared.mingtie_cleared.append(k))
        msg = f"已放回{name.strip()}的名帖（第 {int(version)} 版）。"
        self._write("放回名帖", [msg], tag="管理者")
        return self._log([msg])

    # ── 玩家之間的互動・第二層：打招呼與結伴的回應、逾時、結伴同行（social.py 的說明）──

    def _kin(self, state: GameState) -> Game:
        """別人的那一份 Game（不叫模型、不補算他的時間；賽季與「現在」接上你這一份），替他寫東西用。"""
        other = Game(self.content, state, self.rng, self.world)
        other.client = None
        other.state.world = self.state.world
        other.now = self.now
        return other

    def _load_kin(self, name: str) -> Game | None:
        if not hasattr(self.world, "db"):
            return None
        try:
            state = CharacterStore(self.world.db).load(name)
        except ValueError:
            return None
        return None if state is None else self._kin(state)

    def _save_kin(self, other: Game) -> None:
        CharacterStore(self.world.db).save(other.state)

    def calls_here(self) -> list[dict]:
        """場景底下「別人遞給你、還沒回的」打招呼、結伴、切磋邀請（social.calls）。"""
        return social.calls(self)

    def join_refusal(self, leader: str) -> str | None:
        """答應跟 leader 結伴同行，不行的原因：他得還在這裡、兩個人都沒在跟別人、你身後也沒有人跟著你、你人不在路上。"""
        p = self.state.player
        if p.journey is not None:
            return "你在路上"
        if p.tagalong is not None:
            return f"你已經跟著{p.tagalong.leader}了"
        if self._party():
            return "已經有人跟著你走"
        other = self._peer(leader)
        if other is None:
            return social.GONE.rstrip("。")
        if other.state.player.tagalong is not None:
            return f"{leader}已經跟著別人走了"
        return None

    def _party_expires(self) -> None:
        """答應結伴之後，帶頭的人 party_wait_seconds（現實秒）之內沒動身，各走各的。"""
        p = self.state.player
        tag = p.tagalong
        if tag is not None and p.journey is None and tag.since < self.now - self.content.config.party_wait_seconds:
            p.tagalong = None
            self._write(f"結伴同行・{tag.leader}", [f"{tag.leader}遲遲沒有動身，你們各走各的。"])

    def _party(self, catch_up: bool = False) -> list[Game]:
        """跟著你結伴同行、還算數的人（各自那一份 Game）：還在等你動身的（跟你同一個地點、沒過期），或已經跟著你在路上的。
        catch_up：先替他們補算路上的抵達（抵達終點就散了），帶他們出發、改道之前要用。"""
        if not hasattr(self.world, "db"):
            return []
        me = self.state.player
        out = []
        for state in CharacterStore(self.world.db).tagging(me.name):
            other = self._kin(state)
            if catch_up:
                other._arrivals()
            o = other.state.player
            if o.tagalong is None or o.tagalong.leader != me.name:
                if catch_up:
                    self._save_kin(other)
                continue
            # 帶頭的人剛動身（_lead）時 location 還是出發的那一站，所以還在等的人照樣認得出來
            waiting = o.journey is None and o.location == me.location \
                and o.tagalong.since >= self.now - self.content.config.party_wait_seconds
            if waiting or (o.journey is not None and me.journey is not None):
                out.append(other)
            elif catch_up:
                self._save_kin(other)
        return out

    def party_view(self) -> dict | None:
        """場景底下結伴同行的那一行：跟著誰（可以分道揚鑣），或誰跟著你。都沒有是 None。"""
        p = self.state.player
        if p.tagalong is not None:
            return {"lead": False, "names": [p.tagalong.leader], "text": f"你跟著{p.tagalong.leader}結伴同行，由對方定去哪、怎麼走。"}
        names = [g.state.player.name for g in self._party()]
        if not names:
            return None
        when = "一路同行" if p.journey is not None else "你動身時跟著走"
        return {"lead": True, "names": names, "text": f"{'、'.join(names)}與你結伴同行，{when}。"}

    def leave_party(self) -> list[str]:
        """場景底下的「分道揚鑣」（還在等帶頭的人動身時）：見 _part_ways。在路上時走選單的 act:part。"""
        if self.state.player.tagalong is None:
            return self._log(["（你沒有跟著誰。）"])
        leader = self.state.player.tagalong.leader
        msgs = self._part_ways()
        self._write(f"結伴同行・{leader}", msgs)
        return self._log(msgs)

    def _part_ways(self) -> list[str]:
        """不再跟著帶頭的人（他的紀錄記一句）。在路上的話照原本那一趟自己走下去（之後可以自己折返、改道）。"""
        p = self.state.player
        tag, p.tagalong = p.tagalong, None
        if tag is None:
            return []
        leader = self._load_kin(tag.leader)
        if leader is not None:
            leader._write(f"結伴同行・{p.name}", [f"{p.name}與你分道揚鑣。"])
            self._save_kin(leader)
            self.touched.add(tag.leader)
        return [f"你與{tag.leader}分道揚鑣。"]

    def _lead(self, start: str | None, foot: int, told: str) -> list[str]:
        """結伴同行：帶頭的你出發、改道、喊停之後，跟著的人照抄這一趟（同樣的路、同樣的抵達時間，連步調 Journey.pace 一起抄：
        整隊照帶頭的人的坐騎走，_partners 才認得出同行）。趕路、疾行的體力各付各的（裝備四欄 5.8）：foot 是不算坐騎的體力
        （atlas.route_foot_stamina；喊停是 0），每個跟著的人照自己的坐騎再省（atlas.ride_stamina、mounts.saving）。
        start 是你動身的地點（從路上改道、喊停時是 None）。跟不上的人（體力不夠、手上有事、已經不在這裡）就散了，兩邊各記一句。
        回傳寫給你的幾句。told 是寫進跟著的人紀錄的那一句。"""
        me = self.state.player
        j = me.journey
        lines: list[str] = []
        for other in self._party(catch_up=True):
            o = other.state.player
            cost = atlas.ride_stamina(foot, mounts.saving(other.state, self.content))  # 這個人自己騎的馬省下之後要付的
            # 路是帶頭的人認得的路，跟著的人不必自己認得（所以不問 travel_refusal），只看他手上有沒有事、體力夠不夠
            block = atlas.travel_block(other.state, self.content)
            if start is not None and (o.journey is not None or o.location != start):
                problem = social.GONE.rstrip("。")
            elif start is not None and block is not None:
                problem = block.reason
            else:
                problem = None if o.stamina >= cost else f"體力不足，要 {cost} 體力"
            if problem is not None:
                o.tagalong = None
                other._write(f"結伴同行・{me.name}", [f"{me.name}{told.split('，')[0]}，你沒能跟上（{problem}）。"])
                lines.append(f"{o.name}沒能跟上，你們就此分開。")
            else:
                o.stamina -= cost
                o.journey = j.model_copy(deep=True)
                o.leg_actions = o.leg_actions | me.leg_actions
                other._write(f"結伴同行・{me.name}", [told] + ([f"體力 -{cost}"] if cost else []))
                if j.mode == "dash":
                    other._arrivals()
                lines.append(f"{o.name}跟著你。")
            self._save_kin(other)
            self.touched.add(o.name)
        return lines

    def _partners(self) -> list[Game]:
        """同一趟路上結伴的其他人（帶頭的與其他跟著的；路上小事的收穫分給他們）：補算過抵達，跟你走在同一段路上的。"""
        p, j = self.state.player, self.state.player.journey
        if j is None or not hasattr(self.world, "db"):
            return []
        leader = p.tagalong.leader if p.tagalong is not None else p.name
        states = CharacterStore(self.world.db).tagging(leader)
        if leader != p.name:
            head = CharacterStore(self.world.db).load(leader)
            states = ([head] if head is not None else []) + states
        out = []
        for state in states:
            if name_key(state.player.name) == name_key(p.name):
                continue
            other = self._kin(state)
            other._arrivals()
            oj = other.state.player.journey
            if oj is not None and oj.path == j.path and oj.reached == j.reached and oj.arrive_at == j.arrive_at:
                out.append(other)
            else:
                self._save_kin(other)
        return out

    def _share_road(self, what: str, gain: tuple | None) -> list[str]:
        """路上小事的收穫分給同行的人（企劃者：每一樣收穫兩個人都有）：這一段路上這件事也算他做過了。
        有收穫上限的（心得、素材）照他自己這個遊戲日的上限給。回傳寫給你的幾句。"""
        lines: list[str] = []
        me = self.state.player.name
        name = ROAD_TASKS[what][0]
        for other in self._partners():
            o = other.state.player
            o.leg_actions.add(what)
            got: list[str] = []
            if gain is not None:
                kind, value = gain
                capped = kind in ("xinde", "material") and not other._road_reward_due("task")
                if capped:
                    got = ["（這陣子的收穫拿滿了。）"]
                elif kind == "xinde":
                    o.stats["xinde"] = o.stats.get("xinde", 0) + value
                    other._count_road_reward("task")
                    got = [f"心得 +{value}"]
                elif kind == "material":
                    got = [materials.grant(other.state, self.content, value)]
                    other._count_road_reward("task")
                elif kind == "rumor":
                    got = [f"聽說：{value}"]
            if got:
                other._write(f"結伴同行・{me}", [f"同行的{me}{name}，你也有一份。", *got])
                lines.append(f"（同行的{o.name}也有一份。）")
                self.touched.add(o.name)
            self._save_kin(other)
        return lines

    # ── 管理者：玩家個人劇情（管理者觸發鈕第 2 組）──────────────────────
    # 輸入一個名號：照角色存檔認人（不分大小寫，同 CharacterStore），在這一把行動鎖裡讀他的存檔、補算到此刻，做完存回去——
    # 跟伺服器替每個人做動作一樣（重讀 → 同步 → 動作 → 存檔）。給他的東西都走自然那條路的同一個函式；他的江湖紀錄記一則，
    # 看起來跟自然發生的一樣（不標管理者，審查 M-1：管理者的動作波及玩家時一向不提管理者，例如取消決戰），管理者自己記一則、
    # 標「管理者」。拒絕的字只有管理者看得到。

    def _admin_target(self, name: str, *, sync: bool = True) -> Game | None:
        """名號對到的那個角色（不分大小寫、不管前後空白）；沒有這個人、或存檔讀不懂，是 None。給自己就是這一份 Game（伺服器在
        動作結束時存的就是它）。別人的：讀存檔、接上同一份共用賽季、不叫模型，sync 為真時補算到此刻（self.now）。"""
        key = name_key(name)
        if not key:
            return None
        if key == name_key(self.state.player.name):
            return self
        try:
            state = CharacterStore(self.world.db).load(name)
        except ValueError:  # 讀不懂的存檔（pydantic 的 ValidationError）：不動它，他自己登入時伺服器會備份重開
            return None
        if state is None:
            return None
        target = Game(self.content, state, self.rng, self.world)
        target.client = None  # 替別人做的事一個模型都不叫
        if sync:
            target.sync(self.now)
        return target

    def _save_target(self, target: Game) -> None:
        """存回他的存檔（給自己的話不必：伺服器動作結束時會存）。他的同步可能存過共用賽季（席次的帳、密謀），管理者這一份跟著重讀。"""
        if target is self:
            return
        CharacterStore(self.world.db).save(target.state)
        self.state.world = self.world.get_season()

    def _summons_plan(self, target: Game) -> tuple[str | None, PromotionDef | None]:
        """「立刻替他發召見」：（拒絕的原因, 要發的那一階）。發的是下一階（rank_of + 1）；不看貢獻門檻、也不看那一階的機緣做了沒
        （控制者裁決：測試要跳過的就是這兩樣）。散人、手上已經有召見、已經取得第 4 階資格、到頂、第 3、4 階第一段此刻沒有人能出面
        （企劃者裁決 E3 那一句的情況），都不發。"""
        s, c, p = target.state, self.content, target.state.player
        if p.faction is None:
            return f"（{p.name}是散人，沒有陣營可以召見{gender.pronoun(p)}。）", None
        if p.summons is not None:
            return f"（{p.name}手上已經有一張第 {p.summons.rank} 階的召見了。）", None
        if p.qualified:
            return f"（{p.name}已經取得第 {ranks.SEAT_RANK} 階的資格了。）", None
        promo = ranks.promotion_for(c, p.faction, ranks.rank_of(s) + 1)
        cap = allied.rank_cap(s, c)  # 豪強分屬兩軍：豪強第 3 階就到頂
        if promo is None or (cap is not None and promo.rank > cap):
            return f"（{p.name}已經升到頂了。）", None
        if promo.legs and ranks.current_cast(s, c, promo, 0, None) is None:
            line = ranks.NO_PRESENTER.get(p.faction, ranks.NO_PRESENTER["guan"])
            return f"（第 {promo.rank} 階此刻沒有人能出面召見{p.name}：{line}）", None
        return None, promo

    def admin_summon(self, name: str) -> list[str]:
        """立刻替他發召見：下一階的召見照 ranks.issue_summons（check_summons 過了門檻之後的同一條：召見地點、出面的人、摸清路、那一句），
        第 3、4 階從第一段起。他的江湖紀錄記一則「召見」（同步時發的召見也是這個標題）。"""
        refusal = self._admin_refusal("發召見")
        if refusal:
            return self._log(refusal)
        if not season_one(self.content, self.state.world):
            return self._log(["（這一季沒有陣營的階級，發不了召見。）"])
        target = self._admin_target(name)
        if target is None:
            return self._log([NO_SUCH_PLAYER.format(name=name.strip())])
        why, promo = self._summons_plan(target)
        lines = [] if promo is None else ranks.issue_summons(target.state, self.content, promo)
        if lines:
            target._write("召見", lines)  # 同步時自然發的召見也是這個標題；不標管理者（審查 M-1）
        self._save_target(target)
        if why is not None:
            return self._log([why])
        msg = f"已替{target.state.player.name}發第 {promo.rank} 階的召見：{lines[0]}"
        self._write("發召見", [msg], tag="管理者")
        return self._log([msg])

    def admin_give_opportunity(self, name: str, opp_id: str) -> list[str]:
        """給他一個機緣：放到這一種機緣自然送上門那一刻之後的樣子（opportunities.offer，每一種用自然那條路的同一個函式；
        集體密謀型沒有那一刻，拒絕）。別的陣營的、完成過的、階不夠的、已經給過的都拒絕。"""
        refusal = self._admin_refusal("給機緣")
        if refusal:
            return self._log(refusal)
        if not opportunities.active(self.state, self.content):
            return self._log(["（這一季沒有機緣。）"])
        o = next((x for x in self.content.opportunities if x.id == opp_id), None)
        if o is None:
            return self._log(["（沒有這個機緣。）"])
        target = self._admin_target(name)
        if target is None:
            return self._log([NO_SUCH_PLAYER.format(name=name.strip())])
        s = target.state
        why = opportunities.offer_refusal(s, self.content, o, self.world)
        if why is None:
            lines, done = opportunities.offer(s, self.content, o, self.world)
            # 聽到的（線索、內鬼的特徵）照自然聽到的樣子，不說是哪一個機緣；其他照機緣的寫法。都不標管理者（審查 M-1）
            heard = o.kind in opportunities.HEARD_KINDS
            target._write(HEARD_TITLE if heard else opportunities.title(s, self.content, f"offer:{o.id}"), lines)
        self._save_target(target)
        if why is not None:
            return self._log([why])
        msg = f"已給{s.player.name}機緣「{o.name}」：{done}。"
        self._write("給機緣", [msg], tag="管理者")
        return self._log([msg])

    def admin_give_fragment(self, name: str, ref: str) -> list[str]:
        """給他一個伏筆片段（ref 是「鏈 id:片段序號」）：照效果給片段的同一條（foreshadow.grant_fragment：記進聽過的片段、
        江湖紀錄那一句「你聽到一件事：…」、不發傳聞）。不是他那一方的、已經聽過的、那條伏筆已經用不上的都拒絕。
        給管理者的那一句不寫片段的原文（天機的答案填在裡面，管理者自己也是玩家），也不提鎖定。"""
        refusal = self._admin_refusal("給伏筆片段")
        if refusal:
            return self._log(refusal)
        c = self.content
        if not foreshadow.active(self.state, c):
            return self._log(["（這一季沒有伏筆。）"])
        chain_id, _, index = ref.rpartition(":")
        chain = foreshadow.chain(c, chain_id)
        if chain is None or not index.isdecimal() or not 0 <= int(index) < len(chain.fragments):
            return self._log(["（沒有這一則伏筆片段。）"])
        i = int(index)
        target = self._admin_target(name)
        if target is None:
            return self._log([NO_SUCH_PLAYER.format(name=name.strip())])
        s = target.state
        why = foreshadow.grant_refusal(s, c, chain, i)
        if why is None:
            target._write(HEARD_TITLE, foreshadow.grant_fragment(s, c, chain.id, i, self.world))  # 不標管理者（審查 M-1）
        self._save_target(target)
        if why is not None:
            return self._log([why])
        event = self._timetable_event(chain.event)
        msg = f"已讓{s.player.name}聽到{event.title if event else chain.event}那條伏筆的第 {i + 1} 則片段。"
        self._write("給伏筆片段", [msg], tag="管理者")
        return self._log([msg])

    def admin_player_choices(self, name: str) -> dict:
        """管理者區「玩家個人劇情」查一個名號：他是誰（陣營・頭銜，在哪裡）、能不能替他發召見（不能的話為什麼）、能給他的機緣與伏筆片段
        （從內容裡挑此刻給得了的：他那一方、他的階、還沒完成也還沒給過）。只讀：不補算、不存檔。查不到回 {"refusal": …}。"""
        if not self.is_admin():
            return {"refusal": "（只有管理者能查玩家。）"}
        target = self._admin_target(name, sync=False)
        if target is None:
            return {"refusal": NO_SUCH_PLAYER.format(name=name.strip())}
        s, c, p = target.state, self.content, target.state.player
        if season_one(c, s.world):
            why, promo = self._summons_plan(target)
        else:
            why, promo = "（這一季沒有陣營的階級，發不了召見。）", None
        parts = [allied.label_of(s, c) if p.faction else "散人"]
        title = ranks.title(c, s) or ranger.title(c, s) or "・".join(renown.titles(s, c))  # 名聲開著時寫兩個稱號
        if title:
            parts.append(title)
        place = c.locations[p.location].name if p.location in c.locations else p.location
        opps = [o for o in c.opportunities if opportunities.offer_refusal(s, c, o, self.world) is None] \
            if opportunities.active(s, c) else []
        frags = [(ch, i) for ch in c.foreshadows.chains for i in range(len(ch.fragments))
                 if foreshadow.grant_refusal(s, c, ch, i) is None] if foreshadow.active(s, c) else []
        return {
            "name": p.name,
            "line": f"{p.name}：{'・'.join(parts)}，在{place}",
            "summons": {"ok": why is None, "note": why or f"會發第 {promo.rank} 階的召見"},
            # note：確認框多問的那一句（情誼型補的是真的情誼，審查 M-5）；其他種類是空字串
            "opportunities": [
                {"id": o.id, "label": opportunities.offer_label(c, o), "note": opportunities.offer_note(s, c, o)} for o in opps
            ],
            "fragments": [{"id": f"{ch.id}:{i}", "label": foreshadow.grant_label(c, ch, i)} for ch, i in frags],
        }

    # ── 畫面文字 ──────────────────────────────────────────

    def location_text(self) -> str:
        loc = self.content.locations[self.state.player.location]
        if jianfa(self.content, self.state.world, "marks_visible"):  # 減法季批 4：痕跡過了門檻，描寫多接一段（marks.describe）
            return f"【{loc.name}】危險 {'★' * loc.danger}\n\n{marks_rules.describe(loc, self.state.world, self.content)}"
        return f"【{loc.name}】危險 {'★' * loc.danger}\n\n{loc.describe(self.state.world.flags)}"  # 宛城的描寫隨版本換

    def scene_art(self) -> dict | None:
        """江湖頁場景卡上面那張圖（減法季批 8 圖像版；減法季整合設計第八章、第一批圖提示單）。回 {kind, path, title, sub, head}：
        path 是 web/img/ 底下不含副檔名的路徑；head 是場景 Markdown 的第一行（地名那一行、事件標題、人名），有圖時網頁把它疊在圖上、
        不在卡片裡寫第二次。事件開著（pending_event）→ 事件的類型圖 events/<Event.image>；跟人物談話 → 他的像（CharacterDef.image）；
        平常站在地點 → Location.image，沒寫就是所屬大區的 places/<大區 id>（atlas.region_of），沒有大區是 places/world。
        其餘的畫面一律 None、一字不變：全服戰鬥蓋著場景、季收了、單挑、擂台、宴席、有所感、投靠與叛投、求見名單、伏筆問話、在路上，
        還有事件沒寫 image、人物沒有像。圖檔在不在是伺服器的事（server.scene_art）。"""
        s, c = self.state, self.content
        p = s.player
        if s.world.ended or self._battle_for_me(tick=False) is not None:
            return None
        if s.pending_event:
            event = c.events[s.pending_event]
            own = storyline.stage_art(s, c)  # 一條線事件段的專屬圖（StoryStage.image）蓋過事件的類型圖
            if not event.image and own is None:
                return None
            path = own or f"events/{event.image}"
            return {"kind": "event", "path": path, "title": event.title, "sub": "", "head": f"**{event.title}**"}
        if p.duel is not None or p.arena is not None or p.feasting is not None or p.sensing is not None:
            return None
        if p.pending_companion:
            character = c.characters[p.pending_companion]
            if not character.image:
                return None
            sub = self.affinity_text(p.pending_companion)
            return {"kind": "figure", "path": character.image, "title": character.name, "sub": sub, "head": f"**{character.name}**（{sub}）"}
        if self._own_scene_text() != self.location_text():  # 投靠、叛投、求見、伏筆問話、在路上……都不是地點的描寫
            return None
        loc = c.locations[p.location]
        if loc.image:
            path = loc.image
        else:
            region = atlas.region_of(c, loc.id)
            path = f"places/{region.id}" if region is not None else "places/world"
        return {"kind": "place", "path": path, "title": loc.name, "sub": f"危險 {'★' * loc.danger}", "head": f"【{loc.name}】危險 {'★' * loc.danger}"}

    def method_help(self, option_ids: Iterable[str]) -> dict | None:
        """有所感選做法那一步，網頁畫在做法鈕底下的兩行小字（explain-2，sensing.method_help；鈕上的心意審查 I1 起預設不給）；
        選單上沒有做法（不在選做法、戰場蓋過了畫面）是 None。不讀這一處悟得到什麼：哪一個做法是對的看不出來。"""
        got = sensing.method_help(self.state, self.content)
        if got is None or not any(sensing.is_method(i) for i in option_ids):
            return None
        return got

    def scene_text(self) -> str:
        """有全服戰鬥時大家都看得到戰場；照常遊玩的人（集結中、只能觀戰、開打了還沒投效的散人，見 _fighting），自己眼前的事
        （事件、對話、地點）接在戰場底下，不然遇到事件時只看得到選項、看不到事件本身。序章裡不畫戰場（_battle_for_me）。"""
        battle_status = self._battle_for_me(tick=False)
        if battle_status is None:
            return self._own_scene_text()
        battle_scene = self._battle_scene_text(*battle_status)
        if self._fighting(*battle_status):
            return battle_scene  # 開打後在場上的人：戰場取代整個畫面；其餘照常遊玩，自己眼前的事接在底下（同 options）
        return f"{battle_scene}\n\n---\n\n{self._own_scene_text()}"

    def _own_scene_text(self) -> str:
        s, c = self.state, self.content
        if s.world.ended:
            if season_one(c, s.world):  # 第一季：結局寫在江湖頁最上面的結算卡（season_result），場景寫所在的地方（FB-046）
                return self.location_text()
            return f"## {s.world.ending_title}\n\n{s.world.ending_text}"
        if s.pending_event:
            event = c.events[s.pending_event]
            return f"**{event.title}**\n\n{fill_marks(self._event_text(event), s)}"
        if s.player.duel is not None:
            return self._duel_scene()
        if s.player.arena is not None:
            return self._arena_scene()
        seat = feast_actions.scene(self)  # 坐在宴席上（宴客包；過渡：場景卡還沒有掛鉤）
        if seat is not None:
            return seat
        sense_card = sensing.scene_text(s, c) if s.player.sensing is not None else ""
        if sense_card:
            return sense_card
        if s.player.god_naming is not None:  # 特殊頓悟心魔過了：取名（同選單的順序）
            return epiphany.scene_text(s, c)
        question = storyline.question_text(s, c) if s.player.story_open is not None else None
        if question:  # 一條線的答題：場景寫這一題（選單上是答案）
            progress = s.player.storylines[s.player.story_open]
            line = storyline.definition(c, progress)
            return f"**{line.title}**\n\n{question}"
        if s.player.pending_companion:
            character = c.characters[s.player.pending_companion]
            history = s.player.dialogue_history.get(s.player.pending_companion, [])
            last = next((m["content"] for m in reversed(history) if m.get("role") == "assistant"), "")
            # 談話時名字旁寫著你們的情誼（explain-1：以前哪裡都看不到這個數）；上回見面談過的事多一行（Joy 2026-10-23）
            return f"**{character.name}**（{self.affinity_text(s.player.pending_companion)}）\n\n{self._last_talk_line(s.player.pending_companion)}{last}"
        if allied.needs_ally(s, c):  # 拜入要依附的門派之後還沒挑一邊（豪強分屬兩軍）
            return f"**依附哪一邊**\n\n{allied.ALLY_AFTER_SECT.format(counts=self.faction_counts_text())}"
        if s.player.pending_faction:
            faction = self.content.scenario.faction(s.player.pending_faction)
            return f"**投靠{faction.name}**\n\n{self._faction_prompt(faction)}"
        if s.player.pending_defect:
            target = self.content.scenario.faction(s.player.pending_defect)
            ally = s.player.pending_ally
            head = defection.slot_label(s, c, target, ally)  # 「叛投X」；豪強分屬兩軍時也可能是「改投X」「改依附X」
            return f"**{head}**\n\n{defection.prompt(s, c, target, self.faction_counts_text(), ally, self._left_names(target.id))}"
        if s.player.picking_audience:
            title = SOCIAL_LIST_TITLE if precise.on(c, s.world) else "求見"
            return f"**{title}**\n\n{self._audience_intro()}"
        asking = foreshadow.asking_text(s, c, self.world) if s.player.fs_asking is not None else None
        if asking is not None:
            return asking
        if s.player.journey is not None:
            # 往哪、幾時抵達只寫在狀態列（status_data 的 journey，每一頁都看得到），場景不再寫一次（FB-046）
            halted = "（已經喊停）" if s.player.journey.stop_at is not None else ""
            tasks = "邊走邊想、沿途打聽、路邊採集"  # 全圖開放拿掉了留意地形（FB-300，同 howto）
            return (
                f"**在路上**{halted}\n\n"
                f"路上可以折返，也可以打開輿圖改去別處，或去修練、煉製；{tasks}，"
                "到下一站之前各能做一次。可以先下線，到了會自己抵達。"
            )
        return self.location_text()

    def feature_status(self) -> dict:
        """功能包合進江湖畫面頂層的資料（FEATURES 的 status，照清單的順序；例：商城的入口 main.mall）。server.main_view 放在原本商城那一格。"""
        return features_core.status(self)

    def status_data(self) -> dict:
        """狀態列的資料（數字與短字串），網頁前端照這份自己排版；status_text 是同一份資料的文字版。"""
        s, c = self.state, self.content
        p, w = s.player, s.world
        names = c.config.stat_names
        now, cap = team.member_neili(c, p.member, team.con_of(s, c, self.world, PLAYER), season=w)
        mates = []
        for cid in p.team:
            progress = self.world.get_companion(cid)
            mate_now, mate_cap = team.member_neili(c, progress, team.con_of(s, c, self.world, cid), season=w)
            mates.append({"name": c.characters[cid].name, "level": progress.level,
                          "hp": round(mate_now), "hp_max": round(mate_cap)})
        data = {
            "name": p.name,
            "affiliation": social.affiliation(s, c),
            "ranger": ranger.status(s, c),  # 散人的遊俠名號（名號、階、俠名、下一階）；陣營的人、劇本沒有陣營、名聲開著是 None
            "renown": renown.status(s, c),  # 名聲（狀態列 1B、2C 的稱號與說明卡）；名聲關著是 None
            # 手上揭了的懸賞（標題、怎麼完成、賞、期限與名額），加上身上有合用東西的求兵（多一個 have）；懸賞榜關著是空的
            "bounties": bounties.status(s, c, self.world),
            # 武學譜（口訣與秘方）：這一季聽過口訣或合中過的秘方，一條一筆 {"clues": [聽過的口訣], "solved": 名號或 None}
            "manual": secret_recipes.view(s, c, self.world),
            "manual_total": secret_recipes.progress(s, c, self.world)[1],  # 武學譜入口的分母：這一季全服共有幾條（不是「你聽過的」）
            "seal_duel": self.seal_duel_card(),  # 奪璽卡（玉璽碎片設計 5.10）：全服看得到；沒有單挑是 None
            "seal": self.seal_view(),  # 持有者的碎片卡（玉璽碎片設計第十節）
            "seal_watch": self.seal_watch(),  # 為真時網頁在背景也輪詢、輪到出招改分頁標題（5.5）
            "armament": self.armament_view(),  # 陣營的軍備存量（素材與經濟設計第六節）；散人、捐軍備關著是 None
            # 鑄譜（打造的隱藏配方）：這一季聽過口訣或打中過的，一條一筆 {"clues", "solved", "recipe"}（打造隱藏配方設計 6.3）
            "forge_manual": forge_secrets.view(s, c, self.world),
            "create": self.create_view(),  # 自創武學那一塊（煉製頁；tianxia/create.py）
            "ascension": ascend.view(self.state),  # 剛破境、還沒看過的破境卡（tianxia/ascend.py）
            "anonymous": p.anonymous,
            "gender": gender.of(p),  # 性別：修練頁的人物面板照它換男女版（web/app.js 的 HERO_FIGURES）
            "gender_chosen": p.gender_chosen,  # 選過了沒：設定頁沒選過的舊角色給一次改的機會
            "hints_off": p.hints_off,  # 設定頁「不再提示」的勾（新手引導計畫三）
            "level": p.member.level,
            "exp": team.exp_view(c, p.member),  # 這一級攢了多少、升下一級要多少（狀態列展開那一行）；滿級是 None
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
            "pills": None if (p.stamina_pills <= 0 and not c.config.beta_free_refill) or (
                prologue_rules.active(s, c) and not prologue_rules.pills_open(s, c)) else {
                "name": c.config.stamina_pill_name, "count": p.stamina_pills, "restore": c.config.stamina_pill_restore,
                "full": p.stamina >= c.config.stamina_max,
                # 今天還能服幾顆（一天的上限，台灣時間 00:00 換日，企劃者 2026-10-12）；不限（stamina_pills_per_day 0）時沒有這個鍵
                **({"today": self.pills_left_today()} if c.config.stamina_pills_per_day > 0 else {}),
                **({"refill": c.config.beta_free_refill_label} if c.config.beta_free_refill and not prologue_rules.active(s, c) else {}),
            },
            "newbie": self.newbie_view(),  # 新手目標（新手引導重做；tianxia/newbie.py）：引導走完、新手期裡才有
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
            "stat_uses": skillview.stat_uses(c, s),  # 減法季屬性五段開著時寫「現在給你什麼」的數字（設計 4.5）
            "stat_uses_note": skillview.STAT_CHECK_NOTE,
            # 心得付得起、又真的有事可做時才有；籌備中練成、合成都被擋，不提示（explain-2 審查 Minor 1）
            "hint": None if self._preparing() else skillview.practice_hint(s, c),
            "team": mates,
            "busy_hours": None if p.busy_until is None else round((p.busy_until - w.time) / HOUR / c.config.time_scale, 1),  # 現實小時
            "journey": None if p.journey is None else self._journey_line(),
            **self._calendar_status(),  # 第一季：季曆與下一件大事的倒數；開關關著時沒有這兩欄
        }
        # 點體力條看的說明（explain-1）：怎麼回、新手期、回體丹（一天的上限）或補滿，數字全讀設定；體力條上沒有那顆鈕（序章、沒丹）就不提它
        newbie = roster.newbie(s, c, c.config.newbie_stamina_days)
        data["stamina_help"] = howto.stamina_lines(
            c, w, newbie, p.stamina_pills, button=data["pills"] is not None, today=self.pills_left_today(),
            card=self._pill_card_bonus() if c.config.stamina_pills_per_day > 0 else 0,  # 月卡（FB-480）：上限照 pill_cap 寫
        )
        # 江湖頁行動列底下的「玩法說明」入口（explain-2）：新手期（跟體力回復加快同一段，newbie_stamina_days）才有、序章裡沒有（師父會說）；
        # 過了新手期只剩設定抽屜那一顆
        data["howto_entry"] = newbie and not prologue_rules.active(s, c)
        checkin_card = self.checkin_view()  # 每日簽到（21 天季，正式季整合 6.2）：關著、序章裡沒有這個鍵，畫面照舊
        if checkin_card is not None:
            data["checkin"] = checkin_card
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
            notes = {"sum": stance_sum_note(c)}
            if "haoqiang" in data["stances"]:  # 豪強分屬兩軍的季沒有割據那一方：不寫割據為什麼漲落
                notes["haoqiang"] = chaos_note(s, c, self._roster_players())
            data["stance_notes"] = notes
            data["stance_rule"] = stance_rule_note(s, c)  # 態勢卡底下的收季規則（正式版辛）
            # 點戰況圖卡、態勢、大事、主線看的說明（explain-2）：這一季在打什麼、亂局與割據、大事怎麼定、你能怎麼出力。
            # 門檻讀設定、此刻在亂局的讀 chaos_fronts、大事的件數讀時刻表（howto.war_help）；網頁點開才畫，不推動第一屏
            data["war_help"] = howto.war_help(s, c)
            data["invites"] = self._invite_status()
        return data

    def _invite_status(self) -> dict:
        """玩家卡要的邀請（玩家互動第二層）：收到的（就在你這個地點的）與發出去還在等的，各一份；剩幾秒是現實秒。
        答應、婉拒、收回照選單上的 id 送（invite:yes|no|cancel:<編號>，走 choose），發邀請走 /api/do/invite。"""
        s, c = self.state, self.content
        p = s.player

        def row(inv, who: str) -> dict:
            return {
                "id": inv.id, "kind": inv.kind, "kind_name": invites.kind_name(inv.kind), "who": who,
                "seconds_left": max(0, round((inv.expires_at - s.world.time) / c.config.time_scale)),
            }

        return {
            "incoming": [row(i, i.sender) for i in invites.incoming(s.world, p.name) if i.location == p.location],
            "outgoing": [row(i, i.target) for i in invites.outgoing(s.world, p.name)],
        }

    def _calendar_status(self) -> dict:
        """狀態列的季曆（第 N 週、週幾、幾點）與下一件大事：季曆時刻 at，加上倒數 in_seconds。倒數是現實秒：(大事時刻 − 世界秒) ÷ time_scale。"""
        w, c = self.state.world, self.content
        if not calendar.season_one_on(w, c):
            return {}
        at = calendar.point(w.time, c, w)
        # 休季時沒有下一件（計畫 T9）；籌備中時鐘沒走，也不倒數（FB-049）
        upcoming = None if w.ended or self._preparing() else timetable.next_event(self.state, c)
        cal = {
            "week": at.week, "weekday": at.weekday, "clock": f"{at.hour:02d}:{at.minute:02d}",
            # 畫面第二行直接用這一句，不自己拼（7 天濃縮季寫「第 N 天 HH:MM」）
            "weeks": calendar.weeks(c, w), "text": calendar.point_text(at, by_day=calendar.week7_on(w, c)),
        }
        if orders.daily(self.state, c):  # 21 天季的軍令每天一道：軍令卡收起來照季曆第幾天記（網頁 orderKey），隔天重新展開
            cal["day"] = at.cal_day
        # 7 天濃縮季：畫面上寫「週」的地方換成段（網頁 calWords，FB-501）；21 天季只有軍令的字（FB-502）；週末、14 天沒有這個鍵
        words = calendar.week_words(c, w)
        if words is not None:
            cal["words"] = words
        return {
            "calendar": cal,
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
        titles = {e.id: e.title for e in timetable.events(w, c)}
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
        for o in orders.current(s, c, self._side()):  # 豪強分屬兩軍：看依附那一軍的軍令
            total = sum(o.progress.values())
            view = {
                "id": o.id, "title": orders.title(c, o), "text": o.text, "mine": o.progress.get(name, 0),
                "progress": min(total, o.quota), "quota": o.quota, "done": o.done,
                "deadline": self.stamp(orders.deadline(s, c, o)),  # 下週一 00:00；21 天季是隔天 00:00
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
        for event in timetable.events(w, c):  # 天命之季含天命之爭（玉璽二）
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
        out = {
            "title": w.ending_title, "text": w.ending_text,
            "stances": [{"side": side, "name": names.get(side, side), "value": value} for side, value in standing.items()],
            "fronts": [{"id": f, "name": trend_name(c, f), "value": values.get(f, 0)} for f in front_ids(c)],
            "timeline": timeline,
            "rankings": [
                {"faction": f.id, "name": f.name, "rows": [list(row) for row in w.final_rankings.get(f.id, [])]}
                for f in c.scenario.factions
            ],
        }
        ending = self.ending_card()  # 三陣營四勝利（減法季批 3c，欄位表 main.ending）：關著的季沒有這個鍵
        if ending is not None:
            out["ending"] = ending
        return out

    # ── 三陣營四勝利（減法季整合設計第三章；計畫 Task 3c-2、3c-3：欄位表 main.ending；三方卡與「你這一步」補在批 1 的 weekcard 裡）──

    def ending_card(self) -> dict | None:
        """結局卡（欄位表 main.ending；設計 3.4）：收季之後、四勝利開著的季才有。winner 是贏的那一軍（和局 None），condition 是你算在
        哪一條（兩軍是陣營名，豪強是「地方豪強（官軍）」；散人、豪強沒有階是 None），my_tier 第幾階（0 是沒有），title 稱號，
        reward 下一季分到的，ledger_used 照哪一本排（豪強和局是 wins.BOTH）。收季那一刻存好（WorldState.final_tiers），這裡只讀。"""
        s, c = self.state, self.content
        w = s.world
        if not w.ended or not self._four_wins():
            return None
        result = w.final_tiers.get(s.player.name)
        tier = result.tier if result is not None else 0
        return {
            "winner": wins.winner_of(w, c), "condition": wins.condition_of(c, s.player.faction, result), "my_tier": tier,
            "title": result.title if result is not None else "", "reward": wins.reward_text(wins.rules_of(c), tier),
            "ledger_used": result.ledger_used if result is not None else None,
        }

    def _tier_outlook(self) -> tuple[TierResult, int | None]:
        """此刻就收季（結局照此刻會成立的那一種，world.evaluate_ending）自己拿第幾階、離上一階還差多少（wins.outlook）。名次要讀
        這一季每個人的帳（CharacterStore.books，只挑那幾欄）；自己照記憶體裡的這一份（這一下剛記的貢獻可能還沒存）。"""
        s, c = self.state, self.content
        me = s.player
        others = [q for q in CharacterStore(self.world.db).books(me.season_number) if name_key(q.name) != name_key(me.name)]
        winner = evaluate_ending(_season_vehicle(c, s.world), c).winner
        return wins.outlook(c, [*others, me], me.name, winner)

    def tier_hint(self) -> str | None:
        """三方卡的 tier_hint（weekcard.sides_card，批 3c）：此刻就收季拿第幾階・離上一階還差多少（「第三階・還差 40」「第一階」
        「未入階・還差 20」，wins.tier_hint）。四勝利開著、季還沒收、投靠了劇本裡的陣營才有；其餘是 None。"""
        s, c = self.state, self.content
        if not self._four_wins() or s.world.ended or c.scenario.find_faction(s.player.faction) is None:
            return None
        return wins.tier_hint(*self._tier_outlook())

    def place_minutes(self, loc_id: str) -> int | None:
        """從此刻的位置走到 loc_id（步行；騎著馬照馬的步調）要現實幾分鐘（同狀態列的「現實約 N 分鐘後抵達」）；就在這裡是 0、走不到是 None。
        先照摸清的路（atlas.way_to），走不到再照所有開放的地點（投靠點是公開的，三方卡照樣寫得出分鐘）。三方卡、本週卡的目標用。"""
        s, c = self.state, self.content
        if s.player.journey is None and s.player.location == loc_id:
            return 0
        route = atlas.way_to(s, c, loc_id)
        if route is None and s.player.journey is None:
            route = atlas.shortest_routes(s, c).get(loc_id)
        if route is None or not route.path:
            return None
        return self._real_minutes(atlas.travel_seconds(route.minutes, "walk", pace=mounts.pace(s, c)))

    def _gentry_now(self, faction: FactionDef) -> str:
        """三方卡豪強那一欄的「現在」：看的人是豪強寫此刻幫誰與兩本帳（設計 3.4），其他人寫此刻依附兩軍各幾人（投靠名冊）。"""
        s, c = self.state, self.content

        def name(side: str) -> str:
            return c.scenario.faction_name(side, side)

        if s.player.faction == faction.id:
            books = "、".join(wins.NOW_GENTRY_BOOK.format(side=name(side), n=n) for side, n in (wins.ledger_view(s.player, c) or {}).items())
            return wins.NOW_GENTRY_MINE.format(side=name(s.player.ally) if s.player.ally else "", books=books)
        rolls = allied.gentry_totals(self.world.roll_counts())
        return "、".join(wins.NOW_GENTRY_ROLL.format(side=name(side), n=rolls.get(side, 0)) for side in faction.allies)

    def sides_card(self) -> dict | None:
        """三方卡的批 3c 資料（設計 3.4）：劇本的每一方（陣營 id →）{name, goal 要做到, reward 贏了給, join_at 投靠在哪
        [{location, name, minutes}], now 現在}，稱號與比例照 Config.jianfa.tiers。畫面的三方卡是批 1 的 weekcard.sides_card
        （欄位表 main.sides_card），它拿這一份補豪強那一格的「現在」、每一方的「贏了給」與投靠點的分鐘；最後一週「離贏還差多少」
        在 week_unlock.win_gap（wins.gap_line）。四勝利關著、休季沒有。"""
        s, c = self.state, self.content
        w = s.world
        if not self._four_wins() or w.ended:
            return None
        standing = stances(s, c)
        out = {}
        for f in c.scenario.factions:
            now = self._gentry_now(f) if f.allies else wins.NOW_ARMY.format(value=standing.get(f.id, 0))
            out[f.id] = {
                "name": f.name, "goal": wins.goal_text(c, f), "reward": wins.reward_card(c, f),
                "join_at": [{"location": loc, "name": c.locations[loc].name, "minutes": self.place_minutes(loc)} for loc in f.join_at],
                "now": now,
            }
        return out

    def annals_view(self) -> dict:
        """見聞的「行狀」頁（玩家傳第一批）：這一季至今記下的事，照時間先後；開關關著時 on 是 False、rows 是空的。
        books 是歷季列傳（第二批）：存著的每一季（這一季收了、還沒換季的也算），新的在前。"""
        on = annals.on(self.content)
        return {
            "on": on, "name": self.state.player.name, "rows": annals.rows(self.state, self.content) if on else [],
            "books": self.biography_list() if on else [],
        }

    # ── 玩家傳第二批：季末寫成《某某傳》、公開分享 ──

    def _season_closed(self) -> bool:
        """這一季收了（休季）：這一季的傳寫得了。"""
        return self.world.season_phase() == "resting"

    def biography_entry(self) -> dict | None:
        """休季時江湖頁最上面的「讀你的傳」（這一季的那一篇）：季收了、有行狀或已經存了那一篇才有；假人、開關關著、季還在跑是 None。
        輪詢每次都問：季還在跑時不讀資料庫。列傳為終點開著（減法季批 7b）多 tier、illustration、seal（_zhuan_extra）。"""
        p = self.state.player
        if not annals.on(self.content) or p.bot is not None or not self.state.world.ended:
            return None
        if not p.annals and self.world.biography(p.season_number, p.name) is None:
            return None
        return {"season": p.season_number, "title": biography.title(p.name), **self._zhuan_extra(p.season_number)}

    # ── 列傳為終點（減法季批 7b）：休季用票、列傳多畫的那幾樣 ──

    def _zhuan_season(self, season: int) -> WorldState | None:
        """那一季的 WorldState（這一季照手上的，以前的照 past_season）；沒有是 None。"""
        p = self.state.player
        return self.state.world if season == p.season_number else self.world.past_season(season)

    def _zhuan_purchases(self) -> list:
        return self.wallet.purchases()

    def _zhuan_extra(self, season: int) -> dict:
        """列傳多畫的那幾樣（zhuan_end.extras：季末論功、插畫的圖庫鍵、紀念印的字）；那一季沒開列傳為終點是空的（一個鍵都不多）。
        這一季的身家照角色身上的，以前的季照存起來的那一份。評曰的名單照寫成的那一篇傳列（FB-847，zhuan_end.extras 的 text）：
        還沒寫成是 None（預告要寫的人）。"""
        p = self.state.player
        world = self._zhuan_season(season)
        if world is None or not zhuan_end.on(self.content, world):
            return {}
        row = self.world.biography(season, p.name)
        if season == p.season_number:
            profile = annals.profile(self.state, self.content, season=world)
        else:
            profile = row["profile"] if row is not None else {}
        text = row["text"] if row is not None else None
        return zhuan_end.extras(self.content, season, profile, zhuan_end.season_tickets(self._zhuan_purchases(), season), text)

    def _zhuan_options(self) -> list[Option]:
        """休季用列傳的票（減法季批 7b；設計第九章）：列傳為終點開著、季收了，手上有沒用的票才有那一顆。插畫：投靠了劇本裡的陣營、
        這一季還沒用過、不是第一階（第一階白送）；紀念印：這一季還沒蓋；親筆評曰：情誼 40～69、這一季還沒替你寫的人物一位一顆。"""
        s, c = self.state, self.content
        if not s.world.ended or not zhuan_end.on(c, s.world):
            return []
        purchases = self._zhuan_purchases()
        if not purchases:
            return []
        n = s.player.season_number
        used = zhuan_end.season_tickets(purchases, n)
        standing = annals.standing(s, c, s.world)
        out = []
        # 票綁買的那一季（FB-845）：只數這一季買的，之前的季沒用掉的不再冒出用票的鈕
        if zhuan_end.unused(purchases, zhuan_end.ART, n) and standing.get("illustration") and not used["art"] and standing.get("tier") != 1:
            out.append(Option(id=zhuan_end.PICK_ART, label=zhuan_end.ART_BUTTON))
        if zhuan_end.unused(purchases, zhuan_end.SEAL_TICKET, n) and not used["seal"]:
            out.append(Option(id=zhuan_end.SEAL, label=zhuan_end.SEAL_BUTTON.format(seal=zhuan_end.seal_text(c, n, standing))))
        if zhuan_end.unused(purchases, zhuan_end.QUOTE_TICKET, n):
            taken = set(used["quotes"]) | set(self._verdict_taken(standing))
            out += [Option(id=f"{zhuan_end.QUOTE}{cid}", label=zhuan_end.QUOTE_BUTTON.format(name=c.characters[cid].name, value=value))
                    for cid, value in zhuan_end.quote_figures(s, c, taken)]
        return out

    def _verdict_taken(self, standing: dict) -> list[str]:
        """這一季已經白送評曰的人物（annals.standing 的 verdicts：第一二階的主將或家主、情誼 70 以上的；親筆評曰不再列他們）。"""
        return [w["fid"] for w in standing.get("verdicts", [])]

    def _zhuan_act(self, option_id: str) -> list[str]:
        """用掉一張列傳的票（_zhuan_options 驗過有票、按得下去）：那一列購買記 used、season（親筆評曰另記 fid），寫一則「列傳」紀錄。"""
        s, c = self.state, self.content
        n = s.player.season_number
        now = self.pill_now()
        if option_id == zhuan_end.PICK_ART:
            self.wallet.consume(zhuan_end.ART, bought_in=n, at=now, season=n, art=zhuan_end.illustration_for(s, c, s.world))
            lines = [zhuan_end.ART_DONE]
        elif option_id == zhuan_end.SEAL:
            self.wallet.consume(zhuan_end.SEAL_TICKET, bought_in=n, at=now, season=n)
            lines = [zhuan_end.SEAL_DONE.format(seal=zhuan_end.seal_text(c, n, annals.standing(s, c, s.world)))]
        else:
            cid = option_id.removeprefix(zhuan_end.QUOTE)
            self.wallet.consume(zhuan_end.QUOTE_TICKET, bought_in=n, at=now, season=n, fid=cid)
            lines = [zhuan_end.QUOTE_DONE.format(name=c.characters[cid].name)]
            row = self.world.biography(n, s.player.name)
            if row is not None and row["text"] is not None:
                lines.append(zhuan_end.QUOTE_LATER)
        journal.add_entry(s, JournalEntry(time=s.world.time, title=zhuan_end.TITLE, lines=lines))
        return lines

    def biography_list(self) -> list[dict]:
        """歷季列傳：每一季一列（季別、篇名、寫成了沒、公開了沒）。這一季收了、行狀還在角色身上（還沒換季）的那一季排第一。"""
        p = self.state.player
        rows = {b["season"]: b for b in self.world.biographies_of(p.name)}
        out = []
        if self._season_closed() and p.annals and p.season_number not in rows:
            out.append({"season": p.season_number, "title": biography.title(p.name), "written": False, "public": False})
        out += [
            {"season": n, "title": biography.title(b["name"]), "written": b["text"] is not None, "public": b["public"]}
            for n, b in sorted(rows.items(), reverse=True)
        ]
        return out

    def biography_request(self, season: int, rewrite: bool = False) -> biography.BiographyRequest | None:
        """A 段（鎖內、只讀）：那一季那一篇要寫（或重寫）的單子。寫不了回 None：開關關著、假人、這一季還沒收、那一季沒有行狀、
        已經寫過而不是重寫、重寫的次數用完了。這一季收了、還沒換季時，行狀與身家照角色身上的；以前的季照存起來的。"""
        c, p = self.content, self.state.player
        if not annals.on(c) or p.bot is not None:
            return None
        row = self.world.biography(season, p.name)
        if row is None:
            if rewrite or season != p.season_number or not self._season_closed() or not p.annals:
                return None
            entries = tuple(e.model_dump() for e in sorted(p.annals, key=lambda e: e.time))
            profile = annals.profile(self.state, c, season=self.state.world)
        else:
            if season == p.season_number and not self._season_closed():
                return None
            entries = tuple(sorted(row["annals"], key=lambda e: e.get("time", 0.0)))
            profile = row["profile"]
            if season == p.season_number and p.annals and row["text"] is None:  # 這一季還沒寫成：照角色身上最新的
                entries = tuple(e.model_dump() for e in sorted(p.annals, key=lambda e: e.time))
                profile = annals.profile(self.state, c, season=self.state.world)
            written = row["text"] is not None
            if written != rewrite or (rewrite and row["rewrites"] >= self._rewrites_allowed()):
                return None
        if not entries:
            return None
        chronicle = dict(self.world.chronicle_before(season + 1)).get(season, [])
        era = [r.text for r in chronicle][: biography.ERA_MAX]
        return biography.BiographyRequest(
            season=season, name=p.name, scenario=c.scenario.name, era_note=c.scenario.era_note, profile=profile,
            annals=entries, era=tuple(era), rewrite=rewrite, sex=gender.of(p), verdicts=self._verdict_jobs(season, entries, profile),
        )

    def _verdict_jobs(self, season: int, entries: tuple[dict, ...], profile: dict) -> tuple:
        """人物評曰的單子（減法季批 7b-2，zhuan_end.verdict_request）：身家裡白送的寫手（第一二階的主將或家主、情誼 70 以上的），
        接這一季用了親筆評曰請的那幾位。那一季沒開列傳為終點是空的。"""
        c, p = self.content, self.state.player
        world = self._zhuan_season(season)
        if world is None or not zhuan_end.on(c, world):
            return ()
        free = [zhuan_end.Writer(w["fid"], w["reason"]) for w in profile.get("verdicts", [])]
        bought = zhuan_end.season_tickets(self._zhuan_purchases(), season)["quotes"]
        writers = zhuan_end.with_bought(free, bought, c)
        fixed = zhuan_end.fixed_verdicts(c, writers, p.name, season)  # 整篇一起挑固定句：模型叫不動時兩位寫手也不會一字不差（FB-848）
        return tuple(zhuan_end.verdict_request(c, w, p.name, gender.of(p), entries, profile, season, fixed=fixed[w.fid])
                     for w in writers)

    def write_biography(
        self, request: biography.BiographyRequest, text: str | None, now: float, verdicts: dict[str, str] | None = None,
    ) -> bool:
        """C 段（鎖內）：重驗單子（同一季、同一份行狀、還寫得了），存進 biographies。text 是 B 段模型寫好、清過的全文；None 就照規則拼。
        這一季的先把行狀與身家存起來（換季時存的是同一份；之後再來的決戰照 add_saved_annal 補）。存了回 True。
        列傳為終點（減法季批 7b-2）：單子上的每一位評曰寫手接一段「評曰：」（verdicts 是 B 段寫好的，人物 id → 一句；沒寫成照固定句）。"""
        current = self.biography_request(request.season, request.rewrite)
        if current is None or current.annals != request.annals:
            return False
        p = self.state.player
        if request.season == p.season_number and p.annals:
            self.world.save_annals(request.season, p.name, list(request.annals), dict(request.profile))
        by = biography.MODEL if text else biography.RULE
        row = self.world.biography(request.season, p.name) if request.rewrite else None
        body = text or biography.rule_text(request)
        for job in request.verdicts:  # 人物評曰（批 7b-2）：一位一段，接在正文（含史官的評曰）後面
            body += "\n\n" + zhuan_end.apply_verdict(job, (verdicts or {}).get(job.fid, ""))
        stored = self.world.store_biography(request.season, p.name, body, by, now, request.rewrite)
        if stored and row is not None and row["rewrites"] >= self.content.config.biography.rewrites:
            self._use_rewrite_token(now)  # 白送的重寫用完了，這一次是萬寶閣買的「重修列傳」
        return stored

    def _rewrite_tokens(self) -> list[int]:
        """萬寶閣「重修列傳」還沒用掉的那幾筆購買（錢包服務的 zhuan_rewrite 票）；商城關著是空的。"""
        return self.wallet.tokens("zhuan_rewrite")

    def _rewrites_allowed(self) -> int:
        """一篇傳能重寫幾次：Config.biography.rewrites 加上手上還沒用掉的「重修列傳」（Joy 2026-10-21 定案：200 元寶、一季兩次）。"""
        return self.content.config.biography.rewrites + len(self._rewrite_tokens())

    def _use_rewrite_token(self, now: float) -> None:
        self.wallet.consume("zhuan_rewrite", at=now)

    def biography_view(self, season: int) -> dict | None:
        """修練之外的一本書（網頁的「讀你的傳」）：篇名、段落、誰寫的、公開了沒、分享代碼、還能不能重寫、還沒寫成時寫不寫得了。
        那一季沒有（沒有行狀、還沒收季）回 None。"""
        p = self.state.player
        row = self.world.biography(season, p.name)
        if row is None or row["text"] is None:
            ready = self.biography_request(season) is not None
            if row is None and not ready:
                return None
            return {
                "season": season, "title": biography.title(p.name), "written": False, "can_write": ready, "paragraphs": [],
                "scenario": self.content.scenario.name, **self._zhuan_extra(season),  # 列傳為終點（批 7b）：關著一個鍵都不多
            }
        return {
            "season": season, "title": biography.title(row["name"]), "written": True, "paragraphs": row["text"].split("\n\n"),
            "by": row["written_by"], "public": row["public"], "code": row["share_code"] if row["public"] else None,
            "can_rewrite": row["rewrites"] < self._rewrites_allowed(), "scenario": self.content.scenario.name,
            **self._zhuan_extra(season),
        }

    def share_biography(self, season: int, public: bool, code: str) -> str | None:
        """公開或收回那一季的傳（寫成了才行）；回傳分享代碼（收回時也回，網頁不用它）。code 是伺服器產生的亂碼，已經有代碼就沿用。"""
        if not annals.on(self.content) or self.state.player.bot is not None:
            return None
        return self.world.share_biography(season, self.state.player.name, public, code)

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
        """江湖史：這一季在最前面，往前每一季各一段（線上架構設計 3.2：江湖史跨季保留），再來是歷屆擂主，最後是玉璽碎片。
        神器譜搬到見聞的「榜單」（divine_book_view，Joy 2026-10-17）。"""
        number = self.world.get_season_number()
        current = _timeline(self.state.world.chronicle, self._day_stamp) or "（江湖史尚無記載。）"
        past = self.world.chronicle_before(number)
        parts = [f"### 第 {number} 季（本季）\n\n{current}" if past else current]
        parts += [f"### 第 {n} 季\n\n{_timeline(entries, calendar.day_text)}" for n, entries in past]  # 上一季照舊寫「第N天」
        champs = arena.champions([(number, [e.text for e in self.state.world.chronicle])]
                                 + [(n, [e.text for e in entries]) for n, entries in past])  # 歷屆擂主（跨季）
        if champs:
            parts.append(champs)
        if seal.on(self.content):  # 七格玉璽排在江湖史最上面（第十節）；舊的碎片紀錄只當前史一行（11.5）
            old, view = self.world.get_jade_seal_fragments(), self.world.seal_state()
            parts.insert(0, seal.chronicle_block(self.content, view.registry, self.world.jade_seal_summary() if old else "",
                                                 mandate=seal.mandate_now(view.registry, view.season)))  # 天命之季多一句（玉璽二）
        else:
            parts.append(self.world.jade_seal_summary())
        return "\n\n---\n\n".join(parts)

    def divine_book_view(self) -> list[dict]:
        """見聞「榜單」的神器譜（打造隱藏配方設計 5.5；Joy 2026-10-17「神器譜移到排行榜」，原本接在江湖史後面）：跨季，新的一季在前，
        同一季打出來的神器在前、名將本命兵器在後。一筆 {season, name, text, ref}（ref 認那一把，點開看卡用，leaderboard.gear_card）；都沒有是空的。"""
        rows = forge_secrets.divine_entries(self.world.divine_records())
        rows += signature_arms.book_entries(self.content, self.world.signature_records())
        rows.sort(key=lambda row: -row[0])  # 穩定排序：同一季照原來的先後
        return [{"season": season, "name": name, "text": text, "ref": ref} for season, name, text, ref in rows]

    # ── 江湖紀錄 ──────────────────────────────────────────

    def _day_stamp(self, time: float) -> str:
        """江湖史與傳聞的時間：沒有季曆時只寫天數（「第2天」），第一季寫季曆。"""
        return self.stamp(time, clock=False)

    def _chip(self, change: str, seed: str) -> tuple[str, int] | None:
        """江湖紀錄畫數值標籤時，戰況變化的換法（FB-064，journal.ChipFn）：紀錄裡存的是機器可讀的寫法，這裡照內容換成一句話、
        照「現在看的人」的陣營算對他是好事還是壞事（顏色在畫的那一刻才定，換了陣營再畫就跟著變）。"""
        return front_chip(self.content, self._side(), change, seed)

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
        if opening_rules.pending(self.state, self.content):
            return ""  # 開局第一分鐘（減法季批 7）：旁白與三選一就是第一張卡，開場那一則（含丹的福利）留在紀錄裡（整合設計 6.7）
        entry = self._now_entry()
        return journal.card_html(entry, self.stamp, self._chip) if entry is not None else ""

    def _now_entry(self) -> JournalEntry | None:
        """「剛剛」那一則（now_entry_html 的挑法，不看籌備中與草廬的事件）。"""
        hut = prologue_rules.active(self.state, self.content)
        shown = self._news_on_cards()

        def repeated(entry: JournalEntry) -> bool:
            story = entry.lines or [entry.tag]
            return entry.title == journal.WORLD_NEWS and all(
                line in shown or line.partition("　")[2] in shown for line in story
            )

        fresh = [e for e in self.state.journal if not repeated(e) and not (hut and journal.is_world_entry(e))]
        return next((e for e in fresh if e.title != journal.ALLOCATE), fresh[0] if fresh else None)

    def now_front(self) -> dict | None:
        """「剛剛」那一則是出陣、有出陣回報（JournalEntry.front，sortie.report）時給畫面的資料；不是 None。戰鬥卡片照 shows_battle_card 看
        同一則，不是戰鬥卡片照 now_entry_html 的挑法（那裡不放卡時這裡也不給）。"""
        if self.shows_battle_card():
            entry = self.state.journal[self._now_start()]
        elif self.now_entry_html():
            entry = self._now_entry()
        else:
            return None
        return entry.front.model_dump() if entry is not None and entry.front is not None else None

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

    def _art_name(self, art_id: str) -> str:
        art = team.resolve_art(art_id, self.content, self.world)
        return art.name if art is not None else art_id

    def _renown_after(self, synced: bool = False, fresh: list[JournalEntry] | None = None) -> None:
        """名聲（設計 3.3、6.4、十一之二第 6 條）：這一下的名望、善名、惡名合成一行、接差距（renown.annotate），再比跨段（renown.watch）。
        動作裡發現的接在這一下那一則江湖紀錄（最新一則、時間是此刻）的最後，得失那一排多一顆金色的「名號傳開」；這一下打了仗，戰報的
        得失一樣接差距。同步時發現的（synced）另起一則「名聲」；fresh 是這一次同步補進來的那幾則（時間可能比此刻早，例如決戰收場那一刻），
        一樣接差距。上線之後第一次看只記段、寫一則說明（一人只寫一次，renown_told 跨季帶著走）。
        行狀記升段（只記到過的最高段以上）。開關關著什麼都不做。"""
        s, c = self.state, self.content
        if not renown.on(c):
            return
        entry = s.journal[0] if s.journal and s.journal[0].time == s.world.time and not synced else None
        if entry is not None:
            entry.changes = renown.annotate(entry.changes, s, c)
        for written in fresh or []:  # 同步時補進來的那幾則（決戰收場後補的戰報與軍餉、首創回饋、擂台的俸）也合成一行、接差距（FB-292）
            written.changes = renown.annotate(written.changes, s, c)
        record = next((r for r in s.battles if r.id == s.battle_card), None) if s.battle_card is not None else None
        if record is not None and not synced:
            record.changes = renown.annotate(record.changes, s, c)
        crossed = renown.watch(s, c, game_day(c, s.world))
        if renown.news_up_due(s, c, crossed.up):  # 名聲 4.5：跨過威震州郡，天下大事傳一句（一季一人一次）
            s.player.flags.add(renown.NEWS_UP_FLAG)
            add_rumor(s, renown.NEWS_UP.format(name=s.player.name), content=c, layer="world")
            # 傳聞在共用賽季裡，這裡自己存（FB-291）：動作照例先存季、再 _log，輪詢的同步只存角色——不存的話旗標跟著角色存了，
            # 那一句卻沒進資料庫，之後也不會再傳
            self._save_season()
        if crossed.first and not s.player.renown_told:
            s.player.renown_told = True
            journal.add_entry(s, Draft(renown.TOLD_TITLE).entry(s.world.time, [renown.TOLD]))
        # 名聲 5.1：浩然、血煞要走對那條路；善名惡名從懸賞、截殺來的（不經 rules.apply_effect）也在這裡接到
        granted = insights.grant_by_name(s, c, self.world) if renown.on(c, "virtue_insight") else []
        lines = crossed.lines + granted
        if not lines:
            return
        marks = [journal.renown_mark(title) for title in crossed.up]
        if entry is not None:
            entry.lines += lines
            entry.changes += marks
        else:
            fresh = Draft(renown.TOLD_TITLE).entry(s.world.time, lines)
            fresh.changes += marks
            journal.add_entry(s, fresh)
        for text, weight in crossed.annals:
            annals.note(s, c, annals.DEED, text, weight)

    def _log(self, msgs: list[str]) -> list[str]:
        """回給呼叫端、也存進 GameState.log 的訊息。戰況變化（機器可讀的寫法）在這裡換成一句話——這些話玩家（管理者工具列的
        提示）看得到，數字不外露（FB-064）；江湖紀錄那邊在畫的時候換（見 _chip），兩邊用同一個 seed（現在的時間），是同一句。"""
        self._renown_after()  # 名聲：這一下的名望、善名、惡名接差距，比跨段（設計 3.3、6.4）
        annals.watch(self.state, self.content, art_name=self._art_name)  # 行狀：這一下改了什麼（投靠、晉升、情誼……）記一筆
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

