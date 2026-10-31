"""打造第二批：神器原品與仿品、定名、神器譜、三階素材新來源、假人打造（docs/superpowers/specs/2026-10-12-打造隱藏配方-design.md
第五節、第十三節；計畫 docs/superpowers/plans/2026-10-12-打造-2-神器.md）。"""
from __future__ import annotations

import random
from collections import Counter
from unittest import mock

import pytest

import server
import webharness
from conftest import FixedRandom, real_content
from test_forge_secrets import BLADE, CLEAVER, JACKET
from test_treasures import _challenger, _won
from tianxia import armor, battlelog, bot, bot_policy, equipment, forge_secrets, fusion, materials, naming, rules, skillview, smithing, team, weapons
from tianxia.content import validate
from tianxia.models import Drop, ForgeSecret, ForgeSide
from tianxia.sqlite_world import open_world
from tianxia.state import COPY_NAME, DIVINE_UNNAMED, Equipment, GearFind, Weapon
from tianxia import equipment, forge_secrets, shopview, skillview, smithing, weapons
from tianxia.state import Weapon

# 測試內容的三階素材只有隕鐵膽（剛三）：神器配方兩樣都是它（剛＋剛＝剛，不在剛柔、快慢那兩對裡）。
# 譜名不能是測試內容字表組得出的名字：content.validate 拿整張字表（字首 20 × 兵器中間字 16）過 name_problem，
# 「斷」是字首、「星」是中間字，「斷星劍」會被擋成 FORGE_CLASH，所以用字首沒有的「墜」
STAR = ForgeSecret(
    id="t_star", slot="weapon", kind="劍", main=ForgeSide(attribute="剛", tier=3), aux=ForgeSide(attribute="剛", tier=3),
    divine=True, name="墜星劍", note="劍身黑得像沒有星的夜。", clues=["星一句。", "星二句。", "星三句。"],
)
WARD = ForgeSecret(
    id="t_ward", slot="armor", main=ForgeSide(attribute="剛", tier=3), aux=ForgeSide(attribute="剛", tier=3),
    divine=True, name="鎮星甲", note="甲片沉得像一塊落下來的星鐵。", clues=["甲星一句。", "甲星二句。", "甲星三句。"],
)


@pytest.fixture
def divine_content(content):
    # 深複本（同 test_forge_secrets.forge_content 的理由：有測試會改內容裡的那一條）
    content.forge_secrets = {r.id: r.model_copy(deep=True) for r in (BLADE, CLEAVER, JACKET, STAR, WARD)}
    content.config.forge_secrets.per_season = {"weapon:1": 1, "weapon:2": 1, "armor:1": 1, "weapon:divine": 1, "armor:divine": 1}
    content.config.weapons.enabled = content.config.armor.enabled = True
    return content


def _forger(content, world, name="鑄神", silver=1000):
    """站在測試內容的城鎮（town），悟性 5；背包：隕鐵膽 ×6、精鐵砂 ×4、驚羽 ×2。"""
    from tianxia.engine import Game
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    p = game.state.player
    p.location, p.stamina, p.stats["silver"], p.stats["wis"] = "town", 100.0, silver, 5
    p.materials = {"gang_3": 6, "gang_1": 4, "kuai_1": 2}
    game.sync(0.0)
    return game


# ── Task 2：神器配方的內容與挑選 ──

def test_divine_recipes_are_picked_per_season_in_their_own_group(divine_content):
    # 神器組不再擋（第一批載入時擋成 0）。神器配方要四階（正式季整合 5.5），測試內容保持三階：驗的那一份另補一個剛四、兩條神器改四階
    checked = divine_content.model_copy(deep=True)
    checked.materials["gang_4"] = checked.materials["gang_3"].model_copy(update={"id": "gang_4", "name": "熔星髓", "tier": 4})
    for rid in ("t_star", "t_ward"):
        r = checked.forge_secrets[rid]
        r.main.tier = r.aux.tier = 4
    squad = next(iter(checked.squads.values()))  # 補的那一個四階要拿得到（載入檢查）：讓一支隊伍掉它
    squad.drops = [*squad.drops, Drop(material="gang_4")]
    validate(checked)
    picked = forge_secrets.active(divine_content, 0)
    assert Counter(forge_secrets.group_of(r) for r in picked) == {
        "weapon:1": 1, "weapon:2": 1, "armor:1": 1, "weapon:divine": 1, "armor:divine": 1}
    assert forge_secrets.match(divine_content, 0, "weapon", "劍", "gang_3", "gang_3") == STAR
    assert forge_secrets.match(divine_content, 0, "armor", smithing.ARMOR_KIND, "gang_3", "gang_3") == WARD
    divine_content.config.armor.enabled = False
    assert all(r.slot == "weapon" for r in forge_secrets.active(divine_content, 0))  # 防具關著：防具的神器配方也不挑


@pytest.mark.smoke
def test_adding_the_divine_groups_leaves_the_other_picks_alone():
    """上線那一季（10.1）：每一組各自照雜湊排、各挑各的，多了神器那兩組，原本那 6 條一條都不變。"""
    rc = real_content()
    with_divine = {t: [r.id for r in forge_secrets.active(rc, t) if not r.divine] for t in range(6)}
    rc.config.forge_secrets.per_season = {g: n for g, n in rc.config.forge_secrets.per_season.items() if not g.endswith("divine")}
    assert {t: [r.id for r in forge_secrets.active(rc, t)] for t in range(6)} == with_divine


