"""玉璽碎片改版第 2 批：獨門行動——引將（玄紐）、頒詔（雲篆）、承露（承露）、傳檄（赤璋）、收心（歸心）
（docs/superpowers/specs/2026-10-21-玉璽碎片改版-design.md 第三、四、五、五之一章；計畫 docs/superpowers/plans/2026-10-21-玉璽碎片改版-2.md）。

- 一片一季 Config.seal.revamp.acts.uses 次、兩次之間隔 gap_days 天（次數記在全服的碎片上：SealShard.act_*，換手跟著碎片走，換季歸零）；
  每個行動生效 days 天。「天」照 day_seconds：有季曆的季（第一季的章）是季曆天，14 天的季是世界天。
- 生效中的行動記在季上（WorldState.seal_acts；SealAct 不記是誰）。掛點讀這裡的查詢：pinned（引將釘住的大勢人物；人物活起來不搬他）、
  edict_sense／edict_cultivate（頒詔：sensing.rate、cultivation.odds_for）、dew_factor／dew_clinic（承露：Game._advance_player_local、
  team 的療傷）、writ_factor（傳檄：Game.push_trend、Game._push_progress）、heart_open／heart_scale（收心：rules.can_meet、
  companion_agent._apply_turn、feasts.toast）。改版關著一律中性值（季上那一本本來就是空的，查詢再擋一次）。
- 不具名（企劃者）：天下大事與江湖史那一句（public_text）不寫是誰；誰用的只在全服登記那一筆 use（管理者看）與起用的人自己的紀錄裡。
- 引將改大勢人物的所在（pull）、期滿回原處（tick：world.advance_world_state 每一步、人物活起來走動之前叫；期滿那一刻另外切一段，
  next_end）、被時刻表或退場搬動時先回原處再提早結束（release：figures._change、_hand_over 叫）。
- 只 import models、state、calendar、world_state、treasures；allied、atlas、figures、rules、timetable 在函式裡延後 import（它們反過來
  import 的鏈很長，figures、figure_life、team、rules、sensing、cultivation 都會叫這裡）。不擲骰、不讀時鐘。字待 joy 潤。"""
from __future__ import annotations

import math
from collections.abc import Callable

from . import calendar, treasures
from .models import Content
from .state import GameState, SealAct, WorldState
from .world_state import SealRegistry, SealShard

KINDS = ("yinjiang", "banzhao", "chenglu", "chuanxi", "shouxin")  # models.SealActKind；第 3 批再加鎮地、補缺
EPS = calendar.EPS_SECONDS

# ── 字（待 joy 潤）────────────────────────────────────────────

