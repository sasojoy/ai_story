from tianxia.battle import BattleEvent
from tianxia.battlelog import (
    card_text,
    clock_text,
    detail_text,
    gains_text,
    key_moments,
    list_label,
    moment_text,
    split_changes,
    story_text,
    summary_line,
)
from tianxia.state import BattleRecord, Fighter


def ult(rnd, actor="韓鐵", art="驚濤掌"):
    return BattleEvent(rnd, "ultimate", actor, 0, art=art)


def ctrl(rnd, control="封脈"):
    return BattleEvent(rnd, "control", "小墨", 0, target="劫道山賊", art="亂針", control=control)


def ko(rnd, actor, target, side=0, leader=False):
    return BattleEvent(rnd, "knockout", actor, side, target=target, is_leader=leader)


def record(**kw):
    base = dict(
        id=3, time=86400 + 8 * 3600 + 30 * 60, location="揚州城郊", kind="train", opponent="劫道山賊",
        ours=[Fighter(name="沈浪", level=1)], theirs=[Fighter(name="劫道山賊", level=3)],
        outcome="win", rounds=4, ending="劫道山賊倒下，敵方敗退。", leader_ok=True,
    )
    return BattleRecord(**(base | kw))


def test_moment_sentences():
    assert moment_text(ctrl(4)) == "第4回合　小墨【亂針】封住劫道山賊的經脈"
    assert moment_text(ctrl(1, "點穴")) == "第1回合　小墨【亂針】點住劫道山賊的穴道"
    assert moment_text(ctrl(1, "卸兵")) == "第1回合　小墨【亂針】卸下劫道山賊的兵刃"
    assert moment_text(ctrl(0)) == "開戰前　小墨【亂針】封住劫道山賊的經脈"  # 心法在第一回合之前
    assert moment_text(ult(2)) == "第2回合　韓鐵施展【驚濤掌】"
    assert moment_text(ko(5, "沈浪", "劫道山賊", leader=True)) == "第5回合　沈浪擊倒敵方隊長劫道山賊"
    assert moment_text(ko(3, "翻江龍", "韓鐵", side=1)) == "第3回合　翻江龍擊倒韓鐵"
    assert moment_text(ko(6, "翻江龍", "沈浪", side=1, leader=True)) == "第6回合　翻江龍擊倒我方隊長沈浪"


def test_key_moments_take_one_of_each_kind_first_then_list_by_time():
    events = [
        ko(1, "沈浪", "地痞無賴"), ult(2), ult(3, "沈浪", "家傳劍法"), ctrl(3),
        ko(4, "韓鐵", "劫道山賊", leader=True),
    ]
    assert key_moments(events) == [
        "第2回合　韓鐵施展【驚濤掌】",
        "第3回合　小墨【亂針】封住劫道山賊的經脈",
        "第4回合　韓鐵擊倒敵方隊長劫道山賊",  # 倒下的以隊長優先
    ]


def test_key_moments_fill_up_in_the_order_ultimate_control_knockout():
    events = [ult(1), ko(2, "韓鐵", "地痞無賴"), ult(3, "沈浪", "家傳劍法"), ko(4, "沈浪", "劫道山賊", leader=True)]
    # 沒有控制：第一輪挑到絕招與隊長倒下，第二輪先補絕招，就滿三則了
    assert key_moments(events) == [
        "第1回合　韓鐵施展【驚濤掌】",
        "第3回合　沈浪施展【家傳劍法】",
        "第4回合　沈浪擊倒敵方隊長劫道山賊",
    ]


def test_key_moments_are_at_most_three():
    assert len(key_moments([ult(r) for r in range(1, 9)])) == 3
    assert key_moments([]) == []


def test_record_texts():
    rec = record()
    assert clock_text(rec.time) == "第2天 08:30"
    assert summary_line(rec) == "⚔ 揚州城郊：擊退劫道山賊（4 回合）"
    assert summary_line(record(outcome="lose")) == "⚔ 揚州城郊：不敵劫道山賊，敗退（4 回合）"
    assert summary_line(record(outcome="draw")) == "⚔ 揚州城郊：與劫道山賊不分勝負（4 回合）"
    assert list_label(rec) == "勝　第3場　第2天 08:30　揚州城郊　vs 劫道山賊　4 回合"
    assert list_label(record(outcome="draw")).startswith("平　第3場　")
    assert list_label(record(outcome="lose")).startswith("敗　第3場　")


def test_theirs_line_omits_the_squad_name_when_it_equals_the_leaders_name():
    # record() 預設對手「劫道山賊」與唯一成員同名：不重複寫隊名。
    detail = detail_text(record())
    assert "**對方**　劫道山賊 Lv3" in detail
    assert "劫道山賊：劫道山賊" not in detail
    # 隊名不同於隊長時，照常寫「隊名：陣容」。
    named = detail_text(record(opponent="水寇小隊", theirs=[Fighter(name="小嘍囉", level=1)]))
    assert "**對方**　水寇小隊：小嘍囉 Lv1" in named


