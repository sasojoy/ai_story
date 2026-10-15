"""江湖輿圖的資料（純資料與文字，不依賴介面框架）：視野、大區歸屬、路程最短的路線與三種走法的時間、體力、
大地圖四個圖層要標的東西、地點詳情與「安排前往」的條件。畫圖在 mapview.py。

全圖開放（Config.open_map，企劃者 2026-10-15）：已開放的地點全部算摸清，沒有視野這件事；摸不摸清只由 location_view 判斷。
開關關著是舊規則：沒摸清（看不見、沒去過、也沒在路上留意地形摸清）的地點在每個圖層都只畫輪廓與「？」，詳情只寫「尚未摸清」。
未開放的地點兩種都完全不畫。
勝算只在呼叫端傳入 odds 函式時才算（敵情層與詳情欄），平常重畫不模擬。
"""
from __future__ import annotations

import heapq
import math
from collections.abc import Callable
from dataclasses import dataclass

from . import allied, figures, insights, mounts, orders, prologue, sortie, territory
from .calendar import point, stamp_text
from .models import Content, Location, MapRegion, SimPlayer, TravelMode
from .rules import (
    audible, ears_of, here_regions, is_revealed, pending_event_title, recent_seconds, resolve_trend, resolve_trends, season_one,
    season_one_off, trend_name, trend_value,
)
from .state import GameState, Order, Rumor, WorldState
from .world import current_act, sim_active, storyline_off

KNOWN = ("current", "visible", "remembered")  # 摸清的地點
LAYERS = {"situation": "局勢", "enemies": "敵情", "story": "劇情", "routes": "路線"}
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


# ── 視野 ──────────────────────────────────────────────


def vision_range(state: GameState, content: Content) -> int:
    cfg, p = content.config, state.player
    bonus = p.stats.get("fame", 0) >= cfg.vision_fame
    return cfg.vision_base + (1 if bonus else 0)


def is_unlocked(loc: Location, state: GameState, content: Content | None = None) -> bool:
    """這個地點開放了沒：世界旗標（unlock_flag），加上序章的草廬只給站在那裡的人（新手引導計畫一）。
    給了 content 時，第一季開著、地點在 season_one_off.unlocks 裡的直接開放（南華觀：舊玉璽鏈關掉之後黃巾伏筆的丹爐灰要拿得到，
    玉璽碎片設計 11.2 第 3 條）。"""
    if loc.prologue_only and state.player.location != loc.id:
        return False
    if content is not None and loc.id in season_one_off(content, state.world, "unlocks"):
        return True
    return not loc.unlock_flag or loc.unlock_flag in state.world.flags


def road_hops(state: GameState, content: Content, limit: int) -> dict[str, int]:
    """從所在地出發、只走已開放的地點，limit 站以內到得了的地點：地點 id → 最少幾站（所在地是 0）。"""
    hops = {state.player.location: 0}
    frontier = [state.player.location]
    for step in range(1, limit + 1):
        nxt = []
        for loc_id in frontier:
            for dest in content.locations[loc_id].connections:
                if dest not in hops and is_unlocked(content.locations[dest], state, content):
                    hops[dest] = step
                    nxt.append(dest)
        frontier = nxt
    return hops


def visible_locations(state: GameState, content: Content) -> set[str]:
    """看得見的地點（舊規則的視野）；全圖開放時沒有視野這件事，是空的（也不必走一遍路）。"""
    if content.config.open_map:
        return set()
    return set(road_hops(state, content, vision_range(state, content)))


def location_view(loc_id: str, state: GameState, content: Content, visible: set[str]) -> str:
    """地點在地圖上的樣子，也是「摸不摸清」唯一的判斷（KNOWN 那三種是摸清）：未開放的 hidden；所在地 current；
    全圖開放（Config.open_map）時其餘已開放的一律 visible（已開放就算知道）；開關關著才照視野、去過、留意地形分。"""
    loc = content.locations[loc_id]
    if not is_unlocked(loc, state, content):
        return "hidden"
    if loc_id == state.player.location and state.player.journey is None:
        return "current"  # 在路上時沒有哪一站是所在地：人在兩站之間（路上設計 3.4，地圖另外畫「你」）
    if content.config.open_map:
        return "visible"
    if loc_id in visible:
        return "visible"
    if loc_id in state.player.visited or loc_id in state.player.surveyed:
        return "remembered"  # 去過，或在路上留意地形摸清了（路上設計第四節）
    return "outline" if loc.important else "dot"


