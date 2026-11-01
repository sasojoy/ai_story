"""坐騎（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第五節；計畫 docs/superpowers/plans/2026-10-11-裝備-2-坐騎.md）。"""
from __future__ import annotations

import math
import random

import pytest

from conftest import next_season, real_content, walk_to
from tianxia import atlas, encounter, equipment, mounts, rules
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.state import Equipment, GameState, Journey, Tagalong


def _on(content):
    """打開坐騎（測試內容三欄都關著）。"""
    content.config.mounts.enabled = True
    return content


def _horse(tier=1, quality="下品", edge=100, hid="騎:1", name="棗騮馬"):
    return Equipment(id=hid, slot="mount", name=name, tier=tier, quality=quality, edge=edge)


def _game(content, world, name="騎客", at="town", stamina=100.0, silver=200, horse=None):
    """坐騎開著的一個角色，同步過了才擺好：人在 at、體力、銀兩、身上那匹。測試內容：小鎮—湖邊 3 分鐘路程，趕路每分鐘 1 點、疾行 2 點。"""
    _on(content)
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    game.sync(0.0)
    p = game.state.player
    p.location, p.stamina, p.stats["silver"], p.mount = at, stamina, silver, horse
    return game


def _ids(game):
    return {o.id: o for o in game.options(odds=False)}


# ── Task 1：資料形狀與數字 ──

def test_the_mount_slot_is_on_by_its_own_switch(content):
    assert not equipment.on(content, "mount")  # 測試內容關著（設計 2.6）
    _on(content)
    slot = equipment.SLOTS["mount"]
    assert equipment.on(content, "mount") and (slot.prefix, slot.label, slot.road_locked) == ("騎", "坐騎", True)
    assert "mount" in equipment.WIELDABLE and "mount" not in equipment.DISMANTLABLE  # 坐騎能換、不能拆（4.8）
    assert not equipment.SLOTS["weapon"].road_locked and not equipment.SLOTS["armor"].road_locked


def test_a_horse_saves_stamina_speeds_the_road_and_counts_how_fed_it_is(content, state):
    """設計 5.1：省體力 25／40／55%、路上快 30／45／60%（品質中 +3、上 +5 個百分點只加這兩列）、騎兵 5／10／15%、脫身 30／50／70%，
    全部乘飽足係數（0.5＋0.5×飽足度／100）；腳力＝省體力×飽足係數。"""
    _on(content)
    p = state.player

    def numbers():
        return (mounts.saving(state, content), mounts.pace(state, content), mounts.cavalry(state, content), mounts.escape(state, content))

    assert numbers() == (0.0, 1.0, 0.0, 0.0)  # 沒騎馬
    p.mount = _horse()
    assert numbers() == pytest.approx((0.25, 0.70, 0.05, 0.30))
    p.mount.edge = 50  # 飽足係數 0.75
    assert numbers() == pytest.approx((0.1875, 0.775, 0.0375, 0.225))
    p.mount.edge = 0  # 餓到底剩一半
    assert numbers() == pytest.approx((0.125, 0.85, 0.025, 0.15))
    p.mount = _horse(tier=2, quality="中品")  # 品質只加省體力、路上快
    assert numbers() == pytest.approx((0.43, 0.52, 0.10, 0.50))
    p.mount = _horse(tier=3, quality="上品")  # 最好的名駒上品省 60%、快 65%
    assert numbers() == pytest.approx((0.60, 0.35, 0.15, 0.70))
    content.config.mounts.enabled = False  # 開關關著：騎著也當沒騎
    assert numbers() == (0.0, 1.0, 0.0, 0.0)


def test_horse_names_and_grades_are_original(content):
    from tianxia import naming
    names = [mounts.horse_name(coat, tier) for coat in mounts.COATS for tier in (1, 2)]
    first = mounts.COATS[0]
    assert len(set(names)) == 12 and names[:2] == [first + mounts.NOUNS[1], first + mounts.NOUNS[2]]  # 毛色＋馬／駒（5.6；字待 joy 潤，不寫死）
    real = real_content()
    assert not [n for n in names if naming.name_problem(n, real, None)]
    taken = {s.name for s in real.skills.values()} | {m.name for m in real.materials.values()} | {ch.name for ch in real.characters.values()}
    assert not set(names) & taken
    assert mounts.grade(_horse()) == f"{mounts.TIER_NAMES[1]}・下品"
    assert mounts.grade(_horse(tier=2, quality="中品")) == f"{mounts.TIER_NAMES[2]}・中品"
    assert mounts.name_of(_horse(name="青驄駒")) == "青驄駒"


def test_odds_text_rounds_half_up_and_says_under_one_tenth():
    assert [mounts.tenths(x) for x in (0.25, 0.15, 0.24, 0.04)] == [3, 2, 2, 0]  # .5 進位（round(2.5) 會給 2）
    assert mounts.odds_text(0.25) == "約 3 成" and mounts.odds_text(0.04) == "不到一成"
    # 百分比也是 .5 進位：f"{x:.0%}" 跟 round 一樣把 .5 捨到偶數（餓到底的駑馬省 12.5% 會寫成 12%、騎兵 2.5% 寫成 2%）
    assert [mounts.pct(x) for x in (0.125, 0.025, 0.225, 0.2, 0.43)] == ["13%", "3%", "23%", "20%", "43%"]


@pytest.mark.smoke
def test_old_save_from_equipment_batch_one_reads_on_foot_with_a_plain_pace(content, world):
    """裝備四欄 3.2、5.3：裝備一的舊存檔（沒有 mount、hunger_warned、picking_market，路上的 Journey 沒有 pace）讀得進來，
    沒騎馬、步調 1，已經排好的抵達時刻照舊。"""
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    game.state.player.journey = Journey(mode="walk", path=["lake"], arrive_at=[180.0])
    raw = game.state.model_dump()
    for key in ("mount", "hunger_warned", "picking_market"):
        raw["player"].pop(key)
    raw["player"]["journey"].pop("pace")
    loaded = GameState.model_validate(raw).player
    assert loaded.mount is None and loaded.hunger_warned is False and loaded.picking_market is False
    assert loaded.journey.pace == 1.0 and loaded.journey.arrive_at == [180.0]


def test_a_new_season_starts_on_foot(content, world):
    game = _game(content, world, horse=_horse())
    p = game.state.player
    p.rack, p.hunger_warned = [_horse(hid="騎:2", name="青驄馬")], True
    next_season(content, world, game)
    p = game.state.player
    assert p.mount is None and p.rack == [] and not p.hunger_warned and not p.picking_market  # 新欄位跟著新角色重來（2.4）


def test_a_mount_cannot_be_changed_on_the_road_but_can_in_seclusion(content, world):
    """設計 2.3：路上不能換坐騎（快慢出發時就算進抵達時刻，換了也不會變快），閉關中照樣能換；換上不花體力。"""
    game = _game(content, world, horse=_horse())
    p = game.state.player
    p.rack = [_horse(hid="騎:2", name="青驄駒", tier=2)]
    game.choose("move:lake")
    assert p.journey is not None
    assert game.wield_weapon("騎:2") == [equipment.ROAD_LOCKED.format(label="坐騎")] and p.mount.id == "騎:1"
    p.journey = None  # 到了（省掉等）
    p.busy_until = game.state.world.time + 3600.0  # 閉關中
    stamina = p.stamina
    assert game.wield_weapon("騎:2") == [equipment.WIELDED.format(name="青驄駒")] and p.mount.id == "騎:2" and p.stamina == stamina
    assert [m.id for m in p.rack] == ["騎:1"]


