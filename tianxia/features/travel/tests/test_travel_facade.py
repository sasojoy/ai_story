"""travel 這一包的測試，從 tests/core/test_engine.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
from unittest import mock
import pytest
from conftest import FixedRandom, at, walk_to
from tianxia import flavor, rules
from tianxia.state import Journey, Rumor
from engine_kit import _add_field, _hall, _install_battle_def, _legacy_hurry, _partway, _south_cave, ids  # noqa: F401

pytestmark = pytest.mark.whole_content


def test_locked_location_hidden_until_flag(game):
    walk_to(game, "lake")
    assert "move:cave" not in ids(game)
    game.state.world.flags.add("cave_open")
    assert "move:cave" in ids(game)


def test_walking_to_a_neighbour_costs_no_stamina(game):
    game.state.player.stamina = 0
    move = next(o for o in game.options() if o.id == "move:lake")
    assert move.enabled and move.label == "前往 湖邊（步行約 3 分鐘）"
    game.choose("move:lake")
    assert game.state.player.stamina == 0


def test_invalid_option_rejected(game):
    assert game.choose("move:cave") == ["（此刻無法這麼做。）"]
    assert game.state.player.location == "town"


def test_insufficient_stamina_disables_actions(game):
    game.state.player.stamina = 4
    opts = game.options()
    assert all(not o.enabled for o in opts if o.id != "act:rest" and not o.id.startswith("move:"))
    assert all(o.enabled for o in opts if o.id.startswith("move:"))  # 步行不花體力
    game.choose("act:explore")
    assert game.state.player.stamina == 4


def test_a_timed_arrival_never_calls_the_model(game):
    """計時器的 sync 拿著全服行動鎖：路上抵達不叫模型（江湖大事潤色也不叫）。"""
    walk_to(game, "lake")
    with mock.patch.object(flavor, "polish_world_event") as news:
        game.choose("move:town")  # 小鎮開局就去過：重遊
        game.state.world.trends["kou"] = 50  # 抵達時才跨過「水寇封江」
        game.advance(game.state.player.journey.arrive_at[-1] - game.state.world.time)
    assert "blocked" in game.state.world.flags  # 門檻照樣觸發，只是沒潤色
    news.assert_not_called()


def test_travel_is_refused_with_a_reason(game):
    before = len(game.state.journal)
    game.state.pending_event = "drunk"
    assert game.travel("lake") == ["（先回江湖頁處理「醉漢」。）"]
    game.state.pending_event = None
    game.state.player.busy_until = 3600.0
    assert game.travel("lake") == ["（閉關中，不能安排前往。）"]
    game.state.player.busy_until = None
    game.state.world.ended = True
    assert game.travel("lake") == ["（賽季已結束，不能安排前往。）"]
    game.state.world.ended = False
    assert game.travel("town") == ["（無法安排前往這裡。）"]  # 所在地
    assert game.travel("cave") == ["（無法安排前往這裡。）"]  # 未開放
    assert game.travel("nowhere") == ["（無法安排前往這裡。）"]
    assert game.travel("lake", "fly") == ["（無法安排前往這裡。）"]
    game.state.player.stamina = 5
    assert game.travel("lake", "dash") == ["（體力不足，疾行要 6 體力。）"]
    assert game.travel("lake", "hurry") == ["（無法安排前往這裡。）"]  # 企劃者 2026-10-12 拿掉趕路
    assert game.state.player.location == "town" and game.state.player.stamina == 5
    assert len(game.state.journal) == before


def test_a_chained_event_names_the_step_that_is_pending_now_when_travel_is_refused(game):
    """FB-063：多段事件走到下一段（next_event）之後，不能出發的原因寫的是「現在」待處理的那一段，不是第一段。"""
    game._present(game.content.events["chain_a"])
    assert game.travel_refusal("lake") == "先回江湖頁處理「跟蹤」"
    game.choose("choice:0")  # 繼續：接到「倉庫」
    assert game.state.pending_event == "chain_b"
    assert game.travel_refusal("lake") == "先回江湖頁處理「倉庫」"
    assert game.travel("lake") == ["（先回江湖頁處理「倉庫」。）"]
    game.choose("choice:0")  # 離開：事件了結，路就通了
    assert game.state.pending_event is None and game.travel_refusal("lake") is None


def test_walking_takes_time_and_arrives_on_the_next_sync(game):
    game.sync(1000.0)
    game.choose("move:lake")  # 夾具：小鎮—湖邊 3 分鐘
    p = game.state.player
    assert p.location == "town" and p.journey.path == ["lake"] and p.journey.arrive_at == [180.0]
    game.sync(1000.0 + 60)
    assert p.location == "town" and p.journey is not None  # 還在路上
    game.sync(1000.0 + 200)
    assert p.location == "lake" and p.journey is None and "lake" in p.visited


def test_on_the_road_you_can_turn_back_but_not_do_what_needs_a_place(game):
    game.choose("move:lake")
    opts = game.options()
    assert [(o.id, o.enabled) for o in opts] == [
        ("act:on_road", False), ("road:back", True),
        ("road:think", True), ("road:ask", True), ("road:gather", True),
    ]
    assert "抵達湖邊" in opts[0].label
    assert game.choose("act:explore") == ["（此刻無法這麼做。）"]
    assert game.seclude(4) == ["你現在無法閉關。"]
    assert game.travel_refusal("lake") is None  # 路上設計 3.1：在路上也能安排前往（改道）


def test_the_status_bar_shows_the_arrival_countdown_and_the_scene_does_not_repeat_it(game):
    """FB-046：抵達的倒數只寫在狀態列（每一頁都看得到）；場景只寫「在路上」與路上能做什麼，不再寫一次。
    FB-062：只寫現實的倒數，不寫抵達的時刻——季曆跑得比現實快，兩種時間混在一行會讓人算不出來。"""
    game.choose("move:lake")
    assert "🧭 在路上：往湖邊（步行），現實約 3 分鐘後抵達" in game.status_text()
    assert game.status_data()["journey"] == "往湖邊（步行），現實約 3 分鐘後抵達"
    scene = game.scene_text()
    assert scene.startswith("**在路上**") and "到了會自己抵達" in scene
    assert "現實約" not in scene and "第1天 00:03" not in scene


def test_the_journey_line_counts_real_minutes_even_when_the_world_clock_runs_faster(content, game):
    """FB-062：世界時鐘的一段秒數 ÷ time_scale ＝ 現實秒；狀態列的「現實約 N 分鐘」照現實算，後面的站名照舊。"""
    content.config.time_scale = 3.0  # 世界時鐘每現實秒走 3 秒：湖邊 3 分鐘的路程（世界秒）只要現實 1 分鐘
    game.choose("move:lake")
    assert game.status_data()["journey"] == "往湖邊（步行），現實約 1 分鐘後抵達"


def test_departing_is_not_arriving_for_the_tutorial(game):
    game.state.player.tutorial_step = 1  # 「去湖邊」
    game.choose("move:lake")
    assert game.state.player.tutorial_step == 1
    game.advance(game.state.player.journey.arrive_at[-1] - game.state.world.time)
    assert game.state.player.tutorial_step == 2


def test_a_threshold_crossed_on_arrival_reaches_the_shared_season(game):
    game.content.config.decisive_from_week = 1  # 這一支不是在測收季門檻要等到決定性那一週（FB-165，test_world 另測）：關掉那一道
    game.sync(1000.0)
    game.choose("move:lake")
    # sync 會先換成共用賽季的那一份，所以改共用的；追趕那 200 秒不滿一小時，世界本身不檢查門檻
    game.world.mutate_season(lambda season: season.trends.__setitem__("kou", 80))
    game.sync(1000.0 + 200)  # 抵達時才檢查：水寇稱霸，賽季落幕
    assert game.state.world.ended and game.world.get_season().ended


# ── 喊停（地圖擴充：停在下一站） ─────────────────────────────────────────


def test_you_can_stop_at_the_next_station(game):
    game.state.world.flags.add("cave_open")
    game.travel("cave", "walk")
    assert "act:halt" in [o.id for o in game.options() if o.enabled]
    assert "喊停（到湖邊就停下）" in [o.label for o in game.options()]
    game.choose("act:halt")
    assert game.state.player.journey.stop_at == 0
    assert not any(o.id == "act:halt" for o in game.options())  # 已經喊停了
    assert "已經喊停" in game.scene_text()
    game.advance(game.state.player.journey.arrive_at[0] - game.state.world.time)
    assert game.state.player.location == "lake" and game.state.player.journey is None
    assert game.state.journal[0].tag == "喊停，停在 湖邊"


def test_there_is_nothing_to_stop_on_the_last_leg(game):
    game.choose("move:lake")
    assert not any(o.id == "act:halt" for o in game.options())


def _back(game):
    return next(o for o in game.options() if o.id.startswith("road:back"))


def test_turning_back_walks_back_the_part_already_walked(game):
    _partway(game)  # 走了一成三：回小鎮要 1 分鐘
    back = _back(game)
    assert (back.id, back.label, back.enabled) == ("road:back", "折返 小鎮（步行約 1 分鐘）", True)
    game.choose("road:back")
    j = game.state.player.journey
    assert (j.path, j.origin, j.share) == (["town"], "lake", pytest.approx(2 / 3))
    assert j.arrive_at == [pytest.approx(120.0)]  # 第 60 秒掉頭，再走 60 秒
    assert (game.state.journal[0].title, game.state.journal[0].tag) == ("前往 小鎮", "步行約 1 分鐘")
    game.advance(60)
    assert game.state.player.location == "town" and game.state.player.journey is None


def test_rerouting_to_either_end_of_the_road(game):
    _partway(game)
    game.travel("lake")  # 改去前面那一站：照原路走完這一段，抵達時間不變
    j = game.state.player.journey
    assert (j.path, j.arrive_at) == (["lake"], [pytest.approx(180.0)])
    game.travel("town")  # 改去剛離開的那一站：就是折返
    j = game.state.player.journey
    assert (j.path, j.origin, j.arrive_at) == (["town"], "lake", [pytest.approx(120.0)])


def test_a_reroute_charges_the_new_way_and_refunds_nothing(game):
    game.state.world.flags.add("cave_open")
    game.state.player.stamina = 100
    _legacy_hurry(game, "lake")  # 3 分鐘：3 點（拿掉趕路之前出發的那一趟）
    game.choose("road:back")  # 剛出發就掉頭：不扣體力、當下回到小鎮（FB-025），原本的 3 點不退
    assert game.state.player.stamina == 97 and game.state.player.journey is None
    _legacy_hurry(game, "lake")
    game.advance(30)  # 趕路 90 秒的三分之一
    game.travel("cave", "dash")  # 改道疾行：2 ＋ 4.5 ＝ 6.5 分鐘，13 點；第一段是半段路
    assert game.state.player.stamina == pytest.approx(97 - 3 - 13 + 30 / 180)  # 走那 30 秒回了一點點
    assert game.state.player.location == "cave" and game.state.player.journey is None


def test_dashing_from_the_road_reaches_an_end_of_the_road_first(content, game):
    _add_field(content)
    _partway(game)
    game.travel("field", "dash")  # 掉頭比較近：先到小鎮，再到田野
    p = game.state.player
    assert p.location == "field" and p.journey is None and "field" in p.visited
    entry = game.state.journal[0]
    assert (entry.title, entry.tag, entry.changes) == ("前往 田野（途經 小鎮）", "疾行立刻到", ["體力 -8"])


def test_a_rerouted_trip_can_be_halted_like_any_other(content, game):
    _add_field(content)
    _partway(game)
    game.travel("field")  # 小鎮、田野兩站
    assert "喊停（到小鎮就停下）" in [o.label for o in game.options()]
    game.choose("act:halt")
    game.advance(game.state.player.journey.arrive_at[0] - game.state.world.time)
    assert game.state.player.location == "town" and game.state.player.journey is None
    assert game.state.journal[0].tag == "喊停，停在 小鎮"


def test_rerouting_out_of_the_battle_region_leaves_it_and_turning_back_returns(content, game):
    definition = _install_battle_def(content)
    definition.region = "north"
    _south_cave(content, game)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        _partway(game)
        game.travel("cave")  # 繼續走：湖邊之後是南區的寶洞
        assert game.world.get_battle().participants["沈浪"].away
        game.choose("road:back")  # 掉頭回小鎮：這一趟的站都在北區
        assert not game.world.get_battle().participants["沈浪"].away


def test_turning_back_follows_the_move_mode(game):
    _partway(game)
    assert (_back(game).id, _back(game).label) == ("road:back", "折返 小鎮（步行約 1 分鐘）")
    game.set_move_mode("dash")
    game.state.player.stamina = 1
    back = _back(game)
    assert (back.id, back.label, back.enabled) == ("road:back:dash", "折返 小鎮（疾行・體力不足，要 2）", False)
    assert game.choose("road:back:dash") == ["（此刻無法這麼做。）"]
    game.state.player.stamina = 10
    game.choose("road:back:dash")
    assert game.state.player.location == "town" and game.state.player.journey is None
    assert game.state.player.stamina == 8


def test_turning_back_right_after_setting_off_is_free_and_lands_at_once(game):
    """剛出發就折返（FB-025）：回程不到半分鐘路程時，哪種走法都不扣體力、當下就回到原地（路上裁決「給 QA 的」）。"""
    game.choose("move:lake")
    game.advance(20)  # 步行 20 秒＝走了 1/3 分鐘路程
    stamina = game.state.player.stamina
    assert [(o.label, o.enabled) for o in game.travel_options("town")] == [("步行（立刻到）", True), ("疾行（立刻到）", True)]
    game.set_move_mode("dash")
    assert (_back(game).id, _back(game).label) == ("road:back:dash", "折返 小鎮（立刻到）")
    game.choose("road:back:dash")
    p = game.state.player
    assert (p.location, p.journey, p.stamina) == ("town", None, stamina)
    assert (game.state.journal[0].title, game.state.journal[0].tag, game.state.journal[0].changes) == (
        "前往 小鎮", "立刻折返", [],
    )


def test_turning_back_after_a_real_stretch_still_costs_and_takes_time(game):
    """走了一段才折返照舊算：回程 1.5 分鐘路程，步行約 2 分鐘；疾行 3 點、立刻到。"""
    game.choose("move:lake")
    game.advance(90)  # 步行 180 秒的一半
    stamina = game.state.player.stamina
    assert _back(game).label == "折返 小鎮（步行約 2 分鐘）"
    game.choose("road:back")
    p = game.state.player
    assert p.journey is not None and p.journey.path == ["town"] and p.stamina == stamina
    game.travel("lake")  # 再掉頭一次（回程 1.5 分鐘），改疾行
    game.set_move_mode("dash")
    stamina = p.stamina
    assert _back(game).label == "折返 小鎮（疾行立刻到・體力 3）"
    game.choose("road:back:dash")
    assert p.journey is None and p.location == "town" and p.stamina == stamina - 3


def test_turning_back_twice_quickly_is_not_a_free_arrival_at_the_far_end(game):
    """掉頭之後馬上又掉頭：身後那一站是剛才要去的湖邊、不是自己最後待過的小鎮，不算剛出發，照舊要走（不能拿來白白抵達）。"""
    game.choose("move:lake")
    game.advance(160)  # 走了快九成
    game.choose("road:back")
    game.choose("road:back")  # 再掉頭：往湖邊，回程 20 秒路程
    p = game.state.player
    assert p.journey is not None and p.journey.path == ["lake"] and p.location == "town"


def test_the_road_scene_says_what_you_can_do_on_the_road(game):
    game.choose("move:lake")
    scene = game.scene_text()
    assert "路上可以折返" in scene and "修練、煉製" in scene and "到了會自己抵達" in scene
    assert "路上不能做事" not in scene


# ── 路上小事（路上設計第四節）──────────────────────────────


def _task(game, what):
    return next(o for o in game.options() if o.id == f"road:{what}")


def test_road_tasks_are_once_per_leg_and_free(game):
    game.state.world.flags.add("cave_open")
    game.travel("cave")  # 小鎮—湖邊—寶洞兩段
    assert (_task(game, "think").label, _task(game, "think").enabled) == ("邊走邊想（心得 +3）", True)
    stamina = game.state.player.stamina
    game.choose("road:think")
    assert game.state.player.stats["xinde"] == 3 and game.state.player.stamina == stamina
    assert (_task(game, "think").label, _task(game, "think").enabled) == ("邊走邊想（想過了，到下一站再說）", False)
    entry = game.state.journal[0]
    assert (entry.title, entry.changes) == ("邊走邊想", ["心得 +3"])
    game.advance(game.state.player.journey.arrive_at[0] - game.state.world.time)  # 到湖邊：換段
    assert game.state.player.journey is not None and _task(game, "think").enabled


def test_turning_back_does_not_hand_out_the_road_tasks_again(game):
    game.choose("move:lake")
    game.choose("road:think")
    game.choose("road:back")  # 剛出發就掉頭，馬上回到小鎮
    game.advance(0)
    assert game.state.player.location == "town" and game.state.player.journey is None
    game.choose("move:lake")  # 再出發：還沒真的到下一站，做過的還是做過了（不然來回折返就能不走路刷完一天的收穫）
    assert (_task(game, "think").label, _task(game, "think").enabled) == ("邊走邊想（想過了，到下一站再說）", False)
    game.advance(game.state.player.journey.arrive_at[0] - game.state.world.time)  # 真的走到湖邊才換段
    assert game.state.player.leg_actions == set()


def test_dashing_has_no_road_tasks(game):
    game.state.player.journey = Journey(mode="dash", path=["lake"], arrive_at=[1e9])
    assert not any(o.id.startswith("road:") and o.id != "road:back" for o in game.options())
    game.state.player.journey = Journey(mode="hurry", path=["lake"], arrive_at=[90.0])
    assert "road:gather" in ids(game)


def test_asking_along_the_road_hears_a_rumor_from_this_part_of_the_land(game):
    game.choose("move:lake")
    w = game.state.world
    w.rumors += [
        Rumor(time=0, text="南邊鬧水患。", location=None, region="south"),
        Rumor(time=0, text="官軍在湖邊集結。", location="lake", region="north", faction="guan"),  # 別的陣營的軍情
        Rumor(time=0, text="湖邊來了個怪客。", location="lake", region="north"),
    ]
    msgs = game.choose("road:ask")
    assert msgs == ["你沿途向人打聽，聽說：湖邊來了個怪客。"]
    assert (_task(game, "ask").label, _task(game, "ask").enabled) == ("沿途打聽（打聽過了，到下一站再說）", False)


def test_asking_with_nothing_to_hear_still_counts(game):
    game.choose("move:lake")
    assert game.choose("road:ask") == ["你沿途問了幾個人，這一帶最近沒什麼新鮮事。"]
    assert not _task(game, "ask").enabled


def test_gathering_by_the_road_follows_what_the_two_ends_offer(content, game):
    content.locations["lake"].materials = ["gang_2"]  # 湖邊出剛的素材：路邊撿到的是剛的一階
    game.choose("move:lake")
    game.rng = FixedRandom(0.1)
    assert game.choose("road:gather") == ["你在路邊翻找了一陣。", "獲得 精鐵砂 ×1"]
    assert game.state.player.materials == {"gang_1": 1}


def test_gathering_can_come_up_empty(game):
    game.choose("move:lake")
    game.rng = FixedRandom(0.9)  # 四成機會：沒撿到
    assert game.choose("road:gather") == ["你在路邊翻找了一陣，沒找到什麼能用的。"]
    assert game.state.player.materials == {} and not _task(game, "gather").enabled


def test_gathering_without_any_tier_one_material_finds_nothing(content, game):
    """內容裡沒有一階素材時，採集當成沒找到，不會出錯，也不算今天的收穫。"""
    content.materials = {k: m for k, m in content.materials.items() if m.tier != 1}
    game.choose("move:lake")
    game.rng = FixedRandom(0.1)
    assert game.choose("road:gather") == ["你在路邊翻找了一陣，沒找到什麼能用的。"]
    assert game.state.player.road_rewards_today.get("task") is None


def test_the_road_scene_lists_the_road_tasks(game):
    game.choose("move:lake")
    assert "邊走邊想、沿途打聽、路邊採集" in game.scene_text()


# ── 路上收穫的每天上限（企劃者 2026-10-03 決定）──────────────────


def _leg(game, dest, *tasks):
    """從所在的站步行到相鄰的 dest，路上依序做 tasks，一路走到。"""
    game.choose(f"move:{dest}")
    for what in tasks:
        game.choose(f"road:{what}")
    game.advance(game.state.player.journey.arrive_at[-1] - game.state.world.time)


def test_thinking_on_the_road_pays_only_the_first_few_times_a_game_day(content, game):
    content.config.road_reward_daily_cap = 2
    p = game.state.player
    _leg(game, "lake", "think")
    _leg(game, "town", "think")
    assert p.road_rewards_today == {"task": [1, 2]}
    game.choose("move:lake")  # 同一天的第三段路
    think = _task(game, "think")
    moment = rules.day_ends_text(content, game.state.world)  # 換日的那一刻（遊戲日跟著季長縮，企劃者 2026-10-08）
    assert (think.label, think.enabled) == ("邊走邊想（收穫拿滿了）", True)  # 鈕上不寫時刻（2×2 格子放不下）；按下去那一句寫
    xinde = p.stats["xinde"]
    assert game.choose("road:think") == [f"你邊走邊想，這陣子想得夠多了，沒有新的心得（{moment} 之後才會再有）。"]
    assert p.stats["xinde"] == xinde and p.road_rewards_today == {"task": [1, 2]}
    assert game.state.journal[0].changes == []
    assert (_task(game, "think").label, _task(game, "think").enabled) == ("邊走邊想（想過了，到下一站再說）", False)


def test_the_road_reward_count_starts_over_the_next_game_day(content, game):
    content.config.road_reward_daily_cap = 1
    p = game.state.player
    _leg(game, "lake", "think")
    game.state.world.time = rules.day_ends(content, game.state.world)  # 換日：紀錄是前一天的就當沒拿過（跟每天對話輪數同一個算法）
    game.choose("move:town")
    assert _task(game, "think").label == "邊走邊想（心得 +3）"
    xinde = p.stats["xinde"]
    game.choose("road:think")
    assert p.stats["xinde"] == xinde + 3 and p.road_rewards_today == {"task": [2, 1]}


def test_only_a_material_actually_found_counts_toward_the_day(game):
    p = game.state.player
    game.choose("move:lake")
    game.rng = FixedRandom(0.9)
    game.choose("road:gather")  # 沒撿到：不算一次
    assert p.road_rewards_today == {}
    game.advance(p.journey.arrive_at[-1] - game.state.world.time)
    game.choose("move:town")
    game.rng = FixedRandom(0.1)
    game.choose("road:gather")
    assert sum(p.materials.values()) == 1 and p.road_rewards_today == {"task": [1, 1]}


def test_thinking_and_gathering_share_the_days_road_rewards(content, game):
    content.config.road_reward_daily_cap = 1
    p = game.state.player
    game.choose("move:lake")
    game.choose("road:think")
    gather = _task(game, "gather")
    moment = rules.day_ends_text(content, game.state.world)
    assert (gather.label, gather.enabled) == ("路邊採集（收穫拿滿了）", True)
    game.rng = FixedRandom(0.1)  # 沒到上限的話這一擲撿得到
    assert game.choose("road:gather") == [f"你留心路邊，這陣子已經撿夠了，沒再去翻（{moment} 之後再說）。"]
    assert p.materials == {} and p.road_rewards_today == {"task": [1, 1]}
    assert not _task(game, "gather").enabled  # 照樣算這段路做過了
    # 沿途打聽沒有經濟上的收穫，不設上限
    assert _task(game, "ask").label == "沿途打聽（聽一則這一帶的傳聞）"


def test_a_road_sight_seen_while_offline_is_dated_at_the_arrival(content, game):
    content.config.road_sight_chance = 1.0
    game.sync(1000.0)
    game.choose("move:lake")  # 第 0 秒出發，第 180 秒抵達
    game.sync(1000.0 + 3600)  # 下線一小時才回來
    sight = content.road_sights[game.state.player.recent_sights[-1]]
    entry = next(e for e in game.state.journal if sight.text in e.lines)
    assert entry.time == pytest.approx(180.0)


def test_dashing_still_rolls_a_road_sight_at_every_stop(content, game):
    content.config.road_sight_chance = 1.0
    game.state.world.flags.add("cave_open")
    game.travel("cave", "dash")  # 湖邊、寶洞兩站立刻抵達
    assert len(game.state.player.recent_sights) == 2


# ── 路上見聞的每天上限與折返（企劃者 2026-10-03 決定）──────────────
# 夾具在小鎮—湖邊（北區的一般路）能挑的是烏鴉（心得 +1）、起風（沒有收穫）、貨郎（心得 +2）三則；
# 把其餘的標成剛看過，下一則就一定是想要的那一則。


def _sight_rewards(entry):
    """一則江湖紀錄裡，路上見聞會給的那幾種收穫行。"""
    return [line for line in entry.lines + entry.changes if line.startswith(("心得 +", "銀兩 +", "獲得"))]


def test_road_sight_rewards_stop_at_the_days_cap_but_the_text_stays(content, game):
    content.config.road_sight_chance = 1.0
    content.config.road_reward_daily_cap = 1
    p = game.state.player
    xinde = p.stats["xinde"]
    p.recent_sights = ["sight_wind", "sight_north_peddler"]  # 只剩烏鴉
    walk_to(game, "lake")
    assert p.stats["xinde"] == xinde + 1 and p.road_rewards_today == {"sight": [1, 1]}
    p.recent_sights = ["sight_crow", "sight_wind"]  # 同一天走回小鎮：只剩貨郎，但今天的收穫拿滿了
    walk_to(game, "town")
    entry = game.state.journal[0]
    assert content.road_sights["sight_north_peddler"].text in entry.lines  # 文字照寫
    assert _sight_rewards(entry) == []  # 沒有收穫、也沒有多一句
    assert p.stats["xinde"] == xinde + 1 and p.road_rewards_today == {"sight": [1, 1]}
    assert p.recent_sights[-1] == "sight_north_peddler"


def test_at_the_days_cap_sights_that_hand_you_something_stay_away(content, game):
    """拿滿了：給銀兩、素材的見聞，文字寫的就是拿到東西，那天不再出現；給心得的照寫文字、不給心得（見上一則）。"""
    content.config.road_sight_chance = 0.0
    game.state.world.flags.add("cave_open")
    walk_to(game, "lake")
    content.config.road_sight_chance = 1.0
    content.config.road_reward_daily_cap = 1
    p = game.state.player
    p.road_rewards_today = {"sight": [1, 1]}  # 今天的見聞收穫已經拿滿
    p.recent_sights = ["sight_crow", "sight_wind"]  # 湖邊—寶洞是山路：沒看過的只剩峭壁（給銀兩）
    walk_to(game, "cave")
    assert p.recent_sights[-1] != "sight_cliff"
    assert content.road_sights["sight_cliff"].text not in game.state.journal[0].lines


def test_the_road_sight_cap_counts_the_day_of_the_arrival(content, game):
    """下線補算跨過換日：第 1 個遊戲日結束前兩分鐘抵達的那一站，收穫算第 1 天（紀錄上寫的也是那一刻）。"""
    content.config.road_sight_chance = 1.0
    p = game.state.player
    p.recent_sights = ["sight_wind", "sight_north_peddler"]  # 只剩烏鴉（心得 +1）
    game.advance(rules.day_ends(content, game.state.world) - 300 - game.state.world.time)  # 換日前五分鐘
    game.choose("move:lake")  # 走三分鐘，換日前兩分鐘抵達
    game.advance(600)  # 換日之後五分鐘才補算
    assert p.road_rewards_today == {"sight": [1, 1]}


def test_road_sight_rewards_start_over_the_next_game_day(content, game):
    content.config.road_sight_chance = 1.0
    content.config.road_reward_daily_cap = 1
    p = game.state.player
    p.recent_sights = ["sight_wind", "sight_north_peddler"]
    walk_to(game, "lake")
    game.state.world.time = rules.day_ends(content, game.state.world)  # 換日：紀錄是前一天的就當沒拿過
    p.recent_sights = ["sight_wind", "sight_north_peddler"]
    xinde = p.stats["xinde"]
    walk_to(game, "town")
    assert p.stats["xinde"] == xinde + 1 and p.road_rewards_today == {"sight": [2, 1]}
    assert _sight_rewards(game.state.journal[0]) == ["心得 +1"]


def test_a_road_sight_without_a_reward_never_counts_toward_the_day(content, game):
    content.config.road_sight_chance = 1.0
    p = game.state.player
    p.recent_sights = ["sight_crow", "sight_north_peddler"]  # 只剩起風
    walk_to(game, "lake")
    assert p.recent_sights[-1] == "sight_wind" and p.road_rewards_today == {}


def test_turning_back_at_once_brings_no_road_sight(content, game):
    """剛出發就掉頭回到剛離開的那一站（不花時間也不花體力）不擲見聞：跟路上小事不換段是同一條規則。"""
    content.config.road_sight_chance = 1.0
    p = game.state.player
    game.choose("move:lake")
    game.choose("road:back")
    game.advance(0)
    assert p.location == "town" and p.journey is None
    assert p.recent_sights == []
    texts = {sight.text for sight in content.road_sights.values()}
    assert not any(line in texts for entry in game.state.journal for line in entry.lines)
    walk_to(game, "lake")  # 真的走到另一站才有
    assert len(p.recent_sights) == 1


def test_you_cannot_travel_or_seclude_while_picking_whom_to_call_on(content, game):
    _hall(content, game)
    game.choose("act:call")
    assert game.travel_refusal("lake") == "求見中，先返回才能安排前往"
    assert game.travel("lake") == ["（求見中，先返回才能安排前往。）"]
    assert game.seclude(4) == ["你現在無法閉關。"]


# ── 主畫面的走法切換（步行／疾行）──────────────────────


def _move_to_lake(game):
    return next(o for o in game.options() if o.id.startswith("move:lake"))


def test_the_menu_walks_by_default(game):
    assert game.move_mode == "walk"
    move = _move_to_lake(game)
    assert (move.id, move.label, move.enabled) == ("move:lake", "前往 湖邊（步行約 3 分鐘）", True)


def test_dashing_from_the_menu_arrives_at_once(game):
    game.set_move_mode("dash")
    assert _move_to_lake(game).label == "前往 湖邊（疾行立刻到・體力 6）"
    game.choose("move:lake:dash")
    p = game.state.player
    assert p.location == "lake" and p.journey is None and p.stamina == 144


def test_a_mode_you_cannot_afford_disables_the_move_and_says_why(game):
    game.set_move_mode("dash")
    game.state.player.stamina = 5
    move = _move_to_lake(game)
    assert (move.label, move.enabled) == ("前往 湖邊（疾行・體力不足，要 6）", False)
    assert game.choose("move:lake:dash") == ["（此刻無法這麼做。）"]
    assert game.state.player.location == "town" and game.state.player.stamina == 5


def test_the_move_mode_changes_labels_not_the_number_of_options(game):
    walking = ids(game)
    for mode in ("dash",):
        game.set_move_mode(mode)
        assert len(ids(game)) == len(walking)
        assert f"move:lake:{mode}" in ids(game) and "move:lake" not in ids(game)
    assert game.choose("move:lake") == ["（此刻無法這麼做。）"]  # 選單上已經不是步行：舊按鈕的 id 不算數


def test_an_unknown_mode_falls_back_to_walking(game):
    game.set_move_mode("fly")
    assert game.move_mode == "walk" and "move:lake" in ids(game)
