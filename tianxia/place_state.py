"""地點會變樣（世界活起來第二批；Joy 2026-11-04 在選擇卡選「兩個都做」；設計稿 https://claude.ai/artifact/LFooPvhRw5NHosh3wDUKRV 第二節；
數字在 Config.plans）。

每個地點有一個樣子：太平、戰火、淪陷、饑荒、重建（WorldState.places 只記不是太平的；換季整個重來）。
- 誰改它：盤算結算（plans._settle：PlanContest.place_win／place_lose，預設打過一仗）、時刻表大事（TimetableOutcome.places）、
  領地易手（territory／conquest 的 _announce：落入 fall_to 那幾方之手算淪陷，被另一方拿回來算收復）。
- 照時間走（kind_at 現算，不另外記）：戰火、饑荒過了 until 接著重建 rebuild_days7，再之後是太平。淪陷沒有 until：一直淪陷，
  直到有人收復（Joy 10/29「可以」＝設計稿的建議）；收復之後重建。
- 戰火還沒熄（戰火、饑荒）又打一仗就鬧饑荒；淪陷的地方再打一仗、贏的還是佔著的那一方，照舊淪陷。
- 會改什麼（讀它的地方）：這裡抽得到的事件（Condition.place_state，rules.check_condition）、店家的價錢（territory.price_here 乘 factor）、
  馬市開不開（mounts.market_here 問 market_closed）、人物會不會晃過來（figure_life._move 避開 shunned）、到達與場景那一句（Game.location_text、
  main_view 的 place_state）。每一次變樣記一筆世界記事（kind place，邸報讀；此地舊事不列）。
開關：deeds.on（Config.plans.enabled）且 Config.plans.places。關著時一律太平、什麼都不記（一個字都不變）。
只 import models、state、calendar、world_state、deeds；rules、territory、conquest、plans、timetable、figure_life、mounts、engine 呼叫它。"""
from __future__ import annotations

from . import calendar, deeds
from .models import Content
from .state import PlaceMark, WorldState
from .world_state import season_length_days

PEACE, WAR, FALLEN, FAMINE, REBUILD = "peace", "war", "fallen", "famine", "rebuild"

# 畫面上的字（待 joy 潤；改字只改這裡，測試只比對關鍵字）
NAMES = {PEACE: "太平", WAR: "戰火", FALLEN: "淪陷", FAMINE: "饑荒", REBUILD: "重建"}
LINES = {  # 到達與場景那一句（太平不寫）
    WAR: "這一帶剛打過仗，焦土還沒冷，路上都是逃難的人。",
    FALLEN: "{side}的人馬佔了這裡，鋪子關了一半，百姓低著頭走路。",
    FAMINE: "糧價一天三漲，路邊有人在挖草根，孩子餓得哭不出聲。",
    REBUILD: "斷牆邊搭起了木架，工匠的號子聲此起彼落，市面慢慢回來了。",
}
CHANGED = {  # 變樣那一刻的世界記事（邸報讀）
    WAR: "{place}燃起戰火。",
    FALLEN: "{place}落入{side}之手。",
    FAMINE: "{place}鬧起了饑荒。",
    REBUILD: "{place}收復了，開始重建。",
}


def on(content: Content) -> bool:
    return deeds.on(content) and content.config.plans.places


def _days(world: WorldState, content: Content, days7: float) -> float:
    """7 天季的 days7 天是幾個世界秒（別的季長照比例）。"""
    return season_length_days(world, content) * calendar.DAY * days7 / 7.0


def mark_of(world: WorldState, content: Content, loc_id: str | None) -> PlaceMark | None:
    """此刻還算數的那一筆（照時間現算：過了重建期就是 None＝太平）；回的 kind 是此刻的樣子（過了 until 的戰火、饑荒換成重建）。"""
    if not on(content) or loc_id is None:
        return None
    mark = world.places.get(loc_id)
    if mark is None:
        return None
    if mark.until is None or world.time < mark.until:
        return mark
    if mark.kind != REBUILD and world.time < mark.until + _days(world, content, content.config.plans.rebuild_days7):
        return PlaceMark(kind=REBUILD, at=mark.until, until=mark.until + _days(world, content, content.config.plans.rebuild_days7))
    return None


def kind_at(world: WorldState, content: Content, loc_id: str | None) -> str:
    mark = mark_of(world, content, loc_id)
    return PEACE if mark is None else mark.kind


def _side_name(content: Content, side: str | None) -> str:
    return content.scenario.faction_name(side, side) if side else ""


def _place_name(content: Content, loc_id: str) -> str:
    return content.locations[loc_id].name if loc_id in content.locations else loc_id


