"""arts-polish-2 第三輪：joy 的三個 PR（卷軸卡、合成品質擲機率、docs）併進來之後，序章與這幾條舊規矩還對不對。
全部跑正式內容（content/）與假內容各一組；Game 一律沒有模型（沒給 client 的測試，conftest 把模型呼叫假成連不上）。

- 序章（草廬）：第 4 步那一爐一定是下品（不擲品質）、第 6 步一次修練就到中品（師門配方的保證）、第 10 步熔蠻牛拳換回 8 點心得。
- W6：合成擲到中品、上品之後，功法庫那一門跟身上那門的比較照「擲到的那一份」的威力算。
- W8：擲到中品的武學下一步是上品的機率，不走下品→中品那一段（40%、60%、第 3 次必成），也不會寫「一定晉為中品」；
  擲到上品的下一步是絕學（沒有保底、最多 50%），永遠不會寫「一定」。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from conftest import FixedRandom
from tianxia import cultivation, fusion, library, prologue, sensing, skillview, team
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.martial_arts import power_at

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def real():
    c = load_content(ROOT / "content")
    c.config.auto_open_first_season = True
    return c


def _rolling(quality):
    """一個擲出固定品質的亂數（只有擲品質那一下會用到 choices）。"""
    rng = random.Random(0)
    rng.choices = lambda population, weights=None, **kw: [quality]
    return rng


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


def test_prologue_step_4_the_real_hut_fusion_is_the_lowest_quality_even_if_a_roll_would_say_otherwise(real, world):
    """第 4 步（合成）：序章那一爐照劇本固定下品、第一成，不擲 PR #19 的品質機率；就算亂數會擲出上品也一樣。"""
    game = _hut_up_to_the_fusion(real, world)
    game.rng = _rolling("上品")
    insight = game.state.player.insights[0]
    assert "從下品起修" in game.forge_line("jichu_quanjiao", [insight])
    game.forge("jichu_quanjiao", [insight], proposed=(None, ""))
    art = prologue.fused_arts(game.state, real, game.world)[0]
    assert team.player_art(game.state, real, game.world, art.id).quality == "下品"
    assert art.id not in game.state.player.art_quality and art.id not in game.state.player.art_rolled
    assert game.state.player.tutorial_step == 4  # 第 4 步做完了


def test_prologue_steps_6_and_10_one_cultivation_reaches_the_middle_grade_and_melting_pays_eight(real, world):
    game = _hut_up_to_the_fusion(real, world)
    insight = game.state.player.insights[0]
    game.forge("jichu_quanjiao", [insight], proposed=(None, ""))
    art = prologue.fused_arts(game.state, real, game.world)[0]
    game.switch_art(art.id)
    game.practice("武學")
    game.practice("武學")
    game.rng = FixedRandom(0.99)  # 平常的擲骰一定落空：序章這一步的修練照劇本必成（prologue.sure_rng）
    cultivated = game.cultivate(art.id)
    assert game.state.player.art_quality[art.id] == "中品" and game.state.player.tutorial_step == 6
    assert cultivated[0].endswith("從下品晉為中品！")  # joy 的版本沒有寫「…之後」的句子（TutorialStep.after），用引擎的一般那句
    assert art.id not in game.state.player.art_rolled  # 中品是修練上去的，不是合成擲到的
    game.choose("act:rest")
    game.choose("act:train")
    game.allocate_stat("str")
    assert game.state.player.tutorial_step == 9
    before = game.state.player.stats["xinde"]
    melted = game.melt_art("manniu_quan")
    assert melted[0] == "你把【蠻牛拳】熔成了心得。" and "心得 +8" in melted  # 同上：引擎的一般那句，退回的心得是真的 8 點
    assert game.state.player.stats["xinde"] - before == 8


