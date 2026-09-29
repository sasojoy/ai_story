from tianxia.battle import BattleEvent
from tianxia.battlelog import clock_text, gains_text, key_moments, list_label, moment_text, summary_line
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
    assert list_label(rec) == "勝　第2天 08:30　揚州城郊　vs 劫道山賊　4 回合"
    assert list_label(record(outcome="draw")).startswith("平　")
    assert list_label(record(outcome="lose")).startswith("敗　")


def test_gains_text():
    assert gains_text(record()) == "無"
    rec = record(exp=15, xinde=12, silver=10, notes=["臂力 +1"])
    assert gains_text(rec) == "經驗 +15（每人）　心得 +12　銀兩 +10　臂力 +1"
    assert gains_text(record(outcome="lose", silver=-5)) == "銀兩 -5"
