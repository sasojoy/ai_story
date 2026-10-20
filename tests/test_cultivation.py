"""修練（武學重構，Joy 2026-10-20「我想改整個架構，不要縫縫補補」）：品級不靠修練衝——合成與自創才長品級。
修練頁只剩最後一步：上品、第十成、意境槽裝滿（cultivation.ready）→ 打贏硬仗的契機（seize）擲一次頓悟，
或服一枚破境丹強行衝關（cultivate(use_legend=True)，force_odds）。衝品的階梯（40／60／必成、保底、搭配、火候）都拿掉了，
這裡只量剩下的：門檻、服丹衝關、契機、第一個練成絕學的人定名、引擎寫不寫江湖紀錄。"""
import random
import re

import pytest

from tianxia import cultivation, fusion, library, skillview, team
from tianxia.martial_arts import Insight, generate_from_name
from tianxia.state import new_game_state

LOW = {"下品": 100.0, "中品": 0.0, "上品": 0.0, "絕學": 0.0}
AFFINITY = ["快", "剛", "柔", "慢"]  # 旋風腿的相容屬性：四個基本意境都收得下（上品 4 格剛好裝滿）
BASICS = ["feng", "huo", "shui", "shan"]  # 測試內容的四個基本意境（快、剛、柔、慢）


class Fixed(random.Random):
    """random() 永遠回傳固定值（同 conftest.FixedRandom）。"""

    def __init__(self, value):
        super().__init__(0)
        self.value = value

    def random(self):
        return self.value


WIN, LOSE = Fixed(0.0), Fixed(0.999)
PILL = "你服下一枚【破境丹】，關起門來強行衝關。"


def kicker_art():
    """全服登記的那一份只是門面（武學重構）：下品、相容快剛柔慢、合成來的；品級、成數、槽都在玩家自己身上。"""
    return generate_from_name("旋風腿", "武學", "旋風腿", weights=LOW, attribute="快").model_copy(
        update={"origin": "fused", "base": "basic_fist", "affinity": AFFINITY},
    )


def equip(state, art_id="旋風腿", insights=BASICS):
    state.player.arts = [art_id]
    state.player.insights = list(insights)
    state.player.stamina = 150
    return state


def ripen(state, art_id="旋風腿", level=10, quality="上品", slots=BASICS):
    """練到極處（cultivation.ready）：上品、第十成、意境槽（上品 4 格）都裝滿。"""
    p = state.player
    p.art_quality[art_id] = quality
    if art_id == p.member.wugong_id:
        p.member.wugong_level = level
    elif art_id == p.member.neigong_id:
        p.member.neigong_level = level
    else:
        p.art_levels[art_id] = level
    p.art_slots[art_id] = list(slots)
    return state


@pytest.fixture
def kicker(state, world):
    """功法庫裡一門到了極處的旋風腿、四個基本意境都裝在它身上、體力滿。"""
    world.claim_skill_name(kicker_art())
    return ripen(equip(state))


# ── 門檻：上品、第十成、槽裝滿 ──────────────────────────


def test_ready_needs_an_upper_grade_art_at_ten_levels_with_every_slot_filled(kicker, content, world):
    assert cultivation.ready(kicker, content, world, "旋風腿") == (True, None)
    kicker.player.art_levels["旋風腿"] = 9
    ok, why = cultivation.ready(kicker, content, world, "旋風腿")
    assert not ok and why == cultivation.NOT_RIPE_LINE.format(name="旋風腿", level=9, filled=4, slots=4)
    kicker.player.art_levels["旋風腿"] = 10
    kicker.player.art_slots["旋風腿"] = ["feng", "huo", "shui", None]
    ok, why = cultivation.ready(kicker, content, world, "旋風腿")
    assert not ok and "槽 3／4" in why


@pytest.mark.parametrize("quality", ["下品", "中品", "絕學"])
def test_only_an_upper_grade_art_is_on_the_last_step(kicker, content, world, quality):
    """不是上品的沒有「極處」可言：ready 回 (False, None)，不寫原因（原因由 cultivate_problem 寫）。"""
    kicker.player.art_quality["旋風腿"] = quality
    assert cultivation.ready(kicker, content, world, "旋風腿") == (False, None)


def test_a_fixed_content_art_never_reaches_the_last_step(state, content, world):
    """寫死的武學（內容寫了功效的本命、不是下品的內容武學）槽是空清單、裝不了，也不衝絕學。"""
    state.player.member.wugong_id, state.player.member.wugong_level = "fist", 10
    state.player.art_quality["fist"] = "上品"
    assert cultivation.ready(state, content, world, "fist") == (False, None)
    assert cultivation.cultivate_problem(state, content, world, "fist", use_legend=True) is not None


