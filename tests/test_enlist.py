"""入伍段（新手引導計畫二）：第一次投靠時由引薦人帶三步。用真實內容、打開第一季開關（fixture on 在 tests/conftest.py，
跟 test_orders 同一份）。"""
import pytest

from tests.test_orders import _game, _order, _win
from tianxia import enlist, guide
from tianxia.state import ONBOARDING_VERSION
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


def _joined_mid_tutorial(content):
    """引導還沒走完（tutorial_step 是 1，說書人那一步還在框上）就在長社投靠了官軍。"""
    game = _game(content, at="changshe")
    game.state.player.tutorial_step = 1
    game.choose("faction:guan")
    game.choose("faction:confirm")
    return game


def test_the_recruiters_check_mark_waits_for_its_own_box(enlisting):
    """F11：引導那一步還在框上時，入伍段的進度照記，可是「✔ 引導完成」不能掛在說書人的框上（那一步根本沒做完）。"""
    game = _joined_mid_tutorial(enlisting)
    game.view_orders()
    assert game.state.player.enlist_step == 1
    assert game.guide_box()["done"] == []  # 說書人的框上沒有別人的 ✔
    assert not any(line.startswith("✔") for entry in game.state.journal for line in entry.guide)  # 江湖紀錄也不寫 ✔（引薦人的話照記）


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


def test_acknowledging_the_enlistment_ending_closes_the_box(enlisting):
    """入伍段走完、結尾在框上時按「知道了」：結尾收起，之後沒有框。"""
    game = _joined(enlisting)
    game.view_orders()
    _order(game, "siege", "guan", front="yingru")
    with _win():
        game.choose("act:train")
    assert game.guide_box()["key"] == "enlist_end"
    game.guide_ack()
    assert game.guide_box() is None and not game.state.player.enlist_end


def test_the_outro_and_the_enlistment_ending_are_acknowledged_one_at_a_time(enlisting):
    """F8：結語還沒按、入伍段已經走完（兩個旗標都立著）：框是結語，按一下只收結語，框換成入伍段的結尾，再按一下才收它。"""
    enlisting.tutorial.outro = "去闖吧。"
    game = _joined(enlisting)
    p = game.state.player
    p.enlist_step, p.enlist_end, p.guide_outro = 2, True, True
    assert game.guide_box()["key"] == "outro"
    game.guide_ack()
    assert not p.guide_outro and p.enlist_end and game.guide_box()["key"] == "enlist_end"
    game.guide_ack()
    assert not p.enlist_end and game.guide_box() is None


def test_a_stray_acknowledge_while_a_tutorial_step_is_up_closes_nothing(enlisting):
    """引導的步驟還在框上時沒有「知道了」可按：伺服器收到的 guide_ack（舊畫面、重送）不能把還沒輪到的入伍段結尾收掉。"""
    game = _joined(enlisting)
    p = game.state.player
    p.enlist_step, p.enlist_end, p.tutorial_step = 2, True, 1
    assert game.guide_box()["key"] == guide.steps(game.state, enlisting)[1].id
    game.guide_ack()
    assert p.enlist_end
    p.tutorial_step = len(guide.steps(game.state, enlisting))  # 引導走完了：輪到入伍段的結尾
    assert game.guide_box()["key"] == "enlist_end"


def test_the_recruiters_check_mark_does_not_land_on_a_pending_outro(enlisting):
    """F11：結語還沒按、入伍段的第一步在這時做完了：進度照記，可是「✔ 引導完成」不掛在結語上（結語那一步早就做完了）；
    結語按掉之後輪到的是入伍段的下一步，完成列也是空的。"""
    enlisting.tutorial.outro = "去闖吧。"
    game = _joined(enlisting)
    p = game.state.player
    p.guide_outro = True
    game.view_orders()
    assert p.enlist_step == 1
    box = game.guide_box()
    assert box["key"] == "outro" and box["done"] == [] and p.guide_done == []
    game.guide_ack()
    assert game.guide_box()["key"] == "r3_first_order" and game.guide_box()["done"] == []


