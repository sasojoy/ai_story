"""傳功門下（企劃者 2026-10-14「心得大量溢出」）：心得有沒有地方花、隊伍威力漲多少、決戰份量動不動。只量、不改數字。

玩家是「一直在線、體力一有就打」的機器人（每一下 20 秒，挑此地勝算穩勝、有把握的地方遊歷；跟等級上限 50 那一份量表同一套），
開局就投靠官軍、帶著兩位同伴（--mates，預設關羽、張飛）與兩名部下（--followers，預設持矛、弩手鄉勇）。
每 10 步照整季機器人的 spend_xinde 花心得：先練自己的兩門，再把多出來的傳功（bot.teach：最便宜的一項、留 30 點）。
同一個種子跑兩次：傳功關著（Config.chuangong.enabled = False）與開著，比
- 心得：一季攢了多少、傳功花了多少、季末還剩多少；
- 威力（不看對手）：本人、每位同伴、部下合計、全隊；
- 決戰份量：部下讓強攻、奇襲多幾成（Game._battle_troops，照人數算，傳功不動它）、本人的實力（battle_instance.strength）。
--online 一天在線幾小時（其餘時間只推時間）。

用法：.venv/Scripts/python.exe scripts/measure_chuangong.py --seeds 1 2 [--profile weekend] [--online 24] [--hours 0]
"""
from __future__ import annotations

import argparse
import io
import os
import random
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="measure_chuangong_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")  # 別開到 worktree 的 saves/tianxia.db

from tianxia import atlas, battle_instance, bot, encounter, sensing, team  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.state import PLAYER  # noqa: E402

GOOD = ("穩勝", "有把握")
MARKS = (6, 12, 24, 36, 48, 60)


def best_spot(game, target):
    s, c, w = game.state, game.content, game.world
    m = s.player.member
    saved = (m.neili, m.injury)
    m.neili, m.injury = None, 0.0
    routes = atlas.shortest_routes(s, c)
    best, score = None, -1.0
    for loc in c.locations.values():
        sqs = [c.squads[x] for x in loc.enemies if x in c.squads]
        if not sqs or (loc.id != s.player.location and loc.id not in routes):
            continue
        if not all(team.estimate(s, c, w, q.id) in GOOD for q in sqs):
            continue
        dist = 0 if loc.id == s.player.location else routes[loc.id].minutes
        val = sum(q.exp for q in sqs) / len(sqs) - dist / 60
        if val > score:
            best, score = loc.id, val
    m.neili, m.injury = saved
    return best


