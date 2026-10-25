"""探索一顆（減法季整合設計 4.1；主機側實作計畫 Task 2-2）的純規則：這一處算哪一張表（`kind_of`）、這一趟每一拍的比重
（`weights`）、抽一拍（`roll`）、出門一趟抽幾拍（`draw`）、自己的亂數（`rng_for`）。

按一下「探索」＝出門一趟：連抽 `beats`（3）拍，每一拍照這一處的表抽一類——事件、遭遇、素材、感悟。素材與遭遇自動結算；
事件與感悟要玩家選（`CHOICE`），一趟最多一個、排最後。同一類一趟最多兩拍。

cfg 是 `jianfa_numbers.JianfaNumbers`（批 0 之後是 `Config.jianfa`）；地點只讀 `tags` 與 `danger`。不 import engine、不碰 Game.rng：
開關、選單、逐拍結算、段落與「剛剛」那一則都在引擎接線（Task 2-3，批 0 之後）。
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .jianfa_numbers import ExploreOneTable, JianfaNumbers

TOWN, TEMPLE, FORD, WILD, HILL, CAMP = "town", "temple", "ford", "wild", "hill", "camp"  # 六種地點（jianfa_numbers.ExploreKind）
EVENT, ENCOUNTER, MATERIAL, INSIGHT = "event", "encounter", "material", "insight"
KINDS = (EVENT, ENCOUNTER, MATERIAL, INSIGHT)  # 一拍的四類（比重的鍵照這個順序）
CHOICE = (EVENT, INSIGHT)  # 要玩家選的拍：一趟最多一個、排最後
MAX_SAME = 2  # 同一趟同一類最多幾拍
# 上一趟在這裡要選的那一拍若是這幾類，這一趟不再抽它：同一處的感悟是同一則（設計 4.1「同一處連續兩趟要選的拍不同一則」）。
# 事件不在這裡：事件的不重照舊交給 events.rotation_pool，連兩趟都抽到事件是兩則不同的。
REPEATS_SAME = (INSIGHT,)
FILL = MATERIAL  # 什麼都抽不出來的那一拍（比重全是 0、或能抽的都抽滿了）補素材


def match(cfg: JianfaNumbers, tags: Iterable[str]) -> ExploreOneTable | None:
    """這組地點標籤靠自己對得上哪一張表：照 `explore_tables` 的順序，第一張有共同標籤的；一個都對不上是 None。
    內容驗證（每個正式地點都歸得到一張）問它；探索本身問 `kind_of`。"""
    have = set(tags)
    return next((t for t in cfg.explore_tables if have & set(t.tags)), None)


def kind_of(cfg: JianfaNumbers, loc) -> ExploreOneTable:
    """這一處用哪一張表：`match`；標籤一張都對不上的歸最後一張（野）。"""
    return match(cfg, loc.tags) or cfg.explore_tables[-1]


def weights(cfg: JianfaNumbers, loc, *, has_foes: bool, bounty_here: bool = False) -> dict[str, int]:
    """這一處每一拍四類的比重（設計 4.1）：
    - 照表；危險度每多一星（一星就是表上的數字），遭遇 +`danger_shift`、事件 −`danger_shift`，這兩欄夾在 `beat_floor`～`beat_cap`；
    - 接了這裡的討伐懸賞（bounty_here）：遭遇 +`bounty_encounter_bonus`、夾在 `beat_cap`（懸賞那一路易手了也找得到，所以不看 has_foes）；
    - 沒接懸賞、這裡沒有對手（has_foes：引擎照此刻站的、不是自家的隊伍判）：遭遇是 0，那一份照比重分給其餘三類。
    地點自己寫了四欄（`Location.explore_mix`，設計 4.1 的覆寫）就照它，不照表的四欄。"""
    t = getattr(loc, "explore_mix", None) or kind_of(cfg, loc)
    got = {EVENT: t.event, ENCOUNTER: t.encounter, MATERIAL: t.material, INSIGHT: t.insight}
    shift = cfg.danger_shift * (loc.danger - 1)
    if shift:
        got[EVENT] = _clamp(cfg, t.event - shift)
        got[ENCOUNTER] = _clamp(cfg, t.encounter + shift)
    if bounty_here:
        got[ENCOUNTER] = min(cfg.beat_cap, got[ENCOUNTER] + cfg.bounty_encounter_bonus)
    elif not has_foes:
        got[ENCOUNTER] = 0
    return got


def _clamp(cfg: JianfaNumbers, value: int) -> int:
    return min(cfg.beat_cap, max(cfg.beat_floor, value))


def roll(rng: random.Random, weights: Mapping[str, float], exclude: Iterable[str] = ()) -> str | None:
    """照比重抽一類（比重是 0 的與 exclude 裡的不抽）；一類都抽不了是 None。擲一次 rng.random()。"""
    skip = set(exclude)
    pool = [(kind, w) for kind, w in weights.items() if w > 0 and kind not in skip]
    if not pool:
        return None
    x = rng.random() * sum(w for _, w in pool)
    for kind, w in pool:
        x -= w
        if x < 0:
            return kind
    return pool[-1][0]


def draw(
    cfg: JianfaNumbers, rng: random.Random, weights: Mapping[str, float], *,
    last_choice: str | None = None, bounty_here: bool = False,
) -> list[str]:
    """出門一趟的 `beats` 拍（設計 4.1）：一拍一拍照比重抽，
    - 同一類最多 `MAX_SAME`（2）拍；
    - 要選的拍（事件、感悟）最多一個，排最後；
    - last_choice：上一趟在這裡要選的那一拍是哪一類（換了地方就給 None）；是 `REPEATS_SAME` 的（感悟）這一趟不抽它；
    - bounty_here（接了這裡的討伐懸賞）：第一拍就是遭遇（比重裡遭遇是 0 時不放；weights 給了 bounty_here 就不會是 0）；
    - 什麼都抽不了的那一拍補素材（`FILL`）。
    「三拍都沒收穫補一個一階素材」看的是結算的結果，在引擎（Task 2-3）。"""
    beats: list[str] = [ENCOUNTER] if bounty_here and weights.get(ENCOUNTER, 0) > 0 else []
    while len(beats) < cfg.beats:
        exclude = {kind for kind in KINDS if beats.count(kind) >= MAX_SAME}
        if any(b in CHOICE for b in beats):
            exclude.update(CHOICE)
        if last_choice in REPEATS_SAME:
            exclude.add(last_choice)
        beats.append(roll(rng, weights, exclude) or FILL)
    return [b for b in beats if b not in CHOICE] + [b for b in beats if b in CHOICE]


def rng_for(season: int, name: str, serial: int, what: str) -> random.Random:
    """出門這一趟、這一個用途自己的亂數：季數｜名號｜第幾次探索（PlayerState.explore_seq）｜用途。決定性，不動 Game.rng；
    跟 `explore_modes.rng_for`（「探索|…」）分開，拍裡叫的舊結算照舊用它自己的。"""
    return random.Random(f"出門|{season}|{name}|{serial}|{what}")