# ── Task 3：原品與仿品 ──

def test_the_first_divine_forge_is_the_unnamed_original_and_rolls_no_quality(divine_content, world, monkeypatch):
    rolled = []
    monkeypatch.setattr(fusion, "roll_quality", lambda odds, rng: rolled.append(rng) or "下品")
    cfg = divine_content.config.forge_secrets
    game = _forger(divine_content, world, name="甲")
    item, msgs = smithing.forge(game.state, divine_content, world, "劍", "gang_3", "gang_3", rng=random.Random(0))
    assert rolled == []  # 照甲（5.1）：一爐必出神器，不擲品質，不碰亂數
    assert (item.name, item.original, item.copy_of, item.secret, item.tier, item.quality) == (DIVINE_UNNAMED, True, None, "t_star", 3, "上品")
    assert equipment.grade(item) == "三階上品" + equipment.DIVINE_MARK and not equipment.named(divine_content, item)
    assert msgs[0].startswith(f"打出一把【{DIVINE_UNNAMED}】（三階上品{equipment.DIVINE_MARK}・劍・屬剛）：鐵匠把兩份隕鐵膽下爐。") and STAR.note in msgs[0] and cfg.divine_line.format(unit="把") in msgs[0]
    find = world.lookup_gear_find("鑄|t_star")
    assert (find.divine, find.owner, find.master_shown, find.divine_name, find.copies, find.name) == (True, "甲", "甲", None, 0, DIVINE_UNNAMED)
    rumors = [r.text for r in game.state.world.rumors]
    assert cfg.divine_rumor.format(who="甲", unit="把") in rumors and not any("墜星劍" in r for r in rumors)  # 打出時的傳聞不帶名字（7.2）
    assert game.state.player.forge_manual.solved == ["t_star"]  # 鑄譜照樣記打中


def test_after_the_original_every_forge_is_a_copy_named_after_it(divine_content, world, monkeypatch):
    monkeypatch.setattr(fusion, "season_one", lambda *a, **k: True)  # 首創名望回饋只在第一季規則開著時有
    cfg = divine_content.config.forge_secrets
    first = _forger(divine_content, world, name="甲")
    smithing.forge(first.state, divine_content, world, "劍", "gang_3", "gang_3")
    mine, msgs = smithing.forge(first.state, divine_content, world, "劍", "gang_3", "gang_3")
    assert (mine.original, mine.copy_of, mine.name) == (False, "鑄|t_star", COPY_NAME.format(name=DIVINE_UNNAMED))  # 主人自己打的也是仿品（5.3）
    assert cfg.copy_mine_line in msgs[0]
    other = _forger(divine_content, world, name="乙")
    copy, msgs = smithing.forge(other.state, divine_content, world, "劍", "gang_3", "gang_3")
    assert (copy.original, copy.copy_of, copy.secret, copy.tier, copy.quality) == (False, "鑄|t_star", "t_star", 3, "上品")
    assert equipment.grade(copy) == "三階上品" + equipment.COPY_MARK and cfg.copy_line.format(who="甲") in msgs[0]
    assert world.lookup_gear_find("鑄|t_star").copies == 2
    entry = other.state.world.echoes["鑄|t_star"]
    assert entry.creator == "甲" and entry.followers == ["乙"] and entry.made == "打"  # 原品主人的回饋：主人自己打的不算


def test_armor_divine_recipes_make_originals_and_copies_too(divine_content, world):
    game = _forger(divine_content, world)
    key = "鎧|gang_3+gang_3"
    coat, _ = smithing.forge(game.state, divine_content, world, smithing.ARMOR_KIND, "gang_3", "gang_3", rng=smithing.own_rng(game.state, key))
    again, _ = smithing.forge(game.state, divine_content, world, smithing.ARMOR_KIND, "gang_3", "gang_3", rng=smithing.own_rng(game.state, key))
    assert (coat.slot, coat.original, coat.secret, coat.quality) == ("armor", True, "t_ward", "上品")
    assert (again.copy_of, again.name) == ("鑄|t_ward", COPY_NAME.format(name=DIVINE_UNNAMED))
    assert world.lookup_gear_find("鑄|t_ward").slot == "armor"


