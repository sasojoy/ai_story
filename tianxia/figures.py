"""大勢人物（計畫 T4；T2 先放了只改欄位的最小版）。

人物表（content/figures.json，濃縮版內容表 1.1）上每一位這一季的聲威、狀態、戰線、所在，存在 WorldState.figures；
開關開著時，開季那一刻照人物表種好（world_state.stamp_season 呼叫 seed）。
- 讀：state_of（沒種過的照人物表的起始值，不寫回存檔）、present_at／placed_characters（誰在哪裡）、commander
  （那條戰線那一方的主將）、difficulty／squad_of（挑戰本人的難度）。
- 改：apply（時刻表的人物結局與接手）、defeat（挑戰本人打贏扣聲威）。

state 是 GameState（季的事用的是 world._season_vehicle 那個空殼玩家），只讀寫 state.world；不碰儲存。
人物表沒有的 id（測試夾具）照 T2 最小版的規則：FigureState 的預設值、只改欄位。"""
from __future__ import annotations

from . import calendar
from .models import Content, FigureChange, FigureDef, Squad
from .rules import add_rumor, change_trend, season_one, trend_value
from .state import FigureState, GameState, WorldState

OUT = ("retired", "crippled")  # 退場（非天命）、重創（天命）：本季不再出現；下獄不算（時刻表結算 5.2）
FATE_STATUS = {"退場": "retired", "重創": "crippled", "下獄": "jailed", "到任": "active"}
ZEROED = ("退場", "重創")  # 時刻表結算文件第一節：這兩種是聲威歸零
HANDOFF_FATES = ("退場", "重創", "重挫")  # 這三種會空出戰線，由接位的人接（下獄的戰線由同一件大事裡「到任」的人接）


# ── 種與讀 ───────────────────────────────────────────────


def initial(fig: FigureDef) -> FigureState:
    """人物表上這一位開季時的樣子。"""
    return FigureState(prestige=fig.start_prestige, status=fig.start_status, front=fig.front, location=fig.location)


def seed(world: WorldState, content: Content) -> None:
    """開季時把人物表的每一位照起始值種進 WorldState.figures（world_state.stamp_season 在開關開著時呼叫）。
    時刻表的 only_if（holds）與伏筆的出面人物（on_front）讀的都是種好的這一份。"""
    world.figures = {fid: initial(fig) for fid, fig in content.figures.items()}


def _completed(stored: FigureState, fig: FigureDef | None) -> FigureState:
    """T4 之前蓋「開」的章的季，被時刻表碰過的人存的是 T2 最小版的預設值：沒有所在（location 是空的）、戰線也沒填。
    人物表上有這位、存檔的所在是空的，就當成這種最小版：所在照人物表補上；在場（active）又沒有戰線的，戰線也照人物表補上
    （人物表上的戰線本身可以是空的，例如趙弘、董卓）。聲威、狀態照存檔。已經有所在的（連重挫退出戰線的）照存檔，
    人物表沒有的（夾具）也照存檔。回傳補好的一份新物件；不用補就是存檔本身。"""
    if fig is None or stored.location:
        return stored
    update: dict[str, object] = {"location": fig.location}
    if stored.status == "active" and stored.front is None:
        update["front"] = fig.front
    return stored.model_copy(update=update)


def state_of(state: GameState, content: Content, fid: str) -> FigureState:
    """這位人物此刻的樣子：種過的照存檔（T2 最小版留下的空所在、空戰線照人物表補上，見 _completed）；沒種過的（T4 之前
    開的季、季中才加進人物表的人）照人物表的起始值，都不寫回存檔（讀畫面不該改存檔）。人物表也沒有的（測試夾具）
    照 FigureState 的預設值。"""
    fig = content.figures.get(fid)
    stored = state.world.figures.get(fid)
    if stored is not None:
        return _completed(stored, fig)
    return initial(fig) if fig is not None else FigureState()


def _ensure(state: GameState, content: Content, fid: str) -> FigureState:
    """要改之前先確定存檔裡有這一筆，而且是補好的（沒種過的照 state_of 建一筆；T2 最小版的存檔補好再寫回去）。
    存檔本來就好的，state_of 回傳的就是存檔本身，原地改得到。"""
    now = state_of(state, content, fid)
    state.world.figures[fid] = now
    return now


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


# ── 每曆時的推動 ─────────────────────────────────────────


def push_goal(state: GameState, content: Content, fid: str) -> int:
    """這位人物此刻往哪個方向推所在的戰線：在場、有戰線、每次推得動（push、actions_per_day 都大於 0），自己陣營對這條
    戰線也有目標時，是那個目標（黃巾 +1、官軍 −1）；否則 0——何進、開季時的趙弘與董卓、還沒出場的、下獄或退場的都不推。
    不看週次（active_from_week 由 tick 判斷）。"""
    fig = content.figures[fid]
    now = state_of(state, content, fid)
    if now.status != "active" or now.front is None or fig.push <= 0 or fig.actions_per_day <= 0:
        return 0
    faction = content.scenario.faction(fig.faction)
    return faction.goals.get(now.front, 0) if faction is not None else 0


