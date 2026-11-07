"""邊界測試（test_feature_boundaries.py）的名單：過渡還留著的每一筆，寫最後的值、一行一筆；規則與掃描在那個檔，這裡沒有邏輯。

- 名單跟掃到的逐張比，多一筆、少一筆都紅。搬走了就刪那一行，新的過渡加一行、寫明「為什麼留、哪一批收」。
- GAME_DELEGATE_CALLERS 照被叫的委派歸到哪一包分組，加在那一包的組裡，不接在表尾。
"""
from __future__ import annotations

# ── engine.py ──

# 瘦下來的 Game（engine.py）也是核心（手冊 3.1）。它是核心裡唯一另外 import 包的地方：只准下面這幾樣，多一處就紅
# （要接一包先想掛鉤；真的要過渡就加進這裡、回報寫明）。
GAME_IMPORTS = {
    "tianxia.features.battle.rules",  # Game.BATTLE_GAMBLE_* 類別屬性、委派的型別註記；測試從 engine 拿決戰的字
    "tianxia.features.bout.duel_rules",  # Game.DUEL_GAMBLE_NOTE 類別屬性、委派的型別註記（DuelTextRequest）
    "tianxia.features.companions.actions",  # Game.SELF_IN_TEAM、FOLLOWER_IN_TEAM 類別屬性
    "tianxia.features.cultivation.actions",  # MELT_MANY_PROLOGUE：test_prologue 從 engine 拿
    "tianxia.features.figure_acts.plan_actions",  # 已經沒人用，第 98 批拿掉
    "tianxia.features.peers.invite_actions",  # INVITE_LAPSED、INVITE_LAPSED_AWAY：test_discuss 從 engine 拿
    "tianxia.features.sortie.rules",  # CLASH_*、TRAIN_CONFIRM*：測試從 engine 拿
    "tianxia.guide",  # note_action（舊名別名）：tests/core/test_engine.py 換 tianxia.engine.note_action，第 98 批進引導包
    "tianxia.sensing",  # 舊名別名：測試與 tianxia/sensing.py 經 engine.sensing 讀
    "tianxia.sortie",  # 舊名別名：序章的戰報標籤（sortie.on、PROLOGUE_FIGHT）
}

# 核心自己的邏輯直接叫包（沒有對應的掛鉤；過渡）。核心的接縫（選單、補算時間、行動列與 act 子動詞、choose 前後段、本人這一輪、場景卡、
# 戰報頁、店面）都換成了接縫掛鉤（tianxia/core/features.py），留下的都不是核心自己的接縫：還沒搬的別的功能（或同一包還沒搬的那一半）叫包。
GAME_DIRECT = {
    "_squad_encounter": "戰鬥（as_sortie 那一支）打贏之後出陣包給獎勵、約戰開著的季不推進度（那兩對記在 GAME_DELEGATE_CALLERS）：留原位（第 26 批量過：獎勵是出陣包與核心二選一、接在 msgs 最前面不進 extra；約戰開著與否是查詢；都不在懸賞那一個發布點上，原位行尾標「# 留原位：第 26 批」）。序章那一場的戰報標題寫雪恥（sortie.on、PROLOGUE_FIGHT）留在這裡（第 17 批）：戰報在這個單打服務裡建、裡面就存檔，序章裡誰打都照寫（不只 act:train），出陣包從外面改不到；要拿掉得在單打服務開一個「這一場戰報叫什麼」的位置，交 PM 定",
    "_note_action": "引導看這一步完成了沒：測試換的是 tianxia.engine.note_action，第 98 批進引導包",
}

