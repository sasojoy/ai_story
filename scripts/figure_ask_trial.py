"""開口求人的真實模型實測（Joy 2026-10-23「先做看看」；tianxia/parley.py）：站在一位大勢人物面前，用「自己說」求他做事，
看模型挑了哪一件（ask）、給多少意願（willing）、開什麼條件（condition），引擎夾完、擲完是答應、開條件還是婉拒，三版回話各寫了什麼。

要先開 Ollama，模型用 content/config.json 的設定（跟遊戲一樣）。世界開在暫存的資料庫裡，不碰 saves/。一個指令：

    .venv/Scripts/python.exe scripts/figure_ask_trial.py  # 預設：跟盧植說三句、每句 10 次，共 30 次
    .venv/Scripts/python.exe scripts/figure_ask_trial.py --runs 30  # 每句 30 次
    .venv/Scripts/python.exe scripts/figure_ask_trial.py --figure luzhi --affinity 60 "盧公可否陪我出陣"

預期：求指點挑 spar、求帶路去廣宗挑 escort:guangzong（份量大、情誼淺時多半開條件）、借兵這種清單外的事填 refuse；
條件 id 都在清單上（清單外的會印「清單外」，引擎當沒開）。最後印每句的統計：挑了什麼、意願平均、開條件幾成、結果分布。
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import random
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TIANXIA_DB", str(Path(tempfile.mkdtemp()) / "figure_ask_trial.db"))  # 開世界之前：不碰這份 clone 的 saves/

from tianxia import companion_agent, figure_life, parley  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game, say_text  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402

DEFAULT_LINES = [
    "盧公，可否指點我一招槍法？",  # 該挑 spar
    "盧公，可否親自帶我去廣宗看看賊勢？",  # 該挑 escort:guangzong
    "把你的兵借我三千。",  # 清單外：該填 refuse
]
WHERE = {"luzhi": "luzhi_camp"}  # 人物 → 站在哪裡跟他說（沒寫的照他此刻在哪）
OUTCOME = {"do": "答應", "terms": "開條件", "no": "婉拒", None: "不是在求事"}


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")  # cp950 主控台印中文會噴錯
    logging.basicConfig(level=logging.WARNING, format="  ⚠ %(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser()
    parser.add_argument("lines", nargs="*", default=DEFAULT_LINES)
    parser.add_argument("--figure", default="luzhi", help="人物 id（content/characters）")
    parser.add_argument("--runs", type=int, default=10, help="每句問幾次")
    parser.add_argument("--affinity", type=int, default=25, help="你跟他的情誼（決定意願的天花板）")
    parser.add_argument("--faction", default=None, help="你投靠的陣營 id（guan、huang；不給是散人）")
    parser.add_argument("--model", help="換一個模型試（預設用 content/config.json 的 ollama_model）")
    parser.add_argument("--warmup-timeout", type=int, default=600, help="第一次載入模型最多等幾秒")
    parser.add_argument("--quiet", action="store_true", help="不印每一次的回話，只印統計")
    args = parser.parse_args()

    content = load_content(ROOT / "content")
    content.config.parley.enabled = True
    content.config.auto_open_first_season = True
    cfg = content.config
    client = OllamaClient(
        base_url=cfg.ollama_url, model=args.model or cfg.ollama_model, timeout=cfg.ollama_timeout, think=cfg.ollama_think,
        keep_alive=cfg.ollama_keep_alive, repeat_penalty=cfg.ollama_repeat_penalty,
        presence_penalty=cfg.ollama_presence_penalty, frequency_penalty=cfg.ollama_frequency_penalty,
    )
    cid = args.figure
    character = content.characters[cid]
    print(f"模型：{client.model}　人物：{character.name}　情誼：{args.affinity}　資料庫：{os.environ['TIANXIA_DB']}")
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

    game = Game.new(content, "試開口的人")
    p = game.state.player
    p.location = WHERE.get(cid) or figure_life.where(game.state, content, cid) or p.location
    p.flags.add(f"結識:{cid}")
    p.affinities[cid] = args.affinity
    if args.faction:
        p.faction = args.faction
    p.pending_companion = cid
    asks, conditions = game._parley_lists(cid)
    hostile = parley.enemy(game.state, content, cid, game._side())
    word, _ = parley.band(content, args.affinity)
    print(f"地點：{content.locations[p.location].name}　情誼那一檔：{word}{'（敵對）' if hostile else ''}")
    print("他做得到的事：" + "、".join(f"{a.id}（份量 {a.weight}，上限 {parley.ceiling(content, args.affinity, a.weight, hostile)}）" for a in asks))
    print("他可以開的條件：" + "、".join(c.id for c in conditions) + "\n")
    extra = game._parley_prompt(cid)
    ask_ids, cond_ids = {a.id for a in asks}, {c.id for c in conditions}
    dice = random.Random(0)

    for line in args.lines:
        said = say_text(line, game.say_max())
        if said is None:
            print(f"「{line}」 字數不對（1～{game.say_max()} 字），跳過\n")
            continue
        picked, outcomes, conds, willing, fails = Counter(), Counter(), 0, [], 0
        print(f"══ 你：「{said}」")
        for n in range(1, args.runs + 1):
            request = companion_agent.build_request(game.state, content, game.world, cid, "talk:say", said, free=True, extra=extra)
            start = time.monotonic()
            try:
                turn = companion_agent.generate_turn(client, request.messages)
            except companion_agent.DialogueUnavailable as e:
                fails += 1
                print(f"  #{n} 模型叫不動（遊戲裡這輪會取消、不扣體力）：{e}")
                continue
            ask = (turn.ask or "").strip()
            cond = (turn.condition or "").strip()
            decision = parley.decide(content, asks, conditions, ask, turn.willing, cond, args.affinity, hostile, dice.randint(1, 100))
            picked[ask if ask in ask_ids or ask in ("", parley.REFUSE) else f"{ask}（清單外）"] += 1
            outcomes[OUTCOME[decision.kind]] += 1
            conds += bool(cond)
            if turn.willing is not None:
                willing.append(turn.willing)
            if args.quiet:
                continue
            cond_note = "" if not cond or cond in cond_ids else "（清單外，當沒開）"
            print(f"  #{n} ask={ask or '空'} willing={turn.willing} condition={cond or '空'}{cond_note}"
                  f" → 夾到 {decision.chance}，{OUTCOME[decision.kind]}　{time.monotonic() - start:.0f} 秒")
            print(f"     答應：{turn.narrative}")
            if turn.narrative_terms:
                print(f"     開條件：{turn.narrative_terms}")
            if turn.narrative_no:
                print(f"     婉拒：{turn.narrative_no}")
        avg = f"{sum(willing) / len(willing):.0f}" if willing else "—"
        done = args.runs - fails
        print(f"  ── 統計（{done} 次{f'，{fails} 次失敗' if fails else ''}）：挑了 {dict(picked)}；意願平均 {avg}；"
              f"開條件 {conds}/{done}；結果 {dict(outcomes)}\n")


if __name__ == "__main__":
    main()
