"""親衛隊長專長量表（親衛隊長第四批；Joy 2026-11-10「全部做完一起上」；平衡清單：各種配法、真實對手、搭配吃屬性的武學、說清楚沒量的）。

量的是每一條出路的專長在它那一格到底推多少，跟玉璽碎片（全服七片、最稀有的那一格）比：親衛隊長人人養得到，一格不該超過碎片的一半。
每個人都是真的 Game 物件（scripts/balance_matrix.py 的配法 × 身手），打的是真的判定：

1. 打野怪（team.fight，單次判定＋回合＋閃避）：每一種配法 × 身手，難度先對分找到勝負各半的那一點，再打它與難一成、易一成，
   各打 N 場，比沒有親衛、弓箭手（fight_pp）、恩深與敬重（dodge）的勝率、落敗率。另量碎片的威力 ×1.10 做對照。
2. 截殺與設伏（encounter.resolve_encounter 用 combat.spar_power，真的雙方）：每一對配法 × 身手互打，比殺手（raid）、謀士（ambush）
   的威力加成推的勝率，跟碎片 ×1.10 對照。
3. 醫者（toll_cut）：每一套身手原本的化勁＋防具減損，加上醫者之後實際少掉幾成（照舊夾 armor.total_cap）。
4. 其他六格照設定換算成「多幾成」：大場面判讀（big_fight，百分點，夾 ±big_fight_swing）、懸賞（bounty_pct）、打造（forge_points，
   跟輔料高一階的分比）、農夫（stamina_day，跟一天自然回的體力比）、乞丐（tavern_asks，跟一天問酒家幾次比）、斥候（explore_legend，
   破境丹的機會）。這幾格是倍數或固定點，不吃屬性。

沒量的：擂台、奪璽單挑、論武、切磋的快照對打（親衛不進快照，專長在那幾條路上本來就是 0）；全服決戰的回合（將軍走大場面判讀，
不走決戰回合）；整季下來多賺多少（每一格都照它那一格的單位換算，沒跑整季機器人比總收入）。

用法：python scripts/measure_guard.py [--profile week7] [--n 400] [--level 30] [--json out.json]
     [--set 弓箭手.fight_pp=2 恩深.dodge=0.02 ...]（試別的數字；不給照 Config.guard 現在的）
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("balance_matrix", ROOT / "scripts" / "balance_matrix.py")
bm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bm)  # 它先把 stdout 包成 UTF-8、TIANXIA_DB 設到暫存檔

from tianxia import encounter, team, traits  # noqa: E402
from tianxia.core import combat  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.state import GuardBook  # noqa: E402

KITS = ("下品", "上品", "自創上品", "絕學", "護命回春", "輕身先手", "悟招破甲")
BUILDS = ("全武力", "全統御", "全悟性", "全身法", "全魅力", "均衡")
WIN = team.WIN_TIERS
SEAL_POWER = 1.10  # 對照：玉璽碎片改版的威力倍數（Config.seal.revamp.power）

# 建議的數字（這支腳本要驗的）：碎片的一半上下
PROPOSAL = {
    "將軍": {"big_fight": 3}, "謀士": {"ambush": 0.05}, "遊俠": {"bounty_pct": 0.1}, "鐵匠": {"forge_points": 4},
    "農夫": {"stamina_day": 24}, "乞丐": {"tavern_asks": 1}, "殺手": {"raid": 0.05}, "弓箭手": {"fight_pp": 3},
    "醫者": {"toll_cut": 0.05}, "斥候": {"explore_legend": 0.25},
}
BAND_PROPOSAL = {"恩深": {"dodge": 0.02}, "敬重": {"dodge": 0.01}}


def guarded(g, path: str, qing: int) -> None:
    g.state.player.guard = GuardBook(stage="sworn", name="阿牛", sex="男", path=path, title="試", qing=qing, along=True)


def unguarded(g) -> None:
    g.state.player.guard = None


def npc_power(g, squad_id: str) -> float:
    s, c, w = g.state, g.content, g.world
    squad = c.squads[squad_id]
    with team.facing(s, c, squad):
        arts = team.team_arts(s, c, w)
        return encounter.team_power(*team._with_attribute(team._styled_fighters(s, c, w, arts, squad), arts, squad.attribute))


def npc_rates(g, squad_id: str, difficulty: float, n: int, seed: int) -> tuple[float, float]:
    """打 n 場：(勝率, 落敗率)。每場換一次戰報流水號，回合的亂數才不會每場一樣。"""
    rng = random.Random(seed)
    s = g.state
    seq0 = s.battle_seq
    won = lost = 0
    for i in range(n):
        s.battle_seq = seq0 + i
        r = team.fight(s, g.content, g.world, squad_id, rng, difficulty=difficulty)
        won += r.tier in WIN
        lost += r.tier == "落敗"
    s.battle_seq = seq0
    return won / n, lost / n


def even_difficulty(g, squad_id: str, n: int, seed: int) -> float:
    """勝率剛好一半的難度（對分找；威力跟難度不是一比一：屬性對抗、功效、回合都會改）。"""
    lo, hi = 1.0, npc_power(g, squad_id) * 3
    for _ in range(10):
        mid = (lo * hi) ** 0.5
        if npc_rates(g, squad_id, mid, n, seed)[0] > 0.5:
            lo = mid
        else:
            hi = mid
    return (lo * hi) ** 0.5


def pvp_rate(a, b, mult: float, n: int, seed: int) -> float:
    rng = random.Random(seed)
    ours, theirs = combat.spar_power(a, b) * mult, combat.spar_power(b, a)
    return sum(encounter.resolve_encounter(ours, theirs, rng).tier in WIN for _ in range(n)) / n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="week7")
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--level", type=int, default=30)
    ap.add_argument("--json")
    ap.add_argument("--set", nargs="*", default=[], help="出路或心性.鍵=值")
    args = ap.parse_args()
    content = load_content(ROOT / "content", profile=args.profile)
    t = content.config.guard
    t.enabled = True
    perks = {k: dict(v) for k, v in PROPOSAL.items()}
    bands = {k: dict(v) for k, v in BAND_PROPOSAL.items()}
    for item in args.set:
        head, _, val = item.partition("=")
        who, _, key = head.partition(".")
        (bands if who in bands else perks).setdefault(who, {})[key] = float(val)
    t.perks, t.band_perks = perks, bands
    print(f"設定 {args.profile}、{args.level} 級、每格 {args.n} 場；建議：{json.dumps(perks, ensure_ascii=False)} {json.dumps(bands, ensure_ascii=False)}")
    kit, seq = bm.Kit(content), [0]
    games = {(b, k): bm.make(content, kit, b, k, args.level, seq) for b in BUILDS for k in KITS}
    squad_id = next(sid for sid, sq in content.squads.items() if not getattr(sq, "story", False))
    out: dict = {"npc": [], "pvp": [], "toll": [], "flat": {}}

    # 1. 打野怪
    print("\n一、打野怪（勝率／落敗率，百分點差；難度＝勝負各半的那一點 ×0.9、×1.0、×1.1、×1.4：最後一種才打得出落敗，量擋刀）")
    print("配法・身手 | 難度 | 沒親衛 | 弓箭手 | 恩深擋刀 | 敬重擋刀 | 碎片 ×1.10（對照）")
    worst = {"fight_pp": 0.0, "恩深": 0.0, "敬重": 0.0, "seal": 0.0}
    for (b, k), g in games.items():
        unguarded(g)
        power = even_difficulty(g, squad_id, max(60, args.n // 4), 7)
        for scale in (0.9, 1.0, 1.1, 1.4):
            d = power * scale
            seed = hash((b, k, scale)) & 0xFFFF
            unguarded(g)
            base_w, base_l = npc_rates(g, squad_id, d, args.n, seed)
            guarded(g, "弓箭手", 0)  # 淡然：沒有擋刀，只看弓箭手
            pp_w, _ = npc_rates(g, squad_id, d, args.n, seed)
            guarded(g, "醫者", 15)  # 恩深（醫者不動判定）：只看擋刀
            en_w, en_l = npc_rates(g, squad_id, d, args.n, seed)
            guarded(g, "醫者", 8)
            jz_w, jz_l = npc_rates(g, squad_id, d, args.n, seed)
            unguarded(g)
            sl_w, _ = npc_rates(g, squad_id, d / SEAL_POWER, args.n, seed)
            row = {"build": b, "kit": k, "scale": scale, "base_win": base_w, "base_loss": base_l, "pp": pp_w - base_w,
                   "en_loss": base_l - en_l, "jz_loss": base_l - jz_l, "seal": sl_w - base_w}
            out["npc"].append(row)
            worst["fight_pp"] = max(worst["fight_pp"], row["pp"])
            worst["恩深"] = max(worst["恩深"], row["en_loss"])
            worst["敬重"] = max(worst["敬重"], row["jz_loss"])
            worst["seal"] = max(worst["seal"], row["seal"])
            if scale in (1.0, 1.4):
                print(f"{b}・{k} | ×{scale} | {base_w:.0%}／{base_l:.0%} | {row['pp']:+.1%} | 敗 {-row['en_loss']:+.1%} | "
                      f"敗 {-row['jz_loss']:+.1%} | {row['seal']:+.1%}")
    npc = out["npc"]
    print(f"四種難度合計：弓箭手勝率平均 {statistics.mean(r['pp'] for r in npc):+.1%}（最多 {worst['fight_pp']:+.1%}）；"
          f"恩深落敗少 {statistics.mean(r['en_loss'] for r in npc):.1%}（最多 {worst['恩深']:.1%}）；"
          f"敬重落敗少 {statistics.mean(r['jz_loss'] for r in npc):.1%}（最多 {worst['敬重']:.1%}）；"
          f"碎片勝率平均 {statistics.mean(r['seal'] for r in npc):+.1%}（最多 {worst['seal']:+.1%}）")

    # 2. 截殺與設伏：每一對配法（同一套身手）與每一對身手（均衡配法）
    print("\n二、截殺、設伏（真的雙方；勝率百分點差）")
    pairs = [((a, k), (b2, k)) for k in KITS for a in BUILDS for b2 in BUILDS if a != b2]
    pairs += [(("均衡", k1), ("均衡", k2)) for k1 in KITS for k2 in KITS if k1 != k2]
    raid_m, amb_m = 1 + perks["殺手"]["raid"], 1 + perks["謀士"]["ambush"]
    for x, y in pairs:
        a, b = games[x], games[y]
        seed = hash((x, y)) & 0xFFFF
        base = pvp_rate(a, b, 1.0, args.n, seed)
        out["pvp"].append({"a": x, "b": y, "base": base, "raid": pvp_rate(a, b, raid_m, args.n, seed) - base,
                           "ambush": pvp_rate(a, b, amb_m, args.n, seed) - base, "seal": pvp_rate(a, b, SEAL_POWER, args.n, seed) - base})
    pvp = out["pvp"]
    even = [r for r in pvp if 0.3 <= r["base"] <= 0.7]
    for key, label in (("raid", "殺手"), ("ambush", "謀士"), ("seal", "碎片 ×1.10（對照）")):
        print(f"{label}：全部 {len(pvp)} 對平均 {statistics.mean(r[key] for r in pvp):+.1%}（最多 {max(r[key] for r in pvp):+.1%}）；"
              f"勢均力敵的 {len(even)} 對平均 {statistics.mean(r[key] for r in even):+.1%}")

    # 3. 醫者
    print("\n三、醫者（每一場本人少扣的氣血；化勁＋防具＋醫者照舊夾上限）")
    cap = content.config.armor.total_cap
    cut = perks["醫者"]["toll_cut"]
    for k in KITS:
        g = games[("均衡", k)]
        lo = traits.loadout(g.state, content, g.world)
        had = min(cap, traits.amount(content, lo, "toll_cut") + team.armor_cut(g.state, content, g.world))
        now = min(cap, had + cut)
        saved = (now - had) / (1 - had) if had < 1 else 0.0
        out["toll"].append({"kit": k, "had": had, "now": now, "saved": saved})
        print(f"{k}：原本少扣 {had:.0%} → {now:.0%}（掉的氣血再少 {saved:.1%}）")

    # 4. 其他六格
    cfg = content.config
    regen_day = 86400 / cfg.stamina_regen_seconds
    rule = cfg.weapons.quality
    flat = {
        "將軍 big_fight": f"大場面判讀 +{perks['將軍']['big_fight']:.0f} 個百分點（模型給 ±{cfg.big_fight_swing}，合起來照舊夾在 ±{cfg.big_fight_swing}）",
        "謀士 ambush": f"伏兵威力 ×{amb_m:.2f}（勝率見第二節；碎片 ×{SEAL_POWER:.2f}）",
        "遊俠 bounty_pct": f"懸賞賞銀 +{perks['遊俠']['bounty_pct']:.0%}",
        "鐵匠 forge_points": f"造化分 +{perks['鐵匠']['forge_points']:.0f}（輔料高一階 +{rule.aux_tier.get('1', 0) - rule.aux_tier.get('0', 0):.0f}、熟手上限 +{rule.practice_cap:.0f}）",
        "農夫 stamina_day": f"每天 +{perks['農夫']['stamina_day']:.0f} 體力（自然回一天 {regen_day:.0f}：+{perks['農夫']['stamina_day'] / regen_day:.0%}；碎片承露 +10%～25%）",
        "乞丐 tavern_asks": f"問酒家一天 {cfg.xinshen.ask_per_day} → {cfg.xinshen.ask_per_day + int(perks['乞丐']['tavern_asks'])} 次",
        "斥候 explore_legend": f"探索撿破境丹 {cfg.explore_legend_chance:.1%} → {cfg.explore_legend_chance * (1 + perks['斥候']['explore_legend']):.2%}",
        "醫者 toll_cut": f"少扣 +{cut:.0%}（見第三節）",
    }
    out["flat"] = flat
    print("\n四、照單位換算的幾格")
    for k, v in flat.items():
        print(f"{k}：{v}")
    if args.json:
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
