"""替 content/looks.json 的形象算一張手位表（web/img/looks/<id>/hands.json）。

兵器掛在哪，網頁本來一律讀 web/arena_anim.js 的 RING_HAND——那是照斗笠小子量的。換一套形象手就不在
同一個地方：2026-11-02 量新收的四套，49 格裡各有 7～11 格的手位落在身體以外，兵器就懸在空中（Joy 看出來的）。
這支照每一套自己的身體算（tianxia/features/looks/cutting.hand_row），寫成圖旁邊的 hands.json，
網頁抓得到就用它、抓不到照舊讀 RING_HAND。算出來的檔要進版控（圖本來就在版控裡）。

用法：
    .venv/Scripts/python.exe scripts/look_hands.py            # 全部重算
    .venv/Scripts/python.exe scripts/look_hands.py xianv lishi  # 只算這幾套
    .venv/Scripts/python.exe scripts/look_hands.py --check    # 只檢查，不寫（有落空的回 1）

自建形象（u<編號>）不走這一支：圖存進來的時候 orders.save_sheet 就順手算好了。
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from tianxia.features.looks import cutting, orders  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOOKS = ROOT / "web" / "img" / "looks"


def off_body(strip: bytes, name: str, row: list[list[int]]) -> list[str]:
    """算完之後還落在身體以外的那幾格（倒地那幾格兵器本來就在地上，不算）。"""
    a = np.asarray(Image.open(io.BytesIO(strip)).convert("RGBA"))[..., 3] > 32
    out = []
    for k, (x, y) in enumerate(row):
        if cutting.HAND[name][k][3] == cutting.GROUND_LAYER:
            continue
        cell = a[:, k * cutting.CELL:(k + 1) * cutting.CELL]
        if not cell[max(0, y - 2):y + 3, max(0, x - 2):x + 3].any():
            out.append(f"{name}#{k + 1}")
    return out


def one(look: str, write: bool) -> int:
    table, bad, n = {}, [], 0
    for sheet in orders.ARENA:  # 走一趟那六張不掛兵器
        path = orders.sheet_file(LOOKS, look, sheet)
        if path is None:
            continue
        data = path.read_bytes()
        row = cutting.hand_row(data, sheet)
        table[sheet] = row
        bad += off_body(data, sheet, row)
        n += len(row)
    if not table:
        print(f"{look}：沒有圖，跳過")
        return 0
    if write:
        orders.hands_file(LOOKS, look).write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    print(f"{look}：{len(table)} 張 {n} 格{'（寫好了）' if write else ''}"
          + (f"　仍落空 {len(bad)} 格：{'、'.join(bad)}" if bad else "　全部落在身上"))
    return len(bad)


def main(argv: list[str]) -> int:
    write = "--check" not in argv
    names = [a for a in argv if not a.startswith("-")]
    if not names:
        names = sorted(d.name for d in LOOKS.iterdir() if d.is_dir()) if LOOKS.is_dir() else []
    return 1 if sum(one(look, write) for look in names) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
