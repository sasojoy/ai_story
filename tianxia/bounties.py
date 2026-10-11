"""懸賞榜（PM 2026-10-08 派工「加強散人玩法」；Config.bounties）。

- 官軍、黃巾每週一 00:00（季曆；第一季走 world.WEEK_HOOKS、規則關著的季走 tick，都叫 issue）各自動掛討伐兩張、打探、護送各一張（Config.bounties.kinds）：討伐是到指定的地方遊歷、
  打贏一場對頭陣營的隊伍；打探是到指定的地方探索一次；護送是在起點的城鎮接下、走到終點的城鎮。掛 auto_weeks 週，過期的下榜。
- 投靠了陣營的人可以在玩家卡上花銀兩通緝一個敵對陣營的人（押金就是賞金）；接了通緝的人在卡上對他「截殺」，照截殺的規則打，
  打贏就完成。沒人完成就在 post_weeks 週後下榜，押金在掛單的人下次同步時退回（deliver_refunds）。
- 散人兩邊的都能接，陣營的人只能接自己陣營的（can_take）；接了才算，一個人同時最多接 max_taken 張。
  前 quota 個完成的人各拿一份：銀兩（遊俠名號到第 4 階的散人另有加成）與經驗，散人另記俠名（ranger.add_deeds）。

每季都有（企劃者 2026-10-10「整個懸賞榜每季都有」，懸賞榜設計 2.2）：只看 Config.bounties.enabled 與劇本有沒有陣營（active），
不看第一季開關；關著時每個函式都什麼都不做、回空的。
只改 GameState（玩家與共用的季）；不 import engine、world（world 會 import 這裡，掛 WEEK_HOOKS）。"""
from __future__ import annotations

import math
import random

from . import calendar, ranger, roster, team
from .characters import name_key
from .models import Content, Location
from .state import Bounty, GameState, WorldState
from .world_state import WorldStateStore, season_length_days

KIND_NAMES = {"strike": "討伐", "scout": "打探", "escort": "護送", "wanted": "通緝"}
ENEMY = {"guan": "huang", "huang": "guan"}  # 自動掛單的兩個陣營與他們的對頭（同軍令）
BOARD = "懸賞榜"
SEASON_END = "到季末"  # 待 joy 潤：期限到季末或過了季末時寫這個（due_text）
LAPSED_FULL = "【懸賞】「{title}」名額被別人交滿了，你手上這一張作廢。"  # 待 joy 潤（FB-121 第 5 件，deliver_lapses）
LAPSED_DUE = "【懸賞】「{title}」過了期限，你手上這一張作廢。"  # 待 joy 潤


def active(state: GameState, content: Content) -> bool:
    """懸賞榜開著：設定開著（Config.bounties.enabled）、劇本有陣營（沒有陣營就沒有人掛單）。不看第一季開關（懸賞榜設計 2.2）。"""
    return content.config.bounties.enabled and bool(content.scenario.factions)


def is_town(content: Content, loc_id: str) -> bool:
    loc = content.locations[loc_id]
    return content.config.explore_mix_of(loc.tags).kind == "town"


def board_here(state: GameState, content: Content) -> bool:
    """這裡看得到懸賞榜：懸賞榜開著（active）、人在城鎮類的地點。"""
    return active(state, content) and is_town(content, state.player.location)


def week_seconds(state: GameState, content: Content) -> float:
    return calendar.WEEK / calendar.cal_scale(content, state.world)


def quota(content: Content) -> int:
    cfg = content.config
    return max(cfg.bounties.quota_min, math.ceil(cfg.bounties.quota_base * cfg.server_max_players / 100))


def _loc_name(content: Content, loc_id: str | None) -> str:
    return content.locations[loc_id].name if loc_id in content.locations else ""


def title(content: Content, b: Bounty) -> str:
    """短標題：「討伐・黃巾游騎（南陽郊野）」「打探・嵩山深處」「護送・新野→宛城」「通緝・某某」。"""
    kind = KIND_NAMES.get(b.kind, b.kind)
    if b.kind == "strike":
        return f"{kind}・{_loc_name(content, b.location)}的{_enemy_name(content, b)}"
    if b.kind == "escort":
        return f"{kind}・{_loc_name(content, b.location)}→{_loc_name(content, b.end)}"
    if b.kind == "wanted":
        return f"{kind}・{b.target}"
    return f"{kind}・{_loc_name(content, b.location)}"


