"""唯讀盤點：用 ast 把 splitwt 工作樹的架構抽成 inventory.json（給後面五位調查員分配用）。只讀工作樹、只寫 split 資料夾。"""
from __future__ import annotations

import ast
import io
import json
import re
import subprocess
import sys
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

WT = Path(r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\splitwt")
OUT = Path(r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\split")
TMP = OUT / "tmp_inventory"
TX = WT / "tianxia"

PREFIX_RE = re.compile(r"^([a-z][a-z0-9_]*):")
REMOVAL_MODULES = {"tianxia.explore_modes", "tianxia.gather_llm"}  # 企劃者 10/31：探索三選一整套拿掉（搬完六包之後）
REMOVAL_CONTENT = {"content/profiles/weekend.json", "content/gather_branches.json"}


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def nlines(text: str) -> int:
    return len(text.splitlines())


def rel(p: Path) -> str:
    return p.relative_to(WT).as_posix()


def span(node) -> tuple[int, int]:
    start = node.lineno
    for d in getattr(node, "decorator_list", []) or []:
        start = min(start, d.lineno)
    return start, node.end_lineno


def unparse(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "?"


# ───────────────────────── 模組與 import ─────────────────────────
mod_files = sorted(p for p in TX.rglob("*.py") if "__pycache__" not in p.parts)


def modname_of(p: Path) -> str:
    parts = list(p.relative_to(WT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


KNOWN = {modname_of(p): p for p in mod_files}
TREES: dict[str, ast.Module] = {}
TEXTS: dict[str, str] = {}
for name, p in KNOWN.items():
    TEXTS[name] = read(p)
    TREES[name] = ast.parse(TEXTS[name], filename=str(p))


def is_type_checking(test) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")


def iter_imports(tree: ast.Module):
    """(node, context)：context 是 top／type_checking／lazy（在函式裡）。"""
    out = []

    def walk(node, ctx):
        for child in ast.iter_child_nodes(node):
            c = ctx
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                c = "lazy"
            if isinstance(child, ast.If) and is_type_checking(child.test) and ctx == "top":
                for b in child.body:
                    if isinstance(b, (ast.Import, ast.ImportFrom)):
                        out.append((b, "type_checking"))
                    else:
                        walk(b, "type_checking")
                for b in child.orelse:
                    walk(b, ctx) if not isinstance(b, (ast.Import, ast.ImportFrom)) else out.append((b, ctx))
                continue
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                out.append((child, c))
            else:
                walk(child, c)

    walk(tree, "top")
    return out


def resolve_import(node, cur: str, is_pkg: bool) -> list[tuple[str, str | None, str]]:
    """回 [(目標模組, 匯入的名字或 None, 本地別名)]。"""
    res = []
    if isinstance(node, ast.Import):
        for a in node.names:
            target = a.name
            local = a.asname or a.name.split(".")[0]
            res.append((target, None, local if a.asname else a.name))
        return res
    if node.level == 0:
        base = node.module or ""
    else:
        pkg = cur.split(".") if is_pkg else cur.split(".")[:-1]
        if node.level > 1:
            pkg = pkg[: len(pkg) - (node.level - 1)]
        base = ".".join(pkg + ([node.module] if node.module else []))
    for a in node.names:
        cand = f"{base}.{a.name}" if base else a.name
        if cand in KNOWN:
            res.append((cand, None, a.asname or a.name))  # 匯入的是子模組
        else:
            res.append((base, a.name, a.asname or a.name))
    return res


def tx(target: str) -> bool:
    return target == "tianxia" or target.startswith("tianxia.")


def norm_target(t: str) -> str:
    # tianxia.x.y 這種寫法裡最長的已知模組
    parts = t.split(".")
    while parts:
        cand = ".".join(parts)
        if cand in KNOWN:
            return cand
        parts = parts[:-1]
    return t


ALIASES: dict[str, dict[str, str]] = {}  # 模組 → 本地名 → 它指的 tianxia 模組（只收「匯入的是模組」的那種）
FROM_NAMES: dict[str, dict[str, tuple[str, str]]] = {}  # 模組 → 本地名 → (來源模組, 原名)
MODULE_IMPORTS: dict[str, dict[str, set]] = {}
for name, tree in TREES.items():
    is_pkg = KNOWN[name].name == "__init__.py"
    al, fn = {}, {}
    imps = {"top": set(), "type_checking": set(), "lazy": set()}
    for node, ctx in iter_imports(tree):
        for target, imported, local in resolve_import(node, name, is_pkg):
            if not tx(target):
                continue
            t = norm_target(target)
            if t == name:
                continue
            imps[ctx].add(t)
            if ctx == "top":
                if imported is None:
                    if isinstance(node, ast.Import) and "." in target and local == target:
                        pass  # import tianxia.x → 本地名 tianxia
                    else:
                        al[local] = t
                else:
                    fn[local] = (t, imported)
    ALIASES[name], FROM_NAMES[name] = al, fn
    MODULE_IMPORTS[name] = imps

# 殼與腳本、測試誰 import 誰
OUTSIDE_FILES = [p for p in WT.glob("*.py")] + sorted((WT / "scripts").rglob("*.py"))
TEST_FILES = sorted((WT / "tests").rglob("*.py"))
outside_imports: dict[str, set] = {}
outside_alias: dict[str, dict[str, str]] = {}
for p in OUTSIDE_FILES + TEST_FILES:
    try:
        tree = ast.parse(read(p))
    except SyntaxError:
        continue
    s, al = set(), {}
    for node, ctx in iter_imports(tree):
        for target, imported, local in resolve_import(node, "", False):
            if tx(target):
                t = norm_target(target)
                s.add(t)
                if ctx == "top" and imported is None:
                    al[local] = t
                elif ctx == "top" and imported is not None:
                    pass
    outside_imports[rel(p)] = s
    outside_alias[rel(p)] = al

imported_by = defaultdict(set)
imported_by_tests = defaultdict(set)
for name, imps in MODULE_IMPORTS.items():
    for ctx, targets in imps.items():
        for t in targets:
            (imported_by_tests if "/tests/" in rel(KNOWN[name]) or rel(KNOWN[name]).endswith("conftest.py") else imported_by)[t].add(
                name + ("" if ctx == "top" else f"（{ctx}）"))
for f, targets in outside_imports.items():
    for t in targets:
        (imported_by_tests if f.startswith("tests/") else imported_by)[t].add(f)

# sys.modules 別名（搬包後舊模組名留的）
module_aliases = []
for name, tree in TREES.items():
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Subscript) and unparse(t.value) == "sys.modules":
                    v = unparse(node.value)
                    module_aliases.append({"in": name, "line": node.lineno, "alias": unparse(t.slice), "value": v,
                                           "old_name": name if unparse(t.slice) == "__name__" else unparse(t.slice),
                                           "now_is": ALIASES.get(name, {}).get(v)})
        if isinstance(node, ast.Call) and unparse(node.func) in ("sys.modules.setdefault", "sys.modules.update"):
            module_aliases.append({"in": name, "line": node.lineno, "alias": unparse(node), "value": ""})

# CLAUDE.md 功能區塊表：模組 → 區塊
BLOCK_OF: dict[str, str] = {}
for line in read(WT / "CLAUDE.md").splitlines():
    m = re.match(r"^\| \[([^\]]+)\]\([^)]*\) \| [^|]* \| ([^|]*) \|", line)
    if m:
        for mod in re.split(r"[、,，\s]+", m.group(2)):
            mod = mod.strip().strip("`")
            if mod and mod != "—":
                BLOCK_OF.setdefault(mod, m.group(1))


def top_level_defs(tree: ast.Module) -> list[dict]:
    out = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            s, e = span(n)
            d = {"name": n.name, "kind": "class" if isinstance(n, ast.ClassDef) else "function", "start": s, "end": e,
                 "lines": e - s + 1}
            if isinstance(n, ast.ClassDef):
                d["methods"] = sum(isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) for b in n.body)
            out.append(d)
    return out


modules = []
for name, p in KNOWN.items():
    r = rel(p)
    short = name.removeprefix("tianxia.")
    pkg = ".".join(name.split(".")[:-1]) if p.name != "__init__.py" else name
    imps = MODULE_IMPORTS[name]
    all_imps = sorted(imps["top"] | imps["type_checking"] | imps["lazy"])
    tl = top_level_defs(TREES[name])
    entry = OrderedDict(
        path=r, module=name, package=pkg, is_init=p.name == "__init__.py",
        is_test="/tests/" in r or p.name == "conftest.py",
        block=(BLOCK_OF.get(short) if "." not in short else
               "（核心 tianxia/core）" if short.startswith("core") else
               BLOCK_OF.get(short.split(".")[1]) if short.startswith("features.") and short.count(".") >= 1 else None),
        removal="整套拿掉（企劃者 10/31：只剩 week7、season21；排在搬完六包之後）" if name in REMOVAL_MODULES else None,
        lines=nlines(TEXTS[name]),
        imports_tianxia=all_imps,
        imports_lazy=sorted(imps["lazy"]),
        imports_type_checking=sorted(imps["type_checking"]),
        imported_by=sorted(imported_by.get(name, ())),
        imported_by_tests_count=len(imported_by_tests.get(name, ())),
        imported_by_tests=sorted(imported_by_tests.get(name, ())),
        top_functions=sum(d["kind"] == "function" for d in tl),
        top_classes=sum(d["kind"] == "class" for d in tl),
        top_level=tl,
    )
    modules.append(entry)
mod_by_name = {m["module"]: m for m in modules}

# ───────────────────────── 字串常數解析（選項 id 用）─────────────────────────


def module_consts(name: str) -> dict[str, str]:
    out = {}
    tree = TREES.get(name)
    if tree is None:
        return out
    for n in tree.body:
        targets = []
        if isinstance(n, ast.Assign):
            targets, value = n.targets, n.value
        elif isinstance(n, ast.AnnAssign) and n.value is not None:
            targets, value = [n.target], n.value
        else:
            continue
        for t in targets:
            if isinstance(t, ast.Name):
                h = static_str(value, name, out)
                if h is None and isinstance(value, ast.Attribute):
                    h = resolve_name(value, name)
                if h is None and isinstance(value, ast.Name):
                    h = out.get(value.id) or resolve_name(value, name)
                if h is not None:
                    out[t.id] = h
            elif isinstance(t, ast.Tuple) and isinstance(value, ast.Tuple) and len(t.elts) == len(value.elts):
                for te, ve in zip(t.elts, value.elts):
                    if isinstance(te, ast.Name):
                        h = static_str(ve, name, out)
                        if h is not None:
                            out[te.id] = h
    return out


def static_str(node, modname: str, local_consts: dict | None = None):
    """整個字串都能靜態決定時回字串，否則 None。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = static_str(node.left, modname, local_consts), static_str(node.right, modname, local_consts)
        return a + b if a is not None and b is not None else None
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(v.value)
            elif isinstance(v, ast.FormattedValue):
                s = static_str(v.value, modname, local_consts)
                if s is None:
                    return None
                parts.append(s)
        return "".join(parts)
    if isinstance(node, ast.Name) and local_consts is not None and node.id in local_consts:
        return local_consts[node.id]
    return None


CONST_CACHE: dict[str, dict[str, str]] = {}


def consts(name: str) -> dict[str, str]:
    if name not in CONST_CACHE:
        CONST_CACHE[name] = {}
        CONST_CACHE[name] = module_consts(name)
    return CONST_CACHE[name]


def resolve_name(node, modname: str, depth: int = 0):
    """Name／Attribute 指到的字串常數。"""
    if depth > 4:
        return None
    if isinstance(node, ast.Name):
        c = consts(modname)
        if node.id in c:
            return c[node.id]
        src = FROM_NAMES.get(modname, {}).get(node.id)
        if src:
            return resolve_name(ast.Name(id=src[1]), src[0], depth + 1)
        return None
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        target = ALIASES.get(modname, {}).get(node.value.id)
        if target:
            return resolve_name(ast.Name(id=node.attr), target, depth + 1)
    return None


def str_head(node, modname: str):
    """字串運算式開頭能靜態決定的那一段（f-string 的常數部分、常數名）。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, (ast.Name, ast.Attribute)):
        return resolve_name(node, modname)
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(v.value)
            elif isinstance(v, ast.FormattedValue):
                s = str_head(v.value, modname)
                if s is None:
                    break
                parts.append(s)
        return "".join(parts) if parts else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a = str_head(node.left, modname)
        if a is None:
            return None
        b = str_head(node.right, modname)
        return a + (b or "")
    if isinstance(node, ast.IfExp):
        return str_head(node.body, modname)
    return None


def prefix_of(head):
    if not head:
        return None
    m = PREFIX_RE.match(head)
    return m.group(1) if m else None


# ───────────────────────── engine.py：Game ─────────────────────────
ENG = "tianxia.engine"
eng_tree = TREES[ENG]
game_cls = next(n for n in eng_tree.body if isinstance(n, ast.ClassDef) and n.name == "Game")
gs, ge = span(game_cls)
method_nodes = [b for b in game_cls.body if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef))]
GAME_METHODS = {m.name for m in method_nodes}
eng_alias = ALIASES[ENG]
eng_from = FROM_NAMES[ENG]


