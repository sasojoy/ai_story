"""《天下大勢》的網頁伺服器：FastAPI 給資料，`web/` 裡的單頁網頁負責畫面。

取代原本的 Gradio 介面（`app.py`）。遊戲規則全部在 tianxia/，這個檔案只做三件事：
登入與角色、把每個動作包進跨程式的行動鎖（重讀角色 → 同步時間 → 動作 → 存檔）、把畫面需要的東西整理成 JSON。

- 數字、清單、選項用 JSON；引擎寫的大段文字（場景、事件、角色卡、戰報）是 Markdown，
  在這裡轉成 HTML 再送出（`md()`，原始 HTML 一律跳脫，名號裡的 `<` 不會變成標籤）。
  江湖紀錄、地圖沿用引擎產生的 HTML／SVG（線上架構設計第七節的混合做法）。
- 登入狀態放在 cookie（`tx_session`），伺服器記憶體裡對應到帳號；重開伺服器要重新登入。
- 資料庫是唯一的真實來源；同一個角色在伺服器上只有一份 `Game`（`GAMES`），每次進行動鎖都先從資料庫
  重讀角色（`_locked`）：同一個帳號開兩個分頁、換手機再登入，看到的都是最新存好的那一份，
  動作中途出錯撤回時，做到一半的改動也不會被下一個請求存回去（線上架構設計 5.1）。
- 人物對話照舊在行動鎖外生成（`prepare_dialogue`），模型的 9~10 秒不會卡住全服。

執行：`.venv/Scripts/python.exe server.py`（http://127.0.0.1:7861，預設只聽這台電腦）。要讓外面的手機連進來，
加 `--share`：會用 cloudflared 開一個臨時的公開網址（要先裝 cloudflared，見 CLAUDE.md）；
或加 `--lan`：讓同一個區網的裝置直接連過來（有網址的人都進得來）。
"""
from __future__ import annotations

import argparse
import contextlib
import contextvars
import hashlib
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
import unicodedata
from collections import deque
from collections.abc import Callable, Iterable
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt

from tianxia import companion_agent, event_llm, foreshadow, materials, rules, server_bots, team
from tianxia.accounts import NAME_TAKEN, PASSWORDS_DIFFER, AccountError, AccountStore, normalize
from tianxia.content import PROFILE_ENV, load_content, profile_line
from tianxia.characters import open_characters
from tianxia.craft import MATERIALS_PER_CRAFT
from tianxia.database import default_path, open_database
from tianxia.engine import Game
from tianxia.models import FREE_TEXT_MAX
from tianxia.journal import CSS as JOURNAL_CSS

ROOT = Path(__file__).parent
WEB = ROOT / "web"
PROFILE = os.environ.get(PROFILE_ENV) or None  # 設定覆寫檔（例如 weekend）；run_bots.py 要設同一個
CONTENT = load_content(ROOT / "content", profile=PROFILE)
PORT = 7861
COOKIE = "tx_session"
RECENT_ROWS = 5  # 「剛剛」之後直接列出幾則江湖紀錄
OLDER_ROWS = 30  # 「更早的紀錄」最多幾則（存檔本來就只留 30 則）
KINDS = ("武學", "內功")
DEFAULT_LAYER = "situation"
NAME_MAX = 16  # 角色名號的長度上限
BAD_NAME = f"名號最多 {NAME_MAX} 字，也不能有看不見的字元。"  # 看不見的字元（零寬、控制、雙向排版）會讓兩個名號看起來一樣
REPORT_EMPTY_TEXT = "還沒有戰報。打一場遭遇戰或劇情戰之後，這裡會列出每一場。"

_MD = MarkdownIt("commonmark", {"html": False, "breaks": True}).enable("table")

