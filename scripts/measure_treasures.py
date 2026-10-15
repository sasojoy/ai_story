"""寶物量表（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第十節第 3 項；裝備三）：整季機器人跑幾個種子，比開寶物與關寶物。
只量不改；武器、防具、坐騎照設定開著（兩邊一樣；良駒、名駒的來源是這一批，件數照記）。

每個種子、寶物開關各一行：一季拿到幾件寶物、各從哪個來源（懸賞的重賞、挑戰本人、名將贈禮、奇遇：包住 treasures.bounty_prize、
challenge_drop、gifts_due、grant_effect，前後比身上、裝備庫、寄放的東西多了哪幾件）、良駒幾匹、名駒幾匹、換成銀兩幾次（掉落池都有了、
奇遇給的那件已經有了）、寄放過幾件、補發了幾件（包住 treasures.deliver_held；整季機器人只 advance、不 sync，Game.advance 也補，
所以補得回來）、換寶物幾次（包住 Game.wield_weapon，數寶物那一欄換成的；設計 2.3 要記的）、季末身上的寶物。
效果實際多給了多少（設計第十節第 3 項），只在真正結算的地方數，不數 treasures.amount 被問了幾次（畫面每次組選單都會問，數字會灌水）：
修練升品成功幾次（包住 Game.cultivate，前後比 art_quality 變了幾門）、多掉的素材幾個（包住 treasures.extra_drop，回的不是 None 就是多掉一個）、
撿到幾枚破境丹（包住 Game._legend_find，回的不是空的就是撿到一枚）、打贏拿到的心得與經驗合計（印成「勝場心得」「勝場經驗」；
只算遊歷、探索野怪、劇情戰〔含挑戰本人〕這三種走 _battle_rewards 的仗，切磋、截殺、頭目戰的獎勵不吃寶物，不算進來；
state.battles 只留最近 20 場，在 observe 裡照流水號逐步累計）——都是寶物開、關兩行對照著看。量不到的照實寫：閉關心得（整季機器人
不閉關，設計 6.2 的依據欄）、求見提早幾天（機器人不刻意求見）。季末等級、銀兩、季長、結局。一個機器人獨佔一個資料庫，懸賞的重賞一定是
它第一個交差，所以那一欄是全服的上限。

兩組（第十節）：14 天設定加 --season-one（挑戰本人現在只在第一季規則開著時有；設計 6.4 要開到每一季，是另一份設計）種子 1～5；
週末設定（--profile weekend --steer）種子 1～5。模型一律不連。

用法：.venv/Scripts/python.exe scripts/measure_treasures.py --seeds 1 2 3 4 5 [--season-one] [--profile weekend --steer]
"""
from __future__ import annotations

import argparse
import atexit
import io
import itertools
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path
from unittest import mock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="measure_treasures_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")  # 別開到 worktree 的 saves/tianxia.db

from tianxia import bot, bot_policy, bounties, database, naming, orders, treasures  # noqa: E402
from tianxia.content import load_content, profile_line  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

STEER = 0.5  # 同 measure_gear、measure_sanren：一半的時候照手上的事走
SOURCES = {"bounty_prize": "懸賞", "challenge_drop": "挑戰本人", "gifts_due": "名將", "grant_effect": "奇遇"}
REWARD_KINDS = ("train", "wild", "event")  # 走 Game._battle_rewards 的三種仗（寶物的打贏心得、經驗只掛在這裡）
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
    if "scout" in work and (choice := bot.explore_choice(ids)) is not None:  # 打探：三選一開著時找素材（出陣探索與地盤）
        return choice
    if "act:duty" in ids and orders.duty_counts(s, c, s.player.faction, here):
        return "act:duty"
    places = bounties.targets(s, c) + orders.targets(s, c, s.player.faction)
    hop = bot_policy.next_hop(game, places) if places else None
    move = next((i for i in ids if i.startswith("move:") and i.partition(":")[2].partition(":")[0] == hop), None)
    if move is not None:
        return move
    return "act:train" if "act:train" in ids else None


def _gear(state) -> dict:
    """身上、裝備庫、寄放的每一件（id → 那一件）：來源函式前後各照一次，多出來的就是這一下拿到的。"""
    p = state.player
    items = [p.weapon, p.armor, p.mount, p.treasure, *p.rack, *p.held_gear]
    return {item.id: item for item in items if item is not None}