NAMES = {"yinjiang": "引將", "banzhao": "頒詔", "chenglu": "承露", "chuanxi": "傳檄", "shouxin": "收心"}
DESC = {  # 碎片卡上那一句（數字照 Config.seal.revamp.acts）
    "yinjiang": "指定一位大勢人物，引到你此刻所在之地坐鎮一日：期間不走動，期滿回原處。",
    "banzhao": "詔令天下一日：人人靜心感悟擲中的機會 +{sense} 個百分點、修練升品的機會 ×{cultivate}。",
    "chenglu": "甘露降在你此刻所在的大區一日：那一區人人體力回復 ×{stamina}、醫館療傷不收錢。",
    "chuanxi": "指定一條戰線一日：那一軍在那條線上推的量 ×{push}。",
    "shouxin": "指定一位人物一日：人人跟他說話、宴客敬酒的情誼漲幅 ×{affinity}，求見不看門檻。",
}
RULE_NOTE = "一季 {uses} 次，兩次之間隔 {gap} 天。天下大事只寫有人起用，不寫是誰。"
WHAT = {  # 天下大事、江湖史、起用的人自己的紀錄與行狀共用的那一段
    "yinjiang": "{figure}應召移駐{place}，一日之內按兵不動",
    "banzhao": "詔令頒行天下，一日之內感悟與修練都順遂幾分",
    "chenglu": "甘露降於{region}，一日之內那一帶體力回得快，醫館療傷分文不取",
    "chuanxi": "檄文傳遍{line}，一日之內{side}在那裡推得更猛",
    "shouxin": "一日之內{person}對來客格外親厚，求見不拒",
}
PUBLIC = "有人起用了『{shard}』：{what}。"  # 天下大事與江湖史（不寫是誰，企劃者）
BACK = "{figure}坐鎮期滿，回到了{place}。"  # 引將期滿（天下大事；人物移動本來就寫天下大事）
MINE = "你起用了『{shard}』：{what}。這一季還能再起用 {left} 次。"  # 起用的人自己的江湖紀錄
ANNAL = "起用了『{shard}』：{what}。"  # 起用的人自己的行狀
LIVE = "生效中：{what}（到 {until}）"  # 碎片卡：這一片的行動此刻還在生效
CONFIRM = {  # 確認的問句；{target}、{side} 由畫面換成挑的那一個
    "yinjiang": "起用『{shard}』，把{target}引到{place}坐鎮一日？",
    "banzhao": "起用『{shard}』，頒詔天下一日？",
    "chenglu": "起用『{shard}』，讓甘露降在{region}一日？",
    "chuanxi": "起用『{shard}』，替{side}傳檄{target}一日？",
    "shouxin": "起用『{shard}』，讓{target}一日之內來者不拒？",
}
CONFIRM_TAIL = "用了之後這一季還剩 {left} 次，隔 {gap} 天才能再用。"
# 按不下去的原因
NOT_RUNNING = "此刻不是季中，起用不了。"
PAUSED = "賽季時鐘暫停中，起用不了。"
NO_SHARD = "你懷中沒有能起用的碎片。"
USED_UP = "這一季的 {n} 次都用過了。"
COOLING = "要到 {when} 之後才能再起用。"
ON_ROAD = "在路上起用不了，先到了地方再說。"
NO_TARGET = "要先指定一個目標。"
BAD_TARGET = "指定的目標不對。"
PICK_SIDE = "先挑這一次照哪一軍算。"
BAD_SIDE = "這條線上沒有那一軍。"
# 目標灰掉的原因（短）
PINNED = "正被引著"
HERE = "已經在這裡"
CLASH = "一日之內時刻表要動他"
GONE = "此刻不在江湖上"
NO_REGION = "這裡不在任何一個大區"


def on(content: Content) -> bool:
    """改版開著（同 seal.revamp_on；seal 反過來叫這裡，所以照 treasures 那一條讀）。"""
    return treasures.revamp_on(content)


def tuning(content: Content):
    return content.config.seal.revamp.acts


def act_of(content: Content, shard_id: str | None) -> str | None:
    """這一片的獨門行動（content/seal.json 的 act）；改版關著、沒有這一片、這一片這一批沒有行動是 None。"""
    shard = content.seal.get(shard_id or "")
    return shard.act if shard is not None and on(content) else None


# ── 時間：一日、間隔、次數 ───────────────────────────────────────

def day_seconds(content: Content, world: WorldState) -> float:
    """「一日」是幾個世界秒：有季曆的季（第一季的章：週末、7 天、21 天）是一個季曆天；14 天的季畫面寫的是世界天（「第 2 天 14:05」），
    照世界天（開發定，計畫第一節第 1 條）。"""
    if calendar.season_one_on(world, content):
        return calendar.DAY / calendar.cal_scale(content, world)
    return calendar.DAY


def span(content: Content, world: WorldState) -> float:
    return tuning(content).days * day_seconds(content, world)


def gap(content: Content, world: WorldState) -> float:
    return tuning(content).gap_days * day_seconds(content, world)


def used(shard: SealShard, season: int) -> int:
    """這一片這一季起用過幾次（act_season 不是這一季＝還沒用過）。"""
    return shard.act_uses if shard.act_season == season else 0


