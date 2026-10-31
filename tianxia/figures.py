"""大勢人物（計畫 T4；T2 先放了只改欄位的最小版）。

人物表（content/figures.json，濃縮版內容表 1.1）上每一位這一季的聲威、狀態、戰線、所在，存在 WorldState.figures；
第一季開季那一刻照人物表種好（world_state.stamp_season 呼叫 seed），其他季第一次被打贏才寫（_ensure）。
挑戰本人每季都有（挑戰大勢人物每季都有設計）：challenge_on 是開關，untimed 是「有挑戰本人但不是第一季」（沒有時刻表的季，
才有 recover、defeat 的一天上限、leader_out）。推戰線（tick）與時刻表的人物結局（apply）只在第一季。
- 讀：state_of（沒種過的照人物表的起始值，不寫回存檔）、present_at／placed_characters（誰在哪裡）、commander
  （那條戰線那一方的主將）、difficulty／squad_of（挑戰本人的難度）。
- 改：apply（時刻表的人物結局與接手）、defeat（挑戰本人打贏扣聲威）。

state 是 GameState（季的事用的是 world._season_vehicle 那個空殼玩家），只讀寫 state.world；不碰儲存。
人物表沒有的 id（測試夾具）照 T2 最小版的規則：FigureState 的預設值、只改欄位。"""
from __future__ import annotations

from . import calendar, push, relations, seal_acts
from .calendar import DAY
from .models import Content, FigureChange, FigureDef, Squad
from .rules import add_rumor, change_trend, season_one, trend_shown, trend_value, world_day
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


def challenge_on(content: Content, world: WorldState) -> bool:
    """這一季有沒有「挑戰大勢人物本人」（挑戰每季都有設計 3.1）：人物表有人、劇本有陣營才有；第一季的規則開著一定有（打擊軍令
    靠它交差），其他季看 Config.figure_challenge_every_season（主機的退路：關掉就回到「只有第一季」）。"""
    if not content.figures or not content.scenario.factions:
        return False
    return season_one(content, world) or content.config.figure_challenge_every_season


def untimed(content: Content, world: WorldState) -> bool:
    """沒有時刻表的季：有挑戰本人、但不是第一季（14 天的預設設定）。聲威回復、一天上限、龍頭人物退場停手、out_flag 只在這種季。"""
    return challenge_on(content, world) and not season_one(content, world)


def upkept(content: Content, world: WorldState) -> bool:
    """大勢人物的聲威有回復（recover）與一天上限（loss_cap）的季：沒有時刻表的季，加上 21 天季的第一季（正式季整合 3.9、12.3 第 17 條：
    讓人物撐到時刻表寫到他的那一天）。週末的第一季照舊沒有。龍頭人物退場停手、out_flag 照舊只在沒有時刻表的季（untimed）。"""
    return untimed(content, world) or (season_one(content, world) and calendar.season21_on(world, content))


def loss_cap(content: Content, world: WorldState) -> int | None:
    """挑戰本人打贏時，這位人物這一天最多被打掉幾點（figure_daily_loss_cap；0 或不是 upkept 的季是 None）。"""
    cap = content.config.figure_daily_loss_cap
    return cap if cap and upkept(content, world) else None


def by_name(content: Content, name: str) -> str | None:
    """名字是這個的大勢人物 id（龍頭人物〔虛擬玩家〕照名字對人物表；atlas 與 world 共用）。"""
    return next((fid for fid, fig in content.figures.items() if fig.name == name), None)


def leader_out(state: GameState, content: Content, name: str) -> bool:
    """這位龍頭人物（虛擬玩家，照名字）在沒有時刻表的季已經退場或重創（丙 (c)：不再出手、輿圖不再標他）。緊急開關關著、第一季、
    人物表沒有同名的人，一律是假（虛擬玩家照舊）。"""
    fid = by_name(content, name)
    return fid is not None and untimed(content, state.world) and is_out(state, fid)