def test_the_hut_rows_carry_the_server_glow_lists_and_the_forge_page_the_pick_cues(real, world):
    """序章的指路由伺服器說（卷軸卡照它畫，不自己猜）：第 4 步（合成）煉製頁要放進爐子的底（基礎拳腳）帶 pick:art、剛悟到的意境帶
    pick:insight，別的武學都不帶；合成做完（第 5 步）兩個提示都沒有了。（review-ap3 M2：以前這條只看 glow 這個鍵在不在。）"""
    game = _hut_up_to_the_fusion(real, world)
    assert game.state.player.tutorial_step == 3
    rows = skillview.art_rows(game.state, real, game.world)
    assert [r["id"] for r in rows if "pick:art" in r["glow"]] == ["jichu_quanjiao"]  # 底：基礎拳腳；內功基礎吐納不點名
    assert all(r["glow"] == [] for r in rows if r["id"] != "jichu_quanjiao")  # 這一步別的武學不亮（沒有修練、熔煉可按）
    assert all("forge_odds" not in row for row in rows)  # 序章那一爐照劇本、沒有機率條
    ins = game.insight_rows()
    assert ins and all(r["glow"] == ["pick:insight"] for r in ins)  # 剛悟到的意境
    game.forge("jichu_quanjiao", [game.state.player.insights[0]], proposed=(None, ""))  # 放進爐裡、開爐：這一步做完
    assert game.state.player.tutorial_step == 4
    assert not any("pick:art" in r["glow"] for r in skillview.art_rows(game.state, real, game.world))
    assert not any("glow" in r and r["glow"] for r in game.insight_rows())  # 兩個提示都沒有了


# ── W6：擲到中品、上品的合成武學，比較照擲到的威力 ──────────────


def named(name):
    from unittest import mock

    from tianxia import naming

    client = mock.Mock()
    client.chat_structured.return_value = naming.NameReply(name=name, description="一句話說明。")
    return client


def _forged_with_messages(state, content, world, quality):
    state.player.insights = ["feng"]
    state.player.stats["xinde"] = 100
    state.player.member.wugong_id = "basic_fist"
    art, msgs = fusion.fuse(state, content, world, named("旋風腿"), "basic_fist", "feng", rng=_rolling(quality))
    assert art is not None and state.player.art_quality.get(art.id, art.quality) == quality
    return art, msgs


def _forged(state, content, world, quality):
    return _forged_with_messages(state, content, world, quality)[0]


@pytest.mark.parametrize("quality", ["中品", "上品"])
def test_w6_the_comparison_uses_the_rolled_quality_of_the_new_art(state, content, world, quality):
    art = _forged(state, content, world, quality)
    mine = team.player_art(state, content, world, art.id)
    worn = team.player_art(state, content, world, "basic_fist")
    assert mine.quality == quality and worn.quality == "下品"
    diff = power_at(mine, 1) - power_at(worn, 1)
    line = team.compare_with_worn(state, content, world, art)
    assert f"威力 {diff:+.1f}".replace("-", "−") in line and line.startswith("比身上的【粗淺拳腳】：")
    assert diff > power_at(art, 1) - power_at(worn, 1)  # 擲到的品質真的算進去了：比拿登記的下品那一份比還大
    (row,) = [r for r in skillview.art_rows(state, content, world) if r["id"] == art.id]
    assert row["quality"] == quality and row["compare"] == line and f"【旋風腿】{quality}・" in row["card"]
    assert line in row["card"].split("\n")


@pytest.mark.parametrize("quality", ["下品", "中品", "上品"])
def test_w6_the_forge_result_itself_compares_with_the_rolled_quality(state, content, world, quality):
    """review-ap3 M3：合成的結果訊息（不只功法庫的卡）裡那一句比較，也用擲到的那一份品質的威力：訊息是 fusion.fuse 回的，
    比較排在「收進功法庫」之後、指路那句之前；它對的前提是 library.store_art 先把擲到的品質記下來、才輪到比較（順序換了，
    上品會被拿登記的下品去比、只差 +0.3）。"""
    art, msgs = _forged_with_messages(state, content, world, quality)
    mine = team.player_art(state, content, world, art.id)
    worn = team.player_art(state, content, world, "basic_fist")
    assert mine.quality == quality
    diff = power_at(mine, 1) - power_at(worn, 1)
    line = f"比身上的【粗淺拳腳】：威力 {diff:+.1f}（第一成）".replace("-", "−")
    compare = [m for m in msgs if m.startswith("比身上的【粗淺拳腳】")]
    assert len(compare) == 1 and compare[0].startswith(line), (msgs, line)
    assert msgs.index(compare[0]) == len(msgs) - 2 and msgs[-1] == library.SWITCH_HINT  # 指路那句還是最後一句
    if quality != "下品":  # 擲到的品質真的算進去了：不是拿登記的下品那一份比
        assert diff > power_at(art, 1) - power_at(worn, 1)


