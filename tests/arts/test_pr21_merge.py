"""arts-polish-2 第三輪：joy 的三個 PR（卷軸卡、合成品質擲機率、docs）併進來之後，序章與這幾條舊規矩還對不對。
全部跑正式內容（content/）與假內容各一組；Game 一律沒有模型（沒給 client 的測試，conftest 把模型呼叫假成連不上）。

- 序章（草廬）：武學重構之後第 4 步在修練頁把意境裝進基礎拳腳的槽、第 5 步練到第三成、第 6 步在爐裡揣摩、第 10 步熔蠻牛拳換回 16 點心得。
- W6、W8（合成擲品質、衝品的機率）跟著武學重構拿掉了。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from tianxia import insight_fx, library, prologue, sensing, skillview, team
from tianxia.content import load_content
from tianxia.engine import Game

ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def real():
    c = load_content(ROOT / "content")
    c.config.auto_open_first_season = True
    return c


# ── 熔煉的確認問句：有心得、又有重學的地方（re-review m1、m3）──────────────


def test_m1_a_valued_art_that_can_also_be_learned_again_says_both(content, world, state):
    """有心得的熔煉不能漏掉去哪裡重學：開局送的基礎武學練到第四成（熔了退 4）、各地教的湖邊腿法練到第五成（退 8）。
    以前的測試只釘了「有心得、又沒有重學的地方」那一種（合成的旋風腿）。"""
    content.config.starter_skills = ["basic_breath", "basic_fist"]
    state.player.member.wugong_id = "sword"  # 欄位有人佔著，下面的才在功法庫裡
    state.player.arts = ["basic_fist", "lake_kick"]
    state.player.art_levels.update({"basic_fist": 4, "lake_kick": 5})
    rows = {r["id"]: r for r in skillview.art_rows(state, content, world)}
    assert rows["basic_fist"]["melt"]["note"] == "退回心得 4"
    assert rows["basic_fist"]["melt"]["confirm"] == (
        "把【粗淺拳腳】熔成心得？退回心得 4。熔了還能免費重學：這裡就是城鎮，到江湖頁「此地還能做」找「學粗淺拳腳」。"
    )
    assert rows["lake_kick"]["melt"]["note"] == "退回心得 8"
    assert rows["lake_kick"]["melt"]["confirm"] == (
        "把【湖邊腿法】熔成心得？退回心得 8。熔了想拿回來，到湖邊再學一次（學費 10 兩），在江湖頁「此地還能做」找「學湖邊腿法」。"
    )
    assert "熔掉就沒了" not in rows["basic_fist"]["melt"]["confirm"] + rows["lake_kick"]["melt"]["confirm"]


def test_m3_away_from_a_town_the_confirm_names_the_nearest_one(content, world, state):
    content.config.starter_skills = ["basic_breath", "basic_fist"]
    state.player.member.wugong_id = "sword"
    state.player.arts = ["basic_fist"]
    state.player.art_levels["basic_fist"] = 4
    state.player.location = "lake"  # 湖邊不是城鎮；夾具裡離它最近的城鎮是小鎮
    (row,) = [r for r in skillview.art_rows(state, content, world) if r["id"] == "basic_fist"]
    assert row["melt"]["confirm"] == (
        "把【粗淺拳腳】熔成心得？退回心得 4。熔了還能免費重學：到任何城鎮（離你最近的是小鎮），在江湖頁「此地還能做」找「學粗淺拳腳」。"
    )


# ── 序章：第 4、6、10 步 ────────────────────────────────────


def _hut_up_to_the_fusion(real, world):
    game = Game.new(real, "新人", rng=random.Random(0), world=world, prologue=True)
    game.world.open_season(real, now=0.0)
    for option in ("choice:0", "choice:0"):  # 遇險、拜師
        game.choose(option)
    game.view_tab("practice")
    game.choose("act:explore")
    got = sensing.current(game.state, real)  # 草廬四景（有所感）：選松林聽風、順其自然
    order = [got[1].methods[j].attribute for j in got[0].order]
    game.choose(f"sense:{order.index('快')}")
    game.choose(sensing.LET_GO)
    return game


def test_prologue_step_4_the_real_hut_slots_the_insight_into_the_basic_fist(real, world):
    """第 4 步（武學重構：以前是合成一門師門功夫、照劇本固定下品）：在修練頁把剛悟到的意境裝進基礎拳腳的第一格
    （Game.slot_insight；爐裡只合意境），不花心得、不擲骰，基礎拳腳照舊是下品。裝別的門、在爐裡開都擋。"""
    game = _hut_up_to_the_fusion(real, world)
    insight = game.state.player.insights[0]
    xinde = game.state.player.stats["xinde"]
    assert game.forge(None, [insight, insight], proposed=(None, "")) == [prologue.fuse_problem(game.state, real, [insight, insight])]
    assert game.slot_insight("jichu_tuna", insight) == [prologue.slot_problem(game.state, real, "jichu_tuna")]
    assert game.state.player.tutorial_step == 3
    game.slot_insight("jichu_quanjiao", insight)
    assert game.state.player.art_slots["jichu_quanjiao"][0] == insight
    assert [a.id for a in prologue.slotted_arts(game.state, real, game.world)] == ["jichu_quanjiao"]
    assert team.player_art(game.state, real, game.world, "jichu_quanjiao").quality == "下品"
    assert game.state.player.stats["xinde"] == xinde  # 裝意境不花心得
    assert game.state.player.tutorial_step == 4  # 第 4 步做完了


def test_prologue_steps_5_to_10_level_deepen_and_melting_pays_sixteen(real, world):
    """武學重構：第 5 步把裝了意境的基礎拳腳練到第三成、第 6 步同一種意境的兩份揣摩成二重（以前是一次修練就到中品）；
    第 10 步熔蠻牛拳照舊退 16 點心得。"""
    game = _hut_up_to_the_fusion(real, world)
    insight = game.state.player.insights[0]
    game.slot_insight("jichu_quanjiao", insight)
    game.practice("武學")
    game.practice("武學")
    assert library.level_of(game.state, "jichu_quanjiao") == 3 and game.state.player.tutorial_step == 5
    game.forge(None, [insight, f"{insight}~2"], proposed=(None, ""))  # 意境效果池：練到第三成時師父多給的那一份
    assert insight_fx.strength(game.state, insight) == 2 and prologue.deepened(game.state)
    assert game.state.player.tutorial_step == 6
    game.take_stamina_pill()  # 體力見底：服一顆回體丹（新手引導重做，以前是調息）
    game.choose("act:train")
    game.allocate_stat("str")
    assert game.state.player.tutorial_step == 9
    before = game.state.player.stats["xinde"]
    melted = game.melt_art("manniu_quan")
    # 引擎的一般那句，退回的心得是真的 16 點（練成每成 2N 之後，練成花的八成跟著翻倍）
    assert melted[0] == "你把【蠻牛拳】熔成了心得。" and "心得 +16" in melted
    assert game.state.player.stats["xinde"] - before == 16


def test_the_hut_rows_carry_the_server_glow_lists_and_the_forge_page_the_pick_cues(real, world):
    """序章的指路由伺服器說（卷軸卡照它畫，不自己猜）：第 4 步（裝意境）修練頁要裝槽的那一門（基礎拳腳）帶 slot，
    別的武學都不帶、意境也不亮（爐子是揣摩那一步才用）；裝好了（第 5 步）提示就沒有了。（review-ap3 M2：以前這條只看 glow 這個鍵在不在。）"""
    game = _hut_up_to_the_fusion(real, world)
    assert game.state.player.tutorial_step == 3
    rows = skillview.art_rows(game.state, real, game.world)
    assert [r["id"] for r in rows if "slot" in r["glow"]] == ["jichu_quanjiao"]  # 基礎拳腳；內功基礎吐納不點名
    assert all(r["glow"] == [] for r in rows if r["id"] != "jichu_quanjiao")  # 這一步別的武學不亮（沒有修練、熔煉可按）
    assert all("forge_odds" not in row for row in rows)  # 序章沒有機率條
    ins = game.insight_rows()
    assert ins and not any(r.get("glow") for r in ins)  # 意境不亮：這一步不開爐
    game.slot_insight("jichu_quanjiao", game.state.player.insights[0])  # 裝進槽：這一步做完
    assert game.state.player.tutorial_step == 4
    assert not any("slot" in r["glow"] for r in skillview.art_rows(game.state, real, game.world))


# ── W6、W8 拿掉了（武學重構）：合成不再擲品質（武學合成整個拿掉了）、修練不再衝品
# （沒有 cultivation.odds_for、下品→中品的階梯、擲到的品質那一份），這幾條測的東西都不在了。
