"""scripts/measure_battle.py（決戰改版一 Task 6：三招與推力的數字量一場）要一直跑得動：腳本不在引擎裡，
引擎改了它就悄悄壞掉（scripts/simulate.py 就是這樣死掉的）。這裡只跑小場面、不驗平衡，驗「跑得完、結果合理」。"""
from __future__ import annotations

import importlib.util
import io
import os
import random
import sys
from pathlib import Path
from unittest import mock

import pytest

from tianxia.content import load_content

pytestmark = pytest.mark.slow  # 跑整個腳本：合併前的整套才跑（pytest -m "slow or not slow"）

ROOT = Path(__file__).parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("measure_battle", ROOT / "scripts" / "measure_battle.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["measure_battle"] = module
    with mock.patch.object(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="utf-8")):  # 匯入時它會換掉 stdout
        spec.loader.exec_module(module)
    return module


def test_a_small_fight_runs_to_the_end_and_the_numbers_make_sense():
    m = _load()
    content = load_content(ROOT / "content")
    definition = content.battles["changshe_fire"].model_copy(update={"trend_start": 50})
    tuning = content.config.battle
    trend, pushes, rounds = m.run(definition, tuning, 30, 10, m.best, m.anything, seed=1)
    assert 0 <= trend <= 100 and 1 <= rounds <= 9 and len(pushes) == rounds
    assert trend > 50  # 三比一、同一套份量：人多的官軍佔上風
    assert all(abs(p) <= tuning.push_max for p in pushes)
    # 同一個種子跑兩次一樣（量測要能重現）
    assert m.run(definition, tuning, 30, 10, m.best, m.anything, seed=1) == (trend, pushes, rounds)
    # 兩邊人數一樣、策略一樣：不會一面倒
    even, _, _ = m.run(definition, tuning, 20, 20, m.best, m.best, seed=2)
    assert 30 <= even <= 70


def test_every_strategy_picks_a_real_move():
    m = _load()
    content = load_content(ROOT / "content")
    definition = content.battles["changshe_fire"]
    from tianxia import battle_instance as bi
    from tianxia.models import MOVES

    battle = bi.start_muster(definition, now=0)
    bi.join_faction(battle, "甲", "guan", neili_cap=400, power=80, scores=bi.move_scores(content.config.battle, 80, "剛", "柔"))
    p = battle.participants["甲"]
    rng = random.Random(0)
    for strategy in m.STRATEGIES.values():
        for last in ({}, {"強攻": 0.7, "固守": 0.2, "奇襲": 0.1}):
            assert strategy(p, rng, last) in MOVES


def test_the_server_bot_measurement_runs_on_a_temporary_database(tmp_path, monkeypatch, capsys):
    """量伺服器假人那一段：用暫存資料庫、不碰 saves/；印出新手起手的份量與三招各出幾成。"""
    m = _load()
    content = load_content(ROOT / "content")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(m.tempfile, "tempdir", str(scratch))  # 暫存資料夾都開在這裡，才看得出有沒有留下來
    before = os.environ.get("TIANXIA_DB")
    m.measure_server_bots(content, samples=30)
    out = capsys.readouterr().out
    assert "新手起手的份量" in out and "固守" in out and "隨機武學的假人" in out
    assert list(scratch.iterdir()) == []  # 量完不留暫存資料夾（每跑一次留一個，日積月累）
    assert os.environ.get("TIANXIA_DB") == before  # 環境變數也還原
