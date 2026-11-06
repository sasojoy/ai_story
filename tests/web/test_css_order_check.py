"""scripts/css_order_check.py 自己的測試：0 對才算過，所以它看漏的就是沒人驗的（第 B 波審查：揣摩預覽卡的 .mc-tags i 對 .lv i）。"""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "css_order_check.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("css_order_check_under_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass 要從 sys.modules 找得到自己
    spec.loader.exec_module(module)
    return module


def _tree(root: Path, style: str, moved: str, js: str):
    (root / "web").mkdir(parents=True)
    (root / "web" / "style.css").write_text(style, encoding="utf-8")
    (root / "web" / "moved.css").write_text(moved, encoding="utf-8")
    (root / "web" / "mall.css").write_text("", encoding="utf-8")
    (root / "web" / "index.html").write_text(
        '<link href="/static/style.css"><link href="/static/moved.css"><link href="/static/mall.css">', encoding="utf-8")
    (root / "web" / "page.js").write_text(js, encoding="utf-8")
    (root / "server.py").write_text("", encoding="utf-8")


def _reversed_pair(tmp_path: Path, js: str) -> subprocess.CompletedProcess:
    """base 是 .outer i 在前、.inner i 在後；head 把 .outer i 搬到後面那一支，先後反了。"""
    outer, inner = ".outer i { color: red; }\n", ".inner i { color: blue; }\n"
    _tree(tmp_path / "base", outer + inner, "", js)
    _tree(tmp_path / "head", inner, outer, js)
    return subprocess.run([sys.executable, str(TOOL), str(tmp_path / "base"), str(tmp_path / "head")],
                          capture_output=True, text=True, encoding="utf-8")


INNER = '  const innerHtml = () => `<span class="inner"><i></i></span>`;\n'


@pytest.mark.parametrize("js", [
    pytest.param(INNER + '  function card(v) {\n    return `<div class="outer">${innerHtml()}</div>`;\n  }\n', id="literal"),
    # 先存進區域變數，再放進標籤
    pytest.param(INNER + '  function card(v) {\n    const tags = v.map((t) => `<b>${innerHtml()}</b>`);\n    return `<div class="outer">${tags.join("")}</div>`;\n  }\n', id="local"),
    # 區域變數之後才 push 進去
    pytest.param(INNER + '  function card(v) {\n    const tags = [];\n    if (v) tags.push(innerHtml());\n    return `<div class="outer">${tags.join("")}</div>`;\n  }\n', id="push"),
    # 傳參數給包標籤的函式
    pytest.param(INNER + '  function wrap(body) {\n    return `<div class="outer">${body}</div>`;\n  }\n  function page() {\n    return wrap(innerHtml());\n  }\n', id="param"),
    # 參數傳的是區域變數
    pytest.param(INNER + '  function wrap(body) {\n    return `<div class="outer">${body}</div>`;\n  }\n  function page() {\n    const b = innerHtml();\n    return wrap(b);\n  }\n', id="param-local"),
])
def test_reversed_rules_are_found_through_variables_and_params(tmp_path, js):
    got = _reversed_pair(tmp_path, js)
    assert got.returncode == 1, got.stdout
    assert ".outer i" in got.stdout and ".inner i" in got.stdout


def test_unrelated_elements_stay_quiet(tmp_path):
    # 裡面是別的東西、參數只取資料的欄位：包不到 .inner，不報
    js = INNER + '  function wrap(a) {\n    return `<div class="outer"><i>${a.name}</i></div>`;\n  }\n  function page() {\n    return wrap({ name: "x" }) + innerHtml();\n  }\n'
    got = _reversed_pair(tmp_path, js)
    assert got.returncode == 0, got.stdout


def test_short_prefix_with_a_hyphen_takes_any_data_value(tool):
    assert tool.prefix_hit("k-*", "k-material")
    assert tool.prefix_hit("g-*", "g-redgold")
    assert tool.prefix_hit("t*", "t12")
    assert not tool.prefix_hit("t*", "tabs")  # 沒有連字號的短字根照舊只算短尾巴
    assert not tool.prefix_hit("k-*", "kiln-hub")


def test_prefix_inside_a_hole_counts(tool):
    assert "mood-*" in tool.hole_tokens('a.mood ? ` mood-${a.mood}` : ""')
    assert "k-*" in tool.hole_tokens('kind ? "k-" + kind : ""')


def test_direct_children_of_different_parents_cannot_clash(tool):
    assert tool.sel_of(".muster-head > p").parent == {"muster-head"}
    assert tool.sel_of(".muster-head p").parent == frozenset()
    assert tool.sel_of(".a .b > p").parent == {"b"}


def test_real_sheets_keep_the_level_cells_over_the_tag_pill():
    """揣摩預覽卡的重數格同時中 .mc-tags i 與 .lv i（權重一樣），要 .lv i 排後面，不然沒亮的那格變成籤的底色與圓角。"""
    order = re.findall(r'href="/static/([^"]+\.css)"', (ROOT / "web" / "index.html").read_text(encoding="utf-8"))
    text = "\n".join((ROOT / "web" / name).read_text(encoding="utf-8") for name in order)
    assert text.index("\n.mc-tags i {") < text.index("\n.lv i {")
