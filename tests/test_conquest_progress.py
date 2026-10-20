"""領地爭奪第一批 Task 6：出陣改推進度（計畫三、Task 6；設計 3.7：平常出陣推攻城目標的進度、不推線；貢獻照記）。
輿圖重製第 1 批（新天下）：中立地換成中原的荒丘、官軍的陣營區塊換成南陽官道、大本營換成宛城與鉅鹿道壇、沒寫 garrison 的官軍城鎮換成新野
（v1 是南陽官道、潁川郊野、長社、南陽黃巾營、潁川郡）；線上的敵方陣營區塊照 conquest_kit.conquest_game_with 把汝南荒野改回 v1。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, contribution, conquest_game, conquest_game_with, go, join, plain_game, win_sortie
from tianxia import bot_policy, conquest, howto, orders, rules, sortie, territory, works
from tianxia.state import BotProfile

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _sortie(game):
    return next((o for o in game.options() if o.id == "act:train"), None)


def _value(game, line):
    return rules.world_trend_value(game.state.world, game.content, line)


def test_sortie_attack_win_pushes_progress_not_the_line():
    game = go(join(conquest_game("season21"), "huang"), "hilltop_wilds")
    announce(game, "hilltop_wilds", "huang")  # 第二批起只有今天公告的目標推得動進度（計畫 2.3）
    before = _value(game, "yingru")
    option = _sortie(game)
    assert option is not None and option.enabled and "攻" in option.label
    msgs = win_sortie(game)
    assert conquest.progress_of(game.state.world, "hilltop_wilds") > 50
    assert _value(game, "yingru") == before  # 不推線
    assert contribution(game) > 0  # 貢獻照記（不然沒人升得到第 4 階）
    assert any("荒丘一帶" in m for m in msgs)  # 一句話、不寫數字
    assert not any("大勢@" in m for m in msgs)


def test_hold_at_own_block_pushes_back():
    game = go(join(conquest_game("season21"), "guan"), "nanyang_road")
    announce(game, "nanyang_road", "huang")
    option = _sortie(game)
    assert option is not None and "守" in option.label
    game.choose("act:train")
    assert conquest.progress_of(game.state.world, "nanyang_road") < 50  # 往官軍那頭
    assert contribution(game) > 0


def test_sortie_exists_at_non_line_block_but_not_off_the_blocks():
    game = go(join(conquest_game("season21"), "guan"), "deep_mountain")  # 嵩山深處不是戰線地點
    option = _sortie(game)
    assert option is not None and "攻" in option.label
    go(game, "haozu_fort")  # 豪強的投靠點不是區塊
    assert _sortie(game) is None


def test_bases_hold_but_push_no_progress():
    game = go(join(conquest_game("season21"), "guan"), "wan_city")
    assert "守" in _sortie(game).label
    game.choose("act:train")
    assert conquest.progress_of(game.state.world, "wan_city") == 50  # 大本營搶不下來：沒有進度


def test_neutral_block_foes_are_the_neutral_garrison():
    game = go(join(conquest_game("season21"), "guan"), "deep_mountain")
    loc = game.content.locations["deep_mountain"]
    assert set(game._sortie_foes(loc)) == set(territory.squads_at(game.state.world, game.content, "deep_mountain"))
    assert "nz_tiger" in game._sortie_foes(loc)


def test_enemy_block_without_garrison_has_the_holders_patrol():
    game = go(join(conquest_game("season21"), "huang"), "xinye")  # 官軍的城鎮沒寫 garrison
    loc = game.content.locations["xinye"]
    assert set(game._sortie_foes(loc)) == set(game.content.scenario.territory.side_garrison["guan"])


def test_event_at_block_pushes_progress_once():
    game = go(join(conquest_game("season21"), "guan"), "yingchuan_wilds")
    announce(game, "yingchuan_wilds", "huang")
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
            # 只推一次 event_progress（一個人推：人數緩衝 ÷√1），往官軍那頭
            assert conquest.progress_of(s.world, "yingchuan_wilds") == pytest.approx(50 - c.config.conquest.event_progress)
            return
    pytest.skip("找不到單純的事件選項")


def test_bot_train_value_follows_progress():
    game = go(join(conquest_game("season21"), "huang"), "julu_altar")
    profile = BotProfile(personality="普通", seed=1, faction="huang", season_number=1)
    assert bot_policy._train_value(game, profile, "baima_ford") == 0  # 第二批：今天沒公告推不動
    announce(game, "baima_ford", "huang")
    assert bot_policy._train_value(game, profile, "baima_ford") > 0
    assert bot_policy._train_value(game, profile, "julu_altar") == 0  # 大本營：沒有進度可推


def test_siege_places_are_todays_targets_on_that_line():
    """第二批（裁決 11）：攻城軍令的地點是這一邊今天公告要攻的目標（第一批是此刻歸敵方的目標）。"""
    game = conquest_game_with({"runan_wilds": ("huang", "yingru")})  # 線上的敵方陣營區塊：汝南荒野改回 v1
    w, c = game.state.world, game.content
    assert orders.siege_places(c, "guan", "yingru", w) == []  # 還沒公告
    announce(game, "runan_wilds", "guan")
    assert orders.siege_places(c, "guan", "yingru", w) == ["runan_wilds"]
    assert orders.siege_places(c, "huang", "yingru", w) == []


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


def test_help_texts_say_progress_and_holdings():
    """戰況圖卡、主線小標、投靠那一段的說明：出陣推進度、戰線照佔領算（不再寫「在戰線上的地點出陣會推動戰況」）；關著照舊。"""
    game = conquest_game("season21")
    s, c = game.state, game.content
    helps = howto.war_help(s, c)
    assert howto.CONQUEST_FRONTS in " ".join(helps["fronts"]) and howto.SORTIE_PLACES not in " ".join(helps["fronts"])
    assert howto.CONQUEST_PLACES in " ".join(helps["quest"])
    assert howto.CONQUEST_PLACES in " ".join(howto.season_page_lines(c, s.world))
    assert howto.CONQUEST_JOIN in " ".join(howto.join_lines(c, s.world))
    plain = plain_game("season21")
    old = howto.war_help(plain.state, plain.content)
    assert howto.SORTIE_PLACES in " ".join(old["quest"]) and howto.CONQUEST_FRONTS not in " ".join(old["fronts"])
    assert howto.SORTIE_JOIN in " ".join(howto.join_lines(plain.content, plain.state.world))


def _note(game, loc_id):
    return game._sortie_line(game.content.locations[loc_id])  # 行動列底下出陣那一行（action_notes 的 act:train）


def test_action_note_says_progress_not_the_line():
    """行動列底下那一行：出陣推的是這一塊的進度，不寫「這條線推滿了」（sortie_push 開著時是空的，舊寫法會判成推不動）。"""
    game = go(join(conquest_game("season21"), "huang"), "hilltop_wilds")
    assert howto.SORTIE_NOT_TODAY in _note(game, "hilltop_wilds")  # 第二批：今天沒公告推不動
    announce(game, "hilltop_wilds", "huang")
    announce(game, "nanyang_road", "huang")
    assert howto.SORTIE_PROGRESS in _note(game, "hilltop_wilds") and howto.SORTIE_NO_PUSH not in _note(game, "hilltop_wilds")
    go(join(game, "guan"), "nanyang_road")  # 守自家的區塊
    assert howto.SORTIE_PROGRESS in _note(game, "nanyang_road")
    go(game, "wan_city")  # 大本營搶不下來：沒有進度（FB-532：自家的大本營另一句，見 test_conquest_sortie_notes）
    assert "沒有進度可推" in _note(game, "wan_city") and howto.SORTIE_PROGRESS not in _note(game, "wan_city")
    plain = go(join(plain_game("weekend"), "huang"), "runan_wilds")
    assert howto.SORTIE_PROGRESS not in _note(plain, "runan_wilds")  # 關著照舊寫推動戰局


def test_ranger_sees_why_at_every_block():
    """散人站在不是戰線地點的區塊（嵩山深處）：投靠了陣營的人在這裡有出陣，散人那一格灰著寫原因（FB-250 的同一條，照區塊判）。"""
    game = go(join(conquest_game("season21"), None), "deep_mountain")
    option = _sortie(game)
    assert option is not None and not option.enabled and sortie.RANGER_NOTE in option.label
    go(game, "haozu_fort")  # 不是區塊：沒有出陣那一格
    assert _sortie(game) is None
    plain = go(join(plain_game("season21"), None), "deep_mountain")
    assert _sortie(plain) is None  # 關著：嵩山深處不是戰線地點，照舊沒有


def test_switch_off_sortie_unchanged():
    game = go(join(plain_game("weekend"), "huang"), "runan_wilds")
    w = game.state.world
    assert game.sortie_push("guan_camp", "attack")  # 關著：出陣照舊推線
    assert w.conquest is None and game.sortie_progress("guan_camp") == 0
