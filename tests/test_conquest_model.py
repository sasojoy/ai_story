"""領地爭奪第一批 Task 1：設定、蓋章與資料模型（計畫 docs/superpowers/plans/2026-10-20-領地爭奪.md 三、Task 1）。"""
from __future__ import annotations

import pytest

from conftest import real_content
from conquest_kit import conquest_rules, plain_game
from tianxia import conquest
from tianxia.models import BlockDef, ConquestRules
from tianxia.state import WorldState
from tianxia.world_state import stamp_season

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _with_blocks(content):
    """這一條只測蓋章：給一塊區塊就夠（正式的區塊表在 Task 2）。"""
    if not content.scenario.territory.blocks:
        content.scenario.territory.blocks = {"changshe": BlockDef(kind="guan", line="yingru")}
    return content


def test_old_season_json_reads_without_conquest_fields():
    w = WorldState.model_validate_json(WorldState().model_dump_json(exclude={"conquest_on", "conquest"}))
    assert w.conquest_on is False and w.conquest is None


def test_switch_is_on_in_the_real_content_pm_1022():
    """企劃者 2026-10-22「領地爭奪……要打開」：正式內容的開關打開（content/config.json，三種設定覆寫檔都不寫、照它）。以前這一條鎖
    「每一份設定都關著」（裁決 15：三批做完、QA 過、PM 說可以再開）。Config 的預設與測試內容照舊關著；哪幾種季開得了見
    tests/test_conquest_on.py。"""
    for profile in (None, "weekend", "season21", "week7"):
        assert real_content(profile).config.conquest.enabled is True, profile
    assert ConquestRules().enabled is False


def test_stamp_needs_switch_season_one_and_blocks():
    c = _with_blocks(conquest_rules(real_content("season21")))
    season = WorldState()
    stamp_season(season, c, now=0.0)
    assert season.conquest_on is True and conquest.on(c, season)
    c.config.conquest.enabled = False
    assert conquest.on(c, season) is False  # 主機關掉：照關著
    c2 = _with_blocks(conquest_rules(real_content()))  # 14 天：第一季規則關著
    s2 = WorldState()
    stamp_season(s2, c2, now=0.0)
    assert s2.conquest_on is False


def test_stamp_needs_blocks_and_allied_gentry():
    c = conquest_rules(real_content("season21"))
    c.scenario.territory.blocks = {}
    season = WorldState()
    stamp_season(season, c, now=0.0)
    assert season.conquest_on is False  # 沒寫區塊
    c = _with_blocks(conquest_rules(real_content("season21")))
    c.config.haoqiang_allied = False  # 豪強是第三方：割據要佔地，跟領地爭奪對不上（設計 4.1）
    s2 = WorldState()
    stamp_season(s2, c, now=0.0)
    assert s2.conquest_on is False


def test_running_season_keeps_its_stamp():
    game = plain_game("season21")  # 開季時開關關著
    assert game.state.world.conquest_on is False
    game.content.config.conquest.enabled = True  # 開季後才打開：這一季不變
    assert conquest.on(game.content, game.state.world) is False
