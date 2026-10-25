"""減法季批 4 接線（主機側計畫 Task 4-2、6.5 的勾選清單；整合設計 5.1、5.3、5.9；PM 2026-10-25 交接第四節之四）：
隨口應對分岔的 C 段（Game.answer_event 照 outcomes.plan 分四條走）、貢獻與每日上限、行狀不存句子、選單與欄位表的 options[].outcomes，
與「關著一個字都不變」。模型一律是假的：C 段直接拿歸好類的 outcome（tests/outcomes_kit.answer），或 mock 掉 event_llm。"""
from __future__ import annotations

import pytest

from conftest import FixedRandom
from outcomes_kit import CHASE, GIVE, LEAVE, OLD, OLD_FAIL, PROMPT, TALK, answer, branch_game, fight
from tianxia import annals, calendar, event_llm, events, outcomes, rules
from tianxia.engine import EVIL_ANNAL, FREE_TEXT_OPTION
from tianxia.models import Effect, FreeTextChoice

SAID = "我把他押去見官"


def _snapshot(game):
    p = game.state.player
    entry = game.state.journal[0]
    return {
        "stats": dict(p.stats), "stamina": p.stamina, "contrib": p.contrib, "marks": dict(game.state.world.marks),
        "lines": list(entry.lines), "changes": list(entry.changes), "tag": entry.tag, "title": entry.title,
        "annals": [(a.kind, a.text, a.quote) for a in p.annals], "rng": game.rng.getstate(),
        "outcome": game.last_gamble.model_dump(exclude={"time"}) if game.last_gamble else None,
        "pending": game.state.pending_event, "json": sorted(p.model_dump()),
    }


# ── 四條路 ────────────────────────────────────────────────


def test_a_combat_outcome_fights_and_on_a_win_leaves_its_mark_and_contribution(content, world):
    g = branch_game(content, world)
    p = g.state.player
    fame, contrib = p.stats.get("fame", 0), p.contrib
    with fight("險勝"):
        answer(g, SAID, "chase")
    assert g.state.pending_event is None
    record = g.state.battles[0]
    assert record.kind == "event" and record.tier == "險勝"
    assert p.stats["fame"] == fame + 1  # 贏了套 effect
    assert g.state.world.marks["town:扭送"] == 1  # 痕跡 +1
    assert p.contrib == contrib + 4  # 貢獻 +4（wins.credit）
    entry = g.state.journal[0]
    assert entry.title == "醉漢・隨口應對" and entry.lines[0].startswith(f"你：「{SAID}」（扭送）")
    assert CHASE.effect.text in entry.lines
    assert g.last_gamble.outcome == "chase" and g.last_gamble.success is True
    assert g.last_gamble.effect_text == CHASE.effect.text


def test_a_lost_fight_takes_the_fail_effect_without_mark_or_contribution(content, world):
    g = branch_game(content, world)
    p = g.state.player
    contrib = p.contrib
    with fight("落敗"):
        answer(g, SAID, "chase")
    assert "town:扭送" not in g.state.world.marks and p.contrib == contrib
    assert CHASE.fail_effect.text in g.state.journal[0].lines
    assert g.last_gamble.success is False and g.last_gamble.effect_text == CHASE.fail_effect.text


@pytest.mark.parametrize("said", ["fly", "", None, "LEAVE"])
def test_an_unlisted_outcome_is_the_fallback(content, world, said):
    """模型回的 id 不在清單：一律最後一種（計畫 Review Focus 第 4 條），只套那一句、不擲骰、不留痕跡、不記貢獻。"""
    g = branch_game(content, world)
    rng = g.rng.getstate()
    contrib = g.state.player.contrib
    answer(g, "跟他聊聊天氣", said)
    assert g.state.pending_event is None and g.rng.getstate() == rng
    assert LEAVE.effect.text in g.state.journal[0].lines
    assert not g.state.world.marks and g.state.player.contrib == contrib
    assert g.last_gamble.outcome == "leave" and g.last_gamble.success is True


