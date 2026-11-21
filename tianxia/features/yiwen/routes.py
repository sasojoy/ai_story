"""異聞的鎖外工作（手冊 G10）。只在殼建鎖外工作時才 import（__init__ 的掛鉤裡面才 from . import routes）；不 import 網頁框架。
殼的東西一律照 shell.<名字> 當下讀。

- /api/do/yiwen_step {tale, opening, node, pick, text, pay}：撞見卡上按一顆（這一批是平鋪：進鎖就做、不叫模型；異聞二換成三段式，請求與回應的鍵不變）。
  text 殼不截，這裡截 120 字（同 features/guard/routes.py 的 guard_say）。
關著的時候回空清單（不進鎖、不動帳）。"""
from __future__ import annotations

from tianxia.core.features import Outlock
from tianxia.core.services import not_while_preparing

from . import actions, rules


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
    return shell.act(game, not_while_preparing(lambda g: actions.step(g, body)))
