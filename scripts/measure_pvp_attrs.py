"""五項屬性的季、玩家對玩家：幾種配法互打的勝率（企劃者 2026-11-04「全部點武力 會不會沒人打得過他」）。

同一套起始武學（兩門都練滿）、同一個等級，只差配比與送點：每一對照切磋的算法（Game._spar_power：照對手本人的五項對抗）擲 N 場，
印「列那一個人贏的機會」；再印打 NPC 與事件檢定（pve）。--old 照改之前的算法（對上同等級的平均人、各算各的）對照。

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
from tianxia.martial_arts import MAX_LEVEL  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

# 名字 → (配比, 送點全給哪一項)。「全某項」是上限 4 底下最偏那一項的配法：那一項 4、另一項 3、其餘 1，送點全給那一項
BUILDS = {
    "全武力": ({"str": 4, "lead": 1, "int": 1, "spd": 3, "cha": 1}, "str"),
    "全統御": ({"str": 3, "lead": 4, "int": 1, "spd": 1, "cha": 1}, "lead"),
    "全悟性": ({"str": 1, "lead": 1, "int": 4, "spd": 1, "cha": 3}, "int"),
    "悟性武力": ({"str": 3, "lead": 1, "int": 4, "spd": 1, "cha": 1}, "int"),
    "全身法": ({"str": 3, "lead": 1, "int": 1, "spd": 4, "cha": 1}, "spd"),
    "全魅力": ({"str": 1, "lead": 1, "int": 3, "spd": 1, "cha": 4}, "cha"),
    "武將": ("warrior", "str"),
    "均衡": ("balanced", None),
}


def make(content, name: str, level: int) -> Game:
    split, bonus = BUILDS[name]
    world = open_world(Path(tempfile.mkdtemp(prefix="pvp-")) / "t.db")
    g = Game.new(content, name, rng=random.Random(0), world=world)
    g.client = None
    p = g.state.player
    p.member.level = level
    p.member.wugong_level = p.member.neigong_level = MAX_LEVEL  # 兩門都練滿（內功的份量才看得出悟性）
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


def pve(content, games: dict, level: int) -> None:
    """打 NPC 與事件檢定：每一路對手都當同等級（屬性照它的資質長），威力比均衡多幾成、落敗閃成僵持的機會、少掉的氣血；
    正式內容每一個檢定的平均與這一套最輕那一項的檢定平均，另外每一項各自的檢定平均。"""
    from tianxia import attrset, rules
    squads = [sq.model_copy(update={"level": float(level)}) for sq in content.squads.values()]
    checks = [ch.check for ev in content.events.values() for ch in ev.choices if ch.check is not None]
    print(f"  打 NPC（{len(squads)} 路對手都當第 {level} 級）與事件檢定 {len(checks)} 個")
    rows = {}
    for name, g in games.items():
        s, c, w = g.state, g.content, g.world
        powers, dodges, guards = [], [], []
        for sq in squads:
            with team.facing(s, c, sq):
                powers.append(team.power_vs(s, c, w, sq, fresh=True))
                dodges.append(team.dodge_chance(s, c))
            guards.append(team._guard(s, c, w, sq))
        by: dict[str, list[float]] = {}
        for ch in checks:
            by.setdefault(attrset.key_of(c, ch.stat), []).append(rules.check_chance(ch, s, c, w))
        each = {k: sum(v) / len(v) for k, v in by.items()}
        rows[name] = (sum(powers) / len(powers), sum(dodges) / len(dodges), sum(guards) / len(guards),
                      sum(sum(v) for v in by.values()) / len(checks), each)
    base = rows["均衡"][0]
    print("  " + "".ljust(10) + "威力比均衡  閃成僵持  少掉氣血  檢定平均  各項檢定")
    for name, (mean, dodge, guard, chk, each) in rows.items():
        parts = " ".join(f"{k}{v:.0%}" for k, v in sorted(each.items()))
        print("  " + name.ljust(10) + f"{mean / base - 1:+.0%}".ljust(12) + f"{dodge:.0%}".ljust(10) + f"{guard:.0%}".ljust(10)
              + f"{chk:.0%}".ljust(10) + parts)


def win_rate(a: float, b: float, n: int, seed: int) -> float:
    rng = random.Random(seed)
    won = sum(encounter.resolve_encounter(a, b, rng).tier in team.WIN_TIERS for _ in range(n))
    return won / n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", type=int, nargs="+", default=[10, 20, 30, 50])
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--old", action="store_true", help="照改之前：對上同等級的平均人")
    ap.add_argument("--int-outer", type=float, default=None, help="試：悟性也管外功（對他的悟性），上限這麼多")
    ap.add_argument("--str-cap", type=float, default=None, help="試：武力管外功的上限改成這麼多")
    ap.add_argument("--inner-x", type=float, default=None, help="試：內功那一項的份量乘這麼多（悟性管的那一塊變重）")
    ap.add_argument("--pvp", type=float, default=None, help="試別的 pvp_scale（玩家對玩家時效果表再乘幾倍，例 1 或 0.5）")
    args = ap.parse_args()
    c = load_content(ROOT / "content", profile="season21")
    c.config.attributes.v2.enabled = True
    c.config.auto_open_first_season = True
    if args.int_outer:
        from tianxia.models import AttrEffect
        c.config.attributes.v2.effects.append(AttrEffect(attr="int", hook="outer", curve="contest", cap=args.int_outer, scale=40, origin=50))
    if args.str_cap is not None:
        for row in c.config.attributes.v2.effects:
            if row.attr == "str" and row.hook == "outer":
                row.cap = args.str_cap
    if args.inner_x:
        encounter.NEIGONG_BONUS_DIVISOR /= args.inner_x
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
        pve(c, games, level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
