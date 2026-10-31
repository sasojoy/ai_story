"""W2 實機：從工作樹開伺服器（埠 8179、w2.localhost），模型網址指到沒人聽的埠（絕不打 11434）。TIANXIA_DB、TIANXIA_PROFILE 由外面設。
改 web/ 不必重開（每次請求讀檔）。"""
import os
import sys

ROOT = r"C:\Ray\專案\天下大勢\.claude\worktrees\wf_b90e2f0a-6ca-1"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import server  # noqa: E402

server.CONTENT.config.ollama_url = "http://127.0.0.1:9"
server.main(["--port", "8179"])
