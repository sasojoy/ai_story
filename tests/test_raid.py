"""截殺（Config.raid；企劃者 2026-10-08 在決策卡選「有限制地開」）：只有敵對陣營的兩個人之間、不必對方同意；
新手期與城鎮類地點不能打、同一個目標有冷卻、被截殺過的人一陣子之內誰都不能再截殺他；輸的一方失一點銀兩與氣血，贏的拿走一部分。

兩個角色開在同一個資料庫；每一個動作照伺服器的做法先從資料庫重讀自己（server._locked），做完存回去。"""
from __future__ import annotations

import math
import random

import pytest

from conftest import install_season_one
from tianxia import encounter, rules, social, team
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.models import FactionDef
from tianxia.state import BotProfile

NOW = 1000.0


@pytest.fixture
def pair(content, world):
    install_season_one(content)
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


def test_the_switch_off_has_no_raids(pair):
    content, world = pair
    content.config.season_one = False
    world.mutate_season(lambda season: setattr(season, "season_one", False))
    assert _raid_buttons(content, world, "甲", "乙") == []


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
