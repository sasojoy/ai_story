"""擂台動畫（web/arena_anim.js；企劃者 2026-10-31「擂台也可以把走一趟的角色拿出來用，有攻擊跟受擊甚至是陣亡的動畫」）：
每一回合照兩邊氣血、氣勢的變化排誰出招、誰受擊或閃開；收場照結果排倒地、跪地。畫布在 node 裡畫不出來，這裡只驗排出來的幕。"""
from __future__ import annotations

import pytest
import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node")

DRIVER = r"""
const block = (name) => { const a = src.indexOf(`\n  const ${name} = `); return a < 0 ? konst(name) : src.slice(a, src.indexOf(";\n", a) + 2); };
const code = ["RING_ARMS", "RING_SHEETS"].map(block).join("\n")
  + "\nconst RA = { looks: { me: '', foe: '' } };\n"
  + "\n" + ["ringArms", "ringAtk", "ringAct"].map(konst).join("\n") + fn("ringStrike") + fn("ringExchange") + fn("ringFinale");
const H = new Function(code + "\nreturn { RA, ringExchange, ringFinale };")();
H.RA.looks = input.looks;
const brief = (beats) => beats.map((b) => ({ lunge: b.lunge, me: b.me && b.me.sheet, foe: b.foe && b.foe.sheet, keep: !!((b.me && b.me.keep) || (b.foe && b.foe.keep)) }));
finish({ ex: input.ex.map(([a, b]) => brief(H.ringExchange(a, b))), fin: input.fin.map(([t, low]) => brief(H.ringFinale(t, low))) });
"""

A = {"me": 100, "foe": 100, "edge": 50}


def _run(ex=(), fin=(), looks=None):
    return webharness.run(DRIVER, {"ex": list(ex), "fin": list(fin), "looks": looks or {"me": "槍", "foe": ""}})


def test_whoever_loses_blood_is_the_one_hit():
    out = _run(ex=[(A, dict(A, foe=80)), (A, dict(A, me=85)), (A, dict(A, me=90, foe=70))])["ex"]
    assert out[0] == [{"lunge": "me", "me": "hero_atk_pole", "foe": "hero_bare_hit", "keep": False}]  # 拿槍的出長兵那一招
    assert out[1] == [{"lunge": "foe", "me": "hero_bare_hit", "foe": "hero_atk_fist", "keep": False}]  # 空手的出拳腳
    assert [b["lunge"] for b in out[2]] == ["foe", "me"]  # 兩邊都掛彩：先演傷得輕的那一下


def test_no_blood_means_a_dodge_toward_the_edge():
    out = _run(ex=[(A, dict(A, edge=58)), (A, dict(A, edge=40)), (A, A)])["ex"]
    assert out[0] == [{"lunge": "me", "me": "hero_atk_pole", "foe": "hero_bare_dodge", "keep": False}]
    assert out[1][0]["me"] == "hero_bare_dodge" and out[2] == []


def test_the_finale_drops_or_kneels_the_loser():
    out = _run(fin=[("大勝", False), ("險勝", False), ("落敗", True), ("落敗", False), ("僵持", False)], looks={"me": "劍", "foe": "弓弩"})["fin"]
    assert out[0] == [{"lunge": "me", "me": "hero_atk_slash", "foe": "hero_bare_fall", "keep": True}]
    assert out[1][0]["foe"] == "hero_bare_kneel"
    assert out[2] == [{"lunge": "foe", "me": "hero_bare_fall", "foe": "hero_atk_shoot", "keep": True}]  # 你氣血見底：倒地
    assert out[3][0]["me"] == "hero_bare_kneel"
    assert [b["keep"] for b in out[4]] == [False, False]


def test_every_sheet_has_a_hand_for_every_frame():
    """每一張圖的每一格都標了手的位置（少一格，兵器就會在那一格不見）。"""
    out = webharness.run(r"""
const block = (name) => { const a = src.indexOf(`\n  const ${name} = `); return a < 0 ? konst(name) : src.slice(a, src.indexOf(";\n", a) + 2); };
const code = ["RING_SHEETS", "RING_HAND"].map(block).join("\n");
const H = new Function(code + "\nreturn { RING_SHEETS, RING_HAND };")();
finish(Object.keys(H.RING_SHEETS).map((k) => [k, H.RING_SHEETS[k], (H.RING_HAND[k] || []).length]));
""", {})
    assert all(n == hands for _, n, hands in out), out
