"""人物活起來（大勢人物擴充第一批；Joy 2026-10-17「歷史武將人數新增多一些，更智能化，像是真的活在這個亂世」；
設計稿 https://claude.ai/code/artifact/03df3760-b4bd-417c-935f-96dda0f500c2；數字在 Config.figure_life）。

- 每日行事（tick）：每 every_cal_days 個季曆天，每位能深度對話的人物照心事挑一件事做——移動（在 CharacterDef.haunts 之間走，
  follows 的人跟著走）、募兵（大勢人物回聲威，跟自然回復共用 daily_gain_cap）、襲擾（大勢人物替自己那一方推戰線，只在那條線
  這一季存在時）、養傷（剛吃了敗仗的人留在原地回一點聲威）。第一季的大勢人物不自己移動（時刻表搬人）。決定性的亂數
  （天機｜人物｜第幾輪），不碰 Game.rng 也不碰季的那一顆。移動與襲擾各發一則傳聞。
- 心事在 figures.mood_of（挑戰難度要用，放在 figures）。
- 風聞（spread）：玩家做了份量夠的事，跟這件事有關的人物記一句、情誼照表動；對話提示照 prompt_lines 帶進去。
- 華佗坐診（healer_factor）：他此刻在的醫館療傷打折。

只 import models、state、figures、rules、calendar、push、atlas（延後）；engine、world、team、companion_agent 呼叫它。"""
from __future__ import annotations

import random

from . import calendar, figures, push, relations, renown, seal_acts
from .calendar import DAY
from .models import Content
from .rules import add_rumor, change_trend, season_one, trend_shown, trend_value, world_day
from .state import GameState, WorldState
from .world_state import season_length_days

HEALER = "huatuo"  # 坐診打折的那一位（characters.json 的 id）

MOVE_LINE = "{name}移往{place}。"
RAID_LINE = "{name}的人馬在{place}一帶襲擾，{front}的戰事又緊了幾分。"
SEEN_LINE = "有人在{place}見到了{name}。"  # 不是大勢人物的人物走動：地方傳聞
HEARD = "{names}聽說了這件事，情誼 {delta:+d}。"
HEARSAY_TITLE = "風聞"  # 截殺、決戰的風聞另起的那一則江湖紀錄

MOOD_PROMPT = {
    "得意": "戰局對他這一方有利、或他的仇人剛倒下，他心情不錯、說話有底氣。",
    "焦慮": "戰局對他這一方不利、或聲威大損，他心事重重，急著找人幫忙。",
    "負傷": "他剛在別人手下吃了敗仗，臉上掛不住，提起打仗就不太高興。",
    "悲憤": "身邊的同袍、兄弟或師長剛倒下，他悲憤難平，一心想著報仇。",
}

# 心事 → 這一輪做哪件事的權重（移動、募兵、襲擾）；負傷一律養傷
WEIGHTS = {
    None: (0.5, 0.25, 0.25),
    "得意": (0.3, 0.2, 0.5),
    "焦慮": (0.2, 0.5, 0.3),
    "悲憤": (0.2, 0.2, 0.6),
}
STROLL = 0.6  # 不是大勢人物的人物這一輪走動的機會（其餘留在原地）


def on(content: Content) -> bool:
    return figures.life_on(content)


def period(content: Content, world: WorldState) -> float:
    """一輪多少世界秒。"""
    return content.config.figure_life.every_cal_days * 24 * calendar.cal_hour_seconds(content, world)


def home_of(content: Content, cid: str) -> str | None:
    ch = content.characters.get(cid)
    return None if ch is None else (ch.haunts[0] if ch.haunts else ch.talk_at or ch.recruit_at)


def where(state: GameState, content: Content, cid: str) -> str | None:
    """這位人物此刻在哪：大勢人物照他的狀態（不在場是 None），其他人照每日行事走到的地方、沒走過的照 talk_at。"""
    fid = figures.of_character(content, cid)
    if fid is not None:
        now = figures.state_of(state, content, fid)
        return now.location if now.status == "active" else None
    return state.world.whereabouts.get(cid) or home_of(content, cid)


