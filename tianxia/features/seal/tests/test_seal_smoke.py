"""玉璽包的煙霧（全部拆包第 27 批）：包的宣告與格、舊名是同一個模組、最常見的那一條路（正式內容 week7：開季藏一片、探索一顆走到藏處撿到、
補送寫進傳承那一格與江湖紀錄）。細的規則照舊在 tests/seal/ 與這一包 tests/ 的其他檔。"""
from __future__ import annotations

from unittest import mock

from conftest import real_content
from jianfa_kit import _new, jianfa_rules, ready

from tianxia import explore_one
from tianxia.core import features as features_core
from tianxia.core import seal_base
from tianxia.core.registry import FEATURES


def test_the_package_declares_what_it_owns_and_the_old_name_is_the_same_module():
    from tianxia import seal as old
    from tianxia.features.seal import FEATURE
    from tianxia.features.seal import seal

    assert old is seal and FEATURES[-1] is FEATURE
    assert FEATURE.name == "seal" and FEATURE.prefix is None and FEATURE.content == ("seal.json",)
    assert FEATURE.player_fields == ("heirloom", "seal_seen") and FEATURE.carried == ("seal_seen",)
    assert [(h.event, h.slot) for h in FEATURE.bus()] == [("outing", "seal"), ("battle_end", "seal")]
    assert [(h.at, h.slot) for h in FEATURE.world()] == [
        ("muster", "seal"), ("open", "seal.cache"), ("next", "seal.mandate"), ("next", "seal.cache"), ("retire", "seal")]
    assert [h.slot for h in FEATURE.effects()] == ["runic", "shard"]
    assert features_core.bus_hooks("battle_end").keys() == {"seal"}
    # 核心與決戰包讀的那一小半在核心本體，包 re-export 同一個函式物件
    for name in ("on", "filled", "holders", "mandate_event", "is_mandate_battle", "lean_shift", "chronicle_block", "deserted"):
        assert getattr(seal, name) is getattr(seal_base, name), name


def test_exploring_the_hiding_place_picks_up_the_shard():
    """week7（領地爭奪的季）：開季那一刻藏一片（hide_chance 開滿），站到藏處按探索一顆，撿到的機率開滿——登記記在自己名下、
    回話接撿到那一句、補送寫傳承那一格與「玉璽碎片」那一則紀錄。"""
    from tianxia.features.seal import seal

    c = jianfa_rules(real_content("week7"))
    c.config.seal.cache.hide_chance = c.config.seal.cache.find_chance = 1.0
    game = _new(c, "拾璽客")
    view = game.world.seal_state()
    cache = view.registry.cache
    assert cache is not None and seal.live_cache(view.registry, view.season) is not None
    ready(game, side="guan", loc=cache.loc)
    with mock.patch.object(explore_one, "draw", return_value="material"):
        msgs = game.choose("act:explore")
    reg = game.world.seal_state().registry
    assert seal.FIND_SCENE in msgs
    assert reg.shards[cache.shard].state == "held" and reg.shards[cache.shard].holder == "拾璽客" and reg.cache is None
    assert game.state.player.heirloom is not None and game.state.player.heirloom.template == cache.shard
    assert game.state.player.seal_seen == reg.seq
    assert any(e.title == seal.SEAL_TITLE for e in game.state.journal)
