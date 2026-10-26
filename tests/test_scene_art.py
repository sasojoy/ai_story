"""江湖頁場景卡上面那張圖（減法季批 8 圖像版；減法季整合設計第八章、第一批圖提示單）。
引擎挑圖（Game.scene_art）：事件開著→事件的類型圖，跟人物談話→他的像，站在地點→地點的圖（沒寫就退回所屬大區的 places/<大區>）；
其餘畫面 None。伺服器只在 web/img/ 真的有那個檔時才給 m.art（server.scene_art），網頁有圖時把原本寫地名／標題的第一段拿掉、疊在圖上；
沒圖一字不變。分類表在 content/art.json（事件的 image 只能寫那 20 類）。"""
from __future__ import annotations

import re

import pytest
from conftest import real_content

import server
import webharness
from tianxia import content as content_mod
from tianxia.content import validate
from tianxia.engine import Game

ROOT = server.ROOT


def _errors(c) -> list[str]:
    try:
        validate(c)
    except content_mod.ContentError as e:
        return str(e).splitlines()
    return []


# ── 引擎挑圖 ──────────────────────────────────────────


def test_a_place_falls_back_to_its_region_picture(game):
    """地點沒寫 image：所屬大區的 places/<大區 id>；標題是地名、副題是危險度、head 是場景第一行。"""
    game.state.player.location = "town"
    region = __import__("tianxia.atlas", fromlist=["region_of"]).region_of(game.content, "town")
    art = game.scene_art()
    assert art == {"kind": "place", "path": f"places/{region.id}", "title": game.content.locations["town"].name,
                   "sub": f"危險 {'★' * game.content.locations['town'].danger}", "head": game.location_text().split("\n")[0]}
    assert game.scene_text().startswith(art["head"])


def test_a_place_with_its_own_picture_uses_it_and_no_regions_means_world(game):
    game.content.locations["town"].image = "places/town_gate"
    assert game.scene_art()["path"] == "places/town_gate"
    game.content.locations["town"].image = None
    game.content.map.regions = []
    assert game.scene_art()["path"] == "places/world"


def test_an_event_uses_its_type_picture_and_none_without_one(game):
    game.content.art.events["town"] = "城鎮"
    game.content.events["drunk"].image = "town"
    game.state.pending_event = "drunk"
    art = game.scene_art()
    assert art["kind"] == "event" and art["path"] == "events/town" and art["title"] == game.content.events["drunk"].title
    assert art["head"] == f"**{game.content.events['drunk'].title}**" and game.scene_text().startswith(art["head"])
    game.content.events["drunk"].image = None
    assert game.scene_art() is None  # 沒寫 image 的事件：沒圖、卡片一字不變


def test_a_figure_uses_the_portrait_and_none_without_one(game):
    game.state.player.pending_companion = "scholar"
    assert game.scene_art() is None
    game.content.characters["scholar"].image = "figures/scholar"
    art = game.scene_art()
    assert art["kind"] == "figure" and art["path"] == "figures/scholar" and art["title"] == game.content.characters["scholar"].name
    assert art["sub"] == game.affinity_text("scholar") and game.scene_text().startswith(art["head"])


def test_other_screens_get_no_picture(game):
    """在路上、季收了：不是地點的描寫，不給圖。"""
    game.state.world.ended = True
    assert game.scene_art() is None
    game.state.world.ended = False
    game.choose("move:lake")
    assert game.state.player.journey is not None and game.scene_art() is None


# ── 伺服器：有圖檔才給 ──────────────────────────────────


def test_the_server_only_offers_pictures_that_exist(game, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "WEB", tmp_path)
    assert server.main_view(game)["art"] is None
    path = game.scene_art()["path"]
    (tmp_path / "img" / path).parent.mkdir(parents=True)
    (tmp_path / "img" / f"{path}.webp").write_bytes(b"x")
    m = server.main_view(game)
    assert m["art"]["src"] == f"/static/img/{path}.webp" and m["art"]["kind"] == "place"
    assert m["art"]["head"] == server.md(game.scene_art()["head"]) and m["scene"].startswith(m["art"]["head"])
    assert m["art"]["time"] == f"第{m['status']['day']}天 {m['status']['clock']}"  # 沒有季曆的季：第 N 天 HH:MM


# ── 內容檢查 ──────────────────────────────────────────


def test_an_event_image_must_be_a_listed_type(content):
    content.events["drunk"].image = "palace"
    assert any("drunk" in e and "palace" in e for e in _errors(content))
    content.art.events["palace"] = "宮門"
    assert _errors(content) == []


def test_location_and_figure_images_are_paths_under_web_img(content):
    content.locations["town"].image = "town.webp"
    content.characters["scholar"].image = "scholar"
    errs = _errors(content)
    assert any("town" in e for e in errs) and any("scholar" in e for e in errs)
    content.locations["town"].image, content.characters["scholar"].image = "places/town", "figures/scholar"
    assert _errors(content) == []


@pytest.mark.slow  # 載真實內容
def test_the_real_content_classifies_every_event_and_ships_the_pictures():
    """正式內容：297 則事件都分了類、類型都在 art.json；20 類插圖、5 個大區與 world、三位人物像的 webp 都在 web/img/。"""
    c = real_content()
    assert len(c.art.events) == 20
    assert all(ev.image in c.art.events for ev in c.events.values())
    for key in c.art.events:
        assert (ROOT / "web" / "img" / "events" / f"{key}.webp").is_file(), key
    for region in c.map.regions:
        assert (ROOT / "web" / "img" / "places" / f"{region.id}.webp").is_file(), region.id
    assert (ROOT / "web" / "img" / "places" / "world.webp").is_file()
    for cid in ("luzhi", "bocai", "huangfusong"):
        assert c.characters[cid].image == f"figures/{cid}" and (ROOT / "web" / "img" / f"figures/{cid}.webp").is_file()


# ── 網頁 ──────────────────────────────────────────────


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_page_puts_the_picture_on_top_and_drops_the_duplicated_first_line(game, tmp_path, monkeypatch):
    from test_prologue_web import run

    monkeypatch.setattr(server, "WEB", tmp_path)
    plain = server.main_view(game)
    page_plain = run(plain, "return H.pageJianghu();")
    assert "scene-art" not in page_plain and plain["art"] is None
    path = game.scene_art()["path"]
    (tmp_path / "img" / path).parent.mkdir(parents=True)
    (tmp_path / "img" / f"{path}.webp").write_bytes(b"x")
    m = server.main_view(game)
    page = run(m, "return H.pageJianghu();")
    card = re.search(r'<section class="card scene has-art">(.*?)</section>', page, re.S).group(1)
    assert card.startswith('<figure class="scene-art place"><img src="/static/img/' + path + '.webp" alt="" decoding="async">')
    assert f"<b>{m['art']['title']}</b>" in card and f'<span class="sub">{m["art"]["sub"]}</span>' in card and f'<span class="time">{m["art"]["time"]}</span>' in card
    assert m["art"]["head"].strip() not in card  # 地名那一段只疊在圖上，卡片裡不再寫一次
    assert card.count("<p>") == plain["scene"].count("<p>") - 1
    # 沒圖那一份一字不變
    assert page_plain == run({**m, "art": None}, "return H.pageJianghu();")
