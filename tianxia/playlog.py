"""真人量表（減法季批 0，設計稿第十章；整合設計 11.4）：每個帳號每天按了哪幾顆、哪幾天上線、第一次寫隨口應對、
第一次跟人物說話、第一次看「全區」是哪一天。

- 只有伺服器寫（server.py：真人自己的請求）。假人程式不經過伺服器，不記；記了也只是總數，不寫任何名號到畫面或主控台。
- 不露給玩家：沒有 API、不進 main_view；主機端用 scripts/play_metrics.py 看總數（不列名號：只列真人會讓人從缺席看出誰是假人）。
- 資料庫第 7 版的兩張表（action_counts、action_firsts）。owner 是角色名號的 casefold（characters.name_key；一個帳號一個角色，
  同商城的 owner）。day 是回體丹換日的那一天（台灣 00:00，Game._pill_day），season 是那時的季數。
- 每個寫的方法自己開 db.transaction()：呼叫端已經開著（伺服器的行動鎖）就併進那一筆，出錯整筆撤回。

判準【預設】（整合設計 11.4）：遭遇佔每日行動不超過四成、第 3 天留存五成、第 7 天四成、一半的人在第 2 天前寫過一次隨口應對。這裡只記與算，判準寫在報表上。
只碰資料庫，不碰遊戲規則、不讀時鐘（時間由呼叫端傳進來）。
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field

from .database import Database

FREE_TEXT = "free_text"  # 第一次寫隨口應對（/api/answer）
FIGURE_TALK = "figure_talk"  # 第一次跟人物說話（交友、求見、對話選項、自己說）
WHOLE_AREA = "whole_area"  # 第一次看輿圖的「全區」（輿圖四層那一批接上；表先留好，不必再升版）
FIRSTS = (FREE_TEXT, FIGURE_TALK, WHOLE_AREA)
# 照前兩段歸類的前綴：行動列的格子（act:train 出陣、act:explore 探索……）與探索三選一（explore:gather……）分得開；
# 其他照第一段（choice、talk、call、battle、move……），選項 id 後面帶的地點、人物、編號不記
TWO_PART = ("act:", "explore:")


def button_of(option_id: str) -> str:
    """選項 id 歸成量表上的一顆鈕：act:train、explore:gather、choice、talk……（空的回 ""）。"""
    parts = option_id.split(":")
    if option_id.startswith(TWO_PART) and len(parts) > 1:
        return ":".join(parts[:2])
    return parts[0]


@dataclass
class Account:
    """一個帳號這一季的樣子（報表用，不帶名號）。"""

    days: set[int] = field(default_factory=set)  # 上線的那幾天（季的第幾天，1 起算）
    buttons: Counter = field(default_factory=Counter)  # 整季每顆鈕按了幾次
    firsts: dict[str, int] = field(default_factory=dict)  # 第一次做某件事是季的第幾天


class PlayLog:
    def __init__(self, db: Database):
        self.db = db

    def seen(self, owner: str, season: int, day: int) -> None:
        """這一天上線了（自己的請求）：沒有那一列就開一列。"""
        with self.db.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO action_counts (owner, season, day) VALUES (?, ?, ?)", (owner, season, day))

    def press(self, owner: str, season: int, day: int, button: str) -> None:
        """這一天按了一次 button（button_of 歸過類的）。"""
        if not button:
            return
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT buttons FROM action_counts WHERE owner = ? AND season = ? AND day = ?", (owner, season, day),
            ).fetchone()
            counts = json.loads(row["buttons"]) if row else {}
            counts[button] = counts.get(button, 0) + 1
            conn.execute(
                "INSERT INTO action_counts (owner, season, day, buttons) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (owner, season, day) DO UPDATE SET buttons = excluded.buttons",
                (owner, season, day, json.dumps(counts, ensure_ascii=False, sort_keys=True)),
            )

    def first(self, owner: str, season: int, kind: str, day: int, time: float) -> bool:
        """第一次做 kind（FIRSTS 之一）：這一季還沒記過才記，回有沒有記下。"""
        if kind not in FIRSTS:
            raise ValueError(f"不認得的第一次：{kind}")
        with self.db.transaction() as conn:
            done = conn.execute(
                "INSERT OR IGNORE INTO action_firsts (owner, season, kind, day, time) VALUES (?, ?, ?, ?, ?)",
                (owner, season, kind, day, time),
            )
            return done.rowcount > 0

    def accounts(self, season: int, start_day: int | None = None) -> list[Account]:
        """這一季每個帳號一份（照 owner 排、不帶名號）。start_day 是季的第 1 天（回體丹換日的那一天）；不給就用這一季最早有人上線的那一天。"""
        with self.db.snapshot() as conn:
            days = conn.execute("SELECT owner, day, buttons FROM action_counts WHERE season = ? ORDER BY owner, day", (season,)).fetchall()
            firsts = conn.execute("SELECT owner, kind, day FROM action_firsts WHERE season = ?", (season,)).fetchall()
        if start_day is None:
            start_day = min((r["day"] for r in days), default=0)
        out: dict[str, Account] = {}
        for r in days:
            a = out.setdefault(r["owner"], Account())
            a.days.add(r["day"] - start_day + 1)
            a.buttons.update(json.loads(r["buttons"]))
        for r in firsts:
            out.setdefault(r["owner"], Account()).firsts[r["kind"]] = r["day"] - start_day + 1
        return [out[k] for k in sorted(out)]


def retention(accounts: list[Account], day: int) -> float | None:
    """第 day 天的留存：開季頭一天就來了的帳號裡，第 day 天（含）以後還上線過的有幾成；頭一天沒人來回 None。"""
    first_day = [a for a in accounts if 1 in a.days]
    if not first_day:
        return None
    return sum(1 for a in first_day if max(a.days) >= day) / len(first_day)


def last_days(accounts: list[Account]) -> Counter:
    """第幾天不再上線：每個帳號最後上線的那一天（季的第幾天）→ 幾個帳號。"""
    return Counter(max(a.days) for a in accounts if a.days)
