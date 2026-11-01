"""讀 inventory.json，寫 inventory_summary.md（數字總表）。"""
from __future__ import annotations

import io
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
OUT = Path(r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\split")
d = json.loads((OUT / "inventory.json").read_text(encoding="utf-8"))

L = []
w = L.append
meta = d["meta"]
w("# 架構盤點：數字總表")
w("")
w(f"工作樹 `{meta['worktree']}`，develop `{meta['commit']}`（detached）。完整資料在 `inventory.json`（同資料夾）；這份只放數字。")
w(f"抽法：{meta['how']}。")
w("")

# ── 一、總表
mods = d["modules"]
nontest = [m for m in mods if not m["is_test"]]
root = [m for m in nontest if m["package"] == "tianxia"]
core = [m for m in nontest if m["module"].startswith("tianxia.core")]
feat = [m for m in nontest if m["module"].startswith("tianxia.features")]
ftest = [m for m in mods if m["is_test"]]
gc = d["game_class"]
gms = d["game_methods"]
eng = next(m for m in mods if m["module"] == "tianxia.engine")
routes = d["server_routes"]
srv_routes = [r for r in routes if r["source"] == "server.py"]
feat_routes = [r for r in routes if r["source"] != "server.py"]
app = d["web"]["app_js"]
app_file = next(f for f in d["web"]["files"] if f["path"] == "web/app.js")
app_fn = [x for x in app["top_level"] if x["kind"] in ("function", "async function")]
app_arrow = [x for x in app["top_level"] if x["kind"].endswith("arrow/function")]
content = d["content"]
tests = d["tests"]

w("## 一、總表")
w("")
w("| 項目 | 數 | 行數 |")
w("|---|---:|---:|")
w(f"| `tianxia/` 底下所有 .py（含 features 的 tests） | {len(mods)} | {sum(m['lines'] for m in mods):,} |")
w(f"| 　其中非測試 | {len(nontest)} | {sum(m['lines'] for m in nontest):,} |")
w(f"| 　　`tianxia/*.py`（頂層模組） | {len(root)} | {sum(m['lines'] for m in root):,} |")
w(f"| 　　`tianxia/core/` | {len(core)} | {sum(m['lines'] for m in core):,} |")
w(f"| 　　`tianxia/features/**`（不含 tests） | {len(feat)} | {sum(m['lines'] for m in feat):,} |")
w(f"| 　其中 `tianxia/features/*/tests`（含 conftest） | {len(ftest)} | {sum(m['lines'] for m in ftest):,} |")
w(f"| `engine.py` | 1 | {eng['lines']:,} |")
w(f"| 　`class Game`（第 {gc['start']}～{gc['end']} 行） | 方法 {gc['methods']} | 類別 {gc['lines']:,}；方法合計 {gc['method_lines']:,} |")
w(f"| 　engine.py 裡 Game 以外的頂層函式／類別 | {sum(1 for x in d['engine_other'] if x['kind'] == 'function')} 函式／"
  f"{sum(1 for x in d['engine_other'] if x['kind'] == 'class')} 類別 | {sum(x['lines'] for x in d['engine_other']):,} |")
w(f"| `server.py` 路由 | {len(srv_routes)} | handler 合計 {sum(r['lines'] for r in srv_routes):,} |")
w(f"| 功能包的路由（`features/*/routes.py`） | {len(feat_routes)} | {sum(r['lines'] for r in feat_routes):,} |")
w(f"| 　路由合計 | **{len(routes)}** | |")
srv_other_fn = [f for f in d["server_other"] if f.get("kind") != "class"]
w(f"| `server.py` 其餘頂層函式（不是路由） | {len(srv_other_fn)} | {sum(f['lines'] for f in srv_other_fn):,} |")
tbl = {k: v for k, v in d["server_tables"].items() if k != "_sets"}
w(f"| `server.py` 動作表（op → lambda） | {len(tbl)} 張、{sum(len(v['ops']) for v in tbl.values())} 個 op | |")
w(f"| `web/` 檔案 | {len(d['web']['files'])} | 文字檔合計 {sum(f.get('lines', 0) for f in d['web']['files']):,} |")
w(f"| `web/app.js` | 1 | {app_file['lines']:,} |")
w(f"| 　app.js 頂層 `function` 宣告 | **{len(app_fn)}** | {sum(x['lines'] for x in app_fn):,} |")
w(f"| 　app.js 頂層 `const x = () =>`／function 運算式 | {len(app_arrow)} | {sum(x['lines'] for x in app_arrow):,} |")
w(f"| 　app.js 頂層 `const` 物件 | {len(app['const_objects'])} | {sum(x['lines'] for x in app['const_objects']):,} |")
w(f"| 　app.js 頂層宣告合計（function、const、let、class） | {len(app['top_level'])} | |")
w(f"| `content/` 檔案 | {len(content)} | {sum(c['bytes'] for c in content):,} bytes |")
w(f"| 測試檔（test_*.py，`tests/` ＋ `features/*/tests`） | {tests['total']['files']} | `def test_` {tests['total']['test_functions']:,}（slow {tests['total']['slow_test_functions']:,}） |")
w(f"| 選項 id 的前綴（選項類別） | {len(d['option_prefixes'])} | |")
w(f"| 功能包（registry 登記） | {len(d['feature_packages'])} | |")
w("")
chk = d["web"]["node_syntax_check"]
w(f"JS 驗證：web/*.js 抽出的 {chk.get('total')} 段頂層宣告各自用 node `vm.Script` 編譯，失敗 {len(chk.get('bad', []))} 段；"
  f"app.js 掃到檔尾的深度 {app['scan_end_depth']}、狀態 {app['scan_end_mode']}（括號全部對上）。"
  "Game 方法數（1033）跟 engine.py 裡 `^    def` 的行數（1036）差 3：`OutingPlan.foe_note`，與兩個裝飾器"
  "（`_not_while_preparing`、`_outing_watch`）裡的內層函式；工作樹 `git status` 照舊是乾淨的。")
w("")
w("### inventory.json 的鍵")
w("")
w("| 鍵 | 筆數 | 內容 |")
w("|---|---:|---|")
keys = [
    ("game_methods", "Game 每個方法：行號、裝飾器、calls_self、called_by、mod_refs、ext_callers、ext_test_*、patched_in、touches_removal"),
    ("engine_other", "engine.py 裡 Game 以外的頂層函式與類別"),
    ("modules", "tianxia 底下每個 .py：package、區塊、行數、imports_tianxia（含 lazy、type_checking）、imported_by、imported_by_tests、頂層函式清單"),
    ("feature_packages", "現有功能包：prefix、bot_always、檔案"),
    ("server_routes", "每一條路由：路徑、方法、handler、行號、calls_game、calls_game_via_tables、calls_game_via_helpers、sub_ops（/api/do 的 op 分支）"),
    ("server_other", "server.py 其餘頂層函式（含 calls_game）"),
    ("server_tables", "MAIN_ACTIONS、ADMIN_ACTIONS、MENXIA_ACTIONS 每個 op 叫哪個 Game 方法"),
    ("server_plumbing", "殼的共用管線"),
    ("option_prefixes", "選項類別：處理方法、分派位置與 phase、子動詞、做出 id 的方法、提到它的模組"),
    ("other_prefix_like", "像前綴但不是選項類別的字串"),
    ("choose_dispatch", "Game.choose 的每一個分派條件（含 phase）"),
    ("act_dispatch", "Game._act 的每一個分派條件"),
    ("bot_policy", "score 的段與 act 子分支；bot_policy／bot／bot_runner 其他函式裡的前綴字串"),
    ("tests", "dirs（每個資料夾）、files（每個檔：test 數、slow 數、import 的 tianxia 模組）"),
    ("content", "content 每個檔：大小、JSON 型別與筆數"),
    ("web", "每個檔的行數；app_js 與 other_js 的頂層宣告"),
]
for k, desc in keys:
    v = d[k]
    n = len(v) if isinstance(v, (list, dict)) else ""
    if k == "tests":
        n = len(v["files"])
    if k == "web":
        n = len(v["files"])
    if k == "bot_policy":
        n = len(v["score"]["segments"])
    w(f"| `{k}` | {n} | {desc} |")
w("")

# ── 二、Game 方法照名字前綴分組
w("## 二、Game 方法照名字前綴分組（前 60 組）")
w("")
w("前綴＝去掉開頭底線之後、第一個底線前的字（`_battle_choose` → `battle`；沒有底線的整個名字算一組）。照方法數排，同數照行數。")
w("")
groups = defaultdict(lambda: [0, 0, []])
for m in gms:
    base = m["name"].lstrip("_")
    pf = base.split("_", 1)[0] if base else m["name"]
    g = groups[pf]
    g[0] += 1
    g[1] += m["lines"]
    g[2].append(m["name"])
ranked = sorted(groups.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))
w(f"共 {len(groups)} 組；前 60 組涵蓋 {sum(v[0] for _, v in ranked[:60])} 個方法、{sum(v[1] for _, v in ranked[:60]):,} 行"
  f"（全部 {len(gms)} 個、{gc['method_lines']:,} 行）。")
