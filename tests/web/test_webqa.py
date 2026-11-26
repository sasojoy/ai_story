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


def test_only_a_picture_with_nothing_else_different_is_drawn_again(noise):
    # 第 237 批：AA 波鐵匠鋪 045 的 375 深色 102 px、淺色 40 色階，A 對 A 也紅；兩邊重畫出過同一張就是這一景自己的畫法
    assert noise.recheck_candidate(clean_strict=True, unstable=False, same_size=True)
    assert not noise.recheck_candidate(clean_strict=False, unstable=False, same_size=True)  # 有樣式差（連 used 值也算）：照舊直接紅
    assert not noise.recheck_candidate(clean_strict=True, unstable=True, same_size=True)
    assert not noise.recheck_candidate(clean_strict=True, unstable=False, same_size=False)
    assert noise.render_variants(["x1", "y1"], ["z1", "y1"])
    assert not noise.render_variants(["x1", "x2"], ["y1", "y2"])
    assert not noise.render_variants([], ["y1"])  # 有一邊沒重畫成：不算雜訊


def test_a_real_line_says_whether_the_two_walks_left_the_same_dom_and_styles():
    # 第 254 批：AI 波 c 回合 028 那一張 REAL，PM 要自己翻 summary.json 的 fingerprint 才知道兩邊 DOM、樣式一樣
    gate = _load("gate")
    same = {"scenes": "s", "dom": "d", "style": "y", "main": "m"}
    assert gate.fingerprint_note({"A": same, "B": dict(same)}) == " fingerprint same"
    assert gate.fingerprint_note({"A": same, "B": {**same, "dom": "d2"}}) == " fingerprint differs: dom"
    assert gate.fingerprint_note({"A": same, "B": {**same, "style": "y2", "dom": "d2"}}) == " fingerprint differs: dom,style"
    assert gate.fingerprint_note(None) == ""  # 重放的列沒有指紋
    assert gate.fingerprint_note({"A": same, "B": None}) == ""


def test_the_battle_card_mutation_inverts_its_two_pictures_only(tmp_path):
    # 第 254 批：selftest 的 img-battle，決戰卡底圖（web/battle.js BP_BG）反相、同尺寸同格式，c 回合要判像素 REAL
    Image = pytest.importorskip("PIL.Image")
    gate = _load("gate")
    ev = tmp_path / "web" / "img" / "events"
    ev.mkdir(parents=True)
    for name in ("camp.webp", "night.webp", "rain.webp"):
        Image.new("RGB", (4, 3), (10, 200, 30)).save(ev / name, format="WEBP", lossless=True)
    gate.mutate(str(tmp_path), gate.IMG_BATTLE)
    for name, px in (("camp.webp", (245, 55, 225)), ("night.webp", (245, 55, 225)), ("rain.webp", (10, 200, 30))):
        with Image.open(ev / name) as im:
            assert (im.format, im.size) == ("WEBP", (4, 3))
            assert max(abs(x - y) for x, y in zip(im.convert("RGB").getpixel((0, 0)), px)) <= 8  # 存回去是有損的 webp，差幾級
    assert set(gate.IMG_BATTLE_FILES) == {"web/img/events/camp.webp", "web/img/events/night.webp"}
    assert '"/static/img/events/camp.webp"' in (ROOT / "web" / "battle.js").read_text(encoding="utf-8")  # 底圖換了檔名，突變要跟著換


def test_the_battle_card_spot_mutation_inverts_a_middle_band_only(tmp_path):
    # 第 260 批：selftest 的 img-battle-spot，同兩張底圖只把中間一條橫帶（高度一成）反相，c 回合要判像素 REAL、repaint-variants 不准收
    Image = pytest.importorskip("PIL.Image")
    gate = _load("gate")
    ev = tmp_path / "web" / "img" / "events"
    ev.mkdir(parents=True)
    for name in ("camp.webp", "night.webp", "rain.webp"):
        Image.new("RGB", (40, 40), (10, 200, 30)).save(ev / name, format="WEBP", lossless=True)
    gate.mutate(str(tmp_path), gate.IMG_BATTLE_SPOT)
    near = lambda got, want: max(abs(x - y) for x, y in zip(got, want)) <= 8  # 存回去是有損的 webp，差幾級
    for name in ("camp.webp", "night.webp"):
        with Image.open(ev / name) as im:
            assert (im.format, im.size) == ("WEBP", (40, 40))
            px = im.convert("RGB")
            assert near(px.getpixel((20, 20)), (245, 55, 225)) and near(px.getpixel((5, 19)), (245, 55, 225))
            assert near(px.getpixel((20, 5)), (10, 200, 30)) and near(px.getpixel((20, 35)), (10, 200, 30))
    with Image.open(ev / "rain.webp") as im:
        assert near(im.convert("RGB").getpixel((20, 20)), (10, 200, 30))


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

def _walk(root: Path, *, dom="<body><p>甲</p></body>", props=("color", "margin-left"), vals=("red", "1px"), steps=(), fatal=None, text="沈浪", dots=None, width=None, toast="",
          variants=None) -> Path:
    """dots: 這一鏡有一張 375-light 的截圖，塗黑這麼多個點（None 是沒有圖）。width: 視窗量到的 scrollWidth。
    variants: 同一邊不重新載入再拍的那幾張的雜湊（第 260 批 facts.variants；圖的雜湊寫成 dots<點數>）。"""
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
    if variants is not None:
        report["scenes"][sid]["variants"] = {name: list(variants) for name in shots}
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


