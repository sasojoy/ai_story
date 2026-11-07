"""遊戲門面：介面層唯一需要呼叫的類別。負責行動、選項、時間流逝與畫面文字。

sanguo-companions 合併大幅重寫：拿掉 battle.py 的 3v3 全自動戰鬥、多隊派遣、招賢抽卡、
收徒系統，改成單次判定遭遇（encounter.py）、單一隊伍（最多 4 位同伴）、唯一同伴的
招募（roster.py）、練功（team.py：鍛鍊；開局送兩門基礎武學，自創武學已作廢）。
"""
from __future__ import annotations

import contextlib
import math
import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from . import arts as arts_mod
# （cultivation：破境卡 ascend 全部拆包第 23 批搬進修練包，engine 不再用，拿掉）
from . import attrset  # 五項屬性（屬性與跨季架構 v2 第三節）
from . import narration  # 事件旁白每週改寫（減法季批 10）
from . import (
    allied, armor, atlas, battlelog, calendar, clinic, conquest, economy, encounter, equipment,
    fight_llm, figures, forge_secrets, gender, insight_fx, insights, journal, library, martial_arts, place_state, plans,
    materials, mounts, orders, precise, push, ranger, ranks, renown, rise, roster, rounds, seal_acts, secret_recipes, sensing,
    shopview, signature, skillview,
    sortie, styles, tactics, team, terrain, territory, timetable, traits, treasures, weapons, week_unlock, zh,
)
from . import flavor
from .flavor import FlavorJob
from . import tiers  # 事件分級：場景卡上那一行「州郡大事」「天下大事」
from . import growth  # 減法季批 2：三道閘、屬性五段的純規則（開關走 rules.jianfa；探索一顆搬進了探索包）
from . import speech
from . import events as event_rules  # note_round 走模組屬性（測試要能換掉它，確認只有 _present 會叫）
from . import prologue as prologue_rules  # Game.new 有個參數也叫 prologue，所以模組在這裡一律叫 prologue_rules
from . import rumor_view  # 傳聞分層的畫面：見聞頁的四層、你不在的時候（計畫 2026-10-06 傳聞分層一）
# 減法季批 4：隨口應對分岔、痕跡看得見、貢獻（三陣營四勝利的 wins.credit）；別名避開這個檔裡叫 marks、outcomes 的區域變數
from . import marks as marks_rules
from . import outcomes as outcome_rules
from . import wins as wins_rules
from .models import FreeTextChoice, Outcome
from .rules import jianfa
from . import step as step_rules  # 本週卡「你這一步」（減法季批 3c）；叫 step_rules：這個檔裡有區域變數叫 step
from . import wins  # 三陣營四勝利（減法季批 3c）：豪強兩本帳、傾向、季末四階
from .characters import CharacterStore, name_key
from .events import (
    event_candidates, free_text_note, pick_event, visible_choices,
)
from . import training
# guide（全部拆包第 22 批）：新手引導的本體在 tianxia/features/guide/；Game._note_action 叫的是這裡的 note_action（別名 tianxia.guide，
# tests/core/test_engine.py 換的是 tianxia.engine.note_action），其餘的委派叫包的 actions
from .guide import note_action
from .journal import LOG_BREAK, Draft
from .core import bounty_base  # 懸賞榜「別人讀」的那一半（全部拆包第 45 批：收店、榜的入口、投靠那一下作廢、翻頁不寫紀錄、第 2 週才開）
from .martial_arts import QUALITIES  # （cultivation：is_renamed 跟著 _deliver_renames 搬進修練包，拿掉）
from .models import (
    EXPLORE_BRANCHES, FREE_TEXT_MAX, Check, Choice, Content, Effect, Event, FactionDef, Location,
    RoadKind, Squad, TravelMode, TutorialStep,
)
from .ollama_client import ModelBudget, OllamaClient, quick_client
from .rules import (
    HUANGJIN, add_rumor, add_season_rumor, add_world_flags, apply_effect, audible, audience_bar, audience_hint, can_meet, change_trend,
    ears_of, fill_marks, game_day, here_regions,
    chaos_fronts, front_chip, front_ids, front_of, humanize,
    is_revealed, learn_skill, resolve_goals, resolve_trend, roll_check,
    season_one, stance_rule_note, stance_sum_note, stances, trend_name, trend_shown, trend_value,
    world_day, world_trend_value,
)
from .rules import jianfa  # 減法季（Config.jianfa＋開季的章；子開關照名字問）
from .sqlite_world import open_world
from .wallet import Wallet
from .core import annal_base as annals  # 行狀記一筆（第 29 批之二）
from .core import features as features_core  # 核心照 FEATURES 問每一包（開發規範手冊 3.3）
from .core import battle_base as battle_instance  # battle（全部拆包第 54 批）：決戰的資料型別與判定（核心本體）；規則那一半在決戰包，Game 上沒有方法讀它
from .core import xinshen  # 心神：跟人物交談扣的點數（核心的資源，同體力；Config.xinshen）
from .core import omen_base  # 正在答題（軍情包認領的 fs_asking；core_seams，全部拆包第 56 批：_own_scene_text 改問它）
from .core import seal_base  # seal（全部拆包第 27 批）：管理者「定結果」替天命之爭定天命、江湖史七格讀玉璽「讀」的那一小半（核心本體）
from .core.option import IDLE_MARK, Option  # 選單上的一顆（搬進核心：功能包要做選項）；閒著的選單一定有的那一顆（走一趟要認它）
from .core.services import PAUSED_REFUSAL, PAUSED_TEXT, WalletService, drill_share, wallet_on  # 共用的字與小函式、錢包服務（3.10）
from .core.services import BIG_FIGHT_WAIT  # sortie（全部拆包第 17 批）：大場面按鈕上的字搬進核心的共用的字（出陣包的遊歷鈕也用）
from .core.services import PLAN_OPTION, ROAD_SAY, SAY_MAX, SAY_OPTION, TEXT_TALKS, say_text  # noqa: F401  companions（全部拆包第 20 批）：「自己說」那三顆的 id 與那句話能不能送，搬進核心的共用的字
from .core.services import SNUB_NOTE, SOCIAL_NO_ONE  # noqa: F401  socialize（全部拆包第 21 批）：交友求見的三個共用的字搬進核心的共用的字（SOCIAL_NO_ONE、SNUB_NOTE 測試從 engine 拿）
from .core.services import ROAD_REWARD_TASKS, ROAD_TASKS  # noqa: F401  travel（全部拆包第 47 批）：路上小事的名稱表與有收穫的那兩樣搬進核心的共用的字（from tianxia.engine import ROAD_TASKS 照舊拿得到）
from .core.services import MOVE_BLOCKED, RaidSpoils  # stamina_plays（全部拆包第 39 批）：移動被擋的標籤與設伏／截殺共用的贏家帳
from .core.services import HutReward  # guide（全部拆包第 22 批）：序章步驟的獎勵那一行的記號（原本 import 自 guide）
# sense（全部拆包第 24 批）：籌備中那兩句與走一趟的裝飾器搬進核心的共用的字與小函式（engine 照舊用：`from tianxia.engine import PREPARING_REFUSAL`
# 兩個測試檔在拿；choose、answer_event 照舊掛 @_outing_watch）
from .core.services import PREPARING_REFUSAL, PREPARING_TEXT  # noqa: F401
from .core.services import outing_watch as _outing_watch
# explore
# tavern（擺在宴客與出陣之間：別條拆包線在 core.services 之後、出陣那一行之後各加一段，不貼在一起）
from .features.sortie.rules import CLASH_OPEN, CLASH_THEIRS_WON, CLASH_WON  # noqa: F401  過渡：tianxia/features/peers/tests/test_raid.py 從 engine 拿
# sortie（全部拆包第 17 批）：舊遊歷、操練、守勢的 8 個一行委派；必敗先問的那兩句搬進包（test_orders、test_mounts、test_prologue_web 從 engine 拿）
from .features.sortie.rules import TRAIN_CONFIRM, TRAIN_CONFIRM_RIDING  # noqa: F401  過渡：三個測試檔從 engine 拿
# battle
from .features.battle import rules as battle_rules  # 過渡：決戰的字（Game.BATTLE_GAMBLE_* 類別屬性、委派的型別註記）
from .features.battle.rules import (  # noqa: F401  過渡：測試從 engine 拿（test_companions_battle、test_followers_matter、
    ESCORT_MUSTER, ESCORT_SCENE, RESTORED_NOTE, ROUND_BLOCKS, TROOPS_LINE, TROOPS_REPORT,  # test_showdown_full_report、test_battle_round_blocks）
    ESCORT_PICK,  # 第 7 批：挑同伴那一句（test_companions_battle 從 engine 讀）
)
# bout
from .features.bout import duel_rules as bout_rules  # 過渡：Game.DUEL_GAMBLE_NOTE 類別屬性、委派的型別註記（DuelTextRequest）
# companions（全部拆包第 19 批：人物情誼一）
from .features.companions import actions as companions_actions  # 過渡：Game 上人物情誼的 29 個一行委派（招募、名下、心意、託付、書信）
# companions（全部拆包第 20 批：人物情誼二）

if TYPE_CHECKING:  # 型別註記用（companion_agent、parley 搬進人物情誼包之後 engine 不再 import 它們；Game 上的委派只轉手）
    from .features.companions import companion_agent, parley
    from .features.territory_acts import xingshi  # 〈天下形勢〉B 段的請求型別（全部拆包第 46 批）
# cultivation（全部拆包第 23 批「修練」）：裝飾器搬進核心的共用的小函式（還掛在 Game 上的動作照舊掛 @_not_while_preparing；籌備中那兩句第 24 批先搬了，
# `# sense` 那一行 import）；
# 修練頁的 33 個一行委派（原本 engine 那兩行 import 的 cultivation、chuangong 與 `from . import ascend` 現在是修練包的別名，engine 不再用，拿掉）
from .core.services import not_while_preparing as _not_while_preparing
# seal（全部拆包第 27 批）：Game 上玉璽碎片季流程的 11 個一行委派（核心原位、殼的 ADMIN_ACTIONS、決戰包經 ctx、測試與量表腳本叫的）。
# 第 28 批（玉璽二）：碎片卡、獨門行動、奪璽單挑、管理者六個也搬進包（Game 留 22 個一行委派）；頂端的 seal_rules 與 seal_duel 沒人用了，拿掉
# smithy（全部拆包第 41 批）：Game 上鐵匠鋪的 12 個一行委派（server、假人、測試與核心原位的選單叫的）
from .features.cultivation.actions import MELT_MANY_PROLOGUE  # noqa: F401  過渡：tianxia/features/guide/tests/test_prologue.py 從 engine 拿
# checkin（全部拆包第 30 批）：回體丹那一套歸核心，簽到開著沒、掉回體丹那一句搬進核心的共用小函式（Game._pill_find 用）
from .core.services import PILL_FOUND, checkin_on
# story（全部拆包第 30 批）：一條線的底座（共用規則層：JOURNAL、場景圖、題目文字、線的定義）；10 個一行委派（章回 chapters 的模組層 import 搬到包的 actions.py：載入時登記 TASKS）
from . import story_base
# figure_acts（全部拆包第 31 批）：大勢人物的行動（挑戰本人、護衛犒軍探望、盤算、月旦評、管理者救回人物）的 14 個一行委派
from .features.figure_acts import plan_actions as figure_plan_actions  # 過渡：Game 上盤算的 3 個一行委派
# checkin（全部拆包第 30 批）：每日簽到的 3 個一行委派
# military（全部拆包第 33 批）：第 3、4 階行動的選項 id 前綴搬進核心的共用的字（軍情包的選單產生它、Verb 認它，第 57 批；這裡留這個名字：features/military/tests 從 engine 拿）
from .core.services import RANK_ACTION_PREFIX
# 軍令卡、押糧、第 2 階與第 3／4 階行動、席次抄帳、管理者的軍令與召見的 15 個一行委派
# territory_acts（全部拆包第 46 批）：戰書與攻城時段、22:00 換天與分紅補送、〈天下形勢〉、地盤畫面、管理者救場的 20 個一行委派
from .state import (
    ONBOARDING_VERSION, PLAYER, BattleRecord, Convoy, GameState, JournalEntry, Mingtie, Rumor,
    TierResult,
    new_game_state,
)
from .world import (
    _season_vehicle, advance_world_state, check_thresholds, evaluate_ending,
    start_pending_battle,
)
from .world_state import WorldStateStore, season_length_days
# core-events：事件檢定是核心本體（tianxia/core/event_check.py，全部拆包第 16 批）。排在上面的 import 都做完之後：那一份 import 的模組這時都已經
# 載入，載入的先後一個都不變；模組層的四個名字照名字拿回來（server、假人、測試 `from tianxia.engine import FREE_TEXT_OPTION` 照舊）
from .core import event_check  # 事件檢定的本體（Game 上留一行委派）
from .core import presence  # 「此地還有」的判斷與身分字（全部拆包第 37 批：從 social 拆進核心）
from .core import signature_base  # 本命兵器的名字照內容讀（core_seams，全部拆包第 55 批：清失效參照 signature 那一格；原本經舊名 signature_arms 讀）
from .core import smith_base  # 打造單子讀的那一小半（全部拆包第 40 批，第 41 批 PM 認定第 4 條：choose 併成一則、讀檔與 sync 清單子，不經舊名 smithing）
# peers（全部拆包第 37 批）：玩家卡、邀請框、打招呼、贈物、名帖的 31 個方法搬進玩家互動包，Game 留 21 個一行委派（另加月旦評那一句）；
# 名帖遞帖的登記（mingtie_card）改在包載入時做；原本那兩行 invites、social 的 import 是切磋、論武還在原位用的，第 38 批搬進包之後沒人用，拿掉了
# peers2（全部拆包第 38 批）：切磋、論武、截殺的 28 個方法搬進玩家互動包；Game 留 13 個一行委派（論武 4、截殺 9；切磋沒有外面的呼叫端）
from .features.peers.invite_actions import INVITE_LAPSED, INVITE_LAPSED_AWAY  # noqa: F401  邀請沒成局的兩句：tianxia/features/peers/tests/test_discuss.py 從 engine 拿
from .core import arena_ranks, duel_base  # 擂台的名次與稱號、單挑底層（全部拆包第 12 批：留核心；擂台、頭目戰本身在單挑包）
from .core.event_check import EVIL_ANNAL, FREE_TEXT_OPTION, FreeTextOutcome, FreeTextRequest

HOUR = 3600
DAY = 86400
BULLETIN_MAX = 3  # 江湖頁那排小標「大事」點開的面板最多放這一週的幾則大事（計畫 T2；以前是公告卡）
SOCIAL_LIST_TITLE = "交友"  # 待 joy 潤：一類一顆的交友打開的人物名單（FB-421）
# （SECT_LABEL：拜入門派那一顆的字，全部拆包第 35 批搬進陣營包 features/faction/join_actions.py）
SUMMONS_LABEL = "應召晉升（召見在此・不花體力）"  # 待 joy 潤：一類一顆的應召（設計 9.1 第 1 組乙，橫幅上的字）
GENDER_SET = "往後江湖上以{word}相稱。"  # 設定頁選了性別（只能選一次）
GENDER_LOCKED = "性別已經定了，改不了。"

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


def _points(lines: list[str]) -> int:
    """heal_fraction 回的「氣血 +N」那一行的 N：功效演出句的括號（FB-084）寫的跟戰報上那一行是同一個數，不另外算一份。"""
    return next((int(m.removeprefix("氣血 +")) for m in lines if m.startswith("氣血 +")), 0)


LOW_HP_RATIO = 0.3  # 開打前氣血剩上限的三成以下（含）算「氣血見底」：厚的那一句「氣血見底，……硬撐」（battlelog.LOW_HP_MARKS）才挑得到