def views(state: GameState, content: Content) -> dict[str, str]:
    """每個地點在地圖上的樣子：current／visible／remembered（摸清）、outline（有名字的未知）、dot、hidden。"""
    visible = visible_locations(state, content)
    return {loc_id: location_view(loc_id, state, content, visible) for loc_id in content.locations}


def known_locations(state: GameState, content: Content) -> set[str]:
    """摸清的地點（location_view）：全圖開放時是所有已開放的地點；舊規則是看得見、去過或在路上留意地形摸清（PlayerState.surveyed）。"""
    return {loc_id for loc_id, view in views(state, content).items() if view in KNOWN}


def is_known(state: GameState, content: Content, loc_id: str) -> bool:
    """這個地點摸清了嗎（location_view；全圖開放時已開放就算）。沒摸清的地點不能洩漏敵人、勝算、路線或名字：
    下面局勢、劇情、敵情的資料函式本身不檢查，呼叫端（圖層、詳情欄）要先用這個把關。"""
    return location_view(loc_id, state, content, visible_locations(state, content)) in KNOWN


def place_choices(state: GameState, content: Content) -> list[tuple[str, str]]:
    """大地圖選得到的地點（顯示文字, 地點 id），依內容順序：摸清的寫名字（所在地另外註明），
    畫出輪廓的未知重要地點寫「名字？」；沒名字的淡點與未開放的地點不列。"""
    out = []
    for loc_id, view in views(state, content).items():
        name = content.locations[loc_id].name
        if view in KNOWN:
            out.append((name + ("（所在地）" if view == "current" else ""), loc_id))
        elif view == "outline":
            out.append((f"{name}？", loc_id))
    return out


# ── 大區 ──────────────────────────────────────────────


def _inside(x: float, y: float, points: list[list[int]]) -> bool:
    """射線法：點是否在多邊形內。"""
    inside = False
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _edge_distance(x: float, y: float, points: list[list[int]]) -> float:
    """點到多邊形邊界的最短距離。"""
    best = math.inf
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        dx, dy = x2 - x1, y2 - y1
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)))
    return best


def region_of(content: Content, loc_id: str) -> MapRegion | None:
    """地點所屬的大區：座標落在哪個大區的多邊形內（依 map.json 的順序取第一個）；
    落在所有大區外時歸給邊界最近的大區（同樣近取排在前面的）。地圖沒有大區時為 None。"""
    regions = content.map.regions
    if not regions:
        return None
    loc = content.locations[loc_id]
    for region in regions:
        if _inside(loc.x, loc.y, region.points):
            return region
    return min(regions, key=lambda region: _edge_distance(loc.x, loc.y, region.points))


def region_locations(content: Content, region_id: str) -> list[str]:
    """屬於這個大區的地點 id（照內容順序；區外的地點歸最近的大區，同 region_of）。"""
    return [
        loc_id for loc_id in content.locations
        if (region := region_of(content, loc_id)) is not None and region.id == region_id
    ]


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
    if point(state.world.time, content, state.world).week < fig.active_from_week:
        text += f"（第 {fig.active_from_week} 週起）"
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
    return f"；{REGEN_NOTE}" if figures.untimed(content, state.world) and content.config.figure_prestige_regen > 0 else ""


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


def _strike_place(state: GameState, content: Content, order: Order) -> str | None:
    """打擊目標此刻的所在（讀人物此刻的樣子，不是發令那一刻的 order.location，他會挪窩）；
    他挑戰不了（figures.can_challenge：不在場、戰線空著……）或所在不在地圖上時是 None。"""
    if not figures.can_challenge(state, content, order.figure):
        return None
    loc_id = figures.state_of(state, content, order.figure).location
    return loc_id if loc_id in content.locations else None


def strike_how(state: GameState, content: Content, order: Order) -> str:
    """軍令卡上打擊那道多寫的一行：怎麼打（到他所在的地方挑戰他本人、打贏記一次），以及他在哪。
    他的所在摸清了才寫地點名字；沒摸清只寫大區（沒有大區的內容就只說沒摸清），不洩漏沒摸清的地點（見 is_known）。
    他眼下挑戰不了（跟挑戰按鈕同一份規則，figures.can_challenge）就直說，不指路。"""
    name = orders.figure_name(content, order.figure)
    loc_id = _strike_place(state, content, order)
    if loc_id is None:
        where = "他眼下沒在戰線上領兵，挑戰不了"
    elif is_known(state, content, loc_id):
        where = f"他現在在{content.locations[loc_id].name}"
    elif (region := region_of(content, loc_id)) is not None:
        where = f"他現在在{region.name}一帶，那裡你還沒摸清"
    else:
        where = "他在哪裡你還沒摸清"
    return f"到{name}所在的地方挑戰他本人，打贏記一次（{where}）。"


