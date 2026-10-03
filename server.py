"""《天下大勢》的網頁伺服器：FastAPI 給資料，`web/` 裡的單頁網頁負責畫面。

取代原本的 Gradio 介面（`app.py`）。遊戲規則全部在 tianxia/，這個檔案只做三件事：
登入與角色、把每個動作包進跨程式的行動鎖（同步時間 → 動作 → 存檔）、把畫面需要的東西整理成 JSON。

- 數字、清單、選項用 JSON；引擎寫的大段文字（場景、事件、角色卡、戰報）是 Markdown，
  在這裡轉成 HTML 再送出（`md()`，原始 HTML 一律跳脫，名號裡的 `<` 不會變成標籤）。
  江湖紀錄、地圖沿用引擎產生的 HTML／SVG（線上架構設計第七節的混合做法）。
- 登入狀態放在 cookie（`tx_session`），伺服器記憶體裡對應到帳號；重開伺服器要重新登入。
- 同一個角色只有一份 `Game`（`GAMES`）：同一個帳號開兩個分頁、換手機再登入，看到的都是同一份，
  不再有「兩個分頁各一份、最後存的蓋掉前面」。
- 人物對話照舊在行動鎖外生成（`prepare_dialogue`），模型的 9~10 秒不會卡住全服。

執行：`.venv/Scripts/python.exe server.py`（http://127.0.0.1:7861）。要讓外面的手機連進來，
加 `--share`：會用 cloudflared 開一個臨時的公開網址（要先裝 cloudflared，見 CLAUDE.md）。
"""
from __future__ import annotations

import argparse
import secrets
import shutil
import subprocess
import threading
import time
import unicodedata
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt

from tianxia import companion_agent, materials
from tianxia.accounts import NAME_TAKEN, PASSWORDS_DIFFER, AccountError, AccountStore, normalize
from tianxia.content import load_content
from tianxia.craft import MATERIALS_PER_CRAFT
from tianxia.engine import Game
from tianxia.journal import CSS as JOURNAL_CSS
from tianxia.characters import open_characters
from tianxia.sqlite_world import open_world

ROOT = Path(__file__).parent
WEB = ROOT / "web"
CONTENT = load_content(ROOT / "content")
SAVE_DIR = ROOT / "saves"
PORT = 7861
COOKIE = "tx_session"
RECENT_ROWS = 5  # 「剛剛」之後直接列出幾則江湖紀錄
OLDER_ROWS = 30  # 「更早的紀錄」最多幾則（存檔本來就只留 30 則）
KINDS = ("武學", "內功")
DEFAULT_LAYER = "situation"
NAME_MAX = 16  # 角色名號的長度上限
BAD_NAME = f"名號最多 {NAME_MAX} 字，也不能有看不見的字元。"  # 看不見的字元（零寬、控制、雙向排版）會讓兩個名號看起來一樣
REPORT_EMPTY_TEXT = "還沒有戰報。打一場遭遇戰或劇情戰之後，這裡會列出每一場。"
UNCHANGED = object()  # 動作回傳它表示什麼都沒做：不存檔

_MD = MarkdownIt("commonmark", {"html": False, "breaks": True}).enable("table")

LOGIN_FAILURES: dict[str, list[float]] = {}  # 擋猜密碼的紀錄，整個伺服器共用、只放記憶體（帳號密碼登入設計第三節）
SESSIONS: dict[str, str] = {}  # cookie → 帳號（normalize 過的）
GAMES: dict[str, Game] = {}  # 名號（casefold）→ 這個角色唯一的一份 Game
_GAMES_LOCK = threading.Lock()


class GameError(Exception):
    """要直接告訴玩家的錯誤（帳號密碼不對、名號有人用……），回 400 與這句話。"""


def md(text: str | None) -> str:
    return _MD.render(text or "")


def account_store() -> AccountStore:
    return AccountStore(SAVE_DIR / "accounts" / "accounts.json", failures=LOGIN_FAILURES)


# ── 角色與存檔 ──────────────────────────────────────────


