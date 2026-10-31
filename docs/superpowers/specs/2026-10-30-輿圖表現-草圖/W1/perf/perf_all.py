"""W1 後續 Task 1：V（向量）、R（點陣，同一份 web/、網址帶 ?ground=raster）、S1 預設（參考列：Joy 的點陣、中近景不畫地，換 web/ 的三個檔）
四種條件（像素比 3／2 × 降速 6／4）各兩輪，輪內 V、R 輪流（第二輪 R 先），S1 排最後；每一次是一個新開的瀏覽器、裡面跑三次。最後換回 V 的檔。
  perf_all.py [輸出資料夾]"""
import shutil
import subprocess
import sys
from pathlib import Path

SP = Path(r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\w1b")
NODE = r"C:\Users\ray61\AppData\Local\hermes\node\node.exe"
out = Path(sys.argv[1]) if len(sys.argv) > 1 else SP / "perf"
out.mkdir(exist_ok=True)


def use(ver):
    for f in ("map.js", "app.js", "style.css"):
        shutil.copyfile(SP / f"web_{ver}" / f, SP / "src" / "web" / f)


try:
    for dpr, thr in ((3, 6), (3, 4), (2, 6), (2, 4)):
        for rnd in (1, 2):
            for var in (("V", "R", "S1") if rnd == 1 else ("R", "V", "S1")):
                use("s1" if var == "S1" else "v")
                r = subprocess.run([NODE, "perf3.mjs", str(out), str(SP / "local" / "w1bqa_password.txt"), "w1bqa", var, str(dpr), str(thr), str(rnd)],
                                   cwd=SP, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
                print(var, dpr, thr, rnd, r.returncode, (r.stdout or "")[-600:], (r.stderr or "")[-600:], flush=True)
finally:
    use("v")
    print("restored v", flush=True)
