"""決戰放手一搏的負載實測（Joy 2026-10-13「這是我們效能問題，我們應該要做到能承受而不是把自己的功能閹割」）：
二十人同一回合各搏一次，每一個都要在回合結算前（round_seconds）評到成功率。評分只回成功率（battle_instance.score_gamble），
劇情等回合結算後一整回合批給模型寫一次（write_tales）。這支量三樣：
  1. 熱機後單一一次評分要幾秒；
  2. N 次評分一個接一個（佇列一次只放一件時，二十人排隊的樣子）總共幾秒，跟 round_seconds 比；
  3. 一整回合 N 搏的劇情一次寫完要幾秒、寫出幾句能用的。
--parallel K 改成 K 件同時送（模型佇列 llm_queue_slots＝K、Ollama 的 OLLAMA_NUM_PARALLEL 也要開到 K 才有意義）。

要先開 Ollama，模型用 content/config.json 的設定（跟遊戲一樣）。用法：

    .venv/Scripts/python.exe scripts/measure_gamble_load.py                 # 二十句，一個接一個
    .venv/Scripts/python.exe scripts/measure_gamble_load.py --count 30 --parallel 2

一行「⚠ 保底」代表那一次模型沒回或回壞了（成功率是 40），不能拿來當評到了。
"""
from __future__ import annotations

import argparse
import io
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import battle_instance  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402

LINES = [  # Joy 那場（2026-10-08）的五句，加上各種寫法湊滿二十句
    "分兵隱藏起來伺機而動", "刺殺主將", "屌 可唔可以快少少", "扮成絕世美女色誘對面主將", "用上火影中的多重影分身之術十萬個分身",
    "火燒糧草", "夜襲敵營", "擂鼓助威", "放冷箭射旗手", "挖地道繞到後方",
    "假裝投降再反咬一口", "請天兵天將下凡", "帶十個人衝陣", "斷他們的水源", "在上風處撒石灰",
    "大喊援軍到了", "背水一戰", "生擒黃巾渠帥", "騎馬繞到側翼", "裝死等他們走近",
]
NAMES = ["彩加", "沈青", "陸乙", "韓甲", "柳風", "石岩", "白芷", "雲歸", "江寒", "葉秋",
         "林泉", "顧遠", "蘇木", "秦川", "楚歌", "燕回", "孟章", "季白", "溫言", "方圓"]


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")  # cp950 主控台印中文會噴錯
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20, help="一回合幾個人放手一搏")
    parser.add_argument("--parallel", type=int, default=1, help="同時送幾件（模型佇列的 llm_queue_slots）")
    parser.add_argument("--battle", default="huangjin_showdown")
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
    definition = content.battles[args.battle]
    act = definition.acts[0]
    print(f"模型：{client.model}　一回合 {definition.round_seconds} 秒　{args.count} 人放手一搏、同時送 {args.parallel} 件")
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

    # 1. 熱機後單一一次
    singles = []
    for text in LINES[:3]:
        start = time.monotonic()
        battle_instance.score_gamble(client, act, "官軍", text, NAMES[0])
        singles.append(time.monotonic() - start)
    print(f"熱機後單一一次評分：{statistics.median(singles):.1f} 秒（三次 {'／'.join(f'{t:.1f}' for t in singles)}）")

    # 2. 一整回合的評分排隊
    texts = [(NAMES[i % len(NAMES)], LINES[i % len(LINES)]) for i in range(args.count)]
    started = time.monotonic()
    done_at: list[float] = []

    def score(item: tuple[str, str]) -> int:
        name, text = item
        rate = battle_instance.score_gamble(client, act, "官軍", text, name)
        done_at.append(time.monotonic() - started)
        return rate

    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        rates = list(pool.map(score, texts))
    total = time.monotonic() - started
    fallbacks = sum(r == battle_instance.DEFAULT_FREE_TEXT_SUCCESS_RATE for r in rates)
    print(f"{args.count} 次評分總共：{total:.1f} 秒（一回合 {definition.round_seconds} 秒的 {total / definition.round_seconds:.0%}）；"
          f"最後一個人等了 {max(done_at):.1f} 秒" + (f"　⚠ 保底 {fallbacks} 次" if fallbacks else ""))
    for (name, text), rate in zip(texts, rates):
        print(f"  {name}「{text}」 {rate}%")

    # 3. 回合結算後一整回合的劇情（一次批完，最多 TALE_BATCH 搏一批）
    items = [
        battle_instance.TaleItem(name=name, faction_name="官軍", text=text, won=rate >= 50)
        for (name, text), rate in zip(texts, rates)
    ]
    print()
    for start_at in range(0, len(items), battle_instance.TALE_BATCH):
        batch = items[start_at:start_at + battle_instance.TALE_BATCH]
        start = time.monotonic()
        stories = battle_instance.write_tales(client, act, batch)
        took = time.monotonic() - start
        print(f"一批 {len(batch)} 搏的劇情：{took:.1f} 秒，寫出 {len(stories)} 句能用的")
        for item in batch:
            print(f"  {'成' if item.won else '敗'} {stories.get(item.name, '（空，播固定句）')}")


if __name__ == "__main__":
    main()