def open_game(name: str) -> Game:
    """讀取角色；舊格式讀不進來時，先把那一列搬到備份表再開新角色，不刪除任何東西。"""
    characters = open_characters()
    try:
        state = characters.load(name)
    except ValueError:  # pydantic 的 ValidationError 屬於 ValueError
        characters.backup(name)
        game = Game.new(CONTENT, name)
        game.notice("（舊存檔的格式已不相容，已備份起來；這是新的開始。）", "舊存檔已備份")
        return game
    if state is None:
        return Game.new(CONTENT, name)
    if state.player.bot is not None:  # 伺服器假人的存檔：不讓真人接手（伺服器假人設計第五節）
        raise GameError(NAME_TAKEN)
    return Game(CONTENT, state)


def game_for(name: str) -> Game:
    """這個角色在伺服器上唯一的一份 Game；第一次用到時才讀存檔。"""
    key = name.casefold()
    with _GAMES_LOCK:
        game = GAMES.get(key)
        if game is None:
            game = GAMES[key] = open_game(name)
        return game


def name_taken(name: str) -> bool:
    """名號有人用：已經有存檔（真人或假人一樣）、綁在某個帳號上，或是管理者的名號。
    假人與真人回同一句話，就沒辦法用名號試出誰是假人（帳號密碼登入設計第三節）。"""
    admins = {a.casefold() for a in CONTENT.config.admins}
    return open_characters().exists(name) or account_store().owner_of(name) is not None or name.casefold() in admins


def act(game: Game, action) -> list[str] | None:
    """同步時間 → 執行動作 → 存檔。拿跨程式的行動鎖（假人程式也拿同一把），計時器、按鈕與假人就一個一個來。
    回傳動作的訊息；動作回傳 UNCHANGED 時不存檔。"""
    with game.world.action_lock():
        game.sync(time.time())
        msgs = action(game)
        if msgs is UNCHANGED:
            return None
        open_characters().save(game.state)
        return msgs


def look(game: Game, view):
    """只讀的畫面（點名冊、切圖層、看戰報）：拿鎖但不同步、不存檔。"""
    with game.world.action_lock():
        return view(game)


def prepare_dialogue(game: Game, option_id: str) -> companion_agent.PreparedTurn | None:
    """對話選項在行動鎖外生成（企劃者 2026-10-03 核准的過渡做法，正解是線上架構第二階段的 LLM 佇列）。
    模型一輪要 9~10 秒，整段包在鎖裡的話全服玩家與假人程式都得跟著等。分三段：
      A（鎖內、很快）同步時間，問引擎這個選項現在會不會生成對話，會就拿到送模型的單子；
      B（鎖外、很慢）呼叫模型，失敗時單子裡的 turn 是 None；
      C（鎖內、很快）由呼叫端把結果交給 Game.choose(prepared=...)，引擎進鎖後重新核對再套用。
    這裡做 A 與 B，不會生成對話的選項（包含 talk:leave）回傳 None，由呼叫端走一般的 act()。"""
    with game.world.action_lock():
        game.sync(time.time())
        request = game.dialogue_request(option_id)
    if request is None:
        return None
    return companion_agent.prepare_turn(game.client, request)


def choose(game: Game, option_id: str) -> list[str] | None:
    prepared = None
    # 只有 talk:N 與交遊可能呼叫對話模型；talk:leave 永遠不會，不必多繞一趟備料的鎖
    if (option_id.startswith("talk:") and option_id != "talk:leave") or option_id == "act:socialize":
        prepared = prepare_dialogue(game, option_id)
    return act(game, lambda g: g.choose(option_id, prepared=prepared))


# ── 畫面資料 ──────────────────────────────────────────