def side_of(content: Content, cid: str) -> str | None:
    """站哪一方：大勢人物照人物表的陣營，其他人照 CharacterDef.side。"""
    fid = figures.of_character(content, cid)
    if fid is not None:
        return content.figures[fid].faction
    ch = content.characters.get(cid)
    return ch.side if ch is not None else None


def _region(content: Content, loc: str | None) -> str | None:
    from . import atlas  # noqa: PLC0415  atlas → world → rules：延後載入

    if loc is None or loc not in content.locations:
        return None
    found = atlas.region_of(content, loc)
    return found.id if found is not None else None


def _place(content: Content, loc: str) -> str:
    return content.locations[loc].name if loc in content.locations else loc


# ── 聲威：募兵與自然回復共用一天的上限 ────────────────────


def gain_left(world: WorldState, content: Content, fid: str) -> int:
    """這位人物這個遊戲日在戰場外還能回幾點聲威（daily_gain_cap；募兵、自然回復、犒軍共用）。開關關著是無限。"""
    if not on(content):
        return 10**9
    return max(0, content.config.figure_life.daily_gain_cap - int(world.trend_accum.get(_gain_key(world, content, fid), 0.0) + 1e-9))


def note_gain(world: WorldState, content: Content, fid: str, amount: int) -> None:
    """記下這一天回了多少（舊日子的帳順手刪掉）。"""
    if not on(content) or amount <= 0:
        return
    key = _gain_key(world, content, fid)
    for old in [k for k in world.trend_accum if k.startswith(f"gain:{fid}:") and k != key]:
        del world.trend_accum[old]
    world.trend_accum[key] = world.trend_accum.get(key, 0.0) + amount


def _gain_key(world: WorldState, content: Content, fid: str) -> str:
    return f"gain:{fid}:{world_day(content, world)}"


def _recruit(state: GameState, content: Content, fid: str) -> None:
    fig = content.figures[fid]
    now = figures.state_of(state, content, fid)
    room = min(fig.start_prestige - now.prestige, content.config.figure_life.recruit, gain_left(state.world, content, fid))
    if room > 0:  # 沒被打過的人（存檔裡沒有他）聲威本來就滿，不寫存檔
        figures._ensure(state, content, fid).prestige += room
        note_gain(state.world, content, fid, room)


# ── 每日行事 ─────────────────────────────────────────────


