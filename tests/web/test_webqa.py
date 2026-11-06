"""scripts/webqa 自己的測試：雜訊表放的是 B、C 波真的出現過的列（鏡名與數字照當時的比對紀錄），看漏的就是沒人驗的。"""
import ast
import gzip
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "webqa"
HOSTS = ("127.0.0.1:8292", "localhost:8293")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"webqa_{name}_under_test", TOOL / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def noise():
    return _load("noise")


@pytest.fixture(scope="module")
def compare():
    pytest.importorskip("PIL")
    sys.path.insert(0, str(TOOL))
    return _load("compare")


# ── 雜訊表 ──

@pytest.mark.parametrize("row, pixels, levels, view", [
    ("016_newbie_c05_now-more", 19, 2, "375-light"),  # (23,671)-(352,673)，B r1 判成雜訊沒嚴格證明的那一條
    ("331_pe_c07_duty-open", 76, 2, "1280"),  # (336,247)-(339,614)，同上
    ("082_pr_c39_melt-mode+melt-mode", 11, 1, "1280"),  # (935,115)-(937,149)，同一份程式跑兩次也會出現（第 77 批第一段量到）
    ("015_newbie_c04_sides-first", 18, 3, "375-light"),
    ("579_ml_c10_mall-tab+look-seg", 33, 10, "375-light"),
])
def test_rounded_corner_rows_of_wave_b_are_anti_aliasing(noise, row, pixels, levels, view):
    assert noise.pixel_class(pixels, levels, view=view) == "aa", row


def test_a_real_looking_difference_is_not_noise(noise):
    assert noise.pixel_class(6647, 212, view="1280") is None  # 340_mt_shuffle：差一個字就是這個量
    assert noise.pixel_class(101, 2, view="375-light") is None  # 過了張數
    assert noise.pixel_class(12, 13, view="375-light") is None  # 過了色階


def test_nothing_is_noise_when_either_side_was_unstable_or_the_dom_differs(noise):
    assert noise.pixel_class(11, 1, view="1280", unstable=True) is None
    assert noise.pixel_class(11, 1, view="1280", clean=False) is None
    assert noise.pixel_class(210000, 200, view="1280", sw_a=1265, sw_b=1280, unstable=True) is None
    assert noise.style_class({"margin-left"}, True, unstable=True) is None


def test_the_scrollbar_only_at_desktop_widths(noise):
    assert noise.pixel_class(210000, 200, view="1280", sw_a=1265, sw_b=1280) == "gutter"  # cl_c08
    assert noise.pixel_class(210000, 200, view="375-light", sw_a=1265, sw_b=1280) is None
    assert noise.pixel_class(210000, 200, view="1280", sw_a=1265, sw_b=1270) is None


def test_used_values_only_when_the_window_looks_the_same(noise):
    assert noise.style_class({"margin-left", "margin-inline-start", "width", "block-size", "perspective-origin"}, True) == "layout-used"  # .shell
    assert noise.style_class({"margin-left"}, False) is None
    assert noise.style_class({"font-size"}, True) is None  # 字級不是版面算出來的：不准跟 *-size 混
    assert noise.style_class({"margin-left", "color"}, True) is None


def test_share_and_chronicle_only_inside_their_rects(noise):
    assert noise.pixel_class(9000, 200, view="375-light", only_share=True) == "share"
    assert noise.pixel_class(9000, 200, view="375-light", only_tale=True) == "tale"
    assert noise.pixel_class(9000, 200, view="375-light") is None


def test_dom_masks(noise):
    hosts = noise.hosts_pattern(HOSTS)
    a = '<a href="http://127.0.0.1:8292/zhuan/AbC?v=1">x</a><div id="toast" class="show">甲</div><button class="linkish huaben-link" disabled>史官還在落筆</button>'
    b = '<a href="http://localhost:8293/zhuan/ZzZ?v=2">x</a><div id="toast">乙</div><button class="linkish huaben-link" data-act="tale" data-id="3">戰記 ›</button>'
    assert noise.mask_dom(a, hosts) == noise.mask_dom(b, hosts)
    assert noise.dom_noise(a, b, hosts) == ["share", "tale"]
    assert noise.mask_dom("<p>甲</p>", hosts) != noise.mask_dom("<p>乙</p>", hosts)
    assert noise.mask_dom('<div class="options fit-tight">', hosts) != noise.mask_dom('<div class="options">', hosts)  # 006_prep_c02：這種靠等版面穩定壓，不遮


