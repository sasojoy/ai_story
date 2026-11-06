"""地盤的 API（功能包 tianxia/features/territory_acts/；原本寫在 server.py，開發規範手冊 3.2）：殼（server 模組，參數 shell）照 FEATURES 掛，
/api/do/{op} 的管理者工具也照清單接（admin_tools）。

- GET /api/xingshi：見聞的「形勢」（這一季每天一篇的〈天下形勢〉；只讀，不叫模型——文章在背景寫，server.write_xingshi 留在殼）
- 管理者五個救場工具：op 名字照舊。立刻下戰書叫 admin_conquest_letter、不叫 conquest_letter：api_do 先查功能包的管理者工具，同名會把玩家的下戰書
  （MAIN_ACTIONS["conquest_letter"]，全部拆包第 68 批搬進這個檔的 main_actions）整個蓋掉（FB-609）。領地爭奪、〈天下形勢〉關著時各動作自己回一句（跟原本一樣，沒有 404）。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
"""
from fastapi import APIRouter, Request

from tianxia.core.features import AdminTool, Outlock, OutlockJob

from . import admin_actions, letter_actions, xingshi, xingshi_actions


def main_actions(shell) -> dict:
    return {
        # 領地爭奪：下戰書（翻地與爭搶，輿圖簡化設計 4.4；這一週在任的第 4 階、自己那一邊在這一塊的進度到門檻）。每天投票拿掉了（PM 2026-10-20）
        "conquest_letter": lambda g, b: letter_actions.conquest_letter(g, str(b.get("loc", ""))),
    }


def _gate() -> None:
    """這一包沒有總開關（原本 ADMIN_ACTIONS 那五個也沒有 404）：什麼都不擋，各動作自己驗。"""


def admin_tools(shell) -> dict[str, AdminTool]:
    """管理者五個救場工具（設定頁「領地爭奪」那一組與「現在就開一篇天下形勢」）；暫停中照做（paused_ok 預設 True，同原本 ADMIN_ACTIONS 那一條）。"""
    return {
        # 領地爭奪（第 38 項改版第一批）：定一塊歸誰（side 空字串＝放回中立）；第一批沒有攻城戰，地圖只靠這裡與時刻表指定易手
        "conquest_set": AdminTool(_gate, lambda g, b: admin_actions.conquest_set(g, str(b.get("id", "")), str(b.get("side", "")) or None)),
        # 救場（翻地與爭搶，QA 用）：定一條進度（到 100 照推滿易手）、立刻替一邊下戰書（集結馬上開）、取消一場（id 是時程表那一場的 id）
        "conquest_progress": AdminTool(_gate, lambda g, b: admin_actions.conquest_progress(
            g, str(b.get("id", "")), str(b.get("side", "")), shell._float(b.get("value"), 0.0))),
        "admin_conquest_letter": AdminTool(_gate, lambda g, b: admin_actions.conquest_letter(g, str(b.get("id", "")), str(b.get("side", "")))),
        "conquest_cancel": AdminTool(_gate, lambda g, b: admin_actions.conquest_cancel(g, str(b.get("id", "")))),
        "xingshi_now": AdminTool(_gate, lambda g, b: xingshi_actions.admin_now(g)),  # 領地爭奪第三批 A：現在就開一篇〈天下形勢〉
    }


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/api/xingshi")
    def api_xingshi(request: Request):
        """見聞的「形勢」：這一季每天一篇的〈天下形勢〉（領地爭奪第三批 A；只讀，不叫模型——文章在背景寫，write_xingshi）。"""
        game = shell._game(request)
        return shell.look(game, lambda g: xingshi_actions.view(g))

    return r


# ── 鎖外工作（原本寫在 server.py，全部拆包第 69 批）：殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）；模型呼叫絕不進鎖 ──


