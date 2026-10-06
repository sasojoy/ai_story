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
- 開爐的首次取名也在行動鎖外（`prepare_forge`／`forge`），整段有時間預算（`Config.naming_budget_seconds`），
  用完走退路字表，請求在 trycloudflare 切斷之前結束。
- 大場面（挑戰大勢人物本人、打頭目）的判讀也在行動鎖外（`prepare_fight`），預算是 `Config.big_fight_budget_seconds`；
  一般的仗不問模型，備料與動作在同一次拿鎖裡做完。
- 對話生成與隨口應對的評分、潤色也有總預算（`Config.dialogue_budget_seconds`、`free_text_budget_seconds`；評分與潤色共用
  後面那一份），跟開爐、大場面一樣從備料那一段開始算、扣掉等鎖與排隊的時間。
- 鎖外的五個模型呼叫（對話生成、大場面判讀、開爐取名、隨口應對的評分與潤色）一律走 `model_call`：開關
  `Config.llm_queue_slots`（預設 0＝關）打開時先排隊（`llm_queue.py`：真人先、假人有上限、排太久拿退路；同一個人同時只有一件，
  第二件被擋下來——評分、開爐、大場面回一句話、什麼都不套用，對話取消、潤色不插句子），
  關著就直接叫。鎖內的小呼叫（`Game._quick_client`）與排程不進佇列。

