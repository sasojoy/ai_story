"""人物記得上次談了什麼（Joy 2026-10-23）：模型每一輪寫一句 talk_memo，引擎夾長度存在 PlayerState.talk_memos；
下次求見時放進對話提示（開口那一輪要他提起），談話畫面名字底下寫「上回」。只記文字，不動情誼與任何數值。"""

from random import Random

from tianxia import companion_agent
from tianxia.companion_agent import CompanionTurn
from tianxia.state import TalkMemo

DAY = 86400


def _turn(memo=None, narrative="他點了點頭。"):
    return CompanionTurn(
        narrative=narrative, options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "雪中送炭"], talk_memo=memo,
    )


def _prompt(content, state, world):
    return companion_agent.build_system_prompt(content.characters["mate"], state, content, world, "mate")


def test_each_turn_stores_the_models_memo_with_time_and_place(content, state, world):
    state.world.time = 3 * DAY + 100
    companion_agent.start_dialogue(None, state, content, world, "mate", Random(0), turn=_turn("談到潁川的糧道吃緊"))
    memo = state.player.talk_memos["mate"]
    assert (memo.text, memo.at, memo.place) == ("談到潁川的糧道吃緊", 3 * DAY + 100, state.player.location)
    assert "mate" not in state.player.talk_prev  # 第一次見面：沒有上回


def test_the_memo_is_clipped_and_cleaned(content, state, world):
    long = "「談到" + "糧" * 80 + "」\n"
    companion_agent.start_dialogue(None, state, content, world, "mate", Random(0), turn=_turn(long))
    text = state.player.talk_memos["mate"].text
    assert len(text) == companion_agent.MEMO_CHARS and "「" not in text and "\n" not in text


def test_without_a_memo_the_players_line_is_kept_but_not_the_opening(content, state, world):
    companion_agent.start_dialogue(None, state, content, world, "mate", Random(0), turn=_turn(None))
    assert "mate" not in state.player.talk_memos  # 開口那一句是通用的攀談，不記
    state.player.last_offered_dialogue["mate"] = [["問他糧道的事", "告辭"], ["真誠請教", "尋常寒暄"]]
    companion_agent.continue_dialogue(None, state, content, world, "mate", 0, Random(0), turn=_turn(None))
    assert state.player.talk_memos["mate"].text == "你說起「問他糧道的事」"


def test_next_visit_puts_last_time_into_the_opening_prompt(content, state, world):
    state.player.talk_memos["mate"] = TalkMemo(text="約好下回一起去汝南", at=1 * DAY, place=state.player.location)
    state.world.time = 3 * DAY
    line = next(x for x in _prompt(content, state, world).splitlines() if x.startswith("【上回見面】"))
    assert "2 天前" in line and "約好下回一起去汝南" in line and "開口時自然地提起" in line


def test_no_last_time_section_before_ever_talking(content, state, world):
    assert "【上回見面】" not in _prompt(content, state, world)


def test_opening_moves_the_old_memo_to_prev_and_keeps_it_through_the_talk(content, state, world):
    old = TalkMemo(text="約好下回一起去汝南", at=1 * DAY, place=state.player.location)
    state.player.talk_memos["mate"] = old
    state.world.time = 2 * DAY
    companion_agent.start_dialogue(None, state, content, world, "mate", Random(0), turn=_turn("說起汝南已經到了"))
    assert state.player.talk_prev["mate"] == old
    assert state.player.talk_memos["mate"].text == "說起汝南已經到了"
    assert companion_agent.last_talk(state, "mate") == old  # 談話中：上回是開口之前那一份
    line = next(x for x in _prompt(content, state, world).splitlines() if x.startswith("【上回見面】"))
    assert "約好下回一起去汝南" in line and "不要重複追問" in line
    companion_agent.leave_dialogue(state)
    assert companion_agent.last_talk(state, "mate").text == "說起汝南已經到了"  # 談完：下次的上回就是這一次


def test_the_memo_does_not_change_affinity(content, state, world):
    state.player.last_offered_dialogue["mate"] = [["誇他兩句", "告辭"], ["雪中送炭", "尋常寒暄"]]
    state.player.pending_companion = "mate"
    companion_agent.continue_dialogue(None, state, content, world, "mate", 0, Random(0), turn=_turn("誇了他練兵有方"))
    assert state.player.affinities["mate"] == 8  # 照 tag 查表，跟沒有 memo 一樣


def test_the_prompt_asks_for_the_memo_field(content, state, world):
    prompt = _prompt(content, state, world)
    assert "talk_memo" in prompt and '"talk_memo": "..."' in prompt
    assert '"talk_memo"' in companion_agent.free_line(content.characters["mate"], "久仰")


def test_generated_memo_is_converted_to_traditional():
    class Client:
        def chat_structured(self, *a, **k):
            return _turn("谈到粮道")

    assert companion_agent.generate_turn(Client(), []).talk_memo == "談到糧道"


def test_the_talk_scene_shows_last_time(game):
    s = game.state
    s.player.talk_memos["mate"] = TalkMemo(text="約好下回一起去汝南", at=s.world.time, place=s.player.location)
    companion_agent.start_dialogue(None, s, game.content, game.world, "mate", Random(0), turn=_turn("說起汝南"))
    scene = game.scene_text()
    assert "上回（" in scene and "約好下回一起去汝南" in scene
    assert game.content.locations[s.player.location].name in scene


def test_the_memos_start_over_with_the_season(game):
    s = game.state
    s.player.talk_memos["mate"] = TalkMemo(text="約好下回一起去汝南", at=0, place=s.player.location)
    s.player.talk_prev["mate"] = TalkMemo(text="更早的事", at=0, place=s.player.location)
    game._reset_player_for_new_season(s.player.season_number + 1)
    assert game.state.player.talk_memos == {} and game.state.player.talk_prev == {}
