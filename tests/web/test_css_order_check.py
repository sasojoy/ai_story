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


def test_a_swap_across_sheets_is_reported_as_a_swap(tmp_path):
    """第 86 批起比所有樣式：base 的 .outer i 在 style.css、.inner i 在 moved.css，head 兩支對調。報的是「先後反了」，不是「多出來」。"""
    js = INNER + '  function card(v) {\n    return `<div class="outer">${innerHtml()}</div>`;\n  }\n'
    outer, inner = ".outer i { color: red; }\n", ".inner i { color: blue; }\n"
    _tree(tmp_path / "base", outer, inner, js)
    _tree(tmp_path / "head", inner, outer, js)
    got = subprocess.run([sys.executable, str(TOOL), str(tmp_path / "base"), str(tmp_path / "head")],
                         capture_output=True, text=True, encoding="utf-8")
    assert got.returncode == 1, got.stdout
    assert "head 多出來的規則： 0" in got.stdout and "base 有、head 不見的規則： 0" in got.stdout
    assert "先後反了又可能打架的規則對： 1" in got.stdout
    assert "base style.css:1、moved.css:1" in got.stdout


def test_not_same_el_only_clears_that_pair(tool):
    """逐對的認定只擋那一對：.glow 是 classList 加的（wild），對別的 class 照舊算可能，工具不會因為這張表變鬆。"""
    assert frozenset(("glow", "mv-fight")) in tool.NOT_SAME_EL
    co = tool.Co({}, set(), {"glow"}, set())
    assert not co.can("glow", "mv-fight") and not co.can("mv-fight", "glow")
    assert co.can("glow", "btn")
    assert co.can("mv-fight", "mv-fight")


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
    """揣摩預覽卡的重數格同時中 .mc-tags i 與 .lv i（權重一樣），要 .lv i 排後面，不然沒亮的那格變成籤的底色與圓角。
    所以 .mc-tags i 留在 web/style.css，.lv i 在 web/cultivation.css，別把前者搬進 web/craft.css（那支載入得比較晚）。"""
    order = re.findall(r'href="/static/([^"]+\.css)"', (ROOT / "web" / "index.html").read_text(encoding="utf-8"))
    text = "\n".join((ROOT / "web" / name).read_text(encoding="utf-8") for name in order)
    assert text.index("\n.mc-tags i {") < text.index("\n.lv i {")


# 第 86 批切走的前綴：這些規則現在在 map.css、shop.css，排在 style.css 後面。.m-gap 不在那一批的範圍，照位置留在 style.css。
# 後面括號那一串沒有前綴、是整個 class 搬走的名字（整個名字比對）；.book-layer、.book-bar、.book-cover 在 style.css 還有本體，不列。
CUT_PREFIXES = re.compile(
    r"\.mv-|\.m-(?!gap(?![\w-]))|\.mapx|\.map-|#map-|\.mdrawer|\.mgrab|\.mbody|\.shop-|\.ring-|\.forge-|\.ledger-"
    r"|\.(?:w-melee|wear-bar|tempers|form-why|pot-slot|flame|pot-out|pot-head|pot-why|cell|reveal-layer|bundle|tapme|first-seal)(?![\w-])"
)


def _selectors(css: str) -> list[str]:
    """每一個大括號前面的那一段（選擇器與 @media 條件）；註解與屬性值不算。"""
    return [s.strip() for s in re.findall(r"([^{};]+)\{", re.sub(r"/\*.*?\*/", "", css, flags=re.S))]


def test_index_loads_style_then_map_then_shop():
    """第 86 批 link 的位置就是行為：這三支排在各包的樣式前面、先後固定。shop.css 刻意不登記成哪一包的（契約測試查不到它），只有這條查 / 有沒有載它。"""
    order = re.findall(r'href="/static/([^"]+\.css)"', (ROOT / "web" / "index.html").read_text(encoding="utf-8"))
    assert order[:3] == ["style.css", "map.css", "shop.css"]


def test_style_css_stays_free_of_the_cut_prefixes():
    """靜默失效（第二輪總表第九節第 3 條）：接在 style.css 尾巴覆寫同權重的輿圖、店面規則，git 不報衝突，但 map.css、shop.css 載入得比較晚，蓋不掉。"""
    hits = [s for s in _selectors((ROOT / "web" / "style.css").read_text(encoding="utf-8")) if CUT_PREFIXES.search(s)]
    assert not hits, f"寫進 web/map.css 或 web/shop.css：它們排在 style.css 後面，寫在 style.css 尾巴蓋不掉：{hits[:5]}"


@pytest.mark.parametrize("css, hits", [
    pytest.param(".shop-layer .x { color: red; }", [".shop-layer .x"], id="plain"),
    pytest.param(":where(.shop-layer) .x { color: red; }", [":where(.shop-layer) .x"], id="where"),
    pytest.param(".card.ring-a, .y { color: red; }", [".card.ring-a, .y"], id="compound"),
    pytest.param("@media (min-width: 641px) {\n  #map-host .x { color: red; }\n}", ["#map-host .x"], id="in-media"),
    pytest.param(".m-foo { color: red; }", [".m-foo"], id="m-other"),
    pytest.param(".m-gap2 { color: red; }", [".m-gap2"], id="m-gap-longer"),
    pytest.param(".m-gap { color: red; }", [], id="m-gap-stays"),
    pytest.param(".xshop-a, .mapping { color: red; }", [], id="other-names"),
    pytest.param(".pot-slot { color: red; }", [".pot-slot"], id="moved-whole"),
    pytest.param(".bundle.g-red { color: red; }", [".bundle.g-red"], id="moved-whole-compound"),
    pytest.param(".cells, .bundle-x, .xflame { color: red; }", [], id="moved-whole-longer-names"),
    pytest.param(".book-layer { color: red; }", [], id="book-stays"),
    pytest.param("/* .shop-layer { } */ .x { background: url(a.shop-b.png); }", [], id="comment-and-value"),
])
def test_the_cut_prefix_check_bites(css, hits):
    assert [s for s in _selectors(css) if CUT_PREFIXES.search(s)] == hits
