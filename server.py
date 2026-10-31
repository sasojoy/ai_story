"""《天下大勢》的網頁伺服器：FastAPI 給資料，`web/` 裡的單頁網頁負責畫面。

取代原本的 Gradio 介面（`app.py`）。遊戲規則全部在 tianxia/，這個檔案只做三件事：
登入與角色、把每個動作包進跨程式的行動鎖（重讀角色 → 同步時間 → 動作 → 存檔）、把畫面需要的東西整理成 JSON。

- 數字、清單、選項用 JSON；引擎寫的大段文字（場景、事件、角色卡、戰報）是 Markdown，
  在這裡轉成 HTML 再送出（`md()`，原始 HTML 一律跳脫，名號裡的 `<` 不會變成標籤）。
  江湖紀錄、地圖沿用引擎產生的 HTML／SVG（線上架構設計第七節的混合做法）。
- 登入狀態放在 cookie（`tx_session`），資料庫的 sessions 表只存它的雜湊、對應到帳號（`accounts.SessionStore`，審查 S-10）；
  重開伺服器不必重新登入。
- 資料庫是唯一的真實來源；同一個角色在伺服器上只有一份 `Game`（`GAMES`），每次進行動鎖都先從資料庫
  重讀角色（`_locked`）：同一個帳號開兩個分頁、換手機再登入，看到的都是最新存好的那一份，
  動作中途出錯撤回時，做到一半的改動也不會被下一個請求存回去（線上架構設計 5.1）。
- 人物對話照舊在行動鎖外生成（`prepare_dialogue`），模型的 9~10 秒不會卡住全服。
- 開爐的首次取名也在行動鎖外（`prepare_forge`／`forge`），整段有時間預算（`Config.naming_budget_seconds`），
  用完走退路字表，請求在 trycloudflare 切斷之前結束。
- 大場面（挑戰大勢人物本人、打頭目）的判讀也在行動鎖外（`prepare_fight`），預算是 `Config.big_fight_budget_seconds`；
  一般的仗不問模型，備料與動作在同一次拿鎖裡做完。
- 對話生成與隨口應對的評分、潤色也有總預算（`Config.dialogue_budget_seconds`、`free_text_budget_seconds`；評分與潤色共用
  後面那一份），跟開爐、大場面一樣從備料那一段開始算、扣掉等鎖與排隊的時間。
- 鎖外的五個模型呼叫（對話生成、大場面判讀、開爐取名、隨口應對的評分與潤色）一律走 `model_call`：開關
  `Config.llm_queue_slots`（預設 0＝關）打開時先排隊（`llm_queue.py`：真人先、假人有上限、排太久被擋下來；同一個人同時只有一件，
  第二件被擋下來——評分、開爐、大場面、對話回一句話、什麼都不套用（對話是 FB-077），潤色不插句子；排超過等候的時間還沒輪到的那一件也一樣，
  不給退路，PM 2026-10-06），
  關著就直接叫。鎖內的小呼叫（`Game._quick_client`）與排程不進佇列。
- 伺服器推送（`server_push.py`，開關 `Config.push_events`，預設關）：開著時 `/api/events` 是 SSE，每個動作做完（五個動作的端點，
  鎖放掉之後）通知這個角色的其他分頁，背景的看守發現公開的世界變了通知所有分頁；只送「哪一種變了」，頁面收到再抓 `/api/main`。
  輪詢與開頁絕不通知。關著 `/api/events` 是 404，頁面照舊每 10 秒輪詢。

執行：`.venv/Scripts/python.exe server.py`（http://127.0.0.1:7861，預設只聽這台電腦）。要讓外面的手機連進來，
加 `--share`：會用 cloudflared 開一個臨時的公開網址（要先裝 cloudflared，見 CLAUDE.md）；
或加 `--lan`：讓同一個區網的裝置直接連過來（有網址的人都進得來）。
"""
from __future__ import annotations

import argparse
import contextlib
import contextvars
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
import unicodedata
import weakref
from urllib.parse import urlsplit
from collections import deque
from collections.abc import Callable, Iterable
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt
from starlette.concurrency import run_in_threadpool

import console
import server_push
import zhuan_html
from llm_queue import Busy, LlmQueue, QueueTimeout
from tianxia import (
    arena_crowd, ascend, battle_instance, flavor, battlelog, biography, calendar, companion_agent, create, divine, duel, epiphany, event_llm, fight_llm, foreshadow, gather_llm, gender, glyph, insight_llm, leaderboard, letters, mapdata, might,
    naming, narration, outing,
    ollama_client, power_save, rules,
    precise, seal, seal_duel, server_bots, social, sortie, speech, tale, tavern, team, timetable, training, treasures, weekcard, xingshi, yuedan,
    zhuan_end,
)
from tianxia.accounts import NAME_TAKEN, PASSWORDS_DIFFER, SESSION_SECONDS, AccountError, AccountStore, SessionStore, normalize
from tianxia.content import env_profile, load_content, profile_line
from tianxia.characters import name_key, open_characters
from tianxia.database import default_path, open_database
from tianxia.flavor import FlavorJob
from tianxia.engine import FIGHT_GONE_LINES, FREE_TEXT_OPTION, PAUSED_TEXT, SAY_OPTION, TEXT_TALKS, Game, Refused
from tianxia.core import features as features_core  # 功能包：殼照 FEATURES 掛管理者工具與路由（開發規範手冊 3.1）
from tianxia.features.feast import rules as feasts  # 宴客自己寫的敬酒詞：鎖外評分（三段式還在殼裡，過渡）
from tianxia.models import FREE_TEXT_MAX
from tianxia.notices import KINDS as NOTICE_KINDS
from tianxia.notices import current as current_notices
from tianxia.journal import CSS as JOURNAL_CSS
from tianxia.sqlite_world import open_world
from tianxia.ollama_client import OllamaClient
from tianxia.playlog import FIGURE_TALK, FREE_TEXT, PlayLog, button_of
from tianxia.world_state import season_length_days

ROOT = Path(__file__).parent
WEB = ROOT / "web"


def scene_art(game: Game, status: dict) -> dict | None:
    """江湖頁場景卡上面那張圖（減法季批 8 圖像版）：引擎挑圖（Game.scene_art），這裡只看 web/img/<路徑>.webp 真的在不在——
    沒檔案就不給（None），網頁一字不變（同 horse_art：正式圖到了放進資料夾就上，程式不用改）。head 是場景 Markdown 的第一段轉好的
    HTML，網頁有圖時把那一段拿掉、把地名／危險／時刻（事件標題；人名與情誼）疊在圖的下緣。"""
    got = game.scene_art()
    if got is None or not (WEB / "img" / f"{got['path']}.webp").is_file():
        return None
    cal = status.get("calendar")
    when = cal["text"] if cal and cal.get("text") else f"第{status['day']}天 {status['clock']}"
    return {
        "kind": got["kind"], "src": f"/static/img/{got['path']}.webp", "title": got["title"], "sub": got["sub"],
        "time": when if got["kind"] == "place" else "", "head": md(got["head"]),
    }


def story_cards(game: Game) -> list[dict]:
    """特殊事件的跳顯框（Game.story_card_view）：圖檔真的在 web/img/ 才給 src（同 scene_art），內文轉成 HTML。"""
    out = []
    for card in game.story_card_view():
        image = card.pop("image")
        card["src"] = f"/static/img/{image}.webp" if image and (WEB / "img" / f"{image}.webp").is_file() else None
        card["text"] = md(card["text"])
        out.append(card)
    return out


def zhuan_art_src(key: str | None) -> str | None:
    """列傳插畫（減法季批 7b，zhuan_end.illustration_for 的圖庫鍵）的網址：web/img/zhuan/<鍵>.webp 真的在才給（雲端批 8 放圖；同 scene_art）。"""
    if not key:
        return None
    path = zhuan_end.art_path(key)
    return f"/static/img/{path}.webp" if (WEB / "img" / f"{path}.webp").is_file() else None


def horse_art() -> list[str]:
    """web/ 裡真的有的馬圖（web/horse-<鍵>.webp，鍵見 mounts.COAT_ART、STEED_ART）：網頁只對這些鍵放圖，其餘照舊畫色塊。"""
    return sorted(path.stem.removeprefix("horse-") for path in WEB.glob("horse-*.webp"))
PROFILE = env_profile()  # 設定覆寫檔（TIANXIA_PROFILE，例如 weekend）；run_bots.py、scripts/set_password.py 讀同一個
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
REGISTRATIONS: dict[str, list[float]] = {}  # 註冊的次數（來源 IP → 最近一小時註冊成功的時間），只放記憶體（審查 S-10）
REGISTER_LIMIT = 5  # 同一個來源 IP 一小時最多註冊幾個帳號
REGISTER_WINDOW = 3600.0
TOO_MANY_REGISTERS = "這個網路註冊太多帳號了，請一小時後再試。"
_REGISTER_LOCK = threading.Lock()


class _Sessions:
    """cookie → 帳號（normalize 過的）：存在資料庫（accounts.SessionStore，審查 S-10），重開伺服器照樣認得。
    每次都照當下的資料庫開（測試每個換一個暫存檔）；介面照以前的 dict 留著 get／pop／clear。"""

    @staticmethod
    def _store() -> SessionStore:
        return SessionStore(open_database())

    def get(self, token: str | None) -> str | None:
        return self._store().get(token)

    def create(self, account_key: str) -> str:
        return self._store().create(account_key)

    def pop(self, token: str | None, default: str | None = None) -> str | None:
        return self._store().pop(token, default)

    def clear(self) -> None:
        self._store().clear()


SESSIONS = _Sessions()
# 名號（casefold）→ 這個角色在伺服器上唯一的一份 Game。GAMES 只決定「這個角色的 Game 物件放在哪裡」，
# 不是存檔：資料庫才是真實來源，每次進行動鎖都把這份 Game 的 state 換成資料庫裡存好的那一列（見 _locked）。
GAMES: dict[str, Game] = {}
_GAMES_LOCK = threading.Lock()
# GAMES 不是只進不出（審查 S-06：一份 Game 約 1.4 MB，上線過的人越多越大）：GAME_IDLE_SECONDS 沒有請求用到的那一份，下一次
# game_for 時順手丟掉（最多每 GAME_SWEEP_SECONDS 掃一次），再有請求時照第一次的樣子從資料庫重建（open_game）。丟掉不會掉東西：
# 每次進鎖本來就從資料庫重讀（_reload），Game 上其他的欄位都只活在一個請求裡。唯一的例外是管理者「時間快轉」推過的那一截
# （Game.advanced_real，回體丹換日看它，留在那一份上直到伺服器重開），快轉過的那一份不丟。還有請求拿著的那一份（三段式的 B 段在
# 鎖外等模型）在 GAME_USED 裡是剛剛才用過的，不會被丟；就算丟了，那個請求手上那一份照樣能用（C 段照舊進鎖重讀）。
# 時鐘用伺服器自己的 _game_clock（引擎不讀時鐘），測試換掉它就不必真的等。
GAME_IDLE_SECONDS = 30 * 60
GAME_SWEEP_SECONDS = 60
_game_clock = time.monotonic
GAME_USED: weakref.WeakKeyDictionary[Game, float] = weakref.WeakKeyDictionary()  # 每一份 Game 最後一次被請求用到（_game_clock 的秒）
_games_swept: float | None = None  # 上一次掃 GAMES 的時刻
# 勝算的記憶（FB-321）：所有角色的 Game 共用這一份（game_for 掛上），輿圖疊層的勝算輸入一樣就不再在行動鎖裡模擬四十場
ODDS_MEMO = team.OddsMemo()


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
    now = _game_clock()
    with _GAMES_LOCK:
        _sweep_games(now)
        game = GAMES.get(key)
        if game is None:
            game = GAMES[key] = open_game(name)
            game.odds_memo = ODDS_MEMO
            if NARRATION is not None:  # 事件旁白每週改寫（減法季批 10）：這一週寫好的旁白從小檔讀
                game.narration = NARRATION.get
        GAME_USED[game] = now
        return game


def _sweep_games(now: float) -> None:
    """丟掉 GAME_IDLE_SECONDS 沒被用到的 Game（見 GAME_IDLE_SECONDS）；最多每 GAME_SWEEP_SECONDS 掃一次。呼叫端拿著 _GAMES_LOCK。
    沒記過用到時間的（測試直接塞進 GAMES 的）不丟。"""
    global _games_swept
    if _games_swept is not None and now - _games_swept < GAME_SWEEP_SECONDS:
        return
    _games_swept = now
    for key, game in list(GAMES.items()):
        used = GAME_USED.get(game)
        if used is not None and now - used >= GAME_IDLE_SECONDS and not game.advanced_real:
            del GAMES[key]


def _used(game: Game) -> None:
    """這一份 Game 剛被用過（進鎖、出鎖時記）：一個請求拖得再久（鎖外等模型），它都不算閒著。"""
    with _GAMES_LOCK:
        GAME_USED[game] = _game_clock()


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


# 這次請求的頁面選的走法（主畫面的「走法」切換：步行／疾行）。走法歸頁面管：頁面自己記著、每個請求都帶上
# （X-Move-Mode，見 _game），這裡在行動鎖裡套到 Game 上再排選單（見 _locked）。所以重新整理頁面就回到步行，
# 同一個角色開兩個分頁也各走各的、不會互相蓋掉——GAMES 裡一個角色只有一份 Game，走法只記在那份物件上就做不到。
# FastAPI 的同步端點各自在複製出來的 context 裡跑，設了只在這次請求裡有效；不經過 _game 的（登入、/api/me）就是步行。
MOVE_MODE: contextvars.ContextVar[str] = contextvars.ContextVar("move_mode", default="walk")


# ── 鎖內模型呼叫的全服斷路器（PM 2026-10-05）──
# 鎖內每一步模型呼叫最多等 Config.in_lock_model_timeout（15 秒），一次拿鎖期間只容忍一次失敗（Game._quick_client）。可是模型
# 掛了的時候，每個玩家的下一個動作都還是要在行動鎖裡等一次逾時，全服跟著等。所以任何一次拿鎖裡有鎖內的模型呼叫失敗或逾時，
# 就把全服的斷路器打開 MODEL_BREAKER_SECONDS 秒：這段時間每一次拿鎖（不分玩家）一開始額度就用完，鎖內直接用固定文字、
# 不碰網路；時間到之後的第一次拿鎖照常叫模型，又失敗就再打開。只管鎖內：鎖外的取名、對話、隨口應對的評分照舊叫模型。
# 只在 server.py（PM：不進 Config）；假人程式（run_bots.py）鎖內的 Game 沒有 client，用不到它。假人替首創配方與絕學定名取名是
# 在鎖外、用它自己的 client（bot_runner._name_and_apply，一次一件、至少隔 bot_naming_gap_seconds），在另一個程式裡，這個斷路器管不到。
MODEL_BREAKER_SECONDS = 180
_monotonic = time.monotonic  # 斷路器的時鐘（引擎不讀時鐘，伺服器可以）；測試換掉它，不必真的等
_BREAKER_LOCK = threading.Lock()  # 「到期了就關上、印一行」是先讀再寫：兩個請求同時進來也只關一次、只印一行
_breaker_until: float | None = None  # 斷路器開到什麼時候（_monotonic 的秒數）；None＝關著


def _model_paused() -> bool:
    """這一次拿鎖時斷路器還開著嗎？已經到期的話先關上（印一行），這一次照常叫模型。"""
    global _breaker_until
    with _BREAKER_LOCK:
        if _breaker_until is None:
            return False
        if _monotonic() < _breaker_until:
            return True
        _breaker_until = None
    print(f"鎖內的模型呼叫暫停滿 {MODEL_BREAKER_SECONDS} 秒，下一次再試模型。", flush=True)
    return False


def _pause_model() -> None:
    """有一次鎖內的模型呼叫失敗或逾時：打開斷路器 MODEL_BREAKER_SECONDS 秒（已經開著的不延長、不再印）。
    印的那一行不寫是誰的動作（也就看不出是不是假人）。"""
    global _breaker_until
    with _BREAKER_LOCK:
        now = _monotonic()
        if _breaker_until is not None and now < _breaker_until:
            return
        _breaker_until = now + MODEL_BREAKER_SECONDS
    print(f"鎖內的模型呼叫失敗或逾時：接下來 {MODEL_BREAKER_SECONDS} 秒全服鎖內不叫模型，改用固定文字。", flush=True)


@contextlib.contextmanager
def _model_guard(game: Game):
    """已經拿到行動鎖之後：這一次拿鎖的鎖內模型額度重新開始；全服斷路器開著時一開始就用完；這一次拿鎖裡（動作出錯也算）
    有鎖內的模型呼叫失敗，就打開斷路器（見 MODEL_BREAKER_SECONDS）。玩家請求（_locked）與排程（world_step）共用這一套。
    一定寫成 `with game.world.action_lock(), _model_guard(game)`：沒拿著鎖就用它直接丟 RuntimeError（審查 M1），
    順序寫反不會悄悄在鎖外歸零額度。用 RuntimeError 不用 assert：python -O 也照樣擋。"""
    if not game.world.db.writing():
        raise RuntimeError("_model_guard 要在拿到行動鎖之後用：with game.world.action_lock(), _model_guard(game)")
    game.reset_model_budget()  # 新的一次拿鎖：鎖內的模型呼叫重新有額度（一次拿鎖期間只容忍一次失敗，見 Game._quick_client）
    paused = _model_paused()
    if paused:
        game._model_budget.gave_up = True  # 斷路器開著：額度一開始就用完（直接碰 Game 的私有欄位，PM 同意只在這裡這樣做）
    try:
        yield
    finally:
        if not paused and game._model_budget.gave_up:  # 這一次拿鎖裡鎖內的模型呼叫失敗了（私有欄位，同上）
            _pause_model()


@contextlib.contextmanager
def _locked(game: Game):
    """拿行動鎖，並先重讀角色（見 _reload）。這支程式裡每一個要用 game.state 的地方都從這裡進鎖
    （act、look、prepare_dialogue），不另外呼叫 game.world.action_lock()：資料庫是唯一的真實來源，
    GAMES 裡的 Game 只是這一個動作的工作副本。FastAPI 的同步端點跑在執行緒池裡，同一個角色的兩個請求
    可能同時進來；行動鎖是 BEGIN IMMEDIATE，不同執行緒就一個一個來，重讀與動作不會交錯。
    鎖內的模型額度與斷路器見 _model_guard。
    這一次拿鎖裡觸發的江湖大事（S-09）：鎖內只寫固定的原文，放鎖之後才開背景執行緒請模型潤色（write_flavor）。"""
    _used(game)
    jobs: list[FlavorJob] = []
    try:
        with game.world.action_lock(), _model_guard(game):
            _reload(game)
            game.set_move_mode(MOVE_MODE.get())  # 這次請求選的走法（見 MOVE_MODE）：之後的選單與 choose() 都照它
            yield
            jobs = game.take_flavor_jobs()  # 動作丟例外就不拿：那一下整筆撤回，下一次拿鎖 reset_model_budget 會清掉
    finally:
        _used(game)
    if jobs and TALE_THREADS and game.client is not None:
        write_flavor(game, jobs)


def _refuse_while_paused(game: Game) -> None:
    """管理者暫停了賽季時鐘（線上架構 8.3「維護模式：擋住所有動作」）：玩家的動作一律回這一句。畫面照常可看——計時器的同步、
    看名冊、輿圖、戰報都不經過這裡。呼叫端要拿著行動鎖、已經同步過；丟出去時整筆交易撤回。"""
    if game.world.paused_at() is not None:
        raise GameError(f"{PAUSED_TEXT}。")


NOT_ON_MENU = "（此刻無法這麼做。）"  # Game.choose 對不在選單上的選項回的那一句（真人量表不算按了）


def _play_where(game: Game) -> tuple[str, int, int] | None:
    """真人量表（tianxia/playlog.py）記在哪裡：(帳號的鍵, 季數, 那一天)；假人不記（假人程式不經過伺服器，這裡多擋一次）。"""
    p = game.state.player
    if p.bot is not None:
        return None
    return name_key(p.name), p.season_number, game._pill_day()


def _play_seen(game: Game) -> None:
    """自己的請求進鎖、同步過之後：這一天上線了（真人量表）。在 act／act_look 的那一筆交易裡。
    也記下全服最後一次有真人來（LAST_HUMAN：省電模式沒人在線時，旁白改寫不叫模型）。"""
    global LAST_HUMAN
    LAST_HUMAN = time.time()
    where = _play_where(game)
    if where is not None:
        PlayLog(game.world.db).seen(*where)


def _play_did(game: Game, button: str, first: str | None = None) -> None:
    """一個動作做成了（沒丟例外、沒被擋）之後：記一次 button，first 給了就記第一次（真人量表）。
    動作那一把鎖已經放了：自己另開一筆小交易，只寫量表那兩張表，不碰角色與世界。"""
    where = _play_where(game)
    if where is None:
        return
    owner, season, day = where
    log = PlayLog(game.world.db)
    log.press(owner, season, day, button)
    if first is not None:
        log.first(owner, season, first, day, game.now)


def act(game: Game, action, *, paused_ok: bool = False) -> list[str] | None:
    """同步時間 → 執行動作 → 存檔。開一筆寫入交易（假人程式寫同一個資料庫），計時器、按鈕與假人就一個一個來。
    進鎖先從資料庫重讀角色（見 _reload）：動作丟例外時整筆撤回，下一個動作不會把失敗的改動存回去。
    回傳動作的訊息。動作之後一律存檔：同步寫進江湖紀錄的江湖大事，不能因為動作本身沒改東西就被下一次重讀丟掉。
    賽季時鐘暫停中，只有 paused_ok 的照做（計時器的同步、管理者的動作、畫面上的設定），其他回「賽季暫停中」（_refuse_while_paused）。"""
    with _locked(game):
        now = time.time()
        game.sync(now)
        game.mark_seen(now)  # 這是他自己的請求（玉璽碎片設計 5.3、5.5）
        _play_seen(game)
        if not paused_ok:
            _refuse_while_paused(game)
        msgs = action(game)
        open_characters().save(game.state)
        tales = _tales_waiting(game)
        crowd = _crowd_waiting(game)
        chat = _chatter_waiting(game)
        mail = _letter_waiting(game)
        review = _yuedan_waiting(game)
        essay = _xingshi_waiting(game)
    if tales:
        narrate_battle(game)
    if crowd:
        write_crowd(game)
    if chat:
        write_chatter(game, chat)
    if mail:
        write_letter(game)
    if review:
        write_yuedan(game)
    if essay:
        write_xingshi(game)
    return msgs


def _tales_waiting(game: Game) -> bool:
    """這一場有等著補劇情的放手一搏、模型叫得到、還沒有一條在寫（narrate_battle）。行動鎖內叫：回合可能在任何人的動作、
    假人程式、逾時的追趕裡結算，所以每一個動作與輪詢之後都看一眼。"""
    if not TALE_THREADS or game.client is None or TALE_RUNNING:
        return False
    return any(battle.tales for battle in game._tale_battles())  # 決戰與攻城戰（領地爭奪第二批）


def look(game: Game, view):
    """只讀的畫面（點名冊、切圖層、看戰報）：拿鎖、重讀角色，但不同步、不存檔。"""
    with _locked(game):
        return view(game)


def act_look(game: Game, action, view) -> tuple[list[str] | None, object]:
    """act 加 look 在同一把行動鎖裡做完：同步時間 → 動作 → 存檔 → 畫面。回傳 (動作的訊息, 畫面)。
    以前輪詢是 act(無事) 再 look(main_view)，各拿一次鎖、各重讀一次角色，每個在線的人每 10 秒就拿兩次（壓測 2026-10-06）。
    跟兩步的結果一樣：存檔在畫面之前，所以畫面建構時才做的事（決戰追趕、收場補的紀錄）跟 look 一樣不存、下一次同步再補；
    動作丟例外時整筆撤回、不看畫面（act 的規矩）。
    畫面丟例外時，同步與存檔照舊留著（兩步時 act 那一把鎖早就放了），畫面自己寫的撤回（兩步時 look 那一把鎖整筆撤回）：
    畫面建構不是唯讀，options() 會把全服決戰追趕到現在（標成收場、套結果）。所以畫面包在 savepoint 裡，丟例外時只撤回
    這一段的寫入；例外先記下、讓鎖正常放掉（COMMIT 同步與存檔），再原樣丟出去。不撤回的話，決戰已經標成收場而結果沒套上，
    下一次輪詢看到「早就收場了」就不再套，那場決戰的結果整個服永遠丟了。"""
    failure: Exception | None = None
    with _locked(game):
        now = time.time()
        game.sync(now)
        game.mark_seen(now)  # 這是他自己的請求（玉璽碎片設計 5.3、5.5）
        _play_seen(game)
        msgs = action(game)
        open_characters().save(game.state)
        try:
            with game.world.db.savepoint():
                shown = view(game)
        except Exception as exc:  # 見上：畫面自己的寫入已經撤回，先讓鎖放掉，再丟出去
            failure = exc
        tales = failure is None and _tales_waiting(game)
        crowd = failure is None and _crowd_waiting(game)
        chat = _chatter_waiting(game) if failure is None else None
        mail = failure is None and _letter_waiting(game)
        review = failure is None and _yuedan_waiting(game)
        essay = failure is None and _xingshi_waiting(game)
    if failure is not None:
        raise failure
    if tales:
        narrate_battle(game)
    if crowd:
        write_crowd(game)
    if chat:
        write_chatter(game, chat)
    if mail:
        write_letter(game)
    if review:
        write_yuedan(game)
    if essay:
        write_xingshi(game)
    return msgs, shown


def poll_main(game: Game) -> dict:
    """計時器（/api/main）與開頁、登入之後的第一畫面（_entry）：同步時間、存檔、回江湖畫面，一把鎖做完。
    賽季時鐘暫停中也照常做：動作只是同步（暫停中補算不推時鐘），不擋；畫面上選單只剩一顆灰的「賽季暫停中」。"""
    return act_look(game, lambda g: None, main_view)[1]


# 排程用的那一份沒有玩家的 Game（Game.for_world）。只有排程執行緒（start_scheduler，只從 main() 開、只開一條）用它，
# 請求的處理從不呼叫 world_step；在 world_step 裡、第一次用到時才建，建不起來就跟這一下的其他錯誤一樣由排程迴圈印出來、下一下再建
WORLD_GAME: Game | None = None


