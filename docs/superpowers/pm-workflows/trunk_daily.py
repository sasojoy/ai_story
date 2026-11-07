"""主幹每天一次的全面檢查（企劃者 2026-11-04「不要一直測試變成高度重複測試，這就是拆分的精神」）。
每批只驗自己那一包；跨包、合起來才壞的問題在這裡一次抓，所以批與合併都不必再跑整套和別包的軌（開發規範手冊 4.2）。

做兩件事：
1. same_behavior 所有軌（加 explore-compare）：上一次驗過的主幹 對 現在的主幹。
2. 現在的主幹跑整套含 slow（-n 4）。

PM 一天開一次，挑沒有合併在跑的時候（同一台最多兩份測試）：
  C:/Ray/專案/天下大勢/.venv/Scripts/python.exe docs/superpowers/pm-workflows/trunk_daily.py
結果寫在 <主要 clone>/.local/trunk_daily/：<SHA>.log、latest.txt。兩件都綠才把現在的主幹記進 verified.txt。
主幹從上次驗過到現在只動文件就只記一筆，不跑。行程優先權 BelowNormal，不搶線上玩家。不推任何東西。

紅了：從 `git log <verified>..<現在>` 那幾批裡找，開單交回；比對紅了就用那一軌（--tracks）對每一批的合併各比一次。
"""
from __future__ import annotations

import datetime as dt
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

# 只剩 7 天與 21 天兩種季（企劃者 10/31）；第 14 批 none、weekend 關門，same_behavior 的 compare 預設 --profiles 就是 week7、season21、test，假人軌一起比。
BRANCH = "split/trunk"
ANCHOR = "split-anchor-20261104"
FLAGS = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失敗：{out.stderr.strip()}")
    return out.stdout.strip()


def unpack(repo: Path, sha: str, dest: Path) -> None:
    dest.mkdir(parents=True)
    raw = subprocess.run(["git", "archive", "--format=tar", sha], cwd=repo, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        tar.extractall(dest)


def step(cmd: list[str], cwd: Path, env: dict, log: Path, title: str) -> int:
    started = dt.datetime.now()
    with log.open("a", encoding="utf-8") as f:
        f.write(f"\n===== {title} {started:%H:%M:%S}\n{' '.join(cmd)}\n")
        f.flush()
        code = subprocess.call(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT, creationflags=FLAGS)
        minutes = (dt.datetime.now() - started).total_seconds() / 60
        f.write(f"\n===== {title} 結束碼 {code}，{minutes:.1f} 分鐘\n")
    print(f"{title}：結束碼 {code}，{minutes:.1f} 分鐘", flush=True)
    return code


def tail(log: Path, n: int = 2) -> str:
    lines = [l for l in log.read_text(encoding="utf-8", errors="replace").splitlines() if " passed" in l or " failed" in l]
    return " / ".join(lines[-n:])[:300]


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    start = Path(__file__).resolve().parent
    repo = Path(git(start, "rev-parse", "--path-format=absolute", "--git-common-dir")).parent
    out = repo / ".local" / "trunk_daily"
    out.mkdir(parents=True, exist_ok=True)
    git(repo, "fetch", "origin", f"+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}")
    head = git(repo, "rev-parse", f"origin/{BRANCH}")
    mark = out / "verified.txt"
    base = mark.read_text(encoding="utf-8").strip() if mark.exists() else git(repo, "rev-parse", f"{ANCHOR}^{{commit}}")
    if base == head:
        print(f"主幹沒動（{head[:8]}），不跑")
        return 0
    changed = git(repo, "diff", "--name-only", base, head, "--", ".", ":(exclude)docs", ":(exclude).claude", ":(exclude)CLAUDE.md")
    if not changed:
        mark.write_text(head + "\n", encoding="utf-8")
        print(f"{base[:8]}..{head[:8]} 只動文件，記成驗過，不跑")
        return 0

    work = Path(tempfile.gettempdir()) / "tianxia-trunk-daily"
    shutil.rmtree(work, ignore_errors=True)
    unpack(repo, base, work / "base")
    # 現在的主幹開成真的工作樹：test_test_for 有幾條要叫 git，解開的 archive 不是 repo 會紅（11/04 第一次跑就中了三條）
    git(repo, "worktree", "add", "--detach", str(work / "head"), head)
    (work / "tmp").mkdir()
    log = out / f"{head[:8]}.log"
    log.write_text(f"{BRANCH} {base[:8]}..{head[:8]}\n", encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "TIANXIA_DB": str(work / "tmp" / "daily.db")}
    py = sys.executable
    script = str(work / "head" / "scripts" / "same_behavior.py")
    both = ["--base", str(work / "base"), "--head", str(work / "head")]
    compare = step([py, script, "compare", *both, "--tmp", str(work / "tmp" / "cmp")], work / "head", env, log, "所有軌比對")
    explore = step([py, script, "explore-compare", *both, "--tmp", str(work / "tmp" / "exp")], work / "head", env, log, "探索比對")
    shutil.rmtree(work / "base", ignore_errors=True)
    suite = step([py, "-m", "pytest", "-q", "-n", "4", "-m", "slow or not slow", "-p", "no:cacheprovider"],
                 work / "head", env, log, "整套含 slow")
    git(repo, "worktree", "remove", "--force", str(work / "head"))
    shutil.rmtree(work, ignore_errors=True)

    green = compare == 0 and explore == 0 and suite == 0
    summary = [
        f"{dt.datetime.now():%Y-%m-%d %H:%M} {BRANCH} {base[:8]}..{head[:8]}：{'全綠' if green else '有紅'}",
        f"所有軌比對 結束碼 {compare}；探索比對 結束碼 {explore}；整套含 slow 結束碼 {suite}（{tail(log)}）",
        f"完整輸出：{log}",
    ]
    (out / "latest.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary))
    if green:
        mark.write_text(head + "\n", encoding="utf-8")
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
