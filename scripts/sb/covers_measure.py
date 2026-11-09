"""各軌 covers 的量法（測試流程優化第 109 批；第 107 批的一次性腳本改成可重跑的工具）。

  python scripts/sb/covers_measure.py measure [<根>] --out <資料夾> [--profiles season21,week7,test] [--jobs 4] [--tracks a,b]
      每軌每設定一個子行程（PYTHONHASHSEED=0，TIANXIA_DB、--tmp、--db 都在 --out 底下），sys.monitoring 的 PY_START 從 Scenario.run 開始記
      <根>/tianxia/ 底下（不含 tests/）被叫到的函式（檔:qualname:首行），audit hook 記讀到的 <根>/web/ 檔；寫 <out>/<設定>/<軌>.json。
  python scripts/sb/covers_measure.py analyze <資料夾> [--root <根>] [--threshold 0.9]
      共同組照設定各算一次（同一設定裡被 ≥ 門檻比例的軌碰到的函式）；每軌 covers＝各設定扣掉共同組後碰到的包的聯集 ∪ 讀到的 web/<包>.js|css 的包。
      印分佈表，寫 <資料夾>/covers.json；共同組裡 ALWAYS_TRACKS（同一設定）一軌都沒碰到的包函式不是 0 就結束碼 1（共同組的改動只靠 ALWAYS 抓）。
  python scripts/sb/covers_measure.py write <資料夾>
      照 covers.json 改寫 scripts/sb/base.py 與 scripts/sb/tracks/*.py 每一處 register_track 的 covers=（有就取代、沒有就加；CRLF 照原樣）。
  python scripts/sb/covers_measure.py verify [<根>] --out <資料夾> --mutate <檔> <舊> <新> --covers <包> [--profiles season21] [--jobs 4]
      反向驗：<根> 的 HEAD 用 git archive 解一份當 base（解過就重用），抄一份改那一句當 head，跑 same_behavior compare 全軌（--no-bots、
      base 那一側開 --cache，第二對起不重跑）；印 --covers 挑到的軌紅了幾軌、沒挑到的軌紅了哪幾軌。沒挑到的有紅、或挑到的一軌都沒紅，結束碼 1。
第 112 批：measure 不帶 --tracks 時連 harness.BOT_SEATS 每個座位、它登記的每種設定一起量（same_behavior bots，從 runner 被叫的那一刻開始記），
寫 <out>/<設定>/bots_<座位>.json；--seats a,b 只量座位（軌的那一份要先量好）。analyze 的座位 covers＝扣掉同一設定**軌**的共同組之後碰到的包
（座位不參與算共同組），寫進 covers.json 的 bots:<座位>；write 連 register_bots 的 covers= 一起改（--seats-only 只改座位）；
verify --bots 改一句之後每個座位 base／head 各跑一次，harness.pick_seats 挑到的要紅、沒挑到的不准紅。
量完記得刪 <out> 底下的 *.txt 與 tmp/（一軌輸出約 1 MB）。
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures
import io
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tarfile
import time
from collections import Counter
from pathlib import Path

SB = Path(__file__).resolve().parent
SCRIPTS = SB.parent
REPO = SCRIPTS.parent
THRESHOLD = 0.9  # 共同組的門檻（第 109 批：試過 1.0、0.95、0.9、0.8、0.7、0.5，0.9 起 ALWAYS 不變量守得住、0.5 破）
TABLE_THRESHOLDS = (1.0, 0.95, 0.9, 0.8, 0.7, 0.5)


# ── 純函式（tests/core/test_same_behavior_covers.py 直接叫）──
def package_of(fn: str) -> str | None:
    """「features/<包>/x.py:qualname:行」→ 包；不在包裡回 None。"""
    parts = fn.split(":", 1)[0].split("/")
    return parts[1] if parts[0] == "features" and len(parts) > 2 else None


def web_packages(webs, packages: set[str]) -> set[str]:
    """讀到的 web 檔（相對 web/）裡，直下的 <包>.js|css 的包。"""
    out = set()
    for w in webs:
        if "/" not in w and w.endswith((".js", ".css")) and w.rsplit(".", 1)[0] in packages:
            out.add(w.rsplit(".", 1)[0])
    return out


def common_set(rows: dict[str, dict], threshold: float) -> set[str]:
    """一種設定裡被 ≥ threshold 比例的軌碰到的函式。"""
    n = len(rows)
    count = Counter(f for r in rows.values() for f in set(r["fns"]))
    return {f for f, c in count.items() if n and c >= threshold * n}


def track_covers(by_profile: dict[str, dict[str, dict]], packages: set[str], threshold: float) -> dict[str, list[str]]:
    """每軌 covers：各設定扣掉那一設定的共同組之後碰到的包的聯集，再併上讀到的 web/<包>.js|css 的包。"""
    out: dict[str, set[str]] = {}
    for rows in by_profile.values():
        common = common_set(rows, threshold)
        for t, r in rows.items():
            got = out.setdefault(t, set())
            got |= {p for f in r["fns"] if f not in common and (p := package_of(f)) in packages}
            got |= web_packages(r.get("web", ()), packages)
    return {t: sorted(v) for t, v in sorted(out.items())}


def seat_covers(by_profile: dict[str, dict[str, dict]], seats_by_profile: dict[str, dict[str, dict]], packages: set[str], threshold: float) -> dict[str, list[str]]:
    """第 112 批：每個假人座位的 covers：它跑的每種設定扣掉那一設定**軌**的共同組（座位不參與算共同組，門檻同一個）之後碰到的包的聯集，
    再併上讀到的 web/<包>.js|css 的包。那一設定沒有軌的量測就不扣（measure 會先擋）。"""
    out: dict[str, set[str]] = {}
    for profile, seats in seats_by_profile.items():
        common = common_set(by_profile.get(profile, {}), threshold)
        for s, r in seats.items():
            got = out.setdefault(s, set())
            got |= {p for f in r["fns"] if f not in common and (p := package_of(f)) in packages}
            got |= web_packages(r.get("web", ()), packages)
    return {s: sorted(v) for s, v in sorted(out.items())}


def always_gaps(by_profile: dict[str, dict[str, dict]], threshold: float, always) -> list[str]:
    """共同組裡的包函式，同一設定的 ALWAYS 軌一軌都沒碰到的（「設定 函式」）。"""
    gaps = []
    for profile, rows in sorted(by_profile.items()):
        hit = set().union(*(set(rows[t]["fns"]) for t in always if t in rows)) if any(t in rows for t in always) else set()
        gaps += [f"{profile} {f}" for f in sorted(common_set(rows, threshold)) if package_of(f) and f not in hit]
    return gaps


# ── measure ──
def _child(out_json: Path, argv: list[str]) -> None:
    """子行程：same_behavior.main(["run", …])，結束時（run 最後走 os._exit）寫函式集。"""
    t0 = time.perf_counter()
    sys.path.insert(0, str(SCRIPTS))
    import same_behavior  # noqa: E402
    from sb import base  # noqa: E402

    root = Path(argv[1]).resolve()
    prefix = str((root / "tianxia").resolve()).lower() + os.sep
    webprefix = str((root / "web").resolve()).lower() + os.sep
    fns: set[str] = set()
    webs: set[str] = set()
    on = [False]
    mon = sys.monitoring
    tool = mon.PROFILER_ID
    mon.use_tool_id(tool, "covers")

    def on_start(code, offset):
        f = code.co_filename.lower()
        if on[0] and f.startswith(prefix):
            rel = f[len(prefix):].replace(os.sep, "/")
            if "/tests/" not in rel and not rel.startswith("tests/"):
                fns.add(f"{rel}:{code.co_qualname}:{code.co_firstlineno}")
        return mon.DISABLE

    mon.register_callback(tool, mon.events.PY_START, on_start)

    def audit(event, args):
        if on[0] and event == "open" and args and isinstance(args[0], (str, os.PathLike)):
            f = os.path.abspath(os.fspath(args[0])).lower()
            if f.startswith(webprefix):
                webs.add(f[len(webprefix):].replace(os.sep, "/"))

    sys.addaudithook(audit)
    orig_run = base.Scenario.run
    from sb import harness  # noqa: E402

    def start() -> None:
        on[0] = True
        mon.set_events(tool, mon.events.PY_START)

    def run(self, *a, **k):
        start()
        return orig_run(self, *a, **k)

    base.Scenario.run = run
    # 第 112 批：座位的 runner 自己 import tianxia、自己 load_content；軌的這兩件事在 Scenario.__init__（import server）、開始記之前做完。
    # 座位照軌的起點：runner 叫 _setup_child 之後先 import server、照 runner 的讀法 load_content 一次，這一段 PY_START 照樣觸發但不記、
    # 回 DISABLE（之後 runner 再 load_content 也不會再記）；做完才開始記。runner 沒叫 _setup_child 的，從 runner 被叫的那一刻記。
    for seat, (profiles, runner) in list(harness.BOT_SEATS.items()):
        home = sys.modules[runner.__module__]
        real_setup = getattr(home, "_setup_child", None)

        def seat_setup(root_, profile, db, _real=real_setup):
            _real(root_, profile, db)
            mon.set_events(tool, mon.events.PY_START)  # on[0] 還是 False：觸發的都不記、DISABLE
            import server  # noqa: F401, PLC0415  同 Scenario.__init__
            from tianxia.content import load_content  # noqa: PLC0415

            load_content(Path(root_) / "content", profile=profile)
            on[0] = True

        def seat_run(*a, _runner=runner, _home=home, _setup=seat_setup, _real=real_setup, **k):
            if _real is None:
                start()
            else:
                _home._setup_child = _setup
            return _runner(*a, **k)

        harness.BOT_SEATS[seat] = (profiles, seat_run)
    real_exit = os._exit

    def dump_exit(code):
        out_json.write_text(json.dumps({"fns": sorted(fns), "web": sorted(webs), "secs": round(time.perf_counter() - t0, 2)}, ensure_ascii=False), encoding="utf-8")
        real_exit(code)

    os._exit = dump_exit
    sys.exit(same_behavior.main(argv))


def _track_names(only: str) -> list[str]:
    sys.path.insert(0, str(SCRIPTS))
    from sb import harness  # noqa: E402

    if not harness.TRACK_NAMES:
        harness.load_tracks()
    return [t for t in only.split(",") if t] or list(harness.TRACK_NAMES)


SEAT_PREFIX = "bots_"  # 第 112 批：座位量到的寫 <設定>/bots_<座位>.json（軌名沒有這個開頭），covers.json 的鍵是 bots:<座位>


def _seat_profiles(only: str) -> dict[str, tuple[str, ...]]:
    """座位 → 登記的設定（harness.BOT_SEATS）；only 給了只留那幾個（不認得的座位丟 SystemExit）。"""
    _track_names("")
    from sb import harness  # noqa: E402

    want = [s for s in only.split(",") if s] or list(harness.BOT_SEATS)
    unknown = sorted(set(want) - set(harness.BOT_SEATS))
    if unknown:
        raise SystemExit(f"沒有這幾個座位：{unknown}（登記的是 {list(harness.BOT_SEATS)}）")
    return {s: harness.BOT_SEATS[s][0] for s in want}


def measure(root: Path, out: Path, profiles: list[str], jobs: int, only: str = "", seats_only: str | None = None) -> int:
    """only（--tracks）給了只量那幾軌、不量座位（照舊）；seats_only（--seats）給了只量那幾個座位（同一設定軌的那一份要已經量好，共同組靠它）；
    兩個都沒給：全部的軌加上全部的座位（第 112 批）。"""
    tracks = [] if seats_only is not None and not only else _track_names(only)
    seats = _seat_profiles(seats_only or "") if (seats_only is not None or not only) else {}
    tmp = out / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8", "TIANXIA_DB": str(tmp / "x.db")}
    bad = []
    for profile in profiles:
        folder = out / profile
        folder.mkdir(parents=True, exist_ok=True)
        here = [s for s, ps in seats.items() if profile in ps]
        if here and not tracks and not any(j for j in folder.glob("*.json") if not j.name.startswith(SEAT_PREFIX)):
            print(f"{profile}：沒有軌的量測（{folder}），座位的共同組算不出來；先量軌", flush=True)
            return 2
        started = time.time()

        def one(job: tuple[str, str]) -> tuple[str, int]:
            kind, name = job
            stem = f"{SEAT_PREFIX}{name}" if kind == "seat" else name
            argv = (["bots", str(root), profile, str(folder / f"{stem}.txt"), "--tmp", str(tmp / f"{profile}_{stem}"), "--seats", name] if kind == "seat" else
                    ["run", str(root), profile, str(folder / f"{stem}.txt"), "--tmp", str(tmp), "--track", name, "--db", str(tmp / f"{profile}_{name}.db")])
            with (folder / f"{stem}.log").open("w", encoding="utf-8") as fh:
                code = subprocess.run([sys.executable, str(Path(__file__).resolve()), "_child", str(folder / f"{stem}.json"), *argv],
                                      env=env, stdout=fh, stderr=subprocess.STDOUT).returncode
            return stem, code

        jobs_list = [("seat", s) for s in here] + [("track", t) for t in tracks]  # 座位慢（一格 20～45 秒），排前面免得拖尾
        with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
            failed = [(t, c) for t, c in pool.map(one, jobs_list) if c or not (folder / f"{t}.json").exists()]
        bad += [(profile, t, c) for t, c in failed]
        secs = [json.loads((folder / f"{t}.json").read_text(encoding="utf-8"))["secs"] for t in tracks if (folder / f"{t}.json").exists()]
        seat_secs = {s: json.loads(p.read_text(encoding="utf-8"))["secs"] for s in here if (p := folder / f"{SEAT_PREFIX}{s}.json").exists()}
        print(f"{profile}：{len(tracks)} 軌、座位 {seat_secs or '無'}，牆鐘 {time.time() - started:.1f} 秒，一軌中位數 {statistics.median(secs) if secs else 0:.2f} 秒、"
              f"合計 {sum(secs):.0f} 秒，沒量到 {failed or '無'}", flush=True)
    return 1 if bad else 0


# ── analyze ──
def _load(folder: Path, seats: bool = False) -> dict[str, dict[str, dict]]:
    """<設定>/<軌>.json（seats=True 改讀 <設定>/bots_<座位>.json，鍵是座位名）；沒有的設定不列。"""
    out = {}
    for d in sorted(folder.iterdir()):
        if not d.is_dir() or d.name == "tmp":
            continue
        rows = {(j.stem[len(SEAT_PREFIX):] if seats else j.stem): json.loads(j.read_text(encoding="utf-8"))
                for j in sorted(d.glob("*.json")) if j.name.startswith(SEAT_PREFIX) == seats}
        if rows:
            out[d.name] = rows
    return out


def _packages(root: Path) -> set[str]:
    return {p.name for p in (root / "tianxia" / "features").iterdir() if p.is_dir() and (p / "__init__.py").exists()}


def analyze(folder: Path, root: Path, threshold: float) -> int:
    sys.path.insert(0, str(SCRIPTS))
    from sb import harness  # noqa: E402

    by_profile = _load(folder)
    packages = _packages(root)
    print("設定：" + "、".join(f"{p} {len(r)} 軌" for p, r in by_profile.items()) + f"；包 {len(packages)} 個")
    print("| 門檻 | 共同組函式（其中包裡的，各設定） | 每軌包數中位數／最少／最多 | 共同組裡 ALWAYS 沒碰到的包函式 |")
    print("|---|---|---|---|")
    for th in sorted(set(TABLE_THRESHOLDS) | {threshold}, reverse=True):
        commons = {p: common_set(rows, th) for p, rows in by_profile.items()}
        sizes = [len(v) for v in track_covers(by_profile, packages, th).values()]
        mark = "**" if th == threshold else ""
        common_text = "、".join(f"{p} {len(c)}（{sum(1 for f in c if package_of(f))}）" for p, c in commons.items())
        print(f"| {mark}{th:.0%}{mark} | {common_text} | {statistics.median(sizes)}／{min(sizes)}／{max(sizes)} | {len(always_gaps(by_profile, th, harness.ALWAYS_TRACKS))} |")
    covers = track_covers(by_profile, packages, threshold)
    per_pkg = Counter(p for v in covers.values() for p in v)
    print(f"\n門檻 {threshold:.0%} 每包幾軌碰到（共 {len(covers)} 軌）：" + " ".join(f"{p}:{per_pkg.get(p, 0)}" for p in sorted(packages)))
    empty = [t for t, v in covers.items() if not v]
    if empty:
        print(f"covers 是空的軌：{empty}（write 會拒絕）")
    seat_rows = _load(folder, seats=True)
    seats = seat_covers(by_profile, seat_rows, packages, threshold)
    if seats:
        print("座位（扣掉同一設定軌的共同組）：" + "；".join(f"{s} {'、'.join(sorted(p for p, r in seat_rows.items() if s in r))} {len(v)} 包 {','.join(v)}"
                                          for s, v in seats.items()))
        if [s for s, v in seats.items() if not v]:
            print(f"covers 是空的座位：{[s for s, v in seats.items() if not v]}（write 會拒絕）")
    covers.update({f"bots:{s}": v for s, v in seats.items()})
    (folder / "covers.json").write_text(json.dumps(covers, ensure_ascii=False, indent=1), encoding="utf-8")
    gaps = always_gaps(by_profile, threshold, harness.ALWAYS_TRACKS)
    if gaps:
        print(f"共同組裡 ALWAYS 沒碰到的包函式 {len(gaps)} 個（改到它們的話沒有一軌挑得到）：", gaps[:20])
        return 1
    return 0


# ── write ──
def _literal(packages: list[str], indent: int) -> str:
    chunks = [", ".join(f'"{p}"' for p in packages[i:i + 10]) for i in range(0, len(packages), 10)]
    return "covers=(" + (",\n" + " " * (indent + 8)).join(chunks) + ("," if len(packages) == 1 else "") + ")"


REWRITE_CALLS = {"register_track": "", "register_bots": "bots:"}  # 函式 → covers.json 的鍵前綴（第 112 批 register_bots 的鍵是 bots:<座位>）


def rewrite_covers(text: str, covers: dict[str, list[str]], funcs: tuple[str, ...] = tuple(REWRITE_CALLS)) -> tuple[str, list[str]]:
    """一個檔（\\n 換行）裡每一處 register_track（與 register_bots，第 112 批）的 covers= 換成量到的（沒有就加在最後一個參數後面，縮排對齊左括號）；
    covers= 前面整行的註解拿掉（舊的手寫理由）。funcs 只改這幾種。回新字與改到的鍵（covers.json 的鍵）。"""
    raw = text.encode("utf-8")
    starts = [0]
    for line in raw.split(b"\n")[:-1]:
        starts.append(starts[-1] + len(line) + 1)

    def at(line: int, col: int) -> int:
        return starts[line - 1] + col

    tree = ast.parse(text)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", None) in funcs]
    done = []
    for node in sorted(calls, key=lambda n: (n.end_lineno, n.end_col_offset), reverse=True):
        name = REWRITE_CALLS[node.func.id] + node.args[0].value
        indent = node.col_offset + len(node.func.id) + 1
        if not covers.get(name):
            raise SystemExit(f"{'軌' if node.func.id == 'register_track' else '座位'} {name} 沒有量到的 covers（covers.json 沒有或是空的）")
        kw = next((k for k in node.keywords if k.arg == "covers"), None)
        if kw is not None:
            lit = _literal(covers[name], kw.col_offset)
            prev = max((n.end_lineno for n in [*node.args, *node.keywords] if n is not kw and n.end_lineno < kw.lineno), default=node.lineno)
            raw = raw[:at(kw.lineno, kw.col_offset)] + lit.encode("utf-8") + raw[at(kw.value.end_lineno, kw.value.end_col_offset):]
            for ln in range(kw.lineno - 1, prev, -1):  # covers= 那一行上面、前一個參數之後整行的註解
                begin, end = starts[ln - 1], starts[ln]
                if raw[begin:end].strip().startswith(b"#"):
                    raw = raw[:begin] + raw[end:]
        else:
            pos = at(node.end_lineno, node.end_col_offset) - 1
            assert raw[pos:pos + 1] == b")", (name, raw[pos - 5:pos + 2])
            raw = raw[:pos] + b",\n" + b" " * indent + _literal(covers[name], indent).encode("utf-8") + raw[pos:]
        done.append(name)
    out = raw.decode("utf-8")
    ast.parse(out)
    return out, done


def write(folder: Path, seats_only: bool = False) -> int:
    """seats_only（--seats-only，第 112 批）：只改 register_bots，各軌的 covers= 不動。"""
    covers = json.loads((folder / "covers.json").read_text(encoding="utf-8"))
    funcs = ("register_bots",) if seats_only else tuple(REWRITE_CALLS)
    done = []
    for path in [SB / "base.py", *sorted((SB / "tracks").glob("*.py"))]:
        data = path.read_bytes()
        crlf = b"\r\n" in data
        text = data.decode("utf-8").replace("\r\n", "\n")
        new, names = rewrite_covers(text, covers, funcs)
        done += names
        if new != text:
            path.write_bytes((new.replace("\n", "\r\n") if crlf else new).encode("utf-8"))
    keys = {k for k in covers if seats_only <= k.startswith("bots:")}
    print(f"改寫 {len(done)} 處 {'／'.join(funcs)}；covers.json 有、檔裡沒登記的：{sorted(keys - set(done)) or '無'}")
    return 0


# ── verify ──
def _unpack(root: Path, dest: Path) -> None:
    raw = subprocess.run(["git", "archive", "--format=tar", "HEAD", "--", ".", ":(exclude)docs"], cwd=root, capture_output=True, check=True).stdout  # docs 不跑，省一半
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        tar.extractall(dest, filter="data")


LINE = re.compile(r"^(\S+)\s+(\S+)\s+整段 .*｜head \S+ (一樣|不一樣)")


def verify(root: Path, out: Path, mutate: tuple[str, str, str], package: str, profiles: list[str], jobs: int) -> int:
    sys.path.insert(0, str(SCRIPTS))
    from sb import harness  # noqa: E402

    if not harness.TRACK_NAMES:
        harness.load_tracks()
    rel, old, new = mutate
    base = out / "base"
    if not base.exists():
        _unpack(root, base)
    head = out / "head"
    shutil.rmtree(head, ignore_errors=True)
    shutil.copytree(base, head)
    path = head / rel
    text = path.read_bytes().decode("utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"{rel} 裡「{old}」不是剛好一處（{text.count(old)} 處）")
    path.write_bytes(text.replace(old, new).encode("utf-8"))
    tmp = out / "tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8", "TIANXIA_DB": str(out / "x.db")}
    started = time.time()
    proc = subprocess.run([sys.executable, str(SCRIPTS / "same_behavior.py"), "compare", "--base", str(base), "--head", str(head), "--tmp", str(tmp),
                           "--profiles", ",".join(profiles), "--no-bots", "--jobs", str(jobs), "--cache", str(out / "cache")],
                          env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (out / "verify.txt").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    red = sorted({m.group(1) for line in proc.stdout.splitlines() if (m := LINE.match(line)) and m.group(3) == "不一樣"})
    seen = {m.group(1) for line in proc.stdout.splitlines() if (m := LINE.match(line))}
    picked = harness.pick_tracks([package])
    missing = sorted(set(harness.TRACK_NAMES) - seen)
    picked_red = [t for t in picked if t in red]
    stray = [t for t in red if t not in picked]
    print(f"改 {rel}「{old}」→「{new}」，--covers {package} 挑到 {len(picked)} 軌（{','.join(picked)}）：紅 {len(picked_red)} 軌 {picked_red}；"
          f"沒挑到的紅 {stray or '無'}；{time.time() - started:.0f} 秒" + (f"；沒有結果的軌 {missing}" if missing else ""), flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(head, ignore_errors=True)
    return 1 if stray or not picked_red or missing else 0


def verify_bots(root: Path, out: Path, mutate: tuple[str, str, str], package: str, jobs: int) -> int:
    """第 112 批 verify --bots：每個座位、它登記的每種設定，base（解過就重用，base 的輸出也留著重用）與改那一句的 head 各跑一次 bots，逐位元組比。
    harness.pick_seats([包], []) 挑到的座位至少一格紅、沒挑到的一格都不准紅，不然結束碼 1。"""
    seats = _seat_profiles("")
    from sb import harness  # noqa: E402

    rel, old, new = mutate
    base = out / "base"
    if not base.exists():
        _unpack(root, base)
    head = out / "head"
    shutil.rmtree(head, ignore_errors=True)
    shutil.copytree(base, head)
    path = head / rel
    text = path.read_bytes().decode("utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"{rel} 裡「{old}」不是剛好一處（{text.count(old)} 處）")
    path.write_bytes(text.replace(old, new).encode("utf-8"))
    tmp = out / "tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    keep = out / "bots_base"
    keep.mkdir(exist_ok=True)
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8", "TIANXIA_DB": str(out / "x.db")}
    cells = [(s, p) for s, ps in seats.items() for p in ps]

    def one(job: tuple[str, str, str]) -> None:
        side, s, p = job
        dest = (keep if side == "base" else tmp) / f"{s}_{p}.txt"
        if side == "base" and dest.exists():
            return
        with (tmp / f"{side}_{s}_{p}.log").open("w", encoding="utf-8") as fh:
            code = subprocess.run([sys.executable, str(SCRIPTS / "same_behavior.py"), "bots", str(base if side == "base" else head), p, str(dest),
                                   "--tmp", str(tmp / f"{side}_{s}_{p}"), "--seats", s], env=env, stdout=fh, stderr=subprocess.STDOUT).returncode
        if code:
            raise RuntimeError(f"bots {side} {s} {p} 結束碼 {code}（{tmp / f'{side}_{s}_{p}.log'}）")

    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
        list(pool.map(one, [(side, s, p) for side in ("base", "head") for s, p in cells]))
    red = sorted({s for s, p in cells if (keep / f"{s}_{p}.txt").read_bytes() != (tmp / f"{s}_{p}.txt").read_bytes()})
    lines = [f"假人 {s} {p} {'一樣' if (keep / f'{s}_{p}.txt').read_bytes() == (tmp / f'{s}_{p}.txt').read_bytes() else '不一樣'}" for s, p in cells]
    picked = harness.pick_seats([package], [])
    picked_red = [s for s in picked if s in red]
    stray = [s for s in red if s not in picked]
    (out / "verify_bots.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"改 {rel}「{old}」→「{new}」，--bot-covers {package} 挑到座位 {','.join(picked)}：紅 {picked_red}；沒挑到的紅 {stray or '無'}；"
          f"{time.time() - started:.0f} 秒", flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(head, ignore_errors=True)
    return 1 if stray or not picked_red else 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "_child":
        _child(Path(args[1]), args[2:])
        return 0
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("root", nargs="?", default=str(REPO))
    m.add_argument("--out", required=True)
    m.add_argument("--profiles", default="season21,week7,test")
    m.add_argument("--jobs", type=int, default=4)
    m.add_argument("--tracks", default="")
    m.add_argument("--seats", default=None, help="第 112 批：只量這幾個假人座位（逗號隔開；同一設定軌的那一份要已經量好）")
    n = sub.add_parser("analyze")
    n.add_argument("folder")
    n.add_argument("--root", default=str(REPO))
    n.add_argument("--threshold", type=float, default=THRESHOLD)
    w = sub.add_parser("write")
    w.add_argument("folder")
    w.add_argument("--seats-only", action="store_true", help="第 112 批：只改 register_bots 的 covers=，各軌不動")
    v = sub.add_parser("verify")
    v.add_argument("root", nargs="?", default=str(REPO))
    v.add_argument("--out", required=True)
    v.add_argument("--mutate", nargs=3, required=True, metavar=("檔", "舊", "新"))
    v.add_argument("--covers", required=True)
    v.add_argument("--profiles", default="season21")
    v.add_argument("--jobs", type=int, default=4)
    v.add_argument("--bots", action="store_true", help="第 112 批：只驗假人座位（每個座位它登記的設定，bots base／head 逐位元組比；--profiles 不看）")
    a = ap.parse_args(args)
    if a.cmd == "measure":
        return measure(Path(a.root).resolve(), Path(a.out).resolve(), [p for p in a.profiles.split(",") if p], a.jobs, a.tracks, a.seats)
    if a.cmd == "analyze":
        return analyze(Path(a.folder).resolve(), Path(a.root).resolve(), a.threshold)
    if a.cmd == "write":
        return write(Path(a.folder).resolve(), a.seats_only)
    if a.bots:
        return verify_bots(Path(a.root).resolve(), Path(a.out).resolve(), tuple(a.mutate), a.covers, a.jobs)
    return verify(Path(a.root).resolve(), Path(a.out).resolve(), tuple(a.mutate), a.covers, [p for p in a.profiles.split(",") if p], a.jobs)


if __name__ == "__main__":
    sys.path[0] = str(SCRIPTS)  # 直接跑這支時 sys.path[0] 是 scripts/sb：換成 scripts，sb 裡的 base、cache 才不會被當成頂層模組
    sys.exit(main())
