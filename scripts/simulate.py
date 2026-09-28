"""平衡模擬：讓亂數機器人玩完整季，統計結局與大勢發展。

用法：.venv/Scripts/python.exe scripts/simulate.py 50
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia.bot import play_season  # noqa: E402
from tianxia.content import load_content  # noqa: E402


def main(runs: int) -> None:
    content = load_content(ROOT / "content")
    endings, thresholds = Counter(), Counter()
    days, events = [], []
    for seed in range(runs):
        world = (game := play_season(content, seed)).state.world
        endings[world.ending_title] += 1
        thresholds.update(world.fired_thresholds)
        days.append(world.time / 86400)
        events.append(len(game.state.player.seen_events))
    print(f"模擬 {runs} 季")
    print("結局：", dict(endings))
    print("門檻觸發次數：", dict(thresholds))
    print(f"平均季長 {sum(days) / runs:.1f} 天；平均遇到 {sum(events) / runs:.1f} 種事件")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