def test_paying_without_the_silver_does_nothing_and_keeps_the_event(content, world):
    """掏錢的後果：銀兩不夠就回那一句、不做、不扣次數（事件還停著，可以再寫一句）；什麼都不寫進江湖紀錄。"""
    g = branch_game(content, world, silver=9)
    before = len(g.state.journal)
    msgs = answer(g, "給他十兩去喝醒酒湯", "give")
    assert outcomes.NOT_ENOUGH_SILVER in msgs
    assert g.state.pending_event == "drunk" and g.state.player.stats["silver"] == 9
    assert len(g.state.journal) == before and g.last_gamble is None
    assert FREE_TEXT_OPTION in {o.id for o in g.options()}  # 還按得到隨口應對


def test_paying_with_the_silver_always_works_and_does_not_roll(content, world):
    g = branch_game(content, world, silver=30)
    rng = g.rng.getstate()
    contrib = g.state.player.contrib
    answer(g, "給他十兩去喝醒酒湯", "give", rate=0)  # 成功率 0 也成：掏錢必成（企劃者第 8 件 c）
    p = g.state.player
    assert p.stats["silver"] == 20 and p.stats["good"] == 1 and g.rng.getstate() == rng
    assert g.state.world.marks["town:周濟"] == 1 and p.contrib == contrib + 1
    assert "銀兩 -10" in g.state.journal[0].changes
    assert g.last_gamble.outcome == "give" and g.last_gamble.success


def _talk_rate(g, llm):
    return outcomes.rate(TALK, llm, g.state, g.content, g.world)


def test_a_check_outcome_rolls_on_its_best_stat_against_its_difficulty(content, world):
    """PM 2026-10-25 第 3 件：成功率＝模型分數＋（屬性 − 那一種後果的難度）× 4，夾 5～85；best_of 取最高的那一項。"""
    g = branch_game(content, world)
    g.state.player.stats.update(str=8, wis=3)
    assert _talk_rate(g, 40) == 40 + (8 - TALK.check.difficulty) * rules.FREE_TEXT_PER_POINT == 56
    g.state.player.stats.update(str=3, wis=9)
    assert _talk_rate(g, 40) == 40 + (9 - 4) * 4 == 60
    assert _talk_rate(g, 100) == rules.FREE_TEXT_MAX_RATE
    assert _talk_rate(g, -50) == 0 + (9 - 4) * 4  # 模型的分數先夾到 0
    g.state.player.stats.update(str=0, wis=0)
    assert _talk_rate(g, 0) == rules.FREE_TEXT_MIN_RATE


@pytest.mark.parametrize("roll, landed", [(0.595, True), (0.605, False)])
def test_a_check_outcome_lands_or_misses_on_the_engine_roll(content, world, roll, landed):
    g = branch_game(content, world, rng=FixedRandom(roll))
    p = g.state.player
    p.stats.update(str=3, wis=9)  # 40 ＋（9 − 4）× 4 ＝ 60
    good, stamina, contrib = p.stats.get("good", 0), p.stamina, p.contrib
    answer(g, "我好言勸他回家", "talk", rate=40)
    entry = g.state.journal[0]
    assert entry.lines[0] == "你：「我好言勸他回家」（勸說・成算六成）"
    assert entry.tag == ("成功" if landed else "失敗")
    if landed:
        assert p.stats["good"] == good + 2 and g.state.world.marks["town:勸醒"] == 1 and p.contrib == contrib + 2
    else:
        assert p.stats.get("good", 0) == good and "town:勸醒" not in g.state.world.marks and p.contrib == contrib
        assert p.stamina == stamina + rules.fail_stamina(-10, content)  # 失手另扣的體力照縮
    assert g.last_gamble.success is landed


# ── 貢獻：每天上限、散人不記、作惡不記 ─────────────────────────


def test_the_daily_deed_contribution_is_capped(content, world):
    g = branch_game(content, world)
    p = g.state.player
    cap = content.config.jianfa.deed_contribution_cap
    assert cap == 12  # 【預設】
    w = g.state.world
    today = calendar.point(w.time, content, w).cal_day
    p.deed_day, p.deed_today = today, cap - 2
    contrib = p.contrib
    with fight("大勝"):
        answer(g, SAID, "chase")
    assert p.contrib == contrib + 2 and p.deed_today == cap  # 只記得進兩點
    g.state.pending_event = "drunk"
    p.deed_day = today - 1  # 換了一天：重新算
    with fight("大勝"):
        answer(g, SAID, "chase")
    assert p.contrib == contrib + 2 + 4 and (p.deed_day, p.deed_today) == (today, 4)


