"""tests/server/test_server.py 拆走的測試與留下的測試共用的小工具（全部拆包第 61 批，只搬位置、不改內容）。"""
import contextlib
import sqlite3
import time
from unittest import mock
import pytest
from fastapi.testclient import TestClient
import llm_queue
import server
import server_push
from tianxia.features.battle import instance as battle_instance
from tianxia.features.companions import companion_agent
from tianxia import fusion, insights, naming
from tianxia.features.tale import tale
from tianxia.characters import open_characters
from tianxia.engine import Game
from tianxia.ollama_client import OllamaClient
from tianxia.sqlite_world import SqliteWorldStore, open_world


@pytest.fixture(autouse=True)
def save_dir(tmp_path):
    return tmp_path


@pytest.fixture(autouse=True)
def season_already_open(monkeypatch):
    """server.CONTENT 是正式內容（預設要管理者開季）；這裡的測試要的是一季已經開打的畫面。"""
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)


@pytest.fixture(autouse=True)
def scheduler_off(monkeypatch):
    """server.CONTENT 是正式內容，伺服器排程開著（減法季批 0 起 world_tick_seconds 10）：這裡的測試叫 server.main 時不要真的開執行緒；
    測排程本身的測試自己再打開。"""
    monkeypatch.setattr(server.CONTENT.config, "world_tick_seconds", 0)


def _stop_scheduler() -> None:
    """排程執行緒也是 server 的模組狀態：測試留下來的那一條先停掉、等它真的結束，再把停止的旗子放下，
    免得它在後面測試的暫存資料庫上推世界。"""
    thread = server.SCHEDULER_THREAD
    if thread is not None:
        server.SCHEDULER_STOP.set()
        thread.join(5.0)
        assert not thread.is_alive()
    server.SCHEDULER_THREAD = None
    server.SCHEDULER_STOP.clear()


def _stop_push() -> None:
    """推送也是 server 的模組狀態（HUB 與看守執行緒）：每個測試從關著開始，留下來的看守先停掉、等它真的結束。"""
    thread = server.PUSH_THREAD
    if thread is not None:
        server.PUSH_STOP.set()
        thread.join(5.0)
        assert not thread.is_alive()
    server.PUSH_THREAD = None
    server.PUSH_STOP.clear()
    server.HUB = None


@pytest.fixture(autouse=True)
def _no_landing(monkeypatch):
    """合到舊的（設計 12.2）在 test_fusion.py 測；這裡的測試照舊每一爐都長新的，結果才固定。"""


@pytest.fixture(autouse=True)
def _no_preset_recipes(monkeypatch):
    """師門配方（基礎拳腳融風、山、水、火，content/preset_recipes.json）名字是寫好的、不叫模型；這裡測開爐取名的三段式，
    拿基礎拳腳融基本意境當例子，要的是一般的配方。師門配方在 test_prologue.py、test_real_content.py 測。"""
    monkeypatch.setattr(server.CONTENT, "preset_recipes", [])


@pytest.fixture(autouse=True)
def fresh_server_memory():
    """登入紀錄、登入狀態、角色快取（還有排程那一份沒有玩家的 Game、排程執行緒）都只放在伺服器記憶體裡：每個測試從空的開始，
    不然上一個測試的暫存資料庫會被沿用。"""
    _stop_scheduler()
    _stop_push()
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    server.WORLD_GAME = None
    server.QUEUE = None  # 模型佇列也是模組狀態：每個測試從關著開始（Config.llm_queue_slots 預設 0）
    yield
    _stop_scheduler()
    _stop_push()
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    server.WORLD_GAME = None
    server.QUEUE = None


@pytest.fixture(autouse=True)
def model_breaker_closed(monkeypatch):
    """鎖內模型呼叫的全服斷路器是 server 的模組狀態：每個測試從關著開始，前一個測試的模型失敗（conftest 把 chat_structured
    假成連不上）不會讓這一個的鎖內呼叫全部跳過。"""
    monkeypatch.setattr(server, "_breaker_until", None, raising=False)


@pytest.fixture(autouse=True)
def cheap_password_hashing(monkeypatch):
    """這個檔測的是伺服器，不是密碼：scrypt 換成最便宜的一組參數（一次約 40 毫秒變成幾微秒；測試整併第 4 區）。
    雜湊與比對都在呼叫的當下讀 accounts.SCRYPT_PARAMS，所以註冊、登入、改密碼照舊走同一條路；
    正式的參數與雜湊在 tests/core/test_accounts.py 測、也釘在那裡。正式程式不動。"""
    from tianxia import accounts

    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})


