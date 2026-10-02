"""Windows 上兩個程式同時碰同一個檔案時的重試（伺服器假人設計第九節）。

一個程式正開著檔案讀的時候，另一個程式要用新檔換掉它（Path.replace）會丟 PermissionError；
反過來，正在換檔的那一瞬間去讀也可能丟同樣的錯。這是暫時的，稍等一下再試就好。
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

ATTEMPTS = 40
DELAY = 0.025  # 秒；全部重試完大約等 1 秒


def retry_sharing(fn: Callable[[], T]) -> T:
    """呼叫 fn()；遇到 PermissionError（檔案被另一個程式占用）就稍等重試，試完還不行才丟出去。"""
    for attempt in range(ATTEMPTS):
        try:
            return fn()
        except PermissionError:
            if attempt == ATTEMPTS - 1:
                raise
            time.sleep(DELAY)
    raise AssertionError("unreachable")
