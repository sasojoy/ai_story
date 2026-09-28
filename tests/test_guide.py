from tianxia.guide import next_hint, note_action, quest_text, tutorial_active, tutorial_intro


def test_intro_is_first_step(content):
    assert tutorial_intro(content) == ["【說書人】先探索一下。"]


def test_matching_action_completes_step_and_rewards(state, content):
    msgs = note_action(state, content, "explore")
    assert state.player.tutorial_step == 1
    assert state.player.stats["silver"] == 55
    assert msgs[0] == "✔ 引導完成：先探索一下。"
    assert msgs[-1] == "【說書人】去湖邊。"


def test_wrong_action_or_place_does_nothing(state, content):
    assert note_action(state, content, "train") == []
    note_action(state, content, "explore")
    assert note_action(state, content, "move") == []  # 還在小鎮，不是湖邊
    state.player.location = "lake"
    note_action(state, content, "move")
    assert state.player.tutorial_step == 2


def test_outro_after_last_step(state, content):
    state.player.tutorial_step = 2
    msgs = note_action(state, content, "view_map")
    assert not tutorial_active(state, content)
    assert msgs[-1] == "【說書人】去闖吧。"
    assert note_action(state, content, "view_map") == []


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


def test_quest_text_after_season_end(state, content):
    state.world.ended = True
    state.world.ending_title = "風雨飄搖"
    state.world.ending_text = "江南依舊動盪。"
    assert quest_text(state, content).startswith("### 賽季落幕：風雨飄搖")