@pytest.fixture
def breaker_clock(monkeypatch):
    """斷路器的時鐘（server._monotonic）換成撥得動的：clock[0] 是現在的秒數，測試不必真的等 180 秒。"""
    clock = [1000.0]
    monkeypatch.setattr(server, "_monotonic", lambda: clock[0], raising=False)
    return clock


@pytest.fixture
def game():
    return Game.new(server.CONTENT, "測試")


@pytest.fixture
def client():
    return TestClient(server.app)


def _player(client, login="shen_01", name="沈青衫", prologue=False, password="secret-pw"):
    """註冊、建角色。網頁上建的新角色先走序章（新手引導計畫一）；這裡的測試大多測序章之後的事，預設略過序章站到潁川
    （prologue=True 留在草廬）。"""
    client.post("/api/register", json={"login": login, "password": password, "again": password})
    out = client.post("/api/character", json={"name": name}).json()
    if not prologue:
        out = client.post("/api/do/skip_tutorial", json={}).json()
    return out


# ── 戰記（Joy 2026-10-29，原稱戰役話本）：/api/tale 的三種狀態、背景寫一篇、江湖史目錄的開關 ──
# 寫法與存放的測試在 tianxia/features/tale/tests/test_tale.py，這裡只管伺服器這一側。


def _tale_store(tmp_path, monkeypatch):
    store = tale.TaleStore(tmp_path / "server-tale.sqlite")
    monkeypatch.setattr(server, "TALES", store)
    return store


def _ended_showdown(world, *, unfinished=False):
    """開一場黃巾決戰再把它收掉（沒有回合紀錄也寫得出戰記）。回它在資料庫裡的流水號。"""
    battle = world.start_battle(server.CONTENT.battles["huangjin_showdown"], now=0.0)

    def _end(b):
        b.phase, b.unfinished = "ended", unfinished
        b.outcome_title = "" if unfinished else "黃巾大勝"
        b.outcome_side = "huang"

    world.mutate_battle(_end)
    return battle.record_id


def _js_function(js: str, header: str) -> str:
    """app.js 裡 IIFE 內的一個函式本體：從標頭（例如 "async function mx("）到下一個縮兩格的收尾 "\\n  }\\n"。"""
    start = js.index(header)
    return js[start:js.index("\n  }\n", start)]


def _a_player_with_insights(client, insights=("feng", "huo"), xinde=100):
    """新角色（開局送的兩門基礎武學在身上），悟得 insights、心得 xinde；存進資料庫（進鎖會重讀）。"""
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.insights = list(insights)
    game.state.player.stats["xinde"] = xinde
    open_characters().save(game.state)


# ── 開爐的首次取名在行動鎖外（最終審查 Critical 1）：A 鎖內備料 → B 鎖外取名（有預算）→ C 鎖內重驗、登記、收費 ──

FENG_HUO = fusion.merge_key("feng", "huo")  # 煉製只剩意境＋意境（Joy 2026-10-21）：取名的配方換成風＋火合併（名字沿用）


def _forger(name="沈青衫", insights=("feng", "huo"), xinde=100) -> Game:
    """伺服器上這個角色唯一的那份 Game（server.game_for），悟得 insights、心得 xinde，存進資料庫（進鎖會重讀）。"""
    game = server.game_for(name)
    game.state.player.insights = list(insights)
    game.state.player.stats["xinde"] = xinde
    open_characters().save(game.state)
    return game


def _model(reply):
    """假的模型：reply(self, messages) 回名字（字串）。self 是那一次呼叫用的 OllamaClient（有預算時是複本）。"""
    def chat_structured(self, messages, response_model, **kwargs):
        return naming.NameReply(name=reply(self, messages), description="一句話。")

    return mock.patch.object(OllamaClient, "chat_structured", chat_structured)


def _nobody_holds_the_lock(game):
    assert not game.world.db.writing()  # 這個執行緒沒拿著寫入交易
    probe = sqlite3.connect(game.world.db.path, timeout=0)
    try:
        probe.execute("BEGIN IMMEDIATE")  # 別的程式（假人、別的玩家）也拿得到寫入權
        probe.execute("ROLLBACK")
    finally:
        probe.close()


# ── 決戰選項的回話（FB-030）：網頁上要看得到按下去發生了什麼 ──────────────


