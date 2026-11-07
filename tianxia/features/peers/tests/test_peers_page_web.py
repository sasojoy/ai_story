"""peers 這一包的測試，從 tests/web/test_jianghu_page_web.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
from __future__ import annotations
import re
import pytest
import server
import webharness
import random
from tianxia.engine import Game
from tianxia.engine import SOCIAL_NO_ONE, Game
from test_prologue_web import run as run_prologue_web
from jianghu_kit import ROOT, _bar, _cell, _face, _game, node  # noqa: F401

pytestmark = pytest.mark.whole_content


def _html_tree(html: str) -> dict:
    from html.parser import HTMLParser

    void = {"img", "hr", "br", "input", "meta", "link", "source"}
    root = {"tag": "#", "attrs": {}, "kids": [], "text": ""}
    stack = [root]

    class Reader(HTMLParser):
        def handle_starttag(self, tag, attrs):
            node = {"tag": tag, "attrs": dict(attrs), "kids": [], "text": ""}
            stack[-1]["kids"].append(node)
            if tag not in void:
                stack.append(node)

        def handle_startendtag(self, tag, attrs):
            stack[-1]["kids"].append({"tag": tag, "attrs": dict(attrs), "kids": [], "text": ""})

        def handle_endtag(self, tag):
            while len(stack) > 1 and stack[-1]["tag"] != tag:
                stack.pop()
            if len(stack) > 1:
                stack.pop()

        def handle_data(self, data):
            for node in stack[1:]:
                node["text"] += data

    Reader().feed(html)
    return root


def _scene_card(node: dict) -> dict | None:
    classes = node["attrs"].get("class", "").split()
    if node["tag"] == "section" and "card" in classes and "scene" in classes:
        return node
    for kid in node["kids"]:
        found = _scene_card(kid)
        if found:
            return found
    return None


@node
@pytest.mark.parametrize("with_art", [True, False])
def test_the_description_selector_follows_the_real_scene_markup(on, with_art):
    """第 6c 步的選擇器（app.js：場景卡直接孩子裡沒有 class 的 <p>，沒有畫時去掉第一段）照真的場景卡寫：有畫時地名那一條疊在畫上、
    場景文字裡拿掉；沒有畫時它是第一段；「此地還有」、邀請、結伴是 <div>，選不到。"""
    game = Game.new(on, "甲", rng=random.Random(0))
    game.client = None
    m = server.main_view(game)
    paras = re.findall(r"<p>(.*?)</p>", m["scene"], re.S)
    head, desc = paras[0], paras[1:]
    assert head.startswith("【") and desc
    m["art"] = ({"kind": "place", "src": "/static/img/places/world.webp", "title": "某地", "sub": "危險 ★", "time": "第 1 天 08:00", "head": f"<p>{head}</p>"}
                if with_art else None)
    m["here"] = [{"name": "沈伯安", "side": "黃巾軍"}]
    m["calls"] = [{"text": "有人跟你打招呼", "options": [{"id": "invite:accept:1", "label": "回禮", "enabled": True}]}]
    m["party"] = {"text": "你與某人結伴同行", "lead": False}
    card = _scene_card(_html_tree(run_prologue_web(m, "return H.pageJianghu();")))["kids"]
    drawn_art = any("scene-art" in k["attrs"].get("class", "") for k in card)
    assert drawn_art is with_art
    # 介面重整：場景文字包在 .rv-scene 裡（app.js 的 sceneBody），畫還是場景卡的直接孩子；結伴、邀請在卡底下，「此地還有」搬到此地人物那一排
    kids = next(k for k in card if "rv-scene" in k["attrs"].get("class", "").split())["kids"]
    picked = [k for k in kids if k["tag"] == "p" and "class" not in k["attrs"]]
    if not drawn_art:
        assert picked[0]["text"].startswith("【")  # 第一段是地名那一條
        picked = picked[1:]
    norm = lambda text: " ".join(re.sub(r"<[^>]*>", "", text).split())  # noqa: E731
    assert [norm(k["text"]) for k in picked] == [norm(d) for d in desc]
    assert "calls" in {k["attrs"].get("class") for k in card if k["tag"] == "div"} and not any("calls" in k["attrs"].get("class", "") for k in kids)
    src = (ROOT / "web" / "fit.js").read_text(encoding="utf-8")
    assert 'scene.querySelectorAll(":scope > p:not([class])")' in src and 'document.querySelector("#page > .card.scene:not(.road)").querySelector(":scope > .scene-art")' in src
    assert 'card.querySelector(":scope > .rv-scene") || card' in src


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
@pytest.mark.slow
def test_the_social_cell_greyed_for_nobody_here_says_it_briefly_and_the_note_row_has_the_sentence():
    game = _game("yingchuan")
    social = next(o for o in game.options() if o.id == "act:socialize")
    assert not social.enabled and social.label == f"交友（{SOCIAL_NO_ONE}）"  # 前提：真的是這一句
    bar = _bar(game)
    cell = _cell(bar, "social")
    assert "<b>交友</b><small>沒有人</small>" in cell and SOCIAL_NO_ONE not in _face(cell)
    assert f'data-why="{SOCIAL_NO_ONE}。"' in cell  # 整句在點了浮出的那一句（減法季批 1 拿掉了底下那一行），不是伺服器寫的那一句「結識這裡的人」
    assert "結識這裡的人" not in bar
