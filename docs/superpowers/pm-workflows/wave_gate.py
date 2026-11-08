"""一波的總閘門（企劃者 2026-11-06「火力全開」「減少測試驗收的頻率」「一次性多改幾個功能再一起全部合併測試」）。

開發不再逐批比對、逐批合併；一波的每條線合起來之後，這裡一次驗完，不花 token：
1. 未定義名稱掃一次（tianxia、server.py、scripts、tests）。
2. 三種設定（season21、week7、不帶）各起一次伺服器，GET / 要 200。
3. same_behavior 所有軌、explore-compare：--base 對 --head（跟整套同時跑，省牆上時間）。每軌每設定的秒數在 compare.txt，最慢十格進 result.json。
4. --head 跑整套含 slow（-n 4），每條測試的秒數在 suite.xml（junit）。
5. 帶 --web 才跑：等前面都跑完（不跟整套同時跑）叫 head 上的 scripts/webqa/gate.py --base <sha> --head <sha> --out <結果夾>/web，
   結束碼 0 才綠、其他算紅，輸出在 web.txt。head 上沒有那個檔（第 77 批順延）就印一行、result.json 的 web 寫沒跑，不擋。

用法（Windows 上用 venv 的 python）：
  python docs/superpowers/pm-workflows/wave_gate.py --base <sha> --head <sha> [--name 波A] [--no-suite] [--no-compare] [--web] [--cache]
--cache 預設關：只給 compare 開，base 的結果留在 <主要 clone>/.local/wave_gate/cache（scripts/sb/cache.py）。同一波修正後重跑才省；要省到第二次，第一次就要帶
（第一次全沒命中，跑的跟不帶一樣、只多存檔）。進 develop、上 main 的那一次不開：鍵漏掉相依會假綠。
結果在 <主要 clone>/.local/wave_gate/<head 前 8 碼>/：gate.log、result.json、done（最後才寫，等它就好）。
結束碼 0 全綠、1 有紅。不推任何東西、不改 verified.txt（全面檢查的基準由 PM 記）。

紅了怎麼找：result.json 寫哪幾段紅、紅的軌與失敗的測試；比對紅了就用那一軌（--tracks）對每條線的 head 各比一次，看是哪一條線。
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

FLAGS = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
PROFILES = ("season21", "week7", "")  # 空字串＝不帶 TIANXIA_PROFILE（server.py 照舊套 season21）
BOOT_SECONDS = 180


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


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def boot(py: str, root: Path, env: dict, profile: str, log: Path) -> str:
    """起一次伺服器看 GET / 200。回空字串＝過，否則回原因。"""
    port = free_port()
    e = {**env, "TIANXIA_DB": str(root.parent / "tmp" / f"boot-{profile or 'none'}.db"), "PYTHONUNBUFFERED": "1"}
    e.pop("TIANXIA_PROFILE", None)
    if profile:
        e["TIANXIA_PROFILE"] = profile
    with log.open("a", encoding="utf-8") as f:
        f.write(f"\n===== 起伺服器 {profile or '不帶'} 埠 {port}\n")
        f.flush()
        run = f"import server; server.CONTENT.config.ollama_url = 'http://127.0.0.1:9'; server.main(['--port', '{port}'])"  # 模型網址指到死埠，絕不打 11434
        proc = subprocess.Popen([py, "-u", "-c", run], cwd=root, env=e, stdout=f, stderr=subprocess.STDOUT, creationflags=FLAGS)
    try:
        deadline = time.monotonic() + BOOT_SECONDS
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return f"{profile or '不帶'}：伺服器自己結束了，結束碼 {proc.returncode}"
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
                    return "" if r.status == 200 else f"{profile or '不帶'}：GET / 回 {r.status}"
            except OSError:
                time.sleep(1)
        return f"{profile or '不帶'}：{BOOT_SECONDS} 秒內沒起來"
    finally:
        subprocess.call(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start(cmd: list[str], cwd: Path, env: dict, out: Path):
    f = out.open("w", encoding="utf-8")
    return subprocess.Popen(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT, creationflags=FLAGS), f


def red_lines(path: Path, pattern: str, limit: int = 60) -> list[str]:
    if not path.exists():
        return []
    hits = [l.strip()[:200] for l in path.read_text(encoding="utf-8", errors="replace").splitlines() if re.search(pattern, l)]
    return hits[-limit:]


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--tracks", default="", help="只比這幾軌（修正之後重驗用）")
    ap.add_argument("--new", default="", help="新功能波：新包的名字（逗號分開），compare 扣掉它們帶來的 js、css、表、op（企劃者 11/08「新東西列出來，其餘一樣」）")
    ap.add_argument("--no-suite", action="store_true")
    ap.add_argument("--no-compare", action="store_true")
    ap.add_argument("--jobs", default="")
    ap.add_argument("--web", action="store_true", help="前面都跑完之後跑網頁比對（scripts/webqa/gate.py）")
    ap.add_argument("--cache", action="store_true", help="同一波修正後重跑才開；進 develop、上 main 的那一次不開")
    a = ap.parse_args()

    here = Path(__file__).resolve().parent
    repo = Path(git(here, "rev-parse", "--path-format=absolute", "--git-common-dir")).parent
    base, head = git(repo, "rev-parse", a.base + "^{commit}"), git(repo, "rev-parse", a.head + "^{commit}")
    out = repo / ".local" / "wave_gate" / head[:8]
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    work = Path(tempfile.gettempdir()) / f"tianxia-wave-{head[:8]}"
    shutil.rmtree(work, ignore_errors=True)
    (work / "tmp").mkdir(parents=True)
    git(repo, "worktree", "add", "--detach", str(work / "head"), head)  # 真的工作樹：test_test_for 有幾條要叫 git
    log = out / "gate.log"
    log.write_text(f"{a.name} {base[:8]}..{head[:8]} {dt.datetime.now():%m-%d %H:%M}\n", encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "TIANXIA_DB": str(work / "tmp" / "gate.db")}
    py = sys.executable
    root = work / "head"
    result: dict = {"name": a.name, "base": base, "head": head, "started": f"{dt.datetime.now():%m-%d %H:%M}", "cache": a.cache}
    if a.cache:
        print("這一次開了快取，不能當進 develop、上 main 的依據", flush=True)

    scan = subprocess.run([py, str(root / "docs" / "superpowers" / "pm-workflows" / "undef_scan.py"), "tianxia", "server.py", "scripts", "tests"],
                          cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    result["undef_scan"] = {"code": scan.returncode, "tail": scan.stdout.strip().splitlines()[-15:]}
    print("未定義名稱：", scan.returncode, flush=True)

    boots = [boot(py, root, env, p, log) for p in PROFILES]
    result["boot"] = [b for b in boots if b]
    print("三種設定起伺服器：", result["boot"] or "都 200", flush=True)

    running = {}
    script = str(root / "scripts" / "same_behavior.py")
    if not a.no_compare:
        unpack(repo, base, work / "base")
        both = ["--base", str(work / "base"), "--head", str(root)]
        extra = (["--tracks", a.tracks] if a.tracks else []) + (["--jobs", a.jobs] if a.jobs else []) + (["--new", a.new] if a.new else [])
        cached = ["--cache", str(repo / ".local" / "wave_gate" / "cache")] if a.cache else []  # 只給 compare；explore-compare 不快取
        running["compare"] = start([py, script, "compare", *both, "--tmp", str(work / "tmp" / "cmp"), *extra, *cached], root, env, out / "compare.txt")
        if not a.tracks:
            running["explore"] = start([py, script, "explore-compare", *both, "--tmp", str(work / "tmp" / "exp")], root, env, out / "explore.txt")
    if not a.no_suite:
        suite_env = {**env, "TIANXIA_DB": str(work / "tmp" / "suite.db")}
        running["suite"] = start([py, "-m", "pytest", "-q", "-n", "4", "-m", "slow or not slow", "-p", "no:cacheprovider", f"--junitxml={out / 'suite.xml'}"],
                                 root, suite_env, out / "suite.txt")

    started = time.monotonic()
    for key, (proc, f) in running.items():
        code = proc.wait()
        f.close()
        minutes = (time.monotonic() - started) / 60
        result[key] = {"code": code, "minutes_since_start": round(minutes, 1)}
        print(f"{key}：結束碼 {code}，開跑後 {minutes:.1f} 分鐘", flush=True)
    if "compare" in result:
        result["compare"]["red"] = red_lines(out / "compare.txt", r"不一樣|不同|DIFF|differ|失敗|Traceback|Error")
        result["compare"]["slowest"] = red_lines(out / "compare.txt", r"^最慢 ", 10)
    if "explore" in result:
        result["explore"]["red"] = red_lines(out / "explore.txt", r"不一樣|不同|DIFF|differ|失敗|Traceback|Error")
    if "suite" in result:
        result["suite"]["red"] = red_lines(out / "suite.txt", r"^(FAILED|ERROR) ")
        result["suite"]["tail"] = red_lines(out / "suite.txt", r" passed| failed", 2)
        result["suite"]["xml"] = str(out / "suite.xml")

    web = root / "scripts" / "webqa" / "gate.py"
    if a.web and web.exists():  # 上面全部等完才跑，不跟整套同時跑：同時跑的話畫面比對的雜訊多
        started = time.monotonic()
        proc, f = start([py, str(web), "--base", base, "--head", head, "--out", str(out / "web")], root,
                        {**env, "TIANXIA_DB": str(work / "tmp" / "web.db")}, out / "web.txt")
        code = proc.wait()
        f.close()
        result["web"] = {"ran": True, "code": code, "minutes": round((time.monotonic() - started) / 60, 1), "out": str(out / "web")}
        print(f"網頁比對：結束碼 {code}，{result['web']['minutes']} 分鐘", flush=True)
    else:
        result["web"] = {"ran": False, "why": "head 上沒有 scripts/webqa/gate.py" if a.web else "沒帶 --web"}
        print("網頁比對：沒跑，" + result["web"]["why"], flush=True)

    subprocess.call(["git", "worktree", "remove", "--force", str(root)], cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(work, ignore_errors=True)

    green = scan.returncode == 0 and not result["boot"] and all(result[k]["code"] == 0 for k in running) and (not result["web"]["ran"] or result["web"]["code"] == 0)
    result["green"] = green
    result["finished"] = f"{dt.datetime.now():%m-%d %H:%M}"
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "done").write_text("green\n" if green else "red\n", encoding="utf-8")
    print("全綠" if green else "有紅", out, flush=True)
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