def how(content: Content, b: Bounty) -> str:
    """怎麼完成（一句）。"""
    if b.kind == "strike":
        return f"到{_loc_name(content, b.location)}遊歷，打贏一場{_enemy_name(content, b)}的隊伍"
    if b.kind == "scout":
        return f"到{_loc_name(content, b.location)}探索一次"
    if b.kind == "escort":
        return f"在{_loc_name(content, b.location)}接下，走到{_loc_name(content, b.end)}"
    return f"找到{b.target}，在他的玩家卡上截殺並打贏他"


def _enemy_name(content: Content, b: Bounty) -> str:
    return content.scenario.faction_name(ENEMY.get(b.faction or "")) or "敵軍"


def issuer(content: Content, b: Bounty) -> str:
    return content.scenario.faction_name(b.faction) or "江湖"


def _left(b: Bounty) -> int:
    return b.quota - len(b.done_by)


def due_text(b: Bounty, content: Content, world: WorldState) -> str:
    """給玩家看的期限（懸賞榜設計 3.5）：第一季寫「第 5 週・週一 00:00」、規則關著寫「第11天 12:00」（calendar.stamp_text，跟 Game.stamp
    同一個寫法；這裡不能 import engine）。到季末或過了季末一律寫「到季末」：規則關著時 stamp_text 不會夾，14 天的季第 11、12 週掛的單
    會寫成這一季沒有的「第15天 00:00」「第16天 04:00」。真正的 expires 不夾：收季時懸賞榜跟著 WorldState 整個重來。"""
    if b.expires >= season_length_days(world, content) * calendar.DAY - calendar.EPS_SECONDS:
        return SEASON_END
    return calendar.stamp_text(b.expires, content, world)


def due_line(state: GameState, content: Content, b: Bounty) -> str:
    """「期限 第11天 12:00・名額還剩 2」：懸賞榜每一行、懸賞卡每一列、揭下的回話都寫它（FB-121 第 5 件）。待 joy 潤：寫法。"""
    return f"期限 {due_text(b, content, state.world)}・名額還剩 {_left(b)}"


def open_bounties(state: GameState, content: Content) -> list[Bounty]:
    """榜上還有效的（沒過期、還有名額）。截殺關著（Config.raid.enabled）時通緝不算：只能靠截殺交差，揭了也交不了
    （mine、take、hunting、status、整季機器人與假人都經過這裡，自然看不到、揭不了、不佔格）；押金照期限退（deliver_refunds 直接掃榜）。"""
    if not active(state, content):
        return []
    now, raids = state.world.time, content.config.raid.enabled
    return [b for b in state.world.bounties if b.expires > now and _left(b) > 0 and (raids or b.kind != "wanted")]


def can_take(state: GameState, b: Bounty) -> bool:
    """這個人接不接得了這一種：散人兩邊都能接；陣營的人只能接自己陣營的；通緝不能接自己的。"""
    p = state.player
    if b.kind == "wanted" and name_key(b.target or "") == name_key(p.name):
        return False
    if b.poster is not None and name_key(b.poster) == name_key(p.name):
        return False
    return p.faction is None or p.faction == b.faction


def mine(state: GameState, content: Content) -> list[Bounty]:
    """我接了、還沒完成、還有效的；接了之後換了陣營、接不了的不算。"""
    name = name_key(state.player.name)
    return [
        b for b in open_bounties(state, content)
        if name in (name_key(t) for t in b.takers) and can_take(state, b)
    ]


def visible(state: GameState, content: Content) -> list[Bounty]:
    """這個人在懸賞榜上看得到的（FB-121 第 3 件）：手上揭了的，加上接得了（can_take）、自己還沒交過的。「懸賞榜（N 張）」的 N
    只算這些（0 張不畫那顆鈕：打開只有「返回」就是 FB 抱怨的事），榜上列的也是這些，所以 N 等於打開之後列出的張數。
    不查武學與兵器，所以不收 world。"""
    me = name_key(state.player.name)
    held = {b.id for b in mine(state, content)}
    return [
        b for b in open_bounties(state, content)
        if b.id in held or (can_take(state, b) and me not in (name_key(t) for t in b.done_by))
    ]


