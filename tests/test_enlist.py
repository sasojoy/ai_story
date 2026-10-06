"""入伍段（新手引導計畫二）：第一次投靠時由引薦人帶三步。用真實內容、打開第一季開關（照 tests/test_orders.py）。"""
import pytest

from tests.test_orders import _game, _order, _win, on, real  # noqa: F401（fixture）
from tianxia import enlist, guide
from tianxia.content import ContentError, validate
from tianxia.models import Enlist, EnlistStep, Recruiter, TutorialGoal


@pytest.fixture
def enlisting(on):
    """測試用的入伍段（正式文字是 Task 3 的事）：兩步、三位引薦人。lines 不帶名字（框上的名字另外寫，preflight F9）。"""
    people = {
        fid: Recruiter(
            name=name, intro=f"{name}迎你進營。", briefing="看這三條線。", order_hint="挑一道軍令。",
            done="做得好。", lines=["看看本週軍令", "挑一道軍令，出一次力"], rejoin="又是你。",
        )
        for fid, name in (("guan", "老石"), ("huang", "青禾"), ("haoqiang", "季伯平"))
    }
    on.tutorial.enlist = Enlist(
        steps=[
            EnlistStep(id="r2_briefing", done_when=TutorialGoal(action="view_orders")),
            EnlistStep(id="r3_first_order", done_when=TutorialGoal(action="order")),
        ],
        recruiters=people, drifter_line="想投靠的話……",
    )
    on.tutorial.steps = [s for s in on.tutorial.steps if not s.season_one]  # 舊的 t7、t8 由入伍段取代
    return on


def _joined(content, at="changshe", faction="guan"):
    game = _game(content, at=at)
    game.state.player.tutorial_step = len(guide.steps(game.state, content))  # 序章與舊引導都走完了
    game.choose(f"faction:{faction}")
    game.choose("faction:confirm")
    return game


def test_joining_opens_the_first_step_only(enlisting):
    game = _joined(enlisting)
    assert game.state.player.enlist_step == 0
    box = game.guide_box()
    assert box["speaker"] == "老石" and box["text"] == "老石迎你進營。\n\n看這三條線。"
    assert box["line"] == "看看本週軍令" and box["key"] == "r2_briefing"  # key 是這一步的 id（FB-076 的欄位，不另加 step）
    assert box["end"] is False and box["pending"] is False and box["done"] == []


def test_seeing_the_orders_then_doing_one_finishes(enlisting):
    game = _joined(enlisting)
    game.view_orders()
    assert game.state.player.enlist_step == 1 and game.guide_box()["text"] == "挑一道軍令。"
    assert game.guide_box()["key"] == "r3_first_order"
    _order(game, "siege", "guan", front="yingru")
    with _win():
        game.choose("act:train")
    assert enlist.done(game.state, enlisting)
    box = game.guide_box()
    assert box["end"] and box["text"] == "做得好。" and box["speaker"] == "老石"
    assert box["key"] == "enlist_end" and box["pending"] is False and box["done"] == ["✔ 引導完成"]
    game.guide_ack()
    assert game.guide_box() is None
    assert not game.state.player.enlist_end


def test_joining_through_a_sect_starts_enlistment(enlisting):
    from tianxia.models import Effect
    from tianxia.rules import apply_effect

    game = _game(enlisting, at="cao_manor")
    game.state.player.tutorial_step = len(guide.steps(game.state, enlisting))
    apply_effect(Effect(join_sect="cao_manor"), game.state, enlisting, game.world)
    assert enlist.begin_if_joined(game.state, enlisting)
    assert enlist.recruiter(game.state, enlisting).name == "季伯平"


def test_a_sect_joined_through_an_event_choice_starts_enlistment(enlisting):
    """拜入陣營名下的門派在事件的選項裡（choose 的 choice:N），也從那一下開始入伍段（Review Focus 2，走真正的 choose）。"""
    from tianxia.models import Choice, Effect, Event

    game = _game(enlisting, at="cao_manor")
    game.state.player.tutorial_step = len(guide.steps(game.state, enlisting))
    event = Event(
        id="t_join_sect", title="結社", text="莊裡的人問你要不要入夥。", actions=[],
        choices=[Choice(text="入夥", effect=Effect(join_sect="cao_manor"))],
    )
    enlisting.events[event.id] = event
    game._present(event)
    game.choose("choice:0")
    assert game.state.player.faction == "haoqiang" and game.state.player.enlist_step == 0
    assert game.guide_box()["speaker"] == "季伯平"