def test_split_changes_separates_numeric_deltas_from_narrative():
    """engine 用這個把 apply_effect／訓練加成的訊息分成數值變化（changes）與敘事文字（notes）。"""
    changes, notes = split_changes([
        "名望 +3", "你率眾闖進倉庫，殺得水寇四散奔逃！", "銀兩 -10", "沈浪升到第 2 級！", "臂力 +1",
        "【江湖傳聞】測試俠客大破水寇！",
    ])
    assert changes == ["名望 +3", "銀兩 -10", "臂力 +1"]
    assert notes == ["你率眾闖進倉庫，殺得水寇四散奔逃！", "沈浪升到第 2 級！", "【江湖傳聞】測試俠客大破水寇！"]
    assert split_changes([]) == ([], [])


def test_gains_text():
    """獲得與損失只列數值：經驗／心得／銀兩三個專屬欄位，加上 changes 裡的其他數值變化。"""
    assert gains_text(record()) == "無"
    rec = record(exp=15, xinde=12, silver=10, changes=["臂力 +1"])
    assert gains_text(rec) == "經驗 +15（每人）　心得 +12　銀兩 +10　臂力 +1"
    assert gains_text(record(outcome="lose", silver=-5)) == "銀兩 -5"
    # notes（敘事文字）不算進獲得與損失，即使裡面有東西。
    assert gains_text(record(notes=["你率眾闖進倉庫，殺得水寇四散奔逃！"])) == "無"


def test_story_text_joins_notes_but_hides_rumor_lines():
    assert story_text(record()) == ""
    rec = record(notes=["你率眾闖進倉庫，殺得水寇四散奔逃！", "【江湖傳聞】測試俠客在太湖一帶大破水寇！"])
    assert story_text(rec) == "你率眾闖進倉庫，殺得水寇四散奔逃！"


def test_card_text_puts_story_before_gains_and_hides_rumor():
    rec = record(
        notes=["你率眾闖進倉庫，殺得水寇四散奔逃！", "【江湖傳聞】測試俠客在太湖一帶大破水寇！"],
        changes=["名望 +3", "善名 +2"], exp=25, xinde=20, silver=15,
    )
    card = card_text(rec)
    assert "**結果**　你率眾闖進倉庫，殺得水寇四散奔逃！" in card
    assert "【江湖傳聞】" not in card
    assert "**獲得與損失**　經驗 +25（每人）　心得 +20　銀兩 +15　名望 +3　善名 +2" in card
    assert card.index("**結果**") < card.index("**獲得與損失**")


def test_card_text_omits_the_result_line_when_there_is_no_story():
    assert "**結果**" not in card_text(record())


def test_detail_text_puts_story_before_gains_and_hides_rumor():
    rec = record(
        notes=["你率眾闖進倉庫，殺得水寇四散奔逃！", "【江湖傳聞】測試俠客在太湖一帶大破水寇！"],
        changes=["名望 +3"], exp=25,
    )
    detail = detail_text(rec)
    assert "**結果**　你率眾闖進倉庫，殺得水寇四散奔逃！" in detail
    assert "【江湖傳聞】" not in detail
    assert detail.index("**結果**") < detail.index("**獲得與損失**")


def test_detail_text_groups_the_round_by_round_report_under_headings():
    """逐回合戰報依回合分組：每回合一個 #### 標題，底下是這回合的行（列點）；
    回合線之前的心法歸在「開戰前」。文字本身（來自 battle.py）不變，只是排版分組。"""
    rec = record(report=[
        "【心法】小墨運起吐納法。",
        "── 第1回合 ──",
        "沈浪對劫道山賊使出一記重拳，造成 5 點傷害。",
        "韓鐵對劫道山賊使出一記重拳，造成 4 點傷害。",
        "── 第2回合 ──",
        "小墨對劫道山賊使出【亂針】，命中！",
        "劫道山賊倒下，敵方敗退。",
    ])
    detail = detail_text(rec)
    assert "#### 開戰前\n- 【心法】小墨運起吐納法。" in detail
    assert (
        "#### 第1回合\n"
        "- 沈浪對劫道山賊使出一記重拳，造成 5 點傷害。\n"
        "- 韓鐵對劫道山賊使出一記重拳，造成 4 點傷害。"
    ) in detail
    assert (
        "#### 第2回合\n"
        "- 小墨對劫道山賊使出【亂針】，命中！\n"
        "- 劫道山賊倒下，敵方敗退。"
    ) in detail
    assert detail.index("#### 開戰前") < detail.index("#### 第1回合") < detail.index("#### 第2回合")
    assert "── 第1回合 ──" not in detail  # 原本的回合線換成標題，不重複


def test_detail_text_omits_the_pre_battle_heading_when_there_is_no_心法():
    rec = record(report=["── 第1回合 ──", "沈浪對劫道山賊使出一記重拳，造成 5 點傷害。"])
    detail = detail_text(rec)
    assert "#### 開戰前" not in detail
    assert "#### 第1回合\n- 沈浪對劫道山賊使出一記重拳，造成 5 點傷害。" in detail
