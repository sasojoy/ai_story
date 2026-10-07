"""碰到才說（新手引導計畫三，Task 1、2）：提示的內容、排隊、對話框、知道了、不再提示、換季；什麼時候說（觸發條件）。

用 hints_content（測試內容加上 tests/fixtures/hints/hints.json 五條；說書人三步、結語「去闖吧。」；劇本有一個陣營 guan＝官軍）。
說過（hints_seen）與記進江湖紀錄都算在「提示上了框」的那一刻，不是排進佇列的那一刻（控制者裁示 N1、N12）。"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
from conftest import FixedRandom, next_season
from test_cultivation import kicker_art
from test_practice_hardening import harden
from tests.test_orders import _game as _real_game  # 真內容的 real、on 是 tests/conftest.py 的 fixture（每個測試自己的一份複本）
from tianxia import defection, guide
from tianxia.content import ContentError, load_content
from tianxia.engine import Game
from tianxia.models import Effect, Enlist, EnlistStep, ExploreMix, FreeTextChoice, HintDef, Hints, Recruiter, TutorialGoal
from tianxia.state import BattleRecord, BotProfile, Fighter, HintNote, PlayerState, Summons

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


def _finished(content, world, name="沈浪"):
    """走完引導的角色（不是略過）：只有走完的人，下一季開季時師父才送行（控制者裁示：略過的人沒有要人帶，不送）。
    測試內容沒有序章，「走完」就是說書人那三步做完（tutorial_step 等於步數）。"""
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.state.player.tutorial_step = len(guide.steps(game.state, game.content))
    assert not game.state.player.guide_skipped
    return game


def test_season_change_keeps_seen_and_sends_you_off(hints_content, world):
    game = _finished(hints_content, world)
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
    game = _finished(hints_content, world)
    next_season(hints_content, world, game)
    box = game.guide_box()
    assert (box["speaker"], box["text"], box["key"], box["end"]) == (MENTOR, "又是一年。", "s_return", True)
    assert "【想起師父說過】又是一年。" in _journal_guides(game)
    game.guide_ack()
    assert game.guide_box() is None and game.state.player.hint_queue == []


def test_the_send_off_comes_every_season_not_once(hints_content, world):
    game = _finished(hints_content, world)
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


def test_no_send_off_for_someone_who_skipped_the_guide(hints_content, world):
    """控制者裁示：略過新手引導的人沒有要誰帶，師父不送他下山（他們照樣有碰到才說，換季也帶著說過的）。"""
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    game._hint("h_merge")
    game.guide_ack()
    next_season(hints_content, world, game)
    p = game.state.player
    assert p.guide_skipped and p.hint_queue == [] and p.hints_seen == {"h_merge"}
    assert game.guide_box() is None


def test_no_send_off_when_hints_are_off_or_for_bots(hints_content, world):
    """這兩個負向測試要真的守住條件：造的是「走完」的角色，除了開關與假人身分之外跟會被送行的一模一樣。"""
    off = _finished(hints_content, world)
    off.set_hints_off(True)
    bot = _finished(hints_content, world, "假人")
    bot.state.player.bot = BotProfile(personality="普通", seed=1)
    ok = _finished(hints_content, world, "對照")
    next_season(hints_content, world, off, bot, ok)
    assert [n.id for n in ok.state.player.hint_queue] == ["s_return"]  # 對照組：同樣走完、沒關、不是假人，收到
    assert off.state.player.hint_queue == [] and off.state.player.hints_off  # 開關帶到下一季
    assert bot.state.player.hint_queue == []


def test_no_send_off_when_the_book_has_none(hints_root, world):
    content = _reload(hints_root, lambda d: d.update(season_return=""))
    game = _finished(content, world)
    game._hint("h_merge")  # 排著還沒按「知道了」的，換季不帶：書裡沒有送行的話，新的一季佇列就是空的
    assert [n.id for n in game.state.player.hint_queue] == ["h_merge"]
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
    assert note.by == "" and HintNote(id="h_x", speaker="老石", text="話。", by="guan").by == "guan"


# ── Task 2：什麼時候說（觸發條件，設計 5.2 的十八條）────────────────────────────
# 觸發看的是角色「此刻的狀態」（第一次由 hints_seen 管）；排隊的規矩（控制者裁示 N2）：一次檢查最多排一條狀態提示，
# 事件型的（h_snubbed、s_rejoin、s_return、h_mandate）當場排。


def _with(content, *ids):
    """hints_content 只有五條：這些測試多用到的條，直接補一條師父說的。"""
    for hint_id in ids:
        content.hints.hints.append(HintDef(id=hint_id, by="mentor", text=f"{hint_id} 的話"))


def _key(game):
    box = game.guide_box()
    return None if box is None else box["key"]


def _queued(game):
    return [n.id for n in game.state.player.hint_queue]


def _lost_fight(kind="train", tier="落敗"):
    return BattleRecord(
        id=1, time=0.0, location="小鎮", kind=kind, opponent="山賊", ours=[Fighter(name="沈浪", level=1)], tier=tier,
        our_power=1.0, difficulty=9.0,
    )


def test_second_insight_triggers_merge(game):
    game.skip_tutorial()
    game.state.player.insights = ["feng"]
    game._check_hints()
    assert game.guide_box() is None
    game.state.player.insights = ["feng", "huo"]
    game._check_hints()
    assert _key(game) == "h_merge"


def test_clash_when_inner_and_outer_arts_counter_each_other(game):
    _with(game.content, "h_clash")
    game.skip_tutorial()
    member = game.state.player.member
    member.neigong_id, member.wugong_id = "calm", "fist"  # 虛／剛：不相剋
    game._check_hints()
    assert game.guide_box() is None
    member.wugong_id = "basic_fist"  # 虛／實：相剋
    game._check_hints()
    assert _key(game) == "h_clash"


def test_clash_needs_both_arts(game):
    _with(game.content, "h_clash")
    game.skip_tutorial()
    member = game.state.player.member
    member.neigong_id, member.wugong_id = None, "basic_fist"
    game._check_hints()
    assert game.guide_box() is None and _queued(game) == []


def test_a_failed_refinement_triggers_refine_fail(game):
    _with(game.content, "h_refine_fail")
    game.skip_tutorial()
    game.state.player.art_mastery = {"basic_fist": 0}  # 成功就歸零
    game._check_hints()
    assert game.guide_box() is None
    game.state.player.art_mastery = {"basic_fist": 2}
    game._check_hints()
    assert _key(game) == "h_refine_fail"


def _tempering_game(hints_content, world):
    """joy 的加難（方案 C，breakthrough.heat = 8，跟正式內容一樣）：上品、第十成的【旋風腿】，下一次修練是往絕學添火候。"""
    c = harden(hints_content)
    _with(c, "h_refine_fail")
    game = Game.new(c, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    world.claim_skill_name(kicker_art())
    p = game.state.player
    p.arts, p.insights, p.stamina, p.location = ["旋風腿"], ["feng"], 150, "cave"
    p.art_levels["旋風腿"], p.art_quality["旋風腿"] = 10, "上品"
    return game


def test_tempering_toward_mastery_is_not_a_failed_refinement(hints_content, world):
    """往絕學修練只添火候（cultivation._temper，也記在 art_mastery），不擲骰、沒有失敗：師父不說「沒成也不白修」（整合審查 I1）。"""
    game = _tempering_game(hints_content, world)
    assert game.cultivate("旋風腿")[0].startswith("【旋風腿】又添了一分火候")
    assert game.state.player.art_mastery["旋風腿"] == 1
    assert "h_refine_fail" not in _queued(game) and _key(game) != "h_refine_fail"


def test_a_real_failure_on_the_way_to_upper_grade_still_says_it(hints_content, world):
    """同樣的加難設定，往上品修練真的擲骰失敗了：照舊說（art_mastery 記的是失敗幾次）。"""
    game = _tempering_game(hints_content, world)
    game.state.player.art_quality["旋風腿"] = "中品"
    for _ in range(5):
        game.cultivate("旋風腿")
        if game.state.player.art_mastery.get("旋風腿", 0) > 0:
            break
    assert game.state.player.art_quality["旋風腿"] == "中品" and game.state.player.art_mastery["旋風腿"] > 0
    assert _key(game) == "h_refine_fail"


def test_a_lost_fight_triggers_lose_but_a_win_or_a_lost_showdown_does_not(game):
    """（落敗；僵持也算，見下一個測試。）"""
    game.skip_tutorial()
    for record in (_lost_fight(tier="大勝"), _lost_fight(kind="showdown")):
        game.state.battles = [record]
        game._check_hints()
        assert game.guide_box() is None
    for kind in ("train", "wild", "event"):
        game.state.battles = [_lost_fight(kind=kind)]
        game.state.player.hints_seen.discard("h_lose")
        game._check_hints()
        assert _key(game) == "h_lose", kind
        game.guide_ack()


@pytest.mark.parametrize("kind", ["train", "wild", "event"])
def test_the_first_fight_you_did_not_win_triggers_lose_even_when_it_is_only_a_draw(game, kind):
    """h_lose 是「第一場沒打贏的仗」：僵持與落敗都算（FB-095 旁的規劃者決定；以前只有落敗，被閃成僵持的人師父不開口）。"""
    game.skip_tutorial()
    game.state.battles = [_lost_fight(kind=kind, tier="險勝")]  # 險勝是贏
    game._check_hints()
    assert game.guide_box() is None
    game.state.battles = [_lost_fight(kind=kind, tier="僵持")]
    game._check_hints()
    assert _key(game) == "h_lose" and "h_lose" in game.state.player.hints_seen


def test_a_real_draw_from_a_dodge_in_a_travelling_fight_brings_the_mentor(on):
    """整條路：真的遊歷、結果被身法閃成僵持（team.fight 寫死），行動做完師父就開口。"""
    from unittest import mock

    from tianxia import team
    from tianxia.encounter import EncounterResult
    from tests.test_orders import _game as _fresh

    game = _fresh(on, at="huangjin_camp")
    game.skip_tutorial()
    assert game.guide_box() is None
    draw = EncounterResult(tier="僵持", margin=-10, our_power=10, difficulty=60)
    with mock.patch.object(team, "fight", return_value=draw):
        game.choose("act:train")
    assert game.state.battles[-1].tier == "僵持"
    assert _key(game) == "h_lose"


def test_a_draw_after_a_win_still_counts_and_a_second_non_win_is_not_said_again(game):
    game.skip_tutorial()
    game.state.battles = [_lost_fight(tier="大勝"), _lost_fight(tier="僵持")]
    game._check_hints()
    assert _key(game) == "h_lose"
    game.guide_ack()
    game.state.battles.append(_lost_fight(tier="落敗"))  # 第二場沒打贏的：只說一次
    game._check_hints()
    assert game.guide_box() is None and _queued(game) == []


def test_an_injury_triggers_injury(game):
    _with(game.content, "h_injury")
    game.skip_tutorial()
    game.state.player.member.injury = 10
    game._check_hints()
    assert _key(game) == "h_injury"


def test_a_place_that_teaches_a_basic_art_triggers_basic_art(game):
    _with(game.content, "h_basic_art")
    game.skip_tutorial()
    game._check_hints()  # 小鎮不教
    assert game.guide_box() is None
    game.state.player.location = "lake"  # 湖邊教湖邊腿法
    game._check_hints()
    assert _key(game) == "h_basic_art"


def test_basic_art_only_counts_a_lesson_the_player_can_actually_learn(game):
    """「這裡能學新的底」：這裡教、可是現在學不了的（名望不夠、學費不夠、持有滿了）不算——不然師父說「能學」，按下去卻是一句「學不了」。
    學得了的那一刻才說。"""
    from tianxia.models import LearnRule

    _with(game.content, "h_basic_art")
    game.skip_tutorial()
    p = game.state.player
    p.location = "lake"
    lesson = game.content.skills["lake_kick"]
    lesson.learn = LearnRule(at="lake", silver=10, fame=5)  # 名望 5 以上才肯教
    game._check_hints()
    assert game.guide_box() is None and _queued(game) == []
    p.stats["fame"] = 5
    game._check_hints()
    assert _key(game) == "h_basic_art"


def test_basic_art_waits_while_the_library_is_full_or_the_purse_is_short(game, monkeypatch):
    from tianxia import library

    _with(game.content, "h_basic_art")
    game.skip_tutorial()
    p = game.state.player
    p.location = "lake"
    p.stats["silver"] = 3  # 學費 10 兩
    game._check_hints()
    assert game.guide_box() is None
    p.stats["silver"] = 50
    monkeypatch.setattr(library, "cap_of", lambda s, c: library.held_count(s))  # 滿了（這時師父說的是「快滿了」，不是「能學」）
    game._check_hints()
    assert "h_basic_art" not in _queued(game)
    monkeypatch.undo()
    game.state.player.hint_queue = []  # 滿了那一條按掉
    game._check_hints()
    assert _key(game) == "h_basic_art"


def test_a_recruitable_character_here_triggers_recruit(game):
    _with(game.content, "h_recruit")
    game.skip_tutorial()
    game._check_hints()  # 小鎮有三位可招募的人
    assert _key(game) == "h_recruit"


def test_a_free_text_event_triggers_the_hint_once_the_event_is_settled(game):
    """事件還擺在眼前時提示排著等（F3）：了結之後才上框。"""
    _with(game.content, "h_free_text")
    game.skip_tutorial()
    game.content.events["drunk"].free_text = FreeTextChoice(
        prompt="自己想辦法……", stat="str", by="self", effect=Effect(text="成了。"), fail_effect=Effect(text="敗了。"),
    )
    game.state.pending_event = "drunk"
    game._check_hints()
    assert _queued(game) == ["h_free_text"] and game.guide_box() is None
    game.state.pending_event = None
    assert _key(game) == "h_free_text"


def test_an_event_without_free_text_does_not_trigger_it(game):
    _with(game.content, "h_free_text")
    game.skip_tutorial()
    game.state.pending_event = "drunk"
    game._check_hints()
    assert _queued(game) == []


def test_a_road_sight_triggers_road(game):
    _with(game.content, "h_road")
    game.skip_tutorial()
    game._check_hints()
    assert game.guide_box() is None
    game.state.player.recent_sights = ["a_sight"]
    game._check_hints()
    assert _key(game) == "h_road"


def test_a_nearly_full_library_triggers_cap(game, monkeypatch):
    from tianxia import library

    game.skip_tutorial()
    game._check_hints()
    assert game.guide_box() is None
    monkeypatch.setattr(library, "cap_of", lambda s, c: library.held_count(s) + 6)  # 還差六個：44／50，還早
    game._check_hints()
    assert game.guide_box() is None and _queued(game) == []
    monkeypatch.setattr(library, "cap_of", lambda s, c: library.held_count(s) + 5)  # 還差五個：45／50
    game._check_hints()
    assert _key(game) == "h_cap"


def test_a_full_library_still_triggers_cap(game, monkeypatch):
    """滿了（或博聞被扣下來超過上限）更該說：條件是「差不到五個」，不是剛好五個。"""
    from tianxia import library

    game.skip_tutorial()
    monkeypatch.setattr(library, "cap_of", lambda s, c: library.held_count(s) - 2)
    game._check_hints()
    assert _key(game) == "h_cap"


def test_a_drifter_who_heard_a_hint_does_not_hear_it_again_after_joining(game):
    """設計 5.2：散人聽過伏筆的提示（師父講的散人版）之後才投靠，引薦人不再講同一條。"""
    game.skip_tutorial()
    game.state.player.fragments = {"chain": [0]}
    game._check_hints()
    assert game.guide_box()["text"] == "這是線索（散人）。"
    game.guide_ack()
    game.state.player.faction = "guan"
    game._check_hints()
    assert game.guide_box() is None and _queued(game) == []


def test_a_saved_note_without_by_loads_as_the_mentors():
    old = PlayerState.model_validate({
        **PlayerState(name="甲", location="town", stats={}, stamina=0).model_dump(),
        "hint_queue": [{"id": "h_merge", "speaker": MENTOR, "text": "話。", "shown": True}],
    })
    assert old.hint_queue[0].by == ""  # 沒有 by 的舊存檔：當作師父說的，叛投時不丟


def test_a_heard_fragment_triggers_foreshadow(game):
    game.skip_tutorial()
    game.state.player.fragments = {"chain": []}  # 鏈在、沒聽過片段
    game._check_hints()
    assert game.guide_box() is None
    game.state.player.fragments = {"chain": [0]}
    game._check_hints()
    assert game.guide_box()["text"] == "這是線索（散人）。"


def test_a_delivered_big_event_triggers_event_reveal(game):
    _with(game.content, "h_event_reveal")
    game.skip_tutorial()
    game.state.player.events_seen = ["changshe_fire"]
    game._check_hints()
    assert _key(game) == "h_event_reveal"


def test_a_summons_triggers_promotion_for_a_faction_member_only(game):
    game.skip_tutorial()
    game.state.player.summons = Summons(rank=2, location="town")
    game._check_hints()  # 散人沒有散人版：不說、也不記成說過
    assert game.guide_box() is None and "h_promotion" not in game.state.player.hints_seen
    game.state.player.faction = "guan"
    game._check_hints()
    assert game.guide_box()["text"] == "上頭點你的名了。"


def test_a_brush_off_triggers_snubbed(game, hints_content):
    _with(hints_content, "h_snubbed")
    game.skip_tutorial()
    lines = game._brush_off("sage")  # 打發不看名望夠不夠，直接回那一句（測試內容的人物沒寫打發話，用通用的那一句）
    assert lines and "名望還差" in lines[0]
    assert _key(game) == "h_snubbed"
    assert f"【{MENTOR}】h_snubbed 的話" in _journal_guides(game)


def _muster(game, region=None):
    """開一場在集結的全服決戰（官軍對黃巾），可以限定在某個大區。"""
    from test_engine import _install_battle_def

    definition = _install_battle_def(game.content)
    definition.region = region
    game.world.start_battle(definition, now=1000.0)
    return definition


def test_a_drifter_at_a_muster_triggers_spectator(game):
    _with(game.content, "h_spectator", "h_showdown")
    game.skip_tutorial()
    game._check_hints()
    assert game.guide_box() is None  # 還沒有決戰
    _muster(game)
    game._check_hints()
    assert _key(game) == "h_spectator" and _queued(game) == ["h_spectator"]  # 散人在一旁看，沒有開戰說明


def test_spectator_only_fires_where_the_battle_is(game):
    """N3：決戰在別的大區，散人雖然「觀戰」中、人卻不在戰場上，不說。"""
    _with(game.content, "h_spectator")
    game.skip_tutorial()
    definition = _muster(game, region="south")  # 小鎮在北區
    game._check_hints()
    assert game.guide_box() is None and _queued(game) == []
    definition.region = "north"  # 決戰換到小鎮所在的大區：人在現場了
    game._check_hints()
    assert _key(game) == "h_spectator"


def test_a_member_at_a_muster_triggers_showdown_and_a_drifter_does_not(game):
    _with(game.content, "h_showdown", "h_spectator")
    game.skip_tutorial()
    game.state.player.faction = "guan"
    _muster(game)
    game._check_hints()
    assert _queued(game) == ["h_showdown"]
    assert game.guide_box()["text"] == "h_showdown 的話"


def test_a_member_away_from_the_muster_does_not_get_the_showdown_hint(game):
    _with(game.content, "h_showdown")
    game.skip_tutorial()
    game.state.player.faction = "guan"
    _muster(game, region="south")  # 在別的大區：趕不上這場，不是「遇上」
    game._check_hints()
    assert game.guide_box() is None


def test_showdown_waits_for_the_muster(game):
    """決戰已經開打（不在集結）時不說：這一條是教怎麼選邊、怎麼出招的，集結才是入場的時候。"""
    _with(game.content, "h_showdown")
    game.skip_tutorial()
    game.state.player.faction = "guan"
    _muster(game)
    game.world.mutate_battle(lambda b: setattr(b, "phase", "active"))
    game._check_hints()
    assert game.guide_box() is None


# ── h_figure：只有大勢人物（F1），用真內容、第一季的規則 ──────────────────────

def _figure_game(content, at):
    content.hints.hints.append(HintDef(id="h_figure", by="mentor", text="那位是大人物。"))
    game = _real_game(content, at=at)
    game.state.player.tutorial_step = len(guide.steps(game.state, content))  # 引導走完（真內容的序章與引導不擋在前面）
    return game


def test_a_great_figure_in_the_room_triggers_figure(on):
    game = _figure_game(on, "changshe")  # 皇甫嵩、朱儁在長社
    game._check_hints()
    assert _key(game) == "h_figure"


@pytest.mark.parametrize("place", ["runan_market", "qiao_county", "zhuo_county"])
def test_a_character_who_is_not_a_great_figure_does_not_trigger_figure(on, place):
    """陶謙、曹操、劉備三兄弟是可以交友的人物（_figures_here 會列出來），但不是人物表上的大勢人物（F1）。"""
    game = _figure_game(on, place)
    assert game._figures_here()  # 這裡確實有「人物」
    game._check_hints()
    assert game.guide_box() is None and _queued(game) == []


def test_figure_needs_the_season_one_rules(real):
    game = _figure_game(real, "changshe")  # 開關關著（beta 的那一季）：沒有大勢人物
    game._check_hints()
    assert game.guide_box() is None


# ── 排隊的規矩 ─────────────────────────────────────────


def test_one_state_hint_at_a_time_the_next_waits_until_the_first_is_read(game, monkeypatch):
    """N2：同時碰到兩個狀態條件，先排一條；框上（或排著）那一條按了「知道了」之後，條件還成立才排下一條。
    不管是一次行動、一次同步還是兩者連著來（見下面 sync 接 choose 那一條）：同一時間最多一條狀態提示在框上或排著。"""
    from tianxia import library

    game.skip_tutorial()
    p = game.state.player
    p.insights = ["feng", "huo"]
    monkeypatch.setattr(library, "cap_of", lambda s, c: library.held_count(s) + 3)
    game._check_hints()
    assert _queued(game) == ["h_merge"]  # 兩個條件都成立，這一次只排一條
    game._check_hints()  # 下一次行動或同步：第一條還沒按「知道了」，不排
    game._check_hints()
    assert _queued(game) == ["h_merge"]
    game.guide_ack()
    game._check_hints()
    assert _queued(game) == ["h_cap"]  # 讀過了，條件還成立：輪到下一條
    assert _key(game) == "h_cap"


def test_a_request_never_queues_two_state_hints(game):
    """伺服器每個動作都是先 sync 再做動作（server.act）：兩個狀態條件同時成立時，這一個請求只排出一條，不是 sync 排一條、動作再排一條。"""
    _with(game.content, "h_injury")
    game.skip_tutorial()
    p = game.state.player
    p.insights = ["feng", "huo"]
    p.member.injury = 5
    game.sync(1000.0)
    assert _queued(game) == ["h_merge"]
    game.choose("act:rest")
    assert _queued(game) == ["h_merge"]  # 動作做完的那次檢查也不再排
    game.guide_ack()
    game.sync(1010.0)
    assert _queued(game) == ["h_injury"]  # 讀過之後的下一次，輪到第二條


def test_the_second_hint_is_dropped_if_its_condition_no_longer_holds(game, monkeypatch):
    from tianxia import library

    game.skip_tutorial()
    game.state.player.insights = ["feng", "huo"]
    monkeypatch.setattr(library, "cap_of", lambda s, c: library.held_count(s) + 3)
    game._check_hints()
    game.guide_ack()
    monkeypatch.setattr(library, "cap_of", lambda s, c: library.held_count(s) + 30)  # 熔掉了幾樣
    game._check_hints()
    assert _queued(game) == []


def test_a_hint_that_cannot_be_said_does_not_use_up_the_turn(game):
    """排不進去的（散人碰到沒有散人版的）不算「這一次排過了」：同一次檢查裡接著看後面的。"""
    game.skip_tutorial()
    p = game.state.player
    p.summons = Summons(rank=2, location="town")  # h_promotion：散人沒有散人版
    p.insights = ["feng", "huo"]
    p.fragments = {"chain": [0]}
    game._check_hints()
    assert _queued(game) == ["h_merge"]
    game.guide_ack()
    game._check_hints()
    assert _queued(game) == ["h_foreshadow"]  # h_promotion 一直排不進去，不擋住後面的


def test_event_hints_are_not_paced(game, hints_content):
    """事件型的（被打發、玉璽碎片的秘密揭開、開季那一句、再投靠的招呼）當場排：不吃限速，也不被排著的狀態提示擋住。"""
    _with(hints_content, "h_snubbed")
    game.skip_tutorial()
    game.state.player.insights = ["feng", "huo"]
    game._check_hints()
    game._brush_off("sage")
    assert _queued(game) == ["h_merge", "h_snubbed"]  # 當場排
    game.guide_ack()
    game.guide_ack()
    game._brush_off("sage")  # 說過的不重說
    assert _queued(game) == []


def test_a_queued_event_hint_does_not_hold_back_a_state_hint(game, hints_content):
    """限速只管狀態提示彼此之間（同一時間最多一條在框上或排著）：排著的事件型提示不算。"""
    _with(hints_content, "h_snubbed")
    game.skip_tutorial()
    game._brush_off("sage")
    game.state.player.insights = ["feng", "huo"]
    game._check_hints()
    assert _queued(game) == ["h_snubbed", "h_merge"]


def test_sync_notices_what_changed_without_an_action(game):
    """大事揭曉、決戰開打、抵達都是同步時發生的：不靠行動，下一次同步就看到。"""
    _with(game.content, "h_event_reveal")
    game.skip_tutorial()
    game.state.player.events_seen = ["changshe_fire"]
    game.sync(1000.0)
    assert _key(game) == "h_event_reveal"
    assert f"【{MENTOR}】h_event_reveal 的話" in _journal_guides(game)


# ── 有所感（悟意境設計第零節，joy 的序章四景也是它）：跟事件待處理一樣，提示排著等 ──────────────────────────


def _feeling(game):
    """探索落在悟意境那一支、這一處有場景：跳出一張「有所感」的卡（做法選單，卡片本身是畫面）。"""
    from tianxia import sensing
    from tianxia.models import InsightScene, SenseMethod

    scene = InsightScene(
        id="lake_wind", title="湖風", text="風吹過湖面，停過腳的{痕跡}。", tags=["湖畔"], hints=["柔"],
        methods=[SenseMethod(attribute=a, text=t) for a, t in (("柔", "看水"), ("剛", "打水"), ("快", "追風"), ("慢", "靜坐"))],
    )
    game.content.insight_scenes = {scene.id: scene}
    game.state.player.location = "lake"
    sensing.start(game.state, game.content, scene, random.Random(0))
    assert game.state.player.sensing is not None
    return scene


def test_a_hint_waits_while_a_feeling_is_on_the_screen(game):
    """「有所感」的卡擺在眼前（選做法、畫一筆）時，提示的框不出：它跟事件的選項一樣佔住畫面，擺上去會把最後一個做法擠出第一屏（F3）。
    排著、不算說過；有所感了結的那一下上框。"""
    game.skip_tutorial()
    _feeling(game)
    game._hint("h_merge")
    p = game.state.player
    assert game.guide_box() is None and _queued(game) == ["h_merge"] and "h_merge" not in p.hints_seen
    game.guide_ack()  # 框上沒有提示：什麼都不收
    assert _queued(game) == ["h_merge"]
    p.sensing = None
    assert _key(game) == "h_merge"


def test_a_hint_shows_when_the_feeling_is_let_go(game):
    """選對做法、「順其自然」了結這次有所感（走 choose）：排著的提示在這一下上框、記在這一則。"""
    game.skip_tutorial()
    scene = _feeling(game)
    game.rng = FixedRandom(0.0)  # 擲骰必中：進感悟狀態
    game._hint("h_merge")
    index = [scene.methods[j].attribute for j in game.state.player.sensing.order].index("柔")
    game.choose(f"sense:{index}")
    assert game.state.player.sensing is not None and game.guide_box() is None  # 還在畫的那一步：照舊等
    game.choose("sense:let")
    assert game.state.player.sensing is None
    assert _key(game) == "h_merge" and "h_merge" in game.state.player.hints_seen
    assert f"【{MENTOR}】意境可以合。" in game.state.journal[0].guide


def test_a_hint_shows_when_the_stroke_is_drawn(game):
    """畫完那一筆（server 的 sense_request／sense_draw，不走 choose）：悟到意境、排著的提示在這一則上框；悟到的意境本身也可能讓
    某一條成立（第二個意境：h_merge），這時候看一遍。"""
    from tianxia import glyph

    game.skip_tutorial()
    scene = _feeling(game)
    game.rng = FixedRandom(0.0)
    game.state.player.insights = ["huo"]  # 手上已經一個：這一筆再悟到一個就是兩個
    index = [scene.methods[j].attribute for j in game.state.player.sensing.order].index("柔")
    game.choose(f"sense:{index}")
    req = game.sense_request(glyph.SAMPLES["柔"])
    assert not isinstance(req, str)
    assert game.guide_box() is None and _queued(game) == []
    game.sense_draw(req)
    assert game.state.player.sensing is None and len(game.state.player.insights) == 2
    assert _key(game) == "h_merge"
    assert f"【{MENTOR}】意境可以合。" in game.state.journal[0].guide


# ── 什麼時候不看 ───────────────────────────────────────


def test_no_hints_inside_the_prologue(prologue_content, world):
    prologue_content.hints = Hints(hints=[HintDef(id="h_merge", by="mentor", text="合。")])
    g = Game.new(prologue_content, "沈浪", rng=random.Random(0), world=world, prologue=True)
    g.state.player.insights = ["feng", "huo"]
    g._check_hints()
    assert g.state.player.hint_queue == [] and "h_merge" not in g.state.player.hints_seen
    g._hint("h_merge")  # 事件型的也一樣：序章本身在教
    assert g.state.player.hint_queue == [] and "h_merge" not in g.state.player.hints_seen


def test_nothing_is_queued_before_the_season_opens_or_after_it_ends(hints_content, world):
    """F7：籌備中與休季框都不畫；排進去就算「說過」會讓它們白白丟掉，所以這兩段不排。"""
    hints_content.config.auto_open_first_season = False
    waiting = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    waiting.skip_tutorial()
    waiting.state.player.insights = ["feng", "huo"]
    assert waiting._preparing()
    waiting._check_hints()
    assert waiting.state.player.hint_queue == []


def test_nothing_is_queued_after_the_season_has_ended(game):
    game.skip_tutorial()
    game.state.player.insights = ["feng", "huo"]
    game.state.world.ended = True
    game._check_hints()
    assert game.state.player.hint_queue == []
    game.state.world.ended = False
    game._check_hints()
    assert _queued(game) == ["h_merge"]  # 休季之前沒排進去的，下一季條件還成立就排


def test_bots_and_hints_off_check_nothing(game):
    game.skip_tutorial()
    game.state.player.insights = ["feng", "huo"]
    game.state.player.bot = BotProfile(personality="普通", seed=1)
    game._check_hints()
    assert game.state.player.hint_queue == []
    game.state.player.bot = None
    game.set_hints_off(True)
    game._check_hints()
    assert game.state.player.hint_queue == []


def test_once_every_hint_has_been_said_nothing_is_worked_out(game, monkeypatch):
    """N10：每條都說過了就不再算條件（每次行動與每次同步都會叫一遍）。"""
    game.skip_tutorial()
    game.state.player.hints_seen |= {h.id for h in game.content.hints.hints}

    def boom(*args, **kwargs):
        raise AssertionError("不該算條件")

    monkeypatch.setattr(game, "_hint_triggers", boom)
    game._check_hints()


def test_event_only_hints_do_not_keep_the_early_return_from_applying(game, monkeypatch, hints_content):
    """h_snubbed、h_mandate 不看狀態（事件發生時自己叫）：還沒說過也不該讓每次行動與同步都去算條件。"""
    _with(hints_content, "h_snubbed", "h_mandate")
    game.skip_tutorial()
    game.state.player.hints_seen |= {h.id for h in game.content.hints.hints} - {"h_snubbed", "h_mandate"}

    def boom(*args, **kwargs):
        raise AssertionError("該說的狀態提示都說過了，不該算條件")

    monkeypatch.setattr(game, "_hint_triggers", boom)
    game._check_hints()


def test_only_the_hints_the_book_has_are_worked_out(game, monkeypatch):
    """書裡沒有的條不算它的條件（真內容一條一條補進來之前，決戰的資料庫讀取也不必每次都做）。"""

    def boom(*args, **kwargs):
        raise AssertionError("不該讀決戰")

    monkeypatch.setattr(game, "_battle_status", boom)
    game.skip_tutorial()
    game._check_hints()


# ── 行動做完就看一遍（每個地方都插在記進江湖紀錄之前，說的話記在那一則）────────────────

def test_choose_notices_what_the_action_made_true(game):
    game.skip_tutorial()
    game.state.player.insights = ["feng", "huo"]
    game.choose("act:rest")
    assert _key(game) == "h_merge"
    assert f"【{MENTOR}】意境可以合。" in game.state.journal[0].guide  # 記在這一次行動那一則


def test_travel_notices_it_too(game):
    game.skip_tutorial()
    game.state.player.insights = ["feng", "huo"]
    game.travel("lake")
    assert _key(game) == "h_merge" and f"【{MENTOR}】意境可以合。" in game.state.journal[0].guide


def test_allocating_a_point_notices_it_too(game):
    game.skip_tutorial()
    game.state.player.insights = ["feng", "huo"]
    game.state.player.stat_points = 1
    game.allocate_stat("str")
    assert _key(game) == "h_merge"


def test_a_page_action_notices_it_too(game):
    """修練頁、煉製頁的動作（療傷、練成、修練、熔煉、合成、改練都經過 _menxia_entry）：修練失敗就是在這裡留下熟練度的。"""
    _with(game.content, "h_refine_fail")
    game.skip_tutorial()
    game.state.player.art_mastery = {"basic_fist": 1}
    game.heal()
    assert _key(game) == "h_refine_fail"
    assert f"【{MENTOR}】h_refine_fail 的話" in _journal_guides(game)


def test_every_page_action_looks_for_hints(game, monkeypatch):
    """修練頁、煉製頁的每一種動作做完都經過 _menxia_entry、看一遍提示（療傷、練成、改練、熔武學、熔意境、合成、修練）：
    一個一個做、每做成一個，檢查就多叫一次。"""
    from tianxia import cultivation

    game.skip_tutorial()
    p = game.state.player
    p.stats.update(xinde=500)
    p.stamina = float(game.content.config.stamina_max)
    p.member.neigong_id, p.member.wugong_id = "breath", "fist"
    p.arts = ["sword", "step"]
    p.insights = ["feng", "huo", "shui"]
    calls = []
    real = game._check_hints
    monkeypatch.setattr(game, "_check_hints", lambda *args, **kwargs: (calls.append(1), real(*args, **kwargs))[1])
    monkeypatch.setattr(cultivation, "cultivate_problem", lambda *args, **kwargs: None)
    monkeypatch.setattr(cultivation, "cultivate", lambda *args, **kwargs: ["【失敗】修練沒有成。"])
    actions = {
        "heal": lambda: game.heal(),
        "practice": lambda: game.practice("武學"),
        "switch_art": lambda: game.switch_art("sword"),
        "melt_art": lambda: game.melt_art("step"),
        "melt_insight": lambda: game.melt_insight("shui"),
        "forge": lambda: game.forge("sword", ["feng"]),
        "cultivate": lambda: game.cultivate("sword"),
    }
    for name, act in actions.items():
        before = len(calls)
        act()
        assert len(calls) == before + 1, name


# ── M-1：「知道了」與略過之前先上框 ──────────────────────────


def test_skipping_the_guide_brings_up_a_waiting_hint_and_notes_it(game):
    game._hint("h_merge")  # 說書人還在框上，排著
    assert "h_merge" not in game.state.player.hints_seen
    game.skip_tutorial()  # 框換成這一條：同一下上框、記說過、記進江湖紀錄（不必等同步）
    assert _key(game) == "h_merge" and "h_merge" in game.state.player.hints_seen
    assert f"【{MENTOR}】意境可以合。" in _journal_guides(game)


def test_ack_never_pops_a_hint_that_was_not_shown_yet(game):
    """框上的提示是別的狀態改變（引導走完）讓它輪到的、還沒有任何呼叫把它記成說過：按「知道了」先記再收，不會憑空吞掉一條。"""
    game._hint("h_merge")
    game.state.player.tutorial_step = len(guide.steps(game.state, game.content))  # 說書人退場，沒有經過 sync 與行動
    assert "h_merge" not in game.state.player.hints_seen
    game.guide_ack()
    p = game.state.player
    assert p.hint_queue == [] and "h_merge" in p.hints_seen
    assert f"【{MENTOR}】意境可以合。" in _journal_guides(game)


# ── I-1：網頁在修練、煉製頁也畫提示，靠伺服器標的 hint ──────────────────────────


def test_a_hint_box_says_it_is_a_hint(game):
    p = game.state.player
    p.tutorial_step = len(guide.steps(game.state, game.content))
    game._hint("h_merge")
    assert game.guide_box()["hint"] is True
    game.guide_ack()
    p.guide_outro = True
    box = game.guide_box()
    assert box["key"] == "outro" and not box.get("hint")  # 結語不是提示：網頁只在江湖頁畫


def test_a_tutorial_step_is_not_a_hint(game):
    assert not game.guide_box().get("hint")


# ── N7：叛投時，舊陣營那邊排著的提示作廢 ──────────────────────────


def test_a_hint_note_remembers_whose_voice_it_is(game):
    from tianxia import hints

    game.skip_tutorial()
    p = game.state.player
    assert hints.note_for(game.state, game.content, "h_merge").by == ""  # 師父
    assert hints.note_for(game.state, game.content, "h_foreshadow").by == ""  # 散人聽到的，也是師父講的
    p.faction = "guan"
    assert hints.note_for(game.state, game.content, "h_foreshadow").by == "guan"  # 自己那一邊的引薦人


def test_defecting_drops_the_old_sides_queued_hints_and_keeps_the_mentors(game):
    p = game.state.player
    p.faction = "guan"
    p.hint_queue = [
        HintNote(id="h_promotion", speaker="老石", text="上頭點你的名了。", by="guan"),
        HintNote(id="h_merge", speaker=MENTOR, text="意境可以合。"),
        HintNote(id="h_x", speaker="青禾", text="另一邊的話。", by="huang"),
    ]
    defection.clear_progress(p)
    assert [n.id for n in p.hint_queue] == ["h_merge", "h_x"]  # 舊陣營（guan）的作廢，師父的與別人的不動
    p.faction = None  # 散人沒有舊陣營：什麼都不丟
    defection.clear_progress(p)
    assert [n.id for n in p.hint_queue] == ["h_merge", "h_x"]


# ── Task 3：再投靠的招呼（設計 7.1、10.6；話寫在 tutorial.json 入伍段的 rejoin）──────────────────────
# 用真內容、第一季的規則打開；提示表清空（真的提示表另有測試，招呼不靠它）。

JOIN_POINTS = {"guan": ("changshe", "老石"), "huang": ("huangjin_camp", "青禾"), "haoqiang": ("zhuo_militia_hall", "季伯平")}


def _rejoiner(content, faction, **kwargs):
    """上一季入伍段走完的人，這一季又是散人、站在那一邊的投靠點：他一投靠就是「再投靠」。"""
    content.hints = Hints()
    game = _real_game(content, at=JOIN_POINTS[faction][0], **kwargs)
    p = game.state.player
    p.tutorial_step = len(guide.steps(game.state, content))
    p.enlist_step = len(content.tutorial.enlist.steps)
    assert p.faction is None
    return game


def _join(game, faction):
    game.choose(f"faction:{faction}")
    game.choose("faction:confirm")
    assert game.state.player.faction == faction


@pytest.mark.parametrize("faction", ["guan", "huang", "haoqiang"])
def test_rejoining_greets_in_the_recruiters_own_voice(on, faction):
    game = _rejoiner(on, faction)
    who = on.tutorial.enlist.recruiters[faction]
    _join(game, faction)
    box = game.guide_box()
    assert (box["speaker"], box["text"], box["key"], box["end"], box["hint"]) == (who.name, who.rejoin, "s_rejoin", True, True)
    assert box["speaker"] == JOIN_POINTS[faction][1] and who.rejoin  # 三位引薦人各說各的
    assert f"【{who.name}】{who.rejoin}" in _journal_guides(game)  # 說過的話記進江湖紀錄（設計 6.2）
    assert game.state.player.hint_queue[0].by == faction  # 叛投時作廢
    assert game.state.player.enlist_step == len(on.tutorial.enlist.steps)  # 入伍段不重走
    game.guide_ack()
    assert game.guide_box() is None and game.state.player.hint_queue == []
    assert "s_rejoin" not in game.state.player.hints_seen  # 每季都要打招呼，不記成說過


def test_the_greeting_comes_every_season(on):
    game = _rejoiner(on, "guan")
    _join(game, "guan")
    game.guide_ack()
    game._reset_player_for_new_season(3)
    p = game.state.player
    assert p.faction is None and p.enlist_step == len(on.tutorial.enlist.steps) and not p.guide_skipped
    p.location = "changshe"
    _join(game, "guan")
    assert game.guide_box()["key"] == "s_rejoin"


def test_the_first_join_is_the_enlistment_not_a_greeting(on):
    game = _rejoiner(on, "guan")
    game.state.player.enlist_step = None
    _join(game, "guan")
    assert game.state.player.enlist_step == 0
    assert game.state.player.hint_queue == [] and game.guide_box()["key"] == "r2_briefing"


def test_someone_who_skipped_the_guide_gets_no_greeting(on):
    game = _rejoiner(on, "guan")
    game.state.player.guide_skipped = True  # 略過新手引導：序章與入伍段都算走完（enlist.skip），之後的季帶著這個旗
    _join(game, "guan")
    assert game.state.player.hint_queue == [] and game.guide_box() is None


def test_no_greeting_for_bots_or_with_hints_off(on):
    off = _rejoiner(on, "guan")
    off.set_hints_off(True)
    _join(off, "guan")
    bot = _rejoiner(on, "guan", name="假人")
    bot.state.player.bot = BotProfile(personality="普通", seed=1)
    _join(bot, "guan")
    assert off.state.player.hint_queue == [] and bot.state.player.hint_queue == []


def test_defecting_is_not_a_rejoin(on):
    """叛投：投靠之前已經有陣營，不打招呼。"""
    game = _rejoiner(on, "guan")
    game.state.player.faction = "guan"
    game.state.player.location = "huangjin_camp"
    game.choose("defect:huang")
    game.choose("defect:confirm")
    assert game.state.player.faction == "huang" and game.state.player.hint_queue == []


def test_a_greeting_is_dropped_when_you_defect_before_reading_it(on):
    game = _rejoiner(on, "guan")
    _join(game, "guan")
    assert [n.id for n in game.state.player.hint_queue] == ["s_rejoin"]
    game.state.player.location = "huangjin_camp"
    game.choose("defect:huang")
    game.choose("defect:confirm")
    assert game.state.player.faction == "huang" and game.state.player.hint_queue == []  # 老石的招呼隨舊陣營作廢


def test_the_greeting_is_not_held_back_by_an_unread_state_hint(on):
    """招呼是事件型的，當場排：不被排著的狀態提示擋住（限速只管狀態提示彼此）。"""
    game = _rejoiner(on, "guan")
    on.hints = Hints(hints=[HintDef(id="h_merge", by="mentor", text="「合。」")])
    game.state.player.insights = ["feng", "huo"]
    game._check_hints()
    assert [n.id for n in game.state.player.hint_queue] == ["h_merge"]
    _join(game, "guan")
    assert [n.id for n in game.state.player.hint_queue] == ["h_merge", "s_rejoin"]


def test_a_free_text_answer_that_joins_a_sect_also_greets(on):
    """隨口應對（answer_event）拜入陣營名下的門派：同選項一樣，入伍段早就走完的人收到招呼。"""
    from conftest import FixedRandom
    from tianxia.models import Choice, Event

    game = _rejoiner(on, "haoqiang")
    game.state.player.location = "cao_manor"
    event = Event(
        id="t_join_free", title="結社", text="莊裡的人問你要不要入夥。", actions=[],
        choices=[Choice(text="再想想", effect=Effect(text="你沒有表態。"))], free_text=FreeTextChoice(
            prompt="自己想辦法……", stat="str", by="self", effect=Effect(join_sect="cao_manor"), fail_effect=Effect(text="沒成。"),
        ),
    )
    on.events[event.id] = event
    game._present(event)
    game.rng = FixedRandom(0.0)
    game.answer_event(game.free_text_request("我願意替莊裡跑腿"), 90)
    assert game.state.player.faction == "haoqiang"
    box = game.guide_box()
    assert (box["speaker"], box["key"]) == ("季伯平", "s_rejoin")


def test_queue_note_follows_the_same_gates_as_the_queue(game):
    from tianxia import hints

    note = HintNote(id="s_rejoin", speaker="老石", text="「又是你。」", by="guan")
    assert hints.queue_note(game.state, note) is True
    assert hints.queue_note(game.state, note) is False  # 同一條已經排著
    game.state.player.hint_queue = []
    game.state.player.hints_off = True
    assert hints.queue_note(game.state, note) is False
    game.state.player.hints_off = False
    game.state.player.bot = BotProfile(personality="普通", seed=1)
    assert hints.queue_note(game.state, note) is False
    assert game.state.player.hint_queue == []