def left(shard: SealShard, season: int, content: Content) -> int:
    return max(0, tuning(content).uses - used(shard, season))


def ready_at(shard: SealShard, season: int, content: Content, world: WorldState) -> float | None:
    """這一片什麼時候才能再起用（世界秒）；這一季還沒用過是 None。"""
    if shard.act_season != season or shard.act_last is None:
        return None
    return shard.act_last + gap(content, world)


def note_use(shard: SealShard, season: int, now: float) -> None:
    """記一次起用（次數跟著碎片走）。"""
    if shard.act_season != season:
        shard.act_season, shard.act_uses = season, 0
    shard.act_uses += 1
    shard.act_last = now


# ── 生效中的 ───────────────────────────────────────────────

def ends(act: SealAct) -> float:
    return act.ended if act.ended is not None else act.until


def active(act: SealAct, t: float) -> bool:
    """生效的區間 [開始, 期滿或提前結束)。"""
    return act.start <= t + EPS and t < ends(act) - EPS


def live(world: WorldState, kind: str | None = None, t: float | None = None) -> list[SealAct]:
    t = world.time if t is None else t
    return [a for a in world.seal_acts if (kind is None or a.kind == kind) and active(a, t)]


def pinned(world: WorldState | None, fid: str) -> SealAct | None:
    """引將：此刻把 fid 釘住的那一筆（還沒期滿回原處、也還沒提前結束）；沒有是 None。人物活起來的走動、跟隨、趕往都問它。"""
    if world is None:
        return None
    return next((a for a in world.seal_acts if a.kind == "yinjiang" and a.target == fid and a.ended is None), None)


def edict_sense(world: WorldState, content: Content) -> int:
    """頒詔：靜心感悟擲中的機會多幾個百分點（sensing.rate 夾在上限之內）；沒有是 0。"""
    if not on(content):
        return 0
    return tuning(content).sense_points * len(live(world, "banzhao"))


def edict_cultivate(world: WorldState, content: Content) -> float:
    """頒詔：修練升品的機會倍數（cultivation.odds_for，跟寶物同一個位置）；沒有是 1。"""
    factor = 1.0
    if on(content):
        for _ in live(world, "banzhao"):
            factor *= tuning(content).cultivate
    return factor


def region_of(content: Content, loc_id: str | None) -> str | None:
    """地點所在的大區 id（atlas.region_of）；不是地點、地圖沒有大區是 None。"""
    from . import atlas  # noqa: PLC0415  atlas → world → rules → …：延後 import

    if not loc_id or loc_id not in content.locations:
        return None
    region = atlas.region_of(content, loc_id)
    return region.id if region is not None else None


def region_name(content: Content, region_id: str) -> str:
    return next((r.name for r in content.map.regions if r.id == region_id), region_id)


def dew_factor(state: GameState, content: Content, seconds: float) -> float:
    """承露的體力（PM 五之一 4）：這一段回復（世界秒 [此刻 − seconds, 此刻]）跟所在大區的承露重疊幾秒，那幾秒多乘（stamina − 1）；
    在路上照身後那一站的大區。沒有承露、改版關著是 1。"""
    w = state.world
    if seconds <= 0 or not w.seal_acts or not on(content):
        return 1.0
    region = region_of(content, state.player.location)
    begin, end = w.time - seconds, w.time
    overlap = sum(
        max(0.0, min(end, ends(a)) - max(begin, a.start)) for a in w.seal_acts if a.kind == "chenglu" and a.target == region
    )
    return 1.0 + (tuning(content).stamina - 1.0) * min(seconds, overlap) / seconds


def dew_clinic(state: GameState, content: Content) -> bool:
    """承露：人在承露那一區、此刻不在路上（醫館療傷不收錢）。"""
    if not state.world.seal_acts or not on(content) or state.player.journey is not None:
        return False
    region = region_of(content, state.player.location)
    return region is not None and any(a.target == region for a in live(state.world, "chenglu"))


