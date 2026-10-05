"""機緣（機緣文件；正式版乙一）：升第 3、4 階除了貢獻門檻，還要完成一種機緣。

這一份管：誰做得了（自己陣營；第 4 階要已經是第 3 階）、情誼型的對話話題、累積型的計數與交付、天時地利型的
時段與檢定、線索。完成只寫一句個人敘事，不發任何傳聞。需求量照伏筆的分檔換算（foreshadow.need）。
只有第一季的規則開著才有（rules.season_one）。拼圖、推理、集體密謀在計畫乙二。"""
from __future__ import annotations

from . import foreshadow, ranks
from .models import Content, OppDef
from .rules import season_one
from .state import GameState, PlayerState

DONE = "（機緣「{name}」完成。）"


def active(state: GameState, content: Content) -> bool:
    return season_one(content, state.world) and bool(content.opportunities)


def open_ones(state: GameState, content: Content) -> list[OppDef]:
    """這個人此刻做得了、還沒完成的機緣：自己陣營的；第 3 階的投靠了就行，第 4 階的要已經是第 3 階（機緣文件第一節）。"""
    p = state.player
    if not active(state, content) or p.faction is None:
        return []
    rank = ranks.rank_of(state)
    return [
        o for o in content.opportunities
        if o.faction == p.faction and o.id not in p.opp_done and (o.rank == 3 or rank >= 3)
    ]


def done_for_rank(state: GameState, content: Content, rank: int) -> bool:
    """這一季替目前陣營完成過第 rank 階的任一種機緣（同一階完成任一種就夠，機緣文件第一節）；計畫丙的召見讀它。"""
    p = state.player
    return any(o.rank == rank and o.faction == p.faction and o.id in p.opp_done for o in content.opportunities)


def clear(p: PlayerState) -> None:
    """叛投時清掉機緣的一切（機緣文件第一節：換季、叛投清掉）。換季不用叫：角色每季重來。
    rank2_days 不清：那是每人每曆日第 2 階行動的限次，不屬於哪個陣營的進度，叛投不能拿來重置它。"""
    p.opp_done, p.opp_counts, p.opp_items, p.opp_fronts, p.opp_clues, p.opp_tried = [], {}, {}, {}, [], {}


def _complete(state: GameState, opp: OppDef) -> list[str]:
    """記下完成、收掉這一種的計數與物品；回傳那一行「（機緣「…」完成。）」。不發傳聞。"""
    p = state.player
    p.opp_done.append(opp.id)
    p.opp_counts.pop(opp.id, None)
    p.opp_items.pop(opp.id, None)
    p.opp_fronts.pop(opp.id, None)
    return [DONE.format(name=opp.name)]


# ── 情誼型：對話的話題 ─────────────────────────────────


def _topics(state: GameState, content: Content, companion_id: str) -> list[OppDef]:
    return [
        o for o in open_ones(state, content)
        if o.kind == "bond" and o.bond.character == companion_id
        and state.player.affinities.get(companion_id, 0) >= foreshadow.need(content, o.bond.affinity)
    ]


def talk_options(state: GameState, content: Content, companion_id: str) -> list:
    """對話選單上的話題 talk:opp:<id>（標籤是話題）：自己陣營的情誼型、情誼夠、還沒完成、在跟的就是這位才有。"""
    from .engine import Option  # noqa: PLC0415  延後 import：engine → opportunities

    return [Option(id=f"talk:opp:{o.id}", label=o.bond.topic) for o in _topics(state, content, companion_id)]


def hear_topic(state: GameState, content: Content, companion_id: str, opp_id: str) -> list[str]:
    """按了話題：回他說的話（不經模型、不扣體力、不算對話輪數），完成這一種機緣。選項不在了就回空串列。"""
    for o in _topics(state, content, companion_id):
        if o.id == opp_id:
            return [o.bond.text] + _complete(state, o)
    return []