# （RANK_ACTION_PREFIX 搬進核心的共用的字 core/services.py，全部拆包第 33 批；上面 import 回來，`from tianxia.engine import RANK_ACTION_PREFIX` 照舊）
# （FREE_TEXT_OPTION、EVIL_ANNAL 與 FreeTextRequest、FreeTextOutcome 搬進核心的事件檢定 tianxia/core/event_check.py，全部拆包第 16 批；
# 上面 import 回來，`from tianxia.engine import FREE_TEXT_OPTION` 照舊拿得到）
# （SAY_OPTION、PLAN_OPTION、ROAD_SAY、TEXT_TALKS、SAY_MAX、say_text 搬進核心的共用的字與小函式 tianxia/core/services.py，全部拆包第 20 批；
# 上面 import 回來，`from tianxia.engine import SAY_OPTION` 照舊拿得到）
DUEL_FLEE = "duel:flee"  # 頭目戰的抽身退走（整季機器人不按它：bot.pick）
ARENA_YIELD = "arena:yield"  # 擂台的認輸下台（整季機器人不按它：bot.pick）；寫字面（＝ features/bout/arena_rules.YIELD_ID）：單挑搬成包之後模組層不碰包
# （RAID_AFTER_CLASH、RAID_SHIELD_CLASH 隨截殺搬進玩家互動包 raid_actions.py，全部拆包第 38 批）


# （管理者「立刻發軍令」「立刻輪替席次」回話用的 ADMIN_REISSUE_*、ADMIN_ROTATE_* 五個常數，全部拆包第 33 批搬進 tianxia/features/military/admin_actions.py）


# （RaidSpoils 全部拆包第 39 批搬進 tianxia/core/services.py；上面 import 回來，`from tianxia.engine import RaidSpoils` 照舊是同一個類別）
# （管理者給的伏筆片段、機緣線索在玩家江湖紀錄裡的標題 HEARD_TITLE，全部拆包第 34 批搬進 tianxia/features/military/opp_actions.py）
# 等模型判讀的時候選項沒了（另一個分頁把人帶走、事件被了結、體力花光）：這一仗不打，回這一句話代替一句看不出所以然的「無法這麼做」
FIGHT_LEFT = "你離開了，這一仗沒打成。"
FIGHT_CHANGED = "情勢變了，這一仗沒打成。"
FIGHT_GONE_LINES = (FIGHT_LEFT, FIGHT_CHANGED)


class Refused(list):
    """choose() 回的話，而且這一下是被擋下來的：懸賞選項已經不在選單上（兩個分頁搶同一張，FB-162）、馬市的鈕已經灰掉（FB-195）。沒做事、沒寫江湖紀錄，
    所以伺服器要把這句話直接傳去網頁跳提示（server.api_choose 看 isinstance）。是 list 的子類，其他地方照一般的訊息清單用。
    不放在 Game 的欄位裡：同一個角色的兩個分頁共用同一個 Game，鎖放掉之後別的請求可能已經改掉欄位；回傳值跟著這一次請求走。"""


# 賽季籌備中的 PREPARING_TEXT、PREPARING_REFUSAL（全部拆包第 24 批）與裝飾器 _not_while_preparing（第 23 批）搬進核心的共用的字與小函式
# （tianxia/core/services.py）：上面 import 回來，`from tianxia.engine import PREPARING_REFUSAL` 照舊拿得到
GROWTH_PREFIX = "growth:"  # 開季準備卡上挑成長配比的鈕（growth:<配比>；growth:custom 只打開自己配的那一塊）
GROWTH_LOCKED = "這一季的成長配比已經定了，下一季開季再挑。"
GROWTH_CUSTOM_ASK = "（在卡上自己配五項，配好按「定下來」。）"
# 測試期間一鍵補滿體力（Config.beta_free_refill，企劃者 2026-10-07）。以下四句與鈕上的字（Config.beta_free_refill_label）全是新寫的，待 joy 潤：
REFILL_TITLE = "補滿體力"  # 江湖紀錄那一則的標題（joy 的丹是「服下回體丹」）
REFILL_LINE = "你運了口氣，體力回滿了。"  # 補滿成功時寫進紀錄的那一句
REFILL_FULL = "體力是滿的，用不著補。"  # 體力本來就是滿的：跟丹的「這時候服丹是糟蹋」一樣，只回一句話、不寫紀錄
PROLOGUE_REST = "調息（照師父教的吐納，把體力調回來）"  # 序章教體力那一步（打坐 2026-10-12 拿掉，只留這一下）
PILL_DAY_FULL = "今天已服{n}顆，明日 00:00 後再服。"  # 回體丹一天的上限（企劃者 2026-10-12）
CN_COUNTS = {1: "一", 2: "兩", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}


def _cn_count(n: int) -> str:
    return CN_COUNTS.get(n, str(n))


REFILL_HUT = "草廬裡先照師父說的做，體力等出了草廬再補。"  # 序章裡不能補（序章的體力是照步驟算好的），跟丹的「出了草廬再吃」同一個道理


# 頭目戰放手一搏鎖外評估的單子 DuelTextRequest 搬進單挑包（features/bout/duel_rules.py，全部拆包第 12 批）

ONBOARD_SEGMENT = 4  # 初入江湖上線的版本章（ONBOARDING_VERSION 升到 4 的那一版）：比它小、已經走出草廬的存檔讀檔時蓋成引導走完
ONBOARD_SEVEN = 5  # 新手引導重做（老周七步、草廬第 7 步改服丹）的版本章：章是 4 的存檔讀檔時照 prologue.seven_step 換步數
SHOP_ACTS = frozenset({"smith", "bounties", "market", "arena"})  # 初入江湖「進城裡的鋪子看看」認的幾間（act:<這些>）
# 出店的那一顆。酒肆的寫字面（＝ features/tavern/rules.BACK_ID）：酒肆搬成包之後模組層不碰包（主動搬六包第 10 批）；擂台同
# （＝ features/bout/arena_rules.BACK_ID，全部拆包第 12 批）
LEAVE_SHOP_IDS = frozenset({"bounty:back", "smith:back", mounts.BACK, "arena:back", "tavern:back"})
# （叛投 after 位置的 leave_behind 那一格：全部拆包第 35 批改由陣營包登記〔FactionFeature.defection()〕，原本核心代叫的 _DEFECT_AFTER_CORE 拿掉；食言〔parley〕是人物情誼包登記的）
# core_eventbus（全部拆包第 26 批）：事件的格由核心代叫的那幾格（還沒成包的舊模組）。BUS_ORDER 在 core/features.py；契約測試讀這一份。
# 懸賞的五格（win、outing、explore、arrive、raid_win 的 bounties）與第 45 批開的 aid 全部拆包第 45 批由懸賞榜包登記（BountiesFeature.bus()），每一列都空了留 {}
# 玉璽的兩格（outing、battle_end 的 seal）全部拆包第 27 批改由玉璽包登記（SealFeature.bus()）；battle_end 那一列空了留 {}（契約鎖 keys 跟 BUS_ORDER 一樣）
_BUS_CORE: dict[str, dict[str, Callable[..., Any]]] = {
    "win": {},
    "outing": {},
    "explore": {},
    "arrive": {},
    "raid_win": {},
    "aid": {},
    "battle_end": {},
}

# core_seams（全部拆包第 55 批「補算與換季收接縫」；計畫 docs/superpowers/plans/2026-11-06-補算換季收接縫-第55批.md 一、三、六）：補算與換季由核心代叫的格
# （還沒成包的舊模組與核心自己的段；包登記的在各包的 seams()，要用 sync 區域變數的兩格在 Game._sync_core）。SEAM_ORDER 在 core/features.py；契約測試讀這一份。
# 格裡一律在叫的那一下才照模組屬性或 ctx 找（monkeypatch 照樣有效）。


def _deliver_plans(ctx: Game) -> None:
    settled = plans.deliver(ctx.state, ctx.content)  # 世界活起來：我插過手的盤算有了結果
    if settled:
        ctx._write(plans.TITLE, settled)


def _deliver_summons(ctx: Game) -> list[str]:
    summons = ranks.check_summons(ctx.state, ctx.content)  # 行動之外記到的貢獻（抵達、別人觸發的結算）：同步時補發召見（計畫 T5）
    if summons:
        ctx._write("召見", summons)
    return summons


def _drop_resting(ctx: Game) -> None:
    ctx.state.player.resting_since = None  # 打坐 2026-10-12 拿掉了：存檔時坐著的人讀檔就起身（只是不再回得比較快，沒有別的帳要算）


def _carry_ties(ctx: Game, old: GameState, fresh: GameState) -> None:
    """換季照帶：跟人的交情（self.state 這時候還是舊的：只准讀 old、fresh、ctx.content；self、rack 同）。"""
    fresh.player.renown_told = old.player.renown_told  # 名聲：兩個稱號說明過了就不再說（段 renown_seen 跟角色一起重來）
    ratio = ctx.content.config.affinity_carry_ratio
    fresh.player.affinities = {key: int(value * ratio) for key, value in old.player.affinities.items()}
    # 上一季的交情另外留著（這一季的關係從頭寫），好感度只剩一成時提示才不會說「親如兄弟」（正式版辛）；
    # 這一季沒聊過的人物留著更早的那一句
    fresh.player.past_notes = {**old.player.past_notes, **old.player.relationship_notes}


def _carry_self(ctx: Game, old: GameState, fresh: GameState) -> None:
    """換季照帶：角色自己的（身分、性別、回體丹與幾個「一天幾次」，沒有人認領的）。排在 guide 後面：stamina_pills 照蓋。"""
    fresh.player.bot = old.player.bot  # 伺服器假人的身分與作息跨季保留
    fresh.player.gender, fresh.player.gender_chosen = old.player.gender, old.player.gender_chosen  # 性別跨季保留
    fresh.player.stamina_pills = old.player.stamina_pills  # 回體丹是建角色時送的，換季不再送，剩下的帶著走
    fresh.player.pills_topped_to = old.player.pills_topped_to  # 補過的不再補（第二季起建的角色在這裡還沒拿贈送）
    fresh.player.pill_day, fresh.player.pills_today = old.player.pill_day, old.player.pills_today  # 換季不能多吃一輪
    fresh.player.drill_day, fresh.player.drills_today = old.player.drill_day, old.player.drills_today  # 換季不能多操練一輪
    fresh.player.upgrade_day, fresh.player.upgrades_today = old.player.upgrade_day, old.player.upgrades_today  # 換季不能多升一輪三階
    fresh.player.seen_real = old.player.seen_real


def _carry_rack(ctx: Game, old: GameState, fresh: GameState) -> None:
    """換季照帶：神器輪替與收集（正式季整合 5.8）：輪替季打的神器（collected）跨季帶走、放進裝備庫，以器配招清掉，品質淬煉磨損照舊；
    帶了東西過來流水號才接著走（帶過來的 id 不會跟新打的撞；沒帶的照上線前重來，FB-401）；鑄譜上打中過的神器記得（forge_secrets.divine_solved）。
    排在 guide 後面：讀 fresh 的裝備庫（forge_secrets 是共用層，rack、weapon_serial、divine_solved 沒人認領）。"""
    carried = [item for item in forge_secrets.owned_gear(old.player) if item.collected and item.signature is None]
    for item in carried:
        item.bound_art = None
    fresh.player.rack = carried + fresh.player.rack
    if carried:
        fresh.player.weapon_serial = max(fresh.player.weapon_serial, old.player.weapon_serial)
    fresh.player.divine_solved = dict(old.player.divine_solved)


_SEAM_CORE: dict[str, dict[str, Callable[..., Any]]] = {
    "sync.close": {
        # 搬成包的店（店面登記，第 11 批；酒肆，與全部拆包第 12 批的擂台〔擂台關了、季收了〕）：關了、人被挪走了就收起來（接在舊的五間店後面）
        # （picking_donate、picking_dadian：全部拆包第 43 批換成銀兩出口包的店面登記，這裡收）
        "shops": lambda ctx: features_core.drop_shops(ctx),
    },
    "sync.deliver": {
        "big_events": lambda ctx: ctx._deliver_big_events(),  # 這一季的時刻表大事人人有份：沒看過的補上，推進的人也走這一條（FB-038）
        # 收場補送（接縫掛鉤，第 11 批）：決戰包——先補場上沒有份量快照的自己（上線前就在決戰裡；排程的 world_tick 不走這裡。原本是緊接著的
        # 前一行，全部拆包第 8 批併進這一格），再補下線時收場的決戰，回來第一次同步就補上（休季、籌備中也一樣，FB-027）；玉璽包接著補
        # 碎片的事：現世、單挑收場、隱沒（5.9），下線時發生的回來補（原本緊接著的下一行 _deliver_seal_results，全部拆包第 27 批併進這一格）
        "results": lambda ctx: features_core.deliver_results(ctx),
        "echoes": lambda ctx: ctx._deliver_echoes(),  # 別人照著你首創的配方合了出來：補名望（首創名望回饋）
        # 別人捎來的（接縫掛鉤，第 11 批）：酒肆包——風聲（有人在酒肆打聽你）、自己雇的殺手得手失手或到期退錢、託酒家留意的人有了準信或到期
        "notices": lambda ctx: features_core.deliver_notices(ctx),
        "marks": lambda ctx: ctx._marks_tick(),  # 減法季批 4：痕跡過門檻的防漏、替自己記出過力的行狀（關著什麼都不做）
        "plans": _deliver_plans,
        "summons": _deliver_summons,
    },
    # 到時的結算（接縫掛鉤，第 11 批；出陣包的約戰：快轉不動現實時刻，窗照現實時間；快轉到季末時還沒打的作廢、退次數）
    "advance.turn": {"due": lambda ctx: features_core.on_due(ctx)},
    "season.carry": {"ties": _carry_ties, "self": _carry_self, "rack": _carry_rack},
    "stale.early": {"resting": _drop_resting},
    "stale.mid": {
        # （picking_donate、picking_dadian：捐軍備關了、人不在大本營了、銀兩出口這裡一樣都做不了了，全部拆包第 43 批換成銀兩出口包的店面登記，這裡收）
        # 搬成包的店（店面登記，第 11 批；酒肆，與全部拆包第 12 批的擂台〔擂台關了、季收了〕）：關了、人不在那裡了就收起來（接在舊的五間店後面）
        "shops": lambda ctx: features_core.drop_shops(ctx),
        # 寶物、名駒的名字照內容讀（裝備四欄 3.1）：joy 改了名字，存檔裡的跟著改；內容拿掉了留著舊名字
        "treasures": lambda ctx: treasures.refresh_names(ctx.state.player, ctx.content),
        # 名器的名字照內容讀（4.2）、神器的名字照全服那一列讀（5.2、5.3：原品定了名，仿品跟著改）
        "forge": lambda ctx: forge_secrets.refresh_names(ctx.state.player, ctx.content, ctx.world),
        # 本命兵器的名字照內容讀（打造第三批）：joy 改了名，手上的跟著改
        "signature": lambda ctx: signature_base.refresh_names(ctx.state.player, ctx.content),
    },
}

# core_seams（全部拆包第 56 批「選單收接縫」；計畫 docs/superpowers/plans/2026-11-06-選單收接縫-第56批.md 一、三）：選單由核心代叫的格（店面登記、act 子動詞、應召、療傷、序章的調息與體力玩法那一串；
# 包登記的在各包的 menus()）。MENU_ORDER 在 core/features.py；契約測試讀這一份。格裡一律在叫的那一下才照模組屬性或 ctx 找（monkeypatch 照樣有效）。


def _here_explore(ctx: Game, loc: Location, cost: dict[str, int], odds: bool) -> list[Option]:
    """探索那一格（act 子動詞的主人，接縫掛鉤，第 11 批）：探索包——減法季探索一顆（整合設計 4.1）開著時只剩那一顆「探索」；探索包沒接走（序章、test 內容）是舊探索那一顆。"""
    cell = features_core.act_cell(ctx, "explore", loc, cost["explore"], odds)
    return cell if cell is not None else [ctx._cost_option("act:explore", "探索", cost["explore"])]


def _here_train(ctx: Game, loc: Location, cost: dict[str, int], odds: bool) -> list[Option]:
    """出陣那一格（act 子動詞的主人，接縫掛鉤，第 11 批）：出陣包——整格是它的（第 17 批起連地盤關著的舊遊歷一起：序章的雪恥、出陣、散人與不在爭奪之列的灰格、舊遊歷；
    出陣探索與地盤設計第二節、FB-250、裁決 18）；接了一顆都沒有是 []。"""
    return features_core.act_cell(ctx, "train", loc, cost["train"], odds) or []


def _here_summons(ctx: Game, loc: Location, cost: dict[str, int], odds: bool) -> list[Option]:
    """晉升奇遇（計畫 T5）：人在召見的地點才有，不花體力。一類一顆開著時網頁畫成行動列上面一條金框橫幅（設計 9.1 第 1 組乙），鈕上寫它自己的名字與一行小字。"""
    s, c = ctx.state, ctx.content
    if ranks.summons_event(s, c) is None:
        return []
    return [Option(id="act:summons", label=SUMMONS_LABEL if precise.on(c, s.world) else "應召")]


