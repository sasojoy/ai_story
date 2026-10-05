"""取名（從 craft.py 搬來，武學與成長設計 3.4、3.6）：模型只給名字和一句說明，一個數字都不碰；
過濾在登記之前跑（名字會永久進全服的登記表）；叫不動或取壞了就走決定性的退路字表。"""
from __future__ import annotations

import hashlib

from pydantic import BaseModel

from . import zh
from .models import Content
from .ollama_client import OllamaClient

NAME_MIN_CHARS, NAME_MAX_CHARS = 2, 6
NAME_ATTEMPTS = 3  # 模型最多試幾次（第一次 + 兩次重生成）；全部失敗就走決定性組名
CLAIM_ATTEMPTS = 4  # 名字被占用時，用決定性組名換名字再試幾次

SYSTEM_PROMPT = (
    "你是武俠小說裡替武功與意境取名的人。你只負責取名字、寫一句話的說明，"
    "**絕對不要提到任何數字、品質、等級或威力**。全程使用繁體中文。"
)
FORMAT_RULES = (
    f"name：{NAME_MIN_CHARS}～{NAME_MAX_CHARS} 個中文字，必須原創，"
    "不可使用金庸等武俠小說裡的專有名詞，不要標點符號。\n"
    "description：20 字以內，說它是什麼樣子。"
)


class NameReply(BaseModel):
    """模型唯一被允許回傳的東西：名字與一句說明。這裡刻意沒有任何數字欄位。"""

    name: str
    description: str = ""


def clean_name(raw: str) -> str:
    """把名字整理乾淨：去掉空白與書名號之類的包裝，再轉成繁體（含異體字表，見 zh.py）。"""
    name = (raw or "").strip()
    for ch in "【】《》「」〈〉『』()（）[]<>\"'“”‘’ \t\n　":
        name = name.replace(ch, "")
    return zh.to_traditional(name)


def name_problem(name: str, content: Content) -> str | None:
    """名字過不了過濾的原因；None＝可以用。全服重名不在這裡查（那要看資料庫，見 world.is_skill_name_taken）。"""
    if not (NAME_MIN_CHARS <= len(name) <= NAME_MAX_CHARS):
        return f"長度要 {NAME_MIN_CHARS}~{NAME_MAX_CHARS} 個字"
    if not all("一" <= ch <= "鿿" for ch in name):
        return "只能是中文字"
    for banned in content.banned_names:
        if banned and banned in name:
            return f"用到了既有作品的專有名詞（{banned}）"
    if any(name == m.name for m in content.materials.values()):
        return "跟素材同名"
    if any(name == ch.name for ch in content.characters.values()):
        return "跟人物同名"
    if any(name == sk.name for sk in content.skills.values()):
        return "跟內容裡的武學同名"
    if any(name == ins.name for ins in content.insights.values()):
        return "跟意境同名"
    return None


def propose(client: OllamaClient | None, content: Content, messages: list[dict[str, str]]) -> tuple[str | None, str]:
    """請模型命名，回傳（通過過濾的名字, 一句說明）；連不上、取壞了都回 (None, "")，呼叫端走退路字表。
    client 是 None（伺服器假人，bot_runner 會把 game.client 設成 None）時不叫模型。"""
    if client is None:
        return None, ""
    for _ in range(NAME_ATTEMPTS):
        try:
            reply = client.chat_structured(messages, NameReply, required_fields=["name"])
        except Exception:  # noqa: BLE001  連不上、404、逾時——一律當作這次沒取到名字
            return None, ""
        if reply is None:
            return None, ""
        name = clean_name(reply.name)
        if name_problem(name, content) is None:
            return name, zh.to_traditional((reply.description or "").strip())
    return None, ""


def fallback_name(content: Content, key: str, kind: str, salt: int = 0) -> str:
    """決定性組名：同一個配方永遠組出同一個名字，離線也能玩、全服也一致。kind 是「內功」「武學」「意境」。
    `tests/test_real_content.py` 的整季模擬把模型 mock 掉，走的就是這條路。"""
    names = content.craft_names
    suffixes = {"內功": names.neigong, "武學": names.wugong, "意境": names.insight}[kind]
    digest = hashlib.sha256(f"{key}#{salt}".encode()).digest()
    return names.prefixes[digest[0] % len(names.prefixes)] + suffixes[digest[1] % len(suffixes)]
