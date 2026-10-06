"""傳聞分層的畫面（傳聞分層設計第二、十二節；計畫 2026-10-06 傳聞分層一）：見聞頁「傳聞」分成四層。
只讀狀態與內容、只產生文字，不改任何東西；誰聽得到哪一則照 rules.audible，這裡不另寫一份規則。"""
from __future__ import annotations

from collections.abc import Callable

from . import foreshadow
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


def _region_names(content: Content, ears: Ears) -> str:
    """此刻所在的大區名字（照地圖的順序；在路上兩頭不同區時兩個都寫）。"""
    names = [region.name for region in content.map.regions if region.id in ears.regions]
    return "、".join(names) or NO_REGION


def _listing(rumors: list[Rumor], when: Callable[[float], str], empty: str) -> str:
    """最新的在前、最多 LAYER_LIMIT 則，一則一段（跟以前那一條清單同一個寫法：時間、全形空白、文字）。"""
    rows = rumors[-LAYER_LIMIT:][::-1]
    return "\n\n".join(f"{when(r.time)}　{r.text}" for r in rows) or empty


def layers(
    state: GameState, content: Content, world: WorldStateStore | None, when: Callable[[float], str],
) -> list[dict[str, str]]:
    """見聞頁的四層（傳聞分層設計第二節）：天下大事、陣營軍情、所在大區、個人線索，各一段 {id, title, body}（body 是 Markdown）。
    陣營軍情只有自己陣營的、散人寫一句說明；所在大區只有此刻人在的大區、傳聞板上的（在路上是這段路兩頭）；個人線索是寫給
    自己的傳聞加上聽過的伏筆片段（foreshadow.heard_texts）。when 是時間的寫法（Game._day_stamp）。"""
    ears = ears_of(state, content)
    heard = [r for r in state.world.rumors if audible(r, ears)]

    def of(layer: str) -> list[Rumor]:
        return [r for r in heard if r.layer == layer]

    faction = _listing(of("faction"), when, FACTION_EMPTY) if state.player.faction else FACTION_LONER
    personal = [f"{when(r.time)}　{r.text}" for r in of("personal")[::-1]] + foreshadow.heard_texts(state, content, world)
    title = LOCAL_TITLE.format(regions=_region_names(content, ears), days=content.config.rumor_board_days)
    return [
        {"id": "world", "title": WORLD_TITLE, "body": _listing(of("world"), when, WORLD_EMPTY)},
        {"id": "faction", "title": FACTION_TITLE, "body": faction},
        {"id": "local", "title": title, "body": _listing(of("local"), when, LOCAL_EMPTY)},
        {"id": "personal", "title": PERSONAL_TITLE, "body": "\n\n".join(personal) or PERSONAL_EMPTY},
    ]