def test_cultivate_problem_says_why_in_the_configured_words(kicker, content, world):
    p = kicker.player
    assert cultivation.cultivate_problem(kicker, content, world, "旋風腿") == cultivation.CHANCE_LINE.format(name="旋風腿", pill="破境丹")
    assert cultivation.cultivate_problem(kicker, content, world, "旋風腿", use_legend=True) == cultivation.CHANCE_LINE.format(name="旋風腿", pill="破境丹")  # 勾了卻沒有丹
    p.legend_items = 1
    assert cultivation.cultivate_problem(kicker, content, world, "旋風腿", use_legend=True) is None
    assert cultivation.cultivate_problem(kicker, content, world, "旋風腿", use_legend=False) is not None  # 沒勾：只能等契機
    p.art_levels["旋風腿"] = 9
    assert cultivation.cultivate_problem(kicker, content, world, "旋風腿", use_legend=True) == cultivation.NOT_RIPE_LINE.format(name="旋風腿", level=9, filled=4, slots=4)
    p.art_levels["旋風腿"] = 10
    p.art_quality["旋風腿"] = "中品"
    assert cultivation.cultivate_problem(kicker, content, world, "旋風腿", use_legend=True) == cultivation.NO_RANK_LINE
    p.art_quality["旋風腿"] = "絕學"
    assert "修無可修" in cultivation.cultivate_problem(kicker, content, world, "旋風腿", use_legend=True)
    p.art_quality["旋風腿"] = "上品"
    p.stamina = 5
    assert "體力不足" in cultivation.cultivate_problem(kicker, content, world, "旋風腿", use_legend=True)
    p.stamina = 150
    p.arts = []
    assert "你沒有這門武學" in cultivation.cultivate_problem(kicker, content, world, "旋風腿", use_legend=True)


def test_the_pill_name_in_the_last_step_line_follows_config(kicker, content, world):
    content.config.legend_item_name = "天機丹"
    assert "服一枚天機丹強行衝關" in cultivation.cultivate_problem(kicker, content, world, "旋風腿")


# ── 服丹強行衝關 ──────────────────────────


def test_force_odds_follow_the_pill_bonus_and_the_players_insight(kicker, content, world):
    """機會＝legend_item_bonus × 悟性，夾在 1～breakthrough.max_chance；不看成數、搭配、地點。"""
    p = kicker.player
    assert cultivation.force_odds(kicker, content, world, "旋風腿") == 15
    p.stats["wis"] = 15
    assert cultivation.force_odds(kicker, content, world, "旋風腿") == 20  # 15 × 1.3 = 19.5
    p.stats["wis"] = 1
    assert cultivation.force_odds(kicker, content, world, "旋風腿") == 13  # 15 × 0.88 = 13.2
    p.stats["wis"] = 5
    content.config.legend_item_bonus = 100
    assert cultivation.force_odds(kicker, content, world, "旋風腿") == content.config.breakthrough.max_chance
    content.config.legend_item_bonus = 0
    assert cultivation.force_odds(kicker, content, world, "旋風腿") == 1


def test_a_won_force_promotes_this_player_only_and_uses_one_pill(kicker, content, world):
    p = kicker.player
    p.legend_items = 2
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", WIN, use_legend=True)
    assert msgs[0] == PILL and "【旋風腿】衝開了最後那一層，從上品晉為絕學！" == msgs[1]
    assert "取一個正式的名字" in msgs[2] and msgs[3] == "體力 -10"
    assert p.art_quality["旋風腿"] == "絕學" and p.legend_items == 1 and p.stamina == 140 and p.naming == "旋風腿"
    assert world.get_skill("旋風腿").quality == "下品"  # 全服登記的那一份不動


def test_a_lost_force_still_uses_the_pill_and_says_the_odds(kicker, content, world):
    p = kicker.player
    p.legend_items = 2
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", LOSE, use_legend=True)
    assert msgs == [PILL, "【旋風腿】撞在那一層上，又彈了回來（約 15% 的機會）。", "體力 -10"]
    assert p.art_quality["旋風腿"] == "上品" and p.legend_items == 1 and p.stamina == 140 and p.naming is None
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", LOSE, use_legend=True)  # 沒成火候還在：再服一枚照樣可以衝
    assert msgs[0] == PILL and p.legend_items == 0
    assert cultivation.cultivate_problem(kicker, content, world, "旋風腿", use_legend=True) == cultivation.CHANCE_LINE.format(name="旋風腿", pill="破境丹")  # 丹用完了


def test_the_roll_wins_strictly_under_the_odds(kicker, content, world):
    p = kicker.player
    p.legend_items = 2
    assert "彈了回來" in cultivation.cultivate(kicker, content, world, "旋風腿", Fixed(0.15), use_legend=True)[1]  # 15 不小於 15
    assert "晉為絕學" in cultivation.cultivate(kicker, content, world, "旋風腿", Fixed(0.149), use_legend=True)[1]


def test_the_level_does_not_change_on_a_quality_rise(kicker, content, world):
    kicker.player.legend_items = 1
    cultivation.cultivate(kicker, content, world, "旋風腿", WIN, use_legend=True)
    assert kicker.player.art_levels["旋風腿"] == 10 and kicker.player.art_slots["旋風腿"] == BASICS  # 槽裡的意境照舊裝著


def test_a_worn_art_can_be_forced_too(state, content, world):
    """修練不看功法在庫裡還是配在身上（兩處都算擁有）；配在身上的成也不動。"""
    world.claim_skill_name(kicker_art())
    state.player.member.wugong_id = "旋風腿"
    equip(state)
    state.player.arts = []
    ripen(state)
    state.player.legend_items = 1
    cultivation.cultivate(state, content, world, "旋風腿", WIN, use_legend=True)
    assert state.player.art_quality["旋風腿"] == "絕學" and state.player.member.wugong_level == 10


