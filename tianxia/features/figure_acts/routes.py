"""大勢人物行動的管理者工具（功能包 tianxia/features/figure_acts/；原本寫在 server.py 的 ADMIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（admin_tools 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。"""
from tianxia.core.features import AdminTool, no_gate

from . import admin_actions


def admin_tools(shell) -> dict[str, AdminTool]:
    """暫停中照做（paused_ok 預設 True，同原本 ADMIN_ACTIONS 那一條）。"""
    return {
        "revive_figure": AdminTool(no_gate, lambda g, b: admin_actions.revive_figure(g, str(b.get("id", "")))),
    }
