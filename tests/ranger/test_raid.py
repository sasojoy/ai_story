"""截殺（Config.raid；企劃者 2026-10-08 在決策卡選「有限制地開」）：只有敵對陣營的兩個人之間、不必對方同意；
新手期與城鎮類地點不能打、同一個目標有冷卻、被截殺過的人一陣子之內誰都不能再截殺他；輸的一方失一點銀兩與氣血，贏的拿走一部分。

兩個角色開在同一個資料庫；每一個動作照伺服器的做法先從資料庫重讀自己（server._locked），做完存回去。"""
from __future__ import annotations

import math
import random

import pytest

from conftest import install_season_one
from tianxia import calendar, encounter, roster, rules, social, team
from tianxia.characters import CharacterStore
from tianxia.engine import CLASH_OPEN, CLASH_THEIRS_WON, CLASH_WON, Game
from tianxia.models import FactionDef
from tianxia.state import BotProfile

NOW = 1000.0


def _seat(content, world):
    content.config.auto_open_first_season = True
    content.config.newbie_days = -1  # 測試不等新手期過去；新手期另外測
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾", join_at=["lake"]),
    ]
    for name, faction in (("甲", "guan"), ("乙", "huang")):
        game = Game.new(content, name, rng=random.Random(0), world=world)
        game.client = None
        rules.learn_skill(game.state, content, "fist")
        game.state.player.faction = faction
        game.state.player.location = "lake"  # 湖畔不是城鎮類
        game.state.player.stamina = 100.0
        game.state.player.stats["silver"] = 200
        game.sync(NOW)
        CharacterStore(world.db).save(game.state)
    return content, world


@pytest.fixture
def pair(content, world):
    """第一季（install_season_one）：官軍的甲、黃巾的乙，都在湖畔。"""
    install_season_one(content)
    return _seat(content, world)


@pytest.fixture
def beta_pair(content, world):
    """第一季規則關著的季（不叫 install_season_one，season_one 維持 False）：截殺每季都有（懸賞榜設計 2.2 第 3 點）。其餘同 pair。"""
    return _seat(content, world)


def _do(content, world, name, act, rng=None):
    state = CharacterStore(world.db).load(name)
    game = Game(content, state, rng or random.Random(0), world)
    game.client = None
    game.sync(NOW)
    msgs = act(game)
    game._save_season()
    CharacterStore(world.db).save(game.state)
    return msgs, game


def _load(world, name):
    return CharacterStore(world.db).load(name)


def _raid_buttons(content, world, name, other):
    card = _do(content, world, name, lambda g: g.peer_card(other))[0]
    return [b for b in card["actions"] if b["action"] == "raid"]


def _raid(content, world, rng=None, tier=None, monkeypatch=None):
    if tier is not None:
        real = encounter.resolve_encounter
        monkeypatch.setattr(encounter, "resolve_encounter", lambda ours, theirs, rng, *a, **k: real(ours, theirs, rng).model_copy(
            update={"tier": tier}))
    return _do(content, world, "甲", lambda g: g.peer_act("乙", "raid"), rng)


def test_the_button_shows_only_between_enemy_factions(pair):
    content, world = pair
    [button] = _raid_buttons(content, world, "甲", "乙")
    assert button["enabled"] and "體力 10" in button["note"] and "勝算" in button["note"] and button["confirm"]
    for mine, theirs in (("guan", "guan"), (None, "huang"), ("guan", None)):
        for name, faction in (("甲", mine), ("乙", theirs)):
            state = _load(world, name)
            state.player.faction = faction
            CharacterStore(world.db).save(state)
        assert _raid_buttons(content, world, "甲", "乙") == []  # 同陣營、散人：沒有這顆鈕
        assert _do(content, world, "甲", lambda g: g.peer_act("乙", "raid"))[0] == ["（此刻無法這麼做。）"]