def test_the_notes_use_the_configured_pill_name(kicker, content, world):
    content.config.legend_item_name = "天機丹"
    kicker.player.legend_items = 1
    assert cultivation.cultivate(kicker, content, world, "旋風腿", LOSE, use_legend=True)[0] == "你服下一枚【天機丹】，關起門來強行衝關。"


@pytest.mark.parametrize("break_it", [
    lambda p: p.art_slots.update({"旋風腿": ["feng", "huo", "shui", None]}),  # 槽沒裝滿
    lambda p: p.art_levels.update({"旋風腿": 9}),                            # 還沒第十成
    lambda p: setattr(p, "stamina", 5),                                       # 體力不足
    lambda p: setattr(p, "naming", "別的絕學"),                                 # 還有一門絕學等著取名
    lambda p: setattr(p, "arts", []),                                         # 沒有這門武學
    lambda p: setattr(p, "legend_items", 0),                                  # 頁面過期：丹已經沒有了
])
def test_a_refused_try_with_the_box_ticked_keeps_the_pill_and_changes_nothing(kicker, content, world, break_it):
    p = kicker.player
    p.legend_items = 1
    break_it(p)
    stamina, pills = p.stamina, p.legend_items
    assert cultivation.cultivate_problem(kicker, content, world, "旋風腿", use_legend=True) is not None
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", WIN, use_legend=True)
    assert len(msgs) == 1 and p.legend_items == pills and p.stamina == stamina and p.art_quality["旋風腿"] == "上品"


def test_a_save_from_before_the_pill_loads_with_none(state):
    from tianxia.state import PlayerState

    data = state.player.model_dump()
    data.pop("legend_items")
    assert PlayerState.model_validate(data).legend_items == 0 and state.player.legend_items == 0


def test_a_roll_says_what_it_cost_in_stamina_right_after_the_result(kicker, content, world):
    """FB-070 (b)：修練的回話寫出花了多少體力，跟合併的回話（「心得 -5」「體力 -5」）同一種寫法；數字照 Config.cultivate_stamina。
    服丹的話在前、擲骰的結果、第一個練成絕學的話，體力那一行最後。"""
    content.config.cultivate_stamina = 7
    p = kicker.player
    p.legend_items = 2
    lost = cultivation.cultivate(kicker, content, world, "旋風腿", LOSE, use_legend=True)
    assert len(lost) == 3 and "彈了回來" in lost[1] and lost[2] == "體力 -7"
    peerless = cultivation.cultivate(kicker, content, world, "旋風腿", WIN, use_legend=True)
    assert peerless[0] == PILL and "晉為絕學" in peerless[1] and "取一個正式的名字" in peerless[2]
    assert peerless[3] == "體力 -7"  # 體力那一行在最後（定名的話也在它前面）
    assert p.stamina == 150 - 2 * 7


# ── 契機（打贏硬仗擲一次頓悟）──────────────────────────


def _worn(state, level=10, slots=BASICS):
    """旋風腿穿在身上、上品、第十成、槽裝滿。"""
    p = state.player
    p.arts, p.member.wugong_id = [], "旋風腿"
    return ripen(state, level=level, slots=slots)


def test_a_hard_win_at_the_last_step_can_break_through_and_names_the_first(kicker, content, world):
    _worn(kicker)
    msgs = cultivation.seize(kicker, content, world, 0.5, WIN)
    assert msgs[0] == "這一戰打到最後，【旋風腿】忽然通了——從上品晉為絕學！"
    assert kicker.player.art_quality["旋風腿"] == "絕學" and kicker.player.naming == "旋風腿"


def test_a_missed_chance_leaves_a_soft_hint_and_changes_nothing(kicker, content, world):
    _worn(kicker)
    assert cultivation.seize(kicker, content, world, 0.5, LOSE) == ["打到緊處，【旋風腿】似乎摸到了什麼，轉眼又滑走了。"]
    assert kicker.player.art_quality["旋風腿"] == "上品" and kicker.player.naming is None


@pytest.mark.parametrize(("ratio", "level", "slots"), [
    (0.29, 10, BASICS),                          # 仗不夠硬
    (0.5, 9, BASICS),                            # 還沒第十成
    (0.5, 10, ["feng", "huo", "shui", None]),    # 槽沒裝滿
])
def test_no_chance_without_a_hard_enough_fight_ten_levels_and_full_slots(kicker, content, world, ratio, level, slots):
    _worn(kicker, level=level, slots=slots)
    assert cultivation.seize(kicker, content, world, ratio, WIN) == []
    assert kicker.player.art_quality["旋風腿"] == "上品"


def test_a_chance_only_looks_at_the_two_worn_arts(kicker, content, world):
    """旋風腿躺在功法庫裡（到了極處也一樣）：契機只看身上練著的兩門。"""
    assert cultivation.seize(kicker, content, world, 1.0, WIN) == []
    assert kicker.player.art_quality["旋風腿"] == "上品"


def test_a_chance_is_held_back_while_another_art_waits_for_its_name(kicker, content, world):
    _worn(kicker)
    kicker.player.naming = "別的絕學"
    assert cultivation.seize(kicker, content, world, 1.0, WIN) == [] and kicker.player.art_quality["旋風腿"] == "上品"


