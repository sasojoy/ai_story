"""異聞的純規則（不讀時鐘、不碰 Game）：開關、季鐘、內容檔讀取、種子、模板句、獎勵表、路與足跡怎麼數。
這一份裡的 rules.x 指包的 rules.py；核心的 tianxia/rules.py 在 actions.py 寫 core_rules.x。
設計 docs/superpowers/specs/2026-11-20-異聞-design.md；做法照總計畫 docs/superpowers/plans/2026-11-21-異聞-計畫.md「異聞一」。"""
from __future__ import annotations

import hashlib
import json
import random
import re
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 內容檔這一包自己讀（總計畫「對不上的」第 12 條：Content 不加欄位）；測試由 yiwen_kit.use_test_lines 換 openings 那一格
FILES: dict[str, Path] = {"openings": HERE / "content" / "yiwen_openings.json", "lines": HERE / "content" / "yiwen_lines.json"}
# 探索的六種地點（核心 core/explore_base 的常數）→ 畫面上的單字（包自己的映射，地圖包的表不能 import）
KINDS = {"town": "城", "temple": "寺", "ford": "渡", "wild": "野", "hill": "山", "camp": "營"}
FIND, TRAIL = "find", "trail"  # YiwenWalk.role
WALKING, OPEN, SETTLED, REMOVED = "walking", "open", "settled", "removed"  # tales.status
GOOD, BAD = "good", "bad"  # 順、逆
LUCK_SEAL = {GOOD: "順", BAD: "逆"}  # 待 joy 潤
DEPTH = 3  # 一則三步
DAY = 86400.0
HOUR = 3600.0
SLOT = re.compile(r"\{(\w+)\}")
# 每組至少幾句（設計 3.3；gone、drop、locked 是總計畫加的）
LINE_GROUPS: dict[str, int] = {
    "lead_in": 4, "first_frame": 2, **{f"trail_frame.{k}": 2 for k in KINDS}, "echo": 3, "zhupi": 3, "summary": 4, "broken": 3,
    "fallback_options": 3, "close": 3, "verdict": 3, "no_verdict": 2, "pending": 1, "omen": 3, "omen_none": 2, "discover_rumor": 2,
    "busy": 2, "refuse_typed": 3, "taken": 1, "full_paths": 1, "full": 1, "removed": 2, "gone": 1, "drop": 1, "locked": 1,
}
# 每組的填空（驗證：只能用這幾個、填得進去）
LINE_SLOTS: dict[str, set[str]] = {
    "trail_frame": {"place"}, "echo": {"pick"}, "zhupi": {"who", "words"}, "summary": {"who", "pick", "thing"},
    "broken": {"pick", "thing"}, "fallback_options": {"thing"}, "verdict": {"place", "place_word", "thing", "answer", "who", "n"},
    "no_verdict": {"place", "thing"}, "pending": {"days"}, "omen": {"place", "thing", "answer"}, "omen_none": {"place", "thing"},
    "discover_rumor": {"place"},
}


def on(content, world) -> bool:
    """開關開著、而且這一季開季時蓋了章（季中打開下一季才有；季中關掉這一刻就停）。"""
    return bool(content.config.yiwen.enabled) and bool(getattr(world, "yiwen_on", False))


def season_clock(world, content) -> float:
    """這一季開季以來真的在跑的現實秒（暫停的那段不算）：world.time / time_scale（總計畫「對不上的」第 1 條）。"""
    scale = float(content.config.time_scale or 1.0)
    return float(world.time) / scale


def roll(*parts) -> random.Random:
    """種子字串 sha256 開一個 Random（不用 hash()、不碰 Game.rng：開關開著也不改別的包抽亂數的順序）。"""
    digest = hashlib.sha256("｜".join(map(str, parts)).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


@lru_cache(maxsize=4)
def _read(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def openings() -> dict[str, dict]:
    """開場 id → 那一句（yiwen_openings.json 的 openings 陣列，照檔裡的先後）。"""
    return {o["id"]: o for o in _read(str(FILES["openings"])).get("openings", [])}


def lines() -> dict[str, list[str]]:
    return dict(_read(str(FILES["lines"])))


def cache_clear() -> None:
    _read.cache_clear()


def pick_line(table: dict[str, list[str]], group: str, *, season, tale, node) -> str:
    """一組裡照「異聞｜季｜則｜節點｜組名」挑一句（同一處每個人看到同一句）；沒有這一組回空字串。"""
    choices = table.get(group) or []
    if not choices:
        return ""
    digest = hashlib.sha256("｜".join(map(str, ("異聞", season, tale, node, group))).encode("utf-8")).digest()
    return choices[int.from_bytes(digest[:4], "big") % len(choices)]


def fill(template: str, **slots) -> str:
    """只換 {已知鍵}，一次掃過：玩家的字放進去之後不再掃（裡面的 {…} 照字面留著；評審焦點 1）。"""
    return SLOT.sub(lambda m: str(slots[m.group(1)]) if m.group(1) in slots else m.group(0), template)


def reward(tier_table: dict, content, world=None) -> dict[str, int]:
    """等級（Config.rewards.grades 的 key）照 amounts 換成數字：{"silver": 20, "xinde": 8}。只算、不發；五項屬性的季照等級放大由核心 apply_effect 做。"""
    rr = content.config.rewards
    keys = [grade_row.key for grade_row in rr.grades]
    out: dict[str, int] = {}
    for kind, grade in tier_table.items():
        row = rr.amounts.get(kind)
        if row is None or grade not in keys:
            continue
        out[kind] = int(row[keys.index(grade)])
    return out


def path_of(nodes: list[dict], leaf: int) -> list[int]:
    """從第一幕到 leaf 的節點 id（父子照 parent 接）。"""
    by_id = {n["id"]: n for n in nodes}
    out: list[int] = []
    cur = by_id.get(leaf)
    while cur is not None:
        out.append(cur["id"])
        cur = by_id.get(cur["parent"])
    return out[::-1]


def leaves(nodes: list[dict]) -> list[int]:
    parents = {n["parent"] for n in nodes}
    return [n["id"] for n in nodes if n["id"] not in parents]


def counts(path: list[int], nodes: list[dict], cap: int) -> bool:
    """一條路算不算數：替身超過 fallback_max_per_path 幕的不算（不能成為定論、不露正文；異聞四用）。"""
    by_id = {n["id"]: n for n in nodes}
    return sum(1 for nid in path if by_id.get(nid, {}).get("fallback")) <= cap


def depth_of(node: dict | None) -> int:
    """站在這一個節點上，下一步是第幾步（0 號是開場：下一步第 1 步）。"""
    return 1 if node is None else int(node["depth"]) + 1


def labels(opening: dict, node: dict | None) -> list[str]:
    """站在這一個節點上的三個做法：開場是開場自帶的三個猜法；之後是那一幕存的做法（第三步沒有）。"""
    if node is None:
        return list(opening.get("guesses", []))
    return list(node.get("options") or [])


def fallback_options(table: dict[str, list[str]], *, season, tale, node, thing: str) -> list[str]:
    """引擎的退路做法三顆（fallback_options 一組一句，三顆用「／」隔開）。"""
    line = pick_line(table, "fallback_options", season=season, tale=tale, node=node)
    return [fill(x, thing=thing) for x in line.split("／")][:3]
