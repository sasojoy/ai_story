"""託付與來信（減法季批 6 Task 6-2；整合設計 5.5、5.9；tianxia/errands.py）：情誼到 letter_affinity 的大勢人物每週託你一件事，
以一封「託付」信送到（早上的那一封，letters.deliver 的第一順位）；一人同時最多一件；送信（走到就交）、探營（不打仗的探查，回一張卡
留在見聞）、勸降（寫一句，模型評成功率、引擎夾、成了立痕跡推線、敗了打一場）。辦成了情誼、心意 +1、貢獻、行狀；過期作罷情誼 −2、
婉拒不扣。假人不收託付。正式內容的 season21（盧植、波才、皇甫嵩各三件）；模型一律是假的。"""
from __future__ import annotations

import pytest

from stances_kit import BOCAI, DAY, HUANGFU, LUZHI, at, real_game
from tianxia import annals, errands, letters, rules, stances
from tianxia.state import BotProfile


def _friend(g, cid=LUZHI, affinity=50):
    g.state.player.affinities[cid] = affinity


def _give(g, fid, eid):
    """直接開一件（同 errands.offer 挑中之後那一下）：信附在身上，回那一件。"""
    errands.give(g.state, g.content, fid, eid)
    return g.state.player.errands[-1]


def _press(g, option_id):
    opts = {o.id: o for o in g.options(odds=False)}
    assert option_id in opts and opts[option_id].enabled, sorted(opts)
    return g.choose(option_id)


def test_a_friend_sends_one_errand_letter_and_it_leads_the_week_card():
    g = real_game()
    s, c = g.state, g.content
    assert not s.player.errands
    _friend(g)
    at(g, g.now + 60)
    [e] = s.player.errands
    assert (e.figure, e.status) == (LUZHI, "open") and e.kind in ("letter", "scout", "persuade")
    letter = letters.find(s, e.letter)
    assert (letter.kind, letter.sender, letter.task) == ("託付", LUZHI, None)
    card = g.letter_view()
    assert card["kind"] == "託付" and card["open"] and card["errand"]["id"] == e.id and card["errand"]["status"] == "open"
    row = errands.view(s, c)[0]
    assert row["id"] == e.id and row["figure"] == LUZHI and row["who"] == "盧植" and row["kind"] == e.kind
    assert row["target"]["location"] == e.target and row["target"]["name"] == c.locations[e.target].name and row["target"]["minutes"] >= 1
    assert row["deadline"].startswith("第 ") and row["status"] == "open"
    [step] = errands.step_items(s, c)
    assert {k: step[k] for k in ("kind", "text", "who", "id")} == {"kind": "errand", "text": errands.STEP.format(
        place=c.locations[e.target].name, who="盧植", label=errands.LABELS[e.kind]), "who": "盧植", "id": e.id}


def test_one_errand_at_a_time_and_one_per_figure_per_week():
    g = real_game()
    s = g.state
    _friend(g)
    _friend(g, HUANGFU)
    at(g, g.now + 60)
    first = s.player.errands[-1]
    at(g, g.now + DAY)  # 隔天早上：身上那一件還沒辦完，誰都不再託
    assert len(s.player.errands) == 1
    first.status = "done"
    at(g, g.now + DAY)
    second = s.player.errands[-1]
    assert len(s.player.errands) == 2 and second.figure != first.figure  # 同一位人物一週一件
    second.status = "done"
    at(g, g.now + DAY)
    assert len(s.player.errands) == 2  # 兩位都託過了：這一週沒有了


def test_bots_get_no_errands():
    g = real_game()
    g.state.player.bot = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    _friend(g)
    at(g, g.now + 60)
    assert not g.state.player.errands


def test_delivering_the_letter_pays_affinity_contribution_a_stance_and_an_annal():
    g = real_game(setup=lambda c: setattr(c.config.biography, "enabled", True))
    s, c = g.state, g.content
    _friend(g)
    e = _give(g, LUZHI, "luzhi_letter")
    assert errands.here(s, c) == []  # 還沒到長社：此地沒有那一顆
    s.player.location = e.target
    affinity, contrib = s.player.affinities[LUZHI], s.player.contrib
    msgs = _press(g, f"errand:deliver:{e.id}")
    assert e.status == "done" and e.done_at is not None
    # 情誼 +5 照寫的數字給（PM 2026-10-26 修正輪推翻「照 affinity_gain_scale 放慢」；新規則的測試在 test_errands_fix6.py）
    assert s.player.affinities[LUZHI] == affinity + 5 and s.player.contrib == contrib + 4
    assert s.world.stance_counts[LUZHI]["chizhong"] == 1  # 心意 +1（這一件寫的是持重），不佔你一天一筆
    assert stances.heard_today(s, c, LUZHI) is None
    note = [a for a in s.player.annals if a.kind == annals.ERRAND]
    assert len(note) == 1 and "盧植" in note[0].text and note[0].figure == LUZHI
    assert s.player.letters[-1].kind == "道謝" and s.player.letters[-1].sender == LUZHI  # 下一封來信是道謝
    assert any("交" in m for m in msgs)
    assert f"errand:deliver:{e.id}" not in {o.id for o in g.options(odds=False)}