# ── Task 2：移動的時間與體力 ──

def test_pure_travel_math_takes_the_pace_and_the_saving(content):
    """設計 5.2（企劃者選丙）：先照原本的四捨五入（至少 1），再乘（1－腳力）四捨五入、至少 1；.5 一律進位。5.3：時間乘步調。"""
    assert atlas.travel_seconds(9, "walk", pace=0.7) == pytest.approx(378.0)
    assert atlas.travel_seconds(9, "hurry", pace=0.7) == pytest.approx(189.0) and atlas.travel_seconds(9, "dash", pace=0.7) == 0
    assert atlas.mode_when(9, "walk", pace=0.7) == "約 6 分鐘" and atlas.mode_when(9, "dash", pace=0.7) == "立刻到"
    assert atlas.ride_stamina(6, 0.25) == 5  # 4.5 進位（Python 的 round 會給 4）
    assert atlas.ride_stamina(8, 0.1875) == 7  # 6.5 進位
    assert atlas.ride_stamina(1, 0.6) == 1 and atlas.ride_stamina(0, 0.6) == 0  # 至少 1 點；步行本來就不花
    assert [atlas.foot_stamina(content, 3.0, m) for m in ("walk", "hurry", "dash")] == [0, 3, 6]
    assert [atlas.travel_stamina(content, 3.0, m, saving=0.25) for m in ("walk", "hurry", "dash")] == [0, 2, 5]
    assert atlas.mode_text(content, 3.0, "hurry", pace=0.775, saving=0.1875) == "趕路約 1 分鐘・體力 2"
    assert atlas.arrival_times(10.0, [3.0, 4.5], "walk", pace=0.7) == pytest.approx([136.0, 325.0])


def test_half_up_survives_the_float_products_the_tables_reach():
    """設計 5.2「.5 一律進位」：表裡的數字相乘會落在浮點的 .5 邊界上，差一點點就被 floor(x＋0.5) 漏掉進位——
    30×(1−0.55)＝13.499999999999998（名駒省 55% 的 30 點）、0.30×0.75 乘 100＝22.499999999999996（餓了一半的駑馬脫身）。
    half_up 多補一個遠小於任何有意義差距的量（1e-9）。"""
    assert math.floor(30 * (1 - 0.55) + 0.5) == 13 and mounts.half_up(30 * (1 - 0.55)) == 14  # 為什麼不能單用 floor(x＋0.5)
    assert [mounts.half_up(x) for x in (4.5, 0.5, 4.4999, 4.6, 0.0, 13.499999999999998)] == [5, 1, 4, 5, 0, 14]
    assert atlas.ride_stamina(30, 0.55) == 14 and atlas.ride_stamina(6, 0.25) == 5
    assert atlas.ride_stamina(1, 0.9) == 1  # 至少 1 點照舊
    assert mounts.pct(0.30 * 0.75) == "23%" and mounts.pct(0.525) == "53%" and mounts.pct(0.125) == "13%"
    # 守方駑馬吃飽（省 25%）、攻方良駒餓到底（省 20%）：腳力差 4.999999999999999%，要寫「約 1 成」而不是「不到一成」
    gap = 0.25 - 0.40 * 0.5
    assert gap < 0.05 and mounts.tenths(gap) == 1 and mounts.odds_text(gap) == "約 1 成"
    assert mounts.tenths(0.04) == 0 and mounts.odds_text(0.04) == "不到一成"  # 真的不到半成的照舊


def test_foot_stamina_keeps_the_old_rounding(content):
    """foot_stamina 就是原本的 travel_stamina：floor(x＋0.5)、至少 1 點，老數字不能因為坐騎這一批挪動（trunk 的算法不補 1e-9）。"""
    assert [atlas.foot_stamina(content, m, "hurry") for m in (0.2, 0.5, 1.5, 2.5, 9.0)] == [1, 1, 2, 3, 9]
    assert [atlas.foot_stamina(content, m, "dash") for m in (0.2, 0.25, 4.5)] == [1, 1, 9]


def test_the_pure_functions_have_no_default_pace_or_saving(content):
    """設計 5.3：漏改的呼叫處直接丟 TypeError，不會悄悄照沒騎馬算。"""
    for call in (lambda: atlas.travel_seconds(9, "walk"), lambda: atlas.travel_stamina(content, 9, "dash"),
                 lambda: atlas.mode_when(9, "walk"), lambda: atlas.mode_text(content, 9, "walk", pace=1.0),
                 lambda: atlas.arrival_times(0.0, [9], "walk")):
        with pytest.raises(TypeError):
            call()


@pytest.mark.parametrize("mode, cost, when", [("walk", 0, "約 2 分鐘"), ("dash", 5, "立刻到")])
def test_every_place_that_states_the_stamina_matches_what_departing_takes(content, world, mode, cost, when):
    """Review Focus 1：騎著餓了一半的駑馬（飽足 50：省 18.75%、步調 0.775）往湖邊（3 分鐘路程），選單「前往」、輿圖三顆鈕、
    地點詳情、輿圖的拒絕話寫的體力與時間，都等於出發時實際扣的（設計 5.3 的呼叫處表，一處都不能漏乘）。"""
    game = _game(content, world, horse=_horse(edge=50))
    p = game.state.player
    game.set_move_mode(mode)
    oid = "move:lake" if mode == "walk" else f"move:lake:{mode}"
    word, price = atlas.MODES[mode], f"・體力 {cost}" if cost else ""
    assert _ids(game)[oid].label == f"前往 湖邊（{word}{when}{price}）"
    [button] = [b for b in game.travel_options("lake") if b.mode == mode]
    assert button.label == f"{word}（{when}{price}）"
    assert f"{word}{when}{price}" in game.place_detail("lake")
    if cost:
        p.stamina = cost - 0.5
        assert game.travel_refusal("lake", mode) == f"體力不足，{word}要 {cost} 體力"
        assert _ids(game)[oid].label == f"前往 湖邊（{word}・體力不足，要 {cost}）"
        p.stamina = 100.0
    start = game.state.world.time
    game.choose(oid)
    assert p.stamina == 100.0 - cost
    if mode != "dash":
        assert p.journey.pace == pytest.approx(0.775)
        assert p.journey.arrive_at[0] - start == pytest.approx(3.0 * 60 * atlas.TIME_SHARE[mode] * 0.775)
        assert game.state.journal[0].tag == f"{word}{when}"  # 紀錄的標籤用同一個步調


@pytest.mark.parametrize("mode, cost, when", [("walk", 0, "約 1 分鐘"), ("dash", 2, "立刻到")])
def test_turning_back_on_the_road_states_and_takes_the_same_stamina(content, world, mode, cost, when):
    """走到一半折返（設計 5.3：兩種走法各驗一次；趕路 2026-10-12 拿掉）：回程照路上的位置算（road_spot 讀出發時的步調），鈕上寫的時間與體力就是扣的、
    排好的。回程 1.5 分鐘：趕路原本 2 點、疾行 3 點，騎餓了一半的駑馬（省 18.75%）2×0.8125＝1.625 → 2、3×0.8125＝2.4375 → 2；
    回程的步調照折返那一刻的坐騎（飽足還是 50：0.775）。road_spot 要是用步調 1 反推，會算成走了六成一（回程 1.8375 分鐘）：
    疾行 4 點 → 3，步行、趕路排的抵達時刻也多兩成多。"""
    game = _game(content, world, horse=_horse(edge=50))
    p = game.state.player
    start = game.state.world.time
    game.choose("move:lake")  # 步行：步調 0.775，139.5 秒到
    assert p.journey.arrive_at[0] - start == pytest.approx(139.5)
    game.advance(139.5 / 2)  # 走到一半
    game.set_move_mode(mode)
    oid = "road:back" if mode == "walk" else f"road:back:{mode}"
    word, price = atlas.MODES[mode], f"・體力 {cost}" if cost else ""
    assert _ids(game)[oid].label == f"折返 小鎮（{word}{when}{price}）"
    before, turn = p.stamina, game.state.world.time
    game.choose(oid)
    assert before - p.stamina == cost
    if mode == "dash":
        assert p.location == "town" and p.journey is None
    else:
        assert p.journey.pace == pytest.approx(0.775)
        assert p.journey.arrive_at[-1] - turn == pytest.approx(1.5 * 60 * atlas.TIME_SHARE[mode] * 0.775)


