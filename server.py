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
- 三段式的鎖外那一段（A 鎖內開單 → B 鎖外叫模型 → C 鎖內重驗再套用）與放鎖之後才開的背景寫字，全部拆包第 69 批搬進各包 `routes.py`，這個檔只留
  框架（`model_call`、`within_budget`、`_open_request`、佇列）、分派（`choose`）、歸核心的那幾條（`prepare_fight`、`answer_event`、`write_flavor`）與給測試叫的一行包裝；
  各包經 `outlock` 掛鉤接到 `api_do`（`OUTLOCK_OPS`）與 `act`、`act_look`（`OUTLOCK_JOBS`）。
- 人物對話照舊在行動鎖外生成（人物情誼包的 `prepare_dialogue`），模型的 9~10 秒不會卡住全服。
- 開爐的首次取名也在行動鎖外（煉製包的 `prepare_forge`／`forge`），整段有時間預算（`Config.naming_budget_seconds`），
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
import functools
import hashlib
import json
import os
import re
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
from llm_queue import Busy, LlmQueue, QueueTimeout
from tianxia.features.battle import instance as battle_instance
from tianxia import flavor, battlelog, calendar
from tianxia.features.companions import companion_agent
from tianxia.features.craft import create
from tianxia import divine
from tianxia.features.sense import epiphany
from tianxia import event_llm, fight_llm, gender
from tianxia.features.sense import insight_llm
from tianxia import leaderboard
from tianxia.features.companions import letters  # noqa: F401  server 本身不讀，留著是載入先後
from tianxia import might, naming, narration, ollama_client, power_save, precise
from tianxia.features.seal import seal
from tianxia import server_bots, speech, team, training, treasures, weekcard
from tianxia.features.companions import talk_log
from tianxia.accounts import NAME_TAKEN, PASSWORDS_DIFFER, SESSION_SECONDS, AccountError, AccountStore, SessionStore, normalize
from tianxia.content import env_profile, load_content, profile_line, serving_profile
from tianxia.characters import name_key, open_characters
from tianxia.database import default_path, open_database
from tianxia.flavor import FlavorJob
from tianxia.engine import FIGHT_GONE_LINES, FREE_TEXT_OPTION, PAUSED_TEXT, SAY_OPTION, TEXT_TALKS, Game, Refused
from tianxia.core import features as features_core  # 功能包：殼照 FEATURES 掛管理者工具與路由（開發規範手冊 3.1）
from tianxia.core import identity_base  # identity（帳號與客服第 201 批）：開著時擋客服與 id: 開頭的名號（name_taken）
from tianxia.core import omen_base  # 門下頁的伏筆物品：核心的查詢服務（全部拆包第 40 批，原本經舊名 foreshadow 讀軍情包）
from tianxia.features.map import views as map_views  # 輿圖的 /api/map 資料與底圖快取：全部拆包第 49 批搬進輿圖包（殼留同一個物件的別名）  # 殼留薄包裝：`map_view` 要 `md`（第 49 批 PM 認定第 10 條）
from tianxia.features.notify import routes as notify_routes  # 手機通知：全部拆包第 53 批搬進手機通知包；殼留 state 與 4 個一行薄包裝（main 印一行、same_behavior 與測試叫）
from tianxia.features.battle import routes as battle_routes  # 鎖外工作（全部拆包第 69 批）：本體在各包 routes.py，殼留一行包裝給測試與 same_behavior 叫（同 tale_routes）
from tianxia.features.bout import routes as bout_routes
from tianxia.features.companions import routes as companions_routes
from tianxia.features.craft import routes as craft_routes
from tianxia.features.feast import routes as feast_routes
from tianxia.features.peers import routes as peers_routes
from tianxia.features.sense import routes as sense_routes
from tianxia.features.figure_acts import routes as figure_acts_routes
from tianxia.features.tavern import routes as tavern_routes
from tianxia.features.territory_acts import routes as territory_acts_routes
from tianxia.features.zhuan import routes as zhuan_routes
from tianxia.features.socialize import intro as socialize_intro  # 人物簡介：第二輪第 83 批搬進交友包
from tianxia.features.tale import routes as tale_routes  # 戰記：全部拆包第 52 批搬進戰記包；殼留 state 與 8 個一行薄包裝（act、look、main_view 原位叫）
from tianxia.models import FREE_TEXT_MAX
from tianxia.journal import CSS as JOURNAL_CSS
from tianxia.sqlite_world import open_world
from tianxia.ollama_client import OllamaClient
from tianxia.playlog import FIGURE_TALK, FREE_TEXT, PlayLog, button_of

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
    art = {
        "kind": got["kind"], "src": f"/static/img/{got['path']}.webp", "title": got["title"], "sub": got["sub"],
        "time": when if got["kind"] == "place" else "", "head": md(got["head"]),
    }
    if got.get("mood"):  # 地點會變樣：戰火、淪陷、饑荒、重建的地點，畫換色調（網頁的 mood-<kind>）；太平沒有這個鍵
        art["mood"] = got["mood"]
    return art


