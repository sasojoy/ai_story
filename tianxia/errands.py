"""託付與來信（減法季整合設計 5.5、5.9，主機側計畫 Task 6-2；企劃者 2026-10-24 定）。

能深度對話、寫了託付池（FigureDef.errands）的大勢人物，情誼到 Config.figure_life.letter_affinity（40）時，每週（7 天的季是每段）
託你一件事，以一封「託付」信送到（letters.deliver 的第一順位：託付 → 道賀 → 邀宴 → 求援，一個送信日一封；減法季照早上 9 點的送信日）。
三種，事情本身是規則定的：
- 送信（letter）：走到 target，「此地」多一顆「交信」，按了就成；他回一封道謝信（不佔一天一封）。
- 探營（scout）：走到 target，「此地」多一顆「探營」（花 errand_stamina 體力），一次不打仗的探查：回一張卡（誰佔著、攻勢推到幾成、
  這幾天幾人在這裡出陣、守將），卡留在見聞（個人線索）。
- 勸降（persuade）：走到 target，「此地」多一顆「勸降」，按了叫出輸入框；寫一句，三段式（Game.persuade_request → 鎖外
  event_llm.rate_persuasion 評那一句 → Game.persuade）：引擎加情誼與名望的修正、夾在 persuade_floor～persuade_cap、自己擲骰；
  成了立痕跡、推線（照事件的推法），敗了打一場遭遇；模型叫不動就什麼都不發生（最保守，照批 4 的慣例），那一件照舊在。
辦成了：他的情誼 +affinity、陣營貢獻 +contribution（跟分岔、心意同一本每日上限）、他的那個心意 +1（ErrandDef.stance）、行狀一則
（annals.ERRAND）。過期作罷情誼 −errand_lapse_affinity；婉拒不扣。一人同時最多一件。假人不收託付、不回信（企劃者 2026-10-24）。
信的開頭那段話照 letters.write 的三段式請模型照他的口氣重寫（寫不出來照固定句）。

開關是 rules.jianfa(content, world, "errands")（加上書信本身的開關 letters.on）；關著每個函式都當沒有這回事。
狀態只在 PlayerState.errands（與那封信）；不碰季。只 import models、state、rules、calendar、gender、figures、atlas／conquest／territory（延後）；
letters、engine、weekcard、server 叫它。字待 joy 潤。"""
from __future__ import annotations

import random

from pydantic import BaseModel

from . import calendar, gender, rules
from .models import Content, ErrandDef
from .state import ErrandState, GameState, Letter, Rumor

VERBS = {"letter": "deliver", "scout": "scout", "persuade": "persuade"}  # 選項 id 的動詞：errand:<動詞>:<id>
LABELS = {"letter": "交信", "scout": "探營", "persuade": "勸降"}  # 鈕上、本週卡上的字（待 joy 潤）
STATUS_TEXT = {"open": "", "done": "辦成了", "lapsed": "作罷了", "declined": "婉拒了", "failed": "沒談成"}

ARRIVED = "{who}派人送來一封信，託你一件事。"  # 待 joy 潤：江湖紀錄那一句
LAPSED = "【託付】{who}託你{task}，過了期限，作罷了。"  # 待 joy 潤
DECLINED = "你回了{who}的信，婉拒了這件事。"  # 待 joy 潤
DONE = "{who}託你的事辦成了。"  # 待 joy 潤
DELIVERED = "你把信交給了{to}。"  # 待 joy 潤
THANKS = "{hero}見字如面：{task}一事，多虧{hero}奔走，此情記下了。"  # 待 joy 潤：送信辦成了的道謝信（固定句）
STEP = "到{place}，替{who}{label}。"  # 待 joy 潤：本週卡「你這一步」
SCOUT_TITLE = "探營・{place}："  # 待 joy 潤：見聞裡那張卡的開頭
PERSUADE_ASK = "（寫下你要怎麼勸他，二十字以內。）"  # 待 joy 潤：按「勸降」只叫出輸入框
PERSUADE_SILENT = "對方聽完，不置可否，揮手要你改日再來。"  # 待 joy 潤：模型叫不動——什麼都沒發生，那一件照舊在
PERSUADE_WON = "{who}沉默良久，終於點了頭。"  # 待 joy 潤
PERSUADE_LOST = "{who}冷笑一聲，喝令手下動手。"  # 待 joy 潤
NOT_HERE = "（此刻無法這麼做。）"
TEXT_MAX = 20  # 勸降那一句最多幾個字（同隨口應對）


