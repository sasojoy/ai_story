"""江湖輿圖的圖層、詳情與勝算（全部拆包第 50 批「輿圖二」：tianxia/atlas.py 拆兩半，這是輿圖包的那一半；計畫
docs/superpowers/plans/2026-11-07-輿圖包-第2批.md 1.1、1.2）。

大地圖四個圖層要標的東西（局勢：大區的大勢、龍頭人物在這裡／出兵之前／閒著；本週軍令的打擊標記；劇情：本週的目標、耳聞所及的傳聞；
敵情：此地的對手與最凶的那一路）、地點詳情那一欄（detail_text：意境與地利、地盤、尋敵分級、路程與走法）、標題那一行與大地圖選得到的地點。
勝算只在呼叫端傳入 odds 函式時才算（敵情層與詳情欄），平常重畫不模擬。

原本寫在 tianxia/atlas.py，一個字沒改（第 29 批之二 annals → standing 的拆法）；地點、大區、路線、走法時間、軍令卡的寫法與打擊點、
安排前往的條件與 LAYERS 那一半留在 atlas（共用規則層 registry.SHARED），這裡從它拿 KNOWN、views、is_known、region_of、_strike_place、
MODES、mode_text、returns_at_once、way_to、_names 十個名字。舊名 atlas.<圖層> 不留別名（共用層不准 import 包）：輿圖包的 actions、
mapview、mapdata 與測試照新的路徑讀。
"""
from __future__ import annotations

import math
from collections.abc import Callable

from tianxia import allied, conquest, figures, insights, mounts, orders, terrain, territory  # 共用規則層
from tianxia.atlas import KNOWN, MODES, is_known, mode_text, region_of, returns_at_once, views, way_to  # 共用規則層（atlas 留下的那一半，第 50 批拆兩半）
from tianxia.atlas import _names, _strike_place  # noqa: SLF001  同上（兩半原本在同一個檔）
from tianxia.calendar import stamp_text
from tianxia.models import Content, Location, MapRegion, SimPlayer
from tianxia.rules import (
    audible, ears_of, here_regions, is_revealed, recent_seconds, resolve_trend, resolve_trends, season_one, trend_value,
)
from tianxia.state import GameState, Order, Rumor, WorldState
from tianxia.world import current_act, sim_active, storyline_off

NEWS_DAYS = 3  # Config.rumor_board_days 的預設，只給 mapview.LEGEND_LAYERS 那一份預設說明用；✦、詳情欄、圖例真正用的是 news_days(content)
NEWS_FAR = "這一帶離得遠，沒聽到什麼消息"  # 詳情欄：不在耳聞所及的大區，不替玩家斷言「沒有消息」（待 joy 潤）
LEADER_NEWS = 2  # 詳情欄每位龍頭人物最多列幾則最近提到他的傳聞
LEADER_WHO = "江湖上的龍頭人物，會自己行動，左右江湖大勢"
LEADER_QUIET = "眼下沒有動靜"
ODDS_ORDER = ("穩勝", "有把握", "五五波", "難分勝負", "凶險", "必敗")  # 由易到難；「最險」取排在最後的
DRILL = "操練"  # 自己陣營的隊伍：遇上了一起操練、不會輸，不算勝算（見 foes）
ARROWS = ("→", "↘", "↓", "↙", "←", "↖", "↑", "↗")  # 從正東起順時針，每 45 度一個（畫面座標 y 向下）
UNKNOWN = "尚未摸清"
Odds = Callable[[str], str]  # 敵方隊伍 id → 勝算（Game.odds）


# ── 開放與摸清 ──────────────────────────────────────────────


def place_choices(state: GameState, content: Content) -> list[tuple[str, str]]:
    """大地圖選得到的地點（顯示文字, 地點 id），依內容順序：已開放的寫名字（所在地另外註明）；未開放的不列。"""
    return [
        (content.locations[loc_id].name + ("（所在地）" if view == "current" else ""), loc_id)
        for loc_id, view in views(state, content).items() if view in KNOWN
    ]


