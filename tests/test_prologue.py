"""序章（新手引導計畫一）：進出序章、草廬只給序章裡的人、舊存檔與換季。"""
import random

import pytest
from conftest import next_season

from tianxia import atlas, prologue
from tianxia.engine import Game
from tianxia.state import ONBOARDING_VERSION


@pytest.fixture
def fresh(prologue_content):
    return Game.new(prologue_content, "沈浪", rng=random.Random(0), prologue=True)


def test_new_character_starts_in_the_hut_with_the_ambush(fresh, prologue_content):
    s = fresh.state
    assert s.player.location == "hut"
    assert s.pending_event == "p_ambush"
    assert s.player.tutorial_step == 0
    # 探索 10＋合成 5（武學與成長計畫五的 fuse_stamina）＋修練 10；設計 3.2 寫的是 20（那時合成不花體力）
    assert s.player.stamina == prologue.start_stamina(prologue_content) == 25
    assert prologue.active(s, prologue_content)


def test_bots_never_see_the_hut(prologue_content):
    bot = Game.new(prologue_content, "假人", rng=random.Random(0))  # 預設 prologue=False：假人、機器人、腳本
    p = bot.state.player
    assert p.location == "town" and bot.state.pending_event is None
    assert p.tutorial_step == prologue_content.tutorial.prologue_steps
    assert p.stamina == prologue_content.config.stamina_max
    assert not prologue.active(bot.state, prologue_content)


def test_hut_is_invisible_to_everyone_outside(fresh, prologue_content):
    other = Game.new(prologue_content, "路人", rng=random.Random(0))
    hut = prologue_content.locations["hut"]
    assert atlas.is_unlocked(hut, fresh.state)
    assert not atlas.is_unlocked(hut, other.state)
    assert all(not o.id.startswith("move:hut") for o in other.options())
    assert "hut" not in atlas.visible_locations(other.state, prologue_content)
    assert "hut" not in atlas.shortest_routes(other.state, prologue_content)


def test_the_hut_does_not_change_the_terrain(prologue_content, content):
    """草廬只有序章裡的一個人看得到：它不能把整張地圖的山與樹換掉（mapart 的地形鍵不算它）。"""
    from tianxia import mapart

    assert mapart._terrain_key(prologue_content) == mapart._terrain_key(content)
    assert [p.svg for p in mapart.terrain(prologue_content)] == [p.svg for p in mapart.terrain(content)]


def test_only_the_farewell_step_lets_the_menu_and_the_map_leave(fresh, prologue_content):
    """出師之前選單沒有前往、輿圖的安排前往只剩一顆寫原因、按不下去的鈕；出師那一步才有 move:town（草廬只連潁川）。"""
    s = fresh.state
    s.pending_event = None
    block = atlas.travel_block(s, prologue_content)
    assert block is not None and "師父" in block.reason
    assert all(not o.id.startswith("move:") for o in fresh.options())
    buttons = atlas.travel_options(s, prologue_content, "town")
    assert buttons is not None and [b.enabled for b in buttons] == [False]
    s.player.tutorial_step = 10  # 出師那一步（第 11 步）
    assert atlas.travel_block(s, prologue_content) is None
    assert [o.id for o in fresh.options()] == ["move:town"]


def test_a_save_stuck_outside_the_hut_is_let_through(prologue_content, world):
    """序章沒走完卻不在草廬（內容改版、腳本改了位置）：讀檔時當作走過，不卡在引導第一步。"""
    game = Game.new(prologue_content, "沈浪", rng=random.Random(0), world=world, prologue=True)
    game.state.player.location = "town"
    again = Game(prologue_content, game.state, world=world)
    assert again.state.player.tutorial_step == prologue_content.tutorial.prologue_steps
    assert again.state.pending_event is None and not prologue.active(again.state, prologue_content)


def test_old_saves_count_as_past_the_prologue(prologue_content, world):
    game = Game.new(prologue_content, "老手", rng=random.Random(0), world=world)
    p = game.state.player
    p.onboarding, p.tutorial_step = 0, 3  # 舊引導走到第 4 步的老角色
    again = Game(prologue_content, game.state, world=world)
    assert again.state.player.tutorial_step == prologue_content.tutorial.prologue_steps
    assert again.state.player.onboarding == ONBOARDING_VERSION
    assert again.state.player.location == "town"