def world_step(clock: Callable[[], float] = time.time) -> list[str]:
    """伺服器排程的一下（線上架構設計第四節）：拿行動鎖（跟玩家請求同一把、等到拿到為止），推全服的事到現在
    （Game.world_tick）。鎖內的模型呼叫照玩家請求那一套額度與斷路器（_model_guard）。
    現在時間在拿到鎖之後才讀（clock()，跟 act() 一樣）：等鎖等得再久，這一下開的集結、回合的期限也不會因此變短。
    clock 是牆上的時鐘（time.time）：共用賽季的 season_last_real 與決戰的期限存的都是它，不能用 monotonic。
    出錯時交易整筆撤回、鎖放掉，記憶體裡那份做到一半的空殼也丟掉（下一下從資料庫重建，跟 _reload 同一個道理），
    例外丟給呼叫端（排程迴圈印出來、下一輪照跑）。回傳的訊息不要逐下印出來：裡面可能有參戰者的名號。"""
    global WORLD_GAME
    if WORLD_GAME is None:
        WORLD_GAME = Game.for_world(CONTENT, open_world())
    game = WORLD_GAME
    try:
        with game.world.action_lock(), _model_guard(game):
            return game.world_tick(clock())
    except BaseException:
        WORLD_GAME = None
        raise


SCHEDULER_STOP = threading.Event()  # 讓排程執行緒停下來（測試用；伺服器關掉時執行緒是 daemon，跟著結束）
SCHEDULER_THREAD: threading.Thread | None = None  # 正在跑的那一條排程執行緒（一個伺服器只開一條，見 start_scheduler）
_SCHEDULER_LOCK = threading.Lock()
SCHEDULER_REPEAT_SUMMARY_SECONDS = 600  # 同一個錯一直重複時，每幾秒印一行累計的次數（第一次照樣整段印，見 _StepFailures）


class _StepFailures:
    """排程那一下出錯的紀錄。只寫例外的類別（stdout 一行）與呼叫堆疊（stderr，程式碼的位置與那幾行原始碼），
    例外訊息一概不寫：常夾著名號（伺服器視窗不該看得出誰在打、誰是假人），跟 bot_runner.log_failure 同一個規矩（最終審查 I1）。
    同一個錯（同一個類別、在同一行丟出來）一直重複時，第一次整段印，之後只數次數：換了別的錯、或距離上一次印滿
    SCHEDULER_REPEAT_SUMMARY_SECONDS 秒，才印一行「又出錯 N 次」（最終審查 M2：每 10 秒一下，不收斂的話一天八千多段）。
    寫紀錄本身出錯（主控台的編碼寫不出某個字、主控台不見了）一律吞掉：記錄不能讓排程停下來。
    clock 只給節流用（預設 time.monotonic），跟世界時間無關。
    label 是印出來的那一行裡說的是誰（預設「排程」）；推送的看守（start_push）也用這一套，寫成「推送的看守」，規矩一樣。"""

    def __init__(self, clock: Callable[[], float], label: str = "排程"):
        self.clock = clock
        self.label = label
        self.key: tuple[str, str | None, int | None] | None = None  # 上一個整段印過的錯：（類別, 檔案, 行號）
        self.repeats = 0  # 它之後又出了幾次、還沒交代
        self.since = 0.0  # 上一次印（整段或摘要）的時刻

    def failed(self, exc: BaseException) -> None:
        with contextlib.suppress(Exception):
            frames = traceback.extract_tb(exc.__traceback__)
            top = frames[-1] if frames else None
            key = (type(exc).__name__, top.filename if top else None, top.lineno if top else None)
            if key == self.key:
                self.repeats += 1
                return
            self._summary()  # 換了別的錯：上一個錯還沒交代的次數先交代
            self.key, self.since = key, self.clock()
            print(f"{self.label}這一下出錯：{type(exc).__name__}", flush=True)
            sys.stderr.write("".join(traceback.format_tb(exc.__traceback__)))
            sys.stderr.flush()

    def tick(self) -> None:
        """每一下之後都叫（成功也叫）：同一個錯攢了次數、距離上一次印滿 SCHEDULER_REPEAT_SUMMARY_SECONDS 秒就印一行摘要。"""
        with contextlib.suppress(Exception):
            if self.repeats and self.clock() - self.since >= SCHEDULER_REPEAT_SUMMARY_SECONDS:
                self._summary()

    def _summary(self) -> None:
        if self.key is None or not self.repeats:
            return
        count, self.repeats, self.since = self.repeats, 0, self.clock()
        print(f"{self.label}這一下又出錯 {count} 次：{self.key[0]}（同一個地方，細節同上）", flush=True)


def run_scheduler(
    interval: float, stop: threading.Event, step=None, clock: Callable[[], float] = time.time,
    log_clock: Callable[[], float] = time.monotonic,
) -> None:
    """排程迴圈：每 interval 秒叫一次 step(clock)（預設是 world_step，它拿到行動鎖之後才讀 clock），直到 stop 被設起來。
    一下出錯就記下來（_StepFailures：只寫例外的類別與呼叫堆疊，同一個錯重複時只數次數），下一輪照跑：排程不能因為一次
    例外、也不能因為寫紀錄出錯就停掉，不然世界又變成等人點擊才動。
    每一下回傳的訊息不印：裡面可能有參戰者的名號，伺服器視窗不該看得出誰在打、誰是假人。
    step 預設寫成 None 再取 world_step：測試用 monkeypatch 換掉 server.world_step 時，執行緒拿到的是換過的那一個。
    log_clock 只給出錯紀錄的節流用；世界的時間一律是 clock（牆上時鐘）。"""
    step = step or world_step
    failures = _StepFailures(log_clock)
    while not stop.wait(interval):
        try:
            step(clock)
        except Exception as e:  # noqa: BLE001  任何錯都不能讓排程死掉
            failures.failed(e)
        failures.tick()


def scheduler_line(interval: float) -> str:
    if interval <= 0:
        return "排程：關（世界時間等有人連線才推）"
    return f"排程：每 {interval:g} 秒推一次全服的事（世界時間、時刻表、決戰逾時、季末）"


def start_scheduler(interval: float) -> threading.Thread | None:
    """開關打開（interval > 0）時開排程執行緒（daemon：伺服器關掉時跟著結束）；關著回 None。
    只有 main() 呼叫它（import 時不開），一個伺服器只開一條：已經有一條在跑就丟 RuntimeError（WORLD_GAME 只給一條執行緒用）。"""
    global SCHEDULER_THREAD
    if interval <= 0:
        return None
    with _SCHEDULER_LOCK:
        if SCHEDULER_THREAD is not None and SCHEDULER_THREAD.is_alive():
            raise RuntimeError("排程執行緒已經在跑了：一個伺服器只開一條")
        SCHEDULER_THREAD = threading.Thread(
            target=run_scheduler, args=(interval, SCHEDULER_STOP), daemon=True, name="world-scheduler",
        )
        SCHEDULER_THREAD.start()
        return SCHEDULER_THREAD


# ── 伺服器推送（線上架構設計 5.3；server_push.py）──
# 開關是 Config.push_events（預設關）：關著 HUB 是 None、/api/events 是 404、頁面照舊每 10 秒輪詢；main() 照設定建（start_push）。
HUB: server_push.PushHub | None = None
PUSH_STOP = threading.Event()  # 讓推送的看守停下來（測試用；伺服器關掉時看守是 daemon，跟著結束）
PUSH_THREAD: threading.Thread | None = None  # 正在跑的那一條看守執行緒（測試要等它真的結束）
HEARTBEAT_SECONDS = 15.0  # 這麼久沒有通知就送一個 ping，代理（Cloudflare 閒置約 100 秒）才不會切掉連線，頁面也才看得出連線還活著


def current_fingerprint() -> str:
    """看守用：現在大家都看得到的世界的指紋（server_push.world_fingerprint；唯讀的快照，不拿行動鎖，所以看守不跟玩家搶鎖）。
    全服狀態、天下大事傳聞的最大流水號、江湖史的則數在同一個快照裡讀（fingerprint_parts）：分開讀的話，中間有人寫就會讀到
    一半舊一半新的指紋、白白廣播兩次；傳聞與江湖史也不讀回每一列，讓資料庫數，所以隨著一季的列數長大也不會變慢。"""
    shared, rumor_id, chronicle_count = open_world().fingerprint_parts()
    battle = shared.active_battle
    definition = CONTENT.battles.get(battle.battle_id) if battle is not None else None
    progress = battle_instance.round_progress(battle, definition) if definition is not None and battle.phase == "active" else None
    sieges = [  # 攻城戰（領地爭奪第二批）：每一場同決戰那幾樣
        (siege, battle_instance.round_progress(siege, CONTENT.battles[siege.battle_id])
         if siege.phase == "active" and siege.battle_id in CONTENT.battles else None)
        for siege in shared.sieges
    ]
    return server_push.world_fingerprint(
        shared.season_number, shared.season_phase(), shared.season, battle,
        rumor_id=rumor_id, chronicle_count=chronicle_count, paused=shared.paused_at is not None, progress=progress,
        seal=shared.seal_duels, sieges=sieges,
    )


def push_line(config) -> str:
    if not config.push_events:
        return "推送：關（分頁每 10 秒輪詢）"
    return f"推送：開（SSE；世界每 {config.push_watch_seconds:g} 秒看一次，兩次通知至少隔 {config.push_world_min_seconds:g} 秒）"


def start_push(config) -> server_push.PushHub | None:
    """開關打開（push_events）時建 HUB、開看守執行緒（daemon：伺服器關掉時跟著結束）；關著什麼都不做、回 None（HUB 一直是 None）。
    只有 main() 呼叫它（import 時不開）。看守出錯照排程的規矩只記例外的類別、同一個錯只數次數（_StepFailures；
    例外的訊息常夾著名號，伺服器視窗不該看得出誰是假人，預檢 F5）。"""
    global HUB, PUSH_THREAD
    if not config.push_events:
        return None
    failures = _StepFailures(time.monotonic, "推送的看守")
    HUB = server_push.PushHub()
    PUSH_THREAD = threading.Thread(
        target=server_push.watch_world,
        args=(HUB, current_fingerprint, PUSH_STOP, config.push_watch_seconds, config.push_world_min_seconds),
        kwargs={"on_error": failures.failed, "on_round": failures.tick},
        daemon=True, name="push-watch",
    )
    PUSH_THREAD.start()
    return HUB


# ── 網頁推送（減法季整合設計第十章「回來的理由」，批 9；server_push.WebPush、tianxia/notices.py）──
# 開關是 Config.web_push.enabled（content/config.json 打開；測試內容關著）＋主機裝了 cryptography：關著 WEB_PUSH 是 None、
# 設定頁不畫「手機通知」、/api/push* 回 404。玩家在設定頁自己打開（預設關），訂閱記在資料庫旁邊的小檔（PushStore）。
# 看守（notice_round）每 watch_seconds 秒把開了通知的人看一遍：到了 09:00 先替他送今天的信（Game.morning_mail），再比五種事
# （notices.current）有沒有新的，新的才跳。哪幾件跳過了記在記憶體（NOTICE_SENT）：伺服器重開後第一輪只記下、不跳，
# 停機那段時間發生的事不補跳（畫面上照樣看得到）。
WEB_PUSH: server_push.WebPush | None = None
NOTICE_STOP = threading.Event()  # 讓通知的看守停下來（測試用）
NOTICE_THREAD: threading.Thread | None = None
NOTICE_SENT: dict[str, set[str]] = {}  # 帳號 → 上一輪看到的事（已跳過、或正在玩不必跳的）
MAIL_DONE: dict[str, int] = {}  # 帳號 → 已經替他送過信的送信日（letters.mail_day），同一天不再進鎖試
NOTICE_TITLE = "天下大勢"
PUSH_WELCOME = "手機通知開了：來信、約戰、決戰集結、被截殺、被〈天下形勢〉提到時，會在這裡告訴你。"  # 待 joy 潤
PUSH_TEST = "通知設定好了：這一台收得到。"  # 設定頁「傳一則測試通知」（待 joy 潤）
PUSH_NOT_HERE = "這台裝置還沒開手機通知：先勾「手機通知」。"  # 待 joy 潤
VAPID_FILE = ROOT / ".local" / "webpush_vapid.pem"  # 這台主機的 VAPID 金鑰：第一次開時產生；換了它，所有人要重開一次通知


def push_store_path() -> Path:
    """訂閱的小檔：遊戲資料庫旁邊、同名多「-push.sqlite」（TIANXIA_DB 換了檔，它跟著換）。"""
    db = default_path()
    return db.with_name(f"{db.stem}-push.sqlite")


def web_push_line(config) -> str:
    if not config.web_push.enabled:
        return "手機通知：關"
    if not server_push.AVAILABLE:
        return "手機通知：關（這台主機沒裝 cryptography：pip install -r requirements.txt）"
    return f"手機通知：開（每 {config.web_push.watch_seconds:g} 秒看一次開了通知的人；金鑰 {VAPID_FILE}）"


def start_web_push(config, post=None) -> server_push.WebPush | None:
    """開關開著、cryptography 在：建 WEB_PUSH、開看守執行緒（daemon）；不然什麼都不做、回 None。只有 main() 與測試呼叫。
    簽名的 sub 照 TIANXIA_PUBLIC_URL（固定網域），沒設就寫固定網域本身（推送服務只認 https 或 mailto）。"""
    global WEB_PUSH, NOTICE_THREAD
    if not config.web_push.enabled or not server_push.AVAILABLE:
        return None
    subject = os.environ.get("TIANXIA_PUBLIC_URL") or "https://tianxiadashi.com"
    WEB_PUSH = server_push.WebPush(server_push.PushStore(push_store_path()), server_push.Vapid(VAPID_FILE, subject), post=post)
    failures = _StepFailures(time.monotonic, "通知的看守")

    def loop() -> None:
        while not NOTICE_STOP.wait(config.web_push.watch_seconds):
            try:
                notice_round()
            except Exception as e:  # noqa: BLE001  看守不能因為一輪出錯就停
                failures.failed(e)
            failures.tick()

    NOTICE_THREAD = threading.Thread(target=loop, daemon=True, name="notice-watch")
    NOTICE_THREAD.start()
    return WEB_PUSH


def _notice_keys(game: Game, account_key: str, now: float) -> tuple[list, bool]:
    """行動鎖內：到了送信的時刻先替他送今天的信（送了就存角色；開著的分頁照常輪詢就看得到，不叫 HUB：只有動作的端點叫，
    見 _tell_tabs），回傳（五種事, 正在玩）。
    正在玩：quiet_seconds 之內同步過（分頁開著），畫面上已經看得到，不必再跳。"""
    day = letters.mail_day(game.content, game.state.world, now)
    if day is not None and MAIL_DONE.get(account_key) != day:
        if game.morning_mail(now):
            open_characters().save(game.state)
        MAIL_DONE[account_key] = day
    last = game.state.last_real
    busy = last is not None and now - last < game.content.config.web_push.quiet_seconds
    return current_notices(game.state, game.content, game.world.get_battle(), game.world.sortie_duels()), busy


def notice_round(clock: Callable[[], float] = time.time) -> int:
    """看守的一輪：開了通知的每一個帳號進一次鎖（_notice_keys），鎖外比上一輪、新的才跳（一人一輪最多 per_round 則，
    多的下一輪再跳）。第一次看到這個帳號只記下、不跳。回傳跳了幾則（測試用）。"""
    push = WEB_PUSH
    if push is None:
        return 0
    cfg = CONTENT.config.web_push
    sent_total = 0
    for account_key in push.store.accounts():
        account = account_store().get(account_key)
        if account is None or account.character is None:
            continue
        game = game_for(account.character)
        with _locked(game):
            now = clock()
            notes, busy = _notice_keys(game, account_key, now)
        keys = {n.key for n in notes}
        seen = NOTICE_SENT.get(account_key)
        if seen is None or busy:
            NOTICE_SENT[account_key] = keys
            continue
        off = push.store.kinds_off(account_key)  # 設定頁關掉的那幾種：不跳，也記成看過（之後打開不會補跳一串舊的）
        muted = {n.key for n in notes if n.key not in seen and n.kind in off}
        fresh = [n for n in notes if n.key not in seen and n.kind not in off]
        for n in fresh[:cfg.per_round]:
            sent_total += bool(push.send(account_key, NOTICE_TITLE, n.text, tag=n.kind, now=now))
        NOTICE_SENT[account_key] = (keys & seen) | muted | {n.key for n in fresh[:cfg.per_round]}
    return sent_total


# ── 事件旁白每週改寫（減法季整合設計第十章，批 10；tianxia/narration.py）──
# 全服一條背景執行緒（start_narration，main() 開）：每 rewrite_round_seconds 秒改寫一則，這一週的寫完就停到下一週。
# 不拿行動鎖（只讀季的快照、寫旁邊的小檔），模型呼叫排在真人後面（佇列開著時當假人排；關著時一輪只叫一次、短的），
# 省電模式開著而 ONLINE_SECONDS 之內沒有真人來過就不叫（不讓它把模型載回 VRAM）。這一季沒開改寫、休季、籌備中什麼都不做。
NARRATION: narration.NarrationStore | None = None
NARRATION_CLIENT = None  # 改寫用的 client（main() 照設定建；測試塞假的）
NARRATION_STOP = threading.Event()
NARRATION_THREAD: threading.Thread | None = None
NARRATION_FAILS: dict[tuple[int, int, str], int] = {}  # （季, 週, 事件）寫壞了幾次：rewrite_tries 次就這一週照原文，不再試
LAST_HUMAN = float("-inf")  # 最後一次有真人的請求（_play_seen）
ONLINE_SECONDS = 600.0  # 省電模式下「有人在線」的窗口（跟 scripts/warm_keeper.py 同一個數，不讀 presence_seconds）
NARRATION_KEY = "旁白改寫"  # 佇列裡的名號（不是任何角色：一人一件的規矩只管它自己）


def narration_store_path() -> Path:
    db = default_path()
    return db.with_name(f"{db.stem}-narration.sqlite")


def narration_line(config) -> str:
    if not config.jianfa.enabled or not config.jianfa.rewrite_narration:
        return "旁白改寫：關"
    return f"旁白改寫：開（每 {config.jianfa.rewrite_round_seconds:g} 秒一則，排在真人後面；寫在 {narration_store_path()}）"


def start_narration(config, client=None) -> threading.Thread | None:
    """減法季的開關與 rewrite_narration 開著：建 NARRATION、開背景執行緒（daemon）；不然什麼都不做。只有 main() 與測試呼叫。
    小檔不管開關都建起來（讀的一邊才有東西可查；開關關著的季 narration.text_of 本來就照原文）。"""
    global NARRATION, NARRATION_CLIENT, NARRATION_THREAD
    NARRATION = narration.NarrationStore(narration_store_path())
    if not config.jianfa.enabled or not config.jianfa.rewrite_narration:
        return None
    if client is None:
        try:
            client = OllamaClient.from_config(config)
        except Exception:  # noqa: BLE001  建不起 client：照原文，不擋伺服器
            return None
    NARRATION_CLIENT = client
    failures = _StepFailures(time.monotonic, "旁白改寫")

    def loop() -> None:
        while not NARRATION_STOP.wait(config.jianfa.rewrite_round_seconds):
            try:
                narration_round()
            except Exception as e:  # noqa: BLE001  一則出錯不能讓整條停下來
                failures.failed(e)
            failures.tick()

    NARRATION_THREAD = threading.Thread(target=loop, daemon=True, name="narration")
    NARRATION_THREAD.start()
    return NARRATION_THREAD


def narration_round(clock: Callable[[], float] = time.time) -> str | None:
    """改寫一則（背景執行緒的一輪；測試直接叫）：這一季開著改寫、這一週還有沒寫過的，就挑第一則請模型寫，寫成了存進小檔。
    回傳寫成的事件 id；沒做事或寫壞了是 None。呼叫端不能握著行動鎖。"""
    store, client = NARRATION, NARRATION_CLIENT
    if store is None or client is None:
        return None
    if power_save.on() and clock() - LAST_HUMAN > ONLINE_SECONDS:
        return None  # 省電模式、沒人在線：讓模型卸掉，等有人來再寫
    world = open_world()
    if world.season_phase() != "running":
        return None
    season = world.get_season()
    if not narration.on(CONTENT, season) or season.ended:
        return None
    number, week = world.get_season_number(), narration.period(CONTENT, season)
    cfg = CONTENT.config.jianfa
    done = store.done(number, week)
    todo = [e for e in narration.eligible(CONTENT)
            if e not in done and NARRATION_FAILS.get((number, week, e), 0) < cfg.rewrite_tries]
    if not todo:
        return None
    event = CONTENT.events[todo[0]]
    budget = cfg.rewrite_budget_seconds
    started = _monotonic()

    def ask() -> str | None:
        return narration.write(within_budget(client, budget - (_monotonic() - started)), CONTENT, event)

    if QUEUE is None:
        text = ask()
    else:
        try:
            text = QUEUE.run(NARRATION_KEY, ask, fallback=None, bot=True, wait=budget)
        except (Busy, QueueTimeout):
            return None  # 真人正在等模型：這一輪讓路，下一輪再來（不算寫壞）
    if not text:
        NARRATION_FAILS[(number, week, event.id)] = NARRATION_FAILS.get((number, week, event.id), 0) + 1
        return None
    store.put(number, week, event.id, text)
    return event.id


def _tell_tabs(game: Game, also: str = "") -> None:
    """動作做完、行動鎖已經放掉：叫這個角色開著的分頁刷新（推送開著時；其他分頁會去抓 /api/main，這一個分頁通常正忙著、
    會略過）。只有動作的端點叫它（api_choose、api_answer、api_do、api_menxia_do、api_travel），而且在動作成功之後：
    動作丟例外時交易整筆撤回、什麼都沒變，不通知。
    絕不能放進 act／look／act_look／poll_main／_entry：輪詢與開頁也走那些，通知一寫在輪詢的路上，同一個角色兩個看得到的
    分頁就會互相叫醒、永遠停不下來（一個分頁輪詢 → 通知另一個 → 它輪詢 → 通知回來……，預檢 B1）。
    一般的仗（prepare_fight 的 A 段）不經過 act，所以通知也不能寫在 act 裡（預檢 F1）。
    also：另一個名號——管理者動到別人的存檔（玩家個人劇情，PLAYER_ADMIN_ACTIONS），他開著的分頁也刷新。
    game.touched：這一個動作動到的別人（邀請、切磋，Game._other_side），通知完清掉。"""
    others, game.touched = set(game.touched), set()  # 這一個動作動到的別人（切磋、邀請）：他們的分頁也刷新
    if HUB is not None:
        HUB.notify(game.state.player.name.casefold())
        for name in {also.strip(), *others} - {""}:
            HUB.notify(name.casefold())


# ── 鎖外的模型呼叫（線上架構設計 5.2：LLM 佇列）──
# 五件事：對話生成、大場面判讀、開爐取名、隨口應對的評分與潤色，都是三段式的 B 段，一律走 model_call。
# 開關是 Config.llm_queue_slots（預設 0＝關）：關著 QUEUE 是 None，model_call 就是直接叫；main() 照設定建佇列。
QUEUE: LlmQueue | None = None


def make_queue(config) -> LlmQueue | None:
    return LlmQueue(config.llm_queue_slots, config.llm_queue_bot_cap) if config.llm_queue_slots > 0 else None


def queue_line(config) -> str:
    if config.llm_queue_slots <= 0:
        return "模型佇列：關（鎖外的模型呼叫照舊直接叫）"
    return (
        f"模型佇列：同時 {config.llm_queue_slots} 件，假人最多 {config.llm_queue_bot_cap} 件，"
        f"排超過 {config.llm_queue_wait_seconds:g} 秒就擋下來（請玩家再試一次）"
    )


# 同一個玩家已經有一件在等模型（另一個分頁、另一台裝置），這一件被擋下來時回的話（佇列開著才會；審查 M2）。
# 退路是一個結果：隨口應對的評分退路是 40（灌水的寫法本來該得 0）、首次開爐的退路是退路字表的名字（整季登記），
# 第二個分頁不能拿來挑結果，所以評分、開爐、大場面一律擋下來、什麼都不套用。三句都是草稿，待 joy 潤。
BUSY_FREE_TEXT = "上一句還在掂量，稍等。"  # 待 joy 潤
BUSY_FORGE = "上一爐還沒出爐。"  # 待 joy 潤
BUSY_FIGHT = "還在對峙，稍等。"  # 待 joy 潤
BUSY_SENSE = "心念還在凝，稍等。"  # 待 joy 潤（有所感畫完那一筆，同一個人另一條連線已經在等模型取名）
BUSY_DIALOGUE = "對方還沒答話，稍等。"  # 待 joy 潤（FB-077：同一個帳號另一條連線已經在等這個人的回話）
# 排超過 llm_queue_wait_seconds 秒還沒輪到的那一件（PM 2026-10-06）：跟重複的那一件一樣處理——退路是一個結果，沒被服務到的人沒道理
# 拿一個結果（評分 40、首次開爐用退路字表），所以給了上面那四句之一的呼叫點（評分、開爐、大場面、對話）也擋下來、什麼都不套用，
# 玩家再試一次就好；只是不能寫「上一件還在……」（排太久不是因為他自己有上一件），四個呼叫點共用這一句。草稿，待 joy 潤。
# 沒給 busy 句子的呼叫點（潤色：不插句子）排太久照舊拿 fallback，跟重複的那一件一樣。
# 對話（FB-077）：同一個帳號兩條連線同時按同一個人，第二件以前拿 cancelled（取消那一輪）先進鎖，把「無心多談，你只好先行告辭」
# 寫進紀錄、求見的選單也收掉，第一件的回話後來套不上；現在跟開爐、隨口應對、大場面一樣被擋下來、什麼都不動。
# 模型自己失敗（輪到了、叫了、答壞或逾時或連不上）不是這個：那是 job 裡的事，照舊走 job 自己的退路。
BUSY_QUEUE_TIMEOUT = "這會兒人多，沒輪到你，稍後再試一次。"  # 待 joy 潤


