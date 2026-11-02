"""擂台形象的畫面（萬寶閣「形象」那一頁，畫在商城包的網頁檔裡）：貨架上有形象才多一格「形象」；每一套一張卡，穿著的寫「穿著」、買了的「換上」、
沒買的一顆價錢（點了走貨架同一條購買確認）；換上送 /api/looks/wear。擂台動畫照 looks 的 me_look／foe_look 抓 web/img/looks/<id>/。"""
from __future__ import annotations

import pytest
from test_mall_web import _async, _click, _view, m_on, run  # noqa: F401  m_on 是 fixture

import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

LOOKS = {"worn": "moying", "looks": [
    {"id": "", "name": "斗笠小子", "note": "", "owned": True, "item": None},
    {"id": "moying", "name": "墨影", "note": "一身墨色。", "owned": True, "item": None},
    {"id": "jinshen", "name": "金身", "note": "通體鎏金。", "owned": False, "item": "look_jinshen"},
]}


def _shelf():
    d = _view()
    d["looks"] = True
    d["items"].append({"id": "look_jinshen", "name": "金身形象", "note": "", "price": 600, "kind": "look", "kind_name": "形象",
                       "effects": "擂台形象一套（換季也帶著走）", "limit": "", "can": True, "why": None, "after": 4400,
                       "gives": {"look": 1}, "card_to": None, "look": "jinshen"})
    return d


def _layer(m, extra="", responses=None):
    """打開商城（點錠子鈕），再做 extra；/api/mall 給有形象的貨架（同 test_mall_web._layer，貨架換一份）。"""
    return run(m, _async(_click('{ act: "mall-open" }') + extra + """
      return { app: T.els.app.innerHTML, calls: T.calls };"""), responses={**(responses or {}), "/api/mall": _shelf()})


def test_the_look_tab_shows_each_look_and_wears_one(m_on):  # noqa: F811
    out = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }') + _click('{ act: "look-wear", id: "" }'),
                 responses={"/api/looks/wear": {"message": "換上了「斗笠小子」。", "looks": {**LOOKS, "worn": ""}}, "/api/looks": LOOKS})
    assert any(c[0] == "/api/looks/wear" and c[1] == {"look": ""} for c in out["calls"])
    html = out["app"]
    assert "斗笠小子" in html and "墨影" in html and "金身" in html
    assert 'data-act="mall-pick" data-id="look_jinshen"' in html  # 沒買的那一套：一顆價錢、走貨架的購買確認
    assert "/static/img/looks/moying/hero_bare_idle.webp" in html
    assert "換上了「斗笠小子」" in html


def test_no_look_tab_without_looks_on_the_shelf(m_on):  # noqa: F811
    out = run(m_on, _async(_click('{ act: "mall-open" }') + "return { app: T.els.app.innerHTML };"), responses={"/api/mall": _view()})
    assert 'data-tab="look"' not in out["app"]
    assert 'data-tab="look"' in _layer(m_on)["app"]


ORDER = {"price": 900, "name_max": 6, "prompt_max": 120, "open": False, "list": [
    {"id": 3, "name": "黑衣客", "prompt": "黑衣蒙面", "status": "rejected", "status_text": "退回", "reason": "看不清楚"},
]}


def test_the_look_tab_has_the_order_form_and_my_orders(m_on):  # noqa: F811
    looks = {**LOOKS, "order": ORDER}
    out = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }') + _click('{ act: "look-order" }'),
                 responses={"/api/looks": looks})
    html = out["app"]
    assert 'id="look-name"' in html and 'id="look-prompt"' in html and 'data-act="look-order"' in html
    assert "黑衣客" in html and "退回" in html and "看不清楚" in html
    assert "先替這一套取個名字" in html  # 沒填名字就按：掌櫃講原因、不送
    assert not any(c[0] == "/api/looks/order" for c in out["calls"])


def test_an_open_order_hides_the_form(m_on):  # noqa: F811
    looks = {**LOOKS, "order": {**ORDER, "open": True, "list": [{**ORDER["list"][0], "status": "pending", "status_text": "等圖中", "reason": ""}]}}
    html = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }'), responses={"/api/looks": looks})["app"]
    assert 'id="look-name"' not in html and "等圖中" in html


