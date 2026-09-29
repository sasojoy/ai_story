from tianxia.atlas import location_view, vision_range, visible_locations
from tianxia.mapview import (
    LEGEND_LAYERS, NODE_FILL, ROUTE_STROKE, SELECT_STROKE, node_shape, render_map, render_minimap, text_width,
)
from tianxia.state import Rumor


def no_odds(squad_id: str) -> str:
    raise AssertionError(f"不該算勝算：{squad_id}")


def test_vision_range_grows_with_fame(state, content):
    assert vision_range(state, content) == 2
    state.player.stats["fame"] = 10
    assert vision_range(state, content) == 3


def test_vision_range_grows_with_trained_vision_skill(state, content):
    from tianxia.rules import learn_skill

    learn_skill(state, content, "step")
    assert vision_range(state, content) == 2
    state.player.skills["step"] = 5
    assert vision_range(state, content) == 3


def test_visible_locations_skip_locked(state, content):
    assert visible_locations(state, content) == {"town", "lake"}
    state.world.flags.add("cave_open")
    assert visible_locations(state, content) == {"town", "lake", "cave"}


def test_location_views(state, content):
    content.config.vision_base = 0
    visible = visible_locations(state, content)
    assert location_view("town", state, content, visible) == "current"
    assert location_view("lake", state, content, visible) == "dot"
    assert location_view("cave", state, content, visible) == "hidden"
    content.locations["lake"].important = True
    assert location_view("lake", state, content, visible) == "outline"
    state.player.visited.add("lake")
    assert location_view("lake", state, content, visible) == "remembered"
    content.config.vision_base = 1
    assert location_view("lake", state, content, visible_locations(state, content)) == "visible"


def test_render_map(state, content):
    svg = render_map(state, content)
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "小鎮" in svg and "湖邊" in svg and "測試區" in svg
    assert "寶洞" not in svg  # 尚未解鎖
    content.config.vision_base = 0
    content.locations["lake"].important = True
    assert "湖邊？" in render_map(state, content)


def test_node_shapes_follow_tags(content):
    assert node_shape(content.locations["town"]) == "town"
    assert node_shape(content.locations["lake"]) == "wild"
    content.locations["lake"].tags.append("門派")
    assert node_shape(content.locations["lake"]) == "sect"


def test_text_width():
    assert text_width("湖邊", 10) == 20
    assert text_width("ab", 10) == 12


def test_render_map_new_look(state, content):
    svg = render_map(state, content, "routes")  # 路線層的大區保持原色
    assert 'fill="#F6F1E4"' in svg  # 固定淺色底
    assert "測試北區" in svg and 'fill="#EFE5CB"' in svg  # 區域
    assert 'stroke="#BA7517"' in svg  # 湖邊危險 2 → 橙色外圈
    assert "湖邊 ⚔" in svg and "★" not in svg
    assert "paint-order:stroke" in svg
    assert "<rect" in svg  # 小鎮（城鎮）畫成方塊


def test_label_flips_left_near_right_edge(state, content):
    content.locations["lake"].x = 390
    assert 'text-anchor="end"' in render_map(state, content)


def test_legend_sits_at_the_bottom(state, content):
    svg = render_map(state, content)
    assert f'<rect x="8" y="{content.map.height - 50}"' in svg


def test_remembered_color_is_distinct_from_visible(state, content):
    from tianxia.mapview import NODE_FILL

    assert NODE_FILL["remembered"] == "#7F77DD"  # 紫色，和看得見的綠色明顯不同
    content.config.vision_base = 0
    state.player.visited.add("lake")
    assert 'fill="#7F77DD"' in render_map(state, content)


# ── 大地圖的圖層 ─────────────────────────────────────


def test_every_layer_has_its_own_legend(state, content):
    for layer, line in LEGEND_LAYERS.items():
        svg = render_map(state, content, layer, odds={"thug": "穩勝"}.get)
        assert line in svg and "外圈：綠安全／橙危險／紅兇險" in svg and "■ 城鎮" in svg
        assert all(other not in svg for other in LEGEND_LAYERS.values() if other != line)


def test_situation_layer_tints_regions_and_flags_haunts(state, content):
    svg = render_map(state, content)
    assert 'fill="#E7C6AE"' in svg and 'fill="#EFE5CB"' not in svg  # 北區依寇亂 30 往紅色靠
    assert 'fill="#E2EAF1"' in svg  # 南區的寶藏線還沒浮現：原色
    assert ">寇亂 30<" in svg and "寶藏" not in svg
    assert "⚑ 翻江龍 常出沒" in svg
    state.world.trends["kou"] = 90
    assert 'fill="#D68875"' in render_map(state, content)  # 越凶越紅


