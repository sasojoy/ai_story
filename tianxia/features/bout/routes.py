"""單挑的鎖外工作（功能包 tianxia/features/bout/；原本寫在 server.py，全部拆包第 69 批）：殼（server 模組，參數 shell）照 FEATURES 接（outlock 掛鉤）；沒有路由（routes 掛鉤照舊回 None）。
這個檔只在殼建鎖外工作時才 import（__init__ 的掛鉤裡面才 from . import routes；殼頂上留一行包裝也 import）；不 import 網頁框架。殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
tests/server/test_server.py 的 _users_in_server 掃這個檔看函式名：裡面寫 shell.model_call、shell.QUEUE，不要先存成別的變數。
- 擂台場邊那一句：_crowd_waiting、write_crowd、crowd_once（背景寫字，放鎖之後才開）
- 頭目戰與擂台的放手一搏：duel_text（/api/do/duel_text，鎖外三段式）。評分讀核心 core/battle_base，不經殼碰決戰包（第二輪第 102 批）"""
from tianxia.core import battle_base
from tianxia.core.features import Outlock, OutlockJob

from . import arena_crowd, duel_rules as duel


def outlock(shell) -> Outlock:
    return Outlock(
        ops={
            "duel_text": lambda g, b: shell.duel_text(g, str(b.get("text", ""))),  # 頭目戰的放手一搏：成功率在行動鎖外評（見 duel_text）
        },
        jobs=(
            OutlockJob("crowd", lambda game: _crowd_waiting(shell, game), lambda game, got: write_crowd(shell, game)),
        ),
    )


CROWD_RUNNING: set[str] = set()  # 正在背景重寫場邊那一句的角色（一人一條；名號鍵）


def _crowd_waiting(shell, game) -> bool:
    """擂台有一句場邊事件等著模型重寫、模型叫得到、這個人還沒有一條在寫（write_crowd）。行動鎖內叫。"""
    if not shell.TALE_THREADS or game.client is None or game.state.player.arena_crowd_note is None:
        return False
    return game.state.player.name not in CROWD_RUNNING


def write_crowd(shell, game) -> bool:
    """擂台場邊那一句（arena_crowd）：開一個背景執行緒重寫。A 鎖內拿單子（Game.arena_crowd_request）→ B 鎖外請模型寫
    （arena_crowd.write_line，預算 Config.arena.crowd.write_budget_seconds；排隊時當假人排）→ C 鎖內重驗同一張單子才換
    （Game.apply_arena_crowd；寫不出來照固定句）。開了回 True。呼叫端不能握著行動鎖。"""
    name = game.state.player.name
    with shell.TALE_LOCK:
        if name in CROWD_RUNNING:
            return False
        CROWD_RUNNING.add(name)

    def job() -> None:
        try:
            shell.crowd_once(game)
        except Exception:  # noqa: BLE001 — 背景執行緒：印出來就好，那一句照固定句
            shell.traceback.print_exc()
        finally:
            with shell.TALE_LOCK:
                CROWD_RUNNING.discard(name)

    shell.threading.Thread(target=job, name="arena-crowd", daemon=True).start()
    return True


def crowd_once(shell, game) -> bool:
    """重寫一句（write_crowd 的那一圈；測試直接叫）：換了回 True。呼叫端不能握著行動鎖。"""
    with shell._locked(game):
        note = game.arena_crowd_request()
    if note is None:
        return False
    budget = game.content.config.arena.crowd.write_budget_seconds
    started = shell._monotonic()

    def ask() -> str:
        return arena_crowd.write_line(shell.within_budget(game.client, budget - (shell._monotonic() - started)), note)

    if shell.QUEUE is None:
        text = ask()
    else:
        try:
            text = shell.QUEUE.run(game.state.player.name, ask, fallback="", bot=True, wait=budget)
        except (shell.Busy, shell.QueueTimeout):
            text = ""
    with shell._locked(game):
        done = game.apply_arena_crowd(note, text)
        shell.open_characters().save(game.state)
    return done


def duel_text(shell, game, text: str) -> list[str]:
    """單人頭目戰的放手一搏，三段同 battle_text：A Game.duel_text_request（只讀）→ B 鎖外請模型評成功率、寫成敗兩版劇情
    （預算同隨口應對）→ C Game.duel_gamble 重驗同一隻、同一回合、同一句才用評好的分，對不上回「這一回合已經結算」、不重評。"""
    started, request = shell._open_request(game, lambda: game.duel_text_request(text))
    if isinstance(request, list):
        return request
    total = game.content.config.free_text_budget_seconds
    fallback = battle_base.GambleVerdict(battle_base.DEFAULT_FREE_TEXT_SUCCESS_RATE)
    scene = duel.Scene(request.title, request.scene)

    def score():
        client = shell.within_budget(game.client, total - (shell._monotonic() - started))
        if client is None and game.client is not None:
            return fallback, ""
        verdict = battle_base.assess_gamble(
            client, scene, request.faction_name, request.text, request.name, setting=request.setting or duel.SETTING,
            place=request.place or duel.PLACE, target=request.target, sex=request.sex,  # 擂台帶對手那一行與擂台的場合（Game.duel_text_request）
        )
        crowd = ""
        if request.boss.startswith("arena:") and arena_crowd.on(game.content):  # 擂台：另問一次台下觀眾的反應（評分那一次的提示不動）
            crowd = arena_crowd.judge_gamble(shell.within_budget(game.client, total - (shell._monotonic() - started)), request.text,
                                             request.title, request.name)
        return verdict, crowd

    verdict, crowd = shell.model_call(game, score, fallback=(fallback, ""), left=total - (shell._monotonic() - started), busy=shell.BUSY_FREE_TEXT)
    return shell.act(game, lambda g: g.duel_gamble(request.text, verdict.rate, (verdict.win, verdict.lose), request=request, crowd=crowd))
