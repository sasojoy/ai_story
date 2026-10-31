"""寶物與好馬（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第六節、5.7；計畫 docs/superpowers/plans/2026-10-11-裝備-3-寶物與好馬.md）。"""
from __future__ import annotations

import json
import random
from unittest import mock

import pytest

from conftest import idle_step, install_season_one, next_season, real_content
from test_content import copy_fixture, edit_json
from tianxia import equipment, rules, treasures
from tianxia.characters import CharacterStore
from tianxia.content import ContentError, load_content
from tianxia.engine import Game
from tianxia.models import GOOD_HORSE, TREASURE_EFFECTS, Effect, GearBook, GiftDef, SteedDef, TreasureDef
from tianxia.state import BattleRecord, Bounty, Equipment, GameState

NAMES = {"cultivate": "凝神香囊", "insight": "觀山石", "win_xinde_pct": "戰記殘簡", "win_exp_pct": "百戰護符",
         "seclusion": "入定蒲團", "audience": "烏木名刺", "win_material": "拾遺囊", "legend": "叩關玉"}


def _book(content):
    """打開寶物（測試內容四欄都關著），裝上一份寶物表：掉落池八件（id 就是效果鍵），名將贈禮韓鐵（mate）一件寶物、小六（pupil）一匹名駒。"""
    content.config.treasures.enabled = True
    content.gear = GearBook(
        treasures={**{key: TreasureDef(id=key, name=name, effect=key) for key, name in NAMES.items()},
                   "caoxie": TreasureDef(id="caoxie", name="舊草鞋", effect="win_material", pool=False)},
        steeds={"tashuang": SteedDef(id="tashuang", name="踏霜駒")},
        gifts=[GiftDef(character="mate", gear="caoxie"), GiftDef(character="pupil", gear="tashuang")],
    )
    return content


def _item(key, iid="寶:1"):
    """一件寶物（template 就是 _book 寶物表的 id）。"""
    return Equipment(id=iid, slot="treasure", name=NAMES.get(key, key), template=key)


def _game(content, world, name="寶客", at="town"):
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    game.sync(0.0)
    game.state.player.location = at
    return game


GEAR = {  # 測試內容用的 content/gear.json（_gear_root 寫進一份複本）
    "treasures": [{"id": "mingci", "name": "烏木名刺", "effect": "audience"},
                  {"id": "caoxie", "name": "舊草鞋", "effect": "win_material", "pool": False}],
    "steeds": [{"id": "tashuang", "name": "踏霜駒"}],
    "gifts": [{"character": "mate", "gear": "caoxie"}, {"character": "pupil", "gear": "tashuang"}],
}


