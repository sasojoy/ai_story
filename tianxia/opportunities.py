"""機緣（機緣文件；正式版乙一）：升第 3、4 階除了貢獻門檻，還要完成一種機緣。

這一份管：誰做得了（自己陣營；第 4 階要已經是第 3 階）、情誼型的對話話題、累積型的計數與交付、天時地利型的
時段與檢定、線索。完成只寫一句個人敘事，不發任何傳聞。需求量照伏筆的分檔換算（foreshadow.need）。
只有第一季的規則開著才有（rules.season_one）。拼圖、推理、集體密謀在計畫乙二。"""
from __future__ import annotations

import random

from . import calendar, figures, foreshadow, ranks
from .models import Content, OppDef, Rank2Action
from .rules import GEJU, change_trend, front_of, season_one
from .state import GameState, PlayerState

DONE = "（機緣「{name}」完成。）"
NOT_NOW = "（此刻無法這麼做。）"


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


# ── 第 2 階行動（設計 5.5）─────────────────────────────────


def rank2_action(state: GameState, content: Content) -> Rank2Action | None:
    """自己陣營的第 2 階行動（orders.json 的 rank2）；第一季規則沒開、散人、還沒到第 2 階、陣營沒有這種行動時是 None。"""
    p = state.player
    if not season_one(content, state.world) or p.faction is None or ranks.rank_of(state) < 2:
        return None
    return content.orders.rank2.get(p.faction)


def _today(state: GameState, content: Content) -> int:
    return calendar.point(state.world.time, content, state.world).cal_day


def rank2_left(state: GameState, content: Content) -> int:
    """今天還能做幾次（每曆日 rank2_daily 次，不論成敗）。"""
    return content.config.rank2_daily - state.player.rank2_days.get(_today(state, content), 0)


def count_rank2(state: GameState, content: Content) -> None:
    """記一次第 2 階行動（只留今天那一筆）。"""
    today = _today(state, content)
    state.player.rank2_days = {today: state.player.rank2_days.get(today, 0) + 1}


# ── 累積型 ─────────────────────────────────


def _commander_name(state: GameState, content: Content, front: str, side: str, generic: str) -> str:
    fid = figures.commander(state, content, front, side)
    return figures.name_of(content, fid) if fid is not None else generic


def after_success(state: GameState, content: Content, source: str, loc_id: str, rng: random.Random) -> list[str]:
    """第 2 階行動成功（source="rank2"）或守勢行動之後（"duty"）：累積型記一次（duty 的流民先擲 chance）；
    湊滿換算後的次數那一刻拿到東西、記下要送去哪條戰線（所在地點的戰線）。已經拿著東西的不再記。"""
    msgs: list[str] = []
    front = front_of(content, loc_id)
    place = content.locations[loc_id].name
    for o in open_ones(state, content):
        a = o.accumulate
        if o.kind != "accumulate" or a.source != source or o.id in state.player.opp_items:
            continue
        if a.chance < 1 and rng.random() >= a.chance:
            continue
        p = state.player
        p.opp_counts[o.id] = p.opp_counts.get(o.id, 0) + 1
        if a.tick:
            msgs.append(a.tick.replace("{地點}", place))
        n = foreshadow.need(content, a.count)
        if p.opp_counts[o.id] >= n:
            chief = _commander_name(state, content, front, "huang", "黃巾渠帥") if front else "黃巾渠帥"
            msgs.append(a.milestone.replace("{n}", str(n)).replace("{渠帥}", chief))
            p.opp_items[o.id] = a.item
            if front is not None:
                p.opp_fronts[o.id] = front
    return msgs


def _faction_def(content: Content, faction_id: str):
    return next(f for f in content.scenario.factions if f.id == faction_id)


def _deliver_here(state: GameState, content: Content, o: OppDef, loc_id: str) -> str | None:
    """東西拿在手上、此刻在交得了的地方時，回傳 {主將} 要填的名字；交不了是 None。
    front_commander：那條戰線己方此刻的主將所在；沒有主將時是那條戰線上的己方投靠點，名字寫「官軍的主將」。
    nearest_base：任一個己方投靠點（不用最近，到了就能交）。"""
    p = state.player
    if o.id not in p.opp_items:
        return None
    side = _faction_def(content, o.faction)
    deliver = o.accumulate.deliver if o.kind == "accumulate" else "front_commander"
    if deliver == "nearest_base":
        return side.name if loc_id in side.join_at else None
    front = p.opp_fronts.get(o.id)
    fid = figures.commander(state, content, front, o.faction) if front else None
    if fid is not None:
        return figures.name_of(content, fid) if figures.state_of(state, content, fid).location == loc_id else None
    on_front = [b for b in side.join_at if front_of(content, b) == front]
    return f"{side.name}的主將" if loc_id in on_front else None


def _deliver_label(o: OppDef) -> str:
    return o.accumulate.label if o.kind == "accumulate" else o.timing.deliver_label


def _deliver_done(o: OppDef) -> str:
    return o.accumulate.done if o.kind == "accumulate" else o.timing.done


def place_options(state: GameState, content: Content, loc_id: str) -> list:
    """閒著的選單上，這個地點做得了的機緣：交東西（opp:deliver:<id>）。Task 4 再加天時地利型的 opp:try:<id>。"""
    from .engine import Option  # noqa: PLC0415

    opts = []
    for o in open_ones(state, content):
        who = _deliver_here(state, content, o, loc_id)
        if who is not None:
            opts.append(Option(id=f"opp:deliver:{o.id}", label=_deliver_label(o).replace("{主將}", who)))
    return opts


def _trend_on_done(state: GameState, content: Content, o: OppDef, loc_id: str) -> list[str]:
    """交付完成時推一點：官軍、黃巾推那條戰線往己方（降卒、密信是記下的戰線；名冊是交在哪個據點，就是那裡的戰線），
    豪強推割據。推的是機緣的效果，不是個人推動：直接 change_trend，不走人數緩衝與上限（同軍令達成）。"""
    amount = o.accumulate.trend if o.kind == "accumulate" else 0
    if not amount:
        return []
    faction = _faction_def(content, o.faction)
    if faction.goals.get(GEJU):
        return change_trend(state, content, GEJU, amount)
    front = front_of(content, loc_id) if o.kind == "accumulate" and o.accumulate.deliver == "nearest_base" \
        else state.player.opp_fronts.get(o.id)
    goal = faction.goals.get(front or "", 0)
    return change_trend(state, content, front, goal * amount) if goal else []


def act(state: GameState, content: Content, world, arg: str, rng: random.Random) -> list[str]:
    """閒著的選單上按了機緣的選項（opp:<arg>）：deliver:<id> 交東西；Task 4 加 try:<id>。選項不在了回「此刻無法」。"""
    what, _, opp_id = arg.partition(":")
    o = next((x for x in open_ones(state, content) if x.id == opp_id), None)
    loc_id = state.player.location
    if o is None:
        return [NOT_NOW]
    if what == "deliver":
        who = _deliver_here(state, content, o, loc_id)
        if who is None:
            return [NOT_NOW]
        msgs = [_deliver_done(o).replace("{主將}", who)] + _trend_on_done(state, content, o, loc_id)
        return msgs + _complete(state, o)  # _trend_on_done 要在 _complete 之前：_complete 會把 opp_fronts 收掉
    return [NOT_NOW]


def title(state: GameState, content: Content, arg: str) -> str:
    """江湖紀錄的標題：「機緣・{名稱}」。"""
    opp_id = arg.partition(":")[2]
    o = next((x for x in content.opportunities if x.id == opp_id), None)
    return f"機緣・{o.name}" if o is not None else "機緣"
