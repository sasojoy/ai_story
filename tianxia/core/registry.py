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
    # ── 清單（new_feature.py 接在這一行前面）──
]

# 共用規則層（全部拆包總表第六節第 5 條；第 11 批 PM 定的格式）：還沒、也不會搬進任何一包的規則模組（tianxia/<名字>.py），好幾包都讀。
# 模組名 → 一句誰在用、為什麼在共用層。包 import 這裡的模組不必註「過渡：待搬」；這幾個模組跟核心一樣不准 import 包
# （tests/core/test_feature_boundaries.py 守）。核心本體（tianxia/core/__init__.py 的 MODULES）可以 import 這一層、這一層可以 import 核心
# 本體與同一層。第 11 批只放主人已經寫成「共用規則層」的那一個；戰鬥引擎、武學與裝備、世界模型那幾十個照總表第 15 批登記。
SHARED: dict[str, str] = {
    "siege": "攻城的規則（攻城戰的名字、收場改季、誰贏）：決戰包的攻城與戰況、地盤都讀；總表附錄甲裁定不搬進任何一包",
    # shared（全部拆包第 15 批「共用規則層登記」，計畫 docs/superpowers/plans/2026-11-01-共用規則層登記.md 1.2）：只登記、不搬程式。
    # 戰鬥引擎（9 個）：核心的 team 打每一場都讀，每一種打一場的包都用，放進哪一包都會變成包 import 包
    "encounter": "單次判定（威力差、勝算、四種結果）：核心的 team、content 讀；出陣、酒肆的殺手那一場與大勢人物、單挑都叫",
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
    "moves": "以意成招（自創武學的招）：戰法 tactics、武學 arts、功效 traits 讀；認勢用到的擺式幾何在 create（函式裡 import，"
             "記在邊界測試的 SHARED_PENDING：煉製第 44 批成包之前要處理）",
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
}
