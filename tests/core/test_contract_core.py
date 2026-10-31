"""核心契約：核心照 FEATURES 問每一包的時機（開發規範手冊 3.3）。用一個假的包（只在這個檔裡登記）驗每個掛鉤真的被叫、
叫的位置與順序；真的包各自守自己的契約在 test_contract_features.py。"""
from __future__ import annotations

import random

import pytest

from conftest import next_season
from tianxia.core import features as features_core
from tianxia.core import registry
from tianxia.core.features import AdminTool, Feature, Outcome
from tianxia.core.option import Option
from tianxia.engine import Game

DAY = 24 * 3600.0


class Fake(Feature):
    """記下每一次被叫；open 是 enabled 的答案。"""

    name = "fake"
    prefix = "fake"
    bot_always = ("fake:wait",)

    def __init__(self, open_=True, modal=False):
        self.open, self.modal, self.calls = open_, modal, []

    def _note(self, what, *extra):
        self.calls.append((what, *extra))

    def enabled(self, ctx):
        return self.open

    def options(self, ctx):
        self._note("options")
        return [Option(id="fake:do", label="假的一顆"), Option(id="fake:wait", label="一直按得下去")]

    def menu(self, ctx):
        self._note("menu")
        return [Option(id="fake:only", label="只剩這一顆")] if self.modal else None

    def choose(self, ctx, kind, arg):
        if kind != self.prefix:
            return None
        self._note("choose", arg)
        return Outcome(title=f"假的・{arg}", run=lambda: self._note("run", arg) or [f"做了{arg}。"])

    def status(self, ctx):
        return {"fake": {"n": 1}}

    def on_sync(self, ctx, elapsed):
        self._note("on_sync", round(elapsed))

    def on_day(self, ctx):
        self._note("on_day")

    def on_season_end(self, ctx):
        self._note("on_season_end", ctx.state.player.name, ctx.state.player.season_number)

    def on_season_start(self, ctx, old):
        self._note("on_season_start", ctx.state.player.name, old.player.season_number, ctx.state.player.season_number)

    def on_drop_stale(self, ctx):
        self._note("on_drop_stale")

    def bot_pick(self, ctx, option):
        return 77.0 if option.id == "fake:do" else None

    def admin_tools(self, shell):
        return {"fake_fix": AdminTool(gate=lambda: None, run=lambda g, b: ["修好了。"])}


@pytest.fixture
def fake(monkeypatch):
    f = Fake()
    monkeypatch.setattr(registry, "FEATURES", [f])
    return f


def _made(game: Game) -> Game:
    game.state.player.tutorial_step = len(game.content.tutorial.steps)
    game.sync(1000.0)
    return game


def test_place_options_come_from_the_packages(game, fake):
    ids = [o.id for o in _made(game).options()]
    assert "fake:do" in ids and "fake:wait" in ids


def test_a_package_takes_over_the_whole_menu(game, fake):
    fake.modal = True
    assert [o.id for o in _made(game).options()] == ["fake:only"]


def test_choose_hands_the_id_to_the_package_and_titles_the_entry_first(game, fake):
    msgs = _made(game).choose("fake:do")
    assert msgs == ["做了do。"]
    assert fake.calls.index(("choose", "do")) < fake.calls.index(("run", "do"))
    assert game.state.journal[0].title == "假的・do" and game.state.journal[0].lines == ["做了do。"]


def test_a_closed_package_is_never_asked(game, fake):
    fake.open = False
    fake.modal = True
    g = _made(game)
    ids = [o.id for o in g.options()]
    assert not any(i.startswith("fake:") for i in ids)
    assert g.choose("fake:do") == ["（此刻無法這麼做。）"]
    assert g.feature_status() == {}
    assert fake.calls == []


def test_status_goes_to_the_top_of_the_page(game, fake):
    assert _made(game).feature_status() == {"fake": {"n": 1}}