def _join_is_the_last_step(content):
    """引導的最後一步是「投靠」（舊的 t7 的樣子）：投靠那一下就把引導走完，用來看那一下的 ✔ 掛在哪一個框上。"""
    from tianxia.models import Condition, TutorialStep

    content.tutorial.steps.append(TutorialStep(
        id="t_join", text="去投靠一邊。", done_when=TutorialGoal(condition=Condition(factions=["guan", "huang", "haoqiang"])),
    ))
    game = _game(content, at="changshe")
    game.state.player.tutorial_step = len(guide.steps(game.state, content)) - 1
    return game


def test_a_step_the_join_finishes_does_not_leave_its_check_on_the_recruiters_box(enlisting):
    """投靠那一下把引導的最後一步做完（沒有結語）：框換成引薦人，剛投靠這一下不算完成任何一步，說書人那一步的 ✔ 不掛在他的框上。"""
    enlisting.tutorial.outro = ""  # 正式內容有結語；這個測試要看沒有結語的樣子
    game = _join_is_the_last_step(enlisting)
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert not guide.tutorial_active(game.state, enlisting) and game.state.player.enlist_step == 0
    box = game.guide_box()
    assert box["speaker"] == "老石" and box["done"] == []


def test_a_step_the_join_finishes_keeps_its_check_on_the_outro(enlisting):
    """同樣是投靠做完最後一步，但有結語：框是結語，說書人那一步的 ✔ 還在結語上；按掉之後才是引薦人、完成列是空的。"""
    enlisting.tutorial.outro = "去闖吧。"
    game = _join_is_the_last_step(enlisting)
    game.choose("faction:guan")
    game.choose("faction:confirm")
    box = game.guide_box()
    assert box["key"] == "outro" and box["done"] == ["✔ 引導完成"]
    game.guide_ack()
    assert game.guide_box()["speaker"] == "老石" and game.guide_box()["done"] == []


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


def test_skipping_after_the_tutorial_but_before_joining_skips_enlistment(enlisting):
    """設計 7.3「略過新手引導＝跳過序章與入伍段」：引導走完、還沒投靠就按「略過」，不是什麼都不發生——之後投靠也不開始入伍段。"""
    game = _game(enlisting, at="changshe")
    game.state.player.tutorial_step = len(guide.steps(game.state, enlisting))
    assert enlist.waiting(game.state, enlisting)
    msgs = game.skip_tutorial()
    assert msgs and game.state.player.guide_skipped and enlist.done(game.state, enlisting)
    assert not enlist.waiting(game.state, enlisting)
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert enlist.done(game.state, enlisting) and game.guide_box() is None  # 投靠了也不開始、不畫框
    assert "老石" not in guide.next_hint(game.state, enlisting, game.world)


def test_skipping_with_the_outro_pending_clears_it_and_enlistment_is_skipped_too(enlisting):
    enlisting.tutorial.outro = "去闖吧。"
    game = _game(enlisting, at="changshe")
    game.state.player.tutorial_step = len(guide.steps(game.state, enlisting))
    game.state.player.guide_outro = True
    assert game.skip_tutorial()
    assert not game.state.player.guide_outro and game.guide_box() is None and enlist.done(game.state, enlisting)


def test_the_second_press_of_skip_does_nothing(enlisting):
    game = _game(enlisting, at="changshe")
    game.state.player.tutorial_step = len(guide.steps(game.state, enlisting))
    assert game.skip_tutorial()
    entries = len(game.state.journal)
    assert game.skip_tutorial() == [] and len(game.state.journal) == entries  # 沒有第二則「新手引導」紀錄


def test_skipping_stays_a_no_op_where_there_is_nothing_to_skip(enlisting):
    """真的沒有東西可以略過的時候照舊什麼都不做：第一季沒開（beta 季）、內容沒有入伍段（現在的正式內容）、入伍段早就走完。"""
    def idle(game):
        game.state.player.tutorial_step = len(guide.steps(game.state, enlisting))
        return game

    game = idle(_game(enlisting, at="changshe"))
    enlisting.config.season_one = False  # beta 季
    assert not enlist.waiting(game.state, enlisting)
    assert game.skip_tutorial() == [] and not game.state.player.guide_skipped
    enlisting.config.season_one = True
    saved, enlisting.tutorial.enlist = enlisting.tutorial.enlist, None  # 內容沒有入伍段
    assert not enlist.waiting(game.state, enlisting)
    assert game.skip_tutorial() == [] and not game.state.player.guide_skipped
    enlisting.tutorial.enlist = saved
    game.state.player.enlist_step = 2  # 走完了
    assert not enlist.waiting(game.state, enlisting)
    assert game.skip_tutorial() == [] and not game.state.player.guide_skipped