SIEGE_NAMED_MAX = 2  # 攻城記得了次數的地點（orders.siege_places）只有這麼幾處時，軍令卡寫出地名（FB-221，PM 2026-10-14）；更多照舊寫「一帶」
SIEGE_AT = "到{where}遊歷，打贏一場{enemy}記一次{note}。"  # 待 joy 潤（FB-221）
SIEGE_UNSEEN = "（那裡你還沒摸清）"  # 待 joy 潤（FB-221）：記得了次數的地方都還沒摸清，只寫大區
SIEGE_SOME_UNSEEN = "（另一處你還沒摸清）"  # 待 joy 潤（FB-221）：兩處裡摸清了一處
SIEGE_AT_SORTIE = "到{where}出陣，打贏一場{enemy}記一次{note}。"  # 待 joy 潤：出陣開著時的攻城（設計第七節）
SIEGE_AREA_SORTIE = "到{front}一帶{enemy}的地盤出陣，打贏一場記一次。"  # 待 joy 潤
INTERCEPT_SORTIE = "到{place}出陣，撞上對面的運糧隊、打贏記一次。"  # 待 joy 潤（FB-248：出陣開著時糧隊只在這一處，orders.intercept_spots）
DEFEND_SORTIE = "在{front}一帶自家的地盤出陣守一回，或按「{duty}」（收在「此地還能做」裡），做一次記一次。"  # 待 joy 潤


def siege_how(state: GameState, content: Content, order: Order) -> str:
    """軍令卡上攻城那道多寫的一行（FB-221）：記得了次數的地點（orders.siege_places：這條戰線上有敵方陣營隊伍的地方）只有一兩處時
    寫出地名（「到官軍大營遊歷，打贏一場官軍記一次。」）——潁川汝南的黃巾只有官軍大營記得到，寫「一帶」會讓人在潁川郊野、長社白打。
    沒摸清的地點同打擊（strike_how）只寫大區（沒有大區寫戰線），不洩漏名字。三處以上、或一處都沒有（舊存檔），照舊寫那條戰線一帶。
    出陣開著時說「出陣」、地點照控制方（設計第七節：攻城認出陣的攻打贏）。"""
    front = trend_name(content, order.front) if order.front else "戰線"
    places = orders.siege_places(content, order.faction, order.front, state.world) if order.front else []
    enemy = content.scenario.faction_name(orders.ENEMY.get(order.faction or "")) or "對面的兵"
    if not places or len(places) > SIEGE_NAMED_MAX:
        if sortie.on(content):
            return SIEGE_AREA_SORTIE.format(front=front, enemy=enemy)
        return f"到{front}一帶遊歷，打贏一場對面的兵記一次。"
    known = [content.locations[loc_id].name for loc_id in places if is_known(state, content, loc_id)]
    hidden: list[str] = []
    for loc_id in places:
        if not is_known(state, content, loc_id):
            region = region_of(content, loc_id)
            area = f"{region.name if region is not None else front}一帶"
            if area not in hidden:
                hidden.append(area)
    note = "" if not hidden else SIEGE_SOME_UNSEEN if known else SIEGE_UNSEEN
    template = SIEGE_AT_SORTIE if sortie.on(content) else SIEGE_AT
    return template.format(where="或".join(known + hidden), enemy=enemy, note=note)