def test_a_ranger_pushes_marks_but_records_no_contribution(content, world):
    g = branch_game(content, world, faction=None)
    with fight("大勝"):
        answer(g, SAID, "chase")
    assert g.state.world.marks["town:扭送"] == 1 and g.state.player.contrib == 0


def test_the_evil_outcome_marks_but_never_credits_and_ignores_the_moral(content, world):
    """作惡那一種（PM 第 6 件）：留壞痕跡、扣善名、不記貢獻。善惡評分（FB-223）只在歸到最後一種時才看（PM 第 8 件）：
    選中作惡那一種時善惡怎麼評都不換效果。"""
    g = branch_game(content, world, rng=FixedRandom(0.0))
    p = g.state.player
    p.stats.update(good=3, evil=0)
    contrib = p.contrib
    answer(g, "趁他醉倒摸他的錢袋", "rob", moral="惡")
    assert p.stats["good"] == 2 and p.stats.get("evil", 0) == 0  # 照後果自己的效果：善名 −1，沒有另換成惡名
    assert g.state.world.marks["town:搜身"] == 1 and p.contrib == contrib
    assert g.last_gamble.evil is False


def test_a_good_outcome_is_not_turned_evil_by_the_moral(content, world):
    g = branch_game(content, world, rng=FixedRandom(0.0))
    p = g.state.player
    p.stats.update(good=3, evil=0)
    answer(g, "我好言勸他回家", "talk", moral="惡")
    assert p.stats["good"] == 5 and p.stats.get("evil", 0) == 0 and g.last_gamble.evil is False
    assert TALK.effect.text in g.state.journal[0].lines


def test_paying_is_never_turned_evil_by_the_moral(content, world):
    """掏錢的後果也不擲骰、必成，但它不是最後一種：善惡怎麼評都照那一種自己的效果（PM 第 8 件）。"""
    g = branch_game(content, world, silver=30)
    answer(g, "給他十兩去喝醒酒湯", "give", moral="惡")
    assert g.last_gamble.evil is False and GIVE.effect.text in g.state.journal[0].lines
    assert g.state.player.stats["good"] == 1 and g.state.player.stats.get("evil", 0) == 0


def test_the_fallback_still_reads_the_moral_like_before(content, world):
    """歸到最後一種：照舊用模型的善惡評分（FB-223）——判「惡」就是惡行成了（rules.EVIL_DONE、行狀照實寫），潤色照惡行寫。"""
    g = branch_game(content, world)
    answer(g, "一刀把他砍了", "leave", moral="惡")
    entry = g.state.journal[0]
    assert rules.EVIL_DONE in entry.lines and LEAVE.effect.text not in entry.lines
    assert g.last_gamble.evil is True and g.last_gamble.effect_text == rules.EVIL_DONE
    assert any(a.text.endswith(EVIL_ANNAL) for a in g.state.player.annals if a.kind == annals.DEED)


# ── 行狀不存句子 ─────────────────────────────────────────────


def test_the_annal_keeps_the_outcome_but_never_the_players_words(content, world):
    g = branch_game(content, world)
    with fight("大勝"):
        answer(g, SAID, "chase")
    deeds = [a for a in g.state.player.annals if "隨口應對" in a.text]
    assert len(deeds) == 1 and deeds[0].quote == ""
    assert "扭送" in deeds[0].text and SAID not in deeds[0].text
    assert all(SAID not in a.text and SAID not in a.quote for a in g.state.player.annals)


# ── 選單、欄位表、單子 ─────────────────────────────────────────


def test_the_free_text_button_lists_the_outcome_tags_when_on(content, world):
    g = branch_game(content, world)
    button = next(o for o in g.options() if o.id == FREE_TEXT_OPTION)
    assert button.outcomes == [{"id": o.id, "tag": o.tag} for o in content.events["drunk"].free_text.outcomes]
    assert button.model_dump()["outcomes"] == button.outcomes  # 欄位表 1.3：main.options[].outcomes
    assert button.label == PROMPT + events.WRITE_NOTE
    request = g.free_text_request(SAID)
    assert request.outcomes == button.outcomes


@pytest.mark.parametrize("parts", [None, {"free_text_outcomes": False}], ids=["off", "sub-switch-off"])
def test_the_button_is_the_old_one_when_off(content, world, parts):
    g = branch_game(content, world, on=parts is not None, parts=parts)
    button = next(o for o in g.options() if o.id == FREE_TEXT_OPTION)
    assert button.outcomes is None and "outcomes" not in button.model_dump()
    assert not button.label.endswith(events.WRITE_NOTE)
    assert g.free_text_request(SAID).outcomes == []


