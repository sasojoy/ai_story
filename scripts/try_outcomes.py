"""隨口應對分岔的真實模型實測（減法季批 4，主機側計畫 Task 4-4、第十節「真模型」）：同一則有後果的事件寫幾種做法，每種歸類幾次，
看模型挑的後果對不對、成功率合不合理（引擎再照那一種的屬性與難度夾成真正的成算）。只在主機上跑（要開 Ollama，模型照
content/config.json 的設定，跟遊戲一樣）；開發與測試不跑它，模型一律是假的。用法：

    .venv/Scripts/python.exe scripts/try_outcomes.py  # 預設：人拉犁（yc_wilds_plow）三種寫法、各歸類 3 次
    .venv/Scripts/python.exe scripts/try_outcomes.py --runs 5 "我替他把犁拉完" "跟他聊聊天氣"
    .venv/Scripts/python.exe scripts/try_outcomes.py --event rn_hill_deserter "原地挖坑把他埋了" "替他拔箭敷藥"

預期（整合設計 5.9）：「我替他拉犁」→ labor、「我去搶牛」→ chase、「給他錢」→ give，對不上的（「跟他聊聊天氣」）一律 leave。
歸到最後一種時另外判一次善惡（PM 2026-10-25 第 8 件，event_llm.judge_outcome），也一起印出來。
"""
from __future__ import annotations

import argparse
import collections
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

DEFAULT_EVENT = "yc_wilds_plow"
DEFAULT_APPROACHES = ["我替他拉犁", "我去搶牛", "給他錢"]  # 主機側計畫 Task 4-4：三種寫法各三次


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")  # cp950 主控台印中文會噴錯
    logging.basicConfig(level=logging.WARNING, format="  ⚠ %(message)s", stream=sys.stdout)  # 模型呼叫失敗的原因要看得到
    parser = argparse.ArgumentParser()
    parser.add_argument("approaches", nargs="*", default=DEFAULT_APPROACHES)
    parser.add_argument("--event", default=DEFAULT_EVENT)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--profile", default="season21", help="設定覆寫檔（分岔是 season21、week7 開著的；內容一樣，只影響門檻換算）")
    parser.add_argument("--model", help="換一個模型試（預設用 content/config.json 的 ollama_model）")
    parser.add_argument("--warmup-timeout", type=int, default=600, help="第一次載入模型最多等幾秒")
    args = parser.parse_args()

    content = load_content(ROOT / "content", profile=args.profile)
    cfg = content.config
    event = content.events[args.event]
    outcomes = event.free_text.outcomes if event.free_text is not None else []
    if not outcomes:
        print(f"【{event.title}】沒有寫分岔的後果（free_text.outcomes），換一則事件。")
        return
    client = OllamaClient(
        base_url=cfg.ollama_url, model=args.model or cfg.ollama_model, timeout=cfg.ollama_timeout, think=cfg.ollama_think,
        keep_alive=cfg.ollama_keep_alive, repeat_penalty=cfg.ollama_repeat_penalty,
        presence_penalty=cfg.ollama_presence_penalty, frequency_penalty=cfg.ollama_frequency_penalty,
    )
    print(f"模型：{client.model}　事件：【{event.title}】{event.text}")
    print("可能的走向：" + "；".join(f"{o.id}（{o.tag}）" for o in outcomes))

    # 先把模型載進記憶體再開始量（同 try_event_llm.py：冷啟動會超過 ollama_timeout，量到的全是保底值）
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

    for text in args.approaches:
        picked, rates, morals, seconds = collections.Counter(), [], [], []
        for _ in range(args.runs):
            start = time.monotonic()
            verdict = event_llm.judge_outcome(client, event, outcomes, text)
            seconds.append(time.monotonic() - start)
            picked[verdict.outcome] += 1
            rates.append(verdict.rate)
            morals.append(verdict.moral)
        spread = f"±{statistics.pstdev(rates):.0f}" if len(rates) > 1 else ""
        kinds = "、".join(f"{oid}×{n}" for oid, n in picked.most_common())
        print(f"「{text}」→ {kinds}　成功率 {rates}（平均 {statistics.mean(rates):.0f}{spread}）"
              f"　善惡 {morals}　每次 {statistics.mean(seconds):.1f} 秒")


if __name__ == "__main__":
    main()
