"""宴席「讀」的那一半（全部拆包第 40 批：宴客包 features/feast/rules.py 的 on、find、is_open、open_feasts、hosting、toasted、_key
原樣搬來，包 re-export 同一批）：人物活起來 figure_life（共用規則層）的行事先問誰在擺宴、書信的邀宴問開著的宴，不 import 宴客包。
只讀 WorldState.feasts（宴客包認領）與 PlayerState 的名號，不寫；設宴（寫）是世界層 life 那一格（宴客包登記，core/features.py 的
WORLD_ORDER）。核心本體（tianxia/core/ 底下的檔），不進 MODULES。"""
from __future__ import annotations

from ..models import Content
from ..state import Feast, GameState


def on(content: Content) -> bool:
    from .. import figure_life  # noqa: PLC0415  figure_life 最外層 import 這裡（共用規則層），反過來延後
    return figure_life.on(content) and content.config.figure_life.feasts


def find(state: GameState, feast_id: int | None) -> Feast | None:
    return next((f for f in state.world.feasts if f.id == feast_id), None) if feast_id is not None else None


def is_open(state: GameState, f: Feast) -> bool:
    return not f.settled and f.start <= state.world.time < f.end


def open_feasts(state: GameState) -> list[Feast]:
    return [f for f in state.world.feasts if is_open(state, f)]


def hosting(state: GameState, cid: str) -> Feast | None:
    """cid 此刻在擺的那一場（擺宴的人不走動：figure_life._act 先問它）。"""
    return next((f for f in open_feasts(state) if f.host == cid), None)


def toasted(state: GameState, f: Feast) -> bool:
    key = _key(state.player.name)
    return any(_key(t.name) == key for t in f.toasts)


def _key(name: str) -> str:
    return name.casefold()
