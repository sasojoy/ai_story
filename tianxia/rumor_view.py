"""傳聞分層的畫面（傳聞分層設計第二、八、十二節；計畫 2026-10-06 傳聞分層一）：見聞頁「傳聞」分成四層、
「你不在的時候」那一份摘要。只讀狀態與內容、只產生文字，不改任何東西；誰聽得到哪一則照 rules.audible，這裡不另寫一份規則。"""
from __future__ import annotations

from collections.abc import Callable

from . import calendar, foreshadow, opportunities, orders
from .models import Content
from .rules import Ears, audible, ears_of
from .state import GameState, Rumor
from .world_state import WorldStateStore

LAYER_LIMIT = 30  # 每一層列最近幾則（跟以前那一條清單一樣）

# 畫面上的字（待 joy 潤；改字只改這裡，測試只比對關鍵字）
WORLD_TITLE = "天下大事"
FACTION_TITLE = "陣營軍情"
PERSONAL_TITLE = "個人線索"
LOCAL_TITLE = "{regions}的傳聞（最近 {days:g} 天）"
NO_REGION = "此地"  # 地圖沒有大區時，所在大區那一段的標題
WORLD_EMPTY = "（還沒有天下大事。）"
FACTION_EMPTY = "（還沒有自己人的消息。）"
FACTION_LONER = "散人沒有陣營軍情；投靠一方之後，這裡是只有自己人才知道的消息。"
LOCAL_EMPTY = "（這一帶最近沒什麼傳聞。走到別的大區，聽到的就是那裡的事。）"
PERSONAL_EMPTY = "（還沒聽到只屬於你的線索。）"
AWAY_LINE = "〔{label}〕{when}　{text}"  # 「你不在的時候」的一行：哪一段、季曆時間、傳聞全文
AWAY_MORE = "另有 {n} 則沒列出來，到「見聞」的傳聞翻。"  # 摘要放不下時的最後一行（待 joy 潤；算在 Config.away_max 那幾行裡）
AWAY_TAG = "共 {n} 則"
LOCAL_REPEAT = "（×{n}）"  # 所在大區那一段同一句傳聞出現 N 次、合成一行時接在句尾（待 joy 潤；N > 1 才寫）
FACTION_KEYS = (orders.ISSUED, orders.DONE)  # 陣營軍情的「要點」：軍令發布與達成（議事、刺探有了再把它們的開頭加進來）


def _region_names(content: Content, ears: Ears) -> str:
    """此刻所在的大區名字（照地圖的順序；在路上兩頭不同區時兩個都寫）。"""
    names = [region.name for region in content.map.regions if region.id in ears.regions]
    return "、".join(names) or NO_REGION


def _listing(rumors: list[Rumor], when: Callable[[float], str], empty: str) -> str:
    """最新的在前、最多 LAYER_LIMIT 則，一則一段（跟以前那一條清單同一個寫法：時間、全形空白、文字）。"""
    rows = rumors[-LAYER_LIMIT:][::-1]
    return "\n\n".join(f"{when(r.time)}　{r.text}" for r in rows) or empty


def _collapsed(rumors: list[Rumor]) -> list[tuple[Rumor, int]]:
    """一模一樣的字合成一則：留在最新那一則的位置（同樣新就留排在前面的），附上一共幾則；其餘的順序不動。
    跟「你不在的時候」的規則 (b)（_newest_only）同一條，只是這裡只在一份清單裡合，而且要數一共幾則。"""
    newest: dict[str, int] = {}
    count: dict[str, int] = {}
    for i, r in enumerate(rumors):
        count[r.text] = count.get(r.text, 0) + 1
        at = newest.get(r.text)
        if at is None or r.time > rumors[at].time:
            newest[r.text] = i
    return [(r, count[r.text]) for i, r in enumerate(rumors) if newest[r.text] == i]


def _local_listing(rumors: list[Rumor], when: Callable[[float], str], empty: str) -> str:
    """所在大區那一段：跟 _listing 一樣最新的在前、最多 LAYER_LIMIT 行，只是同一句傳聞（地方傳聞常常一模一樣，QA 看過同一句六次）
    先合成一行、超過一則時句尾接 LOCAL_REPEAT（×N）；先合再截，重複的不會把別的傳聞擠出這一段。只動這一段的畫法：
    誰聽得到哪一則（rules.audible）、世界裡的傳聞、其他三層都不變。"""
    rows = _collapsed(rumors)[-LAYER_LIMIT:][::-1]
    return "\n\n".join(
        f"{when(r.time)}　{r.text}{LOCAL_REPEAT.format(n=n) if n > 1 else ''}" for r, n in rows
    ) or empty


