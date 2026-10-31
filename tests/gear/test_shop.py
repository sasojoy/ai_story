"""店面第一批：共用店面與鐵匠鋪（docs/superpowers/specs/2026-10-13-店面獨立介面-design.md；
計畫 docs/superpowers/plans/2026-10-13-店面-1-共用店面與鐵匠鋪.md）。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import equipment, shopview, smithing, weapons
from tianxia.content import validate

LINES = {"smith": {key: [f"鐵匠說{key}之一。", f"鐵匠說{key}之二。"] for key in shopview.SITUATIONS["smith"]}}


def _smith(content, world, silver=300, name="試鋪"):
    """測試內容的城鎮（town）、兵器防具都開著、店面的字照 LINES；身上那門是流雲劍（柔・劍）；背包：精鐵砂 ×4、玄鋼骨 ×1、驚羽 ×2。
    走進鐵匠鋪（act:smith）。"""
    from tianxia import rules
    from tianxia.engine import Game

    content.config.weapons.enabled = content.config.armor.enabled = True
    content.shop_lines = LINES
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    rules.learn_skill(game.state, content, "sword")
    p = game.state.player
    p.location, p.stamina, p.stats["silver"], p.stats["wis"] = "town", 100.0, silver, 5
    p.member.wugong_id = "sword"
    p.materials = {"gang_1": 4, "gang_2": 1, "kuai_1": 2}
    game.sync(0.0)
    game.choose("act:smith")
    return game


# ── Task 1：開關、掌櫃的話與存檔欄位 ──


def test_the_switch_is_on_by_default_and_the_lines_load_from_content():
    c = real_content()
    assert c.config.shop_screens is True
    for key in shopview.SITUATIONS["smith"]:
        assert c.shop_lines["smith"][key], key
    validate(c)


def test_a_missing_situation_is_refused_when_the_smithy_is_open():
    from tianxia.content import ContentError

    c = real_content()
    del c.shop_lines["smith"]["temper"]
    with pytest.raises(ContentError, match="temper"):
        validate(c)
    c = real_content()
    c.shop_lines["smith"]["buy"] = [" "]
    with pytest.raises(ContentError, match="空白"):
        validate(c)
    c = real_content()
    c.shop_lines["inn"] = {"enter": ["掌櫃說話。"]}
    with pytest.raises(ContentError, match="不認得的店"):
        validate(c)


@pytest.mark.smoke
def test_entering_and_each_smith_action_record_a_keeper_situation(content, world):
    game = _smith(content, world)
    p = game.state.player
    assert p.shop_line == "enter" and shopview.line_text(game.state, content, "smith") in LINES["smith"]["enter"]
    game.choose("smith:buy:劍")
    assert p.shop_line == "buy"
    p.stats["silver"] = 3
    game.choose("smith:buy:刀")  # 灰掉的鈕：choose 在選單那一關就擋下，掌櫃那一句不動（錢不夠那一句留給開爐被拒絕，Task 4）
    assert p.shop_line == "buy"
    p.stats["silver"] = 300
    p.weapon.edge = 40
    game.choose("smith:repair")
    assert p.shop_line == "repair"
    game.choose("smith:temper")
    assert p.shop_line == "temper"
    game.choose("smith:back")
    assert (p.shop_line, p.shop_clue) == ("", "")


def test_the_keeper_line_stays_put_across_polls(content, world):
    game = _smith(content, world)
    first = shopview.line_text(game.state, content, "smith")
    game.sync(50.0)
    assert shopview.line_text(game.state, content, "smith") == first
    lines = {shopview.line_text(game.state, content, "smith") for _ in range(5)}
    assert lines == {first}


def test_problem_and_forged_keys():
    from tianxia.state import Weapon

    assert shopview.problem_key(None, "buy") == "buy"
    assert shopview.problem_key("還差 12 兩", "buy") == "short_silver"
    assert shopview.problem_key(equipment.RACK_FULL, "buy") == "rack_full"
    assert shopview.problem_key("刀口還利", "repair") == "refused"
    w = Weapon(id="兵:1", name="試刃", kind="劍", attribute="剛", tier=1, quality="中品")
    assert shopview.forged_key(w) == "forge_mid"
    assert shopview.forged_key(w.model_copy(update={"secret": "t_blade"})) == "forge_named"
    assert shopview.forged_key(w.model_copy(update={"original": True})) == "forge_divine"
    assert shopview.forged_key(w.model_copy(update={"copy_of": "鑄|t_star"})) == "forge_divine"


def test_the_smith_clue_takes_over_the_keeper_line_for_one_action(content, world, monkeypatch):
    game = _smith(content, world)
    monkeypatch.setattr(game, "_smith_clue", lambda paid=True: ["鐵匠順口說了一句口訣。"])
    game.choose("smith:buy:劍")
    assert shopview.line_text(game.state, content, "smith") == "鐵匠順口說了一句口訣。"
    game.choose("smith:page:armor")
    assert shopview.line_text(game.state, content, "smith") in LINES["smith"]["buy"]


# ── Task 2：smith_view 與 main_view ──


def test_the_smith_view_lists_the_shelf_with_the_rule_reasons(content, world):
    import server

    game = _smith(content, world)
    view = game.shop_view()
    assert (view["shop"], view["sign"], view["back"], view["page"]) == ("smith", f"{content.locations['town'].name}鐵匠鋪", "smith:back", "weapon")
    assert [p["slot"] for p in view["pages"]] == ["weapon", "armor"] and view["silver"] == 300
    shelf = {x["kind"]: x for x in view["shelf"]}
    assert len(view["shelf"]) == 6 and shelf["劍"]["fit"] and shelf["劍"]["id"] == "smith:buy:劍" and shelf["劍"]["enabled"]
    game.state.player.stats["silver"] = 10
    view = game.shop_view()
    assert all(not x["enabled"] and x["why"] == "還差 30 兩" for x in view["shelf"])
    assert server.main_view(game)["shop"] == view


def test_the_armor_page_and_the_worn_card(content, world):
    game = _smith(content, world)
    game.choose("smith:buy:劍")
    worn = game.shop_view()["worn"]
    assert worn["item"]["name"] == game.state.player.weapon.name and worn["item"]["wear_word"] == "鋒利度"
    assert not worn["repair"]["enabled"] and worn["repair"]["why"] == weapons.KEEN["劍"]
    assert worn["temper"]["enabled"] and "精鐵砂×1" in worn["temper"]["use"]
    game.choose("smith:page:armor")
    view = game.shop_view()
    assert view["page"] == "armor" and [x["attribute"] for x in view["shelf"]] == ["剛", "柔", "快", "慢"]
    assert view["worn"]["item"] is None and view["worn"]["empty"]
    assert view["forge"]["kinds"] == [] and view["forge"]["kind"] == smithing.ARMOR_KIND


def test_only_one_slot_open_has_no_page_switch(content, world):
    game = _smith(content, world)
    content.config.armor.enabled = False
    view = game.shop_view()
    assert [p["slot"] for p in view["pages"]] == ["weapon"]


def test_the_rack_rows_keep_the_dismantle_reasons_and_the_naming(content, world):
    from tianxia.state import Weapon

    game = _smith(content, world)
    p = game.state.player
    p.weapon = Weapon(id="兵:9", name="手上刃", kind="劍", attribute="柔", tier=1, quality="下品")
    p.rack = [Weapon(id=f"兵:{i}", name=f"庫刃{i}", kind="刀", attribute="剛", tier=1, quality="下品") for i in range(1, 11)]
    p.rack[3].original, p.rack[3].secret = True, "t_star"
    rows = game.shop_view()["rack"]["rows"]
    assert len(rows) == 10 and next(r for r in rows if r["id"] == "兵:4")["keep"] == equipment.ORIGINAL_KEPT
    assert all(r["confirm"] for r in rows if r["id"] != "兵:4")


def test_no_shop_when_closed_or_switched_off(content, world):
    import server
    from tianxia.state import SmithDraft

    game = _smith(content, world)
    content.config.shop_screens = False
    assert game.shop_view() is None and "shop" not in server.main_view(game)
    content.config.shop_screens = True
    game.state.player.location = "lake"  # 測試內容的湖邊不是城鎮：同步時收起鐵匠鋪
    game.sync(10.0)
    assert game.shop_view() is None and "shop" not in server.main_view(game)
    game = _smith(content, world, name="單子")
    game.state.player.smith_draft = SmithDraft()  # 舊存檔的一步一步單子還開著：照舊畫那一串按鈕
    assert game.shop_view() is None


def test_the_switch_off_leaves_the_old_menu(content, world):
    import server

    on = _smith(content, world, name="開")
    content.config.shop_screens = False
    off = _smith(content, world, name="關")
    view_off = server.main_view(off)
    content.config.shop_screens = True
    view_on = server.main_view(on)
    assert "shop" not in view_off and "shop" in view_on
    assert [o["id"] for o in view_on["options"]] == [o["id"] for o in view_off["options"]]


# ── Task 3：這一爐會怎樣 ──


def test_cells_say_why_a_material_cannot_go_in(content, world):
    game = _smith(content, world, silver=30)
    line = game.smith_line("劍")
    cells = {c["id"]: c for c in line["cells"]}
    assert cells["gang_1"]["ok"] and cells["gang_1"]["to"] == "main"
    assert not cells["gang_2"]["ok"] and cells["gang_2"]["why"] == shopview.SHORT_CELL.format(n=30)  # 二階工錢 60
    game.state.player.materials["kuai_1"] = 1
    line = game.smith_line("劍", "kuai_1")
    cells = {c["id"]: c for c in line["cells"]}
    assert cells["kuai_1"]["main"] and not cells["kuai_1"]["ok"] and cells["kuai_1"]["why"] == shopview.ONLY_ONE
    assert cells["gang_1"]["ok"] and cells["gang_1"]["to"] == "aux"


def test_a_ready_pot_shows_the_same_odds_as_the_go_button(content, world):
    from tianxia import fusion

    game = _smith(content, world)
    line = game.smith_line("劍", "gang_1", "kuai_1")
    assert line["ready"] and line["problem"] is None and line["price"] == 20 and line["tier"] == "一階"
    odds = smithing.forge_odds(game.state, content, world, "劍", "gang_1", "kuai_1")
    assert "、".join(f"{o['q']} {o['pct']}%" for o in line["odds"] if o["pct"] > 0) in fusion.quality_odds_text(odds)
    option = smithing.go_option(game.state, content, world, "劍", "gang_1", "kuai_1")
    assert fusion.quality_odds_text(odds) in option.label and line["head"] == ""


def test_the_line_never_names_a_secret_your_book_has_not_solved(content, world):
    from test_forge_secrets import BLADE

    content.forge_secrets = {BLADE.id: BLADE.model_copy(deep=True)}
    content.config.forge_secrets.per_season = {"weapon:1": 1}
    game = _smith(content, world)
    assert game.smith_line("劍", "gang_1", "kuai_1")["head"] == ""
    smithing.forge(game.state, content, world, "劍", "gang_1", "kuai_1", rng=random.Random(0))  # 打中一次：記進自己的鑄譜
    assert game.smith_line("劍", "gang_1", "kuai_1")["head"] == smithing.SOLVED_HEAD.format(name=BLADE.name).removeprefix(" → ")


def test_a_full_rack_blocks_every_cell_and_says_so_once(content, world):
    from tianxia.state import Weapon

    game = _smith(content, world)
    p = game.state.player
    p.weapon = Weapon(id="兵:99", name="手上刃", kind="劍", attribute="柔", tier=1, quality="下品")
    p.rack = [Weapon(id=f"兵:{i}", name=f"庫刃{i}", kind="刀", attribute="剛", tier=1, quality="下品") for i in range(content.config.weapons.rack_cap)]
    line = game.smith_line("劍")
    assert line["rack_full"] == equipment.RACK_FULL and not any(c["ok"] for c in line["cells"])


def test_bad_input_is_trimmed_to_what_you_hold(content, world):
    game = _smith(content, world)
    line = game.smith_line("劍", "nope", "kuai_1")
    assert (line["main"], line["aux"], line["ready"]) == (None, None, False)
    assert game.smith_line("不是兵器")["cells"] == []
    assert game.shop_view()["forge"]["line"] == game.smith_line(game.shop_view()["forge"]["kind"])


# ── Task 4：直接開爐 ──


def _both(content, world, kind, main, aux, seed=7):
    """同一個名號、同一個種子各打一爐：一個照一步一步的單子（smith:forge → 種類 → 主料 → 輔料 → 開爐），一個直接開爐。
    回（單子那一件, 直接那一件, 兩個 game）。防具的亂數照名號，所以兩邊同名。"""
    step = _smith(content, world, name="同名")
    if smithing.is_armor(kind):
        step.choose("smith:page:armor")
    step.rng = random.Random(seed)
    for option in smithing.wizard_steps(kind, main, aux):
        step.choose(option)
    direct = _smith(content, world, name="同名")
    direct.rng = random.Random(seed)
    direct.smith_forge(kind, main, aux)
    slot = smithing.slot_of(kind)
    return equipment.worn(step.state.player, slot), equipment.worn(direct.state.player, slot), step, direct


@pytest.mark.parametrize("kind", ["劍", smithing.ARMOR_KIND])
def test_direct_forging_matches_the_step_by_step_forge(content, world, kind):
    a, b, step, direct = _both(content, world, kind, "gang_1", "kuai_1")
    same = lambda i: (i.name, i.attribute, i.tier, i.quality, i.recipe)  # noqa: E731
    assert a is not None and same(a) == same(b)
    sp, dp = step.state.player, direct.state.player
    assert (sp.materials, sp.stats["silver"], sp.forge_counts) == (dp.materials, dp.stats["silver"], dp.forge_counts)
    top, old = direct.state.journal[0], step.state.journal[0]
    assert top.title == smithing.FORGE_TITLE and (top.lines, top.changes) == (old.lines, old.changes)
    assert dp.smith_draft is None and dp.shop_line == shopview.forged_key(b)


def test_two_direct_forges_make_two_journal_entries(content, world):
    game = _smith(content, world)
    game.smith_forge("劍", "gang_1", "kuai_1")
    game.smith_forge("刀", "gang_1", "gang_1")
    assert [e.title for e in game.state.journal[:2]] == [smithing.FORGE_TITLE, smithing.FORGE_TITLE]


def test_a_stale_pot_is_refused_without_cost(content, world):
    game = _smith(content, world)
    p = game.state.player
    before = (dict(p.materials), p.stats["silver"], len(game.state.journal), p.weapon_serial)
    msgs = game.smith_forge("劍", "gang_2", "gang_2")  # 玄鋼骨只剩一個：主輔同一種要兩個
    assert msgs == ["（玄鋼骨不夠（要 2 個）。）"] and game.smith_result is None
    assert (dict(p.materials), p.stats["silver"], len(game.state.journal), p.weapon_serial) == before
    assert p.shop_line == "refused"
    p.stats["silver"] = 5
    assert game.smith_forge("劍", "gang_1", "kuai_1") == ["（還差 15 兩。）"] and p.shop_line == "short_silver"
    game.choose("smith:back")
    assert game.smith_forge("劍", "gang_1", "kuai_1") == [equipment.NOT_NOW]


def test_the_forged_card_says_where_it_went_and_glows_by_quality(content, world):
    game = _smith(content, world)
    game.smith_forge("劍", "gang_1", "kuai_1")
    card = game.smith_result
    item = game.state.player.weapon
    assert card["id"] == item.id and card["where"] == "worn" and card["grade"] == equipment.grade(item)
    assert card["glow"] == {"下品": "none", "中品": "cyan", "上品": "gold"}[item.quality] and card["first"] is False
    game.smith_forge("劍", "gang_1", "kuai_1")
    assert game.smith_result["where"] == "rack"


def test_a_first_find_and_a_divine_original_show_on_the_card(content, world):
    from test_forge_divine import STAR
    from test_forge_secrets import BLADE

    content.forge_secrets = {r.id: r.model_copy(deep=True) for r in (BLADE, STAR)}
    content.config.forge_secrets.per_season = {"weapon:1": 1, "weapon:divine": 1}
    game = _smith(content, world, silver=1000)
    game.state.player.materials.update({"gang_3": 4})
    game.smith_forge("劍", "gang_1", "kuai_1")
    assert game.smith_result["first"] and game.smith_result["glow"] == "purple"
    game.smith_forge("劍", "gang_3", "gang_3")
    card = game.smith_result
    assert card["glow"] == "redgold" and card["first"] and card["divine"] == STAR.name and card["where"] == "rack"


def test_the_server_returns_the_forged_card(content, world):
    import server

    game = _smith(content, world)
    msgs = server.MAIN_ACTIONS["smith_forge"](game, {"kind": "劍", "main": "gang_1", "aux": "kuai_1"})
    assert msgs and game.smith_result["id"] == game.state.player.weapon.id


def test_the_routes_answer_the_forge_page(monkeypatch):
    """/api/smith_line 與 /api/do/smith_forge 走真的伺服器（週末設定的正式內容）：店開著時 main 有 shop，問一爐、開一爐、拿到出爐卡。"""
    from fastapi.testclient import TestClient

    import server
    from tianxia import accounts
    from tianxia.characters import open_characters

    content = real_content("week7")
    content.config.auto_open_first_season = True
    content.config.jianfa.enabled = False  # 減法季的開局第一分鐘擋在鐵匠鋪前面；這裡測的是打造的路由
    monkeypatch.setattr(server, "CONTENT", content)
    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})
    monkeypatch.setattr(server, "_breaker_until", None, raising=False)
    stores = (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES)
    for store in stores:
        store.clear()
    try:
        client = TestClient(server.app)
        client.post("/api/register", json={"login": "smith_01", "password": "secret-pw", "again": "secret-pw"})
        client.post("/api/character", json={"name": "鐵匠客"})
        client.post("/api/do/skip_tutorial", json={})
        game = server.game_for("鐵匠客")
        p = game.state.player
        p.location, p.stats["silver"], p.materials = "yingchuan", 300, {"gang_1": 3, "kuai_1": 2}
        equipment.open_smith(p, content)
        open_characters().save(game.state)
        shop = client.get("/api/main").json()["shop"]
        assert shop["shop"] == "smith"
        line = client.post("/api/smith_line", json={"kind": "劍", "main": "gang_1", "aux": "kuai_1"}).json()
        assert line["ready"] and line["problem"] is None
        out = client.post("/api/do/smith_forge", json={"kind": "劍", "main": "gang_1", "aux": "kuai_1"}).json()
        assert out["forged"]["slot"] == "weapon" and out["main"]["shop"]["silver"] == shop["silver"] - 20  # 一爐 20 兩
        refused = client.post("/api/do/smith_forge", json={"kind": "劍", "main": "gang_1", "aux": "nope"}).json()
        assert refused["forged"] is None and "沒有這種素材" in refused["message"]
    finally:
        for store in stores:
            store.clear()


# ── 終審 Critical 1：店面只在鐵匠鋪那一串真的是眼前的選單時才有（決戰、休季、奪璽單挑排在前面時不蓋住它們）──


def test_a_battle_takes_the_screen_back_from_the_shop(on):
    """宛城之戰：官軍的甲在宛城加入集結、走進鐵匠鋪，開打之後選單是三招：店面不能再蓋住決戰（出店會被拒絕，人就困在店裡），
    也不能直接開爐。集結時選單前面多了決戰的鈕：也照舊畫那一串按鈕，免得加入、趕到的鈕被蓋住。"""
    import server
    from tianxia.engine import Game

    on.config.weapons.enabled = on.config.armor.enabled = True
    game = Game.new(on, "甲", rng=random.Random(0))
    game.client = None
    game.set_hints_off(True)
    p = game.state.player
    p.faction, p.location, p.stats["silver"] = "guan", "wan_city", 300
    p.materials = {"gang_1": 4, "kuai_1": 2}
    game.world.start_battle(on.battles["wancheng_jia"], now=game.now)
    game.choose("battle:join:guan")
    game.choose("act:smith")
    assert p.picking_smith and any(o.id.startswith("battle:") for o in game.options(odds=False))
    assert game.shop_view() is None and "shop" not in server.main_view(game)  # 集結：決戰的鈕還在選單上
    game.world.mutate_battle(lambda x: setattr(x, "muster_deadline_real", -1.0))
    ids = [o.id for o in game.options(odds=False)]
    assert ids and all(i.startswith("battle:") for i in ids)  # 開打了：選單只剩三招
    assert game.shop_view() is None and "shop" not in server.main_view(game)
    before = (p.stats["silver"], dict(p.materials))
    assert game.smith_forge("劍", "gang_1", "kuai_1") == [equipment.NOT_NOW]
    assert (p.stats["silver"], dict(p.materials)) == before and game.smith_result is None


def test_no_shop_and_no_forging_in_the_rest_season(content, world):
    """休季：選單只有「休季中」，什麼都不能做。人在鐵匠鋪裡收季（存檔裡 picking_smith 還是真的）也不給店面、不能直接開爐。"""
    import server

    content.config.admins = ["試鋪"]
    game = _smith(content, world)
    game.admin_end_season(now=100.0)
    assert [o.id for o in game.options(odds=False)] == ["season:resting"] and game.state.player.picking_smith
    assert game.shop_view() is None and "shop" not in server.main_view(game)
    p = game.state.player
    before = (p.stats["silver"], dict(p.materials))
    assert game.smith_forge("劍", "gang_1", "kuai_1") == [equipment.NOT_NOW]
    assert (p.stats["silver"], dict(p.materials)) == before


# ── 設計第七節補測（PM 2026-10-13）：直接開爐與一步一步打出來一樣（隱藏配方、首位發現、神器原品、仿品、首創名望回饋）──

SECRET_STEPS = [  # (種類, 主料, 輔料, 有沒有人先打過)：先打過的那一位是「先手」
    pytest.param("劍", "gang_1", "kuai_1", False, id="weapon-named-first-find"),
    pytest.param("劍", "gang_1", "kuai_1", True, id="weapon-named-follower-echo"),
    pytest.param(smithing.ARMOR_KIND, "gang_1", "kuai_1", False, id="armor-named-first-find"),
    pytest.param(smithing.ARMOR_KIND, "gang_1", "kuai_1", True, id="armor-named-follower-echo"),
    pytest.param("劍", "gang_3", "gang_3", False, id="weapon-divine-original"),
    pytest.param("劍", "gang_3", "gang_3", True, id="weapon-divine-copy-echo"),
    pytest.param(smithing.ARMOR_KIND, "gang_3", "gang_3", False, id="armor-divine-original"),
    pytest.param(smithing.ARMOR_KIND, "gang_3", "gang_3", True, id="armor-divine-copy-echo"),
]


def _secret_content(content):
    from test_forge_divine import STAR, WARD
    from test_forge_secrets import BLADE, JACKET

    content.forge_secrets = {r.id: r.model_copy(deep=True) for r in (BLADE, JACKET, STAR, WARD)}
    content.config.forge_secrets.per_season = {"weapon:1": 1, "armor:1": 1, "weapon:divine": 1, "armor:divine": 1}
    return content


def _shop_in(content, world, name):
    game = _smith(content, world, silver=1000, name=name)
    game.state.player.materials.update({"gang_3": 4})
    return game


def _one_path(content, world, kind, main, aux, prior, direct, seed=7):
    """一個世界裡：先手（要的話）照同一個種子先打一爐，再由「同名」用一步一步的單子（direct 為假）或直接開爐打同一爐。"""
    if prior:
        first = _shop_in(content, world, "先手")
        rng = smithing.own_rng(first.state, smithing.recipe_key(kind, main, aux)) if smithing.is_armor(kind) else random.Random(0)
        assert smithing.forge(first.state, content, world, kind, main, aux, rng=rng)[0] is not None
    game = _shop_in(content, world, "同名")
    game.rng = random.Random(seed)
    if direct:
        game.smith_forge(kind, main, aux)
    else:
        if smithing.is_armor(kind):
            game.choose("smith:page:armor")
        for option in smithing.wizard_steps(kind, main, aux):
            game.choose(option)
    return game


def _outcome(game, world, kind, main, aux):
    """拿來比的東西：打出來的那一件、身上的錢與料與熟手次數、鑄譜、全服那一列、首創名望回饋、傳聞、最上面那一則紀錄。"""
    from tianxia import forge_secrets

    p = game.state.player
    slot = smithing.slot_of(kind)
    item = next(i for i in [equipment.worn(p, slot), *equipment.in_slot(p, slot)] if i is not None and i.recipe == smithing.recipe_key(kind, main, aux))
    secret = forge_secrets.match(game.content, world.read().tianji, slot, kind, main, aux)
    find = world.lookup_gear_find(forge_secrets.key(secret))
    echo = game.state.world.echoes.get(forge_secrets.key(secret))
    top = game.state.journal[0]
    return {
        "item": item.model_dump(exclude={"id"}),
        "purse": (p.stats["silver"], dict(p.materials), dict(p.forge_counts)),
        "book": (list(p.forge_manual.solved), dict(p.forge_manual.made)),
        "find": None if find is None else (find.creator, find.owner, find.divine, find.copies, find.name),
        "echo": None if echo is None else (echo.creator, list(echo.followers), echo.name, echo.made),
        "rumors": [r.text for r in game.state.world.rumors],
        "journal": (top.title, top.lines, top.changes),
    }


@pytest.mark.parametrize(("kind", "main", "aux", "prior"), SECRET_STEPS)
def test_direct_forging_matches_the_step_by_step_forge_for_hidden_and_divine_recipes(content, world, tmp_path, monkeypatch, kind, main, aux, prior):
    from tianxia import fusion
    from tianxia.sqlite_world import open_world

    monkeypatch.setattr(fusion, "season_one", lambda *a, **k: True)  # 首創名望回饋只在第一季規則開著時有
    _secret_content(content)
    other = open_world(tmp_path / "direct.db")  # 兩條路各在自己的世界打：先手、首位發現、仿品數都一樣地從零開始
    step = _one_path(content, world, kind, main, aux, prior, direct=False)
    direct = _one_path(content, other, kind, main, aux, prior, direct=True)
    a, b = _outcome(step, world, kind, main, aux), _outcome(direct, other, kind, main, aux)
    assert a == b
    item = a["item"]
    assert item["secret"] is not None  # 真的打中了隱藏配方（名器或神器）
    if main == "gang_3":
        assert item["original"] is not prior and (item["copy_of"] is not None) is prior
    if prior:
        assert a["echo"][0] == "先手" and a["echo"][1] == ["同名"]  # 首創名望回饋記給先手
    else:
        assert a["find"][0] == "同名" and direct.smith_result["first"]  # 首位發現


# ── 設計第七節補測：smith_line（/api/smith_line 回的就是它）與 smith_view 不露別人打中的隱藏配方 ──


@pytest.mark.parametrize(("kind", "main", "aux", "name"), [
    pytest.param("劍", "gang_1", "kuai_1", "穿霞劍", id="weapon-named"),
    pytest.param(smithing.ARMOR_KIND, "gang_1", "kuai_1", "赤霞鎧", id="armor-named"),
    pytest.param("劍", "gang_3", "gang_3", "墜星劍", id="weapon-divine"),
    pytest.param(smithing.ARMOR_KIND, "gang_3", "gang_3", "鎮星甲", id="armor-divine"),
])
def test_another_players_find_never_shows_on_your_forge_page(content, world, kind, main, aux, name):
    """先手打中了（首位發現、神器原品），他的鑄譜記著；同名自己沒打中過：這一爐的說法不寫「照鑄譜上的【…】打」、不寫譜名、
    不說必出神器（照樣寫三個機率），店面整份也找不到那個名字。自己打中過一次之後才寫（對照組）。"""
    import json

    import server

    _secret_content(content)
    first = _shop_in(content, world, "先手")
    rng = smithing.own_rng(first.state, smithing.recipe_key(kind, main, aux)) if smithing.is_armor(kind) else random.Random(0)
    assert smithing.forge(first.state, content, world, kind, main, aux, rng=rng)[0].secret is not None
    assert first.smith_line(kind, main, aux)["head"]  # 先手自己看得到
    game = _shop_in(content, world, "同名")
    if smithing.is_armor(kind):
        game.choose("smith:page:armor")
    line = server.look(game, lambda g: g.smith_line(kind, main, aux))  # /api/smith_line 的那一份
    assert line["ready"] and line["head"] == "" and line["divine"] is False and line["odds"]
    shop = server.main_view(game)["shop"]
    for text in (json.dumps(line, ensure_ascii=False), json.dumps(shop, ensure_ascii=False)):
        assert name not in text and "照鑄譜" not in text and "必出神器" not in text
    assert shop["pending"] == {}
    game.smith_forge(kind, main, aux)  # 對照組：自己打中過一次，鑄譜記下了才寫
    assert game.smith_line(kind, main, aux)["head"].startswith("照鑄譜上的")
