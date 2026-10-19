"""正式季第 10 批：神器輪替（正式季整合設計 5.6、10.3、10.4）。這個伺服器第一季九件全開，之後每季 2～4 件輪替現世、至少一件新的；
現世過哪幾件記在全服（SharedWorldState.divine）、開季換季時蓋進季（WorldState.divine_lineup）。開關關著、沒蓋章的季照舊。"""
from __future__ import annotations

from conftest import real_content

from tianxia import divine, equipment, forge_secrets
from tianxia.sqlite_world import open_world

NOW = 1792339200.0  # 2026-10-19 週一 00:00（台灣）


def _content(rotation=True):
    c = real_content()
    c.config.forge_secrets.rotation = rotation
    return c


def _opened(c):
    w = open_world()
    w.seed_first_season(c)
    assert w.open_season(c, NOW)
    return w


def _next(c, w, n=1):
    for i in range(n):
        w.mutate_season(lambda s: setattr(s, "ended", True))
        assert w.next_season(c, NOW + (i + 1) * 86400)
    return w.get_season()


def _divines(c, ids):
    return [c.forge_secrets[i] for i in ids]


# ── Task 1：現世登記與每季輪替 ──


def test_the_first_season_opens_all_nine():
    c = _content()
    w = _opened(c)
    nine = sorted(r.id for r in c.forge_secrets.values() if r.divine and r.wave == 1)
    assert len(nine) == 9
    assert sorted(w.get_season().divine_lineup) == nine
    assert sorted(w.divine_state().seen) == nine


def test_later_seasons_rotate_two_to_four():
    c = _content()
    w = _opened(c)
    for _ in range(10):
        before = set(w.divine_state().seen)
        pool = {r.id for r in c.forge_secrets.values() if r.divine}
        lineup = _next(c, w).divine_lineup
        picked = _divines(c, lineup)
        assert c.config.forge_secrets.rotation_min <= len(lineup) <= c.config.forge_secrets.rotation_max
        assert any(r.slot == "weapon" for r in picked) and any(r.slot == "armor" for r in picked)
        kinds = [r.kind for r in picked if r.slot == "weapon"]
        assert len(kinds) == len(set(kinds))  # 同一種兵器一季最多一件
        if pool - before:
            assert set(lineup) - before  # 至少一件之前沒現世過
        assert set(lineup) <= set(w.divine_state().seen)


def test_when_new_divines_run_out_it_still_picks_and_warns():
    """Review Focus 5：全部都現世過之後照樣挑得出 2～4 件、規則照守；那一季記下、管理者換季的回話提醒。"""
    from tianxia.engine import Game
    import random

    c = _content()
    c.config.admins = ["管理者"]
    w = _opened(c)
    every = [r.id for r in c.forge_secrets.values() if r.divine]
    w.mutate(lambda s: setattr(s.divine, "seen", list(every)))
    admin = Game.new(c, "管理者", rng=random.Random(1), world=w)
    admin.admin_end_season(now=NOW + 100)
    msgs = admin.admin_next_season(now=NOW + 200)
    lineup = w.get_season().divine_lineup
    assert 2 <= len(lineup) <= 4 and any(c.forge_secrets[i].slot == "armor" for i in lineup)
    assert w.divine_state().exhausted == w.get_season_number()
    assert divine.EXHAUSTED in msgs


def test_active_follows_the_lineup():
    c = _content()
    w = _opened(c)
    season = _next(c, w)
    tianji = w.read().tianji
    active = forge_secrets.active(c, tianji, season)
    assert sorted(r.id for r in active if r.divine) == sorted(season.divine_lineup)
    assert any(not r.divine for r in active)  # 名器配方照舊照天機挑


def test_rotation_off_or_unstamped_is_unchanged():
    """Review Focus 2：開關關著不蓋章；沒有章的季（開關打開之前就在跑的）active 照舊。"""
    c = _content(rotation=False)
    w = _opened(c)
    season = w.get_season()
    assert season.divine_lineup is None and w.divine_state().seen == []
    tianji = w.read().tianji
    old = [r.id for r in forge_secrets.active(c, tianji, season)]
    c.config.forge_secrets.rotation = True  # 開關打開之後，正在跑的季照它開季時的挑法
    assert [r.id for r in forge_secrets.active(c, tianji, season)] == old


