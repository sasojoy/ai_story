"""回饋單甲批（PM 2026-10-14；企劃者「先不用等～都先做～之後再回頭潤字」）：裝備、店面、紀錄、版面的幾張小單。新寫的字都待 joy 潤。"""
from __future__ import annotations

import random

import pytest
from test_weapons import _blade, _game, _new_state, _on, _town

from tianxia import team, weapons

ATTRS = "剛柔快慢陰陽虛實"


# ── FB-127：兵器的字 ──


def test_fb127_only_a_blade_is_said_to_have_a_blade_edge(content, world):
    """拳套、弩、棍沒有刀口：鈍了的提醒照種類換字；只有刀寫「刀口」。"""
    _on(content)
    state = _new_state(content, world, "鈍拳")
    lines = {}
    for kind in ("劍", "刀", "槍", "棍", "弓弩", "拳腳"):
        state.player.weapon, state.player.edge_warned = _blade(kind=kind, edge=30), False
        [lines[kind]] = weapons.wear(state, content, "落敗")
    assert all(("刀口" in line) == (kind == "刀") for kind, line in lines.items()), lines
    assert "拳套" in lines["拳腳"] and "弩" in lines["弓弩"]


def test_fb127_a_full_edge_does_not_say_blade_edge_for_a_fist(content, world):
    game = _town(content, world)
    game.state.player.weapon = _blade(kind="拳腳", edge=100)
    problem = weapons.repair_problem(game.state, content)
    assert problem is not None and "刀口" not in problem


def test_fb127_the_mismatch_names_the_piece_not_the_kind(content, world):
    """「這把拳腳用不上你的劍法」：拳腳是種類名，東西是一副拳套。"""
    _on(content)
    game = _game(content, world)
    art = team.resolve_art("sword", content, world)
    game.state.player.weapon = _blade(kind="拳腳")
    line = weapons.card_line(game.state, content, world, art)
    assert "這副拳套用不上你的劍法" in line and "這把拳腳" not in line
    game.state.player.weapon = _blade(kind="弓弩")
    assert "這把弩用不上你的劍法" in weapons.card_line(game.state, content, world, art)


def test_fb127_a_clashing_blade_says_so_instead_of_a_bare_plus_zero(content, world):
    """配得上、屬性卻跟武學相剋：一階下品的加成正好抵掉，寫「威力 +0%」像沒配上。補一句相剋（角色卡與修練頁那一列）。"""
    _on(content)
    game = _game(content, world)
    art = team.player_art(game.state, content, world, game.state.player.member.wugong_id)
    clash = next(a for a in ATTRS if weapons.counters(a, art.attribute) or weapons.counters(art.attribute, a))
    game.state.player.weapon = _blade(kind=weapons.art_weapon(art.id, content, world), attribute=clash)
    line = weapons.card_line(game.state, content, world, art)
    assert "威力 +0%" in line and weapons.CLASH_NOTE in line
    row = weapons.rows(game.state, content, world, art)["worn"]
    assert row["bonus"] == "+0%" + weapons.CLASH_NOTE
    game.state.player.weapon = _blade(kind=weapons.art_weapon(art.id, content, world), attribute=art.attribute)
    assert weapons.CLASH_NOTE not in weapons.card_line(game.state, content, world, art)


def test_fb127_the_practice_rows_carry_the_piece_noun(content, world):
    """修練頁、人物面板、店面裝備庫那幾處寫的種類：伺服器給 noun（拳套、弩），網頁照它寫，不寫種類名（拳腳、弓弩）。"""
    _on(content)
    game = _game(content, world)
    art = team.player_art(game.state, content, world, game.state.player.member.wugong_id)
    game.state.player.weapon = _blade(kind="拳腳")
    assert weapons.rows(game.state, content, world, art)["worn"]["noun"] == "拳套"