def self_calls(fn):
    calls, refs = [], []
    call_funcs = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) \
                and n.func.value.id == "self" and n.func.attr in GAME_METHODS:
            call_funcs.add(id(n.func))
            if n.func.attr not in calls:
                calls.append(n.func.attr)
    for n in ast.walk(fn):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self" \
                and n.attr in GAME_METHODS and id(n) not in call_funcs and n.attr not in refs and n.attr not in calls:
            refs.append(n.attr)
    return calls, refs


def mod_refs(fn, modname=ENG):
    al, fr = ALIASES[modname], FROM_NAMES[modname]
    out = []
    for n in ast.walk(fn):
        t = None
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in al:
            t = al[n.value.id]
        elif isinstance(n, ast.Name) and n.id in fr:
            t = fr[n.id][0]
        if t and t != modname and t not in out:
            out.append(t)
    return out


game_methods = []
for m in method_nodes:
    s, e = span(m)
    calls, refs = self_calls(m)
    mr = mod_refs(m)
    game_methods.append(OrderedDict(
        name=m.name, start=s, end=e, lines=e - s + 1,
        decorators=[unparse(d) for d in m.decorator_list],
        calls_self=calls, refs_self_uncalled=refs,
        mod_refs=[t.removeprefix("tianxia.") for t in mr],
        touches_removal=[t.removeprefix("tianxia.") for t in mr if t in REMOVAL_MODULES],
    ))
called_by = defaultdict(list)
for gm in game_methods:
    for c in gm["calls_self"] + gm["refs_self_uncalled"]:
        if gm["name"] not in called_by[c]:
            called_by[c].append(gm["name"])
for gm in game_methods:
    gm["called_by"] = called_by.get(gm["name"], [])

game_class_attrs = []
for b in game_cls.body:
    if isinstance(b, (ast.Assign, ast.AnnAssign)):
        tgt = b.targets[0] if isinstance(b, ast.Assign) else b.target
        game_class_attrs.append({"name": unparse(tgt), "line": b.lineno})

engine_other = []
for n in eng_tree.body:
    if n is game_cls:
        continue
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        s, e = span(n)
        engine_other.append({"name": n.name, "kind": "class" if isinstance(n, ast.ClassDef) else "function", "start": s, "end": e,
                             "lines": e - s + 1, "decorators": [unparse(d) for d in n.decorator_list]})
engine_consts = [{"name": unparse(n.targets[0] if isinstance(n, ast.Assign) else n.target), "line": n.lineno}
                 for n in eng_tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))]

# 引擎以外誰叫 Game 的方法（receiver 是 game／g／ctx／self.game…），以及測試換掉 Game 方法的
RECEIVERS = {"game", "g", "ctx", "gm", "host", "viewer", "player_game", "other", "target_game", "them", "peer", "mine", "his", "her",
             "theirs", "a", "b", "me", "you", "attacker", "defender", "challenger", "foe_game", "other_game", "new", "old", "fresh"}
ext_src = defaultdict(Counter)
ext_tests = defaultdict(Counter)
patched = defaultdict(set)
receiver_seen = Counter()


def scan_external(p: Path, tree: ast.Module, is_test: bool):
    r = rel(p)
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr in GAME_METHODS:
            v = n.value
            recv = None
            if isinstance(v, ast.Name):
                recv = v.id
            elif isinstance(v, ast.Attribute) and v.attr in ("game", "_game"):
                recv = "*.game"
            elif isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in ("_game", "Game"):
                recv = v.func.id + "()"
            if recv is None:
                continue
            if recv in RECEIVERS or recv in ("Game", "*.game", "_game()", "Game()") or recv.endswith("game"):
                receiver_seen[recv] += 1
                (ext_tests if is_test else ext_src)[n.attr][r] += 1
        if isinstance(n, ast.Call):
            fname = unparse(n.func)
            if fname.endswith("setattr") and len(n.args) >= 2 and isinstance(n.args[1], ast.Constant) \
                    and isinstance(n.args[1].value, str):
                tgt = unparse(n.args[0])
                attr = n.args[1].value
                if attr in GAME_METHODS and (tgt in ("Game", "engine.Game", "tianxia.engine.Game") or "game" in tgt.lower()
                                             or tgt in RECEIVERS):
                    patched[attr].add(r)
            if fname.endswith("setattr") and len(n.args) >= 1 and isinstance(n.args[0], ast.Constant) \
                    and isinstance(n.args[0].value, str) and n.args[0].value.startswith("tianxia.engine.Game."):
                attr = n.args[0].value.rsplit(".", 1)[1]
                if attr in GAME_METHODS:
                    patched[attr].add(r)


