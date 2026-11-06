"""玩家互動的 API（功能包 tianxia/features/peers/；原本寫在 server.py，全部拆包第 37 批照商城、列傳的做法搬進來）：殼（server 模組，參數 shell）
照 FEATURES 掛（server 的 features_core.routers 那一行；四條路徑 /api/peer、/api/peer/act、/api/mingtie、/api/mingtie/{op} 跟別的路由不重疊，先後不影響）。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。

玩家卡按鈕的鎖外三段式（挑釁那一句的審、論武的首創取名：shell.screen_peer、shell.prepare_peer，A 鎖內開單、B 鎖外取名、C 是這裡的 peer_act；A 段 discuss_actions.request、C 段 discuss_actions.discuss 第 38 批搬進包了），照手冊 G10 殼的接線
第 69 批搬進這個檔，路由照舊經 shell. 叫（tests/arts/test_discuss.py 換 server.prepare_peer、server.screen_peer）。名帖定稿那一句的審（shell.screen_text，探索包也用）留在殼。
"""
from fastapi import APIRouter, Body, HTTPException, Request

from tianxia import speech
from tianxia.core import presence
from tianxia.core.features import AdminTool, no_gate

from . import actions, mingtie_actions, social


def admin_tools(shell) -> dict[str, AdminTool]:
    """名帖檢舉（Joy 2026-10-19）：撤下清掉畫與自題，放回是看過沒事。原本寫在 server.py 的 ADMIN_ACTIONS（全部拆包第 68 批）；暫停中照做（paused_ok 預設 True，同原本那一條）。
    mingtie_remove 動到別人的存檔：做完也叫他的分頁刷新，名單是殼的 PLAYER_ADMIN_ACTIONS。"""
    return {
        "mingtie_remove": AdminTool(no_gate, lambda g, b: mingtie_actions.admin_remove(g, str(b.get("name", "")), shell._int(b.get("version"), 0))),
        "mingtie_restore": AdminTool(no_gate, lambda g, b: mingtie_actions.admin_restore(g, str(b.get("name", "")), shell._int(b.get("version"), 0))),
    }


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


# ── 鎖外工作（原本寫在 server.py，全部拆包第 69 批）：殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）；模型呼叫絕不進鎖 ──


def prepare_peer(shell, game, name: str, action: str, params: dict) -> tuple[str | None, str] | None:
    """玩家卡上要先請模型的互動（social.CardAction.request；論武答應時的首創取名）：照開爐的三段式（prepare_forge），
    A 在鎖內問 Game.peer_request、B 在鎖外 naming.generate，回傳（名字, 說明）交給 C（peer_act 的 params["proposed"]）。
    這一種互動不需要模型是 None（不多拿一次鎖）；需要、但這一爐不必取名是 NO_NAME。"""
    handler = social.ACTIONS.get(action)
    if handler is None or handler.request is None:
        return None
    started, request = shell._open_request(game, lambda: game.peer_request(name, action, params))
    if request is None:
        return shell.NO_NAME
    total = game.content.config.naming_budget_seconds

    def name_it():
        budget = max(0.0, total - (shell._monotonic() - started))
        return shell.naming.generate(game.client, game.content, request, budget=budget, person=game.world.is_character_name)

    return shell.model_call(game, name_it, fallback=shell.NO_NAME, left=total - (shell._monotonic() - started), busy=shell.BUSY_FORGE)


def screen_peer(shell, game, name: str, action: str, params: dict) -> str:
    """玩家卡上帶一句話的互動（social.CardAction.screen；挑釁）：要審就審，不要審是空字串。只讀引擎，不拿鎖（那一句只是字）。"""
    handler = social.ACTIONS.get(action)
    if handler is None or handler.screen is None:
        return ""
    got = handler.screen(game, game, params)  # 只看 params（那一句），不讀對方；對方那一份 C 段才拿
    return "" if got is None else shell.screen_text(game, got[0], got[1])