def _here_heal(ctx: Game, loc: Location, cost: dict[str, int], odds: bool) -> list[Option]:
    heal = ctx._heal_option()
    return [] if heal is None else [heal]


def _here_rest(ctx: Game, loc: Location, cost: dict[str, int], odds: bool) -> list[Option]:
    """打坐 2026-10-12 拿掉了（企劃者）；只剩序章教體力那一步的調息，一下回滿。"""
    return [Option(id="act:rest", label=PROLOGUE_REST)] if prologue_rules.instant_rest(ctx.state, ctx.content) else []


_MENU_CORE: dict[str, dict[str, Callable[..., Any]]] = {
    "take": {
        # 功能包此刻接管整個選單（開發規範手冊 3.3）：坐在宴席上的敬酒詞與離席（宴客包）、擂台打到一半的三招與認輸（單挑包）；放手一搏同頭目戰走輸入框
        "menu": lambda ctx: features_core.menu(ctx),
        # 坐在搬成包的店裡（店面登記，第 11 批；酒肆，企劃者 2026-10-18；擂台邊，全部拆包第 12 批；軍需官、打點，第 43 批）：選單整個是那間店的
        "shops": lambda ctx: features_core.shop_menu(ctx),
    },
    "here": {
        "explore": _here_explore,
        "train": _here_train,
        "summons": _here_summons,
        # 搬成包的店的入口（店面登記，第 11 批；酒肆：帶「酒肆」標籤的城鎮，只是打開酒肆，不花體力；擂台：哪裡都有，全部拆包第 12 批）
        "shops": lambda ctx, loc, cost, odds: features_core.shop_entries(ctx),
        "plays": lambda ctx, loc, cost, odds: ctx._stamina_play_options(),  # 後期體力玩法：設伏劫道、屯糧練兵、護衛、包的選項、盤算
        "heal": _here_heal,
        "rest": _here_rest,
    },
    "plays": {"options": lambda ctx: features_core.options(ctx)},
    "open": {"shops": lambda ctx: features_core.shop_open(ctx)},  # 店面登記的店（坐在店裡、這裡也還開著）
}

