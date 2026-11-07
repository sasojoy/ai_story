"""煉製頁的 API（功能包 tianxia/features/craft/；原本寫在 server.py，全部拆包第 44 批照有所感的做法搬進來）：殼（server 模組，參數 shell）
照 FEATURES 掛（server 的 features_core.routers 那一行；前面沒有吃得到 /api/forge_line 的帶參數路由，先後不影響）。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
開爐與立意的鎖外三段式（forge_args、prepare_forge、forge、create_intent、create_reread）第 69 批搬進這個檔（outlock 掛鉤）；殼留一行包裝（api_menxia_do、測試叫），包裡互叫也經 shell.<名字>。
自創的動作表（原本寫在 server.py 的 MENXIA_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（menxia_actions 掛鉤）。"""
from fastapi import APIRouter, Body, Request

from tianxia.core.features import Outlock

from . import actions, create


def menxia_actions(shell) -> dict:
    return {
        # 自創武學（tianxia/create.py）：執器、擺式、回頭、立名、擱下；立意走 /api/do/create_intent（三段式，模型讀這一句意）
        "create_begin": lambda g, b: actions.begin(g, str(b.get("kind") or ""), str(b.get("form") or "")),
        "create_pose": lambda g, b: actions.pose(g, b.get("pose") if isinstance(b.get("pose"), dict) else {}),
        "create_back": lambda g, b: actions.back(g, str(b.get("to") or "")),
        "create_name": lambda g, b: actions.name(g, str(b.get("name") or ""), str(b.get("move") or "")[:create.MOVE_MAX * 2]),
        "create_cancel": lambda g, b: actions.cancel(g),
        "create_reroll": lambda g, b: actions.reroll(g),  # 重悟帖：成了形直接重骰（萬寶閣，Joy 2026-10-21）
        # 一武學＋一意境、兩武學＝合成，兩意境＝合併。端點走 forge()（A 鎖內備料 → B 鎖外取名或挑 → C 鎖內登記），不走這一條；
        # 這裡也帶 NO_NAME，就算有人直接拿它在鎖裡呼叫，也不會叫模型
        "forge": lambda g, b: _forge_without_naming(shell, g, *shell.forge_args(b)),
    }


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.post("/api/forge_line")
    def api_forge_line(request: Request, body: dict = Body(default={})):
        """煉製頁選了東西就更新說明（不算行動、不存檔）。爐裡只放了一樣時多給 picks：另一格放得進來的每一樣合不合得了，
        判斷是開爐時那一套（forge_view.forge_picks）；其他時候是 None。"""
        game = shell._game(request)
        _art, picked = shell.forge_args(body)
        return shell.look(game, lambda g: {
            "line": shell.md(g.forge_line(picked)), "picks": g.forge_picks(picked),
            "preview": g.forge_preview(picked),  # 兩格都放好：預覽卡，其餘 None、網頁畫 line
        })

    return r


# ── 鎖外工作（原本寫在 server.py，全部拆包第 69 批）：殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）；模型呼叫絕不進鎖 ──


def outlock(shell) -> Outlock:
    return Outlock(ops={
        "create_intent": lambda g, b: create_intent(shell, g, b),  # 自創武學的形意：意分在行動鎖外評（見 create_intent）
        "create_reread": lambda g, b: shell.create_reread(g, b),  # 重悟帖：重讀這句意，意分在行動鎖外評（見 create_reread）
    })


def create_intent(shell, game, body: dict) -> list[str]:
    """自創武學的立意（tianxia/create.py），三段同 duel_text：A Game.create_request（只讀）→ B 鎖外 create.read 讀這一句意
    （分數、最多兩路屬性、正邪；預算同隨口應對）→ C Game.create_intent(reading=) 整個重驗再成形。叫不動照關鍵字表讀。"""
    text = str(body.get("text") or "")[:create.INTENT_MAX * 2]
    started, request = shell._open_request(game, lambda: game.create_request(text))
    if isinstance(request, list):
        return request
    total = game.content.config.free_text_budget_seconds

    def reading():
        return create.read(shell.within_budget(game.client, total - (shell._monotonic() - started)), request, game.content)

    value = shell.model_call(
        game, reading, fallback=create.fallback_read(game.content, request.text),
        left=total - (shell._monotonic() - started), busy=shell.BUSY_FREE_TEXT,
    )
    return shell.act(game, lambda g: g.create_intent(request.text, reading=value))


def create_reread(shell, game, body: dict) -> list[str]:
    """重悟帖的第二個用法：重讀這句意（可以改寫），三段同 create_intent：A Game.create_reread_request → B 鎖外 create.read_or_none
    → C Game.create_reread(reading=)。叫不動（None）就什麼都不改、不扣帖（不照關鍵字表讀）。"""
    text = str(body.get("text") or "")[:create.INTENT_MAX * 2]
    started, request = shell._open_request(game, lambda: game.create_reread_request(text))
    if isinstance(request, list):
        return request
    total = game.content.config.free_text_budget_seconds

    def reading():
        return create.read_or_none(shell.within_budget(game.client, total - (shell._monotonic() - started)), request)

    value = shell.model_call(game, reading, fallback=None, left=total - (shell._monotonic() - started), busy=shell.BUSY_FREE_TEXT)
    return shell.act(game, lambda g: g.create_reread(request.text, value))


