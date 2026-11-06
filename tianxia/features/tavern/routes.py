"""酒肆的動作表（功能包 tianxia/features/tavern/；原本寫在 server.py 的 MAIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（main_actions 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
問酒家（/api/do/tavern_ask）是鎖外三段式，留在殼。"""
from . import actions


def main_actions(shell) -> dict:
    return {
        # 酒肆那一頁（企劃者 2026-10-18）：op 是 news、seek、ties、material、wall、treat、hide、trace；target 是名號或素材 id、text 是題壁那一句
        "tavern": lambda g, b: actions.tavern_do(g, str(b.get("op", "")), str(b.get("target", ""))[:20], str(b.get("text", ""))[:40]),
    }