# ── 大區 ──────────────────────────────────────────────


def direction(start: tuple[float, float], end: tuple[float, float]) -> str:
    """從 start 看 end 的八方位箭頭。"""
    angle = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
    return ARROWS[round(angle / 45) % len(ARROWS)]


# ── 局勢 ──────────────────────────────────────────────


def region_trends(state: GameState, content: Content, region: MapRegion) -> list[tuple[str, int]]:
    """大區對應、而且已經浮現的大勢：（名稱, 數值）；隱藏的大勢浮現前不列。地圖寫的戰線照 rules.resolve_trend 換
    （開關關著時三條戰線都是黃巾聲勢），換到同一條的只列一次。"""
    names = {t.id: t.name for t in content.scenario.trends}
    shown: list[str] = []
    for key in region.trends:
        trend_id = resolve_trend(content, state.world, key)
        if trend_id is not None and trend_id not in shown and is_revealed(state.world, content, trend_id):
            shown.append(trend_id)
    return [(names[trend_id], trend_value(state, content, trend_id)) for trend_id in shown]


def sim_shown(sim: SimPlayer, state: GameState) -> bool:
    """龍頭人物要等他需要的隱藏大勢浮現（requires_revealed 與條件裡的 revealed_all）才標在地圖上。"""
    needed = ([sim.requires_revealed] if sim.requires_revealed else []) + sim.condition.revealed_all
    return set(needed) <= state.world.revealed


def haunters(state: GameState, content: Content, loc_id: str) -> list[str]:
    """常出沒在這個地點、而且已經該露面的龍頭人物名字（同名只列一次）。第一季的規則開著時是此刻站在這裡的大勢人物
    （figures.present_at；虛擬玩家那時不出手，也不再標）。不檢查視野：呼叫端要先用 is_known 把關。"""
    if season_one(content, state.world):
        return [content.figures[fid].name for fid in figures.present_at(state, content, loc_id)]
    names = [  # 沒有時刻表的季退場的龍頭人物不再標（丙 (c)，figures.leader_out）
        sim.name for sim in content.scenario.sim_players
        if loc_id in sim.haunts and sim_shown(sim, state) and not figures.leader_out(state, content, sim.name)
    ]
    return list(dict.fromkeys(names))


def leader_activity(state: GameState, content: Content, name: str) -> str:
    """龍頭人物現在在做什麼：他名下此刻會行動的設定（和世界模擬同一條規則，見 world.sim_active），
    寫成「每天約出手 N 次，讓某某大勢上升／下降」。只寫已浮現的大勢，隱藏大勢不提；沒有一條會行動時寫「眼下沒有動靜」。
    第一季的規則開著時照大勢人物的推動寫（_figure_activity）。"""
    if season_one(content, state.world):
        return _figure_activity(state, content, name)
    trend_names = {t.id: t.name for t in content.scenario.trends}
    doing = []
    for sim in content.scenario.sim_players:
        if sim.name != name or not sim_active(sim, state, content):
            continue
        moves = resolve_trends(content, state.world, sim.trend)  # 開關關著時戰線都算黃巾聲勢
        ups = [trend_names[t] for t, delta in moves.items() if delta > 0 and is_revealed(state.world, content, t)]
        downs = [trend_names[t] for t, delta in moves.items() if delta < 0 and is_revealed(state.world, content, t)]
        pushes = ([f"讓{'、'.join(ups)}上升"] if ups else []) + ([f"讓{'、'.join(downs)}下降"] if downs else [])
        doing.append("，".join([f"每天約出手 {sim.actions_per_day:g} 次", *pushes]))
    return "；".join(doing) or LEADER_QUIET