# （走一趟的裝飾器 _outing_watch 搬進核心〔tianxia/core/services.py 的 outing_watch，全部拆包第 24 批〕：上面 import 回來，同一個名字）


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
        self._flavor_jobs: list[FlavorJob] = []  # 這一份 Game 觸發、還沒潤色的江湖大事（S-09，見 _flavor_sink、take_flavor_jobs）
        self._preparing_memo: list[bool] | None = None  # 一次畫面建構裡記住的「籌備中嗎」；None＝不在範圍裡（見 phase_memo）
        self._draft: Draft | None = None  # choose() 進行中那次行動的江湖紀錄草稿
        self._outing_busy = False  # 走一趟正在走（outing_actions.outing_walk）或正在記一件事選完的得失（_outing_watched）：不再套一層
        self._loot_scale = 1.0  # 打贏的心得與銀兩倍數：探索包遭遇那一場（城裡的地痞 town_loot_scale）才不是 1
        # 減法季探索一顆（批 2）：遭遇拍那一場掉的素材打幾成（城裡的地痞 town_loot_scale、三道閘的倍數）；其餘的仗都是 1，一個字不變
        self._drop_scale = 1.0
        self._gate_scale = 1.0  # 減法季三道閘（批 2）：遭遇拍那一場的經驗、心得、銀兩乘疲勞與對手兩道閘（explore_actions.fight_gate）；其餘是 1
        self._outing_close: set[str] = set()  # 這一趟出門打了折的那幾道閘（explore_actions.fight_gate 記、explore_one 寫段落結尾那一句）
        self._beat: dict | None = None  # 走一趟：剛剛那一次探索抽到什麼（explore_actions.explore_one 寫、outing_actions.outing_walk 讀）
        self._outing_upset = False  # 走一趟這一場遭遇開打前勝算凶險以下（_outing_fight 寫、探索包的 explore_one 讀）
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
        self.last_gamble: FreeTextOutcome | None = None  # 上一次 answer_event 擲完骰的結果（server.py 拿去潤色）
        self.smith_result: dict | None = None  # 上一次 smith_forge 的出爐卡（server 的 /api/do/smith_forge 回給網頁）；被拒絕是 None
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

    def _flavor_sink(self) -> list[FlavorJob] | None:
        """江湖大事的潤色單子記在哪（S-09，world._fire）：有 client 才記（伺服器在行動鎖外請模型，見 server.write_flavor）；
        沒有 client（伺服器假人：bot_runner 把 game.client 設成 None；測試與腳本）回 None，一張都不記、一個模型都不叫。"""
        return self._flavor_jobs if self.client is not None else None

    def take_flavor_jobs(self) -> list[FlavorJob]:
        """三段式的 A 段（行動鎖內）：拿走等著潤色的江湖大事，全服快取裡已經有合格句子的（別人先潤色好了）先套上、不再請模型。"""
        jobs, self._flavor_jobs = self._flavor_jobs, []
        waiting: list[FlavorJob] = []
        for job in jobs:
            if not self.apply_flavor(job, ""):
                waiting.append(job)
        return waiting

    def apply_flavor(self, job: FlavorJob, flourish: str) -> bool:
        """三段式的 C 段（行動鎖內）：模型寫回的那一句再驗一次（flavor.clean），合格就存進全服快取（先寫的為準）、記一則天下大事，
        再把這個人江湖紀錄與原始訊息裡那一則固定的原文換成潤色過的（全服共用的那一句）。快取裡沒有合格句子就什麼都不動，回 False。
        呼叫端存檔。"""
        line = flavor.clean(flourish)
        if line and not flavor.clean(self.world.get_event_flavor(job.fire_id) or ""):
            self.world.set_event_flavor(job.fire_id, line)
            # 這一下才存進快取的（先寫的為準，別人先潤色好的那一句由他那一下記）：也進天下大事，全服看得到（Joy 2026-10-31）
            self.world.mutate_season(lambda season: add_season_rumor(season, line, job.location, content=self.content))
        shared = flavor.clean(self.world.get_event_flavor(job.fire_id) or "")
        if not shared:
            return False
        polished = f"{job.text}\n\n{shared}"
        swap = {job.text: polished, f"【江湖大事】{job.text}": f"【江湖大事】{polished}"}
        s = self.state
        s.log[:] = [swap.get(m, m) for m in s.log]
        for entry in s.journal:
            entry.tag = swap.get(entry.tag, entry.tag)
            entry.lines = [swap.get(m, m) for m in entry.lines]
        return True

    def reset_model_budget(self) -> None:
        """新的一次拿鎖：鎖內的模型呼叫重新有額度（見 _quick_client）。server._locked 與 bot_runner._bot_game 每次拿到行動鎖先呼叫。"""
        self._model_budget.gave_up = False
        self._flavor_jobs = []  # 上一次拿鎖留下的潤色單子（動作丟例外、整筆撤回的那一下）不算數

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
        if (prologue or graduated) and game._opening_on():
            # 減法季的開局第一分鐘（整合設計 6.7）：真人與假人都不進草廬，站在起點看旁白、三選一；人物的信在選完那一下送到（choose）
            game._opening_begin()
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
            if attrset.on(content, game.state.world) and game.state.player.growth_preset is None:
                # 序章算走過：五項屬性的季序章那一步就是挑配比，照預設那一套（開季準備卡是給網頁上建的真人與換季的人看的）
                game.state.player.growth_preset = content.config.attributes.v2.default_preset
        p = game.state.player
        p.visited.add(p.location)
        gift = content.config.beta_gift and content.config.beta_gift_stamina_pills > 0
        if gift:  # 內測贈送（企劃者 2026-10-07）：真人、假人、整季機器人建角色時一樣拿到
            p.stamina_pills += content.config.beta_gift_stamina_pills
        game._log(
            [f"══ {content.scenario.name} ══", content.scenario.intro, game.location_text()]
            + game._tutorial_intro()
        )
        if not game.state.journal:  # 第二季起建的角色：__init__ 的換季重來已經寫了開場那一則，不再寫一次（FB-052）
            game._write(content.scenario.name, [content.scenario.intro], tag=journal.SEASON_START, guide=game._tutorial_intro())
        if gift:
            game._note_gift()
        return game

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
        self._write(cfg.stamina_pill_name, [self._top_up_line(added)])

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
        之後新增的 PlayerState 欄位預設就跟著新角色重來；要跨季保留的才加進 SEAM_ORDER["season.carry"] 自己那一格（第 55 批）。"""
        old = self.state
        past = self._zhuan_past(old)  # 列傳為終點（減法季批 7b）：收季之後沒回來過的人，存之前補季末論功與〈天下形勢〉
        self._story_close_season(old)  # 一條線：還沒收的寫「此事未了」進傳（休季時同步過的已經寫了；一條線包，第 30 批：要在 save_annals 之前，接不了 on_season_end）
        if old.player.annals:  # 行狀跟著角色重來：先把上一季的存起來，季末的傳照它寫（玩家傳）
            self.world.save_annals(
                old.player.season_number, old.player.name, [e.model_dump() for e in old.player.annals],
                self._zhuan_profile(old, past),
            )
        features_core.on_season_end(self)  # 功能包：舊的那一季要丟之前（self.state 還是舊的；開發規範手冊 3.3）
        fresh = new_game_state(self.content, old.player.name)
        fresh.last_real = old.last_real
        # 照帶的欄位（core_seams，全部拆包第 55 批：包登記自己那一格，都是照抄、不看開關；self.state 這時候還是舊的）
        features_core.seam_run("season.carry", _SEAM_CORE["season.carry"], self, old, fresh)
        fresh.player.season_number = season_number
        self.state = fresh
        self.state.world = self.world.get_season()  # 開場那一則記此刻的季時間（FB-052：以前記成新存檔的 0）
        self.state.player.visited.add(self.state.player.location)
        features_core.on_season_start(self, old)  # 功能包：新的存檔接上了、開場那一則之前（old 是上一季的）
        self._write(
            self.content.scenario.name, [self.content.scenario.intro], tag=journal.SEASON_START, guide=self._tutorial_intro(),
        )
        features_core.seam_run("season.grant", {}, self, old)

    def _drop_stale_references(self) -> None:
        """內容檔改版後，舊存檔可能引用已刪除的事件、地點、武學或人物；丟掉這些引用以免當機。"""
        # 入伍段上線之前就投靠了的老手蓋成走完（設計 7.2）：要在換季之前，換季會把陣營清掉、之後就認不出他是老手
        features_core.seam_run("stale.first", {}, self)
        self._reconcile_season()
        s, c = self.state, self.content
        p = s.player
        for key in team.COMBAT_STATS:  # 舊存檔沒有後來加的屬性（博聞，武學與成長設計 6.3）：照開局的數字補上
            p.stats.setdefault(key, c.config.start_stats.get(key, team.BASE_STAT))
        if s.pending_event and s.pending_event not in c.events:
            s.pending_event = None
        self._top_up_pills()
        features_core.seam_run("stale.early", _SEAM_CORE["stale.early"], self)  # 追風步的舊品質、起身、有所感的場景、舊的同伴確認
        # 投靠、改依附、叛投還在確認畫面上而陣營被拿掉了：第 35 批改接陣營包的 on_drop_stale 掛鉤（下面 features_core.on_drop_stale；中間沒有任何一行讀這三個欄位）
        lost_place = p.location not in c.locations
        if lost_place:
            p.location = c.scenario.start_location
        features_core.seam_run("stale.mid", _SEAM_CORE["stale.mid"], self)  # 收懸賞榜、鐵匠鋪、馬市與別的店，寶物與神兵的名字，玉璽碎片的抄本
        features_core.seam_run("stale.road", {}, self, lost_place)  # 路上那一段不在了、小事與見聞
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
        # 自創的舊三步單子收掉（還沒付錢；create.prune）：全部拆包第 44 批改接煉製包的 on_drop_stale 掛鉤（下面 features_core.on_drop_stale）
        if p.naming is not None and (p.naming not in owned or self.world.master_of(p.naming) != p.name):
            p.naming = None
        # 伏筆：內容改版後拿掉的鏈與物品（第 34 批改接軍情包的 on_drop_stale 掛鉤，下面 features_core.on_drop_stale）
        features_core.seam_run("stale.late", {}, self)  # 內容改版拿掉的大勢人物（T4）
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
        for i, rumor in enumerate(s.world.rumors):  # 換成一份新的、不就地改：讀回來的傳聞跟別的讀取共用（sqlite_world._logs）
            if rumor.location is not None and rumor.location not in c.locations:
                s.world.rumors[i] = rumor.model_copy(update={"location": None})
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
        features_core.on_due(self)  # 到時的結算（接縫掛鉤，第 11 批；出陣包：窗滿了的約戰沒人在線也照時結算，關著、沒有到時的什麼都不做、不寫）
        msgs += features_core.seam_lines("tick", {}, self)  # 領地爭奪：22:00 沒人在線也照時換天；推一次決戰；奪璽單挑
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
        # 到時的結算（接縫掛鉤，第 11 批）：排程關著（或還沒輪到）時，下一個同步的人替窗滿了的約戰結算（出陣包；只往前走、手上這一份季
        # 剛讀回來，結算改的進度當場存）
        features_core.on_due(self)
        self._stamp_join()  # 新角色、換季重來的角色：補算完賽季才記下加入的那一刻
        self._week_unlock_tick()  # 減法季 6.6：第 2 週的功能對這個人開了的那一刻，寫一則紀錄
        self._record_faction()
        features_core.seam_run("sync.heirloom", {}, self)  # 玉璽碎片的抄本，排在 _advance_player_local 之前：承露照整段離線時間算體力回復（7.4）
        elapsed = 0.0  # 這一次補算的自己的秒數（功能包的 on_sync 拿它）
        if self.state.last_real is None:
            self.state.last_real = now
        else:
            elapsed = max(0.0, now - self.state.last_real) * self.content.config.time_scale
            self.state.last_real = now
            msgs += self._advance_player_local(elapsed)
            # 下線那一段（接縫掛鉤，第 11 批）：酒肆包——離線夠久，殺手找上門（站在城外下線的人）；戰報與紀錄自己寫，不併進江湖大事
            features_core.on_away(self, away_from)
        # 開關關了、人被挪走了就收店（鐵匠鋪、馬市、店面登記的那幾間）、守著的埋伏到時刻了收起來；
        # 抵達的站自己寫一則江湖紀錄（途中觸發的大事也寫在那裡），不併進下面的「江湖大事」
        arrived = features_core.seam_lines("sync.close", _SEAM_CORE["sync.close"], self)
        if arrived:
            self._save_season()  # 抵達時觸發的大勢門檻改了共用賽季
        news = journal.news_entry(self.state.world.time, self._without_timetable(msgs))
        if news is not None:
            journal.add_entry(self.state, news, merge=True)
        # 補送到席次（core_seams：先後就是江湖紀錄的先後，寫死在 SEAM_ORDER）。回話依序是密謀、召見、席次（盤算那一格寫完就丟）
        delivered = features_core.seam_lines("sync.deliver", {**_SEAM_CORE["sync.deliver"], **self._sync_core(elapsed, away_from)}, self)
        # 名聲：同步時發現的跨段另起一則「名聲」（設計 3.3）；這一次補進來的那幾則接差距
        self._renown_after(synced=True, fresh=[e for e in self.state.journal if id(e) not in before])
        self._deliver_away(away_from)  # 最後寫：江湖頁的「剛剛」先放這一份摘要（要跟別的計畫合併時，這一行維持在 return 的前一句）
        return self._log(msgs + arrived + delivered)

    def _sync_core(self, elapsed: float, away_from: float | None) -> dict[str, Callable[..., Any]]:
        """sync.deliver 裡要用 sync 區域變數的兩格（core_seams，全部拆包第 55 批；其餘核心代叫的格在模組層 _SEAM_CORE）。"""

        def day(ctx: Game) -> None:
            # 功能包：回體丹那一天換了（台灣 00:00；上一次同步之後第一次）。同 _pill_day 照現實時間加快轉推過的那一截（advanced_real）比：
            # 快轉跨過的那一次 advance 自己報過了，這裡只比上一次同步到這一次同步那一段
            if away_from is None or ctx._day_of(away_from + ctx.advanced_real) != ctx._pill_day():
                features_core.on_day(ctx)

        def on_sync(ctx: Game) -> None:
            features_core.on_sync(ctx, elapsed)  # 功能包的補算（開發規範手冊 3.3；宴客：散席時席間最佳補名望、宴散了收起敬酒的選單）

        return {"day": day, "on_sync": on_sync}

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
        gazette = rumor_view.gazette_on(c)  # 世界活起來第二批：上線邸報（你去過的地方、你認識的人、誰提起了你）；關著照舊那一長串
        lines, total = (rumor_view.gazette_lines if gazette else rumor_view.away_lines)(s, c, since, self.stamp)
        if lines:
            tag = rumor_view.AWAY_TAG.format(n=total)
            title = journal.GAZETTE if gazette else journal.AWAY
            journal.add_entry(s, JournalEntry(time=s.world.time, title=title, tag=tag, lines=lines))

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
        arrived = features_core.seam_lines("advance.arrive", {}, self)  # 同 sync：抵達自己寫紀錄
        # 領地爭奪：快轉跨過 22:00 也換天（下面一起存）；同 sync：快轉（與只 advance 的整季機器人）也補翻地的分紅；到時的結算
        msgs += features_core.seam_lines("advance.turn", _SEAM_CORE["advance.turn"], self)
        self._save_season()
        msgs += start_pending_battle(self.world, self.content, self.now)
        self.state.world = self.world.get_season()
        self._week_unlock_tick()  # 推完了再看一次：快轉跨過第 2 週（整季機器人、測試）那一下就寫
        news = journal.news_entry(self.state.world.time, self._without_timetable(msgs))
        if news is not None:
            journal.add_entry(self.state, news, merge=True)
        self._deliver_big_events()
        features_core.seam_run("advance.held", {}, self)  # 同 sync：快轉（與只 advance 的整季機器人）也補寄放的東西
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
        have = {"arena": arena_ranks.on(c), "bounties": bounty_base.active(s, c)}
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
        """本人這一輪（mark_seen；假人程式自己那一輪也叫）：系統通緝這一週還沒掛就掛（懸賞榜包 rules.post_auto，名聲 4.6、5.4），被掛的那幾句
        寫進一則「懸賞」紀錄。結伴同行的人、管理者查玩家、玩家卡動到別人建的 Game 都不叫、不掛。
        最前面問功能包（on_own_turn，接縫掛鉤，第 11 批）：商城包的封測元寶在這裡發——錢包第一次進來的那一下，真人假人一樣；暫停中照發（帳跟世界無關）。"""
        self.own_turn = True
        features_core.on_own_turn(self)
        if self.world.paused_at() is not None:  # 賽季時鐘暫停中世界不變（線上架構 8.3）：mark_seen 在 server.act 的暫停擋之前
            return
        features_core.seam_run("own_turn", {}, self)

    # ── 心神（tianxia/core/xinshen.py；功能包經服務清單的 ctx.xinshen_purse／xinshen_spend 叫）──

    def _xinshen_card(self) -> bool:
        return xinshen.card_active(self._wallet(), self._mall_owner(), self._pill_day())

    def xinshen_purse(self) -> xinshen.Purse:
        """此刻手上的心神（免費、月卡、存著的三份）。"""
        return xinshen.purse(self.state, self.content, self._pill_day(), self._xinshen_card(), xinshen.bank(self._wallet(), self._mall_owner()))

    def xinshen_spend(self, n: int, free_only: bool = False) -> bool:
        """扣 n 點心神：一般交談先扣月卡、再扣免費、最後動存著的；free_only（女性角色的隱線）只扣免費那一份。夠就扣、回 True。"""
        wallet = self._wallet()
        from_bank = xinshen.spend(self.state, self.content, self._pill_day(), self._xinshen_card(),
                                  xinshen.bank(wallet, self._mall_owner()), n, free_only)
        if from_bank is None:
            return False
        if from_bank:
            xinshen.use_bank(wallet, self._mall_owner(), from_bank)
        return True

    def xinshen_view(self) -> dict | None:
        """狀態列的心神那一格；關著是 None。"""
        if not xinshen.on(self.content):
            return None
        return xinshen.view(self.content, self.xinshen_purse(), self._xinshen_card())

    def xinshen_asks_left(self) -> int | None:
        """今天還能問酒家幾次（心神開著才限）；不限是 None。"""
        return xinshen.asks_left(self.state, self.content, self._pill_day())

    def xinshen_note_ask(self) -> None:
        xinshen.note_ask(self.state, self.content, self._pill_day())

    def _advance_player_local(self, seconds: float) -> list[str]:
        """玩家自己的部分：體力／氣血回復、閉關出關、新立門戶福緣——
        這些是「我」的進度，不是共用賽季的一部分，照自己經過的時間算，不受共用賽季時鐘怎麼走影響。"""
        cfg, p = self.content.config, self.state.player
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
        return features_core.seam_lines("local", {}, self)  # 閉關出關、福緣到期自己送上門

    # ── 選項 ──────────────────────────────────────────────

    def options(self, odds: bool = True, tick: bool = True) -> list[Option]:
        """tick 照 _battle_status 的規則往下傳：預設 True，這個呼叫順便把全服戰鬥追趕到現實時間；
        只想讀選單、不該推進戰鬥的呼叫端（dialogue_request）傳 False——一次請求只能推進一次。"""
        if tick:
            features_core.menu_run("tick", {}, self)  # 奪璽單挑跟決戰一樣：誰輪詢誰推（5.4；玉璽包，core_seams）
        battle_status = self._battle_for_me(tick=tick)
        if self.world.paused_at() is not None:  # 賽季時鐘暫停（線上架構 8.3「擋住所有動作」）：選單只剩一顆灰的
            return [Option(id="season:paused", label=PAUSED_TEXT, enabled=False)]
        if battle_status is not None and not self._watching_battle(*battle_status):
            battle, definition = battle_status
            if not self._fighting(battle, definition):
                # 集結那段時間照常遊玩，加入的按鈕（已經加入就是灰的「已加入」）放在平常的選單前面
                # （企劃者 2026-10-03 決定，FB-009）；走出決戰的大區就照 _watching_battle 算不在場。
                # 開打了還沒投效的散人也一樣：投效的按鈕接在平常的選單前面，不把散人鎖在戰場上（這場仗本來不是他的）
                return features_core.menu_lines("front", {}, self) + self._battle_menu(battle, definition) + self._everyday_options(odds)
            battle_menu = self._battle_menu(battle, definition)
            if self.state.player.pending_defect:  # 同理：開著的叛投確認畫面不能因為開打就卡到整場打完（最終審查 Minor 1）
                battle_menu.append(Option(id="defect:cancel", label="再想想"))
            return battle_menu
        return features_core.menu_lines("front", {}, self) + self._everyday_options(odds)

    def _everyday_options(self, odds: bool) -> list[Option]:
        """平常的選單（沒有要親身參與、已經開打的決戰時；集結時接在加入的按鈕後面）：籌備或休季、事件、接管整個選單的（對話、
        投靠確認、求見名單、店……）、閉關、在路上，都不是就是在地點上能做的事。籌備、休季、事件留核心；其餘每一格的先後寫死在 core/features.py 的 MENU_ORDER
        （core_seams，全部拆包第 56 批）：take、busy、road、here，包登記自己那一格（Feature.menus()），核心代叫的在模組層 _MENU_CORE。"""
        s, c = self.state, self.content
        if self._preparing():
            return [Option(id="season:preparing", label=PREPARING_TEXT, enabled=False)]
        if s.world.ended:  # 休季：列傳為終點開著、手上有列傳的票時多幾顆用票的鈕（減法季批 7b；關著、沒票一顆不多）
            return [Option(id="season:resting", label="休季中，等待管理者開啟下一季", enabled=False)] + features_core.menu_lines("rest", {}, self)
        prep = self._season_prep()  # 開季準備（企劃者 2026-11-05）：成長配比、識海，做完才能做別的事；排在事件（開局三選一）前面
        if prep is not None:
            return prep
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
                    ok = renown.open_to(s, c, "choices", ch.needs.path, ch.needs.tier)  # 傳承的門路也開得了第一段
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
        taken = features_core.menu_first("take", _MENU_CORE["take"], self)  # 此刻接管整個選單的（空的也算：髒存檔的待確認畫面真的是空選單）
        if taken is not None:
            return taken
        if s.player.busy_until is not None:
            return features_core.menu_lines("busy", {}, self)  # 閉關中：提前出關；也能上擂台（PM 轉述 Joy 2026-10-14）
        j = s.player.journey
        if j is not None:
            return features_core.menu_lines("road", {}, self, j)  # 路上那一行、折返或分道揚鑣、帶路說一句、喊停、路上小事；路上也能上擂台
        opts = features_core.menu_lines("here", _MENU_CORE["here"], self, c.locations[s.player.location], self._action_costs(), odds)
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

    # ── 捐軍備、銀兩出口（搬進功能包 tianxia/features/outlets/，全部拆包第 43 批；Game 留一行委派，本體在包裡）──

    def _at_clinic_town(self) -> bool:
        """名師指點、買破境丹的地方（6.5）：帶醫館標籤的地點、不在路上（看標籤，不看 Config.heal_at_clinic：那個開關關著時哪裡都能療傷）。"""
        p = self.state.player
        return p.journey is None and clinic.CLINIC_TAG in (self.content.locations[p.location].tags or [])


    def _cost_option(self, option_id: str, label: str, cost: int, note: str = "") -> Option:
        extra = f"・{note}" if note else ""
        return Option(
            id=option_id, label=f"{label}（體力 {cost}{extra}）", enabled=self.state.player.stamina >= cost
        )

    def action_notes(self, option_ids: Iterable[str]) -> dict[str, str]:
        """江湖頁行動列底下那幾行（explain-1）：選單上的探索、遊歷、交友、求見這一下會怎樣，句子在 howto，事實照引擎的規則：
        探索的比重是擲骰用的那一份（_explore_weights），遊歷照這裡的對手與操練（出陣包 train_actions.train_line，經 act 子動詞的 Verb.note），交友照會不會直接開口談話
        （_socialize_figure）與這裡有沒有交友事件。只給 option_ids 裡有的。序章裡是空的：探索、遊歷照那一步寫好的走（草廬四景、
        斷眉），師父自己會說。只讀，不擲骰。"""
        s, c = self.state, self.content
        if prologue_rules.active(s, c):
            return {}
        ids = set(option_ids)
        loc = c.locations[s.player.location]
        notes: dict[str, str] = {}
        # 探索那一行（act 子動詞的主人，接縫掛鉤，第 11 批）：探索包——減法季探索一顆開著時寫這一處多半給什麼（比重照擲骰用的那一份）
        if "act:explore" in ids:
            explore_note = features_core.act_note(self, "explore", loc)
            if explore_note is not None:
                notes["act:explore"] = explore_note
        if "act:train" in ids:  # 出陣那一行（act 子動詞的主人，接縫掛鉤，第 11 批）：出陣包——約戰開著寫約戰那一句、出陣開著寫出陣那一行；都不是寫舊遊歷那一行（第 17 批收進包）
            train_note = features_core.act_note(self, "train", loc)
            if train_note is not None:
                notes["act:train"] = train_note
        for got in features_core.menu_run("notes", {}, self, ids, loc):  # 交友、求見那幾行（交友求見包，core_seams）；鍵的順序算行為
            notes.update(got)
        return notes

    def _insight_blocked(self, loc: Location) -> bool:
        """探索那一行的悟意境那一支，是不是只因為這個遊戲日在這裡選錯過做法才拿掉（這裡本來悟得到、比重不是 0）：是的話那一行
        句尾補一句什麼時候才悟得出（howto.explore_line）。"""
        c = self.content
        return (
            self._sense_missed(loc)
            and c.config.explore_mix_of(loc.tags).weights.get("insight", 0) > 0 and bool(insights.explore_gives(loc, c))
        )

    def _choice_label(self, choice: Choice, odds: bool) -> str:
        return event_check.choice_label_of(self, choice, odds)

    def event_option_view(self) -> dict[str, dict] | None:
        return event_check.event_option_view(self)

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

    # ── 酒肆（企劃者 2026-10-18）：本體在功能包 tianxia/features/tavern/actions.py（主動搬六包第 10 批），這裡留一行委派——server 的
    # MAIN_ACTIONS 與鎖外三段式、假人、腳本、測試，與核心原位的 shop_view（tavern_view）。選單接管那一格、act:tavern、sync 的下線殺手與
    # 三個 deliver、choose 最後那一下殺手檢查、紀錄標題第 11 批換成接縫掛鉤（酒肆包的 shops、verbs、on_away、deliver_notices、after_action）──

    # ── 大場面：鎖外請模型判讀（武學與成長設計 8.3、計畫三 Task 2）────────────

    def is_big(self, squad: Squad) -> bool:
        """大場面：對手標了頭目、是大勢人物本人（figures 的 squad），或難度到 big_fight_difficulty（武學與成長設計 8.3）。
        只看對手本身：遊歷遇上自己陣營的隊伍是操練、不打架，那是遊歷那一條路自己擋（出陣包 train_actions.train_squad、train_option）；
        劇情戰從來不操練（_event_battle 不看陣營），黃巾的人打黃巾的頭目照樣是大場面（Task 2 審查修正 1）。"""
        return styles.is_big(self.content, squad)

    def _fight_squad(self, option_id: str) -> Squad | None:
        """這個選項按下去會打哪一路（遊歷、挑戰大勢人物本人、劇情戰的戰鬥選項）；不會打仗是 None。
        隨口應對（choice:free）不是數字，不是仗。"""
        s, c = self.state, self.content
        kind, _, arg = option_id.partition(":")
        # act 子動詞的主人說這一下打哪一路（Verb.squad，全部拆包第 17 批多開的一格）：出陣包——遊歷、出陣那一格（約戰開著不打仗、遇上自己人
        # 是操練，不打架）；大勢人物包——挑戰本人（Verb.tail_squad，第 57 批：難度照他此刻的聲威與江湖水漲）；不打仗、沒有主人照舊往下
        owned = features_core.act_squad(self, arg) if kind == "act" else None
        if owned is not None:
            return owned
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

    @_outing_watch
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
        # 不在選單上的動作（接縫掛鉤，第 11 批）：出陣包——約戰開著時的貼、應戰、同去（sortie:*，封招的組合放不進選單），各自在 world.mutate
        # 裡重驗；約戰關著的季照舊當成不在選單上
        unlisted = features_core.choose_unlisted(self, option_id)
        if unlisted is not None:
            return unlisted
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
            return Refused(self._log(self._bounty_stale(option_id.partition(":")[2])))
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
            # （為什麼不成問單挑包：全部拆包第 12 批）
            problem = self._arena_fight_problem(option_id)
            if problem:
                return Refused([f"（{problem}。）"])
        if option is None or not option.enabled:
            return self._log([self._fight_gone(fight) if fight is not None else "（此刻無法這麼做。）"])
        if option_id.startswith(GROWTH_PREFIX):  # 開季準備卡挑配比：pick_growth 自己寫紀錄（自己配要五項的數字，走 /api/growth）
            preset = option_id.removeprefix(GROWTH_PREFIX)
            return self._log([GROWTH_CUSTOM_ASK]) if preset == attrset.CUSTOM else self.pick_growth(preset)
        faction_before = self.state.player.faction  # 這一下才投靠的人才開始入伍段（見 _begin_enlistment）
        self.state.battle_card = None
        self.state.player.guide_done = []  # 對話框上一次完成的那幾行，下一次行動就清掉
        kind, _, arg = option_id.partition(":")
        # 選單上、不建紀錄的那幾顆（MENU_ORDER["quick"]，全部拆包第 57 批；格裡不寫紀錄，這裡 _log 一次）：決戰不走 Draft（加入與趕到自己寫一則，每回合的出招不寫，FB-030）；
        # 奪璽單挑、頭目戰、擂台每回合的出招不寫（收場那一下各自寫一則、一份戰報）；勸降與有所感的「畫下來」只叫出輸入框與畫布（送出走各自的三段式）
        quick = features_core.menu_first("quick", {}, self, kind, arg, option_id)
        if quick is not None:
            return self._log(quick)
        if option_id == FREE_TEXT_OPTION:
            return self._log([f"（寫下你的做法，{FREE_TEXT_MAX} 字以內。）"])  # 選項本身只叫出輸入框，不消耗事件
        said = say_text(text, self.say_max()) if option_id in TEXT_TALKS else None
        if option_id in TEXT_TALKS and said is None:
            return self._log([f"（寫下你想說的話，{self.say_max()} 字以內。）"])  # 選項本身只叫出輸入框
        prepared = self._checked_prepared(option_id, prepared, text) if kind in ("act", "talk", "call", "parley") else None
        self._fight = self._checked_fight(option_id, fight)
        was_opening = kind == "choice" and self._opening_pending()  # 開局三選一（減法季批 7）：選完人物的信到
        # 搬成包的功能：那一包接走（只吃自己前綴的 id；這一下江湖紀錄的標題在動作之前先拿，同 _action_title；開發規範手冊 3.3）
        self._talk_turn, self._talk_said = prepared, said  # 談話與帶路的路上一句（人物情誼包 choose 掛鉤）要的：鎖外生成好的一輪與驗過的那句話（寄放，同 _persuade_said）
        taken = features_core.choose(self, kind, arg)
        self._draft = Draft(taken.title if taken is not None else self._action_title(kind, arg))
        self._affinity_before = dict(self.state.player.affinities)
        stamina = self.state.player.stamina
        try:
            if taken is not None:
                msgs = taken.run()
            elif kind == "act":
                msgs = self._act(arg, prepared)
            # （move：前往，road：折返與路上小事，全部拆包第 47 批換成移動包的 choose 掛鉤〔上面 taken 那一支〕，拿掉）
            # （talk：談話；parley:road：帶路的路上說一句，第 20 批審查換成人物情誼包的 choose 掛鉤〔上面 taken 那一支；prepared 與 said 經 _talk_turn、_talk_said 寄放〕，拿掉）
            # （faction：投靠、確認、選邊、改幫；defect：叛投。全部拆包第 35 批換成陣營包的 choose 掛鉤〔上面 features_core.choose 接走〕，拿掉）
            # （call：指名求見，全部拆包第 21 批換成交友求見包的 choose 掛鉤〔上面 features_core.choose 接走；prepared 經 _talk_turn 寄放〕，拿掉）
            # （learn：拜師學藝，全部拆包第 23 批換成修練包的 choose 掛鉤〔上面 features_core.choose 接走〕，拿掉）
            # （opp：機緣、fs：伏筆的最後一步，全部拆包第 34 批換成軍情包的 choose 掛鉤〔上面 features_core.choose 接走〕，拿掉）
            # （sense：有所感選做法、順其自然，全部拆包第 24 批換成有所感包的 choose 掛鉤〔上面 features_core.choose 接走〕，拿掉）
            # （invite：邀請的答應、婉拒、收回，全部拆包第 37 批換成玩家互動包的 choose 掛鉤〔上面 features_core.choose 接走〕，拿掉）
            # （bounty：懸賞榜第二、三層選單上的每一顆，全部拆包第 45 批換成懸賞榜包的 choose 掛鉤〔上面 features_core.choose 接走〕，拿掉；FB-162 被搶的那一句仍在上面 choose 前段）
            # （smith：鐵匠鋪第二層選單上的每一顆，全部拆包第 41 批換成鐵匠鋪包的 choose 掛鉤〔上面 features_core.choose 接走〕，拿掉）
            # （market：馬市第二層選單上的每一顆，全部拆包第 42 批換成裝備包的 choose 掛鉤〔上面 features_core.choose 接走〕，拿掉；FB-195 被搶的那一句仍在上面 choose 前段）
            # （donate：軍需官那一串的選擇；dadian：打點那一間店的離開。全部拆包第 43 批換成銀兩出口包的 choose 掛鉤〔上面 features_core.choose 接走〕，拿掉）
            # （arena:join／fight／back：單挑包的 choose 掛鉤接走，上面 taken 那一支；全部拆包第 12 批）
            # （sect：拜入門派〔一類一顆，_sect_options〕，全部拆包第 35 批換成陣營包的 choose 掛鉤〔上面 features_core.choose 接走〕，拿掉）
            # （ambush：設伏、收伏；works：屯糧練兵。全部拆包第 39 批換成體力玩法包的 choose 掛鉤〔上面 features_core.choose 接走〕，拿掉）
            # （aid：護衛、犒軍、探望；plan：助他一臂、壞他的事。全部拆包第 31 批換成大勢人物包的 choose 掛鉤〔上面 features_core.choose 接走〕，拿掉）
            # （story：一條線的答題、打一場、端事件，全部拆包第 30 批換成一條線包的 choose 掛鉤〔上面 features_core.choose 接走〕，拿掉）
            elif kind == "dunwu":  # 特殊頓悟取名（有所感包，第 24 批；choose 掛鉤不帶 text——自己寫的名字在 text——留原位叫委派）
                msgs = self._epiphany_name(arg, text)
            else:
                msgs = self._choose(int(arg))
            # act 子動詞的主人宣告的「只打開一張卡」的回話（Verb.picks，第 11 批）：約戰開著時按出陣那一格只是打開出陣前那張卡（減法季批 3b）。
            # 不算做過、不寫紀錄；要在後面接上大勢門檻、召見那些訊息之前記
            picked_only = kind == "act" and msgs in [[reply] for reply in features_core.pick_replies(arg)]
            if faction_before is None and self.state.player.faction is not None:
                msgs += self._join_lean()  # 三陣營四勝利：拜入曹氏莊院而投靠的那一下照門派所在地給傾向（關著什麼都不做）
            self._begin_enlistment(faction_before)  # 投靠（或拜入陣營名下的門派）那一下：入伍段開始，同一下不算完成任何一步
            self._greet_rejoin(faction_before)  # 入伍段早就走完的人再投靠：引薦人打個招呼（新手引導計畫三）
            if faction_before is None and self.state.player.faction is not None:  # 這一下才投靠（確認，或拜入陣營名下的門派）：手上新陣營接不了的懸賞作廢、說一聲（FB-151）；叛投在 defection.defect 裡做
                msgs += bounty_base.drop_stranded(self.state, self.content, self._side())
            msgs += self._hear_after_stamina(stamina)
            if kind == "choice":  # 選了事件的選項：序章的遇險、拜師、四景（新手引導計畫一）
                msgs += self._guide(self._note_action("choice"))
            if was_opening and not self._opening_pending():  # 開局第一分鐘：那位人物開口、託付第一件事（信附委託）
                msgs += self._opening_deliver()
            if kind == "act" and arg != "break" and not picked_only:
                msgs += self._guide(self._note_action(arg))
                if arg in SHOP_ACTS:  # 初入江湖「進城裡的鋪子看看」：進哪一間都算（新手引導第四段）
                    msgs += self._guide(self._note_action("shop"))
            if option_id in LEAVE_SHOP_IDS:  # 出店（進了店再出來，新手引導重做：出了店下一步才不會被店面蓋住）
                msgs += self._guide(self._note_action("leave_shop"))
            if kind == "call" and arg != "back":
                msgs += self._guide(self._note_action("socialize"))  # 指名求見算一次交友
            # 名將贈禮（裝備四欄 6.4）與本命兵器（打造第三批）：這一下的情誼（對話、事件）到了門檻就送；另起一則「名將贈禮」，
            # 不接在當下這個動作的紀錄裡（FB-139、FB-149：名將多半不在場，也跟那件事無關），排在這一則之後（「剛剛」看得到）
            gifts = self._general_gifts() + self._signature_arms()
            msgs += check_thresholds(self.state, self.content, self.world, self._flavor_sink(), now=self.now)
            msgs += self._settle_plots()  # 參與過的密謀收場了：各自結算一次（正式版乙二）
            msgs += self._story_tick()  # 一條線：這一下做成的事、過了的期限往下走（關著是空的）
            msgs += ranks.check_summons(self.state, self.content)  # 貢獻跨過門檻就發召見（計畫 T5）
            msgs += self._report_seat()  # 第四階席次：抄帳、補缺（正式版丁）；這個動作結束時 _save_season 一起存
            if not picked_only:  # 只打開一張卡（什麼都沒做）：排著的提示留到下一個真的動作再上框，這一下才不必寫紀錄
                self._check_hints()  # 這一下碰到的新玩法排一條提示；事件了結、引導或入伍段走完的這一下，排著的上框。記在這一則的 guide（新手引導計畫三）
            # 打造的每一步（挑種類、主料、輔料、開爐、上一步、不打了）併成一則「打造」：一爐一則，不是一步一則。
            # 打開單子那一步（"forge"）不併、另起一則：_mergeable_head 只看最新一則是不是同標題，不然連打兩爐（或打開又不打了）
            # 會全部併進上一爐那一則。懸賞榜：打開榜那一則的標題是「懸賞榜・此地」，每次來都另起一則；挑一件、回到懸賞榜只是翻頁，
            # 只有那一句回話時不寫紀錄（bounty_base.is_browse_line）；交出、揭下、放棄、返回各一則（FB-161：交出不再跟挑、回併成一則，
            # 連交幾張時各寫各的得失）
            entry = self._draft.entry(self.state.world.time, msgs)
            # 鐵匠鋪切頁（裝備四欄設計 4.6）只是換一頁：沒有別的事（訊息、數值變化、引導）就不寫紀錄，不然每切一次多一則「鐵匠鋪」
            quiet = kind == "smith" and arg.startswith("page:") and not (entry.lines or entry.changes or entry.guide)
            quiet = quiet or (kind == "bounty" and arg.partition(":")[0] in bounty_base.BROWSE_VERBS and not (entry.changes or entry.guide)
                              and all(bounty_base.is_browse_line(line) for line in entry.lines))
            quiet = quiet or (picked_only and entry.lines in [[reply] for reply in features_core.pick_replies()]
                              and not (entry.changes or entry.guide))
            if not quiet:
                # FB-141：開爐成了（_smith_act 打完把單子收起來了）那一下併進「打造」那一則時只留結果——結果句排第一，375 寬「剛剛」
                # 收著時看得到；挑種類、主料、輔料的回報收掉（放了哪兩樣、哪一種，結果句「打出一把【…】（種類・屬…）」
                # 本身寫了）。開爐沒成（單子還在）、上一步、不打了照舊接在後面。收掉的只有單子自己的回話（smith_base.is_step_line）：
                # 前幾步順便帶來的別的話（大勢門檻的消息、召見之類）接在結果句後面留著（終審 M3）
                forged = kind == "smith" and arg.partition(":")[0] == smith_base.GO_VERB and self.state.player.smith_draft is None
                journal.add_entry(self.state, entry, merge=kind == "smith" and smith_base.is_forge_step(arg) and arg != "forge",
                                  fold=smith_base.is_step_line if forged else False)
            self._gift_entry(gifts)
            msgs += gifts
        finally:
            self._draft = None
            self._fight = None
            self._affinity_before = None
        self._record_faction()
        msgs += features_core.after_action(self)  # 本人做完一件事（接縫掛鉤，第 11 批）：酒肆包——有人雇了殺手找你，你剛在城外做完一件事（設計第六節）
        self._save_season()
        return self._log(msgs)

    def free_text_request(self, text: str) -> FreeTextRequest | None:
        return event_check.free_text_request(self, text)

    def _free_text_of(self, event: Event) -> FreeTextChoice | None:
        return event_check.free_text_of(self, event)

    def _branches(self, event: Event) -> list[Outcome]:
        return event_check.branches_of(self, event)

    @_outing_watch
    def answer_event(
        self, request: FreeTextRequest, llm_rate: int | None = None, moral: str | None = None, outcome: str | None = None,
    ) -> list[str]:
        return event_check.answer_event(self, request, llm_rate, moral, outcome)

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

    # ── 人物心意（減法季批 6）：本體在 tianxia/features/companions/actions.py（全部拆包第 19 批），這裡留一行委派 ────────────

    # ── 託付與勸降（減法季批 6）：本體同上 ────────────

    _persuade_said: tuple | None = None  # 勸降的 C 段（人物情誼包 actions.persuade）交給 choose 的單子與模型的分數（服務清單四、寄放）
    _talk_turn: companion_agent.PreparedTurn | None = None  # choose 前段驗過的那一輪對話（鎖外生成好的）與那句話，交給人物情誼包的 choose 掛鉤（服務清單四、寄放）
    _talk_said: str | None = None


    def add_gamble_narration(self, outcome: FreeTextOutcome, narration: str) -> None:
        return event_check.add_gamble_narration(self, outcome, narration)

    # ── 有所感與頓悟：本體在功能包 tianxia/features/sense/actions.py（全部拆包第 24 批），這裡留一行委派 ──
    # （_sense、_sense_apply 只有包裡叫：sense: 由 choose 掛鉤接走；epiphany_names、sense_draw 在包裡掛核心的 outing_watch）

    # ── 有所感的服務（全部拆包第 24 批）：核心原位（選單、清失效參照、舊探索、choose、紀錄標題）與別的包（探索、新手引導）叫的，
    # 本體在 sense_actions；探索包的查詢服務 _rare_boost（有所感擲特殊頓悟乘它）──

    def _action_title(self, kind: str, arg: str) -> str:
        s, c = self.state, self.content
        # （faction：投靠、確認、選邊、改幫；defect：叛投。標題全部拆包第 35 批換成陣營包 choose 掛鉤的 Outcome.title，拿掉；sect 沒有自己的支，掉到最後的「提前出關」）
        # （move：「前往 <地點名>」，全部拆包第 47 批換成移動包 choose 掛鉤的 Outcome.title，拿掉）
        if kind == "choice":
            event = c.events[s.pending_event]
            return f"{event.title}・{event.choices[int(arg)].text}"
        # （talk：「交談・某人」、parley:road：「同行・某人」，第 20 批審查換成人物情誼包 choose 掛鉤的 Outcome.title，拿掉）
        # （call：「求見・某某」「收回名帖」，全部拆包第 21 批換成交友求見包 choose 掛鉤的 Outcome.title，拿掉）
        # （sense：「有所感・場景」，全部拆包第 24 批換成有所感包 choose 掛鉤的 Outcome.title，拿掉）
        # （learn：「學藝・<武學名>」，全部拆包第 23 批換成修練包 choose 掛鉤的 Outcome.title，拿掉）
        # （fs：「作罷」「<這一趟>・<所在>」，全部拆包第 34 批換成軍情包 choose 掛鉤的 Outcome.title，拿掉）
        # （road：折返跟「前往」同一個標題、路上小事寫它自己的名字，全部拆包第 47 批換成移動包 choose 掛鉤的 Outcome.title，拿掉）
        # （opp：機緣的標題，全部拆包第 34 批換成軍情包 choose 掛鉤的 Outcome.title，拿掉）
        # （bounty：「懸賞榜」，全部拆包第 45 批換成懸賞榜包 choose 掛鉤的 Outcome.title，拿掉）
        # （smith：鐵匠鋪的標題，全部拆包第 41 批換成鐵匠鋪包 choose 掛鉤的 Outcome.title，拿掉）
        # （market：馬市的標題，全部拆包第 42 批換成裝備包 choose 掛鉤的 Outcome.title，拿掉）
        # （donate、dadian 的標題：全部拆包第 43 批換成銀兩出口包 choose 掛鉤的 Outcome.title 與 act 子動詞的 Verb.title，拿掉）
        # （kind == "aid"、"plan"：標題由大勢人物包的 choose 掛鉤給，全部拆包第 31 批）
        # （kind == "arena"：報名、挑人的標題由單挑包的 choose 掛鉤給，全部拆包第 12 批）
        # （kind == "invite"：標題由玩家互動包的 choose 掛鉤給，全部拆包第 37 批）
        # （story：寫線的名字，全部拆包第 30 批換成一條線包 choose 掛鉤的 Outcome.title，拿掉）
        if kind == "dunwu":  # 特殊頓悟取名（有所感包，第 24 批）
            return self._epiphany_title()
        # act 子動詞的標題都由主人給（接縫掛鉤，第 11 批；其餘的全部拆包第 57 批接上，帶後綴的走 Verb.tail_title）。下面那張表照 arg 查、不看 kind，這裡也照 arg 問，
        # 只有帶後綴的與銀兩那四樣要 kind == "act"（第 57 批拿掉過，補回：base 這幾種都看 kind；_action_title("sect", "furnace") 是「提前出關」）；
        # 主人不接照舊查表：舊探索、沒有主人時的遊歷、療傷（留核心，計畫第四節）；其餘（act:break、sect:）是「提前出關」
        owned = features_core.act_title(self, arg) if kind == "act" or not (":" in arg or arg in ("silver_donate", "mentor", "furnace", "buy_legend")) else None
        if owned is not None:
            return owned
        here = c.locations[s.player.location].name
        titles = {"explore": f"探索{here}", "train": f"遊歷・{here}", "heal": f"療傷・{here}"}
        return titles.get(arg, "提前出關")

    # core_eventbus（全部拆包第 26 批）
    def publish(self, event: str, *args: Any) -> list[str]:
        """一包發生的事、別包跟著動（事件機制，全部拆包第 26 批）：照 core/features.py 的 BUS_ORDER[event] 一格一格叫（包登記的叫包的，
        其餘是 _BUS_CORE 核心代叫），每一格回的那幾句照順序串起來（battle_end 的格回 None，不串）。"""
        msgs: list[str] = []
        for got in features_core.bus_run(event, _BUS_CORE.get(event, {}), self, *args):
            msgs += got or []
        return msgs

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
        heads = tuple(f"【{name}】" for name in self._guide_speakers())  # 每一步可以是不同的人說（新手引導計畫一）
        shown = [n for n in notes if not n.startswith(heads)]
        if shown:  # 只有引薦人的話（入伍段的 ✔ 在它的框不是框上那一個時不回傳）：框上原本的完成列不動
            self.state.player.guide_done = shown

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

    # ── 新手引導的服務（全部拆包第 22 批：核心原位與出陣包碰引導的那幾處改叫這幾個一行的委派；本體在新手引導包；計畫
    # docs/superpowers/plans/2026-11-01-新手引導包-第1批.md 1.4）──

    def _note_action(self, action: str) -> list[str]:
        """做完一個行動，引導（說書人的步驟與入伍段）看這一步完成了沒（guide.note_action），回那幾行（呼叫端交給 _guide）。
        叫 engine 模組層的 note_action：tests/core/test_engine.py 換的是 tianxia.engine.note_action。"""
        return note_action(self.state, self.content, self.world, action)

    # ── 新手目標（新手引導重做；tianxia/newbie.py）──

    # ── 書信與委託（大勢人物擴充第二批）：本體同上 ──

    # ── 人物的行程與盤算（世界活起來；tianxia/plans.py、deeds.py）──


    def place_state_view(self) -> dict | None:
        """地點會變樣（main.place_state）：此刻所在地的樣子 {kind, name, line}；太平、在路上、關著是 None。"""
        s = self.state
        if s.player.journey is not None:
            return None
        return place_state.view(s.world, self.content, s.player.location)

    # ── 宴客（搬進功能包 tianxia/features/feast/；server 的三段式照舊叫 Game 的這三個，過渡留一行委派）──

    # ── 月旦評（第三批；tianxia/yuedan.py）──

    # ── 行動 ──────────────────────────────────────────────

    def _action_costs(self) -> dict[str, int]:
        """各行動花的體力：照 Config.action_cost。按鈕上寫的與真的扣的都讀這一個。（輕身以前少花遊歷的體力；本命戰法第三批起
        改成回合裡的化影，tactics.py）"""
        return dict(self.content.config.action_cost)

    def _act(self, what: str, prepared: companion_agent.PreparedTurn | None = None) -> list[str]:
        # act 子動詞的主人是功能包的（接縫掛鉤，第 11 批；計畫 docs/superpowers/plans/2026-11-01-核心收接縫.md 1.3）：探索包——減法季探索一顆的
        # 出門一趟（體力在裡面扣）；酒肆包——進店（不花體力）；出陣包——約戰開著、不在序章時出陣那一格打開出陣前那張卡（不花體力；截糧的
        # 運糧隊經過時照舊攻打，體力在裡面扣），其餘打那一場（第 17 批：扣體力、並肩出陣的加成、出陣或遊歷，體力在裡面扣），與守勢（act:duty，
        # 第 17 批，體力在裡面扣）；單挑包——打開擂台（不花體力，頭一句是名次；全部拆包第 12 批）。後幾支原本在中段：前面那幾支只比 what、
        # 只讀（ranks.summons_event 只讀），子動詞互斥，挪到最前面結果一樣
        # 全部拆包第 57 批：其餘的子動詞也接走了（招募、調息、第 2 階、第 3／4 階、糧車、應召、打點門路、求見、交友、挑戰本人，帶後綴的走 Verb.tail_run；計畫第二節）；
        # 這裡只剩療傷與舊探索（計畫第四節）
        got = features_core.act(self, what, prepared)
        if got is not None:
            return got
        if what == "heal":  # 醫館療傷（企劃者 2026-10-12）：同修練頁的療傷鈕，不花體力
            return self._heal_msgs()
        promotion = ranks.summons_event(self.state, self.content)
        self.state.player.stamina -= self._action_costs()[what]  # 不認得的 what 在這裡 KeyError，照舊
        if promotion is not None and not precise.on(self.content, self.state.world):
            # 在召見的地點探索：端出晉升奇遇（計畫 T5）；一類一顆開著時不再換掉（正式季整合 2.10），應召照舊在「此地還能做」。交友那一支同一段在交友求見包 actions.press
            return self._present(self.content.events[promotion])
        return self._explore()

    def _pill_find(self, rng: random.Random) -> list[str]:
        """素材那一拍掉一顆回體丹（21 天季，正式季整合 6.4；Config.checkin.pill_drop）：用探索自己的亂數（用途「回體丹」），
        不碰別的骰。兩行同破境丹：「獲得」開頭的敘事與「回體丹 +1」（寫進紀錄的數值變化）。"""
        c = self.content
        chance = c.config.checkin.pill_drop
        if chance <= 0 or not checkin_on(c, self.state.world) or rng.random() >= chance:
            return []
        self.state.player.stamina_pills += 1
        name = c.config.stamina_pill_name
        return [PILL_FOUND.format(name=name), f"{name} +1"]

    # ── 減法季探索一顆（整合設計 4.1，批 2；Config.jianfa 的 explore_one）：本體在功能包 tianxia/features/explore/explore_actions.py（主動搬六包第 3＋4 批），這裡留一行委派 ──

    # ── 走一趟（企劃者 2026-10-29～30）：本體在功能包 tianxia/features/explore/outing_actions.py（主動搬六包第 3＋4 批），這裡留一行委派 ──

    def is_idle(self) -> bool:
        """此刻閒著（切磋、論武、假人答論武都問它）：選單上有探索（IDLE_MARK）——不在路上、沒有事件、對話、店面的選單擋著、不在開打的決戰裡。
        減法季探索一顆開著時「探索」照舊是 act:explore、出現在同樣的那幾種選單上，判斷不必換訊號；序章另外擋（呼叫端）。"""
        return IDLE_MARK in {o.id for o in self.options(odds=False, tick=False)}

    def _push_room(self, trend_id: str) -> float:
        """自己今天在這條線上還推得動多少（每人每曆日上限，緩衝後的量）：跟 push_trend 走 push.py 的同一個算法（push.room）。
        第一季的規則沒開時 push_trend 不設上限，這裡也是無限。"""
        s, c = self.state, self.content
        if not calendar.season_one_on(s.world, c):
            return math.inf
        day = calendar.point(s.world.time, c, s.world).cal_day
        return push.room(s.player.pushed, day, trend_id, self.daily_push_cap())

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

    def _shop_say(self, key: str, problem: str | None = None) -> None:
        """店面上掌櫃那一句（店面獨立介面設計 1.4、6.1）：記下店裡最後一件事的情況鍵、挑句子的種子（這一刻的季的時間），與被拒的那一句
        撐到什麼時候（shopview.hold_for，FB-192：problem 是被拒的原因，錢不夠那一句照它記要多少銀兩）。"""
        p = self.state.player
        p.shop_line, p.shop_line_seed = key, int(self.state.world.time)
        p.shop_hold = shopview.hold_for(self.state, self.content, key, problem)

    def _shop_after(self, problem: str | None, done: str, keyer=None) -> None:
        """照這一下的擋法記掌櫃那一句：做成了是 done，被拒照 shopview.problem_key（懸賞榜照 board_key）換成情況鍵，連同被拒的原因（FB-192）。"""
        self._shop_say((keyer or shopview.problem_key)(problem, done), problem)

    def _shop_open(self) -> str | None:
        """哪一間店開著（店面獨立介面設計 1.1；同 options() 的先後：懸賞榜、鐵匠鋪、馬市）。那個地方已經不開門了（同步之前）是 None；
        鐵匠鋪的一步一步單子還開著（開關關著時開的、舊存檔）也是 None，照舊畫那一串按鈕（店面上的鈕在單子那一步不在選單上）。"""
        # 先後在 MENU_ORDER["open"]（core_seams，全部拆包第 56 批）：擂台打到一半（Joy 2026-10-14「擂台應該要是獨立的一頁」）、懸賞榜、鐵匠鋪、馬市，最後是店面登記的店（坐在店裡、這裡也還開著）；
        # 格回 "" 是坐著、這裡不開門了
        return features_core.menu_first("open", _MENU_CORE["open"], self) or None

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
        if shop == "smith":  # 打造頁的爐火（鐵匠鋪與合成流程 3.2，forge.furnace）要回體丹的換日與序章：Game 才知道
            view = shopview.smith_view(s, c, self.world, day=self._pill_day(), prologue=prologue_rules.active(s, c))
            view["trade"] = shopview.trade_view(s, c, self._pill_day())  # 素材買賣（素材與經濟設計第四、五節）：收購、升階都關著是 None
            return view
        return {"market": shopview.market_view, "board": shopview.board_view}[shop](s, c, self.world)



    # ── NPC 智能 2.0（parley.py；Joy 2026-10-23「先做看看」）────────────

    _parley_decision: parley.Decision | None = None  # 這一輪「自己說」擲出來的結果（_parley_decide 記、_talk 收尾時拿去做事）



    def _side(self) -> str | None:
        """敵我的一個讀法（allied.side_of）：豪強分屬兩軍的季，豪強是依附的那一軍；其他人是自己的陣營（散人 None）。"""
        return allied.side_of(self.state, self.content)

    def faction_counts_text(self) -> str:
        """名冊那一句（allied.roster_text）：「目前官軍 N 人、黃巾軍 M 人、地方豪強 K 人」，照全服投靠名冊（真人與假人一起算）；
        豪強分屬兩軍的季照兩軍寫、括號寫豪強（「目前官軍 12 人（其中豪強 3 人）、黃巾軍 9 人」）。"""
        return allied.roster_text(self.content, self.state.world, self.world.roll_counts())

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
        if attrset.on(self.content, self.state.world):  # 五項屬性的季：照新的五項比（舊的四項有上限曲線，上限不同會偏向悟性）
            stats = {old: attrset.value(self.state, self.content, new) for old, new in self.content.config.attributes.v2.legacy.items()}
            return battle_instance.role_for(stats, team.COMBAT_STATS)
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
        """快照進 BattleParticipant 的坐騎、部下與防具減損（join_faction／auto_assign_latecomer 的 mount、cavalry、troops、troop_bonus、cut）。
        cut 是奪璽單挑吃防具用的（鐵匠鋪與合成流程 3.9，照坐騎的先例在加入決戰那一刻抄）；決戰本身不吃。"""
        horse, cavalry = self._battle_mount()
        troops, bonus = self._battle_troops()
        return {"mount": horse, "cavalry": cavalry, "troops": troops, "troop_bonus": bonus, "cut": self._duel_cut()}

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
        card = team.pvp_card(self.state, self.content, self.world)
        if card is not None:  # 五項屬性的季才多這一鍵（奪璽單挑照對手重算）；舊的季一個字不變
            marks["card"] = card
        return marks

    def _battle_road(self) -> str:
        """加入戰局時快照的武學屬性（決戰的隊伍多樣性，一門打不遍）：只有第一季開著時才記，關著時是空的、不算一路。"""
        if not season_one(self.content, self.state.world):
            return ""
        return team.worn_attribute(self.state, self.content, self.world) or ""

    def _battle_neili_cap(self) -> float:
        """決戰的氣血池上限：決戰的池子不吃螭首（玉璽碎片設計 7.1：決戰一個字都不改）。"""
        _, cap = team.member_neili(
            self.content, self.state.player.member, team.con_of(self.state, self.content, self.world, PLAYER), plain=True,
            season=self.state.world,
        )
        return cap

    # ── 好幾場戰鬥並存（領地爭奪第二批 Task 10）：時刻表決戰一場（world.get_battle）＋攻城戰一串（world.get_sieges）──
    # 攻城那幾個（_sieges、_definition_of、_tick_siege、_cancel_siege）的本體在 tianxia/features/battle/sieges.py（全部拆包第 6 批）；推進與結算
    # （我在哪一場、一回合一回合推、收兵、收場與論功）的本體在 tianxia/features/battle/progress.py（全部拆包第 8 批），這裡留一行委派。

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

    # ── 全服決戰收場補送（戰報、江湖紀錄、軍餉、行狀、戰功；FB-027）：本體在 tianxia/features/battle/view.py（主動搬六包第 5 批），這裡留一行委派 ──

    # ── 全服決戰的畫面（戰局條、攻城條、場景、一回合一段的戰況、點名、已送出／在場）：本體在 tianxia/features/battle/view.py，這裡留一行委派 ──

    def event_free_text_prompt(self) -> str | None:
        return event_check.event_free_text_prompt(self)

    # ── 決戰的放手一搏（輸入框、鎖外三段式的 A、C 段）與補劇情（server.narrate_once 的 A、C 段）：本體在 tianxia/features/battle/view.py，
    # 這裡留一行委派 ──

    # 放手一搏輸入框旁邊那兩句（字在 features/battle/rules.py；過渡：tests/core/test_engine.py 從 game 讀）
    BATTLE_GAMBLE_NOTE = battle_rules.BATTLE_GAMBLE_NOTE
    BATTLE_GAMBLE_LAST = battle_rules.BATTLE_GAMBLE_LAST

    def _present(self, event: Event, action: str | None = None) -> list[str]:
        return event_check.present(self, event, action)

    def _event_text(self, event: Event) -> str:
        return event_check.event_text(self, event)

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
            return self._drill(squad)  # 遇上自家隊伍改操練：操練是出陣包的（第 17 批），打不打在這個單打服務裡定
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
            rewards = self._sortie_rewards(squad, record) if as_sortie else self._battle_rewards(squad, record)  # 留原位：第 26 批（打贏的獎勵是出陣包與核心二選一、接在 msgs 最前面不進 extra，不在懸賞那一個發布點上）
            msgs += rewards
            extra: list[str] = []
            if not wild and not prologue_rules.active(s, c):  # 序章打贏不推大勢、不抽伏筆、不記軍令
                if not as_sortie:  # 出陣不推線（領地爭奪：推那一塊的進度，下面 _push_progress）
                    for trend_id, delta in self.train_trend_push(loc.id).items():  # 換算過的線，照舊交給 T3 的 push_trend  # 留原位：第 26 批（推大勢夾在記功、地盤進度之前，結果交給 push_trend，不在發布點上）
                        extra += self.push_trend(trend_id, delta, source="train")
                credit: list[str] | None = None
                # 領地爭奪：出陣攻打贏推這一塊的進度、不推線（設計 3.7）；約戰開著時這裡只剩截糧（減法季批 3b：進度只在約戰結算動）
                if as_sortie and not self.duel_on():  # 留原位：第 26 批（約戰開著與否是查詢，決定記功與推進度走哪一支，不是事件）
                    # 軍令照推之前的清單記（FB-608：推滿易手的那一下，推完那一塊已經是自家的、在冷卻，不在攻的清單上）；那一句照舊排在後面
                    credit = self._order_credit(
                        kind="win", location=loc.id, front=front_of(c, loc.id), squad=squad.id, squad_faction=squad.faction,
                    )
                    extra += self._push_progress(loc.id, conquest.sortie_nominal(c, loc.id, "attack"), "sortie", "attack")
                region = atlas.region_of(c, p.location)  # 官銀（伏筆，濃縮版內容表 4.0）：只有遊歷打贏才擲
                extra += self._fs_after_win(squad, region.id if region is not None else None)
                extra += credit if credit is not None else self._order_credit(  # 軍令（計畫 T6）：攻城看戰線與敵方陣營，截糧看地點與運糧隊
                    kind="win", location=loc.id, front=front_of(c, loc.id), squad=squad.id, squad_faction=squad.faction,
                )
                extra += self._opp_on_win(front_of(c, loc.id), squad.faction)  # 三路並進（正式版乙二）
                extra += self.publish("win", loc.id, squad.id)  # 懸賞榜的討伐（事件 win，第 26 批）
                if as_sortie:  # 名聲 3.1：出陣攻打贏 +1（遊歷、探索野怪不給）
                    extra += self._deed_fame("sortie")
            changes, notes = battlelog.split_changes(extra, for_record=True)
            record.changes += changes
            record.notes += notes
            msgs += extra
        elif result.tier == "落敗":
            msgs += self._lose_silver(record)
        toll, hp_lost, facts = self._take_toll(result.tier, wild=wild, clash=result.clash, squad=squad)
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
        規則關著的季是它們合成的那一條（黃巾聲勢）。玉璽線索不算。"""
        c, w = self.content, self.state.world
        return {line for front in front_ids(c) if (line := resolve_trend(c, w, front)) is not None}

    def _shaped(self, trend_id: str, delta: float, source: str) -> tuple[float, bool]:
        """玩家這一下真的要推多少（設計 3.2、5.1、5.2）：可重複的事件推戰線打 event_trend_share；第一季的出陣乘季長倍數（規則關著的季
        照舊在 push_trend 那一條縮）；再照推之前的戰線打盡頭阻力。回傳（推的量, 有沒有被阻力打折）。開關都關著時原樣回傳。"""
        c, w = self.content, self.state.world
        cfg = c.config
        amount = float(delta)
        if trend_id not in self._resisted_lines():
            return amount, False
        if source == "event":
            amount *= cfg.event_trend_share
        season21 = calendar.season21_on(w, c)
        if season21 and source in ("sortie", "donate", "event"):  # 21 天季（7.4）：出陣、捐軍備、可重複的事件同一個速度，不乘季長倍數
            amount *= cfg.season21_daily.push_speed
        if not cfg.push_resistance.enabled:
            return amount, False
        if source in ("sortie", "donate") and calendar.season_one_on(w, c) and not season21:  # 捐軍備照出陣（素材與經濟設計第六節第 2 點）
            amount *= self.season_scale()
        share = push.resistance_share(world_trend_value(w, c, trend_id), amount, push.tuning_for(w, c))
        return amount * share, share < 1

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

    def _drill_gains(self, squad: Squad, share: float | None = None, source: str = "hold", echo: bool = True) -> list[str]:
        """跟這一路一起操練拿的：對手心得與經驗的 share（預設 drill_reward_share；不給銀兩、素材）；經驗本人與帶著的同伴都拿（FB-002）。
        操練（_drill）與出陣的守（_sortie_hold）、守勢行動（_duty）共用；一類一顆開著時守、守勢行動給全額（_hold_share）。
        source（growth.exp_source）：這幾樣都不打仗（hold，PM 2026-10-25 第 5 件）；減法季自家營寨跟同袍比劃算仗（camp_spar）。
        echo：「心得 +N」那一行要不要也放進回傳的訊息。江湖紀錄的標籤本來就由草稿（_draft.changes）記一顆、訊息那一行在敘事裡收掉；
        出門一趟的比劃（_outing_fight）自己有「得：」那一行，兩邊都有就被 explore_actions.outing_ledger 加成兩倍、後面還多一則單獨的訊息
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

    # ── 一條線（特殊事件與特殊頓悟的底座）：本體在 tianxia/features/story/actions.py（全部拆包第 30 批），這裡留一行委派 ──
    # （_story_act、_story_fight、_story_bout 只有包裡叫：story: 由 choose 掛鉤接走，不留）

    def event_tier(self) -> dict | None:
        return event_check.event_tier(self)

    # ── 混戰（翻地與爭搶，輿圖簡化設計 4.3）、出陣的鈕、出陣、獎勵、守：本體在 tianxia/features/sortie/actions.py，這裡留一行委派 ──

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

    # ── 出陣約戰（減法季批 3b；整合設計 4.3）：本體在 tianxia/features/sortie/duel_actions.py，這裡留一行委派（主動搬六包第 2 批）──
    # 貼、應戰、同去、兩張卡（server、假人、測試在叫）；三處結算（world_tick、sync、advance）與假人程式那一下；核心原位那幾處

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

    def _take_toll(self, tier: str, *, wild: bool = False, clash: tactics.Clash | None = None, squad: Squad | None = None,
                   ) -> tuple[list[str], int, TollFacts]:
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
        saved, spared = team.toll_saved(self.state, self.content, self.world, tier, wild=wild, share=share, squad=squad)  # 扣之前量：化勁、不動這一場改了多少
        toll = team.take_encounter_toll(self.state, self.content, self.world, tier, wild=wild, share=share, squad=squad)
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
        our_agility = float(team.v1_stat(s, c, "agi"))
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

    def _story_squad(self, squad: Squad) -> Squad:
        """劇情戰的對手：大場面（is_big）照江湖水漲浮上來（全隊威力 × big_scale，不看打贏幾次：劇情戰多半一次性）；
        其餘、序章照內容寫的。勝算（_choice_label）、備料（_fight_squad）、打起來（_event_battle）都照這一份。"""
        s, c = self.state, self.content
        if not rise.on(c, s.world) or not self.is_big(squad) or prologue_rules.active(s, c):
            return squad
        level = rise.big(c, squad.difficulty, team.power_vs(s, c, self.world, squad, fresh=True, terrain=False, seal=False))  # 地利、碎片不浮
        return squad if level == squad.difficulty else squad.model_copy(update={"difficulty": round(level, 1)})

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

    def _goals(self) -> dict[str, int]:
        """自己陣營的目標，照 rules.resolve_goals 換過鍵（開關關著時三條戰線都算黃巾聲勢）；散人是空的。
        照那一邊（_side）：豪強分屬兩軍的季是依附那一軍的目標，所以豪強的守勢行動、修築塢堡、遊歷也往那一軍推。"""
        faction = self.content.scenario.find_faction(self._side())
        return resolve_goals(self.content, self.state.world, faction.goals) if faction is not None else {}

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
            # 推到 60 或砸到 0，決戰「要嘛第一天開、要嘛整季不開」）。決戰收場不走這裡、不縮放；操練的縮放在出陣包 train_actions.drill_push 先算好，
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
            # 捐軍備（source="donate"）的貢獻照捐的份量在 donate_actions.take 記，推力不另記（PM 2026-10-15）
            if source != "donate" and goal and (goal > 0) == (amount > 0):  # 替自己陣營的目標方向推；逆著推、這條線沒有目標都不記
                gained = push.contribution(abs(delta), pushed, moved, cfg.contrib_per_push, cfg.over_cap_contrib_ratio)
                wins.credit(p, c, w, at.week, gained)
            w.active_pushers.setdefault(side, {})[p.name] = now
        w.active_pushers = push.drop_stale(w.active_pushers, now, window)  # 順手清掉超過時窗的人，名單不會一直長
        return msgs + tail

    def _battle_rewards(self, squad: Squad, record, max_tier: int | None = None) -> list[str]:
        p = self.state.player
        msgs = []
        scale = self._loot_scale  # 探索包遭遇那一場（城裡的地痞）才不是 1
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
        msgs = self._seize_chance(record.difficulty / record.our_power)  # 留原位：第 26 批（頓悟的契機在單打服務收尾、三處叫、野怪與僵持也算，不是懸賞那一下；修練包的查詢服務）
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

    def _real_minutes(self, world_seconds: float) -> int:
        """世界時鐘的一段秒數，換成給玩家看的「現實」整分鐘（至少 1 分，.5 進位）：世界秒 ÷ time_scale ＝ 現實秒（FB-062）。"""
        return atlas.whole_minutes(max(0.0, world_seconds) / self.content.config.time_scale / 60)

    def _choose(self, index: int) -> list[str]:
        return event_check.resolve_choice(self, index)

    def _tale_clue(self, event: Event) -> list[str]:
        return event_check.tale_clue(self, event)

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

    def _overhear(self, companion_id: str, msgs: list[str]) -> list[str]:
        """人物這一輪原字原句引出了他知道的那句口訣：記進武學譜，多一句提醒（第一次聽到才寫）。"""
        if secret_recipes.overheard(self.state, self.content, self.world, companion_id, "\n".join(msgs)):
            return [self.content.config.secrets.overheard]
        return []

    def _event_battle(self, event: Event, choice: Choice) -> list[str]:
        return event_check.event_battle(self, event, choice)

    def _apply(self, effect: Effect, once: bool = False) -> list[str]:
        return event_check.apply(self, effect, once)

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
            # 同一個範圍順便記住純粹照內容與輸入算的東西（最短路、名聲說明卡的選項），一次畫面建構不重算（主機實測 view 0.13～0.2 秒，2026-11-03）
            with atlas.route_memo(), renown.needs_memo():
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
            and s.player.journey is None
            # 求見名單、懸賞榜、鐵匠鋪、答題、有所感、頭目戰、馬市、軍需官、打點、酒肆、擂台、還沒挑依附哪一邊：選單卡在別處，先了結（FB-121 第 4 件；先後在 MENU_ORDER["idle"]，core_seams）
            and not features_core.menu_any("idle", {}, self)
        )

    # ── 閉關（本體在功能包 tianxia/features/seclusion/，全部拆包第 39 批；這裡留一行委派給 server 的修練頁、_advance_player_local 與測試）──

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

    # ── 修練（全部拆包第 23 批：本體在修練包 tianxia/features/cultivation/actions.py，server、假人、測試照舊叫 Game，這裡留一行委派）──

    # ── 自創武學（五步：執器、擺式、立意、成形、立名；tianxia/create.py）──────────────────

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
        rewards = self._guide(self._note_action("pill"))  # 序章「服一顆回體丹」（新手引導重做）
        return self._log(msgs + [f"體力 +{round(p.stamina - before)}（{name}還剩 {p.stamina_pills} 顆）"] + rewards)

    # ── 每日簽到：本體在 tianxia/features/checkin/actions.py（全部拆包第 30 批），這裡留一行委派 ──

    # ── 領地爭奪：翻地與爭搶（輿圖簡化設計第四章）——戰書、換天的掛鉤、分紅送到、畫面資料。投票與 22:00 公告結算拿掉了（PM 2026-10-20）──

    def _conquest_side(self) -> str | None:
        """替哪一軍推進度、下戰書、打攻城（豪強分屬兩軍：依附的那一軍）；散人、不是兩軍是 None。"""
        side = allied.side_of(self.state, self.content)
        return side if side in conquest.SIDES else None

    # ── 〈天下形勢〉（領地爭奪第三批 A；tianxia/xingshi.py，計畫第五章 Task 16、17）──

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

    # ── 錢包（核心；開發規範手冊 3.10）──

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

    def _season_prep(self) -> list[Option] | None:
        """開季準備卡（企劃者 2026-11-05「至少需要導引」）：進新的一季第一個畫面，依序 ① 挑這一季的成長配比（五項屬性的季、還沒挑）
        ② 功能包的開季準備（傳承：識海的候選封一份或不帶）。做完才能做別的事，所以接管整個選單；不在選單上的動作照舊各自擋。
        序章裡不問（序章那一步就是挑配比，跟這張卡不重複問）。沒有要準備的回 None。"""
        s, c = self.state, self.content
        if prologue_rules.active(s, c):
            return None
        if attrset.on(c, s.world) and s.player.growth_preset is None:
            return [Option(id=f"{GROWTH_PREFIX}{p['key']}", label=f"這一季照「{p['name']}」長")
                    for p in attrset.view(s, c)["presets"]] + [Option(id=f"{GROWTH_PREFIX}{attrset.CUSTOM}", label="自己配")]
        return features_core.prep(self)

    def season_prep_view(self) -> dict | None:
        """江湖畫面的 main.prep（網頁畫開季準備卡）：step 是 growth（挑配比，鈕照 main.status.growth 畫）或 feature（功能包的那一步，
        選項照選單畫：傳承的識海）；steps 是這一張卡有幾步（五項屬性的季有挑配比那一步，功能包還有要準備的多一步）。沒有要準備的是 None。"""
        prep = self._season_prep()
        if prep is None:
            return None
        growth = any(o.id.startswith(GROWTH_PREFIX) for o in prep)
        steps = (["growth"] if attrset.on(self.content, self.state.world) else []) + (["feature"] if features_core.prep(self) is not None else [])
        return {"step": "growth" if growth else "feature", "steps": steps}

    @_not_while_preparing
    def pick_growth(self, preset: str, custom: dict | None = None) -> list[str]:
        """挑這一季的成長配比（屬性與跨季架構 v2 3.1：五套預設或自己配，合計固定）：只有五項屬性的季有。
        一季只挑一次、挑了就鎖（企劃者 2026-11-05「加點是隨時都可以調整？感覺有點奇怪」）：序章那一步或開季準備卡上挑；
        還沒挑的人照 default_preset 長。"""
        s, c = self.state, self.content
        if not attrset.on(c, s.world):
            return self._log(["（這一季沒有成長配比。）"])
        if s.player.growth_preset is not None:
            return Refused(self._log([GROWTH_LOCKED]))
        return self._apply_growth(preset, custom)

    # ── 玩家之間的邀請與切磋（玩家互動第二層，企劃者 2026-10-08「互動的兩層也可以派下去做了」）──────────
    # 切磋掛在玩家卡上（玩家互動包 spar.py 載入時登記進 social.ACTIONS，動作在 spar_actions.py，全部拆包第 38 批）：發邀請、答應、婉拒、收回都是按的那個人自己的動作，
    # 在他自己那一把行動鎖裡做；對方那一份照 social 的做法拿（_peer：此刻在這裡的人、不補算時間、賽季接上這一份），做完存回去。收到的邀請也列在選單上
    # （invite:yes|no|cancel:<編號>，走 choose；假人照這條路答，玩家互動包 bots._answer_invite）。邀請存在這一季的 WorldState.invites。
    # 「是假人」不影響任何一句話。這裡留的是同一對人的帳與邀請框的一行委派（第 37 批），加結伴同行的一行委派（移動包 party.py，第 48 批）。

    # ── 論武（玩家互動第二層）：兩個人各出一個意境合成一個新的，兩人都拿到；首創算兩人共有，價錢各付一半 ──
    # 走 fusion.merge（fusion.Partner：對方出的那一個不必是你的、不佔你的持有）；持有上限、「已經有了」照舊各自擋。
    # 武學不再拿來合（Joy 2026-10-21），論武跟著只剩意境。
    # 開爐的是答應的那一方（玩家互動包 discuss_actions：request 是 A 段，伺服器在鎖外取名〔server.prepare_peer、screen_peer〕，discuss 是 C 段；全部拆包第 38 批），
    # 發邀請的那一方接著照配方合出同一門。這裡留的是測試叫的一行委派。

    @staticmethod
    def _spar_power(who: Game, against: Game, *, seal: bool = True) -> float:
        """這個人切磋時的威力：只算本人（同伴、部下不上場），照對手身上那一門武學的屬性算相剋，吃自己的氣血係數與加成。
        seal=False 不含玉璽碎片的戰力（買兇的殺手照它浮上來，同江湖水漲）。"""
        s, c, w = who.state, who.content, who.world
        with team.facing_player(c, s, against.state, against.world):  # 五項屬性的季：照對手本人的五項對抗（他的統御擋你的武力）
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

    # ── 截殺（Config.raid；企劃者 2026-10-08 在決策卡選「有限制地開」）：玩家卡上的一顆鈕，不必對方同意 ──
    # 每季都有、不看第一季開關（企劃者 2026-10-10，懸賞榜設計 2.2）；Config.raid.enabled 是主機的緊急開關，關著時通緝一起收。
    # 兩個人都投靠了陣營、而且是不同陣營時才有（三個陣營彼此都是敵對）；散人只能截殺自己揭了通緝的那個人。對方下線、在忙也照打：
    # 他在「此地還有」的名單上（presence_seconds 內同步過、不在路上）就行，他回來在戰報與江湖紀錄裡看得到。真人假人一樣。

    @staticmethod
    def _raid_key(attacker: str, target: str) -> str:
        return f"{name_key(attacker)}>{name_key(target)}"

    # ── 後期體力玩法第一批（Joy 2026-10-16）：設伏劫道、屯糧練兵（本體在 tianxia/features/stamina_plays/；修築工事 2026-10-27 跟著舊拔河拿掉）──

    def _stamina_play_options(self) -> list[Option]:
        """「此地還能做」裡的體力玩法：序章裡、休季沒有；設伏／收伏、屯糧在體力玩法包（stamina_actions.options），接在後面的是護衛、
        功能包的選項（FEATURES 照順序）、盤算。順序是這樣就不能把設伏屯糧改成 Feature.options 登記（會排進 FEATURES 的順序，跑到護衛之後）：先後在 MENU_ORDER["plays"]（core_seams）。"""
        if prologue_rules.active(self.state, self.content) or self.state.world.ended:
            return []
        return features_core.menu_lines("plays", _MENU_CORE["plays"], self)

    # 設伏劫道、屯糧練兵的本體在功能包 tianxia/features/stamina_plays/（全部拆包第 39 批）；這裡留一行委派給 sync、_arrivals 與測試

    # ── 單人頭目戰（Joy 2026-10-10：「有種打小 boss 的感覺，也可以算是大事件的單人體驗版，可以放手一搏自訂行動」）：本體在功能包
    # tianxia/features/bout/duel_actions.py（全部拆包第 12 批），這裡留一行委派——server 的輸入框與鎖外三段式、腳本、測試，與核心原位的
    # choose（出招不建紀錄）、打到一半的選單（_everyday_options）、場景卡、探索撞上頭目、奪璽單挑的陣營名；只有包裡叫的那幾個
    # （_duel_after、_bout_rng……）不留 ──

    DUEL_GAMBLE_NOTE = bout_rules.DUEL_GAMBLE_NOTE  # 頭目戰、擂台的輸入框底下那一句（tests/server/test_server 從 game. 讀；字在單挑包）

    # ── 擂台（Joy 2026-10-14 選「隨時挑擂」：報名留分身，別人隨時來挑，照積分排名，只算本季）：本體在功能包
    # tianxia/features/bout/arena_actions.py（全部拆包第 12 批），這裡留一行委派——server 的看台三段式、假人、測試，與核心原位的
    # choose（灰掉的挑擂鈕、出招不建紀錄）、閉關中與路上的入口、場景卡、sync 的補送、店面那一頁。坐在擂台邊的選單、此地還能做的入口、
    # 收店、打開擂台、報名與挑人換成單挑包的店面登記、act 子動詞與 choose 掛鉤；擂台的名次與稱號在核心 tianxia/core/arena_ranks.py ──

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
        notes = self._note_action(action) if guide else []
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

    SELF_IN_TEAM = companions_actions.SELF_IN_TEAM  # 名冊上本人、部下那兩句（搬進人物情誼包；tests/battle/test_ranks.py 讀 Game.FOLLOWER_IN_TEAM）
    FOLLOWER_IN_TEAM = companions_actions.FOLLOWER_IN_TEAM

    # ── 門下頁面：武學說明（全部拆包第 23 批：修練頁的唯讀資料在修練包 tianxia/features/cultivation/view.py，這裡留一行委派）──────

    def heal_button(self) -> dict:
        """修練頁療傷鈕按不按得下去與不能按的原因（FB-082，見 skillview.heal_button）。"""
        return skillview.heal_button(self.state, self.content)

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
        if record is not None:  # 戰報頁那一筆（接縫掛鉤，第 11 批）：決戰包——決戰照 battles 表重讀完整戰況（收場之後才補上的放手一搏劇情也在）
            record = features_core.record_detail(self, record)
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

    # ── 大地圖 ────────────────────────────────────────────

    # ── 管理者 ────────────────────────────────────────────

    def is_admin(self) -> bool:
        """暫時用名號認管理者（content/config.json 的 admins）；線上架構會換成帳號權限。"""
        return self.state.player.name in self.content.config.admins

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

    # 立刻開戰的選單、立刻開戰、取消決戰（admin_battles、admin_start_battle、admin_cancel_battle）與三場大戲那三顆鈕：本體在
    # tianxia/features/battle/admin.py（全部拆包第 6 批），這裡留一行委派

    # ── 管理者：每週的事（管理者觸發鈕第 1 組，企劃者 2026-10-07）────────────
    # 「效果跟自然發生一樣」：每一顆都叫週一掛鉤（world.WEEK_HOOKS）用的同一個函式，不另寫一份。

    # ── 管理者：玉璽碎片（玉璽碎片設計第十二節；公告不寫管理者，效果跟自然發生一樣）──────────

    # ── 管理者：三場大戲（管理者觸發鈕第 3 組）──────────────────────
    # 「立刻開戰」（admin_start_battle）早就照時刻表開時刻表決戰（world.open_showdown：照版本挑那一筆、照前線戰況定起點、
    # 在 WorldState.showdowns_opened 記下開過了，時間到了不再開）。這裡只是每一場一顆鈕、照時刻表的大事認，按不下去時說清楚為什麼。
    # 本體在 tianxia/features/battle/admin.py（全部拆包第 6 批），這裡留一行委派。

    # ── 玩家之間的互動（social.py，企劃者 2026-10-08）────────────────────
    # 同一個地點的人看得到彼此：場景底下一行「此地還有誰」、點名字打開玩家卡、卡上的動作鈕（social.ACTIONS）。
    # 替對方寫東西（收到的禮、邀請、招呼）在同一把行動鎖裡讀他的存檔、改完存回去；不替他補算時間——補算會把他的
    # last_real 推到此刻，下了線的人就會一直掛在名單上。真人假人一樣對待（伺服器假人設計第五節）。

    # ── 名帖（Joy 2026-10-19；tianxia/mingtie.py 的說明）與贈物一天的次數 ──

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

    # ── 畫面文字 ──────────────────────────────────────────

    def location_text(self) -> str:
        loc = self.content.locations[self.state.player.location]
        # 地點會變樣（世界活起來第二批）：不是太平的地方，地名那一行底下多一段「〔戰火〕這一帶剛打過仗……」；地名那一行不動
        # （有畫時網頁照 scene_art 的 head 把它拿掉、疊在畫上）。太平、關著一個字都不變
        mood = place_state.view(self.state.world, self.content, loc.id)
        head = f"【{loc.name}】危險 {'★' * loc.danger}" + (f"\n\n〔{place_state.NAMES[mood['kind']]}〕{mood['line']}" if mood is not None else "")
        if jianfa(self.content, self.state.world, "marks_visible"):  # 減法季批 4：痕跡過了門檻，描寫多接一段（marks.describe）
            return f"{head}\n\n{marks_rules.describe(loc, self.state.world, self.content)}"
        return f"{head}\n\n{loc.describe(self.state.world.flags)}"  # 宛城的描寫隨版本換

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
            own = story_base.stage_art(s, c)  # 一條線事件段的專屬圖（StoryStage.image）蓋過事件的類型圖
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
        art = {"kind": "place", "path": path, "title": loc.name, "sub": f"危險 {'★' * loc.danger}", "head": f"【{loc.name}】危險 {'★' * loc.danger}"}
        mood = place_state.view(s.world, c, loc.id)  # 地點會變樣：疊在畫上的那一行多寫此刻的樣子，畫照樣子換色調（網頁的 mood-<kind>）
        if mood is not None:
            art["sub"] += f"・{mood['name']}"
            art["mood"] = mood["kind"]
        return art

    def scene_text(self) -> str:
        """有全服戰鬥時大家都看得到戰場；照常遊玩的人（集結中、只能觀戰、開打了還沒投效的散人，見 _fighting），自己眼前的事
        （事件、對話、地點）接在戰場底下，不然遇到事件時只看得到選項、看不到事件本身。序章裡不畫戰場（_battle_for_me）。
        蓋在畫面上的問功能包（scene_over，接縫掛鉤，第 11 批）：決戰包回（戰場那一段, 要不要整個取代）。"""
        over = features_core.scene_over(self)
        if over is None:
            return self._own_scene_text()
        battle_scene, whole = over
        if whole:
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
        # 自己眼前的場景卡（接縫掛鉤，第 11 批）：宴客包——坐在宴席上那一張；有所感包（全部拆包第 24 批）——有所感的卡、特殊頓悟取名那一張
        seat = features_core.scene(self)
        if seat is not None:
            return seat
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
            return self._defect_scene()  # 「叛投X」的確認畫面（陣營包 defect_actions.scene，第 35 批）
        if s.player.picking_audience:
            title = SOCIAL_LIST_TITLE if precise.on(c, s.world) else "求見"
            return f"**{title}**\n\n{self._audience_intro()}"
        asking = self._fs_asking_text() if omen_base.fs_answering(s) else None
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

    def _attr_rows(self, names: dict[str, str]) -> list[tuple[str, int, str]]:
        """狀態列的屬性（名字, 數值, 鍵）：舊的季照存檔的五屬性；五項屬性的季照 attrset 算（武力、統御……）。"""
        s, c = self.state, self.content
        if attrset.on(c, s.world):
            shown = attrset.names(c, s.world)
            return [(shown[k], int(attrset.value(s, c, k)), k) for k in attrset.keys(c)]
        return [(names[k], s.player.stats[k], k) for k in team.COMBAT_STATS]

    def status_data(self) -> dict:
        """狀態列的資料（數字與短字串），網頁前端照這份自己排版；status_text 是同一份資料的文字版。照 core/features.py 的 STATUS_ORDER["status"]
        一格一格合（全部拆包第 66 批：鍵的先後算行為）：包的格在各包的 status_slots，核心的格是這裡的閉包。"""
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

        def head(ctx, data) -> dict:
            return {
                "name": p.name,
                "affiliation": presence.affiliation(s, c),
                "ranger": ranger.status(s, c),  # 散人的遊俠名號（名號、階、俠名、下一階）；陣營的人、劇本沒有陣營、名聲開著是 None
                "renown": renown.status(s, c),  # 名聲（狀態列 1B、2C 的稱號與說明卡）；名聲關著是 None
            }

        def manual(ctx, data) -> dict:
            return {
                # 武學譜（口訣與秘方）：這一季聽過口訣或合中過的秘方，一條一筆 {"clues": [聽過的口訣], "solved": 名號或 None}
                "manual": secret_recipes.view(s, c, self.world),
                "manual_total": secret_recipes.progress(s, c, self.world)[1],  # 武學譜入口的分母：這一季全服共有幾條（不是「你聽過的」）
            }

        def forge_manual(ctx, data) -> dict:
            # 鑄譜（打造的隱藏配方）：這一季聽過口訣或打中過的，一條一筆 {"clues", "solved", "recipe"}（打造隱藏配方設計 6.3）
            return {"forge_manual": forge_secrets.view(s, c, self.world)}

        def self_row(ctx, data) -> dict:
            return {
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
                **({"xinshen": self.xinshen_view()} if xinshen.on(c) else {}),  # 心神（跟人物交談扣的）：關著時沒有這個鍵，畫面照舊
            }

        def vitals(ctx, data) -> dict:
            return {
                "hp": round(now),  # 跟角色卡（skillview.member_card 的 {:.0f}）同一種進位：兩邊寫出來的數字一樣
                "hp_max": round(cap),
                "injury": int(p.member.injury),
                "silver": p.stats.get("silver", 0),
                "xinde": p.stats.get("xinde", 0),
                "minor": [(names[k], p.stats.get(k, 0)) for k in ("fame", "good", "evil")],
                "attrs": self._attr_rows(names),  # 第三項是鍵：配點鈕送它（allocate_stat）
                "stat_points": p.stat_points,
                "stat_cap": c.config.stat_cap if not attrset.on(c, s.world) else 10**9,  # 五項屬性的季沒有上限
                **({"growth": attrset.view(s, c)} if attrset.on(c, s.world) else {}),  # 挑成長配比的那一塊（屬性與跨季架構 v2 3.1）
                # 歷練：這一季從事件得來的屬性有多少、上限多少（展開的屬性底下那一條，企劃者 2026-11-05）
                **({"lilian": {"have": attrset.event_total(s), "cap": c.config.attributes.v2.event_cap}} if attrset.on(c, s.world) else {}),
                # ＋鈕底下那一行：五項各管什麼、事件檢定也看它們（計畫二最終審查 M2）；網頁只在有點可配時畫
                "stat_uses": skillview.stat_uses(c, s),  # 減法季屬性五段開著時寫「現在給你什麼」的數字（設計 4.5）
                "stat_uses_note": skillview.STAT_CHECK_NOTE,
                # 心得付得起、又真的有事可做時才有；籌備中練成、合成都被擋，不提示（explain-2 審查 Minor 1）
                "hint": None if self._preparing() else skillview.practice_hint(s, c),
                "team": mates,
                "busy_hours": None if p.busy_until is None else round((p.busy_until - w.time) / HOUR / c.config.time_scale, 1),  # 現實小時
            }

        def help_row(ctx, data) -> dict:
            # 點體力條看的說明（explain-1）：怎麼回、新手期、回體丹（一天的上限）或補滿，數字全讀設定；體力條上沒有那顆鈕（序章、沒丹）就不提它
            newbie = roster.newbie(s, c, c.config.newbie_stamina_days)
            return {
                "stamina_help": self._stamina_help(newbie, data["pills"] is not None),
                # 江湖頁行動列底下的「玩法說明」入口（explain-2）：新手期（跟體力回復加快同一段，newbie_stamina_days）才有、序章裡沒有（師父會說）；
                # 過了新手期只剩設定抽屜那一顆
                "howto_entry": newbie and not prologue_rules.active(s, c),
            }

        def war(ctx, data) -> dict:
            if not season_one(c, w):  # 第一季濃縮版：江湖頁的三條戰況與三方態勢；開關關著時沒有這兩個鍵，畫面照舊
                return {}
            # FB-065：圖卡畫亂局帶（兩端讀設定，跟 in_chaos 同一份、含兩端）、標出在亂局裡的戰線；態勢那一行的說明也由這裡給，
            # 前端不寫死 35／65，也不自己數條數。全服公開的戰況，誰看都一樣
            in_the_chaos = set(chaos_fronts(s, c))
            return {
                "fronts": [
                    {"id": tid, "name": trend_name(c, tid), "value": trend_value(s, c, tid), "chaos": tid in in_the_chaos}
                    for tid in front_ids(c)
                ],
                "chaos_band": {"low": c.config.chaos_low, "high": c.config.chaos_high},
                "stances": stances(s, c),
                "stance_notes": {"sum": stance_sum_note(c)},
                "stance_rule": stance_rule_note(s, c),  # 態勢卡底下的收季規則（正式版辛）
                # 點戰況圖卡、態勢、大事、主線看的說明（explain-2）：這一季在打什麼、亂局、大事怎麼定、你能怎麼出力。
                # 門檻讀設定、此刻在亂局的讀 chaos_fronts、大事的件數讀時刻表（howto.war_help）；網頁點開才畫，不推動第一屏
                "war_help": self._war_help(),
            }

        core = {"head": head, "manual": manual, "forge_manual": forge_manual, "self": self_row, "vitals": vitals,
                "calendar": lambda ctx, data: self._calendar_status(),  # 第一季：季曆與下一件大事的倒數；開關關著時沒有這兩欄
                "help": help_row, "war": war}
        return features_core.status_run("status", core, {}, self)

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
        huangjin = values.get(HUANGJIN, 0)
        standing = {"guan": 100 - huangjin, "huang": huangjin}
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
            parts.append(f"**{trend.name}** {value}/100\n\n`{bar}`\n\n{trend.desc}")
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
        champs = arena_ranks.champions([(number, [e.text for e in self.state.world.chronicle])]
                                 + [(n, [e.text for e in entries]) for n, entries in past])  # 歷屆擂主（跨季）
        if champs:
            parts.append(champs)
        if seal_base.on(self.content):  # 七格玉璽排在江湖史最上面（第十節）；舊的碎片紀錄只當前史一行（11.5）
            old, view = self.world.get_jade_seal_fragments(), self.world.seal_state()
            parts.insert(0, seal_base.chronicle_block(self.content, view.registry, self.world.jade_seal_summary() if old else "",
                                                      mandate=seal_base.mandate_now(view.registry, view.season)))  # 天命之季多一句（玉璽二）
        else:
            parts.append(self.world.jade_seal_summary())
        return "\n\n---\n\n".join(parts)

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
        if self._opening_pending():
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


# core_api（第二輪第 72 批）：包的一行委派搬進各包的 game_api.py，這裡掛一次（`g.xxx` 照舊）。放檔尾：Game 要先定義好，各包的模組此刻都已載入，sys.modules 的先後不變。
features_core.attach_game_api(Game)
