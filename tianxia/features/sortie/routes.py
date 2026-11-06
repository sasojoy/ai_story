"""出陣的動作表（功能包 tianxia/features/sortie/；原本寫在 server.py 的 MAIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（main_actions 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。"""
from . import duel_actions


def main_actions(shell) -> dict:
    return {
        # 出陣約戰（減法季批 3b；main.sortie_card、main.sorties）：moves 是三招（清單，或「強攻,固守,奇襲」），id 是約戰卡上的 id。
        # 引擎在 world.mutate 裡重驗（兩個人同時應戰，先到的那一位是守方）；關著的季回「此刻無法這麼做」
        "sortie_go": lambda g, b: duel_actions.sortie_go(g, shell._moves(b.get("moves"))),
        "sortie_answer": lambda g, b: duel_actions.sortie_answer(g, str(b.get("id", ""))[:80], shell._moves(b.get("moves"))),
        "sortie_join": lambda g, b: duel_actions.sortie_join(g, str(b.get("id", ""))[:80]),
    }
