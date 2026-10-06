import pytest

from tianxia.atlas import (
    Route, TravelBlock, TravelOption, detail_text, direction, foes, goal_places, haunters, is_known, known_locations, leg_minutes,
    place_choices, recent_news, region_of, region_trends, road_hops, road_spot, routes, travel_block, travel_options,
    travel_refusal, travel_seconds, travel_stamina, views, way_to, whole_minutes, worst_foe,
)
from tianxia.models import Condition, Connection, Location, SimPlayer
from tianxia.state import Journey, Rumor

DAY = 86400


def region(content, region_id):
    return next(r for r in content.map.regions if r.id == region_id)


def add_hill(content) -> None:
    """夾具只有一條線（小鎮—湖邊—寶洞）；加一座山丘，讓小鎮到寶洞多一條路。"""
    content.locations["hill"] = Location(
        id="hill", name="山丘", description="小山丘。", connections=["town", "cave"], x=200, y=50
    )
    content.locations["town"].connections.append("hill")
    content.locations["cave"].connections.append("hill")


def no_odds(squad_id: str) -> str:
    raise AssertionError(f"不該算勝算：{squad_id}")


def test_locations_belong_to_the_region_that_contains_them(content):
    assert region_of(content, "town").id == "north"
    assert region_of(content, "cave").id == "north"
    content.locations["lake"].y = 170  # 移進南區的多邊形
    assert region_of(content, "lake").id == "south"


def test_location_outside_every_region_goes_to_the_nearest(content):
    content.locations["lake"].y = 197  # 南區只畫到 y=190：兩區之外，離南區最近
    assert region_of(content, "lake").id == "south"
    content.locations["lake"].y = 200  # 地圖最下緣：還是南區最近
    assert region_of(content, "lake").id == "south"


def test_no_regions_means_no_region(content):
    content.map.regions = []
    assert region_of(content, "town") is None


# ── 視野與選得到的地點 ─────────────────────────────────


def test_known_locations_and_place_choices(state, content):
    assert known_locations(state, content) == {"town", "lake"}  # 寶洞未開放
    assert place_choices(state, content) == [("小鎮（所在地）", "town"), ("湖邊", "lake")]
    content.config.vision_base = 0
    assert known_locations(state, content) == {"town"}
    assert place_choices(state, content) == [("小鎮（所在地）", "town")]  # 沒名字的淡點不列
    content.locations["lake"].important = True
    assert place_choices(state, content) == [("小鎮（所在地）", "town"), ("湖邊？", "lake")]


# ── 大區 ──────────────────────────────────────────────


def test_direction():
    assert [direction((0, 0), end) for end in ((9, 0), (9, 9), (0, 9), (-9, 9), (-9, 0), (-9, -9), (0, -9), (9, -9))] == [
        "→", "↘", "↓", "↙", "←", "↖", "↑", "↗",
    ]


def test_road_hops_count_stops_over_open_roads(state, content):
    assert road_hops(state, content, 2) == {"town": 0, "lake": 1}  # 寶洞未開放
    state.world.flags.add("cave_open")
    assert road_hops(state, content, 2) == {"town": 0, "lake": 1, "cave": 2}
    assert road_hops(state, content, 1) == {"town": 0, "lake": 1}
    add_hill(content)
    assert road_hops(state, content, 2) == {"town": 0, "lake": 1, "hill": 1, "cave": 2}


# ── 局勢 ──────────────────────────────────────────────


def test_region_trends_hide_unrevealed_trends(state, content):
    assert region_trends(state, content, region(content, "north")) == [("寇亂", 30)]
    assert region_trends(state, content, region(content, "south")) == []  # 寶藏線還沒浮現
    state.world.revealed.add("bao")
    state.world.trends["bao"] = 12
    assert region_trends(state, content, region(content, "south")) == [("寶藏", 12)]