def layers(
    state: GameState, content: Content, world: WorldStateStore | None, when: Callable[[float], str],
) -> list[dict[str, str]]:
    """見聞頁的四層（傳聞分層設計第二節）：天下大事、陣營軍情、所在大區、個人線索，各一段 {id, title, body}（body 是 Markdown）。
    陣營軍情只有自己陣營的、散人寫一句說明；所在大區只有此刻人在的大區、傳聞板上的（在路上是這段路兩頭）；個人線索是寫給
    自己的傳聞，加上聽過的伏筆片段（foreshadow.heard_texts），再加上聽過的機緣線索（opportunities.heard_clues：天時地利型的線索
    與內鬼的特徵，FB-086）——三樣都是「你聽到一件事」，都只有自己聽過的。所在大區那一段同一句傳聞合成一行、句尾接（×N）（_local_listing）；
    其他三層照舊一則一行。when 是時間的寫法（Game._day_stamp）。"""
    ears = ears_of(state, content)
    heard = [r for r in state.world.rumors if audible(r, ears)]

    def of(layer: str) -> list[Rumor]:
        return [r for r in heard if r.layer == layer]

    faction = _listing(of("faction"), when, FACTION_EMPTY) if state.player.faction else FACTION_LONER
    personal = (
        [f"{when(r.time)}　{r.text}" for r in of("personal")[::-1]]  # 寫給自己的傳聞，新的在前
        + foreshadow.heard_texts(state, content, world)  # 伏筆片段，照鏈與片段的順序
        + opportunities.heard_clues(state, content)  # 機緣的線索（天時地利與內鬼的特徵），照聽到的先後（FB-086）
    )
    title = LOCAL_TITLE.format(regions=_region_names(content, ears), days=content.config.rumor_board_days)
    return [
        {"id": "world", "title": WORLD_TITLE, "body": _listing(of("world"), when, WORLD_EMPTY)},
        {"id": "faction", "title": FACTION_TITLE, "body": faction},
        {"id": "local", "title": title, "body": _local_listing(of("local"), when, LOCAL_EMPTY)},
        {"id": "personal", "title": PERSONAL_TITLE, "body": "\n\n".join(personal) or PERSONAL_EMPTY},
    ]


def away_lines(
    state: GameState, content: Content, since: float | None, when: Callable[[float], str],
) -> tuple[list[str], int]:
    """「你不在的時候」那一份（傳聞分層設計第八節）：since（世界秒；None＝這一季從頭）之後、現在聽得到的
    1. 天下大事，全部——時刻表的大事除外（Game._deliver_big_events 已經補成「江湖大事」那一則，不寫兩次）；
    2. 陣營軍情的要點（FACTION_KEYS 開頭的）；
    3. 你所在大區的地方傳聞（傳聞板上的；地方摘要是傳聞分層第二份計畫的事，有了之後放摘要）。
    每一段照時間先後，三段照這個順序接起來。先去掉不用再看的（最終審查 I1：週末一週是現實 5 小時，離開一晚就是好幾週的軍令）：
    本週軍令只留最新那一週發的（過期的不列），【軍令達成】每一則都留；一模一樣的字只留最新的一則（三段之間也一樣）。
    再最多放 Config.away_max 行（含最後那一行）：放不下時前面的段先放滿，同一段裡留最近的。
    回傳（那幾行, 去掉之後一共幾則）；有沒列出來的，最後多一行（AWAY_MORE）叫人去見聞翻。什麼都沒有是（[], 0）。"""
    w = state.world
    ears = ears_of(state, content)
    announced = {r.text for r in w.timeline.values() if r.text}
    fresh = [r for r in w.rumors if (since is None or r.time > since) and audible(r, ears)]
    names = {region.id: region.name for region in content.map.regions}

    def week(r: Rumor) -> int:
        return calendar.point(r.time, content, w).week

    key_points = [r for r in fresh if r.layer == "faction" and r.text.startswith(FACTION_KEYS)]
    latest = max((week(r) for r in key_points if r.text.startswith(orders.ISSUED)), default=None)
    sections = _newest_only([
        [(WORLD_TITLE, r) for r in fresh if r.layer == "world" and r.text not in announced],
        [(FACTION_TITLE, r) for r in key_points if not r.text.startswith(orders.ISSUED) or week(r) == latest],
        [(names.get(r.region or "", NO_REGION), r) for r in fresh if r.layer == "local"],
    ])
    total = sum(len(section) for section in sections)
    room = content.config.away_max - (1 if total > content.config.away_max else 0)  # 放不下時最後一行留給「另有 N 則」
    rows: list[tuple[str, Rumor]] = []
    for section in sections:
        kept = section[len(section) - min(room, len(section)):] if room > 0 else []
        rows += kept
        room -= len(kept)
    lines = [AWAY_LINE.format(label=label, when=when(r.time), text=r.text) for label, r in rows]
    if total > len(rows):
        lines.append(AWAY_MORE.format(n=total - len(rows)))
    return lines, total


def _newest_only(sections: list[list[tuple[str, Rumor]]]) -> list[list[tuple[str, Rumor]]]:
    """一模一樣的字只留最新的一則，留在它那一段原來的位置；三段之間也一樣（同樣新就留排在前面的段、前面的位置）。"""
    best: dict[str, tuple[int, int]] = {}
    for s, section in enumerate(sections):
        for i, (_, r) in enumerate(section):
            at = best.get(r.text)
            if at is None or r.time > sections[at[0]][at[1]][1].time:
                best[r.text] = (s, i)
    return [[row for i, row in enumerate(section) if best[row[1].text] == (s, i)] for s, section in enumerate(sections)]