def run(seed: int, profile: str | None, on: bool, steer: bool, season_one: bool) -> dict:
    content = load_content(ROOT / "content", profile=profile)
    content.config.treasures.enabled = on
    if season_one:
        content.config.season_one = True
    got = {name: Counter() for name in SOURCES}  # 來源 → 「treasure」「good」「named」「silver」「held」
    count: Counter = Counter()  # swaps、arrived、upgrades、extra、pills、xinde、exp
    seen: set[int] = set()
    real = {name: getattr(treasures, name) for name in (*SOURCES, "extra_drop", "deliver_held")}
    real_wield, real_cultivate, real_legend, original_pick = Game.wield_weapon, Game.cultivate, Game._legend_find, bot.pick

    def wrap(name):
        def inner(state, *args, **kwargs):
            before, silver, held = _gear(state), state.player.stats.get("silver", 0), len(state.player.held_gear)
            out = real[name](state, *args, **kwargs)
            for item in (item for iid, item in _gear(state).items() if iid not in before):
                got[name]["treasure" if item.slot == "treasure" else "named" if item.tier == 3 else "good"] += 1
            if name != "gifts_due" and state.player.stats.get("silver", 0) > silver:
                got[name]["silver"] += 1  # 掉落池都有了、奇遇那件已經有了（懸賞本身的賞銀不在這個包裝裡）
            got[name]["held"] += len(state.player.held_gear) - held
            return out
        return inner

    def extra_drop(*args, **kwargs):
        out = real["extra_drop"](*args, **kwargs)
        count["extra"] += out is not None  # 寶物「打贏多掉一個素材」真的多掉了一個
        return out

    def deliver_held(state, content_):
        held = len(state.player.held_gear)
        out = real["deliver_held"](state, content_)
        count["arrived"] += held - len(state.player.held_gear)  # 寄放的補發了幾件
        return out

    def wield(self, item_id):
        out = real_wield(self, item_id)
        if item_id.startswith("寶:") and out and out[0].startswith("你換上了"):
            count["swaps"] += 1
        return out

    def cultivate(self, art_id, *args, **kwargs):
        before = dict(self.state.player.art_quality)
        out = real_cultivate(self, art_id, *args, **kwargs)
        after = self.state.player.art_quality
        count["upgrades"] += sum(1 for key, quality in after.items() if before.get(key) != quality)  # 修練升了品
        return out

    def legend_find(self, rng=None):  # 探索三選一傳自己的亂數（出陣探索與地盤），舊的探索不傳
        out = real_legend(self, rng)
        count["pills"] += bool(out)  # 探索撿到一枚破境丹
        return out

    def pick(game, options, rng):
        steered = _steer(game, options, rng) if steer else None
        return steered if steered is not None else original_pick(game, options, rng)

    def observe(game) -> None:
        for b in sorted((b for b in game.state.battles if b.id not in seen), key=lambda b: b.id):
            seen.add(b.id)
            if b.kind in REWARD_KINDS and b.tier in ("大勝", "險勝"):
                count["xinde"] += b.xinde
                count["exp"] += b.exp

    def refuse(*args, **kwargs):
        raise RuntimeError("量測不連模型")

    # engine、bounties、rules 照模組屬性呼叫 treasures 的四種來源、extra_drop、deliver_held；Game.wield_weapon、cultivate、_legend_find
    # 照類別找；bot.play_season 照模組全域呼叫 pick：都換得到
    patches = [mock.patch.object(treasures, name, wrap(name)) for name in SOURCES]
    with mock.patch.object(naming, "propose", lambda *a, **k: (None, "")), \
            mock.patch.object(naming, "pick", lambda *a, **k: (None, "")), \
            mock.patch.object(OllamaClient, "chat_structured", refuse), mock.patch.object(OllamaClient, "chat_text", refuse), \
            mock.patch("requests.post", refuse), mock.patch("requests.get", refuse), \
            mock.patch.object(treasures, "extra_drop", extra_drop), mock.patch.object(treasures, "deliver_held", deliver_held), \
            mock.patch.object(Game, "wield_weapon", wield), mock.patch.object(Game, "cultivate", cultivate), \
            mock.patch.object(Game, "_legend_find", legend_find), \
            mock.patch.object(bot, "pick", pick), patches[0], patches[1], patches[2], patches[3]:
        game = bot.play_season(content, seed, world=open_world(TMP / f"s{seed}-{int(on)}-{next(_RUNS)}.db"), observe=observe)
    p = game.state.player
    season = game.state.world
    return {
        "got": got, **{key: count[key] for key in ("swaps", "arrived", "upgrades", "extra", "pills", "xinde", "exp")},
        "treasure": p.treasure.name if p.treasure else "—", "level": p.member.level,
        "silver": p.stats.get("silver", 0), "hours": season.time / 3600, "ending": season.ending_id or "—",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument("--profile", default=None)
    parser.add_argument("--steer", action="store_true", help="一半的時候照手上的懸賞、軍令走（週末那一組用，同 measure_gear）")
    parser.add_argument("--season-one", action="store_true", help="打開第一季開關（14 天設定量挑戰本人掉寶物用）")
    args = parser.parse_args()
    content = load_content(ROOT / "content", profile=args.profile)
    extra = ("（照手上的事走）" if args.steer else "") + ("（第一季開關開）" if args.season_one else "")
    print(profile_line(content, args.profile) + extra, flush=True)
    for seed in args.seeds:
        for on in (False, True):
            r = run(seed, args.profile, on, args.steer, args.season_one)
            got = r["got"]
            by = "、".join(f"{label} {got[name]['treasure']}" for name, label in SOURCES.items())
            total = sum(got[name]["treasure"] for name in SOURCES)
            good = sum(got[name]["good"] for name in SOURCES)
            named = sum(got[name]["named"] for name in SOURCES)
            silver = sum(got[name]["silver"] for name in SOURCES)
            held = sum(got[name]["held"] for name in SOURCES)
            print(f"種子 {seed} 寶物{'開' if on else '關'}：寶物 {total} 件（{by}）、良駒 {good} 匹、名駒 {named} 匹、"
                  f"換成銀兩 {silver} 次、寄放 {held} 件、補發 {r['arrived']} 件、換寶物 {r['swaps']} 次、季末寶物 {r['treasure']}、"
                  f"升品 {r['upgrades']} 次、多掉素材 {r['extra']} 個、破境丹 {r['pills']} 枚、"
                  f"勝場心得 {r['xinde']}、勝場經驗 {r['exp']}、等級 {r['level']}、銀兩 {r['silver']}、"
                  f"季長 {r['hours']:.1f} 小時（世界時間）、結局 {r['ending']}", flush=True)


if __name__ == "__main__":
    main()