def test_haunters_wait_for_their_hidden_trend(state, content):
    assert haunters(state, content, "lake") == ["翻江龍"]
    assert haunters(state, content, "cave") == []  # 鬼手要等寶藏線浮現
    state.world.revealed.add("bao")
    assert haunters(state, content, "cave") == ["鬼手"]
    content.scenario.sim_players[1].haunts.append("lake")
    content.scenario.sim_players.append(content.scenario.sim_players[0].model_copy())
    assert haunters(state, content, "lake") == ["翻江龍", "鬼手"]  # 同名只列一次


def test_haunters_also_respect_revealed_all_in_the_condition(state, content):
    content.scenario.sim_players[0].condition.revealed_all.append("bao")
    assert haunters(state, content, "lake") == []
    state.world.revealed.add("bao")
    assert haunters(state, content, "lake") == ["翻江龍"]


# ── 劇情 ──────────────────────────────────────────────


def test_goal_places_follow_the_current_act(state, content):
    assert goal_places(state, content) == ["lake"]
    state.world.act = 1
    assert goal_places(state, content) == []
    state.world.storyline, state.world.act = "treasure", 1  # 隱藏主線取代主線之後
    assert goal_places(state, content) == ["cave"]


def test_goal_places_are_empty_for_a_storyline_season_one_turns_off(state, content):
    """計畫 T8：第一季不觸發的 beta 主線不在大地圖上標目標；開關關著照舊。"""
    from tianxia.models import SeasonOneOff

    content.scenario.season_one_off = SeasonOneOff(storylines=["main"])
    state.world.season_one = True
    assert goal_places(state, content) == ["lake"]  # 開關關著
    content.config.season_one = True
    assert goal_places(state, content) == []


def test_the_detail_panel_says_nothing_about_a_storyline_season_one_turns_off(state, content):
    """審查 M-3：第一季不觸發的 beta 主線，詳情欄不寫「是不是這一幕主線的目標」（那條主線玩家看不到）；開關關著照舊。"""
    from tianxia.models import SeasonOneOff

    content.scenario.season_one_off = SeasonOneOff(storylines=["main"])
    state.world.season_one = True
    assert "不是這一幕主線的目標" in detail_text(state, content, "town", no_odds)
    odds = {"thug": "穩勝"}.get
    assert "★ 這一幕主線的目標" in detail_text(state, content, "lake", odds)
    content.config.season_one = True
    for loc_id in ("town", "lake"):
        text = detail_text(state, content, loc_id, odds)
        assert "主線" not in text and "**劇情**　最近 3 天沒有大事或傳聞" in text, loc_id


def test_recent_news_keeps_the_last_three_days(state, content):
    rumors = state.world.rumors
    rumors.append(Rumor(time=0.5 * DAY, text="太舊了", location="lake"))
    rumors.append(Rumor(time=1.5 * DAY, text="三天內", location="lake"))
    rumors.append(Rumor(time=2 * DAY, text="別處", location="town"))
    rumors.append(Rumor(time=3 * DAY, text="沒有地點"))
    rumors.append(Rumor(time=4 * DAY, text="剛剛", location="lake"))
    state.world.time = 4.5 * DAY
    assert [r.text for r in recent_news(state, content, "lake")] == ["剛剛", "三天內"]


# ── 敵情 ──────────────────────────────────────────────


def test_worst_foe_is_the_one_with_the_worst_odds(content):
    lake = content.locations["lake"]
    lake.enemies = ["thug", "boss", "thug"]
    words = {"thug": "穩勝", "boss": "必敗"}
    assert foes(content, lake, words.get) == [("水寇小隊", "穩勝"), ("翻江龍", "必敗")]
    assert worst_foe(content, lake, words.get) == ("翻江龍", "必敗")
    words = {"thug": "凶險", "boss": "難分勝負"}
    assert worst_foe(content, lake, words.get) == ("水寇小隊", "凶險")
    words = {"thug": "五五波", "boss": "五五波"}
    assert worst_foe(content, lake, words.get) == ("水寇小隊", "五五波")  # 一樣險取排在前面的
    assert worst_foe(content, content.locations["town"], no_odds) is None