def test_content_without_a_prologue_leaves_old_saves_alone(content, world):
    """沒有序章的內容：舊存檔的步數照舊編號、不蓋章（preflight F6）。"""
    game = Game.new(content, "老手", rng=random.Random(0), world=world)
    p = game.state.player
    p.onboarding, p.tutorial_step = 0, 2
    again = Game(content, game.state, world=world)
    assert again.state.player.tutorial_step == 2 and again.state.player.onboarding == 0


def test_migrated_step_keeps_the_old_season_one_steps(prologue_content):
    from tianxia.state import PlayerState

    old = PlayerState(name="甲", location="town", stats={}, stamina=0, tutorial_step=7)  # 舊引導第 8 步（t8）
    assert prologue.migrated_step(old, prologue_content) == 11 + 1
    old.tutorial_step = 2
    assert prologue.migrated_step(old, prologue_content) == 11


def test_new_character_in_season_two_still_starts_in_the_hut(prologue_content, world):
    next_season(prologue_content, world)
    late = Game.new(prologue_content, "晚到", rng=random.Random(0), world=world, prologue=True)
    assert late.state.player.season_number == 2
    assert late.state.player.location == "hut" and late.state.pending_event == "p_ambush"
    assert late.state.player.stamina == prologue.start_stamina(prologue_content)
    bot = Game.new(prologue_content, "晚到假人", rng=random.Random(0), world=world)
    assert bot.state.player.location == "town" and bot.state.pending_event is None
    assert bot.state.player.stamina == prologue_content.config.stamina_max  # 換季重來把體力放成序章的，假人要拿回滿的


def test_mid_prologue_season_change_restarts_the_prologue(prologue_content, world):
    game = Game.new(prologue_content, "沈浪", rng=random.Random(0), world=world, prologue=True)
    game.state.player.tutorial_step = 4
    next_season(prologue_content, world, game)
    p = game.state.player
    assert p.location == "hut" and p.tutorial_step == 0 and game.state.pending_event == "p_ambush"


def test_old_save_reset_keeps_its_season_one_step(prologue_content, world):
    """舊存檔換季：用換算過的步數判斷要不要保留（Review Focus 1）。舊引導第 7 步（t8）＝新的第 12 步。"""
    game = Game.new(prologue_content, "老手", rng=random.Random(0), world=world)
    game.state.player.onboarding, game.state.player.tutorial_step = 0, 7
    next_season(prologue_content, world, game)
    assert game.state.player.location == "town" and game.state.player.tutorial_step == 12


def test_finished_prologue_survives_a_season(prologue_content, world):
    game = Game.new(prologue_content, "沈浪", rng=random.Random(0), world=world, prologue=True)
    prologue.finish(game.state, prologue_content, world, purse=False)
    next_season(prologue_content, world, game)
    assert game.state.player.location == "town"
    assert game.state.player.tutorial_step >= prologue_content.tutorial.prologue_steps


def test_skip_from_the_hut_lands_in_town_with_the_purse(fresh):
    silver = fresh.state.player.stats["silver"]
    fresh.skip_tutorial()
    p = fresh.state.player
    assert p.location == "town" and fresh.state.pending_event is None
    assert p.stats["silver"] == silver + 30  # 出師那一步的獎勵（設計 7.3：略過的人也拿盤纏）
    assert p.stamina == fresh.content.config.stamina_max
    assert p.guide_skipped


# ── 引導與對話框跟著序章走 ─────────────────────────────────

def _walk(game, *option_ids):
    for oid in option_ids:
        game.choose(oid)


def _to_step(game, n: int) -> None:
    """照正常的玩法把序章走到第 n 步開頭（0 起算）：遇險、拜師、看修練頁、探索選松林、合成、換上並練到第三成……
    （只寫到第 5 步：後面的要等序章的探索、合成、遊歷安排好結果才走得過，第 4 個 task 接著補。）
    每一輪都要真的前進一步：卡住就當場失敗，不要無窮迴圈。"""
    script = [
        lambda g: _walk(g, "choice:0", "choice:0"),  # 0 → 1
        lambda g: g.view_tab("practice"),  # 1 → 2
        lambda g: _walk(g, "act:explore", "choice:0"),  # 2 → 3：松林，悟到風
        lambda g: g.forge("basic_fist", ["feng"]),  # 3 → 4：穿林腿
        lambda g: (g.switch_art(_fused(g)), g.practice("武學"), g.practice("武學")),  # 4 → 5：換上、練到第三成
    ]
    while game.state.player.tutorial_step < n:
        before = game.state.player.tutorial_step
        script[before](game)
        assert game.state.player.tutorial_step > before, f"序章卡在第 {before + 1} 步"