def goal(content: Content, world: WorldState, side: str | None, line: str) -> int:
    """side 那一軍在 line 上的目標（往 100 是 +1、往 0 是 −1；規則關著的季三條戰線合成黃巾聲勢，照 rules.resolve_goals）；沒有是 0。"""
    from .rules import resolve_goals  # noqa: PLC0415

    faction = content.scenario.find_faction(side) if side else None
    return resolve_goals(content, world, faction.goals).get(line, 0) if faction is not None else 0


def writ_factor(world: WorldState, content: Content, line: str | None, side: str | None, direction: float | None = None) -> float:
    """傳檄：side 那一軍的人在 line 上往 direction（正：往 100；None＝往那一軍的目標，區塊進度用）推，此刻有照那一軍算、指定這條線的
    傳檄，而且方向是那一軍的目標，就乘 push（好幾筆相乘，PM 五之一 7）；其餘是 1。"""
    if not line or side is None or not world.seal_acts or not on(content):
        return 1.0
    factor = 1.0
    for act in live(world, "chuanxi"):
        if act.target != line or act.side != side:
            continue
        aim = goal(content, world, side, line)
        if aim and (direction is None or aim * direction > 0):
            factor *= tuning(content).push
    return factor


def heart_open(world: WorldState, content: Content, character_id: str) -> bool:
    """收心：此刻有指定他的收心（求見不看門檻）。"""
    return on(content) and any(a.target == character_id for a in live(world, "shouxin"))


def heart_scale(world: WorldState, content: Content, character_id: str) -> float:
    """收心：跟他說話、宴客敬酒加的情誼倍數；沒有是 1。"""
    factor = 1.0
    if on(content):
        for act in live(world, "shouxin"):
            if act.target == character_id:
                factor *= tuning(content).affinity
    return factor


def warmer(world: WorldState, content: Content, character_id: str, delta: int) -> int:
    """收心放大加的情誼（「漲幅」；扣的照舊），四捨五入（同 renown.warmed 的進位）。"""
    if delta <= 0:
        return delta
    scale = heart_scale(world, content, character_id)
    return delta if scale == 1.0 else math.floor(delta * scale + 0.5 + 1e-9)


# ── 引將：拉過去、提前結束、期滿回原處 ───────────────────────────

def pull(state: GameState, content: Content, act: SealAct) -> None:
    """引將起用那一下：記下原處、把人物搬到 act.place。"""
    from . import figures  # noqa: PLC0415

    figure = figures._ensure(state, content, act.target)  # noqa: SLF001  同一個套件
    act.origin = figure.location
    figure.location = act.place


def _back(state: GameState, content: Content, act: SealAct) -> bool:
    """回原處：他還在場、還站在被引到的地方才搬回去；回傳搬了沒。"""
    from . import figures  # noqa: PLC0415

    now = figures.state_of(state, content, act.target)
    if now.status != "active" or now.location != act.place or not act.origin or act.origin == act.place:
        return False
    figures._ensure(state, content, act.target).location = act.origin  # noqa: SLF001
    return True


def release(state: GameState, content: Content, fid: str) -> bool:
    """引將提前結束（PM 五之一 1：時刻表要搬他、他被打到退場、接位的人要搬他——時刻表優先）：先回原處、記下結束的那一刻。
    不另寫天下大事（時刻表與退場那一句本來就會寫）。沒被引著回 False。"""
    act = pinned(state.world, fid)
    if act is None:
        return False
    _back(state, content, act)
    act.ended = state.world.time
    return True


