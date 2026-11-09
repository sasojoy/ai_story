"""親衛隊長的玩家動作與鎖外工作（手冊 G10）。只在殼建動作表、鎖外工作時才 import（__init__ 的掛鉤裡面才 from . import routes）；不 import 網頁框架。
殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。

- /api/do/guard_rename {name}：親衛隊長那一頁上替他改名（一次）；/api/do/guard_along {on}：出門帶不帶他（鎖外工作的表，進鎖就做，不叫模型）。
- /api/do/guard_say {text}：自己寫的那一句，三段：A actions.say_request（鎖內只讀）→ B 鎖外 rules.judge_say（預算 Config.guard.budget_seconds）
  → C actions.apply_say 重驗同一件才記。
- 背景寫字 guard（表外的格，接在 OUTLOCK_ORDER 表尾）：有一件事要生（want）時放鎖之後開一條執行緒：A actions.event_request → B rules.write_event
  （出師結算是 rules.settle，預算 Config.guard.settle_budget_seconds）→ C actions.apply_event（寫不出來換固定的）。
關著的時候每一條都回 rules.NO_SUCH（不叫模型、不動帳）。"""
from __future__ import annotations

from tianxia.core.features import Outlock, OutlockJob
from tianxia.core.services import not_while_preparing

from . import actions, rules

RUNNING: set[str] = set()  # 正在背景生事件的角色（名號；一人一條）


def _on(game) -> bool:
    return bool(game.content.config.guard.enabled)


def _plain(shell, game, step) -> list[str]:
    """親衛隊長那一頁上不叫模型的那兩顆（改名、帶不帶）：也走鎖外工作的表（包自己的 /api/do/{op}，不加殼的 MAIN_ACTION_ORDER），進鎖做完就回。"""
    if not _on(game):
        return [rules.NO_SUCH]
    return shell.act(game, not_while_preparing(step))


def outlock(shell) -> Outlock:
    return Outlock(
        ops={
            "guard_say": lambda g, b: guard_say(shell, g, str(b.get("text", ""))[:120]),
            "guard_rename": lambda g, b: _plain(shell, g, lambda game: actions.rename(game, str(b.get("name", ""))[:12])),
            "guard_along": lambda g, b: _plain(shell, g, lambda game: actions.set_along(game, bool(b.get("on")))),
        },
        jobs=(OutlockJob("guard", lambda game: _waiting(shell, game), lambda game, got: write_event(shell, game, got)),),
    )


def guard_say(shell, game, text: str) -> list[str]:
    if not _on(game):
        return [rules.NO_SUCH]
    started, request = shell._open_request(game, lambda: actions.say_request(game, text))
    if isinstance(request, list):
        return request
    t = game.content.config.guard

    def ask():
        return rules.judge_say(shell.within_budget(game.client, t.budget_seconds - (shell._monotonic() - started)), request, t)

    judged = shell.model_call(game, ask, fallback=None, left=t.budget_seconds - (shell._monotonic() - started), busy=shell.BUSY_FREE_TEXT)
    return shell.act(game, lambda g: actions.apply_say(g, request, judged))


def _waiting(shell, game) -> str | None:
    """行動鎖內問：這個人有一件事等著生、模型叫得到、還沒有一條在寫：回名號。"""
    if not _on(game) or not shell.TALE_THREADS or game.client is None or actions.event_request(game) is None:
        return None
    name = game.state.player.name
    return None if name in RUNNING else name


def event_once(shell, game) -> bool:
    """生一件（write_event 的那一圈；測試直接叫）。呼叫端不能握著行動鎖。"""
    with shell._locked(game):
        request = actions.event_request(game)
    if request is None:
        return False
    t = game.content.config.guard
    started = shell._monotonic()
    budget = t.settle_budget_seconds if request.kind == "settle" else t.budget_seconds
    write = rules.settle if request.kind == "settle" else rules.write_event  # 出師結算或生一件事（家裡、路上、信、出師考驗）

    def ask():
        return write(shell.within_budget(game.client, budget - (shell._monotonic() - started)), request, t)

    if shell.QUEUE is None:
        event = ask()
    else:
        try:
            event = shell.QUEUE.run(shell.TALE_OWNER, ask, fallback=None, bot=True, wait=budget)
        except (shell.Busy, shell.QueueTimeout):
            event = None
    with shell._locked(game):
        done = actions.apply_event(game, request, event)
        if done:
            shell.open_characters().save(game.state)
        return done


def write_event(shell, game, name: str) -> bool:
    with shell.TALE_LOCK:
        if name in RUNNING:
            return False
        RUNNING.add(name)

    def job() -> None:
        try:
            event_once(shell, game)
        except Exception:  # noqa: BLE001 — 背景執行緒：印出來就好，等太久 on_sync 會換固定事件
            shell.traceback.print_exc()
        finally:
            with shell.TALE_LOCK:
                RUNNING.discard(name)

    shell.threading.Thread(target=job, name="guard-event", daemon=True).start()
    return True
