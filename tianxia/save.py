"""存讀檔：整個 GameState 直接序列化成 JSON。"""
from __future__ import annotations

from pathlib import Path

from .fileio import retry_sharing
from .state import GameState


def save_game(state: GameState, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(state.model_dump_json(indent=1), encoding="utf-8")
    retry_sharing(lambda: tmp.replace(path))


def load_game(path: Path) -> GameState:
    return GameState.model_validate_json(retry_sharing(lambda: Path(path).read_text(encoding="utf-8")))