def present_at(state: GameState, content: Content, loc_id: str) -> list[str]:
    """此刻在這個地點、在場（active）的人物（人物表的順序）。下獄、退場、重創、還沒出場的都不算。"""
    return [
        fid for fid in content.figures
        if (now := state_of(state, content, fid)).status == "active" and now.location == loc_id
    ]


def placed_characters(state: GameState, content: Content) -> dict[str, str | None]:
    """有挑戰本人的季（challenge_on）：人物表上有對話人物的那幾位此刻在哪裡：在場的是所在地點，下獄、退場、重創、還沒出場的是
    None（求見、交友都沒有他）。沒有挑戰本人的季（緊急開關關著、劇本沒有陣營）是空的：大家照 characters.json 的 talk_at。
    14 天的季沒人退場時跟 talk_at 一模一樣（content.check_figures 驗開季地點等於 talk_at）。"""
    out: dict[str, str | None] = {}
    if life_on(content):  # 人物活起來：不是大勢人物的人物照每日行事走到的地方（沒走過的照 talk_at，不寫）
        out.update(state.world.whereabouts)
    if not challenge_on(content, state.world):
        return out
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
    四捨五入成整數（總計畫第五節；先 round 到小數六位，免得 127.4999… 這種浮點雜訊）。人物活起來開著時再乘心事
    （負傷 hurt_scale、悲憤 grief_scale；決戰份量照這一條算，兩邊都吃到）。"""
    fig = content.figures[fid]
    floor = content.config.figure_difficulty_floor
    prestige = state_of(state, content, fid).prestige
    value = content.squads[fig.squad].difficulty * (floor + (1 - floor) * prestige / 100) * mood_scale(state, content, fid)
    return int(round(value, 6) + 0.5)


def start_difficulty(content: Content, fid: str) -> int:
    """這位人物開季時（人物表的 start_prestige）的挑戰難度：戊 (b) 獎勵打折的分母。寫法同 difficulty。"""
    fig = content.figures[fid]
    floor = content.config.figure_difficulty_floor
    value = content.squads[fig.squad].difficulty * (floor + (1 - floor) * fig.start_prestige / 100)
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
    faction = content.scenario.find_faction(fig.faction)
    return faction.goals.get(now.front, 0) if faction is not None else 0


def started(state: GameState, content: Content, fid: str, time: float) -> bool:
    """這位人物在世界秒 time 已經出兵推線了沒（tick；atlas 寫「…起」）：21 天季照天數（FigureDef.active_from_day，沒寫是 0；
    正式季整合設計 1.2 給開發 5），其他季照週次（active_from_week）。"""
    fig = content.figures[fid]
    if calendar.season21_on(state.world, content):
        return calendar.cal_days(time, content, state.world) + calendar.EPS_SECONDS >= _from_day(fig, content, state.world)
    return calendar.point(time, content, state.world).week >= fig.active_from_week


def _from_day(fig: FigureDef, content: Content, world: WorldState) -> float:
    """照現實天的季這位人物第幾天才出兵（季曆第 1 週週初起幾天，沒寫是 0）：7 天濃縮季讀 active_from_day7，21 天季 active_from_day。"""
    return (fig.active_from_day7 if calendar.week7_on(world, content) else fig.active_from_day) or 0.0


def start_text(state: GameState, content: Content, fid: str) -> str:
    """還沒出兵時「（…起）」那一句（atlas）：21 天季寫出兵的那一刻（季曆，calendar.stamp_text），其他季寫第幾週。待 joy 潤。"""
    fig, w = content.figures[fid], state.world
    if calendar.season21_on(w, content):
        at = (_from_day(fig, content, w) * calendar.DAY - w.cal_offset) / calendar.cal_scale(content, w)
        return f"（{calendar.stamp_text(at, content, w)} 起）"
    return f"（第 {fig.active_from_week} 週起）"


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
    for fid, fig in content.figures.items():
        goal = push_goal(state, content, fid)
        if not goal or not started(state, content, fid, middle):
            continue
        front = state_of(state, content, fid).front
        value = trend_value(state, content, front)
        losing = (50 - value) * goal >= cfg.figure_reaction_lean
        rate = fig.actions_per_day * (cfg.figure_reaction_mult if losing else 1.0)
        scale = _stance_push(state, content, fid)  # 人物心意（減法季批 6）：速戰加倍、持重與恤民不推；關著是 1、一個字都不變
        if scale != 1.0:
            rate *= scale
        if cfg.push_resistance.enabled:  # 盡頭阻力（出陣探索與地盤設計 5.1）：往對方老巢推得慢，累積照推之前的戰線打折
            rate *= push.resistance_share(value, goal, push.tuning_for(w, content))
        key = f"fig:{fid}"
        pending = w.trend_accum.get(key, 0.0) + rate * cal_hours / 24
        whole = int(pending + 1e-9)  # 容一點浮點誤差：24 個 1/24 才剛好湊成 1（累積不先四捨五入，誤差才不會越滾越大）
        rest = max(0.0, pending - whole)
        if rest:
            w.trend_accum[key] = rest
        else:
            w.trend_accum.pop(key, None)
        if whole:
            change_trend(state, content, front, whole * fig.push * goal, reveal=False)


def _stance_push(state: GameState, content: Content, fid: str) -> float:
    """人物心意照著做的那一個要他推線乘幾倍（stances.push_scale）。stances → calendar、rules：延後 import。"""
    from . import stances  # noqa: PLC0415

    return stances.push_scale(state, content, fid)


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


MOVING_FATES = ("退場", "重創", "下獄", "重挫", "到任")  # 會搬動或拿掉人物的結局（moves）


def moves(now: FigureState, change: FigureChange, content: Content) -> bool:
    """這一筆效果會不會搬動或拿掉這位人物（玉璽碎片改版第 2 批：引將提前結束、窗口檢查都問它）：退場、重創、下獄、重挫、到任，寫了轉往的
    地點，或聲威會被扣到 0（_change 照退場或重創處理；聲威大減、受挫沒扣到 0 留在原地）。"""
    if change.fate in MOVING_FATES or change.location is not None:
        return True
    return now.prestige + content.config.fate_prestige.get(change.fate or "", 0) + change.prestige <= 0


def _change(state: GameState, content: Content, fid: str, change: FigureChange) -> list[str]:
    """apply 的本體：改這位人物、空出戰線時照接位鏈交接；回傳接手的那一句與倒下時盟友、仇敵的反應（figure_life.on_fall）
    （apply 拿去發傳聞、defeat 接在退場那句後面）。被引將釘著、這一筆又會搬動或拿掉他時，引將先提前結束、回原處（時刻表優先，
    玉璽碎片改版五之一 1），接位的人才接得到原本的所在。"""
    figure = _ensure(state, content, fid)
    if seal_acts.pinned(state.world, fid) is not None and figure.status not in OUT and moves(figure, change, content):
        seal_acts.release(state, content, fid)
    if figure.status in OUT:
        if change.fate in ZEROED:  # 被挑戰打倒、還等著回來的人，時刻表也寫他退場（例：張角病逝）：就不回來了
            figure.back_at = figure.back_front = None
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
    react: list[str] = []
    if figure.status in OUT:
        figure.fell_at = state.world.time  # 心事：同陣營同戰線的人悲憤（mood_of）
        from . import figure_life  # noqa: PLC0415  figure_life → figures：延後載入

        react = figure_life.on_fall(state, content, fid)  # 第二批：盟友悲憤趕來、掛復仇懸賞，仇敵得意（接在接手那一句後面）
        figure_life.note_fall(state, content, fid)  # 世界活起來：記一筆世界記事（figure_fell）
    if fate in ("重挫", "到任"):  # 重挫：退出原戰線、轉往別處；到任：接下新戰線
        figure.front = change.front
        if change.location is not None:
            figure.location = change.location
    if fig is None or fate not in HANDOFF_FATES or held is None or (figure.status == "active" and figure.front == held):
        return react
    return _hand_over(state, content, fid, held, post) + react


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
            seal_acts.release(state, content, nxt)  # 接位的人正被引將釘著：時刻表優先（玉璽碎片改版五之一 1），先回原處再接
            heir = _ensure(state, content, nxt)
            heir.status, heir.front, heir.location = "active", front, location
            return [f"{name_of(content, nxt)}接手{_front_name(content, front)}的戰事。"]
        nxt = content.figures[nxt].successor
    return []


def _front_name(content: Content, front: str) -> str:
    return next((t.name for t in content.scenario.trends if t.id == front), front)


OUT_BACK = "{name}連吃敗仗，聲威掃地，只得收兵退下，一時號令不動手下的兵。"  # 待 joy 潤：被挑戰打退、過幾天會回來（PM 2026-10-16）
OUT_BACK_DESTINY = "{name}連吃敗仗，元氣大傷，只得退下養傷，一時露不了面。"
BACK_LINE = "{name}收拾殘部，重新出來領兵{where}。"  # 待 joy 潤：回來那一句（天下大事）
DRAW_LINE = "你與{name}過了數十招不分勝負，各自收手；這一番交手讓你有所長進。"  # 挑戰本人打成僵持（engine._challenge_draw）
DENT_ONCE_LINE = "{name}今天已經在你手下敗過一陣，這一場沒能再動搖他的聲威。"  # 待 joy 潤：同一個人同一天第二場起（figure_dent_once_per_day）
HELD_LINE = "{name}今天已經敗了好幾陣，部眾死守不退。"  # 待 joy 潤：沒有時刻表的季，這位人物今天被打掉的聲威到了上限（甲 (d)）


def defeat(state: GameState, content: Content, fid: str, amount: float, cap: int | None = None) -> list[str]:
    """挑戰本人打贏（計畫 T4、軍令文件 4.5）：他敗走，聲威扣 amount（人數緩衝之後的量，可能有小數；不足一點的記在
    trend_accum["prestige:<id>"]，滿一點才扣）。扣到 0 時照退場（天命人物重創）處理、由接位的人接下戰線，退場與接手
    合成一則天下大事。回傳給打贏的人看的句子：「波才聲威 -5」，歸零時再接退場與接手那幾句。已經退場的人不再扣。
    figure_return_days 不是 0 時，打到歸零的人記下回來的時刻與他守的戰線（revive），退場那一句也不說「今年露不了面」。
    cap（沒有時刻表的季才給，甲 (d)）：這一位這個遊戲日最多被打掉幾點；今天被打掉的量記在 trend_accum["lost:<id>:<遊戲日>"]
    （舊日子的順手刪掉），到了上限聲威不動、回 HELD_LINE。"""
    figure = _ensure(state, content, fid)
    if figure.status in OUT or amount <= 0:
        return []
    w = state.world
    if cap:
        day_key = f"lost:{fid}:{world_day(content, w)}"
        for old in [k for k in w.trend_accum if k.startswith(f"lost:{fid}:") and k != day_key]:
            del w.trend_accum[old]
        left = cap - w.trend_accum.get(day_key, 0.0)
        if left <= 1e-9:
            return [HELD_LINE.format(name=name_of(content, fid))]
        amount = min(amount, left)
        w.trend_accum[day_key] = w.trend_accum.get(day_key, 0.0) + amount
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
    if figure.prestige < before:
        figure.hurt_at = w.time  # 心事：負傷（mood_of）
    if figure.prestige == 0:
        destiny = fid in content.figures and content.figures[fid].destiny
        days = content.config.figure_return_days
        held = figure.front if figure.status == "active" else None
        # 濃縮版內容表 1.5（S1 審過）：不說「這一季」；退場句後面緊接接手句，所以這裡不再寫「的戰事」
        if days > 0 and fid in content.figures:
            news = [(OUT_BACK_DESTINY if destiny else OUT_BACK).format(name=name)]
        else:
            news = [f"{name}連吃敗仗，元氣大傷，今年是露不了面了。" if destiny else f"{name}連吃敗仗，聲威掃地，再也號令不動手下的兵。"]
        news += _change(state, content, fid, FigureChange(fate="重創" if destiny else "退場"))
        if days > 0 and fid in content.figures and figure.status in OUT:
            figure.back_at = w.time + days * 24 * calendar.cal_hour_seconds(content, w)
            figure.back_front = held
        add_rumor(state, "".join(news), content=content, layer="world")
        lines += news
    return lines


def recover(state: GameState, content: Content, cal_hours: float) -> None:
    """沒有時刻表的季（甲 (b)）：存檔裡有寫的人物（沒被打過的本來就是開季值），在場、聲威低於人物表的開季值時，每個季曆天回
    figure_prestige_regen 點（累積在 trend_accum["regen:<id>"]，滿一點加一點），回到開季值為止；退場、重創、不在場的不回，
    累積拿掉；人物表已經沒有的 id 跳過。決定性的，不擲骰，不發傳聞。由 world.advance_world_state 每一步呼叫。"""
    w = state.world
    rate = content.config.figure_prestige_regen
    if not upkept(content, w) or rate <= 0:  # 21 天季的第一季也回（正式季整合 3.9）
        return
    for fid, now in w.figures.items():
        fig = content.figures.get(fid)
        if fig is None:
            continue
        key = f"regen:{fid}"
        if now.status != "active" or now.prestige >= fig.start_prestige:
            w.trend_accum.pop(key, None)
            continue
        pending = w.trend_accum.get(key, 0.0) + rate * cal_hours / 24
        whole = int(pending + 1e-9)  # 容一點浮點誤差（同 tick）
        if whole:  # 跟犒軍共用一天的上限（figure_aid.restore；開關關著照舊補到開季值）
            from . import figure_aid  # noqa: PLC0415  figure_aid → figures：延後 import
            figure_aid.restore(state, content, fid, whole)
        rest = max(0.0, pending - whole)
        if rest and now.prestige < fig.start_prestige:
            w.trend_accum[key] = rest
        else:
            w.trend_accum.pop(key, None)


def revive(state: GameState, content: Content) -> list[str]:
    """被挑戰打到退場、重創的人物（defeat 記了 back_at）時候到了就回來（PM 2026-10-16）：聲威是開季的 figure_return_share、
    回到倒下時守的戰線與所在；那條戰線這段時間由同一方接位的人接著的，接位的人把戰線交還（留在原地、不領兵）。時刻表把他
    寫成退場、重創的（_change）不回來。兩種季都有；決定性的，不擲骰。由 world.advance_world_state 每一步呼叫；
    回來那一句發天下大事，也回傳。"""
    w = state.world
    lines = []
    for fid, now in w.figures.items():
        fig = content.figures.get(fid)
        if now.back_at is None or w.time < now.back_at:
            continue
        front, now.back_at, now.back_front = now.back_front, None, None
        w.aid_tally.pop(f"visitcut:{fid}", None)  # 探望提前了多少：這一次倒下的帳
        if fig is None or now.status not in OUT:
            continue
        now.status = "active"
        now.prestige = max(1, int(fig.start_prestige * content.config.figure_return_share + 0.5))
        now.front = front
        if front is not None:
            for other, ofig in content.figures.items():
                there = w.figures.get(other)
                if other != fid and ofig.faction == fig.faction and there is not None and there.status == "active" and there.front == front:
                    there.front = None  # 接位的人把戰線交還
        where = f"，回到{_front_name(content, front)}" if front is not None else ""
        line = BACK_LINE.format(name=name_of(content, fid), where=where)
        add_rumor(state, line, content=content, layer="world")
        lines.append(line)
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


# ── 心事（人物活起來，FigureLifeTuning）───────────────────

MOODS = ("得意", "焦慮", "負傷", "悲憤")  # 沒有心事（觀望、平常）是 None


def life_on(content: Content) -> bool:
    """人物活起來開著沒（主機的緊急開關；測試內容關著）。"""
    return content.config.figure_life.enabled


def mood_span(content: Content, world: WorldState) -> float:
    """負傷、悲憤撐多久（世界秒）：mood_cal_days 個季曆天。"""
    return content.config.figure_life.mood_cal_days * 24 * calendar.cal_hour_seconds(content, world)


def mood_of(state: GameState, content: Content, fid: str) -> str | None:
    """這位大勢人物此刻的心事，照事實算、不存檔、不擲骰：
    - 悲憤：同陣營、同一條戰線（他守的或倒下時守的）的人、或關係表上的盟友（relations）剛退場或重創（mood_span 之內）；
    - 負傷：他自己剛被挑戰打掉聲威；
    - 焦慮：他那條戰線偏向對方 lean 以上，或聲威不到開季的一半；
    - 得意：關係表上的仇敵剛倒下，或他那條戰線偏向自己這一方 lean 以上。
    不是大勢人物、開關關著、不在場的人是 None。"""
    fig = content.figures.get(fid)
    if fig is None or not life_on(content):
        return None
    now = state_of(state, content, fid)
    if now.status != "active":
        return None
    w = state.world
    span = mood_span(content, w)
    tie = relations.mood(state, content, fig.character, span) if fig.character is not None else None  # 第二批：兄弟、師生、上下、仇敵
    if tie == "悲憤":
        return tie
    front = line_of(state, content, fid)
    for other, ofig in content.figures.items():
        if other == fid or ofig.faction != fig.faction:
            continue
        there = w.figures.get(other)
        if there is None or there.fell_at is None or w.time - there.fell_at > span:
            continue
        if front is not None and front in (there.front, there.back_front, ofig.front, line_of(state, content, other)):
            return "悲憤"
    if now.hurt_at is not None and w.time - now.hurt_at <= span:
        return "負傷"
    if tie is not None:  # 仇敵剛倒下：得意
        return tie
    tuning = content.config.figure_life
    if now.prestige * 2 < fig.start_prestige:
        return "焦慮"
    faction = content.scenario.find_faction(fig.faction)
    goal = faction.goals.get(front, 0) if faction is not None and front is not None else 0
    if goal:
        line = front if trend_shown(content, w, front) else "huangjin"  # 規則關著的季三條戰線合成黃巾聲勢
        lean = (trend_value(state, content, line) - 50) * goal
        if lean >= tuning.lean:
            return "得意"
        if lean <= -tuning.lean:
            return "焦慮"
    return None


def line_of(state: GameState, content: Content, fid: str) -> str | None:
    """這位人物心事與襲擾看的那條戰線：他守的戰線；沒有戰線的（偏將傅燮、秦頡、卜己、劉辟，不當主將也不推）照所在地點的大區。"""
    now = state_of(state, content, fid)
    if now.front is not None:
        return now.front
    from .rules import front_of  # noqa: PLC0415

    return front_of(content, now.location) if now.location else None


def mood_scale(state: GameState, content: Content, fid: str) -> float:
    """心事改挑戰難度（也是決戰份量）：負傷 hurt_scale、悲憤 grief_scale，其餘 1。"""
    mood = mood_of(state, content, fid)
    tuning = content.config.figure_life
    return tuning.hurt_scale if mood == "負傷" else tuning.grief_scale if mood == "悲憤" else 1.0
