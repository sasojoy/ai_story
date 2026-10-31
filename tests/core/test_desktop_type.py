"""電腦寬的店面字級（FB-305，企劃者 10/16 從對照圖選甲）：web/style.css 店面那一段（三間店、擂台、素材頁與軍需帳）每一條寫了字級的
規則，在 @media (min-width: 641px) 裡都有一條同一個選擇器（不是掛在 .shop-layer／.shop-board 底下的前面加 :where(.shop-layer)，
權重不變）、字級 ×1.3（四捨五入到 0.5px）的，而且先後跟店面那一段一樣；手機（沒有 media 的那一條）的值不動。
功能包切出去的樣式（開發規範手冊 3.7；FEATURES 登記的 web 裡的 .css，現在是商城的 web/mall.css）一起管：那個檔裡掛在店面那一層
（.shop-layer／.shop-board）底下、不在 media 裡的規則算店面那一段，接在 style.css 那一段後面（index.html 照這個順序載入）；
電腦寬那一段同樣接在 style.css 的後面。
讀的是 CSS 原文：webharness 沒有排版，量不到 computed style（實機比對在 docs/superpowers/feedback/ 的 FB-305 那一筆）。"""
from __future__ import annotations

import re
from pathlib import Path
import html
from urllib.parse import unquote_plus, urlparse
import pytest
import zhuan_html

from tianxia.core import features as features_core

CSS = (Path(__file__).resolve().parents[2] / "web" / "style.css").read_text(encoding="utf-8")
# 功能包的樣式（index.html 排在 style.css 後面；第 3 階才由伺服器照 FEATURES 生成，這裡照登記的順序讀）
FEATURE_CSS = [(Path(__file__).resolve().parents[2] / "web" / name).read_text(encoding="utf-8")
               for name in features_core.web_files() if name.endswith(".css")]
SHOP_START = "/* ── 店面（店面獨立介面設計第五節）"
SHOP_END = "/* ── 電腦上的店面與武學譜那本書（FB-225"
K = 1.3
LAYER = (".shop-smith", ".shop-market", ".shop-donate", ".shop-arena")  # 掛在店面那一層本身的 class


def _scoped(sel: str) -> str:
    """店面那一條在電腦寬那一段的選擇器：掛在店面那一層底下、權重不變。"""
    parts = []
    for part in (p.strip() for p in sel.split(",")):
        if part.startswith((".shop-layer", ".shop-board")):
            parts.append(part)
        elif part.startswith(LAYER):
            parts.append(":where(.shop-layer)" + part)
        else:
            parts.append(":where(.shop-layer) " + part)
    return ", ".join(parts)