執行：`.venv/Scripts/python.exe server.py`（http://127.0.0.1:7861，預設只聽這台電腦）。要讓外面的手機連進來，
加 `--share`：會用 cloudflared 開一個臨時的公開網址（要先裝 cloudflared，見 CLAUDE.md）；
或加 `--lan`：讓同一個區網的裝置直接連過來（有網址的人都進得來）。
"""
from __future__ import annotations

import argparse
import contextlib
import contextvars
import copy
import hashlib
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
from collections import deque
from collections.abc import Callable, Iterable
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt

from llm_queue import Busy, LlmQueue
from tianxia import companion_agent, event_llm, fight_llm, foreshadow, naming, rules, server_bots, team, timetable
from tianxia.accounts import NAME_TAKEN, PASSWORDS_DIFFER, AccountError, AccountStore, normalize
from tianxia.content import PROFILE_ENV, load_content, profile_line
from tianxia.characters import open_characters
from tianxia.database import default_path, open_database
from tianxia.engine import FIGHT_GONE_LINES, FREE_TEXT_OPTION, Game
from tianxia.models import FREE_TEXT_MAX
from tianxia.journal import CSS as JOURNAL_CSS
from tianxia.sqlite_world import open_world

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


# ── 鎖內模型呼叫的全服斷路器（PM 2026-10-05）──
# 鎖內每一步模型呼叫最多等 Config.in_lock_model_timeout（15 秒），一次拿鎖期間只容忍一次失敗（Game._quick_client）。可是模型
# 掛了的時候，每個玩家的下一個動作都還是要在行動鎖裡等一次逾時，全服跟著等。所以任何一次拿鎖裡有鎖內的模型呼叫失敗或逾時，
# 就把全服的斷路器打開 MODEL_BREAKER_SECONDS 秒：這段時間每一次拿鎖（不分玩家）一開始額度就用完，鎖內直接用固定文字、
# 不碰網路；時間到之後的第一次拿鎖照常叫模型，又失敗就再打開。只管鎖內：鎖外的取名、對話、隨口應對的評分照舊叫模型。
# 只在 server.py（PM：不進 Config）；假人程式（run_bots.py）的 client 是 None，本來就不叫模型。
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
    鎖內的模型額度與斷路器見 _model_guard。"""
    with game.world.action_lock(), _model_guard(game):
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
    clock 只給節流用（預設 time.monotonic），跟世界時間無關。"""

    def __init__(self, clock: Callable[[], float]):
        self.clock = clock
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
            print(f"排程這一下出錯：{type(exc).__name__}", flush=True)
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
        print(f"排程這一下又出錯 {count} 次：{self.key[0]}（同一個地方，細節同上）", flush=True)


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
        f"排超過 {config.llm_queue_wait_seconds:g} 秒就用退路"
    )


# 同一個玩家已經有一件在等模型（另一個分頁、另一台裝置），這一件被擋下來時回的話（佇列開著才會；審查 M2）。
# 退路是一個結果：隨口應對的評分退路是 40（灌水的寫法本來該得 0）、首次開爐的退路是退路字表的名字（整季登記），
# 第二個分頁不能拿來挑結果，所以評分、開爐、大場面一律擋下來、什麼都不套用。三句都是草稿，待 joy 潤。
BUSY_FREE_TEXT = "上一句還在掂量，稍等。"  # 待 joy 潤
BUSY_FORGE = "上一爐還沒出爐。"  # 待 joy 潤
BUSY_FIGHT = "還在對峙，稍等。"  # 待 joy 潤


def model_call(game: Game, job, *, fallback, left: float | None = None, busy: str | None = None):
    """行動鎖外叫模型一律走這裡：佇列開著就用這個角色的名號排隊（真人先、假人有上限、一人一件、排太久拿 fallback，
    見 llm_queue.LlmQueue），關著就直接叫。呼叫端不能握著行動鎖：排隊最久要等 llm_queue_wait_seconds 秒，握著鎖等就是全服一起等；
    在鎖裡被叫到直接丟 RuntimeError（跟 _model_guard 一樣，用 RuntimeError 不用 assert：python -O 也照樣擋），開關開著關著都一樣。
    鎖內的小呼叫走 Game._quick_client、不進佇列。佇列只認名號；是不是假人只決定排序與上限，不改任何玩家看得到的字。
    left 是呼叫端那一件的總預算還剩幾秒（有總預算的四種呼叫都給）：排隊最久只等 min(llm_queue_wait_seconds, left)，
    一個請求不會排過自己的總預算（審查 M1）；剩下 0 秒就是 0：位子正好空著照常進場（job 自己發現預算用完、不叫模型），
    要排的話馬上拿退路。沒給（None）就只受 llm_queue_wait_seconds 管。
    同一個人已經有一件在排或在跑（佇列對這一件丟 Busy，審查 M2）：給了 busy（一句話）就丟 GameError、不叫 job、不套用任何東西，
    呼叫端不能繼續往下走；沒給就拿 fallback（對話：取消那一輪、潤色：不插句子，本來就無害）。佇列關著沒有這回事，照舊直接叫。"""
    if game.world.db.writing():
        raise RuntimeError("model_call 要在行動鎖外用：鎖內的小呼叫走 Game._quick_client，不排隊")
    queue = QUEUE
    if queue is None:
        return job()
    p = game.state.player
    wait = game.content.config.llm_queue_wait_seconds
    if left is not None:
        wait = max(0.0, min(wait, left))
    try:
        return queue.run(p.name.casefold(), job, fallback=fallback, bot=p.bot is not None, wait=wait)
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
    own = getattr(client, "timeout", None)
    per_post = min(float(own) if isinstance(own, (int, float)) else left, left / naming.POSTS_PER_CALL)
    if per_post < naming.MIN_POST_SECONDS:
        return None
    capped = copy.copy(client)
    capped.timeout = per_post
    return capped


def prepare_dialogue(game: Game, option_id: str) -> companion_agent.PreparedTurn | None:
    """對話選項在行動鎖外生成（企劃者 2026-10-03 核准的過渡做法，正解是線上架構第二階段的 LLM 佇列）。
    模型一輪要 9~10 秒，整段包在鎖裡的話全服玩家與假人程式都得跟著等。分三段：
      A（鎖內、很快）同步時間，問引擎這個選項現在會不會生成對話，會就拿到送模型的單子；同步的結果（共用賽季的推進
        已經寫進資料庫、江湖大事寫進這個角色的江湖紀錄）要存起來，不然 C 段進鎖重讀就把它丟了；
      B（鎖外、很慢）呼叫模型（model_call：佇列開著要排隊），失敗、太慢、排太久時單子裡的 turn 是 None；預算是
        Config.dialogue_budget_seconds 扣掉 A 段（含等鎖）與排隊花掉的時間，引擎不讀時鐘，所以時間在這裡量（見 within_budget）；
      C（鎖內、很快）由呼叫端把結果交給 Game.choose(prepared=...)，引擎進鎖後重新核對再套用。
    這裡做 A 與 B，不會生成對話的選項（包含 talk:leave）回傳 None，由呼叫端走一般的 act()。"""
    started = _monotonic()
    with _locked(game):
        game.sync(time.time())
        request = game.dialogue_request(option_id)
        open_characters().save(game.state)
    if request is None:
        return None
    cancelled = companion_agent.PreparedTurn(request.option_id, request.companion_id, request.player_action, None)
    total = game.content.config.dialogue_budget_seconds

    def generate():
        client = within_budget(game.client, total - (_monotonic() - started))
        if client is None and game.client is not None:
            return cancelled  # 等鎖、排隊把整份預算用完了：不叫模型，這一輪取消（跟模型叫不動一樣）
        return companion_agent.prepare_turn(client, request)

    return model_call(game, generate, fallback=cancelled, left=total - (_monotonic() - started))


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
        太慢、排太久時判讀是 None——單子照樣帶著，等判讀的時候這個選項沒了（人被另一個分頁帶走），C 段才說得出是哪一仗沒打成；
      C 由呼叫端交給 Game.choose(fight=...)，引擎進鎖後重驗再套用（判讀是 None 也照樣打，優勢 0；選項已經不在就不打，
        回一句 FIGHT_LEFT／FIGHT_CHANGED，見 api_choose）。
    鎖內任何一步都不叫模型；鎖外這一段不歸鎖內的模型上限與斷路器管（跟對話、開爐取名一樣）。"""
    started = _monotonic()
    with _locked(game):
        game.sync(time.time())
        request = game.fight_request(option_id)
        done = game.choose(option_id) if request is None else None
        open_characters().save(game.state)
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


