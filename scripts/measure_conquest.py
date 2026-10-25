"""領地爭奪的量表（減法季批 3b-4；計畫第四節 Task 3b-4、整合設計 4.3「20 人的服一季易手 7～8 次」）：只量不改。

量的是約戰開著的季（rules.jianfa 的 sortie_duel：一天兩次、十分鐘窗、三回合、到時沒人應由假人補位、連假人都沒有守軍迎戰）一季易手幾次。
- 正式內容（--profile week7｜season21），擋模型（OllamaClient.from_config 回 None、ollama_url 指死埠），開季一刻固定在 2026-10-28（週三）
  14:00 台灣（同 2026-10-22 7 天季調整那一次的量法）。
- 20 人：官軍 8、黃巾 8、地方豪強 4（依附兩軍各 2）；每一邊一半是假人（存檔的 bot 有值：照作息 server_bots.is_online 上線，到時沒人應戰時
  能補位），一半是「認真的真人」（bot 是 None，一樣走 bot_policy.take_turn；台灣時間 12:00～13:30、19:30～23:30 在線）。一開始就投靠好、
  站在投靠點。
- 每 --step 秒一輪：先跑一下伺服器排程（Game.for_world(...).world_tick：收到時的約戰、換天、季末），在線的人各做最多 --acts 個動作（每一個
  照伺服器的做法從資料庫重讀、同步、做、存；做不了事就停）。
- 攔下 sortie_duel.open／advance 記每一張約戰（誰貼的、守方是真人、補位的假人、守軍，還是作廢；攻方的結果），攔下 conquest.flip 記易手
  （推滿與攻城戰都算）。
印：每天易手（官軍／黃巾拿下）、整季易手、約戰幾張與分類、攻方勝率、季末還有進度的塊、等級中位。只有數字與陣營，不列名號。
--progress-scale 覆寫 Config.conquest.progress_scale（量「調到多少」用）；--days 只跑前幾天。

執行：.venv/Scripts/python.exe scripts/measure_conquest.py --profile week7 --seed 1 [--progress-scale 12] [--days 7] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import ollama_client  # noqa: E402

ollama_client.OllamaClient.from_config = classmethod(lambda cls, cfg: None)  # 擋模型：一個都不叫

from tianxia import bot_policy, conquest, server_bots, sortie_duel  # noqa: E402
from tianxia.characters import CharacterStore  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.state import BotProfile  # noqa: E402

DAY = 86400
T0 = 1_793_167_200.0  # 2026-10-28（週三）14:00 台灣
LINEUP = [("guan", None)] * 8 + [("huang", None)] * 8 + [("haoqiang", "guan")] * 2 + [("haoqiang", "huang")] * 2
HUMAN_HOURS = ((12 * 60, 13 * 60 + 30), (19 * 60 + 30, 23 * 60 + 30))  # 認真的真人在線的時段（台灣時間，分鐘）


def human_online(now: float) -> bool:
    minute = int((now + server_bots.TZ_OFFSET) % DAY // 60)
    return any(start <= minute < end for start, end in HUMAN_HOURS)


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="week7")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--progress-scale", type=float, default=None)
    ap.add_argument("--days", type=float, default=None)
    ap.add_argument("--step", type=float, default=300.0)
    ap.add_argument("--acts", type=int, default=3)
    ap.add_argument("--json", default=None)
    args = ap.parse_args(argv)

    os.environ["TIANXIA_DB"] = str(Path(tempfile.mkdtemp(prefix="measure-conquest-")) / "tianxia.db")
    content = load_content(ROOT / "content", profile=args.profile)
    content.config.ollama_url = "http://127.0.0.1:9"
    content.config.bot_naming = False
    if args.progress_scale is not None:
        content.config.conquest.progress_scale = args.progress_scale
    world = open_world(Path(os.environ["TIANXIA_DB"]))
    world.seed_first_season(content)
    world.open_season(content, now=T0)
    store = CharacterStore(world.db)
    season = world.get_season_number()

    # ── 攔下約戰與易手（只記數字）──
    posts: Counter = Counter()
    duels: list[dict] = []
    flips: list[tuple[float, str, str, bool]] = []
    real_open, real_advance, real_flip = sortie_duel.open, sortie_duel.advance, conquest.flip

    def open_(shared, **kw):
        posts[kw["attacker"].side] += 1
        return real_open(shared, **kw)

    def advance(shared, cfg, now, candidates_for):
        waiting = {key for key, d in shared.sorties.items() if d.defender is None}
        done = real_advance(shared, cfg, now, candidates_for)
        for d in done:
            kind = ("void" if d.status == "void" else "garrison" if d.defender.garrison
                    else "filled" if d.id in waiting else "answered")
            duels.append({"day": int((now - T0) // DAY), "side": d.attacker.side, "kind": kind,
                          "tier": d.result.tier if d.result is not None else None})
        return done

    def flip(world_state, content_, loc_id, side, note=True):
        if conquest.capturable(content_, loc_id):
            flips.append((world_state.time, loc_id, side, note))
        return real_flip(world_state, content_, loc_id, side, note)

    sortie_duel.open, sortie_duel.advance, conquest.flip = open_, advance, flip

    # ── 20 人 ──
    rng = random.Random(args.seed)
    taken = store.names() | server_bots.reserved_names(content)
    roster: list[tuple[str, BotProfile, bool]] = []
    for i, (faction, ally) in enumerate(LINEUP):
        name = server_bots.make_name(rng, taken)
        taken.add(name)
        game = Game.new(content, name, rng=random.Random(args.seed * 1000 + i), world=world, graduated=True)
        game.client = None
        p = game.state.player
        p.faction, p.ally = faction, ally
        p.location, p.journey = content.scenario.faction(faction).join_at[0], None
        p.tutorial_step = len(content.tutorial.steps)
        bot = i % 2 == 0
        profile = BotProfile(personality=server_bots.pick_personality(rng) if bot else "積極", seed=rng.randrange(2**31),
                             faction=faction, season_number=season)
        if bot:
            p.bot = profile
        game.sync(T0)
        store.save(game.state)
        roster.append((name, profile, bot))

    days = args.days if args.days is not None else content.config.season_days
    end = T0 + days * DAY
    t, turns, started = T0, 0, time.time()
    while t < end:
        with world.action_lock():
            vehicle = Game.for_world(content, world, random.Random(f"{args.seed}|tick|{t}"))
            vehicle.client = None
            vehicle.world_tick(t)
        if world.season_phase() != "running":
            break
        for name, profile, bot in roster:
            if not (server_bots.is_online(profile, t) if bot else human_online(t)):
                continue
            for k in range(args.acts):
                now = t + k * 20
                with world.action_lock():
                    state = store.load(name)
                    game = Game(content, state, random.Random(f"{args.seed}|{name}|{now}"), world)
                    game.client = None
                    game.sync(now)
                    game.state.player.seen_real = now
                    if game.state.world.ended:
                        store.save(game.state)
                        break
                    msgs = bot_policy.take_turn(game, profile, random.Random(f"{args.seed}|turn|{name}|{now}"))
                    store.save(game.state)
                turns += 1
                if not msgs:
                    break
        t += args.step
    with world.action_lock():
        vehicle = Game.for_world(content, world, random.Random(f"{args.seed}|tick|end"))
        vehicle.client = None
        vehicle.world_tick(t + sortie_duel_window(content) + 1)

    states = store.all()
    levels = sorted(s.player.member.level for s in states)
    final = world.get_season()
    open_bars = {loc: {s: round(v) for s, v in conquest.bars(final, loc).items()}
                 for loc in conquest.blocks(content) if conquest.bars(final, loc)}
    by_day: dict[int, Counter] = {}
    for when, _, side, _ in flips:  # 世界秒（開季從 0 起）照 24 小時一段分
        by_day.setdefault(int(when // DAY), Counter())[side] += 1
    kinds = Counter(d["kind"] for d in duels)
    fought = [d for d in duels if d["tier"] is not None]
    report = {
        "profile": args.profile, "seed": args.seed, "progress_scale": content.config.conquest.progress_scale, "days": days,
        "turns": turns, "wall_seconds": round(time.time() - started),
        "flips": len(flips), "flips_by_side": dict(Counter(side for _, _, side, _ in flips)),
        "flips_by_letter": sum(1 for *_, note in flips if not note),
        "flips_by_day": {day: dict(c) for day, c in sorted(by_day.items())},
        "posts": dict(posts), "duels": dict(kinds),
        "attacker_wins": sum(1 for d in fought if d["tier"] in ("big", "win")), "attacker_draws": sum(1 for d in fought if d["tier"] == "draw"),
        "attacker_losses": sum(1 for d in fought if d["tier"] == "lose"), "fought": len(fought),
        "open_bars": open_bars, "level_median": statistics.median(levels) if levels else 0, "level_max": max(levels, default=0),
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def sortie_duel_window(content) -> float:
    return content.config.sortie.window_minutes * 60


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