def test_turning_on_the_road_replans_with_the_horse_as_it_is_then(content, world):
    """設計 5.3：在路上改道、折返照改道那一刻的坐騎與飽足重算一趟——已經走掉的半段照出發時的步調算，新的這一趟用新的步調與腳力。
    吃飽出發（步調 0.7）走到一半，路上餓到底（步調 0.85、腳力 0.125）：回程 1.5 分鐘疾行原本 3 點，照現在的腳力 3×0.875＝2.625 → 3
    （照出發時吃飽的算會是 2）；改步行回去，Journey.pace 換成 0.85。"""
    game = _game(content, world, horse=_horse())
    p = game.state.player
    game.choose("move:lake")  # 126 秒到
    game.advance(63.0)  # 走到一半（照出發時的步調 0.7）
    p.mount.edge = 0
    [dash] = [b for b in game.travel_options("town") if b.mode == "dash"]
    assert dash.label == "疾行（立刻到・體力 3）"
    before, turn = p.stamina, game.state.world.time
    game.travel("town", "walk")
    assert p.stamina == before and p.journey.pace == pytest.approx(0.85)
    assert p.journey.arrive_at[-1] - turn == pytest.approx(1.5 * 60 * 0.85)


def test_the_spot_on_the_road_keeps_the_pace_the_trip_was_planned_with(content, world):
    """設計 5.3：路上的位置照出發時快照的步調反推；路上餓了不回頭改寫已經排好的抵達時刻與位置。"""
    game = _game(content, world, horse=_horse())  # 吃飽：步調 0.7
    start = game.state.world.time
    game.choose("move:lake")
    j = game.state.player.journey
    assert j.arrive_at[0] - start == pytest.approx(126.0)
    game.advance(63.0)
    assert atlas.road_spot(game.state, content).done == pytest.approx(0.5)
    game.state.player.mount.edge = 0  # 路上餓了：現在的步調是 0.85
    assert atlas.road_spot(game.state, content).done == pytest.approx(0.5) and j.arrive_at[0] - start == pytest.approx(126.0)


def test_the_map_routes_layer_counts_walking_minutes_on_horseback(content, world):
    """設計 5.3 的表漏列的：輿圖路線層的「N 分鐘」也乘步調，跟詳情欄、「前往」寫的步行時間一樣。"""
    from tianxia.mapview import render_map
    game = _game(content, world, horse=_horse())  # 吃飽的駑馬：步行快三成
    game.state.world.flags.add("cave_open")
    svg = render_map(game.state, content, "routes", selected="cave")
    assert ">2 分鐘<" in svg and ">5 分鐘<" in svg  # 湖邊 3×0.7＝2.1、寶洞 7.5×0.7＝5.25（沒騎馬時是 3、8）


# ── Task 3：飽足、餵、結伴同行 ──

def test_each_new_leg_makes_the_horse_hungrier(content, world):
    """設計 5.4：每抵達新的一站扣：步行 −5，疾行 −10；剛出發就折返（回到原地、不換段）不扣；坐騎關著不扣。"""
    game = _game(content, world, horse=_horse())
    p = game.state.player
    walk_to(game, "lake")
    assert p.mount.edge == 95
    game.set_move_mode("dash")
    game.choose("move:town:dash")
    assert p.location == "town" and p.mount.edge == 85
    game.set_move_mode("walk")
    game.choose("move:lake")
    game.choose("road:back")  # 剛出發就折返：立刻回原地
    assert p.location == "town" and p.journey is None and p.mount.edge == 85
    content.config.mounts.enabled = False
    game.set_move_mode("walk")
    walk_to(game, "lake")
    assert p.mount.edge == 85


def test_a_hungry_horse_warns_once_and_feeding_fills_it_and_resets_the_warning(content, world):
    game = _game(content, world, horse=_horse(edge=33))
    p = game.state.player
    p.materials = {"gang_1": 2}
    warn = mounts.HUNGRY_WARNING.format(name="棗騮馬")
    assert warn in walk_to(game, "lake") and p.mount.edge == 28 and p.hunger_warned
    assert warn not in walk_to(game, "town")  # 只提醒一次
    assert game.feed_mount() == [mounts.FED.format(material="精鐵砂", name="棗騮馬")]
    assert p.mount.edge == 100 and not p.hunger_warned and p.materials == {"gang_1": 1}
    from tianxia import journal
    assert game.state.journal[0].title == journal.PRACTICE  # 修練頁的「餵」寫一則修練紀錄
    assert game.feed_mount() == [f"（{mounts.NOT_HUNGRY}。）"] and p.materials == {"gang_1": 1}


def test_feeding_needs_a_mount_a_tier_one_material_and_free_hands(content, world):
    """設計 5.4：一個一階素材（屬性不限），閒著時哪裡都能餵——不在路上、不在閉關。"""
    game = _game(content, world)
    p = game.state.player
    assert game.feed_mount() == [f"（{mounts.NO_MOUNT}。）"]
    p.mount = _horse(edge=40)
    assert game.feed_mount() == [f"（{equipment.NO_REPAIR_MATERIAL}。）"]
    p.materials = {"gang_2": 3}  # 二階的不算
    assert mounts.feed_note(game.state, content) == equipment.NO_REPAIR_MATERIAL
    p.materials["kuai_1"] = 1
    assert mounts.feed_note(game.state, content) == "驚羽×1"
    p.busy_until = game.state.world.time + 3600.0
    assert game.feed_mount() == [f"（{mounts.FEED_SECLUDED}。）"]
    p.busy_until = None
    game.choose("move:lake")
    assert game.feed_mount() == [f"（{mounts.FEED_ON_ROAD}。）"]
    assert p.mount.edge == 40 and p.materials == {"gang_2": 3, "kuai_1": 1}


NOW = 1_000_000.0


def _traveller(content, name, horse=None, stamina=100.0):
    """結伴同行的一方（同 tests/test_social.py 的 _player）：在小鎮、存回資料庫。"""
    _on(content)
    game = Game.new(content, name, rng=random.Random(0))
    game.client = None
    game.sync(NOW)
    p = game.state.player
    p.location, p.stamina, p.mount = "town", stamina, horse
    CharacterStore(game.world.db).save(game.state)
    return game


def _follow(game, leader):
    game.state.player.tagalong = Tagalong(leader=leader, since=NOW)
    CharacterStore(game.world.db).save(game.state)