def _fused(game) -> str:
    return prologue.fused_arts(game.state, game.content, game.world)[0].id


def test_first_step_has_no_box_and_choosing_moves_on(fresh):
    assert fresh.guide_box() is None  # 還沒遇到師父
    _walk(fresh, "choice:0")  # 擋 → 接著端出拜師那一則
    assert fresh.state.pending_event == "p_apprentice"
    assert fresh.guide_box() is None  # 序章的事件端出來時，畫面就是那則事件
    _walk(fresh, "choice:0")  # 拜師
    box = fresh.guide_box()
    assert box["speaker"] == "師父" and box["text"] == "去看修練頁。" and box["line"] == "師父：看修練頁"
    assert box["scene"] == "" and box["done"] == ["✔ 引導完成"] and box["end"] is False
    assert fresh.prologue_view() == {
        "reveal": ["tab:jianghu", "tab:practice", "xinde"], "glow": ["tab:practice"], "skip": False,
    }


def test_the_first_choice_does_not_finish_step_one_early(fresh):
    """第一步要「選了事件的選項」加上拜了師：只擋下亂民還沒算，要等拜師那一則。"""
    _walk(fresh, "choice:1")  # 喊
    assert fresh.state.player.tutorial_step == 0 and "序章:喊" in fresh.state.player.flags


def test_opening_the_practice_tab_finishes_step_two(fresh):
    _walk(fresh, "choice:0", "choice:0")
    fresh.view_tab("practice")
    assert fresh.state.player.tutorial_step == 2
    assert fresh.guide_box()["text"] == "去探索。"
    fresh.view_tab("practice")  # 連按兩下、開兩個分頁：不會多走一步
    assert fresh.state.player.tutorial_step == 2


def test_view_tab_ignores_unknown_tabs(fresh):
    _walk(fresh, "choice:0", "choice:0")
    fresh.view_tab("nowhere")
    assert "看過:nowhere" not in fresh.state.player.flags
    assert fresh.state.player.tutorial_step == 1


def test_view_tab_does_not_change_the_latest_card(fresh):
    """打開修練頁不寫紀錄、不換「剛剛」：引導的那幾行接在最新一則的 guide。"""
    _walk(fresh, "choice:0", "choice:0")
    entries = len(fresh.state.journal)
    before = fresh.state.journal[0]
    fresh.view_tab("practice")
    latest = fresh.state.journal[0]
    assert len(fresh.state.journal) == entries
    assert (latest.title, latest.lines, latest.changes) == (before.title, before.lines, before.changes)  # 「剛剛」沒換
    assert latest.guide[-2:] == ["✔ 引導完成", "【師父】去探索。"]  # 引導的那幾行接在最新一則的 guide


def test_skip_link_only_on_the_first_step(fresh):
    assert fresh.prologue_view()["skip"] is True
    _walk(fresh, "choice:0", "choice:0")
    assert fresh.prologue_view()["skip"] is False


def test_outside_the_prologue_there_is_nothing_to_reveal(prologue_content):
    bot = Game.new(prologue_content, "路人", rng=random.Random(0))
    assert bot.prologue_view() is None


def test_each_step_can_have_its_own_speaker(fresh, prologue_content):
    """框上寫的人照這一步（TutorialStep.speaker）；完成後記給對話框的 ✔ 與獎勵不帶說話的人那一行。"""
    prologue_content.tutorial.steps[1].speaker = "旁人"
    _walk(fresh, "choice:0", "choice:0")
    assert fresh.guide_box()["speaker"] == "旁人"
    fresh.view_tab("practice")
    assert fresh.guide_box()["speaker"] == "師父" and fresh.guide_box()["done"] == ["✔ 引導完成"]