def test_fb127_the_practice_page_writes_the_noun(hints_content, world):
    import webharness
    if webharness.NODE is None:
        pytest.skip("沒有 node，前端畫面測試略過")
    from test_prologue_web import run
    from test_weapons_web import _gear, _row, _weapons_block

    import server
    from tianxia.engine import Game

    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    m, x = server.main_view(game), server.menxia_view(game)
    x["gear"] = _gear(weapon={"worn": _row(kind="拳腳", noun="拳套", grade="一階下品", confirm=""),
                              "rack": [_row(id="兵:2", kind="弓弩", noun="弩", grade="一階下品", confirm="")]})
    block = _weapons_block(run(m, "return H.pagePractice();", menxia=x))
    assert "拳套・屬柔" in block and "弩・屬柔" in block and "拳腳" not in block and "弓弩" not in block


# ── FB-133、FB-160：種類字與量詞一致（拳套／拳腳、弩／弓弩；拳套論「副」） ──


def _piece(kind="拳腳", **over):
    from tianxia.state import Weapon
    return Weapon(**{"id": "兵:9", "name": "綿羽護手", "kind": kind, "attribute": "剛", "tier": 1, "quality": "中品", **over})


def test_fb133_the_forge_result_writes_the_noun_and_its_measure_word():
    """打出來的結果句寫「拳腳」「弓弩」，挑種類與開爐鈕寫「拳套」「弩」：結果句也寫拳套、弩；拳套論副。"""
    from tianxia import smithing

    fist = smithing.forged_head(_piece("拳腳"), "兩份精鐵砂")
    assert "一副" in fist and "拳套" in fist and "拳腳" not in fist and "一把" not in fist
    bow = smithing.forged_head(_piece("弓弩", name="驚弦弩"), "兩份精鐵砂")
    assert "一把" in bow and "弩・" in bow and "弓弩" not in bow


def test_fb133_buying_and_picking_up_a_fist_says_a_pair(content, world):
    game = _town(content, world)
    game.choose("act:smith")
    assert "買下一副【厚背拳套】" in game.choose("smith:buy:拳腳")[0]
    assert weapons.DROP_LINE.format(unit=weapons.unit("拳腳"), name="厚背拳套") == "撿到一副【厚背拳套】"


def test_fb133_the_old_smithy_menu_writes_nouns(content, world):
    """店面開關關著的舊選單：買鈕的括號寫「弩」「拳套」，不寫「弓弩」「拳腳」。"""
    content.config.shop_screens = False
    game = _town(content, world)
    game.choose("act:smith")
    labels = {o.id: o.label for o in game.options(odds=False)}
    assert "（弩・一階" in labels["smith:buy:弓弩"] and "（拳套・一階" in labels["smith:buy:拳腳"]
    assert not any("弓弩" in label or "拳腳" in label for label in labels.values())


def test_fb133_the_dismantle_question_says_the_tempering_goes_too(content):
    """鈕上寫「（一階中品・淬煉 5）」，確認框只寫「（一階中品）」：淬過的次數會一起沒了，確認框該提醒。"""
    from tianxia import equipment

    ask = equipment.dismantle_confirm(content, _piece(tempers=5))
    assert "淬煉 5 次" in ask
    assert "淬煉" not in equipment.dismantle_confirm(content, _piece())


def test_fb133_stepping_back_says_so_before_asking_again(content, world):
    """「上一步」只回下一步的問句，讀起來像同一個問題問了兩次：先回一句退回了。這一句也算單子自己的回話（開爐成了收掉）。"""
    from tianxia import smithing
    from tianxia.state import SmithDraft

    _on(content)
    state = _new_state(content, world, "退步")
    state.player.smith_draft = SmithDraft(kind="劍", main="gang_1")
    assert smithing.step(state, content, "forge-undo", "") == [smithing.UNDONE, smithing.ASK_MAIN]
    assert smithing.is_step_line(smithing.UNDONE)


