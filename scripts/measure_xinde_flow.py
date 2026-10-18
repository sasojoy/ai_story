"""心得的收與花（Joy 2026-10-17 清單第 9 條「心得過剩」）：一季從哪裡攢、花在哪、什麼時候開始只進不出。只量、不改數字。

玩家照 measure_chuangong.py 的「一直在線、體力一有就打」機器人（每 10 步照整季機器人花心得、練、合成、修練）。
每一筆心得的增減照呼叫它的函式記帳（p.stats 換成會記帳的 dict）。
用法：python scripts/measure_xinde_flow.py --seeds 1 2 [--profile weekend] [--online 24] [--mates guanyu zhangfei | --mates]
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure_chuangong as mc  # noqa: E402  （它會把 stdout 包成 UTF-8、把 TIANXIA_DB 設到暫存）

import random  # noqa: E402

from tianxia import bot, sensing, team  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.state import PLAYER  # noqa: E402

SKIP = {"__setitem__", "_note", "<lambda>"}
HOURS = (3, 6, 12, 24, 36, 48, 60)


class Ledger(dict):
    book: collections.Counter
    def __setitem__(self, key, value):
        if key == "xinde":
            before = self.get("xinde", 0)
            delta = value - before
            if delta:
                f = sys._getframe(1)
                names = []
                while f is not None and len(names) < 3:
                    fn = f.f_code.co_filename
                    if "tianxia" in fn and f.f_code.co_name not in SKIP:
                        names.append(f"{Path(fn).stem}.{f.f_code.co_name}")
                    f = f.f_back
                Ledger.book[(delta > 0, " < ".join(names[:2]))] += delta
        super().__setitem__(key, value)


def run(seed, args):
    content = load_content(mc.ROOT / "content", profile=None if args.profile == "none" else args.profile)
    if args.no_buy:
        content.config.legend_xinde_price = 0  # 對照組：沒有以心得換破境丹
    world = open_world(mc.TMP / f"x{seed}{len(args.mates)}{int(args.no_buy)}.db")
    if not world.get_season().storyline:
        world.seed_first_season(content)
    world.open_season(content, now=0)
    game = Game.new(content, f"機器人{seed}", rng=random.Random(seed), world=world, graduated=True)
    game.now = 0
    p = game.state.player
    Ledger.book = collections.Counter()
    p.stats = Ledger(p.stats)
    if args.faction:
        p.faction = args.faction
        p.followers = list(args.followers)
    for cid in args.mates:
        world.try_recruit(cid, p.name)
        ch = content.characters[cid]
        def seed_arts(progress, ch=ch):
            progress.wugong_id, progress.neigong_id = ch.starting_wugong, ch.starting_neigong
        world.update_companion(cid, seed_arts)
        p.team.append(cid)
    rng = random.Random(seed)
    target: dict = {}
    marks = {}
    step = 0
    while not game.state.world.ended and step < 400000:
        if not isinstance(game.state.player.stats, Ledger):
            game.state.player.stats = Ledger(game.state.player.stats)
        step += 1
        choice = None
        if (game.advanced_real / 3600) % 24 < args.online:
            bot.take_pill(game)
            if bot.wants_heal(game):
                game.heal()
            options = [o for o in game.options(odds=False) if o.enabled]
            hop = bot.clinic_hop(game)
            choice = f"move:{hop}" if hop is not None and f"move:{hop}" in {o.id for o in options} else (
                mc.choose(game, options, rng, target) if options else None)
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
        hours = game.advanced_real / 3600
        for h in HOURS:
            if h not in marks and hours >= h:
                inc = sum(v for (pos, _), v in Ledger.book.items() if pos)
                out = -sum(v for (pos, _), v in Ledger.book.items() if not pos)
                pp = game.state.player
                marks[h] = (inc, out, pp.stats.get("xinde", 0), pp.member.level,
                            pp.member.neigong_level, pp.member.wugong_level)
    pp = game.state.player
    for aid in (pp.member.wugong_id, pp.member.neigong_id):
        if aid:
            print(f"  身上 {aid}：{pp.art_quality.get(aid, '?')}・火候 {pp.art_mastery.get(aid, 0)}・丹 {pp.legend_items}", flush=True)
    jue = sum(1 for a, q in pp.art_quality.items() if q == "絕學")
    return Ledger.book, marks, pp.stats.get("xinde", 0), pp.member.level, game.advanced_real / 3600, (pp.legend_bought, jue)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2])
    ap.add_argument("--profile", default="weekend")
    ap.add_argument("--online", type=float, default=24)
    ap.add_argument("--faction", default="guan")
    ap.add_argument("--no-buy", action="store_true", help="關掉以心得換破境丹（對照組）")
    ap.add_argument("--mates", nargs="*", default=["guanyu", "zhangfei"])
    ap.add_argument("--followers", nargs="*", default=["follower_guan_spear", "follower_guan_crossbow"])
    args = ap.parse_args()
    for seed in args.seeds:
        book, marks, left, level, hours, (bought, jue) = run(seed, args)
        inc = sum(v for (pos, _), v in book.items() if pos)
        out = -sum(v for (pos, _), v in book.items() if not pos)
        print(f"種子 {seed}：{hours:.0f} 小時、第 {level} 級　攢 {inc}・花 {out}・剩 {left}　心得換丹 {bought} 枚・季末絕學 {jue} 門")
        print("  收：" + "；".join(f"{k} {v}" for (pos, k), v in book.most_common() if pos and v > 0)[:2000])
        print("  花：" + "；".join(f"{k} {-v}" for (pos, k), v in sorted(book.items(), key=lambda kv: kv[1]) if not pos))
        print("  時間軸（攢, 花, 剩, 等級, 內功成, 武學成）：" + "  ".join(f"{h}h:{v}" for h, v in marks.items()), flush=True)


if __name__ == "__main__":
    main()
