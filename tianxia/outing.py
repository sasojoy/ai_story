"""走一趟（企劃者 2026-10-29～30；設計稿 https://claude.ai/artifact/RJu4dK5cZoQcEe8SHphktc）：按一次探索走一、三、五段，
每一段就是現行的一次探索（Game._explore_one：一樣的表、一樣扣體力、一樣寫一則江湖紀錄），只是串起來演。

- 素材、遭遇自動走；端出要選的事（事件、有所感、頭目）就停在那一段，玩家選完再接著走（Game.outing_go 不帶段數）。
- 打輸、一段走完氣血低於上限的 outing_turn_back 就回頭；沒走的段不扣體力（體力是一段一段扣的）。
- 段數越多稀有的越容易來（rare_boost）：奇遇事件、一條線的開頭、二階素材、特殊頓悟的機率乘這一趟的倍數。畫面不寫倍數。

- 走完可以在這一處留一句話（say）：預設句免費，自己寫的要一張題壁墨（商城 inscribe，先只能用元寶買），過字表與模型、
  後面掛名號；一處留最近 outing_keep 則，管理者可以刪。之後來這裡走一趟的人，路上會看到刻在石頭、樹上的這一句（trace 那一行，
  不佔段數，一趟最多 outing_trace_cap 行，自己寫的比預設句容易抽到）；這一處 24 小時內有別人，遠處會有個人朝你揮手。

這裡只放純規則（開關、倍數、這一趟還在不在路上、留言、畫面那一份）；走路本身在引擎（Game.outing_go、Game._outing_walk）。
"""

from __future__ import annotations

import random

from .models import Content
from .rules import jianfa
from .state import GameState, Inscription, Outing, OutingBeat

DONE, LOST, HURT, TIRED, LEFT = "done", "lost", "hurt", "tired", "left"
# 收尾那一句（待 joy 潤）：走完不另說，結算卡自己寫「走完一趟」
END_LINES = {
    LOST: "負傷退回，剩下的路不走了。",
    HURT: "氣血見底，先回頭了。",
    TIRED: "體力不夠，先回頭了。",
    LEFT: "人已經離開了那裡，這一趟就到這裡。",
}
END_TITLES = {DONE: "走完一趟", LOST: "負傷退回", HURT: "回頭", TIRED: "回頭", LEFT: "中途離開"}
# 選段數時那一行（Joy 10/30「有顯示多段的時候越容易獲得更好獎勵的資訊就夠了」；待 joy 潤）
MORE_IS_RARER = "走得越遠，越容易碰上稀有的東西。"
INK = "inscribe"  # 題壁墨：商城的效果名（mall.EFFECTS）；買了得一張，自己寫一句用掉一張
TRACE = "trace"  # 路上看到的那一行（留言、遠處的人）：OutingBeat.kind，不佔段數
# 預設句（免費；假人也從這裡挑；待 joy 潤）
PRESETS = (
    "此處有匪，慎行。", "溪水可飲。", "前路難行，量力而為。", "此地清靜，宜歇腳。", "好風景，不枉此行。",
    "某到此一遊。", "後來者保重。", "林中有寶，細找。", "夜裡莫獨行。", "江湖路遠，有緣再會。",
)
SURFACES = ("路邊的石頭", "一棵老樹的樹幹", "半截斷碑", "破廟的牆", "橋頭的欄杆")  # 留言刻在哪（照留言 id 挑，同一則每次一樣）
SEEN_LINE = "{surface}上刻著一行字：「{text}」——{author}"
WAVE_LINE = "遠處山坡上，{name}朝你揮了揮手。"
# 留言那一格（待 joy 潤）
SAY_DONE = "你在{place}留下一句：「{text}」"
SAY_AGAIN = "這一趟已經留過一句了。"
SAY_NOT_HERE = "要人在這一處，走完一趟才能留言。"
SAY_EMPTY = "寫點什麼再留。"
NO_INK = "自己寫的要用一張題壁墨，你手上沒有，先到萬寶閣買。"
ERASED = "那一句已經抹掉了。"


def on(content: Content, state: GameState) -> bool:
    """走一趟開著：減法季的探索一顆開著，而且 outing 子開關也開著（rules.jianfa）。"""
    world = state.world
    return jianfa(content, world, "explore_one") and jianfa(content, world, "outing")


def segments(content: Content) -> list[int]:
    return list(content.config.jianfa.outing_segments)


def active(state: GameState) -> Outing | None:
    """還在路上的那一趟（沒收、人還在出發的地方）；沒有是 None。"""
    trip = state.player.outing
    if trip is None or trip.end or trip.place != state.player.location:
        return None
    return trip


