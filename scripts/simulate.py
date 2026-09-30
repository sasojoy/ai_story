"""平衡模擬：讓亂數機器人玩完整季，統計結局、大勢發展、名冊的成長與整季拿到的心得；
給了元寶時另跑一組付費機器人（開季先把元寶花在招賢），量兩邊本隊交手的勝率。

用法：.venv/Scripts/python.exe scripts/simulate.py 30          （免費機器人 30 季）
      .venv/Scripts/python.exe scripts/simulate.py 30 3000     （再加上開季先花 3000 元寶招賢的付費機器人）
"""
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import team  # noqa: E402
from tianxia.battle import run_battle  # noqa: E402
from tianxia.bot import play_season  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.models import COMPANION_TIERS  # noqa: E402
from tianxia.rules import DAY, current_day  # noqa: E402
from tianxia.state import PLAYER  # noqa: E402

# 看第幾天結束時的名冊人數。設計草稿的新手目標是第 1 天 3 人、第 3 天 6 人、季末 10～12 人；但機器人只在名冊（含你）
# 還塞不滿已開放的隊伍（第一幕 6 人、第二幕 9 人、第三幕 12 人）、而且付完還付得起下一次時才收徒，結識、福緣、招降
# 則一律接受，所以這裡的人數反映的是這套策略，不是遊戲規則的上限。
CHECKPOINTS = (1, 3, 7)
# 付費方與免費方本隊交手的時間點（看 act_reached）：開季＝招賢之後、第一步之前；第二幕、第三幕＝那一季第一次到達時。
# 那一季沒到就用季末的樣子。後面是設計文件 1c §九的目標：付費方勝率不超過這個數。
DUEL_POINTS = {0: ("開季", 0.70), 1: ("第二幕", 0.60), 2: ("第三幕", 0.55)}
DUEL_RUNS = 40  # 每一對交手幾場（內力全滿）：一半付費方列在前面、一半免費方列在前面（同速時列在前面的先出手）


def xinde_earned(game) -> int:
    """這一季拿到的心得（不是餘額）：餘額加上花在精進上的。機器人從不散功、內容裡也沒有扣心得的事件，
    所以這就是整季的總收入（歷練、劇情、新手引導、重複結識，付費機器人另有招賢）。"""
    p, c = game.state.player, game.content
    levels = list(p.skills.values()) + [m.innate_level for key, m in p.members.items() if key != PLAYER]
    return p.stats.get("xinde", 0) + sum(team.upgrade_cost(c, n) for level in levels for n in range(1, level))


def play(content, runs: int, yuanbao: int = 0) -> dict:
    """runs 季，回傳統計；snaps[i][幕] 是第 i 季在那個時間點的狀態（深拷貝），reached[i] 是第 i 季真的到過的幕。"""
    stats = {
        "endings": Counter(), "thresholds": Counter(), "storylines": Counter(), "days": [], "events": [],
        "sizes": {day: [] for day in CHECKPOINTS}, "final_sizes": [], "final_tiers": Counter(),
        "xinde": [], "gacha_xinde": [], "snaps": [], "reached": [],
    }
    for seed in range(runs):
        seen: dict[int, int] = {}
        snaps: dict[int, object] = {}

        def observe(game, seen=seen, snaps=snaps) -> None:
            today = current_day(game.state)
            for day in CHECKPOINTS:
                if today <= day:
                    seen[day] = len(game.state.player.members)
            for act in DUEL_POINTS:
                if act not in snaps and game.state.world.act_reached >= act:
                    snaps[act] = game.state.model_copy(deep=True)

        game = play_season(content, seed, observe=observe, yuanbao=yuanbao)
        world, p = game.state.world, game.state.player
        stats["endings"][world.ending_title] += 1
        stats["thresholds"].update(world.fired_thresholds)
        stats["storylines"][world.storyline] += 1
        stats["days"].append(world.time / DAY)
        stats["events"].append(len(p.seen_events))
        for day in CHECKPOINTS:
            stats["sizes"][day].append(seen.get(day, len(p.members)))
        stats["final_sizes"].append(len(p.members))
        stats["final_tiers"].update(content.characters[key].tier for key in p.members if key != PLAYER)
        stats["xinde"].append(xinde_earned(game))
        stats["gacha_xinde"].append(p.gacha_xinde)
        stats["reached"].append(set(snaps))
        for act in DUEL_POINTS:
            snaps.setdefault(act, game.state.model_copy(deep=True))
        stats["snaps"].append(snaps)
    return stats


