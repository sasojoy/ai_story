"""設伏劫道（後期體力玩法第一批，Joy 2026-10-16；Config.ambush）的純規則：哪幾段路設得了伏、這一段此刻有沒有埋伏、記下與收起。

規則（Joy 的修正為準）：
- 花 Config.ambush.stamina（80）體力，守在這一站往某一站的那段路上 hours 個世界小時；守著的時候本人不能移動（atlas.travel_block、
  Game._move_option），下線也照守。一個人同一時刻只守一處；同一段路可以有好幾個人各自埋伏（不擋，擋了就等於告訴人那裡有伏兵），
  路過的人一段只打一場（先設的先打；打完記了護身，同一段的下一個伏兵就劫不到他）。
- 敵對的人走過那一段（步行、疾行都算；照抵達那一站的時刻判）就跟伏兵打一場（Game._ambush_check，在 Game._arrivals 每換一段比一次）。
  贏的拿走輸的一點銀兩與幾個素材，輸的扣氣血——雙向的：伏兵輸了，賠的是伏兵自己的東西，埋伏也就散了。
- 保護照截殺：敵對陣營（allied.side_of 不同）或伏兵揭了通緝他；雙方過了新手期（roster.raid_newbie）；城鎮旁邊的路不能設；同一個伏兵劫
  同一個人隔 pair_cooldown_seconds（跟截殺共用 WorldState.raids）、剛被截過的人（WorldState.raided，Config.raid.shield_seconds）不劫。

效能：路過的人每換一段只查一次 WorldState.ambushes[路段鍵]（字典，一段最多幾筆），不掃全服；真的要打才讀伏兵的存檔、寫回一次。
收了、過了時刻的紀錄留 keep_hours，下線的人回來補算路程時照「當時」判（active 看 when，不看現在）；設新的埋伏時順手清掉過期的（prune）。
只讀寫傳進來的 GameState／WorldState；打、記帳、紀錄在 engine.Game。"""
from __future__ import annotations

from . import allied, atlas, bounties, roster
from .characters import name_key
from .models import Content
from .state import Ambush, AmbushPost, GameState, WorldState

HOUR = 3600.0

# 玩家看得到的字（待 joy 潤）
TITLE = "設伏"  # 江湖紀錄、戰報的類型
SET_LABEL = "設伏・往{to}的路"
LIFT_LABEL = "收伏（守著往{to}的路，{until} 撤）"
SET_DONE = "你在往{to}的路上埋伏下來，守到{until}。這段時間你守在這裡，不能移動。"
LIFTED = "你收起埋伏，從路邊撤了回來。"
EXPIRED = "往{to}的路上守了這麼久，沒再等到人，你收起埋伏。"
BROKEN = "你被{rival}打退，往{to}的埋伏散了。"
MOVE_BLOCKED = "守著埋伏"
TOWN = "城鎮旁邊耳目眾多，設不了伏"
NO_PREY = "散人只劫得了你揭了通緝的人，先去懸賞榜揭一張"
NEWBIE = "你初入江湖，還在新手期，先別結這種仇"
# 戰報與紀錄的敘事（{rival} 是對手的名號；伏兵是 owner）
OWNER_WON = "{rival}走進你的埋伏，被你打得丟下財物逃了。"
OWNER_LOST = "{rival}走進你的埋伏，反把你打退，搶走了你的財物。"
OWNER_DRAW = "{rival}走進你的埋伏，兩人鬥了半天不分高下，各自退開。"
PASSER_WON = "路上殺出伏兵{rival}，你把{him}打退，搶下{him}的財物。"
PASSER_LOST = "路上殺出伏兵{rival}，你不敵，財物被搶走。"
PASSER_DRAW = "路上殺出伏兵{rival}，兩人鬥了半天不分高下，各自退開。"


def on(content: Content) -> bool:
    return content.config.ambush.enabled and bool(content.scenario.factions)


def key(a: str, b: str) -> str:
    """路段鍵：兩頭的地點 id 排序後用 | 接起來（不分方向）。"""
    return "|".join(sorted((a, b)))


def _town(content: Content, loc_id: str) -> bool:
    loc = content.locations[loc_id]
    return content.config.explore_mix_of(loc.tags).kind == "town"


def road_ok(content: Content, a: str, b: str) -> bool:
    """這段路設不設得了伏：兩頭都不是城鎮類的地點、都不是序章專屬。"""
    la, lb = content.locations.get(a), content.locations.get(b)
    if la is None or lb is None or la.prologue_only or lb.prologue_only:
        return False
    return not _town(content, a) and not _town(content, b)