def test_travelling_together_follows_the_leaders_horse_and_each_pays_with_his_own(content):
    """設計 5.8（Review Focus 1）：整隊照帶頭的人的坐騎走（照抄的這一趟連步調一起抄，抵達時刻一樣）：帶頭的騎吃飽的駑馬步行，
    跟著的沒馬也照步調 0.7 走；步行不花體力（體力各付各的見下一條的疾行）。"""
    a = _traveller(content, "甲", horse=_horse())
    b = _traveller(content, "乙")
    _follow(b, "甲")
    assert "乙跟著你。" in a.choose("move:lake")
    stored = CharacterStore(a.world.db).load("乙").player
    assert a.state.player.stamina == 100.0 and stored.stamina == 100.0
    assert stored.journey == a.state.player.journey and stored.journey.pace == pytest.approx(0.7)


def test_a_follower_with_his_own_horse_keeps_up_where_on_foot_he_could_not(content):
    """跟著的人照自己的坐騎算：帶頭的沒馬疾行到湖邊 6 點，跟著的騎吃飽的駑馬只要 5 點，手上剛好 5 點跟得上；
    疾行一段只扣有騎馬的人的飽足。"""
    a = _traveller(content, "甲")
    b = _traveller(content, "乙", horse=_horse(), stamina=5.0)
    _follow(b, "甲")
    a.set_move_mode("dash")
    assert "乙跟著你。" in a.choose("move:lake:dash")
    stored = CharacterStore(a.world.db).load("乙").player
    assert stored.stamina == 0.0 and stored.location == "lake" and stored.mount.edge == 90
    assert a.state.player.stamina == 94.0 and a.state.player.mount is None


# ── Task 4：馬市 ──

def _market_game(content, world, **kw):
    """小鎮臨時加上「馬市」標籤（測試內容的 locations.json 不動）：那一匹的毛色照 town 的 sha256 挑（TOWN_HORSE）。"""
    if mounts.MARKET_TAG not in content.locations["town"].tags:
        content.locations["town"].tags.append(mounts.MARKET_TAG)
    return _game(content, world, **kw)


TOWN_HORSE = mounts.horse_name(mounts.coat_for("town"), 1)  # 測試內容小鎮的馬市賣的那一匹（毛色字表待 joy 潤，不寫死）


def test_the_market_is_where_the_tag_is_and_only_when_mounts_are_on(content, world):
    game = _game(content, world)
    assert "act:market" not in _ids(game)  # 小鎮沒有馬市標籤
    content.locations["town"].tags.append(mounts.MARKET_TAG)
    assert _ids(game)["act:market"].label == mounts.MARKET
    content.config.mounts.enabled = False
    assert "act:market" not in _ids(game)


def test_four_markets_in_the_real_content_each_sell_their_own_coat():
    c = real_content()
    markets = sorted(loc.id for loc in c.locations.values() if mounts.MARKET_TAG in loc.tags)
    assert markets == sorted(["zhuo_county", "runan_market", "wan_city", "xiaquyang"])
    assert len({mounts.coat_for(m) for m in markets}) == 4  # 四處不一樣（5.6；只取 sha256 第一個位元組時涿郡、宛城會撞色）
    assert all(equipment.TOWN_TAG in c.locations[m].tags for m in markets)


def test_buying_a_nag_wears_it_and_the_second_goes_to_the_rack(content, world):
    game = _market_game(content, world, silver=250)
    p = game.state.player
    game.choose("act:market")
    opts = _ids(game)
    assert list(opts) == [mounts.BUY, mounts.BACK]
    label = opts[mounts.BUY].label  # 整句待 joy 潤：只鎖名字、階品、省幾成、價錢
    assert f"【{TOWN_HORSE}】" in label and mounts.grade(mounts.shop_item(game.state, content)) in label
    assert "25%" in label and "100 兩" in label
    game.choose(mounts.BUY)
    assert (p.mount.id, p.mount.name, p.mount.tier, p.mount.quality, p.mount.edge) == ("騎:1", TOWN_HORSE, 1, "下品", 100)
    assert p.stats["silver"] == 150 and p.picking_market  # 做完選單還開著
    game.choose(mounts.BUY)
    assert [m.id for m in p.rack] == ["騎:2"] and p.stats["silver"] == 50
    opts = _ids(game)
    assert list(opts) == [mounts.BUY, mounts.FEED, f"{mounts.WIELD}騎:2", mounts.BACK]
    assert not opts[mounts.BUY].enabled and "還差 50 兩" in opts[mounts.BUY].label
    assert not opts[mounts.FEED].enabled and mounts.NOT_HUNGRY in opts[mounts.FEED].label
    content.config.weapons.rack_cap = 1
    p.stats["silver"] = 500
    assert equipment.RACK_FULL in _ids(game)[mounts.BUY].label  # 身上有馬、裝備庫（四欄合算）也滿了


def test_feeding_and_wielding_at_the_market(content, world):
    game = _market_game(content, world, horse=_horse(edge=40))
    p = game.state.player
    p.materials = {"kuai_1": 1, "gang_1": 2}
    p.rack = [_horse(hid="騎:2", name="青驄駒", tier=2)]
    game.choose("act:market")
    feed = _ids(game)[mounts.FEED]  # 整句待 joy 潤：只鎖名字、飽足度、用哪一種素材
    assert feed.enabled and "【棗騮馬】" in feed.label and f"{mounts.WEAR_WORD} 40" in feed.label and "精鐵砂×1" in feed.label
    game.choose(mounts.FEED)
    assert p.mount.edge == 100 and p.materials == {"kuai_1": 1, "gang_1": 1}
    game.choose(f"{mounts.WIELD}騎:2")
    assert p.mount.id == "騎:2" and [m.id for m in p.rack] == ["騎:1"]
    assert _ids(game)[mounts.BACK].label == mounts.LEAVE
    assert mounts.LEFT in game.choose(mounts.BACK) and not p.picking_market


@pytest.mark.parametrize("exit_by", ["back", "walk_away", "depart", "reconcile"])
def test_every_way_out_of_the_market_closes_it(content, world, exit_by):
    """Review Focus 3：凡是收起第二層選單的地方都收馬市（同鐵匠鋪）：離開、同步時人不在馬市、出發、存檔修補。"""
    game = _market_game(content, world)
    p = game.state.player
    game.choose("act:market")
    assert p.picking_market
    if exit_by == "back":
        game.choose(mounts.BACK)
    elif exit_by == "walk_away":
        p.location = "lake"
        game.sync(1.0)
    elif exit_by == "depart":
        game.travel_refusal = lambda *a, **k: None  # 繞過「馬市還開著」的擋，直接測 _depart 的防線（同 test_weapons）
        game.travel("lake", "dash")
    else:
        content.config.mounts.enabled = False
        game._drop_stale_references()
    assert not p.picking_market


def test_an_open_market_blocks_travel_and_seclusion(content, world):
    game = _market_game(content, world)
    assert mounts.ENTERED in game.choose("act:market")
    assert game.travel_refusal("lake") == mounts.TRAVEL_BLOCKED
    assert game.seclude(1) == ["你現在無法閉關。"] and game.state.player.busy_until is None  # 閉關的拒絕話是舊的那一句（_idle）
    game.choose(mounts.BACK)
    assert game.travel_refusal("lake") is None


def test_the_market_tag_is_not_written_as_terrain(content):
    """有所感的標題括號寫的是地形（河畔、城鎮……）；「馬市」是設施，不寫。"""
    from types import SimpleNamespace

    from tianxia import sensing
    loc = content.locations["town"]
    loc.tags.append(mounts.MARKET_TAG)
    assert sensing.place_tags(SimpleNamespace(prologue=False), loc) == "（城鎮）"


