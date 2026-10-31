"""領地爭奪的規則：區塊與相連、控制方與大勢、駐軍、陣營加成、每天的鐘與換天、開關與蓋章、搶不下來的大本營、時刻表決戰的起點、玉璽在領地爭奪的季。2026-10-27 測試整理 4 由 model、map、trend、garrison、perks、day、settle、seam、fb530_wall、on、out_of_contest、front_note、seal 十三個檔併成；各段開頭照抄原本那一檔的說明。"""
from __future__ import annotations
from conftest import real_content
from conquest_kit import conquest_rules, plain_game
from tianxia import conquest, sortie
from tianxia.models import BlockDef, ConquestRules
from tianxia.state import WorldState
from tianxia.world_state import stamp_season
import pytest
from conquest_kit import conquest_game
from tianxia.content import ContentError, validate
from tianxia.models import BlockDef
from conquest_kit import conquest_game, plain_game
from tianxia import conquest, rules, territory
from tianxia import conquest, territory
import random
from tianxia import conquest, explore_modes, sensing, territory
import calendar as pycal
from datetime import datetime
from tianxia import conquest, conquest_day
from conquest_kit import announce, conquest_game, join, plain_game
from tianxia import conquest, conquest_day, howto, orders
from tianxia.state import Order
from tianxia.world import keep_showdowns_on_time
from tianxia import conquest_day, howto, xingshi
from tianxia.state import DayNote
from tianxia import conquest, rules
import json
import tempfile
from pathlib import Path
from conquest_kit import _new, conquest_rules, go, join, plain_game
from test_seal_web import DRIVER
import server
import webharness
from conftest import real_content
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from conquest_kit import conquest_game, go, join, plain_game
from tianxia import bot_policy, mapview, orders, sortie
from tianxia.state import BotProfile, Order
import re
import unicodedata
from tianxia import battle_instance as bi
from tianxia import conquest, seal, territory
from tianxia import world as world_mod
from conquest_kit import _new, conquest_rules, go, join
from conftest import next_season, real_content
from jianfa_kit import no_jianfa
from tianxia import atlas, conquest, explore_modes, library, seal
from tianxia import world as world_rules
from tianxia.world_state import SealCache, SealRegistry


def test_old_season_json_reads_without_conquest_fields():
    w = WorldState.model_validate_json(WorldState().model_dump_json(exclude={"conquest_on", "conquest"}))
    assert w.conquest_on is False and w.conquest is None


@pytest.mark.parametrize(("profile", "on"), [("week7", True), ("season21", True), (None, False)])
def test_conquest_is_on_wherever_territory_is(profile, on):
    """沒有開關（2026-10-27 舊出陣拔河拿掉）：有第一季規則、劇本寫了區塊、豪強分屬兩軍就是領地爭奪，不看季上的章；14 天（不帶設定）沒有第一季規則。"""
    c = real_content(profile)
    assert conquest.on(c) is on and territory.on(c) is on and sortie.on(c) is on
    if not on:
        return
    c.config.haoqiang_allied = False  # 豪強是第三方：割據要佔地，跟領地爭奪對不上（設計 4.1）
    assert not conquest.on(c)
    c = real_content(profile)
    c.scenario.territory.blocks = {}
    assert not conquest.on(c)


# ── 原 test_conquest_map.py（整檔搬進來） ──
# 領地爭奪第一批 Task 2：區塊表、相連與目標（計畫三、Task 2；裁決 2：開季兩邊碰得到的中立地差不多，目標各 6～7 塊）。
#
# 區塊表 v3（輿圖簡化設計 3.2，計畫「區塊表 v3」那一節；企劃者 10/20「這些灰色沒人的地方有些根本只有連接在黃巾軍」）：每一塊中立地兩軍
# 各有一條路從自家開季持有的領地走得到（只走自家與中立的區塊），開季兩邊直通的中立地差在一塊以內。

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


@pytest.mark.smoke
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


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
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


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
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


# ── 原 test_conquest_trend.py（整檔搬進來） ──
# 領地爭奪第一批 Task 3：控制方照佔領、大勢值＝佔領的基準＋偏移（計畫三、Task 3；設計 4.7；裁決 5：分母只算中立、偏移從劇本起點開始）。

LINES = ("yingru", "nanyang", "jizhou")


def _value(game, line):
    return rules.world_trend_value(game.state.world, game.content, line)


def _owner(game, loc):
    return territory.controller(game.state.world, game.content, loc)


def test_opening_base_is_fifty_and_the_offset_keeps_the_scenario_start():
    plain = plain_game("season21")
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    assert {line: conquest.base(w, c, line) for line in LINES} == {line: 50.0 for line in LINES}
    assert {line: _value(game, line) for line in LINES} == {line: _value(plain, line) for line in LINES}  # 40／35／55 照舊
    assert w.conquest.offset["nanyang"] == _value(game, "nanyang") - 50


def test_opening_control_follows_the_block_kinds():
    game = conquest_game("season21")
    assert _owner(game, "changshe") == "guan" and _owner(game, "yingchuan") == "guan" and _owner(game, "zhuo_county") == "guan"
    assert _owner(game, "runan") == "huang" and _owner(game, "xinye") == "huang" and _owner(game, "guangzong") == "huang"
    assert _owner(game, "nanyang_wilds") is None and _owner(game, "yu_river") is None  # 中立地沒人佔（區塊表 v3）
    assert _owner(game, "haozu_fort") is None and _owner(game, "jade_cave") is None  # 不是區塊
    game.advance(3600)
    assert not [r for r in game.state.world.rumors if r.text.endswith("之手。")]  # 第一次算不發天下大事、之後不拔河


def test_capture_moves_the_base_and_keeps_the_offset():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    rules.change_trend(game.state, c, "nanyang", 4)  # 其他來源：偏移 +4
    pushed = _value(game, "nanyang")
    conquest.set_control(w, c, "nanyang_wilds", "huang")
    assert _owner(game, "nanyang_wilds") == "huang"
    assert conquest.base(w, c, "nanyang") == pytest.approx(50 + 35 / 4)  # 南陽開季中立 4 塊（區塊表 v3）
    assert _value(game, "nanyang") == round(pushed + 35 / 4)
    assert any("南陽郊野落入" in r.text for r in w.rumors)
    assert any("南陽郊野落入" in r.text for r in w.chronicle)


def test_pushes_still_move_the_line_after_a_capture():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    conquest.set_control(w, c, "nanyang_wilds", "huang")
    before = _value(game, "nanyang")
    msgs = rules.change_trend(game.state, c, "nanyang", -3)
    assert _value(game, "nanyang") == before - 3 and msgs  # 其他來源照舊推（設計 3.8）


def test_push_into_the_wall_is_lost_like_before():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    rules.change_trend(game.state, c, "nanyang", 100)
    assert _value(game, "nanyang") == 100
    assert rules.change_trend(game.state, c, "nanyang", 5) == []  # 推進牆：不動、不寫
    conquest.set_control(w, c, "nanyang_road", "guan")  # 官軍拿下一塊中立：基準往下，值＝新基準＋重錨後的偏移（50）
    assert _value(game, "nanyang") == round(50 - 35 / 4 + 50)