# 核心自己的邏輯叫委派（呼叫端, 委派）；GAME_DIRECT 的方法裡叫的也列。
GAME_DELEGATE_CALLERS = {
    # battle
    ("options", "_battle_menu"): "battle_status 這個值從第一段傳到後面、中間夾暫停那一道，結果有「接在平常的選單前面」「整個取代（再接 defect:cancel）」「只能看」三種：MENU_ORDER 的格沒有這個回傳形狀，menu、options 掛鉤又只問開著的包；不接（第 56 批）",
    ("_battle_marks", "_escort_carry"): "戰力快照（核心的單打服務）帶這一次加入的同伴：沒有掛鉤，總表第 15 批登記戰力快照時再看",
    ("options", "_battle_for_me"): "battle_status 這個值從第一段傳到後面、中間夾暫停那一道，結果有「接在平常的選單前面」「整個取代（再接 defect:cancel）」「只能看」三種：MENU_ORDER 的格沒有這個回傳形狀，menu、options 掛鉤又只問開著的包；不接（第 56 批）",
    ("options", "_watching_battle"): "battle_status 這個值從第一段傳到後面、中間夾暫停那一道，結果有「接在平常的選單前面」「整個取代（再接 defect:cancel）」「只能看」三種：MENU_ORDER 的格沒有這個回傳形狀，menu、options 掛鉤又只問開著的包；不接（第 56 批）",
    ("options", "_fighting"): "battle_status 這個值從第一段傳到後面、中間夾暫停那一道，結果有「接在平常的選單前面」「整個取代（再接 defect:cancel）」「只能看」三種：MENU_ORDER 的格沒有這個回傳形狀，menu、options 掛鉤又只問開著的包；不接（第 56 批）",
    ("scene_art", "_battle_for_me"): "場景卡的圖：全服戰鬥蓋著場景時沒有圖（序章裡不算）：殼的場景卡（總表第 64～67 批）；位置固定、沒有對應的掛鉤（全部拆包第 8 批計畫 1.4）",
    # bounties
    ("choose", "_bounty_stale"): "FB-162 被搶的那一句回 Refused（伺服器照它跳提示）；choose_unlisted 回 list、而且在查選單之前，位置與回傳都不同，照 FB-195 馬市那一支留原位",
    # bout
    ("choose", "_arena_fight_problem"): "按到灰掉的挑擂鈕（兩個分頁、畫面還沒重抓）回為什麼不成、還要等多久：在查完選單之後、「此刻無法」之前，choose_unlisted 在查選單之前，不是這個位置",
    ("_own_scene_text", "_duel_scene"): "自己眼前的場景卡（頭目戰、擂台排在宴客的席位之前）：scene 掛鉤在擂台之後，接上去會排到宴客後面",
    ("_own_scene_text", "_arena_scene"): "同上",
    ("shop_view", "arena_left"): "店面那一頁的擂台（今天還能挑幾次）：同 (shop_view, tavern_view)，店面那一頁接店面登記是總表第 41 批",
    ("_battle_gear", "_duel_cut"): "戰力快照（核心的單打服務）抄奪璽單挑吃的防具減損（鐵匠鋪與合成流程 3.9）：_duel_cut 照總表第六節第 12 條歸單挑，_battle_gear 在核心",
    # companions
    ("choose", "_checked_prepared"): "進鎖後重驗鎖外生成的一輪對話（查完選單、建紀錄之前）：不是動作，是重驗、驗過的那一輪要傳給後面的格；MENU_ORDER 的 quick 接不了（第 57 批）",
    ("choose", "say_max"): "「自己說」最多幾個字：choose 前段驗那句話",
    ("_own_scene_text", "_last_talk_line"): "談話畫面名字底下的「上回」那一行：場景文字（_own_scene_text）的一部分。不接 scene 掛鉤的理由（第 20 批審查）：掛鉤坐在一條線的答題（storyline.question_text）之前，談話這一段在答題之後；包的登記順序又是人物情誼排在有所感前面，接成掛鉤得替它補「答題開著就讓路」與「有所感開著就讓路」兩道守衛，位置算行為，這一批的軌證明不了兩者永不並存，所以維持委派",
    ("_own_scene_text", "affinity_text"): "談話畫面名字旁的「情誼 N」：同上一筆（場景文字的一部分，不接 scene 掛鉤）",
    ("scene_art", "affinity_text"): "談話那張人物卡（scene_art）的副標也寫「情誼 N」：與 _own_scene_text 同一個詞，兩處不能各拼一份",
    # cultivation
    ("_seize", "_seize_chance"): "核心的單打服務收尾擲絕學的契機：留原位（第 26 批量過：在單打服務收尾、三處叫、野怪與僵持也算，不是懸賞那一下，回傳還要寫進戰報；原位行尾標「# 留原位：第 26 批」）",
    ("pick_growth", "_apply_growth"): "五項屬性的季挑成長配比（序章配點那一步，升一級沒有點可配）：三步（籌備中擋、這一季沒有配比、已定回 Refused）留在 Game，Refused 只在 engine；其餘本體在修練包 actions.pick_growth（合回 2A 已收）",
    # explore
    ("_act", "_explore"): "關著探索一顆時的舊探索（扣體力、晉升奇遇、序章的舊探索都在它前面；第 11 批 README 認定留原位，不改成 Verb）",
    # faction
    ("choose", "_lean_anytime"): "「改幫…」不在選單上時照樣收（在路上、決戰的大區，設計 3.2）：要先查選單、查不到才問它，choose 掛鉤在查選單之後，位置不對",
    ("choose", "_join_lean"): "投靠或拜入陣營名下的門派那一下，動作之後、入伍段之前給傾向：位置固定、動作之後的收尾沒有對應的掛鉤",
    ("_own_scene_text", "_faction_prompt"): "場景那一段的順序算行為（談著、選邊、投靠、叛投確認、求見…）：位置固定，場景的掛鉤是第 55～57 批",
    ("_own_scene_text", "_defect_scene"): "同上（叛投確認畫面的場景）",
    ("season_result", "ending_card"): "收季之後的結局卡接在 season_result 的 out 後面（欄位表 main.ending）：資料的鍵序算行為，沒有對應的掛鉤",
    # gear
    ("choose", "_general_gifts"): "位置固定、沒有對應的掛鉤（名將贈禮夾在「引導」與 check_thresholds 之間，choose 後半的先後算行為）",
    ("choose", "_signature_arms"): "位置固定、沒有對應的掛鉤（同上：本命兵器與名將贈禮同一處）",
    ("choose", "_gift_entry"): "位置固定、沒有對應的掛鉤（贈禮另起一則江湖紀錄，接在這一下的紀錄寫完之後）",
    # guide
    ("choose", "_check_hints"): "choose 最後、記進江湖紀錄之前：這一下碰到的新玩法排一條、排著的上框；after_action 之後才存回季、紀錄已經寫了",
    ("_menxia_entry", "_check_hints"): "修練頁、煉製頁的動作寫進紀錄（核心的修練頁紀錄服務）：說的話接在這一則",
    ("choose", "_begin_enlistment"): "這一下才投靠（或拜入陣營名下的門派）的人開始入伍段：陣營成包（第 35 批）之後，投靠那一步在包裡，入伍段屬引導包；要知道動作之前的陣營，位置固定在 choose 掛鉤之後",
    ("choose", "_greet_rejoin"): "第二季起再投靠：引薦人打個招呼（同上）",
    ("choose", "_note_action"): "「做完一件事」第 57 批量過不開事件（BUS_ORDER 沒有這種事件；計畫第四節）：choose 那 5 行（選了事件的選項、act 做完、進店、出店、指名求見）之間夾著 _opening_deliver，回話照位置接",
    ("take_stamina_pill", "_note_action"): "「做完一件事」第 57 批量過不開事件（BUS_ORDER 沒有這種事件；計畫第四節）：服回體丹（序章那一步）：回體丹是核心，在動作中間、回話照位置接",
    ("_menxia_entry", "_note_action"): "「做完一件事」第 57 批量過不開事件（BUS_ORDER 沒有這種事件；計畫第四節）：修練頁、煉製頁的動作（序章的練功、熔煉）：核心的修練頁紀錄服務，還把 HutReward 拆進 changes，位置就是行為",
    ("choose", "_opening_pending"): "開局第一分鐘（城門口三選一還沒選）：選完那一下人物的信接在這一下的回話裡（位置算行為）",
    ("choose", "_opening_deliver"): "同上：那位人物的信與護送委託",
    ("now_entry_html", "_opening_pending"): "開局第一分鐘（城門口三選一還沒選）不放「剛剛」那張卡：江湖頁的「剛剛」是核心",
    ("_reset_player_for_new_season", "_tutorial_intro"): "開場那一則江湖紀錄（_write）的引數：是引數不是一段，沒有格可接",
    ("_note_guide", "_guide_speakers"): "核心的引導框服務照說話的人分開「下一步的話」與「✔ 與獎勵」",
    ("_top_up_pills", "_top_up_line"): "_top_up_pills 歸核心（總表附錄甲）：讀檔那一刻補回體丹、寫一行，那裡沒有掛鉤",
    ("status_data", "_stamina_help"): "點體力條看的說明：第 66 批 status_data 的表裡這一格留在核心（同一格還有別的鍵），句子在新手引導包，經委派問",
    ("status_data", "_war_help"): "點戰況圖卡看的說明：第 66 批 status_data 的表裡這一格留在核心（同一格還有別的鍵），句子在新手引導包，經委派問",
    # military
    ("_squad_encounter", "_order_credit"): "戰鬥（核心的單打服務）打贏之後替軍令記功：位置固定在推線與地盤進度之間（出陣攻打的記功排在推進度之前），沒有對應的掛鉤",
    ("choose", "_report_seat"): "做完一個動作之後抄帳、補缺（這個動作結束時 _save_season 一起存）：位置在 after_action 之前，先後算行為",
    ("choose", "_settle_plots"): "做完一個動作之後的集體密謀結算：位置在回話的最後一段，沒有對應的掛鉤",
    ("choose", "_hear_after_stamina"): "花體力的動作之後抽伏筆片段與機緣線索：位置在 choose 結尾、after_action 之前，伏筆先機緣後、共用 self.rng，擲骰順序算行為，沒有對應的掛鉤",
    ("_squad_encounter", "_fs_after_win"): "遊歷打贏之後擲官銀：留原位（第 26 批量過：夾在軍令記功前後、懸賞那一個發布點之前，只在單打服務這一處有，收進事件 win 兩個發布點的訂閱者就不一樣）",
    ("_squad_encounter", "_opp_on_win"): "遊歷打贏之後記密謀一處（三路並進）：夾在軍令記功與懸賞討伐之間，留原位（第 26 批量過：同上）",
    ("_own_scene_text", "_fs_asking_text"): "答題中的場景文字排在拜入、投靠、叛投、求見的畫面之後、趕路的畫面之前，scene 掛鉤在更前面（有所感、宴席之後、談話之前），位置不同不能接",
    # outlets
    ("shop_view", "_bribe_targets"): "店面那一頁（打點的帳簿）要此地打點得了的人物，shop_view 是核心的店面殼",
    # seal
    ("_battle_marks", "_seal_bare"): "加入決戰那一刻的戰力快照（單打服務，核心）多一鍵 seal_bare：位置固定在快照組好之後、沒有對應的掛鉤",
    # sense
    ("_insight_blocked", "_sense_missed"): "舊探索那一行（action_notes）句尾補什麼時候才悟得出：舊探索（留給序章與測試內容；總表第七節第 1 題選甲，沒有下一批要收）",
    ("choose", "_epiphany_name"): "dunwu:（特殊頓悟取名）：要帶自己寫的名字（choose 的 text），choose 掛鉤不帶 text，留在原位的 elif",
    ("_action_title", "_epiphany_title"): "dunwu: 那一下江湖紀錄的標題（同上，dunwu: 留在原位）",
    # socialize
    ("_own_scene_text", "_audience_intro"): "求見畫面的說明（picking_audience）：場景文字夾在叛投確認與伏筆答題之間，`scene` 掛鉤坐在更前面，位置算行為",
    # sortie
    ("_squad_encounter", "_sortie_rewards"): "戰鬥（as_sortie）打贏之後給出陣的獎勵：留原位（第 26 批量過：出陣包與核心二選一、接在 msgs 最前面不進 extra，不在懸賞那一個發布點上；原位行尾標「# 留原位：第 26 批」）",
    ("_squad_encounter", "duel_on"): "戰鬥（as_sortie）打贏之後：約戰開著時只剩截糧、不推進度（進度只在約戰結算動）：留原位（第 26 批量過：約戰開著與否是查詢，決定記功與推進度走哪一支，不是事件；原位行尾標「# 留原位：第 26 批」）",
    ("_squad_encounter", "_drill"): "戰鬥（核心的單打服務，遊歷、探索的野怪、劇情以外的仗都經它）遇上自家陣營的隊伍改成操練：操練是出陣包的（第 17 批）、打不打在單打服務裡定；單打服務的「遇上自己人」沒有對應的掛鉤。68 批裡沒有排：總表 3.4 可選的「戰鬥單打服務收進核心」（戰鬥調查 C1）那一次在 core/combat.py 開這一格、改叫掛鉤；不做 C1 就一直留著",
    ("_squad_encounter", "train_trend_push"): "戰鬥（不是出陣的那一支）打贏之後遊歷推大勢：留原位（第 26 批量過：推大勢夾在記功、地盤進度之前，結果交給 push_trend，不在發布點上；原位行尾標「# 留原位：第 26 批」）",
    # story
    ("_reset_player_for_new_season", "_story_close_season"): "還沒收的線要在 world.save_annals 存上一季的行狀之前寫「此事未了」進傳，夾在 _zhuan_past 與 _zhuan_profile 中間（同上）；on_season_end 在 save_annals 之後、又只問開著的包",
    ("choose", "_story_tick"): "每個動作結束那一格（事件了結之後、召見之前）：不是任何掛鉤的位置",
    ("_event_progress", "_story_tick"): "事件了結的推進：段落事件了結了，照記下的那一步往下走；同上",
    # tavern
    ("shop_view", "tavern_view"): "店面那一頁：鐵匠鋪那條線（feature/smithing-flow）緊貼著這一行改，這一輪不動；鐵匠鋪落地、成包時（總表第 41 批）店面那一頁接上店面登記（Shop）",
    # zhuan
    ("_reset_player_for_new_season", "_zhuan_past"): "換季最前面補季末論功與〈天下形勢〉，回的 past 要傳給第三行的 _zhuan_profile、中間夾一條線收尾：掛鉤沒有傳值的位置，硬開一格要多一份暫存；不接",
    ("_reset_player_for_new_season", "_zhuan_profile"): "換季存行狀（save_annals 的第四個引數）時的身家，讀第一行的 past（同上）",
}

