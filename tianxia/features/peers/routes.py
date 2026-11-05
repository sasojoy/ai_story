"""玩家互動的 API（功能包 tianxia/features/peers/；原本寫在 server.py，全部拆包第 37 批照商城、列傳的做法搬進來）：殼（server 模組，參數 shell）
照 FEATURES 掛（server 的 features_core.routers 那一行；四條路徑 /api/peer、/api/peer/act、/api/mingtie、/api/mingtie/{op} 跟別的路由不重疊，先後不影響）。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。

玩家卡按鈕的鎖外三段式（挑釁那一句的審、論武的首創取名：shell.screen_peer、shell.prepare_peer，A 鎖內開單、B 鎖外取名、C 是這裡的 peer_act；A 段 discuss_actions.request、C 段 discuss_actions.discuss 第 38 批搬進包了），照手冊 G10 殼的接線
留在 server.py，這裡經 shell. 叫。名帖定稿那一句的審（shell.screen_text）也在殼。
"""
from fastapi import APIRouter, Body, HTTPException, Request

from tianxia import speech
from tianxia.core import presence

from . import actions, mingtie_actions, social


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/api/peer")
    def api_peer(request: Request, name: str = ""):
        """玩家卡（social.card）：他不在這裡了 card 是 None，網頁照 gone 那一句說。只讀。"""
        game = shell._game(request)
        return {"card": shell.look(game, lambda g: actions.peer_card(g, name)), "gone": presence.GONE}

    @r.post("/api/peer/act")
    def api_peer_act(request: Request, body: dict = Body(default={})):
        """按了玩家卡上的一顆鈕（actions.peer_act）：回傳 {card, main, message}。參數都是客戶端寫的，一律轉成字串或整數再交給引擎驗。"""
        game = shell._game(request)
        name, action = str(body.get("name", "")), str(body.get("action", ""))
        params = {"arg": str(body.get("arg", "")), "choice": str(body.get("choice", ""))}
        try:
            params["amount"] = int(body.get("amount", 0))
        except (TypeError, ValueError):
            params["amount"] = 0
        params["text"] = str(body.get("text", ""))[:200]  # 挑釁附的一句話（CardButton.text）：C 段照字數與字表再驗
        verdict = shell.screen_peer(game, name, action, params)  # 那一句先在鎖外請模型審（speech.judge），結果交給 C 段
        if verdict:
            params["verdict"] = verdict
        proposed = shell.prepare_peer(game, name, action, params)  # 論武的首創取名：A 鎖內開單、B 鎖外取名，C 是下面的 peer_act
        if proposed is not None:
            params["proposed"] = proposed
        msgs = shell.act(game, lambda g: actions.peer_act(g, name, action, params))
        shell._tell_tabs(game)
        return {
            "card": shell.look(game, lambda g: actions.peer_card(g, name)),
            "gone": presence.GONE,
            "main": shell.look(game, shell.main_view),
            "message": shell.joined(msgs),
            # 卡已經關了或換了人時，網頁的提示泡泡只講這一句（FB-242）：論武合成了是「論武有結果了：合出…」，其餘是回話的第一句
            "brief": game.peer_brief or social.brief(msgs),
        }

    @r.get("/api/mingtie")
    def api_mingtie(request: Request):
        """見聞的「名帖匣」（mingtie_actions.view）：頭銜的榜單名次照快取的整張榜（boards_now，不拿行動鎖）。"""
        game = shell._game(request)
        board = shell.boards_now(game)
        return shell.look(game, lambda g: mingtie_actions.view(g, board))

    @r.post("/api/mingtie/{op}")
    def api_mingtie_do(op: str, request: Request, body: dict = Body(default={})):
        """名帖的動作：save（定稿：筆劃、頭銜、自題一句；那一句先在鎖外審過）、report（檢舉某人的第幾版）。回傳 {mingtie, message}。"""
        game = shell._game(request)
        if op == "save":
            board = shell.boards_now(game)
            motto = speech.clean(str(body.get("motto", ""))[:200])
            verdict = shell.screen_text(game, motto, speech.MOTTO) if shell.look(game, lambda g: mingtie_actions.screen(g, motto)) else ""
            titles = body.get("titles")
            titles = [str(t) for t in titles] if isinstance(titles, list) else []
            msgs = shell.act(game, lambda g: mingtie_actions.make(g, body.get("strokes"), titles, motto, verdict, board))
        elif op == "report":
            msgs = shell.act(game, lambda g: mingtie_actions.report(g, str(body.get("name", "")), shell._int(body.get("version"), 0)))
            board = shell.boards_now(game)
        else:
            raise HTTPException(404)
        shell._tell_tabs(game)
        return {"mingtie": shell.look(game, lambda g: mingtie_actions.view(g, board)), "message": shell.joined(msgs)}

    return r