def tick(state: GameState, content: Content) -> None:
    """跨進新的一輪就讓每位人物做一件事（一次推進跨過好幾輪也只做最新那一輪：停機補算不洗版）。開季後第一次只記下輪數、不做事。"""
    w = state.world
    if not on(content) or w.ended or not content.characters:
        return
    turn = int(w.time // period(content, w))
    if turn == w.life_turn:
        return
    first, w.life_turn = w.life_turn < 0, turn
    if first:
        return
    from .features.feast import rules as feasts  # noqa: PLC0415  宴客（功能包）→ figure_life：延後載入

    movers = [cid for cid, ch in content.characters.items() if ch.deep_interaction and ch.follows is None]
    for cid in movers:
        if feasts.hosting(state, cid) is None:  # 擺著宴的人留在原地（第三批）
            _act(state, content, cid, random.Random(f"人物|{w.tianji}|{cid}|{turn}"))
    for cid, ch in content.characters.items():  # 跟著走的人最後才動：關羽、張飛跟著劉備
        if ch.follows is not None and ch.deep_interaction:
            _follow(state, content, cid, ch.follows)
    for cid, ch in content.characters.items():  # 第三批：宴客、求援委託（排在走動之後：照他這一輪走到的地方）
        if ch.deep_interaction:
            feasts.maybe_open(state, content, cid, turn)
            _maybe_rally(state, content, cid, turn)


RALLY_MOODS = ("焦慮",)  # 戰線吃緊、聲威大損：對自己陣營全部人發求援委託


def _maybe_rally(state: GameState, content: Content, cid: str, turn: int) -> None:
    """心事焦慮的大勢人物擲 rally_chance，對自己陣營全部人發一件求援委託（bounties.post_rally），陣營軍情一句。"""
    tuning = content.config.figure_life
    fid = figures.of_character(content, cid)
    if not tuning.rallies or fid is None or figures.state_of(state, content, fid).status != "active":
        return
    if mood_any(state, content, cid) not in RALLY_MOODS:
        return
    if random.Random(f"求援|{state.world.tianji}|{cid}|{turn}").random() >= tuning.rally_chance:
        return
    from . import bounties  # noqa: PLC0415  bounties → territory → …：延後載入

    made = bounties.post_rally(state, content, cid)
    if made is None:
        return
    side = made.faction
    add_rumor(state, bounties.RALLY_POSTED.format(who=content.characters[cid].name, side=content.scenario.faction_name(side, side),
                                                  how=bounties.how(content, made, world=state.world)),  # 陣營的傳聞：照陣營的人寫（FB-435：要給 world）
              made.location, content=content, layer="faction", faction=side)


def _act(state: GameState, content: Content, cid: str, rng: random.Random) -> None:
    ch = content.characters[cid]
    fid = figures.of_character(content, cid)
    from . import plans  # noqa: PLC0415  plans → figure_life

    walks = not plans.holds(content, cid)  # 照行程走的人（世界活起來）不在常去的地方之間隨機晃；亂數照抽，別人的序列不位移
    if fid is None:
        if len(ch.haunts) > 1 and rng.random() < STROLL and walks:
            _move(state, content, cid, None, rng)
        return
    now = figures.state_of(state, content, fid)
    if now.status != "active":
        return
    mood = figures.mood_of(state, content, fid)
    if mood == "負傷":  # 養傷：留在原地，回一點聲威
        _recruit(state, content, fid)
        return
    move, recruit, _raid = WEIGHTS.get(mood, WEIGHTS[None])
    roll = rng.random()
    timed = season_one(content, state.world)  # 第一季：時刻表搬人，自己不移動
    if roll < move:
        # 被引將釘著的人不走動（玉璽碎片改版第 2 批：坐鎮一日、期滿回原處）；亂數是每人每輪一份，別人的序列不位移
        if walks and not timed and len(ch.haunts) > 1 and now.location in ch.haunts and seal_acts.pinned(state.world, fid) is None:
            _move(state, content, cid, fid, rng)
        return
    if roll < move + recruit:
        _recruit(state, content, fid)
        return
    _raid_front(state, content, fid)


def _move(state: GameState, content: Content, cid: str, fid: str | None, rng: random.Random) -> None:
    ch = content.characters[cid]
    here = where(state, content, cid)
    options = [loc for loc in ch.haunts if loc != here]
    if not options:
        return
    dest = rng.choice(options)
    _place_at(state, content, cid, fid, dest)
    if fid is not None:
        add_rumor(state, MOVE_LINE.format(name=ch.name, place=_place(content, dest)), dest, content=content, layer="world")
    else:
        add_rumor(state, SEEN_LINE.format(name=ch.name, place=_place(content, dest)), dest, content=content, layer="local")


def _place_at(state: GameState, content: Content, cid: str, fid: str | None, dest: str) -> None:
    if fid is not None:
        figures._ensure(state, content, fid).location = dest
    else:
        state.world.whereabouts[cid] = dest


def _follow(state: GameState, content: Content, cid: str, leader: str) -> None:
    dest = where(state, content, leader)
    fid = figures.of_character(content, cid)
    if dest is None or dest == where(state, content, cid):
        return
    if fid is not None:
        if figures.state_of(state, content, fid).status != "active" or season_one(content, state.world):
            return
        if seal_acts.pinned(state.world, fid) is not None:  # 被引將釘著（改版第 2 批）：不跟著走
            return
    _place_at(state, content, cid, fid, dest)


def _raid_front(state: GameState, content: Content, fid: str) -> None:
    """襲擾：替自己這一方把所在戰線推 raid_push 點（照盡頭阻力，零頭累積）。那條線這一季不存在（第一季規則關著的季）時只是傳聞。"""
    fig = content.figures[fid]
    now = figures.state_of(state, content, fid)
    front = figures.line_of(state, content, fid)
    faction = content.scenario.find_faction(fig.faction)
    goal = faction.goals.get(front, 0) if faction is not None and front is not None else 0
    if not goal or not now.location:
        return
    w = state.world
    amount = content.config.figure_life.raid_push
    line = front if trend_shown(content, w, front) else "huangjin"  # 規則關著的季三條戰線合成黃巾聲勢
    if not season_one(content, w) and trend_shown(content, w, line) and amount > 0:  # 第一季人物本來就每曆時推（figures.tick）
        days = season_length_days(w, content)
        rate = amount * (min(1.0, content.config.drill_push_base_days / days) if days > 0 else 1.0)  # 季長倍數，同 Game.season_scale
        if content.config.push_resistance.enabled:
            rate *= push.resistance_share(trend_value(state, content, line), goal, content.config.push_resistance)
        key = f"raid:{fid}"
        pending = w.trend_accum.get(key, 0.0) + rate
        whole = int(pending + 1e-9)
        rest = max(0.0, pending - whole)
        if rest:
            w.trend_accum[key] = rest
        else:
            w.trend_accum.pop(key, None)
        if whole:
            change_trend(state, content, line, whole * goal, reveal=False)
    front_name = next((t.name for t in content.scenario.trends if t.id == front), front)
    add_rumor(state, RAID_LINE.format(name=fig.name, place=_place(content, now.location), front=front_name),
              now.location, content=content, layer="local")  # 地方傳聞：每兩天十幾位人物，放天下大事會洗版


# ── 倒下時的反應（第二批：人與人）────────────────────────

FELL_MOVE = "{fallen}倒下的消息傳到{here}，{ally}拔營趕往{dest}。"  # 待 joy 潤：盟友趕往那一區（天下大事，同設計稿「張梁拔營南下」）
FELL_GRIEF = "{fallen}倒下的消息傳到{here}，{ally}悲憤難平，誓要報仇。"  # 待 joy 潤：盟友沒有地方可趕（第一季、那一區沒有他的據點）
FELL_GLAD = "{foe}聽說{fallen}倒了，撫掌大笑。"  # 待 joy 潤：仇敵得意
REVENGE_LINE = "{who}放出話來：誰在{place}打贏{enemy}，替{fallen}報仇，賞銀加倍。"  # 待 joy 潤：盟友掛的復仇懸賞
HUNT_LINE = "{who}趁勢放出話來：誰在{place}打贏{enemy}，賞銀加倍。"  # 待 joy 潤：仇敵掛的追剿懸賞（設計稿：秦頡「張曼成一倒就放話加倍懸賞」）


def on_fall(state: GameState, content: Content, fid: str) -> list[str]:
    """一位大勢人物剛退場或重創（figures._change 叫）：關係表上的盟友悲憤（mood_of 照 fell_at 算）、往那一區趕（第一季的大勢人物
    不自己移動；大勢人物只走到自己的據點）、盟友那一方掛一張復仇懸賞；仇敵得意，仇敵那一方掛一張追剿懸賞。回傳天下大事的句子
    （呼叫端照接手那一句一起發）。一方最多一張懸賞，掛在倒下那一區。開關關著、沒有關係表、倒下的人沒有對話人物是空的。"""
    if not on(content) or not content.config.figure_life.reactions or not content.relations:
        return []
    fig = content.figures.get(fid)
    cid = fig.character if fig is not None else None
    if cid is None or cid not in content.characters:
        return []
    fallen = content.characters[cid].name
    spot = figures.state_of(state, content, fid).location
    region = _region(content, spot)
    lines: list[str] = []
    posted: set[str] = set()
    for ally in relations.allies(content, cid):
        ch = content.characters[ally]
        here = where(state, content, ally)
        if here is None or not ch.deep_interaction:
            continue
        dest = None if ch.follows is not None else _rush_to(state, content, ally, region, spot)
        tmpl = FELL_MOVE if dest is not None else FELL_GRIEF
        lines.append(tmpl.format(fallen=fallen, here=_place(content, here), ally=ch.name, dest=_place(content, dest or here)))
        if dest is not None:
            _place_at(state, content, ally, figures.of_character(content, ally), dest)
        lines += _post(state, content, ally, "復仇", region, spot, fallen, posted)
    for foe in relations.foes(content, cid):
        ch = content.characters[foe]
        if where(state, content, foe) is None or not ch.deep_interaction:
            continue
        lines.append(FELL_GLAD.format(foe=ch.name, fallen=fallen))
        lines += _post(state, content, foe, "追剿", region, spot, fallen, posted)
    return lines


FELL_DEED = "{fallen}在{place}倒下。"  # 世界記事（世界活起來）：章回主線讀 figure_fell 換交代人


def note_fall(state: GameState, content: Content, fid: str) -> None:
    """一位大勢人物剛退場或重創：記一筆世界記事（figure_fell；開關關著 deeds 自己不記）。"""
    from . import deeds  # noqa: PLC0415

    fig = content.figures.get(fid)
    if fig is None:
        return
    spot = figures.state_of(state, content, fid).location or None
    deeds.record(state, content, "figure_fell", FELL_DEED.format(fallen=fig.name, place=_place(content, spot) if spot else "陣中"),
                 place=spot, figures=[fig.character] if fig.character else [], side=fig.faction)


def _rush_to(state: GameState, content: Content, cid: str, region: str | None, spot: str | None) -> str | None:
    """盟友趕往倒下那一區的哪裡：他自己在那一區的據點（haunts）；不是大勢人物的，那一區沒有據點就到倒下的地方。
    第一季的大勢人物不自己移動（時刻表搬人）；已經在那一區、或倒下的地方不明，就不動。"""
    if region is None or _region(content, where(state, content, cid)) == region:
        return None
    fid = figures.of_character(content, cid)
    if fid is not None and season_one(content, state.world):
        return None
    if fid is not None and seal_acts.pinned(state.world, fid) is not None:  # 被引將釘著（改版第 2 批）：不趕往
        return None
    ch = content.characters[cid]
    mine = next((loc for loc in ch.haunts if _region(content, loc) == region), None)
    if mine is not None or fid is not None:
        return mine
    return spot if spot in content.locations else None


def _post(state: GameState, content: Content, cid: str, motive: str, region: str | None, spot: str | None,
          fallen: str, posted: set[str]) -> list[str]:
    from . import bounties  # noqa: PLC0415  bounties → territory → …：延後載入

    side = side_of(content, cid)
    if side is None or side in posted:
        return []
    made = bounties.post_figure(state, content, cid, motive, region, spot)
    if made is None:
        return []
    posted.add(side)
    tmpl = REVENGE_LINE if motive == "復仇" else HUNT_LINE
    return [tmpl.format(who=content.characters[cid].name, place=_place(content, made.location),
                        enemy=bounties.enemy_name(content, made), fallen=fallen)]


# ── 風聞 ─────────────────────────────────────────────────


def spread(state: GameState, content: Content, kind: str, target: str, *, at: str | None, side: str | None,
           text: str, region: str | None = None) -> list[str]:
    """玩家做了一件份量夠的事：跟它有關的人物記一句風聞、情誼照表動，回傳江湖紀錄的句子。
    kind：beat（打退大勢人物 target）、raid（截殺 side 那一方的 target）、merit（替 side 那一方在決戰 target 立功）。
    在場的範圍是事情發生的大區（at 那個地點所在的大區）；同一件事（kind|target）一季只傳一次。散人、陣營關係不明的人不受影響。"""
    if not on(content):
        return []
    p = state.player
    key = f"{kind}|{target}"
    if key in p.hearsay_keys:
        return []
    p.hearsay_keys.append(key)
    tuning = content.config.figure_life
    region = region or _region(content, at)  # 決戰直接給大區
    victim = content.figures[target].character if kind == "beat" and target in content.figures else None
    warring = [f.id for f in content.scenario.factions if f.goals]  # 交戰兩軍（豪強沒有自己的目標，不算誰的仇敵）
    deltas: dict[int, list[str]] = {}
    for cid, ch in content.characters.items():
        if not ch.deep_interaction or cid == victim:
            continue
        mine = side_of(content, cid)
        if mine is None or region is None or _region(content, where(state, content, cid)) != region:
            continue
        if kind == "beat":
            delta = tuning.ally_beaten if mine == side else tuning.foe_beaten if mine in warring and side in warring else 0
        elif kind == "raid":
            delta = tuning.side_raided if mine == side else 0
        else:
            delta = tuning.side_merit if mine == side else 0
        if not delta:
            continue
        notes = p.hearsay.setdefault(cid, [])
        notes.append(text)
        del notes[:-tuning.hearsay_keep]
        before = p.affinities.get(cid, 0)
        p.affinities[cid] = max(0, min(100, before + renown.warmed(content, delta)))  # 加的放慢（Config.affinity_gain_scale）
        moved = p.affinities[cid] - before
        if moved:
            deltas.setdefault(moved, []).append(ch.name)
        if moved > 0:  # 第二批：他欣賞你做的事，情誼夠的話會寫信道賀
            from . import letters  # noqa: PLC0415  letters → figure_life

            letters.note_cheer(state, content, cid, text)
    return [HEARD.format(names="、".join(names), delta=d) for d, names in sorted(deltas.items())]


def prompt_lines(state: GameState, content: Content, cid: str) -> str:
    """對話提示多的幾行：此刻在哪、心事、聽說過你的事（最多 hearsay_prompt 條）。開關關著是空的。"""
    if not on(content):
        return ""
    ch = content.characters[cid]
    lines = []
    here = where(state, content, cid)
    if here is not None and here != home_of(content, cid):
        lines.append(f"【{ch.name}此刻在】{_place(content, here)}（不是他平常在的地方）\n")
    mood = mood_any(state, content, cid)
    if mood is not None:
        lines.append(f"【{ch.name}此刻的心事】{mood}：{MOOD_PROMPT[mood]}\n")
    heard = state.player.hearsay.get(cid, [])[-content.config.figure_life.hearsay_prompt:] if content.config.figure_life.hearsay_prompt else []
    if heard:
        lines.append(f"【{ch.name}聽說過玩家的事】{'；'.join(heard)}（可以自然地提起，不必每句都提）\n")
    from . import deeds  # noqa: PLC0415  deeds 只讀狀態（世界活起來）

    lines.append(deeds.prompt_lines(state, content, cid))
    return "".join(lines)


def mood_any(state: GameState, content: Content, cid: str) -> str | None:
    """任何一位人物此刻的心事：大勢人物照 figures.mood_of；其他人只看關係表（盟友剛倒下悲憤、仇敵剛倒下得意）。開關關著是 None。"""
    if not on(content):
        return None
    fid = figures.of_character(content, cid)
    if fid is not None:
        return figures.mood_of(state, content, fid)
    return relations.mood(state, content, cid, figures.mood_span(content, state.world))


def healer_factor(state: GameState, content: Content) -> float:
    """華佗此刻坐診的醫館療傷打 healer_share 折；其他地方 1。"""
    if not on(content) or HEALER not in content.characters:
        return 1.0
    return content.config.figure_life.healer_share if where(state, content, HEALER) == state.player.location else 1.0


def healer_here(state: GameState, content: Content) -> bool:
    return healer_factor(state, content) < 1.0