def order_how(state: GameState, content: Content, order: Order) -> str:
    """軍令卡上多寫的一行：這道軍令怎麼出力（FB-093：以前要等做完一次，引薦人的結語才說）。打擊照 strike_how、攻城照 siege_how；
    守城寫陣營自己的守勢行動（巡哨、傳道、保境安民），那一顆收在「此地還能做」裡。截糧、護糧的地點都是軍令本身就寫出來的，不多洩漏。"""
    if order.template == "strike":
        return strike_how(state, content, order)
    if order.template == "siege":
        return siege_how(state, content, order)
    def place(loc_id: str | None) -> str:
        return content.locations[loc_id].name if loc_id in content.locations else "那裡"

    front = trend_name(content, order.front) if order.front else "戰線"
    if order.template == "defend":
        duty = content.orders.duties.get(order.faction)
        name = duty.name if duty else "守勢"
        if sortie.on(content):
            return DEFEND_SORTIE.format(front=front, duty=name)
        return f"在{front}一帶按「{name}」（收在「此地還能做」裡），做一次記一次。"
    if order.template == "intercept":
        if sortie.on(content):
            return INTERCEPT_SORTIE.format(place=place(order.location))
        return f"到{place(order.location)}或附近遊歷，撞上對面的運糧隊、打贏記一次。"
    if order.template == "escort":
        return (f"帶 {content.config.convoy_grain} 份糧草到{place(order.start)}接下糧車，"
                f"送到{place(order.end)}記一次。")
    return ""


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
) -> list[tuple[str, str]]:
    """可能遇到的隊伍與勝算：（隊伍名稱, 勝算），同一隊只列一次。faction 是自己的陣營：自己陣營的隊伍遇上了是
    一起操練、不會輸（engine._drill），寫「操練」不算勝算（試玩回饋 FB-008）。
    world 給了：站的隊伍照控制方（territory.squads_at，地盤易手）；沒給照 loc.enemies。
    不檢查視野：呼叫端要先用 is_known 把關，沒摸清的地點不能露出敵人，也不該去算勝算。"""
    listed = []
    for squad_id in dict.fromkeys(territory.squads_at(world, content, loc.id) if world is not None else loc.enemies):
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


# ── 路線與安排前往 ────────────────────────────────────

# 走法（地圖擴充設計 3.2）：企劃者 2026-10-12 拿掉趕路（「毫無存在的意義」），出發只剩步行、疾行，依序是詳情欄按鈕的順序。
# 趕路還留在 MODE_NAMES、TIME_SHARE 與 TravelMode 裡：拿掉之前以趕路出發、還在路上的那一趟照原本的步調走完，畫面照舊寫得出名字。
MODES: dict[str, str] = {"walk": "步行", "dash": "疾行"}
MODE_NAMES: dict[str, str] = {"walk": "步行", "hurry": "趕路", "dash": "疾行"}  # 寫給玩家看的走法名字（含舊的趕路）
TIME_SHARE: dict[str, float] = {"walk": 1.0, "hurry": 0.5, "dash": 0.0}  # 各花全程的幾成時間


def leg_minutes(content: Content, a: str, b: str) -> float:
    """相鄰兩地 a、b 之間的路程（步行幾分鐘）：地圖上的距離 × 路的種類係數 × 換算比例（地圖擴充設計 3.1）。"""
    cfg = content.config
    start, end = content.locations[a], content.locations[b]
    distance = math.hypot(start.x - end.x, start.y - end.y)
    return distance * cfg.road_factor[start.road_to(b)] * cfg.travel_minutes_per_unit


def whole_minutes(minutes: float) -> int:
    """給玩家看的分鐘數：四捨五入（.5 進位），至少 1 分鐘。"""
    return max(1, math.floor(minutes + 0.5))


def travel_seconds(minutes: float, mode: TravelMode, *, pace: float) -> float:
    """走完 minutes 分鐘的路程要幾秒（遊戲時間）：步行全程、趕路一半、疾行立刻到；再乘 pace（出發時騎的馬，裝備四欄 5.3：
    1＝沒騎馬）。pace 必填、不給預設：漏改的呼叫處直接丟 TypeError，不會悄悄照沒騎馬算。"""
    return minutes * 60 * TIME_SHARE[mode] * pace


def foot_stamina(content: Content, minutes: float, mode: TravelMode) -> int:
    """不騎馬時這種走法出發要扣的體力：步行 0；趕路、疾行照每分鐘路程的點數算，四捨五入（.5 進位）、至少 1 點。"""
    cfg = content.config
    rate = {"walk": 0.0, "hurry": cfg.hurry_stamina_per_minute, "dash": cfg.dash_stamina_per_minute}[mode]
    return 0 if rate <= 0 else max(1, math.floor(minutes * rate + 0.5))


def ride_stamina(foot: int, saving: float) -> int:
    """騎馬省下之後的體力（裝備四欄 5.2，企劃者 2026-10-10 選丙：照比例算、不設保底）：四捨五入（原本的體力 ×（1－腳力）），
    .5 一律進位（mounts.half_up：不用 round，Python 的 round 把 .5 捨到偶數，4.5 會變 4；也補一個浮點誤差，
    30×(1－0.55)＝13.499999999999998 要算 14），剩下的至少 1 點；原本就是 0（步行）照舊 0。
    結伴同行時跟著的人拿帶頭的人的 foot 照自己的腳力算（Game._lead）。"""
    return 0 if foot <= 0 else max(1, mounts.half_up(foot * (1 - saving)))


