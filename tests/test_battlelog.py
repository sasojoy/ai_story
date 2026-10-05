import random

from tianxia import battlelog, rounds
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
        "### ⚔ 湖邊・對陣 劫道山賊\n\n第2天 08:30　遊歷\n\n**大勝**　我方威力 40　對手難度 5\n\n**得失**　無"
    )
    assert battlelog.detail_text(record()).endswith("\n\n**獲得與損失**　無")  # 戰報頁照舊兩個詞、各自一段


def test_card_text_puts_story_before_gains_and_hides_rumor():
    rec = record(
        notes=["你率眾闖進倉庫，殺得水寇四散奔逃！", "【江湖傳聞】測試俠客在太湖一帶大破水寇！"],
        changes=["名望 +3"], exp=25, xinde=20, silver=15,
    )
    card = battlelog.card_text(rec)
    assert "【江湖傳聞】" not in card
    assert card.endswith(
        "\n\n**結果**　你率眾闖進倉庫，殺得水寇四散奔逃！　**得失**　經驗 +25（每人）　心得 +20　銀兩 +15　名望 +3"
    )  # 結果與得失併成同一段：手機上少一段的間距
    assert "**獲得與損失**" not in card
    detail = battlelog.detail_text(rec)  # 戰報頁照舊：結果一段、獲得與損失一段
    assert "\n\n**結果**　你率眾闖進倉庫，殺得水寇四散奔逃！\n\n**獲得與損失**　經驗 +25（每人）　心得 +20　銀兩 +15　名望 +3" in detail


def test_detail_text_includes_the_lineup_and_battle_number():
    rec = record()
    detail = battlelog.detail_text(rec)
    assert detail.startswith("### ⚔ 湖邊・對陣 劫道山賊\n\n第2天 08:30　遊歷　第 3 場")
    assert "**我方**　沈浪 Lv1" in detail
    assert "**大勝**　我方威力 40　對手難度 5" in detail


def test_a_wild_fight_is_worded_as_a_wild_encounter_not_as_training():
    """探索撞上的野怪（kind="wild"）在卡片與詳情寫「探索遇敵」，遊歷仍寫「遊歷」（FB-023）。"""
    assert battlelog.KIND_WORDS["wild"] == "探索遇敵"
    wild = record(kind="wild")
    assert battlelog.card_text(wild).split("\n\n")[1] == "第2天 08:30　探索遇敵"
    assert "第2天 08:30　探索遇敵　第 3 場" in battlelog.detail_text(wild)
    assert "遊歷" not in battlelog.card_text(wild) and "遊歷" not in battlelog.detail_text(wild)
    assert battlelog.card_text(record(kind="train")).split("\n\n")[1] == "第2天 08:30　遊歷"


def test_every_kind_a_record_can_have_has_a_word():
    """BattleRecord.kind 新增一種值時，這裡會提醒：KIND_WORDS 少一個就是畫面上的 KeyError。"""
    from typing import get_args

    assert set(get_args(BattleRecord.model_fields["kind"].annotation)) == set(battlelog.KIND_WORDS)


def test_an_old_training_record_still_loads_and_reads_as_training():
    """FB-023 不遷移舊戰報：存檔裡 kind="train" 的紀錄照舊讀得進來、顯示「遊歷」。"""
    old = record(kind="train")
    loaded = BattleRecord.model_validate_json(old.model_dump_json())
    assert loaded.kind == "train" and "第2天 08:30　遊歷" in battlelog.detail_text(loaded)
    assert BattleRecord.model_validate_json(record(kind="event").model_dump_json()).kind == "event"
    assert BattleRecord.model_validate_json(record(kind="wild").model_dump_json()).kind == "wild"


def showdown(**kw):
    """參戰者手上的全服決戰戰報（FB-027）：沒有我方威力與對手難度，有站哪一邊、結果的敘事與大勢的增減。"""
    base = dict(
        kind="showdown", location="潁汝", event="黃巾決戰", opponent="黃巾軍", ours=[], tier="官軍大勝",
        our_power=0.0, difficulty=0.0, side="官軍", notes=["官軍士氣如虹。", "你出手 3 回合"], changes=["黃巾聲勢 -35"],
    )
    return record(**(base | kw))