def _gear_root(tmp_path, edit=None):
    root = copy_fixture(tmp_path)
    data = json.loads(json.dumps(GEAR))
    if edit is not None:
        edit(data)
    (root / "gear.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return root


# ── Task 1：資料形狀、寶物表與寶物那一欄 ──

def test_the_treasure_slot_is_on_by_its_own_switch(content):
    assert not equipment.on(content, "treasure")  # 測試內容關著（設計 2.6）
    content.config.treasures.enabled = True
    slot = equipment.SLOTS["treasure"]
    assert equipment.on(content, "treasure")
    # 寶物不設限制（2.3【定】，企劃者 2026-10-11）：不擋路上（只有坐騎擋）；沒有磨損，所以沒有提醒旗標
    assert (slot.prefix, slot.label, slot.warned, slot.road_locked) == ("寶", "寶物", "", False)
    assert "treasure" not in equipment.DISMANTLABLE  # 寶物不能拆（4.8）


def test_a_treasure_needs_no_tier_or_quality_and_keeps_its_template():
    item = Equipment(id="寶:1", slot="treasure", name="烏木名刺", template="wumu_mingci")
    assert (item.tier, item.quality, item.template) == (0, "", "wumu_mingci")
    assert equipment.grade(item) == ""


def test_store_puts_a_treasure_on_without_a_warning_flag_or_into_the_rack(content, state):
    _book(content)
    item = treasures.new_treasure(state, content, "audience")
    assert (item.id, item.slot, item.name, item.template) == ("寶:1", "treasure", "烏木名刺", "audience")
    assert equipment.store(state, item) == equipment.SLOTS["treasure"].put_on.format(name="烏木名刺")
    assert state.player.treasure is item
    second = treasures.new_treasure(state, content, "win_material")
    assert equipment.store(state, second) == equipment.STORED.format(name="拾遺囊")  # 寶物欄有東西了：進裝備庫
    assert state.player.rack == [second] and second.id == "寶:2"


@pytest.mark.smoke
def test_old_save_from_equipment_batch_two_reads_with_empty_treasure_fields(content, world):
    """裝備四欄 3.2：裝備二的舊存檔（沒有 treasure、treasure_drops、held_gear，裝備沒有 template；季沒有 general_gifts、tianji）
    讀得進來，欄位都是預設值。"""
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    game.state.player.rack = [Equipment(id="騎:1", slot="mount", name="棗騮馬", tier=1, quality="下品")]
    raw = game.state.model_dump(mode="json")
    for key in ("treasure", "treasure_drops", "held_gear"):
        raw["player"].pop(key)
    raw["player"]["rack"][0].pop("template")
    raw["world"] = game.state.world.model_dump(mode="json")  # GameState 的 world 是 exclude 的；舊存檔裡夾帶的 world 讀得進來、隨即被取代
    for key in ("general_gifts", "tianji"):
        raw["world"].pop(key)
    loaded = GameState.model_validate(raw)
    p = loaded.player
    assert p.treasure is None and p.treasure_drops == set() and p.held_gear == []
    assert p.rack[0].template is None and loaded.world.general_gifts == {} and loaded.world.tianji == 0
    old = Bounty.model_validate({"id": "b1", "kind": "strike", "faction": "guan", "week": 1, "expires": 1.0, "silver": 20, "deeds": 3})
    assert old.prize is None


def test_a_new_season_clears_the_treasure_fields(content, world):
    _book(content)
    game = _game(content, world)
    p = game.state.player
    p.treasure, p.rack, p.held_gear = _item("audience"), [_item("win_material", "寶:2")], [_item("legend", "寶:3")]
    p.treasure_drops = {"bocai"}
    game.state.world.general_gifts = {"mate": "寶客"}
    next_season(content, world, game)
    p = game.state.player
    assert p.treasure is None and p.rack == [] and p.held_gear == [] and p.treasure_drops == set()
    assert game.state.world.general_gifts == {}  # 全服的贈禮名單跟著新的一季重來（2.4、第八節）


def test_the_gear_table_loads_from_gear_json(tmp_path):
    c = load_content(_gear_root(tmp_path))
    assert c.gear.treasures["mingci"].effect == "audience" and c.gear.treasures["caoxie"].pool is False
    assert c.gear.steeds["tashuang"].quality == "上品" and [g.character for g in c.gear.gifts] == ["mate", "pupil"]


def test_no_gear_json_means_an_empty_table(content):
    assert content.gear == GearBook()


@pytest.mark.parametrize(("edit", "match"), [
    (lambda d: d["treasures"][0].update(name="韓鐵"), "命名過濾"),  # 跟人物同名
    (lambda d: d["treasures"][0].update(effect="power"), "effect"),  # 不是八種之一
    (lambda d: d["gifts"][0].update(character="ghost"), "ghost"),
    (lambda d: d["gifts"][1].update(gear="mingci"), "贈禮"),  # 掉落池的寶物不能當贈禮
    (lambda d: d["gifts"].append({"character": "mate", "gear": "tashuang"}), "兩次"),
    (lambda d: d["treasures"][0].update(pool=False), "掉落池"),  # 掉落池一件都沒有
    (lambda d: d["steeds"].append({"id": "good_horse", "name": "雪蹄駒"}), "good_horse"),
    (lambda d: d["gifts"][0].update(line="{who}送你【{gift}】"), "general"),
    (lambda d: d.update(armor=[]), "gear.json"),
])
def test_bad_gear_tables_are_rejected(tmp_path, edit, match):
    with pytest.raises(ContentError, match=match):
        load_content(_gear_root(tmp_path, edit))


def test_the_real_gear_table_has_eight_pool_treasures_and_seven_gifts():
    c = real_content()
    pool = [t for t in c.gear.treasures.values() if t.pool]
    assert len(pool) == 8 and {t.effect for t in pool} == set(TREASURE_EFFECTS)
    assert {g.character for g in c.gear.gifts} == {"caocao", "sunjian", "liubei", "guanyu", "zhangfei", "yuanshao", "taoqian"}
    assert sorted(c.gear.steeds[g.gear].name for g in c.gear.gifts if g.gear in c.gear.steeds) == ["破浪駒", "踏霜駒"]


def test_effect_of_reads_the_template_and_names_follow_the_content(content, state):
    _book(content)
    p = state.player
    p.treasure = _item("audience")
    p.treasure.name = "舊名"
    assert treasures.effect_of(content, p.treasure) == "audience"
    assert treasures.effect_of(content, Equipment(id="兵:1", name="試刃", template="audience")) is None  # 不是寶物那一欄
    treasures.refresh_names(p, content)
    assert p.treasure.name == "烏木名刺"
    p.treasure.template = "gone"  # 內容拿掉了這一件：名字留著當備份、沒有效果
    treasures.refresh_names(p, content)
    assert p.treasure.name == "烏木名刺" and treasures.effect_of(content, p.treasure) is None
    assert "3" in treasures.effect_text(content, "audience") and "20%" in treasures.effect_text(content, "win_xinde_pct")
    assert "25%" in treasures.effect_text(content, "win_material")
    assert "×2" in treasures.effect_text(content, "legend") and content.config.legend_item_name in treasures.effect_text(content, "legend")


def test_loading_a_save_refreshes_treasure_and_steed_names(content, world):
    """設計 3.1：寶物與名駒的名字照 template 從內容讀（joy 改名不動存檔）——每次建 Game 都照內容重寫一次 name。"""
    _book(content)
    content.config.mounts.enabled = True
    game = _game(content, world)
    p = game.state.player
    p.treasure = _item("audience")
    p.treasure.name = "舊名"
    p.held_gear = [Equipment(id="騎:2", slot="mount", name="舊駒", tier=3, quality="上品", template="tashuang")]
    CharacterStore(world.db).save(game.state)
    loaded = Game(content, CharacterStore(world.db).load("寶客"), random.Random(0), world)
    assert loaded.state.player.treasure.name == "烏木名刺" and loaded.state.player.held_gear[0].name == "踏霜駒"
    assert treasures.owned_templates(loaded.state.player) == {"audience", "tashuang"}


# ── Task 2：八個掛點 ──

def _record(kind="event"):
    return BattleRecord(id=1, time=0.0, location="湖邊", kind=kind, opponent="誰", ours=[], tier="大勝", our_power=1.0, difficulty=1.0)


def test_amount_is_neutral_unless_worn_and_switched_on(content, state):
    _book(content)
    assert treasures.amount(state, content, "cultivate") == 1.0 and treasures.amount(state, content, "audience") == 0.0
    state.player.treasure = _item("audience")
    assert treasures.amount(state, content, "audience") == 3 and treasures.amount(state, content, "cultivate") == 1.0
    content.config.treasures.enabled = False  # 開關關著：帶著也當沒帶
    assert treasures.amount(state, content, "audience") == 0.0
    content.config.treasures.enabled = True
    state.player.treasure.template = "gone"  # 內容拿掉了這一件
    assert treasures.amount(state, content, "audience") == 0.0
    state.player.treasure = None
    state.player.rack = [_item("audience")]  # 放在裝備庫裡的不算
    assert treasures.amount(state, content, "audience") == 0.0


def test_cultivate_treasure_now_multiplies_the_last_step(content, state, world):
    """武學重構：衝品拿掉了，寶物「cultivate」改乘絕學這一步——服丹衝關（force_odds）照 ×1.2（夾 max_chance 之前）。"""
    from tianxia import cultivation
    _book(content)
    content.config.legend_item_bonus = 20  # 照悟性 5 是 20%，乘 1.2 是 24%，不碰 max_chance
    forcing = cultivation.force_odds(state, content, world, "nope")
    state.player.treasure = _item("cultivate")
    assert treasures.amount(state, content, "cultivate") == 1.2
    assert cultivation.force_odds(state, content, world, "nope") == round(forcing * 1.2)


def test_insight_treasure_weighs_only_the_insight_branch(content, world):
    _book(content)
    game = _game(content, world)
    loc = content.locations["lake"]
    with mock.patch.object(Game, "_explore_can", lambda self, branch, place: True):
        plain = dict(game._explore_weights(loc))
        game.state.player.treasure = _item("insight")
        worn = dict(game._explore_weights(loc))
    assert worn["insight"] == pytest.approx(plain["insight"] * 1.5)
    assert {k: v for k, v in worn.items() if k != "insight"} == {k: v for k, v in plain.items() if k != "insight"}


def test_win_treasures_add_to_the_streak_bonus_on_train_wild_challenge_and_story_wins(content, world):
    """設計 6.2：打贏的心得、經驗掛在 _battle_rewards，跟乘勝相加不疊乘。遊歷（train）、探索野怪（wild）、挑戰本人與劇情戰
    （都是 kind=event）打贏都走 _battle_rewards，都吃（設計沒有排除，跟乘勝、遊俠名號的經驗加成同一個範圍）。"""
    from tianxia import traits
    _book(content)
    game = _game(content, world)
    squad = content.squads["thug"].model_copy(update={"reward_silver": 0, "reward_xinde": 10, "exp": 20})

    def won(kind="event"):
        record = _record(kind)
        game._battle_rewards(squad, record)
        return record.xinde, record.exp

    assert won() == (10, 20)
    game.state.player.treasure = _item("win_xinde_pct")
    assert [won(kind) for kind in ("train", "wild", "event")] == [(12, 20)] * 3
    game.state.player.treasure = _item("win_exp_pct")
    assert [won(kind) for kind in ("train", "wild", "event")] == [(10, 23)] * 3  # round(20 × 1.15)
    game.state.player.treasure = _item("win_xinde_pct")
    with mock.patch.object(traits, "amount", lambda content_, lo, hook: 0.5 if hook == "win_reward" else 0.0):
        assert won()[0] == 12  # 乘勝換成回合裡的戰法（本命戰法第三批），不再多給打贏的心得：只有寶物 +20%


def test_seclusion_treasure_adds_a_quarter_to_the_xinde(content, world):
    """設計 6.2：閉關心得照出關那一刻身上那件算（寶物隨時能換；閉關中換上也算，Task 4 另驗）。"""
    _book(content)
    game = _game(content, world)
    p = game.state.player
    base = 4 * content.config.seclusion_xinde_per_hour * (1 + p.stats["wis"] / 20)

    def secluded():
        p.seclusion_start, p.busy_until = 0.0, 4 * 3600.0
        before = p.stats.get("xinde", 0)
        game._finish_seclusion(4 * 3600.0)
        return p.stats["xinde"] - before

    assert secluded() == round(base)
    p.treasure = _item("seclusion")
    assert secluded() == round(base * 1.25)


def test_audience_treasure_lowers_the_bar_but_not_below_zero(content, state):
    _book(content)
    content.characters["mate"].audience_fame = 10
    assert rules.audience_bar(state, content, "mate") == 10
    state.player.treasure = _item("audience")
    assert rules.audience_bar(state, content, "mate") == 7
    content.characters["mate"].audience_fame = 2
    assert rules.audience_bar(state, content, "mate") == 0


def test_win_material_treasure_adds_one_more_only_on_train_and_wild_wins_that_dropped(content, world):
    """設計 6.2：打贏、這一場掉了素材時多掉一個——只有遊歷（train）、探索野怪（wild）；挑戰本人與劇情戰（kind=event，也走
    _battle_rewards）不吃，沒掉素材不擲（序章本來就不掉素材）。多的那一個是這一場掉到的那一種（要 PM 定的第 3 條），寫進戰報的得失；
    用自己的亂數，Game.rng 跟沒帶時一模一樣（FB-129）。"""
    from tianxia.models import Drop
    _book(content)
    content.config.treasures.effects["win_material"] = 1.0  # 一定中：這一支只驗掛點與範圍（25% 的擲法另一支驗）
    game = _game(content, world)
    p = game.state.player
    dropping = content.squads["thug"].model_copy(update={"reward_silver": 0, "drops": [Drop(material="gang_1")]})
    barren = dropping.model_copy(update={"drops": [Drop(material="gang_1", chance=0.0)]})

    def won(kind, squad, worn):
        p.treasure = _item("win_material") if worn else None
        game.rng = random.Random(5)
        before = p.materials.get("gang_1", 0)
        record = _record(kind)
        game._battle_rewards(squad, record)
        return p.materials.get("gang_1", 0) - before, record.materials, game.rng.getstate()

    for kind in ("train", "wild"):
        plain, worn = won(kind, dropping, False), won(kind, dropping, True)
        # 多一個；戰報的得失跟掉到的那一種合成一格、寫是寶物多給的（FB-140）
        assert (plain[0], worn[0], plain[1], worn[1]) == (1, 2, ["精鐵砂 ×1"], [f"精鐵砂 ×2（{p.treasure.name} +1）"])
        assert worn[2] == plain[2]  # Game.rng 一顆都沒多吃
    assert won("event", dropping, True)[0] == 1  # 挑戰本人、劇情戰不吃
    assert won("train", barren, True)[0] == 0  # 這一場沒掉素材：不擲、不給


def test_the_extra_material_rolls_a_quarter_on_season_name_and_record(content, state):
    """多掉的那一個用自己一份亂數（寶|素材|季數|名號|戰報流水號；戰報流水號每季從 1 算起，所以要有季數），擲 win_material（25%）。"""
    _book(content)
    name = state.player.name
    state.player.treasure = _item("win_material")
    hits = [random.Random(f"寶|素材|3|{name}|{rid}").random() < 0.25 for rid in range(1, 40)]
    got = [treasures.extra_drop(state, content, ["gang_1"], 3, rid) == "gang_1" for rid in range(1, 40)]
    assert got == hits and any(hits) and not all(hits)
    assert treasures.extra_drop(state, content, [], 3, 1) is None  # 這一場沒掉素材
    state.player.treasure = None
    assert all(treasures.extra_drop(state, content, ["gang_1"], 3, rid) is None for rid in range(1, 40))  # 沒帶


def test_legend_treasure_doubles_the_pill_chance_on_the_same_die(content, world):
    """設計 6.2：探索撿破境丹的門檻 ×2（夾在 1 以下），擲的還是同一顆 self.rng.random()：帶不帶都只擲一次，亂數序列不位移；
    基本機率是 0（測試內容）時照舊不擲。"""
    _book(content)
    game = _game(content, world)
    roll = random.Random(7).random()
    content.config.explore_legend_chance = roll * 0.75  # 沒帶：roll ≥ 門檻、撿不到；帶了：門檻 1.5×roll > roll、撿到

    def found():
        game.rng = random.Random(7)
        got = game._legend_find()
        return bool(got), game.rng.getstate()

    plain, plain_dice = found()
    game.state.player.treasure = _item("legend")
    worn, worn_dice = found()
    assert not plain and worn and plain_dice == worn_dice
    content.config.explore_legend_chance = 0.0
    game.rng = random.Random(7)
    dice = game.rng.getstate()
    assert game._legend_find() == [] and game.rng.getstate() == dice  # 基本機率 0：帶著也不擲


# ── Task 3：拿到的共用路與奇遇 ──

def test_a_new_thing_goes_on_an_empty_slot_or_into_the_rack(content, state):
    _book(content)
    p = state.player
    assert treasures.deliver(state, content, _item("audience")) == [equipment.SLOTS["treasure"].put_on.format(name="烏木名刺")]
    assert p.treasure.template == "audience"
    assert treasures.deliver(state, content, _item("win_material", "寶:2")) == [equipment.STORED.format(name="拾遺囊")]
    assert [i.id for i in p.rack] == ["寶:2"]


def test_a_full_rack_holds_what_may_wait_and_says_what_is_lost(content, state):
    _book(content)
    content.config.weapons.rack_cap = 1
    p = state.player
    p.treasure, p.rack = _item("audience"), [_item("win_material", "寶:2")]
    assert treasures.deliver(state, content, _item("legend", "寶:3"), hold=True) == [treasures.HELD.format(name="叩關玉")]
    assert [i.id for i in p.held_gear] == ["寶:3"]
    assert treasures.deliver(state, content, _item("insight", "寶:4")) == [treasures.NO_ROOM.format(name="觀山石")]
    assert len(p.rack) == 1 and len(p.held_gear) == 1


def test_a_treasure_got_in_seclusion_goes_on_an_empty_slot_like_any_other(content, world):
    """設計 2.2（企劃者 2026-10-11）：閉關中拿到寶物照一般的規則——寶物欄空著就直接穿上（原本「先放裝備庫」的例外拿掉了：
    寶物閉關中本來就能換，閉關心得照出關那一刻身上那件算）。"""
    _book(content)
    game = _game(content, world)
    p = game.state.player
    p.busy_until = game.state.world.time + 3600.0
    assert treasures.deliver(game.state, content, _item("seclusion")) == [equipment.SLOTS["treasure"].put_on.format(name="入定蒲團")]
    assert p.treasure.id == "寶:1" and p.rack == []


def test_held_gear_arrives_on_sync_and_advance_when_there_is_room(content, world):
    """設計 6.5、3.2：同步時裝備庫有空位就補，一次補到裝備庫滿為止，補不完的留著；閉關中照補（要 PM 定的第 4 條：寶物閉關中本來
    就能換，「閉關中不補」要擋的東西已經不在了）。整季機器人只 advance、不 sync，所以快轉（advance）也補。"""
    _book(content)
    game = _game(content, world)
    p = game.state.player
    p.treasure, p.rack = _item("audience"), [_item("win_material", "寶:2")]
    p.held_gear = [_item("legend", "寶:3"), _item("insight", "寶:4"), _item("cultivate", "寶:5")]
    content.config.weapons.rack_cap = 2
    p.busy_until = game.state.world.time + 3600.0  # 閉關中照補
    game.sync(1.0)
    assert [i.id for i in p.rack] == ["寶:2", "寶:3"] and [i.id for i in p.held_gear] == ["寶:4", "寶:5"]  # 補到滿為止，補不完的留著
    assert game.state.journal[0].title == treasures.HELD_TITLE
    content.config.weapons.rack_cap = 3
    p.busy_until = None
    game.advance(60.0)
    assert [i.id for i in p.rack] == ["寶:2", "寶:3", "寶:4"] and [i.id for i in p.held_gear] == ["寶:5"]


def test_an_event_gives_a_pool_treasure_and_the_same_one_again_turns_into_silver(content, state, world):
    _book(content)
    p = state.player
    silver = p.stats["silver"]
    msgs = rules.apply_effect(Effect(gear="audience"), state, content, world)
    assert p.treasure.template == "audience"
    assert treasures.GOT.format(name="烏木名刺", effect=treasures.effect_text(content, "audience")) in msgs
    msgs = rules.apply_effect(Effect(gear="audience"), state, content, world)  # 設計 6.5：手上有同一件改給 50 兩
    dup = content.config.treasures.dup_silver
    assert treasures.DUP.format(name="烏木名刺", silver=dup) in msgs and f"銀兩 +{dup}" in msgs
    assert p.stats["silver"] == silver + dup and p.rack == []


def test_an_event_horse_is_a_good_horse_every_time_on_its_own_seed(content, state, world):
    from tianxia import mounts
    _book(content)
    content.config.mounts.enabled = True
    p = state.player
    rng = random.Random(f"奇遇|{world.get_season_number()}|{p.name}|{GOOD_HORSE}|{p.weapon_serial}")
    coat = rng.choice(mounts.COATS)
    table = content.config.treasures.horse_quality
    quality = rng.choices(list(table), weights=list(table.values()))[0]
    rules.apply_effect(Effect(gear=GOOD_HORSE), state, content, world)
    assert (p.mount.tier, p.mount.name, p.mount.quality) == (2, mounts.horse_name(coat, 2), quality)
    rules.apply_effect(Effect(gear=GOOD_HORSE), state, content, world)
    assert len(equipment.in_slot(p, "mount")) == 1  # 良駒不是一人一件：第二匹照給、進裝備庫


def test_event_gear_does_nothing_with_the_slot_off_and_is_lost_when_full(content, state, world):
    _book(content)
    content.config.treasures.enabled = False
    assert rules.apply_effect(Effect(gear="audience"), state, content, world) == [] and state.player.treasure is None
    content.config.treasures.enabled = True
    content.config.weapons.rack_cap = 0
    state.player.treasure = _item("win_material", "寶:9")
    serial = state.player.weapon_serial
    assert rules.apply_effect(Effect(gear="audience"), state, content, world) == [treasures.NO_ROOM.format(name="烏木名刺")]
    assert state.player.weapon_serial == serial and state.player.held_gear == []  # 奇遇當下拿不了就沒了（6.5），也不佔流水號


def _give_gear(gear, once=True):
    """測試內容的事件 drunk（可以重複遇到）第二個選項寫 gear；once 把它標成一次性的事件。"""
    def edit(d):
        d[0]["choices"][1]["effect"]["gear"] = gear
        if once:
            d[0]["once"] = True
    return edit


@pytest.mark.parametrize(("gear", "ok"), [("mingci", True), (GOOD_HORSE, True), ("caoxie", False), ("tashuang", False), ("ghost", False)])
def test_events_may_give_pool_treasures_or_a_good_horse_only(tmp_path, gear, ok):
    root = _gear_root(tmp_path)
    edit_json(root / "events" / "test.json", _give_gear(gear))
    if ok:
        assert load_content(root).events["drunk"].choices[1].effect.gear == gear
    else:
        with pytest.raises(ContentError, match="gear"):
            load_content(root)


def test_only_one_time_events_may_give_gear(tmp_path):
    """可以重複遇到的事件寫 gear，等於每遇一次送一件、或每遇一次換 50 兩（涿郡「馬市試騎」就是這種）：載入時擋，只准 once 的事件
    （要 PM 定的第 5 條；沒標 once 的奇遇看過也照樣留著，所以只看 qiyu 不夠）。"""
    root = _gear_root(tmp_path)
    edit_json(root / "events" / "test.json", _give_gear("mingci", once=False))
    with pytest.raises(ContentError, match="once"):
        load_content(root)


def test_gear_on_a_once_event_chained_from_a_repeatable_one_is_refused(tmp_path):
    """裝備三終審：串接（next_event）不看 once——Game._present 照樣叫出看過的事件，所以從可以重複遇到的事件串得到的一次性事件
    寫了 gear，一樣每遇一次送一件；載入時擋（隔一層也擋）。"""
    def chained(depth):
        def edit(d):
            _give_gear("mingci")(d)  # drunk：一次性、寫了 gear
            hops = [e for e in d[1:] if not e.get("once")][:depth]
            for here, there in zip(hops, hops[1:]):
                there["once"] = True  # 中間那一層是一次性的事件，照樣被串得到
                here["choices"][0].setdefault("effect", {})["next_event"] = there["id"]
            hops[-1]["choices"][0].setdefault("effect", {})["next_event"] = "drunk"
        return edit

    for depth in (1, 2):
        root = _gear_root(tmp_path / str(depth))
        edit_json(root / "events" / "test.json", chained(depth))
        with pytest.raises(ContentError, match="next_event"):
            load_content(root)


def test_free_text_and_road_sights_cannot_give_gear(tmp_path):
    root = _gear_root(tmp_path / "a")
    edit_json(root / "events" / "test.json",
              lambda d: d[0].update(free_text={"prompt": "自己想辦法", "stat": "str", "effect": {"gear": "mingci"}}))
    with pytest.raises(ContentError, match="隨口應對.*gear"):
        load_content(root)
    root = _gear_root(tmp_path / "b")
    edit_json(root / "road_sights.json", lambda d: d[0].setdefault("effect", {}).update(gear="mingci"))
    with pytest.raises(ContentError, match="小收穫只能用"):
        load_content(root)


# ── Task 4：換上寶物、修練頁、角色卡 ──

def test_a_treasure_can_be_swapped_any_time_even_in_seclusion(content, world):
    """設計 2.3【定】（企劃者 2026-10-11「不需要限制隨時可以換」）：同一個遊戲日可以連換、閉關中也能換；閉關心得照出關那一刻
    身上那件算——閉關到一半換上閉關的寶物也拿得到 +25%。寶物不能拆（4.8）。"""
    _book(content)
    game = _game(content, world)
    p = game.state.player
    p.rack = [_item("audience", "寶:1"), _item("seclusion", "寶:2")]
    assert game.wield_weapon("寶:1") == [equipment.WIELDED.format(name="烏木名刺")] and p.treasure.id == "寶:1"
    assert game.wield_weapon("寶:2") == [equipment.WIELDED.format(name="入定蒲團")] and [t.id for t in p.rack] == ["寶:1"]  # 同一天連換
    assert game.wield_weapon("寶:1") == [equipment.WIELDED.format(name="烏木名刺")] and [t.id for t in p.rack] == ["寶:2"]
    base = 4 * content.config.seclusion_xinde_per_hour * (1 + p.stats["wis"] / 20)
    p.seclusion_start, p.busy_until = 0.0, 4 * 3600.0  # 閉關中
    assert game.wield_weapon("寶:2") == [equipment.WIELDED.format(name="入定蒲團")]  # 閉關中照樣換得上
    before = p.stats.get("xinde", 0)
    game._finish_seclusion(4 * 3600.0)
    assert p.stats["xinde"] - before == round(base * 1.25)  # 照出關那一刻身上那件
    # 寶物不能拆（4.8）：DISMANTLABLE 只有武器、防具，寶物一開頭就濾掉。測試內容武器、防具關著，回的是 NOT_NOW（開著時是
    # DISMANTLE_MISSING），所以不鎖哪一句，只鎖「沒拆、還在裝備庫」
    assert not game.dismantle_weapon("寶:1")[0].startswith(equipment.DISMANTLE_PREFIX) and [t.id for t in p.rack] == ["寶:1"]


def test_gear_rows_have_a_treasure_slot_with_effects(content, world):
    from tianxia import skillview
    _book(content)
    game = _game(content, world)
    p = game.state.player
    p.treasure, p.rack = _item("audience", "寶:1"), [_item("win_material", "寶:2")]
    gear = skillview.gear_rows(game.state, content, world)
    [slot] = gear["slots"]  # 測試內容其他三欄關著：只有寶物那一段
    assert (slot["slot"], slot["label"], slot["empty"], slot["note"]) == ("treasure", "寶物", treasures.EMPTY, treasures.RACK_NOTE)
    assert slot["worn"]["effect_text"] == treasures.effect_text(content, "audience")
    assert [(r["id"], r["effect"]) for r in slot["rack"]] == [("寶:2", "win_material")]
    assert set(slot["rack"][0]) == {"id", "name", "effect", "effect_text", "might"}  # 沒有「能不能換」的旗標：寶物隨時能換（2.3）；might 是換上後的戰力
    assert gear["held_note"] == ""
    p.held_gear = [_item("seclusion", "寶:3")]
    assert "【入定蒲團】" in skillview.gear_rows(game.state, content, world)["held_note"]
    content.config.treasures.enabled = False
    assert skillview.gear_rows(game.state, content, world)["slots"] == []


def test_player_card_has_the_treasure_line(content, world):
    from tianxia import skillview
    _book(content)
    game = _game(content, world)
    assert "寶物" not in skillview.member_card(game.state, content, world, "player")
    game.state.player.treasure = _item("audience")
    line = treasures.card_line(game.state, content)  # 整行待 joy 潤：只鎖名字與效果
    assert "【烏木名刺】" in line and treasures.effect_text(content, "audience") in line
    assert line in skillview.member_card(game.state, content, world, "player").splitlines()


def test_the_practice_page_wield_action_puts_a_treasure_on(content, world):
    import server
    _book(content)
    game = _game(content, world)
    game.state.player.rack = [_item("audience", "寶:1")]
    server.MENXIA_ACTIONS["wield"](game, {"weapon": "寶:1"})
    assert game.state.player.treasure.id == "寶:1"
    assert server.menxia_view(game)["gear"]["slots"][0]["worn"]["name"] == "烏木名刺"


# ── Task 5：懸賞的重賞 ──

from test_bounties import _direct, _do, _post, _seat  # noqa: E402  懸賞的測試共用同一套開角色、照伺服器的做法存讀


@pytest.fixture
def board(content, world):
    """第一季（install_season_one）：官軍的甲、散人丙、散人丁；寶物照 _book、坐騎開著（同 test_bounties.setup 的開法）。"""
    from tianxia.models import FactionDef
    install_season_one(content)
    content.scenario.factions = [FactionDef(id="guan", name="官軍", join_at=["town"]), FactionDef(id="huang", name="黃巾", join_at=["lake"])]
    _book(content)
    content.config.mounts.enabled = True
    return _seat(content, world, (("甲", "guan"), ("丙", None), ("丁", None)))


def _strike(world, prize):
    return _post(world, kind="strike", faction="guan", silver=20, deeds=3, location="lake", squad="thug", quota=3, prize=prize)


def test_each_season_carries_its_tianji_for_the_weekly_dice(content, world):
    game = _game(content, world)
    assert world.get_season().tianji == world.read().tianji == 0
    next_season(content, world, game)
    assert world.read().tianji == 1 and world.get_season().tianji == 1 and game.state.world.tianji == 1


def test_issue_hangs_prizes_on_the_first_two_strikes_of_each_side_without_moving_the_board():
    from tianxia import bounties
    from tianxia.state import WorldState
    content = real_content("week7")

    def posted(treasure, horse):
        content.config.treasures.bounty_treasure_chance, content.config.treasures.bounty_horse_chance = treasure, horse
        state = GameState(player=Game.new(content, "測", rng=random.Random(0)).state.player, world=WorldState(season_one=True, tianji=4))
        bounties.issue(state, content, 1)
        return state.world.bounties

    plain, prized = posted(0.0, 0.0), posted(1.0, 1.0)
    assert [(b.id, b.kind, b.location, b.end) for b in plain] == [(b.id, b.kind, b.location, b.end) for b in prized]  # 另一份亂數：單子一張都不變
    assert all(b.prize is None for b in plain) and all(b.prize is None for b in prized if b.kind != "strike")
    for faction in ("guan", "huang"):
        strikes = [b.prize for b in prized if b.faction == faction and b.kind == "strike"]
        assert strikes[:2] == ["treasure", "horse"] and all(prize is None for prize in strikes[2:])
        only_horse = [b.prize for b in posted(0.0, 1.0) if b.faction == faction and b.kind == "strike"]
        assert only_horse[0] == "horse" and all(prize is None for prize in only_horse[1:])  # 只中一個就掛第一張
    content.config.mounts.enabled = False
    assert not any(b.prize == "horse" for b in posted(1.0, 1.0))  # 坐騎關著不掛良駒


def test_prize_rolls_hang_on_tianji_week_and_side():
    from tianxia import bounties
    content = real_content()
    cfg = content.config.treasures
    rng = random.Random("bounty-prize|4|1|guan")
    assert bounties.prize_rolls(4, 1, "guan", content) == (rng.random() < cfg.bounty_treasure_chance, rng.random() < cfg.bounty_horse_chance)
    assert len({bounties.prize_rolls(t, 1, "guan", content) for t in range(60)}) > 1  # 換一季（天機）結果會變


def test_only_the_first_to_finish_a_prize_strike_gets_the_treasure(board):
    from tianxia import bounties
    content, world = board
    b = _strike(world, "treasure")
    note = treasures.PRIZE_NOTE.format(what=treasures.PRIZE_WORDS["treasure"])
    _, game = _do(content, world, "丙", lambda g: [])
    assert note in bounties.reward_text(game.state, content, game.state.world.bounties[-1])  # 榜上寫「另有重賞：寶物一件」
    for name in ("丙", "丁"):
        _direct(content, world, name, lambda g: bounties.take(g.state, g.content, b.id))
    msgs, game = _direct(content, world, "丙", lambda g: bounties.on_win(g.state, g.content, g.world, "lake", "thug"))
    p = game.state.player
    assert treasures.PRIZE_GOT.format(issuer="官軍") in msgs and p.treasure is not None and content.gear.treasures[p.treasure.template].pool
    assert note not in bounties.reward_text(game.state, content, game.state.world.bounties[-1])  # 給出去了，榜上不再寫
    msgs, game = _direct(content, world, "丁", lambda g: bounties.on_win(g.state, g.content, g.world, "lake", "thug"))
    assert game.state.player.treasure is None and treasures.PRIZE_GOT.format(issuer="官軍") not in msgs
    assert any(m.startswith("【懸賞】") for m in msgs)  # 第二個人照舊拿銀兩經驗


def test_a_prize_with_no_room_waits_in_held_gear_and_arrives_later(board):
    from tianxia import bounties
    content, world = board
    content.config.weapons.rack_cap = 1
    b = _strike(world, "treasure")
    _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, b.id))

    def full_then_win(g):
        p = g.state.player
        p.treasure, p.rack = _item("audience", "寶:90"), [_item("win_material", "寶:91")]
        return bounties.on_win(g.state, g.content, g.world, "lake", "thug")

    msgs, game = _direct(content, world, "丙", full_then_win)
    [held] = game.state.player.held_gear
    assert treasures.HELD.format(name=held.name) in msgs
    assert held.template not in ("audience", "win_material")  # 只抽你還沒有的（6.5）
    content.config.weapons.rack_cap = 2
    _, game = _do(content, world, "丙", lambda g: [])  # 同步時補發
    assert game.state.player.held_gear == [] and held.id in [i.id for i in game.state.player.rack]


