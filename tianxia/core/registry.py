"""FEATURES：登記的功能包（有順序；開發規範手冊 3.3）。核心唯一 import 功能包的地方。

新的一包用 `scripts/new_feature.py <包名>` 生：它在下面兩個標記前面各加一行（import 與清單）。順序就是核心問的順序
（選項怎麼排、哪一包先接走選單）。搬一包進來時照它在 engine.py 裡原本的位置排，行為才一個字不變。
"""
from __future__ import annotations

from .features import Feature

# explore
from ..features import explore  # 探索（走一趟、探索一顆）：主動搬六包第 3＋4 批（沒有選項、選單、狀態，排在哪裡結果都一樣）
from ..features import feast, mall  # 商城（萬寶閣）：第 1 階搬進來的示範；宴客：第 1 階多搬的有按鈕的小包（3.10）
# tavern
from ..features import tavern  # 酒肆：主動搬六包第 10 批（只接 tavern:* 的 choose 與假人分數，都照前綴認，排在哪裡結果都一樣）
from ..features import sortie  # 出陣：主動搬六包第 1 批（沒有選項、選單、狀態，排在哪裡結果都一樣）
# battle
from ..features import battle  # 全服決戰：主動搬六包第 5 批（「看」那一半；沒有選項、選單、狀態，排在哪裡結果都一樣）
from ..features import looks  # 擂台形象
# guide
from ..features import guide  # 新手引導：全部拆包第 22 批（沒有選項、選單、狀態，排在哪裡結果都一樣；check_content 的錯誤排在別包之後——
# 第 12 批合進 develop 時單挑包接在它後面，只有碰到才說與場邊事件同時寫壞時錯誤的先後不同）
# companions
from ..features import companions  # 人物情誼：全部拆包第 19 批（只接 errand:* 的 choose 與 /api/figure；都照前綴、路徑認，排在哪裡結果都一樣）
# sense
from ..features import sense  # 有所感與頓悟：全部拆包第 24 批（choose 只吃 sense:、scene 接在宴客之後——原本那一行就在宴客那一行後面）
# cultivation
from ..features import cultivation  # 修練：全部拆包第 23 批（只接 learn:* 的 choose，照前綴認，排在哪裡結果都一樣）
# story
from ..features import story  # 一條線：全部拆包第 30 批（只接 story:* 的 choose，照前綴認，排在哪裡結果都一樣）
# checkin
from ..features import checkin  # 簽到：全部拆包第 30 批（沒有選項、選單；排在哪裡結果都一樣）
# socialize
from ..features import socialize  # 交友求見：全部拆包第 21 批（只接 call: 的 choose 與假人分數，照前綴認，排在哪裡結果都一樣）
# figure_acts
from ..features import figure_acts  # 大勢人物的行動：全部拆包第 31 批（只接 aid:、plan: 的 choose 與假人分數，照前綴認，排在哪裡結果都一樣；同步補名望 _deliver_guard_credits 不接 deliver_notices，留 Game 的委派原位）
# zhuan
from ..features import zhuan  # 列傳：全部拆包第 29 批（只接 zhuan: 的 choose 與 5 條路由，照前綴、路徑認，排在哪裡結果都一樣）
# military
from ..features import military  # 軍情：全部拆包第 33 批（沒有選項、選單、狀態、掛鉤，排在哪裡結果都一樣；選單那幾顆和按下去都在核心原位叫 Game 的委派）
# outlets
from ..features import outlets  # 銀兩出口與捐軍備：全部拆包第 43 批（兩間店的店面登記排在酒肆之後、擂台之前，entry 都回 None；只有同時坐在兩間店裡才分先後，正常不會）
# craft
from ..features import craft  # 煉製與自創：全部拆包第 44 批（只接 routes、content、on_drop_stale，排在哪裡結果都一樣；on_drop_stale 的 prune 只動 creating）
# smithy
from ..features import smithy  # 鐵匠鋪：全部拆包第 41 批（choose 前綴 smith 與 act:smith 的 Verb、路由、content；沒有店面登記，排在哪裡結果都一樣）
# territory_acts
from ..features import territory_acts  # 地盤的行動與畫面：全部拆包第 46 批（只接 /api/xingshi、管理者五個工具與〈天下形勢〉句型的 check_content，排在哪裡結果都一樣；22:00 換天沒有掛鉤，留 Game 的委派原位）
# bout
from ..features import bout  # 單挑（頭目戰、擂台）：全部拆包第 12 批。擂台的店面登記接在酒肆後面（「此地還能做」的入口原本就在酒肆之後）；後面接的 stamina_plays、seclusion（第 39 批）與 peers（第 37 批）沒有店面登記、沒有 menu 掛鉤，bout 的店面與 menu 位置不變
# stamina_plays
from ..features import stamina_plays  # 體力玩法（設伏、屯糧）：全部拆包第 39 批。choose 與 bot_pick 的前綴 ambush／works 與別的包不重疊；world() 的格有表序；選項不走 FEATURES（見該包 actions.py）
# seclusion
from ..features import seclusion  # 閉關：全部拆包第 39 批。只有 verbs()（act:break），沒有選項、選單
# peers
from ..features import peers  # 玩家互動一（此地還有、玩家卡、邀請框、打招呼、贈物、名帖）：全部拆包第 37 批（只接 invite: 的 choose、換季的頭銜簿與路由，排在哪裡結果都一樣）
# ── import（new_feature.py 接在這一行前面）──

