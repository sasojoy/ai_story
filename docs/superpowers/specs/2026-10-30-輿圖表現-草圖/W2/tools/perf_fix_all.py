"""W2 修正輪：拖縮會不會因為小地圖的白框每一幀改屬性而變卡（W2 審查 nit）。三個版本輪流換進伺服器複本的 web/（伺服器每次請求讀檔）：
  W1（feature/map-view 2e35330f）、FIX（dev/map-view-w2-fix HEAD）、NOMINI（FIX 但 camSet 不叫 miniFrame：拖縮途中白框不動）。
像素比 3、CPU 降速 6，每個版本兩輪（每一輪一個新開的瀏覽器、裡面三次），輪內順序輪流。最後換回 FIX。
  perf_fix_all.py"""
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
SP = Path(r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\w2fix")
NODE = r"C:\Users\ray61\AppData\Local\hermes\node\node.exe"
OUT = SP / "perf"
OUT.mkdir(exist_ok=True)
SRC = SP / "src"

vers = {}
for v, tar in (("W1", "web_w1.tar"), ("FIX", "web_fix.tar")):
    d = SP / f"web_{v}"
    if not d.exists():
        tarfile.open(SP / tar).extractall(d)
    vers[v] = d / "web"
nomini = SP / "web_NOMINI" / "web"
if not nomini.exists():
    shutil.copytree(vers["FIX"], nomini)
    p = nomini / "map.js"
    t = p.read_bytes().decode("utf-8").replace("\r\n", "\n")
    old = "    miniFrame(q, g); // 小地圖的白框跟著每一幀（只改四個屬性）\n"
    assert t.count(old) == 1, t.count(old)
    p.write_bytes(t.replace(old, "").encode("utf-8"))
vers["NOMINI"] = nomini


def use(v):
    shutil.rmtree(SRC / "web")
    shutil.copytree(vers[v], SRC / "web")


try:
    for rnd in (1, 2):
        order = ("W1", "FIX", "NOMINI") if rnd == 1 else ("NOMINI", "FIX", "W1")
        for var in order:
            use(var)
            r = subprocess.run([NODE, "perf3_fix.mjs", str(OUT), str(SP / "local" / "w2qa_password.txt"), "w2qa", var, "3", "6", str(rnd)],
                               cwd=SP, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200)
            print(var, rnd, r.returncode, (r.stdout or "")[-500:], (r.stderr or "")[-500:], flush=True)
finally:
    use("FIX")
    print("restored FIX", flush=True)
