"""走一趟（企劃者 2026-10-29～30；設計稿 https://claude.ai/artifact/RJu4dK5cZoQcEe8SHphktc）：按一次探索走一、三、五段，
每一段就是現行的一次探索（Game._explore_one：一樣的表、一樣扣體力、一樣寫一則江湖紀錄），只是串起來演。

- 素材、遭遇自動走；端出要選的事（事件、有所感、頭目）就停在那一段，玩家選完再接著走（Game.outing_go 不帶段數）。
- 打輸、一段走完氣血低於上限的 outing_turn_back 就回頭；沒走的段不扣體力（體力是一段一段扣的）。
- 段數越多稀有的越容易來（rare_boost）：奇遇事件、一條線的開頭、二階素材、特殊頓悟的機率乘這一趟的倍數。畫面不寫倍數。

這裡只放純規則（開關、倍數、這一趟還在不在路上、畫面那一份）；走路本身在引擎（Game.outing_go、Game._outing_walk）。
"""

from __future__ import annotations

from .models import Content
from .rules import jianfa
from .state import GameState, Outing

DONE, LOST, HURT, TIRED, LEFT = "done", "lost", "hurt", "tired", "left"
# 收尾那一句（待 joy 潤）：走完不另說，結算卡自己寫「走完一趟」
END_LINES = {
    LOST: "負傷退回，剩下的路不走了。",
    HURT: "氣血見底，先回頭了。",
    TIRED: "體力不夠，先回頭了。",
    LEFT: "人已經離開了那裡，這一趟就到這裡。",
}
END_TITLES = {DONE: "走完一趟", LOST: "負傷退回", HURT: "回頭", TIRED: "回頭", LEFT: "中途離開"}
# 選段數時那一行（Joy 10/30「有顯示多段的時候越容易獲得更好獎勵的資訊就夠了」；待 joy 潤）
MORE_IS_RARER = "走得越遠，越容易碰上稀有的東西。"


def on(content: Content, state: GameState) -> bool:
    """走一趟開著：減法季的探索一顆開著，而且 outing 子開關也開著（rules.jianfa）。"""
    world = state.world
    return jianfa(content, world, "explore_one") and jianfa(content, world, "outing")


def segments(content: Content) -> list[int]:
    return list(content.config.jianfa.outing_segments)


def active(state: GameState) -> Outing | None:
    """還在路上的那一趟（沒收、人還在出發的地方）；沒有是 None。"""
    trip = state.player.outing
    if trip is None or trip.end or trip.place != state.player.location:
        return None
    return trip


def rare_boost(state: GameState, content: Content) -> float:
    """此刻稀有的東西乘多少：在路上照這一趟幾段（Config.jianfa.outing_rare），不在路上是 1（跟以前一模一樣）。"""
    trip = active(state)
    if trip is None or not on(content, state):
        return 1.0
    return float(content.config.jianfa.outing_rare.get(str(trip.total), 1.0))


def cost(content: Content, total: int) -> int:
    return content.config.jianfa.explore_stamina * total


def view(state: GameState, content: Content) -> dict | None:
    """/api/main 的 outing：網頁照它畫探索鈕的段數選單（picker）與走一趟的畫面（trip）。關著是 None（網頁照舊一顆探索）。"""
    if not on(content, state):
        return None
    p = state.player
    picker = [{"n": n, "stamina": cost(content, n), "ok": p.stamina >= cost(content, n)} for n in segments(content)]
    trip = p.outing
    out = {"picker": picker, "note": MORE_IS_RARER, "trip": None}
    if trip is not None:
        out["trip"] = {
            "place": content.locations[trip.place].name if trip.place in content.locations else trip.place,
            "total": trip.total, "done": trip.done, "end": trip.end,
            "waiting": not trip.end and bool(trip.beats) and trip.beats[-1].stop,
            "title": END_TITLES.get(trip.end, ""), "end_line": END_LINES.get(trip.end, ""),
            "beats": [b.model_dump() for b in trip.beats],
        }
    return out
