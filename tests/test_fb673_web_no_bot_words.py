"""FB-673：`web/` 底下送給瀏覽器的檔（js、css、html）不准出現「假人」「機器人」「bot」。

設計是任何畫面都不透露誰是假人（伺服器假人設計）。渲染出來的頁面與 /api 回應早有測試守著，
但 `app.js`、`style.css` 整支隨檔送到每個玩家的瀏覽器（`/static/…`），註解與字串看原始碼的人都讀得到：
練功入口（FB-670）新加的一句註解寫了「假人、整季機器人不受影響」，舊的一句寫了「真人假人是同一份名單」。
要寫給自己看的說明放 docs 或 Python 端，網頁檔裡用中性的字（「每個角色」「名單」「模擬腳本」）。

白名單（真的有合理用途的英文字詞）：
- `bottom`：DOM 的 `getBoundingClientRect().bottom`、CSS 的 `bottom` / `padding-bottom` / `margin-bottom`。
- `both`：CSS 的 `animation-fill-mode: both`、`clear: both`、`scrollbar-gutter: stable both-edges`。
"""

from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"

# 送給瀏覽器的文字檔；圖片、影片不掃。
TEXT_SUFFIXES = {".js", ".css", ".html", ".htm", ".svg", ".json", ".txt", ".map", ".xml", ".webmanifest"}

# 「bot」不分大小寫，只放行 bottom 與 both 這兩個字（見檔頭）。
BOT_WORD = re.compile(r"bot(?!tom|h\b)", re.IGNORECASE)
FORBIDDEN = (re.compile("假人"), re.compile("機器人"), BOT_WORD)


def leaks(text: str) -> list[tuple[int, str]]:
    """(行號, 那一行裡抓到的字)；一行抓到幾個就列幾個。"""
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        for pattern in FORBIDDEN:
            for hit in pattern.finditer(line):
                found.append((number, line[max(0, hit.start() - 8) : hit.end() + 8]))
    return found


def web_text_files() -> list[Path]:
    return sorted(p for p in WEB.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES)


def test_the_scan_sees_the_files_the_browser_gets():
    names = {p.name for p in web_text_files()}
    assert {"app.js", "style.css", "index.html"} <= names
    for name in ("app.js", "style.css", "index.html"):
        assert len((WEB / name).read_text(encoding="utf-8")) > 1000


def test_the_scan_catches_the_words_and_lets_the_css_words_through():
    # 掃描器本身要抓得到（不然「一個都沒有」可能只是掃不到）。
    assert leaks("// 假人、整季機器人不受影響")
    assert leaks("const isBot = true;")
    assert leaks("// 真人假人是同一份名單")
    assert leaks("function robotNames() {}")
    assert leaks("// BOT cap")
    # 放行的：bottom、both。
    assert not leaks("const under = bar.getBoundingClientRect().bottom + 8;")
    assert not leaks("padding-bottom: var(--bottom); animation: x 3s ease-out both;")
    assert not leaks("scrollbar-gutter: stable both-edges; clear: both; Bottom")
    # both / bottom 以外的 bot 開頭字不放行。
    assert leaks("bother")


def test_no_web_file_names_the_dummy_players():
    problems = []
    for path in web_text_files():
        text = path.read_text(encoding="utf-8")
        for number, snippet in leaks(text):
            problems.append(f"{path.relative_to(WEB.parent).as_posix()}:{number}: …{snippet}…")
    assert not problems, "web/ 的檔隨檔送到每個玩家的瀏覽器，不能出現假人、機器人、bot：\n" + "\n".join(problems)
