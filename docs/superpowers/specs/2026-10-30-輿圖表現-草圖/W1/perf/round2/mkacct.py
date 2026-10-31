"""建帳號（帳號 w1c、名號 映雪）。密碼寫到 w1c/local，不印。TIANXIA_DB、TIANXIA_PROFILE 由外面設。"""
import os
import subprocess
import sys

SP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(SP, "src")
PY = r"C:\Ray\專案\天下大勢\.venv\Scripts\python.exe"
env = dict(os.environ, PYTHONIOENCODING="utf-8")
r = subprocess.run([PY, os.path.join(ROOT, "scripts", "set_password.py"), "w1c", "--character", "映雪", "--db", os.environ["TIANXIA_DB"],
                    "--local-dir", os.path.join(SP, "local")], cwd=ROOT, env=env, capture_output=True, encoding="utf-8", errors="replace")
print("w1c", r.returncode, (r.stdout or "")[-300:], (r.stderr or "")[-600:])
sys.exit(0)
