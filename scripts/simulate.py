"""平衡模擬：讓亂數機器人玩完整季，統計結局、大勢發展與名冊的成長。

用法：.venv/Scripts/python.exe scripts/simulate.py 50
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia.bot import play_season  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.models import COMPANION_TIERS  # noqa: E402
from tianxia.rules import DAY, current_day  # noqa: E402
from tianxia.state import PLAYER  # noqa: E402

CHECKPOINTS = (1, 3, 7)  # 看第幾天結束時的名冊人數（設計草稿的目標：第 1 天 3 人、第 3 天 6 人、季末 10～12 人）


def main(runs: int) -> None:
    content = load_content(ROOT / "content")
    endings, thresholds = Counter(), Counter()
    storylines = Counter()
    days, events = [], []
    sizes = {day: [] for day in CHECKPOINTS}
    final_sizes, final_tiers = [], Counter()
    for seed in range(runs):
        seen: dict[int, int] = {}

        def observe(game, seen=seen) -> None:
            today = current_day(game.state)
            for day in CHECKPOINTS:
                if today <= day:
                    seen[day] = len(game.state.player.members)

        game = play_season(content, seed, observe=observe)
        world, members = game.state.world, game.state.player.members
        endings[world.ending_title] += 1
        thresholds.update(world.fired_thresholds)
        storylines[world.storyline] += 1
        days.append(world.time / DAY)
        events.append(len(game.state.player.seen_events))
        for day in CHECKPOINTS:
            sizes[day].append(seen.get(day, len(members)))
        final_sizes.append(len(members))
        final_tiers.update(content.characters[key].tier for key in members if key != PLAYER)
    print(f"模擬 {runs} 季")
    print("結局：", dict(endings))
    print("門檻觸發次數：", dict(thresholds))
    print("最終主線：", dict(storylines))
    print(f"平均季長 {sum(days) / runs:.1f} 天；平均遇到 {sum(events) / runs:.1f} 種事件")
    counts = "　".join(f"第{day}天 {sum(sizes[day]) / runs:.1f}" for day in CHECKPOINTS)
    print(f"名冊人數（含你本人，平均）：{counts}　季末 {sum(final_sizes) / runs:.1f}（最少 {min(final_sizes)}、最多 {max(final_sizes)}）")
    print("季末品階（每季平均幾人）：" + "　".join(f"{tier} {final_tiers[tier] / runs:.1f}" for tier in COMPANION_TIERS))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
