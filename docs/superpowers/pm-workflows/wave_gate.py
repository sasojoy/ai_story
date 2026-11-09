"""一波的總閘門（企劃者 2026-11-06「火力全開」「減少測試驗收的頻率」「一次性多改幾個功能再一起全部合併測試」）。

開發不再逐批比對、逐批合併；一波的每條線合起來之後，這裡一次驗完，不花 token：
1. 未定義名稱掃一次（tianxia、server.py、scripts、tests）。
2. 三種設定（season21、week7、不帶）各起一次伺服器，GET / 要 200。
3. --head 跑 pytest（-n 4，每條測試的秒數在 suite.xml〔junit〕），等它跑完才開比對（第 107 批：不再跟比對同時跑）。
   預設跑不含 slow 的一趟，再跑一條冒煙（SMOKE，整季機器人一個種子，不 -n，smoke.xml）；--full 才跑整套含 slow（不另跑冒煙）。
4. same_behavior、explore-compare：--base 對 --head（兩者同時跑）。每軌每設定的秒數在 compare.txt，最慢十格進 result.json。
   不帶 --changed：所有軌、三種設定、--crossover（跟以前一樣）。--changed：照 decide() 挑（下面），只比改到的包走到的軌。
5. 帶 --web 才跑（--changed 時 decide 說網頁有動也跑）：等前面都跑完叫 head 上的 scripts/webqa/gate.py --base <sha> --head <sha> --out <結果夾>/web，
   結束碼 0 才綠、其他算紅，輸出在 web.txt。head 上沒有那個檔（第 77 批順延）就印一行、result.json 的 web 寫沒跑，不擋。
   --changed 時把 decide 的 web_files 原樣交給 --changed-files（只走對照表上碰得到的回合；對不到的檔怎麼辦由 gate.py 定）；網頁要開的原因不只 web/ 的檔
   （server.py 回頁面的行、別處的 css／html、scripts/webqa）就不交、全回合；核心退回全軌只管比對的軌，不拉網頁全回合（第 109 批）；--full 全回合。帶 --new 時原樣轉給 gate.py --new（N 波）。
   --web-jobs N 轉成 gate.py --jobs N（O 波起工作流程的閘門帶 --changed --web-jobs 4：八回合並行約 35 分，不帶要一回合接一回合跑）。

用法（Windows 上用 venv 的 python）：
  python docs/superpowers/pm-workflows/wave_gate.py --base <sha> --head <sha> [--name 波A] [--changed | --full] [--dry-run]
      [--no-suite] [--no-compare] [--web] [--cache] [--tracks a,b]
--changed（第 107 批）：照 git diff base..head 決定比哪幾軌、哪幾種設定、要不要半舊半新與網頁（decide()，拿不準一律往寬：退回全軌）。
  第 109 批：只改軌檔（scripts/sb/tracks/<軌>.py）是 mode "tracks"，只比那個檔登記的軌＋import 它的軌檔登記的軌、三種設定、半舊半新；
  tianxia/core/ 直下的 .md、.gitattributes 不比。
  第 112 批：tianxia/core/tuning/<包>.py 照包挑（核心、共用層、舊模組或 server.py 也讀 Config.<包> 就照舊全軌，別包讀的一起挑）；
  packages 模式另把包交給 compare --bot-covers，假人座位也照 register_bots 的 covers 挑（ALWAYS、座位名在軌裡、covers 有交集，聯集，只會多跑）；
  head 的 same_behavior.py 沒有 --bot-covers（舊的 head）或 --tracks 蓋過時照舊。--dry-run 多印 bot_covers、seats。
--full：全軌三設定＋--crossover＋整套含 slow＋--web 全回合（上 main 前、每日）。--changed 與 --full 不能一起帶；--tracks 照舊蓋過挑軌。
--dry-run：只印 decide 的 JSON 與會挑到的軌，不開工作樹、不跑任何東西、不碰結果夾；挑軌用這支腳本所在那一份程式的 same_behavior.py pick
（舊波的 head 上沒有 covers），所以拿得來對舊波的 diff 跑。
--cache 預設關：只給 compare 開，base 的結果留在 <主要 clone>/.local/wave_gate/cache（scripts/sb/cache.py）。同一波修正後重跑才省；要省到第二次，第一次就要帶
（第一次全沒命中，跑的跟不帶一樣、只多存檔）。進 develop、上 main 的那一次不開：鍵漏掉相依會假綠。
結果在 <主要 clone>/.local/wave_gate/<head 前 8 碼>/：gate.log、result.json、done（最後才寫，等它就好）。
result.json 另有 decision（怎麼決定的、實際挑到的軌與設定）、concurrent_gates（開跑當下別的還沒寫 done 的閘門數）、
slow_unmarked（不含 slow 的那些裡跑了 1 秒以上的，只列不紅）。
結束碼 0 全綠、1 有紅。不推任何東西、不改 verified.txt（全面檢查的基準由 PM 記）。

紅了怎麼找：result.json 寫哪幾段紅、紅的軌與失敗的測試；比對紅了就用那一軌（--tracks）對每條線的 head 各比一次，看是哪一條線。
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
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
import xml.etree.ElementTree as ET
from pathlib import Path

FLAGS = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
PROFILES = ("season21", "week7", "")  # 空字串＝不帶 TIANXIA_PROFILE（server.py 照舊套 season21）
BOOT_SECONDS = 180
SMOKE = "tests/season/test_real_content.py::test_bot_plays_a_full_season[1]"  # 預設模式的冒煙（slow，整季機器人一個種子）
SB_PROFILES = ("season21", "week7", "test")  # same_behavior 的設定（scripts/sb/harness.PROFILES）
SLOW_SECONDS = 1.0  # 手冊：單一條超過一秒的要標 slow

# ── decide：改到哪些、要跑什麼（純函式，測試直接叫：tests/core/test_same_behavior_gate.py）──
FULL_FILES = ("server.py", "pyproject.toml", "scripts/same_behavior.py")  # 改了退回全軌
FULL_PREFIXES = ("tianxia/core/", "scripts/sb/", "tests/fixtures/content/")
SKIP_PREFIXES = ("docs/", "tests/", ".claude/", ".github/", "scripts/webqa/")  # 不比（tests/fixtures/content/ 先被上面接走）
WEEK7_WORDS = re.compile(r"season_one|season_days|week7|timetable|calendar|decisive_from_week|battle_from_week|season_scale|profile")
CROSS_WORDS = re.compile(r"Field\(|BaseModel|json_schema_extra|SCHEMA_VERSION")
CROSS_FILES = {"state.py", "models.py", "world_state.py", "database.py", "sqlite_world.py"}
PAGE_WORDS = re.compile(r"HTMLResponse|FileResponse|text/html|<[a-z]|static")


def _changed_lines(diff_text: str) -> dict[str, list[str]]:
    """git diff -U0 的 +/- 行，照檔分（--- /+++ 那兩行不算；刪掉的檔記在 a/ 的名字）。"""
    out: dict[str, list[str]] = {}
    current = ""
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            m = re.match(r'diff --git "?a/(.+?)"? "?b/(.+?)"?$', line)
            current = m.group(2) if m else ""
            out.setdefault(current, [])
        elif line.startswith(("+++", "---")):
            continue
        elif line.startswith(("+", "-")) and current:
            out[current].append(line[1:])
    return out


def _load_test_for(head_root: Path):
    """head 的 scripts/test_for.py（核心、共用層的名單只有一份，不另寫解析）；沒有那個檔回 None。"""
    path = head_root / "scripts" / "test_for.py"
    if not path.exists():
        return None
    name = f"_wave_gate_test_for_{abs(hash(str(path.resolve())))}"
    if name not in sys.modules:  # dataclass 要在 sys.modules 裡找得到自己的模組
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def _alias_package(path: Path) -> str | None:
    """舊名別名檔（只有 sys.modules[__name__] = …）指到的包；不是別名回 None。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if "sys.modules[__name__]" not in text:
        return None
    found = set(re.findall(r"tianxia\.features\.(\w+)", text))
    return found.pop() if len(found) == 1 else None


