"""機緣與伏筆的底座（全部拆包第 34 批「軍情二」；主人：軍情包 features/military；手冊 3.3、3.10 的查詢服務）。

核心與共用規則層讀機緣、伏筆的「只讀」那一小半留在這裡：核心的 rules（晉升條件的糧草換算）、content（驗內容讀天機表與題目）、
共用規則層待收的 ranks（召見問「這一階的機緣做過沒」）、叛投確認畫面（defection：手上有沒有沒收場的密謀）都經它，不 import 軍情包
（核心與共用規則層不准 import 包）。軍情包的 fs_rules、opp_rules 從這裡 re-export 同一批名字，所以舊名
`tianxia.foreshadow.need`、`tianxia.opportunities.done_for_rank` 照舊拿到同一個函式。

原本寫在 tianxia/foreshadow.py（GUANYIN、TIANJI、FIGURE_SLOT、TIANJI_ANSWER、scale、need、trips、_asks、asks_of）與
tianxia/opportunities.py（done_for_rank、_live、in_plot），一個字沒改。與 event_check 同樣不進 MODULES（tianxia/core/ 底下的檔本來就是核心）。
"""
from __future__ import annotations

import math
from collections.abc import Iterator

from ..models import Content, FsAsk, FsChain, FsFinal, FsStep
from ..state import GameState, Plot

GUANYIN = "guanyin"  # 官銀的計數鍵（PlayerState.fs_counters）
# 天機（伏筆文件 2.9）：同一個天機、同一個 key 永遠同一個答案。廣宗的內鬼（mole）是黃巾第 4 階機緣「營中的內鬼」
# （正式版乙二，opportunities 的推理型）用的，伏筆的鏈沒有用它
TIANJI: dict[str, tuple[str, ...]] = {
    "wind": ("東", "南", "西", "北"),
    "disguise": ("鹽車", "棺木", "香客", "商隊"),
    "mole": ("clerk", "priest", "strongman"),  # 廣宗的內鬼（伏筆文件 2.9；黃巾第 4 階機緣「營中的內鬼」）
}
FIGURE_SLOT = "{人物}"  # 最後一步的敘事裡「出面的那位」：figure 在那條戰線上就是他，否則是 stand_in
TIANJI_ANSWER = "tianji:"  # 答案寫成 tianji:<key>


# ── 伏筆：換算與題目 ───────────────────────────────────────


def scale(content: Content) -> float:
    """需求量的係數（伏筆文件 2.8、Config.foreshadow_tiers）：人數上限未滿哪一檔就用那一檔；都不是（1000 人以上）是 1。"""
    players = content.config.server_max_players
    for bound, factor in content.config.foreshadow_tiers:
        if players < bound:
            return factor
    return 1.0


def need(content: Content, base: int) -> int:
    """基準量換算成這個伺服器的需求量：乘上係數、無條件進位、最少 1。基準量 0（或更少）就是不要，回 0。"""
    if base <= 0:
        return 0
    return max(1, math.ceil(round(base * scale(content), 9)))


def trips(final: FsFinal) -> list[FsStep]:
    """最後一步的每一趟：寫了 steps 就是 steps，否則 final 自己就是那一趟。"""
    return list(final.steps) if final.steps else [final]


def _asks(trip: FsStep) -> list[FsAsk]:
    if not trip.question:
        return []
    main = FsAsk.model_construct(question=trip.question, options=list(trip.options), answer=trip.answer or "")
    return [main, *trip.then]


def asks_of(c: FsChain) -> Iterator[tuple[str, FsAsk]]:
    """每一趟的每一道題（給內容檢查用）：(哪裡, 題)。"""
    for i, trip in enumerate(trips(c.final)):
        for j, ask in enumerate(_asks(trip)):
            yield f"第 {i + 1} 趟第 {j + 1} 題", ask


# ── 機緣：召見與叛投確認畫面問的 ───────────────────────────


def done_for_rank(state: GameState, content: Content, rank: int) -> bool:
    """這一季替目前陣營完成過第 rank 階的任一種機緣（同一階完成任一種就夠，機緣文件第一節）；計畫丙的召見讀它。"""
    p = state.player
    return any(o.rank == rank and o.faction == p.faction and o.id in p.opp_done for o in content.opportunities)


def _live(state: GameState, plot: Plot) -> bool:
    """還在進行：開著、沒過期、而且這一季還沒落幕（休季什麼都不能再加）。"""
    return plot.status == "open" and state.world.time <= plot.deadline and not state.world.ended


def in_plot(state: GameState) -> bool:
    """響應或牽頭過、還沒收場也沒領的密謀：還開著（沒過期）的，或已經完成但自己還沒結算的。叛投的確認畫面讀它。"""
    p = state.player
    return any(
        p.name in x.members and x.id not in p.opp_settled and x.faction == p.faction and (_live(state, x) or x.status == "done")
        for x in state.world.plots
    )
