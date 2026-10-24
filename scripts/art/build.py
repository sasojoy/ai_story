"""把第一批圖全部畫出來，寫到 web/img/（圖像版第八章；圖檔進 git，企劃者 2026-10-24）。

    python3 scripts/art/build.py            # 寫 SVG
    python3 scripts/art/build.py --sheet    # 另外產一張對照表 web/img/sheet.html（看圖用，不進遊戲）

每一張用名字當亂數種子，重跑一樣；改了畫法重跑一次就好。檔名就是地點 id、事件類型、人物 id、圖示鍵。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from events import EVENT_NAMES, EVENTS  # noqa: E402
from figures import FIGURES  # noqa: E402
from icons import ICON_NAMES, ICONS  # noqa: E402
from scenes import SCENES  # noqa: E402

ROOT = Path(__file__).resolve().parents[2] / "web" / "img"
PLACE_NAMES = {"yingru": "潁川汝南", "nanyang": "南陽", "jizhou": "冀州", "luoyang": "洛陽", "youzhou": "幽州", "tianxia": "天下"}
FIGURE_NAMES = {"luzhi": "盧植", "bocai": "波才", "huangfusong": "皇甫嵩"}


def write(folder: str, table: dict) -> list[str]:
    out = ROOT / folder
    out.mkdir(parents=True, exist_ok=True)
    names = []
    for key, fn in table.items():
        (out / f"{key}.svg").write_text(fn(), encoding="utf-8", newline="\n")
        names.append(key)
    return names


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    groups = [("places", SCENES, PLACE_NAMES), ("events", EVENTS, EVENT_NAMES), ("figures", FIGURES, FIGURE_NAMES), ("icons", ICONS, ICON_NAMES)]
    for folder, table, _ in groups:
        names = write(folder, table)
        print(f"{folder}: {len(names)} 張")
    if "--sheet" in sys.argv:
        rows = []
        for folder, table, labels in groups:
            size = "width:140px;height:140px" if folder == "figures" else ("width:72px;height:72px;background:#fbf7ee" if folder == "icons" else "width:250px")
            cells = "".join(f'<figure><img src="{folder}/{k}.svg" style="{size}"><figcaption>{labels[k]}<br><small>{k}</small></figcaption></figure>' for k in table)
            rows.append(f"<h2>{folder}</h2><div class=row>{cells}</div>")
        html = ("<!doctype html><meta charset=utf-8><title>第一批圖</title><style>body{font-family:'Noto Serif TC',serif;background:#e9e2d2;margin:16px}"
                ".row{display:flex;flex-wrap:wrap;gap:10px}figure{margin:0;text-align:center;font-size:12px}img{display:block;border:1px solid #cfc4ab;border-radius:6px}</style>"
                + "".join(rows))
        (ROOT / "sheet.html").write_text(html, encoding="utf-8", newline="\n")
        print("sheet: web/img/sheet.html")


if __name__ == "__main__":
    main()