# ── 核心模組（tianxia/core/ 與頂層的核心模組）──

# 核心模組經 ctx 叫包的委派（過渡；同 GAME_DELEGATE_CALLERS 的格式與規矩：(模組.函式, 委派) → 為什麼留、哪一批收）。
# import 那一向沒有名單：核心 import 了成包的舊名時，test_the_core_never_imports_a_feature_package_except_the_registry 會抓到（核心只准 engine.py 的 GAME_IMPORTS）。
CORE_DELEGATE_CALLERS: dict[tuple[str, str], str] = {
    ("event_check.answer_event", "_begin_enlistment"): "隨口應對的結果拜入陣營名下的門派：開始入伍段",
    ("event_check.answer_event", "_greet_rejoin"): "同上：入伍段早就走完的人，引薦人打個招呼",
    ("event_check.answer_event", "_check_hints"): "隨口應對了結了事件：同選項一樣，碰到的新玩法排一條、排著的上框",
    ("event_check.answer_branch", "_begin_enlistment"): "分岔的隨口應對：同 answer_event",
    ("event_check.answer_branch", "_greet_rejoin"): "同上",
    ("event_check.answer_branch", "_check_hints"): "同上",
    ("services.outing_watch", "_outing_watched"): "走一趟停在要選的事上時這一下選完的得失（探索包的委派）：裝飾器原本是 engine.py 模組層的 _outing_watch，掛在 Game.choose、answer_event 與有所感包的 sense_draw、epiphany_names 上；包不能 import engine，第 24 批搬進核心的共用小函式。「做完一件事」第 57 批量過不開事件（計畫第四節）",
    ("event_check.event_tier", "_battle_for_me"): "事件分級那一行：全服戰鬥蓋著場景時不寫（tick=False）；事件檢定是核心本體、決戰包回答「此刻蓋著的那一場」，位置固定、沒有對應的掛鉤（總表第 55～57 批再看要不要改成查詢服務的掛鉤）",
    ("event_check.answer_event", "_report_seat"): "隨口應對的結果也可能推大勢、記貢獻：第四階席次的帳在這裡也抄（正式版丁）；事件檢定是核心本體、席次抄帳在軍情包，位置固定、沒有對應的掛鉤",
    ("event_check.answer_branch", "_report_seat"): "同上（隨口應對的分岔那一支）",
    ("event_check.present", "_hear_from_event"): "事件觸發時聽到的伏筆片段（計畫 T7）：接在事件卡的後面，事件檢定是核心本體、伏筆在軍情包，位置固定、沒有對應的掛鉤",
    ("event_check.answer_event", "_general_gifts"): "隨口應對的效果加了情誼，另起一則贈禮（名將贈禮、本命兵器）：事件檢定是核心本體，位置固定在效果套完之後、沒有對應的掛鉤",
    ("event_check.answer_event", "_signature_arms"): "同上（本命兵器與名將贈禮同一處）",
    ("event_check.answer_event", "_gift_entry"): "同上（贈禮另起的那一則江湖紀錄）",
    ("event_check.answer_branch", "_general_gifts"): "同上（隨口應對的分岔那一支）",
    ("event_check.answer_branch", "_signature_arms"): "同上",
    ("event_check.answer_branch", "_gift_entry"): "同上",
}