def test_raids_happen_with_the_season_one_switch_off_without_contribution(beta_pair, monkeypatch):
    """截殺每季都有（企劃者 2026-10-10）；第一季規則關著的季沒有晉升，打贏不記貢獻，戰報與紀錄都不寫「貢獻」（懸賞榜設計 6.1）。"""
    content, world = beta_pair
    assert not world.get_season().season_one
    [button] = _raid_buttons(content, world, "甲", "乙")
    assert button["enabled"]
    assert [name for name, _ in _do(content, world, "甲", lambda g: g.raid_targets())[0]] == ["乙"]  # 假人也看得到（真人假人一樣）
    msgs, _ = _raid(content, world, tier="大勝", monkeypatch=monkeypatch)
    me, them = _load(world, "甲"), _load(world, "乙")
    assert me.player.contrib == 0 and not any("貢獻" in m for m in msgs)
    assert not any("貢獻" in line for line in me.battles[0].changes)
    assert them.player.stats["silver"] < 200 and me.player.stats["silver"] > 200  # 輸贏照舊


def test_the_raid_switch_off_has_no_raids(pair):
    """Config.raid.enabled（主機的緊急開關，懸賞榜設計 2.2 第 3 點）關著：沒有截殺鈕、按了也打不了、假人沒有對象。"""
    content, world = pair
    content.config.raid.enabled = False
    assert _raid_buttons(content, world, "甲", "乙") == []
    assert _do(content, world, "甲", lambda g: g.peer_act("乙", "raid"))[0] == ["（此刻無法這麼做。）"]
    assert _do(content, world, "甲", lambda g: g.raid_targets())[0] == []


@pytest.mark.parametrize("fixture", ["pair", "beta_pair"])
def test_the_raid_button_is_not_drawn_in_the_off_season_fb163(request, fixture):
    """FB-163：休季（這一季收了）卡上不畫「截殺」，跟通緝鈕、懸賞榜一樣（以前還畫著灰的，城裡寫「城裡耳目眾多」、城外寫「你此刻正忙」，
    原因都不對）。按了（直接打 API）也打不了、不扣體力不失銀兩；假人（raid_targets）沒有對象。下一季開了，同樣的兩個人又看得到。
    第一季規則開著的季與關著的季都一樣。"""
    content, world = request.getfixturevalue(fixture)
    assert [b["enabled"] for b in _raid_buttons(content, world, "甲", "乙")] == [True]  # 季還在跑
    world.mutate_season(lambda s: setattr(s, "ended", True))
    card = _do(content, world, "甲", lambda g: g.peer_card("乙"))[0]
    assert [b["action"] for b in card["actions"] if b["action"] in ("raid", "wanted")] == []  # 通緝鈕本來就收了，截殺鈕現在一樣
    state = _load(world, "甲")
    stamina, silver = state.player.stamina, state.player.stats["silver"]
    msgs, game = _do(content, world, "甲", lambda g: g.peer_act("乙", "raid"))
    assert msgs == ["（此刻無法這麼做。）"] and game.raid_shown(_do(content, world, "乙", lambda g: g)[1]) is False
    assert _do(content, world, "甲", lambda g: g.raid_targets())[0] == []
    after = _load(world, "甲")
    assert after.player.stamina >= stamina and after.player.stats["silver"] == silver and not after.battles
    world.mutate_season(lambda s: setattr(s, "ended", False))
    assert [b["enabled"] for b in _raid_buttons(content, world, "甲", "乙")] == [True]


def test_not_in_a_town_and_not_on_newcomers(pair):
    content, world = pair
    for name in ("甲", "乙"):
        state = _load(world, name)
        state.player.location = "town"
        CharacterStore(world.db).save(state)
    [button] = _raid_buttons(content, world, "甲", "乙")
    assert not button["enabled"] and "城裡" in button["note"]
    for name in ("甲", "乙"):
        state = _load(world, name)
        state.player.location = "lake"
        CharacterStore(world.db).save(state)
    content.config.newbie_days = 18
    [button] = _raid_buttons(content, world, "甲", "乙")
    assert not button["enabled"] and "新手期" in button["note"]
    before = _load(world, "乙").player.stats["silver"]
    assert "新手期" in _do(content, world, "甲", lambda g: g.peer_act("乙", "raid"))[0][0]
    assert _load(world, "乙").player.stats["silver"] == before


