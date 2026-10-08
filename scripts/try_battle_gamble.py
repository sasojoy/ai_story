"""決戰放手一搏的真實模型實測（試玩回饋 2026-10-08）：同一次模型呼叫評成功率、寫成功與失敗兩版劇情，
看成功率排序合不合理、劇情有沒有具體接住玩家寫的內容、有沒有夾數字或簡體字。

要先開 Ollama，模型用 content/config.json 的設定（跟遊戲一樣）。用法：

    .venv/Scripts/python.exe scripts/try_battle_gamble.py              # 預設：Joy 那場的五句、各評 2 次
    .venv/Scripts/python.exe scripts/try_battle_gamble.py --runs 3 "做法一" "做法二"

一行「⚠ 保底」代表模型沒回或回壞了（成功率是 40、劇情空的、畫面會用固定句），那一筆不能拿來判斷模型寫得好不好。
"""
from __future__ import annotations

import argparse
import io
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import battle_instance  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402

JOY_LINES = [  # Joy 那場（2026-10-08）玩家實際寫的五句
    "分兵隱藏起來伺機而動",
    "刺殺主將",
    "屌 可唔可以快少少",
    "扮成絕世美女色誘對面主將",
    "用上火影中的多重影分身之術十萬個分身",
]


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")  # cp950 主控台印中文會噴錯
    logging.basicConfig(level=logging.WARNING, format="  ⚠ %(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser()
    parser.add_argument("lines", nargs="*", default=JOY_LINES)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--battle", default="huangjin_showdown")
    parser.add_argument("--name", default="彩加", help="劇情開頭的名號")
    parser.add_argument("--faction", default="官軍")
    parser.add_argument("--model", help="換一個模型試（預設用 content/config.json 的 ollama_model）")
    parser.add_argument("--warmup-timeout", type=int, default=600, help="第一次載入模型最多等幾秒")
    args = parser.parse_args()

    content = load_content(ROOT / "content")
    cfg = content.config
    client = OllamaClient(
        base_url=cfg.ollama_url, model=args.model or cfg.ollama_model, timeout=cfg.ollama_timeout, think=cfg.ollama_think,
        keep_alive=cfg.ollama_keep_alive, repeat_penalty=cfg.ollama_repeat_penalty,
        presence_penalty=cfg.ollama_presence_penalty, frequency_penalty=cfg.ollama_frequency_penalty,
    )
    act = content.battles[args.battle].acts[0]
    print(f"模型：{client.model}　情境：【{act.title}】{act.text}")
    print(f"載入模型中（最多等 {args.warmup_timeout} 秒）……", flush=True)
    timeout, client.timeout = client.timeout, args.warmup_timeout
    start = time.monotonic()
    try:
        client.chat_text([{"role": "user", "content": "好"}], num_predict=1)
    except Exception as e:
        body = getattr(getattr(e, "response", None), "text", "")
        print(f"載入失敗：{e!r} {body}\n請先確認 `ollama run {client.model}` 能正常對話，再跑這支腳本。")
        return
    client.timeout = timeout
    print(f"載入完成（{time.monotonic() - start:.0f} 秒）\n")

    for text in args.lines:
        print(f"「{text}」")
        for _ in range(args.runs):
            start = time.monotonic()
            verdict = battle_instance.assess_gamble(client, act, args.faction, text, args.name)
            took = time.monotonic() - start
            fallback = verdict.rate == battle_instance.DEFAULT_FREE_TEXT_SUCCESS_RATE and not (verdict.win or verdict.lose)
            print(f"  成功率 {verdict.rate}%（{took:.0f} 秒）{'　⚠ 保底' if fallback else ''}")
            print(f"    成：{verdict.win or '（空，播固定句）'}")
            print(f"    敗：{verdict.lose or '（空，播固定句）'}")
        print()


if __name__ == "__main__":
    main()
