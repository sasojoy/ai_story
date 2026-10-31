"""W2 第二輪實機：把工作樹 HEAD 的程式解到 w2b/srv（伺服器從這裡開），QA 的資料庫與密碼檔複製一份到 w2b（不動 qa-w2 那一份）。
web/ 之後用 swap_web.py 換（伺服器每次請求讀檔）。"""
import os
import shutil
import subprocess
import sys
import tarfile

WT = r"C:\Ray\專案\天下大勢\.claude\worktrees\wf_1654dfc8-5ce-1"
SP = r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad"
W2B = os.path.join(SP, "w2b")
SRV = os.path.join(W2B, "srv")
tar = os.path.join(W2B, "src.tar")
if os.path.isdir(SRV):
    shutil.rmtree(SRV)
os.makedirs(SRV)
subprocess.run(["git", "archive", "HEAD", "-o", tar, "tianxia", "content", "web", "server.py", "server_push.py", "zhuan_html.py", "llm_queue.py",
                "console.py", "scripts"], cwd=WT, check=True)
with tarfile.open(tar) as t:
    t.extractall(SRV)
print("srv", sorted(os.listdir(SRV)))
if "--db" in sys.argv:
    for ext in ("", "-wal", "-shm"):
        shutil.copy2(os.path.join(SP, "qa-w2", "qa.db" + ext), os.path.join(W2B, "live.db" + ext))
    os.makedirs(os.path.join(W2B, "local"), exist_ok=True)
    for f in os.listdir(os.path.join(SP, "qa-w2", "local")):
        shutil.copy2(os.path.join(SP, "qa-w2", "local", f), os.path.join(W2B, "local", f))
    print("db and passwords copied")
