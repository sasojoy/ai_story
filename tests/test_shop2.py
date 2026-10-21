"""店面第二批：馬市與懸賞榜（docs/superpowers/specs/2026-10-13-店面獨立介面-design.md 第三、四節；
計畫 docs/superpowers/plans/2026-10-13-店面-2-馬市與懸賞榜.md）。"""
from __future__ import annotations

import json
import random

import pytest

from conftest import real_content
from tianxia import bounties, equipment, mounts, shopview
from tianxia.content import validate
from tianxia.models import FactionDef
from tianxia.state import Bounty, Equipment

LINES = {shop: {key: [f"{shop}說{key}之一。", f"{shop}說{key}之二。"] for key in keys} for shop, keys in shopview.SITUATIONS.items()}
NOW = 1000.0
WEEK = 10_000_000.0  # 測試裡的懸賞一律掛到很久以後（同 tests/test_bounties.py）
SWORD = dict(id="兵:1", slot="weapon", name="試劍", kind="劍", attribute="剛", tier=1, quality="下品")
SCOUT = dict(kind="scout", faction="guan", silver=10, deeds=2, location="lake")
STRIKE = dict(kind="strike", faction="guan", silver=20, deeds=3, location="lake", squad="thug")
ARMS = dict(kind="arms", faction="guan", silver=0, deeds=2, attribute="剛", weapon_kind="劍", quota=3)


def _horse(hid="騎:1", name="青驄駒", tier=2, quality="中品", edge=100):
    return Equipment(id=hid, slot="mount", name=name, tier=tier, quality=quality, edge=edge)


def _market(content, world, silver=200, horse=None, name="試馬"):
    """坐騎開著、測試內容的小鎮臨時加上「馬市」標籤（同 tests/test_mounts.py::_market_game）、店面的字照 LINES；
    背包：精鐵砂 ×2（一階，餵得了）。走進馬市（act:market）。"""
    from tianxia.engine import Game

    content.config.mounts.enabled = True
    if mounts.MARKET_TAG not in content.locations["town"].tags:
        content.locations["town"].tags.append(mounts.MARKET_TAG)
    content.shop_lines = LINES
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    game.sync(0.0)
    p = game.state.player
    p.location, p.stamina, p.stats["silver"], p.mount = "town", 100.0, silver, horse
    p.materials = {"gang_1": 2}
    game.choose("act:market")
    return game


def _board(content, world, posts=(), name="試榜", faction=None):
    """劇本兩個陣營（官軍 join_at 小鎮、黃巾 join_at 湖邊，同 tests/test_bounties.py 的 setup）、兵器開著（求兵要）、店面的字照 LINES。
    posts 有東西時先把開季自動掛的單拿掉、照順序貼這幾張（同 test_bounties._post，掛到很久以後），直接貼在這一份 Game 的季上再存季；
    沒給就照季上原本的（另一個角色先貼好的）。走進懸賞榜（act:bounties）。"""
    from tianxia import rules
    from tianxia.engine import Game

    content.scenario.factions = [FactionDef(id="guan", name="官軍", join_at=["town"]), FactionDef(id="huang", name="黃巾", join_at=["lake"])]
    content.config.weapons.enabled = True
    content.shop_lines = LINES
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    rules.learn_skill(game.state, content, "fist")
    p = game.state.player
    p.faction, p.location, p.stamina, p.stats["silver"] = faction, "town", 100.0, 200
    game.sync(NOW)
    if posts:
        w = game.state.world
        w.bounties = []
        for kw in posts:
            w.bounty_seq += 1
            w.bounties.append(Bounty(id=f"b{w.bounty_seq}", week=1, expires=WEEK, **kw))
        game._save_season()
    game.choose("act:bounties")
    return game


def _ids(game):
    return [b.id for b in game.state.world.bounties]


# ── Task 1：馬販與榜吏的話、記情況鍵、收起店 ──


def test_the_market_and_board_lines_load_and_every_situation_is_required():
    c = real_content()
    for shop in ("market", "board"):
        for key in shopview.SITUATIONS[shop]:
            assert c.shop_lines[shop][key], (shop, key)
    validate(c)
    from tianxia.content import ContentError

    for shop, key in (("market", "feed"), ("board", "give")):
        c = real_content()
        del c.shop_lines[shop][key]
        with pytest.raises(ContentError, match=key):
            validate(c)
    c = real_content()
    c.shop_lines["market"]["haggle"] = ["馬販殺價。"]
    with pytest.raises(ContentError, match="不認得的情況"):
        validate(c)