# ── W8：擲到的品質走自己的下一步，不走下品→中品的階梯 ────────────


def _row(state, content, world, art_id):
    (row,) = [r for r in skillview.art_rows(state, content, world) if r["id"] == art_id]
    return row


def test_w8_a_rolled_middle_grade_art_aims_at_the_upper_grade_not_the_first_ladder(state, content, world):
    art = _forged(state, content, world, "中品")
    odds = cultivation.odds_for(state, content, "上品", 0)
    note = _row(state, content, world, art.id)["cultivate"]["note"]
    assert note.startswith(f"{odds}% 晉為上品") and "中品" not in note and "一定" not in note
    assert odds == 10  # 上品那一段第一次 10%（+6），不是下品→中品的 40%
    for failures in (1, 2, 3):  # 下品→中品第 3 次必成：擲到中品的這一門不吃那一段，失敗再多次也只是上品那一段的機率往上加
        state.player.art_mastery[art.id] = failures
        note = _row(state, content, world, art.id)["cultivate"]["note"]
        assert note.startswith(f"{cultivation.odds_for(state, content, '上品', failures)}% 晉為上品") and "一定" not in note
    state.player.art_mastery[art.id] = 0
    state.player.stamina = 100
    msgs = cultivation.cultivate(state, content, world, art.id, FixedRandom(0.99))  # 擲不中
    assert state.player.art_quality[art.id] == "中品" and state.player.art_mastery[art.id] == 1
    assert any("晉為上品" in m for m in msgs) and not any("晉為中品" in m or "一定" in m for m in msgs)
    won = cultivation.cultivate(state, content, world, art.id, FixedRandom(0.0))  # 擲中：升上品
    assert state.player.art_quality[art.id] == "上品" and any("從中品晉為上品" in m for m in won)


def test_w8_a_rolled_upper_grade_art_aims_at_the_peerless_grade_with_no_guarantee(state, content, world):
    art = _forged(state, content, world, "上品")
    note = _row(state, content, world, art.id)["cultivate"]["note"]
    assert note.startswith(f"{cultivation.odds_for(state, content, '絕學', 0)}% 晉為絕學") and "一定" not in note
    state.player.art_mastery[art.id] = 60  # 失敗再多次，絕學沒有保底：機會最多到 cultivate_cap
    note = _row(state, content, world, art.id)["cultivate"]["note"]
    cap = content.config.cultivate_cap["絕學"]
    assert note.startswith(f"{cap}% 晉為絕學") and "一定" not in note


def test_w8_the_first_ladder_still_belongs_to_the_lowest_grade(state, content, world):
    """對照：沒擲到品質的（下品）照舊走下品→中品：第 1 次 40%、第 2 次 60%、第 3 次一定。"""
    art = _forged(state, content, world, "下品")
    notes = []
    for failures in (0, 1, 2):
        state.player.art_mastery[art.id] = failures
        notes.append(_row(state, content, world, art.id)["cultivate"]["note"].split("・")[0])
    assert notes == ["40% 晉為中品", "60% 晉為中品", "一定晉為中品"]


def test_w8_the_melt_value_counts_a_rolled_grade_as_held_since_registration(state, content, world):
    """PR #19 的規矩跟 W8 不打架：擲到中品的那一階在熔的時候不給加給（登記時就有的那一階）。"""
    art = _forged(state, content, world, "中品")
    state.player.arts = [art.id]
    state.player.member.wugong_id = "basic_fist"
    base = library.melt_value(state, content, world, art.id)
    state.player.art_quality[art.id] = "上品"  # 自己再修練到上品：只多上品那一階的加給
    assert library.melt_value(state, content, world, art.id) - base == (
        content.config.melt_quality_bonus["上品"] - content.config.melt_quality_bonus["中品"]
    )
