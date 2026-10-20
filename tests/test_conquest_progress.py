"""領地爭奪第一批 Task 6：出陣改推進度（計畫三、Task 6；設計 3.7：平常出陣推攻城目標的進度、不推線；貢獻照記）。"""
from __future__ import annotations

import pytest

from conquest_kit import contribution, conquest_game, go, join, plain_game, win_sortie
from tianxia import bot_policy, conquest, howto, orders, rules, territory, works
from tianxia.state import BotProfile

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _sortie(game):
    return next((o for o in game.options() if o.id == "act:train"), None)


def _value(game, line):
    return rules.world_trend_value(game.state.world, game.content, line)


def test_sortie_attack_win_pushes_progress_not_the_line():
    game = go(join(conquest_game("season21"), "huang"), "nanyang_road")
    before = _value(game, "nanyang")
    option = _sortie(game)
    assert option is not None and option.enabled and "攻" in option.label
    msgs = win_sortie(game)
    assert conquest.progress_of(game.state.world, "nanyang_road") > 50
    assert _value(game, "nanyang") == before  # 不推線
    assert contribution(game) > 0  # 貢獻照記（不然沒人升得到第 4 階）
    assert any("南陽官道一帶" in m for m in msgs)  # 一句話、不寫數字
    assert not any("大勢@" in m for m in msgs)


def test_hold_at_own_block_pushes_back():
    game = go(join(conquest_game("season21"), "guan"), "yingchuan_wilds")
    option = _sortie(game)
    assert option is not None and "守" in option.label
    game.choose("act:train")
    assert conquest.progress_of(game.state.world, "yingchuan_wilds") < 50  # 往官軍那頭
    assert contribution(game) > 0


def test_sortie_exists_at_non_line_block_but_not_off_the_blocks():
    game = go(join(conquest_game("season21"), "guan"), "deep_mountain")  # 嵩山深處不是戰線地點
    option = _sortie(game)
    assert option is not None and "攻" in option.label
    go(game, "haozu_fort")  # 豪強的投靠點不是區塊
    assert _sortie(game) is None


def test_bases_hold_but_push_no_progress():
    game = go(join(conquest_game("season21"), "guan"), "changshe")
    assert "守" in _sortie(game).label
    game.choose("act:train")
    assert conquest.progress_of(game.state.world, "changshe") == 50  # 大本營搶不下來：沒有進度


def test_neutral_block_foes_are_the_neutral_garrison():
    game = go(join(conquest_game("season21"), "guan"), "deep_mountain")
    loc = game.content.locations["deep_mountain"]
    assert set(game._sortie_foes(loc)) == set(territory.squads_at(game.state.world, game.content, "deep_mountain"))
    assert "nz_tiger" in game._sortie_foes(loc)


def test_enemy_block_without_garrison_has_the_holders_patrol():
    game = go(join(conquest_game("season21"), "huang"), "yingchuan")  # 官軍的城鎮沒寫 garrison
    loc = game.content.locations["yingchuan"]
    assert set(game._sortie_foes(loc)) == set(game.content.scenario.territory.side_garrison["guan"])


def test_event_at_block_pushes_progress_once():
    game = go(join(conquest_game("season21"), "guan"), "yingchuan_wilds")
    s, c = game.state, game.content
    for event in c.events.values():
        for i, choice in enumerate(event.choices):
            if choice.combat or choice.check or choice.effect.next_event or choice.needs or event.once or event.qiyu:
                continue
            s.pending_event = event.id
            option = next((o for o in game.options() if o.id == f"choice:{i}" and o.enabled), None)
            if option is None:
                s.pending_event = None
                continue
            game.choose(option.id)
            assert s.pending_event is None
            assert conquest.progress_of(s.world, "yingchuan_wilds") < 50
            return
    pytest.skip("找不到單純的事件選項")


def test_bot_train_value_follows_progress():
    game = go(join(conquest_game("season21"), "huang"), "nanyang_huangjin_camp")
    profile = BotProfile(personality="普通", seed=1, faction="huang", season_number=1)
    assert bot_policy._train_value(game, profile, "nanyang_road") > 0
    assert bot_policy._train_value(game, profile, "nanyang_huangjin_camp") == 0  # 大本營：沒有進度可推


def test_siege_places_are_enemy_held_targets_on_that_line():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    assert orders.siege_places(c, "guan", "yingru", w) == ["runan_wilds"]
    assert orders.siege_places(c, "huang", "yingru", w) == []  # 黃巾開季碰不到官軍的陣營區塊


def test_fortify_is_not_drawn():
    game = go(join(conquest_game("season21"), "guan"), "yingchuan_wilds")
    game.content.config.fortify.enabled = True
    assert not works.fort_spot(game.state, game.content, "guan")
    assert not any(o.id == "works:fortify" for o in game.options())


def test_howto_has_the_conquest_version():
    game = conquest_game("season21")
    lines = howto.territory_lines(game.content, True, game.state.world)
    assert any("中立地" in line for line in lines)
    plain = plain_game("season21")
    assert not any("中立地" in line for line in howto.territory_lines(plain.content, True, plain.state.world))


def test_switch_off_sortie_unchanged():
    game = go(join(plain_game("weekend"), "huang"), "runan_wilds")
    w = game.state.world
    assert game.sortie_push("guan_camp", "attack")  # 關著：出陣照舊推線
    assert w.conquest is None and game.sortie_progress("guan_camp") == 0
