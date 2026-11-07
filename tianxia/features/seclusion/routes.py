"""閉關的動作表（功能包 tianxia/features/seclusion/；原本寫在 server.py 的 MAIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（main_actions 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。"""
from . import actions


def main_actions(shell) -> dict:
    return {
        "seclude": lambda g, b: actions.seclude(g, shell._int(b.get("hours"), 8)),
    }
