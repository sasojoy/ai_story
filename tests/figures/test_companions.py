"""歷史武將同行（docs/superpowers/specs/2026-10-18-歷史武將同行-design.md）：十五位不是大勢人物的歷史武將照陣營招進名下、
全服唯一、一人三位、情誼放慢、放走、叛投帶不走。決戰裡的同伴在 tests/test_companions_battle.py。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from conftest import real_content
from tianxia import roster
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.state import MAX_TEAM_COMPANIONS

FIFTEEN = {
    "caocao", "liubei", "guanyu", "zhangfei", "yuanshao", "taoqian", "wangyun", "gongsunzan",
    "xuchu", "tangzhou", "zhangyan", "xushao", "xunyu", "huatuo", "zhangrang",
}


@pytest.fixture
def real():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


def _player(content, store, name, faction, at, warm=False) -> Game:
    """warm：十五位的情誼都先補到招募門檻（Config.recruit_min_affinity，Joy 2026-10-21；沒到的不畫招募鈕，見 test_recruit_gate.py）。"""
    game = Game.new(content, name, rng=random.Random(0), world=store)
    p = game.state.player
    if warm:
        p.affinities.update({cid: content.config.recruit_min_affinity for cid in FIFTEEN})
    p.faction, p.location = faction, at
    p.tutorial_step = len(content.tutorial.steps)
    p.visited.add(at)
    p.joined_at = -1e9
    p.stamina = 250
    p.stats["silver"] = 100
    game.now = 1000.0
    game._save_season()
    CharacterStore(store.db).save(game.state)
    return game


def _opts(game):
    return {o.id: o for o in game.options()}


# ── Task 1：開關、可招的人、照陣營招、名下三位 ──


def test_fifteen_are_recruitable_and_no_figure_is():
    c = real_content()
    assert c.config.companions.enabled
    recruitable = {cid for cid, ch in c.characters.items() if ch.recruitable}
    assert recruitable == FIFTEEN
    assert not recruitable & {f.character for f in c.figures.values() if f.character}
    assert c.characters["zhangyan"].side == "huang"  # 9.2：黑山軍出自黃巾


def test_the_recruit_button_follows_the_side(real, world):
    guan = _player(real, world, "官甲", "guan", "zhuo_county", warm=True)
    button = _opts(guan)["act:recruit:liubei"]
    assert button.enabled and "成功率約" in button.label
    huang = _player(real, world, "黃甲", "huang", "zhuo_county", warm=True)
    button = _opts(huang)["act:recruit:liubei"]
    assert not button.enabled and roster.SIDE_ONLY.format(side="官軍") in button.label
    drifter = _player(real, world, "散甲", None, "yingchuan_academy", warm=True)
    assert _opts(drifter)["act:recruit:xunyu"].enabled  # 沒寫 side 的誰都招得到（含散人）


@pytest.mark.smoke
def test_a_recruit_lands_him_in_your_name_and_team(real, world):
    guan = _player(real, world, "官甲", "guan", "zhuo_county", warm=True)
    guan.rng = mock.Mock(random=mock.Mock(return_value=0.0))
    guan.choose("act:recruit:guanyu")
    assert world.get_companion("guanyu").owner == "官甲"
    assert "guanyu" in guan.state.player.team
    assert "act:recruit:guanyu" not in _opts(guan)  # 有主了：鈕不再出現


# ── FB-364：十五位裡以前不能招的九位補起始武學、內功 ──

NEW_NINE = {"wangyun", "gongsunzan", "tangzhou", "xuchu", "zhangyan", "xushao", "xunyu", "huatuo", "zhangrang"}


def test_every_recruitable_companion_has_arts_and_power(real, world):
    """十五位都有一門武學、一門內功；新補的九位挑現有內容的武學（不新造名字）、不帶本命戰法、不是絕學；招到之後威力不是 0。
    main 的 d0ca2c25（Joy 2026-10-21）給學來的下品武學各帶一個小戰法，九位起始的下品武學也帶：不是本命戰法（FB-640，
    原本斷言 tactic 是 None；本命與小戰法的分法在 tests/test_signature_arts.py）。"""
    from tianxia import team

    for cid in FIFTEEN:
        ch = real.characters[cid]
        assert real.skills[ch.starting_wugong].kind == "武學" and real.skills[ch.starting_neigong].kind == "內功"
    for cid in NEW_NINE:
        ch = real.characters[cid]
        for sid in (ch.starting_wugong, ch.starting_neigong):
            tactic = real.skills[sid].tactic
            assert (tactic is None or tactic.minor) and real.skills[sid].quality != "絕學"
    game = _player(real, world, "官甲", "guan", "zhuo_county")
    for cid in NEW_NINE:
        roster._seed_starting_skills(world, cid, real.characters[cid])
        assert team.mate_power(game.state, real, world, cid) > 0


def test_the_new_nine_teach_no_signature_art(real, world):
    """情誼到 signature_affinity 時教的是「本命武學」：只有絕學的起始武學才算（十八位大勢人物的都是），新補的九位不教。"""
    from tianxia import companion_agent

    game = _player(real, world, "官甲", "guan", "zhuo_county")
    p = game.state.player
    p.affinities["wangyun"] = p.affinities["liubei"] = real.config.signature_affinity
    arts = set(p.arts)
    assert companion_agent._maybe_grant_signature_skill(game.state, real, real.characters["wangyun"], "wangyun") == []
    assert set(p.arts) == arts and "學會本命:wangyun" not in p.flags
    assert companion_agent._maybe_grant_signature_skill(game.state, real, real.characters["liubei"], "liubei")  # 本命照教
    assert {"liubei_wugong", "liubei_neigong"} <= set(p.arts)


def test_a_late_recruit_click_says_who_took_him(real, world):
    """FB-363：兩個分頁搶，慢的那一頁的鈕還在、按下去時他已經有主了：回「已經被某某招攬走了」（Refused，網頁跳提示；同 FB-162），
    不扣體力、不寫紀錄。名號照寫（匿名只在地方傳聞，rules.display_name）。"""
    from tianxia import engine

    first = _player(real, world, "韓甲", "guan", "zhuo_county", warm=True)
    late = _player(real, world, "趙戊", "guan", "zhuo_county", warm=True)
    assert "act:recruit:liubei" in _opts(late)
    assert world.try_recruit("liubei", "韓甲", cap=3)
    stamina, entries = late.state.player.stamina, len(late.state.journal)
    msgs = late.choose("act:recruit:liubei")
    assert isinstance(msgs, engine.Refused) and msgs == [roster.TAKEN.format(name="劉備", owner="韓甲")]
    assert late.state.player.stamina == stamina and len(late.state.journal) == entries
    assert first.choose("act:recruit:caocao")  # 自己名下的、或還沒有主的：照舊
    assert not isinstance(late.choose("act:recruit:nobody"), engine.Refused)  # 不認得的 id 照舊「此刻無法這麼做」


def test_a_fourth_companion_is_refused(real, world):
    guan = _player(real, world, "Ray", "guan", "zhuo_county", warm=True)
    for cid in ("caocao", "yuanshao", "taoqian"):
        assert world.try_recruit(cid, "Ray", cap=3)
    button = _opts(guan)["act:recruit:liubei"]
    assert not button.enabled and roster.FULL.format(n=3) in button.label
    assert not world.try_recruit("liubei", "Ray", cap=3)
    assert not world.try_recruit("liubei", "RAY", cap=3)  # 名號比對不分大小寫
    assert world.get_companion("liubei").owner is None


def test_switch_off_changes_nothing(content):
    assert not content.config.companions.enabled
    assert roster.cap(content) == MAX_TEAM_COMPANIONS
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.state.player.tutorial_step = len(content.tutorial.steps)
    ids = {o.id for o in game.options()}
    assert not any(i.startswith("act:recruit:") for i in ids)


# ── Task 2：情誼放慢 ──


def test_affinity_gains_are_scaled_and_rounded():
    from tianxia import renown

    c = real_content()
    assert c.config.affinity_gain_scale == 0.7
    assert [renown.warmed(c, d) for d in (1, 2, 5, 8, -5, 0)] == [1, 1, 4, 6, -5, 0]  # 9.4：四捨五入、至少 1、扣的不乘
    c.config.affinity_gain_scale = 1.0
    assert renown.warmed(c, 7) == 7


def test_each_gain_source_goes_through_warmed(real, world):
    from tianxia import atlas, companion_agent, figure_life, renown, rules
    from tianxia.companion_agent import CompanionTurn
    from tianxia.models import Effect

    game = _player(real, world, "官甲", "guan", "zhuo_county")
    s, p = game.state, game.state.player
    rules.apply_effect(Effect(affinity={"liubei": 5}), s, real, world)  # 事件
    assert p.affinities["liubei"] == 4
    companion_agent._apply_turn(s, real.characters["guanyu"], "guanyu", "請教", CompanionTurn(narrative="嗯。"), "坦誠相待", real)  # 對話
    assert p.affinities["guanyu"] == 7  # 關羽的坦誠相待 +10（affinity_tag_deltas）× 0.7
    p.stats["fame"] = 100_000
    renown.first_meet(s, real, "zhangfei")  # 名望起步
    assert p.affinities["zhangfei"] == renown.warmed(real, real.config.renown.fame_affinity)
    region = atlas.region_of(real, "zhuo_county").id
    figure_life.spread(s, real, "merit", "長社", at=None, side="guan", text="立了戰功", region=region)  # 風聞
    assert p.affinities["gongsunzan"] == renown.warmed(real, real.config.figure_life.side_merit)


# ── Task 3：放走與名冊 ──


def test_release_frees_him_for_anyone(real, world):
    guan = _player(real, world, "官甲", "guan", "zhuo_county")
    assert world.try_recruit("guanyu", "官甲", cap=3)
    guan.state.player.team.append("guanyu")
    msgs = guan.release_companion("guanyu")
    assert world.get_companion("guanyu").owner is None and "guanyu" not in guan.state.player.team
    assert msgs == [roster.RELEASE_DONE.format(name="關羽")]
    other = _player(real, world, "官乙", "guan", "zhuo_county", warm=True)
    assert _opts(other)["act:recruit:guanyu"].enabled


def test_release_refuses_someone_not_yours(real, world):
    guan = _player(real, world, "官甲", "guan", "zhuo_county")
    assert world.try_recruit("guanyu", "官乙", cap=3)
    assert guan.release_companion("guanyu") == [roster.RELEASE_NOT_YOURS]
    assert world.get_companion("guanyu").owner == "官乙"


def test_unowned_team_members_are_dropped_on_load(real, world):
    guan = _player(real, world, "官甲", "guan", "zhuo_county")
    assert world.try_recruit("liubei", "官甲", cap=3)
    guan.state.player.team = ["liubei", "guanyu"]  # 關羽不在他名下（例：打完決戰回江湖了）
    CharacterStore(world.db).save(guan.state)
    again = Game(real, CharacterStore(world.db).load("官甲"), random.Random(0), world)
    assert again.state.player.team == ["liubei"]


def test_the_roster_card_offers_release_through_the_server(real, world):
    import server

    guan = _player(real, world, "官甲", "guan", "zhuo_county")
    assert world.try_recruit("guanyu", "官甲", cap=3)
    view = server.menxia_view(guan, "guanyu")
    assert view["release"] == {"confirm": roster.RELEASE_CONFIRM.format(name="關羽")}
    assert server.menxia_view(guan, "player")["release"] is None
    server.MENXIA_ACTIONS["release"](guan, {"person": "guanyu"})
    assert world.get_companion("guanyu").owner is None


# ── Task 7：叛投帶不走 ──


def test_defecting_drops_companions_of_the_old_side(real, world):
    """9.5：官軍叛投黃巾，劉備（寫了官軍）當場回江湖、情誼減半，確認畫面列出他；荀彧（沒寫陣營）照舊跟著。"""
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    p = game.state.player
    for cid in ("liubei", "xunyu"):
        assert world.try_recruit(cid, "官甲", cap=3)
        p.team.append(cid)
    p.affinities["liubei"] = 61
    target = next(f for f in real.scenario.factions if f.id == "huang")
    assert p.location in target.join_at
    prompt = game.choose(f"defect:{target.id}")
    assert roster.DEFECT_LOST.format(names="劉備") in "".join(prompt)
    msgs = game.choose("defect:confirm")
    assert roster.DEFECT_LEFT.format(name="劉備", before=61, after=30) in msgs
    assert world.get_companion("liubei").owner is None and "liubei" not in p.team and p.affinities["liubei"] == 30
    assert world.get_companion("xunyu").owner == "官甲" and "xunyu" in p.team


def test_the_defect_scene_lists_companions_left_behind(real, world):
    """FB-362：按「叛投」之後玩家看的是場景那一段（Game._own_scene_text）；江湖紀錄那一則只留標題（_hide）。場景那一段也要列帶不走的同伴。"""
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    p = game.state.player
    for cid in ("liubei", "xunyu"):
        assert world.try_recruit(cid, "官甲", cap=3)
        p.team.append(cid)
    game.choose("defect:huang")
    scene = game.scene_text()
    assert roster.DEFECT_LOST.format(names="劉備") in scene
    assert "荀彧" not in scene  # 沒寫陣營的照舊跟著，不列


# ── 最終審查：劇情送人也照陣營、名下三位擋（第七節）──


def test_a_story_gift_follows_the_side_and_the_cap(real, world):
    huang = _player(real, world, "黃甲", "huang", "huangjin_camp")
    xinde = huang.state.player.stats.get("xinde", 0)
    msgs = roster.recruit(huang.state, real, world, "liubei")  # 劉備只追隨官軍
    assert world.get_companion("liubei").owner is None and huang.state.player.stats["xinde"] > xinde
    assert any(roster.SIDE_ONLY.format(side="官軍") in m for m in msgs)
    guan = _player(real, world, "官甲", "guan", "zhuo_county")
    for cid in ("caocao", "yuanshao", "taoqian"):
        assert world.try_recruit(cid, "官甲", cap=3)
    roster.recruit(guan.state, real, world, "liubei")  # 名下滿了
    assert world.get_companion("liubei").owner is None
