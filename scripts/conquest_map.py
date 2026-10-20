"""領地爭奪的區塊表（第 38 項改版計畫 2.1；只讀、只載內容、不開資料庫）：給 PM 對地圖用。

印每條戰線的中立數、可奪的陣營區塊數、權重、中立全被一方拿下時基準偏幾點（兩種分母），與兩邊開季能挑的目標。

    python scripts/conquest_map.py [--profile season21]
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from tianxia import conquest, rules  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.renown import GREENWOOD_FLAG  # noqa: E402
from tianxia.state import WorldState  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="season21")
    args = parser.parse_args()
    c = load_content(Path(__file__).resolve().parent.parent / "content", profile=args.profile or None)
    cfg = c.config.conquest
    names = {t.id: t.name for t in c.scenario.trends}
    table = conquest.blocks(c)
    print(f"區塊 {len(table)} 塊；不是區塊：{'、'.join(c.locations[x].name for x in c.locations if x not in table)}")
    for kind in ("neutral", "guan", "huang"):
        rows = [c.locations[x].name + ("" if conquest.capturable(c, x) else "（大本營／fixed）") for x, b in table.items() if b.kind == kind]
        print(f"  {kind}（{len(rows)}）：{'、'.join(rows)}")
    print()
    for line in rules.front_ids(c):
        spots = [x for x, b in table.items() if b.line == line and conquest.capturable(c, x)]
        neutral = [x for x in spots if table[x].kind == "neutral"]
        faction = [x for x in spots if table[x].kind != "neutral"]
        weight_n = len(neutral) * cfg.neutral_weight
        weight_t = weight_n + len(faction) * cfg.faction_weight
        swing_t = cfg.share * weight_n / weight_t if weight_t else 0
        swing_n = cfg.share if weight_n else 0
        print(f"{names.get(line, line)}：中立 {len(neutral)}、可奪陣營區塊 {len(faction)}、總權重 {weight_t:g}；"
              f"中立全被一方拿下 ±{swing_t:.0f}（分母＝總權重）／±{swing_n:.0f}（分母＝只算中立）")
    print()
    world = WorldState()
    if c.config.renown.titles and c.config.renown.lessons:  # 綠林開寨：名聲開著時開季就立（world_state.stamp_season）
        world.flags.add(GREENWOOD_FLAG)
    for side in conquest.SIDES:
        got = conquest.targets(world, c, side)
        neutral = [x for x in got if table[x].kind == "neutral"]
        print(f"{side} 開季能挑：中立 {len(neutral)} 塊（{'、'.join(c.locations[x].name for x in neutral)}）"
              f"；敵方陣營區塊：{'、'.join(c.locations[x].name for x in got if x not in neutral) or '無'}")


if __name__ == "__main__":
    main()
