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


@pytest.mark.parametrize("mode, cost, when", [("walk", 0, "約 2 分鐘"), ("hurry", 2, "約 1 分鐘"), ("dash", 5, "立刻到")])
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


@pytest.mark.parametrize("mode, cost, when", [("walk", 0, "約 1 分鐘"), ("hurry", 2, "約 1 分鐘"), ("dash", 2, "立刻到")])
def test_turning_back_on_the_road_states_and_takes_the_same_stamina(content, world, mode, cost, when):
    """走到一半折返（設計 5.3：三種走法各驗一次）：回程照路上的位置算（road_spot 讀出發時的步調），鈕上寫的時間與體力就是扣的、
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