for name, tree in TREES.items():
    if name == ENG:
        continue
    scan_external(KNOWN[name], tree, "/tests/" in rel(KNOWN[name]) or KNOWN[name].name == "conftest.py")
for p in OUTSIDE_FILES + TEST_FILES:
    try:
        tree = ast.parse(read(p))
    except SyntaxError:
        continue
    scan_external(p, tree, rel(p).startswith("tests/"))
for gm in game_methods:
    src = ext_src.get(gm["name"], Counter())
    tst = ext_tests.get(gm["name"], Counter())
    gm["ext_callers"] = dict(sorted(src.items()))
    gm["ext_test_files"] = len(tst)
    gm["ext_test_refs"] = sum(tst.values())
    gm["ext_test_sample"] = sorted(tst)[:12]
    gm["patched_in"] = sorted(patched.get(gm["name"], ()))

# ───────────────────────── 選項前綴 ─────────────────────────
meth_by_name = {m.name: m for m in method_nodes}
OPTION_CTORS = {"Option", "_cost_option", "Option.model_validate"}


def enclosing_map(tree):
    """節點 id → 包著它的頂層函式／Game 方法名。"""
    owner = {}
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            for b in n.body:
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for x in ast.walk(b):
                        owner[id(x)] = f"{n.name}.{b.name}"
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for x in ast.walk(n):
                owner[id(x)] = n.name
    return owner


def option_id_nodes(tree):
    """Option(id=...)／Option("...")／self._cost_option("...") 的 id 運算式。"""
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        fname = n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id if isinstance(n.func, ast.Name) else ""
        if fname not in ("Option", "_cost_option", "_option", "_shop_option"):
            continue
        idn = next((k.value for k in n.keywords if k.arg in ("id", "option_id")), None)
        if idn is None and n.args:
            idn = n.args[0]
        if idn is not None:
            yield n, idn


prefixes = defaultdict(lambda: {"generated_in": set(), "handled_by": [], "examples": set(), "mentioned_in": set()})
unresolved_option_ids = []
for name, tree in TREES.items():
    if "/tests/" in rel(KNOWN[name]):
        continue
    owner = enclosing_map(tree)
    for call, idn in option_id_nodes(tree):
        head = str_head(idn, name)
        pf = prefix_of(head)
        where = (owner.get(id(call), "<module>") if name == ENG else f"{name.removeprefix('tianxia.')}.{owner.get(id(call), '<module>')}")
        if name == ENG and where.startswith("Game."):
            where = where[5:]
        if pf:
            prefixes[pf]["generated_in"].add(where)
            prefixes[pf]["examples"].add(head)
        else:
            unresolved_option_ids.append({"module": name, "line": call.lineno, "in": where, "id_expr": unparse(idn)[:120]})

# engine 方法裡提到前綴字串的（比較、startswith、字典鍵…）
eng_owner = enclosing_map(eng_tree)
for n in ast.walk(eng_tree):
    if isinstance(n, (ast.Constant, ast.JoinedStr)):
        head = str_head(n, ENG)
        pf = prefix_of(head) if head else None
        if pf and len(head) >= len(pf) + 1:
            w = eng_owner.get(id(n))
            if w:
                prefixes[pf]["mentioned_in"].add(w.removeprefix("Game."))
                prefixes[pf]["examples"].add(head[:40])


def cond_keys(test, kind_var="kind", id_var="option_id"):
    """choose 的條件 → [(類型, 值)]：('kind', 'act')、('id', 'talk:say')、('startswith', 'bounty:')。"""
    out = []
    for n in ast.walk(test):
        if isinstance(n, ast.Compare) and isinstance(n.left, ast.Name) and len(n.ops) == 1:
            var = n.left.id
            comp = n.comparators[0]
            vals = []
            if isinstance(n.ops[0], ast.Eq):
                vals = [str_head(comp, ENG)]
            elif isinstance(n.ops[0], ast.In) and isinstance(comp, (ast.Tuple, ast.List, ast.Set)):
                vals = [str_head(e, ENG) for e in comp.elts]
            for v in vals:
                if v is None:
                    continue
                if var == kind_var:
                    out.append(("kind", v))
                elif var == id_var:
                    out.append(("id", v))
                else:
                    out.append((var, v))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "startswith" \
                and isinstance(n.func.value, ast.Name) and n.args:
            arg = n.args[0]
            elts = arg.elts if isinstance(arg, ast.Tuple) else [arg]
            for e in elts:
                v = str_head(e, ENG)
                if v is not None:
                    out.append(("startswith:" + n.func.value.id, v))
    return out


def body_handlers(stmts, modname=ENG):
    g, mods = [], []
    al = ALIASES[modname]
    for st in stmts:
        for n in ast.walk(st):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name):
                if n.func.value.id == "self" and n.func.attr in GAME_METHODS and n.func.attr not in g:
                    g.append(n.func.attr)
                elif n.func.value.id in al:
                    q = f"{n.func.value.id}.{n.func.attr}"
                    if q not in mods:
                        mods.append(q)
    return [x for x in g if x not in ("_log",)], mods


choose_dispatch = []
for n in ast.walk(meth_by_name["choose"]):
    if isinstance(n, ast.If):
        keys = cond_keys(n.test)
        if not keys:
            continue
        g, mods = body_handlers(n.body)
        choose_dispatch.append({"line": n.lineno, "test": unparse(n.test)[:200], "keys": [f"{k}={v}" for k, v in keys],
                                "game_methods": g, "module_calls": mods})
act_dispatch = []
for n in ast.walk(meth_by_name["_act"]):
    if isinstance(n, ast.If):
        keys = cond_keys(n.test, kind_var="what", id_var="__none__")
        if not keys:
            continue
        g, mods = body_handlers(n.body)
        act_dispatch.append({"line": n.lineno, "test": unparse(n.test)[:200], "keys": [f"{k}={v}" for k, v in keys],
                             "game_methods": g, "module_calls": mods})

for d in choose_dispatch:
    for k in d["keys"]:
        typ, _, v = k.partition("=")
        pf = v if typ == "kind" else prefix_of(v)
        if typ == "kind" and v:
            pf = v
        if not pf:
            continue
        prefixes[pf]["handled_by"].append({"where": "choose", "line": d["line"], "cond": k, "game_methods": d["game_methods"],
                                           "module_calls": d["module_calls"]})
for d in act_dispatch:
    for k in d["keys"]:
        typ, _, v = k.partition("=")
        if typ in ("kind", "startswith:what"):
            prefixes["act"]["handled_by"].append({"where": "_act", "line": d["line"], "cond": f"act:{v}" + ("*" if typ != "kind" else ""),
                                                  "game_methods": d["game_methods"], "module_calls": d["module_calls"]})

# 功能包：prefix 與 bot_always
feature_pkgs = []
for p in sorted((TX / "features").glob("*/__init__.py")):
    name = modname_of(p)
    tree = TREES[name]
    info = {"package": name, "path": rel(p.parent), "prefix": None, "bot_always": [], "web": [], "content": [], "player_fields": [],
            "carried": []}
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef):
            for b in n.body:
                tgt = b.targets[0] if isinstance(b, ast.Assign) else b.target if isinstance(b, ast.AnnAssign) else None
                if isinstance(tgt, ast.Name) and getattr(b, "value", None) is not None:
                    if tgt.id == "prefix":
                        info["prefix"] = static_str(b.value, name)
                    elif tgt.id in ("bot_always", "web", "content", "player_fields", "carried"):
                        try:
                            info[tgt.id] = list(ast.literal_eval(b.value))
                        except Exception:
                            info[tgt.id] = [unparse(b.value)]
    files = sorted(rel(f) for f in p.parent.rglob("*") if f.is_file() and "__pycache__" not in f.parts)
    info["files"] = files
    info["lines_py_nontest"] = sum(nlines(read(f)) for f in p.parent.rglob("*.py") if "tests" not in f.parts)
    feature_pkgs.append(info)
    if info["prefix"]:
        prefixes[info["prefix"]]["handled_by"].append({"where": f"features_core.choose → {name}", "line": 0, "cond": f"kind={info['prefix']}",
                                                       "game_methods": [], "module_calls": []})


