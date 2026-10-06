"""序章（新手引導計畫一）：進出序章、草廬只給序章裡的人、舊存檔與換季。"""
import json
import random

import pytest
from conftest import next_season

from tianxia import atlas, prologue
from tianxia.content import load_content
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


def test_the_allow_lists_only_name_ids_the_code_really_makes():
    """models.ALLOW_FIXED／ALLOW_FAMILIES 是照 engine.py、foreshadow.py 做得出來的閒著選單 id 列的：每一筆都要真的出現在原始碼的
    字串裡（不憑空多寫）。反過來有沒有漏列，由 test_real_content 整季隨機玩、對照每一個閒著的選單。"""
    import ast
    from pathlib import Path

    from tianxia import models

    package, found = Path(models.__file__).parent, set()
    for name in ("engine.py", "foreshadow.py"):
        for node in ast.walk(ast.parse((package / name).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found.add(node.value)  # f"call:{id}" 的 "call:" 也是一個字串常數
    assert models.ALLOW_FIXED <= found
    assert set(models.ALLOW_FAMILIES) <= found


def test_the_hut_does_not_change_the_terrain(prologue_content, content):
    """草廬只有序章裡的一個人看得到：它不能把整張地圖的山與樹換掉（mapart 的地形鍵不算它）。"""
    from tianxia import mapart

    assert mapart._terrain_key(prologue_content) == mapart._terrain_key(content)
    assert [p.svg for p in mapart.terrain(prologue_content)] == [p.svg for p in mapart.terrain(content)]


def test_a_hut_that_sorts_after_the_start_adds_no_road_to_the_terrain(prologue_root, content):
    """mapart._obstacles 只收 a_id < b_id 的路：草廬叫 hut 時排在 town 前面，那一條路本來就被略過，擋不擋它都看不出來。
    換成排在 town 後面的 zhulu，草廬的路只靠「連到草廬的路不算」那一行擋住。"""
    from tianxia import mapart

    for name in ("locations.json", "tutorial.json"):
        path = prologue_root / name
        path.write_text(path.read_text(encoding="utf-8").replace('"hut"', '"zhulu"'), encoding="utf-8")
    renamed = load_content(prologue_root)
    assert renamed.tutorial.location == "zhulu" and "town" < "zhulu"
    assert mapart._obstacles(renamed) == mapart._obstacles(content)
    assert mapart._terrain_key(renamed) == mapart._terrain_key(content)


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


def test_a_human_past_the_prologue_is_never_sent_back_to_the_hut(prologue_root, world):
    """序章走完、後面還有一步沒做完（內容改版多出來的）：換季回到起點，從序章之後的起始步重來，不回草廬；
    序章走到一半的人照舊回草廬第一步。"""
    path = prologue_root / "tutorial.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["steps"].append({"id": "p12", "text": "再逛逛。", "done_when": {"action": "explore"}})
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    content = load_content(prologue_root)
    past = Game.new(content, "走完的", rng=random.Random(0), world=world)  # 站在起點、步數 11（序章算走過）
    half = Game.new(content, "半途的", rng=random.Random(0), world=world, prologue=True)
    half.state.player.tutorial_step = 4
    assert past.state.player.tutorial_step == 11 < len(content.tutorial.steps)
    next_season(content, world, past, half)
    p = past.state.player
    assert p.location == "town" and past.state.pending_event is None
    assert p.tutorial_step == 11 and p.stamina == content.config.stamina_max
    assert half.state.player.location == "hut" and half.state.player.tutorial_step == 0


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
    """照正常的玩法把序章走到第 n 步開頭（0 起算）：遇險、拜師、看修練頁、探索選松林、合成、換上並練到第三成、修練、打坐、
    雪恥一戰、配點、熔雜學。每一輪都要真的前進一步：卡住就當場失敗，不要無窮迴圈。"""
    script = [
        lambda g: _walk(g, "choice:0", "choice:0"),  # 0 → 1
        lambda g: g.view_tab("practice"),  # 1 → 2
        lambda g: _walk(g, "act:explore", "choice:0"),  # 2 → 3：松林，悟到風
        lambda g: g.forge("basic_fist", ["feng"]),  # 3 → 4：穿林腿
        lambda g: (g.switch_art(_fused(g)), g.practice("武學"), g.practice("武學")),  # 4 → 5：換上、練到第三成
        lambda g: g.cultivate(_fused(g)),  # 5 → 6：一定升中品
        lambda g: _walk(g, "act:rest"),  # 6 → 7：體力見底，一坐就回滿
        lambda g: _walk(g, "act:train"),  # 7 → 8：險勝斷眉，掉出一門雜學
        lambda g: g.allocate_stat("str"),  # 8 → 9：升到第 2 級的那一點
        lambda g: g.melt_art("junk"),  # 9 → 10：熔掉雜學
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


def test_the_reveal_accumulates_over_the_steps(fresh):
    """畫面上亮起來的東西一路累積：前面幾步亮的照舊亮著，只有「發光」是這一步的。"""
    fresh.state.pending_event = None
    fresh.state.player.tutorial_step = 3  # 第 4 步：去合成（reveal 只寫了 tab:craft）
    view = fresh.prologue_view()
    assert view["reveal"] == ["act:explore", "stamina", "tab:craft", "tab:jianghu", "tab:practice", "xinde"]
    assert view["glow"] == ["tab:craft", "forge"]
    fresh.state.player.tutorial_step = 6  # 第 7 步：打坐（reveal 只寫了 act:rest）
    assert prologue.view(fresh.state, fresh.content)["reveal"] == [
        "act:explore", "act:rest", "stamina", "tab:craft", "tab:jianghu", "tab:practice", "xinde",
    ]


def test_skip_link_only_on_the_first_step(fresh):
    assert fresh.prologue_view()["skip"] is True
    _walk(fresh, "choice:0", "choice:0")
    assert fresh.prologue_view()["skip"] is False


def test_outside_the_prologue_there_is_nothing_to_reveal(prologue_content):
    bot = Game.new(prologue_content, "路人", rng=random.Random(0))
    assert bot.prologue_view() is None


def test_each_step_can_have_its_own_speaker(fresh, prologue_content):
    """框上寫的人照這一步（TutorialStep.speaker）；完成上一步後記給對話框的 ✔ 與獎勵，不帶「下一步誰說的話」那一行——
    那一行的人是這一步的旁人，不是預設的師父（_note_guide 要把每一個說話的人都認出來）。"""
    prologue_content.tutorial.steps[1].speaker = "旁人"
    _walk(fresh, "choice:0", "choice:0")  # 完成第 1 步，輪到旁人說第 2 步
    box = fresh.guide_box()
    assert box["speaker"] == "旁人" and box["text"] == "去看修練頁。"
    assert box["done"] == ["✔ 引導完成"]  # 「【旁人】去看修練頁。」不在裡面
    assert fresh.state.journal[0].guide[-1] == "【旁人】去看修練頁。"  # 江湖紀錄照舊寫那一行
    fresh.view_tab("practice")  # 完成第 2 步，輪到預設的師父
    box = fresh.guide_box()
    assert box["speaker"] == "師父" and box["done"] == ["✔ 引導完成"]


def test_the_fused_goals_need_a_fused_art(fresh):
    """done_when 的 fused／fused_level：有一門合成出來的武學、而且練到第幾成才算。"""
    from tianxia import guide

    steps = fresh.content.tutorial.steps
    s, c = fresh.state, fresh.content
    assert not guide._step_done(s, c, fresh.world, steps[3], "x")  # 還沒合成
    s.player.insights, s.player.tutorial_step = ["feng"], 3  # 序章只准在合成那一步開爐
    fresh.forge("basic_fist", ["feng"])
    assert prologue.fused_arts(s, c, fresh.world) and guide._step_done(s, c, fresh.world, steps[3], "x")
    assert not guide._step_done(s, c, fresh.world, steps[4], "x")  # 還在庫裡、第一成
    fresh.switch_art(_fused(fresh))
    s.player.member.wugong_level = 3
    assert guide._step_done(s, c, fresh.world, steps[4], "x")


def _wear_a_fused_art(game) -> str:
    """合成一門、換上身（第一成、下品）：序章第 5、6 步的起點。回傳那一門的 id。"""
    game.state.player.insights, game.state.player.tutorial_step = ["feng"], 3  # 序章只准在合成那一步開爐
    game.state.pending_event = None  # 開場的遇險不用演
    game.forge("basic_fist", ["feng"])
    game.switch_art(_fused(game))
    return _fused(game)


def test_the_level_goal_needs_the_level(fresh):
    from tianxia import guide

    s, c = fresh.state, fresh.content
    _wear_a_fused_art(fresh)
    s.player.tutorial_step = 4  # 第 5 步：換上、練到第三成
    s.player.member.wugong_level = 2
    assert guide.note_action(s, c, fresh.world, "practice") == [] and s.player.tutorial_step == 4
    s.player.member.wugong_level = 3
    assert "✔ 引導完成" in guide.note_action(s, c, fresh.world, "practice") and s.player.tutorial_step == 5


def test_the_quality_goal_needs_a_promotion_not_just_the_level(fresh):
    """第 6 步：成數夠了、身上也是合成的那一門，但還是下品、沒升品，不算完成；升了中品才算。"""
    from tianxia import guide

    s, c = fresh.state, fresh.content
    art_id = _wear_a_fused_art(fresh)
    s.player.member.wugong_level = 3
    s.player.tutorial_step = 5
    assert guide.note_action(s, c, fresh.world, "cultivate") == [] and s.player.tutorial_step == 5
    s.player.art_quality[art_id] = "中品"  # 升了品
    assert "✔ 引導完成" in guide.note_action(s, c, fresh.world, "cultivate") and s.player.tutorial_step == 6


def test_finishing_a_step_gives_its_art(fresh):
    """序章第 8 步（雪恥一戰）做完就掉出那門雜學：第五成、收進功法庫（身上的武學欄已經有合成的那一門）。"""
    from tianxia import guide, library

    s, c = fresh.state, fresh.content
    s.pending_event, s.player.tutorial_step = None, 7
    msgs = guide.note_action(s, c, fresh.world, "train")
    assert s.player.tutorial_step == 8
    assert library.level_of(s, "junk") == 5
    assert "✔ 引導完成" in msgs and any("蠻牛拳" in m for m in msgs)


def test_the_box_and_the_next_step_line_name_the_fused_art(fresh):
    """{武學} 換成合成出來的那一門：對話框的話與完成上一步時記在江湖紀錄裡的那一行都一樣。"""
    s = fresh.state
    s.pending_event, s.player.tutorial_step, s.player.insights = None, 3, ["feng"]
    fresh.forge("basic_fist", ["feng"])
    assert s.player.tutorial_step == 4
    name = prologue.fused_arts(s, fresh.content, fresh.world)[0].name
    line = f"把【{name}】換上，練到第三成。"
    assert fresh.guide_box()["text"] == line
    assert s.journal[0].guide[-1] == f"【師父】{line}"


def test_a_step_without_words_writes_no_blank_speaker_line(fresh, prologue_content):
    """序章第一步沒有話（還沒遇到師父）：開場那一則的 guide、對話框、完成上一步時接下去的那一行，都不會有空空的「【師父】」。"""
    from tianxia import guide

    assert guide.tutorial_intro(prologue_content) == []
    assert fresh.state.journal[-1].guide == []  # 開場那一則
    assert "【師父】" not in fresh.state.log
    fresh.state.pending_event = None  # 沒有事件擋著：話是空的就不畫框
    assert fresh.guide_box() is None
    prologue_content.tutorial.steps[1].text = ""  # 第 2 步也沒有話：完成第 1 步時不接那一行
    fresh.state.pending_event = "p_ambush"
    _walk(fresh, "choice:0", "choice:0")
    assert fresh.state.player.tutorial_step == 1
    assert fresh.state.journal[0].guide == ["✔ 引導完成"]
    assert fresh.guide_box() is None


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

    art_id = _wear_a_fused_art(fresh)
    fresh.state.player.tutorial_step = 5
    fresh.rng = FixedRandom(0.99)  # 平常的擲骰一定落空；序章這一步的修練不看它（prologue.sure_rng）
    fresh.cultivate(art_id)
    assert fresh.state.player.art_quality[art_id] == "中品"
    assert fresh.state.player.tutorial_step == 6


@pytest.mark.skip(reason="師門配方（Task 5）才有穿林腿這個名字")
def test_box_fills_in_the_fused_art(fresh):
    _to_step(fresh, 4)  # 合成完、換上之前：松林的風，師門配方叫穿林腿
    assert fresh.guide_box()["text"] == "把【穿林腿】換上，練到第三成。"


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


# ── 序章裡安排好的結果（計畫一 Task 4）──────────────────────

def test_exploring_in_the_hut_always_offers_the_four_sights(fresh):
    _to_step(fresh, 2)
    fresh.choose("act:explore")
    assert fresh.state.pending_event == "p_insight"
    fresh.choose("choice:2")  # 溪水
    assert fresh.state.player.insights == ["shui"]
    assert fresh.state.player.tutorial_step == 3


def test_exploring_in_the_hut_never_finds_a_legend_pill(fresh):
    fresh.content.config.explore_legend_chance = 1.0  # 平常每次探索都撿得到
    _to_step(fresh, 2)
    fresh.choose("act:explore")
    assert fresh.state.player.legend_items == 0


def test_only_the_step_actions_are_on_the_menu(fresh):
    _to_step(fresh, 2)
    assert [o.id for o in fresh.options()] == ["act:explore"]
    _to_step(fresh, 6)
    assert [o.id for o in fresh.options()] == ["act:rest"]


def test_the_hut_never_rolls_for_story_fragments_after_a_costly_action(fresh, monkeypatch):
    """伏筆與機緣的線索是真實世界的事：草廬裡花了體力也不抽（_hear_after_stamina）。"""
    from tianxia import foreshadow, opportunities

    heard = []
    monkeypatch.setattr(foreshadow, "active", lambda s, c: True)
    monkeypatch.setattr(foreshadow, "hear_after_action", lambda *a, **k: heard.append("fs") or ["伏筆"])
    monkeypatch.setattr(opportunities, "active", lambda s, c: True)
    monkeypatch.setattr(opportunities, "hear_clues", lambda *a, **k: heard.append("opp") or ["線索"])
    _to_step(fresh, 2)
    fresh.choose("act:explore")
    assert heard == []


def test_prologue_practice_never_injures(fresh):
    _to_step(fresh, 4)
    fresh.content.config.practice_injury_chance = 1.0
    fresh.switch_art(_fused(fresh))
    fresh.practice("武學")
    assert fresh.state.player.member.injury == 0
    assert fresh.state.player.member.wugong_level == 2  # 真的練了一成


def test_safe_practice_does_not_even_roll_for_an_injury(prologue_content, world):
    """team.practice 的 safe：不傷人、也不擲那一次亂數（既有的亂數序列只在序章裡少一次）。"""
    from tianxia import team
    from tianxia.state import new_game_state

    class NoRoll(random.Random):
        def random(self):
            raise AssertionError("安全的練功不該擲受傷")

    prologue_content.config.practice_injury_chance = 1.0
    state = new_game_state(prologue_content, "甲")
    team.practice(state, prologue_content, world, "武學", NoRoll(), safe=True)
    assert state.player.member.injury == 0 and state.player.member.wugong_level == 2
    hurt = new_game_state(prologue_content, "乙")
    team.practice(hurt, prologue_content, world, "武學", random.Random(0))
    assert hurt.player.member.injury > 0  # 不安全的照舊會傷


def test_sure_cultivate_only_once(fresh):
    from conftest import FixedRandom

    _to_step(fresh, 5)
    art = _fused(fresh)
    fresh.rng = FixedRandom(0.99)  # 平常的擲骰一定落空
    fresh.cultivate(art)
    assert fresh.state.player.art_quality[art] == "中品"
    assert fresh.state.player.tutorial_step == 6
    assert prologue.sure_rng(fresh.state, fresh.content) is None  # 下一步不再保證
    stamina = fresh.state.player.stamina
    assert "師父" in fresh.cultivate(art)[0] and fresh.state.player.stamina == stamina  # 序章裡下一步沒叫你修練：擋下、不花體力
    outside = Game.new(fresh.content, "路人", rng=random.Random(0))
    assert prologue.sure_rng(outside.state, outside.content) is None  # 序章外沒有任何保證


def test_rest_refills_at_once(fresh):
    _to_step(fresh, 6)
    assert fresh.state.player.stamina == 0
    msgs = fresh.choose("act:rest")
    assert fresh.state.player.stamina == fresh.content.config.stamina_max
    assert fresh.state.player.resting_since is None
    assert "你坐下，又有了力氣。" in msgs
    assert fresh.state.player.tutorial_step == 7


def test_rest_outside_the_prologue_still_waits(prologue_content):
    outside = Game.new(prologue_content, "路人", rng=random.Random(0))
    outside.state.player.stamina = 0
    outside.choose("act:rest")
    assert outside.state.player.resting_since is not None and outside.state.player.stamina == 0


def test_revenge_is_a_narrow_win_with_nothing_extra(fresh, monkeypatch):
    from tianxia import foreshadow
    from tianxia.models import Choice, Drop, Effect, Event

    content = fresh.content
    content.squads["duanmei"].difficulty = 90  # 本來新手打不贏：險勝是寫好的，不是擲出來的
    content.squads["duanmei"].drops = [Drop(material="gang_1", chance=1.0)]  # 平常打贏一定掉
    content.locations["hut"].train_trend = {"kou": 3}  # 平常打贏會推大勢
    content.config.train_event_chance = 1.0  # 平常打完會接戰後事件
    content.events["afterglow"] = Event(
        id="afterglow", title="餘韻", text="打鬥剛歇。", actions=["train"], choices=[Choice(text="嗯", effect=Effect(text="嗯。"))],
    )
    touched = []
    monkeypatch.setattr(foreshadow, "after_win", lambda *a, **k: touched.append("伏筆") or [])
    monkeypatch.setattr(fresh, "push_trend", lambda *a, **k: touched.append("大勢") or [])
    monkeypatch.setattr(fresh, "_order_credit", lambda **k: touched.append("軍令") or [])
    _to_step(fresh, 7)
    assert [o.id for o in fresh.options()] == ["act:train"]
    fresh.choose("act:train")
    assert fresh.state.battles[0].tier == "險勝"  # 戰報最新的在最前面（battlelog.add_record）
    assert fresh.state.pending_event is None  # 沒有接戰後事件
    assert fresh.state.player.materials == {}  # 不掉素材
    assert touched == []  # 不推大勢、不抽伏筆、不記軍令
    p = fresh.state.player
    assert p.tutorial_step == 8 and p.stat_points == 1  # 升到第 2 級
    assert "junk" in p.arts and p.art_levels["junk"] == 5


def test_the_revenge_button_promises_no_odds(fresh):
    """雪恥那一場的勝負是寫好的：按鈕不寫勝算（算出來可能是「凶險」，跟安排好的險勝對不上）；序章外的遊歷照舊寫。"""
    words = ("穩勝", "有把握", "五五波", "難分勝負", "凶險", "必敗")
    fresh.content.squads["duanmei"].difficulty = 90
    _to_step(fresh, 7)
    label = next(o.label for o in fresh.options(odds=True) if o.id == "act:train")
    assert "斷眉" in label and not any(word in label for word in words)
    outside = Game.new(fresh.content, "路人", rng=random.Random(0))
    outside.state.player.location = "lake"
    label = next(o.label for o in outside.options(odds=True) if o.id == "act:train")
    assert any(word in label for word in words)


def test_the_scripted_tier_comes_before_the_life_guard(prologue_content, world, monkeypatch):
    """team.fight 的 tier：護命（no_loss）會把落敗改判僵持、並標 guarded；寫好的結果在它之前，所以不被它動、也不標 guarded。"""
    from conftest import FixedRandom
    from tianxia import team, traits
    from tianxia.state import new_game_state

    state = new_game_state(prologue_content, "甲")
    monkeypatch.setattr(traits, "loadout", lambda *a: traits.Loadout(specials={"no_loss": object()}))
    natural = team.fight(state, prologue_content, world, "boss", FixedRandom(0.5))
    assert natural.tier == "僵持" and natural.guarded  # 難度 200 的對手本來會落敗：護命接住
    scripted = team.fight(state, prologue_content, world, "boss", FixedRandom(0.5), tier="險勝")
    assert scripted.tier == "險勝" and not scripted.guarded


def test_the_hut_gives_no_road_sight_and_the_farewell_line_comes_once(fresh):
    fresh.content.config.road_sight_chance = 1.0  # 平常每一段新的路都看得到見聞
    _to_step(fresh, 10)
    silver = fresh.state.player.stats["silver"]
    fresh.choose("move:town")
    msgs = fresh.advance(fresh.state.player.journey.arrive_at[-1] - fresh.state.world.time)
    p = fresh.state.player
    assert p.location == "town" and p.tutorial_step == 11
    assert p.recent_sights == []  # 出師那段路不抽路上見聞
    assert p.stats["silver"] == silver + 30 and p.stamina == fresh.content.config.stamina_max
    assert "\n".join(msgs).count("草廬已經看不見了。") == 1
    assert not prologue.active(fresh.state, fresh.content)
    assert all(not o.id.startswith("move:hut") for o in fresh.options())


def test_the_farewell_line_is_only_for_leaving_the_hut(prologue_content):
    bot = Game.new(prologue_content, "路人", rng=random.Random(0))  # 不走序章的人：到哪都不會有那一句
    bot.choose("move:lake")
    msgs = bot.advance(bot.state.player.journey.arrive_at[-1] - bot.state.world.time)
    assert "草廬已經看不見了。" not in "\n".join(msgs)


def test_prologue_refuses_off_script_moves(fresh):
    _to_step(fresh, 3)
    before, level = fresh.state.player.stats["xinde"], fresh.state.player.member.wugong_level
    fresh.forge("basic_breath", ["feng"])  # 拿別的底合成：擋下、不收心得
    fresh.forge(None, ["feng", "feng"])  # 合併：序章裡也擋
    fresh.forge("basic_fist", [], other_art="basic_breath")  # 兩門武學合成：也擋
    assert fresh.state.player.stats["xinde"] == before and fresh.state.player.tutorial_step == 3
    fresh.melt_insight("feng")
    assert fresh.state.player.insights == ["feng"]  # 序章裡不熔意境
    fresh.practice("武學")  # 這一步沒叫你練功（F11）：不花心得
    fresh.cultivate("basic_fist")  # 這一步沒叫你修練：不花體力
    assert fresh.state.player.stats["xinde"] == before and fresh.state.player.member.wugong_level == level
    _to_step(fresh, 4)
    cost = fresh.state.player.stats["xinde"]
    fresh.practice("武學")  # 練功那一步，但身上還是基本功：要練的是新得的那一門（F11）
    fresh.practice("內功")
    assert fresh.state.player.stats["xinde"] == cost and fresh.state.player.member.wugong_level == level
    _to_step(fresh, 9)
    fresh.melt_art("basic_fist")
    assert "basic_fist" in fresh.state.player.arts  # 只准熔雜學
    fresh.melt_art("junk")
    assert "junk" not in fresh.state.player.arts and fresh.state.player.tutorial_step == 10


def test_the_forge_does_not_ask_the_model_for_a_move_the_hut_refuses(fresh):
    _to_step(fresh, 3)
    assert fresh.forge_request("basic_breath", ["feng"]) is None  # 擋下的合成不開取名的單子
    assert fresh.forge_request(None, ["feng", "feng"]) is None
    line = fresh.forge_line("basic_breath", ["feng"])
    assert line.startswith("⚠") and "師父" in line


def test_melt_and_cultivate_buttons_follow_the_script(fresh):
    """修練頁的按鈕與動作的拒絕走同一個判斷（skillview.art_rows）：序章裡不能熔的、不能修練的，按鈕按不下去、寫原因。"""
    _to_step(fresh, 9)
    rows = {row["id"]: row for row in fresh.art_rows()}
    assert rows["junk"]["melt"]["ok"] and "退回心得" in rows["junk"]["melt"]["note"]
    assert not rows["basic_fist"]["melt"]["ok"] and "師父" in rows["basic_fist"]["melt"]["note"]
    assert not any(row["cultivate"]["ok"] for row in rows.values())  # 第 10 步沒叫你修練
    outside = Game.new(fresh.content, "路人", rng=random.Random(0))
    assert "師父" not in "".join(row["melt"]["note"] for row in outside.art_rows())


def test_library_melt_only_limits_what_can_be_melted(prologue_content, world):
    from tianxia import library
    from tianxia.models import GiveArt
    from tianxia.state import new_game_state

    state = new_game_state(prologue_content, "甲")
    prologue.give_art(state, prologue_content, world, GiveArt(id="junk", level=1))
    state.player.arts.append("basic_breath")  # 隨便另一門庫裡的
    assert library.melt_problem(state, "junk") is None  # 沒限制（序章外）
    assert library.melt_problem(state, "junk", only="junk") is None
    assert "師父" in library.melt_problem(state, "basic_breath", only="junk")
    assert "師父" in library.melt_problem(state, "junk", only="")  # 空字串：這一步一門都不准熔


def test_cannot_leave_the_hut_before_farewell(fresh):
    _to_step(fresh, 9)
    assert fresh.travel_refusal("town", "walk") is not None
    _to_step(fresh, 10)
    assert fresh.travel_refusal("town", "walk") is None


def test_the_forge_step_takes_only_the_masters_base_and_one_insight(fresh):
    """第 4 步的合成：一門基本功（fuse_base）加一個意境，別的組合都擋；擋下的原因寫給玩家看。"""
    _to_step(fresh, 3)
    for args in (("basic_breath", ["feng"]), (None, ["feng", "feng"])):
        assert "師父" in fresh.forge(*args)[0]
    assert "師父" in fresh.forge("basic_fist", [], other_art="basic_breath")[0]
    assert "師父" in fresh.forge("basic_fist", ["feng", "shan"])[0]
    _to_step(fresh, 6)
    assert "師父" in fresh.forge("basic_fist", ["feng"])[0]  # 合成那一步過了：不再准開爐