def test_enlistment_waits_behind_the_tutorial(enlisting):
    game = _game(enlisting, at="changshe")
    game.state.player.tutorial_step = 1  # 引導還有一步有話的沒走完（序章第 2 步）
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert game.state.player.enlist_step == 0
    waiting = guide.steps(game.state, enlisting)[1]
    assert game.guide_box()["speaker"] == guide.speaker_of(enlisting, waiting)  # 框照舊是引導那一步（內容還沒換成師父，所以不寫死名字）
    assert game.guide_box()["speaker"] != "老石" and game.guide_box()["key"] == waiting.id
    game.view_orders()
    assert game.state.player.enlist_step == 1  # 進度照記


def test_the_recruiters_check_mark_waits_for_its_own_box(enlisting):
    """F11：引導那一步還在框上時，入伍段的進度照記，可是「✔ 引導完成」不能掛在說書人的框上（那一步根本沒做完）。"""
    game = _game(enlisting, at="changshe")
    game.state.player.tutorial_step = 1
    game.choose("faction:guan")
    game.choose("faction:confirm")
    game.view_orders()
    assert game.state.player.enlist_step == 1
    assert game.guide_box()["done"] == []  # 說書人的框上沒有別人的 ✔
    assert game.state.journal[0].guide == []  # 江湖紀錄也不寫


def test_finishing_enlistment_does_not_bring_back_the_outro(enlisting):
    enlisting.tutorial.outro = "去闖吧。"
    game = _joined(enlisting)
    game.state.player.guide_outro = False  # 結語早就按過「知道了」
    game.view_orders()
    assert not game.state.player.guide_outro


def test_a_pending_outro_is_shown_before_the_recruiter(enlisting):
    """F8：先是引導的步驟、再是結語、最後才是入伍段；「知道了」只收框上那一個。結語還沒按就投靠了：框還是結語，
    按下去之後才輪到引薦人（不然按「知道了」把兩個一起清掉，結語從沒出現過）。"""
    enlisting.tutorial.outro = "去闖吧。"
    game = _game(enlisting, at="changshe")
    game.state.player.tutorial_step = len(guide.steps(game.state, enlisting))
    game.state.player.guide_outro = True
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert game.state.player.enlist_step == 0
    box = game.guide_box()
    assert box["end"] and box["key"] == "outro" and box["text"] == "去闖吧。"
    game.guide_ack()
    box = game.guide_box()
    assert box["speaker"] == "老石" and box["key"] == "r2_briefing" and not box["end"]
    assert not game.state.player.guide_outro


def test_acknowledging_the_enlistment_ending_leaves_a_pending_outro_alone(enlisting):
    """反過來：入伍段走完、結尾在框上時按「知道了」只收入伍段的結尾。"""
    game = _joined(enlisting)
    game.view_orders()
    _order(game, "siege", "guan", front="yingru")
    with _win():
        game.choose("act:train")
    assert game.guide_box()["key"] == "enlist_end"
    game.guide_ack()
    assert game.guide_box() is None and not game.state.player.enlist_end


def test_no_enlistment_outside_season_one(enlisting):
    enlisting.config.season_one = False
    game = _joined(enlisting)
    assert game.state.player.enlist_step is None


def test_skipping_the_guide_skips_enlistment(enlisting):
    game = _game(enlisting, at="changshe")
    game.skip_tutorial()
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert enlist.done(game.state, enlisting) and game.guide_box() is None


def test_skipping_during_enlistment_skips_the_rest(enlisting):
    """F7：序章與舊引導都走完了、入伍段正在進行，設定頁的「略過新手引導」不能什麼都不做（設計 7.3）。"""
    game = _joined(enlisting)
    assert enlist.active(game.state, enlisting) and game.guide_box()["speaker"] == "老石"
    msgs = game.skip_tutorial()
    assert msgs and enlist.done(game.state, enlisting) and game.guide_box() is None
    assert game.state.player.guide_skipped and not game.state.player.enlist_end
    game.view_orders()  # 之後軍令卡出現也不再冒出結尾
    assert game.guide_box() is None