# 處理方法裡照 arg 分的子動詞（啟發式：比較第一個參數、或從它 partition/split 出來的名字）
def sub_verbs(fn):
    params = [a.arg for a in fn.args.args if a.arg != "self"]
    if not params:
        return []
    watch = {params[0]}
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and isinstance(n.value, (ast.Subscript, ast.Call)):
            src = unparse(n.value)
            if any(src.startswith(f"{w}.partition") or src.startswith(f"{w}.split") or src.startswith(f"{w}.rpartition")
                   for w in list(watch)):
                for t in n.targets:
                    for x in ast.walk(t):
                        if isinstance(x, ast.Name):
                            watch.add(x.id)
    verbs = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Compare) and isinstance(n.left, ast.Name) and n.left.id in watch:
            for op, comp in zip(n.ops, n.comparators):
                elts = comp.elts if isinstance(comp, (ast.Tuple, ast.List, ast.Set)) and isinstance(op, (ast.In, ast.NotIn)) else [comp]
                for e in elts:
                    v = str_head(e, ENG)
                    if v is not None and v not in verbs:
                        verbs.append(v)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "startswith" \
                and isinstance(n.func.value, ast.Name) and n.func.value.id in watch and n.args:
            elts = n.args[0].elts if isinstance(n.args[0], ast.Tuple) else [n.args[0]]
            for e in elts:
                v = str_head(e, ENG)
                if v is not None and v + "*" not in verbs:
                    verbs.append(v + "*")
    return verbs


option_prefixes = []
for pf in sorted(prefixes):
    d = prefixes[pf]
    handlers = []
    for h in d["handled_by"]:
        handlers.append(h)
    main = []
    for h in handlers:
        for gname in h["game_methods"]:
            if gname not in main:
                main.append(gname)
    verbs = {}
    for h in handlers:
        if h["where"] == "choose" and h["cond"] == f"kind={pf}":
            for gname in h["game_methods"][:1]:
                if gname in meth_by_name:
                    verbs[gname] = sub_verbs(meth_by_name[gname])
    owner_pkg = next((f["package"] for f in feature_pkgs if f["prefix"] == pf), None)
    option_prefixes.append(OrderedDict(
        prefix=pf + ":", handler_methods=main, dispatch=handlers, sub_verbs=verbs,
        generated_in=sorted(d["generated_in"]), mentioned_in_methods=sorted(d["mentioned_in"])[:60],
        mentioned_count=len(d["mentioned_in"]), examples=sorted(d["examples"])[:25], feature_package=owner_pkg,
    ))

# ───────────────────────── server.py ─────────────────────────
SRV = WT / "server.py"
srv_text = read(SRV)
srv_tree = ast.parse(srv_text)
srv_alias = outside_alias.get("server.py", {})
srv_module_names = set()
for node, ctx in iter_imports(srv_tree):
    if isinstance(node, ast.Import):
        for a in node.names:
            srv_module_names.add(a.asname or a.name.split(".")[0])
    else:
        for a in node.names:
            srv_module_names.add(a.asname or a.name)
srv_funcs = {n.name: n for n in srv_tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
HTTP = {"get", "post", "put", "delete", "patch", "api_route", "websocket", "head", "options"}


def game_calls_in(node, module_names=srv_module_names):
    out, recv = [], Counter()
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute) and n.attr in GAME_METHODS and isinstance(n.value, ast.Name) \
                and n.value.id not in module_names:
            if n.attr not in out:
                out.append(n.attr)
            recv[n.value.id] += 1
        elif isinstance(n, ast.Attribute) and n.attr in GAME_METHODS and isinstance(n.value, ast.Call) \
                and isinstance(n.value.func, ast.Name) and n.value.func.id in ("_game", "_locked"):
            if n.attr not in out:
                out.append(n.attr)
            recv[n.value.func.id + "()"] += 1
    return out, recv


def server_calls_in(node, funcs=srv_funcs):
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id in funcs and n.id not in out:
            out.append(n.id)
    return out


# 頂層的動作表：{op: lambda g, b: g.xxx(...)}
srv_tables = {}
for n in srv_tree.body:
    if isinstance(n, (ast.Assign, ast.AnnAssign)):
        tgt = n.targets[0] if isinstance(n, ast.Assign) else n.target
        val = n.value
        if isinstance(tgt, ast.Name) and isinstance(val, ast.Dict) and val.keys and \
                any(isinstance(v, (ast.Lambda, ast.Name, ast.Attribute)) for v in val.values):
            ops = OrderedDict()
            for k, v in zip(val.keys, val.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    gc, _ = game_calls_in(v)
                    ops[k.value] = {"line": k.lineno, "game_methods": gc, "server_funcs": [f for f in server_calls_in(v)]}
            if ops:
                srv_tables[tgt.id] = {"start": n.lineno, "end": n.end_lineno, "lines": n.end_lineno - n.lineno + 1, "ops": ops}
        elif isinstance(tgt, ast.Name) and isinstance(val, ast.Call) and unparse(val.func) in ("frozenset", "set"):
            try:
                items = sorted(ast.literal_eval(val.args[0])) if val.args else []
                srv_tables.setdefault("_sets", {})[tgt.id] = {"line": n.lineno, "items": items}
            except Exception:
                pass


def route_of(fn, owner_label: str):
    routes = []
    for d in fn.decorator_list:
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in HTTP:
            path = d.args[0].value if d.args and isinstance(d.args[0], ast.Constant) else unparse(d.args[0]) if d.args else ""
            methods = [d.func.attr.upper()]
            for k in d.keywords:
                if k.arg == "methods":
                    try:
                        methods = list(ast.literal_eval(k.value))
                    except Exception:
                        methods = [unparse(k.value)]
            routes.append((path, methods, unparse(d.func.value)))
    return routes


server_routes = []
server_other = []
route_handlers = []
for n in srv_tree.body:
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        rs = route_of(n, "server")
        s, e = span(n)
        gc, recv = game_calls_in(n)
        sc = [f for f in server_calls_in(n) if f != n.name]
        if rs:
            for path, methods, obj in rs:
                server_routes.append(OrderedDict(path=path, methods=methods, handler=n.name, source="server.py", start=s, end=e,
                                                 lines=e - s + 1, calls_game=gc, calls_server=sc, receivers=dict(recv)))
            route_handlers.append(n)
        else:
            server_other.append(OrderedDict(name=n.name, start=s, end=e, lines=e - s + 1,
                                            decorators=[unparse(d) for d in n.decorator_list], calls_game=gc, calls_server=sc))
    elif isinstance(n, ast.ClassDef):
        s, e = span(n)
        server_other.append(OrderedDict(name=n.name, kind="class", start=s, end=e, lines=e - s + 1,
                                        decorators=[unparse(d) for d in n.decorator_list], calls_game=[], calls_server=[]))

# 功能包的路由（features/*/routes.py 的 router(shell) 裡 @r.get…）
for p in sorted((TX / "features").glob("*/routes.py")):
    name = modname_of(p)
    tree = TREES[name]
    mods = set(ALIASES[name]) | set(FROM_NAMES[name])
    for node, ctx in iter_imports(tree):
        for a in node.names:
            mods.add(a.asname or a.name.split(".")[0])
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            rs = route_of(n, name)
            if rs:
                s, e = span(n)
                gc, recv = game_calls_in(n, mods)
                shell_calls = sorted({x.attr for x in ast.walk(n) if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name)
                                      and x.value.id == "shell"})
                for path, methods, obj in rs:
                    server_routes.append(OrderedDict(path=path, methods=methods, handler=n.name, source=rel(p), start=s, end=e,
                                                     lines=e - s + 1, calls_game=gc, calls_server=shell_calls, receivers=dict(recv)))

# 路由的子分派（op == "x"）與動作表
for r in server_routes:
    if r["source"] != "server.py":
        continue
    fn = srv_funcs[r["handler"]]
    params = [a.arg for a in fn.args.args]
    subs, tables = [], []
    for n in ast.walk(fn):
        if isinstance(n, ast.If):
            t = n.test
            if isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) and t.left.id in params and len(t.ops) == 1:
                comp = t.comparators[0]
                if isinstance(t.ops[0], ast.Eq) and isinstance(comp, ast.Constant):
                    gc, _ = game_calls_in(ast.Module(body=n.body, type_ignores=[]))
                    sc = server_calls_in(ast.Module(body=n.body, type_ignores=[]))
                    subs.append({"value": comp.value, "line": n.lineno, "calls_game": gc, "calls_server": sc})
                elif isinstance(t.ops[0], ast.In) and isinstance(comp, ast.Name):
                    tables.append(comp.id)
        if isinstance(n, ast.Name) and n.id in srv_tables and n.id not in tables:
            tables.append(n.id)
    if subs:
        r["sub_ops"] = subs
    if tables:
        r["tables"] = tables
        via = []
        for tname in tables:
            for op, info in srv_tables.get(tname, {}).get("ops", {}).items():
                for gname in info["game_methods"]:
                    if gname not in via:
                        via.append(gname)
        r["calls_game_via_tables"] = via

