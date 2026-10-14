"""變強之後還有沒有挑戰（企劃者 2026-10-14「10 幾級都能把所有歷史武將跟所有事件打敗，根本不會輸」）：只量、不改數字。

玩家照 measure_chuangong 那一套「一直在線、體力一有就打」的機器人練（官軍），三種隊伍：
- solo：沒有同伴、部下；
- team：兩位同伴（關羽、張飛）兩名部下，傳功關著；
- taught：同上，傳功開著（bot.teach 把心得傳光）。
練到 10、15、20、30、40 級各停一下，照真的規則算（不擲亂數，2000 次模擬）：
- 挑戰大勢人物本人（開季聲威的難度）：最弱、中位、最強那一位的贏面；大場面對手（toumu、shoumu、fanjianglong）、這一刻摸得到最難的遊歷對手；
- 頭目戰：最難那一隻（照份量與職位；招一半看架勢一半亂出，不放手一搏）的大勝＋險勝機會；
- 事件檢定：正式內容每一個檢定照本人此刻的屬性算成功率，平均與 ≥90% 的佔幾成。
贏面＝大勝＋險勝（勝算那一套，氣血當滿的），對手的屬性與一門打不遍不算（大場面還有模型的 ±15，也不算）。

用法：.venv/Scripts/python.exe scripts/measure_difficulty.py --seeds 1 2 [--profile weekend] [--kinds solo team taught] [--rise on|off]
（--rise off 是修前：江湖水漲關著；人物的難度照開季聲威，練功的走法不打人物）
"""
from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
TMP = Path(tempfile.mkdtemp(prefix="measure_difficulty_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")

from tianxia import bot, duel as duel_rules, encounter, rise, rules, sensing, team  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.state import PLAYER, DuelState  # noqa: E402

import measure_chuangong as grind  # noqa: E402  同一套練功的走法（它把 stdout 包成 UTF-8，這裡不再包一次）

LEVELS = (10, 15, 20, 30, 40)
BIG = ("toumu", "shoumu", "fanjianglong")
RUNS = 2000


def win_rate(power: float, difficulty: float, mods=None) -> float:
    rng = random.Random(7)
    wins = 0
    for _ in range(RUNS):
        r = encounter.resolve_encounter(power, difficulty, rng, mods=mods)
        wins += r.tier in ("大勝", "險勝")
    return wins / RUNS


def team_power_vs(game, squad_id: str, difficulty: float | None = None) -> float:
    s, c, w = game.state, game.content, game.world
    squad = c.squads[squad_id]
    if difficulty is not None:
        squad = squad.model_copy(update={"difficulty": difficulty})
    return team.power_vs(s, c, w, squad, fresh=True)  # 養好傷再上陣的那一份（練功的走法常常帶著傷）


def mods_of(game):
    from tianxia import traits
    s, c, w = game.state, game.content, game.world
    return team.trait_mods(c, traits.loadout(s, c, w))


def figures_base(game, fid):
    from tianxia import figures
    return figures.difficulty(game.state, game.content, fid)


def duel_rate(game, boss_id: str) -> float:
    c = game.content
    boss = c.duels[boss_id]
    cfg = c.config.duel
    now, cap = game._player_hp_and_cap()
    rng = random.Random(11)
    wins = 0
    foe_idx = duel_rules.foe_index(boss, game.state.player.faction)
    power, scores, role = game._battle_power(), game._battle_scores(mounted=False), game._battle_role()
    for _ in range(RUNS // 4):
        d = DuelState(boss=boss.id, foe=foe_idx, edge=cfg.start, hp=cap, hp_cap=cap, hp_start=cap,
                      power=power, scores=scores, role=role, difficulty=rise.duel(c, boss.difficulty, power))
        foe = boss.foes[d.foe]
        duel_rules.roll_next(d, foe, cfg, rng)
        while True:
            shown = duel_rules.shown_move(d)
            if rng.random() < 0.5 and shown:
                move = next(m for m in duel_rules.MOVES if duel_rules.BEATS[m] == shown)
            else:
                move = rng.choice(duel_rules.MOVES)
            duel_rules.exchange(d, boss, move, cfg, c.config.battle, rng)
            d.round += 1
            tier = duel_rules.verdict(d, boss, cfg)
            if tier is not None:
                wins += tier in ("大勝", "險勝")
                break
            duel_rules.roll_next(d, foe, cfg, rng)
    return wins / (RUNS // 4)


def checks(content):
    out = []
    for ev in content.events.values():
        for ch in ev.choices:
            if ch.check is not None:
                out.append(ch.check)
    return out


def train_squads(game):
    """這一刻開放的地點裡最難的遊歷對手（敵人池）。"""
    c = game.content
    best = None
    for loc in c.locations.values():
        for sid in loc.enemies:
            sq = c.squads.get(sid)
            if sq and (best is None or sq.difficulty > c.squads[best].difficulty):
                best = sid
    return best


def snapshot(game) -> dict:
    s, c, w = game.state, game.content, game.world
    mods = mods_of(game)
    figs = []
    for fid, fig in c.figures.items():
        squad = game._figure_squad(fid)  # 開季聲威（練功的走法不打人物）、江湖水漲開著就浮上來
        power = team_power_vs(game, fig.squad, squad.difficulty)
        again = rise.big(c, figures_base(game, fid), team.power_vs(s, c, w, squad, fresh=True), 2)  # 這一季打贏他兩次之後
        figs.append((round(squad.difficulty), win_rate(power, squad.difficulty, mods), fig.name, win_rate(power, again, mods)))
    figs.sort()
    big = {}
    for sid in BIG:
        squad = game._story_squad(c.squads[sid])
        big[sid] = win_rate(team_power_vs(game, sid, squad.difficulty), squad.difficulty, mods)
    hard = train_squads(game)
    hard_duel = max(c.duels.values(), key=lambda b: b.difficulty).id
    rates = [rules.check_chance(ch, s, c, w) for ch in checks(c)]
    stats = {k: team.check_value(s, c, w, PLAYER, k) for k in ("str", "agi", "con", "wis")}
    mine, mates, troops, whole = grind.powers(game)
    return {
        "level": s.player.member.level, "mine": mine, "whole": whole,
        "fig_low": figs[0], "fig_mid": figs[len(figs) // 2], "fig_high": figs[-1],
        "fig_all_win": sum(1 for f in figs if f[1] >= 0.9) / len(figs),
        "big": big, "hard_train": (hard, c.squads[hard].difficulty, win_rate(team_power_vs(game, hard), c.squads[hard].difficulty, mods)),
        "duel": (hard_duel, duel_rate(game, hard_duel)),
        "ev_mean": statistics.mean(rates), "ev_90": sum(1 for r in rates if r >= 0.9) / len(rates),
        "stats": stats,
    }


def run(seed, args, kind):
    content = load_content(ROOT / "content", profile=None if args.profile == "none" else args.profile)
    content.config.chuangong.enabled = kind == "taught"
    content.config.rise.enabled = args.rise == "on"
    world = open_world(TMP / f"w{seed}{kind}.db")
    if not world.get_season().storyline:
        world.seed_first_season(content)
    world.open_season(content, now=0)
    game = Game.new(content, f"機器人{seed}", rng=random.Random(seed), world=world, graduated=True)
    game.now = 0
    p = game.state.player
    p.faction = "guan"
    if kind != "solo":
        p.followers = list(grind_args.followers)
        for cid in grind_args.mates:
            world.try_recruit(cid, p.name)
            ch = content.characters[cid]

            def seed_arts(progress, ch=ch):
                progress.wugong_id, progress.neigong_id = ch.starting_wugong, ch.starting_neigong

            world.update_companion(cid, seed_arts)
            p.team.append(cid)
    rng = random.Random(seed)
    target: dict = {}
    snaps = {}
    step = 0
    while not game.state.world.ended and step < 400000 and len(snaps) < len(LEVELS):
        step += 1
        lv = game.state.player.member.level
        for want in LEVELS:
            if want not in snaps and lv >= want:
                snaps[want] = snapshot(game)
        choice = None
        bot.take_pill(game)
        if bot.wants_heal(game):
            game.heal()
        options = [o for o in game.options(odds=False) if o.enabled and not o.id.startswith("act:challenge")]  # 挑戰本人另外算
        hop = bot.clinic_hop(game)
        choice = f"move:{hop}" if hop is not None and f"move:{hop}" in {o.id for o in options} else (
            grind.choose(game, options, rng, target) if options else None)
        if choice is not None and choice.startswith(("act:train", "act:explore", "explore:", "act:challenge")):
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
    return snaps


class _GrindArgs:
    mates = ["guanyu", "zhangfei"]
    followers = ["follower_guan_spear", "follower_guan_crossbow"]


grind_args = _GrindArgs()


def pct(x: float) -> str:
    return f"{x:.0%}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2])
    ap.add_argument("--profile", default="weekend")
    ap.add_argument("--kinds", nargs="+", default=["solo", "team", "taught"])
    ap.add_argument("--rise", choices=("on", "off"), default="on", help="江湖水漲開著（修後）或關著（修前）")
    args = ap.parse_args()
    for kind in args.kinds:
        for seed in args.seeds:
            snaps = run(seed, args, kind)
            print(f"== {kind} 種子 {seed}", flush=True)
            for lv, r in sorted(snaps.items()):
                lo, mid, hi = r["fig_low"], r["fig_mid"], r["fig_high"]
                big = "・".join(f"{k} {pct(v)}" for k, v in r["big"].items())
                ht = r["hard_train"]
                st = "/".join(f"{v:.0f}" for v in r["stats"].values())
                print(f"  {lv:>2} 級（實 {r['level']}）威力 本人 {r['mine']:.0f} 全隊 {r['whole']:.0f}｜人物 "
                      f"{lo[2]}{lo[0]} {pct(lo[1])}・{mid[2]}{mid[0]} {pct(mid[1])}・{hi[2]}{hi[0]} {pct(hi[1])}"
                      f"（打贏兩次後 {pct(hi[3])}）"
                      f"（≥90% 的 {pct(r['fig_all_win'])}）｜大場面 {big}｜遊歷最難 {ht[0]}{ht[1]} {pct(ht[2])}"
                      f"｜頭目 {r['duel'][0]} {pct(r['duel'][1])}｜事件 平均 {pct(r['ev_mean'])}・≥90% {pct(r['ev_90'])}"
                      f"（臂身根悟 {st}）", flush=True)


if __name__ == "__main__":
    main()