def test_originals_and_copies_take_their_own_base_and_skip_the_named_bonus(divine_content, world):
    c = divine_content
    w, a = c.config.weapons, c.config.armor
    assert (w.copy_base, w.original_base, a.copy_cut, a.original_cut) == (0.19, 0.22, 0.22, 0.25)  # 設計 4.3
    game = _forger(c, world)
    rules.learn_skill(game.state, c, "sword")
    game.state.player.member.wugong_id = "sword"
    art = team.player_art(game.state, c, world, "sword")
    plain = Weapon(id="兵:1", name="甲劍", kind="劍", attribute="剛", tier=3, quality="上品")  # 一般三階上品
    base = weapons.bonus(plain, art, c, world)
    original = plain.model_copy(update={"original": True, "secret": "t_star", "name": "墜星劍"})
    copy = plain.model_copy(update={"copy_of": "鑄|t_star", "secret": "t_star", "name": "仿・墜星劍"})
    assert weapons.bonus(original, art, c, world) == pytest.approx(base + 0.07)  # 22 對 15：上品合計 26 對 19
    assert weapons.bonus(copy, art, c, world) == pytest.approx(base + 0.04)  # 19 對 15：上品合計 23 對 19
    assert weapons.bonus(plain.model_copy(update={"secret": "t_blade"}), art, c, world) == pytest.approx(base + 0.02)  # 名器照舊
    gone = original.model_copy(update={"secret": "removed"})
    assert weapons.bonus(gone, art, c, world) == pytest.approx(base + 0.07)  # 神器不看內容：拿掉了那一條照樣算神器
    coat = Equipment(id="甲:2", slot="armor", name="甲衣", attribute="剛", tier=3, quality="上品")
    assert armor.cut(coat.model_copy(update={"original": True, "secret": "t_ward"}), None, c) == pytest.approx(armor.cut(coat, None, c) + 0.07)
    assert armor.cut(coat.model_copy(update={"copy_of": "鑄|t_ward", "secret": "t_ward"}), None, c) == pytest.approx(armor.cut(coat, None, c) + 0.04)


def test_the_go_button_says_a_solved_divine_recipe_always_makes_a_copy(divine_content, world):
    game = _forger(divine_content, world, name="甲")
    smithing.forge(game.state, divine_content, world, "劍", "gang_3", "gang_3")
    label = smithing.go_option(game.state, divine_content, world, "劍", "gang_3", "gang_3").label
    assert smithing.DIVINE_HEAD.format(name="墜星劍") in label and "工錢 150 兩" in label and "下品" not in label  # 6.4：必出神器，不寫機率
    fresh = _forger(divine_content, world, name="乙")
    label = smithing.go_option(fresh.state, divine_content, world, "劍", "gang_3", "gang_3").label
    assert "墜星劍" not in label and "神器" not in label and "下品" in label  # 自己的鑄譜上沒打中過：不露（別人打中了也不寫）


def test_old_gear_finds_read_as_named_pieces_and_divine_items_keep_names_without_a_row(divine_content, world):
    old = GearFind.model_validate_json('{"secret": "t_blade", "slot": "weapon", "attribute": "陽", "tier": 1, "title": "穿霞劍"}')
    assert (old.divine, old.owner, old.divine_name, old.copies, old.name) == (False, None, None, 0, "穿霞劍")  # 第一批的列照讀
    game = _forger(divine_content, world)
    p = game.state.player
    p.rack = [Weapon(id="兵:9", name="仿・舊神器", kind="劍", attribute="剛", tier=3, quality="上品", secret="t_star", copy_of="鑄|t_star")]
    game._drop_stale_references()
    assert p.rack[0].name == "仿・舊神器"  # 這一季那一列不在（別一季打的、資料不在）：留著存檔裡的名字


# ── Task 4：原品定名 ──

def test_the_owner_names_the_original_once_and_the_name_takes_the_namespace(divine_content, world):
    cfg = divine_content.config.forge_secrets
    owner = _forger(divine_content, world, name="甲")
    original, _ = smithing.forge(owner.state, divine_content, world, "劍", "gang_3", "gang_3")
    assert forge_secrets.unnamed_originals(owner.state, world) == {original.id: "墜星劍"}
    other = _forger(divine_content, world, name="乙")
    assert smithing.name_divine(other.state, divine_content, world, original.id, "斬月") == (False, [smithing.NAME_GONE])  # 不是他的
    ok, msgs = smithing.name_divine(owner.state, divine_content, world, original.id, "斬月")  # 不必帶劍字（5.2）
    assert ok and msgs == [smithing.DIVINE_NAMED.format(name="斬月", unit="把")] and original.name == "斬月"
    find = world.lookup_gear_find("鑄|t_star")
    assert (find.divine_name, find.name) == ("斬月", "斬月") and world.is_skill_name_taken("斬月")  # 佔名字空間（7.3）
    assert forge_secrets.unnamed_originals(owner.state, world) == {}
    assert smithing.name_divine(owner.state, divine_content, world, original.id, "別名") == (False, [smithing.NAME_GONE])  # 只定一次
    assert cfg.named_chronicle.format(who="甲", name="斬月", what="劍", unit="把") in [r.text for r in owner.state.world.chronicle]
    assert cfg.named_rumor.format(who="甲", name="斬月") in [r.text for r in owner.state.world.rumors]