def test_skipping_when_there_is_nothing_left_to_skip_does_nothing(enlisting):
    """引導與入伍段都沒有在進行（還沒投靠、引導走完）：照舊什麼都不做。"""
    game = _game(enlisting, at="changshe")
    game.state.player.tutorial_step = len(guide.steps(game.state, enlisting))
    assert game.skip_tutorial() == [] and not game.state.player.guide_skipped


def test_the_recruiter_box_collapses_while_an_event_is_pending(enlisting):
    """F12（FB-063／FB-076 用在入伍段）：眼前有事件還沒了結時，引薦人的框也換成「先把眼前的「…」了結」、pending 標 True，
    網頁就把它收成一行；收起來那一行也跟著換。結尾照舊不被事件擋住。"""
    game = _joined(enlisting)
    event = next(iter(enlisting.events.values()))
    game.state.pending_event = event.id
    box = game.guide_box()
    assert box["speaker"] == "老石" and box["key"] == "r2_briefing"
    assert box["text"] == guide.pending_line(game.state, enlisting) == f"先把眼前的「{event.title}」了結"
    assert box["pending"] is True and box["line"] == ""
    game.state.pending_event = None
    assert game.guide_box()["pending"] is False and game.guide_box()["line"] == "看看本週軍令"
    game.state.player.enlist_step, game.state.player.enlist_end = 2, True
    game.state.pending_event = event.id
    assert game.guide_box()["end"] and game.guide_box()["pending"] is False


def test_the_recruiters_hint_has_no_doubled_name(enlisting):
    """F9：lines 不帶名字——「下一步」寫「（老石）看看本週軍令」，不是「（老石）老石：…」。"""
    game = _joined(enlisting)
    assert guide.next_hint(game.state, enlisting, game.world) == "（老石）看看本週軍令"
    game.view_orders()
    assert guide.next_hint(game.state, enlisting, game.world) == "（老石）挑一道軍令，出一次力"
    event = next(iter(enlisting.events.values()))
    game.state.pending_event = event.id  # 事件擋著路時「下一步」跟框一樣：先了結它
    assert guide.next_hint(game.state, enlisting, game.world) == f"（老石）先把眼前的「{event.title}」了結"
    assert "老石" in guide.speakers(enlisting) and "青禾" in guide.speakers(enlisting)


def test_the_recruiters_words_are_not_mistaken_for_a_checkmark_row(enlisting):
    """引薦人的名字在 guide.speakers 裡：_note_guide 照它把「下一步的話」跟「✔ 與獎勵」分開。"""
    assert {"老石", "青禾", "季伯平"} <= guide.speakers(enlisting)


def test_view_orders_only_counts_for_the_enlistment_step_that_asks_for_it(enlisting):
    game = _game(enlisting, at="changshe")
    before = list(game.state.journal[0].guide)
    game.view_orders()  # 還沒投靠、入伍段還沒開始：什麼都不發生
    assert game.state.player.enlist_step is None and game.state.journal[0].guide == before
    game = _joined(enlisting)
    game.view_orders()
    game.view_orders()  # 第二步要的是替軍令出力，再看一次不算
    assert game.state.player.enlist_step == 1


def test_the_content_check_wants_real_factions_and_one_line_per_step(enlisting):
    validate(enlisting)
    enlisting.tutorial.enlist.recruiters["nobody"] = Recruiter(
        name="某人", intro="a", briefing="b", order_hint="c", done="d", lines=["x", "y"],
    )
    with pytest.raises(ContentError, match="nobody"):
        validate(enlisting)
    del enlisting.tutorial.enlist.recruiters["nobody"]
    enlisting.tutorial.enlist.recruiters["guan"].lines = ["只有一行"]
    with pytest.raises(ContentError, match="老石|guan"):
        validate(enlisting)


def test_view_orders_is_a_main_action_that_the_season_pause_allows():
    """F6：軍令卡出現時網頁送 view_orders；賽季時鐘暫停中它跟 view_map 一樣只動自己的引導，不能被擋下（不然 S.ordersSeen 已經設了，
    這個工作階段不會再送）。"""
    import server

    assert "view_orders" in server.MAIN_ACTIONS and "view_orders" in server.PAUSE_OK_ACTIONS
