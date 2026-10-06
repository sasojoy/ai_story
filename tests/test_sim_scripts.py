"""量測腳本（scripts/fun_run.py 好玩度、scripts/sim_server_bots.py 伺服器假人整季）裡的模擬玩家也要配點：
升級給的屬性點（武學與成長設計 6.2）不分掉的話，整季五項都停在 5，量出來的平衡描述的是「不會配點的玩家」
（CLAUDE.md「第三層」的教訓：量平衡之前先確認機器人會用到那個機制）。伺服器假人本來就在 bot_policy.look_after 裡配點。

兩支腳本都只跑幾步，用測試內容，不驗平衡、只驗「點數有分掉」。"""
from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

from conftest import FixedRandom
from tianxia import team
from tianxia.engine import Game

ROOT = Path(__file__).parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # fun_run 有 dataclass：建類別時要在 sys.modules 查得到自己的模組
    # fun_run 匯入時把 sys.stdout 換成 UTF-8 的包裝：先換成一個用完就丟的，匯入完原樣換回來（不碰 pytest 的擷取）
    with mock.patch.object(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="utf-8")):
        spec.loader.exec_module(module)
    return module


def _spent(game: Game) -> bool:
    p = game.state.player
    return p.stat_points == 0 and max(p.stats[k] for k in team.COMBAT_STATS) > team.BASE_STAT


def test_the_fun_run_player_spends_its_stat_points(content, tmp_path, monkeypatch):
    fun_run = _load("fun_run")
    real_new, games = Game.new, []

    def new(*args, **kwargs):  # 開局就給 3 點：等於已經升了幾級
        game = real_new(*args, **kwargs)
        game.state.player.stat_points = 3
        games.append(game)
        return game

    monkeypatch.setattr(Game, "new", new)
    monkeypatch.setattr(fun_run, "MAX_STEPS", fun_run.SPEND_XINDE_EVERY + 1)  # 第 0 步與第 5 步各輪到一次花用
    fun_run.play(content, 1, tmp_path)
    assert len(games) == 1 and _spent(games[0])


def test_the_server_bot_simulation_humans_spend_their_stat_points(game):
    sim = _load("sim_server_bots")
    game.state.player.stat_points = 3
    sim.human_turn(game, FixedRandom(0.1))  # random() < 0.2：這一輪輪到花用（練成、配點）
    assert _spent(game)


def test_the_companion_measure_script_removes_its_temp_folder(tmp_path):
    """最終審查 M4：量測腳本在暫存目錄開一堆資料庫檔，結束時要清掉，不能每跑一次留一個 measure_companions_* 資料夾。
    只匯入、開一個資料庫就結束（不跑整個量測，太慢），然後看暫存目錄還在不在。"""
    code = (
        f"import sys; sys.path.insert(0, {str(ROOT / 'scripts')!r}); import measure_companions as m; "
        "m.open_world(m.TMP / 'x.db')"
    )
    env = {**os.environ, "TEMP": str(tmp_path), "TMP": str(tmp_path), "TMPDIR": str(tmp_path)}
    subprocess.run([sys.executable, "-c", code], check=True, env=env, cwd=ROOT)
    assert list(tmp_path.glob("measure_companions_*")) == []


def test_the_server_bot_simulation_can_pause_the_season_clock(content, tmp_path, monkeypatch):
    """--pause-at：模擬中途讓賽季時鐘停一段——停著的時候「真人」照樣刷新（同步）、假人程式照樣巡，季的時間一秒都不動、
    假人一個動作都沒做；繼續之後照常跑到收季。測試內容的季壓到幾分鐘（time_scale 400），「真人」整天在線。"""
    sim = _load("sim_server_bots")
    monkeypatch.setattr(sim, "HUMAN_HOURS", range(24))
    content.config.time_scale = 400.0
    resumed, real = [], sim.resume_season_clock  # 「繼續」走 world.resume_season_clock（三步的順序只寫在那一個地方）
    monkeypatch.setattr(sim, "resume_season_clock", lambda *a, **k: resumed.append(a) or real(*a, **k))
    result = sim.run_season(content, tmp_path, seed=0, tick=60.0, pause=(0.05, 0.1))
    assert len(resumed) == 1
    assert result["pause"]["at_day"] is not None
    assert result["pause"]["season_moved"] == 0.0 and result["pause"]["bot_moves"] == 0
    assert result["ended"] and isinstance(result["late_joiners"], int)
