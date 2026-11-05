"""核心契約：核心照 FEATURES 問每一包的時機（開發規範手冊 3.3）。用一個假的包（只在這個檔裡登記）驗每個掛鉤真的被叫、
叫的位置與順序；真的包各自守自己的契約在 test_contract_features.py。"""
from __future__ import annotations

import random

import pytest

from conftest import next_season
from tianxia.core import features as features_core
from tianxia.core import registry
from tianxia.core.features import AdminTool, DefectHook, EffectHook, Feature, Outcome, Shop, Verb, WorldHook
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
    """defection.clear_progress（測試直接叫它）照 DEFECT_ORDER["clear"] 走：叛投自己的（_clear_own）→ 包登記的押糧、提示（登記的先後跟表
    相反）→ 機緣（第 34 批起也是包登記的）；每一格拿到同一個 PlayerState。核心代叫的只剩 progress 一格，在叫的那一下才照模組屬性找（換掉照樣打得到）。"""
    from tianxia import defection

    calls = []

    def note(slot):
        return lambda *args: calls.append((slot, args))

    # 機緣那一格第 34 批起也是包登記的（原本是核心代叫、換掉 opportunities.clear）：四格合起來照表的先後，登記的先後跟表相反
    pkg = Effectful(defection=[DefectHook("clear", "opportunities", note("opportunities")), DefectHook("clear", "hints", note("hints")),
                               DefectHook("clear", "convoy", note("convoy"))], open_=False)
    monkeypatch.setattr(registry, "FEATURES", [pkg])
    monkeypatch.setattr(defection, "_clear_own", note("progress"))
    p = game.state.player
    defection.clear_progress(p)
    assert calls == [("progress", (p,)), ("convoy", (p,)), ("hints", (p,)), ("opportunities", (p,))]


def test_defecting_asks_the_leave_stranded_and_after_slots_where_the_old_lines_were(monkeypatch):
    """defection.defect：清完、改投之前問 leave（密謀），「你叛出…」那一句之後問 stranded（懸賞，回話接在最後）；Game._defect_step 確定那一支：
    defection.defect 之後問 after——同伴回江湖（核心代叫 Game._leave_behind）、再食言（包登記），回話照這個先後接。關著的假包照樣被問。"""
    from tianxia import defection

    g = _sided_game()
    calls = []

    def note(slot, back):
        return lambda *args: calls.append((slot, args)) or back

    pkg = Effectful(defection=[DefectHook("stranded", "bounties", note("bounties", ["懸賞作廢"])),
                               DefectHook("leave", "plots", note("plots", None)),
                               DefectHook("after", "parley", note("parley", ["食言"]))], open_=False)
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
    monkeypatch.setattr(g2, "_leave_behind", lambda side: calls.append(("leave_behind", (side,))) or ["回江湖"])
    assert g2._defect_step("confirm") == ["叛投了", "回江湖", "食言"]
    assert calls == [("leave_behind", ("huang",)), ("parley", (g2, "huang"))]


def test_the_core_and_the_packages_take_every_effect_and_defection_slot_exactly_once():
    """核心代叫的格（rules._EFFECT_CORE；defection._CLEAR_CORE、_LEAVE_CORE、_STRANDED_CORE；engine._DEFECT_AFTER_CORE）與包登記的格
    （照真的 FEATURES）合起來剛好是表上的格、沒有重疊：沒有一格默默不跑、也沒有一格兩邊都寫。誰登記哪一格照計畫 1.4。"""
    from tianxia import defection, engine, rules

    own = features_core.effect_hooks()
    assert not own.keys() & rules._EFFECT_CORE.keys()
    assert own.keys() | rules._EFFECT_CORE.keys() == set(features_core.EFFECT_ORDER)
    core = {"clear": defection._CLEAR_CORE, "leave": defection._LEAVE_CORE, "stranded": defection._STRANDED_CORE,
            "after": engine._DEFECT_AFTER_CORE}
    assert core.keys() == features_core.DEFECT_ORDER.keys()
    for at, order in features_core.DEFECT_ORDER.items():
        mine = features_core.defect_hooks(at)
        assert not mine.keys() & core[at].keys(), at
        assert mine.keys() | core[at].keys() == set(order), at
    fs = features_core.registered()
    assert {f.name: [h.slot for h in f.effects()] for f in fs if f.effects()} == {
        "story": ["story"], "military": ["grain", "fs_fragments", "foreshadow"]}
    assert {f.name: [(h.at, h.slot) for h in f.defection()] for f in fs if f.defection()} == {
        "military": [("clear", "convoy"), ("clear", "opportunities"), ("leave", "plots")], "guide": [("clear", "hints")], "companions": [("after", "parley")]}