# 殼的共用管線（被 8 條以上路由直接叫的）與經過其餘殼函式的遞移呼叫
helper_use = Counter()
for r in server_routes:
    if r["source"] == "server.py":
        for f in r["calls_server"]:
            helper_use[f] += 1
COMMON = {f for f, c in helper_use.items() if c >= 8}
srv_direct = {f["name"]: f for f in server_other if f.get("kind") != "class"}
for r in server_routes:
    if r["source"] != "server.py":
        continue
    seen, stack, via = set(), [f for f in r["calls_server"] if f not in COMMON], []
    while stack:
        f = stack.pop()
        if f in seen or f in COMMON or f not in srv_direct:
            continue
        seen.add(f)
        for gname in srv_direct[f]["calls_game"]:
            if gname not in via and gname not in r["calls_game"]:
                via.append(gname)
        stack.extend(srv_direct[f]["calls_server"])
    r["calls_game_via_helpers"] = via
    r["helpers_followed"] = sorted(seen)

srv_misc = []
for n in srv_tree.body:
    if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and unparse(n.value.func) in ("app.mount", "app.include_router",
                                                                                             "app.add_middleware"):
        srv_misc.append({"line": n.lineno, "call": unparse(n.value)[:160]})
    if isinstance(n, ast.For):
        for x in ast.walk(n):
            if isinstance(x, ast.Call) and unparse(x.func) == "app.include_router":
                srv_misc.append({"line": x.lineno, "call": unparse(n)[:200]})

# ───────────────────────── web ─────────────────────────
TEXT_EXT = {".js", ".css", ".html", ".webmanifest", ".svg", ".json", ".txt", ".md"}


def js_scan(src: str):
    """回每一行開頭的狀態（mode、depth）與結構字元事件 [(idx, ch, depth_after)]（只收程式碼裡的）。"""
    n = len(src)
    i = 0
    mode = "code"  # code / line / block / sq / dq / tmpl / re / reclass
    stack = []  # 樣板的 ${ 層：每層記那一層的 brace 數
    depth = 0
    line_state = [("code", 0)]
    events = []
    prev_sig = ""  # 程式碼裡上一個有意義的字元或字

    def regex_ok(prev):
        if prev == "":
            return True
        if prev in "(,=:[!&|?{};+-*%<>~^":
            return True
        if prev in ("return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw", "instanceof",
                    "yield", "await", "}"):
            return True
        return False

    word = ""
    while i < n:
        c = src[i]
        if c == "\n":
            if mode == "line":
                mode = "code"
            line_state.append((mode, depth))
            i += 1
            if word:
                prev_sig, word = word, ""
            continue
        if mode == "code":
            if c.isalnum() or c in "_$":
                word += c
                i += 1
                continue
            if word:
                prev_sig, word = word, ""
            if c in " \t\r":
                i += 1
                continue
            if c == "/" and i + 1 < n and src[i + 1] == "/":
                mode = "line"
                i += 2
                continue
            if c == "/" and i + 1 < n and src[i + 1] == "*":
                mode = "block"
                i += 2
                continue
            if c == "/":
                if regex_ok(prev_sig):
                    mode = "re"
                    i += 1
                    continue
                prev_sig = "/"
                i += 1
                continue
            if c == "'":
                mode = "sq"
            elif c == '"':
                mode = "dq"
            elif c == "`":
                mode = "tmpl"
            elif c in "({[":
                depth += 1
                if c == "{" and stack:
                    stack[-1] += 1
                events.append((i, c, depth))
                prev_sig = c
            elif c in ")}]":
                if c == "}" and stack and stack[-1] == 0:
                    stack.pop()
                    depth -= 1
                    mode = "tmpl"
                    i += 1
                    continue
                if c == "}" and stack:
                    stack[-1] -= 1
                depth -= 1
                events.append((i, c, depth))
                prev_sig = c if c != ")" else ")"
            elif c == ";":
                events.append((i, c, depth))
                prev_sig = c
            else:
                prev_sig = c
            i += 1
            continue
        if mode == "block":
            if c == "*" and i + 1 < n and src[i + 1] == "/":
                mode = "code"
                i += 2
                continue
            i += 1
            continue
        if mode == "line":
            i += 1
            continue
        if mode in ("sq", "dq"):
            if c == "\\":
                i += 2
                continue
            if (mode == "sq" and c == "'") or (mode == "dq" and c == '"'):
                mode = "code"
                prev_sig = "str"
            i += 1
            continue
        if mode == "tmpl":
            if c == "\\":
                i += 2
                continue
            if c == "`":
                mode = "code"
                prev_sig = "str"
                i += 1
                continue
            if c == "$" and i + 1 < n and src[i + 1] == "{":
                stack.append(0)
                depth += 1
                mode = "code"
                prev_sig = "{"
                i += 2
                continue
            i += 1
            continue
        if mode == "re":
            if c == "\\":
                i += 2
                continue
            if c == "[":
                mode = "reclass"
            elif c == "/":
                mode = "code"
                prev_sig = "re"
                i += 1
                while i < n and (src[i].isalpha()):
                    i += 1
                continue
            i += 1
            continue
        if mode == "reclass":
            if c == "\\":
                i += 2
                continue
            if c == "]":
                mode = "re"
            i += 1
            continue
    return line_state, events, depth, mode


DECL_RE = re.compile(r"^(?:export\s+)?(?:(async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)|(const|let|var)\s+([A-Za-z_$][\w$]*|\{[^}]*\}|\[[^\]]*\])\s*=\s*(.?)|class\s+([A-Za-z_$][\w$]*))")


def js_toplevel(src: str):
    lines = src.split("\n")
    line_state, events, end_depth, end_mode = js_scan(src)
    offsets = [0]
    for ln in lines:
        offsets.append(offsets[-1] + len(ln) + 1)

    def line_of(idx):
        lo, hi = 0, len(offsets) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if offsets[mid] <= idx:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    starts = []  # 頂層宣告開頭的行（0 起算）：行首在 depth 0 的程式碼裡（app.js 的頂層照舊縮兩格，不看欄位）
    for li, ln in enumerate(lines):
        mode, d = line_state[li]
        if mode != "code" or d != 0 or not ln.strip():
            continue
        if DECL_RE.match(ln.lstrip()):
            starts.append(li)
    decls = []
    ev_idx = 0
    for k, li in enumerate(starts):
        ln = lines[li].lstrip()
        m = DECL_RE.match(ln)
        if not m:
            continue
        start_off = offsets[li] + (len(lines[li]) - len(ln))
        nxt = starts[k + 1] if k + 1 < len(starts) else len(lines)
        limit_off = offsets[nxt]
        # 找結尾
        while ev_idx < len(events) and events[ev_idx][0] < start_off:
            ev_idx += 1
        end_off = None
        end_by = "next_decl"
        if m.group(2) or m.group(6):  # function／class：本體的 { 回到 0
            opened = False
            for idx, ch, d in events[ev_idx:]:
                if idx >= limit_off and not opened:
                    break
                if ch == "{" and d == 1:
                    opened = True
                if opened and ch == "}" and d == 0:
                    end_off = idx
                    end_by = "brace"
                    break
        else:
            for idx, ch, d in events[ev_idx:]:
                if idx >= limit_off:
                    break
                if ch == ";" and d == 0:
                    end_off = idx
                    end_by = "semicolon"
                    break
        if end_off is None:  # 沒分號：下一個頂層宣告前最後一行有程式的
            e = nxt - 1
            while e > li and (not lines[e].strip() or lines[e].lstrip().startswith("//")):
                e -= 1
            end_line = e + 1
        else:
            end_line = line_of(end_off)
        if m.group(2):
            kind, name = ("async function" if m.group(1) else "function"), m.group(2)
        elif m.group(6):
            kind, name = "class", m.group(6)
        else:
            first = m.group(5)
            rest = ln[m.end(4):]
            after = rest.split("=", 1)[1].strip() if "=" in rest else ""
            if first == "{":
                vk = "object"
            elif first == "[":
                vk = "array"
            elif re.match(r"^(async\s*)?(\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", after) or after.startswith("function") \
                    or after.startswith("async function") or re.match(r"^async\s*\(", after):
                vk = "arrow/function"
            elif after.startswith("new "):
                vk = "new"
            elif after[:1] in "'\"`":
                vk = "string"
            elif re.match(r"^-?\d", after):
                vk = "number"
            else:
                vk = "other"
            kind, name = f"{m.group(3)} {vk}", m.group(4)
        decls.append({"name": name, "kind": kind, "start": li + 1, "end": end_line, "lines": end_line - li, "end_by": end_by})
    return decls, end_depth, end_mode


