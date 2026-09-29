from tianxia.atlas import location_view, vision_range, visible_locations
from tianxia.mapview import node_shape, render_map, text_width


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
    svg = render_map(state, content)
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
