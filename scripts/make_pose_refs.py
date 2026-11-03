"""產畫坊用的姿勢剪影（tianxia/features/looks/pose/<張>.png）：斗笠小子那一條照排法重排、人塗成一片灰。

為什麼要剪影（2026-11-03 畫坊量測，scripts/studio_bench.py；正式站 #494、#495 都卡在 dodge／fall）：
原本畫圖時第一張參考圖是斗笠小子的彩色原圖，klein 把它當成要畫的人——審圖擋下的理由最多的是
「穿斗笠小子的格紋護甲、深色褲子」「頭上冒出斗笠」「多躺一個斗笠男孩」。拿掉它（只給定裝照）長相不漏了，
動作卻跟著沒了（fall 畫成跪爬、坐下）。灰色剪影只留姿勢與排法：兩套角色合計第一次就過的比例
dodge 6% → 31%（去掉斗笠）、fall 6% → 17%（留著斗笠）。
- dodge 去斗笠：斗笠的輪廓會被畫成「金色尖塔頭飾」。
- fall 留斗笠：踉蹌、倒地那幾格靠帽沿看得出臉朝哪邊；去掉之後第 3 格一半畫成朝左。
其他八張沒量過、現在也過得去，所以不產（studio.POSE 沒有的照舊用彩色原圖）。

    .venv/Scripts/python.exe scripts/make_pose_refs.py
要 Pillow、numpy、scipy（requirements-studio.txt）。斗笠小子的圖改了才要重產。
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia.features.looks import orders, studio  # noqa: E402

CELL = orders.CELL
WEB_IMG = ROOT / "web" / "img"
GRAY = 128
HATLESS = {"hero_bare_dodge": True, "hero_bare_fall": False}  # 哪幾張要產、要不要去斗笠（見上面）


def no_hat(cell: np.ndarray) -> np.ndarray:
    """一格剪影去掉斗笠：帽沿（頭部附近最寬的那一列）以上換成跟臉一樣寬的圓頂。躺著的格（寬大於高）不動。"""
    ys, xs = np.nonzero(cell)
    if not len(ys):
        return cell
    top, bottom = ys.min(), ys.max()
    if (xs.max() - xs.min()) > (bottom - top):
        return cell
    best, brim = 0, None
    for y in range(top, top + int((bottom - top) * 0.45)):
        lab, n = ndimage.label(cell[y])
        for i in range(1, n + 1):
            width = int((lab == i).sum())
            if width > best:
                best, brim = width, y
    if brim is None:
        return cell
    face = np.nonzero(cell[min(bottom, brim + 15)])[0]
    if not len(face):
        return cell
    cx, r = (face.min() + face.max()) / 2, max(8, (face.max() - face.min()) / 2)
    out = cell.copy()
    out[:brim + 3] = False
    yy, xx = np.mgrid[0:cell.shape[0], 0:cell.shape[1]]
    out |= (((xx - cx) / r) ** 2 + ((yy - (brim + 3)) / (r * 0.9)) ** 2 <= 1) & (yy <= brim + 3)
    lab, n = ndimage.label(out)  # 帽沿兩端切剩的細條丟掉：只留最大的那一塊
    if n > 1:
        out = lab == (int(np.argmax(ndimage.sum(out, lab, range(1, n + 1)))) + 1)
    return out


def silhouette(sheet: str, hatless: bool) -> bytes:
    """斗笠小子那一條照這一張的排法（studio.LAYOUT）重排，人塗成一片灰、白底，PNG。"""
    cols, rows = studio.LAYOUT[sheet]
    a = np.asarray(Image.open(orders.reference(WEB_IMG, sheet)).convert("RGBA"))[..., 3] > 32
    alpha = np.zeros((rows * CELL, cols * CELL), dtype=bool)
    for k in range(orders.SHEETS[sheet]):
        cell = a[:, k * CELL:(k + 1) * CELL]
        y, x = (k // cols) * CELL, (k % cols) * CELL
        alpha[y:y + CELL, x:x + CELL] = no_hat(cell) if hatless else cell
    out = np.full((*alpha.shape, 3), 255, dtype=np.uint8)
    out[alpha] = GRAY
    buf = io.BytesIO()
    Image.fromarray(out, "RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def main() -> int:
    studio.POSE_DIR.mkdir(parents=True, exist_ok=True)
    for sheet, hatless in HATLESS.items():
        path = studio.POSE_DIR / f"{sheet}.png"
        path.write_bytes(silhouette(sheet, hatless))
        print(f"{path.relative_to(ROOT)}（{'去斗笠' if hatless else '留斗笠'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
