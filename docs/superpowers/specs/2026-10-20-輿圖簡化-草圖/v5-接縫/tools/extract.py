"""git archive HEAD 解到 scratchpad（照 tianxia-dev：tar 用 Python 解，中文路徑才不出錯）。用法：python extract.py <工作樹> <目標資料夾>"""
import io
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

root, dest = Path(sys.argv[1]), Path(sys.argv[2])
if dest.exists():
    shutil.rmtree(dest)
dest.mkdir(parents=True)
data = subprocess.run(["git", "-C", str(root), "archive", "HEAD", "tianxia", "content", "web", "scripts", "server.py", "server_push.py",
                       "zhuan_html.py", "llm_queue.py", "console.py"], capture_output=True, check=True).stdout
with tarfile.open(fileobj=io.BytesIO(data)) as tar:
    tar.extractall(dest)
print("ok", sum(1 for _ in dest.rglob("*.py")))
