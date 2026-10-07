"""T11：第一季濃縮版的整季模擬腳本（計畫 2026-10-05-T11-整季模擬）——跑得完、輸出欄位齊、卡住會標出來、驗收照兩條判。

用真實內容、週末設定，季長縮到 0.25 天（一週 30 分鐘現實時間），每陣營 1 個假人：只驗腳本本身，不驗平衡。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tianxia.content import load_content

pytestmark = pytest.mark.slow  # 跑整個腳本：合併前的整套才跑（pytest -m "slow or not slow"）

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location("sim_season_one", ROOT / "scripts" / "sim_season_one.py")
sim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sim)

ONE_EACH = {"guan": 1, "huang": 1, "haoqiang": 1}
FIELDS = {"weekly", "events", "missing", "showdowns", "orders", "promoted", "ending", "ending_id", "end_week", "ended",
          "stuck", "checks", "geju_first", "roster"}


def _content(days: float = 0.25):
    c = load_content(ROOT / "content", profile="weekend")
    c.config.season_days = days
    return c


def test_a_short_season_runs_to_the_end_with_every_field(tmp_path):
    result = sim.run_season(_content(), tmp_path / "sim.db", seed=1, targets=ONE_EACH, hours=8, tick=120)
    assert FIELDS <= set(result)
    assert result["ended"] and not result["stuck"] and result["ending"]
    assert result["events"]["uprising"]["result"] == "fixed"
    assert set(result["weekly"][1]) == {"yingru", "nanyang", "jizhou", "geju"}
    assert set(result["orders"]) == set(ONE_EACH) and set(result["promoted"]) == set(ONE_EACH)
    assert set(result["showdowns"]) == {"changshe_fire", "wancheng", "guangzong"}
    assert result["events"].keys().isdisjoint(result["missing"])
    assert set(result["geju_first"]) == {85, 100} and isinstance(result["roster"], int)  # 割據首次到 85／100：(週, 時間章) 或 None
    for hit in result["geju_first"].values():
        assert hit is None or (isinstance(hit[0], int) and isinstance(hit[1], str))
    assert "割據首次到" in sim.summary(1, result)
    assert "第" in sim.summary(1, result)  # 印得出來


def test_reports_stuck_when_out_of_time(tmp_path):
    """RF1：給的時間不夠一季：停在上限、標成卡住，不無限跑。"""
    result = sim.run_season(_content(), tmp_path / "sim.db", seed=1, targets=ONE_EACH, hours=0.5, tick=120)
    assert (result["ended"], result["stuck"]) == (False, True)


def test_a_season_exactly_as_long_as_hours_still_ends(tmp_path):
    """季長剛好等於 hours：最後一輪要落在 hours 那一刻（上限含頭含尾），不然停在差一輪就收季的地方、被誤標成卡住。
    0.25 天＝6 現實小時。"""
    result = sim.run_season(_content(), tmp_path / "sim.db", seed=1, targets=ONE_EACH, hours=6, tick=120)
    assert (result["ended"], result["stuck"]) == (True, False)


def test_acceptance_flags():
    """RF2：只判兩條——第 6 週以前沒有決定性勝利、三條戰線的週末中位數在 20～80。"""
    weekly = {w: {"yingru": 50, "nanyang": 40, "jizhou": 60, "geju": 20} for w in range(1, 11)}
    content = _content()
    ok = sim.checks({"weekly": weekly, "ending_id": "s1_warlords", "end_week": 10}, content)
    assert ok["passed"] and ok["no_early_decisive"] and ok["medians"] == {"yingru": 50, "nanyang": 40, "jizhou": 60}
    early = sim.checks({"weekly": weekly, "ending_id": "s1_warlords", "end_week": 5}, content)
    assert not early["no_early_decisive"] and not early["passed"]
    lopsided = {w: {**v, "jizhou": 90} for w, v in weekly.items()}
    assert not sim.checks({"weekly": lopsided, "ending_id": "s1_gentry", "end_week": 12}, content)["passed"]
