"""把生圖工具生出來的九張原圖切成擂台形象用的九張（自建形象第二批；管理者在主機或自己的電腦上跑）。

python scripts/cut_look.py <原圖資料夾> <輸出資料夾>

原圖資料夾裡照九張的名字放（hero_bare_idle.png、hero_atk_slash.jpg……，副檔名 png／jpg／webp 都行），白底、側面朝右（提示詞在管理者區
「自建形象」那一格展開就有）。切法同走一趟與擂台斗笠小子（/mnt/project-files/design/走一趟/sprites.py）：去白底、照格數切格、照斗笠
的寬度定比例、腳底對到 (100, 212)，每格 220×220，輸出 webp。切好的九張到設定頁管理者區「自建形象」那一張訂單上傳。

要 Pillow、numpy、scipy（伺服器不用裝；跑之前 pip install pillow numpy scipy）。這支只動檔案，不碰資料庫、不叫任何外部服務。
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tianxia.features.looks.cutting import LAYOUT, sheet  # noqa: E402  切法搬進功能包（畫坊也用）


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    src, out = Path(argv[1]), Path(argv[2])
    out.mkdir(parents=True, exist_ok=True)
    missing = []
    for name, (cols, rows) in LAYOUT.items():
        path = next((p for ext in ("png", "jpg", "jpeg", "webp") for p in [src / f"{name}.{ext}"] if p.is_file()), None)
        if path is None:
            missing.append(name)
            continue
        strip = sheet(path, cols, rows)
        strip.save(out / f"{name}.webp", "WEBP", quality=82, method=6)
        print(f"{name}：{strip.width // CELL} 格 → {out / (name + '.webp')}")
    if missing:
        print(f"缺 {len(missing)} 張：{'、'.join(missing)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
