"""裝備量表（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第十節；裝備一：防具那一項）：整季機器人跑幾個種子，
比開防具與關防具。只量不改；武器照設定開著（兩邊一樣），坐騎、寶物固定關著。

開頭先印一行對照：照設計 4.1 的算法（一場扣上限的 Config.encounter_neili_loss 那幾成，不含身法與回血），一階下品對上內功
那件防具讓一條氣血從撐幾場變成幾場。

每個種子、防具開關各一行：遊歷與野怪的場數與勝率；一季掉的氣血與累積的內傷（只算本人：包住 team.take_encounter_toll 量前後，
同伴不算）；療傷花的銀兩（包住 team.heal）；穿著防具打了幾場、其中硬仗幾場；硬仗（險勝、僵持、落敗）的場數與「一條氣血撐幾場硬仗」
（硬仗那一刻的氣血上限合計 ÷ 硬仗掉的氣血合計）；硬仗之後緊接著再打的那一場的勝率（連續硬仗：防具少扣的氣血讓氣血係數維持得
比較高，設計 2.1、4.1）；修了幾次防具、鐵匠鋪花在防具上的銀兩（包住 armor.buy、armor.repair）；季末身上的防具、一階素材、銀兩、
季長與結局。
防具打造（打造第一批）：打了幾件防具與品質分布（包住 smithing.forge，只算打出來是防具的）、其中幾件名器、淬了幾次防具（包住
smithing.temper，只算 slot 是 armor、淬煉次數真的多了的）；「防具花」含打造與淬煉的銀兩。從打造第一批起整季機器人兵器的事做完會打
防具、淬防具，防具開那一行的數字跟裝備一量的不能直接比。
**防具開那一行的硬仗、一條氣血撐幾場、硬仗之後的勝率只算穿著防具的仗**（toll 包裝在開打那一刻記下身上有沒有防具）：整季機器人
先在兵器頁花 40 兩買兵器（開局 50 兩），防具要晚很多才買得起；買之前打的仗混進來的話，硬仗打在買防具之前時開、關兩行會一模一樣，
量不到「有防具時」的差別。防具關那一行全算。這幾項都從 toll 包裝算（遊歷、探索野怪、挑戰本人每一場都走 take_encounter_toll），
所以含挑戰本人；掉的氣血、內傷照整季算。
遊歷野怪的場數與勝率同 measure_weapons：state.battles 只留最近 20 場，所以在 observe 裡照流水號逐步累計新出現的戰報。

兩組（設計第十節）：14 天設定（不給 --profile）種子 1～5；週末設定（--profile weekend --steer）種子 1～5——週末的機器人一季只打
9～29 場（FB-129），--steer 照 measure_sanren._steer 一半的時候照手上的懸賞、軍令走，手上沒事就在這裡遊歷。模型一律不連。

用法：.venv/Scripts/python.exe scripts/measure_gear.py --seeds 1 2 3 4 5 [--profile weekend --steer]
"""
from __future__ import annotations

import argparse
import atexit
import io
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
TMP = Path(tempfile.mkdtemp(prefix="measure_gear_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")  # 別開到 worktree 的 saves/tianxia.db

from tianxia import armor, bot, bot_policy, bounties, database, naming, orders, smithing, team  # noqa: E402
from tianxia.content import load_content, profile_line  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.state import PLAYER  # noqa: E402

STEER = 0.5  # 同 measure_sanren：一半的時候照手上的事走
HARD = ("險勝", "僵持", "落敗")
WINS = ("大勝", "險勝")


def _cleanup() -> None:
    """結束時關掉所有資料庫連線再刪暫存資料夾（Windows 上開著的檔刪不掉）。"""
    database.close_all()
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)


def _steer(game, options, rng) -> str | None:
    """照抄 scripts/measure_sanren.py 的 _steer（同一個量法；那支腳本一 import 就改 stdout 與 TIANXIA_DB，不能直接 import）。"""
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