def _strip(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _blocks(css: str) -> list[tuple[str, str]]:
    """最外層的（選擇器或 @規則, 內容）。"""
    out, depth, start, head, body = [], 0, 0, "", 0
    for i, ch in enumerate(css):
        if ch == "{":
            if depth == 0:
                head, body = css[start:i].strip(), i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                out.append((head, css[body:i]))
                start = i + 1
    return out


def _sizes(body: str) -> dict[str, str]:
    """一條規則裡的 font-size 與 font（有 px 的那幾個）。"""
    found = {}
    for decl in body.split(";"):
        if ":" in decl:
            prop, val = (x.strip() for x in decl.split(":", 1))
            if prop in ("font-size", "font") and "px" in val:
                found[prop] = val
    return found


def _scaled(val: str) -> str:
    return re.sub(r"(\d+(?:\.\d+)?)px", lambda m: f"{round(float(m.group(1)) * K * 2) / 2:g}px", val)


def _in_shop(sel: str) -> bool:
    """功能包的 CSS 裡算店面那一段的規則：每一個選擇器都掛在店面那一層底下。"""
    return all(part.strip().startswith((".shop-layer", ".shop-board")) for part in sel.split(","))


def _shop_base() -> dict[str, dict[str, str]]:
    section = _strip(CSS[CSS.index(SHOP_START): CSS.index(SHOP_END)])
    base = {sel: _sizes(body) for sel, body in _blocks(section) if not sel.startswith("@") and _sizes(body)}
    for css in FEATURE_CSS:  # 功能包切出去的店面（商城那一層）接在後面
        base.update({sel: _sizes(body) for sel, body in _blocks(_strip(css)) if not sel.startswith("@") and _in_shop(sel) and _sizes(body)})
    return base


def _desktop() -> dict[str, dict[str, str]]:
    rules: dict[str, dict[str, str]] = {}
    for css in [CSS, *FEATURE_CSS]:
        for head, body in _blocks(_strip(css)):
            if head.replace(" ", "") == "@media(min-width:641px)":
                for sel, inner in _blocks(body):
                    rules.setdefault(sel, {}).update(_sizes(inner))
    return rules


def test_every_shop_size_has_a_desktop_rule_one_point_three_times_bigger():
    base, desk = _shop_base(), _desktop()
    assert len(base) > 100  # 三間店、擂台、素材頁與軍需帳都在這一段
    assert sum(sel.startswith(".shop-layer.shop-mall") for sel in base) >= 20  # 商城那一層（web/mall.css）也在：讀漏了這一條就空轉
    missing = {sel: (sizes, desk.get(_scoped(sel))) for sel, sizes in base.items()
               if {prop: _scaled(val) for prop, val in sizes.items()} != {prop: desk.get(_scoped(sel), {}).get(prop) for prop in sizes}}
    assert not missing, missing


def test_the_desktop_twins_keep_the_shop_order():
    """先後跟店面那一段一樣（權重也一樣），電腦上誰蓋過誰才跟手機一模一樣。"""
    twins = [_scoped(sel) for sel in _shop_base()]
    assert [sel for sel in _desktop() if sel in set(twins)] == twins


def test_the_notice_tag_title_and_due_line_on_desktop():
    desk = _desktop()
    assert desk[".shop-board .note .tag, .shop-board .paper .tag"]["font-size"] == "12.5px"
    assert desk[".shop-board .note b"]["font"].startswith("600 17px")
    assert desk[".shop-board .note small"]["font-size"] == "12.5px"
    assert desk[".shop-board .board-sheet .paper"]["font-size"] == "16px"
    assert desk[":where(.shop-layer) .shop-line"]["font"].startswith("17px/")


def test_the_phone_sizes_are_untouched():
    base = _shop_base()
    assert base[".shop-board .note .tag, .shop-board .paper .tag"]["font-size"] == "9.5px"
    assert base[".shop-board .note b"]["font"].startswith("600 13px")
    assert base[".shop-board .note small"]["font-size"] == "9.5px"
    assert base[".shop-line"]["font"].startswith("13px/")


def test_text_that_inherits_its_size_grows_too_but_only_inside_the_shop():
    desk = _desktop()
    assert desk[".shop-layer"]["font-size"] == "19.5px"  # 吃 body 15px 的
    assert desk[":where(.shop-layer) .btn"]["font-size"] == "19.5px" and desk[":where(.shop-layer) .btn.small"]["font-size"] == "18px"
    assert all(sel.startswith((".shop-layer", ".shop-board", ".book-", ":where(.shop-layer)")) for sel in desk if "shop" in sel)
    assert ".shell" not in desk and "body" not in desk  # 江湖頁、修練頁不動


# ── 原 test_fb575_serif_weights.py（整檔搬進來） ──
# FB-575：全站寫 400 的襯線字（行狀、武學譜與鑄譜那本書、書信、店面的話……）顯示成粗體。
# 原因：網頁字型只從 Google Fonts 拿了 Noto Serif TC 的 700；瀏覽器照 CSS 的字重配對（CSS Fonts 4 第 5.2 節），要 400 而這一家只有 700，
# 就用 700 那一張——全站的 `--serif`、`--bk-serif` 底下寫 400 的地方都變粗。
# 修法：載入頁面真的會用到的字重（400 與 700；寫 600、800、900 的地方配對下去照舊是 700），不多載。公開的傳（/zhuan/<代碼>）只有印章那一處用
# Noto Serif TC（700），內文是霞鶩文楷（400、700 都載了），所以那一頁不多載 400。
# 這裡不開瀏覽器：把「頁面載了哪些字重」「CSS 要哪些字重」都從原文讀出來，再照瀏覽器配對字重的規則算每一個要的字重落在哪一張。

WEB = Path(__file__).parents[2] / "web"


GOOGLE = re.compile(r"https://fonts\.googleapis\.com/css2\?[^\"')\s]+")


NOTO = "Noto Serif TC"


LXGW = "LXGW WenKai TC"


# 每一家字型在 CSS 裡怎麼被叫到：我們自己的變數與字型名
USES = {
    NOTO: re.compile(r"var\(--(?:bk-)?serif\)|Noto Serif TC"),
    LXGW: re.compile(r"var\(--zh-font\)|var\(--zh-title-font|LXGW WenKai TC"),
}


def snap(wanted: int, loaded: set[int]) -> int:
    """瀏覽器把要的字重配到這一家有的哪一張（CSS Fonts 4 第 5.2 節）。"""
    assert loaded, "這一家一張都沒載"
    if wanted in loaded:
        return wanted
    above, below = sorted(w for w in loaded if w > wanted), sorted((w for w in loaded if w < wanted), reverse=True)
    if 400 <= wanted <= 500:  # 先往上找到 500 為止，再往下，最後才越過 500 往上
        first = [w for w in above if w <= 500]
        return (first + below + [w for w in above if w > 500])[0]
    if wanted < 400:
        return (below + above)[0]
    return (above + below)[0]  # 比 500 重：先往更重找，再往輕


def families(text: str) -> dict[str, set[int]]:
    """文字（HTML 或 CSS）裡所有 Google Fonts 的網址要的字型與字重；沒寫 wght 就是 400 一張。"""
    out: dict[str, set[int]] = {}
    for url in GOOGLE.findall(html.unescape(text)):
        for part in urlparse(url).query.split("&"):
            if not part.startswith("family="):
                continue
            name, _, axes = unquote_plus(part[len("family="):]).partition(":")
            weights: set[int] = set()
            found = re.search(r"wght@([\d;.]+)", axes)
            for token in (found.group(1).split(";") if found else ["400"]):
                if ".." in token:
                    low, high = token.split("..")
                    weights |= set(range(int(low), int(high) + 1, 100))
                else:
                    weights.add(int(token))
            out.setdefault(name, set()).update(weights)
    return out


def loaded_by_page(page: str) -> dict[str, set[int]]:
    """一頁載入的字型：頁面自己的 <link>、加上它連到的 /static/*.css 裡的 @import。"""
    out = families(page)
    for href in re.findall(r"""<link[^>]*rel=["']stylesheet["'][^>]*href=["']/static/([^"'?]+)""", page):
        for family, weights in families((WEB / href).read_text(encoding="utf-8")).items():
            out.setdefault(family, set()).update(weights)
    return out


def requested(css: str, family: str) -> dict[int, list[str]]:
    """CSS 裡明明白白向這一家要的字重 → 哪些選擇器。簡寫 `font:` 沒寫字重就是 400（簡寫會把字重重設）；只寫 font-family
    沒寫字重的規則是繼承來的，看不出要幾，不算。"""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out: dict[int, list[str]] = {}
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        decls = [d.split(":", 1) for d in body.split(";") if ":" in d]
        decls = [(p.strip(), v.strip()) for p, v in decls if not p.strip().startswith("--")]
        weight = None
        for prop, value in decls:
            if prop == "font" and USES[family].search(value):
                token = next((t for t in re.split(r"[\s/]+", value) if re.fullmatch(r"[1-9]00|normal|bold", t)), "normal")
                weight = {"normal": 400, "bold": 700}.get(token) or int(token)
            elif prop == "font-family" and USES[family].search(value) and weight is None:
                weight = -1  # 只知道用這一家，字重看底下的 font-weight 或繼承
        if weight is None:
            continue
        for prop, value in decls:
            if prop == "font-weight" and re.fullmatch(r"[1-9]00|normal|bold", value):
                weight = {"normal": 400, "bold": 700}.get(value) or int(value)
        if weight > 0:
            out.setdefault(weight, []).append(" ".join(selector.split()))
    return out


def _page_of_public_zhuan() -> str:
    return zhuan_html.page({"name": "沈浪", "text": "沈浪者，江湖人也。\n\n評曰：可。", "season": 1}, "第一季", "http://x/zhuan/a", "http://x/og.png")


def _check(page: str, css_files: list[str], family: str):
    """這一頁向這一家要的每個字重，都配到「要幾就是幾」的那一張或是照舊往粗的那一張；載了的每一張都有人要，沒有多載。"""
    loaded = loaded_by_page(page).get(family, set())
    wanted: dict[int, list[str]] = {}
    for name in css_files:
        for weight, where in requested((WEB / name).read_text(encoding="utf-8") if name != "zhuan_html.CSS" else zhuan_html.CSS, family).items():
            wanted.setdefault(weight, []).extend(where)
    return loaded, wanted


def test_the_snap_rule_is_what_the_browser_does():
    """這個測試的尺：只載 700 時要 400 配到 700（FB-575 的現狀）；載 400、700 時 600、800、900 配到 700、500 配到 400。"""
    assert snap(400, {700}) == 700
    assert [snap(w, {400, 700}) for w in (400, 500, 600, 700, 800, 900)] == [400, 400, 700, 700, 700, 700]
    assert snap(300, {400, 700}) == 400
    assert snap(400, {300, 700}) == 300  # 要 400：先看 400～500 之間有沒有，沒有就往輕找，找不到才往重


def test_the_google_font_urls_are_read_the_way_the_browser_reads_them():
    assert families('@import url("https://fonts.googleapis.com/css2?family=LXGW+WenKai+TC:wght@400;700&family=Noto+Serif+TC:wght@700&display=swap");') \
        == {LXGW: {400, 700}, NOTO: {700}}
    assert families('<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@400..700&amp;display=swap">') == {NOTO: {400, 500, 600, 700}}


def _game_css(page: str) -> list[str]:
    """遊戲頁載入的 /static/*.css（照 index.html 的順序；含功能包切出去的 mall.css）。"""
    return re.findall(r"""<link[^>]*rel=["']stylesheet["'][^>]*href=["']/static/([^"'?]+\.css)""", page)


def test_the_game_page_css_includes_the_feature_packages():
    """字重的檢查照頁面真的載入的那幾份讀：功能包切出去的樣式（FEATURES 的 web）也在裡面，不然它寫的字重沒人管。"""
    css = _game_css((WEB / "index.html").read_text(encoding="utf-8"))
    assert css[0] == "style.css" and "zhuan.css" in css
    assert [n for n in features_core.web_files() if n.endswith(".css")] and all(n in css for n in features_core.web_files() if n.endswith(".css"))


def test_the_game_asks_for_serif_at_400_and_700_so_both_have_to_be_loaded():
    """尺的另一頭：遊戲的 CSS 真的有寫 400 與 700 的襯線字（不是只有繼承），這一條沒了、下面幾條就空轉。"""
    page = (WEB / "index.html").read_text(encoding="utf-8")
    _, wanted = _check(page, _game_css(page), NOTO)
    assert 400 in wanted and 700 in wanted
    assert any(s.startswith(".mall-ask") for s in wanted[700])  # 商城購買確認的標題（web/mall.css）也讀到了
    assert any("leaf-sign" in s for s in wanted[400]) and any("shop-line" in s for s in wanted[400])  # 武學譜的簽、店面掌櫃的話


@pytest.mark.parametrize("family", [NOTO, LXGW])
def test_the_game_page_loads_every_weight_it_asks_for_and_no_more(family):
    page = (WEB / "index.html").read_text(encoding="utf-8")
    loaded, wanted = _check(page, _game_css(page), family)
    assert loaded, f"遊戲頁沒載 {family}"
    for weight in wanted:  # 沒有一個字重被配到別的粗細：400 就是 400（FB-575），700 就是 700
        landed = snap(weight, loaded)
        assert landed == weight or weight not in (400, 700), f"{family} 要 {weight}，載了 {sorted(loaded)}，配到 {landed}：{wanted[weight][:3]}"
    unused = {w for w in loaded if not any(snap(want, loaded) == w for want in wanted)}
    assert not unused, f"{family} 多載了沒人要的字重 {sorted(unused)}（手機流量）"


@pytest.mark.parametrize("family", [NOTO, LXGW])
def test_the_public_zhuan_page_loads_every_weight_it_asks_for_and_no_more(family):
    """公開的傳不用登入、多半是手機點進來：內文是霞鶩文楷（400、700），Noto Serif TC 只有印章 700；不能為了遊戲那邊的 400 多載。"""
    loaded, wanted = _check(_page_of_public_zhuan(), ["zhuan.css", "zhuan_html.CSS"], family)
    assert loaded, f"公開頁沒載 {family}"
    for weight in wanted:
        assert snap(weight, loaded) == weight or weight not in (400, 700), f"{family} 要 {weight}，載了 {sorted(loaded)}"
    unused = {w for w in loaded if not any(snap(want, loaded) == w for want in wanted)}
    assert not unused, f"{family} 多載了沒人要的字重 {sorted(unused)}（手機流量）"
