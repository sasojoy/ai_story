"""某次工作流程每個子代理吃的 token（照 transcript 的 usage 加總）與用的模型。用法：agent_tokens.py <run_id>..."""
import io
import json
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = Path(os.environ["WF_DIR"])  # 這個 session 的 subagents\workflows 資料夾（工作流程結果裡的 Transcript dir 往上一層）
for run in sys.argv[1:]:
    print("=====", run)
    for meta in sorted((BASE / run).glob("agent-*.meta.json")):
        m = json.loads(meta.read_text(encoding="utf-8"))
        f = meta.with_name(meta.name.replace(".meta.json", ".jsonl"))
        tot = {"input": 0, "output": 0, "create": 0, "read": 0}
        models, turns = set(), 0
        seen = set()
        for line in f.read_text(encoding="utf-8").splitlines() if f.exists() else []:
            try:
                o = json.loads(line)
            except Exception:
                continue
            msg = o.get("message") or {}
            u = msg.get("usage")
            if not u or msg.get("id") in seen:
                continue
            seen.add(msg.get("id"))
            turns += 1
            models.add(msg.get("model"))
            tot["input"] += u.get("input_tokens", 0)
            tot["output"] += u.get("output_tokens", 0)
            tot["create"] += u.get("cache_creation_input_tokens", 0)
            tot["read"] += u.get("cache_read_input_tokens", 0)
        lab = m.get("label") or m.get("description") or ""
        print(f" {str(lab)[:24]:<24} turns={turns:<4} in={tot['input']:<7} out={tot['output']:<7} create={tot['create']:<8} read={tot['read']:<10} {sorted(str(x) for x in models)}")
