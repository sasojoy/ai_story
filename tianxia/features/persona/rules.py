"""人物性子的純規則（設計稿 https://claude.ai/artifact/R8w6aMxgeH89djeKYC7n5U，Joy 2026-11-06「可以」、換季選「全部歸回本性」）。

- 每位人物兩條性子（content/personas.json，PersonaAxis）：一把兩頭的尺分五段，起點照史實，最多離起點 reach 段。
- 值是 -100～100（往 ends[1] 是正），一段 40 點：第 i 段是 [-100 + 40i, -60 + 40i)，最後一段含 100。起點是那一段的正中間。
- 跟他說話那一輪模型只歸「這句在把他往哪一頭推」（填 ends 的叫法或 NONE）；引擎記一筆：一人對一位人物一天一筆，份量照情誼（bands），
  不到第一檔不算、也不佔今天那一筆。
- 每天 00:00 以後第一個同步的人替全服結算（settle，懶結算：WorldState.persona_day 記結算到哪一天）：淨推力不到 min_net 份不動；
  夠了就動 points×份數、一天最多 daily_cap 點；一整天沒人推往起點回 decay 點；兩邊都很多、淨值卻不夠的是拉鋸（persona_torn）。
  換段那一刻記 persona_log、發一則天下傳聞（不列名字）、記一筆江湖史。
- 換季：WorldState 整個重來，就是全部歸回本性（Joy 11/6）；上一季的換段留在那一季的江湖史。

只 import 核心（models、state、rules、calendar）。玩家看得到的字都在這裡、都待 joy 潤。"""
from __future__ import annotations

from tianxia import calendar, rules
from tianxia.models import Content, PersonaAxis
from tianxia.state import GameState, PersonaNote, PersonaShift, WorldState

NONE = "none"  # 模型歸不進任何一頭時填的
SPAN = 40  # 一段幾點
HEARD = "（{name}把你的話聽進去了幾分。）"  # 待 joy 潤：記到你那一筆的那一輪
RUMOR = "有人說{name}近來{short}。"  # 待 joy 潤：換段那一刻的天下傳聞（不列名字）
CHRONICLE = "{name}的性子變了：{short}。"  # 待 joy 潤：江湖史
HISTORY = "{stamp} 起，{short}"  # 待 joy 潤：簡介的變化紀錄
TORN = "眾說紛紜，他自己也拿不定主意。"  # 待 joy 潤：簡介上拉鋸的那一句
ANNAL = "你常勸{name}{toward}，他近來果然{short}。"  # 待 joy 潤：勸過的人的行狀
MINE = "你勸過他 {n} 次"  # 待 joy 潤


def cfg(content: Content):
    return content.config.persona_shift


def on(content: Content) -> bool:
    return cfg(content).enabled and bool(content.personas)


def axes(content: Content, cid: str) -> list[PersonaAxis]:
    return list(content.personas.get(cid, [])) if on(content) else []


def covers(content: Content, cid: str) -> bool:
    """這位人物歸新的性子管（開著、他有性子）：舊的性情漂移對他不寫也不讀。"""
    return bool(axes(content, cid))


# ── 值與段 ──

def center(stage: int) -> int:
    return -100 + SPAN * stage + SPAN // 2