def choose(game: Game, option_id: str) -> list[str] | None:
    if may_generate_dialogue(option_id):
        prepared = prepare_dialogue(game, option_id)
        return act(game, lambda g: g.choose(option_id, prepared=prepared))
    if may_judge_fight(option_id):
        fight = prepare_fight(game, option_id)
        if isinstance(fight, list):
            return fight  # 不是大場面：A 段那一次拿鎖已經做完了
        return act(game, lambda g: g.choose(option_id, fight=fight))
    return act(game, lambda g: g.choose(option_id))


NO_NAME: tuple[str | None, str] = (None, "")  # 開爐的 B 段沒取到名字（或不必取）：C 段直接走退路字表、不在鎖裡叫模型


def prepare_forge(
    game: Game, art_id: str | None, insight_ids: list[str], other_art: str | None = None,
) -> tuple[str | None, str]:
    """開爐的首次取名或挑選在行動鎖外（最終審查 Critical 1）。首次合出來的配方要等模型取名（合到舊的、候選兩個以上時是
    請模型從候選挑一個名字），以前整段包在行動鎖裡：
    一次最多叫三次、每次最多等 OllamaClient.timeout（120 秒），全服玩家與假人程式都得跟著等，試玩走的 trycloudflare
    也會在約 100 秒切斷請求。跟 prepare_dialogue 一樣分三段：
      A（鎖內、很快）同步時間，問引擎這一爐要不要模型取名或挑（Game.forge_request），要就拿到單子；同步的結果要存起來，
        不然 C 段進鎖重讀就把它丟了；
      B（鎖外、很慢）naming.generate（model_call：佇列開著要排隊）：預算是 Config.naming_budget_seconds 扣掉 A 段（含等鎖）
        與排隊花掉的時間，引擎不讀時鐘，所以時間在這裡量，輪到了才算；用完、排太久就回 (None, "")，C 段走退路字表（挑的話改由規則挑）；
      C（鎖內、很快）由呼叫端把結果交給 Game.forge(..., proposed=...)，引擎整個重驗再登記、收費。
    這裡做 A 與 B，回傳 B 的結果（名字, 說明）；不必叫模型時是 NO_NAME。假人程式之後要合成，照樣能不經過 HTTP
    走這三段（Game.forge_request 在 action_lock 裡、naming.generate 在鎖外、Game.forge(proposed=...) 再進鎖）。
    other_art 有、insight_ids 空的是武學＋武學。"""
    started = _monotonic()
    with _locked(game):
        game.sync(time.time())
        request = game.forge_request(art_id, insight_ids, other_art=other_art)
        open_characters().save(game.state)
    if request is None:
        return NO_NAME
    total = game.content.config.naming_budget_seconds

    def name_it():
        budget = max(0.0, total - (_monotonic() - started))
        # 角色名號的查詢是唯讀的快照、不拿行動鎖（FB-069：模型取到角色的名號就再取一次；C 段進鎖還會再擋一次）
        return naming.generate(game.client, game.content, request, budget=budget, person=game.world.is_character_name)

    return model_call(game, name_it, fallback=NO_NAME, left=total - (_monotonic() - started), busy=BUSY_FORGE)