def test_your_own_factions_squads_are_a_drill_not_a_foe(content):
    """自己陣營的隊伍遇上了是操練、不會輸：敵情寫「操練」不算勝算，「最險」也不拿它算（試玩回饋 FB-008）。"""
    lake = content.locations["lake"]
    lake.enemies = ["thug", "boss"]
    content.squads["boss"].faction = "huang"
    words = {"thug": "穩勝", "boss": "必敗"}
    assert foes(content, lake, words.get, "huang") == [("水寇小隊", "穩勝"), ("翻江龍", "操練")]
    assert worst_foe(content, lake, words.get, "huang") == ("水寇小隊", "穩勝")
    assert worst_foe(content, lake, words.get, None) == ("翻江龍", "必敗")  # 散人沒有自己人：照常要打
    lake.enemies = ["boss"]
    assert worst_foe(content, lake, words.get, "huang") is None  # 只有自己人：沒有「最險」


# ── 路線 ──────────────────────────────────────────────


def test_leg_minutes_follow_distance_and_road(content):
    per_unit = content.config.travel_minutes_per_unit  # 夾具 0.03：每站 100 單位
    assert leg_minutes(content, "town", "lake") == pytest.approx(100 * 1.0 * per_unit)
    assert leg_minutes(content, "lake", "cave") == pytest.approx(100 * 1.5 * per_unit)  # 山路
    assert leg_minutes(content, "cave", "lake") == leg_minutes(content, "lake", "cave")
    content.locations["town"].connections = [Connection("lake", "官道")]
    assert leg_minutes(content, "town", "lake") == pytest.approx(100 * 0.8 * per_unit)


def test_travel_math_for_the_three_ways():
    assert (travel_seconds(9, "walk"), travel_seconds(9, "hurry"), travel_seconds(9, "dash")) == (540, 270, 0)
    assert (whole_minutes(0.2), whole_minutes(2.5), whole_minutes(4.49)) == (1, 3, 4)


def test_travel_stamina_follows_the_route_minutes(content):
    assert [travel_stamina(content, 9, mode) for mode in ("walk", "hurry", "dash")] == [0, 9, 18]
    assert travel_stamina(content, 0.2, "hurry") == 1  # 至少 1 點


def test_routes_take_the_quickest_way(state, content):
    state.world.flags.add("cave_open")
    found = routes(state, content)
    assert found["town"] == Route((), ())
    assert found["cave"].path == ("lake", "cave") and found["cave"].via == ("lake",)
    assert found["cave"].minutes == pytest.approx(3.0 + 4.5)  # 湖邊—寶洞是山路
    add_hill(content)  # 一樣兩站，但不用走山路
    quick = routes(state, content)["cave"]
    assert quick.path == ("hill", "cave") and quick.minutes == pytest.approx(2 * leg_minutes(content, "town", "hill"))


def test_routes_only_pass_known_and_open_places(state, content):
    assert "cave" not in routes(state, content)  # 未開放
    content.config.vision_base = 0
    assert routes(state, content) == {"town": Route((), ())}  # 湖邊沒摸清
    state.player.visited.add("lake")
    assert routes(state, content)["lake"].path == ("lake",)
    add_hill(content)  # 比較快，但山丘沒摸清
    state.world.flags.add("cave_open")
    state.player.visited.add("cave")
    assert routes(state, content)["cave"].path == ("lake", "cave")


def test_routes_prefer_fewer_stops_when_equally_quick(state, content):
    state.world.flags.add("cave_open")
    content.config.vision_base = 3
    content.locations["lake"].connections = ["town", "cave"]  # 湖邊—寶洞改成一般路：小鎮→寶洞 6 分鐘
    content.locations["cave"].connections = ["lake"]
    for loc_id, x in (("aa", 150), ("ab", 250)):  # 同一直線上多兩站：小鎮—aa—ab—寶洞，一樣 6 分鐘
        content.locations[loc_id] = Location(id=loc_id, name=loc_id, description="測試地點。", connections=[], x=x, y=100)
    for a, b in (("town", "aa"), ("aa", "ab"), ("ab", "cave")):
        content.locations[a].connections.append(b)
        content.locations[b].connections.append(a)
    assert routes(state, content)["cave"].path == ("lake", "cave")  # 一樣近時站數少的贏，即使另一條路的 id 排在前面