web_files = []
js_decls = {}
for p in sorted((WT / "web").rglob("*")):
    if not p.is_file():
        continue
    r = rel(p)
    entry = {"path": r, "bytes": p.stat().st_size}
    if p.suffix in TEXT_EXT:
        t = read(p)
        entry["lines"] = nlines(t)
        if p.suffix == ".js":
            decls, d_end, m_end = js_toplevel(t.replace("\r\n", "\n"))
            js_decls[r] = {"decls": decls, "scan_end_depth": d_end, "scan_end_mode": m_end}
            entry["top_functions"] = sum(d["kind"] in ("function", "async function") or d["kind"].endswith("arrow/function") for d in decls)
            entry["top_function_decls"] = sum(d["kind"] in ("function", "async function") for d in decls)
            entry["top_const_objects"] = sum(d["kind"] == "const object" for d in decls)
            entry["top_decls"] = len(decls)
    web_files.append(entry)

# node 驗：每一段頂層宣告單獨編譯得過（vm.Script 只編譯不執行）
TMP.mkdir(parents=True, exist_ok=True)
snips = []
for r, info in js_decls.items():
    src_lines = read(WT / r).replace("\r\n", "\n").split("\n")
    for d in info["decls"]:
        snips.append({"file": r, "name": d["name"], "src": "\n".join(src_lines[d["start"] - 1:d["end"]])})
(TMP / "snips.json").write_text(json.dumps(snips, ensure_ascii=False), encoding="utf-8")
(TMP / "check.js").write_text(r"""
const fs = require('fs'); const vm = require('vm');
const snips = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const bad = [];
for (const s of snips) { try { new vm.Script(s.src); } catch (e) { bad.push({file: s.file, name: s.name, err: String(e.message)}); } }
console.log(JSON.stringify({total: snips.length, bad}));
""", encoding="utf-8")
node_check = None
try:
    out = subprocess.run(["node", str(TMP / "check.js"), str(TMP / "snips.json")], capture_output=True, text=True, encoding="utf-8",
                         timeout=120)
    node_check = json.loads(out.stdout.strip().splitlines()[-1])
except Exception as e:  # noqa: BLE001
    node_check = {"error": repr(e)}

app_js = js_decls.get("web/app.js", {})
web = OrderedDict(
    files=web_files,
    app_js=OrderedDict(
        top_level=app_js.get("decls", []),
        functions=[d for d in app_js.get("decls", []) if d["kind"] in ("function", "async function")],
        const_objects=[d for d in app_js.get("decls", []) if d["kind"] == "const object"],
        scan_end_depth=app_js.get("scan_end_depth"), scan_end_mode=app_js.get("scan_end_mode"),
    ),
    other_js={r: v for r, v in js_decls.items() if r != "web/app.js"},
    node_syntax_check=node_check,
)

# ───────────────────────── content ─────────────────────────
content_files = []
for p in sorted((WT / "content").rglob("*")):
    if not p.is_file():
        continue
    r = rel(p)
    e = {"path": r, "bytes": p.stat().st_size}
    if p.suffix == ".json":
        try:
            data = json.loads(read(p))
            e["json_type"] = type(data).__name__
            e["json_len"] = len(data) if isinstance(data, (list, dict)) else None
            if isinstance(data, dict):
                e["top_keys"] = list(data)[:20]
        except Exception as ex:  # noqa: BLE001
            e["json_error"] = repr(ex)
    if r in REMOVAL_CONTENT:
        e["removal"] = "整套拿掉（週末設定／探索三選一）" if "weekend" in r else "探索三選一用的（整套拿掉時一起看）"
    content_files.append(e)

# ───────────────────────── tests ─────────────────────────


def is_slow_deco(d) -> bool:
    return "slow" in unparse(d)


def test_file_info(p: Path):
    try:
        tree = ast.parse(read(p))
    except SyntaxError:
        return {"file": rel(p), "tests": 0, "slow_tests": 0, "error": "syntax"}
    file_slow = False
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in n.targets):
            if "slow" in unparse(n.value):
                file_slow = True
    tests = slow = 0

    def visit(body, cls_slow=False):
        nonlocal tests, slow
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_"):
                tests += 1
                if file_slow or cls_slow or any(is_slow_deco(d) for d in n.decorator_list):
                    slow += 1
            elif isinstance(n, ast.ClassDef):
                visit(n.body, cls_slow or any(is_slow_deco(d) for d in n.decorator_list))
    visit(tree.body)
    tx_imps = sorted(t.removeprefix("tianxia.") for t in outside_imports.get(rel(p), set()))
    if not tx_imps:
        name = modname_of(p) if p.is_relative_to(TX) else None
        if name in MODULE_IMPORTS:
            imps = MODULE_IMPORTS[name]
            tx_imps = sorted(t.removeprefix("tianxia.") for t in imps["top"] | imps["lazy"] | imps["type_checking"])
    return {"file": rel(p), "tests": tests, "slow_tests": slow, "file_slow": file_slow, "imports_tianxia": tx_imps,
            "lines": nlines(read(p))}


tests_dirs = OrderedDict()
test_files_detail = []
roots = [("tests", WT / "tests")] + [(rel(d), d) for d in sorted((TX / "features").glob("*/tests"))]
for label, root in roots:
    groups = defaultdict(list)
    for p in sorted(root.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        relp = p.relative_to(root)
        key = f"{label}/{relp.parts[0]}" if len(relp.parts) > 1 else f"{label}/（根）"
        groups[key].append(p)
    for key, files in groups.items():
        pys = [f for f in files if f.suffix == ".py"]
        infos = [test_file_info(f) for f in pys]
        test_files_detail.extend(infos)
        tests_dirs[key] = {"files": len(files), "py_files": len(pys), "test_files": sum(f.name.startswith("test_") for f in pys),
                           "test_functions": sum(i["tests"] for i in infos), "slow_test_functions": sum(i["slow_tests"] for i in infos)}
# 其他資料夾在 tianxia 底下的測試數（features 已含）
tests_total = {"files": sum(v["test_files"] for v in tests_dirs.values()),
               "test_functions": sum(v["test_functions"] for v in tests_dirs.values()),
               "slow_test_functions": sum(v["slow_test_functions"] for v in tests_dirs.values())}

# ───────────────────────── bot_policy.score ─────────────────────────
BP = "tianxia.bot_policy"
bp_tree = TREES[BP]
score_fn = next(n for n in bp_tree.body if isinstance(n, ast.FunctionDef) and n.name == "score")


def bp_keys(test):
    out = []
    for n in ast.walk(test):
        if isinstance(n, ast.Compare) and isinstance(n.left, ast.Name) and len(n.ops) == 1:
            comp = n.comparators[0]
            if isinstance(n.ops[0], ast.Eq):
                v = str_head(comp, BP)
                out.append((n.left.id, v if v is not None else unparse(comp)))
            elif isinstance(n.ops[0], ast.In) and isinstance(comp, (ast.Tuple, ast.List, ast.Set)):
                for e in comp.elts:
                    v = str_head(e, BP)
                    out.append((n.left.id, v if v is not None else unparse(e)))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "startswith" and n.args:
            elts = n.args[0].elts if isinstance(n.args[0], ast.Tuple) else [n.args[0]]
            for e in elts:
                v = str_head(e, BP)
                out.append((unparse(n.func.value) + ".startswith", v if v is not None else unparse(e)))
    return out


segments = []
for st in score_fn.body:
    if isinstance(st, ast.If):
        keys = bp_keys(st.test)
        seg = OrderedDict(prefixes=sorted({v + ":" for k, v in keys if k == "kind" and v}), test=unparse(st.test)[:160],
                          start=st.lineno, end=st.end_lineno, lines=st.end_lineno - st.lineno + 1)
        if any(k == "kind" and v == "act" for k, v in keys):
            subs = []
            for sub in st.body:
                if isinstance(sub, ast.If):
                    sk = bp_keys(sub.test)
                    subs.append({"ids": sorted({("act:" + v + ("*" if "startswith" in k else "")) for k, v in sk if k in ("arg", "arg.startswith") and v}),
                                 "test": unparse(sub.test)[:140], "start": sub.lineno, "end": sub.end_lineno})
            seg["act_branches"] = subs
        segments.append(seg)
    elif isinstance(st, (ast.Assign, ast.Expr, ast.Return)):
        segments.append(OrderedDict(prefixes=[], test=None, stmt=unparse(st)[:160], start=st.lineno, end=st.end_lineno,
                                    lines=st.end_lineno - st.lineno + 1))

# bot_policy、bot 其他函式裡提到的前綴
other_refs = []
for modn in ("tianxia.bot_policy", "tianxia.bot", "tianxia.bot_runner"):
    tree = TREES[modn]
    for fn in tree.body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or (modn == BP and fn.name == "score"):
            continue
        found = []
        for n in ast.walk(fn):
            if isinstance(n, (ast.Constant, ast.JoinedStr)):
                h = str_head(n, modn)
                pf = prefix_of(h) if h else None
                if pf and h not in [f[0] for f in found]:
                    found.append((h[:30], n.lineno))
        if found:
            s, e = span(fn)
            other_refs.append({"module": modn.removeprefix("tianxia."), "function": fn.name, "start": s, "end": e,
                               "prefix_strings": [{"s": h, "line": ln} for h, ln in found]})

bot_policy = OrderedDict(score=OrderedDict(start=span(score_fn)[0], end=score_fn.end_lineno,
                                           lines=score_fn.end_lineno - span(score_fn)[0] + 1, segments=segments),
                         other_prefix_refs=other_refs)

# ───────────────────────── 選項前綴（精確版，取代上面的粗略版）─────────────────────────


def ifexp_branches(v):
    if isinstance(v, ast.IfExp):
        return ifexp_branches(v.body) + ifexp_branches(v.orelse)
    if isinstance(v, ast.BoolOp):
        out = []
        for x in v.values:
            out += ifexp_branches(x)
        return out
    return [v]


def find_func(modname, fname):
    tree = TREES.get(modname)
    if tree is None:
        return None
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fname:
            return n
    return None


def call_return_heads(call, modname, depth=0):
    if depth > 2 or not isinstance(call, ast.Call):
        return []
    f = call.func
    target_mod, fn = None, None
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        if f.value.id == "self" and modname == ENG and f.attr in meth_by_name:
            target_mod, fn = ENG, meth_by_name[f.attr]
        elif f.value.id in ALIASES.get(modname, {}):
            target_mod = ALIASES[modname][f.value.id]
            fn = find_func(target_mod, f.attr)
    elif isinstance(f, ast.Name):
        if f.id in FROM_NAMES.get(modname, {}):
            target_mod, orig = FROM_NAMES[modname][f.id]
            fn = find_func(target_mod, orig)
        else:
            target_mod, fn = modname, find_func(modname, f.id)
    if fn is None:
        return []
    heads = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Return) and n.value is not None:
            for v in ifexp_branches(n.value):
                h = str_head(v, target_mod)
                if h is None and isinstance(v, ast.Name):
                    h = next(iter(local_heads(v.id, fn, target_mod, depth + 1)), None)
                if h:
                    heads.append(h)
    return heads