def test_a_direct_write_is_reanchored():
    """決戰收場、管理者這類直接寫 world.trends 的：下一次重算照上一次的基準重錨偏移，易手只動基準。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    w.trends["jizhou"] = _value(game, "jizhou") + 10
    territory.update(w, c)
    moved = _value(game, "jizhou")
    conquest.set_control(w, c, "xiaquyang", "huang")
    assert _value(game, "jizhou") == round(moved + 35 / 3)  # 冀州開季中立 3 塊（區塊表 v3）


def test_capturing_an_enemy_faction_block_weighs_double():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    before = _value(game, "yingru")
    conquest.set_control(w, c, "runan", "guan")  # 黃巾的陣營區塊（權重 2）被官軍拿下；潁川汝南開季中立 2 塊（區塊表 v3）
    assert conquest.base(w, c, "yingru") == pytest.approx(50 - 35 * 2 / 2)
    assert _value(game, "yingru") == round(before - 35 * 2 / 2)
    conquest.set_control(w, c, "runan", "huang")  # 拿回自己的：不算佔得，回到 50
    assert conquest.base(w, c, "yingru") == 50
    assert any("收復汝南。" in r.text for r in w.rumors)


def test_weigh_by_neutral_full_ring_reaches_the_share():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    for loc in ("nanyang_road", "nanyang_wilds", "yu_river", "lulin_zhai"):
        conquest.set_control(w, c, loc, "huang")
    assert conquest.base(w, c, "nanyang") == pytest.approx(85)
    c.config.conquest.weigh_by = "total"  # 設計 4.7 原文：分母是那條線所有可奪區塊的權重和（中立 4、陣營 1 塊〔新野〕×2）
    assert conquest.base(w, c, "nanyang") == pytest.approx(50 + 35 * 4 / 6)


def test_timetable_assign_sticks_and_reweighs():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    before = _value(game, "jizhou")
    territory.assign(w, c, {"guangzong": "guan"})
    assert _owner(game, "guangzong") == "guan"
    assert _value(game, "jizhou") == before  # 廣宗是 fixed：不算權重
    game.advance(3600)
    w = game.state.world  # 推進之後讀回來的那一份
    assert _owner(game, "guangzong") == "guan"  # 規則不會把它翻回去
    territory.assign(w, c, {"xiaquyang": "guan"})  # 時刻表指定一塊中立：指定了就是指定了
    assert _owner(game, "xiaquyang") == "guan" and conquest.base(w, c, "jizhou") == pytest.approx(50 - 35 / 3)


def test_admin_sets_a_block():
    game = conquest_game("season21", name="Rayal")
    msgs = game.admin_conquest_set("nanyang_wilds", "huang")
    assert _owner(game, "nanyang_wilds") == "huang" and msgs
    game.admin_conquest_set("nanyang_wilds", None)
    assert _owner(game, "nanyang_wilds") is None  # 放回中立
    before = _owner(game, "changshe")
    game.admin_conquest_set("changshe", "huang")  # 大本營不收
    assert _owner(game, "changshe") == before
    game.admin_conquest_set("zhuo_county", "haoqiang")  # 只收兩軍（區塊表 v3 之前用淯水河畔，現在是中立地）
    assert _owner(game, "zhuo_county") == "guan"


def test_admin_set_refused_for_players():
    game = conquest_game("season21")
    msgs = game.admin_conquest_set("nanyang_wilds", "huang")
    assert _owner(game, "nanyang_wilds") is None and "管理者" in "".join(msgs)


# ── 原 test_conquest_garrison.py（整檔搬進來） ──
# 領地爭奪第一批 Task 4：中立區塊另一套駐軍（計畫三、Task 4；設計 3.3：佔下之後駐軍對兩邊都照打。隊伍是佔位，待 joy）。

def _squads(game, loc):
    return territory.squads_at(game.state.world, game.content, loc)


def test_every_neutral_block_has_a_garrison_without_faction():
    c = real_content("season21")
    t = c.scenario.territory
    neutral = {loc for loc, b in t.blocks.items() if b.kind == "neutral"}
    assert set(t.neutral_garrison) == neutral
    for squads in t.neutral_garrison.values():
        assert squads and all(c.squads[s].faction is None for s in squads)
        assert all(55 <= c.squads[s].difficulty <= 90 for s in squads)  # 計畫 Task 4：高階獵場的強對手


def test_neutral_garrison_stays_after_capture():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    start = _squads(game, "nanyang_wilds")
    assert "nz_luanbing" in start and all(c.squads[s].faction is None for s in start)
    conquest.set_control(w, c, "nanyang_wilds", "huang")
    assert _squads(game, "nanyang_wilds") == start  # 駐軍不換成佔領方自己的兵（設計 3.3）
    river = set(_squads(game, "yu_river"))
    assert river >= {"he_shuikou", "nz_shuifei"} and "louluo" not in river  # 地點自己的野獸流寇照舊在，有陣營的兵不在


def test_faction_block_takes_holder_garrison():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    assert set(_squads(game, "guan_camp")) == {"beijun_wuzu", "liangzhou_cavalry"}
    conquest.set_control(w, c, "guan_camp", "huang")
    assert set(_squads(game, "guan_camp")) == {"louluo", "shuikou"}
    assert _squads(game, "zhuo_county") == []  # 沒寫 garrison 的照 Location.enemies


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
@pytest.mark.parametrize("change", [
    lambda t: t.neutral_garrison.__setitem__("guan_camp", ["nz_daoke"]),  # 只能寫在開季中立的區塊
    lambda t: t.neutral_garrison.__setitem__("hilltop_wilds", ["louluo"]),  # 要是沒有陣營的隊伍
    lambda t: t.neutral_garrison.__setitem__("hilltop_wilds", ["nobody"]),  # 隊伍要認得
])
def test_validate_rejects_bad_neutral_garrison(change):
    c = real_content("season21")
    change(c.scenario.territory)
    with pytest.raises(ContentError):
        validate(c)


# ── 原 test_conquest_perks.py（整檔搬進來） ──
# 領地爭奪第一批 Task 5：陣營領地加成、散人在中立地（計畫三、Task 5；設計 4.5、4.6；裁決 4：新手期在敵方領地療傷不吃 ×1.2）。

def _at(game, loc, faction):
    p = game.state.player
    p.location, p.journey, p.faction = loc, None, faction


def _land(game, loc, faction):
    return territory.price_factor(game.state.world, game.content, faction, loc)


def test_prices_follow_the_holder():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    assert _land(game, "yingchuan", "guan") == pytest.approx(0.9)
    conquest.set_control(w, c, "nanyang_wilds", "huang")
    assert _land(game, "nanyang_wilds", "guan") == pytest.approx(1.2)
    assert _land(game, "nanyang_wilds", "huang") == pytest.approx(0.9)
    assert _land(game, "nanyang_wilds", None) == pytest.approx(0.9)  # 散人：開季中立的區塊算自家（設計 4.6），不論此刻歸誰
    assert _land(game, "yu_river", None) == pytest.approx(0.9)
    assert _land(game, "yingchuan", None) == 1.0  # 散人在陣營領地：原價
    assert _land(game, "yu_river", "guan") == 1.0  # 中立地沒人佔：誰都不是自家


def test_home_follows_where_you_stand():
    game = conquest_game("season21")
    s, c = game.state, game.content
    _at(game, "yingchuan", "guan")
    assert conquest.home(s, c)
    _at(game, "runan", "guan")
    assert not conquest.home(s, c)
    _at(game, "nanyang_wilds", None)
    assert conquest.home(s, c)  # 散人在開季中立的區塊
    _at(game, "haozu_fort", None)
    assert not conquest.home(s, c)  # 不是區塊


def test_newbie_heals_at_home_price_in_enemy_land():
    game = conquest_game("season21")
    s, c = game.state, game.content
    _at(game, "yingchuan", "huang")  # 潁川郡：黃巾新手出序章的第一站，官軍的領地（裁決 4）
    s.player.joined_at = s.world.time
    assert territory.price_here(s, c, heal=True) == pytest.approx(territory.price_here(s, c) / 1.2)
    s.player.joined_at = s.world.time - 100 * 3600  # 過了新手期
    assert territory.price_here(s, c, heal=True) == pytest.approx(territory.price_here(s, c))


def _found_count(game, loc_id):
    s = game.state
    before = sum(s.player.materials.values())
    game._gather(game.content.locations[loc_id], random.Random(7))
    return sum(s.player.materials.values()) - before


def _lucky_seq(game, hit):
    """找一個這一下「領地」那顆骰擲中（hit）或沒中的探索流水號（_explore_mode 擲之前先加一，所以回的是擲那一下的流水號）。"""
    p = game.state.player
    season = game.world.get_season_number()
    chance = game.content.config.conquest.gather_bonus_chance
    for seq in range(1, 200):
        if (explore_modes.rng_for(season, p.name, seq, "領地").random() < chance) == hit:
            return seq
    raise AssertionError("找不到")


def test_gather_bonus_only_at_home():
    game = conquest_game("season21")
    s, c = game.state, game.content
    _at(game, "nanyang_wilds", "guan")
    s.player.explore_seq = _lucky_seq(game, True)
    conquest.set_control(s.world, c, "nanyang_wilds", "guan")
    home = _found_count(game, "nanyang_wilds")
    conquest.set_control(s.world, c, "nanyang_wilds", "huang")
    away = _found_count(game, "nanyang_wilds")
    assert home == away + 1
    s.player.explore_seq = _lucky_seq(game, False)
    conquest.set_control(s.world, c, "nanyang_wilds", "guan")
    assert _found_count(game, "nanyang_wilds") == away  # 沒擲中：不多給


def test_sense_rate_plus_five_at_home():
    game = conquest_game("season21")
    s, c = game.state, game.content
    loc = c.locations["yu_river"]  # 開季中立（區塊表 v3 之前用嵩山深處，現在是官軍的）
    s.player.stats["wis"] = 1  # 壓低成算，免得撞到上限
    _at(game, "yu_river", "guan")
    away = sensing.rate(s, c, loc)
    conquest.set_control(s.world, c, "yu_river", "guan")
    assert sensing.rate(s, c, loc) == away + c.config.conquest.sense_bonus_points


# ── 原 test_conquest_day.py（整檔搬進來） ──
# 領地爭奪：每天的鐘與攻城時段（tianxia/conquest_day.py；設計 4.3，裁決 6）。投票、主將定奪、合成時程表照翻地與爭搶拿掉了（PM 2026-10-20），
# 那幾條測試跟著拿掉；戰書挑時段（next_slot）在這裡，戰書本身在 test_conquest_siege.py。

def _utc(y, mo, d, h, mi=0, s=0) -> float:
    return float(pycal.timegm(datetime(y, mo, d, h, mi, s).timetuple()))


def test_day_key_turns_at_22_taiwan():
    cfg = conquest_game("season21").content.config
    before, after = _utc(2026, 10, 20, 13, 59, 59), _utc(2026, 10, 20, 14, 0, 0)  # 台灣 21:59:59、22:00:00
    assert conquest_day.day_key(after, cfg) == conquest_day.day_key(before, cfg) + 1
    key = conquest_day.day_key(after, cfg)
    assert conquest_day.key_start(key, cfg) == after
    # 那一天的 12:00 是隔天中午（台灣 10/21 12:00＝UTC 04:00），21:00 也在同一天
    assert conquest_day.slot_real(key, 12 * 60, cfg) == _utc(2026, 10, 21, 4)
    assert conquest_day.slot_real(key, 21 * 60, cfg) == _utc(2026, 10, 21, 13)
    assert conquest_day.slot_text(20 * 60 + 30) == "20:30"


def test_next_slot_is_the_nearest_one_or_tomorrows_first():
    """戰書挑的時段（翻地與爭搶，輿圖簡化設計 4.4「時段挑最近的一個」）：今天還開得了集結的第一個，今天沒有了就下一天的第一個。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    morning = _utc(2026, 10, 20, 2)  # 台灣 10/20 10:00
    key = conquest_day.day_key(morning, c.config)
    assert conquest_day.next_slot(w, c, morning) == (key, 12 * 60)
    assert conquest_day.next_slot(w, c, _utc(2026, 10, 20, 11)) == (key, 19 * 60 + 30)  # 台灣 19:00：19:30 才來得及集結
    assert conquest_day.next_slot(w, c, _utc(2026, 10, 20, 12, 40)) == (key + 1, 12 * 60)  # 台灣 20:40：今天沒有了
    assert conquest_day.next_slot(w, c, _utc(2026, 10, 20, 15)) == (key + 1, 12 * 60)  # 台灣 23:00：已經換天，明天中午


def test_slots_skip_showdown_window():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    real_now = _utc(2026, 10, 20, 2)  # 台灣 10/20 10:00
    key = conquest_day.day_key(real_now, c.config) + 1  # 明天的時段：10/21 12:00～21:00
    event = next(e for e in c.timetable if e.kind == "showdown")
    w.schedule[event.id] = w.time + (conquest_day.slot_real(key, 20 * 60, c.config) - real_now)  # 決戰排在那一天 20:00
    got = conquest_day.slots(w, c, key, real_now)
    assert 19 * 60 in got and 21 * 60 in got
    assert not {19 * 60 + 30, 20 * 60, 20 * 60 + 30} & set(got)  # 19:30～20:45 拿掉（裁決 6）
    today = conquest_day.day_key(real_now, c.config)  # 今天（10/20 的 12:00～21:00）：10:00 看，12:00 之前的都還開得了集結
    assert conquest_day.slots(w, c, today, _utc(2026, 10, 20, 12))[0] == 20 * 60 + 30  # 台灣 20:00 看：20:30 以前的都來不及


# ── 原 test_conquest_settle.py（整檔搬進來） ──
# 領地爭奪：每天 22:00 換天的掛鉤（Game._conquest_tick → conquest_day.day_turn）。翻地與爭搶（輿圖簡化設計 4.4，PM 2026-10-20 第 1、2 條）之後
# 投票與 22:00 的公告結算拿掉了：換天只作罷前幾天沒開成的攻城、清掉打完的，不再自己排攻城；這個掛鉤留著給〈天下形勢〉每天一篇。
# 日子只准往前走（Review Focus 2）；暫停繼續時還沒開的攻城照原本的現實時間挪；軍令照「此刻進度最高的那一塊」列與記；救場。

def _tw(y, mo, d, h, mi=0) -> float:
    """台灣時間 → 現實 epoch 秒。"""
    return float(pycal.timegm(datetime(y, mo, d, h, mi).timetuple())) - 8 * 3600


def _game(now: float, name: str = "沈浪", world=None):
    game = join(conquest_game("season21", name=name, world=world), "huang")
    game.now = now
    return game


def _tick(game, now: float):
    game.now = now
    game._conquest_tick()
    game.state.world = game.world.get_season()
    return game.state.world.conquest


