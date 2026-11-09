"""核心契約：核心照 FEATURES 問每一包的時機（開發規範手冊 3.3）。用一個假的包（只在這個檔裡登記）驗每個掛鉤真的被叫、
叫的位置與順序；真的包各自守自己的契約在 test_contract_features.py。"""
from __future__ import annotations

import random

import pytest

from conftest import next_season
from tianxia.core import features as features_core
from tianxia.core import registry
from tianxia.core.features import AdminTool, BusHook, DefectHook, EffectHook, Feature, MenuHook, Outcome, SceneHook, SeamHook, Shop, Verb, WorldHook
from tianxia.core.option import Option, Refused
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


def test_main_and_menxia_actions_merge_and_refuse_the_same_name_twice(monkeypatch):
    """shell_server（全部拆包第 68 批）：殼的兩張動作表照包分，同 admin_tools：不看 enabled、兩包同名丟例外，參數是殼。"""
    seen = []

    class Pack(Feature):
        name = "fake_pack"

        def enabled(self, ctx):
            raise AssertionError("殼建表時沒有 ctx，不問 enabled")

        def main_actions(self, shell):
            seen.append(shell)
            return {"fake_go": lambda g, b: ["走。"]}

        def menxia_actions(self, shell):
            seen.append(shell)
            return {"fake_sit": lambda g, b: ["坐。"]}

    shell = object()
    monkeypatch.setattr(registry, "FEATURES", [Pack(), Feature()])
    assert list(features_core.main_actions(shell)) == ["fake_go"] and list(features_core.menxia_actions(shell)) == ["fake_sit"]
    assert seen == [shell, shell]
    monkeypatch.setattr(registry, "FEATURES", [Pack(), Pack()])
    with pytest.raises(ValueError):
        features_core.main_actions(shell)
    with pytest.raises(ValueError):
        features_core.menxia_actions(shell)


def _outlock_pack(ops=None, slots=()):
    """一包假的鎖外工作：ops 照給、jobs 一格一條（slots）；殼建表時沒有 ctx，問 enabled 就炸。"""
    class Pack(Feature):
        name = "fake_pack"

        def enabled(self, ctx):
            raise AssertionError("殼建表時沒有 ctx，不問 enabled")

        def outlock(self, shell):
            return features_core.Outlock(
                ops=dict(ops or {}), jobs=tuple(features_core.OutlockJob(s, lambda g: None, lambda g, got: None) for s in slots),
            )

    return Pack()


def test_outlock_merges_ops_and_refuses_the_same_op_twice(monkeypatch):
    """shell_server（全部拆包第 69 批）：鎖外的 op 同 main_actions：不看 enabled、兩包同名丟例外；基底的包是空的。"""
    go = lambda g, b: ["走。"]  # noqa: E731
    assert Feature().outlock(object()) == features_core.Outlock()
    monkeypatch.setattr(registry, "FEATURES", [_outlock_pack({"fake_go": go}), Feature()])
    assert features_core.outlock_ops(object()) == {"fake_go": go}
    monkeypatch.setattr(registry, "FEATURES", [_outlock_pack({"fake_go": go}), _outlock_pack({"fake_go": go})])
    with pytest.raises(ValueError):
        features_core.outlock_ops(object())


def test_outlock_jobs_follow_the_written_order_and_refuse_what_does_not_add_up(monkeypatch):
    """背景寫字照 OUTLOCK_ORDER 排（不照 FEATURES 的先後）；表外的格接在表尾、照登記的先後（第二輪第 74 批）；兩包同格、表上沒人登記都丟例外。"""
    order = features_core.OUTLOCK_ORDER
    assert order == ("tale", "crowd", "chatter", "letter", "yuedan", "xingshi")
    monkeypatch.setattr(registry, "FEATURES", [_outlock_pack(slots=order[3:]), Feature(), _outlock_pack(slots=reversed(order[:3]))])
    assert [job.slot for job in features_core.outlock_jobs(object())] == list(order)
    monkeypatch.setattr(registry, "FEATURES", [_outlock_pack(slots=("fake_slot", "fake_later")), _outlock_pack(slots=reversed(order))])
    assert [job.slot for job in features_core.outlock_jobs(object())] == [*order, "fake_slot", "fake_later"]
    for packs in (
        [_outlock_pack(slots=order), _outlock_pack(slots=order[:1])],  # 兩包同格
        [_outlock_pack(slots=(*order, "fake_slot")), _outlock_pack(slots=("fake_slot",))],  # 表外的格一樣不能兩包同格
        [_outlock_pack(slots=order[1:])],  # 表上沒人登記
    ):
        monkeypatch.setattr(registry, "FEATURES", packs)
        with pytest.raises(ValueError):
            features_core.outlock_jobs(object())


def test_action_table_keeps_the_written_order_and_refuses_what_does_not_add_up():
    """action_table：照寫死的 order 排（核心與包穿插）、回普通 dict；order 上沒人提供、核心與包同名都丟例外；order 外的接在後面。"""
    a, b, c, d = (lambda g, body: [name] for name in "abcd")
    table = features_core.action_table(("x", "y", "z"), {"y": b}, {"z": c, "x": a, "later": d})
    assert type(table) is dict and list(table) == ["x", "y", "z", "later"]
    assert (table["x"], table["y"], table["z"], table["later"]) == (a, b, c, d)
    with pytest.raises(ValueError):
        features_core.action_table(("x", "gone"), {}, {"x": a})
    with pytest.raises(ValueError):
        features_core.action_table(("x",), {"x": a}, {"x": b})
    assert features_core.no_gate() is None  # 沒有總開關的管理者工具：什麼都不擋


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

    def scenes(self):  # core_scene（第二輪第 91 批）：原本的 scene 掛鉤
        return (SceneHook("own", "feast", lambda ctx: "**假的宴席**" if self.seated else None),)

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


