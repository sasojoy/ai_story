"""簽到的動作表（功能包 tianxia/features/checkin/；原本寫在 server.py 的 MAIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（main_actions 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
not_while_preparing 原本掛在 Game.check_in 那一行委派上、包裡的函式沒有：表不再經過委派，所以擋法掛在表上這一條（同一支裝飾器，包裡的函式不動）。"""
from tianxia.core.services import not_while_preparing

from . import actions


def main_actions(shell) -> dict:
    return {
        # 江湖頁「簽到」小標攤開的領取鈕（21 天季，正式季整合 6.2）：四階的日子帶 attribute（剛柔快慢）
        "checkin": not_while_preparing(lambda g, b: actions.check_in(g, str(b.get("attribute", ""))[:2])),
    }