@pytest.mark.smoke
def test_a_late_comer_in_a_beta_season_is_protected_from_his_own_join_time(beta_pair):
    """第一季規則關著的季，截殺的新手期從各自加入的那一刻算（企劃者 2026-10-10，懸賞榜設計 14.1 丁）：季初就在的兩個人早就過了，
    很晚才來的人在自己的新手期內截殺不了別人、也不會被截殺；新手的體力、氣血福利照舊從季初算（roster.newbie 不動）。"""
    content, world = beta_pair
    content.config.newbie_days = 18
    newbie = content.config.newbie_days * 86400 / calendar.cal_scale(content, world.get_season())  # 新手期幾個世界秒（測試內容約 10 小時）
    world.mutate_season(lambda season: setattr(season, "time", 2 * newbie))
    game = Game.new(content, "丙", rng=random.Random(0), world=world)
    game.client = None
    rules.learn_skill(game.state, content, "fist")
    game.state.player.faction, game.state.player.location, game.state.player.stamina = "guan", "lake", 100.0
    game.sync(NOW)
    CharacterStore(world.db).save(game.state)
    late = _load(world, "丙")
    late.world = world.get_season()  # 角色存檔不含賽季：接上共用的那一份
    assert late.player.joined_at == pytest.approx(2 * newbie)
    assert roster.raid_newbie(late, content) and not roster.newbie(late, content)  # 福利照舊從季初算
    assert _raid_buttons(content, world, "甲", "乙")[0]["enabled"]  # 季初就在的兩個人
    [button] = _raid_buttons(content, world, "丙", "乙")
    assert not button["enabled"] and "你初入江湖" in button["note"]
    [button] = _raid_buttons(content, world, "乙", "丙")
    assert not button["enabled"] and "丙初入江湖" in button["note"]
    world.mutate_season(lambda season: setattr(season, "time", season.time + newbie + 60))
    assert _raid_buttons(content, world, "乙", "丙")[0]["enabled"]


@pytest.mark.parametrize("tier", ["大勝", "險勝"])
def test_the_winner_takes_part_of_the_losers_silver_and_the_loser_bleeds_a_little(pair, monkeypatch, tier):
    content, world = pair
    cfg = content.config.raid
    before = {n: _load(world, n).player for n in ("甲", "乙")}
    msgs, _ = _raid(content, world, tier=tier, monkeypatch=monkeypatch)
    after = {n: _load(world, n).player for n in ("甲", "乙")}
    lost = min(cfg.silver_cap, math.ceil(200 * cfg.silver_share))
    taken = math.ceil(lost * cfg.take_share)
    assert after["乙"].stats["silver"] == 200 - lost and after["甲"].stats["silver"] == 200 + taken
    assert after["甲"].stamina == pytest.approx(before["甲"].stamina - cfg.stamina, abs=0.5)
    assert after["乙"].stamina == pytest.approx(before["乙"].stamina, abs=0.5)  # 被截殺的人不花體力
    cap = team.neili_cap(content, after["乙"].member.level)
    assert after["乙"].member.neili == pytest.approx(cap * (1 - cfg.hp_loss), abs=1)
    assert after["乙"].member.injury == 0  # 不變成內傷
    assert after["甲"].member.neili is None  # 贏的不掉血
    contrib = content.config.contrib_per_push * cfg.win_contrib_push
    assert after["甲"].contrib == contrib and after["乙"].contrib == 0
    assert f"銀兩 +{taken}" in msgs and f"貢獻 +{contrib}" in msgs and "體力 -10" in msgs
    mine, theirs = _load(world, "甲"), _load(world, "乙")
    assert mine.battles[0].kind == theirs.battles[0].kind == "raid"
    assert mine.battles[0].opponent == "乙" and theirs.battles[0].opponent == "甲"
    assert theirs.battles[0].tier == "落敗" and theirs.battles[0].silver == -lost
    assert f"氣血 -{round(cap * cfg.hp_loss)}" in theirs.battles[0].changes
    assert theirs.journal[0].title == "遭甲截殺" and mine.journal[0].title == "截殺・乙"
    assert f"銀兩 -{lost}" in theirs.journal[0].changes


