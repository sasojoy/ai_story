"""玉璽碎片在換季、開季那一刻的世界層的格（全部拆包第 27 批從核心 sqlite_world 搬來，原樣；世界層 WORLD_ORDER 的 open、next、retire）：
開季藏一片、天命之季的章、舊季收尾（隱沒、沒收場的奪璽單挑記成未分勝負、天命之季過後七片散去）。都直接改傳進來的 SharedWorldState
（開季在 mutate 裡、換季是 next_season 手動 _load／_save，不能巢狀 mutate）。掛鉤不看 enabled，格裡照原位自己問 content.seal、Config.seal.enabled。
"""
from __future__ import annotations

from collections.abc import Callable

from tianxia import timetable  # 共用規則層
from tianxia.models import Content
from tianxia.state import Rumor
from tianxia.world_state import SharedWorldState

from . import seal


def stamp_cache(state: SharedWorldState, content: Content) -> None:
    """開季那一刻（自動開的第一季、管理者開季、換季）：碎片藏在中立地（seal.stamp_cache：上一季沒撿到的清掉、領地爭奪的季照
    hide_chance 擲、天命之季不藏）。直接改 state（同一筆交易、不巢狀 mutate）；內容沒有七片就什麼都不做。
    （原本 SqliteWorldStore._stamp_cache；世界層 open 的 seal.cache、next 的 seal.cache 兩格叫。）"""
    if not content.seal:
        return
    seal.stamp_cache(state, content)


def stamp_mandate(state: SharedWorldState, content: Content) -> None:
    """next_season 換好新的一季之後：該蓋天命之季（seal.mandate_due）就蓋（seal.stamp_mandate，天命之爭的時刻照這一季的章算）；
    這一季打不了天命之爭（沒蓋第一季規則的章、劇本沒標或沒有那一場決戰）就記 mandate_pending，延到下一個能打的季（8.1、8.5）。
    直接改 state（同一筆交易、不巢狀 mutate）。（原本 SqliteWorldStore._stamp_mandate；世界層 next 的 seal.mandate 那一格在
    content.seal 與 Config.seal.enabled 都開著時才叫：主機關掉碎片時不蓋。）"""
    reg = seal.filled(state.seal, content)
    if not seal.mandate_due(reg, content):
        return
    event = seal.mandate_event(content)
    if event is None or seal.mandate_battle(content) is None or not state.season.season_one:
        reg.mandate_pending = True
        return
    seal.stamp_mandate(state, content, timetable.default_time(event, content, state.season))


def retire(state: SharedWorldState, content: Content, now: float, seen_real: Callable[[str], float | None]) -> bool:
    """世界層 retire 的 seal 那一格（原本核心 sqlite_world._retire_seal，原樣搬來；next_season 換新季之前那一段）：玉璽碎片（7.6、5.11、8.4）
    ——直接改 state.seal（next_season 是手動 _load／_save，不能巢狀 mutate）。seen_real(持有者) 是那個人最後一次自己上線的現實秒
    （sqlite_world._seen_real，同一條連線）。回這一段有沒有寫上一季的江湖史（next_season 照它決定要不要先存上一季那一列）。"""
    wrote = False
    if content.seal:
        reg = seal.filled(state.seal, content)
        mandate = state.season.mandate  # 剛結束的是天命之季：這一次不判隱沒、最後七片散去（8.4）
        if content.config.seal.enabled and not mandate:  # 主機關掉碎片時不判隱沒（登記照留）
            seen = {s.holder: seen_real(s.holder) for s in reg.shards.values() if s.state == "held" and s.holder}
            for shard, name in seal.sink(reg, state.season_number, seen, now, content.config.seal):
                text = seal.sink_text(content, name, content.seal[shard.id].name)  # 改版：不點名
                state.season.chronicle.append(Rumor(time=state.season.time, text=text))
                wrote = True
        for duel in state.seal_duels:  # 還沒收場的單挑記成未分勝負，兩人補得到（開關關著時留下來的也一樣，不帶進下一季）
            seal.log(reg, state.season_number, "unsettled", shard=duel.shard, holder=duel.holder.name, other=duel.challenger.name,
                     record=duel.record, where=duel.where, lines=list(duel.lines))
        if mandate:  # 散去不看 seal.enabled：季的章已經蓋了，下一輪照樣要從頭來
            seal.scatter(reg, state.season_number)
            state.season.chronicle.append(Rumor(time=state.season.time, text=seal.SCATTER))
            wrote = True
    return wrote
