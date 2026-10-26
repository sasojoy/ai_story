"""人物評曰的真實模型實測（減法季批 7b-2，主機側計畫第十節「批 7b 評曰三條無假名無簡體無數字」）：照正式內容開三張單——
第一階由主將寫（盧植）、情誼七十以上的人物寫（曹操）、買了親筆評曰請的人物寫（朱儁）——各叫一次 zhuan_end.write_verdict，
印模型原樣回的、清過的、花幾秒、有沒有退回固定句。只量不改，不進測試、不開世界。

要先開 Ollama，模型用 content/config.json 的設定（跟遊戲一樣）；這台的 Ollama 同時在給線上伺服器用：跑一次就好，不要迴圈跑。

    .venv/Scripts/python.exe scripts/try_verdicts.py
    .venv/Scripts/python.exe scripts/try_verdicts.py --model qwen2.5:14b   # 換一個模型試（預設照設定）

清過的那一句是空的（模型叫不動、太長、有阿拉伯數字或假名）時印「⚠ 退回固定句」，遊戲裡會用 content/verdicts.json 的句子。
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import zh, zhuan_end  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402

PLAYER = "沈青衫"
ANNALS = (
    {"kind": "deed", "text": "投靠官軍。", "weight": 4},
    {"kind": "showdown", "text": "長社火攻，你站在官軍以先鋒出陣，出手 4 回合，在 12／30 人中排第 3／12。", "weight": 5},
    {"kind": "figure", "figure": "caocao", "text": "跟曹操的情誼到了 80。", "weight": 3},
    {"kind": "figure", "figure": "zhujun", "text": "第一次跟朱儁說上話。", "weight": 2},
    {"kind": "tier", "text": "季末論功，官軍出力排第 1（共 20 人），得第一階「漢室忠良」。", "weight": 5},
)
PROFILE = {"faction": "官軍", "tier": 1, "tier_title": "漢室忠良", "tier_side": "官軍", "final_rank": 1, "final_of": 20, "contrib": 180}
WRITERS = [zhuan_end.Writer("luzhi", zhuan_end.TIER), zhuan_end.Writer("caocao", zhuan_end.AFFINITY),
           zhuan_end.Writer("zhujun", zhuan_end.BOUGHT)]
_KANA = re.compile(r"[぀-ヿㇰ-ㇿ]")


class Watch:
    """記下模型原樣回的那一句與丟的例外（write_verdict 吃掉例外、清不過回空字串，從外面看不出來）。"""

    def __init__(self, client):
        self.client, self.raw, self.failed = client, None, None
        self.timeout = getattr(client, "timeout", 30)

    def chat_structured(self, *args, **kwargs):
        try:
            reply = self.client.chat_structured(*args, **kwargs)
        except Exception as e:  # noqa: BLE001  實測腳本：照原樣丟回去，只是先記下來
            self.failed = e
            raise
        self.raw = getattr(reply, "verdict", None)
        return reply


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    content = load_content(ROOT / "content", "season21")
    if args.model:
        content.config.ollama_model = args.model
    client = OllamaClient.from_config(content.config)
    if client is None:
        print("設定裡沒有開模型（Config.ollama_*）。")
        return
    limit = content.config.jianfa.verdict_chars
    for writer in WRITERS:
        job = zhuan_end.verdict_request(content, writer, PLAYER, "男", ANNALS, PROFILE, 1)
        watch = Watch(client)
        started = time.monotonic()
        text = zhuan_end.write_verdict(watch, job, limit)
        spent = time.monotonic() - started
        print(f"── {job.name}（{writer.reason}）{spent:.1f} 秒")
        print(f"   模型原樣：{watch.raw!r}" + (f"（例外：{watch.failed!r}）" if watch.failed else ""))
        if text:
            simplified = zh.to_traditional(text) != text
            print(f"   清過：{text}（{len(text)} 字；假名 {'有' if _KANA.search(text) else '無'}、簡體 {'有' if simplified else '無'}、"
                  f"數字 {'有' if re.search(r'[0-9０-９]', text) else '無'}）")
        else:
            print(f"   ⚠ 退回固定句：{job.fixed}")
        print(f"   成段：{zhuan_end.apply_verdict(job, text)}")


if __name__ == "__main__":
    main()