w("")
w("| # | 前綴 | 方法數 | 行數 | 例 |")
w("|---:|---|---:|---:|---|")
for i, (pf, (n, ln, names)) in enumerate(ranked[:60], 1):
    ex = "、".join(f"`{x}`" for x in sorted(names, key=lambda x: -next(m["lines"] for m in gms if m["name"] == x))[:4])
    w(f"| {i} | `{pf}` | {n} | {ln:,} | {ex} |")
w("")

# ── 三、最大的
w("## 三、最大的 Game 方法（前 25）")
w("")
w("| 方法 | 行 | 行數 | self 呼叫數 | 被誰叫（數） | 測試檔數 |")
w("|---|---|---:|---:|---:|---:|")
for m in sorted(gms, key=lambda m: -m["lines"])[:25]:
    w(f"| `{m['name']}` | {m['start']}～{m['end']} | {m['lines']} | {len(m['calls_self'])} | {len(m['called_by'])} | {m['ext_test_files']} |")
w("")
w("## 四、最大的模組（非測試，前 30）")
w("")
w("| 模組 | 行數 | 區塊 | 被 import（非測試／測試） | import tianxia 模組數 |")
w("|---|---:|---|---:|---:|")
for m in sorted(nontest, key=lambda m: -m["lines"])[:30]:
    w(f"| `{m['path']}` | {m['lines']:,} | {m['block'] or '—'} | {len(m['imported_by'])}／{m['imported_by_tests_count']} | {len(m['imports_tianxia'])} |")