def model_call(
    game: Game, job, *, fallback, left: float | None = None, busy: str | None = None, max_wait: float | None = None,
):
    """行動鎖外叫模型一律走這裡：佇列開著就用這個角色的名號排隊（真人先、假人有上限〔滿了拿 fallback〕、一人一件、排太久被擋下來，
    見 llm_queue.LlmQueue），關著就直接叫。呼叫端不能握著行動鎖：排隊最久要等 llm_queue_wait_seconds 秒，握著鎖等就是全服一起等；
    在鎖裡被叫到直接丟 RuntimeError（跟 _model_guard 一樣，用 RuntimeError 不用 assert：python -O 也照樣擋），開關開著關著都一樣。
    鎖內的小呼叫走 Game._quick_client、不進佇列。佇列只認名號；是不是假人只決定排序與上限，不改任何玩家看得到的字。
    left 是呼叫端那一件的總預算還剩幾秒（有總預算的四種呼叫都給）：排隊最久只等 min(llm_queue_wait_seconds, left)，
    一個請求不會排過自己的總預算（審查 M1）；剩下 0 秒就是 0：位子正好空著照常進場（job 自己發現預算用完、不叫模型），
    要排的話馬上被擋下來（QueueTimeout，見下）。沒給（None）就只受 llm_queue_wait_seconds 管。
    max_wait 換掉 llm_queue_wait_seconds 那個上限（決戰的放手一搏：二十人同一回合各搏一次，排在後面的要等前面的評完，
    照 llm_queue_wait_seconds 的 20 秒會被擋掉一半，Joy 2026-10-13；仍受 left 夾）。
    同一個人已經有一件在排或在跑（佇列對這一件丟 Busy，審查 M2），或排超過等候的時間還沒輪到（佇列丟 QueueTimeout，PM 2026-10-06，
    跟 Busy 一樣處理）：給了 busy（一句話）就丟 GameError、不叫 job、不套用任何東西，呼叫端不能繼續往下走——重複的那一件丟 busy
    那句，排太久丟 BUSY_QUEUE_TIMEOUT；沒給 busy 就拿 fallback（潤色：不插句子，本來就無害）。
    佇列關著沒有這回事，照舊直接叫。假人滿了（bot_cap）是佇列直接給 fallback，不丟任何東西。"""
    if game.world.db.writing():
        raise RuntimeError("model_call 要在行動鎖外用：鎖內的小呼叫走 Game._quick_client，不排隊")
    queue = QUEUE
    if queue is None:
        return job()
    p = game.state.player
    wait = game.content.config.llm_queue_wait_seconds if max_wait is None else max_wait
    if left is not None:
        wait = max(0.0, min(wait, left))
    try:
        return queue.run(p.name.casefold(), job, fallback=fallback, bot=p.bot is not None, wait=wait)
    except QueueTimeout:  # 排超過等候的時間還沒輪到（PM 2026-10-06）：跟重複的那一件一樣是拒絕，只是換一句話——不是上一件還在
        if busy is None:
            return fallback
        raise GameError(BUSY_QUEUE_TIMEOUT) from None
    except Busy:
        if busy is None:
            return fallback
        raise GameError(busy) from None


def within_budget(client, left: float):
    """鎖外一趟模型呼叫要用的 client：原本那個的複本，逾時設成 min(原本的逾時, 剩下的秒數 ÷ 2)。chat_structured 一次最多送兩趟
    （第一趟加重問），所以整段不會超過剩下的秒數（chat_text 只送一趟，對它這是寬鬆的一半）；跟 naming.propose、
    fight_llm.judge 同一套分法。對話、隨口應對的評分與潤色都用它。剩下的不夠一趟
    （naming.MIN_POST_SECONDS）回 None＝不叫了；沒有 client（None）還是 None。原本那個 client 不動（同一個角色別的請求可能正在用它）。"""
    if client is None:
        return None
    per_post = naming.per_post_seconds(client, left)
    return None if per_post is None else ollama_client.capped(client, per_post)


def _open_request(game: Game, open_it: Callable[[], object]) -> tuple[float, object]:
    """三段式的 A 段（鎖內、很快）：記下開始的時刻（B 段的預算要扣掉等鎖與 A 段的時間）、拿鎖、同步時間、暫停中就擋
    （模型一次都不叫）、open_it() 開單、存檔（不然 C 段進鎖重讀就把同步的結果丟了）。回傳（開始的時刻, open_it 的結果）。
    對話、大場面、開爐取名、悟意境取名、隨口應對五條路都走它。"""
    started = _monotonic()
    with _locked(game):
        game.sync(time.time())
        _refuse_while_paused(game)  # 暫停中在 A 段就擋：模型一次都不叫
        request = open_it()
        open_characters().save(game.state)
    return started, request


def prepare_dialogue(game: Game, option_id: str, text: str | None = None) -> companion_agent.PreparedTurn | None:
    """對話選項在行動鎖外生成（企劃者 2026-10-03 核准的過渡做法，正解是線上架構第二階段的 LLM 佇列）。
    模型一輪要 9~10 秒，整段包在鎖裡的話全服玩家與假人程式都得跟著等。分三段：
      A（鎖內、很快）同步時間，問引擎這個選項現在會不會生成對話，會就拿到送模型的單子；同步的結果（共用賽季的推進
        已經寫進資料庫、江湖大事寫進這個角色的江湖紀錄）要存起來，不然 C 段進鎖重讀就把它丟了；
      B（鎖外、很慢）呼叫模型（model_call：佇列開著要排隊），失敗、太慢時單子裡的 turn 是 None；預算是
        Config.dialogue_budget_seconds 扣掉 A 段（含等鎖）與排隊花掉的時間，引擎不讀時鐘，所以時間在這裡量（見 within_budget）；
        佇列開著、同一個帳號的另一條連線已經在等這個人的回話（FB-077），或排超過等候的時間還沒輪到：跟開爐、隨口應對、大場面一樣
        被擋下來——丟 GameError（BUSY_DIALOGUE、BUSY_QUEUE_TIMEOUT）、不走 C 段、什麼都不動（不寫紀錄、求見的選單還開著、不扣體力），
        另一條連線的那一件照常套用。以前這種情況拿 cancelled 先進鎖，當成「生成不出對話」寫一行告辭、把選單收掉，之後那一件的回話
        重驗對不上、套用不了，兩邊都沒談成；只有假人滿了（bot_cap）佇列直接給 cancelled，照舊取消那一輪；
      C（鎖內、很快）由呼叫端把結果交給 Game.choose(prepared=...)，引擎進鎖後重新核對再套用。
    這裡做 A 與 B，不會生成對話的選項（包含 talk:leave）回傳 None，由呼叫端走一般的 act()。
    text 只有「自己說」（SAY_OPTION）用：玩家打的那一句（見 say）。"""
    started, request = _open_request(game, lambda: game.dialogue_request(option_id, text))
    if request is None:
        return None
    cancelled = companion_agent.PreparedTurn(request.option_id, request.companion_id, request.player_action, None)
    total = game.content.config.dialogue_budget_seconds

    def generate():
        client = within_budget(game.client, total - (_monotonic() - started))
        if client is None and game.client is not None:
            return cancelled  # 等鎖、排隊把整份預算用完了：不叫模型，這一輪取消（跟模型叫不動一樣）
        return companion_agent.prepare_turn(client, request)

    return model_call(game, generate, fallback=cancelled, left=total - (_monotonic() - started), busy=BUSY_DIALOGUE)


def say(game: Game, text: str, option: str = SAY_OPTION) -> list[str] | None:
    """跟人物對話時的「自己說」（企劃者 2026-10-08）：玩家打的那一句跟按選項走同一條三段式（prepare_dialogue）——
    A 鎖內驗這句話能不能送（還在對話裡、按得下去、1～Game.say_max() 字）並開單，B 鎖外請模型歸類那句話、寫回應與下一輪選項，
    C 鎖內 Game.choose(SAY_OPTION, prepared=…, text=…) 整個重驗再套用（好感度照模型挑的類別查表）。
    送不出去（不在對話裡、字數不對）丟 GameError，什麼都不動。"""
    if option not in TEXT_TALKS:  # NPC 智能 2.1：商量打法（talk:plan）、帶路的路上（parley:road）也走這一條
        option = SAY_OPTION
    prepared = prepare_dialogue(game, option, text)
    if prepared is None:
        raise GameError(f"寫一句 1～{game.say_max()} 字的話；交談已經結束的話，就不必再說了。")
    return act(game, lambda g: g.choose(option, prepared=prepared, text=text))


def may_generate_dialogue(option_id: str) -> bool:
    """這個選項按下去可能呼叫對話模型，要走鎖外生成（見 prepare_dialogue）：交友、對話的 talk:N、求見時指名的
    call:<人物>。告辭（talk:leave）與收起求見名單（call:back）永遠不會，不必多繞一趟備料的鎖。"""
    if option_id == "act:socialize":
        return True
    return option_id.startswith(("talk:", "call:")) and option_id not in ("talk:leave", "call:back")


def may_judge_fight(option_id: str) -> bool:
    """這個選項可能是大場面、要先在鎖外問模型（見 prepare_fight）：遊歷、挑戰大勢人物本人、事件選項。
    隨口應對（choice:free）只是叫出輸入框（真正送出走 /api/answer），不是仗。"""
    if option_id == FREE_TEXT_OPTION:
        return False
    return option_id == "act:train" or option_id.startswith(("act:challenge:", "choice:"))


def prepare_fight(game: Game, option_id: str) -> list[str] | fight_llm.PreparedFight:
    """大場面在行動鎖外問模型（武學與成長設計 8.3，跟 prepare_dialogue 同一套三段）：
      A（鎖內、很快）同步時間，問引擎這個選項是不是大場面（Game.fight_request）。**不是**（一般的仗、自己陣營的操練、
        按不下去、這個角色不叫模型）就在同一次拿鎖裡直接做完、存檔，回傳那個動作的訊息（list）——遊歷與事件選項天天在按，
        一般的仗不能每一下都多搶一次行動鎖（計畫三 G14）。是大場面就拿到單子、存檔（不然 C 段進鎖重讀就把同步的結果丟了）；
      B（鎖外、很慢）fight_llm.judge（model_call：佇列開著要排隊）：預算是 Config.big_fight_budget_seconds 扣掉 A 段（含等鎖）
        與排隊花掉的時間，引擎不讀時鐘，所以時間在這裡量，輪到了才算；回傳 PreparedFight（備料的單子加判讀），叫不動、
        太慢時判讀是 None——單子照樣帶著，等判讀的時候這個選項沒了（人被另一個分頁帶走），C 段才說得出是哪一仗沒打成；
        排太久沒輪到、或同一個人已經有一件（model_call 的 busy），不走 C 段：丟 GameError、這一仗不打（BUSY_QUEUE_TIMEOUT、BUSY_FIGHT）；
      C 由呼叫端交給 Game.choose(fight=...)，引擎進鎖後重驗再套用（判讀是 None 也照樣打，優勢 0；選項已經不在就不打，
        回一句 FIGHT_LEFT／FIGHT_CHANGED，見 api_choose）。
    鎖內任何一步都不叫模型；鎖外這一段不歸鎖內的模型上限與斷路器管（跟對話、開爐取名一樣）。"""
    def open_fight():  # 不是大場面就在同一次拿鎖裡直接做完
        request = game.fight_request(option_id)
        return request, (game.choose(option_id) if request is None else None)

    started, (request, done) = _open_request(game, open_fight)
    if request is None:
        return done
    config = game.content.config

    def ask():
        budget = max(0.0, config.big_fight_budget_seconds - (_monotonic() - started))
        return fight_llm.judge(game.client, request, config.big_fight_swing, budget)

    judgment = model_call(
        game, ask, fallback=None, left=config.big_fight_budget_seconds - (_monotonic() - started), busy=BUSY_FIGHT,
    )
    return fight_llm.PreparedFight(request=request, judgment=judgment)


def choose(game: Game, option_id: str, text: str | None = None) -> list[str] | None:
    """text 只有需要玩家打字的那幾顆用（神品意境「自己取一個名字」dunwu:own）：原樣交給引擎，它自己驗。"""
    if option_id == EPIPHANY_THINK:
        return epiphany_think(game)
    if may_generate_dialogue(option_id):
        prepared = prepare_dialogue(game, option_id)
        return act(game, lambda g: g.choose(option_id, prepared=prepared))
    if may_judge_fight(option_id):
        fight = prepare_fight(game, option_id)
        if isinstance(fight, list):
            return fight  # 不是大場面：A 段那一次拿鎖已經做完了
        return act(game, lambda g: g.choose(option_id, fight=fight))
    return act(game, lambda g: g.choose(option_id, text=text))


NO_NAME: tuple[str | None, str] = (None, "")  # 開爐的 B 段沒取到名字（或不必取）：C 段直接走退路字表、不在鎖裡叫模型


def prepare_forge(game: Game, art_id: str | None, insight_ids: list[str]) -> tuple[str | None, str]:
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
    started, request = _open_request(game, lambda: game.forge_request(art_id, insight_ids))
    if request is None:
        return NO_NAME
    total = game.content.config.naming_budget_seconds

    def name_it():
        budget = max(0.0, total - (_monotonic() - started))
        # 角色名號的查詢是唯讀的快照、不拿行動鎖（FB-069：模型取到角色的名號就再取一次；C 段進鎖還會再擋一次）
        return naming.generate(game.client, game.content, request, budget=budget, person=game.world.is_character_name)

    return model_call(game, name_it, fallback=NO_NAME, left=total - (_monotonic() - started), busy=BUSY_FORGE)


def prepare_peer(game: Game, name: str, action: str, params: dict) -> tuple[str | None, str] | None:
    """玩家卡上要先請模型的互動（social.CardAction.request；論武答應時的首創取名）：照開爐的三段式（prepare_forge），
    A 在鎖內問 Game.peer_request、B 在鎖外 naming.generate，回傳（名字, 說明）交給 C（peer_act 的 params["proposed"]）。
    這一種互動不需要模型是 None（不多拿一次鎖）；需要、但這一爐不必取名是 NO_NAME。"""
    handler = social.ACTIONS.get(action)
    if handler is None or handler.request is None:
        return None
    started, request = _open_request(game, lambda: game.peer_request(name, action, params))
    if request is None:
        return NO_NAME
    total = game.content.config.naming_budget_seconds

    def name_it():
        budget = max(0.0, total - (_monotonic() - started))
        return naming.generate(game.client, game.content, request, budget=budget, person=game.world.is_character_name)

    return model_call(game, name_it, fallback=NO_NAME, left=total - (_monotonic() - started), busy=BUSY_FORGE)


SCREEN_BUDGET_SECONDS = 12.0  # 審一句話（挑釁、名帖自題）最多等模型幾秒：叫不動就只看字表照送


def screen_text(game: Game, text: str, kind: str) -> str:
    """玩家寫給別人看的一句話在行動鎖外請模型審（speech.judge，三段式的 B 段）："ok"、"bad"，叫不動、沒輪到是空字串
    （C 段只看字表）。空的、字表就擋得下的不叫模型。"""
    if not text or game.client is None:
        return ""
    if speech.word_problem(text, game.content, kind, 200):
        return ""
    started = _monotonic()

    def judge():
        client = within_budget(game.client, SCREEN_BUDGET_SECONDS - (_monotonic() - started))
        return speech.judge(client, text, kind)

    return model_call(game, judge, fallback="", left=SCREEN_BUDGET_SECONDS)


def screen_peer(game: Game, name: str, action: str, params: dict) -> str:
    """玩家卡上帶一句話的互動（social.CardAction.screen；挑釁）：要審就審，不要審是空字串。只讀引擎，不拿鎖（那一句只是字）。"""
    handler = social.ACTIONS.get(action)
    if handler is None or handler.screen is None:
        return ""
    got = handler.screen(game, game, params)  # 只看 params（那一句），不讀對方；對方那一份 C 段才拿
    return "" if got is None else screen_text(game, got[0], got[1])


def forge(game: Game, art_id: str | None, insight_ids: list[str]) -> list[str] | None:
    """開爐：A、B 在 prepare_forge，C 進鎖交給 Game.forge。proposed 一定給（不必叫模型時是 NO_NAME），
    所以伺服器上的開爐永遠不會在鎖裡叫模型。同一爐連按兩下、重新整理再按、開兩個分頁：兩個請求可能都走完 A、B，
    C 段重驗時第二個會看見配方有了、東西已經在你身上，什麼都不收（企劃者 2026-10-05：不能重複扣）。
    模型佇列開著時，同一個人已經有一件在等模型（另一個分頁、另一台裝置），第二件在 B 段被擋下來：丟 GameError「上一爐還沒出爐。」
    （BUSY_FORGE），不走 C 段、什麼都不登記、什麼都不收（審查 M2、控制者裁示；以前它拿 NO_NAME 先進鎖，這個配方這一季就用退路
    字表的名字登記，第一件模型取的名字被丟掉）。不必叫模型的爐（配方已經有人合過）不經過佇列，兩個分頁照常都走得完。"""
    proposed = prepare_forge(game, art_id, insight_ids)
    return act(game, lambda g: g.forge(art_id, insight_ids, proposed=proposed))


EPIPHANY_THINK = f"{epiphany.OPTION}:{epiphany.THINK}"
EPIPHANY_OWN = f"{epiphany.OPTION}:{epiphany.OWN}"  # 自己取名：/api/choose 帶 text 送上來（web 的 own-name-form）
BUSY_EPIPHANY = "還在想名字，稍等。"


def epiphany_think(game: Game) -> list[str] | None:
    """特殊頓悟的「靜心思名」，跟開爐取名一樣分三段：
      A（鎖內、很快）同步時間，Game.epiphany_request 開單（只讀）；不在等著取名、已經想過了是 None，照一般的按鈕走（引擎回那一句）；
      B（鎖外、很慢）epiphany.propose_names 請模型一次取三個（model_call 排隊），預算是 Config.naming_budget_seconds 扣掉 A 段；
        取不到是空的；
      C（鎖內、很快）Game.epiphany_names 重驗還是同一個神品、名字再過一次過濾，不夠三個用字表補。"""
    started, request = _open_request(game, game.epiphany_request)
    if request is None:
        return act(game, lambda g: g.choose(EPIPHANY_THINK))
    total = game.content.config.naming_budget_seconds

    def name_it():
        budget = max(0.0, total - (_monotonic() - started))
        return epiphany.propose_names(game.client, game.content, request, budget=budget, person=game.world.is_character_name)

    names = model_call(game, name_it, fallback=[], left=total - (_monotonic() - started), busy=BUSY_EPIPHANY)
    return act(game, lambda g: g.epiphany_names(request, names))


SENSE_PNG_MAX = 300_000  # 畫布存的小 PNG（base64 字數）最多收這麼多；再大就不給模型看圖，只給文字特徵（畫布 256×256，實際約一兩萬字）


def sense_draw(game: Game, points, png: str = "") -> list[str] | None:
    """有所感畫完那一筆（悟意境設計 0.2、0.2a），跟開爐取名一樣分三段：
      A（鎖內、很快）同步時間，Game.sense_request 讀那一筆、開單（只讀）；讀不出來（只點了一下、格式不對）回那一句話；
      B（鎖外、很慢）要悟一個自己的新意境才叫模型：看圖取名，取不到再只給文字特徵（insight_llm.name，model_call 排隊）；
        預算是 Config.sense_budget_seconds 扣掉 A 段（含等鎖）與排隊花掉的時間；落回基本意境的不叫；
      C（鎖內、很快）Game.sense_draw 重驗還是同一次感悟、同一筆讀出同一個屬性才套用，名字再過一次過濾，取不到走退路字表。
    PNG 只轉交給模型，不存（存的是規則取樣過的點位，畫縮圖用）。"""
    image = png if isinstance(png, str) and len(png) <= SENSE_PNG_MAX else ""
    started, request = _open_request(game, lambda: game.sense_request(points, image))
    if isinstance(request, str):
        raise GameError(request)
    proposed = NO_NAME
    if request.needs_name:
        total = game.content.config.sense_budget_seconds

        def name_it():
            budget = max(0.0, total - (_monotonic() - started))
            got = insight_llm.name(
                game.client, game.content, request.facts, image=request.png, budget=budget,
                person=game.world.is_character_name,
            )
            return got[0], got[1]

        proposed = model_call(game, name_it, fallback=NO_NAME, left=total - (_monotonic() - started), busy=BUSY_SENSE)
    return act(game, lambda g: g.sense_draw(request, proposed))


def answer_event(game: Game, text: str) -> list[str] | None:
    """事件的隨口應對（探索的多人與 LLM 玩法 §8.1），跟 prepare_dialogue 一樣分三段：
      A（鎖內、很快）同步時間，問引擎這句話現在能不能送；能就拿到單子（事件 id＋這句話），同步的結果照樣存起來；
      B（鎖外、很慢）請模型評這個做法的成功率，評完再另外很短地判一次善惡（FB-223，event_llm.judge_event_gamble；兩次在同一件
        model_call 裡，佇列開著要排隊），模型失敗、太慢一律 40、善惡當「中」（善惡那一次失敗只是「中」，成功率照用）；排太久沒輪到被擋下來
        （BUSY_QUEUE_TIMEOUT，PM 2026-10-06，跟同一個人的第二件一樣）：丟 GameError、不擲骰、不套用任何東西，不是 40；預算是
        Config.free_text_budget_seconds 扣掉 A 段（含等鎖）與排隊花掉的時間（見 within_budget）；
      C（鎖內、很快）Game.answer_event 重驗還停在同一則事件、同一句話，才擲骰套用（對不上就不套用）；
      D、E 擲骰之後在鎖外請模型潤色一兩句（model_call：同一個人這時沒有別件在排，照常再排一次），再進鎖插回那一則江湖紀錄
        （Game.add_gamble_narration）。潤色跟評分共用同一份 free_text_budget_seconds（控制者 2026-10-06）：從 A 段算起，
        扣掉評分、等鎖與排隊花掉的，剩下的給潤色（同一個 within_budget）；不夠一趟就不叫、不插句子，跟模型叫不動時一樣。
        整個請求因此在 free_text_budget_seconds 加兩次進鎖之內結束，不會超過 trycloudflare 約 100 秒的切斷。
    減法季的分岔（批 4）：A 段的單子帶了可能的走向（request.outcomes，分岔開著、這則事件寫了後果）時，B 段改請模型把這句話歸到其中一種
    （event_llm.judge_outcome：歸到最後一種才另外判善惡），C 段多交那一種的 id；D／E 照舊潤色，結果文字就是那一種後果的那一句。"""
    started, request = _open_request(game, lambda: game.free_text_request(text))
    if request is None:
        raise GameError(f"寫一句 1～{FREE_TEXT_MAX} 字的做法；眼前的事已經過去的話，就不必再寫了。")
    event = CONTENT.events[request.event_id]
    total = game.content.config.free_text_budget_seconds
    if request.outcomes:  # 減法季的分岔（批 4）：B 段歸類、評分，歸到最後一種才另外判善惡（善惡那一次用歸類剩下的預算再切一份）
        branches = event.free_text.outcomes
        fallback = event_llm.OutcomeVerdict(branches[-1].id, event_llm.DEFAULT_FREE_TEXT_SUCCESS_RATE)

        def score():
            client = within_budget(game.client, total - (_monotonic() - started))
            if client is None and game.client is not None:
                return fallback  # 等鎖、排隊把整份預算用完了：不叫模型，最後一種、保底值、善惡當「中」
            return event_llm.judge_outcome(
                client, event, branches, request.text, moral_client=lambda: within_budget(game.client, total - (_monotonic() - started)),
            )

        verdict = model_call(game, score, fallback=fallback, left=total - (_monotonic() - started), busy=BUSY_FREE_TEXT)
        msgs = act(game, lambda g: g.answer_event(request, verdict.rate, verdict.moral, verdict.outcome))
    else:
        fallback = event_llm.EventVerdict(event_llm.DEFAULT_FREE_TEXT_SUCCESS_RATE)

        def score():
            client = within_budget(game.client, total - (_monotonic() - started))
            if client is None and game.client is not None:
                return fallback  # 等鎖、排隊把整份預算用完了：不叫模型，保底值（善惡當「中」）
            # 評分之後另外很短地判善惡（FB-223）：用評分剩下來的預算再切一份；不夠一趟就不叫、當「中」，成功率照用
            return event_llm.judge_event_gamble(
                client, event, request.text, moral_client=lambda: within_budget(game.client, total - (_monotonic() - started)),
            )

        verdict = model_call(game, score, fallback=fallback, left=total - (_monotonic() - started), busy=BUSY_FREE_TEXT)
        msgs = act(game, lambda g: g.answer_event(request, verdict.rate, verdict.moral))  # 善惡在 C 段再驗一次（FB-223）
    outcome = game.last_gamble
    if outcome is not None:  # D（鎖外）擲骰之後請模型潤色一兩句，E（鎖內）插回那一則紀錄；失敗、預算用完就只留結果文字
        def narrate():  # 結果文字是 C 段實際套的那一句（分岔開著時是走的那一種後果的那一句）
            client = within_budget(game.client, total - (_monotonic() - started))  # 評分剩下來的預算，不是重新算一份
            if client is None and game.client is not None:
                return None  # 評分、等鎖、排隊把整份預算用完了：不叫模型，不插句子
            return event_llm.narrate_event_gamble(
                client, event, outcome.text, outcome.success, outcome.effect_text, evil=outcome.evil,
            )

        narration = model_call(game, narrate, fallback=None, left=total - (_monotonic() - started))
        if narration:
            act(game, lambda g: g.add_gamble_narration(outcome, narration), paused_ok=True)  # 擲骰已經做完了，只是插回一兩句
    return msgs