def test_the_board_key_sorts_the_take_refusals():
    assert shopview.board_key(None, "take") == "take"
    assert shopview.board_key(bounties.HELD_FULL.format(count=3), "take") == "held_full"
    assert shopview.board_key(bounties.WANTED_NEWBIE, "take") == "refused"


def test_each_market_action_records_a_keeper_situation(content, world):
    game = _market(content, world, silver=300)
    p = game.state.player
    assert p.shop_line == "enter" and shopview.line_text(game.state, content, "market") in LINES["market"]["enter"]
    game.choose(mounts.BUY)  # 沒有馬：買下來直接騎上
    assert p.shop_line == "buy"
    game.choose(mounts.BUY)  # 第二匹進裝備庫
    assert p.shop_line == "buy"
    p.mount.edge = 40
    game.choose(mounts.FEED)
    assert p.shop_line == "feed"
    other = equipment.in_slot(p, "mount")[0].id
    game.choose(f"{mounts.WIELD}{other}")
    assert p.shop_line == "wield"
    p.stats["silver"] = 10
    game._market("buy")  # 灰掉的鈕在 choose 的選單那一關就擋下：直接叫，等於兩個分頁搶
    assert p.shop_line == "short_silver"
    game._market("feed")  # 換上的那一匹吃飽了
    assert p.shop_line == "refused"
    game.choose(mounts.BACK)
    assert (p.picking_market, p.shop_line, p.shop_clue) == (False, "", "")


def test_each_board_action_records_a_keeper_situation(content, world):
    game = _board(content, world, [SCOUT, dict(SCOUT, location="cave"), ARMS])
    scout, scout2, arms = _ids(game)
    p = game.state.player
    assert p.shop_line == "enter" and shopview.line_text(game.state, content, "board") in LINES["board"]["enter"]
    game.choose(f"bounty:take:{scout}")
    assert p.shop_line == "take"
    game.choose(f"bounty:drop:{scout}")
    assert p.shop_line == "drop"
    p.rack = [Equipment(**SWORD)]
    game.choose(f"bounty:pick:{arms}")
    assert p.shop_line == "pick"
    game.choose(f"bounty:give:{arms}:兵:1")
    assert p.shop_line == "give" and p.bounty_pick is None
    game._bounty("take:b999")  # 下榜了
    assert p.shop_line == "refused"
    content.config.bounties.max_taken = 1
    game.choose(f"bounty:take:{scout}")
    game._bounty(f"take:{scout2}")  # 手上揭滿了（選單上灰掉的鈕，直接叫）
    assert p.shop_line == "held_full"
    game._bounty("drop:b999")
    assert p.shop_line == "refused"
    game.choose("bounty:back")
    assert (p.picking_bounty, p.bounty_pick, p.shop_line) == (False, None, "")


def test_walking_off_or_reloading_clears_the_shop_line(content, world):
    from tianxia.engine import Game

    game = _market(content, world)
    p = game.state.player
    p.location = "lake"  # 湖邊沒有馬市：同步時收起
    game.sync(10.0)
    assert (p.picking_market, p.shop_line) == (False, "")
    game = _board(content, world, [SCOUT], name="讀檔")
    game.state.player.location = "lake"  # 湖邊不是城鎮：讀檔修補時收起懸賞榜
    again = Game(content, game.state, random.Random(0), world)
    assert (again.state.player.picking_bounty, again.state.player.shop_line) == (False, "")


# ── Task 2：market_view 與 shop_view 的分派 ──


def test_the_abilities_match_the_practice_page_row(content, world):
    content.config.mounts.enabled = True
    horse = _horse(edge=40)
    got = mounts.abilities(content, horse)
    game = _market(content, world, horse=horse)
    row = mounts.rows(game.state, content)["worn"]
    assert (row["save"], row["speed"], row["cavalry"], row["escape"]) == tuple(mounts.pct(got[k]) for k in ("save", "speed", "cavalry", "escape"))
    assert got["save"] == mounts.leg_power(content, horse) and got["speed"] == mounts.speed_of(content, horse)