def _fights(world, name):
    return [e for e in _load(world, name).player.annals if e.kind == "fight"]


@pytest.mark.parametrize("tier", ["大勝", "落敗"])
def test_a_raid_notes_the_rivals_name_to_keep_on_both_sides(pair, monkeypatch, tier):
    """FB-9020：對手是玩家，名號帶「你」或阿拉伯數字時季末備援列傳不能改它；原句同時有代詞「你」與對手名號，所以行狀記 keep。兩邊各記自己的。"""
    content, world = pair
    content.config.biography.enabled = True
    _raid(content, world, tier=tier, monkeypatch=monkeypatch)
    (mine,), (theirs,) = _fights(world, "甲"), _fights(world, "乙")
    assert mine.keep == ["乙"] and "乙" in mine.text and "你" in mine.text
    assert theirs.keep == ["甲"] and "甲" in theirs.text and "你" in theirs.text


def test_a_melee_and_an_ambush_note_the_rivals_name_to_keep_too(pair):
    content, world = pair
    content.config.biography.enabled = True
    result = encounter.EncounterResult(tier="大勝", margin=50, our_power=200, difficulty=40)
    _, other = _do(content, world, "乙", lambda g: [])
    story = CLASH_OPEN.format(rival="乙", place="湖畔", side="官軍") + CLASH_WON.format(rival="乙")
    _, game = _do(content, world, "甲", lambda g: g._melee_record(result, "乙", 40.0, other, story, None))
    mine = [e for e in game.state.player.annals if e.kind == "fight"]
    assert [e.keep for e in mine] == [["乙"]] and mine[0].text.startswith("乙正在湖畔替官軍出力")
    theirs_story = CLASH_THEIRS_WON.format(rival="甲", place="湖畔", him="他")
    _, other3 = _do(content, world, "乙", lambda g: g._melee_record(result, "甲", 40.0, game, theirs_story, "遭甲撞上"))
    assert [e.keep for e in other3.state.player.annals if e.kind == "fight"][-1] == ["甲"]
    _, owner = _do(content, world, "甲", lambda g: g._ambush_record(result, "乙", 40.0, other, None, as_owner=True))
    _, passer = _do(content, world, "乙", lambda g: g._ambush_record(result, "甲", 40.0, game, None, as_owner=False))
    assert [e.keep for e in owner.state.player.annals if e.kind == "fight"][-1] == ["乙"]
    assert [e.keep for e in passer.state.player.annals if e.kind == "fight"][-1] == ["甲"]
    assert "乙" in [e for e in owner.state.player.annals if e.kind == "fight"][-1].text


def test_an_attacker_who_loses_pays_the_defender(pair, monkeypatch):
    content, world = pair
    _raid(content, world, tier="落敗", monkeypatch=monkeypatch)
    me, them = _load(world, "甲"), _load(world, "乙")
    assert me.player.stats["silver"] == 190 and them.player.stats["silver"] == 205
    assert them.player.contrib == content.config.contrib_per_push and me.player.contrib == 0
    assert me.battles[0].tier == "落敗" and them.battles[0].tier in team.WIN_TIERS
    assert any("反被你打退" in line for line in them.journal[0].lines)


def test_a_draw_costs_only_the_attackers_stamina(pair, monkeypatch):
    content, world = pair
    _raid(content, world, tier="僵持", monkeypatch=monkeypatch)
    me, them = _load(world, "甲"), _load(world, "乙")
    assert me.player.stats["silver"] == them.player.stats["silver"] == 200
    assert me.player.member.neili is None and them.player.member.neili is None
    assert me.player.contrib == them.player.contrib == 0