def stage_of(value: int) -> int:
    return max(0, min(4, (value + 100) // SPAN))


def bounds(content: Content, axis: PersonaAxis) -> tuple[int, int]:
    """這一條的值夾在哪裡：最多離起點 reach 段。"""
    reach = cfg(content).reach
    lo, hi = max(0, axis.start - reach), min(4, axis.start + reach)
    return -100 + SPAN * lo, (100 if hi == 4 else -100 + SPAN * (hi + 1) - 1)


def value(world: WorldState, cid: str, axis: PersonaAxis) -> int:
    return world.persona.get(cid, {}).get(axis.id, center(axis.start))


def stage(world: WorldState, cid: str, axis: PersonaAxis) -> int:
    return stage_of(value(world, cid, axis))


def find_end(content: Content, cid: str, said: str | None) -> tuple[PersonaAxis, int] | None:
    """模型填的叫法是哪一條的哪一頭（-1 是 ends[0]、+1 是 ends[1]）；NONE、清單外是 None。"""
    for axis in axes(content, cid):
        if said in axis.ends:
            return axis, (1 if said == axis.ends[1] else -1)
    return None


def ends_for(content: Content, cid: str) -> tuple[str, ...]:
    """跟 cid 說話時模型可以填的叫法（companion_agent 照它加 schema）；關著、他沒有性子是空的。"""
    return tuple(end for axis in axes(content, cid) for end in axis.ends)


def weight(content: Content, affinity: int) -> int:
    got = 0
    for at, share in sorted(cfg(content).bands):
        if affinity >= at:
            got = share
    return got


# ── 記一筆 ──

def heard_today(state: GameState, content: Content, cid: str) -> bool:
    note = state.player.persona_notes.get(cid)
    return note is not None and note.day == rules.game_day(content, state.world)


def record(state: GameState, content: Content, cid: str, said: str | None, affinity: int) -> int:
    """記一筆，回算了幾份（0 是沒記：關著、歸不進、今天記過、情誼不到第一檔）。"""
    hit = find_end(content, cid, said)
    if hit is None or heard_today(state, content, cid):
        return 0
    share = weight(content, affinity)
    if share <= 0:
        return 0
    settle(state, content)
    axis, sign = hit
    w = state.world
    push = w.persona_push.setdefault(cid, {})
    push[axis.id] = push.get(axis.id, 0) + sign * share
    tug = w.persona_tug.setdefault(cid, {})
    tug[axis.id] = tug.get(axis.id, 0) + share
    note = state.player.persona_notes.setdefault(cid, PersonaNote())
    note.day = rules.game_day(content, w)
    note.said[said] = note.said.get(said, 0) + 1
    note.first.setdefault(said, w.time)
    return share


def hear(state: GameState, content: Content, cid: str, said: str | None, affinity: int) -> list[str]:
    """跟 cid 說話的一輪收尾（companion_agent._apply_turn）：記到了回那一句，沒記到是空的。"""
    if not record(state, content, cid, said, affinity):
        return []
    return [HEARD.format(name=content.characters[cid].name)]


# ── 每天結算 ──

def settle(state: GameState, content: Content) -> list[PersonaShift]:
    """結算到今天（懶結算：每天 00:00 以後第一個碰到的人替全服算；重複叫是安全的）。回這一次換了段的紀錄。關著什麼都不做。"""
    if not on(content):
        return []
    w = state.world
    today = rules.game_day(content, w)
    if w.persona_day == 0:
        w.persona_day = today
        return []
    shifted: list[PersonaShift] = []
    while w.persona_day < today:
        shifted += _one_day(state, content)
        w.persona_day += 1
        w.persona_push, w.persona_tug = {}, {}
    return shifted


def _one_day(state: GameState, content: Content) -> list[PersonaShift]:
    c, w = cfg(content), state.world
    shifted: list[PersonaShift] = []
    torn: dict[str, list[str]] = {}
    for cid, rows in content.personas.items():
        if cid not in content.characters:
            continue
        for axis in rows:
            before = value(w, cid, axis)
            net = w.persona_push.get(cid, {}).get(axis.id, 0)
            total = w.persona_tug.get(cid, {}).get(axis.id, 0)
            home = center(axis.start)
            if abs(net) >= c.min_net:
                step = min(c.daily_cap, abs(net) * c.points) * (1 if net > 0 else -1)
            elif total == 0 and before != home:
                step = min(c.decay, abs(before - home)) * (1 if home > before else -1)
            else:
                step = 0
            if total >= 2 * c.min_net and abs(net) < c.min_net:
                torn.setdefault(cid, []).append(axis.id)
            if not step:
                continue
            lo, hi = bounds(content, axis)
            after = max(lo, min(hi, before + step))
            if after == home:
                w.persona.get(cid, {}).pop(axis.id, None)
                if not w.persona.get(cid):
                    w.persona.pop(cid, None)
            else:
                w.persona.setdefault(cid, {})[axis.id] = after
            new = stage_of(after)
            if new != stage_of(before):
                shifted.append(_shift(state, content, cid, axis, new, axis.ends[1] if after > before else axis.ends[0]))
    w.persona_torn = torn
    return shifted


def _shift(state: GameState, content: Content, cid: str, axis: PersonaAxis, new: int, toward: str) -> PersonaShift:
    w = state.world
    seq = (w.persona_log[-1].seq if w.persona_log else 0) + 1
    entry = PersonaShift(seq=seq, who=cid, axis=axis.id, stage=new, toward=toward, at=w.time)
    w.persona_log.append(entry)
    ch = content.characters[cid]
    short = axis.stages[new].short
    rules.add_rumor(state, RUMOR.format(name=ch.name, short=short), ch.talk_at, content=content, layer="world", named=False)
    rules.add_chronicle(state, CHRONICLE.format(name=ch.name, short=short))
    return entry


# ── 勸過的人的行狀 ──

def annals_due(state: GameState, content: Content) -> list[tuple[PersonaShift, str]]:
    """你推過那一頭、之後他真的往那一頭換了段、還沒記過行狀的那幾筆（換段紀錄, 行狀那一句）；記下來之後標成記過了。"""
    if not on(content):
        return []
    out = []
    for entry in state.world.persona_log:
        note = state.player.persona_notes.get(entry.who)
        if note is None or not note.said.get(entry.toward) or entry.seq in note.told or note.first.get(entry.toward, entry.at + 1) > entry.at:
            continue
        axis = next((a for a in axes(content, entry.who) if a.id == entry.axis), None)
        if axis is None:
            continue
        # 往起點回的那一段（toward 是起點那一頭、新的一段正是起點）不算你勸成的
        if entry.stage == axis.start:
            continue
        note.told.append(entry.seq)
        name = content.characters[entry.who].name
        out.append((entry, ANNAL.format(name=name, toward=entry.toward, short=axis.stages[entry.stage].short)))
    return out


# ── 給模型與畫面 ──

def prompt_lines(state: GameState, content: Content, cid: str) -> str:
    """對話提示多的一段：他如今的性子（我們寫好的那一段，不讓模型自己編）、拉鋸、要模型多填的 persona。關著、他沒有性子是空的。"""
    rows = axes(content, cid)
    if not rows:
        return ""
    w = state.world
    name = content.characters[cid].name
    now = "".join(f"- {axis.stages[stage(w, cid, axis)].text}\n" for axis in rows)
    torn = f"近來身邊的人勸法不一，他有些左右為難。\n" if w.persona_torn.get(cid) else ""
    hints = "".join(f"- {end}：{hint}\n" for axis in rows for end, hint in zip(axis.ends, axis.hints))
    return (
        f"【{name}如今的性子】以這幾句為準，說話做事照它（比上面的性格更新）：\n{now}{torn}"
        f"另外在 persona 欄位填玩家這一步（說的這句話或選的這個做法）最像在把{name}往哪一頭推，只能填下面的字：\n{hints}"
        f"都不是的填 {NONE}。這一欄只是歸類，不要在敘事裡提到它。\n"
    )


def view(state: GameState, content: Content, cid: str) -> dict | None:
    """簡介的「如今」與變化紀錄：{now, history, torn, mine}。沒換過段的時候 now 是 None（畫面只畫本性）。關著、他沒有性子是 None。"""
    rows = axes(content, cid)
    if not rows:
        return None
    w = state.world
    moved = [axis.stages[stage(w, cid, axis)].text for axis in rows if stage(w, cid, axis) != axis.start]
    by_id = {axis.id: axis for axis in rows}
    history = [HISTORY.format(stamp=calendar.stamp_text(e.at, content, w, clock=False), short=by_id[e.axis].stages[e.stage].short)
               for e in w.persona_log if e.who == cid and e.axis in by_id]
    note = state.player.persona_notes.get(cid)
    n = sum(note.said.values()) if note is not None else 0
    return {
        "now": "".join(moved) if moved else None,
        "history": history,
        "torn": TORN if w.persona_torn.get(cid) else None,
        "mine": MINE.format(n=n) if n else None,
    }
