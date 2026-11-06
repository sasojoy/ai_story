"""酒肆的動作表（功能包 tianxia/features/tavern/；原本寫在 server.py 的 MAIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（main_actions 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
問酒家（/api/do/tavern_ask）與鄰桌閒談的背景寫字是鎖外工作，第 69 批搬進這個檔（outlock 掛鉤；tests/server/test_server.py 的 _users_in_server 掃這個檔看函式名，裡面寫 shell.model_call、shell.QUEUE，不要先存成別的變數）。"""
from tianxia.core.features import Outlock, OutlockJob

from . import actions, rules as tavern


def main_actions(shell) -> dict:
    return {
        # 酒肆那一頁（企劃者 2026-10-18）：op 是 news、seek、ties、material、wall、treat、hide、trace；target 是名號或素材 id、text 是題壁那一句
        "tavern": lambda g, b: actions.tavern_do(g, str(b.get("op", "")), str(b.get("target", ""))[:20], str(b.get("text", ""))[:40]),
    }


# ── 鎖外工作（原本寫在 server.py，全部拆包第 69 批）：殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）；模型呼叫絕不進鎖 ──


def outlock(shell) -> Outlock:
    return Outlock(
        ops={
            "tavern_ask": lambda g, b: tavern_ask(shell, g, str(b.get("text", ""))[:60]),  # 問酒家：回話在行動鎖外寫（見 tavern_ask）
        },
        jobs=(
            OutlockJob("chatter", lambda game: _chatter_waiting(shell, game), lambda game, got: write_chatter(shell, game, got)),
        ),
    )


CHATTER_RUNNING: set[str] = set()  # 正在背景寫鄰桌閒談的酒肆（一間一條；地點 id）


def _chatter_waiting(shell, game) -> str | None:
    """這個人開著的酒肆該換一段閒談、模型叫得到、這一間還沒有一條在寫（write_chatter）：回地點 id。行動鎖內叫。"""
    if not shell.TALE_THREADS or game.client is None or game.tavern_chatter_request() is None:
        return None
    place = game.state.player.location
    return None if place in CHATTER_RUNNING else place


def write_chatter(shell, game, place: str) -> bool:
    """酒肆鄰桌閒談：開一個背景執行緒寫一段。A 鎖內拿單子（Game.tavern_chatter_request）→ B 鎖外請模型寫（tavern.chatter_write，
    預算 Config.tavern.ask_budget_seconds；排隊時當假人排在真人後面）→ C 鎖內重驗才記（Game.apply_tavern_chatter；寫不出來記空的，
    這一陣子照固定句）。開了回 True。呼叫端不能握著行動鎖。"""
    with shell.TALE_LOCK:
        if place in CHATTER_RUNNING:
            return False
        CHATTER_RUNNING.add(place)

    def job() -> None:
        try:
            shell.chatter_once(game)
        except Exception:  # noqa: BLE001 — 背景執行緒：印出來就好，閒談照固定句
            shell.traceback.print_exc()
        finally:
            with shell.TALE_LOCK:
                CHATTER_RUNNING.discard(place)

    shell.threading.Thread(target=job, name="tavern-chatter", daemon=True).start()
    return True


def chatter_once(shell, game) -> bool:
    """寫一段（write_chatter 的那一圈；測試直接叫）：記了寫好的回 True。呼叫端不能握著行動鎖。"""
    with shell._locked(game):
        request = game.tavern_chatter_request()
    if request is None:
        return False
    budget = game.content.config.tavern.ask_budget_seconds
    started = shell._monotonic()

    def ask() -> list[str]:
        return tavern.chatter_write(shell.within_budget(game.client, budget - (shell._monotonic() - started)), request)

    if shell.QUEUE is None:
        lines = ask()
    else:
        try:
            lines = shell.QUEUE.run(shell.TALE_OWNER, ask, fallback=[], bot=True, wait=budget)
        except (shell.Busy, shell.QueueTimeout):
            lines = []
    with shell._locked(game):
        return game.apply_tavern_chatter(request, lines)


def tavern_ask(shell, game, text: str) -> list[str]:
    """問酒家（酒肆，設計第八節），三段：A Game.tavern_ask_request（只讀；問到秘密的單子不叫模型）→ B 鎖外 tavern.ask_write
    （預算 Config.tavern.ask_budget_seconds）→ C Game.tavern_ask 重驗同一間、同一句再收錢；叫不動模型退全額。"""
    started, request = shell._open_request(game, lambda: game.tavern_ask_request(text))
    if isinstance(request, list):
        return request
    total = game.content.config.tavern.ask_budget_seconds

    def write():
        client = shell.within_budget(game.client, total - (shell._monotonic() - started))
        return tavern.ask_write(client, request)

    reply = None if request.secret else shell.model_call(game, write, fallback=None, left=total - (shell._monotonic() - started),
                                                     busy=shell.BUSY_FREE_TEXT)
    return shell.act(game, lambda g: g.tavern_ask(request.question, reply, request=request))
