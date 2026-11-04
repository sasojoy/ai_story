"""傳承的量表（features/legacy；架構方向 v2 第六節、第十一節第 4 條）：權重先一律同值，量過再給 Joy 挑。

兩種量法：
- 讀一份資料庫（--db，建議對備份檔跑）：每個角色「此刻換季的話」評比的六樣原始數、三項的增量與結算後的值，加上每一樣的分布
  （中位數、九成、最大）與「每一樣中位數貢獻一樣多」的建議權重（機緣那四樣；正邪各自只看一樣，權重只改尺度）。
- --demo：三種人（認真、普通、停一季再回來）連玩幾季的走向，看領先多少、差距收不收斂。每一季的原始數用 --keen、--casual 給。

執行：python scripts/measure_legacy.py --db <備份檔> [--profile season21]
      python scripts/measure_legacy.py --demo --seasons 5
印中文前把 stdout 包成 UTF-8（cp950 會噴錯）。名單不寫誰是假人。
"""
from __future__ import annotations

import argparse
import io
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia.content import env_profile, load_content  # noqa: E402
from tianxia.features.legacy import rules as R  # noqa: E402
from tianxia.state import LegacyBook  # noqa: E402

KEYS = ("tasks", "merit", "fame", "relations", "good", "evil")


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def from_db(db: Path, profile: str | None) -> None:
    from tianxia.characters import open_characters  # noqa: PLC0415

    content = load_content(ROOT / "content", profile)
    r = R.rules(content)
    states = [s for s in open_characters(db).all() if s.player.tutorial_step > 0 or s.player.member.level > 1]
    rows = []
    for s in states:
        raw = R.inputs(s, content)
        got = R.gains(raw, r)
        book = R.settle(s.player.legacy or LegacyBook(), got, r, s.player.season_number + 1)
        rows.append((s.player.name, raw, got, book))
    print(f"權重：{r.weights}　曲線：{r.curve}　留 {r.keep}　角色 {len(rows)} 個")
    print("名號 | " + " ".join(KEYS) + " | 正氣 邪氣 機緣（增量 → 結算後）")
    for name, raw, got, book in sorted(rows, key=lambda row: -row[2]["luck"]):
        nums = " ".join(f"{raw[k]:g}" for k in KEYS)
        after = " ".join(f"{got[a]:.1f}→{getattr(book, a):.1f}" for a in R.AXES)
        print(f"{name} | {nums} | {after}")
    print("\n分布（中位數／九成／最大）：")
    medians = {}
    for k in KEYS:
        values = [raw[k] for _, raw, _, _ in rows]
        medians[k] = statistics.median(values) if values else 0.0
        print(f"  {k}: {medians[k]:g}／{_pct(values, 0.9):g}／{max(values, default=0):g}")
    luck = [k for k in R.LUCK_FROM if medians[k] > 0]
    if luck:
        top = max(medians[k] for k in luck)
        print("\n建議權重（機緣四樣的中位數貢獻一樣多；中位數是 0 的照 1）：")
        print("  " + "、".join(f"{k} {top / medians[k]:.3g}" if medians[k] > 0 else f"{k} 1" for k in R.LUCK_FROM))
    for axis in R.AXES:
        values = [getattr(book, axis) for *_, book in rows]
        print(f"{R.NAMES[axis]}：中位數 {statistics.median(values) if values else 0:.1f}、最大 {max(values, default=0):.1f}")


def demo(seasons: int, keen: float, casual: float, profile: str | None) -> None:
    r = R.rules(load_content(ROOT / "content", profile))
    people = {"認真": [keen] * seasons, "普通": [casual] * seasons, "停一季": [keen if i != 1 else 0.0 for i in range(seasons)]}
    print(f"每一季原始的合計：認真 {keen:g}、普通 {casual:g}（停一季：第 2 季沒玩）；曲線 {r.curve}、留 {r.keep}")
    books = {k: LegacyBook() for k in people}
    for season in range(seasons):
        cells = []
        for who, row in people.items():
            gain = R.curve(row[season], r.curve)
            books[who] = R.settle(books[who], {"zheng": 0.0, "xie": 0.0, "luck": gain}, r, season + 1)
            cells.append(f"{who} {books[who].luck:.1f}")
        print(f"第 {season + 1} 季：" + "、".join(cells) + f"　（新人 {R.curve(keen, r.curve):.1f}）")
    print(f"上限（一直認真）：{R.curve(keen, r.curve) / (1 - r.keep):.1f}")


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path)
    parser.add_argument("--profile", default=env_profile())
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--seasons", type=int, default=5)
    parser.add_argument("--keen", type=float, default=400.0)
    parser.add_argument("--casual", type=float, default=100.0)
    args = parser.parse_args()
    if args.demo:
        demo(args.seasons, args.keen, args.casual, args.profile)
    elif args.db is not None:
        from_db(args.db, args.profile)
    else:
        parser.error("給 --db <資料庫檔> 或 --demo")


if __name__ == "__main__":
    main()