# 機器人的排除與給分跟 act:market 一起做（CLAUDE.md「新增永遠按得下去的選項要一併改 bot.py::pick()」）：不然伺服器假人進了馬市就卡住

def test_wanted_wields_a_faster_horse_then_buys_then_feeds(content, world):
    game = _market_game(content, world, silver=130)
    s, p = game.state, game.state.player
    assert mounts.wanted(s, content, reserve=30) == mounts.BUY  # 100＋保留 30
    assert mounts.wanted(s, content, reserve=31) is None
    p.mount, p.rack = _horse(edge=20), [_horse(hid="騎:2", tier=2, edge=10)]  # 良駒餓到底也比駑馬快（比的是吃飽的腳力）
    assert mounts.wanted(s, content) == f"{mounts.WIELD}騎:2"
    p.rack = []
    p.materials = {"gang_1": 1}
    assert mounts.wanted(s, content) == mounts.FEED  # 身上有馬就不買第二匹；飽足低於 50 就餵
    p.mount.edge = 50
    assert mounts.wanted(s, content) is None
    p.location = "lake"
    assert mounts.wanted(s, content) is None  # 不在馬市


def test_pick_never_chooses_the_market_door(content, world):
    from tianxia import bot
    game = _market_game(content, world)
    options = [o for o in game.options(odds=False) if o.enabled]
    assert "act:market" in {o.id for o in options}
    for seed in range(50):
        assert bot.pick(game, options, random.Random(seed)) != "act:market"


def test_a_server_bot_enters_the_market_only_with_something_to_do(content, world):
    """Review Focus 3：沒事可做不進門；進了門只有「離開」有分（不然 bot_policy.pick 會從所有 None 以外的隨機挑、或卡在門裡）。"""
    from tianxia import bot_policy
    from tianxia.state import BotProfile
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    game = _market_game(content, world, silver=50)
    assert bot_policy.score(game, _ids(game)["act:market"], profile) is None
    game.choose("act:market")
    assert {o.id: bot_policy.score(game, o, profile) for o in game.options(odds=False) if o.enabled} == {mounts.BACK: 0.0}
    game.choose(mounts.BACK)
    game.state.player.stats["silver"] = 200
    assert bot_policy.score(game, _ids(game)["act:market"], profile) == bot_policy.MARKET_SCORE
    game.choose("act:market")
    scored = {o.id: bot_policy.score(game, o, profile) for o in game.options(odds=False) if o.enabled}
    assert scored == {mounts.BUY: bot_policy.MARKET_SCORE, mounts.BACK: 0.0}


def test_a_server_bot_in_the_market_never_gets_stuck_and_usually_buys(content, world):
    from tianxia import bot_policy
    from tianxia.state import BotProfile
    profile = BotProfile(personality="普通", seed=1, faction=None, season_number=1)
    bought = 0
    for seed in range(10):
        game = _market_game(content, world)
        rng = random.Random(seed)
        game.choose("act:market")
        for _ in range(6):
            if not game.state.player.picking_market:
                break
            bot_policy.take_turn(game, profile, rng)
        assert not game.state.player.picking_market
        bought += game.state.player.mount is not None
    assert bought >= 5


# ── Task 5：修練頁、角色卡 ──

def test_gear_rows_have_a_mount_slot_with_feed_on_the_worn_horse(content, world):
    from tianxia import skillview
    game = _game(content, world, horse=_horse(edge=60))
    p = game.state.player
    p.materials = {"gang_1": 1}
    p.rack = [_horse(hid="騎:2", name="青驄駒", tier=2, quality="中品")]
    gear = skillview.gear_rows(game.state, content, world)
    [slot] = gear["slots"]  # 測試內容武器、防具關著：只有坐騎那一段
    assert (slot["slot"], slot["label"], slot["empty"], slot["note"]) == ("mount", "坐騎", mounts.EMPTY, mounts.RACK_NOTE)
    worn = slot["worn"]
    # 設計 2.5：路上快、騎兵、脫身寫在修練頁這一列。飽足 60（係數 0.8）：省 25%→20%、快 30%→24%、騎兵 5%→4%、脫身 30%→24%
    assert (worn["grade"], worn["wear_word"], worn["edge"]) == (mounts.grade(p.mount), mounts.WEAR_WORD, 60)
    assert (worn["save"], worn["speed"], worn["cavalry"], worn["escape"]) == ("20%", "24%", "4%", "24%")
    assert worn["feed"] is True and worn["feed_note"] == "精鐵砂×1" and worn["wield_ok"] is True
    [spare] = slot["rack"]  # 良駒中品吃飽：品質只加省體力、路上快（43%、48%），騎兵、脫身照階（10%、50%）
    assert (spare["id"], spare["save"], spare["speed"], spare["cavalry"], spare["escape"], spare["feed"]) == ("騎:2", "43%", "48%", "10%", "50%", False)
    assert (spare["wield_ok"], spare["wield_note"]) == (True, "")
    assert gear["used"] == 1
    content.config.mounts.enabled = False
    assert skillview.gear_rows(game.state, content, world)["slots"] == []


def test_a_rack_horse_cannot_be_wielded_on_the_road(content, world):
    """設計 2.3：路上不能換坐騎——修練頁裝備庫那一列的「換上」在路上灰掉、寫原因，不必按了才知道（按下去 equipment.wield 也擋）。"""
    from tianxia import skillview
    game = _game(content, world, horse=_horse())
    game.state.player.rack = [_horse(hid="騎:2", name="青驄駒", tier=2)]
    game.choose("move:lake")
    [spare] = skillview.gear_rows(game.state, content, world)["slots"][0]["rack"]
    assert (spare["wield_ok"], spare["wield_note"]) == (False, mounts.ON_ROAD)


def test_player_card_has_the_mount_line(content, world):
    from tianxia import skillview
    game = _game(content, world)
    assert "坐騎" not in skillview.member_card(game.state, content, world, "player")
    game.state.player.mount = _horse(edge=60)
    lines = skillview.member_card(game.state, content, world, "player").splitlines()
    line = mounts.card_line(game.state, content)  # 整行待 joy 潤：只鎖名字、飽足度、省幾成
    assert "【棗騮馬】" in line and f"{mounts.WEAR_WORD} 60" in line and "20%" in line  # 設計 2.5：25%×飽足係數 0.8
    assert line in lines and lines.index(line) > next(i for i, x in enumerate(lines) if x.startswith("武學"))


def test_the_practice_page_feed_action_feeds_the_horse(content, world):
    import server
    game = _game(content, world, horse=_horse(edge=40))
    game.state.player.materials = {"gang_1": 1}
    assert server.menxia_view(game)["gear"]["slots"][0]["worn"]["feed"] is True
    server.MENXIA_ACTIONS["feed"](game, {})
    assert game.state.player.mount.edge == 100 and server.menxia_view(game)["gear"]["slots"][0]["worn"]["feed"] is False


# ── Task 6：決戰騎兵 ──

