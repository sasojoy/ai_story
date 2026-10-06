"""取名（從 craft.py 搬來，武學與成長設計 3.4、3.6）：模型只給名字和一句說明，一個數字都不碰；
過濾在登記之前跑（名字會永久進全服的登記表）；叫不動或取壞了就走決定性的退路字表。

開爐的首次取名分三段（最終審查 Critical 1，照人物對話 server.prepare_dialogue 的做法）：
  A（行動鎖內、很快）fusion.forge_request／Game.forge_request 開一張 NamingRequest；
  B（鎖外、很慢）generate：只拿單子與模型，不碰狀態、不拿鎖（之後線上架構第 2 期的模型佇列只換掉這一段）；
  C（鎖內、很快）Game.forge(..., proposed=...)：recheck 再過一次過濾，登記、收費。
合到舊的（設計 12.2）時，B 段不取新名字而是 pick：請模型從清單裡挑一個已知的名字；挑不到（連不上、回了清單外的）就是
(None, "")，C 段改由規則挑（landing.choose）。
這個模組不讀時鐘（引擎不讀時鐘）：B 段的總時間用 budget（秒）管——每一次呼叫給模型的 timeout 照給出去的扣，
給出去的加起來不超過 budget；預算由呼叫端（server.py）算好傳進來。"""
from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from . import zh
from .models import Content
from .ollama_client import OllamaClient

NAME_MIN_CHARS, NAME_MAX_CHARS = 2, 6
NAME_ATTEMPTS = 3  # 模型最多試幾次（第一次 + 兩次重生成）；全部失敗就走決定性組名
CLAIM_ATTEMPTS = 4  # 名字被占用時，用決定性組名換名字再試幾次
# OllamaClient.chat_structured 一次呼叫最多送兩趟（第一次＋格式不對、逾時時的重問），兩趟都用同一個 timeout
POSTS_PER_CALL = 2
MIN_POST_SECONDS = 1.0  # 有預算時，一趟分不到這麼多秒就不叫了（叫了也等不到）


@dataclass(frozen=True)
class NamingRequest:
    """A 段（行動鎖內、很快）開的單子：這一爐要模型取名或挑一個時，B 段需要的全部東西。拿著它就能在鎖外叫模型，不必再碰遊戲狀態。
    kind 是 "fuse"（武學＋意境）、"merge"（意境＋意境）或 "blend"（武學＋武學）；key 是配方鍵；name_kind 是退路字表的種類（內功、武學、意境）。
    choices 不是空的：這一爐合到舊的（武學與成長設計 12.2），模型只能從這幾個名字裡挑一個（naming.pick），不取新名字。"""

    kind: str
    key: str
    name_kind: str
    messages: list[dict[str, str]]
    choices: tuple[str, ...] = ()


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


PersonCheck = Callable[[str], bool]  # 這個名字是不是江湖上某個角色的名號（WorldStateStore.is_character_name）
PERSON_CLASH = "跟江湖上的人物同名"  # 真人、假人都回這一句：看不出那個名號是不是假人（FB-069）
PRESET_CLASH = "跟師門傳下來的武學同名"  # 師門配方（content/preset_recipes.json，新手引導計畫一）的名字：模型、玩家取的名字不能撞它（name_problem）


def name_problem(name: str, content: Content, person: PersonCheck | None = None) -> str | None:
    """名字過不了過濾的原因；None＝可以用。全服重名不在這裡查（那要看資料庫，見 world.is_skill_name_taken）。
    person 給了就也擋角色的名號（FB-069：玩家定名、模型取名、鎖內重驗都給 world.is_character_name；
    內容的驗證與退路字表只看內容、不給）。排在字數之後、字元之前，所以換了大小寫的英文名號也回同一句話。"""
    if not (NAME_MIN_CHARS <= len(name) <= NAME_MAX_CHARS):
        return f"長度要 {NAME_MIN_CHARS}~{NAME_MAX_CHARS} 個字"
    if person is not None and person(name):
        return PERSON_CLASH
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
    if any(name == recipe.name for recipe in content.preset_recipes):
        return PRESET_CLASH  # 師門配方的名字留給那一筆配方（新手引導計畫一）
    return None


def _ask(
    client: OllamaClient | None, messages: list[dict[str, str]],
    accept: Callable[[NameReply], tuple[str, str] | None], budget: float | None,
) -> tuple[str | None, str]:
    """叫模型、照預算扣時間，最多 NAME_ATTEMPTS 次（行動鎖內的複本只一次，見下）；accept 收下這一次的回覆就回它的結果，
    不收就在還有預算時再問一次。client 是 None、連不上、回 None、預算用完都回 (None, "")。預算的扣法見 propose。"""
    if client is None:
        return None, ""
    left = budget
    own = getattr(client, "timeout", None)
    # 行動鎖內的複本（retry 是 False，Game._quick_client）只試一次：鎖內任何一步模型呼叫最多佔住鎖 in_lock_model_timeout 秒，
    # 取壞了就直接走退路。鎖外最多 NAME_ATTEMPTS 次、每次最多兩趟，但要看預算分得完分不完：每一次先扣掉
    # min(timeout, 剩下的 ÷ 2) 的兩趟——伺服器現在的數字（naming_budget_seconds 60、ollama_timeout 120）第一次就分到
    # 30 秒兩趟、把 60 秒用光，所以實際上只問一次，取壞或挑到清單外的名字就直接走退路、不重問；
    # 只有預算比 timeout 的兩倍多（或 client 的 timeout 很短）、或沒給預算（整季機器人、腳本、測試）時才會真的重問
    attempts = 1 if getattr(client, "retry", True) is False else NAME_ATTEMPTS
    for _ in range(attempts):
        caller = client
        if left is not None:
            per_post = min(float(own) if isinstance(own, (int, float)) else left, left / POSTS_PER_CALL)
            if per_post < MIN_POST_SECONDS:
                return None, ""
            caller = copy.copy(client)
            caller.timeout = per_post
            left -= per_post * POSTS_PER_CALL
        try:
            reply = caller.chat_structured(messages, NameReply, required_fields=["name"])
        except Exception:  # noqa: BLE001  連不上、404、逾時——一律當作這次沒拿到
            return None, ""
        if reply is None:
            return None, ""
        got = accept(reply)
        if got is not None:
            return got
    return None, ""