# 頂層的核心模組（MODULES 裡放在 tianxia/ 底下的）經 game 叫包的委派。現在沒有。
CORE_TOP_DELEGATE_CALLERS: dict[tuple[str, str], str] = {}

# 事件檢定（核心本體 tianxia/core/event_check.py）：Game 上本體只有一行 `return event_check.<名>(self, …)` 的方法：server、假人、測試、探索包與 Game 原位在叫的。
CORE_EVENT_DELEGATES = {  # 只有 event_check 自己叫的 _answer_branch、_deed_credit 不留委派
    "_present", "_event_text", "event_tier", "event_option_view", "_choice_label",  # 事件卡
    "_choose", "_tale_clue", "_event_battle", "_apply",  # 固定選項
    "_free_text_of", "_branches", "event_free_text_prompt", "free_text_request", "answer_event", "add_gamble_narration",  # 隨口應對
}

# 被測試換掉的 Game 方法（手冊第十五節「換掉的才打得到」）：event_check 裡叫它們一律經 ctx，不直接叫模組裡的本體。
# 模組裡的函式 → Game 上的委派、誰換掉它
EVENT_CHECK_VIA_CTX = {
    "present": ("_present", "tests/bots/test_event_rotation.py 換掉 Game._present：只有端出事件那一下記輪替"),
    "apply": ("_apply", "tests/figures/test_seats.py 換掉 Game._apply：效果裡記的貢獻要排在抄帳之前"),
    "free_text_request": ("free_text_request", "tests/server/test_server.py 換掉 Game.free_text_request：暫停中不問引擎"),
}

