"""人物心意的真實模型實測（減法季批 6，主機側計畫 Task 6-3、第十節「真模型」）：盧植、波才、皇甫嵩三位人物，每位對他說幾句
（預設是他三個心意各一句、再加一句閒話），每句生成幾輪對話（跟遊戲「自己說」同一條提示與 schema），印模型歸的 stance 對不對。
只在主機上跑（要開 Ollama，模型照 content/config.json 的設定，跟遊戲一樣）；開發與測試不跑它（--fake 用假的模型，只驗這支腳本本身）。

    .venv/Scripts/python.exe scripts/try_stances.py               # 三位各四句、各 3 輪
    .venv/Scripts/python.exe scripts/try_stances.py --runs 5 --figure luzhi
    .venv/Scripts/python.exe scripts/try_stances.py --figure bocai "官軍快到了，趕緊打下長社"

預期：每句歸到它寫在旁邊的那一個心意 id；閒話歸 none。開一個暫存的資料庫（TIANXIA_DB 沒設就用系統暫存目錄的新檔），不碰正式資料庫。
"""
from __future__ import annotations

import argparse
import collections
import io
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TIANXIA_DB", str(Path(tempfile.mkdtemp(prefix="try_stances_")) / "try.db"))  # 不開到 saves/tianxia.db

from tianxia import companion_agent, stances  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.state import new_game_state  # noqa: E402

LINES = {  # 每位人物：（一句話, 預期的心意 id）；字待 joy 潤
    "luzhi": [("黃巾烏合之眾，趁他們立足未穩，該速攻廣宗！", "suzhan"), ("廣宗城堅，不如深溝高壘，等援軍到了再說。", "chizhong"),
              ("城外流民挨餓，先開倉放糧安頓百姓吧。", "xumin"), ("將軍今天吃過飯了嗎？", stances.NONE)],
    "bocai": [("官軍還沒到，咱們一鼓作氣拿下長社！", "mengong"), ("營寨要紮穩，多派哨探，別中了官軍的計。", "jieying"),
              ("別再搶鄉親的糧了，人心散了仗就打不贏。", "fuzhong"), ("渠帥這把刀真好看。", stances.NONE)],
    "huangfusong": [("賊兵依草結營，趁大風放火，必能大破之。", "chuqi"), ("賊眾我寡，不如堅守長社，等朱將軍來援。", "jianshou"),
                    ("軍紀要嚴，不能擾民，潁川百姓才肯送糧。", "anmin"), ("長社的酒好喝嗎？", stances.NONE)],
}


class FakeClient:
    """--fake：不打模型，回一輪寫死的對話（stance 照句子的順序輪流挑），只驗這支腳本本身跑得通。"""

    model = "fake"
    turn = 0

    def chat_structured(self, messages, model, **kwargs):
        ids = model.model_json_schema()["properties"]["stance"]["enum"]
        FakeClient.turn += 1
        return model(narrative="他點了點頭。", options=["再說說", "告辭"], option_tags=["真誠請教", "尋常寒暄"],
                     stance=ids[(FakeClient.turn - 1) % len(ids)])

    def chat_text(self, *args, **kwargs):
        return "好"


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")  # cp950 主控台印中文會噴錯
    logging.basicConfig(level=logging.WARNING, format="  ⚠ %(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser()
    parser.add_argument("lines", nargs="*", help="自己寫的幾句（給了就只試 --figure 那一位、不比對預期）")
    parser.add_argument("--figure", choices=sorted(LINES), help="只試這一位")
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

    world = open_world()
    figures = [args.figure] if args.figure else list(LINES)
    total = hits = 0
    for fid in figures:
        fig = content.figures[fid]
        cid = fig.character
        state = new_game_state(content, "試客")
        state.world.jianfa_on = True
        state.player.location = fig.location
        state.player.affinities[cid] = 20
        rows = [(x, None) for x in args.lines] if args.lines else LINES[fid]
        print(f"\n【{fig.name}】心意：" + "；".join(f"{d.id}（{d.name}）" for d in fig.stances))
        for said, want in rows:
            request = companion_agent.build_request(state, content, world, cid, "talk:say", said, free=True)
            picked, seconds = collections.Counter(), []
            for _ in range(args.runs):
                start = time.monotonic()
                try:
                    turn = companion_agent.generate_turn(client, request.messages, request.required, stances=request.stances)
                    picked[getattr(turn, "stance", None) or "（沒填）"] += 1
                except companion_agent.DialogueUnavailable as e:
                    picked[f"（生成失敗：{str(e)[:30]}）"] += 1
                seconds.append(time.monotonic() - start)
            got = picked.get(want, 0) if want else None
            if want:
                total, hits = total + args.runs, hits + got
            mark = "" if want is None else f"　預期 {want}：{got}/{args.runs}"
            print(f"  「{said}」→ {dict(picked)}{mark}　每輪 {sum(seconds) / len(seconds):.1f} 秒")
    if total:
        print(f"\n合計歸對 {hits}/{total}")


if __name__ == "__main__":
    main()