def test_no_horse_has_an_empty_stall_and_focuses_the_sale(content, world):
    game = _market(content, world)
    view = game.shop_view()
    price = content.config.mounts.shop_price
    assert (view["shop"], view["back"], view["sign"]) == ("market", mounts.BACK, f"{content.locations['town'].name}{mounts.MARKET}")
    empty, sale = view["stalls"]
    assert empty["empty"] and empty["name"] == shopview.NO_HORSE and empty["who"] == shopview.STALL_WHO["worn"]
    assert sale["role"] == "sale" and sale["id"] == "架:馬" and view["focus"] == "架:馬"
    assert sale["action"] == {"id": mounts.BUY, "label": shopview.BUY_TEXT.format(price=price), "use": "", "enabled": True, "why": None}
    assert [b["label"] for b in sale["bars"]] == ["省體力", "路上快", "決戰騎兵", "落敗脫身"] and sale["fed"] is None
    fresh = mounts.fresh_power(content, mounts.shop_item(game.state, content))
    assert sale["bars"][0]["text"] == mounts.pct(fresh) and sale["bars"][0]["value"] == mounts.half_up(fresh * 100)
    assert sale["coat"] == mounts.COATS.index(mounts.coat_for("town")) and sale["sub"].endswith(f"{price} 兩")


def test_the_ridden_horse_feeds_and_the_rack_compares(content, world):
    ride = _horse(edge=40)
    game = _market(content, world, horse=ride)
    game.state.player.rack = [_horse("騎:2", "黑鬃馬", 1, "下品"), _horse("騎:3", "白蹄駒", 3, "下品")]  # FB-194 之後照卡上的路上快（含飽足）比
    view = game.shop_view()
    worn, _sale, slow, fast = view["stalls"]
    assert worn["id"] == "騎:1" and view["focus"] == "騎:1"
    assert worn["fed"] == {"word": mounts.WEAR_WORD, "value": 40, "note": shopview.HUNGRY_NOTE}
    assert worn["action"]["id"] == mounts.FEED and worn["action"]["enabled"] and "精鐵砂×1" in worn["action"]["use"]
    assert (slow["compare"], fast["compare"]) == (shopview.SLOWER, shopview.FASTER)
    assert fast["action"] == {"id": f"{mounts.WIELD}騎:3", "label": shopview.WIELD_TEXT, "use": "", "enabled": True, "why": None}
    ride.edge = 100
    worn = game.shop_view()["stalls"][0]
    assert not worn["action"]["enabled"] and worn["action"]["why"] == mounts.NOT_HUNGRY and worn["fed"]["note"] == ""


def test_buying_is_greyed_with_the_rule_reason(content, world):
    game = _market(content, world, silver=50)
    assert game.shop_view()["stalls"][1]["action"]["why"] == f"還差 {content.config.mounts.shop_price - 50} 兩"
    game = _market(content, world, name="滿", horse=_horse())
    content.config.weapons.rack_cap = 1
    game.state.player.rack = [_horse("騎:2", "黑鬃馬", 1, "上品")]
    sale = game.shop_view()["stalls"][1]
    assert not sale["action"]["enabled"] and sale["action"]["why"] == equipment.RACK_FULL


def test_no_market_shop_when_switched_off_left_or_in_a_battle(content, world):
    import server

    game = _market(content, world)
    assert server.main_view(game)["shop"]["shop"] == "market"
    assert game.shop_view([mounts.BACK, "battle:join:x"]) is None  # 決戰的鈕在前面：照舊畫那一串（同第一批的 _shop_live）
    content.config.shop_screens = False
    assert game.shop_view() is None and "shop" not in server.main_view(game)
    content.config.shop_screens = True
    game.choose(mounts.BACK)
    assert game.shop_view() is None


def test_the_switch_off_leaves_the_old_market_menu(content, world):
    import server

    on = _market(content, world, name="開", horse=_horse(edge=40))
    content.config.shop_screens = False
    off = _market(content, world, name="關", horse=_horse(edge=40))
    view_off = server.main_view(off)
    content.config.shop_screens = True
    view_on = server.main_view(on)
    assert "shop" not in view_off and view_on["shop"]["shop"] == "market"
    assert [(o["id"], o["label"], o["enabled"]) for o in view_on["options"]] == [(o["id"], o["label"], o["enabled"]) for o in view_off["options"]]


# ── Task 3：board_view ──


