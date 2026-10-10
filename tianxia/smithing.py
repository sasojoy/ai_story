"""打造與淬煉（docs/superpowers/specs/2026-10-09-兵器-design.md 4.2～4.4、4.7；兵器第二批：自己打造）。

| 誰 | 做什麼 |
|---|---|
| 模型 | 只替這一季第一次打出來的配方取名字＋一句說明（三段式），一個數字都不碰 |
| 引擎 | 配方鍵、屬性、階、工錢、品質擲骰、全服登記、淬煉 |

這個模組 import team 與 fusion（品質的推法、悟性、天時地利）；team 會 import weapons，所以 weapons 不能 import 這裡。
鐵匠鋪的選單項（Option）在 engine 裡，回選單的函式延後 import（同 foreshadow.talk_options）。"""
from __future__ import annotations

from collections import Counter

from . import fusion, team, weapons
from .fusion import QualityOdds
from .insights import merged_attribute
from .models import WEAPON_KINDS, Content
from .state import GameState
from .world_state import WorldStateStore

NOT_ENOUGH = "身上的素材不到兩個"  # 待 joy 潤


def tier_of(content: Content, main: str) -> int:
    """打出來的階照主料的階（4.2）。"""
    return content.materials[main].tier


def price(content: Content, tier: int) -> int:
    """打一把這一階的工錢（4.2，Config.weapons.forge_silver）。"""
    return content.config.weapons.forge_silver.get(str(tier), 0)


def attribute_with(content: Content, tianji: int, kind: str, main: str, aux: str) -> str:
    """打出來的屬性（4.2）：照 insights.merged_attribute，種子是「天機|配方鍵」（同 fusion.recipe_seed），所以同一季同一個配方一樣。
    同屬性與四對（剛快、柔慢、快柔、剛慢）合出來的跟主輔順序無關；其餘組合（剛柔、快慢）照種子的雜湊挑兩者之一，配方鍵分主輔，
    主輔對調是另一個配方，挑到的屬性可能不同（4.4：主輔不交換）。選單一次要算好幾個時先讀一次天機，用這一個。"""
    seed = f"{tianji}|{weapons.recipe_key(kind, main, aux)}"
    return merged_attribute(content.materials[main], content.materials[aux], seed)


def attribute_of(world: WorldStateStore, content: Content, kind: str, main: str, aux: str) -> str:
    return attribute_with(content, world.read().tianji, kind, main, aux)


def forge_problem(state: GameState, content: Content, kind: str, main: str, aux: str) -> str | None:
    """打不成的原因；None＝打得成。順序：不在鐵匠鋪、種類、素材認不得、素材不夠（主輔同一種要兩個）、裝備庫滿、銀兩不夠。
    鐵匠鋪的鈕灰掉時寫它，C 段（forge）也再驗一次。"""
    if not weapons.smith_here(state, content):
        return weapons.NOT_HERE
    if kind not in WEAPON_KINDS:
        return "沒有這種兵器"
    if main not in content.materials or aux not in content.materials:
        return "沒有這種素材"
    held = state.player.materials
    for mid, need in Counter([main, aux]).items():
        if held.get(mid, 0) < need:
            return f"{content.materials[mid].name}不夠（要 {need} 個）"
    if weapons.rack_full(state, content):
        return weapons.RACK_FULL
    short = price(content, tier_of(content, main)) - state.player.stats.get("silver", 0)
    return f"還差 {short} 兩" if short > 0 else None


def setting_points(state: GameState, content: Content, attribute: str) -> list[tuple[str, float]]:
    """打造的天時地利（附帶決定 b）：地利、戰場、心靜都同合成（地利看此地探索悟得到同屬性的意境）。最多 setting_max 條。
    兵器沒有正邪，所以合成的「晝夜」這裡沒有。"""
    rule = content.config.weapons.quality
    out: list[tuple[str, float]] = []
    if rule.terrain and fusion.terrain_here(state, content, attribute):
        out.append(("terrain", rule.terrain))
    if rule.battlefield and attribute == "剛" and fusion.battlefield_here(state, content):
        out.append(("battlefield", rule.battlefield))
    if rule.calm and fusion.calm_now(state, rule.calm_hours):
        out.append(("calm", rule.calm))
    out.sort(key=lambda item: -abs(item[1]))
    return out[: rule.setting_max]


def setting_line(content: Content, scored: list[tuple[str, float]]) -> list[str]:
    """結果多一句含蓄的話：天時地利合起來加分寫 setting_good、扣分寫 setting_bad；沒有、或那句是空的就不寫。"""
    rule = content.config.weapons.quality
    total = sum(points for _, points in scored)
    line = rule.setting_good if total > 0 else rule.setting_bad if total < 0 else ""
    return [line] if line else []


def forge_odds(state: GameState, content: Content, world: WorldStateStore, kind: str, main: str, aux: str) -> QualityOdds:
    """這一爐的品質機率（4.3）：輔料的階（比主料高幾階）、悟性、熟手（這個配方這一季打過幾次，有上限）、天時地利，
    從 Config.weapons.quality.odds 推（fusion.odds_from_points）。只看這一爐的組成，配方有沒有人打過都一樣。"""
    rule = content.config.weapons.quality
    m, a = content.materials[main], content.materials[aux]
    wis = state.player.stats.get("wis", team.BASE_STAT)
    done = state.player.forge_counts.get(weapons.recipe_key(kind, main, aux), 0)
    scored = [
        ("aux", rule.aux_tier.get(str(a.tier - m.tier), 0.0)),
        ("wis", (team.stat_factor(content, wis) - 1) * 100 * rule.wis_weight),
        ("practice", min(rule.practice_cap, rule.practice_point * done)),
    ]
    scored += setting_points(state, content, attribute_of(world, content, kind, main, aux))
    return fusion.odds_from_points(scored, rule, rule.odds)
