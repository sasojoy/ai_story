"""領地爭奪第一批 Task 6：出陣改推進度（計畫三、Task 6；設計 3.7：平常出陣推那一塊的進度、不推線；貢獻照記）。翻地與爭搶（輿圖簡化設計第四章）之後
進度是每個攻方各一條、推得動的是碰得到的每一塊（不再只推今天公告的目標），這幾條照新形狀改寫；推滿易手、混戰、戰書另在 test_conquest_flip*.py、
test_conquest_clash.py、test_conquest_letter.py。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, contribution, conquest_game, go, join, plain_game, win_sortie
from tianxia import bot_policy, conquest, howto, orders, rules, sortie, territory, works
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
    assert conquest.bar(game.state.world, "nanyang_road", "huang") > 0
    assert _value(game, "nanyang") == before  # 不推線
    assert contribution(game) > 0  # 貢獻照記（不然沒人升得到第 4 階）
    assert any("你在南陽官道替黃巾軍推進了" in m for m in msgs)  # 輿圖簡化設計第五章起進度看得到數字
    assert not any("大勢@" in m for m in msgs)


def test_hold_at_own_block_pushes_back():
    game = go(join(conquest_game("season21"), "guan"), "yingchuan_wilds")
    conquest.push(game.state.world, game.content, "yingchuan_wilds", "huang", "某", 30, "attack")  # 黃巾在推官軍的潁川郊野
    option = _sortie(game)
    assert option is not None and "守" in option.label
    game.choose("act:train")
    assert conquest.bar(game.state.world, "yingchuan_wilds", "huang") < 30  # 把黃巾那一條拉回來
    assert contribution(game) > 0


def test_sortie_exists_at_non_line_block_but_not_off_the_blocks():
    game = go(join(conquest_game("season21"), "huang"), "deep_mountain")  # 嵩山深處不是戰線地點（區塊表 v3：官軍的）
    option = _sortie(game)
    assert option is not None and "攻" in option.label
    go(game, "haozu_fort")  # 豪強的投靠點不是區塊
    assert _sortie(game) is None


def test_bases_hold_but_push_no_progress():
    game = go(join(conquest_game("season21"), "guan"), "changshe")
    assert "守" in _sortie(game).label
    game.choose("act:train")
    assert conquest.bars(game.state.world, "changshe") == {}  # 大本營搶不下來：沒有進度


def test_neutral_block_foes_are_the_neutral_garrison():
    game = go(join(conquest_game("season21"), "guan"), "yu_river")  # 區塊表 v3 之前用嵩山深處（現在是官軍的）
    loc = game.content.locations["yu_river"]
    assert set(game._sortie_foes(loc)) == set(territory.squads_at(game.state.world, game.content, "yu_river"))
    assert "nz_shuifei" in game._sortie_foes(loc)


def test_enemy_block_without_garrison_has_the_holders_patrol():
    game = go(join(conquest_game("season21"), "huang"), "yingchuan")  # 官軍的城鎮沒寫 garrison
    loc = game.content.locations["yingchuan"]
    assert set(game._sortie_foes(loc)) == set(game.content.scenario.territory.side_garrison["guan"])


def test_event_at_block_pushes_progress_once():
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")  # 還沒人佔的中立地：事件了結推自己那一條
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
            # 只推一次 event_progress（一個人推：人數緩衝 ÷√1），推官軍那一條；不是出陣，不記「正在推的人」
            assert conquest.bar(s.world, "hilltop_wilds", "guan") == pytest.approx(c.config.conquest.event_progress)
            assert conquest.pushers(s.world, c, "hilltop_wilds") == []
            return
    pytest.skip("找不到單純的事件選項")


def test_bot_train_value_follows_progress(monkeypatch):
    # 2026-10-22（7 天季領地爭奪調整）之後假人出陣也看勝算（bot_policy._outmatched，測試在 test_bot_policy_conquest.py）：剛建的人打不贏
    # 南陽官道的駐軍；這一條只鎖「推不推得動」，勝算一律當成穩勝
    monkeypatch.setattr(bot_policy, "_sortie_win", lambda game, loc_id: 1.0)
    game = go(join(conquest_game("season21"), "huang"), "nanyang_huangjin_camp")
    profile = BotProfile(personality="普通", seed=1, faction="huang", season_number=1)
    assert bot_policy._train_value(game, profile, "nanyang_road") > 0  # 碰得到的中立地：推得動
    announce(game, "nanyang_road", "huang")  # 下了戰書：凍結，推不動
    assert bot_policy._train_value(game, profile, "nanyang_road") == 0
    assert bot_policy._train_value(game, profile, "nanyang_huangjin_camp") == 0  # 大本營：沒有進度可推


def test_siege_places_are_the_highest_block_on_that_line():
    """翻地與爭搶（PM 2026-10-20 第 1 條）：攻城軍令的地點是這一邊此刻進度最高、推得動的那一塊（第二批是今天公告的目標）。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    assert "runan_wilds" in orders.siege_places(c, "guan", "yingru", w)  # 全是 0：推得動的每一塊都算
    conquest.push(w, c, "runan_wilds", "guan", "某", 10, "attack")
    assert orders.siege_places(c, "guan", "yingru", w) == ["runan_wilds"]
    assert orders.siege_places(c, "huang", "yingru", w) == ["runan_wilds"]  # 區塊表 v3：黃巾開季碰不到荒丘


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
    game = go(join(conquest_game("season21"), "huang"), "nanyang_road")
    assert howto.SORTIE_PROGRESS in _note(game, "nanyang_road") and howto.SORTIE_NO_PUSH not in _note(game, "nanyang_road")
    conquest.push(game.state.world, game.content, "yingchuan_wilds", "huang", "某", 10, "attack")
    go(join(game, "guan"), "yingchuan_wilds")  # 守自家的區塊：有人在推，拉得回來
    assert howto.SORTIE_HOLD_PROGRESS in _note(game, "yingchuan_wilds")
    go(game, "changshe")  # 大本營搶不下來：沒有進度（FB-532：自家的大本營另一句，見 test_conquest_sortie_notes）
    assert "沒有進度可推" in _note(game, "changshe") and howto.SORTIE_PROGRESS not in _note(game, "changshe")
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
