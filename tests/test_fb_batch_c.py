"""回饋單丙批（PM 2026-10-14 派工：回饋單甲批、乙批 QA 新開的四張小單）：一張單一段，各自的重現與修正。新寫的字都待 joy 潤。"""
from __future__ import annotations

import pytest
from test_forge_divine import _forger, divine_content  # noqa: F401（fixture）

import server
import webharness
from tianxia import equipment, forge_secrets, shopview, skillview, smithing, weapons
from tianxia.state import Weapon

needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


# ── FB-197：防具神器的定名表單寫「這把神器」→ 量詞照 equipment.unit_for，伺服器帶出去、網頁照它寫 ──


def _slot_rows(game, content, world, slot):
    block = next(b for b in skillview.gear_rows(game.state, content, world)["slots"] if b["slot"] == slot)
    return [block["worn"], *block["rack"]]


def test_fb197_the_practice_rows_carry_the_unit_of_the_unnamed_original(divine_content, world):
    """修練頁（與店面裝備庫，shopview._rack 讀同一份）那一列的 divine 多帶量詞：兵器照種類（劍一把），防具一件。"""
    game = _forger(divine_content, world, name="甲")
    blade, _ = smithing.forge(game.state, divine_content, world, "劍", "gang_3", "gang_3")
    coat, _ = smithing.forge(game.state, divine_content, world, smithing.ARMOR_KIND, "gang_3", "gang_3",
                             rng=smithing.own_rng(game.state, "鎧|gang_3+gang_3"))
    assert blade.original and coat.original
    [row] = [r for r in _slot_rows(game, divine_content, world, "weapon") if r and r["id"] == blade.id]
    assert row["divine"] == {"pattern": "墜星劍", "unit": "把"}
    [row] = [r for r in _slot_rows(game, divine_content, world, "armor") if r and r["id"] == coat.id]
    assert row["divine"] == {"pattern": "鎮星甲", "unit": "件"}
    assert row["divine"]["unit"] == equipment.unit_for("armor")


def test_fb197_a_fist_original_is_a_fu(divine_content, world, monkeypatch):
    """拳套論副（FB-133）：等著定名的拳套那一列寫「副」，跟 equipment.unit_for 同一個字。"""
    game = _forger(divine_content, world, name="甲")
    fist = weapons.new_weapon(game.state, name="無名神器", kind="拳腳", attribute="剛", tier=3, quality="上品")
    game.state.player.rack.append(fist)
    monkeypatch.setattr(forge_secrets, "unnamed_originals", lambda state, world: {fist.id: "撼岳拳套"})
    [row] = [r for r in _slot_rows(game, divine_content, world, "weapon") if r and r["id"] == fist.id]
    assert row["divine"] == {"pattern": "撼岳拳套", "unit": "副"} == {"pattern": "撼岳拳套", "unit": equipment.unit_for("weapon", "拳腳")}


def test_fb197_the_forged_card_carries_the_unit(divine_content, world):
    """店面的出爐卡（shopview.forged_card）多一個 unit：防具一件、拳套一副、其他兵器一把。"""
    game = _forger(divine_content, world, name="甲")
    coat, _ = smithing.forge(game.state, divine_content, world, smithing.ARMOR_KIND, "gang_3", "gang_3",
                             rng=smithing.own_rng(game.state, "鎧|gang_3+gang_3"))
    card = shopview.forged_card(game.state, divine_content, world, coat, {"first": True})
    assert card["divine"] == "鎮星甲" and card["unit"] == "件"
    fist = weapons.new_weapon(game.state, name="鐵拳", kind="拳腳", attribute="剛", tier=1, quality="下品")
    assert shopview.forged_card(game.state, divine_content, world, fist, {})["unit"] == "副"
    blade = weapons.new_weapon(game.state, name="鐵劍", kind="劍", attribute="剛", tier=1, quality="下品")
    assert shopview.forged_card(game.state, divine_content, world, blade, {})["unit"] == "把"