def literal_seq_heads(it, idx, modname):
    """for a, b in ((...), (...))：第 idx 個元素的字頭。it 可以是常數名。"""
    if isinstance(it, ast.Name):
        tree = TREES.get(modname)
        for n in tree.body if tree else []:
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == it.id for t in n.targets):
                it = n.value
                break
    if isinstance(it, (ast.Tuple, ast.List)):
        out = []
        for e in it.elts:
            if isinstance(e, (ast.Tuple, ast.List)) and idx is not None and idx < len(e.elts):
                h = str_head(e.elts[idx], modname)
            else:
                h = str_head(e, modname) if idx is None else None
            if h:
                out.append(h)
        return out
    return []


def local_heads(name, fn, modname, depth=0):
    heads = []
    for n in ast.walk(fn):
        if isinstance(n, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                if isinstance(t, ast.Name) and t.id == name and n.value is not None:
                    for v in ifexp_branches(n.value):
                        h = str_head(v, modname)
                        hs = [h] if h else call_return_heads(v, modname, depth + 1)
                        heads += hs
                elif isinstance(t, ast.Tuple) and isinstance(n.value, ast.Tuple) and len(t.elts) == len(n.value.elts):
                    for te, ve in zip(t.elts, n.value.elts):
                        if isinstance(te, ast.Name) and te.id == name:
                            h = str_head(ve, modname)
                            heads += [h] if h else call_return_heads(ve, modname, depth + 1)
        if isinstance(n, (ast.For, ast.comprehension)):
            tgt = n.target
            if isinstance(tgt, ast.Name) and tgt.id == name:
                heads += literal_seq_heads(n.iter, None, modname)
            elif isinstance(tgt, ast.Tuple):
                for i, e in enumerate(tgt.elts):
                    if isinstance(e, ast.Name) and e.id == name:
                        heads += literal_seq_heads(n.iter, i, modname)
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and depth == 0:
        # 參數：看呼叫端（只在 engine 裡，self.<fn>(...) 的那個位置）
        params = [a.arg for a in fn.args.args]
        if name in params and modname == ENG and fn.name in meth_by_name:
            pos = params.index(name) - 1  # 去掉 self
            for n in ast.walk(eng_tree):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == fn.name \
                        and isinstance(n.func.value, ast.Name) and n.func.value.id == "self":
                    arg = n.args[pos] if 0 <= pos < len(n.args) else next((k.value for k in n.keywords if k.arg == name), None)
                    if arg is not None:
                        h = str_head(arg, ENG)
                        if h:
                            heads.append(h)
                        elif isinstance(arg, ast.Name):
                            caller = meth_by_name.get(eng_owner.get(id(n), "").removeprefix("Game."))
                            if caller is not None:
                                heads += local_heads(arg.id, caller, ENG, depth + 1)
    return heads


def enclosing_fn_nodes(tree):
    owner = {}
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            for b in n.body:
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for x in ast.walk(b):
                        owner[id(x)] = b
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for x in ast.walk(n):
                owner[id(x)] = n
    return owner


P = defaultdict(lambda: {"generated_in": set(), "examples": set(), "dispatch": [], "modules": Counter(), "mentioned_in": set()})
unresolved_option_ids = []
for name, tree in TREES.items():
    if "/tests/" in rel(KNOWN[name]):
        continue
    owner = enclosing_map(tree)
    fnodes = enclosing_fn_nodes(tree)
    for call, idn in option_id_nodes(tree):
        fn = fnodes.get(id(call))
        heads = [h for h in [str_head(idn, name)] if h]
        if not heads and isinstance(idn, ast.Name) and fn is not None:
            heads = local_heads(idn.id, fn, name)
        if not heads and isinstance(idn, ast.Call):
            heads = call_return_heads(idn, name)
        where = owner.get(id(call), "<module>")
        where = where.removeprefix("Game.") if name == ENG else f"{name.removeprefix('tianxia.')}.{where}"
        got = False
        for h in heads:
            pf = prefix_of(h)
            if pf:
                P[pf]["generated_in"].add(where)
                P[pf]["examples"].add(h[:40])
                got = True
        if not got:
            unresolved_option_ids.append({"module": name.removeprefix("tianxia."), "line": call.lineno, "in": where,
                                          "id_expr": unparse(idn)[:120], "heads_found": heads[:5]})

choose_fn = meth_by_name["choose"]
try_node = next(st for st in choose_fn.body if isinstance(st, ast.Try))
chain, node = [], try_node.body[0]
while isinstance(node, ast.If):
    chain.append(node)
    node = node.orelse[0] if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If) else None
chain_ids = {id(n) for n in chain}

choose_dispatch = []
for n in ast.walk(choose_fn):
    if not isinstance(n, ast.If):
        continue
    keys = cond_keys(n.test)
    if not keys:
        continue
    if id(n) in chain_ids:
        phase = "main"
    elif n.lineno < try_node.lineno:
        body_src = "\n".join(unparse(b) for b in n.body)
        phase = "pre-guard" if "Refused" in body_src or "_fight_gone" in body_src else "pre"
    else:
        phase = "post"
    g, mods = body_handlers(n.body)
    choose_dispatch.append({"line": n.lineno, "phase": phase, "test": unparse(n.test)[:200], "keys": [f"{k}={v}" for k, v in keys],
                            "game_methods": g, "module_calls": mods})
choose_dispatch.sort(key=lambda d: d["line"])

act_dispatch = []
for n in ast.walk(meth_by_name["_act"]):
    if isinstance(n, ast.If):
        keys = cond_keys(n.test, kind_var="what", id_var="__none__")
        keys = [(k, v) for k, v in keys if k in ("kind", "startswith:what")]
        if not keys:
            continue
        g, mods = body_handlers(n.body)
        act_dispatch.append({"line": n.lineno, "ids": [("act:" + v + ("*" if k != "kind" else "")) for k, v in keys],
                             "test": unparse(n.test)[:200], "game_methods": g, "module_calls": mods})
act_dispatch.sort(key=lambda d: d["line"])

OPTION_KINDS = set()
for d in choose_dispatch:
    for k in d["keys"]:
        typ, _, v = k.partition("=")
        pf = v if typ == "kind" else prefix_of(v) if typ in ("id", "startswith:option_id") else None
        if not pf:
            continue
        if typ == "kind" and d["phase"] != "post":
            OPTION_KINDS.add(pf)
        elif typ != "kind":
            OPTION_KINDS.add(pf)
        P[pf]["dispatch"].append({"where": "choose", "phase": d["phase"], "line": d["line"], "cond": k,
                                  "game_methods": d["game_methods"], "module_calls": d["module_calls"]})