def prepare_forge(shell, game, art_id: str | None, insight_ids: list[str]) -> tuple[str | None, str]:
    """開爐的首次取名或挑選在行動鎖外（最終審查 Critical 1）。首次合出來的配方要等模型取名（合到舊的、候選兩個以上時是
    請模型從候選挑一個名字），以前整段包在行動鎖裡：
    一次最多叫三次、每次最多等 OllamaClient.timeout（120 秒），全服玩家與假人程式都得跟著等，試玩走的 trycloudflare
    也會在約 100 秒切斷請求。跟 prepare_dialogue 一樣分三段：
      A（鎖內、很快）同步時間，問引擎這一爐要不要模型取名或挑（Game.forge_request），要就拿到單子；同步的結果要存起來，
        不然 C 段進鎖重讀就把它丟了；
      B（鎖外、很慢）naming.generate（model_call：佇列開著要排隊）：預算是 Config.naming_budget_seconds 扣掉 A 段（含等鎖）
        與排隊花掉的時間，引擎不讀時鐘，所以時間在這裡量，輪到了才算；用完（輪到了、預算已經沒了）就回 (None, "")，C 段走退路字表（挑的話改由規則挑）；
        排太久沒輪到被擋下來（BUSY_QUEUE_TIMEOUT，PM 2026-10-06），跟同一個人的第二件一樣丟 GameError、不走 C 段；
      C（鎖內、很快）由呼叫端把結果交給 Game.forge(..., proposed=...)，引擎整個重驗再登記、收費。
    這裡做 A 與 B，回傳 B 的結果（名字, 說明）；不必叫模型時是 NO_NAME。假人程式（bot_runner._name_and_apply）不經過 HTTP，
    照樣走這三段：A 是 Game.forge_request(named_outside=True) 在 action_lock 裡，B 是它自己的 client 在鎖外叫 naming.generate
    （預算 Config.bot_naming_budget_seconds，一次一件、至少隔 bot_naming_gap_seconds），C 是 bot_policy.apply_job 再進鎖交給
    Game.forge(proposed=...)；絕學定名也是同一條路（Game.mastery_request、Game.name_mastered）。煉製只剩意境＋意境。"""
    started, request = shell._open_request(game, lambda: game.forge_request(art_id, insight_ids))
    if request is None:
        return shell.NO_NAME
    total = game.content.config.naming_budget_seconds

    def name_it():
        budget = max(0.0, total - (shell._monotonic() - started))
        # 角色名號的查詢是唯讀的快照、不拿行動鎖（FB-069：模型取到角色的名號就再取一次；C 段進鎖還會再擋一次）
        return shell.naming.generate(game.client, game.content, request, budget=budget, person=game.world.is_character_name)

    return shell.model_call(game, name_it, fallback=shell.NO_NAME, left=total - (shell._monotonic() - started), busy=shell.BUSY_FORGE)


def forge(shell, game, art_id: str | None, insight_ids: list[str]) -> list[str] | None:
    """開爐：A、B 在 prepare_forge，C 進鎖交給 Game.forge。proposed 一定給（不必叫模型時是 NO_NAME），
    所以伺服器上的開爐永遠不會在鎖裡叫模型。同一爐連按兩下、重新整理再按、開兩個分頁：兩個請求可能都走完 A、B，
    C 段重驗時第二個會看見配方有了、東西已經在你身上，什麼都不收（企劃者 2026-10-05：不能重複扣）。
    模型佇列開著時，同一個人已經有一件在等模型（另一個分頁、另一台裝置），第二件在 B 段被擋下來：丟 GameError「上一爐還沒出爐。」
    （BUSY_FORGE），不走 C 段、什麼都不登記、什麼都不收（審查 M2、控制者裁示；以前它拿 NO_NAME 先進鎖，這個配方這一季就用退路
    字表的名字登記，第一件模型取的名字被丟掉）。不必叫模型的爐（配方已經有人合過）不經過佇列，兩個分頁照常都走得完。"""
    proposed = shell.prepare_forge(game, art_id, insight_ids)
    return shell.act(game, lambda g: g.forge(art_id, insight_ids, proposed=proposed))


def forge_args(shell, body: dict) -> tuple[str | None, list[str]]:
    """煉製頁送來的東西：意境 id 們（爐裡只合意境）；舊網頁送來的武學 id 照傳，引擎回「爐裡只合意境」那一句。body 是客戶端寫的：
    意境不是清單就當作沒放，形狀不對只會得到一句話，不會打出 500。"""
    art, picked = body.get("art"), body.get("insights")
    return str(art) if art else None, [str(i) for i in picked] if isinstance(picked, list) else []


def _forge_without_naming(shell, game, art_id: str | None, insight_ids: list[str]) -> list[str]:
    return game.forge(art_id, insight_ids, proposed=shell.NO_NAME)