def test_the_breakthrough_chance_grows_with_how_hard_the_fight_was(kicker, content, world):
    """機會＝25% ×（難度比 ÷ 0.5）× 悟性，夾在 1～60：難度比 0.3 是 15%、0.5 是 25%、1.0 是 50%、3.0 夾在 60%。"""
    for ratio, odds in ((0.3, 15), (0.5, 25), (1.0, 50), (3.0, 60)):
        _worn(kicker)
        kicker.player.naming = None
        assert cultivation.seize(kicker, content, world, ratio, Fixed((odds - 0.01) / 100))[0].startswith("這一戰")
        _worn(kicker)
        kicker.player.naming = None
        assert cultivation.seize(kicker, content, world, ratio, Fixed((odds + 0.01) / 100))[0].startswith("打到緊處")


def test_the_chance_is_switched_off_by_a_zero_chance(kicker, content, world):
    _worn(kicker)
    content.config.breakthrough.chance = 0
    assert cultivation.seize(kicker, content, world, 1.0, WIN) == []


# ── 第一個練成絕學的人定名 ──────────────────────────


def _master(state, content, world, art_id="旋風腿", rng=WIN):
    """服一枚丹衝開（擲骰預設贏）。"""
    state.player.legend_items += 1
    return cultivation.cultivate(state, content, world, art_id, rng, use_legend=True)


def test_the_first_to_reach_peerless_names_it_for_everyone(kicker, content, world):
    msgs = _master(kicker, content, world)
    assert kicker.player.naming == "旋風腿" and any("取一個正式的名字" in m for m in msgs)
    cultivation.name_mastered(kicker, content, world, "風神腿")
    assert world.get_skill("旋風腿").name == "風神腿" and kicker.player.naming is None
    assert any("風神腿" in r.text for r in kicker.world.chronicle)


def test_the_chronicle_line_names_the_old_name_and_the_new_one(kicker, content, world):
    """F14：每一件各寫一行（換季那一行是另外一份總結，T10）。"""
    _master(kicker, content, world)
    cultivation.name_mastered(kicker, content, world, "風神腿")
    assert [r.text for r in kicker.world.chronicle] == ["沈浪把【旋風腿】練成絕學，為之定名【風神腿】。"]


def test_an_anonymous_namer_goes_into_the_chronicle_by_name(kicker, content, world):
    """匿名行走只作用在地方傳聞（傳聞分層第七節，企劃者 2026-10-06）：江湖史一律寫名號，定名那一筆也是。"""
    kicker.player.anonymous = True
    _master(kicker, content, world)
    cultivation.name_mastered(kicker, content, world, "風神腿")
    assert [r.text for r in kicker.world.chronicle] == ["沈浪把【旋風腿】練成絕學，為之定名【風神腿】。"]


def test_the_second_to_reach_peerless_sees_an_anonymous_first_by_name(kicker, content, world):
    """第一個練成的人匿名行走：取名權照名號認（身分），後到的人看到的也是名號（江湖上的首創不能匿名）。"""
    kicker.player.anonymous = True
    _master(kicker, content, world)
    assert world.master_of("旋風腿") == "沈浪" and kicker.player.naming == "旋風腿"
    other = ripen(equip(new_game_state(content, "乙")))
    msgs = _master(other, content, world)
    assert "這門武學已由沈浪率先練成絕學。" in msgs and not any("某位少俠" in m for m in msgs)


def test_the_season_firsts_write_an_anonymous_player_by_name(state, content, world):
    """換季寫進江湖史的首創（合成、首悟、練成絕學）：匿名行走的人也寫名號，走真的合成（武學＋武學）、合併、服丹衝關、定名。"""
    from unittest import mock

    from tianxia import naming

    content.config.auto_open_first_season = True
    world.seed_first_season(content)
    state.player.anonymous = True
    state.player.member.wugong_id, state.player.member.neigong_id = "basic_fist", "basic_breath"
    state.player.insights = list(BASICS)
    state.player.stats["xinde"], state.player.stamina = 100, 150
    model = mock.Mock()
    model.chat_structured.side_effect = [naming.NameReply(name="旋風腿"), naming.NameReply(name="燎原")]
    art, _ = fusion.blend(state, content, world, model, "basic_fist", "basic_breath")  # 武學重構：合成只剩武學＋武學
    assert art is not None and art.name == "旋風腿"
    fusion.merge(state, content, world, model, "feng", "huo")
    ripen(state, art.id)
    _master(state, content, world, art.id)
    cultivation.name_mastered(state, content, world, "風神腿")
    world.mutate_season(lambda season: setattr(season, "ended", True))
    assert world.next_season(content, now=1.0)
    [(_, entries)] = world.chronicle_before(2)
    assert [e.text for e in entries] == [
        "第 1 季合成首創 1 門：【風神腿】沈浪",
        "第 1 季首悟意境 1 個：「燎原」沈浪",
        "第 1 季練成絕學 1 門：【風神腿】沈浪",
    ]


def test_the_second_to_reach_peerless_does_not_name_it(kicker, content, world):
    world.claim_master("旋風腿", "甲")
    msgs = _master(kicker, content, world)
    assert kicker.player.naming is None and any("甲" in m for m in msgs)


