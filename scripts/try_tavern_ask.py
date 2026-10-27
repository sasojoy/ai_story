"""問酒家的答題率（企劃者 2026-10-27「打聽的功能太弱了……很容易就回答不出來」）：拿一批玩家會問的題目，比改版前後酒家手上的事實清單，
加 --model 時真的叫模型寫回話、照酒家有沒有說「不清楚」算答出了沒。開一個暫存的世界（不碰這份 clone 的 saves/），不進測試。

    .venv/Scripts/python.exe scripts/try_tavern_ask.py                  # 只比事實清單：每一題清單裡有沒有對得上題目的那一樣（不叫模型，幾秒）
    .venv/Scripts/python.exe scripts/try_tavern_ask.py --model          # 真的叫模型（content/config.json 的設定），改版前後各寫一次，約十來分鐘
    .venv/Scripts/python.exe scripts/try_tavern_ask.py --model --only after --out ask.txt   # 只跑改版後，全文另存

最後兩行是總計：清單對得上幾題、模型答出幾題（改版前 → 改版後）。目標是改版後答出八成以上。
"""
from __future__ import annotations

import argparse
import io
import os
import random
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["TIANXIA_DB"] = str(Path(tempfile.mkdtemp(prefix="try-tavern-ask-")) / "tianxia.db")  # 不碰這份 clone 的 saves/

from tianxia import social, tavern  # noqa: E402
from tianxia.characters import CharacterStore  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

# （題目, 清單裡要有其中一樣才算答得出來）
QUESTIONS: list[tuple[str, tuple[str, ...]]] = [
    ("鐵匠鋪在哪裡？", ("鐵匠鋪",)),
    ("哪裡可以療傷？", ("醫館",)),
    ("哪裡買得到馬？", ("馬市",)),
    ("波才現在在哪？", ("波才",)),
    ("皇甫嵩是什麼人？", ("皇甫嵩",)),
    ("張角最近怎麼樣？", ("張角",)),
    ("精鐵砂哪裡採得到？", ("精鐵砂",)),
    ("柳絲綿多少錢？", ("柳絲綿",)),
    ("潁川郡怎麼走？", ("潁川郡",)),
    ("嵩山腳危險嗎？", ("嵩山腳",)),
    ("冰狼西獅是誰？", ("冰狼西獅",)),
    ("白衣秀士在哪一帶？", ("白衣秀士",)),
    ("怎麼升級比較快？", ("經驗",)),
    ("體力不夠怎麼辦？", ("體力",)),
    ("怎麼賺銀兩？", ("銀兩",)),
    ("要怎麼投靠官軍？", ("投靠",)),
    ("出陣是做什麼的？", ("出陣",)),
    ("意境怎麼悟？", ("意境",)),
    ("武學去哪學？", ("武學",)),
    ("懸賞榜在哪？", ("懸賞",)),
    ("被人截殺怎麼辦？", ("截殺",)),
    ("怎麼防殺手？", ("保鏢",)),
    ("名望怎麼漲？", ("名望",)),
    ("決戰什麼時候打？", ("決戰",)),
    ("現在天下局勢如何？", ("黃巾", "甲子")),
    ("黃巾為什麼起事？", ("太平道",)),
    ("這附近有什麼好去處？", ("附近",)),
    ("附近哪裡有怪可以打？", ("野外",)),
    ("挾風槍法是什麼？", ("挾風槍法",)),
    ("青龍刀法在哪學得到？", ("青龍刀法",)),
    ("潁川書院是什麼地方？", ("潁川書院",)),
    ("哪裡還有酒肆？", ("酒肆：",)),
    ("這一季還有多久？", ("眼下是",)),
    ("劉備在哪裡？", ("劉備",)),
    ("曹操是哪一邊的？", ("曹操",)),
    ("哪裡採得到素材？", ("採得到",)),
    ("宛城有什麼店？", ("宛城",)),
    ("長社離這裡多遠？", ("長社",)),
    ("盧植在哪？", ("盧植",)),
    ("華佗會治病嗎？", ("華佗",)),
    ("今天有什麼新鮮事？", ("傳聞", "附近")),
    ("我該先做什麼？", ("附近", "玩法")),
]