def _tuning_readers(head_root: Path, package: str) -> tuple[set[str], list[str]]:
    """第 112 批：head 樹裡 tianxia/**/*.py（不含任何 tests/ 資料夾與這一包自己）與 server.py 讀 `config.<包>` 的人 →
    （別的包，包外不是包的檔）。只掃字面 `config.<包>`：`getattr(cfg, name)` 這種動態讀掃不到，認了。"""
    word = re.compile(rf"config\.{re.escape(package)}\b")
    others: set[str] = set()
    outside: list[str] = []
    paths = sorted((head_root / "tianxia").rglob("*.py")) if (head_root / "tianxia").is_dir() else []
    if (head_root / "server.py").exists():
        paths.append(head_root / "server.py")
    for path in paths:
        rel = path.relative_to(head_root).parts
        if "tests" in rel[:-1]:
            continue
        if rel[:2] == ("tianxia", "features") and len(rel) >= 4 and rel[2] == package:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not word.search(text):
            continue
        if rel[:2] == ("tianxia", "features") and len(rel) >= 4:
            others.add(rel[2])
        else:
            outside.append("/".join(rel))
    return others, outside


TRACK_FILE = re.compile(r"scripts/sb/tracks/(?!__init__\.py$)([^/]+)\.py")  # 一軌的檔（第 109 批）；tracks/__init__.py 與 sb 其他檔照舊退回全軌