def test_a_horse_prize_is_a_good_horse_rolled_on_season_name_and_bounty(board):
    from tianxia import bounties, mounts
    content, world = board
    b = _strike(world, "horse")
    _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, b.id))
    msgs, game = _direct(content, world, "丙", lambda g: bounties.on_win(g.state, g.content, g.world, "lake", "thug"))
    rng = random.Random(f"bounty-prize|{world.get_season_number()}|丙|{b.id}")
    coat = rng.choice(mounts.COATS)
    table = content.config.treasures.horse_quality
    quality = rng.choices(list(table), weights=list(table.values()))[0]
    horse = game.state.player.mount
    assert (horse.tier, horse.name, horse.quality) == (2, mounts.horse_name(coat, 2), quality)
    assert treasures.GOT_HORSE.format(grade=mounts.grade(horse), name=horse.name) in msgs


def test_the_weekly_board_changes_with_tianji_but_not_at_zero():
    """週初掛單原本的兩份亂數（懸賞榜第一批 bounty|…、第二批 bounty-give|…）天機不是 0 時才帶天機：測試與量表（天機 0）的基準不位移。"""
    from tianxia import bounties
    from tianxia.state import WorldState
    content = real_content("week7")

    def posted(tianji):
        state = GameState(player=Game.new(content, "測", rng=random.Random(0)).state.player, world=WorldState(season_one=True, tianji=tianji))
        bounties.issue(state, content, 1)
        return [(b.kind, b.faction, b.location, b.end, b.attribute, b.weapon_kind) for b in state.world.bounties]

    assert posted(0) == posted(0)
    assert any(posted(t) != posted(0) for t in (1, 2, 3))


