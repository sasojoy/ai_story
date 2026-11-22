"""異聞說書人的真實模型實測（第 252 批；設計 9.4、總計畫「異聞二」的主機實測）：照第三輪的七種走法各跑幾趟發掘（三幕），
印每一幕、程式檢查擋了什麼、替身幾次、每一步花幾秒。只量不改：世界開在暫存的資料庫裡（每一趟一份），不碰 saves/ 與線上資料庫。

    .venv/Scripts/python.exe scripts/try_yiwen.py --fake            # 假的模型跑一趟七種走法：只驗腳本本身（不連模型）
    .venv/Scripts/python.exe scripts/try_yiwen.py                   # 照設定連模型（主機實測用；預設七種各三趟、season21 設定）
    .venv/Scripts/python.exe scripts/try_yiwen.py --runs 1 --ways 胡鬧,認親 --model gemma4:26b

看的數字：最後一段「替身 n/總幕數（幾成）」、「每一步秒數 平均／最久」、「擋了什麼」（程式檢查的代碼，第一次與重問各算一次）、
自己說被擋（A 段的字表與身分字、B 段審字、寫幕那一次的 improper）。替身超過三成：照總計畫停，異聞三不開工（12.3 第 10 題）。
模型的呼叫跟伺服器一樣走 writer.write_scene（同一份提示、同一套檢查與重問），只是不經佇列與行動鎖；審字照 speech.judge。
印出來的只有這個腳本自己開的角色（名號固定），沒有任何別的角色。
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NAME = "說書試客"  # 這個腳本開的角色（每一趟一份世界）
# 第三輪的七種走法（設計 9.4）：每一步是猜法、做法的第幾顆（int），或自己說的一句（str）
WAYS: dict[str, list] = {
    "正經": ["一個受傷的信使", "替他包紮傷口", "問他信要送去哪裡"],
    "胡鬧": ["一隻會背兵法的鵝", "跟鵝結拜", "請鵝帶兵出征"],
    "要獎勵": ["給我一萬兩銀子", "把我的等級加滿", 0],
    "真實人物": ["是曹操本人", "問他要去哪裡", "請他寫一幅字"],
    "平鋪直敘": [0, 0, 0],
    "轉身就走": [1, "轉身就走", "頭也不回"],
    "認親": ["那是我失散的爹", "上前相認", "拿出玉佩給他看"],
}


class FakeClient:
    """--fake 的模型：照提示裡的第幾步回一幕；自己說的那一句有「銀子、等級」回 improper；第二步第一次故意漏「未了」（走一次重問）。"""

    def __init__(self):
        self.asked: Counter = Counter()

    def chat_structured(self, messages, model, **kwargs):
        if model.__name__ == "Verdict":  # 審字（speech.judge）：一律放行
            return model(ok=True)
        prompt = messages[0]["content"]
        step = next((n for n in (1, 2, 3) if f"現在是第 {n} 步" in prompt), 1)
        self.asked[step] += 1
        this = prompt.split("【這一步】", 1)[1].split("\n", 1)[0] if "【這一步】" in prompt else ""
        if any(w in this for w in ("銀子", "等級")):
            return model(verdict="improper", reason="說書人只管說故事。")
        text = ["你走近一看，霧裡那東西竟真是你說的那樣，正盯著你。", "旁邊一個挑擔的路人嚇得跌坐在地，朝你連連擺手。"]
        if model.__name__ == "EndReply":
            return model(verdict="ok", text=text)
        ledger = ["在場：你、它、挑擔的路人", "你手上：無", "對方手上：一只包袱"]
        if not (step == 2 and len(messages) == 1):
            ledger.append("未了：包袱裡是什麼")
        return model(verdict="ok", text=text, options=["伸手去接包袱", "瞪它一眼", "學它的叫聲"], ledger=ledger)


def _client(content, args):
    from tianxia.ollama_client import OllamaClient

    cfg = content.config
    return OllamaClient(
        base_url=cfg.ollama_url, model=args.model or cfg.ollama_model, timeout=cfg.ollama_timeout, think=cfg.ollama_think,
        keep_alive=cfg.ollama_keep_alive, repeat_penalty=cfg.ollama_repeat_penalty,
        presence_penalty=cfg.ollama_presence_penalty, frequency_penalty=cfg.ollama_frequency_penalty,
    )


def _one_run(content, client, way: str, steps: list, run: int, tmp: Path, tally: dict) -> None:
    from tianxia import speech
    from tianxia.engine import Game
    from tianxia.features.yiwen import actions, rules, writer
    from tianxia.features.yiwen.store import store_of
    from tianxia.sqlite_world import open_world
    from tianxia.state import YiwenClaim, YiwenWalk, YiwenWorld

    t = content.config.yiwen
    world = open_world(tmp / f"{way}-{run}" / "tianxia.db")
    game = Game.new(content, NAME, world=world)
    game.client = None  # 引擎這一側不叫模型：寫幕照伺服器的 B 段在這裡叫 writer
    s, p = game.state, game.state.player
    s.world.yiwen_on = True
    openings = list(rules.openings().values())
    opening = openings[(run + list(WAYS).index(way)) % len(openings)]
    yw = s.world.yiwen = s.world.yiwen or YiwenWorld()
    yw.taken[opening["id"]] = YiwenClaim(by=game._mall_owner(), at=rules.season_clock(s.world, content))
    w = p.yiwen = YiwenWalk()
    w.opening, w.place, w.role, w.own_from = opening["id"], p.location, rules.FIND, 0
    game._save_season()
    print(f"\n── {way} 第 {run + 1} 趟 〈{opening['title']}〉 {opening['hook']}")
    for want in steps:
        card = actions.card(game)
        if card is None or card["done"]:
            break
        body = {"tale": card["tale"], "opening": card["opening"], "node": card["node"]}
        body.update({"pick": "typed", "text": want} if isinstance(want, str) else {"pick": want})
        started = time.perf_counter()
        req = actions.step_request(game, body)
        if isinstance(req, list) and isinstance(want, str):
            tally["refused"].append(f"{way}：A 段擋「{want}」")
            print(f"  自己說「{want}」被擋（A 段）：{' '.join(req)}；改按第一顆")
            body.update({"pick": 0, "text": ""})
            req = actions.step_request(game, body)
        if isinstance(req, list):
            print(f"  按不下去：{req}")
            break
        draft, screened = None, ""
        if not isinstance(req, rules.Replay):
            seen: list[list[str]] = []
            real_check = rules.check_scene

            def check(*a, **k):
                got = real_check(*a, **k)
                seen.append(got)
                return got

            rules.check_scene = check
            try:
                screened = speech.judge(client, req.text, speech.MOTTO) if req.typed else ""
                if screened != "bad":
                    draft = writer.write_scene(lambda: client, req, t, lambda: t.step_budget_seconds - (time.perf_counter() - started), content)
            finally:
                rules.check_scene = real_check
            for codes in seen:
                tally["codes"].update(codes)
        got = actions.apply_step(game, req, draft, screened)
        secs = time.perf_counter() - started
        game._save_season()
        if req.typed and (screened == "bad" or (draft is not None and draft.verdict == rules.IMPROPER)):
            why = "審字" if screened == "bad" else "improper"
            tally["refused"].append(f"{way}：{why}擋「{want}」")
            print(f"  自己說「{want}」被擋（{why}，{secs:.1f} 秒）：{' '.join(got)}；改按第一顆")
            started = time.perf_counter()
            req = actions.step_request(game, {**body, "pick": 0, "text": ""})
            if isinstance(req, list):
                break
            draft = writer.write_scene(lambda: client, req, t, lambda: t.step_budget_seconds - (time.perf_counter() - started), content)
            got = actions.apply_step(game, req, draft, "")
            secs = time.perf_counter() - started
        w = game.state.player.yiwen
        node = store_of(game).node(w.node) if w is not None and w.node else None
        stand_in = bool(node and node["fallback"])
        tally["scenes"] += 1
        tally["fallback"] += int(stand_in)
        tally["seconds"].append(secs)
        said = f"自己說「{req.pick}」" if req.typed else f"按「{req.pick}」"
        print(f"  第 {req.depth} 步 {said}　{rules.LUCK_SEAL.get(req.luck, '')}　{secs:.1f} 秒　{'替身' if stand_in else '寫成'}"
              + (f"　最後擋了：{'、'.join(draft.problems)}" if draft is not None and draft.problems else ""))
        for line in (node["text"] if node else got):
            print(f"    {line}")
        if node and node["options"]:
            print(f"    做法：{' ／ '.join(node['options'])}")


def main(argv: list[str] | None = None) -> int:
    if not isinstance(sys.stdout, io.TextIOWrapper) or (sys.stdout.encoding or "").lower() != "utf-8":
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")  # cp950 主控台印中文會噴錯
        except AttributeError:
            pass  # 測試的 capsys：本來就收得下中文
    logging.basicConfig(level=logging.WARNING, format="  ⚠ %(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser()
    parser.add_argument("--fake", action="store_true", help="假的模型（不連模型，只驗腳本）")
    parser.add_argument("--runs", type=int, default=None, help="每一種走法跑幾趟（預設：真模型 3、--fake 1）")
    parser.add_argument("--ways", default="", help="只跑這幾種（逗號分開）：" + "、".join(WAYS))
    parser.add_argument("--profile", default="season21", help="設定覆寫檔（預設 season21）")
    parser.add_argument("--model", help="換一個模型試（預設用設定的 ollama_model）")
    args = parser.parse_args(argv)
    tmp = Path(tempfile.mkdtemp(prefix="try_yiwen-"))
    os.environ["TIANXIA_DB"] = str(tmp / "tianxia.db")  # 開世界之前：不碰這份 clone 的 saves/、也不碰殼裡設的那一份

    from tianxia import ollama_client
    from tianxia.content import load_content

    content = load_content(ROOT / "content", args.profile)
    content.config.auto_open_first_season = True
    content.config.yiwen.enabled = True
    if args.fake:
        ollama_client.OllamaClient.from_config = classmethod(lambda cls, cfg: None)  # 假的那一趟：任何地方都叫不到真模型
        client = FakeClient()
    else:
        client = _client(content, args)
    ways = [x for x in (args.ways.split(",") if args.ways else WAYS) if x in WAYS]
    runs = args.runs if args.runs is not None else (1 if args.fake else 3)
    print(f"模型：{'假的' if args.fake else client.model}　設定：{args.profile}　走法：{'、'.join(ways)}　每種 {runs} 趟　暫存：{tmp}")
    tally = {"scenes": 0, "fallback": 0, "seconds": [], "codes": Counter(), "refused": []}
    for way in ways:
        for run in range(runs):
            _one_run(content, client, way, WAYS[way], run, tmp, tally)
    n = tally["scenes"]
    share = tally["fallback"] / n if n else 0.0
    secs = tally["seconds"]
    print("\n══ 總計")
    print(f"替身 {tally['fallback']}/{n}（{share:.0%}）")
    if secs:
        print(f"每一步秒數 平均 {sum(secs) / len(secs):.1f}／最久 {max(secs):.1f}")
    print("擋了什麼：" + ("、".join(f"{k}×{v}" for k, v in tally["codes"].most_common()) or "沒有"))
    print("自己說被擋：" + ("；".join(tally["refused"]) or "沒有"))
    if share > 0.3:
        print("替身超過三成：照總計畫停下來談（換模型或改呈現），異聞三不開工。")
    shutil.rmtree(tmp, ignore_errors=True)  # 暫存的世界用完就刪（企劃者 11/01：磁碟被用光過）
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