def test_fb160_a_fist_bounty_asks_for_a_pair():
    from tianxia import bounties
    from tianxia.state import Bounty

    fist = Bounty(id="b1", kind="arms", faction="guan", week=1, silver=0, deeds=2, attribute="剛", weapon_kind="拳腳", expires=0.0)
    assert "交出一副屬剛的拳套" in bounties.how(None, fist) and bounties.unit_of(fist) == "副"
    bow = fist.model_copy(update={"weapon_kind": "弓弩"})
    assert "交出一把屬剛的弩" in bounties.how(None, bow) and bounties.unit_of(bow) == "把"
    art = fist.model_copy(update={"kind": "art", "weapon_kind": None})
    assert bounties.unit_of(art) == "門"


# ── FB-146：防具神器的量詞 ──

from test_forge_divine import _forger, divine_content  # noqa: E402,F401（divine_content 是 fixture）


def test_fb146_an_armor_divine_piece_is_one_jian_everywhere(divine_content, world):
    """打出凝波甲：結果句寫「一件」，後面的「這是一把神器」、傳聞「打出了一把神器」、江湖史「打出一把神器（防具）」都是「把」。
    照欄位換：防具一件，兵器照種類（劍一把）。"""
    from tianxia import armor, equipment, smithing

    game = _forger(divine_content, world, name="甲")
    key = "鎧|gang_3+gang_3"
    coat, msgs = smithing.forge(game.state, divine_content, world, smithing.ARMOR_KIND, "gang_3", "gang_3",
                                rng=smithing.own_rng(game.state, key))
    text = "\n".join(msgs)
    assert "一件神器" in text and "這一件原品" in text and "一把" not in text
    rumors = [r.text for r in game.state.world.rumors]
    assert any("一件神器" in r for r in rumors) and not any("一把神器" in r for r in rumors)
    spare, _ = smithing.forge(game.state, divine_content, world, smithing.ARMOR_KIND, "gang_3", "gang_3", rng=smithing.own_rng(game.state, key))
    armor.wield(game.state, divine_content, spare.id)  # 原品進裝備庫
    [kept] = armor.dismantle(game.state, divine_content, coat.id)
    assert "這一件" in kept and "這一把" not in kept
    ok, named = smithing.name_divine(game.state, divine_content, world, coat.id, "鏡湖")
    assert ok and "這件神器" in named[0]
    assert any("打出一件神器（防具）" in r.text for r in game.state.world.chronicle)
    blade = _forger(divine_content, world, name="乙")
    _, msgs = smithing.forge(blade.state, divine_content, world, "劍", "gang_3", "gang_3")
    assert "這是一把神器" in "\n".join(msgs)


# ── FB-141、FB-148：「剛剛」收成一行時看得出名器、神器與品質 ──


def test_fb148_the_first_words_of_the_forge_result_say_what_kind_of_piece_it_is():
    """375 寬收成一行只露開頭十五、六個字：名器「打出一把【柳影劍】（劍・屬虛・」跟一般組合長得一樣，品質也切掉了。
    名器寫在名字前面，括號先寫階品再寫種類屬性；神器原品與仿品的名字（無名神器、仿・…）已經看得出來，標記照舊接在階品後面。"""
    from tianxia import smithing
    from tianxia.state import Equipment

    cases = [
        (_piece("劍", name="柳影劍", secret="t_blade"), "打出一把名器【柳影劍】（一階中品・劍・屬剛）"),
        (_piece("拳腳"), "打出一副【綿羽護手】（一階中品・拳套・屬剛）"),
        (_piece("劍", name="無名神器", tier=3, quality="上品", original=True, secret="t_star"), "打出一把【無名神器】（三階上品・神器・劍・屬剛）"),
        (_piece("劍", name="仿・無名神器", tier=3, quality="上品", copy_of="鑄|t_star", secret="t_star"),
         "打出一把【仿・無名神器】（三階上品・仿品・劍・屬剛）"),
        (Equipment(id="甲:1", slot="armor", name="垂柳衫", attribute="柔", tier=1, quality="上品", secret="t_jacket"),
         "打出一件名器【垂柳衫】（一階上品・防具・屬柔）"),
    ]
    for item, start in cases:
        head = smithing.forged_head(item, "柳絲綿與驚羽")
        assert head.startswith(start + "：鐵匠把柳絲綿與驚羽下爐。"), head
        assert item.quality in head[:18]  # 收成一行露得出品質


