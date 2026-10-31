"""章回主線（tianxia/chapters.py；企劃者 2026-10-29 選丙、「四個都同意」）：開回、做成記份量與貢獻、大事結算收回、
錯過不補、換陣營作罷、改擲骰與決戰起點、文字讀全服旗標與大事結果、眼下要事與章回卡。用正式內容 week7。"""
from __future__ import annotations

import pytest
from jianfa_kit import jianfa_game, ready

from tianxia import chapters, storyline, timetable, weekcard
from tianxia.content import ContentError, validate
from tianxia.rules import fill_marks
from tianxia.state import TimelineResult

G1, G2 = "ch_guan_1", "ch_guan_2"


def _game(side: str = "guan", loc: str = "changshe", **flags: bool):
    game = ready(jianfa_game("week7", **flags), side=side, loc=loc, level=20)
    if side == "haoqiang":
        game.state.player.ally = "guan"  # 豪強投靠時挑的那一邊（沒挑的話選單只剩挑一邊那兩顆）
    game.state.player.stats["silver"] = 500
    game._story_tick()  # noqa: SLF001  同步與每個動作之前都跑它
    return game


def _week(game) -> dict:
    return weekcard.week_card(game, game.status_data(), game.orders_view())


def _pick(game, words: str) -> list[str]:
    for opt in game.options():
        if words in opt.label and opt.enabled:
            return game.choose(opt.id)
    raise AssertionError(f"沒有「{words}」：{[o.label for o in game.options()]}")


def _go(game, loc: str) -> None:
    p = game.state.player
    p.location, p.journey = loc, None
    p.visited.add(loc)
    game._story_tick()  # noqa: SLF001


def _resolve(game, event_id: str, key: str) -> None:
    w = game.state.world
    w.timeline[event_id] = TimelineResult(key=key, time=w.time)
    game._story_tick()  # noqa: SLF001


def _scene(game, event_id: str) -> None:
    """到了那一幕的地方：按「未了之事」端出來（章回的幕不搶走那裡別的事，immediate 關著）。"""
    assert game.state.pending_event is None
    _pick(game, "未了之事")
    assert game.state.pending_event == event_id


def _do_g1(game, letter: str = "帶他們回城") -> None:
    """官軍第一回走到 wait：北門 → 傅燮（實話）→ 送軍書 → 前營 → 回城頭。"""
    _scene(game, "chg1_gate")
    _pick(game, "往城隍廟去")
    _pick(game, "沒有。我是來吃飯的")
    _go(game, "yingchuan_wilds")
    _scene(game, "chg1_road")
    _pick(game, letter)
    _pick(game, "信送到了")
    _go(game, "changshe")
    _scene(game, "chg1_back")
    _pick(game, "跟他上門樓")


def test_joining_a_side_opens_its_first_chapter_and_the_week_card_leads_with_it():
    game = _game()
    s = game.state
    assert list(s.player.storylines) == [G1]
    assert s.pending_event is None  # 人就在長社：不搶走長社別的事，選單與卡上多一顆
    card = weekcard.chapter_card(game)
    assert card["no"] == "一" and card["title"] == "投軍長社" and card["beat"] == "波才大敗朱儁" and not card["waiting"]
    assert card["here"] and card["hint"] == "到長社北門" and card["target"] is None  # 人在那裡：不用再去輿圖
    _pick(game, "未了之事")
    card = weekcard.chapter_card(game)
    assert card["scene"] and card["hint"] == "眼前這一幕：北門" and not card["here"]
    steps = _week(game)["steps"]
    assert steps[0]["kind"] == "chapter" and steps[0]["text"].startswith("第一回・投軍長社：")
    assert _week(game)["chapter"]["line"] == G1


