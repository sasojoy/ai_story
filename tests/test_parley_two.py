"""開口求人第二批（Joy 2026-10-23「先繼續完成後面的」；tianxia/parley.py、Game._parley_*）：
先做後付與食言（守約紀錄、情誼扣、盟友聽說、天花板每筆 −broken_cut、做到一件抵一筆）、人物主動開口（求見時他先求你，
接了是委託、做到他回報）、同行中的自由文字（帶路的路上每到一站說一句、出陣前商量打法：模型評機率、引擎夾、引擎擲）。"""

from unittest import mock

import pytest

from tianxia import bounties, companion_agent, figure_life, parley, relations, team
from tianxia.companion_agent import CompanionTurn
from tianxia.engine import PLAN_OPTION, ROAD_SAY
from tianxia.state import ParleyBacking, ParleyDebt, ParleyRecord

DAY = 86400


def _turn(narrative="他點了點頭。", **extra):
    return CompanionTurn(narrative=narrative, options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "尋常寒暄"], **extra)


OPEN = _turn()


@pytest.fixture
def on(content):
    content.config.parley.enabled = True
    content.characters["mate"].deep_interaction = True
    content.characters["mate"].haunts = ["lake"]
    return content


@pytest.fixture
def talking(on, game):
    with mock.patch.object(companion_agent, "_generate", return_value=OPEN):
        game.choose("act:socialize")
    assert game.state.player.pending_companion == "mate"
    return game


def _say(game, turn, text="韓兄幫我一個忙", dice=1, option="talk:say"):
    with mock.patch.object(companion_agent, "generate_turn", return_value=turn), \
            mock.patch.object(parley, "roll", return_value=dice):
        return game.choose(option, text=text)


def _ids(game):
    return [o.id for o in game.options(odds=False)]


# ── 先做後付與食言 ────────────


def test_a_hit_with_a_condition_is_done_now_and_owed(talking):
    p = talking.state.player
    p.stats["silver"] = 100
    msgs = _say(talking, _turn(ask="spar", willing=100, condition="silver", narrative_terms="先教你，回頭拿二十兩來。"))
    assert "先教你，回頭拿二十兩來。" in msgs and "心得 +15" in msgs
    assert any(m.startswith("（你求韓鐵指點一招，他答應了，先替你做。你欠他一件：交 20 兩銀子") for m in msgs)
    debt = p.parley_debts["mate"]
    assert (debt.kind, debt.condition, debt.task) == ("owe", "silver", None)
    assert p.parley_records["mate"].promised == 1
    labels = {o.id: o.label for o in talking.options(odds=False)}
    assert labels["talk:repay"] == "還韓鐵：交 20 兩銀子"
    msgs = talking.choose("talk:repay")
    assert "銀兩 -20" in msgs and p.stats["silver"] == 80 and "mate" not in p.parley_debts
    assert p.parley_records["mate"].kept == 1 and p.talk_memos["mate"].text.startswith("答應他的事做到了")


def test_he_does_not_lend_twice(talking):
    talking.state.player.parley_debts["mate"] = ParleyDebt(kind="owe", condition="silver", due=10 * DAY)
    assert not parley.can_owe(talking.state, talking.content, "mate")
    _say(talking, _turn(ask="gift", willing=100, condition="silver"))
    assert "mate" in talking.state.player.parley_terms  # 欠著一件：擲中也只肯先付後做


def test_an_owed_scout_becomes_a_commission_and_lapses_into_a_broken_promise(talking, monkeypatch):
    p, c = talking.state.player, talking.content
    monkeypatch.setattr(relations, "allies", lambda content, cid: ["scholar"] if cid == "mate" else [])
    p.affinities["mate"], p.affinities["scholar"] = 40, 20
    _say(talking, _turn(ask="spar", willing=100, condition="scout:lake"))
    debt = p.parley_debts["mate"]
    letter = p.letters[-1]
    assert letter.kind == "條件" and letter.task.id == debt.task and letter.task.expires == debt.due
    assert bounties.open_commissions(talking.state, c)[-1].location == "lake"
    talking.state.world.time = debt.due
    msgs = parley.lapse(talking.state, c)
    assert msgs[0] == "【食言】你答應韓鐵的事沒做到（替他打探湖邊），韓鐵情誼 -15。"
    assert msgs[1] == "書生聽說你對韓鐵食言，情誼各 -3。"
    assert p.affinities["mate"] < 40 and p.affinities["scholar"] == 17 and letter.lapsed
    assert p.parley_records["mate"] == ParleyRecord(promised=1, broken=1, owing=1)
    assert p.parley_records["scholar"].heard == ["mate"] and "聽說你答應韓鐵的事沒做到" in p.hearsay["scholar"]
    assert parley.broken_of(talking.state, "scholar") == 1 and "mate" not in p.parley_debts


