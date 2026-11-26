"""客服單到期刪除（隱私權條款第二條「客服單……結案後 1 年」；Config.support.purge_days 預設 365）。

- purge_once：旁檔在才做（不建檔）；store.purge 刪列（同一筆交易）之後，再刪那幾張單的截圖資料夾 files_dir/<單號>/。
  不看 support.enabled：關掉客服不等於不用守條款。
- start：伺服器啟動時（只有 server.main 經 threads 掛鉤叫）開一條 daemon 執行緒，先刪一次，之後每 CHECK_SECONDS 一次；測試設 STOP 停。
已經貼到 Discord #客服 的訊息不在這裡（橋不記訊息 id，要人工清頻道，見 README）；備份檔裡的舊單也不在這裡。"""
from __future__ import annotations

import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from . import rules, store

CHECK_SECONDS = 6 * 3600.0  # 一天看四次就夠：到期差幾小時沒關係，重開伺服器也會先看一次
STOP = threading.Event()


def purge_once(db_path: Path, now: float, days: int) -> list[int]:
    """刪到期的單，回單號。旁檔不在回 []。"""
    sidecar = store.open_store(store.store_path(db_path), create=False)
    if sidecar is None:
        return []
    ids = sidecar.purge(now, days * rules.DAY_SECONDS)
    folder = store.files_dir(db_path)
    for tid in ids:
        shutil.rmtree(folder / str(tid), ignore_errors=True)
    return ids


def start(db_path: Callable[[], Path], clock: Callable[[], float], days: int, *, interval: float = CHECK_SECONDS,
          stop: threading.Event = STOP, warn: Callable[[str], None] = print) -> threading.Thread:
    """開看守：先刪一次，之後每 interval 秒一次；一輪出錯印一行、不停。"""

    def loop() -> None:
        while True:
            try:
                ids = purge_once(db_path(), clock(), days)
                if ids:
                    warn(f"客服單到期刪除：{len(ids)} 張（結案超過 {days} 天）")
            except Exception as e:  # noqa: BLE001  看守不能因為一輪出錯就停
                warn(f"客服單到期刪除這一輪失敗：{e!r}")
            if stop.wait(interval):
                return

    thread = threading.Thread(target=loop, daemon=True, name="support-purge")
    thread.start()
    return thread
