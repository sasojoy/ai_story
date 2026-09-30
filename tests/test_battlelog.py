import random

from tianxia import battlelog
from tianxia.encounter import resolve_encounter
from tianxia.state import BattleRecord, Fighter

MAX_RECORDS = battlelog.MAX_RECORDS


def record(**kw):
    base = dict(
        id=3, time=86400 + 8 * 3600 + 30 * 60, location="湖邊", kind="train", opponent="劫道山賊",
        ours=[Fighter(name="沈浪", level=1)], tier="大勝", our_power=40.0, difficulty=5.0,
    )
    return BattleRecord(**(base | kw))


# ── 建立紀錄 ──────────────────────────────────────────


def test_new_record_captures_the_team_and_the_encounter_result(state, content, world):
    squad = content.squads["thug"]
    result = resolve_encounter(30, squad.difficulty, random.Random(0))
    rec = battlelog.new_record(state, content, world, squad, result, "train")
    assert rec.id == 1 and rec.location == "小鎮" and rec.kind == "train"
    assert rec.opponent == "水寇小隊" and rec.ours == [Fighter(name="沈浪", level=1)]
    assert (rec.tier, rec.our_power, rec.difficulty) == (result.tier, 30.0, squad.difficulty)
    assert rec.exp == 0 and rec.xinde == 0 and rec.silver == 0 and rec.notes == [] and rec.changes == []


def test_new_record_includes_the_team_at_their_current_levels(state, content, world):
    state.player.team.append("mate")
    state.player.member.level = 3
    world.update_companion("mate", lambda p: setattr(p, "level", 2))
    squad = content.squads["thug"]
    result = resolve_encounter(30, squad.difficulty, random.Random(0))
    rec = battlelog.new_record(state, content, world, squad, result, "event", "劇情")
    assert rec.kind == "event" and rec.event == "劇情"
    assert [(f.name, f.level) for f in rec.ours] == [("沈浪", 3), ("韓鐵", 2)]


def test_add_record_keeps_only_the_newest_records(state):
    for i in range(MAX_RECORDS + 5):
        battlelog.add_record(state, record(id=i + 1))
    assert len(state.battles) == MAX_RECORDS
    assert [r.id for r in state.battles[:2]] == [MAX_RECORDS + 5, MAX_RECORDS + 4]
    assert state.battles[-1].id == 6
    assert state.battle_seq == MAX_RECORDS + 5


def test_find_looks_up_by_id_or_returns_none(state):
    battlelog.add_record(state, record(id=1))
    battlelog.add_record(state, record(id=2))
    assert battlelog.find(state, 1).id == 1
    assert battlelog.find(state, None) is None
    assert battlelog.find(state, 999) is None


# ── 文字 ──────────────────────────────────────────────


def test_clock_text():
    assert battlelog.clock_text(86400 + 8 * 3600 + 30 * 60) == "第2天 08:30"
    assert battlelog.clock_text(0) == "第1天 00:00"


def test_outcome_and_summary_and_list_label_word_each_tier():
    rec = record()
    assert battlelog.outcome_text(rec) == "大勝劫道山賊"
    assert battlelog.summary_line(rec) == "⚔ 湖邊：大勝劫道山賊"
    assert battlelog.summary_line(record(tier="險勝")) == "⚔ 湖邊：險勝劫道山賊"
    assert battlelog.summary_line(record(tier="僵持")) == "⚔ 湖邊：平手劫道山賊"
    assert battlelog.summary_line(record(tier="落敗")) == "⚔ 湖邊：落敗劫道山賊"
    assert battlelog.list_label(rec) == "大勝　第3場　第2天 08:30　湖邊　vs 劫道山賊"


def test_split_changes_separates_numeric_deltas_from_narrative():
    changes, notes = battlelog.split_changes([
        "名望 +3", "你率眾闖進倉庫，殺得水寇四散奔逃！", "銀兩 -10", "沈浪升到第 2 級！", "臂力 +1",
        "【江湖傳聞】測試俠客大破水寇！",
    ])
    assert changes == ["名望 +3", "銀兩 -10", "臂力 +1"]
    assert notes == ["你率眾闖進倉庫，殺得水寇四散奔逃！", "沈浪升到第 2 級！", "【江湖傳聞】測試俠客大破水寇！"]
    assert battlelog.split_changes([]) == ([], [])


def test_gains_text_lists_only_numeric_totals():
    assert battlelog.gains_text(record()) == "無"
    rec = record(exp=25, xinde=20, silver=15, changes=["名望 +3"])
    assert battlelog.gains_text(rec) == "經驗 +25（每人）　心得 +20　銀兩 +15　名望 +3"
    assert battlelog.gains_list(rec) == ["經驗 +25（每人）", "心得 +20", "銀兩 +15", "名望 +3"]
    assert battlelog.gains_list(record()) == []
    # notes（敘事文字）不算進獲得與損失
    assert battlelog.gains_text(record(notes=["你率眾闖進倉庫，殺得水寇四散奔逃！"])) == "無"


def test_story_text_joins_notes_but_hides_rumor_lines():
    assert battlelog.story_text(record()) == ""
    rec = record(notes=["你率眾闖進倉庫，殺得水寇四散奔逃！", "【江湖傳聞】測試俠客在太湖一帶大破水寇！"])
    assert battlelog.story_text(rec) == "你率眾闖進倉庫，殺得水寇四散奔逃！"


def test_card_text_omits_the_result_line_when_there_is_no_story():
    card = battlelog.card_text(record())
    assert "**結果**" not in card
    assert card == (
        "### ⚔ 湖邊・對陣 劫道山賊\n\n第2天 08:30　歷練\n\n**大勝**　我方威力 40　對手難度 5\n\n**獲得與損失**　無"
    )


def test_card_text_puts_story_before_gains_and_hides_rumor():
    rec = record(
        notes=["你率眾闖進倉庫，殺得水寇四散奔逃！", "【江湖傳聞】測試俠客在太湖一帶大破水寇！"],
        changes=["名望 +3"], exp=25, xinde=20, silver=15,
    )
    card = battlelog.card_text(rec)
    assert "**結果**　你率眾闖進倉庫，殺得水寇四散奔逃！" in card
    assert "【江湖傳聞】" not in card
    assert card.index("**結果**") < card.index("**獲得與損失**")


def test_detail_text_includes_the_lineup_and_battle_number():
    rec = record()
    detail = battlelog.detail_text(rec)
    assert detail.startswith("### ⚔ 湖邊・對陣 劫道山賊\n\n第2天 08:30　歷練　第 3 場")
    assert "**我方**　沈浪 Lv1" in detail
    assert "**大勝**　我方威力 40　對手難度 5" in detail


def test_detail_text_lists_multiple_teammates():
    rec = record(ours=[Fighter(name="沈浪", level=3), Fighter(name="韓鐵", level=2)])
    assert "**我方**　沈浪 Lv3、韓鐵 Lv2" in battlelog.detail_text(rec)
