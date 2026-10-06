"""引導小改版（新手引導重做設計第八節）：說書人的話放在行動列上方的對話框，「剛剛」只放這次行動的結果。

用測試夾具的內容：說書人三步（先探索一下〔獎勵銀兩 5〕→ 去湖邊 → 看看地圖），結語「去闖吧。」。開關照夾具（關著）——
這個小改版不看開關。"""
from __future__ import annotations

from conftest import walk_to
from tianxia import journal
from tianxia.models import ExploreMix

STEP_ONE, STEP_TWO, STEP_THREE, OUTRO = "先探索一下。", "去湖邊。", "看看地圖。", "去闖吧。"


def _box(text, done=(), end=False):
    return {"speaker": "說書人", "scene": "", "text": text, "line": "", "done": list(done), "end": end}


def pending_line(title):
    return f"先把眼前的「{title}」了結"


def _explore_event(game):
    game.content.config.explore_mix = [ExploreMix(kind="wild", tags=[], weights={"event": 1})]


def test_a_new_character_sees_the_first_step_in_the_box(game):
    """8.3：全新角色一進江湖頁就有對話框與第一步的話；開場那一則「剛剛」只有劇本的開場，說書人那一句記在 guide。"""
    assert game.guide_box() == _box(STEP_ONE)
    entry = game.state.journal[0]
    assert entry.lines == ["測試開始。"] and entry.guide == [f"【說書人】{STEP_ONE}"]
    assert "說書人" not in journal.card_html(entry)
    assert f"【說書人】{STEP_ONE}" in journal.rows_html([entry])  # 江湖紀錄照舊看得到


def test_finishing_a_step_goes_to_the_box_not_the_latest_card(game):
    """RF1：做完一步，「剛剛」只有這次行動的結果；獎勵照舊只套一次，「✔ 引導完成」與獎勵在對話框，接著是下一步的話；
    江湖紀錄的那一則把引導記在 guide。下一次行動清掉完成的那幾行。"""
    _explore_event(game)
    silver = game.state.player.stats["silver"]
    msgs = game.choose("act:explore")
    assert game.state.player.stats["silver"] == silver + 5
    assert "✔ 引導完成" not in msgs and f"【說書人】{STEP_TWO}" not in msgs
    entry = game.state.journal[0]
    assert (entry.lines, entry.changes) == ([], [])
    assert entry.guide == ["✔ 引導完成", "銀兩 +5", f"【說書人】{STEP_TWO}"]
    assert "引導完成" not in journal.card_html(entry) and "銀兩 +5" not in journal.card_html(entry)
    title = game.content.events[game.state.pending_event].title
    assert game.guide_box() == _box(pending_line(title), ["✔ 引導完成", "銀兩 +5"])  # 眼前還有事件：先了結它（FB-063）
    game.choose("choice:1")
    assert game.guide_box() == _box(STEP_TWO)


def test_a_pending_event_replaces_the_step_text_until_it_is_settled(game):
    """FB-063：事件還沒了結時不推教學那一步（叫人往郊野走、事件卻擋著路），框上寫「先把眼前的「…」了結」；
    事件了結後是原來那一步，步驟本身沒有動。每一步都一樣，不只是叫人出發的那幾步。"""
    p = game.state.player
    for step, text in enumerate((STEP_ONE, STEP_TWO, STEP_THREE)):
        p.tutorial_step = step
        game.state.pending_event = "drunk"
        assert game.guide_box() == _box(pending_line("醉漢"))  # 說書人還是說書人
        assert p.tutorial_step == step
        game.state.pending_event = None
        assert game.guide_box() == _box(text)


def test_a_chained_event_names_the_step_that_is_pending_now_in_the_box(game):
    """next_event 接下去的下一段：框上寫現在待處理的那一則。"""
    game._present(game.content.events["chain_a"])
    assert game.guide_box()["text"] == pending_line("跟蹤")
    game.choose("choice:0")
    assert game.state.pending_event == "chain_b"
    assert game.guide_box()["text"] == pending_line("倉庫")
    game.choose("choice:0")
    assert game.guide_box()["text"] == STEP_ONE


