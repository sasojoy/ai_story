"""等一個檔出現（工作流程裡的子代理等 wave_gate.py 跑完用；Bash 的前景 sleep 被擋）。
用法：python wait_file.py <檔> [最多等幾秒，預設 570]。等到了印 done 與內容，結束碼 0；還沒好印 waiting，結束碼 0，再叫一次。"""
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
limit = float(sys.argv[2]) if len(sys.argv) > 2 else 570
end = time.monotonic() + limit
while time.monotonic() < end:
    if path.exists():
        print("done", path.read_text(encoding="utf-8", errors="replace").strip())
        raise SystemExit(0)
    time.sleep(5)
print("waiting")