@needs_node
def test_fb197_the_practice_page_form_says_jian_for_armor_and_fu_for_a_fist(hints_content, world):
    """修練頁那一列底下的表單：照 divine.unit 寫「這件神器」「這副神器」「這把神器」，不再一律寫「把」。"""
    import random

    from test_prologue_web import run
    from test_weapons_web import _armor_row, _gear, _row, _slot_block

    from tianxia.engine import Game

    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    m, x = server.main_view(game), server.menxia_view(game)
    x["gear"] = _gear(
        weapon={"worn": None, "rack": [_row(id="兵:2", kind="拳腳", name="無名神器", keep="原品不能拆", divine={"pattern": "撼岳拳套", "unit": "副"}),
                                       _row(id="兵:3", name="無名神器", keep="原品不能拆", divine={"pattern": "墜星劍", "unit": "把"})]},
        armor={"worn": _armor_row(id="甲:1", name="無名神器", keep="原品不能拆", divine={"pattern": "鎮星甲", "unit": "件"}), "rack": []},
    )
    page = run(m, "return H.pagePractice();", menxia=x)
    armor_block, weapon_block = _slot_block(page, "armor"), _slot_block(page, "weapon")
    assert "打出這件神器的人" in armor_block and "這把神器" not in armor_block
    assert "打出這副神器的人" in weapon_block and "打出這把神器的人" in weapon_block


@needs_node
def test_fb197_the_shop_forged_card_and_rack_follow_the_server_unit(content, world, monkeypatch):
    """店面：出爐卡照卡上的 unit（防具一件），裝備庫那一頁照那一列的 divine.unit（拳套一副）。伺服器真的帶出去的資料（main_view）。"""
    import json

    from test_shop import _smith
    from test_shop_web import FORGED
    from test_shop_web import run as shop_run

    game = _smith(content, world)
    fist = Weapon(id="兵:7", name="無名神器", kind="拳腳", attribute="剛", tier=3, quality="上品", original=True)
    game.state.player.rack = [fist]
    monkeypatch.setattr(forge_secrets, "unnamed_originals", lambda state, world: {fist.id: "撼岳拳套"})
    m = server.main_view(game)
    [row] = m["shop"]["rack"]["rows"]
    assert row["divine"] == {"pattern": "撼岳拳套", "unit": "副"}
    rack = shop_run(m, 'H.S.shopTab = "rack"; H.render(); return T.els.app.innerHTML;')
    assert "打出這副神器的人" in rack and "這把神器" not in rack
    shop = json.loads(json.dumps(m["shop"]))
    shop["pending"] = {"甲:1": "鎮星甲"}
    card = {**FORGED, "id": "甲:1", "slot": "armor", "kind": "防具", "first": True, "glow": "redgold", "divine": "鎮星甲", "unit": "件"}
    html = shop_run({**m, "shop": shop}, "H.S.shopReveal = H.S.next; H.S.shopOpened = true; H.render(); return T.els.app.innerHTML;",
                    S={"next": card})
    assert 'id="shop-name-divine-甲:1"' in html and "打出這件神器的人" in html and "這把神器" not in html


# ── FB-198：375 寬只要有內傷「氣血」兩個字就讓開 → 數字放得下就寫全，放不下才讓開（體力條同一條規則）──
# app.js 的 fitBars 畫好之後量：條上那一行字的字尾（Range）碰不碰得到右邊的「傷 N」或丹的鈕；碰到先 .snug（字小一號、兩個字照寫），
# 還碰到才 .tight（拿掉兩個字）。假瀏覽器沒有排版：給每個狀態（寫全、snug、tight）各一個字尾位置與右邊那一格的左緣，看它收到哪一步。

_FIT_DRIVER = r"""
eval(fn("fitBars"));
let current = null;
const mkBar = (c) => {
  const classes = new Set(c.start || []);
  const state = () => (classes.has("tight") ? "tight" : classes.has("snug") ? "snug" : "full");
  const pick = (v) => (typeof v === "number" ? v : v[state()]);
  const tag = { classList: { contains: (x) => x === (c.pill ? "pill-btn" : "inj") }, getBoundingClientRect: () => ({ left: pick(c.tag) }) };
  const bar = {
    clientWidth: c.width ?? 109,
    classList: { add: (...x) => x.forEach((y) => classes.add(y)), remove: (...x) => x.forEach((y) => classes.delete(y)), contains: (x) => classes.has(x) },
    querySelector: (sel) => (sel.includes("pill-btn") ? (c.tag == null ? null : tag) : { end: () => pick(c.end) }),
  };
  return { bar, classes };
};
const bars = input.cases.map(mkBar);
globalThis.document = {
  getElementById: (id) => (id === "top" ? { querySelectorAll: () => bars.map((b) => b.bar) } : null),
  createRange: () => ({ selectNodeContents(n) { current = n; }, getBoundingClientRect: () => ({ right: current.end() }) }),
};
fitBars();
finish(bars.map((b) => [...b.classes].sort()));
"""