def test_enemies_layer_colours_by_danger_and_names_the_worst_foe(state, content):
    svg = render_map(state, content, "enemies", odds={"thug": "穩勝"}.get)
    assert "最險：水寇小隊 穩勝" in svg
    assert f'r="8" fill="{NODE_FILL["visible"]}"' not in svg  # 湖邊改用危險度的顏色
    assert 'fill="#BA7517" stroke="#BA7517"' in svg
    bare = render_map(state, content, "enemies").replace(LEGEND_LAYERS["enemies"], "")
    assert "最險" not in bare  # 沒給 odds：不寫、也不算


def test_story_layer_marks_goals_and_recent_news(state, content):
    svg = render_map(state, content, "story")
    assert "★ 湖邊 ⚔" in svg and "✦" not in svg.replace(LEGEND_LAYERS["story"], "")
    state.world.rumors.append(Rumor(time=0, text="小鎮出事了。", location="town"))
    assert "✦ 小鎮（你）" in render_map(state, content, "story")


def test_routes_layer_shows_costs_and_the_selected_path(state, content):
    state.world.flags.add("cave_open")
    svg = render_map(state, content, "routes", selected="cave")
    assert ">所在地<" in svg and ">5 體力<" in svg and ">10 體力<" in svg
    assert f'<polyline points="100,100 200,100 300,100" fill="none" stroke="{ROUTE_STROKE}"' in svg
    assert ROUTE_STROKE + '" stroke-width="5"' not in render_map(state, content, "routes", selected="town")


def test_selected_place_is_outlined_and_places_are_clickable(state, content):
    svg = render_map(state, content, selected="lake")
    assert f'r="18" fill="none" stroke="{SELECT_STROKE}" stroke-width="3"' in svg  # 湖邊 8 ＋ 10
    assert svg.count('<g data-loc="town"') == 1 and svg.count('<g data-loc="lake"') == 1
    assert 'data-loc="cave"' not in svg  # 未開放：不畫
    content.config.vision_base = 0
    assert 'data-loc="lake"' not in render_map(state, content)  # 沒名字的淡點點不到
    content.locations["lake"].important = True
    assert '<g data-loc="lake"' in render_map(state, content)  # 畫出「湖邊？」的輪廓可以點


def test_unknown_places_show_only_outline_and_question_mark(state, content):
    content.config.vision_base = 0
    content.locations["lake"].important = True
    state.world.rumors.append(Rumor(time=0, text="湖邊出事了。", location="lake"))
    for layer in LEGEND_LAYERS:
        svg = render_map(state, content, layer, odds=no_odds).replace(LEGEND_LAYERS[layer], "")
        assert "湖邊？" in svg
        assert all(mark not in svg for mark in ("★", "✦", "⚑", "最險", "5 體力", "湖邊 ⚔"))


# ── 場景小地圖 ─────────────────────────────────────


def test_minimap_draws_only_the_current_region(state, content):
    svg = render_minimap(state, content)
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert svg.count("<polygon") == 1 and 'fill="#EFE5CB"' in svg and 'fill="#E2EAF1"' not in svg
    assert ">小鎮<" in svg and "湖邊" not in svg  # 只有所在地與重要地點寫名字
    assert f'r="10" fill="none" stroke="{NODE_FILL["current"]}"' in svg  # 所在地的醒目記號
    assert all(mark not in svg for mark in ("<line", "體力", "★", "⚔", "寇亂"))  # 不畫路、不放數字
    content.locations["lake"].important = True
    assert ">湖邊<" in render_minimap(state, content)


def test_minimap_points_to_neighbouring_regions(state, content):
    assert "↓" not in render_minimap(state, content)  # 還沒有路通到南區
    content.locations["cave"].y = 170
    state.world.flags.add("cave_open")
    assert ">↓ 測試南區<" in render_minimap(state, content)
    state.player.location = "cave"
    svg = render_minimap(state, content)
    assert 'fill="#E2EAF1"' in svg and ">↑ 測試北區<" in svg and ">寶洞<" in svg


def test_minimap_keeps_showing_the_player_during_an_event(state, content):
    state.pending_event = "drunk"
    assert f'r="5" fill="{NODE_FILL["current"]}"' in render_minimap(state, content)


def test_minimap_without_regions_is_empty(state, content):
    content.map.regions = []
    assert render_minimap(state, content) == ""
