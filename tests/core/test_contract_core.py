"""核心契約：核心照 FEATURES 問每一包的時機（開發規範手冊 3.3）。用一個假的包（只在這個檔裡登記）驗每個掛鉤真的被叫、
叫的位置與順序；真的包各自守自己的契約在 test_contract_features.py。"""
from __future__ import annotations

import random

import pytest

from conftest import next_season
from tianxia.core import features as features_core
from tianxia.core import registry
from tianxia.core.features import AdminTool, BusHook, DefectHook, EffectHook, Feature, Outcome, Shop, Verb, WorldHook
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


def test_start_threads_asks_every_registered_package_even_a_closed_one(monkeypatch):
    """背景執行緒（全部拆包第 52 批）：殼啟動時照清單問登記的每一包、不看 enabled（那時候還沒有 ctx），參數是殼；不回東西。"""
    one, two = Seams(open_=False), Seams()
    monkeypatch.setattr(registry, "FEATURES", [one, two])
    shell = object()
    assert features_core.start_threads(shell) is None
    assert one.calls == [("threads", shell)] and two.calls == [("threads", shell)]


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
        self.fights = True  # sortie（第 17 批）：fakeverb 那一格按下去打不打仗（Verb.squad）

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

    def on_season_close(self, ctx, reread):  # battle（全部拆包第 8 批）
        self._note("on_season_close", reread)

    def threads(self, shell):  # tale（全部拆包第 52 批）
        self._note("threads", shell)

    def shops(self):
        return (Shop(key="fakeshop", inside=lambda g: self.in_shop, here=lambda g: self.shop_here,
                     close=lambda g: setattr(self, "in_shop", False) or self._note("close_shop"),
                     menu=lambda g: [Option(id="fake:leave", label="出店")],
                     entry=lambda g: Option(id="act:fakeshop", label="假的店") if self.shop_here else None),)

    def verbs(self):
        return (
            Verb("fakeverb", run=lambda g, prepared: ["只打開一張卡。"], title=lambda g: "假的子動詞・此地", picks=("只打開一張卡。",),
                 squad=lambda g: g.content.squads["thug"] if self.fights else None),
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
    assert [o.id for o in g.options()].count("act:fakeshop") == 1 and g._shop_open() is None  # 進店那一顆只有一顆（第 11 批審查）
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


def test_choose_takes_the_unlisted_ones_first_and_hears_the_package_after_each_action(game, seams):
    """choose_unlisted 在查選單、建紀錄之前問（不在選單上的也接得到、不寫江湖紀錄、不走做完一件事那一下）；after_action 在每個動作的
    最後（記下陣營之後、存回季之前），回的話接在動作的話後面。兩個都不問 enabled。"""
    g = _made(game)
    journal = len(g.state.journal)
    assert g.choose("fake:raw") == ["不在選單上的也接得到。"]
    assert len(g.state.journal) == journal and ("after_action",) not in seams.calls
    assert g.choose("fake:do") == ["做了do。", "做完之後的那一句。"]
    assert seams.calls.index(("run", "do")) < seams.calls.index(("after_action",))
    seams.open = False
    assert g.choose("fake:raw") == ["不在選單上的也接得到。"]
    seams.calls.clear()
    g.choose("fake:do")  # 關著：fake:do 不在選單上，「此刻無法這麼做」那一下不走到最後
    assert ("after_action",) not in seams.calls


def test_a_verb_owner_runs_titles_fills_the_cell_and_writes_the_note(game, seams):
    """act 子動詞的主人（Verb）：行動列那一格（探索那一格換成它給的那幾顆）、底下那一行、按下去（_act 最前面）、紀錄的標題（照 arg 問、
    不看 kind，同原本那張表）；按了只打開一張卡的回話不寫江湖紀錄（Verb.picks）。行動列那一格給選項：關著的主人不接；其餘不問 enabled。"""
    g = _made(game)
    assert g.options()[0].id == "act:fakeverb"
    assert g.action_notes(["act:explore"])["act:explore"] == "假的那一行"
    assert g._action_title("act", "fakeverb") == "假的子動詞・此地" and g._action_title("xyz", "fakeverb") == "假的子動詞・此地"
    journal = len(g.state.journal)
    assert g.choose("act:fakeverb") == ["只打開一張卡。", "做完之後的那一句。"]  # 做完一件事那一下照樣接在後面（同約戰那張卡之後的殺手檢查）
    assert len(g.state.journal) == journal
    assert g._act("fakeverb") == ["只打開一張卡。"]
    seams.open = False
    assert "act:fakeverb" not in [o.id for o in g.options()]
    assert g.action_notes(["act:explore"])["act:explore"] == "假的那一行" and g._act("fakeverb") == ["只打開一張卡。"]


# sortie（全部拆包第 17 批「出陣三」：Verb 多開的一格 squad）


def test_a_verb_owner_names_the_squad_its_press_fights(game, seams):
    """這一下打哪一路（Verb.squad）：Game._fight_squad 最前面問 act:<verb> 的主人（大場面判讀、鎖外 A 段、鎖內 C 段的重驗都問它）；
    主人回 None 照舊往下（act: 的其餘幾格往下也是 None）。不問 enabled（同 run、title、note：原位那一支本來就不看開關）。"""
    g = _made(game)
    thug = g.content.squads["thug"]
    assert g._fight_squad("act:fakeverb") is thug
    seams.fights = False
    assert g._fight_squad("act:fakeverb") is None
    seams.fights, seams.open = True, False
    assert g._fight_squad("act:fakeverb") is thug
    assert g._fight_squad("act:challenge:nobody") is None and g._fight_squad("act:nobody") is None  # 沒有主人的照舊往下


def test_the_scene_and_the_report_page_ask_the_packages(game, seams):
    """場景卡：自己眼前的那一張問 scene（_own_scene_text 擂台之後）；蓋在畫面上的問 scene_over（scene_text 最前面：整個取代，或接在上面、
    自己眼前的事接在底下）。戰報頁那一筆問 record_detail。三個都不問 enabled。"""
    g = _made(game)
    seams.open = False
    seams.seated = True
    assert g.scene_text() == "**假的宴席**"
    seams.over = ("**假的戰場**", False)
    assert g.scene_text() == "**假的戰場**\n\n---\n\n**假的宴席**"
    seams.over = ("**假的戰場**", True)
    assert g.scene_text() == "**假的戰場**"
    from tianxia.state import BattleRecord

    g.state.battles = [BattleRecord(id=1, time=0.0, location=g.state.player.location, kind="train", opponent="山賊", ours=[], tier="大勝",
                                    our_power=1.0, difficulty=1.0)]
    assert "換過的對手" in g.battle_detail(1) and "山賊" not in g.battle_detail(1)


def test_the_own_turn_is_heard_even_when_the_package_is_closed(game, seams):
    """on_own_turn 在 own_turn_checks 最前面（暫停的檢查之前：原位的封測發放暫停中照發），關著的包照叫。"""
    g = _made(game)
    seams.open = False
    g.mark_seen(1000.0)
    assert ("on_own_turn",) in seams.calls


# battle（全部拆包第 8 批：收季的收兵）
def test_closing_the_season_asks_the_packages_where_the_old_lines_were(game, seams):
    """收季的收兵（on_season_close）：管理者立刻收季叫一次（reread=False：呼叫端剛讀回收季那一份季）；開下一季只在休季時叫（reread=True：
    收兵之前讀回手上那一份季），季還在進行中按開下一季不叫。不問 enabled（原位那兩段本來就不看包的開關：決戰照內容、攻城照這一季的地盤）。"""
    g = _made(game)
    g.content.config.admins = [g.state.player.name]
    seams.open = False
    seams.calls.clear()
    g.admin_next_season(now=1010.0)  # 還在進行中：不收兵、也開不了下一季
    assert [c for c in seams.calls if c[0] == "on_season_close"] == []
    g.admin_end_season(now=1020.0)
    assert [c for c in seams.calls if c[0] == "on_season_close"] == [("on_season_close", False)]
    seams.calls.clear()
    g.admin_next_season(now=1030.0)
    assert [c for c in seams.calls if c[0] == "on_season_close"] == [("on_season_close", True)]
    assert g.world.get_season_number() == 2


def test_the_own_turn_is_heard_while_the_season_clock_is_paused(game, seams):
    """賽季時鐘暫停中（own_turn_checks 在暫停的檢查那裡就回頭、不掛系統通緝）on_own_turn 照叫：它排在暫停的檢查之前（原位的封測元寶
    暫停中照發，帳跟世界無關；第 11 批審查：挪到暫停的檢查後面，契約與商城包的測試原本都不紅）。"""
    g = _made(game)
    assert g.world.pause_clock(1000.0) and g.world.paused_at() is not None
    seams.calls.clear()
    g.mark_seen(1010.0)
    assert seams.calls.count(("on_own_turn",)) == 1


# core_world（全部拆包第 25 批「世界層掛鉤」；計畫 docs/superpowers/plans/2026-11-05-世界層掛鉤-第25批.md 1.4、Task 2）
class Worldly(Feature):
    """只登記世界層的格的假包；open 是 enabled 的答案（世界層不問它）。"""

    name = "worldly"

    def __init__(self, hooks, open_=True):
        self.hooks, self.open = tuple(hooks), open_

    def enabled(self, ctx):
        return self.open

    def world(self):
        return self.hooks


def test_the_world_order_is_the_table_in_the_plan():
    """順序就是行為：每一個位置的格照換成掛鉤之前的呼叫順序（計畫 1.4），一格不挪。改這張表先過 PM。"""
    assert features_core.WORLD_ORDER == {
        "step": ("bounties", "figures.recover", "figures.revive", "seal_acts", "figure_life", "feast", "plans", "yuedan"),
        "week": ("seats", "orders", "bounties", "stances"),
        "day": ("orders", "bounties", "stances"),
        "start": ("bounties",),
        "close": ("arena",),
        "muster": ("front", "works", "seal", "generals"),
        "open": ("divine", "seal.cache"),
        "retire": ("seal",),
        "next": ("inscriptions", "divine", "seal.mandate", "seal.cache"),
        "life": ("feast",),  # core_world2（全部拆包第 40 批）：figure_life.tick 每一輪每一位對話人物設宴
    }
    assert Feature().world() == ()


def test_a_package_can_only_take_a_slot_on_the_table_and_only_one_package_a_slot(monkeypatch):
    """包登記的格都在表上、同一格只有一包：表外的格（哪一個位置都驗）、沒有的位置、兩包登記同一格，world_hooks 都丟 ValueError；
    核心代叫的打錯字也丟（world_run）。"""
    run = lambda *a: None  # noqa: E731
    monkeypatch.setattr(registry, "FEATURES", [Worldly([WorldHook("step", "nobody", run)])])
    with pytest.raises(ValueError):
        features_core.world_hooks("week")
    monkeypatch.setattr(registry, "FEATURES", [Worldly([WorldHook("nowhere", "feast", run)])])
    with pytest.raises(ValueError):
        features_core.world_hooks("step")
    monkeypatch.setattr(registry, "FEATURES", [Worldly([WorldHook("step", "feast", run)]), Worldly([WorldHook("step", "feast", run)])])
    with pytest.raises(ValueError):
        features_core.world_hooks("step")
    with pytest.raises(ValueError):
        features_core.world_hooks("nowhere")
    monkeypatch.setattr(registry, "FEATURES", [])
    with pytest.raises(ValueError):
        features_core.world_run("step", {"feasts": run}, None, None, None, 1.0)


def test_the_world_layer_calls_its_slots_in_the_table_order(monkeypatch):
    """world_run 照表的順序叫：包登記的兩格（宴客、月旦評，登記的先後跟表相反）夾在核心代叫的格之間；回每一格的回傳值（照順序），
    包的格回 None 照樣在；兩邊都沒有的格跳過。先取好的 hooks 照用、不再問包。"""
    calls = []

    def note(owner, slot, back):
        return lambda *args: calls.append((owner, slot, args)) or back

    pkg = Worldly([WorldHook("step", "yuedan", note("pkg", "yuedan", None)), WorldHook("step", "feast", note("pkg", "feast", None))])
    monkeypatch.setattr(registry, "FEATURES", [pkg])
    core = {slot: note("core", slot, [slot]) for slot in features_core.WORLD_ORDER["step"] if slot not in ("feast", "yuedan", "plans")}
    got = features_core.world_run("step", core, "v", "c", "w", 1.0)
    assert [slot for _, slot, _ in calls] == ["bounties", "figures.recover", "figures.revive", "seal_acts", "figure_life", "feast", "yuedan"]
    assert [owner for owner, _, _ in calls] == ["core"] * 5 + ["pkg", "pkg"] and all(args == ("v", "c", "w", 1.0) for _, _, args in calls)
    assert got == [["bounties"], ["figures.recover"], ["figures.revive"], ["seal_acts"], ["figure_life"], None, None]
    calls.clear()
    monkeypatch.setattr(registry, "FEATURES", [])
    features_core.world_run("step", core, "v", "c", "w", 1.0, hooks=features_core.world_hooks("step") | {"plans": note("pre", "plans", None)})
    assert [slot for _, slot, _ in calls][-2:] == ["figure_life", "plans"] and calls[-1][0] == "pre"


def test_the_world_layer_asks_a_closed_package_too(monkeypatch):
    """世界層不問 enabled（原位那幾行本來就不看包的開關：宴客關著也照散席、擂台只看 arena_ranks.on）：關著的包照樣被叫。"""
    calls = []
    pkg = Worldly([WorldHook("close", "arena", lambda *args: calls.append(args))], open_=False)
    monkeypatch.setattr(registry, "FEATURES", [pkg])
    assert features_core.world_run("close", {}, "state", "content", "store") == [None]
    assert calls == [("state", "content", "store")]


def test_the_world_layer_is_asked_where_the_old_lines_were(game, monkeypatch):
    """接在原本那幾行（Task 4）：同步推世界一步問 step（宴客那一格）；管理者立刻收季問 close（擂台那一格）；開下一季先問 retire
    （舊季收尾）再問 next（題壁照帶），換季之後的季照著走。關著的假包照樣被問。"""
    calls = []

    def note(at, slot, back=None):
        return lambda *args: calls.append((at, slot)) or back

    pkg = Worldly([WorldHook("step", "feast", note("step", "feast")), WorldHook("close", "arena", note("close", "arena")),
                   WorldHook("retire", "seal", note("retire", "seal", False)),
                   WorldHook("next", "inscriptions", note("next", "inscriptions"))], open_=False)
    monkeypatch.setattr(registry, "FEATURES", [pkg])
    g = _made(game)
    g.sync(1060.0)  # 再過一分鐘：世界推一步
    assert ("step", "feast") in calls and ("close", "arena") not in calls
    g.content.config.admins = [g.state.player.name]
    calls.clear()
    g.admin_end_season(now=1020.0)
    assert calls.count(("close", "arena")) == 1
    calls.clear()
    g.admin_next_season(now=1030.0)
    assert [c for c in calls if c[0] in ("retire", "next")] == [("retire", "seal"), ("next", "inscriptions")]
    assert g.world.get_season_number() == 2


# core_effects（全部拆包第 32 批「效果與叛投掛鉤」；計畫 docs/superpowers/plans/2026-11-06-效果與叛投掛鉤-第32批.md 1.2、1.3、Task 2）
class Effectful(Feature):
    """只登記效果與叛投的格的假包；open 是 enabled 的答案（這兩種掛鉤不問它）。"""

    name = "effectful"

    def __init__(self, effects=(), defection=(), open_=True):
        self.fx, self.dx, self.open = tuple(effects), tuple(defection), open_

    def enabled(self, ctx):
        return self.open

    def effects(self):
        return self.fx

    def defection(self):
        return self.dx


def test_the_effect_and_defection_orders_are_the_tables_in_the_plan():
    """順序就是行為：一則效果一段一格、叛投那一刻四個位置，都照換成掛鉤之前的先後（計畫 1.2、1.3），一格不挪；每一格認領的效果欄位
    照計畫 2.1。改這幾張表先過 PM。"""
    assert features_core.EFFECT_ORDER == (
        "text", "stats", "materials", "insights", "gear", "stamina", "affinity",
        "patron", "grain", "fs_fragments", "runic", "event_mods", "summons_next", "promote",
        "flags", "learn_skills", "join_sect", "leave_sect", "recruit", "trend", "world_flags", "marks",
        "foreshadow", "rumor", "chronicle", "shard", "story",
    )
    assert features_core.EFFECT_FIELDS == {
        "text": ("text",), "stats": ("stats",), "materials": ("materials",), "insights": ("insights",), "gear": ("gear",),
        "stamina": ("stamina",), "affinity": ("affinity",), "patron": ("patron",), "grain": ("donate_grain",),
        "fs_fragments": ("fs_fragments",), "runic": ("runic",), "event_mods": ("event_mods",), "summons_next": ("summons_next",),
        "promote": ("promote", "followers"), "flags": ("flags_add", "flags_remove"), "learn_skills": ("learn_skills",),
        "join_sect": ("join_sect",), "leave_sect": ("leave_sect",), "recruit": ("recruit",), "trend": ("trend",),
        "world_flags": ("world_flags_add",), "marks": ("marks",), "foreshadow": ("clue_items", "fs_counters"),
        "rumor": ("rumor",), "chronicle": ("chronicle",), "shard": (), "story": ("story",),
    }
    assert features_core.DEFECT_ORDER == {
        "clear": ("progress", "convoy", "hints", "opportunities"),
        "leave": ("plots",),
        "stranded": ("bounties",),
        "after": ("leave_behind", "parley"),
    }
    assert Feature().effects() == () and Feature().defection() == ()


def test_every_effect_field_belongs_to_exactly_one_slot():
    """照效果欄位分派給主人：EFFECT_FIELDS 的格就是 EFFECT_ORDER（同一個先後）；併起來＝models.Effect 的欄位扣掉 apply_effect 不讀的
    next_event（串接是事件檢定的事）、contribution（只准寫在隨口應對的分岔上），沒有一個欄位歸兩格。Effect 多一個欄位就紅：先想好歸哪一格。"""
    from tianxia.models import Effect

    assert tuple(features_core.EFFECT_FIELDS) == features_core.EFFECT_ORDER
    claimed = [field for fields in features_core.EFFECT_FIELDS.values() for field in fields]
    assert len(claimed) == len(set(claimed))
    assert set(claimed) == set(Effect.model_fields) - {"next_event", "contribution"}


def test_a_package_can_only_take_an_effect_or_defection_slot_on_the_table_and_only_one_package_a_slot(monkeypatch):
    """包登記的格都在表上、同一格只有一包：表外的格、沒有的位置、兩包（或同一包兩次）登記同一格，effect_hooks／defect_hooks 都丟
    ValueError（叛投那邊哪一個位置都驗）；核心代叫的打錯字、沒有的位置也丟（effect_run、defect_run）。"""
    run = lambda *a: None  # noqa: E731
    monkeypatch.setattr(registry, "FEATURES", [Effectful([EffectHook("nobody", run)])])
    with pytest.raises(ValueError):
        features_core.effect_hooks()
    monkeypatch.setattr(registry, "FEATURES", [Effectful([EffectHook("story", run)]), Effectful([EffectHook("story", run)])])
    with pytest.raises(ValueError):
        features_core.effect_hooks()
    monkeypatch.setattr(registry, "FEATURES", [Effectful([EffectHook("story", run), EffectHook("story", run)])])
    with pytest.raises(ValueError):
        features_core.effect_hooks()
    monkeypatch.setattr(registry, "FEATURES", [Effectful(defection=[DefectHook("clear", "nobody", run)])])
    with pytest.raises(ValueError):
        features_core.defect_hooks("after")
    monkeypatch.setattr(registry, "FEATURES", [Effectful(defection=[DefectHook("nowhere", "convoy", run)])])
    with pytest.raises(ValueError):
        features_core.defect_hooks("clear")
    monkeypatch.setattr(registry, "FEATURES", [Effectful(defection=[DefectHook("clear", "convoy", run)]),
                                               Effectful(defection=[DefectHook("clear", "convoy", run)])])
    with pytest.raises(ValueError):
        features_core.defect_hooks("clear")
    monkeypatch.setattr(registry, "FEATURES", [])
    with pytest.raises(ValueError):
        features_core.defect_hooks("nowhere")
    with pytest.raises(ValueError):
        features_core.effect_run({"stroy": run}, None)
    with pytest.raises(ValueError):
        features_core.defect_run("clear", {"convoys": run}, None)
    with pytest.raises(ValueError):
        features_core.defect_run("nowhere", {}, None)


def test_the_effect_and_defection_slots_are_called_in_the_table_order(monkeypatch):
    """effect_run、defect_run 照表的順序叫：包登記的兩格（登記的先後跟表相反）夾在核心代叫的格之間；回每一格的回傳值（照順序）；
    兩邊都沒有的格跳過；包登記了的格就不叫核心那一份。先取好的 hooks 照用、不再問包。"""
    calls = []

    def note(owner, slot, back):
        return lambda *args: calls.append((owner, slot, args)) or back

    pkg = Effectful([EffectHook("story", note("pkg", "story", ["s"])), EffectHook("grain", note("pkg", "grain", ["g"]))],
                    [DefectHook("clear", "hints", note("pkg", "hints", None)), DefectHook("clear", "convoy", note("pkg", "convoy", None))])
    monkeypatch.setattr(registry, "FEATURES", [pkg])
    core = {slot: note("core", slot, [slot]) for slot in features_core.EFFECT_ORDER if slot != "shard"}
    got = features_core.effect_run(core, "r")
    order = [slot for slot in features_core.EFFECT_ORDER if slot != "shard"]
    assert [slot for _, slot, _ in calls] == order
    assert all(owner == ("pkg" if slot in ("story", "grain") else "core") for owner, slot, _ in calls)
    assert all(args == ("r",) for _, _, args in calls)
    assert got == [["g"] if slot == "grain" else ["s"] if slot == "story" else [slot] for slot in order]
    calls.clear()
    clear_core = {"progress": note("core", "progress", None), "convoy": note("core", "convoy", None),
                  "opportunities": note("core", "opportunities", None)}
    assert features_core.defect_run("clear", clear_core, "p") == [None, None, None, None]
    assert [(owner, slot) for owner, slot, _ in calls] == [("core", "progress"), ("pkg", "convoy"), ("pkg", "hints"), ("core", "opportunities")]
    assert all(args == ("p",) for _, _, args in calls)
    calls.clear()
    monkeypatch.setattr(registry, "FEATURES", [])
    features_core.effect_run({"text": note("core", "text", [])}, "r", hooks={"story": note("pre", "story", [])})
    assert [(owner, slot) for owner, slot, _ in calls] == [("core", "text"), ("pre", "story")]
    calls.clear()
    assert features_core.defect_run("after", {"leave_behind": note("core", "leave_behind", ["x"])}, "ctx", "side") == [["x"]]
    assert calls == [("core", "leave_behind", ("ctx", "side"))]


def test_the_effect_and_defection_slots_ask_a_closed_package_too(monkeypatch):
    """效果與叛投的格不問 enabled（原位那幾段本來就不看包的開關：一條線關著也照記記號、押糧關著也照清）：關著的包照樣被叫。"""
    calls = []
    pkg = Effectful([EffectHook("story", lambda r: calls.append(("story", r)) or ["一步"])],
                    [DefectHook("after", "parley", lambda ctx, side: calls.append(("parley", ctx, side)) or ["食言"])], open_=False)
    monkeypatch.setattr(registry, "FEATURES", [pkg])
    assert features_core.effect_run({}, "r") == [["一步"]]
    assert features_core.defect_run("after", {}, "ctx", "huang") == [["食言"]]
    assert calls == [("story", "r"), ("parley", "ctx", "huang")]


def _sided_game():
    """叛投要兩軍：正式內容（測試內容沒有陣營），官軍的人站在黃巾的投靠點。"""
    from conftest import real_content

    content = real_content()
    content.config.auto_open_first_season, content.config.train_event_chance = True, 0.0
    g = Game.new(content, "甲", rng=random.Random(0))
    g.state.player.faction, g.state.player.location = "guan", "huangjin_camp"
    return g


def test_apply_effect_asks_the_effect_slots(game, monkeypatch):
    """接在原本那一段的位置（Task 4）：rules.apply_effect 一則帶 story 的效果，登記了 story 那一格的包被叫（拿到這一下的 EffectRun），
    換掉 FEATURES 之後一條線包那一格不叫（紀念物沒收）；照真的 FEATURES，一條線包那一格照原本收紀念物、回「收進行囊」那一句。"""
    from tianxia import rules
    from tianxia.models import Effect, StoryStep

    real = list(registry.FEATURES)
    calls = []
    pkg = Effectful([EffectHook("story", lambda r: calls.append(r) or ["一步"])], open_=False)
    monkeypatch.setattr(registry, "FEATURES", [pkg])
    effect = Effect(story=StoryStep(line="沒開過的線", keepsake="木牌"))
    p = game.state.player
    assert rules.apply_effect(effect, game.state, game.content, game.world) == ["一步"]
    assert len(calls) == 1 and isinstance(calls[0], rules.EffectRun)
    assert (calls[0].effect, calls[0].state, calls[0].content, calls[0].world) == (effect, game.state, game.content, game.world)
    assert "木牌" not in p.keepsakes
    monkeypatch.setattr(registry, "FEATURES", real)
    assert rules.apply_effect(effect, game.state, game.content, game.world) == ["（收進行囊：木牌）"]
    assert p.keepsakes[-1] == "木牌"


def test_clear_progress_asks_the_clear_slots_in_the_table_order(game, monkeypatch):
    """defection.clear_progress（測試直接叫它）照 DEFECT_ORDER["clear"] 走：叛投自己的（progress：_clear_own）→ 押糧、提示 → 機緣；
    每一格拿到同一個 PlayerState。四格都是包登記的（機緣第 34 批起、progress 第 35 批起由陣營包登記），核心代叫的一格都不剩：
    假包自己登記這四格（登記的先後跟表相反），驗的是照表的先後。"""
    from tianxia import defection

    calls = []

    def note(slot):
        return lambda *args: calls.append((slot, args))

    # 機緣那一格第 34 批起也是包登記的（原本是核心代叫、換掉 opportunities.clear）：四格合起來照表的先後，登記的先後跟表相反
    pkg = Effectful(defection=[DefectHook("clear", "opportunities", note("opportunities")), DefectHook("clear", "hints", note("hints")),
                               DefectHook("clear", "convoy", note("convoy")),
                               # progress 那一格第 35 批起也是包登記的（陣營包；原本是核心代叫、換掉 defection._clear_own）
                               DefectHook("clear", "progress", note("progress"))], open_=False)
    monkeypatch.setattr(registry, "FEATURES", [pkg])
    p = game.state.player
    defection.clear_progress(p)
    assert calls == [("progress", (p,)), ("convoy", (p,)), ("hints", (p,)), ("opportunities", (p,))]


def test_defecting_asks_the_leave_stranded_and_after_slots_where_the_old_lines_were(monkeypatch):
    """defection.defect：清完、改投之前問 leave（密謀），「你叛出…」那一句之後問 stranded（懸賞，回話接在最後）；陣營包 defect_actions.defect_step
    確定那一支（第 35 批前是 Game._defect_step）：defection.defect 之後問 after——同伴回江湖（leave_behind，第 35 批起陣營包登記；原本核心代叫
    Game._leave_behind）、再食言（parley，人物情誼包登記），回話照這個先後接。關著的假包照樣被問。"""
    from tianxia import defection
    from tianxia.features.faction import defect_actions

    g = _sided_game()
    calls = []

    def note(slot, back):
        return lambda *args: calls.append((slot, args)) or back

    pkg = Effectful(defection=[DefectHook("stranded", "bounties", note("bounties", ["懸賞作廢"])),
                               DefectHook("leave", "plots", note("plots", None)),
                               DefectHook("after", "parley", note("parley", ["食言"])),
                               # leave_behind 那一格第 35 批起是陣營包登記的（原本是核心代叫 Game._leave_behind、測試換掉實例上的方法）
                               DefectHook("after", "leave_behind",
                                          lambda ctx, side: calls.append(("leave_behind", (side,))) or ["回江湖"])], open_=False)
    monkeypatch.setattr(registry, "FEATURES", [pkg])
    huang = g.content.scenario.faction("huang")
    msgs = defection.defect(g.state, g.content, huang)
    assert calls == [("plots", (g.state,)), ("bounties", (g.state, g.content, "huang"))]
    assert msgs[-2:] == ["你叛出官軍，投了黃巾軍。", "懸賞作廢"] and g.state.player.faction == "huang"
    calls.clear()
    g2 = _sided_game()
    g2.state.player.pending_defect = "huang"
    monkeypatch.setattr(defection, "refusal", lambda *args, **kwargs: None)
    monkeypatch.setattr(defection, "defect", lambda *args, **kwargs: ["叛投了"])
    assert defect_actions.defect_step(g2, "confirm") == ["叛投了", "回江湖", "食言"]
    assert calls == [("leave_behind", ("huang",)), ("parley", (g2, "huang"))]


def test_the_core_and_the_packages_take_every_effect_and_defection_slot_exactly_once():
    """核心代叫的格（rules._EFFECT_CORE；叛投那邊只剩 defection._STRANDED_CORE——_CLEAR_CORE、_LEAVE_CORE 與 engine._DEFECT_AFTER_CORE
    第 35 批拿掉，那幾格改由包登記）與包登記的格（照真的 FEATURES）合起來剛好是表上的格、沒有重疊：沒有一格默默不跑、也沒有一格兩邊都寫。
    誰登記哪一格照計畫 1.4。"""
    from tianxia import defection, rules

    own = features_core.effect_hooks()
    assert not own.keys() & rules._EFFECT_CORE.keys()
    assert own.keys() | rules._EFFECT_CORE.keys() == set(features_core.EFFECT_ORDER)
    core = {"clear": {}, "leave": {}, "stranded": defection._STRANDED_CORE, "after": {}}  # clear、after 第 35 批起全是包登記的（陣營包）
    assert core.keys() == features_core.DEFECT_ORDER.keys()
    for at, order in features_core.DEFECT_ORDER.items():
        mine = features_core.defect_hooks(at)
        assert not mine.keys() & core[at].keys(), at
        assert mine.keys() | core[at].keys() == set(order), at
    fs = features_core.registered()
    assert {f.name: [h.slot for h in f.effects()] for f in fs if f.effects()} == {
        "story": ["story"], "military": ["grain", "fs_fragments", "foreshadow"],
        "seal": ["runic", "shard"]}  # 全部拆包第 27 批：符文殘片、舊鏈的玉璽碎片改由玉璽包登記（rules._EFFECT_CORE 少這兩格）
    assert {f.name: [(h.at, h.slot) for h in f.defection()] for f in fs if f.defection()} == {
        "military": [("clear", "convoy"), ("clear", "opportunities"), ("leave", "plots")], "guide": [("clear", "hints")], "companions": [("after", "parley")],
        "faction": [("clear", "progress"), ("after", "leave_behind")],
        "bounties": [("stranded", "bounties")]}  # 全部拆包第 45 批：原本陣營包 defection._STRANDED_CORE 代叫，換主人


# core_eventbus（全部拆包第 26 批「事件機制」；計畫 docs/superpowers/plans/2026-11-06-事件機制-第26批.md 1.2、2.1、Task 2）
class Bussy(Feature):
    """只登記事件的格的假包；open 是 enabled 的答案（事件不問它）。"""

    name = "bussy"

    def __init__(self, hooks, open_=True):
        self.hooks, self.open = tuple(hooks), open_

    def enabled(self, ctx):
        return self.open

    def bus(self):
        return self.hooks


def test_the_bus_order_is_the_table_in_the_plan():
    """順序就是行為：每一種事件的格照換成事件之前一行裡的呼叫先後（計畫 1.2），一格不挪——同一下兩個訂閱者的先後就是回話與存檔寫入的先後
    （outing：打探懸賞→撿玉璽碎片；arrive：交糧車→護送懸賞；計畫 1.9 調了就抓得到）。改這張表先過 PM。"""
    assert features_core.BUS_ORDER == {
        "win": ("bounties",),
        "outing": ("bounties", "seal"),
        "explore": ("bounties",),
        "arrive": ("convoy", "bounties"),
        "raid_win": ("bounties",),
        "aid": ("bounties",),  # 全部拆包第 45 批：人物託付開成事件（PM 點頭，只加這一列）
        "battle_end": ("seal",),
    }
    assert Feature().bus() == ()


def test_a_package_can_only_take_an_event_slot_on_the_table_and_only_one_package_a_slot(monkeypatch):
    """包登記的格都在表上、同一格只有一包：表外的格（哪一種事件都驗）、沒有的事件、兩包（或同一包兩次）登記同一格，bus_hooks 都丟
    ValueError；核心代叫的打錯字、沒有這一種事件也丟（bus_run）。"""
    run = lambda *a: None  # noqa: E731
    monkeypatch.setattr(registry, "FEATURES", [Bussy([BusHook("arrive", "nobody", run)])])
    with pytest.raises(ValueError):
        features_core.bus_hooks("win")
    monkeypatch.setattr(registry, "FEATURES", [Bussy([BusHook("nothing", "bounties", run)])])
    with pytest.raises(ValueError):
        features_core.bus_hooks("win")
    monkeypatch.setattr(registry, "FEATURES", [Bussy([BusHook("arrive", "convoy", run)]), Bussy([BusHook("arrive", "convoy", run)])])
    with pytest.raises(ValueError):
        features_core.bus_hooks("arrive")
    monkeypatch.setattr(registry, "FEATURES", [Bussy([BusHook("outing", "seal", run), BusHook("outing", "seal", run)])])
    with pytest.raises(ValueError):
        features_core.bus_hooks("outing")
    monkeypatch.setattr(registry, "FEATURES", [])
    with pytest.raises(ValueError):
        features_core.bus_hooks("nothing")
    with pytest.raises(ValueError):
        features_core.bus_run("win", {"bounty": run}, "ctx", "loc", "squad")
    with pytest.raises(ValueError):
        features_core.bus_run("nothing", {}, "ctx")
    with pytest.raises(ValueError):
        features_core.bus_run("nothing", {}, "ctx", hooks={})


def test_the_bus_calls_its_slots_in_the_table_order(monkeypatch):
    """bus_run 照表的順序叫：包登記的那一格（arrive 的護送懸賞、outing 的撿碎片，各自排在核心代叫的那一格之後）照表、不照登記的先後；
    回每一格的回傳值（照順序）；兩邊都沒有的格跳過；包登記了的格就不叫核心那一份。先取好的 hooks 照用、不再問包。"""
    calls = []

    def note(owner, slot, back):
        return lambda *args: calls.append((owner, slot, args)) or back

    pkg = Bussy([BusHook("outing", "seal", note("pkg", "seal", ["碎片"])), BusHook("arrive", "bounties", note("pkg", "bounties", ["護送"]))])
    monkeypatch.setattr(registry, "FEATURES", [pkg])
    core = {"convoy": note("core", "convoy", ["糧車"]), "bounties": note("core", "bounties", ["不該叫"])}
    assert features_core.bus_run("arrive", core, "ctx", "loc") == [["糧車"], ["護送"]]
    assert calls == [("core", "convoy", ("ctx", "loc")), ("pkg", "bounties", ("ctx", "loc"))]
    calls.clear()
    assert features_core.bus_run("outing", {"bounties": note("core", "bounties", ["打探"])}, "ctx", "loc") == [["打探"], ["碎片"]]
    assert [(owner, slot) for owner, slot, _ in calls] == [("core", "bounties"), ("pkg", "seal")]
    calls.clear()
    assert features_core.bus_run("outing", {}, "ctx", "loc") == [["碎片"]]
    assert calls == [("pkg", "seal", ("ctx", "loc"))]
    calls.clear()
    monkeypatch.setattr(registry, "FEATURES", [])
    assert features_core.bus_run("arrive", {}, "ctx", "loc") == []
    assert calls == []
    got = features_core.bus_run("arrive", {"bounties": note("core", "bounties", [])}, "ctx", "loc",
                                hooks={"convoy": note("pre", "convoy", ["糧車"])})
    assert got == [["糧車"], []] and [(owner, slot) for owner, slot, _ in calls] == [("pre", "convoy"), ("core", "bounties")]


def test_the_bus_returns_what_each_slot_returns_and_asks_a_closed_package_too(monkeypatch):
    """事件不問 enabled（原位那幾行本來就不看包的開關：押糧、懸賞、玉璽的判斷都在被叫的函式裡）：關著的包照樣被叫；battle_end 的格回 None
    照樣在回傳值裡（不接是發布點的事）。"""
    calls = []
    pkg = Bussy([BusHook("battle_end", "seal", lambda *args: calls.append(args)),
                 BusHook("raid_win", "bounties", lambda ctx, target: calls.append((ctx, target)) or ["通緝"])], open_=False)
    monkeypatch.setattr(registry, "FEATURES", [pkg])
    assert features_core.bus_run("battle_end", {}, "ctx", "battle", "definition", "result") == [None]
    assert features_core.bus_run("raid_win", {}, "ctx", "某人") == [["通緝"]]
    assert calls == [("ctx", "battle", "definition", "result"), ("ctx", "某人")]


def _every_bus_slot(calls):
    """登記事件表上每一格的假包（關著）：叫到就記 (事件, 格, 參數)，回一句「事件/格」（battle_end 回 None，同玉璽那一格）。"""
    def note(event, slot):
        return lambda *args: calls.append((event, slot, args)) or (None if event == "battle_end" else [f"{event}/{slot}"])

    return Bussy([BusHook(event, slot, note(event, slot)) for event, slots in features_core.BUS_ORDER.items() for slot in slots], open_=False)


def _won(tier="大勝"):
    """這一場照 tier 打完（team.fight 帶 tier，同 tests/battle/test_drill_gates_engine.py）。"""
    from unittest import mock

    from tianxia import team
    from tianxia.encounter import EncounterResult

    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


def test_the_core_publish_points_ask_the_bus(game, monkeypatch):
    """接在原本那一行（Task 4）：Game._arrive 抵達一站（arrive：交糧車→護送，回話接在地點描寫之後）、_squad_encounter 打贏（win：不是野怪）、
    _raid_bounty（raid_win，回話寫成懸賞榜那一則）、舊探索 explore_base.explore（explore，回話接在最後）各發一次自己那一種，參數是 ctx 加原本
    那幾個；換掉 FEATURES 之後核心代叫的懸賞那一格不叫。野怪那一場不發 win。"""
    import ast
    import inspect

    from tianxia.features.battle import progress
    from tianxia.features.explore import explore_base

    calls = []
    monkeypatch.setattr(registry, "FEATURES", [_every_bus_slot(calls)])
    got = game._arrive("lake")
    assert calls == [("arrive", "convoy", (game, "lake")), ("arrive", "bounties", (game, "lake"))]
    assert got[1:3] == ["arrive/convoy", "arrive/bounties"]
    calls.clear()
    with _won():
        game._squad_encounter("thug", wild=True)
        assert calls == []
        game._squad_encounter("thug")
    assert calls == [("win", "bounties", (game, "lake", "thug"))]
    calls.clear()
    assert game._raid_bounty("某人") == ["raid_win/bounties"]
    assert calls == [("raid_win", "bounties", (game, "某人"))]
    calls.clear()
    assert explore_base.explore(game)[-1] == "explore/bounties"
    assert calls == [("explore", "bounties", (game, "lake"))]
    calls.clear()
    # 決戰收場：發布點在 progress.settle_showdown 改完戰報那一列、讀回季之前（那一行照原位，回傳不接）；發一次看格與參數
    assert game.publish("battle_end", "battle", "definition", "result") == []
    assert calls == [("battle_end", "seal", (game, "battle", "definition", "result"))]
    body = ast.parse(inspect.getsource(progress.settle_showdown)).body[0].body
    at = next(i for i, stmt in enumerate(body) if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
              and ast.unparse(stmt.value.func) == "ctx.publish")
    assert ast.unparse(body[at]) == "ctx.publish('battle_end', battle, definition, result)"
    assert ast.unparse(body[at - 1]) == "ctx.world.mutate_battle(_relabel)"
    assert ast.unparse(body[at + 1]) == "ctx.state.world = ctx.world.get_season()"


def test_the_explore_package_publishes_the_win_and_the_outing(monkeypatch):
    """出門一趟（正式內容的探索一顆）：遭遇打贏（不是城裡）發 win，收尾發 outing（打探懸賞→撿玉璽碎片，回話照這個先後接）；
    參數是 ctx 加地點（win 多一個對手）。"""
    from unittest import mock

    from jianfa_kit import jianfa_game, ready

    from tianxia import explore_one
    from tianxia.features.explore import explore_actions

    game = ready(jianfa_game(), side="guan", loc="yingchuan_wilds", level=20)
    plan = game.outing_plan()
    assert plan.how == "foe"
    calls = []
    monkeypatch.setattr(registry, "FEATURES", [_every_bus_slot(calls)])
    with mock.patch.object(explore_one, "draw", return_value="encounter"), _won():
        got = explore_actions.explore_one(game)
    here = ("yingchuan_wilds",)
    assert calls == [("win", "bounties", (game, *here, plan.foe.id)), ("outing", "bounties", (game, *here)), ("outing", "seal", (game, *here))]
    lines = [line for line in got if line in ("outing/bounties", "outing/seal")]
    assert lines == ["outing/bounties", "outing/seal"]


def test_the_core_and_the_packages_take_every_event_slot_exactly_once():
    """核心代叫的格（engine._BUS_CORE）與包登記的格（照真的 FEATURES）合起來剛好是表上的格、沒有重疊：沒有一格默默不跑、也沒有一格兩邊
    都寫。包登記的是軍情包的交糧車（計畫 1.5）與玉璽包的撿碎片、收場（全部拆包第 27 批：_BUS_CORE 的 outing 只剩 bounties、battle_end 空了）。"""
    from tianxia import engine

    assert engine._BUS_CORE.keys() == features_core.BUS_ORDER.keys()
    for event, order in features_core.BUS_ORDER.items():
        mine = features_core.bus_hooks(event)
        assert not mine.keys() & engine._BUS_CORE[event].keys(), event
        assert mine.keys() | engine._BUS_CORE[event].keys() == set(order), event
    fs = features_core.registered()
    assert {f.name: [(h.event, h.slot) for h in f.bus()] for f in fs if f.bus()} == {
        "military": [("arrive", "convoy")], "seal": [("outing", "seal"), ("battle_end", "seal")],
        # 全部拆包第 45 批：懸賞榜包登記六格（原本 engine._BUS_CORE 那五格，加 aid），_BUS_CORE 每一列都空了
        "bounties": [("win", "bounties"), ("outing", "bounties"), ("explore", "bounties"), ("arrive", "bounties"), ("raid_win", "bounties"), ("aid", "bounties")]}


def test_the_core_slots_look_up_the_old_functions_when_called(game, monkeypatch):
    """懸賞榜包那幾格在叫的那一下才照模組屬性找（bounties.on_*，舊名是包 rules 的別名，全部拆包第 45 批換主人、第一個參數改 ctx）：換掉的照樣打得到；照真的 FEATURES，抵達那一刻先交糧車（軍情包那一格，也照模組屬性找）再護送，探索收尾先打探懸賞再撿碎片、決戰收場叫玉璽
    （全部拆包第 27 批：玉璽包那兩格照包的模組屬性找 actions.seal_find、actions.settle，原本是 Game 上的 _seal_find、_seal_settle）。"""
    from tianxia import bounties
    from tianxia.features.military import convoy_actions
    from tianxia.features.seal import actions as seal_actions

    calls = []

    def note(name, back):
        return lambda *args: calls.append((name, args)) or back

    for name in ("on_win", "on_explore", "on_arrive", "on_raid_win"):
        monkeypatch.setattr(bounties, name, note(name, [name]))
    monkeypatch.setattr(convoy_actions, "convoy_arrives", note("convoy_arrives", ["糧車"]))
    monkeypatch.setattr(seal_actions, "seal_find", note("seal_find", ["碎片"]))
    monkeypatch.setattr(seal_actions, "settle", note("settle", None))
    assert game.publish("win", "lake", "thug") == ["on_win"]
    assert game.publish("outing", "lake") == ["on_explore", "碎片"]
    assert game.publish("explore", "lake") == ["on_explore"]
    assert game.publish("arrive", "lake") == ["糧車", "on_arrive"]
    assert game.publish("raid_win", "某人") == ["on_raid_win"]
    assert game.publish("battle_end", "battle", "definition", "result") == []
    assert calls == [
        ("on_win", (game, "lake", "thug")),
        ("on_explore", (game, "lake")), ("seal_find", (game, "lake")),
        ("on_explore", (game, "lake")),
        ("convoy_arrives", (game, "lake")), ("on_arrive", (game, "lake")),
        ("on_raid_win", (game, "某人")),
        ("settle", (game, "battle", "definition", "result")),
    ]


# core_step（全部拆包第 36 批「你這一步」；計畫 docs/superpowers/plans/2026-11-06-你這一步-第36批.md 1.2、2.1、Task 2）
class Stepper(Feature):
    """只登記「你這一步」的格的假包；open 是 enabled 的答案（「你這一步」不問它）。"""

    name = "stepper"

    def __init__(self, hooks, open_=True):
        self.hooks, self.open = tuple(hooks), open_

    def enabled(self, ctx):
        return self.open

    def steps(self):
        return self.hooks


def _no_items(ctx, status, orders):
    return []


def test_the_step_order_is_the_table_in_the_plan():
    """順序就是行為：七格照換成掛鉤之前 weekcard._steps 一段一段接的先後（計畫 1.2：託付 → 委託 → 軍令 → 揭了的懸賞 → 伏筆 → 新手目標 →
    去投靠），一格不挪——卡上的先後與「換一件事」從哪一件排起（計畫 1.9：相鄰的兩格對調都抓得到）。改這張表先過 PM。包預設不登記。"""
    assert features_core.STEP_ORDER == ("errand", "commission", "order", "bounty", "foreshadow", "newbie", "join")
    assert Feature().steps() == ()


def test_a_package_can_only_take_a_step_slot_on_the_table_and_only_one_package_a_slot(monkeypatch):
    """包登記的格都在表上、同一格只有一包：表外的格（章回不是表上的一格）、兩包（或同一包兩次）登記同一格，step_hooks 都丟 ValueError；
    核心代叫的寫了表外的格、key 跟 slot 對不上、兩格寫同一個 ref（finish 照 ref 找回那一格），step_table 都丟。"""
    step = features_core.StepHook
    monkeypatch.setattr(registry, "FEATURES", [Stepper([step("chapter", _no_items)])])
    with pytest.raises(ValueError):
        features_core.step_hooks()
    with pytest.raises(ValueError):
        features_core.step_table({})
    monkeypatch.setattr(registry, "FEATURES", [Stepper([step("order", _no_items, "order")]), Stepper([step("order", _no_items, "order")])])
    with pytest.raises(ValueError):
        features_core.step_hooks()
    monkeypatch.setattr(registry, "FEATURES", [Stepper([step("join", _no_items, "join"), step("join", _no_items, "join")])])
    with pytest.raises(ValueError):
        features_core.step_hooks()
    monkeypatch.setattr(registry, "FEATURES", [])
    assert features_core.step_hooks() == {} and features_core.step_table({}) == []
    with pytest.raises(ValueError):
        features_core.step_table({"chapter": step("chapter", _no_items)})
    with pytest.raises(ValueError):
        features_core.step_table({"bounty": step("commission", _no_items, "errand")})
    with pytest.raises(ValueError):
        features_core.step_table({"commission": step("commission", _no_items, "errand"), "bounty": step("bounty", _no_items, "errand")})
    with pytest.raises(ValueError):
        features_core.step_places({"commission": step("commission", _no_items, "errand"), "bounty": step("bounty", _no_items, "errand")})
    monkeypatch.setattr(registry, "FEATURES", [Stepper([step("order", _no_items, "bounty")])])  # 包的格跟核心那一份寫同一個 ref
    with pytest.raises(ValueError):
        features_core.step_table({"bounty": step("bounty", _no_items, "bounty")})


def test_the_step_table_puts_its_slots_in_the_table_order(monkeypatch):
    """step_table 照表的順序排：包登記的格（登記的先後故意倒過來）與核心代叫的那一份穿插，照表、不照登記的先後；包登記了的格就不用核心
    那一份（join）；兩邊都沒有的格（order、foreshadow）跳過。照排好的走一遍叫 items(ctx, status, orders)，叫到的順序＝表、參數照傳。"""
    calls = []

    def note(owner, slot):
        return lambda ctx, status, orders: calls.append((owner, slot, (ctx, status, orders))) or [{"kind": slot}]

    step = features_core.StepHook
    pkg = Stepper([step("join", note("pkg", "join"), "join"), step("newbie", note("pkg", "newbie"), "newbie"), step("errand", note("pkg", "errand"))])
    monkeypatch.setattr(registry, "FEATURES", [pkg])
    core = {"commission": step("commission", note("core", "commission"), "errand"), "bounty": step("bounty", note("core", "bounty"), "bounty"),
            "join": step("join", note("core", "join"), "join")}
    table = features_core.step_table(core)
    assert [h.slot for h in table] == ["errand", "commission", "bounty", "newbie", "join"]
    out = []
    for hook in table:
        out += hook.items("ctx", "status", "orders")
    assert [x["kind"] for x in out] == ["errand", "commission", "bounty", "newbie", "join"]
    assert calls == [(owner, slot, ("ctx", "status", "orders")) for owner, slot in
                     [("pkg", "errand"), ("core", "commission"), ("core", "bounty"), ("pkg", "newbie"), ("pkg", "join")]]
    monkeypatch.setattr(registry, "FEATURES", [])
    assert [h.slot for h in features_core.step_table(core)] == ["commission", "bounty", "join"]


def test_the_steps_ask_a_closed_package_too(monkeypatch):
    """「你這一步」不問 enabled（原位那幾行本來就不看包的開關：託付看 errands.on、軍令看 orders_view 回了什麼、新手目標看 status["newbie"]，
    判斷都在被叫的函式裡）：關著的包照樣排進表、照樣補目標。"""
    step = features_core.StepHook
    pkg = Stepper([step("foreshadow", lambda ctx, status, orders: [{"kind": "foreshadow"}], "foreshadow", lambda ctx, ref: ("fs", None, None))],
                  open_=False)
    monkeypatch.setattr(registry, "FEATURES", [pkg])
    assert features_core.step_hooks().keys() == {"foreshadow"}
    assert [h.items("ctx", {}, []) for h in features_core.step_table({})] == [[{"kind": "foreshadow"}]]
    assert features_core.step_places({})["foreshadow"]("ctx", ("foreshadow",)) == ("fs", None, None)


def test_the_step_places_list_only_the_slots_with_a_ref_and_a_place(monkeypatch):
    """step_places 是 {ref: place}（照 ref、不照格：委託那一格的 ref 是 errand）：沒有 ref（人物的託付自己帶 target）或沒有 place 的格不列。"""
    step = features_core.StepHook

    def place(ctx, ref):
        return ref[1], None, None

    monkeypatch.setattr(registry, "FEATURES", [Stepper([step("errand", _no_items), step("order", _no_items, "order", place),
                                                        step("newbie", _no_items, "newbie")])])
    got = features_core.step_places({"commission": step("commission", _no_items, "errand", place)})
    assert got == {"errand": place, "order": place}
    assert list(got) == ["errand", "order"]


def _every_step_slot(items_calls, place_calls):
    """登記「你這一步」表上每一格的假包（關著）：items 記 (格, ctx, status, orders)、回一件 kind＝格名（託付那一格自己帶 target、不掛 _ref，
    同人物情誼包）；place 記 (格, ctx, ref)、照格回 (id, target, then)：委託三樣都有、軍令 target 是 None（不給 then）、懸賞 id 是 None（不寫 id）。"""
    from tianxia import step as step_rules

    back = {"commission": ("c1", {"location": "c"}, {"location": "c2"}), "order": ("o1", None, {"location": "o2"}),
            "bounty": (None, {"location": "b"}, None), "foreshadow": ("f1", {"location": "f"}, None),
            "newbie": ("n1", {"location": "n"}, None), "join": ("j1", {"location": "j"}, None)}
    refs = {"commission": "errand", "order": "order", "bounty": "bounty", "foreshadow": "foreshadow", "newbie": "newbie", "join": "join"}

    def items(slot):
        def run(ctx, status, orders):
            items_calls.append((slot, ctx, status, orders))
            if slot == "errand":
                return [{"kind": slot, "text": slot, "id": "e1", "target": {"location": "e"}}]
            return [{"kind": slot, "text": slot, step_rules.REF: (refs[slot], slot)}]
        return run

    def place(slot):
        return lambda ctx, ref: place_calls.append((slot, ctx, ref)) or back[slot]

    hooks = [features_core.StepHook(slot, items(slot), refs.get(slot), place(slot) if slot in refs else None) for slot in features_core.STEP_ORDER]
    return Stepper(hooks, open_=False)


def test_the_week_card_asks_the_step_slots_with_the_shells_status_and_orders(monkeypatch):
    """真的本週卡（weekcard.week_card，server.main_view 叫的那一個）問「你這一步」的掛鉤：換掉 FEATURES、假包登記七格（關著），每一格的 items
    照表的順序叫一次，參數是 ctx 與殼傳進來的那一份 status、orders（同一個物件，不重算）；四勝利開著時 finish 照每一件 _ref 的第一個字叫到
    寫它那一格的 place（委託那一格的 ref 是 errand），(id, target, then) 照原本的規矩寫進那一件（target 是 None 不給 then、id 是 None 不寫、
    _ref 拿掉），自己帶 target 的託付照留、不叫 place。四勝利關著時一格的 place 都不叫，只拿掉 _ref。"""
    from wins_kit import wins_game

    from tianxia import step as step_rules
    from tianxia import weekcard

    game = wins_game(faction="guan", at="changshe")
    assert step_rules.on(game)
    status, orders = game.status_data(), [{"id": "殼算好的軍令"}]
    items_calls, place_calls = [], []
    monkeypatch.setattr(registry, "FEATURES", [_every_step_slot(items_calls, place_calls)])
    rows = [r for r in weekcard.week_card(game, status, orders)["steps"] if r["kind"] != "chapter"]
    assert [(slot, ctx is game, got is status, given is orders) for slot, ctx, got, given in items_calls] == [
        (slot, True, True, True) for slot in features_core.STEP_ORDER]
    assert [(slot, ctx is game, ref) for slot, ctx, ref in place_calls] == [
        ("commission", True, ("errand", "commission")), ("order", True, ("order", "order")), ("bounty", True, ("bounty", "bounty")),
        ("foreshadow", True, ("foreshadow", "foreshadow")), ("newbie", True, ("newbie", "newbie")), ("join", True, ("join", "join"))]
    assert rows == [
        {"kind": "errand", "text": "errand", "id": "e1", "target": {"location": "e"}},
        {"kind": "commission", "text": "commission", "target": {"location": "c"}, "id": "c1", "then": {"location": "c2"}},
        {"kind": "order", "text": "order", "target": None, "id": "o1"},
        {"kind": "bounty", "text": "bounty", "target": {"location": "b"}},
        {"kind": "foreshadow", "text": "foreshadow", "target": {"location": "f"}, "id": "f1"},
        {"kind": "newbie", "text": "newbie", "target": {"location": "n"}, "id": "n1"},
        {"kind": "join", "text": "join", "target": {"location": "j"}, "id": "j1"},
    ]
    items_calls.clear()
    place_calls.clear()
    monkeypatch.setattr(step_rules, "on", lambda game: False)  # 四勝利關著（或季收了）：finish 只拿掉 _ref
    rows = [r for r in weekcard.week_card(game, status, orders)["steps"] if r["kind"] != "chapter"]
    assert [slot for slot, *_ in items_calls] == list(features_core.STEP_ORDER) and place_calls == []
    assert rows[1:] == [{"kind": slot, "text": slot} for slot in features_core.STEP_ORDER[1:]]


def test_the_core_and_the_packages_take_every_step_slot_exactly_once():
    """核心代叫的格（step._STEP_CORE：第 45 批懸賞榜成包之後空了）與包登記的格（照真的 FEATURES）合起來剛好是表上的格、沒有重疊、ref 不重複：
    沒有一格默默不排、也沒有一格兩邊都寫。主人照計畫 1.2 量的：託付是人物情誼包、委託與懸賞是懸賞榜包、軍令與伏筆是軍情包、新手目標是新手引導包、去投靠是陣營包；
    有 ref 的格都有 place（託付自己帶 target，兩個都沒有）。"""
    from tianxia import step as step_rules

    mine = features_core.step_hooks()
    assert not mine.keys() & step_rules._STEP_CORE.keys()
    assert mine.keys() | step_rules._STEP_CORE.keys() == set(features_core.STEP_ORDER)
    assert set(step_rules._STEP_CORE) == set()  # 全部拆包第 45 批：commission、bounty 換主人
    table = features_core.step_table(step_rules._STEP_CORE)
    assert [h.slot for h in table] == list(features_core.STEP_ORDER)
    assert [h.ref for h in table] == [None, "errand", "order", "bounty", "foreshadow", "newbie", "join"]
    assert all((h.ref is None) == (h.place is None) for h in table)
    fs = features_core.registered()
    assert {f.name: [h.slot for h in f.steps()] for f in fs if f.steps()} == {
        "companions": ["errand"], "military": ["order", "foreshadow"], "guide": ["newbie"], "faction": ["join"],
        "bounties": ["commission", "bounty"]}  # 全部拆包第 45 批


def test_the_step_slots_look_up_their_functions_when_called(monkeypatch):
    """每一格在叫的那一下才照模組屬性找（懸賞榜兩格找舊名 tianxia.bounties，第 45 批成了包 rules 的別名；包的格找自己的模組）：換掉的照樣打得到，參數照傳
    （軍令那一格拿殼傳進來的 orders、新手目標那一格拿 status；託付、伏筆、去投靠讀 ctx 上的 state 與 content）。"""
    from wins_kit import wins_game

    from tianxia import bounties
    from tianxia import step as step_rules
    from tianxia.features.companions import errands
    from tianxia.features.faction import join_actions
    from tianxia.features.guide import actions as guide_actions
    from tianxia.features.military import fs_rules, order_actions

    game = wins_game(faction="guan", at="changshe")
    calls = []

    def note(name, back):
        return lambda *args: calls.append((name, args)) or back

    s, c = game.state, game.content
    monkeypatch.setattr(errands, "step_items", note("errands.step_items", []))
    monkeypatch.setattr(order_actions, "step_items", note("order_actions.step_items", []))
    monkeypatch.setattr(fs_rules, "next_step", note("fs_rules.next_step", None))
    monkeypatch.setattr(guide_actions, "newbie_step_items", note("guide_actions.newbie_step_items", []))
    monkeypatch.setattr(join_actions, "join_step_items", note("join_actions.join_step_items", []))
    status, orders = {"bounties": [], "newbie": None}, ["軍令"]
    assert step_rules.items(game, status, orders) == []
    assert calls == [("errands.step_items", (s, c)), ("order_actions.step_items", (game, orders)), ("fs_rules.next_step", (s, c)),
                     ("guide_actions.newbie_step_items", (game, status)), ("join_actions.join_step_items", (game,))]
    calls.clear()
    monkeypatch.setattr(bounties, "open_commissions", note("bounties.open_commissions", []))
    monkeypatch.setattr(bounties, "rallies", note("bounties.rallies", []))
    monkeypatch.setattr(fs_rules, "next_trip", note("fs_rules.next_trip", None))
    rows = step_rules.finish(game, [{"kind": "errand", "text": "x", step_rules.REF: ("errand", "沒有這一張")},
                                    {"kind": "foreshadow", "text": "y", step_rules.REF: ("foreshadow",)}])
    assert rows == [{"kind": "errand", "text": "x", "target": None, "id": "沒有這一張"}, {"kind": "foreshadow", "text": "y", "target": None}]
    assert calls == [("bounties.open_commissions", (s, c)), ("bounties.rallies", (s, c)), ("fs_rules.next_trip", (s, c))]


# core_world2（全部拆包第 40 批「世界模型二」；計畫 docs/superpowers/plans/2026-11-06-世界模型二-第40批.md 1.6、2.4、Task 4）：世界層多一個位置
# life（figure_life.tick 每一輪每一位對話人物設宴，宴客包登記；核心不代叫）。figure_life 收進共用規則層之後不 import 宴客包。
def test_the_life_slot_runs_only_when_a_package_takes_it_and_asks_a_closed_one_too(monkeypatch):
    """life 那一格核心不代叫（core 傳 {}）：包沒登記（契約測試換掉 FEATURES）時不跑、回空串；登記了照 registered() 問、不看 enabled
    （原位本來就不看宴客包的開關：maybe_open 自己判 on），收到 (state, content, cid, turn)。真的宴客包登記的那一格就是 rules.maybe_open
    （叫的那一下才照模組屬性找：換掉 feasts.maybe_open 照樣打得到）。"""
    from tianxia import feasts

    real = registry.FEATURES
    monkeypatch.setattr(registry, "FEATURES", [])
    assert features_core.world_run("life", {}, "state", "content", "cid", 3) == []
    calls = []
    monkeypatch.setattr(registry, "FEATURES", [Worldly([WorldHook("life", "feast", lambda *args: calls.append(args))], open_=False)])
    assert features_core.world_run("life", {}, "state", "content", "cid", 3) == [None]
    assert calls == [("state", "content", "cid", 3)]
    monkeypatch.setattr(registry, "FEATURES", real)
    calls.clear()
    monkeypatch.setattr(feasts, "maybe_open", lambda *args: calls.append(args))
    assert sorted(features_core.world_hooks("life")) == ["feast"]
    features_core.world_run("life", {}, "state", "content", "cid", 3)
    assert calls == [("state", "content", "cid", 3)]


def test_figure_life_opens_feasts_through_the_life_slot_one_figure_at_a_time(monkeypatch):
    """figure_life.tick 的先後照換之前：每一位對話人物先設宴（life 那一格）、再求援（_maybe_rally），一位一位穿插，照人物表的順序；
    life 那一格一輪只問一次包（world_hooks）。包沒登記時只剩求援。"""
    from conftest import real_content

    from tianxia import figure_life
    from tianxia.state import GameState, PlayerState
    from tianxia.world_state import fresh_season

    c = real_content()
    s = GameState(player=PlayerState(name="甲", location=c.scenario.start_location, stats={}, stamina=0), world=fresh_season(c))
    assert figure_life.on(c)
    talkers = [cid for cid, ch in c.characters.items() if ch.deep_interaction]
    assert len(talkers) >= 2
    calls = []
    monkeypatch.setattr(figure_life, "_act", lambda *args: None)
    monkeypatch.setattr(figure_life, "_follow", lambda *args: None)
    monkeypatch.setattr(figure_life, "_maybe_rally", lambda state, content, cid, turn: calls.append(("rally", cid, turn)))
    asked = []
    real_hooks = features_core.world_hooks
    monkeypatch.setattr(features_core, "world_hooks", lambda at: asked.append(at) or real_hooks(at))
    monkeypatch.setattr(registry, "FEATURES", [Worldly([WorldHook("life", "feast", lambda st, co, cid, turn: calls.append(("feast", cid, turn)))],
                                                       open_=False)])

    def tick_at(turn):
        s.world.time = turn * figure_life.period(c, s.world)
        s.world.life_turn = turn - 1
        figure_life.tick(s, c)

    tick_at(5)
    assert calls == [(kind, cid, 5) for cid in talkers for kind in ("feast", "rally")]
    assert asked == ["life"]
    calls.clear()
    monkeypatch.setattr(registry, "FEATURES", [])
    tick_at(6)
    assert calls == [("rally", cid, 6) for cid in talkers]


# shell_web（全部拆包第 66 批；計畫 docs/superpowers/plans/2026-11-06-網頁殼化-第66批.md 第四節）：狀態列與江湖畫面的格
class Slotter(Feature):
    """只登記狀態列格的假包；open 是 enabled 的答案（狀態列的格不問它）。"""

    name = "slotter"

    def __init__(self, hooks, open_=True):
        self.hooks, self.open = tuple(hooks), open_

    def enabled(self, ctx):
        return self.open

    def status_slots(self):
        return self.hooks


def test_the_status_order_is_the_table_in_the_plan():
    """順序就是行為（JSON 鍵的先後閘門逐位元組比，叫的先後也算）：一格不挪。改這張表先過 PM。"""
    assert features_core.STATUS_ORDER == {
        "status": ("head", "bounties", "manual", "seal", "armament", "forge_manual", "create", "ascension", "self", "newbie", "vitals", "journey",
                   "calendar", "help", "checkin", "war", "invites"),
        "main": ("screen", "outing", "say_max", "sortie", "modes", "action_notes", "sense_help", "on_road", "free_text", "gauges", "journal", "peers",
                 "party", "news", "tales", "admin", "guide", "horse_art", "push", "web_push", "shop", "prep", "milestone", "features", "glow", "fronts",
                 "orders", "week_card", "mostly", "sides_card", "figures_here", "companions", "event_opts", "rumor_layers", "convoy", "conquest",
                 "sortie_cards", "siege", "xingshi", "plan", "place_state", "place_deeds", "letter", "zhuan", "season_result", "ending"),
    }
    assert Feature().status_slots() == ()


def _slot(table, slot, keys=None):
    return features_core.StatusHook(table, slot, lambda ctx, frame: {k: slot for k in (keys or (slot,))})


def test_a_package_can_only_take_a_status_slot_on_the_table_and_only_one_package_a_slot(monkeypatch):
    """表上沒有的表或格、兩包（或同一包兩次）登記同一格，status_hooks 都丟 ValueError（問別的表也丟：每一次都驗全部）；核心代叫的寫了表外的格，status_run 丟。"""
    monkeypatch.setattr(registry, "FEATURES", [Slotter([_slot("status", "nosuch")])])
    with pytest.raises(ValueError):
        features_core.status_hooks("status")
    monkeypatch.setattr(registry, "FEATURES", [Slotter([_slot("nosuch", "head")])])
    with pytest.raises(ValueError):
        features_core.status_hooks("status")
    monkeypatch.setattr(registry, "FEATURES", [Slotter([_slot("main", "plan")]), Slotter([_slot("main", "plan")])])
    with pytest.raises(ValueError):
        features_core.status_hooks("status")
    monkeypatch.setattr(registry, "FEATURES", [Slotter([_slot("main", "plan"), _slot("main", "plan")])])
    with pytest.raises(ValueError):
        features_core.status_hooks("main")
    monkeypatch.setattr(registry, "FEATURES", [])
    assert features_core.status_hooks("status") == {} and features_core.status_hooks("main") == {}
    with pytest.raises(ValueError):
        features_core.status_hooks("nosuch")
    with pytest.raises(ValueError):
        features_core.status_run("status", {"nosuch": lambda ctx, frame: {}}, {}, None)


def test_the_status_run_goes_down_the_table_and_merges_the_keys_in_that_order(monkeypatch):
    """照表叫、不照 FEATURES：包的優先、否則核心，兩邊都沒有跳過；關著的包照叫；回的鍵照順序合；status 表的 frame 就是合到一半的那一份。"""
    monkeypatch.setattr(registry, "FEATURES", [Slotter([_slot("status", "war"), _slot("status", "seal", ("seal_duel", "seal"))], open_=False), Slotter([_slot("status", "head")])])
    seen = []

    def manual(ctx, frame):
        seen.append(list(frame))
        return {"manual": 1}

    out = features_core.status_run("status", {"manual": manual, "head": lambda ctx, frame: {"core_head": True}, "vitals": lambda ctx, frame: {}}, {}, None)
    assert list(out) == ["head", "manual", "seal_duel", "seal", "war"] and "core_head" not in out
    assert seen == [["head"]]


def test_the_main_table_merges_into_the_view_of_the_frame(monkeypatch):
    """main 表的 frame 是 MainFrame：鍵合進 frame.view，回的就是那一份；一格可以看 frame 上別的東西、改已經合進去的（glow 那一格）。"""
    monkeypatch.setattr(registry, "FEATURES", [Slotter([_slot("main", "guide"),
                                                        features_core.StatusHook("main", "glow", lambda ctx, frame: frame.view.update(guide="改過") or {})])])
    frame = features_core.MainFrame({}, [], None, {}, None)
    out = features_core.status_run("main", {"screen": lambda ctx, f: {"status": f.status}}, frame, None)
    assert out is frame.view and list(out) == ["status", "guide"] and out["guide"] == "改過"
    assert frame.orders == []


@pytest.mark.parametrize("bad", [None, "字串", [("鍵", 1)]])
def test_a_status_slot_must_answer_with_a_dict(monkeypatch, bad):
    """沒有鍵回 {}；回別的（None、字串、串列）丟 TypeError，不默默少鍵。"""
    monkeypatch.setattr(registry, "FEATURES", [Slotter([features_core.StatusHook("status", "head", lambda ctx, frame: bad)])])
    with pytest.raises(TypeError):
        features_core.status_run("status", {}, {}, None)
