"""每日整套（開發規範手冊 4.4）：把 origin/develop 抓一份乾淨的出來，整套含 slow 跑一次，摘要跟前一天比。

平常由 scripts/nightly.ps1 叫（排程每天一次；行程優先權 BelowNormal、-n 4，不搶線上伺服器）。也可以手動：
  .venv/Scripts/python.exe scripts/nightly.py                    # 抓、跑、寫摘要
  .venv/Scripts/python.exe scripts/nightly.py --summarize-only   # 不抓不跑，拿今天已經有的結果重寫摘要
  .venv/Scripts/python.exe scripts/nightly.py --date 2026-10-31 --summarize-only   # 指定哪一天（驗比較用）

寫在 <主要 clone>/.local/nightly/ 底下（.local/ 不進版控）：
  checkout/        origin/develop 的乾淨工作樹（git worktree，每次重設到最新、清掉沒進版控的檔）
  <日期>.log       pytest 的完整輸出（留 30 天）
  <日期>.xml       pytest 的 junit 結果（摘要從這裡讀；留 30 天）
  <日期>.json      這一次的摘要（下一次拿來比）
  latest.txt       給人看的摘要：develop 的 SHA、passed／failed、新紅、舊紅、轉綠、昨天到今天 develop 新進的提交
不推任何東西；資料庫用系統暫存資料夾的 tianxia-nightly/nightly.db（TIANXIA_DB），不碰 saves/ 與線上。"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_COMMITS = 80  # 摘要裡最多列幾筆提交（再多就寫「還有幾筆」）
KEEP_DAYS = 30  # <日期>.log、<日期>.xml 留幾天
FETCH_TIMEOUT = 300  # 秒：fetch 卡住（網路、憑證要跳視窗）就放棄，照本機上一次抓到的 origin/develop 跑，寫進備註
LOCK_STALE = 3 * 3600  # 秒：排程的時限是兩小時，鎖比這還舊就是被砍掉的那一次留下的，不算數
LOCK_NAME = "running.lock"


def take_lock(out: Path, now: float | None = None) -> bool:
    """一次只跑一份（手冊 4.2）：在 .local/nightly 建 running.lock（O_EXCL，誰先建到算誰的）。拿不到回 False。
    鎖裡記 pid 與開始的時間；超過 LOCK_STALE 的是被砍掉的那一次留下的，清掉重拿。內容讀不了（剛建好還沒寫）照檔案時間算。"""
    now = time.time() if now is None else now
    lock = out / LOCK_NAME
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                started = float(json.loads(lock.read_text(encoding="utf-8"))["started"])
            except (OSError, ValueError, KeyError, TypeError):
                try:
                    started = lock.stat().st_mtime
                except OSError:  # 剛好被對方收掉了：再搶一次
                    continue
            if now - started <= LOCK_STALE:
                return False
            lock.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "started": now}, f)
        return True
    return False


def lock_holder(out: Path) -> str:
    try:
        held = json.loads((out / LOCK_NAME).read_text(encoding="utf-8"))
        when = dt.datetime.fromtimestamp(float(held["started"])).strftime("%Y-%m-%d %H:%M")
        return f"pid {held.get('pid')}，{when} 開始"
    except (OSError, ValueError, KeyError, TypeError):
        return f"鎖 {out / LOCK_NAME}"


def release_lock(out: Path) -> None:
    (out / LOCK_NAME).unlink(missing_ok=True)


def git(cwd: Path, *args: str, check: bool = False, timeout: float | None = None) -> subprocess.CompletedProcess:
    """排程在背景跑、沒有人看著：git 一律不跳提示（憑證過期要登入就失敗，不是一直等）；給了 timeout 的逾時當失敗（結束碼 124）。"""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        out = subprocess.CompletedProcess(["git", *args], 124, "", f"逾時（{timeout} 秒）")
    if check and out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失敗：{out.stderr.strip()}")
    return out


def find_repo(start: Path) -> Path:
    """主要的那份 clone（工作樹的 .git 是檔案，照它找回主要的 .git）。"""
    common = git(start, "rev-parse", "--path-format=absolute", "--git-common-dir", check=True).stdout.strip()
    return Path(common).parent


def prepare_checkout(repo: Path, checkout: Path, branch: str) -> tuple[str, list[str]]:
    """明確 fetch origin/<branch>，把 checkout 重設成它的乾淨一份；回（SHA, 備註）。"""
    notes: list[str] = []
    fetched = git(repo, "fetch", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}", timeout=FETCH_TIMEOUT)
    if fetched.returncode != 0:
        notes.append(f"fetch 失敗，用的是本機上一次抓到的 origin/{branch}：{fetched.stderr.strip()[:200]}")
    target = f"origin/{branch}"
    alive = checkout.exists() and git(checkout, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true" \
        and Path(git(checkout, "rev-parse", "--show-toplevel").stdout.strip()).resolve() == checkout.resolve()
    if not alive:
        if checkout.exists():
            shutil.rmtree(checkout, ignore_errors=True)
        git(repo, "worktree", "prune")
        checkout.parent.mkdir(parents=True, exist_ok=True)
        git(repo, "worktree", "add", "--detach", "--force", str(checkout), target, check=True)
    else:
        git(checkout, "checkout", "--detach", "--force", target, check=True)
        git(checkout, "reset", "--hard", target, check=True)
        git(checkout, "clean", "-ffdx", check=True)
    sha = git(checkout, "rev-parse", "HEAD", check=True).stdout.strip()
    return sha, notes


def run_suite(checkout: Path, out: Path, date: str, workers: int) -> tuple[int, float]:
    """整套含 slow、-n workers、BelowNormal；輸出寫 <日期>.log，junit 寫 <日期>.xml。
    資料庫放系統暫存資料夾（路徑沒有中文），每次清掉重來。"""
    tmp = Path(tempfile.gettempdir()) / "tianxia-nightly"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "TIANXIA_DB": str(tmp / "nightly.db"), "PYTHONIOENCODING": "utf-8"}
    junit = out / f"{date}.xml"
    junit.unlink(missing_ok=True)  # 同一天重跑：pytest 沒寫出新的（結束碼 3、4、被砍），不能拿早上那一份當這一次的
    cmd = [sys.executable, "-m", "pytest", "-q", "-n", str(workers), "-m", "slow or not slow",
           "-p", "no:cacheprovider", "-rfE", f"--junitxml={junit}"]
    flags = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    start = time.time()
    with open(out / f"{date}.log", "wb") as log:
        log.write(f"每日整套 {date}：{' '.join(cmd[1:])}（{checkout}）\n".encode("utf-8"))
        log.flush()
        code = subprocess.call(cmd, cwd=checkout, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    return code, time.time() - start


def _nodeid(classname: str, name: str, root: Path) -> str:
    """junit 的 classname（tests.core.test_x 或 tests.core.test_x.TestY）加 name 換回 pytest 的 id。"""
    parts = classname.split(".")
    for cut in range(len(parts), 0, -1):
        path = "/".join(parts[:cut]) + ".py"
        if (root / path).exists():
            return "::".join([path, *parts[cut:], name])
    return f"{classname}::{name}"


def parse_junit(xml_path: Path, root: Path) -> dict | None:
    """junit 結果：tests、failures、errors、skipped、passed、time、failed（紅的測試 id）。沒有檔或讀不了回 None。"""
    if not xml_path.exists():
        return None
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return None
    suites = [tree.getroot()] if tree.getroot().tag == "testsuite" else list(tree.getroot().iter("testsuite"))
    counts = {k: sum(int(s.get(k, 0)) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
    failed = sorted({_nodeid(c.get("classname", ""), c.get("name", ""), root)
                     for s in suites for c in s.iter("testcase")
                     if c.find("failure") is not None or c.find("error") is not None})
    counts["passed"] = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
    counts["time"] = round(sum(float(s.get("time", 0)) for s in suites), 1)
    counts["failed"] = failed
    return counts


def load_previous(out: Path, date: str) -> dict | None:
    """date 之前最近的一份摘要（<日期>.json）。"""
    earlier = sorted(p for p in out.glob("????-??-??.json") if p.stem < date)
    for p in reversed(earlier):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def compare(previous: list[str] | None, today: list[str]) -> tuple[list[str], list[str], list[str]]:
    """（新紅：前一次綠、今天紅〔前一次沒有這條也算〕；舊紅：前一次就紅；轉綠：前一次紅、今天不紅）。"""
    before = set(previous or [])
    now = set(today)
    return sorted(now - before), sorted(now & before), sorted(before - now)


def commits_between(repo: Path, previous: dict | None, sha: str) -> tuple[str, str, list[str]]:
    """前一次的 SHA 到這一次之間 develop 新進的提交（沒有前一次就列一天之內的）：（標題寫的範圍, 自己查用的 git log, 提交）。"""
    fmt = "--format=%h %ad %an：%s"
    if previous and previous.get("sha"):
        if previous["sha"] == sha:
            return "跟前一次是同一個 SHA，沒有新提交", "", []
        span = f"{previous['sha'][:8]}..{sha[:8]}"
        out = git(repo, "log", "--date=short", fmt, f"{previous['sha']}..{sha}")
        if out.returncode == 0:
            return span, f"git log {span}", [line for line in out.stdout.splitlines() if line.strip()]
    out = git(repo, "log", "--date=short", fmt, "--since=1 day ago", sha)
    return ("沒有前一次可比，列一天之內的", f'git log --since="1 day ago" {sha[:8]}',
            [line for line in out.stdout.splitlines() if line.strip()])


def red_days(since: str, date: str) -> int:
    """從 since 那一天起紅到 date 是第幾天（當天算第 1 天）。"""
    return (dt.date.fromisoformat(date) - dt.date.fromisoformat(since)).days + 1


def render(summary: dict, previous: dict | None, new: list[str], old: list[str], fixed: list[str],
           span: str, log_cmd: str, commits: list[str]) -> str:
    lines = [f"每日整套 {summary['date']}（develop {summary['sha'][:8]}，{summary.get('started', '')}開始）"]
    if summary.get("result") is None:
        lines.append(f"結果：沒跑完（pytest 結束碼 {summary.get('exit')}，不是 0、1 或沒有 junit 結果；不比、不留 .json；"
                     f"看 {summary['date']}.log 最後幾行）")
    else:
        r = summary["result"]
        lines.append(f"結果：{r['passed']} passed，{r['failures']} failed，{r['errors']} error，{r['skipped']} skipped"
                     f"（pytest 結束碼 {summary.get('exit')}，用了 {summary.get('minutes', '?')} 分鐘，-n {summary.get('workers')}）")
    lines += [f"備註：{n}" for n in summary.get("notes", [])]
    if previous is None:
        lines.append("前一次：沒有前一天可比（第一次跑）；下面紅的全部列在「新紅」")
    else:
        lines.append(f"前一次：{previous.get('date')}（develop {previous.get('sha', '')[:8]}，"
                     f"紅 {len(previous.get('failed', []))} 條）")
    lines.append("")
    lines.append(f"新紅（前一次綠、這一次紅）：{len(new)} 條" + ("" if new else "（無）"))
    lines += [f"  {t}" for t in new]
    lines.append(f"舊紅（前一次就紅）：{len(old)} 條" + ("（無）" if not old else "（手冊 4.4：新紅三天沒修，revert 那一線的合併）"))
    since = summary.get("red_since", {})
    lines += [f"  {t}" + (f"（從 {since[t]} 起紅，第 {red_days(since[t], summary['date'])} 天）" if t in since else "")
              for t in old]
    lines.append(f"轉綠（前一次紅、這一次不紅）：{len(fixed)} 條" + ("" if fixed else "（無）"))
    lines += [f"  {t}" for t in fixed]
    lines.append("")
    lines.append(f"develop 新進的提交（{span}）：{len(commits)} 筆" + ("" if commits else "（無）"))
    lines += [f"  {c}" for c in commits[:MAX_COMMITS]]
    if len(commits) > MAX_COMMITS:
        lines.append(f"  ……還有 {len(commits) - MAX_COMMITS} 筆（{log_cmd}）")
    return "\n".join(lines) + "\n"


def finished(code: int | None) -> bool:
    """pytest 的結束碼算不算跑完整套：0 全綠、1 有紅。2 是中斷（junit 只有跑到的那一半）、3 內部錯誤、4 用法錯誤、5 一條都沒收到；
    None 是只重寫摘要、不知道結束碼（--summarize-only 又沒有那一天的 json），照 junit 算。"""
    return code is None or code in (0, 1)


def summarize(repo: Path, out: Path, checkout: Path, date: str, sha: str, extra: dict) -> str:
    """讀這一次的 junit、跟前一次比、寫 <日期>.json 與 latest.txt；回摘要文字。結束碼不是 0、1 的當成沒跑完。"""
    result = parse_junit(out / f"{date}.xml", checkout) if finished(extra.get("exit")) else None
    summary = {"date": date, "sha": sha, **extra, "result": None if result is None else
               {k: v for k, v in result.items() if k != "failed"},
               "failed": [] if result is None else result["failed"]}
    previous = load_previous(out, date)
    if result is None:  # 沒跑完：不知道誰紅誰綠，不比
        new, old, fixed = [], [], []
    else:
        new, old, fixed = compare(previous.get("failed") if previous else None, summary["failed"])
        # 每一條紅的從哪一天起紅：舊紅照前一次記的（這一欄以前沒有：當成從前一次那一天起），新紅是今天
        before = previous.get("red_since", {}) if previous else {}
        summary["red_since"] = {**{t: before.get(t) or previous["date"] for t in old}, **{t: date for t in new}}
    span, log_cmd, commits = commits_between(repo, previous, sha)
    text = render(summary, previous, new, old, fixed, span, log_cmd, commits)
    if result is not None:  # 沒跑完的那一次不留 json：下一次照樣跟最後一次跑完的比
        (out / f"{date}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "latest.txt").write_text(text, encoding="utf-8-sig")  # 帶 BOM：Windows PowerShell 5.1 的 Get-Content 才讀得對
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="每日整套：origin/develop 整套含 slow，摘要跟前一天比")
    parser.add_argument("--repo", type=Path, help="主要的 clone（預設照這支腳本所在的工作樹找）")
    parser.add_argument("--branch", default="develop")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--date", default=None, help="這一次記成哪一天（預設今天，YYYY-MM-DD）")
    parser.add_argument("--summarize-only", action="store_true", help="不抓不跑，拿那一天已經有的 junit 重寫摘要")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    repo = (args.repo or find_repo(Path(__file__).resolve().parent)).resolve()
    out = repo / ".local" / "nightly"
    checkout = out / "checkout"
    out.mkdir(parents=True, exist_ok=True)
    date = args.date or dt.date.today().isoformat()
    started = dt.datetime.now().strftime("%Y-%m-%d %H:%M ")
    if args.summarize_only:
        sha = git(checkout, "rev-parse", "HEAD").stdout.strip() if checkout.exists() else ""
        old = out / f"{date}.json"
        if old.exists():
            kept = json.loads(old.read_text(encoding="utf-8"))
            sha = kept.get("sha") or sha
            extra = {k: kept[k] for k in ("started", "exit", "minutes", "workers", "notes") if k in kept}
        else:
            extra = {"started": started, "exit": None, "workers": args.workers, "notes": ["只重寫摘要（--summarize-only）"]}
        print(summarize(repo, out, checkout, date, sha, extra))
        return 0
    if not take_lock(out):  # 另一份（排程或手動）正在用 checkout 與暫存資料夾：不動它，它跑完會寫 latest.txt
        print(f"另一份每日整套正在跑（{lock_holder(out)}）：這一次不跑。")
        return 1
    try:
        return _run(repo, out, checkout, args.branch, args.workers, date, started)
    finally:
        release_lock(out)


def _run(repo: Path, out: Path, checkout: Path, branch: str, workers: int, date: str, started: str) -> int:
    try:
        sha, notes = prepare_checkout(repo, checkout, branch)
    except (RuntimeError, OSError) as exc:  # 抓不到、重設不了：寫進 latest.txt，免得早上看到的是前一天的
        text = f"每日整套 {date}（{started}開始）\n結果：沒跑——準備 checkout 失敗：{exc}\n"
        (out / "latest.txt").write_text(text, encoding="utf-8-sig")
        print(text)
        return 1
    print(f"每日整套：develop {sha[:8]}，跑在 {checkout}", flush=True)
    code, seconds = run_suite(checkout, out, date, workers)
    extra = {"started": started, "exit": code, "minutes": round(seconds / 60, 1), "workers": workers, "notes": notes}
    print(summarize(repo, out, checkout, date, sha, extra))
    prune(out, date)
    return 0


def prune(out: Path, date: str) -> None:
    """<日期>.log、<日期>.xml 只留最近 KEEP_DAYS 天（一份 xml 約 1.5 MB）；<日期>.json 很小，全留。"""
    cutoff = (dt.date.fromisoformat(date) - dt.timedelta(days=KEEP_DAYS)).isoformat()
    for p in [*out.glob("????-??-??.log"), *out.glob("????-??-??.xml")]:
        if p.stem < cutoff:
            p.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
