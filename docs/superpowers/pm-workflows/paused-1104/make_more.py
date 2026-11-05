"""接下來幾批的派工（第 21、30、31、29、14、18、33、43、44、25、32、34、37、39、46 批）。用法：make_more.py <批號> <split/trunk SHA> [輸出資料夾]
先把 feature 分支快轉或開在那一筆，再把產生的 b<批號>.js 交給 Workflow。第 31 批的包名不用總表寫的 `figures`：`tianxia/figures.py` 留著，同名不准（第 23 批的教訓）。"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = (REPO / "split-batch.js").read_text(encoding="utf-8").replace("\r\n", "\n")
N, BASE = sys.argv[1], sys.argv[2]
OUT = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).parent

COMMON_BODY = [
    "- same_behavior 新開的軌一律用原創名字（PM 11/04，第 22 批認定第 3 條）。",
    "- 前幾批的 PM 認定在手冊第十五節，開工先用 grep 找跟這一包有關的，不要整節讀。**不准碰 `web/`**；動到路由的話，自己那一軌每一條都要打到（web/ 沒動就沒有實機驗收）。",
    "- 這一批搬的模組若是世界層代叫的舊模組（`tianxia/world.py` 開頭模組說明「另外要跑的」反過來那一段點名的，例：`figure_life`、`bounties`），`test_for` 挑不到 `test_world` 那一串：開發與修正另跑那一段列的檔（第 25 批 PM 認定第 7 條）。",
    "- 審查常抓到的（第 19、20 批）：總表附錄甲點名這一批的方法與測試檔有沒有漏；這一批搬進來的 `PlayerState` 欄位 `player_fields` 與 README 有沒有認領；「列舉每一包」的表（`STAGE_PACKAGES`）；情境有沒有真的走到（看輸出裡有沒有預期的按鈕或句子，不是只看 200）。",
]

BATCHES = {
    "21": dict(
        title="交友求見——交友、求見、打發、次數、結識奇遇（新包 `socialize`）",
        pkg="socialize", feature="feature/socialize", dev="dev/socialize-1", host="socialize1",
        plan="docs/superpowers/plans/2026-11-04-交友求見包-第1批.md",
        ports={"dev": 8179, "rev": 8180, "fix": 8180, "head": 8181, "base": 8182}, fb="FB-9320～FB-9329",
        body=[
            "- 範圍照總表 3.3 第 21 列（約 31 個方法、305 行）與第二節「交友求見（`socialize`）」、附錄甲與丙的裁定。`call:` 前綴；`bot_policy.score` 的 `call:` 那一段搬進包的 `bots.py`。對話、閉門不見經查詢服務叫，不 import 人物情誼包。",
            "- 第 20 批留給這一批的 `PlayerState` 欄位：`talks_today`、`picking_audience`，這一批認領。",
            "- 順手改 `tianxia/features/companions/README.md` 第 20 批修正輪之前的兩句（`talk:`、`parley:` 的 choose 現在走掛鉤；委派現在是 41 個，第 20 批 14 個），只動字。",
            "- Task 1 的情境：交友（人物在與不在）、求見（成、被打發、次數用完）、結識奇遇；三種設定；半舊半新切在挑對象挑到一半（`picking_audience`）；假人碰得到 `call:`。season21 一個地點只有一位人物時選單會收合，要把名望擺高才看得到（第 20 批的教訓）。",
        ]),
    "30": dict(
        title="一條線＋簽到（小包併批）——`storyline` 進新包 `story`（換字那一小段留核心）、`story:` 前綴、四個故事事件檔；`checkin` 進新包 `checkin`",
        pkg="story", feature="feature/story", dev="dev/story-1", host="story1",
        plan="docs/superpowers/plans/2026-11-04-一條線簽到-第30批.md",
        ports={"dev": 8183, "rev": 8184, "fix": 8184, "head": 8185, "base": 8186}, fb="FB-9330～FB-9339",
        body=[
            "- 範圍照總表 3.3 第 30 列（13 個方法、126 行；一條線 10／90，簽到 3／36）與第二節「一條線（`story`）」「簽到（`checkin`）」。一批開兩個包，登記各寫各的段（`# story`、`# checkin`），舊名留別名。",
            "- Task 1 的情境：一條線答題（對、錯）、打一場、期限到、結局寫進傳；簽到當天第一次、重複、斷簽；三種設定；半舊半新切在答題答到一半，或簽到當天還沒領；假人碰得到這兩包的選項。",
        ]),
    "31": dict(
        title="大勢人物——挑戰本人、護衛犒軍探望（`aid:`）、助他一臂或壞他的事（`plan:`）、月旦評三段式、管理者救回人物（`figure_aid`、`yuedan` 進新包 `figure_acts`）",
        pkg="figure_acts", feature="feature/figure-acts", dev="dev/figure-acts-1", host="figureacts1",
        plan="docs/superpowers/plans/2026-11-04-大勢人物包-第1批.md",
        ports={"dev": 8187, "rev": 8188, "fix": 8188, "head": 8189, "base": 8190}, fb="FB-9340～FB-9349",
        body=[
            "- 範圍照總表 3.3 第 31 列（約 24 個方法、388 行）與第二節「大勢人物」。**包名用 `figure_acts`，不是總表寫的 `figures`**：`tianxia/figures.py` 留著，同名不准（`scripts/new_feature.py`，第 23 批的教訓）。",
            "- `bot_policy` 裡 `aid:`、`ambush:`、`works:` 共用的那一行拆開，`aid:` 搬進包的 `bots.py`。",
            "- Task 1 的情境：挑戰本人（閉門不見、勝、和、敗、掉寶物與三四階料）、護衛犒軍探望、助他一臂與壞他的事、月旦評 A、B、C 三段（模型回與模型擋著）、管理者救回人物；三種設定；半舊半新切在月旦評寫到一半或助他一臂還沒結；假人碰得到 `aid:`。",
        ]),
    "29": dict(
        title="列傳——寫傳三段式、休季三顆、行狀頁與分享、`zhuan_html.py`、server 的列傳那一段與 5 條路由（`biography`、`zhuan_end` 進新包 `zhuan`）",
        pkg="zhuan", feature="feature/zhuan", dev="dev/zhuan-1", host="zhuan1",
        plan="docs/superpowers/plans/2026-11-04-列傳包-第1批.md",
        ports={"dev": 8191, "rev": 8192, "fix": 8192, "head": 8193, "base": 8194}, fb="FB-9350～FB-9359",
        body=[
            "- 範圍照總表 3.3 第 29 列（約 20 個方法、219 行）與第二節「列傳（`zhuan`）」。`zhuan:` 前綴。**先做**：`annals`、`content`、商城三處 import 列傳的地方，改走核心服務或 `check_content`。",
            "- 鎖外的三段式照第 24 批 `sense_draw` 的做法，模型呼叫不進鎖。戰記（`tale.py`、server 的 TALES）不碰。",
            "- Task 1 的情境：寫傳 A、B、C 三段（模型回與模型擋著）、休季三顆、行狀頁、分享頁，5 條路由都打到；三種設定；半舊半新切在寫傳寫到一半；假人碰得到 `zhuan:`（碰不到就寫明）。",
        ]),
    "14": dict(
        title="拿掉二：週末設定、不帶設定的 14 天季（甲：只關門）（**不是純搬**：week7、season21、test 三種設定一個字不變）",
        pkg="strip", feature="feature/strip", dev="dev/strip-2", host="strip2",
        plan="docs/superpowers/plans/2026-11-04-拿掉二-第14批.md",
        ports={"dev": 8151, "rev": 8152, "fix": 8152, "head": 8153, "base": 8154}, fb="FB-9360～FB-9369",
        all_tracks=True,
        body=[
            "- 範圍照總表 3.3 第 14 列（0 個方法）：**甲，只關門**。拿掉 `profiles/weekend.json`；`server.py`、`run_bots.py` 沒帶 `TIANXIA_PROFILE` 時套 season21，啟動時照舊印出來；用 weekend 的腳本與測試改用 week7。`config.json` 的值不動。`calendar`、`figures`、`timetable` 照季長分岔的幾段，只拿專給 weekend 的那幾支（開工時量），14 天的留著。",
            "- **承諾**：week7、season21、test 三種設定 same_behavior 一個字不變；none、weekend 不再是可以選的設定，`same_behavior.py` 的 `PROFILES` 跟著改，計畫寫清楚。",
            "- `same_behavior.py` 的假人軌寫死帶 none、weekend（train、arts、sortie）：改成只跑 `PROFILES` 裡的，`--profiles` 給什麼就跑什麼。`docs/superpowers/pm-workflows/trunk_daily.py` 的 `BOTS` 改回 `[]`、`PROFILES` 拿掉。",
            "- 第 13 批留給這一批的清單在總表第 14 列（初入江湖兩步的字、新手目標 field2、`h_field_lose`、序章與懸賞的「尋敵」「操練」字）：none、weekend 關門之後走不到的一起清，week7、season21 走得到的一字不動。拿掉型的批刪之前看斷言，不要只看名字（第 13 批把活規則的測試刪掉過）；用 `scratchpad\\b13\\removed_names.py`、`mark_diff.py` 靜態掃。",
            "- CLAUDE.md 與導覽裡寫週末設定的段落，計畫第五節列出來交 PM 改（你不改 CLAUDE.md）。",
        ]),
    "33": dict(
        title="軍情一——軍令卡與應召、押糧、第 2 階晉升奇遇、第 3／4 階行動、席次輪替與召見（`rank_actions` 進新包 `military`）",
        pkg="military", feature="feature/military", dev="dev/military-1", host="military1",
        plan="docs/superpowers/plans/2026-11-05-軍情包-第1批.md",
        ports={"dev": 8159, "rev": 8160, "fix": 8160, "head": 8161, "base": 8162}, fb="FB-9380～FB-9389",
        body=[
            "- 範圍照總表 3.3 第 33 列（約 17 個方法、280 行）與第二節「軍情」、附錄甲與丙的裁定。**包名用 `military`，不是總表寫的 `orders`**：`tianxia/orders.py` 這一批不搬，同名不准（第 23 批的教訓）。`act:rank2`、`act:convoy`、`act:summons` 在 `_act` 留委派。機緣、伏筆是第 34 批，不搬。",
            "- Task 1 的情境：軍令卡與應召（接、截止、過期）、押糧、第 2 階晉升奇遇、第 3／4 階行動、席次輪替與召見；三種設定；半舊半新切在軍令接了還沒交或押糧走到一半；假人碰得到（碰不到就寫明）。",
        ]),
    "43": dict(
        title="銀兩出口與捐軍備——捐素材、捐銀兩、名師指點、買破境丹、打點門路與帳簿（新包 `outlets`）",
        pkg="outlets", feature="feature/outlets", dev="dev/outlets-1", host="outlets1",
        plan="docs/superpowers/plans/2026-11-05-銀兩出口包-第1批.md",
        ports={"dev": 8163, "rev": 8164, "fix": 8164, "head": 8165, "base": 8166}, fb="FB-9390～FB-9399",
        body=[
            "- 範圍照總表 3.3 第 43 列（約 17 個方法、225 行）與第二節「銀兩出口（`outlets`）」。`donate:`、`dadian:` 前綴；`bot_policy.score` 那兩段搬進包的 `bots.py`。看火候跟鐵匠鋪共用規則層的 `silver`，`silver.py` 留在共用規則層。",
            "- Task 1 的情境：捐素材、捐銀兩、名師指點、買破境丹、打點門路與帳簿（成、錢不夠、次數滿）；三種設定；半舊半新切在打點開了還沒結；假人碰得到這兩個前綴（碰不到就寫明）。",
        ]),
    "44": dict(
        title="煉製與自創——意境合成與揣摩（取名三段式、預覽、`/api/forge_line`）、自創五步、重悟帖、作罷（`create` 進新包 `craft`）",
        pkg="craft", feature="feature/craft", dev="dev/craft-1", host="craft1",
        plan="docs/superpowers/plans/2026-11-05-煉製自創包-第1批.md",
        ports={"dev": 8167, "rev": 8168, "fix": 8168, "head": 8169, "base": 8170}, fb="FB-9400～FB-9409",
        body=[
            "- 範圍照總表 3.3 第 44 列（約 16 個方法、126 行）與第二節「煉製與自創（`craft`）」。`create` 進包（舊名留別名），`fusion` 不搬，留共用層。鎖外的取名三段式照第 24 批 `sense_draw` 的做法，模型呼叫不進鎖。`/api/forge_line` 那一條自己的軌要打到。",
            "- Task 1 的情境：意境合成與揣摩（取名 A、B、C 三段，模型回與模型擋著）、預覽、自創五步走完與作罷、重悟帖；三種設定；半舊半新切在自創走到一半；假人碰得到（碰不到就寫明）。",
        ]),
    "25": dict(
        title="世界層掛鉤（核心批）——世界一步、每週、每天；世界層的開季與換季；全服收季；開集結；`world.py` 收進核心本體",
        pkg="core_world", feature="feature/core-world", dev="dev/core-world-1", host="coreworld1",
        plan="docs/superpowers/plans/2026-11-05-世界層掛鉤-第25批.md",
        prev_plan="docs/superpowers/plans/2026-11-01-核心收接縫.md",
        ports={"dev": 8150, "rev": 8151, "fix": 8151, "head": 8152, "base": 8153}, fb="FB-9410～FB-9419",
        reviewers=3, dev_model=None, all_tracks=True,
        parallel="**核心批單獨跑**（總表 5.2 第 3 條）：這段期間沒有別的拆包批在開發。PM 開 `feature/core-world` 在 split/trunk 這一筆",
        body=[
            "- **這一批是核心批，沒有新包**：範圍照總表 3.3 第 25 列整格、第 15 列「`world.py` 兩份名單都沒有…第 25 批改成世界層掛鉤之後收進核心本體（`MODULES` 加一個）」、手冊第十五節「第 12 批的 PM 認定」第 2 條。下面 Task 2～4 寫「搬進 `tianxia/features/<包>/`」的地方換成：**Task 2** 在 `tianxia/core/features.py` 開掛鉤（寫法照第 11 批的接縫掛鉤與 `on_season_close`：位置固定、不看包的 `enabled`、照 `registered()` 問），`services.py` 補要的服務；**Task 3** 把 `world.py`、`sqlite_world.py` 裡直接叫包與還沒成包的舊模組的地方改成叫掛鉤或服務，各包在自己的 `rules.py`／`actions.py` 掛上自己那一格（各包加的集中在那一包的檔裡），`world.py` 進核心 `MODULES`；**Task 4** 契約測試與邊界測試（核心不 import 包，`world.py` 也一樣）。",
            "- **要開的掛鉤**（總表第 25 列）：世界一步、每週、每天（取代 `world.advance_world_state` 裡的直接呼叫和 `WEEKLY`、`DAILY` 兩張表）；世界層的開季與換季（`sqlite_world` 的 `open_season`、`next_season`）；全服收季（`world.end_season`）；開集結（`world._open_claimed`，裡面延後 import 的 `seal`、`works`、`generals`）。`world.py` 讀宴客散席那一處、經舊名 `arena` 叫單挑包 `close_season`（收季那一刻排擂台前三名）那一處，一起改成掛鉤或服務。",
            "- **順序就是行為**：每一個掛鉤叫各包的順序必須跟現在的呼叫順序一模一樣（同一步裡先推誰、後推誰、亂數抽到的順序都算）。順序寫死在核心（一張明確的順序表或照 `FEATURES` 的固定位置，計畫寫清楚哪一種與理由），加一條契約測試鎖住順序；不要靠 import 順序或註冊先後碰運氣。",
            "- `world.py` 現在 import 的共用規則層模組（`registry.SHARED` 裡的）照舊直接 import；import 包或還沒成包、不在共用層的舊模組的，一律改掛鉤或服務。真的改不了的標 `# 過渡：待搬` 並在計畫第五節寫理由與該由哪一批收（例：第 26、27、32 批）。`SHARED_PENDING` 裡跟 `world` 有關的那幾條（含「連帶載入 bout」）照改完的實際情況改。",
            "- Task 1 的情境：**所有軌**都要跑（核心批）。這一批特別要走到的：世界一步跨過每天與每週的界線（同一步裡跨好幾天）、開季、收季（自然收季與管理者立刻收季，含擂台前三名與宴客散席）、開下一季、開集結（大勢門檻與時刻表兩種）；week7、season21、test 三種設定；半舊半新切在世界一步推到一半（base 推過某一天，head 接著推過下一週）；假人照常跑。現有的軌已經走到的就不另加，計畫第一節列出哪一軌走到哪一個掛鉤。",
            "- **不改的**：資料庫結構（develop 第 9 版）；`world_state.py` 的時間讀法；戰記、輿圖、鐵匠鋪、`web/`。",
        ]),
    "32": dict(
        title="效果與叛投掛鉤（核心批）——`rules.apply_effect` 照效果欄位分派給主人；叛投時各包清自己的進度",
        pkg="core_effects", feature="feature/core-effects", dev="dev/core-effects-1", host="coreeffects1",
        plan="docs/superpowers/plans/2026-11-06-效果與叛投掛鉤-第32批.md",
        prev_plan="docs/superpowers/plans/2026-11-05-世界層掛鉤-第25批.md",
        ports={"dev": 8154, "rev": 8155, "fix": 8155, "head": 8156, "base": 8157}, fb="FB-9420～FB-9429",
        reviewers=3, dev_model=None, all_tracks=True,
        parallel="**核心批單獨跑**（總表 5.2 第 3 條）：這段期間沒有別的拆包批在開發。第 25 批（世界層掛鉤）已合；PM 開 `feature/core-effects` 在 split/trunk 這一筆",
        body=[
            "- **這一批是核心批，沒有新包**：範圍照總表 3.3 第 32 列整格與第六節第 1 條（「效果與叛投」「叛投清軍情的進度」）。下面 Task 2～4 寫「搬進 `tianxia/features/<包>/`」的地方換成：**Task 2** 在 `tianxia/core/features.py` 開兩個掛鉤（寫法照第 11 批的接縫掛鉤與第 25 批的世界層掛鉤：位置固定、不看包的 `enabled`、照 `registered()` 問）；**Task 3** 把 `rules.apply_effect` 與叛投（`defection.defect`、`Game._defect_step` 那一路）裡直接碰各包的地方改成叫掛鉤，各包在自己的檔裡掛上自己那一格；**Task 4** 契約測試與邊界測試。",
            "- **掛鉤一：效果分派**。`rules.apply_effect` 照效果欄位分派給主人：晉升、帶兵、招同伴、伏筆、碎片、屯糧、四勝利記帳。**呼叫點一個都不動**。總表說「位置不影響結果」，開發要自己證明：同一則效果帶好幾個欄位時，回傳的訊息行順序、世界旗標與狀態寫入的先後都算行為，分派順序寫死在核心（明確的順序表），契約測試鎖住；證明不了位置無關的，就照現在的順序。",
            "- **掛鉤二：叛投清進度**。叛投那一刻各包清自己的進度（軍情包 `military` 的軍令與押糧、還有誰在叛投時被清，照現行程式量），不再由叛投那一側伸手進別包。清的順序照現在的。",
            "- 主人還沒成包的（伏筆是第 34 批、碎片是第 27 批……照現行程式量）：那一格先掛在舊模組上、標 `# 過渡：待搬`，計畫第五節寫由哪一批收；主人在共用規則層的照共用層的寫法掛。陣營包（第 35 批）會把 `defection` 搬走，這一批不搬它，只把叛投那一側改成叫掛鉤。",
            "- Task 1 的情境：**所有軌**都要跑（核心批）。這一批特別要走到的：事件效果分別帶上面七種欄位、還有一則同時帶好幾種的；叛投時手上有軍令、押糧在路上、其他會被清的進度各一；week7、season21、test 三種設定；半舊半新切在叛投確認到一半（先按、還沒確認）或效果套到一半的事件；假人照常跑。現有的軌已經走到的就不另加，計畫第一節列出哪一軌走到哪一個欄位。",
            "- **順手收**（第 25 批 PM 認定第 2 條）：`log_archive`（封存舊季的傳聞與回合紀錄；只有 `sqlite_world`、`database` 用，自己不 import 任何 tianxia 模組）兩份名單都沒有，收進核心本體（`MODULES` 加一個）；先想好 `test_for` 的「核心測試」會不會因此多收檔（第 25 批 `NOT_CORE_TESTS` 的先例），計畫第五節寫多收了幾條。",
            "- **不改的**：資料庫結構（develop 第 9 版）；戰記、輿圖、鐵匠鋪、`web/`。",
        ]),
    "34": dict(
        title="軍情二——機緣（`opp:`）與伏筆（`fs:`）；`opportunities`、`foreshadow` 進包 `military`；`ranks` 讀機緣改查詢服務",
        pkg="military", feature="feature/military", dev="dev/military-2", host="military2",
        plan="docs/superpowers/plans/2026-11-06-軍情包-第2批.md",
        prev_plan="docs/superpowers/plans/2026-11-05-軍情包-第1批.md",
        ports={"dev": 8158, "rev": 8159, "fix": 8159, "head": 8160, "base": 8161}, fb="FB-9440～FB-9449",
        body=[
            "- 範圍照總表 3.3 第 34 列（5 個方法、85 行，加 `opportunities` 973 行、`foreshadow` 770 行兩個模組，測試 257 條）與第二節「軍情」。包名照第 33 批用 `military`（`tianxia/orders.py` 留著，同名不准）。`ranks` 讀機緣改成查詢服務；伏筆的內容檢查改成 `check_content`；搬 `bot_policy` 的 `opp:` 那一段。",
            "- **第 32 批留給這一批的過渡格**：`tianxia/rules.py` 效果分派裡伏筆那幾格、`tianxia/defection.py` 叛投清進度裡機緣那兩格（標「過渡：待搬（第 34 批）」；grep 時連「過渡：第 34 批」一起找），主人搬進包之後由包登記，`EFFECT_ORDER`／`DEFECT_ORDER` 的位置不准動（順序就是行為，第 32 批 PM 認定第 1 條）。",
            "- Task 1 的情境：機緣（出現、接下、做完、過期）、伏筆（埋下、事件推進、收線、拿到物品）；事件效果帶伏筆的欄位；叛投時手上有機緣；三種設定；半舊半新切在機緣接了還沒做完、伏筆埋了還沒收；假人碰得到 `opp:`（碰不到就寫明）。",
        ]),
    "37": dict(
        title="玩家互動一——此地還有、玩家卡、邀請框、打招呼、贈物、名帖、`/api/peer` 與 `/api/mingtie` 四條路由（`social`、`invites`、`mingtie`、`mingtie_card` 進新包 `peers`）",
        pkg="peers", feature="feature/peers", dev="dev/peers-1", host="peers1",
        plan="docs/superpowers/plans/2026-11-06-玩家互動包-第1批.md",
        ports={"dev": 8162, "rev": 8163, "fix": 8163, "head": 8164, "base": 8165}, fb="FB-9450～FB-9459",
        body=[
            "- 範圍照總表 3.3 第 37 列（31 個方法、365 行）與第二節「玩家互動（`peers`）」。**先做**：「此地還有」的判斷（窗口 `Config.presence_seconds`）與狀態列的身分字，從 `social` 拆成核心服務，其他包（截殺、酒肆查人、通緝）改問服務；`tests/test_tavern_seek_presence.py` 守的不變量照舊成立。切磋、論武、截殺是第 38 批，不搬。",
            "- 四條路由跟著搬進包的 `routes.py`（照商城的做法）；`web/` 不准碰，所以沒有實機驗收，自己那一軌四條路由每一條都要打到、看回應的內容不是只看 200。",
            "- Task 1 的情境：同一地點有別人（24 小時內同步過、不在路上）與沒有；看玩家卡；邀請（送出、接受、過期 `invite_ttl_seconds`）；打招呼；贈物；名帖（寫、看、分享）；三種設定；半舊半新切在邀請送出還沒接受；假人照常（任何畫面都不能透露誰是假人）。",
        ]),
    "39": dict(
        title="體力玩法＋閉關（小包併批）——設伏、屯糧（`ambush`、`works` 進新包 `stamina_plays`，`works.on_muster` 掛「開集結」）；閉關（新包 `seclusion`）",
        pkg="stamina_plays", feature="feature/stamina-plays", dev="dev/stamina-plays-1", host="stamina1",
        plan="docs/superpowers/plans/2026-11-06-體力玩法閉關-第39批.md",
        ports={"dev": 8166, "rev": 8167, "fix": 8167, "head": 8168, "base": 8169}, fb="FB-9460～FB-9469",
        body=[
            "- 範圍照總表 3.3 第 39 列（10 個方法、240 行）與第二節「體力玩法（`stamina_plays`）」「閉關（`seclusion`）」。一批開兩個包，登記各寫各的段（`# stamina_plays`、`# seclusion`），舊名留別名；搬 `bot_policy` 的 `ambush:`、`works:` 兩段。",
            "- `works.on_muster` 現在是第 25 批世界層「開集結」那一格的主人（舊模組），搬進包之後改由包登記，`WORLD_ORDER` 的位置不准動（順序就是行為，第 25 批 PM 認定第 1 條）。第 25 批量到：三種設定的屯糧（`Config.stockpile`）都關著、`on_muster` 什麼都不寫，Task 1 要在那一下把它打開才看得到。",
            "- Task 1 的情境：設伏（埋、中伏、撤）、屯糧（捐、練兵、開集結那一刻結算）、閉關（1～12 小時、`act:break` 提早出關）；三種設定；半舊半新切在設伏埋了還沒中、閉關閉到一半；假人碰得到 `ambush:`、`works:`。",
        ]),
    "46": dict(
        title="地盤——戰書與攻城時段、22:00 換天、〈天下形勢〉三段式、地盤畫面的資料、分紅與守城功、管理者五個救場工具（`conquest_day`、`xingshi` 進新包 `territory_acts`）",
        pkg="territory_acts", feature="feature/territory-acts", dev="dev/territory-acts-1", host="territory1",
        plan="docs/superpowers/plans/2026-11-06-地盤包-第1批.md",
        ports={"dev": 8170, "rev": 8171, "fix": 8171, "head": 8172, "base": 8173}, fb="FB-9470～FB-9479",
        body=[
            "- 範圍照總表 3.3 第 46 列（27 個方法、431 行）與第二節「地盤」。**包名用 `territory_acts`，不是總表寫的 `territory`**：`tianxia/territory.py` 這一批不搬，同名不准（第 23 批的教訓）。這一批不等輿圖那條線（交接第三節），照現行程式搬。",
            "- **先做**：`conquest_day` 的 `void`、`note_void`、`today` 搬進 `conquest`（共用規則層），攻城與軍令就不必 import 包。`/api/xingshi` 跟著搬進包的 `routes.py`；`web/` 不准碰，自己那一軌要打到那條路由、看內容。〈天下形勢〉是三段式，模型呼叫不在鎖裡的寫法照舊。",
            "- 22:00 換天若經第 25 批的世界層「每天」那一格，主人換成包登記、`WORLD_ORDER` 位置不准動。",
            "- Task 1 的情境：下戰書、攻城時段、22:00 換天（跨過與沒跨過）、〈天下形勢〉、分紅與守城功補送、管理者五個救場工具各一次；三種設定（地盤要劇本有陣營、寫了 `territory`；設定關著的那一種寫明走不到）；半舊半新切在戰書下了、還沒到攻城時段；假人照常。",
        ]),
    "18": dict(
        title="探索三——序章草廬四景與探索的底：權重、野怪、自家營寨比劃、練功分級、撿破境丹",
        pkg="explore", feature="feature/explore", dev="dev/explore-3", host="explore3",
        plan="docs/superpowers/plans/2026-11-04-探索包-第3批.md",
        ports={"dev": 8155, "rev": 8156, "fix": 8156, "head": 8157, "base": 8158}, fb="FB-9370～FB-9379",
        body=[
            "- 範圍照總表 3.3 第 18 列（9 個方法、107 行）。`training` 剩下的分級（`TIER_WORDS`、`PLACE_LINE`、`is_town`、`tier_of`）**不進探索包**，進共用規則層；`_practice_tier` 列成探索包的查詢服務。",
            "- Task 1 的情境：接在探索那一軌：序章草廬四景、權重、野怪、自家營寨比劃、練功分級、撿破境丹；三種設定；半舊半新切在序章探索走到一半；假人。",
        ]),
}

b = BATCHES[N]
DEFAULTS = {"reviewers": 2, "dev_model": "sonnet", "after15": True,
            "prev_plan": "docs/superpowers/plans/2026-11-04-人物情誼包-第2批.md"}
PARALLEL = (f"同時在跑的批看 split/trunk 交接第一節「現在在跑」。這一批從 split/trunk `{BASE}` 開（PM 開 `{b['feature']}` 在這一筆）。"
            "共用登記檔各寫各的段，合併時 PM 照順序接。")
a = {**DEFAULTS, **{k: v for k, v in b.items() if v is not None}, "n": int(N), "base": BASE,
     "parallel": b.get("parallel") or PARALLEL,
     "body": "\n".join(b["body"] + COMMON_BODY)}
if b.get("dev_model", "x") is None:  # 核心批留在 Opus（總表 5.2 第 3 條）：不給 dev_model
    a.pop("dev_model", None)
meta_end = SRC.index("}\n", SRC.index("export const meta")) + 2
body = re.sub(r"\bargs\b", "ARGS", SRC[meta_end:])
s = SRC[:meta_end] + "\nconst ARGS = " + json.dumps(a, ensure_ascii=False) + "\n" + body
(OUT / f"b{N}.js").write_text(s, encoding="utf-8", newline="\n")
print("wrote", OUT / f"b{N}.js")