def _fit(cases):
    return webharness.run(_FIT_DRIVER, {"cases": cases})


@needs_node
def test_fb198_the_word_stays_when_the_numbers_fit():
    """QA 的例子（銀兩 50、心得 20、氣血 413/416、傷 3）：寫全放得下就不收；字尾碰到「傷 N」先收一號、兩個字照寫；收一號還碰到才拿掉。"""
    out = _fit([
        {"end": {"full": 230, "snug": 222, "tight": 200}, "tag": {"full": 236, "snug": 239, "tight": 239}},  # 放得下：寫全
        {"end": {"full": 239, "snug": 229, "tight": 207}, "tag": {"full": 236, "snug": 239, "tight": 239}},  # 寫全碰到，收一號放得下
        {"end": {"full": 262, "snug": 250, "tight": 201}, "tag": {"full": 200, "snug": 203, "tight": 203}},  # FB-135：1044/1170、傷 123
    ])
    assert out == [[], ["snug"], ["snug", "tight"]]


@needs_node
def test_fb198_the_stamina_bar_keeps_clear_of_the_pill_button():
    """體力條同一條規則：字尾離丹的鈕至少留 3px；沒有丹的鈕、沒有內傷、條還沒排版（寬 0）都不量、照寫全；上一次留下的 class 先拿掉。"""
    out = _fit([
        {"pill": True, "end": {"full": 98, "snug": 92, "tight": 70}, "tag": 102},  # 98＋3 ≤ 102：放得下
        {"pill": True, "end": {"full": 100, "snug": 92, "tight": 70}, "tag": 102},  # 100＋3 > 102：收一號
        {"end": 300, "tag": None},  # 沒有「傷 N」（沒有內傷）
        {"end": 300, "tag": 100, "width": 0},  # 還沒排版
        {"end": 100, "tag": 200, "start": ["snug", "tight"]},  # 上一次收過、這一次放得下：拿掉
    ])
    assert out == [[], ["snug"], [], [], []]


# ── FB-220：贈物送滿之後，卡上灰掉的「贈銀兩」「贈回體丹」被右邊那句原因擠成一字一行（鈕高 103px）──
# 名字包一格不折行（.pa-name）；說明放得下就跟名字並排，放不下換到名字底下一行、照空白與標點折（375 寬實機：103px → 75px，
# 同一張卡上的「邀他結伴同行」63px → 75px，名字不再被折成兩行；「身上 50 兩」這種短的照舊並排，48px）。原因那一句字不改。


@needs_node
def test_fb220_a_full_gift_button_keeps_its_name_on_one_line(content):
    import json

    from test_prologue_web import run
    from test_shop2_web import _css, _rule
    from test_social import _player

    from tianxia import social

    cap = content.config.gift_per_pair_day
    a = _player(content, "甲")
    b = _player(content, "乙")
    a.state.player.stats["silver"], a.state.player.stamina_pills = 50, 3
    for _ in range(cap):
        a.peer_act("乙", "gift", {"arg": "silver", "amount": 1})
    card = social.card(a, b)
    full = social.pair_full(a, "gift")
    assert [x["note"] for x in card["actions"] if x["action"] == "gift"] == [full, full]  # 原因那一句字不改
    out = run(server.main_view(a), "H.S.peer = { name: '乙', card: CARD }; return H.peerHtml();".replace("CARD", json.dumps(card, ensure_ascii=False)))
    assert f'disabled><span class="pa-name">贈銀兩</span><small>{full}</small></button>' in out
    assert f'disabled><span class="pa-name">贈回體丹</span><small>{full}</small></button>' in out
    css = _css()
    assert "white-space: nowrap" in _rule(css, ".peer-acts .btn .pa-name") and "flex: none" in _rule(css, ".peer-acts .btn .pa-name")
    assert "flex-wrap: wrap" in _rule(css, ".peer-acts .btn")  # 說明放不下就換到名字底下一行
    note = _rule(css, ".peer-acts .btn small")
    assert "min-width: 0" in note and "word-break: keep-all" in note and "overflow-wrap: anywhere" in note  # 照空白、標點折，太長才硬折


