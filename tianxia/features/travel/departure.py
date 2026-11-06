"""出發與抵達的補算、在路上那一行字（功能包 tianxia/features/travel/；原本是 Game._depart、_arrivals、_arrive、_journey_line，全部拆包第 48 批）。
ctx 是 Game（第一階）。sync、advance 每次都補算抵達（ctx._arrivals）：迴圈中途的 _ambush_check → arrive → 騎乘飽足 → 路上見聞，先後算行為，一個都不動。
抵達是事件 arrive 的發布點（ctx.publish，訂閱者先後由 core/features.py 的 BUS_ORDER 定）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import atlas  # 共用規則層（輿圖：路程、走法、抵達時刻；第 50 批收進）
from tianxia.core import bounty_base
from tianxia import equipment, journal, mounts, precise
from tianxia.core import features as features_core
from tianxia.journal import Draft
from tianxia.models import TravelMode
from tianxia.state import Journey
from tianxia.world import check_thresholds

from . import party as travel_party
from . import road_actions

if TYPE_CHECKING:
    from tianxia.engine import Game


def depart(ctx: Game, route: atlas.Route, mode: TravelMode, pace: float | None = None) -> list[str]:
    """出發（地圖擴充設計 3.2、3.3）：趕路、疾行的體力出發時一次扣，照走法排好每一站的抵達時間。
    疾行立刻一站一站抵達；步行、趕路就在路上，之後由 sync／advance 補算抵達（見 arrivals）。
    在路上改道、折返（路上設計 3.1）也從這裡出發：route 的第一段是半段路（origin、share 記著是哪條路、走掉幾成），
    新路程整個取代原本那一趟；原本已經扣的趕路體力不退。剛出發就折返（見 atlas.returns_at_once）不扣體力、當下就回到原地。
    騎著馬的體力與步調照出發這一刻的坐騎（裝備四欄 5.3）。"""
    s, c = ctx.state, ctx.content
    bounty_base.close_board(s.player)  # 動身了：城鎮的第二層選單（懸賞榜、鐵匠鋪）收起來，不留在路上
    s.player.parley_escort = None  # NPC 智能 2.1：自己動身就不是誰帶的路了（帶路那一支出發之後再寫回去）
    equipment.close_smith(s.player)  # 鐵匠鋪連同打造到一半的單子、停在哪一頁一起收
    mounts.close_market(s.player)  # 馬市也收起來（裝備四欄 5.5）
    # （picking_donate、picking_dadian：全部拆包第 43 批換成銀兩出口包的店面登記，下面 close_shops 收）
    features_core.close_shops(ctx)  # 搬成包的店也收起來（店面登記，第 11 批；酒肆、擂台〔全部拆包第 12 批〕）
    rerouting = s.player.journey is not None
    start = None if rerouting else s.player.location
    parted = travel_party.part_ways(ctx) if s.player.tagalong is not None and not rerouting else []  # 答應了結伴卻自己先走：散了
    minutes = route.minutes
    at_once = atlas.returns_at_once(s, c, route)  # 要在換掉原本那一趟之前看：它看的是現在在路上的位置
    pace = mounts.pace(s, c) if pace is None else pace  # 出發這一刻的步調（大勢人物帶路照他的腳程，parley）（裝備四欄 5.3）：寫進 Journey、排抵達時刻、紀錄的標籤都用這一個數；路上餓了、換了馬都不回頭改
    cost = atlas.route_stamina(s, c, route, mode)
    foot = atlas.route_foot_stamina(s, c, route, mode)  # 不算坐騎的那一份：結伴同行時跟著的人照自己的坐騎再省（lead，5.8）
    s.player.stamina -= cost
    legs = [0.0] if at_once else list(route.legs)
    s.player.journey = Journey(
        mode=mode, path=list(route.path), arrive_at=atlas.arrival_times(s.world.time, legs, mode, pace=pace),
        origin=route.origin, share=route.share, pace=pace,
    )
    if ctx._draft is not None:
        ctx._draft.tag = "立刻折返" if at_once else atlas.MODE_NAMES[mode] + atlas.mode_when(minutes, mode, pace=pace)
        if cost:
            ctx._draft.changes.append(f"體力 -{cost}")
    verb = "改道" if rerouting else "動身"
    told = f"{s.player.name}{verb}{atlas.MODE_NAMES[mode]}前往{c.locations[route.path[-1]].name}，你跟著走。"
    party = parted + travel_party.lead(ctx, start, foot, told)  # 結伴同行：跟著的人照抄這一趟（玩家互動第二層），體力各付各的
    if mode == "dash" or at_once:
        return party + ctx._arrivals()
    left = ctx._real_minutes(s.player.journey.arrive_at[-1] - s.world.time)
    msg = f"你{verb}{atlas.MODE_NAMES[mode]}前往{c.locations[route.path[-1]].name}，現實約 {left} 分鐘後抵達。"  # 只寫現實的倒數（FB-062）
    ctx._hide(msg)  # 場景會顯示「在路上」，紀錄只留標題與走法
    ctx._sync_battle_presence()
    return [msg] + party


def arrivals(ctx: Game) -> list[str]:
    """在路上：抵達時間已經到了的站，一站一站抵達（地圖擴充設計 3.3）。走到這一趟的最後一站（終點或喊停的
    那一站）就下馬。賽季已經落幕時，落幕前就該到的站照樣抵達（時鐘停在落幕那一刻，之後的站不會再到），
    然後停在當下那一站；抵達某一站時觸發了賽季落幕，就停在那一站。不在行動裡（sync、advance）時自己寫
    江湖紀錄（見 journal.add_arrival），而且不叫模型——它們在計時器裡、拿著全服行動鎖；疾行在
    travel() 的行動裡，寫在那次行動的紀錄，照原本的規則可以叫模型。"""
    s, c = ctx.state, ctx.content
    j = s.player.journey
    if j is None or (j.arrive_at[j.reached] > s.world.time and not s.world.ended):
        return []
    own = ctx._draft is None
    if own:
        ctx._draft = Draft(atlas.journey_title(c, j.path))
    try:
        already_over = s.world.ended
        msgs: list[str] = []
        when = s.world.time
        while j.reached <= j.last and j.arrive_at[j.reached] <= s.world.time:
            if s.world.ended and not already_over:
                break  # 剛抵達的那一站觸發了賽季落幕：停在那裡
            when = j.arrive_at[j.reached]
            stop = j.path[j.reached]
            came_from = j.origin if j.reached == 0 and j.origin is not None else s.player.location
            j.reached += 1
            # 到了另一站：換段，路上小事重新可做，也可能看見路上見聞。掉頭回到剛離開的那一站不算換段、也不擲見聞
            # （剛出發就折返不花時間也不花體力，不能拿來刷見聞）
            new_leg = stop != s.player.location
            if new_leg:
                s.player.leg_actions = set()
                msgs += ctx._ambush_check(came_from, stop, when)  # 設伏劫道：這一段路上有沒有埋伏（字典查一次，疾行也算）
            msgs += arrive(ctx, stop)
            if new_leg:
                msgs += mounts.hunger(s, c, j.mode)  # 騎著馬走完一段（裝備四欄 5.4）：扣飽足度，第一次低到 30 以下提醒一次；掉頭回原地不扣
            if new_leg and not c.locations[came_from].prologue_only:  # 出師那段路不抽路上見聞
                msgs += road_actions.sight(ctx, c.locations[came_from].road_to(stop), stop, when)
        done = j.reached > j.last or s.world.ended
        if done:
            s.player.journey = None
            if s.player.tagalong is not None:  # 結伴同行到這一趟的最後一站就散了（玩家互動第二層）
                msgs.append(f"一路同行到此，你與{s.player.tagalong.leader}拱手作別。")
                s.player.tagalong = None
            if s.player.location != j.path[-1]:
                reason = "賽季落幕" if s.world.ended else "喊停"
                ctx._draft.tag = f"{reason}，停在 {c.locations[s.player.location].name}"
        if own:
            entry = ctx._draft.entry(when, msgs)
            if done or entry.lines or entry.changes or entry.guide:  # 只到了中途的站、又沒有別的事（連引導也沒有），不另寫一則
                journal.add_arrival(s, entry, done)
    finally:
        if own:
            ctx._draft = None
    ctx._sync_battle_presence()
    return msgs


def arrive(ctx: Game, loc_id: str) -> list[str]:
    """抵達一站：照原本走到一個地點的規則——地點描寫、新手引導、大勢門檻。鎖內一個模型都不叫：江湖大事的潤色記成單子、
    放鎖之後才請（S-09，見 _flavor_sink）。以前重遊的終點還在鎖內請模型補一句點綴，那句只進 GameState.log、
    畫面上看不到，卻佔著全服的行動鎖（2026-10-12 拿掉，見 _present）。"""
    s, c = ctx.state, ctx.content
    before = s.player.tutorial_step
    s.player.location = loc_id
    s.player.visited.add(loc_id)
    text = ctx.location_text()
    ctx._hide(text)
    # 糧車到了終點（路過也算）先交糧，再照原本的新手引導與門檻（計畫 T6）；呼叫的先後不能換
    convoy = ctx.publish("arrive", loc_id)  # 事件 arrive（第 26 批）：軍情包交糧車→懸賞榜的護送（走到終點就交差，路過也算）
    guide = ctx._guide(ctx._note_action("move"))  # 出師的盤纏（序章步驟的獎勵）是這一趟路的結果，回在這裡
    if not precise.is_town(c, c.locations[loc_id]):  # 走到城外（初入江湖逛鋪子那一步：沒進鋪子、直接出城也算過，Joy 2026-10-22）
        guide += ctx._guide(ctx._note_action("leave_town"))
    thresholds = check_thresholds(s, c, ctx.world, ctx._flavor_sink(), now=ctx.now)
    t = c.tutorial
    left = [t.leave_text] if t.location is not None and before < t.prologue_steps <= s.player.tutorial_step and t.leave_text else []
    # 出師、抵達起點：「剛剛」先接一句草廬已經看不見了（新手引導設計 10.3），再寫盤纏（T7 審查 M4）
    return [text] + convoy + left + guide + thresholds


def journey_line(ctx: Game) -> str:
    """在路上的那一句（狀態列）：「往寶洞（步行），現實約 8 分鐘後抵達；下一站湖邊」。
    只寫現實的倒數，不寫抵達的季曆時刻（FB-062）：季曆跑得比現實快，「第 8 週・週五 12:19 抵達」配上「還要約 1 分鐘」
    兩種時間混在一行，玩家算不出來；季曆時刻已經在狀態列上一行。"""
    s, c = ctx.state, ctx.content
    j = s.player.journey
    left = ctx._real_minutes(j.arrive_at[j.last] - s.world.time)
    line = f"往{c.locations[j.path[j.last]].name}（{atlas.MODE_NAMES[j.mode]}），現實約 {left} 分鐘後抵達"
    if j.reached < j.last:
        line += f"；下一站{c.locations[j.path[j.reached]].name}"
    return line
