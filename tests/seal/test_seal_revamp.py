"""玉璽碎片改版第 1 批（docs/superpowers/specs/2026-10-21-玉璽碎片改版-design.md；計畫 docs/superpowers/plans/2026-10-21-玉璽碎片改版-1.md）：
子開關 Config.seal.revamp、七片的常駐效果（戰力 ×1.10＋照部位的成長或生活）、奪璽單挑與江湖水漲不吃戰力。持有者藏起來在
test_seal_revamp_hidden.py。舊的七個效果（開關關著）照 test_seal.py。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from test_seal import put_shards, seal_problems, sealed  # noqa: F401  sealed 是夾具
from tianxia import seal, treasures

REVAMP = {  # 設計第三章：每片的常駐成長或生活效果鍵（戰力 ×1.10 每片都有，不在這裡）
    "chishou": ["injury"], "xuanniu": ["talk_turns", "audience"], "yunzhuan": ["practice"], "jinjiao": ["keep_silver"],
    "chenglu": ["stamina_regen"], "chizhang": ["fuse_points"], "guixin": ["mate_exp", "chuangong"],
}
NUMBERS = {  # 設計第三章的【預設】
    "injury": 0.5, "talk_turns": 2, "audience": 5, "practice": 0.75, "keep_silver": 1,
    "stamina_regen": 1.25, "fuse_points": 10, "mate_exp": 1.25, "chuangong": 0.9,
}


def revamp(content):
    """測試內容裝上七片、打開改版（put_shards 預設關著改版，舊測試照舊規則）。"""
    put_shards(content)
    for sid, keys in REVAMP.items():
        content.seal[sid].effects = list(keys)
    content.config.seal.revamp.enabled = True
    return content


def holding(content, world, shard="chishou", name="懷璽", now=0.0):
    """把 shard 記在 name 名下（since_season 0），回傳他的 Game（同步過：抄本照登記抄好）。"""
    from tianxia.engine import Game

    def _give(st):
        reg = seal.filled(st.seal, content)
        reg.shards[shard].state, reg.shards[shard].holder, reg.shards[shard].since_season = "held", name, 0

    world.mutate(_give)
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.sync(now)
    return game


# ── Task 1：子開關、內容 ──

@pytest.mark.slow
def test_the_real_content_gives_each_shard_its_revamp_effects():
    """七片的常駐效果鍵照設計第三章；數字是【預設】；子開關預設開（PM 五之一 6）；戰力 ×1.10。"""
    c = real_content()
    assert {sid: list(s.effects) for sid, s in c.seal.items()} == REVAMP
    cfg = c.config.seal.revamp
    assert cfg.enabled and cfg.power == pytest.approx(1.10)
    assert cfg.effects == pytest.approx(NUMBERS)
    assert seal.revamp_on(c) and treasures.revamp_on(c)
    for profile in ("week7", "season21"):
        assert seal.revamp_on(real_content(profile))


def test_the_switch_needs_the_seal_and_its_own_flag(content):
    put_shards(content)
    assert not seal.revamp_on(content)  # put_shards 關著改版（舊測試照舊規則）
    revamp(content)
    assert seal.revamp_on(content) and treasures.revamp_on(content)
    content.config.seal.enabled = False  # 主機的緊急開關：碎片整個關著，改版也不算
    assert not seal.revamp_on(content) and not treasures.revamp_on(content)


def test_an_unknown_revamp_effect_is_refused_at_load(sealed):
    assert seal_problems(sealed) == []
    sealed.seal["guixin"].effects = ["mate_exp", "沒有這一種"]
    assert any("沒有這一種" in problem and "revamp" in problem for problem in seal_problems(sealed)), seal_problems(sealed)


# ── Task 2：常駐效果走傳承那一格、說明句 ──

@pytest.mark.parametrize(("shard", "key", "value"), [
    ("chishou", "injury", 0.5), ("xuanniu", "talk_turns", 2), ("xuanniu", "audience", 5), ("yunzhuan", "practice", 0.75),
    ("jinjiao", "keep_silver", 1), ("chenglu", "stamina_regen", 1.25), ("chizhang", "fuse_points", 10),
    ("guixin", "mate_exp", 1.25), ("guixin", "chuangong", 0.9),
])
def test_each_shard_feeds_its_revamp_numbers_into_the_hooks(content, world, shard, key, value):
    """傳承那一格照改版的效果鍵與 Config.seal.revamp.effects（設計第三章）；一片兩個效果的（玄紐、歸心）兩個都給。"""
    revamp(content)
    game = holding(content, world, shard)
    assert treasures.amount(game.state, content, key) == pytest.approx(value)
    content.config.seal.revamp.effects[key] = 7  # 數字照 Config 讀，不寫死
    assert treasures.amount(game.state, content, key) == pytest.approx(7)


def test_chishou_and_jinjiao_drop_their_old_effects(content, world):
    """螭首不再加氣血上限（取代「氣血上限 ×1.06」）、金角不再加閃避（取代「落敗閃成僵持 +3%」，那一條算戰力，拿掉）。"""
    from tianxia import team

    revamp(content)
    chishou = holding(content, world, "chishou")
    assert treasures.amount(chishou.state, content, "hp_cap") == 1.0 and chishou.state.player.member.cap_scale == 1.0
    jinjiao = holding(content, world, "jinjiao", name="金角客")
    jinjiao.state.player.stats["agi"] = 5
    assert team.dodge_chance(jinjiao.state, content) == 0.0


@pytest.mark.smoke
def test_the_talk_cap_and_stamina_regen_take_the_bigger_numbers(content, world):
    from tianxia.engine import Game

    revamp(content)
    xuanniu = holding(content, world, "xuanniu")
    assert xuanniu._talk_cap() == content.config.talk_turns_per_day + 2
    plain = Game.new(content, "平人", rng=random.Random(0), world=world)
    plain.sync(0.0)
    chenglu = holding(content, world, "chenglu", name="承露客")
    plain.state.player.stamina = chenglu.state.player.stamina = 0.0
    later = content.config.stamina_regen_seconds * 10 / content.config.time_scale
    plain.sync(later)
    chenglu.sync(later)
    assert chenglu.state.player.stamina == pytest.approx(plain.state.player.stamina * 1.25)


def test_switched_off_the_shards_keep_their_old_effects(content, world):
    """子開關關著：舊的七個效果與數字（Config.seal.effects）一個都不變，新的鍵是中性值、沒有戰力倍數。"""
    revamp(content)
    content.config.seal.revamp.enabled = False
    old = {"chishou": ("hp_cap", 1.06), "xuanniu": ("talk_turns", 1), "jinjiao": ("dodge", 0.03), "guixin": ("mate_exp", 1.1)}
    for i, (sid, (key, value)) in enumerate(old.items()):
        game = holding(content, world, sid, name=f"舊{i}")
        assert treasures.amount(game.state, content, key) == pytest.approx(value)
        assert treasures.power_scale(game.state, content) == 1.0
        for new_key in ("injury", "audience", "keep_silver", "chuangong"):
            assert treasures.amount(game.state, content, new_key) == (1.0 if new_key in treasures.MULTIPLY else 0.0)


@pytest.mark.smoke
def test_only_the_holder_gets_the_power_scale(content, world):
    from tianxia.engine import Game

    revamp(content)
    game = holding(content, world, "yunzhuan")
    assert treasures.power_scale(game.state, content) == pytest.approx(1.10)
    other = Game.new(content, "旁人", rng=random.Random(0), world=world)
    other.sync(0.0)
    assert treasures.power_scale(other.state, content) == 1.0


def test_the_heirloom_row_and_card_say_power_and_every_effect(content, world):
    """傳承那一列、角色卡、碎片卡（只給自己看）寫「戰力 ×1.1、…」（待 joy 潤）；一片兩個效果照 content/seal.json 的順序接。關著照舊一句。"""
    revamp(content)
    game = holding(content, world, "xuanniu")
    text = "戰力 ×1.1、每位人物每日多談 2 輪、求見門檻 −5"
    assert seal.shard_text(content, "xuanniu") == text
    assert treasures.rows(game.state, content)["heirloom"]["effect_text"] == text
    assert f"【玄紐】{text}" in treasures.card_line(game.state, content)
    assert game.seal_view()["effect_text"] == text
    assert seal.shard_text(content, "jinjiao") == "戰力 ×1.1、落敗不失銀兩"
    content.config.seal.revamp.enabled = False
    assert seal.shard_text(content, "xuanniu") == "每位人物每日多談 1 輪"
    assert treasures.rows(game.state, content)["heirloom"]["effect_text"] == "每位人物每日多談 1 輪"


def test_got_and_assigned_lines_name_the_revamp_effects(content, world):
    """拿到碎片那一句（現世、管理者指定）照改版的說明寫（自己的江湖紀錄）。"""
    revamp(content)
    content.config.admins = ["管理"]
    from tianxia.engine import Game

    admin = Game.new(content, "管理", rng=random.Random(0), world=world)
    admin.sync(0.0)
    admin.admin_seal_assign("chenglu", "懷璽")
    game = Game.new(content, "懷璽", rng=random.Random(0), world=world)
    game.sync(1.0)
    lines = [line for e in game.state.journal if e.title == seal.SEAL_TITLE for line in [e.tag, *e.lines]]
    assert any("戰力 ×1.1、體力回復 ×1.25" in line for line in lines), lines


def test_chizhang_adds_ten_to_the_self_made_intent(content, world):
    """合 develop（武學重構）時 PM 2026-10-21 定：合成不再擲品質，赤璋改版開著時改成「自創的意分 +10」（create.seal_points，
    底子威力的倍數照它推）；子開關關著照 main 的 +5（test_seal.py）。說明句跟著寫自創的意分。"""
    from tianxia import create

    revamp(content)
    game = holding(content, world, "chizhang")
    assert create.seal_points(game.state, content) == 10
    assert seal.shard_text(content, "chizhang") == "戰力 ×1.1、自創的意分 +10"
    content.config.seal.revamp.enabled = False
    assert create.seal_points(game.state, content) == 5
    assert seal.shard_text(content, "chizhang") == "自創的意分 +5"


# ── Task 3：新的掛點（螭首、金角、歸心的傳功、玄紐的求見）──

def _two(content, world, shard):
    """持有 shard 的「懷璽」與一樣新的「平人」（都同步過、都學了拳腳，威力一樣）。"""
    from tianxia import rules
    from tianxia.engine import Game

    game = holding(content, world, shard)
    plain = Game.new(content, "平人", rng=random.Random(0), world=world)
    plain.sync(0.0)
    for g in (game, plain):
        g.client = None
        rules.learn_skill(g.state, content, "fist")
    return game, plain


def _lost():
    from tianxia import encounter

    return encounter.EncounterResult(tier="落敗", margin=-50, our_power=10, difficulty=20)


def test_chishou_halves_the_injury_of_an_ordinary_fight(content, world):
    """螭首：一場仗（遊歷、出陣、探索野怪、挑戰本人都走 take_encounter_toll）變成內傷的減半；掉的氣血照舊。"""
    from tianxia import team

    revamp(content)
    game, plain = _two(content, world, "chishou")
    team.take_encounter_toll(game.state, content, world, "落敗")
    team.take_encounter_toll(plain.state, content, world, "落敗")
    assert plain.state.player.member.injury > 0
    assert game.state.player.member.injury == pytest.approx(plain.state.player.member.injury * 0.5)
    assert game.state.player.member.neili == pytest.approx(plain.state.player.member.neili)
    content.config.seal.revamp.enabled = False  # 關著照舊
    before = game.state.player.member.injury
    team.take_encounter_toll(game.state, content, world, "落敗")
    assert game.state.player.member.injury - before > plain.state.player.member.injury * 0.5 + 1e-9


def test_chishou_halves_the_injury_of_a_boss_fight(content, world):
    """頭目戰收場：池子掉的氣血扣回本人時，變成內傷的那一份減半（Game._duel_finish）。"""
    from test_duel import _boss

    revamp(content)
    content.duels = {"lake_boss": _boss()}
    content.config.train_event_chance = 0.0
    hurt = []
    for game in _two(content, world, "chishou"):
        game.state.player.location = "lake"
        game._duel_start(content.duels["lake_boss"])
        duel = game.state.player.duel
        duel.hp = duel.hp_start - 40
        game._duel_finish("落敗", "（測試）")
        hurt.append(game.state.player.member.injury)
    assert hurt[1] > 0 and hurt[0] == pytest.approx(hurt[1] * 0.5)


def test_a_hired_killer_leaves_one_hp_with_or_without_chishou(content, world):
    """酒肆買兇的殺手打贏那一場：氣血只剩 1，不加內傷（企劃者 2026-10-27「上線回來時氣血只剩 1 點」；以前扣上限一成半、
    其中變內傷的螭首減半，現在沒有內傷可減，帶不帶螭首一樣）。"""
    from unittest import mock

    from tianxia import encounter
    from tianxia.state import TavernHit

    revamp(content)
    hurt = []
    for game in _two(content, world, "chishou"):
        hit = TavernHit(id=1, client="雇主", target=game.state.player.name, tier=0, price=10, place="town", placed_real=0.0,
                        until_real=1e12)
        with mock.patch.object(encounter, "resolve_encounter", return_value=_lost()):
            game._tavern_hit_fight(hit, random.Random(0))
        hurt.append((game.state.player.member.injury, game.state.player.member.neili))
    assert hurt[0] == hurt[1] == (0.0, 1.0)


def test_jinjiao_keeps_the_silver_when_you_lose(content, world):
    """金角：落敗不失銀兩（只管 Game._lose_silver：遊歷、出陣、探索野怪、挑戰本人，PM 五之一 3）；戰報與紀錄寫一句（待 joy 潤）。
    沒有銀兩可丟時不寫；關著照舊失落一成。"""
    from types import SimpleNamespace

    from tianxia import treasures as tr

    revamp(content)
    game, plain = _two(content, world, "jinjiao")
    for g in (game, plain):
        g.state.player.stats["silver"] = 100
    record, other = SimpleNamespace(id=1, notes=[], silver=0), SimpleNamespace(id=1, notes=[], silver=0)
    line = tr.KEEP_SILVER.format(shard="金角")
    assert game._lose_silver(record) == [line] and record.notes == [line] and record.silver == 0
    assert game.state.player.stats["silver"] == 100
    assert plain._lose_silver(other) == ["銀兩 -10"] and plain.state.player.stats["silver"] == 90
    game.state.player.stats["silver"] = 5  # 一成是 0：本來就不丟，不寫那一句
    assert game._lose_silver(SimpleNamespace(id=2, notes=[], silver=0)) == []
    game.state.player.stats["silver"] = 100
    content.config.seal.revamp.enabled = False
    assert game._lose_silver(SimpleNamespace(id=3, notes=[], silver=0)) == ["銀兩 -10"]


def test_guixin_discounts_every_chuangong_lesson(content, world):
    """歸心：傳功的心得 ×0.9（照 round、最少 1，同雲篆的練成）；鈕上寫的跟扣的是同一個數。"""
    from test_chuangong import _with_mate

    from tianxia import chuangong

    revamp(content)
    game, plain = _two(content, world, "guixin")
    rule = content.config.chuangong
    for g in (plain, game):  # 同一位同伴輪流歸兩人名下（_with_mate 改 owner）：最後歸懷璽
        _with_mate(g)
        mine = {row["what"]: row for row in g.chuangong_lessons("mate")}
        scale = 0.9 if g is game else 1.0
        assert mine["wugong"]["label"].endswith(f"{max(1, round(rule.mate_art_xinde * scale))} 心得")
        assert mine["str"]["label"].endswith(f"{max(1, round(rule.mate_stat_xinde * scale))} 心得")
    before = game.state.player.stats["xinde"]
    game.chuangong("mate", "wugong")
    assert before - game.state.player.stats["xinde"] == max(1, round(rule.mate_art_xinde * 0.9))
    assert chuangong.price_of(game.state, content, 1) == 1 and chuangong.price_of(game.state, content, 100) == 90
    assert chuangong.price_of(plain.state, content, 100) == 100


def test_xuanniu_cuts_the_audience_bar_as_its_own_line(content, world):
    """玄紐：求見門檻 −5，在折抵裡另列一項、寫碎片的名字（不跟寶物併成一項、不寫成寶物的名字）。"""
    from tianxia import rules

    revamp(content)
    content.characters["mate"].audience_fame = 20
    game, plain = _two(content, world, "xuanniu")
    mine, theirs = rules.audience_parts(game.state, content, "mate"), rules.audience_parts(plain.state, content, "mate")
    assert mine.bar == theirs.bar == 20 and theirs.discounts == []
    assert mine.discounts == [("玄紐", 5)]
    assert rules.audience_bar(game.state, content, "mate") == 15
    content.config.seal.revamp.enabled = False
    assert rules.audience_parts(game.state, content, "mate").discounts == []


# ── Task 4：戰力 ×1.10；奪璽單挑、江湖水漲不吃 ──

def test_the_holder_is_ten_percent_stronger_in_every_fight(content, world):
    """戰力乘在本人的 Boost.factor（team.player_boost）：一般的仗（power_vs）、決戰與頭目戰、擂台、截殺的快照（_battle_power）都吃；
    seal=False 是不含碎片的那一份；開關關著一樣強。"""
    from tianxia import team

    revamp(content)
    game, plain = _two(content, world, "yunzhuan")
    assert plain._battle_power() > 0
    assert game._battle_power() == pytest.approx(plain._battle_power() * 1.10)
    assert game._battle_power(seal=False) == pytest.approx(plain._battle_power())
    assert game._battle_scores()["強攻"] > plain._battle_scores()["強攻"]
    assert game._battle_scores(seal=False) == plain._battle_scores()
    squad = next(iter(content.squads.values()))
    ours, theirs = (team.power_vs(g.state, content, world, squad) for g in (game, plain))
    assert ours == pytest.approx(theirs * 1.10)
    assert team.power_vs(game.state, content, world, squad, seal=False) == pytest.approx(theirs)
    content.config.seal.revamp.enabled = False
    assert game._battle_power() == pytest.approx(plain._battle_power())


def test_companions_do_not_take_the_power(content, world):
    from test_chuangong import _with_mate

    from tianxia import team

    revamp(content)
    game, _ = _two(content, world, "yunzhuan")
    _with_mate(game)
    boosts, bare = team.team_boosts(game.state, content, world), team.team_boosts(game.state, content, world, seal=False)
    assert len(boosts) == 2
    assert boosts[0].factor == pytest.approx(bare[0].factor * 1.10)
    assert boosts[1] == bare[1]  # 同伴照舊


def test_joining_a_battle_snapshots_a_bare_copy_for_the_duel(content, world):
    """決戰加入時的份量快照照吃戰力；另外快照一份不含碎片的（seal_bare，只在有碎片時記），奪璽單挑的快照用它，跟沒碎片時一樣。
    沒碎片的人那一包標記一個字不變（沒有 seal_bare 這個鍵）。"""
    from tianxia import battle_instance, seal_duel
    from tianxia.battle_instance import BattleInstance

    revamp(content)
    game, plain = _two(content, world, "yunzhuan")
    marks = game._battle_marks()
    assert "seal_bare" not in plain._battle_marks()
    assert marks["seal_bare"].power == pytest.approx(plain._battle_power())
    assert marks["seal_bare"].scores == plain._battle_scores()
    b = BattleInstance(battle_id="changshe_fire")
    battle_instance.join_faction(b, "懷璽", "guan", 300.0, game._battle_power(), scores=game._battle_scores(), **marks)
    battle_instance.join_faction(b, "平人", "guan", 300.0, plain._battle_power(), scores=plain._battle_scores(), **plain._battle_marks())
    holder, other = b.participants["懷璽"], b.participants["平人"]
    assert holder.power == pytest.approx(other.power * 1.10) and holder.scores["強攻"] > other.scores["強攻"]
    mine, theirs = seal_duel.side_from_participant(holder, "guan"), seal_duel.side_from_participant(other, "guan")
    assert mine.power == pytest.approx(theirs.power) and mine.scores == theirs.scores


def test_a_holder_off_the_field_duels_without_the_power(content, world):
    """沒參戰的持有者（Game._seal_side_of）現算的那一份照不含碎片的。"""
    revamp(content)
    game, plain = _two(content, world, "yunzhuan")
    side = game._seal_side_of("懷璽")
    assert side.power == pytest.approx(plain._battle_power())
    assert side.scores == plain._battle_scores(mounted=False)


def test_rising_difficulty_floats_on_the_power_without_the_shard(content, world):
    """江湖水漲（PM 五之一 2）：劇情大場面與頭目戰的浮動難度照不含碎片的威力算——跟沒碎片的人一樣難，打起來強一成。"""
    from test_duel import _boss

    from tianxia.models import Squad

    revamp(content)
    content.config.rise.enabled = True
    content.config.train_event_chance = 0.0
    content.duels = {"lake_boss": _boss(difficulty=1)}
    game, plain = _two(content, world, "yunzhuan")
    big = Squad(id="試頭目", name="試頭目", difficulty=1, boss=True)
    for g in (game, plain):
        g.state.player.tutorial_step = len(content.tutorial.steps)
    assert plain._story_squad(big).difficulty > 1
    assert game._story_squad(big).difficulty == pytest.approx(plain._story_squad(big).difficulty)
    seen = []
    for g in (game, plain):
        g.state.player.location = "lake"
        g._duel_start(content.duels["lake_boss"])
        seen.append((g.state.player.duel.difficulty, g.state.player.duel.power))
    assert seen[0][0] == pytest.approx(seen[1][0]) and seen[0][1] == pytest.approx(seen[1][1] * 1.10)


def test_a_hired_killer_scales_off_the_power_without_the_shard(content, world):
    """酒肆買兇的殺手照被找的人自己的威力浮上來（同江湖水漲）：照不含碎片的那一份浮，打起來照含的。"""
    from unittest import mock

    from tianxia import encounter
    from tianxia.state import TavernHit

    revamp(content)
    seen = []

    def spy(power, difficulty, rng, *args, **kwargs):
        seen.append((power, difficulty))
        return _lost()

    for game in _two(content, world, "yunzhuan"):
        hit = TavernHit(id=1, client="雇主", target=game.state.player.name, tier=0, price=10, place="town", placed_real=0.0,
                        until_real=1e12)
        with mock.patch.object(encounter, "resolve_encounter", side_effect=spy):
            game._tavern_hit_fight(hit, random.Random(0))
    assert seen[0][1] == pytest.approx(seen[1][1]) and seen[0][0] == pytest.approx(seen[1][0] * 1.10)


@pytest.mark.slow
def test_a_figure_challenge_floats_on_the_power_without_the_shard(world):
    """挑戰大勢人物本人（大場面，rise.big 照 figure_wins）：同一個人有碎片、沒碎片，浮上來的難度一樣；勝算的威力照含碎片的。"""
    from test_rise import _player

    from tianxia import figures, team

    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.terrain_arts.enabled = False

    def _give(st):
        reg = seal.filled(st.seal, c)
        reg.shards["chishou"].state, reg.shards["chishou"].holder, reg.shards["chishou"].since_season = "held", "官甲", 0

    world.mutate(_give)
    game = _player(c, world, mates=("guanyu", "zhangfei"))
    assert game.state.player.heirloom is not None
    base = figures.squad_of(game.state, c, "bocai")
    risen = game._figure_squad("bocai").difficulty
    full = team.power_vs(game.state, c, world, base, fresh=True, terrain=False)
    bare = team.power_vs(game.state, c, world, base, fresh=True, terrain=False, seal=False)
    assert full > bare and risen == pytest.approx(bare * c.config.rise.big_scale, abs=0.1)
    game.state.player.heirloom = None
    assert game._figure_squad("bocai").difficulty == pytest.approx(risen)