OPTION_KINDS |= {pf for pf, v in P.items() if v["generated_in"]}
OPTION_KINDS |= {f["prefix"] for f in feature_pkgs if f["prefix"]}

# 每一個 tianxia 模組（非測試）裡提到 "<前綴>:" 的字串
for name, tree in TREES.items():
    if "/tests/" in rel(KNOWN[name]) or name == ENG:
        continue
    for n in ast.walk(tree):
        if isinstance(n, (ast.Constant, ast.JoinedStr)):
            h = str_head(n, name)
            pf = prefix_of(h) if isinstance(h, str) else None
            if pf in OPTION_KINDS:
                P[pf]["modules"][name.removeprefix("tianxia.")] += 1
for n in ast.walk(eng_tree):
    if isinstance(n, (ast.Constant, ast.JoinedStr)):
        h = str_head(n, ENG)
        pf = prefix_of(h) if isinstance(h, str) else None
        if pf:
            w = eng_owner.get(id(n))
            if w:
                P[pf]["mentioned_in"].add(w.removeprefix("Game."))

option_prefixes = []
other_prefix_like = []
for pf in sorted(P):
    d = P[pf]
    disp = d["dispatch"]
    handlers = []
    for x in disp:
        if x["phase"] in ("main", "pre"):
            for gname in x["game_methods"] or []:
                if gname not in handlers:
                    handlers.append(gname)
            if not x["game_methods"]:
                for mc in x["module_calls"]:
                    if mc not in handlers:
                        handlers.append(mc)
    pkg = next((f["package"] for f in feature_pkgs if f["prefix"] == pf), None)
    if pkg:
        handlers.insert(0, f"{pkg}（features_core.choose，Game.choose 第 {choose_fn.lineno} 行起的 taken）")
    verbs = {}
    main_kind = [x for x in disp if x["phase"] == "main" and x["cond"] == f"kind={pf}"]
    for x in main_kind:
        for gname in x["game_methods"][:1]:
            verbs[gname] = sub_verbs(meth_by_name[gname])
    entry = OrderedDict(
        prefix=pf + ":",
        handler_methods=handlers,
        dispatch=disp,
        after_hooks=[{"line": x["line"], "cond": x["cond"], "game_methods": x["game_methods"]} for x in disp if x["phase"] == "post"],
        stale_guards=[{"line": x["line"], "cond": x["cond"], "module_calls": x["module_calls"]} for x in disp if x["phase"] == "pre-guard"],
        sub_verbs=verbs,
        generated_in=sorted(d["generated_in"]),
        examples=sorted(d["examples"])[:30],
        engine_methods_mentioning=sorted(d["mentioned_in"])[:80],
        engine_methods_mentioning_count=len(d["mentioned_in"]),
        modules_mentioning=dict(d["modules"].most_common()),
        feature_package=pkg,
        removal="整套拿掉（探索三選一）" if pf == "explore" else None,
    )
    if pf == "act":
        entry["act_sub_dispatch"] = act_dispatch
    (option_prefixes if pf in OPTION_KINDS else other_prefix_like).append(entry)
other_prefix_like = [{"prefix": e["prefix"], "engine_methods_mentioning": e["engine_methods_mentioning"][:20],
                      "examples": e["examples"][:10], "note": "看起來像前綴、但不是選項的類別（子動詞、紀錄鍵、旗標…）"}
                     for e in other_prefix_like]

# 殼的管線：被 5 個以上殼函式／路由直接叫的（遞移時略過，另列它們各自叫的 Game 方法）
callers_of = defaultdict(set)
for r in server_routes:
    if r["source"] == "server.py":
        for f in r["calls_server"]:
            callers_of[f].add("route:" + r["handler"])
for f in server_other:
    for c in f.get("calls_server", []):
        callers_of[c].add(f["name"])
COMMON = {f for f, c in callers_of.items() if len(c) >= 5}
for r in server_routes:
    r.setdefault("calls_game_via_tables", [])
    if r["source"] != "server.py":
        r["calls_game_via_helpers"], r["helpers_followed"] = [], []
        continue
    seen, stack, via = set(), [f for f in r["calls_server"] if f not in COMMON], []
    while stack:
        f = stack.pop()
        if f in seen or f in COMMON or f not in srv_direct:
            continue
        seen.add(f)
        for gname in srv_direct[f]["calls_game"]:
            if gname not in via and gname not in r["calls_game"]:
                via.append(gname)
        stack.extend(srv_direct[f]["calls_server"])
    r["calls_game_via_helpers"] = via
    r["helpers_followed"] = sorted(seen)
    r["plumbing_used"] = sorted(f for f in r["calls_server"] if f in COMMON)
server_plumbing = [{"name": f, "callers": len(callers_of[f]), "calls_game": srv_direct[f]["calls_game"] if f in srv_direct else [],
                    "calls_server": srv_direct[f]["calls_server"] if f in srv_direct else []} for f in sorted(COMMON)]

# ───────────────────────── 寫檔 ─────────────────────────
inventory = OrderedDict(
    meta=OrderedDict(
        worktree=str(WT), commit=subprocess.run(["git", "-C", str(WT), "rev-parse", "--short", "HEAD"], capture_output=True,
                                                text=True).stdout.strip(),
        how="Python ast（server、engine、tianxia 全部）；web/*.js 用自寫的掃描器（字串、樣板、註解、正規式），每一段頂層宣告再用 node vm.Script 單獨編譯驗過",
        notes=[
            "行號都是 1 起算；start 含裝飾器那一行。lines = end - start + 1。",
            "calls_self：方法裡 self.<Game方法>(...) 叫到的（去重、照出現順序）；refs_self_uncalled：當成值傳出去的（callback）。",
            "mod_refs：方法裡用到的 tianxia 模組（模組別名.屬性，或 from 匯入的名字）。",
            "ext_callers：引擎以外（tianxia 其他模組、殼、scripts）用 game./g./ctx. 叫到這個方法的檔案與次數；ext_test_*：測試裡的。",
            "patched_in：測試裡 setattr／monkeypatch.setattr 換掉這個 Game 方法的檔。",
            "server_routes.calls_game：handler 本體（含 lambda）直接叫的 Game 方法；calls_game_via_tables：經 MAIN_ACTIONS 這類動作表；"
            "calls_game_via_helpers：經過殼裡其餘函式遞移叫到的（略過被 5 個以上殼函式／路由直接叫的共用管線，管線另列在 server_plumbing，"
            "路由用到哪幾個寫在 plumbing_used）。",
            "option_prefixes.dispatch：Game.choose 的分派，phase＝pre（try 之前提早 return 的，例 battle、seal、duel）、pre-guard（兩個分頁搶、回 Refused 的）、"
            "main（try 裡那一串 if/elif）、post（做完之後的補記，例 _guide）；handler_methods 只收 pre 與 main。act: 另有 act_sub_dispatch（Game._act 照 what 分）。"
            "sub_verbs 是處理方法裡照 arg 分的字（啟發式，* 表示 startswith）。generated_in：做出這種 id 的 Option(...) 在哪個方法／函式。",
            "other_prefix_like：字串長得像「xxx:」但不是選項類別的（act: 底下的子動詞 challenge:、recruit:，紀錄鍵等）。",
            "removal：企劃者 10/31 只剩 week7、season21；週末設定、不帶設定的 14 天季、探索三選一（explore_modes、gather_llm）整套拿掉，排在搬完六包之後。",
        ],
        removal_modules=sorted(REMOVAL_MODULES), removal_content=sorted(REMOVAL_CONTENT),
    ),
    game_class=OrderedDict(start=gs, end=ge, lines=ge - gs + 1, methods=len(game_methods),
                           method_lines=sum(m["lines"] for m in game_methods), class_attrs=game_class_attrs),
    game_methods=game_methods,
    engine_other=engine_other,
    engine_constants=engine_consts,
    modules=modules,
    module_aliases=module_aliases,
    feature_packages=feature_pkgs,
    server_routes=server_routes,
    server_other=server_other,
    server_tables=srv_tables,
    server_common_helpers=sorted(COMMON),
    server_plumbing=server_plumbing,
    server_misc=srv_misc,
    web=web,
    content=content_files,
    tests=OrderedDict(dirs=tests_dirs, total=tests_total, files=test_files_detail),
    bot_policy=bot_policy,
    option_prefixes=option_prefixes,
    other_prefix_like=other_prefix_like,
    choose_dispatch=choose_dispatch,
    act_dispatch=act_dispatch,
    unresolved_option_ids=unresolved_option_ids,
    receivers_seen=dict(receiver_seen.most_common()),
)
(OUT / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=1), encoding="utf-8")
print("ok", len(game_methods), len(modules), len(server_routes), node_check if isinstance(node_check, dict) and node_check.get("bad") is None
      else (node_check.get("total"), len(node_check.get("bad", []))))