def test_two_players_reaching_peerless_together_only_the_first_names_it(kicker, content, world):
    """兩個人這一刻都把同一門武學練成絕學：claim_master 是原子的，只有先登記的拿到取名權；
    後到的沒有 naming，也取不了名（沒有等著他取名的武學），全服的名字只被改一次。"""
    other = ripen(equip(new_game_state(content, "乙")))
    _master(kicker, content, world)
    msgs = _master(other, content, world)
    assert kicker.player.naming == "旋風腿" and other.player.naming is None
    assert any("沈浪" in m for m in msgs) and world.master_of("旋風腿") == "沈浪"
    assert cultivation.name_mastered(other, content, world, "裂地腿") == ["（沒有等著你取名的武學。）"]
    assert world.get_skill("旋風腿").name == "旋風腿"  # 後到的沒改成
    cultivation.name_mastered(kicker, content, world, "風神腿")
    assert world.get_skill("旋風腿").name == "風神腿"
    assert cultivation.name_mastered(kicker, content, world, "另一個名") == ["（沒有等著你取名的武學。）"]  # 一門只取一次


def test_the_last_step_to_peerless_waits_until_the_pending_naming_is_done(kicker, content, world):
    """取名的權利一人一次只留一門（PlayerState.naming）：還有一門練成了絕學沒定名時，不能再衝第二門的絕學——
    不然第二門成了、第一門的取名權被蓋掉，那門就永遠沒有人替它定名。服丹衝關與契機都擋。"""
    world.claim_skill_name(generate_from_name("裂石拳", "武學", "裂石拳"))
    kicker.player.naming = "裂石拳"
    kicker.player.legend_items = 1
    assert "【裂石拳】還沒定名" in cultivation.cultivate(kicker, content, world, "旋風腿", WIN, use_legend=True)[0]
    assert kicker.player.stamina == 150 and kicker.player.art_quality["旋風腿"] == "上品" and kicker.player.naming == "裂石拳"
    assert kicker.player.legend_items == 1
    cultivation.name_mastered(kicker, content, world, "碎石拳")
    assert kicker.player.naming is None
    assert cultivation.cultivate_problem(kicker, content, world, "旋風腿", use_legend=True) is None


def test_a_bad_or_taken_name_is_refused(kicker, content, world):
    kicker.player.naming = "旋風腿"
    world.claim_master("旋風腿", kicker.player.name)
    assert "長度" in cultivation.name_mastered(kicker, content, world, "風")[0]
    world.claim_skill_name(generate_from_name("裂石拳", "武學", "裂石拳"))
    assert "有人用了" in cultivation.name_mastered(kicker, content, world, "裂石拳")[0]
    assert kicker.player.naming == "旋風腿"


def test_a_name_used_by_an_alias_or_an_insight_is_refused(kicker, content, world):
    """全服不能重名：別門武學改過的新名字、合併出來的意境名字，跟內容裡的意境名字（過濾那一關）一樣都不行。"""
    kicker.player.naming = "旋風腿"
    world.claim_skill_name(generate_from_name("裂石拳", "武學", "裂石拳"))
    assert world.rename_skill("裂石拳", "碎石拳")
    world.claim_insight_recipe("合|feng+huo", Insight(id="燎原", name="燎原", attribute="陽", creator="乙"))
    assert "有人用了" in cultivation.name_mastered(kicker, content, world, "碎石拳")[0]
    assert "有人用了" in cultivation.name_mastered(kicker, content, world, "燎原")[0]
    assert "意境同名" in cultivation.name_mastered(kicker, content, world, "浩然")[0]  # 內容裡的意境
    assert kicker.player.naming == "旋風腿" and world.get_skill("旋風腿").name == "旋風腿"


def test_naming_it_with_the_name_it_already_has_keeps_the_name(kicker, content, world):
    """第一個練成的人覺得模型取的名字就很好：這算定名（取名權用掉、江湖史記一筆），名字不變——
    不能說成「已經有人用了」，用的人就是這門武學自己。"""
    kicker.player.naming = "旋風腿"
    world.claim_master("旋風腿", kicker.player.name)
    msgs = cultivation.name_mastered(kicker, content, world, "旋風腿")
    assert msgs == ["從今以後，江湖上這門武學就叫【旋風腿】。"] and kicker.player.naming is None
    assert world.get_skill("旋風腿").name == "旋風腿" and not world.is_skill_name_taken("風神腿")
    assert [r.text for r in kicker.world.chronicle] == ["沈浪把【旋風腿】練成絕學，為之定名【旋風腿】。"]
    assert cultivation.name_mastered(kicker, content, world, "風神腿") == ["（沒有等著你取名的武學。）"]  # 取名權用掉了


def test_a_name_is_cleaned_before_it_is_checked(kicker, content, world):
    kicker.player.naming = "旋風腿"
    cultivation.name_mastered(kicker, content, world, "《風神腿》")
    assert world.get_skill("旋風腿").name == "風神腿"


def test_naming_an_art_that_has_gone_missing_says_so_and_changes_nothing(state, content, world):
    state.player.naming = "不存在的功法"
    assert "找不到" in cultivation.name_mastered(state, content, world, "風神腿")[0]
    assert state.player.naming == "不存在的功法" and state.world.chronicle == []


