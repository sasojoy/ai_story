"""世界記事（Joy 2026-10-29「讓整個世界活起來」：「你做的事會被世界記住、有人回應」；設計稿
https://claude.ai/artifact/LFooPvhRw5NHosh3wDUKRV 第三節；數字在 Config.plans）。

引擎記下「誰、在哪、做了什麼」（WorldState.deeds，全服共用、換季整個重來），之後拿出來用：
- 人物對話（prompt_lines，figure_life.prompt_lines 接在後面）：跟玩家有關、跟這位人物有關的那幾筆，模型可以自然地提起；
- 此地舊事（at_place）：江湖頁場景底下列這裡最近的幾筆。
章回主線也讀寫同一份（kind chapter；它讀 plan、figure_fell 換下一回的交代人與地點）。
只 import models、state、calendar（延後）；plans、figure_life、engine 呼叫它。"""
from __future__ import annotations

from .models import Content
from .state import Deed, GameState

PROMPT_HEAD = "【江湖上記得的事】"  # 對話提示那一段的開頭


def on(content: Content) -> bool:
    return content.config.plans.enabled


def record(state: GameState, content: Content, kind: str, text: str, *, place: str | None = None,
           figures: list[str] | None = None, actors: list[str] | None = None, side: str | None = None) -> Deed | None:
    """記一筆（開關關著什麼都不記，回 None）。舊的照 deeds_keep 丟。"""
    if not on(content):
        return None
    w = state.world
    w.deed_seq += 1
    deed = Deed(id=w.deed_seq, kind=kind, text=text, place=place, figures=list(figures or []), actors=list(actors or []),
                side=side, time=w.time)
    w.deeds.append(deed)
    del w.deeds[:-content.config.plans.deeds_keep]
    return deed


def _key(name: str) -> str:
    return name.casefold()


def mine(state: GameState, name: str) -> list[Deed]:
    """名號 name 出過力的那幾筆（舊的在前）。"""
    key = _key(name)
    return [d for d in state.world.deeds if any(_key(a) == key for a in d.actors)]


def about(state: GameState, content: Content, cid: str) -> list[Deed]:
    """這位人物會記得的、玩家出過力的事：跟他有關（他在 figures 裡），最新的 deeds_prompt 筆。"""
    n = content.config.plans.deeds_prompt
    if not on(content) or not n:
        return []
    return [d for d in mine(state, state.player.name) if cid in d.figures][-n:]


def prompt_lines(state: GameState, content: Content, cid: str) -> str:
    """對話提示多的一行：玩家替他（或跟他作對）做過的事。沒有是空的。"""
    found = about(state, content, cid)
    if not found:
        return ""
    ch = content.characters.get(cid)
    name = ch.name if ch is not None else cid
    return f"{PROMPT_HEAD}{'；'.join(d.text for d in found)}（這些事玩家都出過力，{name}知道；可以自然地提起，不必每句都提）\n"


def at_place(state: GameState, content: Content, loc: str | None) -> list[Deed]:
    """此地舊事：發生在 loc 的最新 deeds_place 筆（新的在前）。"""
    n = content.config.plans.deeds_place
    if not on(content) or not n or loc is None:
        return []
    return [d for d in reversed(state.world.deeds) if d.place == loc][:n]
