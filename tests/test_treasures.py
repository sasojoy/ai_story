"""寶物與好馬（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第六節、5.7；計畫 docs/superpowers/plans/2026-10-11-裝備-3-寶物與好馬.md）。"""
from __future__ import annotations

import json
import random
from unittest import mock

import pytest

from conftest import install_season_one, next_season, real_content
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


def test_cultivate_treasure_multiplies_the_odds_within_the_cap_but_not_the_sure_try_or_forcing(content, state, world):
    """設計 6.2：中品第一次 40→48、上品第一次 6→7、中品第三次照舊 100（寫明必成那一次直接回 100）。中品寫在 cultivate_sure_by 裡，
    odds_for 照樣算寶物（不併進搭配）；服丹衝關（force_odds）與頓悟不吃寶物。"""
    from tianxia import cultivation
    content.config.cultivate_odds = {"中品": (40, 20), "上品": (6, 3), "絕學": (4, 3)}
    content.config.cultivate_sure_by = {"中品": 3}
    assert cultivation.chance(content, "中品", 0, treasure=1.2) == 48
    assert cultivation.chance(content, "上品", 0, treasure=1.2) == 7
    assert cultivation.chance(content, "中品", 2, treasure=1.2) == 100
    _book(content)
    forcing = cultivation.force_odds(state, content, world, "nope")
    assert cultivation.odds_for(state, content, "中品", 0) == 40
    state.player.treasure = _item("cultivate")
    assert cultivation.odds_for(state, content, "中品", 0) == 48
    assert cultivation.force_odds(state, content, world, "nope") == forcing


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
        assert won()[0] == 17  # 乘勝 +50% 與寶物 +20% 相加：10 × 1.7；疊乘會是 18


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
        return p.materials.get("gang_1", 0) - before, len(record.materials), game.rng.getstate()

    for kind in ("train", "wild"):
        plain, worn = won(kind, dropping, False), won(kind, dropping, True)
        assert (plain[0], worn[0], worn[1]) == (1, 2, plain[1] + 1)  # 多一個、戰報的得失多一行
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
    assert set(slot["rack"][0]) == {"id", "name", "effect", "effect_text"}  # 沒有「能不能換」的旗標：寶物隨時能換（2.3）
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