def test_a_skipper_from_before_the_enlist_content_never_gets_the_recruiters_hint_or_box(enlisting):
    """I2：內容還沒有入伍段時略過的人，`enlist.skip` 存的是 0（＝步數 0 的「走完」）；之後內容加了入伍段，0 不能被讀成
    「入伍段進行中、第一步」——不然他一投靠，「主線與目標」就永遠寫著「（老石）看看本週軍令」。"""
    saved, enlisting.tutorial.enlist = enlisting.tutorial.enlist, None
    game = _game(enlisting, at="changshe")
    game.state.player.tutorial_step = 1  # 新角色一開局已經站在序章之後（Game.new 不走草廬）；這裡要一個引導還沒走完的人
    assert game.skip_tutorial() and game.state.player.guide_skipped and game.state.player.enlist_step == 0
    enlisting.tutorial.enlist = saved  # 之後入伍段內容上線
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert not enlist.active(game.state, enlisting) and game.guide_box() is None
    assert "老石" not in game.quest_text()
    game.view_orders()
    assert game.guide_box() is None and "老石" not in game.quest_text()


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


def test_every_enlistment_box_says_it_is_never_cut_and_only_the_two_paragraph_step_is_paged(enlisting):
    """G2-W1（設計 6.2 對序章與入伍段：「話不會被切掉」）：引薦人的每個框都帶 full（網頁不套 FB-076 的三行收合）；入營＋看戰局兩段的第一步
    另外帶 paged（網頁照空一行分頁、一次一段，指示在最後一頁，跟師父的出師那一步同一個做法）。只有這兩個鍵：說書人的框不動。"""
    game = _joined(enlisting)
    box = game.guide_box()
    assert box["full"] is True and box["paged"] is True and box["text"].count("\n\n") == 1
    game.view_orders()
    box = game.guide_box()
    assert box["full"] is True and "paged" not in box  # 第二步只有一句
    event = next(iter(enlisting.events.values()))
    game.state.pending_event = event.id
    box = game.guide_box()  # 事件待處理：換成「先把眼前的…了結」（一行），網頁照舊預設收成一行；仍然不切
    assert box["pending"] is True and box["full"] is True and "paged" not in box
    game.state.pending_event = None
    game.state.player.enlist_step, game.state.player.enlist_end = 2, True
    box = game.guide_box()
    assert box["end"] is True and box["full"] is True and "paged" not in box
    narrator = _game(enlisting, at="changshe")
    narrator.state.player.tutorial_step = 1
    assert "full" not in narrator.guide_box() and "paged" not in narrator.guide_box()


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


def _told(game, name="老石"):
    """江湖紀錄（見聞）裡這位引薦人說過的話，照說的先後排：每一則 entry 的 guide 裡 `【名字】…` 的行。"""
    return [
        line for entry in reversed(game.state.journal) for line in entry.guide if line.startswith(f"【{name}】")
    ]


def test_the_recruiters_words_go_into_the_journal_once_each(enlisting):
    """設計 6.2「說過的話都記進見聞的江湖紀錄」：引薦人的話跟說書人的一樣，記在那一則的 guide（不進「剛剛」、不進對話框的完成列）。
    每一步的話在那一步成為眼前這一步的那一刻記一次：入營＋看戰局（投靠的那一下）、第一道軍令、結尾。"""
    from tianxia import journal

    game = _joined(enlisting)
    assert _told(game) == ["【老石】老石迎你進營。", "【老石】看這三條線。"]
    joined_entry = game.state.journal[0]
    assert "老石迎你進營" not in journal.card_html(joined_entry) and "老石迎你進營" in journal.rows_html([joined_entry])
    assert game.guide_box()["done"] == []  # 對話框的完成列只有 ✔ 與獎勵，不是引薦人的話
    game.view_orders()
    assert _told(game)[2:] == ["【老石】挑一道軍令。"]
    game.view_orders()  # 再看一次：這一步沒有往前，不重複記
    assert len(_told(game)) == 3
    _order(game, "siege", "guan", front="yingru")
    with _win():
        game.choose("act:train")
    assert _told(game)[3:] == ["【老石】做得好。"] and game.guide_box()["done"] == ["✔ 引導完成"]
    game.guide_ack()
    game.view_orders()
    assert len(_told(game)) == 4  # 按「知道了」、之後的行動都不再記


