"""收尾：刪掉 QA_DIR 的暫存大檔（資料庫、快照、回應副本、無頭 Chromium 的設定檔、測試伺服器的密碼與金鑰、單張原圖），
三份工作樹若還有殘留也刪；留腳本、比對報告、log、三張並排圖。"""
import os
import io
import shutil
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
CHK = Path(os.environ["QA_DIR"]).resolve()
for name in ("HEAD", "BASE", "MUT", "db", "snap", "out", "chrome", "local"):
    p = CHK / name
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)
    print(name, "gone" if not p.exists() else "STILL THERE")
for p in (CHK / "shots").iterdir() if (CHK / "shots").exists() else ():
    if not p.name.startswith("side-"):
        p.unlink()
print("left in shots:", sorted(x.name for x in (CHK / "shots").iterdir()) if (CHK / "shots").exists() else [])
print("HEAD、BASE、MUT 若是 git worktree：回 repo 跑一次 git worktree prune")
print("left:", sorted(x.name for x in CHK.iterdir()))
total = sum(f.stat().st_size for f in CHK.rglob("*") if f.is_file())
print("QA_DIR total bytes:", total)
