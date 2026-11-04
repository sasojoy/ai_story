import ast
import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
for root in sys.argv[1:]:
    p = Path(root) / "tianxia" / "core" / "services.py"
    doc = ast.get_docstring(ast.parse(p.read_text(encoding="utf-8"))) or ""
    names = set(re.findall(r"`ctx\.(\w+)", doc))
    reg = Path(root) / "tianxia" / "core" / "registry.py"
    tree = ast.parse(reg.read_text(encoding="utf-8"))
    shared = next(n for n in tree.body if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "SHARED")
    print(root, "services", len(names), "shared", len(shared.value.keys))
