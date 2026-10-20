"""領地爭奪第一批 Task 2：區塊表、相連與目標（計畫三、Task 2；裁決 2：開季兩邊碰得到的中立地差不多，目標各 6～7 塊）。"""
from __future__ import annotations

import pytest

from conftest import real_content
from conquest_kit import conquest_game
from tianxia import conquest
from tianxia.content import ContentError, validate
from tianxia.models import BlockDef

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOT_BLOCKS = {"mentor_hut", "jade_cave", "zhuo_militia_hall", "cao_manor", "haozu_fort"}  # 序章、劇情、豪強三處投靠點（設計 4.1）
GUAN_OPEN = {"guan_camp", "hilltop_wilds", "deep_mountain", "nanyang_road", "nanyang_wilds", "lulin_zhai", "baima_ford"}
HUANG_OPEN = {"hilltop_wilds", "nanyang_road", "baima_ford", "xiaquyang", "juma_river", "yanshan_foot"}


def _neutral(game, side):
    w, c = game.state.world, game.content
    return {loc for loc in conquest.targets(w, c, side) if conquest.start_kind(w, c, loc) == "neutral"}


def test_conquest_game_is_on():
    game = conquest_game("season21")
    assert conquest.on(game.content, game.state.world)


def test_every_place_but_five_is_a_block():
    c = real_content("season21")
    assert set(c.locations) - set(conquest.blocks(c)) == NOT_BLOCKS


def test_opening_reach_is_balanced():
    """裁決 2【企劃者「調整比例」】：開季碰得到的中立地兩邊差不多（各 6～7 塊），每一條戰線兩邊都碰得到至少一塊。"""
    game = conquest_game("season21")
    guan, huang = _neutral(game, "guan"), _neutral(game, "huang")
    assert guan == GUAN_OPEN and huang == HUANG_OPEN
    assert 6 <= len(guan) <= 7 and 6 <= len(huang) <= 7
    for line in ("yingru", "nanyang", "jizhou"):
        blocks = conquest.blocks(game.content)
        assert any(blocks[x].line == line for x in guan) and any(blocks[x].line == line for x in huang), line


def test_targets_include_adjacent_enemy_blocks_but_never_bases():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    guan = set(conquest.targets(w, c, "guan"))
    assert "runan_wilds" in guan  # 黃巾的陣營區塊、跟長社直通（設計 3.2：相連就能打，裁決 3）
    assert not guan & {"changshe", "huangjin_camp", "guangzong", "julu_altar", "wan_city"}
    assert "xiaquyang" not in guan  # 隔著拒馬河：要先打通旁邊的地
    huang = set(conquest.targets(w, c, "huang"))
    assert not huang & {"changshe", "luzhi_camp", "wan_city", "zhuo_county"}  # 自己的、大本營都不是目標


def test_capturable():
    c = real_content("season21")
    assert conquest.capturable(c, "yu_river") and conquest.capturable(c, "nanyang_road") and conquest.capturable(c, "runan")
    assert not conquest.capturable(c, "changshe") and not conquest.capturable(c, "julu_altar")  # 大本營
    assert not conquest.capturable(c, "guangzong")  # fixed：只照廣宗決戰易手
    assert not conquest.capturable(c, "haozu_fort") and not conquest.capturable(c, "mentor_hut")  # 不是區塊


def test_adjacent_is_direct_roads_between_blocks():
    c = real_content("season21")
    assert set(conquest.adjacent(c, "deep_mountain")) == {"songshan_foot"}  # 南華觀不是區塊
    assert set(conquest.adjacent(c, "xiaquyang")) == {"julu_altar", "juma_river"}  # 豪族塢堡不是區塊、不穿過去


def test_locked_block_is_not_a_target_until_unlocked():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    flag = c.locations["lulin_zhai"].unlock_flag
    w.flags.discard(flag)
    assert "lulin_zhai" not in conquest.targets(w, c, "guan")
    w.flags.add(flag)
    assert "lulin_zhai" in conquest.targets(w, c, "guan")


@pytest.mark.parametrize("change", [
    lambda b: b.__setitem__("changshe", BlockDef(kind="neutral", line="yingru")),  # 大本營不能是中立
    lambda b: b.__setitem__("changshe", BlockDef(kind="huang", line="yingru")),  # 大本營要是自己陣營的
    lambda b: b.__setitem__("haozu_fort", BlockDef(kind="neutral", line="jizhou")),  # 豪強投靠點不是區塊
    lambda b: b.__setitem__("mentor_hut", BlockDef(kind="guan", line="yingru")),  # 序章專屬不是區塊
    lambda b: b.__setitem__("yu_river", BlockDef(kind="guan", line="nowhere")),  # 線 id 不存在
    lambda b: b.__setitem__("guangzong", BlockDef(kind="neutral", line="jizhou")),  # fixed 要是陣營的種類
    lambda b: b.__setitem__("ghost", BlockDef(kind="neutral", line="jizhou")),  # 地點不存在
    lambda b: b.__setitem__("jade_cave", BlockDef(kind="neutral", line="yingru")) or b.pop("deep_mountain"),  # 中立沒有直通的區塊
])
def test_validate_rejects_bad_blocks(change):
    c = real_content("season21")
    change(c.scenario.territory.blocks)
    with pytest.raises(ContentError):
        validate(c)