# ── 共用規則層 ──

# 共用規則層的模組碰到別的舊模組的（總表第六節第 5 條：只准 import 核心本體與同一層）：(模組, 舊模組) → 寫在理由開頭：「排定：」收進核心本體或共用規則層的（那一批
# 收完拿掉這一行）；「之後成包：」主人成包之前要先改成查詢服務、或把用到的那一段留在共用規則層。多一條、少一條都紅。現在沒有。
SHARED_PENDING: dict[tuple[str, str], str] = {}

# 還不收進共用規則層的舊模組：讀的都是還沒成包的舊模組，還沒有包可以回答查詢。模組 → 卡在哪、哪一批之後收。包 import 它們的那幾行照舊註「過渡：待搬」。
SHARED_LATER = {
    "fusion": "讀有所感的自創（sensing.add_own、own_name：有所感第 24 批成包）（第 24 批 PM 認定第 3 條；行狀 annals.note 那一半第 29 批之二收進核心 core/annal_base.py，fusion 改 import 它，不算了）",
    "skillview": "門下頁的說明（彙整）：讀自創 create（第 44 批）、修練 cultivation（第 23 批）、玉璽 seal（第 27 批已成包，經舊名別名）、鐵匠鋪 smithing（第 41 批已成包，經舊名別名）；那幾包成包、改成查詢服務之後再收（輿圖 atlas 第 50 批收進了共用規則層）",
    "shopview": "店面的畫面資料（彙整）：讀擂台 arena（第 12 批）、懸賞 bounties（第 45 批已成包，經舊名別名）、鐵匠鋪 smithing（第 41 批已成包，經舊名別名）、單挑 duel 的底層；那幾包成包之後再收",
    "events": "事件抽選：只剩讀事件分級 tiers（tiers 讀舊名 arena，也在這一份名單）；伏筆在不在跑、伏筆的事件第 40 批改問核心的 omen_base（心意第 19 批換成共用規則層 stance_world）",
    "tiers": "事件分級：讀擂台的名次 arena.entry_of，經舊名 arena（單挑包的別名）：名次已經是核心的查詢服務 arena_ranks（第 12 批），可是 tests/core/test_event_tiers.py 換掉 tianxia.arena.entry_of，改讀核心之後那一條打不到；那一條改成換掉核心那一份（改核心測試，PM 定）之後再收",
    "narration": "事件旁白每週改寫：只剩讀事件抽選 events（也在這一份名單）；伏筆的事件第 40 批改問核心的 omen_base",
    "leaderboard": "賽季榜單：讀本命兵器 signature_arms（裝備第 42 批已搬進 features/gear/signature_arms.py，函式裡經舊名別名讀）與門下頁的說明 skillview（函式裡）；擂台榜第 12 批審查修正改讀核心的查詢服務 arena_ranks；gear_card 讀本命兵器改成查詢服務、skillview 收進來之後再收",
}