def test_cavalry_multiplies_charge_and_raid_but_not_hold_and_stacks_with_the_role():
    """設計 5.9：強攻、奇襲 ×（1＋騎兵），固守不加；跟職位疊乘。沒騎馬（預設 0）數字一個都不變。"""
    from tianxia import battle_instance
    from tianxia.models import BattleTuning
    t = BattleTuning()
    plain = battle_instance.move_scores(t, 100.0, None, None)
    assert battle_instance.move_scores(t, 100.0, None, None, cavalry=0.0) == plain
    rode = battle_instance.move_scores(t, 100.0, None, None, cavalry=0.1)
    base = battle_instance.strength(t, 100.0) * t.affinity_base / 100
    assert rode["強攻"] == round(base * 1.1, 1) and rode["奇襲"] == round(base * 1.1, 1) and rode["固守"] == plain["固守"]
    vanguard = battle_instance.move_scores(t, 100.0, None, None, role="str", cavalry=0.1)  # 先鋒：強攻另 +15%
    assert vanguard["強攻"] == round(base * (1 + t.role_move_bonus) * 1.1, 1)


def test_riding_into_a_showdown_snapshots_the_horse_and_shows_it(content, game):
    """設計 5.9：份量與騎兵在加入時快照（同職位），之後馬餓了不影響這一場；集結、開打後的畫面與戰報各寫一句。"""
    from conftest import at
    from test_engine import _fighter, _three_round_showdown
    _on(content)
    definition = _three_round_showdown(content)
    p = game.state.player
    p.faction, p.mount = "guan", _horse()  # 吃飽的駑馬：騎兵 +5%
    foe = _fighter(content, game, "乙", "huang")
    game.world.start_battle(definition, now=0.0)
    ride = mounts.CAVALRY_LINE.format(name="棗騮馬", pct="5%")  # 待 joy 潤的句子從常數組，只鎖馬名與幾成
    with at(game, 0.0), at(foe, 0.0):
        game.choose("battle:join:guan")
        foe.choose("battle:join:huang")
        assert ride + "。集結結束就開打" in game.scene_text()  # 接在職位後面、「集結結束就開打」（舊句）前面
    me = game.world.get_battle().participants[p.name]
    assert me.mount == "棗騮馬" and me.cavalry == pytest.approx(0.05) and me.scores == game._battle_scores()
    plain = game._battle_scores(mounted=False)
    assert me.scores["強攻"] > plain["強攻"] and me.scores["奇襲"] > plain["奇襲"] and me.scores["固守"] == plain["固守"]
    them = game.world.get_battle().participants["乙"]
    assert (them.mount, them.cavalry) == ("", 0.0)  # 沒騎馬
    p.mount.edge = 0  # 加入之後馬餓了：這一場照加入時的快照
    start = definition.muster_seconds + 1
    with at(game, start):
        assert ride in game.scene_text()  # 馬餓了也照加入時的 5% 寫
    for i in range(3):
        with at(game, start + i), at(foe, start + i):
            game.choose("battle:act:guan_hold")
            foe.choose("battle:act:huang_hold")
    game.sync(start + 10)  # 收場那一下是乙出的手：自己的那一則同步時補
    assert mounts.CAVALRY_REPORT.format(name="棗騮馬") in game.state.journal[0].lines
    assert mounts.CAVALRY_REPORT.format(name="棗騮馬") in game.state.battles[0].notes  # 戰報也寫（同一份 lines）


def test_a_fighter_with_no_snapshot_gets_his_horse_backfilled(content, game):
    """上線前就在場上、沒有份量快照的人：自己同步時連馬一起補（_backfill_battle_scores）。"""
    from test_engine import _open_three_move_battle, _strip_scores
    _on(content)
    game.state.player.mount = _horse(tier=2)
    _open_three_move_battle(game)
    name = game.state.player.name
    game.world.mutate_battle(lambda b: setattr(b.participants[name], "mount", ""))
    game.world.mutate_battle(lambda b: setattr(b.participants[name], "cavalry", 0.0))
    _strip_scores(game)
    game.sync(1.0)
    after = game.world.get_battle().participants[name]
    assert after.scores == game._battle_scores() and (after.mount, after.cavalry) == ("棗騮馬", pytest.approx(0.10))


def test_the_enlist_and_latecomer_paths_snapshot_the_horse_like_joining(content, game):
    """五條加入的路：join（上面）、集結時臨時投效、開打後臨時投效、晚到（join_late）都快照馬，跟份量同一刻算。"""
    from conftest import at
    from test_engine import _fighter, _install_battle_def, _install_factions
    _on(content)
    _install_factions(content)
    definition = _install_battle_def(content)
    definition.rounds_per_act = 3
    game.state.player.mount = _horse(tier=3, name="名駒甲")  # 散人（沒陣營）集結時臨時投效：名駒騎兵 +15%
    game.world.start_battle(definition, now=0.0)
    late = _fighter(content, game, "丙", "guan")  # 官軍，晚到
    late.state.player.mount = _horse(tier=2, name="良駒乙", hid="騎:2")
    drifter = _fighter(content, game, "丁", None)  # 另一個散人，開打後臨時投效
    drifter.state.player.mount = _horse(tier=1, name="駑馬丙", hid="騎:3", edge=0)  # 餓到底：5%×0.5
    with at(game, 0.0):
        game.choose("battle:enlist:guan")
    me = game.world.get_battle().participants[game.state.player.name]
    assert (me.mount, me.cavalry) == ("名駒甲", pytest.approx(0.15)) and me.scores == game._battle_scores()
    start = definition.muster_seconds + 1
    with at(game, start):
        game._battle_status()  # 集結關閉，已經開打
    with at(late, start):
        late.choose("battle:join_late")
    with at(drifter, start):
        drifter.choose("battle:enlist:huang")
    parts = game.world.get_battle().participants
    assert (parts["丙"].mount, parts["丙"].cavalry) == ("良駒乙", pytest.approx(0.10)) and parts["丙"].scores == late._battle_scores()
    assert (parts["丁"].mount, parts["丁"].cavalry) == ("駑馬丙", pytest.approx(0.025)) and parts["丁"].scores == drifter._battle_scores()
    assert mounts.pct(parts["丁"].cavalry) == "3%"  # 2.5% 進位成 3%（half_up，不是捨到偶數的 2%）


def test_a_duel_takes_its_scores_without_the_horse(content, world):
    """頭目戰（Joy 的 duel.py）用同一份份量快照，但騎兵只在全服決戰（設計 2.1 的三個用途）。"""
    from test_duel import _boss
    from tianxia.models import FactionDef
    content.scenario.factions = [FactionDef(id="guan", name="官軍", join_at=["town"]), FactionDef(id="huang", name="黃巾", join_at=["town"])]
    content.duels = {"lake_boss": _boss()}
    game = _game(content, world, at="lake", horse=_horse(tier=3))
    rules.learn_skill(game.state, content, "fist")
    game._duel_start(content.duels["lake_boss"])
    assert game.state.player.duel.scores == game._battle_scores(mounted=False) != game._battle_scores()


# ── Task 7：截殺追逃、落敗策馬脫身 ──

def test_the_flee_chance_is_the_gap_in_legs_capped(content):
    """設計 5.10：脫身機率＝守方腳力－攻方腳力，夾在 0～40%。例：駑馬對沒馬 25%、良駒對駑馬 15%、名駒對沒馬封頂 40%、攻方比較快 0。"""
    from tianxia.state import new_game_state
    _on(content)
    a, b = new_game_state(content, "甲"), new_game_state(content, "乙")
    assert mounts.raid_flee(content, a, b) == 0.0
    b.player.mount = _horse()
    assert mounts.raid_flee(content, a, b) == pytest.approx(0.25)
    a.player.mount, b.player.mount = _horse(), _horse(tier=2)
    assert mounts.raid_flee(content, a, b) == pytest.approx(0.15)
    a.player.mount = _horse(tier=3)
    assert mounts.raid_flee(content, a, b) == 0.0  # 攻方的馬比較快：跑不掉
    a.player.mount, b.player.mount = None, _horse(tier=3, quality="上品")
    assert mounts.raid_flee(content, a, b) == pytest.approx(0.40)  # 60 對 0：封頂
    content.config.mounts.enabled = False
    assert mounts.raid_flee(content, a, b) == 0.0


