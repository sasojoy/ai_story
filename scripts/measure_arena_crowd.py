"""擂台場邊事件的觸發率與勝率差（PM 2026-10-17：「量表量實際觸發率」「量開關勝率差，要在幾個百分點內」；只量不改）。

正式內容（--profile，預設 weekend）、一個暫存資料庫、兩個一樣強的角色：甲挑乙（乙第一名、甲第二名，每一場打完把名次、戰績擺回去，
免得「天下第一」的喊聲每一場都在）。甲照假人的打法出招（看架勢出剋它的招六成，bot_policy.duel_move），--gamble 的機率改寫放手一搏
（成功率 --rate，觀眾反應照 --label）。每一種情境 --fights 場、場邊事件開與關各打一遍（同一串亂數），印：
- 一場有場邊事件的比例、各種事件各幾件；
- 甲的贏面（大勝＋險勝）開與關、差幾個百分點。
情境（兩邊的底細照 CrowdSide 直接擺，不必真的去交朋友）：
  none：兩邊什麼都沒有；patron：只有甲有台下暗助的武將（最偏一邊的情形）；both：兩邊都有暗助、同伴；
  mixed：甲、乙各自照 --share 的機率有每一樣（暗助、喝采或噓、決戰立功、同伴），每一場重擲；
  boo：只有甲是惡名在外的（被噓）；champion：乙是天下第一、打過幾場（擺回去時保留戰績）。
--daily：同一種事件同一人一天一次照算（一天打 --per-day 場）；不加就每一場把那一本帳清掉（量的是一場的機率）。"""
from __future__ import annotations

import argparse
import io
import random
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import arena, arena_crowd, bot_policy, database  # noqa: E402
from tianxia.characters import CharacterStore  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.state import CrowdSide  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

KINDS_OF = {
    "patron": lambda c: {"patron": "x", "patron_name": c},
    "cheer": lambda c: {"fame_tier": 3, "fame_title": "威震州郡", "virtue_path": "俠"},
    "boo": lambda c: {"virtue_tier": 3, "virtue_title": "州郡大盜", "virtue_path": "寇"},
    "veteran": lambda c: {"veteran": "長社火攻"},
    "mate": lambda c: {"mate": c},
}


def side(rng: random.Random, share: float, helper: str) -> CrowdSide:
    fields: dict = {}
    for kind in ("patron", "veteran", "mate"):
        if rng.random() < share:
            fields.update(KINDS_OF[kind](helper))
    pick = rng.random()
    if pick < share:
        fields.update(KINDS_OF["cheer"](helper))
    elif pick < share * 1.5:
        fields.update(KINDS_OF["boo"](helper))
    return CrowdSide(**fields)


def scenario(name: str, rng: random.Random, share: float, helper: str) -> tuple[CrowdSide, CrowdSide]:
    if name == "none" or name == "champion":
        return CrowdSide(), CrowdSide()
    if name == "patron":
        return CrowdSide(**KINDS_OF["patron"](helper)), CrowdSide()
    if name == "boo":
        return CrowdSide(**KINDS_OF["boo"](helper)), CrowdSide()
    if name == "both":
        both = {**KINDS_OF["patron"](helper), **KINDS_OF["mate"](helper)}
        return CrowdSide(**both), CrowdSide(**both)
    return side(rng, share, helper), side(rng, share, helper)


def run(args, name: str, crowd_on: bool) -> tuple[float, float, Counter]:
    content = load_content(ROOT / "content", profile=None if args.profile == "none" else args.profile)
    cfg = content.config
    cfg.auto_open_first_season = True
    cfg.arena.enabled = True
    cfg.arena.crowd.enabled = crowd_on
    cfg.arena.pair_cooldown_seconds = 0
    cfg.arena.per_day = 10 ** 6
    helper = next(iter(content.characters.values())).name
    rng = random.Random(f"{args.seed}|{name}")
    kinds: Counter = Counter()
    won = fired = 0
    real_apply = arena_crowd.apply

    def apply(fight, happening, tuning):  # 記是哪一種、落在哪一邊
        kinds[f"{happening.kind}・{'甲' if happening.side == 'me' else '乙'}"] += 1
        return real_apply(fight, happening, tuning)

    arena_crowd.apply = apply
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        store = open_world(Path(tmp) / "t.db")
        try:
            store.open_season(content, 0.0)
            chars = CharacterStore(store.db)
            games = {}
            for who in ("甲", "乙"):
                g = Game.new(content, who, rng=random.Random(who), world=store)
                g.client = None
                g.state.player.tutorial_step = len(content.tutorial.steps)
                g.sync(0.0)
                g.choose("act:arena")
                g.choose("arena:join")
                g.choose("arena:back")
                chars.save(g.state)
                games[who] = g
            a = games["甲"]
            for i in range(args.fights):
                w = store.get_season()
                mine, foe = w.arena["甲"], w.arena["乙"]
                mine.rank, foe.rank = 2, 1
                for e in (mine, foe):
                    e.wins = e.losses = e.draws = e.streak = 0
                if name == "champion":
                    foe.wins, foe.streak = 5, 5
                me_side, foe_side = scenario(name, rng, args.share, helper)
                foe.crowd = foe_side
                day = i // args.per_day
                if not args.daily or i % args.per_day == 0:
                    foe.crowd_seen = {}
                    a.state.player.arena_crowd_seen = {}
                store.save_season(w)
                a.state.world = store.get_season()
                a._pill_day = lambda day=day: day  # 一天打 per_day 場（--daily 才有差）
                a.choose("act:arena")
                a.choose("arena:fight:乙")
                fight = a.state.player.arena
                fight.crowd_me = me_side
                while a.state.player.arena is not None:
                    if args.gamble and rng.random() < args.gamble:
                        a.duel_gamble("翻個筋斗踹他屁股", args.rate, ("", ""), crowd=args.label)
                    else:
                        a.choose(f"arena:{bot_policy.duel_move(a, rng, a.state.player.arena)}")
                last = a.state.player.arena_last
                won += last.tier in arena.WIN_TIERS
                hit = [line for line in last.lines if line.startswith(arena_crowd.PREFIX)]
                fired += bool(hit)
                a.choose("arena:back")
        finally:
            arena_crowd.apply = real_apply
            database.close_all()
    return fired / args.fights, won / args.fights, kinds


def main(argv=None) -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="weekend")
    ap.add_argument("--fights", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--scenarios", nargs="+", default=["none", "patron", "both", "mixed", "boo", "champion"])
    ap.add_argument("--share", type=float, default=0.3)
    ap.add_argument("--gamble", type=float, default=0.0)
    ap.add_argument("--rate", type=int, default=30)
    ap.add_argument("--label", default="平常")
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--per-day", type=int, default=10)
    args = ap.parse_args(argv)
    print(f"設定：{args.profile}　每種 {args.fights} 場　放手一搏 {args.gamble}（成功率 {args.rate}、觀眾 {args.label}）"
          f"　{'一天一次照算（一天 ' + str(args.per_day) + ' 場）' if args.daily else '每場清帳'}", flush=True)
    for name in args.scenarios:
        rate, win_on, kinds = run(args, name, True)
        _, win_off, _ = run(args, name, False)
        top = "、".join(f"{k} {n}" for k, n in kinds.most_common() if n)
        print(f"{name:9s} 有場邊事件 {rate * 100:5.1f}%　甲的贏面 開 {win_on * 100:5.1f}% 關 {win_off * 100:5.1f}%"
              f"（差 {(win_on - win_off) * 100:+.1f}）　{top}", flush=True)


if __name__ == "__main__":
    main()
