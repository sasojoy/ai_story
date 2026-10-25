"""事件旁白每週改寫的真實模型實測（減法季整合設計第十章，批 10）：拿這一季會改寫的事件，一則一則叫 narration.write，印原文、改寫、
花幾秒、有沒有過 narration.clean（過不了印原因）。只量不改：不開世界、不寫資料庫、不寫改寫的小檔，不進測試。

要先開 Ollama，模型用 content/config.json 的設定（跟遊戲一樣）。這台的 Ollama 同時在給線上伺服器用：先試幾則，看品質再決定要不要跑整週。

    .venv/Scripts/python.exe scripts/try_narration.py                 # 預設十則（照 id 排的前十則）
    .venv/Scripts/python.exe scripts/try_narration.py -n 30 --random  # 隨機挑三十則
    .venv/Scripts/python.exe scripts/try_narration.py --all           # 整週（約兩百六十則，一則十來秒，約一個小時）
    .venv/Scripts/python.exe scripts/try_narration.py --event <事件id> --model qwen2.5:14b
    .venv/Scripts/python.exe scripts/try_narration.py --all --out narration_week.txt  # 全文另存一份，慢慢看

最後一行是總計：寫成幾則、退回原文幾則（各是什麼原因）、平均幾秒。退回的比例高，先看原因再調 narration.SYSTEM 或過濾。
"""
from __future__ import annotations

import argparse
import io
import os
import random
import re
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TIANXIA_DB", str(Path(tempfile.mkdtemp(prefix="try-narration-")) / "tianxia.db"))  # 不碰這份 clone 的 saves/

from tianxia import narration, zh  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402


class Watch:
    """把 client 包一層：記下模型原樣回的字與丟的例外（narration.write 吃掉例外、過不了 clean 回 None，從外面看不出來）。"""

    def __init__(self, client):
        self.client, self.raw, self.failed = client, None, None

    def chat_text(self, *args, **kwargs):
        self.raw, self.failed = None, None
        try:
            self.raw = self.client.chat_text(*args, **kwargs)
        except Exception as e:  # noqa: BLE001  實測腳本：照原樣丟回去，只是先記下來
            self.failed = e
            raise
        return self.raw


def why_not(content, original: str, raw: str) -> str:
    """過不了 clean 的原因（照 clean 的順序再走一次，只為了印給人看）。"""
    out = zh.to_traditional(str(raw or "")).strip()
    out = re.sub(r"^[#>*\-\s]+", "", out, flags=re.MULTILINE)
    out = "".join(p.strip() for p in re.sub(r"[*_`#]", "", out).split("\n") if p.strip())
    if not out:
        return "空的"
    if out == original:
        return "一字沒改"
    ratio = len(out) / max(1, len(original))
    if not (narration.MIN_RATIO <= ratio <= narration.MAX_RATIO):
        return f"長度 {ratio:.2f} 倍"
    if sorted(narration._MARKS.findall(out)) != sorted(narration._MARKS.findall(original)):
        return "標記不對"
    bare = narration._MARKS.sub("", out)
    if narration._DIGITS.findall(bare) != narration._DIGITS.findall(narration._MARKS.sub("", original)):
        return "數字"
    if narration._KANA.search(bare):
        return "假名"
    if narration._LATIN.search(bare):
        return "英文字母"
    extra = [n for n in narration._names(content) if n in out and n not in original]
    if extra:
        return f"冒出原文沒有的名字：{'、'.join(extra[:3])}"
    return "禁用名單"


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")  # cp950 主控台印不了中文
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=10, help="試幾則（預設 10）")
    parser.add_argument("--all", action="store_true", help="整週：這一季會改寫的每一則")
    parser.add_argument("--random", action="store_true", help="隨機挑，不照 id 排的前幾則")
    parser.add_argument("--event", action="append", default=[], help="指定事件 id（可以給好幾次）")
    parser.add_argument("--model", help="換一個模型試（預設用 content/config.json 的 ollama_model）")
    parser.add_argument("--profile", default="season21", help="設定檔（預設 season21）")
    parser.add_argument("--out", help="全文另存到這個檔")
    args = parser.parse_args()

    content = load_content(ROOT / "content", args.profile)
    cfg = content.config
    pool = narration.eligible(content)
    if args.event:
        picked = [e for e in args.event if e in content.events]
        skipped = [e for e in args.event if e not in pool]
        if skipped:
            print(f"（{'、'.join(skipped)} 不在改寫的名單裡，照樣試給你看）")
    elif args.all:
        picked = pool
    elif args.random:
        picked = random.sample(pool, min(args.n, len(pool)))
    else:
        picked = pool[: args.n]

    client = OllamaClient(
        base_url=cfg.ollama_url, model=args.model or cfg.ollama_model, timeout=cfg.jianfa.rewrite_budget_seconds, think=cfg.ollama_think,
        keep_alive=cfg.ollama_keep_alive, repeat_penalty=cfg.ollama_repeat_penalty,
        presence_penalty=cfg.ollama_presence_penalty, frequency_penalty=cfg.ollama_frequency_penalty,
    )
    print(f"模型：{client.model}；這一季會改寫的共 {len(pool)} 則，這次試 {len(picked)} 則\n")
    watch = Watch(client)
    log: list[str] = []
    reasons: Counter[str] = Counter()
    took: list[float] = []
    for i, eid in enumerate(picked, 1):
        event = content.events[eid]
        start = time.monotonic()
        text = narration.write(watch, content, event)
        seconds = time.monotonic() - start
        took.append(seconds)
        head = f"── {i}/{len(picked)} {eid}【{event.title}】{seconds:.1f} 秒"
        if text is not None:
            body = f"{head} ✓ {len(event.text)}→{len(text)} 字\n原文：{event.text}\n改寫：{text}"
        else:
            why = f"叫不動：{watch.failed!r}" if watch.failed is not None else why_not(content, event.text, watch.raw)
            reasons[why.split("：")[0]] += 1
            body = f"{head} ⚠ 照原文（{why}）\n原文：{event.text}\n模型：{watch.raw!r}"
        print(body + "\n", flush=True)
        log.append(body)
    ok = len(picked) - sum(reasons.values())
    avg = sum(took) / len(took) if took else 0.0
    tail = f"總計：寫成 {ok}／{len(picked)} 則；照原文 {sum(reasons.values())} 則"
    if reasons:
        tail += "（" + "、".join(f"{k} {v}" for k, v in reasons.most_common()) + "）"
    tail += f"；平均 {avg:.1f} 秒一則，整週 {len(pool)} 則約 {avg * len(pool) / 60:.0f} 分鐘"
    print(tail)
    if args.out:
        Path(args.out).write_text("\n\n".join(log + [tail]) + "\n", encoding="utf-8")
        print(f"全文存在 {args.out}")


if __name__ == "__main__":
    main()
