"""引導的動作表（功能包 tianxia/features/guide/；原本寫在 server.py 的 MAIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（main_actions 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
暫停中也照做的那幾個（hints_off、skip_tutorial、view_map、view_orders、guide_ack）名單是殼的 PAUSE_OK_ACTIONS。"""
from . import actions


def main_actions(shell) -> dict:
    return {
        "hints_off": lambda g, b: actions.set_hints_off(g, bool(b.get("value"))),  # 設定頁的「不再提示」（碰到才說，新手引導計畫三）
        "skip_tutorial": lambda g, b: actions.skip_tutorial(g),
        "view_map": lambda g, b: actions.view_map(g),
        "view_orders": lambda g, b: actions.view_orders(g),  # 入伍段第一步：軍令卡出現在畫面上（新手引導計畫二）
        "view_tab": lambda g, b: actions.view_tab(g, str(b.get("tab", ""))),  # 序章裡打開修練、煉製頁（新手引導計畫一）
        "guide_ack": lambda g, b: actions.guide_ack(g),  # 對話框的結語按「知道了」
        "newbie_drifter": lambda g, b: actions.newbie_drifter(g),  # 任務卡「新手目標」的「就當散人」（新手引導重做）
    }