def test_the_admin_box_lists_open_orders_with_prompts(m_on):  # noqa: F811
    import json

    from test_mall_web import DRIVER as MALL_DRIVER

    driver = MALL_DRIVER.replace('wholeApp(["S", ', 'wholeApp(["S", "looksAdminHtml", ', 1)
    admin = {"sheets": {"hero_bare_idle": 4, "hero_bare_hit": 3}, "gen": "off", "done": [], "open": [
        {"id": 5, "owner": "沈浪", "name": "白衣書生", "prompt": "白衣書生，背著竹簍", "status": "pending", "status_text": "等圖中",
         "reason": "", "look": "u5", "have": ["hero_bare_idle"], "prompts": {"hero_bare_idle": "Style: idle", "hero_bare_hit": "Style: hit"}}]}
    script = f"H.S.adLooks = {json.dumps(admin, ensure_ascii=False)}; return H.looksAdminHtml();"
    html = webharness.run(driver, {"m": m_on, "script": script, "S": {}, "menxia": None, "stored": {}, "responses": {}})
    assert "白衣書生，背著竹簍" in html and "Style: idle" in html
    assert 'id="ad-looks-file-5"' in html and 'data-op="reject"' in html
    assert 'data-op="release" data-id="5" disabled' in html  # 十張還沒齊：上架按不下去
    moves = {"sheet": "fx", "size": "1320×220", "done": [], "open": [
        {"id": 9, "owner": "沈浪", "art": "旋風腿", "style_text": "拳腳", "prompt": "背後出現一座大佛擊出一掌", "status": "pending",
         "status_text": "等圖中", "reason": "", "move": "m9", "scene": True, "missing": ["art2"], "have": False, "gen_prompt": "",
         "arts": [{"slot": "art1", "label": "大佛", "have": True, "prompt": "Draw ONE subject only: 「大佛」"},
                  {"slot": "art2", "label": "佛掌", "have": False, "prompt": "Draw ONE subject only: 「佛掌」"}]}]}
    script = f"H.S.adLooks = {json.dumps({**admin, 'open': [], 'moves': moves}, ensure_ascii=False)}; return H.looksAdminHtml();"
    html = webharness.run(driver, {"m": m_on, "script": script, "S": {}, "menxia": None, "stored": {}, "responses": {}})
    assert "art1・大佛" in html and "「佛掌」" in html  # 一句話自創：要畫的一樣一格，附提示詞
    assert 'data-slot="art2"' in html and 'id="ad-moves-file-9-art2"' in html
    assert 'data-op="move-release" data-id="9" disabled' in html  # 還缺佛掌：上架按不下去
    stopped = {**moves["open"][0], "studio": {"painted": 3, "failed": "佛掌：有字"}}  # 畫坊停手：寫原因、給「再畫一次」
    script = f"H.S.adLooks = {json.dumps({**admin, 'gen': 'api', 'open': [], 'moves': {**moves, 'open': [stopped]}}, ensure_ascii=False)}; return H.looksAdminHtml();"
    html = webharness.run(driver, {"m": m_on, "script": script, "S": {}, "menxia": None, "stored": {}, "responses": {}})
    assert "畫坊：畫了 3 張・停手了：佛掌：有字" in html and 'data-op="studio-retry" data-id="9"' in html and "畫坊自動畫" in html


MOVES = {"price": 300, "prompt_max": 120, "art": "旋風腿", "has_art": True, "style": "fist", "style_text": "拳腳", "open": False, "bound": False,
         "library": [{"id": 7, "move": "m7", "art": "流雲掌", "style": "fist", "style_text": "拳腳", "prompt": "青色劍氣", "status": "made",
                      "status_text": "上架", "reason": "", "bound": "", "on_art": False, "bindable": True}],
         "list": []}


