"""坐騎量表（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第十節第 2 項；裝備二）：整季機器人跑幾個種子，比開坐騎與關坐騎。
只量不改；武器、防具照設定開著（兩邊一樣）。

每個種子、坐騎開關各一行：一季走了幾段（步行、趕路、疾行各幾段；包住 mounts.hunger，Game._arrivals 每換一段叫一次，
坐騎關著也叫）；步行、趕路花的遊戲時間與「沒騎馬要花多少」（出發那一刻照 atlas.travel_seconds 與 mounts.pace 算）；趕路、疾行花的
體力與「沒騎馬要花多少」（出發那一刻照 atlas.route_stamina／route_foot_stamina 算）；買了幾匹、花多少銀兩（包住 mounts.buy）；
餵了幾次（包住 mounts.feed，一次吃一個一階素材）；落敗幾場、策馬脫身幾場、保住多少銀兩（包住 Game._lose_silver）；決戰騎著馬上陣
幾場、騎兵平均多幾成（參戰者快照的 cavalry）；季末坐騎與飽足度、一階素材、銀兩、季長、結局。
截殺被跑掉幾次看 scripts/sim_season_one.py 的截殺那一行（整季機器人一個人玩，沒有人截殺他）。

整季機器人平常只步行（Game.move_mode 預設 walk、不存檔）：--gait mix 讓機器人每一步照種子擲一次走法（步行、趕路、疾行各三分之一，
自己一份亂數，不動 Game.rng 與 bot.pick 的那一份；體力不夠的鈕本來就灰掉、bot.pick 不會挑），才量得到省下的體力（設計 5.2 的依據缺口）。
兩組（第十節）：14 天設定（不給 --profile）種子 1～5，加 --season-one 量決戰騎兵；週末設定（--profile weekend --steer）種子 1～5——
週末的機器人一季只走 81～90 段（FB-129），--steer 照 measure_gear 的 _steer 一半的時候照手上的懸賞、軍令走。模型一律不連。
湊整的地方（個數、兩數、百分比）走 mounts.half_up／mounts.pct（.5 進位，不用 round）。

用法：.venv/Scripts/python.exe scripts/measure_mounts.py --seeds 1 2 3 4 5 [--profile weekend --steer] [--gait mix] [--season-one]
"""
from __future__ import annotations

import argparse
import atexit
import io
import itertools
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="measure_mounts_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")  # 別開到 worktree 的 saves/tianxia.db

from tianxia import atlas, bot, bot_policy, bounties, database, mounts, naming, orders  # noqa: E402
from tianxia.content import load_content, profile_line  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

STEER = 0.5  # 同 measure_gear、measure_sanren：一半的時候照手上的事走
GAITS = ("walk", "hurry", "dash")
_RUNS = itertools.count()  # 每跑一次一個新的資料庫檔：同一個行程裡同種子跑兩次，第二次不會接著上一次收了季的世界跑成空的


def _cleanup() -> None:
    """結束時關掉所有資料庫連線再刪暫存資料夾（Windows 上開著的檔刪不掉）。"""
    database.close_all()
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)


def _steer(game, options, rng) -> str | None:
    """照抄 scripts/measure_gear.py 的 _steer（同一個量法；那支腳本一 import 就改 stdout 與 TIANXIA_DB，不能直接 import）。
    合併後 measure_gear 的 _steer 跟這裡不一樣時，照它的實際寫法抄。"""
    if game.state.pending_event or rng.random() >= STEER:
        return None
    s, c = game.state, game.content
    ids = {o.id for o in options}
    here = s.player.location
    work = {b.kind for b in bounties.mine(s, c) if b.location == here}
    if "act:train" in ids and ("strike" in work or orders.win_counts(s, c, s.player.faction, here)):
        return "act:train"
    if "act:explore" in ids and "scout" in work:
        return "act:explore"
    if "act:duty" in ids and orders.duty_counts(s, c, s.player.faction, here):
        return "act:duty"
    places = bounties.targets(s, c) + orders.targets(s, c, s.player.faction)
    hop = bot_policy.next_hop(game, places) if places else None
    move = next((i for i in ids if i.startswith("move:") and i.partition(":")[2].partition(":")[0] == hop), None)
    if move is not None:
        return move
    return "act:train" if "act:train" in ids else None