def test_naming_renames_the_owners_own_copies_at_once(divine_content, world):
    """終審 M1：主人先打了仿品（「仿・無名神器」）再替原品定名——定成的同一下，他手上與裝備庫裡的仿品就跟著改成「仿・斬月」，
    不用等下一次進鎖重讀（forge_secrets.refresh_names）。"""
    owner = _forger(divine_content, world, name="甲")
    original, _ = smithing.forge(owner.state, divine_content, world, "劍", "gang_3", "gang_3")
    wielded, _ = smithing.forge(owner.state, divine_content, world, "劍", "gang_3", "gang_3")  # 原品在手上，仿品進裝備庫
    owner.state.player.weapon, owner.state.player.rack = wielded, [original]  # 換個擺法：仿品拿在手上、原品在裝備庫
    stored, _ = smithing.forge(owner.state, divine_content, world, "劍", "gang_3", "gang_3")  # 再一把仿品進裝備庫
    assert owner.state.player.weapon is wielded and owner.state.player.rack == [original, stored]
    assert [i.name for i in (wielded, stored)] == [COPY_NAME.format(name=DIVINE_UNNAMED)] * 2
    assert smithing.name_divine(owner.state, divine_content, world, original.id, "斬月")[0]
    assert (original.name, wielded.name, stored.name) == ("斬月", COPY_NAME.format(name="斬月"), COPY_NAME.format(name="斬月"))


def test_naming_updates_the_first_makers_echo_entry_and_saves_it(divine_content, world, monkeypatch):
    """終審 M2：原品定名之前就有人照著打了仿品，首創名望回饋記下的名字凍在「【無名神器】」（fusion.echo 打下的）；
    定名時同一筆改成新名字、跟著 _save_season 存回，之後主人收到的回饋與湊滿人數的傳聞才寫得出是哪一把。"""
    monkeypatch.setattr(fusion, "season_one", lambda *a, **k: True)  # 首創名望回饋只在第一季規則開著時有
    owner = _forger(divine_content, world, name="甲")
    original, _ = smithing.forge(owner.state, divine_content, world, "劍", "gang_3", "gang_3")
    other = _forger(divine_content, world, name="乙")
    smithing.forge(other.state, divine_content, world, "劍", "gang_3", "gang_3")  # 定名之前就有人照著打
    assert other.state.world.echoes["鑄|t_star"].name == f"【{DIVINE_UNNAMED}】"
    world.save_season(other.state.world)  # 乙那一下動作存回共用賽季
    owner.state.world = world.get_season()  # 甲下一次進鎖重讀
    assert owner.name_divine(original.id, "斬月") == [smithing.DIVINE_NAMED.format(name="斬月", unit="把")]
    entry = world.get_season().echoes["鑄|t_star"]  # 從資料庫讀回來：真的存了
    assert (entry.name, entry.creator, entry.followers, entry.made) == ("【斬月】", "甲", ["乙"], "打")
    owner.state.world = world.get_season()
    owner._deliver_echoes()
    assert "江湖上又有 1 人照著你首創的【斬月】打了出來。" in owner.state.journal[0].lines



def test_the_first_divine_forge_and_its_naming_go_into_the_annals(divine_content, world):
    """玩家傳（行狀，main 合進來的）：首創照第一批記名器的那一則接上神器——打出原品那一下記一則（還沒定名，寫譜名），
    定名再記一則（份量 5，同絕學定名）；別人照著打的仿品不記。"""
    divine_content.config.biography.enabled = True
    owner = _forger(divine_content, world, name="甲")
    original, _ = smithing.forge(owner.state, divine_content, world, "劍", "gang_3", "gang_3")
    assert [(e.text, e.weight) for e in owner.state.player.annals] == [(smithing.DIVINE_DEED.format(name="墜星劍"), 4)]
    other = _forger(divine_content, world, name="乙")
    smithing.forge(other.state, divine_content, world, "劍", "gang_3", "gang_3")
    assert other.state.player.annals == []  # 仿品不是首創
    assert smithing.name_divine(owner.state, divine_content, world, original.id, "斬月")[0]
    assert (owner.state.player.annals[-1].text, owner.state.player.annals[-1].weight) == (smithing.DIVINE_NAMED_DEED.format(name="斬月"), 5)

@pytest.mark.parametrize("slot, pick, problem", [
    ("weapon", lambda c: "斬月刀", weapons.KIND_CLASH),  # 劍的原品不能有別種兵器的字
    ("weapon", lambda c: weapons.shop_name("劍", "剛"), weapons.SHOP_CLASH),
    ("weapon", lambda c: weapons.table_name(c, "劍", "gang_1", "kuai_1"), forge_secrets.TABLE_CLASH),  # 不然「仿・X」跟一般組合的 X 並存
    ("weapon", lambda c: "穿霞劍", naming.FORGE_CLASH),  # 別條隱藏配方的名字（name_problem）
    ("armor", lambda c: "斬月劍", armor.WORD_CLASH),
    ("armor", lambda c: armor.SHOP_NAMES["剛"], armor.SHOP_CLASH),
    ("armor", lambda c: armor.table_name(c, "gang_1", "kuai_1", "陽"), forge_secrets.TABLE_CLASH),
])
def test_a_divine_name_is_checked_like_mastery_plus_kind_shop_and_table(divine_content, world, slot, pick, problem):
    game = _forger(divine_content, world)
    kind = "劍" if slot == "weapon" else smithing.ARMOR_KIND
    original, _ = smithing.forge(game.state, divine_content, world, kind, "gang_3", "gang_3")
    ok, msgs = smithing.name_divine(game.state, divine_content, world, original.id, pick(divine_content))
    assert not ok and msgs == [smithing.NAME_BAD.format(problem=problem)] and original.name == DIVINE_UNNAMED
    assert world.lookup_gear_find(forge_secrets.key_for(original.secret)).divine_name is None  # 什麼都沒動，定名的權利還在