def forge(game: Game, art_id: str | None, insight_ids: list[str], other_art: str | None = None) -> list[str] | None:
    """開爐：A、B 在 prepare_forge，C 進鎖交給 Game.forge。proposed 一定給（不必叫模型時是 NO_NAME），
    所以伺服器上的開爐永遠不會在鎖裡叫模型。同一爐連按兩下、重新整理再按、開兩個分頁：兩個請求可能都走完 A、B，
    C 段重驗時第二個會看見配方有了、東西已經在你身上，什麼都不收（企劃者 2026-10-05：不能重複扣）。
    模型佇列開著時，同一個人已經有一件在等模型（另一個分頁、另一台裝置），第二件在 B 段被擋下來：丟 GameError「上一爐還沒出爐。」
    （BUSY_FORGE），不走 C 段、什麼都不登記、什麼都不收（審查 M2、控制者裁示；以前它拿 NO_NAME 先進鎖，這個配方這一季就用退路
    字表的名字登記，第一件模型取的名字被丟掉）。不必叫模型的爐（配方已經有人合過）不經過佇列，兩個分頁照常都走得完。"""
    proposed = prepare_forge(game, art_id, insight_ids, other_art)
    return act(game, lambda g: g.forge(art_id, insight_ids, proposed=proposed, other_art=other_art))


def answer_event(game: Game, text: str) -> list[str] | None:
    """事件的隨口應對（探索的多人與 LLM 玩法 §8.1），跟 prepare_dialogue 一樣分三段：
      A（鎖內、很快）同步時間，問引擎這句話現在能不能送；能就拿到單子（事件 id＋這句話），同步的結果照樣存起來；
      B（鎖外、很慢）請模型評這個做法的成功率（model_call：佇列開著要排隊），失敗、太慢、排太久一律 40；預算是
        Config.free_text_budget_seconds 扣掉 A 段（含等鎖）與排隊花掉的時間（見 within_budget）；
      C（鎖內、很快）Game.answer_event 重驗還停在同一則事件、同一句話，才擲骰套用（對不上就不套用）；
      D、E 擲骰之後在鎖外請模型潤色一兩句（model_call：同一個人這時沒有別件在排，照常再排一次），再進鎖插回那一則江湖紀錄
        （Game.add_gamble_narration）。潤色跟評分共用同一份 free_text_budget_seconds（控制者 2026-10-06）：從 A 段算起，
        扣掉評分、等鎖與排隊花掉的，剩下的給潤色（同一個 within_budget）；不夠一趟就不叫、不插句子，跟模型叫不動時一樣。
        整個請求因此在 free_text_budget_seconds 加兩次進鎖之內結束，不會超過 trycloudflare 約 100 秒的切斷。"""
    started = _monotonic()
    with _locked(game):
        game.sync(time.time())
        request = game.free_text_request(text)
        open_characters().save(game.state)
    if request is None:
        raise GameError(f"寫一句 1～{FREE_TEXT_MAX} 字的做法；眼前的事已經過去的話，就不必再寫了。")
    event = CONTENT.events[request.event_id]
    total = game.content.config.free_text_budget_seconds

    def score():
        client = within_budget(game.client, total - (_monotonic() - started))
        if client is None and game.client is not None:
            return event_llm.DEFAULT_FREE_TEXT_SUCCESS_RATE  # 等鎖、排隊把整份預算用完了：不叫模型，保底值
        return event_llm.assess_event_success_rate(client, event, request.text)

    rate = model_call(
        game, score, fallback=event_llm.DEFAULT_FREE_TEXT_SUCCESS_RATE, left=total - (_monotonic() - started),
        busy=BUSY_FREE_TEXT,
    )
    msgs = act(game, lambda g: g.answer_event(request, rate))
    outcome = game.last_gamble
    if outcome is not None:  # D（鎖外）擲骰之後請模型潤色一兩句，E（鎖內）插回那一則紀錄；失敗、預算用完就只留結果文字
        def narrate():
            client = within_budget(game.client, total - (_monotonic() - started))  # 評分剩下來的預算，不是重新算一份
            if client is None and game.client is not None:
                return None  # 評分、等鎖、排隊把整份預算用完了：不叫模型，不插句子
            return event_llm.narrate_event_gamble(client, event, outcome.text, outcome.success, outcome.effect_text)

        narration = model_call(game, narrate, fallback=None, left=total - (_monotonic() - started))
        if narration:
            act(game, lambda g: g.add_gamble_narration(outcome, narration))
    return msgs


