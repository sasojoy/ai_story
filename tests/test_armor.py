"""防具與裝備四欄（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第二～四節、第九節；
計畫 docs/superpowers/plans/2026-10-10-裝備-1-四欄化與防具.md）。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from conftest import next_season, real_content, walk_to
from tianxia import armor, encounter, equipment, rules, team, weapons
from tianxia.state import BattleRecord, Equipment, Weapon


def _on(content, weapons_on=False):
    """打開防具（測試內容三欄都關著）；weapons_on 連武器也開。"""
    content.config.armor.enabled = True
    content.config.weapons.enabled = weapons_on
    return content


def _jacket(attribute="虛", tier=1, quality="下品", edge=100, aid="甲:1", name="試甲"):
    return Equipment(id=aid, slot="armor", name=name, attribute=attribute, tier=tier, quality=quality, edge=edge)


def _blade(aid="兵:3", name="厚背刀", kind="刀", attribute="剛"):
    return Weapon(id=aid, name=name, kind=kind, attribute=attribute, tier=1, quality="下品")


def _game(content, world, name="試甲", inner="calm"):
    """身上一門內功（預設靜心訣，屬虛：它的一般功效是「險」，不碰扣血；粗淺吐納屬柔，會帶化勁）。"""
    from tianxia.engine import Game
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    rules.learn_skill(game.state, content, inner)
    game.state.player.member.neigong_id = inner
    return game


def _neigong(game, content, world):
    return team.player_art(game.state, content, world, game.state.player.member.neigong_id)


def _town(content, world, silver=200, weapons_on=False, name="試甲", inner="calm"):
    """站在測試內容的城鎮（town：標籤城鎮）。"""
    _on(content, weapons_on)
    game = _game(content, world, name=name, inner=inner)
    p = game.state.player
    p.location, p.stamina, p.stats["silver"] = "town", 100.0, silver
    p.materials = {}
    game.sync(0.0)
    return game


def _ids(game):
    return {o.id: o for o in game.options(odds=False)}


# ── Task 1：資料形狀與 equipment ──

def test_weapon_is_the_same_model_as_equipment_and_defaults_to_the_weapon_slot():
    assert Weapon is Equipment
    assert _blade().slot == "weapon"
    a = _jacket()
    assert a.kind == "" and a.slot == "armor" and Equipment.model_validate_json(a.model_dump_json()) == a


def test_fixture_turns_armor_off_and_real_content_on(content):
    assert content.config.armor.enabled is False
    real = real_content().config.armor
    assert real.enabled is True and real.total_cap == 0.6 and real.shop_price == 40 and real.repair_silver == 5
    assert real.tier_cut == {"1": 0.06, "2": 0.12, "3": 0.18}
    assert real.wear == {"大勝": 1, "險勝": 2, "僵持": 3, "落敗": 5}


def test_slots_are_on_by_their_own_switch_and_unknown_slots_are_off(content):
    assert not equipment.on(content, "weapon") and not equipment.on(content, "armor")
    content.config.armor.enabled = True
    assert equipment.on(content, "armor") and not equipment.on(content, "weapon")
    assert not equipment.on(content, "mount") and not equipment.on(content, "treasure")  # 這一批表外的欄位一律關著


def test_store_puts_each_slot_on_when_empty_and_counts_the_rack_across_slots(content, world):
    game = _town(content, world, weapons_on=True)
    s, p = game.state, game.state.player
    assert equipment.store(s, _jacket()) == "你穿上了【試甲】。" and p.armor.id == "甲:1"
    assert equipment.store(s, _jacket(aid="甲:2", name="鐵葉甲")) == "【鐵葉甲】放上了裝備庫。"
    content.config.weapons.rack_cap = 2
    assert not equipment.rack_full(s, content, "weapon")  # 武器欄空著：新的一把直接拿上手，用不到裝備庫
    p.rack.append(_blade())
    assert equipment.rack_full(s, content, "armor")  # 裝備庫兩格（一件防具、一把兵器）合算滿了
    assert equipment.next_id(s, "armor") == "甲:1" and equipment.next_id(s, "weapon") == "兵:2"  # 共用 weapon_serial


def test_wield_takes_each_item_into_its_own_slot_and_resets_its_reminder(content, world):
    game = _town(content, world, weapons_on=True)
    p = game.state.player
    p.armor, p.armor_warned = _jacket(edge=20), True
    p.rack = [_jacket(aid="甲:2", name="鐵葉甲", attribute="剛"), _blade()]
    assert game.wield_weapon("甲:2") == ["你換上了【鐵葉甲】。"]
    assert p.armor.id == "甲:2" and p.armor_warned is False and p.weapon is None
    assert [i.id for i in p.rack] == ["兵:3", "甲:1"]  # 換下來的那件回裝備庫
    assert game.wield_weapon("兵:3") == ["你換上了【厚背刀】。"] and p.weapon.id == "兵:3"
    assert game.state.journal[0].tag == "你換上了【厚背刀】。"  # 修練紀錄照舊


def test_wield_and_dismantle_obey_the_slot_switch_after_finding_the_item(content, world):
    game = _town(content, world)  # 只開防具
    p = game.state.player
    p.rack = [_blade(), _jacket(aid="甲:2")]
    assert game.wield_weapon("兵:3") == ["（此刻無法這麼做。）"]  # 武器關著：裝備庫裡的兵器不能動
    assert game.dismantle_weapon("兵:3") == ["（此刻無法這麼做。）"] and len(p.rack) == 2
    assert game.wield_weapon("甲:9") == [equipment.WIELD_MISSING]  # 防具開著：找不到就是找不到
    assert game.dismantle_weapon("甲:2")[0].startswith(equipment.DISMANTLE_PREFIX)
    assert [i.id for i in p.rack] == ["兵:3"] and sum(p.materials.values()) == 1
    content.config.armor.enabled = False
    assert game.wield_weapon("甲:9") == ["（此刻無法這麼做。）"]


def test_armor_can_be_changed_in_seclusion_and_on_the_road(content, world):
    """設計 2.3：武器、防具隨時能換（含閉關中、路上）、不花體力。之後坐騎、寶物加換裝限制（2.3 的三條）時不能誤擋到防具。"""
    game = _town(content, world)
    p = game.state.player
    p.rack = [_jacket(aid="甲:2", name="鐵葉甲", attribute="剛"), _jacket(aid="甲:3", name="軟皮甲", attribute="柔")]
    p.busy_until = game.state.world.time + 3600.0  # 閉關中（同 tests/test_engine.py 的寫法）
    assert game.wield_weapon("甲:2") == ["你換上了【鐵葉甲】。"] and p.armor.id == "甲:2"
    p.busy_until = None
    game.choose("move:lake")
    assert p.journey is not None  # 在路上
    stamina = p.stamina
    assert game.wield_weapon("甲:3") == ["你換上了【軟皮甲】。"] and p.armor.id == "甲:3" and p.stamina == stamina
    assert [i.id for i in p.rack] == ["甲:2"]


def test_a_new_season_starts_with_no_armor_and_an_empty_rack(content, world):
    game = _town(content, world)
    p = game.state.player
    p.armor, p.rack, p.smith_page = _jacket(), [_jacket(aid="甲:2")], "armor"
    next_season(content, world, game)
    p = game.state.player
    assert p.armor is None and p.rack == [] and p.smith_page == "weapon" and p.weapon_serial == 0  # 新欄位跟著新角色重來（設計 2.4）


# ── Task 2：防具的規則 ──

def test_cut_adds_tier_quality_and_the_inner_art_then_scales_by_durability(content, world):
    _on(content)
    game = _game(content, world)
    ng = _neigong(game, content, world)  # 靜心訣：虛
    assert armor.cut(_jacket(), ng, content) == pytest.approx(0.06 + 0.03)  # 同屬性 +3%
    assert armor.cut(_jacket(attribute="實"), ng, content) == pytest.approx(0.06 - 0.03)  # 實剋虛（兩個方向都查）
    assert armor.cut(_jacket(attribute="柔"), ng, content) == pytest.approx(0.06)
    assert armor.cut(_jacket(edge=80), ng, content) == pytest.approx(0.09 * 0.9)  # 設計 2.5 的例子：8.1%
    assert armor.cut(_jacket(edge=0), ng, content) == pytest.approx(0.09 * 0.5)  # 全壞剩一半
    best = _jacket(tier=3, quality="上品").model_copy(update={"tempers": 5})
    assert armor.cut(best, ng, content) == pytest.approx(0.30)  # 最好的：18＋4＋5＋3
    assert armor.cut(_jacket(), None, content) == pytest.approx(0.06)  # 沒有內功：沒有那 ±3%
    assert armor.cut(_blade(), ng, content) == 0.0  # 不是防具那一欄的
    content.config.armor.enabled = False
    assert armor.cut(_jacket(), ng, content) == 0.0 and armor.cut(None, ng, content) == 0.0


def test_wear_by_tier_and_warn_once(content, world):
    _on(content)
    game = _game(content, world)
    s, p = game.state, game.state.player
    p.armor = _jacket(edge=34)
    assert armor.wear(s, content, "大勝") == [] and p.armor.edge == 33  # 大勝扣 1（武器是 2）
    assert armor.wear(s, content, "險勝") == [] and p.armor.edge == 31
    assert armor.wear(s, content, "僵持") == [armor.WORN_WARNING.format(name="試甲")] and p.armor.edge == 28
    assert armor.wear(s, content, "落敗") == [] and p.armor.edge == 23  # 只提醒一次
    p.armor.edge = 2
    armor.wear(s, content, "落敗")
    assert p.armor.edge == 0
    content.config.armor.enabled = False
    assert armor.wear(s, content, "落敗") == [] and p.armor.edge == 0


def test_only_training_wild_fights_and_a_lost_raid_wear_the_armor():
    assert armor.wears("train", "大勝") and armor.wears("wild", "落敗")
    assert armor.wears("raid", "落敗") and not armor.wears("raid", "大勝") and not armor.wears("raid", "僵持")
    for kind in ("spar", "duel", "event"):
        assert not armor.wears(kind, "落敗")


def test_buy_one_of_four_shop_pieces_puts_it_on(content, world):
    game = _town(content, world)
    s, p = game.state, game.state.player
    assert armor.SHOP_ATTRIBUTES == ("剛", "柔", "快", "慢")
    assert armor.buy(s, content, "柔") == ["你花 40 兩買下一件【軟皮甲】。", "你穿上了【軟皮甲】。"]
    assert p.armor.slot == "armor" and p.armor.id == "甲:1" and p.armor.tier == 1 and p.armor.quality == "下品"
    assert p.stats["silver"] == 160
    assert armor.buy(s, content, "剛")[-1] == "【鐵葉甲】放上了裝備庫。"
    assert armor.buy(s, content, "陰") == ["（沒有這一件。）"]
    p.stats["silver"] = 10
    assert armor.buy(s, content, "快") == ["（還差 30 兩。）"] and p.stats["silver"] == 10
    content.config.weapons.rack_cap = 1
    p.stats["silver"] = 200
    assert armor.buy_problem(s, content, "快") == equipment.RACK_FULL
    p.location = "lake"
    assert armor.buy_problem(s, content, "快") == equipment.NOT_HERE


def test_repair_needs_a_tier_one_material_and_silver_at_the_smith(content, world):
    game = _town(content, world)
    s, p = game.state, game.state.player
    assert armor.repair(s, content) == [f"（{armor.NO_ARMOR}。）"]
    p.armor, p.armor_warned = _jacket(edge=20), True
    assert armor.repair_problem(s, content) == equipment.NO_REPAIR_MATERIAL
    p.materials = {"kuai_1": 2, "gang_1": 1}
    msgs = armor.repair(s, content)
    assert p.armor.edge == 100 and not p.armor_warned and p.stats["silver"] == 195
    assert p.materials == {"kuai_1": 1, "gang_1": 1} and "驚羽" in msgs[0]  # 用數量最多的一階素材
    assert armor.repair_problem(s, content) == armor.INTACT
    p.armor.edge, p.stats["silver"] = 10, 2
    assert armor.repair_problem(s, content) == "還差 3 兩"
    p.location = "lake"
    assert armor.repair_problem(s, content) == equipment.NOT_HERE


def test_wanted_wields_a_better_piece_then_buys_then_repairs(content, world):
    game = _town(content, world, inner="basic_breath")  # 粗淺吐納：屬柔，架上有軟皮甲
    s, p = game.state, game.state.player
    ng = _neigong(game, content, world)
    assert armor.wanted(s, content, ng) == f"{armor.BUY}柔"  # 跟內功同屬性的那一件
    p.armor = _jacket(attribute="剛")  # 剛剋柔：3%
    p.rack = [_jacket(aid="甲:2", attribute="快", edge=10)]  # 不剋：修好之後 6%
    assert armor.wanted(s, content, ng) == "smith:wield:甲:2"  # 比的是修好之後的減損
    p.armor, p.rack = _jacket(attribute="快", edge=40), []
    assert armor.wanted(s, content, ng) == f"{armor.BUY}柔"  # 架上有同屬性的（9%）
    p.armor = _jacket(attribute="柔", edge=40)
    p.materials = {"gang_1": 1}
    assert armor.wanted(s, content, ng) == armor.REPAIR
    p.armor.edge = 60
    assert armor.wanted(s, content, ng) is None  # 耐久 50 以上不修
    p.location = "lake"
    assert armor.wanted(s, content, ng) is None


def test_wanted_buys_a_piece_that_does_not_clash_when_the_shop_has_no_match(content, world):
    game = _town(content, world)  # 靜心訣：虛，架上沒有虛
    s, p = game.state, game.state.player
    ng = _neigong(game, content, world)
    assert armor.wanted(s, content, ng) == f"{armor.BUY}剛"  # 剛不剋虛：照剛柔快慢的順序第一件
    p.armor = _jacket(attribute="剛", name="鐵葉甲")
    assert armor.wanted(s, content, ng) is None  # 身上那件跟架上一樣好：不會路過就再買一件
    assert armor.wanted(s, content, None) is None  # 沒有內功也一樣挑剛


def test_rows_and_card_line(content, world):
    _on(content)
    game = _game(content, world)
    s, p = game.state, game.state.player
    ng = _neigong(game, content, world)
    assert armor.card_line(s, content, ng) == ""
    p.armor = _jacket(edge=80)
    p.rack = [_jacket(aid="甲:2", name="鐵葉甲", attribute="實", tier=2, quality="中品"), _blade()]
    assert armor.card_line(s, content, ng) == "防具　【試甲】屬虛・一階下品・耐久度 80，一場少扣 8% 氣血（跟你的內功同屬性）"
    data = armor.rows(s, content, ng)
    assert data["worn"]["cut"] == "8%" and data["worn"]["confirm"] == "" and data["worn"]["grade"] == "一階下品"
    assert data["worn"]["wear_word"] == equipment.WEAR_WORDS["armor"] == "耐久度" and data["worn"]["recipe"] is None  # 不是自己打的：沒有配方
    assert [r["id"] for r in data["rack"]] == ["甲:2"]  # 裝備庫裡的兵器不列在防具那一段
    assert data["rack"][0]["fit"] == armor.CLASH_NOTE and data["rack"][0]["cut"] == "11%"  # 12＋2－3
    assert data["rack"][0]["confirm"] == "把【鐵葉甲】（二階中品）拆成玄鋼骨×1？拆掉就沒了。"
    content.config.armor.enabled = False
    assert armor.rows(s, content, ng) == {"worn": None, "rack": []} and armor.card_line(s, content, ng) == ""


def test_shop_names_are_original_and_do_not_clash_with_weapons():
    from tianxia import naming
    from tianxia.models import WEAPON_KINDS
    c = real_content()
    names = set(armor.SHOP_NAMES.values())
    assert set(armor.SHOP_NAMES) == set(armor.SHOP_ATTRIBUTES) and len(names) == 4
    assert not names & {weapons.shop_name(k, a) for k in WEAPON_KINDS for a in weapons.ATTR_WORDS}
    taken = {s.name for s in c.skills.values()} | {m.name for m in c.materials.values()} | {ch.name for ch in c.characters.values()}
    assert not names & taken
    assert not [n for n in names if naming.name_problem(n, c, None)]


# ── Task 3：扣氣血、截殺、磨耐久 ──

def _hp_lost(state, content, world, tier):
    """直接扣一場（team.take_encounter_toll）：本人掉了多少氣血、多了多少內傷。"""
    member = state.player.member
    con = team.con_of(state, content, world, "player")
    before, _ = team.member_neili(content, member, con)
    injury = member.injury
    team.take_encounter_toll(state, content, world, tier)
    after, _ = team.member_neili(content, member, con)
    return before - after, member.injury - injury


def _soft(game, layers=3):
    """身上換一門化勁 layers 層的武學（照 tests/test_trait_numbers.py::_wear；三層是 30%）。"""
    from tianxia.martial_arts import generate_from_name
    art = generate_from_name("護體拳", "武學", "護體拳", attribute="柔").model_copy(
        update={"origin": "fused", "traits": ["柔"] * layers, "special": None},
    )
    game.world.claim_skill_name(art)
    game.state.player.member.wugong_id = art.id
    game.state.player.art_quality[art.id] = "下品"
    return art


def _fought(game, tier):
    """在湖邊打一場、結果寫死（同 tests/test_trait_numbers.py::_fought），回傳那一場的戰報。"""
    if game.state.player.location != "lake":
        walk_to(game, "lake")
    result = encounter.EncounterResult(tier=tier, margin=0, our_power=10, difficulty=5)
    with mock.patch.object(team, "fight", return_value=result):
        game.choose("act:train")
    return game.state.battles[0]


def test_armor_cuts_the_player_toll_and_injury_by_the_same_share(content, world):
    _on(content)
    game = _game(content, world)
    game.state.player.armor = _jacket()  # 虛對虛：9%
    bare = game.state.model_copy(deep=True)
    bare.player.armor = None
    lost, hurt = _hp_lost(game.state, content, world, "落敗")
    lost0, hurt0 = _hp_lost(bare, content, world, "落敗")
    assert lost == pytest.approx(lost0 * 0.91) and hurt == pytest.approx(hurt0 * 0.91)
    assert team.armor_cut(game.state, content, world) == pytest.approx(0.09)
    content.config.armor.enabled = False
    assert team.armor_cut(game.state, content, world) == 0.0


def test_soft_and_armor_together_are_capped_at_sixty_percent(game):
    content, world = _on(game.content), game.world
    content.config.armor.tier_cut = {"1": 0.5}  # 防具 50%（沒有內功：沒有 ±3%）＋化勁 30%：超過合計上限
    _soft(game)
    game.state.player.armor = _jacket()
    bare = game.state.model_copy(deep=True)
    bare.player.member.wugong_id = None  # 拿掉化勁
    bare.player.armor = None
    lost, _ = _hp_lost(game.state, content, world, "落敗")
    lost0, _ = _hp_lost(bare, content, world, "落敗")
    assert lost == pytest.approx(lost0 * 0.4)


def test_toll_saved_stays_zero_with_armor_alone(content, world):
    _on(content)
    game = _game(content, world)
    game.state.player.armor = _jacket()
    assert team.toll_saved(game.state, content, world, "落敗") == (0, 0)  # 防具不是功效：不寫化勁那一句


def test_soft_says_only_what_it_saved_on_top_of_the_armor(game):
    """FB-084 加上防具（設計 4.3）：戰鬥卡片「（化勁）少扣了 N 點」是「只有防具」跟「防具加化勁」的差，不把防具省的算給化勁。"""
    content = _on(game.content)
    rules.learn_skill(game.state, content, "calm")
    game.state.player.member.neigong_id = "calm"
    _soft(game)  # 化勁 30%
    game.state.player.armor = _jacket()  # 虛對虛：9%
    walk_to(game, "lake")
    plain = game.state.model_copy(deep=True)
    plain.player.member.wugong_id = None  # 只拿掉化勁、留著防具
    armor_only, _ = _hp_lost(plain, content, game.world, "落敗")
    record = _fought(game, "落敗")
    shown = next(int(ch.removeprefix("氣血 -")) for ch in record.changes if ch.startswith("氣血 -"))
    (line,) = [x for x in record.trait_before + record.trait_after if x.startswith("〔化勁〕")]
    assert line.endswith(f"（少扣了 {round(armor_only) - shown} 點氣血）")
    assert shown == round(armor_only * (1 - 0.39) / (1 - 0.09))  # 真的扣的是防具加化勁 39%


@pytest.mark.parametrize("kind,tier,worn", [
    ("train", "大勝", True), ("wild", "落敗", True), ("raid", "落敗", True), ("raid", "大勝", False),
    ("spar", "落敗", False), ("duel", "落敗", False), ("event", "落敗", False),
])
def test_file_battle_wears_the_armor_only_in_training_wild_and_a_lost_raid(content, world, kind, tier, worn):
    _on(content)
    game = _game(content, world)
    game.state.player.armor = _jacket()
    record = BattleRecord(id=1, time=0.0, location="湖邊", kind=kind, event="劇情", opponent="誰", ours=[], tier=tier,
                          our_power=1.0, difficulty=1.0)
    game._file_battle(record)
    assert (game.state.player.armor.edge < 100) is worn


def test_both_reminders_reach_the_record_and_the_journal_lines(content, world):
    """防具破了的提醒照兵器的做法，戰鬥卡片與江湖紀錄都寫（計畫「範圍與取捨」；設計第九節的「戰報不寫防具」指每一場不寫省了多少）。"""
    _on(content, weapons_on=True)
    game = _game(content, world)
    p = game.state.player
    p.armor = _jacket(edge=31)
    p.weapon = Weapon(id="兵:1", name="試刃", kind="劍", attribute="柔", tier=1, quality="下品", edge=31)
    record = BattleRecord(id=1, time=0.0, location="湖邊", kind="train", event="", opponent="誰", ours=[], tier="落敗",
                          our_power=1.0, difficulty=1.0)
    game._file_battle(record)
    assert record.notes == [weapons.EDGE_WARNING.format(name="試刃"), armor.WORN_WARNING.format(name="試甲")]
    assert game._last_wear == record.notes  # 切磋、截殺的訊息與守方的江湖紀錄都從這裡讀


def test_challenging_a_great_figure_wears_the_armor_like_training(world):
    from tianxia.encounter import EncounterResult
    from tianxia.engine import Game
    c = real_content()
    c.config.season_one = True
    c.config.auto_open_first_season = True
    game = Game.new(c, "官甲", rng=random.Random(0), world=world)
    game.client = None
    p = game.state.player
    p.faction, p.location = "guan", "huangjin_camp"
    p.tutorial_step = len(c.tutorial.steps)
    p.visited.add("huangjin_camp")
    p.stamina = 250.0
    game.now = 1000.0
    p.armor = _jacket()
    fight = EncounterResult(tier="險勝", margin=20, our_power=200, difficulty=120)
    with mock.patch.object(team, "fight", return_value=fight):
        game.choose("act:challenge:bocai")
    assert game.state.battles[0].kind == "event" and p.armor.edge == 98  # 挑戰本人的戰報是 event，但防具照磨（險勝扣 2）


# ── Task 4：鐵匠鋪分兵器、防具兩頁 ──

def test_with_both_on_the_smith_opens_on_the_weapon_page_and_switches(content, world):
    from tianxia import smithing
    game = _town(content, world, weapons_on=True)
    p = game.state.player
    game.choose("act:smith")
    ids = list(_ids(game))
    assert "smith:buy:劍" in ids and ids[-2:] == ["smith:page:armor", "smith:back"]  # 切頁排在「離開」前面
    assert not any(i.startswith(armor.BUY) for i in ids) and p.smith_page == "weapon"
    entries = len(game.state.journal)
    assert game.choose("smith:page:armor") == [] and p.smith_page == "armor"
    assert len(game.state.journal) == entries  # 切頁不寫紀錄
    ids = list(_ids(game))
    assert ids[:4] == [f"{armor.BUY}{a}" for a in armor.SHOP_ATTRIBUTES] and ids[-2:] == ["smith:page:weapon", "smith:back"]
    assert not any(i.startswith(("smith:buy:", smithing.KIND)) for i in ids)
    assert _ids(game)[smithing.OPEN].label.startswith("打造防具…")  # 兩頁各有自己的打造入口（防具打造）
    game.choose("smith:page:weapon")
    assert p.smith_page == "weapon" and "smith:buy:劍" in _ids(game)


def test_with_only_armor_on_the_smith_opens_on_the_armor_page_and_closes_away_from_town(content, world):
    from tianxia import smithing
    game = _town(content, world)  # 武器關、防具開（測試內容的武器本來就關著）
    p = game.state.player
    assert "act:smith" in _ids(game)
    game.choose("act:smith")
    ids = list(_ids(game))
    assert p.smith_page == "armor" and ids[-1] == "smith:back"
    assert not any(i.startswith(("smith:buy:", "smith:page:", smithing.KIND)) for i in ids)  # 沒有灰掉的兵器鈕、沒有切頁
    assert _ids(game)[smithing.OPEN].label.startswith("打造防具…")  # 只開防具：打造入口是防具的
    p.location = "lake"
    game.sync(1.0)
    assert not p.picking_smith and "act:smith" not in _ids(game)


def test_with_only_weapons_on_the_menu_has_no_page_button(content, world):
    game = _town(content, world, weapons_on=True)
    content.config.armor.enabled = False
    game.choose("act:smith")
    ids = list(_ids(game))
    assert ids[-1] == "smith:back" and not any(i.startswith("smith:page:") for i in ids)
    assert game.state.player.smith_page == "weapon"


def test_armor_page_buys_repairs_wields_and_dismantles(content, world):
    game = _town(content, world, inner="basic_breath")  # 粗淺吐納：屬柔
    p = game.state.player
    game.choose("act:smith")
    opts = _ids(game)
    assert "少扣 9% 氣血・跟你的內功同屬性・40 兩" in opts[f"{armor.BUY}柔"].label
    assert "跟你的內功相剋" in opts[f"{armor.BUY}剛"].label
    game.choose(f"{armor.BUY}柔")
    game.choose(f"{armor.BUY}快")
    assert p.armor.name == "軟皮甲" and [a.name for a in p.rack] == ["輕綃衫"]
    p.armor.edge, p.materials = 40, {"gang_1": 1}
    opts = _ids(game)
    spare = p.rack[0].id
    assert opts[armor.REPAIR].label == "修【軟皮甲】（耐久度 40・精鐵砂×1＋5 兩）"
    assert opts[f"smith:dismantle:{spare}"].confirm.startswith("把【輕綃衫】（一階下品）拆成")
    assert opts[f"smith:dismantle:{spare}"].confirm_yes == "拆掉"  # FB-125：防具頁的拆解也先問一次
    ids = list(opts)
    assert ids.index(armor.REPAIR) < ids.index(f"smith:wield:{spare}") < ids.index(f"smith:dismantle:{spare}") < ids.index("smith:back")
    game.choose(armor.REPAIR)
    assert p.armor.edge == 100 and p.stats["silver"] == 200 - 40 - 40 - 5
    game.choose(f"smith:wield:{spare}")
    assert p.armor.name == "輕綃衫" and [a.name for a in p.rack] == ["軟皮甲"]
    game.choose(f"smith:dismantle:{p.rack[0].id}")
    assert p.rack == [] and sum(p.materials.values()) == 1 and p.picking_smith  # 做完選單還開著


@pytest.mark.parametrize("exit_by", ["back", "walk_away", "depart", "reconcile"])
def test_every_way_out_of_the_smith_resets_the_page(content, world, exit_by):
    game = _town(content, world, weapons_on=True)
    p = game.state.player
    game.choose("act:smith")
    game.choose("smith:page:armor")
    if exit_by == "back":
        game.choose("smith:back")
    elif exit_by == "walk_away":
        p.location = "lake"
        game.sync(1.0)
    elif exit_by == "depart":
        game.travel_refusal = lambda *a, **k: None  # 繞過「鐵匠鋪還開著」的檢查，直接測 _depart 的防線（同 test_weapons）
        game.travel("lake", "dash")
    else:
        content.config.weapons.enabled = content.config.armor.enabled = False
        game._drop_stale_references()
    assert not p.picking_smith and p.smith_page == "weapon" and p.smith_draft is None


def test_a_button_from_the_other_page_does_nothing(content, world):
    """兩個分頁一個停在兵器頁、一個停在防具頁：另一頁的鈕不在選單上，按了什麼都不動（choose 只認選單上真的有的）。"""
    game = _town(content, world, weapons_on=True)
    p = game.state.player
    game.choose("act:smith")
    assert game.choose(f"{armor.BUY}柔") == ["（此刻無法這麼做。）"] and p.armor is None and p.stats["silver"] == 200
    game.choose("smith:page:armor")
    assert game.choose("smith:buy:劍") == ["（此刻無法這麼做。）"] and p.weapon is None and p.stats["silver"] == 200
    assert game.choose("smith:page:armor") == ["（此刻無法這麼做。）"]  # 已經在防具頁：切到同一頁的鈕不在選單上


def test_a_forging_draft_is_dropped_when_weapons_close_and_the_armor_page_stays(content, world):
    """打造單子挑到一半時武器被關（內容改版、管理者改設定）、防具還開著：鐵匠鋪照開（只剩防具頁），單子要清掉——
    _smith_options 先看單子、後看停在哪一頁，不清的話畫出來的還是灰掉的兵器單子、沒有切頁鈕，只能按「不打了」。"""
    from tianxia import smithing
    from tianxia.state import SmithDraft
    game = _town(content, world, weapons_on=True)
    p = game.state.player
    game.choose("act:smith")
    p.smith_draft = SmithDraft(kind="劍")  # 單子挑到一半
    content.config.weapons.enabled = False
    game.sync(1.0)
    assert p.picking_smith and p.smith_draft is None
    ids = list(_ids(game))
    assert ids[:4] == [f"{armor.BUY}{a}" for a in armor.SHOP_ATTRIBUTES] and ids[-1] == "smith:back"
    assert not any(i.startswith((smithing.KIND, smithing.MAIN, "smith:page:")) for i in ids)  # 兵器的單子清掉了
    assert _ids(game)[smithing.OPEN].label.startswith("打造防具…")
    p.smith_draft = SmithDraft(kind="劍")
    game._drop_stale_references()  # 存檔修補也清
    assert p.picking_smith and p.smith_draft is None


def test_the_armor_page_only_sees_armor_in_a_rack_with_all_four_slots(content, world):
    """裝備四欄 3.3（Review Focus 3 的防具那一側）：裝備庫裡混了武器、坐騎、寶物，防具那幾個函式與鐵匠鋪防具頁只看到防具；
    坐騎、寶物（之後的批次）與武器不列、不能換、不能拆，格數照算。"""
    game = _town(content, world)  # 只開防具；靜心訣（虛）
    s, p = game.state, game.state.player
    ng = _neigong(game, content, world)
    p.rack = [
        _blade(),
        Equipment(id="騎:4", slot="mount", name="棗騮馬", tier=3, quality="上品"),
        Equipment(id="寶:5", slot="treasure", name="烏木名刺", tier=3, quality="上品"),
        _jacket(aid="甲:2", attribute="柔"),
    ]
    assert [r["id"] for r in armor.rows(s, content, ng)["rack"]] == ["甲:2"]
    for item_id in ("兵:3", "騎:4", "寶:5"):
        assert armor.wield(s, content, item_id) == [equipment.WIELD_MISSING]
        assert armor.dismantle(s, content, item_id) == [equipment.DISMANTLE_MISSING]
    assert armor.wanted(s, content, ng) == "smith:wield:甲:2"  # 柔不剋虛：6%，比身上空著好；坐騎、寶物不在候選裡
    game.choose("act:smith")
    picked = [i for i in _ids(game) if i.startswith(("smith:wield:", "smith:dismantle:"))]
    assert picked == ["smith:wield:甲:2", "smith:dismantle:甲:2"]
    assert game.choose("smith:wield:騎:4") == ["（此刻無法這麼做。）"]  # 不在選單上
    assert p.armor is None and len(p.rack) == 4 and p.materials == {}
    content.config.weapons.rack_cap = 4
    p.armor = _jacket(aid="甲:9")
    assert armor.rack_full(s, content)  # 格數四欄合算


# ── PM：白淬白修 ──

def _repairable(content, world, kind, *, art="sword"):
    """站在鐵匠鋪、手上一把鈍了的兵器（劍或別種）、背包有一階素材、銀兩夠：修與淬煉都按得下去。art 是身上的武學（None：空著）。"""
    game = _town(content, world, weapons_on=True)
    p = game.state.player
    if art is not None:
        rules.learn_skill(game.state, content, art)
        p.member.wugong_id = art
    p.weapon = Weapon(id="兵:1", name="試刃", kind=kind, attribute="柔", tier=1, quality="下品", edge=40)
    p.materials = {"gang_1": 3}
    game.choose("act:smith")
    return game


@pytest.mark.parametrize("kind,art", [("刀", "sword"), ("劍", None)])  # 配不上（種類不同）、身上沒有武學
def test_repair_and_temper_warn_when_the_worn_weapon_does_not_fit(content, world, kind, art):
    from tianxia import smithing
    game = _repairable(content, world, kind, art=art)
    opts = _ids(game)
    for oid in ("smith:repair", smithing.TEMPER):
        assert opts[oid].enabled and opts[oid].label.endswith(weapons.UNFIT_NOTE)  # 按得下去，只多一句提醒
    game.choose("smith:repair")  # 照樣修得動：id 沒變、也沒擋
    assert game.state.player.weapon.edge == 100 and game.state.player.materials == {"gang_1": 2}


def test_repair_and_temper_say_nothing_extra_when_the_weapon_fits_or_the_button_is_off(content, world):
    from tianxia import smithing
    game = _repairable(content, world, "劍")  # 流雲劍配劍
    opts = _ids(game)
    assert weapons.UNFIT_NOTE not in opts["smith:repair"].label and weapons.UNFIT_NOTE not in opts[smithing.TEMPER].label
    assert opts["smith:repair"].label == "修【試刃】（鋒利度 40・精鐵砂×1＋5 兩）"  # 配得上：原樣
    # 配不上、可是灰掉的鈕不再添一句：修滿的不用修、沒料修不了、淬滿了
    p = game.state.player
    p.member.wugong_id = None
    p.weapon.edge, p.weapon.tempers, p.materials = 100, content.config.weapons.temper_max, {}
    opts = _ids(game)
    assert not opts["smith:repair"].enabled and weapons.UNFIT_NOTE not in opts["smith:repair"].label
    assert not opts[smithing.TEMPER].enabled and smithing.FULL in opts[smithing.TEMPER].label and weapons.UNFIT_NOTE not in opts[smithing.TEMPER].label
    p.weapon.tempers = 0
    opts = _ids(game)
    assert not opts[smithing.TEMPER].enabled and weapons.UNFIT_NOTE not in opts[smithing.TEMPER].label


# ── Task 5：修練頁「裝備」與角色卡 ──

def test_gear_rows_list_each_open_slot_and_count_the_whole_rack(content, world):
    from tianxia import skillview
    _on(content, weapons_on=True)
    game = _game(content, world)
    p = game.state.player
    p.armor = _jacket()
    p.rack = [_jacket(aid="甲:2", name="鐵葉甲", attribute="剛"), _blade()]
    gear = skillview.gear_rows(game.state, content, world)
    assert gear["cap"] == 100 and gear["used"] == 2
    assert [g["slot"] for g in gear["slots"]] == ["weapon", "armor"] and [g["label"] for g in gear["slots"]] == ["武器", "防具"]
    weapon_slot, armor_slot = gear["slots"]
    assert weapon_slot["worn"] is None and [r["id"] for r in weapon_slot["rack"]] == ["兵:3"]
    assert armor_slot["worn"]["id"] == "甲:1" and [r["id"] for r in armor_slot["rack"]] == ["甲:2"]
    assert weapon_slot["empty"] == weapons.EMPTY and armor_slot["empty"] == armor.EMPTY and armor_slot["note"] == armor.RACK_NOTE
    content.config.weapons.enabled = False
    gear = skillview.gear_rows(game.state, content, world)
    assert [g["slot"] for g in gear["slots"]] == ["armor"] and gear["used"] == 2  # 關著的欄位不列，東西照樣佔格子


def test_player_card_has_the_armor_line_under_the_weapon_line(content, world):
    from tianxia import skillview
    _on(content, weapons_on=True)
    game = _game(content, world)
    p = game.state.player
    assert "防具" not in skillview.member_card(game.state, content, world, "player")
    rules.learn_skill(game.state, content, "sword")
    p.member.wugong_id = "sword"
    p.weapon = Weapon(id="兵:1", name="試刃", kind="劍", attribute="柔", tier=1, quality="下品")
    p.armor = _jacket(edge=80)
    lines = skillview.member_card(game.state, content, world, "player").splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith("兵器"))
    assert lines[at + 1] == "防具　【試甲】屬虛・一階下品・耐久度 80，一場少扣 8% 氣血（跟你的內功同屬性）"


def test_menxia_view_sends_gear_and_the_wield_action_takes_armor(content, world):
    import server
    _on(content)
    game = _game(content, world)
    p = game.state.player
    p.rack = [_jacket(aid="甲:2")]
    view = server.menxia_view(game)
    assert "weapons" not in view and [g["slot"] for g in view["gear"]["slots"]] == ["armor"]
    server.MENXIA_ACTIONS["wield"](game, {"weapon": "甲:2"})  # 網頁照舊送 weapon 這個鍵：防具的 id 也走它
    assert p.armor.id == "甲:2" and server.menxia_view(game)["gear"]["slots"][0]["worn"]["id"] == "甲:2"


# ── Task 6：整季機器人與假人會買、修、換防具 ──

def test_smith_want_does_this_page_first_then_switches(content, world):
    from tianxia import bot
    game = _town(content, world, weapons_on=True)  # 內功是靜心訣（虛）、沒有武學：兵器沒事要做
    p = game.state.player
    assert bot.smith_want(game) == "smith:page:armor"  # 還沒進門：照進門會停的兵器頁算，防具的事在另一頁
    game.choose("act:smith")
    assert bot.smith_want(game) == "smith:page:armor"
    game.choose("smith:page:armor")
    assert bot.smith_want(game) == f"{armor.BUY}剛"
    rules.learn_skill(game.state, content, "sword")
    p.member.wugong_id = "sword"
    assert bot.smith_want(game) == f"{armor.BUY}剛"  # 這一頁還有事：先做完，不來回切
    game.choose(f"{armor.BUY}剛")
    assert bot.smith_want(game) == "smith:page:weapon"  # 防具買好了，兵器那邊要買一把劍


def test_visit_smith_buys_repairs_and_wields_armor_though_the_smith_opens_on_the_weapon_page(content, world):
    from tianxia import bot
    game = _town(content, world, weapons_on=True, inner="basic_breath")  # 粗淺吐納：屬柔
    p = game.state.player
    rules.learn_skill(game.state, content, "sword")
    p.member.wugong_id = "sword"
    bot.visit_smith(game)
    assert p.weapon is not None and p.weapon.kind == "劍" and p.armor is not None and p.armor.attribute == "柔"
    assert not p.picking_smith and p.smith_page == "weapon" and p.stats["silver"] == 120
    p.weapon.tempers = content.config.weapons.temper_max  # 兵器淬滿了：那一個一階素材留給修防具
    p.armor.edge, p.materials = 40, {"gang_1": 1}
    bot.visit_smith(game)
    assert p.armor.edge == 100 and p.materials == {}  # 修得到
    p.rack.append(_jacket(aid="甲:9", attribute="柔", tier=2, name="二階軟甲"))
    bot.visit_smith(game)
    assert p.armor.id == "甲:9" and not p.picking_smith  # 換得上


def test_visit_smith_with_only_armor_on_buys_on_the_armor_page_and_closes_the_door(content, world):
    from tianxia import bot
    game = _town(content, world)  # 只開防具：進門就是防具頁，兵器頁那一段整個跳過
    p = game.state.player
    bot.visit_smith(game)
    assert p.armor is not None and p.armor.attribute == "剛" and p.stats["silver"] == 160 and not p.picking_smith
    before = p.stats["silver"]
    bot.visit_smith(game)  # 身上那件跟架上一樣好、也不鈍：不進門
    assert p.stats["silver"] == before and not p.picking_smith and p.smith_page == "weapon"


def test_a_server_bot_switches_to_the_armor_page_and_buys(content, world):
    from tianxia import bot_policy
    from tianxia.state import BotProfile
    game = _town(content, world, weapons_on=True)
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    assert bot_policy.score(game, _ids(game)["act:smith"], profile) is not None  # 只有防具要買也進門

    def best():
        scored = {o.id: bot_policy.score(game, o, profile) for o in game.options(odds=False) if o.enabled}
        return max(scored, key=lambda k: scored[k] if scored[k] is not None else -1), scored

    game.choose("act:smith")
    assert best()[0] == "smith:page:armor"
    game.choose("smith:page:armor")
    top, scored = best()
    assert top == f"{armor.BUY}剛" and scored["smith:back"] == 0.0 and scored["smith:page:weapon"] is None


def test_a_server_bot_with_only_armor_on_usually_buys_and_never_gets_stuck(content, world):
    from tianxia import bot_policy
    from tianxia.state import BotProfile
    profile = BotProfile(personality="普通", seed=1, faction=None, season_number=1)
    bought = 0
    for seed in range(10):
        game = _town(content, world)
        rng = random.Random(seed)
        game.choose("act:smith")
        for _ in range(6):
            if not game.state.player.picking_smith:
                break
            bot_policy.take_turn(game, profile, rng)
        assert not game.state.player.picking_smith
        bought += game.state.player.armor is not None
    assert bought >= 5


def test_pick_never_presses_a_smith_page_button(content, world):
    from tianxia import bot
    game = _town(content, world, weapons_on=True)
    game.choose("act:smith")
    options = [o for o in game.options(odds=False) if o.enabled]
    assert "smith:page:armor" in {o.id for o in options}
    for seed in range(30):
        assert bot.pick(game, options, random.Random(seed)) != "smith:page:armor"


def test_bots_never_want_to_dismantle_armor(content, world):
    from tianxia import bot, bot_policy
    from tianxia.state import BotProfile
    game = _town(content, world, silver=0)
    game.state.player.rack = [_jacket(aid="甲:5")]
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    game.choose("act:smith")
    assert bot_policy.score(game, _ids(game)["smith:dismantle:甲:5"], profile) is None
    assert not (bot.smith_want(game) or "").startswith("smith:dismantle")
