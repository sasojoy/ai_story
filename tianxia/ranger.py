"""遊俠名號（散人的成長階梯，PM 2026-10-08 派工：「散人玩法對比加入陣營好像薄弱很多」）。

散人時攢的善名、惡名（只算加的）各記一本帳（PlayerState.ranger_good／ranger_evil），加上懸賞的功績（ranger_deeds），
俠名＝兩本帳取高的那一本＋功績；走哪條路看哪一本帳高（善名高是「俠」，惡名高是「寇」，一樣高算俠）。
名號分五階（0 是沒有名號），門檻在 Config.ranger.thresholds；每一階解鎖一樣東西（見 UNLOCKS）。

投靠了陣營就凍結：帳不再記、名號不顯示、好處不給（陣營的人走 ranks 的頭銜），存檔照留；
現在沒有從陣營回到散人的路（叛投是換到另一個陣營），所以凍結了就是這一季都凍結。換季整個重來（新角色）。

每季都有（企劃者 2026-10-10，懸賞榜設計 2.2）：只看是不是散人、劇本有沒有陣營（沒有陣營就沒有「散人」可言，測試內容因此不記），
不看第一季開關（先例是叛投 defection.can_defect）。不 import engine。"""
from __future__ import annotations

from . import gender, renown
from .models import Content
from .state import GameState

PATHS = ("俠", "寇")
# 第 0～4 階的名號（第 0 階不寫在狀態列上，只出現在名號的說明裡）
TITLES: dict[str, list[str]] = {
    "俠": ["無名小卒", "江湖遊俠", "一方豪俠", "州郡大俠", "天下名俠"],
    "寇": ["無名小卒", "綠林好漢", "江湖巨寇", "州郡大盜", "天下大盜"],
}
FEMALE_TITLES = renown.FEMALE_TITLES  # 女的名號換字（PM 2026-10-12）：表搬到 renown（名聲設計 2.2），這裡照舊讀得到


def _named(name: str, state: GameState) -> str:
    return FEMALE_TITLES.get(name, name) if gender.female(state) else name


def merged(content: Content) -> bool:
    """名聲開著：遊俠名號併進善惡稱號（名聲設計 2.3）。舊的帳（ranger_good／evil／deeds）不再記也不再讀，欄位留著讓舊存檔讀得進來；
    散人原本的好處（求見、經驗、招募、奇遇、懸賞）照舊只給散人，階改讀善惡稱號的段（renown.virtue_tier）。"""
    return renown.on(content)


def active(state: GameState, content: Content) -> bool:
    """這個人此刻有遊俠名號可言：劇本有陣營、而且是散人（投靠了陣營就凍結）。每季都有，不看第一季開關。"""
    return state.player.faction is None and bool(content.scenario.factions)


def note_gain(state: GameState, content: Content, key: str, delta: int) -> None:
    """善名、惡名加了 delta（rules.apply_effect 照實際動了多少呼叫）：散人才記進那一本帳。"""
    if delta <= 0 or merged(content) or not active(state, content):
        return
    p = state.player
    if key == "good":
        p.ranger_good += delta
    elif key == "evil":
        p.ranger_evil += delta


def add_deeds(state: GameState, content: Content, points: int) -> list[str]:
    """懸賞的功績：散人才記，回寫進紀錄的那一行（陣營的人是空的）。名聲開著時照交差那一刻走的路記成善名或惡名（名聲設計 2.3，
    第十一節第 3 題甲）；關著照舊記俠名。善名、惡名改了，跨段與悟浩然、血煞在 Game._log 那一下一起比（renown.watch）。"""
    if points <= 0 or not active(state, content):
        return []
    if merged(content):
        key = renown.BOOKS[renown.path(state)]
        state.player.stats[key] = state.player.stats.get(key, 0) + points
        return [f"{content.config.stat_names.get(key, key)} +{points}"]
    state.player.ranger_deeds += points
    return [f"俠名 +{points}"]


def path(state: GameState, content: Content | None = None) -> str:
    """走哪一條路。給了 content、名聲開著時照善名惡名（renown.path）；其餘照舊看兩本帳。"""
    if content is not None and merged(content):
        return renown.path(state)
    p = state.player
    return "寇" if p.ranger_evil > p.ranger_good else "俠"


def points(state: GameState) -> int:
    p = state.player
    return max(p.ranger_good, p.ranger_evil) + p.ranger_deeds


def tier_of(content: Content, value: int) -> int:
    return sum(1 for need in content.config.ranger.thresholds if value >= need)


def tier(state: GameState, content: Content) -> int:
    """此刻的階（0～4）：名聲開著時是善惡稱號的段（renown.virtue_tier），只有散人才有；關著照舊看俠名。
    沒有名號可言（陣營的人、劇本沒有陣營）是 0。"""
    if not active(state, content):
        return 0
    return renown.virtue_tier(state, content) if merged(content) else tier_of(content, points(state))


def title(content: Content, state: GameState) -> str | None:
    """狀態列寫在名號後面的那一段（「江湖遊俠」）；第 0 階、陣營的人、劇本沒有陣營是 None。
    名聲開著時一律 None：稱號改寫在名聲那一行（名聲設計 2.5，social.affiliation 不再接）。"""
    if merged(content):
        return None
    t = tier(state, content)
    return _named(TITLES[path(state)][t], state) if t > 0 else None


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
    """狀態列與人物卡用的資料：名號、階、俠名、下一階要多少、這一階解鎖了什麼。不是散人、劇本沒有陣營是 None。
    名聲開著時也是 None：換成 renown.status（散人的好處列在說明卡上）。"""
    if merged(content) or not active(state, content):
        return None
    cfg = content.config.ranger
    value, t, way = points(state), tier(state, content), path(state)
    upcoming = cfg.thresholds[t] if t < len(cfg.thresholds) else None
    return {
        "title": _named(TITLES[way][t], state),
        "tier": t,
        "path": way,
        "points": value,
        "next": upcoming,
        "next_title": _named(TITLES[way][t + 1], state) if upcoming is not None else None,
        "perks": unlocks(content)[t - 1] if t > 0 else "",
    }