# 收進共用規則層之後函式裡也不准 import 包的那七個（test_the_seven_joined_the_shared_layer_and_import_no_package_not_even_inside_a_function）。
SHARED_CORE_WORLD2 = ("figures", "figure_life", "plans", "orders", "ranks", "chapters", "rumor_view")

# ── 各包之間 ──

# 服務清單上三段式的 A、C 段：清單不分包，看不出別包叫它們。這些是各包自己的委派，只准主人的 routes.py 接三段式；別包叫就是跨包（手冊 3.4 第 1 條）。
RELAY_OWNERS = {
    "battle": {"battle_text_request", "submit_battle_custom_action"},
    "bout": {"arena_crowd_request", "apply_arena_crowd", "duel_text_request", "duel_gamble"},
    "companions": {"letter_request", "apply_letter", "persuade_request", "persuade", "dialogue_request", "say_max"},
    "craft": {"create_request", "create_intent", "create_reread_request", "create_reread", "forge_request"},
    "cultivation": {"ascend_request", "ascend_line"},
    "explore": {"outing_tale_request", "outing_say", "outing_set_tale"},
    "feast": {"feast_text_request", "feast_toast"},
    "figure_acts": {"yuedan_request", "apply_yuedan"},
    "peers": {"peer_request"},
    "seal": {"seal_text_request", "seal_gamble"},
    "sense": {"epiphany_request", "epiphany_names", "sense_request", "sense_draw"},
    "tavern": {"tavern_chatter_request", "apply_tavern_chatter", "tavern_ask_request", "tavern_ask"},
    "territory_acts": {"xingshi_waiting", "xingshi_request", "settle_xingshi", "release_xingshi"},
    "zhuan": {"biography_request", "write_biography"},
}

