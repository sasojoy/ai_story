"""異聞的鎖外工作（手冊 G10）。只在殼建鎖外工作時才 import（__init__ 的掛鉤裡面才 from . import routes）；不 import 網頁框架。
殼的東西一律照 shell.<名字> 當下讀。

- /api/do/yiwen_step {tale, opening, node, pick, text, pay}：撞見卡上按一顆（第 252 批起三段式，照 features/guard/routes.py 的 guard_say；
  請求與回應的鍵跟異聞一一樣）。
  A shell._open_request → actions.step_request（鎖內只讀、開單；已經寫過那一顆回 Replay，C 照樣進鎖重放、不叫模型、不審字）；
  B 鎖外：自己說的先 shell.screen_text 審字（最多 12 秒），剩下的不到 step_min_write_seconds 回 busy 那一句、什麼都不動；
    再 shell.model_call → writer.write_scene（預算 step_budget_seconds 從 A 開單算起，每一趟用 within_budget 的複本）；
    同一個人已經有一件在排回 busy 那一句、排太久回殼的 BUSY_QUEUE_TIMEOUT（都是 GameError：什麼都不扣、不推進）；
  C shell.act → actions.apply_step（重驗再寫；寫壞或兩次都沒過存替身）。
  text 殼不截，這裡截 120 字（同 guard_say）；自己說的上限 typed_max 由 A 段擋。
關著的時候回空清單（不進鎖、不動帳）。"""
from __future__ import annotations

from tianxia import speech
from tianxia.core.features import Outlock
from tianxia.core.services import not_while_preparing

from . import actions, rules, writer


def outlock(shell) -> Outlock:
    return Outlock(ops={"yiwen_step": lambda g, b: yiwen_step(shell, g, b)})


def _body(b: dict) -> dict:
    pick = b.get("pick")
    if not (isinstance(pick, int) and not isinstance(pick, bool)) and pick not in ("zhupi", "typed"):
        pick = None
    return {"tale": b.get("tale"), "opening": str(b.get("opening", ""))[:40], "node": b.get("node"), "pick": pick,
            "text": str(b.get("text", ""))[:120], "pay": bool(b.get("pay"))}


def yiwen_step(shell, game, b: dict) -> list[str]:
    if not game.content.config.yiwen.enabled or not rules.on(game.content, game.state.world):
        return []
    body = _body(b if isinstance(b, dict) else {})
    started, req = shell._open_request(game, lambda: not_while_preparing(lambda g: actions.step_request(g, body))(game))
    if isinstance(req, list):
        return req
    if isinstance(req, rules.Replay):
        return shell.act(game, not_while_preparing(lambda g: actions.apply_step(g, req, None, "")))
    t = game.content.config.yiwen

    def left() -> float:
        return t.step_budget_seconds - (shell._monotonic() - started)

    busy = actions.busy_line(game, req)
    screened = shell.screen_text(game, req.text, speech.MOTTO) if req.typed else ""
    if left() < t.step_min_write_seconds:
        return [busy]  # 審字吃掉了預算：不寫、什麼都不動，字留著、再按一次會重審
    draft = None
    if screened != "bad":
        draft = shell.model_call(game, lambda: writer.write_scene(lambda: shell.within_budget(game.client, left()), req, t, left, game.content),
                                 fallback=None, left=left(), busy=busy)
    return shell.act(game, not_while_preparing(lambda g: actions.apply_step(g, req, draft, screened)))