def story_cards(game: Game) -> list[dict]:
    """特殊事件的跳顯框（Game.story_card_view）：圖檔真的在 web/img/ 才給 src（同 scene_art），內文轉成 HTML。"""
    out = []
    for card in game.story_card_view():
        image = card.pop("image")
        card["src"] = f"/static/img/{image}.webp" if image and (WEB / "img" / f"{image}.webp").is_file() else None
        card["text"] = md(card["text"])
        out.append(card)
    return out


def figure_face(cid: str) -> str | None:
    """大勢人物的半身像（介面重整第一批圖，web/img/figures/full/<人物 id>.webp，去背）：檔案在才給網址，沒有是 None（網頁畫名字的第一個字）。"""
    return f"/static/img/figures/full/{cid}.webp" if cid and (WEB / "img" / "figures" / "full" / f"{cid}.webp").is_file() else None


# 人物簡介搬進交友包 tianxia/features/socialize/intro.py（第二輪第 83 批）；殼留一行別名（測試與 same_behavior 讀 server.FIGURE_INTROS，同一個物件）
FIGURE_INTROS = socialize_intro.FIGURE_INTROS


def horse_art() -> list[str]:
    """web/ 裡真的有的馬圖（web/horse-<鍵>.webp，鍵見 mounts.COAT_ART、STEED_ART）：網頁只對這些鍵放圖，其餘照舊畫色塊。"""
    return sorted(path.stem.removeprefix("horse-") for path in WEB.glob("horse-*.webp"))
PROFILE = serving_profile() if __name__ == "__main__" else env_profile()  # 設定覆寫檔（TIANXIA_PROFILE，例如 week7）；當主程式跑、沒帶時套 season21；被 import（測試）沒帶＝預設內容。run_bots.py、scripts/set_password.py 讀同一個
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
    return _md(text or "")


@functools.lru_cache(maxsize=1024)
def _md(text: str) -> str:
    """同一段文字轉出來的 HTML 一樣：狀態列、主線、場景每次畫面都轉一次，多半跟上一次一字不差（主機實測，2026-11-03）。"""
    return _MD.render(text)


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
    return open_characters().exists(name) or account_store().owner_of(name) is not None or name.casefold() in reserved \
        or identity_base.blocked_name(name, CONTENT)  # identity：帳號綁定開著才擋（關著回假，行為不變）


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
# 這次請求的登入 token（帳號與客服第 207 批）：main_view 的 admin 格拿不到 request，照它問 identity_base.admin_session_ok。
# _server_timing 每個請求一開始設（端點、執行緒池裡的都看得到），_start_session 開了新 token 再設一次（登入回應的 _entry 不另經 _game）。
# identity 關著時 admin_session_ok 一律回真、不讀它。
SESSION_TOKEN: contextvars.ContextVar[str | None] = contextvars.ContextVar("session_token", default=None)


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


# ── 每個請求的時間花在哪裡（Server-Timing 回應標頭；Joy 2026-11-03「探索選完、果出來前就等 5 秒」，雲端量不到，主機用 curl -I
# 或瀏覽器開發者工具看）：等鎖幾次、共等幾毫秒（lock）、拿著鎖多久（hold，含 reload 重讀角色、view 重組畫面）、量表那一筆小交易
# （log）、整個請求（total）。只有數字，玩家看不到；一個請求一份（_server_timing 放進來），請求以外（排程、背景執行緒）的不記。
TIMING: contextvars.ContextVar[dict[str, float] | None] = contextvars.ContextVar("timing", default=None)
TIMING_KEYS = ("lock", "reload", "view", "hold", "log")


def _timed(key: str, seconds: float, count: bool = False) -> None:
    got = TIMING.get()
    if got is None:
        return
    got[key] = got.get(key, 0.0) + seconds
    if count:
        got[f"{key}_n"] = got.get(f"{key}_n", 0.0) + 1


def server_timing(got: dict[str, float], total: float) -> str:
    """Server-Timing 標頭的值（毫秒，一位小數）：沒記到的那一樣不寫；等鎖另寫次數。"""
    parts = []
    for key in TIMING_KEYS:
        if key in got:
            desc = f';desc="n={int(got[key + "_n"])}"' if f"{key}_n" in got else ""
            parts.append(f"{key}{desc};dur={got[key] * 1000:.1f}")
    parts.append(f"total;dur={total * 1000:.1f}")
    return ", ".join(parts)


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
    asked, got = time.perf_counter(), None
    try:
        with game.world.action_lock(), _model_guard(game):
            got = time.perf_counter()
            _timed("lock", got - asked, count=True)  # 等鎖（Server-Timing，見 TIMING）
            _reload(game)
            _timed("reload", time.perf_counter() - got)
            game.set_move_mode(MOVE_MODE.get())  # 這次請求選的走法（見 MOVE_MODE）：之後的選單與 choose() 都照它
            yield
            jobs = game.take_flavor_jobs()  # 動作丟例外就不拿：那一下整筆撤回，下一次拿鎖 reset_model_budget 會清掉
    finally:
        if got is not None:
            _timed("hold", time.perf_counter() - got)  # 拿著鎖多久（含重讀、動作、重組畫面、存檔）
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
    started = time.perf_counter()
    log = PlayLog(game.world.db)
    log.press(owner, season, day, button)
    if first is not None:
        log.first(owner, season, first, day, game.now)
    _timed("log", time.perf_counter() - started)


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
        said, liked = talk_log.snapshot(game.state), talk_log.affinity_before(game.state)  # 往來紀錄：動作前後比，多出來的那幾輪記進小檔
        msgs = action(game)
        _log_talk(game, said, liked)
        open_characters().save(game.state)
        waiting = _outlock_waiting(game)
    _outlock_start(game, waiting)
    return msgs


