"""走一趟的動作表（功能包 tianxia/features/explore/；原本寫在 server.py 的 MAIN_ACTIONS、ADMIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（main_actions、admin_tools 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
走一趟的留言（/api/do/outing_say，自己寫的那一句先在鎖外審）與遊記（/api/do/outing_tale）是鎖外三段式，留在殼。"""
from tianxia import speech
from tianxia.core.features import AdminTool, Outlock, no_gate

from . import outing_actions, outing_rules as outing


def main_actions(shell) -> dict:
    return {
        # 走一趟（tianxia/outing.py）：n 是段數（1／3／5）就出發；0 或沒帶是停在要選的事上、選完接著走。沿路的事在 main.outing.trip
        "outing": lambda g, b: outing_actions.outing_go(g, shell._int(b.get("n"), 0)),
    }


def admin_tools(shell) -> dict[str, AdminTool]:
    """暫停中照做（paused_ok 預設 True，同原本 ADMIN_ACTIONS 那一條）。"""
    return {
        "outing_erase": AdminTool(no_gate, lambda g, b: outing_actions.admin_erase_inscription(g, shell._int(b.get("id"), 0))),  # 走一趟的留言：管理者抹掉一則
    }


# ── 鎖外工作（原本寫在 server.py，全部拆包第 69 批）：殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）；模型呼叫絕不進鎖 ──


def outlock(shell) -> Outlock:
    return Outlock(ops={
        "outing_say": lambda g, b: outing_say(shell, g, b),
        "outing_tale": lambda g, b: outing_tale(shell, g),  # 走一趟的遊記：模型在行動鎖外寫（見 outing_tale）
    })


def outing_say(shell, game, body: dict) -> list[str]:
    """走一趟留言：自己寫的那一句先在行動鎖外審（speech.judge），預設句不必審。"""
    text = speech.clean(str(body.get("text", ""))[:200])
    preset = shell._int(body.get("preset"), -1)
    verdict = shell.screen_text(game, text, speech.MOTTO) if preset < 0 and text else ""
    return shell.act(game, lambda g: g.outing_say(preset, text, verdict))


def outing_tale(shell, game) -> list[str]:
    """走一趟的遊記（tianxia/outing.py），三段：A Game.outing_tale_request（只讀；收了、還沒請過才開單）→ B 鎖外 outing.tale_write
    （預算 Config.jianfa.outing_tale_seconds）→ C Game.outing_set_tale 照同一趟才收；叫不動、不合用記成請過了，畫面用模板。"""
    started, request = shell._open_request(game, game.outing_tale_request)
    if isinstance(request, list):
        return request
    total = game.content.config.jianfa.outing_tale_seconds

    def write():
        client = shell.within_budget(game.client, total - (shell._monotonic() - started))
        return outing.tale_write(client, request)

    text = shell.model_call(game, write, fallback=None, left=total - (shell._monotonic() - started), busy=shell.BUSY_FREE_TEXT)
    return shell.act(game, lambda g: g.outing_set_tale(text, request))
