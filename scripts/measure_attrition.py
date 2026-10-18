"""大勢人物會不會被一季打光（PM 2026-10-16；只量不改）。

二十人試玩週末第一季一季打退官軍五位，假人量不到：假人只在穩勝、有把握時順路打，江湖水漲之後多半打不贏。這份量表直接照
真人的打法擺：正式內容、週末設定（或 --profile none 的 14 天）、一個資料庫、N 個投靠了陣營的角色（真的 Game，走
Game.choose("act:challenge:<id>")），勝負由 --win 定（mock team.fight，真人打得贏），每 --step 現實秒一輪：
- 刷的人（--heavy 個／陣營）在線時每一輪都挑一位挑得了、沒閉門不見的敵方人物（瞬移到他那裡，路上的時間不算——寧可高估）；
- 其他人在線時每一輪 --casual 的機會挑一場。
在線：刷的人每天 --heavy-hours 小時、其他人 --casual-hours 小時（照名號錯開）。陣營的人一律算活躍（人數緩衝的 n 是陣營人數，
二十人試玩大家都在出陣）。體力不設限。印每一方被打退幾次、季末還倒著幾位、每位聲威最低，--rules old 是改之前的規則。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import random
import sys
import tempfile
from collections import Counter
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import database, figures, team  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.encounter import EncounterResult  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.world_state import season_length_days  # noqa: E402

DAY = 86400.0


def _hash(text: str) -> float:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF


def run(args, seed: int) -> dict:
    content = load_content(ROOT / "content", profile=None if args.profile == "none" else args.profile)
    cfg = content.config
    cfg.auto_open_first_season = True
    cfg.train_event_chance = 0.0
    if args.rules == "old":
        cfg.figure_dent_once_per_day, cfg.figure_return_days = False, 0
    cfg.figure_life.enabled = args.life == "on"
    if args.return_days is not None:
        cfg.figure_return_days = args.return_days
    rng = random.Random(seed)
    outcome = {"win": True}

    def fight(*a, **k):
        return EncounterResult(tier="大勝" if outcome["win"] else "落敗", margin=50 if outcome["win"] else -80,
                               our_power=200, difficulty=120)

    falls: Counter = Counter()
    wins: Counter = Counter()
    low: dict[str, int] = {}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, mock.patch.object(team, "fight", fight):
        store = open_world(Path(tmp) / "t.db")
        try:
            store.open_season(content, 0.0)
            players = []
            for side in ("guan", "huang"):
                for i in range(args.per_side):
                    name = f"{'官' if side == 'guan' else '黃'}{i}"
                    game = Game.new(content, name, rng=random.Random(f"{seed}|{name}"), world=store)
                    p = game.state.player
                    p.faction = side
                    p.tutorial_step = len(content.tutorial.steps)
                    heavy = i < args.heavy
                    players.append((game, heavy, _hash(f"{seed}|{name}")))
            length = season_length_days(store.get_season(), content) * DAY
            now = 0.0
            while now < length:
                now += args.step
                for game, heavy, phase in players:
                    hours = args.heavy_hours if heavy else args.casual_hours
                    if ((now / DAY + phase) % 1.0) * 24 >= hours:
                        continue
                    if not heavy and rng.random() >= args.casual:
                        continue
                    game.sync(now)
                    s, c = game.state, game.content
                    if s.world.ended:
                        break
                    p = s.player
                    w = s.world
                    w.active_pushers.setdefault(p.faction, {}).update(
                        {g.state.player.name: w.time for g, _, _ in players if g.state.player.faction == p.faction})
                    targets = [fid for fid, fig in c.figures.items() if fig.faction != p.faction
                               and figures.can_challenge(s, c, fid) and p.snubbed_until.get(fid, 0) <= now]
                    if not targets:
                        continue
                    fid = rng.choice(targets)
                    p.location = figures.state_of(s, c, fid).location
                    p.stamina = cfg.stamina_max
                    was_out = figures.is_out(s, fid)
                    outcome["win"] = rng.random() < args.win
                    if f"act:challenge:{fid}" not in [o.id for o in game.options() if o.enabled]:
                        continue
                    game.choose(f"act:challenge:{fid}")
                    wins[p.name] += outcome["win"]
                    if figures.is_out(game.state, fid) and not was_out:
                        falls[fid] += 1
                    for f2, st in game.state.world.figures.items():
                        if st.status == "active":
                            low[f2] = min(low.get(f2, 999), st.prestige)
                if store.get_season().ended:
                    break
            end = store.get_season()
            still = [fid for fid, st in end.figures.items() if st.status in figures.OUT]
        finally:
            database.close_all()
    side_of = {fid: fig.faction for fid, fig in content.figures.items()}
    return {
        "退場次數": {s: sum(n for fid, n in falls.items() if side_of[fid] == s) for s in ("guan", "huang")},
        "誰": {figures.name_of(content, fid): n for fid, n in falls.items()},
        "季末倒著": [figures.name_of(content, fid) for fid in still],
        "聲威最低": {figures.name_of(content, fid): v for fid, v in low.items()},
        "打贏最多": sorted(wins.values(), reverse=True)[:4],
    }


def main(argv=None) -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="weekend")
    ap.add_argument("--life", choices=["on", "off"], default="on", help="人物活起來（Config.figure_life）")
    ap.add_argument("--rules", choices=("new", "old"), default="new")
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--per-side", type=int, default=10)
    ap.add_argument("--heavy", type=int, default=3)
    ap.add_argument("--heavy-hours", type=float, default=14)
    ap.add_argument("--casual-hours", type=float, default=5)
    ap.add_argument("--casual", type=float, default=0.15)
    ap.add_argument("--win", type=float, default=0.85)
    ap.add_argument("--step", type=float, default=600)
    ap.add_argument("--return-days", type=float, default=None)
    args = ap.parse_args(argv)
    print(f"設定：{args.profile}　規則 {args.rules}　每邊 {args.per_side} 人（刷的 {args.heavy}）　勝率 {args.win}", flush=True)
    for seed in args.seeds:
        print(f"種子 {seed}：{run(args, seed)}", flush=True)


if __name__ == "__main__":
    main()