def test_keep_takes_the_book_name_and_copies_follow_on_load(divine_content, world):
    owner = _forger(divine_content, world, name="甲")
    original, _ = smithing.forge(owner.state, divine_content, world, "劍", "gang_3", "gang_3")
    other = _forger(divine_content, world, name="乙")
    early, _ = smithing.forge(other.state, divine_content, world, "劍", "gang_3", "gang_3")
    assert early.name == COPY_NAME.format(name=DIVINE_UNNAMED)
    ok, _ = smithing.name_divine(owner.state, divine_content, world, original.id, "", keep=True)
    assert ok and original.name == "墜星劍"  # 沿用譜名（5.2）：不過 name_problem（譜名撞到自己會回 FORGE_CLASH）
    later, _ = smithing.forge(other.state, divine_content, world, "劍", "gang_3", "gang_3")
    assert later.name == "仿・墜星劍"
    other._drop_stale_references()
    assert early.name == "仿・墜星劍"  # 定名之前打的仿品：下一次讀檔照全服那一列重寫（5.3）


def test_two_originals_cannot_share_a_name(divine_content, world):
    a = _forger(divine_content, world, name="甲")
    sword, _ = smithing.forge(a.state, divine_content, world, "劍", "gang_3", "gang_3")
    b = _forger(divine_content, world, name="乙")
    coat, _ = smithing.forge(b.state, divine_content, world, smithing.ARMOR_KIND, "gang_3", "gang_3",
                             rng=smithing.own_rng(b.state, "鎧|gang_3+gang_3"))
    assert smithing.name_divine(a.state, divine_content, world, sword.id, "斬月")[0]
    assert smithing.name_divine(b.state, divine_content, world, coat.id, "斬月") == (False, [smithing.NAME_TAKEN.format(name="斬月")])
    assert coat.name == DIVINE_UNNAMED  # 原子：全服不重名，後到的換一個


def test_naming_goes_through_the_game_and_only_a_true_keep_counts(divine_content, world):
    import server
    game = _forger(divine_content, world, name="甲")
    original, _ = smithing.forge(game.state, divine_content, world, "劍", "gang_3", "gang_3")
    msgs = server.MENXIA_ACTIONS["name_divine"](game, {"weapon": original.id, "keep": "true"})  # 只認布林 true（同 use_legend）
    assert original.name == DIVINE_UNNAMED and msgs[0].startswith("這個名字不行")
    msgs = server.MENXIA_ACTIONS["name_divine"](game, {"weapon": original.id, "keep": True})
    assert original.name == "墜星劍" and msgs[0] == smithing.DIVINE_NAMED.format(name="墜星劍", unit="把")
    assert game.state.journal[0].tag == msgs[0]  # 修練紀錄（同絕學定名 _menxia_entry）


# ── Task 5：神器譜；原品不能拆、不能交 ──

def _book(game) -> str:
    """榜單的神器譜（Joy 2026-10-17 從江湖史搬過去），一筆一行接起來比對。"""
    return "\n".join(f"{r['season']} {r['name']} {r['text']}" for r in game.divine_book_view())


def test_the_divine_book_lives_on_the_boards_across_seasons(divine_content, world):
    owner = _forger(divine_content, world, name="甲")
    original, _ = smithing.forge(owner.state, divine_content, world, "劍", "gang_3", "gang_3")
    smithing.forge(owner.state, divine_content, world, "劍", "gang_1", "kuai_1")  # 名器不上神器譜
    smithing.forge(_forger(divine_content, world, name="乙").state, divine_content, world, "劍", "gang_3", "gang_3")
    season = world.get_season_number()
    old = GearFind(secret="t_old", slot="armor", attribute="剛", tier=3, title="舊甲", creator="丙", creator_shown="丙",
                   divine=True, owner="丙", master_shown="丙", divine_name="鎮岳甲", copies=3)
    with world.db.transaction() as conn:  # 上一季的原品：換季不刪，跨季保留（5.5）
        conn.execute("INSERT INTO gear_recipes (season, key, name, creator, data) VALUES (?, ?, ?, ?, ?)",
                     (season - 1, "鑄|t_old", "鎮岳甲", "丙", old.model_dump_json()))
    assert [(s, f.secret) for s, f in world.divine_records()] == [(season - 1, "t_old"), (season, "t_star")]
    book = _book(owner)
    assert forge_secrets.DIVINE_BOOK not in owner.chronicle_text()  # 江湖史不再接神器譜
    assert [r["season"] for r in owner.divine_book_view()] == [season, season - 1]  # 新的一季在前
    assert f"{DIVINE_UNNAMED}（劍）" in book and "仿品 1 把" in book and "【鎮岳甲】" in book and "仿品 3 件" in book  # 防具論件（終審 F5）
    assert "乙" not in book and "穿霞劍" not in book  # 不列打仿品的人；名器不上
    smithing.name_divine(owner.state, divine_content, world, original.id, "斬月")
    assert "【斬月】" in _book(owner)


