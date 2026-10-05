"""同伴也拿經驗、照同一套規則升級（試玩回饋 FB-002）。

戰報與江湖紀錄一直寫「經驗 +N（每人）」，但以前只有本人真的拿到。同伴的進度存在全服共用的
CompanionProgress（world_state.py），所以這裡驗的是共用世界裡的那一份；等級照氣血設計 A1 只抬高
氣血上限（300 + 20 × 等級）。
"""
from tianxia import team


def test_everyone_on_the_team_gains_the_same_exp(state, content, world):
    state.player.team += ["mate", "scholar"]
    team.add_team_exp(state, content, world, 30)
    assert state.player.member.exp == 30
    assert world.get_companion("mate").exp == 30
    assert world.get_companion("scholar").exp == 30
    assert world.get_companion("pupil").exp == 0  # 沒帶出戰的不分


def test_companions_level_up_by_the_same_rules_and_say_so(state, content, world):
    state.player.team.append("mate")
    world.update_companion("mate", lambda progress: setattr(progress, "exp", 90))
    msgs = team.add_team_exp(state, content, world, 20)
    mate = world.get_companion("mate")
    assert (mate.level, mate.exp) == (2, 10)  # 夾具 level_exp 100：第 1 級升第 2 級要 100
    assert msgs == ["韓鐵升到第 2 級！"]


def test_level_messages_come_in_team_order(state, content, world):
    state.player.team += ["mate", "scholar"]
    state.player.member.exp = 90
    world.update_companion("scholar", lambda progress: setattr(progress, "exp", 95))
    assert team.add_team_exp(state, content, world, 10) == [
        "沈浪升到第 2 級！", "你有 1 點屬性可以分配（點名號展開）。", "書生升到第 2 級！",  # 本人的升級與配點提示在前，同伴在後
    ]


def test_a_companions_blood_cap_grows_with_the_level(state, content, world):
    state.player.team.append("mate")
    world.update_companion("mate", lambda progress: setattr(progress, "neili", 150.0))
    _, before = team.member_neili(content, world.get_companion("mate"))
    team.add_team_exp(state, content, world, 100)
    now, after = team.member_neili(content, world.get_companion("mate"))
    cfg = content.config
    assert before == cfg.neili_base + cfg.neili_per_level  # 第 1 級
    assert after == cfg.neili_base + 2 * cfg.neili_per_level  # 第 2 級：上限跟著升
    assert now == 150.0  # 升級只抬高上限，不順便回血


def test_nobody_gains_past_the_max_level(state, content, world):
    state.player.team.append("mate")
    world.update_companion("mate", lambda progress: setattr(progress, "level", content.config.max_level))
    assert team.add_team_exp(state, content, world, 50) == []
    assert world.get_companion("mate").exp == 0
    assert state.player.member.exp == 50