# ── Task 2：原品全服一把、名字跨季 ──

SWORD = "wd_dark_crystal"  # 玄晶劍：劍，快四＋柔四


def _smith(c, w, name, level=20):
    import random

    from tianxia.engine import Game

    game = Game.new(c, name, rng=random.Random(0), world=w)
    p = game.state.player
    p.location = next(lid for lid, loc in c.locations.items() if equipment.TOWN_TAG in (loc.tags or []))
    p.member.level = level
    p.stats["silver"] = 10000
    return game


def _forge_sword(c, w, game, rid=SWORD):
    from tianxia import smithing

    recipe = c.forge_secrets[rid]
    main = next(m.id for m in c.materials.values() if m.tier == 4 and m.attribute == recipe.main.attribute)
    aux = next(m.id for m in c.materials.values() if m.tier == 4 and m.attribute == recipe.aux.attribute)
    p = game.state.player
    p.materials[main] = p.materials.get(main, 0) + 1
    p.materials[aux] = p.materials.get(aux, 0) + 1
    return smithing.forge(game.state, c, w, recipe.kind, main, aux)


def test_one_original_per_server_across_seasons():
    c = _content()
    w = _opened(c)
    jia = _smith(c, w, "甲")
    item, _ = _forge_sword(c, w, jia)
    assert item.original and item.collected
    find = w.divine_state().finds[SWORD]
    assert find.owner == "甲" and find.season == 1
    season = _next(c, w)
    w.mutate_season(lambda s: setattr(s, "divine_lineup", [SWORD, "ad_still_wave"]))  # 這一季玄晶劍再現世
    yi = _smith(c, w, "乙")
    copy, _ = _forge_sword(c, w, yi)
    assert not copy.original and copy.copy_of == forge_secrets.key_for(SWORD) and copy.collected
    assert w.divine_state().finds[SWORD].copies == 1 and season.divine_lineup is not None
    records = dict((f.secret, (s, f)) for s, f in w.divine_records())
    assert records[SWORD][0] == 1 and records[SWORD][1].owner == "甲" and records[SWORD][1].copies == 1


def test_the_name_holds_across_seasons():
    """Review Focus 3：第一季沒定名就換季，第二季主人照樣定名；定的名字別人取不到（跨季保留）。"""
    c = _content()
    w = _opened(c)
    _forge_sword(c, w, _smith(c, w, "甲"))
    _next(c, w)
    key = forge_secrets.key_for(SWORD)
    assert w.lookup_gear_find(key).divine_name is None
    assert w.name_divine(key, "乙", "寒星") == "owner"
    assert w.name_divine(key, "甲", "寒星") is None
    assert w.lookup_gear_find(key).divine_name == "寒星"
    assert w.is_skill_name_taken("寒星")
    _next(c, w)
    assert w.is_skill_name_taken("寒星") and w.lookup_gear_find(key).divine_name == "寒星"


def test_one_divine_each():
    c = _content()
    w = _opened(c)
    jia = _smith(c, w, "甲")
    _forge_sword(c, w, jia)
    p = jia.state.player
    silver = p.stats["silver"]
    item, msgs = _forge_sword(c, w, jia)
    assert item is None and msgs == [f"（{forge_secrets.HAVE_DIVINE}。）"]
    assert p.stats["silver"] == silver and p.materials.get("kuai_4") == 1 and p.materials.get("rou_4") == 1  # 不收錢、不收料
    assert w.divine_state().finds[SWORD].copies == 0


def test_old_seasons_keep_their_rows():
    """Review Focus 1、2：沒蓋章的季打的原品照舊記在照季分的那一列、神器譜照列，不進全服登記、不帶走。"""
    c = _content(rotation=False)
    w = _opened(c)
    rid = next(r.id for r in forge_secrets.active(c, w.read().tianji, w.get_season()) if r.divine and r.slot == "weapon")
    item, _ = _forge_sword(c, w, _smith(c, w, "甲"), rid)
    assert item.original and not item.collected
    assert w.divine_state().finds == {}
    assert w.lookup_gear_find(forge_secrets.key_for(rid)).owner == "甲"
    assert [f.secret for _, f in w.divine_records()] == [rid]
