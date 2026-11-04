"""五項屬性的季、玩家對玩家：幾種配法互打的勝率（企劃者 2026-11-04「全部點武力 會不會沒人打得過他」）。

同一套武學、同一個等級，只差配比與送點：每一對照切磋的算法（Game._spar_power：照對手本人的五項對抗）擲 N 場，
印「列那一個人贏的機會」。--old 照改之前的算法（對上同等級的平均人、各算各的）對照。

用法：python scripts/measure_pvp_attrs.py [--levels 10 20 30 50] [--n 4000] [--old] [--pvp 0.5]
"""
from __future__ import annotations

import argparse
import io
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TIANXIA_DB", str(Path(tempfile.mkdtemp(prefix="pvp-")) / "t.db"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from tianxia import encounter, team  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

# 名字 → (配比, 送點全給哪一項)；「全武力」是上限 4 之下最重的武力配法（另一項 3 給身法：閃得掉）
BUILDS = {
    "全武力": ({"str": 4, "lead": 1, "int": 1, "spd": 3, "cha": 1}, "str"),
    "武將": ("warrior", "str"),
    "均衡": ("balanced", None),
    "全統御": ({"str": 3, "lead": 4, "int": 1, "spd": 1, "cha": 1}, "lead"),
    "謀士": ("strategist", "int"),
    "舊全武力(6)": ({"str": 6, "lead": 1, "int": 1, "spd": 1, "cha": 1}, "str"),
}


def make(content, name: str, level: int) -> Game:
    split, bonus = BUILDS[name]
    world = open_world(Path(tempfile.mkdtemp(prefix="pvp-")) / "t.db")
    g = Game.new(content, name, rng=random.Random(0), world=world)
    g.client = None
    p = g.state.player
    p.member.level = level
    if isinstance(split, dict):
        p.growth_preset, p.growth_custom = "custom", dict(split)
    else:
        p.growth_preset = split
    pts = (level // content.config.attributes.v2.bonus_every) * content.config.attributes.v2.bonus_points
    keys = content.config.attributes.v2.keys
    if bonus:
        p.attr_alloc = {bonus: pts}
    else:
        p.attr_alloc = {k: pts // len(keys) for k in keys}
    return g


def alone(g: Game) -> float:
    """改之前的算法：各算各的、對上同等級的平均人（Game._battle_power 的形狀）。"""
    s, c, w = g.state, g.content, g.world
    return encounter.member_power(s.player.member, team.team_arts(s, c, w), boost=team.player_boost(s, c, w))


def win_rate(a: float, b: float, n: int, seed: int) -> float:
    rng = random.Random(seed)
    won = sum(encounter.resolve_encounter(a, b, rng).tier in team.WIN_TIERS for _ in range(n))
    return won / n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", type=int, nargs="+", default=[10, 20, 30, 50])
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--old", action="store_true", help="照改之前：對上同等級的平均人")
    ap.add_argument("--pvp", type=float, default=None, help="試別的 pvp_scale（玩家對玩家時效果表再乘幾倍，例 1 或 0.5）")
    args = ap.parse_args()
    c = load_content(ROOT / "content", profile="season21")
    c.config.attributes.v2.enabled = True
    c.config.auto_open_first_season = True
    if args.pvp is not None:
        c.config.attributes.v2.pvp_scale = args.pvp
    names = list(BUILDS)
    for level in args.levels:
        games = {n: make(c, n, level) for n in names}
        print(f"\n第 {level} 級（列的人贏的機會；同武學同等級）")
        print("".ljust(12) + "".join(n.ljust(12) for n in names))
        for a in names:
            row = []
            for b in names:
                if args.old:
                    pa, pb = alone(games[a]), alone(games[b])
                else:
                    pa, pb = Game._spar_power(games[a], games[b]), Game._spar_power(games[b], games[a])
                row.append(f"{win_rate(pa, pb, args.n, hash((level, a, b)) & 0xffff):.0%}")
            print(a.ljust(12) + "".join(r.ljust(12) for r in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
