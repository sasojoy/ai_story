"""走一趟的動作表（功能包 tianxia/features/explore/；原本寫在 server.py 的 MAIN_ACTIONS、ADMIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（main_actions、admin_tools 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
走一趟的留言（/api/do/outing_say，自己寫的那一句先在鎖外審）與遊記（/api/do/outing_tale）是鎖外三段式，留在殼。"""
from tianxia.core.features import AdminTool, no_gate

from . import outing_actions


def main_actions(shell) -> dict:
    return {
        # 走一趟（tianxia/outing.py）：n 是段數（1／3／5）就出發；0 或沒帶是停在要選的事上、選完接著走。沿路的事在 main.outing.trip
        "outing": lambda g, b: outing_actions.outing_go(g, shell._int(b.get("n"), 0)),
    }


def admin_tools(shell) -> dict[str, AdminTool]:
    """暫停中照做（paused_ok 預設 True，同原本 ADMIN_ACTIONS 那一條）。"""
    return {
        "outing_erase": AdminTool(no_gate, lambda g, b: outing_actions.admin_erase_inscription(g, shell._int(b.get("id"), 0))),  # 走一趟的留言：管理者抹掉一則
    }