def take_problem(state: GameState, content: Content, b: Bounty) -> str | None:
    """「接下」按不按得下去（拒絕的話）。"""
    p = state.player
    name = name_key(p.name)
    if name in (name_key(t) for t in b.done_by):
        return "這一張你已經交過差了。"
    if not can_take(state, b):
        return "這一張不是給你接的。"
    if len(mine(state, content)) >= content.config.bounties.max_taken:
        return f"你手上已經有 {content.config.bounties.max_taken} 張了，先交了差再說。"
    if b.kind == "escort" and p.location != b.location:
        return f"要在{_loc_name(content, b.location)}接。"
    return None


def reward_text(state: GameState, content: Content, b: Bounty) -> str:
    silver = _silver(state, content, b)
    deeds = b.deeds if ranger.active(state, content) else 0
    exp = _exp(state, content, b)
    return f"賞銀 {silver}" + (f"・經驗 {exp}" if exp else "") + (f"・俠名 +{deeds}" if deeds else "")


def _share(state: GameState, content: Content, b: Bounty) -> float:
    """陣營的人做自己陣營掛的懸賞只拿 faction_share；通緝的賞金是押金，照數給。"""
    if b.kind == "wanted" or state.player.faction is None:
        return 1.0
    return content.config.bounties.faction_share


def _silver(state: GameState, content: Content, b: Bounty) -> int:
    if b.kind == "wanted":
        return b.silver
    return round(b.silver * ranger.bounty_factor(state, content) * _share(state, content, b))


def _exp(state: GameState, content: Content, b: Bounty) -> int:
    return round(content.config.bounties.exp.get(b.kind, 0) * _share(state, content, b))


def take(state: GameState, content: Content, bounty_id: str) -> list[str]:
    b = next((x for x in open_bounties(state, content) if x.id == bounty_id), None)
    if b is None:
        return ["這張懸賞已經揭下了。"]
    problem = take_problem(state, content, b)
    if problem is not None:
        return [problem]
    if name_key(state.player.name) not in (name_key(t) for t in b.takers):
        b.takers.append(state.player.name)
    return [f"你揭下了「{title(content, b)}」：{how(content, b)}。（{reward_text(state, content, b)}；{due_line(state, content, b)}）"]


def drop(state: GameState, content: Content, bounty_id: str) -> list[str]:
    name = name_key(state.player.name)
    for b in state.world.bounties:
        if b.id == bounty_id and name in (name_key(t) for t in b.takers):
            b.takers = [t for t in b.takers if name_key(t) != name]
            return [f"你把「{title(content, b)}」放回了榜上。"]
    return ["你手上沒有這一張。"]


def _complete(state: GameState, content: Content, world: WorldStateStore, b: Bounty) -> list[str]:
    p = state.player
    name = name_key(p.name)
    b.takers = [t for t in b.takers if name_key(t) != name]
    b.done_by.append(p.name)
    silver = _silver(state, content, b)
    p.stats["silver"] = p.stats.get("silver", 0) + silver
    p.bounties_done += 1
    msgs = [f"【懸賞】「{title(content, b)}」交差了，{issuer(content, b)}的賞銀送到。", f"銀兩 +{silver}"]
    exp = _exp(state, content, b)
    if exp:
        msgs.append(f"經驗 +{exp}")
        msgs += team.add_team_exp(state, content, world, exp)
    deeds = ranger.add_deeds(state, content, b.deeds)
    if deeds:
        msgs.insert(2, f"俠名 +{deeds}")
    return msgs


def _done(state: GameState, content: Content, world: WorldStateStore, match) -> list[str]:
    msgs: list[str] = []
    for b in mine(state, content):
        if match(b):
            msgs += _complete(state, content, world, b)
    return msgs