def outlock(shell) -> Outlock:
    return Outlock(jobs=(
        OutlockJob("xingshi", lambda game: shell._xingshi_waiting(game), lambda game, got: write_xingshi(shell, game)),
    ))


# 〈天下形勢〉（領地爭奪第三批 A；tianxia/xingshi.py）：每天 22:00 換天那一刻開一張單，這裡在背景請模型照事實寫一篇。
# 全服同時只有一條在寫（XINGSHI_RUNNING）；佇列開著時當成假人排在真人後面（名號是 XINGSHI_OWNER，不是任何一個角色）。
XINGSHI_RUNNING: set[str] = set()
XINGSHI_OWNER = "§史官"
XINGSHI_SKIPPED = object()  # 佇列沒讓這一趟跑（假人的名額被佔、排不到）：跟「模型寫不出來」分開——前者單子放回去下一輪再試


def _xingshi_waiting(shell, game) -> bool:
    """有一張〈天下形勢〉的單等著模型寫、模型叫得到、還沒有一條在寫（write_xingshi）。行動鎖內叫。只有 main() 打開 TALE_THREADS 的正式伺服器
    才開背景執行緒（測試直接叫 xingshi_once）；假人程式的 Game 沒有 client，不叫模型。"""
    if not shell.TALE_THREADS or game.client is None or XINGSHI_RUNNING:
        return False
    return game.xingshi_waiting()


def write_xingshi(shell, game) -> bool:
    """開一個背景執行緒寫〈天下形勢〉。A 鎖內拿單子（Game.xingshi_request，記 taken）→ B 鎖外請模型寫（xingshi.write，預算
    Config.xingshi.budget_seconds；排隊時當假人排）→ C 鎖內重驗同一張單才收（Game.settle_xingshi；寫不出來照固定段）。開了回 True。
    呼叫端不能握著行動鎖。"""
    with shell.TALE_LOCK:
        if XINGSHI_RUNNING:
            return False
        XINGSHI_RUNNING.add("xingshi")

    def job() -> None:
        try:
            shell.xingshi_once(game)
        except Exception:  # noqa: BLE001 — 背景執行緒：印出來就好，那一篇過了 grace_seconds 照固定段收
            shell.traceback.print_exc()
        finally:
            with shell.TALE_LOCK:
                XINGSHI_RUNNING.clear()

    shell.threading.Thread(target=job, name="xingshi", daemon=True).start()
    return True


def xingshi_once(shell, game) -> bool:
    """寫一篇（write_xingshi 的那一圈；測試直接叫）：收了回 True。呼叫端不能握著行動鎖。
    佇列沒讓這一趟跑（假人的名額被佔、排不到）：不照固定段收，單子放回去（Game.release_xingshi），隔 retry_seconds 下一輪再試；
    寬限（grace_seconds）到了還沒寫成，由換天（Game._conquest_tick → 地盤包 xingshi_actions.grace）照固定段收（PM，第三批 A 回報之後）。模型叫了卻寫不出來照舊馬上照固定段。"""
    with shell._locked(game):
        request = game.xingshi_request()
    if request is None:
        return False
    budget = game.content.config.xingshi.budget_seconds
    started = shell._monotonic()

    def ask() -> str | None:
        return xingshi.write(shell.within_budget(game.client, budget - (shell._monotonic() - started)), request)

    if shell.QUEUE is None:
        essay = ask()
    else:
        try:  # 排在真人的評分後面（當成假人排）
            essay = shell.QUEUE.run(XINGSHI_OWNER, ask, fallback=XINGSHI_SKIPPED, bot=True, wait=min(budget, 120))
        except (shell.Busy, shell.QueueTimeout):
            essay = XINGSHI_SKIPPED
    with shell._locked(game):  # 收下那一刻寫天下大事：推送的指紋跟著變，開著的分頁會更新
        if essay is XINGSHI_SKIPPED:
            game.release_xingshi(request)
            return False
        return game.settle_xingshi(request, essay)