def test_the_shop_page_asks_the_packages_even_a_closed_one_and_takes_the_first_answer(monkeypatch):
    """店面那一頁（第二輪第 93 批）：features.shop_page 問每一包，第一個不是 None 的回去；不問 enabled（原本的分派不看開關）；沒有包認是 None。"""
    class Pack(Feature):
        name = "pack"

        def enabled(self, ctx) -> bool:
            return False

        def shop_view(self, ctx, shop):
            return {"shop": shop, "ctx": ctx} if shop == "fakeshop" else None

    monkeypatch.setattr(registry, "FEATURES", [Feature(), Pack()])
    assert features_core.shop_page("這個 ctx", "fakeshop") == {"shop": "fakeshop", "ctx": "這個 ctx"}
    assert features_core.shop_page("這個 ctx", "別間") is None


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
    """場景卡：自己眼前的那一張問 scenes 登記的格（SCENE_ORDER["own"]）；蓋在畫面上的問 scene_over（scene_text 最前面：整個取代，或接在上面、
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
    from tianxia.features.faction import defection

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
    from tianxia.features.faction import defection
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
    from tianxia.features.faction import defection
    from tianxia import rules

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
        "raid_win": ("bounties", "zongmen"),
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
    """這一場照 tier 打完（team.fight 帶 tier，同 tianxia/features/explore/tests/test_drill_gates_engine.py）。"""
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
    assert game._raid_bounty("某人") == ["raid_win/bounties", "raid_win/zongmen"]
    assert calls == [("raid_win", "bounties", (game, "某人")), ("raid_win", "zongmen", (game, "某人"))]
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

    from tianxia.features.explore import explore_rules as explore_one
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
        "bounties": [("win", "bounties"), ("outing", "bounties"), ("explore", "bounties"), ("arrive", "bounties"), ("raid_win", "bounties"), ("aid", "bounties")],
        # 門派第三批：截殺打贏親傳撿殘頁（Joy 2026-11-08「不錯，按照設計稿動工」）
        "zongmen": [("raid_win", "zongmen")]}


def test_the_core_slots_look_up_the_old_functions_when_called(game, monkeypatch):
    """懸賞榜包那幾格在叫的那一下才照模組屬性找（bounties.on_*，全部拆包第 45 批換主人、第一個參數改 ctx）：換掉的照樣打得到；照真的 FEATURES，抵達那一刻先交糧車（軍情包那一格，也照模組屬性找）再護送，探索收尾先打探懸賞再撿碎片、決戰收場叫玉璽
    （全部拆包第 27 批：玉璽包那兩格照包的模組屬性找 actions.seal_find、actions.settle，原本是 Game 上的 _seal_find、_seal_settle）。"""
    from tianxia.features.bounties import rules as bounties
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
    """每一格在叫的那一下才照模組屬性找（懸賞榜兩格找包的 rules；包的格找自己的模組）：換掉的照樣打得到，參數照傳
    （軍令那一格拿殼傳進來的 orders、新手目標那一格拿 status；託付、伏筆、去投靠讀 ctx 上的 state 與 content）。"""
    from wins_kit import wins_game

    from tianxia.features.bounties import rules as bounties
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
    from tianxia.features.feast import rules as feasts

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


# core_seams（全部拆包第 55 批「補算與換季收接縫」；計畫 docs/superpowers/plans/2026-11-06-補算換季收接縫-第55批.md 一、四、六）
class Seamy(Feature):
    """只登記補算與換季的格的假包；open 是 enabled 的答案（這些格不問它）。"""

    name = "seamy"

    def __init__(self, hooks, open_=True):
        self.hooks, self.open = tuple(hooks), open_

    def enabled(self, ctx):
        return self.open

    def seams(self):
        return self.hooks


def test_the_seam_order_is_the_table_in_the_plan():
    """順序就是行為：每一個位置的格照換成掛鉤之前一行一行的呼叫順序（計畫第一節），連核心自己的段一起列，一格不挪。改這張表先過 PM。"""
    assert features_core.SEAM_ORDER == {
        "local": ("seclusion", "fortune"),
        "sync.heirloom": ("seal",),
        "sync.close": ("smithy", "gear", "shops", "ambush", "arrive"),
        "sync.deliver": ("big_events", "results", "renames", "echoes", "guard", "notices", "conquest", "conquest.deliver", "arena",
                         "marks", "stances", "zhuan", "mail", "plans", "day", "on_sync", "held_gear", "checkin", "partings", "bounties",
                         "plots", "summons", "story", "seat", "enlist", "hints", "party"),
        "advance.arrive": ("arrive",),
        "advance.turn": ("conquest", "conquest.deliver", "due"),
        "advance.held": ("held_gear",),
        "tick": ("conquest", "battle", "seal"),
        "own_turn": ("bounties",),
        "season.carry": ("guide", "ties", "companions", "self", "mall", "sortie", "outlets", "battle", "seal", "rack", "peers", "story", "legacy"),
        "season.grant": ("faction",),
        "stale.first": ("guide",),
        "stale.early": ("cultivation", "resting", "sense", "companions"),
        "stale.mid": ("bounties", "smithy", "gear", "shops", "treasures", "forge", "signature", "seal"),
        "stale.road": ("travel",),
        "stale.late": ("figure_acts",),
    }
    assert Feature().seams() == ()


def test_a_package_can_only_take_a_seam_slot_on_the_table_and_only_one_package_a_slot(monkeypatch):
    """包登記的格都在表上、同一格只有一包：表外的格（哪一個位置都驗）、沒有的位置、兩包（或同一包兩次）登記同一格，seam_hooks 都丟 ValueError；
    核心代叫的打錯字、沒有這個位置也丟（seam_run）。"""
    run = lambda *a: None  # noqa: E731
    monkeypatch.setattr(registry, "FEATURES", [Seamy([SeamHook("local", "nobody", run)])])
    with pytest.raises(ValueError):
        features_core.seam_hooks("tick")
    monkeypatch.setattr(registry, "FEATURES", [Seamy([SeamHook("nothing", "seal", run)])])
    with pytest.raises(ValueError):
        features_core.seam_hooks("tick")
    monkeypatch.setattr(registry, "FEATURES", [Seamy([SeamHook("tick", "seal", run)]), Seamy([SeamHook("tick", "seal", run)])])
    with pytest.raises(ValueError):
        features_core.seam_hooks("tick")
    monkeypatch.setattr(registry, "FEATURES", [Seamy([SeamHook("tick", "seal", run), SeamHook("tick", "seal", run)])])
    with pytest.raises(ValueError):
        features_core.seam_hooks("tick")
    monkeypatch.setattr(registry, "FEATURES", [])
    with pytest.raises(ValueError):
        features_core.seam_hooks("nothing")
    with pytest.raises(ValueError):
        features_core.seam_run("tick", {"sea": run}, "ctx")
    with pytest.raises(ValueError):
        features_core.seam_run("nothing", {}, "ctx")
    with pytest.raises(ValueError):
        features_core.seam_run("nothing", {}, "ctx", hooks={})


def test_the_seams_call_their_slots_in_the_table_order_and_ask_a_closed_package_too(monkeypatch):
    """seam_run 照表的順序叫：包登記的與核心代叫的穿插，照表、不照登記的先後；關著的包照叫（原位不看開關）；那一格的包沒登記就跳過（契約測試換掉 FEATURES 時）。
    回每一格的回傳值。"""
    calls = []

    def note(who, slot, back=None):
        return lambda *args: calls.append((who, slot, args)) or back

    monkeypatch.setattr(registry, "FEATURES", [Seamy(
        [SeamHook("sync.close", "arrive", note("pack", "arrive", ["到了"])), SeamHook("sync.close", "smithy", note("pack", "smithy"))], open_=False)])
    got = features_core.seam_run("sync.close", {"shops": note("core", "shops")}, "ctx")
    assert [(who, slot) for who, slot, _ in calls] == [("pack", "smithy"), ("core", "shops"), ("pack", "arrive")]
    assert got == [None, None, ["到了"]]
    assert all(args == ("ctx",) for _, _, args in calls)
    calls.clear()
    monkeypatch.setattr(registry, "FEATURES", [])
    assert features_core.seam_run("sync.close", {}, "ctx") == []
    assert features_core.seam_run("tick", {}, "ctx", hooks={"seal": note("given", "seal", ["推"])}) == [["推"]]
    assert calls == [("given", "seal", ("ctx",))]


@pytest.mark.parametrize("wrong", ["一句話", ("一句話",), 7, True, {"一句話"}])
def test_seam_lines_takes_lists_or_none_and_refuses_anything_else(monkeypatch, wrong):
    """seam_lines 把每一格回的那幾句接成一串、None 不算；回字串（一個字一個字接進回話）、回 tuple（某個回傳值漏接）當場紅。"""
    monkeypatch.setattr(registry, "FEATURES", [Seamy([
        SeamHook("local", "seclusion", lambda ctx: ["出關"]), SeamHook("local", "fortune", lambda ctx: None)])])
    assert features_core.seam_lines("local", {}, "ctx") == ["出關"]
    monkeypatch.setattr(registry, "FEATURES", [Seamy([
        SeamHook("local", "seclusion", lambda ctx: ["出關"]), SeamHook("local", "fortune", lambda ctx: ["福緣"])])])
    assert features_core.seam_lines("local", {}, "ctx") == ["出關", "福緣"]
    monkeypatch.setattr(registry, "FEATURES", [Seamy([SeamHook("local", "fortune", lambda ctx: wrong)])])
    with pytest.raises(TypeError):
        features_core.seam_lines("local", {}, "ctx")


def _seam_core_slots(at):
    """核心代叫的格：模組層 engine._SEAM_CORE，加 Game._sync_core 回的那兩格（要用 sync 的區域變數）。"""
    from tianxia import engine

    return set(engine._SEAM_CORE.get(at, ())) | (set(Game._sync_core(None, 0.0, None)) if at == "sync.deliver" else set())


def test_the_core_and_the_packages_take_every_seam_slot_exactly_once():
    """核心代叫的格與包登記的格（照真的 FEATURES）合起來剛好是表上的格、沒有重疊：沒有一格默默不跑、也沒有一格兩邊都寫。誰登記哪一格照計畫第二節鎖住。"""
    from tianxia import engine

    assert set(engine._SEAM_CORE) <= set(features_core.SEAM_ORDER)
    for at, order in features_core.SEAM_ORDER.items():
        mine = features_core.seam_hooks(at)
        theirs = _seam_core_slots(at)
        assert not mine.keys() & theirs, at
        assert mine.keys() | theirs == set(order), at
    got = {f.name: sorted((h.at, h.slot) for h in f.seams()) for f in features_core.registered() if f.seams()}
    assert got == {
        "seal": sorted([("sync.heirloom", "seal"), ("stale.mid", "seal"), ("tick", "seal"), ("season.carry", "seal")]),
        "smithy": sorted([("sync.close", "smithy"), ("stale.mid", "smithy")]),
        "gear": sorted([("sync.close", "gear"), ("stale.mid", "gear"), ("sync.deliver", "held_gear"), ("advance.held", "held_gear")]),
        "stamina_plays": [("sync.close", "ambush")],
        "travel": sorted([("sync.close", "arrive"), ("advance.arrive", "arrive"), ("sync.deliver", "party"), ("stale.road", "travel")]),
        "cultivation": sorted([("sync.deliver", "renames"), ("stale.early", "cultivation")]),
        "figure_acts": sorted([("sync.deliver", "guard"), ("stale.late", "figure_acts")]),
        "territory_acts": sorted([("sync.deliver", "conquest"), ("sync.deliver", "conquest.deliver"), ("advance.turn", "conquest"),
                                  ("advance.turn", "conquest.deliver"), ("tick", "conquest")]),
        "bout": [("sync.deliver", "arena")],
        "companions": sorted([("sync.deliver", "stances"), ("sync.deliver", "mail"), ("stale.early", "companions"), ("season.carry", "companions")]),
        "zhuan": [("sync.deliver", "zhuan")],
        "checkin": [("sync.deliver", "checkin")],
        "battle": sorted([("sync.deliver", "partings"), ("tick", "battle"), ("season.carry", "battle")]),
        "bounties": sorted([("sync.deliver", "bounties"), ("own_turn", "bounties"), ("stale.mid", "bounties")]),
        "military": sorted([("sync.deliver", "plots"), ("sync.deliver", "seat")]),
        "story": sorted([("sync.deliver", "story"), ("season.carry", "story")]),
        "guide": sorted([("sync.deliver", "enlist"), ("sync.deliver", "hints"), ("stale.first", "guide"), ("season.carry", "guide")]),
        "sense": [("stale.early", "sense")],
        "seclusion": [("local", "seclusion")],
        "socialize": [("local", "fortune")],
        "faction": [("season.grant", "faction")],
        "mall": [("season.carry", "mall")],
        "sortie": [("season.carry", "sortie")],
        "outlets": [("season.carry", "outlets")],
        "peers": [("season.carry", "peers")],
        "legacy": [("season.carry", "legacy")],
        "craft": [("sync.deliver", "echoes")],  # core_rest
    }


# 回話接得到字的格：其餘照位置回 None
_SEAM_LINES = {("local", "seclusion"), ("local", "fortune"), ("sync.close", "arrive"), ("sync.deliver", "plots"), ("sync.deliver", "seat"),
               ("advance.arrive", "arrive"), ("advance.turn", "conquest"), ("tick", "conquest")}


def _every_seam_slot(calls):
    """登記表上每一格包的格的假包（關著）：叫到就記 (位置, 格, 參數)；回話接得到字的格回一句「位置/格」。"""
    def note(at, slot):
        return lambda *args: calls.append((at, slot, args)) or ([f"{at}/{slot}"] if (at, slot) in _SEAM_LINES else None)

    return Seamy([SeamHook(at, slot, note(at, slot)) for at, order in features_core.SEAM_ORDER.items() for slot in order
                  if slot not in _seam_core_slots(at)], open_=False)


def _package_slots(*places):
    return [(at, slot) for at in places for slot in features_core.SEAM_ORDER[at] if slot not in _seam_core_slots(at)]


def test_the_game_walks_the_seams_at_sync_advance_and_tick(game, monkeypatch):
    """Game.sync、advance、world_tick、own_turn_checks 在位置上問表：先後照表，回話接法照原本（sync：msgs + arrived + 密謀、席次；advance：msgs + arrived）；
    第一次同步（還沒有上次的現實時間）沒有 local；暫停中不掛系統通緝。換掉 FEATURES 之後包的格只叫假包。"""
    calls = []
    monkeypatch.setattr(registry, "FEATURES", [_every_seam_slot(calls)])
    words = {f"{at}/{slot}" for at, slot in _SEAM_LINES}
    game.state.last_real = None
    game.sync(1000.0)
    assert [(at, slot) for at, slot, _ in calls] == _package_slots("sync.heirloom", "sync.close", "sync.deliver")
    calls.clear()
    reply = game.sync(2000.0)
    assert [(at, slot) for at, slot, _ in calls] == _package_slots("sync.heirloom", "local", "sync.close", "sync.deliver")
    assert all(args == (game,) for _, _, args in calls)
    assert [line for line in reply if line in words] == ["local/seclusion", "local/fortune", "sync.close/arrive", "sync.deliver/plots", "sync.deliver/seat"]
    calls.clear()
    reply = game.advance(60.0)
    assert [(at, slot) for at, slot, _ in calls] == _package_slots("local", "advance.arrive", "advance.turn", "advance.held")
    assert [line for line in reply if line in words] == ["local/seclusion", "local/fortune", "advance.turn/conquest", "advance.arrive/arrive"]
    calls.clear()
    reply = game.world_tick(3000.0)
    assert [(at, slot) for at, slot, _ in calls] == _package_slots("tick")
    assert [line for line in reply if line in words] == ["tick/conquest"]
    calls.clear()
    game.own_turn_checks()
    assert [(at, slot) for at, slot, _ in calls] == [("own_turn", "bounties")]
    calls.clear()
    monkeypatch.setattr(game.world, "paused_at", lambda: 1.0)
    game.own_turn_checks()
    assert calls == []


def test_the_game_walks_the_seams_when_it_drops_stale_references(game, monkeypatch):
    """_drop_stale_references：stale.first 排在對齊賽季之前（換季會把陣營清掉，老手要先蓋）、其餘照表；stale.road 拿到所在地被拿掉了沒。"""
    calls = []
    monkeypatch.setattr(registry, "FEATURES", [_every_seam_slot(calls)])
    real = game._reconcile_season
    monkeypatch.setattr(game, "_reconcile_season", lambda: (calls.append(("core", "reconcile", ())), real())[1])
    game._drop_stale_references()
    assert [(at, slot) for at, slot, _ in calls] == [("stale.first", "guide"), ("core", "reconcile"),
                                                     *_package_slots("stale.early", "stale.mid", "stale.road", "stale.late")]
    assert [args for at, _, args in calls if at == "stale.road"] == [(game, False)]
    calls.clear()
    game.state.player.location = "沒有這個地方"
    game._drop_stale_references()
    assert [args for at, _, args in calls if at == "stale.road"] == [(game, True)]
    assert game.state.player.location == game.content.scenario.start_location


def test_the_game_walks_the_seams_at_the_season_turnover(game, monkeypatch):
    """_reset_player_for_new_season：season.carry 跑的時候 self.state 還是舊的（只准讀 old、fresh）、拿到 (ctx, old, fresh)；新的存檔接上、開場那一則之後才 season.grant，
    拿到 (ctx, old)。核心代叫的三格照舊帶（好感度一成、一天幾次）。"""
    from tianxia import journal

    calls, seen = [], []
    monkeypatch.setattr(registry, "FEATURES", [_every_seam_slot(calls)])
    old = game.state
    old.player.affinities = {"某人": 80}
    old.player.pill_day, old.player.pills_today = 77, 3
    number = old.player.season_number + 1
    real_seam_run = features_core.seam_run

    def spy(at, core, *args, hooks=None):
        seen.append((at, game.state is old, game.state.journal[-1].tag if game.state.journal and at == "season.grant" else None))
        return real_seam_run(at, core, *args, hooks=hooks)

    monkeypatch.setattr(features_core, "seam_run", spy)
    game._reset_player_for_new_season(number)
    assert [(at, slot) for at, slot, _ in calls] == _package_slots("season.carry", "season.grant")
    fresh = game.state
    for at, _, args in calls:
        assert args == ((game, old, fresh) if at == "season.carry" else (game, old))
    assert [(at, was_old) for at, was_old, _ in seen] == [("season.carry", True), ("season.grant", False)]
    assert seen[-1][2] == journal.SEASON_START  # 開場那一則已經寫了
    assert fresh is not old and fresh.player.season_number == number
    assert fresh.player.affinities == {"某人": 8}
    assert (fresh.player.pill_day, fresh.player.pills_today) == (77, 3)


# core_seams（全部拆包第 56 批「選單收接縫」；計畫 docs/superpowers/plans/2026-11-06-選單收接縫-第56批.md 一、五、七）
class Menuy(Feature):
    """只登記選單與動身的格的假包；open 是 enabled 的答案（這些格不問它）。"""

    name = "menuy"

    def __init__(self, hooks, open_=True):
        self.hooks, self.open = tuple(hooks), open_

    def enabled(self, ctx):
        return self.open

    def menus(self):
        return self.hooks


def test_the_menu_order_is_the_table_in_the_plan():
    """順序就是行為：每一個位置的格照換成掛鉤之前一行一行的先後（計畫第一節），連核心自己的格一起列，一格不挪。改這張表先過 PM。"""
    assert features_core.MENU_ORDER == {
        "tick": ("seal",),
        "front": ("seal",),
        "rest": ("zhuan",),
        "take": ("duel", "menu", "sense", "story", "talk", "faction", "audience", "bounties", "smithy", "gear", "shops", "omen"),
        "busy": ("seclusion", "arena"),
        "road": ("head", "parley", "halt", "tasks", "arena"),
        "here": ("explore", "train", "challenge", "summons", "story", "sect", "social", "recruit", "move", "lessons", "join", "defect", "lean",
                 "order", "rank2", "rank", "omen", "errand", "invite", "bounties", "smithy", "gear", "shops", "plays", "heal", "donate", "dadian", "rest"),
        "plays": ("head", "aid", "options", "plan"),
        "notes": ("socialize",),
        "idle": ("audience", "bounties", "smithy", "omen", "sense", "duel", "gear", "outlets", "tavern", "arena", "faction"),
        "open": ("arena", "bounties", "smithy", "gear", "shops"),
        "depart": ("bounties", "escort", "smithy", "gear", "shops"),
        "block": ("ended", "prologue", "event", "bout", "talk", "audience", "bounties", "smithy", "gear", "outlets", "tavern", "faction", "omen", "follow", "busy", "ambush"),
        "quick": ("battle", "seal", "duel", "arena", "errand", "canvas"),  # 第 57 批
        "stale": ("lean", "bounties", "market", "recruit", "arena"),  # 第二輪第 92 批
    }
    assert Feature().menus() == ()


def test_a_package_can_only_take_a_menu_slot_on_the_table_and_only_one_package_a_slot(monkeypatch):
    """包登記的格都在表上、同一格只有一包：表外的格（哪一個位置都驗）、沒有的位置、兩包（或同一包兩次）登記同一格，menu_hooks 都丟 ValueError；
    核心代叫的打錯字、沒有這個位置也丟。"""
    run = lambda *a: None  # noqa: E731
    monkeypatch.setattr(registry, "FEATURES", [Menuy([MenuHook("idle", "nobody", run)])])
    with pytest.raises(ValueError):
        features_core.menu_hooks("tick")
    monkeypatch.setattr(registry, "FEATURES", [Menuy([MenuHook("nothing", "seal", run)])])
    with pytest.raises(ValueError):
        features_core.menu_hooks("tick")
    monkeypatch.setattr(registry, "FEATURES", [Menuy([MenuHook("tick", "seal", run)]), Menuy([MenuHook("tick", "seal", run)])])
    with pytest.raises(ValueError):
        features_core.menu_hooks("tick")
    monkeypatch.setattr(registry, "FEATURES", [Menuy([MenuHook("tick", "seal", run), MenuHook("tick", "seal", run)])])
    with pytest.raises(ValueError):
        features_core.menu_hooks("tick")
    monkeypatch.setattr(registry, "FEATURES", [])
    with pytest.raises(ValueError):
        features_core.menu_hooks("nothing")
    for call in (features_core.menu_run, features_core.menu_first, features_core.menu_lines, features_core.menu_any):
        with pytest.raises(ValueError):
            call("tick", {"sea": run}, "ctx")
        with pytest.raises(ValueError):
            call("nothing", {}, "ctx")


def test_the_menu_slots_go_in_the_table_order_and_ask_a_closed_package_too(monkeypatch):
    """menu_run 照表的順序叫：包登記的與核心代叫的穿插，照表、不照登記的先後；關著的包照叫（原位不看開關）；那一格的包沒登記就跳過（契約測試換掉 FEATURES 時）。回每一格的回傳值。"""
    calls = []

    def note(who, slot, back=None):
        return lambda *args: calls.append((who, slot, args)) or back

    monkeypatch.setattr(registry, "FEATURES", [Menuy(
        [MenuHook("depart", "shops", note("pack", "shops", "收")), MenuHook("depart", "bounties", note("pack", "bounties"))], open_=False)])
    got = features_core.menu_run("depart", {"escort": note("core", "escort")}, "ctx")
    assert [(who, slot) for who, slot, _ in calls] == [("pack", "bounties"), ("core", "escort"), ("pack", "shops")]
    assert got == [None, None, "收"]
    assert all(args == ("ctx",) for _, _, args in calls)
    monkeypatch.setattr(registry, "FEATURES", [])
    assert features_core.menu_run("depart", {}, "ctx") == []


def test_menu_first_stops_at_the_first_answer_and_an_empty_list_is_an_answer(monkeypatch):
    """menu_first 一格一格叫，第一個不是 None 就停、後面的不叫。空的 [] 算接管（take：髒存檔的待確認畫面真的是空選單；用 if got 會掉到下一格）、"" 也算（open：坐著、這裡不開門）；都是 None 回 None。"""
    calls = []

    def note(slot, back):
        return lambda *args: calls.append(slot) or back

    monkeypatch.setattr(registry, "FEATURES", [Menuy([
        MenuHook("take", "duel", note("duel", None)), MenuHook("take", "sense", note("sense", [])), MenuHook("take", "omen", note("omen", ["答"]))])])
    assert features_core.menu_first("take", {"menu": note("menu", None)}, "ctx") == []
    assert calls == ["duel", "menu", "sense"]
    monkeypatch.setattr(registry, "FEATURES", [Menuy([MenuHook("open", "arena", note("arena", "")), MenuHook("open", "gear", note("gear", "market"))])])
    assert features_core.menu_first("open", {}, "ctx") == ""
    monkeypatch.setattr(registry, "FEATURES", [Menuy([MenuHook("take", "duel", note("duel", None))])])
    assert features_core.menu_first("take", {}, "ctx") is None


@pytest.mark.parametrize("wrong", [None, "一顆", ("一顆",), 7, True])
def test_menu_lines_takes_only_lists(monkeypatch, wrong):
    """menu_lines 照順序接成一串；格只准回 list：回字串（一個字一個字接進選單）、回 None（有一支漏了 return）、回 tuple 當場紅。"""
    monkeypatch.setattr(registry, "FEATURES", [Menuy([
        MenuHook("busy", "seclusion", lambda ctx: ["出關"]), MenuHook("busy", "arena", lambda ctx: ["擂台"])])])
    assert features_core.menu_lines("busy", {}, "ctx") == ["出關", "擂台"]
    monkeypatch.setattr(registry, "FEATURES", [Menuy([MenuHook("busy", "arena", lambda ctx: wrong)])])
    with pytest.raises(TypeError):
        features_core.menu_lines("busy", {}, "ctx")


def test_menu_any_stops_at_the_first_true(monkeypatch):
    """menu_any 一格一格叫，第一個真值就停、回 True；都不是回 False（Game._idle 拿它接在前五樣後面，回的是 bool）。"""
    calls = []

    def note(slot, back):
        return lambda *args: calls.append(slot) or back

    monkeypatch.setattr(registry, "FEATURES", [Menuy([
        MenuHook("idle", "audience", note("audience", False)), MenuHook("idle", "smithy", note("smithy", 1)), MenuHook("idle", "faction", note("faction", True))])])
    assert features_core.menu_any("idle", {}, "ctx") is True
    assert calls == ["audience", "smithy"]
    monkeypatch.setattr(registry, "FEATURES", [Menuy([MenuHook("idle", "audience", note("audience", False))])])
    assert features_core.menu_any("idle", {}, "ctx") is False


def _menu_core_slots(at):
    """核心代叫的格：engine._MENU_CORE、atlas._BLOCK_CORE、移動包 departure._DEPART_CORE 三份（atlas、departure 沒有 Game；這兩份只有一個位置）。"""
    from tianxia import atlas, engine
    from tianxia.features.travel import departure

    return set({**engine._MENU_CORE, "block": atlas._BLOCK_CORE, "depart": departure._DEPART_CORE}.get(at, ()))


# core_scene（第二輪第 91 批「場景卡收接縫」；計畫 docs/superpowers/plans/2026-11-07-第二輪-第91批.md 第二節）


class Sceney(Feature):
    """只登記場景卡的格的假包；open 是 enabled 的答案（這些格不問它）。"""

    name = "sceney"

    def __init__(self, hooks, open_=True):
        self.hooks, self.open = tuple(hooks), open_

    def enabled(self, ctx):
        return self.open

    def scenes(self):
        return self.hooks


def test_the_scene_order_is_the_table_in_the_plan():
    """順序就是行為：每一個位置的格照換成掛鉤之前 if 鏈一支一支的先後（計畫第二節），連核心自己的格一起列，一格不挪。改這張表先過 PM。"""
    assert features_core.SCENE_ORDER == {
        "own": ("ended", "event", "duel", "arena", "feast", "sense", "story", "talk", "ally", "faction", "defect", "audience", "omen", "road", "place"),
        "art": ("ended", "battle", "event", "bout", "feast", "sense", "talk", "place"),
    }
    assert Feature().scenes() == ()


def test_a_package_can_only_take_a_scene_slot_on_the_table_and_only_one_package_a_slot(monkeypatch):
    """包登記的格都在表上、同一格只有一包：表外的格（哪一個位置都驗）、沒有的位置、兩包（或同一包兩次）登記同一格，scene_hooks 都丟 ValueError；
    核心自己的格打錯字、沒有這個位置也丟。"""
    run = lambda ctx: None  # noqa: E731
    monkeypatch.setattr(registry, "FEATURES", [Sceney([SceneHook("art", "story", run)])])  # 答題不在圖的表上是刻意的
    with pytest.raises(ValueError):
        features_core.scene_hooks("own")
    monkeypatch.setattr(registry, "FEATURES", [Sceney([SceneHook("nothing", "feast", run)])])
    with pytest.raises(ValueError):
        features_core.scene_hooks("own")
    monkeypatch.setattr(registry, "FEATURES", [Sceney([SceneHook("own", "feast", run)]), Sceney([SceneHook("own", "feast", run)])])
    with pytest.raises(ValueError):
        features_core.scene_hooks("own")
    monkeypatch.setattr(registry, "FEATURES", [Sceney([SceneHook("own", "feast", run), SceneHook("own", "feast", run)])])
    with pytest.raises(ValueError):
        features_core.scene_hooks("own")
    monkeypatch.setattr(registry, "FEATURES", [])
    with pytest.raises(ValueError):
        features_core.scene_hooks("nothing")
    with pytest.raises(ValueError):
        features_core.scene_first("own", {"plce": run}, "ctx")
    with pytest.raises(ValueError):
        features_core.scene_first("nothing", {}, "ctx")


def test_the_first_scene_slot_that_answers_takes_the_card_and_an_empty_answer_counts(monkeypatch):
    """scene_first 照表的順序叫：包的與核心的格穿插，照表、不照登記的先後；關著的包照叫（原位不看開關）；第一個不是 None 的就回它、後面的不叫。
    "" 與 {} 也算接管：取名的意境不在了文字就是空字串，不往下掉到地點；{} 是「這個畫面是我的，沒有圖」。那一格的包沒登記就跳過（契約測試換掉 FEATURES 時）。"""
    calls = []

    def note(slot, back=None):
        return lambda ctx: calls.append((slot, ctx)) or back

    hooks = [SceneHook("own", "road", note("road", "路上")), SceneHook("own", "sense", note("sense", "")), SceneHook("own", "duel", note("duel"))]
    monkeypatch.setattr(registry, "FEATURES", [Sceney(hooks, open_=False)])
    assert features_core.scene_first("own", {"ended": note("ended"), "place": note("place", "地點")}, "ctx") == ""
    assert calls == [("ended", "ctx"), ("duel", "ctx"), ("sense", "ctx")]
    monkeypatch.setattr(registry, "FEATURES", [Sceney([SceneHook("art", "bout", lambda ctx: {})])])
    assert features_core.scene_first("art", {"place": lambda ctx: {"kind": "place"}}, "ctx") == {}
    monkeypatch.setattr(registry, "FEATURES", [])
    assert features_core.scene_first("art", {"place": lambda ctx: {"kind": "place"}}, "ctx") == {"kind": "place"}
    assert features_core.scene_first("art", {"ended": lambda ctx: None}, "ctx") is None


def test_the_core_and_the_packages_take_every_scene_slot_exactly_once():
    """核心自己的格與包登記的格（照真的 FEATURES）合起來剛好是表上的格、沒有重疊：沒有一格默默不跑（scene_art 靠整條 own 鏈判斷，少一格圖會蓋錯或不見）、也沒有一格兩邊都寫。誰登記哪一格照計畫第二節鎖住。"""
    from tianxia.core import scene_view

    assert scene_view.OWN_CORE.keys() == {"ended", "event", "place"}
    assert scene_view.ART_CORE.keys() == {"ended", "event", "place"}
    for at, theirs in (("own", scene_view.OWN_CORE), ("art", scene_view.ART_CORE)):
        mine = features_core.scene_hooks(at)
        assert not mine.keys() & theirs.keys(), at
        assert mine.keys() | theirs.keys() == set(features_core.SCENE_ORDER[at]), at
    got = {f.name: sorted((h.at, h.slot) for h in f.scenes()) for f in features_core.registered() if f.scenes()}
    assert got == {
        "bout": sorted([("own", "duel"), ("own", "arena"), ("art", "bout")]),
        "battle": [("art", "battle")],
        "feast": sorted([("own", "feast"), ("art", "feast")]),
        "sense": sorted([("own", "sense"), ("art", "sense")]),
        "story": [("own", "story")],
        "companions": sorted([("own", "talk"), ("art", "talk")]),
        "faction": sorted([("own", "ally"), ("own", "faction"), ("own", "defect")]),
        "socialize": [("own", "audience")],
        "military": [("own", "omen")],
        "travel": [("own", "road")],
    }


def test_the_core_and_the_packages_take_every_menu_slot_exactly_once():
    """核心代叫的格與包登記的格（照真的 FEATURES）合起來剛好是表上的格、沒有重疊：沒有一格默默不跑、也沒有一格兩邊都寫。誰登記哪一格照計畫第二節鎖住。"""
    from tianxia import engine

    assert set(engine._MENU_CORE) <= set(features_core.MENU_ORDER)
    for at, order in features_core.MENU_ORDER.items():
        mine = features_core.menu_hooks(at)
        theirs = _menu_core_slots(at)
        assert not mine.keys() & theirs, at
        assert mine.keys() | theirs == set(order), at
    got = {f.name: sorted((h.at, h.slot) for h in f.menus()) for f in features_core.registered() if f.menus()}
    assert got == {
        "seal": sorted([("tick", "seal"), ("front", "seal"), ("quick", "seal")]),
        "battle": [("quick", "battle")],
        "zhuan": [("rest", "zhuan")],
        "bout": sorted([("take", "duel"), ("busy", "arena"), ("road", "arena"), ("idle", "duel"), ("idle", "arena"), ("open", "arena"), ("block", "bout"), ("quick", "duel"), ("quick", "arena"), ("stale", "arena")]),
        "sense": sorted([("take", "sense"), ("idle", "sense"), ("quick", "canvas")]),
        "story": sorted([("take", "story"), ("here", "story")]),
        "companions": sorted([("take", "talk"), ("road", "parley"), ("here", "recruit"), ("here", "errand"), ("block", "talk"), ("quick", "errand"), ("stale", "recruit")]),
        "faction": sorted([("take", "faction"), ("here", "sect"), ("here", "join"), ("here", "defect"), ("here", "lean"), ("idle", "faction"), ("block", "faction"), ("stale", "lean")]),
        "socialize": sorted([("take", "audience"), ("here", "social"), ("notes", "socialize"), ("idle", "audience"), ("block", "audience")]),
        "bounties": sorted([("take", "bounties"), ("here", "bounties"), ("idle", "bounties"), ("open", "bounties"), ("depart", "bounties"), ("block", "bounties"), ("stale", "bounties")]),
        "smithy": sorted([("take", "smithy"), ("here", "smithy"), ("idle", "smithy"), ("open", "smithy"), ("depart", "smithy"), ("block", "smithy")]),
        "gear": sorted([("take", "gear"), ("here", "gear"), ("idle", "gear"), ("open", "gear"), ("depart", "gear"), ("block", "gear"), ("stale", "market")]),
        "outlets": sorted([("here", "donate"), ("here", "dadian"), ("idle", "outlets"), ("block", "outlets")]),
        "tavern": sorted([("idle", "tavern"), ("block", "tavern")]),
        "military": sorted([("take", "omen"), ("here", "order"), ("here", "rank2"), ("here", "rank"), ("here", "omen"), ("idle", "omen")]),
        "figure_acts": sorted([("here", "challenge"), ("plays", "aid"), ("plays", "plan")]),
        "travel": sorted([("road", "head"), ("road", "halt"), ("road", "tasks"), ("here", "move")]),
        "stamina_plays": sorted([("plays", "head"), ("block", "ambush")]),
        "seclusion": [("busy", "seclusion")],
        "cultivation": [("here", "lessons")],
        "peers": [("here", "invite")],
    }


def _every_menu_slot(calls, answer):
    """登記表上每一格包的格的假包（關著）：叫到就記 (位置, 格)、回 answer(位置, 格)。"""
    def note(at, slot):
        return lambda *args: calls.append((at, slot)) or answer(at, slot)

    return Menuy([MenuHook(at, slot, note(at, slot)) for at, order in features_core.MENU_ORDER.items() for slot in order if slot not in _menu_core_slots(at)], open_=False)


_MENU_EMPTY = {"front": [], "rest": [], "busy": [], "road": [], "here": [], "plays": [], "notes": {}}


def _package_menu_slots(at):
    return [(at, slot) for slot in features_core.MENU_ORDER[at] if slot not in _menu_core_slots(at)]


def test_the_game_asks_the_menu_table_at_its_places(game, monkeypatch):
    """Game.options、_idle、_shop_open、action_notes 在位置上問表：先後照表；tick=False 不問 tick；關著的包照問。換掉 FEATURES 之後包的格只叫假包。"""
    calls = []
    monkeypatch.setattr(registry, "FEATURES", [_every_menu_slot(calls, lambda at, slot: _MENU_EMPTY.get(at))])
    game.options()
    assert calls[:2] == [("tick", "seal"), ("front", "seal")]
    assert [c for c in calls if c[0] == "take"] == _package_menu_slots("take")
    assert [c for c in calls if c[0] == "here"] == _package_menu_slots("here")
    calls.clear()
    game.options(tick=False)
    assert ("tick", "seal") not in calls
    calls.clear()
    assert game._idle() is True
    assert calls == _package_menu_slots("idle")
    calls.clear()
    assert game._shop_open() is None
    assert calls == _package_menu_slots("open")
    calls.clear()
    game.action_notes(["act:socialize"])
    assert calls == [("notes", "socialize")]


def test_the_game_takes_the_first_answer_of_the_take_row(game, monkeypatch):
    """take 接管整個選單：第一個不是 None 的就是選單（空的也是），後面的不問；閉關、路上在 take 之後。"""
    calls = []

    def answer(at, slot):
        if (at, slot) == ("take", "gear"):
            return []
        return _MENU_EMPTY.get(at)

    monkeypatch.setattr(registry, "FEATURES", [_every_menu_slot(calls, answer)])
    assert game._everyday_options(False) == []
    assert ("take", "gear") in calls and ("take", "omen") not in calls
    assert not [c for c in calls if c[0] == "here"]


def test_the_shop_open_row_turns_an_empty_answer_into_none(game, monkeypatch):
    """open 格回 "" 是坐著、這裡不開門：_shop_open 回 None，後面的不問（鐵匠鋪的單子開著、榜不在這裡）。"""
    calls = []
    monkeypatch.setattr(registry, "FEATURES", [_every_menu_slot(calls, lambda at, slot: "" if (at, slot) == ("open", "smithy") else None)])
    assert game._shop_open() is None
    assert calls == [("open", "arena"), ("open", "bounties"), ("open", "smithy")]


def test_travel_block_walks_its_row_and_core_slots_sit_between_the_packages(game, monkeypatch):
    """動身被擋照表：包的格與核心代叫的穿插。閉關（核心）在守著埋伏（包）前面：閉關中不問埋伏那一格；什麼都沒有回 None；格拿到的是傳進來的 state（結伴拿別人的 state 問）。"""
    from tianxia import atlas

    seen = []
    calls = []
    monkeypatch.setattr(registry, "FEATURES", [Menuy([
        MenuHook("block", slot, (lambda slot: lambda state, content: calls.append(slot) or seen.append(state))(slot))
        for slot in ("bout", "talk", "audience", "bounties", "smithy", "gear", "outlets", "tavern", "faction", "ambush")])])
    state = game.state
    state.world.ended = False
    state.pending_event = None
    assert atlas.travel_block(state, game.content) is None
    assert calls == ["bout", "talk", "audience", "bounties", "smithy", "gear", "outlets", "tavern", "faction", "ambush"]
    assert all(s is state for s in seen)
    calls.clear()
    state.player.busy_until = 1.0
    blocked = atlas.travel_block(state, game.content)
    assert blocked is not None and blocked.reason == "閉關中，不能安排前往" and not blocked.to_jianghu
    assert "ambush" not in calls and calls[-1] == "faction"


def test_the_departure_row_clears_in_the_table_order(game, monkeypatch):
    """動身收店照表：懸賞榜、帶路、鐵匠鋪、馬市、店面登記的店。帶路（移動包代叫）夾在包的格中間。"""
    from tianxia.features.travel import departure

    calls = []
    game.state.player.parley_escort = "某人"
    monkeypatch.setattr(registry, "FEATURES", [_every_menu_slot(calls, lambda at, slot: None)])
    features_core.menu_run("depart", departure._DEPART_CORE, game)
    assert calls == _package_menu_slots("depart")
    assert game.state.player.parley_escort is None


# core_seams（全部拆包第 57 批「分派與標題收接縫」；計畫 docs/superpowers/plans/2026-11-06-分派標題收接縫-第57批.md 一、五）
class Quicky(Menuy):
    """選單上放一顆假的、choose 掛鉤接 fake:（看 quick 回 None 有沒有往下走）。"""

    def choose(self, ctx, kind, arg):
        return Outcome(title="假的", run=lambda: ["走到 choose 掛鉤。"]) if kind == "fake" else None


def test_the_quick_row_answers_after_the_menu_check_and_before_the_journal(game, monkeypatch):
    """Game.choose 的 quick：不在選單上不問；查完選單、清掉「剛剛」與引導之後照表的先後問；第一個不是 None 的就是回話（空的 [] 也算接管），後面的不問、_log 一次、不建紀錄；
    都回 None 照舊往下走 choose 掛鉤。"""
    calls, answers = [], {}

    def slot(name):
        return lambda ctx, *args: calls.append((name, *args)) or answers.get(name)

    monkeypatch.setattr(registry, "FEATURES", [Quicky([
        MenuHook("take", "gear", lambda ctx: [Option(id="fake:go", label="假的那一顆")]),
        *(MenuHook("quick", name, slot(name)) for name in features_core.MENU_ORDER["quick"]),
    ])])
    g = _made(game)
    assert g.choose("fake:gone") == ["（此刻無法這麼做。）"]
    assert not calls

    answers["duel"] = ["出了一招。"]
    g.state.player.guide_done = ["上一次完成的"]
    journal, log = len(g.state.journal), len(g.state.log)
    assert g.choose("fake:go") == ["出了一招。"]
    assert calls == [(name, "fake", "go", "fake:go") for name in ("battle", "seal", "duel")]
    assert len(g.state.journal) == journal
    assert g.state.log[log] == "出了一招。" and len(g.state.log) == log + 2  # 那一句加一個分隔：_log 只有一次
    assert g.state.player.guide_done == []

    calls.clear()
    answers["duel"] = []
    assert g.choose("fake:go") == []
    assert [c[0] for c in calls] == ["battle", "seal", "duel"]

    calls.clear()
    answers.clear()
    assert "走到 choose 掛鉤。" in g.choose("fake:go")
    assert [c[0] for c in calls] == list(features_core.MENU_ORDER["quick"])
    assert len(g.state.journal) == journal + 1


def test_the_stale_row_answers_after_the_menu_lookup_and_before_the_cannot_line(game, monkeypatch):
    """Game.choose 的 stale（第二輪第 92 批）：查完選單之後、「此刻無法」之前照表的先後問，每一格拿到查到的那一顆與 id；
    回 Refused 就直接回它、後面的不問、不再 _log（寫不寫江湖紀錄是格自己的事）；回 Option 換掉查到的那一顆、照它往下走；都回 None 照舊往下。"""
    calls, answers = [], {}

    def slot(name):
        return lambda ctx, option, option_id: calls.append((name, option.id if option else None, option_id)) or answers.get(name)

    monkeypatch.setattr(registry, "FEATURES", [Quicky([
        MenuHook("take", "gear", lambda ctx: [Option(id="fake:go", label="假的那一顆")]),
        *(MenuHook("stale", name, slot(name)) for name in features_core.MENU_ORDER["stale"]),
    ])])
    g = _made(game)

    assert g.choose("fake:gone") == ["（此刻無法這麼做。）"]
    assert calls == [(name, None, "fake:gone") for name in features_core.MENU_ORDER["stale"]]

    calls.clear()
    log = len(g.state.log)
    answers["market"] = Refused(["不成。"])
    got = g.choose("fake:gone")
    assert isinstance(got, Refused) and got == ["不成。"] and len(g.state.log) == log
    assert [c[0] for c in calls] == ["lean", "bounties", "market"]

    calls.clear()
    answers.clear()
    answers["lean"] = Option(id="fake:go", label="假的那一顆")
    assert "走到 choose 掛鉤。" in g.choose("fake:gone")
    assert [c[0] for c in calls] == ["lean"]

    calls.clear()
    answers.clear()
    answers["lean"] = Option(id="fake:go", label="灰的", enabled=False)
    assert g.choose("fake:gone") == ["（此刻無法這麼做。）"]  # 換上來的灰的照舊擋

    calls.clear()
    answers.clear()
    assert "走到 choose 掛鉤。" in g.choose("fake:go")
    assert calls == [(name, "fake:go", "fake:go") for name in features_core.MENU_ORDER["stale"]]


def test_the_outcome_says_how_the_journal_entry_lands(game, monkeypatch):
    """Outcome 接在 run 後面的三格（第二輪第 92 批）：沒給就是一下一則；quiet 拿建好的這一則、真的就不寫；merge 併進同標題那一則；fold 在動作之後才叫、回的東西交給 add_entry。
    現有兩格的先後與預設不准動（各包都用位置或名字建）。"""
    order, made = [], {}

    class Landy(Quicky):
        def choose(self, ctx, kind, arg):
            return made[arg] if kind == "fake" else None

    def said(line):
        return lambda: order.append("run") or [line]

    monkeypatch.setattr(registry, "FEATURES", [Landy([
        MenuHook("take", "gear", lambda ctx: [Option(id=f"fake:{name}", label=name) for name in ("plain", "quiet", "loud", "merge", "fold")]),
    ])])
    g = _made(game)
    bare = Outcome("標題", said("x"))
    assert (bare.quiet, bare.merge, bare.fold) == (None, False, None)

    made["plain"] = Outcome("一樣的標題", said("第一句。"))
    start = len(g.state.journal)
    g.choose("fake:plain")
    assert len(g.state.journal) == start + 1 and g.state.journal[0].lines[:1] == ["第一句。"]

    seen = []
    made["quiet"] = Outcome("一樣的標題", said("翻頁。"), quiet=lambda entry: seen.append(entry.lines) or True)
    g.choose("fake:quiet")
    assert len(g.state.journal) == start + 1 and seen and seen[0][:1] == ["翻頁。"]

    made["loud"] = Outcome("一樣的標題", said("第二句。"), quiet=lambda entry: False)
    g.choose("fake:loud")
    assert len(g.state.journal) == start + 2  # quiet 是假的、沒給 merge：照舊另起一則

    made["merge"] = Outcome("一樣的標題", said("第三句。"), merge=True)
    g.choose("fake:merge")
    assert len(g.state.journal) == start + 2 and g.state.journal[0].lines[:2] == ["第二句。", "第三句。"]

    order.clear()
    made["fold"] = Outcome("一樣的標題", said("結果。"), merge=True, fold=lambda: order.append("fold") or (lambda line: line == "第二句。"))
    g.choose("fake:fold")
    assert order == ["run", "fold"]  # fold 在動作之後才叫（判斷要讀動作之後的狀態）
    assert len(g.state.journal) == start + 2
    assert g.state.journal[0].lines[:2] == ["結果。", "第三句。"]  # 收掉 fold 說是的那一行、其餘接在結果句後面（add_entry）


SCRATCH_FLAGS = {
    "explore": {"_outing_busy": False, "_loot_scale": 1.0, "_drop_scale": 1.0, "_gate_scale": 1.0, "_outing_close": set(), "_beat": None, "_outing_upset": False},
    "gear": {"_affinity_before": None},
    "battle": {"_escort_picked": False, "_escort_now": None, "_battle_ref": None},
    "sortie": {"_clash_won": False, "_sortie_marked": False, "_sortie_moved": 0.0, "_sortie_flipped": False},
    "smithy": {"smith_result": None},
    "peers": {"peer_brief": None},
    "cultivation": {"forged": False, "forged_thing": None, "secret_solved": None},
    "companions": {"_persuade_said": None, "_talk_turn": None, "_talk_said": None, "_parley_decision": None},
}


def test_the_scratch_flags_are_declared_by_their_packages_and_do_not_clash():
    """Feature.scratch()（第二輪第 92 批）：24 個旗標照包宣告、預設值照原本的 Game.__init__；名字不重複、不撞 Game 類別上的東西（不然 setattr 會蓋掉方法）；
    每次回新的 dict，_outing_close 兩份 Game 不能共用。"""
    got = {f.name: f.scratch() for f in registry.DECLARED if f.scratch()}
    assert got == SCRATCH_FLAGS
    names = [name for flags in got.values() for name in flags]
    assert len(names) == len(set(names)) == 24
    assert not [name for name in names if hasattr(Game, name)]
    for f in registry.DECLARED:
        assert f.scratch() is not f.scratch()
    assert Feature().scratch() == {}


def _has_every_scratch_flag(g: Game) -> bool:
    return all(hasattr(g, name) for flags in SCRATCH_FLAGS.values() for name in flags)


def test_every_game_has_the_scratch_flags_before_it_drops_stale_references(game, monkeypatch):
    """scratch_init 在 _drop_stale_references 之前跑完（那一支會換季、跑掛鉤，會讀旗標）；_kin、_admin_target、_load_kin 開的也有；FEATURES 換掉（假的或空的）建的也有
    （核心的 combat、pushing、choose 照樣讀，所以走 DECLARED 不走 registered）；兩份 Game 的 _outing_close 不是同一個。"""
    from tianxia.characters import CharacterStore

    assert _has_every_scratch_flag(game)

    other = game._kin(game.state.model_copy(deep=True))
    assert _has_every_scratch_flag(other) and other._outing_close is not game._outing_close

    other.state.player.name = "別人"
    CharacterStore(game.world.db).save(other.state)
    assert game._load_kin("別人") is not None and _has_every_scratch_flag(game._load_kin("別人"))
    target = game._admin_target("別人")
    assert target is not game and _has_every_scratch_flag(target)

    seen = []
    real = Game._drop_stale_references
    monkeypatch.setattr(Game, "_drop_stale_references", lambda self: seen.append(_has_every_scratch_flag(self)) or real(self))
    for features in ([], [Menuy([])]):
        monkeypatch.setattr(registry, "FEATURES", features)
        built = Game(game.content, game.state, game.rng, game.world)
        assert _has_every_scratch_flag(built)
    assert seen == [True, True]


class Tailed(Feature):
    """帶後綴的 act 子動詞的假包（關著：這幾格不問 enabled）。plainverb 只有沒後綴的那幾格。"""

    name = "tailed"

    def __init__(self):
        self.calls = []

    def enabled(self, ctx):
        return False

    def verbs(self):
        def note(*got):
            self.calls.append(got)

        return (
            Verb("fakeverb", run=lambda g, prepared: note("run", prepared) or ["沒有後綴。"], title=lambda g: "沒有後綴的標題",
                 tail_run=lambda g, prepared, tail: note("tail_run", prepared, tail) or ["有後綴。"], tail_title=lambda g, tail: f"標題・{tail}",
                 tail_squad=lambda g, tail: g.content.squads["thug"] if tail == "打" else None),
            Verb("plainverb", run=lambda g, prepared: ["只有沒後綴的。"], title=lambda g: "只有沒後綴的標題", squad=lambda g: g.content.squads["thug"]),
        )


def test_a_verb_with_a_tail_gets_the_tail_and_a_verb_without_one_falls_to_the_core(game, monkeypatch):
    """act:<verb>:<後綴>：按下去、標題、打哪一路問 tail_*，拿到第一個冒號後面整段（可以再有冒號、可以是空的），run 不被叫；同一個 Verb 也管沒有後綴的那一下。
    主人沒有 tail_* 回 None，核心照舊：_act 不認得是 KeyError、標題「提前出關」、不打仗。"""
    tailed = Tailed()
    monkeypatch.setattr(registry, "FEATURES", [tailed])
    g = _made(game)
    assert g._act("fakeverb:甲", "那一輪") == ["有後綴。"]
    assert g._act("fakeverb:甲:乙") == ["有後綴。"] and g._act("fakeverb:") == ["有後綴。"]
    assert tailed.calls == [("tail_run", "那一輪", "甲"), ("tail_run", None, "甲:乙"), ("tail_run", None, "")]
    tailed.calls.clear()
    assert g._act("fakeverb") == ["沒有後綴。"]
    assert tailed.calls == [("run", None)]
    assert g._action_title("act", "fakeverb:甲") == "標題・甲" and g._action_title("act", "fakeverb") == "沒有後綴的標題"
    thug = g.content.squads["thug"]
    assert g._fight_squad("act:fakeverb:打") is thug
    assert g._fight_squad("act:fakeverb:不打") is None and g._fight_squad("act:fakeverb") is None

    assert features_core.act(g, "plainverb:乙", None) is None
    with pytest.raises(KeyError):
        g._act("plainverb:乙")
    assert g._action_title("act", "plainverb:乙") == "提前出關"
    assert g._fight_squad("act:plainverb:乙") is None and g._fight_squad("act:plainverb") is thug


def test_the_silver_verbs_answer_the_title_only_for_kind_act(world):
    """銀兩那四樣（Verb.act_only；第二輪第 99 批從 Game._action_title 的字面換來）：kind 要是 "act" 才問主人，別的 kind 帶同一個字照舊是「提前出關」。"""
    from conftest import real_content

    g = Game.new(real_content("season21"), "甲", rng=random.Random(0), world=world)
    for verb in ("silver_donate", "mentor", "furnace", "buy_legend"):
        assert g._action_title("sect", verb) == "提前出關"
        assert g._action_title("act", verb) != "提前出關"


def test_every_act_verb_has_the_owner_in_the_plan():
    """一格一主，逐字鎖住（計畫第二、五節）；只有這四格帶後綴。act:heal 與舊探索留在 Game._act 原位（explore 這一格的主人回 None 才走到舊探索）。"""
    owners = {v.verb: f.name for f in features_core.registered() for v in f.verbs()}
    assert owners == {
        "explore": "explore", "tavern": "tavern", "train": "sortie", "duty": "sortie", "rest": "guide", "recruit": "companions",
        "call": "socialize", "socialize": "socialize", "challenge": "figure_acts",
        "rank2": "military", "rank": "military", "convoy": "military", "summons": "military",
        "donate": "outlets", "dadian": "outlets", "silver_donate": "outlets", "mentor": "outlets", "furnace": "outlets", "buy_legend": "outlets", "bribe": "outlets",
        "smith": "smithy", "arena": "bout", "break": "seclusion", "halt": "travel", "part": "travel", "market": "gear", "bounties": "bounties",
    }
    tails = {v.verb for f in features_core.registered() for v in f.verbs() if v.tail_run is not None}
    assert tails == {"recruit", "rank", "bribe", "challenge"}


# core_bots（全部拆包第 60 批「假人殼收尾」；計畫 docs/superpowers/plans/2026-11-06-假人殼收尾-第60批.md 第一、九節）


def test_the_bot_slots_on_the_verbs_are_the_ones_in_the_plan():
    """假人怎麼按 act: 那幾格，逐字鎖住（計畫第二節）：一格一主，不開順序表。有 bot 格的是 bot_policy.score 問主人的；沒寫的落到 ACT_SCORES.get(arg, 0.0)，0.0 是隨機挑得到的、不是不按。
    bot_skip、tail_bot_skip 與 bot_always 是 bot.pick 不按的（永遠按得下去）。"""
    verbs = [v for f in features_core.registered() for v in f.verbs()]
    assert {v.verb for v in verbs if v.bot is not None} == {
        "explore", "tavern", "train", "duty", "call", "socialize", "rank2", "convoy", "summons", "donate", "dadian", "smith", "arena", "market", "bounties",
    }
    assert {v.verb for v in verbs if v.tail_bot is not None} == {"recruit", "challenge"}
    assert {v.verb for v in verbs if v.bot_skip} == {"rest", "halt", "bounties", "smith", "market", "arena", "donate", "dadian", "tavern"}
    assert {v.verb for v in verbs if v.tail_bot_skip} == {"recruit"}
    assert sorted(features_core.bot_always()) == [
        "aid:", "ambush:", "dadian:", "defect:", "donate:", "errand:", "faction:lean:", "feast:", "fs:", "invite:", "legacy:skip", "opp:", "road:", "smith:page:",
        "talk:clue:", "talk:opp:", "tavern:", "works:",
    ]


def test_the_scores_written_twice_stay_the_same_number():
    """包裡照鐵匠鋪前例重寫一份的分數（模組層不碰 bot_policy），跟 bot_policy 留著的那個名字同值（計畫第二節）。"""
    from tianxia import bot_policy as bp
    from tianxia.features.bounties import bots as bounties_bots
    from tianxia.features.gear import bots as gear_bots
    from tianxia.features.military import bots as military_bots
    from tianxia.features.smithy import bots as smithy_bots
    from tianxia.features.socialize import bots as socialize_bots

    assert bounties_bots.BOUNTY_SCORE == bp.BOUNTY_SCORE and gear_bots.MARKET_SCORE == bp.MARKET_SCORE
    assert smithy_bots.SMITH_SCORE == bp.SMITH_SCORE and smithy_bots.FORGE_SCORE == bp.FORGE_SCORE
    assert socialize_bots.ACT_SCORE == bp.ACT_SCORES["socialize"]
    assert military_bots.RANK2_SCORE == bp.DUTY_SCORE and military_bots.CONVOY_SCORE == bp.ORDER_SCORE and military_bots.SUMMONS_SCORE == bp.SUMMONS_SCORE


class Scored(Fake):
    """假包：三格 act 子動詞（有分數也不按的、回 None 的、只有按下去的）與一顆有條件的「按了也白按」。"""

    def verbs(self):
        return (
            Verb("fakebot", bot=lambda g, profile: 5.5, tail_bot=lambda g, profile, tail: None if tail == "不按" else 6.5, bot_skip=True),
            Verb("fakenone", bot=lambda g, profile: None, tail_bot_skip=True),
            Verb("fakeplain", run=lambda g, prepared: ["只有按下去。"]),
        )

    def bot_idle(self, ctx, option):
        self._note("bot_idle", option.id)
        return option.id == "fake:idle"


@pytest.fixture
def scored(monkeypatch):
    f = Scored(open_=False)  # 關著也照問：這幾格原位本來就不看開關
    monkeypatch.setattr(registry, "FEATURES", [f])
    return f


def test_act_score_tells_a_no_from_no_owner(game, scored):
    """(有沒有主人, 分數)：格回 None 是主人說不按；那一格沒寫算沒主人，核心照舊落到 ACT_SCORES。帶後綴問 tail_bot，沒有 tail_bot 也算沒主人。"""
    assert features_core.act_score(game, "fakebot", None) == (True, 5.5)
    assert features_core.act_score(game, "fakebot:甲", None) == (True, 6.5)
    assert features_core.act_score(game, "fakebot:不按", None) == (True, None)
    assert features_core.act_score(game, "fakenone", None) == (True, None)
    assert features_core.act_score(game, "fakenone:甲", None) == (False, None)
    assert features_core.act_score(game, "fakeplain", None) == (False, None)
    assert features_core.act_score(game, "nosuch", None) == (False, None)


def test_bot_idle_asks_the_prefix_the_verb_and_the_owner(game, scored):
    """四條路：包宣告的前綴（問到就不再問主人）、act:<verb> 的 bot_skip（比相等）、act:<verb>:<後綴> 的 tail_bot_skip（比開頭）、選項主人的 bot_idle。不是任何一包的選項是 False。"""
    def idle(option_id):
        return features_core.bot_idle(game, Option(id=option_id, label=""))

    assert idle("fake:wait") and scored.calls == []
    assert idle("act:fakebot") and not idle("act:fakebot:甲")
    assert idle("act:fakenone:甲") and idle("act:fakenone:") and not idle("act:fakenone")
    assert not idle("act:fakeplain") and not idle("act:nosuch") and not idle("nokind")
    assert scored.calls == []  # act: 不是任何一包的前綴，不問主人
    assert idle("fake:idle") and not idle("fake:do") and scored.calls == [("bot_idle", "fake:idle"), ("bot_idle", "fake:do")]


def test_the_bots_reach_the_package_through_the_verb_slots(game, scored):
    """bot_policy.score 的 act: 那一段與 bot.pick 的排除真的走到假包；沒有主人的落到 ACT_SCORES（兩鍵留著），act:heal 兩邊都留在核心。"""
    from tianxia import bot, bot_policy
    from tianxia.state import BotProfile

    g = _made(game)
    profile = BotProfile(personality="普通", seed=1)

    def score(option_id):
        return bot_policy.score(g, Option(id=option_id, label=""), profile)

    def picked(option_id):
        return bot.pick(g, [Option(id=option_id, label="")], random.Random(0))

    assert score("act:fakebot") == 5.5 and score("act:fakebot:甲") == 6.5 and score("act:fakebot:不按") is None and score("act:fakenone") is None
    assert score("act:fakeplain") == 0.0 and score("act:fakeplain:甲") == 0.0 and score("act:nosuch") == 0.0
    assert score("act:explore") == bot_policy.ACT_SCORES["explore"] and score("act:socialize") == bot_policy.ACT_SCORES["socialize"]
    assert score("act:heal") is None  # 不在醫館：核心那兩行
    assert picked("act:fakeplain") == "act:fakeplain" and picked("fake:do") == "fake:do"
    for option_id in ("act:fakebot", "act:fakenone:甲", "fake:wait", "fake:idle", "act:heal", "choice:free"):
        assert picked(option_id) is None, option_id


# ── 玩法說明的格（全部拆包第 59 批「引導二」；計畫 docs/superpowers/plans/2026-11-06-玩法說明-第59批.md 第二節）──


class Howtoer(Feature):
    """只登記玩法說明的格的假包；open 是 enabled 的答案（玩法說明不問 enabled）。"""

    name = "howtoer"

    def __init__(self, hooks, open_=True):
        self.hooks, self.open = tuple(hooks), open_

    def enabled(self, ctx):
        return self.open

    def howto(self):
        return self.hooks


def test_the_howto_order_is_the_table_in_the_plan():
    """順序就是行為：22 格照換成掛鉤之前 howto.page 一段一段接的先後，一格不挪；插句三格。改這張表先過 PM。"""
    assert features_core.HOWTO_ORDER == (
        "season", "act_head", "explore", "growth", "sortie", "socialize", "travel", "ambush", "stamina", "fame", "join", "factions", "land",
        "bond", "challenge", "xinde", "pages", "forge", "insight", "bag", "economy", "mall")
    assert features_core.HOWTO_INSERTS == ("fame_seal", "fame_tavern", "land_seal")
    assert Feature().howto() == ()


def test_a_package_can_only_take_a_howto_slot_on_the_table_and_only_one_package_a_slot(monkeypatch):
    """包登記的格都在兩張表上、同一格只有一包：表外的格、兩包（或同一包兩次）登記同一格，howto_hooks、howto_table 都丟 ValueError。"""
    hook = features_core.HowtoHook
    none = lambda content, season, page: []  # noqa: E731
    monkeypatch.setattr(registry, "FEATURES", [Howtoer([hook("no_such_slot", none)])])
    with pytest.raises(ValueError):
        features_core.howto_hooks()
    with pytest.raises(ValueError):
        features_core.howto_table()
    monkeypatch.setattr(registry, "FEATURES", [Howtoer([hook("bag", none)]), Howtoer([hook("bag", none)])])
    with pytest.raises(ValueError):
        features_core.howto_hooks()
    monkeypatch.setattr(registry, "FEATURES", [Howtoer([hook("fame_seal", none), hook("fame_seal", none)])])
    with pytest.raises(ValueError):
        features_core.howto_hooks()


def test_the_howto_table_keeps_the_order_and_asks_closed_packages_too(monkeypatch):
    """登記的先後不算數，照 HOWTO_ORDER 排；沒人登記的格跳過；關著的包照叫（玩法說明不看個人、不問 enabled）。"""
    hook = features_core.HowtoHook
    bag, season = hook("bag", lambda content, season, page: ["背"]), hook("season", lambda content, season, page: ["季"])
    monkeypatch.setattr(registry, "FEATURES", [Howtoer([bag], open_=False), Howtoer([season])])
    assert [h.slot for h in features_core.howto_table()] == ["season", "bag"]
    assert [h.lines(None, None, features_core.HowtoPage()) for h in features_core.howto_table()] == [["季"], ["背"]]
    monkeypatch.setattr(registry, "FEATURES", [])
    assert features_core.howto_hooks() == {} and features_core.howto_table() == []


def test_the_howto_insert_knows_only_its_table_and_says_nothing_when_nobody_took_it(monkeypatch):
    """插句只認 HOWTO_INSERTS（表上的格、寫錯的字都丟）；沒人登記回 []；有人登記照 lines 回，page 是預設的 HowtoPage。"""
    hook = features_core.HowtoHook
    seen = []
    monkeypatch.setattr(registry, "FEATURES", [])
    assert features_core.howto_insert("fame_seal", None, None) == []
    with pytest.raises(ValueError):
        features_core.howto_insert("bag", None, None)
    with pytest.raises(ValueError):
        features_core.howto_insert("no_such_insert", None, None)
    monkeypatch.setattr(registry, "FEATURES", [Howtoer([hook("land_seal", lambda content, season, page: seen.append(page) or ["句"])], open_=False)])
    assert features_core.howto_insert("land_seal", None, None) == ["句"]
    assert seen == [features_core.HowtoPage()] and seen[0].recruitable is False and seen[0].rule == ""


def test_every_howto_slot_and_insert_has_exactly_one_package():
    """照真的 FEATURES：22 格加 3 個插句都有主人、沒有一格默默不寫（主人照計畫第二節那張表）；沒有格留在核心。"""
    assert set(features_core.howto_hooks()) == {*features_core.HOWTO_ORDER, *features_core.HOWTO_INSERTS}
    assert [h.slot for h in features_core.howto_table()] == list(features_core.HOWTO_ORDER)
    assert {f.name: [h.slot for h in f.howto()] for f in features_core.registered() if f.howto()} == {
        "guide": ["season", "act_head", "growth", "stamina", "fame", "bag"], "explore": ["explore"], "sortie": ["sortie"],
        "socialize": ["socialize"], "travel": ["travel"], "stamina_plays": ["ambush"], "faction": ["join", "factions"],
        "territory_acts": ["land"], "companions": ["bond"], "figure_acts": ["challenge"], "cultivation": ["xinde", "pages"],
        "smithy": ["forge"], "sense": ["insight"], "outlets": ["economy"], "mall": ["mall"],
        "seal": ["fame_seal", "land_seal"], "tavern": ["fame_tavern"]}


def test_the_howto_page_is_the_table_joined_and_slots_look_up_their_functions_when_called(monkeypatch):
    """page 只把每一格接起來（順序就是表）；每一格在叫的那一下才照模組屬性找（換掉包裡的函式打得到）。"""
    from conftest import real_content
    from tianxia.features.guide import howto as guide_words
    from tianxia.features.sense import howto as sense_words
    from tianxia.world_state import fresh_season

    content = real_content("season21")
    season = fresh_season(content)
    view = features_core.HowtoPage(recruitable=True, rule="收季規則")
    table = features_core.howto_table()
    assert guide_words.page(content, season, recruitable=True, rule="收季規則") == "\n".join(
        line for hook in table for line in hook.lines(content, season, view))
    monkeypatch.setattr(sense_words, "insight_section", lambda content, season: ["第五十九批換掉的"])
    assert "第五十九批換掉的" in guide_words.page(content, season, recruitable=False)


# core_content（第二輪第 100 批；計畫 docs/superpowers/plans/2026-11-07-第二輪-第100批.md 第二節）：位置固定的內容驗證
class ContentSlotter(Feature):
    """只登記內容驗證格的假包。"""

    name = "content_slotter"

    def __init__(self, hooks):
        self.hooks = tuple(hooks)

    def enabled(self, ctx):
        return False

    def content_slots(self):
        return self.hooks


def test_a_feature_takes_no_content_slot_by_default_and_the_table_is_the_plan():
    assert Feature().content_slots() == ()
    assert features_core.CONTENT_SLOTS == (
        "insight_scenes", "insight_strong", "faction_choices", "seal", "stances", "errands", "companions", "foreshadows", "promotions", "opportunities",
        "duels", "gear", "signature_arms", "bounties", "storylines")


def test_check_at_only_knows_its_table_and_only_one_package_a_slot(monkeypatch):
    """打錯字、表外的格、同一格登記兩次（兩包或同一包）都丟 ValueError；每一次都驗登記的全部格，不只驗問的那一格。"""
    hook = features_core.ContentSlot
    none = lambda *a: None  # noqa: E731
    monkeypatch.setattr(registry, "DECLARED", ())
    with pytest.raises(ValueError):
        features_core.check_at("no_such_slot", None, None)
    monkeypatch.setattr(registry, "DECLARED", (ContentSlotter([hook("no_such_slot", none)]),))
    with pytest.raises(ValueError):
        features_core.check_at("gear", None, None)
    monkeypatch.setattr(registry, "DECLARED", (ContentSlotter([hook("duels", none)]), ContentSlotter([hook("duels", none)])))
    with pytest.raises(ValueError):
        features_core.check_at("gear", None, None)
    monkeypatch.setattr(registry, "DECLARED", (ContentSlotter([hook("duels", none), hook("duels", none)]),))
    with pytest.raises(ValueError):
        features_core.check_at("gear", None, None)


def test_check_at_reads_declared_not_features_and_passes_what_the_call_site_passes(monkeypatch):
    """契約測試把 FEATURES 換成 [] 時內容母本可能正好在建：照舊驗（讀 DECLARED）。多傳的參數原樣傳；沒人登記的格跳過。"""
    seen = []
    slotter = ContentSlotter([features_core.ContentSlot("gear", lambda content, need, *args: seen.append((content, need, args)))])
    monkeypatch.setattr(registry, "DECLARED", (slotter,))
    monkeypatch.setattr(registry, "FEATURES", [])
    features_core.check_at("gear", "內容", "need", "known")
    assert seen == [("內容", "need", ("known",))]
    features_core.check_at("duels", "內容", "need")
    assert len(seen) == 1


def test_every_content_slot_has_exactly_one_package(monkeypatch):
    """照真的 DECLARED：15 格都有主人、沒有一格默默不驗（主人照計畫第二節那張表）；FEATURES 換成 [] 照樣叫得到真的包。"""
    owners = {f.name: [h.slot for h in f.content_slots()] for f in registry.DECLARED if f.content_slots()}
    assert owners == {
        "sense": ["insight_scenes", "insight_strong"], "faction": ["faction_choices"], "seal": ["seal"],
        "companions": ["stances", "errands", "companions"], "military": ["foreshadows", "promotions", "opportunities"],
        "bout": ["duels"], "gear": ["gear", "signature_arms"], "bounties": ["bounties"], "story": ["storylines"]}
    assert sorted(s for slots in owners.values() for s in slots) == sorted(features_core.CONTENT_SLOTS)
    from conftest import real_content

    monkeypatch.setattr(registry, "FEATURES", [])
    seen: list[bool] = []
    features_core.check_at("bounties", real_content("season21"), lambda ok, message: seen.append(ok))
    assert seen and all(seen)


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
        "admin": ("phase", "battles", "events", "trends", "timetable", "season_one", "season21", "realign", "default_dates", "mandate_at", "showdowns",
                  "next_has_timetable", "fallen", "seal", "xingshi", "conquest", "mingtie", "divine_out", "llm_queue", "now"),
    }
    assert Feature().status_slots() == ()


def _slot(table, slot, keys=None):
    return features_core.StatusHook(table, slot, lambda ctx, frame: {k: slot for k in (keys or (slot,))})


def test_a_package_slot_off_the_table_goes_to_the_tail_and_only_one_package_a_slot(monkeypatch):
    """包的格不在表上：status_hooks 收下、status_run 走完表再照登記的先後叫，鍵排在最後（第二輪第 74 批，同 action_table）。表名打錯、兩包（或同一包兩次）登記同一格，
    status_hooks 都丟 ValueError（問別的表也丟：每一次都驗全部）；核心代叫的寫了表外的格，status_run 照丟（只有包能接尾巴）。"""
    monkeypatch.setattr(registry, "FEATURES", [Slotter([_slot("status", "nosuch"), _slot("status", "invites")]), Slotter([_slot("status", "later"), _slot("status", "head")])])
    assert list(features_core.status_hooks("status")) == ["nosuch", "invites", "later", "head"]
    assert features_core.status_hooks("main") == {}  # 別的表不收它們
    assert list(features_core.status_run("status", {}, {}, None)) == ["head", "invites", "nosuch", "later"]
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