def battle_text(game: Game, text: str) -> list[str]:
    """決戰的放手一搏，跟 answer_event 一樣分三段（試玩回饋 2026-10-08：以前成功率在行動鎖裡評，最多等 in_lock_model_timeout 秒，
    全服所有人的動作都跟著等）：
      A（鎖內、很快）同步時間，問引擎這句話現在送不送得出去（Game.battle_text_request）；不行就回那一句、模型一次都不叫；
      B（鎖外、很慢）請模型評成功率（model_call：佇列開著要排隊），預算是 Config.free_text_budget_seconds 扣掉 A 段與排隊花掉的，
        模型失敗、太慢一律保底值；同一個人上一句還在評、或排太久沒輪到，照隨口應對擋下來、什麼都不送；
      C（鎖內、很快）Game.submit_battle_custom_action 重驗還送得出去，才帶著評好的分送出（可能湊滿這一回合而結算）。"""
    started, request = _open_request(game, lambda: game.battle_text_request(text))
    if isinstance(request, list):
        return request
    act_ = CONTENT.battles[request.battle_id].acts[request.act_index]
    total = game.content.config.free_text_budget_seconds

    fallback = battle_instance.DEFAULT_FREE_TEXT_SUCCESS_RATE

    def score():
        client = within_budget(game.client, total - (_monotonic() - started))
        if client is None and game.client is not None:
            return fallback  # 等鎖、排隊把整份預算用完了：不叫模型，保底值、固定句
        # 只評成功率（Joy 2026-10-13：二十人同一回合各搏一次也要每一個都評到）；劇情等回合結算後 narrate_battle 一整批寫
        return battle_instance.score_gamble(
            client, act_, request.faction_name, request.text, request.name, target=request.target, sex=request.sex,
        )

    left = total - (_monotonic() - started)
    rate = model_call(game, score, fallback=fallback, left=left, busy=BUSY_FREE_TEXT, max_wait=left)
    return act(game, lambda g: g.submit_battle_custom_action(request.text, rate))


# 決戰放手一搏的劇情（Joy 2026-10-13「應該要做到能承受」）：評分只回成功率，劇情等回合結算後一整回合批給模型寫一次。
# 全服同時只有一條在寫（TALE_RUNNING）；佇列開著時排在真人的評分後面（當成假人排，名號是 TALE_OWNER，不是任何一個角色）。
TALE_LOCK = threading.Lock()
TALE_RUNNING = False
TALE_OWNER = "§說書"
TALE_THREADS = False  # main() 打開：伺服器真的在跑才開背景執行緒寫劇情（測試直接叫 narrate_once，不留執行緒在背景碰資料庫）


def narrate_battle(game: Game) -> bool:
    """這一場有等著補劇情的放手一搏、而且還沒有一條在寫：開一個背景執行緒寫最早那一回合的一批。開了回 True。
    A 鎖內開單（Game.battle_tale_request）→ B 鎖外一整批請模型寫（battle_instance.write_tales，預算 battle_tale_budget_seconds）
    → C 鎖內重驗同一場才補（Game.apply_battle_tales；寫不出來的照固定句、不重寫）。呼叫端不能握著行動鎖。"""
    global TALE_RUNNING
    with TALE_LOCK:
        if TALE_RUNNING:
            return False
        TALE_RUNNING = True

    def tale_job() -> None:
        global TALE_RUNNING
        try:
            while narrate_once(game) is not None:  # 一批寫完還有（下一回合也結算了）就接著寫
                pass
        except Exception:  # noqa: BLE001 — 背景執行緒：印出來就好，那幾搏照固定句
            traceback.print_exc()
        finally:
            with TALE_LOCK:
                TALE_RUNNING = False

    threading.Thread(target=tale_job, name="battle-tales", daemon=True).start()
    return True


def narrate_once(game: Game) -> int | None:
    """寫一批（narrate_battle 的一圈）：沒有等著補的回 None，寫了回補上幾句。呼叫端不能握著行動鎖。"""
    with _locked(game):
        request = game.battle_tale_request()
    if request is None:
        return None
    definition = CONTENT.battles.get(request.battle_id) or game.content.battles.get(request.battle_id)
    act_ = definition.acts[request.act_index]
    budget = game.content.config.battle_tale_budget_seconds
    started = _monotonic()

    def ask() -> dict[str, str]:
        client = within_budget(game.client, budget - (_monotonic() - started))
        sides = [f.name for f in definition.factions]  # 兩軍的名字：失手那一句不准寫敵方受損（守門用）
        return battle_instance.write_tales(client, act_, request.items, sides=sides)

    if QUEUE is None:
        stories = ask()
    else:
        try:  # 排在真人的評分後面（當成假人排）；排不到就照固定句
            stories = QUEUE.run(TALE_OWNER, ask, fallback={}, bot=True, wait=min(budget, 120))
        except Busy:
            stories = {}
    with _locked(game):  # 補上了，等著補的單子就少了：推送的指紋跟著變，開著的分頁會更新
        return game.apply_battle_tales(request, stories)


FLAVOR_OWNER = "§大事"  # 江湖大事潤色排隊用的名號（當成假人排、排在真人後面；不是任何一個角色）
FLAVOR_BUDGET_SECONDS = 30.0  # 一件江湖大事潤色的總預算（鎖外；晚幾秒換上是可以的）


def write_flavor(game: Game, jobs: list[FlavorJob]) -> bool:
    """江湖大事的潤色（S-09）：開一個背景執行緒。A 鎖內觸發時記單子（world._fire → Game.take_flavor_jobs，固定的原文已經寫進紀錄）
    → B 鎖外請模型（flavor.polish_world_event，預算 FLAVOR_BUDGET_SECONDS；排隊時當假人排）→ C 鎖內驗過才存進全服快取、
    把這個人的那一則換掉（Game.apply_flavor；寫不出來就留著固定的原文）。呼叫端不能握著行動鎖。"""

    def job() -> None:
        for one in jobs:
            try:
                flavor_once(game, one)
            except Exception:  # noqa: BLE001 — 背景執行緒：印出來就好，留著固定的原文
                traceback.print_exc()

    threading.Thread(target=job, name="event-flavor", daemon=True).start()
    return True


def flavor_once(game: Game, job: FlavorJob) -> bool:
    """潤色一件（write_flavor 的那一圈；測試直接叫）：換上了回 True。呼叫端不能握著行動鎖。
    全服快取裡已經有合格的句子（別人先潤色好）就直接套、不叫模型。"""
    with _locked(game):
        done = game.apply_flavor(job, "")
        if done:
            open_characters().save(game.state)
    if done:
        return True
    started = _monotonic()

    def ask() -> str:
        return flavor.polish_world_event(within_budget(game.client, FLAVOR_BUDGET_SECONDS - (_monotonic() - started)), job.text)

    if QUEUE is None:
        text = ask()
    else:
        try:
            text = QUEUE.run(FLAVOR_OWNER, ask, fallback="", bot=True, wait=FLAVOR_BUDGET_SECONDS)
        except (Busy, QueueTimeout):
            text = ""
    if not text:
        return False
    with _locked(game):
        done = game.apply_flavor(job, text)
        open_characters().save(game.state)
    return done


LETTER_RUNNING: set[str] = set()  # 正在背景重寫書信的角色（一人一條；名號）


def _letter_waiting(game: Game) -> bool:
    """有一封信等著模型照他的口氣重寫、模型叫得到、這個人還沒有一條在寫（write_letter）。行動鎖內叫。"""
    if not TALE_THREADS or game.client is None or game.state.player.name in LETTER_RUNNING:
        return False
    return game.letter_request() is not None


def write_letter(game: Game) -> bool:
    """書信（大勢人物擴充第二批，letters.py）：開一個背景執行緒重寫。A 鎖內拿單子（Game.letter_request）→ B 鎖外請模型寫
    （letters.write，預算 Config.figure_life.letter_write_budget_seconds；排隊時當假人排、排在真人後面）→ C 鎖內重驗同一封才換
    （Game.apply_letter；寫不出來照固定句）。開了回 True。呼叫端不能握著行動鎖。"""
    name = game.state.player.name
    with TALE_LOCK:
        if name in LETTER_RUNNING:
            return False
        LETTER_RUNNING.add(name)

    def job() -> None:
        try:
            letter_once(game)
        except Exception:  # noqa: BLE001 — 背景執行緒：印出來就好，信照固定句
            traceback.print_exc()
        finally:
            with TALE_LOCK:
                LETTER_RUNNING.discard(name)

    threading.Thread(target=job, name="letter", daemon=True).start()
    return True


def letter_once(game: Game) -> bool:
    """重寫一封（write_letter 的那一圈；測試直接叫）：換了回 True。呼叫端不能握著行動鎖。"""
    with _locked(game):
        note = game.letter_request()
    if note is None:
        return False
    budget = game.content.config.figure_life.letter_write_budget_seconds
    started = _monotonic()

    def ask() -> str:
        return letters.write(within_budget(game.client, budget - (_monotonic() - started)), note)

    if QUEUE is None:
        text = ask()
    else:
        try:
            text = QUEUE.run(game.state.player.name, ask, fallback="", bot=True, wait=budget)
        except (Busy, QueueTimeout):
            text = ""
    with _locked(game):
        done = game.apply_letter(note, text)
        open_characters().save(game.state)
    return done


YUEDAN_RUNNING: set[str] = set()  # 月旦評正在背景寫（全服一條：有東西就是有一條在寫）


def _yuedan_waiting(game: Game) -> bool:
    """這一週的月旦評等著模型寫評語、模型叫得到、還沒有一條在寫（write_yuedan）。行動鎖內叫。"""
    if not TALE_THREADS or game.client is None or YUEDAN_RUNNING:
        return False
    return game.yuedan_request() is not None


def write_yuedan(game: Game) -> bool:
    """月旦評（大勢人物擴充第三批，yuedan.py）：開一個背景執行緒寫評語。A 鎖內拿單子（Game.yuedan_request）→ B 鎖外請模型寫
    （yuedan.write，預算 Config.figure_life.yuedan_budget_seconds；排隊時當假人排）→ C 鎖內重驗同一批才換上並發出去
    （Game.apply_yuedan；寫不出來照固定句發）。開了回 True。呼叫端不能握著行動鎖。"""
    with TALE_LOCK:
        if YUEDAN_RUNNING:
            return False
        YUEDAN_RUNNING.add("yuedan")

    def job() -> None:
        try:
            yuedan_once(game)
        except Exception:  # noqa: BLE001 — 背景執行緒：印出來就好，評語照固定句（等太久由季的事發）
            traceback.print_exc()
        finally:
            with TALE_LOCK:
                YUEDAN_RUNNING.clear()

    threading.Thread(target=job, name="yuedan", daemon=True).start()
    return True


def yuedan_once(game: Game) -> bool:
    """寫一批（write_yuedan 的那一圈；測試直接叫）：發了回 True。呼叫端不能握著行動鎖。"""
    with _locked(game):
        note = game.yuedan_request()
    if note is None:
        return False
    budget = game.content.config.figure_life.yuedan_budget_seconds
    started = _monotonic()

    def ask() -> dict:
        return yuedan.write(within_budget(game.client, budget - (_monotonic() - started)), note)

    if QUEUE is None:
        lines = ask()
    else:
        try:
            lines = QUEUE.run(game.state.player.name, ask, fallback={}, bot=True, wait=budget)
        except (Busy, QueueTimeout):
            lines = {}
    with _locked(game):
        return game.apply_yuedan(note, lines)


# 〈天下形勢〉（領地爭奪第三批 A；tianxia/xingshi.py）：每天 22:00 換天那一刻開一張單，這裡在背景請模型照事實寫一篇。
# 全服同時只有一條在寫（XINGSHI_RUNNING）；佇列開著時當成假人排在真人後面（名號是 XINGSHI_OWNER，不是任何一個角色）。
XINGSHI_RUNNING: set[str] = set()
XINGSHI_OWNER = "§史官"
XINGSHI_SKIPPED = object()  # 佇列沒讓這一趟跑（假人的名額被佔、排不到）：跟「模型寫不出來」分開——前者單子放回去下一輪再試


def _xingshi_waiting(game: Game) -> bool:
    """有一張〈天下形勢〉的單等著模型寫、模型叫得到、還沒有一條在寫（write_xingshi）。行動鎖內叫。只有 main() 打開 TALE_THREADS 的正式伺服器
    才開背景執行緒（測試直接叫 xingshi_once）；假人程式的 Game 沒有 client，不叫模型。"""
    if not TALE_THREADS or game.client is None or XINGSHI_RUNNING:
        return False
    return game.xingshi_waiting()


def write_xingshi(game: Game) -> bool:
    """開一個背景執行緒寫〈天下形勢〉。A 鎖內拿單子（Game.xingshi_request，記 taken）→ B 鎖外請模型寫（xingshi.write，預算
    Config.xingshi.budget_seconds；排隊時當假人排）→ C 鎖內重驗同一張單才收（Game.settle_xingshi；寫不出來照固定段）。開了回 True。
    呼叫端不能握著行動鎖。"""
    with TALE_LOCK:
        if XINGSHI_RUNNING:
            return False
        XINGSHI_RUNNING.add("xingshi")

    def job() -> None:
        try:
            xingshi_once(game)
        except Exception:  # noqa: BLE001 — 背景執行緒：印出來就好，那一篇過了 grace_seconds 照固定段收
            traceback.print_exc()
        finally:
            with TALE_LOCK:
                XINGSHI_RUNNING.clear()

    threading.Thread(target=job, name="xingshi", daemon=True).start()
    return True


def xingshi_once(game: Game) -> bool:
    """寫一篇（write_xingshi 的那一圈；測試直接叫）：收了回 True。呼叫端不能握著行動鎖。
    佇列沒讓這一趟跑（假人的名額被佔、排不到）：不照固定段收，單子放回去（Game.release_xingshi），隔 retry_seconds 下一輪再試；
    寬限（grace_seconds）到了還沒寫成，由 Game._xingshi_grace 照固定段收（PM，第三批 A 回報之後）。模型叫了卻寫不出來照舊馬上照固定段。"""
    with _locked(game):
        request = game.xingshi_request()
    if request is None:
        return False
    budget = game.content.config.xingshi.budget_seconds
    started = _monotonic()

    def ask() -> str | None:
        return xingshi.write(within_budget(game.client, budget - (_monotonic() - started)), request)

    if QUEUE is None:
        essay = ask()
    else:
        try:  # 排在真人的評分後面（當成假人排）
            essay = QUEUE.run(XINGSHI_OWNER, ask, fallback=XINGSHI_SKIPPED, bot=True, wait=min(budget, 120))
        except (Busy, QueueTimeout):
            essay = XINGSHI_SKIPPED
    with _locked(game):  # 收下那一刻寫天下大事：推送的指紋跟著變，開著的分頁會更新
        if essay is XINGSHI_SKIPPED:
            game.release_xingshi(request)
            return False
        return game.settle_xingshi(request, essay)


def feast_text(game: Game, text: str) -> list[str]:
    """自己寫的敬酒詞（宴客，大勢人物擴充第三批），三段：A Game.feast_text_request（只讀）→ B 鎖外請模型評一個分數
    （feasts.score，預算 Config.figure_life.feast_score_budget_seconds；評不到照 feasts.DEFAULT_SCORE）→ C Game.feast_toast
    重驗同一場、同一句才記。"""
    started, request = _open_request(game, lambda: game.feast_text_request(text))
    if isinstance(request, list):
        return request
    total = game.content.config.figure_life.feast_score_budget_seconds

    def ask() -> int:
        return feasts.score(within_budget(game.client, total - (_monotonic() - started)), request)

    rate = model_call(game, ask, fallback=feasts.DEFAULT_SCORE, left=total - (_monotonic() - started), busy=BUSY_FREE_TEXT)
    return act(game, lambda g: g.feast_toast(request.text, rate, request))


def gather_text(game: Game, text: str) -> list[str]:
    """找素材的「自己說」（第 32 項），三段同 feast_text：A Game.gather_text_request（只讀）→ B 鎖外請模型評成算、挑屬性
    （gather_llm.score，預算同隨口應對 free_text_budget_seconds；評不到 40、屬性照第一條分支）→ C Game.gather_say 重驗同一個地點、
    同一次探索、同一句才扣體力擲骰。排隊被擋丟 GameError（BUSY_FREE_TEXT、BUSY_QUEUE_TIMEOUT），不扣體力。"""
    started, request = _open_request(game, lambda: game.gather_text_request(text))
    if isinstance(request, list):
        return request
    total = game.content.config.free_text_budget_seconds

    def ask() -> tuple[int, str | None]:
        return gather_llm.score(within_budget(game.client, total - (_monotonic() - started)), request)

    rate, attribute = model_call(game, ask, fallback=(gather_llm.DEFAULT_RATE, None), left=total - (_monotonic() - started),
                                 busy=BUSY_FREE_TEXT)
    return act(game, lambda g: g.gather_say(request, rate, attribute))


def persuade_text(game: Game, errand_id: str, text: str) -> list[str]:
    """勸降（減法季批 6，整合設計 5.9），三段同 gather_text：A Game.persuade_request（只讀：那一件還在辦、人在那裡、字是 1～20 字）→
    B 鎖外請模型評那一句（event_llm.rate_persuasion，預算同隨口應對 free_text_budget_seconds）→ C Game.persuade 重驗同一件、同一句才
    扣體力擲骰。模型叫不動（評不到、逾時、沒有模型）是 None：照批 4 的慣例落到最保守的結果，什麼都不發生、那一件照舊在。
    排隊被擋丟 GameError（BUSY_FREE_TEXT、BUSY_QUEUE_TIMEOUT），不扣體力。"""
    started, request = _open_request(game, lambda: game.persuade_request(errand_id, text))
    if isinstance(request, list):
        return request
    total = game.content.config.free_text_budget_seconds

    def ask() -> int | None:
        return event_llm.rate_persuasion(within_budget(game.client, total - (_monotonic() - started)), request)

    rate = model_call(game, ask, fallback=None, left=total - (_monotonic() - started), busy=BUSY_FREE_TEXT)
    return act(game, lambda g: g.persuade(request, rate))


CROWD_RUNNING: set[str] = set()  # 正在背景重寫場邊那一句的角色（一人一條；名號鍵）


def _crowd_waiting(game: Game) -> bool:
    """擂台有一句場邊事件等著模型重寫、模型叫得到、這個人還沒有一條在寫（write_crowd）。行動鎖內叫。"""
    if not TALE_THREADS or game.client is None or game.state.player.arena_crowd_note is None:
        return False
    return game.state.player.name not in CROWD_RUNNING


def write_crowd(game: Game) -> bool:
    """擂台場邊那一句（arena_crowd）：開一個背景執行緒重寫。A 鎖內拿單子（Game.arena_crowd_request）→ B 鎖外請模型寫
    （arena_crowd.write_line，預算 Config.arena.crowd.write_budget_seconds；排隊時當假人排）→ C 鎖內重驗同一張單子才換
    （Game.apply_arena_crowd；寫不出來照固定句）。開了回 True。呼叫端不能握著行動鎖。"""
    name = game.state.player.name
    with TALE_LOCK:
        if name in CROWD_RUNNING:
            return False
        CROWD_RUNNING.add(name)

    def job() -> None:
        try:
            crowd_once(game)
        except Exception:  # noqa: BLE001 — 背景執行緒：印出來就好，那一句照固定句
            traceback.print_exc()
        finally:
            with TALE_LOCK:
                CROWD_RUNNING.discard(name)

    threading.Thread(target=job, name="arena-crowd", daemon=True).start()
    return True


def crowd_once(game: Game) -> bool:
    """重寫一句（write_crowd 的那一圈；測試直接叫）：換了回 True。呼叫端不能握著行動鎖。"""
    with _locked(game):
        note = game.arena_crowd_request()
    if note is None:
        return False
    budget = game.content.config.arena.crowd.write_budget_seconds
    started = _monotonic()

    def ask() -> str:
        return arena_crowd.write_line(within_budget(game.client, budget - (_monotonic() - started)), note)

    if QUEUE is None:
        text = ask()
    else:
        try:
            text = QUEUE.run(game.state.player.name, ask, fallback="", bot=True, wait=budget)
        except (Busy, QueueTimeout):
            text = ""
    with _locked(game):
        done = game.apply_arena_crowd(note, text)
        open_characters().save(game.state)
    return done


CHATTER_RUNNING: set[str] = set()  # 正在背景寫鄰桌閒談的酒肆（一間一條；地點 id）


def _chatter_waiting(game: Game) -> str | None:
    """這個人開著的酒肆該換一段閒談、模型叫得到、這一間還沒有一條在寫（write_chatter）：回地點 id。行動鎖內叫。"""
    if not TALE_THREADS or game.client is None or game.tavern_chatter_request() is None:
        return None
    place = game.state.player.location
    return None if place in CHATTER_RUNNING else place


def write_chatter(game: Game, place: str) -> bool:
    """酒肆鄰桌閒談：開一個背景執行緒寫一段。A 鎖內拿單子（Game.tavern_chatter_request）→ B 鎖外請模型寫（tavern.chatter_write，
    預算 Config.tavern.ask_budget_seconds；排隊時當假人排在真人後面）→ C 鎖內重驗才記（Game.apply_tavern_chatter；寫不出來記空的，
    這一陣子照固定句）。開了回 True。呼叫端不能握著行動鎖。"""
    with TALE_LOCK:
        if place in CHATTER_RUNNING:
            return False
        CHATTER_RUNNING.add(place)

    def job() -> None:
        try:
            chatter_once(game)
        except Exception:  # noqa: BLE001 — 背景執行緒：印出來就好，閒談照固定句
            traceback.print_exc()
        finally:
            with TALE_LOCK:
                CHATTER_RUNNING.discard(place)

    threading.Thread(target=job, name="tavern-chatter", daemon=True).start()
    return True


def chatter_once(game: Game) -> bool:
    """寫一段（write_chatter 的那一圈；測試直接叫）：記了寫好的回 True。呼叫端不能握著行動鎖。"""
    with _locked(game):
        request = game.tavern_chatter_request()
    if request is None:
        return False
    budget = game.content.config.tavern.ask_budget_seconds
    started = _monotonic()

    def ask() -> list[str]:
        return tavern.chatter_write(within_budget(game.client, budget - (_monotonic() - started)), request)

    if QUEUE is None:
        lines = ask()
    else:
        try:
            lines = QUEUE.run(TALE_OWNER, ask, fallback=[], bot=True, wait=budget)
        except (Busy, QueueTimeout):
            lines = []
    with _locked(game):
        return game.apply_tavern_chatter(request, lines)


def duel_text(game: Game, text: str) -> list[str]:
    """單人頭目戰的放手一搏，三段同 battle_text：A Game.duel_text_request（只讀）→ B 鎖外請模型評成功率、寫成敗兩版劇情
    （預算同隨口應對）→ C Game.duel_gamble 重驗同一隻、同一回合、同一句才用評好的分，對不上回「這一回合已經結算」、不重評。"""
    started, request = _open_request(game, lambda: game.duel_text_request(text))
    if isinstance(request, list):
        return request
    total = game.content.config.free_text_budget_seconds
    fallback = battle_instance.GambleVerdict(battle_instance.DEFAULT_FREE_TEXT_SUCCESS_RATE)
    scene = duel.Scene(request.title, request.scene)

    def score():
        client = within_budget(game.client, total - (_monotonic() - started))
        if client is None and game.client is not None:
            return fallback, ""
        verdict = battle_instance.assess_gamble(
            client, scene, request.faction_name, request.text, request.name, setting=request.setting or duel.SETTING,
            place=request.place or duel.PLACE, target=request.target, sex=request.sex,  # 擂台帶對手那一行與擂台的場合（Game.duel_text_request）
        )
        crowd = ""
        if request.boss.startswith("arena:") and arena_crowd.on(game.content):  # 擂台：另問一次台下觀眾的反應（評分那一次的提示不動）
            crowd = arena_crowd.judge_gamble(within_budget(game.client, total - (_monotonic() - started)), request.text,
                                             request.title, request.name)
        return verdict, crowd

    verdict, crowd = model_call(game, score, fallback=(fallback, ""), left=total - (_monotonic() - started), busy=BUSY_FREE_TEXT)
    return act(game, lambda g: g.duel_gamble(request.text, verdict.rate, (verdict.win, verdict.lose), request=request, crowd=crowd))


def create_intent(game: Game, body: dict) -> list[str]:
    """自創武學的立意（tianxia/create.py），三段同 duel_text：A Game.create_request（只讀）→ B 鎖外 create.read 讀這一句意
    （分數、最多兩路屬性、正邪；預算同隨口應對）→ C Game.create_intent(reading=) 整個重驗再成形。叫不動照關鍵字表讀。"""
    text = str(body.get("text") or "")[:create.INTENT_MAX * 2]
    started, request = _open_request(game, lambda: game.create_request(text))
    if isinstance(request, list):
        return request
    total = game.content.config.free_text_budget_seconds

    def reading():
        return create.read(within_budget(game.client, total - (_monotonic() - started)), request, game.content)

    value = model_call(
        game, reading, fallback=create.fallback_read(game.content, request.text),
        left=total - (_monotonic() - started), busy=BUSY_FREE_TEXT,
    )
    return act(game, lambda g: g.create_intent(request.text, reading=value))


def create_reread(game: Game, body: dict) -> list[str]:
    """重悟帖的第二個用法：重讀這句意（可以改寫），三段同 create_intent：A Game.create_reread_request → B 鎖外 create.read_or_none
    → C Game.create_reread(reading=)。叫不動（None）就什麼都不改、不扣帖（不照關鍵字表讀）。"""
    text = str(body.get("text") or "")[:create.INTENT_MAX * 2]
    started, request = _open_request(game, lambda: game.create_reread_request(text))
    if isinstance(request, list):
        return request
    total = game.content.config.free_text_budget_seconds

    def reading():
        return create.read_or_none(within_budget(game.client, total - (_monotonic() - started)), request)

    value = model_call(game, reading, fallback=None, left=total - (_monotonic() - started), busy=BUSY_FREE_TEXT)
    return act(game, lambda g: g.create_reread(request.text, value))


def ascend_line(game: Game) -> list[str]:
    """破境卡那一句（tianxia/ascend.py），三段同 create_intent：A Game.ascend_request（只讀）→ B 鎖外 ascend.read
    （預算同隨口應對）→ C Game.ascend_line 存回卡上（卡換了就不存）。叫不動照套句。"""
    started, request = _open_request(game, game.ascend_request)
    if request is None:
        return []
    total = game.content.config.free_text_budget_seconds

    def writing():
        return ascend.read(within_budget(game.client, total - (_monotonic() - started)), request)

    value = model_call(game, writing, fallback=ascend.fallback(request), left=total - (_monotonic() - started), busy=BUSY_FREE_TEXT)
    return act(game, lambda g: g.ascend_line(request, value))