def test_after_a_rename_the_name_shows_everywhere_and_the_id_still_keys(kicker, content, world):
    """Task 1 的提醒：改名之後 id 跟顯示的名字不一樣。顯示的地方都要寫新名字（功法庫、功法卡、修練頁那一列），
    認東西的地方都要照 id（擁有、品質、熟練度、登記）。"""
    _master(kicker, content, world)
    cultivation.name_mastered(kicker, content, world, "風神腿")
    # 顯示：新名字
    assert team.resolve_art("旋風腿", content, world).name == "風神腿"
    assert team.player_art(kicker, content, world, "旋風腿").name == "風神腿"
    (row,) = [r for r in skillview.art_rows(kicker, content, world) if r["id"] == "旋風腿"]
    assert (row["name"], row["quality"], row["attribute"], row["level"]) == ("風神腿", "絕學", "快", 10)
    # 認東西：還是 id
    assert "旋風腿" in library.owned_arts(kicker) and kicker.player.art_quality == {"旋風腿": "絕學"}
    assert world.get_skill("旋風腿") is not None and world.get_skill("風神腿") is None
    assert "修無可修" in cultivation.cultivate_problem(kicker, content, world, "旋風腿")


def test_the_new_name_cannot_be_taken_by_anyone_else_afterwards(kicker, content, world):
    kicker.player.naming = "旋風腿"
    cultivation.name_mastered(kicker, content, world, "風神腿")
    assert world.is_skill_name_taken("風神腿")
    assert not world.claim_skill_name(generate_from_name("風神腿", "武學", "風神腿"))


# ── 以心得換破境丹（細的在 test_legend_xinde）──────────────────────────


def test_buying_a_pill_is_off_when_the_price_is_zero(kicker, content):
    """測試內容 legend_xinde_price 是 0：換不到、什麼都不扣。"""
    assert cultivation.legend_price(kicker, content) is None
    kicker.player.stats["xinde"] = 5000
    assert cultivation.buy_legend(kicker, content) == ["破境丹換不到。"]
    assert kicker.player.legend_items == 0 and kicker.player.stats["xinde"] == 5000


# ── 引擎：修練與定名寫不寫江湖紀錄（F12：真的有事發生才寫）──────────────────


@pytest.fixture
def adept(game):
    """一個配好了旋風腿（庫裡、到了極處）、手上一枚破境丹、體力滿的角色。擲骰預設全贏，要輸的測試自己換 game.rng。"""
    game.world.claim_skill_name(kicker_art())
    ripen(equip(game.state))
    game.state.player.legend_items = 1
    game.rng = WIN
    return game


def test_cultivating_writes_one_journal_entry_with_the_pill_next_to_the_stamina(adept):
    msgs = adept.cultivate("旋風腿", use_legend=True)
    entry = adept.state.journal[0]
    assert msgs[0] == PILL and "晉為絕學" in msgs[1]
    assert entry.title == "修練" and entry.tag == msgs[1] and entry.changes == ["體力 -10", "破境丹 -1"]
    assert adept.state.player.art_quality["旋風腿"] == "絕學"
    assert entry.tag == msgs[1]  # 結果標記是擲骰的結果，不是服丹那一句


def test_the_cultivate_reply_shows_the_stamina_but_the_journal_counts_it_once(adept):
    """FB-070 (b)：修練頁頂的回話有「體力 -10」（狀態列與江湖紀錄本來就有）；紀錄的數值變化還是只算一次，
    敘事也不多一行「體力 -10」。被拒絕的照舊只回那一句原因，沒有體力那一行。"""
    msgs = adept.cultivate("旋風腿", use_legend=True)
    assert f"體力 -{adept.content.config.cultivate_stamina}" in msgs
    entry = adept.state.journal[0]
    assert entry.changes == ["體力 -10", "破境丹 -1"] and entry.lines == [] and entry.tag == msgs[1]
    adept.state.player.art_quality["旋風腿"], adept.state.player.naming = "上品", None
    adept.state.player.legend_items, adept.state.player.stamina = 1, 5
    refused = adept.cultivate("旋風腿", use_legend=True)
    assert len(refused) == 1 and "體力不足" in refused[0] and not any(m.startswith("體力 -") for m in refused)


def test_a_failed_roll_is_something_that_happened_and_is_written(adept):
    adept.rng = LOSE
    msgs = adept.cultivate("旋風腿", use_legend=True)
    entry = adept.state.journal[0]
    assert msgs[0] == PILL and "彈了回來" in msgs[1] and adept.state.player.legend_items == 0
    assert entry.title == "修練" and entry.tag == msgs[1] and entry.changes == ["體力 -10", "破境丹 -1"]  # 輸了也花了體力與丹


def test_an_unticked_try_rolls_nothing_and_keeps_the_pill(adept):
    """沒勾「服下破境丹」：只回「等契機或服丹」那一句，不擲骰、不寫紀錄、丹留著。"""
    before = list(adept.state.journal)
    msgs = adept.cultivate("旋風腿")
    assert msgs == [cultivation.CHANCE_LINE.format(name="旋風腿", pill="破境丹")]
    assert adept.state.player.legend_items == 1 and adept.state.player.stamina == 150 and adept.state.journal == before