def _track_graph(head_root: Path) -> tuple[dict[str, list[str]], dict[str, set[str]]] | None:
    """head 的 scripts/sb/tracks/*.py 用 AST 讀（不 import）：檔名 → 登記的軌名、檔名 → import 它的檔名。
    register_track 的第一個參數不是字面字串就回 None（量不出，退回全軌）。"""
    import ast
    folder = head_root / "scripts" / "sb" / "tracks"
    if not folder.is_dir():
        return None
    registered: dict[str, list[str]] = {}
    importers: dict[str, set[str]] = {}
    for path in sorted(folder.glob("*.py")):
        stem = path.stem
        tree = ast.parse(path.read_text(encoding="utf-8"))
        registered[stem] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "register_track":
                if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    return None
                registered[stem].append(node.args[0].value)
            mods = [node.module or ""] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names] if isinstance(node, ast.Import) else []
            for mod in mods:
                if mod.startswith("sb.tracks."):
                    importers.setdefault(mod.split(".")[2], set()).add(stem)
    return registered, importers


def _track_file_tracks(head_root: Path, stem: str, graph) -> list[str] | None:
    """改了 tracks/<stem>.py 影響的軌：它自己登記的＋直接或間接 import 它的檔登記的。head 上沒有這個檔或一軌都沒有回 None。"""
    if graph is None or stem not in graph[0]:
        return None
    registered, importers = graph
    seen, todo = {stem}, [stem]
    while todo:
        for user in importers.get(todo.pop(), ()):
            if user not in seen:
                seen.add(user)
                todo.append(user)
    hit = sorted({t for s in seen for t in registered.get(s, ())})
    return hit or None