def test_a_recruiter_met_behind_the_tutorial_is_still_met_at_the_join(enlisting):
    """引導還沒走完就投靠：引薦人迎你進營是投靠那一刻的事，江湖紀錄記在那一刻；框上等說書人那一步走完才輪到他。
    框上沒有的 ✔ 也不會因此記進去。"""
    game = _joined_mid_tutorial(enlisting)
    assert _told(game) == ["【老石】老石迎你進營。", "【老石】看這三條線。"]
    game.view_orders()
    assert _told(game)[2:] == ["【老石】挑一道軍令。"]  # 進度照記，這一步的話也在它成為眼前這一步的那一刻記下
    assert not any(line.startswith("✔") for entry in game.state.journal for line in entry.guide)


def test_the_recruiters_words_do_not_wipe_the_narrators_check_rows(enlisting):
    """說書人的框上有上一次行動完成的 ✔ 與獎勵時，入伍段在背後往前一步（只寫引薦人的話進紀錄）不能把那些完成列清掉。"""
    game = _game(enlisting, at="changshe")
    game.state.player.tutorial_step = 1
    game.choose("faction:guan")
    game.choose("faction:confirm")
    game.state.player.guide_done = ["✔ 引導完成", "銀兩 +5"]
    game.view_orders()
    assert game.state.player.enlist_step == 1 and game.guide_box()["done"] == ["✔ 引導完成", "銀兩 +5"]


def test_a_skipped_guide_writes_no_recruiter_words(enlisting):
    game = _game(enlisting, at="changshe")
    game.skip_tutorial()
    game.choose("faction:guan")
    game.choose("faction:confirm")
    game.view_orders()
    assert _told(game) == []


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


def test_the_content_check_looks_at_each_enlist_steps_location_and_condition(enlisting):
    from tianxia.models import Condition

    validate(enlisting)
    step = enlisting.tutorial.enlist.steps[0]
    step.done_when = TutorialGoal(action="view_orders", locations=["mars"])
    with pytest.raises(ContentError, match="mars"):
        validate(enlisting)
    step.done_when = TutorialGoal(action="view_orders", condition=Condition(factions=["nowhere"]))
    with pytest.raises(ContentError, match="nowhere"):
        validate(enlisting)


def test_begin_if_joined_needs_a_recruiter_and_an_unskipped_guide(enlisting):
    game = _game(enlisting, faction="guan")
    p = game.state.player
    p.guide_skipped = True  # 略過過的人，投靠不開始
    assert not enlist.begin_if_joined(game.state, enlisting) and p.enlist_step is None
    p.guide_skipped = False
    recruiters = enlisting.tutorial.enlist.recruiters
    kept = recruiters.pop("guan")  # 這一邊沒有引薦人（內容沒寫）：沒有入伍段
    assert not enlist.begin_if_joined(game.state, enlisting) and p.enlist_step is None
    recruiters["guan"] = kept
    assert enlist.begin_if_joined(game.state, enlisting) and p.enlist_step == 0
    assert not enlist.begin_if_joined(game.state, enlisting)  # 已經開始過：不重開


def test_skipping_clears_an_ending_that_was_waiting(enlisting):
    """入伍段在引導還沒走完時就走完了（結尾等著、框上是說書人）：這時按「略過」，結尾也一起收掉。"""
    game = _game(enlisting, at="changshe")
    p = game.state.player
    p.tutorial_step = 1  # 引導還沒走完（Game.new 的新角色已經在序章之後）
    p.enlist_step, p.enlist_end = 2, True
    assert game.skip_tutorial()
    assert not p.enlist_end and p.enlist_step == 2 and game.guide_box() is None


