"""本命武學加強前後，跟頂尖合成品比（企劃者 2026-10-15「現在的本命絕學很爛，甚至比玩家自己合成的還差」）：只量、不改數字。

每一位人物，本人第 30 級（屬性點照 臂力、根骨、身法、悟性、博聞 的順序配到頂）、身上兩門都是他的本命武學與本命內功、第十成，三種：
- 修前：本命武學照舊（絕學 50～120、只有自己屬性一個功效、沒有本命特效）；
- 頂尖合成：同屬性的兩門合成絕學擲到最高（威力 ×1.1，第十成 132），帶跟本命武學一樣的三個一般功效、沒有特別功效；
- 修後：本命武學（威力 ×Config.signature_arts.power_scale、三個一般功效、本命特效）。
量的是本人單挑（不帶同伴部下）：威力（氣血當滿的），對上「頂尖合成那一份威力 ×0.8、×1.0」難度的對手的贏面（大勝＋險勝，
含功效與本命特效的破甲、先手、穩，不含閃避；固定種子 2000 場）。本命特效其餘的（門下、回血、內傷、心得經驗銀兩、閃避、體力）
不進威力與贏面，照數字列在最後一欄。

用法：.venv/Scripts/python.exe scripts/measure_signature.py [--profile weekend] [--level 30]
"""
from __future__ import annotations

import argparse
import io
import os
import random
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="measure_signature_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")

from tianxia import encounter, signature, team, traits  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

RUNS = 2000
POINT_ORDER = ("str", "con", "agi", "wis", "lore")
IN_POWER = ("self_power", "difficulty_cut", "big_win_cut", "luck_narrow")  # 已經算進威力與贏面的掛點
SYNTH_TOP = 1.1  # 合成擲到的微調最多 ±10%（martial_arts），絕學第十成 120 → 132


def stats_at(content, level):
    cfg = content.config
    stats = dict.fromkeys(team.COMBAT_STATS, float(team.BASE_STAT))
    points = team.points_between(cfg, 1, level)
    for key in POINT_ORDER:
        add = min(points, cfg.stat_cap - stats[key])
        stats[key] += add
        points -= add
    return stats


def win_rate(power, difficulty, mods):
    rng = random.Random(7)
    return sum(encounter.resolve_encounter(power, difficulty, rng, mods=mods).tier in ("大勝", "險勝") for _ in range(RUNS)) / RUNS


def old_content(content):
    """修前：本命武學沒有功效清單、沒有本命特效（power_scale 跟著不乘）。"""
    skills = {k: s.model_copy(update={"traits": [], "signature": None}) for k, s in content.skills.items()}
    return content.model_copy(update={"skills": skills})


def synth_content(content):
    """頂尖合成：三個一般功效照本命武學、沒有本命特效；威力在 resolve_art 那一層乘 SYNTH_TOP。"""
    skills = {k: s.model_copy(update={"signature": None}) for k, s in content.skills.items()}
    return content.model_copy(update={"skills": skills})


def measure(game, content, squad, difficulty_of=None):
    s, w = game.state, game.world
    power = team.power_vs(s, content, w, squad, fresh=True)
    mods = team.trait_mods(content, traits.loadout(s, content, w), s)
    return power, mods


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="weekend")
    ap.add_argument("--level", type=int, default=30)
    args = ap.parse_args()
    content = load_content(ROOT / "content", profile=None if args.profile == "none" else args.profile)
    world = open_world(TMP / "w.db")
    game = Game.new(content, "量測", rng=random.Random(0), world=world, graduated=True)
    p = game.state.player
    p.stats.update(stats_at(content, args.level))
    p.member.level = args.level
    squad = content.squads["shoumu"]
    real_resolve = team.resolve_art

    def synth_resolve(skill_id, c, wld):
        art = real_resolve(skill_id, c, wld)
        if art is None or skill_id not in sig_ids:
            return art
        return art.model_copy(update={"base_power": art.base_power * SYNTH_TOP, "top_power": art.top_power * SYNTH_TOP, "origin": "fused"})

    sig_ids = {sid for sid, sk in content.skills.items() if sk.signature is not None}
    print(f"設定：{args.profile}，本人第 {args.level} 級，兩門第十成，對手 shoumu 的屬性；贏面＝大勝＋險勝（{RUNS} 場）")
    print("人物 | 威力 修前/合成/修後 | 對合成×0.8 修前/合成/修後 | 對合成×1.0 修前/合成/修後 | 本命特效（不進威力與贏面的）")
    rows = []
    for cid, ch in content.characters.items():
        if not (ch.starting_wugong and ch.starting_neigong) or ch.starting_wugong not in sig_ids:
            continue
        p.member.wugong_id, p.member.wugong_level = ch.starting_wugong, 10
        p.member.neigong_id, p.member.neigong_level = ch.starting_neigong, 10
        p.art_quality = {}
        with mock.patch.object(team, "resolve_art", synth_resolve):
            synth_c = synth_content(content)
            sp, smods = measure(game, synth_c, squad)
        op, omods = measure(game, old_content(content), squad)
        np_, nmods = measure(game, content, squad)
        rates = [[win_rate(pw, sp * k, m) for pw, m in ((op, omods), (sp, smods), (np_, nmods))] for k in (0.8, 1.0)]
        extra = "；".join(
            f"{sig.name}：" + ("、".join(
                signature.HOOK_TEXT[h].replace("{value}", signature.value_text(h, v)) for h, v in sig.effects.items()
                if h not in IN_POWER
            ) or "（全進威力與贏面）")
            for _, sig in signature.worn(game.state, content)
        )
        rows.append((np_ / sp, rates))
        print(
            f"{ch.name} | {op:.0f}/{sp:.0f}/{np_:.0f} | "
            + " | ".join("/".join(f"{r:.0%}" for r in rr) for rr in rates)
            + f" | {extra}"
        )
    n = len(rows)
    print(f"平均：修後威力是頂尖合成的 {sum(r for r, _ in rows) / n:.2f} 倍；"
          f"對合成×0.8 修前/合成/修後 {'/'.join(f'{sum(rr[0][i] for _, rr in rows) / n:.0%}' for i in range(3))}，"
          f"對合成×1.0 {'/'.join(f'{sum(rr[1][i] for _, rr in rows) / n:.0%}' for i in range(3))}")


if __name__ == "__main__":
    main()