def tavern_ask(game: Game, text: str) -> list[str]:
    """問酒家（酒肆，設計第八節），三段：A Game.tavern_ask_request（只讀；問到秘密的單子不叫模型）→ B 鎖外 tavern.ask_write
    （預算 Config.tavern.ask_budget_seconds）→ C Game.tavern_ask 重驗同一間、同一句再收錢；叫不動模型退全額。"""
    started, request = _open_request(game, lambda: game.tavern_ask_request(text))
    if isinstance(request, list):
        return request
    total = game.content.config.tavern.ask_budget_seconds

    def write():
        client = within_budget(game.client, total - (_monotonic() - started))
        return tavern.ask_write(client, request)

    reply = None if request.secret else model_call(game, write, fallback=None, left=total - (_monotonic() - started),
                                                     busy=BUSY_FREE_TEXT)
    return act(game, lambda g: g.tavern_ask(request.question, reply, request=request))


def outing_tale(game: Game) -> list[str]:
    """走一趟的遊記（tianxia/outing.py），三段：A Game.outing_tale_request（只讀；收了、還沒請過才開單）→ B 鎖外 outing.tale_write
    （預算 Config.jianfa.outing_tale_seconds）→ C Game.outing_set_tale 照同一趟才收；叫不動、不合用記成請過了，畫面用模板。"""
    started, request = _open_request(game, game.outing_tale_request)
    if isinstance(request, list):
        return request
    total = game.content.config.jianfa.outing_tale_seconds

    def write():
        client = within_budget(game.client, total - (_monotonic() - started))
        return outing.tale_write(client, request)

    text = model_call(game, write, fallback=None, left=total - (_monotonic() - started), busy=BUSY_FREE_TEXT)
    return act(game, lambda g: g.outing_set_tale(text, request))


def seal_text(game: Game, text: str) -> list[str]:
    """奪璽單挑的放手一搏（玉璽碎片設計 5.7），三段同 duel_text：A Game.seal_text_request（只讀；判成不在場的回合不開單）→
    B 鎖外請模型評成功率、寫成敗兩版劇情（預算同隨口應對，評不到 40）→ C Game.seal_gamble 重驗同一場、同一回合、同一邊、同一句才用，
    回合對不上直接回「這一回合已經結算」，不在鎖內重評。"""
    started, request = _open_request(game, lambda: game.seal_text_request(text))
    if isinstance(request, list):
        return request
    total = game.content.config.free_text_budget_seconds
    fallback = battle_instance.GambleVerdict(battle_instance.DEFAULT_FREE_TEXT_SUCCESS_RATE)
    scene = duel.Scene(request.title, request.scene)

    def score():
        client = within_budget(game.client, total - (_monotonic() - started))
        if client is None and game.client is not None:
            return fallback
        return battle_instance.assess_gamble(
            client, scene, request.faction_name, request.text, request.name,
            setting=seal_duel.SETTING, place=seal_duel.PLACE, target=request.target, sex=request.sex,
        )

    verdict = model_call(game, score, fallback=fallback, left=total - (_monotonic() - started), busy=BUSY_FREE_TEXT)
    return act(game, lambda g: g.seal_gamble(request.text, verdict.rate, (verdict.win, verdict.lose), request=request))


# ── 畫面資料 ──────────────────────────────────────────


PATCH_FILE = ROOT / "content" / "patch_notes.json"
PATCH_SHOW = 3  # 首頁「改版」那一格列最近幾次
_patch_cache: dict = {"mtime": None, "notes": []}


def patch_notes(path: Path | None = None) -> list[dict]:
    """登入頁宣傳影片底下的「近期改版」（Joy 2026-10-21「首頁應該有地方顯示近期的更版資訊」）。

    讀 content/patch_notes.json 的 notes（新的在前），最多 PATCH_SHOW 次；檔案改了照修改時間重讀，不必重開伺服器。
    每一次只留 date、new、tweak、fix 四欄（字串與字串清單），寫壞的那一次跳過、檔案讀不了就是空的（首頁不畫那一格）。"""
    path = path or PATCH_FILE
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []
    if path == PATCH_FILE and _patch_cache["mtime"] == mtime:
        return _patch_cache["notes"]
    try:
        raw = json.loads(path.read_text(encoding="utf-8")).get("notes", [])
    except (OSError, ValueError, AttributeError):
        raw = []
    notes = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("date"), str) or not item["date"].strip():
            continue
        lines = {key: [x for x in item.get(key) or [] if isinstance(x, str) and x.strip()] for key in ("new", "tweak", "fix")}
        if any(lines.values()):
            notes.append({"date": item["date"].strip(), **lines})
        if len(notes) >= PATCH_SHOW:
            break
    if path == PATCH_FILE:
        _patch_cache.update(mtime=mtime, notes=notes)
    return notes


def main_view(game: Game) -> dict:
    """江湖畫面與頂上的狀態列；每次動作、每次計時器都回這一份。呼叫端要拿著行動鎖。"""
    with game.phase_memo():  # 這一次建構裡「籌備中嗎」只讀一次共用狀態（見 Game.phase_memo）
        return _main_view_body(game)


def _main_view_body(game: Game) -> dict:
    fighting = game.battle_on_screen()
    card = game.battle_card() if game.shows_battle_card() else None
    status, quest, scene = game.status_data(), md(game.quest_text()), md(game.scene_text())
    options = game.options()  # 照原本的順序：狀態、主線、場景先讀，選單（會推進全服戰鬥）最後
    if fighting and not game.battle_on_screen():
        # 這一次的選單把決戰推到收場了（手機介面自檢 U-06）：先讀的場景還停在最後一回合，換成收場之後的（回到地點），
        # 卡片、狀態、主線也一起重讀，跟「剛剛」（下面才讀）同一刻
        card = game.battle_card() if game.shows_battle_card() else None
        status, quest, scene = game.status_data(), md(game.quest_text()), md(game.scene_text())
    latest = game.journal_top_html()
    view = {
        "status": status,
        "quest": quest,
        "scene": scene,
        "art": scene_art(game, status),  # 場景卡上面那張圖（減法季批 8）：事件插圖、人物像或地點的圖；沒有圖檔是 None、網頁一字不變
        "options": [o.model_dump() for o in options],
        # 走一趟（tianxia/outing.py）：探索鈕的段數選單（picker）與這一趟（trip）；關著是 None、網頁照舊一顆探索
        "outing": game.outing_view(),
        "say_max": game.say_max(),  # 「自己說」最多幾個字（NPC 智能 2.0開著時比較長，網頁的輸入框照它）
        # 出陣開著（出陣探索與地盤設計第二節）：行動列那一格叫「出陣」、等候的話換一句；關著時照舊「遊歷」
        "sortie": sortie.on(game.content),
        # 一類一顆開著（正式季整合第二章）：應召畫成行動列上面一條金框橫幅（設計 9.1 第 1 組乙），不收在「此地還能做」
        "precise": precise.on(game.content, game.state.world),
        # 城裡操練與城外練功（新手引導重做，tianxia/training.py）：練功從探索三選一拿出來，在行動列自成一格
        "training": training.on(game.content, game.state.world),
        # 行動列底下那幾行（explain-1）：探索、遊歷、交友、求見這一下會怎樣（選項 id → 一句；序章裡是空的）
        "action_notes": game.action_notes(o.id for o in options),
        # 有所感選做法那一步（explain-2）：做法鈕上寫的心意（選項 id → 剛柔快慢）與鈕底下兩行小字；不在選做法是 None
        "sense_help": game.method_help(o.id for o in options),
        # 在路上（路上設計 3.3）：頁面在選項底下多放三個捷徑（輿圖、修練、煉製），那是頁面切換、不是引擎的行動。
        # 看的是選單本身：參戰者在決戰大區裡走動時選單是戰鬥選項，那時不放捷徑
        "on_road": any(o.id == "act:on_road" for o in options),
        "free_text": game.battle_free_text_prompt() or game.seal_free_text_prompt() or game.duel_free_text_prompt()
        or game.feast_free_text_prompt(),  # 宴席上自己寫的敬酒詞（第三批）
        "free_text_note": game.battle_free_text_note() or game.seal_free_text_note() or game.duel_free_text_note(),  # 放手一搏輸入框旁邊：風險越高、失手時傷自己越重
        # 輸入框送到哪裡：正在打的決戰 > 奪璽單挑 > 頭目戰（玉璽碎片設計 5.7）
        "free_op": "battle_text" if game.battle_free_text_prompt() is not None
        else "seal_text" if game.seal_free_text_prompt() is not None
        else "feast_text" if game.feast_free_text_prompt() is not None else "duel_text",
        "event_free_text": game.event_free_text_prompt(),
        # 事件分級：眼前的事件是第二、三階時，場景卡頂上那一行（州郡大事、天下大事）與框色；第一階是 None、一字不變
        "event_tier": game.event_tier(),
        # 特殊事件的跳顯框（開頭、此事已了・入傳、此事未了）：照順序一張一張跳，「收下」送 story_seen 清掉；沒有是空的
        "story_cards": story_cards(game),  # 眼前事件的隨口應對：選單上那一顆按下去叫出輸入框
        "keepsakes": list(game.state.player.keepsakes),  # 長篇奇事的紀念物（俠客頁「紀念」那一段；沒有效果、不能賣）
        # 「剛剛」：這次行動打了仗就放戰鬥卡片，卡片沒寫到的補充放在 now；之後配了點也一樣（配點不換「剛剛」，計畫二最終審查 M1）
        "card": md(card) if card is not None else None,
        "card_id": game.battle_card_id() if card is not None else None,
        # 決戰的即時戰局條（Joy 2026-10-10）：場景裡畫著的這一場（集結、開打），與「剛剛」是一場決戰時收場那一刻的
        "battle_gauge": game.battle_gauge(),
        "card_gauge": game.card_gauge() if card is not None else None,
        # 江湖紀錄頁是 latest＋journal＋older 接起來的，從最新一則列起（最新一則就是卡片那一場時，latest 是卡片的補充）
        "latest": latest,
        "journal": game.journal_html(1, RECENT_ROWS),
        "older": game.journal_html(1 + RECENT_ROWS, OLDER_ROWS),
        # 江湖頁的「剛剛」：跟 latest 一樣，只是最新的幾則若只是本週大事（江湖頁那排小標「大事」點開的面板；休季是結算卡）上已經有全文的大事，
        # 改放再前面那一則，同一段公告不寫兩次（FB-046）；最新的配點也越過，卡片與補充看的都是那一場那一則
        "now": game.battle_extra_html(for_card=True) if card is not None else game.now_entry_html(),
        # 出陣回報（企劃者 2026-10-23）：「剛剛」那一則是領地爭奪的出陣時，卡片底下的進度條、一句話與小籤（sortie.report）；不是 None
        "front": game.now_front(),
        # 小地圖（舊的江湖頁那一張）網頁已經不畫了：不再每次輪詢在鎖裡重畫、多送 30 KB（全面自檢 S-07）
        # 此地還有誰（玩家之間的互動第一層）：[{name, side}]；路上、序章裡是空的。真人假人同一份（伺服器假人設計第五節）
        "here": game.peers_here(),
        "calls": game.calls_here(),  # 別人遞給你、還沒回的打招呼、結伴、切磋邀請（玩家互動第二層）；回應鈕是選單上的 invite: 選項
        "party": game.party_view(),  # 結伴同行的那一行；沒有是 None
        "bulletin": [md(text) for text in game.bulletin()],  # 江湖頁那排小標「大事」點開的本週大事（新的在前）；開關關著是空的
        "trends": md(game.trends_text()),
        "rumors": md(game.rumors_text()),
        "chronicle": md(game.chronicle_text()),
        "tales": tale_index(game),  # 江湖史最上面那排「戰記」：[{battle_id, title, season, result}]，新的在前；開關關著是空的
        "admin": game.is_admin(),
        "paused": game.paused_minutes(),  # 賽季時鐘停了幾分鐘；沒暫停是 None（設定頁的「暫停／繼續」）
        "guide": game.guide_box(),  # 行動列上方的說書人對話框（引導重做設計 8.1）；略過或早就做完是 None
        # 序章（新手引導計畫一）：要亮的畫面元件、要發光的鈕、略過連結；不在序章是 None，網頁照平常畫
        "prologue": game.prologue_view(),
        # 初入江湖（新手引導第四段）：出了草廬之後那幾步要亮的畫面元件、要發光的元件；不在初入江湖是 None
        "onboard": game.onboard_view(),
        "horse_art": horse_art(),  # 馬市與修練頁坐騎那一列：真的有圖檔的那幾個鍵，其餘照舊畫色塊
        # 伺服器推送（線上架構設計 5.3）：頁面照 push 決定開不開 /api/events（開著時平常 60 秒才輪詢一次、有通知才刷新），
        # push_spread 是收到「世界變了」之後各分頁重抓畫面要攤開的秒數（預檢 F3：全服同時重抓會在同一把行動鎖上排隊）
        "push": HUB is not None,
        "push_spread": game.content.config.push_world_min_seconds,
        "web_push": WEB_PUSH is not None,  # 手機通知（減法季批 9）：設定頁畫不畫那一顆、第一次來信問不問
    }
    shop = game.shop_view([o.id for o in options])  # 店面（店面獨立介面設計 6.1）：開關開著、店開著、鐵匠鋪那一串是眼前的選單才有
    if shop is not None:
        view["shop"] = shop
    milestone = game.milestone_card()  # 減法季屬性五段的境界卡（主機側計畫欄位表 main.milestone）：到了境界、點還沒配完才有這個鍵
    if milestone is not None:
        view["milestone"] = milestone
    # 功能包的狀態（FEATURES 的 status，照清單的順序；開發規範手冊 3.3）：商城的入口 mall（齒輪旁的錠子鈕＋餘額、底部第六格）；關著沒有這個鍵
    view.update(game.feature_status())
    if view["guide"] is not None:  # 入伍段「出一次力」：選單上能完成它的那幾顆（FB-093）；網頁讓它們發光，「此地還能做」攤開
        view["guide"]["glow"] = game.enlist_glow([o.id for o in options if o.enabled])
    if "fronts" in status:  # 第一季濃縮版才有：江湖頁的三條戰況（開關關著時不送，頁面照舊）
        view["fronts"] = status["fronts"]
    orders = game.orders_view()  # 第一季：自己陣營的本週軍令（計畫 T6；散人、別陣營、開關關著時都沒有這個鍵）
    if orders:
        view["orders"] = orders
    # 減法季批 1（整合設計 6.1、3.4）：江湖頁最上面的本週卡（主題、你這一步）與三方卡；序章裡、休季沒有這兩個鍵
    week = weekcard.week_card(game, status, orders)
    if week is not None:
        view["week_card"] = week
    # 四格探索那一格的小字「城裡多事」（整合設計 6.3，批 5）；在路上沒有這個鍵。減法季探索一顆開著時照出門一趟那一張表（批 2，Game.mostly_here）
    mostly = game.mostly_here()
    if mostly:
        view["mostly"] = mostly
    sides = weekcard.sides_card(game)
    if sides is not None:
        view["sides_card"] = sides
    talking = game.state.player.pending_companion  # 人物頁（減法季批 6）：正在跟他談的那一位的心意條；關著、他沒有心意沒有這個鍵
    figure = game.figure_view(talking) if talking else None
    if figure is not None:
        view["figure"] = figure
    errands_now = game.errands_view()  # 託付清單（減法季批 6，主機側計畫 1.3 的 main.errands）；託付關著沒有這個鍵
    if errands_now is not None:
        view["errands"] = errands_now
    event_opts = game.event_option_view()  # 事件選項只留動作（整合設計 6.4）：選項 id → 動作、圖示、沒把握時的心裡話；沒有事件沒有這個鍵
    if event_opts is not None:
        view["event_opts"] = event_opts
    layers = game.rumor_layers()  # 第一季：見聞頁的傳聞分四層（開關關著時不送，頁面照舊畫 rumors 那一條清單）
    if layers is not None:
        view["rumor_layers"] = [{**layer, "body": md(layer["body"])} for layer in layers]
    convoy = game.convoy_line()  # 押著的糧車（T6 審查 I3）：軍令卡上寫一行
    if convoy is not None:
        view["convoy"] = convoy
    conquest_view = game.conquest_view()  # 領地爭奪：戰書排的攻城、每一塊的翻地資料、能不能下戰書（開關關著、季收了沒有這個鍵）
    if conquest_view is not None:
        view["conquest"] = conquest_view
    # 出陣約戰（減法季批 3b，計畫 1.3）：出陣前那張卡（main.sortie 已經是出陣開著的布林，卡放 sortie_card）與約戰卡清單；約戰關著沒有這兩個鍵
    duel_card = game.sortie_card()
    if duel_card is not None:
        view["sortie_card"] = duel_card
    duel_cards = game.sortie_cards()
    if duel_cards is not None:
        view["sorties"] = duel_cards
    banner = game.siege_banner()  # 領地爭奪第三批 A：場景裡畫的是攻城戰時，最上面那一條「攻城・地點｜守方：某某」（企劃者挑甲；決戰沒有這個鍵）
    if banner is not None:
        view["siege"] = banner
    if xingshi.on(game.content, game.state.world):  # 〈天下形勢〉開著的季：見聞多一顆「形勢」（文章另外讀 /api/xingshi；關著沒有這個鍵）
        view["xingshi"] = True
        view["xingshi_mark"] = game.xingshi_mark()  # FB-578：最新一篇的篇次＋有沒有一張還在寫；變了，停在「形勢」頁的網頁就重抓
    plan = game.plan_view()  # 世界活起來：全服開著的盤算裡最切身的一件（江湖頁行動列底下一張卡）；沒有開著的就沒有這個鍵
    if plan is not None:
        view["plan"] = plan
    place_deeds = game.place_deeds_view()  # 世界活起來：此地舊事（場景卡底下最近的幾筆世界記事）；沒有就沒有這個鍵
    if place_deeds is not None:
        view["place_deeds"] = place_deeds
    letter = game.letter_view()  # 書信（大勢人物擴充第二批）：江湖頁「剛剛」上面一張小卡；沒有沒看過的信就沒有這個鍵
    if letter is not None:
        view["letter"] = letter
    zhuan = game.biography_entry()  # 休季：江湖頁最上面的「讀你的傳」（玩家傳第二批）；季還在跑、沒有行狀是 None
    if zhuan is not None:
        if zhuan.get("illustration"):  # 列傳插畫（減法季批 7b）：圖檔在才給網址，沒有是 None
            zhuan["illustration_src"] = zhuan_art_src(zhuan["illustration"])
        view["zhuan"] = zhuan
    result = game.season_result()  # 第一季休季：江湖頁最上面的結算卡（計畫 T9；開關關著、進行中都不送）
    if result is not None:
        view["season_result"] = {
            **{key: value for key, value in result.items() if key != "ending"}, "text": md(result["text"]),
            "timeline": [{**row, "text": md(row["text"])} for row in result["timeline"]],
        }
    # 三陣營四勝利的結局卡（減法季批 3c；計畫 1.3 欄位表的 main.ending）：關著的季沒有這個鍵。本週卡「你這一步」與三方卡是批 1 的
    # week_card、sides_card（上面），批 3c 的資料補在那裡面（step.finish、Game.sides_card、Game.tier_hint），這裡不另送一份
    ending = game.ending_card()
    if ending is not None:
        view["ending"] = ending
    return view


def menxia_view(game: Game, person: str | None = None) -> dict:
    """修練與煉製兩頁的資料（同一份：心得、名冊、背包、功法庫都兩邊用得到）。person 是名冊裡點的人。"""
    lines = game.roster_lines()
    person = None if person is None else str(person)  # 客戶端寫的：JSON 清單之類不能拿去查集合（unhashable → 500）
    if person not in {key for _, key in lines}:
        person = None
    member = game.state.player.member
    # 身上兩門各自有沒有功法、練到第幾成、練滿了沒（C5 鍛鍊鈕亮不亮）；還沒學是 False、0、False
    learned = {"武學": member.wugong_id is not None, "內功": member.neigong_id is not None}
    level = {
        "武學": member.wugong_level if learned["武學"] else 0,
        "內功": member.neigong_level if learned["內功"] else 0,
    }
    return {
        "xinde": game.state.player.stats.get("xinde", 0),
        "rules": md(game.menxia_rules()),
        "attribute_note": game.attribute_note(),  # 純文字，網頁自己跳脫；兩頁各摺一行（W2）
        "player_card": md(game.member_card("player")),
        "roster": [{"label": label, "key": key} for label, key in lines],
        "roster_cards": game.roster_cards(),  # 門下一人一張卡（俠客頁，Joy 2026-10-26）
        "person": person,
        "person_card": md(game.member_card(person)) if person else None,
        "on_team": person is not None and person in game.state.player.team,
        "release": game.release_view(person),  # 歷史武將同行：名下的同伴多一顆「放他回江湖」（問句）；不是就 None
        "lessons": game.chuangong_lessons(person),  # 傳功鈕（同伴、部下；本人與開關關著是空的）
        "bag": md(game.bag_text()),
        "heal": game.heal_button(),  # 修練頁的療傷鈕：按不按得下去、不能按的原因（FB-082）；鈕上的字寫內傷與下面的 heal_cost
        # 背包旁的「伏筆物品」：開關開著、這一季蓋了章、手上有才有東西，沒有就是空的（畫面整塊不出現）。只有名字與數量
        "clue_items": [
            {"id": item.id, "name": item.name, "count": n} for item, n in foreshadow.held_items(game.state, game.content)
        ],
        # 功法卡（FB-006）：身上兩門各一張，還沒學的那一門是一句「你還沒有內功。」；
        # 功法庫通常只有幾門，卡一起送，點開不必再打一次 API（QA L4：先看卡再改練）
        "slot_cards": [
            {"kind": k, "card": md(game.skill_detail(k)), "learned": learned[k], "level": level[k],
             "maxed": level[k] >= team.MAX_LEVEL,
             # 序章裡這一欄現在不能練的原因（Game.practice_refusal）；平常是 None。練成鈕灰掉、寫它
             "blocked": game.practice_refusal(k),
             # 練下一成要的心得（修練頁的鈕上寫給玩家看）；還沒學或已經第十成就沒有價錢
             "price": team.practice_price(game.content, level[k], treasures.amount(game.state, game.content, "practice")) if learned[k] and level[k] < team.MAX_LEVEL else None}
            for k in KINDS
        ],
        # 療傷要多少銀兩（修練頁的療傷鈕上寫）：照內傷計價，沒有內傷是 0
        "heal_cost": team.heal_cost(game.content, member, game.state),
        "forge_line": md(game.forge_line([])),
        # 武學與成長（修練頁、煉製頁）：持有數與上限、每門武學一列（身上的在前）、悟得的意境、等著取名的那一門
        "seclude_blocked": game.seclusion_refusal(),  # 序章裡不閉關：閉關鈕灰掉、寫這句；平常是 None
        "holdings": game.holdings(),
        "owned_arts": [{**row, "card": md(row["card"])} for row in game.art_rows()],
        "insights": game.insight_rows(),
        "naming": game.naming_row(),
        # 裝備（裝備四欄設計 2.5）：開著的欄位一段一段（武器、防具、坐騎），每段身上那件、裝備庫裡同一欄的；格數四欄合算。
        # 都關著時 slots 是空的，修練頁那一塊不畫
        "gear": game.gear_rows(),
        # 全身的戰力（招式與絕學稿案第四輪；tianxia/might.py）：修練頁人形圖氣血旁邊那個數，換上清單的「→ N」跟它比
        "might": might.now(game.state, game.content, game.world),
        "legend_items": game.state.player.legend_items,  # 手上的破境丹：服丹衝關有沒有真的擲骰，網頁照它少沒少一枚判斷
        # 自創武學的入口從煉製搬到修練（第四輪）：開關關著、還在序章裡是 None
        "create": {"price": create.price(game.state, game.content), "problem": create.allowed(game.state, game.content)}
        if create.on(game.content) else None,
    }


MAP_BASE: dict[str, dict] = {}  # 輿圖升級的底圖：照開放的地點（mapdata.base_key）快取；一季差不多只有一兩把鍵
MAP_BASE_KEEP = 8  # 超過就整個清掉重來（劇情開放的地點只有幾處，不會真的到）


def map_base_view(game: Game) -> dict:
    """輿圖升級的底圖與清單（/api/map/base）：同一把鍵（開放的地點一樣）回同一份，不重畫。呼叫端拿著行動鎖（look）。
    減法季探索一顆開著的季，名字旁的兩個字是看的人的（Game.map_mostly，2f，FB-886；網頁讀這裡 places[].mostly）：快取的是跟人無關的那一份
    （山河的圖、路、大區、天下圖），每個人再換上自己的名字旁與鍵（mapdata.with_mostly，新的 dict、重的部分同一份物件）；鍵跟疊層
    （Game.map_state）的 key 是同一串，字變了網頁就會重抓。"""
    key = mapdata.base_key(game.state, game.content)
    if key not in MAP_BASE:
        if len(MAP_BASE) >= MAP_BASE_KEEP:
            MAP_BASE.clear()
        MAP_BASE[key] = game.map_base(viewer=False)
    mostly = game.map_mostly()
    if mostly is None:
        return MAP_BASE[key]
    return mapdata.with_mostly(MAP_BASE[key], mapdata.base_key(game.state, game.content, mostly), mostly)


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
        # 圖例不畫進 svg（圖裡的會跟著平移、縮放，放大時就看不見）：跟 svg 並排給網頁，疊在地圖框角落（web/app.js 的 legendHtml）
        "legend": game.map_legend(layer),
        "places": [{"label": label, "id": loc_id} for label, loc_id in places],
        "selected": selected,
        "here": game.state.player.location,
        "detail": md(game.place_detail(selected)),
        # 步行、疾行兩個按鈕（照 atlas.MODES 的順序）；就在這裡時是 None。被待處理的事件擋著時只有一顆灰的、
        # label 寫是哪一則，to_jianghu 為真：頁面在旁邊多給一顆「回江湖」（FB-063）
        "travel": [
            {"mode": o.mode, "label": o.label, "enabled": o.enabled, "to_jianghu": o.to_jianghu}
            for o in game.travel_options(selected) or []
        ] or None,
    }


def reports_view(game: Game, record_id: int | None) -> dict:
    if record_id is None:
        record_id = game.latest_battle_id()
    big = game.big_battle_ids()
    return {
        # big：決戰、奪璽單挑，網頁另外排一組在最上面（Joy 2026-10-14）
        "list": [{"label": label, "id": rid, "big": rid in big} for label, rid in game.battle_list()],
        "selected": record_id,
        "detail": md(game.battle_detail(record_id)) if record_id is not None else md(REPORT_EMPTY_TEXT),
        "gauge": game.record_gauge(record_id),  # 決戰的戰報畫收場那一刻的戰局條（Joy 2026-10-10）；不是決戰是 None
        # 戰記（Joy 2026-10-29）：決戰、奪璽單挑的戰報帶著資料庫裡那一場的流水號，網頁拿它問 /api/tale/<流水號>；其他是 None
        "tale_id": _tale_ref(game, record_id),
    }