def test_view_orders_is_a_main_action_that_the_season_pause_allows():
    """F6：軍令卡出現時網頁送 view_orders；賽季時鐘暫停中它跟 view_map 一樣只動自己的引導，不能被擋下（不然 S.ordersSeen 已經設了，
    這個工作階段不會再送）。"""
    import server

    assert "view_orders" in server.MAIN_ACTIONS and "view_orders" in server.PAUSE_OK_ACTIONS


# ── Task 2：舊存檔、換季、主線與目標 ─────────────────────────────────
# preflight F1：入伍段只在「這一下才投靠」的動作上開始（engine.Game._begin_enlistment），所以已經有陣營的人不會被「有陣營、入伍段還沒開始」
# 拖進來。換版當下就已經投靠的老手（設計 7.2「已經投靠的：不走入伍段」）另外在讀檔時蓋成「走完」（enlist.mark_veteran，認的是
# PlayerState.onboarding 的版本章：ONBOARDING_VERSION 升到 3＝有入伍段，比 3 小的是入伍段上線之前存的），要在換季清掉陣營之前蓋。


def test_a_joined_character_of_this_version_is_not_pulled_in_by_having_a_faction(enlisting, world):
    """換版之後才有陣營、入伍段卻沒開始的人（例如 beta 季投靠的）：讀檔、做任何行動都不會因為「有陣營、入伍段還沒開始」就被拖進入伍段
    （F1：只在「這一下才投靠」的動作上開始）。也不會被當成老手蓋成走完：他還沒走過，下一季投靠時照常走（見下面的測試）。"""
    from tianxia.engine import Game

    game = _game(enlisting, faction="guan", world=world)
    game.state.player.tutorial_step = len(guide.steps(game.state, enlisting))
    assert game.state.player.enlist_step is None and game.state.player.onboarding == ONBOARDING_VERSION
    again = Game(enlisting, game.state, world=world)
    assert again.state.player.enlist_step is None and again.guide_box() is None
    again.choose("act:rest")  # 之後做任何行動，也不會因為「有陣營、入伍段還沒開始」就被拖進入伍段
    assert again.state.player.enlist_step is None and again.guide_box() is None
    again.view_orders()
    assert again.state.player.enlist_step is None and not enlist.active(again.state, enlisting)


def _free_text_event(content, effect):
    """測試用的隨口應對事件：成功、失敗都套同一個效果（不看擲骰）。載入時的檢查不准隨口應對拜入門派，這裡直接塞進記憶體裡的內容。"""
    from tianxia.models import Choice, Event, FreeTextChoice

    event = Event(
        id="t_free", title="攔路", text="有人攔路。", actions=[], choices=[Choice(text="走開")],
        free_text=FreeTextChoice(prompt="自己想辦法……", stat="str", effect=effect, fail_effect=effect),
    )
    content.events[event.id] = event
    return event


def _answer(game, event, text="我上前理論"):
    game._present(event)
    request = game.free_text_request(text)
    assert request is not None
    return game.answer_event(request, llm_rate=50)


def test_old_saves_with_a_faction_are_not_pulled_in_by_a_free_text_answer(enlisting, world):
    """隨口應對（answer_event）也有一個開始入伍段的點：已經有陣營的人答完不會被拖進入伍段（F1 的另一半）。"""
    from tianxia.models import Effect

    game = _game(enlisting, faction="guan", world=world)
    game.state.player.tutorial_step = len(guide.steps(game.state, enlisting))
    _answer(game, _free_text_event(enlisting, Effect(stats={"str": 1})))
    assert game.state.player.enlist_step is None and game.guide_box() is None


def test_a_free_text_answer_that_joins_a_sect_starts_enlistment(enlisting, world):
    from tianxia.models import Effect

    game = _game(enlisting, at="cao_manor", world=world)
    game.state.player.tutorial_step = len(guide.steps(game.state, enlisting))
    _answer(game, _free_text_event(enlisting, Effect(join_sect="cao_manor")))
    assert game.state.player.faction == "haoqiang" and game.state.player.enlist_step == 0
    assert game.guide_box()["speaker"] == "季伯平"
    assert "【季伯平】季伯平迎你進營。" in game.state.journal[0].guide  # 跟投靠的那一下一樣記進這一則


