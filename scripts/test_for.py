"""改了哪些檔就跑哪幾個測試檔（開發中用；合併前照舊跑整套 pytest -m "slow or not slow"）。

用法：
  python scripts/test_for.py                 # 跟 origin/main 比，加上還沒提交的改動
  python scripts/test_for.py tianxia/fusion.py content/skills.json
  python scripts/test_for.py --list ...      # 只列出會跑哪幾個檔，不跑
  python scripts/test_for.py --all           # 整套（含 slow），合併前用
  python scripts/test_for.py -- -x -k fuse   # -- 之後的參數原樣交給 pytest

怎麼挑（只看直接關係，間接用到的留給合併前的整套）：
- tests/ 裡的測試檔：跑它自己；tests/conftest.py、tests/fixtures/、pyproject.toml、requirements.txt：整套。
- tianxia/<模組>.py、server.py、run_bots.py、scripts/<腳本>.py：直接 import 它的測試檔，加上檔名是 test_<模組>…的。
- content/：test_content.py、test_real_content.py，加上寫到那個檔名的測試檔。
- web/：寫到那個檔名的測試檔（app.js、style.css、index.html），加上 test_server.py。
- docs/、CLAUDE.md 這類文件：不跑。
挑到的檔連 slow 一起跑（改內容就會跑到真實內容的整季機器人）。裝了 pytest-xdist 而且挑到三個檔以上時自動平行（-n auto）。"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
EVERYTHING = {"tests/conftest.py", "pyproject.toml", "requirements.txt"}
PARALLEL_FROM = 3  # 挑到這麼多個檔以上才開 xdist（開工作行程本身要幾秒）


def changed_files() -> list[str]:
    """跟 origin/main 分岔之後改過的、還沒提交的、還沒加進版控的檔。"""
    def git(*args: str) -> list[str]:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        return [line.strip() for line in out.stdout.splitlines() if line.strip()]

    files = git("diff", "--name-only", "origin/main...HEAD") + git("diff", "--name-only", "HEAD")
    files += git("ls-files", "--others", "--exclude-standard")
    return sorted(set(files))


def imported(test: Path) -> set[str]:
    """這個測試檔直接 import 的本專案模組（tianxia.x 記成 x；server、run_bots、scripts 底下的腳本照名字）。"""
    names: set[str] = set()
    for node in ast.walk(ast.parse(test.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "tianxia":
                names.update(a.name for a in node.names)
            elif node.module.startswith("tianxia."):
                names.add(node.module.split(".")[1])
            else:
                names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name.split(".")[1] if a.name.startswith("tianxia.") else a.name.split(".")[0])
    return names


def pick(files: list[str]) -> list[Path] | None:
    """要跑的測試檔；None 是整套。"""
    tests = sorted(TESTS.glob("test_*.py"))
    texts = {t: t.read_text(encoding="utf-8") for t in tests}
    imports = {t: imported(t) for t in tests}
    chosen: set[Path] = set()
    for raw in files:
        f = raw.replace("\\", "/")
        path = Path(f)
        if f in EVERYTHING or f.startswith("tests/fixtures/"):
            return None
        if f.startswith("tests/"):
            if path.name.startswith("test_") and (ROOT / f).exists():
                chosen.add(ROOT / f)
            elif path.suffix == ".py":  # 測試共用的小工具：import 它的測試檔
                chosen.update(t for t in tests if path.stem in imports[t])
            continue
        if path.suffix == ".py" and (f.startswith("tianxia/") or f.startswith("scripts/") or "/" not in f):
            mod = path.stem
            chosen.update(t for t in tests if mod in imports[t] or t.stem == f"test_{mod}" or t.stem.startswith(f"test_{mod}_")
                          or (f.startswith("scripts/") and f"{mod}.py" in texts[t]))
            continue
        if f.startswith("content/"):
            chosen.update(TESTS / n for n in ("test_content.py", "test_real_content.py"))
            chosen.update(t for t in tests if path.name in texts[t])
            continue
        if f.startswith("web/"):
            chosen.add(TESTS / "test_server.py")
            chosen.update(t for t in tests if path.name in texts[t])
    return sorted(chosen)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="改了哪些檔就跑哪幾個測試檔")
    parser.add_argument("files", nargs="*", help="改過的檔（沒給就問 git）")
    parser.add_argument("--list", action="store_true", help="只列出要跑的測試檔")
    parser.add_argument("--all", action="store_true", help="整套，含 slow（合併前用）")
    argv = sys.argv[1:] if argv is None else argv
    extra = argv[argv.index("--") + 1:] if "--" in argv else []  # -- 之後的原樣交給 pytest（例：-- -x -k fusion）
    args = parser.parse_args(argv[:argv.index("--")] if "--" in argv else argv)
    files = args.files or changed_files()
    chosen = None if args.all else pick(files)
    if chosen is not None and not chosen:
        print("這些改動沒有對應的測試檔（文件之類）。要跑整套用 --all。")
        return 0
    targets = ["tests"] if chosen is None else [str(t.relative_to(ROOT)) for t in chosen]
    print("整套" if chosen is None else "要跑：" + " ".join(t.removeprefix("tests/") for t in targets), flush=True)
    if args.list:
        return 0
    cmd = [sys.executable, "-m", "pytest", "-q", "-m", "slow or not slow", *targets, *extra]
    if importlib.util.find_spec("xdist") is not None and (chosen is None or len(chosen) >= PARALLEL_FROM):
        cmd += ["-n", "auto"]
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
