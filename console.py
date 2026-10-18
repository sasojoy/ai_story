"""主控台輸出的編碼（server.py、run_bots.py 啟動時第一件事）。

Windows 的主控台與重導向後的 log 預設是系統的 cp950：中文印得出來，但只要有一個 cp950 沒有的字，
`print` 就丟 `UnicodeEncodeError` **把整個程式弄死**。2026-10-18 實際踩到：設定（TIANXIA_PROFILE）
沒帶到時，兩個程式要印 `calendar.PROFILE_MISMATCH` 那行開頭的 `⚠`，結果不是看到警告，而是伺服器與
假人啟動即崩——該提醒人「設定帶錯了」的那一行，自己變成了當機的原因。

所以輸出一律改成 UTF-8（`errors="replace"`：真的還有編不出來的字就寫成 `?`，不要再因為一個字停機）。
副作用是 log 固定是 UTF-8，不必再靠外面設 `PYTHONIOENCODING`，主機端操作文件寫的
`Get-Content server_out.log -Encoding UTF8` 從此一定對。

只碰 stdout／stderr 的編碼，不碰任何遊戲狀態；`tianxia/` 是純規則引擎，這種主控台的事放在它外面。
"""
from __future__ import annotations

import io
import sys


def use_utf8() -> None:
    """把 stdout／stderr 換成 UTF-8。換不動就原樣留著（例如測試把它換成自己的物件）。"""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:  # 一般的情形：真的主控台或重導向的檔
            try:
                reconfigure(encoding="utf-8", errors="replace")
                continue
            except (ValueError, OSError):
                pass
        buffer = getattr(stream, "buffer", None)
        if buffer is not None:  # 退路：自己包一層（CLAUDE.md 給臨時腳本的寫法）
            try:
                setattr(sys, name, io.TextIOWrapper(buffer, encoding="utf-8", errors="replace", line_buffering=True))
            except (ValueError, OSError):
                pass
