"""功效的說明要白話、戰報裡功效發動那一句要寫出這一場改了多少（arts-polish-2：FB-084）。

說明：正式內容（content/traits.json）每一個功效的說明不能再用規則的行話（門檻、下限、起伏……），而且每句話都要跟程式真的做的事對得上。
數字：功效的演出句後面接一段括號，寫這一場真的少扣、多拿、回了多少；數字跟戰報上的「氣血 -N」「心得 +N」是同一批算的，
不是另寫一份。本命戰法第三批起，除了化勁（少扣氣血）與厚，功效都換成回合裡的戰法，一般的仗不再寫它們。"""
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


def test_every_general_trait_shows_its_number(real):
    """{value} 是功法卡上「這一門自己的」數字（照層數與品質算）：下品與絕學並排時看得出差別，所以八個一般功效的說明都要留著。"""
    for t in real.traits.general:
        assert "{value}" in t.desc, (t.name, t.desc)


def test_the_descriptions_say_what_the_rules_do(real):
    """本命戰法第三批：功效換成回合裡的戰法（tianxia/tactics.py），每個一句白話，逐個對著那一招的規則寫。"""
    by_name = {t.name: t.desc for t in [*real.traits.general, *real.traits.special]}
    assert by_name == {
        "先手": "剋中對手後有 {value} 的機會連環（這一回合再推一次）",
        "穩": "運氣的好壞幅度小 {value}，勝負更看實力；有 {extra} 的機會不受定身、失神",
        "破甲": "強攻剋中對手時，有 {value} 的機會讓他下一回合的固守與借力落空",
        "化勁": "挨打掉的氣血少 {value}；挨強攻時有 {extra} 的機會借力，把那一下的一半還回去",
        "乘勝": "每贏一回合推力 +{value}，一場內疊加（最多 +30%），輸一回合減半",
        "吸取": "剋中對手時回氣血 {value}",
        "險": "每回合有 {value} 的機會起霧：雙方都可能打空，身法高的那一方少打空",
        "厚": "氣血掉得越多，推力打折得越少：最多多保住 {value} 的推力（滿血時沒差）",
        "連環": "每回合有 20% 的機會連環（這一回合再推一次）",
        "不動": "不受定身、卸勁",
        "護命": "一場一次：氣血要見底時留一成，那一回合化影",
        "悟招": "每被對手剋中一次就看破一分，之後推力每次 +10%（最多 3 次）",
        "借力": "挨強攻時有 30% 的機會借力，把那一下的一半還回去",
        "回春": "每回合開始回氣血 3%",
        "輕身": "前 2 回合有 15% 的機會化影（那一回合不掉氣血）",
    }


def test_the_card_line_reads_in_plain_words(real):
    art = generate_from_name("試招拳", "武學", "試招拳", attribute="快", weights={"下品": 100.0, "中品": 0.0, "上品": 0.0, "絕學": 0.0}).model_copy(
        update={"origin": "fused", "traits": ["快", "柔", "實"], "special": "huming"},
    )
    line = traits.card_line(real, art)
    assert line == (
        "功效：〔先手〕剋中對手後有 10% 的機會連環（這一回合再推一次）"
        "・〔化勁〕挨打掉的氣血少 10%；挨強攻時有 5% 的機會借力，把那一下的一半還回去"
        "・〔厚〕氣血掉得越多，推力打折得越少：最多多保住 5% 的推力（滿血時沒差）"
        "・〔護命〕一場一次：氣血要見底時留一成，那一回合化影"
    )


# ── 戰報裡：發動那一句後面寫這一場改了多少 ───────────────────────


def _wear(game, name, attribute, trait_list, special=None, kind="武學", quality="下品"):
    """穿上一門登記的武學。武學重構：功效照槽裡的意境（arts.apply），所以照 trait_list（同一屬性幾個＝強度幾）與 special
    造自己悟的意境裝進槽，不再寫在武學上。"""
    from tianxia.martial_arts import Insight

    art = generate_from_name(name, kind, name, attribute=attribute).model_copy(update={"origin": "fused", "affinity": [attribute]})
    game.world.claim_skill_name(art)
    slot = "neigong_id" if art.kind == "內功" else "wugong_id"
    setattr(game.state.player.member, slot, art.id)
    p = game.state.player
    p.art_quality[art.id] = quality
    wanted = [(a, None, min(3, trait_list.count(a))) for a in dict.fromkeys(trait_list)]
    if special:
        wanted.append((attribute, special, 1))
    slots = []
    for a, sp, strength in wanted:
        ins = Insight(id=f"悟:{len(p.own_insights) + 1}", name=f"悟{a}", attribute=a, secret_special=sp)
        p.own_insights[ins.id] = ins
        p.insights.append(ins.id)
        if strength > 1:
            p.insight_strength[ins.id] = strength
        slots.append(ins.id)
    p.art_slots[art.id] = slots
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


def test_soft_does_not_claim_the_injury_that_still_would_not_have_been_saved(game):
    """化勁只減氣血（內傷跟著那個量按比例變少，但不是它的數字）：它的括號只寫氣血，不寫內傷。"""
    _wear(game, "護體拳", "柔", ["柔"])
    record = _fought(game, "落敗")
    assert "內傷" not in _line(record, "化勁")


def test_the_number_notes_do_not_break_the_trait_lead_the_page_looks_for(game):
    _wear(game, "護體拳", "柔", ["柔", "柔", "柔"])
    record = _fought(game, "落敗")
    assert all(x.startswith(battlelog.TRAIT_LEAD) for x in record.trait_before + record.trait_after)


def test_toll_saved_is_read_only_and_zero_without_the_traits(game):
    p = game.state.player
    before = (p.member.neili, p.member.injury)
    assert team.toll_saved(game.state, game.content, game.world, "落敗") == (0, 0)  # 沒有化勁
    _wear(game, "護體拳", "柔", ["柔", "柔", "柔"], special="budong")
    saved, spared = team.toll_saved(game.state, game.content, game.world, "落敗")
    assert saved > 0 and spared == 0  # 不動換成回合裡的戰法（本命戰法第三批），不再免內傷
    assert (p.member.neili, p.member.injury) == before  # 只量、不動狀態
    assert team.toll_saved(game.state, game.content, game.world, "莫名其妙") == (0, 0)
    assert re.fullmatch(r"\d+", str(saved))