def test_the_weekly_seeds_are_byte_identical_at_tianji_zero_and_carry_it_after():
    """天機是 0 時兩份週初亂數的種子一字不差（基準不位移）；不是 0 時兩份都在最後接「|天機」。"""
    from tianxia import bounties
    from tianxia.state import WorldState
    content = real_content("week7")

    def seeds(tianji):
        state = GameState(player=Game.new(content, "測", rng=random.Random(0)).state.player, world=WorldState(season_one=True, tianji=tianji))
        seen = []
        real = random.Random
        with mock.patch.object(bounties.random, "Random", side_effect=lambda seed=None: (seen.append(seed), real(seed))[1]):
            bounties.issue(state, content, 1)
        return [s for s in seen if str(s).startswith("bounty|") or str(s).startswith("bounty-give|")]

    zero, three = seeds(0), seeds(3)
    assert len(zero) == len(three) == 2 and all(not s.endswith("|0") for s in zero)
    assert zero[0].startswith("bounty|1|0|") and zero[1].startswith("bounty-give|1|")
    assert [s + "|3" for s in zero] == three


# ── Task 6：名將贈禮 ──

def test_a_general_gives_his_gift_once_a_season_to_the_first_who_gets_close(content, world):
    """設計 6.4：情誼到 gift_affinity（60）時送；每位名將每季全服只送一人（WorldState.general_gifts，動作最後存季）。"""
    _book(content)
    first, second = _game(content, world, "甲客"), _game(content, world, "乙客")
    first.state.player.affinities["mate"] = 60
    msgs = idle_step(first)
    assert first.state.player.treasure.template == "caoxie"
    assert treasures.GIFT_LINE.format(general="韓鐵", gift="舊草鞋") in msgs
    assert world.get_season().general_gifts == {"mate": "甲客"}
    second.sync(1.0)
    second.state.player.affinities["mate"] = 80
    idle_step(second)
    assert second.state.player.treasure is None


