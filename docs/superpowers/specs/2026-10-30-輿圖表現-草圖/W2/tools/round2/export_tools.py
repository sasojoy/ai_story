"""把第二輪的量測、拍照腳本與結果抄進 W2/tools/round2/（腳本、選項的 patch、每一支的結果 JSON）；四張重拍存 JPG 進 W2/。
腳本裡的路徑是 scratchpad 的絕對路徑（照 W2 tools 的慣例）。文字檔一律寫 LF（git 會照 autocrlf 處理）。"""
import io
import os
import shutil
import sys

from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
W2B = r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\w2b"
W2 = r"C:\Ray\專案\天下大勢\.claude\worktrees\wf_1654dfc8-5ce-1\docs\superpowers\specs\2026-10-30-輿圖表現-草圖\W2"
DST = os.path.join(W2, "tools", "round2")
os.makedirs(DST, exist_ok=True)
SCRIPTS = ["setup_srv.py", "serve.py", "swap_web.py", "look_saves.py", "calday.py", "cdp.mjs", "lib.mjs", "grab.mjs", "dragstop.mjs", "blink.mjs",
           "hud.mjs", "goto.mjs", "goto_sum.py", "cover.mjs", "cover_sum.py", "optshot.mjs", "compose_9094.py", "mkopt.py", "mkshoot2.py", "shoot2.mjs",
           "shots2.json", "opt-甲.patch", "opt-乙.patch", "opt-丙.patch", "compose_round2.py", "export_tools.py"]
for name in SCRIPTS:
    with open(os.path.join(W2B, name), encoding="utf-8", newline="") as f:
        text = f.read().replace("\r\n", "\n")
    with open(os.path.join(DST, name), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
RESULTS = {"grab-before": "grab.json", "grab-after": "grab.json", "dragstop-before": "dragstop.json", "dragstop-after": "dragstop.json",
           "blink-before": "blink.json", "blink-after": "blink.json", "hud-before": "hud.json", "hud-after": "hud.json",
           "cover-now": "cover.json", "cover-甲": "cover.json", "cover-乙": "cover.json", "cover-丙": "cover.json",
           "opt-now": "optshot.json", "opt-甲": "optshot.json", "opt-乙": "optshot.json", "opt-丙": "optshot.json", "retake": "measure.json"}
for w in ("375", "360", "320", "1280"):
    RESULTS[f"goto-before-{w}"] = "goto.json"
    RESULTS[f"goto-after-{w}"] = "goto.json"
os.makedirs(os.path.join(DST, "out"), exist_ok=True)
for tag, name in RESULTS.items():
    src = os.path.join(W2B, "out", tag, name)
    if os.path.exists(src):
        shutil.copyfile(src, os.path.join(DST, "out", f"{tag}-{name}"))
    else:
        print("missing", src)
shutil.copyfile(os.path.join(W2B, "out", "cover_summary.json"), os.path.join(DST, "out", "cover_summary.json"))
for name in ("W2-3-去輿圖-375", "W2-4-去輿圖護糧-375", "W2-5-抽屜一排卡-375", "W2-6-抽屜全開-375"):
    Image.open(os.path.join(W2B, "out", "retake", name + ".png")).convert("RGB").save(os.path.join(W2, name + ".jpg"), quality=86)
print("exported", len(SCRIPTS), "scripts,", len(RESULTS), "results")