@needs_node
def test_fb220_every_card_button_wraps_its_name(content):
    """卡上每一顆鈕（論武出哪一樣收成下拉清單那一顆也是）名字都包一格，沒有說明的照樣包。"""
    import json

    from test_prologue_web import run
    from test_social import _player

    actions = [
        {"action": "greet", "label": "抱拳", "enabled": True},
        {"action": "spar", "label": "切磋", "enabled": True, "note": "體力 6・勝算 五五波"},
        {"action": "discuss", "label": "出流雲劍", "group": "論武", "pick": "流雲劍", "enabled": True},
        {"action": "discuss", "label": "出風", "group": "論武", "pick": "風", "enabled": True},
    ]
    card = {"name": "乙", "affiliation": "散人", "level": 1, "record": "", "arts": [], "actions": actions}
    script = "H.S.peer = { name: '乙', card: CARD }; return H.peerHtml();".replace("CARD", json.dumps(card, ensure_ascii=False))
    out = run(server.main_view(_player(content, "甲")), script)
    assert '<span class="pa-name">抱拳</span></button>' in out and '<span class="pa-name">切磋</span><small>體力 6・勝算 五五波</small>' in out
    assert 'data-act="peer-pick"><span class="pa-name">論武</span></button>' in out


# ── FB-221：黃巾在潁川汝南的攻城只寫「到潁川汝南一帶遊歷」，記得了次數的地方卻只有官軍大營 ──
# 攻城記得了次數的地點（orders.siege_places）只有一兩處時，卡上寫出地名（atlas.siege_how，order_how 攻城那一支）；
# 沒摸清的只寫大區、不洩漏名字（同打擊）；三處以上照舊寫一帶。


def _siege_card(on, faction, front, at, visited=()):
    from test_orders import _game, _order

    game = _game(on, faction=faction, at=at)
    game.state.player.visited = list(visited)
    _order(game, "siege", faction, front=front)
    [card] = [c for c in game.orders_view() if c["title"].startswith("攻城")]
    return card["how"]


def test_fb221_the_yellow_turbans_siege_names_the_government_camp(on):
    from conftest import classic_rules, closed_map
    from tianxia import atlas, orders

    classic_rules(on)  # FB-221 的攻城地名照舊站法（出陣探索與地盤之前）；地盤開著時照控制方，另見 tests/test_territory.py
    closed_map(on)  # 「還沒摸清只寫大區」是全圖開放之前的規則；全圖開放的見 tests/test_open_map.py
    assert orders.siege_places(on, "huang", "yingru") == ["guan_camp"]
    known = _siege_card(on, "huang", "yingru", at="guangzong", visited=["guan_camp"])
    assert known == "到官軍大營遊歷，打贏一場官軍記一次。" == atlas.SIEGE_AT.format(where="官軍大營", enemy="官軍", note="")
    unseen = _siege_card(on, "huang", "yingru", at="guangzong")  # 還沒摸清：只寫大區，不寫「官軍大營」
    assert "官軍大營" not in unseen and unseen == f"到潁川汝南一帶遊歷，打贏一場官軍記一次{atlas.SIEGE_UNSEEN}。"


def test_fb221_two_places_are_both_named_and_an_unseen_one_stays_a_region(on):
    from conftest import classic_rules, closed_map
    from tianxia import atlas, orders

    classic_rules(on)  # FB-221 的攻城地名照舊站法（出陣探索與地盤之前）；地盤開著時照控制方，另見 tests/test_territory.py
    closed_map(on)  # 「另一處你還沒摸清」是全圖開放之前的規則；全圖開放的見 tests/test_open_map.py
    assert orders.siege_places(on, "huang", "jizhou") == ["luzhi_camp", "baima_ford"]
    both = _siege_card(on, "huang", "jizhou", at="nanyang_wilds", visited=["luzhi_camp", "baima_ford"])
    assert both == "到盧植營或白馬津遊歷，打贏一場官軍記一次。"
    one = _siege_card(on, "huang", "jizhou", at="nanyang_wilds", visited=["luzhi_camp"])
    assert one == f"到盧植營或冀州一帶遊歷，打贏一場官軍記一次{atlas.SIEGE_SOME_UNSEEN}。" and "白馬津" not in one


def test_fb221_three_or_more_places_still_say_the_whole_front(on):
    from conftest import classic_rules
    from tianxia import atlas, orders

    classic_rules(on)  # FB-221 的攻城地名照舊站法（出陣探索與地盤之前）；地盤開著時照控制方，另見 tests/test_territory.py
    places = orders.siege_places(on, "guan", "yingru")
    assert len(places) > atlas.SIEGE_NAMED_MAX
    assert _siege_card(on, "guan", "yingru", at="changshe", visited=places) == "到潁川汝南一帶遊歷，打贏一場對面的兵記一次。"