def tick(state: GameState, content: Content) -> list[str]:
    """期滿回原處（world.advance_world_state 每一步、人物活起來走動之前）：天下大事一句（BACK）。不看開關：關掉之前引出去的照樣回去。"""
    w = state.world
    if not w.seal_acts:
        return []
    from . import figures  # noqa: PLC0415
    from .rules import add_rumor  # noqa: PLC0415

    lines: list[str] = []
    for act in w.seal_acts:
        if act.kind != "yinjiang" or act.ended is not None or w.time + EPS < act.until:
            continue
        act.ended = act.until
        if _back(state, content, act):
            place = content.locations[act.origin].name if act.origin in content.locations else act.origin
            line = BACK.format(figure=figures.name_of(content, act.target), place=place)
            add_rumor(state, line, act.origin, content=content, layer="world")
            lines.append(line)
    return lines


def next_end(world: WorldState) -> float | None:
    """下一個還沒處理的引將期滿在什麼時候（world.advance_world_state 在那一刻另切一段）；沒有是 None。"""
    pending = [a.until for a in world.seal_acts if a.kind == "yinjiang" and a.ended is None]
    return min(pending) if pending else None


def clash(state: GameState, content: Content, fid: str, until: float) -> bool:
    """窗口內有還沒結算、會搬動或拿掉 fid 的時刻表大事（PM 五之一 1：按不下去）：只在第一季的季（時刻表只在那時結算）；人物效果的鍵照
    timetable._target 此刻指到誰；「會搬動」照 figures.moves。時間到了還沒收場的決戰也算（收場時才套效果）。"""
    w = state.world
    if not calendar.season_one_on(w, content):
        return False
    from . import figures, timetable  # noqa: PLC0415

    now = figures.state_of(state, content, fid)
    for event in timetable.events(w, content):
        if event.id in w.timeline or timetable.when(state, content, event) > until + EPS:
            continue
        for outcome in event.outcomes.values():
            for key, change in outcome.figures.items():
                if timetable._target(state, content, event, key) == fid and figures.moves(now, change, content):  # noqa: SLF001
                    return True
    return False


# ── 目標 ──────────────────────────────────────────────────

def lines(content: Content, world: WorldState) -> list[str]:
    """傳檄能指定的線：每條戰線照這一季的規則換成真的會動的那一條（規則關著的季三條合成黃巾聲勢），去重、照戰線的順序。"""
    from .rules import front_ids, resolve_trend, trend_shown  # noqa: PLC0415

    out: list[str] = []
    for front in front_ids(content):
        line = resolve_trend(content, world, front)
        if line is not None and line not in out and trend_shown(content, world, line):
            out.append(line)
    return out


def armies(content: Content, world: WorldState, line: str | None = None) -> list[str]:
    """交戰兩軍（散人挑一邊的那兩個）：在這條線（line 是 None 時任何一條能指定的線）上有目標的陣營，照劇本的順序。"""
    targets = [line] if line is not None else lines(content, world)
    return [f.id for f in content.scenario.factions if any(goal(content, world, f.id, t) for t in targets)]


def own_side(state: GameState, content: Content, line: str | None = None) -> str | None:
    """不用挑的自家：自己（豪強分屬兩軍的季照依附的那一軍，allied.side_of）是交戰兩軍之一就是它；散人與不依附的豪強是 None（要挑）。"""
    from . import allied  # noqa: PLC0415

    side = allied.side_of(state, content)
    return side if side in armies(content, state.world, line) else None


def figure_targets(state: GameState, content: Content, until: float) -> list[dict]:
    """引將能指定的大勢人物：此刻在場、有所在的（退場、重創、下獄、還沒出場的不列）；正被引著、已經在你這裡、一日之內時刻表要動他的灰掉
    （why）。照人物表的順序。"""
    from . import figures  # noqa: PLC0415

    here = state.player.location
    out = []
    for fid, fig in content.figures.items():
        now = figures.state_of(state, content, fid)
        if now.status != "active" or not now.location:
            continue
        why = (PINNED if pinned(state.world, fid) is not None else HERE if now.location == here
               else CLASH if clash(state, content, fid, until) else "")
        place = content.locations[now.location].name if now.location in content.locations else now.location
        out.append({"id": fid, "name": f"{fig.name}（{place}）", "why": why})
    return out


