"""探索三選一（FB-013，docs/superpowers/specs/2026-10-03-探索三選一-design.md）。

按「探索」：先看這裡有沒有還能遇上的奇遇（一次性或奇遇事件），有的話滾 rare_explore_chance，中了就是它；
沒中就照地點類型的比例抽「悟意境／野怪／事件」三支之一，抽中的那支做不了就把它的比例分給另外兩支。
"""
from __future__ import annotations

import random
from collections import Counter
from pathlib import Path

import pytest

from conftest import FixedRandom
from tianxia import journal, rules, team
from tianxia.content import load_content
from tianxia.engine import FREE_TEXT_OPTION
from tianxia.models import Condition, ExploreMix, FactionDef, FreeTextChoice

N = 2000


def _lake(game, tags=("湖畔",), enemies=("thug",), with_event=True):
    """把玩家放到湖邊，改成要測的樣子：地點標籤（決定類型）、敵人、要不要有可重複的探索事件
    （fixture 的醉漢只在小鎮，這裡也放到湖邊）。湖邊唯一的探索事件殘卷（一次性＋奇遇）標成看過，
    奇遇那一步就不會插進來。"""
    c = game.content
    c.locations["lake"].tags = list(tags)
    c.locations["lake"].enemies = list(enemies)
    if with_event:
        c.events["drunk"].locations = ["town", "lake"]
    game.state.player.location = "lake"
    game.state.player.seen_events.add("scroll")
    return c.locations["lake"]


def _only(game, **weights):
    """所有地點都用同一組比例（只有一筆「其餘」）：要逼探索走某一支時用。"""
    game.content.config.explore_mix = [ExploreMix(kind="wild", tags=[], weights=weights)]


def _explore_many(game, n=N):
    """直接呼叫探索 n 次，數每一次落在哪一支（事件看完就清掉，免得擋住下一次）。"""
    counts = Counter()
    s = game.state
    for _ in range(n):
        battles, known, xinde = s.battle_seq, len(s.player.insights), s.player.stats.get("xinde", 0)
        msgs = game._explore()
        if s.pending_event:
            counts["event"] += 1
            counts[f"event:{s.pending_event}"] += 1
            s.pending_event = None
        elif s.battle_seq != battles:
            counts["wild"] += 1
        elif len(s.player.insights) > known or s.player.stats.get("xinde", 0) > xinde:
            counts["insight"] += 1  # 悟得新的意境，或是悟到已經會的、化成心得（沒有戰鬥就只有這一支會給心得）
        else:
            counts["nothing"] += 1
            assert msgs == ["你四處走走，一無所獲。"]
    return counts


def _factions(content):
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"], goals={"kou": -1}),
        FactionDef(id="huang", name="黃巾", join_at=["lake"], goals={"kou": 1}),
    ]


# ── 三選一的比例 ─────────────────────────────────────────


@pytest.mark.parametrize("tags, expected", [
    (["營寨"], {"insight": 15, "wild": 35, "event": 50}),
    (["城池", "營寨"], {"insight": 15, "wild": 35, "event": 50}),  # 廣宗：營寨優先
    (["城鎮"], {"insight": 15, "wild": 0, "event": 85}),  # 城裡探索不會被打，就算這裡有敵人
    (["湖畔"], {"insight": 40, "wild": 35, "event": 25}),
    (["官道", "野外"], {"insight": 40, "wild": 35, "event": 25}),
])
def test_each_kind_of_place_splits_exploring_by_its_own_ratio(game, tags, expected):
    game.rng = random.Random(11)
    _lake(game, tags)
    counts = _explore_many(game)
    assert counts["nothing"] == 0
    for branch, weight in expected.items():
        assert counts[branch] / N == pytest.approx(weight / 100, abs=0.035), (branch, counts)


def test_no_foes_here_gives_the_wild_share_to_the_other_two(game):
    game.rng = random.Random(12)
    _lake(game, enemies=())
    counts = _explore_many(game)
    assert counts["wild"] == 0 and counts["nothing"] == 0
    assert counts["insight"] / N == pytest.approx(40 / 65, abs=0.035)
    assert counts["event"] / N == pytest.approx(25 / 65, abs=0.035)


