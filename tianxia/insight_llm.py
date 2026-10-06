"""感悟狀態畫完那一筆之後，請模型替新悟到的意境取名（悟意境設計 0.2、0.2a）。

模型只寫名字與一句說明：成敗在選做法時已經擲完、屬性由規則讀筆畫定好（glyph.py），這裡一個數字都不碰。
退路照 0.2a：看圖（gemma4:26b 本身看得懂圖，帶玩家畫的那張小 PNG）→ 只給規則讀到的文字特徵 → 都拿不到就是 (None, "")，
由呼叫端走退路字表。走三段式的 B 段（鎖外、不碰狀態）：A 段 sensing.request 開單、C 段 sensing.finish 重驗再套用。
這個模組不讀時鐘：總時間用 budget（秒）扣，照給出去的 timeout 算（同 naming.propose）。"""
from __future__ import annotations

import copy

from . import naming, zh
from .models import Content
from .ollama_client import OllamaClient

SYSTEM_PROMPT = (
    "你是武俠小說裡替意境取名的人。有人在某個地方心有所感，用手指一筆畫下了心中的形。"
    "你只負責替這份領悟取名字、寫一句話的說明，**絕對不要提到任何數字、品質、等級或威力**。全程使用繁體中文。"
)
# 本機實測：沒有這一句時模型認得出形狀，但命名會被地點景色蓋過去（只有 75% 講到形狀）；加了這句九次全部講到
SHAPE_RULE = "說明裡一定要寫出你在圖上看到的線條形狀（例如圓轉、折角、急折、雜亂），不要只寫地點的景色。"
SHAPE_RULE_TEXT = "說明裡一定要寫出這一筆線條的形狀（照上面讀到的那一句），不要只寫地點的景色。"
IMAGE_SHARE = 0.7  # 預算的這幾成先給看圖；看圖拿不到，剩下的給只看文字特徵
MIN_TEXT_SECONDS = 3.0  # 看圖失敗之後，剩不到這麼多秒就不再問文字那一層（熱機時文字約 4 秒）
WARM_SECONDS = 2.0  # 暖機請求只是叫 Ollama 把模型載起來，不等它載完（載完要十幾二十秒）


def messages(facts: dict[str, str], image: str = "") -> list[dict]:
    """取名的提示詞。facts：place（地點）、scene（場景標題）、text（場景）、method（玩家選的做法）、note（規則讀到的那一筆）、
    attribute（結合出來的屬性）。image 是 base64 的 PNG：給了就附在 user 那一則（Ollama 的 images 欄位），沒給就只看文字。"""
    shape = SHAPE_RULE if image else SHAPE_RULE_TEXT
    user = {
        "role": "user",
        "content": (
            f"地點：{facts['place']}\n"
            f"場景：「{facts['scene']}」{facts['text']}\n"
            f"他的做法：{facts['method']}\n"
            f"他心中有一個形，一筆畫了下來（{'圖附在這裡' if image else '看不到圖'}）。規則讀到的那一筆：{facts['note']}\n"
            f"這份領悟的屬性：{facts['attribute']}\n"
            "替這份領悟取名。名字要像一種境界或天地之象，不是招式名。\n"
            f"{shape}\n{naming.FORMAT_RULES}"
        ),
    }
    if image:
        user["images"] = [image]
    return [{"role": "system", "content": SYSTEM_PROMPT}, user]


def _once(
    client: OllamaClient, content: Content, msgs: list[dict], seconds: float, person: naming.PersonCheck | None,
) -> tuple[str | None, str]:
    """送一趟（不重問）：名字過得了 naming.name_problem 才收。"""
    caller = copy.copy(client)
    own = getattr(client, "timeout", None)
    caller.timeout = min(float(own), seconds) if isinstance(own, (int, float)) else seconds
    caller.retry = False
    try:
        reply = caller.chat_structured(msgs, naming.NameReply, required_fields=["name"])
    except Exception:  # noqa: BLE001  連不上、逾時、格式不對——一律當這次沒拿到
        return None, ""
    if reply is None:
        return None, ""
    name = naming.clean_name(reply.name)
    if naming.name_problem(name, content, person) is not None:
        return None, ""
    return name, zh.to_traditional((reply.description or "").strip())


def name(
    client: OllamaClient | None, content: Content, facts: dict[str, str], image: str = "", budget: float | None = None,
    person: naming.PersonCheck | None = None,
) -> tuple[str | None, str, str]:
    """B 段：回（名字, 說明, 怎麼取到的）。怎麼取到的是 "看圖"、"文字" 或 ""（都沒拿到，名字是 None）。
    client 是 None（伺服器假人、沒開模型）就不叫。budget 沒給就照 client 自己的 timeout（兩層各一趟）。"""
    if client is None:
        return None, "", ""
    own = getattr(client, "timeout", None)
    left = budget if budget is not None else (float(own) * 2 if isinstance(own, (int, float)) else 60.0)
    if image:
        share = left * IMAGE_SHARE
        got = _once(client, content, messages(facts, image), share, person)
        left -= share
        if got[0] is not None:
            return got[0], got[1], "看圖"
    if left < MIN_TEXT_SECONDS:
        return None, "", ""
    got = _once(client, content, messages(facts), left, person)
    return (got[0], got[1], "文字") if got[0] is not None else (None, "", "")


def warm(client: OllamaClient | None) -> bool:
    """畫布一出現就送的暖機請求（0.2a：閒置後第一次看圖要 19～28 秒，玩家畫圖那幾秒剛好用來載入）：只叫 Ollama 把模型載起來、
    不取名，也不等它載完。連不上就算了（回 False），真正取名時照常走退路。"""
    if client is None or not hasattr(client, "warm"):
        return False
    try:
        return bool(client.warm(WARM_SECONDS))
    except Exception:  # noqa: BLE001
        return False
