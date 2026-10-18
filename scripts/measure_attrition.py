"""大勢人物會不會被一季打光（PM 2026-10-16；只量不改）。

二十人試玩週末第一季一季打退官軍五位，假人量不到：假人只在穩勝、有把握時順路打，江湖水漲之後多半打不贏。這份量表直接照
真人的打法擺：正式內容、週末設定（或 --profile none 的 14 天）、一個資料庫、N 個投靠了陣營的角色（真的 Game，走
Game.choose("act:challenge:<id>")），勝負由 --win 定（mock team.fight，真人打得贏），每 --step 現實秒一輪：
- 刷的人（--heavy 個／陣營）在線時每一輪都挑一位挑得了、沒閉門不見的敵方人物（瞬移到他那裡，路上的時間不算——寧可高估）；
- 其他人在線時每一輪 --casual 的機會挑一場。
在線：刷的人每天 --heavy-hours 小時、其他人 --casual-hours 小時（照名號錯開）。陣營的人一律算活躍（人數緩衝的 n 是陣營人數，
二十人試玩大家都在出陣）。體力不設限。印每一方被打退幾次、季末還倒著幾位、每位聲威最低，--rules old 是改之前的規則。

護著大勢人物（Joy 2026-10-17 第 6 條；figure_aid）：--guards 個／陣營（排在刷的人後面）在線時每一輪去替自己陣營聲威最低、
還在場的人物站崗（站著崗就不動）；--rally 個／陣營在線時每一輪犒一位聲威沒滿的。挑戰的人突破護衛的機會照 --guard-break
（mock 護衛那一關的判定）。--no-aid 把整個開關關掉當對照。
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

from tianxia import database, encounter, figure_aid, figures, team  # noqa: E402
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
    if args.no_aid:
        cfg.figure_aid.enabled = False
    if args.guard_hours is not None:
        cfg.figure_aid.guard_hours = args.guard_hours
    if args.rally_points is not None:
        cfg.figure_aid.rally_points = args.rally_points
    if args.aid_hours is not None:
        args.aid_online = args.aid_hours
    rng = random.Random(seed)
    outcome = {"win": True}
    guard_rng = random.Random(f"{seed}|護衛")

    def contest(*a, **k):
        broke = guard_rng.random() < args.guard_break
        return EncounterResult(tier="大勝" if broke else "落敗", margin=50 if broke else -80, our_power=200, difficulty=120)

    def fight(*a, **k):
        return EncounterResult(tier="大勝" if outcome["win"] else "落敗", margin=50 if outcome["win"] else -80,
                               our_power=200, difficulty=120)

    falls: Counter = Counter()
    wins: Counter = Counter()
    low: dict[str, int] = {}
    blocked = Counter()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, mock.patch.object(team, "fight", fight), \
            mock.patch.object(encounter, "resolve_encounter", contest):
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
                    role = "guard" if args.heavy <= i < args.heavy + args.guards else (
                        "rally" if args.heavy + args.guards <= i < args.heavy + args.guards + args.rally else "")
                    players.append((game, heavy, _hash(f"{seed}|{name}"), role))
            length = season_length_days(store.get_season(), content) * DAY
            now = 0.0
            while now < length:
                now += args.step
                for game, heavy, phase, role in players:
                    hours = args.heavy_hours if heavy else (args.aid_online if role else args.casual_hours)
                    if ((now / DAY + phase) % 1.0) * 24 >= hours:
                        continue
                    if role and cfg.figure_aid.enabled:
                        game.sync(now)
                        _aid(game, role)
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
                        {g.state.player.name: w.time for g, _, _, _ in players if g.state.player.faction == p.faction})
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
                    msgs = game.choose(f"act:challenge:{fid}")
                    if any("身前" in m and "退下" in m for m in msgs):
                        blocked[fid] += 1
                        continue
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
        "護衛擋下": sum(blocked.values()),
    }


def _aid(game, role: str) -> None:
    """護衛：站著崗就不動；否則去替自己陣營聲威最低、還在場的人物站崗。犒軍：犒一位聲威沒滿的（聲威最低的先）。瞬移、體力不設限。"""
    s, c = game.state, game.content
    p = s.player
    figure_aid.prune(s, c)
    if role == "guard" and any(q.name == p.name for q in s.world.figure_guards):
        return
    mine = sorted(
        (fid for fid, fig in c.figures.items() if fig.faction == p.faction
         and (st := figures.state_of(s, c, fid)).status == "active" and st.location),
        key=lambda fid: (figures.state_of(s, c, fid).prestige, fid),
    )
    for fid in mine:
        p.location = figures.state_of(s, c, fid).location
        p.stamina = c.config.stamina_max
        p.stats["silver"] = 1000
        option = f"aid:{role}:{fid}"
        if option in [o.id for o in game.options() if o.enabled]:
            game.choose(option)
            return


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
    ap.add_argument("--guards", type=int, default=0)
    ap.add_argument("--rally", type=int, default=0)
    ap.add_argument("--guard-break", type=float, default=0.5)
    ap.add_argument("--no-aid", action="store_true")
    ap.add_argument("--guard-hours", type=float, default=None)
    ap.add_argument("--rally-points", type=int, default=None)
    ap.add_argument("--aid-hours", type=float, default=None, help="護衛、犒軍的人每天在線幾小時（預設同 --casual-hours）")
    args = ap.parse_args(argv)
    args.aid_online = args.casual_hours
    print(f"設定：{args.profile}　規則 {args.rules}　每邊 {args.per_side} 人（刷的 {args.heavy}、護衛 {args.guards}、犒軍 {args.rally}）"
          f"　勝率 {args.win}　突破護衛 {args.guard_break}" + ("　護著人物關著" if args.no_aid else ""), flush=True)
    for seed in args.seeds:
        print(f"種子 {seed}：{run(args, seed)}", flush=True)


if __name__ == "__main__":
    main()
