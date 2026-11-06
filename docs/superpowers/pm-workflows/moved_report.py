"""一條線搬了什麼的機械報告（波次模式的審查先讀這一份，不必自己逐條比；企劃者 2026-11-06「減少測試驗收的頻率」）。

把 base 與 head 的 `Game` 方法、`tianxia/` 模組函式逐條比：
- 搬走的方法：head 的 `Game` 上變成一行委派或不見了，到 `tianxia/` 其他檔找同名函式（委派叫誰就找誰），
  self 換成第一個參數之後比語法樹；一樣的只算數，不一樣的列出每一行。
- 留在 `Game` 上、內容變了的方法：列出每一行。
- 整個模組搬進包：同名函式比語法樹；舊位置變成別名的記一筆。
用法：python docs/superpowers/pm-workflows/moved_report.py <base> <head> [--max 200]
只讀，不改任何東西。
"""
from __future__ import annotations

import argparse
import ast
import difflib
import io
import re
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
TOP = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=HERE, capture_output=True, text=True, encoding="utf-8").stdout.strip()  # ls-tree 的路徑照 cwd 算


def git(*args: str) -> str:
    out = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=TOP, capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} 失敗：{out.stderr.decode('utf-8', 'replace')}")
    return out.stdout.decode("utf-8", "replace").replace("\r\n", "\n")


def py_files(rev: str) -> dict[str, str]:
    names = [n for n in git("ls-tree", "-r", "--name-only", rev, "tianxia", "server.py").splitlines() if n.endswith(".py") and "/tests/" not in n]
    return {n: git("show", f"{rev}:{n}") for n in names}


def parse(text: str):
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def strip_doc(fn) -> list:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    return body


def first_arg(fn) -> str:
    args = fn.args.posonlyargs + fn.args.args
    return args[0].arg if args else ""


class Rename(ast.NodeTransformer):
    def __init__(self, old: str):
        self.old = old

    def visit_Name(self, node):
        if node.id == self.old:
            node.id = "self"
        return node


def text_of(fn, *, drop_first: bool = False) -> list[str]:
    """函式本體攤成幾行：拿掉說明字、第一個參數一律叫 self。"""
    clone = ast.parse(ast.unparse(fn)).body[0]
    old = first_arg(clone)
    if old and old != "self":
        clone = Rename(old).visit(clone)
    lines = []
    for stmt in strip_doc(clone):
        lines += ast.unparse(stmt).splitlines()
    return lines


def norm_line(line: str) -> str:
    """機械改寫不算差別：模組路徑的前綴；self._x(...) 對 x(self, ...)（方法搬成函式最常見的改寫）。"""
    line = re.sub(r"\b(?:[a-z_]+_base|seal_rules)\.", "", line)
    line = re.sub(r"\bself\._?(\w+)\(", r"\1(self, ", line)
    line = re.sub(r"\b_(\w+)\(self\b", r"\1(self", line)
    return line.replace("(self, )", "(self)")


def functions(files: dict[str, str]) -> dict[str, list[tuple[str, ast.AST]]]:
    out: dict[str, list[tuple[str, ast.AST]]] = {}
    for path, text in files.items():
        tree = parse(text)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.setdefault(node.name, []).append((path, node))
    return out


def game_methods(files: dict[str, str]) -> dict:
    tree = parse(files.get("tianxia/engine.py", ""))
    for node in (tree.body if tree else []):
        if isinstance(node, ast.ClassDef) and node.name == "Game":
            return {f.name: f for f in node.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return {}


def delegate_target(fn) -> str | None:
    body = strip_doc(fn)
    if len(body) != 1:
        return None
    stmt = body[0]
    value = stmt.value if isinstance(stmt, (ast.Return, ast.Expr)) else None
    if isinstance(value, ast.Await):
        value = value.value
    if not isinstance(value, ast.Call):
        return None
    func = value.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def compare(old: list[str], new: list[str]) -> list[str]:
    a, b = [norm_line(x) for x in old], [norm_line(x) for x in new]
    if a == b:
        return []
    return [l for l in difflib.unified_diff(a, b, lineterm="", n=0) if not l.startswith(("---", "+++", "@@"))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("head")
    ap.add_argument("--max", type=int, default=200, help="每個方法最多列幾行差別")
    a = ap.parse_args()
    bf, hf = py_files(a.base), py_files(a.head)
    bg, hg = game_methods(bf), game_methods(hf)
    hfun = functions({k: v for k, v in hf.items() if k != "tianxia/engine.py"})
    same, changed, missing, kept_changed = [], [], [], []
    for name, fn in sorted(bg.items()):
        now = hg.get(name)
        old_body = text_of(fn)
        if now is not None:
            target = delegate_target(now)
            is_delegate_now = target is not None and delegate_target(fn) is None
            if not is_delegate_now:
                diff = compare(old_body, text_of(now))
                if diff:
                    kept_changed.append((name, diff))
                continue
        else:
            target = name
        cands = hfun.get(target or name, []) or hfun.get(name, []) or hfun.get(name.lstrip("_"), [])
        if not cands:
            missing.append((name, target))
            continue
        best = None
        for path, cand in cands:
            diff = compare(old_body, text_of(cand))
            if best is None or len(diff) < len(best[1]):
                best = (path, diff)
        (same if not best[1] else changed).append((name, best[0], best[1]))

    print(f"# 搬走的 Game 方法：語法樹一樣 {len(same)}、有差 {len(changed)}、找不到 {len(missing)}；留在 Game 上內容變了 {len(kept_changed)}")
    by_file: dict[str, int] = {}
    for _, path, _d in same:
        by_file[path] = by_file.get(path, 0) + 1
    for path, n in sorted(by_file.items()):
        print(f"  一樣：{path} {n} 個")
    for name, target in missing:
        print(f"## 找不到：{name}（委派叫 {target}）")
    for name, path, diff in changed:
        print(f"## 有差：{name} → {path}（{len(diff)} 行）")
        print("\n".join(diff[: a.max]))
    for name, diff in kept_changed:
        print(f"## 留在 Game、內容變了：{name}（{len(diff)} 行）")
        print("\n".join(diff[: a.max]))

    # 舊模組函式：head 同檔沒有了，到別處找同名的比
    bfun_by_file = {}
    for path, text in bf.items():
        if path == "tianxia/engine.py":
            continue
        tree = parse(text)
        if tree is None:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                bfun_by_file.setdefault(path, {})[node.name] = node
    allhead = functions(hf)
    mod_same = mod_changed = 0
    print("\n# 搬動或內容變了的模組函式")
    for path, fns in sorted(bfun_by_file.items()):
        here_tree = parse(hf.get(path, ""))
        here = {n.name: n for n in (here_tree.body if here_tree else []) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name, fn in sorted(fns.items()):
            old = text_of(fn)
            if name in here:
                diff = compare(old, text_of(here[name]))
                if diff:
                    mod_changed += 1
                    print(f"## 原地改了：{path}:{name}（{len(diff)} 行）")
                    print("\n".join(diff[: a.max]))
                continue
            cands = [c for c in allhead.get(name, []) if c[0] != path]
            if not cands:
                print(f"## 不見了：{path}:{name}")
                mod_changed += 1
                continue
            best = min(((p, compare(old, text_of(c))) for p, c in cands), key=lambda x: len(x[1]))
            if best[1]:
                mod_changed += 1
                print(f"## 搬了又改：{path}:{name} → {best[0]}（{len(best[1])} 行）")
                print("\n".join(best[1][: a.max]))
            else:
                mod_same += 1
    print(f"# 模組函式：搬了一字不差 {mod_same}、有差或不見 {mod_changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