def person_targets(state: GameState, content: Content) -> list[dict]:
    """收心能指定的人物：能深談的人物（deep_interaction），大勢人物裡此刻退場、重創、下獄、還沒出場的灰掉。照人物表的順序。"""
    from . import figures  # noqa: PLC0415

    out = []
    for cid, ch in content.characters.items():
        if not ch.deep_interaction:
            continue
        fid = figures.of_character(content, cid)
        gone = fid is not None and figures.state_of(state, content, fid).status != "active"
        out.append({"id": cid, "name": ch.name, "why": GONE if gone else ""})
    return out


def line_targets(state: GameState, content: Content) -> list[dict]:
    from .rules import trend_name  # noqa: PLC0415

    return [{"id": line, "name": trend_name(content, line), "why": ""} for line in lines(content, state.world)]


def targets(state: GameState, content: Content, kind: str, until: float) -> list[dict]:
    """要指定目標的三種（引將、傳檄、收心）的清單；頒詔、承露不用指定（承露照所在的大區），是空的。"""
    if kind == "yinjiang":
        return figure_targets(state, content, until)
    if kind == "chuanxi":
        return line_targets(state, content)
    if kind == "shouxin":
        return person_targets(state, content)
    return []


# ── 一次起用 ───────────────────────────────────────────────

def mine(state: GameState, content: Content, reg: SealRegistry) -> tuple[SealShard, str] | None:
    """自己懷中、有獨門行動的那一片：（登記那一筆, 行動）；沒有是 None。"""
    from . import seal  # noqa: PLC0415  seal → battle_instance → …：延後 import

    shard = seal.shard_of(reg, state.player.name)
    kind = act_of(content, shard.id) if shard is not None else None
    return (shard, kind) if shard is not None and kind is not None else None


def problem(
    state: GameState, content: Content, reg: SealRegistry, season: int, *, running: bool, paused: bool,
    stamp: Callable[[float], str],
) -> str | None:
    """這一刻整個按不下去的原因（不看目標）；按得下去是 None。"""
    held = mine(state, content, reg)
    if held is None:
        return NO_SHARD
    if not running:
        return NOT_RUNNING
    if paused:
        return PAUSED
    shard, kind = held
    if left(shard, season, content) <= 0:
        return USED_UP.format(n=tuning(content).uses)
    ready = ready_at(shard, season, content, state.world)
    if ready is not None and state.world.time + EPS < ready:
        return COOLING.format(when=stamp(ready))
    if kind in ("yinjiang", "chenglu") and state.player.journey is not None:
        return ON_ROAD
    if kind == "chenglu" and region_of(content, state.player.location) is None:
        return NO_REGION + "。"
    return None


def target_problem(state: GameState, content: Content, kind: str, target: str, side: str) -> str | None:
    """指定的目標（與散人挑的那一軍）按不按得下去；可以是 None。"""
    if kind in ("yinjiang", "chuanxi", "shouxin"):
        if not target:
            return NO_TARGET
        row = next((t for t in targets(state, content, kind, state.world.time + span(content, state.world)) if t["id"] == target), None)
        if row is None:
            return BAD_TARGET
        if row["why"]:
            return f"{row['name']}{row['why']}。"
    if kind == "chuanxi" and own_side(state, content, target) is None:
        if not side:
            return PICK_SIDE
        if side not in armies(content, state.world, target):
            return BAD_SIDE
    return None


def plan(state: GameState, content: Content, shard_id: str, kind: str, target: str, side: str) -> SealAct:
    """要寫進季上的那一筆（呼叫端先驗過 problem、target_problem）：引將的地點是此刻所在、承露的目標是此刻所在的大區、傳檄照自家或挑的那一軍。"""
    w = state.world
    act = SealAct(kind=kind, shard=shard_id, start=w.time, until=w.time + span(content, w))
    if kind == "yinjiang":
        act.target, act.place = target, state.player.location
    elif kind == "chenglu":
        act.target = region_of(content, state.player.location) or ""
    elif kind == "chuanxi":
        act.target, act.side = target, own_side(state, content, target) or side
    elif kind == "shouxin":
        act.target = target
    return act