def test_broken_promises_lower_the_ceiling_and_a_kept_one_pays_one_back(talking):
    c, s = talking.content, talking.state
    assert parley.ceiling(c, 0, 1, False, broken=2) == 30
    s.player.parley_records["mate"] = ParleyRecord(promised=2, broken=1, owing=1, heard=["scholar"])
    parley.keep(s, c, "mate", "替他打探湖邊")
    assert (s.player.parley_records["mate"].owing, s.player.parley_records["mate"].heard) == (0, ["scholar"])
    parley.keep(s, c, "mate", "替他打探湖邊")
    assert s.player.parley_records["mate"].heard == [] and parley.broken_of(s, "mate") == 0


def test_the_promise_record_reaches_the_dialogue_prompt(talking):
    s = talking.state
    s.player.parley_records["mate"] = ParleyRecord(promised=3, kept=1, broken=2, owing=2, heard=["scholar"])
    line = parley.prompt_lines(s, talking.content, "mate")
    assert line.startswith("【守約紀錄】") and "答應過韓鐵 3 件事，做到 1 件" in line and "食言 2 件" in line and "書生" in line
    prompt = companion_agent.build_system_prompt(talking.content.characters["mate"], s, talking.content, talking.world, "mate")
    assert "【守約紀錄】" in prompt


def test_defecting_breaks_every_promise(talking):
    s = talking.state
    s.player.parley_debts["mate"] = ParleyDebt(kind="plea", condition="scout:lake", due=s.world.time + 10 * DAY)
    msgs = parley.forsake_all(s, talking.content)
    assert msgs[0].startswith("【食言】你答應韓鐵的事沒做到") and "-8" in msgs[0] and not s.player.parley_debts


def test_doing_a_terms_commission_counts_as_kept(talking):
    s, c = talking.state, talking.content
    _say(talking, _turn(ask="spar", willing=0, condition="scout:lake"), dice=100)
    talking.choose("talk:terms:yes")
    task = s.player.letters[-1].task
    bounties._complete_commission(s, c, task)
    record = s.player.parley_records["mate"]
    assert (record.promised, record.kept) == (1, 1) and s.player.parley_owed["mate"] == "spar"


# ── 人物主動開口 ────────────


def _plea_open(game, turn, mood="焦慮"):
    with mock.patch.object(figure_life, "mood_any", return_value=mood), \
            mock.patch.object(companion_agent, "_generate", return_value=turn) as gen:
        msgs = game.choose("act:socialize")
    return msgs, gen


def test_a_worried_figure_asks_first_and_the_ask_becomes_a_commission(on, game):
    plea = _turn("韓鐵拉住你：「湖邊有怪動靜，你替我去看看，回來我教你兩手。」", want="scout:lake", reward="spar")
    msgs, gen = _plea_open(game, plea)
    assert "【韓鐵有求於玩家】" in gen.call_args.kwargs["extra"] and "scout:lake" in gen.call_args.kwargs["extra"]
    labels = {o.id: o.label for o in game.options(odds=False)}
    assert labels["talk:terms:yes"] == "接下：替他打探湖邊（他回報：指點一招）" and labels["talk:terms:no"] == "不接"
    msgs = game.choose("talk:terms:yes")
    p = game.state.player
    assert msgs[0].startswith("你接下了韓鐵的請託：替他打探湖邊") and p.parley_debts["mate"].kind == "plea"
    task = p.letters[-1].task
    done = bounties._complete_commission(game.state, game.content, task)
    assert "下回見到韓鐵，他會兌現答應你的事。" in done
    assert p.parley_owed["mate"] == "spar" and "mate" not in p.parley_debts and p.parley_records["mate"].kept == 1


def test_a_plea_comes_once_a_day_and_only_with_something_on_his_mind(on, game):
    plea = _turn(want="scout:lake", reward="spar")
    _, gen = _plea_open(game, plea, mood="平靜")
    assert gen.call_args.kwargs["extra"] == "" and "mate" not in game.state.player.parley_terms
    game.choose("talk:leave")
    _plea_open(game, plea)
    game.choose("talk:terms:no")
    game.choose("talk:leave")
    _, gen = _plea_open(game, plea)
    assert gen.call_args.kwargs["extra"] == ""  # 今天開口過了


def test_a_reward_off_the_list_or_heavier_than_the_ask_is_ignored(on, game):
    _plea_open(game, _turn(want="scout:lake", reward="sortie"))  # 陪你出陣不當回報
    assert "mate" not in game.state.player.parley_terms
    want, reward = parley.Item("scout:lake", "替他打探湖邊", 1), parley.Item("escort:far", "帶路", 2)
    assert parley.plea_pick([want], [reward], "scout:lake", "escort:far") is None


