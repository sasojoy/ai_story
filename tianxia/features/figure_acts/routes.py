"""大勢人物行動的管理者工具（功能包 tianxia/features/figure_acts/；原本寫在 server.py 的 ADMIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（admin_tools 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。"""
from tianxia.core.features import AdminTool, Outlock, OutlockJob, no_gate

from . import admin_actions, yuedan


def admin_tools(shell) -> dict[str, AdminTool]:
    """暫停中照做（paused_ok 預設 True，同原本 ADMIN_ACTIONS 那一條）。"""
    return {
        "revive_figure": AdminTool(no_gate, lambda g, b: admin_actions.revive_figure(g, str(b.get("id", "")))),
    }


# ── 鎖外工作（原本寫在 server.py，全部拆包第 69 批）：殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）；模型呼叫絕不進鎖 ──


def outlock(shell) -> Outlock:
    return Outlock(jobs=(
        OutlockJob("yuedan", lambda game: _yuedan_waiting(shell, game), lambda game, got: write_yuedan(shell, game)),
    ))


YUEDAN_RUNNING: set[str] = set()  # 月旦評正在背景寫（全服一條：有東西就是有一條在寫）


def _yuedan_waiting(shell, game) -> bool:
    """這一週的月旦評等著模型寫評語、模型叫得到、還沒有一條在寫（write_yuedan）。行動鎖內叫。"""
    if not shell.TALE_THREADS or game.client is None or YUEDAN_RUNNING:
        return False
    return game.yuedan_request() is not None


def write_yuedan(shell, game) -> bool:
    """月旦評（大勢人物擴充第三批，yuedan.py）：開一個背景執行緒寫評語。A 鎖內拿單子（Game.yuedan_request）→ B 鎖外請模型寫
    （yuedan.write，預算 Config.figure_life.yuedan_budget_seconds；排隊時當假人排）→ C 鎖內重驗同一批才換上並發出去
    （Game.apply_yuedan；寫不出來照固定句發）。開了回 True。呼叫端不能握著行動鎖。"""
    with shell.TALE_LOCK:
        if YUEDAN_RUNNING:
            return False
        YUEDAN_RUNNING.add("yuedan")

    def job() -> None:
        try:
            shell.yuedan_once(game)
        except Exception:  # noqa: BLE001 — 背景執行緒：印出來就好，評語照固定句（等太久由季的事發）
            shell.traceback.print_exc()
        finally:
            with shell.TALE_LOCK:
                YUEDAN_RUNNING.clear()

    shell.threading.Thread(target=job, name="yuedan", daemon=True).start()
    return True


def yuedan_once(shell, game) -> bool:
    """寫一批（write_yuedan 的那一圈；測試直接叫）：發了回 True。呼叫端不能握著行動鎖。"""
    with shell._locked(game):
        note = game.yuedan_request()
    if note is None:
        return False
    budget = game.content.config.figure_life.yuedan_budget_seconds
    started = shell._monotonic()

    def ask() -> dict:
        return yuedan.write(shell.within_budget(game.client, budget - (shell._monotonic() - started)), note)

    if shell.QUEUE is None:
        lines = ask()
    else:
        try:
            lines = shell.QUEUE.run(game.state.player.name, ask, fallback={}, bot=True, wait=budget)
        except (shell.Busy, shell.QueueTimeout):
            lines = {}
    with shell._locked(game):
        return game.apply_yuedan(note, lines)
