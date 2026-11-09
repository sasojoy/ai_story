"""CSP（帳號與客服第 213 批）：server.py 每個回應帶 `script-src 'self' https://challenges.cloudflare.com; object-src 'none'; base-uri 'none'`，
所以頁面上不准有 inline 的程式——`<script>` 一律帶 src、沒有 on*= 屬性、沒有 javascript: 連結、沒有 eval／new Function／字串的計時器。
這裡純 Python 掃字（不開 node），守住以後不長回來：web/ 的 js 與 index.html、伺服器生成的公開頁（列傳 /zhuan、戰記 /zhanji）。
標頭本身在 tests/server/test_server.py（test_every_response_carries_the_csp）。"""
from __future__ import annotations

import re
from pathlib import Path

from tianxia.core import features as features_core
from tianxia.features.tale import tale_html
from tianxia.features.zhuan import zhuan_html
from test_tale_page import VIEW

ROOT = Path(__file__).parents[2]
WEB = ROOT / "web"

# on*= 屬性：前面不是字、點、$、-（不抓 es.onerror = () =>、data-confirm=），後面接引號或反引號（樣板字串裡的屬性）
HANDLER = re.compile(r"""(?<![\w.$-])on[a-z]+\s*=\s*["'`]""")
FORBIDDEN = (
    ("javascript: 連結", re.compile(r"javascript:", re.I)),
    ("eval", re.compile(r"(?<![\w.$])eval\s*\(")),
    ("new Function", re.compile(r"new\s+Function\b")),
    ("字串的計時器", re.compile(r"""set(Timeout|Interval)\s*\(\s*["'`]""")),
)
SCRIPT_TAG = re.compile(r"<script\b[^>]*>", re.I)


def problems(text: str) -> list[str]:
    found = [f"inline handler：{m[0]}" for m in HANDLER.finditer(text)]
    found += [f"{why}：{m[0]}" for why, rx in FORBIDDEN for m in rx.finditer(text)]
    return found


def inline_scripts(html: str) -> list[str]:
    """不帶 src 的 <script>（inline 的程式）。"""
    return [tag for tag in SCRIPT_TAG.findall(html) if not re.search(r"\bsrc\s*=", tag, re.I)]


def test_web_has_no_inline_handlers():
    files = sorted(WEB.glob("*.js")) + sorted(WEB.glob("*.mjs")) + [WEB / "index.html"]
    bad = {p.name: got for p in files if (got := problems(p.read_text(encoding="utf-8")))}
    assert bad == {}
    index = (WEB / "index.html").read_text(encoding="utf-8")
    assert inline_scripts(index) == [] and inline_scripts(features_core.with_scripts(index)) == []


def test_server_pages_have_no_inline_code():
    row = {"name": "沈青衫", "season": 1, "text": "沈青衫者，汝南人也。\n\n評曰：善。"}
    pages = {
        "zhuan.page": zhuan_html.page(row, "三國", "https://x/zhuan/abc", "https://x/og.png"),
        "zhuan.page+extras": zhuan_html.page(row, "三國", "https://x/zhuan/abc", "https://x/og.png", {"art": "/static/a.webp", "seal": "印"}),
        "zhuan.missing": zhuan_html.missing(),
        "tale.page": tale_html.page(VIEW, url="https://x/zhanji/abc", image="https://x/c.webp", embedded=False),
        "tale.page.in": tale_html.page(VIEW, url="https://x/zhanji/abc", image="https://x/c.webp", embedded=True),
        "tale.missing": tale_html.missing(),
    }
    for name, html in pages.items():
        assert problems(html) == [], name
        assert inline_scripts(html) == [], name
        for src in re.findall(r"""<script\b[^>]*\bsrc=["']/static/([^"'?#]+)""", html):
            assert (WEB / src).is_file(), (name, src)