def test_routes_break_remaining_ties_by_id(state, content):
    state.world.flags.add("cave_open")
    for loc_id, y in (("hill", 50), ("dale", 150)):  # 上下對稱的兩條路：一樣近、一樣兩站，都比走湖邊—寶洞的山路快
        content.locations[loc_id] = Location(
            id=loc_id, name=loc_id, description="測試地點。", connections=["town", "cave"], x=200, y=y
        )
        content.locations["town"].connections.append(loc_id)
        content.locations["cave"].connections.append(loc_id)
    assert routes(state, content)["cave"].path == ("dale", "cave")  # 比地點 id：dale 在 hill 前面
    for loc in content.locations.values():
        loc.connections.reverse()
    assert routes(state, content)["cave"].path == ("dale", "cave")  # 和連線寫的順序無關


# ── 安排前往 ──────────────────────────────────────────


def test_travel_options_offer_walking_hurrying_and_dashing(state, content):
    assert travel_options(state, content, "town") is None  # 所在地
    assert travel_options(state, content, "cave") is None  # 未開放
    assert travel_options(state, content, "lake") == [
        TravelOption("walk", "步行（約 3 分鐘）", True),
        TravelOption("hurry", "趕路（約 2 分鐘・體力 3）", True),
        TravelOption("dash", "疾行（立刻到・體力 6）", True),
    ]
    state.player.stamina = 4
    assert travel_options(state, content, "lake")[2] == TravelOption("dash", "疾行（體力不足，要 6）", False)
    state.player.stamina = 2
    assert travel_options(state, content, "lake")[1] == TravelOption("hurry", "趕路（體力不足，要 3）", False)
    assert travel_options(state, content, "lake")[0].enabled  # 步行不花體力
    content.config.vision_base = 0
    assert travel_options(state, content, "lake") is None  # 沒摸清


def test_travel_options_and_refusal_explain_why_you_cannot_go(state, content):
    for setup, reason, to_jianghu in (
        (lambda: setattr(state, "pending_event", "drunk"), "先回江湖頁處理「醉漢」", True),
        (lambda: setattr(state.player, "busy_until", 3600.0), "閉關中，不能安排前往", False),
        (lambda: setattr(state.player, "resting_since", 0.0), "打坐中，先起身才能安排前往", False),
        (lambda: setattr(state.player, "pending_companion", "someone"), "交談中，先告辭才能安排前往", True),
        (lambda: setattr(state.player, "picking_audience", True), "求見中，先返回才能安排前往", True),
        (lambda: setattr(state.player, "pending_faction", "guan"), "投靠還沒決定，先決定再安排前往", True),
        (lambda: setattr(state.player, "fs_asking", "chain"), "正在答話，先作罷才能安排前往", True),
        (lambda: setattr(state.world, "ended", True), "賽季已結束，不能安排前往", False),
    ):
        state.pending_event, state.player.busy_until, state.player.resting_since = None, None, None
        state.player.pending_companion, state.player.pending_faction = None, None
        state.player.picking_audience, state.player.fs_asking = False, None
        state.world.ended = False
        setup()
        # 要回江湖頁了結才解得開的（事件、交談、求見、投靠待確認、答話）：頁面照 to_jianghu 多給一顆「回江湖」；
        # 閉關、打坐、賽季結束不是回江湖頁就解得開的事（FB-063）
        expected = [TravelOption("walk", reason, False, to_jianghu=to_jianghu)]
        assert travel_options(state, content, "lake") == expected
        assert travel_block(state, content) == TravelBlock(reason, to_jianghu=to_jianghu)
        assert travel_refusal(state, content, "lake", "walk") == reason
    state.world.ended = False
    assert travel_refusal(state, content, "town", "walk") == "無法安排前往這裡"
    state.player.stamina = 5
    assert travel_refusal(state, content, "lake", "dash") == "體力不足，疾行要 6 體力"
    assert travel_refusal(state, content, "lake", "hurry") is None


