"""引擎層壓測（線上架構設計 9.1 第 1 層、9.2）：在程式裡直接走伺服器做動作的那一條路（server.act：拿行動鎖、
重讀角色、同步、做動作、存檔），量每個動作握鎖多久、每秒做得了幾個、資料庫多大、記憶體尖峰，以及 N 個角色時
管理者收季要多久。不經過網路，所以量到的是「伺服器本身」的上限；網路層另見 load_web.py。

一律開新的暫存資料庫（--workdir），不碰 saves/ 與試玩伺服器。模型用不到：選單裡會叫模型的選項（對話、交友、求見、
大場面）一律跳過，那是網路層的事；每個角色的 Game 也拿掉 client（跟伺服器假人一樣），內容設定的 ollama_url 換成
一個沒人聽的埠，萬一哪裡漏了也不會碰到真的 Ollama。

握鎖時間量的是「行動鎖那一筆寫入交易」：從拿到寫入權（BEGIN IMMEDIATE 回來）到 COMMIT 完成，含進鎖重讀角色、
同步、動作、存檔與 COMMIT 寫進磁碟（synchronous = FULL）。這一段別的玩家與假人都在等。

這一支是單一執行緒，不會有人排隊：「每個動作（含排隊）」比握鎖時間多的只是鎖外那一點點（挑選項、建 Game），
真正的排隊要看網路層（load_web.py）。tracemalloc 會讓 Python 慢上四成左右，所以量時間時加 --no-tracemalloc；
記憶體另外有整個程序的尖峰（Windows 才有）。每個動作是從「現在選單上能按的選項」裡隨機挑一個，角色都很年輕
（平均每個角色只做了幾個到十幾個動作、江湖紀錄與存檔都還小），所以數字是新角色的下限；玩了好幾個小時的角色存檔會更大、讀寫更久。

--polls-per-action N：每個動作之後穿插 N 個「畫面請求」（/api/main 做的事：server.poll_main，同步、存檔與 main_view
在一把行動鎖裡做完；2026-10-06 之前是 act 加 look 各拿一次），握鎖時間另外記在 poll_locked。預設 0＝只量動作。真的封測時每個在線的人每 10 秒就打一次 /api/main，
所以這一項才是行動鎖上量最大的負擔。

執行：.venv/Scripts/python.exe scripts/load_engine.py --characters 3000 --actions 20000 --end-season --out <檔>
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import json
import os
import random
import sys
import tempfile
import time
import traceback
import tracemalloc
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import load_common  # noqa: E402

SKIP_PREFIXES = ("talk:", "call:", "act:socialize", "act:challenge:", "choice:free")  # 會叫模型的，引擎層不做
ENV_KEYS = ("TIANXIA_DB", "TIANXIA_PROFILE")  # run() 會動的環境變數
NO_MODEL_URL = "http://127.0.0.1:1"  # 沒人聽的埠：真的有地方漏叫了模型，也只會連線失敗，碰不到真的 Ollama（11434）
AFTER_END_ACTIONS = 3  # 收季之後再讓幾個角色做動作，確認伺服器還能回應
PROTECTED_DIRS = ("saves", ".local", "tianxia-play")  # 正式資料、本機設定、試玩伺服器的資料夾：壓測的資料庫不能放在底下


def check_workdir(workdir: Path) -> Path:
    """壓測的暫存資料庫只能放在全新的、不是正式或試玩資料的地方：路徑上不能有 saves、.local、tianxia-play
    這幾層，資料夾裡也不能已經有 tianxia.db。有問題就丟 ValueError（什麼都還沒建、沒動環境變數）。"""
    resolved = Path(workdir).resolve()
    for part in resolved.parts:
        if part.casefold() in PROTECTED_DIRS:
            raise ValueError(f"壓測的資料庫不能放在 {part} 底下（那裡是正式或試玩的資料）：{resolved}")
    if (resolved / "tianxia.db").exists():
        raise ValueError(f"這個資料夾裡已經有 tianxia.db（正式或試玩的資料庫），壓測不能用：{resolved}")
    return resolved


def _note_error(errors: dict[str, int], samples: dict[str, str], exc: BaseException) -> None:
    """記一次出錯：次數照例外的類型算，每個類型另外留第一次的完整追蹤（只有次數的話，兩萬個動作之後看不出是什麼壞了）。"""
    name = type(exc).__name__
    errors[name] = errors.get(name, 0) + 1
    samples.setdefault(name, "".join(traceback.format_exception(exc))[-1500:])


def _import_server(db_path: Path):
    """server 在 import 時就讀環境變數、載入內容；要在 import 之前把資料庫指到暫存檔。"""
    os.environ["TIANXIA_DB"] = str(db_path)
    os.environ.setdefault("TIANXIA_PROFILE", "weekend")
    import server  # noqa: PLC0415

    return server


@contextlib.contextmanager
def lock_timer(db, clock=time.perf_counter) -> Iterator[list[float]]:
    """在 db.transaction 上裝計時：每一筆「最外層」的寫入交易（也就是行動鎖）握了多久就往清單加一筆。
    計時從拿到寫入權（BEGIN IMMEDIATE 回來）開始、到 COMMIT 完成為止：等別人放掉寫入權的時間不算，COMMIT 寫進磁碟的
    時間要算（兩頭各有一條測試釘住）；巢狀在裡面的交易（角色存檔、全服狀態的寫入）不另外算。
    離開時拆掉。不改 server.py：伺服器的 _locked 一律走 game.world.action_lock() → db.transaction()。
    clock 只給測試換成假時鐘用。"""
    held: list[float] = []
    real = db.transaction  # 綁好的原方法

    @contextlib.contextmanager
    def timed(timeout: float | None = None):
        outermost = not db.writing()
        start = None
        try:
            with real(timeout) as conn:  # 進來＝拿到寫入權；離開＝COMMIT 做完
                start = clock()
                yield conn
        finally:
            if outermost and start is not None:
                held.append(clock() - start)

    db.transaction = timed
    try:
        yield held
    finally:
        del db.transaction


def one_action(server, game, rng: random.Random) -> float:
    """照伺服器的路做一個動作（server.act），回傳握著行動鎖的秒數。從選單上能按的選項隨機挑一個。"""

    def pick(g):
        options = [o.id for o in g.options(odds=False) if o.enabled and not o.id.startswith(SKIP_PREFIXES)]
        return g.choose(rng.choice(options)) if options else []

    with lock_timer(game.world.db) as held:
        server.act(game, pick)
    return sum(held)


def one_poll(server, game) -> float:
    """/api/main 做的事（server.poll_main）：同步、存檔與 main_view 在同一把行動鎖裡做完；回傳握鎖的秒數。
    （2026-10-06 之前是 act 加 look 各拿一次鎖，這個函式回的是兩次合計；舊的數字跟現在的不能直接比。）"""
    with lock_timer(game.world.db) as held:
        server.poll_main(game)
    return sum(held)


def _peak_working_set_mb() -> float | None:
    """這個程序到目前為止的記憶體尖峰（Windows 的 PeakWorkingSetSize）；不是 Windows 就回 None。
    tracemalloc 只看得到 Python 自己配的記憶體（看不到 SQLite 的快取、C 擴充），封測的記憶體目標是整個程序的，所以兩個都記。"""
    if sys.platform != "win32":
        return None

    class Counters(ctypes.Structure):  # PROCESS_MEMORY_COUNTERS：前兩個是 DWORD，後面都是 SIZE_T
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(
        ctypes.c_void_p(kernel32.GetCurrentProcess()), ctypes.byref(counters), counters.cb)
    return counters.PeakWorkingSetSize / 1e6 if ok else None


def _file_mb(db_path: Path) -> float:
    """資料庫檔加上還沒併回去的 WAL，單位 MB。"""
    return sum(p.stat().st_size for p in (db_path, Path(f"{db_path}-wal")) if p.exists()) / 1e6


def run(
    characters: int, actions: int, seed: int, workdir: Path, end_season: bool,
    polls_per_action: int = 0, trace_memory: bool = True,
) -> dict:
    if characters < 1:
        raise ValueError("characters 至少要 1 個角色：沒有角色就沒有人可以做動作")
    db_path = check_workdir(workdir) / "load.db"  # 先擋：什麼都還沒建、沒動環境變數
    env_before = {key: os.environ.get(key) for key in ENV_KEYS}  # _import_server 會動這兩個，跑完要原樣放回去
    server = _import_server(db_path)
    config = server.CONTENT.config
    config_before = (config.auto_open_first_season, list(config.admins), config.ollama_url)
    config.auto_open_first_season = True  # 全服第一次開局直接開季，不必管理者按開季
    config.ollama_url = NO_MODEL_URL
    server.GAMES.clear()  # 同一個程序裡別的測試留下的角色（它們的 Game 指向別的資料庫）
    rng = random.Random(seed)
    names = [f"壓測{i:04d}" for i in range(characters)]
    locked: list[float] = []
    total: list[float] = []
    poll_locked: list[float] = []
    poll_total: list[float] = []
    errors: dict[str, int] = {}
    error_samples: dict[str, str] = {}
    stopped, end_seconds, end_ok, after_ok, elapsed = False, None, None, None, None
    started = time.perf_counter()
    if trace_memory:
        tracemalloc.start()
    try:
        try:  # Ctrl+C 在哪一段都接住：印出到目前為止的結果（建角色與收季那一下也一樣）
            from tianxia.characters import open_characters  # noqa: PLC0415
            from tianxia.database import open_database  # noqa: PLC0415
            from tianxia.engine import Game  # noqa: PLC0415

            store = open_characters()
            with open_database().transaction():  # 建幾千個角色：一筆交易寫完，不要每個角色各 COMMIT 一次
                for name in names:
                    if not store.exists(name):
                        store.save(Game.new(server.CONTENT, name, rng=random.Random(rng.random())).state)
            prepared: set[str] = set()

            def player(name: str):
                game = server.game_for(name)
                if name not in prepared:  # 每個角色一份固定種子的亂數、不叫模型（跟伺服器假人一樣 client 是 None）
                    game.rng = random.Random(rng.random())
                    game.client = None
                    prepared.add(name)
                return game

            started = time.perf_counter()  # 建角色不算：量的是做動作
            for _ in range(actions):
                game = player(rng.choice(names))
                t0 = time.perf_counter()
                try:
                    held = one_action(server, game, rng)
                except Exception as exc:  # noqa: BLE001  一個動作出錯記下來、不毀掉整輪
                    _note_error(errors, error_samples, exc)
                else:
                    locked.append(held)
                    total.append(time.perf_counter() - t0)
                for _ in range(polls_per_action):
                    game = player(rng.choice(names))
                    t0 = time.perf_counter()
                    try:
                        held = one_poll(server, game)
                    except Exception as exc:  # noqa: BLE001
                        _note_error(errors, error_samples, exc)
                    else:
                        poll_locked.append(held)
                        poll_total.append(time.perf_counter() - t0)
            elapsed = max(time.perf_counter() - started, 1e-9)
            if end_season:
                config.admins = [names[0]]
                admin = player(names[0])
                t0 = time.perf_counter()
                server.act(admin, lambda g: g.admin_end_season(time.time()))
                end_seconds = time.perf_counter() - t0
                end_ok = admin.world.season_phase() == "resting"
                after_ok = True  # 收季之後別的角色照常做動作（休季的選單只有一個灰掉的選項，動作本身仍然同步、存檔）
                for _ in range(AFTER_END_ACTIONS):
                    try:
                        one_action(server, player(rng.choice(names)), rng)
                    except Exception as exc:  # noqa: BLE001
                        _note_error(errors, error_samples, exc)
                        after_ok = False
        except KeyboardInterrupt:
            stopped = True
            after_ok = None  # 收季之後的確認做到一半被打斷：不知道（收季那一下量到了就照記，沒量到的本來就是 None）
            if elapsed is None:
                elapsed = max(time.perf_counter() - started, 1e-9)
        peak = tracemalloc.get_traced_memory()[1] if trace_memory else None
        report = {
            "characters": characters, "actions_done": len(locked), "locked": locked, "total": total,
            "poll_locked": poll_locked, "poll_total": poll_total, "polls_per_action": polls_per_action,
            "rate": len(locked) / elapsed, "lock_busy": (sum(locked) + sum(poll_locked)) / elapsed,
            "db_mb": _file_mb(db_path), "peak_mb": None if peak is None else peak / 1e6,
            "peak_ws_mb": _peak_working_set_mb(), "errors": errors, "error_samples": error_samples,
            "end_season_seconds": end_seconds, "end_season_ok": end_ok, "after_end_season_ok": after_ok,
            "stopped_early": stopped,
        }
    finally:
        if trace_memory:
            tracemalloc.stop()
        config.auto_open_first_season = config_before[0]
        config.admins = config_before[1]
        config.ollama_url = config_before[2]
        server.GAMES.clear()
        for key, value in env_before.items():  # 原本沒設的要刪掉，不能留著 setdefault 補上的值
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="引擎層壓測：直接走伺服器做動作的路，量握鎖時間與吞吐")
    parser.add_argument("--characters", type=int, default=300)
    parser.add_argument("--actions", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--end-season", action="store_true", help="最後用管理者收季，量季末結算的時間")
    parser.add_argument("--polls-per-action", type=int, default=0, help="每個動作之後穿插幾個畫面請求（/api/main）")
    parser.add_argument("--no-tracemalloc", action="store_true", help="不開 tracemalloc（它會拖慢 Python，量握鎖時間時關掉比較準）")
    parser.add_argument("--workdir", default=None, help="暫存資料庫放哪（預設開一個新的暫存資料夾）")
    parser.add_argument("--out", default=None, help="結果 JSON 寫到哪")
    args = parser.parse_args(argv)
    if args.characters < 1 or args.actions < 0 or args.polls_per_action < 0:
        print("--characters 至少要 1，--actions 與 --polls-per-action 不能是負的", file=sys.stderr)
        return 2
    if args.workdir:
        try:
            check_workdir(Path(args.workdir))  # 先擋，再建資料夾
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 2
    workdir = Path(args.workdir or tempfile.mkdtemp(prefix="tianxia-load-"))
    workdir.mkdir(parents=True, exist_ok=True)
    report = run(
        args.characters, args.actions, args.seed, workdir, args.end_season,
        polls_per_action=args.polls_per_action, trace_memory=not args.no_tracemalloc,
    )
    errors = sum(report["errors"].values())
    print(load_common.summarize("握鎖時間", report["locked"], errors))
    print(load_common.summarize("每個動作（含排隊）", report["total"], errors))
    if report["poll_locked"]:
        print(load_common.summarize("畫面請求握鎖時間（一把行動鎖）", report["poll_locked"], 0))
    memory = "" if report["peak_mb"] is None else f"；Python 記憶體尖峰 {report['peak_mb']:.1f} MB（tracemalloc）"
    ws = "" if report["peak_ws_mb"] is None else f"；整個程序記憶體尖峰 {report['peak_ws_mb']:.0f} MB"
    mixed = "（連同穿插的畫面請求一起算時間，不是只做動作的上限）" if report["polls_per_action"] else ""
    print(f"每秒 {report['rate']:.1f} 個動作{mixed}；行動鎖忙了 {report['lock_busy'] * 100:.0f}%；"
          f"資料庫 {report['db_mb']:.1f} MB（含還沒併回去的 WAL，可能比併回之後大）{memory}{ws}")
    if report["errors"]:
        print(f"動作出錯：{report['errors']}")
        for name, sample in report["error_samples"].items():  # 每種例外第一次的追蹤（完整的在 --out 的 JSON 裡）
            print(f"  {name}：{sample.strip().splitlines()[-1]}")
    if report["end_season_seconds"] is not None:
        done = "" if report["end_season_ok"] else "（沒有真的收成：賽季不在進行中）"
        after = {True: "還能照常回應", False: "有動作出錯", None: "還沒確認完就被打斷了"}[report["after_end_season_ok"]]
        print(f"{args.characters} 個角色時收季花了 {report['end_season_seconds']:.2f} 秒{done}；收季之後{after}")
    if report["stopped_early"]:
        print("（中途停下來了：上面是到停下來為止的結果）")
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
