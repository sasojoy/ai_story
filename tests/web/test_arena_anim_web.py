"""擂台動畫（web/arena_anim.js；企劃者 2026-10-31「擂台也可以把走一趟的角色拿出來用，有攻擊跟受擊甚至是陣亡的動畫」）：
每一回合照兩邊出的招排動作（強攻、固守、奇襲各有一套），誰挨打照氣血；不知道出了哪一招照氣血、氣勢的變化排；收場照結果排倒地、跪地。畫布在 node 裡畫不出來，這裡只驗排出來的幕。"""
from __future__ import annotations

import pytest
import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node")

DRIVER = r"""
const block = (name) => { const a = src.indexOf(`\n  const ${name} = `); return a < 0 ? konst(name) : src.slice(a, src.indexOf(";\n", a) + 2); };
const code = ["RING_ARMS", "RING_SHEETS", "RING_PICKS", "RING_BEATS"].map(block).join("\n")
  + "\nconst RA = { looks: { me: '', foe: '' } };\n"
  + "\n" + ["ringArms", "ringAtk", "ringAct", "RING_HIT"].map(konst).join("\n")
  + fn("ringStrike") + fn("ringPlan") + fn("ringPicked") + fn("ringExchange") + fn("ringFinale");
const H = new Function(code + "\nreturn { RA, ringExchange, ringFinale };")();
H.RA.looks = input.looks;
// 每一幕寫成：誰往前衝（有正的 lunge 的那一邊）、兩邊依序演哪幾張、有沒有停在最後一格
const seq = (acts) => [].concat(acts || []).slice().sort((x, y) => x.at - y.at).map((a) => a.sheet);
const brief = (beats) => beats.map((b) => ({
  lunge: ["me", "foe"].filter((k) => [].concat(b[k] || []).some((a) => (a.lunge || 0) > 0)).join(","),
  me: seq(b.me), foe: seq(b.foe), keep: ["me", "foe"].some((k) => [].concat(b[k] || []).some((a) => a.keep)),
  fx: ["me", "foe"].filter((k) => [].concat(b[k] || []).some((a) => a.fx)).join(","),
}));
const plain = (beats) => beats.map(({ fx, ...rest }) => (input.fx ? { fx, ...rest } : rest));
finish({ ex: input.ex.map(([a, b, pick, burst]) => plain(brief(H.ringExchange(a, b, pick, burst)))),
         fin: input.fin.map(([t, low, pick, burst]) => plain(brief(H.ringFinale(t, low, pick, burst)))) });
"""

A = {"me": 100, "foe": 100, "edge": 50}


def _run(ex=(), fin=(), looks=None, fx=False):
    return webharness.run(DRIVER, {"ex": list(ex), "fin": list(fin), "looks": looks or {"me": "槍", "foe": ""}, "fx": fx})


def test_whoever_loses_blood_is_the_one_hit():
    """不知道出了哪一招（放手一搏、舊的一場）：照誰掉了血。"""
    out = _run(ex=[(A, dict(A, foe=80)), (A, dict(A, me=85)), (A, dict(A, me=90, foe=70)), (A, dict(A, foe=80), ["搏", ""])])["ex"]
    assert out[0] == [{"lunge": "me", "me": ["hero_atk_pole"], "foe": ["hero_bare_hit"], "keep": False}]  # 拿槍的出長兵那一招
    assert out[1] == [{"lunge": "foe", "me": ["hero_bare_hit"], "foe": ["hero_atk_fist"], "keep": False}]  # 空手的出拳腳
    assert [b["lunge"] for b in out[2]] == ["foe", "me"]  # 兩邊都掛彩：先演傷得輕的那一下
    assert out[3] == out[0]


def test_no_blood_means_a_dodge_toward_the_edge():
    out = _run(ex=[(A, dict(A, edge=58)), (A, dict(A, edge=40)), (A, A)])["ex"]
    assert out[0] == [{"lunge": "me", "me": ["hero_atk_pole"], "foe": ["hero_bare_dodge"], "keep": False}]
    assert out[1][0]["me"] == ["hero_bare_dodge"] and out[2] == []


