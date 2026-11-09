"""核心（開發規範手冊 docs/superpowers/specs/2026-10-30-開發模式-design.md 第三節）：功能包只能 import 這裡與核心的那幾個模組。

- MODULES（這個檔）：核心的那幾個模組，只有這一份。
- services.py：錢包服務（票的庫存與消耗）、共用的字；services_list.md：服務清單（功能包准叫的 Game 方法）。
- tuning/：新包的 Config 子模型，一包一檔（第二輪第 74 批；scripts/new_feature.py 生，models.py 引用）。
- features.py：掛鉤（Protocol 與有預設值的基底）、核心照 FEATURES 彙整選項、分派、狀態、換日、換季、清失效參照。
- registry.py：FEATURES（有順序）；核心唯一 import 功能包的地方。
- swap.py：JSON 裡整個字串相等的換字（易名帖、資料庫改名共用）。
- event_check.py（core-events：全部拆包第 16 批）：事件檢定——端出事件卡、固定選項的檢定與結果、效果套用、事件裡打一場、隨口應對的
  三段式；本體從 Game 搬來，Game 留一行委派。核心本體的一部分（tianxia/core/ 底下的檔本來就算核心：功能包可以 import、它不 import 包），
  不進 MODULES（那一份是 tianxia/<名字>.py 頂層的核心模組）、不進 FEATURES（它不是包、沒有掛鉤與前綴）。
- combat.py（core_combat：第二輪第 79 批）：單打服務——大場面判讀、戰力快照、操練的帳與立功、打完的收場、本人對本人、打一場的主流程（squad_encounter，第 98 批）；本體從 Game 搬來，Game 留一行委派。同 event_check 不進 MODULES、不進 FEATURES。
- pushing.py（core_pushing：第二輪第 80 批）：推大勢——push_trend、季長倍數、每人每日上限、事件五折與盡頭阻力、零頭、領地爭奪的進度、文字的事的貢獻；本體從 Game 搬來，Game 留一行委派。同 event_check 不進 MODULES、不進 FEATURES。
- pills.py（core_pushing：第二輪第 80 批）：回體丹——服一顆、一天的上限、測試期間的一鍵補滿、讀檔補丹與那幾句字；本體從 Game 搬來，Game 留一行委派（engine 照名字 import 回那幾句字）。同 event_check 不進 MODULES、不進 FEATURES。
- duel_base.py（bout：全部拆包第 12 批）：單挑底層——剋、推力、挨打、防具、放手一搏擲一次、勝負、架勢、氣勢的字、選單上的一招、Scene；
  頭目戰、擂台（單挑包）與奪璽單挑（已進玉璽包 features/seal/duel_rules.py）共用，單挑包的 duel_rules re-export 同一批函式物件。同 event_check 不進 MODULES。
- arena_ranks.py（bout：全部拆包第 12 批）：擂台的名次與稱號（on、entry_of、ladder、title_of、title_for、record_text、board、歷屆擂主）
  ——查詢服務：酒肆包的名氣、名帖、玩家卡、榜單、事件分級、江湖史讀它；單挑包的 arena_rules re-export 同一批。同 event_check 不進 MODULES。
- annal_base.py（zhuan：全部拆包第 29 批之二）：行狀「記一筆」的那一半——note、entry、trim、kept_names、clip、first_sentence、figure_name、on、heard、
  盯狀態變化的 mark、watch，與種類常數（SHOWDOWN…STORY、KINDS、GROUPS、UNHEARD）；engine、event_check、fusion 與各包記行狀都經它。
  查詢與行狀頁那一半（profile、standing、tier_*、xingshi_notes、rows）在列傳包 features/zhuan/standing.py（standing re-export 這裡的名字，兩半都拿得到）。同 event_check 不進 MODULES。
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
  共用規則層、假人殼、別的包非讀不可的判定（move_scores、idle、merit、call_orders、outcome_reason、result_at、start_muster、shift_deadlines、assess_gamble、clean_story……，
  共 63 個名字）；world_state、sqlite_world、world、team、duel_base、seal_base、chiefs、conquest、event_llm、siege、tale、seal_duel、bot_policy、bot_runner、engine 與
  bout、seal、territory_acts、looks、faction 幾包讀它。規則那一半在決戰包 features/battle/instance.py，它 re-export 這裡的名字。同 event_check 不進 MODULES。

# bounties（全部拆包第 45 批：懸賞榜成包；計畫 docs/superpowers/plans/2026-11-07-懸賞榜包-第1批.md）
- cards.py：玩家卡的動作登記表——CardButton、CardAction、ACTIONS、register（原本在玩家互動包的 social.py，第 37 批 PM 認定第 3 條）；玩家互動包的卡模組與懸賞榜包的通緝都登記進這一張，
  social re-export 同一批物件。同 event_check 不進 MODULES。
- bounty_base.py：懸賞榜「別人讀」的那一半——字句（ENEMY、BOARD、OFFICIAL、STRANDED_*、LAPSED_SIDE、LAPSED_LEAN、BEATEN_OFFICIAL、RALLY_POSTED……）、榜（active、board_here、close_board、mine、visible、
  open_bounties）、標題與怎麼完成（title、how、issuer、enemy_name）、接不接得了（can_take、stranded、join_note、drop_stranded、hunting、official_hit）、委託（open_commissions、commission_line）、
  掛單的地點（_opened、_strike_spots）、人物掛的（post_rally、post_figure：會寫季，但只靠核心與共用層）；事件檢定、Game 原位、figure_life 與各包讀它，懸賞榜包的 rules re-export 同一批。同 event_check 不進 MODULES。

# jieyi（結義第一、二批，Joy 2026-11-09「其他按照建議」「第二批也繼續做」）
- jieyi_base.py：結義「別人讀」的那一半——名號與排行（num、bond_of、rank_of、bond_name、bond_title、card_tag）、義不相殘（brothers、sworn）、替兄出頭（feud_against、record_feud、
  prune_feuds、avenge）與字句；玩家互動、懸賞榜、決戰、設伏幾包與 core/combat 讀它，結義包的 rules re-export 名號那一批。同 event_check 不進 MODULES。

# mall（全部拆包第 58 批：商城收尾）
- name_base.py：保留的名號——FAMOUS_NAMES、reserved_names，與這一季效力中的 active（原本在假人的 server_bots，它 re-export 同一批物件）；建角色、易名帖、假人取名、出陣約戰補位共用，
  商城包、出陣包問這裡、不 import 假人的模組。同 event_check 不進 MODULES。
# guide（全部拆包第 59 批「引導二」：玩法說明；計畫 docs/superpowers/plans/2026-11-06-玩法說明-第59批.md）
- howto_base.py：玩法說明兩包以上要用的那幾樣——一節的寫法 section、一成兩成 tenth、會推戰況的陣營 order_pushers、SOME_PLACES；各節在各包的 howto.py，
  順序在 features.py 的 HOWTO_ORDER。同 event_check 不進 MODULES。
# core_views（第二輪第 81 批；計畫 docs/superpowers/plans/2026-11-07-第二輪-第81批.md）
- status_view.py：狀態列的資料與文字版（status_data、status_text）；Game 留 2 個一行委派。同 event_check 不進 MODULES。
- page_view.py：江湖頁、公告、見聞、江湖紀錄的查詢、店面（第二輪第 93 批起分派問包：features.shop_page）、行動列底下那幾行；Game 留 21 個一行委派，engine._MENU_CORE["open"] 指到這裡的 OPEN_CORE。同 event_check 不進 MODULES。
# core_scene（第二輪第 91 批；計畫 docs/superpowers/plans/2026-11-07-第二輪-第91批.md）
- scene_view.py：江湖頁場景卡的文字與圖（scene_text、_own_scene_text、scene_art、location_text、place_state_view）；Game 留 5 個一行委派，哪一張照 features.py 的 SCENE_ORDER 問。同 event_check 不進 MODULES。
- content_base.py（core_content：第二輪第 96、100 批）：內容驗證共用的小工具——NUMBER_IN_TEXT、TIMETABLE_SIDES、check_traditional、week7、check_line、event_effects、stage_events；content.validate 與共用層
  各模組的 check_* 讀它（驗證本體回各自模組，validate 函式內 import、原位呼叫）。同 event_check 不進 MODULES，也不進 test_for.CORE_SERVICES。
# shop（第二輪第 93 批；計畫 docs/superpowers/plans/2026-11-07-第二輪-第93批.md）
- shop_base.py：店裡共用的（原本在 shopview）——掌櫃的話的情況表 SITUATIONS、離開鈕 BACKS、情況鍵 problem_key、被拒那一句撐到什麼時候 hold_for、still_holds、招牌底下那一句 line_text、素材格的排序 attribute_rank、階名 TIER_NAMES，
  加跨店的內容檢查 check_shop_lines（content.validate 原位函式內 import，不開 CONTENT_SLOTS 新格）；page_view、酒肆、軍需帳與四間店的 shop_view.py 讀它。各間店本體在包裡（Feature.shop_view）。同 event_check 不進 MODULES。
# identity（J 波第 201 批「帳號一」；計畫 docs/superpowers/plans/2026-11-08-帳號與客服-計畫.md）
- identity_base.py：帳號綁定別人也要讀的那一半——正規化、遮罩、金鑰、subject_hmac、on、phone_ok、blocked_name；identity 包、server.name_taken、商城易名帖讀它。同 event_check 不進 MODULES。
# terms（第 206 批「帳號六」；計畫 docs/superpowers/plans/2026-11-08-帳號與客服-第206批.md）
- terms_base.py：註冊那兩條路（server.register、identity 包建角色）查兩個勾選、建好帳號記同意版本的接縫——on、set_hook、register_problem、record；terms 包掛路由時 set_hook，殼與 identity 包讀它。同 event_check 不進 MODULES。

第一階 ctx 就是 Game 本身，不另包一層（手冊 3.3）。
"""

