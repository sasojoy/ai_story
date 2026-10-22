"""原型那一份 app.js 對 HEAD 的 web/app.js 出一份 patch（路徑寫成 web/app.js，在工作樹 `git apply --check` 得過）。
用法：python mkpatch.py <原本的 app.js> <原型的 app.js> <輸出 patch>"""
import subprocess
import sys
from pathlib import Path

orig, mock, out = (Path(a) for a in sys.argv[1:4])
r = subprocess.run(["git", "diff", "--no-index", "--no-color", str(orig), str(mock)], capture_output=True)
assert r.returncode == 1, r.stderr
text = r.stdout.decode("utf-8")
lines = text.split("\n")
fixed = []
for line in lines:
    if line.startswith("diff --git "):
        line = "diff --git a/web/app.js b/web/app.js"
    elif line.startswith("--- "):
        line = "--- a/web/app.js"
    elif line.startswith("+++ "):
        line = "+++ b/web/app.js"
    fixed.append(line)
out.write_bytes("\n".join(fixed).encode("utf-8"))
print("ok", out, len(fixed))
