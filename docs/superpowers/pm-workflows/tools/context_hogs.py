"""某個子代理的 context 被什麼吃掉：每一回合的 context 大小曲線、最大的工具結果前幾名與對應指令。用法：context_hogs.py <run_id> <label 子字串>"""
import io
import json
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = Path(os.environ["WF_DIR"])  # 這個 session 的 subagents\workflows 資料夾（工作流程結果裡的 Transcript dir 往上一層）
run, want = sys.argv[1], sys.argv[2]
for meta in sorted((BASE / run).glob("agent-*.meta.json")):
    if want not in meta.read_text(encoding="utf-8"):
        continue
    f = meta.with_name(meta.name.replace(".meta.json", ".jsonl"))
    calls, sizes, ctx, seen = {}, [], [], set()
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            o = json.loads(line)
        except Exception:
            continue
        msg = o.get("message") or {}
        u = msg.get("usage")
        if u and msg.get("id") not in seen:
            seen.add(msg.get("id"))
            ctx.append(u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0))
        c = msg.get("content")
        if not isinstance(c, list):
            continue
        for it in c:
            if not isinstance(it, dict):
                continue
            if it.get("type") == "tool_use":
                calls[it.get("id")] = it.get("name", "") + " " + json.dumps(it.get("input"), ensure_ascii=False)[:150]
            elif it.get("type") == "tool_result":
                sizes.append((len(json.dumps(it.get("content"), ensure_ascii=False)), calls.get(it.get("tool_use_id"), "?")))
    n = len(ctx)
    print("turns", n, "context at turn:", [ctx[i * (n - 1) // 8] // 1000 for i in range(9)], "K")
    print("total tool result chars", sum(s for s, _ in sizes) // 1000, "K; first-turn context", ctx[0] // 1000 if ctx else 0, "K")
    for s, cmd in sorted(sizes, key=lambda x: -x[0])[:12]:
        print(f" {s // 1000:>4}K {cmd}")
