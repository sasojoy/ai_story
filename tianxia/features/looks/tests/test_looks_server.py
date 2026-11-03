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
    # 圖換了網址不會換（上架之後還會 refit、重畫、退回重來），所以不能讓瀏覽器釘死：
    # 每次都要回來問，靠 ETag 省流量（照 server.NO_CACHE 那條家規）。2026-11-02 之前寫 max-age=86400，
    # 把十張 refit 回標準身高之後畫面上還是舊的大號身體。
    assert got.headers["cache-control"] == "no-cache"
    assert got.headers.get("etag"), "要有 ETag，不然每次都得重傳整張"
    again = client.get("/api/looks/img/u7/hero_bare_idle", headers={"If-None-Match": got.headers["etag"]})
    assert again.status_code == 304, "沒換就回 304"
    assert client.get("/api/looks/img/u7/hero_bare_hit").status_code == 404
    assert client.get("/api/looks/img/moying/hero_bare_idle").status_code == 404
    assert client.get("/api/looks/img/u7/..%2Fsecret").status_code == 404


def test_main_sends_a_version_for_the_custom_images_so_phones_see_new_art():
    """main.looks_ver：網頁把它接在圖網址後面當 ?v=（同 server.versioned_page 對自家檔案那一套）。
    圖換了版本就換，之前快取過舊圖的手機也會抓到新的（Joy 2026-11-02「我手機現在看還是大的圖」）。"""
    client = _player()
    root = actions.images_beside(default_path())
    before = client.get("/api/main").json()["looks_ver"]
    orders.save_sheet(root, "u9", "hero_bare_idle", (ART / "hero_bare_idle.webp").read_bytes())
    after = client.get("/api/main").json()["looks_ver"]
    assert before and after and after != before, "多一張圖，版本就要換"
    orders.save_sheet(root, "u9", "hero_bare_idle", (ART / "hero_bare_hit.webp").read_bytes())
    assert client.get("/api/main").json()["looks_ver"] != after, "同一張換了內容，版本也要換"


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


def test_the_order_uses_the_draft_the_preview_showed(monkeypatch):
    """企劃者 2026-11-03：「我送審前，頁面顯示說會做『槍』跟『菊花』兩個，但是最後只有兩把槍，所以是不一致的問題」。

    正式站 #493 的真因：預覽（/api/looks/scene）與下單（/api/looks/move）各自問一次模型
    （temperature 0.3），兩次答案不同——玩家付 300 元寶核准的那一份，跟真的畫出來的不是同一份。
    所以預覽要把模型填的那張表回給網頁，下單原樣帶回來就不再問第二次。
    """
    from tianxia.features.looks import scenes
    calls = []
    answers = [{"figure": "長槍", "thrown": "菊花", "swords": scenes.NONE, "beam": False, "quake": False,
                "fall": scenes.NONE, "mark": scenes.NONE, "glow": "金", "tone": "夜"},
               {"figure": "法相", "thrown": "長槍", "swords": scenes.NONE, "beam": False, "quake": False,
                "fall": scenes.NONE, "mark": scenes.NONE, "glow": "金", "tone": "夜"}]

    def fake(client, text):  # 第一次給「長槍＋菊花」，第二次給 #493 真的拿到的那一份
        calls.append(text)
        return answers[min(len(calls) - 1, len(answers) - 1)]

    monkeypatch.setattr(scenes, "model_draft", fake)
    client = _player()
    client.get("/api/main")
    text = "長槍法相，打到敵人爆炸後才出現一朵菊花"
    shown = client.post("/api/looks/scene", json={"text": text}).json()
    assert [a["label"] for a in shown["scene"]["arts"]] == ["長槍", "菊花"], "預覽給玩家看的那一份"
    assert isinstance(shown.get("draft"), dict), "預覽要把那張表回給網頁"
    assert len(calls) == 1

    got = client.post("/api/looks/move", json={"prompt": text, "ref": "web-move-0493", "draft": shown["draft"]})
    assert len(calls) == 1, "帶了預覽那一份就不該再問模型（不然答案會變）"
    assert "先練一門自己合成或自創的武功" in got.json()["message"]  # 這個角色沒有自己的武功，到這裡就被擋

    # 沒帶（舊版網頁、或那一句被改過）才會再問一次
    client.post("/api/looks/move", json={"prompt": text, "ref": "web-move-0494"})
    assert len(calls) == 2


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


def test_the_player_can_withdraw_an_order_that_is_stuck():
    """Joy 2026-11-02「審圖卡住，玩家也不能退回，會被卡死」：還沒上架的單下單的人自己撤回，元寶全退、可以再下一張；只能撤一次。"""
    client = _player()
    client.get("/api/main")
    first = client.post("/api/looks/order", json={"name": "白衣書生", "prompt": "白衣書生", "ref": "web-order-0009"}).json()
    row = first["looks"]["order"]["list"][0]
    assert row["withdraw"] is True and first["looks"]["order"]["open"]
    got = client.post("/api/looks/withdraw", json={"id": row["id"], "kind": "look"}).json()
    assert "撤回了「白衣書生」" in got["message"] and got["main"]["mall"]["balance"] == 5000
    row = got["looks"]["order"]["list"][0]
    assert row["status"] == orders.REJECTED and row["reason"] == orders.WITHDRAWN and row["withdraw"] is False
    assert not got["looks"]["order"]["open"]
    again = client.post("/api/looks/withdraw", json={"id": row["id"], "kind": "look"}).json()
    assert "撤不回來" in again["message"] and again["main"]["mall"]["balance"] == 5000
