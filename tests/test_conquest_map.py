"""領地爭奪第一批 Task 2：區塊表、相連與目標（計畫三、Task 2；裁決 2：開季兩邊碰得到的中立地差不多）。
輿圖重製第 1 批（新天下，輿圖簡化設計第三章）把第一批的 v1 區塊表整個換掉：外圈出生州是陣營領地、中原與核心開季中立，
大勢值整個中原一條線（企劃者 2026-10-21）。這一份照新天下釘；三圈本身的守門在 tests/test_map_remake_content.py。"""
from __future__ import annotations

import pytest

from conftest import real_content
from conquest_kit import conquest_game
from tianxia import conquest
from tianxia.content import ContentError, validate
from tianxia.models import BlockDef

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOT_BLOCKS = {"mentor_hut", "jade_cave", "zhuo_militia_hall", "cao_manor", "haozu_fort"}  # 序章、劇情、豪強三處投靠點（設計 4.1）
# 新天下開季碰得到的中立地：官軍從洛陽、南陽往潁川、東郡、汝南，黃巾從冀州、青州往東郡、陳留、汝南（各 5 塊；裁決 2 原本的 6～7 塊是 v1 地圖的數，見計畫）
GUAN_OPEN = {"yingchuan", "guan_camp", "hilltop_wilds", "nanyang_huangjin_camp", "baima_ford"}
HUANG_OPEN = {"baima_ford", "luzhi_camp", "guandu", "jiwu", "qiao_county"}


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
    """裁決 2【企劃者「調整比例」】：開季碰得到的中立地兩邊差不多；中原那一條線兩邊都碰得到。"""
    game = conquest_game("season21")
    guan, huang = _neutral(game, "guan"), _neutral(game, "huang")
    assert guan == GUAN_OPEN and huang == HUANG_OPEN
    assert len(guan) == len(huang) == 5
    blocks = conquest.blocks(game.content)
    assert {blocks[x].line for x in guan | huang} == {"yingru"}  # 整個中原一個總值（暫用 yingru 那一條）


def test_targets_include_adjacent_enemy_blocks_but_never_bases():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    guan = set(conquest.targets(w, c, "guan"))
    assert "taishan_foot" in guan  # 黃巾的陣營區塊、跟南陽官道直通（外環路：相連就能打，裁決 3）
    assert not guan & {"julu_altar", "qingzhou_camp", "guangzong", "wan_city", "dajiangjun_fu"}
    assert "xiaquyang" not in guan  # 跟洛陽之間隔著豪族塢堡（不是區塊）：要先打通旁邊的地
    huang = set(conquest.targets(w, c, "huang"))
    assert "nanyang_road" in huang  # 外環路另一頭
    assert not huang & {"wan_city", "dajiangjun_fu", "julu_altar", "zhuo_county"}  # 自己的、大本營都不是目標


def test_capturable():
    c = real_content("season21")
    assert conquest.capturable(c, "yu_river") and conquest.capturable(c, "nanyang_road") and conquest.capturable(c, "runan")
    assert conquest.capturable(c, "changshe")  # 長社改成中原的高級資源地（不再是大本營）
    assert not conquest.capturable(c, "wan_city") and not conquest.capturable(c, "julu_altar")  # 大本營
    assert not conquest.capturable(c, "guangzong")  # fixed：只照廣宗決戰易手
    assert not conquest.capturable(c, "haozu_fort") and not conquest.capturable(c, "mentor_hut")  # 不是區塊


def test_adjacent_is_direct_roads_between_blocks():
    c = real_content("season21")
    assert set(conquest.adjacent(c, "deep_mountain")) == {"songshan_foot", "lutai"}  # 南華觀不是區塊
    assert set(conquest.adjacent(c, "lutai")) == {"deep_mountain", "puyang", "chenliu_city", "runan"}  # 南華觀不穿過去
    assert set(conquest.adjacent(c, "xiaquyang")) == {"julu_altar", "juma_river"}  # 豪族塢堡不是區塊、不穿過去


def test_locked_block_is_not_a_target_until_unlocked():
    """綠林山寨（劇情開寨才去得了）在新天下是官軍南陽的陣營區塊：讓黃巾先佔下隔壁的新野，它才碰得到。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    conquest.set_control(w, c, "xinye", "huang")
    flag = c.locations["lulin_zhai"].unlock_flag
    w.flags.discard(flag)
    assert "lulin_zhai" not in conquest.targets(w, c, "huang")
    w.flags.add(flag)
    assert "lulin_zhai" in conquest.targets(w, c, "huang")


@pytest.mark.parametrize("change", [
    lambda b: b.__setitem__("wan_city", BlockDef(kind="neutral", line=None)),  # 大本營不能是中立
    lambda b: b.__setitem__("wan_city", BlockDef(kind="huang", line=None)),  # 大本營要是自己陣營的
    lambda b: b.__setitem__("haozu_fort", BlockDef(kind="neutral", line="jizhou")),  # 豪強投靠點不是區塊
    lambda b: b.__setitem__("mentor_hut", BlockDef(kind="guan", line="yingru")),  # 序章專屬不是區塊
    lambda b: b.__setitem__("yu_river", BlockDef(kind="guan", line="nowhere")),  # 線 id 不存在
    lambda b: b.__setitem__("guangzong", BlockDef(kind="neutral", line="jizhou")),  # fixed 要是陣營的種類
    lambda b: b.__setitem__("ghost", BlockDef(kind="neutral", line="jizhou")),  # 地點不存在
    lambda b: (b.__setitem__("jade_cave", BlockDef(kind="neutral", line="yingru")), b.pop("deep_mountain"), b.pop("lutai")),  # 中立沒有直通的區塊
])
def test_validate_rejects_bad_blocks(change):
    c = real_content("season21")
    change(c.scenario.territory.blocks)
    with pytest.raises(ContentError):
        validate(c)
