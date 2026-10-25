"""FB-640（release/1021：develop 的 FB-364 給九位歷史武將同行補了起始武學，main 的 d0ca2c25 給學來的 23 門下品武學各帶一個小戰法；
兩邊各自都過，合起來正式內容載不起來，content.check_signature_arts 把人物的 starting_* 一律當本命）。PM 裁決：兩邊都留，
本命＝人物起始武學裡的絕學（寫本命戰法的那一門，tactics.figure_arts）；同伴起始帶的學來的下品武學照樣帶小戰法、不是本命：
誰的都不算（tactics.figure_of）、情誼到了不教、名帖不寫親傳、玩家照樣在各地學得到也熔得掉；十八位大勢人物的本命一個字不變。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content
from test_content import copy_fixture, edit_json

from tianxia import arts, library, mingtie, roster, signature, skillview, tactics, team
from tianxia.content import ContentError, load_content
from tianxia.engine import Game

pytestmark = pytest.mark.slow

NEW_NINE = ("wangyun", "gongsunzan", "tangzhou", "xuchu", "zhangyan", "xushao", "xunyu", "huatuo", "zhangrang")
MINOR = {"tactic": {"name": "湖畔試腿", "timing": "起手", "kind": "vanguard", "rate": 0.5, "rounds": 1,
                    "desc": "搶先一腿：這一回合連環，推兩次。", "minor": True}}


@pytest.mark.parametrize("profile", [None, "season21", "week7"])
def test_real_content_loads_with_both_sides_kept(profile):
    """正式內容在不帶設定（14 天）、週末、21 天、7 天都載得起來，而且合併的兩邊都在：九位同伴有起始武學，其中下品的帶小戰法。"""
    c = real_content(profile)
    starts = {s for cid in NEW_NINE for s in (c.characters[cid].starting_wugong, c.characters[cid].starting_neigong)}
    assert None not in starts
    minors = {s for s in starts if c.skills[s].tactic is not None and c.skills[s].tactic.minor}
    assert len(minors) == 13 and "jichu_tuna" in minors and "ganshan_tui" in minors


def test_old_figures_keep_their_signature_new_companions_have_none():
    """劉備的本命照舊是那兩門絕學；華佗起始的趕山腿、基礎吐納不是誰的本命。十八位、三十六門一門不少。"""
    c = real_content()
    assert tactics.figure_arts(c, c.characters["liubei"]) == ["liubei_wugong", "liubei_neigong"]
    for sid in ("liubei_wugong", "liubei_neigong"):
        assert tactics.figure_of(c, sid) == "liubei" and signature.is_signature(c, sid)
    owners = {cid: tactics.figure_arts(c, ch) for cid, ch in c.characters.items() if tactics.figure_arts(c, ch)}
    assert len(owners) == 18 and sum(len(v) for v in owners.values()) == 36
    assert all(c.skills[s].tactic is not None and not c.skills[s].tactic.minor for v in owners.values() for s in v)
    for cid in NEW_NINE:
        ch = c.characters[cid]
        assert tactics.figure_arts(c, ch) == []
        for sid in (ch.starting_wugong, ch.starting_neigong):
            assert tactics.figure_of(c, sid) is None and not signature.is_signature(c, sid)
            tactic = c.skills[sid].tactic
            assert tactic is None or tactic.minor  # 下品的帶小戰法，上品的（行伍槍法、力士錘法、部曲刀法）什麼都不帶
            if c.skills[sid].quality == "下品":
                assert not arts.fixed(c, sid)  # 槽照開（同 main 對學來的武學）


def test_the_player_still_learns_and_melts_a_companions_starting_art():
    """main 上跟各地師父學的那條路不被「本命要情誼到了才學得到」擋：燕山腳下照樣教趕山腿（華佗起始的那一門），學得到、熔得掉。"""
    c = real_content()
    game = Game.new(c, "測試俠客", rng=random.Random(0))
    p = game.state.player
    p.location = "yanshan_foot"
    p.stats["silver"] = 100
    p.member.wugong_id, p.member.wugong_level = "jichu_quanjiao", 1  # 身上有武學：學到的進功法庫
    lessons = {s.id: problem for s, problem in library.lessons_here(game.state, c)}
    assert "ganshan_tui" in lessons and lessons["ganshan_tui"] is None
    library.learn(game.state, c, "ganshan_tui")
    assert "ganshan_tui" in p.arts and p.art_levels.get("ganshan_tui", 1) == 1  # 不從第七成起
    assert library.melt_problem(game.state, "ganshan_tui", content=c) is None


def test_the_name_card_only_counts_real_signatures():
    """名帖的「某某親傳」只認本命：人人開局都有的基礎吐納不寫「華佗親傳」、學了書生劍不寫「荀彧親傳」，學到劉備的本命照寫。"""
    c = real_content()
    game = Game.new(c, "測試俠客", rng=random.Random(0))
    p = game.state.player
    p.member.neigong_id = "jichu_tuna"
    p.arts += ["shusheng_jian", "ganshan_tui"]
    titles = mingtie.earned(game.state, c, game.world)
    assert not [t for t in titles if t.endswith("親傳")]
    p.arts.append("liubei_wugong")
    assert "劉備親傳" in mingtie.earned(game.state, c, game.world)


def test_old_save_flags_for_the_new_nine_lift_nothing():
    """FB-364 之前情誼到了的舊角色可能留著「學會本命:huatuo」：讀檔補第七成只認本命，基礎吐納不被拉到第七成。"""
    c = real_content()
    game = Game.new(c, "測試俠客", rng=random.Random(0))
    p = game.state.player
    p.flags |= {"學會本命:huatuo", "學會本命:liubei"}
    assert set(signature.learned(game.state, c)) == {"liubei_wugong", "liubei_neigong"}
    p.member.neigong_id, p.member.neigong_level = "jichu_tuna", 1
    loaded = Game(c, game.state, random.Random(0), game.world)
    assert loaded.state.player.member.neigong_level == 1


def test_companion_card_and_fight_use_the_minor_tactic(world):
    """華佗招到之後身上是趕山腿、基礎吐納：卡上蓋「看家」印、不蓋「本命」，有戰力（FB-364），打仗時照小戰法發動、不算誰的本命
    （沒有連動、底蘊）；關羽的本命照舊認得是他的。"""
    c = real_content()
    game = Game.new(c, "測試俠客", rng=random.Random(0), world=world)
    roster._seed_starting_skills(world, "huatuo", c.characters["huatuo"])
    card = skillview.member_card(game.state, c, world, "huatuo")
    # main 632cc5e5：卡上不寫「小戰法」，學來的武學招名前蓋「看家」印、本命蓋「本命」印（tactics.title_of）
    assert "看家〔搶山一腿〕" in card and "看家〔吐故納新〕" in card and "本命〔" not in card
    assert team.mate_power(game.state, c, world, "huatuo") > 0
    held = tactics.holders_of(c, [("華佗", "huatuo", "ganshan_tui", "jichu_tuna")])
    assert [h.tactic.name for h in held] == ["搶山一腿", "吐故納新"]
    assert all(h.figure is None and h.tactic.minor and not h.tactic.might for h in held)
    guan = tactics.holders_of(c, [("關羽", "guanyu", "guanyu_wugong", "guanyu_neigong")])
    assert {h.figure for h in guan} == {"guanyu"}


def test_a_minor_on_a_companions_learned_starting_art_loads(tmp_path):
    """測試內容裡重現合併的那一下：一門學得到的下品武學帶小戰法、又是一位同伴的起始武學——載得起來，誰的本命都不是。"""
    root = copy_fixture(tmp_path)

    def put_minor(skills):
        next(s for s in skills if s["id"] == "lake_kick").update(MINOR)

    def give_pupil(characters):
        next(ch for ch in characters if ch["id"] == "pupil")["starting_wugong"] = "lake_kick"

    edit_json(root / "skills.json", put_minor)
    edit_json(root / "characters.json", give_pupil)
    c = load_content(root)
    assert c.skills["lake_kick"].tactic.minor and tactics.figure_of(c, "lake_kick") is None
    assert tactics.figure_arts(c, c.characters["pupil"]) == []


def test_a_minor_on_a_figures_signature_is_still_rejected(tmp_path):
    """本命（人物起始武學裡的絕學）寫小戰法照舊擋（main 原本的那一條）。"""
    root = copy_fixture(tmp_path)

    def put_minor(skills):
        next(s for s in skills if s["id"] == "palm").update(MINOR)  # 韓鐵的起始武學，品質沒寫＝絕學

    edit_json(root / "skills.json", put_minor)
    with pytest.raises(ContentError, match="人物的本命武學寫的是本命戰法，不是小戰法"):
        load_content(root)
