"""新手引導包的 API 與動作表（功能包 tianxia/features/guide/）：/api/howto 原本寫在 server.py，全部拆包第 59 批搬進來；動作表原本寫在 server.py 的 MAIN_ACTIONS，全部拆包第 68 批。
殼（server 模組，參數 shell）照 FEATURES 掛路由（server 的 features_core.routers 那一行；路徑沒有帶參數的路由吃得到，先後不影響）、接動作表（main_actions 掛鉤）。
這個檔只在殼掛路由、建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes；引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
/api/prologue 這一批不動。暫停中也照做的那幾個（hints_off、skip_tutorial、view_map、view_orders、guide_ack）名單是殼的 PAUSE_OK_ACTIONS。"""
from fastapi import APIRouter, Request

from . import actions


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/api/howto")
    def api_howto(request: Request):
        """設定抽屜的「玩法說明」（explain-1）：五個行動、體力、情誼、心得、意境、背包各一兩句，數字照設定（Markdown 轉成 HTML）。
        不看個人狀態，網頁同一次載入只問一次。"""
        game = shell._game(request)
        return shell.look(game, lambda g: {"text": shell.md(g.howto_text())})

    return r


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