FEATURES: list[Feature] = [
    # explore（排最前面不是排最後：同時在拆的別條線都在標記前面接自己的一行，各佔各的行合併才不撞；這一包只有 check_content，
    # 其餘掛鉤都是預設的，順序唯一的影響是 content.validate 裡探索的錯誤排在商城前面——審查修正，不是「忘了排最後」）
    explore.FEATURE,
    mall.FEATURE,
    feast.FEATURE,
    # tavern
    tavern.FEATURE,
    sortie.FEATURE,
    # battle
    battle.FEATURE,
    looks.FEATURE,
    # guide
    guide.FEATURE,
    # companions
    companions.FEATURE,
    # sense
    sense.FEATURE,
    # cultivation
    cultivation.FEATURE,
    # story
    story.FEATURE,
    # checkin
    checkin.FEATURE,
    # socialize
    socialize.FEATURE,
    # figure_acts
    figure_acts.FEATURE,
    # zhuan
    zhuan.FEATURE,
    # military
    military.FEATURE,
    # outlets
    outlets.FEATURE,
    # craft
    craft.FEATURE,
    # smithy
    smithy.FEATURE,
    # territory_acts
    territory_acts.FEATURE,
    # bout（店面登記的入口排在酒肆之後、menu 掛鉤排在宴客之後，都是原本那一行的位置；計畫 2026-11-03-單挑包-第1批.md 1.4。
    # 後面接的 stamina_plays、seclusion、peers 沒有店面登記、沒有 menu 掛鉤，bout 的店面與 menu 位置不變）
    bout.FEATURE,
    # stamina_plays（排在 bout 後面：choose 前綴與別的包不重疊，順序不影響結果）
    stamina_plays.FEATURE,
    # seclusion
    seclusion.FEATURE,
    # peers（排在 seclusion 後面〔照合併先後〕：只接 invite: 的 choose、on_season_start 與路由，跟 stamina_plays、seclusion、territory_acts 的掛鉤不重疊，順序不影響結果）
    peers.FEATURE,
    # ── 清單（new_feature.py 接在這一行前面）──
]