def test_old_saves_without_a_faction_enlist_later(enlisting, world):
    from tianxia.engine import Game

    game = _game(enlisting, at="changshe", world=world)
    game.state.player.tutorial_step = len(guide.steps(game.state, enlisting))
    game.state.player.onboarding = 2  # 入伍段上線之前存的
    again = Game(enlisting, game.state, world=world)
    assert again.state.player.enlist_step is None and again.guide_box() is None
    assert again.state.player.onboarding == ONBOARDING_VERSION  # 讀檔蓋了新的章，沒投靠的人沒有東西好蓋
    again.choose("faction:guan")
    again.choose("faction:confirm")  # 還沒投靠的：第一次投靠時照常走入伍段（設計 7.2）
    assert again.state.player.enlist_step == 0 and again.guide_box()["speaker"] == "老石"


def _veteran(content, world, name="老手", **fields):
    """入伍段上線之前就投靠了官軍的角色：版本章是 2（序章那一版）、有陣營、入伍段沒有記。回傳 (遊戲, 存檔狀態)。"""
    game = _game(content, name, faction="guan", at="changshe", world=world)
    p = game.state.player
    p.tutorial_step, p.onboarding = len(guide.steps(game.state, content)), 2
    for key, value in fields.items():
        setattr(p, key, value)
    return game, game.state


def test_a_character_who_joined_before_enlistment_existed_is_marked_enlisted_when_loaded(enlisting, world):
    """設計 7.2「已經投靠的：不走入伍段」：換版當下就有陣營的角色，讀檔那一刻蓋成走完——沒有框、沒有紀錄裡的話。"""
    from tianxia.engine import Game

    _, state = _veteran(enlisting, world)
    journal_before = [list(entry.guide) for entry in state.journal]
    again = Game(enlisting, state, world=world)
    p = again.state.player
    assert p.enlist_step == len(enlisting.tutorial.enlist.steps) and not p.enlist_end and enlist.done(again.state, enlisting)
    assert again.guide_box() is None and [list(entry.guide) for entry in again.state.journal] == journal_before
    assert p.onboarding == ONBOARDING_VERSION


def test_a_veteran_loaded_mid_season_is_not_walked_through_it_when_he_rejoins_next_season(enlisting, world):
    from tianxia.engine import Game

    _, state = _veteran(enlisting, world)
    game = Game(enlisting, state, world=world)  # 這一季讀檔：蓋章
    game._reset_player_for_new_season(2)  # 換季：陣營清掉
    assert game.state.player.faction is None and enlist.done(game.state, enlisting)
    game.state.player.location = "changshe"
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert game.guide_box() is None and not any(line.startswith("【老石】") for e in game.state.journal for line in e.guide)


def test_a_veteran_first_loaded_after_the_season_already_changed_is_not_walked_through_it(enlisting, world):
    """換季的那一刻他沒在線，下次讀檔時陣營在同一次讀檔裡被換季清掉：蓋章要在換季之前（_drop_stale_references 一開頭），不然那時
    他已經認不出是老手了。走真的換季（管理者收季、開下一季）、真的讀檔。"""
    import random

    from tianxia.characters import open_characters
    from tianxia.engine import Game

    enlisting.config.auto_open_first_season, enlisting.config.admins = True, ["管"]
    chars = open_characters()
    admin = Game.new(enlisting, "管", rng=random.Random(1), world=world)
    _, state = _veteran(enlisting, world)
    for saved in (admin.state, state):
        chars.save(saved)
    admin.admin_end_season(now=100.0)
    admin.admin_next_season(now=200.0)
    loaded = Game(enlisting, chars.load("老手"), rng=random.Random(2), world=world)
    loaded.sync(300.0)
    assert loaded.state.player.season_number == 2 and loaded.state.player.faction is None  # 陣營被換季清掉了
    assert enlist.done(loaded.state, enlisting)
    loaded.state.player.location = "changshe"
    loaded.choose("faction:guan")
    loaded.choose("faction:confirm")
    assert loaded.guide_box() is None and enlist.done(loaded.state, enlisting)