LOGIN_FAILURES: dict[str, list[float]] = {}  # 擋猜密碼的紀錄，整個伺服器共用、只放記憶體（帳號密碼登入設計第三節）
SESSIONS: dict[str, str] = {}  # cookie → 帳號（normalize 過的）
# 名號（casefold）→ 這個角色在伺服器上唯一的一份 Game。GAMES 只決定「這個角色的 Game 物件放在哪裡」，
# 不是存檔：資料庫才是真實來源，每次進行動鎖都把這份 Game 的 state 換成資料庫裡存好的那一列（見 _locked）。
GAMES: dict[str, Game] = {}
_GAMES_LOCK = threading.Lock()


class GameError(Exception):
    """要直接告訴玩家的錯誤（帳號密碼不對、名號有人用……），回 400 與這句話。"""


def md(text: str | None) -> str:
    return _MD.render(text or "")


def account_store() -> AccountStore:
    return AccountStore(open_database(), failures=LOGIN_FAILURES)


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
    """這個角色在伺服器上唯一的一份 Game；第一次用到時才讀存檔。所有分頁、裝置共用這一份物件，
    但它的 state 只是工作副本：每次進鎖都從資料庫重讀（_locked），所以鎖外看到的 state 可能已經過時，
    拿來做決定的讀取一律放在 act／look 的鎖裡。"""
    key = name.casefold()
    with _GAMES_LOCK:
        game = GAMES.get(key)
        if game is None:
            game = GAMES[key] = open_game(name)
        return game


def name_taken(name: str) -> bool:
    """名號不能用：已經有角色（真人或假人一樣）、綁在某個帳號上，或是保留的名號（三國名人、遊戲裡的人物、
    管理者，見 server_bots.reserved_names，FB-004）。全部回同一句話，就沒辦法用名號試出誰是假人、名單裡有誰
    （帳號密碼登入設計第三節）。"""
    reserved = {n.casefold() for n in server_bots.reserved_names(CONTENT)}
    return open_characters().exists(name) or account_store().owner_of(name) is not None or name.casefold() in reserved


def _reload(game: Game) -> None:
    """進鎖之後先從資料庫重新讀這個角色：上一個動作出錯撤回時，記憶體裡的 Game 還帶著做到一半的改動，
    不重讀的話下一次存檔會把它存回去；別的分頁、裝置（或同一個角色的另一份 Game）存過的改動也不會被蓋掉
    （線上架構設計 5.1）。還沒存過的新角色資料庫裡沒有，照舊用記憶體裡那一份。
    讀回來的角色不帶賽季（GameState.world 不進存檔），而且是資料庫裡原樣的那一列、沒經過 Game 建構時的清理
    （內容改版後存檔裡可能留著已經不存在的地點、事件、武學），所以接著跑一次 _drop_stale_references：
    它先把角色指回共用賽季（_reconcile_season），再清掉過時的引用；之後的 sync 會再對齊一次。
    資料庫裡這個名號的那一列是假人的存檔時，不換進來、跟 open_game 一樣回「名號已有人使用」：
    真人不能接手假人的角色（伺服器假人設計第五節）。"""
    stored = open_characters().load(game.state.player.name)
    if stored is not None and stored.player.bot is not None:
        raise GameError(NAME_TAKEN)
    if stored is not None:
        game.state = stored
    game._drop_stale_references()


# 這次請求的頁面選的走法（主畫面的「走法」切換：步行／趕路／疾行）。走法歸頁面管：頁面自己記著、每個請求都帶上
# （X-Move-Mode，見 _game），這裡在行動鎖裡套到 Game 上再排選單（見 _locked）。所以重新整理頁面就回到步行，
# 同一個角色開兩個分頁也各走各的、不會互相蓋掉——GAMES 裡一個角色只有一份 Game，走法只記在那份物件上就做不到。
# FastAPI 的同步端點各自在複製出來的 context 裡跑，設了只在這次請求裡有效；不經過 _game 的（登入、/api/me）就是步行。
MOVE_MODE: contextvars.ContextVar[str] = contextvars.ContextVar("move_mode", default="walk")