def main_view(game: Game) -> dict:
    """江湖畫面與頂上的狀態列；每次動作、每次計時器都回這一份。呼叫端要拿著行動鎖。"""
    card = game.battle_card() if game.shows_battle_card() else None
    return {
        "status": game.status_data(),
        "quest": md(game.quest_text()),
        "scene": md(game.scene_text()),
        "options": [o.model_dump() for o in game.options()],
        "free_text": game.battle_free_text_prompt(),
        # 「剛剛」：這次行動打了仗就放戰鬥卡片，卡片沒寫到的補充放在 latest；沒打仗時 latest 是最新一則紀錄
        "card": md(card) if card is not None else None,
        "card_id": game.battle_card_id() if card is not None else None,
        "latest": game.battle_extra_html() if card is not None else game.latest_entry_html(),
        "journal": game.journal_html(1, RECENT_ROWS),
        "older": game.journal_html(1 + RECENT_ROWS, OLDER_ROWS),
        "minimap": game.minimap_svg(),
        "trends": md(game.trends_text()),
        "rumors": md(game.rumors_text()),
        "chronicle": md(game.chronicle_text()),
        "admin": game.is_admin(),
    }


def menxia_view(game: Game, person: str | None = None) -> dict:
    """修練與煉製兩頁的資料（同一份：心得、名冊、素材、功法庫都兩邊用得到）。person 是名冊裡點的人。"""
    lines = game.roster_lines()
    if person not in {key for _, key in lines}:
        person = None
    return {
        "xinde": game.state.player.stats.get("xinde", 0),
        "rules": md(game.menxia_rules()),
        "player_card": md(game.member_card("player")),
        "roster": [{"label": label, "key": key} for label, key in lines],
        "person": person,
        "person_card": md(game.member_card(person)) if person else None,
        "on_team": person is not None and person in game.state.player.team,
        "bag": md(game.bag_text()),
        "materials": [
            {"id": m.id, "name": m.name, "tier": materials.tier_label(m), "rank": m.tier, "attribute": m.attribute, "count": n}
            for m, n in materials.bag_contents(game.state, game.content)
        ],
        "per_craft": MATERIALS_PER_CRAFT,
        "arts": [{"label": label, "id": aid} for label, aid in game.art_library()],
        "craft_line": md(game.craft_line([], KINDS[0])),
    }


def map_view(game: Game, layer: str, selected: str | None) -> dict:
    places = game.map_places()
    if selected not in {loc_id for _, loc_id in places}:
        selected = game.state.player.location
    if layer not in Game.MAP_LAYERS:
        layer = DEFAULT_LAYER
    return {
        "header": md(game.map_header()),
        "layers": [{"id": key, "name": name} for key, name in Game.MAP_LAYERS.items()],
        "layer": layer,
        "svg": game.world_map_svg(layer, selected),
        "places": [{"label": label, "id": loc_id} for label, loc_id in places],
        "selected": selected,
        "here": game.state.player.location,
        "detail": md(game.place_detail(selected)),
        # 步行、趕路、疾行三個按鈕（照 atlas.MODES 的順序）；就在這裡時是 None
        "travel": [{"mode": o.mode, "label": o.label, "enabled": o.enabled} for o in game.travel_options(selected) or []]
        or None,
    }


def reports_view(game: Game, record_id: int | None) -> dict:
    if record_id is None:
        record_id = game.latest_battle_id()
    return {
        "list": [{"label": label, "id": rid} for label, rid in game.battle_list()],
        "selected": record_id,
        "detail": md(game.battle_detail(record_id)) if record_id is not None else md(REPORT_EMPTY_TEXT),
    }


def admin_choices() -> dict:
    """管理者觸發區的三個下拉選單（戰鬥、大事、大勢線）。照內容固定；已經發生過的大事按下去會被引擎拒絕。"""
    scenario = CONTENT.scenario
    return {
        "battles": [{"label": b.name, "id": b.id} for b in CONTENT.battles.values()],
        "events": [{"label": f"{x.text[:30]}（{x.id}）", "id": x.id}
                   for x in [*scenario.thresholds, *scenario.world_events]],
        "trends": [{"label": t.name, "id": t.id} for t in scenario.trends],
    }


