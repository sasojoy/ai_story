"""易名帖改名之後（sqlite_world.rename_character 那一筆交易 COMMIT 之後）要跟著換名號的小檔（帖友書信 features/mail 第一個用）。
資料庫交易管不到資料庫旁邊的 sqlite 小檔，核心又不能 import 功能包：包在載入時登記一支 (資料庫檔路徑, 舊 key, 新 key)，這裡照登記的先後叫。
叫的時候丟例外不擋改名（名號已經換好了；小檔換不成只是那幾封信對不上人），印出來就繼續。"""
from __future__ import annotations

import traceback
from collections.abc import Callable
from pathlib import Path

AFTER: list[Callable[[Path, str, str], None]] = []


def register(fn: Callable[[Path, str, str], None]) -> None:
    if fn not in AFTER:
        AFTER.append(fn)


def run(db_path: Path, old: str, new: str) -> None:
    for fn in list(AFTER):
        try:
            fn(Path(db_path), old, new)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