def test_only_the_heads_messages_count(noise):
    base = ["001_zh: 404 http://127.0.0.1:8292/favicon.ico"]
    head = ["009_zh: 404 http://localhost:8293/favicon.ico", "010_x: 404 http://localhost:8293/static/new.png"]
    assert noise.head_only(base, head, noise.hosts_pattern(HOSTS)) == [head[1]]
    assert noise.head_only(head, base, noise.hosts_pattern(HOSTS)) == []


def test_expected_rows_only_count_when_they_match(noise):
    expect = [{"scene": "^0\\d\\d_mall", "class": "pixel", "reason": "這一波改了商城"}]
    assert noise.matches_expect(expect, "012_mall", "pixel")["reason"]
    assert noise.matches_expect(expect, "012_mall", "dom") is None
    assert noise.matches_expect(expect, "112_news", "pixel") is None


# ── 兩邊的比對（不開瀏覽器，假的走法紀錄） ──

def _walk(root: Path, *, dom="<body><p>甲</p></body>", props=("color", "margin-left"), vals=("red", "1px"), steps=(), fatal=None, text="沈浪") -> Path:
    for sub in ("dom", "style", "main", "shots"):
        (root / sub).mkdir(parents=True)
    sid = "001_scene"
    (root / "dom" / f"{sid}.html").write_text(dom, encoding="utf-8")
    key = "\x01".join(vals)
    doc = {"props": list(props), "els": [["BODY.", key]], "dict": {key: key}}
    with gzip.open(root / "style" / f"{sid}__375-light.json.gz", "wt", encoding="utf-8") as f:
        json.dump(doc, f)
    report = {"label": root.name, "facts": {}, "console": [], "exceptions": [], "http": [], "failed": [], "steps": list(steps), "apiCalls": [], "hashes": {}, "pyErrors": [],
              "scenes": {sid: {"text": text, "layout": {"375-light": {"sw": 375}}, "shots": [], "sty": {"375-light": key}, "vol": {}, "unstable": False}}}
    if fatal:
        report["fatal"] = fatal
    (root / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return root


def _classes(out):
    return sorted({row["class"] for row in out["real"]})


def test_two_same_walks_are_green_and_share_a_fingerprint(compare, tmp_path):
    out = compare.compare(_walk(tmp_path / "a"), _walk(tmp_path / "b"), HOSTS)
    assert out["real"] == [] and out["tool"] == [] and out["fingerprint"]["A"] == out["fingerprint"]["B"]


def test_a_changed_dom_a_changed_style_and_changed_clicks_are_real(compare, tmp_path):
    a = _walk(tmp_path / "a")
    assert _classes(compare.compare(a, _walk(tmp_path / "b", dom="<body><p>乙</p></body>"), HOSTS)) == ["dom"]
    assert _classes(compare.compare(a, _walk(tmp_path / "c", vals=("blue", "1px")), HOSTS)) == ["style"]
    assert _classes(compare.compare(a, _walk(tmp_path / "d", steps=["x click y -> missing"]), HOSTS)) == ["steps"]


def test_a_used_value_moving_is_noise_and_stays_out_of_the_fingerprint(compare, tmp_path):
    out = compare.compare(_walk(tmp_path / "a"), _walk(tmp_path / "b", vals=("red", "312.5px")), HOSTS)
    assert out["real"] == [] and out["noise"] == {"layout-used": 1}
    assert out["fingerprint"]["A"]["style"] == out["fingerprint"]["B"]["style"]


def test_a_dead_driver_is_the_tool_not_the_pages(compare, tmp_path):
    out = compare.compare(_walk(tmp_path / "a"), _walk(tmp_path / "b", fatal="no browser"), HOSTS)
    assert out["tool"] and "no browser" in out["tool"][0]


def test_the_words_never_show_on_the_heads_side(compare, tmp_path):
    out = compare.compare(_walk(tmp_path / "a"), _walk(tmp_path / "b", text="他是假人"), HOSTS)
    assert "words" in _classes(out)


# ── 語料重播 ──

def test_the_corpus_plays_each_different_snapshot_once(tmp_path):
    pytest.importorskip("PIL")
    sys.path.insert(0, str(TOOL))
    replay = _load("replay")
    (tmp_path / "001_a.html").write_text('<body><img src="http://127.0.0.1:8292/static/x.png?v=1"></body>', encoding="utf-8")
    (tmp_path / "002_b.html").write_text('<body><img src="http://localhost:8293/static/x.png?v=2"></body>', encoding="utf-8")  # 同一頁：host、?v= 遮掉之後一樣
    (tmp_path / "003_c.html").write_text("<body><p>別的</p></body>", encoding="utf-8")
    (tmp_path / "004_raw.html").write_text("<html><head></head><body>公開分享頁</body></html>", encoding="utf-8")  # 自己帶樣式的整頁，不是這一份 CSS 的事
    pages = replay.load_corpus(str(tmp_path))
    assert sorted(pages) == ["001_a", "003_c"]
    assert "127.0.0.1" not in pages["001_a"][1]


def test_the_candidates_head_comes_without_its_scripts(tmp_path):
    pytest.importorskip("PIL")
    sys.path.insert(0, str(TOOL))
    replay = _load("replay")
    (tmp_path / "index.html").write_text('<html><head><link rel="stylesheet" href="/static/a.css"><script src="/static/app.js"></script></head><body></body></html>', encoding="utf-8")
    head = replay.candidate_head(str(tmp_path))
    assert "a.css" in head and "script" not in head


# ── 工具本身 ──

def _gate(tmp_path, *extra):
    return subprocess.run([sys.executable, str(TOOL / "gate.py"), "--base", "HEAD", "--head", "HEAD", "--out", str(tmp_path / "out"), *extra], capture_output=True, text=True, encoding="utf-8", errors="replace")


def test_no_browser_is_exit_two(tmp_path):
    r = _gate(tmp_path, "--chrome", str(tmp_path / "no-such-chrome.exe"))
    assert r.returncode == 2
    summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
    assert summary["exit"] == 2 and not summary["green"] and "no browser" in summary["tool"][0]


def test_the_real_servers_port_is_refused(tmp_path):
    pytest.importorskip("PIL")
    fake = tmp_path / "fake.exe"
    fake.write_text("", encoding="utf-8")
    r = _gate(tmp_path, "--chrome", str(fake), "--node", str(fake), "--ports", "7861,8299", "--cdp-ports", "9499,9498")
    assert r.returncode == 2
    assert "7861" in json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))["tool"][0]