# ── 畫面資料 ──────────────────────────────────────────


def main_view(game: Game) -> dict:
    """江湖畫面與頂上的狀態列；每次動作、每次計時器都回這一份。呼叫端要拿著行動鎖。"""
    card = game.battle_card() if game.shows_battle_card() else None
    status, quest, scene = game.status_data(), md(game.quest_text()), md(game.scene_text())
    options = game.options()  # 照原本的順序：狀態、主線、場景先讀，選單（會推進全服戰鬥）最後
    latest = game.journal_top_html()
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
        # 「剛剛」：這次行動打了仗就放戰鬥卡片，卡片沒寫到的補充放在 now；之後配了點也一樣（配點不換「剛剛」，計畫二最終審查 M1）
        "card": md(card) if card is not None else None,
        "card_id": game.battle_card_id() if card is not None else None,
        # 江湖紀錄頁是 latest＋journal＋older 接起來的，從最新一則列起（最新一則就是卡片那一場時，latest 是卡片的補充）
        "latest": latest,
        "journal": game.journal_html(1, RECENT_ROWS),
        "older": game.journal_html(1 + RECENT_ROWS, OLDER_ROWS),
        # 江湖頁的「剛剛」：跟 latest 一樣，只是最新的幾則若只是本週大事（江湖頁那排小標「大事」點開的面板；休季是結算卡）上已經有全文的大事，
        # 改放再前面那一則，同一段公告不寫兩次（FB-046）；最新的配點也越過，卡片與補充看的都是那一場那一則
        "now": game.battle_extra_html() if card is not None else game.now_entry_html(),
        "minimap": game.minimap_svg(),
        "bulletin": [md(text) for text in game.bulletin()],  # 江湖頁那排小標「大事」點開的本週大事（新的在前）；開關關著是空的
        "trends": md(game.trends_text()),
        "rumors": md(game.rumors_text()),
        "chronicle": md(game.chronicle_text()),
        "admin": game.is_admin(),
        "guide": game.guide_box(),  # 行動列上方的說書人對話框（引導重做設計 8.1）；略過或早就做完是 None
    }
    if "fronts" in status:  # 第一季濃縮版才有：江湖頁的三條戰況（開關關著時不送，頁面照舊）
        view["fronts"] = status["fronts"]
    orders = game.orders_view()  # 第一季：自己陣營的本週軍令（計畫 T6；散人、別陣營、開關關著時都沒有這個鍵）
    if orders:
        view["orders"] = orders
    convoy = game.convoy_line()  # 押著的糧車（T6 審查 I3）：軍令卡上寫一行
    if convoy is not None:
        view["convoy"] = convoy
    result = game.season_result()  # 第一季休季：江湖頁最上面的結算卡（計畫 T9；開關關著、進行中都不送）
    if result is not None:
        view["season_result"] = {
            **result, "text": md(result["text"]),
            "timeline": [{**row, "text": md(row["text"])} for row in result["timeline"]],
        }
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
        "player_card": md(game.member_card("player")),
        "roster": [{"label": label, "key": key} for label, key in lines],
        "person": person,
        "person_card": md(game.member_card(person)) if person else None,
        "on_team": person is not None and person in game.state.player.team,
        "bag": md(game.bag_text()),
        # 背包旁的「伏筆物品」：開關開著、這一季蓋了章、手上有才有東西，沒有就是空的（畫面整塊不出現）。只有名字與數量
        "clue_items": [
            {"id": item.id, "name": item.name, "count": n} for item, n in foreshadow.held_items(game.state, game.content)
        ],
        # 功法卡（FB-006）：身上兩門各一張，還沒學的那一門是一句「你還沒有內功。」；
        # 功法庫通常只有幾門，卡一起送，點開不必再打一次 API（QA L4：先看卡再改練）
        "slot_cards": [
            {"kind": k, "card": md(game.skill_detail(k)), "learned": learned[k], "level": level[k],
             "maxed": level[k] >= team.MAX_LEVEL,
             # 練下一成要的心得（修練頁的鈕上寫給玩家看）；還沒學或已經第十成就沒有價錢
             "price": team.practice_price(game.content, level[k]) if learned[k] and level[k] < team.MAX_LEVEL else None}
            for k in KINDS
        ],
        "forge_line": md(game.forge_line(None, [])),
        # 武學與成長（修練頁、煉製頁）：持有數與上限、每門武學一列（身上的在前）、悟得的意境、等著取名的那一門
        "holdings": game.holdings(),
        "owned_arts": [{**row, "card": md(row["card"])} for row in game.art_rows()],
        "insights": game.insight_rows(),
        "naming": game.naming_row(),
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
        # 圖例不畫進 svg（圖裡的會跟著平移、縮放，放大時就看不見）：跟 svg 並排給網頁，疊在地圖框角落（web/app.js 的 legendHtml）
        "legend": game.map_legend(layer),
        "places": [{"label": label, "id": loc_id} for label, loc_id in places],
        "selected": selected,
        "here": game.state.player.location,
        "detail": md(game.place_detail(selected)),
        # 步行、趕路、疾行三個按鈕（照 atlas.MODES 的順序）；就在這裡時是 None。被待處理的事件擋著時只有一顆灰的、
        # label 寫是哪一則，to_jianghu 為真：頁面在旁邊多給一顆「回江湖」（FB-063）
        "travel": [
            {"mode": o.mode, "label": o.label, "enabled": o.enabled, "to_jianghu": o.to_jianghu}
            for o in game.travel_options(selected) or []
        ] or None,
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
    """管理者觸發區的三個下拉選單（戰鬥、大事、大勢線）與模型佇列的總數。戰鬥與大事照引擎給的（Game.admin_battles／admin_fires：
    內容的順序，第一季不觸發的 beta 決戰與門檻不列；已經發生過的大事按下去會被引擎拒絕）；
    大勢線照這一季的規則（第一季濃縮版要開關開著、而且這一季蓋了「開」的章）。呼叫端要拿著行動鎖（look）。"""
    world = game.state.world
    return {
        "battles": [{"label": b.name, "id": b.id} for b in game.admin_battles()],
        "events": [{"label": f"{x.text[:30]}（{x.id}）", "id": x.id} for x in game.admin_fires()],
        # 照開關：關著時不列第一季才有的線；開著時不列黃巾聲勢（由三條戰線合成，不能直接推）
        "trends": [{"label": t.name, "id": t.id} for t in CONTENT.scenario.trends if rules.pushable(CONTENT, world, t.id)],
        **timetable_choices(game),
        # 下一季會照第一季的規則開（開關開著）：「開啟下一季」的問句也提醒排三場大戲與季末的時間（FB-050）
        "next_has_timetable": bool(CONTENT.config.season_one),
        # 模型佇列的總數（正在跑幾件、在排幾件，真人與假人算在一起，不分開數）；不列名號，也看不出有沒有假人（審查 M4）。開關關著是 None
        "llm_queue": None if QUEUE is None else QUEUE.snapshot(),
    }