def travel_stamina(content: Content, minutes: float, mode: TravelMode, *, saving: float) -> int:
    """這種走法出發時一次扣的體力：原本的（foot_stamina）再照腳力省（ride_stamina）。saving 必填（同 travel_seconds 的 pace）。"""
    return ride_stamina(foot_stamina(content, minutes, mode), saving)


def mode_when(minutes: float, mode: TravelMode, *, pace: float) -> str:
    """這種走法要花多久：「約 5 分鐘」「立刻到」；時間乘步調（5.3）。"""
    return "立刻到" if mode == "dash" else f"約 {whole_minutes(minutes * TIME_SHARE[mode] * pace)} 分鐘"


def mode_text(content: Content, minutes: float, mode: TravelMode, *, pace: float, saving: float) -> str:
    """「步行約 9 分鐘」「疾行立刻到・體力 18」：選單與詳情欄用。騎著馬時呼叫端傳步調與腳力（5.3）。"""
    stamina = travel_stamina(content, minutes, mode, saving=saving)
    return MODE_NAMES[mode] + mode_when(minutes, mode, pace=pace) + (f"・體力 {stamina}" if stamina else "")


@dataclass(frozen=True)
class Route:
    path: tuple[str, ...]  # 依序要走的地點，最後一個是目的地（不含所在地）；所在地本身是空的
    legs: tuple[float, ...] = ()  # 每一段的路程（步行分鐘），跟 path 一一對應
    origin: str | None = None  # 從路中間出發（路上設計 3.1）時，第一段那條路的另一頭；None＝從所在地出發
    share: float = 0.0  # 從路中間出發時，origin—path[0] 那條路已經走掉的幾成（legs[0] 只算剩下的）

    @property
    def minutes(self) -> float:
        """全程的路程（步行分鐘）。"""
        return sum(self.legs)

    @property
    def via(self) -> tuple[str, ...]:
        """途經的地點（不含目的地）。"""
        return self.path[:-1]


def shortest_routes(
    state: GameState, content: Content, allowed: set[str] | None = None, start: str | None = None,
) -> dict[str, Route]:
    """從 start（None＝所在地）出發、只走 allowed 裡的地點（None＝所有已開放的地點），到每個地點路程最短（步行分鐘最少）
    的走法（地圖擴充設計 3.2）。一樣近取站數少的，再一樣時比地點 id 的順序，結果固定。"""
    if allowed is None:
        allowed = {loc_id for loc_id, loc in content.locations.items() if is_unlocked(loc, state, content)}
    begin = state.player.location if start is None else start
    best: dict[str, Route] = {}
    heap: list[tuple[float, int, tuple[str, ...], tuple[float, ...], str]] = [(0.0, 0, (), (), begin)]
    while heap:
        minutes, hops, path, legs, here = heapq.heappop(heap)
        if here in best:
            continue
        best[here] = Route(path, legs)
        for dest in content.locations[here].connections:
            dest_id = str(dest)
            if dest_id in allowed and dest_id not in best:
                leg = leg_minutes(content, here, dest_id)
                # 分鐘數取到小數第 6 位再比，免得一樣長的路因為浮點誤差分出先後
                heapq.heappush(heap, (round(minutes + leg, 6), hops + 1, path + (dest_id,), legs + (leg,), dest_id))
    return best


def routes(state: GameState, content: Content) -> dict[str, Route]:
    """從所在地出發、只走摸清且已開放的地點，到每個摸清地點路程最短的走法（取代原本最省體力的路線）。
    全圖開放時摸清的就是所有已開放的地點，等於 shortest_routes 不限地點。"""
    return shortest_routes(state, content, known_locations(state, content))


@dataclass(frozen=True)
class RoadSpot:
    """路上的位置（路上設計第二節）：在 behind 與 ahead 這兩站之間的那條路上，正往 ahead 走。只用這三樣表示，
    不另外存座標。平常 behind 就是 player.location（最後抵達的那一站，設計裡的 P）、ahead 是下一站（N）；
    掉頭之後 behind 是剛才要去的那一站（人正在離開它）。"""

    behind: str  # 身後那一站：正在離開的那一頭
    ahead: str  # 前面那一站：正要走到的那一頭
    done: float  # 從 behind 往 ahead 走了幾成，0～1
    minutes: float  # behind—ahead 這條路整條的路程（步行分鐘）