w("")
unl = [m for m in nontest if not m["block"] and m["module"] != "tianxia"]
w(f"CLAUDE.md 功能區塊表沒列到的非測試模組：{len(unl)} 個（`modules[].block` 是 null；照 CLAUDE.md「沒列在表上的照它做的事歸到最近的那一塊」，分配時要補）。")
w("")

# ── 五、選項前綴
w("## 五、選項 id 前綴 → 處理的 Game 方法")
w("")
w("`Game.choose` 照 `kind`（id 第一個冒號前）分派；phase 寫在 `option_prefixes[].dispatch`。`act:` 的子分派在 `Game._act`（見下一段）。")
w("")
w("| 前綴 | 處理（pre／main） | 做出 id 的地方 | 備註 |")
w("|---|---|---|---|")
for p in d["option_prefixes"]:
    note = []
    if p["feature_package"]:
        note.append(f"功能包 `{p['feature_package']}`")
    if p["removal"]:
        note.append(p["removal"])
    if p["stale_guards"]:
        note.append("有兩分頁搶的 Refused 守門")
    if p["after_hooks"]:
        note.append("做完補記：" + "、".join(sorted({g for h in p["after_hooks"] for g in h["game_methods"]})))
    w(f"| `{p['prefix']}` | {'、'.join(f'`{h}`' for h in p['handler_methods'][:4]) or '—'} | "
      f"{'、'.join(f'`{g}`' for g in p['generated_in'][:4])}{'…' if len(p['generated_in']) > 4 else ''} | {'；'.join(note)} |")
w("")
act = next(p for p in d["option_prefixes"] if p["prefix"] == "act:")
w(f"`Game._act` 子分派 {len(act['act_sub_dispatch'])} 條：")
w("")
w("| 行 | id | 處理 |")
w("|---:|---|---|")
for a in act["act_sub_dispatch"]:
    w(f"| {a['line']} | {'、'.join(f'`{i}`' for i in a['ids'])} | {'、'.join(f'`{g}`' for g in a['game_methods'][:4]) or '、'.join(a['module_calls'][:3]) or '（就地處理）'} |")
w("")

# ── 六、bot_policy
bp = d["bot_policy"]["score"]
w(f"## 六、`bot_policy.score`（第 {bp['start']}～{bp['end']} 行，{bp['lines']} 行）照前綴分的段")
w("")
w("| 行 | 前綴 | 行數 |")
w("|---|---|---:|")
for s in bp["segments"]:
    if s["prefixes"]:
        w(f"| {s['start']}～{s['end']} | {'、'.join(f'`{x}`' for x in s['prefixes'])} | {s['lines']} |")
    elif s.get("stmt") and "bot_pick" in s["stmt"]:
        w(f"| {s['start']} | （`features_core.bot_pick`：功能包先答） | {s['lines']} |")
w("")
actseg = next(s for s in bp["segments"] if "act:" in s["prefixes"])
w(f"`act:` 那一段的子分支 {len(actseg['act_branches'])} 條：" + "、".join(
    f"{'／'.join(b['ids']) or '（' + b['test'][:20] + '）'}@{b['start']}" for b in actseg["act_branches"]))
