"""減法季的開關（減法季批 0，設計稿第十章；Config.jianfa 加開季時蓋的章，讀的時候走 rules.jianfa）：
season21、week7 新開的季蓋章，週末設定不蓋；正在跑的季照它自己的章；主機把開關關掉時一律照關著。"""
from __future__ import annotations

from pathlib import Path

import pytest

from tianxia import rules
from tianxia.content import load_content
from tianxia.world_state import fresh_season, stamp_season

pytestmark = pytest.mark.slow  # 載三份正式內容

CONTENT = Path(__file__).resolve().parent.parent / "content"


@pytest.mark.parametrize(("profile", "on"), [("season21", True), ("week7", True), ("weekend", False), (None, False)])
def test_which_settings_stamp_the_season(profile, on):
    content = load_content(CONTENT, profile=profile)
    season = fresh_season(content, now=1_800_000_000.0)
    assert content.config.jianfa.enabled is on
    assert season.jianfa_on is on and rules.jianfa(content, season) is on


def test_a_running_season_keeps_its_stamp_and_the_host_switch_wins(content):
    assert content.config.jianfa.enabled is False  # 測試內容關著
    season = fresh_season(content)
    assert season.jianfa_on is False and rules.jianfa(content, season) is False
    content.config.jianfa.enabled = True
    assert rules.jianfa(content, season) is False  # 打開時正在跑的季沒有章，照舊
    stamp_season(season, content)
    assert season.jianfa_on is True and rules.jianfa(content, season) is True
    content.config.jianfa.enabled = False
    assert season.jianfa_on is True and rules.jianfa(content, season) is False  # 主機的緊急開關
    assert rules.jianfa(content, None) is False