def propose(
    client: OllamaClient | None, content: Content, messages: list[dict[str, str]], budget: float | None = None,
    person: PersonCheck | None = None,
) -> tuple[str | None, str]:
    """請模型命名，回傳（通過過濾的名字, 一句說明）；連不上、取壞了、預算用完都回 (None, "")，呼叫端走退路字表。
    client 是 None（伺服器假人，bot_runner 會把 game.client 設成 None）時不叫模型。

    budget（秒）：整段取名最多花多久（server.py 從 Config.naming_budget_seconds 算好傳進來；沒給就照 client 自己的
    timeout，整季機器人、腳本、測試直接呼叫時是這樣）。不讀時鐘，照給出去的 timeout 扣：每一次呼叫拿 client 的複本、
    timeout 設成 min(client.timeout, 剩下的 ÷ POSTS_PER_CALL)，連重問那一趟都用完也不超過剩下的；
    分不到 MIN_POST_SECONDS 就不叫了。原本那個 client 不動（同一個角色的別的請求可能正在用它）。
    person：角色名號的查詢（見 name_problem）；模型取到角色的名號跟取壞了一樣，再請它取一次。"""

    def accept(reply: NameReply) -> tuple[str, str] | None:
        name = clean_name(reply.name)
        if name_problem(name, content, person) is not None:
            return None
        return name, zh.to_traditional((reply.description or "").strip())

    return _ask(client, messages, accept, budget)


def pick(
    client: OllamaClient | None, messages: list[dict[str, str]], choices: tuple[str, ...], budget: float | None = None,
) -> tuple[str | None, str]:
    """合到舊的（武學與成長設計 12.2）：請模型從 choices 挑一個，回 (那個名字, "")；挑不到是 (None, "")，呼叫端改由規則挑
    （landing.choose）。回覆照取名的方式整理（括號、繁簡）再比對，清單外的名字不收、再問一次。不碰數字。
    不過命名過濾、也不擋角色名號（FB-069）：這裡不產生新名字，清單裡都是這一季已經登記、當時過了過濾的名字，
    挑到哪一個那一門都還是那個名字；擋了只會改由規則挑另一門，名字一樣不會變。"""
    allowed = set(choices)

    def accept(reply: NameReply) -> tuple[str, str] | None:
        name = clean_name(reply.name)
        return (name, "") if name in allowed else None

    return _ask(client, messages, accept, budget)


def generate(
    client: OllamaClient | None, content: Content, request: NamingRequest, budget: float | None = None,
    person: PersonCheck | None = None,
) -> tuple[str | None, str]:
    """B 段（鎖外、很慢）：拿 A 段開的單子請模型取名（或從清單挑一個，request.choices 不是空的時），回傳（名字, 說明）；
    取不到是 (None, "")。只拿單子、模型與內容（過濾要用），不碰任何遊戲狀態、不拿行動鎖——可以單獨呼叫，也可以整段換成模型佇列。
    person 是角色名號的查詢（server 給 world.is_character_name：唯讀的快照，不拿行動鎖），只用在取新名字。"""
    if request.choices:
        return pick(client, request.messages, request.choices, budget=budget)
    return propose(client, content, request.messages, budget=budget, person=person)


def recheck(
    content: Content, proposed: tuple[str | None, str], person: PersonCheck | None = None,
) -> tuple[str | None, str]:
    """C 段（鎖內）登記之前，把鎖外拿到的名字再過一次完整的過濾：整理包裝、轉繁體（含異體字表）、長度與字、禁用詞、
    跟素材／人物／內容武學／意境同名，給了 person 也擋角色的名號（FB-069）。過不了就是 (None, "")，呼叫端走退路字表。
    全服重名不在這裡查：登記時（world.claim_recipe／claim_insight_recipe 的 _name_taken）在同一筆交易裡原子判斷，
    同時有兩個配方拿到同一個名字也只有一個登記得上。"""
    name, note = proposed
    if name is None:
        return None, ""
    name = clean_name(name)
    if name_problem(name, content, person) is not None:
        return None, ""
    return name, zh.to_traditional((note or "").strip())


def fallback_name(content: Content, key: str, kind: str, salt: int = 0, tianji: int = 0) -> str:
    """決定性組名：同一個配方永遠組出同一個名字，離線也能玩、全服也一致。kind 是「內功」「武學」「意境」。
    種子是配方鍵＋這一季的天機（天機 0 照舊只用配方鍵，跟 martial_arts.generate_from_name 同一個規矩），
    所以名字只看配方與這一季，不看誰先到；同一個配方每季組出不同的名字。
    `tests/test_real_content.py` 的整季模擬把模型 mock 掉，走的就是這條路。"""
    names = content.craft_names
    suffixes = {"內功": names.neigong, "武學": names.wugong, "意境": names.insight}[kind]
    seed = key if tianji == 0 else f"{tianji}|{key}"
    digest = hashlib.sha256(f"{seed}#{salt}".encode()).digest()
    return names.prefixes[digest[0] % len(names.prefixes)] + suffixes[digest[1] % len(suffixes)]