def _outlock_waiting(game: Game) -> list[tuple[features_core.OutlockJob, object]]:
    """放鎖之後要開的背景寫字（各包 routes.py 的 outlock 掛鉤；OUTLOCK_JOBS 照 features_core.OUTLOCK_ORDER 排）：行動鎖內照順序問一輪，有的記下來。問的都只讀、不叫模型。"""
    return [(job, got) for job in OUTLOCK_JOBS if (got := job.waiting(game))]


def _outlock_start(game: Game, waiting: list[tuple[features_core.OutlockJob, object]]) -> None:
    """鎖放掉之後照順序開（_outlock_waiting 問到的那幾條）。呼叫端不能握著行動鎖。"""
    for job, got in waiting:
        job.start(game, got)


def _tales_waiting(game: Game) -> bool:
    return tale_routes._tales_waiting(sys.modules[__name__], game)


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
        waiting = _outlock_waiting(game) if failure is None else []
    if failure is not None:
        raise failure
    _outlock_start(game, waiting)
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


def web_push_line(config) -> str:
    return notify_routes.web_push_line(sys.modules[__name__], config)


def start_web_push(config, post=None) -> server_push.WebPush | None:
    """看守與訂閱的本體在 tianxia/features/notify/routes.py（全部拆包第 53 批）；main() 經 features_core.start_threads 開、測試直接叫這一行。"""
    return notify_routes.start_web_push(sys.modules[__name__], config, post)


def _notice_keys(game: Game, account_key: str, now: float) -> tuple[list, bool]:
    return notify_routes._notice_keys(sys.modules[__name__], game, account_key, now)


def notice_round(clock: Callable[[], float] = time.time) -> int:
    return notify_routes.notice_round(sys.modules[__name__], clock)


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


TALK_LOG: talk_log.TalkLogStore | None = None  # 往來紀錄的小檔（<db>-talk.sqlite）；第一次用到才開（talk_store）


# 小檔的鎖外包裝與 act 前後那兩行留在殼：after_action 拿不到動作前的那一份
def talk_store() -> talk_log.TalkLogStore:
    """往來紀錄的小檔：跟著現在的資料庫（TIANXIA_DB）走；換了資料庫（測試）就重開一份。"""
    global TALK_LOG
    db = default_path()
    path = db.with_name(f"{db.stem}-talk.sqlite")
    if TALK_LOG is None or TALK_LOG.path != path:
        TALK_LOG = talk_log.TalkLogStore(path)
    return TALK_LOG


def _log_talk(game: Game, before: dict[str, int], liked: dict[str, int]) -> None:
    """這一下多談的那幾輪記進往來紀錄（行動鎖裡叫）。寫不進去不擋動作：紀錄只是給人看的。假人不記。"""
    s = game.state
    if s.player.bot is not None:
        return
    lines = talk_log.new_lines(s, before)
    if not lines:
        return
    loc = game.content.locations.get(s.player.location)
    place = loc.name if loc is not None else ""
    stamp = game.stamp(s.world.time)
    rows = [{"figure": cid, "at": s.world.time, "stamp": stamp, "place": place, "role": role, "text": text,
             "affinity": (liked if role == "user" else s.player.affinities).get(cid, 0)} for cid, role, text in lines]
    try:
        talk_store().add(name_key(s.player.name), s.player.season_number, rows)
    except Exception:  # noqa: BLE001  小檔寫不進去（磁碟、鎖）：這一句不記，遊戲照走
        traceback.print_exc()


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
    return companions_routes.prepare_dialogue(sys.modules[__name__], game, option_id, text)


def say(game: Game, text: str, option: str = SAY_OPTION) -> list[str] | None:
    return companions_routes.say(sys.modules[__name__], game, text, option)


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
    return craft_routes.prepare_forge(sys.modules[__name__], game, art_id, insight_ids)


def prepare_peer(game: Game, name: str, action: str, params: dict) -> tuple[str | None, str] | None:
    return peers_routes.prepare_peer(sys.modules[__name__], game, name, action, params)


SCREEN_BUDGET_SECONDS = 12.0  # 審一句話（挑釁、名帖自題）最多等模型幾秒：叫不動就只看字表照送


# 玩家互動、探索兩包都用，留在殼
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
    return peers_routes.screen_peer(sys.modules[__name__], game, name, action, params)


