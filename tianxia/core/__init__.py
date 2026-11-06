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
  頭目戰、擂台（單挑包）與奪璽單挑（已進玉璽包 features/seal/duel_rules.py）共用，單挑包的 duel_rules re-export 同一批函式物件。同 event_check 不進 MODULES。
- arena_ranks.py（bout：全部拆包第 12 批）：擂台的名次與稱號（on、entry_of、ladder、title_of、title_for、record_text、board、歷屆擂主）
  ——查詢服務：酒肆包的名氣、名帖、玩家卡、榜單、事件分級、江湖史讀它；單挑包的 arena_rules re-export 同一批。同 event_check 不進 MODULES。
- annal_base.py（zhuan：全部拆包第 29 批之二）：行狀「記一筆」的那一半——note、entry、trim、kept_names、clip、first_sentence、figure_name、on、heard、
  盯狀態變化的 mark、watch，與種類常數（SHOWDOWN…STORY、KINDS、GROUPS、UNHEARD）；engine、event_check、fusion 與各包記行狀都經它。
  查詢與行狀頁那一半（profile、standing、tier_*、xingshi_notes、rows）在列傳包 features/zhuan/standing.py；舊名 tianxia/annals.py 是指到
  standing 的 sys.modules 別名（standing re-export 這裡的名字，兩半都拿得到）。同 event_check 不進 MODULES。
- omen_base.py（military：全部拆包第 34 批）：機緣與伏筆「只讀」的那一小半——伏筆需求量的換算（scale、need）、天機表與題目（GUANYIN、
  TIANJI、FIGURE_SLOT、TIANJI_ANSWER、trips、asks_of）、召見與叛投確認畫面讀的機緣（done_for_rank、in_plot）；rules、content、ranks、
  defection 讀它，軍情包的 fs_rules、opp_rules re-export 同一批。同 event_check 不進 MODULES。
  core_world2（全部拆包第 40 批）再收伏筆與機緣「讀」的那一半：fs_active、event_ids、held_items、heard_texts（與填字的 fill 那一串）、
  opp_active、heard_clues，與新的 clue_count——events、narration、rumor_view、殼的門下頁、rules.check_condition 讀它。
- convoy_base.py（faction：全部拆包第 35 批）：押糧「只讀」的那一小半——手上押著糧車沒有（held）；叛投確認畫面（陣營包 defection.prompt）經它問，
  只讀軍情包認領的 PlayerState.convoy，不寫（寫與清照舊是軍情包的 convoy_actions）。同 event_check 不進 MODULES。
- feast_base.py（core_world2：全部拆包第 40 批）：宴席「讀」的那一半——on、find、is_open、open_feasts、hosting、toasted；人物活起來 figure_life
  （共用規則層）問誰在擺宴、書信的邀宴問開著的宴，宴客包的 rules re-export 同一批。設宴（寫）是世界層 life 那一格。同 event_check 不進 MODULES。
- smith_base.py（core_world2：全部拆包第 40 批，第 41 批 PM 認定第 4 條）：打造單子「讀」的那一小半——GO_VERB、is_forge_step、is_step_line、
  draft_here、draft_stale（與 here、ARMOR_KIND、單子回話的八句常數）；engine 的 choose 與鐵匠鋪包收店那兩格（第 55 批）讀它，鐵匠鋪包的 smithing
  re-export 同一批。同 event_check 不進 MODULES。
- signature_base.py（core_seams：全部拆包第 55 批）：本命兵器「清失效參照」那一小半——owned、refresh_names；stale.mid 的 signature 那一格（engine._SEAM_CORE）讀它，
  裝備包的 signature_arms re-export 同一批。同 event_check 不進 MODULES。
