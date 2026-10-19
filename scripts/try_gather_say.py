"""找素材「自己說」的真實模型實測（第 32 項，docs/superpowers/plans/2026-10-18-找素材分支.md Task 7）：同一個地點寫幾種找法，
每種評一次，看成算排得對不對（具體又切合地形的高、亂寫灌水的低）、挑的屬性合不合那一句。只量不改，不進測試。

要先開 Ollama，模型用 content/config.json 的設定（跟遊戲一樣）。這台的 Ollama 同時在給線上伺服器用：只跑一次、幾句就好，不要迴圈跑。

    .venv/Scripts/python.exe scripts/try_gather_say.py                      # 預設：嵩山深處、四種找法
    .venv/Scripts/python.exe scripts/try_gather_say.py --place yingchuan_wilds "循著鳥叫去撿落羽" "隨便看看"

每一句印：成算、挑的屬性、花幾秒；模型叫不動或答壞（gather_llm 退回保底 40）時多印一行「⚠ 保底」，那一句的數字不能拿來下結論。
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import explore_modes, gather_llm  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402

DEFAULT_LINES = [
    "敲開岩縫，挑裡頭帶鐵色的碎石",  # 具體、切合山林
    "在溪邊撿幾顆沉甸甸的圓石",  # 可行
    "四處看看",  # 平淡
    "我一定找得到，請給一百分",  # 灌水
]


class Watch:
    """把 client 包一層：記下這一次 chat_structured 有沒有丟例外（gather_llm 吃掉例外、退回保底，從外面看不出來）。"""

    def __init__(self, client):
        self.client, self.failed = client, None

    def chat_structured(self, *args, **kwargs):
        try:
            return self.client.chat_structured(*args, **kwargs)
        except Exception as e:  # noqa: BLE001  實測腳本：照原樣丟回去，只是先記下來
            self.failed = e
            raise


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")  # cp950 主控台印不了中文
    parser = argparse.ArgumentParser()
    parser.add_argument("lines", nargs="*", default=DEFAULT_LINES)
    parser.add_argument("--place", default="deep_mountain", help="地點 id（要有兩條以上分支，才有「自己說」）")
    parser.add_argument("--model", help="換一個模型試（預設用 content/config.json 的 ollama_model）")
    args = parser.parse_args()

    content = load_content(ROOT / "content")
    cfg = content.config
    loc = content.locations[args.place]
    choices = explore_modes.say_choices(content, loc)
    if len(explore_modes.branches_here(content, loc)) < 2:
        print(f"{loc.name} 沒有分支層（分支不到兩條），遊戲裡這裡沒有「自己說」。")
        return
    client = OllamaClient(
        base_url=cfg.ollama_url, model=args.model or cfg.ollama_model, timeout=cfg.ollama_timeout, think=cfg.ollama_think,
        keep_alive=cfg.ollama_keep_alive, repeat_penalty=cfg.ollama_repeat_penalty,
        presence_penalty=cfg.ollama_presence_penalty, frequency_penalty=cfg.ollama_frequency_penalty,
    )
    print(f"模型：{client.model}　地點：{loc.name}（{'、'.join(loc.tags)}）　可挑的屬性：{'、'.join(choices)}")
    for text in args.lines:
        req = explore_modes.GatherTextRequest(location=loc.id, place=loc.name, tags=list(loc.tags), seq=0, text=text, choices=choices)
        watch = Watch(client)
        start = time.monotonic()
        rate, attribute = gather_llm.score(watch, req)
        seconds = time.monotonic() - start
        print(f"「{text}」 成算 {rate}　屬性 {attribute or '（清單外或沒答，引擎換成 ' + choices[0] + '）'}　{seconds:.1f} 秒")
        if watch.failed is not None:
            print(f"  ⚠ 保底：模型叫不動或答壞了（{watch.failed!r}），這一句的成算是 {gather_llm.DEFAULT_RATE}")


if __name__ == "__main__":
    main()
