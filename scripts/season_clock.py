"""主機端：讓賽季時鐘暫停或繼續（線上架構設計第四節、8.3「公告停機時賽季時鐘暫停，季末跟著往後延」）。

要停很久（大改版、搬電腦）時，關伺服器之前跑 pause、伺服器開回來之後跑 resume：停的那一段不算進賽季，季末往後延；
排好的決戰照原本的現實時間開，原本的時間落在暫停裡的，resume 那一刻就開集結（企劃者 2026-10-06）。跟管理者在設定頁按
「暫停賽季時鐘」「繼續」是同一件事（WorldStateStore.pause_clock、world.resume_season_clock），不用登入；伺服器開著也可以跑（拿同一把行動鎖，一筆交易做完）。resume 要讀內容：設定覆寫檔要跟伺服器同一份
（TIANXIA_PROFILE 或 --profile），不然第一季的季曆與排好的決戰會照錯的設定算。
執行：.venv/Scripts/python.exe scripts/season_clock.py pause|resume|status [--db <資料庫檔>] [--profile weekend]
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import time
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia.content import PROFILE_ENV, load_content, profile_line  # noqa: E402
from tianxia.database import default_path  # noqa: E402
from tianxia.models import Content  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.world import resume_season_clock  # noqa: E402

PHASES = {"preparing": "籌備中", "running": "進行中", "resting": "休季"}


def main(argv: list[str] | None = None, clock: Callable[[], float] = time.time, content: Content | None = None) -> int:
    """content 給了就用它（測試）；沒給時 resume 照 --profile（預設讀 TIANXIA_PROFILE）讀 content/。"""
    parser = argparse.ArgumentParser(description="讓賽季時鐘暫停或繼續（停機維護用）")
    parser.add_argument("action", choices=("pause", "resume", "status"), help="pause 暫停、resume 繼續、status 看現在的狀態")
    parser.add_argument("--db", default=None, help="資料庫檔（預設：環境變數 TIANXIA_DB，沒設就是 saves/tianxia.db）")
    parser.add_argument("--profile", default=os.environ.get(PROFILE_ENV) or None, help="設定覆寫檔，要跟伺服器同一份（預設讀 TIANXIA_PROFILE）")
    args = parser.parse_args(argv)
    path = Path(args.db) if args.db else default_path()
    print(f"資料庫：{path.resolve()}")
    if not path.exists():  # 打錯路徑時不要憑空開一個新的資料庫
        print("找不到這個資料庫檔。")  # 待 S1／joy 潤
        return 1
    if args.action == "resume" and content is None:
        content = load_content(ROOT / "content", profile=args.profile)  # 讀內容很慢：在拿鎖之前讀好
        print(profile_line(content, args.profile))
    world = open_world(path)
    now = clock()
    with world.action_lock():
        phase, at = world.season_phase(), world.paused_at()
        if args.action == "pause":
            if at is not None:
                print(f"賽季時鐘已經停著了（停了 {int((now - at) // 60)} 分鐘）。")  # 待 S1／joy 潤
                return 0
            if not world.pause_clock(now):
                print(f"現在是{PHASES[phase]}，沒有時鐘可以停。")  # 待 S1／joy 潤
                return 1
            print("賽季時鐘停了：季的時間不走、決戰不推，玩家暫時不能行動。伺服器開回來之後跑：season_clock.py resume")  # 待 S1／joy 潤
            return 0
        if args.action == "resume":
            # 跟管理者按「繼續」同一條路（Game.admin_resume_clock）：繼續、補算、開集結三步都在 resume_season_clock，
            # 回傳繼續的那一行、補算的訊息、集結號角（原本的時間落在暫停裡的決戰這一刻開集結），照順序印出來
            lines = resume_season_clock(
                world, content, now, random.Random(),
                "賽季時鐘接著走了（停了 {minutes} 分鐘）；季末往後延一樣長，排好的決戰照原本的時間開。",  # 待 S1／joy 潤
            )
            if lines is None:
                print("賽季時鐘沒有暫停。")  # 待 S1／joy 潤
                return 0
            for line in lines:
                print(line)
            return 0
        clock_text = "在走" if at is None else f"停了 {int((now - at) // 60)} 分鐘"
        print(f"賽季：{PHASES[phase]}；時鐘：{clock_text}。")  # 待 S1／joy 潤
        return 0


if __name__ == "__main__":
    sys.exit(main())
