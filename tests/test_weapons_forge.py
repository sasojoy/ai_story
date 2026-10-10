"""兵器第二批：自己打造（docs/superpowers/specs/2026-10-09-兵器-design.md 4.2～4.4、4.7、4.7.1；
計畫 docs/superpowers/plans/2026-10-10-兵器-2-自己打造.md）。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import team, weapons
from tianxia.models import WEAPON_KINDS
from tianxia.state import Weapon


def _on(content):
    content.config.weapons.enabled = True
    return content


def _blade(kind="劍", attribute="柔", tier=1, quality="下品", edge=100, wid="兵:1", name="試刃"):
    return Weapon(id=wid, name=name, kind=kind, attribute=attribute, tier=tier, quality=quality, edge=edge)


def _game(content, world, name="試劍", art="sword"):
    from tianxia import rules
    from tianxia.engine import Game
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    rules.learn_skill(game.state, content, art)
    return game


def _town(content, world, silver=200, name="試劍"):
    """在測試內容的城鎮（town：標籤城鎮、沒寫素材，當地鐵匠的屬性是剛），身上那門是流雲劍（柔・劍）。"""
    _on(content)
    game = _game(content, world, name=name)
    p = game.state.player
    p.location, p.stamina, p.stats["silver"] = "town", 100.0, silver
    p.member.wugong_id = "sword"
    game.sync(0.0)
    return game


def _ids(game):
    return {o.id: o for o in game.options(odds=False)}


def _art(game, content, world):
    return team.player_art(game.state, content, world, game.state.player.member.wugong_id)


# ── Task 1：拆解先問一次（FB-125）──

def test_rack_rows_carry_the_grade_and_a_dismantle_question(content, world):
    game = _town(content, world)
    p = game.state.player
    p.weapon = _blade()
    p.rack = [_blade(kind="刀", attribute="剛", tier=2, quality="中品", wid="兵:2", name="厚背刀")]
    data = weapons.rows(game.state, content, world, _art(game, content, world))
    assert data["rack"][0]["grade"] == "二階中品"
    assert data["rack"][0]["confirm"] == "把【厚背刀】（二階中品）拆成玄鋼骨×1？拆掉就沒了。"
    assert data["worn"]["grade"] == "一階下品" and data["worn"]["confirm"] == ""  # 身上那把不能拆，沒有問句


def test_smith_dismantle_buttons_ask_first_with_their_own_yes_word(content, world):
    game = _town(content, world)
    p = game.state.player
    p.weapon = _blade()
    p.rack = [_blade(kind="刀", attribute="剛", wid="兵:2", name="厚背刀")]
    game.choose("act:smith")
    opts = _ids(game)
    assert opts["smith:dismantle:兵:2"].confirm == "把【厚背刀】（一階下品）拆成精鐵砂×1？拆掉就沒了。"
    assert opts["smith:dismantle:兵:2"].confirm_yes == weapons.DISMANTLE_YES == "拆掉"
    assert all(o.confirm == "" for oid, o in opts.items() if not oid.startswith("smith:dismantle:"))
    game.choose("smith:dismantle:兵:2")  # 問一次是網頁的事：引擎收到照拆（機器人、腳本都這樣走）
    assert p.rack == [] and p.materials == {"gang_1": 1}


# ── Task 2：兵器配方的資料與資料庫第 4 版 ──

from tianxia.martial_arts import Insight, generate_from_name  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.state import WeaponRecipe  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return open_world(tmp_path / "w.db")


def _recipe(name="寒星劍", key="兵|劍|gang_1+kuai_1", creator="甲"):
    return WeaponRecipe(name=name, key=key, kind="劍", attribute="陽", tier=1, main="gang_1", aux="kuai_1",
                        creator=creator, creator_shown=creator)


def test_weapon_recipe_id_is_its_name_and_round_trips():
    r = _recipe()
    assert r.id == "寒星劍"
    assert WeaponRecipe.model_validate_json(r.model_dump_json()) == r


def test_the_first_weapon_recipe_claim_wins_and_later_ones_read_it(store):
    first = _recipe()
    assert store.claim_weapon_recipe(first.key, first) == (first, True)
    got, is_first = store.claim_weapon_recipe(first.key, _recipe(name="霜鳴劍", creator="乙"))
    assert is_first is False and got.name == "寒星劍" and got.creator == "甲"
    assert store.lookup_weapon_recipe(first.key) == first
    assert store.lookup_weapon_recipe("兵|劍|kuai_1+gang_1") is None  # 主輔對調是另一個配方
    assert store.is_skill_name_taken("霜鳴劍") is False  # 沒登記上的名字不佔名字空間


def test_weapon_recipe_names_share_the_namespace_with_arts_and_insights(store):
    store.claim_skill_name(generate_from_name("寒星劍", "武學", "寒星劍"))
    assert store.claim_weapon_recipe("兵|劍|gang_1+kuai_1", _recipe()) == (None, False)  # 武學用掉的名字
    other = _recipe(name="霜鳴劍", key="兵|劍|gang_1+gang_1")
    assert store.claim_weapon_recipe(other.key, other) == (other, True)
    assert store.is_skill_name_taken("霜鳴劍") is True
    assert store.claim_skill_name(generate_from_name("霜鳴劍", "武學", "霜鳴劍")) is False  # 反過來也擋
    got, first = store.claim_insight_recipe("feng+huo", Insight(id="霜鳴劍", name="霜鳴劍", attribute="陽"))
    assert (got, first) == (None, False)
    clash = _recipe(name="霜鳴劍", key="兵|刀|gang_1+gang_1")
    assert store.claim_weapon_recipe(clash.key, clash) == (None, False)  # 兩個配方不能同名


def test_weapon_recipes_are_per_season(store, content):
    content.config.auto_open_first_season = True
    store.seed_first_season(content)
    r = _recipe()
    store.claim_weapon_recipe(r.key, r)
    store.mutate_season(lambda season: setattr(season, "ended", True))
    assert store.next_season(content, now=1.0)
    assert store.lookup_weapon_recipe(r.key) is None
    with store.db.snapshot() as conn:  # 換季不刪資料：上一季的配方留著
        assert conn.execute("SELECT season FROM gear_recipes WHERE key = ?", (r.key,)).fetchone()["season"] == 1
    again = _recipe(creator="乙")
    assert store.claim_weapon_recipe(r.key, again) == (again, True)  # 新的一季：同一個配方別人首創、名字也能再用
