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


def test_grant_team_exp_also_reports_who_reached_which_level(state, content, world):
    """戰報要畫一行簡短的「升到第 N 級」（FB-074）：誰升到第幾級是結構化的資料，不從句子裡讀；句子照舊（下面是同一批）。"""
    state.player.team += ["mate", "scholar"]
    state.player.member.exp = 90
    world.update_companion("scholar", lambda progress: setattr(progress, "exp", 95))
    msgs, ups = team.grant_team_exp(state, content, world, 10)
    assert msgs == ["沈浪升到第 2 級！", "你有 1 點屬性可以分配（點名號展開）。", "書生升到第 2 級！"]
    assert (ups.you, ups.points, ups.mates, ups.lines) == (2, 1, [("書生", 2)], msgs)


def test_several_levels_in_one_fight_report_the_final_level_and_all_the_points(state, content, world):
    state.player.team.append("mate")
    world.update_companion("mate", lambda progress: setattr(progress, "exp", 0))
    state.player.stat_points = 2  # 之前還沒配的也算在「目前可配」裡（句子寫的也是總數）
    msgs, ups = team.grant_team_exp(state, content, world, 350)  # 夾具每級要 100×級：100、200 → 升兩級
    assert state.player.member.level == 3 and world.get_companion("mate").level == 3
    assert (ups.you, ups.points, ups.mates) == (3, 4, [("韓鐵", 3)])
    assert msgs.count("沈浪升到第 2 級！") == 1 and msgs.count("沈浪升到第 3 級！") == 1  # 句子還是一級一句


def test_no_levelups_means_none(state, content, world):
    assert team.grant_team_exp(state, content, world, 10) == ([], None)


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
