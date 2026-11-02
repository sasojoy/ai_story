"""成長的純規則（減法季整合設計 4.2、4.5；主機側實作計畫 Task 2-4、2-5）：遭遇的三道閘——疲勞（`fatigue_factor`、`nth_fight`）、
對手要配得上你（`outlevel_factor`）、45 級以後只認打出來的經驗（`exp_source`、`capped_exp`、`room_to_cap`）；屬性五段加點
（`reached`、`milestone_points`）與假人照路配點（`stat_path`、`plan_points`）。

cfg 是 `Config.jianfa`（`models.JianfaRules`，繼承 `jianfa_numbers.JianfaNumbers`；純規則的測試直接建後者）。不 import engine、不改狀態。
接線（批 2）：遭遇拍乘前兩道閘在探索包的 `explore_actions.fight_gate`（`PlayerState.fights_today`／`fight_day`）；十一處給經驗的地方標來源、
`team.player_exp`／`maxed_xinde`／`grant_team_exp`／`add_exp` 收來源；升級給點走 `team.level_points`（開著時照里程碑）；
`bot.allocate_points` 照路配。開關一律問 `rules.jianfa(content, world, "drill_gates"|"stat_milestones")`。
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .jianfa_numbers import JianfaNumbers
    from .models import Config

Source = Literal["battle", "other"]
BATTLE: Source = "battle"  # 打出來的經驗：45 級以後也照算
OTHER: Source = "other"  # 不是仗給的：到 drill_level_cap（45）為止，之後換心得

# 給經驗的地方標哪一種（接線時每一處傳一個；設計 4.2「交戰」＝任何一場仗，野外遭遇也算）。不在這兩張表的當場炸（ValueError）。
BATTLE_KINDS = frozenset({
    "encounter",  # 探索的遭遇拍：野外的對手、城裡的地痞
    "camp_spar",  # 自家營寨的遭遇：跟同袍比劃（Task 2-3，照 _drill_gains 給）
    "battle",  # 一般打贏（Game._battle_rewards）
    "boss",  # 頭目戰（_duel_finish）
    "sortie",  # 出陣打的那一場（_sortie_full、_sortie_drill；3b 之後是約戰的攻方）
    "answer",  # 應戰（3b）
    "spar",  # 切磋（_spar_record）
    "raid",  # 截殺
    "arena",  # 擂台
    "showdown",  # 全服決戰的軍餉（_showdown_pay）
    "challenge",  # 挑戰大勢人物本人，僵持也算（_challenge_draw）
    "dividend",  # 翻地分紅（_deliver_conquest；計畫 Task 2-4 歸仗：地是打下來的）
})
OTHER_KINDS = frozenset({
    "event",  # 事件
    "insight",  # 感悟
    "errand",  # 託付（批 6）
    "material",  # 素材拍
    "drill",  # 城裡操練（_town_drill）
    "bounty",  # 懸賞交付（bounties.deliver）
    "hold",  # 不打的：守、攪局、守勢行動、自家隊伍的零風險操練（_drill_gains 現在的呼叫點；計畫寫 _drill_gains 歸仗，見計畫 3.0）
})


def exp_source(kind: str) -> Source:
    """這一筆經驗算仗（BATTLE）還是不是仗（OTHER）。"""
    if kind in BATTLE_KINDS:
        return BATTLE
    if kind in OTHER_KINDS:
        return OTHER
    raise ValueError(f"不認得的經驗來源：{kind}")


# ── 第一道：疲勞 ──


def nth_fight(*, fight_day: int | None, fights_today: int, today: int) -> int:
    """這一場是今天第幾場（含這一場）：記的那一天（PlayerState.fight_day）不是今天就從 1 起算。today 照 Game._pill_day（台灣 00:00 換日）。
    接線：`n = nth_fight(...)`、存回 `fight_day = today`、`fights_today = n`。"""
    return (fights_today if fight_day == today else 0) + 1


def fatigue_factor(cfg: JianfaNumbers, fights_today: int) -> float:
    """今天第 fights_today 場（含這一場）的倍數：前 drill_full_per_day（15）場 1，之後每場再乘 drill_decay（0.8），最低 drill_floor（0.3）。
    只乘遭遇拍（含地痞）的經驗、心得、銀兩、素材；頭目、出陣、切磋不乘（設計 4.2、計畫 Task 2-4）。"""
    over = fights_today - cfg.drill_full_per_day
    if over <= 0:
        return 1.0
    return max(cfg.drill_floor, cfg.drill_decay**over)


# ── 第二道：對手要配得上你 ──


def outlevel_factor(cfg: JianfaNumbers, level: int, difficulty: float) -> float:
    """對手難度的檔（難度 // drill_outlevel_band）比自己等級的檔（等級 // drill_outlevel_band）低幾檔：不低 1，低一檔
    drill_outlevel_steps[0]（0.5），低兩檔以上照最後一個（0.1）。"""
    gap = int(level // cfg.drill_outlevel_band - difficulty // cfg.drill_outlevel_band)
    if gap <= 0:
        return 1.0
    steps = cfg.drill_outlevel_steps
    return steps[min(gap, len(steps)) - 1]


# ── 第三道：45 級以後只認打出來的經驗 ──


def capped_exp(cfg: JianfaNumbers, level: int, amount: int, source: Source, *, room: int) -> tuple[int, int]:
    """這一筆經驗（amount）拆成（算經驗的, 換心得的）：
    - 仗（BATTLE）的全算經驗（滿級換心得照舊是 team.maxed_xinde 的事）；
    - 不是仗的：本人已經到 drill_level_cap（45）全換心得；還沒到的只算到剛好升上 45 為止（room＝離 45 還差多少，`room_to_cap`），
      多出來的那一截換心得——不留在經驗裡，不然之後一場仗就帶著它升 46。
    換心得照 team.as_xinde（Config.maxed_exp_per_xinde 換 1）。給 0 或負的回 (0, 0)。"""
    if amount <= 0:
        return 0, 0
    if source == BATTLE:
        return amount, 0
    if level >= cfg.drill_level_cap:
        return 0, amount
    keep = min(amount, max(0, room))
    return keep, amount - keep


def room_to_cap(cfg: JianfaNumbers, config: Config, member) -> int:
    """本人（member：level、exp）離 drill_level_cap 還差多少經驗，照遊戲的升級表（team.level_cost，config 是遊戲的 Config）；
    已經到了是 0。"""
    from . import team  # noqa: PLC0415  team 之後會反過來 import 這裡（points_between 走里程碑），延後免得循環

    if member.level >= cfg.drill_level_cap:
        return 0
    return sum(team.level_cost(config, lv) for lv in range(member.level, cfg.drill_level_cap)) - int(member.exp)


# ── 屬性五段加點（設計 4.5）──

STATS = ("str", "agi", "con", "wis", "lore")  # 五條路：力、巧、韌、悟、博（同 team.COMBAT_STATS 的順序；這裡不 import team）


def reached(cfg: JianfaNumbers, before: int, after: int) -> list[int]:
    """從第 before 級升到第 after 級，跨過哪幾個境界（milestone_levels）。接線時最後一個記進 PlayerState.milestone_due（境界卡）。"""
    return [lv for lv in cfg.milestone_levels if before < lv <= after]


# 五個境界的名字（境界卡 main.milestone 的 title；設計 4.5 的例子是第 20 級「筋骨大成」）：佔位，待 joy 潤。milestone_levels 改了多出來的等級寫「第 N 級」
MILESTONE_TITLES = {10: "初窺門徑", 20: "筋骨大成", 30: "登堂入室", 40: "爐火純青", 50: "返璞歸真"}


def milestone_title(level: int) -> str:
    """境界卡上那一級的名字（MILESTONE_TITLES；沒寫的寫「第 N 級」）。"""
    return MILESTONE_TITLES.get(level, f"第 {level} 級")


def milestone_points(cfg: JianfaNumbers, before: int, after: int) -> int:
    """從第 before 級升到第 after 級拿幾點屬性：每跨過一個境界 stat_points_per_milestone（5）點；升級本身不再給點。
    開著時 team.points_between 走它（升級給點的五處都走 points_between）；同伴的每級成長照舊（growth_steps 的另一半不動）。"""
    return len(reached(cfg, before, after)) * cfg.stat_points_per_milestone


def stat_path(name: str) -> tuple[str, ...]:
    """假人照名號挑的一條路：五項屬性照「配點|名號|屬性」的雜湊排，第一項先配滿、再第二項……（設計 4.5「配滿一項是一條路」）。
    只看名號：同一個假人每一季走同一條路。不碰亂數。"""
    return tuple(sorted(STATS, key=lambda k: hashlib.sha256(f"配點|{name}|{k}".encode()).digest()))


def plan_points(stats: Mapping[str, float], points: int, cap: int, path: Sequence[str]) -> list[str]:
    """照路配 points 點，回要按的屬性（一點一個，依序走 Game.allocate_stat）：path 的第一項配到 cap，再下一項；全到頂就停，
    剩下的點留著。沒寫的屬性當 0（同 bot.allocate_points）。"""
    have = {k: stats.get(k, 0) for k in path}
    out: list[str] = []
    for k in path:
        while len(out) < points and have[k] < cap:
            have[k] += 1
            out.append(k)
    return out