def _outcomes_only(content):
    ft = content.events["drunk"].free_text
    content.events["drunk"].free_text = ft.model_copy(update={"outcomes_only": True, "effect": Effect(), "fail_effect": Effect()})


def test_an_outcomes_only_free_text_shows_only_when_on(content, world):
    """人拉犁（PM 第 7 件）：原本沒有隨口應對，補上的那一顆只在分岔開著時才畫；關著的季不多一顆鈕、提示語與新手提示也沒有。"""
    g_off = branch_game(content, world, name="甲", on=False)
    _outcomes_only(content)
    assert FREE_TEXT_OPTION not in {o.id for o in g_off.options()}
    assert g_off.event_free_text_prompt() is None and g_off.free_text_request(SAID) is None
    g_on = branch_game(content, world, name="乙", on=True)
    _outcomes_only(content)
    assert FREE_TEXT_OPTION in {o.id for o in g_on.options()} and g_on.event_free_text_prompt() == PROMPT
    assert g_on.free_text_request(SAID) is not None


# ── 鎖內自己歸類（直接呼叫的測試、腳本） ─────────────────────────


def test_no_verdict_classifies_inside_the_lock(content, world, monkeypatch):
    g = branch_game(content, world, rng=FixedRandom(0.0))
    asked = []

    def classify(client, event, outs, text):
        asked.append((event.id, [o.id for o in outs], text))
        return "talk", 50

    monkeypatch.setattr(event_llm, "classify_outcome", classify)
    monkeypatch.setattr(event_llm, "judge_moral", lambda *a, **k: pytest.fail("不是最後一種，不判善惡"))
    g.answer_event(g.free_text_request("我好言勸他回家"))
    assert asked == [("drunk", [o.id for o in content.events["drunk"].free_text.outcomes], "我好言勸他回家")]
    assert g.last_gamble.outcome == "talk"


# ── 關著一個字都不變 ───────────────────────────────────────────


@pytest.mark.parametrize("roll", [0.0, 0.99], ids=["landed", "missed"])
@pytest.mark.parametrize("parts", [None, {"free_text_outcomes": False}], ids=["off", "sub-switch-off"])
def test_answering_is_unchanged_when_off(content, world, roll, parts):
    """關著（總開關或子開關）：有後果的事件照舊用 stat、effect、fail_effect 擲骰，跟沒寫後果的事件一個字都不差；
    傳進來的 outcome 不理（host 中途關掉時，B 段照舊歸過類的那一張單）。"""
    branched = branch_game(content, world, name="甲", on=parts is not None, parts=parts, rng=FixedRandom(roll))
    answer(branched, "大喊官兵來了", "chase", rate=50)
    plain = branch_game(content, world, name="乙", on=False, rng=FixedRandom(roll))
    content.events["drunk"].free_text = FreeTextChoice(prompt=PROMPT, stat="str", effect=OLD, fail_effect=OLD_FAIL)  # 沒寫後果
    plain.answer_event(plain.free_text_request("大喊官兵來了"), 50, None)
    got, want = _snapshot(branched), _snapshot(plain)
    assert got == want
    assert branched.state.journal[0].lines[0].startswith("你：「大喊官兵來了」（成算")
    assert "deed_day" not in branched.state.player.model_dump_json() and "deed_today" not in branched.state.player.model_dump_json()


def test_new_player_fields_add_no_keys_until_used(state):
    """存檔一個鍵都不多（tests/test_gentry_ledgers.py 的做法）：deed_day、deed_today 是預設值時不寫鍵，有值寫得出來、讀得回去。"""
    dumped = state.player.model_dump()
    assert "deed_day" not in dumped and "deed_today" not in dumped
    state.player.deed_day, state.player.deed_today = 3, 7
    again = type(state.player).model_validate_json(state.player.model_dump_json())
    assert (again.deed_day, again.deed_today) == (3, 7)


def test_the_kit_effect_is_not_an_outcome():
    """outcomes_kit.OLD 是關著時套的那一組：不是任何一種後果的效果（比對才比得出走錯了路）。"""
    assert OLD not in [o.effect for o in (TALK, CHASE, GIVE, LEAVE)] and OLD != Effect()
