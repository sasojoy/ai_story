"""序章（新手引導計畫一）：進出序章、草廬只給序章裡的人、舊存檔與換季。"""
import json
import random

import pytest
from conftest import next_season

from tianxia import atlas, prologue, sensing
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
    """models.ALLOW_FIXED／ALLOW_FAMILIES 是照做得出閒著選單 id 的原始碼（engine.py、foreshadow.py、opportunities.py）列的：
    固定的每一筆要真的是原始碼裡的字串，家族每一個要真的是某個字串的開頭（不憑空多寫）。反過來有沒有漏列，這裡查不到：
    由 test_real_content 整季隨機玩、對照每一個閒著的選單（只看得到那一季玩到的 id）。"""
    import ast
    from pathlib import Path

    from tianxia import models

    package, found = Path(models.__file__).parent, set()
    for name in ("engine.py", "foreshadow.py", "opportunities.py"):
        for node in ast.walk(ast.parse((package / name).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found.add(node.value)  # f"call:{id}" 的 "call:" 也是一個字串常數
    assert models.ALLOW_FIXED <= found, sorted(models.ALLOW_FIXED - found)
    unmade = [family for family in models.ALLOW_FAMILIES if not any(text.startswith(family) for text in found)]
    assert not unmade, unmade


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


def test_a_bot_mid_prologue_is_never_sent_to_the_hut(prologue_content, world):
    """換季重來的 `and not old.player.bot`：做成假人、序章又沒走完的角色（腳本做的、或之後哪條路忘了 prologue=False）換季也不進草廬——
    進了草廬，閒著的選單只剩那一步的行動，假人就不動了；而且假人的畫面不能跟真人不一樣。"""
    from tianxia.state import BotProfile

    bot = Game.new(prologue_content, "假人甲", rng=random.Random(0), world=world, prologue=True)
    bot.state.player.bot = BotProfile(personality="普通", seed=1)
    assert prologue.active(bot.state, prologue_content)  # 現在確實在草廬、序章第一步
    next_season(prologue_content, world, bot)
    p = bot.state.player
    assert p.location == "town" and bot.state.pending_event is None
    assert p.tutorial_step == prologue_content.tutorial.prologue_steps and p.stamina == prologue_content.config.stamina_max
    assert not prologue.active(bot.state, prologue_content)


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


def _sense(game, attribute: str) -> None:
    """草廬的有所感：照屬性挑那個做法（卡上的順序每次洗牌），再順其自然（不畫，落回那個屬性的基本意境）。"""
    game.choose("act:explore")
    got = sensing.current(game.state, game.content)
    order = [got[1].methods[j].attribute for j in got[0].order]
    game.choose(f"sense:{order.index(attribute)}")
    game.choose(sensing.LET_GO)


def _to_step(game, n: int) -> None:
    """照正常的玩法把序章走到第 n 步開頭（0 起算）：遇險、拜師、看修練頁、探索選松林、合成、換上並練到第三成、修練、打坐、
    雪恥一戰、配點、熔雜學。每一輪都要真的前進一步：卡住就當場失敗，不要無窮迴圈。"""
    script = [
        lambda g: _walk(g, "choice:0", "choice:0"),  # 0 → 1
        lambda g: g.view_tab("practice"),  # 1 → 2
        lambda g: _sense(g, "快"),  # 2 → 3：松林聽風，悟到風
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
    assert box["speaker"] == "師父" and box["text"] == "去看修練頁。" and box["line"] == "看修練頁"
    assert box["scene"] == "" and box["done"] == [] and box["end"] is False
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
    assert latest.guide[-1:] == ["【師父】去探索。"] and "✔ 引導完成" not in latest.guide  # 引導的下一步接在最新一則的 guide（序章不寫「✔」）


def test_the_reveal_accumulates_over_the_steps(fresh):
    """畫面上亮起來的東西一路累積：前面幾步亮的照舊亮著，只有「發光」是這一步的。"""
    fresh.state.pending_event = None
    fresh.state.player.tutorial_step = 3  # 第 4 步：去合成（reveal 只寫了 tab:craft）
    view = fresh.prologue_view()
    assert view["reveal"] == ["act:explore", "stamina", "tab:craft", "tab:jianghu", "tab:practice", "xinde"]
    assert view["glow"] == ["tab:craft", "pick:art", "pick:insight", "forge"]
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
    assert box["done"] == []  # 「【旁人】去看修練頁。」不在裡面
    assert fresh.state.journal[0].guide[-1] == "【旁人】去看修練頁。"  # 江湖紀錄照舊寫那一行
    fresh.view_tab("practice")  # 完成第 2 步，輪到預設的師父
    box = fresh.guide_box()
    assert box["speaker"] == "師父" and box["done"] == []


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


def test_the_prologue_fusion_is_always_the_lowest_quality(fresh):
    """序章那一爐照劇本固定下品第一成，不擲品質（企劃者 2026-10-06 改成合成擲品質，序章除外）；
    說明也照劇本寫「從下品起修」，不寫機率。"""
    fresh.state.player.insights, fresh.state.player.tutorial_step = ["feng"], 3
    fresh.state.pending_event = None
    assert "從下品起修" in fresh.forge_line("basic_fist", ["feng"])
    fresh.rng.choices = lambda *a, **k: ["上品"]  # 萬一擲了就是上品
    fresh.forge("basic_fist", ["feng"])
    art = _fused(fresh)
    assert art not in fresh.state.player.art_quality and art not in fresh.state.player.art_rolled


def test_the_level_goal_needs_the_level(fresh):
    from tianxia import guide

    s, c = fresh.state, fresh.content
    _wear_a_fused_art(fresh)
    s.player.tutorial_step = 4  # 第 5 步：換上、練到第三成
    s.player.member.wugong_level = 2
    assert guide.note_action(s, c, fresh.world, "practice") == [] and s.player.tutorial_step == 4
    s.player.member.wugong_level = 3
    assert guide.note_action(s, c, fresh.world, "practice")[0].startswith("【師父】") and s.player.tutorial_step == 5


def test_the_quality_goal_needs_a_promotion_not_just_the_level(fresh):
    """第 6 步：成數夠了、身上也是合成的那一門，但還是下品、沒升品，不算完成；升了中品才算。"""
    from tianxia import guide

    s, c = fresh.state, fresh.content
    art_id = _wear_a_fused_art(fresh)
    s.player.member.wugong_level = 3
    s.player.tutorial_step = 5
    assert guide.note_action(s, c, fresh.world, "cultivate") == [] and s.player.tutorial_step == 5
    s.player.art_quality[art_id] = "中品"  # 升了品
    assert guide.note_action(s, c, fresh.world, "cultivate")[0].startswith("【師父】") and s.player.tutorial_step == 6


def test_finishing_a_step_gives_its_art(fresh):
    """序章第 8 步（雪恥一戰）做完就掉出那門雜學：第五成、收進功法庫（身上的武學欄已經有合成的那一門）。"""
    from tianxia import guide, library

    s, c = fresh.state, fresh.content
    s.pending_event, s.player.tutorial_step = None, 7
    msgs = guide.note_action(s, c, fresh.world, "train")
    assert s.player.tutorial_step == 8
    assert library.level_of(s, "junk") == 5
    assert "✔ 引導完成" not in msgs and any("蠻牛拳" in m for m in msgs)


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
    assert fresh.state.journal[0].guide == []
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
    assert fresh.state.journal[0].guide[-1:] == ["【師父】把蠻牛拳熔了。"] and "✔ 引導完成" not in fresh.state.journal[0].guide


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
    got = sensing.current(fresh.state, fresh.content)
    assert got is not None and got[1].id == "hut_four" and len(fresh.options()) == 4
    fresh.state.player.sensing = None
    fresh.state.player.stamina = 150
    _sense(fresh, "柔")  # 溪邊看水：每個做法都對、必中，順其自然落回水
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


def test_the_practice_buttons_follow_the_script(fresh):
    """review-t4-5 M6：練成鈕亮不亮跟動作的拒絕走同一個判斷（slot_cards 的 blocked）：沒叫你練功的步驟兩顆都灰、寫原因。"""
    import server

    def blocked():
        return {c["kind"]: c["blocked"] for c in server.menxia_view(fresh)["slot_cards"]}

    _to_step(fresh, 1)
    assert all(v and "師父" in v for v in blocked().values())  # 看修練頁那一步：還不能練
    _to_step(fresh, 4)  # 練成那一步，但還沒換上新得的那一門
    assert blocked()["武學"] and "換上" in blocked()["武學"]
    fresh.switch_art(_fused(fresh))
    assert blocked()["武學"] is None  # 換上之後：武學那顆亮
    assert blocked()["內功"]  # 內功還是基本功：不能練
    outside = Game.new(fresh.content, "路人", rng=random.Random(0))
    assert all(c["blocked"] is None for c in server.menxia_view(outside)["slot_cards"])


def test_the_first_screen_is_the_ambush_not_the_season_intro(fresh, prologue_content, world):
    """T6 review M8：「剛剛」那張卡在序章第一屏放的是賽季開場那一則，疊在遇險的上面，第一屏就不只有遇險與選項了。
    草廬裡不放它；選了之後的結果照常放。那一則還在江湖紀錄裡，序章走完之後它就是紀錄裡的一則。"""
    import server

    assert fresh.state.journal and fresh.state.journal[0].tag == "賽季開始"  # 紀錄裡還在
    assert fresh.now_entry_html() == "" and server.main_view(fresh)["now"] == ""
    _walk(fresh, "choice:0")
    assert fresh.now_entry_html() == ""  # 拜師的事件在眼前：整張卡不放（T7 審查 I2、I3）
    _walk(fresh, "choice:0")
    assert "好徒兒。" in fresh.now_entry_html()  # 事件了結之後，選了的結果照常放
    next_season(prologue_content, world, fresh)  # 換季重回草廬：換季重來寫的那一則開場也不放
    assert fresh.state.player.location == "hut" and fresh.now_entry_html() == ""


def _world_entries(game):
    """江湖上別人的事：江湖大事（季曆一過一個交界、新來的人第一次同步就補進來）、你不在的時候、賽季開場；都最新的在最上面。"""
    from tianxia import journal
    from tianxia.state import JournalEntry

    time = game.state.world.time
    for entry in (
        JournalEntry(time=time, title=journal.WORLD_NEWS, tag="共 4 件", lines=["第 4 週・週一 00:00　甲子年二月，三十六方同日起事。"]),
        JournalEntry(time=time, title=journal.AWAY, tag="三天", lines=["你不在的時候，江湖上發生了幾件事。"]),
    ):
        journal.add_entry(game.state, entry)


def test_the_now_card_in_the_hut_never_shows_world_news(fresh):
    """T7 審查 I2、I3：草廬裡「剛剛」只放自己這一步的結果，不放江湖大事、你不在的時候、賽季開場（紀錄裡照舊都有）；
    晚加入的第一季新人頭一次同步就被補了「江湖大事」，不能疊在遇險的畫面上面。"""
    _walk(fresh, "choice:0", "choice:0")  # 遇險、拜師：自己的結果（拜師那一則）
    own = fresh.now_entry_html()
    assert "好徒兒" in own  # 拜師的結果（fixture 的 effect 文字是「好徒兒。」）
    _world_entries(fresh)
    shown = fresh.now_entry_html()
    assert shown == own  # 世界上的事排在最上面也不頂掉它
    assert "江湖大事" not in shown and "你不在的時候" not in shown and "賽季開始" not in shown
    assert any(e.title == "江湖大事" for e in fresh.state.journal) and any("賽季開始" == e.tag for e in fresh.state.journal)  # 紀錄裡照舊有


def test_the_now_card_in_the_hut_is_empty_when_only_world_news_is_left(fresh):
    """第一屏（遇險）：紀錄裡只有賽季開場與補來的江湖大事——什麼都不放，不是放別人的事。"""
    _world_entries(fresh)
    assert fresh.now_entry_html() == ""
    import server

    assert server.main_view(fresh)["now"] == ""
    fresh.state.pending_event = None  # 事件了結了、紀錄裡還是只有別人的事（賽季開場也在其中）：照樣什麼都不放
    assert any(e.tag == "賽季開始" for e in fresh.state.journal) and fresh.now_entry_html() == ""


def test_the_now_card_is_hidden_while_a_hut_event_is_on_screen(fresh):
    """四景（或拜師）的事件在眼前時整張卡不放：它重複事件標題「遇上【…】」，還把選項擠到分頁列底下。事件了結之後照放。"""
    _walk(fresh, "choice:0")  # 擋下之後接拜師事件：事件在眼前
    assert fresh.state.pending_event and fresh.now_entry_html() == ""
    fresh.choose("choice:0")
    assert fresh.state.pending_event is None and fresh.now_entry_html() != ""
    fresh.view_tab("practice")
    fresh.choose("act:explore")  # 探索端出草廬四景（有所感）：它是一張卡，不是事件（pending_event 是空的），一樣整張「剛剛」不放
    assert fresh.state.pending_event is None and fresh.state.player.sensing is not None
    assert fresh.now_entry_html() == "" and fresh.guide_box() is None  # 師父的框也不放：畫面就是那一張卡
    sensing_choice = next(o for o in fresh.options() if o.id.startswith("sense:"))
    fresh.choose(sensing_choice.id)  # 選了做法、進了感悟狀態，還沒了結：照舊
    assert fresh.state.player.sensing is not None and fresh.now_entry_html() == "" and fresh.guide_box() is None
    fresh.choose(sensing.LET_GO)  # 了結之後兩張都回來
    assert fresh.state.player.sensing is None and fresh.now_entry_html() != "" and fresh.guide_box() is not None


def test_the_season_intro_is_still_the_card_for_everyone_outside_the_hut(prologue_content, world):
    bot = Game.new(prologue_content, "路人", rng=random.Random(0), world=world)
    assert "賽季開始" in bot.now_entry_html()


def test_the_guide_box_says_when_a_step_is_paged(fresh, prologue_content):
    """分頁的步驟（TutorialStep.paged）：guide_box 多一個 paged: True，網頁照 \\n\\n 切頁；別的步驟沒有這個鍵（既有的整份比對不變）。"""
    prologue_content.tutorial.steps[1].paged = True
    prologue_content.tutorial.steps[1].text = "第一段。\n\n第二段，去看修練頁。"
    _walk(fresh, "choice:0", "choice:0")
    box = fresh.guide_box()
    assert box["paged"] is True and box["text"].count("\n\n") == 1
    fresh.view_tab("practice")
    assert "paged" not in fresh.guide_box()


def test_only_the_art_the_master_names_is_the_switch_target(fresh):
    """步驟 5 的改練（W-A）：伺服器說哪一列是師父點名的那一門——換上之前只有合成出來的那一列要發光，換上之後沒有一列發光
    （不然被換下來的基礎拳腳會變成新的改練目標，邀人換回去）。不加新的拒絕：這只管發光。序章外的列沒有 glow 這個鍵。"""
    _to_step(fresh, 4)
    named = _fused(fresh)
    rows = {row["id"]: row for row in fresh.art_rows()}
    assert [art_id for art_id, row in rows.items() if "switch" in row["glow"]] == [named]
    fresh.switch_art(named)
    assert fresh.state.player.tutorial_step == 4  # 還在第 5 步：換上不算完成
    assert all("switch" not in row["glow"] for row in fresh.art_rows())
    assert any(row["id"] == "basic_fist" for row in fresh.art_rows())  # 被換下來的在功法庫裡
    assert fresh.switch_art("basic_fist") and fresh.state.player.member.wugong_id == "basic_fist"  # 沒有新的拒絕：想換回去還是換得了
    outside = Game.new(fresh.content, "路人", rng=random.Random(0), world=fresh.world)
    assert all("glow" not in row for row in outside.art_rows())


def test_the_server_names_which_row_each_other_glow_belongs_to(fresh):
    """修練的那一列（步驟 6）與熔煉的那一列（步驟 10）也由伺服器說：只有按得下去的那一門有那個鍵。"""
    _to_step(fresh, 5)
    named = _fused(fresh)
    assert [r["id"] for r in fresh.art_rows() if "cultivate" in r["glow"]] == [named]
    _to_step(fresh, 9)
    assert [r["id"] for r in fresh.art_rows() if "melt" in r["glow"]] == ["junk"]
    assert all("switch" not in r["glow"] for r in fresh.art_rows())  # 步驟 10 不叫人改練


def test_the_forge_pick_lists_name_what_to_put_in_the_furnace(fresh):
    """步驟 4（煉製頁）：師父點名的底（基礎拳腳）與剛悟到的意境，在挑選清單裡由伺服器標出來（pick:art、pick:insight），
    網頁照它讓兩樣發光、直到放進爐子；別的武學、別的步驟都沒有。"""
    _to_step(fresh, 3)
    rows = fresh.art_rows()
    assert [r["id"] for r in rows if "pick:art" in r["glow"]] == ["basic_fist"]
    assert [i["id"] for i in fresh.insight_rows() if "pick:insight" in i["glow"]] == fresh.state.player.insights
    _to_step(fresh, 4)
    assert not any("pick:art" in r["glow"] for r in fresh.art_rows())
    assert not any("pick:insight" in i["glow"] for i in fresh.insight_rows())
    outside = Game.new(fresh.content, "路人", rng=random.Random(0), world=fresh.world)
    outside.state.player.insights.append("feng")
    assert all("glow" not in i for i in outside.insight_rows())


def test_the_preview_says_a_preset_recipe_is_the_masters_way(fresh):
    """W-E：師門配方的預覽不寫「沒人合過」（結果會說這是師門傳下來的路數）；別的配方照舊。"""
    _to_step(fresh, 3)
    line = fresh.forge_line("basic_fist", ["feng"])
    assert "師門傳下來" in line and "沒人合過" not in line
    outside = Game.new(fresh.content, "路人", rng=random.Random(0), world=fresh.world)
    outside.state.player.insights.append("feng")
    assert "沒人合過" in outside.forge_line("basic_breath", ["feng"]) and "師門" not in outside.forge_line("basic_breath", ["feng"])
    fresh.forge("basic_fist", ["feng"])  # 做出來之後別人看到的是「會合出【穿林腿】」
    other = Game.new(fresh.content, "老手", rng=random.Random(0), world=fresh.world)
    other.state.player.insights.append("feng")
    assert "會合出【穿林腿】" in other.forge_line("basic_fist", ["feng"])


def test_the_hut_steps_show_no_done_chip(fresh):
    """T7 審查 M3（設計 3.1「不再每步跳「✔ 引導完成…」」）：草廬每一步做完，對話框上沒有「✔ 完成」那一列（獎勵就是劇情本身）；
    紀錄（journal.guide）裡也不寫那一句。序章外照舊（第一季的軍令兩步，test_orders）。"""
    for step in range(10):
        _to_step(fresh, step + 1)
        assert fresh.state.player.guide_done == [] or all("✔" not in line for line in fresh.state.player.guide_done), step
        box = fresh.guide_box()
        assert box is None or "✔ 引導完成" not in box["done"], step
    assert all("✔ 引導完成" not in line for entry in fresh.state.journal for line in entry.guide)


def test_the_farewell_reward_is_a_result_of_the_walk_not_a_box_line(prologue_root, tmp_path):
    """T7 審查 M4：出師的盤纏（銀兩 +30、體力補滿）寫在抵達潁川那一則「剛剛」裡，beta 與第一季一樣；不留在對話框的 done 裡
    （beta 的框抵達後就沒了，第一季的框是下一步的話，那一列會寫成別的意思）；體力那一項寫「體力回滿」，不是「體力 +150」。
    第一季要在開季那一刻就開著才蓋得到章（rules.season_one），所以兩種季各用自己的資料庫、先設好開關再建角色（T7 審查 N4）。"""
    import json
    import re

    from tianxia import guide
    from tianxia.sqlite_world import open_world

    path = prologue_root / "tutorial.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["steps"].append({"id": "t7", "text": "去投靠。", "season_one": True, "done_when": {"action": "order"}})
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    seasons = {}
    for label, on in (("beta", False), ("season one", True)):
        content = load_content(prologue_root)
        content.config.season_one = on
        world = open_world(tmp_path / f"{on}.db")
        game = Game.new(content, f"沈浪{label}", rng=random.Random(0), world=world, prologue=True)
        assert (guide.steps(game.state, content)[-1].id == "t7") is on, label  # 第一季真的開著：t7 在步驟裡
        _to_step(game, 10)
        game.state.player.stamina = 12.0
        game.choose("move:town")
        game.advance(game.state.player.journey.arrive_at[-1] - game.state.world.time)
        entry = game.state.journal[0]
        assert "銀兩 +30" in entry.changes and "體力回滿" in entry.lines, label
        assert entry.lines.index("草廬已經看不見了。") < entry.lines.index("體力回滿"), label  # 先是景，再是盤纏
        assert "體力 +150" not in "".join(entry.changes + entry.lines + game.state.player.guide_done), label
        assert game.state.player.guide_done == [], label
        # 玩家看到的整張卡（文字與數值變化的小標）：拿掉「剛剛　時間」那一行（第一季寫季曆、beta 寫第幾天，本來就不同）之後兩種季一字不差
        card = re.sub(r'<div class="tx-when">.*?</div>', "", game.now_entry_html())
        assert "草廬已經看不見了。" in card and "體力回滿" in card and "銀兩 +30" in card and "體力 +150" not in card, label
        assert "tx-up" in card, label  # 銀兩 +30 是綠色的增加小標
        seasons[label] = (entry.title, entry.tag, entry.lines, entry.changes, card)
        assert entry.guide == [f"【師父】{'去投靠。' if on else '去闖吧。'}"], label  # 引導那幾行（下一步的話）本來就不同，不在卡上，也不含盤纏
    assert seasons["beta"] == seasons["season one"]  # 兩種季寫得一樣：標題、結果標記、敘事、數值變化、整張卡


def test_a_late_step_outside_the_hut_still_shows_its_chip_and_reward(prologue_root, world):
    """序章之外的步驟（第一季的軍令兩步）照舊：「✔ 引導完成」與獎勵在對話框上。"""
    import json

    path = prologue_root / "tutorial.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["steps"].append({"id": "t7", "text": "去探索。", "season_one": True, "done_when": {"action": "explore"},
                          "reward": {"stats": {"silver": 10}}})
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    content = load_content(prologue_root)
    content.config.season_one = True
    game = Game.new(content, "沈浪", rng=random.Random(0), world=world)  # 站在潁川、序章走過
    msgs = game.choose("act:explore")
    assert game.state.player.guide_done == ["✔ 引導完成", "銀兩 +10"] and "銀兩 +10" not in msgs


def test_a_hut_step_can_write_its_own_result_line(fresh):
    """T7 審查 M1：10.3 的三句「…之後（場景）」（合成、修練、熔煉）寫在步驟的 after 上，草廬裡這一步的結果就用它，不用引擎的一般那句：
    {意境}、{武學}、{心得} 換成這一次真的合出來的、修練的、退回的。合成那一句後面接武學自己的說明，不再接「這是師門傳下來的路數。」
    （師父的下一句 p5 開頭寫的是同一件事）。"""
    from tianxia import journal

    _to_step(fresh, 3)
    fused = fresh.forge("basic_fist", ["feng"])
    assert fused[0] == "你把粗淺拳腳融進風之意境，練出了一門新武學——【穿林腿】。\n腿隨風走。"
    assert "師門傳下來" not in "\n".join(fused) and "心得 -5" in fused
    assert journal._line_class(fused[0]) == "tx-line tx-new"  # 拿到新東西那一行照樣掃光
    _to_step(fresh, 5)
    cultivated = fresh.cultivate(_fused(fresh))
    assert cultivated[0] == "這一遍修練，你忽然摸到了門道——【穿林腿】從下品升到了中品！"
    assert journal._line_class(cultivated[0]) == "tx-line tx-new"
    _to_step(fresh, 9)
    melted = fresh.melt_art("junk")
    assert melted[0] == "你把蠻牛拳熔了，換回 8 點心得。" and "心得 +8" in melted
    outside = Game.new(fresh.content, "路人", rng=random.Random(0))
    outside.state.player.insights.append("feng")
    outside.state.player.stats["xinde"] = 20
    assert "你以【粗淺拳腳】融入「風」" in outside.forge("basic_fist", ["feng"], proposed=("旋風腿", ""))[0]  # 序章外照舊


def test_the_sight_is_said_once_in_the_card(fresh):
    """T7 審查 M1（草廬四景悟到的那句在紀錄裡只說一次）：現在四景是有所感，悟到的那一句只有引擎的「你悟得了「風」的意境（屬快）！」，
    不會又有一句事件文字說同一件事；那一句留在紀錄、畫成「新東西」的樣子。"""
    from tianxia import journal

    _to_step(fresh, 2)
    fresh.choose("act:explore")
    got = sensing.current(fresh.state, fresh.content)
    order = [got[1].methods[j].attribute for j in got[0].order]
    fresh.choose(f"sense:{order.index('快')}")
    msgs = fresh.choose(sensing.LET_GO)
    lines = fresh.state.journal[0].lines
    said = [line for line in lines if line.startswith("你悟得了「")]
    assert len(said) == 1 and journal._line_class(said[0]) == "tx-line tx-new"
    assert any(m.startswith("你悟得了「") for m in msgs)  # 回給呼叫端的訊息照舊


def test_the_hut_refuses_seclusion(fresh):
    """T6 review M4：閉關在草廬裡不是師父教的，也會把心得賺過劇本備好的帳（20 → 170）。擋下、不寫紀錄，跟別的拒絕一樣。"""
    _to_step(fresh, 3)
    p = fresh.state.player
    xinde, entries = p.stats["xinde"], len(fresh.state.journal)
    assert fresh.seclusion_refusal() and "師父" in fresh.seclusion_refusal()
    msgs = fresh.seclude(8)
    assert msgs == [fresh.seclusion_refusal()]
    assert p.busy_until is None and p.stats["xinde"] == xinde and len(fresh.state.journal) == entries
    outside = Game.new(fresh.content, "路人", rng=random.Random(0))
    assert outside.seclusion_refusal() is None
    outside.seclude(1)
    assert outside.state.player.busy_until is not None  # 序章外照舊閉得了


def test_the_hut_greys_the_insight_melt_with_the_same_reason_the_action_gives(fresh):
    """T6 review M7：化成心得在草廬裡永遠被擋；按鈕要跟動作的拒絕同一個判斷，灰掉、寫原因，不是亮著按了才說。"""
    _to_step(fresh, 3)
    rows = fresh.insight_rows()
    assert rows and all(row["blocked"] and "師父" in row["blocked"] for row in rows)
    assert fresh.melt_insight(rows[0]["id"]) == [rows[0]["blocked"]]
    outside = Game.new(fresh.content, "路人", rng=random.Random(0))
    outside.state.player.insights.append("feng")
    assert [row["blocked"] for row in outside.insight_rows()] == [None]


def test_a_scripted_fight_never_waits_for_the_model(fresh, monkeypatch):
    """review-t4-5 M7：斷眉若寫成頭目、或難度到大場面的門檻，平常按下去要等模型判讀；雪恥那一場勝負是寫好的，不叫模型、不排佇列，
    連手上有一張備好的判讀也不拿來用（_judged 不被問）。"""
    duanmei = fresh.content.squads["duanmei"]
    duanmei.boss, duanmei.difficulty = True, 150
    _to_step(fresh, 7)
    assert fresh.is_big(duanmei)  # 平常是大場面
    option = next(o for o in fresh.options() if o.id == "act:train")
    assert option.wait == "" and fresh.fight_request("act:train") is None

    def consulted(self, squad):
        raise AssertionError("寫好的那一場不看判讀")

    with monkeypatch.context() as patch:
        patch.setattr(Game, "_judged", consulted)
        fresh.choose("act:train")
    assert fresh.state.battles[0].tier == "險勝"  # 照寫好的
    outside = Game.new(fresh.content, "路人", rng=random.Random(0))
    outside.state.player.location = "lake"
    fresh.content.locations["lake"].enemies = ["duanmei"]
    assert outside.fight_request("act:train") is not None  # 序章外同一個對手照舊要等判讀


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


@pytest.mark.parametrize("mode", ["walk", "hurry", "dash"])
def test_leaving_the_hut_fills_the_stamina_whatever_the_way(fresh, mode):
    """出師那一步的獎勵是人走出草廬時唯一能補體力的地方（略過的人由 finish 補）：不管怎麼走、走之前剩多少，抵達潁川都是滿的，
    跟略過序章的人一樣。"""
    _to_step(fresh, 10)
    fresh.state.player.stamina = 40.0  # 趕路、疾行要花體力：夠付、又離滿很遠
    fresh.set_move_mode(mode)
    fresh.choose("move:town" if mode == "walk" else f"move:town:{mode}")
    assert fresh.state.player.stamina < fresh.content.config.stamina_max or fresh.state.player.journey is None
    if fresh.state.player.journey is not None:
        fresh.advance(fresh.state.player.journey.arrive_at[-1] - fresh.state.world.time)
    p = fresh.state.player
    assert p.location == "town" and p.stamina == fresh.content.config.stamina_max
    skipper = Game.new(fresh.content, "略過", rng=random.Random(0), world=fresh.world, prologue=True)
    skipper.skip_tutorial()
    assert skipper.state.player.stamina == p.stamina


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


def test_nothing_melts_before_the_melt_step(fresh):
    """蠻牛拳在第 9 步（配點）就已經在功法庫裡了：熔了它第 10 步（熔雜學）就永遠做不成。熔煉只准在熔的那一步、只准熔它。"""
    _to_step(fresh, 8)
    assert "junk" in fresh.state.player.arts and prologue.melt_only(fresh.state, fresh.content) == ""
    assert "師父" in fresh.melt_art("junk")[0]
    assert "junk" in fresh.state.player.arts and fresh.state.player.tutorial_step == 8
    _to_step(fresh, 10)  # 照常走完還是走得通


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


# ── 重看序章、任務欄的下一步（計畫一 Task 6）──────────────────

def test_prologue_recap_reads_the_whole_prologue(prologue_content, content, world):
    game = Game.new(prologue_content, "沈浪", world=world)
    text = game.prologue_recap()
    assert text.index("城外") < text.index("草廬") < text.index("去看修練頁。") < text.index("草廬已經看不見了。")
    assert text.index("斷眉來了。") < text.index("跟他打。")  # 旁白排在話的前面
    assert "{武學}" not in text and "把【新武學】換上，練到第三成。" in text
    assert Game.new(content, "路人", world=world).prologue_recap() == ""  # 測試內容沒有序章


def test_the_recap_includes_the_masters_reply_and_the_four_sights(prologue_content, world):
    """T7 審查 M5：重看序章不跳過拜師之後師父那一段（拜師的結果文字）與四景（事件的引子加四個悟到的句子）。"""
    text = Game.new(prologue_content, "沈浪", world=world).prologue_recap()
    assert text.index("想學嗎？") < text.index("好徒兒。") < text.index("去看修練頁。")  # 拜師的結果在師父第一步的話之前
    scene = prologue_content.insight_scenes["hut_four"]  # 草廬四景（有所感）：場景的引子與四個做法，排在探索那一步之後、合成那一步之前
    assert text.index("去探索。") < text.index(scene.text) < min(text.index(m.text) for m in scene.methods)
    assert max(text.index(m.text) for m in scene.methods) < text.index("去合成。")
    assert all(m.text in text for m in scene.methods) and "{" not in text


def test_the_recap_does_not_depend_on_where_you_are(fresh):
    before = fresh.prologue_recap()
    _to_step(fresh, 4)
    assert fresh.prologue_recap() == before  # 只讀內容：走到哪一步、合成了什麼都不變


def test_the_quest_card_fills_in_the_fused_art(fresh):
    """任務欄「下一步」的話跟對話框一樣：{武學} 換成合成出來的那一門，不寫出字面的佔位。"""
    _to_step(fresh, 4)
    name = prologue.fused_arts(fresh.state, fresh.content, fresh.world)[0].name
    quest = fresh.quest_text()
    assert f"把【{name}】換上，練到第三成。" in quest and "{武學}" not in quest


def test_the_quest_card_has_no_blank_master_before_he_is_met(fresh):
    """序章第一步師父還沒出場：任務欄不寫「（師父）」。事件還沒了結時也不寫（那時師父還沒說過話）。"""
    assert "（師父）" not in fresh.quest_text()
    ambush, fresh.state.pending_event = fresh.state.pending_event, None  # 沒有事件擋著的樣子
    assert "（師父）" not in fresh.quest_text() and "**下一步**" not in fresh.quest_text()
    fresh.state.pending_event = ambush
    _walk(fresh, "choice:0", "choice:0")  # 遇到師父了
    assert "（師父）去看修練頁。" in fresh.quest_text()


# ── 假人與腳本：序章之後的樣子要跟真人一樣（Game.new(graduated=True)，M8）────────────

def _look(game):
    """別人一眼看得到的樣子：等級、功法欄與功法庫裡每一門的（品質, 第幾成）、銀兩、位置、有沒有內傷。名字不比（四門師門功夫看種子）。"""
    from tianxia import library, team

    s = game.state
    p, m = s.player, s.player.member

    def art(art_id, level):
        return None if art_id is None else (team.player_art(s, game.content, game.world, art_id).quality, level)

    return {
        "level": m.level, "wugong": art(m.wugong_id, m.wugong_level), "neigong": art(m.neigong_id, m.neigong_level),
        "library": sorted((team.player_art(s, game.content, game.world, a).quality, library.level_of(s, a)) for a in p.arts),
        "silver": p.stats["silver"], "location": p.location, "stamina": p.stamina, "step": p.tutorial_step,
        "hurt": m.injury > 0,
    }


def _walked(prologue_content, world):
    """真人走完草廬、出了師（抵達潁川）。"""
    human = Game.new(prologue_content, "真人", rng=random.Random(0), world=world, prologue=True)
    _to_step(human, 10)
    human.choose("move:town")
    human.advance(human.state.player.journey.arrive_at[-1] - human.state.world.time)
    return human


def test_a_graduated_bot_looks_like_a_human_who_walked_the_hut(prologue_content, world):
    """假人不走序章，但離開起點時的樣子要跟走完草廬的真人一樣：不然新人頭一個鐘頭就看得出誰是假人（等級 2、一門中品
    第三成的師門功夫、剩一點內傷、多了盤纏）。做法是把序章用真的行動走一遍（Game._graduate），不是手抄一份清單。"""
    human = _walked(prologue_content, world)
    bot = Game.new(prologue_content, "假人", rng=random.Random(1), world=world, graduated=True)
    assert _look(bot) == _look(human)
    assert _look(bot)["level"] == 2 and _look(bot)["hurt"] and _look(bot)["location"] == "town"
    s, p = bot.state, bot.state.player
    assert s.pending_event is None and not prologue.active(s, prologue_content)
    assert p.tutorial_step == prologue_content.tutorial.prologue_steps and p.stamina == prologue_content.config.stamina_max
    fused = prologue.fused_arts(s, prologue_content, world)
    assert [a.name for a in fused] and fused[0].preset and fused[0].name in {"穿林腿", "坐山拳", "回瀾手", "烈爐拳"}
    assert fused[0].quality == "中品" and fused[0].creator is None  # 師門功夫，沒有首創者
    assert "junk" not in p.arts  # 雜學熔掉了，跟真人一樣
    assert len(s.journal) <= 1 and s.battles == []  # 序章走過的痕跡不留在假人的紀錄裡（回到跟沒走序章的假人一樣乾淨）


def test_graduating_picks_one_of_the_four_presets_by_seed(prologue_content, world):
    names = {}
    for seed in range(24):
        game = Game.new(prologue_content, f"假人{seed}", rng=random.Random(seed), world=world, graduated=True)
        names[seed] = prologue.fused_arts(game.state, prologue_content, world)[0].name
    assert set(names.values()) == {"穿林腿", "坐山拳", "回瀾手", "烈爐拳"}  # 四種都有人
    again = Game.new(prologue_content, "假人3", rng=random.Random(3), world=world, graduated=True)
    assert prologue.fused_arts(again.state, prologue_content, world)[0].name == names[3]  # 同一顆種子同一門


def test_graduating_does_not_ask_the_model_and_leaves_no_season_footprint(prologue_content, world, monkeypatch):
    """走序章的過程不叫模型（師門配方不等取名、遇敵是寫好的）；也不把共用賽季的時鐘往前推。"""
    from tianxia.ollama_client import OllamaClient

    asked = []  # 數呼叫、不丟例外：呼叫端多半接得住例外、悄悄走退路，丟了反而看不出來

    def ask(self, *args, **kwargs):
        asked.append(args)
        raise RuntimeError("連不上")

    monkeypatch.setattr(OllamaClient, "chat_text", ask)
    monkeypatch.setattr(OllamaClient, "chat_structured", ask)
    before = world.get_season().time
    bot = Game.new(prologue_content, "假人", rng=random.Random(2), world=world, graduated=True)
    assert asked == [] and world.get_season().time == before
    assert bot.client is not None  # 走完序章把客戶端還回去（伺服器假人之後由 bot_runner 自己設成 None）


def test_graduating_does_not_ask_the_model_even_for_a_recipe_nobody_wrote(prologue_content, world, monkeypatch):
    """師門配方被拿掉（內容改版）時，首次出現的配方平常要在這裡叫模型取名：走序章的假人不叫（走退路字表），一次也不叫。"""
    from tianxia.ollama_client import OllamaClient

    asked = []

    def ask(self, *args, **kwargs):
        asked.append(args)
        raise RuntimeError("連不上")

    monkeypatch.setattr(OllamaClient, "chat_text", ask)
    monkeypatch.setattr(OllamaClient, "chat_structured", ask)
    prologue_content.preset_recipes.clear()
    bot = Game.new(prologue_content, "假人", rng=random.Random(2), world=world, graduated=True)
    assert asked == [] and prologue.fused_arts(bot.state, prologue_content, world)  # 合成了、沒有問模型
    assert bot.state.player.location == "town"


def test_graduating_only_takes_choices_that_lead_to_the_step_flag(prologue_content, world):
    """遇險那一則多一個「逃」（走不到拜師）：假人不挑它，不然這一步永遠完成不了、整個序章只剩略過的樣子。"""
    from tianxia.models import Choice, Effect

    prologue_content.events["p_ambush"].choices.append(Choice(text="逃", effect=Effect(text="你逃了。", flags_add=["序章:逃"])))
    for seed in range(16):
        bot = Game.new(prologue_content, f"假人{seed}", rng=random.Random(seed), world=world, graduated=True)
        assert "序章:拜師" in bot.state.player.flags and "序章:逃" not in bot.state.player.flags, seed
        assert bot.state.player.member.level == 2, seed  # 整個序章走完：雪恥打過、升了級


def test_a_graduated_bot_in_season_two_is_the_same_as_in_season_one(prologue_content, world):
    one = Game.new(prologue_content, "假人甲", rng=random.Random(4), world=world, graduated=True)
    next_season(prologue_content, world)
    two = Game.new(prologue_content, "假人乙", rng=random.Random(4), world=world, graduated=True)
    assert two.state.player.season_number == 2 and _look(two) == _look(one)


def test_graduating_a_script_that_cannot_be_followed_falls_back_to_the_purse(prologue_content, world):
    """內容改版讓某一步照著走不通（這裡把修練那一步的「一定升品」拿掉，師父那一步沒叫你修練、修練被擋）：假人不能卡在
    草廬，走不下去就像略過一樣直接出師、拿盤纏。"""
    prologue_content.tutorial.steps[5].sure_cultivate = False
    bot = Game.new(prologue_content, "假人", rng=random.Random(1), world=world, graduated=True)
    p = bot.state.player
    assert p.location == "town" and p.tutorial_step == prologue_content.tutorial.prologue_steps
    assert not prologue.active(bot.state, prologue_content) and bot.state.pending_event is None
    assert p.stamina == prologue_content.config.stamina_max
    fused = prologue.fused_arts(bot.state, prologue_content, world)[0]
    assert fused.quality != "中品" and p.member.level == 1  # 真的卡在第 6 步：後面的雪恥、配點都沒走到
    assert p.stats["silver"] == prologue_content.config.start_stats["silver"] + 30  # 盤纏照拿


def test_graduating_changes_nothing_on_content_without_a_prologue(content, world, monkeypatch):
    """沒有序章的內容（正式內容現在就是）：graduated=True 什麼都不做，連亂數都不多用一次。"""
    def boom(self):
        raise AssertionError("沒有序章的內容不該走序章")

    monkeypatch.setattr(Game, "_graduate", boom, raising=False)
    plain_rng, graduated_rng = random.Random(7), random.Random(7)
    plain = Game.new(content, "甲", rng=plain_rng, world=world)
    graduated = Game.new(content, "甲", rng=graduated_rng, world=world, graduated=True)
    assert graduated.state.model_dump() == plain.state.model_dump()
    assert graduated_rng.getstate() == plain_rng.getstate()


def test_the_season_bot_leaves_the_start_like_a_human_on_content_with_a_prologue(prologue_content, world, tmp_path):
    """bot.play_season 的整季機器人也一樣；而且賽季還在籌備中（沒有 auto_open）它自己先開季再走序章，不然什麼都做不了。"""
    from tianxia import bot
    from tianxia.sqlite_world import open_world

    human = _walked(prologue_content, world)
    prologue_content.config.auto_open_first_season = False
    game = bot.play_season(prologue_content, 1, max_steps=0, world=open_world(tmp_path / "w.db"))
    assert _look(game) == _look(human) and _look(game)["level"] == 2
    assert game.state.player.location == "town" and prologue.fused_arts(game.state, prologue_content, game.world)[0].preset


@pytest.mark.slow
def test_the_season_bot_plays_the_same_game_on_content_without_a_prologue(content, tmp_path, monkeypatch):
    """bot.play_season 現在也傳 graduated=True：沒有序章時，同一顆種子玩出來的整季要跟不傳一模一樣。"""
    from tianxia import bot
    from tianxia.sqlite_world import open_world

    def boom(self):
        raise AssertionError("沒有序章的內容不該走序章")

    original = Game.new.__func__

    def without(cls, *args, **kwargs):
        kwargs.pop("graduated", None)
        return original(cls, *args, **kwargs)

    new = bot.play_season(content, 1, max_steps=300, world=open_world(tmp_path / "a.db"))
    monkeypatch.setattr(Game, "new", classmethod(without))
    monkeypatch.setattr(Game, "_graduate", boom, raising=False)
    old = bot.play_season(content, 1, max_steps=300, world=open_world(tmp_path / "b.db"))
    assert new.state.model_dump_json() == old.state.model_dump_json()
