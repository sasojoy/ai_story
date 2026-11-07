"""從 journal 印出某次工作流程最後的修正結果、開發的待定問題、審查的發現標題。用法：show_fix.py <run_id>"""
import io
import json
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = Path(os.environ["WF_DIR"])  # 這個 session 的 subagents\workflows 資料夾（工作流程結果裡的 Transcript dir 往上一層）
fix, dev, findings = None, None, []
for line in (BASE / sys.argv[1] / "journal.jsonl").read_text(encoding="utf-8").splitlines():
    o = json.loads(line)
    if o.get("type") != "result":
        continue
    v = o.get("value") or o.get("result")
    if not isinstance(v, dict):
        continue
    if "fixed" in v:
        fix = v
    elif "findings" in v:
        findings += v["findings"]
    elif "open_questions" in v:
        dev = v
if fix:
    for k in ("head", "fixed", "rejected", "tests", "learned", "report"):
        v = fix.get(k)
        print(f"--- {k}")
        print(v[:3000] if isinstance(v, str) else "\n".join(str(x)[:600] for x in (v or [])))
print("--- open_questions")
for q in (dev or {}).get("open_questions") or []:
    print("-", q[:600])
print("--- findings")
for f in findings:
    print(f"[{f['severity']}] {f['title']}")