def test_first_sync_only_records_the_key():
    game = _game(_tw(2026, 10, 20, 10))
    state = _tick(game, game.now)
    assert state.settled_key == conquest_day.day_key(game.now, game.content.config)
    assert state.schedule == []
    assert not [r for r in game.state.world.rumors if "攻" in r.text and r.layer == "world"]


def test_the_day_turns_once_and_never_schedules_sieges_by_itself():
    game = _game(_tw(2026, 10, 20, 10))
    _tick(game, game.now)
    state = _tick(game, _tw(2026, 10, 20, 22, 1))  # 換天
    assert state.settled_key == conquest_day.day_key(game.now, game.content.config)
    assert state.schedule == [] and state.day_log == []  # 沒有主將定奪、沒有投票：沒人下戰書就照推
    assert not [r for r in game.state.world.rumors if r.layer == "world" and "攻" in r.text]
    again = _tick(game, _tw(2026, 10, 20, 23))
    assert again.settled_key == state.settled_key


def test_settle_only_moves_forward():
    a = _game(_tw(2026, 10, 20, 10), name="甲某")
    _tick(a, a.now)
    b = _game(_tw(2026, 10, 20, 10), name="乙某", world=a.world)
    b.advanced_real = 86400.0  # b 快轉過一天：它認為已經是明天
    _tick(b, _tw(2026, 10, 20, 22, 1))  # b 的「今天」是 10/21 22:01
    ahead = a.world.get_season().conquest
    a.state.world = a.world.get_season()
    slot = announce(a, "hilltop_wilds", "huang")
    slot.key = ahead.settled_key
    a._save_season()
    behind = _tick(a, _tw(2026, 10, 20, 22, 1))  # a 天數小：不倒退、不作罷今天的
    assert behind.settled_key == ahead.settled_key
    assert [s.status for s in behind.schedule] == ["planned"]


def test_sync_and_world_tick_turn_the_day():
    game = _game(_tw(2026, 10, 20, 10))
    game.sync(game.now)
    game.sync(game.now + 60)  # 季推進一下（第一次推進才算地盤、領地爭奪）
    assert game.state.world.conquest.settled_key == conquest_day.day_key(game.now, game.content.config)
    from tianxia.engine import Game

    ticker = Game.for_world(game.content, game.world)
    ticker.world_tick(_tw(2026, 10, 20, 22, 1))
    assert game.world.get_season().conquest.settled_key == conquest_day.day_key(_tw(2026, 10, 20, 22, 1), game.content.config)


def test_admin_letter_opens_soon_and_cancel_voids_it():
    game = _game(_tw(2026, 10, 20, 23), name="Rayal")
    _tick(game, game.now)
    msgs = game.admin_conquest_letter("hilltop_wilds", "huang")
    state = game.world.get_season().conquest
    assert len(state.schedule) == 1 and msgs and "攻荒丘" in msgs[0]
    w = game.world.get_season()
    assert state.schedule[0].muster_at - w.time <= 60  # 集結馬上開
    game.admin_conquest_cancel(state.schedule[0].id)
    assert game.world.get_season().conquest.schedule[0].status == "void"


def test_resume_shifts_planned_slots():
    game = _game(_tw(2026, 10, 20, 10))
    _tick(game, game.now)
    announce(game, "hilltop_wilds", "huang")
    season = game.state.world
    before = [(s.at, s.muster_at) for s in season.conquest.schedule]
    keep_showdowns_on_time(season, game.content, 600.0, season.time)
    assert [(s.at, s.muster_at) for s in season.conquest.schedule] == [(a - 600, m - 600) for a, m in before]


def test_siege_and_defend_orders_follow_the_highest_block():
    game = _game(_tw(2026, 10, 20, 10))
    w, c = game.state.world, game.content
    assert orders.siege_places(c, "huang", "yingru", w) == ["runan_wilds"]  # 潁川汝南黃巾推得動的只有汝南荒野（區塊表 v3；全是 0：每一塊都算）
    held = [loc for loc in conquest.blocks(c) if conquest.capturable(c, loc) and conquest.holder(w, c, loc) == "guan"
            and conquest.line_of(w, c, loc) == "yingru"]
    week = orders.period_of(game.state, c)
    w.orders.append(Order(id="d1", template="defend", faction="guan", week=week, front="yingru", quota=5, text="守"))
    assert not any(orders.duty_counts(game.state, c, "guan", loc) for loc in held)  # 沒人在推官軍的地方：沒有可守的
    conquest.push(w, c, held[0], "huang", "某", 20, "attack")
    conquest.push(w, c, held[1], "huang", "某", 30, "attack")
    assert orders.duty_counts(game.state, c, "guan", held[1])  # 被推得最高的那一塊
    assert not orders.duty_counts(game.state, c, "guan", held[0])


def test_howto_has_the_flip_rules():
    game = conquest_game("season21")
    lines = " ".join(howto.territory_lines(game.content, True, game.state.world))
    assert "推滿" in lines and "戰書" in lines and "投票" not in lines


# ── 原 test_conquest_seam.py（整檔搬進來） ──
# 輿圖第三版第 5 批（領地爭奪接縫；計畫 docs/superpowers/plans/2026-10-22-輿圖v3-接縫.md 第一節）：翻地第 1 批已經在引擎拿掉投票與
# 22:00 公告結算、攻城改戰書觸發；這一批把還留著「給舊季認得」的眾議、主將定奪收掉——領地爭奪從沒合進 develop／main，沒有哪一季的存檔有
# 投票那一版的 day_log。舊資料（帶眾議比例、by 是 vote 的那一筆）照樣讀得進來，〈天下形勢〉認不得的那一筆略過、不炸。
# 玩法說明（領地爭奪的季）不再寫輿圖第三版已經拿掉的「局勢層」。

def test_the_vote_era_words_are_gone():
    for name in ("VOTE", "COMMANDER", "REASON_PLAIN"):
        assert not hasattr(conquest_day, name), name
    assert conquest_day.BY_WORDS == {conquest_day.LETTER: "戰書"}


def test_xingshi_has_no_vote_era_sentences():
    game = conquest_game("season21", xingshi=True)
    fact = xingshi.lines(game.content)["fact"]
    for key in ("plan_vote", "plan_commander"):
        assert key not in xingshi.FACT_KEYS and key not in fact, key
    assert "reason" not in xingshi.SAMPLE
    assert "主將" not in xingshi.SYSTEM and "戰書" in xingshi.SYSTEM  # 下一仗是誰下了戰書，不是主將挑的


def test_old_day_notes_still_load_and_are_skipped():
    """day_log 的舊資料（眾議那一版）：多的鍵（share）略過、讀得進來；by 是 vote 的那一筆〈天下形勢〉認不得，略過不寫、不炸。"""
    assert "share" not in DayNote.model_fields
    old = DayNote.model_validate({"key": 1, "side": "huang", "loc": "nanyang_road", "minute": 21 * 60, "by": "vote", "share": 0.6})
    game = conquest_game("season21", xingshi=True)
    w, c = game.state.world, game.content
    assert xingshi.note_fact(c, old) is None
    facts = xingshi.facts(w, c, [old], {})
    assert facts and not any("南陽官道" in f for f in facts)


def test_the_kit_places_a_letter_not_a_commanders_pick():
    """測試的小工具 conquest_kit.announce 排的那一場同戰書排的（以前寫 by="commander"，主將定奪）；畫面資料的 by 寫「戰書」。"""
    game = join(conquest_game("season21"), "guan")
    slot = announce(game, "nanyang_road", "huang")
    assert slot.by == {"huang": conquest_day.LETTER}
    row = next(r for r in game.conquest_view()["today"] if r["id"] == slot.id)
    assert set(row["by"].values()) == {"戰書"}


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
def test_the_conquest_howto_speaks_of_the_new_map():
    """玩法說明「地盤」那一節：輿圖第三版沒有局勢層了，寫天下圖的地面與區圖的名字框。領地爭奪的季第 5 批先改；關著的季原本一個字不動，
    PM 2026-10-22 定也改（設計 5.6：關著的季也用新畫法；關著的季對照只差這一句與意境那一句）。"""
    game = conquest_game("season21")
    on = "".join(howto.territory_lines(game.content, season=game.state.world))
    assert "局勢層" not in on and "天下圖" in on and "區圖" in on
    for profile in ("week7", None, "season21"):
        plain = plain_game(profile)
        off = "".join(howto.territory_lines(plain.content, season=plain.state.world))
        assert "局勢層" not in off and "天下圖的地面、區圖名字框的顏色就是此刻誰佔著" in off, profile


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
def test_the_strongest_insight_howto_points_at_the_region_map():
    """玩法說明「靜心感悟」那一句（STRONG_HOWTO）：輿圖第三版拿掉了意境濾鏡（第 4 批），改寫區圖名字底下的意境字與卡上的「最濃」
    （PM 2026-10-22，每一種季都改）。"""
    assert "濾鏡" not in howto.STRONG_HOWTO and "區圖" in howto.STRONG_HOWTO and "最濃" in howto.STRONG_HOWTO
    for profile in ("week7", None, "season21"):
        game = plain_game(profile)
        text = game.howto_text()
        assert "濾鏡" not in text and "局勢層" not in text and howto.STRONG_HOWTO in text, profile


# ── 原 test_conquest_fb530_wall.py（整檔搬進來） ──
# FB-530：基準超過 100（裁決 5 分母只算中立之後才有）時，推一條線不該把偏移往回扣（計畫 6.2）。
#
# 偏移是「其他來源累積的量」，夾值只在顯示那一刻做；推過牆的那一截丟掉（往牆那一邊推、未夾的值已經在牆外時整個丟掉）。

LINE = "jizhou"  # 區塊表 v3 之後南陽沒有官軍搶得下來的陣營區塊（淯水河畔改成中立），換成同樣形狀的冀州


def _past_the_wall(game):
    """QA 的南陽（三塊中立加淯水河畔〔官軍的陣營區塊，權重 2〕都歸黃巾）照搬到冀州：三塊中立加涿郡（官軍的陣營區塊）都歸黃巾，
    基準 50＋35×5÷3＝108.33、偏移 −7、值 100。"""
    w, c = game.state.world, game.content
    rules.change_trend(game.state, c, LINE, 43 - _value(game, LINE))  # QA 那一季的南陽：開季那一刻張曼成取宛 +8，35 → 43
    for loc in ("baima_ford", "xiaquyang", "juma_river", "zhuo_county"):
        conquest.set_control(w, c, loc, "huang")
    assert conquest.base(w, c, LINE) == pytest.approx(50 + 35 * 5 / 3)
    assert w.conquest.offset[LINE] == pytest.approx(-7)
    assert _value(game, LINE) == 100
    return w, c


