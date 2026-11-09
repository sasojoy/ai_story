"""殼不再長（架構收尾第 106 批）：`Game`、`server.py`、`web/app.js`、`web/main.js`、`web/style.css`、`content/`、各包 `game_api.py` 長新東西就紅。
企劃者 11/07「最新的commit 都確定有照架構拆分之後就可以進行下一階段開發」；稽核注入 61 種違規、綠 37 種，這個檔補那些綠的。

做法統一：名單鎖現況（同資料夾的 shell_tables.py），**只擋多出來的**，搬走不用改測試；每一條另外看真的掃到東西（現況跟名單有交集），不然永遠綠。
紅的訊息三段：多了什麼、該放哪、要誰點頭。靜態的用語法樹或正規式讀檔，不 import。
"""
from __future__ import annotations

import ast
import fnmatch
import importlib.util
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import pytest
import server
from fastapi.testclient import TestClient
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, _player, cheap_password_hashing, client, fresh_server_memory,
    model_breaker_closed, save_dir, scheduler_off, season_already_open,
)
from shell_tables import (
    ADMIN_NO_GATE,
    APP_JS_CASES,
    APP_JS_FORM_IDS,
    APP_JS_TARGET_IDS,
    APP_JS_TOP,
    CLOCK_OK,
    CONTENT_EVENTS,
    CONTENT_TOP,
    GAME_INIT_ATTRS,
    GAME_METHODS,
    MAIN_JS_TOP,
    NO_LOGIN_ROUTES,
    PLAYER_PLAIN_FIELDS,
    ROUTE_GATE_EXCEPTIONS,
    ROUTES_NO_SWITCH,
    SHELL_APP_CALLS,
    SHELL_ASSIGNED,
    STYLE_CSS_CLASSES,
    VALIDATE_READS,
    WORLD_PLAIN_FIELDS,
)
from starlette.routing import Mount
from test_server_bots import leaks  # FB-673 的掃描器（FORBIDDEN）；conftest 放了 tests/bots 的路徑

from tianxia.core import features as features_core
from tianxia.core.registry import FEATURES

ROOT = Path(__file__).resolve().parents[2]
NOD_ONLY = "真的要留在這裡：企劃者或 Joy 點頭、PR 寫原話"
NOD = f"{NOD_ONLY}，再加進 tests/core/shell_tables.py"


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")


def only_listed(what: str, found, listed, where: str) -> None:
    found = set(found)
    assert found & set(listed), f"{what}一個都沒掃到：掃法壞了，不是真的沒有"
    extra = sorted(found - set(listed), key=str)
    assert not extra, f"{what}多了 {extra}。該放哪：{where}。{NOD}。"


# ── 1. Game ──


def game_class() -> ast.ClassDef:
    return next(n for n in ast.parse(read("tianxia/engine.py")).body if isinstance(n, ast.ClassDef) and n.name == "Game")


def game_methods() -> set[str]:
    """class 本體的 def，加上本體直接寫的名字（`zz = lambda self: …`、`zz = _helper` 一樣是多一個方法；現況只有 MAP_LAYERS）。"""
    names: set[str] = set()
    for node in game_class().body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names |= {sub.id for t in targets for sub in ast.walk(t) if isinstance(sub, ast.Name)}
    return names


def _self_targets(target: ast.AST) -> set[str]:
    """賦值目標裡的 self.x；`self.a, self.b = …` 拆開，`self.x.y = …` 不算 x（那是改 x 裡面的東西）。"""
    if isinstance(target, (ast.Tuple, ast.List)):
        return {name for item in target.elts for name in _self_targets(item)}
    if isinstance(target, ast.Starred):
        return _self_targets(target.value)
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
        return {target.attr}
    return set()