def choose(game, options, rng, target):
    ids = [o.id for o in options]
    s = game.state
    hit = [i for i in ids if i.startswith("act:challenge:")]
    if hit:
        return hit[0]
    if s.player.journey is None and not any(i.startswith(("choice:", "sense:", "battle:", "duel:", "event")) for i in ids):
        key = (s.player.member.level // 3, s.player.member.wugong_id)
        if target.get("key") != key:
            target["key"], target["loc"] = key, best_spot(game, target)
        loc = target["loc"]
        if loc and loc != s.player.location:
            r = atlas.shortest_routes(s, game.content).get(loc)
            if r and r.path and f"move:{r.path[0]}" in ids:
                return f"move:{r.path[0]}"
    for pref in ("act:train", "act:explore"):
        hit = [i for i in ids if i.startswith(pref)]
        if hit:
            return hit[0]
    return bot.pick(game, options, rng)


def powers(game):
    """（本人, [每位同伴], 部下合計, 全隊）：不看對手的威力（沒有相剋、路數），氣血係數一律 1。"""
    s, c, w = game.state, game.content, game.world
    arts = team.team_arts(s, c, w)
    mine = encounter.member_power(s.player.member, arts, None, 1.0, team.player_boost(s, c, w))
    mates = [encounter.member_power(w.get_companion(k), arts, None, 1.0, team.mate_boost(s, c, w, k)) for k in s.player.team]
    troops = sum(team.follower_power(s, c, w, f, key) for key, f in team.follower_rows(s, c))
    return mine, mates, troops, mine + sum(mates) + troops


def run(seed, args, teach_on):
    content = load_content(ROOT / "content", profile=None if args.profile == "none" else args.profile)
    content.config.chuangong.enabled = teach_on
    world = open_world(TMP / f"w{seed}{int(teach_on)}.db")
    if not world.get_season().storyline:
        world.seed_first_season(content)
    world.open_season(content, now=0)
    game = Game.new(content, f"機器人{seed}", rng=random.Random(seed), world=world, graduated=True)
    game.now = 0
    p = game.state.player
    p.faction = "guan"
    p.followers = list(args.followers)
    for cid in args.mates:
        world.try_recruit(cid, p.name)
        ch = content.characters[cid]

        def seed_arts(progress, ch=ch):
            progress.wugong_id, progress.neigong_id = ch.starting_wugong, ch.starting_neigong

        world.update_companion(cid, seed_arts)
        p.team.append(cid)
    spent = {"teach": 0}
    real_teach = game.chuangong

    def counted(key, what):
        before = game.state.player.stats.get("xinde", 0)
        out = real_teach(key, what)
        spent["teach"] += before - game.state.player.stats.get("xinde", 0)
        return out

    game.chuangong = counted
    rng = random.Random(seed)
    target: dict = {}
    last, earned, marks = p.stats.get("xinde", 0), 0, {}
    step = 0
    while not game.state.world.ended and (not args.hours or game.advanced_real / 3600 < args.hours) and step < 400000:
        step += 1
        choice = None
        if (game.advanced_real / 3600) % 24 < args.online:
            bot.take_pill(game)
            if bot.wants_heal(game):
                game.heal()
            options = [o for o in game.options(odds=False) if o.enabled]
            hop = bot.clinic_hop(game)
            choice = f"move:{hop}" if hop is not None and f"move:{hop}" in {o.id for o in options} else (
                choose(game, options, rng, target) if options else None)
        if choice is not None and choice.startswith(("act:train", "act:explore", "act:challenge")):
            m = game.state.player.member
            now_hp, cap = team.member_neili(content, m, team.con_of(game.state, content, game.world, PLAYER))
            if now_hp < 0.5 * cap or game.state.player.stamina < 10:
                choice = None
        if choice is not None:
            if choice == sensing.DRAW:
                bot.sense_draw(game, rng)
            else:
                game.choose(choice)
            if step % 10 == 0:
                bot.allocate_points(game, rng)
                bot.spend_xinde(game, rng)
                bot.forge_and_cultivate(game, rng)
            bot.take_bounties(game)
            bot.visit_smith(game)
            bot.visit_market(game)
            bot.feed_mount(game)
            bot.wear_better(game)
            game.advance(20)
        else:
            game.advance(600)
        x = game.state.player.stats.get("xinde", 0)
        if x > last:
            earned += x - last
        last = x
        hours = game.advanced_real / 3600
        for h in MARKS:
            if h not in marks and hours >= h:
                marks[h] = (earned, spent["teach"], x, round(powers(game)[3]), game.state.player.member.level)
    mine, mates, troops, whole = powers(game)
    _, bonus = game._battle_troops()
    weight = battle_instance.strength(content.config.battle, mine)
    return {
        "earned": earned, "teach": spent["teach"], "left": last, "level": game.state.player.member.level,
        "mine": mine, "mates": mates, "troops": troops, "whole": whole, "bonus": bonus, "weight": weight, "marks": marks,
        "mate_arts": [(game.world.get_companion(k).wugong_level, game.world.get_companion(k).neigong_level,
                       dict(game.world.get_companion(k).taught)) for k in p.team],
        "drill": [(d.cheng, d.arm) for d in p.follower_drill],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2])
    ap.add_argument("--profile", default="weekend")
    ap.add_argument("--online", type=float, default=24)
    ap.add_argument("--hours", type=float, default=0)
    ap.add_argument("--mates", nargs="*", default=["guanyu", "zhangfei"])
    ap.add_argument("--followers", nargs="*", default=["follower_guan_spear", "follower_guan_crossbow"])
    ap.add_argument("--only", choices=("on", "off"), default=None, help="只跑傳功開著或關著的那一組")
    args = ap.parse_args()
    for seed in args.seeds:
        for teach_on in (False, True):
            if args.only and (args.only == "on") != teach_on:
                continue
            r = run(seed, args, teach_on)
            print(f"種子 {seed} 傳功{'開' if teach_on else '關'}：第 {r['level']} 級　心得 攢 {r['earned']}・傳功花 {r['teach']}・剩 {r['left']}")
            print(f"   威力 本人 {r['mine']:.0f}・同伴 {'／'.join(f'{v:.0f}' for v in r['mates'])}・部下合計 {r['troops']:.0f}"
                  f"・全隊 {r['whole']:.0f}　決戰 部下 +{r['bonus']:.0%}・本人實力 {r['weight']:.1f}")
            print(f"   同伴（武學成, 內功成, 傳的屬性） {r['mate_arts']}　部下（多練成, 臂力） {r['drill']}")
            print("   時間軸（攢, 傳功花, 剩, 全隊威力, 等級） " + "  ".join(f"{h}h:{v}" for h, v in r["marks"].items()), flush=True)


if __name__ == "__main__":
    main()