def road_spot(state: GameState, content: Content) -> RoadSpot | None:
    """在路上的位置；人在某一站（沒在路上）時是 None。走了幾成＝這一段已經走掉的時間 ÷ 這一段的時間；
    改道出發的第一段只走那條路剩下的部分（Journey.origin、share）。"""
    j = state.player.journey
    if j is None or j.reached >= len(j.path):
        return None
    ahead = j.path[j.reached]
    first = j.reached == 0 and j.origin is not None
    behind = j.origin if first else state.player.location
    share = j.share if first else 0.0
    minutes = leg_minutes(content, behind, ahead)
    span = travel_seconds(minutes * (1 - share), j.mode, pace=j.pace)  # 這一段這一趟要走幾秒：照出發時快照的步調（5.3），跟排好的抵達時刻同一個數
    left = j.arrive_at[j.reached] - state.world.time
    walked = 1.0 if span <= 0 else min(1.0, max(0.0, 1 - left / span))
    return RoadSpot(behind, ahead, share + (1 - share) * walked, minutes)


def way_to(state: GameState, content: Content, loc_id: str) -> Route | None:
    """從現在的位置到 loc_id 路程最短的走法；走不到時是 None。人在某一站時就是 routes 的那一條（所在地本身是 None）。
    在路上時（路上設計 3.1）比兩種走法、取路程短的（一樣近時繼續往前）：繼續走完這一段到前面那一站再接著走，
    或掉頭先回身後那一站再接著走。第一段是半段路、路的種類照原本那一條；身後那一站本身也到得了（就是折返）。"""
    spot = road_spot(state, content)
    if spot is None:
        route = routes(state, content).get(loc_id)
        return route if route is not None and route.path else None
    known = known_locations(state, content)
    best: Route | None = None
    for end, other, part in ((spot.ahead, spot.behind, 1 - spot.done), (spot.behind, spot.ahead, spot.done)):
        onward = shortest_routes(state, content, known, start=end).get(loc_id)
        if onward is None:
            continue
        way = Route((end, *onward.path), (spot.minutes * part, *onward.legs), origin=other, share=1 - part)
        if best is None or round(way.minutes, 6) < round(best.minutes, 6):
            best = way
    return best


RETURN_AT_ONCE_MINUTES = 0.5  # 剛出發就折返：回程不到這麼多分鐘路程（趕路的體力四捨五入正好是 0）


def returns_at_once(state: GameState, content: Content, route: Route) -> bool:
    """這條路是不是「剛出發就折返」（FB-025）：在路上、只回到自己最後待過的那一站、回程不到 RETURN_AT_ONCE_MINUTES
    分鐘路程。是的話哪種走法都不扣體力、當下就回到原地（路上裁決：剛出發就折返，立刻回原地、不花體力）。
    掉頭後馬上又掉頭時，身後那一站是剛才要去的那一站、不是自己待過的，不算——不然走到快到時連掉兩次頭就能白白抵達。"""
    spot = road_spot(state, content)
    return (
        spot is not None and spot.behind == state.player.location and tuple(route.path) == (spot.behind,)
        and route.minutes < RETURN_AT_ONCE_MINUTES
    )


def route_stamina(state: GameState, content: Content, route: Route, mode: TravelMode) -> int:
    """照這條路、這種走法出發要扣的體力（騎著馬照腳力省，mounts.saving，裝備四欄 5.2）；剛出發就折返不扣（見 returns_at_once）。
    選單、輿圖的鈕、輿圖的拒絕話與 Game._depart 實際扣的都走這裡。"""
    if returns_at_once(state, content, route):
        return 0
    return travel_stamina(content, route.minutes, mode, saving=mounts.saving(state, content))


def route_foot_stamina(state: GameState, content: Content, route: Route, mode: TravelMode) -> int:
    """同 route_stamina，但不算坐騎：結伴同行時交給跟著的人，各自照自己的坐騎再省（Game._lead，裝備四欄 5.8）。"""
    return 0 if returns_at_once(state, content, route) else foot_stamina(content, route.minutes, mode)


def route_text(state: GameState, content: Content, route: Route, mode: TravelMode) -> str:
    """選單「前往／折返」括號裡的字（見 mode_text，步調與腳力照身上那匹）；剛出發就折返是「立刻到」。"""
    if returns_at_once(state, content, route):
        return "立刻到"
    return mode_text(content, route.minutes, mode, pace=mounts.pace(state, content), saving=mounts.saving(state, content))


@dataclass(frozen=True)
class TravelOption:
    """詳情欄底下的一個「安排前往」按鈕。"""

    mode: TravelMode
    label: str
    enabled: bool
    to_jianghu: bool = False  # 按不下去是因為江湖頁上有事沒了結（事件、交談、求見、投靠、叛投、答話）：頁面多給一顆「回江湖」（FB-063）