def decide(files: list[str], diff_text: str, head_root: Path) -> dict:
    """改到的檔（git diff --name-only base..head）與 -U0 的 diff → 要跑什麼。拿不準一律往寬。
    mode：full（全軌，packages 是 None）、packages（只比 covers 碰得到這幾包的軌加上 ALWAYS_TRACKS；包是空的就只跑 ALWAYS_TRACKS；
    再併上 track_files_tracks）、tracks（第 109 批：只改了軌檔，只比 track_files_tracks、不加 ALWAYS）、none（不比）。"""
    lines = _changed_lines(diff_text)
    graph = _track_graph(head_root) if any(TRACK_FILE.fullmatch(f) for f in files) else None
    track_tracks: set[str] = set()
    test_for = _load_test_for(head_root)
    core = test_for.core_modules(head_root / "tianxia" / "core" / "__init__.py") if test_for else frozenset()
    shared = test_for.shared_modules(head_root / "tianxia" / "core" / "registry.py") if test_for else frozenset()
    features = head_root / "tianxia" / "features"
    full_reasons: list[str] = []
    reasons: list[str] = []
    packages: set[str] = set()
    compared: list[str] = []  # 會進比對的檔（設定與半舊半新只看這些檔的行）
    web = False
    web_other = False  # 網頁要開的原因不只 web/ 的檔：網頁回合不縮減
    web_files: list[str] = []
    for f in sorted(set(files)):
        parts = f.split("/")
        name = parts[-1]
        if f.startswith("web/"):
            web = True
            web_files.append(f)
            stem = name.rsplit(".", 1)[0]
            if name.endswith((".js", ".css")) and len(parts) == 2 and (features / stem).is_dir():
                packages.add(stem)
                reasons.append(f"{f}：包 {stem} 的網頁")
            else:
                reasons.append(f"{f}：網頁（facade、drape 那幾軌照跑）")
            compared.append(f)
            continue
        if name.endswith((".css", ".html")) and not f.startswith("docs/"):  # docs/ 的 html（架構圖）不上網頁
            web = web_other = True
        if f.startswith("scripts/webqa/"):
            web = web_other = True
            reasons.append(f"{f}：只開網頁")
            continue
        track_file = TRACK_FILE.fullmatch(f)
        if track_file:
            hit = _track_file_tracks(head_root, track_file.group(1), graph)
            if hit is None:
                full_reasons.append(f"{f}（軌檔，量不出登記的軌）")
            else:
                track_tracks.update(hit)
                reasons.append(f"{f}：軌檔，跑 {'、'.join(hit)}")
            compared.append(f)
            continue
        if parts[:2] == ["tianxia", "core"] and len(parts) == 3 and name.endswith(".md"):
            reasons.append(f"{f}：文件，不比")
            continue
        if parts[:3] == ["tianxia", "core", "tuning"] and len(parts) == 4 and name.endswith(".py") and name != "__init__.py" and (features / name[:-3]).is_dir():
            stem = name[:-3]  # 第 112 批：tuning/<包>.py 照包挑；核心、共用層、舊模組或 server.py 也讀 Config.<包> 就照舊全軌，別包讀就一起挑
            others, outside = _tuning_readers(head_root, stem)
            compared.append(f)
            if outside:
                full_reasons.append(f"{f}（核心也讀 Config.{stem}：{'、'.join(outside)}）")
                continue
            packages.update({stem, *others})
            reasons.append(f"{f}：tuning，照包 {stem}" + (f"（別包也讀：{'、'.join(sorted(others))}）" if others else ""))
            continue
        if f.startswith("tests/fixtures/content/") or f.startswith(FULL_PREFIXES) or f in FULL_FILES or re.fullmatch(r"requirements[\w-]*\.txt", f):
            full_reasons.append(f)
            compared.append(f)
            continue
        if f.startswith(SKIP_PREFIXES) or (len(parts) == 1 and name.endswith(".md")) or f in (".gitignore", ".gitattributes"):
            reasons.append(f"{f}：不比")
            continue
        if parts[0] == "scripts" and f not in FULL_FILES:
            reasons.append(f"{f}：包外工具，不比")
            continue
        if parts[0] == "content":
            full_reasons.append(f)
            compared.append(f)
            continue
        if parts[:2] == ["tianxia", "features"] and len(parts) >= 4:
            if "tests" in parts[3:-1]:
                reasons.append(f"{f}：包的測試，不比")
                continue
            packages.add(parts[2])
            reasons.append(f"{f}：包 {parts[2]}")
            compared.append(f)
            continue
        if parts[0] == "tianxia" and len(parts) == 2 and name.endswith(".py"):
            alias = _alias_package(head_root / f)
            if alias and (features / alias).is_dir():
                packages.add(alias)
                reasons.append(f"{f}：別名，照包 {alias}")
                compared.append(f)
                continue
            mod = name[:-3]
            kind = "核心" if mod in core else "共用層" if mod in shared else "舊模組或殼"
            full_reasons.append(f"{f}（{kind}）")
            compared.append(f)
            continue
        full_reasons.append(f"{f}（歸不到包）")  # engine.py、tianxia/features/ 直下的檔、run_bots.py 與其他沒列到的
        compared.append(f)
    full = bool(full_reasons)
    week7 = any(f.startswith("content/profiles/") or f in ("tianxia/calendar.py", "content/config.json") or "timetable" in f for f in compared) or any(
        WEEK7_WORDS.search(line) for f in compared for line in lines.get(f, ()))
    crossover = full or bool(track_tracks) or any(f.split("/")[-1] in CROSS_FILES for f in compared) or any(CROSS_WORDS.search(line) for f in compared for line in lines.get(f, ()))
    for f in files:
        if f == "server.py" or (f.startswith("tianxia/features/") and f.endswith("/routes.py")):
            if any(PAGE_WORDS.search(line) for line in lines.get(f, ())):
                web = web_other = True
                reasons.append(f"{f}：改到回頁面的行，開網頁")
    if full:
        mode, profiles = "full", list(SB_PROFILES)
    elif packages or web_files:
        mode, profiles = "packages", ["season21", "test"] + (["week7"] if week7 or track_tracks else [])
    elif track_tracks:
        mode, profiles = "tracks", list(SB_PROFILES)  # 軌檔改了一律三種設定、半舊半新（切點在軌裡）
    else:
        mode, profiles = "none", []
    return {"mode": mode, "packages": None if full else sorted(packages), "full_reasons": full_reasons, "profiles": [p for p in SB_PROFILES if p in profiles],
            "crossover": crossover and mode != "none", "web": web, "web_files": web_files, "web_all_rounds": web_other,  # 第 109 批：核心退回全軌不再拉全回合
            "track_files_tracks": [] if full else sorted(track_tracks), "reasons": reasons}