def forge(game: Game, art_id: str | None, insight_ids: list[str]) -> list[str] | None:
    return craft_routes.forge(sys.modules[__name__], game, art_id, insight_ids)


EPIPHANY_THINK = f"{epiphany.OPTION}:{epiphany.THINK}"
EPIPHANY_OWN = f"{epiphany.OPTION}:{epiphany.OWN}"  # 自己取名：/api/choose 帶 text 送上來（web 的 own-name-form）
BUSY_EPIPHANY = "還在想名字，稍等。"


def epiphany_think(game: Game) -> list[str] | None:
    return sense_routes.epiphany_think(sys.modules[__name__], game)


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
    return battle_routes.battle_text(sys.modules[__name__], game, text)


# 決戰放手一搏的劇情：本體在 tianxia/features/tale/routes.py（全部拆包第 52 批）；state 留殼，包照 shell.<名字> 當下讀寫。
TALE_LOCK = threading.Lock()
TALE_RUNNING = False
TALE_OWNER = "§說書"
TALE_THREADS = False  # main() 打開：伺服器真的在跑才開背景執行緒寫劇情（測試直接叫 narrate_once，不留執行緒在背景碰資料庫）


def narrate_battle(game: Game) -> bool:
    return tale_routes.narrate_battle(sys.modules[__name__], game)


def narrate_once(game: Game) -> int | None:
    return tale_routes.narrate_once(sys.modules[__name__], game)


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


def letter_once(game: Game) -> bool:
    return companions_routes.letter_once(sys.modules[__name__], game)


def yuedan_once(game: Game) -> bool:
    return figure_acts_routes.yuedan_once(sys.modules[__name__], game)


def _xingshi_waiting(game: Game) -> bool:
    return territory_acts_routes._xingshi_waiting(sys.modules[__name__], game)


def xingshi_once(game: Game) -> bool:
    return territory_acts_routes.xingshi_once(sys.modules[__name__], game)


def feast_text(game: Game, text: str) -> list[str]:
    return feast_routes.feast_text(sys.modules[__name__], game, text)


def persuade_text(game: Game, errand_id: str, text: str) -> list[str]:
    return companions_routes.persuade_text(sys.modules[__name__], game, errand_id, text)


def crowd_once(game: Game) -> bool:
    return bout_routes.crowd_once(sys.modules[__name__], game)


def chatter_once(game: Game) -> bool:
    return tavern_routes.chatter_once(sys.modules[__name__], game)


def duel_text(game: Game, text: str) -> list[str]:
    return bout_routes.duel_text(sys.modules[__name__], game, text)