def test_affinity_from_an_event_also_brings_the_gift(content, world):
    """情誼從事件（Effect.affinity）來也送（設計 6.4：以前跨門檻只在對話裡偵測）。"""
    _book(content)
    game = _game(content, world)
    content.events["drunk"].choices[1].effect.affinity = {"mate": 1}
    game.state.player.affinities["mate"] = 59
    game.state.pending_event = "drunk"
    game.choose("choice:1")
    assert game.state.player.treasure.template == "caoxie"


def test_a_steed_gift_waits_while_mounts_are_off(content, world):
    _book(content)
    game = _game(content, world)
    game.state.player.affinities["pupil"] = 60
    idle_step(game)
    assert game.state.player.mount is None and "pupil" not in world.get_season().general_gifts  # 坐騎關著：不送也不佔名額
    content.config.mounts.enabled = True
    idle_step(game)  # 照樣走到 choose 最後的贈禮檢查
    horse = game.state.player.mount
    assert (horse.name, horse.tier, horse.quality, horse.template) == ("踏霜駒", 3, "上品", "tashuang")


def test_a_gift_with_no_room_is_held(content, world):
    _book(content)
    content.config.weapons.rack_cap = 0
    game = _game(content, world)
    p = game.state.player
    p.treasure = _item("audience")
    p.affinities["mate"] = 60
    msgs = idle_step(game)
    assert [i.template for i in p.held_gear] == ["caoxie"] and treasures.HELD.format(name="舊草鞋") in msgs
    assert world.get_season().general_gifts == {"mate": "寶客"}  # 寄放了也算送出去了