# map2（全部拆包第 50 批「輿圖二」：atlas 收進共用規則層，讀包認領的欄位改問核心；計畫 docs/superpowers/plans/2026-11-07-輿圖包-第2批.md 1.5、1.6）
- explore_base.py：探索表的小字與小函式——LOSE_WORD、六種地點（TOWN…CAMP）、四類事（EVENT…INSIGHT、KINDS、FILL）、PLACE_WORDS、BEAT_MOSTLY、
  BALANCED、match、kind_of、mostly_of、table_weights、mostly_in、hint_in、terrain_tags；第 49 批寄放在 services.py 檔尾 # map 那一段，第 50 批
  一個字沒改移過來（services.py 不留 re-export）。探索包的 explore_rules、explore_actions、有所感包的 sensing、輿圖包的 mapdata re-export 同一批。
  跟探索包的 features/explore/explore_base.py（第 18 批）同檔名、不同模組，一律寫完整路徑。同 event_check 不進 MODULES。
- travel_base.py：結伴同行「只讀」的那一小半——跟著誰走在路上（following：tagalong 與 journey 都有值時回帶頭的人的名號）；共用規則層的
  atlas.travel_block 經它問，只讀移動包認領的 PlayerState.tagalong，不寫（寫與清照舊是移動包的 party）。移動包的 party re-export 同一個。
  同 event_check 不進 MODULES。
- omen_base.py 再收 fs_answering（正在答最後一步的題：PlayerState.fs_asking 有值）：atlas.travel_block 經它問，軍情包的 fs_rules re-export 同一個。
- omen_base.py 再收 heard_any（聽過伏筆片段了嗎：PlayerState.fragments 有值）：引導包碰到才說的提示 h_foreshadow 經它問（第 34 批認定第 9 條）。
- seal_base.py（seal：全部拆包第 27 批，PM 認定甲案）：玉璽碎片「讀」的那一小半——on、revamp_on、filled、key、holders、天命之爭（mandate_event、
  mandate_battle、is_mandate_battle、mandate_now）、保底收場 deserted、天命未定的兩句、挑戰者門檻與「戰功居前」（threshold、challenger_ok、
  hint_names、merit_hint）、璽動那一句 stir_text、起點偏移與那一句（lean_shift、lean_text、shift_text、MANDATE_SCENE、MANDATE_WEIGHT）、江湖史七格
  （chronicle_block、sink_text 與 BOOK_*）；核心的 world、engine 的管理者「定結果」與江湖史、決戰包的 view、progress 讀它，玉璽包的 seal.py
  re-export 同一批。同 event_check 不進 MODULES。
- battle_base.py（battle：全部拆包第 54 批）：全服決戰的資料型別與「讀」的那一半——全服狀態存的 BattleInstance、BattleRoundRecord、SiegeInfo 這些型別，加上核心、
  共用規則層、舊模組、別的包非讀不可的判定（move_scores、idle、merit、call_orders、outcome_reason、result_at、start_muster、shift_deadlines、assess_gamble、clean_story……，
  共 63 個名字）；world_state、sqlite_world、world、team、duel_base、seal_base、chiefs、conquest、event_llm、siege、tale、seal_duel、bot_policy、bot_runner、engine 與
  bout、seal、territory_acts、looks、faction 幾包讀它。規則那一半在決戰包 features/battle/instance.py，它 re-export 這裡的名字；舊名 tianxia/battle_instance.py 是指到
  instance 的 sys.modules 別名。同 event_check 不進 MODULES。

# bounties（全部拆包第 45 批：懸賞榜成包；計畫 docs/superpowers/plans/2026-11-07-懸賞榜包-第1批.md）
- cards.py：玩家卡的動作登記表——CardButton、CardAction、ACTIONS、register（原本在玩家互動包的 social.py，第 37 批 PM 認定第 3 條）；玩家互動包的卡模組與懸賞榜包的通緝都登記進這一張，
  social re-export 同一批物件。同 event_check 不進 MODULES。