def picked_tracks(script: Path, decision: dict) -> list[str] | None:
    """decide 的結果 → 要比的軌（None＝全軌）：tracks 模式只比軌檔的軌；packages 模式 pick(包) 再併上軌檔的軌；none 是空的。"""
    if decision["mode"] == "none":
        return []
    if decision["mode"] == "tracks":
        return list(decision["track_files_tracks"])
    picked = pick(script, decision["packages"])
    if picked is None:
        return None
    return picked + [t for t in decision.get("track_files_tracks", ()) if t not in picked]


def pick(script: Path, packages: list[str] | None) -> list[str] | None:
    """會挑到的軌（same_behavior.py pick）；全軌回 None。"""
    if packages is None:
        return None
    out = subprocess.run([sys.executable, str(script), "pick", "--covers", ",".join(packages) or ","], capture_output=True, text=True, encoding="utf-8",
                         env={**os.environ, "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8"})
    if out.returncode != 0:
        raise RuntimeError(f"same_behavior pick 失敗：{out.stderr[-500:]}")
    return [t for t in out.stdout.strip().split(",") if t]


def bot_covers(script: Path, decision: dict, tracks_given: bool) -> list[str] | None:
    """第 112 批：packages 模式交給 compare 的 --bot-covers（假人座位也照包挑：ALWAYS、座位名在軌裡、座位 covers 有交集，三者聯集，只會多跑）；
    其他模式、--tracks 蓋過的、或那一份 same_behavior.py 還沒有 --bot-covers（舊的 head）回 None＝照舊。"""
    if decision["mode"] != "packages" or tracks_given:
        return None
    try:
        if "--bot-covers" not in script.read_text(encoding="utf-8"):
            return None
    except OSError:
        return None
    return list(decision["packages"])