def with_full_neili(state):
    """內力全滿的複本；不動傳進來的狀態。"""
    copy = state.model_copy(deep=True)
    for member in copy.player.members.values():
        member.neili = None
    return copy


def duel(paid, free, content, seed: int) -> tuple[int, int]:
    """付費方與免費方的本隊（內力全滿）打 DUEL_RUNS 場，回傳（付費方勝場, 平手場）。傳進來的狀態不會被動到。"""
    rules, rng = team.battle_rules(content), random.Random(seed)
    paid, free = with_full_neili(paid), with_full_neili(free)  # run_battle 不改狀態（戰後內力是 fight 寫的），全滿只要設一次
    wins = draws = 0
    for i in range(DUEL_RUNS):
        ours, theirs = team.team_units(paid, content), team.team_units(free, content)  # 戰鬥單位每場都要重建
        if i % 2 == 0:
            outcome = run_battle(ours, theirs, rng, rules).outcome
        else:
            outcome = {"win": "lose", "lose": "win", "draw": "draw"}[run_battle(theirs, ours, rng, rules).outcome]
        wins += outcome == "win"
        draws += outcome == "draw"
    return wins, draws


def report(title: str, stats: dict, runs: int) -> None:
    print(title)
    print("結局：", dict(stats["endings"]))
    print("門檻觸發次數：", dict(stats["thresholds"]))
    print("最終主線：", dict(stats["storylines"]))
    print(f"平均季長 {sum(stats['days']) / runs:.1f} 天；平均遇到 {sum(stats['events']) / runs:.1f} 種事件")
    sizes, final = stats["sizes"], stats["final_sizes"]
    counts = "　".join(f"第{day}天 {sum(sizes[day]) / runs:.1f}" for day in CHECKPOINTS)
    print(f"名冊人數（含你本人，平均）：{counts}　季末 {sum(final) / runs:.1f}（最少 {min(final)}、最多 {max(final)}）")
    tiers = stats["final_tiers"]
    print("季末品階（每季平均幾人）：" + "　".join(f"{tier} {tiers[tier] / runs:.1f}" for tier in COMPANION_TIERS))
    xinde = stats["xinde"]
    gacha = f"，其中招賢 {sum(stats['gacha_xinde']) / runs:.0f}" if any(stats["gacha_xinde"]) else ""
    print(f"整季拿到的心得（不是餘額）：平均 {sum(xinde) / runs:.0f}{gacha}（最少 {min(xinde)}、最多 {max(xinde)}）")


def main(runs: int, yuanbao: int) -> None:
    content = load_content(ROOT / "content")
    free = play(content, runs)
    report(f"模擬 {runs} 季（免費機器人）", free, runs)
    if not yuanbao:
        return
    paid = play(content, runs, yuanbao)
    print()
    report(f"付費機器人：開季先花 {yuanbao} 元寶招賢", paid, runs)
    print()
    print(f"付費方本隊對免費方本隊（同一個種子的兩季，每一對 {DUEL_RUNS} 場，內力全滿）：")
    for act, (name, target) in DUEL_POINTS.items():
        wins = draws = 0
        for seed in range(runs):
            w, d = duel(paid["snaps"][seed][act], free["snaps"][seed][act], content, seed)
            wins, draws = wins + w, draws + d
        total = runs * DUEL_RUNS
        missing = sum(act not in paid["reached"][seed] or act not in free["reached"][seed] for seed in range(runs))
        note = f"；{missing} 季至少一邊沒到，用季末" if missing else ""
        print(f"  {name}：付費方勝 {wins / total:.0%}、平 {draws / total:.0%}（目標 ≤ {target:.0%}{note}）")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20, int(sys.argv[2]) if len(sys.argv) > 2 else 0)