def tick(state: GameState, content: Content, cal_hours: float) -> None:
    """大勢人物的日常推動（第一季設計 8.2 第 1、2 條，總計畫 T4）：決定性的累積，不擲骰。每位推得動的人物把
    actions_per_day × cal_hours ÷ 24 累積進 trend_accum["fig:<id>"]，每滿 1 就往自己陣營的方向推所在戰線 push 點；
    戰線偏向對方 figure_reaction_lean 以上時累積乘 figure_reaction_mult（反應規則：輸得多的一方推得勤，兩邊都有人物
    在這條戰線上時，輸的那邊推得比對方勤兩倍（每天出手的次數一樣的話），戰線就不容易被推到底、停在中段一帶；某一方的
    人物都退場了，戰線就往另一方漂，沒有任何東西把它拉回 50）。active_from_week 之前不推（官軍三將與孫堅第 2 週才出兵）；週次看這一段時間的中點，所以週一
    00:00 那一刻結束的那個曆時算上一週。
    直接走 change_trend、不經過 T3 的人數緩衝（大勢人物不受玩家人數影響，第一季設計第七節），也不回傳訊息——背景推動
    跟以前的虛擬玩家一樣安靜，不洗版。由 world.season_hour 每曆時呼叫一次（cal_hours＝1）；規則沒開時什麼都不做。"""
    w = state.world
    if not season_one(content, w):
        return
    cfg = content.config
    middle = max(0.0, w.time - cal_hours * calendar.cal_hour_seconds(content, w) / 2)
    week = calendar.point(middle, content, w).week
    for fid, fig in content.figures.items():
        goal = push_goal(state, content, fid)
        if not goal or week < fig.active_from_week:
            continue
        front = state_of(state, content, fid).front
        losing = (50 - trend_value(state, content, front)) * goal >= cfg.figure_reaction_lean
        rate = fig.actions_per_day * (cfg.figure_reaction_mult if losing else 1.0)
        key = f"fig:{fid}"
        pending = w.trend_accum.get(key, 0.0) + rate * cal_hours / 24
        whole = int(pending + 1e-9)  # 容一點浮點誤差：24 個 1/24 才剛好湊成 1（同 rules.geju_tick；累積不先四捨五入，誤差才不會越滾越大）
        rest = max(0.0, pending - whole)
        if rest:
            w.trend_accum[key] = rest
        else:
            w.trend_accum.pop(key, None)
        if whole:
            change_trend(state, content, front, whole * fig.push * goal, reveal=False)


# ── 時刻表的人物結局 ─────────────────────────────────────


def apply(state: GameState, content: Content, fid: str, change: FigureChange) -> list[str]:
    """照時刻表結算文件第一節改一位人物（T2 定的用詞，T4 補上接手）：
    - 退場（非天命）、重創（天命）：聲威歸零、本季不再出現，由接位的人接下他的戰線；
    - 重挫：聲威 −30，退出所在戰線（front 換成 change.front，沒給就是 None）、轉往 change.location，由接位的人接下原本的戰線；
    - 聲威大減、受挫：聲威 −30、−15，留在原地；
    - 下獄：本季不出現、不能對話、不算退場、聲威不變；戰線由同一件大事裡「到任」的人接（不走接位鏈）；
    - 到任：回到在場，接下 change.front 與 change.location。
    任何時候聲威扣到 0：天命人物重創、其他人退場（照上面處理）。已經退場或重創的人不再變（例：張角病逝之後廣宗的「張角退場」）。
    聲威夾在 0～100；only_if 由呼叫端（timetable）判斷。還沒種過的人物先照人物表建一筆；人物表沒有的（測試夾具）只改欄位。
    接手另發一則天下大事傳聞（見聞頁看得到），不接在公告後面——時刻表的公告已經寫了結果（例：「皇甫嵩重挫退走，潁川交給了
    朱儁」），再接就重複了。所以回傳（要接在公告後面的話）一律是空的。"""
    for line in _change(state, content, fid, change):
        add_rumor(state, line, content=content, layer="world")
    return []


