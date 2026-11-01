"""事件檢定（核心本體；全部拆包第 16 批，計畫 docs/superpowers/plans/2026-11-01-事件檢定進核心.md，導覽 docs/guide/核心與存檔.md「事件檢定」）：
端出事件卡、固定選項的檢定與結果、效果套用、事件裡打一場、隨口應對的三段式。原本是 Game 上的 17 個方法，本體照抄、self 換成 ctx
（第一階 ctx 就是 Game，開發規範手冊 3.3），Game 留 15 個一行委派（server、假人、測試、探索包都在叫；只有這裡叫的 answer_branch、
deed_credit 不留）。模組裡互相叫直接叫函式；被測試換掉的 Game 方法經 ctx.<名>（_present：tests/bots/test_event_rotation 換掉
Game._present），留在 Game 上的（選單、分派、記錄、戰鬥的單打服務、地盤的進度……）一律經 ctx。

- 事件卡：present（把事件端到眼前）、event_text（旁白）、event_tier（州郡大事、天下大事那一行）、event_option_view（江湖頁的鈕）、
  choice_label_of（選單上那一顆的字）
- 固定選項：resolve_choice（按下去：檢定、打一場、套效果、行狀）、event_battle（劇情戰）、apply（效果；串下一則）、tale_clue（說書的口訣）
- 隨口應對：free_text_of、branches_of、event_free_text_prompt（那一顆與輸入框）、free_text_request（A 段，鎖內只讀）、
  answer_event（C 段）、answer_branch（分岔的 C 段）、deed_credit（分岔的後果記貢獻）、add_gamble_narration（E 段，潤色插回紀錄）；
  鎖外的 B、D 段照舊在 server.answer_event，叫 Game 的委派
- 模組層的名字：FREE_TEXT_OPTION、EVIL_ANNAL、FreeTextRequest、FreeTextOutcome（engine 照名字 import 回來，`from tianxia.engine import …` 照舊）

名字的綁法照 engine：engine 拿名字的（rules.roll_check、apply_effect……）這裡也拿名字，engine 叫模組屬性的（events.note_round、team、
event_llm、secret_recipes）這裡也叫模組屬性——測試換掉的東西兩邊打得到的一樣。engine 在 `from .world import (...)` 之後才 import 這一份
（這裡 import 的模組那時都已經載入，載入順序不變）。

改這一份 test_for 挑核心測試＋煙霧；照舊直接碰到事件檢定、要另外跑的（-m "slow or not slow"）：tests/bots/test_free_text_and_marks.py、
tests/bots/test_event_rotation.py、tests/core/test_outcomes_answer.py、tests/core/test_outcomes_server.py、tests/core/test_outcomes_bots.py、
tests/arts/test_in_lock_model_timeout.py、tests/core/test_events.py、tests/core/test_event_tiers.py、tests/server/test_server.py，
與 scripts/same_behavior.py 的 events 一軌（見計畫第五節）。
"""
from __future__ import annotations

from pydantic import BaseModel

FREE_TEXT_OPTION = "choice:free"  # 事件的「隨口應對」：按下去只是叫出輸入框，真正送出走 free_text_request／answer_event
EVIL_ANNAL = "，行了一件惡事，成了。"  # 行狀：隨口應對判成惡行而且成了（FB-223），接在「遇上【某事】，隨口應對」後面。待 joy 潤


class FreeTextRequest(BaseModel):
    """隨口應對鎖外評估的單子（server.py 的 A 段拿到、B 段送模型、C 段交回 answer_event 重驗）。"""
    event_id: str
    text: str
    # 減法季批 4：分岔開著、這則事件寫了後果時是可能的走向（outcomes.tags；B 段照它改叫 event_llm.judge_outcome）；其餘是空的
    outcomes: list[dict[str, str]] = []


class FreeTextOutcome(BaseModel):
    """擲完骰的結果：server.py 拿它在鎖外請模型潤色，再交回 add_gamble_narration 插進那一則江湖紀錄。"""
    event_id: str
    text: str
    success: bool
    effect_text: str
    time: float  # 那一則紀錄的遊戲時間與標題，插潤色前用來認是不是同一則
    title: str
    evil: bool = False  # 判成惡行而且成了（FB-223）：effect_text 是 rules.EVIL_DONE，潤色照惡行寫、寫成了換掉那一句
    outcome: str = ""  # 減法季批 4：分岔開著時走的是哪一種後果（id）；關著是空的
