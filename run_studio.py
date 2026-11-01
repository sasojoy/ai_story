"""畫坊程式（功能包 looks 的 studio.py；Joy 2026-11-01「一步到位」）：跟 server.py、run_bots.py 同時開著，每隔一陣子看有沒有等圖的訂單
（一句話自創絕招要畫的法相、巨物；自建形象的定裝照與十張），叫 Nano Banana 畫、去背切格、叫 Claude 審，不過照意見重畫，最多三張；
過了收下（到齊了變待審，管理者上架）。

執行（主機）：.venv/Scripts/python.exe -u run_studio.py
- 先裝：.venv/Scripts/python.exe -m pip install -r requirements-studio.txt
- 金鑰只設在主機的環境變數：GEMINI_API_KEY（生圖）、ANTHROPIC_API_KEY（審圖）。
- 資料庫同 server.py（TIANXIA_DB；沒設是 saves/tianxia.db），圖放在資料庫旁邊的 looks/。
- TIANXIA_STUDIO_DAILY：一天最多叫幾次生圖（預設 80；到了就停到隔天，免得出錯時一直燒錢）。
- TIANXIA_STUDIO_SECONDS：幾秒巡一輪（預設 30）。
- --once：巡一輪就結束（試的時候用）。

伺服器那邊要設 TIANXIA_LOOK_GEN=api（管理者頁寫「畫坊自動畫」；不設也照樣會畫，只是頁面上寫等上傳）。
主控台只印訂單編號與哪一張，不印玩家名號、不印金鑰。
"""
from __future__ import annotations

import datetime
import os
import sys
import time
from pathlib import Path

import console
from tianxia import database
from tianxia.content import env_profile, load_content, profile_line
from tianxia.features.looks import actions, cutting, studio
from tianxia.features.looks.studio_api import ClaudeCritic, GeminiPainter
from tianxia.sqlite_world import open_world

ROOT = Path(__file__).parent


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


def main(argv: list[str]) -> int:
    console.use_utf8()
    once = "--once" in argv
    profile = env_profile()
    content = load_content(ROOT / "content", profile=profile)
    store = open_world()
    root = actions.images_beside(store.db.path)
    painter, critic = GeminiPainter(), ClaudeCritic()
    daily, seconds = _int_env("TIANXIA_STUDIO_DAILY", 80), _int_env("TIANXIA_STUDIO_SECONDS", 30) or 30
    print(f"畫坊啟動：生圖 {painter.model}、審圖 {critic.model}；一天最多畫 {daily} 張；每 {seconds} 秒巡一輪（Ctrl+C 結束）", flush=True)
    print(f"資料庫：{database.default_path().resolve()}；圖：{root}", flush=True)
    print(profile_line(content, profile), flush=True)
    day, spent = datetime.date.today(), 0
    try:
        while True:
            if datetime.date.today() != day:
                day, spent = datetime.date.today(), 0
            if spent + studio.MAX_TRIES <= daily:
                try:
                    before = _painted(store)
                    for line in studio.tick(content, store, root, actions.WEB_IMG, painter, critic,
                                            lambda job, raw: studio.cut_for(job, raw, cutting)):
                        print(line, flush=True)
                    spent += max(0, _painted(store) - before)
                except Exception as exc:  # 一輪出錯只記一筆就繼續（同 run_bots）
                    print(f"畫坊這一輪出錯：{type(exc).__name__}：{exc}", flush=True)
            if once:
                return 0
            time.sleep(seconds)
    except KeyboardInterrupt:
        print("畫坊結束", flush=True)
        return 0


def _painted(store) -> int:
    """全部訂單畫坊叫過幾次生圖（記在訂單上的，算今天花了多少用）。"""
    with store.db.snapshot() as conn:
        rows = conn.execute("SELECT data FROM mall_purchases WHERE data LIKE '%\"studio\"%'").fetchall()
    import json  # noqa: PLC0415

    return sum(int((json.loads(r["data"]).get("studio") or {}).get("painted", 0)) for r in rows)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