def test_a_pending_event_blocks_travel_by_name_and_says_where_to_settle_it(state, content):
    """FB-063：事件還沒選完不能出發。原因寫出是哪一則、要回江湖頁處理；多段事件寫「現在」待處理的那一則。"""
    state.pending_event = "chain_a"
    assert travel_block(state, content) == TravelBlock("先回江湖頁處理「跟蹤」", to_jianghu=True)
    state.pending_event = "chain_b"  # next_event 接下去的下一段
    assert travel_block(state, content) == TravelBlock("先回江湖頁處理「倉庫」", to_jianghu=True)
    assert travel_refusal(state, content, "lake", "dash") == "先回江湖頁處理「倉庫」"
    (option,) = travel_options(state, content, "lake")
    assert (option.label, option.enabled, option.to_jianghu) == ("先回江湖頁處理「倉庫」", False, True)
    state.pending_event = None
    state.player.busy_until = 3600.0  # 閉關中也不能出發，但那不是回江湖頁就解得開的事
    assert travel_block(state, content) == TravelBlock("閉關中，不能安排前往")
    assert travel_block(state, content).to_jianghu is False


def test_a_pending_event_missing_from_content_still_blocks_travel_toward_the_jianghu_page(state, content):
    """防守用的退路（讀檔時會清掉指向不存在事件的 pending_event，平常走不到）：事件名找不到也不能崩，照樣擋、照樣叫人回江湖頁。"""
    state.pending_event = "no_such_event"
    assert travel_block(state, content) == TravelBlock("先回江湖頁處理眼前的事", to_jianghu=True)
    assert travel_refusal(state, content, "lake", "walk") == "先回江湖頁處理眼前的事"
    (option,) = travel_options(state, content, "lake")
    assert (option.label, option.enabled, option.to_jianghu) == ("先回江湖頁處理眼前的事", False, True)


def test_the_season_ending_outranks_a_pending_event_in_the_travel_block(state, content):
    """賽季已結束時事件也動不了：原因寫賽季結束，不叫人回江湖頁。"""
    state.pending_event, state.world.ended = "drunk", True
    assert travel_block(state, content) == TravelBlock("賽季已結束，不能安排前往")


# ── 詳情欄 ────────────────────────────────────────────


def test_detail_of_an_unknown_place_leaks_nothing(state, content):
    content.config.vision_base = 0
    content.locations["lake"].important = True
    assert detail_text(state, content, "lake", no_odds) == "### 湖邊？\n\n尚未摸清"  # 只有畫出輪廓的才有名字


def test_detail_of_a_locked_place_or_a_dot_leaks_no_name(state, content):
    assert detail_text(state, content, "cave", no_odds) == "### ？\n\n尚未摸清"  # 未開放：完全不畫
    content.config.vision_base = 0
    assert content.locations["lake"].important is False
    assert detail_text(state, content, "lake", no_odds) == "### ？\n\n尚未摸清"  # 淡點沒有名字


def test_is_known_gates_places_for_the_layer_primitives(state, content):
    assert (is_known(state, content, "town"), is_known(state, content, "lake"), is_known(state, content, "cave")) == (
        True, True, False,
    )
    content.config.vision_base = 0
    assert is_known(state, content, "lake") is False
    state.player.visited.add("lake")
    assert is_known(state, content, "lake") is True  # 去過的記得


def test_detail_lists_situation_enemies_story_and_route(state, content):
    state.world.rumors.append(Rumor(time=0, text="翻江龍又劫了一艘船。", location="lake"))
    text = detail_text(state, content, "lake", {"thug": "穩勝"}.get)
    assert text.startswith("### 湖邊　危險 ★★")
    assert "**局勢**　測試北區（寇亂 30）\n" in text and "**龍頭人物**　翻江龍（常出沒在此）" in text
    assert "**敵情**　水寇小隊 穩勝" in text
    assert "★ 這一幕主線的目標：壓制寇亂" in text
    assert "✦ 最近 3 天的大事與傳聞：\n- 第1天 00:00　翻江龍又劫了一艘船。" in text
    assert text.endswith("**路線**　步行約 3 分鐘、趕路約 2 分鐘・體力 3、疾行立刻到・體力 6")
    here = detail_text(state, content, "town", no_odds)  # 沒有敵人：不算勝算
    assert here.startswith("### 小鎮（所在地）　危險 ★")
    assert "沒有龍頭人物在此出沒" in here and "沒有人在這裡滋事" in here
    assert "不是這一幕主線的目標" in here and "最近 3 天沒有大事或傳聞" in here
    assert here.endswith("**路線**　你就在這裡")


