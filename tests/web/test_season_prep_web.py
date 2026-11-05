"""開季準備卡（web/app.js 的 prepHtml）與江湖頁頂上的提示條（web/main.js 的 jhHintsHtml）：企劃者 2026-11-05
「識海入口藏在現在那個位子 一般玩家怎麼可能知道 至少需要導引」「加點是隨時都可以調整？」「舊玩家根本不會知道要去哪邊點點數」。

- 準備卡：main.prep 的 step 是 growth（五套預設＋自己配，先點一張再按「定下來」）或 feature（識海的候選：封進識海、這一季不帶）；
  兩步時畫步驟；沒有關掉的鈕。
- 狀態列的成長配比：挑了只寫現在怎麼長（一季只挑一次），沒有改的鈕。
- 提示條：五項屬性的季有送點時「有 N 點屬性可配」，攤開是五顆＋鈕；識海封著一份時寫解封還差什麼，解得開時發光；舊的季一顆都不畫。"""
from __future__ import annotations

import re

import pytest

import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = r"""
const cut = (from, to) => { const a = src.indexOf(from), b = src.indexOf(to, a); if (a < 0 || b < a) throw new Error("找不到 " + from); return src.slice(a, b); };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const lgNum = (n) => String(n);
const S = input.S;
eval(cut("\n  // 成長配比（五項屬性的季才有 s.growth）", "\n  function statUsesHtml") + cut("\n  function jhHintsHtml", "\n  function pageJianghu")
  + "\nglobalThis.__P = { prepHtml, growthHtml, jhHintsHtml, lilianHtml };");
const m = S.main;
finish(input.what === "prep" ? __P.prepHtml(m.prep) : input.what === "growth" ? __P.growthHtml(m.status.growth)
  : input.what === "lilian" ? __P.lilianHtml(m.status.lilian) : __P.jhHintsHtml(m));
"""

KEYS = [["str", "武力"], ["lead", "統御"], ["int", "悟性"], ["spd", "身法"], ["cha", "魅力"]]
PRESETS = [("warrior", "武將", [4, 3, 1, 1, 1]), ("ranger", "遊俠", [2, 1, 1, 4, 2]), ("balanced", "均衡", [2, 2, 2, 2, 2])]


def _growth(chosen=None):
    return {
        "chosen": chosen, "keys": KEYS, "per_level": 10, "custom_min": 1, "custom_max": 4, "event_cap": 60,
        "presets": [{"key": k, "name": n, "split": [[name, v] for (_, name), v in zip(KEYS, split)]} for k, n, split in PRESETS],
        "now": [[name, 2] for _, name in KEYS],
    }


def _shihai(offers=(), sealed=None, need_ok=(False, False, False), held=False):
    return {"shihai": {
        "offers": [{"name": n, "attribute": "快", "season": 1} for n in offers],
        "sealed": None if sealed is None else {"name": sealed, "attribute": "快", "season": 1, "names": []},
        "need": [{"key": k, "text": t, "ok": ok, "now": ""} for (k, t), ok in zip((("time", "開季滿一天"), ("level", "15 級以上"), ("xinde", "心得 100")), need_ok)],
        "held": held,
    }}


def run(main, what, **state):
    return webharness.run(DRIVER, {"S": {"main": main, **state}, "what": what})


def text(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


def test_the_growth_step_lists_the_presets_and_waits_for_a_pick():
    main = {"prep": {"step": "growth", "steps": ["growth", "feature"]}, "status": {"growth": _growth()}}
    html = run(main, "prep")
    assert 'aria-modal="true"' in html and "close" not in html  # 蓋住整頁、沒有關掉的鈕
    assert "成長配比" in text(html) and "識海" in text(html) and "這一季只挑一次" in text(html)
    assert [m for m in re.findall(r'data-act="prep-pick" data-preset="(\w+)"', html)] == ["warrior", "ranger", "balanced", "custom"]
    assert 'data-act="prep-growth"' not in html  # 還沒點：沒有「定下來」
    picked = run(main, "prep", prepPick="ranger")
    assert 'data-act="prep-growth"' in picked and "照「遊俠」長" in text(picked)
    custom = run(main, "prep", prepPick="custom", growthDraft={"str": 2, "lead": 2, "int": 2, "spd": 2, "cha": 2})
    assert 'data-act="growth-save"' in custom and 'data-act="prep-growth"' not in custom
    assert "江湖歷練每一季最多長 60 點，滿了化為心得" in text(html)
    alone = run({"prep": {"step": "growth", "steps": ["growth"]}, "status": {"growth": _growth()}}, "prep")
    assert "prep-steps" not in alone  # 只有一步不畫步驟


def test_the_shihai_step_seals_one_or_skips():
    main = {"prep": {"step": "feature", "steps": ["growth", "feature"]}, "status": {"growth": _growth("ranger")},
            "legacy": _shihai(offers=("寒江獨照", "斷水流雲"))}
    html = run(main, "prep")
    assert 'data-id="legacy:seal:0"' in html and 'data-id="legacy:seal:1"' in html and 'data-id="legacy:skip"' in html
    assert "開季滿一天、15 級以上、心得 100" in text(html) and "✓" in html  # 第一步打勾


def test_the_status_bar_only_shows_the_chosen_growth():
    html = run({"status": {"growth": _growth("ranger")}}, "growth")
    assert "這一季的成長：遊俠" in text(html) and "data-act" not in html
    custom = run({"status": {"growth": {**_growth("custom")}}}, "growth")
    assert "自己配" in text(custom) and "data-act" not in custom


def test_the_hint_bar_shows_points_and_the_shihai():
    status = {"growth": _growth("ranger"), "stat_points": 10, "attrs": [[n, 50, k] for k, n in KEYS]}
    shut = run({"status": status}, "hints")
    assert "有 10 點屬性可配" in text(shut) and 'data-act="allocate"' not in shut
    opened = run({"status": status}, "hints", allocOpen=True)
    assert re.findall(r'data-act="allocate" data-stat="(\w+)"', opened) == [k for k, _ in KEYS]
    waiting = run({"status": {**status, "stat_points": 0}, "legacy": _shihai(sealed="寒江獨照", need_ok=(True, False, False))}, "hints")
    assert "解封還差：15 級以上、心得 100" in text(waiting) and "ready" not in waiting and 'data-v="shihai"' in waiting
    ready = run({"status": {**status, "stat_points": 0}, "legacy": _shihai(sealed="寒江獨照", need_ok=(True, True, True))}, "hints")
    assert "可以解封了" in text(ready) and "jh-hint ready" in ready


def test_the_old_season_draws_no_hint():
    assert run({"status": {"stat_points": 3, "attrs": []}}, "hints") == ""


def test_the_lilian_line_counts_up_to_the_cap():
    half = run({"status": {"lilian": {"have": 14, "cap": 60}}}, "lilian")
    assert "歷練 14／60" in text(half) and "--w:23%" in half and "full" not in half
    full = run({"status": {"lilian": {"have": 60, "cap": 60}}}, "lilian")
    assert "已到火候" in text(full) and "lilian full" in full and "刷" not in text(full)