# 發布點之外不直接叫事件的訂閱者：懸賞的交差（bounties.on_*）、玉璽的撿碎片與收場（_seal_find、_seal_settle：Game 上只剩給測試的一行委派，包與 engine 照樣不准叫）、
# 交糧車（_convoy_arrives，已拿掉），在 engine.py 與每一包的 .py（測試除外）只准出現在核心代叫表 engine._BUS_CORE 裡；別處要聽，登記事件的格（Feature.bus()），先後照核心的 BUS_ORDER。
BUS_SUBSCRIBERS = {
    ("bounties", "on_aid"),
    ("bounties", "on_arrive"),
    ("bounties", "on_explore"),
    ("bounties", "on_raid_win"),
    ("bounties", "on_win"),
}
BUS_METHODS = {"_seal_find", "_seal_settle", "_convoy_arrives"}

# 效果那幾格與叛投清進度不碰包認領的欄位：rules.apply_effect 與它的格（_fx_*、核心代叫表 _EFFECT_CORE）、defection 的清進度（clear_progress、_clear_own、defect 與代叫表）
# 屬性名不准是任何一包 player_fields 裡的名字；包的欄位由那一包登記的格寫，核心照表叫。defection.prompt（確認畫面讀 convoy）是讀不是清，不在這一條。
# defection 在陣營包（features/faction/defection.py）；代叫表只剩 _STRANDED_CORE，_CLEAR_CORE、_LEAVE_CORE 那兩個名字掃不到就不算，不礙事。
EFFECT_DEFECT_SCAN = {
    "rules": ("apply_effect", "_fx_", "_EFFECT_CORE"),
    "defection": ("clear_progress", "_clear_own", "defect", "_CLEAR_CORE", "_LEAVE_CORE", "_STRANDED_CORE"),
}

# step、weekcard 換之前直接讀的包的欄位與函式（收進核心本體之後不准再讀）。
STEP_PACKAGE_READS = {"convoy", "_nearest_to", "next_step", "next_trip", "step_items"}

# atlas.travel_block 換之前直接讀的格（改問 MENU_ORDER["block"]，各包登記自己那一格），不准再讀。
ATLAS_PACKAGE_FIELDS = {
    "ambush",
    "arena",
    "duel",
    "fs_asking",
    "pending_companion",
    "pending_defect",
    "pending_faction",
    "picking_arena",
    "picking_audience",
    "picking_bounty",
    "picking_dadian",
    "picking_donate",
    "picking_market",
    "picking_smith",
    "picking_tavern",
    "tagalong",
}

# 只讀擂台名次與稱號的舊模組讀核心的 arena_ranks，不經舊名 arena 連帶載入單挑包（手冊 3.11「能走服務就走服務」）。tiers 照舊經別名：
# tests/core/test_event_tiers.py 換掉 tianxia.arena.entry_of，改讀核心之後那一條打不到（SHARED_LATER 的 tiers）。
ARENA_RANK_READERS = ("features/peers/mingtie", "leaderboard")

# ── 各包 game_api.py 的表 ──

# 原本掛 @_not_while_preparing 的委派
PREPARING_GUARDED = {"name_divine", "bind_art", "check_in", "add_to_team", "remove_from_team", "release_companion"}
# 委派與本體參數名不同的（名字 → (委派的, 本體的)）：直接掛之後 g.x 的參數名是本體的，今天全 repo 沒有人用關鍵字傳這一格
RENAMED_PARAMS = {"write_biography": ("request", "req"), "_ambush_record": ("spoils", "got")}

# ── 各包之間的呼叫（core_api，第二輪第 74 批）──

