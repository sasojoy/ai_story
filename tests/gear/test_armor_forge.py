"""防具打造（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 4.7、4.1；打造隱藏配方設計第九節：照兵器那一套，沒有種類，
名字照對照表、不叫模型；計畫 docs/superpowers/plans/2026-10-12-打造-1-隱藏配方與防具.md Task 2～5）。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import armor, equipment, naming, rules, smithing, team, weapons
from tianxia.state import Equipment, SmithDraft, Weapon

KEY_YANG = "鎧|gang_1+kuai_1"  # 精鐵砂（剛）＋驚羽（快）＝陽 → 接「鎧」
GO_YANG = "smith:forge-go:防具:gang_1:kuai_1"


def _on(content, weapons_on=False):
    """打開防具（測試內容兩欄都關著）；weapons_on 連武器也開。"""
    content.config.armor.enabled = True
    content.config.weapons.enabled = weapons_on
    return content


def _jacket(attribute="虛", tier=1, quality="下品", edge=100, aid="甲:1", name="試甲", tempers=0, recipe=None):
    return Equipment(id=aid, slot="armor", name=name, attribute=attribute, tier=tier, quality=quality, edge=edge,
                     tempers=tempers, recipe=recipe)


def _game(content, world, name="試甲", inner="calm"):
    """身上一門內功（預設靜心訣，屬虛）。"""
    from tianxia.engine import Game
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    rules.learn_skill(game.state, content, inner)
    game.state.player.member.neigong_id = inner
    return game


def _smithy(content, world, silver=200, weapons_on=False, name="試甲", inner="calm"):
    """站在測試內容的城鎮（town），悟性 5；背包：精鐵砂（剛一階）×3、玄鋼骨（剛二階）×2、驚羽（快一階）×2。"""
    _on(content, weapons_on)
    game = _game(content, world, name=name, inner=inner)
    p = game.state.player
    p.location, p.stamina, p.stats["silver"], p.stats["wis"] = "town", 100.0, silver, 5
    p.materials = {"gang_1": 3, "gang_2": 2, "kuai_1": 2}
    game.sync(0.0)
    return game


def _ids(game):
    return {o.id: o for o in game.options(odds=False)}


def _inner(game, content, world):
    return team.player_art(game.state, content, world, game.state.player.member.neigong_id)


# ── Task 2：防具的配方鍵、名字對照表與打造規則 ──

def test_armor_recipe_keys_have_their_own_prefix():
    assert armor.recipe_key("gang_1", "kuai_1") == KEY_YANG
    assert armor.recipe_key("kuai_1", "gang_1") != KEY_YANG  # 主輔不交換
    assert armor.recipe_parts(KEY_YANG) == ("gang_1", "kuai_1")
    assert armor.recipe_parts("兵|劍|gang_1+kuai_1") is None and armor.recipe_parts(None) is None
    assert weapons.recipe_parts(KEY_YANG) is None  # 前綴就是欄位：兵器那一側讀不到防具的鍵


def test_recipe_text_writes_main_then_aux(content):
    assert armor.recipe_text(content, KEY_YANG) == "精鐵砂＋驚羽"
    assert armor.recipe_text(content, "兵|劍|gang_1+kuai_1") is None and armor.recipe_text(content, None) is None


def test_the_armor_word_follows_the_attribute_and_matches_the_shop():
    assert armor.noun_for("剛") == armor.noun_for("柔") == "甲" and armor.noun_for("快") == armor.noun_for("虛") == "衫"
    assert armor.noun_for("慢") == armor.noun_for("陰") == "袍" and armor.noun_for("陽") == armor.noun_for("實") == "鎧"
    for attribute, shop in armor.SHOP_NAMES.items():
        assert shop.endswith(armor.noun_for(attribute))  # 架上四件就是這個對法（鐵葉甲、軟皮甲、輕綃衫、厚氈袍）
    assert set(armor.FORGE_NOUNS.values()) == set(armor.FORGE_WORDS)  # 四個字都用得到


def test_word_problem_wants_an_armor_word_and_no_weapon_word():
    assert armor.word_problem("玄鱗鎧") is None and armor.word_problem("石鱗甲") is None
    assert armor.word_problem("玄甲雲紋") is None  # 帶防具字就行：隱藏配方的名字由內容寫，不必以它結尾
    assert armor.word_problem("玄鱗") == armor.WORD_MISSING
    assert armor.word_problem("刀鱗甲") == armor.WORD_CLASH and armor.word_problem("護手衫") == armor.WORD_CLASH  # 像兵器
    assert armor.word_problem("軟皮甲") == armor.SHOP_CLASH  # 鐵匠鋪架上的防具名


def test_armor_table_names_follow_main_and_aux_and_never_repeat(content):
    """PM 2026-10-12 決定第 1 條（「要 PM 定的」第 1 條）：字首照主料、中間字（craft_names.armor）照輔料的位置，最後接照屬性的防具字。"""
    names, order = content.craft_names, list(content.materials)
    assert armor.table_name(content, "gang_1", "kuai_1", "陽") == (
        names.prefixes[order.index("gang_1")] + names.armor[order.index("kuai_1")] + "鎧")
    heads = {armor.table_name(content, m, a, "剛")[:2] for m in order for a in order}
    assert len(heads) == len(order) ** 2  # 前兩個字只看組合，全部不同：不管接哪個防具字都不重名
    for m in order:
        for a in order:
            name = armor.table_name(content, m, a, "實")
            assert naming.name_problem(name, content) is None and armor.word_problem(name) is None


def test_validate_checks_the_armor_table(content):
    from tianxia.content import ContentError, validate
    content.craft_names.armor = ["刀", "霜", "雲", "紋"]  # 「某刀甲」看起來像兵器：載入當下就要報錯
    with pytest.raises(ContentError, match="craft_names.armor 組出的防具名"):
        validate(content)
    content.craft_names.armor = list("鱗鱗雲紋")
    with pytest.raises(ContentError, match="craft_names.armor 至少要 4 個不重複的字"):
        validate(content)
    content.craft_names.armor = []
    with pytest.raises(ContentError, match="craft_names.armor 不能是空的"):
        validate(content)
    assert real_content().craft_names.armor  # 正式內容載入時已經驗過每一個組合


def test_armor_forging_numbers_follow_the_weapons_and_live_in_the_armor_config(content):
    rule = content.config.armor
    assert rule.forge_silver == {"1": 20, "2": 60, "3": 150, "4": 300} and rule.temper_max == 5  # 四階 300（正式季整合 5.1）
    assert rule.temper_silver == {"1": 0, "2": 30, "3": 80, "4": 150} and rule.temper_step == 0.01
    assert rule.quality.odds == {"下品": 50, "中品": 30, "上品": 20} and (rule.quality.terrain, rule.quality.calm) == (0, 0)
    q = real_content().config.armor.quality
    assert (q.terrain, q.battlefield, q.calm) == (10, 10, 8) and q.setting_good


def test_new_armor_can_carry_its_recipe(content, world):
    game = _game(_on(content), world)
    a = armor.new_armor(game.state, name="玄鱗鎧", attribute="陽", tier=1, quality="中品", recipe=KEY_YANG)
    assert a.recipe == KEY_YANG and a.id.startswith("甲:") and a.slot == "armor"
    assert armor.new_armor(game.state, name="鐵葉甲", attribute="剛", tier=1, quality="下品").recipe is None


def test_the_armor_kind_maps_to_the_armor_slot_key_and_rules(content):
    assert smithing.is_armor(smithing.ARMOR_KIND) and not smithing.is_armor("劍") and not smithing.is_armor(None)
    assert smithing.slot_of(smithing.ARMOR_KIND) == "armor" and smithing.slot_of("劍") == smithing.slot_of(None) == "weapon"
    assert smithing.rules_of(content, "armor") is content.config.armor and smithing.rules_of(content, "weapon") is content.config.weapons
    assert smithing.recipe_key(smithing.ARMOR_KIND, "gang_1", "kuai_1") == KEY_YANG
    assert smithing.recipe_key("劍", "gang_1", "kuai_1") == "兵|劍|gang_1+kuai_1"


def test_armor_forge_problem_reasons(content, world):
    game = _smithy(content, world)  # 只開防具
    s, p = game.state, game.state.player
    A = smithing.ARMOR_KIND
    assert smithing.forge_problem(s, content, A, "gang_1", "kuai_1") is None
    p.materials = {"gang_1": 1}
    assert smithing.forge_problem(s, content, A, "gang_1", "gang_1") == "精鐵砂不夠（要 2 個）"
    p.materials, p.stats["silver"] = {"gang_1": 2}, 5
    assert smithing.forge_problem(s, content, A, "gang_1", "gang_1") == "還差 15 兩"
    p.stats["silver"] = 200
    p.armor = _jacket()
    p.rack = [_jacket(aid=f"甲:{i + 2}") for i in range(content.config.weapons.rack_cap)]
    assert smithing.forge_problem(s, content, A, "gang_1", "gang_1") == equipment.RACK_FULL
    p.rack = []
    assert smithing.forge_problem(s, content, "劍", "gang_1", "gang_1") == weapons.NOT_HERE  # 兵器關著：只能打防具
    content.config.armor.enabled = False
    assert smithing.forge_problem(s, content, A, "gang_1", "gang_1") == weapons.NOT_HERE


def test_armor_attribute_tier_and_price(content, world):
    A = smithing.ARMOR_KIND
    assert smithing.attribute_of(world, content, A, "gang_1", "kuai_1") == "陽"
    assert smithing.attribute_of(world, content, A, "kuai_1", "kuai_1") == "快"
    content.config.armor.forge_silver = {"1": 7, "2": 8, "3": 9}
    assert [smithing.price(content, t, "armor") for t in (1, 2, 3)] == [7, 8, 9]
    assert [smithing.price(content, t) for t in (1, 2, 3)] == [20, 60, 150]  # 兵器照舊


def test_the_armor_attribute_seed_is_the_armor_key():
    """剛＋柔不在四對裡：照「天機|配方鍵」挑，防具的鍵是「鎧|主料+輔料」（正式內容的柳絲綿 rou_1）。"""
    from tianxia.insights import merged_attribute
    rc = real_content()
    for tianji in range(4):
        assert smithing.attribute_with(rc, tianji, smithing.ARMOR_KIND, "gang_1", "rou_1") == merged_attribute(
            rc.materials["gang_1"], rc.materials["rou_1"], f"{tianji}|鎧|gang_1+rou_1")


def test_armor_odds_use_the_armor_rule_and_the_armor_key(content, world):
    game = _smithy(content, world)
    A = smithing.ARMOR_KIND
    odds = smithing.forge_odds(game.state, content, world, A, "gang_1", "kuai_1")
    assert odds.odds == {"下品": 46.0, "中品": 32.0, "上品": 22.0} and odds.reasons == ("輔料壓得住主料",)
    game.state.player.forge_counts = {KEY_YANG: 3, "兵|劍|gang_1+kuai_1": 5}
    assert smithing.forge_odds(game.state, content, world, A, "gang_1", "kuai_1").odds == {"下品": 40.0, "中品": 35.0, "上品": 25.0}  # 熟手照防具自己的配方鍵（+6）
    content.config.armor.quality.aux_tier = {"0": 0}
    assert smithing.forge_odds(game.state, content, world, A, "gang_1", "kuai_1").odds == {"下品": 44.0, "中品": 33.0, "上品": 23.0}


def test_armor_setting_uses_the_armor_rule(content, world, monkeypatch):
    from tianxia import fusion
    game = _smithy(content, world)
    content.config.armor.quality.terrain = 10
    monkeypatch.setattr(fusion, "terrain_here", lambda state, content, attribute: attribute == "剛")
    assert smithing.setting_points(game.state, content, "剛", "armor") == [("terrain", 10)]
    assert smithing.setting_points(game.state, content, "剛") == []  # 兵器的天時地利照舊（測試內容是 0）
    content.config.armor.quality.setting_good = "爐火正旺。"
    assert smithing.setting_line(content, [("terrain", 10)], "armor") == ["爐火正旺。"]
    assert smithing.setting_line(content, [("terrain", 10)]) == []  # 兵器那一句是空的


# ── Task 3：防具頁的打造單子與開爐 ──

def _armor_smith(content, world, **kw):
    game = _smithy(content, world, **kw)
    game.choose("act:smith")
    return game


def _at_armor_go(content, world, **kw):
    game = _armor_smith(content, world, **kw)
    for oid in (smithing.OPEN, f"{smithing.MAIN}gang_1", f"{smithing.AUX}kuai_1"):
        game.choose(oid)
    return game


def test_own_rng_is_fixed_by_season_name_serial_and_key(content, world):
    game = _smithy(content, world)
    s = game.state
    first = smithing.own_rng(s, KEY_YANG).random()
    assert smithing.own_rng(s, KEY_YANG).random() == first  # 同一個人同一季同一件：一樣
    assert smithing.own_rng(s, "鎧|gang_1+gang_1").random() != first
    s.player.weapon_serial += 1
    assert smithing.own_rng(s, KEY_YANG).random() != first  # 下一件：不一樣


def test_the_armor_page_has_a_forge_door_between_wield_and_dismantle(content, world):
    game = _smithy(content, world)
    p = game.state.player
    p.armor = _jacket()
    p.rack = [_jacket(aid="甲:7", name="鐵葉甲", attribute="剛")]
    game.choose("act:smith")
    opts = _ids(game)
    door = opts[smithing.OPEN]
    assert door.enabled and door.label.startswith("打造防具…") and "挑主料、輔料" in door.label
    ids = list(opts)
    assert ids.index("smith:wield:甲:7") < ids.index(smithing.OPEN) < ids.index("smith:dismantle:甲:7")  # FB-125：換上與拆解不相鄰
    p.materials = {"gang_1": 1}
    door = _ids(game)[smithing.OPEN]
    assert not door.enabled and smithing.NOT_ENOUGH in door.label


def test_the_armor_wizard_skips_the_kind_and_walks_main_aux_go(content, world):
    game = _armor_smith(content, world)
    msgs = game.choose(smithing.OPEN)
    assert smithing.ARMOR_ASK_MAIN in msgs
    ids = list(_ids(game))
    assert not any(i.startswith(smithing.KIND) for i in ids) and ids[0] == f"{smithing.MAIN}gang_2"  # 沒有挑種類；高階的排前面
    assert smithing.UNDO not in ids and ids[-1] == smithing.CANCEL  # 第一步：沒有「上一步」
    game.choose(f"{smithing.MAIN}gang_1")
    aux = _ids(game)[f"{smithing.AUX}kuai_1"]
    assert "→ 屬陽" in aux.label
    game.choose(aux.id)
    go = _ids(game)[GO_YANG]
    assert go.enabled and go.label.startswith("開爐：精鐵砂＋驚羽（防具・屬陽・一階・工錢 20 兩；下品 46%") and go.wait == ""
    game.choose(go.id)
    p = game.state.player
    assert p.armor is not None and p.armor.recipe == KEY_YANG and p.smith_draft is None and p.picking_smith
    assert p.armor.name == armor.table_name(content, "gang_1", "kuai_1", "陽")  # 一般組合照對照表（不叫模型）
    assert smithing.OPEN in _ids(game)  # 打完回到防具頁的選單
    forged = [e for e in game.state.journal if e.title == smithing.FORGE_TITLE]
    assert len(forged) == 1 and any(p.armor.name in line for line in forged[0].lines)  # 一爐一則紀錄
    lines = forged[0].lines  # FB-141：開爐成了那一則只留結果、結果句排第一；挑主料、輔料的回報收掉（結果句寫了放哪兩樣）
    assert lines[0].startswith(f"打出一件【{p.armor.name}】（一階") and "・防具・屬陽）" in lines[0] and lines[0].endswith("：鐵匠把精鐵砂與驚羽下爐。")
    assert "主料：精鐵砂。" not in lines and "輔料：驚羽。" not in lines and smithing.ARMOR_ASK_AUX not in lines


def test_aux_marks_the_attribute_that_matches_the_inner_art(content, world, monkeypatch):
    game = _armor_smith(content, world)  # 靜心訣：屬虛
    monkeypatch.setattr(smithing, "attribute_with", lambda content, tianji, kind, main, aux: "虛" if aux == "kuai_1" else "剛")
    for oid in (smithing.OPEN, f"{smithing.MAIN}gang_1"):
        game.choose(oid)
    opts = _ids(game)
    assert opts[f"{smithing.AUX}kuai_1"].label.endswith(smithing.ARMOR_ATTR_MARK)
    assert smithing.ARMOR_ATTR_MARK not in opts[f"{smithing.AUX}gang_1"].label


def test_undo_on_the_armor_wizard_never_asks_for_a_kind(content, world):
    game = _at_armor_go(content, world)
    game.choose(smithing.UNDO)
    game.choose(smithing.UNDO)
    d = game.state.player.smith_draft
    assert d.kind == smithing.ARMOR_KIND and d.main is None and d.aux is None
    assert not any(i.startswith(smithing.KIND) for i in _ids(game))
    game.choose(smithing.CANCEL)
    assert game.state.player.smith_draft is None and "smith:back" in _ids(game)


def test_a_second_press_of_the_armor_go_does_nothing(content, world):
    game = _at_armor_go(content, world)
    game.choose(GO_YANG)
    p = game.state.player
    before = (p.stats["silver"], dict(p.materials), len(p.rack) + (p.armor is not None))
    assert game.choose(GO_YANG) == ["（此刻無法這麼做。）"]
    assert (p.stats["silver"], p.materials, len(p.rack) + (p.armor is not None)) == before


def test_armor_quality_rolls_on_its_own_dice(content, world, monkeypatch):
    from tianxia import fusion
    game = _at_armor_go(content, world)
    odds = smithing.forge_odds(game.state, content, world, smithing.ARMOR_KIND, "gang_1", "kuai_1")
    expected = fusion.roll_quality(odds, smithing.own_rng(game.state, KEY_YANG))
    seen, real = [], fusion.roll_quality
    monkeypatch.setattr(fusion, "roll_quality", lambda o, rng: seen.append(rng) or real(o, rng))
    game.choose(GO_YANG)
    assert len(seen) == 1 and seen[0] is not game.rng and isinstance(seen[0], random.Random)  # 不碰 Game.rng（設計 9.3）
    assert game.state.player.armor.quality == expected


def test_an_armor_draft_follows_the_armor_switch_not_the_weapon_one(content, world):
    game = _armor_smith(content, world, weapons_on=True)
    p = game.state.player
    game.choose("smith:page:armor")
    game.choose(smithing.OPEN)
    assert p.smith_draft == SmithDraft(kind=smithing.ARMOR_KIND)
    content.config.weapons.enabled = False
    game.sync(1.0)
    assert p.smith_draft == SmithDraft(kind=smithing.ARMOR_KIND)  # 兵器關了不關防具的事
    content.config.weapons.enabled, content.config.armor.enabled = True, False
    game.sync(2.0)
    assert p.smith_draft is None and p.picking_smith  # 防具關了、兵器還開著：鐵匠鋪照開（兵器頁），防具的單子清掉
    content.config.armor.enabled = True
    p.smith_draft = SmithDraft(kind=smithing.ARMOR_KIND, main="gone_material")
    game._drop_stale_references()
    assert p.smith_draft is None  # 內容改版拿掉了單子上的素材：從頭來
    p.smith_draft = SmithDraft(kind=smithing.ARMOR_KIND)
    p.location = "lake"
    game.sync(3.0)
    assert not p.picking_smith and p.smith_draft is None  # 人不在城鎮：鐵匠鋪收起來，單子一起清


def test_a_weapon_draft_still_opens_on_the_weapon_page(content, world):
    game = _armor_smith(content, world, weapons_on=True)  # 兩欄都開著：進門停在兵器頁
    assert _ids(game)[smithing.OPEN].label.startswith("打造兵器…")
    msgs = game.choose(smithing.OPEN)
    assert smithing.ASK_KIND in msgs and game.state.player.smith_draft == SmithDraft()  # 兵器的單子照舊從挑種類起
    assert any(i.startswith(smithing.KIND) for i in _ids(game))


def test_the_shared_forge_door_opens_the_draft_of_the_page_the_server_is_on(content, world):
    """兩頁共用 smith:forge（「範圍與取捨」記的取捨，鎖住現在的行為）：舊分頁停在兵器頁、另一個分頁已經切到防具頁時，舊分頁按
    「打造兵器…」開的是防具的單子；什麼都不收，按「不打了」回到防具頁。"""
    game = _armor_smith(content, world, weapons_on=True)
    p = game.state.player
    before = (p.stats["silver"], dict(p.materials))
    game.choose("smith:page:armor")  # 另一個分頁切到防具頁
    msgs = game.choose(smithing.OPEN)  # 舊分頁照兵器頁按「打造兵器…」：同一個 id
    assert smithing.ARMOR_ASK_MAIN in msgs and p.smith_draft == SmithDraft(kind=smithing.ARMOR_KIND)
    game.choose(smithing.CANCEL)
    assert p.smith_draft is None and p.smith_page == "armor" and (p.stats["silver"], p.materials) == before
    assert _ids(game)[smithing.OPEN].label.startswith("打造防具…")


def test_the_armor_page_lists_at_most_eight_to_wield_best_first(content, world):
    """FB-134：防具頁的「換上」最多 equipment.DISMANTLE_LIST 件，修好之後減損高的先（同 armor.wanted 的鍵：整季機器人與假人要按的那一顆
    一定在上面），多的一行灰掉的說明指到修練頁，打造入口跟著上移。"""
    game = _smithy(content, world)  # 靜心訣（虛）
    p = game.state.player
    p.armor = _jacket(attribute="快", aid="甲:1")
    p.rack = [_jacket(attribute="剛", aid=f"甲:{i}", name="鐵葉甲") for i in range(2, 12)]  # 十件一樣的
    p.rack.append(_jacket(attribute="虛", tier=2, aid="甲:12", name="雲紋衫"))  # 最好的那一件（跟內功同屬性、二階）
    game.choose("act:smith")
    ids = list(_ids(game))
    wields = [i for i in ids if i.startswith("smith:wield:")]
    assert len(wields) == equipment.DISMANTLE_LIST and wields[0] == "smith:wield:甲:12"
    assert armor.wanted(game.state, content, _inner(game, content, world)) == wields[0]  # 機器人要按的就是第一顆
    more = _ids(game)["smith:wield-more"]
    assert not more.enabled and more.label == equipment.WIELD_MORE.format(n=3)
    assert ids.index(wields[-1]) < ids.index("smith:wield-more") < ids.index(smithing.OPEN)

# ── Task 4：淬煉防具、防具列與角色卡 ──

def test_armor_temper_takes_one_tier_one_material_and_charges_by_the_armor_tier(content, world):
    game = _armor_smith(content, world)
    p = game.state.player
    p.armor, p.materials = _jacket(tier=2), {"gang_1": 5, "gang_2": 1, "gang_3": 1}
    assert smithing.temper_material(game.state, content, "armor") == "gang_1"  # 料一律一階（鐵匠鋪與合成流程 3.7）
    assert smithing.temper_price(game.state, content, "armor") == 30  # 工錢照防具的階
    opt = _ids(game)[smithing.ARMOR_TEMPER]
    assert opt.enabled and opt.label == "淬煉【試甲】（第 1/5 次・精鐵砂×1＋30 兩）"
    ng = _inner(game, content, world)
    before = armor.cut(p.armor, ng, content)
    game.choose(smithing.ARMOR_TEMPER)
    assert p.armor.tempers == 1 and p.materials == {"gang_1": 4, "gang_2": 1, "gang_3": 1} and p.stats["silver"] == 170
    assert armor.cut(p.armor, ng, content) == pytest.approx(before + content.config.armor.temper_step)  # 減損每次 +1%（4.1）
    assert game.state.journal[0].title == smithing.TEMPER_TITLE


def test_armor_temper_stops_at_five_and_refuses_without_material_silver_or_armor(content, world):
    game = _armor_smith(content, world)
    p = game.state.player
    p.armor, p.materials = _jacket(tempers=5), {"gang_1": 3}
    opt = _ids(game)[smithing.ARMOR_TEMPER]
    assert not opt.enabled and smithing.FULL in opt.label
    assert smithing.temper(game.state, content, "armor") == [f"（{smithing.FULL}。）"] and p.materials == {"gang_1": 3}
    p.armor, p.materials = _jacket(tier=3), {"gang_2": 1, "gang_3": 1}
    assert smithing.temper_problem(game.state, content, "armor") == "沒有一階的料"  # 二階、三階的料不收（3.7）
    p.armor, p.materials, p.stats["silver"] = _jacket(tier=2), {"gang_1": 1}, 10
    assert smithing.temper_problem(game.state, content, "armor") == "還差 20 兩"
    p.armor = None
    assert smithing.ARMOR_TEMPER not in _ids(game) and smithing.temper_problem(game.state, content, "armor") == armor.NO_ARMOR
    p.armor, p.location = _jacket(), "lake"
    assert smithing.temper_problem(game.state, content, "armor") == weapons.NOT_HERE


def test_armor_temper_sits_after_repair_and_the_weapon_temper_is_untouched(content, world):
    game = _smithy(content, world, weapons_on=True)
    p = game.state.player
    rules.learn_skill(game.state, content, "sword")
    p.member.wugong_id = "sword"
    p.weapon = Weapon(id="兵:1", name="試刃", kind="劍", attribute="柔", tier=1, quality="下品")
    p.armor = _jacket(edge=40)
    game.choose("act:smith")
    weapon_page = list(_ids(game))
    assert smithing.TEMPER in weapon_page and smithing.ARMOR_TEMPER not in weapon_page
    game.choose("smith:page:armor")
    ids = list(_ids(game))
    assert smithing.TEMPER not in ids and ids.index(armor.REPAIR) < ids.index(smithing.ARMOR_TEMPER) < ids.index(smithing.OPEN)
    game.choose(smithing.ARMOR_TEMPER)
    assert p.armor.tempers == 1 and p.weapon.tempers == 0


# 鐵匠鋪與合成流程 3.4（B 批）：修與淬煉裝備庫裡的那一件（item_id；None＝身上那件，舊呼叫端一字不改）


def _two_jackets(content, world, **kw):
    """身上一件（甲:1，一階、耐久 40）、裝備庫一件（甲:2，二階、耐久 30）。"""
    game = _smithy(content, world, **kw)
    p = game.state.player
    p.armor = _jacket(edge=40)
    p.rack = [_jacket(tier=2, edge=30, aid="甲:2", name="庫甲")]
    return game


def test_the_worn_armors_own_id_is_the_same_as_no_id(content, world):
    a, b = _two_jackets(content, world, name="甲"), _two_jackets(content, world, name="乙")
    assert armor.repair_problem(a.state, content) == armor.repair_problem(b.state, content, "甲:1") is None
    assert smithing.temper_problem(a.state, content, "armor") == smithing.temper_problem(b.state, content, "armor", "甲:1") is None
    assert smithing.temper_material(a.state, content, "armor") == smithing.temper_material(b.state, content, "armor", "甲:1") == "gang_1"
    assert armor.repair(a.state, content) == armor.repair(b.state, content, "甲:1")
    assert smithing.temper(a.state, content, "armor") == smithing.temper(b.state, content, "armor", "甲:1")
    sa, sb = a.state.player, b.state.player
    assert (sa.armor, sa.rack, sa.materials, sa.stats["silver"]) == (sb.armor, sb.rack, sb.materials, sb.stats["silver"])


def test_repairing_a_rack_armor_leaves_the_worn_one_and_its_warning_alone(content, world):
    game = _two_jackets(content, world)
    p = game.state.player
    p.armor_warned = True
    msgs = armor.repair(game.state, content, "甲:2")
    assert [a.id for a in p.rack] == ["甲:2"] and p.rack[0].edge == 100 and p.armor.id == "甲:1" and p.armor.edge == 40
    assert p.armor_warned is True and p.stats["silver"] == 195 and p.materials == {"gang_1": 2, "gang_2": 2, "kuai_1": 2}
    assert msgs == ["鐵匠拿精鐵砂把【庫甲】補好了（銀兩 -5）。"]
    armor.repair(game.state, content, "甲:1")
    assert p.armor.edge == 100 and p.armor_warned is False


def test_a_rack_armor_is_repaired_only_when_it_needs_it_and_can_be_paid_for(content, world):
    game = _two_jackets(content, world)
    p, s = game.state.player, game.state
    p.rack[0].edge = 100
    assert armor.repair_problem(s, content, "甲:2") == armor.INTACT
    p.rack[0].edge = 30
    assert armor.repair_problem(s, content, "甲:2") is None
    assert armor.repair_problem(s, content, "甲:9") == equipment.RACK_MISSING
    assert armor.repair_problem(s, content, "兵:1") == equipment.RACK_MISSING  # 兵器的 id 不歸防具管
    p.stats["silver"] = 3
    assert armor.repair_problem(s, content, "甲:2") == "還差 2 兩"
    p.stats["silver"], p.materials = 200, {"gang_2": 2}
    assert armor.repair_problem(s, content, "甲:2") == equipment.NO_REPAIR_MATERIAL
    p.materials, p.location = {"gang_1": 3}, "lake"
    assert armor.repair_problem(s, content, "甲:2") == weapons.NOT_HERE
    before = (p.stats["silver"], dict(p.materials), p.rack[0].edge)
    assert armor.repair(s, content, "甲:2") == [f"（{weapons.NOT_HERE}。）"]
    assert (p.stats["silver"], dict(p.materials), p.rack[0].edge) == before


def test_tempering_a_rack_armor_pays_the_wage_of_that_very_armor_and_keeps_it_in_the_rack(content, world):
    game = _two_jackets(content, world)
    p, s = game.state.player, game.state
    p.materials = {"gang_1": 5, "gang_2": 1, "gang_3": 1}
    assert smithing.temper_material(s, content, "armor") == smithing.temper_material(s, content, "armor", "甲:2") == "gang_1"
    assert smithing.temper_price(s, content, "armor") == 0 and smithing.temper_price(s, content, "armor", "甲:2") == 30
    assert smithing.temper_problem(s, content, "armor", "甲:2") is None
    msgs = smithing.temper(s, content, "armor", "甲:2")
    assert p.rack[0].tempers == 1 and p.armor.tempers == 0 and p.armor.id == "甲:1" and [a.id for a in p.rack] == ["甲:2"]
    assert p.materials == {"gang_1": 4, "gang_2": 1, "gang_3": 1} and p.stats["silver"] == 170
    assert msgs[0] == "鐵匠拿精鐵砂把【庫甲】淬了一回，這是第 1 次。"
    p.rack[0].tempers = content.config.armor.temper_max
    assert smithing.temper_problem(s, content, "armor", "甲:2") == smithing.FULL
    assert smithing.temper_problem(s, content, "armor", "甲:9") == equipment.RACK_MISSING


def test_armor_rows_and_card_carry_tempers_and_the_recipe(content, world):
    game = _smithy(content, world)
    smithing.forge(game.state, content, world, smithing.ARMOR_KIND, "gang_1", "kuai_1", rng=random.Random(0))
    p = game.state.player
    p.armor.tempers = 2
    ng = _inner(game, content, world)
    row = armor.rows(game.state, content, ng)["worn"]
    assert row["tempers"] == 2 and row["temper_max"] == 5 and row["recipe"] == "精鐵砂＋驚羽"
    assert "・淬煉 2 次・" in armor.card_line(game.state, content, ng)
    p.armor = _jacket()
    row = armor.rows(game.state, content, ng)["worn"]
    assert row["recipe"] is None and row["tempers"] == 0 and "淬煉" not in armor.card_line(game.state, content, ng)


# ── Task 5：整季機器人打防具、淬防具；假人不打 ──

def test_wizard_steps_for_armor_have_no_kind():
    assert smithing.wizard_steps(smithing.ARMOR_KIND, "gang_1", "kuai_1") == [
        smithing.OPEN, f"{smithing.MAIN}gang_1", f"{smithing.AUX}kuai_1", GO_YANG]
    assert smithing.wizard_steps("劍", "gang_1", "kuai_1")[1] == f"{smithing.KIND}劍"  # 兵器照舊五顆


def test_armor_plan_reaches_for_the_highest_tier_and_stops_once_it_has_one(content, world):
    game = _smithy(content, world)
    s, p = game.state, game.state.player
    ng = _inner(game, content, world)  # 靜心訣（虛）：沒有同屬性的料，同階照數量；剛、陽都不剋虛
    assert smithing.armor_plan(s, content, world, ng) == (smithing.ARMOR_KIND, "gang_2", "gang_2")  # 最高階、夠兩個就主輔同一種
    p.materials = {"gang_2": 1, "gang_1": 2, "kuai_1": 3}
    assert smithing.armor_plan(s, content, world, ng) == (smithing.ARMOR_KIND, "gang_2", "kuai_1")  # 輔料挑低一階數量最多的
    p.rack = [_jacket(tier=2, aid="甲:3", recipe=armor.recipe_key("gang_2", "gang_2"))]
    assert smithing.armor_plan(s, content, world, ng) is None  # 已經有一件同階、自己打的
    p.rack = []
    p.stats["silver"] = 10
    assert smithing.armor_plan(s, content, world, ng) is None  # 打不起
    content.config.armor.enabled = False
    p.stats["silver"] = 200
    assert smithing.armor_plan(s, content, world, ng) is None and not smithing.armor_errand(s, content, world, ng)


def test_armor_plan_skips_pairs_the_inner_art_counters(content, world):
    """合出來會被內功剋的組合不打；被內功剋的那幾件不算「已經有了」。
    武學重構：基礎內功（粗淺吐納）兼容並蓄、沒有屬性，跟什麼都不剋；這裡改用寫死的吐納法（屬陰，陰陽相剋）。"""
    game = _smithy(content, world, inner="breath")  # 吐納法：屬陰，陽剋陰；精鐵砂（剛）＋驚羽（快）合出陽
    s, p = game.state, game.state.player
    ng = _inner(game, content, world)
    p.materials = {"gang_1": 2, "kuai_1": 1}
    assert smithing.armor_plan(s, content, world, ng) == (smithing.ARMOR_KIND, "gang_1", "gang_1")  # 剛＋快＝陽剋陰：改配剛＋剛（剛）
    p.materials = {"gang_1": 1, "kuai_1": 1}
    assert smithing.armor_plan(s, content, world, ng) is None  # 只合得出陽：不打
    p.materials = {"gang_1": 2, "kuai_1": 1}
    p.rack = [_jacket(attribute="陽", aid="甲:3", recipe=armor.recipe_key("gang_1", "kuai_1"))]  # 同階、自己打的，可是被內功剋
    assert smithing.armor_plan(s, content, world, ng) == (smithing.ARMOR_KIND, "gang_1", "gang_1")
    assert armor.clashes("陽", ng) and not armor.clashes("剛", ng) and not armor.clashes("剛", None)
    basic = team.player_art(s, content, world, "basic_breath")  # 兼容並蓄的基礎內功沒有屬性：不剋、不搭
    assert basic.attribute == "" and not armor.clashes("剛", basic) and not armor.clashes("柔", basic)


def test_forge_plan_for_weapons_is_unchanged_by_the_shared_picker(content, world):
    """兵器的 forge_plan 改走共用的 _pick_pair 之後一模一樣（這裡再鎖一次主料偏好武學屬性）。"""
    game = _smithy(content, world, weapons_on=True)
    s, p = game.state, game.state.player
    rules.learn_skill(s, content, "fist")  # 長拳：剛・拳腳
    p.member.wugong_id = "fist"
    art = team.player_art(s, content, world, "fist")
    p.materials = {"gang_1": 1, "kuai_1": 3}
    assert smithing.forge_plan(s, content, world, art) == ("拳腳", "gang_1", "kuai_1")  # 同階先挑跟武學同屬性的（剛），不是最多的


def test_visit_smith_forges_and_tempers_armor_then_leaves(content, world):
    from tianxia import bot
    game = _smithy(content, world, silver=30)  # 只開防具：架上 40 兩買不起，一爐一階 20 兩打得起
    p = game.state.player
    p.materials = {"gang_1": 6}
    bot.visit_smith(game)
    assert p.armor is not None and p.armor.recipe == armor.recipe_key("gang_1", "gang_1")
    assert p.armor.tempers == 4 and p.materials == {} and p.stats["silver"] == 10  # 打一件用兩個，剩四個全拿去淬（一階不收錢）
    assert not p.picking_smith and p.smith_draft is None


def test_visit_smith_does_weapons_first_then_forges_armor(content, world):
    from tianxia import bot
    game = _smithy(content, world, weapons_on=True)
    p = game.state.player
    rules.learn_skill(game.state, content, "sword")
    p.member.wugong_id = "sword"
    p.weapon = Weapon(id="兵:1", name="試刃", kind="劍", attribute="柔", tier=3, quality="上品", tempers=5)  # 兵器沒事要做
    p.armor = _jacket(attribute="剛", aid="甲:2")  # 架上那件買過了
    p.materials = {"gang_1": 2}
    bot.visit_smith(game)
    forged = [a for a in [p.armor, *p.rack] if a is not None and a.recipe == armor.recipe_key("gang_1", "gang_1")]
    assert len(forged) == 1 and p.stats["silver"] == 180 and p.materials == {}
    assert not p.picking_smith and p.smith_draft is None and p.smith_page == "weapon"


def test_visit_smith_never_leaves_an_armor_draft_open(content, world, monkeypatch):
    from tianxia import bot
    game = _smithy(content, world)
    monkeypatch.setattr(smithing, "wizard_steps", lambda kind, main, aux: [smithing.OPEN, f"{smithing.MAIN}{main}"])  # 走到一半就停
    bot.visit_smith(game)
    assert not game.state.player.picking_smith and game.state.player.smith_draft is None


def test_server_bots_forge_armor_step_by_step_and_never_temper_it(content, world):
    """打造第二批（PM 2026-10-12 決定第 3 條）：防具也照整季機器人的 armor_plan 一步一步打（防具沒有挑種類那一步：
    打開 → 主料 → 輔料 → 開爐）；淬煉永遠不按。"""
    from tianxia import bot_policy
    from tianxia.state import BotProfile
    game = _armor_smith(content, world)
    p = game.state.player
    p.armor = _jacket()  # 一階、買的、屬虛（對上靜心訣）：架上那件不比它好，不會先去買
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    plan = smithing.armor_plan(game.state, content, world, team.player_art(game.state, content, world, p.member.neigong_id))
    assert plan is not None and plan[0] == smithing.ARMOR_KIND
    pressed = []
    for _ in range(10):
        want = bot_policy._smith_want(game)
        scored = {o.id: bot_policy.score(game, o, profile) for o in game.options(odds=False)}
        assert scored.get(smithing.ARMOR_TEMPER) is None  # 不淬煉
        if want is None:
            break
        assert scored[want] == bot_policy.SMITH_SCORE
        pressed.append(want)
        game.choose(want)
    assert pressed[:4] == smithing.wizard_steps(*plan) and p.smith_draft is None  # 之後可能多一顆「換上」打出來的那件
    assert smithing.recipe_key(*plan) in {a.recipe for a in [p.armor, *p.rack] if a is not None and a.slot == "armor"}


# ── 鐵匠鋪與合成流程 3.6（D 批）：品質有「質」的差別（防具；兵器的在 test_weapons_forge.py）──


def _graded(content):
    """稿的佔位值：淬煉上限下品 5、中品 6、上品 7；上品每場少扣 1（防具自己一組，四欄設計 2.6、3.4）。"""
    content.config.armor.temper_max_by_quality = {"下品": 5, "中品": 6, "上品": 7}
    content.config.armor.wear_less_by_quality = {"上品": 1}
    return content


def test_the_armor_temper_cap_follows_the_quality_and_reads_the_armor_group(content):
    low, mid, top = (_jacket(quality=q) for q in ("下品", "中品", "上品"))
    assert content.config.armor.temper_max_by_quality == {}
    assert [smithing.temper_cap(a, content) for a in (low, mid, top)] == [5, 5, 5]  # 設定沒寫那一組：跟以前一字不差
    _graded(content)
    assert [smithing.temper_cap(a, content) for a in (low, mid, top)] == [5, 6, 7]
    assert smithing.temper_cap(_jacket(quality=""), content) == content.config.armor.temper_max
    weapon = Weapon(id="兵:1", name="刃", kind="劍", attribute="柔", tier=1, quality="上品")
    assert smithing.temper_cap(weapon, content) == 5  # 兵器那一組沒寫：防具寫了不影響兵器


def test_top_quality_armor_wears_one_less_but_never_below_one(content, world):
    game = _smithy(content, world)
    p, s = game.state.player, game.state
    rule = content.config.armor
    tiers = ("大勝", "險勝", "僵持", "落敗")
    assert rule.wear == {"大勝": 1, "險勝": 2, "僵持": 3, "落敗": 5}

    def lost(quality, tier):
        p.armor = _jacket(quality=quality)
        armor.wear(s, content, tier)
        return 100 - p.armor.edge

    assert [lost(q, t) for q in ("下品", "中品", "上品") for t in tiers] == [1, 2, 3, 5] * 3  # 沒寫那一組：跟以前一字不差
    _graded(content)
    assert [lost(q, t) for q in ("下品", "中品") for t in tiers] == [1, 2, 3, 5] * 2
    assert [lost("上品", t) for t in tiers] == [1, 1, 2, 4]  # 大勝本來只扣 1：上品那一場等於沒省（刻意）
    assert lost("上品", "平手") == 0  # 本來不扣的不扣
    assert equipment.wear_note(_jacket(quality="上品"), content) == "磨得慢" and equipment.wear_note(_jacket(quality="中品"), content) == ""


def test_each_armor_quality_tempers_up_to_its_own_cap_and_then_is_full(content, world):
    _graded(content)
    for quality, cap in (("下品", 5), ("中品", 6), ("上品", 7)):
        game = _armor_smith(content, world, name=f"淬{quality}")
        p = game.state.player
        p.armor, p.materials, p.stats["silver"] = _jacket(quality=quality), {"gang_1": 9}, 500
        for n in range(1, cap + 1):
            opt = _ids(game)[smithing.ARMOR_TEMPER]
            assert opt.enabled and f"第 {n}/{cap} 次" in opt.label
            game.choose(smithing.ARMOR_TEMPER)
        assert p.armor.tempers == cap
        opt = _ids(game)[smithing.ARMOR_TEMPER]
        assert not opt.enabled and smithing.FULL in opt.label
        assert smithing.temper(game.state, content, "armor") == [f"（{smithing.FULL}。）"] and p.armor.tempers == cap


def test_the_armor_group_has_its_own_temper_material_tier_and_a_tier_four_coat_asks_for_no_tier_three(content, world):
    game = _armor_smith(content, world)
    p, s = game.state.player, game.state
    p.armor, p.materials = _jacket(tier=4), {"gang_1": 1}
    assert smithing.temper_problem(s, content, "armor") is None and smithing.temper_price(s, content, "armor") == 150  # 一個一階＋150 兩
    content.config.weapons.temper_material_tier = 2  # 兵器那一組改了，不影響防具
    assert smithing.temper_material(s, content, "armor") == "gang_1"
    content.config.armor.temper_material_tier = 2
    assert smithing.temper_material(s, content, "armor") is None and smithing.temper_problem(s, content, "armor") == "沒有二階的料"


def test_the_whole_season_bot_tempers_a_top_quality_jacket_seven_times(content, world, monkeypatch):
    from tianxia import bot
    _graded(content)
    game = _smithy(content, world)
    p = game.state.player
    p.armor, p.materials, p.stats["silver"] = _jacket(quality="上品"), {"gang_1": 9}, 500
    monkeypatch.setattr(smithing, "armor_plan", lambda *a, **k: None)  # 只看淬煉：不讓它先拿素材去打一件
    assert smithing.armor_temper_wanted(game.state, content, world, _inner(game, content, world))
    bot.visit_smith(game)
    assert p.armor.tempers == 7 and p.materials == {"gang_1": 2}
    assert not smithing.armor_temper_wanted(game.state, content, world, _inner(game, content, world))


def test_a_divine_original_armor_is_top_quality_for_the_cap_and_the_rows_write_it(content, world):
    _graded(content)
    game = _smithy(content, world)
    p, s = game.state.player, game.state
    original = _jacket(tier=3, quality="上品", aid="甲:2", name="原品甲")
    original.original = True
    p.armor, p.rack = _jacket(quality="中品"), [original]
    assert smithing.temper_cap(original, content) == 7
    ng = _inner(game, content, world)
    data = armor.rows(s, content, ng)
    assert data["worn"]["temper_max"] == 6 and data["rack"][0]["temper_max"] == 7
    assert data["worn"]["wear_note"] == "" and data["rack"][0]["wear_note"] == "磨得慢"
    from tianxia import shopview
    view = shopview.smith_view(s, content, world)
    assert view["worn"]["item"]["temper_max"] == 6 and view["rack"]["rows"][0]["temper_max"] == 7
    assert view["worn"]["item"]["wear_note"] == "" and view["rack"]["rows"][0]["wear_note"] == "磨得慢"