def test_a_refused_try_with_the_box_ticked_keeps_the_pill_and_writes_no_entry(adept):
    p = adept.state.player
    p.stamina = 5
    before = list(adept.state.journal)
    assert "體力不足" in adept.cultivate("旋風腿", use_legend=True)[0]
    assert p.legend_items == 1 and adept.state.journal == before


def test_the_stamina_and_pills_of_consecutive_rolls_add_up_in_one_merged_entry(adept):
    adept.rng = LOSE
    adept.state.player.legend_items = 2
    adept.cultivate("旋風腿", use_legend=True)
    adept.cultivate("旋風腿", use_legend=True)
    entries = [e for e in adept.state.journal if e.title == "修練"]
    assert len(entries) == 1 and entries[0].changes == ["體力 -20", "破境丹 -2"] and adept.state.player.stamina == 130


def test_two_rolls_in_a_row_read_as_two_on_the_just_now_card(adept):
    """FB-070 (c)：連續修練兩次（彈回來、再衝開）：「剛剛」那一則照順序兩行、每一句只出現一次（以前最後一句
    寫在標題旁又列在底下，看起來像修了三次），體力照舊加總成「體力 -20」。"""
    from html import escape

    adept.state.player.legend_items = 2
    adept.rng = LOSE
    lost = adept.cultivate("旋風腿", use_legend=True)[1]
    adept.rng = WIN
    won = adept.cultivate("旋風腿", use_legend=True)[1]
    card = adept.now_entry_html()
    assert "彈了回來" in lost and "晉為絕學" in won
    assert re.findall(r'<span class="tx-tag">(.*?)</span>', card) + re.findall(
        r'<div class="tx-line[^"]*">(.*?)</div>', card) == [escape(lost), escape(won)]
    assert '<span class="tx-chg tx-down">體力 -20</span>' in card


def test_the_stamina_change_is_not_written_for_a_naming(adept):
    adept.state.player.naming = "旋風腿"
    adept.name_mastered("風神腿")
    assert adept.state.journal[0].changes == [] and adept.state.player.stamina == 150


@pytest.mark.parametrize("break_it", [
    lambda p: p.art_slots.update({"旋風腿": ["feng", "huo", "shui", None]}),  # 槽沒裝滿
    lambda p: setattr(p, "arts", []),                                         # 沒有這門武學
    lambda p: setattr(p, "stamina", 5),                                       # 體力不足
    lambda p: p.art_quality.update({"旋風腿": "絕學"}),                        # 已經是絕學
    lambda p: p.art_quality.update({"旋風腿": "中品"}),                        # 不是上品：品級不靠修練
    lambda p: setattr(p, "legend_items", 0),                                  # 沒有丹
])
def test_a_refused_cultivation_writes_no_journal_entry(adept, break_it):
    break_it(adept.state.player)
    before = list(adept.state.journal)
    msgs = adept.cultivate("旋風腿", use_legend=True)
    assert len(msgs) == 1 and adept.state.journal == before
    assert any(msgs[0] in line for line in adept.state.log)  # 話還是照樣留在 log


def test_melting_the_art_waiting_for_its_name_is_refused_without_an_entry(adept):
    """練成絕學、還沒定名的那門不能熔：熔了，讀檔清理會把取名權連同已登記的第一人一起丟掉。"""
    adept.cultivate("旋風腿", use_legend=True)
    assert adept.state.player.naming == "旋風腿"
    before = list(adept.state.journal)
    msgs = adept.melt_art("旋風腿")
    assert "先替它定名" in msgs[0] and "旋風腿" in adept.state.player.arts and adept.state.journal == before
    adept.name_mastered("風神腿")
    assert "熔成了心得" in adept.melt_art("旋風腿")[0] and adept.state.player.arts == []  # 定了名就能熔


def test_a_basic_art_is_refused_without_a_journal_entry(adept):
    """基礎武學是下品：品級不靠修練（NO_RANK_LINE），不擲骰、不寫紀錄。"""
    adept.state.player.member.wugong_id = "basic_fist"
    before = list(adept.state.journal)
    assert adept.cultivate("basic_fist", use_legend=True) == [cultivation.NO_RANK_LINE] and adept.state.journal == before


def test_naming_writes_the_chronicle_the_journal_and_saves_the_season(adept):
    adept.cultivate("旋風腿", use_legend=True)
    assert adept.state.player.naming == "旋風腿"
    msgs = adept.name_mastered("風神腿")
    assert "風神腿" in msgs[0] and adept.state.journal[0].tag == msgs[0]
    assert [r.text for r in adept.world.get_season().chronicle][-1] == "沈浪把【旋風腿】練成絕學，為之定名【風神腿】。"  # 存回共用賽季了


def test_a_refused_naming_writes_no_journal_entry(adept):
    before = list(adept.state.journal)
    assert adept.name_mastered("風神腿") == ["（沒有等著你取名的武學。）"]  # 沒有等著取名的武學
    adept.state.player.naming = "旋風腿"
    assert "長度" in adept.name_mastered("風")[0]                              # 名字不合格
    adept.world.claim_skill_name(generate_from_name("裂石拳", "武學", "裂石拳"))
    assert "有人用了" in adept.name_mastered("裂石拳")[0]                       # 名字被用掉了
    assert adept.state.journal == before and adept.state.player.naming == "旋風腿"