def on(content: Content, world) -> bool:
    return rules.jianfa(content, world, "errands")


def find_def(content: Content, fid: str, eid: str) -> ErrandDef | None:
    fig = content.figures.get(fid)
    return next((d for d in fig.errands if d.id == eid), None) if fig is not None else None


def find(state: GameState, errand_id: str) -> ErrandState | None:
    return next((e for e in state.player.errands if e.id == errand_id), None)


def by_letter(state: GameState, letter_id: int) -> ErrandState | None:
    return next((e for e in state.player.errands if e.letter == letter_id), None)


def live(state: GameState) -> ErrandState | None:
    """身上還在辦的那一件（一人同時最多一件）：開著、還沒過期。"""
    t = state.world.time
    return next((e for e in state.player.errands if e.status == "open" and e.expires > t), None)


def who(content: Content, e: ErrandState) -> str:
    return content.figures[e.figure].name if e.figure in content.figures else e.figure


def cid_of(content: Content, e: ErrandState) -> str:
    fig = content.figures.get(e.figure)
    return (fig.character if fig is not None else None) or e.figure


def place(content: Content, loc: str) -> str:
    return content.locations[loc].name if loc in content.locations else loc


def task_text(content: Content, e: ErrandState) -> str:
    d = find_def(content, e.figure, e.errand)
    return d.task.format(place=place(content, e.target)) if d is not None else LABELS[e.kind]


def _pool(state: GameState, content: Content, reachable) -> list[str]:
    """這一週還能託你事的人物（人物表 id，照 id 排）：寫了託付池、對話人物聯絡得上（情誼到、在場：reachable）、這一週還沒託過你。"""
    week = calendar.point(state.world.time, content, state.world).week
    asked = {e.figure for e in state.player.errands if e.week == week}
    return sorted(fid for fid, fig in content.figures.items()
                  if fig.errands and fig.character and fid not in asked and reachable(fig.character))


def offer(state: GameState, content: Content, rng: random.Random, reachable) -> Letter | None:
    """送信日的第一順位（letters.deliver）：開著、不是假人、身上沒有還在辦的、這一週有人能託——挑一位（rng 是那一封信自己的亂數）、
    從他的池子挑一件（這一季還沒託過你的先），開單、寫信。沒有是 None。"""
    p = state.player
    if not on(content, state.world) or p.bot is not None or live(state) is not None:
        return None
    pool = _pool(state, content, reachable)
    if not pool:
        return None
    fid = rng.choice(pool)
    fig = content.figures[fid]
    given = {e.errand for e in p.errands}
    fresh = [d for d in fig.errands if d.id not in given] or list(fig.errands)
    return give(state, content, fid, rng.choice(fresh).id)


def give(state: GameState, content: Content, fid: str, eid: str) -> Letter:
    """開一件託付、附在一封「託付」信上（信放進 PlayerState.letters、託付放進 PlayerState.errands；舊的辦完、作罷的照
    errands_keep 丟最舊的）。回那封信。不檢查條件（offer 檢查過；測試直接叫）。"""
    p, w = state.player, state.world
    d = find_def(content, fid, eid)
    assert d is not None, (fid, eid)
    p.letter_seq += 1
    week = calendar.point(w.time, content, w).week
    expires = w.time + d.deadline_days * rules.day_seconds(content, w)
    p.errands.append(ErrandState(id=f"e{p.letter_seq}", figure=fid, errand=d.id, kind=d.kind, target=d.target, week=week,
                                 at=w.time, expires=expires, letter=p.letter_seq))
    keep = content.config.jianfa.errands_keep
    while len(p.errands) > keep:
        old = next((e for e in p.errands if e.status != "open"), p.errands[0])
        p.errands.remove(old)
    text = d.text.format(hero=gender.hero(p), place=place(content, d.target))
    letter = Letter(id=p.letter_seq, kind="託付", sender=content.figures[fid].character or fid, at=w.time, text=text)
    p.letters.append(letter)
    del p.letters[:-content.config.figure_life.letters_keep]
    return letter