def test_a_stuck_order_can_be_withdrawn(m_on):  # noqa: F811
    """Joy 2026-11-02「審圖卡住，玩家也不能退回，會被卡死」：還沒上架的單一顆「撤回」，先問一次，送 /api/looks/withdraw。"""
    open_ = {**ORDER, "open": True, "list": [{**ORDER["list"][0], "status": "review", "status_text": "審核中", "reason": "", "withdraw": True}]}
    done = {**ORDER, "list": [{**ORDER["list"][0], "reason": "自己撤回", "withdraw": False}]}
    out = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }')
                 + 'const before = T.els.app.innerHTML;'
                 + _click('{ act: "look-withdraw", kind: "look", id: "3", name: "黑衣客" }') + 'const asked = T.bodyHtml.join("");'
                 + _click('{ act: "ask-yes" }') + 'return { before, asked, app: T.els.app.innerHTML, calls: T.calls };',
                 responses={"/api/looks": {**LOOKS, "order": open_},
                            "/api/looks/withdraw": {"message": "撤回了「黑衣客」：元寶 +900 退回來了。", "looks": {**LOOKS, "order": done}}})
    assert 'data-act="look-withdraw" data-kind="look" data-id="3"' in out["before"] and "按「撤回」退掉" in out["before"]
    assert "撤回「黑衣客」？元寶全退" in out["asked"]
    assert any(c[0] == "/api/looks/withdraw" and c[1] == {"id": 3, "kind": "look"} for c in out["calls"])


def test_the_move_section_orders_and_binds(m_on):  # noqa: F811
    """招式動畫（第三批）：寫現在練的那一門與打法、下單的表單、招式庫一列一顆「綁到」；綁送 /api/looks/bind。"""
    looks = {**LOOKS, "moves": MOVES}
    out = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }') + _click('{ act: "move-bind", id: "7" }'),
                 responses={"/api/looks/bind": {"message": "把招式綁到「旋風腿」上了（這一季）。", "looks": looks}, "/api/looks": looks})
    html = out["app"]
    assert "絕招" in html and "現在練的「旋風腿」・打法拳腳" in html
    assert 'id="move-prompt"' in html and 'data-act="move-order"' in html and 'data-act="move-preview"' in html
    assert "/api/looks/img/m7/fx" in html  # 舊的光效單照舊畫那一張
    assert any(c[0] == "/api/looks/bind" and c[1] == {"id": 7} for c in out["calls"])
    assert "把招式綁到「旋風腿」" in html


def test_a_move_that_cannot_play_says_why(m_on):  # noqa: F811
    """綁著、但手上的兵器換了打法：擂台上不會演，招式庫那一列與抬頭都要寫明（Joy 2026-11-02
    「我那個絕招寒霜雪怎麼都還沒施放過」——空手下的單，後來拿了劍）。下單那一塊也先講明打法會鎖住。"""
    asleep = "這一招是拳腳的，你現在的打法是揮砍——擂台上不會演，換回拳腳才演得出來。"
    moves = {**MOVES, "style": "slash", "style_text": "揮砍", "bound": True, "asleep_text": asleep,
             "order_style_note": "照你現在的打法（揮砍）登記。換成別種兵器時這一招不會演，要另外下一張。",
             "library": [{**MOVES["library"][0], "bound": "旋風腿", "on_art": True, "bindable": False,
                          "plays": False, "asleep": True, "asleep_text": asleep}]}
    html = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }'), responses={"/api/looks": {**LOOKS, "moves": moves}})["app"]
    assert html.count("擂台上不會演，換回拳腳才演得出來") == 2  # 抬頭一句、那一列一句
    assert 'data-act="move-bind"' not in html  # 打法對不上，綁不了


SCENE = {"v": 1, "name": "旋風腿", "glow": "#ffd27a", "length": 3300, "arts": [{"slot": "art1", "label": "大佛"}, {"slot": "art2", "label": "佛掌"}],
         "beats": [{"op": "暗場", "at": 0, "tone": "暖"}, {"op": "法相", "at": 350, "art": "art1", "label": "大佛"}, {"op": "落款", "at": 900},
                   {"op": "巨物飛擊", "at": 1500, "art": "art2", "label": "佛掌"}, {"op": "白光", "at": 2600}]}