@dataclass(frozen=True)
class TravelBlock:
    """現在不能安排前往的原因（話只在 travel_block 寫一次）。to_jianghu：要回江湖頁了結才解得開（待處理的事件、交談中、
    求見中、投靠或叛投待確認、答話中；FB-063），頁面照這個旗標多給「回江湖」，不去解析中文。閉關、賽季結束不是。"""

    reason: str
    to_jianghu: bool = False


def travel_block(state: GameState, content: Content) -> TravelBlock | None:
    """現在不能安排前往的原因（賽季已結束、有事件待處理、交談中、求見中、投靠或叛投待確認、閉關中）；可以時為 None。
    有事件待處理時寫出是哪一則、去哪裡了結（FB-063）：多段的事件（next_event）是現在待處理的那一段。
    在路上不擋：從路上改去別處（路上設計 3.1，見 way_to）。"""
    if state.world.ended:
        return TravelBlock("賽季已結束，不能安排前往")
    if not prologue.can_travel(state, content):
        return TravelBlock("師父的話還沒說完，先別急著走")
    if state.pending_event:
        title = pending_event_title(state, content)  # 找不到事件（存檔指著拿掉的事件）時退回「眼前的事」
        what = f"「{title}」" if title is not None else "眼前的事"
        return TravelBlock(f"先回江湖頁處理{what}", to_jianghu=True)
    p = state.player
    if p.duel is not None:  # 單人頭目戰打到一半（tianxia/duel.py）
        return TravelBlock("正跟人交手，先分出勝負或抽身退走", to_jianghu=True)
    if p.arena is not None:  # 擂台打到一半（tianxia/arena.py）
        return TravelBlock("正在擂台上，先分出勝負或認輸下台", to_jianghu=True)
    if p.picking_arena:
        return TravelBlock("還在擂台邊，先返回才能安排前往", to_jianghu=True)
    if p.pending_companion:
        return TravelBlock("交談中，先告辭才能安排前往", to_jianghu=True)
    if p.picking_audience:
        return TravelBlock("求見中，先返回才能安排前往", to_jianghu=True)
    if p.picking_bounty:
        return TravelBlock("懸賞榜還開著，先離開才能安排前往", to_jianghu=True)
    if p.picking_smith:
        return TravelBlock("鐵匠鋪還開著，先離開才能安排前往", to_jianghu=True)
    if p.picking_market:
        return TravelBlock(mounts.TRAVEL_BLOCKED, to_jianghu=True)  # 待 joy 潤的字在 mounts（atlas 為了騎馬的步調與省體力 import mounts，這句就近讀它）
    if p.picking_donate:  # 大本營的捐軍備（素材與經濟設計第六節）；待 joy 潤
        return TravelBlock("還在軍需官帳前，先離開才能安排前往", to_jianghu=True)
    if p.pending_faction:
        return TravelBlock("投靠還沒決定，先決定再安排前往", to_jianghu=True)
    if allied.needs_ally(state, content):  # 拜入之後還沒挑依附哪一邊（豪強分屬兩軍）
        return TravelBlock(allied.ALLY_FIRST, to_jianghu=True)
    if p.pending_defect:
        return TravelBlock("叛投還沒決定，先決定再安排前往", to_jianghu=True)
    if p.fs_asking is not None:
        return TravelBlock("正在答話，先作罷才能安排前往", to_jianghu=True)
    if p.tagalong is not None and p.journey is not None:  # 結伴同行：路線由帶頭的人定（玩家互動第二層）
        return TravelBlock(f"跟著{p.tagalong.leader}同行，要改道先分道揚鑣", to_jianghu=True)
    if p.busy_until is not None:
        return TravelBlock("閉關中，不能安排前往")
    return None


def travel_refusal(state: GameState, content: Content, loc_id: str, mode: TravelMode) -> str | None:
    """用這種走法安排前往這裡，不行的原因；可以時為 None。在路上時照改道的走法算（見 way_to）。"""
    route = way_to(state, content, loc_id)
    if route is None:
        return "無法安排前往這裡"
    block = travel_block(state, content)
    if block:
        return block.reason
    cost = route_stamina(state, content, route, mode)
    if state.player.stamina < cost:
        return f"體力不足，{MODE_NAMES[mode]}要 {cost} 體力"
    return None


