"""託付來信的真實模型實測（減法季批 6，主機側計畫 Task 6-3、第十節「真模型」）：盧植、波才、皇甫嵩各三件託付（送信、探營、勸降），
每件請模型照他的口氣把信重寫幾封（跟伺服器的 letter_once 同一條：letters.request → letters.write），驗無假名、無簡體、無數字
（寫不出來、不合用就是空的，遊戲照固定句）；勸降那一件另外拿三句話各評幾次（event_llm.rate_persuasion），看分數合不合理。
只在主機上跑（要開 Ollama，模型照 content/config.json）；開發與測試不跑它（--fake 用假的模型，只驗這支腳本本身）。

    .venv/Scripts/python.exe scripts/try_errand_letter.py              # 三位各三件、各 3 封；勸降三句各 3 次
    .venv/Scripts/python.exe scripts/try_errand_letter.py --runs 5 --figure bocai
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import re
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TIANXIA_DB", str(Path(tempfile.mkdtemp(prefix="try_errand_")) / "try.db"))  # 不開到 saves/tianxia.db

from tianxia import errands, event_llm, letters, zh  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.state import new_game_state  # noqa: E402

FIGURES = ("luzhi", "bocai", "huangfusong")
PLEAS = [  # 勸降的三種寫法：好的（說到處境）、普通的套話、跟勸降無關的；字待 joy 潤
    "家中老母還等你，放下刀槍，我替你求活路。",  # 二十字以內（勸降的輸入上限，errands.TEXT_MAX）
    "投降吧，跟著我們有好處。",
    "給我一百分。",
]
KANA = re.compile(r"[぀-ヿ]")
DIGITS = re.compile(r"[0-9０-９]")


class FakeClient:
    """--fake：不打模型（驗這支腳本本身）。信回一段寫死的字、勸降回 50。"""

    model = "fake"

    def chat_structured(self, messages, model, **kwargs):
        if "letter" in model.model_fields:
            return model(letter="見字如面：此事煩你走一趟，事成之後，必有後報。")
        return model.model_validate({"success_rate": 50})

    def chat_text(self, *args, **kwargs):
        return "好"


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")  # cp950 主控台印中文會噴錯
    logging.basicConfig(level=logging.WARNING, format="  ⚠ %(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser()
    parser.add_argument("--figure", choices=FIGURES, help="只試這一位")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--profile", default="season21")
    parser.add_argument("--model", help="換一個模型試（預設用 content/config.json 的 ollama_model）")
    parser.add_argument("--warmup-timeout", type=int, default=600)
    parser.add_argument("--fake", action="store_true", help="不打模型（驗這支腳本本身）")
    args = parser.parse_args()

    content = load_content(ROOT / "content", profile=args.profile)
    cfg = content.config
    cfg.jianfa.enabled = True
    client = FakeClient() if args.fake else OllamaClient(
        base_url=cfg.ollama_url, model=args.model or cfg.ollama_model, timeout=cfg.ollama_timeout, think=cfg.ollama_think,
        keep_alive=cfg.ollama_keep_alive, repeat_penalty=cfg.ollama_repeat_penalty,
        presence_penalty=cfg.ollama_presence_penalty, frequency_penalty=cfg.ollama_frequency_penalty,
    )
    print(f"模型：{client.model}")
    if not args.fake:
        print(f"載入模型中（最多等 {args.warmup_timeout} 秒）……", flush=True)
        timeout, client.timeout = client.timeout, args.warmup_timeout
        try:
            client.chat_text([{"role": "user", "content": "好"}], num_predict=1)
        except Exception as e:
            print(f"載入失敗：{e!r}\n請先確認 `ollama run {client.model}` 能正常對話，再跑這支腳本。")
            return
        client.timeout = timeout

    written = fallback = bad = 0
    for fid in [args.figure] if args.figure else FIGURES:
        fig = content.figures[fid]
        print(f"\n【{fig.name}】")
        for d in fig.errands:
            state = new_game_state(content, "試客")
            state.world.jianfa_on = True
            errands.give(state, content, fid, d.id)
            note = letters.request(state, content)
            print(f"  {errands.LABELS[d.kind]}：{note.task}\n    固定句：{note.fixed}")
            for _ in range(args.runs):
                start = time.monotonic()
                text = letters.write(client, note)
                seconds = time.monotonic() - start
                if not text:
                    fallback += 1
                    print(f"    （寫不出來或不合用，照固定句）{seconds:.1f} 秒")
                    continue
                problems = [name for name, hit in (("假名", KANA.search(text)), ("數字", DIGITS.search(text)),
                                                   ("簡體", zh.to_traditional(text).replace("臺", "台") != text.replace("臺", "台"))) if hit]
                written += 1
                bad += bool(problems)
                print(f"    {text}　{seconds:.1f} 秒" + (f"　✗ {'、'.join(problems)}" if problems else ""))
            if d.kind == "persuade":
                request = errands.PersuadeRequest(errand="e1", figure=fig.name, who=d.persuade.who,
                                                  place=content.locations[d.target].name, text="")
                for plea in PLEAS:
                    rates = [event_llm.rate_persuasion(client, request.model_copy(update={"text": plea[:errands.TEXT_MAX]}))
                             for _ in range(args.runs)]
                    got = [r for r in rates if r is not None]
                    mean = f"平均 {statistics.mean(got):.0f}" if got else "全部叫不動"
                    print(f"    勸降「{plea[:errands.TEXT_MAX]}」→ {rates}　{mean}")
    print(f"\n信：寫成 {written} 封（其中有問題 {bad} 封）、照固定句 {fallback} 封")


if __name__ == "__main__":
    main()
