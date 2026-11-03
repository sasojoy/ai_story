"""工作樹的伺服器（埠 8154）：模型網址指到死埠，碰不到本機的 Ollama。TIANXIA_DB、TIANXIA_PROFILE 由呼叫的人設好。"""
import os
import sys

ROOT = r"C:\Ray\專案\天下大勢\.claude\worktrees\wf_dc7bba53-cfb-2"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import server  # noqa: E402

server.CONTENT.config.ollama_url = "http://127.0.0.1:9"
server.main(["--port", "8154"])
