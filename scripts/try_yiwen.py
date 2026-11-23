"""異聞說書人的真實模型實測（第 252 批；設計 9.4、總計畫「異聞二」的主機實測）：照第三輪的七種走法各跑幾趟發掘（三幕），
印每一幕、每一次呼叫的秒數與結果、程式檢查擋了什麼、替身與正忙幾次。只量不改：世界開在暫存的資料庫裡（每一趟一份），不碰 saves/ 與線上資料庫。

    .venv/Scripts/python.exe scripts/try_yiwen.py --fake            # 假的模型跑一趟七種走法：只驗腳本本身（不連模型）
    .venv/Scripts/python.exe scripts/try_yiwen.py                   # 照設定連模型（主機實測用；預設七種各三趟、season21 設定）
    .venv/Scripts/python.exe scripts/try_yiwen.py --runs 1 --ways 胡鬧,認親 --model gemma4:26b
    .venv/Scripts/python.exe scripts/try_yiwen.py --uncapped        # 舊量法：不套時間限制，只看模型本身寫不寫得出來
    .venv/Scripts/python.exe scripts/try_yiwen.py --budget 90       # 這一趟把一步的預算換成 90 秒（只改腳本記憶體裡的設定）
    .venv/Scripts/python.exe scripts/try_yiwen.py --drafts          # 沒過檢查的草稿整段印出來

第 265 批起預設**照伺服器的時間限制量**（對齊 tianxia/features/yiwen/routes.py 的 yiwen_step）：一步從開單起算
step_budget_seconds；自己說的先審字（server.screen_text：字表擋得下的不叫模型，審字另一份 12 秒、每一趟逾時 min(模型逾時, 剩下÷2)），
審完剩下不到 step_min_write_seconds 就是「正忙」（伺服器什麼都不存：腳本另數一類、那一趟停）；寫幕每叫一次 client_for 給一份
照剩下的秒數套上限的複本（naming.per_post_seconds＋ollama_client.capped，跟 server.within_budget 同兩行；分不到 1 秒就不叫）。
刻意跟伺服器不一樣的：不經模型佇列與行動鎖（正式伺服器上排隊的秒數也吃預算，伺服器只會更差）；自己說被擋之後腳本自己改按第一顆
（新開一張單、重新起算，等於玩家再按一次）；正忙就停那一趟（不替玩家假設下一步）。--uncapped 完全照第 252 批的量法。

看的數字（結尾）：寫成／替身／正忙（替身率的分母＝寫成＋替身）、第一次就過、重問與救回、每一次呼叫的秒數（中位／九成／最久；
九成取最近序 sorted[ceil(0.9n)-1]）、第一次與重問各擋了什麼（程式檢查的代碼，加逾時、連不上、回不成 JSON）、自己說被擋（A 段、審字、improper）。
替身超過三成：照總計畫停，異聞三不開工（12.3 第 10 題）——只有照伺服器量的數才算。
模型的呼叫跟伺服器一樣走 writer.write_scene（同一份提示、同一套檢查與重問）；每一次呼叫在腳本這一側包一層記下來，不改 writer。
印出來的只有這個腳本自己開的角色（名號固定），沒有任何別的角色。
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import math
import os
import shutil
import statistics
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NAME = "說書試客"  # 這個腳本開的角色（每一趟一份世界）
CLOCK = time.perf_counter  # 第 265 批：量秒數一律經它（測試換成假鐘）
SCREEN_BUDGET_SECONDS = 12.0  # 第 265 批：照 server.SCREEN_BUDGET_SECONDS（不 import server）
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
        self.timeout = 120.0  # 第 265 批：main 換成設定的 ollama_timeout；跟真的一樣能被 capped 換掉

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


def _within(client, left: float):
    """第 265 批：照 server.within_budget 的兩行（不 import server）：這一趟逾時 min(模型逾時, 剩下÷2)，分不到 1 秒回 None。"""
    from tianxia import naming, ollama_client

    if client is None:
        return None
    per_post = naming.per_post_seconds(client, left)
    return None if per_post is None else ollama_client.capped(client, per_post)


def _failure(e: Exception) -> str:
    import requests
    from pydantic import ValidationError

    from tianxia.ollama_client import ModelGaveUp

    if isinstance(e, (requests.Timeout, TimeoutError)):
        return "逾時"
    if isinstance(e, (requests.ConnectionError, requests.RequestException, ModelGaveUp)):
        return "連不上"
    if isinstance(e, (json.JSONDecodeError, ValidationError, ValueError)):
        return "回不成 JSON"
    return type(e).__name__


class _Recorder:
    """第 265 批：包在（套過上限的）client 外面，記下每一次 chat_structured 花幾秒、回來的是什麼；例外照原樣再丟（writer 的行為不變）。"""

    def __init__(self, inner, log: list, kind: str, cap: float | None):
        self.inner, self.log, self.kind, self.cap = inner, log, kind, cap

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def chat_structured(self, messages, model, **kwargs):
        entry = {"kind": self.kind, "cap": self.cap, "called": True, "secs": 0.0, "fail": "", "reply": None, "codes": None, "draft": None}
        self.log.append(entry)
        t0 = CLOCK()
        try:
            got = self.inner.chat_structured(messages, model, **kwargs)
        except Exception as e:  # noqa: BLE001 — 記下類別，照原樣丟回去
            entry["secs"], entry["fail"] = CLOCK() - t0, _failure(e)
            raise
        entry["secs"], entry["reply"] = CLOCK() - t0, got
        return got


def _not_called(log: list, kind: str, left: float) -> None:
    log.append({"kind": kind, "cap": None, "called": False, "secs": 0.0, "fail": f"沒叫（剩 {max(left, 0.0):.1f} 秒）",
                "reply": None, "codes": None, "draft": None})


def _writer_client(client, log: list, left, uncapped: bool):
    """writer.write_scene 的 client_for：第一次叫是「第一次」、之後是「重問」；照伺服器量時每一次照 left() 套上限。"""
    asked = [0]

    def client_for():
        asked[0] += 1
        kind = "第一次" if asked[0] == 1 else "重問"
        if uncapped:
            return _Recorder(client, log, kind, None)
        rest = left()
        got = _within(client, rest)
        if got is None:
            _not_called(log, kind, rest)
            return None
        return _Recorder(got, log, kind, got.timeout)

    return client_for


def _screen(client, text: str, content, log: list, uncapped: bool) -> str:
    """自己說的審字：照伺服器 server.screen_text（字表擋得下的不叫模型；另一份 12 秒預算）；--uncapped 照舊直接 speech.judge。"""
    from tianxia import speech

    if uncapped:
        return speech.judge(_Recorder(client, log, "審字", None), text, speech.MOTTO)
    if not text or client is None:
        return ""
    if speech.word_problem(text, content, speech.MOTTO, 200):
        return ""
    started = CLOCK()
    rest = SCREEN_BUDGET_SECONDS - (CLOCK() - started)
    got = _within(client, rest)
    if got is None:
        _not_called(log, "審字", rest)
        return speech.judge(None, text, speech.MOTTO)
    return speech.judge(_Recorder(got, log, "審字", got.timeout), text, speech.MOTTO)


def _write(client, req, t, left, content, log: list, uncapped: bool, typed: bool):
    """叫 writer.write_scene，把 rules.check_scene 每一次的代碼配給最後一筆回來了的呼叫（第 252 批的包法）。"""
    from tianxia.features.yiwen import rules, writer

    real_check = rules.check_scene

    def check(*a, **k):
        got = real_check(*a, **k)
        for entry in reversed(log):
            if entry["called"] and not entry["fail"] and entry["kind"] != "審字":
                entry["codes"], entry["draft"] = list(got), a[0]
                break
        return got

    rules.check_scene = check
    try:
        draft = writer.write_scene(_writer_client(client, log, left, uncapped), req, t, left, content)
    finally:
        rules.check_scene = real_check
    for entry in log:  # 回 improper 的那一次 writer 不叫 check_scene（_check 自己判）
        if entry["kind"] != "審字" and entry["called"] and not entry["fail"] and entry["codes"] is None:
            verdict = str(getattr(entry["reply"], "verdict", "") or "").strip().lower()
            if verdict == rules.IMPROPER:
                entry["codes"] = ["improper（交給 C）"] if typed else ["improper"]
    return draft


def _print_calls(log: list, drafts: bool) -> None:
    for entry in log:
        head = f"    〔{entry['kind']}〕"
        if not entry["called"]:
            print(head + entry["fail"])
            continue
        cap = f"（上限 {entry['cap']:.1f}）" if entry["cap"] is not None else ""
        if entry["fail"]:
            print(f"{head}{entry['secs']:.1f} 秒{cap}　{entry['fail']}")
            continue
        if entry["kind"] == "審字":
            ok = getattr(entry["reply"], "ok", None)
            print(f"{head}{entry['secs']:.1f} 秒{cap}　{'放行' if ok is True else '擋' if ok is False else '怪值'}")
            continue
        codes = entry["codes"] or []
        draft = entry["draft"]
        size = ""
        if draft is not None:
            size = f"　段長 {[len(x) for x in draft.text]}　做法 {[len(x) for x in draft.options]}"
        print(f"{head}{entry['secs']:.1f} 秒{cap}　{'、'.join(codes) if codes else '過'}{size}")
        if drafts and codes and draft is not None:
            for line in draft.text:
                print(f"      ✗ {line}")
            if draft.options:
                print(f"      ✗ 做法：{' ／ '.join(draft.options)}")


def _one_run(content, client, way: str, steps: list, run: int, tmp: Path, tally: dict, uncapped: bool = False, drafts: bool = False) -> None:
    from tianxia.engine import Game
    from tianxia.features.yiwen import actions, rules
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
        started = CLOCK()
        req = actions.step_request(game, body)
        if isinstance(req, list) and isinstance(want, str):
            tally["refused"].append(f"{way}：A 段擋「{want}」")
            tally["refused_by"]["A 段"] += 1
            print(f"  自己說「{want}」被擋（A 段）：{' '.join(req)}；改按第一顆")
            body.update({"pick": 0, "text": ""})
            started = CLOCK()  # 第 265 批：改按第一顆是新的一張單（玩家再按一次）
            req = actions.step_request(game, body)
        if isinstance(req, list):
            print(f"  按不下去：{req}")
            break

        def left(started=started) -> float:
            return t.step_budget_seconds - (CLOCK() - started)

        log: list = []
        draft, screened = None, ""
        if not isinstance(req, rules.Replay):
            screened = _screen(client, req.text, content, log, uncapped) if req.typed else ""
            if not uncapped and left() < t.step_min_write_seconds:  # routes.yiwen_step：審字吃掉了預算＝正忙，什麼都不存
                tally["log"].extend(log)
                tally["steps"].append({"way": way, "depth": req.depth, "result": "正忙", "log": log})
                print(f"  第 {req.depth} 步 自己說「{req.pick}」　正忙（剩 {left():.1f} 秒，不到 {t.step_min_write_seconds:g}）：{actions.busy_line(game, req)}")
                _print_calls(log, drafts)
                return  # 伺服器什麼都沒存：這一趟停
            if screened != "bad":
                draft = _write(client, req, t, left, content, log, uncapped, req.typed)
        got = actions.apply_step(game, req, draft, screened)
        secs = CLOCK() - started
        game._save_season()
        if req.typed and (screened == "bad" or (draft is not None and draft.verdict == rules.IMPROPER)):
            why = "審字" if screened == "bad" else "improper"
            tally["refused"].append(f"{way}：{why}擋「{want}」")
            tally["refused_by"][why] += 1
            print(f"  自己說「{want}」被擋（{why}，{secs:.1f} 秒）：{' '.join(got)}；改按第一顆")
            _print_calls(log, drafts)
            tally["log"].extend(log)
            started = CLOCK()
            req = actions.step_request(game, {**body, "pick": 0, "text": ""})
            if isinstance(req, list):
                break

            def left(started=started) -> float:  # noqa: F811 — 新的一張單重新起算
                return t.step_budget_seconds - (CLOCK() - started)

            log = []
            draft = None
            if not uncapped and left() < t.step_min_write_seconds:
                tally["steps"].append({"way": way, "depth": req.depth, "result": "正忙", "log": log})
                print(f"  第 {req.depth} 步 按「{req.pick}」　正忙：{actions.busy_line(game, req)}")
                return
            draft = _write(client, req, t, left, content, log, uncapped, False)
            got = actions.apply_step(game, req, draft, "")
            secs = CLOCK() - started
        w = game.state.player.yiwen
        node = store_of(game).node(w.node) if w is not None and w.node else None
        stand_in = bool(node and node["fallback"])
        tally["log"].extend(log)
        tally["steps"].append({"way": way, "depth": req.depth, "result": "替身" if stand_in else "寫成", "log": log})
        tally["seconds"].append(secs)
        said = f"自己說「{req.pick}」" if req.typed else f"按「{req.pick}」"
        print(f"  第 {req.depth} 步 {said}　{rules.LUCK_SEAL.get(req.luck, '')}　{secs:.1f} 秒　{'替身' if stand_in else '寫成'}"
              + (f"　最後擋了：{'、'.join(draft.problems)}" if draft is not None and draft.problems else ""))
        _print_calls(log, drafts)
        for line in (node["text"] if node else got):
            print(f"    {line}")
        if node and node["options"]:
            print(f"    做法：{' ／ '.join(node['options'])}")


def _count_line(steps: list) -> str:
    c = Counter(x["result"] for x in steps)
    a, b, busy = c["寫成"], c["替身"], c["正忙"]
    share = b / (a + b) if a + b else 0.0
    return f"寫成 {a}　替身 {b}　正忙 {busy}（共 {a + b} 幕；替身 {share:.0%}）"


def _spread(secs: list[float]) -> str:
    if not secs:
        return "沒有"
    ordered = sorted(secs)
    p90 = ordered[math.ceil(0.9 * len(ordered)) - 1]
    return f"中位 {statistics.median(ordered):.1f}／九成 {p90:.1f}／最久 {ordered[-1]:.1f}（{len(ordered)} 次）"


def _codes(log: list, kind: str) -> str:
    c: Counter = Counter()
    for entry in log:
        if entry["kind"] != kind or not entry["called"]:
            continue
        if entry["fail"]:
            c[entry["fail"]] += 1
        else:
            c.update(entry["codes"] or [])
    return "、".join(f"{k}×{v}" for k, v in c.most_common()) or "沒有"


def _summary(tally: dict, t, uncapped: bool) -> None:
    steps, log = tally["steps"], tally["log"]
    scenes = [x for x in steps if x["result"] != "正忙"]
    print("\n══ 總計")
    print(_count_line(steps))
    for depth in sorted({x["depth"] for x in steps}):
        print(f"  第 {depth} 步　" + _count_line([x for x in steps if x["depth"] == depth]))
    for way in dict.fromkeys(x["way"] for x in steps):
        print(f"  {way}　" + _count_line([x for x in steps if x["way"] == way]))

    def first_ok(x) -> bool:
        first = next((e for e in x["log"] if e["kind"] == "第一次"), None)
        return bool(first and first["called"] and not first["fail"] and not first["codes"])

    retried = [x for x in scenes if any(e["kind"] == "重問" and e["called"] for e in x["log"])]
    print(f"第一次就過 {sum(first_ok(x) for x in scenes)}/{len(scenes)}")
    print(f"重問 {sum(1 for e in log if e['kind'] == '重問' and e['called'])} 次、救回 {sum(1 for x in retried if x['result'] == '寫成')} 次")
    print("每一次呼叫秒數（寫幕） " + _spread([e["secs"] for e in log if e["called"] and e["kind"] != "審字"]))
    print("每一次呼叫秒數（審字） " + _spread([e["secs"] for e in log if e["called"] and e["kind"] == "審字"]))
    print(f"沒叫（預算不夠）{sum(1 for e in log if not e['called'])} 次")
    print("第一次擋了什麼：" + _codes(log, "第一次"))
    print("重問擋了什麼：" + _codes(log, "重問"))
    by = tally["refused_by"]
    print(f"自己說被擋：A 段 {by['A 段']}、審字 {by['審字']}、improper {by['improper']}　" + ("；".join(tally["refused"]) or "沒有"))
    a = sum(1 for x in scenes if x["result"] == "寫成")
    share = (len(scenes) - a) / len(scenes) if scenes else 0.0
    if share > 0.3:
        if uncapped:
            print("替身超過三成：這是沒套時間限制的數，照伺服器量再看。")
        else:
            print("替身超過三成：照總計畫停下來談（換模型或改呈現），異聞三不開工。")
    if uncapped:
        print("量法：沒套時間限制（--uncapped），替身率比伺服器樂觀")
    else:
        print(f"量法：照伺服器的時間限制（一步 {t.step_budget_seconds:g} 秒）")


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
    parser.add_argument("--uncapped", action="store_true", help="不套時間限制（舊量法：只看模型本身寫不寫得出來，比伺服器樂觀）")
    parser.add_argument("--budget", type=float, default=None, help="這一趟把一步的預算換成這麼多秒（只改腳本記憶體裡的設定）")
    parser.add_argument("--drafts", action="store_true", help="沒過檢查的草稿整段印出來")
    args = parser.parse_args(argv)
    tmp = Path(tempfile.mkdtemp(prefix="try_yiwen-"))
    os.environ["TIANXIA_DB"] = str(tmp / "tianxia.db")  # 開世界之前：不碰這份 clone 的 saves/、也不碰殼裡設的那一份

    from tianxia import ollama_client
    from tianxia.content import load_content

    content = load_content(ROOT / "content", args.profile)
    content.config.auto_open_first_season = True
    content.config.yiwen.enabled = True
    if args.budget is not None:
        content.config.yiwen.step_budget_seconds = float(args.budget)  # 只改這一份載入的設定，不寫任何檔
    t = content.config.yiwen
    if args.fake:
        ollama_client.OllamaClient.from_config = classmethod(lambda cls, cfg: None)  # 假的那一趟：任何地方都叫不到真模型
        client = FakeClient()
        client.timeout = float(content.config.ollama_timeout)
    else:
        client = _client(content, args)
    ways = [x for x in (args.ways.split(",") if args.ways else WAYS) if x in WAYS]
    runs = args.runs if args.runs is not None else (1 if args.fake else 3)
    how = "沒套時間限制（--uncapped）" if args.uncapped else f"照伺服器（一步 {t.step_budget_seconds:g} 秒）"
    print(f"模型：{'假的' if args.fake else client.model}　設定：{args.profile}　走法：{'、'.join(ways)}　每種 {runs} 趟　量法：{how}　暫存：{tmp}")
    tally = {"steps": [], "log": [], "seconds": [], "refused": [], "refused_by": Counter()}
    for way in ways:
        for run in range(runs):
            _one_run(content, client, way, WAYS[way], run, tmp, tally, uncapped=args.uncapped, drafts=args.drafts)
    _summary(tally, t, args.uncapped)
    shutil.rmtree(tmp, ignore_errors=True)  # 暫存的世界用完就刪（企劃者 11/01：磁碟被用光過）
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