w("")
w(f"`bot_policy`、`bot`、`bot_runner` 其他函式裡寫到前綴字串的：{len(d['bot_policy']['other_prefix_refs'])} 個函式（`bot_policy.other_prefix_refs`）。")
w("")

# ── 七、路由
w("## 七、路由")
w("")
w("| 方法 | 路徑 | handler | 行 | 行數 | 直接叫的 Game 方法 | 經動作表 | 經殼函式 |")
w("|---|---|---|---|---:|---:|---:|---:|")
for r in routes:
    src = "" if r["source"] == "server.py" else f"（{r['source']}）"
    w(f"| {'/'.join(r['methods'])} | `{r['path']}` | `{r['handler']}`{src} | {r['start']}～{r['end']} | {r['lines']} | {len(r['calls_game'])} | "
      f"{len(r.get('calls_game_via_tables', []))} | {len(r.get('calls_game_via_helpers', []))} |")
w("")
w("動作表：" + "；".join(f"`{k}` {len(v['ops'])} 個 op（第 {v['start']}～{v['end']} 行）" for k, v in tbl.items()) + "。")
w("")
w("殼的共用管線（被 5 個以上殼函式／路由直接叫，遞移時略過）：" + "、".join(f"`{p['name']}`（{p['callers']}）" for p in d["server_plumbing"]) + "。")
w("")

# ── 八、web 與 content
w("## 八、web 與 content")
w("")
w("| web 檔 | 行數 | bytes | 頂層 function 宣告 | const 物件 | 頂層宣告合計 |")
w("|---|---:|---:|---:|---:|---:|")
for f in d["web"]["files"]:
    if "lines" in f:
        w(f"| `{f['path']}` | {f['lines']:,} | {f['bytes']:,} | {f.get('top_function_decls', '')} | {f.get('top_const_objects', '')} | {f.get('top_decls', '')} |")
bins = [f for f in d["web"]["files"] if "lines" not in f]
w(f"| 圖、影片等二進位檔 {len(bins)} 個 | | {sum(f['bytes'] for f in bins):,} | | | |")
w("")
ev = [c for c in content if c["path"].startswith("content/events/")]
prof = [c for c in content if c["path"].startswith("content/profiles/")]
top = [c for c in content if c["path"].count("/") == 1]
w(f"content：頂層 {len(top)} 檔（{sum(c['bytes'] for c in top):,} bytes）、`events/` {len(ev)} 檔（{sum(c['bytes'] for c in ev):,} bytes）、"
  f"`profiles/` {len(prof)} 檔（{'、'.join(c['path'].rsplit('/', 1)[1] for c in prof)}）。")
w("")

# ── 九、測試
w("## 九、測試（ast 數 `def test_`，參數化算一條）")
w("")
w("| 資料夾 | 檔 | test_*.py | test 函式 | 其中 slow |")
w("|---|---:|---:|---:|---:|")
for k, v in tests["dirs"].items():
    w(f"| `{k}` | {v['files']} | {v['test_files']} | {v['test_functions']:,} | {v['slow_test_functions']:,} |")
w(f"| **合計** | | {tests['total']['files']} | {tests['total']['test_functions']:,} | {tests['total']['slow_test_functions']:,} |")
w("")

# ── 十、功能包與要拿掉的
w("## 十、現有功能包與整套拿掉的")
w("")
for f in d["feature_packages"]:
    w(f"- `{f['path']}`：prefix `{f['prefix']}`，bot_always {f['bot_always']}，非測試 {f['lines_py_nontest']:,} 行，{len(f['files'])} 個檔")
w("- `sys.modules` 舊名別名：" + "、".join(f"`{a['old_name']}` → `{a['now_is']}`" for a in d["module_aliases"]))
w("")
rm = [m for m in gms if m["touches_removal"]]
w("**整套拿掉**（企劃者 10/31：只剩 week7、season21；排在搬完六包之後，不規劃搬包）：")
w("")
for m in mods:
    if m["removal"]:
        w(f"- `{m['path']}`（{m['lines']:,} 行；被 {len(m['imported_by'])} 個非測試模組、{m['imported_by_tests_count']} 個測試檔 import）")
for c in content:
    if c.get("removal"):
        w(f"- `{c['path']}`（{c['bytes']:,} bytes）：{c['removal']}")
w(f"- Game 方法裡用到 explore_modes／gather_llm 的：{len(rm)} 個、{sum(m['lines'] for m in rm):,} 行（`game_methods[].touches_removal`）："
  + "、".join(f"`{m['name']}`" for m in rm))
w("- 不帶設定的 14 天季、週末設定：散在 `Config`／`content.py` 的 profile 判斷，這份盤點不逐條列（另派）")
w("")
(OUT / "inventory_summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("written", len(L), "lines; groups", len(groups))
