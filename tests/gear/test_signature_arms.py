"""打造第三批：名將本命兵器（docs/superpowers/specs/2026-10-09-兵器-design.md 4.10；打造隱藏配方設計第十三節第三批；
計畫 docs/superpowers/plans/2026-10-12-打造-3-名將本命兵器.md）。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from conftest import idle_step, next_season, real_content
from test_treasures import _game, _gear_root, _won
from tianxia import equipment, figures, forge_secrets, naming, rules, signature_arms, smithing, team, treasures, weapons
from tianxia.characters import CharacterStore
from tianxia.content import ContentError, load_content
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.models import GearBook, SignatureArmDef
from tianxia.state import FigureState, GameState, GearFind, SignatureClaim, Weapon, WorldState

# 測試內容用的一把：韓鐵（mate）的刀。四個字、只帶「刀」：測試內容的兵器字表組出來的刀名都是三個字，撞不到
ARM = {"character": "mate", "name": "鐵脊長刀", "kind": "刀", "attribute": "剛"}


def _arms(content, **extra):
    """打開兵器（測試內容關著），裝上一把本命兵器（預設是 ARM；extra 改欄位）。直接建 GearBook，不走載入檢查。"""
    content.config.weapons.enabled = True
    content.gear = GearBook(signature_arms=[SignatureArmDef(**{**ARM, **extra})])
    return content


# ── Task 1：內容、資料形狀與載入檢查 ──

def test_the_real_table_has_seven_arms_matching_each_generals_own_art():
    c = real_content()
    arms = {a.character: a for a in c.gear.signature_arms}
    assert {cid: a.name for cid, a in arms.items()} == {
        "caocao": "梟風槍", "liubei": "雲紋雙鋒", "guanyu": "赤魄長刀", "zhangfei": "裂雷矛",
        "sunjian": "江潮槍", "yuanshao": "冠冕劍", "taoqian": "厚德杖",
    }  # 兵器設計 4.10 的暫名表（待 joy 潤；換名只改 content/gear.json）
    for cid, arm in arms.items():
        art = c.skills[c.characters[cid].starting_wugong]
        assert (arm.kind, arm.attribute) == (art.weapon, art.attribute), cid  # 種類・屬性照他的本命武學
    assert [(a.character, a.figure) for a in c.gear.signature_arms if a.figure] == [("sunjian", "sunjian")]  # 只有孫堅是大勢人物
    assert all(naming.name_problem(a.name, c) == naming.GEAR_CLASH for a in arms.values())  # 名字佔住：模型、玩家都取不到
    assert (c.config.weapons.signature_affinity, c.config.weapons.signature_wins) == (80, 3)


def test_the_signature_table_loads_from_gear_json(tmp_path):
    c = load_content(_gear_root(tmp_path, lambda d: d.update(signature_arms=[ARM])))
    arm = c.gear.signature_arms[0]
    assert (arm.character, arm.name, arm.kind, arm.attribute, arm.figure, arm.gift_line, arm.seize_line) == (
        "mate", "鐵脊長刀", "刀", "剛", None, "", "")
    assert naming.name_problem("鐵脊長刀", c) == naming.GEAR_CLASH


@pytest.mark.parametrize("bad, match", [
    ({"character": "ghost"}, "ghost"),
    ({"kind": "鞭"}, "種類"),
    ({"attribute": "冷"}, "屬性"),
    ({"name": "鐵脊長劍"}, "別種兵器"),  # 刀不能帶劍字
    ({"name": "烏木名刺"}, "重複"),  # 跟寶物同名（_gear_root 的寶物表裡有）
    ({"figure": "bocai"}, "大勢人物"),  # 測試內容沒有人物表
    ({"gift_line": "{who}把【{arm}】給你"}, "general"),
    ({"seize_line": "把【{gift}】擲給你"}, "general"),
])
def test_bad_signature_tables_are_rejected(tmp_path, bad, match):
    root = _gear_root(tmp_path, lambda d: d.update(signature_arms=[{**ARM, **bad}]))
    with pytest.raises(ContentError, match=match):
        load_content(root)


def test_one_general_has_one_arm(tmp_path):
    root = _gear_root(tmp_path, lambda d: d.update(signature_arms=[ARM, {**ARM, "name": "鐵脊重刀"}]))
    with pytest.raises(ContentError, match="兩次"):
        load_content(root)


@pytest.mark.smoke
def test_old_saves_read_with_empty_signature_fields(content, world):
    """舊存檔沒有 Equipment.signature、PlayerState.figure_wins、WorldState.signature_arms：讀得進來，都是預設值（不升資料庫版本）。"""
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    game.state.player.rack = [Weapon(id="兵:1", name="甲劍", kind="劍", attribute="剛", tier=1, quality="下品")]
    raw = game.state.model_dump(mode="json")
    raw["player"].pop("figure_wins")
    raw["player"]["rack"][0].pop("signature")
    raw["world"] = game.state.world.model_dump(mode="json")  # GameState 的 world 是 exclude 的；舊存檔裡夾帶的讀得進來、隨即被取代
    raw["world"].pop("signature_arms")
    loaded = GameState.model_validate(raw)
    assert loaded.player.figure_wins == {} and loaded.player.rack[0].signature is None and loaded.world.signature_arms == {}
    assert SignatureClaim(owner="甲", via="gift").model_dump() == {"owner": "甲", "via": "gift"}


# ── Task 2：一把本命兵器 ──

def test_a_signature_arm_is_a_tier_three_original_with_its_own_mark(content, world):
    _arms(content)
    game = _game(content, world)
    arm = signature_arms.new_arm(game.state, content.gear.signature_arms[0])
    assert (arm.slot, arm.name, arm.kind, arm.attribute, arm.tier, arm.quality) == ("weapon", "鐵脊長刀", "刀", "剛", 3, "上品")
    assert (arm.original, arm.signature, arm.secret, arm.copy_of) == (True, "mate", None, None)  # 算原品、不是打出來的
    assert arm.id.startswith("兵:") and equipment.grade(arm) == f"三階上品{equipment.SIGNATURE_MARK}"


def test_it_counts_as_a_divine_original_and_the_bots_pick_it_from_the_rack(content, world):
    _arms(content, name="鐵脊雙鋒", kind="劍", attribute="柔")
    game = _game(content, world)
    rules.learn_skill(game.state, content, "sword")  # 流雲劍：劍・柔
    game.state.player.member.wugong_id = "sword"
    art = team.player_art(game.state, content, world, "sword")
    w = content.config.weapons
    arm = signature_arms.new_arm(game.state, content.gear.signature_arms[0])
    assert weapons.bonus(arm, art, content, world) == pytest.approx(w.original_base + w.quality_bonus["上品"] + w.match)  # 22＋4＋同屬性 5
    game.state.player.weapon = Weapon(id="兵:90", name="甲劍", kind="劍", attribute="柔", tier=3, quality="上品")
    game.state.player.rack = [arm]
    assert smithing.better_in_rack(game.state, content, world, art) is arm  # 整季機器人與假人換兵器照這一份：拿到了就會換上


def test_names_follow_the_content_on_load(content, world):
    """名字照內容讀（joy 改名不動存檔）：每次建 Game 都照 content/gear.json 重寫；內容拿掉了那一把就留著舊名字。"""
    _arms(content)
    game = _game(content, world)
    p = game.state.player
    arm = signature_arms.new_arm(game.state, content.gear.signature_arms[0])
    arm.name = "舊名"
    p.rack = [arm]
    CharacterStore(world.db).save(game.state)
    loaded = Game(content, CharacterStore(world.db).load(p.name), random.Random(0), world)
    assert [a.name for a in signature_arms.owned(loaded.state.player)] == ["鐵脊長刀"]
    content.gear = GearBook()
    signature_arms.refresh_names(loaded.state.player, content)
    assert [a.name for a in signature_arms.owned(loaded.state.player)] == ["鐵脊長刀"]  # 拿掉了：留著


def test_a_signature_arm_cannot_be_dismantled(content, world):
    _arms(content)
    game = _game(content, world)
    p = game.state.player
    arm = signature_arms.new_arm(game.state, content.gear.signature_arms[0])
    p.weapon, p.rack = Weapon(id="兵:90", name="甲刀", kind="刀", attribute="剛", tier=1, quality="下品"), [arm]
    assert weapons.dismantle(game.state, content, arm.id) == [equipment.SIGNATURE_KEPT_LINE.format(unit=equipment.unit_for("weapon", arm.kind))] and arm in p.rack
    row = weapons._row(arm, None, content, world)
    assert (row["keep"], row["confirm"]) == (equipment.SIGNATURE_KEPT, "")  # 修練頁：鈕灰掉寫原因、沒有問句
    game.choose("act:smith")
    kept = {o.id: o for o in game.options(odds=False)}[f"smith:dismantle:{arm.id}"]
    assert not kept.enabled and equipment.SIGNATURE_KEPT in kept.label  # 鐵匠鋪那一顆照樣列出、灰掉寫原因


def test_a_new_season_clears_the_arm_and_the_claims(content, world):
    _arms(content)
    game = _game(content, world)
    game.state.player.rack = [signature_arms.new_arm(game.state, content.gear.signature_arms[0])]
    game.state.player.figure_wins = {"sunjian": 2}
    game.state.world.signature_arms = {"mate": SignatureClaim(owner=game.state.player.name, via="gift")}
    game._save_season()  # 歸屬真的寫進這一季那一列，換季才有東西可清
    next_season(content, world, game)
    assert signature_arms.owned(game.state.player) == [] and game.state.player.figure_wins == {}
    assert game.state.world.signature_arms == {}  # 換季整個重來（兵器設計 2.5）；神器譜照 seasons 表留著（Task 5）


# ── Task 3：情誼那條路 ──

def test_a_general_hands_over_his_arm_at_eighty_once_a_season(content, world):
    _arms(content)
    first, second = _game(content, world, "甲客"), _game(content, world, "乙客")
    first.state.player.affinities["mate"] = 79
    idle_step(first)
    assert signature_arms.owned(first.state.player) == []
    first.state.player.affinities["mate"] = 80
    msgs = idle_step(first)  # 照樣走到 choose 最後的檢查
    [arm] = signature_arms.owned(first.state.player)
    assert arm.name == "鐵脊長刀" and signature_arms.GIFT_LINE.format(general="韓鐵", arm="鐵脊長刀") in msgs
    assert world.get_season().signature_arms == {"mate": SignatureClaim(owner="甲客", via="gift")}
    second.sync(1.0)
    second.state.player.affinities["mate"] = 100
    idle_step(second)
    assert signature_arms.owned(second.state.player) == []  # 每位名將每季全服一人


def test_affinity_from_an_event_also_brings_the_arm(content, world):
    """情誼從事件（Effect.affinity）來也給（同名將贈禮：choose 最後檢查）。"""
    _arms(content)
    game = _game(content, world)
    content.events["drunk"].choices[1].effect.affinity = {"mate": 1}
    game.state.player.affinities["mate"] = 79
    game.state.pending_event = "drunk"
    game.choose("choice:1")
    assert [a.signature for a in signature_arms.owned(game.state.player)] == ["mate"]


def test_the_gift_goes_into_the_chronicle_the_rumors_and_the_annals(content, world):
    _arms(content)
    content.config.biography.enabled = True  # 行狀（測試內容關著：annals.note 什麼都不記）
    game = _game(content, world, "甲客")
    game.state.player.affinities["mate"] = 80
    idle_step(game)
    season = world.get_season()
    words = {"who": "甲客", "general": "韓鐵", "arm": "鐵脊長刀"}
    assert signature_arms.CHRONICLE_GIFT.format(**words) in [r.text for r in season.chronicle]
    assert signature_arms.RUMOR_GIFT.format(**words) in [r.text for r in season.rumors]
    assert signature_arms.ANNAL_GIFT.format(general="韓鐵", arm="鐵脊長刀") in [e.text for e in game.state.player.annals]


def test_with_weapons_off_nothing_is_given_or_claimed(content, world):
    _arms(content)
    content.config.weapons.enabled = False
    game = _game(content, world)
    game.state.player.affinities["mate"] = 90
    idle_step(game)
    assert signature_arms.owned(game.state.player) == [] and world.get_season().signature_arms == {}  # 不給也不佔名額
    content.config.weapons.enabled = True
    idle_step(game)
    assert len(signature_arms.owned(game.state.player)) == 1  # 開了之後照樣給得出去


def test_with_no_room_the_arm_is_held_and_still_counts_as_given(content, world):
    _arms(content)
    content.config.weapons.rack_cap = 0
    game = _game(content, world)
    p = game.state.player
    p.weapon = Weapon(id="兵:90", name="甲刀", kind="刀", attribute="剛", tier=1, quality="下品")
    p.affinities["mate"] = 80
    msgs = idle_step(game)
    assert [i.signature for i in p.held_gear] == ["mate"] and treasures.HELD.format(name="鐵脊長刀") in msgs
    assert "mate" in world.get_season().signature_arms  # 寄放了也算給出去了（「要 PM 定的」第 6 條）


# ── Task 4：打贏三次那條路 ──

def _sun_challenger(world, name="黃甲"):
    """正式內容、第一季開著：黃巾的人站在宛城，挑戰得到孫堅（照 test_treasures._challenger，換成黃巾、宛城）。寶物關著，免得多一筆掉落。"""
    c = real_content()
    c.config.season_one = True
    c.config.auto_open_first_season = True
    c.config.treasures.enabled = False
    game = Game.new(c, name, rng=random.Random(0), world=world)
    game.client = None
    p = game.state.player
    p.faction, p.location = "huang", "wan_city"
    p.tutorial_step = len(c.tutorial.steps)
    p.visited.add("wan_city")
    p.stamina = 250.0
    game.now = 1000.0
    return game


def _beat_sun(game, times):
    """連打孫堅 times 場、場場險勝；不讓他敗走（_rout 回空的：不扣聲威、不閉門不見），同一位連打得下去。回最後一場的話。"""
    p = game.state.player
    msgs = []
    with mock.patch.object(team, "fight", return_value=_won()), mock.patch.object(Game, "_rout", return_value=[]):
        for _ in range(times):
            p.snubbed_until.clear()
            p.stamina = 250.0
            msgs = game.choose("act:challenge:sunjian")
    return msgs


def test_the_third_win_over_sun_jian_lets_you_seize_his_spear(world):
    game = _sun_challenger(world)
    p = game.state.player
    assert "act:challenge:sunjian" in {o.id for o in game.options(odds=False) if o.enabled}
    _beat_sun(game, 2)
    assert p.figure_wins == {"sunjian": 2} and signature_arms.owned(p) == []
    msgs = _beat_sun(game, 1)
    [arm] = signature_arms.owned(p)
    assert (arm.name, arm.kind, arm.signature) == ("江潮槍", "槍", "sunjian")
    assert signature_arms.SEIZE_LINE.format(general="孫堅", arm="江潮槍") in msgs
    assert signature_arms.GAIN_LINE.format(name="江潮槍") in game.state.battles[0].materials  # 這一場戰報的「得失」
    assert world.get_season().signature_arms == {"sunjian": SignatureClaim(owner="黃甲", via="seized")}


def test_losses_do_not_count_and_a_later_winner_gets_nothing(world):
    first = _sun_challenger(world, "黃甲")
    lost = EncounterResult(tier="落敗", margin=-80, our_power=50, difficulty=120)
    with mock.patch.object(team, "fight", return_value=lost):
        first.choose("act:challenge:sunjian")
    assert first.state.player.figure_wins == {}  # 只算大勝、險勝
    _beat_sun(first, 3)
    second = _sun_challenger(world, "黃乙")
    _beat_sun(second, 3)
    assert second.state.player.figure_wins == {"sunjian": 3} and signature_arms.owned(second.state.player) == []  # 每季全服一人


def test_a_crippled_figure_gives_nothing_unless_this_fight_put_him_out(world):
    """孫堅退場或重創，兩條路都沒了（「要 PM 定的」第 3 條）；把他打到重創的那一場（beaten）例外照給。"""
    game = _sun_challenger(world)
    s, c = game.state, game.content
    s.player.figure_wins["sunjian"] = 3
    s.world.figures["sunjian"] = FigureState(status="crippled")
    assert signature_arms.due(s, c) == ([], []) and s.world.signature_arms == {}
    items, _ = signature_arms.due(s, c, beaten="sunjian")
    assert [i.signature for i in items] == ["sunjian"] and s.world.signature_arms["sunjian"].via == "seized"


def test_the_signature_arm_rolls_no_dice(world, tmp_path):
    from tianxia.sqlite_world import open_world
    draws = []
    for table, store in ((True, world), (False, open_world(tmp_path / "off.db"))):
        game = _sun_challenger(store)
        if not table:
            game.content.gear.signature_arms = []
        _beat_sun(game, 3)
        assert bool(signature_arms.owned(game.state.player)) == table
        draws.append(game.rng.random())
    assert draws[0] == draws[1]  # 不擲骰（FB-129）：給不給，Game.rng 接下來的序列都一樣


def test_the_win_path_only_exists_where_challenges_do(world):
    """挑戰本人每季都有（《挑戰大勢人物每季都有》，figures.challenge_on）：散人沒有挑戰鈕，也就走不到打贏三次；第一季規則關著的季
    （14 天）也有孫堅的挑戰鈕；主機的緊急開關（figure_challenge_every_season）關著時，第一季以外沒有。計數在 _challenge。"""
    game = _sun_challenger(world)
    game.state.player.faction = None
    assert not any(o.id.startswith("act:challenge:") for o in game.options(odds=False))
    game.state.player.faction = "huang"
    game.content.config.season_one = False
    assert "act:challenge:sunjian" in [o.id for o in game.options(odds=False)]
    game.content.config.figure_challenge_every_season = False
    assert not any(o.id.startswith("act:challenge:") for o in game.options(odds=False))


def test_the_fight_that_cripples_him_still_hands_over_the_spear(world):
    """真的走 _rout：第三次打贏把他的聲威打到 0 重創了，這一場照給（beaten）。"""
    game = _sun_challenger(world)
    s, p = game.state, game.state.player
    p.figure_wins["sunjian"] = 2
    figures_now = figures.state_of(s, game.content, "sunjian")
    s.world.figures["sunjian"] = figures_now
    figures_now.prestige = 1
    with mock.patch.object(team, "fight", return_value=_won()):
        msgs = game.choose("act:challenge:sunjian")
    assert figures.is_out(s, "sunjian")  # 他真的被打到重創了
    assert [a.signature for a in signature_arms.owned(p)] == ["sunjian"] and p.figure_wins["sunjian"] == 3
    assert signature_arms.SEIZE_LINE.format(general="孫堅", arm="江潮槍") in msgs
    assert world.get_season().signature_arms["sunjian"].via == "seized"


# ── Task 5：神器譜 ──

def test_signature_arms_join_the_divine_book_across_seasons(content, world):
    _arms(content)
    game = _game(content, world, "甲客")
    season = world.get_season_number()
    old = WorldState(signature_arms={"mate": SignatureClaim(owner="丙", via="seized")})
    with world.db.transaction() as conn:  # 上一季：每一季的 WorldState 照季留在 seasons 表（換季不刪）
        conn.execute("INSERT INTO seasons (number, data) VALUES (?, ?)", (season - 1, old.model_dump_json()))
    assert world.signature_records() == [(season - 1, {"mate": SignatureClaim(owner="丙", via="seized")})]  # 這一季還沒給，不列
    game.state.player.affinities["mate"] = 80
    idle_step(game)
    assert [n for n, _ in world.signature_records()] == [season - 1, season]
    lines = [f"{r['season']} {r['name']} {r['text']}" for r in game.divine_book_view() if "鐵脊長刀" in r["name"]]  # 榜單的神器譜
    assert len(lines) == 2  # 沒有打出來的神器也列
    assert "甲客" in lines[0] and signature_arms.HOW["gift"] in lines[0] and "韓鐵" in lines[0]  # 新的一季在前
    assert "丙" in lines[1] and signature_arms.HOW["seized"] in lines[1]


def test_no_divine_items_and_no_arms_means_no_book(content, world):
    game = _game(_arms(content), world)
    assert forge_secrets.DIVINE_BOOK not in game.chronicle_text() and game.divine_book_view() == []
    assert forge_secrets.divine_book([], []) == ""


def test_the_book_sorts_by_season_with_divine_items_first_and_skips_arms_the_content_dropped(content):
    """divine_book 併進本命兵器：照季排，同一季打出來的神器在前；內容拿掉了的那一把不寫（book_rows）。"""
    _arms(content)
    find = GearFind(secret="t_star", slot="weapon", kind="劍", attribute="快", tier=3, title="暫名", divine=True,
                    owner="乙", master_shown="乙", divine_name="流星")
    rows = signature_arms.book_rows(content, [
        (2, {"mate": SignatureClaim(owner="丙", via="gift"), "ghost": SignatureClaim(owner="丁", via="gift")}),
        (4, {"mate": SignatureClaim(owner="戊", via="seized")}),
    ])
    assert [season for season, _ in rows] == [2, 4]  # 內容裡沒有的 ghost 不寫
    book = forge_secrets.divine_book([(2, find), (3, find)], rows)
    lines = book.splitlines()[2:]
    assert [line.split("　")[0] for line in lines] == ["- 第 2 季", "- 第 2 季", "- 第 3 季", "- 第 4 季"]
    assert "流星" in lines[0] and "鐵脊長刀" in lines[1] and "鐵脊長刀" in lines[3]  # 同一季：神器在前，本命兵器在後
    assert forge_secrets.divine_book([], rows).startswith(forge_secrets.DIVINE_BOOK)  # 只有本命兵器也有這一段


def test_only_the_beaten_generals_arm_goes_into_that_fights_report_and_its_annal_comes_after_the_fight(world):
    """終審（minor）：同一下動作裡另一位名將的情誼也到了，兩把都給，可是只有被打敗的孫堅那一把寫進這一場戰報的「得失」；
    行狀照時間先後：先「挑戰孫堅本人」那一筆，再「奪走了他的本命兵器」。"""
    game = _sun_challenger(world)
    game.content.config.biography.enabled = True
    p = game.state.player
    _beat_sun(game, 2)
    p.affinities["caocao"] = 80
    _beat_sun(game, 1)
    assert sorted(arm.name for arm in signature_arms.owned(p)) == sorted(["江潮槍", "梟風槍"])
    gains = [m for m in game.state.battles[0].materials if m.startswith("本命兵器")]
    assert gains == [signature_arms.GAIN_LINE.format(name="江潮槍")]
    texts = [e.text for e in p.annals]
    fight = max(i for i, t in enumerate(texts) if t.startswith("挑戰孫堅本人"))
    seized = texts.index(signature_arms.ANNAL_SEIZED.format(general="孫堅", arm="江潮槍"))
    assert fight < seized
