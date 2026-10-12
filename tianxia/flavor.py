"""重複內容的 LLM 潤色（設計文件 8.2 第 4 點）：一般地點重複造訪、事件重複觸發，固定
文字後面加一小段即時生成的裝飾句；世界事件傳聞則是全服只潤色一次、所有玩家共用同一份
結果（快取在共用世界狀態，見 world_state.py::get_event_flavor/set_event_flavor）。

優先度最低（設計文件 8.2：「其餘做完再回頭補」），所以這裡刻意極簡：固定一次呼叫、
不重試、失敗或沒有 client 就直接回傳空字串讓呼叫端整句省略，絕不讓這種錦上添花的潤色
拖慢或卡住正常的行動流程。

**polish_revisit 與 polish_event_repeat 現在沒有人呼叫**（2026-10-12）：它們以前在 engine 的
`_present`（重複事件）與 `_arrive`（重遊的終點）裡，而那兩處都在**全服唯一的那把行動鎖裡面**，
用的是 `Game._quick_client()`——模型慢的時候每次要等滿 `in_lock_model_timeout`（15 秒），
那 15 秒裡任何人點任何東西都在排隊（joy 2026-10-12 回報「點完探索有時候伺服器沒有立即反應」）。
而且這兩句話其實**沒有任何玩家看得到**：事件與地點的場景文字是每次輪詢從 content 重新組的
（`engine._own_scene_text`、`location_text`），這一句只附在行動回傳的 msgs 上，而 `/api/choose`
（探索、移動都是選項）與 `/api/travel` 都不把 msgs 回給前端，`_hide(text)` 又把它擋在江湖紀錄外面。
所以那是「花 15 秒鎖住全服，生成一句丟掉的話」。

要把這個功能做回來的話（設計 8.2 第 4 點），兩件事都得做：先讓它真的顯示得出來（場景或紀錄要存得住
這一句），而且**一定要走鎖外的三段式**（像對話、開爐取名那樣：A 鎖內開單、B 鎖外叫模型、C 鎖內套用），
不要再放回行動鎖裡。`polish_world_event` 不在此列：它由 `world.py` 呼叫、全服只潤色一次、結果快取在
共用世界狀態，玩家在傳聞裡看得到。
"""
from __future__ import annotations

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
    return zh.to_traditional(text.strip().strip('「」"'))


def polish_revisit(client: OllamaClient | None, loc_name: str, loc_desc: str) -> str:
    """重遊一個已經去過、沒有手寫特殊內容的地點時，補一句此刻的小細節。"""
    return _ask(client, f"玩家這次又重新造訪了「{loc_name}」。這個地方原本的描述是：{loc_desc}")


def polish_event_repeat(client: OllamaClient | None, event_title: str, event_text: str) -> str:
    """同一個事件又被觸發一次時，補一句跟上次不盡相同的小細節，避免讀起來像複製貼上。"""
    return _ask(client, f"玩家又遇上了「{event_title}」這件事。事件原文是：{event_text}")


def polish_world_event(client: OllamaClient | None, text: str) -> str:
    """江湖大事（世界門檻/世界事件）的傳聞文字，全服共用一次潤色結果（見 world.py::_fire）。"""
    return _ask(client, f"江湖上剛傳開一件大事：{text}")
