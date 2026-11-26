"""地方大事的純規則（不讀時鐘、不碰 Game）：開關、內容檔、這一週挑哪一件、三幕要多少、第二幕的成算、第三幕一下多重。
設計：玩家一起玩設計稿第一節（https://claude.ai/artifact/J2hWqymn9SXRgw1qashgKb；Joy 2026-11-26「做」）。"""
from __future__ import annotations

import hashlib
import json
import math
import random
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILE = HERE / "content" / "difang.json"  # 包自己讀（同 yiwen：Content 不加欄位）
OPEN, DONE, FAILED = "open", "done", "failed"
ACTS = 3


def on(content) -> bool:
    return bool(content.config.difang.enabled)


def roll(*parts) -> random.Random:
    """種子字串 sha256 開一個 Random（不碰 Game.rng：開關開著也不改別的包抽亂數的順序）。"""
    digest = hashlib.sha256("｜".join(map(str, parts)).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


@lru_cache(maxsize=2)
def _read(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def affairs() -> dict[str, dict]:
    """內容 id → 那一件（照檔裡的先後）。"""
    return {a["id"]: a for a in _read(str(FILE)).get("affairs", [])}


def cache_clear() -> None:
    _read.cache_clear()


def pick(region: str, season: int, week: int, table: dict[str, dict] | None = None) -> dict | None:
    """這個大區這一週是哪一件：寫了這個大區的先挑，都沒有再挑不限大區的（regions 空的）；同一季同一週同一區大家看到同一件。"""
    table = affairs() if table is None else table
    mine = [a for a in table.values() if region in a.get("regions", [])]
    pool = mine or [a for a in table.values() if not a.get("regions")]
    if not pool:
        return None
    return pool[roll("地方大事", season, week, region).randrange(len(pool))]


def needs(tuning, heads: int) -> list[int]:
    """三幕各要多少：上一件出過力的人數 × per_head，夾在 need_min 與 need_max 之間。"""
    out = []
    for i in range(ACTS):
        n = math.ceil(heads * float(tuning.per_head[i]))
        out.append(max(int(tuning.need_min[i]), min(int(tuning.need_max[i]), n)))
    return out


def way_chance(tuning, stat: int) -> float:
    """第二幕挑一個做法成的機率：照那一項屬性。"""
    return max(0.0, min(float(tuning.way_cap), float(tuning.way_base) + float(tuning.way_per_point) * max(0, int(stat))))


def blow(tuning, power: float) -> int:
    """第三幕一下算幾份：1 + 戰力 ÷ blow_power，夾在 blow_max。"""
    return max(1, min(int(tuning.blow_max), 1 + int(max(0.0, float(power)) // max(1.0, float(tuning.blow_power)))))


def fill(text: str, **slots) -> str:
    out = str(text)
    for k, v in slots.items():
        out = out.replace("{" + k + "}", str(v))
    return out