def test_the_move_preview_shows_what_needs_drawing(m_on):  # noqa: F811
    """一句話自創（Joy 2026-11-01）：按「先看看」送 /api/looks/scene、不扣元寶，下面多一塊畫布照稿演，寫要畫哪幾樣；
    招式庫裡一句話自創的那一招蓋一個「絕」字印（沒有光效圖）。"""
    lib = [{**MOVES["library"][0], "id": 8, "move": "m8", "scene": True, "arts": []}]
    looks = {**LOOKS, "moves": {**MOVES, "library": lib}}
    out = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }') + _click('{ act: "move-preview" }'),
                 responses={"/api/looks/scene": {"scene": SCENE}, "/api/looks": looks})
    html = out["app"]
    assert any(c[0] == "/api/looks/scene" for c in out["calls"])
    assert 'id="scene-preview"' in html and "獨門會畫「大佛」「佛掌」" in html
    assert 'move-seal' in html and "/api/looks/img/m8/fx" not in html
    bad = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }') + _click('{ act: "move-preview" }'),
                 responses={"/api/looks/scene": {"problem": "只能寫中文。"}, "/api/looks": looks})["app"]
    assert "只能寫中文。" in bad and 'id="scene-preview"' not in bad


def test_made_looks_and_moves_can_be_shown(m_on):  # noqa: F811
    """做好了的也要能看（Joy 2026-11-01「形象頁那邊，已經做好的形象跟絕招也要能展示」）：每一套一顆「看動作」，按了格子上面多一塊畫布
    （arena_scene.js 的 lookShow 一張一張演），再按收起；招式庫裡一句話自創的那一招一顆「演一次」，抓 /api/looks/scene/m<id> 照稿演、
    表單先收起來。"""
    lib = [{**MOVES["library"][0], "id": 8, "move": "m8", "scene": True, "arts": ["大佛"]}]
    looks = {**LOOKS, "moves": {**MOVES, "library": lib}}
    out = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }') + _click('{ act: "look-show", id: "moying", name: "墨影" }'),
                 responses={"/api/looks": looks})
    html = out["app"]
    assert 'data-act="look-show" data-id="jinshen"' in html  # 沒買的也看得到
    assert 'id="look-show"' in html and "<b>墨影</b>" in html and 'data-act="look-show" data-id=""' in html
    closed = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }') + _click('{ act: "look-show", id: "moying", name: "墨影" }')
                    + _click('{ act: "look-show", id: "" }'), responses={"/api/looks": looks})["app"]
    assert 'id="look-show"' not in closed
    out = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }') + _click('{ act: "move-show", id: "m8" }'),
                 responses={"/api/looks/scene/m8": {"scene": SCENE}, "/api/looks": looks})
    html = out["app"]
    assert any(c[0] == "/api/looks/scene/m8" for c in out["calls"])
    assert 'id="scene-preview"' in html and 'id="move-prompt"' not in html and ">收起</button>" in html


def test_no_art_no_move_form(m_on):  # noqa: F811
    looks = {**LOOKS, "moves": {**MOVES, "has_art": False, "art": "", "library": []}}
    html = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }') + _click('{ act: "move-order" }'), responses={"/api/looks": looks})["app"]
    assert 'id="move-prompt"' not in html and "先練一門自己合成或自創的武功" in html


MARKET = {"shelf": [{"look": "u5", "name": "白衣書生", "seller": "沈浪", "price": 800}],
          "mine": [{"look": "u9", "name": "黑衣客", "price": None}, {"look": "u11", "name": "紅袍", "price": 700}],
          "min": 300, "max": 3000, "default": 600, "share": 0.5, "hold_days": 7, "paid_only": False, "sold": 2, "paid": 400, "held": 350}