# ── FB-142：鐵匠順口那一句照有沒有收錢換句 ──

from test_forge_secrets import _smith, forge_content  # noqa: E402,F401（forge_content 是 fixture）


def test_fb142_a_free_temper_does_not_say_the_smith_took_money(forge_content, world):
    """一階淬煉只收一個素材、不收錢，鐵匠順口卻寫「一邊收錢一邊嘀咕」：沒收銀兩的那一下換一句。"""
    from tianxia import forge_secrets
    from tianxia.state import Weapon

    rule = forge_content.config.forge_secrets
    rule.smith_chance = 1.0
    game = _smith(forge_content, world)
    recipe = forge_secrets.smith_clue(forge_content, world.read().tianji, "town")
    clue = recipe.clues[forge_secrets.SMITH]
    game.state.player.weapon = Weapon(id="兵:9", name="試刃", kind="劍", attribute="剛", tier=1, quality="下品")
    game.state.player.materials["gang_1"] = 3
    silver = game.state.player.stats["silver"]
    game.choose("act:smith")
    msgs = game.choose("smith:temper")
    assert game.state.player.stats["silver"] == silver  # 一階淬煉不收錢
    assert rule.smith_frame_free.format(clue=clue) in msgs and rule.smith_frame.format(clue=clue) not in msgs
    assert "收錢" not in rule.smith_frame_free


# ── FB-139、FB-149：名將贈禮與本命兵器另起一則，人不在名將身邊寫「託人送來」 ──


def _gift_entries(game):
    from tianxia import treasures
    return [e for e in game.state.journal if e.title == treasures.GIFT_TITLE]


def test_fb139_a_gift_from_afar_is_its_own_entry_and_sent_by_a_messenger(content, world):
    """在燕山腳了結事件時冒出「劉備把【舊草鞋】交到你手上」：名將不在場，也跟那件事無關。另起一則「名將贈禮」，寫成託人送來。"""
    from conftest import idle_step
    from test_treasures import _book, _game as _treasure_game

    from tianxia import treasures

    _book(content)
    game = _treasure_game(content, world, "遠客", at="lake")
    assert "mate" not in game._people_here()
    game.state.player.affinities["mate"] = 60
    idle_step(game)
    sent = treasures.GIFT_SENT_LINE.format(general="韓鐵", gift="舊草鞋")
    newest, action = game.state.journal[0], game.state.journal[1]
    assert newest.title == treasures.GIFT_TITLE and sent in [newest.tag, *newest.lines]  # 最新一則：「剛剛」看得到
    assert not any("舊草鞋" in line for line in [action.tag, *action.lines])  # 當下那個動作的紀錄不再接這一句
    assert "交到你手上" not in sent


def test_fb139_a_gift_in_person_still_says_handed_over(content, world):
    from conftest import idle_step
    from test_treasures import _book, _game as _treasure_game

    from tianxia import treasures

    _book(content)
    game = _treasure_game(content, world, "近客", at="town")
    assert "mate" in game._people_here()
    game.state.player.affinities["mate"] = 60
    idle_step(game)
    [entry] = _gift_entries(game)
    assert treasures.GIFT_LINE.format(general="韓鐵", gift="舊草鞋") in [entry.tag, *entry.lines]


def test_fb149_a_signature_arm_from_afar_joins_the_gift_entry(content, world):
    from conftest import idle_step
    from test_signature_arms import _arms, _game as _arm_game

    from tianxia import signature_arms

    _arms(content)
    game = _arm_game(content, world)
    game.state.player.location = "lake"
    game.state.player.affinities["mate"] = 80
    idle_step(game)
    [entry] = _gift_entries(game)
    assert signature_arms.GIFT_SENT_LINE.format(general="韓鐵", arm="鐵脊長刀") in [entry.tag, *entry.lines]
    assert not any("鐵脊長刀" in line for e in game.state.journal[1:] for line in [e.tag, *e.lines])