def test_a_showdown_report_shows_the_side_and_the_trends_instead_of_power_and_difficulty():
    rec = showdown()
    card = battlelog.card_text(rec)
    assert card == (
        "### ⚔ 潁汝・對陣 黃巾軍\n\n第2天 08:30　決戰：黃巾決戰\n\n**官軍大勝**　你站在官軍\n\n"
        "**結果**　官軍士氣如虹。　你出手 3 回合　**大勢**　黃巾聲勢 -35"
    )
    detail = battlelog.detail_text(rec)
    assert detail == (
        "### ⚔ 潁汝・對陣 黃巾軍\n\n第2天 08:30　決戰：黃巾決戰　第 3 場\n\n**官軍大勝**　你站在官軍\n\n"
        "**結果**　官軍士氣如虹。　你出手 3 回合\n\n**大勢**　黃巾聲勢 -35"
    )
    for text in (card, detail):
        assert "威力" not in text and "難度" not in text and "**我方**" not in text and "獲得與損失" not in text
    assert battlelog.list_label(rec) == "官軍大勝　第3場　第2天 08:30　潁汝　vs 黃巾軍"
    assert battlelog.outcome_text(rec) == "官軍大勝" and battlelog.summary_line(rec) == "⚔ 潁汝：官軍大勝"


def test_a_showdown_without_trend_changes_has_no_trend_line():
    """上一季打的那一場，大勢的增減寫在敘事裡（標了第幾季），不另起一行「大勢」。"""
    rec = showdown(location="第 1 季・潁汝", notes=["官軍士氣如虹。", "（第 1 季）黃巾聲勢 -35"], changes=[])
    for text in (battlelog.card_text(rec), battlelog.detail_text(rec)):
        assert "**大勢**" not in text and "**結果**　官軍士氣如虹。　（第 1 季）黃巾聲勢 -35" in text
        assert text.startswith("### ⚔ 第 1 季・潁汝・對陣 黃巾軍")


def test_a_showdown_report_saved_before_the_side_field_still_loads():
    old = record().model_dump()
    old.pop("side")
    assert BattleRecord.model_validate(old).side == ""


def test_detail_text_lists_multiple_teammates():
    rec = record(ours=[Fighter(name="沈浪", level=3), Fighter(name="韓鐵", level=2)])
    assert "**我方**　沈浪 Lv3、韓鐵 Lv2" in battlelog.detail_text(rec)



def test_report_list_and_detail_take_the_calendar_stamp():
    """戰報的列表與詳情用呼叫端給的時間寫法（第一季是季曆）；不給時照舊「第N天 HH:MM」。"""
    from tianxia.state import BattleRecord, Fighter

    record = BattleRecord(id=3, time=3900, location="湖邊", kind="train", opponent="水寇", ours=[Fighter(name="沈浪", level=1)],
                          tier="大勝", our_power=50, difficulty=10)
    assert "第1天 01:05" in battlelog.list_label(record) and "第1天 01:05" in battlelog.detail_text(record)
    stamp = lambda t: "第 1 週・週一 01:05"  # noqa: E731
    assert battlelog.list_label(record, stamp) == "大勝　第3場　第 1 週・週一 01:05　湖邊　vs 水寇"
    assert "第 1 週・週一 01:05　遊歷" in battlelog.detail_text(record, stamp)


# ── 回合演出（武學與成長設計 8.2、計畫三 Task 1）──────────────────────


def test_round_lines_never_print_a_missing_art(content):
    played = rounds.play(
        "落敗", [rounds.Fighter(name="沈浪", art=None, attribute=None)],
        rounds.Foe(name="山賊", attribute=None, agility=9.0), our_agility=5.0, hp_lost=30, rng=random.Random(0),
    )
    lines = battlelog.round_lines(content, played, random.Random(0))
    assert lines[0].startswith("第1回合") and all("None" not in line and "【】" not in line for line in lines)


