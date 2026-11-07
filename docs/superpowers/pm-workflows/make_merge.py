"""產生一批的合併腳本。用法：make_merge.py <args.json> <輸出的 merge-b<批號>.js>
args.json 的鍵：n、title、feature、source（origin/dev/<x>）、source_head、plan、ports（"8159～8162"）、
full_suite（核心批 true）、decisions（字串陣列，PM 的認定）、notes（字串陣列，要特別處理的）。
產生的 .js 交給 Workflow（scriptPath）。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SRC = (Path(__file__).resolve().parent / "split-merge.js").read_text(encoding="utf-8").replace("\r\n", "\n")
a = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
a["decisions"] = "\n".join(a.get("decisions", []))
a["notes"] = "\n".join(a.get("notes", []))
meta_end = SRC.index("}\n", SRC.index("export const meta")) + 2
body = re.sub(r"\bargs\b", "ARGS", SRC[meta_end:])
Path(sys.argv[2]).write_text(SRC[:meta_end] + "\nconst ARGS = " + json.dumps(a, ensure_ascii=False) + "\n" + body, encoding="utf-8", newline="\n")
print("wrote", sys.argv[2])