def game_init_attrs() -> set[str]:
    init = next(n for n in game_class().body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    names: set[str] = set()
    for node in ast.walk(init):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                names |= _self_targets(t)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            names |= _self_targets(node.target)
    return names


def test_game_has_no_new_method():
    only_listed("Game 的方法", game_methods(), GAME_METHODS, "邏輯放包的 actions；要給 Game 叫，走包的 game_api.py 的表（tianxia/features/<包>/）")


def test_game_init_has_no_new_attribute():
    only_listed("Game.__init__ 的 self 屬性", game_init_attrs(), GAME_INIT_ATTRS, "暫存旗標由包的 Feature.scratch() 宣告（手冊第十五節 F 波），Game 不加欄位")


# ── 2. app.js、main.js、style.css ──
WEB_HOME = "新鈕、表單、change 放 web/<包>.js（registerClicks、registerForms、registerChanges），畫法放包，樣式放 web/<包>.css（手冊 G9）"


def _load_test_for():
    """scripts/test_for.py 的 _JS_TOP（第 95 批，hunk 照頂層名字挑）：載法跟 tests/core/test_test_for.py 開頭一樣，同一個行程只載一次。"""
    if "test_for" not in sys.modules:
        spec = importlib.util.spec_from_file_location("test_for", ROOT / "scripts" / "test_for.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["test_for"] = module  # dataclass 要從 sys.modules 找得到它的模組
        spec.loader.exec_module(module)
    return sys.modules["test_for"]


def js_top(rel: str) -> set[str]:
    pattern = _load_test_for()._JS_TOP
    return {m.group(1) or m.group(2) for line in read(rel).split("\n") for m in [pattern.match(line)] if m}


def app_js_cases() -> set[str]:
    return set(re.findall(r"""\bcase\s+["'`]([^"'`]+)["'`]\s*:""", read("web/app.js")))


def app_js_form_ids() -> set[str]:
    return set(re.findall(r"""\bform\.id\s*[!=]==?\s*["'`]([^"'`]+)["'`]""", read("web/app.js")))


def app_js_target_ids() -> set[str]:
    return set(re.findall(r"""\btarget\.id\s*[!=]==?\s*["'`]([^"'`]+)["'`]""", read("web/app.js")))


def style_css_classes() -> set[str]:
    css = re.sub(r"/\*.*?\*/", "", read("web/style.css"), flags=re.S)
    names: set[str] = set()
    for selector in re.findall(r"([^{}]+)\{", css):
        if not selector.strip().startswith("@"):
            names |= set(re.findall(r"\.(-?[A-Za-z_][\w-]*)", selector))
    return names


def test_app_js_has_no_new_case():
    only_listed("web/app.js 的 case", app_js_cases(), APP_JS_CASES, WEB_HOME)


def test_app_js_has_no_new_form_id():
    only_listed("web/app.js 認的表單 id", app_js_form_ids(), APP_JS_FORM_IDS, WEB_HOME)


def test_app_js_has_no_new_target_id():
    only_listed("web/app.js 認的 target id", app_js_target_ids(), APP_JS_TARGET_IDS, WEB_HOME)


def test_app_js_has_no_new_top_name():
    only_listed("web/app.js 的頂層名字", js_top("web/app.js"), APP_JS_TOP, WEB_HOME)


def test_main_js_has_no_new_top_name():
    only_listed("web/main.js 的頂層名字", js_top("web/main.js"), MAIN_JS_TOP, WEB_HOME)


def test_style_css_has_no_new_class():
    only_listed("web/style.css 的 class", style_css_classes(), STYLE_CSS_CLASSES, WEB_HOME)


# ── 3. server.py ──


def shell_app_calls() -> set[tuple[str, str]]:
    """server.py 裡所有 app.<屬性>(第一個參數) 的呼叫：裝飾器也是 Call，一套邏輯兩種寫法都抓；`app.router.add_route(…)` 也算（屬性寫成 router.add_route）。"""
    found: set[tuple[str, str]] = set()
    for node in ast.walk(ast.parse(read("server.py"))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        parts: list[str] = []
        at: ast.AST = node.func
        while isinstance(at, ast.Attribute):
            parts.insert(0, at.attr)
            at = at.value
        if isinstance(at, ast.Name) and at.id == "app":
            first = node.args[0] if node.args else None
            text = first.value if isinstance(first, ast.Constant) else (ast.unparse(first) if first is not None else "")
            found.add((".".join(parts), str(text)))
    return found


def test_server_has_no_new_app_call():
    only_listed("server.py 的 app.*", shell_app_calls(), SHELL_APP_CALLS, "路由放包的 routes.py（Feature.routes，手冊 G8～G10），殼不掛新路由")


# ── 4. game_api ──


def game_api_problems() -> tuple[int, list[str]]:
    """(掃到幾個 def, 違規)。表只掛名字：def 去 docstring 只准一句 return 或一個運算式；全檔不准 lambda、三元、比較。"""
    defs, bad = 0, []
    files = sorted((ROOT / "tianxia" / "features").glob("*/game_api.py"))
    assert files, "一個 game_api.py 都沒掃到：掃法壞了"
    for path in files:
        pack = path.parent.name
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.Lambda, ast.IfExp, ast.Compare)):
                bad.append(f"{pack}/game_api.py:{node.lineno} {type(node).__name__}")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs += 1
                body = [s for s in node.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
                if len(body) != 1 or not isinstance(body[0], (ast.Return, ast.Expr)):
                    bad.append(f"{pack}/game_api.py:{node.lineno} def {node.name} 不是一句")
    return defs, bad


def test_game_api_is_only_a_table():
    defs, bad = game_api_problems()
    assert defs, "一個 def 都沒掃到：掃法壞了"
    assert not bad, f"game_api.py 放了邏輯：{bad}。該放哪：邏輯放包的 actions，表只掛名字。{NOD_ONLY}（這一條沒有名單）。"


# ── 5. QUIET ──


def plain_fields(model) -> set[str]:
    from tianxia.state import QUIET

    return {name for name, field in model.model_fields.items() if field.json_schema_extra != QUIET}


QUIET_HOME = "新欄位標 Field(<預設>, json_schema_extra=QUIET)（手冊 G7；空的不寫鍵，舊程式讀得回去；test_gentry_ledgers 扣掉 QUIET 再比，抓不到這個）"


def test_new_player_field_is_quiet():
    from tianxia.state import PlayerState

    only_listed("PlayerState 不標 QUIET 的欄位", plain_fields(PlayerState), PLAYER_PLAIN_FIELDS, QUIET_HOME)


def test_new_world_field_is_quiet():
    from tianxia.state import WorldState

    only_listed("WorldState 不標 QUIET 的欄位", plain_fields(WorldState), WORLD_PLAIN_FIELDS, QUIET_HOME)


# ── 6. 時鐘 ──
CLOCK_TIME = frozenset({"time", "monotonic", "perf_counter", "time_ns", "monotonic_ns", "perf_counter_ns", "process_time"})
CLOCK_DATE = frozenset({"now", "utcnow", "today"})
CLOCK_FORMAT = frozenset({"gmtime", "localtime", "ctime", "asctime", "strftime"})


def clock_reads(tree: ast.AST) -> list[int]:
    """讀電腦時鐘的行號。抓 Attribute 不限 Call：accounts.py 把 time.time 當預設值；`import time as t`、`from datetime import datetime as d` 認得別名。"""
    time_bases, date_bases, lines = {"time", "time_module"}, {"datetime", "date"}, []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "time" and alias.asname:
                    time_bases.add(alias.asname)
                elif alias.name == "datetime" and alias.asname:
                    date_bases.add(alias.asname)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            for alias in node.names:
                if node.module == "time" and alias.name in CLOCK_TIME:
                    lines.append(node.lineno)
                elif node.module == "datetime" and alias.name in ("datetime", "date") and alias.asname:
                    date_bases.add(alias.asname)

    def base_name(value: ast.AST) -> str | None:
        return value.id if isinstance(value, ast.Name) else value.attr if isinstance(value, ast.Attribute) else None

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            base = base_name(node.value)
            if (node.attr in CLOCK_TIME and base in time_bases) or (node.attr in CLOCK_DATE and base in date_bases):
                lines.append(node.lineno)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                name, on_time = func.id, True
            elif isinstance(func, ast.Attribute):
                name, on_time = func.attr, base_name(func.value) in time_bases
            else:
                continue
            allowed = 1 if name == "strftime" else 0  # strftime(格式) 不帶第二個參數也是讀現在
            if name in CLOCK_FORMAT and on_time and len(node.args) <= allowed:
                lines.append(node.lineno)
    return lines


CLOCK_MAYBE = re.compile(r"\bimport\s+time\b|\bfrom\s+time\b|\btime\.|time_module|datetime|\bdate\.|gmtime|localtime|ctime|asctime|strftime")  # 先篩一次，沒有這些字的檔不必解語法樹（整包解一次要快 3 秒）


def clock_map() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for path in sorted((ROOT / "tianxia").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if "/tests/" not in rel and CLOCK_MAYBE.search(text):
            lines = clock_reads(ast.parse(text))
            if lines:
                found[rel] = lines
    return found


def test_nobody_new_reads_the_clock():
    found = clock_map()
    assert any(fnmatch.fnmatch(rel, pattern) for rel in found for pattern in CLOCK_OK), "一處時鐘都沒掃到：掃法壞了，不是真的沒有"
    extra = {rel: lines for rel, lines in found.items() if not any(fnmatch.fnmatch(rel, pattern) for pattern in CLOCK_OK)}
    assert not extra, f"讀電腦時鐘的多了 {extra}。該放哪：引擎不讀電腦時鐘，現在時間用 Game.now（Game.sync(now) 設的），或參數傳 now（CLAUDE.md 原則）。{NOD}。"


# ── 7. 檔名與內容 ──
CONTENT_HOME = "內容放 tianxia/features/<包>/content/，包的 Feature.content 宣告；驗證放包的 check_content（手冊 G8～G10）"


def test_test_file_names_are_unique():
    names = Counter(p.name for base in ("tests", "tianxia/features") for p in (ROOT / base).rglob("test_*.py"))
    assert len(names) > 100, "測試檔沒掃到幾個：掃法壞了"
    same = sorted(name for name, count in names.items() if count > 1)
    assert not same, f"測試檔名重複 {same}。該放哪：tests/conftest.py 把每個資料夾放上 sys.path，檔名全 repo 不能重複（含功能包的測試），換一個名字或併進原本那個檔。這條沒有名單、不開例外。"


def validate_reads() -> set[str]:
    validate = next(n for n in ast.parse(read("tianxia/content.py")).body if isinstance(n, ast.FunctionDef) and n.name == "validate")
    return {n.attr for n in ast.walk(validate) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "c"}


def test_content_top_has_no_new_file():
    only_listed("content/ 頂層", (p.name for p in (ROOT / "content").iterdir()), CONTENT_TOP, CONTENT_HOME)


def test_content_events_has_no_new_file():
    only_listed("content/events/", (p.name for p in (ROOT / "content" / "events").iterdir()), CONTENT_EVENTS, CONTENT_HOME)


def test_validate_reads_no_new_field():
    only_listed("tianxia/content.py 的 validate 讀的 c.<欄位>", validate_reads(), VALIDATE_READS, CONTENT_HOME)


# ── 8. 登入與開關 ──
GATE_HOME = "路由第一行要有 gate，關著丟 404（照 tianxia/features/heroines/routes.py 的 api_adult 開頭）；不用登入的路由要寫理由"


def flat_routes(app) -> list[tuple[str, object]]:
    """(方法, 路由)。這個版本的 FastAPI 把包的 router 包成私有的 _IncludedRouter，有 original_router 就往裡走；Mount（/static）跳過。"""
    out: list[tuple[str, object]] = []

    def walk(routes) -> None:
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                walk(inner.routes)
            elif not isinstance(route, Mount):
                out.extend((method, route) for method in sorted(route.methods - {"HEAD", "OPTIONS"}))

    walk(app.routes)
    return out


def hit(http, method: str, route):
    """路徑參數、查詢參數都填 1，POST 帶空的 json：參數檢查不該比登入先擋（不然 422 會被當成不用登入）。"""
    query = {param.name: "1" for param in route.dependant.query_params}
    return http.request(method, re.sub(r"\{[^}]+\}", "1", route.path), params=query, json={} if method == "POST" else None)


def no_login_replies() -> dict[tuple[str, str], object]:
    """沒 cookie 打每一條路由，不是 401 的留下來。"""
    anon = TestClient(server.app, raise_server_exceptions=False)
    replies = {(method, route.path): hit(anon, method, route) for method, route in flat_routes(server.app)}
    return {key: reply for key, reply in replies.items() if reply.status_code != 401}


def test_no_new_route_works_without_login():
    only_listed("不用登入就打得到的路由", no_login_replies(), NO_LOGIN_ROUTES, GATE_HOME)


ROUTED_PACKS = {feature.name: feature for feature in FEATURES if feature.routes(server) is not None}


def switch_off(name: str, monkeypatch) -> None:
    """把這一包的開關關掉；新包一律 Config.<包>.enabled（new_feature.py 生的 tuning 預設 False）。"""
    config = server.CONTENT.config
    if name in ("mall", "looks"):
        monkeypatch.setattr(config.mall, "enabled", False)
    elif name == "heroines":
        monkeypatch.setattr(server.CONTENT, "heroines", {})
    elif name == "notify":
        monkeypatch.setattr(server, "WEB_PUSH", None)  # start_web_push 沒跑就是關著；同一個行程別的測試可能留著值
    elif name == "zhuan":
        monkeypatch.setattr(config.jianfa, "zhuan_end", False)
    elif name == "smithy":
        monkeypatch.setattr(config.weapons, "enabled", False)
        monkeypatch.setattr(config.armor, "enabled", False)
    else:
        switch = getattr(config, name, None)
        assert switch is not None, f"{name} 有路由，但 Config 沒有 {name}。該放哪：tianxia/core/tuning/{name}.py 的 enabled（new_feature.py 生的）。沒有開關要列進 ROUTES_NO_SWITCH：{NOD_ONLY}。"
        monkeypatch.setattr(switch, "enabled", False)


def test_the_switch_sweep_sees_the_packages():
    assert len(ROUTED_PACKS) > len(ROUTES_NO_SWITCH) >= 1 and set(ROUTED_PACKS) & set(ROUTES_NO_SWITCH), "有路由的包沒掃到幾個：掃法壞了"


@pytest.mark.parametrize("name", sorted(set(ROUTED_PACKS) - set(ROUTES_NO_SWITCH)))
def test_package_routes_are_404_with_the_switch_off(name, monkeypatch):
    player = TestClient(server.app, raise_server_exceptions=False)
    _player(player)
    switch_off(name, monkeypatch)
    routes = flat_routes(ROUTED_PACKS[name].routes(server))
    assert routes, f"{name} 一條路由都沒掃到：掃法壞了"
    replies = {(method, route.path): hit(player, method, route).status_code for method, route in routes}
    extra = {key: status for key, status in replies.items() if status != 404 and key not in ROUTE_GATE_EXCEPTIONS}
    assert not extra, f"{name} 的開關關著，路由還回 {extra}。該放哪：{GATE_HOME}。例外：{NOD_ONLY}，列進 ROUTE_GATE_EXCEPTIONS 寫理由。"


def test_no_new_admin_tool_without_a_gate():
    no_gate = {name for name, tool in server.FEATURE_ADMIN_ACTIONS.items() if tool.gate is features_core.no_gate}
    only_listed("AdminTool 用 no_gate 的工具", no_gate, ADMIN_NO_GATE, "新工具 AdminTool(<開關的 gate>, …)：包的開關關著就不准叫（Feature.admin_tools，tianxia/core/features.py）")


# ── 9. shell 與路由重複 ──


def shell_assigned() -> set[str]:
    """包裡賦值的 shell.<名字>，加 setattr(shell, …)。"""
    found: set[str] = set()

    def targets_of(target: ast.AST):
        if isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                yield from targets_of(item)
        elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "shell":
            yield target.attr

    for path in (ROOT / "tianxia" / "features").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "/tests/" in path.relative_to(ROOT).as_posix() or "shell" not in text:
            continue
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    found.update(targets_of(target))
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                found.update(targets_of(node.target))
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "setattr"
                  and len(node.args) > 1 and isinstance(node.args[0], ast.Name) and node.args[0].id == "shell"):
                second = node.args[1]
                found.add(second.value if isinstance(second, ast.Constant) else ast.unparse(second))
    return found


def test_shell_assigns_no_new_name():
    only_listed("包賦值的 shell.<名字>", shell_assigned(), SHELL_ASSIGNED, "包自己的狀態放包的模組；殼不再長新的模組變數（手冊 G8～G10）")


def test_routes_are_unique():
    routes = flat_routes(server.app)
    own = sum(1 for _, route in routes if route.endpoint.__module__ == "server")
    assert len(routes) - own > own, "看不到 router 裡的路由：掃法壞了，FastAPI 換版要看 flat_routes"
    same = sorted(key for key, count in Counter((method, route.path) for method, route in routes).items() if count > 1)
    assert not same, f"同一個方法加路徑掛了兩次 {same}：後掛的那條永遠走不到。該放哪：換一條路徑，或併進原本那條。這條沒有名單、不開例外。"


# ── 10. 看不出假人 ──


def test_no_login_replies_do_not_say_who_is_a_bot():
    """FB-673 掃 web/；這條掃不用登入就拿得到的回應（body 加 headers）。`name="robots"` 是分享頁 404 的 meta，不算。"""
    replies = no_login_replies()
    assert replies, "一條回應都沒打到：掃法壞了"
    found = {key: hits[:3] for key, reply in replies.items() if (hits := leaks(reply.text.replace('name="robots"', "") + "\n" + str(reply.headers)))}
    assert not found, f"不用登入就看得到假人字樣 {found}。該放哪：任何畫面、回應都不能透露誰是假人（FB-673；CLAUDE.md 原則「伺服器假人跟真人完全一樣」），這條沒有名單、不開例外。"


# ── 15. same_behavior compare --new（整條比對在波末閘門，這裡只驗兩個不開伺服器就看得到的）──


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    from sb import harness as module  # 只走 sb.harness 這條路徑，不要 scripts.sb（同 same_behavior.py 開頭）

    yield module
    module.set_new(())


def test_compare_new_only_hides_the_tables_with_the_package_prefix(harness, tmp_path):
    db = tmp_path / "x.db"
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE players (id INTEGER); CREATE TABLE zzdemo (id INTEGER); CREATE TABLE zzdemo_notes (id INTEGER); CREATE TABLE zz_notes (id INTEGER); CREATE TABLE zzdemos (id INTEGER);")
    con.close()
    harness.set_new(())
    assert "### zzdemo_notes" in harness.db_text(db) and "### zzdemo " in harness.db_text(db)
    harness.set_new(("zzdemo",))
    text = harness.db_text(db)
    assert "### zzdemo_notes" not in text and "### zzdemo " not in text
    assert {"### players", "### zz_notes", "### zzdemos"} <= {line.rsplit(" [", 1)[0] for line in text.split("\n")}  # 沒帶前綴的照紅，免得順手藏掉別的表
    assert harness.NEW["seen"]["表"] == {"zzdemo", "zzdemo_notes"}


def test_compare_new_refuses_a_package_that_is_not_new(harness, tmp_path):
    with pytest.raises(SystemExit, match="不是新包"):
        harness.compare(ROOT, ROOT, tmp_path, ["week7"], 1, False, tracks=["facade"], new=("mall",))
    with pytest.raises(SystemExit, match="head 沒有這一包"):
        harness.compare(ROOT, ROOT, tmp_path, ["week7"], 1, False, tracks=["facade"], new=("zz_no_such_pack",))


def test_compare_new_also_existing_takes_a_package_base_already_has(harness, tmp_path):
    """K 波 --also-existing：同一包的後續批（base 已經有）不帶旗標照舊拒，帶了放行；head 沒有那一包帶了也拒。"""
    with pytest.raises(SystemExit, match="不是新包"):
        harness.compare(ROOT, ROOT, tmp_path, ["week7"], 1, False, tracks=["facade"], new=("identity",))
    harness.check_new(ROOT, ROOT, ("identity", "support"), also_existing=True)
    with pytest.raises(SystemExit, match="head 沒有這一包"):
        harness.check_new(ROOT, ROOT, ("zz_no_such_pack",), also_existing=True)
    cli = (ROOT / "scripts" / "same_behavior.py").read_text(encoding="utf-8")
    assert "also_existing=a.also_existing" in cli and '"--also-existing"' in cli  # compare 子命令收得到、傳得進去
    import inspect  # noqa: PLC0415

    assert "*base_new" in inspect.getsource(harness.compare)  # base 也有這一包：base 的子行程同樣扣，不然 base 多出包自己的行