# ── Task 7：挑戰本人掉落 ──

def _challenger(world, *, treasures_on=True, chance=1.0):
    """正式內容、第一季開著：官軍的人站在黃巾營，挑戰得到波才（同 test_armor 的挑戰本人那一支）。"""
    c = real_content()
    c.config.season_one = True
    c.config.auto_open_first_season = True
    c.config.treasures.enabled = treasures_on
    c.config.treasures.challenge_chance = chance
    game = Game.new(c, "官甲", rng=random.Random(0), world=world)
    game.client = None
    p = game.state.player
    p.faction, p.location = "guan", "huangjin_camp"
    p.tutorial_step = len(c.tutorial.steps)
    p.visited.add("huangjin_camp")
    p.stamina = 250.0
    game.now = 1000.0
    return game


def _won():
    from tianxia.encounter import EncounterResult
    return EncounterResult(tier="險勝", margin=20, our_power=200, difficulty=120)


def test_beating_a_great_figure_drops_a_pool_treasure_once_a_season(world):
    from tianxia import team
    game = _challenger(world)
    with mock.patch.object(team, "fight", return_value=_won()):
        msgs = game.choose("act:challenge:bocai")
    p = game.state.player
    assert p.treasure is not None and game.content.gear.treasures[p.treasure.template].pool
    assert p.treasure_drops == {"bocai"} and treasures.DROP_LINE.format(who=game.content.figures["bocai"].name, name=p.treasure.name) in msgs
    record = game.state.battles[0]
    assert treasures.GAIN_LINE.format(name=p.treasure.name) in record.materials  # 戰報「得失」那一格（同兵器掉落）
    assert not any(p.treasure.name in note for note in record.notes)  # 不重複進戰報的敘事
    assert treasures.challenge_drop(game.state, game.content, "bocai", world.get_season_number(), 99) == (None, [])  # 同一位每季只掉一次


