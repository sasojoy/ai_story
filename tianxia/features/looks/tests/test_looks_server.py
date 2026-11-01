"""自建形象與招式動畫的伺服器那一側：下單走 /api/looks/order、/api/looks/move（同一個編號送兩次只扣一次）、圖從資料庫旁邊的 looks/ 送（只認 u<數字> 配十張、m<數字> 配 fx 與 art1、art2）。"""
from __future__ import annotations

from pathlib import Path

from test_mall_server import _player, fresh_server  # noqa: F401  fresh_server 是 autouse 的 fixture

from tianxia.database import default_path
from tianxia.features.looks import actions, orders

ART = Path(__file__).resolve().parents[4] / "web/img/looks/moying"


def test_order_over_the_api_charges_once_and_shows_up():
    client = _player()
    client.get("/api/main")
    body = {"name": "白衣書生", "prompt": "白衣書生，背著竹簍", "ref": "web-order-0001"}
    first = client.post("/api/looks/order", json=body).json()
    again = client.post("/api/looks/order", json=body).json()
    assert "下單了" in first["message"] and "已經下過單" in again["message"]
    assert first["looks"]["order"]["list"][0]["status"] == orders.PENDING
    assert first["main"]["mall"]["balance"] == 5000 - 900


def test_custom_images_are_served_from_beside_the_database():
    client = _player()
    root = actions.images_beside(default_path())
    orders.save_sheet(root, "u7", "hero_bare_idle", (ART / "hero_bare_idle.webp").read_bytes())
    got = client.get("/api/looks/img/u7/hero_bare_idle")
    assert got.status_code == 200 and got.headers["content-type"] == "image/webp"
    assert client.get("/api/looks/img/u7/hero_bare_hit").status_code == 404
    assert client.get("/api/looks/img/moying/hero_bare_idle").status_code == 404
    assert client.get("/api/looks/img/u7/..%2Fsecret").status_code == 404


def test_move_effects_are_served_as_fx_only():
    """招式動畫（第三批）：m<數字> 只送 fx 那一張；u<數字> 不送 fx。"""
    client = _player()
    root = actions.images_beside(default_path())
    orders.save_sheet(root, "m9", "fx", actions.FX_SAMPLE.read_bytes())
    assert client.get("/api/looks/img/m9/fx").status_code == 200
    assert client.get("/api/looks/img/m9/hero_bare_idle").status_code == 404
    assert client.get("/api/looks/img/u9/fx").status_code == 404
    orders.save_sheet(root, "m9", "art1", actions.FX_SAMPLE.read_bytes())
    assert client.get("/api/looks/img/m9/art1").status_code == 200  # 一句話自創要畫的那幾張（法相、巨物）
    assert client.get("/api/looks/img/m9/art3").status_code == 404


def test_the_scene_preview_charges_nothing_and_unknown_scenes_404():
    """一句話自創（Joy 2026-11-01）：/api/looks/scene 回導演稿或不行的那一句，不扣元寶；沒上架的招沒有稿。"""
    client = _player()
    client.get("/api/main")
    got = client.post("/api/looks/scene", json={"text": "背後出現一座大佛擊出一掌"}).json()
    assert [a["label"] for a in got["scene"]["arts"]] == ["大佛", "佛掌"]
    assert client.post("/api/looks/scene", json={"text": "fire"}).json() == {"problem": "只能寫中文。"}
    assert client.get("/api/looks/scene/m424242").status_code == 404
    assert client.get("/api/looks/scene/u1").status_code == 404
    assert client.get("/api/main").json()["mall"]["balance"] == 5000


def test_move_order_without_an_own_art_is_refused_and_charges_nothing():
    client = _player()
    client.get("/api/main")
    got = client.post("/api/looks/move", json={"prompt": "劍氣", "ref": "web-move-0001"}).json()
    assert "先練一門自己合成或自創的武功" in got["message"] and got["main"]["mall"]["balance"] == 5000


def test_the_market_endpoint_refuses_a_look_you_did_not_make():
    client = _player()
    client.get("/api/main")
    got = client.post("/api/looks/market", json={"op": "list", "look": "u3", "price": 600}).json()
    assert "不是你做的" in got["message"]
    assert client.post("/api/looks/market", json={"op": "sell"}).status_code == 400
