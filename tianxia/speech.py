"""玩家寫給別人看的一句話（Joy 2026-10-19：挑釁時可以對對方說一句話、名帖上自題一句，「要防止玩家說髒話侮辱人」）。

兩道擋：
  一、字表（content/banned_words.json，髒話與辱罵）：比對前先去掉空白、標點、符號，英文換小寫，所以「幹．你」「白 癡」也擋得到。
     純函式，鎖內鎖外都能用，伺服器的 C 段一定再查一次。
  二、模型（judge）：字表擋不到換個說法的辱罵。很短的一次結構化呼叫，只回 ok 一欄；在行動鎖外（server.screen_text），
     結果交給 C 段（"ok"／"bad"；叫不動、逾時、預算用完是空字串＝只看字表照送）。
挑釁本來就要有點火藥味：挑釁那一句只擋髒話、人身攻擊、歧視、性騷擾，不擋「你這三腳貓」這種江湖嗆聲（TAUNT）；
名帖自題公開給所有看名帖的人，另外也擋廣告、聯絡方式與網址（MOTTO）。
假人不寫自由文字（伺服器假人設計），自題那一句從 content/mingtie.json 的句庫挑、不必過模型。
被擋下時不管是哪一道擋的都回同一句（BLOCKED），不透露是誰擋的。"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel

from .models import Content
from .zh import to_traditional

logger = logging.getLogger(__name__)

BLOCKED = "這話說得太難聽，江湖人也聽不下去。換句話吧。"  # 待 joy 潤
TOO_LONG = "最多 {n} 個字。"
TAUNT, MOTTO = "taunt", "motto"
Kind = Literal["taunt", "motto"]
JUDGE_PREDICT = 16  # {"ok": false} 不到十個 token，多留一點不被截斷
_STRIP = re.compile(r"[\s\W_]+", re.UNICODE)
_URLISH = re.compile(r"(https?|www\.|\.com|\.tw|\.net|\bline\b|\big\b|@)", re.IGNORECASE)


class Verdict(BaseModel):
    ok: bool


PROMPT = {
    TAUNT: (
        "你是一個武俠網路遊戲的聊天審核員。玩家在遊戲裡挑釁另一個玩家，附了一句話。"
        "江湖人互相嗆聲、看不起對方的身手、放狠話都可以（例如「你這三腳貓也敢來」「改天讓你見識見識」）。"
        "不可以的是：髒話、罵人祖宗親屬、針對現實的人身攻擊、性別或族群歧視、性騷擾、威脅現實中的人身安全。"
        "諧音、拆字、注音、英文縮寫的髒話也算。只回 JSON：{\"ok\": true} 表示可以送出，{\"ok\": false} 表示要擋下。"
    ),
    MOTTO: (
        "你是一個武俠網路遊戲的審核員。玩家在自己的名帖上題一句話，所有人都看得到。"
        "詩句、自述、江湖氣的豪語、玩笑都可以。不可以的是：髒話、辱罵或嘲笑別人、歧視、色情、"
        "廣告、聯絡方式（電話、帳號、群組）、網址。諧音、拆字、注音、英文縮寫的髒話也算。"
        "只回 JSON：{\"ok\": true} 表示可以，{\"ok\": false} 表示要擋下。"
    ),
}


def clean(text: str) -> str:
    """玩家打的字：去掉頭尾空白、換行換成空白、轉繁體（模型產出以外的字也照轉，免得簡體字繞過字表）。"""
    return to_traditional(" ".join(str(text or "").split()))


def squash(text: str) -> str:
    """比對字表用的寫法：全形半形統一、英文小寫、去掉空白標點符號。"""
    return _STRIP.sub("", unicodedata.normalize("NFKC", text).lower())


def word_problem(text: str, content: Content, kind: Kind, limit: int) -> str | None:
    """字表與字數這一道：不行回那一句話，行是 None。空字串是行（不寫也可以）。"""
    if len(text) > limit:
        return TOO_LONG.format(n=limit)
    flat = squash(text)
    if any(squash(word) and squash(word) in flat for word in content.banned_words):
        return BLOCKED
    if kind == MOTTO and (_URLISH.search(text) or sum(ch.isdigit() for ch in unicodedata.normalize("NFKC", text)) >= 6):
        return BLOCKED  # 名帖公開：網址、帳號、一長串數字（電話）不給印
    return None


def judge(client, text: str, kind: Kind) -> str:
    """模型這一道（三段式的 B 段，鎖外）："ok"、"bad"；沒有 client、叫不動、怪值是空字串（只看字表）。"""
    if client is None or not text:
        return ""
    messages = [{"role": "system", "content": PROMPT[kind]}, {"role": "user", "content": f"那一句話：「{text}」"}]
    try:
        result = client.chat_structured(messages, Verdict, temperature=0.0, num_predict=JUDGE_PREDICT)
    except Exception as e:  # noqa: BLE001  叫不動就只看字表
        logger.warning("審一句話失敗，只看字表：%r", e)
        return ""
    ok = getattr(result, "ok", None)
    return "" if not isinstance(ok, bool) else ("ok" if ok else "bad")


def problem(text: str, content: Content, kind: Kind, limit: int, verdict: str = "") -> str | None:
    """C 段：字表再查一次，加上 B 段模型的判斷（"bad" 擋下）。"""
    return word_problem(text, content, kind, limit) or (BLOCKED if verdict == "bad" else None)