@contextlib.contextmanager
def _locked(game: Game):
    """拿行動鎖，並先重讀角色（見 _reload）。這支程式裡每一個要用 game.state 的地方都從這裡進鎖
    （act、look、prepare_dialogue），不另外呼叫 game.world.action_lock()：資料庫是唯一的真實來源，
    GAMES 裡的 Game 只是這一個動作的工作副本。FastAPI 的同步端點跑在執行緒池裡，同一個角色的兩個請求
    可能同時進來；行動鎖是 BEGIN IMMEDIATE，不同執行緒就一個一個來，重讀與動作不會交錯。"""
    with game.world.action_lock():
        _reload(game)
        game.set_move_mode(MOVE_MODE.get())  # 這次請求選的走法（見 MOVE_MODE）：之後的選單與 choose() 都照它
        yield


def act(game: Game, action) -> list[str] | None:
    """同步時間 → 執行動作 → 存檔。開一筆寫入交易（假人程式寫同一個資料庫），計時器、按鈕與假人就一個一個來。
    進鎖先從資料庫重讀角色（見 _reload）：動作丟例外時整筆撤回，下一個動作不會把失敗的改動存回去。
    回傳動作的訊息。動作之後一律存檔：同步寫進江湖紀錄的江湖大事，不能因為動作本身沒改東西就被下一次重讀丟掉。"""
    with _locked(game):
        game.sync(time.time())
        msgs = action(game)
        open_characters().save(game.state)
        return msgs


def look(game: Game, view):
    """只讀的畫面（點名冊、切圖層、看戰報）：拿鎖、重讀角色，但不同步、不存檔。"""
    with _locked(game):
        return view(game)


def prepare_dialogue(game: Game, option_id: str) -> companion_agent.PreparedTurn | None:
    """對話選項在行動鎖外生成（企劃者 2026-10-03 核准的過渡做法，正解是線上架構第二階段的 LLM 佇列）。
    模型一輪要 9~10 秒，整段包在鎖裡的話全服玩家與假人程式都得跟著等。分三段：
      A（鎖內、很快）同步時間，問引擎這個選項現在會不會生成對話，會就拿到送模型的單子；同步的結果（共用賽季的推進
        已經寫進資料庫、江湖大事寫進這個角色的江湖紀錄）要存起來，不然 C 段進鎖重讀就把它丟了；
      B（鎖外、很慢）呼叫模型，失敗時單子裡的 turn 是 None；
      C（鎖內、很快）由呼叫端把結果交給 Game.choose(prepared=...)，引擎進鎖後重新核對再套用。
    這裡做 A 與 B，不會生成對話的選項（包含 talk:leave）回傳 None，由呼叫端走一般的 act()。"""
    with _locked(game):
        game.sync(time.time())
        request = game.dialogue_request(option_id)
        open_characters().save(game.state)
    if request is None:
        return None
    return companion_agent.prepare_turn(game.client, request)


def may_generate_dialogue(option_id: str) -> bool:
    """這個選項按下去可能呼叫對話模型，要走鎖外生成（見 prepare_dialogue）：交友、對話的 talk:N、求見時指名的
    call:<人物>。告辭（talk:leave）與收起求見名單（call:back）永遠不會，不必多繞一趟備料的鎖。"""
    if option_id == "act:socialize":
        return True
    return option_id.startswith(("talk:", "call:")) and option_id not in ("talk:leave", "call:back")


def choose(game: Game, option_id: str) -> list[str] | None:
    prepared = None
    if may_generate_dialogue(option_id):
        prepared = prepare_dialogue(game, option_id)
    return act(game, lambda g: g.choose(option_id, prepared=prepared))


