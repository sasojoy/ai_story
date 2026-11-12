"""極限假人（scripts/limit_bots.py、limit_report.py，企劃者 2026-11-11／11/12）：只驗腳本跑得起來、量得到東西、判準照寫的標，不驗平衡。

整季要跑幾分鐘，標 slow（合併前的整套與每日 03:30 才跑）；判準那幾條是純函式、不碰 Game，照樣標 slow 跟著同一個檔（量測腳本不進平常的整套）。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

ROOT = Path(__file__).parents[2]


def _load(name: str):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _run(level: list[int], key: str = "level", focus: str = "level", final: dict | None = None) -> dict:
    curve = [{"day": i + 1, "me": {key: v}, "bots": {key: {"median": 1, "max": 2}}} for i, v in enumerate(level)]
    return {"profile": "week7", "focus": focus, "label": focus, "hours": 8, "curve": curve,
            "final": final or {key: level[-1]}, "bots_final": {key: {"median": 1, "max": 2}}, "arena_vs_bots": {"mean": 0.5}}


def test_report_flags_rising_fast_cap_and_dominance(tmp_path):
    report = _load("limit_report")
    rising = report.flags("week7", "level", [_run([5, 10, 15, 20, 30, 40])], [], None)
    assert any(tag == "還在漲" for tag, _ in rising)
    capped = report.flags("week7", "level", [_run([20, 50, 50, 50, 50, 50])], [_run([5, 10, 12, 14, 15, 16], focus="control")],
                          {"now": {"level": {"max": 30}}})
    tags = [tag for tag, _ in capped]
    assert "太快封頂" in tags and "輾壓" in tags and "贏過所有測試玩家" in tags
    assert "還在漲" not in tags  # 到了上限不算還在漲
    calm = report.flags("week7", "level", [_run([5, 9, 10, 10, 10, 10])], [_run([5, 9, 10, 10, 10, 10], focus="control")], None)
    assert calm == []


def test_one_focus_plays_a_short_season(monkeypatch):
    limit = _load("limit_bots")
    monkeypatch.setattr(limit, "MAX_REAL_DAYS", 2)  # 兩天就收：只驗跑得起來、每天量得到一列
    result = limit.run_one("week7", "level", seed=1, tick=1800.0, talk_tier="loose", fights=2)
    assert result["turns"] > 0
    assert len(result["curve"]) >= 1
    assert result["final"]["level"] >= 1
    assert set(result["final"]) == set(_load("limit_metrics").FIELDS)
