"""功效的說明要白話、戰報裡功效發動那一句要寫出這一場改了多少（arts-polish-2：FB-084）。

說明：正式內容（content/traits.json）每一個功效的說明不能再用規則的行話（門檻、下限、起伏……），而且每句話都要跟程式真的做的事對得上。
數字：功效的演出句後面接一段括號，寫這一場真的少扣、多拿、回了多少；數字跟戰報上的「氣血 -N」「心得 +N」是同一批算的，
不是另寫一份。改到贏的機會的功效（先手、穩、破甲、險、連環、借力、厚）沒有「這一場多了多少」的數字——機率沒有一個單一的量——
所以只有說明、句子照舊。"""
from __future__ import annotations

import re
from pathlib import Path
from unittest import mock

import pytest

from conftest import walk_to
from tianxia import battlelog, encounter, team, traits
from tianxia.content import load_content
from tianxia.martial_arts import generate_from_name

ROOT = Path(__file__).parent.parent

# 規則自己的說法：玩家不該在功效說明裡讀到它們（FB-084 列的「門檻」「下限」「起伏」，加上同一類）
JARGON = ("門檻", "下限", "起伏", "掛點", "判定", "擲", "當作", "層")


@pytest.fixture(scope="module")
def real():
    return load_content(ROOT / "content")


def test_no_trait_description_uses_the_rules_own_words(real):
    for t in [*real.traits.general, *real.traits.special]:
        for word in JARGON:
            assert word not in t.desc, (t.name, t.desc)


def test_every_trait_that_has_a_number_still_shows_it(real):
    """{value} 是功法卡上「這一門自己的」數字（照層數與品質算）：下品與絕學並排時看得出差別，所以說明裡要留著。
    只有沒有數字的三個特別功效（連環、不動、護命）不寫。"""
    no_number = {"double_luck", "no_injury", "no_loss"}
    for t in [*real.traits.general, *real.traits.special]:
        assert ("{value}" in t.desc) is (t.hook not in no_number), (t.name, t.desc)


def test_the_descriptions_say_what_the_rules_do(real):
    """每個功效一句白話；逐個對著程式的規則寫（encounter.resolve_encounter、team.take_encounter_toll、engine._battle_rewards……）。"""
    by_name = {t.name: t.desc for t in [*real.traits.general, *real.traits.special]}
    assert by_name == {
        "先手": "比較容易打出大勝（大勝要贏的幅度少對手強度的 {value}），回合裡一定先出手",
        "穩": "戰場上運氣的好壞幅度縮小 {value}，勝負更看實力",
        "破甲": "對手的強度等於低了 {value}，更容易贏",
        "化勁": "每場打完損失的氣血減少 {value}",
        "乘勝": "打贏時，得到的心得和經驗都多 {value}",
        "吸取": "打贏之後，回復氣血上限的 {value}",
        "險": "戰場上運氣的好壞幅度放大 {value}：有機會以弱勝強，也可能陰溝裡翻船",
        "厚": "受傷時威力掉得少：氣血越低，比平常多保住最多 {value} 的威力（滿血時沒差）",
        "連環": "每場打鬥碰兩次運氣，取比較好的那一次",
        "不動": "打完損失的氣血都只是輕傷，不會變成內傷",
        "護命": "落敗時改判成平手（僵持）；劇情裡安排好輸贏的戰鬥不算",
        "悟招": "打贏多得 {value} 點心得",
        "借力": "對手越強，你的威力越高：威力加上對手強度的 {value}",
        "回春": "不論輸贏，打完都回復氣血上限的 {value}",
        "輕身": "遊歷少花 {value} 點體力",
    }


def test_the_card_line_reads_in_plain_words(real):
    art = generate_from_name("試招拳", "武學", "試招拳", attribute="快", weights={"下品": 100.0, "中品": 0.0, "上品": 0.0, "絕學": 0.0}).model_copy(
        update={"origin": "fused", "traits": ["快", "柔", "實"], "special": "huming"},
    )
    line = traits.card_line(real, art)
    assert line == (
        "功效：〔先手〕比較容易打出大勝（大勝要贏的幅度少對手強度的 4%），回合裡一定先出手"
        "・〔化勁〕每場打完損失的氣血減少 10%"
        "・〔厚〕受傷時威力掉得少：氣血越低，比平常多保住最多 5% 的威力（滿血時沒差）"
        "・〔護命〕落敗時改判成平手（僵持）；劇情裡安排好輸贏的戰鬥不算"
    )


# ── 戰報裡：發動那一句後面寫這一場改了多少 ───────────────────────


def _wear(game, name, attribute, trait_list, special=None, kind="武學", quality="下品"):
    art = generate_from_name(name, kind, name, attribute=attribute).model_copy(
        update={"origin": "fused", "traits": trait_list, "special": special},
    )
    game.world.claim_skill_name(art)
    slot = "neigong_id" if art.kind == "內功" else "wugong_id"
    setattr(game.state.player.member, slot, art.id)
    game.state.player.art_quality[art.id] = quality
    return art


def _fought(game, tier):
    """在湖邊打一場、結果寫死，回傳那一場的戰報（跟 test_engine._fought 一樣的做法）。"""
    if game.state.player.location != "lake":
        walk_to(game, "lake")
    result = encounter.EncounterResult(tier=tier, margin=0, our_power=10, difficulty=5)
    with mock.patch.object(team, "fight", return_value=result):
        game.choose("act:train")
    return game.state.battles[0]


def _line(record, name):
    (line,) = [x for x in record.trait_before + record.trait_after if x.startswith(f"〔{name}〕")]
    return line