def _figure_activity(state: GameState, content: Content, name: str) -> str:
    """第一季：大勢人物在做什麼（figures.tick 的規則）——「每天約出手 N 次，讓某戰線上升／下降」，還沒到出兵那一週時
    後面接「（第 N 週起）」；不推的（沒有戰線、何進）寫「眼下沒有動靜」。"""
    fid = figures.by_name(content, name)
    goal = figures.push_goal(state, content, fid) if fid is not None else 0
    if not goal:
        return LEADER_QUIET
    fig, front = content.figures[fid], figures.state_of(state, content, fid).front
    front_name = next((t.name for t in content.scenario.trends if t.id == front), front)
    text = f"每天約出手 {fig.actions_per_day:g} 次，讓{front_name}{'上升' if goal > 0 else '下降'}"
    if not figures.started(state, content, fid, state.world.time):
        text += figures.start_text(state, content, fid)
    return text


def leader_news(state: GameState, content: Content, name: str) -> list[Rumor]:
    """最近提到這位龍頭人物的傳聞（不分地點、不限天數），最新的在前，最多 LEADER_NEWS 則。只列聽得到的（rules.audible：
    別陣營的軍情、寫給別人的個人線索聽不到；第一季別的大區的地方傳聞、撤下傳聞板的也聽不到）。"""
    ears = ears_of(state, content)
    return [r for r in reversed(state.world.rumors) if name in r.text and audible(r, ears)][:LEADER_NEWS]


HERE_TITLE = "**此地的大勢人物**"  # 待 joy 潤：沒有時刻表的季，此刻站在這裡、不是常出沒龍頭人物的大勢人物（挑戰每季都有設計 3.8）
REGEN_NOTE = "沒人去打，他的聲威會慢慢回來"  # 待 joy 潤（甲 (b)）
IDLE_NOTE = "按兵不動，不出營應戰"  # 待 joy 潤：戰線空著、挑戰不了的人物（董卓、趙弘）


def _regen_note(state: GameState, content: Content) -> str:
    """聲威那一行後面接的「沒人去打……慢慢回來」：沒有時刻表的季、回復開著才有。"""
    return f"；{REGEN_NOTE}" if figures.upkept(content, state.world) and content.config.figure_prestige_regen > 0 else ""


def _here_text(state: GameState, content: Content, fid: str) -> str:
    """「此地的大勢人物」一行：名字、聲威、情誼（有對話人物才有）、聲威會回、戰線空著的寫按兵不動。"""
    line = f"- {figures.name_of(content, fid)}　聲威 {figures.state_of(state, content, fid).prestige}（越高越難打）"
    cid = content.figures[fid].character
    if cid is not None:
        line += f"；你跟他的情誼 {state.player.affinities.get(cid, 0)}"
    line += _regen_note(state, content)
    if not figures.can_challenge(state, content, fid):
        line += f"；{IDLE_NOTE}"
    return line + "。"


def leader_text(state: GameState, content: Content, name: str, loc_id: str | None = None) -> str:
    """詳情欄裡一位常出沒在此的龍頭人物：他是誰、現在在做什麼、最近的傳聞（沒有就不寫）。
    和 haunters 一樣不檢查視野與是否該露面：呼叫端要先把關。聲威、情誼兩行：第一季照寫；沒有時刻表的季只有人物此刻就站在
    loc_id 才寫（挑戰每季都有設計 3.8：皇甫嵩站在長社，潁川那一段不寫，黃巾的人不會以為在潁川打得到他）。"""
    lines = [f"**龍頭人物**　{name}（常出沒在此）", f"- {LEADER_WHO}。"]
    fid = figures.by_name(content, name)
    w = state.world
    if fid is not None and not (season_one(content, w) or (
            figures.untimed(content, w) and loc_id is not None and fid in figures.present_at(state, content, loc_id))):
        fid = None
    if fid is not None:  # 聲威寫出來，挑戰本人之前看得到好不好打
        lines.append(f"- 聲威 {figures.state_of(state, content, fid).prestige}（越高越難打）{_regen_note(state, content)}。")
        cid = content.figures[fid].character
        if cid is not None:  # 談得上話的人物：你跟他的情誼（explain-1；沒有對話人物的彭脫、韓忠沒有情誼）
            lines.append(f"- 你跟他的情誼 {state.player.affinities.get(cid, 0)}（談得投機會漲）。")
    lines.append(f"- 現在：{leader_activity(state, content, name)}。")
    news = leader_news(state, content, name)
    if news:
        lines += ["- 最近：", *(f"  - {stamp_text(r.time, content, state.world)}　{r.text}" for r in news)]
    return "\n".join(lines)


