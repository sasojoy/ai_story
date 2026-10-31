"""重複內容的 LLM 潤色（設計文件 8.2 第 4 點）：世界事件傳聞全服只潤色一次、所有玩家共用同一份
結果（快取在共用世界狀態，見 world_state.py::get_event_flavor/set_event_flavor）。
重遊地點、重複事件的點綴句 2026-10-12 拿掉了：在全服行動鎖裡等模型，寫出來卻只進 GameState.log、畫面上看不到。

優先度最低（設計文件 8.2：「其餘做完再回頭補」），所以這裡刻意極簡：固定一次呼叫、
不重試、失敗或沒有 client 就直接回傳空字串讓呼叫端整句省略，絕不讓這種錦上添花的潤色
拖慢或卡住正常的行動流程。

要把那兩句做回來的話（設計 8.2 第 4 點），兩件事都得做：先讓它真的顯示得出來（事件與地點的場景文字是每次
輪詢從 content 重新組的，所以場景或紀錄要存得住這一句），而且**一定要走鎖外的三段式**（像對話、開爐取名
那樣：A 鎖內開單、B 鎖外叫模型、C 鎖內套用）。不要再放回行動鎖裡。
"""
from __future__ import annotations

import re

from . import zh
from .ollama_client import OllamaClient

FLAVOR_NUM_PREDICT = 80

_SYSTEM_PROMPT = (
    "你是漢末三國文字遊戲的氣氛點綴生成器，只負責在一段已經寫好的固定文字後面，補一句簡短"
    "（15~40 字）的即景或心境描寫，貼合漢末亂世的語境（不是武俠小說），不重寫、不否定、不總結"
    "前面的內容，也不要提到原文沒有的人物或事件，純粹是再多看一眼的補充細節。只輸出這一句話"
    "本身，用繁體中文，不要加引號、不要加任何格式標記、不要解釋你在做什麼。"
)


def _ask(client: OllamaClient | None, prompt: str) -> str:
    if client is None:
        return ""
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    try:
        text = client.chat_text(messages, num_predict=FLAVOR_NUM_PREDICT)
    except Exception:
        return ""
    return clean(text)


FLAVOR_MIN, FLAVOR_MAX = 4, 60  # 提示要 15~40 字；太短的也收，只擋長段
_BANNED = ("假人", "機器人", "遊戲", "系統", "玩家")


def clean(raw: str) -> str:
    """點綴那一句驗過才用（結果全服快取、每季都看同一句，寫壞了就一直壞）：轉繁體、去標記；
    太長太短、換行、有數字、英文、不准出現的字就丟掉（回空字串，呼叫端整句省略、不寫快取）。"""
    text = zh.to_traditional(str(raw or "")).strip().strip('「」"')
    text = re.sub(r"[*#>`_]+", "", text).strip()
    if (not (FLAVOR_MIN <= len(text) <= FLAVOR_MAX) or "\n" in text or re.search(r"[0-9０-９A-Za-z{}]", text)
            or any(w in text for w in _BANNED)):
        return ""
    return text


def polish_world_event(client: OllamaClient | None, text: str) -> str:
    """江湖大事（世界門檻/世界事件）的傳聞文字，全服共用一次潤色結果（見 world.py::_fire）。"""
    return _ask(client, f"江湖上剛傳開一件大事：{text}")
