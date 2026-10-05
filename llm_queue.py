"""LLM 佇列（線上架構設計 5.2，第 2 期）：行動鎖外叫模型之前先在這裡排隊。

顯卡同時只處理 slots 件。排隊的規則：
- 真人先、假人後，同一種照先來後到；
- 每個人（名號）同時最多一件在排或在跑，第二件直接拿退路的結果；
- 假人在排加在跑最多 bot_cap 件，滿了也直接拿退路；
- 排超過 wait 秒還沒輪到，就拿退路、不叫模型。
輪到了才執行 job()，執行時不握任何鎖（呼叫端在行動鎖外叫這裡）。

只管「什麼時候輪到誰」，不管模型本身：job 裡面自己的逾時、重問、失敗退路照舊（例如 naming.generate 的預算）。
放在專案根目錄、不在 tianxia/：它要用執行緒與時鐘，引擎不讀時鐘（CLAUDE.md）。"""
from __future__ import annotations

import itertools
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

T = TypeVar("T")

HUMAN, BOT = 0, 1  # 排序的第一個鍵：真人先


@dataclass(order=True)
class _Ticket:
    rank: tuple[int, int]  # （真人 0／假人 1, 掛號順序）
    owner: str = field(compare=False)
    bot: bool = field(compare=False)


class LlmQueue:
    def __init__(self, slots: int, bot_cap: int, clock: Callable[[], float] = time.monotonic):
        if slots < 1:
            raise ValueError("slots 至少要 1")
        self.slots = slots
        self.bot_cap = bot_cap
        self._clock = clock
        self._cond = threading.Condition()
        self._waiting: list[_Ticket] = []
        self._active: list[_Ticket] = []
        self._seq = itertools.count()

    def run(self, owner: str, job: Callable[[], T], *, fallback: T, bot: bool = False, wait: float = 30.0) -> T:
        """排隊、輪到了執行 job() 並回傳它的結果。以下三種情況回傳 fallback、不執行 job：
        同一個人已經有一件、假人滿了、排超過 wait 秒。job 丟出的例外照樣往外丟，位置一定會讓出來。"""
        with self._cond:
            mine = self._waiting + self._active
            if any(t.owner == owner for t in mine):
                return fallback
            if bot and sum(t.bot for t in mine) >= self.bot_cap:
                return fallback
            ticket = _Ticket((BOT if bot else HUMAN, next(self._seq)), owner, bot)
            self._waiting.append(ticket)
            try:
                deadline = self._clock() + wait
                while not self._turn_of(ticket):
                    left = deadline - self._clock()
                    if left <= 0:
                        self._waiting.remove(ticket)
                        self._cond.notify_all()
                        return fallback
                    self._cond.wait(left)
            except BaseException:
                # 排隊時這個執行緒出了事（時鐘壞了、被中斷）：票一定要拿掉。留著的話它永遠是 min(waiting)，後面的人全都輪不到，
                # 連它自己的下一件也永遠被「已經有一件」擋下
                if ticket in self._waiting:
                    self._waiting.remove(ticket)
                    self._cond.notify_all()
                raise
            self._waiting.remove(ticket)
            self._active.append(ticket)
            if self._waiting and len(self._active) < self.slots:
                # 位子還空著、後面還有人：叫醒大家讓下一個進場。兩件一起做完時兩次 notify_all 可能都落在排隊的人搶到條件鎖
                # 之前，後到的先搶到、發現自己不是頭又回去睡；頭進場之後如果不再叫，下一個就睡到自己的期限（審查 I1）
                self._cond.notify_all()
        try:
            return job()
        finally:
            with self._cond:
                self._active.remove(ticket)
                self._cond.notify_all()

    def _turn_of(self, ticket: _Ticket) -> bool:
        return len(self._active) < self.slots and min(self._waiting) is ticket

    def position(self, owner: str) -> int | None:
        """這個人的那一件前面還有幾件（正在跑的也算）；正在跑是 0；沒有在排也沒在跑是 None。"""
        with self._cond:
            if any(t.owner == owner for t in self._active):
                return 0
            for i, t in enumerate(sorted(self._waiting)):
                if t.owner == owner:
                    return len(self._active) + i
            return None

    def snapshot(self) -> dict[str, int]:
        """管理者看的總數：正在跑幾件、在排幾件。只有兩個總數：不列名號，也不把假人與真人分開數（假人不能被看出來，
        連管理者的畫面也不行，審查 M4）；假人的上限 bot_cap 是這裡面的事，不對外。"""
        with self._cond:
            return {"running": len(self._active), "waiting": len(self._waiting)}
