"""決戰的管理者工具（功能包 tianxia/features/battle/；原本寫在 server.py 的 ADMIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（admin_tools 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
現實時間由殼給（shell.time，引擎不讀時鐘）。下拉選單（admin_choices、timetable_choices）與 /api/admin 留在殼。"""
from tianxia.core.features import AdminTool, no_gate

from . import admin


def admin_tools(shell) -> dict[str, AdminTool]:
    """暫停中照做（paused_ok 預設 True，同原本 ADMIN_ACTIONS 那一條）。"""
    return {
        "start_battle": AdminTool(no_gate, lambda g, b: admin.admin_start_battle(g, str(b.get("id", "")), shell.time.time())),
        "cancel_battle": AdminTool(no_gate, lambda g, b: admin.admin_cancel_battle(g)),
        # 三場大戲：照時刻表開（跟「立刻開戰」同一條路），開過就算開過
        "start_showdown": AdminTool(no_gate, lambda g, b: admin.admin_start_showdown(g, str(b.get("id", "")), shell.time.time())),
    }
