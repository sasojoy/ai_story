"""大勢人物（計畫 T4）。T2 先放最小版：時刻表的結果只改 WorldState.figures 的聲威、狀態、戰線與所在；
接手、聲威歸零自動退場、每曆日推動、從 content 種出開季的人物，都留給 T4。

state 是 GameState（季的事用的是 world._season_vehicle 那個空殼玩家），只讀寫 state.world。"""
from __future__ import annotations

from .models import Content, FigureChange
from .state import FigureState, GameState

OUT = ("retired", "crippled")  # 退場（非天命）、重創（天命）：本季不再出現；下獄不算（時刻表結算 5.2）
FATE_STATUS = {"退場": "retired", "重創": "crippled", "下獄": "jailed", "到任": "active"}
ZEROED = ("退場", "重創")  # 時刻表結算文件第一節：這兩種是聲威歸零


def apply(state: GameState, content: Content, fid: str, change: FigureChange) -> list[str]:
    """照時刻表結算文件第一節改一位人物：重挫、聲威大減、受挫照 Config.fate_prestige 扣聲威；退場、重創歸零；
    下獄只改狀態、聲威不變；重挫退出所在戰線（front 換成 change.front，可能是 None）、轉往 change.location；
    到任回到在場、接下 change.front 與 change.location。聲威夾在 0～100。only_if 由呼叫端（timetable）判斷。

    還沒種過的人物先用預設值建一筆（T4 之前的內容沒有人物表）。回傳要接在公告後面的話：最小版沒有。"""
    figure = state.world.figures.setdefault(fid, FigureState())
    if change.fate in ZEROED:
        figure.prestige = 0
    else:
        figure.prestige += content.config.fate_prestige.get(change.fate or "", 0)
    figure.prestige = max(0, min(100, figure.prestige + change.prestige))
    if change.fate in FATE_STATUS:
        figure.status = FATE_STATUS[change.fate]
    if change.fate in ("重挫", "到任"):  # 重挫：退出原戰線、轉往別處；到任：接下新戰線
        figure.front = change.front
        if change.location is not None:
            figure.location = change.location
    return []


def holds(state: GameState, change: FigureChange) -> bool:
    """change.only_if 的每位人物都還在場、而且在指定的戰線上（例：皇甫嵩還在潁川，朱儁才南下）。"""
    for fid, front in change.only_if.items():
        figure = state.world.figures.get(fid)
        if figure is None or figure.status != "active" or figure.front != front:
            return False
    return True


def is_out(state: GameState, fid: str) -> bool:
    """退場或重創。還沒種過的人物（T4 開季時才種）不算，當成在場。"""
    figure = state.world.figures.get(fid)
    return figure is not None and figure.status in OUT


def on_front(state: GameState, fid: str, front: str) -> bool:
    """這位人物此刻在不在 front 這條戰線（伏筆的「主角色不在時改由接手的人出面」用它）。T4 之前的最小版：
    還沒種過的人物當成在他的預設戰線（看不出來就當在場）；種過的要在場（active），而且所在戰線是 front——
    戰線是空的（時刻表套效果時才建的那一筆）一樣看不出來，當成在。T4 種人物之後照同一個規則讀。"""
    figure = state.world.figures.get(fid)
    if figure is None:
        return True
    return figure.status == "active" and figure.front in (None, front)


def commander(state: GameState, content: Content, front: str | None, faction: str) -> str | None:
    """那條戰線上那一方當下的主將（人物 id）。最小版一律沒有：時刻表的 {官軍主將} 填「官軍」，
    @commander 的人物效果略過。T4 照 WorldState.figures 補完。"""
    return None