# ── 本週軍令的打擊（FB-072）────────────────────────────

STRIKE_MARK = "◎"  # 輿圖局勢層：本週打擊軍令的目標人物所在的地點，名字前加這個記號（還沒摸清時加在大區名稱前）


def _open_strikes(state: GameState, content: Content) -> list[Order]:
    """這個玩家自己陣營這週還沒達成的打擊軍令（有目標人物的）；散人、別陣營、開關關著、休季都是空的（同 Game.orders_view）。"""
    if state.world.ended:
        return []
    return [
        o for o in orders.current(state, content, allied.side_of(state, content))  # 豪強分屬兩軍：依附那一軍的軍令
        if o.template == "strike" and not o.done and o.figure is not None
    ]


def strike_marks(state: GameState, content: Content) -> tuple[set[str], set[str]]:
    """局勢層要標的本週打擊目標：（摸清的所在地點 id, 大區 id）。目標的所在摸清了就標地點；沒摸清就標它所屬的大區
    （只標大區、不標地點，所在不洩漏）。只算自己陣營這週還沒達成、而且他眼下挑戰得了的打擊軍令。"""
    places: set[str] = set()
    regions: set[str] = set()
    for order in _open_strikes(state, content):
        loc_id = _strike_place(state, content, order)
        if loc_id is None:
            continue
        if is_known(state, content, loc_id):
            places.add(loc_id)
        elif (region := region_of(content, loc_id)) is not None:
            regions.add(region.id)
    return places, regions


# ── 劇情 ──────────────────────────────────────────────


def goal_places(state: GameState, content: Content) -> list[str]:
    """目前這一幕主線的目標地點。隱藏主線要等大勢浮現、取代主線後，才會是「目前這一幕」。第一季不觸發的 beta 主線
    （計畫 T8）沒有目標。不檢查視野：呼叫端要用 is_known 把關，沒摸清的目標不能標出來。"""
    return [] if storyline_off(state, content) else list(current_act(state, content).places)


def news_days(content: Content) -> float:
    """劇情層 ✦ 與詳情欄的「最近幾天」：跟大區的傳聞板同一個旋鈕（Config.rumor_board_days；第一季是季曆天），
    所以本區地方傳聞的 ✦ 不會比那則傳聞在板上活得久，天下大事的 ✦ 也跟著同一個長度收。"""
    return content.config.rumor_board_days


def _heard_news(state: GameState, content: Content) -> list[Rumor]:
    """最近 news_days 天（第一季是季曆天）、有發生地、而且聽得到的大事與傳聞（rules.audible），最新的在前：劇情層的 ✦
    與詳情欄都看這一份（傳聞分層設計第九節「只標你聽得到的」）。"""
    since = state.world.time - recent_seconds(news_days(content), content, state.world)
    ears = ears_of(state, content)
    return [r for r in reversed(state.world.rumors) if r.location is not None and r.time >= since and audible(r, ears)]


def news_places(state: GameState, content: Content) -> set[str]:
    """劇情層要標 ✦ 的地點（整張圖只算一次，不必每個地點各掃一遍傳聞）。不檢查視野：呼叫端只標摸清的地點。"""
    return {r.location for r in _heard_news(state, content)}


def recent_news(state: GameState, content: Content, loc_id: str) -> list[Rumor]:
    """這個地點最近 news_days 天、聽得到的大事與傳聞，最新的在前。不檢查視野：呼叫端要先用 is_known 把關。"""
    return [r for r in _heard_news(state, content) if r.location == loc_id]


def _in_earshot(state: GameState, content: Content, loc_id: str) -> bool:
    """這個地點的消息你聽不聽得到：第一季照此刻人在哪些大區（rules.here_regions，在路上是兩頭）；beta、地圖沒有大區都算聽得到。
    詳情欄靠它分辨「這一帶真的沒事」與「那一區離得遠、聽不到」。"""
    ears = ears_of(state, content)
    region = region_of(content, loc_id)
    return not ears.layered or region is None or region.id in here_regions(state, content)


