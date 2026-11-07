"""把一波工作流程的回傳寫成紀錄檔（開發定的、留給誰、審查發現、閘門、修正），放進 repo 當合併紀錄。用法：wave_record.py <工作流程 output> <輸出 md> <波>"""
import json
import sys
from pathlib import Path

out_path, md_path, wave = sys.argv[1], sys.argv[2], sys.argv[3]
data = json.loads(Path(out_path).read_text(encoding="utf-8"))
r = data["result"]
if isinstance(r, str):
    r = json.loads(r)
L = [f"# 波次 {wave} 的紀錄（工作流程回傳，PM 整理；認定在手冊第十五節）", ""]
L += [f"合併 `{r['merged']['head'][:8]}`，修正後 `{r['head'][:8]}`，基準 `{r['merge_base'][:8]}`。", ""]
L += ["## 每一批", ""]
line_seen = None
for d in r.get("batches", []):
    if d["line"] != line_seen:
        line_seen = d["line"]
        L.append(f"### 線：{line_seen}")
        L.append("")
    L.append(f"#### 第 {d['n']} 批：{d['title']}")
    L.append("")
    L.append(f"- head `{d['head'][:8]}`")
    if d.get("decided"):
        L.append("- 開發定的：")
        L += [f"  - {x}" for x in dict.fromkeys(d["decided"])]
    if d.get("leftovers"):
        L.append("- 留給後面的：")
        L += [f"  - {x}" for x in dict.fromkeys(d["leftovers"])]
    if d.get("docs"):
        L.append("- 要寫進 README、導覽的：")
        L += [f"  - {x}" for x in dict.fromkeys(d["docs"])]
    L.append("")
L += ["## 合併", "", r["merged"].get("conflicts", ""), "", "## 閘門", "", "```json", (r.get("gate") or {}).get("result", ""), "```", ""]
doc = r.get("docsPass") or {}
if doc:
    L += ["## 文件輪", "", f"head `{str(doc.get('head', ''))[:8]}`", ""]
    L += [f"- 做了：{x}" for x in doc.get("fixed", [])]
    L += [f"- 對不上或沒做：{x}" for x in doc.get("rejected", [])]
    L += ["", doc.get("tests", ""), ""]
L += ["## 審查", ""]
for rv in r.get("reviews", []):
    L.append(f"- {rv.get('summary', '')[:1500]}")
    for f in rv.get("findings", []):
        L.append(f"  - [{f['severity']}] {f['title']}（{f['where']}）")
        L.append(f"    - {f.get('evidence', '')[:800]}".replace("\n", " "))
L += ["", "## 實機驗收", "", (r.get("check") or {}).get("report", "（這一波沒動 `web/`）"), "", "## 修正", ""]
fix = r.get("fix") or {}
L += [f"- 修了：{x}" for x in fix.get("fixed", [])]
L += [f"- 駁回：{x}" for x in fix.get("rejected", [])]
L += ["", fix.get("tests", ""), ""]
text = "\n".join(L).replace("\r\n", "\n")
Path(md_path).write_text(text, encoding="utf-8", newline="\n")
print("wrote", md_path, len(text))