def roads(state: GameState, content: Content) -> list[str]:
    """從這裡出去、設得了伏的那幾段路的另一頭（照 connections 的順序；還沒開放的地點不算）。"""
    here = state.player.location
    loc = content.locations[here]
    return [
        to for to in loc.connections
        if atlas.is_unlocked(content.locations[to], state, content) and road_ok(content, here, to)
    ]


def end_of(a: Ambush) -> float:
    return a.until if a.lifted_at is None else min(a.until, a.lifted_at)


def active(world: WorldState, seg: str, when: float) -> Ambush | None:
    """when 那一刻這一段路上有效的埋伏（set_at ≤ when < 收起或到期）；沒有是 None。"""
    for a in world.ambushes.get(seg, ()):
        if a.set_at <= when < end_of(a):
            return a
    return None


def prune(world: WorldState, content: Content) -> None:
    """收了、過了時刻超過 keep_hours 的埋伏清掉（設新的埋伏時叫，字典不會越長越大）。"""
    keep = content.config.ambush.keep_hours * HOUR
    for seg in list(world.ambushes):
        kept = [a for a in world.ambushes[seg] if end_of(a) + keep > world.time]
        if kept:
            world.ambushes[seg] = kept
        else:
            del world.ambushes[seg]


def has_prey(state: GameState, content: Content) -> bool:
    """這個人設伏劫得到人嗎：投靠了陣營（有敵對的一方），或揭了通緝（散人只劫得了他揭的那個人）。"""
    if allied.side_of(state, content) is not None:
        return True
    return any(b.kind == "wanted" for b in bounties.mine(state, content))


def hostile(owner: GameState, passer: GameState, content: Content) -> bool:
    """伏兵劫不劫這個路過的人：兩邊都有一方、而且不同；或伏兵揭了通緝他（同截殺的 raid_shown，不看截殺的開關）。"""
    mine, theirs = allied.side_of(owner, content), allied.side_of(passer, content)
    if mine is not None and theirs is not None and mine != theirs:
        return True
    return bounties.hunting(owner, content, passer.player.name)


def maybe_hostile(world: WorldState, a: Ambush, side: str | None, name: str) -> bool:
    """不讀伏兵的存檔先篩一次（效能）：兩邊不同一方、或榜上有伏兵揭了的通緝他，才可能劫他。真的要打之前照樣用 hostile 再判一次
    （伏兵叛投了、通緝過期了都以那一次為準）。"""
    if a.side is not None and side is not None and a.side != side:
        return True
    owner, target = name_key(a.owner), name_key(name)
    return any(
        b.kind == "wanted" and name_key(b.target or "") == target and owner in (name_key(t) for t in b.takers)
        for b in world.bounties
    )


def set_problem(state: GameState, content: Content, to: str) -> str | None:
    """在往 to 的路上設伏，不行的原因；行是 None（體力與閒不閒由呼叫端看）。"""
    if not on(content) or state.world.ended:
        return "（此刻無法這麼做。）"
    p = state.player
    if p.ambush is not None:
        return "你已經守著一處埋伏"
    if p.journey is not None or to not in content.locations[p.location].connections:
        return "（此刻無法這麼做。）"
    if not road_ok(content, p.location, to):
        return TOWN
    if roster.raid_newbie(state, content):
        return NEWBIE
    if not has_prey(state, content):
        return NO_PREY
    return None


def place(state: GameState, content: Content, to: str) -> Ambush:
    """記下埋伏（呼叫端先問 set_problem、扣體力）：季上一筆、角色身上一筆。"""
    w, p = state.world, state.player
    prune(w, content)
    seg = key(p.location, to)
    a = Ambush(owner=p.name, at=p.location, to=to, set_at=w.time, until=w.time + content.config.ambush.hours * HOUR,
               side=allied.side_of(state, content))
    w.ambushes.setdefault(seg, []).append(a)
    p.ambush = AmbushPost(key=seg, to=to, until=a.until)
    return a


def mine_now(world: WorldState, post: AmbushPost, owner: str) -> Ambush | None:
    """角色身上那一筆對到季上的哪一筆（同一個人、還沒收）。"""
    for a in world.ambushes.get(post.key, ()):
        if a.owner == owner and a.lifted_at is None and a.until == post.until:
            return a
    return None


def lift(world: WorldState, post: AmbushPost, owner: str, when: float) -> None:
    """收起（自己收、被打退）：季上那一筆記 lifted_at（照 when，不早於設下的那一刻）。角色身上那一筆由呼叫端清。"""
    a = mine_now(world, post, owner)
    if a is not None:
        a.lifted_at = max(a.set_at, min(when, a.until))


def expired(state: GameState) -> bool:
    """角色身上那一筆到時刻了（同步時收起、說一聲）。"""
    post = state.player.ambush
    return post is not None and state.world.time >= post.until