def _change(state: GameState, content: Content, fid: str, change: FigureChange) -> list[str]:
    """apply 的本體：改這位人物、空出戰線時照接位鏈交接；回傳接手的那一句（apply 拿去發傳聞、defeat 接在退場那句後面）。"""
    figure = _ensure(state, content, fid)
    if figure.status in OUT:
        return []
    fig = content.figures.get(fid)
    held = figure.front if figure.status == "active" else None  # 原本守的戰線與所在（交接時接位的人接下這兩樣）
    post = figure.location
    fate = change.fate
    if fate in ZEROED:
        figure.prestige = 0
    else:
        figure.prestige += content.config.fate_prestige.get(fate or "", 0)
    figure.prestige = max(0, min(100, figure.prestige + change.prestige))
    if figure.prestige == 0 and fate not in ("下獄", "到任"):  # 扣到 0：照退場或重創處理
        fate = "重創" if fig is not None and fig.destiny else "退場"
    if fate in FATE_STATUS:
        figure.status = FATE_STATUS[fate]
    if fate in ("重挫", "到任"):  # 重挫：退出原戰線、轉往別處；到任：接下新戰線
        figure.front = change.front
        if change.location is not None:
            figure.location = change.location
    if fig is None or fate not in HANDOFF_FATES or held is None or (figure.status == "active" and figure.front == held):
        return []
    return _hand_over(state, content, fid, held, post)


def _hand_over(state: GameState, content: Content, fid: str, front: str, location: str) -> list[str]:
    """fid 空出 front（人物誌第七節、第一季設計 8.1）：照接位鏈找第一個接得了的人——還沒出場的，或在場、手上沒有別條戰線的——
    換成在場、接下這條戰線與 fid 原本的所在。鏈上已經有人在這條戰線上（朱儁本來就在潁川）就不必交接、也不發公告；退場、
    重創、下獄或守著別條戰線的人跳過，往下一位找；鏈走到底沒人接，這條戰線就沒有這一方的人物了（commander 回 None，
    呼叫端換成泛稱）。回傳接手的那一句，例如「彭脫接手潁川汝南的戰事。」。"""
    seen = {fid}
    nxt = content.figures[fid].successor
    while nxt is not None and nxt not in seen and nxt in content.figures:
        seen.add(nxt)
        heir = state_of(state, content, nxt)
        if heir.status == "active" and heir.front == front:
            return []
        if heir.status == "away" or (heir.status == "active" and heir.front is None):
            heir = _ensure(state, content, nxt)
            heir.status, heir.front, heir.location = "active", front, location
            return [f"{name_of(content, nxt)}接手{_front_name(content, front)}的戰事。"]
        nxt = content.figures[nxt].successor
    return []


def _front_name(content: Content, front: str) -> str:
    return next((t.name for t in content.scenario.trends if t.id == front), front)


def defeat(state: GameState, content: Content, fid: str, amount: float) -> list[str]:
    """挑戰本人打贏（計畫 T4、軍令文件 4.5）：他敗走，聲威扣 amount（人數緩衝之後的量，可能有小數；不足一點的記在
    trend_accum["prestige:<id>"]，滿一點才扣）。扣到 0 時照退場（天命人物重創）處理、由接位的人接下戰線，退場與接手
    合成一則天下大事。回傳給打贏的人看的句子：「波才聲威 -5」，歸零時再接退場與接手那幾句。已經退場的人不再扣。"""
    figure = _ensure(state, content, fid)
    if figure.status in OUT or amount <= 0:
        return []
    w = state.world
    key = f"prestige:{fid}"
    pending = w.trend_accum.get(key, 0.0) + amount
    whole = int(pending + 1e-9)  # 容一點浮點誤差（同 tick）
    rest = max(0.0, pending - whole)
    if rest:
        w.trend_accum[key] = rest
    else:
        w.trend_accum.pop(key, None)
    if not whole:
        return []
    name = name_of(content, fid)
    before = figure.prestige
    figure.prestige = max(0, before - whole)
    lines = [f"{name}聲威 -{before - figure.prestige}"] if figure.prestige < before else []
    if figure.prestige == 0:
        destiny = fid in content.figures and content.figures[fid].destiny
        # 濃縮版內容表 1.5（S1 審過）：不說「這一季」；退場句後面緊接接手句，所以這裡不再寫「的戰事」
        news = [f"{name}連吃敗仗，元氣大傷，今年是露不了面了。" if destiny else f"{name}連吃敗仗，聲威掃地，再也號令不動手下的兵。"]
        news += _change(state, content, fid, FigureChange(fate="重創" if destiny else "退場"))
        add_rumor(state, "".join(news), content=content, layer="world")
        lines += news
    return lines


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


def can_challenge(state: GameState, content: Content, fid: str) -> bool:
    """這位人物此刻挑戰得了嗎：在場（active）、有所在，而且在戰線上領兵——戰線空著的人（董卓、趙弘、重挫退下的人）
    不受挑戰（PM 2026-10-05 定），人物表標了 challenge_off_front 的何進例外。挑戰按鈕（Game._challenge_options）與
    軍令卡、輿圖上的打擊軍令（atlas.strike_how、strike_marks）都問這一份規則；閉門不見（snub）是另一回事，看個人。"""
    now, fig = state_of(state, content, fid), content.figures.get(fid)
    return now.status == "active" and bool(now.location) and (now.front is not None or (fig is not None and fig.challenge_off_front))


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
