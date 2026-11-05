"""核心（開發規範手冊 docs/superpowers/specs/2026-10-30-開發模式-design.md 第三節）：功能包只能 import 這裡與核心的那幾個模組。

- MODULES（這個檔）：核心的那幾個模組，只有這一份。
- services.py：服務清單（功能包准叫的 Game 方法）、錢包服務（票的庫存與消耗）、共用的字。
- features.py：掛鉤（Protocol 與有預設值的基底）、核心照 FEATURES 彙整選項、分派、狀態、換日、換季、清失效參照。
- registry.py：FEATURES（有順序）；核心唯一 import 功能包的地方。
- swap.py：JSON 裡整個字串相等的換字（易名帖、資料庫改名共用）。
- event_check.py（core-events：全部拆包第 16 批）：事件檢定——端出事件卡、固定選項的檢定與結果、效果套用、事件裡打一場、隨口應對的
  三段式；本體從 Game 搬來，Game 留一行委派。核心本體的一部分（tianxia/core/ 底下的檔本來就算核心：功能包可以 import、它不 import 包），
  不進 MODULES（那一份是 tianxia/<名字>.py 頂層的核心模組）、不進 FEATURES（它不是包、沒有掛鉤與前綴）。
- duel_base.py（bout：全部拆包第 12 批）：單挑底層——剋、推力、挨打、防具、放手一搏擲一次、勝負、架勢、氣勢的字、選單上的一招、Scene；
  頭目戰、擂台（單挑包）與奪璽單挑（seal_duel.py）共用，單挑包的 duel_rules re-export 同一批函式物件。同 event_check 不進 MODULES。
- arena_ranks.py（bout：全部拆包第 12 批）：擂台的名次與稱號（on、entry_of、ladder、title_of、title_for、record_text、board、歷屆擂主）
  ——查詢服務：酒肆包的名氣、名帖、玩家卡、榜單、事件分級、江湖史讀它；單挑包的 arena_rules re-export 同一批。同 event_check 不進 MODULES。
- omen_base.py（military：全部拆包第 34 批）：機緣與伏筆「只讀」的那一小半——伏筆需求量的換算（scale、need）、天機表與題目（GUANYIN、
  TIANJI、FIGURE_SLOT、TIANJI_ANSWER、trips、asks_of）、召見與叛投確認畫面讀的機緣（done_for_rank、in_plot）；rules、content、ranks、
  defection 讀它，軍情包的 fs_rules、opp_rules re-export 同一批。同 event_check 不進 MODULES。
- convoy_base.py（faction：全部拆包第 35 批）：押糧「只讀」的那一小半——手上押著糧車沒有（held）；叛投確認畫面（陣營包 defection.prompt）經它問，
  不碰軍情包認領的 PlayerState.convoy。同 event_check 不進 MODULES。

第一階 ctx 就是 Game 本身，不另包一層（手冊 3.3）。
"""

# 核心的模組（tianxia/<名字>.py）：手冊 3.1 的十三個，加上 3.10 的錢包（wallet）與江湖紀錄（journal：PM 2026-10-31 定算核心——
# CLAUDE.md 區塊表把它列在「核心與存檔」，每個功能都寫江湖紀錄；手冊 3.1 由 PM 補）。用到它的有兩處，都照這一份：
# - tests/core/test_feature_boundaries.py：功能包能 import 的就是這幾個（加上 tianxia/core/），這幾個都不能 import 功能包；
# - scripts/test_for.py：改了這幾個跑核心測試＋煙霧＋自己檔名的測試（照語法樹讀這一行、不 import；test_test_for 守兩邊一樣）。
# 只寫字面的名字（test_for 用 ast.literal_eval 讀）。
# core_world（全部拆包第 25 批）：world（世界一步、週初與每天、開季結算、收季、開集結）改成世界層掛鉤（core/features.py 的 WORLD_ORDER）、
# 不再 import 功能包之後收進來（總表第 15 列）。它還代叫幾個沒成包的舊模組（行尾標批號），核心 → 舊模組這一版照舊不掃（同 journal）。
# core_effects（全部拆包第 32 批，第 25 批 PM 認定第 2 條）：log_archive（換季時封存舊季的傳聞與回合紀錄；只 import 標準函式庫，
# 只有 sqlite_world 用）兩份名單都沒有，順手收進核心本體。它的 tests/core/test_log_archive.py（8 條）跟著進核心測試，不放進 NOT_CORE_TESTS。
MODULES = frozenset({
    "state", "sqlite_world", "world_state", "characters", "accounts", "database", "rules", "calendar", "models", "content",
    "team", "gender", "naming", "wallet", "journal",
    "world",
    "log_archive",
})
