"""見面情誼起步與冷淡、對話提示帶稱號（名聲設計 4.3、5.2）。"""
from conftest import real_content

from tianxia import companion_agent, renown
from tianxia.companion_agent import CompanionTurn
from tianxia.sqlite_world import open_world
from tianxia.state import new_game_state


def _cid(c, name):
    return next(cid for cid, ch in c.characters.items() if ch.name == name and ch.deep_interaction)


def _turn():
    return CompanionTurn(narrative="他點了點頭。", options=["一", "二", "三"], option_tags=["尋常寒暄"] * 3,
                         relationship_note_update="剛認識。")


def test_first_meet_gives_once_and_tops_up_after_a_new_tier():
    c = real_content("weekend")
    s = new_game_state(c, "甲")
    liubei = _cid(c, "劉備")
    s.player.stats.update({"fame": 50, "good": 15})
    lines = renown.first_meet(s, c, liubei)
    assert s.player.affinities[liubei] == 5 + 6
    assert lines == ["劉備早聽過你的名號。（情誼 +5）", "劉備早聽說你是一方豪俠。（情誼 +6）"]
    assert renown.first_meet(s, c, liubei) == []
    s.player.stats["good"] = 30  # 升到州郡大俠：補多出來的那一段
    assert renown.first_meet(s, c, liubei) == ["劉備早聽說你是州郡大俠。（情誼 +3）"]
    assert s.player.affinities[liubei] == 5 + 9


def test_fame_below_the_tier_is_not_recorded():
    c = real_content("weekend")
    s = new_game_state(c, "甲")
    lu = _cid(c, "盧植")
    s.player.stats["fame"] = 49
    assert renown.first_meet(s, c, lu) == []
    s.player.stats["fame"] = 50
    assert renown.first_meet(s, c, lu) == ["盧植早聽過你的名號。（情誼 +5）"]


def test_the_wrong_kind_of_person_gets_no_virtue_start():
    c = real_content("weekend")
    s = new_game_state(c, "甲")
    s.player.stats["good"] = 15
    assert renown.first_meet(s, c, _cid(c, "董卓")) == []  # 喜狠的人不理俠
    s.player.stats.update({"good": 0, "evil": 6})
    assert renown.first_meet(s, c, _cid(c, "董卓")) == ["董卓早聽說你是綠林好漢。（情誼 +3）"]
    assert renown.first_meet(s, c, _cid(c, "張角")) == []  # 不偏


def test_cold_trims_gains_only():
    c = real_content("weekend")
    s = new_game_state(c, "甲")
    s.player.stats.update({"evil": 6})
    luzhi = _cid(c, "盧植")
    assert renown.cold(s, c, luzhi, 8) == 6 and renown.cold(s, c, luzhi, 1) == 1 and renown.cold(s, c, luzhi, -3) == -3
    assert renown.cold(s, c, _cid(c, "董卓"), 8) == 8
    c.config.renown.affinity = False
    assert renown.cold(s, c, luzhi, 8) == 8 and renown.first_meet(s, c, luzhi) == []


def test_the_dialogue_starts_warmer_and_a_cold_turn_says_why():
    c = real_content("weekend")
    w = open_world()
    s = new_game_state(c, "甲")
    liubei, luzhi = _cid(c, "劉備"), _cid(c, "盧植")
    s.player.stats.update({"fame": 50, "good": 15})
    msgs = companion_agent.start_dialogue(None, s, c, w, liubei, None, turn=_turn())
    assert msgs[-2:] == ["劉備早聽過你的名號。（情誼 +5）", "劉備早聽說你是一方豪俠。（情誼 +6）"]
    s.player.stats.update({"good": 0, "evil": 6})
    s.player.last_offered_dialogue[luzhi] = [["表明來意"], ["雪中送炭"]]
    s.player.pending_companion = luzhi
    msgs = companion_agent.continue_dialogue(None, s, c, w, luzhi, 0, None, turn=_turn())
    assert "盧植聽過你的名聲，神色淡淡的。" in msgs


def test_the_prompt_carries_titles_and_the_regard():
    c = real_content("weekend")
    w = open_world()
    s = new_game_state(c, "甲")
    s.player.stats.update({"fame": 27, "good": 18})
    text = companion_agent.build_system_prompt(c.characters[_cid(c, "劉備")], s, c, w, _cid(c, "劉備"))
    assert "【玩家的名聲】江湖上稱他「名動一方」，人稱「一方豪俠」。" in text and "【劉備對這種人的看法】敬重行俠仗義的人" in text
    assert "27" not in text.split("【玩家的名聲】")[1].split("\n")[0]  # 只帶稱號，不帶數字
    s.player.stats.update({"good": 0, "evil": 7})
    text = companion_agent.build_system_prompt(c.characters[_cid(c, "盧植")], s, c, w, _cid(c, "盧植"))
    assert "【盧植對這種人的看法】看不起打家劫舍的人，對他冷淡" in text
    c.config.renown.prompt = False
    assert "【玩家的名聲】" not in companion_agent.build_system_prompt(c.characters[_cid(c, "盧植")], s, c, w, _cid(c, "盧植"))


def test_the_virtue_perks_name_the_welcome():
    c = real_content("weekend")
    assert "敬俠的人見面情誼 +6" in renown.virtue_perks(c, "俠", 2)
    assert renown.virtue_perks(c, "寇", 1)[-2:] == ["喜狠的人見面情誼 +3", "敬俠的人對你冷淡"]