def _tale_ref(game: Game, record_id: int | None) -> int | None:
    record = battlelog.find(game.state, record_id)
    return record.battle_ref if record is not None and record.kind in battlelog.BIG_KINDS else None


def admin_choices(game: Game) -> dict:
    """管理者觸發區的三個下拉選單（戰鬥、大事、大勢線）與模型佇列的總數。戰鬥與大事照引擎給的（Game.admin_battles／admin_fires：
    內容的順序，第一季不觸發的 beta 決戰與門檻不列；已經發生過的大事按下去會被引擎拒絕）；
    大勢線照這一季的規則（第一季濃縮版要開關開著、而且這一季蓋了「開」的章）。呼叫端要拿著行動鎖（look）。"""
    world = game.state.world
    return {
        # 賽季在哪個階段（籌備中 preparing／進行中 running／休季 resting）：開季、立刻收季、開啟下一季只在對的階段按得下去（U-19）
        "phase": game.world.season_phase(),
        "battles": [{"label": b.name, "id": b.id} for b in game.admin_battles()],
        "events": [{"label": f"{x.text[:30]}（{x.id}）", "id": x.id} for x in game.admin_fires()],
        # 照開關：關著時不列第一季才有的線；開著時不列黃巾聲勢（由三條戰線合成，不能直接推）
        "trends": [{"label": t.name, "id": t.id} for t in CONTENT.scenario.trends if rules.pushable(CONTENT, world, t.id)],
        **timetable_choices(game),
        # 這一季照第一季的規則（開關開著、開季時蓋了章）：管理者區多「每週的事」（立刻發本週軍令、立刻輪替第 4 階席次）
        "season_one": rules.season_one(CONTENT, world),
        # 21 天季（季曆就是現實的週）：暫停、繼續的問句多說一句季曆會對回現實的星期（PM 2026-10-19）
        "season21": calendar.season21_on(world, CONTENT),
        # 那一句照季寫（FB-501）：「21 天的季…對回現實的星期」「7 天的季…對回現實的日子」（同 world.realign_line）
        "realign": {"days": f"{season_length_days(world, CONTENT):g}", "unit": calendar.week_word("realign", CONTENT, world)}
        if calendar.season21_on(world, CONTENT) else None,
        # 開季、開下一季的問句括號裡那一句：7 天濃縮季照時刻表寫（timetable.default_dates_note）；其他季 None，網頁照原本的字
        "default_dates": timetable.default_dates_note(CONTENT),
        # 「這一季立刻蓋天命之季的章」問句裡天命之爭的時刻：7 天濃縮季照時刻表寫（timetable.mandate_note，FB-503）；其他季 None，網頁照原本的字
        "mandate_at": timetable.mandate_note(CONTENT, world),
        # 三場大戲各一顆「立刻開這一場」（Game.admin_showdowns）：開不了的灰掉、寫為什麼（開過了、結算了、宛城要等第 3 週……）
        "showdowns": [
            {"id": event.id, "label": event.title, "enabled": why is None, "note": why or ""}
            for event, why in game.admin_showdowns()
        ],
        # 下一季會照第一季的規則開（開關開著）：「開啟下一季」的問句也提醒排三場大戲與季末的時間（FB-050）
        "next_has_timetable": bool(CONTENT.config.season_one),
        # 救場「叫回人物」：這一季退場、重創的大勢人物（沒有就不畫那一列）
        "fallen": [{"label": CONTENT.figures[fid].name, "id": fid} for fid in game.admin_fallen()],
        "seal": game.admin_seal_choices(),  # 玉璽一組（碎片關著是 None，不畫）
        "xingshi": xingshi.on(CONTENT, world),  # 〈天下形勢〉開著的季：管理者區多一顆「現在就開一篇天下形勢」（領地爭奪第三批 A）
        # 領地爭奪開著的季：救場一組（定一塊歸誰、定進度、立刻下戰書、取消一場攻城）的下拉選單；關著、季收了是 None（不畫）
        "conquest": game.admin_conquest_choices(),
        "mingtie": game.admin_mingtie_reports(),  # 被檢舉的名帖（撤下、放回）；沒有是空的
        # 新神器用完了（正式季整合 5.6，FB-400）：主控台啟動時印、換季的回話寫，管理者那一塊也寫一行；沒用完是空字串
        "divine_out": divine.EXHAUSTED if divine.exhausted_now(game.world.divine_state(), game.world.get_season_number()) else "",
        # 模型佇列的總數（正在跑幾件、在排幾件，真人與假人算在一起，不分開數）；不列名號，也看不出有沒有假人（審查 M4）。開關關著是 None
        "llm_queue": None if QUEUE is None else QUEUE.snapshot(),
    }


RESULT_WORDS = (("guan:", "官軍"), ("huang:", "黃巾"))  # 結果鍵的白話（定結果的下拉選單）
# cancelled：開打後被取消、還沒有結果（FB-099）：要收尾用「定結果」（只有管理者看得到）
TIMETABLE_STATES = {"done": "已結算", "running": "開打了", "cancelled": "開打後取消・待定結果", "due": "時間到了", "later": "還沒到"}


def _result_label(key: str) -> str:
    if key == "fixed":
        return "照史書"
    for prefix, side in RESULT_WORDS:
        if key.startswith(prefix):
            return side + key[len(prefix):]
    return key


def _ending_title(ending_id: str) -> str:
    """季末那一列的結果：時間軸記的是結局 id（world._finale），寫結局的標題（FB-051）。"""
    return next((e.title for e in CONTENT.scenario.endings if e.id == ending_id), ending_id)


def _done_label(key: str) -> str:
    """時刻表上已結算那一件的結果：拿掉版本（宛城、秦頡的「甲:」「乙:」），跳過的寫「跳過」。"""
    if key == timetable.SKIPPED:
        return "跳過"
    head, _, rest = key.partition(":")
    return _result_label(rest if rest and head not in ("guan", "huang") else key)


def timetable_choices(game: Game) -> dict:
    """設定頁的「時刻表」與「救場」（計畫 T10）：這一季有時刻表（第一季）才有東西，beta 那一季全是空的。
    時刻表每件一列，可排的（三場決戰與季末）附現實時間 at_real（照此刻的季時間換算，time_scale 照設定）；
    定結果的下拉選單列還沒結算、此刻知道是哪一版的大事的每一個結果；鎖定列有人鎖定的大事。"""
    state = game.state
    world = state.world
    if not rules.season_one(CONTENT, world):
        return {"timetable": [], "results": [], "locks": []}
    now = time.time()
    rows = []
    for row in timetable.status_rows(state, CONTENT, cancelled=game.cancelled_showdowns()):
        rows.append({
            # 7 天濃縮季寫「第 1 段（第 1～2 天）」（calendar.week_label，FB-501）；其他季「第1週」
            "id": row["id"], "label": f"{calendar.week_label(row['week'], CONTENT, world, form='tight')}　{row['title']}",
            "state": row["state"], "state_text": TIMETABLE_STATES[row["state"]],
            "result": (_ending_title(row["result"]) if row["kind"] == "finale" else _done_label(row["result"]))
            if row["result"] else None,
            "schedulable": row["schedulable"],
            "at_real": now + (row["when"] - world.time) / CONTENT.config.time_scale if row["schedulable"] else None,
        })
    results = [
        {"value": f"{e.id}|{key}", "label": f"{e.title}：{_result_label(key)}"}
        for e in timetable.events(world, CONTENT) if e.id not in world.timeline
        for key in timetable.result_keys(state, CONTENT, e)
    ]
    locks = [
        {"id": event_id, "label": f"{e.title}（{lock.name}）"}
        for event_id, lock in world.locks.items() if (e := timetable.find(CONTENT, event_id))
    ]
    return {"timetable": rows, "results": results, "locks": locks}