# 包經 Game 叫別包的委派（主人是各包 game_api.py 的 TABLE）：(誰叫, 主人) → 名字。跟全包掃到的逐對比，多了少了都紅。
# 新的跨包呼叫：這裡加一列（或加進那一列的名字），名字也要同時列在 tianxia/core/services_list.md。一對一行、名字排序。
CROSS_PACKAGE_CALLS = {
    ("admin", "battle"): {"cancelled_showdowns"},
    ("admin", "military"): {"admin_player_choices"},
    ("admin", "seal"): {"_mandate_settle"},
    ("battle", "admin"): {"_timetable_event", "_timetable_refusal"},
    ("battle", "cultivation"): {"_seize_chance"},
    ("battle", "faction"): {"_four_wins"},
    ("battle", "looks"): {"_battle_ult", "_round_mvp"},
    ("battle", "seal"): {"_deliver_seal_results", "_mandate_weight", "_seal_bare"},
    ("bounties", "companions"): {"_letter_thank", "_parley_ask_label", "_parley_keep", "_parley_owed_line", "_parley_settle_task"},
    ("bout", "looks"): {"arena_look", "arena_move"},
    ("checkin", "guide"): {"_opening_gate", "_opening_pending"},
    ("companions", "battle"): {"_settle_partings"},
    ("companions", "guide"): {"_hint"},
    ("companions", "military"): {"_fs_hear_talk", "_omen_talk_options", "_opp_hear_topic"},
    ("companions", "socialize"): {"_can_meet", "_count_talk", "_socialize_figure", "_talk_idle"},
    ("companions", "travel"): {"_depart"},
    ("cultivation", "guide"): {"_check_hints"},
    ("explore", "bout"): {"_boss_face", "_boss_ready", "_duel_start"},
    ("explore", "map"): {"_map_mostly_here", "_map_open_places"},
    ("explore", "sense"): {"_sense_here", "_sense_missed", "_sense_start"},
    ("explore", "sortie"): {"_sortie_host"},
    ("explore", "story"): {"_story_begin"},
    ("faction", "battle"): {"_ally_follows_battle", "_battle_now"},
    ("faction", "guide"): {"_nearest_to", "_opening_pending"},
    ("figure_acts", "gear"): {"_signature_arms"},
    ("figure_acts", "military"): {"_order_credit"},
    ("guide", "battle"): {"_at_battle", "_battle_status", "_watching_battle"},
    ("guide", "companions"): {"_recruit_target", "_recruitable_here"},
    ("guide", "craft"): {"_create_allowed", "_create_on", "_create_price", "forge"},
    ("guide", "cultivation"): {"_chuangong_ready", "allocate_stat", "melt_art", "practice", "slot_insight", "switch_art"},
    ("guide", "explore"): {"_practice_tier"},
    ("guide", "sense"): {"_sense_prologue_choice"},
    ("guide", "tavern"): {"_tavern_at", "_tavern_here", "_tavern_on"},
    ("looks", "battle"): {"_battle_for_me"},
    ("map", "explore"): {"_practice_tier", "map_mostly"},
    ("map", "sortie"): {"_duel_squad", "_sortie_foes", "_sortie_mode", "duel_on", "sorties_left"},
    ("military", "admin"): {"_timetable_event"},
    ("military", "guide"): {"_nearest_to"},
    ("military", "sortie"): {"_duty_option"},
    ("notify", "companions"): {"morning_mail"},
    ("peers", "bounties"): {"_raid_bounty"},
    ("peers", "figure_acts"): {"_yuedan_line"},
    ("peers", "travel"): {"_join", "join_refusal"},
    ("seal", "battle"): {"_showdown_status"},
    ("seal", "bout"): {"_duel_cut", "_duel_side"},
    ("sense", "explore"): {"_rare_boost"},
    ("sense", "guide"): {"_check_hints"},
    ("socialize", "companions"): {"_open_dialogue"},
    ("socialize", "figure_acts"): {"_snubbed_character"},
    ("socialize", "guide"): {"_hint"},
    ("sortie", "companions"): {"_parley_backing_here"},
    ("sortie", "explore"): {"_outing_on"},
    ("sortie", "military"): {"_opp_after_success", "_order_credit"},
    ("stamina_plays", "bounties"): {"_raid_bounty"},
    ("tale", "battle"): {"_tale_battles", "apply_battle_tales", "battle_tale_request"},
    ("tavern", "battle"): {"_battle_now"},
    ("territory_acts", "battle"): {"_cancel_siege", "_joinable", "_sieges"},
    ("travel", "battle"): {"_sync_battle_presence"},
    ("travel", "guide"): {"_check_hints"},
    ("travel", "military"): {"_hear_after_stamina", "_report_seat"},
    ("travel", "peers"): {"_peer", "_tell_sender"},
    ("travel", "stamina_plays"): {"_ambush_check"},
}

# 包經殼碰別包的模組（shell.<server.py 最外層 import 的模組>，指到別包）：(這一包, 模組的名字)。過渡，不准加，第 102 批收；跟全包掃到的比，多了少了都紅。
SHELL_FOREIGN = {
    ("bout", "battle_instance"),  # 3 處
    ("notify", "letters"),  # 1 處
    ("seal", "battle_instance"),  # 3 處
    ("tale", "battle_instance"),  # 3 處
}
