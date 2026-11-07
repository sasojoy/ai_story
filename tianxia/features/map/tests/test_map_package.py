"""輿圖包的接縫（全部拆包第 49 批）：殼留的是同一個物件、三條路由掛上了、
搬到核心服務檔的小函式兩邊是同一個物件。行為本身（畫法、資料、疊層）由同一個資料夾裡搬進來的整檔測試守。"""
import server
from tianxia.features.map import mapdata
from tianxia.core import explore_base
from tianxia.features.explore import explore_rules
from tianxia.features.map import views
from tianxia.features.sense import sensing


def test_the_shell_keeps_the_same_cache_and_the_same_default_layer():
    assert server.MAP_BASE is views.MAP_BASE
    assert server.MAP_BASE_KEEP == views.MAP_BASE_KEEP
    assert server.map_base_view is views.map_base_view
    assert server.DEFAULT_LAYER == views.DEFAULT_LAYER


def test_the_three_map_routes_are_mounted_by_the_package():
    paths = server.app.openapi()["paths"]
    assert {"/api/map", "/api/map/base", "/api/map/state"} <= set(paths)
    assert all(list(paths[p]) == ["get"] for p in ("/api/map", "/api/map/base", "/api/map/state"))


def test_the_helpers_moved_to_the_core_service_file_are_the_same_objects():
    assert mapdata.LOSE_WORD == explore_base.LOSE_WORD == "必敗"
    assert explore_rules.kind_of is explore_base.kind_of and explore_rules.hint_in is explore_base.hint_in
    assert explore_rules.mostly_in is explore_base.mostly_in and explore_rules.KINDS is explore_base.KINDS
    assert sensing.terrain_tags is explore_base.terrain_tags
