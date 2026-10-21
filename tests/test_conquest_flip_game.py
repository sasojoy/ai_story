"""翻地與爭搶接到出陣上（輿圖簡化設計 4.1、4.2、4.5；計畫 docs/superpowers/plans/2026-10-20-翻地與爭搶.md）：出陣攻推自己那一條、推滿那一下
當場易手、分紅在自己同步時送到（下線的人回來也拿得到）、冷卻期行動列寫原因、掉落只給一階、每日回在世界推進時跑、集火寫在那一句裡。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, conquest_game, go, join, plain_game, win_sortie
from tianxia import annals, calendar, conquest, materials

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

DAY = 86400


def _game(side="guan", loc="hilltop_wilds", name="沈浪", world=None):
    return go(join(conquest_game("season21", name=name, world=world), side), loc)


def _nominal(game, loc="hilltop_wilds", how="attack"):
    return conquest.sortie_nominal(game.content, loc, how) * game.content.config.conquest.progress_scale


def test_sortie_attack_pushes_my_own_bar():
    game = _game()
    msgs = win_sortie(game)
    w = game.state.world
    assert conquest.bar(w, "hilltop_wilds", "guan") == pytest.approx(_nominal(game))
    assert conquest.bar(w, "hilltop_wilds", "huang") == 0
    assert any("你在荒丘替官軍推進了" in m and "／100" in m for m in msgs)
    assert [row["name"] for row in conquest.pushers(w, game.content, "hilltop_wilds")] == ["沈浪"]


def test_the_push_that_fills_the_bar_flips_on_the_spot_and_pays_on_sync():
    game = _game()
    w, c = game.state.world, game.content
    conquest.push(w, c, "hilltop_wilds", "guan", "別人", 99, "attack")
    silver = game.state.player.stats.get("silver", 0)
    msgs = win_sortie(game)
    assert conquest.holder(w, c, "hilltop_wilds") == "guan" and conquest.cooling(w, c, "hilltop_wilds")
    assert any("進度推滿了，當場易手" in m for m in msgs)
    assert any("荒丘落入" in r.text for r in w.rumors)
    assert {p.name for p in w.conquest.payouts} == {"沈浪", "別人"}
    mine = next(m for m in conquest.fight_of(w, "hilltop_wilds").marks if m.name == "沈浪")
    assert mine.moved == pytest.approx(1)  # 只推得動到滿的那一截
    game._deliver_conquest()
    entry = next(e for e in game.state.journal if e.title == "攻下荒丘")
    assert game.state.player.stats["silver"] > silver and any(line.startswith("銀兩 +") for line in entry.changes)
    assert [p.name for p in w.conquest.payouts] == ["別人"]  # 別人的留著，等他自己同步時拿
    assert not any(a.kind == annals.CONQUER for a in game.state.player.annals)  # 推最多的是「別人」


def test_the_top_pusher_gets_an_annal_and_the_payout_leaves_the_season():
    game = _game()
    w, c = game.state.world, game.content
    conquest.push(w, c, "hilltop_wilds", "guan", "沈浪", 100, "attack")
    game._save_season()
    game.state.world = game.world.get_season()
    game._deliver_conquest()
    assert any(e.title == "攻下荒丘" for e in game.state.journal)
    assert any(a.kind == annals.CONQUER and "率先攻入荒丘" in a.text for a in game.state.player.annals)
    assert game.world.get_season().conquest.payouts == []


def test_the_action_note_says_why_it_cannot_push():
    game = _game()
    w, c = game.state.world, game.content
    loc = c.locations["hilltop_wilds"]
    conquest.push(w, c, "hilltop_wilds", "guan", "別人", 100, "attack")  # 官軍剛拿下：冷卻
    assert "剛易手，60 分後才能再推" in game._sortie_line(loc)
    w.time += 3601
    assert "沒有人在推這裡" in game._sortie_line(loc)  # 自家的、沒人推：守了也拉不動
    conquest.push(w, c, "hilltop_wilds", "huang", "丁", 10, "attack")
    assert "把對面在這裡的進度拉回來" in game._sortie_line(loc)
    other = _game(side="huang", world=game.world)
    other.state.world = w
    announce(game, "hilltop_wilds", "huang")
    assert "已下戰書" in other._sortie_line(loc)
    go(game, "xiaquyang")  # 冀州的中立地：官軍此刻碰不到
    assert "跟自家的領地不相連" in game._sortie_line(c.locations["xiaquyang"])


def test_a_cooling_neutral_block_drops_only_first_tier(monkeypatch):
    game = _game()
    w, c = game.state.world, game.content
    conquest.push(w, c, "hilltop_wilds", "huang", "丁", 100, "attack")  # 黃巾剛拿下：官軍照樣能攻駐軍，但推不動、只掉一階
    seen: list = []
    real = materials.roll_squad_drops
    monkeypatch.setattr(materials, "roll_squad_drops", lambda *a, **k: seen.append(k.get("max_tier")) or real(*a, **k))
    win_sortie(game)
    assert seen == [1]
    assert conquest.bar(w, "hilltop_wilds", "guan") == 0


def test_decay_runs_when_the_world_moves():
    game = _game()
    w, c = game.state.world, game.content
    conquest.push(w, c, "hilltop_wilds", "guan", "別人", 50, "attack")
    game._save_season()
    game.advance(3 * DAY / calendar.cal_scale(c, w))  # 三個季曆天：推過的那一天不回，後面兩天各回 10
    assert conquest.bar(game.state.world, "hilltop_wilds", "guan") == pytest.approx(50 - 2 * c.config.conquest.decay_per_day)


def test_focus_shows_in_the_line():
    game = _game()
    w, c = game.state.world, game.content
    conquest.mark(w, c, "hilltop_wilds", "同袍", "guan", "attack", 3)
    msgs = win_sortie(game)
    assert any("集火 +10%" in m for m in msgs)
    assert conquest.bar(w, "hilltop_wilds", "guan") == pytest.approx(_nominal(game) * 1.1)


def test_switch_off_sortie_and_payouts_unchanged():
    game = go(join(plain_game("season21"), "guan"), "hilltop_wilds")
    assert game.sortie_progress("hilltop_wilds") == 0 and game.state.world.conquest is None
    game._deliver_conquest()  # 沒有這一本：什麼都不做
    assert game.conquest_view() is None