# ── 同行中的自由文字 ────────────


def test_on_the_road_with_him_you_get_one_line_per_stop(talking):
    p = talking.state.player
    _say(talking, _turn(ask="escort:lake", willing=100), text="帶我去湖邊")
    assert p.journey is not None and p.parley_escort == "mate"
    labels = {o.id: o.label for o in talking.options(odds=False)}
    assert labels[ROAD_SAY] == "跟韓鐵說…"
    before = p.stamina
    msgs = _say(talking, _turn("他邊走邊說起湖邊的舊事。", ask="spar", willing=100), text="韓兄路上指點兩招", option=ROAD_SAY)
    assert msgs[0] == "你：「韓兄路上指點兩招」" and "他邊走邊說起湖邊的舊事。" in msgs and "心得 +15" in msgs
    assert p.stamina == before and ROAD_SAY not in _ids(talking)  # 不花體力；這一站說過了


def test_on_the_road_he_cannot_be_asked_to_lead_elsewhere(talking):
    _say(talking, _turn(ask="escort:lake", willing=100), text="帶我去湖邊")
    msgs = _say(talking, _turn(ask="escort:town", willing=100), text="改去城裡", option=ROAD_SAY)
    assert any("他沒有答應" in m for m in msgs)


def test_walking_off_alone_clears_the_escort(talking):
    _say(talking, _turn(ask="escort:lake", willing=100), text="帶我去湖邊")
    talking.choose("road:back")
    assert talking.state.player.parley_escort is None


def _backed(game):
    s = game.state
    s.player.parley_backing = ParleyBacking(figure="mate", region=None, day=parley.game_day(game.content, s.world))


def test_you_can_plan_the_sortie_with_him_and_the_engine_rolls(talking):
    _backed(talking)
    labels = {o.id: o.label for o in talking.options(odds=False)}
    assert labels[PLAN_OPTION] == "跟韓鐵商量打法…"
    turn = _turn("韓鐵點頭：「我從左翼包抄。」", willing=100, narrative_no="韓鐵搖頭。")
    with mock.patch.object(companion_agent, "generate_turn", return_value=turn), \
            mock.patch.object(parley, "plan_roll", return_value=85):
        msgs = talking.choose(PLAN_OPTION, text="將軍從左翼包抄，我正面纏住")
    assert msgs == ["你：「將軍從左翼包抄，我正面纏住」", "韓鐵點頭：「我從左翼包抄。」", "（韓鐵照你的打法布置：這一仗他的部曲出力加倍。）"]
    assert talking.state.player.parley_backing.plan is True and PLAN_OPTION not in _ids(talking)


def test_the_plan_is_clamped_like_a_gamble(talking):
    _backed(talking)
    turn = _turn("成", willing=100, narrative_no="韓鐵搖頭：「太險。」")
    with mock.patch.object(companion_agent, "generate_turn", return_value=turn), \
            mock.patch.object(parley, "plan_roll", return_value=86):  # 模型說 100，夾到 85
        msgs = talking.choose(PLAN_OPTION, text="直接衝他中軍")
    assert msgs[1] == "韓鐵搖頭：「太險。」" and talking.state.player.parley_backing.plan is False


@pytest.mark.parametrize("plan, factor", [(None, 1.3), (True, 1.6), (False, 1.0)])
def test_the_plan_sets_his_share_in_the_sortie(talking, plan, factor):
    talking.choose("talk:leave")
    _backed(talking)
    talking.state.player.parley_backing.plan = plan
    seen = []
    real = team.backed

    def spy(f):
        seen.append(f)
        return real(f)

    with mock.patch.object(team, "backed", side_effect=spy), mock.patch.object(talking, "_parley_backing_here", return_value="mate"), \
            mock.patch.object(talking, "_sortie", return_value=["打了一仗"]), mock.patch.object(talking, "_train", return_value=["打了一仗"]):
        talking._act("train", None)
    assert seen == [pytest.approx(factor)] and talking.state.player.parley_backing is None


# ── 開關關著 ────────────


def test_off_switch_adds_no_plea_road_or_plan(content, game):
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(figure_life, "mood_any", return_value="焦慮"), \
            mock.patch.object(companion_agent, "_generate", return_value=OPEN) as gen:
        game.choose("act:socialize")
    assert gen.call_args.kwargs["extra"] == ""
    _backed(game)
    assert PLAN_OPTION not in _ids(game)
    game.state.player.parley_debts["mate"] = ParleyDebt(kind="owe", condition="silver", due=0)
    assert parley.prompt_lines(game.state, content, "mate") == ""