LEADER_WHO = "江湖上的龍頭人物，會自己行動，左右江湖大勢"


def lake_detail(state, content) -> str:
    return detail_text(state, content, "lake", {"thug": "穩勝"}.get)


def test_detail_explains_who_a_haunting_leader_is_and_what_he_is_doing(state, content):
    text = lake_detail(state, content)
    assert "**龍頭人物**　翻江龍（常出沒在此）\n" in text
    assert f"- {LEADER_WHO}。" in text
    assert "- 現在：每天約出手 24 次，讓寇亂上升。" in text
    assert "常出沒：" not in text and text.count("翻江龍") == 1  # 常出沒的資訊併進這一塊，不說兩次
    assert "最近：" not in text  # 沒有傳聞：不寫最近


def test_detail_says_which_way_each_visible_trend_moves(state, content):
    boss = content.scenario.sim_players[0]
    boss.actions_per_day = 2.5
    boss.trend = {"kou": -2}
    assert "- 現在：每天約出手 2.5 次，讓寇亂下降。" in lake_detail(state, content)
    state.world.revealed.add("bao")
    boss.trend = {"kou": -1, "bao": 1}
    assert "- 現在：每天約出手 2.5 次，讓寶藏上升，讓寇亂下降。" in lake_detail(state, content)
    boss.trend = {"kou": 1, "bao": 1}
    assert "- 現在：每天約出手 2.5 次，讓寇亂、寶藏上升。" in lake_detail(state, content)


def test_detail_never_names_a_hidden_trend_the_leader_pushes(state, content):
    boss = content.scenario.sim_players[0]
    boss.trend = {"kou": 1, "bao": 3}  # 寶藏線還沒浮現：世界模擬不動它，詳情也不能提
    text = lake_detail(state, content)
    assert "- 現在：每天約出手 24 次，讓寇亂上升。" in text and "寶藏" not in text
    boss.trend = {"bao": 3}
    text = lake_detail(state, content)
    assert "- 現在：每天約出手 24 次。" in text and "寶藏" not in text


def test_detail_shows_the_quiet_phrase_when_no_entry_of_his_is_active(state, content):
    boss = content.scenario.sim_players[0]
    boss.condition.world_flags_none.append("fjl_defeated")
    assert "- 現在：每天約出手" in lake_detail(state, content)
    state.world.flags.add("fjl_defeated")
    text = lake_detail(state, content)
    assert "- 現在：眼下沒有動靜。" in text and "每天約出手" not in text and "- 江湖上的龍頭人物" in text  # 還是龍頭人物、還在此出沒


def test_detail_describes_the_entry_that_is_active_now(state, content):
    boss = content.scenario.sim_players[0]
    boss.condition.world_flags_none.append("cave_open")
    content.scenario.sim_players.append(SimPlayer(
        name="翻江龍", actions_per_day=6, trend={"kou": -1}, haunts=["lake"], condition=Condition(world_flags_all=["cave_open"]),
    ))
    assert "- 現在：每天約出手 24 次，讓寇亂上升。" in lake_detail(state, content)
    state.world.flags.add("cave_open")
    text = lake_detail(state, content)
    assert "- 現在：每天約出手 6 次，讓寇亂下降。" in text and "每天約出手 24" not in text
    assert text.count("**龍頭人物**") == 1  # 同一個人只說一次