def test_only_your_own_side_here_counts_as_no_foes(content, game):
    """自己陣營的隊伍不會從探索裡殺出來（也不會變成操練）：野怪那支做不了。"""
    _factions(content)
    content.squads["thug"].faction = "huang"
    game.state.player.faction = "huang"
    game.rng = random.Random(13)
    _lake(game)
    counts = _explore_many(game)
    assert counts["wild"] == 0 and counts["nothing"] == 0
    assert counts["insight"] / N == pytest.approx(40 / 65, abs=0.035)
    assert game.state.world.trends["kou"] == 30  # 沒有操練，大勢也沒動


def test_no_repeatable_event_here_gives_the_event_share_to_the_other_two(game):
    game.rng = random.Random(14)
    _lake(game, with_event=False)  # 湖邊只剩看過的殘卷，可重複的池子是空的
    counts = _explore_many(game)
    assert counts["event"] == 0 and counts["nothing"] == 0
    assert counts["insight"] / N == pytest.approx(40 / 75, abs=0.035)
    assert counts["wild"] / N == pytest.approx(35 / 75, abs=0.035)


def test_nothing_happens_only_when_no_branch_can(game):
    _lake(game, enemies=(), with_event=False)
    _only(game, insight=0, wild=35, event=25)
    assert _explore_many(game, 20) == Counter(nothing=20)


# ── 奇遇判定先於三選一 ───────────────────────────────────


def test_a_rare_event_comes_before_the_three_way_split(game):
    _lake(game)
    game.state.player.seen_events.discard("scroll")
    game.content.config.rare_explore_chance = 1.0
    game.choose("act:explore")
    assert game.state.pending_event == "scroll"
    assert game.state.battles == [] and game.state.player.materials == {}


def test_a_rare_event_never_comes_from_the_event_branch(game):
    game.rng = random.Random(15)
    _lake(game)
    game.state.player.seen_events.discard("scroll")
    game.content.events["scroll"].once = False  # 可以重複的奇遇也一樣
    game.content.config.rare_explore_chance = 0.0
    _only(game, insight=0, wild=0, event=1)
    counts = _explore_many(game, 200)
    assert counts["event:drunk"] == 200 and counts["event:scroll"] == 0


def test_a_seen_qiyu_can_come_back_from_the_rare_step(game):
    """企劃者 2026-10-03 改：奇遇看過之後不從奇遇池拿掉。"""
    _lake(game)
    game.state.player.seen_events.discard("scroll")
    game.content.events["scroll"].once = False
    game.content.config.rare_explore_chance = 1.0
    game.choose("act:explore")
    assert game.state.pending_event == "scroll"
    game.choose("choice:0")
    game.choose("act:explore")
    assert game.state.pending_event == "scroll"


def test_a_seen_once_event_never_comes_back(game):
    game.rng = random.Random(16)
    _lake(game)
    game.state.player.seen_events.discard("scroll")
    game.content.events["scroll"].qiyu = False  # 只是一次性
    game.content.config.rare_explore_chance = 1.0
    game.choose("act:explore")
    assert game.state.pending_event == "scroll"
    game.choose("choice:0")
    counts = _explore_many(game, 300)
    assert counts["event:scroll"] == 0 and counts["event:drunk"] > 0  # 奇遇池空了，回到三選一


# ── 事件那一支：地方痕跡與隨口應對（探索的多人與 LLM 玩法 §8，跟探索三選一疊在一起）──


def test_the_event_branch_still_reads_place_marks(game):
    """地方痕跡的後果事件是可重複事件、帶 marks_min：痕跡不夠時事件那一支抽不到它，夠了才抽得到。"""
    _lake(game)
    _only(game, insight=0, wild=0, event=1)
    game.content.events["drunk"].condition = Condition(marks_min={"lake:棚屋": 2})
    game.content.locations["lake"].enemies = []
    assert _explore_many(game, 20) == Counter(nothing=20)  # 唯一的可重複事件被痕跡擋住：事件那一支做不了
    game.state.world.marks["lake:棚屋"] = 2
    counts = _explore_many(game, 20)
    assert counts["event:drunk"] == 20


