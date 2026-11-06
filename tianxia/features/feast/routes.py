"""宴客的鎖外工作（功能包 tianxia/features/feast/；原本寫在 server.py，全部拆包第 69 批）：殼（server 模組，參數 shell）照 FEATURES 接（outlock 掛鉤）；沒有路由（routes 掛鉤照舊回 None）。
這個檔只在殼建鎖外工作時才 import（__init__ 的掛鉤裡面才 from . import routes；殼頂上留一行包裝也 import）；不 import 網頁框架。殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
tests/server/test_server.py 的 _users_in_server 掃這個檔看函式名：裡面寫 shell.model_call，不要先存成別的變數。
same_behavior 的 relay 軌 selftest 改 fallback=feasts.DEFAULT_SCORE 那一句（全檔要剛好一處）：不要拆行或改名。"""
from tianxia.core.features import Outlock

from . import rules as feasts


def outlock(shell) -> Outlock:
    return Outlock(ops={
        "feast_text": lambda g, b: shell.feast_text(g, str(b.get("text", ""))),  # 宴席上自己寫的敬酒詞：分數在行動鎖外評（見 feast_text）
    })


def feast_text(shell, game, text: str) -> list[str]:
    """自己寫的敬酒詞（宴客，大勢人物擴充第三批），三段：A Game.feast_text_request（只讀）→ B 鎖外請模型評一個分數
    （feasts.score，預算 Config.figure_life.feast_score_budget_seconds；評不到照 feasts.DEFAULT_SCORE）→ C Game.feast_toast
    重驗同一場、同一句才記。"""
    started, request = shell._open_request(game, lambda: game.feast_text_request(text))
    if isinstance(request, list):
        return request
    total = game.content.config.figure_life.feast_score_budget_seconds

    def ask() -> int:
        return feasts.score(shell.within_budget(game.client, total - (shell._monotonic() - started)), request)

    rate = shell.model_call(game, ask, fallback=feasts.DEFAULT_SCORE, left=total - (shell._monotonic() - started), busy=shell.BUSY_FREE_TEXT)
    return shell.act(game, lambda g: g.feast_toast(request.text, rate, request))