def test_the_silver_loss_is_a_share_with_a_cap_and_never_empties_a_purse(pair, monkeypatch):
    content, world = pair
    for purse, lost in ((1000, 15), (40, 2), (1, 1), (0, 0)):
        state = _load(world, "乙")
        state.player.stats["silver"] = purse
        CharacterStore(world.db).save(state)
        world.mutate_season(lambda season: (season.raids.clear(), season.raided.clear()))
        _raid(content, world, tier="大勝", monkeypatch=monkeypatch)
        monkeypatch.undo()
        assert _load(world, "乙").player.stats["silver"] == purse - lost


def test_cooldowns_for_the_same_target_and_for_anyone_after_a_raid(pair):
    content, world = pair
    cfg = content.config.raid
    _raid(content, world)
    [button] = _raid_buttons(content, world, "甲", "乙")
    assert not button["enabled"] and "不久前" in button["note"]
    # 第三個人（同陣營於甲）也不能馬上再截殺乙
    game = Game.new(content, "丙", rng=random.Random(0), world=world)
    game.client = None
    game.state.player.faction, game.state.player.location, game.state.player.stamina = "guan", "lake", 100.0
    game.sync(NOW)
    CharacterStore(world.db).save(game.state)
    [button] = _raid_buttons(content, world, "丙", "乙")
    assert not button["enabled"] and "剛被人截殺過" in button["note"]
    world.mutate_season(lambda season: setattr(season, "time", season.time + cfg.shield_seconds))
    assert _raid_buttons(content, world, "丙", "乙")[0]["enabled"]
    assert not _raid_buttons(content, world, "甲", "乙")[0]["enabled"]  # 甲對乙的冷卻比較長
    world.mutate_season(lambda season: setattr(season, "time", season.time + cfg.pair_cooldown_seconds))
    assert _raid_buttons(content, world, "甲", "乙")[0]["enabled"]


def test_the_attacker_needs_stamina_and_free_hands_but_the_target_does_not(pair):
    content, world = pair
    state = _load(world, "甲")
    state.player.stamina = 5.0
    CharacterStore(world.db).save(state)
    [button] = _raid_buttons(content, world, "甲", "乙")
    assert not button["enabled"] and "體力不夠" in button["note"]
    state = _load(world, "甲")
    state.player.stamina = 100.0
    CharacterStore(world.db).save(state)
    them = _load(world, "乙")
    them.player.stamina = 0.0  # 對方沒體力、在忙都照打：截殺不必他同意
    CharacterStore(world.db).save(them)
    assert _raid_buttons(content, world, "甲", "乙")[0]["enabled"]


def test_an_offline_target_still_on_the_list_gets_hit_and_reads_it_later(pair, monkeypatch):
    content, world = pair
    _raid(content, world, tier="大勝", monkeypatch=monkeypatch)
    them = _load(world, "乙")
    assert them.last_real == NOW  # 替他寫東西不補算他的時間：下了線的人不會一直掛在名單上
    assert them.journal[0].title == "遭甲截殺" and them.battle_card == them.battles[0].id


def test_no_word_reveals_a_bot(pair):
    content, world = pair
    seen = []
    for flag in (False, True):
        for name in ("甲", "乙"):
            state = _load(world, name)
            state.player.bot = BotProfile(personality="普通", seed=1, faction="huang") if flag and name == "乙" else None
            state.player.stats["silver"], state.player.stamina, state.player.contrib = 200, 100.0, 0
            state.player.member.neili, state.battles, state.battle_seq, state.journal = None, [], 0, []
            CharacterStore(world.db).save(state)
        world.mutate_season(lambda season: (season.raids.clear(), season.raided.clear()))
        button = _raid_buttons(content, world, "甲", "乙")[0]
        msgs, _ = _raid(content, world, rng=random.Random(7))
        seen.append((button, msgs, _load(world, "乙").journal[0].lines))
    assert seen[0] == seen[1]