def test_a_free_text_event_from_the_event_branch_offers_its_free_answer(game):
    _lake(game)
    _only(game, insight=0, wild=0, event=1)
    game.content.events["drunk"].free_text = FreeTextChoice(prompt="自己想辦法……", stat="str")
    game.choose("act:explore")
    assert game.state.pending_event == "drunk"
    assert FREE_TEXT_OPTION in [o.id for o in game.options()]


# ── 野怪 ──────────────────────────────────────────────


def test_the_weakest_foe_jumps_out(content, game):
    rules.learn_skill(game.state, content, "fist")
    _lake(game, enemies=("boss", "thug"))
    _only(game, insight=0, wild=1, event=0)
    game.rng = random.Random(17)
    for _ in range(5):
        msgs = game._explore()
        assert msgs[0] == "你在湖邊走著，水寇小隊突然殺出！"
        assert game.state.battles[0].opponent == "水寇小隊"  # 難度 5，翻江龍是 200


def test_your_own_side_never_counts_as_the_weakest(content, game):
    _factions(content)
    content.squads["thug"].faction = "huang"
    game.state.player.faction = "huang"
    _lake(game, enemies=("boss", "thug"))
    _only(game, insight=0, wild=1, event=0)
    game._explore()
    assert game.state.battles[0].opponent == "翻江龍"


def test_a_tie_goes_to_the_first_foe_listed_here(content, game):
    content.squads["boss"].difficulty = content.squads["thug"].difficulty
    _lake(game, enemies=("boss", "thug"))
    _only(game, insight=0, wild=1, event=0)
    game._explore()
    assert game.state.battles[0].opponent == "翻江龍"


def test_a_wild_fight_costs_half_of_a_training_fight(content, game):
    """同樣落敗：遊歷扣上限的三成、兩成變內傷；探索撞上的野怪只扣一半。"""
    _lake(game, with_event=False)
    _only(game, insight=0, wild=1, event=0)
    game.rng = FixedRandom(0.0)  # 沒有武學、運氣最差：兩場都是落敗
    member = game.state.player.member
    now, cap = team.member_neili(content, member)
    game.choose("act:train")
    trained_blood, trained_hurt = now - team.member_neili(content, member)[0], member.injury
    assert game.state.battles[0].tier == "落敗"
    now, hurt = team.member_neili(content, member)[0], member.injury
    msgs = game.choose("act:explore")
    assert game.state.battles[0].tier == "落敗"
    assert now - team.member_neili(content, member)[0] == pytest.approx(trained_blood / 2)
    assert member.injury - hurt == pytest.approx(trained_hurt / 2)
    assert f"氣血 -{trained_blood / 2:.0f}" in msgs


def test_a_wild_loss_still_costs_a_tenth_of_the_silver(content, game):
    _lake(game, enemies=("boss",), with_event=False)
    _only(game, insight=0, wild=1, event=0)
    game._explore()
    record = game.state.battles[0]
    assert record.tier == "落敗" and record.silver == -5
    assert game.state.player.stats["silver"] == 45


def test_a_wild_win_pays_like_training_but_leaves_the_trend_and_no_post_fight_event(content, game):
    rules.learn_skill(game.state, content, "fist")
    content.events["chain_a"].actions = ["train"]  # 遊歷打完會接的戰後事件
    content.config.train_event_chance = 1.0
    content.config.train_stat_chance = 1.0
    _lake(game, with_event=False)
    _only(game, insight=0, wild=1, event=0)
    game.rng = FixedRandom(0.99)
    msgs = game.choose("act:explore")
    assert len(game.state.battles) == 1  # 戰報照常有一筆
    record = game.state.battles[0]
    assert record.tier in team.WIN_TIERS and record.opponent == "水寇小隊"
    assert (record.exp, record.xinde, record.silver) == (20, 10, 5)  # 獎勵照常
    assert any(line.endswith("+1") and line[:2] in ("臂力", "身法", "根骨") for line in msgs)  # 屬性機會照常
    assert game.state.world.trends["kou"] == 30  # 不推大勢（湖邊 train_trend kou:-1）
    assert game.state.pending_event is None  # 不接戰後事件
    game.choose("act:train")  # 對照：遊歷會推大勢、會接戰後事件
    assert game.state.world.trends["kou"] == 29 and game.state.pending_event == "chain_a"