def _a_showdown_fighter(client, started=False):
    """官軍的新角色，黃巾決戰剛開（started＝集結已經結束、正在打），另有一位黃巾的真人在場、所以回合會等人。"""
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.faction = "guan"
    open_characters().save(game.state)
    definition = server.CONTENT.battles["huangjin_showdown"]
    open_world().start_battle(definition, now=time.time() - (definition.muster_seconds + 1 if started else 0))
    open_world().mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=320.0))
    return definition


def _journal_titles(name="沈青衫"):
    return [e.title for e in open_characters().load(name).journal]


# ── 對話在行動鎖外生成（一個玩家的模型呼叫不能讓所有人一起等）────────────


DIALOGUE_TURN = companion_agent.CompanionTurn(
    narrative="他點了點頭。", options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "尋常寒暄"],
)


def _stand_by_a_figure(game):
    """站到正式內容裡盧植所在的地點（盧植營，只有他一位大勢人物：交友直接找他），有他的結識旗標所以見得到；
    福緣設成已領，交友不會先觸發福緣。兩位以上人物的地點（例如廣宗）交友不開口，要「求見」指名。"""
    game.state.player.location = "luzhi_camp"
    game.state.player.flags.add("結識:luzhi")
    game.state.player.fortune = True


@pytest.fixture
def lock_events(monkeypatch):
    """記錄行動鎖「拿到、放掉」的順序，再讓測試把「生成」插進同一條時間線。"""
    events = []
    real = SqliteWorldStore.action_lock

    @contextlib.contextmanager
    def spy(self, timeout=None):
        with real(self, timeout):
            events.append("enter")
            yield
        events.append("exit")

    monkeypatch.setattr(SqliteWorldStore, "action_lock", spy)
    return events


def _stand_in_a_hall(game):
    """站到廣宗（張角、張梁兩位大勢人物：交友不開口，要「求見」指名），有張梁的結識旗標所以見得到他，
    張角名望不到見不到；福緣設成已領。"""
    game.state.player.location = "guangzong"
    game.state.player.flags.add("結識:zhangliang")
    game.state.player.fortune = True


# （--share／cloudflared 臨時網址的測試 2026-10-25 拿掉：2026-10-13 起固定網域走具名 Tunnel，伺服器不再加 --share；
#   server.start_tunnel 那段碼留給主機端，見 docs/superpowers/feedback/beta-主機端操作.md。）


# ── 主畫面的走法切換（步行／疾行）──────────────────────
# 頁面記著走法、每個請求都帶上 X-Move-Mode；伺服器在行動鎖裡照它排選單（server.MOVE_MODE），從不存檔。

DASH = {"X-Move-Mode": "dash"}
HURRY = {"X-Move-Mode": "hurry"}  # 拿掉的走法：當成步行


def _season_one_now(game, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "season_one", True)
    game.world.mutate_season(lambda season: setattr(season, "season_one", True))


class _ScriptedQueue:
    """照劇本回應每一件：「run」照常叫 job、「busy」丟 Busy（同一個人已經有一件在排或在跑）、「timeout」丟 QueueTimeout
    （排超過 wait 秒還沒輪到，PM 2026-10-06）；劇本用完之後一律 run。"""

    def __init__(self, *script):
        self.script, self.calls = list(script), 0

    def run(self, owner, job, *, fallback, bot=False, wait=30.0):
        step = self.script[self.calls] if self.calls < len(self.script) else "run"
        self.calls += 1
        if step == "busy":
            raise llm_queue.Busy("同一個人已經有一件在排或在跑")
        if step == "timeout":
            raise llm_queue.QueueTimeout("排超過等候的時間還沒輪到")
        return job()


# ── 伺服器推送（線上架構推送計畫）──────────────────────────────────────
# 開關是 Config.push_events（預設關）：關著 server.HUB 是 None，/api/events 是 404，頁面照舊每 10 秒輪詢；
# 開著，每個動作做完通知這個角色開著的其他分頁，背景的看守發現公開的世界變了就通知所有分頁，頁面收到再去抓 /api/main。

ME = "沈青衫".casefold()


@pytest.fixture
def told(monkeypatch):
    """推送開著、但不真的送：記下每一次 notify（名號, 哪一種）。"""
    hub = server_push.PushHub()
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(hub, "notify", lambda name, kind="self": calls.append((name, kind)) or 0)
    monkeypatch.setattr(server, "HUB", hub)
    return calls


def _seal_duel():
    from tianxia.world_state import SealDuel, SealSide

    side = SealSide(name="甲", power=50.0, hp=100.0, hp_cap=100.0)
    return SealDuel(id="1:chishou", shard="chishou", phase="active", starts_real=0.0, challenger=side, holder=side.model_copy(update={"name": "乙"}))