def test_sync_reports_the_elapsed_seconds_and_a_new_day(game, fake):
    game.state.player.tutorial_step = len(game.content.tutorial.steps)
    game.sync(1000.0)  # 第一次同步（沒有上一次）：算換了一天
    assert ("on_day",) in fake.calls and ("on_sync", 0) in fake.calls
    fake.calls.clear()
    game.sync(1060.0)  # 同一天
    assert ("on_day",) not in fake.calls
    assert ("on_sync", round(60 * game.content.config.time_scale)) in fake.calls
    fake.calls.clear()
    game.sync(1060.0 + DAY)  # 隔天
    assert ("on_day",) in fake.calls


def test_a_new_day_follows_the_pill_day_through_fast_forward(game, fake):
    """on_day 跟回體丹那一套（_pill_day：sync 給的 now 加上快轉推過的 advanced_real）同一個「天」：管理者快轉、整季機器人用 advance
    跨過 00:00 也算換了一天，之後的 sync 照快轉後的那一天比，不重算、也不漏。"""
    _made(game)
    fake.calls.clear()
    scale = game.content.config.time_scale
    day = game._pill_day()
    game.advance(60 * scale)  # 快轉一分鐘：同一天
    assert game._pill_day() == day and ("on_day",) not in fake.calls
    game.advance(DAY * scale)  # 快轉一整天：回體丹那一天換了
    assert game._pill_day() == day + 1 and fake.calls.count(("on_day",)) == 1
    fake.calls.clear()
    game.sync(1060.0)  # 現實才過一分鐘：還是快轉後的那一天
    assert game._pill_day() == day + 1 and ("on_day",) not in fake.calls
    game.sync(1060.0 + DAY)  # 現實也過了一天
    assert game._pill_day() == day + 2 and fake.calls.count(("on_day",)) == 1


def test_a_new_season_ends_the_old_one_then_starts_the_new_one(content, world, fake):
    game = Game.new(content, "換季客", rng=random.Random(0), world=world)
    game.state.player.tutorial_step = len(content.tutorial.steps)
    game.sync(100.0)
    fake.calls.clear()
    next_season(content, world, game)
    seasons = [c for c in fake.calls if c[0].startswith("on_season") and c[1] == "換季客"]  # 管理者自己也換季，不看他
    assert seasons == [("on_season_end", "換季客", 1), ("on_season_start", "換季客", 1, 2)]


def test_dropping_stale_references_asks_the_packages(content, world, fake):
    Game.new(content, "讀檔客", rng=random.Random(0), world=world)
    assert ("on_drop_stale",) in fake.calls


def test_the_bots_ask_the_package_and_skip_its_always_pressable_ones(game, fake):
    from tianxia import bot, bot_policy
    from tianxia.state import BotProfile

    g = _made(game)
    profile = BotProfile(personality="普通", seed=1)
    opts = {o.id: o for o in g.options()}
    assert bot_policy.score(g, opts["fake:do"], profile) == 77.0
    assert bot_policy.score(g, opts["fake:wait"], profile) is None
    assert "fake:wait" in features_core.bot_always()
    for seed in range(20):  # 整季機器人：永遠按得下去的那一顆從不按
        assert bot.pick(g, [opts["fake:wait"]], random.Random(seed)) is None


def test_admin_tools_merge_and_refuse_the_same_name_twice(monkeypatch):
    one, two = Fake(), Fake()
    monkeypatch.setattr(registry, "FEATURES", [one])
    assert list(features_core.admin_tools(None)) == ["fake_fix"]
    monkeypatch.setattr(registry, "FEATURES", [one, two])
    with pytest.raises(ValueError):
        features_core.admin_tools(None)


def test_owner_of_goes_by_the_prefix(fake):
    assert features_core.owner_of("fake:do") is fake
    assert features_core.owner_of("fakeish:do") is None and features_core.owner_of("act:explore") is None