def answer_event(game: Game, text: str) -> list[str] | None:
    """事件的隨口應對（探索的多人與 LLM 玩法 §8.1），跟 prepare_dialogue 一樣分三段：
      A（鎖內、很快）同步時間，問引擎這句話現在能不能送；能就拿到單子（事件 id＋這句話），同步的結果照樣存起來；
      B（鎖外、很慢）請模型評這個做法的成功率，失敗一律 40；
      C（鎖內、很快）Game.answer_event 重驗還停在同一則事件、同一句話，才擲骰套用（對不上就不套用）；
      D、E 擲骰之後在鎖外請模型潤色一兩句，再進鎖插回那一則江湖紀錄（Game.add_gamble_narration）。"""
    with _locked(game):
        game.sync(time.time())
        request = game.free_text_request(text)
        open_characters().save(game.state)
    if request is None:
        raise GameError(f"寫一句 1～{FREE_TEXT_MAX} 字的做法；眼前的事已經過去的話，就不必再寫了。")
    event = CONTENT.events[request.event_id]
    rate = event_llm.assess_event_success_rate(game.client, event, request.text)
    msgs = act(game, lambda g: g.answer_event(request, rate))
    outcome = game.last_gamble
    if outcome is not None:  # D（鎖外）擲骰之後請模型潤色一兩句，E（鎖內）插回那一則紀錄；失敗就只留結果文字
        narration = event_llm.narrate_event_gamble(game.client, event, outcome.text, outcome.success, outcome.effect_text)
        if narration:
            act(game, lambda g: g.add_gamble_narration(outcome, narration))
    return msgs


# ── 畫面資料 ──────────────────────────────────────────


def main_view(game: Game) -> dict:
    """江湖畫面與頂上的狀態列；每次動作、每次計時器都回這一份。呼叫端要拿著行動鎖。"""
    card = game.battle_card() if game.shows_battle_card() else None
    status, quest, scene = game.status_data(), md(game.quest_text()), md(game.scene_text())
    options = game.options()  # 照原本的順序：狀態、主線、場景先讀，選單（會推進全服戰鬥）最後
    view = {
        "status": status,
        "quest": quest,
        "scene": scene,
        "options": [o.model_dump() for o in options],
        # 在路上（路上設計 3.3）：頁面在選項底下多放三個捷徑（輿圖、修練、煉製），那是頁面切換、不是引擎的行動。
        # 看的是選單本身：參戰者在決戰大區裡走動時選單是戰鬥選項，那時不放捷徑
        "on_road": any(o.id == "act:on_road" for o in options),
        "free_text": game.battle_free_text_prompt(),
        "event_free_text": game.event_free_text_prompt(),  # 眼前事件的隨口應對：選單上那一顆按下去叫出輸入框
        # 「剛剛」：這次行動打了仗就放戰鬥卡片，卡片沒寫到的補充放在 latest；沒打仗時 latest 是最新一則紀錄
        "card": md(card) if card is not None else None,
        "card_id": game.battle_card_id() if card is not None else None,
        "latest": game.battle_extra_html() if card is not None else game.latest_entry_html(),
        "journal": game.journal_html(1, RECENT_ROWS),
        "older": game.journal_html(1 + RECENT_ROWS, OLDER_ROWS),
        "minimap": game.minimap_svg(),
        "bulletin": [md(text) for text in game.bulletin()],  # 江湖頁最上面的公告卡：這一週的大事；開關關著是空的
        "trends": md(game.trends_text()),
        "rumors": md(game.rumors_text()),
        "chronicle": md(game.chronicle_text()),
        "admin": game.is_admin(),
    }
    if "fronts" in status:  # 第一季濃縮版才有：江湖頁的三條戰況（開關關著時不送，頁面照舊）
        view["fronts"] = status["fronts"]
    return view


