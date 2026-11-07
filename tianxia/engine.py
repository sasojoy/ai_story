"""遊戲門面：介面層唯一需要呼叫的類別。負責行動、選項、時間流逝與畫面文字。

sanguo-companions 合併大幅重寫：拿掉 battle.py 的 3v3 全自動戰鬥、多隊派遣、招賢抽卡、
收徒系統，改成單次判定遭遇（encounter.py）、單一隊伍（最多 4 位同伴）、唯一同伴的
招募（roster.py）、練功（team.py：鍛鍊；開局送兩門基礎武學，自創武學已作廢）。
"""
from __future__ import annotations

import contextlib
import random
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from . import arts as arts_mod
# （cultivation：破境卡 ascend 全部拆包第 23 批搬進修練包，engine 不再用，拿掉）
from . import attrset  # 五項屬性（屬性與跨季架構 v2 第三節）
from . import narration  # 事件旁白每週改寫（減法季批 10）
from . import (
    allied, armor, atlas, battlelog, calendar, clinic, conquest, economy, encounter, equipment,
    fight_llm, figures, forge_secrets, gender, insight_fx, insights, journal, library, martial_arts, plans,
    materials, mounts, orders, precise, push, ranger, ranks, renown, rise, roster, rounds, seal_acts, secret_recipes, sensing,
    shopview, signature, art_cards,
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
    ears_of, game_day, here_regions,
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
from .core import combat  # 單打服務的本體（第二輪第 79 批：大場面、戰力快照、操練與立功、收場、本人對本人；Game 上留一行委派）。排在這裡：它 import 的模組這時都已經載入，載入的先後一個都不變
from .core.combat import FIGHT_GONE_LINES, LOW_HP_RATIO  # noqa: F401  server、tests/core/test_engine.py 從 engine 拿
from .core import pushing  # 推大勢的本體（第二輪第 80 批；Game 上留一行委派）。排在這裡：它 import 的模組這時都已經載入，載入的先後一個都不變
from .core import pills  # 回體丹的本體（第二輪第 80 批；Game 上留一行委派）。同上
from .core.pills import PILL_DAY_FULL, REFILL_FULL, REFILL_HUT, REFILL_LINE, REFILL_TITLE, _cn_count  # noqa: F401  tests/bots/test_pill_per_day.py、test_stamina_refill.py 從 engine 拿
from .core import presence  # 「此地還有」的判斷與身分字（全部拆包第 37 批：從 social 拆進核心）
from .core import signature_base  # 本命兵器的名字照內容讀（core_seams，全部拆包第 55 批：清失效參照 signature 那一格；原本經舊名 signature_arms 讀）
from .core import smith_base  # 打造單子讀的那一小半（全部拆包第 40 批，第 41 批 PM 認定第 4 條：choose 併成一則、讀檔與 sync 清單子，不經舊名 smithing）
# peers（全部拆包第 37 批）：玩家卡、邀請框、打招呼、贈物、名帖的 31 個方法搬進玩家互動包，Game 留 21 個一行委派（另加月旦評那一句）；
# 名帖遞帖的登記（mingtie_card）改在包載入時做；原本那兩行 invites、social 的 import 是切磋、論武還在原位用的，第 38 批搬進包之後沒人用，拿掉了
# peers2（全部拆包第 38 批）：切磋、論武、截殺的 28 個方法搬進玩家互動包；Game 留 13 個一行委派（論武 4、截殺 9；切磋沒有外面的呼叫端）
from .features.peers.invite_actions import INVITE_LAPSED, INVITE_LAPSED_AWAY  # noqa: F401  邀請沒成局的兩句：tianxia/features/peers/tests/test_discuss.py 從 engine 拿
from .core import arena_ranks, duel_base  # 擂台的名次與稱號、單挑底層（全部拆包第 12 批：留核心；擂台、頭目戰本身在單挑包）
from .core.event_check import EVIL_ANNAL, FREE_TEXT_OPTION, FreeTextOutcome, FreeTextRequest
from .core import page_view, status_view  # core_views（第二輪第 81 批）：狀態列、江湖頁與店面的本體（Game 上留一行委派）；排在上面的 import 都做完之後，載入的先後不變
from .core import scene_view  # core_scene（第二輪第 91 批）：場景卡的文字與圖（Game 上留一行委派；哪一張照 core/features.py 的 SCENE_ORDER）

HOUR = 3600
DAY = 86400
# （SECT_LABEL：拜入門派那一顆的字，全部拆包第 35 批搬進陣營包 features/faction/join_actions.py）
SUMMONS_LABEL = "應召晉升（召見在此・不花體力）"  # 待 joy 潤：一類一顆的應召（設計 9.1 第 1 組乙，橫幅上的字）
GENDER_SET = "往後江湖上以{word}相稱。"  # 設定頁選了性別（只能選一次）
GENDER_LOCKED = "性別已經定了，改不了。"

# （TollFacts、LOW_HP_RATIO 搬進核心的單打服務 tianxia/core/combat.py，第二輪第 79 批；_points 是死碼，拿掉。上面 import 回 LOW_HP_RATIO，`from tianxia.engine import LOW_HP_RATIO` 照舊）

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
# （FIGHT_LEFT、FIGHT_CHANGED、FIGHT_GONE_LINES 搬進 tianxia/core/combat.py，第二輪第 79 批；上面 import 回 FIGHT_GONE_LINES，server 照舊從 engine 拿）


class Refused(list):
    """choose() 回的話，而且這一下是被擋下來的：懸賞選項已經不在選單上（兩個分頁搶同一張，FB-162）、馬市的鈕已經灰掉（FB-195）。沒做事、沒寫江湖紀錄，
    所以伺服器要把這句話直接傳去網頁跳提示（server.api_choose 看 isinstance）。是 list 的子類，其他地方照一般的訊息清單用。
    不放在 Game 的欄位裡：同一個角色的兩個分頁共用同一個 Game，鎖放掉之後別的請求可能已經改掉欄位；回傳值跟著這一次請求走。"""


# 賽季籌備中的 PREPARING_TEXT、PREPARING_REFUSAL（全部拆包第 24 批）與裝飾器 _not_while_preparing（第 23 批）搬進核心的共用的字與小函式
# （tianxia/core/services.py）：上面 import 回來，`from tianxia.engine import PREPARING_REFUSAL` 照舊拿得到
GROWTH_PREFIX = "growth:"  # 開季準備卡上挑成長配比的鈕（growth:<配比>；growth:custom 只打開自己配的那一塊）
GROWTH_LOCKED = "這一季的成長配比已經定了，下一季開季再挑。"
GROWTH_CUSTOM_ASK = "（在卡上自己配五項，配好按「定下來」。）"
# （回體丹那一群的字 REFILL_*、PILL_DAY_FULL、CN_COUNTS、_cn_count 搬進 tianxia/core/pills.py，第二輪第 80 批；上面 import 回測試從 engine 拿的那幾個。PROLOGUE_REST 不是這一群，留這裡）
PROLOGUE_REST = "調息（照師父教的吐納，把體力調回來）"  # 序章教體力那一步（打坐 2026-10-12 拿掉，只留這一下）


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
    "open": page_view.OPEN_CORE,  # 店面登記的店（第 81 批：格搬進 core/page_view.py，_shop_open 也讀它）
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

    # 回體丹（_top_up_pills、take_stamina_pill、pill_now、pill_cap、pills_left_today）：本體在 tianxia/core/pills.py（第二輪第 80 批），這裡留一行委派；_refill_stamina 只有它自己叫，不留。_pill_day、_day_of、_pill_card_bonus 留原位
    def _top_up_pills(self) -> None:
        return pills.top_up_pills(self)

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
        note = art_cards.heal_note(s, c)
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
        return page_view.action_notes(self, option_ids)

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
    # 本體在 tianxia/core/combat.py（第二輪第 79 批），這裡留一行委派：server 的鎖外三段式、choose、事件檢定、各包在叫；_narrate 照舊是 staticmethod

    def is_big(self, squad: Squad) -> bool:
        return combat.is_big(self, squad)

    def _fight_squad(self, option_id: str) -> Squad | None:
        return combat.fight_squad(self, option_id)

    def fight_request(self, option_id: str) -> fight_llm.FightRequest | None:
        return combat.fight_request(self, option_id)

    def _checked_fight(self, option_id: str, fight: fight_llm.PreparedFight | None) -> fight_llm.PreparedFight | None:
        return combat.checked_fight(self, option_id, fight)

    def _fight_gone(self, fight: fight_llm.PreparedFight) -> str:
        return combat.fight_gone(self, fight)

    def _judged(self, squad: Squad) -> fight_llm.Judgment | None:
        return combat.judged(self, squad)

    def _fight_with(self, squad: Squad, judged: fight_llm.Judgment | None, **kw) -> encounter.EncounterResult:
        return combat.fight_with(self, squad, judged, **kw)

    def _style_note(self, squad: Squad, result: encounter.EncounterResult) -> list[str]:
        return combat.style_note(self, squad, result)

    def _terrain_note(self) -> list[str]:
        return combat.terrain_note(self)

    @staticmethod
    def _narrate(record, result: encounter.EncounterResult, judged: fight_llm.Judgment | None) -> None:
        return combat.narrate(record, result, judged)

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

    # 文字的事的貢獻：本體在 tianxia/core/pushing.py（第二輪第 80 批），這裡留一行委派
    def _deed_points(self, points: int, *, capped: bool = True) -> int:
        return pushing.deed_points(self, points, capped=capped)

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
        return scene_view.place_state_view(self)

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

    # 還推得動多少：本體在 tianxia/core/pushing.py（第二輪第 80 批），這裡留一行委派
    def _push_room(self, trend_id: str) -> float:
        return pushing.push_room(self, trend_id)

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
        return page_view._shop_say(self, key, problem)

    def _shop_after(self, problem: str | None, done: str, keyer=None) -> None:
        return page_view._shop_after(self, problem, done, keyer)

    def _shop_open(self) -> str | None:
        return page_view._shop_open(self)

    def _shop_live(self, option_ids=None, shop: str = "smith") -> bool:
        return page_view._shop_live(self, option_ids, shop)

    def shop_view(self, option_ids=None) -> dict | None:
        return page_view.shop_view(self, option_ids)



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
    # 戰力快照（_battle_power 到 _battle_neili_cap）的本體在 tianxia/core/combat.py（第二輪第 79 批），這裡留一行委派；_battle_mount 只有它自己叫，不留

    def _battle_power(self, *, seal: bool = True) -> float:
        return combat.battle_power(self, seal=seal)

    def _battle_scores(self, mounted: bool = True, *, seal: bool = True) -> dict[str, float]:
        return combat.battle_scores(self, mounted, seal=seal)

    def _battle_role(self) -> str:
        return combat.battle_role(self)

    def _battle_troops(self) -> tuple[str, float]:
        return combat.battle_troops(self)

    def _battle_gear(self) -> dict:
        return combat.battle_gear(self)

    def _battle_marks(self) -> dict:
        return combat.battle_marks(self)

    def _battle_road(self) -> str:
        return combat.battle_road(self)

    def _battle_neili_cap(self) -> float:
        return combat.battle_neili_cap(self)

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

    # 推大勢（season_scale 到 _carry、_push_progress、_event_progress、_goals、push_trend）：本體在 tianxia/core/pushing.py（第二輪第 80 批），這裡留一行委派；_resisted_line 只有它自己叫，不留
    def season_scale(self) -> float:
        return pushing.season_scale(self)

    def daily_push_cap(self) -> float:
        return pushing.daily_push_cap(self)

    def _resisted_lines(self) -> set[str]:
        return pushing.resisted_lines(self)

    def _shaped(self, trend_id: str, delta: float, source: str) -> tuple[float, bool]:
        return pushing.shaped(self, trend_id, delta, source)

    def _carry(self, trend_id: str, amount: float) -> int:
        return pushing.carry(self, trend_id, amount)

    # 操練的帳：本體在 tianxia/core/combat.py（第二輪第 79 批）；_exp_changes 只有它自己叫，不留委派
    def _drill_gains(self, squad: Squad, share: float | None = None, source: str = "hold", echo: bool = True) -> list[str]:
        return combat.drill_gains(self, squad, share, source, echo)

    # ── 出陣（出陣探索與地盤設計第二節）：本體在功能包 tianxia/features/sortie/actions.py（主動搬六包第 1 批），這裡留一行委派 ──

    def _push_progress(self, loc_id: str, nominal: float, source: str, how: str | None = None) -> list[str]:
        return pushing.push_progress(self, loc_id, nominal, source, how)

    def _event_progress(self) -> list[str]:
        return pushing.event_progress(self)

    # ── 一條線（特殊事件與特殊頓悟的底座）：本體在 tianxia/features/story/actions.py（全部拆包第 30 批），這裡留一行委派 ──
    # （_story_act、_story_fight、_story_bout 只有包裡叫：story: 由 choose 掛鉤接走，不留）

    def event_tier(self) -> dict | None:
        return event_check.event_tier(self)

    # ── 混戰（翻地與爭搶，輿圖簡化設計 4.3）、出陣的鈕、出陣、獎勵、守：本體在 tianxia/features/sortie/actions.py，這裡留一行委派 ──

    # 天下聞名點名、立功給名望、戰報的經驗（_famed_news、_deed_fame、_record_exp）：本體在 tianxia/core/combat.py（第二輪第 79 批）
    def _famed_news(self, place: str, foe: str, tier: str) -> None:
        return combat.famed_news(self, place, foe, tier)

    def _deed_fame(self, kind: str) -> list[str]:
        return combat.deed_fame(self, kind)

    def _record_exp(self, record, exp: int, source: str = "battle") -> list[str]:
        return combat.record_exp(self, record, exp, source)

    # ── 出陣約戰（減法季批 3b；整合設計 4.3）：本體在 tianxia/features/sortie/duel_actions.py，這裡留一行委派（主動搬六包第 2 批）──
    # 貼、應戰、同去、兩張卡（server、假人、測試在叫）；三處結算（world_tick、sync、advance）與假人程式那一下；核心原位那幾處

    # 收場：本體在 tianxia/core/combat.py（第二輪第 79 批），這裡留一行委派；_trait_say、_trait_lines 只有它們自己叫，不留
    def _lose_silver(self, record) -> list[str]:
        return combat.lose_silver(self, record)

    def _player_hp_and_cap(self) -> tuple[float, float]:
        return combat.player_hp_and_cap(self)

    def _player_hp(self) -> float:
        return combat.player_hp(self)

    def _hp_facts(self, healed: tuple[str, ...] = ()) -> combat.TollFacts:
        return combat.hp_facts(self, healed)

    def _take_toll(self, tier: str, *, wild: bool = False, clash: tactics.Clash | None = None, squad: Squad | None = None,
                   ) -> tuple[list[str], int, combat.TollFacts]:
        return combat.take_toll(self, tier, wild=wild, clash=clash, squad=squad)

    def _play_rounds(
        self, record, squad: Squad, tier: str, hp_lost: int | None, facts: combat.TollFacts | None = None, clash: tactics.Clash | None = None,
    ) -> None:
        return combat.play_rounds(self, record, squad, tier, hp_lost, facts, clash)

    # ── 挑戰大勢人物本人（計畫 T4、軍令文件 4.5）─────────────
    # _story_squad、_tier3 的本體在 tianxia/core/combat.py（第二輪第 79 批）

    def _story_squad(self, squad: Squad) -> Squad:
        return combat.story_squad(self, squad)

    def _tier3(self, squad: Squad, record, chance: float, tag: str, source: str) -> list[str]:
        return combat.tier3(self, squad, record, chance, tag, source)

    def _goals(self) -> dict[str, int]:
        return pushing.goals(self)

    def push_trend(self, trend_id: str, delta: float, *, source: str) -> list[str]:
        return pushing.push_trend(self, trend_id, delta, source=source)

    # 獎勵、頓悟的契機、歸檔（_battle_rewards、_seize、_file_battle）：本體在 tianxia/core/combat.py（第二輪第 79 批）；_thin_drops 只有它自己叫，不留委派
    def _battle_rewards(self, squad: Squad, record, max_tier: int | None = None) -> list[str]:
        return combat.battle_rewards(self, squad, record, max_tier)

    def _seize(self, record, draw: bool = False) -> list[str]:
        return combat.seize(self, record, draw)

    def _file_battle(self, record, wear: bool | None = None, armor_wear: bool | None = None, team_exp: bool = True) -> str:
        return combat.file_battle(self, record, wear, armor_wear, team_exp)

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
        return pills.take_stamina_pill(self, pill_only=pill_only)

    # ── 每日簽到：本體在 tianxia/features/checkin/actions.py（全部拆包第 30 批），這裡留一行委派 ──

    # ── 領地爭奪：翻地與爭搶（輿圖簡化設計第四章）——戰書、換天的掛鉤、分紅送到、畫面資料。投票與 22:00 公告結算拿掉了（PM 2026-10-20）──

    def _conquest_side(self) -> str | None:
        """替哪一軍推進度、下戰書、打攻城（豪強分屬兩軍：依附的那一軍）；散人、不是兩軍是 None。"""
        side = allied.side_of(self.state, self.content)
        return side if side in conquest.SIDES else None

    # ── 〈天下形勢〉（領地爭奪第三批 A；tianxia/xingshi.py，計畫第五章 Task 16、17）──

    def pill_now(self) -> float:
        return pills.pill_now(self)

    def _pill_day(self) -> int:
        """現在是第幾天（Config.pill_day_utc_offset_hours 的時區、00:00 換日；從 1970-01-01 起算）。"""
        return self._day_of(self.pill_now())

    def _day_of(self, t: float) -> int:
        """現實時間 t 是回體丹那一套的第幾天（_pill_day 照它算；sync 拿它比上一次同步是不是換了一天）。"""
        return int((t + self.content.config.pill_day_utc_offset_hours * HOUR) // (24 * HOUR))

    def pill_cap(self) -> int:
        return pills.pill_cap(self)

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
        return pills.pills_left_today(self)

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

    # 本人對本人（_spar_power、_spar_mirror）的本體在 tianxia/core/combat.py（第二輪第 79 批）；照舊是 staticmethod（懸賞、玉璽的測試用 staticmethod 換 _spar_power）
    @staticmethod
    def _spar_power(who: Game, against: Game, *, seal: bool = True) -> float:
        return combat.spar_power(who, against, seal=seal)

    @staticmethod
    def _spar_mirror(result: encounter.EncounterResult, power: float) -> encounter.EncounterResult:
        return combat.spar_mirror(result, power)

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
        """修練頁療傷鈕按不按得下去與不能按的原因（FB-082，見 art_cards.heal_button）。"""
        return art_cards.heal_button(self.state, self.content)

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
        return scene_view.location_text(self)

    def scene_art(self) -> dict | None:
        return scene_view.scene_art(self)

    def scene_text(self) -> str:
        return scene_view.scene_text(self)

    def _own_scene_text(self) -> str:
        return scene_view._own_scene_text(self)

    def feature_status(self) -> dict:
        """功能包合進江湖畫面頂層的資料（FEATURES 的 status，照清單的順序；例：商城的入口 main.mall）。server.main_view 放在原本商城那一格。"""
        return features_core.status(self)

    def status_data(self) -> dict:
        return status_view.status_data(self)

    def bulletin(self) -> list[str]:
        return page_view.bulletin(self)

    def season_result(self) -> dict | None:
        return page_view.season_result(self)

    # ── 三陣營四勝利（減法季整合設計第三章；計畫 Task 3c-2、3c-3：欄位表 main.ending；三方卡與「你這一步」補在批 1 的 weekcard 裡）──

    def place_minutes(self, loc_id: str) -> int | None:
        return page_view.place_minutes(self, loc_id)

    def stamp(self, time: float, clock: bool = True) -> str:
        """玩家看得到的遊戲時間（江湖紀錄、江湖史、傳聞、戰報、路上）：第一季寫成季曆，其他時候照舊（calendar.stamp_text）。"""
        return calendar.stamp_text(time, self.content, self.state.world, clock=clock)

    def status_text(self) -> str:
        return status_view.status_text(self)

    def trends_text(self) -> str:
        return page_view.trends_text(self)

    def rumors_text(self, limit: int = 30) -> str:
        return page_view.rumors_text(self, limit)

    def rumor_layers(self) -> list[dict[str, str]] | None:
        return page_view.rumor_layers(self)

    def chronicle_text(self) -> str:
        return page_view.chronicle_text(self)

    # ── 江湖紀錄 ──────────────────────────────────────────

    def _day_stamp(self, time: float) -> str:
        return page_view._day_stamp(self, time)

    def latest_entry_html(self) -> str:
        return page_view.latest_entry_html(self)

    def journal_top_html(self) -> str:
        return page_view.journal_top_html(self)

    def now_entry_html(self) -> str:
        return page_view.now_entry_html(self)

    def now_front(self) -> dict | None:
        return page_view.now_front(self)

    def journal_html(self, start: int = 1, limit: int = 5, heading: str = "", empty: str = "") -> str:
        return page_view.journal_html(self, start, limit, heading, empty)

    def shows_battle_card(self) -> bool:
        return page_view.shows_battle_card(self)

    def battle_extra_html(self, for_card: bool = False) -> str:
        return page_view.battle_extra_html(self, for_card)

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


# core_api（第二輪第 72 批）：包的一行委派搬進各包的 game_api.py，這裡掛一次（`g.xxx` 照舊）。放檔尾：Game 要先定義好，各包的模組此刻都已載入，sys.modules 的先後不變。
features_core.attach_game_api(Game)