def test_the_market_buys_lists_and_unlists(m_on):  # noqa: F811
    """形象市集（第四批）：別人的一套一顆價錢（先問一次才送）；自己的沒掛寫價錢「掛上去」、掛著的「撤下」；寫賣了幾份與分成。"""
    looks = {**LOOKS, "market": MARKET}
    reply = {"message": "買下了「白衣書生」（沈浪做的）：元寶 -800（還剩 4200）。", "looks": looks}
    out = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }') + _click('{ act: "market-buy", id: "u5", name: "白衣書生", price: "800" }')
                 + _click('{ act: "ask-yes" }') + _click('{ act: "market-list", id: "u9" }') + _click('{ act: "market-unlist", id: "u11" }'),
                 responses={"/api/looks/market": reply, "/api/looks": looks})
    html = out["app"]
    assert "形象市集" in html and "沈浪做的" in html and 'data-act="market-buy" data-id="u5"' in html
    assert 'id="market-price-u9"' in html and "掛著・700" in html and "賣出 2 份・分成入帳 400・押著 350" in html
    sent = [c[1] for c in out["calls"] if c[0] == "/api/looks/market"]
    assert sent[0]["op"] == "buy" and sent[0]["look"] == "u5" and sent[0]["ref"]
    assert sent[1] == {"op": "list", "look": "u9", "price": 600} and sent[2] == {"op": "unlist", "look": "u11"}


GEAR_DRIVER = r"""
const code = ["GEAR_ORDER"].map(konst).join("\n") + fn("skinParts") + fn("gearFrame");
const H = new Function(code + "\nreturn { skinParts, gearFrame };")();
// 一個假的人：220×220 一格，頭是 60×60 的方塊、身子 40×100、細細的一隻手（侵蝕掉）；躺下的那一格整個轉 90 度，頭朝右
const W = 440, Hh = 220, px = new Uint8ClampedArray(W * Hh * 4);
const fill = (x0, y0, w, h) => { for (let y = y0; y < y0 + h; y++) for (let x = x0; x < x0 + w; x++) px[(y * W + x) * 4 + 3] = 255; };
fill(70, 40, 60, 60); fill(80, 100, 40, 100); fill(120, 120, 60, 3);
fill(220 + 140, 80, 60, 60); fill(220 + 40, 90, 100, 40);
finish({ parts: input.skins.map((s) => H.skinParts(s)), up: H.gearFrame(px, W, Hh, 0, 220), down: H.gearFrame(px, W, Hh, 220, 220) });
"""


def test_gear_finds_the_head_and_waist_in_every_frame():
    """飾品疊在哪：每一格現算（侵蝕掉手腳，頭取頭頂往下 30%、腰取 55～65%）；躺下的照主軸轉、頭在大的那一頭。皮照「形象~飾品」拆。"""
    out = webharness.run(GEAR_DRIVER, {"skins": ["moying~head_red_band.waist_jade", "~face_scar", "u12", "x~bad.head_a"]})
    assert [p["look"] for p in out["parts"]] == ["moying", "", "u12", "x"]
    assert [p["gear"] for p in out["parts"]] == [["waist_jade", "head_red_band"], ["face_scar"], [], ["head_a"]]  # 腰先畫、頭最後
    up, down = out["up"], out["down"]
    assert up["ang"] == pytest.approx(0) and 90 < up["head"][0] < 110 and 50 < up["head"][1] < 85
    assert 85 < up["waist"][0] < 115 and 120 < up["waist"][1] < 160
    assert abs(down["ang"]) == pytest.approx(1.5708, abs=0.05) and down["head"][0] > 150  # 躺著、頭朝右


def test_the_gear_cards_wear_and_take_off(m_on):  # noqa: F811
    looks = {**LOOKS, "skin": "moying", "gear": [
        {"id": "head_red_band", "name": "紅頭巾", "note": "", "slot": "head", "slot_text": "頭", "owned": True, "item": None, "worn": True},
        {"id": "waist_jade", "name": "玉佩", "note": "", "slot": "waist", "slot_text": "腰", "owned": False, "item": "look_jinshen", "worn": False},
    ]}
    out = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }') + _click('{ act: "look-gear", id: "head_red_band" }'),
                 responses={"/api/looks": looks, "/api/looks/gear": {"message": "拿下了「紅頭巾」。", "looks": looks}})
    html = out["app"]
    assert "飾品" in html and "/static/img/looks/head_red_band/icon.webp" in html and 'data-act="look-gear" data-id="head_red_band"' in html
    assert "拿下" in html and 'data-act="look-show" data-id="moying~head_red_band"' in html  # 看動作：身上那一套戴這一件
    assert any(c[0] == "/api/looks/gear" and c[1] == {"id": "head_red_band"} for c in out["calls"])