def on_win(state: GameState, content: Content, world: WorldStateStore, loc_id: str, squad_id: str) -> list[str]:
    """遊歷打贏：在討伐的地點打贏一場對頭陣營的隊伍就交差（哪一支都算）。"""
    enemy = content.squads[squad_id].faction if squad_id in content.squads else None
    return _done(
        state, content, world,
        lambda b: b.kind == "strike" and b.location == loc_id and enemy is not None and enemy == ENEMY.get(b.faction or ""),
    )


def on_explore(state: GameState, content: Content, world: WorldStateStore, loc_id: str) -> list[str]:
    return _done(state, content, world, lambda b: b.kind == "scout" and b.location == loc_id)


def on_arrive(state: GameState, content: Content, world: WorldStateStore, loc_id: str) -> list[str]:
    return _done(state, content, world, lambda b: b.kind == "escort" and b.end == loc_id)


def on_raid_win(state: GameState, content: Content, world: WorldStateStore, target: str) -> list[str]:
    key = name_key(target)
    return _done(state, content, world, lambda b: b.kind == "wanted" and name_key(b.target or "") == key)


def hunting(state: GameState, content: Content, target: str) -> bool:
    """我接了通緝這個人、還沒完成（截殺的鈕看它：散人、同陣營的人也能對他下手）。"""
    key = name_key(target)
    return any(b.kind == "wanted" and name_key(b.target or "") == key for b in mine(state, content))


# ── 通緝（玩家花銀兩掛的）──────────────────────────────


def post_problem(state: GameState, content: Content, target_state: GameState, amount: int | None = None) -> str | None:
    """通緝這個人按不按得下去：懸賞榜與截殺都開著、你投靠了陣營、他是敵對陣營的人、他過了新手期、你手上沒有還掛著的通緝、錢夠。"""
    if not active(state, content) or not content.config.raid.enabled:
        return "（此刻無法這麼做。）"
    p, t = state.player, target_state.player
    if p.faction is None or t.faction is None or p.faction == t.faction:
        return "只能通緝敵對陣營的人。"
    if roster.raid_newbie(target_state, content):  # 截殺不了還在新手期的人：押了錢也只能等退（懸賞榜設計 6.2、14.1 丁）
        return f"{t.name}初入江湖，還在新手期，通緝不了他。"  # 待 joy 潤
    me = name_key(p.name)
    now = state.world.time
    if any(b.kind == "wanted" and b.poster and name_key(b.poster) == me and b.expires > now and _left(b) > 0
           for b in state.world.bounties):
        return "你已經掛著一張通緝了，等它揭下再說。"
    cfg = content.config.bounties
    purse = p.stats.get("silver", 0)
    if purse < cfg.post_min:
        return f"通緝至少要押 {cfg.post_min} 兩。"
    if amount is not None and not cfg.post_min <= amount <= min(cfg.post_max, purse):
        return f"賞金要在 {cfg.post_min}～{min(cfg.post_max, purse)} 兩之間。"
    return None


def post(state: GameState, content: Content, target_state: GameState, amount: int) -> list[str]:
    problem = post_problem(state, content, target_state, amount)
    if problem is not None:
        return [problem]
    p, w = state.player, state.world
    p.stats["silver"] = p.stats.get("silver", 0) - amount
    w.bounty_seq += 1
    b = Bounty(
        id=f"b{w.bounty_seq}", kind="wanted", faction=p.faction, week=calendar.point(w.time, content, w).week,
        expires=w.time + content.config.bounties.post_weeks * week_seconds(state, content), silver=amount,
        deeds=content.config.bounties.deeds.get("wanted", 0), quota=1, poster=p.name, target=target_state.player.name,
    )
    w.bounties.append(b)
    return [f"你押了 {amount} 兩，在懸賞榜上通緝{b.target}。", f"銀兩 -{amount}"]


def deliver_refunds(state: GameState, content: Content) -> list[str]:
    """我掛的通緝過期了、沒人完成：押金退回（掛單的人同步時呼叫）。"""
    p, now = state.player, state.world.time
    me = name_key(p.name)
    msgs: list[str] = []
    for b in state.world.bounties:
        if (b.kind == "wanted" and not b.refunded and not b.done_by and b.expires <= now
                and b.poster and name_key(b.poster) == me):
            b.refunded = True
            p.stats["silver"] = p.stats.get("silver", 0) + b.silver
            msgs += [f"【懸賞】你通緝{b.target}的那一張沒人揭成，押金退回。", f"銀兩 +{b.silver}"]
    return msgs


