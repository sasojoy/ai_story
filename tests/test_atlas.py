from tianxia.atlas import (
    Route, detail_text, direction, foes, goal_places, haunters, is_known, known_locations, neighbours, place_choices,
    recent_news, region_center, region_of, region_trends, routes, travel_button, worst_foe,
)
from tianxia.models import Location
from tianxia.state import Rumor

DAY = 86400


def region(content, region_id):
    return next(r for r in content.map.regions if r.id == region_id)


def add_hill(content, cost: int) -> None:
    """夾具只有一條線（小鎮—湖邊—寶洞）；加一座山丘，讓小鎮到寶洞多一條路。"""
    content.locations["hill"] = Location(
        id="hill", name="山丘", description="小山丘。", connections=["town", "cave"], x=150, y=50, move_cost=cost
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


def test_region_center_and_direction(content):
    assert region_center(region(content, "north")) == (200, 75)
    assert [direction((0, 0), end) for end in ((9, 0), (9, 9), (0, 9), (-9, 9), (-9, 0), (-9, -9), (0, -9), (9, -9))] == [
        "→", "↘", "↓", "↙", "←", "↖", "↑", "↗",
    ]


def test_neighbours_are_regions_joined_by_open_roads(state, content):
    north, south = region(content, "north"), region(content, "south")
    assert neighbours(state, content, north) == []  # 夾具的地點都在北區
    content.locations["cave"].y = 170  # 寶洞移到南區，但還沒開放
    assert neighbours(state, content, north) == []
    state.world.flags.add("cave_open")
    assert neighbours(state, content, north) == [("↓", south)]
    assert neighbours(state, content, south) == [("↑", north)]


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


def test_recent_news_keeps_the_last_three_days(state, content):
    rumors = state.world.rumors
    rumors.append(Rumor(time=0.5 * DAY, text="太舊了", location="lake"))
    rumors.append(Rumor(time=1.5 * DAY, text="三天內", location="lake"))
    rumors.append(Rumor(time=2 * DAY, text="別處", location="town"))
    rumors.append(Rumor(time=3 * DAY, text="沒有地點"))
    rumors.append(Rumor(time=4 * DAY, text="剛剛", location="lake"))
    state.world.time = 4.5 * DAY
    assert [r.text for r in recent_news(state, "lake")] == ["剛剛", "三天內"]


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


# ── 路線 ──────────────────────────────────────────────


def test_routes_take_the_cheapest_way(state, content):
    add_hill(content, cost=9)
    state.world.flags.add("cave_open")
    found = routes(state, content)
    assert found["town"] == Route((), 0)
    assert found["cave"] == Route(("lake", "cave"), 10)
    assert found["cave"].via == ("lake",)
    content.locations["lake"].move_cost = 12
    assert routes(state, content)["cave"] == Route(("hill", "cave"), 14)


def test_routes_only_pass_known_and_open_places(state, content):
    assert "cave" not in routes(state, content)  # 未開放
    content.config.vision_base = 0
    assert routes(state, content) == {"town": Route((), 0)}  # 湖邊沒摸清
    state.player.visited.add("lake")
    assert routes(state, content)["lake"] == Route(("lake",), 5)
    add_hill(content, cost=1)  # 更省，但山丘沒摸清
    content.locations["lake"].move_cost = 12
    state.world.flags.add("cave_open")
    state.player.visited.add("cave")
    assert routes(state, content)["cave"] == Route(("lake", "cave"), 17)


def add_place(content, loc_id: str, cost: int, links: list[str]) -> None:
    content.locations[loc_id] = Location(
        id=loc_id, name=loc_id, description="測試地點。", connections=list(links), x=150, y=50, move_cost=cost
    )
    for other in links:
        content.locations[other].connections.append(loc_id)


def test_routes_break_ties_by_fewer_hops_then_by_id(state, content):
    state.world.flags.add("cave_open")
    content.config.vision_base = 3
    content.locations["lake"].move_cost = 6
    content.locations["cave"].move_cost = 5
    add_place(content, "aa", cost=3, links=["town"])  # 另一條路：小鎮—aa—ab—寶洞，同樣 11 體力，但多一站
    add_place(content, "ab", cost=3, links=["aa", "cave"])
    found = routes(state, content)["cave"]
    assert found == Route(("lake", "cave"), 11)  # 一樣省時站數少的贏，即使另一條路的地點 id 排在前面

    content.locations["lake"].move_cost = 5
    add_place(content, "hill", cost=5, links=["town", "cave"])  # 湖邊與山丘一樣 10 體力、一樣兩站
    assert routes(state, content)["cave"] == Route(("hill", "cave"), 10)  # 再一樣時比地點 id：hill 在 lake 前面
    for loc in content.locations.values():
        loc.connections.reverse()
    assert routes(state, content)["cave"] == Route(("hill", "cave"), 10)  # 和連線寫的順序無關


# ── 安排前往 ──────────────────────────────────────────


def test_travel_button_shows_cost_or_reason(state, content):
    assert travel_button(state, content, "town") is None  # 所在地
    assert travel_button(state, content, "cave") is None  # 未開放
    assert travel_button(state, content, "lake") == ("安排前往（約 5 體力）", True)
    state.player.stamina = 3
    assert travel_button(state, content, "lake") == ("體力不足，第一站要 5 體力", False)
    state.player.stamina = 150
    state.pending_event = "drunk"
    assert travel_button(state, content, "lake") == ("有事件待處理，不能安排前往", False)
    state.pending_event = None
    state.player.busy_until = 3600
    assert travel_button(state, content, "lake") == ("閉關中，不能安排前往", False)
    state.player.busy_until = None
    state.world.ended = True
    assert travel_button(state, content, "lake") == ("賽季已結束，不能安排前往", False)
    state.world.ended = False
    content.config.vision_base = 0
    assert travel_button(state, content, "lake") is None  # 沒摸清


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
    assert "**局勢**　測試北區（寇亂 30）　｜　常出沒：翻江龍" in text
    assert "**敵情**　水寇小隊 穩勝" in text
    assert "★ 這一幕主線的目標：壓制寇亂" in text
    assert "✦ 最近 3 天的大事與傳聞：\n- 第1天 00:00　翻江龍又劫了一艘船。" in text
    assert text.endswith("**路線**　約 5 體力")
    here = detail_text(state, content, "town", no_odds)  # 沒有敵人：不算勝算
    assert here.startswith("### 小鎮（所在地）　危險 ★")
    assert "沒有龍頭人物在此出沒" in here and "沒有人在這裡滋事" in here
    assert "不是這一幕主線的目標" in here and "最近 3 天沒有大事或傳聞" in here
    assert here.endswith("**路線**　你就在這裡")


def test_detail_names_the_places_on_the_way(state, content):
    state.world.flags.add("cave_open")
    assert detail_text(state, content, "cave", no_odds).endswith("**路線**　約 10 體力，途經 湖邊")


def test_game_map_helpers(game):
    assert game.MAP_LAYERS == {"situation": "局勢", "enemies": "敵情", "story": "劇情", "routes": "路線"}
    assert game.map_header() == "⏳ 第1天 00:00　**體力** 150 / 150"
    assert game.map_places() == [("小鎮（所在地）", "town"), ("湖邊", "lake")]
    assert "**敵情**　水寇小隊 穩勝" in game.place_detail("lake")  # 用 Game.odds（有快取）
    assert game.travel_button("lake") == ("安排前往（約 5 體力）", True)
