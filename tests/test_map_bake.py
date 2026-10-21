"""輿圖的底圖烤成一張圖（Joy 2026-10-18「輿圖滑動的時候還是很卡」）：烤進去的是不會變的山水（山頭、樹、河、絹紋、四角壓暗），
會變的照舊是向量：最前面那一塊底色、大區（drawMarks 照這一層換 fill、收州界）、字、記號那一層。
輿圖第三版第 4 批起路（<g class="tx-roads">）也留成向量：區圖照 CSS 把三種路換成一種淡實線（輿圖簡化設計 5.2），天下圖照舊的樣子。"""
from __future__ import annotations

import webharness

DRIVER = r"""
eval(fn("bakeable"));
const el = (tag, o = {}) => ({ tagName: tag, id: o.id || "", attrs: o.attrs || {}, hasText: !!o.text,
  hasAttribute(k) { return k in this.attrs; }, getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
  querySelector(q) { return q === "text" && this.hasText ? {} : null; } });
const kids = [
  el("defs"), el("rect", { attrs: { fill: "#e9e2cc" } }), el("rect", { attrs: { filter: "url(#silk)" } }),
  el("path", { attrs: { "data-region": "luoyang" } }), el("path", { attrs: { "data-region": "nanyang" } }),
  el("path"), el("polyline"), el("circle"), el("text"), el("g", { text: true }), el("g"), el("image"), el("g", { id: "mk" }),
  el("g", { attrs: { class: "tx-roads" } }),
];
const svg = { children: kids, querySelector: (q) => (q === ":scope > rect" ? kids[1] : null) };
finish(bakeable(svg).map((k) => kids.indexOf(k)));
"""


def test_only_the_static_scenery_is_baked():
    # 絹紋那一塊、山水、沒有字的 g 烤掉；defs、底色、兩塊大區、字、有字的 g、已經烤好的圖、記號那一層、路那一組留著
    assert webharness.run(DRIVER, {}) == [2, 5, 6, 7, 10]