def lapse(state: GameState, content: Content) -> list[str]:
    """過了期限還開著的託付作罷：他的情誼 −errand_lapse_affinity、那封信標成作罷，回江湖紀錄的句子（同步時、書信那一格）。"""
    p, w = state.player, state.world
    msgs: list[str] = []
    for e in p.errands:
        if e.status != "open" or e.expires > w.time:
            continue
        e.status, e.done_at = "lapsed", w.time
        letter = next((x for x in p.letters if x.id == e.letter), None)
        if letter is not None:
            letter.lapsed = True
        cid, cut = cid_of(content, e), content.config.jianfa.errand_lapse_affinity
        before = p.affinities.get(cid, 0)
        p.affinities[cid] = max(0, before - cut)
        msgs.append(LAPSED.format(who=who(content, e), task=task_text(content, e)))
        if p.affinities[cid] != before:
            msgs.append(f"{who(content, e)}情誼 {p.affinities[cid] - before:+d}")
    return msgs


def decline(state: GameState, content: Content, letter_id: int) -> list[str] | None:
    """婉拒這封信託的事（不扣情誼）；這封信沒有託付是 None（照舊的書信那一套）。"""
    e = by_letter(state, letter_id)
    if e is None:
        return None
    letter = next((x for x in state.player.letters if x.id == letter_id), None)
    if e.status != "open" or letter is None:
        return []
    e.status, e.done_at = "declined", state.world.time
    letter.lapsed = letter.read = True
    return [DECLINED.format(who=who(content, e))]


def here(state: GameState, content: Content) -> list[ErrandState]:
    """人在託付的地點、沒在路上：那一件（「此地」多一顆）。關著是空的。"""
    e = live(state)
    p = state.player
    if e is None or not on(content, state.world) or p.journey is not None or p.location != e.target:
        return []
    return [e]


def done(state: GameState, e: ErrandState, status: str = "done") -> None:
    e.status, e.done_at = status, state.world.time


def thank(state: GameState, content: Content, e: ErrandState) -> Letter:
    """送信辦成了：他回一封道謝信（不佔一天一封；固定句，伺服器照樣請模型重寫）。"""
    p = state.player
    p.letter_seq += 1
    letter = Letter(id=p.letter_seq, kind="道謝", sender=cid_of(content, e), at=state.world.time, about=task_text(content, e),
                    text=THANKS.format(hero=gender.hero(p), task=task_text(content, e)))
    p.letters.append(letter)
    del p.letters[:-content.config.figure_life.letters_keep]
    return letter


def _minutes(state: GameState, content: Content, loc: str) -> int:
    from . import atlas  # noqa: PLC0415  atlas → world → rules

    if state.player.location == loc and state.player.journey is None:
        return 0
    route = atlas.way_to(state, content, loc)
    return atlas.whole_minutes(route.minutes) if route is not None else 0


def card(state: GameState, content: Content, e: ErrandState) -> dict:
    """主機側計畫 1.3 的 main.errands／figure.errands 的一筆：{"id", "figure"（對話人物 id）, "who"（名字）, "kind", "text"（做什麼）,
    "target": {"location", "name", "minutes"（從你這裡步行幾分鐘；在那裡是 0）}, "deadline"（照 calendar.stamp_text）, "status"}。"""
    return {
        "id": e.id, "figure": cid_of(content, e), "who": who(content, e), "kind": e.kind, "text": task_text(content, e),
        "target": {"location": e.target, "name": place(content, e.target), "minutes": _minutes(state, content, e.target)},
        "deadline": calendar.stamp_text(e.expires, content, state.world), "status": e.status,
    }


def view(state: GameState, content: Content, fid: str | None = None) -> list[dict]:
    """這一季人物託你的事（還在辦的在前，其餘新的在前）；給了 fid 只列那一位的。關著是空的。"""
    if not on(content, state.world):
        return []
    rows = [e for e in state.player.errands if fid is None or e.figure == fid]
    rows.sort(key=lambda e: (e.status != "open", -e.at))
    return [card(state, content, e) for e in rows]


def letter_card(state: GameState, content: Content, letter: Letter) -> dict | None:
    """書信小卡（letters.view）上這封信託的那一件；不是託付的信是 None。"""
    e = by_letter(state, letter.id)
    return card(state, content, e) if e is not None and on(content, state.world) else None


def step_items(state: GameState, content: Content) -> list[dict]:
    """本週卡「你這一步」的第一順位（整合設計 6.1；weekcard._steps 接在最前面）：身上還在辦的那一件，
    [{"kind": "errand", "text", "who", "id", "target": {"location", "name", "minutes"}}]；沒有、關著是空的。"""
    e = live(state)
    if e is None or not on(content, state.world):
        return []
    return [{"kind": "errand", "text": STEP.format(place=place(content, e.target), who=who(content, e), label=LABELS[e.kind]),
             "who": who(content, e), "id": e.id, "target": card(state, content, e)["target"]}]