def what_text(content: Content, act: SealAct) -> str:
    """這一筆做了什麼（WHAT 填好）：天下大事、江湖史、自己的紀錄與行狀、碎片卡的「生效中」共用。"""
    from . import figures  # noqa: PLC0415
    from .rules import trend_name  # noqa: PLC0415

    def place(loc: str) -> str:
        return content.locations[loc].name if loc in content.locations else loc

    if act.kind == "yinjiang":
        return WHAT["yinjiang"].format(figure=figures.name_of(content, act.target), place=place(act.place))
    if act.kind == "chenglu":
        return WHAT["chenglu"].format(region=region_name(content, act.target))
    if act.kind == "chuanxi":
        return WHAT["chuanxi"].format(line=trend_name(content, act.target), side=content.scenario.faction_name(act.side, act.side))
    if act.kind == "shouxin":
        person = content.characters[act.target].name if act.target in content.characters else act.target
        return WHAT["shouxin"].format(person=person)
    return WHAT[act.kind]


def public_text(content: Content, act: SealAct) -> str:
    """天下大事與江湖史那一句：不寫是誰（企劃者）。"""
    return PUBLIC.format(shard=content.seal[act.shard].name, what=what_text(content, act))


def view(
    state: GameState, content: Content, reg: SealRegistry, season: int, *, running: bool, paused: bool,
    stamp: Callable[[float], str],
) -> dict | None:
    """碎片卡上的獨門行動（status.seal.act；碎片卡本來就只給持有者自己）：哪一種、說明、還剩幾次、按不按得下去與原因、這一片此刻生效中的
    那一句、能指定的目標（每一個可以帶灰掉的原因）、要不要挑一邊（sides）、確認的問句（{target}、{side} 由畫面換）。改版關著、手上
    沒有有行動的碎片是 None。"""
    held = mine(state, content, reg)
    if held is None:
        return None
    shard, kind = held
    cfg, w = tuning(content), state.world
    name = content.seal[shard.id].name
    why = problem(state, content, reg, season, running=running, paused=paused, stamp=stamp)
    nums = {"sense": cfg.sense_points, "cultivate": f"{cfg.cultivate:g}", "stamina": f"{cfg.stamina:g}", "push": f"{cfg.push:g}",
            "affinity": f"{cfg.affinity:g}"}
    current = next((a for a in reversed(w.seal_acts) if a.shard == shard.id and active(a, w.time)), None)
    here = state.player.location if state.player.journey is None else ""
    region = region_of(content, here) if here else None
    count = left(shard, season, content)
    out = {
        "kind": kind, "name": NAMES[kind], "text": DESC[kind].format(**nums),
        "rule": RULE_NOTE.format(uses=cfg.uses, gap=f"{cfg.gap_days:g}"),
        "left": count, "ok": why is None, "why": why or "",
        "live": LIVE.format(what=what_text(content, current), until=stamp(ends(current))) if current is not None else "",
        "targets": targets(state, content, kind, w.time + span(content, w)) if why is None else [],
        "sides": [],
        "confirm": CONFIRM[kind].format(
            shard=name, target="{target}", side="{side}",
            place=content.locations[here].name if here in content.locations else "",
            region=region_name(content, region) if region else "",
        ) + CONFIRM_TAIL.format(left=max(0, count - 1), gap=f"{cfg.gap_days:g}"),
    }
    if kind == "chuanxi" and why is None and own_side(state, content) is None:
        out["sides"] = [{"id": f, "name": content.scenario.faction_name(f, f)} for f in armies(content, w)]
    if kind == "chuanxi" and why is None and own_side(state, content) is not None:
        side = own_side(state, content)
        out["confirm"] = out["confirm"].replace("{side}", content.scenario.faction_name(side, side))
    return out
