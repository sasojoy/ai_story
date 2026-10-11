"""懸賞榜的求藝、求兵（懸賞榜設計第四節、第九節；企劃者 2026-10-10）：官軍、黃巾、地方豪強每週各掛一張求藝、一張求兵，
不用揭、在城鎮的懸賞榜上直接交（交了就沒了），前三個交的有賞；散人三方都能交，陣營的人只交自己陣營的、拿全額。

角色開在同一個資料庫，照伺服器的做法一個動作一次讀存（test_bounties 的 _do、_direct）。"""
from __future__ import annotations

import pytest

from conftest import real_content
from test_bounties import _direct, _load, _post, beta_setup  # noqa: F401  （beta_setup 是 fixture）
from tianxia import bounties, calendar
from tianxia.content import ContentError, validate
from tianxia.models import WEAPON_KINDS
from tianxia.state import GameState, PlayerState, WorldState
from tianxia.world_state import fresh_season


def _issue(content, week=1) -> list:
    """照劇本掛第 week 週的那一批（bounties.issue；兩種季都是它），回整個榜。"""
    state = GameState(player=PlayerState(name="測", location="town", stats={}, stamina=0), world=fresh_season(content))
    state.world.time = calendar.week_start(week, content, state.world)
    bounties.issue(state, content, week)
    return state.world.bounties


def test_each_side_posts_one_art_and_one_arms_bounty_with_attributes_that_do_not_repeat():
    """設計 4.1：劇本的每個陣營（含地方豪強）每期各掛一張求藝、一張求兵；屬性從剛柔快慢挑，同一期同一種三方不重複；求兵另挑種類；
    名額 3、不掛地點，期限同其他懸賞。正式內容（兵器開著）一批 8＋6＝14 張。"""
    content = real_content()
    board = _issue(content)
    sides = [f.id for f in content.scenario.factions]
    assert len(board) == 14 and sides == ["guan", "huang", "haoqiang"]
    for kind in ("art", "arms"):
        asks = [b for b in board if b.kind == kind]
        assert [b.faction for b in asks] == sides
        assert len({b.attribute for b in asks}) == 3 and {b.attribute for b in asks} <= {"剛", "柔", "快", "慢"}
        assert all(b.quota == 3 and b.location is None for b in asks)
    assert all(b.weapon_kind in WEAPON_KINDS for b in board if b.kind == "arms")
    assert all(b.weapon_kind is None for b in board if b.kind == "art")
    assert len({b.expires for b in board}) == 1


def test_fewer_attributes_than_sides_still_posts_for_every_side():
    """give_attributes 比陣營少（只寫兩個）：三方照樣掛得出來（不丟 ValueError），先不重複、多的那一方可以重複（設計 4.1）。"""
    content = real_content()
    content.config.bounties.give_attributes = ["剛", "柔"]
    asks = [b for b in _issue(content) if b.kind == "art"]
    assert len(asks) == 3 and {asks[0].attribute, asks[1].attribute} == {"剛", "柔"} and asks[2].attribute in ("剛", "柔")


def test_no_arms_bounties_with_weapons_off():
    content = real_content()
    content.config.weapons.enabled = False
    board = _issue(content)
    assert not any(b.kind == "arms" for b in board) and sum(b.kind == "art" for b in board) == 3 and len(board) == 11


def test_the_hand_in_bounties_draw_from_their_own_dice():
    """求藝、求兵另開一份亂數（設計 4.1）：同一週的討伐、打探、護送地點跟沒有求藝、求兵時一樣。"""
    content = real_content()
    spots = [(b.kind, b.faction, b.location, b.end) for b in _issue(content) if b.kind not in bounties.GIVE_KINDS]
    content.config.bounties.give_kinds = []
    assert [(b.kind, b.faction, b.location, b.end) for b in _issue(content)] == spots


def test_titles_how_and_rewards_name_the_attribute_and_the_weapon_kind():
    """標題寫「求藝・剛」「求兵・屬柔的劍」（不是「求藝・」；種類照兵器名的字，拳腳寫拳套、弓弩寫弩）；賞那一段照 reward_text：
    陣營的人全額、不寫俠名（設計 4.2、4.7）。"""
    content = real_content()
    board = _issue(content)
    art = next(b for b in board if b.kind == "art")
    arms = next(b for b in board if b.kind == "arms")
    assert bounties.title(content, art) == f"求藝・{art.attribute}"
    fist, crossbow = (arms.model_copy(update={"weapon_kind": k}) for k in ("拳腳", "弓弩"))
    assert bounties.title(content, fist) == f"求兵・屬{arms.attribute}的拳套"  # 種類照 weapons.NOUNS 寫（同兵器名；FB-133）
    assert f"一把屬{arms.attribute}的弩（" in bounties.how(content, crossbow)
    assert f"屬{art.attribute}、合成出來的武學或內功" in bounties.how(content, art) and "None" not in bounties.how(content, arms)
    loner = GameState(player=PlayerState(name="測", location="town", stats={}, stamina=0), world=WorldState())
    assert bounties.reward_text(loner, content, art) == "賞銀 20・經驗 30・心得 20・俠名 +2・素材，偶有兵器"
    assert bounties.reward_text(loner, content, arms) == "賞銀 20～50（照品質，高階另加）・經驗 30・心得 10・俠名 +2"
    loner.player.faction = art.faction
    assert bounties.reward_text(loner, content, art) == "賞銀 20・經驗 30・心得 20・素材，偶有兵器"
    content.config.weapons.enabled = False
    assert bounties.reward_text(loner, content, art).endswith("心得 20・素材")  # 兵器關著：不送兵器


def test_hand_ins_are_not_taken(beta_setup):
    """求藝、求兵不用揭（設計 4.3）：揭了會佔掉 max_taken 的格子、擋掉討伐與打探，整季機器人與假人也會一直揭。"""
    content, world = beta_setup
    art = _post(world, kind="art", faction="guan", silver=20, deeds=2, quota=3, attribute="剛")
    msgs, _ = _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, art.id))
    assert msgs == [bounties.NO_TAKE] and world.get_season().bounties[-1].takers == []


@pytest.mark.parametrize("field, value", [
    ("kinds", ["strike", "raid"]),
    ("give_kinds", ["art", "armor"]),
    ("give_kinds", ["art", "art"]),  # 照 kinds 的習慣寫兩次是想掛兩張，issue 卻只掛一張：擋下來
    ("give_attributes", []),
    ("give_attributes", ["剛", "土"]),
    ("give_attributes", ["剛", "剛", "柔"]),
    ("arms_silver", {"下品": 20, "中品": 35}),
    ("arms_tier", {"1": 1, "2": 2}),
])
def test_validate_checks_the_bounty_settings(content, field, value):
    """設計 4.1 末段：認不得的種類（以前 issue 默默跳過）、挑不到屬性、求兵的價錢少一個品質或一個階（交那一把會 KeyError），載入時就擋；
    give_kinds、give_attributes 重複也擋（審查補的）。"""
    setattr(content.config.bounties, field, value)
    with pytest.raises(ContentError, match=f"Config.bounties.{field}"):
        validate(content)