RAID_NOW = 1000.0


@pytest.fixture
def riders(content, world):
    """截殺的兩個人（同 tests/test_raid.py 的 pair）：官軍甲、黃巾乙在湖邊，坐騎開著、都還沒騎馬。"""
    from conftest import install_season_one
    from tianxia.models import FactionDef
    install_season_one(content)
    _on(content)
    content.config.auto_open_first_season = True
    content.config.newbie_days = -1
    content.scenario.factions = [FactionDef(id="guan", name="官軍", join_at=["town"]), FactionDef(id="huang", name="黃巾", join_at=["lake"])]
    for name, faction in (("甲", "guan"), ("乙", "huang")):
        game = Game.new(content, name, rng=random.Random(0), world=world)
        game.client = None
        rules.learn_skill(game.state, content, "fist")
        p = game.state.player
        p.faction, p.location, p.stamina, p.stats["silver"] = faction, "lake", 100.0, 200
        game.sync(RAID_NOW)
        CharacterStore(world.db).save(game.state)
    return content, world


def _loaded(content, world, name):
    """伺服器那樣：重讀、同步。做完自己 _saved：只存角色，不替它存季（peer_act／server.act 都只存角色，FB-119）。"""
    game = Game(content, CharacterStore(world.db).load(name), random.Random(0), world)
    game.client = None
    game.sync(RAID_NOW)
    return game


def _saved(game):
    CharacterStore(game.world.db).save(game.state)


def _ride(world, name, horse):
    store = CharacterStore(world.db)
    state = store.load(name)
    state.player.mount = horse
    store.save(state)


def _no_fight(*args, **kwargs):
    raise AssertionError("跑掉了不該開打")


def _arm(world, name):
    """兩邊各穿一件兵器、一件防具（鋒利度、耐久度 100）：跑掉了要是誤走 _file_battle／_raid_spoils，看得出磨了。"""
    store = CharacterStore(world.db)
    state = store.load(name)
    state.player.weapon = Equipment(id="兵:1", slot="weapon", name="試刃", kind="拳腳", attribute="剛", tier=1, quality="下品")
    state.player.armor = Equipment(id="甲:2", slot="armor", name="軟皮甲", attribute="柔", tier=1, quality="下品")
    store.save(state)


def test_a_faster_horse_rides_away_from_a_raid_and_the_cooldowns_still_stick(riders, monkeypatch):
    """Review Focus 4：跑掉了不打（不走 resolve_encounter：截殺唯一用到 Game.rng 的地方）、誰都不失銀兩與氣血、沒有戰報、
    不磨兵器防具、不扣飽足、不動 Game.rng；發起的人照付體力；冷卻照記而且真的存回共用賽季（這裡不替它存季）；兩邊各一則江湖紀錄。"""
    content, world = riders
    content.config.weapons.enabled = content.config.armor.enabled = True  # 測試內容關著：打開才看得出磨了沒
    for name in ("甲", "乙"):
        _arm(world, name)
    _ride(world, "乙", _horse(tier=3, quality="上品"))
    monkeypatch.setattr(Game, "raid_flee_odds", lambda self, other: 1.0)  # 必定跑掉：不靠亂數
    monkeypatch.setattr(encounter, "resolve_encounter", _no_fight)
    game = _loaded(content, world, "甲")
    dice = game.rng.getstate()  # 玩家卡的 _peer／_kin 跟你共用這一份亂數
    msgs = game.peer_act("乙", "raid")
    _saved(game)
    assert game.rng.getstate() == dice  # 策馬脫身用自己的亂數（「截殺脫身|攻方|守方|世界秒」），Game.rng 一個都沒吃
    assert "體力 -10" in msgs and mounts.RAID_FLED.format(rival="乙", horse="棗騮馬") in msgs
    a, b = CharacterStore(world.db).load("甲"), CharacterStore(world.db).load("乙")
    assert a.player.stamina == 90.0 and a.player.stats["silver"] == 200 == b.player.stats["silver"]
    assert a.battles == [] and b.battles == [] and b.player.mount.edge == 100
    assert [(s.player.weapon.edge, s.player.armor.edge) for s in (a, b)] == [(100, 100), (100, 100)]
    assert (a.journal[0].title, a.journal[0].tag) == ("截殺・乙", mounts.RAID_FLED_TAG.format(him="他"))
    assert (b.journal[0].title, b.journal[0].tag) == ("遭甲截殺", mounts.RAID_ESCAPED_TAG)
    season = world.get_season()
    assert season.raids and season.raided  # 冷卻在共用賽季：_raid_fled 自己存了
    again = _loaded(content, world, "甲")
    assert again.raid_refusal(again._load_kin("乙")) == "你不久前才截殺過乙，過一陣子再說。"


def test_the_raid_button_says_how_likely_the_target_rides_away(riders):
    content, world = riders

    def button():
        game = _loaded(content, world, "甲")
        return next(b for b in game.peer_card("乙")["actions"] if b["action"] == "raid")

    plain = button()["confirm"]  # 誰都沒騎馬：原本那一句（Joy 的，不動）
    _ride(world, "乙", _horse())  # 守方吃飽的駑馬 25%、攻方沒馬
    assert button()["confirm"] == plain + mounts.RAID_FLEE_ASK.format(odds="約 3 成", him="他")  # 待 joy 潤的那一句從常數組，只鎖「約 3 成」
    game = _loaded(content, world, "甲")
    assert game.raid_flee_odds(game._load_kin("乙")) == pytest.approx(0.25)  # 確認句與 raid() 讀同一個數
    _ride(world, "甲", _horse(tier=2))  # 攻方良駒 40% 比較快：跑不掉
    assert button()["confirm"] == plain


@pytest.mark.parametrize("fled", [True, False], ids=["roll_under_the_odds_rides_away", "roll_over_the_odds_is_fought"])
def test_whether_he_rides_away_is_rolled_on_its_own_seed(riders, monkeypatch, fled):
    """設計 5.10：random.Random(f"截殺脫身|{攻方}|{守方}|{世界秒}")；擲中跑掉（沒有戰報），擲不中就照平常打（雙方各一份戰報）。
    真正的機率（駑馬 25%）離這顆種子擲出的數太遠，兩邊都會跑掉、抓不到「根本沒擲」；所以把機會釘在擲出的數的兩側各一點點，
    一個測試兩種結果：差一點點跑得掉、差一點點跑不掉。"""
    content, world = riders
    _ride(world, "乙", _horse())
    game = _loaded(content, world, "甲")
    roll = random.Random(f"截殺脫身|甲|乙|{game.state.world.time}").random()
    assert roll > 0.002  # 下面「差一點點」是 0.001：擲出的數要大過它，機會才是正的
    odds = roll + 0.001 if fled else roll - 0.001
    monkeypatch.setattr(Game, "raid_flee_odds", lambda self, other: odds)
    msgs = game.peer_act("乙", "raid")
    _saved(game)
    a, b = CharacterStore(world.db).load("甲"), CharacterStore(world.db).load("乙")
    flee_text = mounts.RAID_FLED.format(rival="乙", horse="棗騮馬")
    if fled:
        assert flee_text in msgs and a.battles == [] and b.battles == []
        assert (a.journal[0].tag, b.journal[0].tag) == (mounts.RAID_FLED_TAG.format(him="他"), mounts.RAID_ESCAPED_TAG)
    else:
        assert flee_text not in msgs and "體力 -10" in msgs
        assert len(a.battles) == 1 == len(b.battles) and a.battles[0].kind == b.battles[0].kind == "raid"
        assert {a.journal[0].tag, b.journal[0].tag}.isdisjoint({mounts.RAID_FLED_TAG.format(him="他"), mounts.RAID_ESCAPED_TAG})
        assert (a.journal[0].title, b.journal[0].title) == ("截殺・乙", "遭甲截殺")


