"""登入頁的宣傳影片（企劃者 2026-10-12）：靜音、自動播放、循環、playsinline，先顯示首格；偏好減少動態效果的人只看首格；
開聲音那一顆切靜音。只切 app.js 裡那幾段來跑，沒有 node 就略過。"""
from __future__ import annotations

from pathlib import Path

import pytest

import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

WEB = Path(__file__).resolve().parent.parent / "web"

DRIVER = r"""
const parts = [konst("PROMO_POSTER"), "const window = { matchMedia: () => ({ matches: input.calm }) };",
  konst("promoCalm"), fn("promoHtml"), fn("promoSound"), "return { promoHtml, promoSound };"];
const H = new Function(parts.join("\n"))();
const html = H.promoHtml();
// 開聲音：假的影片與按鈕
const v = { muted: true, paused: true, played: 0, play() { this.played++; this.paused = false; return Promise.resolve(); } };
const attrs = {};
const btn = { closest: () => ({ querySelector: () => v }), setAttribute: (k, val) => { attrs[k] = val; }, textContent: "" };
H.promoSound(btn);
const on = { muted: v.muted, played: v.played, pressed: attrs["aria-pressed"], label: btn.textContent };
H.promoSound(btn);
finish({ html, on, off: { muted: v.muted, pressed: attrs["aria-pressed"], label: btn.textContent } });
"""


def test_the_promo_plays_muted_and_the_sound_button_toggles():
    out = webharness.run(DRIVER, {"calm": False})
    html = out["html"]
    for attr in ("muted", "autoplay", "loop", "playsinline", 'poster="/static/promo-poster.jpg"', 'src="/static/promo.mp4"'):
        assert attr in html
    assert out["on"] == {"muted": False, "played": 1, "pressed": "true", "label": "🔊 關聲音"}
    assert out["off"] == {"muted": True, "pressed": "false", "label": "🔇 開聲音"}


def test_reduced_motion_only_shows_the_poster():
    html = webharness.run(DRIVER, {"calm": True})["html"]
    assert "<video" not in html and 'src="/static/promo-poster.jpg"' in html and "promo-sound" not in html


def test_the_web_copy_is_small():
    assert (WEB / "promo.mp4").stat().st_size < 1_200_000
    assert (WEB / "promo-poster.jpg").stat().st_size < 120_000