def test_an_original_cannot_be_dismantled_but_a_copy_can(divine_content, world):
    game = _forger(divine_content, world)
    p = game.state.player
    original, _ = smithing.forge(game.state, divine_content, world, "劍", "gang_3", "gang_3")  # 拿在手上
    first, _ = smithing.forge(game.state, divine_content, world, "劍", "gang_3", "gang_3")  # 仿品進裝備庫
    second, _ = smithing.forge(game.state, divine_content, world, "劍", "gang_3", "gang_3")
    weapons.wield(game.state, divine_content, first.id)  # 原品換下來、進裝備庫
    assert original in p.rack
    assert weapons.dismantle(game.state, divine_content, original.id) == [equipment.ORIGINAL_KEPT_LINE.format(unit="把")] and original in p.rack
    row = weapons._row(original, None, divine_content, world)
    assert (row["keep"], row["confirm"]) == (equipment.ORIGINAL_KEPT, "")  # 5.4：鈕灰掉寫原因、沒有問句
    assert weapons._row(second, None, divine_content, world)["keep"] == ""
    assert weapons.dismantle(game.state, divine_content, second.id)[0].startswith(equipment.DISMANTLE_PREFIX)
    assert p.materials == {"gang_3": 1, "gang_1": 4, "kuai_1": 2}  # 仿品照一般兵器拆：拆成一個三階（打一把要兩個，拆了不會賺）
    game.choose("act:smith")
    menu = {o.id: o for o in game.options(odds=False)}
    kept = menu[f"smith:dismantle:{original.id}"]
    assert not kept.enabled and equipment.ORIGINAL_KEPT in kept.label  # 鐵匠鋪那一顆照樣列出、灰掉寫原因


def test_an_armor_original_is_kept_too(divine_content, world):
    game = _forger(divine_content, world)
    key = "鎧|gang_3+gang_3"
    coat, _ = smithing.forge(game.state, divine_content, world, smithing.ARMOR_KIND, "gang_3", "gang_3", rng=smithing.own_rng(game.state, key))
    spare, _ = smithing.forge(game.state, divine_content, world, smithing.ARMOR_KIND, "gang_3", "gang_3", rng=smithing.own_rng(game.state, key))
    armor.wield(game.state, divine_content, spare.id)  # 原品進裝備庫
    assert armor.dismantle(game.state, divine_content, coat.id) == [equipment.ORIGINAL_KEPT_LINE.format(unit="件")]
    assert armor._row(coat, None, divine_content)["keep"] == equipment.ORIGINAL_KEPT


# ── Task 6：畫面要的資料 ──

def test_gear_rows_mark_the_unnamed_original_with_its_book_name(divine_content, world):
    game = _forger(divine_content, world, name="甲")
    original, _ = smithing.forge(game.state, divine_content, world, "劍", "gang_3", "gang_3")
    worn = lambda: next(s for s in skillview.gear_rows(game.state, divine_content, world)["slots"] if s["slot"] == "weapon")["worn"]  # noqa: E731
    row = worn()
    assert row["divine"] == {"pattern": "墜星劍", "unit": "把"} and row["grade"].endswith(equipment.DIVINE_MARK)
    smithing.name_divine(game.state, divine_content, world, original.id, "", keep=True)
    row = worn()
    assert row["divine"] is None and row["name"] == "墜星劍"  # 定了名：表單不再畫


def _crowded_rack(content, world):
    """手上拿著一把、裝備庫裡九把一般的，然後才打出原品——原品放在裝備庫的最後一格（equipment.store 一律接在後面）。"""
    game = _forger(content, world, name="甲")
    p = game.state.player
    p.weapon = weapons.new_weapon(game.state, name="手刃", kind="劍", attribute="剛", tier=1, quality="下品")
    p.rack = [weapons.new_weapon(game.state, name=f"備刃{i}", kind="刀", attribute="柔", tier=1, quality="下品") for i in range(9)]
    original, _ = smithing.forge(game.state, content, world, "劍", "gang_3", "gang_3")
    assert p.rack[-1] is original and len(p.rack) == 10  # 它真的排在最後
    return game, original


def test_gear_rows_put_the_unnamed_original_first_in_a_long_rack(divine_content, world):
    """終審 I1：修練頁的裝備庫先列 8 件，原品排在最後一格就會被「再列 N 件」藏起來，定名表單找不到——還等著定名的原品排最前面，
    其餘維持原本的先後。定了名就回到原位（不再特別排）。"""
    game, original = _crowded_rack(divine_content, world)
    rack = lambda: next(s for s in skillview.gear_rows(game.state, divine_content, world)["slots"] if s["slot"] == "weapon")["rack"]  # noqa: E731
    rows = rack()
    assert rows[0]["id"] == original.id and rows[0]["divine"] == {"pattern": "墜星劍", "unit": "把"}
    assert [r["name"] for r in rows[1:]] == [f"備刃{i}" for i in range(9)]  # 其餘照原來的先後
    assert all(r["divine"] is None for r in rows[1:])
    assert smithing.name_divine(game.state, divine_content, world, original.id, "", keep=True)[0]
    assert [r["id"] for r in rack()] == [w.id for w in game.state.player.rack]  # 定了名：裝備庫照原樣的順序


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_naming_form_is_drawn_without_pressing_more_when_the_original_is_stored_last(divine_content, world):
    """終審 I1：手上一把、裝備庫九把一般的、原品放最後——修練頁預設只列 8 件，定名表單照樣畫在前 8 件裡（不必按「再列 N 件」）。"""
    from test_weapons_web import _practice
    game, original = _crowded_rack(divine_content, world)
    page = _practice(server.main_view(game), menxia=server.menxia_view(game))  # 裝備庫在那一格的抽屜裡（俠客頁改版）
    block = page.split('data-slot="weapon"')[1].split("</section>")[0]
    assert f'data-op="name-divine" data-id="{original.id}"' in block and f'data-act="divine-keep" data-id="{original.id}"' in block
    assert "再列 2 件" in block and block.count('data-act="wield"') == 8  # 裝備庫仍只列 8 件，表單是其中一件的
    assert block.index("name-divine-") < block.index("備刃6")  # 原品排在一般的前面


