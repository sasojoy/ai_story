"""把 Joy 交的圖（PNG／JPG）壓成網頁用的 webp，放到 web/img/ 對應的路徑（減法季整合設計第八章、第一批圖提示單）。

用法：python scripts/art/to_webp.py <來源資料夾> [--out web/img] [--kb 100]
來源資料夾底下照提示單分子資料夾 places/、figures/、events/、stories/（奇事與頓悟的卡），檔名就是鍵（places/yingru.jpg → web/img/places/yingru.webp）。
場景與事件插圖寬 750（橫式）；人物像（figures/）寬 750、高 1000（3:4，寬了就從中間裁）。
品質從 82 往下找，到一張 kb 上下為止（最低 50）；已經有同名 webp 的照樣蓋掉（正式圖到了就換檔案，程式不用改）。
只做檔案，不碰內容與程式；要接上卡片是 content 的 image 欄位與 web/ 的事。"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
KINDS = {"places": (750, None), "events": (750, None), "figures": (750, 1000), "stories": (750, None)}  # stories：奇事與頓悟的卡（4:5 直式）  # 子資料夾 → （寬, 高或 None＝照比例）
SOURCES = (".png", ".jpg", ".jpeg", ".webp")


def convert(src: Path, dst: Path, width: int, height: int | None, kb: int) -> tuple[int, int, int]:
    """壓一張：回（寬, 高, 品質）。"""
    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    if height is None:
        height = round(img.height * width / img.width)
        img = img.resize((width, height), Image.LANCZOS)
    else:
        img = ImageOps.fit(img, (width, height), Image.LANCZOS, centering=(0.5, 0.35))  # 人物像偏上一點，臉不被裁掉
    quality = 82
    while True:
        buf = io.BytesIO()
        img.save(buf, "WEBP", quality=quality, method=6)
        if buf.tell() <= kb * 1024 or quality <= 50:
            break
        quality -= 4
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(buf.getvalue())
    return width, height, quality


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("source", type=Path, help="Joy 交的圖所在的資料夾（底下 places/、figures/、events/、stories/）")
    parser.add_argument("--out", type=Path, default=ROOT / "web" / "img")
    parser.add_argument("--kb", type=int, default=100, help="一張大約幾 KB（預設 100）")
    args = parser.parse_args(argv)
    done = 0
    for kind, (width, height) in KINDS.items():
        folder = args.source / kind
        if not folder.is_dir():
            continue
        for src in sorted(folder.iterdir()):
            if src.suffix.lower() not in SOURCES:
                continue
            dst = args.out / kind / f"{src.stem}.webp"
            w, h, q = convert(src, dst, width, height, args.kb)
            print(f"{kind}/{src.stem}.webp  {w}×{h}  q{q}  {dst.stat().st_size // 1024} KB")
            done += 1
    print(f"共 {done} 張 → {args.out}")
    return 0 if done else 1


if __name__ == "__main__":
    sys.exit(main())
