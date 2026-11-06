"""玉璽碎片的動作表（功能包 tianxia/features/seal/；原本寫在 server.py 的 MAIN_ACTIONS、ADMIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（main_actions、admin_tools 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
奪璽單挑的放手一搏（/api/do/seal_text）是鎖外三段式，留在殼。現實時間由殼給（shell.time，引擎不讀時鐘）。"""
from tianxia.core.features import AdminTool, no_gate

from . import admin, card


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