# ── Task 7：三階素材的新來源（兵器設計 4.9）──

def test_tier3_pick_follows_the_attribute_and_splits_paired_ones_by_seed():
    rc = real_content()
    assert materials.tier3_pick(rc, "剛", "種子") == "gang_3" and materials.tier3_pick(rc, "慢", "x") == "man_3"
    picks = {materials.tier3_pick(rc, "實", f"種子{i}") for i in range(40)}
    assert picks == {"gang_3", "man_3"}  # 實＝剛＋慢：照種子挑一個來源（同拆解）
    assert materials.tier3_pick(rc, "實", "同一個") == materials.tier3_pick(rc, "實", "同一個")  # 決定性
    assert materials.tier3_pick(rc, None, "x") in {"gang_3", "rou_3", "kuai_3", "man_3"}


def test_beating_a_great_figure_drops_a_tier_three_of_his_attribute_on_the_first_win_only(world):
    """挑戰大勢人物每季都有設計丁 (c)（企劃者 2026-10-13）：保證的那一個三階只在這一季第一次打贏某位人物時給（tier3_per_figure 1；
    打造第二批原本是每位每季 2 次）。"""
    from tianxia.engine import Game
    game = _challenger(world, treasures_on=False)
    rule = game.content.config.forge_secrets
    assert (rule.challenge_tier3, rule.tier3_per_figure, rule.big_tier3) == (1.0, 1, 0.25)  # 「要 PM 定的」第 2 條；每位一次是丁 (c)
    p = game.state.player
    got = []
    with mock.patch.object(team, "fight", return_value=_won()), mock.patch.object(materials, "roll_squad_drops", return_value=[]),             mock.patch.object(Game, "_rout", return_value=[]):  # 不讓他敗走退場：同一位連打三場
        for _ in range(3):
            p.snubbed_until.clear()
            p.stamina = 250.0
            before = p.materials.get("gang_3", 0)
            game.choose("act:challenge:bocai")
            got.append(p.materials.get("gang_3", 0) - before)
    assert got == [1, 0, 0] and p.tier3_drops == {"bocai": 1}  # 波才的隊伍屬剛：隕鐵膽；這一季第一次打贏才有
    assert game.state.battles[-1].materials == [f"隕鐵膽 ×1（{materials.CHALLENGE_SOURCE}）"]  # 第一場的戰報「得失」那一格（寫來源，FB-147；只有這一個不寫 +1，F8）


def test_the_tier_three_drop_never_touches_the_game_rng(world, tmp_path):
    draws = []
    for chance, store in ((1.0, world), (0.0, open_world(tmp_path / "off.db"))):
        game = _challenger(store, treasures_on=False)
        game.content.config.forge_secrets.challenge_tier3 = chance
        with mock.patch.object(team, "fight", return_value=_won()):
            game.choose("act:challenge:bocai")
        draws.append(game.rng.random())
    assert draws[0] == draws[1]  # 自己的亂數（FB-129）：掉不掉，Game.rng 接下來的序列都一樣


def test_big_fights_roll_once_more_but_the_figure_squad_and_small_fights_do_not(world):
    game = _challenger(world, treasures_on=False)  # 站在黃巾營、引導走完：不在序章（序章不掉素材）
    c = game.content
    c.config.forge_secrets.big_tier3 = 1.0

    def tier3():
        return sum(n for mid, n in game.state.player.materials.items() if c.materials[mid].tier == 3)

    def rewards(squad_id, kind="event"):
        squad = c.squads[squad_id]
        record = battlelog.new_record(game.state, c, world, squad, _won(), kind)
        before = tier3()
        with mock.patch.object(materials, "roll_squad_drops", return_value=[]):  # 只看這一擲：掉落表照舊用 Game.rng，另測
            msgs = game._battle_rewards(squad, record)
        return msgs, record, tier3() - before

    msgs, record, gained = rewards("fanjianglong")  # 難度 150（≥ big_fight_difficulty）、屬剛：大場面
    assert gained == 1 and materials.extra_line(c, "gang_3", 1, materials.BIG_SOURCE) in msgs
    assert record.materials == [f"隕鐵膽 ×1（{materials.BIG_SOURCE}）"]  # 得失寫來源（FB-147；只有這一個不寫 +1，F8）
    assert rewards("fanjianglong", "train")[2] == 1  # 遊歷撞上的大場面也擲
    assert rewards("fanjianglong", "wild")[2] == 0  # 探索野怪不算大場面：不擲
    assert rewards("figure_bocai")[2] == 0  # 大勢人物本人那支隊伍：那一個在 _challenge，這裡不重複擲
    small = next(s.id for s in c.squads.values() if not game.is_big(s))
    assert rewards(small)[2] == 0  # 不是大場面：不擲


