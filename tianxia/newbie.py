"""新手目標（新手引導重做，Joy 2026-10-22 同意設計稿第六節 https://claude.ai/artifact/Eb25MwPveJMYSf5Ge4mDyx；Config.training）。

引導走完之後任務卡多一塊：新手期（roster.newbie，正式內容是加入這一季起現實 48 小時）裡一條一條寫「接下來做什麼」，
做到一條給一點小獎勵（回體丹或銀兩）。規則都在這裡、照角色的狀態判斷，假人做到同樣的事也照拿（畫面上看不出誰是假人）。
有幾條看「做過了沒」的記號（PlayerState.newbie_marks，在做那件事的地方記：合出新意境、在二級以上打贏練功、酒肆花錢打聽、
上擂台、選「就當散人」）；其餘照現有的狀態（等級、自創門數、懸賞交差數、陣營）。拿過獎勵的記在 newbie_done，一條只給一次。
純函式：引擎（Game._check_newbie、Game.newbie_view）接線。"""
from __future__ import annotations

from dataclasses import dataclass

from . import prologue, roster
from .models import Content
from .state import GameState

DRIFTER = "drifter"  # 任務卡「就當散人」記的那一個記號
TITLE = "新手目標"  # 江湖紀錄的標題、任務卡那一塊的小標
DONE_LINE = "✔ 新手目標「{text}」做到了："  # 待 joy 潤
DRIFTER_LINE = "你決定誰也不跟，就當個散人，天下照樣走得。"  # 任務卡按「就當散人」那一句。待 joy 潤


@dataclass(frozen=True)
class Goal:
    key: str
    text: str
    reward: str  # "pill" 回體丹、"silver" 銀兩（數量在 Config.training.goal_pill／goal_silver）
    go: str  # 「去做」帶去哪：practice0／practice1 最近的一級／二級練功點、craft／practice 分頁、bounties／tavern／arena 最近有的城、map 輿圖
    outing_text: str = ""  # 減法季探索一顆開著時換的字（那一季沒有「尋敵」這顆鈕了，FB-816）；沒寫就是 text。待 joy 潤


GOALS = (  # 設計稿第六節的表，照這個順序亮（一次亮最上面三條沒做完的）
    Goal("level5", "升到第 5 級", "pill", "practice0"),
    Goal("merge", "悟第二個意境，在煉製合出一個新的", "pill", "craft"),
    Goal("field2", "到匪寇橫行的地方尋敵，打贏一場", "silver", "practice1", "到匪寇橫行的地方出門探索，打贏一場"),
    Goal("create", "自創第一門武學", "pill", "practice"),
    Goal("bounty", "揭一張懸賞並交差", "silver", "bounties"),
    Goal("tavern", "在酒肆打聽一件事", "silver", "tavern"),
    Goal("side", "投靠一方，或選「就當散人」", "pill", "map"),
    Goal("arena", "上一次擂台", "silver", "arena"),
)
SHOWN = 3


def on(content: Content) -> bool:
    return content.config.training.goals


def text_of(state: GameState, content: Content, goal: Goal) -> str:
    """這一條現在寫什麼字：減法季探索一顆開著時（rules.jianfa 的 explore_one）用 outing_text，其餘照舊。任務卡、本週卡、做到了的那一句都走它。"""
    from .rules import jianfa  # noqa: PLC0415  rules 很大，這裡只在畫字時才用

    return goal.outing_text if goal.outing_text and jianfa(content, state.world, "explore_one") else goal.text


def met(state: GameState, goal: Goal) -> bool:
    p = state.player
    if goal.key == "level5":
        return p.member.level >= 5
    if goal.key == "create":
        return p.created_count >= 1
    if goal.key == "bounty":
        return p.bounties_done >= 1
    if goal.key == "side":
        return p.faction is not None or DRIFTER in p.newbie_marks
    return goal.key in p.newbie_marks


def active(state: GameState, content: Content) -> bool:
    """這一塊還在：開著、引導（序章與初入江湖）走完或略過了、新手期還沒過、還有沒拿過的。"""
    from .guide import tutorial_active  # noqa: PLC0415  guide 讀 prologue，這裡在它之後

    p = state.player
    return (on(content) and not prologue.active(state, content) and not tutorial_active(state, content)
            and roster.newbie(state, content) and any(g.key not in p.newbie_done for g in GOALS))


def reward_text(content: Content, goal: Goal) -> str:
    cfg = content.config
    if goal.reward == "pill":
        return f"{cfg.stamina_pill_name} +{cfg.training.goal_pill}"
    return f"銀兩 +{cfg.training.goal_silver}"


def grant(state: GameState, content: Content) -> list[tuple[str, str]]:
    """做到、還沒拿過的照順序發獎勵（新手期裡才發）：回 [(那一句, 數值變化)]。"""
    if not active(state, content):
        return []
    p, cfg = state.player, content.config.training
    out = []
    for goal in GOALS:
        if goal.key in p.newbie_done or not met(state, goal):
            continue
        p.newbie_done.add(goal.key)
        if goal.reward == "pill":
            p.stamina_pills += cfg.goal_pill
        else:
            p.stats["silver"] = p.stats.get("silver", 0) + cfg.goal_silver
        out.append((DONE_LINE.format(text=text_of(state, content, goal)), reward_text(content, goal)))
    return out


def todo(state: GameState) -> list[Goal]:
    """還沒拿過的，最上面 SHOWN 條。"""
    return [g for g in GOALS if g.key not in state.player.newbie_done][:SHOWN]