def menxia_view(game: Game, person: str | None = None) -> dict:
    """修練與煉製兩頁的資料（同一份：心得、名冊、素材、功法庫都兩邊用得到）。person 是名冊裡點的人。"""
    lines = game.roster_lines()
    if person not in {key for _, key in lines}:
        person = None
    member = game.state.player.member
    # 身上兩門各自有沒有功法、練到第幾成、練滿了沒（C4 自創欄收不收、C5 鍛鍊鈕亮不亮）；還沒學是 False、0、False
    learned = {"武學": member.wugong_id is not None, "內功": member.neigong_id is not None}
    level = {
        "武學": member.wugong_level if learned["武學"] else 0,
        "內功": member.neigong_level if learned["內功"] else 0,
    }
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
        # 素材旁的「伏筆物品」：開關開著、這一季蓋了章、手上有才有東西，沒有就是空的（畫面整塊不出現）。只有名字與數量
        "clue_items": [
            {"id": item.id, "name": item.name, "count": n} for item, n in foreshadow.held_items(game.state, game.content)
        ],
        "per_craft": MATERIALS_PER_CRAFT,
        # 功法卡（FB-006）：身上兩門各一張，還沒學的那一門是一句「你還沒有內功。」；
        # 功法庫通常只有幾門，卡一起送，點開不必再打一次 API（QA L4：先看卡再改練）
        "slot_cards": [
            {"kind": k, "card": md(game.skill_detail(k)), "learned": learned[k], "level": level[k],
             "maxed": level[k] >= team.MAX_LEVEL}
            for k in KINDS
        ],
        "arts": [{"label": label, "id": aid, "card": md(game.art_detail(aid))} for label, aid in game.art_library()],
        "craft_line": md(game.craft_line([])),
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


def admin_choices(game: Game) -> dict:
    """管理者觸發區的三個下拉選單（戰鬥、大事、大勢線）。戰鬥與大事照內容固定（已經發生過的大事按下去會被引擎拒絕）；
    大勢線照這一季的規則（第一季濃縮版要開關開著、而且這一季蓋了「開」的章）。呼叫端要拿著行動鎖（look）。"""
    scenario = CONTENT.scenario
    world = game.state.world
    return {
        "battles": [{"label": b.name, "id": b.id} for b in CONTENT.battles.values()],
        "events": [{"label": f"{x.text[:30]}（{x.id}）", "id": x.id}
                   for x in [*scenario.thresholds, *scenario.world_events]],
        # 照開關：關著時不列第一季才有的線；開著時不列黃巾聲勢（由三條戰線合成，不能直接推）
        "trends": [{"label": t.name, "id": t.id} for t in scenario.trends if rules.pushable(CONTENT, world, t.id)],
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
        account_store().register(login_name, password)  # 自己是一筆交易；不另外包一層：scrypt 很慢，不能握著寫入權算
    except AccountError as exc:
        raise GameError(str(exc))
    return normalize(login_name)


def create_character(account_key: str, name: str) -> Game:
    """建立角色：檢查名號沒人用 → 建存檔 → 綁到帳號，三步在同一筆交易裡做完（不跟假人程式取名撞在一起）。"""
    name = unicodedata.normalize("NFKC", name or "").strip()  # 全形英數字當成一般英數字：不能用「Ｒａｙａｌ」冒充「Rayal」
    if not name:
        raise GameError("請先輸入你的名號。")
    if len(name) > NAME_MAX or any(unicodedata.category(ch) in ("Cc", "Cf") for ch in name):
        raise GameError(BAD_NAME)
    store = account_store()
    with open_database().transaction():
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
        account_store().change_password(account_key, old, new)  # 同上：自己是一筆交易，慢的雜湊不在交易裡算
    except AccountError as exc:
        return str(exc)
    return "密碼已更新。"


def reset_password(game: Game, target: str, temp: str) -> str:
    """管理者幫人重設密碼（先照帳號找，再照名號找）；臨時密碼由管理者私下告訴對方。"""
    if not game.is_admin():
        return "（只有管理者能重設密碼。）"
    store = account_store()
    try:
        with open_database().transaction():
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
    MOVE_MODE.set(request.headers.get("X-Move-Mode", "walk"))  # 頁面選的走法，只在這次請求裡有效（見 MOVE_MODE）
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


def content_version(content: bytes) -> str:
    """檔案內容的雜湊（前十碼）：內容沒變、版本就不變，所以只動引擎的更版不會讓手機重抓。"""
    return hashlib.sha256(content).hexdigest()[:10]


def asset_version(url_path: str) -> str:
    """頁面引用的網址（/journal.css 或 /static/<檔名>）對應的版本；檔案不存在就丟 FileNotFoundError。"""
    if url_path == "/journal.css":
        return content_version(JOURNAL_CSS.encode("utf-8"))
    return content_version((WEB / url_path.removeprefix("/static/")).read_bytes())


# 頁面裡指向我們自己檔案的網址；不碰 data:、外部網址，也不碰已經帶了 ? 的
OWN_ASSET = re.compile(r"""(src|href)=(["'])(/static/[^"'?#]+|/journal\.css)\2""")


def versioned_page(html: str, version_of: Callable[[str], str]) -> str:
    """把頁面裡指向我們自己檔案的網址都加上 ?v=<版本>。
    新網址就是新的快取鍵：手機上已經快取了舊檔，也會因為網址變了而重抓。"""
    return OWN_ASSET.sub(lambda m: f"{m[1]}={m[2]}{m[3]}?v={version_of(m[3])}{m[2]}", html)


# 啟動時算一次；index.html 指到 web/ 裡沒有的檔，這裡就丟例外
PAGE = versioned_page((WEB / "index.html").read_bytes().decode("utf-8"), asset_version)
NO_CACHE = {"Cache-Control": "no-cache"}  # 每次都向伺服器確認（有 ETag，沒變就是 304）；不用 immutable：開發時改了檔沒重開，會被瀏覽器釘死


class WebFiles(StaticFiles):
    """/static 的每個回應都加 no-cache；不然瀏覽器會用啟發式快取，更版後留著舊檔好幾個小時。"""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


@app.get("/")
def index():
    return HTMLResponse(PAGE, headers=NO_CACHE)


@app.get("/journal.css")
def journal_css():
    return Response(JOURNAL_CSS, media_type="text/css", headers=NO_CACHE)


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
    "end_season": lambda g, b: g.admin_end_season(time.time()),
    "next_season": lambda g, b: g.admin_next_season(time.time()),
    "fast_forward": lambda g, b: g.advance(_int(b.get("hours"), 1) * 3600),
    "start_battle": lambda g, b: g.admin_start_battle(str(b.get("id", "")), time.time()),
    "fire": lambda g, b: g.admin_fire(str(b.get("id", ""))),
    "push_trend": lambda g, b: g.admin_push_trend(str(b.get("id", "")), _int(b.get("amount"), 0)),
}