@pytest.mark.parametrize("delta", [1, 5])
def test_pushing_toward_the_wall_past_it_leaves_the_offset_alone(delta):
    game = conquest_game("season21")
    w, c = _past_the_wall(game)
    assert rules.change_trend(game.state, c, LINE, delta) == []  # 值不動、不寫
    assert w.conquest.offset[LINE] == pytest.approx(-7)
    conquest.set_control(w, c, "zhuo_county", "guan")  # 官軍收復涿郡：基準 85
    assert _value(game, LINE) == 78  # 85＋(−7)，跟沒推一樣（修前 77）


def test_pushing_back_from_past_the_wall_counts_once():
    game = conquest_game("season21")
    w, c = _past_the_wall(game)
    rules.change_trend(game.state, c, LINE, -1)
    assert w.conquest.offset[LINE] == pytest.approx(-8)  # 照推的量記（修前 −9.33）
    assert _value(game, LINE) == 100  # 未夾的 100.33，顯示照舊夾在 100
    conquest.set_control(w, c, "zhuo_county", "guan")
    assert _value(game, LINE) == 77  # 85＋(−8)（修前 76）


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
def test_pushing_back_far_enough_moves_the_value_and_stops_at_the_other_wall():
    game = conquest_game("season21")
    w, c = _past_the_wall(game)
    msgs = rules.change_trend(game.state, c, LINE, -11)
    assert _value(game, LINE) == 90 and msgs  # 101.33−11＝90.33
    rules.change_trend(game.state, c, LINE, -500)
    assert _value(game, LINE) == 0
    assert w.conquest.offset[LINE] == pytest.approx(-(50 + 35 * 5 / 3))  # 推過 0 那一截丟掉：未夾的剛好 0


def test_a_push_with_a_fractional_base_moves_the_offset_by_the_push():
    """基準有小數（南陽官道歸黃巾：58.75，區塊表 v3 南陽中立 4 塊；QA 那時 3 塊是 61.67）時，推 1 偏移就走 1（修前照四捨五入過的值
    重錨，偏移會多走一截，61.67 時多走 1.33）。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    conquest.set_control(w, c, "nanyang_road", "huang")
    before = _value(game, "nanyang")
    offset = w.conquest.offset["nanyang"]
    rules.change_trend(game.state, c, "nanyang", 1)
    assert _value(game, "nanyang") == before + 1
    assert w.conquest.offset["nanyang"] == pytest.approx(offset + 1)


# ── 原 test_conquest_on.py（整檔搬進來） ──
# 打開領地爭奪（企劃者 2026-10-22「領地爭奪……要打開」；計畫 docs/superpowers/plans/2026-10-22-打開領地爭奪.md）：正式內容的開關打開之後，
# 哪幾種季新開時蓋得上章、正在跑的季不變、要開新季才有；設定頁管理者工具的「領地爭奪」救場一組（Game.admin_conquest_choices 與網頁）。

NOW = 1_793_088_000.0  # 2026-10-27（週二）16:00 台灣


ADMIN = "管事"


def _world():
    return open_world(Path(tempfile.mkdtemp(prefix="conqon-")) / "t.db")


# ── 設定頁「領地爭奪」救場一組 ──


def _admin_game(profile: str = "week7"):
    c = conquest_rules(real_content(profile))
    c.config.admins = [ADMIN]
    return _new(c, ADMIN)


def test_admin_choices_list_capturable_blocks_two_sides_and_open_sieges():
    """下拉選單：搶得下來的區塊（大本營、廣宗不列；字寫此刻歸誰、進度、冷卻、戰書凍結）、交戰兩軍、還沒打完的攻城。"""
    game = _admin_game()
    c, w = game.content, game.state.world
    q = game.admin_conquest_choices()
    ids = [b["id"] for b in q["blocks"]]
    assert ids and all(conquest.capturable(c, loc) for loc in ids)
    assert set(ids) == {loc for loc in conquest.blocks(c) if conquest.capturable(c, loc)}
    assert "changshe" not in ids and "guangzong" not in ids  # 官軍的大本營、廣宗搶不下來
    assert [s["id"] for s in q["sides"]] == ["guan", "huang"] and q["sieges"] == []
    label = next(b["label"] for b in q["blocks"] if b["id"] == "hilltop_wilds")
    assert label == "荒丘（沒人佔）"
    assert {b["id"]: b["name"] for b in q["blocks"]}["yingchuan"] == "潁川郡（陽翟）"  # 問句寫的地名另給（label 不能拿來切）
    game.admin_conquest_progress("hilltop_wilds", "guan", 46)
    assert next(b["label"] for b in game.admin_conquest_choices()["blocks"] if b["id"] == "hilltop_wilds") == "荒丘（沒人佔・官軍 46）"
    game.admin_conquest_progress("hilltop_wilds", "guan", 100)  # 推滿易手：冷卻
    label = next(b["label"] for b in game.admin_conquest_choices()["blocks"] if b["id"] == "hilltop_wilds")
    assert label.startswith("荒丘（官軍・冷卻 ") and label.endswith(" 分）")
    game.admin_conquest_letter("runan_wilds", "guan")
    q = game.admin_conquest_choices()
    [siege] = q["sieges"]
    assert siege["id"] == w.conquest.schedule[-1].id and siege["label"].startswith("汝南荒野：官軍攻・")
    assert "戰書凍結" in next(b["label"] for b in q["blocks"] if b["id"] == "runan_wilds")
    game.admin_conquest_cancel(siege["id"])
    assert game.admin_conquest_choices()["sieges"] == []


def test_server_admin_choices_carry_the_conquest_group(monkeypatch):
    game = _admin_game()
    monkeypatch.setattr(server, "CONTENT", game.content)
    assert server.admin_choices(game)["conquest"] == game.admin_conquest_choices()


def test_the_four_routes_are_admin_actions_named_after_the_engine():
    """網頁的四顆鈕送的路由都在 ADMIN_ACTIONS，跟 Game.admin_* 同名或照舊名（FB-609：不跟玩家的下戰書撞名）。"""
    for op in ("conquest_set", "conquest_progress", "admin_conquest_letter", "conquest_cancel"):
        assert op in server.ADMIN_ACTIONS, op
    assert "conquest_letter" not in server.ADMIN_ACTIONS


def test_a_non_admin_gets_refused_and_the_map_stays():
    """開著領地爭奪、但不是管理者：四條路由都回拒絕話、地圖不動（路由本身不另擋，引擎的 _admin_refusal 擋）。"""
    game = join(go(_new(conquest_rules(real_content("week7")), "路人"), "hilltop_wilds"), "guan")
    before = conquest.holder(game.state.world, game.content, "hilltop_wilds")
    assert game.admin_conquest_set("hilltop_wilds", "guan") == ["（只有管理者能定一塊歸誰。）"]
    assert game.admin_conquest_progress("hilltop_wilds", "guan", 100) == ["（只有管理者能定一塊的進度。）"]
    assert game.admin_conquest_letter("hilltop_wilds", "guan") == ["（只有管理者能立刻下戰書。）"]
    assert conquest.holder(game.state.world, game.content, "hilltop_wilds") == before
    assert conquest.frozen(game.state.world, "hilltop_wilds") is None


# ── 網頁：設定頁畫那一組、四顆鈕先問一次再送 ──


def _admin_view(q):
    return {"battles": [], "events": [], "trends": [], "season_one": False, "showdowns": [], "timetable": [], "results": [],
            "locks": [], "seal": None, "conquest": q}


def _q():
    return {
        "blocks": [{"id": "hilltop_wilds", "name": "荒丘", "label": "荒丘（沒人佔・官軍 46）"},
                   {"id": "yingchuan", "name": "潁川郡（陽翟）", "label": "潁川郡（陽翟）（官軍）"}],
        "sides": [{"id": "guan", "label": "官軍"}, {"id": "huang", "label": "黃巾軍"}],
        "sieges": [{"id": "s-1", "label": "汝南荒野：官軍攻・集結・交戰中・第 1 天 16:30"}],
    }


@pytest.fixture
def m():
    game = _admin_game()
    return server.main_view(game)


def _sheet(m, admin):
    return webharness.run(DRIVER, {"m": {**m, "admin": True}, "script": "return H.sheetHtml();", "S": {"admin": admin},
                                   "menxia": None, "stored": {}, "responses": {}})


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_admin_sheet_draws_the_conquest_group_only_when_on(m):
    sheet = _sheet(m, _admin_view(_q()))
    assert "領地爭奪（救場" in sheet and "荒丘（沒人佔・官軍 46）" in sheet and "汝南荒野：官軍攻" in sheet
    assert "潁川郡（陽翟）（官軍）" in sheet
    for op in ("conquest_set", "conquest_progress", "admin_conquest_letter", "conquest_cancel"):
        assert f'data-op="{op}"' in sheet, op
    assert 'data-op="conquest_set" data-neutral="1"' in sheet
    no_siege = _sheet(m, _admin_view({**_q(), "sieges": []}))
    assert 'data-op="conquest_cancel"' not in no_siege and 'data-op="conquest_set"' in no_siege
    off = _sheet(m, _admin_view(None))
    assert "領地爭奪（救場" not in off and "conquest_" not in off


# 假瀏覽器的 getElementById 只認 app、page 那幾個：換成也認這一組的四個欄位（下拉選單照 selectedIndex 讀字）
FIELDS = """
  const sel = (opts, i) => ({ value: opts[i][0], selectedIndex: i, options: opts.map(([value, text]) => ({ value, text })) });
  const fields = {
    "ad-cq-block": sel([["hilltop_wilds", "荒丘（沒人佔・官軍 46）"], ["yingchuan", "潁川郡（陽翟）（官軍）"]], input.block),
    "ad-cq-side": sel([["guan", "官軍"], ["huang", "黃巾軍"]], input.side),
    "ad-cq-value": { value: input.value },
    "ad-cq-siege": sel([["s-1", "汝南荒野：官軍攻・集結・交戰中・第 1 天 16:30"]], 0),
  };
  const real = T.ctx.document.getElementById;
  T.ctx.document.getElementById = (id) => fields[id] || real(id);