# 共用規則層（全部拆包總表第六節第 5 條；第 11 批 PM 定的格式）：還沒、也不會搬進任何一包的規則模組（tianxia/<名字>.py），好幾包都讀。
# 模組名 → 一句誰在用、為什麼在共用層。包 import 這裡的模組不必註「過渡：待搬」；這幾個模組跟核心一樣不准 import 包
# （tests/core/test_feature_boundaries.py 守）。核心本體（tianxia/core/__init__.py 的 MODULES）可以 import 這一層、這一層可以 import 核心
# 本體與同一層。第 11 批放了主人已經寫成「共用規則層」的 siege；第 15 批（# shared 那一段）登記其餘 59 個。總表第 15 列寫了、這一批先不收的 8 個
# （讀了之後成包的擂台、伏筆、有所感……）與這一層還碰到別的舊模組的 11 條（排定收進來的、之後成包的），在邊界測試的 SHARED_LATER、SHARED_PENDING。
# scripts/test_for.py 照語法樹讀這一份（改這一層的模組只挑自己檔名的測試＋煙霧＋邊界測試）：值只寫字面的字串（相鄰的字串可以接）。
SHARED: dict[str, str] = {
    "siege": "攻城的規則（攻城戰的名字、收場改季、誰贏）：決戰包的攻城與戰況、地盤都讀；總表附錄甲裁定不搬進任何一包",
    # shared（全部拆包第 15 批「共用規則層登記」，計畫 docs/superpowers/plans/2026-11-01-共用規則層登記.md 1.2）：只登記、不搬程式。
    # 戰鬥引擎（9 個）：核心的 team 打每一場都讀，每一種打一場的包都用，放進哪一包都會變成包 import 包
    "encounter": "單次判定（威力差、勝算、四種結果）：核心的 team、content 讀，Game 的單打服務（大場面判讀、切磋、截殺、設伏、頭目戰與擂台的"
                 "收場、戰力快照）也叫；出陣、酒肆的殺手那一場與大勢人物的護衛（figure_aid）都叫，門下頁的說明（skillview）也讀",
    "rounds": "一般的仗一回合一回合的演出（from_clash）：核心的 team 照它寫戰報的回合；戰報 battlelog 也讀",
    "tactics": "回合與本命戰法、相剋：核心的 team、state、world_state、content 都讀；決戰包的戰況、出陣約戰的三招、擂台、單挑都叫",
    "styles": "大場面對手的路數（一門打不遍）：核心的 team 算威力時讀；單打服務的戰報那一句、人物對話也用",
    "terrain": "地利（武學隨地理環境）：核心的 team 算威力時讀；勝算的字、輿圖也照它",
    "rise": "江湖水漲（大場面、頭目跟得上變強的人）：核心的 rules 讀；單打服務的劇情戰與勝算都經它",
    "battlelog": "戰報的資料與拆得失：核心的 journal 讀；決戰、探索、出陣、酒肆四包都寫戰報",
    "fight_llm": "大場面的模型判讀（三段式的單子與夾過的優勢）：單打服務（fight_request、_checked_fight）與殼的 prepare_fight 用，每一種打一場都可能經它",
    "battle_instance": "全服決戰與攻城的資料型別與回合規則：核心的 world_state、sqlite_world 存它的資料型別；決戰包、siege、奪璽單挑、擂台都讀"
                       "（總表第 54 批拆兩半：規則那一半進決戰包、資料型別留下）",
    # 武學與裝備的規則（22 個；總表寫 25 個，fusion、skillview、shopview 先不收：讀了之後成包的有所感、自創、修練、玉璽、鐵匠鋪、擂台、懸賞，
    # 理由在 tests/core/test_feature_boundaries.py 的 SHARED_LATER）：核心的 team、content 算威力、驗內容都讀，修練、煉製、鐵匠鋪、裝備好幾包共用
    "martial_arts": "武學的品質、熟練度、威力：核心的 content、rules、state、team、world_state、sqlite_world 都讀；二十幾個舊模組在用",
    "arts": "武學的評分、裝卸、意境格（arts.score）：核心的 team 讀；修練、煉製、榜單、序章都叫",
    "insight_fx": "意境效果池與層數：武學 arts、意境 insights、功法庫、序章讀；修練、有所感成包之後也要",
    "insights": "意境（基本意境與悟得）：核心的 content、rules 讀；探索包的悟意境、合成、有所感都叫",
    "traits": "武學的功效（八個一般功效與特別功效）：核心的 team 打仗時讀；武學 arts、鐵匠鋪、修練頁都用",
    "moves": "以意成招（自創武學的招）：戰法 tactics、武學 arts、功效 traits 讀；認勢用到的擺式幾何在 pose（第 44 批從 create 抽出來）",
    "might": "戰力（全身加總的數）：修練頁、自創、破境讀；它自己讀 arts、equipment、encounter 這一層",
    "signature": "本命武學（本命戰法）：核心的 team 讀；人物對話、功法庫也用",
    "library": "功法庫（持有上限、熔煉、學基礎武學）：核心的 rules 讀；商城包的深交名額上限 cap_of（手冊 3.10）、修練、自創、名帖都叫",
    "growth": "成長的三道閘（疲勞、今天第幾場、對手的檔）：核心的 team 讀；探索包的遭遇照它打折",
    "secret_recipes": "口訣與秘方：意境效果、鑄器的隱藏配方 forge_secrets 讀；合成、自創、人物對話也叫",
    "forge_secrets": "打造的隱藏配方與神器譜：核心的 content 驗內容時讀；鐵匠鋪、榜單、店面、假人都叫",
    "divine": "神器輪替（這個伺服器現世過哪幾件、每一季開哪幾件）：核心的 sqlite_world 換季時讀",
    "equipment": "裝備四欄的共用部分（耐久、損耗）：核心的 team 讀；酒肆包、鐵匠鋪、馬市、懸賞、寶物都叫",
    "weapons": "兵器（加成、損耗、本命兵器）：核心的 team、content 讀；鐵匠鋪、懸賞、店面都叫",
    "armor": "防具（少扣的氣血與內傷、耐久）：核心的 team、content 讀；鐵匠鋪、店面都叫",
    "mounts": "坐騎（移動省體力、騎兵加成）：核心的 team 讀；決戰包的進場快照、輿圖、截殺、馬市都叫",
    "treasures": "寶物與好馬的來源與加成：核心的 rules、team 讀；出陣、酒肆兩包與修練、玉璽都叫",
    "materials": "素材的掉落與背包：核心的 content、rules 讀；決戰、探索、出陣三包的掉落都經它",
    "four_tiers": "素材四階的小規則：決戰、出陣兩包的掉落與鐵匠鋪、經濟、名聲都讀",
    "silver": "銀兩出口的數（21 天季多的花銀兩的地方）：修練、鐵匠鋪、店面讀",
    "economy": "素材與經濟的純規則（升階、捐軍備的上限）：店面、玩法說明、假人讀；銀兩出口、鐵匠鋪、馬市成包之後都還要",
    # 季的世界模型第一批（11 個；第 40 批再收 figures、figure_life、plans、orders、ranks、chapters）：核心的 rules、content、sqlite_world 讀，
    # 決戰、出陣、酒肆與之後的軍情、陣營、大勢人物都靠它們知道這一季的局面
    "timetable": "時刻表（季曆上的大事什麼時候發生、怎麼結算）：核心的 content、rules、sqlite_world、world_state 讀；決戰包的管理者工具、"
                 "軍情、地盤都叫（讀大勢人物 figures、chapters 記在邊界測試的 SHARED_PENDING：第 40 批收進這一層）",
    "front_lines": "戰況變化的說法（大勢@<線> 換成一句話）：核心的 content、journal、rules 讀；決戰包的戰況也用",
    "push": "推力的算式（陣營人數緩衝、每人每日上限、貢獻）：出陣包的約戰與大勢人物、軍令、四勝利都讀",
    "allied": "豪強分屬兩軍（依附哪一軍）：核心的 rules、sqlite_world 讀；決戰、出陣、酒肆三包與懸賞、叛投都叫",
    "wins": "三陣營四勝利（豪強兩本帳、季末四階）：核心的 content、rules 讀；決戰、出陣兩包與列傳、軍情都叫",
    "relations": "人物之間的關係：大勢人物、人物活起來、懸賞、人物對話讀",
    "deeds": "世界記事（你做的事被世界記住）：探索包的走一趟、人物活起來、章回都讀",
    "seats": "第四階席次與每週輪替：叛投、晉升、世界一步讀（讀 ranks 的稱號記在 SHARED_PENDING：第 40 批收進這一層）",
    "factions": "陣營規模的換算：席次 seats 讀；陣營成包（第 35 批）之後還要",
    "week_unlock": "功能照週解鎖與三週主題：擂台、懸賞、輿圖、本週卡讀",
    "roster": "同伴的名下與全服唯一：核心的 rules 讀；決戰、出陣、酒肆三包與人物情誼、懸賞、叛投都叫",
    # 地盤與攻城（siege 第 11 批已登記，在最上面）、醫館、散人、一類一顆（行動與地盤＋散人區）
    "territory": "地盤易手（誰控制、駐軍、大本營）：核心的 content、rules、team 讀；探索、出陣、酒肆三包與輿圖、懸賞、經濟都叫",
    "conquest": "領地爭奪的規則（區塊、進度、推、拉、易手）：核心的 content、rules 讀；決戰、出陣兩包與輿圖、軍令、之後的地盤包都叫"
                "（讀璽效 seal_acts 記在邊界測試的 SHARED_PENDING：第 51 批那一半進這一層）",
    "clinic": "醫館（只在城鎮療傷、最近的醫館在哪）：核心的 team 讀；修練頁的療傷、名師指點、買破境丹都問（總表附錄甲：醫館是核心的服務）"
              "（讀輿圖的路線 atlas 記在 SHARED_PENDING：第 50 批那一半進這一層）",
    "ranger": "遊俠名號（散人的成長階梯、經驗倍數）：核心的 rules 讀，Game 的戰後獎勵與狀態列也叫；出陣包與懸賞（bounties）、同伴招募（roster）、"
              "玩家卡（social）、行狀（annals：列傳讀它記下的名號）都叫",
    "precise": "一類一顆（每一顆行動鈕只給一類東西）與算不算城鎮（is_town）：出陣、探索、引導三包的獎勵與懸賞、有所感、玩法說明讀",
    # explore（全部拆包第 18 批）
    "training": "城外分級（最弱的對手分一二三級、江湖話、輿圖地點詳情那一句）：探索包的 _practice_tier、輿圖的地點卡與詳情、引導包的提示與新手目標都讀",
    # 其餘（12 個；總表寫 20 個，events、tiers、narration、leaderboard、rumor_view 先不收：讀擂台、伏筆、機緣，理由在 SHARED_LATER）
    "renown": "名聲（名望、善惡稱號、跨段）：核心的 rules、team、world_state 讀；決戰、探索、宴客、酒肆四包與十幾個舊模組都叫（總表附錄甲裁定）",
    "speech": "玩家寫給別人看的一句話（擋髒話）：探索包的題壁、形象包的招式名與名帖、挑釁共用（總表附錄甲裁定）",
    "jianfa_numbers": "減法季的數字（自己的 pydantic 模型、不 import models）：核心的 models 掛它（總表附錄甲裁定）",
    "outcomes": "隨口應對分岔的純規則：事件檢定（engine，總表第 16 批搬進核心）讀；接 event_llm 的評分",
    "marks": "地方痕跡看得見的純規則：事件、世界一步、天下形勢讀",
    "ollama_client": "本機模型的 client：核心的 naming 讀；人物對話、取名、判讀十幾個舊模組與殼、腳本都經它（模型服務）",
    "power_save": "省電模式（模型卸不卸）：ollama_client 讀；殼 server.py（有人登入就叫模型載起來）與主機端的 warm_keeper 也用（模型服務）",
    "zh": "簡繁轉換（模型寫的字轉成台灣正字）：核心的 content、naming 讀；探索、酒肆兩包與十幾個舊模組都叫（模型服務）",
    "event_llm": "探索的隨口應對（模型只評一個機率）：事件檢定（engine）、隨口應對分岔 outcomes 讀；殼的三段式也用（模型服務）",
    "flavor": "重複內容的模型潤色（世界事件傳聞全服只潤一次）：核心的 sqlite_world 讀；世界一步也叫（模型服務）",
    "playlog": "真人量表（每個帳號每天按了哪幾顆）：只 import 核心的 database；殼記帳、量表腳本讀",
    "prologue": "序章（草廬那幾步）：決戰、探索、出陣、酒肆四包都問「還在序章裡」，引導、開局、輿圖也讀",
    # battle（全部拆包第 8 批：generals 進決戰包時，共用規則層的 siege 讀的那一塊留在這一層；第 15 批 PM 認定第 2 條）
    "chiefs": "龍頭上陣的挑法（誰上陣、份量、池子；原本 generals 的 on、pick）：決戰包開集結派人上陣、共用規則層 siege 的攻城留守都讀",
    # companions（全部拆包第 19 批「先做」：stances 拆兩半，總表附錄甲；行動那一半在人物情誼包）
    "stance_world": "人物心意的世界那一半（這一週的計數、誰照哪一個做事、門檻、換手、每週歸零）：核心的 rules、事件檢定與舊模組 world、figures、events 都讀",
    # story（全部拆包第 30 批：storyline 拆兩半，換字那一小段與別包也要讀的底座在這一層，一條線自己的走法在一條線包）
    "story_base": "一條線的底座與換字：核心的 rules〔fill_marks 換字〕、事件檢定〔記自己寫的那一句〕讀；探索包的擲開頭、有所感包登記頓悟那一條線的鉤子也讀"
                  "（讀輿圖的大區 atlas、章回的大事結果 chapters 記在邊界測試的 SHARED_PENDING）",
    # craft（全部拆包第 44 批「煉製與自創」：create 進煉製包，認勢要用的擺式幾何抽出來留在這一層）
    "pose": "擺式的幾何（火柴人九個角度 → 勢與偏向，原本在 create.py）：以意成招 moves 認勢讀；煉製包的 create 照名字 re-export，門下頁的說明也讀",
}
