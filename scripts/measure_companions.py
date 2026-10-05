"""武學與成長計畫二之三 Task 3：同伴、部下吃屬性加成之後，隊伍強多少（人物資質設計 14.6）。只量、不改數字。

1. 威力：本人第 L 級（1／10／20／30）、四屬性都是 5，帶兩個同第 L 級的同伴（兩門第十成），
   隊伍威力「同伴吃加成」比「同伴不吃（計畫二）」多幾 %。強的一對、弱的一對各量一次。
2. 部下：每一種部下單獨的威力，吃不吃臂力差幾 %（部下以前完全沒有加成，這次第一次有）。
3. 勝率偏移：照設計 8.4 那套 272 組（本人第 10 級、四屬性 5、武學屬實、內功屬柔、兩門第十成、品質 4×4，
   對遊歷與探索的隊伍），帶兩個第 10 級的同伴，勝率「吃加成」減「不吃」的偏移（百分點）。

用法：.venv/Scripts/python.exe scripts/measure_companions.py
"""
from __future__ import annotations

import io
import os
import random
import statistics
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="measure_companions_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")  # 別開到 worktree 的 saves/tianxia.db

from tianxia import encounter, team  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.martial_arts import QUALITIES, content_art, with_quality  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.state import Member  # noqa: E402

PAIRS = {"強": ("guanyu", "zhangfei"), "弱": ("taoqian", "yuanshao")}
LEVELS = (1, 10, 20, 30)


def setup(content, pair, level):
    world = open_world(TMP / f"{'-'.join(pair)}-{level}.db")
    game = Game.new(content, "量測", rng=random.Random(0), world=world)
    p = game.state.player
    p.member.level = level
    for key in pair:
        ch = content.characters[key]

        def recruit(progress, ch=ch):
            progress.level, progress.owner = level, p.name
            progress.wugong_id, progress.neigong_id = ch.starting_wugong, ch.starting_neigong
            progress.wugong_level = progress.neigong_level = 10

        world.update_companion(key, recruit)
    p.team = list(pair)
    return game


def power(game, attribute, plain_mates):
    s, c, w = game.state, game.content, game.world
    members = team.team_participants(s, w) + team.follower_units(s, c)
    boosts = team.team_boosts(s, c, w)
    if plain_mates:  # 計畫二：同伴、部下不吃加成
        boosts = boosts[:1] + [encounter.Boost() for _ in boosts[1:]]
    return encounter.team_power(members, team.team_arts(s, c, w), attribute, team.team_conditions(s, c, w), boosts)


def win_rate(value, difficulty):
    rng = random.Random(team.ESTIMATE_SEED)
    wins = sum(
        encounter.resolve_encounter(value, difficulty, rng).tier in team.WIN_TIERS for _ in range(team.ESTIMATE_RUNS)
    )
    return 100 * wins / team.ESTIMATE_RUNS


def player_arts(game, outer_q, inner_q):
    world = game.world
    ids = []
    for kind, attribute, quality in (("武學", "實", outer_q), ("內功", "柔", inner_q)):
        name = f"量{kind}{quality}"
        if world.get_skill(name) is None:
            world.claim_skill_name(with_quality(content_art(name, name, kind, attribute, "下品"), quality))
        ids.append(name)
    m = game.state.player.member
    m.wugong_id, m.neigong_id = ids
    m.wugong_level = m.neigong_level = 10


def main() -> None:
    content = load_content(ROOT / "content")
    print("一、隊伍威力（同伴吃加成 比 不吃，多幾 %）")
    for label, pair in PAIRS.items():
        row = []
        for level in LEVELS:
            game = setup(content, pair, level)
            player_arts(game, "中品", "中品")
            new, old = power(game, None, False), power(game, None, True)
            row.append(f"{level} 級 {100 * (new / old - 1):+.1f}%")
        print(f"  {label}（{'、'.join(content.characters[k].name for k in pair)}）：" + "；".join(row))

    print("二、部下（單獨一人，吃臂力 比 不吃）")
    world = open_world(TMP / "followers.db")
    for follower in content.followers.values():
        unit = Member(wugong_id=follower.wugong, wugong_level=follower.wugong_level)
        arts = {follower.wugong: team.resolve_art(follower.wugong, content, world)}
        new = encounter.member_power(unit, arts, boost=team.follower_boost(content, follower))
        old = encounter.member_power(unit, arts, boost=encounter.Boost())
        print(f"  {follower.name}（臂力 {follower.stats.get('str', team.BASE_STAT)}）：{100 * (new / old - 1):+.1f}%")

    print("三、勝率偏移（272 組，第 10 級，帶兩個同伴；吃加成 減 不吃，百分點）")
    squads = sorted({sid for loc in content.locations.values() for sid in loc.enemies})
    for label, pair in PAIRS.items():
        game = setup(content, pair, 10)
        shifts = []
        for outer_q in QUALITIES:
            for inner_q in QUALITIES:
                player_arts(game, outer_q, inner_q)
                for sid in squads:
                    squad = content.squads[sid]
                    new = win_rate(power(game, squad.attribute, False), squad.difficulty)
                    old = win_rate(power(game, squad.attribute, True), squad.difficulty)
                    shifts.append(new - old)
        moving = [x for x in shifts if x]
        print(
            f"  {label}：{len(shifts)} 組，平均 {statistics.mean(shifts):+.1f}；有變的 {len(moving)} 組平均 "
            f"{statistics.mean(moving) if moving else 0:+.1f}；最大 {max(shifts):+.1f}；超過 10 的 {sum(x > 10 for x in shifts)} 組"
        )


if __name__ == "__main__":
    main()