def test_a_full_rack_means_no_roll_and_no_mark(world):
    game = _challenger(world)
    c, p = game.content, game.state.player
    c.config.weapons.rack_cap = 0
    p.treasure = Equipment(id="寶:9", slot="treasure", name="叩關玉", template="kouguan_yu")
    assert treasures.challenge_drop(game.state, c, "bocai", 1, 7) == (None, [])
    assert p.treasure_drops == set()  # 沒擲就不記「掉過」：騰出空位之後再打贏還有機會（6.4）
    c.config.weapons.rack_cap = 10
    item, _ = treasures.challenge_drop(game.state, c, "bocai", 1, 7)
    assert item is not None and item.template != "kouguan_yu" and p.treasure_drops == {"bocai"}


def test_the_drop_rolls_on_season_name_and_record(world):
    game = _challenger(world, chance=0.2)
    hits = [random.Random(f"寶|3|官甲|{rid}").random() < 0.2 for rid in range(1, 30)]
    got = []
    for rid in range(1, 30):
        game.state.player.treasure_drops = set()
        game.state.player.treasure, game.state.player.rack = None, []
        got.append(treasures.challenge_drop(game.state, game.content, "bocai", 3, rid)[0] is not None)
    assert got == hits and any(hits) and not all(hits)


def test_all_pool_treasures_owned_turns_the_drop_into_silver(world):
    game = _challenger(world)
    c, p = game.content, game.state.player
    p.rack = [Equipment(id=f"寶:{i}", slot="treasure", name=t.name, template=t.id)
              for i, t in enumerate(t for t in c.gear.treasures.values() if t.pool)]
    silver = p.stats["silver"]
    item, lines = treasures.challenge_drop(game.state, c, "bocai", 1, 7)
    assert item is None and lines == [treasures.ALL_OWNED.format(silver=c.config.treasures.dup_silver), f"銀兩 +{c.config.treasures.dup_silver}"]
    assert p.stats["silver"] == silver + c.config.treasures.dup_silver and p.treasure_drops == {"bocai"}