def run(seed: int, profile: str | None, mounts_on: bool, steer: bool, gait: str, season_one: bool) -> dict:
    content = load_content(ROOT / "content", profile=profile)
    content.config.mounts.enabled = mounts_on
    if season_one:
        content.config.season_one = True
    gaits = random.Random(f"gait|{seed}")
    legs = dict.fromkeys(GAITS, 0)
    sums = dict.fromkeys(("walk_s", "foot_s", "paid", "foot", "bought", "spent", "fed", "losses", "escaped", "kept"), 0.0)
    cavalry: dict[str, float] = {}  # 決戰 id → 本人加入時快照的騎兵加成（沒騎馬是 0）
    real_depart, real_lose = Game._depart, Game._lose_silver
    real_hunger, real_buy, real_feed, original_pick = mounts.hunger, mounts.buy, mounts.feed, bot.pick

    def depart(self, route, mode):
        """出發那一刻（扣體力之前）：這一趟扣多少、沒騎馬要扣多少；步行、趕路花多久、沒騎馬要多久。"""
        s, c = self.state, self.content
        sums["paid"] += atlas.route_stamina(s, c, route, mode)
        sums["foot"] += atlas.route_foot_stamina(s, c, route, mode)
        if mode != "dash" and not atlas.returns_at_once(s, c, route):
            plain = sum(atlas.travel_seconds(leg, mode, pace=1.0) for leg in route.legs)
            sums["foot_s"] += plain
            sums["walk_s"] += plain * mounts.pace(s, c)
        return real_depart(self, route, mode)

    def hunger(state, content_, mode):
        legs[mode] += 1
        return real_hunger(state, content_, mode)

    def buy(state, content_):
        before = state.player.stats.get("silver", 0)
        out = real_buy(state, content_)
        paid = before - state.player.stats.get("silver", 0)
        if paid > 0:
            sums["bought"] += 1
            sums["spent"] += paid
        return out

    def feed(state, content_):
        before = sum(state.player.materials.values())
        out = real_feed(state, content_)
        sums["fed"] += before > sum(state.player.materials.values())
        return out

    def lose(self, record):
        purse = self.state.player.stats.get("silver", 0)
        out = real_lose(self, record)
        sums["losses"] += 1
        if purse // 10 and record.silver == 0:
            sums["escaped"] += 1
            sums["kept"] += purse // 10
        return out

    def pick(game, options, rng):
        steered = _steer(game, options, rng) if steer else None
        return steered if steered is not None else original_pick(game, options, rng)

    def observe(game) -> None:
        if gait == "mix":
            game.set_move_mode(gaits.choice(GAITS))  # 下一步的選單照這種走法列「前往」
        battle = game.world.get_battle()
        me = battle.participants.get(game.state.player.name) if battle is not None else None
        if me is not None:
            cavalry.setdefault(battle.battle_id, me.cavalry)

    def refuse(*args, **kwargs):
        raise RuntimeError("量測不連模型")

    # engine 照模組屬性呼叫 mounts.hunger、mounts.buy、mounts.feed，照類別找 Game._depart、Game._lose_silver，
    # bot.play_season 照模組全域呼叫 pick：都換得到
    with mock.patch.object(naming, "propose", lambda *a, **k: (None, "")), \
            mock.patch.object(naming, "pick", lambda *a, **k: (None, "")), \
            mock.patch.object(OllamaClient, "chat_structured", refuse), mock.patch.object(OllamaClient, "chat_text", refuse), \
            mock.patch("requests.post", refuse), mock.patch("requests.get", refuse), \
            mock.patch.object(Game, "_depart", depart), mock.patch.object(Game, "_lose_silver", lose), \
            mock.patch.object(mounts, "hunger", hunger), mock.patch.object(mounts, "buy", buy), \
            mock.patch.object(mounts, "feed", feed), mock.patch.object(bot, "pick", pick):
        game = bot.play_season(content, seed, world=open_world(TMP / f"s{seed}-{int(mounts_on)}-{next(_RUNS)}.db"), observe=observe)
    p = game.state.player
    season = game.state.world
    rode = [v for v in cavalry.values() if v > 0]
    return {
        "legs": legs, "walk_h": sums["walk_s"] / 3600, "foot_h": sums["foot_s"] / 3600,
        "paid": mounts.half_up(sums["paid"]), "foot": mounts.half_up(sums["foot"]),
        "bought": mounts.half_up(sums["bought"]), "spent": mounts.half_up(sums["spent"]),
        "fed": mounts.half_up(sums["fed"]), "losses": mounts.half_up(sums["losses"]),
        "escaped": mounts.half_up(sums["escaped"]), "kept": mounts.half_up(sums["kept"]),
        "fought": len(cavalry), "rode": len(rode), "cavalry": sum(rode) / len(rode) if rode else None,
        "mount": f"{p.mount.name}（{mounts.WEAR_WORD} {p.mount.edge}）" if p.mount else "—",
        "tier1": sum(n for mid, n in p.materials.items() if content.materials[mid].tier == 1),
        "silver": p.stats.get("silver", 0), "hours": season.time / 3600, "ending": season.ending_id or "—",
    }