RESULT_WORDS = (("guan:", "官軍"), ("huang:", "黃巾"))  # 結果鍵的白話（定結果的下拉選單）
TIMETABLE_STATES = {"done": "已結算", "running": "開打了", "due": "時間到了", "later": "還沒到"}


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
    for row in timetable.status_rows(state, CONTENT):
        rows.append({
            "id": row["id"], "label": f"第{row['week']}週　{row['title']}",
            "state": row["state"], "state_text": TIMETABLE_STATES[row["state"]],
            "result": (_ending_title(row["result"]) if row["kind"] == "finale" else _done_label(row["result"]))
            if row["result"] else None,
            "schedulable": row["schedulable"],
            "at_real": now + (row["when"] - world.time) / CONTENT.config.time_scale if row["schedulable"] else None,
        })
    results = [
        {"value": f"{e.id}|{key}", "label": f"{e.title}：{_result_label(key)}"}
        for e in CONTENT.timetable if e.id not in world.timeline
        for key in timetable.result_keys(state, CONTENT, e)
    ]
    locks = [
        {"id": event_id, "label": f"{e.title}（{lock.name}）"}
        for event_id, lock in world.locks.items() if (e := next((x for x in CONTENT.timetable if x.id == event_id), None))
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
    "guide_ack": lambda g, b: g.guide_ack(),  # 對話框的結語按「知道了」
    "allocate": lambda g, b: g.allocate_stat(str(b.get("stat", ""))),  # 狀態列的配點鈕：升級得到的屬性點加到一項
}
ADMIN_ACTIONS = {
    "open_season": lambda g, b: g.admin_open_season(time.time()),
    "end_season": lambda g, b: g.admin_end_season(time.time()),
    "next_season": lambda g, b: g.admin_next_season(time.time()),
    "fast_forward": lambda g, b: g.advance(_int(b.get("hours"), 1) * 3600),
    "start_battle": lambda g, b: g.admin_start_battle(str(b.get("id", "")), time.time()),
    "fire": lambda g, b: g.admin_fire(str(b.get("id", ""))),
    "push_trend": lambda g, b: g.admin_push_trend(str(b.get("id", "")), _int(b.get("amount"), 0)),
    # 時刻表與救場（計畫 T10）：現實時間由伺服器給，引擎不讀時鐘
    "schedule": lambda g, b: g.admin_schedule(str(b.get("id", "")), _float(b.get("at"), 0.0), time.time()),
    "jump_next": lambda g, b: g.admin_jump_next(time.time()),
    "set_trend": lambda g, b: g.admin_set_trend(str(b.get("id", "")), _int(b.get("value"), 0)),
    "resolve_event": lambda g, b: g.admin_resolve_event(str(b.get("id", "")), str(b.get("key", ""))),
    "clear_lock": lambda g, b: g.admin_clear_lock(str(b.get("id", ""))),
    "cancel_battle": lambda g, b: g.admin_cancel_battle(),
}