def test_finishing_a_chapter_adds_weight_credit_and_count_then_the_beat_picks_the_ending():
    game = _game()
    s = game.state
    before = s.player.contrib
    _do_g1(game)
    progress = s.player.storylines[G1]
    assert progress.stage == chapters.WAIT and progress.marks[chapters.DONE] == 1
    assert s.world.chapter_done[G1] == 1
    assert s.world.chapter_weights["bocai_routs_zhujun"] == {"guan": 0.5}  # 晚到 −0.5
    assert s.player.contrib - before == game.content.config.jianfa.chapter_contribution
    if game.content.config.plans.enabled:  # 世界記事（「世界活起來」）：做成的那一刻記一筆
        deed = s.world.deeds[-1]
        assert (deed.kind, deed.place, deed.actors, deed.side) == ("chapter", "changshe", ["沈浪"], "guan")
        assert deed.text == "沈浪在長社做成了第一回「投軍長社」。"
    card = weekcard.chapter_card(game)
    assert card["line"] == G2 and not card["waiting"]  # 做完了就開下一回，卡換成還沒做的那一回
    assert card["here"] and card["hint"] == "到長社城樓見皇甫嵩"  # 第二回第一段也在長社
    game._story_tick()  # noqa: SLF001  做成只記一次
    assert s.world.chapter_done[G1] == 1
    _resolve(game, "bocai_routs_zhujun", "成")
    assert progress.ending == "hist" and progress.marks["果成"] == 1
    assert any("投軍長社" in a.text for a in s.player.annals)


def test_the_card_says_the_beats_battle_is_mustering_or_fighting_instead_of_its_scheduled_time():
    """U-17（手機介面自檢 2026-10-31）：第二回的大事長社火攻被提早開了（管理者「立刻開這一場」）：卡上 live 是集結、開打，
    網頁照它寫狀態；沒在打是 None（照舊寫排定的時刻）。"""
    from tianxia.world import open_showdown

    game = _game()
    _do_g1(game)
    card = weekcard.chapter_card(game)
    assert card["line"] == G2 and card["live"] is None and card["at"]
    game.now = 1000.0
    assert open_showdown(game.world, game.content, "changshe_fire", game.now)
    assert weekcard.chapter_card(game)["live"] == "muster"
    game.world.mutate_battle(lambda b: setattr(b, "phase", "active"))
    assert weekcard.chapter_card(game)["live"] == "active"


def test_a_chapter_not_done_when_its_beat_settles_is_missed_and_cannot_be_made_up():
    game = _game(loc="luoyang_palace")
    s = game.state
    card = weekcard.chapter_card(game)
    assert card["target"]["location"] == "changshe" and not card["scene"] and card["hint"] == "到長社北門"
    _resolve(game, "bocai_routs_zhujun", "不成")
    assert s.player.storylines[G1].ending == chapters.MISSED
    assert G1 not in s.world.chapter_done
    assert G2 in s.player.storylines  # 錯過的那一回不擋下一回


def test_changing_sides_drops_the_open_chapter_and_opens_the_other_sides_first():
    game = _game(loc="luoyang_palace")
    s = game.state
    s.player.faction = "huang"
    game._story_tick()  # noqa: SLF001
    assert s.player.storylines[G1].ending == chapters.LEFT
    assert "ch_huang_1" in s.player.storylines


def test_joining_late_starts_at_the_sides_current_chapter():
    game = _game(side="guan", loc="luoyang_palace")
    s = game.state
    s.player.storylines.clear()
    s.player.faction = None
    for event_id, key in (("bocai_routs_zhujun", "成"), ("changshe_fire", "guan:險勝")):
        s.world.timeline[event_id] = TimelineResult(key=key, time=s.world.time)
    s.player.faction = "guan"
    game._story_tick()  # noqa: SLF001
    opened = sorted(k for k in s.player.storylines if k.startswith("ch_"))
    assert opened == ["ch_guan_3", "ch_guan_4"]  # 第三、四回都只等第二回；第五回還要等盧植下獄


