"""掃未定義名稱（語法樹，不跑程式，幾秒鐘）。第 21 批修正輪把函式搬到另一個檔、漏了 import，測試要走到那條路才紅；這種錯在這裡一次抓。
用法：python docs/superpowers/pm-workflows/undef_scan.py tianxia server.py   # 給檔或資料夾；有問題結束碼 1
寬鬆的做法：推導式裡綁的名字也算在外層，寧可漏不要誤報。"""
from __future__ import annotations

import ast
import builtins
import io
import sys
from pathlib import Path


class Scope:
    def __init__(self, parent=None):
        self.names = set()
        self.parent = parent

    def has(self, name):
        s = self
        while s:
            if name in s.names:
                return True
            s = s.parent
        return False


def bound_in(node, scope):
    """把這一層（不進子函式、子類別）綁定的名字收進 scope。"""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scope.names.add(child.name)
            for d in child.decorator_list:  # 裝飾器裡的推導式（@parametrize(ids=[p.stem for p in …])）算在這一層
                bound_in(d, scope)
            continue
        if isinstance(child, ast.Lambda):
            continue
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            for a in child.names:
                scope.names.add((a.asname or a.name).split(".")[0])
        elif isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
            scope.names.add(child.id)
        elif isinstance(child, ast.ExceptHandler) and child.name:
            scope.names.add(child.name)
        elif isinstance(child, (ast.Global, ast.Nonlocal)):
            scope.names.update(child.names)
        bound_in(child, scope)


def scan(tree) -> list[tuple[int, str]]:
    problems: list[tuple[int, str]] = []

    def walk(node, scope):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                inner = Scope(scope)
                a = child.args
                for arg in [*a.posonlyargs, *a.args, *a.kwonlyargs]:
                    inner.names.add(arg.arg)
                if a.vararg:
                    inner.names.add(a.vararg.arg)
                if a.kwarg:
                    inner.names.add(a.kwarg.arg)
                bound_in(child, inner)
                for d in [*a.defaults, *[k for k in a.kw_defaults if k]]:
                    walk_expr(d, scope)
                if isinstance(child, ast.Lambda):
                    walk_expr(child.body, inner)
                else:
                    for d in child.decorator_list:
                        walk_expr(d, scope)
                    walk(child, inner)
            elif isinstance(child, ast.ClassDef):
                inner = Scope(scope)
                bound_in(child, inner)
                walk(child, inner)
            else:
                walk_expr(child, scope)

    def walk_expr(node, scope):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if not scope.has(node.id) and not hasattr(builtins, node.id):
                problems.append((node.lineno, node.id))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            walk(ast.Module(body=[node], type_ignores=[]), scope)
            return
        walk(node, scope)

    top = Scope()
    top.names.update({"__file__", "__name__", "__doc__"})
    bound_in(tree, top)
    walk(tree, top)
    return sorted(set(problems))


def main(argv) -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    files: list[Path] = []
    for arg in argv:
        p = Path(arg)
        files += sorted(p.rglob("*.py")) if p.is_dir() else [p]
    bad = 0
    for f in files:
        text = f.read_text(encoding="utf-8")
        tree = ast.parse(text)
        if any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in ast.walk(tree)):
            continue  # import * 認不出來，跳過
        found = scan(tree)
        if found:
            bad += 1
            print(f, found)
    print(f"掃了 {len(files)} 個檔，{bad} 個有未定義名稱")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