def test_the_fused_goals_need_a_fused_art(fresh):
    """done_when 的 fused／fused_level：有一門合成出來的武學、而且練到第幾成才算。"""
    from tianxia import guide

    steps = fresh.content.tutorial.steps
    s, c = fresh.state, fresh.content
    assert not guide._step_done(s, c, fresh.world, steps[3], "x")  # 還沒合成
    s.player.insights = ["feng"]
    fresh.forge("basic_fist", ["feng"])
    assert prologue.fused_arts(s, c, fresh.world) and guide._step_done(s, c, fresh.world, steps[3], "x")
    assert not guide._step_done(s, c, fresh.world, steps[4], "x")  # 還在庫裡、第一成
    fresh.switch_art(_fused(fresh))
    s.player.member.wugong_level = 3
    assert guide._step_done(s, c, fresh.world, steps[4], "x")


def test_give_art_gives_it_once_at_the_written_level(fresh, prologue_content):
    from tianxia import library
    from tianxia.models import GiveArt

    s, c = fresh.state, prologue_content
    msgs = prologue.give_art(s, c, fresh.world, GiveArt(id="junk", level=5))
    assert msgs and "junk" in library.owned_arts(s) and library.level_of(s, "junk") == 5
    assert prologue.give_art(s, c, fresh.world, GiveArt(id="junk", level=5)) == []  # 已經有了：不再給


def test_allocating_a_point_finishes_its_step(fresh):
    fresh.state.player.tutorial_step, fresh.state.player.stat_points = 8, 1
    fresh.allocate_stat("str")
    assert fresh.state.player.tutorial_step == 9
    assert fresh.state.journal[0].guide[-2:] == ["✔ 引導完成", "【師父】把蠻牛拳熔了。"]


def test_melting_finishes_its_step(fresh, prologue_content):
    from tianxia.models import GiveArt

    prologue.give_art(fresh.state, prologue_content, fresh.world, GiveArt(id="junk", level=5))
    fresh.state.player.tutorial_step, fresh.state.pending_event = 9, None  # 直接跳到這一步：開場的遇險不用演
    fresh.melt_art("junk")
    assert fresh.state.player.tutorial_step == 10
    assert fresh.guide_box()["text"] == "去城裡吧。"


def test_cultivating_finishes_the_quality_step(fresh):
    from conftest import FixedRandom

    fresh.state.player.insights = ["feng"]
    fresh.forge("basic_fist", ["feng"])
    fresh.switch_art(_fused(fresh))
    fresh.state.player.tutorial_step = 5
    fresh.rng = FixedRandom(0.0)  # 一定升品
    fresh.cultivate(_fused(fresh))
    assert prologue.fused_arts(fresh.state, fresh.content, fresh.world)[0].quality == "中品"
    assert fresh.state.player.tutorial_step == 6


@pytest.mark.skip(reason="序章的探索與合成要 task 4、5 才安排好（四景、師門配方）")
def test_box_fills_in_the_fused_art(fresh):
    _to_step(fresh, 4)  # 合成完、換上之前
    assert "【穿林腿】" in fresh.guide_box()["text"]


def test_fill_leaves_text_alone_until_something_is_fused(fresh, prologue_content):
    assert prologue.fill("練【{武學}】", fresh.state, prologue_content, fresh.world) == "練【新武學】"
    assert prologue.fill("沒有佔位", fresh.state, prologue_content, fresh.world) == "沒有佔位"


def test_main_view_sends_the_prologue(fresh):
    import server

    view = server.main_view(fresh)
    assert view["prologue"]["reveal"] == [] and view["prologue"]["skip"] is True
    assert view["guide"] is None
    other = Game.new(fresh.content, "路人", rng=random.Random(0))
    assert server.main_view(other)["prologue"] is None


def test_the_view_tab_action_reaches_the_game(fresh):
    import server

    _walk(fresh, "choice:0", "choice:0")
    server.MAIN_ACTIONS["view_tab"](fresh, {"tab": "practice"})
    assert fresh.state.player.tutorial_step == 2
    server.MAIN_ACTIONS["view_tab"](fresh, {})  # 沒帶分頁：什麼都不做
    assert fresh.state.player.tutorial_step == 2
