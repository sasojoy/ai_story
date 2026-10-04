"""大勢人物（計畫 T4；T2 先放了只改欄位的最小版）。

人物表（content/figures.json，濃縮版內容表 1.1）上每一位這一季的聲威、狀態、戰線、所在，存在 WorldState.figures；
開關開著時，開季那一刻照人物表種好（world_state.stamp_season 呼叫 seed）。
- 讀：state_of（沒種過的照人物表的起始值，不寫回存檔）、present_at／placed_characters（誰在哪裡）、commander
  （那條戰線那一方的主將）、difficulty／squad_of（挑戰本人的難度）。
- 改：apply（時刻表的人物結局）。

state 是 GameState（季的事用的是 world._season_vehicle 那個空殼玩家），只讀寫 state.world；不碰儲存。
人物表沒有的 id（測試夾具）照 T2 最小版的規則：FigureState 的預設值、只改欄位。"""
from __future__ import annotations

from .models import Content, FigureChange, FigureDef, Squad
from .rules import season_one
from .state import FigureState, GameState, WorldState

OUT = ("retired", "crippled")  # 退場（非天命）、重創（天命）：本季不再出現；下獄不算（時刻表結算 5.2）
FATE_STATUS = {"退場": "retired", "重創": "crippled", "下獄": "jailed", "到任": "active"}
ZEROED = ("退場", "重創")  # 時刻表結算文件第一節：這兩種是聲威歸零


# ── 種與讀 ───────────────────────────────────────────────


def initial(fig: FigureDef) -> FigureState:
    """人物表上這一位開季時的樣子。"""
    return FigureState(prestige=fig.start_prestige, status=fig.start_status, front=fig.front, location=fig.location)


def seed(world: WorldState, content: Content) -> None:
    """開季時把人物表的每一位照起始值種進 WorldState.figures（world_state.stamp_season 在開關開著時呼叫）。
    時刻表的 only_if（holds）與伏筆的出面人物（on_front）讀的都是種好的這一份。"""
    world.figures = {fid: initial(fig) for fid, fig in content.figures.items()}


def state_of(state: GameState, content: Content, fid: str) -> FigureState:
    """這位人物此刻的樣子：種過的照存檔；沒種過的（T4 之前開的季、季中才加進人物表的人）照人物表的起始值，
    不寫回存檔（讀畫面不該改存檔）。人物表也沒有的（測試夾具）照 FigureState 的預設值。"""
    stored = state.world.figures.get(fid)
    if stored is not None:
        return stored
    fig = content.figures.get(fid)
    return initial(fig) if fig is not None else FigureState()


def _ensure(state: GameState, content: Content, fid: str) -> FigureState:
    """要改之前先確定存檔裡有這一筆（沒種過的照 state_of 建一筆）。"""
    if fid not in state.world.figures:
        state.world.figures[fid] = state_of(state, content, fid)
    return state.world.figures[fid]


def name_of(content: Content, fid: str) -> str:
    """畫面上的名字：人物表的 name（彭脫、韓忠沒有對話人物也有名字）；人物表沒有的照 characters.json，都沒有就是 id。"""
    fig = content.figures.get(fid)
    if fig is not None:
        return fig.name
    character = content.characters.get(fid)
    return character.name if character is not None else fid


def of_character(content: Content, character_id: str) -> str | None:
    """這個對話人物是哪一位大勢人物（人物表的 id）；不是大勢人物（曹操、劉備……）就是 None。"""
    return next((fid for fid, fig in content.figures.items() if fig.character == character_id), None)


def present_at(state: GameState, content: Content, loc_id: str) -> list[str]:
    """此刻在這個地點、在場（active）的人物（人物表的順序）。下獄、退場、重創、還沒出場的都不算。"""
    return [
        fid for fid in content.figures
        if (now := state_of(state, content, fid)).status == "active" and now.location == loc_id
    ]


def placed_characters(state: GameState, content: Content) -> dict[str, str | None]:
    """第一季的規則開著時，人物表上有對話人物的那幾位此刻在哪裡：在場的是所在地點，下獄、退場、重創、還沒出場的是
    None（求見、交友都沒有他）。規則沒開（beta）時是空的：大家照 characters.json 的 talk_at，一個字都不變。"""
    if not season_one(content, state.world):
        return {}
    out: dict[str, str | None] = {}
    for fid, fig in content.figures.items():
        if fig.character is not None:
            now = state_of(state, content, fid)
            out[fig.character] = now.location if now.status == "active" else None
    return out