def test_a_wild_fight_is_recorded_as_wild_and_shown_as_a_wild_encounter(content, game):
    """FB-023：探索撞上的野怪戰報 kind 是 wild、顯示「探索遇敵」；遊歷照舊 train／「遊歷」。"""
    from tianxia import battlelog

    rules.learn_skill(game.state, content, "fist")
    _lake(game, with_event=False)
    _only(game, insight=0, wild=1, event=0)
    game.rng = FixedRandom(0.99)
    game.choose("act:explore")
    record = game.state.battles[0]
    assert record.kind == "wild"
    assert "探索遇敵" in battlelog.card_text(record) and "遊歷" not in battlelog.card_text(record)
    assert "探索遇敵" in battlelog.detail_text(record)
    game.choose("act:train")
    trained = game.state.battles[0]
    assert trained.id != record.id and trained.kind == "train"
    assert "遊歷" in battlelog.detail_text(trained) and "探索遇敵" not in battlelog.detail_text(trained)


def test_the_journal_files_it_under_exploring(content, game):
    rules.learn_skill(game.state, content, "fist")
    _lake(game, with_event=False)
    _only(game, insight=0, wild=1, event=0)
    game.rng = FixedRandom(0.99)
    game.choose("act:explore")
    entry = game.state.journal[0]
    assert entry.title == "探索湖邊" and entry.battle_id == game.state.battles[0].id
    assert "你在湖邊走著，水寇小隊突然殺出！" in entry.lines


# ── 悟意境 ────────────────────────────────────────────


def test_the_insight_branch_teaches_an_insight_from_the_location(game):
    _lake(game)  # 湖邊的殘卷（一次性奇遇）標成看過，奇遇那一步不會插進來
    _only(game, insight=1)
    msgs = game._explore()
    assert game.state.player.insights[0] in ("feng", "shui")
    assert any("悟得" in m for m in msgs)
    assert game.state.player.materials == {}  # 探索不再撿素材


def test_the_insight_branch_always_gives_something_and_a_repeat_turns_into_xinde(game):
    """抽到「悟意境」那一支必定有收穫：第一次是新意境，悟到已經會的就化成心得。"""
    game.content.locations["town"].insights = ["huo"]
    game.content.config.rare_explore_chance = 0.0
    _only(game, insight=1, wild=0, event=0)
    game.state.player.stats["xinde"] = 0
    first = game._explore()
    assert first == ["你在小鎮靜下心來，看了好一陣。", "你悟得了「火」的意境（屬剛）！"]
    assert game.state.player.insights == ["huo"] and game.state.player.stats["xinde"] == 0
    for n in range(1, 4):
        msgs = game._explore()
        assert msgs[0] == "你在小鎮靜下心來，看了好一陣。" and msgs[-1] == "心得 +10"
        assert not any("悟得" in m for m in msgs)
        assert game.state.player.insights == ["huo"] and game.state.player.stats["xinde"] == 10 * n


def test_a_place_with_no_insights_listed_still_teaches_a_basic_one(game):
    _lake(game)
    game.content.locations["lake"].insights = []
    _only(game, insight=1)
    game._explore()
    assert game.state.player.insights[0] in ("feng", "huo", "shui", "shan")


def test_without_any_insight_in_the_content_the_insight_share_goes_to_the_other_two(game):
    game.content.insights = {}
    game.rng = random.Random(18)
    _lake(game)
    counts = _explore_many(game)
    assert counts["insight"] == 0 and counts["nothing"] == 0
    assert counts["wild"] / N == pytest.approx(35 / 60, abs=0.035)