def test_the_outro_is_shown_even_while_an_event_is_pending(game):
    """結語（end）照舊：全部做完了，沒有「下一步」可以擋。"""
    game.state.player.tutorial_step = 3
    game.state.player.guide_outro = True
    game.state.pending_event = "drunk"
    assert game.guide_box() == _box(OUTRO, end=True)


def test_finishing_the_last_step_shows_the_outro_until_acknowledged(game):
    """全部做完：對話框是結語，按「知道了」之後不再出現。"""
    game.state.player.tutorial_step = 1
    walk_to(game, "lake")
    assert game.guide_box() == _box(STEP_THREE, ["✔ 引導完成"])
    game.view_map()
    assert game.guide_box() == _box(OUTRO, ["✔ 引導完成"], end=True)
    assert game.state.journal[0].guide[-1] == f"【說書人】{OUTRO}"
    assert game.guide_ack() == []
    assert game.guide_box() is None


def test_finished_before_the_box_shows_nothing(game):
    """RF4：舊存檔裡早就做完引導的角色，沒有結語要看，對話框不出現。"""
    game.state.player.tutorial_step = 3
    assert game.guide_box() is None


def test_skipping_hides_the_box(game):
    game.skip_tutorial()
    assert game.guide_box() is None


def test_skipping_stays_skipped_into_the_next_season():
    """畫面批次審查 I4：beta 那一季略過新手引導（停在不分季的最後一步之後），換成第一季（13 步，多了軍令兩步）之後也不再出現對話框；
    步驟照 T6 的規則記著（做完照樣推進），只是不畫框。沒略過、做完序章十一步的人照 T6 接著做，框照常出現。"""
    import random
    from pathlib import Path

    from tianxia.characters import open_characters
    from tianxia.content import load_content
    from tianxia.engine import Game
    from tianxia.guide import base_step_count
    from tianxia.sqlite_world import open_world

    root = Path(__file__).parent.parent / "content"
    beta = load_content(root)
    beta.config.auto_open_first_season, beta.config.admins = True, ["管"]
    chars = open_characters()
    admin = Game.new(beta, "管", rng=random.Random(1))
    # 略過的人是在草廬裡按了「略過序章」的真人（走完序章、站在起點的人再按略過什麼都不做：引導已經做完了）
    skipper, finisher = Game.new(beta, "略過的", rng=random.Random(2), prologue=True), Game.new(beta, "做完的", rng=random.Random(3))
    skipper.skip_tutorial()
    base = base_step_count(beta)  # 不分季的步數（序章十一步）：第一季的軍令兩步排在它們後面
    finisher.state.player.tutorial_step = base
    for game in (admin, skipper, finisher):
        chars.save(game.state)
    admin.admin_end_season(now=100.0)
    on = load_content(root)
    on.config.admins, on.config.season_one, on.config.season_days = ["管"], True, 2.5
    admin = Game(on, chars.load("管"), rng=random.Random(1), world=open_world())
    admin.admin_next_season(now=200.0)
    games = {name: Game(on, chars.load(name), rng=random.Random(4), world=open_world()) for name in ("略過的", "做完的")}
    for game in games.values():
        game.sync(300.0)
        assert game.state.player.tutorial_step == base
    assert games["略過的"].guide_box() is None
    assert games["做完的"].guide_box()["text"] == on.tutorial.steps[base].text


def test_box_hidden_while_preparing(prologue_content, world, monkeypatch):
    """籌備中選單照舊只有「賽季籌備中」，序章也不例外：對話框不出現（新手引導計畫一 Review Focus 5）。"""
    from tianxia.engine import Game

    game = Game.new(prologue_content, "沈浪", world=world, prologue=True)
    game.choose("choice:0")
    game.choose("choice:0")
    assert game.guide_box() is not None
    monkeypatch.setattr(game, "_preparing", lambda: True)
    assert game.guide_box() is None