def rare_boost(state: GameState, content: Content) -> float:
    """此刻稀有的東西乘多少：在路上照這一趟幾段（Config.jianfa.outing_rare），不在路上是 1（跟以前一模一樣）。"""
    trip = active(state)
    if trip is None or not on(content, state):
        return 1.0
    return float(content.config.jianfa.outing_rare.get(str(trip.total), 1.0))


def cost(content: Content, total: int) -> int:
    return content.config.jianfa.explore_stamina * total


def view(state: GameState, content: Content) -> dict | None:
    """/api/main 的 outing：網頁照它畫探索鈕的段數選單（picker）與走一趟的畫面（trip）。關著是 None（網頁照舊一顆探索）。"""
    if not on(content, state):
        return None
    p = state.player
    picker = [{"n": n, "stamina": cost(content, n), "ok": p.stamina >= cost(content, n)} for n in segments(content)]
    trip = p.outing
    out = {"picker": picker, "note": MORE_IS_RARER, "trip": None}
    if trip is not None:
        out["trip"] = {
            "place": content.locations[trip.place].name if trip.place in content.locations else trip.place,
            "total": trip.total, "done": trip.done, "end": trip.end,
            "waiting": not trip.end and bool(trip.beats) and trip.beats[-1].stop,
            "title": END_TITLES.get(trip.end, ""), "end_line": END_LINES.get(trip.end, ""),
            "beats": [b.model_dump() for b in trip.beats],
            "said": trip.said, "can_say": say_ok(state) is not None, "presets": list(PRESETS),
            "say_max": content.config.jianfa.outing_say_max,
        }
    return out


def say_ok(state: GameState) -> Outing | None:
    """此刻能在這一趟留一句：這一趟收了（走完或回頭；中途離開不算）、還沒留過、人還在這一處。不行是 None。"""
    trip = state.player.outing
    if trip is None or not trip.end or trip.end == LEFT or trip.said or trip.place != state.player.location:
        return None
    return trip


def inscribe(state: GameState, content: Content, text: str, *, preset: bool) -> Inscription:
    """把這一句刻在這一趟的地點（WorldState.inscriptions），同一處只留最近 outing_keep 則。呼叫端驗過能留、驗過字。"""
    w, trip = state.world, state.player.outing
    w.inscription_seq += 1
    item = Inscription(id=w.inscription_seq, place=trip.place, text=text, author=state.player.name, preset=preset, time=w.time)
    w.inscriptions.append(item)
    here = [i for i in w.inscriptions if i.place == trip.place]
    drop = {i.id for i in here[:-content.config.jianfa.outing_keep]}
    w.inscriptions = [i for i in w.inscriptions if i.id not in drop]
    trip.said = text
    return item


def erase(state: GameState, ins_id: int) -> bool:
    before = len(state.world.inscriptions)
    state.world.inscriptions = [i for i in state.world.inscriptions if i.id != ins_id]
    return len(state.world.inscriptions) < before


def traces_left(trip: Outing, content: Content) -> int:
    return content.config.jianfa.outing_trace_cap - sum(1 for b in trip.beats if b.kind == TRACE)


def trace_rng(state: GameState, trip: Outing) -> random.Random:
    """路上那幾行用的亂數：照名號、此刻的季曆時間、走到第幾段（不動 Game.rng，別的亂數一個都不變）。"""
    return random.Random(f"{state.player.name}:{state.world.time:.3f}:{trip.done}:trace")


def seen_beat(state: GameState, content: Content, trip: Outing, rng: random.Random) -> OutingBeat | None:
    """路上看到一則別人的留言（這一處、不是自己留的、這一趟還沒看過的）：自己寫的比預設句容易抽到 outing_trace_custom 倍。沒有是 None。"""
    shown = {b.ref for b in trip.beats if b.kind == TRACE}
    pool = [i for i in state.world.inscriptions
            if i.place == trip.place and i.author != state.player.name and i.id not in shown]
    if not pool:
        return None
    custom = content.config.jianfa.outing_trace_custom
    item = rng.choices(pool, weights=[1.0 if i.preset else custom for i in pool])[0]
    surface = SURFACES[item.id % len(SURFACES)]
    return OutingBeat(kind=TRACE, text=SEEN_LINE.format(surface=surface, text=item.text, author=item.author), ref=item.id)


def wave_beat(names: list[str], rng: random.Random) -> OutingBeat | None:
    """這一處有別人（「此地還有」那一份名單）：遠處有人揮手。沒有人是 None。"""
    if not names:
        return None
    return OutingBeat(kind=TRACE, text=WAVE_LINE.format(name=rng.choice(sorted(names))))
