"""人物情誼的 API（功能包 tianxia/features/companions/；原本寫在 server.py，開發規範手冊 3.2）：殼（server 模組，參數 shell）照 FEATURES 掛。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
名冊、書信小卡、勸降的動作照舊走 server 的 /api/menxia/{op}、/api/do/{op}（動作表總表第 68 批才照包分），這裡只有這一包整條自己的路由（第 3 階之前先做的那一件）。"""
from fastapi import APIRouter, Request

from . import actions, talk_log


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/api/figure")
    def api_figure(request: Request, id: str = ""):
        """人物頁（減法季批 6，主機側計畫 1.3 的 figure.stances、figure.errands）：這位人物（對話人物 id）的心意條、你今天記的那一筆、
        他託你的事（actions.figure_view）。關著、他什麼都沒有是 None。只讀。"""
        game = shell._game(request)
        return {"figure": shell.look(game, lambda g: actions.figure_view(g, str(id)[:40]))}

    @r.get("/api/talk_log")
    def api_talk_log(request: Request, id: str = "", season: str = "now", before: int = 0):
        """往來紀錄（介面重整 2026-11-05）：你跟這位人物這一季（season=now）或上一季（prev）說過的話，新的在前、一次 talk_log.PAGE 句；
        before 是上一頁最舊那一句的 id。情誼的增減照同一位人物前一句記下的情誼算。只讀，不拿行動鎖（讀的是旁邊的小檔與角色的名號）。"""
        game = shell._game(request)
        cid = str(id)[:40]
        ch = game.content.characters.get(cid)
        if ch is None:
            return {"lines": [], "more": False}
        p = game.state.player
        number = p.season_number - (1 if season == "prev" else 0)
        store = shell.talk_store()
        rows, more = store.page(shell.name_key(p.name), cid, number, before or None, talk_log.PAGE + 1)
        lines = []
        for i, row in enumerate(rows[:talk_log.PAGE]):
            said = rows[i + 1] if i + 1 < len(rows) and rows[i + 1]["role"] == "user" else None  # 同一輪玩家那一句記的是動作前的情誼
            gain = row["affinity"] - said["affinity"] if said is not None and row["role"] == "assistant" else 0
            lines.append({"id": row["id"], "stamp": row["stamp"], "place": row["place"], "role": row["role"], "text": row["text"], "gain": gain})
        return {"id": cid, "name": ch.name, "face": shell.figure_face(cid), "affinity": p.affinities.get(cid, 0),
                "meets": store.meets(shell.name_key(p.name), cid), "lines": lines, "more": more or len(rows) > talk_log.PAGE}

    return r