- bounty_base.py：懸賞榜「別人讀」的那一半——字句（ENEMY、BOARD、OFFICIAL、STRANDED_*、LAPSED_SIDE、LAPSED_LEAN、BEATEN_OFFICIAL、RALLY_POSTED……）、榜（active、board_here、close_board、mine、visible、
  open_bounties）、標題與怎麼完成（title、how、issuer、enemy_name）、接不接得了（can_take、stranded、join_note、drop_stranded、hunting、official_hit）、委託（open_commissions、commission_line）、
  掛單的地點（_opened、_strike_spots）、人物掛的（post_rally、post_figure：會寫季，但只靠核心與共用層）；事件檢定、Game 原位、figure_life 與各包讀它，懸賞榜包的 rules re-export 同一批。同 event_check 不進 MODULES。

# mall（全部拆包第 58 批：商城收尾）
- name_base.py：保留的名號——FAMOUS_NAMES、reserved_names（原本在假人的 server_bots，它 re-export 同一批物件）；建角色、易名帖、假人取名共用，
  商城包問這裡、不 import 假人的模組。同 event_check 不進 MODULES。
# guide（全部拆包第 59 批「引導二」：玩法說明；計畫 docs/superpowers/plans/2026-11-06-玩法說明-第59批.md）
- howto_base.py：玩法說明兩包以上要用的那幾樣——一節的寫法 section、一成兩成 tenth、會推戰況的陣營 order_pushers、SOME_PLACES；各節在各包的 howto.py，
  順序在 features.py 的 HOWTO_ORDER。同 event_check 不進 MODULES。

第一階 ctx 就是 Game 本身，不另包一層（手冊 3.3）。
"""

# 核心的模組（tianxia/<名字>.py）：手冊 3.1 的十三個，加上 3.10 的錢包（wallet）與江湖紀錄（journal：PM 2026-10-31 定算核心——
# CLAUDE.md 區塊表把它列在「核心與存檔」，每個功能都寫江湖紀錄；手冊 3.1 由 PM 補）。用到它的有兩處，都照這一份：
# - tests/core/test_feature_boundaries.py：功能包能 import 的就是這幾個（加上 tianxia/core/），這幾個都不能 import 功能包；
# - scripts/test_for.py：改了這幾個跑核心測試＋煙霧＋自己檔名的測試（照語法樹讀這一行、不 import；test_test_for 守兩邊一樣）。
# 只寫字面的名字（test_for 用 ast.literal_eval 讀）。attrset（五項屬性，屬性與跨季架構 v2 第三節）跟 team 一起算核心：team、rules 讀它（合回 develop 2026-11-06，PM 認定第 1 條：tests/core/test_attrset.py 放進 test_for 的 NOT_CORE_TESTS，同 world、step）。
# core_world（全部拆包第 25 批）：world（世界一步、週初與每天、開季結算、收季、開集結）改成世界層掛鉤（core/features.py 的 WORLD_ORDER）、
# 不再 import 功能包之後收進來（總表第 15 列）。它還代叫幾個沒成包的舊模組（行尾標批號），核心 → 舊模組這一版照舊不掃（同 journal）。
# core_effects（全部拆包第 32 批，第 25 批 PM 認定第 2 條）：log_archive（換季時封存舊季的傳聞與回合紀錄；只 import 標準函式庫，
# 只有 sqlite_world 用）兩份名單都沒有，順手收進核心本體。它的 tests/core/test_log_archive.py（8 條）跟著進核心測試，不放進 NOT_CORE_TESTS。
MODULES = frozenset({
    "state", "sqlite_world", "world_state", "characters", "accounts", "database", "rules", "calendar", "models", "content",
    "team", "gender", "naming", "wallet", "journal", "attrset",
    "world",
    "log_archive",
    # core_step（全部拆包第 36 批）：step、weekcard 不再 import 包之後收進來（計畫 1.5 甲案）。懸賞榜兩格第 45 批由包登記（step._STEP_CORE 空了）；它們還
    # 讀章回（chapters），核心 → 舊模組這一版照舊不掃（同 world）
    "step", "weekcard",
})