def _float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default: int) -> int:
    """瀏覽器送來的數字：不是數字就當成預設值（範圍由引擎自己夾，例如閉關 1~12 小時）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _moves(value) -> list[str]:
    """約戰卡送來的三招（減法季批 3b）：清單或「強攻,固守,奇襲」，最多看前幾樣、每樣最多幾個字；對不對由引擎驗（sortie_duel.moves_problem）。"""
    items = value if isinstance(value, list) else str(value or "").replace("、", ",").replace("，", ",").split(",")
    return [str(m).strip()[:4] for m in items[:6] if str(m).strip()]


DONATE_ITEMS_MAX = 40  # 一次最多捐幾種（背包裡的素材種類遠少於這個；擋亂送的長清單）


def donate_items(body: dict) -> list[tuple[str, int]]:
    """軍需帳送來的 items（[{material, count}, …]）：形狀不對的那一筆略過、個數至少 1，範圍與收不收由引擎自己擋。"""
    items = body.get("items")
    out = []
    for item in items[:DONATE_ITEMS_MAX] if isinstance(items, list) else []:
        if isinstance(item, dict) and item.get("material"):
            out.append((str(item["material"]), max(1, _int(item.get("count"), 1))))
    return out


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


def create_character(account_key: str, name: str, sex: str | None = None) -> Game:
    """建立角色：檢查名號沒人用 → 建存檔 → 綁到帳號，三步在同一筆交易裡做完（不跟假人程式取名撞在一起）。
    sex：建角色畫面選的性別（PM 2026-10-12）；只認「男」「女」，別的當沒選（男、設定頁還能選一次）。"""
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
            game = Game.new(CONTENT, name, prologue=True, sex=sex if sex in gender.GENDERS else None)  # 網頁上建的新角色走序章（新手引導計畫一）；假人與腳本不走
            open_characters().save(game.state)
            store.bind_character(account_key, name)
    return game_for(name)


def change_password(account_key: str, old: str, new: str, again: str, keep: str | None = None) -> str:
    """keep 是改密碼的這個裝置的 cookie：它留著，同一個帳號別的裝置都登出（PM 2026-10-31）。"""
    if (new or "") != (again or ""):
        return PASSWORDS_DIFFER
    try:
        account_store().change_password(account_key, old, new, keep)  # 同上：自己是一筆交易，慢的雜湊不在交易裡算
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


def _character_name(request: Request) -> str:
    """這個登入的帳號的角色名號（沒登入 401、還沒有角色 409）；只查帳號，不開 Game、不拿行動鎖。"""
    account = account_store().get(_account(request))
    if account is None or account.character is None:
        raise HTTPException(409, "這個帳號還沒有角色。")
    return account.character


def _warm_model() -> None:
    """有人登入就先叫 Ollama 把模型載起來（省電模式下模型平常是卸掉的，見 tianxia/power_save.py）。

    射後不理（OllamaClient.warm 自己開背景執行緒），登入這個請求一點都不等。模型載入約十幾秒，趁玩家還在讀畫面、
    還沒走到人物面前時載好，免得他點第一句對話就撞上冷啟動（讀取逾時 30 秒、鎖內 15 秒、斷路器 180 秒）。
    這裡只補「剛登入」這一下；之後「人還在線就一直熱著」是 scripts/warm_keeper.py 的事。
    """
    try:
        client = OllamaClient.from_config(CONTENT.config)
    except Exception:  # noqa: BLE001  暖不了不能影響登入
        return
    client.warm()  # warm 自己在背景執行緒裡跑到模型載完（見 OllamaClient.warm），這裡不會被擋住


LOOPBACK = ("127.0.0.1", "::1", "localhost")


def client_ip(request: Request) -> str:
    """這個請求從哪個 IP 來（註冊的次數照它算）。走固定網域時 cloudflared 在這台機器上轉進來，直接連線的一端永遠是本機，
    真正的來源在 Cloudflare 加的 CF-Connecting-IP；只有直接連線的一端是本機時才認那個標頭（--lan 的時候外面的人
    自己帶一個 CF-Connecting-IP 也騙不了）。都沒有就是空字串。"""
    peer = request.client.host if request.client is not None else ""
    forwarded = (request.headers.get("cf-connecting-ip") or "").strip()
    if forwarded and peer in LOOPBACK:
        return forwarded
    return peer


def via_https(request: Request) -> bool:
    """這個請求是不是走 https 來的：直接 https，或 cloudflared 轉進來時標的 X-Forwarded-Proto: https。"""
    return request.url.scheme == "https" or (request.headers.get("x-forwarded-proto") or "").strip().lower() == "https"


def cookie_secure(request: Request) -> bool:
    """cookie 要不要加 Secure（審查 S-10）：請求走 https 來的（via_https），或公開網址（TIANXIA_PUBLIC_URL）是 https、而這個請求
    就是衝著那個網域來的（隧道沒標 X-Forwarded-Proto 也照樣加）。主機在這台電腦上開 http://127.0.0.1:7861、--lan 時區網用
    http 連，都不是那個網域：不加，照樣登入得了（加了的話瀏覽器在 http 上直接丟掉這個 cookie）。"""
    if via_https(request):
        return True
    public = urlsplit(os.environ.get(PUBLIC_URL_ENV) or "")
    return public.scheme == "https" and bool(public.hostname) and request.url.hostname == public.hostname


def _register_allowed(ip: str, now: float) -> bool:
    """這個 IP 這一小時還能不能註冊（REGISTER_LIMIT）；只看，不記。"""
    with _REGISTER_LOCK:
        recent = [t for t in REGISTRATIONS.get(ip, []) if now - t < REGISTER_WINDOW]
        REGISTRATIONS[ip] = recent
        return len(recent) < REGISTER_LIMIT


def _registered(ip: str, now: float) -> None:
    with _REGISTER_LOCK:
        REGISTRATIONS.setdefault(ip, []).append(now)


def _start_session(request: Request, response: Response, account_key: str) -> None:
    token = SESSIONS.create(account_key)
    _warm_model()
    response.set_cookie(
        COOKIE, token, httponly=True, samesite="lax", max_age=SESSION_SECONDS, secure=cookie_secure(request),
    )


def _entry(account_key: str) -> dict:
    """登入後的去處：還沒角色就要取名號，有角色就直接進遊戲。"""
    account = account_store().get(account_key)
    if account is None:
        return {"stage": "login"}
    if account.character is None:
        return {"stage": "create"}
    return {"stage": "game", "main": poll_main(game_for(account.character)), "kinds": KINDS}  # 暫停中照樣進得來、看得到


def content_version(content: bytes) -> str:
    """檔案內容的雜湊（前十碼）：內容沒變、版本就不變，所以只動引擎的更版不會讓手機重抓。"""
    return hashlib.sha256(content).hexdigest()[:10]


def asset_version(url_path: str) -> str:
    """頁面引用的網址（/journal.css、/manifest.webmanifest 或 /static/<檔名>）對應的版本；檔案不存在就丟 FileNotFoundError。"""
    if url_path == "/journal.css":
        return content_version(JOURNAL_CSS.encode("utf-8"))
    return content_version((WEB / url_path.removeprefix("/static/").lstrip("/")).read_bytes())


# 頁面裡指向我們自己檔案的網址；不碰 data:、外部網址，也不碰已經帶了 ? 的
OWN_ASSET = re.compile(r"""(src|href)=(["'])(/static/[^"'?#]+|/journal\.css|/manifest\.webmanifest)\2""")


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


@app.get("/api/patch_notes")
def api_patch_notes() -> dict:
    """登入頁的近期改版：不用登入、不拿行動鎖，只讀 content/patch_notes.json。"""
    return {"notes": patch_notes()}


@app.get("/api/me")
def me(request: Request):
    key = SESSIONS.get(request.cookies.get(COOKIE, ""))
    return {"stage": "login"} if key is None else _entry(key)


@app.post("/api/login")
def api_login(request: Request, response: Response, body: dict = Body(...)):
    key = login(body.get("login", ""), body.get("password", ""))
    _start_session(request, response, key)
    return _entry(key)


@app.post("/api/register")
def api_register(request: Request, response: Response, body: dict = Body(...)):
    """註冊。同一個來源 IP 一小時最多 REGISTER_LIMIT 個帳號（審查 S-10）：超過了回 TOO_MANY_REGISTERS，跟其他註冊錯誤一樣。"""
    ip, now = client_ip(request), time.time()
    if not _register_allowed(ip, now):
        raise GameError(TOO_MANY_REGISTERS)
    key = register(body.get("login", ""), body.get("password", ""), body.get("again", ""))
    _registered(ip, now)
    _start_session(request, response, key)
    return _entry(key)


@app.post("/api/character")
def api_character(request: Request, body: dict = Body(...)):
    key = _account(request)
    create_character(key, body.get("name", ""), body.get("gender"))
    return _entry(key)


@app.post("/api/logout")
def api_logout(request: Request, response: Response):
    SESSIONS.pop(request.cookies.get(COOKIE, ""), None)
    response.delete_cookie(COOKIE, httponly=True, samesite="lax", secure=cookie_secure(request))
    return {"stage": "login"}


@app.get("/api/main")
def api_main(request: Request):
    """計時器：同步時間、存檔、回江湖畫面（氣血、體力等數字才會跟著走）。一把鎖做完（見 act_look）。
    賽季時鐘暫停中畫面照常更新（停了幾分鐘、繼續了沒）：輪詢的動作只是同步，不經過 _refuse_while_paused。"""
    return poll_main(_game(request))


# 江湖畫面上的動作：回傳 {main, message}。引擎的訊息本來就會寫進江湖紀錄，這裡的 message
# 只有不寫紀錄的動作（例如管理者的操作）才用得到，前端拿它跳一句提示。
MAIN_ACTIONS = {
    "seclude": lambda g, b: g.seclude(_int(b.get("hours"), 8)),
    # 店面的直接開爐（店面獨立介面設計 6.3）：打的是同一個 smithing.forge；出爐卡在 game.smith_result，api_do 一起回
    "smith_forge": lambda g, b: g.smith_forge(str(b.get("kind", "")), str(b.get("main", "")), str(b.get("aux", ""))),
    # 鐵匠鋪的素材買賣（素材與經濟設計第四、五節）：收購一次賣 count 個、升階一次換一個
    "smith_sell": lambda g, b: g.smith_sell(str(b.get("material", "")), max(1, _int(b.get("count"), 1))),
    "smith_upgrade": lambda g, b: g.smith_upgrade(str(b.get("attribute", "")), _int(b.get("tier"), 0)),
    # 自家大本營捐軍備（素材與經濟設計第六節）：一次捐一種素材 count 個（上限切一半：收得下的收）；軍需帳那一頁送 items
    # （[{material, count}, …]，挑好的幾種一起捐、一則紀錄）
    "donate": lambda g, b: g.donate_items(donate_items(b)) if "items" in b else g.donate(str(b.get("material", "")), max(1, _int(b.get("count"), 1))),
    # 酒肆那一頁（企劃者 2026-10-18）：op 是 news、seek、ties、material、wall、treat、hide、trace；target 是名號或素材 id、text 是題壁那一句
    "tavern": lambda g, b: g.tavern_do(str(b.get("op", "")), str(b.get("target", ""))[:20], str(b.get("text", ""))[:40]),
    "anonymous": lambda g, b: g.set_anonymous(bool(b.get("value"))),
    "gender": lambda g, b: g.set_gender(str(b.get("value", ""))),  # 設定頁：還沒選過性別的舊角色選一次（PM 2026-10-12）
    "story_seen": lambda g, b: g.story_seen(),  # 特殊事件的跳顯框按「收下」：看過的卡清掉
    "letter_read": lambda g, b: g.read_letter(_int(b.get("id"), -1)),  # 書信小卡的「收起」（大勢人物擴充第二批）
    "letter_decline": lambda g, b: g.decline_letter(_int(b.get("id"), -1)),  # 書信小卡的「婉拒」：委託作罷
    "hints_off": lambda g, b: g.set_hints_off(bool(b.get("value"))),  # 設定頁的「不再提示」（碰到才說，新手引導計畫三）
    "skip_tutorial": lambda g, b: g.skip_tutorial(),
    "view_map": lambda g, b: g.view_map(),
    "view_orders": lambda g, b: g.view_orders(),  # 入伍段第一步：軍令卡出現在畫面上（新手引導計畫二）
    "view_tab": lambda g, b: g.view_tab(str(b.get("tab", ""))),  # 序章裡打開修練、煉製頁（新手引導計畫一）
    "guide_ack": lambda g, b: g.guide_ack(),  # 對話框的結語按「知道了」
    "allocate": lambda g, b: g.allocate_stat(str(b.get("stat", ""))),  # 狀態列的配點鈕：升級得到的屬性點加到一項
    "newbie_drifter": lambda g, b: g.newbie_drifter(),  # 任務卡「新手目標」的「就當散人」（新手引導重做）
    "pill": lambda g, b: g.take_stamina_pill(),  # 狀態列體力條上的「丹」：吃一顆回體丹（企劃者 2026-10-07 內測贈送）
    # 江湖頁「簽到」小標攤開的領取鈕（21 天季，正式季整合 6.2）：四階的日子帶 attribute（剛柔快慢）
    "checkin": lambda g, b: g.check_in(str(b.get("attribute", ""))[:2]),
    # 領地爭奪：下戰書（翻地與爭搶，輿圖簡化設計 4.4；這一週在任的第 4 階、自己那一邊在這一塊的進度到門檻）。每天投票拿掉了（PM 2026-10-20）
    "conquest_letter": lambda g, b: g.conquest_letter(str(b.get("loc", ""))),
    # 玉璽碎片改版第 2 批：起用懷中那一片的獨門行動。target 是指定的目標（大勢人物、戰線、人物 id），side 是散人傳檄挑的那一軍；
    # 玩家的叫 seal_use，跟管理者那一組 seal_* 不同名（FB-609）
    "seal_use": lambda g, b: g.seal_use(str(b.get("target", ""))[:40], str(b.get("side", ""))[:20]),
    # 出陣約戰（減法季批 3b；main.sortie_card、main.sorties）：moves 是三招（清單，或「強攻,固守,奇襲」），id 是約戰卡上的 id。
    # 引擎在 world.mutate 裡重驗（兩個人同時應戰，先到的那一位是守方）；關著的季回「此刻無法這麼做」
    "sortie_go": lambda g, b: g.sortie_go(_moves(b.get("moves"))),
    "sortie_answer": lambda g, b: g.sortie_answer(str(b.get("id", ""))[:80], _moves(b.get("moves"))),
    "sortie_join": lambda g, b: g.sortie_join(str(b.get("id", ""))[:80]),
    # 走一趟（tianxia/outing.py）：n 是段數（1／3／5）就出發；0 或沒帶是停在要選的事上、選完接著走。沿路的事在 main.outing.trip
    "outing": lambda g, b: g.outing_go(_int(b.get("n"), 0)),
}
# 賽季時鐘暫停中也照做的畫面設定（不推任何東西、不碰別人）：匿名、不再提示、略過引導、打開輿圖（頁面靠它載入輿圖）、軍令卡出現（入伍段第一步，
# 只動自己的引導；被擋下的話網頁已經記成「送過了」，這個工作階段不會再送）、對話框的「知道了」
PAUSE_OK_ACTIONS = frozenset({"anonymous", "gender", "hints_off", "story_seen", "skip_tutorial", "view_map", "view_orders", "guide_ack"})
ADMIN_ACTIONS = {
    "outing_erase": lambda g, b: g.admin_erase_inscription(_int(b.get("id"), 0)),  # 走一趟的留言：管理者抹掉一則
    "open_season": lambda g, b: g.admin_open_season(time.time()),
    "end_season": lambda g, b: g.admin_end_season(time.time()),
    "next_season": lambda g, b: g.admin_next_season(time.time()),
    # 公告停機時賽季時鐘暫停（線上架構第四節、8.3）；主機端另有 scripts/season_clock.py
    "pause_clock": lambda g, b: g.admin_pause_clock(time.time()),
    "resume_clock": lambda g, b: g.admin_resume_clock(time.time()),
    "fast_forward": lambda g, b: g.advance(_int(b.get("hours"), 1) * 3600),
    "start_battle": lambda g, b: g.admin_start_battle(str(b.get("id", "")), time.time()),
    "fire": lambda g, b: g.admin_fire(str(b.get("id", ""))),
    "push_trend": lambda g, b: g.admin_push_trend(str(b.get("id", "")), _int(b.get("amount"), 0)),
    # 時刻表與救場（計畫 T10）：現實時間由伺服器給，引擎不讀時鐘
    "schedule": lambda g, b: g.admin_schedule(str(b.get("id", "")), _float(b.get("at"), 0.0), time.time()),
    "jump_next": lambda g, b: g.admin_jump_next(time.time()),
    "set_trend": lambda g, b: g.admin_set_trend(str(b.get("id", "")), _int(b.get("value"), 0)),
    # 領地爭奪（第 38 項改版第一批）：定一塊歸誰（side 空字串＝放回中立）；第一批沒有攻城戰，地圖只靠這裡與時刻表指定易手
    "conquest_set": lambda g, b: g.admin_conquest_set(str(b.get("id", "")), str(b.get("side", "")) or None),
    # 救場（翻地與爭搶，QA 用）：定一條進度（到 100 照推滿易手）、立刻替一邊下戰書（集結馬上開）、取消一場（id 是時程表那一場的 id）。
    # 立刻下戰書叫 admin_conquest_letter，不叫 conquest_letter：api_do 先查這一張，同名會把玩家的下戰書（MAIN_ACTIONS）整個蓋掉（FB-609）
    "conquest_progress": lambda g, b: g.admin_conquest_progress(str(b.get("id", "")), str(b.get("side", "")), _float(b.get("value"), 0.0)),
    "admin_conquest_letter": lambda g, b: g.admin_conquest_letter(str(b.get("id", "")), str(b.get("side", ""))),
    "conquest_cancel": lambda g, b: g.admin_conquest_cancel(str(b.get("id", ""))),
    "xingshi_now": lambda g, b: g.admin_xingshi_now(),  # 領地爭奪第三批 A：現在就開一篇〈天下形勢〉
    "resolve_event": lambda g, b: g.admin_resolve_event(str(b.get("id", "")), str(b.get("key", ""))),
    "clear_lock": lambda g, b: g.admin_clear_lock(str(b.get("id", ""))),
    "cancel_battle": lambda g, b: g.admin_cancel_battle(),
    "revive_figure": lambda g, b: g.admin_revive_figure(str(b.get("id", ""))),
    # 管理者觸發鈕（企劃者 2026-10-07）：每週的事照週一的做法立刻再做一次
    "issue_orders": lambda g, b: g.admin_issue_orders(),
    "rotate_seats": lambda g, b: g.admin_rotate_seats(),
    # 三場大戲：照時刻表開（跟「立刻開戰」同一條路），開過就算開過
    "start_showdown": lambda g, b: g.admin_start_showdown(str(b.get("id", "")), time.time()),
    # 玩家個人劇情：name 是那個玩家的名號，在這一把行動鎖裡讀他的存檔、補算、做完存回去（見 Game._admin_target）
    "summon": lambda g, b: g.admin_summon(str(b.get("name", ""))),
    "give_opportunity": lambda g, b: g.admin_give_opportunity(str(b.get("name", "")), str(b.get("id", ""))),
    "give_fragment": lambda g, b: g.admin_give_fragment(str(b.get("name", "")), str(b.get("id", ""))),
    # 玉璽碎片（玉璽碎片設計第十二節）：效果跟自然發生一樣，公告不寫管理者
    "seal_emerge": lambda g, b: g.admin_seal_emerge(str(b.get("id", ""))),
    "seal_stir": lambda g, b: g.admin_seal_stir(str(b.get("id", ""))),
    "seal_assign": lambda g, b: g.admin_seal_assign(str(b.get("id", "")), str(b.get("name", "")), str(b.get("state", "held"))),
    "seal_duel": lambda g, b: g.admin_seal_duel(str(b.get("id", "")), str(b.get("name", "")), _float(b.get("factor"), 1.0), time.time()),
    "seal_fix": lambda g, b: g.admin_seal_fix(b.get("take") is True),
    "seal_cancel": lambda g, b: g.admin_seal_cancel(),
    "seal_sink_check": lambda g, b: g.admin_seal_sink_check(time.time()),
    "seal_mandate": lambda g, b: g.admin_seal_mandate(str(b.get("when", ""))),
    # 名帖檢舉（Joy 2026-10-19）：撤下清掉畫與自題，放回是看過沒事
    "mingtie_remove": lambda g, b: g.admin_mingtie_remove(str(b.get("name", "")), _int(b.get("version"), 0)),
    "mingtie_restore": lambda g, b: g.admin_mingtie_restore(str(b.get("name", "")), _int(b.get("version"), 0)),
}
PLAYER_ADMIN_ACTIONS = frozenset({"summon", "give_opportunity", "give_fragment", "mingtie_remove"})  # 動到別人的存檔：做完也叫他的分頁刷新

# ── 功能包的管理者工具與路由（FEATURES；開發規範手冊 3.3）：殼照清單掛，位置就是原本商城那一段（路由的先後不變）。
# 商城（/api/mall/…、/api/admin/mall、管理者的補發扣回退款）搬進 tianxia/features/mall/routes.py ──
FEATURE_ADMIN_ACTIONS = features_core.admin_tools(sys.modules[__name__])
for _router in features_core.routers(sys.modules[__name__]):
    app.include_router(_router)


@app.post("/api/choose")
def api_choose(request: Request, body: dict = Body(...)):
    game = _game(request)
    option_id = str(body.get("id", ""))
    # text：需要打字的那幾顆（神品意境自己取名 dunwu:own）；沒帶就是 None，跟以前一樣
    said = body.get("text")
    msgs = choose(game, option_id, text=None if said is None else str(said))
    if not isinstance(msgs, Refused) and NOT_ON_MENU not in (msgs or []):  # 被擋下來、不在選單上的不算按了
        _play_did(game, button_of(option_id), FIGURE_TALK if may_generate_dialogue(option_id) else None)
    _tell_tabs(game)
    out = {"main": look(game, main_view)}
    if option_id.startswith("battle:") or (msgs and msgs[0] in FIGHT_GONE_LINES) or isinstance(msgs, Refused):
        # 決戰選項（加入、趕到、每回合的出招）：按下去發生了什麼只有這句回話（FB-030），前端拿它跳一句提示。
        # 大場面等判讀的時候選項沒了（「你離開了，這一仗沒打成。」）：這一仗沒打、不寫江湖紀錄，也只有這句回話。
        # 兩個分頁搶同一張懸賞，慢的那一頁按下去的懸賞選項已經不在選單上（FB-162）：同樣沒寫江湖紀錄，只有這句回話。
        # 其他選項的話已經寫進江湖紀錄、「剛剛」看得到，再回一句會重複，所以不回。
        out["message"] = joined(msgs)
    # 神品意境自己取名被擋（名字不合格、這一季全服撞名）：那一句要回給表單，不然玩家只看到輸入框沒反應。
    # 取成了不回（話在江湖紀錄與「剛剛」卡上，同別的選項）
    elif option_id == EPIPHANY_OWN and game.state.player.god_naming is not None:
        out["message"] = joined(msgs)
    return out


@app.post("/api/answer")
def api_answer(request: Request, body: dict = Body(...)):
    game = _game(request)
    answer_event(game, str(body.get("text", "")))
    _play_did(game, "answer", FREE_TEXT)
    _tell_tabs(game)
    return {"main": look(game, main_view)}


@app.post("/api/say")
def api_say(request: Request, body: dict = Body(...)):
    game = _game(request)
    say(game, str(body.get("text", "")), str(body.get("option") or SAY_OPTION))
    _play_did(game, "say", FIGURE_TALK)
    _tell_tabs(game)
    return {"main": look(game, main_view)}


@app.post("/api/do/{op}")
def api_do(op: str, request: Request, body: dict = Body(default={})):
    tool = FEATURE_ADMIN_ACTIONS.get(op)  # 功能包的管理者工具（商城的補發、扣回、退一筆）
    if tool is not None:
        tool.gate()  # 那一包關著：沒有這個東西（先於登入的檢查，跟 /api/mall 一樣）
    game = _game(request)
    if tool is not None:
        if not game.is_admin():
            raise GameError("只有管理者能這麼做。")
        msgs = act(game, lambda g: tool.run(g, body), paused_ok=tool.paused_ok)  # 商城：帳跟季無關，暫停中也做得了
    elif op in ADMIN_ACTIONS:
        if not game.is_admin():
            raise GameError("只有管理者能這麼做。")
        msgs = act(game, lambda g: ADMIN_ACTIONS[op](g, body), paused_ok=True)  # 暫停中要按得到「繼續」；其他的引擎自己擋
    elif op == "outing_say":  # 走一趟留言：自己寫的那一句先在行動鎖外審（speech.judge），預設句不必審
        text = speech.clean(str(body.get("text", ""))[:200])
        preset = _int(body.get("preset"), -1)
        verdict = screen_text(game, text, speech.MOTTO) if preset < 0 and text else ""
        msgs = act(game, lambda g: g.outing_say(preset, text, verdict))
    elif op == "outing_tale":  # 走一趟的遊記：模型在行動鎖外寫（見 outing_tale）
        msgs = outing_tale(game)
    elif op == "battle_text":  # 放手一搏：成功率在行動鎖外評（見 battle_text）
        msgs = battle_text(game, str(body.get("text", "")))
    elif op == "seal_text":  # 奪璽單挑的放手一搏：同上（見 seal_text）
        msgs = seal_text(game, str(body.get("text", "")))
    elif op == "duel_text":  # 頭目戰的放手一搏：同上（見 duel_text）
        msgs = duel_text(game, str(body.get("text", "")))
    elif op == "create_intent":  # 自創武學的形意：意分在行動鎖外評（見 create_intent）
        msgs = create_intent(game, body)
    elif op == "create_reread":  # 重悟帖：重讀這句意，意分在行動鎖外評（見 create_reread）
        msgs = create_reread(game, body)
    elif op == "ascend_line":  # 破境卡那一句：模型在行動鎖外寫（見 ascend_line）
        msgs = ascend_line(game)
    elif op == "tavern_ask":  # 問酒家：回話在行動鎖外寫（見 tavern_ask）
        msgs = tavern_ask(game, str(body.get("text", ""))[:60])
    elif op == "feast_text":  # 宴席上自己寫的敬酒詞：分數在行動鎖外評（見 feast_text）
        msgs = feast_text(game, str(body.get("text", "")))
    elif op == "gather_text":  # 找素材的「自己說」：成算在行動鎖外評（見 gather_text）
        msgs = gather_text(game, str(body.get("text", "")))
    elif op == "persuade_text":  # 託付的勸降（減法季批 6）：那一句在行動鎖外評（見 persuade_text）；id 是那一件託付
        msgs = persuade_text(game, str(body.get("id", ""))[:20], str(body.get("text", ""))[:60])
    elif op in MAIN_ACTIONS:
        msgs = act(game, lambda g: MAIN_ACTIONS[op](g, body), paused_ok=op in PAUSE_OK_ACTIONS)
    else:
        raise HTTPException(404)
    _tell_tabs(game, str(body.get("name", "")) if op in PLAYER_ADMIN_ACTIONS else "")
    out = {"main": look(game, main_view), "message": joined(msgs)}
    if op == "smith_forge":
        out["forged"] = game.smith_result  # 店面的出爐卡（麻布的光、點開的卡）；被拒絕是 None
    return out


def forge_args(body: dict) -> tuple[str | None, list[str]]:
    """煉製頁送來的東西：意境 id 們（爐裡只合意境）；舊網頁送來的武學 id 照傳，引擎回「爐裡只合意境」那一句。body 是客戶端寫的：
    意境不是清單就當作沒放，形狀不對只會得到一句話，不會打出 500。"""
    art, picked = body.get("art"), body.get("insights")
    return str(art) if art else None, [str(i) for i in picked] if isinstance(picked, list) else []


def _forge_without_naming(game: Game, art_id: str | None, insight_ids: list[str]) -> list[str]:
    return game.forge(art_id, insight_ids, proposed=NO_NAME)


def _int_of(value) -> int:
    """網頁送來的一個整數（裝意境的第幾格）：不是整數、負的一律當 0。"""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _id_list(value) -> list[str]:
    """網頁送來的一串 id：只收字串串列，其他（字串、數字、物件）一律當空的。"""
    return [str(v) for v in value if isinstance(v, str)] if isinstance(value, list) else []


MENXIA_ACTIONS = {
    "practice": lambda g, b: g.practice(str(b.get("kind") or KINDS[0])),
    "heal": lambda g, b: g.heal(),
    # 一武學＋一意境、兩武學＝合成，兩意境＝合併。端點走 forge()（A 鎖內備料 → B 鎖外取名或挑 → C 鎖內登記），不走這一條；
    # 這裡也帶 NO_NAME，就算有人直接拿它在鎖裡呼叫，也不會叫模型
    "forge": lambda g, b: _forge_without_naming(g, *forge_args(b)),
    "switch": lambda g, b: g.switch_art(str(b.get("art") or "")),
    # 武學重構：把意境裝進武學的意境槽、或拆下來（修練頁與煉製頁都走這裡；不花心得體力）
    "slot": lambda g, b: g.slot_insight(
        str(b.get("art") or ""), str(b.get("insight") or ""), _int_of(b.get("index")) if b.get("index") is not None else None,
    ),
    "unslot": lambda g, b: g.unslot_insight(str(b.get("art") or ""), str(b.get("insight") or "")),
    # 自創武學（tianxia/create.py）：執器、擺式、回頭、立名、擱下；立意走 /api/do/create_intent（三段式，模型讀這一句意）
    "create_begin": lambda g, b: g.create_begin(str(b.get("kind") or ""), str(b.get("form") or "")),
    "create_pose": lambda g, b: g.create_pose(b.get("pose") if isinstance(b.get("pose"), dict) else {}),
    "create_back": lambda g, b: g.create_back(str(b.get("to") or "")),
    "create_name": lambda g, b: g.create_name(str(b.get("name") or ""), str(b.get("move") or "")[:create.MOVE_MAX * 2]),
    "create_cancel": lambda g, b: g.create_cancel(),
    "create_reroll": lambda g, b: g.create_reroll(),  # 重悟帖：成了形直接重骰（萬寶閣，Joy 2026-10-21）
    "ascend_dismiss": lambda g, b: g.ascend_dismiss(),  # 看過破境卡了
    # 用融的意境修練一次，衝下一品；use_legend 是勾了「服下破境丹」。只認真正的布林 true：字串、數字都不算勾
    "cultivate": lambda g, b: g.cultivate(str(b.get("art") or ""), use_legend=b.get("use_legend") is True),
    "melt": lambda g, b: g.melt_art(str(b.get("art") or "")),  # 功法庫裡的一門熔成心得
    "melt_insight": lambda g, b: g.melt_insight(str(b.get("insight") or "")),
    # 批量熔煉：勾好的武學（arts）與意境（insights）一次熔完；不是串列的當沒勾
    "melt_many": lambda g, b: g.melt_many(_id_list(b.get("arts")), _id_list(b.get("insights"))),
    "name": lambda g, b: g.name_mastered(str(b.get("name") or "")),  # 第一個練成絕學的人替它取正式名字
    # 神器原品定名（打造隱藏配方設計 5.2）：自己打的名字，或 keep 是「沿用譜名」；keep 只認真正的布林 true（同 use_legend）
    "name_divine": lambda g, b: g.name_divine(str(b.get("weapon") or ""), str(b.get("name") or ""), keep=b.get("keep") is True),
    "bind_art": lambda g, b: g.bind_art(str(b.get("weapon") or ""), str(b.get("art") or "")),
    "join": lambda g, b: g.add_to_team(str(b.get("person") or "")),
    "leave": lambda g, b: g.remove_from_team(str(b.get("person") or "")),
    "release": lambda g, b: g.release_companion(str(b.get("person") or "")),  # 放他回江湖（歷史武將同行）：引擎驗是不是你名下的
    "wield": lambda g, b: g.wield_weapon(str(b.get("weapon") or "")),  # 裝備庫上那一件換到身上它那一欄（兵器設計 2.2、裝備四欄 2.3）：武器、防具、坐騎、寶物都走這裡，網頁照舊送 weapon 這個鍵
    "dismantle": lambda g, b: g.dismantle_weapon(str(b.get("weapon") or "")),  # 裝備庫上那一件拆成一個素材（兵器設計 4.7.1、裝備四欄 4.8）：坐騎、寶物不能拆
    "feed": lambda g, b: g.feed_mount(),
    # 傳功門下（Config.chuangong）：名冊上點的那個人（person）練一項（what：neigong／wugong／str／agi／con）；引擎照 lessons 驗
    "chuangong": lambda g, b: g.chuangong(str(b.get("person") or ""), str(b.get("what") or "")),  # 身上那匹餵一個一階素材（裝備四欄 5.4）：閒著時哪裡都能餵
}


@app.get("/api/peer")
def api_peer(request: Request, name: str = ""):
    """玩家卡（social.card）：他不在這裡了 card 是 None，網頁照 gone 那一句說。只讀。"""
    game = _game(request)
    return {"card": look(game, lambda g: g.peer_card(name)), "gone": social.GONE}


@app.get("/api/figure")
def api_figure(request: Request, id: str = ""):
    """人物頁（減法季批 6，主機側計畫 1.3 的 figure.stances、figure.errands）：這位人物（對話人物 id）的心意條、你今天記的那一筆、
    他託你的事（Game.figure_view）。關著、他什麼都沒有是 None。只讀。"""
    game = _game(request)
    return {"figure": look(game, lambda g: g.figure_view(str(id)[:40]))}


@app.post("/api/peer/act")
def api_peer_act(request: Request, body: dict = Body(default={})):
    """按了玩家卡上的一顆鈕（Game.peer_act）：回傳 {card, main, message}。參數都是客戶端寫的，一律轉成字串或整數再交給引擎驗。"""
    game = _game(request)
    name, action = str(body.get("name", "")), str(body.get("action", ""))
    params = {"arg": str(body.get("arg", "")), "choice": str(body.get("choice", ""))}
    try:
        params["amount"] = int(body.get("amount", 0))
    except (TypeError, ValueError):
        params["amount"] = 0
    params["text"] = str(body.get("text", ""))[:200]  # 挑釁附的一句話（CardButton.text）：C 段照字數與字表再驗
    verdict = screen_peer(game, name, action, params)  # 那一句先在鎖外請模型審（speech.judge），結果交給 C 段
    if verdict:
        params["verdict"] = verdict
    proposed = prepare_peer(game, name, action, params)  # 論武的首創取名：A 鎖內開單、B 鎖外取名，C 是下面的 peer_act
    if proposed is not None:
        params["proposed"] = proposed
    msgs = act(game, lambda g: g.peer_act(name, action, params))
    _tell_tabs(game)
    return {
        "card": look(game, lambda g: g.peer_card(name)),
        "gone": social.GONE,
        "main": look(game, main_view),
        "message": joined(msgs),
        # 卡已經關了或換了人時，網頁的提示泡泡只講這一句（FB-242）：論武合成了是「論武有結果了：合出…」，其餘是回話的第一句
        "brief": game.peer_brief or social.brief(msgs),
    }


@app.post("/api/party/leave")
def api_party_leave(request: Request):
    """還在等帶頭的人動身時的「分道揚鑣」（Game.leave_party）；在路上時走選單的 act:part。回傳 {main, message}。"""
    game = _game(request)
    msgs = act(game, lambda g: g.leave_party())
    _tell_tabs(game)
    return {"main": look(game, main_view), "message": joined(msgs)}


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
    person = None if person is None else str(person)  # 客戶端寫的：清單之類不是字串的，下面查名冊會丟 TypeError

    def run(g: Game):
        # 名冊（誰是你的人）是全服狀態，換季、假人程式都會改：跟動作在同一把鎖裡核對，引擎才能假設那個人在名冊上
        if op in ("join", "leave", "release") and person not in {key for _, key in g.roster_lines()}:
            raise GameError("名冊裡沒有這個人。")  # 交易整筆撤回（連同進鎖時的同步）；下一個請求重讀再算一次
        return MENXIA_ACTIONS[op](g, body)

    # 開爐：首次合出來的配方要模型取名，在行動鎖外取（見 prepare_forge）；其他動作照舊一把鎖做完
    msgs = forge(game, *forge_args(body)) if op == "forge" else act(game, run)
    made = op == "forge" and game.forged  # 開爐真的合成了：煉製頁把爐子清空；被拒絕（只回一句話）的東西留在爐裡（Joy 2026-10-12）
    _tell_tabs(game)
    out = {
        "menxia": look(game, lambda g: menxia_view(g, person)),
        "main": look(game, main_view),
        "message": joined(msgs),
    }
    if op == "forge":
        out["made"] = made
        # 合出來的那一樣（煉製頁在結果底下直接畫它的卡，不必切去修練頁看；Joy 2026-10-17）：{"type": "art"／"ins", "id"}
        thing = game.forged_thing if made else None
        out["made_item"] = {"type": thing[0], "id": thing[1]} if thing else None
    if op in ("forge", "slot"):
        out["secret"] = game.secret_solved  # 這一季第一次參透一條秘方：網頁跳一個視窗（secretPop）；沒有是 None
    return out


@app.get("/api/prologue")
def api_prologue(request: Request):
    """設定頁的「重看序章」：序章的事件與師父的話排成一頁（Markdown 轉成 HTML）；沒有序章的內容是空字串，網頁就不畫那顆鈕。"""
    game = _game(request)
    return look(game, lambda g: {"text": md(g.prologue_recap())})


@app.get("/api/howto")
def api_howto(request: Request):
    """設定抽屜的「玩法說明」（explain-1）：五個行動、體力、情誼、心得、意境、背包各一兩句，數字照設定（Markdown 轉成 HTML）。
    不看個人狀態，網頁同一次載入只問一次。"""
    game = _game(request)
    return look(game, lambda g: {"text": md(g.howto_text())})


@app.post("/api/sense")
def api_sense(request: Request, body: dict = Body(default={})):
    """有所感畫完那一筆：points 是 [[x, y, 毫秒], …]，png 是畫布的小圖（base64，不含 data: 開頭）。"""
    game = _game(request)
    msgs = sense_draw(game, body.get("points"), body.get("png") or "")
    _tell_tabs(game)
    return {"main": look(game, main_view), "message": joined(msgs)}


@app.post("/api/sense_read")
def api_sense_read(request: Request, body: dict = Body(default={})):
    """畫布底下那一行（不算行動、不拿鎖、不碰狀態）：這一筆讀不讀得出來（跟送出時讀的是同一套 glyph.read）。讀得出來只回 ok，
    不寫規則讀到什麼——玩家面前不寫筆畫的幾何（企劃者 2026-10-06），那一筆的感覺留到意境的說明；讀不出來回一句話（只點了一下）。"""
    _game(request)
    try:
        glyph.read(body.get("points"))
    except glyph.GlyphError as e:
        return {"ok": False, "problem": str(e)}
    return {"ok": True}


@app.post("/api/sense_warm")
def api_sense_warm(request: Request):
    """畫布一出現就送的暖機（悟意境設計 0.2a）：只叫 Ollama 把模型載起來、不取名、不等它載完；不拿鎖、不碰狀態。"""
    game = _game(request)
    return {"ok": insight_llm.warm(game.client)}


@app.post("/api/forge_line")
def api_forge_line(request: Request, body: dict = Body(default={})):
    """煉製頁選了東西就更新說明（不算行動、不存檔）。爐裡只放了一樣時多給 picks：另一格放得進來的每一樣合不合得了，
    判斷是開爐時那一套（skillview.forge_picks）；其他時候是 None。"""
    game = _game(request)
    _art, picked = forge_args(body)
    return look(game, lambda g: {
        "line": md(g.forge_line(picked)), "picks": g.forge_picks(picked),
        "preview": g.forge_preview(picked),  # 兩格都放好：預覽卡，其餘 None、網頁畫 line
    })


@app.post("/api/smith_line")
def api_smith_line(request: Request, body: dict = Body(default={})):
    """店面打造那一頁：爐裡放了什麼就問這一爐會怎樣（不算行動、不存檔；店面獨立介面設計 6.3）。參數是客戶端寫的，一律轉成字串。"""
    game = _game(request)
    kind, main, aux = (str(body.get(key) or "") for key in ("kind", "main", "aux"))
    return look(game, lambda g: g.smith_line(kind, main or None, aux or None))


@app.get("/api/reports")
def api_reports(request: Request, id: int | None = None):
    game = _game(request)
    return look(game, lambda g: reports_view(g, id))


# ── 戰記（Joy 2026-10-29，原稱戰役話本）：決戰收場那一刻在背景寫、全服一份，戰報頁「戰記 ›」與戰記頁讀它 ──
# 介面（主機那邊照同一份寫）：{status: "ready"|"pending"|"none", title, season, battle_name, result,
#   acts: [{title, banner?, scenes: [{head, text, said?: {who, side, line}}]}], cast: [{name, side?, line}], made_at}
# 寫法、產生、存放在 tianxia/tale.py 與下面這一段：收場之後由背景執行緒（tale_round）一篇一篇寫，
# 存進資料庫旁邊的小檔 <db>-tale.sqlite（不動 SCHEMA_VERSION）。模型叫不動就存引擎自己拼的那一版（tale.plain），
# 所以「史官還在落筆」只會是「還沒輪到它寫」，不會永遠卡著。
def tale_view(battle_id: int) -> dict:
    """一場的戰記：寫好了回整篇（ready）；是決戰、收場了、還沒寫好回 pending；其餘（不是決戰、沒這場、還沒接上）回 none。"""
    store = TALES
    if store is None:
        return {"status": "none"}
    written = store.get(battle_id)
    if written is not None:
        return written.model_dump()
    return {"status": "pending"} if _tale_due(battle_id) else {"status": "none"}


def _tale_due(record_id: int) -> bool:
    """這一場該有戰記：收場的決戰，有結果（季終沒打完的 unfinished 沒有結果，不寫）。"""
    battle = open_world().ended_battle(record_id)
    return battle is not None and not battle.unfinished and bool(battle.outcome_title)


# 江湖史也點得進戰記：誰看得到（只有參戰的人，還是全服）等 Joy 定，先關著
TALES_IN_CHRONICLE = False


def tale_index(game: Game) -> list[dict]:
    """江湖史的戰記目錄（新的在前）：開關關著、或主機還沒接上都是空的。"""
    if not TALES_IN_CHRONICLE or TALES is None:
        return []
    return [{"battle_id": record_id, "title": written.battle_name, "season": written.season, "result": written.result}
            for record_id, written in TALES.listing(game.world.get_season_number())]


@app.get("/api/tale/{battle_id}")
def api_tale(request: Request, battle_id: int):
    _game(request)  # 要登入，跟戰報一樣
    return tale_view(battle_id)


# ── 戰記怎麼寫出來：全服一條背景執行緒（start_tales，main() 開），每 TALE_ROUND_SECONDS 秒看一次這一季有沒有收場了
# 卻還沒有戰記的決戰，有就寫一篇。不拿行動鎖（只讀收場的那一場與它的回合、寫旁邊的小檔），模型呼叫排在真人後面
# （佇列開著時當假人排）；省電模式下沒有真人來過就不叫，不把模型載回 VRAM（同旁白改寫）。
TALES: tale.TaleStore | None = None
TALES_CLIENT = None  # 寫戰記用的 client（main() 照設定建；測試塞假的）
TALES_STOP = threading.Event()
TALES_THREAD: threading.Thread | None = None
TALE_ROUND_SECONDS = 30.0  # 看一次的間隔（一季頂多十來場，寫完就閒著）
TALE_BUDGET_SECONDS = 180.0  # 一篇的模型預算
TALE_OWNER_KEY = "戰記"  # 佇列裡的名號（不是任何角色）


def tale_store_path() -> Path:
    db = default_path()
    return db.with_name(f"{db.stem}-tale.sqlite")


def start_tales(config, client=None) -> threading.Thread | None:
    """建 TALES（小檔不管叫不叫得動模型都建：讀的一邊才有東西可查）、開背景執行緒（daemon）。只有 main() 與測試呼叫。"""
    global TALES, TALES_CLIENT, TALES_THREAD
    TALES = tale.TaleStore(tale_store_path())
    if client is None:
        try:
            client = OllamaClient.from_config(config)
        except Exception:  # noqa: BLE001  建不起 client：照模板寫，不擋伺服器
            client = None
    TALES_CLIENT = client
    failures = _StepFailures(time.monotonic, "戰記")

    def loop() -> None:
        while not TALES_STOP.wait(TALE_ROUND_SECONDS):
            try:
                tale_round()
            except Exception as e:  # noqa: BLE001  一篇出錯不能讓整條停下來
                failures.failed(e)
            failures.tick()

    TALES_THREAD = threading.Thread(target=loop, daemon=True, name="tales")
    TALES_THREAD.start()
    return TALES_THREAD


def tale_material(world, battle) -> tale.Material | None:
    """把收場的一場決戰整理成寫戰記的料（只讀）。內容裡沒有這一場（換過內容的舊季）是 None。"""
    definition = CONTENT.battles.get(battle.battle_id)
    if definition is None or battle.record_id is None:
        return None
    return tale.gather(
        definition, battle, world.battle_rounds(battle.record_id),
        season=world.get_season_number(), side_names=battle_instance.side_names(battle, definition),
    )


def tale_round(clock: Callable[[], float] = time.time) -> int | None:
    """寫一篇（背景執行緒的一輪；測試直接叫）：這一季收場了、還沒有戰記的決戰挑最新的一場寫。回傳寫好的流水號，
    沒做事是 None。模型叫不動、寫壞就存模板版（照引擎自己那幾句），不留著讓玩家一直看「史官還在落筆」。
    呼叫端不能握著行動鎖。"""
    store = TALES
    if store is None:
        return None
    if power_save.on() and clock() - LAST_HUMAN > ONLINE_SECONDS:
        return None  # 省電模式、沒人在線：等有人來再寫
    world = open_world()
    if world.season_phase() != "running":
        return None
    season = world.get_season_number()
    done = store.done(season)
    todo = [b for b in world.season_ended_battles(season)
            if b.record_id is not None and b.record_id not in done and not b.unfinished and b.outcome_title]
    if not todo:
        return None
    battle = todo[-1]  # 最新的那一場先（玩家剛打完就在等它）
    material = tale_material(world, battle)
    if material is None:
        return None
    budget, started = TALE_BUDGET_SECONDS, _monotonic()

    def ask() -> tuple[dict, dict]:
        return tale.write(within_budget(TALES_CLIENT, budget - (_monotonic() - started)), material)

    if QUEUE is None:
        scenes, cast = ask()
    else:
        try:  # 排在真人後面（當成假人排）；排不到這一輪就算了，下一輪再寫
            scenes, cast = QUEUE.run(TALE_OWNER_KEY, ask, fallback=({}, {}), bot=True, wait=min(budget, 120))
        except Busy:
            return None
    store.put(material.record_id, tale.compose(material, scenes, cast, made_at=clock()))
    return material.record_id


# ── 見聞的「榜單」（企劃者 2026-10-14：善人、惡人、名人、宗師榜，連同武學榜、內功榜）──
# 一張榜要掃過這一季每一個角色（leaderboard.compute_boards）：二三十人在線、每個人點開都掃一次划不來，整份快取 BOARDS_TTL_SECONDS 秒，
# 全服共用一份（榜上寫的都是名號，人人看到的一樣；「你排第幾」照快取裡的整張找）。不拿行動鎖：只讀，晚幾十秒無妨。
BOARDS_TTL_SECONDS = 60.0
BOARDS_CACHE: dict = {}  # "at"：算好的時刻（time.monotonic）、"season"：哪一季、"board"：compute_boards(top=None)
BOARDS_LOCK = threading.Lock()


def boards_now(game: Game, clock: Callable[[], float] = time.monotonic) -> dict[str, list]:
    """整張榜（快取過的）：過了 BOARDS_TTL_SECONDS 或換了季才重掃；同時好幾個人點開只掃一次（BOARDS_LOCK）。"""
    season = game.world.get_season_number()
    with BOARDS_LOCK:
        cached = BOARDS_CACHE
        if cached.get("season") == season and clock() - cached.get("at", float("-inf")) < BOARDS_TTL_SECONDS:
            return cached["board"]
        board = leaderboard.compute_boards(game.content, game.world, top=None)
        BOARDS_CACHE.clear()
        BOARDS_CACHE.update(at=clock(), season=season, board=board)
        return board


DIVINE_NOTE = "歷季打出的神器原品與名將本命兵器，跨季留名"  # 榜單「神器譜」那一張的說明，待 joy 潤


@app.get("/api/boards")
def api_boards(request: Request):
    """見聞的「榜單」：七張榜的前十名，加上你不在前十名時你排第幾（leaderboard.view）；最後一張是神器譜（跨季，不排名；
    Joy 2026-10-17 從江湖史搬過來）。神器譜只讀兩張小表，不進快取：打出來、定了名馬上看得到。"""
    game = _game(request)
    book = {"id": "神器", "title": "神器譜", "note": DIVINE_NOTE, "book": game.divine_book_view()}
    return {"boards": leaderboard.view(boards_now(game), me=game.state.player.name) + [book]}


@app.get("/api/board_card")
def api_board_card(request: Request, board: str, name: str = "", season: int = 0, ref: str = ""):
    """榜單點開的唯讀卡（Joy 2026-10-22）：武學榜、內功榜那一列給 board＋name（主人的名號），照主人身上那一門畫功法卡；
    神器譜那一筆給 board=神器＋season＋ref（divine_book_view 那一筆的 ref），照原品畫裝備卡。只讀，不拿行動鎖：武學、內功照
    快取的整張榜認得是不是榜上看得到的那幾列（leaderboard.art_card），主人的存檔讀一份快照。看不到了回 {"card": null}。"""
    game = _game(request)
    if board == "神器":
        return {"card": leaderboard.gear_card(game.content, game.world, season, ref)}
    card = leaderboard.art_card(game.content, game.world, boards_now(game), board, name, me=game.state.player.name)
    return {"card": {**card, "card": md(card["card"])} if card else None}  # 功法卡的字同修練頁（menxia_view 的 owned_arts）轉成 HTML



@app.get("/api/mingtie")
def api_mingtie(request: Request):
    """見聞的「名帖匣」（Game.mingtie_view）：頭銜的榜單名次照快取的整張榜（boards_now，不拿行動鎖）。"""
    game = _game(request)
    board = boards_now(game)
    return look(game, lambda g: g.mingtie_view(board))


@app.post("/api/mingtie/{op}")
def api_mingtie_do(op: str, request: Request, body: dict = Body(default={})):
    """名帖的動作：save（定稿：筆劃、頭銜、自題一句；那一句先在鎖外審過）、report（檢舉某人的第幾版）。回傳 {mingtie, message}。"""
    game = _game(request)
    if op == "save":
        board = boards_now(game)
        motto = speech.clean(str(body.get("motto", ""))[:200])
        verdict = screen_text(game, motto, speech.MOTTO) if look(game, lambda g: g.mingtie_screen(motto)) else ""
        titles = body.get("titles")
        titles = [str(t) for t in titles] if isinstance(titles, list) else []
        msgs = act(game, lambda g: g.make_mingtie(body.get("strokes"), titles, motto, verdict, board))
    elif op == "report":
        msgs = act(game, lambda g: g.report_mingtie(str(body.get("name", "")), _int(body.get("version"), 0)))
        board = boards_now(game)
    else:
        raise HTTPException(404)
    _tell_tabs(game)
    return {"mingtie": look(game, lambda g: g.mingtie_view(board)), "message": joined(msgs)}


@app.get("/api/annals")
def api_annals(request: Request):
    """見聞的「行狀」：這一季至今記下的事（玩家傳第一批；不叫模型）。"""
    game = _game(request)
    return look(game, lambda g: g.annals_view())


@app.get("/api/xingshi")
def api_xingshi(request: Request):
    """見聞的「形勢」：這一季每天一篇的〈天下形勢〉（領地爭奪第三批 A；只讀，不叫模型——文章在背景寫，write_xingshi）。"""
    game = _game(request)
    return look(game, lambda g: g.xingshi_view())


# ── 玩家傳第二批：季末寫成《某某傳》、公開分享（企劃者 2026-10-12）──
# 寫一篇要一兩分鐘，一個請求在 trycloudflare 約 100 秒就被切斷：按「寫」只開一個背景執行緒做三段式，網頁每幾秒問一次寫好了沒。
# 伺服器重開時寫到一半的那一篇就沒了（沒存進去），網頁問的時候照「還沒寫」再按一次。

ZHUAN_JOBS: dict[tuple[str, int], float] = {}  # （名號 casefold, 季）→ 開始寫的時間
ZHUAN_LOCK = threading.Lock()
PUBLIC_URL_ENV = "TIANXIA_PUBLIC_URL"  # 分享網址的開頭；沒設就照設定的 Config.biography.public_url，再沒有就照這次請求的網址


def _zhuan_key(game: Game, season: int) -> tuple[str, int]:
    return game.state.player.name.casefold(), season


def write_zhuan(game: Game, season: int, rewrite: bool) -> bool:
    """開一個背景執行緒寫那一季的傳：A 鎖內開單 → B 鎖外請模型寫（model_call，佇列開著要排隊；預算 Config.biography.budget_seconds）
    → C 鎖內重驗再存（Game.write_biography；模型寫不出來就照規則拼）。同一篇已經在寫就不再開；開了回 True。"""
    key = _zhuan_key(game, season)
    with ZHUAN_LOCK:
        if key in ZHUAN_JOBS:
            return False
        ZHUAN_JOBS[key] = time.monotonic()

    def zhuan_job() -> None:
        try:
            with _locked(game):
                request = game.biography_request(season, rewrite)
            if request is None:
                return
            budget = game.content.config.biography.budget_seconds
            started = time.monotonic()

            def ask() -> str | None:
                return biography.write(game.client, request, budget - (time.monotonic() - started))

            text = model_call(game, ask, fallback=None, left=budget)
            if not request.verdicts:  # 關著的季、沒有人替你寫評曰：跟以前一模一樣
                with _locked(game):
                    game.write_biography(request, text, time.time())
                return
            verdicts = {job.fid: verdict_text(game, job) for job in request.verdicts}  # 寫完正文再逐條寫評曰（減法季批 7b-2）
            with _locked(game):
                game.write_biography(request, text, time.time(), verdicts=verdicts)
        except Exception:  # noqa: BLE001 — 背景執行緒：印出來就好，網頁問的時候照「還沒寫」
            traceback.print_exc()
        finally:
            with ZHUAN_LOCK:
                ZHUAN_JOBS.pop(key, None)

    threading.Thread(target=zhuan_job, name=f"zhuan-{season}", daemon=True).start()
    return True


VERDICT_OWNER = "#評曰"  # 人物評曰在佇列裡的名號尾巴：跟這個人自己的請求分開排，當假人排在真人後面


def verdict_text(game: Game, job) -> str:
    """一條人物評曰（減法季批 7b-2；zhuan_job 在鎖外叫）：請模型照他的口氣寫一句（zhuan_end.write_verdict），預算
    Config.jianfa.verdict_budget_seconds（含排隊）；佇列開著時當假人排、排在真人後面（同書信 letter_once）。寫不出來是空字串（照固定句）。"""
    jf = game.content.config.jianfa
    started = _monotonic()

    def ask() -> str:
        return zhuan_end.write_verdict(within_budget(game.client, jf.verdict_budget_seconds - (_monotonic() - started)), job, jf.verdict_chars)

    if QUEUE is None:
        return ask()
    try:
        return QUEUE.run(game.state.player.name.casefold() + VERDICT_OWNER, ask, fallback="", bot=True, wait=jf.verdict_budget_seconds)
    except (Busy, QueueTimeout):
        return ""


def public_base(request: Request) -> str:
    """分享網址的開頭（不含結尾的斜線）：環境變數 > 設定 > 這次請求的網址（走 cloudflared 時照 X-Forwarded-Proto 認 https）。"""
    fixed = os.environ.get(PUBLIC_URL_ENV) or CONTENT.config.biography.public_url
    if fixed:
        return fixed.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return f"{proto}://{request.headers.get('host') or request.url.netloc}"


def zhuan_view(game: Game, season: int, request: Request) -> dict:
    view = game.biography_view(season)
    if view is None:
        raise GameError("這一季沒有你的傳。")
    view["writing"] = _zhuan_key(game, season) in ZHUAN_JOBS
    if view.get("illustration"):  # 列傳插畫（減法季批 7b）：讀傳那一層開頭那一幅，同江湖頁的 main.zhuan；圖檔在才給網址，沒有是 None
        view["illustration_src"] = zhuan_art_src(view["illustration"])
    if view.get("code"):
        view["url"] = f"{public_base(request)}/zhuan/{view['code']}"
    return view


def _season_arg(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise GameError("哪一季？") from None


@app.get("/api/zhuan")
def api_zhuan(request: Request, season: int):
    """那一季的傳（還沒寫成時 written 是 False、can_write 說寫不寫得了；正在寫時 writing 是 True）。"""
    game = _game(request)
    return look(game, lambda g: zhuan_view(g, season, request))


@app.post("/api/zhuan/write")
def api_zhuan_write(request: Request, body: dict = Body(default={})):
    """請史官寫（或重寫一次）那一季的傳：在背景寫，馬上回目前的樣子（writing 是 True）。寫不了丟 GameError。"""
    game = _game(request)
    season, rewrite = _season_arg(body.get("season")), body.get("rewrite") is True
    if look(game, lambda g: g.biography_request(season, rewrite)) is None:
        raise GameError("這一篇現在不能再寫了。" if rewrite else "這一季還不能寫傳。")
    write_zhuan(game, season, rewrite)
    return look(game, lambda g: zhuan_view(g, season, request))


@app.post("/api/zhuan/share")
def api_zhuan_share(request: Request, body: dict = Body(default={})):
    """公開或收回那一季的傳：公開時回分享網址（不用登入的唯讀頁 /zhuan/<代碼>）。"""
    game = _game(request)
    season, public = _season_arg(body.get("season")), body.get("public") is True
    code = look(game, lambda g: g.share_biography(season, public, secrets.token_urlsafe(6)))
    if code is None:
        raise GameError("傳還沒寫成，不能分享。")
    return look(game, lambda g: zhuan_view(g, season, request))


@app.get("/zhuan/{code}")
def zhuan_page(code: str, request: Request):
    """公開的傳（不用登入、唯讀）：只認公開中的分享代碼，其餘一律 404（不說是沒有、還是收回了）。
    帶 Open Graph，LINE、FB 貼上去有預覽（題簽圖是 web/zhuan-og.png，所有的傳共用一張）。"""
    store = open_world()
    row = store.biography_by_code(code)
    if row is None:
        return HTMLResponse(zhuan_html.missing(), status_code=404)
    base = public_base(request)
    return HTMLResponse(zhuan_html.page(row, CONTENT.scenario.name, f"{base}/zhuan/{code}", f"{base}/static/zhuan-og.png",
                                        extras=zhuan_extras(store, row)))


def zhuan_extras(store, row: dict) -> dict:
    """公開頁多畫的（減法季批 7b）：那一季開著列傳為終點時，紀念印上的字（蓋了才有）與插畫的網址（第一階或用了插畫票、圖檔在才有）；
    其餘是空的（頁面一個位元組都不變）。票照那一位的錢包讀（商城關著當沒有）。"""
    number = row["season"]
    season = store.get_season() if number == store.get_season_number() else store.past_season(number)
    if season is None or not zhuan_end.on(CONTENT, season):
        return {}
    from tianxia.core.services import wallet_on  # noqa: PLC0415  錢包開著沒（核心；開發規範手冊 3.10）
    from tianxia.wallet import Wallet  # noqa: PLC0415

    purchases = Wallet(store.db).purchases(name_key(row["name"])) if wallet_on(CONTENT) else []
    got = zhuan_end.extras(CONTENT, number, row["profile"], zhuan_end.season_tickets(purchases, number), row["text"])
    out = {}
    art = zhuan_art_src(got["illustration"])
    if art:
        out["art"] = art
    if got["seal"]:
        out["seal"] = got["seal"]
    return out


@app.get("/api/map")
def api_map(request: Request, layer: str = DEFAULT_LAYER, place: str | None = None):
    """舊的輿圖（四個圖層的整張 SVG 與詳情欄）：輿圖升級之後網頁不再呼叫，留一版給還開著舊網頁的分頁（設計第九節）。"""
    game = _game(request)
    return look(game, lambda g: map_view(g, layer, place))


@app.get("/api/map/base")
def api_map_base(request: Request):
    """輿圖升級的底圖（只有紙、大區、山河、路）與地點、路、大區的清單；網頁一次載入只抓一次，疊層的 key 變了才重抓。"""
    game = _game(request)
    return look(game, map_base_view)


@app.get("/api/map/state")
def api_map_state(request: Request):
    """輿圖升級的疊層：每個地點此刻的控制方、勝算、出陣、分鐘、軍令懸賞，戰線、今天去哪裡出陣、每一週的地盤（mapdata.state）。"""
    game = _game(request)
    return look(game, lambda g: g.map_state())


@app.post("/api/travel")
def api_travel(request: Request, body: dict = Body(...)):
    """「安排前往」（步行、疾行）：出發了就回 {main, arrived: true}，畫面回江湖、場景寫路上或抵達的地點；
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
    if not refused:  # 走不成的什麼都沒變（同步而已），其他分頁不必刷新
        _play_did(game, "travel")
        _tell_tabs(game)
    out = {"main": look(game, main_view), "arrived": not refused}
    if refused:
        out["reason"] = refused[0]
        out["map"] = look(game, lambda g: map_view(g, str(body.get("layer") or DEFAULT_LAYER), target))
    return out


@app.post("/api/password")
def api_password(request: Request, body: dict = Body(...)):
    key = _account(request)
    return {"message": change_password(
        key, body.get("old", ""), body.get("new", ""), body.get("again", ""), request.cookies.get(COOKIE),
    )}


@app.get("/api/queue")
def api_queue(request: Request):
    """等模型的時候前端每 2 秒問一次：這個角色那一件前面還有幾件（正在跑的也算一件；佇列關著、或沒有在排：null）。
    只給一個數字：真人排在假人前面，所以前面的只有正在跑的與先排的真人，看不出有沒有假人。不拿行動鎖。"""
    game = _game(request)
    return {"ahead": None if QUEUE is None else QUEUE.position(game.state.player.name.casefold())}


@app.get("/api/events")
async def api_events(request: Request):
    """伺服器推送（SSE）：這個角色的分頁收「自己的東西變了（self）」與「世界變了（world）」兩種通知，收到再去抓 /api/main；
    連線上沒事時每 HEARTBEAT_SECONDS 秒一個 ping。開關關著是 404（連登入都不問），前端照舊輪詢。
    查帳號是同步的資料庫讀取，放在執行緒池裡做，不卡事件迴圈（這個函式是 async：串流要跑在事件迴圈上）。"""
    hub = HUB
    if hub is None:
        raise HTTPException(404)
    name = await run_in_threadpool(_character_name, request)
    return StreamingResponse(
        server_push.sse_stream(hub, name.casefold(), HEARTBEAT_SECONDS),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},  # 代理不能把串流攢著不送
    )


def _web_push() -> server_push.WebPush:
    push = WEB_PUSH
    if push is None:
        raise HTTPException(404)
    return push


@app.get("/api/push")
def api_push(request: Request):
    """手機通知（減法季批 9）：瀏覽器訂閱要的那一串公鑰，加上五種通知各開著沒（設定頁一種一個開關，預設全開）。開關關著 404。"""
    push = _web_push()
    off = push.store.kinds_off(_account(request))
    return {"key": push.vapid.public, "kinds": {k: k not in off for k in NOTICE_KINDS}}


@app.post("/api/push/prefs")
def api_push_prefs(request: Request, body: dict = Body(...)):
    """開或關一種通知：{kind, on}。存在這個帳號（每一台裝置一樣）。"""
    push = _web_push()
    kind = str(body.get("kind", ""))
    if kind not in NOTICE_KINDS:
        raise GameError("沒有這一種通知。")
    off = push.store.set_kind(_account(request), kind, bool(body.get("on")))
    return {"kinds": {k: k not in off for k in NOTICE_KINDS}}


@app.post("/api/push/test")
def api_push_test(request: Request, body: dict = Body(...)):
    """設定頁「傳一則測試通知」：{endpoint}。當場對這一台送一則，送不出去把原因回給畫面（{sent: false, error}）。"""
    push = _web_push()
    account_key = _account(request)
    endpoint = str(body.get("endpoint", ""))
    device = next((d for d in push.store.devices(account_key) if d["endpoint"] == endpoint), None)
    if device is None:
        return {"sent": False, "error": PUSH_NOT_HERE}
    why = push.deliver(device, NOTICE_TITLE, PUSH_TEST, tag="test")
    return {"sent": why is None, "error": why or ""}


@app.post("/api/push/subscribe")
def api_push_subscribe(request: Request, body: dict = Body(...)):
    """這台裝置開通知：{endpoint, keys: {p256dh, auth}, quiet}（瀏覽器 PushSubscription 的 JSON，多一個 quiet）。
    位址不是認得的推送服務就不收。開了先把他身上現有的事記成看過（不會一開就跳一串舊信）；不是 quiet 就送一則「開了」的通知，
    手機上當場看得到通不通（主機驗收也看這一則）。"""
    push = _web_push()
    account_key = _account(request)
    endpoint = str(body.get("endpoint", ""))
    keys = body.get("keys") if isinstance(body.get("keys"), dict) else {}
    p256dh, auth = str(keys.get("p256dh", "")), str(keys.get("auth", ""))
    if len(endpoint) > 1024 or not server_push.push_host_ok(endpoint) or not (40 <= len(p256dh) <= 200 and 8 <= len(auth) <= 64):
        raise GameError("這個瀏覽器給的通知位址不對，換一個瀏覽器試試。")  # 待 joy 潤
    push.store.add(account_key, endpoint, p256dh, auth, time.time(), CONTENT.config.web_push.max_devices)
    game = _game(request)
    with _locked(game):
        notes = current_notices(game.state, game.content, game.world.get_battle(), game.world.sortie_duels())
    NOTICE_SENT[account_key] = {n.key for n in notes}
    if not body.get("quiet"):
        threading.Thread(target=push.send, args=(account_key, NOTICE_TITLE, PUSH_WELCOME), kwargs={"tag": "welcome"}, daemon=True).start()
    return {"on": True}


@app.post("/api/push/unsubscribe")
def api_push_unsubscribe(request: Request, body: dict = Body(...)):
    """這台裝置關通知：{endpoint}。只刪得掉自己帳號的。"""
    push = _web_push()
    push.store.remove(str(body.get("endpoint", "")), _account(request))
    return {"on": False}


@app.get("/sw.js")
def service_worker():
    """手機通知的 service worker：放在根目錄，管得到整個網站（/static 底下的管不到 /）。"""
    return Response((WEB / "sw.js").read_bytes(), media_type="text/javascript", headers=NO_CACHE)


@app.get("/manifest.webmanifest")
def manifest():
    """加到主畫面用的說明檔（iPhone 要先加到主畫面才收得到通知）。"""
    return Response((WEB / "manifest.webmanifest").read_bytes(), media_type="application/manifest+json", headers=NO_CACHE)


@app.get("/api/admin")
def api_admin(request: Request):
    game = _game(request)
    if not game.is_admin():
        raise HTTPException(403)
    return look(game, admin_choices)


@app.post("/api/admin/player")
def api_admin_player(request: Request, body: dict = Body(...)):
    """管理者區「玩家個人劇情」查一個名號（Game.admin_player_choices）：他是誰、能不能發召見、能給的機緣與伏筆片段。只讀。
    名號放在 POST 的內容裡、不放在網址上。查不到回 200 加 {"refusal": …}（原因寫在表單那一行）。"""
    game = _game(request)
    if not game.is_admin():
        raise HTTPException(403)
    name = str(body.get("name", ""))
    return look(game, lambda g: g.admin_player_choices(name))


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

    console.use_utf8()  # 第一件事：cp950 編不出來的字（例：設定對不上那行開頭的 ⚠）不能把伺服器弄死
    global QUEUE, TALE_THREADS
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
    open_world().mutate(lambda st: seal.ensure_salt(st.seal))  # 玉璽碎片的密鹽（設計 5.13）：正式伺服器啟動時沒有就產生一次；測試與量表腳本不經過這裡，同樣的種子跑出同樣的結果
    print(profile_line(CONTENT, PROFILE), flush=True)  # TIANXIA_PROFILE 也是：兩個程式要用同一份設定
    warning = calendar.profile_warning(CONTENT, open_world().get_season(), open_world().season_phase())  # 這一季蓋了第一季的章、這個程式卻沒開（FB-157）；籌備中不印（FB-636）
    if warning:
        print(warning, flush=True)
    if divine.exhausted_now(open_world().divine_state(), open_world().get_season_number()):  # 新神器用完了（正式季整合 5.6）
        print(divine.EXHAUSTED, flush=True)
    QUEUE = make_queue(CONTENT.config)  # 開關關著是 None：鎖外的模型呼叫照舊直接叫
    TALE_THREADS = True  # 放手一搏的劇情回合結算後在背景補（narrate_battle）
    print(queue_line(CONTENT.config), flush=True)
    interval = CONTENT.config.world_tick_seconds
    print(scheduler_line(interval), flush=True)
    start_scheduler(interval)
    print(push_line(CONTENT.config), flush=True)
    start_push(CONTENT.config)  # 開關關著什麼都不做：HUB 是 None、/api/events 是 404
    print(web_push_line(CONTENT.config), flush=True)
    start_web_push(CONTENT.config)  # 開關關著、沒裝 cryptography 什麼都不做：WEB_PUSH 是 None
    print(narration_line(CONTENT.config), flush=True)
    start_narration(CONTENT.config)  # 減法季的開關關著只建小檔、不開執行緒
    start_tales(CONTENT.config)  # 戰記：小檔一定建，執行緒照樣開（叫不動模型就寫模板版）
    if args.lan:
        print("已開放區網連線：同一個網路裡的裝置都連得到。", flush=True)
    # timeout_graceful_shutdown：uvicorn 關機時會等進行中的回應收完，而 SSE 串流永遠不會自己收完，Ctrl+C 一下就卡住
    # （log_level 是 warning，連「等連線關閉」那行都看不到）。3 秒後取消它們，sse_stream 的 finally 會退訂（預檢 F7）
    uvicorn.run(
        app, host="0.0.0.0" if args.lan else "127.0.0.1", port=args.port, log_level="warning",
        timeout_graceful_shutdown=3,
    )


if __name__ == "__main__":
    main()
