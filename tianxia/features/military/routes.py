"""軍情的管理者工具（功能包 tianxia/features/military/；原本寫在 server.py 的 ADMIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（admin_tools 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
summon、give_opportunity、give_fragment 動到別人的存檔：做完也叫他的分頁刷新，名單是殼的 PLAYER_ADMIN_ACTIONS。"""
from tianxia.core.features import AdminTool, no_gate

from . import admin_actions, fs_actions, opp_actions


def admin_tools(shell) -> dict[str, AdminTool]:
    """暫停中照做（paused_ok 預設 True，同原本 ADMIN_ACTIONS 那一條）。"""
    return {
        # 管理者觸發鈕（企劃者 2026-10-07）：每週的事照週一的做法立刻再做一次
        "issue_orders": AdminTool(no_gate, lambda g, b: admin_actions.issue_orders(g)),
        "rotate_seats": AdminTool(no_gate, lambda g, b: admin_actions.rotate_seats(g)),
        # 玩家個人劇情：name 是那個玩家的名號，在這一把行動鎖裡讀他的存檔、補算、做完存回去（見 Game._admin_target）
        "summon": AdminTool(no_gate, lambda g, b: admin_actions.summon(g, str(b.get("name", "")))),
        "give_opportunity": AdminTool(no_gate, lambda g, b: opp_actions.give_opportunity(g, str(b.get("name", "")), str(b.get("id", "")))),
        "give_fragment": AdminTool(no_gate, lambda g, b: fs_actions.give_fragment(g, str(b.get("name", "")), str(b.get("id", "")))),
    }