def travel_options(state: GameState, content: Content, loc_id: str) -> list[TravelOption] | None:
    """詳情欄底下的按鈕：步行、疾行各一個，寫時間與體力，體力不夠的按不下去（地圖擴充設計 3.2）。
    所在地、沒摸清或未開放的地點不顯示按鈕（None）；現在不能安排前往時只有一個按不下去的按鈕，寫原因。
    在路上時照改道的走法算時間與體力（見 way_to），剛離開的那一站也有按鈕（就是折返）。"""
    route = way_to(state, content, loc_id)
    if route is None:
        return None
    block = travel_block(state, content)
    if block:
        return [TravelOption("walk", block.reason, False, to_jianghu=block.to_jianghu)]
    out: list[TravelOption] = []
    at_once = returns_at_once(state, content, route)
    pace = mounts.pace(state, content)  # 騎著馬步行比較快（5.3）
    for mode in MODES:
        cost = route_stamina(state, content, route, mode)
        if state.player.stamina < cost:
            out.append(TravelOption(mode, f"{MODES[mode]}（體力不足，要 {cost}）", False))
        else:
            price = f"・體力 {cost}" if cost else ""
            when = "立刻到" if at_once else mode_when(route.minutes, mode, pace=pace)
            out.append(TravelOption(mode, f"{MODES[mode]}（{when}{price}）", True))
    return out


def journey_title(content: Content, path) -> str:
    """江湖紀錄裡一趟路的標題：「前往 終點」，途經別的站時加上「（途經 A、B）」。"""
    title = f"前往 {content.locations[path[-1]].name}"
    return f"{title}（途經 {_names(content, path[:-1])}）" if len(path) > 1 else title


def path_legs(content: Content, start: str, path: list[str]) -> list[float]:
    """從 start 照 path 一站一站走，每一段的路程（步行分鐘）。"""
    stops = [start, *path]
    return [leg_minutes(content, a, b) for a, b in zip(stops, stops[1:])]


def arrival_times(now: float, legs: list[float], mode: TravelMode, *, pace: float) -> list[float]:
    """now 出發、照這種走法與步調（出發時騎的馬，5.3），每一站的抵達時間（遊戲秒）；疾行全都是 now。"""
    times: list[float] = []
    t = now
    for leg in legs:
        t += travel_seconds(leg, mode, pace=pace)
        times.append(t)
    return times


# ── 畫面文字 ──────────────────────────────────────────


def header_text(state: GameState, content: Content) -> str:
    """大地圖頁面上方：目前時間與體力。"""
    return f"⏳ {stamp_text(state.world.time, content, state.world)}　**體力** {int(state.player.stamina)} / {content.config.stamina_max}"


def _names(content: Content, loc_ids) -> str:
    return "、".join(content.locations[loc_id].name for loc_id in loc_ids)


INSIGHT_LABEL = "**意境**　"
HERE_INSIGHTS = "這裡能悟：{names}"  # 詳情欄那一行（W3；待 joy 潤）


def insight_names(content: Content, loc: Location) -> list[str]:
    """這個地點探索得到的意境的名字（insights.explore_gives，跟探索同一個判斷）。序章的草廬探索走寫死的四景事件、不抽池子，不列。"""
    if loc.prologue_only:
        return []
    return [content.insights[i].name for i in insights.explore_gives(loc, content)]


def detail_text(state: GameState, content: Content, loc_id: str, odds: Odds) -> str:
    """詳情欄（Markdown）：局勢（含常出沒在此的龍頭人物是誰、現在在做什麼、最近的傳聞）、敵情、劇情、路線。
    沒摸清的地點只寫「尚未摸清」，也不算勝算。"""
    loc = content.locations[loc_id]
    if not is_known(state, content, loc_id):
        # 只有畫出輪廓的未知重要地點才有名字；淡點與未開放的地點連名字都不能露
        outlined = views(state, content)[loc_id] == "outline"
        return f"### {loc.name if outlined else ''}？\n\n{UNKNOWN}"
    here = loc_id == state.player.location and state.player.journey is None  # 在路上時沒有所在地
    parts = [f"### {loc.name}" + ("（所在地）" if here else "") + f"　危險 {'★' * loc.danger}"]

    region = region_of(content, loc_id)
    situation = []
    if region is not None:
        trends = "、".join(f"{name} {value}" for name, value in region_trends(state, content, region))
        situation.append(region.name + (f"（{trends}）" if trends else ""))
    side = territory.controller(state.world, content, loc_id)
    if side is not None:  # 地盤易手（出陣探索與地盤設計 4.3 第 2 點）
        situation.append(territory.CONTROL_LINE.format(side=content.scenario.faction_name(side, side)))
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
