"""接下來幾批的派工（第 21、30、31、29、14、18、33、43、44、25、26、29b（第 29 批之二）、32、34、35、37、39、41、46、47、49、36、40、38、42、48 批）。用法：make_more.py <批號> <split/trunk SHA> [輸出資料夾]
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
    "- **掃原始碼、寫死檔名的測試**跟著改路徑（只改路徑、不改判斷）：搬的方法裡有 `renown.gain(..., \"fame\", ...)` 的，`tests/arts/test_explain2.py` 名望來源那張清單要把那一行從 `engine.py` 改成包裡的檔、照路徑排（第 46 批漏了，主幹全面檢查才抓到，FB-9431）；其他寫死 `\"engine.py\"` 的期望用 `git grep -n '\"engine.py\"' -- tests tianxia/features` 找。`test_for` 挑不到這種測試，開發自己跑一次那幾個檔。",
    "- **事件機制**（第 26 批，11/05 已合）：一包發生的事要別包跟著動，經 `ctx.publish(\"<事件>\", ...)`；現有六種（`win`、`outing`、`explore`、`arrive`、`raid_win`、`battle_end`），同一下各訂閱者的先後是 `tianxia/core/features.py` 的 `BUS_ORDER`，**改它或開新事件先過 PM**（手冊第十五節第 26 批認定）。包登記自己那一格用 `Feature.bus()`，格回 `list[str]` 或 `None`、不准回字串。搬的方法裡有 `self.publish(...)`／`ctx.publish(...)` 的，發布點跟著搬、位置不動；邊界測試的 `bus_bypasses` 擋包直接叫 `bounties.on_*`、`_seal_find`、`_seal_settle`、`convoy_arrives`。",
    "- **數字照重印，不抄舊計畫**：`GAME_DIRECT`、委派、過渡處數一律用 `python tests/core/test_feature_boundaries.py` 在開工那一筆重印的（11/06 第 41 批合完 `GAME_DIRECT` 是 11；第 35、47、29b 三批的計畫都抄了舊的「維持 3」）。`tests/core/test_test_for.py` 拿來當例子的舊模組因為搬走而失效時，照實換一個例子、在測試裡寫明理由與量到的數，不必問 PM（第 35 批認定第 1 條、第 49 批認定第 8 條）；`scripts/test_for.py` 本身的 `IMPORT_CAP` 不准動。",
    "- 這份 clone 的 `git fetch origin <分支>` 只寫 `FETCH_HEAD`、不更新 `origin/<分支>`：一律 `git fetch origin +refs/heads/<分支>:refs/remotes/origin/<分支>`。",
    "- **收進核心或共用層、或把 import 移進函式時，回頭量反方向**（第 36 批認定第 1 條）：`test_for.dependents` 碰到核心模組就不往上走、`module_graph` 只讀最外層的 import，所以依賴它的舊模組原本經它挑到的測試會整串消失。解出 base、head，對每個被它 import 的舊模組各叫一次 `test_for.pick` 比，少挑到的寫進那個模組說明的「另外跑」與計畫第五節，不必問 PM。",
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
    "26": dict(
        title="事件機制（核心批）——一包發生的事、別包跟著動；先開六種事件（懸賞交差四種、玉璽兩種），訂閱順序寫死在核心",
        pkg="core_eventbus", feature="feature/core-eventbus", dev="dev/core-eventbus-1", host="coreeventbus1",
        plan="docs/superpowers/plans/2026-11-06-事件機制-第26批.md",
        prev_plan="docs/superpowers/plans/2026-11-06-效果與叛投掛鉤-第32批.md",
        ports={"dev": 8174, "rev": 8175, "fix": 8175, "head": 8176, "base": 8177}, fb="FB-9480～FB-9489",
        reviewers=3, dev_model=None, all_tracks=True,
        parallel="**核心批單獨跑**（總表 5.2 第 3 條）：這段期間沒有別的拆包批在開發。第 25 批（世界層掛鉤）、第 32 批（效果與叛投）與第 34、37、39、46 批這一波都已合；PM 開 `feature/core-eventbus` 在 split/trunk 這一筆（`feature/core-events`、`dev/core-events-1` 是第 16 批事件檢定用過的名字，不要碰）",
        body=[
            "- **這一批是核心批，沒有新包**：範圍照總表 3.3 第 26 列與第六節第 1、2 條，手冊 3.10 說的「第 2 階有例子再開」的那個機制。下面 Task 2～4 寫「搬進 `tianxia/features/<包>/`」的地方換成：**Task 2** 在 `tianxia/core/features.py` 開事件機制（寫法照第 25 批世界層掛鉤與第 32 批效果掛鉤：發布點位置固定、不看包的 `enabled`、照 `registered()` 問；**每一種事件的訂閱順序寫死在核心**——一張明確的順序表，連還沒成包、先掛在舊模組上的那幾格一起列——契約測試鎖住。第 25、32 批都量到「位置不影響結果」不成立，這一批照同一個做法）；**Task 3** 接上發布點，現在的主人在自己的檔裡掛上自己那一格；**Task 4** 契約測試與邊界測試。",
            "- **先開六種事件**：懸賞交差用的四種（打贏一場、探索一趟、抵達某地、截殺打贏）、玉璽用的兩種（決戰收場、集結開始）。每一種寫明：發布點在哪（就是現在直接叫懸賞／玉璽的那一行，**位置一個都不動**）、帶什麼參數、回傳什麼（訊息行照現在的順序接回原處）、現在有誰該聽。**集結開始**：第 25 批的世界層 `WORLD_ORDER` 的 muster 格已經有 seal（front／works／seal／generals）；先量 `world._open_claimed` 叫 `seal.on_muster` 那一處還在不在，已經被世界層接走的就不另開一份，計畫第一節寫明、交 PM 定。",
            "- **主人還沒成包的**（懸賞是第 45 批、玉璽是第 27 批，截殺是第 38 批）：這一批只開機制與發布點，訂閱那一格先掛在舊模組上、行尾標「# 過渡：待搬（第 N 批）」；第 27、38、45 批搬包時由包登記，位置照順序表不准動。總表第六節第 2 條（第 27 批換決戰收場、集結開始，第 45 批換四種交差）照舊，這一批不搬那幾個模組。",
            "- **原位標「過渡：第 26 批」的那幾處**（`git grep -n \"過渡：第 26 批\"`：`engine.py` `_squad_encounter` 打贏之後的出陣獎勵、遊歷推大勢、約戰開著時不推進度，`_seize_chance`；出陣、修練兩包的 README 也寫了）：一處一處量。只有結果只是「多幾行訊息、互不影響」而且就在發布點上的才收進事件；回傳值有人用（例：`rewards`）、或夾在別的結算中間、先後算行為的，**照舊留原位**，行尾改成「# 留原位：第 26 批（一句理由）」。計畫第一節列成表，交 PM 定。",
            "- Task 1 的情境：**所有軌**都要跑（核心批）。這一批特別要走到的：六種事件各自有人聽的那一刻（打贏一場時手上有懸賞、探索一趟、抵達懸賞的目的地、截殺打贏、決戰收場時身上有玉璽碎片、開集結）；同一下有兩個以上的訂閱者；week7、season21、test 三種設定；半舊半新切在懸賞接了還沒交、決戰集結到一半；假人照常跑。現有的軌已經走到的就不另加，計畫第一節列出哪一軌走到哪一種事件。",
            "- **不改的**：資料庫結構（develop 第 9 版）；戰記、輿圖、鐵匠鋪、`web/`；懸賞榜、玉璽、截殺三個模組本身（第 45、27、38 批搬）。",
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
    "35": dict(
        title="陣營——投靠確認、改幫、叛投、三方卡、結局卡與季末四階、拜入門派（`defection` 進新包 `faction`）",
        pkg="faction", feature="feature/faction", dev="dev/faction-1", host="faction1",
        plan="docs/superpowers/plans/2026-11-06-陣營包-第1批.md",
        ports={"dev": 8178, "rev": 8179, "fix": 8179, "head": 8180, "base": 8181}, fb="FB-9490～FB-9499",
        body=[
            "- 範圍照總表 3.3 第 35 列（20 個方法、252 行，加 `defection` 211 行）與第二節「陣營（`faction`）」。包名 `faction`（`tianxia/factions.py` 是另一個模組、這一批不搬，名字不同可以用；README 寫一句兩者的分別）。`faction:`、`defect:`、`sect:` 三個前綴（`Feature.prefix` 收 tuple，第 11 批 PM 定）；搬 `bot_policy` 的 `defect:`、`sect:` 兩段。",
            "- **第 32 批 PM 認定第 5 條**：`defection.prompt`（叛投確認畫面）直接讀軍情包的押糧（`convoy`）、機緣、懸賞、階，搬 `defection` 時改成查詢服務（軍情包已成包，經 `ctx` 問；懸賞還是舊模組 `bounties`，照共用層或過渡寫法、行尾標「# 過渡：待搬（第 45 批）」）。",
            "- **叛投清進度的掛鉤**（第 32 批開的 `DEFECT_ORDER`，`tianxia/core/features.py`）：叫掛鉤的那一處跟著 `defection` 搬進包，但**順序表留在核心、位置不准動**（順序就是行為，第 32 批 PM 認定第 1 條）；還掛在 `defection.py` 上、主人是別包或別的舊模組的格，照原主人留著，只改 import 的位置。",
            "- Task 1 的情境：投靠（先按 `faction:<id>`、再按 `faction:confirm`）、改幫、叛投（確認畫面上有押糧在路上、有機緣、有懸賞、有階）、拜入門派；季末結局卡與四階；三種設定（陣營要劇本有陣營；測試內容沒有陣營的那一種寫明走不到）；半舊半新切在投靠按了還沒確認、叛投確認到一半；假人碰得到 `defect:`、`sect:`。",
        ]),
    "41": dict(
        title="鐵匠鋪——架上、修、淬煉、一步一步打造與直接開爐、隱藏配方、神器定名、以器配招、收購升階、看火候（`smithing` 進新包 `smithy`）",
        pkg="smithy", feature="feature/smithy", dev="dev/smithy-1", host="smithy1",
        plan="docs/superpowers/plans/2026-11-06-鐵匠鋪包-第1批.md",
        ports={"dev": 8182, "rev": 8183, "fix": 8183, "head": 8184, "base": 8185}, fb="FB-9500～FB-9509",
        body=[
            "- 範圍照總表 3.3 第 41 列（約 23 個方法、381 行，加 `smithing` 825 行）與第二節「鐵匠鋪（`smithy`）」。鐵匠鋪那條線（`feature/smithing-flow`）11/03 已合進 develop，在錨點 `split-anchor-20261104` 裡，照現行程式量。`/api/smith_line` 搬進包的 `routes.py`（照商城的做法）；`smith:` 前綴；搬 `bot_policy` 的 `smith:` 那一段。",
            "- 鐵匠鋪是店面：店面登記（`Shop`，第 11 批開的宣告）與「此地還能做」的入口位置照現在的（FEATURES 裡 `bout` 的店面接在酒肆後面，這一包的店面先後量出來、寫進計畫第一節；接不上的留 Game 一行委派、邊界測試寫理由）。神器定名是三段式（模型呼叫不在鎖裡），寫法照舊；假人打出神器原品一律沿用譜名（CLAUDE.md 寫的已知破綻）照舊，不改。",
            "- `web/` 不准碰（鐵匠鋪的畫面不搬），所以沒有實機驗收：自己那一軌 `/api/smith_line` 與每一個 `smith:` 動作都要打到、看回應內容。",
            "- Task 1 的情境：買、修、淬煉、一步一步打造（每一步都按）與直接開爐、隱藏配方、神器定名（三段式的 A／C 段，模型擋掉時走保底名）、以器配招、收購升階、看火候；三種設定；半舊半新切在打造到一半、神器定名的單開著；假人碰得到 `smith:`。",
        ]),
    "47": dict(
        title="移動一——移動選單（步行、疾行）、路上三樣小事、喊停、折返、`/api/travel`（新包 `travel`）",
        pkg="travel", feature="feature/travel", dev="dev/travel-1", host="travel1",
        plan="docs/superpowers/plans/2026-11-06-移動包-第1批.md",
        ports={"dev": 8186, "rev": 8187, "fix": 8187, "head": 8188, "base": 8189}, fb="FB-9510～FB-9519",
        body=[
            "- 範圍照總表 3.3 第 47 列（19 個方法、208 行）與第二節「移動（`travel`）」。**不等輿圖那條線**（`feature/map-view` 擱著，拆完才追進主幹；交接第三節），照現行程式搬。`move:`、`road:` 前綴；搬 `bot_policy` 的 `move:` 那一段；`/api/travel` 搬進包的 `routes.py`。結伴同行、前往是第 48 批（移動二），不搬。",
            "- 移動是每一步都會碰的：`_arrivals`、`sync` 裡抵達、路上小事、喊停的位置一個都不動（順序就是行為）；接不上掛鉤的留 Game 一行委派、邊界測試寫理由。舊的「趕路」（CLAUDE.md：拿掉之前出發、還在路上的那一趟照原本的步調走完，`atlas.MODE_NAMES`、`TIME_SHARE`、`TravelMode` 還認得它）照舊認得。",
            "- **抵達是事件 `arrive` 的發布點**（第 26 批）：`Game._arrive` 那一行 `self.publish(\"arrive\", loc_id)`（軍情包交糧車→懸賞護送，先後由 `BUS_ORDER` 鎖住；`_convoy_arrives` 委派已拿掉）。`_arrive` 搬進包的話發布點跟著搬、改成 `ctx.publish`、留在原本那個位置；不搬就留 Game。自己的比對要連 `herald` 一軌（溫若谷重新登入那一下同步抵達：「糧車送進了」接著護送交差）一起比，三種設定、整段與半舊半新都一樣。",
            "- `web/` 不准碰，所以沒有實機驗收：自己那一軌 `/api/travel` 與每一個 `move:`、`road:` 動作都要打到、看回應內容。",
            "- Task 1 的情境：步行、疾行、路上三樣小事各一、喊停、折返、抵達（含有人設伏的地點）、舊的趕路還在路上；三種設定；半舊半新切在路上（出發了還沒到、路上小事出現了還沒選）；假人碰得到 `move:`。",
        ]),
    "49": dict(
        title="輿圖一——天下圖、區圖、小地圖、地點詳情、疊層；`mapview`、`mapart`、`mapdata`、`worldgeo`、`map.js` 進新包 `map`；`/api/map` 三條路由",
        pkg="map", feature="feature/map", dev="dev/map-1", host="map1", web=True,
        plan="docs/superpowers/plans/2026-11-06-輿圖包-第1批.md",
        ports={"dev": 8190, "rev": 8191, "fix": 8191, "head": 8192, "base": 8193}, fb="FB-9520～FB-9529",
        body=[
            "- 範圍照總表 3.3 第 49 列（11 個方法、82 行，加 `mapview` 802、`mapart` 545、`mapdata` 677、`worldgeo` 320 與 `atlas` 的圖層那一半）與第二節「輿圖（`map`）」、附錄丙裁給這一包的網頁宣告。**不等輿圖那條線**（`feature/map-view` 的 W2～W4 擱著，拆完才照新位置追進主幹；交接第三節），照現行程式搬；計畫第一節列出 `feature/map-view` 動到的檔，之後追的人照這張表改位置。`/api/map` 三條路由搬進包的 `routes.py`。",
            "- **這一批例外，會動 `web/`**：`web/map.js`（與附錄丙裁給輿圖的宣告）搬到包裡、殼照包的登記把它送出去，網頁拿到的內容一個位元組不變；其餘 `web/` 照舊不准碰。動到 `web/`，所以有實機驗收（375 淺、375 深、1280 並排截圖逐像素比，`split-batch.js` 的 Check 那一段）。",
            "- `atlas` 拆兩半：圖層那一半進包，地點與路的資料（移動、地盤、設伏都在讀的）留在原處；拆的線照附錄甲。",
            "- Task 1 的情境：天下圖、各區圖、小地圖、地點詳情、每一種疊層開關；三種設定；`/api/map` 三條路由與 `map.js` 的內容（整檔 sha256）都要打到；半舊半新切在地圖畫到一半沒有意義的話寫明（沒有寫到一半的狀態）；假人不看地圖就寫明。",
        ]),
    "29b": dict(
        title="列傳二（第 29 批之二）——`annals` 拆兩半：記一筆行狀的那一半收進核心，查詢與行狀頁那一半進列傳包 `zhuan`",
        pkg="zhuan", feature="feature/zhuan", dev="dev/zhuan-2", host="zhuan2",
        plan="docs/superpowers/plans/2026-11-06-列傳包-第29批之二.md",
        prev_plan="docs/superpowers/plans/2026-11-04-列傳包-第1批.md",
        ports={"dev": 8194, "rev": 8195, "fix": 8195, "head": 8196, "base": 8197}, fb="FB-9530～FB-9539",
        body=[
            "- **這是第 29 批之二，不是第 29 批**：第 29 批（列傳包）11/05 已合；這一批做它沒做的總表附錄甲「`annals` 拆兩半」（總表第 29 列末句、附錄甲第 522 行那一列，第 29 批計畫第 168 行的說明）。",
            "- 拆法：**記一筆行狀的那一半**（各包打完、做完時記一筆用的函式與常數，例：`DUEL`、`ERRAND`、`GROUPS`、`MARK`、`STANCE`、`TIER`、`XINGSHI`，與寫進 `PlayerState.annals`／`annals_mark` 的函式）收進核心本體（`tianxia/core/` 新檔，照第 34 批 `omen_base`、第 37 批 `presence` 的前例）；**查詢與行狀頁的那一半**（`standing()` 這一類，`/api/annals` 已在列傳包的 `routes.py`）搬進列傳包。舊名 `tianxia/annals.py` 留別名，兩半都 re-export。`PlayerState.annals`、`annals_mark`、`xingshi_seen` 照舊是核心欄位、不認領。",
            "- **先量**：現在「包 → `tianxia.annals`」的過渡處（約 16～17 處，`git grep -n annals -- tianxia/features` 看行尾「過渡」）、`SHARED_LATER[\"fusion\"]`、companions 與 story 兩包 README 提到的。拆完這些過渡處改 import 核心那一半，拿掉過渡標記，處數寫進計畫第五節。換季與同步的位置（`_stance_annals`、`_zhuan_tick`、`_zhuan_past` 的先後）一個都不動。",
            "- Task 1 的情境：沿用 `zhuan` 一軌，再補「各包記一筆行狀」：打贏、做完差事、立場、決戰、單挑、〈天下形勢〉各一，看 `/api/annals` 的內容；三種設定；半舊半新切在記了一半（有 mark 還沒寫成行狀）；假人照常。",
        ]),
    "36": dict(
        title="「你這一步」與本週卡殼化（核心批）——為 `weekcard`、`step` 開「你這一步」掛鉤，各包交自己那一件；讀伏筆改查詢服務",
        pkg="core_step", feature="feature/core-step", dev="dev/core-step-1", host="corestep1",
        plan="docs/superpowers/plans/2026-11-06-你這一步-第36批.md",
        prev_plan="docs/superpowers/plans/2026-11-06-事件機制-第26批.md",
        ports={"dev": 8198, "rev": 8199, "fix": 8199, "head": 8200, "base": 8201}, fb="FB-9540～FB-9549",
        reviewers=3, dev_model=None, all_tracks=True,
        parallel="**核心批單獨跑**（總表 5.2 第 3 條）：這段期間沒有別的拆包批在開發。第 35、41、47、49、29b 這一波都已合；PM 開 `feature/core-step` 在 split/trunk 這一筆",
        body=[
            "- **這一批是核心批，沒有新包**：範圍照總表 3.3 第 36 列整格（含「接第 34 批 PM 認定第 1 條」）。下面 Task 2～4 寫「搬進 `tianxia/features/<包>/`」的地方換成：**Task 2** 在 `tianxia/core/features.py` 開「你這一步」掛鉤（寫法照第 11 批接縫掛鉤、第 25 批世界層、第 32 批效果、第 26 批事件：位置固定、不看包的 `enabled`、照 `registered()` 問）；**Task 3** 把 `weekcard`、`step` 直接叫各包、讀各包欄位的地方改成叫掛鉤，各包在自己的檔裡交自己那一件；**Task 4** 契約測試與邊界測試。`step`、`weekcard` 兩個舊模組改完之後歸核心本體（`MODULES`）還是共用規則層（`registry.SHARED`），量了在計畫第一節寫理由、交 PM 定。",
            "- **順序就是行為**：總表寫的先後是 託付 → 軍令 → 懸賞 → 伏筆 → 新手 → 投靠；**先照現行程式量**（同一張卡上幾件同時有的時候誰在前、只挑一件時挑誰），跟總表對不上以程式為準、計畫第一節寫明。順序寫死在核心（一張明確的順序表，連還沒成包、先掛在舊模組上的那幾格一起列），契約測試逐字鎖住。",
            "- **主人**：託付＝大勢人物包 `figure_acts`、軍令與伏筆＝軍情包 `military`、懸賞＝還是舊模組 `bounties`（第 45 批搬，那一格先掛在舊模組上、行尾標「# 過渡：待搬（第 45 批）」）、新手＝引導包 `guide`、投靠＝陣營包 `faction`。照現行程式量，主人不同就照實寫。",
            "- **接第 34 批 PM 認定第 1 條**：`step`、`weekcard` 讀伏筆（`next_trip`、`next_step`）現在經舊名別名 `tianxia.foreshadow`，改成軍情包的查詢服務（經 `ctx` 或核心查詢服務，照第 34 批 `omen_base` 的前例）。`events`、`narration`、`rumor_view`、`server.py` 那幾處是第 40 批，這一批不碰。",
            "- Task 1 的情境：**所有軌**都要跑（核心批）。這一批特別要走到的：六種各自是「你這一步」的那一刻、兩件以上同時有（看先後）、一件都沒有；本週卡（`weekcard`）每一格；week7、season21、test 三種設定；半舊半新切在某一件剛出現還沒做；假人照常。現有的軌已經走到的就不另加，計畫第一節列出哪一軌走到哪一件。`tests/core/test_test_for.py` 第 49 批拿 `step` 當「仍是舊模組」的例子，這一批若把 `step` 收進核心或共用層，照共用那一段的規矩換例子。",
            "- **不改的**：資料庫結構（develop 第 9 版）；`web/`；懸賞榜、玉璽、截殺三個模組本身。",
        ]),
    "40": dict(
        title="世界模型第二批（核心批）——六個舊模組收進共用規則層、`yuedan.tick` 走世界一步、條件與敘事讀別包欄位改查詢服務、鐵匠鋪五個純函式進核心",
        pkg="core_world2", feature="feature/core-world2", dev="dev/core-world2-1", host="coreworld2",
        plan="docs/superpowers/plans/2026-11-06-世界模型二-第40批.md",
        prev_plan="docs/superpowers/plans/2026-11-05-世界層掛鉤-第25批.md",
        ports={"dev": 8203, "rev": 8204, "fix": 8204, "head": 8205, "base": 8206}, fb="FB-9550～FB-9559",
        reviewers=3, dev_model=None, all_tracks=True,
        parallel="**核心批單獨跑**（總表 5.2 第 3 條）：這段期間沒有別的拆包批在開發。第 36 批（你這一步）已合；PM 開 `feature/core-world2` 在 split/trunk 這一筆（`feature/core-world` 是第 25 批用過的名字，不要碰）",
        body=[
            "- **這一批是核心批，沒有新包**：範圍照總表 3.3 第 40 列**整格**（含接第 32 批第 6 條、第 34 批第 1、6、9 條、第 35 批第 5 條、第 41 批第 4 條的那幾句）。下面 Task 2～4 寫「搬進 `tianxia/features/<包>/`」的地方換成：**Task 2** 核心那一側（共用規則層登記、查詢服務、核心小模組、世界一步那一格）；**Task 3** 改各處的讀法；**Task 4** 契約測試與邊界測試。",
            "- **六個舊模組收進共用規則層**：`figures`、`figure_life`、`plans`、`orders`、`ranks`、`chapters`（`registry.SHARED`），切掉它們往包與往還沒成包的舊模組的 import（總表量是 15 條，開工重量）。共用層的模組不准 import 包：讀包的欄位或叫包的，改查詢服務或掛鉤；改不了的標「# 過渡：待搬（第 N 批）」、計畫第五節寫理由。`SHARED_PENDING` 照改完的實際情況改。",
            "- **`yuedan.tick` 這幾個改走第 25 批的世界一步掛鉤**：主人在包裡登記那一格，`WORLD_ORDER` 的位置**照現在的呼叫先後**（同一步裡先推誰後推誰、亂數抽到的順序都算），契約測試鎖住。",
            "- **條件與敘事改查詢服務**：`rules.check_condition` 的 `story_marks`、`story_marks_max` 讀一條線包的 `storylines`、`clue_items` 讀軍情包的欄位，改成各包的查詢服務；`events`、`narration`、`rumor_view`、`server.py` 經舊名別名 `tianxia.foreshadow`、`opportunities` 讀的（`active`、`event_ids`、`heard_texts`、`heard_clues`、`held_items`）一樣改。軍情包的過渡處（`fs_rules`、`opp_rules` → `figures`，`opp_rules` → `ranks`）收完之後消掉。",
            "- **鐵匠鋪五個純函式進核心小模組**（第 41 批認定第 4 條）：`GO_VERB`、`is_forge_step`、`is_step_line`、`draft_here`、`draft_stale` 抽到 `tianxia/core/` 新檔（照 `omen_base`、`annal_base`、`convoy_base`），鐵匠鋪包照舊 re-export 同一個物件；`engine` 的 `choose` 後半、`_drop_stale_references`、`sync` 三處改讀核心，邊界測試那三筆 `GAME_DIRECT` 還原。量了若不合適，回報 PM。",
            "- **接第 36 批**（11/06 合）：`step`、`weekcard` 已是核心 `MODULES`，讀伏筆已收成軍情包登記的 `STEP_ORDER` foreshadow 那一格，第 40 列讀伏筆、機緣的名單裡不再有它們。`chapters` 收進共用層時：`weekcard.py` 那一行「# 過渡：待搬（第 40 批…）」拿掉；章回那一件（永遠排第一、不跟著「換一件事」輪）要不要也成 `STEP_ORDER` 一格，量了在計畫第一節寫、交 PM 定（第 36 批認定第 5 條）。**邊界測試**管「核心叫委派」的那一條現在只掃 `tianxia/core/*.py` 裡的 `ctx.`：擴到 `MODULES` 裡放在 `tianxia/` 頂層的模組（`world`、`weekcard`、`step`），`game.<委派>` 照 `ctx.` 一樣算，掃到的現有處（`weekcard` 的 `_opening_pending`、`sides_card`、`tier_hint`，`world` 有的照實）記成過渡、寫明哪一批收（第 36 批認定第 6 條）。",
            "- **`defected`、`ledgers`、`lean_changed` 的歸屬**（第 35 批認定第 5 條）：`wins.set_lean` 在共用層寫、`_clear_own` 清、`battle_instance`、狀態列、引導包都讀；收共用層時一起量，計畫第一節寫誰認領、交 PM 定。",
            "- Task 1 的情境：**所有軌**都要跑（核心批）。這一批特別要走到的：世界一步跨過每天與每週、`yuedan.tick` 那幾個真的動到的那一下；事件條件帶 `story_marks`、`story_marks_max`、`clue_items`（成立與不成立各一）；敘事與傳聞讀到伏筆、機緣的那一下；鐵匠鋪打造併成一則、讀檔清失效的單子、`sync` 收單子；week7、season21、test 三種設定；半舊半新切在世界一步推到一半；假人照常。現有的軌已經走到的就不另加，計畫第一節列出哪一軌走到哪一項。",
            "- **不改的**：資料庫結構（develop 第 9 版）；`web/`；`world_state.py` 的時間讀法。",
        ]),
    "38": dict(
        title="玩家互動二——切磋、論武（三段式首創取名）、截殺（含策馬脫身）、假人答切磋答論武與截殺（`spar`、`discuss`、`raid` 進 `peers`）；拿掉切磋論武的 7 筆 `GAME_DIRECT` 與 engine 對 `invites`、`social` 的過渡 import",
        pkg="peers", feature="feature/peers", dev="dev/peers-2", host="peers2",
        plan="docs/superpowers/plans/2026-11-07-玩家互動包-第2批.md",
        prev_plan="docs/superpowers/plans/2026-11-06-玩家互動包-第1批.md",
        ports={"dev": 8208, "rev": 8209, "fix": 8209, "head": 8210, "base": 8211}, fb="FB-9560～FB-9569",
        parallel="**第二波三條同時跑**：第 38（玩家互動二）、42（裝備）、48（移動二）批都從 split/trunk 這一筆開（核心第 36、40 批已合）。三批會在 `engine.py`、`core/services.py`、邊界測試、`same_behavior.py` 檔尾、`bot_policy.py` 頂端與常數段、`server.py` 的 `/api/peer` 一帶撞，各寫各的段，合併時 PM 照先後接。下面寫的行號是 11/06 在 `96231255` 量的，開工那一筆重量",
        body=[
            "- **範圍**照總表 3.3 第 38 列整格：28 個方法、435 行（切磋 8、論武 11、截殺 9，`engine.py` 約 5126～5679），加上第二節「玩家互動（`peers`）」的 `spar`、`discuss`、`raid` 三個模組（舊名留 `sys.modules` 別名）。包沿用第 37 批的 `peers`，不開新包、不加前綴：三樣都是玩家卡的動作，走 `/api/peer/act`，路由第 37 批已經在包的 `routes.py`。中間夾著不搬的：第 37 批的委派；移動包的 `_join`、`join_refusal`（第 48 批同時在搬）；核心的 `_spar_power`、`_spar_mirror`、`_raid_key`；懸賞榜的 `post_wanted`、`_raid_bounty`（第 45 批）。",
            "- **接第 37 批 PM 認定第 7 條**：`GAME_DIRECT` 的切磋、論武 7 個（`_spar_answer_problem`、`spar_invite`、`spar_refusal`、`_discuss`、`discuss_invite`、`discuss_invite_problem`、`discuss_refusal`）和 `engine.py` 對 `invites`、`social` 的兩行過渡 import 一起拿掉；邊界測試的 `_PEERS_PENDING`（7 筆）、`_PEERS_38`（`GAME_DELEGATE_CALLERS` 6 筆）、`GAME_IMPORTS` 的 `invites`、`social` 一起收。**第 8 條**：三個模組的玩家卡登記從 `engine.py` 頂端的 `as _x  # noqa: F401` 搬到包 `__init__.py`，照 `mingtie_card` 的寫法（`scripts/test_for.py` 的 `registered_actions` 才認得）；通緝那一行留在 engine（第 45 批）。**第 3 條**：照舊登記進 `peers/social.py` 的 `ACTIONS`；卡上照 `(order, id)` 排，計畫第一節量一次登記先後不影響。",
            "- **服務清單**（`core/services.py`）：三、過渡 `# peers` 的 `ctx._spar`、`ctx._discuss`、`ctx.discuss_invite_problem`、`ctx.discuss_item_problem` 搬進包之後改包內直接叫、拿掉那幾條（同一條裡的 `_join`、`join_refusal` 是第 48 批的，不動）。二、查詢服務 `# peers` 反方向那幾個（`_peer`、`_tell_sender`、`_pair_*`、`_spar_pair`、`answer_invite`、`peer_act`）重量誰還在叫：沒人叫的委派拿掉，還有人叫的留著。四、寄放 `ctx.peer_brief`：現在讀它的是包的 `routes.py`、清它的是包的 `actions.py`，`server.py` 不讀；論武進了 `peers`，只照實改說明。`RaidSpoils` 從 `core/services.py` 拿（第 39 批認定第 2 條）。",
            "- **截殺讀懸賞（PM 認定）**：截殺打贏的交差照舊叫 `ctx._raid_bounty`，那是事件 `raid_win` 的發布點、位置不動（第 26 批認定第 7 條）。截殺另外直接讀 `bounties` 的三處（`raid_shown` 的 `hunting`、`raid` 的 `official_hit`、`_raid_record` 的 `BEATEN_OFFICIAL`）**留過渡 import**，行尾標「# 過渡：待搬（第 45 批）」：`bounties` 還是舊模組，包 → 舊模組照標過渡；第 37 批認定第 2 條管的是包對包。第 45 批成包時改成懸賞榜的查詢服務（第 26 批計畫已經排給它）。",
            "- **論武的三段式**照手冊 G10：A 段 `discuss_request`、C 段 `_discuss` 搬進包。殼的接線 `server.prepare_peer`、`screen_peer` **照 G10 留在 `server.py`**、經 `shell.` 叫，只改說明字（`routes.py`、`server.py` 註解與第 37 批計畫寫的「第 38 批」改成照實）；`tests/server/test_server.py::test_only_the_out_of_lock_steps_enter_the_model_queue` 的名單不動。`_discuss_forge` 只要往下開爐就在鎖裡叫 `ctx._quick_client()`（答應的一方一次、對方那份 `Game` 再一次），會不會真的叫模型由 `fusion.merge` 決定：照舊。",
            "- **假人（PM 認定）**：`bot_policy` 的 `_answer_invite`（切磋）、`_answer_discuss`、`_raid` 與常數 `INVITE_YES`、`RAID_CHANCE`、`RAID_ODDS` 搬進包的 `bots.py`；`RAID_ODDS` 現在是 `bot_policy` 自己的 `CHALLENGE_ODDS`（`score` 還在用），包裡照 `SMITH_SCORE` 的前例重寫一份同值常數、`bot_policy` 的名字照舊；包要 import `bot` 的，行尾標過渡（第 41 批認定第 11 條）。**`DiscussJob` 照鐵匠鋪 `ForgeJob` 的前例留在 `bot_policy`**，跟 `ForgeJob`、`MasterJob`、`SenseJob`、`EpiphanyJob` 放一起；包不 import `bot_policy`：`_answer_discuss` 回需要的資料、由 `bot_policy` 包成單子，接不起來就讓 `_answer_discuss` 留在 `bot_policy`、計畫寫理由。`bot_policy` 留 `from .features.peers.bots import …  # noqa: F401` 舊名給測試讀；`take_turn` 的呼叫順序一個字不動；沒有新前綴，`bot.py` 的 `pick()` 不動。`tests/ranger/test_raid.py` 的 `monkeypatch.setattr(bot_policy, \"RAID_CHANCE\", 1.0)` 改成 patch 包的 `bots`（只改叫法，第 47 批認定第 8 條）。",
            "- **patch 會打不到的地方**（第 37 批認定第 9 條，照 grep 整個 `tests/`、各包 `tests/`、`scripts/` 為準）：`scripts/sim_season_one.py`、`sim_server_bots.py` 用 `mock.patch.object(Game, \"_raid_record\"／\"_raid_spoils\"／\"_raid_fled\")` 數截殺，`tests/gear/test_mounts.py` 換 `Game.raid_flee_odds`，`tests/ranger/test_bounties.py`、`tests/seal/test_seal_revamp_hidden.py` 換 `Game._spar_power`：這幾個留 `Game` 一行委派、包裡一律經 `ctx.` 叫（照 `ctx._duel_finish`）。`test_raid.py` 換 `encounter.resolve_encounter`、`test_discuss.py` 換 `naming.generate`、`social.day_turn`、`OllamaClient.from_config`：搬過去的程式照舊經模組屬性叫，不准 `from … import` 名字。外面還在叫的 Game 方法（`raid_shown`、`raid_refusal`、`raid_odds`、`raid_targets`、`raid`、`discuss_items`、`_discuss_cost`、`discuss_item_problem` 等，量出來的為準）留委派。",
            "- **測試與文件**：`tests/battle/test_spar.py`、`tests/ranger/test_raid.py` 整檔搬進 `tianxia/features/peers/tests/`，只改路徑字串。**`tests/arts/test_discuss.py` 不搬**：`test_social`、`test_server` 用裸名從它拿 helper，它自己又有網頁測試，照第 41 批認定第 6 條留在 `tests/`、歸第 61 批。**`tests/core/test_social.py` 不搬（PM 認定）**：第 37 批認定第 6 條寫「第 38 批搬結伴時再看」，可是結伴同行是第 48 批；那 27 條裡真的是結伴的只有 3 條，第 48 批也不拆，整檔歸第 61 批。寫死舊路徑的照實改：`sortie`、`stamina_plays` 兩包 README、`engine.py` 那一行「過渡：tests/ranger/test_raid.py 從 engine 拿」的註解、邊界測試的註解、調查檔 `area_action.json`、`area_combat.json`；`.claude/skills/tianxia-dev/SKILL.md` 寫的 `tests/ranger/test_raid.py::_do` 回報 PM（技能檔只有 PM 改）。包 README 補切磋、論武、截殺，`WorldState` 的 `spar_tally`、`discuss_tally`、`raids`、`raided` 記「資料在核心、不認領」。導覽〈散人與玩家互動〉三條各補一行程式的位置，不改規則文字。",
            "- **共用登記檔**：拿掉第 37 批 `# peers` 段裡的格，一律在自己新開的段用 `del`／`discard`（第 46 批認定第 3 條；那一段的 `(\"_join\", \"_tell_sender\")`、`(\"join_refusal\", \"_peer\")` 歸第 48 批）。`aliases()` 加 `spar`、`discuss`、`raid` → `peers`。`same_behavior.py` 新的軌整塊接在檔尾。",
            "- **Task 1 的情境**：新開一軌（原創名字，接在檔尾；要擴 `peers` 軌就在計畫第一節寫理由）。切磋：發邀請、答應、婉拒、收回、對方不在作廢、同一對一天滿了、體力不夠、打完的戰報與經驗、大勝與平手。論武：出得了的意境、帶一樣發邀請、答應時挑一樣；三段式走 A 段開單 → B 段模型擋掉走 `NO_NAME` → C 段帶 `proposed`；首創與配方已有、心得或體力不夠、已經有了、`peer_brief` 那一句。截殺：敵對陣營、散人揭通緝、城鎮擋、新手期、體力不夠與在忙、同一對冷卻、被截過的護身、混戰過的拒絕話（FB-607）、策馬脫身、打贏打輸平手的銀兩氣血與官府通緝的惡名、對方下線但還在窗口內、休季與 `Config.raid.enabled` 關著不畫。`/api/peer` 與 `/api/peer/act` 三種動作每一顆都打到、看回應內容。第 37 批認定第 12 條的切磋、論武那一半也走到（邀請收回、對方不在收回、選單上 discuss／spar 的邀請與收回、`tell_sender` 對方為 None）；**結伴（travel 邀請答應走到 `_join`）那一半交第 48 批的軌**。",
            "- **Task 1 照第 37 批的教訓**（第 37 批計畫 5.2 第 1～3 條）：每一步清 `server.BOARDS_CACHE`（前半、後半在不同行程，名帖頭銜的名次會不同）；`presence_seconds` 拉長、`invite_ttl_seconds` 拉到 36000，不然前半送出的邀請到後半都作廢；邀請編號是雜湊，選單上的 id 從 `world.invites` 讀出來拼。截殺的冷卻與護身要跨過切點。三種設定 season21、week7、test（test 內容沒有陣營、第一季開關關著，三顆鈕畫不出來，寫明走不到）。半舊半新切在：切磋與論武的邀請送出還沒接受、截殺過後冷卻與護身還沒過、同一對這一天的次數用了一半。假人：BotRunner 答切磋、答論武（模型擋掉時那一輪不答）、截殺，加上整季機器人；任何畫面都不透露誰是假人。",
            "- **比對哪幾軌（PM 認定，不跑全部的軌）**：新的那一軌、`peers`、`herald`、`bout`、`figact`，加上第 26 批量過截殺打贏真的走到的 `companions`、`events`、`socialize`、`strip`、`talk`、`bots-train`（第 26 批計畫 1.8 的表）；三種設定，整段、半舊半新、假人都比。假人每一輪都會叫到這一批搬的 `_answer_*`、`_raid`，其餘的軌由主幹每天的全面檢查全比。",
            "- **不改的**：資料庫結構（develop 第 9 版）；`web/`（手冊 G9，玩家卡的鈕在第 3 階）；`wanted.py`、`post_wanted`、`_raid_bounty`（第 45 批）；`_spar_power`、`_spar_mirror`、`_raid_key`（核心）；`_join`、`join_refusal` 與結伴（第 48 批）；`Config.raid` 留在 `models.py`；任何玩家看得到的字。",
        ]),
    "42": dict(
        title="裝備——換上、拆解（含批量）、餵馬、馬市、寄放補送、名將贈禮、本命兵器、神器譜（`signature_arms` 進新包 `gear`；搬 `bot_policy` 的 `market:`）",
        pkg="gear", feature="feature/gear", dev="dev/gear-1", host="gear1",
        plan="docs/superpowers/plans/2026-11-07-裝備包-第1批.md",
        prev_plan="docs/superpowers/plans/2026-11-06-鐵匠鋪包-第1批.md",
        ports={"dev": 8213, "rev": 8214, "fix": 8214, "head": 8215, "base": 8216}, fb="FB-9570～FB-9579",
        parallel="**第二波三條同時跑**：第 38（玩家互動二）、42（裝備）、48（移動二）批都從 split/trunk 這一筆開（核心第 36、40 批已合）。三批會在 `engine.py`、`core/registry.py`、`core/services.py`、邊界測試、`same_behavior.py` 檔尾、`bot_policy.py` 頂端與常數段撞，各寫各的段，合併時 PM 照先後接。下面寫的行號是 11/06 量的，開工那一筆重量",
        body=[
            "- **範圍**照總表 3.3 第 42 列（13 個方法、128 行，含附錄甲挑錯改裁給裝備的 `_people_here`）與第二節「裝備（`gear`）」：`tianxia/signature_arms.py` 進新包 `gear`，舊名留 `sys.modules` 別名。13 個是 `_market_options`、`_market`、`wield_weapon`、`feed_mount`、`dismantle_weapon`、`dismantle_many`、`_deliver_held_gear`、`_general_gifts`、`_people_here`、`_gift_entry`、`_signature_arms`、`gear_rows`、`divine_book_view`。包名 `gear` 跟測試資料夾 `tests/gear/`、內容欄位 `Content.gear` 同字，README 寫一句分別。前綴 `market:`；`act:market` 接 `Verb`；搬 `bot_policy.score` 的 `market:` 那一段。路由 0 條：`/api/menxia` 的四個動作、`/api/boards` 的神器譜、`/api/board_card` 的裝備卡都留在殼、叫委派。",
            "- **誰在叫**（幾乎每一個都留一行委派，計畫第一節照實量）：殼的 `MENXIA_ACTIONS`、`menxia_view`、`/api/boards`；假人 `bot.feed_mount`、`bot.wear_better`；核心原位 `_everyday_options` 叫 `_market_options`（邊界測試記 `(\"_everyday_options\", \"_market_options\")`，同鐵匠鋪的 `_smith_options`）、`sync` 與 `advance`（在 `_deliver_big_events` 之後）叫 `_deliver_held_gear`（不接 `on_sync`，位置不動）、`choose` 後半與 `core/event_check.py` 的 `answer_event`、`answer_branch` 叫 `_general_gifts`、`_signature_arms`、`_gift_entry`；大勢人物包經 `ctx._signature_arms`；測試直接叫 `_market`、`_people_here`。`dismantle_many` 的裝飾器用核心的 `not_while_preparing`。記行狀一律 `from tianxia.core import annal_base as annals`。",
            "- **`market:` 照鐵匠鋪 `smith:` 的前例（PM 認定）**：`choose` 的 `market` 那一支改接 `choose` 掛鉤（`Outcome(title=mounts.MARKET, …)`），`_action_title` 的 `market` 那一支跟著拿掉；`act:market` 接 `Verb`（照舊寫江湖紀錄、不宣告 `picks`）。**不登記 `Shop`**（第 41 批認定第 1 條：第 42、45 批比較晚合的那一批三間一起排；照排程是第 45 批）：選單（`picking_market`）、入口、`_shop_open`、`shop_view` 的 market 那一支、收店（`_drop_stale_references`、`sync`、`_depart`）、`_idle`、`choose` 裡 FB-195 被搶的那一句（`mounts.stale_problem`）全留 `Game` 原位，邊界測試寫理由。`_depart` 裡的 `mounts.close_market` 第 48 批會跟著 `_depart` 搬進移動包（`mounts` 是共用層，直接 import）。",
            "- **第 31 批留的過渡**：`core/services.py` 三、過渡 `# figure_acts` 那一條 `ctx._signature_arms(...)` 改列二、查詢服務 `# gear`；大勢人物包 `challenge.py` 照舊經 `ctx` 叫，打贏本人第三次寫進那一場戰報的「得失」、行狀照 `later` 的先後。**邊界測試預留的六對**：`CORE_DELEGATE_CALLERS` 註解裡 `answer_event`、`answer_branch` 各配 `_general_gifts`、`_signature_arms`、`_gift_entry`，照第 22、33 批的寫法取消註解、寫理由（事件檢定是核心本體、位置固定），不准拿掉守門。",
            "- **`_drop_stale_references` 的 `signature_arms.refresh_names`（PM 認定）**：它排在 `treasures`、`forge_secrets` 的 `refresh_names` 後面、`_copy_heirloom` 前面，會改 `item.name`、要讀 `owned`，不是只讀的純函式。**留原位經舊名別名讀**：`GAME_IMPORTS` 加 `tianxia.signature_arms`、`GAME_DIRECT` 的 `_drop_stale_references` 寫理由「清失效參照的先後就是行為」、由**第 55 批**（補算與換季收接縫）收；不接 `on_drop_stale`（會挪到最後）。`leaderboard.gear_card`（函式裡 import `signature_arms`）經舊名別名讀，`SHARED_LATER[\"leaderboard\"]` 與 `tianxia/world.py` 那一行註解只改字。",
            "- **內容與欄位（PM 認定）**：`content/gear.json` 照分區調查（`area_growth.json`）由裝備包認領（`GearFeature.content = (\"gear.json\",)`）；`content.py` 的 `check_gear`、`check_signature_arms` 留在 `content.py`、不接 `check_content`（第 34 批認定第 2 條：會動第一個錯誤的先後），README 照實記誰在讀（共用層 `treasures`、`tactics`、`SHARED_LATER` 的 `leaderboard`，核心 `team`、`naming`、`content`；`mounts` 不讀）。`picking_market` 認領；`held_gear` 核心與共用層都讀，不認領；`figure_wins` 已是大勢人物包的。`Game._affinity_before`（`choose` 與核心 `event_check` 寫、`_people_here` 讀的暫時旗標）列進 `core/services.py` 四、寄放 `# gear`，屬性留在 `Game.__init__`（照鐵匠鋪 `smith_result`）。`GearFeature.enabled` 照第 41 批認定第 3 條：四欄各看自己的 `enabled`；坐在馬市裡照樣按得到離開。",
            "- **假人**：`bot_policy.score` 的 `kind == \"market\"` 兩行搬進包的 `bots.py`，`MARKET_SCORE` 在包裡重寫一份同值常數、`bot_policy` 的名字照舊；`act:market` 的分數是核心 `act` 前綴的，留在 `bot_policy`；`bot.py` 的 `market_want`、`visit_market`、`feed_mount`、`wear_better` 是共用底層，不搬。**量表照模組屬性換**：`scripts/measure_mounts.py` 換 `mounts.buy`、`mounts.feed`，`measure_treasures.py` 換 `treasures.gifts_due`、`treasures.deliver_held` 與 `Game.wield_weapon`，所以包裡一律寫 `mounts.xxx(...)`／`treasures.xxx(...)`、換上走 `ctx.wield_weapon`，腳本裡「engine 照模組屬性呼叫」的註解跟著改；`tests/season/test_sim_scripts.py` 那兩條 slow 列進 README「另外要跑的」、開發跑一次。",
            "- **測試**：真的搬進包的只有 `tests/gear/test_gear_where.py`。`test_shop2`、`test_treasures`、`test_signature_arms`、`tests/web/test_shop2_web.py` 被別的測試用裸名 import，照第 41 批認定第 6 條留原處、歸第 61 批；`test_horse_art`（import `server` 查 `web/`）、`test_shop_polish`（走網頁 harness）算網頁類，留原處（第 3 階）。混合檔不拆、README 記下：`test_mounts`、`test_weapons`、`test_armor`、`test_board_cards`、`test_forge_divine`、`test_shop`、`tests/bots/test_bot_policy.py`、`tests/core/test_shop_width.py`、`tests/server/test_server.py`（`/api/boards` 的神器譜）、`tests/seal/test_seal.py`（`dismantle_weapon`）、`tests/season/test_sim_scripts.py`。「馬市（第 42 批）還沒成包」的字照實改：邊界測試 `# smithy` 段頭與 `_SMITHY_SHOP` 的理由、鐵匠鋪 README；大勢人物包 README 寫 `signature_arms.py`、`tests/gear/test_signature_arms.py` 路徑的照實改（第 35 批認定第 12 條）。",
            "- **Task 1 的情境**：新開一軌（原創名字）。籌備中：只有 `dismantle_many` 擋（`@_not_while_preparing`），`wield`、`feed`、`dismantle` 照常做，照實記。馬市：`act:market` 進門、`market:buy` 買得起與買不起、已經有馬時新的進裝備庫、`market:feed` 不餓／沒素材／餵飽、`market:wield:<id>`、`market:back`、FB-195 兩個分頁搶、`/api/main` 的店面與馬販那一句。修練頁 `/api/menxia/{wield,dismantle,feed,dismantle_many}`：兵、甲、騎、寶四種 id，路上換坐騎被擋、閉關中換寶物、坐騎寶物不能拆、空 id（`wield`、`dismantle` 讀的是 `weapon` 鍵、`dismantle_many` 讀 `items`、`feed` 不讀鍵）。寄放：裝備庫滿時重賞或名將贈禮寄放，`sync` 與只 `advance` 都補送、閉關中也補。名將贈禮與本命兵器：情誼經 `choose` 的對話與 `answer_event`／`answer_branch` 兩條路到門檻；當面交給你與託人送來（`_people_here`）；每位名將每季全服一人；挑戰本人打贏 `signature_wins` 次奪走。看榜：`/api/boards` 的神器譜、`/api/board_card`。收季、開下一季。三種設定 season21、week7、test：test 內容四欄都關、沒有 `gear.json`，在記憶體裡打開、補一份做得到就補（兩份程式一樣），補不到的照第 41 批認定第 9 條寫明走不到、正式內容有走到。半舊半新切在：馬市開著剛買了一匹、寄放裡有東西等補送、情誼差一下到贈禮門檻、打贏本人兩次（第三次由新程式打）、坐騎餓了還沒餵。假人：BotRunner 兩個（一個坐在馬市、一個在門外）加整季機器人。",
            "- **比對哪幾軌**：新的那一軌，加上 `smithy`、`figact`、`talk`、`events`、`travel`，計畫第一節量出還有哪幾軌真的叫到（`_deliver_held_gear` 每次 `sync` 都跑：裝備庫滿的軌）；其餘由主幹每天的全面檢查全比。",
            "- `web/` 不准碰（手冊 G9；`app.js` 歸這一包的 `gearEffect`、`gearCell`、`horseImg`、`marketHtml`、`horseCard` 歸第 65 批），沒有實機驗收：自己那一軌把 `/api/menxia` 四個動作、每一個 `market:` 動作、`/api/boards`、`/api/board_card` 都打到、看回應內容。",
            "- **不改的**：資料庫結構（develop 第 9 版）；`web/`；`server.py` 的 `MENXIA_ACTIONS`、`/api/boards`、`/api/board_card`；共用規則層的 `treasures`、`mounts`、`equipment`、`weapons`、`armor`、`forge_secrets`；核心常數 `SHOP_ACTS`、`LEAVE_SHOP_IDS`；`atlas` 那一句「馬市還開著」。",
        ]),
    "48": dict(
        title="移動二——出發與抵達的補算、在路上那一行字、結伴同行路上那一半、`/api/party/leave`（接著進第 47 批開的 `travel` 包）",
        pkg="travel", feature="feature/travel", dev="dev/travel-2", host="travel2",
        plan="docs/superpowers/plans/2026-11-07-移動包-第2批.md",
        prev_plan="docs/superpowers/plans/2026-11-06-移動包-第1批.md",
        ports={"dev": 8218, "rev": 8219, "fix": 8219, "head": 8220, "base": 8221}, fb="FB-9580～FB-9589",
        parallel="**第二波三條同時跑**：第 38（玩家互動二）、42（裝備）、48（移動二）批都從 split/trunk 這一筆開（核心第 36、40 批已合）。三批會在 `engine.py`、`core/services.py`（`# peers` 那一條同時列著第 38 批的 `_spar`、`_discuss` 與這一批的 `_join`、`join_refusal`）、邊界測試的 `# peers` 段、`same_behavior.py`、`bot_policy.py` 頂端、`server.py` 的 `/api/peer` 一帶撞，各寫各的段，合併時 PM 照先後接。下面寫的行號是 11/06 量的，開工那一筆重量",
        body=[
            "- **範圍（PM 認定）**照總表 3.3 第 48 列，但 **`_real_minutes` 留在核心**（`core/services.py` 已寫主人核心，核心的 `place_minutes` 與輿圖包都叫它）：這一批 14 個方法、約 298 行（總表寫 15／307，差的是第 41、43 批改過 `_depart` 收店那幾行，照量到的認）。出發與抵達的補算 `_depart`、`_arrivals`、`_arrive`；在路上那一行字 `_journey_line`；結伴同行 `_join`、`join_refusal`、`_party_expires`、`_party`、`party_view`、`leave_party`、`_part_ways`、`_lead`、`_partners`、`_share_road`。路由 `POST /api/party/leave` 搬進包的 `routes.py`，**函式照舊叫 `api_party_leave`、照舊經 `shell._tell_tabs` 通知**（`tests/server/test_server.py` 的 `test_only_the_action_endpoints_tell_other_tabs` 照名字鎖這組端點、掃描含 `features/*/routes.py`）。接在第 47 批的 `tianxia/features/travel/`，沿用 `feature/travel`；沒有新前綴、沒有要搬的模組；不等輿圖那條線。",
            "- **位置就是行為，一個都不動**：`sync`、`advance` 叫 `_arrivals()`，`sync` 叫 `_party_expires()`，`status_data` 的 `journey`，殼 `_main_view_body` 的 `party`，`_everyday_options` 路上那串的 `act:part`，都留 `Game` 一行委派或原位。`_arrivals` 迴圈中途 `_ambush_check` → `_arrive` → `mounts.hunger` → `_road_sight` 照原樣搬；`mounts.hunger` 照舊經模組屬性叫（`scripts/measure_mounts.py` 換的就是它）；`_road_sight` 改直接叫 `road_actions.sight`、拿掉 `Game._road_sight` 委派。",
            "- **抵達是事件 `arrive` 的發布點**（第 26 批認定第 2、12 條；第 47 批認定第 7 條）：`_arrive` 搬進包，`self.publish(\"arrive\", loc_id)` 改 `ctx.publish`、留在原本的位置（地點描寫之後、新手引導之前），`BUS_ORDER` 不准改；`core/features.py` 事件表註解的發布點照實改。`_arrive` 裡兩處 `_guide(_note_action(...))` 經 `ctx._note_action` 叫、位置不動；邊界測試的 `(\"_arrive\", \"_note_action\")` 在自己的段 `del`（照第 35 批搬 `_faction_step` 的前例），不是留理由。**`Game._arrive` 留一行委派**（`tests/core/test_contract_core.py` 直接叫它鎖事件接法，核心契約測試不動）。自己的比對連 `herald` 一軌。",
            "- **`_depart` 收店那四行**（`bounties.close_board`、`equipment.close_smith`、`mounts.close_market`、`features_core.close_shops`）照原樣搬、先後不動；三間店排進 `Shop` 是第 45 批的事。`bounties` 行尾標「# 過渡：待搬（第 45 批）」；`atlas` 照舊是過渡（第 50 批）；`mounts`、`equipment`、`materials` 是共用規則層，直接 import。",
            "- **第 47 批交給這一批的（PM 認定）**：（一）`_road_gain`：`road_actions` 的 `think`／`ask`／`gather` 把收穫回傳給 `road()`、再當參數交 `_share_road(what, gain)`，包內函式簽名變、輸出不變；`Game.__init__` 不再留這個屬性，`services.py` 三、過渡那一條拿掉。（二）`ROAD_TASKS`、`ROAD_REWARD_TASKS` **留在核心**（`_drop_stale_references` 讀檔清舊還在讀），只把寄放的那一段整理到 `# travel` 一起、寫理由。（三）`bot_policy.py` 的 `travel_bots` 那一行 import 移出決戰那一串；`TravelFeature` 補宣告 `content = (\"road_sights.json\",)`。（四）`_road_reward_due`、`_count_road_reward` 兩個委派拿掉，`tests/figures/test_day_scale.py` 的 7 處改叫 `road_actions` 的函式（只改叫法，第 47 批認定第 8 條）。",
            "- **要留的委派**（呼叫端不在這一包，計畫第一節照實量）：`_depart`（人物帶路 `companions/parley_actions.py`；`measure_mounts.py` 與 `tests/figures/test_seats.py` 換掉它；`same_behavior` 的酒肆、擂台、銀兩出口三軌在鎖裡直接叫；bout 包接縫測試）——**包裡的 `go_actions`／`road_actions` 照舊經 `ctx._depart` 叫**；`_arrivals`（`sync`、`advance` 照舊叫 `self._arrivals()`；`test_seats.py` 換掉它；`stamina_plays` 包測試直接叫；包內在別人那份 `Game` 上叫 `other._arrivals()`）；`_arrive`、`_journey_line`、`_party_expires`、`party_view`（殼與 `test_social`）、`join_refusal`（玩家互動包 `bots.answer_call`）、`_join`（玩家互動包 `invite_actions` 經 `ctx._join`）。`_lead`、`_partners`、`_share_road`、`_party`、`_part_ways`、`leave_party` 呼叫端都在包內，原則上不留。這幾個檔列進 README「另外要跑的」：`test_seats`、bout 接縫測試、`stamina_plays` 包測試、`test_social`、`test_day_scale`。",
            "- **服務清單**：`ctx._join`、`ctx.join_refusal`（現在在三、過渡 `# peers` 那一條）主人成包了，從那一條拿掉、改列二、查詢服務 `# travel`、寫「主人成包了，改列這裡」（第 38 批同時在改同一條的另一半，合併時 PM 接）；`ctx._share_road`、`ctx._lead` 搬進包後拿掉；`ctx._sync_battle_presence` 的主人是決戰包 `muster`，不是移動，照實寫；`ctx._depart` 照前例改列二。包要叫的 Game 東西（`_sync_battle_presence`、`_ambush_check`、`_hide`、`_guide`、`_note_action`、`location_text`、`_flavor_sink`、`_kin`、`_load_kin`、`_save_kin`、`_peer`、`_tell_sender`、`_write`、`touched`）還沒列的補進 `# travel`。",
            "- **`act:part`（PM 認定）**照第 47 批 `act:halt` 的前例接 `Verb(\"part\", …)`，標題「分道揚鑣」取自 `_action_title` 那張表；`_act` 的 `if what == \"part\"` 拿掉；`_everyday_options` 裡 `Option(id=\"act:part\")` 的位置不動。合併時 PM 把總表第 57 列的子動詞數 28 改 27。",
            "- **欄位與邊界**：`PlayerState.tagalong` 進 `player_fields` 與 README；包外直接讀寫它的照第 34 批認定第 9 條記下、寫明哪一批收：`atlas.travel_block`（第 50 批）、`bot_policy.take_turn`（第 60 批）、mall 包測試直接寫它；`characters.py` 的 SQL（`CharacterStore.tagging`）是核心存檔的查詢，不動。`journey` 不認領。邊界測試在自己的 `# travel` 段 `del`（第 46 批認定第 3 條）：決戰段的 `(\"_arrivals\"/\"_depart\", \"_sync_battle_presence\")`、體力玩法段的 `(\"_arrivals\", \"_ambush_check\")`、`# peers` 段的 `(\"_join\", \"_tell_sender\")`、`(\"join_refusal\", \"_peer\")`、`(\"_arrive\", \"_note_action\")`，改登記包經 ctx 叫。寫死 `Game._depart`／`_arrive`／`_join`／`_lead` 的說明字照實改（軍情包 README 與 `__init__`、`peers/__init__.py`、`atlas.py`），`engine.py` 頂端說「結伴同行還在原位用」的過時註解第 38 批會連那兩行 import 一起拿掉。",
            "- **Task 1 的情境**：接著 `travel` 一軌補（原創名字；另開一軌在計畫第一節寫理由），`TravelScenario` 說明字裡「這一軌不擺同伴」那一句改掉。**結伴同行**：Joy 2026-10-19 已經把結伴從玩家卡上拿掉（`/api/peer/act` 的 travel 回「沒有這個動作」），情境直接 `invites.send` 一張 kind 是 `travel` 的邀請、或直接寫 `tagalong`；`invite:yes` 答應、`invite:no` 婉拒；`_join` 重驗（人已經不在這裡、在路上、已經跟著別人、身後已經有人跟著）；帶頭的人步行出發（跟著的人照抄同一趟、體力各付各的、騎馬的照自己的坐騎再省）、疾行出發；跟不上的（體力不夠、手上有事、不在出發那一站）；結伴路上三樣小事分收穫（含收穫上限拿滿的對照）；帶頭的人喊停、折返；跟著的人在路上按 `act:part`；還在等時按 `/api/party/leave`（沒跟著誰時也按一次）；`party_wait_seconds` 內沒動身就散了；答應了卻自己先走；走到終點拱手作別；兩邊 `/api/main` 的 `party`。第 37 批認定第 12 條的結伴那一半（選單上 travel 的邀請與收回、答應走到 `_join`）也在這一軌走到。**出發與抵達**：`/api/main` 的 `journey`（有沒有下一站）、出發那一句的現實倒數、剛出發就折返、人物帶路的步調（在 `talk` 軌）、坐在店裡動身收店、抵達交糧車接護送、出師、走到城外的引導、抵達觸發大勢門檻、季落幕時停在當下那一站、只到中途站不另寫一則。",
            "- **設定、切點與假人**：三種設定 season21、week7、test（test 的路最長 3 分鐘，切在路上只靠 season21、week7，第 47 批認定第 6 條）。半舊半新切在：答應了結伴、帶頭的人還沒動身；結伴走在路上、做了一件小事；帶頭的人喊了停、還沒走到那一站；跟著的人分道揚鑣之後自己還在路上。假人：BotRunner 回結伴邀請（`answer_call` 經 `join_refusal`）、答應了就原地等，加整季機器人；任何畫面都不透露誰是假人。",
            "- **比對哪幾軌（PM 認定，不跑全部的軌）**：`travel`、`herald`、`stamina`、`talk`（人物帶路）、`tavern`、`bout`、`outlets`、`peers`、`battle`、`muster`；三種設定，整段與半舊半新都比；計畫第一節量出還有哪幾軌真的有人在路上。`_arrivals` 每次 `sync` 都跑，其餘的軌由主幹每天的全面檢查全比。",
            "- **測試**：結伴的單元測試在混合檔 `tests/core/test_social.py`（真的是結伴的 3 條）、`/api/party/leave` 的在 `tests/server/test_server.py`，出發與抵達的散在 `test_engine`、`test_mounts`、`test_day_scale`、`test_prologue`、`test_contract_core`：這一批不抽混合檔（第 47 批認定第 5 條），全部列進包 README「另外要跑的」，`test_social` 整檔歸第 61 批。包裡新寫一條測 `/api/party/leave` 回的鍵（`main`、`message`）。",
            "- `web/` 不准碰（手冊 G9；`main.js` 的 `leaveParty`、`app.js` 的分派與 `travel`、`setMoveMode` 等第 66 批），沒有實機驗收：自己那一軌打到 `/api/party/leave`、每一個 `act:part` 與結伴的 `invite:` 動作，看回應內容。",
            "- **不改的**：資料庫結構（develop 第 9 版）；`BUS_ORDER`；`web/`；舊的趕路（`hurry`）照舊認得；`atlas`（第 50 批）、`bounties`（第 45 批）；玩家互動包的檔只在 `ctx._join` 那幾處說明照實改（第 38 批同時在改這一包）。導覽〈行動與地盤〉「移動」那一條只補程式的位置。",
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

b = BATCHES[N]  # 鍵可以帶字尾（「29b」＝第 29 批之二），n 取前面的數字
DEFAULTS = {"reviewers": 2, "dev_model": "sonnet", "after15": True,
            "prev_plan": "docs/superpowers/plans/2026-11-04-人物情誼包-第2批.md"}
PARALLEL = (f"同時在跑的批看 split/trunk 交接第一節「現在在跑」。這一批從 split/trunk `{BASE}` 開（PM 開 `{b['feature']}` 在這一筆）。"
            "共用登記檔各寫各的段，合併時 PM 照順序接。")
a = {**DEFAULTS, **{k: v for k, v in b.items() if v is not None}, "n": int(re.match(r"\d+", N).group()), "base": BASE,
     "parallel": b.get("parallel") or PARALLEL,
     "body": "\n".join(b["body"] + COMMON_BODY)}
if b.get("dev_model", "x") is None:  # 核心批留在 Opus（總表 5.2 第 3 條）：不給 dev_model
    a.pop("dev_model", None)
meta_end = SRC.index("}\n", SRC.index("export const meta")) + 2
body = re.sub(r"\bargs\b", "ARGS", SRC[meta_end:])
s = SRC[:meta_end] + "\nconst ARGS = " + json.dumps(a, ensure_ascii=False) + "\n" + body
(OUT / f"b{N}.js").write_text(s, encoding="utf-8", newline="\n")
print("wrote", OUT / f"b{N}.js")