def _hopeless(game, horse):
    """湖邊換成打不贏的翻江龍（同 test_engine.test_train_loss_costs_a_tenth_of_the_silver）、騎著 horse 走過去。"""
    _on(game.content)
    game.content.locations["lake"].enemies = ["boss"]
    game.state.player.mount = horse
    walk_to(game, "lake")


def test_a_lost_fight_on_horseback_may_keep_the_silver(game, monkeypatch):
    """設計 5.11：只保銀兩——氣血照扣、內傷照算、戰報結果照寫落敗，多一句「你策馬脫身，銀兩沒丟」；一成是 0 兩時不擲、不寫。"""
    from conftest import FixedRandom
    _hopeless(game, _horse(tier=3, quality="上品"))
    monkeypatch.setattr(mounts, "escape", lambda state, content: 1.0)  # 必定脫身
    p = game.state.player
    game.rng = FixedRandom(0.0)
    game.choose("act:train")
    record = game.state.battles[0]
    assert record.tier == "落敗" and record.silver == 0 and mounts.ESCAPED_LOSS in record.notes
    assert p.stats["silver"] == 50 and p.member.injury > 0
    p.stats["silver"] = 9  # 一成是 0 兩：沒有銀兩可保
    game.choose("act:train")
    assert mounts.ESCAPED_LOSS not in game.state.battles[0].notes and p.stats["silver"] == 9


def test_riding_away_from_a_loss_is_rolled_on_its_own_seed(game):
    """random.Random(f"脫身|{季數}|{名號}|{戰報流水號}")，不動 Game.rng（整季測試與量表的基準不位移）。"""
    from conftest import FixedRandom
    _hopeless(game, _horse(tier=3, quality="上品"))
    p = game.state.player
    game.rng = FixedRandom(0.0)
    game.choose("act:train")
    record = game.state.battles[0]
    seed = f"脫身|{game.world.get_season_number()}|{p.name}|{record.id}"
    kept = random.Random(seed).random() < mounts.escape(game.state, game.content)
    assert record.tier == "落敗" and (record.silver == 0) is kept and (p.stats["silver"] == 50) is kept


def test_the_loss_escape_seed_carries_the_season_number(game, monkeypatch):
    """QA（裝備二）：戰報流水號每季從 1 算起，種子少了季數，每一季第 N 場落敗的脫身結果都一樣。種子要帶季數：
    把真的拿去擲的那個種子攔下來看（換了季數，同一個名號、同一個流水號擲的是不同的種子）。"""
    from conftest import FixedRandom
    from tianxia import engine as engine_module
    seeds = []
    real = engine_module.random.Random

    def recording(seed=None):
        if isinstance(seed, str) and seed.startswith("脫身|"):
            seeds.append(seed)
        return real(seed)

    monkeypatch.setattr(engine_module.random, "Random", recording)
    _hopeless(game, _horse(tier=3, quality="上品"))
    monkeypatch.setattr(game.world, "get_season_number", lambda: 7)
    game.rng = FixedRandom(0.0)
    game.choose("act:train")
    record = game.state.battles[0]
    assert seeds == [f"脫身|7|{game.state.player.name}|{record.id}"]


def test_riding_away_from_a_loss_takes_nothing_from_the_games_dice(game):
    """自己的亂數那條，另外從 Game.rng 這一頭鎖：同一場必敗的遊歷，有沒有馬，吃掉 Game.rng 的次數一樣（上一支只在「自己的種子剛好跟
    Game.rng 給的不同結果」時才抓得到換錯亂數；這一支不論擲出什麼都抓得到，整季測試與量表的基準不位移）。"""
    from conftest import FixedRandom

    class Counting(FixedRandom):
        draws = 0

        def random(self):
            self.draws += 1
            return super().random()

    def draws_of_one_loss(horse):
        game.state.player.mount, game.state.player.stats["silver"] = horse, 50  # 銀兩一樣：一成是 5 兩，有東西可保
        game.rng = Counting(0.0)
        game.choose("act:train")
        assert game.state.battles[0].tier == "落敗"
        return game.rng.draws

    _hopeless(game, None)  # 先走過去：路上的亂數不算
    on_foot = draws_of_one_loss(None)
    assert draws_of_one_loss(_horse(tier=3, quality="上品")) == on_foot > 0


def test_the_hopeless_fight_warning_says_the_horse_may_save_the_silver(game, monkeypatch):
    """必敗的遊歷先問的那一句（FB-095）：騎著馬多寫能保住幾成，跟 _lose_silver 擲的是同一個數（mounts.escape）。"""
    from tianxia.engine import TRAIN_CONFIRM, TRAIN_CONFIRM_RIDING
    _hopeless(game, None)
    monkeypatch.setattr(Game, "odds", lambda self, squad_id: "必敗")

    def confirm():
        return next(o for o in game.options() if o.id == "act:train").confirm

    assert confirm() == TRAIN_CONFIRM  # 沒騎馬：照舊那一句
    game.state.player.mount = _horse(edge=60)  # 駑馬 30%×0.8＝24% → 約 2 成
    assert confirm() == TRAIN_CONFIRM_RIDING.format(odds="約 2 成")  # 待 joy 潤的那一句從常數組，只鎖「約 2 成」


# ── Task 8：整季機器人去馬市、餵馬；假人照顧自己時餵馬 ──

def test_visit_market_buys_a_nag_only_with_silver_to_spare_and_closes_the_menu(content, world):
    from tianxia import bot
    game = _market_game(content, world, silver=content.config.mounts.shop_price + bot.MOUNT_SILVER_RESERVE - 1)
    p = game.state.player
    bot.visit_market(game)
    assert p.mount is None and not p.picking_market
    p.stats["silver"] = 130
    bot.visit_market(game)
    assert p.mount is not None and p.stats["silver"] == 30 and not p.picking_market


def test_feed_mount_feeds_below_half_and_only_with_free_hands(content, world):
    from tianxia import bot
    game = _game(content, world, horse=_horse(edge=50))
    p = game.state.player
    p.materials = {"gang_1": 2}
    bot.feed_mount(game)
    assert p.mount.edge == 50  # 不到 50 才餵
    p.mount.edge = 49
    p.busy_until = game.state.world.time + 3600.0
    bot.feed_mount(game)
    assert p.mount.edge == 49  # 閉關中不餵
    p.busy_until = None
    bot.feed_mount(game)
    assert p.mount.edge == 100 and p.materials == {"gang_1": 1}


def test_a_server_bot_feeds_its_horse_while_looking_after_itself(content, world):
    from tianxia import bot_policy
    game = _game(content, world, horse=_horse(edge=40))
    game.state.player.materials = {"gang_1": 1}
    bot_policy.look_after(game, random.Random(0))
    assert game.state.player.mount.edge == 100
