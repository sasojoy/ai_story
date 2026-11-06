"""玉璽碎片的動作表（功能包 tianxia/features/seal/；原本寫在 server.py 的 MAIN_ACTIONS、ADMIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（main_actions、admin_tools 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
奪璽單挑的放手一搏（/api/do/seal_text）是鎖外三段式，留在殼。現實時間由殼給（shell.time，引擎不讀時鐘）。"""
from tianxia.core.duel_base import Scene
from tianxia.core.features import AdminTool, Outlock, no_gate

from . import admin, card, duel_rules as seal_duel


def main_actions(shell) -> dict:
    return {
        # 玉璽碎片改版第 2 批：起用懷中那一片的獨門行動。target 是指定的目標（大勢人物、戰線、人物 id），side 是散人傳檄挑的那一軍；
        # 玩家的叫 seal_use，跟管理者那一組 seal_* 不同名（FB-609）
        "seal_use": lambda g, b: card.use(g, str(b.get("target", ""))[:40], str(b.get("side", ""))[:20]),
    }


def admin_tools(shell) -> dict[str, AdminTool]:
    """玉璽碎片（玉璽碎片設計第十二節）：效果跟自然發生一樣，公告不寫管理者。暫停中照做（paused_ok 預設 True，同原本 ADMIN_ACTIONS 那一條）。"""
    return {
        "seal_emerge": AdminTool(no_gate, lambda g, b: admin.emerge(g, str(b.get("id", "")))),
        "seal_stir": AdminTool(no_gate, lambda g, b: admin.stir(g, str(b.get("id", "")))),
        "seal_assign": AdminTool(no_gate, lambda g, b: admin.assign(g, str(b.get("id", "")), str(b.get("name", "")), str(b.get("state", "held")))),
        "seal_duel": AdminTool(no_gate, lambda g, b: admin.duel(g, str(b.get("id", "")), str(b.get("name", "")), shell._float(b.get("factor"), 1.0), shell.time.time())),
        "seal_fix": AdminTool(no_gate, lambda g, b: admin.fix(g, b.get("take") is True)),
        "seal_cancel": AdminTool(no_gate, lambda g, b: admin.cancel(g)),
        "seal_sink_check": AdminTool(no_gate, lambda g, b: admin.sink_check(g, shell.time.time())),
        "seal_mandate": AdminTool(no_gate, lambda g, b: admin.mandate(g, str(b.get("when", "")))),
    }


# ── 鎖外工作（原本寫在 server.py，全部拆包第 69 批）：殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）；模型呼叫絕不進鎖 ──


def outlock(shell) -> Outlock:
    return Outlock(ops={
        "seal_text": lambda g, b: seal_text(shell, g, str(b.get("text", ""))),  # 奪璽單挑的放手一搏：成功率在行動鎖外評（見 seal_text）
    })


def seal_text(shell, game, text: str) -> list[str]:
    """奪璽單挑的放手一搏（玉璽碎片設計 5.7），三段同 duel_text：A Game.seal_text_request（只讀；判成不在場的回合不開單）→
    B 鎖外請模型評成功率、寫成敗兩版劇情（預算同隨口應對，評不到 40）→ C Game.seal_gamble 重驗同一場、同一回合、同一邊、同一句才用，
    回合對不上直接回「這一回合已經結算」，不在鎖內重評。"""
    started, request = shell._open_request(game, lambda: game.seal_text_request(text))
    if isinstance(request, list):
        return request
    total = game.content.config.free_text_budget_seconds
    fallback = shell.battle_instance.GambleVerdict(shell.battle_instance.DEFAULT_FREE_TEXT_SUCCESS_RATE)
    scene = Scene(request.title, request.scene)

    def score():
        client = shell.within_budget(game.client, total - (shell._monotonic() - started))
        if client is None and game.client is not None:
            return fallback
        return shell.battle_instance.assess_gamble(
            client, scene, request.faction_name, request.text, request.name,
            setting=seal_duel.SETTING, place=seal_duel.PLACE, target=request.target, sex=request.sex,
        )

    verdict = shell.model_call(game, score, fallback=fallback, left=total - (shell._monotonic() - started), busy=shell.BUSY_FREE_TEXT)
    return shell.act(game, lambda g: g.seal_gamble(request.text, verdict.rate, (verdict.win, verdict.lose), request=request))
