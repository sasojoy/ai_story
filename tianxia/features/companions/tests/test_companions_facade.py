"""companions 這一包的測試，從 tests/core/test_engine.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
from unittest import mock
import pytest
from conftest import FixedRandom, walk_to
from tianxia import companion_agent, rules, team
from engine_kit import FAKE_TURN, NEXT_TURN, _figure, _hall, _no_model, _prepared, _spy_battle_status, ids  # noqa: F401

pytestmark = pytest.mark.whole_content


def test_recruit_option_follows_who_is_free_at_this_location(game):
    assert "招募【韓鐵】（體力 15・成功率約 35%）" in [o.label for o in game.options() if o.id == "act:recruit"]
    walk_to(game, "lake")
    assert "招募【琴師】（體力 15・成功率約 35%）" in [o.label for o in game.options() if o.id == "act:recruit"]
    game.world.try_recruit("friend", "李四")
    game.world.try_recruit("hero", "李四")
    assert "act:recruit" not in ids(game)  # 湖邊兩人都被搶走了


def _members(game):
    """出戰的人（名字, key）：本人永遠在第一位，接著是隊伍裡的同伴。"""
    return [(team.member_name(game.state, game.content, key), key) for key in team.team_keys(game.state)]


def test_add_and_remove_from_team(game):
    game.rng = FixedRandom(0.1)
    game.choose("act:recruit")
    assert _members(game) == [("沈浪", "player"), ("韓鐵", "mate")]
    game.remove_from_team("mate")
    assert _members(game) == [("沈浪", "player")]
    game.add_to_team("mate")
    assert _members(game) == [("沈浪", "player"), ("韓鐵", "mate")]


def test_you_yourself_are_never_added_to_or_removed_from_the_team(game):
    """名冊第一列是本人（key "player"）：加入、移出都只回一句話，隊伍裡不會多出一個 "player"。"""
    game.rng = FixedRandom(0.1)
    game.choose("act:recruit")
    for act in (game.add_to_team, game.remove_from_team):
        msgs = act("player")
        assert msgs == ["本人一直都在隊伍裡，不用加入，也不能移出。"]
        assert game.state.player.team == ["mate"]
        assert _members(game) == [("沈浪", "player"), ("韓鐵", "mate")]


def test_owned_companions_and_roster_lines(game):
    game.rng = FixedRandom(0.1)
    game.choose("act:recruit")
    assert game.owned_companions() == ["mate"]
    assert game.roster_lines() == [
        ("本人　沈浪　第 1 級", "player"),
        ("韓鐵　第 1 級　出戰", "mate"),
    ]


def test_socializing_with_a_deep_interaction_companion_starts_a_dialogue(content, game):
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        msgs = game.choose("act:socialize")
    assert msgs == ["他點了點頭。"]
    assert game.state.player.pending_companion == "mate"
    assert ids(game) == ["talk:0", "talk:1", "talk:say", "talk:leave"]
    assert game.scene_text() == "**韓鐵**（情誼 0）\n\n他點了點頭。"  # 名字旁寫著情誼（explain-1）


def test_locked_figures_use_talk_at_instead_of_recruit_at_for_dialogue(content, game):
    """龍頭人物（kind=locked）不可招募，深度對話走 talk_at，不是 recruit_at。"""
    ch = content.characters["mate"]
    ch.kind, ch.recruit_at, ch.talk_at, ch.deep_interaction = "locked", None, "town", True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        msgs = game.choose("act:socialize")
    assert msgs == ["他點了點頭。"]
    assert game.state.player.pending_companion == "mate"
    assert "act:recruit" not in ids(game)  # 鎖定人物不會因為 talk_at 而冒出招募選項


def test_each_dialogue_turn_costs_stamina(content, game):
    """伺服器假人設計第八節第 4 項：跟大勢人物對話每一輪扣體力，不再是免費的。"""
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
        before = game.state.player.stamina
        game.choose("talk:0")
    assert game.state.player.stamina == before - content.config.talk_stamina


def test_dialogue_turns_are_disabled_without_stamina_but_leaving_is_not(content, game):
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
    game.state.player.stamina = content.config.talk_stamina - 1
    options = {o.id: o for o in game.options()}
    assert not options["talk:0"].enabled and not options["talk:1"].enabled
    assert options["talk:leave"].enabled


def test_an_unavailable_dialogue_turn_costs_nothing_and_ends_the_talk(content, game):
    """模型叫不動：這輪不扣體力、不記好感度與交友 tag，對話直接結束（不再卡在同一句保底反應裡）。"""
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
    before = game.state.player.stamina
    with mock.patch.object(companion_agent, "_generate", side_effect=companion_agent.DialogueUnavailable("404")):
        msgs = game.choose("talk:0")
    assert msgs == ["韓鐵似乎無心多談，你只好先行告辭。"]
    assert game.state.player.stamina == before
    assert game.state.player.pending_companion is None
    assert game.state.player.affinities.get("mate", 0) == 0
    assert "mate" not in game.world.read().companion_tag_counts


def test_an_unavailable_opening_refunds_the_socialize_cost(content, game):
    content.characters["mate"].deep_interaction = True
    before = game.state.player.stamina
    with mock.patch.object(companion_agent, "_generate", side_effect=companion_agent.DialogueUnavailable("404")):
        msgs = game.choose("act:socialize")
    assert msgs == ["韓鐵似乎無心多談，你只好先行告辭。"]
    assert game.state.player.stamina == before
    assert game.state.player.pending_companion is None


def test_a_newcomer_without_fame_is_turned_away_from_a_figure(content, game):
    _figure(content, fame=10)
    with mock.patch("tianxia.features.socialize.actions.pick_event", return_value=None), \
            mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        msgs = game.choose("act:socialize")
    assert game.state.player.pending_companion is None
    assert msgs == ["韓鐵連見都不見你，門口的人把你請了出去。（名望還差 10）"]  # 內容沒寫打發話，用通用的那一句


def test_enough_fame_or_a_prior_meeting_opens_the_door(content, game):
    _figure(content, fame=10)
    game.state.player.flags.add("結識:mate")
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
    assert game.state.player.pending_companion == "mate"
    game.choose("talk:leave")
    game.state.player.flags.discard("結識:mate")
    game.state.player.stats["fame"] = 10
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
    assert game.state.player.pending_companion == "mate"


def test_three_turns_a_day_with_the_same_figure(content, game):
    _figure(content)
    game.state.player.fortune = True  # 第二天起交友會先觸發新立門戶福緣，這裡只測輪數上限
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
        game.choose("talk:0")
        game.choose("talk:0")
        msgs = game.choose("talk:0")
        moment = rules.day_ends_text(content, game.state.world)  # 換日的那一刻（遊戲日跟著季長縮，企劃者 2026-10-08）
        assert msgs[-1] == f"韓鐵起身送客，改日再敘：要到 {moment} 之後才能再來拜會。"
        assert game.state.player.pending_companion is None
        with mock.patch("tianxia.features.socialize.actions.pick_event", return_value=None):
            msgs = game.choose("act:socialize")
        assert msgs == [f"韓鐵事忙，要到 {moment} 之後才得空。"]
        game.state.world.time = rules.day_ends(content, game.state.world)  # 換日重算
        game.choose("act:socialize")
    assert game.state.player.pending_companion == "mate"


# ── 鎖外生成：dialogue_request 與 choose(prepared=...) ────────────────


def _open_dialogue(content, game):
    """停在小鎮、已跟韓鐵開了第一輪對話（選項是「閒聊幾句」「就此告辭」）；福緣設成已領，交友不會先觸發福緣。"""
    _figure(content)
    game.state.player.fortune = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")


def test_dialogue_request_for_a_talk_option_carries_the_offered_text(content, game):
    _open_dialogue(content, game)
    req = game.dialogue_request("talk:0")
    assert (req.option_id, req.companion_id, req.player_action) == ("talk:0", "mate", "閒聊幾句")
    assert req.messages[-1]["content"].startswith("玩家的行動：「閒聊幾句」")
    assert game.dialogue_request("talk:1").player_action == "就此告辭"


def test_dialogue_request_is_none_for_leaving_and_for_options_that_are_not_offered(content, game):
    _open_dialogue(content, game)
    assert game.dialogue_request("talk:leave") is None
    assert game.dialogue_request("talk:2") is None  # 只有兩個選項
    assert game.dialogue_request("talk:x") is None
    assert game.dialogue_request("act:socialize") is None  # 對話中選單上沒有交友


def test_dialogue_request_for_socialize_is_the_generic_opening(content, game):
    _figure(content)
    game.state.player.fortune = True
    req = game.dialogue_request("act:socialize")
    assert (req.option_id, req.companion_id, req.player_action) == (
        "act:socialize", "mate", companion_agent.GENERIC_OPENING,
    )
    assert req.messages == companion_agent._build_messages(
        content.characters["mate"], game.state, content, game.world, "mate", companion_agent.GENERIC_OPENING,
    )


def test_dialogue_request_is_none_when_socialize_would_not_open_a_dialogue(content, game):
    _figure(content, fame=10)
    game.state.player.fortune = True
    assert game.dialogue_request("act:socialize") is None  # 名望不夠，見不到
    game.state.player.stats["fame"] = 10
    assert game.dialogue_request("act:socialize") is not None
    game.state.player.stamina = 0
    assert game.dialogue_request("act:socialize") is None  # 選項停用
    game.state.player.stamina = content.config.stamina_max
    game.state.world.time += 86400 * content.config.fortune_day_min
    game.state.player.fortune = False
    assert game.dialogue_request("act:socialize") is None  # 福緣先到，交友不開對話


def test_dialogue_request_does_not_change_the_game(content, game):
    _open_dialogue(content, game)
    def snapshot():  # 角色存檔不含賽季（GameState.world 不進 model_dump），賽季要另外比：記憶體裡的與全服共用的那一份
        return game.state.model_dump(), game.state.world.model_dump(), game.world.get_season().model_dump()

    before = snapshot()
    game.dialogue_request("talk:0")
    game.dialogue_request("act:socialize")
    assert snapshot() == before


def test_choose_applies_a_prepared_talk_turn_without_calling_the_model(content, game):
    _open_dialogue(content, game)
    before = game.state.player.stamina
    prepared = _prepared(game, "talk:0", turn=NEXT_TURN)
    with _no_model(), mock.patch.object(game.client, "chat_structured", side_effect=AssertionError("不該呼叫模型")):
        msgs = game.choose("talk:0", prepared=prepared)
    assert msgs == ["他笑了笑。", "（情誼 +1）"]
    assert game.state.player.stamina == before - content.config.talk_stamina
    assert game._talks_used("mate") == 1  # 這一輪算進今天的輪數
    assert game.state.player.last_offered_dialogue["mate"] == [["再聊聊", "起身告辭"], ["雪中送炭", "尋常寒暄"]]
    assert game.state.player.affinities["mate"] == 1


def test_choose_applies_a_prepared_opening_without_calling_the_model(content, game):
    _figure(content)
    game.state.player.fortune = True
    before = game.state.player.stamina
    prepared = _prepared(game, "act:socialize", turn=NEXT_TURN)
    with _no_model():
        msgs = game.choose("act:socialize", prepared=prepared)
    assert msgs == ["他笑了笑。"]
    assert game.state.player.pending_companion == "mate"
    assert game.state.player.stamina == before - content.config.action_cost["socialize"]
    assert ids(game) == ["talk:0", "talk:1", "talk:say", "talk:leave"]


def test_a_prepared_failure_for_the_opening_refunds_the_socialize_cost(content, game):
    """鎖外生成失敗（turn=None）：跟鎖內 DialogueUnavailable 完全一樣——退回交友體力、不開對話、同一句說明。"""
    _figure(content)
    game.state.player.fortune = True
    before = game.state.player.stamina
    prepared = _prepared(game, "act:socialize", turn=None)
    with _no_model():
        msgs = game.choose("act:socialize", prepared=prepared)
    assert msgs == ["韓鐵似乎無心多談，你只好先行告辭。"]
    assert game.state.player.stamina == before
    assert game.state.player.pending_companion is None


def test_a_prepared_failure_for_a_talk_turn_costs_nothing_and_ends_the_talk(content, game):
    _open_dialogue(content, game)
    before = game.state.player.stamina
    prepared = _prepared(game, "talk:0", turn=None)
    with _no_model():
        msgs = game.choose("talk:0", prepared=prepared)
    assert msgs == ["韓鐵似乎無心多談，你只好先行告辭。"]
    assert game.state.player.stamina == before
    assert game.state.player.pending_companion is None
    assert game.state.player.affinities.get("mate", 0) == 0
    assert game._talks_used("mate") == 0
    assert "mate" not in game.world.read().companion_tag_counts


def test_a_mismatched_prepared_turn_is_ignored_and_the_normal_path_generates(content, game):
    """對不上（玩家行動不同，例如選項清單已經換了）：丟掉預先生成的，照一般路徑在鎖內生成。"""
    _open_dialogue(content, game)
    stale = companion_agent.PreparedTurn("talk:0", "mate", "已經不在選單上的話", FAKE_TURN)
    with mock.patch.object(companion_agent, "_generate", return_value=NEXT_TURN) as gen:
        msgs = game.choose("talk:0", prepared=stale)
    gen.assert_called_once()
    assert msgs[0] == "他笑了笑。"  # 用的是現生成的，不是 stale 帶的 FAKE_TURN


def test_a_mismatched_failed_prepared_turn_does_not_end_the_talk(content, game):
    """對不上的 prepared 連同它的失敗一起丟掉：不能因為別張單子失敗，就把這輪對話結束掉。"""
    _open_dialogue(content, game)
    stale = companion_agent.PreparedTurn("talk:0", "mate", "已經不在選單上的話", None)
    with mock.patch.object(companion_agent, "_generate", return_value=NEXT_TURN):
        msgs = game.choose("talk:0", prepared=stale)
    assert msgs[0] == "他笑了笑。"
    assert game.state.player.pending_companion == "mate"


def test_a_prepared_turn_for_another_companion_or_option_is_ignored(content, game):
    for stale in (
        companion_agent.PreparedTurn("talk:0", "someone_else", "閒聊幾句", FAKE_TURN),
        companion_agent.PreparedTurn("talk:1", "mate", "閒聊幾句", FAKE_TURN),
    ):
        _open_dialogue(content, game)
        with mock.patch.object(companion_agent, "_generate", return_value=NEXT_TURN) as gen:
            msgs = game.choose("talk:0", prepared=stale)
        gen.assert_called_once()
        assert msgs[0] == "他笑了笑。"
        game.choose("talk:leave")  # 退出這段對話，下一個 stale 重新開


def test_a_prepared_turn_is_ignored_by_options_that_do_not_use_it(content, game):
    _figure(content)
    game.state.player.fortune = True
    stray = companion_agent.PreparedTurn("act:explore", "mate", "x", FAKE_TURN)
    before = game.state.player.stamina
    with _no_model():
        game.choose("act:explore", prepared=stray)
    assert game.state.player.stamina == before - content.config.action_cost["explore"]
    assert game.state.player.pending_companion is None


def test_a_prepared_opening_is_dropped_by_the_recheck_when_the_fortune_comes_due_meanwhile(content, game):
    """生成的那段時間福緣到期：交友選項還在、還能按，但這次交友會先發福緣、不開對話——這才是重驗擋下來的情況。"""
    _figure(content)
    game.state.player.fortune = True
    prepared = _prepared(game, "act:socialize")
    game.state.player.fortune = False
    game.state.world.time += 86400 * content.config.fortune_day_min
    assert any(o.id == "act:socialize" and o.enabled for o in game.options())
    assert game._checked_prepared("act:socialize", prepared) is None
    with _no_model():
        game.choose("act:socialize", prepared=prepared)
    assert game.state.player.pending_companion is None
    assert game.state.player.fortune  # 走的是福緣那條路，不是對話


def test_dialogue_request_and_the_recheck_never_tick_the_battle(content, game):
    """一次請求只能推進一次戰鬥（推進可能結算一回合、呼叫 LLM 潤色，而且是握著鎖呼叫）：
    備料（階段 A）與進鎖後的重驗都只讀，推進交給 choose() 自己開頭那一次。"""
    _open_dialogue(content, game)
    prepared = _prepared(game, "talk:0")
    calls, patched = _spy_battle_status(game)
    with patched:
        game.dialogue_request("talk:0")
        game.dialogue_request("act:socialize")
        game._checked_prepared("talk:0", prepared)
    assert calls and True not in calls


def test_choosing_a_prepared_dialogue_option_ticks_the_battle_only_once(content, game):
    _open_dialogue(content, game)
    prepared = _prepared(game, "talk:0")
    calls, patched = _spy_battle_status(game)
    with patched, _no_model():
        game.choose("talk:0", prepared=prepared)
    assert calls.count(True) == 1


def test_calling_on_a_figure_starts_the_dialogue_with_that_figure(content, game):
    _hall(content, game)
    game.choose("act:call")
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN), \
            mock.patch("tianxia.engine.note_action", return_value=[]) as noted:
        msgs = game.choose("call:scholar")
    assert msgs == ["他點了點頭。"]
    p = game.state.player
    assert p.pending_companion == "scholar" and not p.picking_audience
    assert p.stamina == content.config.stamina_max - content.config.action_cost["socialize"]
    assert ids(game) == ["talk:0", "talk:1", "talk:say", "talk:leave"]
    assert game.state.journal[0].title == "求見・書生"
    noted.assert_called_once()
    assert noted.call_args.args[3] == "socialize"  # 指名求見算一次交友（新手引導、任務）