def _set(world: WorldState, content: Content, loc_id: str, kind: str, *, side: str | None = None) -> None:
    """改成 kind（戰火、饑荒、重建照設定的天數到期；淪陷一直到收復），記一筆世界記事。地點不在內容裡的不收。"""
    if loc_id not in content.locations:
        return
    t = content.config.plans
    days = {WAR: t.war_days7, FAMINE: t.famine_days7, REBUILD: t.rebuild_days7}.get(kind)
    until = None if days is None else world.time + _days(world, content, days)
    world.places[loc_id] = PlaceMark(kind=kind, at=world.time, until=until, side=side)
    text = CHANGED[kind].format(place=_place_name(content, loc_id), side=_side_name(content, side))
    deeds.record_world(world, content, deeds.PLACE_KIND, text, place=loc_id, side=side)


def strike(world: WorldState, content: Content, loc_id: str, winner: str | None = None) -> None:
    """這裡打了一仗，贏的是 winner（不知道是 None）。淪陷的地方：贏的是佔著的那一方照舊淪陷，是別的一方就算收復（重建）；
    戰火還沒熄（戰火、饑荒）又打一仗鬧饑荒；其餘燃起戰火。"""
    if not on(content):
        return
    mark = mark_of(world, content, loc_id)
    kind = PEACE if mark is None else mark.kind
    if kind == FALLEN:
        if winner is not None and winner != mark.side:
            _set(world, content, loc_id, REBUILD)
        return
    _set(world, content, loc_id, FAMINE if kind in (WAR, FAMINE) else WAR)


def famine(world: WorldState, content: Content, loc_id: str) -> None:
    """這裡鬧饑荒（徵糧、劫糧）：淪陷的地方照舊淪陷（佔著的人搜刮，樣子不變）。"""
    if on(content) and kind_at(world, content, loc_id) != FALLEN:
        _set(world, content, loc_id, FAMINE)


def fall(world: WorldState, content: Content, loc_id: str, side: str) -> None:
    """落入 side 之手：已經是 side 佔著的不再記一次。"""
    if not on(content):
        return
    mark = mark_of(world, content, loc_id)
    if mark is not None and mark.kind == FALLEN and mark.side == side:
        return
    _set(world, content, loc_id, FALLEN, side=side)


def retake(world: WorldState, content: Content, loc_id: str) -> None:
    """收復：淪陷的地方開始重建；不是淪陷的地方當作打了一仗（燃起戰火，或戰火上又一仗鬧饑荒）。"""
    if not on(content):
        return
    if kind_at(world, content, loc_id) == FALLEN:
        _set(world, content, loc_id, REBUILD)
    else:
        strike(world, content, loc_id)


def apply(world: WorldState, content: Content, loc_id: str, how: str, winner: str | None = None) -> None:
    """照一個字改（TimetableOutcome.places 的值、PlanContest.place_win／place_lose）：war、famine、retake、fallen（落入 winner 之手）、
    fallen:<陣營>、none。"""
    kind, _, side = how.partition(":")
    if kind == WAR:
        strike(world, content, loc_id, winner)
    elif kind == FAMINE:
        famine(world, content, loc_id)
    elif kind == "retake":
        retake(world, content, loc_id)
    elif kind == FALLEN and (side or winner):
        fall(world, content, loc_id, side or winner)


def flipped(world: WorldState, content: Content, loc_id: str, side: str) -> None:
    """領地易手（territory／conquest 的 _announce）：落入 fall_to 那幾方之手算淪陷；淪陷的地方落入別的一方之手算收復；其餘是打了一仗。"""
    if not on(content):
        return
    if side in content.config.plans.fall_to:
        fall(world, content, loc_id, side)
    else:
        retake(world, content, loc_id)


# ── 讀它的地方 ─────────────────────────────────────


def factor(world: WorldState, content: Content, loc_id: str | None) -> float:
    """店家價錢的倍數（territory.price_here 乘上它）；太平、關著是 1。"""
    kind = kind_at(world, content, loc_id)
    return content.config.plans.price.get(kind, 1.0) if kind != PEACE else 1.0


def market_closed(world: WorldState, content: Content, loc_id: str | None) -> bool:
    return kind_at(world, content, loc_id) in content.config.plans.market_closed


def shunned(world: WorldState, content: Content, loc_id: str) -> bool:
    """人物在常去的地方之間晃的時候避開這裡（戰火、淪陷）。照行程走的人、時刻表搬的人不管它。"""
    return kind_at(world, content, loc_id) in (WAR, FALLEN)


def line(world: WorldState, content: Content, loc_id: str | None) -> str:
    """到達與場景那一句；太平、關著是空字串。"""
    mark = mark_of(world, content, loc_id)
    if mark is None:
        return ""
    return LINES[mark.kind].format(side=_side_name(content, mark.side))


def view(world: WorldState, content: Content, loc_id: str | None) -> dict | None:
    """場景卡上那個字（main_view 的 place_state）：{kind, name, line}；太平、關著是 None。"""
    mark = mark_of(world, content, loc_id)
    if mark is None:
        return None
    name = NAMES[mark.kind]
    if mark.kind == FALLEN and mark.side:
        name = f"{name}・{_side_name(content, mark.side)}"
    return {"kind": mark.kind, "name": name, "line": line(world, content, loc_id)}