"""


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_conquest_buttons_ask_then_post_their_bodies(m):
    from test_admin_triggers_web import CLICK

    clicks = [{"act": "admin", "op": "conquest_set"}, {"act": "admin", "op": "conquest_set", "neutral": "1"},
              {"act": "admin", "op": "conquest_progress"}, {"act": "admin", "op": "admin_conquest_letter"},
              {"act": "admin", "op": "conquest_cancel"}]
    script = CLICK.replace("return (async () => {", "return (async () => {" + FIELDS, 1).replace("input.clicks", json.dumps(clicks))
    out = webharness.run(DRIVER, {"m": {**m, "admin": True}, "script": script, "S": {"admin": _admin_view(_q()), "sheet": True},
                                  "menxia": None, "stored": {}, "responses": {"/api/do/": {"main": m, "message": "好了"}},
                                  "block": 1, "side": 1, "value": "130"})
    asked = out["asked"]
    # 地名照伺服器給的 name（潁川郡（陽翟）自己有括號，不從選單的字切）
    assert "把「潁川郡（陽翟）」定給黃巾軍" in asked[0] and "不分紅、不起冷卻" in asked[0]
    assert "把「潁川郡（陽翟）」放回中立" in asked[1]
    assert "黃巾軍那一條進度定成 100" in asked[2] and "推滿當場易手" in asked[2]  # 欄位寫 130：夾在 100
    assert "替黃巾軍立刻對「潁川郡（陽翟）」下一張戰書" in asked[3]
    assert "取消「汝南荒野：官軍攻・集結・交戰中・第 1 天 16:30」這一場攻城" in asked[4]
    posts = [(c[0], c[1]) for c in out["calls"] if c[0].startswith("/api/do/")]
    assert [p[0] for p in posts] == ["/api/do/conquest_set", "/api/do/conquest_set", "/api/do/conquest_progress",
                                     "/api/do/admin_conquest_letter", "/api/do/conquest_cancel"]
    bodies = [p[1] for p in posts]
    assert (bodies[0]["id"], bodies[0]["side"]) == ("yingchuan", "huang")
    assert (bodies[1]["id"], bodies[1]["side"]) == ("yingchuan", "")
    assert (bodies[2]["id"], bodies[2]["side"], bodies[2]["value"]) == ("yingchuan", "huang", 100)
    assert (bodies[3]["id"], bodies[3]["side"]) == ("yingchuan", "huang")
    assert bodies[4]["id"] == "s-1"


def test_get_sieges_reads_the_same_as_the_whole_state():
    """SqliteWorldStore.get_sieges 只讀流水號與那幾列戰鬥（不整份解析共用狀態與季；計畫 4.4 量到整份讀佔假人一個動作的兩成多）：
    跟 read().sieges 一模一樣——沒有攻城、兩場同時集結、其中一場有人加入之後都一樣。"""
    from conquest_kit import announce, conquest_game
    from tianxia import siege

    game = join(go(conquest_game("season21"), "hilltop_wilds"), "guan")
    same = lambda: [b.model_dump() for b in game.world.get_sieges()] == [b.model_dump() for b in game.world.read().sieges]  # noqa: E731
    assert game.world.get_sieges() == [] and same()
    game.now = NOW
    w = game.state.world
    for slot in (announce(game, "hilltop_wilds", "guan", minute=20 * 60), announce(game, "runan_wilds", "huang", minute=20 * 60)):
        slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    assert [b.siege.loc for b in game.world.get_sieges()] == ["hilltop_wilds", "runan_wilds"] and same()
    join_id = next(o.id for o in game.options() if o.id.startswith("battle:join:guan"))
    game.choose(join_id)
    assert game.state.player.name in game.world.get_sieges()[0].participants and same()


def test_the_routes_do_what_the_questions_say():
    """問句說的事跟引擎做的對得上：定歸誰發天下大事、不起冷卻；放回中立不發；定進度到 100 易手、起冷卻；下戰書凍結；取消解凍。"""
    game = _admin_game()
    c, w = game.content, game.state.world
    before = len(w.rumors)
    server.ADMIN_ACTIONS["conquest_set"](game, {"id": "hilltop_wilds", "side": "guan"})
    w = game.state.world
    assert conquest.holder(w, c, "hilltop_wilds") == "guan" and not conquest.cooling(w, c, "hilltop_wilds")
    assert len(w.rumors) == before + 1
    server.ADMIN_ACTIONS["conquest_set"](game, {"id": "hilltop_wilds", "side": ""})
    w = game.state.world
    assert conquest.holder(w, c, "hilltop_wilds") is None and len(w.rumors) == before + 1
    server.ADMIN_ACTIONS["conquest_progress"](game, {"id": "hilltop_wilds", "side": "huang", "value": 100})
    w = game.state.world
    assert conquest.holder(w, c, "hilltop_wilds") == "huang" and conquest.cooling(w, c, "hilltop_wilds")
    server.ADMIN_ACTIONS["admin_conquest_letter"](game, {"id": "runan_wilds", "side": "guan"})
    w = game.state.world
    slot = conquest.frozen(w, "runan_wilds")
    assert slot is not None
    server.ADMIN_ACTIONS["conquest_cancel"](game, {"id": slot.id})
    assert conquest.frozen(game.state.world, "runan_wilds") is None


# ── 原 test_conquest_out_of_contest.py（整檔搬進來） ──
# 計畫第八章裁決 18（PM 2026-10-20）：領地爭奪開著時，敵方的大本營與廣宗搶不下來、不推進度，所以不給攻、不畫 ⚔——
# 出陣那一格灰著寫「此地不在爭奪之列」（待 joy 潤），假人不往那裡出陣，軍令不把它列成攻城地點。截糧的運糧隊打那裡經過時照打
# （截糧不動，裁決 11），只打運糧隊。

ENEMY_SPOTS = (("guan", "huangjin_camp"), ("guan", "guangzong"), ("guan", "julu_altar"), ("huang", "changshe"), ("huang", "wan_city"))


def _train(game):
    return next((o for o in game.options() if o.id == "act:train"), None)


def _note(game, loc_id):
    return game._sortie_line(game.content.locations[loc_id])


@pytest.mark.parametrize(("side", "loc"), ENEMY_SPOTS)
def test_enemy_base_and_guangzong_give_no_attack(side, loc):
    game = go(join(conquest_game("season21"), side), loc)
    option = _train(game)
    assert option is not None and not option.enabled  # 修前「出陣・攻」按得下去
    assert option.label == f"{sortie.NAME}（{sortie.OUT_NOTE}）"
    assert game.sortie_mode() is None
    assert _note(game, loc) == sortie.OUT_LINE


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
@pytest.mark.parametrize(("side", "loc"), ENEMY_SPOTS)
def test_no_crossed_swords_and_no_map_sortie_there(side, loc):
    game = go(join(conquest_game("season21"), side), loc)
    assert loc not in mapview.armed_places(game.state, game.content)
    state = game.map_state()
    assert state["places"][loc]["sortie"] is None and state["places"][loc]["armed"] is False
    assert loc not in {g["id"] for g in state["suggest"]}


def test_crossed_swords_stay_on_blocks_you_can_take():
    game = join(conquest_game("season21"), "guan")
    armed = mapview.armed_places(game.state, game.content)
    assert {"yu_river", "hilltop_wilds", "runan", "xinye"} <= armed  # 中立地、黃巾的陣營區塊（區塊表 v3）
    assert not armed & {"huangjin_camp", "nanyang_huangjin_camp", "julu_altar", "guangzong", "changshe"}


def test_bots_do_not_sortie_there():
    game = go(join(conquest_game("season21"), "guan"), "huangjin_camp")
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    assert bot_policy._train_value(game, profile, "huangjin_camp") == 0
    assert not any(o.id == "act:train" and o.enabled for o in game.options())


def test_siege_places_never_list_them():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    for side, front in (("guan", "yingru"), ("guan", "jizhou"), ("guan", "nanyang"), ("huang", "yingru"), ("huang", "nanyang")):
        assert not set(orders.siege_places(c, side, front, w)) & {"huangjin_camp", "guangzong", "julu_altar", "changshe", "wan_city",
                                                                 "nanyang_huangjin_camp", "luzhi_camp"}


def test_intercept_convoy_at_an_enemy_base_is_still_fought():
    """黃巾的截糧在長社（官軍的大本營）：運糧隊打那裡經過的那一週照打，只打運糧隊、只算截糧，不推進度。"""
    game = go(join(conquest_game("season21"), "huang"), "changshe")
    s, c = game.state, game.content
    s.world.orders.append(Order(id="t:huang:intercept", template="intercept", faction="huang", week=orders.period_of(s, c),
                                location="changshe", quota=4, text="（測試）"))
    convoy = c.orders.convoy_squads["guan"]
    option = _train(game)
    assert option is not None and option.enabled and "攻" in option.label
    assert game._sortie_foes(c.locations["changshe"]) == [convoy]
    assert "changshe" in mapview.armed_places(s, c)
    note = _note(game, "changshe")
    assert note.startswith("對面的運糧隊正打這裡經過：") and "不在爭奪之列" in note and "推這一塊的進度" not in note


def test_own_base_still_holds():
    game = go(join(conquest_game("season21"), "guan"), "changshe")
    option = _train(game)
    assert option is not None and option.enabled and "守" in option.label


# ── 原 test_conquest_front_note.py（整檔搬進來） ──
# 時刻表決戰的起點照哪一條戰線（企劃者 2026-10-22 選計畫 2026-10-22-長社火攻主場 第七節第 4 條：不另加主場偏移，照現在的規則補一句說明）。
#
# 領地爭奪開著的季，時刻表決戰（寫了戰線的：長社火攻、宛城、廣宗、天命之爭）的起點照那條線的戰況算（start_from_front），戰況又照佔領算；
# 開集結那一刻把「那條線上的區塊誰佔幾處、照戰況換算的起點」快照進 BattleInstance.front_note，之後不重算：
# - 天下大事一則：先寫起點照戰況偏幾點，另一句寫那條線上的地盤（FB-686：不能讀成「佔得多就往那邊偏」）；
# - 決戰畫面標題底下一行短句：只寫偏幾點與哪一條線（FB-685：375／360／320 都本來就一行、數字不在句尾）；
# - 天命之爭的碎片那一句改寫成「再」偏的那一份（FB-687）。
# 領地爭奪關著、沒寫戰線、舊資料：什麼都不寫（存檔連鍵都沒有）。

CHANGSHE = "changshe_fire"


WHY = "（戰況從開季的態勢算起，之後的易手與各路推動都算在裡面）"


def _hold(game, given: dict[str, str]) -> None:
    c = game.content

    def _set(season):
        for loc, side in given.items():
            assert conquest.set_control(season, c, loc, side)
        territory.update(season, c)

    game.world.mutate_season(_set)


def _muster(game, battle_id: str = CHANGSHE, given: dict[str, str] | None = None):
    """開集結（時刻表與管理者「立刻開這一場」走的 world._open_claimed），起點照戰況（showdown_start）。"""
    c, world = game.content, game.world
    if given:
        _hold(game, given)
    d = c.battles[battle_id]
    msgs = world_mod._open_claimed(world, c, 0.0, lambda vehicle: (d, world_mod.showdown_start(vehicle, c, d)))  # noqa: SLF001
    return d, msgs, world.get_battle(), world.get_season()


def test_changshe_at_season_open_says_who_holds_the_line():
    game = conquest_game("season21")
    d, msgs, battle, season = _muster(game)
    assert battle.trend_start == battle.trend == 55  # 起點照舊（不另加偏移）
    assert battle.front_note == bi.FrontNote(line="yingru", start=55, held={"guan": 8, "huang": 5}, open=2)
    line = f"長社火攻開集結：戰局起點照潁川汝南此刻的戰況往官軍偏了 5 點{WHY}。潁川汝南一帶的地盤此刻官軍佔 8 處、黃巾軍佔 5 處、2 處還沒人佔。"
    assert f"🗺️ 【天下大事】{line}" in msgs
    assert any(r.text == line and r.layer == "world" for r in season.rumors)
    scene = game._battle_scene_text(battle, d)  # noqa: SLF001
    assert "\n\n起點偏官軍 5 點：潁川汝南戰況\n\n" in scene
    assert "處" not in conquest.front_scene(game.content, d, battle.front_note)  # 佔幾處只寫在天下大事那一則（FB-685）


def test_yellow_turbans_took_the_two_neutral_blocks():
    """開著的季，佔領一：黃巾拿下潁川汝南兩塊中立地，起點往黃巾偏，沒人佔的那一段不寫。"""
    game = conquest_game("season21")
    d, msgs, battle, season = _muster(game, given={"runan_wilds": "huang", "hilltop_wilds": "huang"})
    assert battle.trend_start == 38
    assert battle.front_note == bi.FrontNote(line="yingru", start=38, held={"guan": 8, "huang": 7}, open=0)
    line = f"長社火攻開集結：戰局起點照潁川汝南此刻的戰況往黃巾軍偏了 12 點{WHY}。潁川汝南一帶的地盤此刻官軍佔 8 處、黃巾軍佔 7 處。"
    assert any(r.text == line for r in season.rumors)
    assert "\n\n起點偏黃巾軍 12 點：潁川汝南戰況\n\n" in game._battle_scene_text(battle, d)  # noqa: SLF001


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
def test_han_army_took_runan_wilds_on_the_weekend():
    """開著的季，佔領二（週末）：官軍拿下汝南荒野。"""
    game = conquest_game("week7")
    d, msgs, battle, season = _muster(game, given={"runan_wilds": "guan"})
    assert battle.front_note == bi.FrontNote(line="yingru", start=64, held={"guan": 9, "huang": 5}, open=1)
    assert (f"🗺️ 【天下大事】長社火攻開集結：戰局起點照潁川汝南此刻的戰況往官軍偏了 14 點{WHY}。"
            "潁川汝南一帶的地盤此刻官軍佔 9 處、黃巾軍佔 5 處、1 處還沒人佔。") in msgs
    assert "\n\n起點偏官軍 14 點：潁川汝南戰況\n\n" in game._battle_scene_text(battle, d)  # noqa: SLF001


def test_the_screen_keeps_the_muster_snapshot():
    """數字是開集結那一刻的：之後易手了（戰況變了），決戰畫面照舊寫開集結那一刻的，資料庫讀回來也是同一份。"""
    game = conquest_game("season21")
    d, _, battle, _ = _muster(game)
    _hold(game, {"runan_wilds": "huang", "hilltop_wilds": "huang", "yingchuan_wilds": "huang"})
    now = bi.start_from_front(game.world.get_season().trends["yingru"])
    assert now != 55  # 戰況真的變了：重算的話畫面會不一樣
    again = game.world.get_battle()
    assert again.front_note == battle.front_note
    assert "起點偏官軍 5 點：潁川汝南戰況" in game._battle_scene_text(again, d)  # noqa: SLF001
    assert '"front_note":{"line":"yingru","start":55' in again.model_dump_json(exclude={"record_id", "rounds"})


def test_every_timetable_showdown_with_a_front_gets_it():
    """宛城（南陽）、廣宗（冀州）一樣照自己那條線寫；沒寫戰線的（beta 的黃巾決戰）不寫。"""
    for battle_id, line, name in (("wancheng_jia", "nanyang", "南陽"), ("guangzong", "jizhou", "冀州")):
        game = conquest_game("season21")
        d, msgs, battle, season = _muster(game, battle_id)
        note = battle.front_note
        assert note is not None and note.line == line and note.start == battle.trend_start
        held, unheld = conquest.line_holdings(season, game.content, line)
        assert sum(note.held.values()) + note.open == sum(held.values()) + unheld
        assert any(m.startswith("🗺️ 【天下大事】") and f"{name}一帶的地盤此刻" in m for m in msgs)
        assert f"：{name}戰況" in game._battle_scene_text(battle, d)  # noqa: SLF001
        if battle_id == "guangzong":  # 大本營與廣宗也算（同輿圖）：開季的冀州不寫成「黃巾軍佔 0 處」
            assert note.held == {"guan": 5, "huang": 2} and note.open == 3
            assert any("冀州一帶的地盤此刻官軍佔 5 處、黃巾軍佔 2 處、3 處還沒人佔" in m for m in msgs)
    game = conquest_game("season21")
    d, msgs, battle, season = _muster(game, "huangjin_showdown")
    assert d.front is None and battle.front_note is None
    assert not any("🗺️" in m for m in msgs)
    assert "戰況" not in game._battle_scene_text(battle, d).split("\n\n")[1]  # 標題底下沒有那一行  # noqa: SLF001


def _width(text: str) -> float:
    """排出來大約幾個字寬：全形（中文、全形標點）一個，半形（數字、空格）半個。"""
    return sum(1.0 if unicodedata.east_asian_width(ch) in "WF" else 0.5 for ch in text)


def test_fb685_the_battle_screen_line_is_one_short_line():
    """FB-685（PM 2026-10-22）：決戰畫面那一句只留一行短句——320 寬那一段約 16.6 個字寬（15.5px 的字、258px），最長的局面
    （黃巾軍、兩位數、潁川汝南）也要在 16 個字寬以內；數字不在句尾（收成一行時句尾的數字會被「…」吃掉，fitDigitsShown 就不收）；
    不寫佔幾處。三條線、起點 25～75 每一種都量。"""
    c = conquest_game("season21").content
    for battle_id in ("changshe_fire", "wancheng_jia", "wancheng_yi", "guangzong", "tianming"):
        d = c.battles[battle_id]
        for start in range(25, 76):
            line = conquest.front_scene(c, d, bi.FrontNote(line=d.front, start=start, held={"guan": 9, "huang": 9}, open=9))
            assert _width(line) <= 16, (battle_id, start, line, _width(line))
            assert not re.search(r"[0-9０-９][^0-9０-９]{0,2}$", line), line
            assert "處" not in line and "\n" not in line
    d = c.battles[CHANGSHE]
    assert conquest.front_scene(c, d, bi.FrontNote(line="yingru", start=50)) == "起點不偏：潁川汝南戰況"
    assert conquest.front_scene(c, d, None) == ""


def test_fb686_the_lean_and_the_holdings_are_two_sentences():
    """FB-686（PM 2026-10-22）：冀州開季官軍佔 5 處、黃巾軍佔 2 處，起點卻往黃巾軍偏 2 點（開季的態勢本來就偏黃巾）。天下大事把
    「起點照戰況偏幾點」與「地盤此刻誰佔幾處」寫成兩句：前一句不提處數、後一句不提偏，中間不用因果連起來。"""
    game = conquest_game("season21")
    d, msgs, battle, season = _muster(game, "guangzong")
    assert battle.trend_start == 48
    line = next(r.text for r in season.rumors if r.text.startswith("廣宗決戰開集結："))
    assert line == (f"廣宗決戰開集結：戰局起點照冀州此刻的戰況往黃巾軍偏了 2 點{WHY}。"
                    "冀州一帶的地盤此刻官軍佔 5 處、黃巾軍佔 2 處、3 處還沒人佔。")
    first, second, rest = line.split("。")
    assert "處" not in first and "偏" in first and rest == ""
    assert "偏" not in second and "處" in second
    assert not re.search(r"所以|因此|因為|於是|故", line)


def test_fb687_the_mandate_line_says_the_shards_add_nothing_more():
    """FB-687（PM 2026-10-22）：天命之爭在領地爭奪開著的季，前一句寫起點照冀州戰況偏 2 點，碎片那一句不再寫「戰局起點不偏」
    （講的是碎片另加的那一份），改成「起點不再另偏」／「起點再往某軍偏 N 點」。畫面與天下大事都是。"""
    game = conquest_game("season21")
    d, msgs, battle, season = _muster(game, "tianming")
    assert seal.on(game.content) and seal.is_mandate_battle(game.content, d)
    scene = game._battle_scene_text(battle, d)  # noqa: SLF001
    assert "\n\n起點偏黃巾軍 2 點：冀州戰況\n\n天命之爭：玉璽碎片不在交戰的任何一方手上，起點不再另偏。" in scene
    assert "戰局起點不偏" not in scene
    rumors = [r.text for r in season.rumors]
    assert "天命之爭集結：玉璽碎片不在交戰的任何一方手上，起點不再另偏。" in rumors
    assert not any("戰局起點不偏" in t for t in rumors)
    two = {"guan": 2, "huang": 1}
    assert seal.shift_text(3, two, d, extra=True) == "起點再往官軍偏 3 點"
    assert seal.shift_text(-6, {"huang": 2}, d, extra=True) == "起點再往黃巾軍偏 6 點"
    assert seal.shift_text(0, {"guan": 1, "huang": 1}, d, extra=True) == "兩軍持璽相當，起點不再另偏"
    assert seal.shift_text(0, {}, d, extra=True) == "起點不再另偏"


def test_old_rows_without_the_snapshot_still_render():
    """舊資料（這一版以前開的決戰，那一列沒有 front_note）：讀得進來、是 None，畫面不多寫、不炸。"""
    game = conquest_game("season21")
    d, _, battle, _ = _muster(game)
    data = json.loads(battle.model_dump_json())
    assert data.pop("front_note")["line"] == "yingru"
    old = bi.BattleInstance.model_validate_json(json.dumps(data, ensure_ascii=False))
    assert old.front_note is None and old.battle_id == battle.battle_id
    assert "戰況" not in game._battle_scene_text(old, d).split("\n\n")[1]  # noqa: SLF001
    game.world.mutate_battle(lambda b: setattr(b, "front_note", None))
    stored = game.world.get_battle()
    assert stored.front_note is None
    assert "起點偏" not in game._battle_scene_text(stored, d)  # noqa: SLF001
    assert conquest.front_scene(game.content, d, None) == ""


# ── 原 test_conquest_seal.py（整檔搬進來） ──
# 領地爭奪第三批 B（計畫 docs/superpowers/plans/2026-10-20-領地爭奪.md Task 14，設計 3.9、4.8）：玉璽碎片藏在開季中立的區塊、
# 探索撿到。只動「碎片從哪裡來」：效果、傳承那一格、璽動、單挑、天命之季都照舊（test_seal*.py）。

NAME = "沈浪"


def _content(hide: float = 1.0, find: float = 1.0, profile: str = "season21"):
    """正式內容（21 天季）、領地爭奪打開；hide／find 是這一批的兩個機率（1.0＝一定藏、一定撿到，好測）。"""
    c = no_jianfa(conquest_rules(real_content(profile)))  # 這一份測探索三選一撿碎片（explore:*）；出門一趟撿碎片在 tests/test_explore_one.py
    c.config.seal.cache.hide_chance, c.config.seal.cache.find_chance = hide, find
    return c


def _game_seal(hide: float = 1.0, find: float = 1.0, name: str = NAME, world=None, content=None):
    return _new(content or _content(hide, find), name, world)


def _cache(game) -> SealCache | None:
    return game.world.seal_state().registry.cache


def _reg(game) -> SealRegistry:
    return game.world.seal_state().registry


def _neutral_seal(content) -> list[str]:
    return [loc for loc, block in conquest.blocks(content).items() if block.kind == "neutral"]


def _stand(game, loc_id: str, faction: str | None = None):
    join(game, faction)
    go(game, loc_id)
    return game


def _mode_for(game, mode: str) -> str:
    """explore_modes 的四種：找素材有分支層時要指一條分支（不然只回 GATHER_PICK、不花體力）。"""
    if mode != "gather":
        return mode
    loc = game.content.locations[game.state.player.location]
    layers = explore_modes.layered(game.content, game.state.world, loc)
    return f"gather:{layers[0].id}" if layers else "gather"


def _move_cache(game, loc_id: str) -> None:
    game.world.mutate(lambda st: setattr(st.seal.cache, "loc", loc_id))


# ── 藏 ──────────────────────────────────────────────


def test_hide_is_deterministic_with_salt_and_only_neutral_spots():
    """開季那一刻：同一份密鹽＋天機＋季數藏在同一個地方；只藏在開季中立的區塊；不同的密鹽藏在不同的地方（不只一處）。"""
    c = _content()
    g1, g2 = _game_seal(content=_content()), _game_seal(content=_content())
    a, b = _cache(g1), _cache(g2)
    assert a is not None and a == b  # 測試沒有密鹽：同樣的種子同樣的結果
    neutral = set(_neutral_seal(c))
    assert a.loc in neutral and a.shard in c.seal and a.season == 1
    spots = seal.hide_spots(c, g1.state.world)
    assert {loc for loc, _ in spots} == neutral
    seen = set()
    for i in range(80):
        reg = seal.filled(SealRegistry(salt=f"鹽{i}"), c)
        cache = seal.hide(reg, c, 1, 0, spots)
        assert cache is not None and cache.loc in neutral
        assert cache == seal.hide(seal.filled(SealRegistry(salt=f"鹽{i}"), c), c, 1, 0, spots)
        seen.add(cache.loc)
    assert len(seen) >= 4  # 十處左右的中立地都有可能


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
def test_hide_chance_gates_the_whole_season():
    """開季先擲 hide_chance：0 一片都不藏、1 一定藏；0.4 時大約四成的季有一片藏著。"""
    c = _content()
    spots = seal.hide_spots(c, _game_seal(content=_content()).state.world)

    def hidden(chance: float, n: int = 400) -> int:
        c.config.seal.cache.hide_chance = chance
        return sum(seal.hide(seal.filled(SealRegistry(salt=f"鹽{i}"), c), c, 1, 0, spots) is not None for i in range(n))

    assert hidden(0.0) == 0 and hidden(1.0) == 400
    assert 0.32 < hidden(0.4) / 400 < 0.48
    assert _cache(_game_seal(hide=0.0)) is None


def test_hide_skips_when_nothing_is_left_to_hide():
    """這一輪七片都現世過、不在「未現世」了：沒有可藏的；這一季已經現世過一片也不再藏。"""
    c = _content()
    spots = seal.hide_spots(c, _game_seal(content=_content()).state.world)
    reg = seal.filled(SealRegistry(), c)
    for shard in reg.shards.values():
        shard.state = "sunk"
    assert seal.hide(reg, c, 1, 0, spots) is None
    reg = seal.filled(SealRegistry(emerge_season=1), c)
    assert seal.hide(reg, c, 1, 0, spots) is None


def test_core_regions_weigh_more_and_the_default_names_the_core_region():
    """核心加權（輿圖簡化設計 3.1，企劃者定「核心的機率最高」）：地點落在 core_regions 的大區，權重是 core_weight，其餘 1。
    預設的大區 id 是 "core"（新地理的核心自成一區）；今天的地圖沒有這一區，所以全是 1。"""
    c = _content()
    cfg = c.config.seal.cache
    assert cfg.core_regions == ["core"] and cfg.core_weight > 1
    world = _game_seal(content=_content()).state.world
    assert {w for _, w in seal.hide_spots(c, world)} == {1.0}  # 今天的地圖沒有 core 這一區
    loc = _neutral_seal(c)[0]
    cfg.core_regions, cfg.core_weight = [atlas.region_of(c, loc).id], 9.0
    weights = dict(seal.hide_spots(c, world))
    heavy = {l for l in weights if atlas.region_of(c, l).id == cfg.core_regions[0]}
    assert heavy and all(weights[l] == 9.0 for l in heavy) and all(w == 1.0 for l, w in weights.items() if l not in heavy)
    picked = [seal.hide(seal.filled(SealRegistry(salt=f"鹽{i}"), c), c, 1, 0, list(weights.items())).loc for i in range(600)]
    share = sum(p in heavy for p in picked) / 600
    want = 9.0 * len(heavy) / (9.0 * len(heavy) + len(weights) - len(heavy))
    assert abs(share - want) < 0.07


def test_no_cache_when_the_seal_is_off():
    """主機關掉碎片：什麼都不藏。"""
    off = _content()
    off.config.seal.enabled = False  # 主機關掉碎片
    assert _cache(_game_seal(content=off)) is None


def test_a_new_season_clears_the_old_cache_and_hides_again():
    """上一季沒撿到的清掉；新的一季照 hide_chance 重擲（季數記在藏處上）。"""
    c = _content(find=0.0)
    game = _game_seal(content=c)
    assert _cache(game).season == 1
    next_season(c, game.world)
    assert _cache(game).season == 2 and _reg(game).emerge_season is None
    c.config.seal.cache.hide_chance = 0.0
    next_season(c, game.world)
    assert _cache(game) is None


def test_the_mandate_season_hides_nothing_and_the_one_after_hides_again():
    """天命之季（七片都現世過）不藏；再下一季七片散去，照常藏。"""
    c = _content(find=0.0)
    game = _game_seal(content=c)

    def _all_emerged(st):
        reg = seal.filled(st.seal, c)
        for shard in reg.shards.values():
            shard.state, shard.emerged_round = "sunk", reg.round
        reg.shards["chishou"].state = "hidden"  # 現世過卻回到未現世（管理者收回）：還有一片可藏，不藏是因為天命之季，不是因為沒東西可藏

    game.world.mutate(_all_emerged)
    next_season(c, game.world)
    assert game.world.get_season().mandate and _cache(game) is None
    next_season(c, game.world)
    assert not game.world.get_season().mandate and _cache(game) is not None and _cache(game).season == 3


# ── 撿 ──────────────────────────────────────────────


@pytest.mark.parametrize("mode", ["gather", "seek", "sense", "practice"])
def test_find_only_at_the_cache_and_all_four_explore_modes_roll(mode):
    """只在藏碎片的那一塊擲；探索的四種（找素材、找事件、靜心感悟、練功，計畫第八章裁決 13）都擲。別處探索一百次也撿不到。"""
    game = _game_seal()
    cache = _cache(game)
    away = next(loc for loc in _neutral_seal(game.content) if loc != cache.loc)
    _stand(game, away)
    for _ in range(6):
        game._explore_mode(_mode_for(game, mode))
        game.state.player.stamina = 250.0
    assert seal.shard_of(_reg(game), NAME) is None and _cache(game) == cache  # 沒藏碎片的塊：不擲、藏處紋風不動
    go(game, cache.loc)
    game._explore_mode(_mode_for(game, mode))
    reg = _reg(game)
    shard = seal.shard_of(reg, NAME)
    assert shard is not None and shard.id == cache.shard and shard.since_season == 1 and shard.emerged_round == reg.round
    assert reg.cache is None and reg.emerge_season == 1
    event = reg.history[-1]
    assert (event.kind, event.shard, event.holder, event.record, event.where) == ("emerge", cache.shard, NAME, None, "")


def test_the_finder_gets_the_heirloom_and_learns_the_emerge_skill():
    """撿到的人：傳承那一格、同一季補送時學會混元一氣（Config.seal.emerge_skill，原本跟宛城現世的得主一起送）、紀錄一則、行狀一筆。"""
    game = _game_seal()
    _stand(game, _cache(game).loc)
    assert "hunyuan" not in library.owned_arts(game.state)
    game.choose(f"explore:{_mode_for(game, 'seek')}")
    p = game.state.player
    assert p.heirloom is not None and p.heirloom.template == seal.shard_of(_reg(game), NAME).id
    assert "hunyuan" in library.owned_arts(game.state)
    titles = [e.title for e in game.state.journal]
    assert seal.SEAL_TITLE in titles


def test_one_shard_per_season_and_nobody_else_finds_it():
    """撿走了就沒了：同一塊再探索一百次也不會有第二片；這一季不會再藏。"""
    game = _game_seal()
    loc = _cache(game).loc
    _stand(game, loc)
    game._explore_mode(_mode_for(game, "seek"))
    other = _new(game.content, "旁人", game.world)
    _stand(other, loc)
    for _ in range(5):
        other._explore_mode(_mode_for(other, "seek"))
        other.state.player.stamina = 250.0
    assert seal.shard_of(_reg(other), "旁人") is None
    assert len(seal.holders(_reg(other))) == 1 and _cache(other) is None


def test_someone_who_already_holds_a_shard_does_not_find_a_second():
    """一人一片：手上有碎片的人在藏處探索不擲，藏處留給別人。"""
    game = _game_seal()
    cache = _cache(game)
    held = next(s for s in game.content.seal if s != cache.shard)

    def _hold(st):
        shard = st.seal.shards[held]
        shard.state, shard.holder = "held", NAME

    game.world.mutate(_hold)
    _stand(game, cache.loc)
    game._explore_mode(_mode_for(game, "seek"))
    assert _cache(game) == cache and seal.shard_of(_reg(game), NAME).id == held


def test_no_find_while_the_block_is_cooling():
    """翻地與爭搶（輿圖簡化設計 4.1；翻地計畫第一節第 9 條）：剛易手、還在冷卻的那一塊加成暫停，碎片也不擲（藏處紋風不動）；冷卻過了照擲。"""
    game = _game_seal()
    cache = _cache(game)
    _stand(game, cache.loc, "guan")
    w, c = game.state.world, game.content
    conquest.flip(w, c, cache.loc, "guan")  # 官軍剛拿下：冷卻 cooldown_minutes
    game._save_season()
    assert conquest.cooling(game.state.world, c, cache.loc)
    for _ in range(3):
        game._explore_mode(_mode_for(game, "seek"))
        game.state.player.stamina = 250.0
    assert conquest.cooling(game.state.world, c, cache.loc)
    assert seal.shard_of(_reg(game), NAME) is None and _cache(game) == cache  # 修前冷卻期照擲（find_chance 1.0：一定撿到）
    fight = game.state.world.conquest.fights[cache.loc]
    fight.flipped_at -= conquest._seconds(c, c.config.conquest.cooldown_minutes) + 1  # 冷卻過了
    game._save_season()
    game._explore_mode(_mode_for(game, "seek"))
    assert seal.shard_of(_reg(game), NAME) is not None


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
def test_the_find_roll_scales_for_the_holding_side(monkeypatch):
    """那一塊此刻歸你的陣營，機率再高一點（設計 3.9）：own_scale。純機率驗一次、再驗 Game 傳給 seal.find 的 own 旗標。"""
    cfg = _content().config.seal
    cfg.cache.find_chance, cfg.cache.own_scale = 0.4, 2.0
    reg = SealRegistry(salt="鹽")
    plain = sum(seal.find(reg, 0, "甲", n, False, cfg) for n in range(2000)) / 2000
    own = sum(seal.find(reg, 0, "甲", n, True, cfg) for n in range(2000)) / 2000
    assert 0.35 < plain < 0.45 and 0.75 < own < 0.85
    assert seal.find(reg, 0, "甲", 1, True, _content(find=0.9).config.seal) in (True, False)  # 上限夾在 1：不會炸

    game = _game_seal(find=0.0)
    loc = _cache(game).loc
    calls = []
    monkeypatch.setattr(seal, "find", lambda reg_, tianji, name, seq, own_, cfg_: calls.append(own_) or False)
    _stand(game, loc, "guan")
    game._explore_mode(_mode_for(game, "seek"))  # 沒人佔的中立地：不算自家
    conquest.set_control(game.state.world, game.content, loc, "guan")
    game._explore_mode(_mode_for(game, "seek"))  # 官軍佔下了：官軍的人算自家
    game.state.player.faction = "huang"
    game._explore_mode(_mode_for(game, "seek"))  # 黃巾的人在官軍佔的地方：不算
    assert calls == [False, True, False]


def test_a_gentry_follower_gets_the_scale_on_the_side_he_follows_and_a_ranger_never_does(monkeypatch):
    """FB-571（PM 裁決）：豪強依附一軍，那一軍佔著的藏處算他的自家（照 rules.side_of，同療傷、打造、買馬的地盤折扣）；散人沒有自家、不乘
    ——沒人佔的藏處控制方是 None、散人的 side 也是 None，不能被 None == None 騙成「自家」。"""
    game = _game_seal(find=0.0)
    loc = _cache(game).loc
    calls = []
    monkeypatch.setattr(seal, "find", lambda reg_, tianji, name, seq, own_, cfg_: calls.append(own_) or False)
    _stand(game, loc, "haoqiang")
    p = game.state.player
    assert game.state.world.haoqiang_allied
    p.ally = "guan"
    game._explore_mode(_mode_for(game, "seek"))  # 沒人佔：不算
    conquest.set_control(game.state.world, game.content, loc, "guan")
    game._explore_mode(_mode_for(game, "seek"))  # 他依附的官軍佔下了：算自家
    conquest.set_control(game.state.world, game.content, loc, "huang")
    game._explore_mode(_mode_for(game, "seek"))  # 另一軍佔著：不算
    p.ally = "huang"
    game._explore_mode(_mode_for(game, "seek"))  # 改依附黃巾：算
    assert calls == [False, True, False, True]
    calls.clear()
    p.faction, p.ally = None, None  # 散人
    conquest.set_control(game.state.world, game.content, loc, None)
    game._explore_mode(_mode_for(game, "seek"))  # 沒人佔（控制方 None）：散人也不算
    conquest.set_control(game.state.world, game.content, loc, "guan")
    game._explore_mode(_mode_for(game, "seek"))
    assert calls == [False, False]


def test_the_find_dice_never_touch_game_rng():
    """擲骰用密鹽的亂數，不碰 Game.rng：整季測試與量表的序列不位移。"""
    game = _game_seal(find=0.0)
    _stand(game, _cache(game).loc)
    before = game.rng.getstate()
    game._seal_find(game.state.player.location)
    assert game.rng.getstate() == before


def _admin_game_seal(hide: float = 1.0, find: float = 1.0):
    c = _content(hide, find)
    c.config.admins = [NAME]
    return _game_seal(content=c)


def test_stamping_the_mandate_mid_season_clears_the_cache():
    """FB-570：管理者在這一季「立刻蓋天命之季的章」，藏著的那一片當場清掉（跟自然換季那條路一樣：天命之季不藏），天命之季裡探索撿不到；
    登記上那一片還是未現世。"""
    game = _admin_game_seal()
    cache = _cache(game)
    assert cache is not None
    out = game.admin_seal_mandate("now")
    assert game.world.get_season().mandate and any("天命之季" in line for line in out)
    assert _cache(game) is None
    _stand(game, cache.loc)
    game._explore_mode(_mode_for(game, "seek"))
    reg = _reg(game)
    assert seal.shard_of(reg, NAME) is None and reg.shards[cache.shard].state == "hidden" and reg.emerge_season is None


def test_a_cache_left_in_a_mandate_season_is_not_live():
    """FB-570：就算登記上留著一個藏處（舊資料、別的路徑蓋章），天命之季也當它不存在。"""
    c = _content()
    reg = seal.filled(SealRegistry(), c)
    reg.cache = SealCache(season=3, shard="chishou", loc=_neutral_seal(c)[0])
    assert seal.live_cache(reg, 3) is reg.cache
    reg.mandate_season = 3
    assert seal.live_cache(reg, 3) is None
    spots = seal.hide_spots(c, _game_seal(content=_content()).state.world)
    assert seal.hide(reg, c, 3, 0, spots, force=True) is None


def test_hide_now_says_no_in_a_mandate_season():
    """FB-570：天命之季裡按「現在藏一片」回一句不藏的話，不登記藏處（自然換季天命之季本來就不藏）。"""
    game = _admin_game_seal(hide=0.0, find=1.0)
    assert _cache(game) is None
    game.admin_seal_mandate("now")
    out = game.admin_seal_emerge("guixin")
    assert _cache(game) is None and any(seal.HIDE_MANDATE in line for line in out)
    assert "天命之季" in seal.HIDE_MANDATE


# ── 不漏 ────────────────────────────────────────────


def _snapshot(game) -> dict:
    """玩家與其他人從任何地方看得到的東西：江湖頁／狀態列（/api/main）、江湖史、傳聞、管理者的玉璽那一組。"""
    season = game.world.get_season()
    return {
        "main": json.dumps(server.main_view(game), ensure_ascii=False, sort_keys=True, default=str),
        "chronicle": game.chronicle_text(),
        "rumors": [(r.layer, r.text) for r in season.rumors],
        "history": [(r.text) for r in season.chronicle],
        "admin": json.dumps(game.admin_seal_choices(), ensure_ascii=False, sort_keys=True, default=str),
    }


def test_the_hiding_place_is_not_observable_from_outside():
    """藏在哪裡不公開（計畫 Task 14）：兩個世界一模一樣、只有碎片藏的地方不同，畫面、API、江湖史、傳聞、管理者的玉璽那一組都一個字
    不差；在藏處探索沒擲中的那一下，玩家的狀態也一個字不差（江湖紀錄、亂數）。"""
    a, b = _game_seal(find=0.0), _game_seal(find=0.0)
    spots = _neutral_seal(a.content)
    here, there = spots[0], spots[-1]
    _move_cache(a, here)
    _move_cache(b, there)
    assert _snapshot(a) == _snapshot(b)
    for game in (a, b):
        _stand(game, here)
        game.choose(f"explore:{_mode_for(game, 'seek')}")
    assert _snapshot(a) == _snapshot(b)
    assert a.state.player.model_dump_json() == b.state.player.model_dump_json()
    assert a.rng.getstate() == b.rng.getstate()


def test_the_find_is_announced_without_naming_the_place():
    """撿到的那一句天下大事與江湖史、補送的紀錄都不寫是在哪一塊撿到的。"""
    game = _game_seal()
    loc = _cache(game).loc
    place = game.content.locations[loc].name
    _stand(game, loc)
    game._explore_mode(_mode_for(game, "seek"))
    season = game.world.get_season()
    said = [r.text for r in season.rumors if r.layer == "world"] + [r.text for r in season.chronicle] + [game.chronicle_text()]
    assert any(NAME in line and "傳國玉璽" in line for line in said)
    assert not any(place in line or loc in line for line in said)
    assert not any(place in line for e in game.state.journal if e.title == seal.SEAL_TITLE for line in e.lines)


# ── 宛城、管理者 ────────────────────────────────────


def _muster_wancheng(content):
    game = _new(content, NAME)
    game.world.mutate(lambda st: setattr(seal.filled(st.seal, content), "force_emerge", "yunzhuan"))
    world_rules.open_showdown(game.world, content, "wancheng", 0.0)
    return game, game.world.get_battle()


def test_wancheng_does_not_emerge_under_conquest_but_still_does_without_it():
    """領地爭奪的季不擲宛城現世（碎片只從探索來）；璽動照舊。"""
    c = _content(hide=0.0)
    c.config.seal.emerge_chance = 1.0
    game, battle = _muster_wancheng(c)
    assert battle is not None and battle.seal_emerge is None
    assert seal.EMERGE_OMEN.format(battle="宛城之戰") not in [r.text for r in game.world.get_season().rumors]
    assert _reg(game).force_emerge == "yunzhuan"  # 管理者的記號留著，不吃掉


def test_the_admin_hides_one_now_under_conquest_and_still_forces_emergence_otherwise():
    """管理者「強制現世」在領地爭奪的季改成「現在藏一片」：略過 hide_chance，可指定哪一片；回話不寫藏在哪；已經藏著、這一季已經現世過
    都不再藏。"""
    c = _content(hide=0.0, find=0.0)
    c.config.admins = [NAME]
    game = _game_seal(content=c)
    assert _cache(game) is None and game.admin_seal_choices()["hide"] is True
    out = game.admin_seal_emerge("guixin")
    cache = _cache(game)
    assert cache is not None and cache.shard == "guixin" and cache.season == 1 and cache.loc in _neutral_seal(c)
    assert not any(cache.loc in line or c.locations[cache.loc].name in line for line in out)
    assert any("已經藏著" in line for line in game.admin_seal_emerge())  # 再按一次：不換地方
    assert _cache(game) == cache and _reg(game).force_emerge is None
    assert any("沒有這一片" in line for line in game.admin_seal_emerge("沒有"))
    game.world.mutate(lambda st: setattr(st.seal, "cache", None))
    game.world.mutate(lambda st: setattr(st.seal, "emerge_season", 1))
    assert any("這一季" in line for line in game.admin_seal_emerge())
    assert _cache(game) is None


def test_the_howto_says_where_shards_come_from_without_saying_where():
    """玩法說明「地盤」：碎片只在開季中立的地方、探索才撿得到（設計 3.9，玩家看得出為什麼要搶這一塊）；不寫是哪一塊。碎片關著不寫。"""
    from tianxia import howto

    c = _content()
    lines = [line for line in howto.conquest_lines(c) if "碎片" in line]
    assert len(lines) == 1 and "探索" in lines[0] and "沒人知道" in lines[0]
    assert not any(c.locations[loc].name in lines[0] for loc in _neutral_seal(c))
    c.config.seal.enabled = False
    assert not any("碎片" in line for line in howto.conquest_lines(c))