@app.post("/api/choose")
def api_choose(request: Request, body: dict = Body(...)):
    game = _game(request)
    option_id = str(body.get("id", ""))
    msgs = choose(game, option_id)
    out = {"main": look(game, main_view)}
    if option_id.startswith("battle:"):
        # 決戰選項（加入、趕到、每回合的出招）：按下去發生了什麼只有這句回話（FB-030），前端拿它跳一句提示。
        # 其他選項的話已經寫進江湖紀錄、「剛剛」看得到，再回一句會重複，所以不回。
        out["message"] = joined(msgs)
    return out


@app.post("/api/answer")
def api_answer(request: Request, body: dict = Body(...)):
    game = _game(request)
    answer_event(game, str(body.get("text", "")))
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
    "craft": lambda g, b: g.craft([str(m) for m in b.get("materials") or []]),  # 內功／武學開爐才揭曉，body 的 kind 不看
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

    def run(g: Game):
        # 名冊（誰是你的人）是全服狀態，換季、假人程式都會改：跟動作在同一把鎖裡核對，引擎才能假設那個人在名冊上
        if op in ("join", "leave") and person not in {key for _, key in g.roster_lines()}:
            raise GameError("名冊裡沒有這個人。")  # 交易整筆撤回（連同進鎖時的同步）；下一個請求重讀再算一次
        return MENXIA_ACTIONS[op](g, body)

    msgs = act(game, run)
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
    return {"line": look(game, lambda g: md(g.craft_line(materials)))}


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
    game = _game(request)
    if not game.is_admin():
        raise HTTPException(403)
    return look(game, admin_choices)


@app.post("/api/admin/reset_password")
def api_reset_password(request: Request, body: dict = Body(...)):
    return {"message": reset_password(_game(request), str(body.get("target", "")), str(body.get("temp", "")))}


