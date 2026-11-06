"""map 這一包的測試，從 tests/server/test_server.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import pytest
import server
from tianxia import insights
from tianxia.characters import open_characters
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, _player, cheap_password_hashing, client, fresh_server_memory, game,
    model_breaker_closed, save_dir, scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content


def test_map_view_gives_the_legend_as_data_for_the_layer_shown(game):
    """圖例不畫進 SVG（企劃者 10/4：放大時也要看得到）：跟 svg 並排給網頁，由網頁疊在地圖框角落。
    送的是正在看的那一層的說明（認不得的圖層退回預設那一層），不是四層全給。"""
    from tianxia import mapview

    legend = server.look(game, lambda g: server.map_view(g, "enemies", None))["legend"]
    assert legend["layer"] == mapview.LEGEND_LAYERS["enemies"] and len(legend["icons"]) == 6
    assert all(item["svg"].startswith("<svg") and item["label"] for item in legend["icons"])
    # 不帶設定的正式內容沒有第一季規則、沒有地盤與出陣：⚔ 那一句是遊歷的說法（出陣開著是 LEGEND_RING_SORTIE，見 tests/test_mapview.py）
    assert legend["states"] == mapview.LEGEND_STATES and legend["ring"] == mapview.LEGEND_RING and legend["strike"] == ""
    fallback = server.look(game, lambda g: server.map_view(g, "沒這層", None))["legend"]
    # 預設那一層是局勢層：沒有地盤，不多那一句誰佔著（地盤開著才有，出陣探索與地盤設計 4.3）
    assert fallback["layer"] == mapview.LEGEND_LAYERS[server.DEFAULT_LAYER]


def test_reports_and_map_pages_read_without_saving(client, save_dir):
    _player(client)
    with open_characters().db.transaction() as conn:
        conn.execute("DELETE FROM characters")
    assert client.get("/api/reports").json()["list"] == []
    assert client.get("/api/map?layer=enemy").json()["layer"] in {"enemy", server.DEFAULT_LAYER}
    assert client.get("/api/map/base").json()["places"] and client.get("/api/map/state").json()["places"]
    assert not open_characters().exists("沈青衫")


def test_the_new_map_comes_as_a_base_and_an_overlay(client):
    """輿圖升級（設計第九節）：底圖（svg、地點、路、大區）與疊層（每個地點此刻的樣子）分兩個端點，兩個都只讀。"""
    _player(client)
    base = client.get("/api/map/base").json()
    assert base["svg"].startswith("<svg") and base["places"] and base["edges"] and base["key"]
    st = client.get("/api/map/state").json()
    assert st["key"] == base["key"] and st["here"] in st["places"]


def test_the_map_base_is_cached_until_a_place_opens(client):
    from tianxia import mapdata

    _player(client)
    game = server.game_for("沈青衫")
    first = server.look(game, server.map_base_view)
    assert server.look(game, server.map_base_view) is first  # 同一把鍵：同一份，不重畫
    game.state.world.flags.add("xi_open")  # 南華觀開放（14 天的季要等這面旗）
    second = server.map_base_view(game)
    assert second["key"] != first["key"] and second["key"] == mapdata.base_key(game.state, game.content)
    assert "jade_cave" in {p["id"] for p in second["places"]}


def test_the_map_detail_says_which_insights_a_scouted_place_teaches(client):
    """W3：輿圖點一個摸清的地點，詳情欄多一行「這裡能悟：…」，名字就是探索那裡悟得到的。"""
    _player(client)
    start = server.game_for("沈青衫").state.player.location
    detail = client.get(f"/api/map?place={start}").json()["detail"]
    names = "、".join(server.CONTENT.insights[i].name for i in insights.explore_gives(server.CONTENT.locations[start], server.CONTENT))
    assert f"這裡能悟：{names}" in detail