def test_the_dead_model_goes_into_the_copy(tmp_path):
    unpack = _load("unpack")
    assert json.loads(unpack.dead_model('{"a": 1}'))["ollama_url"] == unpack.DEAD_MODEL
    assert json.loads(unpack.dead_model('{"ollama_url": "http://x:11434", "a": 1}'))["ollama_url"] == unpack.DEAD_MODEL


def _names_in(path: Path) -> set[str]:
    names = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= {(a.asname or a.name).split(".")[0] for a in node.names}
    return names


def test_what_the_wrapper_patches_is_still_in_server_py():
    """搬東西的批早一點知道：serve.py 起不來要等到閘門才看得到（缺了結束碼 3、閘門轉成 2）。"""
    tree = ast.parse((TOOL / "serve.py").read_text(encoding="utf-8"))
    wanted = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "PATCH_NAMES")
    assert set(wanted) - _names_in(ROOT / "server.py") == set()


def test_every_round_has_its_flows_file_and_must_reach_names_known_rounds():
    gate = _load("gate")
    for name in gate.ROUNDS:
        assert (TOOL / "flows" / f"{name}.mjs").exists(), name
    rows = (TOOL / "must_reach.txt").read_text(encoding="utf-8").splitlines()
    rounds = {line.split(":", 1)[0] for line in rows if line and not line.startswith("#")}
    assert rounds <= set(gate.ROUNDS) and rounds