def test_the_veteran_marking_leaves_everyone_else_alone(enlisting, world):
    """只認入伍段上線之前就投靠的人。沒投靠的老存檔（上面）照常走；走到一半的留著步數；略過的還是略過；換版之後才有陣營、
    入伍段沒開始的人（beta 季投靠）不是老手；內容沒有入伍段的話什麼都不蓋。"""
    from tianxia.engine import Game

    _, state = _veteran(enlisting, world, "半途", enlist_step=1)
    assert Game(enlisting, state, world=world).state.player.enlist_step == 1  # 走到一半：留著
    _, state = _veteran(enlisting, world, "略過", guide_skipped=True, enlist_step=0)  # 在還沒有入伍段的內容上略過的樣子（skip 存 0）
    again = Game(enlisting, state, world=world)
    assert again.state.player.guide_skipped and again.state.player.enlist_step == 0 and not enlist.active(again.state, enlisting)
    _, state = _veteran(enlisting, world, "新人")
    state.player.onboarding = ONBOARDING_VERSION  # 換版之後建的角色，在 beta 季投靠：入伍段沒開始
    again = Game(enlisting, state, world=world)
    assert again.state.player.enlist_step is None
    again._reset_player_for_new_season(2)  # 下一季（第一季）投靠時才走
    again.state.player.location = "changshe"
    again.choose("faction:guan")
    again.choose("faction:confirm")
    assert again.state.player.enlist_step == 0 and again.guide_box()["speaker"] == "老石"
    saved, enlisting.tutorial.enlist = enlisting.tutorial.enlist, None
    _, state = _veteran(enlisting, world, "無段")
    assert Game(enlisting, state, world=world).state.player.enlist_step is None  # 內容沒有入伍段：沒有東西好蓋
    enlisting.tutorial.enlist = saved


def test_a_character_made_while_joys_prologue_was_live_is_neither_converted_nor_sent_back(enlisting, world):
    """joy 的序章上線時建的角色版本章是 2（序章那一版）：還在草廬的留在草廬、步數不被換算（章 2 的步數已經是新編號）；沒投靠的讀檔後蓋成新章、
    投靠時照常走入伍段；已經投靠的當老手蓋成走完。"""
    import random

    from tianxia.engine import Game

    mid = Game.new(enlisting, "草廬裡", rng=random.Random(0), world=world, prologue=True)
    mid.state.player.tutorial_step, mid.state.player.onboarding = 5, 2
    again = Game(enlisting, mid.state, world=world)
    p = again.state.player
    assert (p.tutorial_step, p.location, p.onboarding, p.enlist_step) == (5, "mentor_hut", ONBOARDING_VERSION, None)
    out = Game.new(enlisting, "出了草廬", rng=random.Random(0), world=world)  # 走完序章、還沒投靠
    out.state.player.onboarding = 2
    again = Game(enlisting, out.state, world=world)
    assert again.state.player.enlist_step is None
    again.state.player.location = "changshe"
    again.choose("faction:guan")
    again.choose("faction:confirm")
    assert again.state.player.enlist_step == 0 and again.guide_box()["speaker"] == "老石"


def test_a_fresh_character_walks_the_enlistment_and_is_never_marked_as_a_veteran(enlisting, world):
    """換版之後建的角色版本章就是新的：投靠時照常走；之後讀檔、換季（沒走完的重來）都不會被蓋成老手。"""
    from tianxia.engine import Game

    game = _joined(enlisting)
    assert game.state.player.onboarding == ONBOARDING_VERSION and game.state.player.enlist_step == 0
    assert game.guide_box()["speaker"] == "老石"
    again = Game(enlisting, game.state, world=game.world)
    assert again.state.player.enlist_step == 0 and again.guide_box()["speaker"] == "老石"
    again._reset_player_for_new_season(2)
    assert again.state.player.enlist_step is None  # 沒走完就換季：下一季投靠從頭走


