"""決戰的管理者工具（功能包 tianxia/features/battle/；原本寫在 server.py 的 ADMIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（admin_tools 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
現實時間由殼給（shell.time，引擎不讀時鐘）。下拉選單（admin_choices、timetable_choices）與 /api/admin 留在殼。
放手一搏（/api/do/battle_text）是鎖外三段式，第 69 批搬進這個檔（outlock 掛鉤；殼留一行包裝）。"""
from tianxia.core.features import AdminTool, Outlock, no_gate

from . import admin, instance as battle_instance


def admin_tools(shell) -> dict[str, AdminTool]:
    """暫停中照做（paused_ok 預設 True，同原本 ADMIN_ACTIONS 那一條）。"""
    return {
        "start_battle": AdminTool(no_gate, lambda g, b: admin.admin_start_battle(g, str(b.get("id", "")), shell.time.time())),
        "cancel_battle": AdminTool(no_gate, lambda g, b: admin.admin_cancel_battle(g)),
        # 三場大戲：照時刻表開（跟「立刻開戰」同一條路），開過就算開過
        "start_showdown": AdminTool(no_gate, lambda g, b: admin.admin_start_showdown(g, str(b.get("id", "")), shell.time.time())),
    }


# ── 鎖外工作（原本寫在 server.py，全部拆包第 69 批）：殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）；模型呼叫絕不進鎖 ──


def outlock(shell) -> Outlock:
    return Outlock(ops={
        "battle_text": lambda g, b: shell.battle_text(g, str(b.get("text", ""))),  # 放手一搏：成功率在行動鎖外評（見 battle_text）
    })


def battle_text(shell, game, text: str) -> list[str]:
    """決戰的放手一搏，跟 answer_event 一樣分三段（試玩回饋 2026-10-08：以前成功率在行動鎖裡評，最多等 in_lock_model_timeout 秒，
    全服所有人的動作都跟著等）：
      A（鎖內、很快）同步時間，問引擎這句話現在送不送得出去（Game.battle_text_request）；不行就回那一句、模型一次都不叫；
      B（鎖外、很慢）請模型評成功率（model_call：佇列開著要排隊），預算是 Config.free_text_budget_seconds 扣掉 A 段與排隊花掉的，
        模型失敗、太慢一律保底值；同一個人上一句還在評、或排太久沒輪到，照隨口應對擋下來、什麼都不送；
      C（鎖內、很快）Game.submit_battle_custom_action 重驗還送得出去，才帶著評好的分送出（可能湊滿這一回合而結算）。"""
    started, request = shell._open_request(game, lambda: game.battle_text_request(text))
    if isinstance(request, list):
        return request
    act_ = shell.CONTENT.battles[request.battle_id].acts[request.act_index]
    total = game.content.config.free_text_budget_seconds

    fallback = battle_instance.DEFAULT_FREE_TEXT_SUCCESS_RATE

    def score():
        client = shell.within_budget(game.client, total - (shell._monotonic() - started))
        if client is None and game.client is not None:
            return fallback  # 等鎖、排隊把整份預算用完了：不叫模型，保底值、固定句
        # 只評成功率（Joy 2026-10-13：二十人同一回合各搏一次也要每一個都評到）；劇情等回合結算後 narrate_battle 一整批寫
        return battle_instance.score_gamble(
            client, act_, request.faction_name, request.text, request.name, target=request.target, sex=request.sex,
        )

    left = total - (shell._monotonic() - started)
    rate = shell.model_call(game, score, fallback=fallback, left=left, busy=shell.BUSY_FREE_TEXT, max_wait=left)
    return shell.act(game, lambda g: g.submit_battle_custom_action(request.text, rate))