# ── 傳奇道具破境丹（企劃者 2026-10-05）：探索不論走哪一支，結束後都擲一次 ──────────────────


def _legend_setup(game, branch):
    """把探索逼到某一支，並讓破境丹一定掉。"""
    nothing = branch == "nothing"
    _lake(game, enemies=() if nothing else ("thug",), with_event=not nothing)
    game.content.config.explore_legend_chance = 1.0
    game.content.config.rare_explore_chance = 0.0
    if branch == "insight":
        _only(game, insight=1, wild=0, event=0)
    elif branch == "wild":
        _only(game, insight=0, wild=1, event=0)
    elif branch == "event":
        _only(game, insight=0, wild=0, event=1)
    elif nothing:  # 野怪與事件兩支都做不了、悟意境的比例是 0：三支都做不了
        _only(game, insight=0, wild=35, event=25)
    else:  # "rare"：奇遇判定先於三選一
        game.state.player.seen_events.discard("scroll")
        game.content.config.rare_explore_chance = 1.0


@pytest.mark.parametrize("branch", ["insight", "wild", "event", "nothing", "rare"])
def test_every_explore_branch_can_turn_up_a_pill_and_the_entry_shows_it_with_the_shine(game, branch):
    _legend_setup(game, branch)
    game.state.player.tutorial_step = 3  # 引導已走完，免得引導的獎勵混進這則紀錄
    msgs = game.choose("act:explore")
    cfg = game.content.config
    line = f"獲得 【{cfg.legend_item_name}】一枚——{cfg.legend_item_note}"
    assert game.state.player.legend_items == 1
    assert msgs[-2:] == [line, "破境丹 +1"]  # 兩行都接在這次探索本來的訊息後面
    entry = game.state.journal[0]
    assert entry.title.startswith("探索") and "破境丹 +1" in entry.changes and line in entry.lines
    assert journal._line_class(line) == "tx-line tx-new"  # 「獲得 」開頭的新東西，掃一道光


def test_an_explore_that_finds_nothing_still_says_so_before_the_pill(game):
    _legend_setup(game, "nothing")
    assert game._explore() == [
        "你四處走走，一無所獲。",
        f"獲得 【破境丹】一枚——{game.content.config.legend_item_note}",
        "破境丹 +1",
    ]


def test_each_explore_rolls_for_the_pill_once_and_the_pills_pile_up(game):
    _legend_setup(game, "nothing")
    for _ in range(3):
        game._explore()
    assert game.state.player.legend_items == 3


def test_the_pill_roll_uses_the_configured_chance(game):
    _legend_setup(game, "nothing")
    game.content.config.explore_legend_chance = 0.02
    game.rng = FixedRandom(0.019)
    assert "破境丹 +1" in game._explore()
    game.rng = FixedRandom(0.02)  # 擲到的數字要小於機率才中
    assert "破境丹 +1" not in game._explore() and game.state.player.legend_items == 1


def test_a_zero_chance_draws_no_random_number_so_seeded_runs_do_not_shift(game):
    """機率 0 的時候不擲這顆骰（要先判斷機率大於 0）：測試用內容把它設成 0，既有的固定種子序列才不會位移。"""
    _legend_setup(game, "nothing")  # 一無所獲這一支本來就不用亂數
    game.content.config.explore_legend_chance = 0.0
    before = game.rng.getstate()
    assert game._explore() == ["你四處走走，一無所獲。"]
    assert game.rng.getstate() == before and game.state.player.legend_items == 0
    game.content.config.explore_legend_chance = 0.02
    game._explore()
    assert game.rng.getstate() != before  # 對照：機率大於 0 才會多擲一顆


# ── 真實內容 ──────────────────────────────────────────


def test_the_real_places_split_into_the_designed_kinds():
    """規格第三節的地點數：營寨 6、城鎮 17、荒野 17。"""
    content = load_content(Path(__file__).parent.parent / "content")
    kinds = Counter(content.config.explore_mix_of(loc.tags).kind for loc in content.locations.values())
    assert kinds == Counter(camp=6, town=17, wild=17)
