"""接下來幾批的派工（第 21、30、31、29、14、18 批）。用法：make_more.py <批號> <split/trunk SHA> [輸出資料夾]
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
a = {**b, "n": int(N), "base": BASE, "reviewers": 2, "dev_model": "sonnet", "after15": True,
     "prev_plan": "docs/superpowers/plans/2026-11-04-人物情誼包-第2批.md",
     "parallel": f"同時在跑的批看 split/trunk 交接第〇節「現在在跑」。這一批從 split/trunk `{BASE}` 開（PM 開 `{b['feature']}` 在這一筆）。共用登記檔各寫各的段，合併時 PM 照順序接。",
     "body": "\n".join(b["body"] + COMMON_BODY)}
meta_end = SRC.index("}\n", SRC.index("export const meta")) + 2
body = re.sub(r"\bargs\b", "ARGS", SRC[meta_end:])
s = SRC[:meta_end] + "\nconst ARGS = " + json.dumps(a, ensure_ascii=False) + "\n" + body
(OUT / f"b{N}.js").write_text(s, encoding="utf-8", newline="\n")
print("wrote", OUT / f"b{N}.js")