def test_round_lines_name_the_art_and_write_the_numbers_that_were_played(content):
    """我方：「沈浪以【旋風腿】……，對手氣勢 -N」；對手：「山賊……，你氣血 -N」；沒打中的寫「被對方架開」「被你閃開了」。
    句型照出手那門武學（或對手）的屬性挑。"""
    played = [
        rounds.Round(number=1, beats=[
            rounds.Beat(side="theirs", actor="山賊", art=None, attribute="剛", amount=24),
            rounds.Beat(side="ours", actor="沈浪", art="旋風腿", attribute="快", amount=0),
        ]),
        rounds.Round(number=2, beats=[
            rounds.Beat(side="theirs", actor="山賊", art=None, attribute="剛", amount=0),
            rounds.Beat(side="ours", actor="沈浪", art="旋風腿", attribute="快", amount=18),
        ]),
    ]
    first, second = battlelog.round_lines(content, played, random.Random(0))
    theirs = content.combat_lines.theirs["剛"]
    ours = content.combat_lines.ours["快"]
    assert first.startswith("第1回合　山賊") and "，你氣血 -24；沈浪以【旋風腿】" in first and first.endswith("，被對方架開。")
    assert any(f"山賊{how}，你氣血 -24" in first for how in theirs)
    assert any(f"沈浪以【旋風腿】{how}，被對方架開" in first for how in ours)
    assert second.startswith("第2回合　山賊") and "，被你閃開了；" in second and second.endswith("，對手氣勢 -18。")


def test_round_lines_leave_a_blow_with_no_amount_without_a_tail(content):
    """不扣氣血的仗（劇情戰，G5）：對手的出手只寫怎麼出手，不寫「你氣血 -N」也不寫「被你閃開了」——
    落敗的劇情戰寫「被你閃開了」等於說對方從頭到尾沒碰到你、你卻輸了。"""
    played = rounds.play(
        "落敗", [rounds.Fighter(name="沈浪", art="旋風腿", attribute="快")],
        rounds.Foe(name="翻江龍", attribute="剛", agility=15.0), our_agility=5.0, hp_lost=None, rng=random.Random(0),
    )
    lines = battlelog.round_lines(content, played, random.Random(0))
    assert lines and all("你氣血" not in line and "被你閃開了" not in line for line in lines)
    assert all(line.startswith(f"第{i}回合　翻江龍") for i, line in enumerate(lines, 1))  # 對手身法高，先出手
    assert all(any(f"翻江龍{how}；" in line for how in content.combat_lines.theirs["剛"]) for line in lines)


def test_a_foe_with_no_attribute_and_a_bare_fighter_use_the_fallback_lines(content):
    played = rounds.play(
        "大勝", [rounds.Fighter(name="沈浪", art=None, attribute=None)],
        rounds.Foe(name="山賊", attribute=None, agility=1.0), our_agility=5.0, hp_lost=9, rng=random.Random(0),
    )
    for line in battlelog.round_lines(content, played, random.Random(0)):
        assert any(f"沈浪{how}，" in line for how in content.combat_lines.bare)
        assert any(f"山賊{how}，" in line for how in content.combat_lines.theirs_any)


def test_the_card_and_the_report_show_the_rounds_after_the_result_line():
    rec = record(rounds=["第1回合　甲。", "第2回合　乙。"], notes=["你贏了。"])
    for text, gains in ((battlelog.card_text(rec), "**得失**"), (battlelog.detail_text(rec), "**獲得與損失**")):
        assert "**過程**\n- 第1回合　甲。\n- 第2回合　乙。" in text
        assert text.index("對手難度") < text.index("**過程**") < text.index("**結果**") < text.index(gains)


def test_an_old_record_without_rounds_loads_and_shows_no_rounds():
    old = record().model_dump()
    old.pop("rounds")
    loaded = BattleRecord.model_validate(old)
    assert loaded.rounds == []
    assert "**過程**" not in battlelog.card_text(loaded) and "**過程**" not in battlelog.detail_text(loaded)