def test_tier_three_knobs_are_off_in_the_fixture(content):
    rule = content.config.forge_secrets
    assert (rule.challenge_tier3, rule.tier3_per_figure, rule.big_tier3) == (0, 0, 0)  # 預設全關（舊測試一個字都不變）


# ── Task 8：假人與機器人沿用譜名 ──

def test_server_bots_keep_the_book_name_on_a_later_turn(divine_content, world):
    """PM 決定第 3 條：打中神器配方的假人用「沿用譜名」（Game.name_divine(keep=True)，跟真人按那一顆一樣），
    不在打出來那一下就定：每一輪 DIVINE_NAME_CHANCE 的機會。"""
    game = _forger(divine_content, world, name="假甲")
    original, _ = smithing.forge(game.state, divine_content, world, "劍", "gang_3", "gang_3")
    assert bot_policy._name_originals(game, FixedRandom(0.9)) == [] and original.name == DIVINE_UNNAMED  # 這一輪沒擲中
    bot_policy._name_originals(game, FixedRandom(0.1))
    assert original.name == "墜星劍" and world.lookup_gear_find("鑄|t_star").divine_name == "墜星劍"
    assert bot_policy._name_originals(game, FixedRandom(0.1)) == []  # 定過了：沒有等著定名的，連亂數都不擲


def test_season_bots_keep_the_book_name_right_away(divine_content, world):
    game = _forger(divine_content, world)
    original, _ = smithing.forge(game.state, divine_content, world, smithing.ARMOR_KIND, "gang_3", "gang_3",
                                 rng=smithing.own_rng(game.state, "鎧|gang_3+gang_3"))
    bot.keep_book_names(game)
    assert original.name == "鎮星甲"  # 整季機器人不上線，打出原品一律馬上沿用譜名（設計第十一節）


# ── forge-fix：FB-143 ──

def test_the_forge_result_names_the_piece_first_so_a_one_line_card_shows_it(divine_content, world):
    """FB-143：375 寬鐵匠鋪選單長時「剛剛」收成一行，只露結果句開頭十幾個字——打出的東西（名字、種類、屬性、階品）寫在最前面，
    「鐵匠把…下爐」接在後面。一般組合、名器、神器原品與仿品、防具都一樣。"""
    game = _forger(divine_content, world)
    game.state.player.materials.update({"gang_1": 6, "kuai_1": 2})
    s, c = game.state, divine_content
    weapon_forges = [("刀", "gang_1", "gang_1"), ("劍", "gang_1", "kuai_1"), ("劍", "gang_3", "gang_3"), ("劍", "gang_3", "gang_3")]
    armor_forges = [("gang_1", "gang_1"), ("gang_1", "kuai_1"), ("gang_3", "gang_3")]
    made = [smithing.forge(s, c, world, kind, main, aux) for kind, main, aux in weapon_forges]
    made += [smithing.forge(s, c, world, smithing.ARMOR_KIND, main, aux, rng=smithing.own_rng(s, f"鎧|{main}+{aux}")) for main, aux in armor_forges]
    names = [item.name for item, _ in made]
    assert names[1] == "穿霞劍" and names[2] == DIVINE_UNNAMED and names[3] == COPY_NAME.format(name=DIVINE_UNNAMED)  # 名器、原品、仿品都有
    assert names[5] == "赤霞鎧" and made[6][0].original  # 防具的名器、神器原品
    for (item, msgs), noun in zip(made, ["把"] * 4 + ["件"] * 3):
        first = msgs[0].split("\n")[0]
        named = "名器" if equipment.named(c, item) else ""  # FB-148：名器寫在名字前面
        assert first.startswith(f"打出一{noun}{named}【{item.name}】（{equipment.tier_quality(item)}") and "：鐵匠把" in first, first


# ── 原 test_fb_batch_c.py（整檔搬進來） ──
# 回饋單丙批（PM 2026-10-14 派工：回饋單甲批、乙批 QA 新開的四張小單）：一張單一段，各自的重現與修正。新寫的字都待 joy 潤。

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
    from test_weapons_web import _armor_row, _gear, _practice, _row, _slot_block

    from tianxia.engine import Game

    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    m, x = server.main_view(game), server.menxia_view(game)
    x["gear"] = _gear(
        weapon={"worn": None, "rack": [_row(id="兵:2", kind="拳腳", name="無名神器", keep="原品不能拆", divine={"pattern": "撼岳拳套", "unit": "副"}),
                                       _row(id="兵:3", name="無名神器", keep="原品不能拆", divine={"pattern": "墜星劍", "unit": "把"})]},
        armor={"worn": _armor_row(id="甲:1", name="無名神器", keep="原品不能拆", divine={"pattern": "鎮星甲", "unit": "件"}), "rack": []},
    )
    page = _practice(m, menxia=x)  # 裝備庫在那一格的抽屜裡（俠客頁改版）
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
