# 輿圖簡化對比圖的預覽伺服器：埠 7892、season21、領地爭奪只在這個行程裡打開、模型指到沒人聽的埠。
import os
import sys
from pathlib import Path

ROOT = Path(r"C:\Ray\專案\天下大勢\.claude\worktrees\serene-galileo-46e759")
HERE = Path(__file__).resolve().parent
os.environ["TIANXIA_DB"] = str(HERE / "tianxia.db")
os.environ["TIANXIA_PROFILE"] = "season21"
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import server  # noqa: E402

server.CONTENT.config.conquest.enabled = True
server.CONTENT.config.ollama_url = "http://127.0.0.1:9"
server.main(["--port", "7892"])
