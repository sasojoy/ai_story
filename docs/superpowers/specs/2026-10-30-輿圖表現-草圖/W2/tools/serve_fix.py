"""W2 修正輪實機：從 scratchpad 的複本（git archive）開伺服器（埠 8181、w2fix.localhost），模型網址指到沒人聽的埠（絕不打 11434）。
TIANXIA_DB、TIANXIA_PROFILE 由外面設。改 web/ 不必重開（每次請求讀檔）。"""
import os
import sys

ROOT = r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\w2fix\src"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import server  # noqa: E402

server.CONTENT.config.ollama_url = "http://127.0.0.1:9"
server.main(["--port", "8181"])
