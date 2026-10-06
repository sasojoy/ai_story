"""碰到才說（新手引導計畫三，Task 1）：提示的內容、排隊、對話框、知道了、不再提示、換季。

用 hints_content（測試內容加上 tests/fixtures/hints/hints.json 五條；說書人三步、結語「去闖吧。」；劇本有一個陣營 guan＝官軍）。
說過（hints_seen）與記進江湖紀錄都算在「提示上了框」的那一刻，不是排進佇列的那一刻（控制者裁示 N1、N12）。"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
from conftest import next_season
from tianxia import guide
from tianxia.content import ContentError, load_content
from tianxia.engine import Game
from tianxia.models import Enlist, EnlistStep, ExploreMix, HintDef, Hints, Recruiter, TutorialGoal
from tianxia.state import BotProfile, HintNote, PlayerState

MENTOR = "想起師父說過"


@pytest.fixture
def game(hints_content, world):
    return Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)


def _journal_guides(game):
    return [line for entry in game.state.journal for line in entry.guide]


def _enlist(content):
    """測試內容沒有入伍段：補一個，官軍的引薦人叫老石（有引薦人時，陣營的提示由他說）。"""
    content.tutorial.enlist = Enlist(
        steps=[EnlistStep(id="r1", done_when=TutorialGoal(action="view_orders"))],
        recruiters={"guan": Recruiter(name="老石", intro="進營。", briefing="看。", order_hint="做。", done="好。", lines=["看看"])},
    )


# ── 內容與模型 ─────────────────────────────────────────


def test_content_without_hints_has_an_empty_hint_book(content):
    assert content.hints.hints == [] and content.hints.head == MENTOR and content.hints.season_return == ""


def test_the_hint_book_is_loaded(hints_content):
    book = hints_content.hints
    assert [h.id for h in book.hints] == ["h_merge", "h_cap", "h_lose", "h_foreshadow", "h_promotion"]
    assert book.season_return == "又是一年。"
    assert book.hints[3].texts == {"guan": "這是線索（官軍）。"} and book.hints[3].drifter == "這是線索（散人）。"


def _reload(hints_root, change):
    path = hints_root / "hints.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return load_content(hints_root)


@pytest.mark.parametrize("change, message", [
    (lambda d: d["hints"].append({"id": "h_merge", "by": "mentor", "text": "再說一次。"}), "重複"),
    (lambda d: d["hints"].append({"id": "h_made_up", "by": "mentor", "text": "沒有這一條。"}), "不認得"),
    (lambda d: d["hints"][0].update(text=""), "要有 text"),
    (lambda d: d["hints"][3].update(texts={}), "要有 texts"),
    (lambda d: d["hints"][3].update(texts={"nobody": "誰說的？"}), "不是劇本陣營"),
    (lambda d: d["hints"][3].update(texts={"guan": ""}), "空的"),
    (lambda d: d["hints"][0].update(texts={"guan": "不該寫在師父的條上。"}), "師父"),
    (lambda d: d["hints"][4].update(text="不該寫在引薦人的條上。"), "引薦人"),
    (lambda d: d.update(head=""), "head"),
])
def test_a_bad_hint_book_is_refused_at_load(hints_root, change, message):
    with pytest.raises(ContentError, match=message):
        _reload(hints_root, change)


def test_every_known_hint_id_is_one_of_the_eighteen():
    from tianxia import hints

    assert len(hints.KNOWN) == 18 and {"h_snubbed", "h_mandate", "h_merge", "h_figure"} <= hints.KNOWN


# ── 排隊與對話框 ───────────────────────────────────────


def test_a_hint_shows_once_with_the_mentor_head(game):
    game.skip_tutorial()  # 測試內容的引導（說書人三步）不擋在前面
    game._hint("h_merge")
    box = game.guide_box()
    assert (box["speaker"], box["text"], box["end"], box["key"], box["pending"]) == (MENTOR, "意境可以合。", True, "h_merge", False)
    assert box["scene"] == "" and box["line"] == "" and box["done"] == []
    assert box["full"] is True  # 話不被切掉（設計 6.2）
    game.guide_ack()
    assert game.guide_box() is None
    game._hint("h_merge")
    assert game.guide_box() is None  # 只說一次


def test_skipping_the_guide_still_shows_hints(game):
    game.skip_tutorial()
    assert game.state.player.guide_skipped
    game._hint("h_lose")
    assert game.guide_box()["text"] == "打不過就回去練。"


def test_hints_wait_behind_the_tutorial(game):
    game._hint("h_merge")
    assert game.guide_box()["speaker"] == "說書人"  # 引導還沒走完
    p = game.state.player
    assert [n.id for n in p.hint_queue] == ["h_merge"]
    assert "h_merge" not in p.hints_seen  # 還沒上框：不算說過（N1）


def test_the_queue_holds_each_hint_once(game):
    game._hint("h_merge")
    game._hint("h_merge")
    assert [n.id for n in game.state.player.hint_queue] == ["h_merge"]


def test_two_hints_come_one_at_a_time(game):
    game.skip_tutorial()
    game._hint("h_merge")
    game._hint("h_lose")
    p = game.state.player
    assert [n.id for n in p.hint_queue] == ["h_merge", "h_lose"]
    assert game.guide_box()["key"] == "h_merge"
    assert "h_lose" not in p.hints_seen  # 排在後面、還沒上框
    game.guide_ack()
    assert game.guide_box()["key"] == "h_lose" and "h_lose" in p.hints_seen
    game.guide_ack()
    assert game.guide_box() is None and p.hint_queue == []


def test_a_hint_counts_as_said_when_the_box_shows_not_when_queued(game):
    p = game.state.player
    game._hint("h_merge")  # 說書人還在框上
    assert "h_merge" not in p.hints_seen and "【想起師父說過】意境可以合。" not in _journal_guides(game)
    p.tutorial_step = len(guide.steps(game.state, game.content))  # 引導走完了（結語沒有，直接略過這一段）
    game.sync(1000.0)  # 同步的時候輪到它上框
    assert game.guide_box()["key"] == "h_merge" and "h_merge" in p.hints_seen
    assert _journal_guides(game).count("【想起師父說過】意境可以合。") == 1


def test_a_shown_hint_is_written_to_the_journal_once(game):
    """N12：說過的話記進見聞（設計 6.2），上框的那一刻記一次——重畫、按「知道了」、再排一次都不重複。"""
    game.skip_tutorial()
    game._hint("h_merge")
    assert "【想起師父說過】意境可以合。" in game.state.journal[0].guide
    game.sync(1000.0)
    game.guide_ack()
    game._hint("h_merge")
    assert _journal_guides(game).count("【想起師父說過】意境可以合。") == 1


def _event_pending(game):
    """探索一定撞上事件（測試內容的事件，選項 choice:1 了結它）。"""
    game.content.config.explore_mix = [ExploreMix(kind="wild", tags=[], weights={"event": 1})]
    game.choose("act:explore")
    assert game.state.pending_event is not None


def test_a_hint_waits_while_an_event_is_pending_then_shows_when_it_is_settled(game):
    """F3：事件還沒了結時，提示的框不出現（它會把事件的最後一個選項擠出第一屏，FB-076）；事件了結的那一下上框。"""
    game.skip_tutorial()
    _event_pending(game)
    game._hint("h_merge")
    p = game.state.player
    assert game.guide_box() is None and [n.id for n in p.hint_queue] == ["h_merge"] and "h_merge" not in p.hints_seen
    game.guide_ack()  # 框上沒有提示：什麼都不收
    assert [n.id for n in p.hint_queue] == ["h_merge"]
    game.choose("choice:1")
    assert game.state.pending_event is None
    assert game.guide_box()["key"] == "h_merge" and "h_merge" in p.hints_seen
    assert "【想起師父說過】意境可以合。" in game.state.journal[0].guide  # 記在了結事件的這一則


def test_a_free_text_answer_that_settles_the_event_shows_the_waiting_hint(game):
    """隨口應對（answer_event）了結事件，跟選了選項一樣：排著的提示在這一下上框、記在這一則。"""
    from tianxia.models import Effect, FreeTextChoice

    game.skip_tutorial()
    game.content.events["drunk"].free_text = FreeTextChoice(
        prompt="自己想辦法……", stat="str", by="self", effect=Effect(text="醉漢被你唬住了。"), fail_effect=Effect(text="醉漢一拳揮來。"),
    )
    game.state.pending_event = "drunk"
    game._hint("h_merge")
    assert game.guide_box() is None
    game.answer_event(game.free_text_request("把酒罈砸在地上"), 60)
    assert game.state.pending_event is None
    assert game.guide_box()["key"] == "h_merge" and "h_merge" in game.state.player.hints_seen
    assert f"【{MENTOR}】意境可以合。" in game.state.journal[0].guide


def test_ack_takes_only_the_box_that_is_showing(game):
    """F4：步驟 → 結語 → 入伍段 → 提示，框上是哪一個，「知道了」就只收哪一個。"""
    p = game.state.player
    p.tutorial_step = len(guide.steps(game.state, game.content))
    p.guide_outro = True
    game._hint("h_merge")
    assert game.guide_box()["text"] == "去闖吧。"  # 結語在提示前面
    game.guide_ack()
    assert not p.guide_outro and [n.id for n in p.hint_queue] == ["h_merge"]
    assert game.guide_box()["key"] == "h_merge"
    game.guide_ack()
    assert p.hint_queue == [] and game.guide_box() is None


def test_ack_clears_the_enlistment_ending_before_a_hint(hints_content, world):
    _enlist(hints_content)
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    p = game.state.player
    p.tutorial_step = len(guide.steps(game.state, game.content))
    p.faction, p.enlist_step, p.enlist_end = "guan", 1, True
    game._hint("h_merge")
    assert game.guide_box()["key"] == "enlist_end"  # 入伍段的結尾在提示前面
    game.guide_ack()
    assert not p.enlist_end and [n.id for n in p.hint_queue] == ["h_merge"]
    assert game.guide_box()["key"] == "h_merge"
    game.guide_ack()
    assert game.guide_box() is None


def test_hints_wait_behind_the_enlistment(hints_content, world):
    _enlist(hints_content)
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    p = game.state.player
    p.tutorial_step = len(guide.steps(game.state, game.content))
    p.faction, p.enlist_step = "guan", 0  # 入伍段進行中
    game._hint("h_merge")
    assert game.guide_box()["speaker"] == "老石"
    assert "h_merge" not in p.hints_seen


def test_no_hint_box_while_the_season_is_not_running(game):
    game.skip_tutorial()
    game._hint("h_merge")
    game.state.world.ended = True
    assert game.guide_box() is None


# ── 誰說 ──────────────────────────────────────────────


def test_recruiter_hint_without_a_drifter_version_is_kept_for_later(game):
    game.skip_tutorial()
    game._hint("h_promotion")  # 散人：沒有散人版
    assert game.guide_box() is None and "h_promotion" not in game.state.player.hints_seen
    assert game.state.player.hint_queue == []


def test_a_drifter_hears_the_mentor_version(game):
    game.skip_tutorial()
    game._hint("h_foreshadow")
    box = game.guide_box()
    assert (box["speaker"], box["text"]) == (MENTOR, "這是線索（散人）。")


def test_a_recruiter_hint_is_said_by_the_faction_with_its_name(game):
    game.skip_tutorial()
    game.state.player.faction = "guan"
    game._hint("h_foreshadow")
    box = game.guide_box()
    assert (box["speaker"], box["text"]) == ("官軍", "這是線索（官軍）。")  # 測試內容沒有引薦人：用陣營名


def test_a_recruiter_hint_is_said_by_the_recruiter(hints_content, world):
    _enlist(hints_content)
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    game.state.player.faction = "guan"
    game._hint("h_promotion")
    box = game.guide_box()
    assert (box["speaker"], box["text"]) == ("老石", "上頭點你的名了。")


def test_a_note_is_fixed_when_it_is_queued(game):
    """排進去的當下就決定誰說、說什麼：之後投靠了，排著的那一條還是師父講的散人版。"""
    game.skip_tutorial()
    game._hint("h_merge")
    game._hint("h_foreshadow")
    game.state.player.faction = "guan"
    game.guide_ack()
    box = game.guide_box()
    assert (box["speaker"], box["text"]) == (MENTOR, "這是線索（散人）。")


def test_unknown_or_missing_hints_are_ignored(game):
    from tianxia import hints

    game.skip_tutorial()
    assert hints.note_for(game.state, game.content, "h_not_there") is None
    game._hint("h_not_there")
    assert game.state.player.hint_queue == [] and game.guide_box() is None


def test_bots_queue_nothing(game):
    game.skip_tutorial()
    game.state.player.bot = BotProfile(personality="普通", seed=1)
    game._hint("h_merge")
    assert game.state.player.hint_queue == [] and "h_merge" not in game.state.player.hints_seen


# ── 不再提示 ──────────────────────────────────────────


def test_hints_off_clears_and_stops(game):
    game.skip_tutorial()
    game._hint("h_merge")  # 上了框（說過）
    game._hint("h_lose")  # 排在後面、還沒上框
    game.set_hints_off(True)
    p = game.state.player
    assert p.hints_off and game.guide_box() is None and p.hint_queue == []
    game._hint("h_cap")
    assert "h_cap" not in p.hints_seen and p.hint_queue == []
    assert "h_lose" not in p.hints_seen  # 沒上過框的不算說過：關掉再打開還有機會聽到（Review Focus 3）
    game.set_hints_off(False)
    game._hint("h_lose")
    assert game.guide_box()["text"] == "打不過就回去練。"


def test_hints_off_does_not_touch_the_tutorial(game):
    game.set_hints_off(True)
    assert game.guide_box()["speaker"] == "說書人"


# ── 換季 ──────────────────────────────────────────────


def test_season_change_keeps_seen_and_sends_you_off(hints_content, world):
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    game._hint("h_merge")
    game.guide_ack()
    game._hint("h_lose")  # 上了框、還沒按「知道了」
    game._hint("h_cap")  # 排在後面、還沒上框
    next_season(hints_content, world, game)
    p = game.state.player
    assert p.hints_seen == {"h_merge", "h_lose"}  # 說過的保留；排著沒看的不算說過
    assert [n.text for n in p.hint_queue] == ["又是一年。"]  # 排著的清掉，換成送下山那一句
    assert p.hint_queue[0].speaker == MENTOR
    game._hint("h_cap")  # 沒說過的，這一季碰到還是會說
    assert [n.id for n in p.hint_queue] == ["s_return", "h_cap"]


def test_the_send_off_is_shown_and_written_down(hints_content, world):
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    next_season(hints_content, world, game)
    box = game.guide_box()
    assert (box["speaker"], box["text"], box["key"], box["end"]) == (MENTOR, "又是一年。", "s_return", True)
    assert "【想起師父說過】又是一年。" in _journal_guides(game)
    game.guide_ack()
    assert game.guide_box() is None and game.state.player.hint_queue == []


def test_the_send_off_comes_every_season_not_once(hints_content, world):
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    next_season(hints_content, world, game)
    game.guide_ack()
    admin = Game.new(hints_content, "管理者", rng=random.Random(1), world=world)
    admin.admin_end_season(now=500.0)
    admin.admin_next_season(now=600.0)
    game.sync(700.0)
    assert game.state.player.season_number == 3
    assert [n.id for n in game.state.player.hint_queue] == ["s_return"]
    assert "【想起師父說過】又是一年。" in _journal_guides(game)


def test_no_send_off_before_the_guide_is_done(hints_content, world):
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)  # 說書人三步沒走完
    next_season(hints_content, world, game)
    assert game.state.player.hint_queue == []


def test_no_send_off_when_hints_are_off_or_for_bots(hints_content, world):
    off = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    off.skip_tutorial()
    off.set_hints_off(True)
    bot = Game.new(hints_content, "假人", rng=random.Random(0), world=world)
    bot.skip_tutorial()
    bot.state.player.bot = BotProfile(personality="普通", seed=1)
    next_season(hints_content, world, off, bot)
    assert off.state.player.hint_queue == [] and off.state.player.hints_off  # 開關帶到下一季
    assert bot.state.player.hint_queue == []


def test_no_send_off_when_the_book_has_none(hints_root, world):
    content = _reload(hints_root, lambda d: d.update(season_return=""))
    game = Game.new(content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    next_season(content, world, game)
    assert game.state.player.hint_queue == []


# ── 存檔 ──────────────────────────────────────────────


def test_hint_state_survives_a_save(game):
    game.skip_tutorial()
    game._hint("h_merge")
    game._hint("h_lose")
    game.set_hints_off(False)
    p = game.state.player
    again = PlayerState.model_validate_json(p.model_dump_json())
    assert again.hints_seen == p.hints_seen == {"h_merge"}
    assert [(n.id, n.shown) for n in again.hint_queue] == [("h_merge", True), ("h_lose", False)]


def test_an_old_save_without_hint_fields_loads_with_empty_ones(game):
    data = game.state.player.model_dump()
    for key in ("hints_seen", "hint_queue", "hints_off"):
        data.pop(key)
    old = PlayerState.model_validate(data)
    assert old.hints_seen == set() and old.hint_queue == [] and old.hints_off is False


def test_status_data_carries_the_switch(game):
    assert game.status_data()["hints_off"] is False
    game.set_hints_off(True)
    assert game.status_data()["hints_off"] is True


def test_the_settings_sheet_has_the_switch_and_sends_hints_off():
    """設定抽屜的「不再提示」（網頁沒有建置步驟、沒有前端測試：這裡只看原始碼有接上，node --check 另外擋語法）。"""
    src = (Path(__file__).parent.parent / "web" / "app.js").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert 'id="hints-off" ${s.hints_off ? "checked" : ""}> 不再提示（碰到新玩法時的小提醒）' in src
    assert 'ev.target.id === "hints-off") await doMain("hints_off", { value: ev.target.checked })' in src
    assert src.index("略過新手引導</button>") < src.index('id="hints-off"')  # 在「略過新手引導」下面


def test_hint_note_and_hint_def_shapes():
    note = HintNote(id="h_merge", speaker=MENTOR, text="話。")
    assert note.shown is False
    hint = HintDef(id="h_foreshadow", by="recruiter")
    assert hint.texts == {} and hint.drifter == "" and hint.text == ""
    assert Hints().hints == [] and Hints().season_return == ""
