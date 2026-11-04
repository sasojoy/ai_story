"""畫坊程式（功能包 looks 的 studio.py；Joy 2026-11-01「一步到位」）：跟 server.py、run_bots.py 同時開著，每隔一陣子看有沒有等圖的訂單
（一句話自創絕招要畫的法相、巨物；自建形象的定裝照與十張），叫 Nano Banana 畫、去背切格、叫 Claude 審，不過照意見重畫，最多三張；
過了收下（到齊了變待審，管理者上架）。

執行（主機）：.venv/Scripts/python.exe -u run_studio.py
- 先裝：.venv/Scripts/python.exe -m pip install -r requirements-studio.txt
- 金鑰只設在主機的環境變數：GEMINI_API_KEY（生圖）、ANTHROPIC_API_KEY（審圖）。
- TIANXIA_STUDIO_BACKEND：生圖走哪一家。gemini（預設，Nano Banana）或 local（這台的 ComfyUI 跑 FLUX.2 klein，
  見 tianxia/features/looks/studio_local.py）。本機生圖不要錢，所以重畫上限自己帶（10，雲端是 3）、不看每日張數。
- 走 local 時**只在省電模式開著時動工**（klein 要 9～10 GiB，gemma4:12b 要 9.1 GiB，這張卡放不下兩個；
  省電模式的小模型沒人講話就不佔卡，klein 等於獨佔）。`--anytime` 可以蓋過去，自己看著辦。
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
from tianxia import database, power_save
from tianxia.content import env_profile, load_content, profile_line
from tianxia.features.looks import actions, cutting, studio
from tianxia.features.looks.studio_api import ClaudeCritic, GeminiPainter
from tianxia.sqlite_world import open_world

BACKEND_ENV = "TIANXIA_STUDIO_BACKEND"

ROOT = Path(__file__).parent


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


def _painter(argv: list[str]):
    """生圖走哪一家：環境變數 TIANXIA_STUDIO_BACKEND（gemini／local），或 --local／--gemini。"""
    want = "local" if "--local" in argv else "gemini" if "--gemini" in argv else (os.environ.get(BACKEND_ENV, "") or "gemini").lower()
    if want == "local":
        from tianxia.features.looks.studio_local import LocalPainter  # noqa: PLC0415  只有走本機才 import

        return LocalPainter(), True
    return GeminiPainter(), False


def main(argv: list[str]) -> int:
    console.use_utf8()
    once, anytime = "--once" in argv, "--anytime" in argv
    profile = env_profile()
    content = load_content(ROOT / "content", profile=profile)
    store = open_world()
    root = actions.images_beside(store.db.path)
    painter, local = _painter(argv)
    critic = ClaudeCritic()
    tries = int(getattr(painter, "tries", studio.MAX_TRIES))
    fresh = bool(getattr(painter, "fresh_retries", False))  # 本機 klein：沒過就重新畫，不照意見改上一張（studio_local）
    daily = 0 if local else _int_env("TIANXIA_STUDIO_DAILY", 80)  # 本機生圖不要錢，不設每日上限
    seconds = _int_env("TIANXIA_STUDIO_SECONDS", 30) or 30
    gate = local and not anytime  # 本機生圖要跟遊戲搶同一張卡：只在省電模式動工
    print(f"畫坊啟動：生圖 {painter.model}、審圖 {critic.model}；一張最多畫 {tries} 次（{'沒過重新畫' if fresh else '沒過照意見改'}）；"
          + (f"一天最多畫 {daily} 張；" if daily else "不限每日張數；")
          + (f"只在省電模式動工；" if gate else "")
          + f"每 {seconds} 秒巡一輪（Ctrl+C 結束）", flush=True)
    print(f"資料庫：{database.default_path().resolve()}；圖：{root}", flush=True)
    print(profile_line(content, profile), flush=True)
    day, spent, waiting = datetime.date.today(), 0, False
    try:
        while True:
            if datetime.date.today() != day:
                day, spent = datetime.date.today(), 0
            if gate and not power_save.on():
                if not waiting:  # 只印一次，不要每 30 秒洗一行
                    print("省電模式關著，畫坊先停手（顯卡讓給遊戲的模型；--anytime 可以不理這條）", flush=True)
                    waiting = True
            elif not daily or spent + tries <= daily:
                if waiting:
                    print("省電模式開了，畫坊接著做", flush=True)
                    waiting = False
                try:
                    before = _painted(store)
                    for line in studio.tick(content, store, root, actions.WEB_IMG, painter, critic,
                                            lambda job, raw: studio.cut_for(job, _matted(painter, job, raw), cutting),
                                            tries=tries, fresh=fresh):
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


def _matted(painter, job, raw: bytes) -> bytes:
    """法相、巨物那一張（kind "move"）走本機生圖時，先讓 BiRefNet 產一次前景遮罩再切。

    為什麼只給這一張：擂台那十六張的去背是照白底算的、已經校準過（而且有定裝照可以判 wears_white 豁免），
    而法相沒有可比的參考圖，白底法分不開「圍起來的那一塊白」與「主體本身的白」（量過 16 張都分不開）。
    這裡刻意不動 Painter 的介面（雲端那支與所有測試假人都吃 paint(prompt, images, aspect, size)）：
    有 matte 才叫，沒有就照舊。遮罩那一步自己會在失敗時原樣回傳。
    """
    if job.kind != "move":
        return raw
    fn = getattr(painter, "matte", None)
    return fn(raw) if callable(fn) else raw


def _painted(store) -> int:
    """全部訂單畫坊叫過幾次生圖（記在訂單上的，算今天花了多少用）。"""
    with store.db.snapshot() as conn:
        rows = conn.execute("SELECT data FROM mall_purchases WHERE data LIKE '%\"studio\"%'").fetchall()
    import json  # noqa: PLC0415

    return sum(int((json.loads(r["data"]).get("studio") or {}).get("painted", 0)) for r in rows)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
