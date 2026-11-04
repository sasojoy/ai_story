"""五項屬性的量表（屬性與跨季架構 v2 第十一節第 1、2、3、5 條；第 4 條跨季看 measure_legacy.py）。只量、不改數字。

玩家照 measure_difficulty 那一套練功的走法（solo，舊的季練出武學與裝備），練到 --levels 各停一下；同一份身家換成
「舊的四項」與五套配比（五項屬性的季、蓋了章）各算一次（不擲亂數以外的東西，--runs 次模擬）：
- 打得動嗎：開放地點的遊歷對手（照難度換成的等級分兩群：不高過自己、高過自己十級以內）與大勢人物本人（開季聲威）的贏面
  （大勝＋險勝；第五項的對抗式照真的打那一條，team.facing）；
- 過得了嗎：正式內容每一個事件檢定的成功率平均，與「這一套最輕的那一項」的檢定平均（挑輕那一項的人不能整季過不了）；
- 勝算準嗎：遊歷對手的勝算字跟同一把尺模擬出來的贏面。

用法：python scripts/measure_attrs_v2.py --seeds 1 [--levels 10 20 30] [--profile season21] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import measure_difficulty as md  # noqa: E402  它開暫存資料庫、包 stdout

from tianxia import attrset, rules, team  # noqa: E402

UPS: list[float] = []
REGIMES = ("v1", "warrior", "strategist", "ranger", "envoy", "balanced")


def _switch(game, regime: str) -> None:
    c, s = game.content, game.state
    on = regime != "v1"
    c.config.attributes.v2.enabled = on
    s.world.attrs_v2 = on
    s.player.growth_preset = regime if on else None


def _rate(game, squad) -> float:
    s, c, w = game.state, game.content, game.world
    with team.facing(s, c, squad):
        power = team.power_vs(s, c, w, squad, fresh=True)
        return md.win_rate(power, squad.difficulty, md.mods_of(game))


def _odds(game, squad) -> str:
    s, c, w = game.state, game.content, game.world
    return team.estimate(s, c, w, squad.id, difficulty=squad.difficulty)


def snapshot(game) -> dict:
    s, c = game.state, game.content
    level = s.player.member.level
    train = sorted({sid for loc in c.locations.values() for sid in loc.enemies if sid in c.squads})
    figs = [c.squads[f.squad].model_copy(update={"difficulty": md.figures_base(game, fid)}) for fid, f in c.figures.items()]
    checks = md.checks(c)
    out = {"level": level}
    for regime in REGIMES:
        _switch(game, regime)
        low, high, odds = [], [], {}
        for sid in train:
            sq = c.squads[sid]
            lv = attrset.foe_level(c, sq.difficulty)
            if lv > level + 10:
                continue
            r = _rate(game, sq)
            (low if lv <= level else high).append(r)
            odds.setdefault(_odds(game, sq), []).append(r)
        fig_rates = [_rate(game, sq) for sq in figs]
        chances = [(ch.stat, rules.check_chance(ch, s, c, game.world)) for ch in checks]
        row = {
            "low": statistics.mean(low) if low else None, "n_low": len(low),
            "high": statistics.mean(high) if high else None, "n_high": len(high),
            "figs": statistics.mean(fig_rates), "figs_50": sum(r >= 0.5 for r in fig_rates) / len(fig_rates),
            "checks": statistics.mean(v for _, v in chances),
            "odds": {k: (statistics.mean(v), len(v)) for k, v in odds.items()},
        }
        if regime != "v1":
            split = attrset.split(s, c)
            weakest = min(split, key=split.get)
            mine = [v for st, v in chances if attrset.key_of(c, st) == weakest]
            row["weak_key"], row["weak"] = weakest, statistics.mean(mine) if mine else None
            rates = c.config.attributes.v2.grade_rates
            keep = dict(rates)
            for up in UPS:  # 每一級的基本成功率一起加 up（--up），看整體與最輕那一項各升多少
                rates.update({k: v + up for k, v in keep.items()})
                again = [(ch.stat, rules.check_chance(ch, s, c, game.world)) for ch in checks]
                row.setdefault("up", {})[up] = (statistics.mean(v for _, v in again),
                                                statistics.mean(v for st, v in again if attrset.key_of(c, st) == weakest))
            rates.clear()
            rates.update(keep)
            row["values"] = attrset.values(s, c)
        out[regime] = row
    _switch(game, "v1")
    return out


def pct(x) -> str:
    return "—" if x is None else f"{x:.0%}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1])
    ap.add_argument("--levels", type=int, nargs="+", default=[10, 20, 30])
    ap.add_argument("--profile", default="season21")
    ap.add_argument("--runs", type=int, default=600)
    ap.add_argument("--up", type=float, nargs="*", default=[], help="檢定每一級的基本成功率另外加這幾個量各算一次")
    ap.add_argument("--json")
    args = ap.parse_args()
    UPS[:] = args.up
    md.LEVELS = tuple(args.levels)
    md.RUNS = args.runs
    md.snapshot = snapshot
    grind = argparse.Namespace(profile=args.profile, rise="on", jianfa=None)
    result = {}
    for seed in args.seeds:
        snaps = md.run(seed, grind, "solo")
        result[seed] = snaps
        for lv, r in sorted(snaps.items()):
            print(f"== 種子 {seed}・{lv} 級（實 {r['level']}）", flush=True)
            for regime in REGIMES:
                x = r[regime]
                weak = f"｜最輕 {x['weak_key']} {pct(x['weak'])}" if "weak" in x else ""
                weak += "".join(f"｜+{u:g}：{pct(a)}・最輕 {pct(b)}" for u, (a, b) in x.get("up", {}).items())
                print(f"  {regime:<10} 同級以下 {pct(x['low'])}（{x['n_low']}）高十級內 {pct(x['high'])}（{x['n_high']}）"
                      f"人物 {pct(x['figs'])}・過半 {pct(x['figs_50'])}｜檢定 {pct(x['checks'])}{weak}")
            for regime in ("v1", "balanced"):
                cells = "・".join(f"{k} {pct(m)}（{n}）" for k, (m, n) in sorted(r[regime]["odds"].items(), key=lambda kv: -kv[1][0]))
                print(f"  勝算字 {regime}：{cells}")
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
