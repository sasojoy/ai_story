"""遊俠名號（散人的成長階梯，PM 2026-10-08 派工：「散人玩法對比加入陣營好像薄弱很多」）。

散人時攢的善名、惡名（只算加的）各記一本帳（PlayerState.ranger_good／ranger_evil），加上懸賞的功績（ranger_deeds），
俠名＝兩本帳取高的那一本＋功績；走哪條路看哪一本帳高（善名高是「俠」，惡名高是「寇」，一樣高算俠）。
名號分五階（0 是沒有名號），門檻在 Config.ranger.thresholds；每一階解鎖一樣東西（見 UNLOCKS）。

投靠了陣營就凍結：帳不再記、名號不顯示、好處不給（陣營的人走 ranks 的頭銜），存檔照留；
現在沒有從陣營回到散人的路（叛投是換到另一個陣營），所以凍結了就是這一季都凍結。換季整個重來（新角色）。

只有第一季的規則開著（rules.season_one）才有；開關關著時什麼都不記、什麼都不給。不 import engine。"""
from __future__ import annotations

from . import rules  # 與 rules、roster 互相 import：只能引入整個模組、呼叫時才取屬性
from .models import Content
from .state import GameState

PATHS = ("俠", "寇")
# 第 0～4 階的名號（第 0 階不寫在狀態列上，只出現在名號的說明裡）
TITLES: dict[str, list[str]] = {
    "俠": ["無名小卒", "江湖遊俠", "一方豪俠", "州郡大俠", "天下名俠"],
    "寇": ["無名小卒", "綠林好漢", "江湖巨寇", "州郡大盜", "天下大盜"],
}


def active(state: GameState, content: Content) -> bool:
    """這個人此刻有遊俠名號可言：第一季開著、而且是散人（投靠了陣營就凍結）。"""
    return state.player.faction is None and rules.season_one(content, state.world)


def note_gain(state: GameState, content: Content, key: str, delta: int) -> None:
    """善名、惡名加了 delta（rules.apply_effect 照實際動了多少呼叫）：散人才記進那一本帳。"""
    if delta <= 0 or not active(state, content):
        return
    p = state.player
    if key == "good":
        p.ranger_good += delta
    elif key == "evil":
        p.ranger_evil += delta


def add_deeds(state: GameState, content: Content, points: int) -> int:
    """懸賞的功績：散人才記；回傳真的記了多少（陣營的人是 0）。"""
    if points <= 0 or not active(state, content):
        return 0
    state.player.ranger_deeds += points
    return points


def path(state: GameState) -> str:
    p = state.player
    return "寇" if p.ranger_evil > p.ranger_good else "俠"


def points(state: GameState) -> int:
    p = state.player
    return max(p.ranger_good, p.ranger_evil) + p.ranger_deeds


def tier_of(content: Content, value: int) -> int:
    return sum(1 for need in content.config.ranger.thresholds if value >= need)


def tier(state: GameState, content: Content) -> int:
    """此刻的階（0～4）；沒有名號可言（陣營的人、開關關著）是 0。"""
    return tier_of(content, points(state)) if active(state, content) else 0


def title(content: Content, state: GameState) -> str | None:
    """狀態列寫在名號後面的那一段（「江湖遊俠」）；第 0 階、陣營的人、開關關著是 None。"""
    t = tier(state, content)
    return TITLES[path(state)][t] if t > 0 else None


def audience_discount(state: GameState, content: Content) -> int:
    """求見門檻抵幾點（第 1 階起每一階 audience_per_tier，對所有人物都算）。"""
    return tier(state, content) * content.config.ranger.audience_per_tier


def recruit_bonus(state: GameState, content: Content) -> float:
    """招募成功率加多少（第 2 階起每一階 recruit_per_tier）。"""
    return max(0, tier(state, content) - 1) * content.config.ranger.recruit_per_tier


def exp_factor(state: GameState, content: Content) -> float:
    """打贏一場拿的經驗乘多少（第 1 階起每一階 exp_per_tier）：陣營的人跟自己人操練拿經驗，散人在外頭闖蕩、每一仗學得多一些。"""
    return 1.0 + tier(state, content) * content.config.ranger.exp_per_tier


def bounty_factor(state: GameState, content: Content) -> float:
    """懸賞的銀兩乘多少（到 bounty_bonus_tier 階才有）。"""
    cfg = content.config.ranger
    return cfg.bounty_bonus if tier(state, content) >= cfg.bounty_bonus_tier else 1.0


def unlocks(content: Content) -> list[str]:
    """第 1～4 階各解鎖什麼（說明用；數字照 Config）。"""
    cfg = content.config.ranger
    out = []
    for t in range(1, len(cfg.thresholds) + 1):
        parts = [f"求見門檻 -{t * cfg.audience_per_tier}", f"打贏的經驗 +{round(t * cfg.exp_per_tier * 100)}%"]
        if t >= 2:
            parts.append(f"招募 +{round((t - 1) * cfg.recruit_per_tier * 100)}%")
        if t == cfg.qiyu_tier:
            parts.append("遇得上散人才有的奇遇")
        if t == cfg.bounty_bonus_tier:
            parts.append(f"懸賞銀兩 ×{cfg.bounty_bonus:g}")
        out.append("、".join(parts))
    return out


def status(state: GameState, content: Content) -> dict | None:
    """狀態列與人物卡用的資料：名號、階、俠名、下一階要多少、這一階解鎖了什麼。不是散人、開關關著是 None。"""
    if not active(state, content):
        return None
    cfg = content.config.ranger
    value, t, way = points(state), tier(state, content), path(state)
    upcoming = cfg.thresholds[t] if t < len(cfg.thresholds) else None
    return {
        "title": TITLES[way][t],
        "tier": t,
        "path": way,
        "points": value,
        "next": upcoming,
        "next_title": TITLES[way][t + 1] if upcoming is not None else None,
        "perks": unlocks(content)[t - 1] if t > 0 else "",
    }