def run(seed: int, profile: str | None, armor_on: bool, steer: bool) -> dict:
    content = load_content(ROOT / "content", profile=profile)
    content.config.armor.enabled = armor_on
    content.config.mounts.enabled = False  # 防具那一項只比防具：坐騎固定關著，數字才跟裝備一量的對得上（坐騎看 measure_mounts）
    content.config.treasures.enabled = False  # 只比這一欄：寶物固定關著，數字才跟前幾批量的對得上（寶物看 measure_treasures）
    seen: set[int] = set()
    count = dict.fromkeys(("fights", "wins", "armored", "armored_hard", "hard", "after_hard", "after_hard_wins",
                           "repairs", "armor_silver", "heal_silver", "forged", "named", "tempered"), 0)
    grades: Counter = Counter()
    sums = {"hp": 0.0, "injury": 0.0, "hard_hp": 0.0, "hard_cap": 0.0}
    last: dict = {"hard": False}  # 上一場（算進來的）是不是硬仗
    real_toll, real_heal, real_buy, real_repair, original_pick = team.take_encounter_toll, team.heal, armor.buy, armor.repair, bot.pick
    real_forge, real_temper = smithing.forge, smithing.temper

    def toll(state, content_, world, tier, *, wild=False, share=1.0):
        """包住 team.take_encounter_toll：本人這一場掉了多少氣血、多了多少內傷、開打時身上有沒有防具。
        防具開的那一季只拿穿著防具的仗算硬仗、一條氣血撐幾場、硬仗之後的勝率（買防具之前打的不算防具的功勞）；防具關的那一季全算。"""
        member = state.player.member
        con = team.con_of(state, content_, world, PLAYER)
        before, cap = team.member_neili(content_, member, con)
        injury = member.injury
        armored = state.player.armor is not None  # 開打那一刻：這一場扣血時吃不吃得到防具
        out = real_toll(state, content_, world, tier, wild=wild, share=share)
        lost = max(0.0, before - team.member_neili(content_, member, con)[0])
        sums["hp"] += lost
        sums["injury"] += member.injury - injury
        hard = tier in HARD
        count["armored"] += armored
        count["armored_hard"] += armored and hard
        counted = armored or not armor_on
        if counted and last["hard"]:  # 硬仗之後緊接著再打的那一場：兩場都要算得進來
            count["after_hard"] += 1
            count["after_hard_wins"] += tier in WINS
        last["hard"] = counted and hard
        if counted and hard:
            count["hard"] += 1
            sums["hard_hp"] += lost
            sums["hard_cap"] += cap
        return out

    def paid(state, before: int) -> int:
        return max(0, before - state.player.stats.get("silver", 0))

    def heal(state, content_, member, where=None):
        before = state.player.stats.get("silver", 0)
        out = real_heal(state, content_, member, where)
        count["heal_silver"] += paid(state, before)
        return out

    def buy(state, content_, attribute):
        before = state.player.stats.get("silver", 0)
        out = real_buy(state, content_, attribute)
        count["armor_silver"] += paid(state, before)
        return out

    def repair(state, content_):
        before = state.player.stats.get("silver", 0)
        out = real_repair(state, content_)
        cost = paid(state, before)
        if cost:
            count["repairs"] += 1
            count["armor_silver"] += cost
        return out

    def forge(state, content_, world, kind, main, aux, *args, **kwargs):
        """包住 smithing.forge：打出來是防具的才算（兵器打造看 measure_weapons），工錢記進防具花。"""
        before = state.player.stats.get("silver", 0)
        item, msgs = real_forge(state, content_, world, kind, main, aux, *args, **kwargs)
        if item is not None and item.slot == "armor":
            count["forged"] += 1
            count["named"] += item.secret is not None and not item.original and item.copy_of is None  # 神器原品與仿品不算名器（同 measure_secrets.py）
            grades[item.quality] += 1
            count["armor_silver"] += paid(state, before)
        return item, msgs

    def temper(state, content_, slot="weapon"):
        """包住 smithing.temper：淬的是防具、淬煉次數真的多了才算，工錢記進防具花。"""
        before, worn = state.player.stats.get("silver", 0), state.player.armor
        tempers = worn.tempers if worn is not None else 0
        out = real_temper(state, content_, slot)
        if slot == "armor" and worn is not None and worn.tempers > tempers:
            count["tempered"] += 1
            count["armor_silver"] += paid(state, before)
        return out

    def pick(game, options, rng):
        steered = _steer(game, options, rng) if steer else None
        return steered if steered is not None else original_pick(game, options, rng)

    def observe(game) -> None:
        """遊歷野怪的場數與勝率（整季、不分有沒有防具）。硬仗之後的勝率在 toll 包裝裡算（要知道開打時有沒有穿防具）。"""
        for b in sorted((b for b in game.state.battles if b.id not in seen), key=lambda b: b.id):
            seen.add(b.id)
            if b.kind not in ("train", "sortie", "wild"):  # 出陣的攻（出陣探索與地盤）也磨防具（armor.wears）
                continue
            count["fights"] += 1
            count["wins"] += b.tier in WINS

    def refuse(*args, **kwargs):
        raise RuntimeError("量測不連模型")

    # engine 照模組屬性呼叫 team.take_encounter_toll、team.heal、armor.buy、armor.repair，bot.play_season 照模組全域呼叫 pick：都換得到
    with mock.patch.object(naming, "propose", lambda *a, **k: (None, "")), \
            mock.patch.object(naming, "pick", lambda *a, **k: (None, "")), \
            mock.patch.object(OllamaClient, "chat_structured", refuse), mock.patch.object(OllamaClient, "chat_text", refuse), \
            mock.patch("requests.post", refuse), mock.patch("requests.get", refuse), \
            mock.patch.object(team, "take_encounter_toll", toll), mock.patch.object(team, "heal", heal), \
            mock.patch.object(armor, "buy", buy), mock.patch.object(armor, "repair", repair), \
            mock.patch.object(smithing, "forge", forge), mock.patch.object(smithing, "temper", temper), \
            mock.patch.object(bot, "pick", pick):
        game = bot.play_season(content, seed, world=open_world(TMP / f"s{seed}-{int(armor_on)}.db"), observe=observe)
    p = game.state.player
    season = game.state.world
    return {
        "fights": count["fights"], "win": count["wins"] / count["fights"] if count["fights"] else 0.0,
        "hp": round(sums["hp"]), "injury": round(sums["injury"]), "heal_silver": count["heal_silver"],
        "armored": count["armored"], "armored_hard": count["armored_hard"],
        "hard": count["hard"], "lasts": sums["hard_cap"] / sums["hard_hp"] if sums["hard_hp"] else None,
        "after_hard": count["after_hard"],
        "after_hard_win": count["after_hard_wins"] / count["after_hard"] if count["after_hard"] else None,
        "repairs": count["repairs"], "armor_silver": count["armor_silver"],
        "forged": count["forged"], "named": count["named"], "grades": grades, "tempered": count["tempered"],
        "armor": p.armor.name if p.armor else "—",
        "tier1": sum(n for mid, n in p.materials.items() if content.materials[mid].tier == 1),
        "silver": p.stats.get("silver", 0), "hours": season.time / 3600, "ending": season.ending_id or "—",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument("--profile", default=None)
    parser.add_argument("--steer", action="store_true", help="一半的時候照手上的懸賞、軍令走（週末那一組用，同 measure_sanren）")
    args = parser.parse_args()
    content = load_content(ROOT / "content", profile=args.profile)
    print(profile_line(content, args.profile) + ("（照手上的事走）" if args.steer else ""), flush=True)
    cfg = content.config
    cut = cfg.armor.tier_cut.get("1", 0.0) + cfg.armor.match  # 一階下品、跟內功同屬性（架上那件買對了）
    ref = "、".join(f"{t} {1 / cfg.encounter_neili_loss[t]:.1f}→{1 / (cfg.encounter_neili_loss[t] * (1 - cut)):.1f} 場"
                   for t in HARD if cfg.encounter_neili_loss.get(t))
    print(f"對照（設計 4.1 照表算，不含身法與回血；一階下品對上內功 {cut:.0%}）：{ref}", flush=True)
    for seed in args.seeds:
        for on in (False, True):
            r = run(seed, args.profile, on, args.steer)
            lasts = "—" if r["lasts"] is None else f"{r['lasts']:.1f}"
            after = "—" if r["after_hard_win"] is None else f"{r['after_hard_win']:.0%}"
            print(f"種子 {seed} 防具{'開' if on else '關'}：遊歷野怪 {r['fights']} 場（勝率 {r['win']:.0%}）、"
                  f"掉氣血 {r['hp']}、內傷 {r['injury']}、療傷 {r['heal_silver']} 兩、"
                  f"穿著防具 {r['armored']} 場（其中硬仗 {r['armored_hard']} 場）、"
                  f"硬仗 {r['hard']} 場（一條氣血撐 {lasts} 場）、硬仗之後再打的勝率 {after}（{r['after_hard']} 場）、"
                  f"打造防具 {r['forged']} 件（下 {r['grades']['下品']}／中 {r['grades']['中品']}／上 {r['grades']['上品']}）、"
                  f"防具名器 {r['named']} 件、淬防具 {r['tempered']} 次、"
                  f"修防具 {r['repairs']} 次、防具花 {r['armor_silver']} 兩、季末防具 {r['armor']}、"
                  f"一階素材 {r['tier1']}、銀兩 {r['silver']}、季長 {r['hours']:.1f} 小時（世界時間）、結局 {r['ending']}", flush=True)


if __name__ == "__main__":
    main()