def commander(state: GameState, content: Content, front: str | None, faction: str) -> str | None:
    """那條戰線上那一方當下的主將（人物 id）：在場、戰線是 front、陣營是 faction 的人物裡，人物表排最前面的那位——
    人物表的順序就是位階（皇甫嵩在朱儁前、朱儁在孫堅前、張角在張寶前、盧植在董卓前）。沒有就是 None：時刻表的
    {官軍主將} 填「官軍」、@commander 的效果略過，軍令（T6）的 {主將} 換成泛稱。人物表沒有的人物不算（不知道是哪一方）。"""
    if front is None:
        return None
    for fid, fig in content.figures.items():
        now = state_of(state, content, fid)
        if fig.faction == faction and now.status == "active" and now.front == front:
            return fid
    return None


def difficulty(state: GameState, content: Content, fid: str) -> int:
    """挑戰本人的難度：代表本人的隊伍的難度是聲威 100 時的值，聲威 0 時是 figure_difficulty_floor 成，中間線性；
    四捨五入成整數（總計畫第五節；先 round 到小數六位，免得 127.4999… 這種浮點雜訊）。"""
    fig = content.figures[fid]
    floor = content.config.figure_difficulty_floor
    prestige = state_of(state, content, fid).prestige
    value = content.squads[fig.squad].difficulty * (floor + (1 - floor) * prestige / 100)
    return int(round(value, 6) + 0.5)


def squad_of(state: GameState, content: Content, fid: str) -> Squad:
    """挑戰本人時的對手：代表本人的隊伍，難度換成照聲威算的那一個（勝算、戰報、掉落都看它）。"""
    return content.squads[content.figures[fid].squad].model_copy(update={"difficulty": difficulty(state, content, fid)})


# ── 時刻表的人物結局 ─────────────────────────────────────


def apply(state: GameState, content: Content, fid: str, change: FigureChange) -> list[str]:
    """照時刻表結算文件第一節改一位人物：重挫、聲威大減、受挫照 Config.fate_prestige 扣聲威；退場、重創歸零；
    下獄只改狀態、聲威不變；重挫退出所在戰線（front 換成 change.front，可能是 None）、轉往 change.location；
    到任回到在場、接下 change.front 與 change.location。聲威夾在 0～100。only_if 由呼叫端（timetable）判斷。
    還沒種過的人物先照人物表建一筆。回傳要接在公告後面的話：沒有。"""
    figure = _ensure(state, content, fid)
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


def holds(state: GameState, content: Content, change: FigureChange) -> bool:
    """change.only_if 的每位人物都在場、而且在指定的戰線上（例：皇甫嵩還在潁川，朱儁才南下）。
    沒種過的人物照人物表的起始值（state_of）；人物表也沒有、存檔也沒有的照 T2 的規則當成不在。"""
    for fid, front in change.only_if.items():
        if fid not in state.world.figures and fid not in content.figures:
            return False
        figure = state_of(state, content, fid)
        if figure.status != "active" or figure.front != front:
            return False
    return True


def is_out(state: GameState, fid: str) -> bool:
    """退場或重創。還沒種過的人物不算（人物表上沒有人開季就退場），當成在場。"""
    figure = state.world.figures.get(fid)
    return figure is not None and figure.status in OUT


def on_front(state: GameState, fid: str, front: str) -> bool:
    """這位人物此刻在不在 front 這條戰線（伏筆的「主角色不在時改由接手的人出面」用它）：還沒種過的人物當成在他的
    預設戰線（看不出來就當在場）；種過的要在場（active），而且所在戰線是 front——戰線是空的（時刻表套效果時才建的
    那一筆）一樣看不出來，當成在。開季時已經種好，所以第一季的季裡讀的都是種好的那一份。"""
    figure = state.world.figures.get(fid)
    if figure is None:
        return True
    return figure.status == "active" and figure.front in (None, front)
