"""scripts/webqa 自己的測試：雜訊表放的是 B、C 波真的出現過的列（鏡名與數字照當時的比對紀錄），看漏的就是沒人驗的。"""
import ast
import gzip
import importlib.util
import json
import re
import shutil
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


def test_grid_tracks_only_count_when_the_scrollbar_is_what_differs(noise):
    # 第 77 批第一次全量的 main:089_bd_drop 寬 641：BODY inline-size 641 對 626，連 grid-template-columns、rows 一起動
    props = {"block-size", "grid-template-columns", "grid-template-rows", "inline-size", "margin-left"}
    assert noise.used_only(props, flip=True) is True
    assert noise.used_only(props, flip=False) is False
    assert noise.used_only(props | {"color"}, flip=True) is False


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

def _walk(root: Path, *, dom="<body><p>甲</p></body>", props=("color", "margin-left"), vals=("red", "1px"), steps=(), fatal=None, text="沈浪", dots=None, width=None, toast="") -> Path:
    """dots: 這一鏡有一張 375-light 的截圖，塗黑這麼多個點（None 是沒有圖）。width: 視窗量到的 scrollWidth。"""
    for sub in ("dom", "style", "main", "shots"):
        (root / sub).mkdir(parents=True)
    sid = "001_scene"
    shots, hashes = [], {}
    if dots is not None:
        from PIL import Image

        img = Image.new("RGB", (40, 40), (255, 255, 255))
        for i in range(dots):
            img.putpixel((i % 40, i // 40), (250, 250, 250))
        name = f"{sid}__375-light.png"
        img.save(root / "shots" / name)
        shots, hashes = [name], {name: f"dots{dots}"}
    (root / "dom" / f"{sid}.html").write_text(dom, encoding="utf-8")
    key = "\x01".join(vals)
    doc = {"props": list(props), "els": [["BODY.", key]], "dict": {key: key}}
    with gzip.open(root / "style" / f"{sid}__375-light.json.gz", "wt", encoding="utf-8") as f:
        json.dump(doc, f)
    report = {"label": root.name, "facts": {}, "console": [], "exceptions": [], "http": [], "failed": [], "steps": list(steps), "apiCalls": [], "hashes": hashes, "pyErrors": [],
              "scenes": {sid: {"text": text, "toast": toast, "layout": {"375-light": {"sw": width or 375}}, "shots": shots, "sty": {"375-light": key}, "vol": {}, "unstable": False}}}
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
    out = compare.compare(_walk(tmp_path / "a", dots=0), _walk(tmp_path / "b", vals=("red", "312.5px"), dots=0), HOSTS)
    assert out["real"] == [] and out["noise"] == {"layout-used": 1}
    assert out["fingerprint"]["A"]["style"] == out["fingerprint"]["B"]["style"]


def test_a_used_value_with_no_picture_behind_it_is_counted_apart(compare, noise, tmp_path):
    # 640、641、900 走的時候不拍照：只有頁面大小佐證，不准混進 layout-used（第 77 批審查）
    out = compare.compare(_walk(tmp_path / "a"), _walk(tmp_path / "b", vals=("red", "312.5px")), HOSTS)
    assert out["real"] == [] and out["noise"] == {"layout-no-pixels": 1}
    assert noise.style_class({"margin-left"}, True, has_pixels=False) == "layout-no-pixels"
    assert noise.style_class({"color"}, True, has_pixels=False) is None
    assert noise.style_class({"margin-left"}, False, has_pixels=False) is None


def test_anti_aliasing_beside_a_used_value_is_still_the_same_picture(compare, tmp_path):
    # 第 77 批第一次全量的 main:124_ex_1_choose：.shell margin 312.5 對 0，同窗一張圖 13 px、1 色階（波末閘門實測）
    out = compare.compare(_walk(tmp_path / "a", dots=0), _walk(tmp_path / "b", vals=("red", "312.5px"), dots=13), HOSTS)
    assert out["real"] == [] and out["noise"] == {"layout-used": 1, "aa": 1}
    # 超過抗鋸齒的量就不是同一張圖：樣式與像素都紅
    out = compare.compare(_walk(tmp_path / "c", dots=0), _walk(tmp_path / "d", vals=("red", "312.5px"), dots=500), HOSTS)
    assert _classes(out) == ["pixel", "style"]


def test_a_scrollbar_flip_with_grid_tracks_is_the_gutter(compare, tmp_path):
    grid = ("grid-template-columns", "inline-size")
    a = _walk(tmp_path / "a", props=grid, vals=("600px", "641px"), width=641)
    out = compare.compare(a, _walk(tmp_path / "b", props=grid, vals=("585px", "626px"), width=626), HOSTS)
    assert _classes(out) == ["style"]  # 375 沒有捲軸這回事：照舊紅
    a2, b2 = _walk(tmp_path / "a2", props=grid, vals=("600px", "641px"), width=641), _walk(tmp_path / "b2", props=grid, vals=("585px", "626px"), width=626)
    for walk in (a2, b2):
        (walk / "style" / "001_scene__375-light.json.gz").rename(walk / "style" / "001_scene__641.json.gz")
        report = json.loads((walk / "report.json").read_text(encoding="utf-8"))
        scene = report["scenes"]["001_scene"]
        scene["sty"]["641"] = scene["sty"].pop("375-light")
        scene["layout"]["641"] = scene["layout"].pop("375-light")
        (walk / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    out = compare.compare(a2, b2, HOSTS)
    assert out["real"] == [] and out["noise"] == {"gutter": 1}
    assert out["fingerprint"]["A"]["style"] == out["fingerprint"]["B"]["style"]  # 雜訊不進指紋：波末第二趟 main 的樣式指紋就是差在這裡


def test_the_toasts_words_count_when_both_sides_still_show_them(compare, tmp_path):
    a = _walk(tmp_path / "a", toast="已經存好了。")
    assert compare.compare(a, _walk(tmp_path / "b", toast="已經存好了。"), HOSTS)["real"] == []
    assert _classes(compare.compare(a, _walk(tmp_path / "c", toast="沒有存到。"), HOSTS)) == ["toast"]
    out = compare.compare(a, _walk(tmp_path / "d"), HOSTS)  # 3.2 秒自己收掉：只有一邊還在，不比
    assert out["real"] == [] and out["info"]["toast on one side"] == ["001_scene"]
    share = compare.compare(_walk(tmp_path / "e", toast="已複製 http://127.0.0.1:8292/zhuan/AbC"), _walk(tmp_path / "f", toast="已複製 http://localhost:8293/zhuan/ZzZ"), HOSTS)
    assert share["real"] == []  # 分享碼與主機照舊遮掉


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


def test_the_replay_is_for_stylesheets_and_the_page_that_lists_them(tmp_path):
    gate = _load("gate")
    a, b = tmp_path / "a", tmp_path / "b"
    for web in (a, b):
        web.mkdir()
        (web / "index.html").write_text("<head></head>", encoding="utf-8")
        (web / "style.css").write_text(".a{}", encoding="utf-8")
        (web / "app.js").write_text("1", encoding="utf-8")
    assert gate.stylesheet_changes(str(a), str(b)) == []
    (b / "app.js").write_text("2", encoding="utf-8")
    assert gate.stylesheet_changes(str(a), str(b)) == []  # 程式改了 DOM 會走到比對，不靠重播
    (b / "style.css").write_text(".a{color:red}", encoding="utf-8")
    (b / "new.css").write_text(".b{}", encoding="utf-8")
    assert gate.stylesheet_changes(str(a), str(b)) == ["new.css", "style.css"]
    (b / "index.html").write_text("<head><link></head>", encoding="utf-8")
    assert "index.html" in gate.stylesheet_changes(str(a), str(b))


def test_a_walk_that_never_ends_is_the_tool_not_a_hang():
    gate = _load("gate")
    slow = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        with pytest.raises(gate.ToolBroke, match="round main still running"):
            gate.wait_all([slow], 0.1, "round main")
    finally:
        slow.kill()
        slow.wait()
    done = subprocess.Popen([sys.executable, "-c", "pass"])
    gate.wait_all([done], 20, "round main")


@pytest.mark.parametrize("script", ["driver.mjs", "replay.mjs"])
def test_the_browser_cannot_hold_the_walk_forever(script):
    text = (TOOL / script).read_text(encoding="utf-8")
    assert "ws.onclose" in text and "ANSWER_SECONDS" in text and "clearTimeout" in text


def test_a_phone_viewport_widened_by_an_overflow_has_landed():
    # 第 77 批第一次全量的 v:009～011：移動卡展開時 375 量到 383，版面一動不動卻被標 unstable，連帶 .shell margin 不准歸雜訊
    node = shutil.which("node")
    if not node:
        pytest.skip("no node")
    src = (TOOL / "snippets.mjs").as_uri()
    cases = [("383|2106|383|0,0,375,2106|1", 375, True), ("375|2106|375|x|1", 375, True), ("1265|800|1265|x|1", 375, False), ("640|800|640|x|1", 375, False),
             ("383|2106|390|x|1", 375, False), ("641|800|641|x|1", 640, False), ("1280|800|1280|x|1", 1280, True)]
    code = f"const {{ landed }} = await import({json.dumps(src)}); console.log(JSON.stringify({json.dumps([c[:2] for c in cases])}.map(([s, w]) => landed(s, w))));"
    out = subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True, encoding="utf-8", check=True)
    assert json.loads(out.stdout) == [c[2] for c in cases]


def test_a_dialog_is_answered_and_shows_as_a_console_line():
    text = (TOOL / "driver.mjs").read_text(encoding="utf-8")
    assert "Page.javascriptDialogOpening" in text and "Page.handleJavaScriptDialog" in text and "report.console.push(`${sceneNow}: dialog" in text


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


def test_both_copies_get_the_same_push_key_before_a_server_starts(tmp_path):
    # 第 110 批：--jobs 4 時同一份複本的四個伺服器同時產生金鑰、一個讀到半份 PEM（MalformedFraming）；兩份複本先放同一把
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import serialization

    gate = _load("gate")
    pems = []
    for name in ("a", "b"):
        gate.seed_local(str(tmp_path / name))
        pems.append((tmp_path / name / ".local" / "webpush_vapid.pem").read_bytes())
    assert pems[0] == pems[1]
    serialization.load_pem_private_key(pems[0], password=None)
    assert re.search(r'^VAPID_FILE = ROOT / "\.local" / "webpush_vapid\.pem"', (ROOT / "server.py").read_text(encoding="utf-8"), re.M), "server.py 讀金鑰的路徑換了，seed_local 要跟著換"


def test_the_model_queue_is_off_in_the_wrapper():
    # 佇列一格、別的寫手佔著就跳過，那一篇放回單子等 30 秒，而時鐘是凍的：第 77 批第一次全量 extra:069～074 一邊多一筆天下形勢
    text = (TOOL / "serve.py").read_text(encoding="utf-8")
    assert "server.make_queue = lambda config: None" in text
    assert "server.make_queue" not in text.split("import server", 1)[0]


def test_every_named_thread_is_a_writer_or_a_loop():
    # 名單用完全相等比，zhuan-<季> 永遠對不上、tavern-chatter 沒列：列傳寫好的畫面走不到（第 77 批審查）。新開的背景執行緒也要在這裡表態
    loops = {"world-scheduler", "push-watch", "narration", "notice-watch", "tales"}
    tree = ast.parse((TOOL / "serve.py").read_text(encoding="utf-8"))
    values = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in ("WRITERS", "WRITER_PREFIXES")}
    found = set()
    for path in [ROOT / "server.py", *(ROOT / "tianxia").rglob("*.py")]:
        if "tests" in path.parts:
            continue
        found |= set(re.findall(r"Thread\((?:[^()]|\([^()]*\))*?name=f?\"([^\"{]+)", path.read_text(encoding="utf-8"), re.S))
    assert "zhuan-" in found and "tavern-chatter" in found  # 這支掃描自己有效
    missing = {n for n in found - loops if n not in values["WRITERS"] and not n.startswith(values["WRITER_PREFIXES"])}
    assert not missing


def test_every_round_has_its_flows_file_and_must_reach_names_known_rounds():
    gate = _load("gate")
    for name in gate.ROUNDS:
        assert (TOOL / "flows" / f"{name}.mjs").exists(), name
    rows = (TOOL / "must_reach.txt").read_text(encoding="utf-8").splitlines()
    rounds = {line.split(":", 1)[0] for line in rows if line and not line.startswith("#")}
    assert rounds <= set(gate.ROUNDS) and rounds


# ── 第 107 批：回合對照表（coverage.json）與 --changed-files ──


def test_the_coverage_table_checks_out():
    coverage = _load("coverage")
    assert coverage.check() == [], "scripts/webqa/coverage.json 對不上：照 coverage.py 的說明重跑一次 --quick 再 build"


def test_a_missing_file_in_the_table_is_caught(tmp_path):
    coverage = _load("coverage")
    table = json.loads((TOOL / "coverage.json").read_text(encoding="utf-8"))
    table[next(iter(table))].append("web/no_such_file.js")
    bad = tmp_path / "coverage.json"
    bad.write_text(json.dumps(table), encoding="utf-8")
    assert any("no_such_file" in p for p in coverage.check(str(bad)))


def test_every_package_script_picks_some_round():
    """包的網頁檔改到，挑到的回合非空（對照表沒有它就全走，也算），或 NOT_ON_TABLE 寫了為什麼沒有回合走到（第 110 批）；殼的檔一律全走。"""
    gate = _load("gate")
    table = gate.load_coverage()
    packages = {p.name for p in (ROOT / "tianxia" / "features").iterdir() if p.is_dir()}
    for js in sorted((ROOT / "web").glob("*.js")):
        if js.stem in packages:
            rounds, why = gate.rounds_for([f"web/{js.name}"], table)
            assert rounds or f"web/{js.name}" in gate.NOT_ON_TABLE, (js.name, why)
    for shell in sorted(gate.SHELL_FILES):
        assert gate.rounds_for([shell], table)[0] == list(gate.ROUNDS), shell
    assert gate.rounds_for(["scripts/webqa/driver.mjs"], table)[0] == list(gate.ROUNDS)


def test_changed_files_follow_the_table():
    gate = _load("gate")
    table = {"main": ["web/app.js", "web/seal.js"], "x": ["web/yyy.js"]}
    rounds = ("main", "x")
    assert gate.rounds_for(["web/app.js"], table, rounds)[0] == ["main", "x"], "殼的檔不看對照表，全走"
    assert gate.rounds_for(["web/seal.js"], table, rounds)[0] == ["main"]
    assert gate.rounds_for(["web/seal.css"], table, rounds)[0] == ["main"], "包的 css 照同名 js 的回合"
    assert gate.rounds_for(["web/seal.js", "web/yyy.js"], table, rounds)[0] == ["main", "x"]
    assert gate.rounds_for(["web/zzz.js"], table, rounds)[0] == ["main", "x"], "對不到任何回合就全走"
    assert gate.rounds_for(["web/seal.js"], {}, rounds)[0] == ["main", "x"], "沒有對照表就全走"
    # 第 110 批：空清單不走；包的檔不在表上、NOT_ON_TABLE 有理由就不走並寫原因；沒理由照舊全走（保守）
    assert gate.rounds_for([], table, rounds)[0] == [] and gate.rounds_for([" "], table, rounds)[0] == []
    got, why, not_walked = gate.rounds_detail(["web/identity.js"], table, rounds, {"web/identity.js": "off"})
    assert got == [] and not_walked and "web/identity.js" in not_walked[0] and "off" in not_walked[0], why
    assert gate.rounds_for(["web/identity.css"], table, rounds, {"web/identity.js": "off"})[0] == [], "包的 css 照同名 js"
    assert gate.rounds_for(["web/identity.js"], table, rounds, {})[0] == ["main", "x"], "沒寫理由就全走"
    assert gate.rounds_for(["web/identity.js", "web/seal.js"], table, rounds, {"web/identity.js": "off"})[0] == ["main"]
    assert gate.rounds_for(["web/shop.css"], table, rounds)[0] == ["main", "x"], "沒有同名的包就是殼"


def test_dry_run_prints_the_pick_and_walks_nothing():
    def dry(files):
        r = subprocess.run([sys.executable, str(TOOL / "gate.py"), "--dry-run", f"--changed-files={files}"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert r.returncode == 0, r.stderr
        return r.stdout
    assert "rounds: (none)" in dry("")
    out = dry("web/identity.js")
    assert "rounds: (none)" in out and "not walked: web/identity.js" in out
    gate = _load("gate")
    assert f"rounds: {','.join(gate.ROUNDS)}" in dry("web/app.js")


def test_nothing_to_walk_is_green_before_anything_is_looked_for(tmp_path):
    r = _gate(tmp_path, "--changed-files=", "--chrome", str(tmp_path / "no-such-chrome.exe"))
    assert r.returncode == 0, r.stdout
    summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
    assert summary["green"] and summary["rounds"] == [] and not summary["tool"]
    assert "NOTHING TO WALK" in (tmp_path / "out" / "report.txt").read_text(encoding="utf-8").splitlines()[0]