def test_scouting_costs_stamina_and_leaves_a_card_in_your_rumors():
    g = real_game()
    s, c = g.state, g.content
    _friend(g)
    e = _give(g, LUZHI, "luzhi_scout")
    s.player.location = e.target
    stamina = s.player.stamina
    msgs = _press(g, f"errand:scout:{e.id}")
    assert e.status == "done"
    assert s.player.stamina == pytest.approx(stamina - c.config.jianfa.errand_stamina)
    mine = [r for r in g.world.get_season().rumors if r.layer == "personal" and r.character == s.player.name]
    assert mine and mine[-1].text.startswith(errands.SCOUT_TITLE.format(place=c.locations[e.target].name))
    assert any("守" in m for m in msgs)  # 守將或守在這裡的隊伍


def test_a_lapsed_errand_costs_two_affinity_and_declining_costs_nothing():
    g = real_game()
    s, c = g.state, g.content
    _friend(g)
    e = _give(g, LUZHI, "luzhi_letter")
    g._save_season()
    at(g, g.now + 3 * DAY)
    assert e.status == "lapsed" and s.player.affinities[LUZHI] == 50 - c.config.jianfa.errand_lapse_affinity
    assert letters.find(s, e.letter).lapsed
    _friend(g, HUANGFU)
    other = _give(g, HUANGFU, "huangfu_letter")
    msgs = g.decline_letter(other.letter)
    assert other.status == "declined" and s.player.affinities[HUANGFU] == 50 and msgs


@pytest.mark.parametrize("floor_cap, status", [(100, "done"), (0, "failed")])
def test_persuading_succeeds_or_ends_in_a_fight(floor_cap, status):
    def setup(c):
        c.config.jianfa.persuade_floor = c.config.jianfa.persuade_cap = floor_cap
    g = real_game(setup=setup)
    s, c = g.state, g.content
    _friend(g)
    e = _give(g, LUZHI, "luzhi_persuade")
    s.player.location = e.target
    assert _press(g, f"errand:persuade:{e.id}") == [errands.PERSUADE_ASK]  # 按下去只叫出輸入框
    assert e.status == "open"
    before = rules.trend_value(s, c, "jizhou")
    battles = len(s.battles)
    request = g.persuade_request(e.id, "放下刀槍，回家種田吧")
    assert request.errand == e.id and request.text == "放下刀槍，回家種田吧"
    g.persuade(request, 60)
    assert e.status == status
    if status == "done":
        assert s.world.marks["xiaquyang:band_turned"] == 1 and rules.trend_value(s, c, "jizhou") < before
        assert len(s.battles) == battles
    else:
        assert len(s.battles) == battles + 1 and "xiaquyang:band_turned" not in s.world.marks


def test_persuading_without_the_model_changes_nothing():
    """模型叫不動（rate 是 None）：照批 4 的慣例落到最保守的結果——沒談成也不打、不扣體力，那一件照舊還在、可以再去。"""
    g = real_game()
    s, c = g.state, g.content
    _friend(g)
    e = _give(g, LUZHI, "luzhi_persuade")
    s.player.location = e.target
    stamina = s.player.stamina
    msgs = g.persuade(g.persuade_request(e.id, "放下刀槍"), None)
    assert e.status == "open" and s.player.stamina == stamina and msgs == [errands.PERSUADE_SILENT]


def test_persuade_requests_are_refused_away_from_the_spot_or_with_bad_text():
    g = real_game()
    s = g.state
    _friend(g)
    e = _give(g, LUZHI, "luzhi_persuade")
    assert g.persuade_request(e.id, "放下刀槍") == [errands.NOT_HERE]
    s.player.location = e.target
    assert g.persuade_request(e.id, "") == [errands.PERSUADE_ASK]
    assert g.persuade_request(e.id, "放" * 30) == [errands.PERSUADE_ASK]
    assert g.persuade_request("e999", "放下刀槍") == [errands.NOT_HERE]


def test_rate_persuasion_reads_one_number_and_gives_up_quietly():
    from tianxia import event_llm

    request = errands.PersuadeRequest(errand="e1", figure="盧植", who="黃巾的小頭目", place="下曲陽", text="放下刀槍")
    sent = {}

    class Client:
        def __init__(self, value):
            self.value = value

        def chat_structured(self, messages, model, **kwargs):
            sent.update(kwargs, messages=messages)
            if isinstance(self.value, Exception):
                raise self.value
            return model.model_validate({"success_rate": self.value})

    assert event_llm.rate_persuasion(Client(72), request) == 72
    assert sent["schema_required"] == ["success_rate"] and "放下刀槍" in sent["messages"][-1]["content"]
    assert event_llm.rate_persuasion(Client("88.6"), request) == 89
    assert event_llm.rate_persuasion(Client(ValueError("壞了")), request) is None
    assert event_llm.rate_persuasion(None, request) is None
    assert event_llm.rate_persuasion(Client(50), request.model_copy(update={"text": "  "})) is None


def test_closed_seasons_send_no_errands():
    g = real_game(setup=lambda c: setattr(c.config.jianfa, "errands", False))
    s, c = g.state, g.content
    _friend(g)
    at(g, g.now + 60)
    assert not s.player.errands and errands.view(s, c) == [] and errands.step_items(s, c) == []
    assert not [o for o in g.options(odds=False) if o.id.startswith("errand:")]


def test_bocai_errands_push_toward_the_yellow_turbans():
    c = real_game().content
    bocai = {d.id: d for d in c.figures[BOCAI].errands}
    assert bocai["bocai_persuade"].persuade.trend == {"front": 2}  # 往黃巾為正
    assert all(len(c.figures[f].errands) == 3 and {d.kind for d in c.figures[f].errands} == {"letter", "scout", "persuade"}
               for f in (LUZHI, BOCAI, HUANGFU))