def _int(value, default: int) -> int:
    """瀏覽器送來的數字：不是數字就當成預設值（範圍由引擎自己夾，例如閉關 1~12 小時）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def joined(msgs: list[str] | None) -> str:
    return md("\n\n".join(msgs)) if msgs else ""


# ── 登入 ──────────────────────────────────────────


def login(login_name: str, password: str) -> str:
    """回傳帳號（normalize 過）；失敗丟 GameError。"""
    try:
        account_store().authenticate(login_name, password)
    except AccountError as exc:
        raise GameError(str(exc))
    return normalize(login_name)


def register(login_name: str, password: str, again: str) -> str:
    if (password or "") != (again or ""):
        raise GameError(PASSWORDS_DIFFER)
    try:
        with open_world().action_lock():
            account_store().register(login_name, password)
    except AccountError as exc:
        raise GameError(str(exc))
    return normalize(login_name)


def create_character(account_key: str, name: str) -> Game:
    """建立角色：檢查名號沒人用 → 建存檔 → 綁到帳號，三步在同一把行動鎖裡做完（不跟假人程式取名撞在一起）。"""
    name = unicodedata.normalize("NFKC", name or "").strip()  # 全形英數字當成一般英數字：不能用「Ｒａｙａｌ」冒充「Rayal」
    if not name:
        raise GameError("請先輸入你的名號。")
    if len(name) > NAME_MAX or any(unicodedata.category(ch) in ("Cc", "Cf") for ch in name):
        raise GameError(BAD_NAME)
    store = account_store()
    with open_world().action_lock():
        account = store.get(account_key)
        if account is None:
            raise GameError("請先登入。")
        if account.character is not None:  # 連按兩次：已經建好了
            name = account.character
        else:
            if name_taken(name):
                raise GameError(NAME_TAKEN)
            game = Game.new(CONTENT, name)
            open_characters().save(game.state)
            store.bind_character(account_key, name)
    return game_for(name)


def change_password(account_key: str, old: str, new: str, again: str) -> str:
    if (new or "") != (again or ""):
        return PASSWORDS_DIFFER
    try:
        with open_world().action_lock():
            account_store().change_password(account_key, old, new)
    except AccountError as exc:
        return str(exc)
    return "密碼已更新。"


def reset_password(game: Game, target: str, temp: str) -> str:
    """管理者幫人重設密碼（先照帳號找，再照名號找）；臨時密碼由管理者私下告訴對方。"""
    if not game.is_admin():
        return "（只有管理者能重設密碼。）"
    store = account_store()
    try:
        with open_world().action_lock():
            key = store.find(target)
            if key is None:
                return "找不到這個帳號或名號。"
            store.set_password(key, temp)
    except AccountError as exc:
        return str(exc)
    return f"已重設 {store.get(key).login} 的密碼。"


# ── HTTP ──────────────────────────────────────────

app = FastAPI(title="天下大勢", docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(GameError)
def _game_error(request: Request, exc: GameError):
    return JSONResponse({"error": str(exc)}, status_code=400)


def _account(request: Request) -> str:
    key = SESSIONS.get(request.cookies.get(COOKIE, ""))
    if key is None:
        raise HTTPException(401, "請先登入。")
    return key


def _game(request: Request) -> Game:
    account = account_store().get(_account(request))
    if account is None or account.character is None:
        raise HTTPException(409, "這個帳號還沒有角色。")
    return game_for(account.character)


def _start_session(response: Response, account_key: str) -> None:
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = account_key
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=30 * 86400)


def _entry(account_key: str) -> dict:
    """登入後的去處：還沒角色就要取名號，有角色就直接進遊戲。"""
    account = account_store().get(account_key)
    if account is None:
        return {"stage": "login"}
    if account.character is None:
        return {"stage": "create"}
    game = game_for(account.character)
    act(game, lambda g: None)
    return {"stage": "game", "main": look(game, main_view), "kinds": KINDS}


@app.get("/")
def index():
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/journal.css")
def journal_css():
    return Response(JOURNAL_CSS, media_type="text/css")


@app.get("/api/me")
def me(request: Request):
    key = SESSIONS.get(request.cookies.get(COOKIE, ""))
    return {"stage": "login"} if key is None else _entry(key)


@app.post("/api/login")
def api_login(response: Response, body: dict = Body(...)):
    key = login(body.get("login", ""), body.get("password", ""))
    _start_session(response, key)
    return _entry(key)


@app.post("/api/register")
def api_register(response: Response, body: dict = Body(...)):
    key = register(body.get("login", ""), body.get("password", ""), body.get("again", ""))
    _start_session(response, key)
    return _entry(key)


@app.post("/api/character")
def api_character(request: Request, body: dict = Body(...)):
    key = _account(request)
    create_character(key, body.get("name", ""))
    return _entry(key)


@app.post("/api/logout")
def api_logout(request: Request, response: Response):
    SESSIONS.pop(request.cookies.get(COOKIE, ""), None)
    response.delete_cookie(COOKIE)
    return {"stage": "login"}


@app.get("/api/main")
def api_main(request: Request):
    """計時器：同步時間、存檔、回江湖畫面（氣血、體力等數字才會跟著走）。"""
    game = _game(request)
    act(game, lambda g: None)
    return look(game, main_view)


# 江湖畫面上的動作：回傳 {main, message}。引擎的訊息本來就會寫進江湖紀錄，這裡的 message
# 只有不寫紀錄的動作（例如管理者的操作）才用得到，前端拿它跳一句提示。
MAIN_ACTIONS = {
    "seclude": lambda g, b: g.seclude(_int(b.get("hours"), 8)),
    "battle_text": lambda g, b: g.submit_battle_custom_action(str(b.get("text", ""))),
    "anonymous": lambda g, b: g.set_anonymous(bool(b.get("value"))),
    "skip_tutorial": lambda g, b: g.skip_tutorial(),
    "view_map": lambda g, b: g.view_map(),
}
ADMIN_ACTIONS = {
    "open_season": lambda g, b: g.admin_open_season(time.time()),
    "next_season": lambda g, b: g.admin_next_season(time.time()),
    "fast_forward": lambda g, b: g.advance(_int(b.get("hours"), 1) * 3600),
    "start_battle": lambda g, b: g.admin_start_battle(str(b.get("id", "")), time.time()),
    "fire": lambda g, b: g.admin_fire(str(b.get("id", ""))),
    "push_trend": lambda g, b: g.admin_push_trend(str(b.get("id", "")), _int(b.get("amount"), 0)),
}


@app.post("/api/choose")
def api_choose(request: Request, body: dict = Body(...)):
    game = _game(request)
    choose(game, str(body.get("id", "")))
    return {"main": look(game, main_view)}


@app.post("/api/do/{op}")
def api_do(op: str, request: Request, body: dict = Body(default={})):
    game = _game(request)
    if op in ADMIN_ACTIONS:
        if not game.is_admin():
            raise GameError("只有管理者能這麼做。")
        msgs = act(game, lambda g: ADMIN_ACTIONS[op](g, body))
    elif op in MAIN_ACTIONS:
        msgs = act(game, lambda g: MAIN_ACTIONS[op](g, body))
    else:
        raise HTTPException(404)
    return {"main": look(game, main_view), "message": joined(msgs)}


MENXIA_ACTIONS = {
    "create": lambda g, b: g.create_skill(str(b.get("name") or ""), str(b.get("kind") or KINDS[0])),
    "practice": lambda g, b: g.practice(str(b.get("kind") or KINDS[0])),
    "heal": lambda g, b: g.heal(),
    "craft": lambda g, b: g.craft([str(m) for m in b.get("materials") or []], str(b.get("kind") or KINDS[0])),
    "switch": lambda g, b: g.switch_art(str(b.get("art") or "")),
    "join": lambda g, b: g.add_to_team(str(b.get("person") or "")),
    "leave": lambda g, b: g.remove_from_team(str(b.get("person") or "")),
}


@app.get("/api/menxia")
def api_menxia(request: Request, person: str | None = None):
    game = _game(request)
    return look(game, lambda g: menxia_view(g, person))


@app.post("/api/menxia/{op}")
def api_menxia_do(op: str, request: Request, body: dict = Body(default={})):
    """修練／煉製頁的動作：回傳 {menxia, main, message}，message 是這次動作的結果（顯示在那一頁最上面）。"""
    if op not in MENXIA_ACTIONS:
        raise HTTPException(404)
    game = _game(request)
    person = body.get("person")
    if op in ("join", "leave") and person not in {key for _, key in look(game, lambda g: g.roster_lines())}:
        raise GameError("名冊裡沒有這個人。")
    msgs = act(game, lambda g: MENXIA_ACTIONS[op](g, body))
    return {
        "menxia": look(game, lambda g: menxia_view(g, person)),
        "main": look(game, main_view),
        "message": joined(msgs),
    }


@app.post("/api/craft_line")
def api_craft_line(request: Request, body: dict = Body(default={})):
    """選了素材、換了種類就更新成本說明（不算行動、不存檔）。"""
    game = _game(request)
    materials = [str(m) for m in body.get("materials") or []]
    return {"line": look(game, lambda g: md(g.craft_line(materials, str(body.get("kind") or KINDS[0]))))}


@app.get("/api/reports")
def api_reports(request: Request, id: int | None = None):
    game = _game(request)
    return look(game, lambda g: reports_view(g, id))


@app.get("/api/map")
def api_map(request: Request, layer: str = DEFAULT_LAYER, place: str | None = None):
    game = _game(request)
    return look(game, lambda g: map_view(g, layer, place))


@app.post("/api/travel")
def api_travel(request: Request, body: dict = Body(...)):
    """「安排前往」（步行、趕路、疾行）：出發了就回 {main, arrived: true}，畫面回江湖、場景寫路上或抵達的地點；
    按鈕是舊的而走不成時（例如打開輿圖之後才冒出事件）回 {arrived: false, map, reason}，留在輿圖、寫出原因。"""
    game = _game(request)
    target = str(body.get("place", ""))
    mode = str(body.get("mode") or "walk")
    refused: list[str] = []

    def go(g: Game) -> list[str]:
        reason = g.travel_refusal(target, mode)
        if reason is not None:
            refused.append(reason)
        return g.travel(target, mode)

    act(game, go)
    out = {"main": look(game, main_view), "arrived": not refused}
    if refused:
        out["reason"] = refused[0]
        out["map"] = look(game, lambda g: map_view(g, str(body.get("layer") or DEFAULT_LAYER), target))
    return out


@app.post("/api/password")
def api_password(request: Request, body: dict = Body(...)):
    key = _account(request)
    return {"message": change_password(key, body.get("old", ""), body.get("new", ""), body.get("again", ""))}


@app.get("/api/admin")
def api_admin(request: Request):
    if not _game(request).is_admin():
        raise HTTPException(403)
    return admin_choices()


@app.post("/api/admin/reset_password")
def api_reset_password(request: Request, body: dict = Body(...)):
    return {"message": reset_password(_game(request), str(body.get("target", "")), str(body.get("temp", "")))}


app.mount("/static", StaticFiles(directory=WEB), name="static")


# ── 啟動 ──────────────────────────────────────────


def start_tunnel(port: int) -> None:
    """用 cloudflared 開臨時公開網址（trycloudflare，免帳號）。網址出現在它的輸出裡，原樣轉印出來。"""
    exe = shutil.which("cloudflared")
    if exe is None:
        print("找不到 cloudflared，沒有開公開網址。Windows 可以用 `winget install Cloudflare.cloudflared` 安裝。")
        return
    proc = subprocess.Popen(
        [exe, "tunnel", "--url", f"http://127.0.0.1:{port}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )

    def relay() -> None:
        for line in proc.stdout:
            if "trycloudflare.com" in line:
                url = line[line.find("https://"):].split()[0]
                print(f"公開網址：{url}（給手機用；有網址的人都進得來，不要外流）", flush=True)

    threading.Thread(target=relay, daemon=True).start()


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="天下大勢網頁伺服器")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--share", action="store_true", help="用 cloudflared 開一個臨時的公開網址")
    args = parser.parse_args()
    if args.share:
        start_tunnel(args.port)
    print(f"天下大勢：http://127.0.0.1:{args.port}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