def test_held_notes_come_first_with_drop_and_fill_the_held_row(content, world):
    game = _board(content, world, [SCOUT, STRIKE])
    scout, strike = _ids(game)
    game.choose(f"bounty:take:{strike}")
    view = game.shop_view()
    cap = content.config.bounties.max_taken
    assert (view["shop"], view["back"], view["unpick"]) == ("board", "bounty:back", bounties.UNPICK_ID)
    assert view["sign"] == f"{content.locations['town'].name}{bounties.BOARD}"
    assert [n["id"] for n in view["notes"]] == [strike, scout]
    held = view["notes"][0]
    assert held["held"] and held["action"]["verb"] == "drop" and held["action"]["id"] == f"bounty:drop:{strike}"
    assert held["action"]["confirm"] == shopview.DROP_ASK.format(title=held["title"])
    assert [r["id"] for r in view["held"]["rows"]] == [strike]
    assert view["held"]["head"] == shopview.HELD_HEAD.format(n=1, cap=cap) and view["held"]["left_text"] == shopview.SLOT_LEFT.format(n=cap - 1)
    note = view["notes"][1]
    b = game.state.world.bounties[0]
    assert note["head"] == content.locations["lake"].name and note["kind_name"] == "打探" and note["issuer"] == "官軍"
    assert note["action"] == {"id": f"bounty:take:{scout}", "verb": "take", "enabled": True, "why": None}
    assert (note["due"], note["reward"], note["how"]) == (bounties.due_line(game.state, content, b), bounties.reward_text(game.state, content, b), bounties.how(content, b))


def test_take_reasons_come_from_the_rules(content, world):
    game = _board(content, world, [dict(kind="escort", faction="guan", silver=15, deeds=2, location="lake", end="cave"), SCOUT])
    escort, _scout = _ids(game)
    notes = {n["id"]: n for n in game.shop_view()["notes"]}
    assert notes[escort]["action"]["why"] == f"要在{content.locations['lake'].name}接。"
    content.config.bounties.max_taken = 1
    game = _board(content, world, [SCOUT, dict(SCOUT, location="cave")], name="揭滿")
    first, second = _ids(game)
    game.choose(f"bounty:take:{first}")
    notes = {n["id"]: n for n in game.shop_view()["notes"]}
    assert not notes[second]["action"]["enabled"] and notes[second]["action"]["why"] == bounties.HELD_FULL.format(count=1)
    assert game.shop_view()["held"]["left_text"] == ""


def test_hand_ins_say_how_many_fit_and_open_the_third_layer(content, world):
    game = _board(content, world, [ARMS])
    (arms,) = _ids(game)
    p = game.state.player
    p.rack = [Equipment(**SWORD)]
    note = game.shop_view()["notes"][0]
    assert note["have"] == shopview.HAVE_NOTE.format(n=1, unit="把")
    assert note["action"] == {"id": f"bounty:pick:{arms}", "verb": "pick", "enabled": True, "why": None}
    p.rack = []
    note = game.shop_view()["notes"][0]
    assert note["have"] == "" and not note["action"]["enabled"] and note["action"]["why"] == shopview.NO_FIT
    p.rack = [Equipment(**SWORD, original=True)]
    assert game.shop_view()["notes"][0]["action"]["why"] == bounties.ONLY_ORIGINAL.strip("（）")


def test_the_third_layer_is_still_the_board_shop(content, world):
    game = _board(content, world, [ARMS, SCOUT])
    arms, _scout = _ids(game)
    p = game.state.player
    p.rack = [Equipment(**SWORD)]
    game.choose(f"bounty:pick:{arms}")
    ids = [o.id for o in game.options(odds=False)]
    assert "bounty:back" not in ids and bounties.UNPICK_ID in ids  # 第三層的選單
    view = game.shop_view()
    assert view is not None and view["picked"] == arms
    assert [o["id"] for o in view["hand_in"]] == [f"bounty:give:{arms}:兵:1"] and view["hand_in"][0]["label"].startswith("交出【試劍】")
    p.rack = [Equipment(**SWORD, original=True)]  # 交不出了：同 _bounty_options，那一張當它不存在、回到第二層
    view = game.shop_view()
    assert view["picked"] is None and view["hand_in"] == []


def test_an_emptied_board_says_so(content, world):
    game = _board(content, world, [SCOUT])
    b = game.state.world.bounties[0]
    b.done_by = ["別人"]  # 名額被別人交滿了
    view = game.shop_view()
    assert view is not None and view["notes"] == [] and view["empty"] == bounties.BOARD_EMPTY


def test_a_prized_note_says_so_until_someone_hands_it_in(content, world):
    content.config.treasures.enabled = True
    game = _board(content, world, [dict(STRIKE, prize="treasure")])
    assert game.shop_view()["notes"][0]["prize"] == shopview.PRIZE_SHORT
    game.state.world.bounties[0].done_by = ["別人"]
    game.state.world.bounties[0].quota = 2
    assert game.shop_view()["notes"][0]["prize"] == ""


