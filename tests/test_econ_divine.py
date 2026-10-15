"""神器配方每種兵器一季最多一條（素材與經濟設計第二節，企劃者 2026-10-15）：照這一季開季時蓋的章（WorldState.forge_divine_per_kind）。
第一季的章六種兵器各一條；其餘的季照天機抽、同一種只挑一條；防具照舊一季一條；正在跑的季（沒有章）照舊。"""
from __future__ import annotations

from conftest import real_content
from tianxia import forge_secrets
from tianxia.world_state import fresh_season, stamp_season


def _divine(content, season):
    return [r for r in forge_secrets.active(content, season.tianji, season) if r.divine]


def test_season_one_has_one_divine_recipe_per_weapon_kind():
    c = real_content("weekend")
    season = fresh_season(c)
    assert season.forge_divine_per_kind and season.season_one
    weapons = [r for r in _divine(c, season) if r.slot == "weapon"]
    pool_kinds = {r.kind for r in c.forge_secrets.values() if r.divine and r.slot == "weapon"}
    assert sorted(r.kind for r in weapons) == sorted(pool_kinds)
    assert len(weapons) == len({r.kind for r in weapons}) == 6
    assert len([r for r in _divine(c, season) if r.slot == "armor"]) == 1


def test_every_tianji_still_gives_six_kinds_in_season_one():
    c = real_content("weekend")
    season = fresh_season(c)
    for tianji in range(8):
        season.tianji = tianji
        assert len({r.kind for r in _divine(c, season) if r.slot == "weapon"}) == 6, tianji


def test_other_seasons_draw_by_tianji_one_per_kind():
    c = real_content()  # 14 天：沒有第一季的章
    want = c.config.forge_secrets.per_season["weapon:divine"]
    for tianji in range(12):
        season = fresh_season(c)
        season.tianji = tianji
        assert not season.season_one and season.forge_divine_per_kind
        weapons = [r for r in _divine(c, season) if r.slot == "weapon"]
        assert len(weapons) == want and len({r.kind for r in weapons}) == want, tianji


def test_a_running_season_keeps_the_old_draw():
    c = real_content("weekend")
    season = fresh_season(c)
    season.forge_divine_per_kind = False  # 上線那一刻正在跑的季：JSON 沒有這一欄
    old = [r.id for r in forge_secrets.active(c, season.tianji)]
    assert [r.id for r in forge_secrets.active(c, season.tianji, season)] == old
    assert len([r for r in forge_secrets.active(c, season.tianji, season) if r.divine and r.slot == "weapon"]) == 2


def test_old_world_json_reads_as_unstamped():
    from tianxia.state import WorldState

    season = WorldState.model_validate({"storyline": "x"})
    assert not season.forge_divine_per_kind and not season.forge_split_clues


def test_switch_off_stamps_nothing():
    c = real_content("weekend")
    c.config.forge_secrets.divine_per_kind = False
    c.config.forge_secrets.split_clues = False
    season = fresh_season(c)
    stamp_season(season, c)
    assert not season.forge_divine_per_kind and not season.forge_split_clues


def test_match_follows_the_season():
    """打得出神器的組合照這一季挑到的那幾條：第一季的章有棍的神器（撼山棍 慢三＋剛三），沒蓋章的季照天機不一定有。"""
    c = real_content("weekend")
    season = fresh_season(c)
    staff = next(r for r in forge_secrets.active(c, season.tianji, season) if r.divine and r.kind == "棍")
    main = next(m.id for m in c.materials.values() if forge_secrets.fits(staff.main, m))
    aux = next(m.id for m in c.materials.values() if forge_secrets.fits(staff.aux, m))
    assert forge_secrets.match(c, season.tianji, "weapon", "棍", main, aux, season) == staff