def create_reread(game: Game, body: dict) -> list[str]:
    return craft_routes.create_reread(sys.modules[__name__], game, body)


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
    started = time.perf_counter()
    try:
        with game.phase_memo():  # 這一次建構裡「籌備中嗎」只讀一次共用狀態（見 Game.phase_memo）
            return _main_view_body(game)
    finally:
        _timed("view", time.perf_counter() - started)


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
    some = features_core.slot_some

    def free_text(ctx, frame) -> dict:
        return {
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
        }

    def journal(ctx, frame) -> dict:
        return {
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
        }

    def orders_row(ctx, frame) -> dict:
        frame.orders = game.orders_view()  # 第一季：自己陣營的本週軍令（計畫 T6；散人、別陣營、開關關著時都沒有這個鍵）
        return {"orders": frame.orders} if frame.orders else {}

    def rumor_layers(ctx, frame) -> dict:
        layers = game.rumor_layers()  # 第一季：見聞頁的傳聞分四層（開關關著時不送，頁面照舊畫 rumors 那一條清單）
        return {} if layers is None else {"rumor_layers": [{**layer, "body": md(layer["body"])} for layer in layers]}

    def season_row(ctx, frame) -> dict:
        result = game.season_result()  # 第一季休季：江湖頁最上面的結算卡（計畫 T9；開關關著、進行中都不送）
        return {} if result is None else {"season_result": {
            **{key: value for key, value in result.items() if key != "ending"}, "text": md(result["text"]),
            "timeline": [{**row, "text": md(row["text"])} for row in result["timeline"]],
        }}

    # 殼的格（照 core/features.py 的 STATUS_ORDER["main"] 排進去，包的格在各包的 status_slots；全部拆包第 66 批，鍵的先後與叫的先後都算行為）
    core = {
        "screen": lambda ctx, frame: {
            "status": status,
            "quest": quest,
            "scene": scene,
            "art": scene_art(game, status),  # 場景卡上面那張圖（減法季批 8）：事件插圖、人物像或地點的圖；沒有圖檔是 None、網頁一字不變
            "options": [o.model_dump() for o in options],
        },
        "modes": lambda ctx, frame: {
            # 一類一顆開著（正式季整合第二章）：應召畫成行動列上面一條金框橫幅（設計 9.1 第 1 組乙），不收在「此地還能做」
            "precise": precise.on(game.content, game.state.world),
            # 城裡操練與城外練功（新手引導重做，tianxia/training.py）：練功從探索三選一拿出來，在行動列自成一格
            "training": training.on(game.content, game.state.world),
        },
        # 行動列底下那幾行（explain-1）：探索、遊歷、交友、求見這一下會怎樣（選項 id → 一句；序章裡是空的）
        "action_notes": lambda ctx, frame: {"action_notes": game.action_notes(o.id for o in options)},
        "free_text": free_text,
        "journal": journal,
        "news": lambda ctx, frame: {
            "bulletin": [md(text) for text in game.bulletin()],  # 江湖頁那排小標「大事」點開的本週大事（新的在前）；開關關著是空的
            "trends": md(game.trends_text()),
            "rumors": md(game.rumors_text()),
            "chronicle": md(game.chronicle_text()),
        },
        "admin": lambda ctx, frame: {
            # 第 207 批：identity 開著時名單上的人還要這次是密碼登入、staff_hours 內驗過（關著 admin_session_ok 一律回真，原樣）
            "admin": game.is_admin() and identity_base.admin_session_ok(CONTENT, SESSION_TOKEN.get(), time.time),
            "paused": game.paused_minutes(),  # 賽季時鐘停了幾分鐘；沒暫停是 None（設定頁的「暫停／繼續」）
        },
        "horse_art": lambda ctx, frame: {"horse_art": horse_art()},  # 馬市與修練頁坐騎那一列：真的有圖檔的那幾個鍵，其餘照舊畫色塊
        # 伺服器推送（線上架構設計 5.3）：頁面照 push 決定開不開 /api/events（開著時平常 60 秒才輪詢一次、有通知才刷新），
        # push_spread 是收到「世界變了」之後各分頁重抓畫面要攤開的秒數（預檢 F3：全服同時重抓會在同一把行動鎖上排隊）
        "push": lambda ctx, frame: {"push": HUB is not None, "push_spread": game.content.config.push_world_min_seconds},
        "shop": lambda ctx, frame: some("shop", game.shop_view([o.id for o in options])),  # 店面（店面獨立介面設計 6.1）：開關開著、店開著、鐵匠鋪那一串是眼前的選單才有
        "prep": lambda ctx, frame: some("prep", game.season_prep_view()),  # 開季準備卡（企劃者 2026-11-05）：挑成長配比、識海；做完才能做別的事。沒有要準備的沒有這個鍵
        # 功能包的狀態（FEATURES 的 status，照清單的順序；開發規範手冊 3.3）：商城的入口 mall（齒輪旁的錠子鈕＋餘額、底部第六格）；關著沒有這個鍵
        "features": lambda ctx, frame: game.feature_status(),
        # 第一季濃縮版才有：江湖頁的三條戰況（開關關著時不送，頁面照舊）
        "fronts": lambda ctx, frame: {"fronts": status["fronts"]} if "fronts" in status else {},
        "orders": orders_row,
        # 減法季批 1（整合設計 6.1、3.4）：江湖頁最上面的本週卡（主題、你這一步）；序章裡、休季沒有這個鍵（三方卡是陣營包的 sides_card 那一格）
        "week_card": lambda ctx, frame: some("week_card", weekcard.week_card(game, status, frame.orders)),
        "event_opts": lambda ctx, frame: some("event_opts", game.event_option_view()),  # 事件選項只留動作（整合設計 6.4）：選項 id → 動作、圖示、沒把握時的心裡話；沒有事件沒有這個鍵
        "rumor_layers": rumor_layers,
        "place_state": lambda ctx, frame: some("place_state", game.place_state_view()),  # 地點會變樣（世界活起來第二批）：此刻所在地的樣子；太平沒有這個鍵
        "season_result": season_row,
    }
    return features_core.status_run("main", core, features_core.MainFrame(status, options, card, {}, sys.modules[__name__]), game)


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
            {"id": item.id, "name": item.name, "count": n} for item, n in omen_base.held_items(game.state, game.content)
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


# 輿圖的底圖快取與 map_base_view、map_view 搬進輿圖包 tianxia/features/map/views.py（全部拆包第 49 批）；這裡留同一個物件的別名
MAP_BASE = map_views.MAP_BASE  # 輿圖升級的底圖快取（測試 server.MAP_BASE.clear()）
MAP_BASE_KEEP = map_views.MAP_BASE_KEEP
map_base_view = map_views.map_base_view


def map_view(game: Game, layer: str, selected: str | None) -> dict:
    """舊的輿圖（/api/map）與 /api/travel 走不成時帶的 map：資料在輿圖包 views.map_view，這裡只把殼的 md 帶進去。"""
    return map_views.map_view(game, layer, selected, md)


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
        # 第 209 批（企劃者 2026-11-09「2 選 A」）：identity 開著時全體密碼至少 12 字（不看名單：註冊頁試不出名單）；關著 strict 一律假
        strict = identity_base.on(CONTENT)
        account_store().register(login_name, password, strict=strict)  # 自己是一筆交易；不另外包一層：scrypt 很慢，不能握著寫入權算
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
        store = account_store()
        strict = identity_base.on(CONTENT)  # 第 209 批：identity 開著時全體新密碼至少 12 字（不看名單）；關著一律假
        store.change_password(account_key, old, new, keep, strict=strict)  # 同上：自己是一筆交易，慢的雜湊不在交易裡算
    except AccountError as exc:
        return str(exc)
    return "密碼已更新。"