def test_the_menu_does_not_list_raid_and_social_lists_the_card_action():
    assert "raid" in social.ACTIONS


def test_a_bot_raids_only_targets_it_can_beat(pair, monkeypatch):
    from tianxia import bot_policy

    content, world = pair
    monkeypatch.setattr(bot_policy, "RAID_CHANCE", 1.0)
    assert _do(content, world, "甲", lambda g: g.raid_targets())[0] == [("乙", "難分勝負")]
    assert _do(content, world, "甲", lambda g: bot_policy._raid(g, random.Random(0)))[0] is None  # 難分勝負不打
    them = _load(world, "乙")
    them.player.member.wugong_id = them.player.member.neigong_id = None  # 手無寸鐵：威力 0
    CharacterStore(world.db).save(them)
    assert _do(content, world, "甲", lambda g: g.raid_targets())[0] == [("乙", "穩勝")]
    msgs = _do(content, world, "甲", lambda g: bot_policy._raid(g, random.Random(0)))[0]
    assert msgs and _load(world, "乙").battles[0].kind == "raid"
    assert _do(content, world, "甲", lambda g: g.raid_targets())[0] == []  # 冷卻中


def test_both_sides_of_a_raid_dull_their_own_blade_and_the_defender_reads_the_warning_in_the_journal(pair, monkeypatch):
    from tianxia import weapons
    from tianxia.state import Weapon
    content, world = pair
    content.config.weapons.enabled = True
    for name in ("甲", "乙"):
        state = _load(world, name)
        state.player.weapon = Weapon(id=f"兵:{name}", name=f"{name}刃", kind="拳腳", attribute="剛", tier=1, quality="下品", edge=30)
        CharacterStore(world.db).save(state)
    _raid(content, world, tier="大勝", monkeypatch=monkeypatch)
    for name in ("甲", "乙"):
        after = _load(world, name)
        warning = weapons.EDGE_WARNING.format(dull=weapons.DULL["拳腳"], name=f"{name}刃")
        assert after.player.weapon.edge < 30 and after.player.edge_warned
        assert warning in after.battles[0].notes
        assert warning in after.journal[0].lines, name  # 發起的與被截殺的，江湖紀錄都讀得到
        assert after.journal[0].lines.count(warning) == 1


def _armored(world, attribute="剛"):
    from tianxia.state import Equipment
    for name in ("甲", "乙"):
        state = _load(world, name)
        state.player.armor = Equipment(id=f"甲:{name}", slot="armor", name=f"{name}的甲", attribute=attribute, tier=1, quality="下品")
        CharacterStore(world.db).save(state)


def test_the_raid_loser_bleeds_less_with_armor(pair, monkeypatch):
    """裝備四欄 4.4：截殺輸的一方只吃防具（上限的 8% ×（1−防具減損）），不吃化勁、不夾合計上限。"""
    content, world = pair
    content.config.armor.enabled = True
    _armored(world)
    _raid(content, world, tier="大勝", monkeypatch=monkeypatch)
    loser = _load(world, "乙").player
    cap = team.neili_cap(content, loser.member.level)
    assert loser.member.neili == pytest.approx(cap * (1 - content.config.raid.hp_loss * (1 - 0.06)), abs=1)  # 沒有內功：一階下品 6%
    assert loser.member.injury == 0


@pytest.mark.parametrize("tier,raider_edge,target_edge", [("大勝", 100, 95), ("落敗", 95, 100), ("僵持", 100, 100)])
def test_only_the_side_that_loses_a_raid_wears_its_armor(pair, monkeypatch, tier, raider_edge, target_edge):
    """裝備四欄 4.5：截殺只有輸的一方挨打、只有他磨防具（落敗扣 5）；發起的人輸了也是他磨，平手誰都不磨。"""
    content, world = pair
    content.config.armor.enabled = True
    _armored(world)
    _raid(content, world, tier=tier, monkeypatch=monkeypatch)
    assert _load(world, "甲").player.armor.edge == raider_edge and _load(world, "乙").player.armor.edge == target_edge