def test_detail_lists_the_two_newest_rumors_that_mention_him(state, content):
    rumors = state.world.rumors
    rumors.append(Rumor(time=0, text="翻江龍在湖上放話。", location="lake"))
    rumors.append(Rumor(time=1 * DAY, text="鬼手在挖土。", location="cave"))  # 沒提到他
    rumors.append(Rumor(time=2 * DAY + 3600, text="翻江龍又劫了一艘船。", location="lake"))
    rumors.append(Rumor(time=3 * DAY + 7200, text="有人說翻江龍去了別處。", location="town"))
    rumors.append(Rumor(time=4 * DAY, text="翻江龍的老巢被圍了。"))  # 沒有地點也算
    text = lake_detail(state, content)
    assert "- 最近：\n  - 第5天 00:00　翻江龍的老巢被圍了。\n  - 第4天 02:00　有人說翻江龍去了別處。\n" in text
    assert "放話" not in text.split("**敵情**")[0]  # 最多兩則：更舊的不列
    assert "鬼手在挖土" not in text.split("**敵情**")[0]
    rumors.pop()
    rumors.pop()
    assert "- 最近：\n  - 第3天 01:00　翻江龍又劫了一艘船。\n  - 第1天 00:00　翻江龍在湖上放話。\n" in lake_detail(state, content)


def test_detail_waits_for_the_hidden_trend_before_describing_a_leader(state, content):
    state.world.flags.add("cave_open")
    state.player.location = "lake"  # 寶洞在視野內
    assert "鬼手" not in detail_text(state, content, "cave", no_odds)
    assert "寶藏" not in detail_text(state, content, "cave", no_odds)
    state.world.revealed.add("bao")
    text = detail_text(state, content, "cave", no_odds)
    assert "**龍頭人物**　鬼手（常出沒在此）" in text and "- 現在：每天約出手 24 次，讓寶藏上升。" in text


def test_detail_of_a_scouted_place_says_which_insights_can_be_gained_there(state, content):
    """W3：摸清的地點，詳情欄寫「這裡能悟：…」——名字讀自探索自己用的那個判斷（insights.explore_gives）。句子待 joy 潤。"""
    text = detail_text(state, content, "lake", {"thug": "穩勝"}.get)
    assert "**意境**　這裡能悟：水、風" in text  # 內容寫的順序（fixture 的湖邊是 shui、feng）
    assert text.index("**敵情**") < text.index("**意境**") < text.index("**劇情**")
    content.locations["lake"].insights = ["huo"]
    assert "**意境**　這裡能悟：火\n" in detail_text(state, content, "lake", {"thug": "穩勝"}.get)


def test_detail_says_nothing_about_insights_where_exploring_gives_none(state, content):
    from tianxia.models import ExploreMix

    content.config.explore_mix = [ExploreMix(kind="wild", tags=[], weights={"insight": 0, "event": 1})]
    assert "這裡能悟" not in detail_text(state, content, "lake", {"thug": "穩勝"}.get)
    content.config.explore_mix = [ExploreMix(kind="wild", tags=[], weights={"insight": 1})]
    content.locations["lake"].insights = []  # 地點沒寫：探索給靠探索悟的四個基本意境，這裡就照實寫四個
    assert "這裡能悟：風、火、水、山" in detail_text(state, content, "lake", {"thug": "穩勝"}.get)


def test_an_unscouted_place_lists_no_insights(state, content):
    content.config.vision_base = 0
    content.locations["lake"].important = True
    assert detail_text(state, content, "lake", no_odds) == "### 湖邊？\n\n尚未摸清"  # 沒摸清：連「這裡能悟」也不露
    state.player.visited.add("lake")
    assert "這裡能悟：水、風" in detail_text(state, content, "lake", {"thug": "穩勝"}.get)  # 去過了才寫


def test_the_insights_the_map_promises_are_exactly_what_exploring_teaches(game):
    """「這裡能悟」永遠不會說探索給不出的東西，也不漏掉探索給得出的：把探索的比例逼成只悟意境，探很多次，悟到的就是詳情欄寫的那幾個。"""
    from tianxia.models import ExploreMix

    c, p = game.content, game.state.player
    c.config.explore_mix = [ExploreMix(kind="wild", tags=[], weights={"insight": 1})]
    c.config.rare_explore_chance = 0.0
    p.location = "lake"
    text = detail_text(game.state, c, "lake", {"thug": "穩勝"}.get)
    listed = text.split("這裡能悟：")[1].split("\n")[0].split("、")
    for _ in range(80):
        game._explore()
    learned = [c.insights[i].name for i in p.insights]
    assert sorted(learned) == sorted(listed) == ["水", "風"]


