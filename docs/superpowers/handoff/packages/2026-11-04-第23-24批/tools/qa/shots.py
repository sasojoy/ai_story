"""三張圖（sanity）：drive.py season21 hb snap 留下的三個快照（boss、ring、titles），各自起兩台（HEAD 8169 bout1chk.localhost、
BASE 8170 127.0.0.1，時鐘凍在快照那一刻；ring、titles 照 drive 那一刻把擂台的週解鎖關掉），無頭 Chromium 375×812 淺色各拍一張，
再並排（上面一條寫是哪一版、png 的 sha256 前 12 碼）、印逐像素差幾個。python shots.py"""
import hashlib
import io
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import requests
from PIL import Image, ImageChops, ImageDraw, ImageFont

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
CHK = Path(os.environ["QA_DIR"]).resolve()
PY = sys.executable
PROFILE = "season21"
SHOTS = CHK / "shots"
SHOTS.mkdir(exist_ok=True)
PHASES = {"boss": ("qa12boss", "1-boss", "江湖頁：頭目戰打到一半（第一回合之後；程聽松）", False),
          "ring": ("qa12ring2", "2-arena", "擂台：挑范映雪打到一半（放手一搏之後；柯遠帆）", True),
          "titles": ("qa12ring2", "3-board", "見聞・榜單：擂台榜（天下第一；柯遠帆）", True)}
PORTS = tuple(int(x) for x in os.environ.get("QA_PORTS", "8161,8162").split(","))
SIDES = {"head": (CHK / "HEAD", PORTS[0], f"http://{os.environ.get('QA_HOST', 'qachk')}.localhost:{PORTS[0]}/", 9369, "A"),
         "base": (CHK / "BASE", PORTS[1], f"http://127.0.0.1:{PORTS[1]}/", 9370, "B")}


def backup(src: Path, dst: Path) -> None:
    for old in dst.parent.glob(dst.stem + "*"):
        old.unlink()
    a = sqlite3.connect(str(src), timeout=30)
    b = sqlite3.connect(str(dst))
    a.backup(b)
    b.close()
    a.close()


def listening(port: int, seconds: float = 120) -> bool:
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    return False


ONLY = sys.argv[1:]  # 只重拍這幾個（並排照舊三張都重拼）
for phase, (login, key, title, unlock) in PHASES.items():
    if ONLY and phase not in ONLY:
        continue
    clock =(CHK / "snap" / f"{PROFILE}-{phase}-clock.txt").read_text(encoding="utf-8").strip()
    procs = []
    try:
        for side, (root, port, url, cdp, ab) in SIDES.items():
            db = CHK / "db" / f"shot-{phase}-{side}.db"
            backup(CHK / "snap" / f"{PROFILE}-{phase}-{ab}.db", db)
            env = os.environ.copy()
            env.update(QA_ROOT=str(root), QA_T0=clock, QA_PORT=str(port), TIANXIA_DB=str(db), TIANXIA_ADMINS="驗收官",
                       PYTHONIOENCODING="utf-8", PYTHONHASHSEED="0", TIANXIA_PROFILE=PROFILE)
            env.pop("TIANXIA_PUBLIC_URL", None)
            log = open(CHK / "logs" / f"shot-{phase}-{side}.log", "w", encoding="utf-8")
            procs.append((subprocess.Popen([PY, "-u", "-X", "utf8", str(CHK / "s" / "serve.py")], cwd=str(root), env=env,
                                           stdout=log, stderr=subprocess.STDOUT), log))
        for side, (root, port, url, cdp, ab) in SIDES.items():
            assert listening(port), port
            if unlock:
                print(phase, side, requests.post(f"http://127.0.0.1:{port}/__qa/tweak", json={"path": "jianfa.week_unlock", "value": False},
                                                 timeout=30).json(), flush=True)
        for side, (root, port, url, cdp, ab) in SIDES.items():
            r = subprocess.run(["node", "--no-warnings", str(CHK / "s" / "shots.mjs"), url, side, phase, str(SHOTS), str(cdp), login],
                               capture_output=True, text=True, encoding="utf-8", timeout=180)
            print(phase, side, r.stdout.strip()[:900], r.stderr.strip()[:300], flush=True)
    finally:
        for proc, log in procs:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True) if os.name == "nt" else proc.kill()
            log.close()
        time.sleep(1.5)

try:
    font = ImageFont.truetype(os.environ.get("QA_FONT", r"C:\Windows\Fonts\msjh.ttc"), 28)  # 別的系統設 QA_FONT 指到一個中文字型
except OSError:
    font = ImageFont.load_default()
for phase, (login, key, title, unlock) in PHASES.items():
    files = {side: SHOTS / f"{side}-{key}.png" for side in ("head", "base")}
    imgs = {side: Image.open(f).convert("RGB") for side, f in files.items()}
    sha = {side: hashlib.sha256(f.read_bytes()).hexdigest()[:12] for side, f in files.items()}
    diff = ImageChops.difference(imgs["head"], imgs["base"])
    px = sum(1 for p in diff.getdata() if p != (0, 0, 0))
    w, h = imgs["head"].size
    gap, band = 24, 84
    out = Image.new("RGB", (w * 2 + gap, h + band), (255, 255, 255))
    d = ImageDraw.Draw(out)
    for i, (side, label) in enumerate((("head", "HEAD 7857b79e"), ("base", "BASE c4a838f2"))):
        x = i * (w + gap)
        out.paste(imgs[side], (x, band))
        d.text((x + 12, 6), f"{label}　png {sha[side]}", fill=(30, 30, 30), font=font)
        d.text((x + 12, 44), title, fill=(90, 90, 90), font=font)
    dst = SHOTS / f"side-{key}.png"
    out.save(dst)
    print(key, "same_bytes", sha["head"] == sha["base"], "diff_pixels", px, "size", (w, h), "->", dst, flush=True)