# ── HTTP ──────────────────────────────────────────

app = FastAPI(title="天下大勢", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def _server_timing(request: Request, call_next):
    """/api/ 的回應帶 Server-Timing（見 TIMING）。推送的長連線（/api/events）不包：那是串流，量總時間沒有意義。"""
    SESSION_TOKEN.set(request.cookies.get(COOKIE))  # 第 207 批：main_view 的 admin 格照它問（見 SESSION_TOKEN）
    path = request.url.path
    if not path.startswith("/api/") or path == "/api/events":
        return await call_next(request)
    got: dict[str, float] = {}
    token = TIMING.set(got)  # 端點在執行緒池裡跑時拿到的是複製的 context，裡面是同一個 dict：記的會回到這裡
    started = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        TIMING.reset(token)
    response.headers["Server-Timing"] = server_timing(got, time.perf_counter() - started)
    return response


# 帳號與客服第 213 批（設計第三節「CSP 標頭另開小批」）：只准從自己這裡與 Turnstile（challenges.cloudflare.com）載程式，
# 不准 inline 的程式（<script> 不帶 src、on*= 屬性、javascript:）、不准 <object>、不准 <base>。不是開關：整站都有
# 第 209 批（設計第七節「只加一處 middleware」）：frame-ancestors 'none'——誰都不准把我們的頁（含公開頁 /zhuan、/zhanji）嵌進 iframe
# （我們自己嵌 Turnstile 的 iframe 不受這條影響）。style-src、img-src、default-src 只掃不加（數字在第 209 批的回報）
CSP = "script-src 'self' https://challenges.cloudflare.com; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
# 同一處多三個標頭：HSTS 一年含子網域（不加 preload）、不把完整網址帶給別的網站、不准瀏覽器猜檔案類型
SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Content-Type-Options": "nosniff",
}


@app.middleware("http")
async def _content_security_policy(request: Request, call_next):
    """每個回應帶 CSP 與 SECURITY_HEADERS（頁、API、靜態檔、404、400 都是；500 由最外層回、不經這裡）。"""
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CSP
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value
    return response


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


def _start_session(request: Request, response: Response, account_key: str, method: str = "password") -> str:
    """開登入狀態、回 token。identity 開著（帳號與客服第 204 批；設計第七節 server.py 那一列）：帳號鍵換成帳號自己的鍵（補設過密碼的帳號
    用帳號名登入也是 id:<n>），這次用哪一種登入（method：password、line、google、email、phone）與時間記進旁檔；關著一個字不變。"""
    identity_on = identity_base.on(CONTENT)
    if identity_on:
        account = account_store().get(account_key)
        account_key = account.key if account is not None else account_key
    token = SESSIONS.create(account_key)
    SESSION_TOKEN.set(token)  # 第 207 批：登入回應的 _entry 照這個新 token 算 admin 格（見 SESSION_TOKEN）
    _warm_model()
    response.set_cookie(
        COOKIE, token, httponly=True, samesite="lax", max_age=SESSION_SECONDS, secure=cookie_secure(request),
    )
    if identity_on:
        identity_base.record_session(token, method, time.time())
    return token


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


def _web_stamp() -> tuple:
    """web/ 底下每個檔的修改時間：主機只 pull、沒重開伺服器時，頁面上的 ?v= 也要跟著換（2026-11-07 對話告辭急修上線後，
    頁面還是舊的 ?v=，Joy 的手機一直拿舊檔）。"""
    return tuple(sorted((e.name, e.stat().st_mtime_ns) for e in os.scandir(WEB) if e.is_file()))


def _build_page() -> str:
    return versioned_page(features_core.with_scripts((WEB / "index.html").read_bytes().decode("utf-8")), asset_version)


# 啟動時算一次；index.html 指到 web/ 裡沒有的檔，這裡就丟例外。之後 web/ 有檔換了（pull 了沒重開）就重算一次
PAGE = _build_page()
_PAGE_STAMP = _web_stamp()


def current_page() -> str:
    global PAGE, _PAGE_STAMP
    stamp = _web_stamp()
    if stamp != _PAGE_STAMP:
        PAGE, _PAGE_STAMP = _build_page(), stamp
    return PAGE
NO_CACHE = {"Cache-Control": "no-cache"}  # 每次都向伺服器確認（有 ETag，沒變就是 304）；不用 immutable：開發時改了檔沒重開，會被瀏覽器釘死


LONG_CACHE = "max-age=31536000, immutable"
NEVER_LONG_CACHED = {"index.html", "sw.js"}  # 這兩支網址不能換：釘住了就更不了版