def deliver_lapses(state: GameState, content: Content) -> list[str]:
    """我揭了、還沒交差的那一張被別人交滿了名額、或過了期限：拿掉我的名字、補一句（FB-121 第 5 件；寫法同 deliver_refunds，同步時呼叫）。
    過了期限還有人揭著的單，issue 掛新單時先留著（等揭的人同步時在這裡拿掉），不然他回來只看到那一張默默不見了。"""
    p, now = state.player, state.world.time
    me = name_key(p.name)
    msgs: list[str] = []
    for b in state.world.bounties:
        if me not in (name_key(t) for t in b.takers) or me in (name_key(t) for t in b.done_by):
            continue
        if _left(b) <= 0:
            line = LAPSED_FULL
        elif b.expires <= now:
            line = LAPSED_DUE
        else:
            continue
        b.takers = [t for t in b.takers if name_key(t) != me]
        msgs.append(line.format(title=title(content, b)))
    return msgs


# ── 每週一自動掛單 ──────────────────────────────


def tick(state: GameState, content: Content) -> list[str]:
    """第一季規則關著的季的週初掛單（world.advance_world_state 每一步、world.settle_season_start 開季那一刻）：季曆跨進新的一週
    就掛這一週的（只掛這一週，以前的週不補掛；同一週只掛一次，見 issue 的兩道擋）。每一步最多一小時，所以最多晚一小時掛，
    期限錨在週初、不會跟著延後。不回傳訊息。"""
    w = state.world
    return issue(state, content, calendar.point(w.time, content, w).week)


def _opened(loc: Location, w: WorldState) -> bool:
    """這個地點全服來說開放了沒（FB-150：週初掛單只挑已開放的地點，不然揭的人「無法安排前往這裡」、那張單白占一個名額）。
    規則同 atlas.is_unlocked 去掉看人的那一半：不是序章專屬的地點，而且 unlock_flag 沒設或已經在世界旗標裡。
    不 import atlas（它 import rules、orders、figures，怕繞成環），所以在這裡照寫一份；那邊改了這邊要跟著改。"""
    return not loc.prologue_only and (not loc.unlock_flag or loc.unlock_flag in w.flags)


def _strike(content: Content, w: WorldState, faction: str, rng: random.Random, used: set[str]) -> tuple[str, str] | None:
    enemy = ENEMY[faction]
    spots = [
        (loc_id, sid) for loc_id, loc in content.locations.items() if loc_id not in used and _opened(loc, w)
        for sid in loc.enemies if sid in content.squads and content.squads[sid].faction == enemy
    ]
    return rng.choice(spots) if spots else None


def _scout(content: Content, w: WorldState, rng: random.Random, used: set[str]) -> str | None:
    """打探的地點：危險度 2 以上、不是城鎮、已開放；used 是榜上還有效的打探已經用掉的地點（不分陣營）。"""
    spots = [
        loc_id for loc_id, loc in content.locations.items()
        if loc.danger >= 2 and not is_town(content, loc_id) and loc_id not in used and _opened(loc, w)
    ]
    return rng.choice(spots) if spots else None


def _escort(content: Content, w: WorldState, rng: random.Random, used: set[str]) -> tuple[str, str] | None:
    """護送的起點與終點：兩個不相鄰的已開放城鎮；used 是榜上還有效的護送已經用掉的終點（不分陣營）。"""
    towns = [loc_id for loc_id, loc in content.locations.items() if is_town(content, loc_id) and _opened(loc, w)]
    pairs = [
        (a, b) for a in towns for b in towns
        if a != b and b not in {str(x) for x in content.locations[a].connections} and b not in used
    ]
    return rng.choice(pairs) if pairs else None