def test_detail_of_an_unknown_place_still_says_nothing_about_leaders(state, content):
    content.config.vision_base = 0
    content.locations["lake"].important = True
    state.world.rumors.append(Rumor(time=0, text="翻江龍又劫了一艘船。", location="lake"))
    text = detail_text(state, content, "lake", no_odds)
    assert text == "### 湖邊？\n\n尚未摸清" and "翻江龍" not in text


def test_detail_names_the_places_on_the_way(state, content):
    state.world.flags.add("cave_open")
    assert detail_text(state, content, "cave", no_odds).endswith(
        "**路線**　步行約 8 分鐘、趕路約 4 分鐘・體力 8、疾行立刻到・體力 15，途經 湖邊"
    )


def test_game_map_helpers(game):
    assert game.MAP_LAYERS == {"situation": "局勢", "enemies": "敵情", "story": "劇情", "routes": "路線"}
    assert game.map_header() == "⏳ 第1天 00:00　**體力** 150 / 150"
    assert game.map_places() == [("小鎮（所在地）", "town"), ("湖邊", "lake")]
    assert "**敵情**　水寇小隊" in game.place_detail("lake")  # 用 Game.odds；具體勝算數字待平衡調整
    assert game.travel_options("lake")[0] == TravelOption("walk", "步行（約 3 分鐘）", True)


def test_picking_whom_to_call_on_blocks_travel(state, content):
    state.player.picking_audience = True
    assert travel_options(state, content, "lake") == [TravelOption("walk", "求見中，先返回才能安排前往", False, to_jianghu=True)]
    assert travel_refusal(state, content, "lake", "walk") == "求見中，先返回才能安排前往"


# ── 路上（路上設計第二、三節）──────────────────────────────


def _on_the_road(state, at=60.0):
    """從小鎮步行往湖邊（夾具 3 分鐘＝180 秒），現在是第 at 秒。"""
    state.player.journey = Journey(mode="walk", path=["lake"], arrive_at=[180.0])
    state.world.time = at


def test_the_road_spot_is_two_stops_and_how_far_along(state, content):
    assert road_spot(state, content) is None  # 人在某一站
    _on_the_road(state)
    spot = road_spot(state, content)
    assert (spot.behind, spot.ahead, spot.minutes) == ("town", "lake", pytest.approx(3.0))
    assert spot.done == pytest.approx(1 / 3)
    state.player.journey = Journey(mode="walk", path=["town"], arrive_at=[120.0], origin="lake", share=2 / 3)
    spot = road_spot(state, content)  # 掉頭回小鎮：身後是湖邊，在湖邊往小鎮的三分之二處
    assert (spot.behind, spot.ahead, spot.done) == ("lake", "town", pytest.approx(2 / 3))


def test_on_the_road_no_place_is_where_you_are(state, content):
    _on_the_road(state)
    assert views(state, content)["town"] == "visible"
    assert place_choices(state, content) == [("小鎮", "town"), ("湖邊", "lake")]


def test_on_the_road_you_can_arrange_travel_from_where_you_are(state, content):
    _on_the_road(state)
    assert travel_block(state, content) is None
    assert way_to(state, content, "town") == Route(("town",), (pytest.approx(1.0),), origin="lake", share=pytest.approx(2 / 3))
    assert travel_options(state, content, "town") == [  # 剛離開的那一站：就是折返
        TravelOption("walk", "步行（約 1 分鐘）", True),
        TravelOption("hurry", "趕路（約 1 分鐘・體力 1）", True),
        TravelOption("dash", "疾行（立刻到・體力 2）", True),
    ]
    assert travel_options(state, content, "lake")[0] == TravelOption("walk", "步行（約 2 分鐘）", True)
    assert travel_refusal(state, content, "town", "walk") is None
    detail = detail_text(state, content, "town", no_odds)
    assert detail.startswith("### 小鎮　") and "**路線**　步行約 1 分鐘" in detail  # 在路上沒有所在地