@app.post("/api/choose")
def api_choose(request: Request, body: dict = Body(...)):
    game = _game(request)
    option_id = str(body.get("id", ""))
    msgs = choose(game, option_id)
    out = {"main": look(game, main_view)}
    if option_id.startswith("battle:") or (msgs and msgs[0] in FIGHT_GONE_LINES):
        # 決戰選項（加入、趕到、每回合的出招）：按下去發生了什麼只有這句回話（FB-030），前端拿它跳一句提示。
        # 大場面等判讀的時候選項沒了（「你離開了，這一仗沒打成。」）：這一仗沒打、不寫江湖紀錄，也只有這句回話。
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


def forge_args(body: dict) -> tuple[str | None, list[str], str | None]:
    """煉製頁送來的東西：爐裡的武學 id（可以沒有）、意境 id 們、第二門武學 id（武學＋武學，可以沒有）。body 是客戶端寫的：
    武學一律轉成字串、意境不是清單就當作沒放，形狀不對只會得到「不存在／放一門武學和一個意境…」那一句話，不會打出 500。"""
    art, other, picked = body.get("art"), body.get("other_art"), body.get("insights")
    return (
        str(art) if art else None,
        [str(i) for i in picked] if isinstance(picked, list) else [],
        str(other) if other else None,
    )