def issue(state: GameState, content: Content, week: int, rng: random.Random | None = None) -> list[str]:
    """週初掛單（第一季：world.WEEK_HOOKS；規則關著的季：tick）：陣營掛的舊單下榜（通緝照自己的期限），兩個陣營各掛 kinds 裡的每一張
    （只挑已開放的地點〔_opened，FB-150：南華觀要等 xi_open 立起來〕，避開榜上還有效〔沒過期、名額沒滿〕的同種單已經用掉的地點，
    不管是哪一週掛的：討伐看同一個陣營、打探不分陣營、護送不重複終點；濾完沒地方可挑就跳過那一張）。不回傳訊息。
    rng 不用（介面跟其他週初掛鉤一樣）。
    兩道擋（懸賞榜設計 3.2）：只掛「這一週」（week 要等於此刻的季曆週，同 orders.issue；不然停機補算、管理者快轉會把以前的週補掛出來），
    這一週掛過了不再掛（bounty_week）。期限錨在週初：week_start(週次＋auto_weeks)，晚掛也不會多掛。"""
    w, cfg = state.world, content.config.bounties
    if not active(state, content) or week != calendar.point(w.time, content, w).week or week <= w.bounty_week:
        return []
    w.bounty_week = week
    now = w.time
    # 自己一份亂數（週次、流水號、此刻的戰況）：不動季的 rng，排在後面的大事擲骰不會因為多了懸賞榜而位移
    rng = random.Random(f"bounty|{week}|{w.bounty_seq}|{sorted(w.trends.items())}")
    w.bounties = [
        b for b in w.bounties
        if b.expires > now
        or (b.kind == "wanted" and not b.refunded and not b.done_by)  # 過期的通緝留到押金退回
        or b.takers  # 過期了還有人揭著：留到他們同步時聽到那一句（deliver_lapses）
    ]
    expires = calendar.week_start(week + cfg.auto_weeks, content, w)
    # 同一地點不重複掛（FB-121 第 2 件：同一處兩張一樣的單，一次遊歷或探索交兩張差）：避開榜上還有效的同種單已經用掉的地點。
    # 討伐只看同一個陣營（兩邊打的對頭不同，on_win 不會一次交兩張）；打探不分陣營；護送不分陣營、不重複終點。濾完沒地方可挑就跳過那一張
    live = [b for b in w.bounties if b.expires > now and _left(b) > 0]
    scouted = {b.location for b in live if b.kind == "scout"}
    ends = {b.end for b in live if b.kind == "escort"}
    for faction in ENEMY:
        if faction not in {f.id for f in content.scenario.factions}:
            continue
        used = {b.location for b in live if b.kind == "strike" and b.faction == faction}
        for kind in cfg.kinds:
            spec: dict = {}
            if kind == "strike":
                spot = _strike(content, w, faction, rng, used)
                if spot is None:
                    continue
                used.add(spot[0])
                spec = {"location": spot[0], "squad": spot[1]}
            elif kind == "scout":
                loc = _scout(content, w, rng, scouted)
                if loc is None:
                    continue
                scouted.add(loc)
                spec = {"location": loc}
            elif kind == "escort":
                pair = _escort(content, w, rng, ends)
                if pair is None:
                    continue
                ends.add(pair[1])
                spec = {"location": pair[0], "end": pair[1]}
            else:
                continue
            w.bounty_seq += 1
            w.bounties.append(Bounty(
                id=f"b{w.bounty_seq}", kind=kind, faction=faction, week=week, expires=expires,
                silver=cfg.silver.get(kind, 0), deeds=cfg.deeds.get(kind, 0), quota=quota(content), **spec,
            ))
    return []


def targets(state: GameState, content: Content) -> list[str]:
    """假人往哪裡走：手上每一張要去的地點（討伐、打探：那裡；護送：終點）。"""
    out = []
    for b in mine(state, content):
        if b.kind == "escort":
            out.append(b.end)
        elif b.kind in ("strike", "scout"):
            out.append(b.location)
    return [loc for loc in out if loc in content.locations]


def status(state: GameState, content: Content) -> list[dict]:
    """狀態用：我手上的每一張（標題、怎麼完成、賞、期限與名額）。"""
    return [
        {"id": b.id, "title": title(content, b), "how": how(content, b), "reward": reward_text(state, content, b),
         "issuer": issuer(content, b), "due": due_line(state, content, b)}
        for b in mine(state, content)
    ]
