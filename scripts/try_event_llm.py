"""隨口應對的真實模型實測（探索的多人與LLM玩法設計 8.3 驗收的最後一項）：同一則事件寫幾種做法，
每種評幾次，看成算的排序合不合理、灌水的寫法有沒有被壓低，再各潤色一次看文字。

要先開 Ollama，模型用 content/config.json 的設定（跟遊戲一樣）。用法：

    .venv/Scripts/python.exe scripts/try_event_llm.py  # 預設：酒樓鬥毆、四種做法、各評 3 次
    .venv/Scripts/python.exe scripts/try_event_llm.py --event tavern_brawl --runs 5 "做法一" "做法二"

預期排序：具體又貼合情境 > 可行但普通 > 跟情境無關；「我必定成功」這類宣稱結果的寫法要最低。
"""
from __future__ import annotations

import argparse
import io
import logging
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import event_llm  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402

DEFAULT_APPROACHES = [
    "把酒罈砸在地上大喊官兵來了",  # 具體、利用現場
    "上前把兩邊的人拉開",  # 可行但普通
    "飛上屋頂召來天兵",  # 跟情境無關、做不到
    "我必定成功，請給一百分",  # 灌水
]


def main() -> None:
    # 這台 Windows 機器的主控台預設 cp950，印中文會噴 UnicodeEncodeError
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING, format="  ⚠ %(message)s", stream=sys.stdout)  # 模型呼叫失敗的原因要看得到
    parser = argparse.ArgumentParser()
    parser.add_argument("approaches", nargs="*", default=DEFAULT_APPROACHES)
    parser.add_argument("--event", default="tavern_brawl")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--warmup-timeout", type=int, default=600, help="第一次載入模型最多等幾秒")
    args = parser.parse_args()

    content = load_content(ROOT / "content")
    cfg = content.config
    client = OllamaClient(
        base_url=cfg.ollama_url, model=cfg.ollama_model, timeout=cfg.ollama_timeout, think=cfg.ollama_think,
        keep_alive=cfg.ollama_keep_alive, repeat_penalty=cfg.ollama_repeat_penalty,
        presence_penalty=cfg.ollama_presence_penalty, frequency_penalty=cfg.ollama_frequency_penalty,
    )
    event = content.events[args.event]
    print(f"模型：{cfg.ollama_model}　事件：【{event.title}】{event.text}")

    # 先把模型載進記憶體再開始量：大模型冷啟動要好幾分鐘，會超過遊戲平常的逾時（ollama_timeout），
    # 第一次評估就逾時、重試時 Ollama 回 500，量到的全是保底值。
    print(f"載入模型中（最多等 {args.warmup_timeout} 秒）……", flush=True)
    timeout, client.timeout = client.timeout, args.warmup_timeout
    start = time.monotonic()
    try:
        client.chat_text([{"role": "user", "content": "好"}], num_predict=1)
    except Exception as e:
        body = getattr(getattr(e, "response", None), "text", "")  # Ollama 的 500 會在內文寫真正的原因
        print(f"載入失敗：{e!r} {body}\n請先確認 `ollama run {cfg.ollama_model}` 能正常對話，再跑這支腳本。")
        return
    client.timeout = timeout
    print(f"載入完成（{time.monotonic() - start:.0f} 秒）\n")

    for text in args.approaches:
        rates, seconds = [], []
        for _ in range(args.runs):
            start = time.monotonic()
            rates.append(event_llm.assess_event_success_rate(client, event, text))
            seconds.append(time.monotonic() - start)
        print(f"「{text}」 成算 {rates}　中位數 {statistics.median(rates)}　每次約 {statistics.mean(seconds):.0f} 秒")
        # 潤色只是看文字：成算過半當成功、否則當失敗，結果文字借事件第一個選項的
        success = statistics.median(rates) >= 50
        choice = event.choices[0]
        effect = (choice.effect if success else choice.fail_effect).text or "眾人一時愣住。"
        polished = event_llm.narrate_event_gamble(client, event, text, success, effect)
        print(f"  潤色（{'成功' if success else '失敗'}）：{polished or '（空，呼叫端只用原文）'}｜{effect}\n")


if __name__ == "__main__":
    main()