# 核心的模組（tianxia/<名字>.py）：手冊 3.1 的十三個，加上 3.10 的錢包（wallet）與江湖紀錄（journal：PM 2026-10-31 定算核心——
# CLAUDE.md 區塊表把它列在「核心與存檔」，每個功能都寫江湖紀錄；手冊 3.1 由 PM 補）。用到它的有兩處，都照這一份：
# - tests/core/test_feature_boundaries.py：功能包能 import 的就是這幾個（加上 tianxia/core/），這幾個都不能 import 功能包；
# - scripts/test_for.py：改了這幾個跑核心測試＋煙霧＋自己檔名的測試（照語法樹讀這一行、不 import；test_test_for 守兩邊一樣）。
# 只寫字面的名字（test_for 用 ast.literal_eval 讀）。attrset（五項屬性，屬性與跨季架構 v2 第三節）跟 team 一起算核心：team、rules 讀它（合回 develop 2026-11-06，PM 認定第 1 條：tests/core/test_attrset.py 放進 test_for 的 NOT_CORE_TESTS，同 world、step）。
# core_world（全部拆包第 25 批）：world（世界一步、週初與每天、開季結算、收季、開集結）改成世界層掛鉤（core/features.py 的 WORLD_ORDER）、
# 不再 import 功能包之後收進來（總表第 15 列）。它代叫的都在共用規則層（行尾標批號）；核心只 import 核心與共用層，邊界測試連函式裡也掃（第二輪第 102 批）。
# core_effects（全部拆包第 32 批，第 25 批 PM 認定第 2 條）：log_archive（換季時封存舊季的傳聞與回合紀錄；只 import 標準函式庫，
# 只有 sqlite_world 用）兩份名單都沒有，順手收進核心本體。它的 tests/core/test_log_archive.py（8 條）跟著進核心測試，不放進 NOT_CORE_TESTS。
MODULES = frozenset({
    "state", "sqlite_world", "world_state", "characters", "accounts", "database", "rules", "calendar", "models", "content",
    "team", "gender", "naming", "wallet", "journal", "attrset",
    "world",
    "log_archive",
    # core_step（全部拆包第 36 批）：step、weekcard 不再 import 包之後收進來（計畫 1.5 甲案）。懸賞榜兩格第 45 批由包登記（step._STEP_CORE 空了）；它們還
    # 讀章回（chapters，共用規則層）
    "step", "weekcard",
})