def cached_for_good(path: str, query: bytes) -> bool:
    """線上（設了 TIANXIA_PUBLIC_URL）而且 ?v= 等於那個檔現在的內容雜湊。雜湊每次當場算：改了檔沒重開，舊網址對不上就照舊 no-cache，
    蓋上 immutable 的回應內容一定等於網址上的雜湊。「對不上就 no-cache」只對真的打到這裡的請求成立：手機與邊緣存了 immutable 的不會再問，
    所以設了這個環境變數的伺服器，改 web/ 一定要重開，PAGE 才換新網址。"""
    if not os.environ.get(PUBLIC_URL_ENV) or path.lower() in NEVER_LONG_CACHED or not query.startswith(b"v="):
        return False
    return query == b"v=" + content_version((WEB / path).read_bytes()).encode()


class WebFiles(StaticFiles):
    """/static 的回應都標明快取：線上的版本網址長快取（`cached_for_good`），其餘 no-cache；不然瀏覽器會用啟發式快取，更版後留著舊檔好幾個小時。"""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        long_cache = await run_in_threadpool(cached_for_good, path, scope.get("query_string", b""))
        response.headers["Cache-Control"] = LONG_CACHE if long_cache else "no-cache"
        return response


@app.get("/")
def index():
    return HTMLResponse(current_page(), headers=NO_CACHE)


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
    out = {"stage": "login"} if key is None else _entry(key)
    if identity_base.on(CONTENT):  # identity（帳號與客服第 202 批）：開著才帶旗標，web/identity.js 沒旗標不問 /api/identity/gate；關著原樣
        out["identity"] = True
    return out


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
# 全部拆包第 68 批照包分：功能包的在各包 routes.py 的 main_actions（開發規範手冊 3.3；殼照 FEATURES 接），原位只留本體還在 Game 的這幾條。表的先後照寫死的這一張（action_table）。
MAIN_ACTION_ORDER = (
    "seclude", "smith_forge", "smith_sell", "smith_upgrade", "smith_furnace", "donate", "tavern", "anonymous", "gender", "story_seen",
    "letter_read", "letter_decline", "hints_off", "skip_tutorial", "view_map", "view_orders", "view_tab", "guide_ack", "allocate", "growth",
    "newbie_drifter", "pill", "checkin", "conquest_letter", "seal_use", "sortie_go", "sortie_answer", "sortie_join", "outing", "jieyi_leave",
)
MAIN_ACTIONS = features_core.action_table(MAIN_ACTION_ORDER, {
    "anonymous": lambda g, b: g.set_anonymous(bool(b.get("value"))),
    "gender": lambda g, b: g.set_gender(str(b.get("value", ""))),  # 設定頁：還沒選過性別的舊角色選一次（PM 2026-10-12）
    # 五項屬性的季的成長配比（屬性與跨季架構 v2 3.1）：preset 是五套之一或 custom（custom 帶 split：鍵 → 每級幾點）
    "growth": lambda g, b: g.pick_growth(str(b.get("preset", "")), b.get("split") if isinstance(b.get("split"), dict) else None),
    "pill": lambda g, b: g.take_stamina_pill(),  # 狀態列體力條上的「丹」：吃一顆回體丹（企劃者 2026-10-07 內測贈送）
}, features_core.main_actions(sys.modules[__name__]))
OUTLOCK_OPS = features_core.outlock_ops(sys.modules[__name__])  # /api/do/{op} 先接走的鎖外三段式（各包 routes.py 的 outlock 掛鉤；api_do 排在管理者工具之後、MAIN_ACTIONS 之前）
OUTLOCK_JOBS = features_core.outlock_jobs(sys.modules[__name__])  # 放鎖之後要開的背景寫字（各包 routes.py 的 outlock 掛鉤；act、act_look 照這張問與開）
# 賽季時鐘暫停中也照做的畫面設定（不推任何東西、不碰別人）：匿名、不再提示、略過引導、打開輿圖（頁面靠它載入輿圖）、軍令卡出現（入伍段第一步，
# 只動自己的引導；被擋下的話網頁已經記成「送過了」，這個工作階段不會再送）、對話框的「知道了」
PAUSE_OK_ACTIONS = frozenset({"anonymous", "gender", "hints_off", "story_seen", "skip_tutorial", "view_map", "view_orders", "guide_ack"})
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
        # 第 207 批：identity 開著時還要這次是密碼登入、staff_hours 內驗過；不夠的跟不是管理者同一句（關著 admin_session_ok 一律回真）
        if not game.is_admin() or not identity_base.admin_session_ok(CONTENT, request.cookies.get(COOKIE), time.time):
            raise GameError("只有管理者能這麼做。")
        msgs = act(game, lambda g: tool.run(g, body), paused_ok=tool.paused_ok)  # 商城：帳跟季無關，暫停中也做得了
    elif op in OUTLOCK_OPS:  # 鎖外的三段式（各包 routes.py 的 outlock 掛鉤）：A、C 段自己拿鎖，B 段叫模型不握鎖，所以不包在 act 裡
        msgs = OUTLOCK_OPS[op](game, body)
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
    return craft_routes.forge_args(sys.modules[__name__], body)


