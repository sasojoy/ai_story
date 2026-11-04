"""額度重置之後開的兩條：第 20 批（人物情誼二）與第 13 批接手。base 由命令列給（第 23、24 批合完的 split/trunk）。用法：make_next.py <SHA>"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
REPO = Path(r"C:\Ray\專案\天下大勢\.claude\worktrees\pm-1103\docs\superpowers\pm-workflows")
SRC = (REPO / "split-batch.js").read_text(encoding="utf-8").replace("\r\n", "\n")
BASE = sys.argv[1]
SP = r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad"


def embed(a, out):
    meta_end = SRC.index("}\n", SRC.index("export const meta")) + 2
    body = re.sub(r"\bargs\b", "ARGS", SRC[meta_end:])
    s = SRC[:meta_end] + "\nconst ARGS = " + json.dumps(a, ensure_ascii=False) + "\n" + body
    (HERE / out).write_text(s, encoding="utf-8", newline="\n")
    print("wrote", out)


b20 = {
    "n": 20,
    "title": "人物情誼二——人物對話三段式、NPC 智能 2.0（開口求人、開條件、陪你出陣）（`companion_agent`、`parley` 進 `companions` 包）",
    "pkg": "companions",
    "feature": "feature/companions",
    "dev": "dev/companions-2",
    "plan": "docs/superpowers/plans/2026-11-04-人物情誼包-第2批.md",
    "prev_plan": "docs/superpowers/plans/2026-11-04-人物情誼包-第1批.md",
    "host": "companions2",
    "reviewers": 2,
    "dev_model": "sonnet",
    "body": "\n".join([
        "- 範圍照總表 3.3 第 20 列（約 30 個方法、516 行）與第二節「人物情誼（`companions`）」、附錄甲與丙的裁定。`companion_agent`、`parley` 進 `tianxia/features/companions/`（舊名留別名）；`talk:`、`parley:` 前綴；`bot_policy.score` 的 `talk:` 那一段搬進包的 `bots.py`（包還沒有就開）。交友、求見是第 21 批，不搬。",
        "- **先做**（總表那一格）：`content.py` 讀的 `DIALOGUE_TAGS` 搬進 `models`。",
        "- 鎖外的三段式照第 24 批 `sense_draw` 的做法：模型呼叫不進鎖，server 留該留的殼。**不准碰 `web/`**；動到路由的話，自己那一軌每一條都要打到（web/ 沒動就沒有實機驗收）。",
        "- Task 1 的情境：接在 `companions` 一軌（或另開 `talk` 一軌）：人物對話走完 A、B、C 三段（模型回與模型擋著）、開口求人、開條件、陪你出陣、食言；第 19 批修正輪開的 `debts` 那一段可以直接用。五種設定；半舊半新切在對話中（`pending_companion`）或約定還欠著的那一刻；假人碰得到 `talk:`。",
        "- same_behavior 新開的軌一律用原創名字（PM 11/04，第 22 批認定第 3 條）。",
        "- 第 19、23、24 批的 PM 認定在手冊第十五節，開工先讀。第 19 批第七節記了 `STAGE_PACKAGES` 這種「列舉每一包」的表 git 看不到。",
    ]),
    "base": BASE,
    "ports": {"dev": 8175, "rev": 8176, "fix": 8176, "head": 8177, "base": 8178},
    "fb": "FB-9310～FB-9319",
    "parallel": f"同時在跑的：第 13 批（拿掉探索三選一，`dev/strip-1`）。這一批從 split/trunk `{BASE}` 開（PM 開 feature/companions 在這一筆）。",
    "after15": True,
}
embed(b20, "b20.js")

s = (HERE / "make_b13.py").read_text(encoding="utf-8")
ns = {}
code = s[s.index("a = {"):s.index("def embed")]
exec(code, {"BASE": BASE}, ns)
b13 = ns["a"]
b13["body"] = "\n".join([
    "- **接手（PM 11/04 晚）**：上一個子代理做到 Task 1 就停了（session 結束）。**分支這樣開，不要照下面「分支」那一句**：",
    "  - `git switch -c dev/strip-1 origin/feature/strip`（PM 開在這一批的 base），`git merge origin/dev/strip-1b`（`c6cee8bc`：`same_behavior.py` 的 `strip` 一軌 414 行，**還沒有跑過 selftest**）。會撞的只有 `same_behavior.py` 檔尾那一塊，兩邊都留。",
    f"  - 上一個留的東西可以直接用：`{SP}\\b13\\scan_tests.txt`（只測三選一的測試掃描，行號照現行程式重量）、`strip_track.py.txt`。`{SP}\\b13\\base` 是舊的 base `221c43bf`，刪掉重解。",
    "  - 第 19、23、24 批都合進來了：`sense_treasure_points` 搬到 `tianxia/features/sense/` 的設定，舊模組 `sensing` 已經是別名。",
]) + "\n" + b13["body"]
b13["parallel"] = f"同時在跑的：第 20 批（人物情誼二，`dev/companions-2`）。這一批從 split/trunk `{BASE}` 開（第 8、12、17、19、22、23、24 批都已合；PM 開 feature/strip 在這一筆）。"
embed(b13, "b13-r.js")
