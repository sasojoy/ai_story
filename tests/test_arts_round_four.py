"""arts-polish-2 第四輪（整合審查 review-ap3 與控制者走查之後的小修）。
CSS 沒有版面可量（沒有瀏覽器）：用讀樣式表的測試把規則釘住；畫面上的行為用 node 切出 app.js 的函式、或整支 app.js 放進假瀏覽器跑。"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CSS = (ROOT / "web" / "style.css").read_text(encoding="utf-8").replace("\r\n", "\n")


def _rules(css: str):
    """（選擇器, 內容）的平的清單（含 @media 裡面的；@keyframes 與 @media 的外殼不算規則）。夠這裡的幾條規則用，不是完整的 CSS 剖析器。"""
    flat = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    for m in re.finditer(r"([^{}@]+?)\{([^{}]*)\}", flat):
        out.append((" ".join(m.group(1).split()), m.group(2)))
    return out


def _decl(body: str, prop: str):
    m = re.search(rf"(?:^|;|\s){re.escape(prop)}\s*:\s*([^;]+)", body)
    return m.group(1).strip() if m else None


def _layers(shadow: str) -> list[str]:
    """box-shadow 的每一層（逗號隔開，但括號裡的逗號——color-mix(in srgb, …)——不算）。"""
    parts, depth, cur = [], 0, ""
    for ch in shadow:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    return parts + [cur.strip()]


def test_the_dead_filter_row_rule_is_gone():
    """修練頁的庫改用卷軸卡自己的篩選（.lib-filter）之後，.filter-row 沒有任何地方用到（review-ap3 M4）。"""
    assert not any(".filter-row" in sel for sel, _ in _rules(CSS))
    assert ".filter-row" not in (ROOT / "web" / "app.js").read_text(encoding="utf-8")


# ── M1：灰掉的熔煉寫原因，不多佔一排 ──────────────────────────────


def test_the_melt_reason_shares_the_row_with_the_two_links_and_wraps_inside_itself():
    """寫在 .more 左邊的空位：flex 1 1 0（吃剩下的寬度、基準是 0，不會把整排擠到下一行）、min-width 0（字太長在自己裡面折行），
    所以那一排不會比兩個 40px 高的連結更高。"""
    rule = next((body for sel, body in _rules(CSS) if sel == ".more .why"), None)
    assert rule is not None
    assert _decl(rule, "flex") == "1 1 0" and _decl(rule, "min-width") == "0" and _decl(rule, "align-self") == "center"


# ── AP3-W1：功法庫收著的那一列發光，要看得見 ──────────────────────────


def test_a_glowing_library_row_gets_an_inset_glow_because_the_list_clips_the_outer_one():
    """.lib 有 overflow: hidden（joy 的卷軸卡，不能拿掉），列又從左邊貼到右邊，往外長的 box-shadow 整個被裁掉——序章的改練、熔煉那一列
    （「在下面 ↓」捲過去的那一列）看不到任何亮光（控制者 375×812 走查）。往裡長的陰影不會被裁。"""
    lib = next(body for sel, body in _rules(CSS) if sel == ".lib" and "overflow" in body)
    assert _decl(lib, "overflow") == "hidden"  # joy 的版面照舊
    rule = next((body for sel, body in _rules(CSS) if sel == ".lib button.libr.glow"), None)
    assert rule is not None, "沒有 .lib button.libr.glow 的規則"
    shadow = _decl(rule, "box-shadow")
    assert shadow and len(_layers(shadow)) == 2 and all(part.startswith("inset") for part in _layers(shadow)), shadow
    assert "tx-glow-in" in (_decl(rule, "animation-name") or "")  # 有自己的呼吸動畫（裡面也是 inset）


def test_the_inset_breathing_keyframes_stay_inside_the_row():
    frames = re.search(r"@keyframes tx-glow-in \{(.*?)\n\}", CSS, re.S)
    assert frames is not None, "沒有 tx-glow-in 的 @keyframes"
    shadows = re.findall(r"box-shadow:\s*([^;}]+)", frames.group(1))
    assert shadows and all(part.startswith("inset") for s in shadows for part in _layers(s))


def test_reduced_motion_keeps_the_inset_glow_still_instead_of_breathing():
    """減少動態：只留靜態的金邊。.glow 的 animation: none 比 .lib button.libr.glow 的 animation-name 弱（選擇器少），所以那一列要自己關。"""
    blocks = re.findall(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}", CSS, re.S)
    media = next((b for b in blocks if ".glow" in b), None)  # 樣式表裡有兩個減少動態的區塊：找發光的那一個
    assert media is not None
    rules = _rules("{" + media)  # 外殼拿掉，剩裡面的規則
    off = [sel for sel, body in rules if _decl(body, "animation") == "none"]
    assert any(".lib button.libr.glow" in sel for sel in off), off  # 那一列的動畫關掉
    assert any(sel.strip() == ".glow, .lit" or sel.strip() == ".glow" for sel in off)  # 其他發光的鈕照舊關


def test_only_the_collapsed_row_is_inset_not_the_buttons_inside_an_opened_card():
    """卡裡的鈕（改練、修練、熔煉）有邊距，往外的金邊本來就看得見：規則只管 button.libr，不要把整個 .lib 底下的 .glow 都改成往裡。"""
    selectors = [sel for sel, body in _rules(CSS) if "inset" in (_decl(body, "box-shadow") or "")]
    assert ".lib button.libr.glow" in selectors
    assert not any(sel in (".lib .glow", ".glow") for sel in selectors)
