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
    assert card == (  # 標題、時間類型、結果三行同一塊（單換行）：手機上只佔一塊的間距
        "### ⚔ 湖邊・對陣 劫道山賊\n第2天 08:30　遊歷\n**大勝**　我方威力 40　對手難度 5\n\n**得失**　無"
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


# ── 升級那一行（FB-074）：卡片上收成一行，戰報頁照舊寫完整的句子 ─────────────────


def _ups(**kw):
    from tianxia.state import LevelUps

    return LevelUps(**kw)


def test_the_levelup_line_collapses_levels_and_groups_companions_by_level():
    line = battlelog.levelup_line
    assert line(_ups(you=5, points=4)) == "升到第 5 級（可配 4 點）"  # 本人：最後的等級加上現在還沒配的點數
    assert line(_ups(you=5, points=0)) == "升到第 5 級"  # 配完了就不寫「可配 0 點」
    assert line(_ups(mates=[("關羽", 4), ("張飛", 4), ("劉備", 4)])) == "關羽、張飛、劉備升到第 4 級"  # 同一級的併在一起
    assert line(_ups(mates=[("關羽", 4), ("張飛", 3)])) == "關羽升到第 4 級、張飛升到第 3 級"  # 不同級的各寫各的
    assert line(_ups(mates=[("關羽", 4), ("張飛", 3), ("劉備", 4)])) == "關羽、劉備升到第 4 級、張飛升到第 3 級"  # 照第一次出現的順序分組
    assert line(_ups(you=11, points=3, mates=[("關羽", 4), ("張飛", 4), ("劉備", 4)])) == "升到第 11 級（可配 3 點）・關羽、張飛、劉備升到第 4 級"
    assert line(_ups(you=11, points=3), points=1) == "升到第 11 級（可配 1 點）"  # 畫的那一刻照現在的點數（狀態列寫幾點就是幾點）


def test_the_card_shows_one_levelup_line_and_the_report_keeps_the_sentences():
    lines = ["沈浪升到第 10 級！", "沈浪升到第 11 級！", "你有 3 點屬性可以分配（點名號展開）。", "關羽升到第 4 級！", "張飛升到第 4 級！"]
    rec = record(
        notes=["你率眾闖進倉庫。", *lines, "【江湖傳聞】測試俠客大破水寇！"], exp=25,
        levelups=_ups(you=11, points=3, mates=[("關羽", 4), ("張飛", 4)], lines=lines),
    )
    card = battlelog.card_text(rec)
    assert card.endswith("\n\n**結果**　你率眾闖進倉庫。　升到第 11 級（可配 3 點）・關羽、張飛升到第 4 級　**得失**　經驗 +25（每人）")
    assert "升到第 10 級" not in card and "！" not in card and "屬性可以分配" not in card and "【江湖傳聞】" not in card
    detail = battlelog.detail_text(rec)  # 戰報頁：完整的句子照舊（它們也還在江湖紀錄裡）
    assert "**結果**　你率眾闖進倉庫。　沈浪升到第 10 級！　沈浪升到第 11 級！　你有 3 點屬性可以分配（點名號展開）。　關羽升到第 4 級！" in detail
    assert battlelog.told_lines(rec)[1:6] == lines  # 卡片底下的補充不重複這些句子（它們算講過了）
    assert "升到第 11 級（可配 1 點）" in battlelog.card_text(rec, points=1)


def test_a_record_without_levelups_reads_exactly_as_before():
    """沒有升級、或舊戰報（沒有 levelups 欄位）：卡片還是照 notes 原文，一個字不動。"""
    rec = record(notes=["沈浪升到第 2 級！", "你有 1 點屬性可以分配（點名號展開）。"])
    assert rec.levelups is None
    assert "**結果**　沈浪升到第 2 級！　你有 1 點屬性可以分配（點名號展開）。" in battlelog.card_text(rec)
    loaded = BattleRecord.model_validate_json(rec.model_dump_json())
    assert loaded == rec
    old = rec.model_dump()
    old.pop("levelups")
    assert BattleRecord.model_validate(old).levelups is None
    with_ups = record(notes=["沈浪升到第 2 級！"], levelups=_ups(you=2, points=1, lines=["沈浪升到第 2 級！"]))
    assert BattleRecord.model_validate_json(with_ups.model_dump_json()) == with_ups


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
    assert battlelog.card_text(wild).split("\n")[1] == "第2天 08:30　探索遇敵"  # 卡片：標題底下那一行
    assert "第2天 08:30　探索遇敵　第 3 場" in battlelog.detail_text(wild)
    assert "遊歷" not in battlelog.card_text(wild) and "遊歷" not in battlelog.detail_text(wild)
    assert battlelog.card_text(record(kind="train")).split("\n")[1] == "第2天 08:30　遊歷"


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
        "### ⚔ 潁汝・對陣 黃巾軍\n第2天 08:30　決戰：黃巾決戰\n**官軍大勝**　你站在官軍\n\n"
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


def test_a_dodged_loss_says_so_on_the_battle_card(state, content, world):
    from tianxia.encounter import EncounterResult

    result = EncounterResult(tier="僵持", margin=-50.0, our_power=1.0, difficulty=60.0, dodged=True)
    record = battlelog.new_record(state, content, world, content.squads["thug"], result, "train")
    assert record.tier == "僵持" and record.notes == [battlelog.DODGE_NOTE]
    plain = result.model_copy(update={"dodged": False})
    assert battlelog.new_record(state, content, world, content.squads["thug"], plain, "train").notes == []


# ── 武學的功效的演出句（武學與成長設計 13.6；計畫六 Task 4）──────────────


def test_a_trait_line_fills_the_three_placeholders(content):
    line = battlelog.trait_line(content, "先手", "沈浪", "穿林腿", "黃巾散兵", random.Random(0))
    assert line.startswith("〔先手〕") and "沈浪" in line and "{" not in line


def test_every_real_trait_line_fills_in_for_a_person_or_a_crowd(content):
    """S1 的 45 句：{foe} 可能是一個人（波才），也可能是一群人（黃巾散兵）；{who}、{art} 都換得出來、不留括號。"""
    for name, lines in content.trait_lines.items():
        for index in range(len(lines)):
            rng = random.Random(0)
            rng.choice = lambda pool, index=index: pool[index]  # noqa: B023  逐句挑
            for foe in ("波才", "黃巾散兵"):
                line = battlelog.trait_line(content, name, "沈浪", "穿林腿", foe, rng)
                assert line.startswith(f"〔{name}〕") and "{" not in line and "}" not in line and "None" not in line


def test_a_trait_line_picks_by_the_given_rng_and_falls_back_when_the_content_has_no_lines(content):
    a = [battlelog.trait_line(content, "先手", "沈浪", "穿林腿", "山賊", random.Random(seed)) for seed in range(30)]
    assert len(set(a)) > 1  # 三句裡不是永遠同一句
    assert battlelog.trait_line(content, "先手", "沈浪", "穿林腿", "山賊", random.Random(7)) == battlelog.trait_line(
        content, "先手", "沈浪", "穿林腿", "山賊", random.Random(7),
    )  # 同一個種子同一句
    content.trait_lines.clear()
    assert battlelog.trait_line(content, "先手", "沈浪", "穿林腿", "山賊", random.Random(0)) == "〔先手〕沈浪的【穿林腿】起了作用。"


def test_the_bottom_line_of_thick_is_only_for_a_player_at_the_bottom(content):
    """Task 4 審查 M3：厚有一句「氣血見底」（暗號在 LOW_HP_MARKS）：氣血不低（low_hp=False）時挑不到它，低時三句都挑得到。"""
    content.trait_lines["厚"] = ["帶傷，{who}撐著。", "氣血見底，{who}硬撐。"]
    pick = lambda low, seed: battlelog.trait_line(content, "厚", "沈浪", "拳", "山賊", random.Random(seed), low_hp=low)  # noqa: E731
    assert {pick(False, seed) for seed in range(40)} == {"〔厚〕帶傷，沈浪撐著。"}
    assert {pick(True, seed) for seed in range(40)} == {"〔厚〕帶傷，沈浪撐著。", "〔厚〕氣血見底，沈浪硬撐。"}
    assert battlelog.trait_line(content, "厚", "沈浪", "拳", "山賊", random.Random(1)) in {pick(True, seed) for seed in range(40)}  # 預設是低


def test_a_trait_without_a_bottom_line_ignores_the_flag_and_a_lone_bottom_line_falls_back(content):
    rng = lambda seed: random.Random(seed)  # noqa: E731
    assert {battlelog.trait_line(content, "先手", "沈浪", "拳", "山賊", rng(s), low_hp=False) for s in range(40)} == {
        battlelog.trait_line(content, "先手", "沈浪", "拳", "山賊", rng(s)) for s in range(40)
    }  # 先手沒有見底那一句：旗標不影響
    content.trait_lines["厚"] = ["氣血見底，{who}硬撐。"]
    assert battlelog.trait_line(content, "厚", "沈浪", "拳", "山賊", rng(0), low_hp=False) == "〔厚〕沈浪的【拳】起了作用。"


def test_trait_lines_wrap_the_rounds_in_the_report():
    record = BattleRecord(id=1, time=0, location="郊野", kind="train", opponent="山賊", tier="險勝",
                          our_power=50, difficulty=40, ours=[], rounds=["第1回合　……"],
                          trait_before=["〔先手〕甲"], trait_after=["〔乘勝〕乙"])
    block = battlelog._rounds_block(record)[0]
    assert block.index("〔先手〕") < block.index("第1回合") < block.index("〔乘勝〕")
    assert block == "**過程**\n- 〔先手〕甲\n- 第1回合　……\n- 〔乘勝〕乙"


def test_trait_lines_wrap_the_models_story_of_a_big_fight_too():
    """大場面模型寫的那一段（一段話）也一樣：功效的句子在前與後，各佔一行，整段仍是「過程」那一塊。"""
    rec = record(rounds=["第1回合　……"], narration="波才刀勢沉猛，你左支右絀。", trait_before=["〔險〕甲"], trait_after=["〔護命〕乙"])
    assert battlelog._rounds_block(rec) == ["**過程**\n〔險〕甲\n波才刀勢沉猛，你左支右絀。\n〔護命〕乙"]


def test_a_record_without_trait_lines_renders_exactly_as_before():
    rec = record(rounds=["第1回合　甲。", "第2回合　乙。"], notes=["你贏了。"])
    assert rec.trait_before == [] and rec.trait_after == [] and rec.guarded is False
    assert battlelog._rounds_block(rec) == ["**過程**\n- 第1回合　甲。\n- 第2回合　乙。"]
    assert battlelog._rounds_block(record(rounds=[])) == []


def test_trait_lines_alone_still_make_a_process_block():
    """沒有回合（舊戰報補了功效句、或決戰）卻有功效的句子時，句子照樣放進「過程」。"""
    assert battlelog._rounds_block(record(rounds=[], trait_after=["〔乘勝〕乙"])) == ["**過程**\n- 〔乘勝〕乙"]


def test_the_card_and_the_report_both_show_the_trait_lines():
    rec = record(rounds=["第1回合　甲。"], trait_before=["〔先手〕甲"], trait_after=["〔乘勝〕乙"], notes=["你贏了。"])
    for text in (battlelog.card_text(rec), battlelog.detail_text(rec)):
        assert text.index("對手難度") < text.index("〔先手〕") < text.index("第1回合") < text.index("〔乘勝〕") < text.index("**結果**")


def test_an_old_record_without_the_trait_fields_loads():
    old = record().model_dump()
    for key in ("guarded", "trait_before", "trait_after"):
        old.pop(key)
    loaded = BattleRecord.model_validate(old)
    assert loaded.guarded is False and loaded.trait_before == [] and loaded.trait_after == []


def test_new_record_remembers_a_guarded_draw(state, content, world):
    from tianxia.encounter import EncounterResult

    result = EncounterResult(tier="僵持", margin=-50.0, our_power=1.0, difficulty=60.0, guarded=True)
    record = battlelog.new_record(state, content, world, content.squads["thug"], result, "train")
    assert record.guarded is True and record.tier == "僵持"
    plain = result.model_copy(update={"guarded": False})
    assert battlelog.new_record(state, content, world, content.squads["thug"], plain, "train").guarded is False