def test_raising_the_version_does_not_convert_the_step_numbers_again(enlisting, world):
    """版本章升到 3（有入伍段）之後，章是 2 的角色（序章那一版，步數已經是新編號）不能再被換算一次：prologue.migrated_step 認的是
    「序章那一版」（PROLOGUE_ONBOARDING，2），不是現在的版本。比 2 小的（舊的八步）照舊換算。"""
    from tianxia import prologue

    game, _ = _veteran(enlisting, world)
    p = game.state.player
    p.tutorial_step = 8
    assert prologue.PROLOGUE_ONBOARDING == 2 and ONBOARDING_VERSION == 3
    assert prologue.migrated_step(p, enlisting) == 8  # 章 2：已經是新編號
    p.onboarding = 1
    assert prologue.migrated_step(p, enlisting) == enlisting.tutorial.prologue_steps + (8 - prologue.OLD_BASE_STEPS)


def test_defecting_does_not_restart_enlistment(enlisting):
    """叛投：已經有陣營了，不重來；入伍段走完的人叛投之後仍是走完。"""
    game = _joined(enlisting)
    game.state.player.enlist_step, game.state.player.enlist_end = 2, False
    game.state.player.faction = "huang"  # 叛投之後（defection 本身不碰引導）
    assert not enlist.begin_if_joined(game.state, enlisting) and enlist.done(game.state, enlisting)


def test_finished_enlistment_survives_a_season(enlisting):
    game = _joined(enlisting)
    game.state.player.enlist_step = 2
    game._reset_player_for_new_season(2)
    assert game.state.player.enlist_step == 2
    game.state.player.location = "changshe"
    game.choose("faction:guan")
    game.choose("faction:confirm")  # 第二季再投靠：不重走（設計 7.1）
    assert game.state.player.faction == "guan"
    assert game.state.player.enlist_step == 2 and game.guide_box() is None


def test_unfinished_enlistment_restarts_next_season(enlisting):
    game = _joined(enlisting)
    game._reset_player_for_new_season(2)
    assert game.state.player.enlist_step is None
    game.state.player.location = "changshe"
    game.choose("faction:guan")
    game.choose("faction:confirm")  # 沒走完就換季：下一季投靠時從頭走
    assert game.state.player.faction == "guan"
    assert game.state.player.enlist_step == 0 and game.guide_box()["speaker"] == "老石"


def test_a_skipped_guide_stays_skipped_for_enlistment_next_season(enlisting):
    game = _game(enlisting, at="changshe")
    game.skip_tutorial()
    game._reset_player_for_new_season(2)
    assert enlist.done(game.state, enlisting) and game.state.player.guide_skipped
    game.state.player.location = "changshe"
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert game.state.player.faction == "guan" and game.guide_box() is None


def test_drifters_see_where_to_join(enlisting):
    game = _game(enlisting)
    game.state.player.tutorial_step = len(guide.steps(game.state, enlisting))
    assert "想投靠的話……" in game.quest_text()
    game = _joined(enlisting)
    assert "想投靠的話……" not in game.quest_text()


def test_the_where_to_join_line_waits_for_the_tutorial_and_season_one(enlisting):
    """主線與目標那一行（設計 4.1、6.3）：出師之後才有、寫在「下一步」前面；還在引導裡不寫；開關關著（beta 季）也不寫；
    drifter_line 是空的就不寫。"""
    game = _game(enlisting)
    game.state.player.tutorial_step = 1  # 引導還沒走完（Game.new 的新角色已經在序章之後）
    assert "想投靠的話……" not in game.quest_text()
    game.state.player.tutorial_step = len(guide.steps(game.state, enlisting))
    game.state.player.stamina = enlisting.config.stamina_max  # 讓「下一步」有一句（體力將滿）
    text = game.quest_text()
    assert "**投靠**：想投靠的話……" in text and text.index("**投靠**") < text.index("**下一步**")
    enlisting.tutorial.enlist.drifter_line = ""
    assert "**投靠**" not in game.quest_text()
    enlisting.tutorial.enlist.drifter_line = "想投靠的話……"
    enlisting.config.season_one = False
    assert "**投靠**" not in game.quest_text()
