"""解 src.tar 到 w1c/src（伺服器的複本），兩版的 web/map.js 存到 web_before（0fb784ed）、web_after（工作樹 HEAD）。"""
import os
import shutil
import subprocess
import sys
import tarfile

SP = os.path.dirname(os.path.abspath(__file__))
WT = sys.argv[1]
src = os.path.join(SP, "src")
if os.path.isdir(src):
    shutil.rmtree(src)
tarfile.open(os.path.join(SP, "src.tar")).extractall(src)
for name, rev in (("web_before", "0fb784ed"), ("web_after", "HEAD")):
    os.makedirs(os.path.join(SP, name), exist_ok=True)
    data = subprocess.run(["git", "show", f"{rev}:web/map.js"], cwd=WT, capture_output=True, check=True).stdout
    open(os.path.join(SP, name, "map.js"), "wb").write(data)
    print(name, rev, len(data))
print("src", sorted(os.listdir(src)))