def test_the_treasure_drop_does_not_touch_the_game_dice(tmp_path):
    from tianxia import team
    from tianxia.sqlite_world import open_world
    states = []
    for on in (True, False):
        game = _challenger(open_world(tmp_path / f"{on}.db"), treasures_on=on)
        with mock.patch.object(team, "fight", return_value=_won()):
            game.choose("act:challenge:bocai")
        assert (game.state.player.treasure is not None) == on
        states.append(game.rng.getstate())
    assert states[0] == states[1]


# ── Task 8：機器人與假人 ──

def test_bots_put_on_the_better_treasure_by_a_fixed_order(content, world):
    """設計第九節：有好幾件時照固定順序挑一件，不每步換。寶物不設限制，同一天也照換（2.3【定】）。"""
    from tianxia import bot
    _book(content)
    game = _game(content, world)
    p = game.state.player
    p.treasure = _item("seclusion")  # 機器人不閉關：排最後
    p.rack = [_item("audience", "寶:2")]
    bot.wear_better(game)
    assert p.treasure.id == "寶:2"
    p.rack.append(_item("win_exp_pct", "寶:3"))
    bot.wear_better(game)
    assert p.treasure.id == "寶:3"  # 打贏經驗排第一：同一個遊戲日也照換
    p.rack.append(_item("cultivate", "寶:4"))
    assert treasures.wanted(game.state, content) is None
    bot.wear_better(game)
    assert p.treasure.id == "寶:3"  # 身上已經是排第一的：不每步換


def test_better_mount_is_the_one_comparison_the_market_and_the_bots_share(content, world):
    """馬照吃飽的腳力比（餓了的好馬不吃虧）：mounts.better_mount 是馬市 wanted 的前半，也是 bot.wear_better 用的那一份。"""
    from tianxia import mounts
    content.config.mounts.enabled = True
    game = _game(content, world)
    p = game.state.player
    p.mount = Equipment(id="騎:1", slot="mount", name="棗騮馬", tier=1, quality="下品", edge=100)
    p.rack = [Equipment(id="騎:2", slot="mount", name="青驄駒", tier=2, quality="下品", edge=0)]  # 餓到底的良駒
    assert mounts.better_mount(game.state, content) == "騎:2"
    p.mount, p.rack = p.rack[0], [p.mount]
    assert mounts.better_mount(game.state, content) is None  # 身上已經是快的
    content.config.mounts.enabled = False
    p.mount, p.rack = p.rack[0], [p.mount]
    assert mounts.better_mount(game.state, content) is None  # 坐騎關著：腳力都是 0


def test_bots_ride_the_faster_horse_but_not_on_the_road(content, world):
    from tianxia import bot
    _book(content)
    content.config.mounts.enabled = True
    game = _game(content, world)
    p = game.state.player
    p.mount = Equipment(id="騎:1", slot="mount", name="棗騮馬", tier=1, quality="下品")
    p.rack = [Equipment(id="騎:2", slot="mount", name="青驄駒", tier=2, quality="下品")]
    game.choose("move:lake")
    bot.wear_better(game)
    assert p.mount.id == "騎:1"  # 路上不換坐騎（2.3）
    p.journey = None
    bot.wear_better(game)
    assert p.mount.id == "騎:2"


def test_server_bots_put_on_a_better_treasure_while_looking_after_themselves(content, world):
    from tianxia import bot_policy
    _book(content)
    game = _game(content, world)
    game.state.player.rack = [_item("win_exp_pct", "寶:3")]
    bot_policy.look_after(game, random.Random(0))
    assert game.state.player.treasure.id == "寶:3"
