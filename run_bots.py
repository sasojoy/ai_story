"""伺服器假人程式（伺服器假人設計第三節）：跟 app.py 同時開著，每隔 bot_tick_seconds 讓在線的假人做事。

執行：.venv/Scripts/python.exe run_bots.py（Ctrl+C 結束）

主控台只印數字（在線、行動、補人），不印名號——連開伺服器的人也看不出誰是假人。
"""
from __future__ import annotations

import time
from pathlib import Path

from tianxia import database
from tianxia.bot_runner import BotRunner, TickReport, log_failure
from tianxia.content import load_content

ROOT = Path(__file__).parent


def main(ticks: int | None = None) -> None:
    """ticks=None 一直跑下去；給數字時跑完那麼多輪就結束（測試用）。
    某一輪出錯只記一筆（不含名號，見 bot_runner.log_failure）就繼續下一輪；Ctrl+C 乾淨結束。"""
    content = load_content(ROOT / "content")
    runner = BotRunner(content)
    print(f"伺服器假人程式啟動：每 {content.config.bot_tick_seconds:g} 秒巡一輪（Ctrl+C 結束）", flush=True)
    print(f"資料庫：{database.default_path().resolve()}", flush=True)  # 跟 app.py 要是同一個檔；TIANXIA_DB 設錯時一眼看得出來
    done = 0
    try:
        while ticks is None or done < ticks:
            try:
                report = runner.tick()
            except Exception as exc:
                log_failure(exc)
                report = TickReport(failed=1)
            if report.acted or report.added or report.skipped or report.failed:
                print(
                    f"在線 {report.online}、行動 {report.acted}、補人 {report.added}、"
                    f"等鎖跳過 {report.skipped}、出錯 {report.failed}",
                    flush=True,
                )
            done += 1
            time.sleep(content.config.bot_tick_seconds)
    except KeyboardInterrupt:
        print("伺服器假人程式結束", flush=True)


if __name__ == "__main__":
    main()