def _forge_without_naming(game: Game, art_id: str | None, insight_ids: list[str], other_art: str | None) -> list[str]:
    return game.forge(art_id, insight_ids, proposed=NO_NAME, other_art=other_art)


MENXIA_ACTIONS = {
    "practice": lambda g, b: g.practice(str(b.get("kind") or KINDS[0])),
    "heal": lambda g, b: g.heal(),
    # 一武學＋一意境、兩武學＝合成，兩意境＝合併。端點走 forge()（A 鎖內備料 → B 鎖外取名或挑 → C 鎖內登記），不走這一條；
    # 這裡也帶 NO_NAME，就算有人直接拿它在鎖裡呼叫，也不會叫模型
    "forge": lambda g, b: _forge_without_naming(g, *forge_args(b)),
    "switch": lambda g, b: g.switch_art(str(b.get("art") or "")),
    # 用融的意境修練一次，衝下一品；use_legend 是勾了「服下破境丹」。只認真正的布林 true：字串、數字都不算勾
    "cultivate": lambda g, b: g.cultivate(str(b.get("art") or ""), use_legend=b.get("use_legend") is True),
    "melt": lambda g, b: g.melt_art(str(b.get("art") or "")),  # 功法庫裡的一門熔成心得
    "melt_insight": lambda g, b: g.melt_insight(str(b.get("insight") or "")),
    "name": lambda g, b: g.name_mastered(str(b.get("name") or "")),  # 第一個練成絕學的人替它取正式名字
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
    person = None if person is None else str(person)  # 客戶端寫的：清單之類不是字串的，下面查名冊會丟 TypeError

    def run(g: Game):
        # 名冊（誰是你的人）是全服狀態，換季、假人程式都會改：跟動作在同一把鎖裡核對，引擎才能假設那個人在名冊上
        if op in ("join", "leave") and person not in {key for _, key in g.roster_lines()}:
            raise GameError("名冊裡沒有這個人。")  # 交易整筆撤回（連同進鎖時的同步）；下一個請求重讀再算一次
        return MENXIA_ACTIONS[op](g, body)

    # 開爐：首次合出來的配方要模型取名，在行動鎖外取（見 prepare_forge）；其他動作照舊一把鎖做完
    msgs = forge(game, *forge_args(body)) if op == "forge" else act(game, run)
    return {
        "menxia": look(game, lambda g: menxia_view(g, person)),
        "main": look(game, main_view),
        "message": joined(msgs),
    }


@app.post("/api/forge_line")
def api_forge_line(request: Request, body: dict = Body(default={})):
    """煉製頁選了東西就更新說明（不算行動、不存檔）。"""
    game = _game(request)
    art, picked, other = forge_args(body)
    return {"line": look(game, lambda g: md(g.forge_line(art, picked, other_art=other)))}


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


@app.get("/api/queue")
def api_queue(request: Request):
    """等模型的時候前端每 2 秒問一次：這個角色那一件前面還有幾件（正在跑的也算一件；佇列關著、或沒有在排：null）。
    只給一個數字：真人排在假人前面，所以前面的只有正在跑的與先排的真人，看不出有沒有假人。不拿行動鎖。"""
    game = _game(request)
    return {"ahead": None if QUEUE is None else QUEUE.position(game.state.player.name.casefold())}


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

    global QUEUE
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
    QUEUE = make_queue(CONTENT.config)  # 開關關著是 None：鎖外的模型呼叫照舊直接叫
    print(queue_line(CONTENT.config), flush=True)
    interval = CONTENT.config.world_tick_seconds
    print(scheduler_line(interval), flush=True)
    start_scheduler(interval)
    if args.lan:
        print("已開放區網連線：同一個網路裡的裝置都連得到。", flush=True)
    uvicorn.run(app, host="0.0.0.0" if args.lan else "127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
