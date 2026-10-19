"""正式季第 10 批：神器輪替（正式季整合設計 5.6、10.3、10.4）。這個伺服器第一季九件全開，之後每季 2～4 件輪替現世、至少一件新的；
現世過哪幾件記在全服（SharedWorldState.divine）、開季換季時蓋進季（WorldState.divine_lineup）。開關關著、沒蓋章的季照舊。"""
from __future__ import annotations

from conftest import real_content

from tianxia import divine, forge_secrets
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