def scout_lines(state: GameState, content: Content, e: ErrandState) -> list[str]:
    """探營那一張卡（整合設計 5.9「對面幾人在推、條幾成、守將是誰」）：領地爭奪開著、那裡是一塊地時寫誰佔著、每一邊的攻勢推到幾成、
    這幾天幾人在這裡出陣；最後一句是守將（在場的大勢人物）或守在那裡的隊伍。字待 joy 潤。"""
    from . import conquest, figures, territory  # noqa: PLC0415  conquest → territory → rules

    w, loc = state.world, e.target
    names = content.scenario.faction_name
    lines: list[str] = []
    if conquest.on(content, w) and loc in conquest.blocks(content):
        held = conquest.holder(w, content, loc)
        lines.append(f"此地歸{names(held, held)}。" if held else "此地還沒有人佔下。")
        bars = conquest.bars(w, loc)
        if bars:
            lines += [f"{names(side, side)}的攻勢推到{int(value / 10 + 0.5)}成。" for side, value in sorted(bars.items())]
        else:
            lines.append("眼下沒有人在攻這裡。")
        counts: dict[str, int] = {}
        for row in conquest.pushers(w, content, loc):
            counts[row["side"]] = counts.get(row["side"], 0) + 1
        lines += [f"這幾天有{n}個{names(side, side)}的人在這裡出陣。" for side, n in sorted(counts.items())]
    chiefs = [content.figures[fid].name for fid in figures.present_at(state, content, loc)]
    if chiefs:
        lines.append(f"守將：{'、'.join(chiefs)}。")
    else:
        squads = [content.squads[sid].name for sid in territory.squads_at(w, content, loc) if sid in content.squads]
        lines.append(f"守在這裡的是{'、'.join(squads)}。" if squads else "營裡空蕩蕩的，沒見到守將。")
    return lines


def note_scout(state: GameState, content: Content, e: ErrandState, lines: list[str]) -> None:
    """探營那張卡留在見聞（個人線索：只有你看得到）。"""
    w = state.world
    w.rumors.append(Rumor(time=w.time, text=SCOUT_TITLE.format(place=place(content, e.target)) + "".join(lines),
                          location=e.target, layer="personal", character=state.player.name))


class PersuadeRequest(BaseModel):
    """勸降的單子（Game.persuade_request 開；鎖外 event_llm.rate_persuasion 讀；Game.persuade 進鎖照 errand、text 認同一件）。"""

    errand: str
    figure: str  # 託你的人物的名字
    who: str  # 勸的是誰（PersuadeDef.who）
    place: str
    text: str


def persuade_problem(state: GameState, content: Content, errand_id: str) -> str | None:
    """勸降現在按得下去嗎：那一件還在辦、是勸降、人就在那裡。不行回原因。"""
    e = find(state, errand_id)
    if e is None or e.kind != "persuade" or e not in here(state, content):
        return NOT_HERE
    return None


def clean_text(text: str) -> str | None:
    """勸降那一句：去頭尾空白、1～TEXT_MAX 字；不合用是 None。"""
    text = " ".join(str(text or "").split())
    return text if 0 < len(text) <= TEXT_MAX else None


def persuade_rate(state: GameState, content: Content, e: ErrandState, rate: int) -> int:
    """模型評的那一句（0～100）加情誼與名望的修正，夾在 persuade_floor～persuade_cap（整合設計 5.9「照情誼、名望、說的話；引擎再夾」）。"""
    cfg, p = content.config.jianfa, state.player
    affinity = p.affinities.get(cid_of(content, e), 0) - content.config.figure_life.letter_affinity
    bonus = min(cfg.persuade_bonus_cap, max(0, affinity // cfg.persuade_affinity_step))
    bonus += min(cfg.persuade_bonus_cap, max(0, p.stats.get("fame", 0) // cfg.persuade_fame_step))
    return max(cfg.persuade_floor, min(cfg.persuade_cap, int(rate) + bonus))


def persuade_roll(state: GameState, e: ErrandState) -> float:
    """勸降擲的那一顆（自己的亂數：用途、天機、名號、這一件；不碰 Game.rng）。0～100。"""
    return random.Random(f"勸降|{state.world.tianji}|{state.player.name}|{e.id}").random() * 100
