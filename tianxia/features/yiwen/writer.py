"""異聞的 B 段（第 252 批，總計畫「異聞二」）：一次寫幕的呼叫＋程式檢查沒過時重問一次。鎖外跑（routes.yiwen_step 經 shell.model_call 叫）。
只碰 client：不碰狀態、不拿鎖、不讀時鐘（剩下幾秒由 routes 傳 left 這個 callable 進來）、不 import 殼。
client_for() 每叫一次給一份 within_budget 的複本（剩下的 ÷ 2；chat_structured 自己 JSON 壞的那一趟重問算在裡面）；給不出就是 None。
回 None＝叫不到或寫壞（連不上、逾時、回不成 JSON）：C 存替身。回 SceneDraft：problems 空＝合格；非空＝兩次都沒過（C 存替身，模型的字不存）；
verdict improper 且這一步是自己說的：C 回 refuse_typed、tries 加一（不重問）。"""
from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from tianxia import zh  # 共用層（模型的字轉繁體）

from . import rules

logger = logging.getLogger(__name__)


class SceneReply(BaseModel):
    """第一、二步：兩段、三個做法、帳（設計 4.2 那一張表）。欄位都有預設值：require_in_schema 把 required_fields 寫進 schema。"""
    verdict: str = rules.OK
    reason: str = ""
    text: list[str] = []
    options: list[str] = []
    ledger: list[str] = []


class EndReply(BaseModel):
    """第三步：只要兩段（引擎接收場句）。"""
    verdict: str = rules.OK
    reason: str = ""
    text: list[str] = []


def _ask(client, messages: list[dict], last: bool):
    if last:
        return client.chat_structured(messages, EndReply, required_fields=["verdict", "text"], require_in_schema=True)
    return client.chat_structured(messages, SceneReply, required_fields=["verdict", "text", "options", "ledger"], require_in_schema=True)


def _draft(reply, request: rules.YiwenRequest) -> rules.SceneDraft:
    last = request.depth >= rules.DEPTH

    def lines(values) -> list[str]:  # 只轉繁體、去頭尾空白；夾英文由 check_scene 的 latin 那一條擋（整幕換替身）
        return [zh.to_traditional(str(x)).strip() for x in (values or [])]

    verdict = str(getattr(reply, "verdict", rules.OK) or rules.OK).strip().lower()
    return rules.SceneDraft(
        verdict=rules.IMPROPER if verdict == rules.IMPROPER else rules.OK,
        text=rules.tidy_text(lines(getattr(reply, "text", []))),  # 第 263 批：丟空段、丟漏進來的帳、黏成一段的照空行切（不改字）
        options=[] if last else lines(getattr(reply, "options", [])),
        ledger=[] if last else lines(getattr(reply, "ledger", [])),
    )


def _check(draft: rules.SceneDraft, request: rules.YiwenRequest, content) -> list[str]:
    if draft.verdict == rules.IMPROPER:
        return [] if request.typed else ["improper"]  # 猜法那一步回 improper：當成檢查沒過（自己說的交給 C 回 refuse_typed）
    return rules.check_scene(draft, depth=request.depth, opening={}, typed_words=request.typed_words, content=content, known=request.known)


def _retry_note(problems: list[str], draft: rules.SceneDraft) -> str:
    said = rules.problem_note(draft.text, problems)  # 第 263 批：哪一段、幾字、太長還是太短（其他代碼照 PROBLEM_TEXT）
    return f"上一次寫的這一幕有這些毛病：{said}照原本的要求重寫一次，只回 JSON。"


def write_scene(client_for, request: rules.YiwenRequest, tuning, left, content) -> rules.SceneDraft | None:
    """寫一幕：叫一次；檢查沒過、tuning.retry 還有、剩下的秒數（left()）還夠 step_min_write_seconds、client_for() 還給得出，
    就把毛病換成一句話貼回去重問。還不行回帶 problems 的 SceneDraft。例外一律吞掉（不重問：連不上再叫一次只是白等）。"""
    client = client_for()
    if client is None:
        return None
    last = request.depth >= rules.DEPTH
    messages = [{"role": "user", "content": request.prompt}]
    try:
        reply = _ask(client, messages, last)
    except Exception as e:  # noqa: BLE001 — 叫到了但連不上、逾時、回不成 JSON：這一步照寫壞處理（替身）
        logger.warning("異聞寫幕失敗，換替身：%r", e)
        return None
    draft = _draft(reply, request)
    problems = _check(draft, request, content)
    tries = 0
    while problems and tries < int(tuning.retry) and left() >= tuning.step_min_write_seconds:
        tries += 1
        client = client_for()
        if client is None:
            break
        answer = json.dumps({"verdict": draft.verdict, "text": draft.text, "options": draft.options, "ledger": draft.ledger}, ensure_ascii=False)
        messages = messages + [{"role": "assistant", "content": answer}, {"role": "user", "content": _retry_note(problems, draft)}]
        try:
            reply = _ask(client, messages, last)
        except Exception as e:  # noqa: BLE001
            logger.warning("異聞重問失敗，換替身：%r", e)
            break
        draft = _draft(reply, request)
        problems = _check(draft, request, content)
    draft.problems = list(problems)
    return draft