def _plain_toll(game, tier):
    """同一個人、同一份氣血，不帶任何功效打同一個結果：氣血、內傷各扣多少（沒有這個數的就是 0）。"""
    plain = game.state.model_copy(deep=True)
    plain.player.member.wugong_id = plain.player.member.neigong_id = None
    msgs = team.take_encounter_toll(plain, game.content, game.world, tier)
    pick = lambda lead: next((int(m.removeprefix(lead)) for m in msgs if m.startswith(lead)), 0)  # noqa: E731
    return pick("氣血 -"), pick("內傷 +")


def _shown(record, lead):
    return next((int(c.removeprefix(lead)) for c in record.changes if c.startswith(lead)), 0)


def test_soft_says_how_much_blood_it_saved_and_it_is_the_difference_the_toll_really_shows(game):
    _wear(game, "護體拳", "柔", ["柔", "柔", "柔"])  # 化勁 30%
    walk_to(game, "lake")
    bare_lost, _ = _plain_toll(game, "落敗")
    record = _fought(game, "落敗")
    saved = bare_lost - _shown(record, "氣血 -")
    assert saved > 0
    assert _line(record, "化勁").endswith(f"（少扣了 {saved} 點氣血）")


def test_still_says_how_much_inner_injury_it_spared(game):
    _wear(game, "護體拳", "剛", ["剛"], special="budong")
    walk_to(game, "lake")
    _, bare_hurt = _plain_toll(game, "落敗")
    record = _fought(game, "落敗")
    assert bare_hurt > 0 and not any(c.startswith("內傷 +") for c in record.changes)
    assert _line(record, "不動").endswith(f"（免了 {bare_hurt} 點內傷）")


def test_soft_does_not_claim_the_injury_that_still_would_not_have_been_saved(game):
    """化勁只減氣血（內傷跟著那個量按比例變少，但不是它的數字）：它的括號只寫氣血，不寫內傷。"""
    _wear(game, "護體拳", "柔", ["柔"])
    record = _fought(game, "落敗")
    assert "內傷" not in _line(record, "化勁")


def test_absorb_and_spring_say_how_much_blood_they_gave_back(game):
    _wear(game, "吸取掌", "陰", ["陰"], special="huichun")
    record = _fought(game, "大勝")  # 大勝扣 16：吸取回 2%＝6、回春 3%＝10
    gains = [int(c.removeprefix("氣血 +")) for c in record.changes if c.startswith("氣血 +")]
    assert len(gains) == 2
    assert _line(record, "吸取").endswith(f"（回了 {gains[0]} 點氣血）")
    assert _line(record, "回春").endswith(f"（回了 {gains[1]} 點氣血）")


def test_momentum_says_the_extra_xinde_and_exp_it_really_paid(game):
    _wear(game, "得勝拳", "陽", ["陽"])  # 乘勝 10%
    game.content.squads["thug"] = game.content.squads["thug"].model_copy(update={"reward_xinde": 10, "exp": 20})
    record = _fought(game, "大勝")
    assert (record.xinde, record.exp) == (11, 22)
    assert _line(record, "乘勝").endswith("（多得 1 點心得、2 點經驗）")


def test_momentum_names_only_what_was_really_extra(game):
    _wear(game, "得勝拳", "陽", ["陽"])
    game.content.squads["thug"] = game.content.squads["thug"].model_copy(update={"reward_xinde": 3, "exp": 20})
    record = _fought(game, "大勝")  # 3 × 1.1 ＝ 3.3，四捨五入還是 3：心得沒有多，只寫經驗
    assert record.xinde == 3 and _line(record, "乘勝").endswith("（多得 2 點經驗）")


def test_insight_special_says_its_points(game):
    _wear(game, "悟道拳", "剛", ["剛"], special="wuzhao")
    assert _line(_fought(game, "險勝"), "悟招").endswith("（多得 5 點心得）")


def test_light_body_says_the_stamina_it_saved_on_a_journey(game):
    _wear(game, "輕身腿", "快", ["快"], special="qingshen")
    record = _fought(game, "大勝")
    assert _line(record, "輕身").endswith("（少花了 2 點體力）")


def test_the_traits_that_move_the_odds_stay_a_plain_sentence(game):
    """先手、穩、破甲、險、連環、借力、厚改的是贏的機會，沒有「這一場多了多少」：句子照舊，後面不接括號。"""
    for attribute, special, name in (
        ("快", None, "先手"), ("慢", None, "穩"), ("剛", None, "破甲"), ("虛", None, "險"), ("實", "lianhuan", "連環"), ("實", "jieli", "借力"),
    ):
        game.state.battles.clear()
        _wear(game, f"試招{name}", attribute, [attribute], special=special)
        line = _line(_fought(game, "大勝"), name)
        assert not re.search(r"（(少扣|免了|回了|多得|少花)", line), line


def test_the_number_notes_do_not_break_the_trait_lead_the_page_looks_for(game):
    _wear(game, "護體拳", "柔", ["柔", "柔", "柔"])
    record = _fought(game, "落敗")
    assert all(x.startswith(battlelog.TRAIT_LEAD) for x in record.trait_before + record.trait_after)


def test_toll_saved_is_read_only_and_zero_without_the_traits(game):
    p = game.state.player
    before = (p.member.neili, p.member.injury)
    assert team.toll_saved(game.state, game.content, game.world, "落敗") == (0, 0)  # 沒有化勁、不動
    _wear(game, "護體拳", "柔", ["柔", "柔", "柔"], special="budong")
    saved, spared = team.toll_saved(game.state, game.content, game.world, "落敗")
    assert saved > 0 and spared > 0
    assert (p.member.neili, p.member.injury) == before  # 只量、不動狀態
    assert team.toll_saved(game.state, game.content, game.world, "莫名其妙") == (0, 0)
    assert re.fullmatch(r"\d+", str(saved))
