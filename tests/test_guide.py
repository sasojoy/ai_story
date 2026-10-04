from tianxia.guide import next_hint, note_action, quest_text, tutorial_active, tutorial_intro
from tianxia.state import Journey


def test_intro_is_first_step(content):
    assert tutorial_intro(content) == ["【說書人】先探索一下。"]


def test_matching_action_completes_step_and_rewards(state, content, world):
    msgs = note_action(state, content, world, "explore")
    assert state.player.tutorial_step == 1
    assert state.player.stats["silver"] == 55
    assert msgs[0] == "✔ 引導完成"
    assert msgs[-1] == "【說書人】去湖邊。"


def test_wrong_action_or_place_does_nothing(state, content, world):
    assert note_action(state, content, world, "train") == []
    note_action(state, content, world, "explore")
    assert note_action(state, content, world, "move") == []  # 還在小鎮，不是湖邊
    state.player.location = "lake"
    note_action(state, content, world, "move")
    assert state.player.tutorial_step == 2


def test_outro_after_last_step(state, content, world):
    state.player.tutorial_step = 2
    state.player.flags.add("看過地圖")  # s3 現在是地圖旗標條件，模擬 Game.view_map() 先設旗標
    msgs = note_action(state, content, world, "view_map")
    assert not tutorial_active(state, content)
    assert msgs[-1] == "【說書人】去闖吧。"
    assert note_action(state, content, world, "view_map") == []


def test_quest_text_shows_storyline_endings_and_milestones(state, content):
    text = quest_text(state, content)
    assert "寇亂" in text and "水寇橫行" in text and "壓制寇亂" in text
    assert "水寇稱霸：寇亂達 80" in text
    assert "寶藏被奪" not in text  # 屬於尚未出現的寶藏主線
    assert "☐ 拜入門派" in text
    state.player.sect = "cloud"
    assert "☑ 拜入門派" in quest_text(state, content)


def test_next_hint_follows_tutorial_then_act_goal(state, content):
    assert "先探索一下" in next_hint(state, content)
    state.player.tutorial_step = 3
    state.player.stamina = 50
    assert next_hint(state, content) == "壓制寇亂"
    state.player.stamina = 150
    assert "體力將滿" in next_hint(state, content)


def test_next_hint_hides_stamina_reminder_when_not_idle(state, content):
    state.player.tutorial_step = 3
    state.player.stamina = 150
    state.pending_event = "drunk"
    assert "體力將滿" not in next_hint(state, content)
    state.pending_event = None
    state.world.ended = True
    assert "體力將滿" not in next_hint(state, content)
    state.world.ended = False
    state.player.resting_since = 0.0
    assert "體力將滿" not in next_hint(state, content)
    state.player.resting_since = None
    state.player.journey = Journey(mode="walk", path=["lake"], arrive_at=[180.0])
    assert "體力將滿" not in next_hint(state, content)


def test_quest_text_after_season_end(state, content):
    state.world.ended = True
    state.world.ending_title = "風雨飄搖"
    state.world.ending_text = "江南依舊動盪。"
    assert quest_text(state, content).startswith("### 賽季落幕：風雨飄搖")


def test_flag_set_early_completes_later_step_in_same_call(state, content, world):
    """s3（看地圖）的旗標若提早成立，完成 s2 的當下應該連帶完成 s3。"""
    state.player.flags.add("看過地圖")
    note_action(state, content, world, "explore")
    assert state.player.tutorial_step == 1
    state.player.location = "lake"
    msgs = note_action(state, content, world, "move")
    assert state.player.tutorial_step == 3
    assert msgs.count("✔ 引導完成") == 2
    assert msgs[-1] == "【說書人】去闖吧。"


def test_location_only_step_completes_regardless_of_action(state, content, world):
    """把 s2 暫時改成純地點條件：人已經在湖邊時，任何行動都該完成它。"""
    content.tutorial.steps[1].done_when.action = None
    state.player.tutorial_step = 1
    state.player.location = "lake"
    msgs = note_action(state, content, world, "explore")
    assert state.player.tutorial_step == 2
    assert msgs[0] == "✔ 引導完成"


def _storyline_off(state, content):
    """開關打開、這一季蓋了「開」的章，第一季不觸發的清單裡有主線 main（計畫 T8，控制者 2026-10-04）。"""
    from tianxia.models import SeasonOneOff

    content.config.season_one = True
    state.world.season_one = True
    content.scenario.season_one_off = SeasonOneOff(storylines=["main"])
    state.player.tutorial_step = len(content.tutorial.steps)
    state.player.stamina = 50


def test_quest_text_skips_a_storyline_turned_off_in_season_one(state, content):
    """清單裡的主線不顯示（標題、幕、目標、下一步的幕目標、只屬於它的結局）；其餘照舊。開關關著照舊。"""
    _storyline_off(state, content)
    text = quest_text(state, content)
    assert "主線" not in text and "水寇橫行" not in text and "壓制寇亂" not in text
    assert "水寇稱霸：寇亂達 80" in text and "☐ 拜入門派" in text  # 不分主線的結局與個人目標照舊
    assert next_hint(state, content) == ""
    content.config.season_one = False
    assert "水寇橫行" in quest_text(state, content) and next_hint(state, content) == "壓制寇亂"


def test_quest_text_is_empty_when_everything_is_skipped(state, content):
    """全部都被跳過時，「主線與目標」那一塊不畫（quest_text 是空字串），由本週大事卡與倒數撐著。"""
    _storyline_off(state, content)
    content.scenario.milestones = []
    for ending in content.scenario.endings:
        ending.hint = ""
    assert quest_text(state, content) == ""
    state.player.stamina = 150  # 只剩「體力將滿」的提醒時照樣畫
    assert "體力將滿" in quest_text(state, content)