def _css(walk: Path, rows) -> Path:
    (walk / "cssrules.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return walk


def test_a_new_packages_own_sheet_is_listed_not_red(compare, tmp_path):
    # 第 110 批：--new 的包自己那張表的規則兩邊各自扣掉，差異列成 new_css；別張表照舊 css-rules；沒帶 --new 同一份資料是 real
    base = [["style.css", ".card { padding: 1px; }"], ["identity.css", ".id-a { color: red; }"]]
    a = _css(_walk(tmp_path / "a"), base)
    b = _css(_walk(tmp_path / "b"), [*base, ["identity.css", ".id-b { color: blue; }"]])
    out = compare.compare(a, b, HOSTS, new_sheets={"identity.css"})
    assert out["real"] == [] and out["new_css"] == [{"sheet": "identity.css", "only A": [], "only B": [".id-b { color: blue; }"], "counts": [1, 2]}]
    assert _classes(compare.compare(a, b, HOSTS)) == ["css-rules"] and "new_css" not in compare.compare(a, b, HOSTS)
    c = _css(_walk(tmp_path / "c"), [["style.css", ".card { padding: 2px; }"], base[1]])
    assert _classes(compare.compare(a, c, HOSTS, new_sheets={"identity.css"})) == ["css-rules"], "別張表照舊算"
    old = _css(_walk(tmp_path / "old"), [t for _, t in base])
    assert compare.compare(old, _css(_walk(tmp_path / "old2"), [t for _, t in base]), HOSTS, new_sheets={"identity.css"})["real"] == [], "舊格式（純字串）也讀得懂"


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


def test_the_replay_puts_a_clean_pixel_row_aside_and_a_dirty_one_stays_real(compare, tmp_path):
    # 第 237 批：只有 recheck（重放）才延後；DOM 與計算樣式全同、只差像素的那一張先不算紅，記下它在 real 裡的位置
    a, b = _walk(tmp_path / "a", dots=0), _walk(tmp_path / "b", dots=500)
    walk = compare.compare(a, b, HOSTS, str(tmp_path / "red"))
    assert _classes(walk) == ["pixel"] and "recheck" not in walk, "走查照舊直接紅"
    assert walk["real"][0]["red"] == ["001_scene__375-light.png", "001_scene__375-light__A.png", "001_scene__375-light__B.png"]
    assert all((tmp_path / "red" / n).exists() for n in walk["real"][0]["red"]) and walk["red_images"] == 1
    out = compare.compare(a, b, HOSTS, str(tmp_path / "red2"), recheck=True)
    assert out["real"] == [] and out["red_images"] == 0 and not (tmp_path / "red2").exists()
    assert [(c["at"], c["scene"], c["file"], c["view"]) for c in out["recheck"]] == [(0, "001_scene", "001_scene__375-light.png", "375-light")]
    # 有樣式差就不重畫：color 變了、used 值動了（margin 312.5px）都照舊紅
    for name, vals in (("c", ("blue", "1px")), ("d", ("red", "312.5px"))):
        out = compare.compare(a, _walk(tmp_path / name, vals=vals, dots=500), HOSTS, recheck=True)
        assert "pixel" in _classes(out) and out["recheck"] == [], name


def test_a_picture_each_side_drew_of_the_other_is_repaint_variants(compare, tmp_path):
    # 第 260 批：c 回合 bt_watch_open/shut 375 淺色，同一邊不重新載入，倒數每秒重寫就換畫法（整頁剛畫完、倒數那一格局部補畫 713 px 1 級）；
    # 兩邊本來那張落在不同畫法就紅（8 趟紅 2）。走查在同一邊多拍兩張（facts.variants），兩邊各自真的畫出過同一張才是 repaint-variants
    a = _walk(tmp_path / "a", dots=0, variants=["dots0", "dots500"])
    b = _walk(tmp_path / "b", dots=500, variants=["dots0", "dots500"])
    out = compare.compare(a, b, HOSTS, str(tmp_path / "red"))
    assert out["real"] == [] and out["noise"] == {"repaint-variants": 1} and out["red_images"] == 0
    assert out["noise_rows"] == [{"file": "001_scene__375-light.png", "class": "repaint-variants", "pixels": 500, "levels": 5, "box": [0, 0, 40, 13], "variants": [2, 2]}]
    assert out["fingerprint"]["A"] == out["fingerprint"]["B"]
    # 量到的樣子：一邊本來那張是整頁剛畫完（dots0），後拍的兩張都是倒數那一格補畫（dots500）；另一邊本來那張就是 dots500
    out = compare.compare(_walk(tmp_path / "c", dots=0, variants=["dots500", "dots500"]), _walk(tmp_path / "d", dots=500, variants=["dots500"]), HOSTS)
    assert out["real"] == [] and out["noise"] == {"repaint-variants": 1}
    # 共同的是兩邊後拍的第三張也算：兩邊各自真的畫出過它
    out = compare.compare(_walk(tmp_path / "e", dots=0, variants=["dots7"]), _walk(tmp_path / "f", dots=500, variants=["dots7"]), HOSTS)
    assert out["real"] == [] and out["noise"] == {"repaint-variants": 1}


@pytest.mark.parametrize("name, a_seen, b_seen", [
    ("交集空：只有一邊畫得出來的變化", ["dots0"], ["dots500"]),
    ("交集空：兩邊後拍的都是自己那一種", ["dots0", "dots0"], ["dots500", "dots500"]),
    ("一邊沒有 variants", None, ["dots0"]),
    ("一邊的 variants 是空的", [], ["dots0"]),
    ("兩邊都沒有 variants（舊報告）", None, None),
])
def test_a_picture_only_one_side_draws_stays_real(compare, tmp_path, name, a_seen, b_seen):
    out = compare.compare(_walk(tmp_path / "a", dots=0, variants=a_seen), _walk(tmp_path / "b", dots=500, variants=b_seen), HOSTS)
    assert _classes(out) == ["pixel"] and "repaint-variants" not in out["noise"], name


@pytest.mark.parametrize("name, kw, want", [
    ("DOM 有差", {"dom": "<body><p>乙</p></body>"}, ["dom", "pixel"]),
    ("計算樣式有差", {"vals": ("blue", "1px")}, ["pixel", "style"]),
    ("used 值動了也算樣式有差", {"vals": ("red", "312.5px")}, ["pixel", "style"]),
])
def test_repaint_variants_never_take_a_row_with_the_dom_or_styles_different(compare, tmp_path, name, kw, want):
    # AJ 波認定第 2 條：DOM 或計算樣式有差的列不收進新的雜訊類，兩邊的畫法有交集也照樣紅
    a = _walk(tmp_path / "a", dots=0, variants=["dots0", "dots500"])
    out = compare.compare(a, _walk(tmp_path / "b", dots=500, variants=["dots0", "dots500"], **kw), HOSTS)
    assert _classes(out) == want and "repaint-variants" not in out["noise"], name


def test_repaint_variants_needs_a_picture_both_sides_drew(noise):
    assert noise.repaint_variants("a", ["b"], "b", ["a"])
    assert noise.repaint_variants("a", ["b", "b"], "b", ["b"])  # 第 260 批量到的：A 後拍的都是 B 那一種
    assert noise.repaint_variants("a", ["c"], "b", ["c"])
    assert not noise.repaint_variants("a", ["a"], "b", ["b"])
    assert not noise.repaint_variants("a", [], "b", [])


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


def _walk_1280(root: Path, *, sw=1280, sw_end=None, width="1280px", dots_first=0, dots_s1=0, dom="<body><p>甲</p></body>", prop="width") -> Path:
    """1280 一個視窗：第一張、捲動後一張、樣式（捲完才傾印）。sw 是第一張之前量的，sw_end 是視窗拍完量的（None 是沒動、不寫 layoutEnd）。"""
    from PIL import Image

    for sub in ("dom", "style", "main", "shots"):
        (root / sub).mkdir(parents=True)
    sid, shots, hashes = "001_scene", [], {}
    for name, dots in ((f"{sid}__1280.png", dots_first), (f"{sid}__1280__s1.png", dots_s1)):
        img = Image.new("RGB", (40, 40), (255, 255, 255))
        for i in range(dots):
            img.putpixel((i % 40, i // 40), (200, 200, 200))
        img.save(root / "shots" / name)
        shots.append(name)
        hashes[name] = f"dots{dots}"
    (root / "dom" / f"{sid}.html").write_text(dom, encoding="utf-8")
    key = width
    with gzip.open(root / "style" / f"{sid}__1280.json.gz", "wt", encoding="utf-8") as f:
        json.dump({"props": [prop], "els": [["BODY.", key]], "dict": {key: key}}, f)
    scene = {"text": "沈浪", "toast": "", "layout": {"1280": {"sw": sw, "cw": sw}}, "shots": shots, "sty": {"1280": key}, "vol": {}, "unstable": False}
    if sw_end is not None:
        scene["layoutEnd"], scene["moved"] = {"1280": {"sw": sw_end, "cw": sw_end}}, ["1280"]
    report = {"label": root.name, "facts": {}, "console": [], "exceptions": [], "http": [], "failed": [], "steps": [], "apiCalls": [], "hashes": hashes, "pyErrors": [],
              "scenes": {sid: scene}}
    (root / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return root


def test_the_gutter_coming_back_after_the_first_picture_is_judged_at_the_end_of_the_window(compare, tmp_path):
    # 第 258 批：AJ 波 main 092_bd_given 1280，第一張之前兩邊 sw 都 1280、第一張一樣；捲動時一邊的溝回來，__s1 整塊移半條捲軸、BODY 1280 對 1265
    a = _walk_1280(tmp_path / "a")
    old = _walk_1280(tmp_path / "old", width="1265px", dots_s1=500)
    assert _classes(compare.compare(a, old, HOSTS)) == ["pixel", "style"], "只量第一張之前：落成真差異（舊工具就是這樣紅的）"
    b = _walk_1280(tmp_path / "b", sw_end=1265, width="1265px", dots_s1=500)
    out = compare.compare(a, b, HOSTS)
    assert out["real"] == [] and out["noise"] == {"gutter": 2}, out
    assert out["info"]["gutter moved"] == ["B 001_scene 1280"]
    # 第一張照第一張之前的 sw：那一刻兩邊一樣，第一張有差照舊紅
    c = _walk_1280(tmp_path / "c", sw_end=1265, width="1265px", dots_first=500, dots_s1=500)
    assert _classes(compare.compare(a, c, HOSTS)) == ["pixel"]


def test_the_same_scrollbar_and_a_15px_move_stays_real(compare, tmp_path):
    # 第 258 批不准的：兩邊溝一樣（拍完都 1265）、畫面真的移了 15px（.shell 的 margin 改了）——樣式、像素照樣紅
    a = _walk_1280(tmp_path / "a", sw=1280, sw_end=1265, prop="margin-left", width="0px")
    b = _walk_1280(tmp_path / "b", sw=1280, sw_end=1265, prop="margin-left", width="15px", dots_s1=500)
    assert _classes(compare.compare(a, b, HOSTS)) == ["pixel", "style"]
    a2, b2 = _walk_1280(tmp_path / "a2", sw=1265, prop="margin-left", width="0px"), _walk_1280(tmp_path / "b2", sw=1265, prop="margin-left", width="15px", dots_s1=500)
    assert _classes(compare.compare(a2, b2, HOSTS)) == ["pixel", "style"], "沒有 layoutEnd 的也一樣"
    # 拍完的溝差 15，但 DOM 不一樣：不歸 gutter
    d = _walk_1280(tmp_path / "d", sw_end=1265, width="1265px", dots_s1=500, dom="<body><p>乙</p></body>")
    assert _classes(compare.compare(_walk_1280(tmp_path / "e"), d, HOSTS)) == ["dom", "pixel", "style"]
    # 拍完的溝差 15，但樣式有不是 used 值的差：不歸 gutter
    f = _walk_1280(tmp_path / "f", sw_end=1265, prop="color", width="blue", dots_s1=500)
    assert _classes(compare.compare(_walk_1280(tmp_path / "g", prop="color", width="red"), f, HOSTS)) == ["pixel", "style"]


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


def test_the_re_renders_settle_a_put_aside_picture(tmp_path):
    # 第 237 批：兩邊重畫出過同一張 → render-variants 雜訊；從頭到尾不相交 → 照原本的位置插回 real，紅圖連 A、B 原圖
    pytest.importorskip("PIL")
    sys.path.insert(0, str(TOOL))
    replay = _load("replay")
    a, b = _walk(tmp_path / "a", dots=0), _walk(tmp_path / "b", dots=500)
    f = "001_scene__375-light.png"
    detail = {"file": f, "pixels": 500, "levels": 5, "box": [0, 0, 40, 13], "clean": True, "unstable": False}

    def res():
        return {"real": [{"scene": "000_x", "class": "dom", "detail": {}}, {"scene": "009_z", "class": "style", "detail": {}}], "noise": {"aa": 1}, "noise_rows": [], "red_images": 0,
                "recheck": [{"at": 1, "scene": "001_scene", "file": f, "view": "375-light", "detail": detail}]}

    out = replay.settle(res(), [str(a), str(b)], str(tmp_path / "red"), 40, {f: (["p", "q"], ["r", "q"])})
    assert [r["class"] for r in out["real"]] == ["dom", "style"] and "recheck" not in out
    assert out["noise"] == {"aa": 1, "render-variants": 1} and out["noise_rows"][0]["class"] == "render-variants" and out["noise_rows"][0]["renders"] == [2, 2]
    assert out["red_images"] == 0 and not (tmp_path / "red").exists()
    out = replay.settle(res(), [str(a), str(b)], str(tmp_path / "red"), 40, {f: (["p", "p"], ["r", "s"])})
    assert [r["class"] for r in out["real"]] == ["dom", "pixel", "style"] and out["real"][1]["detail"]["renders"] == [1, 2]
    assert out["red_images"] == 1 and out["real"][1]["red"][1:] == ["001_scene__375-light__A.png", "001_scene__375-light__B.png"]
    from PIL import Image

    with Image.open(tmp_path / "red" / "001_scene__375-light__B.png") as im:
        assert im.size == (40, 40)  # 原尺寸
    out = replay.settle(res(), [str(a), str(b)], None, 40, {})  # 重畫沒畫成：保守，照舊紅
    assert [r["class"] for r in out["real"]] == ["dom", "pixel", "style"] and "red" not in out["real"][1]


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


def test_a_window_set_twice_in_a_row_is_flipped_first():
    # 第 254 批：light 景的第一張（375 淺色 dpr 1）跟前一景收尾設的視窗一樣，不會整頁重畫；決戰卡倒數那一塊每秒重寫，A 對 A 隨機差 1 級 713 px
    node = shutil.which("node")
    if not node:
        pytest.skip("no node")
    src = (TOOL / "snippets.mjs").as_uri()
    code = (f"const {{ sameWindow, SHOT_VIEWS: V }} = await import({json.dumps(src)});"
            "console.log(JSON.stringify([sameWindow(null, V[0], 1), sameWindow([V[0], 1], V[0], 1), sameWindow([V[0], 2], V[0], 1),"
            "sameWindow([V[1], 1], V[0], 1), sameWindow([[...V[0]], 1], V[0], 1), sameWindow([V[2], 1], V[2], 1)]));")
    out = subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True, encoding="utf-8", check=True)
    assert json.loads(out.stdout) == [False, True, False, False, True, True]
    # driver.mjs 跑不起來單測（要瀏覽器）：守先後，不守那一行的字（第 258 批）。一個視窗裡先問 sameWindow、換成另一個 dpr 等它畫過，才設回這個視窗
    text = (TOOL / "driver.mjs").read_text(encoding="utf-8").replace("\r\n", "\n")
    body = text[text.index("async function shootWindow("):]
    body = body[:body.index("\n}\n")]
    ask, back = body.index("sameWindow(lastView, v, d)"), body.index("await setView(v, d);")
    flip_line = body[ask:body.index("\n", ask)]
    assert ask < back and "setView(v, d === 1 ? 2 : 1)" in flip_line and "FLIPPED(d === 1 ? 2 : 1)" in flip_line and "< 0) log(" in flip_line
    setview = text[text.index("async function setView("):]
    assert "lastView = [v, dpr];" in setview[:setview.index("\n}\n")]
    # 視窗拍完再量一次：shoot 先叫 shootWindow、再量 LAYOUT、動了才重拍（最多 RESHOOTS 次）
    shoot = text[text.index("async function shoot(name"):]
    shoot = shoot[:shoot.index("\n}\n")]
    assert shoot.index("await shootWindow(") < shoot.index("await ev(LAYOUT)") < shoot.index("take === RESHOOTS") and "const RESHOOTS = 2;" in text
    # FLIPPED 照行為驗：假的時鐘與畫格，dpr 換成了回畫過的毫秒數，一秒內沒換成回 -1（以前逾時也等兩格、回正數，log 幾乎不印）
    code = (f"const {{ FLIPPED }} = await import({json.dumps(src)}); let t = 0;"
            "Object.defineProperty(globalThis, 'performance', { value: { now: () => (t += 50) }, configurable: true, writable: true });"
            "globalThis.setTimeout = () => 0; globalThis.requestAnimationFrame = (cb) => setImmediate(cb);"
            "const run = async (now, want) => { globalThis.devicePixelRatio = now; t = 0; return await (0, eval)(FLIPPED(want)); };"
            "console.log(JSON.stringify([await run(2, 2), await run(1, 2), await run(2, 1)]));")
    got = json.loads(subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    assert got[0] > 0 and got[1] == -1 and got[2] == -1, got
    flipped = subprocess.run([node, "--input-type=module", "-e", f"const {{ FLIPPED }} = await import({json.dumps(src)}); console.log(FLIPPED(2));"],
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
    assert "setTimeout(() => r(-1), 1500)" in flipped  # 換成了但畫格一直不來：最多 1.5 秒


def test_the_walk_shoots_a_light_scenes_phone_window_again_for_hashes_only():
    # 第 260 批：shootVariants 只在 light 景的 375-light、那個視窗拍完（含捲軸重拍那一圈）之後；只記雜湊，不寫檔、不動 shots、hashes、unstable
    text = (TOOL / "driver.mjs").read_text(encoding="utf-8").replace("\r\n", "\n")
    shoot = text[text.index("async function shoot(name"):]
    shoot = shoot[:shoot.index("\n}\n")]
    call = shoot.index("await shootVariants(id, v, d, facts)")
    assert shoot.index("take === RESHOOTS") < call and 'if (light && v[0] === "375-light") await shootVariants' in shoot
    body = text[text.index("async function shootVariants("):]
    body = body[:body.index("\n}\n")]
    for banned in ("writeFileSync", "hashes[", "facts.shots.push", "facts.unstable", "facts.vol", "grab("):
        assert banned not in body, banned
    assert body.index("FLIPPED(") < body.index("sleep(1100)") and "facts.variants[f].push(await grabHash())" in body


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


def test_what_the_outbox_wraps_is_still_in_the_identity_package(tmp_path):
    # 第 110 批：--outbox 包 FAKES 的 sms.send、mail.send；搬走或改名，閘門帶 --outbox 時才會 exit 3，這裡早一點紅
    tree = ast.parse((TOOL / "serve.py").read_text(encoding="utf-8"))
    names = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "OUTBOX_SENDERS")
    from tianxia.core import identity_base
    from tianxia.features.identity import senders

    assert names and all(callable(getattr(getattr(senders.FAKES, k), "send", None)) for k in names)
    gate = _load("gate")
    gate.seed_local(str(tmp_path), outbox=True)
    assert identity_base.read_key(tmp_path / ".local" / "identity.json"), "測試金鑰要讀得到（至少 16 字）"
    gate.seed_local(str(tmp_path / "plain"))
    assert not (tmp_path / "plain" / ".local" / "identity.json").exists()


def test_the_model_queue_is_off_in_the_wrapper():
    # 佇列一格、別的寫手佔著就跳過，那一篇放回單子等 30 秒，而時鐘是凍的：第 77 批第一次全量 extra:069～074 一邊多一筆天下形勢
    text = (TOOL / "serve.py").read_text(encoding="utf-8")
    assert "server.make_queue = lambda config: None" in text
    assert "server.make_queue" not in text.split("import server", 1)[0]


def test_every_named_thread_is_a_writer_or_a_loop():
    # 名單用完全相等比，zhuan-<季> 永遠對不上、tavern-chatter 沒列：列傳寫好的畫面走不到（第 77 批審查）。新開的背景執行緒也要在這裡表態
    loops = {"world-scheduler", "push-watch", "narration", "notice-watch", "tales", "support-purge"}  # support-purge：只刪結案一年的客服單，不寫畫面
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


def test_a_stroke_closes_the_patch_sheet_first():
    """第 112 批：進遊戲後跳的改版資訊（web/news.js .patch-pop）、簽到小窗（web/checkin.js .ck-pop）蓋在畫布上，滑鼠那一筆畫不到
    （sense_pad_clear、sense_sent 走不到）：每個畫一筆的 flow（c.drawOn），第一筆之前同一個 flow 裡要先點掉跳出來的那幾張（.sheet-bg）。"""
    for path in sorted((TOOL / "flows").glob("*.mjs")):
        text = path.read_text(encoding="utf-8")
        for flow in re.split(r'\n    \["', text):
            if "drawOn(" in flow:
                assert ".sheet-bg[data-act]" in flow[:flow.index("drawOn(")], f"{path.name} 有一個 flow 畫一筆之前沒關跳出來的小窗"


def test_main_closes_the_patch_sheet_after_one_picture_and_waits_for_the_ink_picture():
    """第 113 批：driver 的 load() 不關改版資訊（.patch-pop），它蓋在 main 回合前 128 景的下半頁、也讓人物層底下的 body.layer-open
    一直開著（call_close、call_act 量到捲軸 1280 對 1265）。main 第一次進遊戲（prep）先拍 patch_pop、再按「知道了」關掉；
    zh_write 的水墨是 loading="lazy" 的圖，拍之前等它載完、decode 完（base＝head 偶爾像素 REAL）。"""
    text = (TOOL / "flows" / "main.mjs").read_text(encoding="utf-8")
    prep = next(f for f in re.split(r'\n  \["', text) if f.startswith('prep"'))
    assert prep.index('shoot("patch_pop"') < prep.index('[data-act="patch-close"]') < prep.index('shoot("prep_growth"')
    assert '"call_close"' in text and '"call_act"' in text
    seasonend = next(f for f in re.split(r'\n    \["', text) if f.startswith('seasonend"'))
    assert seasonend.index(".decode()") < seasonend.index('shoot("zh_write"')
    rows = set((TOOL / "must_reach.txt").read_text(encoding="utf-8").splitlines())
    assert {"main:patch_pop", "main:call_close", "main:call_act", "main:zh_write"} <= rows


def test_main_loads_the_page_again_before_the_invite_picture():
    """第 260 批：江湖新事邀請卡（第 233 批）排在第 113 批那次重載前面，nx_invite 兩邊偶爾一邊 LCD、一邊灰階反鋸齒（載入時就定了，
    重畫不換）。asPlayer("p3") 之後、查 .sheet.nx-invite 之前多載入一次；守先後，不守那一行的字。"""
    text = (TOOL / "flows" / "main.mjs").read_text(encoding="utf-8").replace("\r\n", "\n")
    prep = next(f for f in re.split(r'\n  \["', text) if f.startswith('prep"'))
    player, invite = prep.index('asPlayer("p3")'), prep.index('.sheet.nx-invite")')
    assert 'await c.load("/");' in prep[player:invite]
    assert invite < prep.index('shoot("nx_invite"')


def test_main_walks_support_between_notify_and_mall_and_puts_the_staff_list_back_in_finally():
    """第 236 批：客服在 week7、season21 打開了。main 回合在 notify 與 mall 之間走一趟客服：玩家寫一張文字單，不是管理者的走查帳號
    只在這個伺服器行程的記憶體裡放進客服名單（Config.support.staff，不寫檔、不設環境變數），重新用密碼登入（staff_session_ok）到 /admin
    回覆，同一個 flow 裡把名單還原；玩家讀過回覆，紅點滅掉，後面的景不多一個紅點。景名手加進 must_reach（不用 --write-must-reach）。
    第 238 批：放名單與還原之間包成 try/finally（click、ev 丟例外時名單照樣還原）。"""
    text = (TOOL / "flows" / "main.mjs").read_text(encoding="utf-8")
    assert text.index('\n    ["notify"') < text.index('\n    ["support"') < text.index('\n    ["mall"')
    sup = next(f for f in re.split(r'\n    \["', text) if f.startswith('support"'))
    put = sup.index("content.config.support.staff = [*content.config.support.staff, 'qaplayer4']")
    back = sup.index("content.config.support.staff = [s for s in content.config.support.staff if s != 'qaplayer4']")
    opened = sup.index("try {", put)
    closed = sup.index("} finally {", put)
    assert put < opened < sup.index('relogin("p4")') < sup.index('load("/admin")') < sup.index('"sup_desk_answered"') < closed < back
    assert "await" not in sup[put:opened]  # nothing else runs between putting the name on and the try
    assert back < sup.index('"sup_mine_answered"')
    # 第 238 批：寫單附截圖（頁面裡造固定的 PNG，挑圖那一下 createObjectURL 換成 data: 網址、finally 換回），再讓走查的管理者
    # 只在記憶體裡上名單、從 /admin 頂列「客服單 ›」進客服頁看到縮圖、點「‹ 管理者工具」回來，名單在 finally 還原
    pick = sup.index('"sup_pick"')
    swap = sup.index("URL.createObjectURL = () =>")
    assert sup.index('"sup_ticket_read"') < swap < sup.index("finally { URL.createObjectURL = was; }") < pick
    put_admin = sup.index("content.config.support.staff = [*content.config.support.staff, 'qaadmin']")
    back_admin = sup.index("content.config.support.staff = [s for s in content.config.support.staff if s != 'qaadmin']")
    opened_admin = sup.index("try {", put_admin)
    closed_admin = sup.index("} finally {", put_admin)
    assert pick < sup.index('"sup_sent_shot"') < put_admin
    assert "await" not in sup[put_admin:opened_admin]
    assert put_admin < opened_admin < sup.index('relogin("admin")') < sup.index('"sup_admin"') < sup.index('"sup_admin_desk"') \
        < sup.index('"sup_admin_desk_shot"') < sup.index('"sup_admin_back"') < closed_admin < back_admin
    assert "support-desk-enter" in sup and "support-desk-leave" in sup
    driver = (TOOL / "driver.mjs").read_text(encoding="utf-8")
    assert "async function relogin(who)" in driver and "relogin," in driver
    lines = (TOOL / "must_reach.txt").read_text(encoding="utf-8").splitlines()
    names = ["sup_mine", "sup_new", "sup_sent", "sup_desk", "sup_desk_pick", "sup_desk_answered", "sup_dot", "sup_dot_sheet", "sup_mine_answered", "sup_ticket_read",
             "sup_pick", "sup_sent_shot", "sup_admin", "sup_admin_desk", "sup_admin_desk_shot", "sup_admin_back"]
    assert {f"main:{n}" for n in names} <= set(lines)
    at = [lines.index(f"main:{n}") for n in names]
    assert at == sorted(at) and lines.index("main:sup_admin_back") < lines.index("main:mall")
    shots = [sup.index(f'"{n}"') for n in names]
    assert shots == sorted(shots)


# ── 第 107 批：回合對照表（coverage.json）與 --changed-files ──


def test_the_coverage_table_checks_out():
    coverage = _load("coverage")
    assert coverage.check() == [], "scripts/webqa/coverage.json 對不上：照 coverage.py 的說明重跑一次（不帶 --quick）再 build"


def test_a_missing_file_in_the_table_is_caught(tmp_path):
    coverage = _load("coverage")
    table = json.loads((TOOL / "coverage.json").read_text(encoding="utf-8"))
    table[next(iter(table))].append("web/no_such_file.js")
    bad = tmp_path / "coverage.json"
    bad.write_text(json.dumps(table), encoding="utf-8")
    assert any("no_such_file" in p for p in coverage.check(str(bad)))


def test_a_script_no_round_reaches_has_to_say_why(tmp_path):
    # 第 110 批：web/*.js 不在表上、不是殼、NOT_ON_TABLE 也沒寫理由，check 要紅；寫在 NOT_ON_TABLE 卻有回合走到也紅
    coverage, gate = _load("coverage"), _load("gate")
    table = json.loads((TOOL / "coverage.json").read_text(encoding="utf-8"))
    thin = {r: [f for f in files if f != "web/seal.js"] for r, files in table.items()}
    bad = tmp_path / "coverage.json"
    bad.write_text(json.dumps(thin), encoding="utf-8")
    assert any(p.startswith("web/seal.js is reached by no round") for p in coverage.check(str(bad)))
    stale = {r: [*files, "web/sw.js"] for r, files in table.items()}
    bad.write_text(json.dumps(stale), encoding="utf-8")
    assert any("web/sw.js is in gate.NOT_ON_TABLE" in p for p in coverage.check(str(bad)))
    assert "web/sw.js" in gate.NOT_ON_TABLE


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
    out = dry("web/explore.js")  # 包的檔、沒有回合走到、NOT_ON_TABLE 寫了為什麼（identity.js 關著也有函式在登入頁跑，在表上：第 110 批量到）
    assert "rounds: (none)" in out and "not walked: web/explore.js" in out
    gate = _load("gate")
    assert f"rounds: {','.join(gate.ROUNDS)}" in dry("web/app.js")


def test_nothing_to_walk_is_green_before_anything_is_looked_for(tmp_path):
    r = _gate(tmp_path, "--changed-files=", "--chrome", str(tmp_path / "no-such-chrome.exe"))
    assert r.returncode == 0, r.stdout
    summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
    assert summary["green"] and summary["rounds"] == [] and not summary["tool"]
    assert "NOTHING TO WALK" in (tmp_path / "out" / "report.txt").read_text(encoding="utf-8").splitlines()[0]


# ── 第 256 批：yw 回合（異聞）──

def _yw_copy(root: Path, *, writer=True, route=True, tuning=True) -> str:
    pkg = root / "tianxia" / "features" / "yiwen"
    pkg.mkdir(parents=True)
    (pkg / "writer.py").write_text("def write_scene(client_for, request, tuning, left, content):\n    pass\n" if writer else "def write_one():\n    pass\n", encoding="utf-8")
    (pkg / "routes.py").write_text('OPS = {"yiwen_step": None}\n' if route else "OPS = {}\n", encoding="utf-8")
    if tuning:
        (root / "tianxia" / "core" / "tuning").mkdir(parents=True)
        (root / "tianxia" / "core" / "tuning" / "yiwen.py").write_text("discover_chance: float = 0.0002\n", encoding="utf-8")
    return str(root)


def test_a_side_without_the_storyteller_cannot_walk_the_yw_round(tmp_path):
    gate = _load("gate")
    full = _yw_copy(tmp_path / "full")
    assert gate.round_cannot_walk(full, "yw") is None
    assert gate.round_cannot_walk(str(tmp_path / "empty"), "main") is None, "別的回合沒有要求"
    assert "write_scene" in gate.round_cannot_walk(_yw_copy(tmp_path / "w", writer=False), "yw")
    assert "yiwen_step" in gate.round_cannot_walk(_yw_copy(tmp_path / "r", route=False), "yw")
    assert "no tianxia/core/tuning/yiwen.py" == gate.round_cannot_walk(_yw_copy(tmp_path / "t", tuning=False), "yw")
    assert gate.round_cannot_walk(str(tmp_path / "empty"), "yw") == "no tianxia/features/yiwen/writer.py"
    assert gate.round_cannot_walk(str(ROOT), "yw") is None, "這一份程式自己要走得了"


def test_new_yiwen_lists_the_yw_rounds_differences_and_keeps_the_heads_errors_red():
    gate = _load("gate")
    rows = [{"round": "yw", "scene": "010_yw_wait", "class": "pixel", "detail": {}},
            {"round": "yw", "scene": "(walk)", "class": "steps", "detail": []},
            {"round": "yw", "scene": "011_yw_act1", "class": "console-head-only", "detail": ""},
            {"round": "yw", "scene": "(css)", "class": "css-rules", "detail": {}},
            {"round": "yw", "scene": "012_yw_act2", "class": "words", "detail": ""},
            {"round": "main", "scene": "001_x", "class": "pixel", "detail": {}},
            {"round": "replay", "scene": "yw-010_yw_wait", "class": "pixel", "detail": {}},
            {"round": "replay-anim", "scene": "main-001_x", "class": "style", "detail": {}},
            {"round": "(static)", "scene": "img/a.png", "class": "static-file", "detail": []}]
    kept, listed = gate.split_round_new(rows, ["yiwen"])
    assert [(r["round"], r["scene"]) for r in listed] == [("yw", "010_yw_wait"), ("yw", "(walk)"), ("replay", "yw-010_yw_wait")]
    assert {r["class"] for r in kept if r["round"] == "yw"} == {"console-head-only", "css-rules", "words"}
    assert gate.split_round_new(rows, ["identity"]) == (rows, []), "不帶 --new yiwen：一列都不動"
    assert gate.split_round_new(rows, []) == (rows, [])
    assert gate.ROUND_PACKAGE == {"yw": "yiwen", "uf": "unfold"} and "yw" in gate.ROUNDS and (TOOL / "flows" / "yw.mjs").exists()
    assert "uf" in gate.ROUNDS and (TOOL / "flows" / "uf.mjs").exists()  # batch 272: the unfolding book's round


def test_a_skipped_round_and_the_listed_rows_are_in_the_report(tmp_path):
    gate = _load("gate")
    skip = "yw: 這一邊走不了：base no tianxia/features/yiwen/writer.py"
    gate.write_report(str(tmp_path), {"base": "a", "head": "b", "green": True, "exit": 0, "rounds": [], "rounds_why": "every round left was skipped", "skipped": [skip]}, {})
    lines = (tmp_path / "report.txt").read_text(encoding="utf-8").splitlines()
    assert "NOTHING TO WALK (exit 0)" in lines[0] and f"SKIPPED {skip}" in lines
    summary = {"base": "a", "head": "b", "green": True, "exit": 0, "rounds": ["main"], "scenes": 1, "shots": 1, "same_shots": 1, "seconds": 1, "noise": {}, "fingerprint": {},
               "replay": {}, "tool": [], "real": [], "expected": [], "must_reach_quick_missing": [], "not_reached": [], "skipped": [skip],
               "new_rows": [{"round": "yw", "scene": "010_yw_wait", "class": "pixel", "detail": {"file": "010_yw_wait__375-light.png"}}]}
    gate.write_report(str(tmp_path), summary, {})
    lines = (tmp_path / "report.txt").read_text(encoding="utf-8").splitlines()
    assert f"SKIPPED {skip}" in lines and any(x.startswith("NEW yw:010_yw_wait pixel ") for x in lines)


# ── 第 262 批：head 把異聞弄丟記紅，base 沒有才略過 ──

def test_the_head_losing_a_round_the_base_walks_is_real_not_skipped(tmp_path):
    gate = _load("gate")
    full, old = _yw_copy(tmp_path / "full"), _yw_copy(tmp_path / "old", writer=False)
    why = lambda copy: {r: gate.round_cannot_walk(copy, r) for r in ("main", "yw")}
    assert gate.split_unwalkable(["main", "yw"], why(full), why(full)) == (["main", "yw"], [], []), "兩邊都有：照走"
    keep, skipped, lost = gate.split_unwalkable(["main", "yw"], why(old), why(full))
    assert keep == ["main"] and lost == [] and skipped == ["yw: 這一邊走不了：base tianxia/features/yiwen/writer.py has no def write_scene"], "base 比 AI 波舊：照舊略過"
    keep, skipped, lost = gate.split_unwalkable(["main", "yw"], why(old), why(old))
    assert keep == ["main"] and lost == [] and len(skipped) == 1 and "; head " in skipped[0], "兩邊都沒有：略過，兩邊都寫"
    keep, skipped, lost = gate.split_unwalkable(["main", "yw"], why(full), why(old))
    assert keep == ["main"] and skipped == []
    assert lost == [{"round": "yw", "scene": "(round)", "class": "round-lost", "detail": "head tianxia/features/yiwen/writer.py has no def write_scene"}], "head 退化：REAL"
    kept, listed = gate.split_round_new(lost, ["yiwen"])
    assert kept == lost and listed == [], "--new yiwen 也不轉成 NEW"
    summary = {"base": "a", "head": "b", "green": False, "exit": 1, "rounds": [], "scenes": 0, "shots": 0, "same_shots": 0, "seconds": 1, "noise": {}, "fingerprint": {},
               "replay": {"ran": False, "why": "every round left was lost on the head"}, "tool": [], "real": lost, "expected": [], "must_reach_quick_missing": [], "not_reached": []}
    gate.write_report(str(tmp_path), summary, {})
    lines = (tmp_path / "report.txt").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "webqa a -> b: RED (exit 1)"
    assert 'REAL yw:(round) round-lost "head tianxia/features/yiwen/writer.py has no def write_scene"' in lines


def test_the_yw_padding_mutation_touches_the_meeting_card_only(tmp_path):
    gate = _load("gate")
    web = tmp_path / "web"
    web.mkdir()
    css = "/* a */\n.yw-wrap { position: fixed; }\n.yw-card { box-sizing: border-box; padding: 0 16px; }\n.yw-card p { margin: 0; }\n"
    (web / "yiwen.css").write_text(css, encoding="utf-8", newline="")
    gate.mutate(str(tmp_path), gate.YW_PADDING)
    got = (web / "yiwen.css").read_text(encoding="utf-8")
    assert got == css.replace("padding: 0 16px; }", "padding: 0 16px;  padding: 31px 23px; }")
    assert "\n.yw-card {" in (ROOT / "web" / "yiwen.css").read_text(encoding="utf-8"), "撞見卡的規則換了寫法，突變要跟著換"
    (web / "yiwen.css").write_text("/* nothing */\n", encoding="utf-8")
    with pytest.raises(gate.ToolBroke):
        gate.mutate(str(tmp_path), gate.YW_PADDING)


def test_the_jh_padding_mutation_touches_the_new_jianghu_page_only(tmp_path):
    """Batch 272: the control that proves the new 江湖頁 is looked at changes one rule of web/jianghu.css, .jh-page."""
    gate = _load("gate")
    web = tmp_path / "web"
    web.mkdir()
    css = "/* a */\n.jh-page { --jh-fade: 1; position: relative; }\n.jh-page .x { margin: 0; }\n"
    (web / "jianghu.css").write_text(css, encoding="utf-8", newline="")
    gate.mutate(str(tmp_path), gate.JH_PADDING)
    got = (web / "jianghu.css").read_text(encoding="utf-8")
    assert got == css.replace("position: relative; }", "position: relative;  padding: 31px 23px; }", 1)
    assert "\n.jh-page {" in (ROOT / "web" / "jianghu.css").read_text(encoding="utf-8"), "江湖頁的規則換了寫法，突變要跟著換"
    (web / "jianghu.css").write_text("/* nothing */\n", encoding="utf-8")
    with pytest.raises(gate.ToolBroke):
        gate.mutate(str(tmp_path), gate.JH_PADDING)


def test_only_the_uf_round_leaves_the_unfolding_book_on():
    """Batch 272: serve.py turns unfold off for every round but uf (every walk account is new; old characters see the page laid out)."""
    text = (TOOL / "serve.py").read_text(encoding="utf-8")
    assert 'if os.environ.get("QA_ROUND") != "uf" and getattr(server.CONTENT.config, "unfold", None) is not None:' in text
    assert "server.CONTENT.config.unfold.enabled = False" in text


def test_only_the_yw_round_turns_the_strange_tales_on_and_its_patch_targets_are_there():
    text = (TOOL / "serve.py").read_text(encoding="utf-8")
    assert 'YW = os.environ.get("QA_ROUND") == "yw"' in text
    block = text.split("if YW:", 1)[1].split("\nfrom fastapi", 1)[0]
    assert "_yw.enabled, _yw.discover_chance, _yw.rewalk_chance = True, 1.0, 1.0" in block
    assert text.count("if YW:") == 2, "改設定與 /__qa/py 的 hold 都只在 yw 回合"
    from tianxia.features.yiwen import routes, writer

    assert callable(writer.write_scene) and "writer.write_scene(" in (ROOT / "tianxia" / "features" / "yiwen" / "routes.py").read_text(encoding="utf-8"), "routes 照模組屬性叫寫幕，閘才包得到"
    assert "shell.screen_text(" in (ROOT / "tianxia" / "features" / "yiwen" / "routes.py").read_text(encoding="utf-8") and "screen_text" in _names_in(ROOT / "server.py")
    from tianxia.core.tuning.yiwen import YiwenTuning

    assert {"enabled", "discover_chance", "rewalk_chance"} <= set(YiwenTuning.model_fields)
    flow = (TOOL / "flows" / "yw.mjs").read_text(encoding="utf-8")
    bad = re.search(r'YW_BAD_WORDS = "([^"]+)"', text).group(1)
    assert f'const BAD = "{bad}"' in flow, "走查送的那一句要等於假的審字認的那一句"
    from tianxia.content import load_content
    from tianxia.features.yiwen import rules as yw_rules

    content = load_content(ROOT / "content", "season21")
    assert yw_rules.typed_problem(bad, content, content.config.yiwen) is None, "那一句要過得了 A 段，才會走到審字"
    assert routes is not None


def test_the_yw_scenes_are_in_must_reach():
    rows = (TOOL / "must_reach.txt").read_text(encoding="utf-8").splitlines()
    flow = (TOOL / "flows" / "yw.mjs").read_text(encoding="utf-8")
    shot = set(re.findall(r'"(yw_[a-z0-9_]+)"', flow)) - {"yw_out", "yw_walk", "yw_trail"}
    assert shot and {line.split(":", 1)[1] for line in rows if line.startswith("yw:")} == shot


# ── 第 262 批：掛在 #app 外、固定定位、自己捲的層捲著拍 ──

SCROLLER_FAKE = r"""
const { SCROLLER } = await import(SRC);
const W = 375, H = 812;
const mk = (id, o) => ({ id, inApp: false, pos: "static", oy: "visible", vis: "visible", sh: H, ch: H, z: 0, rect: [0, 0, W, H], ...o,
  get scrollHeight() { return this.sh; }, get clientHeight() { return this.ch; }, get clientWidth() { return this.rect[2] - this.rect[0]; },
  closest(sel) { return sel === "#app" && this.inApp ? {} : null; }, contains(x) { return x === this; },
  getBoundingClientRect() { const [l, t, r, b] = this.rect; return { left: l, top: t, right: r, bottom: b, width: r - l, height: b - t }; } });
const run = (els, rootSh) => {
  const root = mk("root", { sh: rootSh, ch: H });
  const doc = { scrollingElement: root, querySelectorAll: (sel) => sel === "#app *" ? els.filter((e) => e.inApp) : sel === "body *" ? els : [],
    elementFromPoint: (x, y) => els.filter((e) => { const [l, t, r, b] = e.rect; return x >= l && x <= r && y >= t && y <= b; }).sort((a, b) => b.z - a.z)[0] || null };
  const win = {};
  const f = new Function("window", "document", "getComputedStyle", "innerWidth", "innerHeight", "return " + SCROLLER);
  const got = f(win, doc, (e) => ({ position: e.pos, overflowY: e.oy, visibility: e.vis }), W, H);
  return got && { ...got, id: win.__sc && win.__sc.id };
};
const app = () => mk("panel", { inApp: true, oy: "auto", sh: 2000, ch: 600, z: 1, rect: [0, 100, W, 700] });
const card = (id, o) => mk(id, { pos: "fixed", oy: "auto", sh: 1900, ch: H, z: 10, ...o });
console.log(JSON.stringify([
  run([app(), card("yw")], 3000),
  run([card("top", { z: 20 }), app(), card("under", { z: 5 })], 3000),
  run([app(), card("short", { sh: H, z: 0 })], 3000),
  run([app(), card("abs", { pos: "absolute", z: 0 })], 3000),
  run([app(), card("hidden", { vis: "hidden", z: 0 })], 3000),
  run([app(), card("inside", { inApp: true })], 3000),
  run([], 3000),
  run([], H),
]));
"""


def test_a_fixed_layer_outside_the_app_that_scrolls_is_what_the_pictures_scroll():
    node = shutil.which("node")
    if not node:
        pytest.skip("no node")
    code = f"const SRC = {json.dumps((TOOL / 'snippets.mjs').as_uri())};" + SCROLLER_FAKE
    got = json.loads(subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    assert got[0] == {"sh": 1900, "ch": H_812, "root": False, "id": "yw"}, "頁面外、固定定位、自己捲：選它，不選 #app 裡的"
    assert got[1]["id"] == "top", "兩層都會捲：中心點落在上面那一層的才算（不是 DOM 最後那一層）"
    assert got[2]["id"] == "panel" and got[3]["id"] == "panel" and got[4]["id"] == "panel", "不會捲、不是固定定位、看不見：走原來那一段"
    assert got[5]["id"] == "inside", "#app 裡的固定層照原來那一段比面積（它最大）"
    assert got[6] == {"sh": 3000, "ch": H_812, "root": True, "id": "root"} and got[7] is None, "沒有那種層：跟以前一樣"
    text = (TOOL / "driver.mjs").read_text(encoding="utf-8")
    assert "const SCROLLER" not in text and text.count("await ev(SCROLLER)") == 2, "driver 用 snippets 的那一份（shootWindow、shootVariants）"


H_812 = 812
