"""核心契約：核心照 FEATURES 問每一包的時機（開發規範手冊 3.3）。用一個假的包（只在這個檔裡登記）驗每個掛鉤真的被叫、
叫的位置與順序；真的包各自守自己的契約在 test_contract_features.py。"""
from __future__ import annotations

import random

import pytest

from conftest import next_season
from tianxia.core import features as features_core
from tianxia.core import registry
from tianxia.core.features import AdminTool, Feature, Outcome, Shop, Verb
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


# ── 接縫掛鉤（全部拆包第 11 批「核心收接縫」；計畫 docs/superpowers/plans/2026-11-01-核心收接縫.md 1.3）──
# 另一個假的包：舊的 Fake 不動（test_a_closed_package_is_never_asked 照舊守遊戲當下的掛鉤），接縫掛鉤記在同一份 calls。


class Seams(Fake):
    """接縫掛鉤每一個都記；shop、verb 兩個宣告照旗標回答。"""

    def __init__(self, open_=True):
        super().__init__(open_)
        self.in_shop, self.shop_here, self.seated, self.over = False, True, False, None

    def on_due(self, ctx):
        self._note("on_due")

    def on_away(self, ctx, away_from):
        self._note("on_away", away_from)

    def deliver_results(self, ctx):
        self._note("deliver_results")

    def deliver_notices(self, ctx):
        self._note("deliver_notices")

    def choose_unlisted(self, ctx, option_id):
        if option_id != "fake:raw":
            return None
        self._note("choose_unlisted", option_id)
        return ["不在選單上的也接得到。"]

    def after_action(self, ctx):
        self._note("after_action")
        return ["做完之後的那一句。"]

    def on_own_turn(self, ctx):
        self._note("on_own_turn")

    def scene(self, ctx):
        return "**假的宴席**" if self.seated else None

    def scene_over(self, ctx):
        return self.over

    def record_detail(self, ctx, record):
        return record.model_copy(update={"opponent": "換過的對手"})

    def shops(self):
        return (Shop(key="fakeshop", inside=lambda g: self.in_shop, here=lambda g: self.shop_here,
                     close=lambda g: setattr(self, "in_shop", False) or self._note("close_shop"),
                     menu=lambda g: [Option(id="fake:leave", label="出店")],
                     entry=lambda g: Option(id="act:fakeshop", label="假的店") if self.shop_here else None),)

    def verbs(self):
        return (
            Verb("fakeverb", run=lambda g, prepared: ["只打開一張卡。"], title=lambda g: "假的子動詞・此地", picks=("只打開一張卡。",)),
            Verb("explore", cell=lambda g, loc, cost, odds: [Option(id="act:fakeverb", label="假的那一格")],
                 note=lambda g, loc: "假的那一行"),
        )


@pytest.fixture
def seams(monkeypatch):
    f = Seams()
    monkeypatch.setattr(registry, "FEATURES", [f])
    return f


TIME_SEAMS = ("on_due", "on_away", "deliver_results", "deliver_notices", "on_sync")


def test_the_seams_in_sync_come_where_the_old_lines_were(game, seams):
    """sync 裡的接縫掛鉤照原本那幾行的先後：到時的結算（追完共用賽季之後）→ 下線那一段（有上一次同步才有，away_from 是上一次的現實秒）
    → 收場補送 → 別人捎來的 → 既有的 on_sync。第一次同步沒有上一次：不叫 on_away。"""
    game.state.player.tutorial_step = len(game.content.tutorial.steps)
    game.sync(1000.0)
    assert [c[0] for c in seams.calls if c[0] in TIME_SEAMS] == ["on_due", "deliver_results", "deliver_notices", "on_sync"]
    seams.calls.clear()
    game.sync(1060.0)
    assert [c for c in seams.calls if c[0] in TIME_SEAMS] == [
        ("on_due",), ("on_away", 1000.0), ("deliver_results",), ("deliver_notices",), ("on_sync", round(60 * game.content.config.time_scale))]


def test_the_due_hook_also_runs_on_fast_forward_and_the_world_tick(content, world, seams):
    game = Game.new(content, "快轉客", rng=random.Random(0), world=world)
    _made(game)
    seams.calls.clear()
    game.advance(60.0)
    assert seams.calls.count(("on_due",)) == 1
    seams.calls.clear()
    Game.for_world(content, world).world_tick(2000.0)
    assert seams.calls.count(("on_due",)) == 1


def test_the_time_seams_are_asked_even_when_the_package_is_closed(game, seams):
    """接縫掛鉤不問 enabled（原位那幾行本來就不看包的開關：酒肆的三個 deliver 關著照送、決戰補送照內容）；既有的 on_sync 照舊不叫。"""
    seams.open = False
    _made(game)
    game.sync(1060.0)
    assert [c[0] for c in seams.calls if c[0] in TIME_SEAMS] == [
        "on_due", "deliver_results", "deliver_notices", "on_due", "on_away", "deliver_results", "deliver_notices"]


def test_a_shop_takes_over_the_menu_opens_its_page_and_closes(game, seams):
    """店面登記：此地還能做裡有進店那一顆；坐進去選單整個是那間店的、店面那一頁是它；這裡不開門了同步就收（_drop_stale_references 也收）；
    動身也收（Game._depart）。"""
    g = _made(game)
    assert "act:fakeshop" in [o.id for o in g.options()] and g._shop_open() is None
    seams.in_shop = True
    assert [o.id for o in g.options()] == ["fake:leave"] and g._shop_open() == "fakeshop"
    seams.shop_here = False
    assert g._shop_open() is None
    g.sync(1060.0)
    assert not seams.in_shop and ("close_shop",) in seams.calls
    seams.in_shop, seams.shop_here = True, False
    Game(g.content, g.state, world=g.world)  # 建 Game 就清失效參照：此地不開了，收
    assert not seams.in_shop
    seams.in_shop, seams.shop_here = True, True
    loc = g.content.locations[g.state.player.location]
    g.travel(next(d for d in loc.connections if d in g.content.locations))
    assert not seams.in_shop


def test_a_closed_shop_gives_no_menu_or_entry_but_still_opens_its_page_and_closes(game, seams):
    """給選項的兩樣（店裡那一串、進店那一顆）關著的包不給；哪一間開著、收店照舊看坐在店裡沒（原位本來就不看開關：酒肆的 enabled 在
    坐著的時候一定是 True）。"""
    seams.open = False
    seams.in_shop = True
    g = _made(game)
    ids = [o.id for o in g.options()]
    assert "fake:leave" not in ids and "act:fakeshop" not in ids
    assert g._shop_open() == "fakeshop"
    seams.shop_here = False
    g.sync(1060.0)
    assert not seams.in_shop
