"""領地爭奪第一批 Task 4：中立區塊另一套駐軍（計畫三、Task 4；設計 3.3：佔下之後駐軍對兩邊都照打。隊伍是佔位，待 joy）。"""
from __future__ import annotations

import pytest

from conftest import real_content
from conquest_kit import conquest_game, plain_game
from tianxia import conquest, territory
from tianxia.content import ContentError, validate

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _squads(game, loc):
    return territory.squads_at(game.state.world, game.content, loc)


def test_every_neutral_block_has_a_garrison_without_faction():
    c = real_content("season21")
    t = c.scenario.territory
    neutral = {loc for loc, b in t.blocks.items() if b.kind == "neutral"}
    # 輿圖重製第 1 批：潁川郡在新天下是中立地，但出生點照舊在那裡（第 4 批才搬），新手在城裡練功不該撞上高階駐軍：那一處不放
    assert set(t.neutral_garrison) == neutral - {c.scenario.start_location}
    for squads in t.neutral_garrison.values():
        assert squads and all(c.squads[s].faction is None for s in squads)
        assert all(55 <= c.squads[s].difficulty <= 90 for s in squads)  # 計畫 Task 4：高階獵場的強對手


def test_neutral_garrison_stays_after_capture():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    start = _squads(game, "runan_wilds")  # 新天下的中立地（輿圖重製第 1 批；v1 是南陽郊野）
    assert "nz_luanbing" in start and all(c.squads[s].faction is None for s in start)
    conquest.set_control(w, c, "runan_wilds", "huang")
    assert _squads(game, "runan_wilds") == start  # 駐軍不換成佔領方自己的兵（設計 3.3）
    assert set(_squads(game, "deep_mountain")) >= {"yelang", "heixiong", "nz_tiger"}  # 地點自己的野獸流寇照舊在


def test_faction_block_takes_holder_garrison():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    assert set(_squads(game, "xiaquyang")) == {"taiping_lishi", "shanzei"}  # 新天下黃巾冀州的陣營區塊（v1 是汝南荒野）
    conquest.set_control(w, c, "xiaquyang", "guan")
    assert set(_squads(game, "xiaquyang")) == {"guan_patrol", "jun_bing"}
    assert _squads(game, "zhuo_county") == []  # 沒寫 garrison 的照 Location.enemies


@pytest.mark.parametrize("change", [
    lambda t: t.neutral_garrison.__setitem__("xiaquyang", ["nz_daoke"]),  # 只能寫在開季中立的區塊
    lambda t: t.neutral_garrison.__setitem__("hilltop_wilds", ["louluo"]),  # 要是沒有陣營的隊伍
    lambda t: t.neutral_garrison.__setitem__("hilltop_wilds", ["nobody"]),  # 隊伍要認得
])
def test_validate_rejects_bad_neutral_garrison(change):
    c = real_content("season21")
    change(c.scenario.territory)
    with pytest.raises(ContentError):
        validate(c)


def test_switch_off_squads_unchanged():
    game = plain_game("weekend")
    # 地盤易手：官軍控制的那一組（新天下的舊拔河只剩中原那一條，汝南荒野開季在官軍那一頭；v1 是南陽郊野）
    assert _squads(game, "runan_wilds") == ["guan_patrol", "jun_bing"]
    assert "nz_tiger" not in _squads(game, "deep_mountain")