def picked_seats(script: Path, decision: dict) -> list[str] | None:
    """--dry-run 印的座位（same_behavior.py pick --seats 的第二行）；沒帶 --bot-covers 的回 None（照舊：座位名在挑到的軌裡才跑）。"""
    if decision.get("bot_covers") is None:
        return None
    out = subprocess.run([sys.executable, str(script), "pick", "--covers", ",".join(decision["bot_covers"]) or ",", "--tracks", ",".join(decision["tracks"] or []), "--seats"],
                         capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8"})
    if out.returncode != 0:
        raise RuntimeError(f"same_behavior pick --seats 失敗：{out.stderr[-500:]}")
    lines = out.stdout.strip().split("\n")
    return [s for s in lines[1].split(",") if s] if len(lines) > 1 else []


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失敗：{out.stderr.strip()}")
    return out.stdout.strip()


def unpack(repo: Path, sha: str, dest: Path, *paths: str) -> None:
    dest.mkdir(parents=True)
    raw = subprocess.run(["git", "archive", "--format=tar", sha, *paths], cwd=repo, capture_output=True, check=True).stdout
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


def wait(running: dict, result: dict, started: float) -> None:
    for key, (proc, f) in running.items():
        code = proc.wait()
        f.close()
        minutes = (time.monotonic() - started) / 60
        result[key] = {"code": code, "minutes_since_start": round(minutes, 1)}
        print(f"{key}：結束碼 {code}，開跑後 {minutes:.1f} 分鐘", flush=True)


def red_lines(path: Path, pattern: str, limit: int = 60) -> list[str]:
    if not path.exists():
        return []
    hits = [l.strip()[:200] for l in path.read_text(encoding="utf-8", errors="replace").splitlines() if re.search(pattern, l)]
    return hits[-limit:]


def _junit_slow(xml: Path) -> list[tuple[str, float]]:
    """junit 裡跑了 SLOW_SECONDS 以上的（鍵 classname::name，時間）。"""
    if not xml.exists():
        return []
    return [(f"{c.get('classname')}::{c.get('name')}", float(c.get("time") or 0)) for c in ET.parse(xml).getroot().iter("testcase")
            if float(c.get("time") or 0) >= SLOW_SECONDS]


def _collected_keys(text: str) -> set[str]:
    """pytest --collect-only -q 的 id（a/b/test_x.py::TestC::test_y[1]）換成 junit 的鍵（a.b.test_x.TestC::test_y[1]）。"""
    keys = set()
    for line in text.splitlines():
        if "::" not in line:
            continue
        path, *rest = line.strip().split("::")
        keys.add(".".join([path.removesuffix(".py").replace("/", ".").replace("\\", "."), *rest[:-1]]) + "::" + rest[-1])
    return keys


def concurrent_gates(gates: Path, mine: Path) -> int:
    """開跑當下 .local/wave_gate/*/ 有 gate.log 沒 done 的（不含自己）。"""
    if not gates.is_dir():
        return 0
    return sum(1 for d in gates.iterdir() if d.is_dir() and d != mine and (d / "gate.log").exists() and not (d / "done").exists())


def compare_extra(decision: dict, jobs: str = "", new: str = "", also_existing: bool = False) -> list[str]:
    """compare 的參數：挑到的軌、設定、半舊半新；--new 不管 --changed 還是全軌都傳（PM 11/08 加的）。"""
    picked = decision["tracks"]
    extra = (["--tracks", ",".join(picked)] if picked is not None else []) + (["--jobs", jobs] if jobs else [])
    extra += ["--profiles", ",".join(decision["profiles"])] + (["--crossover"] if decision["crossover"] else [])
    if decision.get("bot_covers") is not None:  # 第 112 批：只有 packages 模式、head 的 compare 認得才有
        extra += ["--bot-covers", ",".join(decision["bot_covers"]) or ","]
    return extra + (["--new", new] if new else []) + (["--also-existing"] if (new and also_existing) else [])


def web_args(decision: dict, changed: bool, new: str = "") -> list[str]:
    """scripts/webqa/gate.py 的參數：--changed 且不全回合才交 --changed-files；--new 照樣轉（N 波合併時補；--also-existing webqa 沒有、不轉）。"""
    files = ["--changed-files", ",".join(decision["web_files"])] if changed and decision["web_files"] and not decision.get("web_all_rounds") else []
    return files + (["--new", new] if new else [])


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--tracks", default="", help="只比這幾軌（修正之後重驗用）；蓋過 --changed 挑的")
    ap.add_argument("--new", default="", help="新功能波：新包的名字（逗號分開），compare 扣掉它們帶來的 js、css、表、op（企劃者 11/08「新東西列出來，其餘一樣」）；--changed 與全軌都傳")
    ap.add_argument("--also-existing", action="store_true", help="跟 --new 一起用：base 已經有這一包（同一包的後續批）也放行它自己的 js、css、表、op（K 波起；compare 要有這個參數）")
    ap.add_argument("--no-suite", action="store_true")
    ap.add_argument("--no-compare", action="store_true")
    ap.add_argument("--jobs", default="")
    ap.add_argument("--web", action="store_true", help="前面都跑完之後跑網頁比對（scripts/webqa/gate.py）")
    ap.add_argument("--web-jobs", default="", help="網頁比對轉給 gate.py 的 --jobs（第 110 批起 --jobs 4 八回合約 35 分；不給就一回合接一回合跑，約兩倍長）；O 波起閘門帶 --changed --web-jobs 4")
    ap.add_argument("--cache", action="store_true", help="同一波修正後重跑才開；進 develop、上 main 的那一次不開")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--changed", action="store_true", help="照 base..head 改到的決定比哪幾軌、設定、半舊半新、網頁（decide）")
    mode.add_argument("--full", action="store_true", help="全軌三設定＋--crossover＋整套含 slow＋--web 全回合")
    ap.add_argument("--dry-run", action="store_true", help="只印 decide 與會挑到的軌，什麼都不跑")
    a = ap.parse_args()

    here = Path(__file__).resolve().parent
    repo = Path(git(here, "rev-parse", "--path-format=absolute", "--git-common-dir")).parent
    base, head = git(repo, "rev-parse", a.base + "^{commit}"), git(repo, "rev-parse", a.head + "^{commit}")

    if a.dry_run:  # 不碰結果夾：同一個 head 真的閘門的結果還在那裡
        if a.changed:
            view = Path(tempfile.mkdtemp(prefix="wave-dry-"))
            try:
                unpack(repo, head, view / "head", "tianxia", "scripts/test_for.py", "scripts/sb/tracks", "server.py")  # decide 只讀 head 的這幾樣（包在不在、核心與共用層名單、別名檔、軌檔；第 112 批 tuning 的讀者要 server.py）
                files = git(repo, "-c", "core.quotepath=off", "diff", "--name-only", base, head).splitlines()
                decision = decide(files, git(repo, "-c", "core.quotepath=off", "diff", "-U0", base, head), view / "head")
            finally:
                shutil.rmtree(view, ignore_errors=True)
        else:
            decision = {"mode": "full", "packages": None, "full_reasons": ["沒帶 --changed"], "profiles": list(SB_PROFILES), "crossover": True,
                        "web": a.full or a.web, "web_files": [], "reasons": []}
        mine = here.parents[2] / "scripts" / "same_behavior.py"  # 這支腳本所在那一份的（舊波的 head 上沒有 covers）
        decision["tracks"] = a.tracks.split(",") if a.tracks else picked_tracks(mine, decision)
        decision["bot_covers"] = bot_covers(mine, decision, bool(a.tracks))
        decision["seats"] = picked_seats(mine, decision)
        decision["files"] = len(files) if a.changed else None
        decision["new"] = a.new.split(",") if a.new else []
        decision["web_args"] = web_args(decision, a.changed, a.new) if (a.web or a.full or (a.changed and decision["web"])) else None
        print(json.dumps(decision, ensure_ascii=False, indent=1))
        return 0

    out = repo / ".local" / "wave_gate" / head[:8]
    others = concurrent_gates(out.parent, out)
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
    result: dict = {"name": a.name, "base": base, "head": head, "started": f"{dt.datetime.now():%m-%d %H:%M}", "cache": a.cache, "concurrent_gates": others}
    if a.cache:
        print("這一次開了快取，不能當進 develop、上 main 的依據", flush=True)
    script = str(root / "scripts" / "same_behavior.py")
    if a.changed:
        files = git(repo, "-c", "core.quotepath=off", "diff", "--name-only", base, head).splitlines()
        decision = decide(files, git(repo, "-c", "core.quotepath=off", "diff", "-U0", base, head), root)
        decision["tracks"] = picked_tracks(Path(script), decision)
        decision["bot_covers"] = bot_covers(Path(script), decision, bool(a.tracks))
    else:
        decision = {"mode": "full", "packages": None, "full_reasons": ["--full" if a.full else "沒帶 --changed"], "profiles": list(SB_PROFILES),
                    "crossover": True, "web": a.full or a.web, "web_files": [], "reasons": [], "tracks": None}
    if a.tracks:
        decision["tracks"] = a.tracks.split(",")
    decision["new"] = a.new.split(",") if a.new else []
    result["decision"] = decision
    print("決定：", json.dumps({k: decision[k] for k in ("mode", "packages", "profiles", "crossover", "web", "new")}, ensure_ascii=False), flush=True)

    scan = subprocess.run([py, str(root / "docs" / "superpowers" / "pm-workflows" / "undef_scan.py"), "tianxia", "server.py", "scripts", "tests"],
                          cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    result["undef_scan"] = {"code": scan.returncode, "tail": scan.stdout.strip().splitlines()[-15:]}
    print("未定義名稱：", scan.returncode, flush=True)

    boots = [boot(py, root, env, p, log) for p in PROFILES]
    result["boot"] = [b for b in boots if b]
    print("三種設定起伺服器：", result["boot"] or "都 200", flush=True)

    suites: dict = {}
    if not a.no_suite:  # 第 107 批：pytest 先跑完，才開比對
        suite_env = {**env, "TIANXIA_DB": str(work / "tmp" / "suite.db")}
        marks = "slow or not slow" if a.full else "not slow"
        suites["suite"] = start([py, "-m", "pytest", "-q", "-n", "4", "-m", marks, "-p", "no:cacheprovider", f"--junitxml={out / 'suite.xml'}"],
                                root, suite_env, out / "suite.txt")
        wait(suites, result, time.monotonic())
        if not a.full:
            smoke = {"smoke": start([py, "-m", "pytest", "-q", SMOKE, "-m", "slow", "-p", "no:cacheprovider", f"--junitxml={out / 'smoke.xml'}"],
                                    root, {**env, "TIANXIA_DB": str(work / "tmp" / "smoke.db")}, out / "smoke.txt")}
            wait(smoke, result, time.monotonic())
            suites.update(smoke)
            result["smoke"]["tail"] = red_lines(out / "smoke.txt", r" passed| failed| error", 2)
        result["suite"]["red"] = red_lines(out / "suite.txt", r"^(FAILED|ERROR) ")
        result["suite"]["tail"] = red_lines(out / "suite.txt", r" passed| failed", 2)
        result["suite"]["xml"] = str(out / "suite.xml")
        slow = _junit_slow(out / "suite.xml")
        if a.full and slow:  # 整套含 slow：只留不含 slow 的那些
            listed = subprocess.run([py, "-m", "pytest", "--collect-only", "-q", "-m", "not slow", "-p", "no:cacheprovider"], cwd=root, env=suite_env,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
            keys = _collected_keys(listed)
            slow = [row for row in slow if row[0] in keys]
        result["slow_unmarked"] = [f"{k} {t:.1f}" for k, t in sorted(slow, key=lambda r: -r[1])]

    running = {}
    if not a.no_compare and decision["mode"] != "none":
        unpack(repo, base, work / "base")
        both = ["--base", str(work / "base"), "--head", str(root)]
        extra = compare_extra(decision, a.jobs, a.new, a.also_existing)
        cached = ["--cache", str(repo / ".local" / "wave_gate" / "cache")] if a.cache else []  # 只給 compare；explore-compare 不快取
        running["compare"] = start([py, script, "compare", *both, "--tmp", str(work / "tmp" / "cmp"), *extra, *cached], root, env, out / "compare.txt")
        if not a.tracks:  # compare 有跑就跟著跑，不照包挑
            running["explore"] = start([py, script, "explore-compare", *both, "--tmp", str(work / "tmp" / "exp")], root, env, out / "explore.txt")
    elif decision["mode"] == "none":
        print("比對：沒跑，改到的都不必比", flush=True)
    wait(running, result, time.monotonic())
    if "compare" in result:
        result["compare"]["red"] = red_lines(out / "compare.txt", r"不一樣|不同|DIFF|differ|失敗|Traceback|Error")
        result["compare"]["slowest"] = red_lines(out / "compare.txt", r"^最慢 ", 10)
    if "explore" in result:
        result["explore"]["red"] = red_lines(out / "explore.txt", r"不一樣|不同|DIFF|differ|失敗|Traceback|Error")

    web = root / "scripts" / "webqa" / "gate.py"
    want_web = a.web or a.full or (a.changed and decision["web"])
    if want_web and web.exists():  # 上面全部等完才跑，不跟整套同時跑：同時跑的話畫面比對的雜訊多
        started = time.monotonic()
        proc, f = start([py, str(web), "--base", base, "--head", head, "--out", str(out / "web"), *web_args(decision, a.changed, a.new),
                         *(["--jobs", a.web_jobs] if a.web_jobs else [])], root,
                        {**env, "TIANXIA_DB": str(work / "tmp" / "web.db")}, out / "web.txt")
        code = proc.wait()
        f.close()
        result["web"] = {"ran": True, "code": code, "minutes": round((time.monotonic() - started) / 60, 1), "out": str(out / "web")}
        print(f"網頁比對：結束碼 {code}，{result['web']['minutes']} 分鐘", flush=True)
    else:
        result["web"] = {"ran": False, "why": "head 上沒有 scripts/webqa/gate.py" if want_web else "沒帶 --web" if not a.changed else "改到的沒碰網頁"}
        print("網頁比對：沒跑，" + result["web"]["why"], flush=True)

    subprocess.call(["git", "worktree", "remove", "--force", str(root)], cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(work, ignore_errors=True)

    ran = {**suites, **running}
    green = scan.returncode == 0 and not result["boot"] and all(result[k]["code"] == 0 for k in ran) and (not result["web"]["ran"] or result["web"]["code"] == 0)
    result["green"] = green
    result["finished"] = f"{dt.datetime.now():%m-%d %H:%M}"
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "done").write_text("green\n" if green else "red\n", encoding="utf-8")
    print("全綠" if green else "有紅", out, flush=True)
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