app.mount("/static", WebFiles(directory=WEB), name="static")


# ── 啟動 ──────────────────────────────────────────


TUNNEL_URL = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com")
# cloudflared 第一行「Requesting new quick Tunnel on trycloudflare.com...」有網域、沒有 https://，所以只認完整的網址；
# 要不到隧道時它的錯誤訊息會帶 https://api.trycloudflare.com（它自己的服務），那個也不是給手機用的。


TUNNEL_TAIL_LINES = 20  # 拿不到網址時，結束前印出 cloudflared 最後這幾行，讓主機端看得到原因


def _say(text: str) -> None:
    print(text, flush=True)


def relay_tunnel_output(lines: Iterable[str], emit: Callable[[str], None] = _say) -> None:
    """把 cloudflared 的輸出逐行讀到結束（EOF）：第一次看到公開網址就印一次，其他輸出照舊安靜。

    一定要把管線讀乾淨：沒人讀的話緩衝寫滿時 cloudflared 會卡住，隧道跟著停。
    所以不提早結束，也不因為任何一行格式怪就丟例外（不認得的行直接跳過）。
    輸出平常是吞掉的，只記住最後 TUNNEL_TAIL_LINES 行（去掉行尾換行、空行不記），不轉印；
    讀到結束還沒拿到網址，就先說一句、再把這幾行印出來（錯誤原因通常就在裡面）；
    連一行輸出都沒有就改說「沒有任何輸出」。拿到網址的路徑完全不印這些。"""
    announced = False
    tail: deque[str] = deque(maxlen=TUNNEL_TAIL_LINES)
    for line in lines:
        found = TUNNEL_URL.search(line)
        if found and not announced:
            announced = True
            emit(f"公開網址：{found.group()}（給手機用；有網址的人都進得來，不要外流）")
        text = line.rstrip()
        if text:
            tail.append(text)
    if announced:
        return
    if not tail:
        emit("cloudflared 沒有任何輸出就結束了。")
        return
    emit("cloudflared 已結束，沒有拿到公開網址。它最後的輸出：")
    for text in tail:
        emit(text)


def start_tunnel(port: int) -> threading.Thread | None:
    """用 cloudflared 開臨時公開網址（trycloudflare，免帳號）。網址出現在它的輸出裡，原樣轉印出來。

    回傳讀 cloudflared 輸出的執行緒（沒裝 cloudflared 時回傳 None）；main() 不必理會，測試用它 join。"""
    exe = shutil.which("cloudflared")
    if exe is None:
        print("找不到 cloudflared，沒有開公開網址。Windows 可以用 `winget install Cloudflare.cloudflared` 安裝。")
        return None
    proc = subprocess.Popen(
        [exe, "tunnel", "--url", f"http://127.0.0.1:{port}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )
    thread = threading.Thread(target=relay_tunnel_output, args=(proc.stdout,), daemon=True)
    thread.start()
    return thread


def main(argv: list[str] | None = None) -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="天下大勢網頁伺服器")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--share", action="store_true", help="用 cloudflared 開一個臨時的公開網址")
    parser.add_argument(
        "--lan", action="store_true",
        help="讓同一個區網的裝置也連得到（綁在所有網卡上；有網址的人都進得來，沒加就只聽這台電腦）",
    )
    args = parser.parse_args(argv)
    if args.share:
        start_tunnel(args.port)  # cloudflared 連的是 http://127.0.0.1:{port}，只聽本機也照常運作
    print(f"天下大勢：http://127.0.0.1:{args.port}", flush=True)
    print(f"資料庫：{default_path().resolve()}", flush=True)  # 跟 run_bots.py 要是同一個檔；TIANXIA_DB 設錯時一眼看得出來
    print(profile_line(CONTENT, PROFILE), flush=True)  # TIANXIA_PROFILE 也是：兩個程式要用同一份設定
    if args.lan:
        print("已開放區網連線：同一個網路裡的裝置都連得到。", flush=True)
    uvicorn.run(app, host="0.0.0.0" if args.lan else "127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