def test_a_wanted_note_never_names_who_posted_it(content, world):
    content.config.raid.enabled = True
    game = _board(content, world, [dict(kind="wanted", faction="huang", silver=80, deeds=3, poster="掛單的人", target="被通緝的人")])
    text = json.dumps(game.shop_view(), ensure_ascii=False)
    assert "被通緝的人" in text and "掛單的人" not in text


def test_no_board_shop_when_switched_off_left_or_in_a_battle(content, world):
    import server

    game = _board(content, world, [SCOUT])
    assert server.main_view(game)["shop"]["shop"] == "board"
    assert game.shop_view(["bounty:back", "battle:join:x"]) is None
    content.config.shop_screens = False
    assert "shop" not in server.main_view(game)
    content.config.shop_screens = True
    game.choose("bounty:back")
    assert game.shop_view() is None


def test_the_switch_off_leaves_the_old_board_menu(content, world):
    import server

    on = _board(content, world, [SCOUT, STRIKE, ARMS], name="開")
    content.config.shop_screens = False
    off = _board(content, world, name="關")  # 同一季：照「開」貼好的那幾張
    view_off = server.main_view(off)
    content.config.shop_screens = True
    view_on = server.main_view(on)
    assert "shop" not in view_off and view_on["shop"]["shop"] == "board"
    assert [(o["id"], o["label"], o["enabled"]) for o in view_on["options"]] == [(o["id"], o["label"], o["enabled"]) for o in view_off["options"]]


# ── Task 8：FB-192 被拒的那一句照眼前的狀態 ──


def test_a_short_of_silver_line_gives_way_once_the_silver_is_there(content, world):
    """FB-192：錢不夠被拒之後，錢補夠了，掌櫃那一句就換回平常那一句（不必等下一個動作）；還是不夠就照舊。"""
    from test_shop import _smith

    game = _smith(content, world, name="補錢")
    p = game.state.player
    p.stats["silver"] = 10
    game._smith("buy:劍")  # 灰掉的鈕：直接叫，等於兩個分頁搶
    lines = content.shop_lines["smith"]
    assert p.shop_line == "short_silver" and shopview.line_text(game.state, content, "smith") in lines["short_silver"]
    p.stats["silver"] = content.config.weapons.shop_price - 1
    assert shopview.line_text(game.state, content, "smith") in lines["short_silver"]
    p.stats["silver"] = 300
    assert shopview.line_text(game.state, content, "smith") in lines["enter"]


def test_a_full_rack_line_gives_way_once_there_is_room(content, world):
    game = _market(content, world, silver=300, horse=_horse())
    content.config.weapons.rack_cap = 1
    p = game.state.player
    p.rack = [_horse("騎:2", "黑鬃馬", 1, "上品")]
    game._market("buy")
    assert p.shop_line == "rack_full" and shopview.line_text(game.state, content, "market") in LINES["market"]["rack_full"]
    p.rack = []
    assert shopview.line_text(game.state, content, "market") in LINES["market"]["enter"]


def test_a_plain_refusal_gives_way_once_anything_changes(content, world):
    game = _market(content, world, horse=_horse())  # 吃飽的馬：餵被拒
    p = game.state.player
    game._market("feed")
    assert shopview.line_text(game.state, content, "market") in LINES["market"]["refused"]
    p.mount.edge = 40  # 走了一段路，餓了：被拒的原因不成立了
    assert shopview.line_text(game.state, content, "market") in LINES["market"]["enter"]


def test_a_held_full_line_gives_way_once_a_slot_frees(content, world):
    content.config.bounties.max_taken = 1
    game = _board(content, world, [SCOUT, dict(SCOUT, location="cave")])
    first, second = _ids(game)
    game.choose(f"bounty:take:{first}")
    game._bounty(f"take:{second}")
    assert shopview.line_text(game.state, content, "board") in LINES["board"]["held_full"]
    game.state.world.bounties[0].takers = []  # 手上那一張作廢了（過期、被交滿）
    assert shopview.line_text(game.state, content, "board") in LINES["board"]["enter"]


def test_closing_a_shop_clears_the_hold(content, world):
    game = _market(content, world, horse=_horse())
    game._market("feed")
    assert game.state.player.shop_hold.startswith("same:")
    game.choose(mounts.BACK)
    assert game.state.player.shop_hold == ""
