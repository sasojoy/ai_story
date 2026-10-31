"""把一份 web/ 的 js、css 抄進伺服器的複本（w2b/srv/web）：
  swap_web.py wt            工作樹現在的 web/
  swap_web.py rev <commit>  某一版（git show）
  swap_web.py dir <資料夾>   某一個資料夾（例 opt-甲/web）
只抄 main.js、map.js、outing.js、mall.js、app.js、style.css（圖不動）。"""
import os
import shutil
import subprocess
import sys

WT = r"C:\Ray\專案\天下大勢\.claude\worktrees\wf_1654dfc8-5ce-1"
SRV = r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\w2b\srv\web"
FILES = ("main.js", "map.js", "outing.js", "mall.js", "app.js", "style.css")
kind = sys.argv[1]
for f in FILES:
    dst = os.path.join(SRV, f)
    if kind == "wt":
        shutil.copyfile(os.path.join(WT, "web", f), dst)
    elif kind == "dir":
        src = os.path.join(sys.argv[2], f)
        if os.path.isfile(src):
            shutil.copyfile(src, dst)
        else:
            shutil.copyfile(os.path.join(WT, "web", f), dst)
    elif kind == "rev":
        data = subprocess.run(["git", "show", f"{sys.argv[2]}:web/{f}"], cwd=WT, capture_output=True, check=True).stdout
        with open(dst, "wb") as fh:
            fh.write(data)
print("swapped", kind, sys.argv[2:] if len(sys.argv) > 2 else "")
