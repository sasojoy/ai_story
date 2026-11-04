"""總表第 13 批「拿掉一」（探索三選一、找素材「自己說」、城裡操練）：企劃者 10/31「整套拿掉，排在搬完六包之後」、11/01「決戰合完就做」。
第 12 批合進 develop 之後開（三選一練功撞頭目那幾格在單挑包）。從 repo 的 split-batch.js 產生 b13.js。base 由命令列給（第 12 批合完的 develop）。
這一批不是純搬：承諾改成 week7、season21、test 三種設定一字不變，none、weekend 照拿掉的範圍變。"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
REPO = Path(r"C:\Ray\專案\天下大勢\.claude\worktrees\pm-1103\docs\superpowers\pm-workflows")
SRC = (REPO / "split-batch.js").read_text(encoding="utf-8").replace("\r\n", "\n")
BASE = sys.argv[1]

a = {
    "n": 13,
    "title": "拿掉一：探索三選一、找素材「自己說」、城裡操練（**不是純搬**：week7、season21、test 三種設定所有軌一個字不變；none、weekend 只照拿掉的範圍變）",
    "pkg": "strip",
    "feature": "feature/strip",
    "dev": "dev/strip-1",
    "plan": "docs/superpowers/plans/2026-11-04-拿掉一-第13批.md",
    "prev_plan": "docs/superpowers/plans/2026-11-01-出陣包-第3批.md",
    "host": "strip1",
    "reviewers": 3,
    "body": "\n".join([
        "- **這一批是拿掉，不是純搬**（企劃者 10/31「整套拿掉，排在搬完六包之後」、11/01「決戰合完就做」；手冊第十五節 11/01 第 4 條「只剩 7 天與 21 天兩種季」）。範圍照總表 3.3 第 13 列整格（18 個方法、337 行）。承諾改成：",
        "  - **week7、season21、test 三種設定**：same_behavior 所有軌、explore-compare、假人，整段與半舊半新**逐位元組一樣**。",
        "  - **none、weekend 兩種設定**：只准照拿掉的範圍變——三選一的三顆、找素材「自己說」、城裡操練不見了，連帶的那幾行字跟著不見。Task 5 把這兩種設定的差異**逐段列出來**，每一段都要對得上「拿掉的東西」，對不上的就是退版、要修。",
        "  - 這一條優先於下面「做法」裡「行為一個字不變」「五種設定全部逐位元組一樣」的寫法。下面的 Task 3、4 在這一批改成：Task 3 拿掉程式、Task 4 拿掉與改寫測試。`# strip` 段只放這一批真的要新增的登記（多半是刪，刪的照原位刪）。",
        "- **先做**（總表那一格的「先做」，不做的話 week7、season21 會變）：`Config.explore_modes.enabled` 在兩種季都是開著的，活著的程式還在讀它（`precise.on`、推大勢的 `event_trend_share` 五折、`economy` 捐軍備、`sensing`／`treasures` 的觀山石加成與說明字、`bounties` 討伐懸賞的說法、`howto` 探索那幾行）：先改成「一直是開著的那個值」；`event_trend_share`、`sense_treasure_points` 搬到讀它的那一包的設定，預設值不變。`explore_modes.py` 裡活著的小工具（`rng_for`、`one_of`、`_one`、`gather_finds` 給探索一顆；`is_town` 進共用規則層）先搬走。照現行程式重量，不要照總表的行號。",
        "- **拿掉的**照總表那一格：`explore_modes.py` 剩下的、`gather_llm.py`、`training.py` 的操練那一半、`content/gather_branches.json`；`Game` 上 18 個方法（含第 12 批留給這一批的 `_boss_away`、`_town_drill`、`_training_option`、`_nearest_practice`）；`bot_policy.score` 的 `explore:` 那一段與 `act:` 裡的 `explore_modes.on`、`drill`；`bot.py` 讀三選一的兩處；server 的 `gather_text`；`choose`、`_act`、`_action_title`、`action_notes`、`_everyday_options`、`_explore_one`、`_arrive` 裡碰到三選一與操練的幾行。`training` 剩下的分級（`on`、`tier_of`、`TIER_WORDS`、`PLACE_LINE`、`is_town`）留著，第 18 批處理。",
        "- **第 12 批（單挑包 `bout`）已經合進 develop**：三選一練功撞頭目那幾格現在在單挑包（`GAME_DELEGATE_CALLERS` 裡標三選一的那十幾對、`_boss_wait_text` 一類），拿掉三選一時一起收掉，單挑包 README、邊界測試跟著改。",
        "- **測試**：只測三選一、城裡操練、找素材「自己說」的測試整條拿掉（計畫列清單與條數）；混著測別的的，只拿掉那一段、別的斷言一字不改。`tests/conftest.py::classic_rules` 與 `test_explore_modes.py::test_the_old_explore_with_the_switch_off`（開關關著的那一條）跟著三選一一起拿；`classic_rules` 剩下只關盡頭阻力，叫它的測試照舊。CLAUDE.md 與導覽裡寫三選一的段落，計畫第五節列出來交 PM 改（你不改 CLAUDE.md）。",
        "- **不動 `web/`**：畫三選一、操練的那幾段先留著（伺服器不再給選項就畫不出來），第 3 階網頁殼化時再清；計畫記下是哪幾段。內容改了要跑 `test_content` 與真實內容不含 slow 的。",
        "- 週末設定第 14 批才拿（甲：只關門），這一批 weekend 照樣起得來、跑得動。",
        "- **same_behavior 新開的軌一律用原創名字**（PM 11/04，第 22 批認定第 3 條）。",
        "- 選項 id：按舊的 `explore:`、`drill` 這類 id，照 `choose` 對不認得的選項既有的回法回，不另寫新字。",
    ]),
    "check_steps": "兩台（HEAD／BASE）各跑 season21、week7：註冊兩個帳號、管理者開季、探索一趟（撞到事件、撞到頭目各一次）、找素材、出陣、推一天，所有回應與資料庫逐位元組一樣。另外 HEAD 單獨開 weekend：行動列沒有三選一的三顆、沒有城裡操練、找素材不再問「自己說」；按舊的 explore:／drill 選項 id 照 choose 既有的回法回；截三張 375 淺色圖（行動列、探索之後、找素材之後）給 PM",
    "base": BASE,
    "ports": {"dev": 8163, "rev": 8164, "fix": 8164, "head": 8165, "base": 8166},
    "fb": "FB-9290～FB-9299",
    "parallel": ("同時在跑的：第 23 批（新包 `arts`，`dev/arts-1`：修練）、第 24 批（新包 `sense`，`dev/sense-1`：有所感與頓悟）。"
                 f"這一批從 develop `{BASE}` 開（第 8、12、17、22 批都已合；PM 開 feature/strip 在這一筆）。第 24 批的有所感（`sensing`）讀觀山石加成，你把 `sense_treasure_points` 搬到讀它的那一包的設定時，**它現在還是舊模組 `sensing.py`**（第 24 批正在搬成 `features/sense/`）：照現行程式搬到它旁邊，合併時 PM 照順序接。"),
    "after15": True,
}


def embed(a, out):
    meta_end = SRC.index("}\n", SRC.index("export const meta")) + 2
    body = re.sub(r"\bargs\b", "ARGS", SRC[meta_end:])
    s = SRC[:meta_end] + "\nconst ARGS = " + json.dumps(a, ensure_ascii=False) + "\n" + body
    (HERE / out).write_text(s, encoding="utf-8")
    print("wrote", out)


embed(a, "b13.js")
