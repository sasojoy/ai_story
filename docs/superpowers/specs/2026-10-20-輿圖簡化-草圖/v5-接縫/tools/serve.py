"""第 5 批對比圖的預覽伺服器：埠 7962、season21、領地爭奪只在這個行程裡打開、模型指到沒人聽的埠。用法：python serve.py <解出來的根目錄>"""
import os
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
HERE = Path(__file__).resolve().parent
os.environ["TIANXIA_DB"] = str(HERE / "shot.db")
os.environ["TIANXIA_PROFILE"] = "season21"
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import server  # noqa: E402

server.CONTENT.config.conquest.enabled = True
server.CONTENT.config.ollama_url = "http://127.0.0.1:9"
server.main(["--port", "7962"])
