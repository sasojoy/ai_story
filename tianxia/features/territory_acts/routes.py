"""地盤的 API（功能包 tianxia/features/territory_acts/；原本寫在 server.py，開發規範手冊 3.2）：殼（server 模組，參數 shell）照 FEATURES 掛，
/api/do/{op} 的管理者工具也照清單接（admin_tools）。

- GET /api/xingshi：見聞的「形勢」（這一季每天一篇的〈天下形勢〉；只讀，不叫模型——文章在背景寫，server.write_xingshi 留在殼）
- 管理者五個救場工具：op 名字照舊。立刻下戰書叫 admin_conquest_letter、不叫 conquest_letter：api_do 先查功能包的管理者工具，同名會把玩家的下戰書
  （MAIN_ACTIONS["conquest_letter"]，全部拆包第 68 批搬進這個檔的 main_actions）整個蓋掉（FB-609）。領地爭奪、〈天下形勢〉關著時各動作自己回一句（跟原本一樣，沒有 404）。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
"""
from fastapi import APIRouter, Request

from tianxia.core.features import AdminTool

from . import admin_actions, letter_actions, xingshi_actions


def main_actions(shell) -> dict:
    return {
        # 領地爭奪：下戰書（翻地與爭搶，輿圖簡化設計 4.4；這一週在任的第 4 階、自己那一邊在這一塊的進度到門檻）。每天投票拿掉了（PM 2026-10-20）
        "conquest_letter": lambda g, b: letter_actions.conquest_letter(g, str(b.get("loc", ""))),
    }


def _gate() -> None:
    """這一包沒有總開關（原本 ADMIN_ACTIONS 那五個也沒有 404）：什麼都不擋，各動作自己驗。"""


def admin_tools(shell) -> dict[str, AdminTool]:
    """管理者五個救場工具（設定頁「領地爭奪」那一組與「現在就開一篇天下形勢」）；暫停中照做（paused_ok 預設 True，同原本 ADMIN_ACTIONS 那一條）。"""
    return {
        # 領地爭奪（第 38 項改版第一批）：定一塊歸誰（side 空字串＝放回中立）；第一批沒有攻城戰，地圖只靠這裡與時刻表指定易手
        "conquest_set": AdminTool(_gate, lambda g, b: admin_actions.conquest_set(g, str(b.get("id", "")), str(b.get("side", "")) or None)),
        # 救場（翻地與爭搶，QA 用）：定一條進度（到 100 照推滿易手）、立刻替一邊下戰書（集結馬上開）、取消一場（id 是時程表那一場的 id）
        "conquest_progress": AdminTool(_gate, lambda g, b: admin_actions.conquest_progress(
            g, str(b.get("id", "")), str(b.get("side", "")), shell._float(b.get("value"), 0.0))),
        "admin_conquest_letter": AdminTool(_gate, lambda g, b: admin_actions.conquest_letter(g, str(b.get("id", "")), str(b.get("side", "")))),
        "conquest_cancel": AdminTool(_gate, lambda g, b: admin_actions.conquest_cancel(g, str(b.get("id", "")))),
        "xingshi_now": AdminTool(_gate, lambda g, b: xingshi_actions.admin_now(g)),  # 領地爭奪第三批 A：現在就開一篇〈天下形勢〉
    }


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/api/xingshi")
    def api_xingshi(request: Request):
        """見聞的「形勢」：這一季每天一篇的〈天下形勢〉（領地爭奪第三批 A；只讀，不叫模型——文章在背景寫，write_xingshi）。"""
        game = shell._game(request)
        return shell.look(game, lambda g: xingshi_actions.view(g))

    return r
