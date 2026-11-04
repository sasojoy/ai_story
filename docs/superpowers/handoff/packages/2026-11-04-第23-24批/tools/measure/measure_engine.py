"""量「改 engine.py 一個方法的最後一行」test_for 挑到幾條：臨時在那個方法最後一行行尾加一個註解，跑 --count（不含／含 slow），
寫回原本的位元組（finally），確認一個位元組都沒變。
用法：python measure_engine.py <git 工作樹> <Game 方法名…>。test_for 要問 git，所以要量 base 用 git worktree add --detach，不能用 git archive 解出來的。"""
import ast
import io
import os
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
root = Path(sys.argv[1])
methods = sys.argv[2:]
path = root / "tianxia" / "engine.py"
orig = path.read_bytes()
text = orig.decode("utf-8")
tree = ast.parse(text.replace("\r\n", "\n"))
game = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Game")
env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
try:
    for name in methods:
        f = next(x for x in game.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == name)
        nl = "\r\n" if "\r\n" in text else "\n"  # Windows 的工作樹是 CRLF，別的系統是 LF
        lines = text.split(nl)
        lines[f.end_lineno - 1] += "  # 量測"
        path.write_bytes(nl.join(lines).encode("utf-8"))
        out = []
        for extra in ([], ["--slow"]):
            r = subprocess.run([sys.executable, "scripts/test_for.py", "tianxia/engine.py", "--base", "HEAD", "--count", *extra],
                               cwd=root, capture_output=True, text=True, encoding="utf-8", env=env)
            last = [x for x in r.stdout.splitlines() if "一共" in x]
            out.append(last[-1] if last else r.stdout[-300:])
        print(name, "|", " || ".join(out))
        path.write_bytes(orig)
finally:
    path.write_bytes(orig)
assert path.read_bytes() == orig
print("restored ok")