def test_each_move_has_its_own_moves():
    """照出的招演（Joy 2026-10-31）：強攻衝上去劈；固守架住，打中人的是架開之後回的那一下；奇襲先閃再補；挨打的那一邊最後受擊。"""
    out = _run(ex=[
        (A, dict(A, me=85), ["強攻", "固守"]),  # 固守剋強攻：他架住再回一下，你挨打
        (A, dict(A, foe=85), ["強攻", "奇襲"]),  # 強攻剋奇襲
        (A, dict(A, me=85), ["固守", "奇襲"]),  # 奇襲剋固守
        (A, dict(A, me=90, foe=90), ["強攻", "強攻"]),  # 對拼：兩邊都挨
    ])["ex"]
    assert out[0] == [{"lunge": "me,foe", "me": ["hero_atk_pole", "hero_bare_hit"], "foe": ["hero_bare_block", "hero_atk_fist"], "keep": False}]
    assert out[1] == [{"lunge": "me", "me": ["hero_atk_pole"], "foe": ["hero_bare_dodge", "hero_bare_hit"], "keep": False}]  # 閃到一半被劈中
    assert out[2] == [{"lunge": "foe", "me": ["hero_bare_block", "hero_bare_hit"], "foe": ["hero_bare_dodge", "hero_atk_fist"], "keep": False}]
    assert out[3][0]["me"] == ["hero_atk_pole", "hero_bare_hit"] and out[3][0]["foe"] == ["hero_atk_fist", "hero_bare_hit"]


def test_the_finale_drops_or_kneels_the_loser():
    out = _run(fin=[("大勝", False), ("險勝", False, ["奇襲", "強攻"]), ("落敗", True), ("落敗", False), ("僵持", False)],
               looks={"me": "劍", "foe": "弓弩"})["fin"]
    assert out[0] == [{"lunge": "me", "me": ["hero_atk_slash"], "foe": ["hero_bare_fall"], "keep": True}]
    assert out[1][0]["foe"] == ["hero_bare_kneel"] and out[1][0]["me"] == ["hero_bare_dodge", "hero_atk_slash"]  # 贏的照最後出的招
    assert out[2] == [{"lunge": "foe", "me": ["hero_bare_fall"], "foe": ["hero_atk_shoot"], "keep": True}]  # 你氣血見底：倒地
    assert out[3][0]["me"] == ["hero_bare_kneel"]
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


def test_only_the_countered_side_is_hit():
    """Joy 2026-11-01：剋人的那一邊不受擊（就算這一回合也掉了血）；出一樣的兩邊都受擊。"""
    out = _run(ex=[
        (A, dict(A, me=95, foe=80), ["強攻", "奇襲"]),  # 你剋他：你也掉了一點血，照樣不演受擊
        (A, dict(A, me=80, foe=95), ["奇襲", "強攻"]),  # 他剋你
        (A, A, ["固守", "固守"]),  # 出一樣：兩邊都受擊
    ])["ex"]
    assert "hero_bare_hit" not in out[0][0]["me"] and out[0][0]["foe"][-1] == "hero_bare_hit"
    assert out[1][0]["me"][-1] == "hero_bare_hit" and "hero_bare_hit" not in out[1][0]["foe"]
    assert out[2][0]["me"][-1] == "hero_bare_hit" and out[2][0]["foe"][-1] == "hero_bare_hit"


def test_the_move_effect_only_shows_when_its_art_fires():
    """Joy 2026-11-01「我以為是招式發動的時候才會有」：光效只疊在伺服器說那一門的戰法發動了的那一回合（bursts），
    平常出手不疊；發動的那一下對手受擊（固守也架開之後回一下）。"""
    out = _run(ex=[
        (A, dict(A, foe=85), ["強攻", "奇襲"]),  # 沒發動：平常一劈，不疊光效
        (A, dict(A, foe=85), ["強攻", "奇襲"], [1, 0]),  # 發動了：出手那一下疊光效
        (A, dict(A, foe=90), ["固守", "固守"], [1, 0]),  # 固守發動：架開之後回一下
        (A, dict(A, me=90), ["強攻", "固守"], [1, 0]),  # 被剋了照樣發動：他也受擊
        (A, dict(A, foe=80), ["搏", ""], [1, 0]),  # 放手一搏那一回合發動
        (A, A, ["搏", ""], [0, 1]),  # 分身發動：沒掉血也出手、你受擊
    ], fin=[("大勝", False, ["強攻", "奇襲"], [1, 0]), ("大勝", False, ["強攻", "奇襲"])], fx=True)
    ex, fin = out["ex"], out["fin"]
    assert ex[0][0]["fx"] == "" and ex[1][0]["fx"] == "me"
    assert ex[2][0]["fx"] == "me" and ex[2][0]["me"] == ["hero_bare_block", "hero_atk_pole", "hero_bare_hit"]
    assert ex[3][0]["fx"] == "me" and ex[3][0]["foe"][-1] == "hero_bare_hit"
    assert ex[4][0]["fx"] == "me" and ex[5] == [{"lunge": "foe", "me": ["hero_bare_hit"], "foe": ["hero_atk_fist"], "keep": False, "fx": "foe"}]
    assert fin[0][0]["fx"] == "me" and fin[1][0]["fx"] == ""