# ── 敵情 ──────────────────────────────────────────────


def foes(
    content: Content, loc: Location, odds: Odds, faction: str | None = None, world: WorldState | None = None,
    squad_ids: list[str] | None = None,
) -> list[tuple[str, str]]:
    """可能遇到的隊伍與勝算：（隊伍名稱, 勝算），同一隊只列一次。faction 是自己的陣營：自己陣營的隊伍遇上了是
    一起操練、不會輸（engine._drill），寫「操練」不算勝算（試玩回饋 FB-008）。
    world 給了：站的隊伍照控制方（territory.squads_at，地盤易手）；沒給照 loc.enemies。
    squad_ids 給了（FB-858，減法季 3d）：就列這幾路，不另查站的隊伍——領地爭奪開著時出陣真的會打的那一路
    （Game._map_foes：conquest.sortie_foes，含敵方大本營、城鎮沒有兵時退回的控制方巡邏；約戰開著是守軍迎戰挑的那一路），
    輿圖地點卡的對手與勝算跟出陣鈕寫的是同一批人。
    不檢查視野：呼叫端要先用 is_known 把關，沒摸清的地點不能露出敵人，也不該去算勝算。"""
    listed = []
    if squad_ids is not None:
        ids = squad_ids
    else:
        ids = territory.squads_at(world, content, loc.id) if world is not None else loc.enemies
    for squad_id in dict.fromkeys(ids):
        squad = content.squads[squad_id]
        own = squad.faction is not None and squad.faction == faction
        listed.append((squad.name, DRILL if own else odds(squad_id)))
    return listed


def worst_foe(
    content: Content, loc: Location, odds: Odds, faction: str | None = None, world: WorldState | None = None,
) -> tuple[str, str] | None:
    """最難對付的對手與勝算（勝算最差的；一樣差取排在前面的）；沒有敵人、或只有自己陣營的隊伍時為 None。
    不檢查視野：呼叫端要先用 is_known 把關（同 foes）。world 照 foes。"""
    listed = [foe for foe in foes(content, loc, odds, faction, world) if foe[1] != DRILL]
    return max(listed, key=lambda foe: ODDS_ORDER.index(foe[1])) if listed else None


# ── 畫面文字 ──────────────────────────────────────────


def header_text(state: GameState, content: Content) -> str:
    """大地圖頁面上方：目前時間與體力。"""
    return f"⏳ {stamp_text(state.world.time, content, state.world)}　**體力** {int(state.player.stamina)} / {content.config.stamina_max}"


INSIGHT_LABEL = "**意境**　"
HERE_INSIGHTS = "這裡能悟：{names}"  # 詳情欄那一行（W3；待 joy 潤）
TERRAIN_LABEL = "**地利**　"  # 詳情欄地利那一行的標題，字在 terrain.place_line（武學隨地理環境；待 joy 潤）


def insight_names(content: Content, loc: Location) -> list[str]:
    """這個地點探索得到的意境的名字（insights.explore_gives，跟探索同一個判斷）。序章的草廬探索走寫死的四景事件、不抽池子，不列。"""
    if loc.prologue_only:
        return []
    return [content.insights[i].name for i in insights.explore_gives(loc, content)]


