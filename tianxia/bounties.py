"""懸賞榜（PM 2026-10-08 派工「加強散人玩法」；Config.bounties）。

- 官軍、黃巾每週一 00:00（季曆，world.WEEK_HOOKS → issue）各自動掛討伐兩張、打探、護送各一張（Config.bounties.kinds）：討伐是到指定的地方遊歷、
  打贏一場對頭陣營的隊伍；打探是到指定的地方探索一次；護送是在起點的城鎮接下、走到終點的城鎮。掛 auto_weeks 週，過期的下榜。
- 投靠了陣營的人可以在玩家卡上花銀兩通緝一個敵對陣營的人（押金就是賞金）；接了通緝的人在卡上對他「截殺」，照截殺的規則打，
  打贏就完成。沒人完成就在 post_weeks 週後下榜，押金在掛單的人下次同步時退回（deliver_refunds）。
- 散人兩邊的都能接，陣營的人只能接自己陣營的（can_take）；接了才算，一個人同時最多接 max_taken 張。
  前 quota 個完成的人各拿一份：銀兩（遊俠名號到第 4 階的散人另有加成）與經驗，散人另記俠名（ranger.add_deeds）。

全部掛在第一季開關後面（rules.season_one）；開關關著時每個函式都什麼都不做、回空的。
只改 GameState（玩家與共用的季）；不 import engine、world（world 會 import 這裡，掛 WEEK_HOOKS）。"""
from __future__ import annotations

import math
import random

from . import calendar, ranger, rules, team
from .characters import name_key
from .models import Content
from .state import Bounty, GameState
from .world_state import WorldStateStore

KIND_NAMES = {"strike": "討伐", "scout": "打探", "escort": "護送", "wanted": "通緝"}
ENEMY = {"guan": "huang", "huang": "guan"}  # 自動掛單的兩個陣營與他們的對頭（同軍令）
BOARD = "懸賞榜"


def active(state: GameState, content: Content) -> bool:
    return rules.season_one(content, state.world)


def is_town(content: Content, loc_id: str) -> bool:
    loc = content.locations[loc_id]
    return content.config.explore_mix_of(loc.tags).kind == "town"


def board_here(state: GameState, content: Content) -> bool:
    """這裡看得到懸賞榜：第一季開著、人在城鎮類的地點。"""
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


def open_bounties(state: GameState, content: Content) -> list[Bounty]:
    """榜上還有效的（沒過期、還有名額）。"""
    if not active(state, content):
        return []
    now = state.world.time
    return [b for b in state.world.bounties if b.expires > now and _left(b) > 0]


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
    return [f"你揭下了「{title(content, b)}」：{how(content, b)}。（{reward_text(state, content, b)}）"]


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
    """通緝這個人按不按得下去：第一季、你投靠了陣營、他是敵對陣營的人、你手上沒有還掛著的通緝、錢夠。"""
    if not active(state, content):
        return "（此刻無法這麼做。）"
    p, t = state.player, target_state.player
    if p.faction is None or t.faction is None or p.faction == t.faction:
        return "只能通緝敵對陣營的人。"
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


# ── 每週一自動掛單 ──────────────────────────────


def _strike(content: Content, faction: str, rng: random.Random, used: set[str]) -> tuple[str, str] | None:
    enemy = ENEMY[faction]
    spots = [
        (loc_id, sid) for loc_id, loc in content.locations.items() if loc_id not in used
        for sid in loc.enemies if sid in content.squads and content.squads[sid].faction == enemy
    ]
    return rng.choice(spots) if spots else None


def _scout(content: Content, rng: random.Random) -> str | None:
    spots = [loc_id for loc_id, loc in content.locations.items() if loc.danger >= 2 and not is_town(content, loc_id)]
    return rng.choice(spots) if spots else None


def _escort(content: Content, rng: random.Random) -> tuple[str, str] | None:
    towns = [loc_id for loc_id in content.locations if is_town(content, loc_id)]
    pairs = [
        (a, b) for a in towns for b in towns
        if a != b and b not in {str(x) for x in content.locations[a].connections}
    ]
    return rng.choice(pairs) if pairs else None


def issue(state: GameState, content: Content, week: int, rng: random.Random | None = None) -> list[str]:
    """週初掛單（world.WEEK_HOOKS）：陣營掛的舊單下榜（通緝照自己的期限），兩個陣營各掛 kinds 裡的每一張（同一週同一個陣營的討伐不重複地點）。不回傳訊息。
    rng 不用（介面跟其他週初掛鉤一樣）。"""
    if not active(state, content):
        return []
    w, cfg = state.world, content.config.bounties
    now = w.time
    # 自己一份亂數（週次、流水號、此刻的戰況）：不動季的 rng，排在後面的大事擲骰不會因為多了懸賞榜而位移
    rng = random.Random(f"bounty|{week}|{w.bounty_seq}|{sorted(w.trends.items())}")
    w.bounties = [
        b for b in w.bounties
        if b.expires > now or (b.kind == "wanted" and not b.refunded and not b.done_by)  # 過期的通緝留到押金退回
    ]
    expires = now + cfg.auto_weeks * week_seconds(state, content)
    for faction in ENEMY:
        if faction not in {f.id for f in content.scenario.factions}:
            continue
        used: set[str] = set()
        for kind in cfg.kinds:
            spec: dict = {}
            if kind == "strike":
                spot = _strike(content, faction, rng, used)
                if spot is None:
                    continue
                used.add(spot[0])
                spec = {"location": spot[0], "squad": spot[1]}
            elif kind == "scout":
                loc = _scout(content, rng)
                if loc is None:
                    continue
                spec = {"location": loc}
            elif kind == "escort":
                pair = _escort(content, rng)
                if pair is None:
                    continue
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
    """狀態用：我手上的每一張（標題、怎麼完成、賞）。"""
    return [
        {"id": b.id, "title": title(content, b), "how": how(content, b), "reward": reward_text(state, content, b),
         "issuer": issuer(content, b)}
        for b in mine(state, content)
    ]