def _int_of(value) -> int:
    """網頁送來的一個整數（裝意境的第幾格）：不是整數、負的一律當 0。"""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _id_list(value) -> list[str]:
    """網頁送來的一串 id：只收字串串列，其他（字串、數字、物件）一律當空的。"""
    return [str(v) for v in value if isinstance(v, str)] if isinstance(value, list) else []


# 全部拆包第 68 批照包分：功能包的在各包 routes.py 的 menxia_actions（殼照 FEATURES 接），原位只留療傷（本體還在 Game）；開爐那一條第 69 批進煉製包。表的先後照寫死的這一張（action_table）。
MENXIA_ACTION_ORDER = (
    "practice", "heal", "forge", "switch", "slot", "unslot", "create_begin", "create_pose", "create_back", "create_name", "create_cancel", "create_reroll",
    "ascend_dismiss", "cultivate", "melt", "melt_insight", "melt_many", "name", "name_divine", "bind_art", "join", "leave", "release",
    "wield", "dismantle", "feed", "repair_item", "temper_item", "dismantle_many", "chuangong",
)
MENXIA_ACTIONS = features_core.action_table(MENXIA_ACTION_ORDER, {
    "heal": lambda g, b: g.heal(),
}, features_core.menxia_actions(sys.modules[__name__]))


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


@app.get("/api/reports")
def api_reports(request: Request, id: int | None = None):
    game = _game(request)
    return look(game, lambda g: reports_view(g, id))


# ── 戰記：本體與路由（/api/tale/{battle_id}、/zhanji/{code}）在 tianxia/features/tale/routes.py（全部拆包第 52 批）。這裡留 state 的宣告（包照 shell.<名字> 當下讀寫，
# 測試與 tests/conftest.py 收尾認這幾個名字）與一行薄包裝。背景執行緒由 main() 經 features_core.start_threads 開（殼開、測試停）──
def tale_view(battle_id: int, request: Request | None = None) -> dict:
    return tale_routes.tale_view(sys.modules[__name__], battle_id, request)


TALE_COVER_DIR = WEB / "img" / "tale"  # 戰記頁的封面資料夾（web/img/tale/；tests/server/test_server.py 換它）


def tale_cover(definition) -> str:
    return tale_routes.tale_cover(sys.modules[__name__], definition)


# 江湖史也點得進戰記：誰看得到（只有參戰的人，還是全服）等 Joy 定，先關著
TALES_IN_CHRONICLE = False


def tale_index(game: Game) -> list[dict]:
    return tale_routes.tale_index(sys.modules[__name__], game)


TALES = None  # 戰記的小檔（tale.TaleStore）；start_tales 建，還沒接上是 None
TALES_CLIENT = None  # 寫戰記用的 client（main() 照設定建；測試塞假的）
TALES_STOP = threading.Event()
TALES_THREAD: threading.Thread | None = None


def start_tales(config, client=None) -> threading.Thread | None:
    return tale_routes.start_tales(sys.modules[__name__], config, client)


def tale_round(clock: Callable[[], float] = time.time) -> int | None:
    return tale_routes.tale_round(sys.modules[__name__], clock)


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



# 列傳的畫面與 ZHUAN_LOCK 搬進列傳包 tianxia/features/zhuan/routes.py（第二輪第 83 批）；殼留兩個別名與 write_zhuan 一行包裝（測試與 same_behavior 讀 server.<名字>，同一個物件）
ZHUAN_JOBS = zhuan_routes.ZHUAN_JOBS
_zhuan_key = zhuan_routes._zhuan_key
PUBLIC_URL_ENV = "TIANXIA_PUBLIC_URL"  # 分享網址的開頭；沒設就照設定的 Config.biography.public_url，再沒有就照這次請求的網址


def write_zhuan(game: Game, season: int, rewrite: bool) -> bool:
    return zhuan_routes.write_zhuan(sys.modules[__name__], game, season, rewrite)


def public_base(request: Request) -> str:
    """分享網址的開頭（不含結尾的斜線）：環境變數 > 設定 > 這次請求的網址（走 cloudflared 時照 X-Forwarded-Proto 認 https）。"""
    fixed = os.environ.get(PUBLIC_URL_ENV) or CONTENT.config.biography.public_url
    if fixed:
        return fixed.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return f"{proto}://{request.headers.get('host') or request.url.netloc}"


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


@app.get("/manifest.webmanifest")
def manifest():
    """加到主畫面用的說明檔（iPhone 要先加到主畫面才收得到通知）。"""
    return Response((WEB / "manifest.webmanifest").read_bytes(), media_type="application/manifest+json", headers=NO_CACHE)


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
    print(narration_line(CONTENT.config), flush=True)
    start_narration(CONTENT.config)  # 減法季的開關關著只建小檔、不開執行緒
    features_core.start_threads(sys.modules[__name__])  # 各包的背景執行緒（殼開、測試停）。戰記：小檔一定建，執行緒照樣開（叫不動模型就寫模板版）。手機通知：開關關著、沒裝 cryptography 什麼都不做（WEB_PUSH 是 None）
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