def detail_text(state: GameState, content: Content, loc_id: str, odds: Odds) -> str:
    """詳情欄（Markdown）：局勢（含常出沒在此的龍頭人物是誰、現在在做什麼、最近的傳聞）、敵情、劇情、路線。
    未開放的地點只寫「尚未摸清」、連名字都不露，也不算勝算。"""
    loc = content.locations[loc_id]
    if not is_known(state, content, loc_id):
        return f"### ？\n\n{UNKNOWN}"
    here = loc_id == state.player.location and state.player.journey is None  # 在路上時沒有所在地
    parts = [f"### {loc.name}" + ("（所在地）" if here else "") + f"　危險 {'★' * loc.danger}"]

    region = region_of(content, loc_id)
    situation = []
    if region is not None:
        trends = "、".join(f"{name} {value}" for name, value in region_trends(state, content, region))
        situation.append(region.name + (f"（{trends}）" if trends else ""))
    side = territory.controller(state.world, content, loc_id)
    neutral = conquest.on(content, state.world) and conquest.start_kind(state.world, content, loc_id) == conquest.NEUTRAL
    if side is not None:  # 地盤易手（出陣探索與地盤設計 4.3 第 2 點）
        line = territory.CONTROL_LINE.format(side=content.scenario.faction_name(side, side))
        situation.append(line + (conquest.NEUTRAL_HELD if neutral else ""))  # 領地爭奪：被佔下的中立地多寫一句開季是中立地
    elif neutral:
        situation.append(conquest.NEUTRAL_LINE)
    people = haunters(state, content, loc_id)
    standing = [  # 沒有時刻表的季：此刻站在這裡、沒有同名龍頭人物那一段的大勢人物（挑戰每季都有設計 3.8，照地點合併、不照名字）
        fid for fid in figures.present_at(state, content, loc_id) if figures.name_of(content, fid) not in people
    ] if figures.untimed(content, state.world) else []
    if not people and not standing:
        situation.append("沒有龍頭人物在此出沒")
    if situation:
        parts.append("**局勢**　" + "　｜　".join(situation))
    parts += [leader_text(state, content, name, loc_id) for name in people]  # 常出沒的人物併在這裡說明，不另外列名字
    if standing:
        parts.append("\n".join([HERE_TITLE, *(_here_text(state, content, fid) for fid in standing)]))

    listed = foes(content, loc, odds, allied.side_of(state, content), state.world)
    parts.append("**敵情**　" + ("、".join(f"{name} {word}" for name, word in listed) if listed else "沒有人在這裡滋事"))

    gives = insight_names(content, loc)
    if gives:  # 探索在這裡悟不到什麼（比例是 0、序章的草廬）就整行不寫；摸清了才走到這裡，沒摸清的地點上面已經回了
        parts.append(INSIGHT_LABEL + HERE_INSIGHTS.format(names="、".join(gives)))
    lie = terrain.place_line(content, loc_id)
    if lie:  # 地利（武學隨地理環境）：開關關著、這一處沒寫最濃、序章專屬的地方都是空的，整行不寫
        parts.append(TERRAIN_LABEL + lie)

    story: list[str] = []
    if not storyline_off(state, content):  # 第一季不觸發的 beta 主線：玩家看不到它，這一行也不寫（審查 M-3）
        act = current_act(state, content)
        story.append(f"★ 這一幕主線的目標：{act.goal}" if loc_id in act.places else "不是這一幕主線的目標")
    news = recent_news(state, content, loc_id)
    if news:
        story.append(f"✦ 最近 {news_days(content):g} 天的大事與傳聞：\n" + "\n".join(f"- {stamp_text(r.time, content, state.world)}　{r.text}" for r in news))
    elif _in_earshot(state, content, loc_id):
        story.append(f"最近 {news_days(content):g} 天沒有大事或傳聞")
    else:
        story.append(NEWS_FAR)
    parts.append("**劇情**　" + "\n\n".join(story))

    route = way_to(state, content, loc_id)  # 在路上時是改道的走法
    if here:
        way = "你就在這裡"
    elif route is None:
        way = "沒有摸清的路可以過去"
    elif returns_at_once(state, content, route):
        way = "剛出發，折返立刻到"
    else:
        pace, saving = mounts.pace(state, content), mounts.saving(state, content)  # 騎著馬照坐騎寫（5.3）
        way = "、".join(mode_text(content, route.minutes, mode, pace=pace, saving=saving) for mode in MODES)
        way += f"，途經 {_names(content, route.via)}" if route.via else ""
    parts.append("**路線**　" + way)
    return "\n\n".join(parts)
