"""W1 後續實機：從 scratchpad 的複本開伺服器（埠 8166），模型網址指到沒人聽的埠（絕不打 11434）。TIANXIA_DB、TIANXIA_PROFILE 由外面設。"""
import os
import sys

ROOT = r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\w1b\src"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import server  # noqa: E402

server.CONTENT.config.ollama_url = "http://127.0.0.1:9"
server.main(["--port", "8166"])
