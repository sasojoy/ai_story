"""門派論劍的殼那一側（只在殼建動作表、開背景執行緒時 import；引擎與假人程式不碰）：

- POST /api/lunjian/plan（body {"text": 戰策}）：上了台的人自己寫的一句戰策（老法子是選項 lunjian:preset:<n>，不走這裡）。
  沒登入 401、開關關著 404（同江湖錄）；回 {main, message}。
- 背景那一條（Feature.threads；只有 server.main 叫，測試直接叫 judge_round）：開打的時刻過了、還沒開打的那一週，一輪挑一對還沒判的，
  在鎖外請模型判三場（judge.ask，走殼的佇列），判好了用 mutate_season 一筆寫回 LunjianMatch.calls。開打本身照舊是下一個同步的人在鎖裡做
  （actions.resolve）；模型叫不動就不寫，等 judge_wait_hours 過了照關鍵字判。時鐘只用殼的 time。"""
from __future__ import annotations

import threading

from fastapi import APIRouter, Body, HTTPException, Request

from tianxia.state import WorldState

from . import actions, judge, rules

STOP = threading.Event()
QUEUE_KEY = "門派論劍"  # 佇列裡的名號（不是任何角色）


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.post("/api/lunjian/plan")
    def api_plan(request: Request, body: dict = Body(default={})):
        """定一句戰策（自己寫的）。"""
        shell._account(request)  # 沒登入 401（先於開關，同江湖錄）
        if not rules.on(shell.CONTENT):
            raise HTTPException(404)
        game = shell._game(request)
        text = str(body.get("text", ""))[:200]
        msgs = shell.act(game, lambda g: _plan(g, text))
        return {"main": shell.look(game, shell.main_view), "message": " ".join(msgs or [])}

    return r


def _plan(g, text: str) -> list[str]:
    return g._log(actions.set_plan(g, text))


def todo(season: WorldState, content) -> tuple[int, int] | None:
    """該判的那一對（週, 第幾對）：抽了籤、到了開打、還沒開打、這一對還沒判。沒有是 None。"""
    lw = season.lunjian
    if lw is None:
        return None
    for w in lw.weeks:
        if not w.drawn or w.fought or season.time < rules.fight_at(w.week, content, season):
            continue
        for i, m in enumerate(w.matches):
            if len(m.calls) < len(m.seats_a):
                return w.week, i
    return None


def judge_round(shell, client) -> bool:
    """一輪（呼叫端不能握著行動鎖）：判一對、寫回；回 True＝寫了。"""
    content = shell.CONTENT
    if client is None or not rules.on(content):
        return False
    world = shell.open_world()
    if world.season_phase() != "running":
        return False
    season = world.get_season()
    got = todo(season, content)
    if got is None:
        return False
    week, i = got
    w = next(x for x in season.lunjian.weeks if x.week == week)
    m = w.matches[i]
    budget = float(content.config.lunjian.judge_budget_seconds)
    calls = []
    for seat, (a, b) in enumerate(zip(m.seats_a, m.seats_b)):
        def ask(a=a, b=b, seat=seat):
            return judge.ask(client, a, b, seat, budget)

        call = None
        if shell.QUEUE is None:
            call = ask()
        else:
            try:
                call = shell.QUEUE.run(QUEUE_KEY, ask, fallback=None, bot=True, wait=budget)
            except Exception:  # noqa: BLE001  佇列忙（真人正在等模型）：這一輪讓路
                return False
        calls.append(call or rules.rule_call(a, b, seat))
    seats = [(x.name, x.plan) for x in m.seats_a + m.seats_b]
    wrote = []

    def put(s: WorldState) -> None:
        ww = next((x for x in (s.lunjian.weeks if s.lunjian else []) if x.week == week), None)
        if ww is None or ww.fought or i >= len(ww.matches):
            return
        mm = ww.matches[i]
        if mm.calls or [(x.name, x.plan) for x in mm.seats_a + mm.seats_b] != seats:
            return  # 等模型的時候別人先開打了、或戰策變了（不該發生：開打之後不能改）：不寫
        mm.calls = calls
        wrote.append(True)

    world.mutate_season(put)
    return bool(wrote)


def start(shell):
    """伺服器啟動時（Feature.threads）開背景那一條；開關關著、建不起 client 就不開。"""
    content = shell.CONTENT
    if not rules.on(content):
        return None
    try:
        client = shell.OllamaClient.from_config(content.config)
    except Exception:  # noqa: BLE001  建不起 client：全照關鍵字判，不擋伺服器
        return None
    every = float(content.config.lunjian.judge_round_seconds)

    def loop() -> None:
        while not STOP.wait(every):
            try:
                judge_round(shell, client)
            except Exception:  # noqa: BLE001, S110  一輪出錯不能讓整條停下來（下一輪再試；等過了照關鍵字判）
                pass

    thread = threading.Thread(target=loop, daemon=True, name="lunjian-judge")
    thread.start()
    return thread
