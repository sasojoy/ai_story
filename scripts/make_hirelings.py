"""生 content/hirelings.json（一般 NPC 同伴，features/hire；企劃者 2026-11-04「NPC 五型在酒肆花銀兩招、名字隨機」）。

每一間帶「酒肆」標籤的地點、每一型（Config.hire.types）生 Config.hire.per_tavern 位：名字是姓加兩個字隨機取（種子固定，
重跑同一份），不跟人物表、大勢人物、禁用名單撞名；屬性照型的資質換成舊的四項（武力→臂力、身法→身法、統御→根骨、悟性→悟性，
跟人物表一樣是 2～9），每級成長照資質的二十分之一。來歷照型的句子挑一句。

用法：python scripts/make_hirelings.py [--seed 1104] [--check]（--check 只比對、不寫：檔案跟現在的內容對不上回 1）
"""
from __future__ import annotations

import argparse
import io
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from tianxia.content import load_content  # noqa: E402

OUT = ROOT / "content" / "hirelings.json"
SURNAMES = "王李張劉陳楊黃周吳徐朱胡郭何高林羅鄭梁謝宋唐韓馮于蕭程曹鄧彭蘇盧蔣蔡丁魏薛葉閻潘杜戴夏鍾汪田任姜范方石姚譚廖鄒熊金陸郝孔崔邱秦江史顧侯邵孟萬段雷錢湯尹黎常喬賀賴龔"
FIRST = "德子仲伯叔季文元公彥士景孝承休長宣世義茂"
SECOND = "平安遠明達和成興昌通方正忠信誠良恭敬勇山"
TO_V1 = {"str": "str", "spd": "agi", "lead": "con", "int": "wis"}


def build(content, seed: int) -> list[dict]:
    rng = random.Random(seed)
    cfg = content.config.hire
    taken = {ch.name for ch in content.characters.values() if ch.hire_type is None}
    taken |= set(content.banned_name_list()) if hasattr(content, "banned_name_list") else set()
    taverns = [(k, loc) for k, loc in content.locations.items() if "酒肆" in (getattr(loc, "tags", None) or [])]
    out = []
    for key, loc in taverns:
        place = loc.name.split("（")[0]
        for kind in cfg.types:
            for n in range(cfg.per_tavern):
                while True:
                    name = rng.choice(SURNAMES) + rng.choice(FIRST) + rng.choice(SECOND)
                    if name not in taken:
                        break
                taken.add(name)
                stats = {old: float(kind.aptitude[new]) for new, old in TO_V1.items()}
                out.append({
                    "id": f"hire_{key}_{kind.key}_{n + 1}", "name": name, "stats": stats,
                    "growth": {k: round(v / 20, 2) for k, v in stats.items()},
                    "desc": rng.choice(kind.blurbs).format(place=place) if kind.blurbs else "",
                    "starting_wugong": kind.wugong, "starting_neigong": kind.neigong,
                    "hire_type": kind.key, "hire_at": key,
                })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1104)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    content = load_content(ROOT / "content")
    rows = build(content, args.seed)
    text = json.dumps(rows, ensure_ascii=False, indent=1) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("一樣" if same else "對不上：重跑 python scripts/make_hirelings.py")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8")
    print(f"寫了 {len(rows)} 位到 {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
