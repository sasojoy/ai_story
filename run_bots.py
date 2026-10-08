"""伺服器假人程式（伺服器假人設計第三節）：跟 server.py 同時開著，每隔 bot_tick_seconds 讓在線的假人做事。

執行：.venv/Scripts/python.exe run_bots.py（Ctrl+C 結束）

主控台只印數字（在線、行動、補人、等鎖跳過、出錯、取名），不印名號——連開伺服器的人也看不出誰是假人。
模型：假人鎖內的 Game 沒有 client；首創配方與絕學定名的取名在鎖外、用這支程式自己的 client（bot_runner._name_and_apply）。
"""
from __future__ import annotations

import time
from pathlib import Path

from tianxia import database
from tianxia.bot_runner import BotRunner, TickReport, log_failure
from tianxia.content import env_profile, load_content, profile_line
from tianxia.ollama_client import OllamaClient

ROOT = Path(__file__).parent


def main(ticks: int | None = None) -> None:
    """ticks=None 一直跑下去；給數字時跑完那麼多輪就結束（測試用）。
    某一輪出錯只記一筆（不含名號，見 bot_runner.log_failure）就繼續下一輪；Ctrl+C 乾淨結束。"""
    profile = env_profile()  # 跟 server.py 用同一份設定覆寫檔（TIANXIA_PROFILE）
    content = load_content(ROOT / "content", profile=profile)
    # 假人只在鎖外替首創的配方與絕學定名請模型取名（見 bot_runner._name_and_apply）；bot_naming 關著就不給 client
    client = OllamaClient.from_config(content.config) if content.config.bot_naming else None
    runner = BotRunner(content, client=client)
    print(f"伺服器假人程式啟動：每 {content.config.bot_tick_seconds:g} 秒巡一輪（Ctrl+C 結束）", flush=True)
    print(f"資料庫：{database.default_path().resolve()}", flush=True)  # 跟 server.py 要是同一個檔；TIANXIA_DB 設錯時一眼看得出來
    print(profile_line(content, profile), flush=True)
    done = 0
    try:
        while ticks is None or done < ticks:
            try:
                report = runner.tick()
            except Exception as exc:
                log_failure(exc)
                report = TickReport(failed=1)
            if report.acted or report.added or report.skipped or report.failed or report.named:
                print(
                    f"在線 {report.online}、行動 {report.acted}、補人 {report.added}、"
                    f"等鎖跳過 {report.skipped}、出錯 {report.failed}、取名 {report.named}",
                    flush=True,
                )
            done += 1
            time.sleep(content.config.bot_tick_seconds)
    except KeyboardInterrupt:
        print("伺服器假人程式結束", flush=True)


if __name__ == "__main__":
    main()
