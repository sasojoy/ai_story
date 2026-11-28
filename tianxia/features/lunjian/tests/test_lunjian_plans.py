"""門派論劍打法第四版：戰策（自己寫、老法子）、排陣（帶隊的人、對面看不到）、等模型判讀、模型判讀夾一次、關鍵字判、悟性的上限、假人挑老法子。"""
from __future__ import annotations

from lunjian_kit import season21_game, seat, to

from tianxia.core.option import Option
from tianxia.features.lunjian import actions, bots, judge, routes, rules
from tianxia.state import LunjianCall


def _week(game):
    return actions.week_of(game, actions._week(game), make=True)


def _drawn(game, mine: int = 2, theirs: int = 3):
    """我報了名、本門再兩位（比我弱）、對面一門三位，撥到抽籤之後。"""
    actions.act(game, "sign")
    w = _week(game)
    me = w.entries[game._mall_owner()]
    for i in range(mine):
        w.entries[f"同門{i}"] = seat(f"同門{i}", "baima", me.kit.power * 0.5, key=f"tm{i}")
    for i in range(theirs):
        w.entries[f"對面{i}"] = seat(f"對面{i}", "nanhua", me.kit.power, key=f"dm{i}")
    to(game, actions.draw_at(game, actions._week(game)) + 1)
    actions.on_sync(game)
    return _week(game)


def test_plan_words_pick_a_way_and_ties_are_nothing():
    assert rules.plan_move("以靜制動，等他先出手") == "固守"
    assert rules.plan_move("開場就搶攻") == "強攻"
    assert rules.plan_move("虛招引他，繞到側面偷襲") == "奇襲"
    assert rules.plan_move("隨便打打") == ""
    assert rules.plan_move("先攻後守") == ""  # 一攻一守一樣多：算沒寫


def test_the_rule_call_rewards_the_counter_and_not_an_empty_plan():
    a, b = seat("甲", "x", 10), seat("乙", "y", 10)
    b.kit.scores = {"強攻": 12, "固守": 8, "奇襲": 8}  # 乙最拿手強攻
    assert rules.rule_call(a, b, 0).adv == 0  # 都沒寫：不加不扣
    a.plan = "以靜制動"  # 固守剋強攻
    assert rules.rule_call(a, b, 0).adv == rules.RULE_HIT
    b.plan = "虛招繞側"  # 乙改寫奇襲：奇襲剋固守，兩邊各剋一下對面
    assert rules.rule_call(a, b, 0).adv == -rules.RULE_HIT * 2


def test_wis_raises_the_cap_and_the_engine_clamps_the_call():
    t = season21_game().content.config.lunjian
    a, b = seat("甲", "x", 10), seat("乙", "y", 10)
    a.wis, b.wis = 15, 5
    assert rules.swing_of(LunjianCall(seat=0, adv=10), a, b, t) == t.plan_cap + t.plan_cap_wis * 10
    assert rules.swing_of(LunjianCall(seat=0, adv=99), a, b, t) == rules.swing_of(LunjianCall(seat=0, adv=10), a, b, t)
    assert rules.swing_of(LunjianCall(seat=0, adv=-10), a, b, t) == -t.plan_cap  # 乙佔上風照乙的悟性
    assert rules.swing_of(None, a, b, t) == 0


def test_a_seated_player_writes_a_plan_only_between_draw_and_fight():
    game = season21_game()
    actions.act(game, "sign")
    assert actions.set_plan(game, "以靜制動") == [actions.PLAN_SHUT]  # 還沒抽籤
    _drawn(game)
    assert actions.set_plan(game, "  ") == [actions.PLAN_EMPTY]
    assert actions.set_plan(game, "守" * 31) == [actions.PLAN_LONG.format(n=30)]
    assert actions.set_plan(game, "以静制动") == [actions.PLAN_SET.format(plan="以靜制動")]  # 轉繁體
    view = actions.status(game)["lunjian"]
    assert view["plan"]["text"] == "以靜制動" and view["plan"]["seat"] in rules.SEAT_NAMES
    to(game, actions.fight_at(game, actions._week(game)))
    assert actions.set_plan(game, "開場搶攻") == [actions.PLAN_SHUT]
    assert actions.status(game)["lunjian"]["plan"] is None


def test_presets_are_options_and_a_written_plan_replaces_them():
    game = season21_game()
    _drawn(game)
    ids = [o.id for o in game.options()]
    assert "lunjian:preset:0" in ids
    actions.act(game, "preset:2")
    assert actions.status(game)["lunjian"]["plan"]["text"] == rules.presets()[2]["text"]
    assert routes._plan(game, "開場搶攻") == [actions.PLAN_SET.format(plan="開場搶攻")]


