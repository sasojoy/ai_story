"""伺服器主動通知（線上架構設計 5.3）：用 SSE（Server-Sent Events）告訴開著的分頁「有東西變了」，分頁再去抓 /api/main。

兩種通知：
- self：某個角色自己做完一個動作，他其他開著的分頁該刷新了；
- world：大家都看得到的世界變了（大事、江湖史、天下大事傳聞、決戰的階段與回合、大勢人物、已浮現的大勢線），每個分頁都刷新。
  由背景的看守（watch_world）每隔幾秒比一次「公開的世界指紋」，變了才發，而且兩次 world 之間至少隔 min_interval 秒。

另有一種不算通知的 ping：連線上沒事時每隔幾秒送一個，頁面靠它分辨「連線還活著」與「半開的死連線」（SSE 的註解行到不了
頁面的 JS，所以心跳要寫成事件）。

指紋只看大家本來就看得到的東西：鎖定、搶輸、豪強、伏筆、軍令、隱藏的大勢線、陣營軍情、地方傳聞與個人線索，還有
決戰裡誰加入了、這一回合出手了幾個，都不算——不然「什麼都沒變卻收到刷新」會洩漏誰在什麼時候做了看不見的事
（伏筆鎖定看不出來；決戰的人數是跟著假人的節奏變的，算了就等於把假人的作息廣播出去）。

放在專案根目錄、不在 tianxia/：要用執行緒、事件迴圈與時鐘。只送「哪一種變了」，不送內容，所以不會把誰的資料推給別人。"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import threading
import time
from collections.abc import Callable

SELF, WORLD, PING = "self", "world", "ping"


class PushHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}

    def subscribe(self, name: str, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subs.setdefault(name, set()).add((loop, queue))

    def unsubscribe(self, name: str, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        with self._lock:
            subs = self._subs.get(name)
            if subs is not None:
                subs.discard((loop, queue))
                if not subs:
                    del self._subs[name]

    def notify(self, name: str, kind: str = SELF) -> int:
        """通知這個角色開著的每個分頁；回傳送了幾個。可以從任何執行緒呼叫。"""
        with self._lock:
            targets = list(self._subs.get(name, ()))
        return sum(_deliver(loop, queue, kind) for loop, queue in targets)

    def broadcast(self, kind: str = WORLD) -> int:
        with self._lock:
            targets = [t for subs in self._subs.values() for t in subs]
        return sum(_deliver(loop, queue, kind) for loop, queue in targets)

    def close(self) -> None:
        """叫每一條連線結束（測試與關伺服器用）：送 None，串流收到就停。"""
        with self._lock:
            targets = [t for subs in self._subs.values() for t in subs]
        for loop, queue in targets:
            _deliver(loop, queue, None)

    def count(self) -> int:
        with self._lock:
            return sum(len(subs) for subs in self._subs.values())


def _deliver(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue, item) -> bool:
    try:
        loop.call_soon_threadsafe(queue.put_nowait, item)
        return True
    except RuntimeError:  # 那條連線的事件迴圈已經關了
        return False


def world_fingerprint(season_number: int, phase: str, season, battle) -> str:
    """大家都看得到的世界部分的指紋。時間本身不算（時鐘一直在走，靠慢速輪詢更新）。
    決戰只看階段、第幾回合與戰局（每個人的畫面都不一樣的那幾樣）；加入的人數、這一回合出手了幾個畫面上哪裡都看不到，不算。"""
    public = {
        "season": season_number,
        "phase": phase,
        "trends": {k: v for k, v in sorted(season.trends.items()) if k in season.revealed},
        "ending": season.ending_title,
        "act": [season.storyline, season.act],
        "timeline": sorted(season.timeline),
        "opened": sorted(season.showdowns_opened),
        "figures": {k: v.model_dump() for k, v in sorted(season.figures.items())},
        "rumor": max((r.id or 0 for r in season.rumors if r.layer == "world"), default=0),
        "chronicle": len(season.chronicle),
        "battle": None if battle is None else [battle.battle_id, battle.phase, battle.round_number, battle.trend],
    }
    blob = json.dumps(public, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def watch_world(
    hub: PushHub, fingerprint: Callable[[], str], stop: threading.Event, interval: float, min_interval: float,
    clock: Callable[[], float] = time.monotonic,
    on_error: Callable[[BaseException], None] | None = None, on_round: Callable[[], None] | None = None,
) -> None:
    """看守：每 interval 秒算一次指紋，跟上次發出去的不同、而且離上次 world 至少 min_interval 秒，就廣播 world。
    還沒到 min_interval 的變化不記下來，下一輪照樣看得出來、時間到了再發。算指紋出錯就跳過這一輪。
    出錯時這裡什麼都不印，只把例外交給 on_error：例外的訊息常夾著名號（含假人的），伺服器視窗不該看得出來，
    怎麼記由呼叫端決定（server.py 只寫例外的類別、同一個錯只數次數）。on_round 每一輪（成敗都算）叫一次，給呼叫端定時印累計用。
    兩個回呼自己出錯也吞掉：記錄不能讓看守停下來。clock 只用來算 min_interval，所以是 monotonic，不是世界的時間。"""
    sent = None
    last = float("-inf")
    while not stop.wait(interval):
        try:
            now_fp = fingerprint()
            if sent is None:
                sent = now_fp
            else:
                now = clock()
                if now_fp != sent and now - last >= min_interval:
                    hub.broadcast(WORLD)
                    sent, last = now_fp, now
        except Exception as e:  # noqa: BLE001  看守不能因為一次讀不到就停
            if on_error is not None:
                with contextlib.suppress(Exception):
                    on_error(e)
        if on_round is not None:
            with contextlib.suppress(Exception):
                on_round()


async def sse_stream(hub: PushHub, name: str, heartbeat: float = 15.0):
    """一條 SSE 連線：訂閱 name、把通知寫成 SSE 的格式；每 heartbeat 秒沒事就送一個 ping 事件，代理才不會當它斷了、
    頁面也才認得出死連線；收到 None（hub.close）就結束；不論怎麼結束（含分頁關掉、連線被切）都退訂。"""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    hub.subscribe(name, loop, queue)
    try:
        yield "retry: 5000\n\n"
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=heartbeat)
            except TimeoutError:
                yield f"event: {PING}\ndata: {{}}\n\n"
                continue
            if item is None:
                break
            yield f"event: {item}\ndata: {{}}\n\n"
    finally:
        hub.unsubscribe(name, loop, queue)
