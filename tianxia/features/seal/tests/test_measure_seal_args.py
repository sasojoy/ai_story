"""scripts/measure_seal.py 的 --mandate-mc --hide --find --explores --own-share（領地爭奪第三批 B，計畫 Task 15）：
參數解析、公式、跟舊的「每季現世率」對得上、Config 的預設落在企劃者要的 16～20 季。腳本不在引擎裡，引擎改了它就悄悄壞掉。"""
from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from unittest import mock

import pytest

from conftest import real_content

ROOT = Path(__file__).parents[4]  # 全部拆包第 27 批從 tests/season/ 搬進玉璽包的 tests/（只改層數）


@pytest.fixture(scope="module")
def measure():
    spec = importlib.util.spec_from_file_location("measure_seal", ROOT / "scripts" / "measure_seal.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["measure_seal"] = module
    with mock.patch.object(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="utf-8")):  # 匯入時它會換掉 stdout
        spec.loader.exec_module(module)
    return module


def test_a_certain_find_in_one_explore_is_the_old_season_rate(measure):
    """hide=0.35、find=1、explores=1 等於舊的「每季現世率 0.35」：結果一模一樣（同一個種子、同一個蒙地卡羅）。自家的比例不改變它。"""
    assert measure.season_rate(0.35, 1.0, 1) == pytest.approx(0.35)
    assert measure.season_rate(0.35, 1.0, 1, own_share=0.5, own_scale=1.5) == pytest.approx(0.35)
    [row] = measure.cache_rows(0.35, 1.0, [1], 0.5, 1.5, trials=2000, seed=1)
    old = measure.mandate_mc(0.35, trials=2000, seed=1)
    assert {k: row[k] for k in old} == old and row["p_find"] == pytest.approx(1.0)


def test_the_season_rate_grows_with_explores_and_with_the_home_share(measure):
    rates = [measure.season_rate(0.4, 0.005, n, 0.5, 1.5) for n in (150, 300, 600, 1000)]
    assert rates == sorted(rates) and rates[-1] <= 0.4  # 探索越多越容易撿到，但藏的機率是上限
    alone = measure.season_rate(0.4, 0.005, 300, 0.0, 1.5)
    home = measure.season_rate(0.4, 0.005, 300, 1.0, 1.5)
    assert alone < measure.season_rate(0.4, 0.005, 300, 0.5, 1.5) < home
    assert measure.season_rate(0.4, 0.005, 0) == 0.0  # 沒人去探索就撿不到
    assert measure.season_rate(0.4, 0.9, 5, 1.0, 5.0) == pytest.approx(0.4)  # 機率夾在 1 以下，不會爆


def test_a_find_chance_of_zero_never_completes_and_does_not_hang(measure):
    [row] = measure.cache_rows(0.4, 0.0, [300], 0.5, 1.5, trials=50)
    assert row["mean"] == float("inf") and row["rate"] == 0.0


def test_the_flags_parse_and_fall_back_to_the_config(measure):
    parser = measure.build_parser()
    content = real_content("season21")
    cfg = content.config.seal.cache
    plain = parser.parse_args(["--mandate-mc"])
    assert not measure.cache_mode(plain)  # 舊的 --emerge-rate 那一套照舊
    args = parser.parse_args(["--mandate-mc", "--hide", "0.4", "--find", "0.005", "--explores", "150", "300", "--own-share", "0.5"])
    assert measure.cache_mode(args)
    assert measure.cache_args(args, content) == (0.4, 0.005, [150, 300], 0.5, cfg.own_scale)
    only = parser.parse_args(["--mandate-mc", "--explores", "300"])
    assert measure.cache_args(only, content) == (cfg.hide_chance, cfg.find_chance, [300], 0.5, cfg.own_scale)
    assert measure.cache_args(parser.parse_args(["--mandate-mc", "--hide", "0.5"]), content)[2] == [150, 300, 600, 1000]


def test_the_config_defaults_land_in_about_seven_seasons(measure):
    """企劃者 2026-10-20 原本定湊滿七片平均約 16～20 季（藏 40%）；主機普查第 7～9 季三季沒人拿到，Joy 2026-11-10「先這樣改」：
    每季必藏一片（hide_chance 1），藏處一季被探索 200 次以上就是 7～8 季湊齊（7 ÷ hide_chance 是快不過的季數）。"""
    cfg = real_content("season21").config.seal.cache
    assert cfg.hide_chance == 1.0
    rows = measure.cache_rows(cfg.hide_chance, cfg.find_chance, [200, 300, 600, 1000], 0.5, cfg.own_scale, trials=4000, seed=1)
    for row in rows:
        assert 7 <= row["mean"] <= 8, (row["explores"], row["mean"])


def test_the_cache_table_prints_each_row(measure, capsys):
    rows = measure.cache_rows(0.4, 0.005, [150, 300], 0.5, 1.5, trials=200, seed=1)
    measure.print_cache_mc(rows)
    out = capsys.readouterr().out
    assert out.count("藏處一季探索") == 2 and "每季現世" in out and "平均" in out
    measure.print_cache_mc(measure.cache_rows(0.4, 0.0, [300], 0.5, 1.5, trials=10))
    assert "永遠湊不齊" in capsys.readouterr().out