def world():
    c = load_content(ROOT / "content")
    c.config.auto_open_first_season = True
    store = open_world()
    now = 16 * 3600 + 3600
    me = Game.new(c, "問路客", rng=random.Random(0), world=store)
    me.client = None
    me.now = now
    p = me.state.player
    p.location, p.tutorial_step = "wan_city", len(c.tutorial.steps)
    p.stats["silver"] = 10_000
    p.seen_real = now
    for name, at, fame in (("冰狼西獅", "songshan_foot", 400), ("白衣秀士", "runan", 40)):
        g = Game.new(c, name, rng=random.Random(1), world=store)
        g.state.player.location, g.state.player.seen_real = at, now
        g.state.player.stats["fame"] = fame
        CharacterStore(store.db).save(g.state)
    CharacterStore(store.db).save(me.state)
    me.choose("act:tavern")
    return me


def old_facts(game: Game) -> tuple[str, ...]:
    """改版前的清單：這一區的局勢、最近的傳聞、這裡的出產、座上客、你自己（tavern.ask_facts 加原本那兩條 extra）。"""
    s, c = game.state, game.content
    extra = []
    guests = [o.player.name for o in social.here(game)][:6]
    if guests:
        extra.append(f"此刻也在{c.locations[s.player.location].name}的江湖人：{'、'.join(guests)}。")
    extra.append(f"問話的客官是{social.side(s, c)}，名號{s.player.name}。")
    return tavern.ask_facts(s, c, extra)


def covered(facts, want) -> bool:
    text = "".join(facts)
    return any(w in text for w in want)


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="store_true", help="真的叫模型寫回話（content/config.json 的 Ollama 設定）")
    ap.add_argument("--only", choices=["before", "after"], help="只跑改版前或改版後")
    ap.add_argument("--out", help="全文另存一份")
    args = ap.parse_args()
    game = world()
    c = game.content
    client = None
    if args.model:
        from tianxia.ollama_client import OllamaClient

        cfg = c.config
        client = OllamaClient(base_url=cfg.ollama_url, model=cfg.ollama_model, timeout=cfg.tavern.ask_budget_seconds, think=cfg.ollama_think,
                              keep_alive=cfg.ollama_keep_alive, repeat_penalty=cfg.ollama_repeat_penalty,
                              presence_penalty=cfg.ollama_presence_penalty, frequency_penalty=cfg.ollama_frequency_penalty)
        print(f"模型：{client.model}")
    sides = [x for x in ("before", "after") if args.only in (None, x)]
    hit = {k: 0 for k in sides}
    said = {k: 0 for k in sides}
    log: list[str] = []
    for i, (q, want) in enumerate(QUESTIONS, 1):
        row = [f"{i:2d}. {q}"]
        for side in sides:
            facts = old_facts(game) if side == "before" else game._tavern_ask_facts(q)[0]
            ok = covered(facts, want)
            hit[side] += ok
            mark = "有" if ok else "缺"
            if client is not None:
                req = tavern.AskRequest(name=game.state.player.name, place=game.state.player.location, sign=tavern.sign(game.state, c),
                                        question=q, facts=tuple(facts))
                t0 = time.time()
                reply = tavern.ask_write(client, req)
                good = reply is not None and not tavern.unsure(reply)
                said[side] += good
                mark += f"／{'答出' if good else '答不出'}（{time.time() - t0:.0f} 秒）"
                log.append(f"[{side}] {q}\n  酒家：{reply}\n")
            row.append(f"{'改版前' if side == 'before' else '改版後'}：{mark}")
        print("  ".join(row))
    n = len(QUESTIONS)
    print()
    print("清單對得上：" + " → ".join(f"{hit[s]}/{n}（{hit[s] * 100 // n}%）" for s in sides))
    if client is not None:
        print("模型答出：" + " → ".join(f"{said[s]}/{n}（{said[s] * 100 // n}%）" for s in sides))
        if args.out:
            Path(args.out).write_text("\n".join(log), encoding="utf-8")
        else:
            print("\n" + "\n".join(log))


if __name__ == "__main__":
    main()
