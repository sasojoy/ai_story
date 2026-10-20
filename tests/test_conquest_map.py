"""領地爭奪第一批 Task 2：區塊表、相連與目標（計畫三、Task 2；裁決 2：開季兩邊碰得到的中立地差不多，目標各 6～7 塊）。

區塊表 v3（輿圖簡化設計 3.2，計畫「區塊表 v3」那一節；企劃者 10/20「這些灰色沒人的地方有些根本只有連接在黃巾軍」）：每一塊中立地兩軍
各有一條路從自家開季持有的領地走得到（只走自家與中立的區塊），開季兩邊直通的中立地差在一塊以內。"""
from __future__ import annotations

import pytest

from conftest import real_content
from conquest_kit import conquest_game
from tianxia import conquest
from tianxia.content import ContentError, validate
from tianxia.models import BlockDef

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOT_BLOCKS = {"mentor_hut", "jade_cave", "zhuo_militia_hall", "cao_manor", "haozu_fort"}  # 序章、劇情、豪強三處投靠點（設計 4.1）
GUAN_OPEN = {"hilltop_wilds", "runan_wilds", "nanyang_road", "nanyang_wilds", "yu_river", "lulin_zhai", "baima_ford", "juma_river"}
HUANG_OPEN = {"runan_wilds", "nanyang_road", "nanyang_wilds", "yu_river", "lulin_zhai", "baima_ford", "xiaquyang"}


def _neutral(game, side):
    w, c = game.state.world, game.content
    return {loc for loc in conquest.targets(w, c, side) if conquest.start_kind(w, c, loc) == "neutral"}


def _reach(c, side):
    """從 side 開季持有的區塊（大本營、fixed 也算）出發、只走自家與中立的區塊走得到的區塊（設計 3.2「相連」：有路直通，
    不穿過不是區塊的地點；conquest.adjacent）。只看內容，不看劇情開放了沒。"""
    table = conquest.blocks(c)
    seen = {loc for loc, block in table.items() if block.kind == side}
    todo = list(seen)
    while todo:
        for nxt in conquest.adjacent(c, todo.pop()):
            if nxt not in seen and table[nxt].kind in (side, conquest.NEUTRAL):
                seen.add(nxt)
                todo.append(nxt)
    return seen


def test_conquest_game_is_on():
    game = conquest_game("season21")
    assert conquest.on(game.content, game.state.world)


def test_every_place_but_five_is_a_block():
    c = real_content("season21")
    assert set(c.locations) - set(conquest.blocks(c)) == NOT_BLOCKS


def test_opening_reach_is_balanced():
    """裁決 2【企劃者「調整比例」】：開季碰得到的中立地兩邊差不多（目標各 6～7 塊、差在一塊以內），每一條戰線兩邊都碰得到至少一塊。
    PM 2026-10-21 收了宛城—綠林山寨的山路、綠林山寨留中立（高級獵場盡量留給兩邊搶）：官軍 8、黃巾 7。"""
    game = conquest_game("season21")
    guan, huang = _neutral(game, "guan"), _neutral(game, "huang")
    assert guan == GUAN_OPEN and huang == HUANG_OPEN
    assert (len(guan), len(huang)) == (8, 7)
    assert abs(len(guan) - len(huang)) <= 1
    for line in ("yingru", "nanyang", "jizhou"):
        blocks = conquest.blocks(game.content)
        assert any(blocks[x].line == line for x in guan) and any(blocks[x].line == line for x in huang), line


def test_every_neutral_block_is_reachable_by_both_armies():
    """輿圖簡化設計 3.2（企劃者 10/20「這些灰色沒人的地方有些根本只有連接在黃巾軍」）：每一塊中立地，兩軍各有一條路從自家開季持有的
    領地走得到，只走自家與中立的區塊。區塊表 v2 有七塊只有一邊走得到（官軍大營、嵩山深處、南陽郊野、綠林山寨只有官軍；下曲陽、拒馬河畔、
    燕山腳只有黃巾）。"""
    c = real_content("season21")
    neutral = {loc for loc, block in conquest.blocks(c).items() if block.kind == conquest.NEUTRAL}
    assert neutral
    for side in conquest.SIDES:
        assert not neutral - _reach(c, side), side


def test_every_neutral_block_has_foes_for_both_armies():
    """每一塊中立地都找得到對手（中立駐軍＋地點自己的流寇野獸，conquest.sortie_foes）：開季兩軍到那裡出陣攻都打得到。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    for loc, block in conquest.blocks(c).items():
        if block.kind != conquest.NEUTRAL:
            continue
        assert c.scenario.territory.neutral_garrison.get(loc), loc
        for side in conquest.SIDES:
            assert conquest.sortie_foes(w, c, loc, side), (loc, side)


def test_targets_include_adjacent_enemy_blocks_but_never_bases():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    huang = set(conquest.targets(w, c, "huang"))
    assert "zhuo_county" in huang  # 官軍的陣營區塊、跟鉅鹿道壇直通（設計 3.2：相連就能打，裁決 3）
    assert not huang & {"changshe", "luzhi_camp", "wan_city", "guangzong", "julu_altar"}  # 自己的、大本營都不是目標
    assert "juma_river" not in huang  # 隔著下曲陽：要先打通旁邊的地
    guan = set(conquest.targets(w, c, "guan"))
    assert not guan & {"changshe", "huangjin_camp", "guangzong", "julu_altar", "wan_city", "nanyang_huangjin_camp", "zhuo_county"}
    assert "xiaquyang" not in guan  # 隔著拒馬河：要先打通旁邊的地


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
    assert "lulin_zhai" not in conquest.targets(w, c, "guan") and "lulin_zhai" not in conquest.targets(w, c, "huang")
    w.flags.add(flag)
    assert "lulin_zhai" in conquest.targets(w, c, "guan") and "lulin_zhai" in conquest.targets(w, c, "huang")


def test_validate_names_the_neutral_block_an_army_cannot_reach():
    """PM 2026-10-21：「每塊中立兩軍都走得到」寫進載入檢查，錯誤訊息寫是哪一塊、哪一軍走不到。新野給官軍之後，黃巾在南陽西半邊沒有
    立足點：淯水河畔、南陽郊野、綠林山寨黃巾都走不到。"""
    c = real_content("season21")
    c.scenario.territory.blocks["xinye"] = BlockDef(kind="guan", line="nanyang")
    with pytest.raises(ContentError) as caught:
        validate(c)
    text = str(caught.value)
    huang = c.scenario.faction_name("huang")
    for loc in ("yu_river", "nanyang_wilds", "lulin_zhai"):
        assert f"{loc}（{c.locations[loc].name}）：{huang}走不到這塊中立地" in text
    assert "nanyang_road（" not in text  # 南陽官道黃巾照樣走得到（南陽黃巾營直通）


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