def _saved(spent: float, plain: float) -> str:
    return "—" if plain <= 0 else mounts.pct(1 - spent / plain)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument("--profile", default=None)
    parser.add_argument("--steer", action="store_true", help="一半的時候照手上的懸賞、軍令走（週末那一組用，同 measure_gear）")
    parser.add_argument("--gait", choices=("walk", "mix"), default="walk", help="mix：每一步照種子擲一次走法（步行、趕路、疾行）")
    parser.add_argument("--season-one", action="store_true", help="打開第一季開關（14 天設定量決戰騎兵用）")
    args = parser.parse_args()
    content = load_content(ROOT / "content", profile=args.profile)
    extra = ("（照手上的事走）" if args.steer else "") + ("（走法混著用）" if args.gait == "mix" else "") \
        + ("（第一季開關開）" if args.season_one else "")
    print(profile_line(content, args.profile) + extra, flush=True)
    for seed in args.seeds:
        for on in (False, True):
            r = run(seed, args.profile, on, args.steer, args.gait, args.season_one)
            legs = r["legs"]
            cav = "—" if r["cavalry"] is None else "+" + mounts.pct(r["cavalry"])
            print(f"種子 {seed} 坐騎{'開' if on else '關'}：走了 {sum(legs.values())} 段（步行 {legs['walk']}、趕路 {legs['hurry']}、"
                  f"疾行 {legs['dash']}）、走路花 {r['walk_h']:.1f} 小時（沒騎馬要 {r['foot_h']:.1f}，省 {_saved(r['walk_h'], r['foot_h'])}）、"
                  f"趕路疾行體力 {r['paid']}（沒騎馬要 {r['foot']}，省 {_saved(r['paid'], r['foot'])}）、"
                  f"買馬 {r['bought']} 匹（{r['spent']} 兩）、餵 {r['fed']} 次、落敗 {r['losses']} 場（策馬脫身 {r['escaped']} 場、"
                  f"保住 {r['kept']} 兩）、決戰騎著馬 {r['rode']}／{r['fought']} 場（騎兵平均 {cav}）、季末坐騎 {r['mount']}、"
                  f"一階素材 {r['tier1']}、銀兩 {r['silver']}、季長 {r['hours']:.1f} 小時（世界時間）、結局 {r['ending']}", flush=True)


if __name__ == "__main__":
    main()