def test_the_sway_is_square_rooted_capped_and_still_inside_the_shared_cap():
    game = _game(loc="luoyang_palace")
    c, w = game.content, game.state.world
    event = timetable.find(c, "bocai_routs_zhujun")  # roll_side 黃巾
    cap, half = c.config.jianfa.chapter_roll_cap, c.config.jianfa.chapter_half_at
    w.chapter_weights["bocai_routs_zhujun"] = {"huang": half}
    assert chapters.roll_mod(w, c, event) == pytest.approx(cap / 2)
    w.chapter_weights["bocai_routs_zhujun"] = {"huang": half, "guan": half}
    assert chapters.roll_mod(w, c, event) == 0
    w.chapter_weights["bocai_routs_zhujun"] = {"guan": 10_000}
    assert -cap < chapters.roll_mod(w, c, event) < -cap * 0.95
    base = timetable.roll_chance(game.state, c, event)
    w.event_mods["bocai_routs_zhujun"] = -0.2
    w.chapter_weights.clear()
    alone = timetable.roll_chance(game.state, c, event)
    w.chapter_weights["bocai_routs_zhujun"] = {"guan": 10_000}
    assert timetable.roll_chance(game.state, c, event) == pytest.approx(alone)  # 伏筆已經 −0.20：合計不再往下
    assert alone < base
    w.chapter_weights["guangzong"] = {"huang": 10_000}
    assert chapters.showdown_edge(w, c, "guangzong") == -c.config.jianfa.chapter_edge_cap


def test_text_reads_world_flags_and_history_results():
    game = _game(loc="luoyang_palace")
    s, c = game.state, game.content
    text = c.events["chg3_shop"].text
    assert "灌了漿" not in storyline.vary(fill_marks(text, s), s)
    s.world.flags.add("ch_gate_sealed")
    assert "灌了漿" in storyline.vary(fill_marks(text, s), s)
    muster = c.events["chg5_muster"].text
    assert "長社那一夜的" in storyline.vary(muster, s)
    s.world.timeline["luzhi_jailed"] = TimelineResult(key="不成", time=s.world.time)
    assert "盧植點將" in storyline.vary(muster, s)


def test_a_chapter_waiting_on_a_beat_settled_at_season_end_still_gets_its_ending():
    game = _game()
    s = game.state
    _do_g1(game)
    s.world.timeline["bocai_routs_zhujun"] = TimelineResult(key="成", time=s.world.time)
    s.world.ended = True
    game._story_tick()  # noqa: SLF001
    assert s.player.storylines[G1].ending == "hist"


def test_switched_off_no_chapter_opens_and_the_week_card_has_no_chapter_key():
    game = _game(chapters=False)
    assert not any(k.startswith("ch_") for k in game.state.player.storylines)
    card = _week(game)
    assert "chapter" not in card and all(step["kind"] != "chapter" for step in card["steps"])


def test_content_checks_catch_a_chapter_without_its_wait_stage():
    game = _game(loc="luoyang_palace")
    c = game.content
    line = c.storylines[G1]
    line.stages = line.stages[:-1]
    with pytest.raises(ContentError, match=G1):
        validate(c)


@pytest.mark.slow
@pytest.mark.parametrize("side", ["guan", "huang", "haoqiang"])
@pytest.mark.parametrize("pick", [0, 2])
def test_each_side_plays_all_five_chapters_through_a_season(side, pick):
    """整季：照章回卡走到每一段的地點、按第 pick 顆（按得下去的），五回都做得成、不會卡住。"""
    from tianxia.rules import day_seconds

    game = _game(side=side)
    s = game.state
    hour = day_seconds(game.content, s.world) / 24
    real = 1_792_549_800.0
    game.sync(real)
    for _ in range(3000):
        s = game.state
        if s.world.ended:
            break
        if s.pending_event:
            opts = [o for o in game.options() if o.enabled and o.id.startswith("choice:") and o.id != "choice:free"]
            assert opts, s.pending_event
            game.choose(opts[min(pick, len(opts) - 1)].id)
            continue
        card = weekcard.chapter_card(game)
        if card and not card["waiting"]:
            if card["target"]:
                _go(game, card["target"]["location"])
                continue
            if card["here"]:
                game.choose(f"story:{card['line']}")
                continue
        s.player.stamina = float(game.content.config.stamina_max)
        real += hour
        game.sync(real)
    done = {k for k, v in game.state.player.storylines.items() if k.startswith("ch_") and v.marks.get(chapters.DONE)}
    assert len(done) == 5, sorted(game.state.player.storylines)
