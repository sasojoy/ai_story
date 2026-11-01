"""酒肆包接在核心接縫掛鉤上的那幾格，走公開的路（全部拆包第 11 批審查）：下線那一段殺手得手了存回季（on_away）、一次同步收護衛、風聲、
殺手單、託付的先後（deliver_notices）、在城外做完一件事殺手找上門（after_action，走 choose）、進店那一顆只有一顆（Shop.entry）。
這幾行以前只有 scripts/same_behavior.py 抓得到：酒肆的測試都直接叫 _tavern_hit_check()、_deliver_hits()，不經 sync 與 choose。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import figure_aid, tavern
from tianxia.characters import CharacterStore, name_key
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import TavernHit, TavernWatch, Whisper

pytestmark = pytest.mark.slow

NOW = 16 * 3600 + 3600


def _content():
    c = real_content("week7")
    c.config.auto_open_first_season = True
    return c


def _game(name, world, c, at="wan_city", faction=None):
    game = Game.new(c, name, rng=random.Random(0), world=world)
    game.client = None
    p = game.state.player
    p.location, p.faction = at, faction
    p.tutorial_step = len(c.tutorial.steps)
    p.stats["silver"] = 500
    p.joined_at = -10 ** 9
    game.now = NOW
    p.seen_real = NOW
    CharacterStore(world.db).save(game.state)
    return game


def _outside(c):
    return next(lid for lid in c.locations if not tavern.town(c, lid) and tavern.near(c, "wan_city", lid) >= 1
                and not c.locations[lid].tags.count("序章"))


def _rig(monkeypatch):
    """殺手那一場定成本人落敗、一定找得到（同 test_tavern._rig）。"""
    from tianxia import encounter

    def fake(mine, killer, rng, *a, **k):
        return encounter.EncounterResult(tier="落敗", margin=0.0, our_power=mine, difficulty=killer)

    monkeypatch.setattr("tianxia.engine.encounter.resolve_encounter", fake)
    monkeypatch.setattr(tavern, "find_chance", lambda c, reach: 1.0)


def _hired(world, c):
    """沈浪在宛城的酒肆查到李尋歡、雇一張找他的單子；李尋歡是另一個陣營、過了新手期。"""
    me = _game("沈浪", world, c, faction="guanjun")
    them = _game("李尋歡", world, c, faction="huangjin")
    them.state.player.stats["fame"] = 10_000
    CharacterStore(world.db).save(them.state)
    me.choose("act:tavern")
    me.tavern_do("seek", "李尋歡")
    me.tavern_do("hit", "李尋歡", "0")
    me._save_season()
    return me, them


def test_a_killer_who_finds_you_while_away_is_written_back_to_the_season(monkeypatch):
    """下線那一段（on_away）殺手得手了：那張單子的結果寫回共用賽季（得手了改了季上的單子，存回），雇主自己同步才收得到。"""
    world, c = open_world(), _content()
    _, them = _hired(world, c)
    _rig(monkeypatch)
    them.sync(NOW + 5)
    them.state.player.location = _outside(c)
    them.sync(NOW + 60)  # 才隔一分鐘：不算下線
    them.sync(NOW + 60 + c.config.tavern.hit_offline_minutes * 60 + 1)
    assert them.state.world.tavern_hits[-1].outcome == "殺手贏"
    stored = world.get_season().tavern_hits[-1]
    assert stored.done and stored.outcome == "殺手贏"


def test_one_sync_hands_over_the_guard_credit_then_the_whisper_the_hit_and_the_watch():
    """一次同步收四樣，江湖紀錄照 sync 的先後（新的在前）：護衛補帳（核心，前一格）→ 風聲 → 自己雇的單子到期退錢 → 託付到期
    （酒肆包 deliver_notices，照原本那三行的順序）。"""
    world, c = open_world(), _content()
    me = _game("沈浪", world, c)
    me.sync(NOW)
    now = NOW + 60

    def fn(s) -> None:
        s.guard_credits.setdefault("沈浪", []).append(figure_aid.CREDIT_LINE.format(name="某人", who="李尋歡"))
        s.tavern_whispers.setdefault(name_key("沈浪"), []).append(
            Whisper(kind="seek", who="李尋歡", place="wan_city", time=s.time, named=True))
        s.tavern_hit_seq += 1
        s.tavern_hits.append(TavernHit(id=s.tavern_hit_seq, client="沈浪", target="李尋歡", tier=0, price=20, place="wan_city",
                                       placed_real=now - 7200, until_real=now - 60))

    world.mutate_season(fn)
    me.state.player.tavern_watches = [TavernWatch(target="查無此人", place="wan_city", until_real=now - 1)]
    me.sync(now)
    titles = [e.title for e in me.state.journal]
    wanted = (tavern.WATCH_TITLE, tavern.HIT_TITLE, tavern.WHISPER_TITLE, figure_aid.CREDIT_TITLE)
    assert all(t in titles for t in wanted), titles
    at = [titles.index(t) for t in wanted]
    assert at == sorted(at), titles


def test_a_killer_finds_you_right_after_you_act_outside_town(monkeypatch):
    """在城外做完一件事（choose 最後那一下，after_action）：殺手照打聽度擲、找到了打一場，紀錄裡有遭殺手找上。"""
    world, c = open_world(), _content()
    _, them = _hired(world, c)
    _rig(monkeypatch)
    them.sync(NOW + 5)
    them.state.player.location = _outside(c)
    ids = {o.id: o for o in them.options()}
    pick = next(i for i in ("act:explore", "act:train", "act:socialize") if i in ids and ids[i].enabled)
    them.choose(pick)
    hit = them.state.world.tavern_hits[-1]
    assert hit.done and hit.outcome == "殺手贏", pick
    assert any(e.title == tavern.HIT_STRUCK for e in them.state.journal)


def test_the_tavern_door_is_one_button():
    """此地還能做裡進店那一顆（Shop.entry）只有一顆。"""
    world, c = open_world(), _content()
    game = _game("沈浪", world, c)
    assert [o.id for o in game.options()].count("act:tavern") == 1