def test_the_leader_reorders_and_the_other_side_cannot_see_the_order():
    game = season21_game()
    w = _drawn(game)
    m = w.matches[0]
    mine = m.seats_a if m.a == "baima" else m.seats_b
    assert rules.leader(mine) == game._mall_owner()  # 我身手最高：我帶隊
    before = [x.name for x in mine]
    assert any(o.id == "lunjian:swap:0" for o in game.options())
    actions.act(game, "swap:1")
    after = [x.name for x in (m.seats_a if m.a == "baima" else m.seats_b)]
    assert after == [before[0], before[2], before[1]]
    view = actions.status(game)["lunjian"]["match"]
    assert view["hidden"] and [s["name"] for s in view["seats_them"]] == sorted(s["name"] for s in view["seats_them"])
    assert all("arts" in s and "lean" in s and "plan" not in s for s in view["seats_them"])  # 對面的戰策看不到


def test_not_the_leader_cannot_swap():
    game = season21_game()
    w = _drawn(game)
    m = w.matches[0]
    mine = m.seats_a if m.a == "baima" else m.seats_b
    for x in mine:
        if x.key != game._mall_owner():
            x.kit.power *= 100
    assert not any(o.id.startswith("lunjian:swap:") for o in game.options())
    assert actions.act(game, "swap:0") == [actions.NOT_LEADER]


def test_the_fight_waits_for_the_judge_then_uses_the_rule():
    game = season21_game(judge_wait_hours=0.5)
    w = _drawn(game)
    at = actions.fight_at(game, actions._week(game))
    to(game, at + 1)
    actions.on_sync(game)
    assert not w.fought  # 還在等模型
    w.matches[0].calls = [LunjianCall(seat=i, adv=0) for i in range(3)]
    actions.on_sync(game)
    assert w.fought  # 全判好了：不用等滿


def test_the_fight_runs_on_the_rule_once_the_wait_is_over():
    game = season21_game(judge_wait_hours=0.5)
    w = _drawn(game)
    from tianxia import calendar

    to(game, actions.fight_at(game, actions._week(game)) + 0.5 * calendar.cal_hour_seconds(game.content, game.state.world))
    actions.on_sync(game)
    assert w.fought and len(w.matches[0].bouts) == 3


class _Client:
    timeout = 60

    def __init__(self, reply):
        self.reply, self.asked = reply, []

    def chat_structured(self, messages, model, **kw):
        self.asked.append(messages[1]["content"])
        return model(**self.reply)


def test_the_judge_clamps_and_drops_text_with_digits():
    a, b = seat("甲", "x", 10), seat("乙", "y", 10)
    a.plan = "以靜制動"
    got = judge.ask(_Client({"advantage": 40, "a_wins": "甲以靜制動，乙久攻不下。", "b_wins": "乙打出 999 下。"}), a, b, 1)
    assert got.adv == rules.ADV_MAX and got.model and got.seat == 1 and got.win_a == got.win_b == ""
    assert judge.ask(None, a, b, 0) is None


class _Shell:
    QUEUE = None

    def __init__(self, game):
        self.CONTENT, self._world = game.content, game.world

    def open_world(self):
        return self._world


def test_the_background_round_writes_the_calls_and_the_story_is_used():
    game = season21_game(judge_wait_hours=0.5)
    _drawn(game)
    to(game, actions.fight_at(game, actions._week(game)) + 1)
    game._save_season()
    client = _Client({"advantage": 6, "a_wins": "甲方佔了上風。", "b_wins": "乙方佔了上風。"})
    shell = _Shell(game)
    assert routes.judge_round(shell, client)
    assert len(client.asked) == 3 and "戰策" in client.asked[0]
    assert not routes.judge_round(shell, client)  # 判過了：這一輪沒事
    season = game.world.get_season()
    calls = season.lunjian.weeks[0].matches[0].calls
    assert [c.adv for c in calls] == [6, 6, 6] and all(c.model for c in calls)
    game.state.world = season
    actions.on_sync(game)
    m = game.state.world.lunjian.weeks[0].matches[0]
    assert m.bouts and all(x.story in ("甲方佔了上風。", "乙方佔了上風。") for x in m.bouts)
    assert all(x.swing > 0 for x in m.bouts)


def test_bots_pick_one_preset_and_never_swap():
    game = season21_game()
    _drawn(game)
    pick = bots._preset(game)
    for o in game.options():
        if o.id.startswith("lunjian:swap:"):
            assert bots.idle(game, o)
        if o.id.startswith("lunjian:preset:"):
            assert bots.idle(game, o) == (o.id != f"lunjian:preset:{pick}")
    actions.act(game, f"preset:{pick}")
    assert bots.idle(game, Option(id=f"lunjian:preset:{pick}", label=""))