def test_cultivating_and_naming_wait_while_the_season_is_preparing(adept):
    from unittest import mock

    with mock.patch.object(adept.world, "season_phase", return_value="preparing"):
        assert "籌備中" in adept.cultivate("旋風腿", use_legend=True)[0] and "籌備中" in adept.name_mastered("風神腿")[0]
    assert adept.state.player.stamina == 150 and adept.state.player.art_quality == {"旋風腿": "上品"} and adept.state.player.legend_items == 1


def test_the_practice_row_only_offers_the_pill_on_the_last_step(adept):
    """修練頁那一列：到了極處才按得下去、寫衝開的機會與丹的數目；沒到的灰掉、寫原因。"""
    row = next(r for r in skillview.art_rows(adept.state, adept.content, adept.world) if r["id"] == "旋風腿")
    assert row["cultivate"]["ok"] and row["cultivate"]["legend"]["bonus"] == 15 and row["cultivate"]["legend"]["count"] == 1
    assert row["cultivate"]["xinde"] is None  # 武學重構：沒有以心得修練了
    adept.state.player.art_levels["旋風腿"] = 9
    row = next(r for r in skillview.art_rows(adept.state, adept.content, adept.world) if r["id"] == "旋風腿")
    assert not row["cultivate"]["ok"] and row["cultivate"]["legend"] is None and "槽 4／4" in row["cultivate"]["note"]
    adept.state.player.art_levels["旋風腿"] = 10
    adept.state.player.art_quality["旋風腿"] = "中品"
    row = next(r for r in skillview.art_rows(adept.state, adept.content, adept.world) if r["id"] == "旋風腿")
    assert not row["cultivate"]["ok"] and row["cultivate"]["note"] == cultivation.NO_RANK_LINE


# ── FB-069：絕學的正式名字不能取成江湖上任何一個角色的名號 ──────────────────


def _save_character(content, name, bot=False):
    from tianxia.characters import open_characters
    from tianxia.state import BotProfile

    state = new_game_state(content, name)
    if bot:
        state.player.bot = BotProfile(personality="普通", seed=1)
    open_characters().save(state)


def test_fb069_a_mastered_art_cannot_take_a_players_or_a_bots_name(kicker, content, world):
    """QA 驗收時把絕學定名成另一個玩家的名號「驗收新武」也被接受了。現在真人、假人的名號都擋（不分大小寫），
    回的是同一句話，看不出那是不是假人；普通的名字照常定名。"""
    kicker.player.naming = "旋風腿"
    world.claim_master("旋風腿", kicker.player.name)
    _save_character(content, "驗收新武")
    _save_character(content, "雲中客", bot=True)
    _save_character(content, "Lan", bot=True)
    refusal = ["這個名字不行：跟江湖上的人物同名。"]
    assert cultivation.name_mastered(kicker, content, world, "驗收新武") == refusal  # 真人
    assert cultivation.name_mastered(kicker, content, world, "雲中客") == refusal  # 假人：同一句話
    assert cultivation.name_mastered(kicker, content, world, "lAN") == refusal  # 假人的名號換了大小寫
    assert kicker.player.naming == "旋風腿" and world.get_skill("旋風腿").name == "旋風腿"  # 什麼都沒動
    assert cultivation.name_mastered(kicker, content, world, "風神腿") == ["從今以後，江湖上這門武學就叫【風神腿】。"]
    assert world.get_skill("旋風腿").name == "風神腿"


def test_fb069_the_world_store_knows_every_characters_name_ignoring_case(content, world):
    _save_character(content, "驗收新武")
    _save_character(content, "Lan", bot=True)
    assert world.is_character_name("驗收新武") and world.is_character_name(" LAN ") and world.is_character_name("lan")
    assert not world.is_character_name("風神腿")


def test_fb069_a_forge_never_registers_a_characters_name(ready_forge, content, world):
    """開爐也一樣（武學重構：合成只剩武學＋武學）：鎖外取到的名字（C 段重驗）、鎖內叫模型取到的名字，撞上角色的名號都不用，改走退路字表。"""
    from unittest import mock

    from tianxia import naming

    _save_character(content, "驗收新武")
    art, _ = fusion.blend(ready_forge, content, world, None, "basic_fist", "basic_breath", proposed=("驗收新武", "一句話。"))
    assert art is not None and art.name != "驗收新武"
    client = mock.Mock()
    client.chat_structured.side_effect = [naming.NameReply(name="驗收新武"), naming.NameReply(name="裂江訣")]
    art, _ = fusion.blend(ready_forge, content, world, client, "basic_fist", "lake_kick")
    assert art is not None and art.name == "裂江訣"  # 第一個名字是角色的名號：再請模型取一次


@pytest.fixture
def ready_forge(state):
    """身上粗淺拳腳與粗淺吐納、庫裡湖邊腿法，心得體力都夠合兩爐。"""
    state.player.member.wugong_id, state.player.member.neigong_id = "basic_fist", "basic_breath"
    state.player.arts = ["lake_kick"]
    state.player.stats["xinde"], state.player.stamina = 100, 150
    return state
