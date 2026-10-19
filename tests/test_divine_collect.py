"""正式季第 10 批：神器跨季帶著走、15 級才穿得上、鑄譜記得打中過的（正式季整合設計 5.6、5.8）。"""
from __future__ import annotations

from test_divine_rotation import NOW, SWORD, _content, _forge_sword, _next, _opened, _smith

from tianxia import equipment, forge_secrets, weapons

ROBE = "ad_still_wave"  # 凝波甲：防具，柔四＋柔四


def _roll(c, w, game, lineup=None):
    """換季（store 那一層），可以指定下一季現世的神器；再讓這個角色同步一次（換季重來發生在 sync 裡）。"""
    _next(c, w)
    if lineup is not None:
        w.mutate_season(lambda s: setattr(s, "divine_lineup", list(lineup)))
    game.sync(NOW + 5 * 86400)
    assert game.state.player.season_number == w.get_season_number()


def test_divines_cross_the_season_in_the_rack():
    c = _content()
    w = _opened(c)
    jia = _smith(c, w, "甲")
    item, _ = _forge_sword(c, w, jia)
    p = jia.state.player
    assert p.weapon is not None and p.weapon.id == item.id  # 20 級：空著的欄位直接穿上
    item.tempers, item.edge, item.bound_art = 2, 70, "某門絕學"
    old = weapons.new_weapon(jia.state, name="舊神器", kind="刀", attribute="剛", tier=3, quality="上品", original=True,
                             secret="wd_fallen_star")  # 上線前打的三階神器：不帶走
    plain = weapons.new_weapon(jia.state, name="尋常劍", kind="劍", attribute="快", tier=1, quality="下品")
    p.rack += [old, plain]
    serial = p.weapon_serial
    _roll(c, w, jia)
    q = jia.state.player
    assert q.weapon is None  # 換季後放在裝備庫，不在身上
    carried = [i for i in q.rack if i.id == item.id]
    assert len(carried) == 1 and len(q.rack) == 1
    kept = carried[0]
    assert (kept.tempers, kept.edge, kept.quality, kept.original, kept.collected) == (2, 70, "上品", True, True)
    assert kept.bound_art is None  # 以器配招清掉
    assert q.weapon_serial >= serial  # 流水號接著走：新打的不會跟帶過來的撞 id
    assert forge_secrets.unnamed_originals(jia.state, w) == {item.id: c.forge_secrets[SWORD].name}  # 第二季照樣能定名


def test_without_carried_divines_the_serial_starts_over():
    """FB-401：沒帶神器過季（輪替關著、手上沒有輪替季的神器）時，四欄流水號照上線前重來；帶了才接著走（上一個測試）。"""
    import random

    from tianxia.engine import Game

    c = _content(rotation=False)
    w = _opened(c)
    jia = _smith(c, w, "甲")
    p = jia.state.player
    p.rack += [weapons.new_weapon(jia.state, name=f"尋常劍{i}", kind="劍", attribute="快", tier=1, quality="下品") for i in range(3)]
    assert p.weapon_serial >= 3
    _roll(c, w, jia)
    fresh = Game.new(c, "乙", rng=random.Random(0), world=w).state.player.weapon_serial
    assert jia.state.player.rack == [] and jia.state.player.weapon_serial == fresh


def test_below_level_fifteen_divines_wait_in_the_rack():
    """Review Focus 4：14 級打出來的神器進裝備庫（裝備庫滿了也放得進）、換不上、鐵匠鋪不列「換上」；15 級穿得上。"""
    c = _content()
    w = _opened(c)
    jia = _smith(c, w, "甲", level=14)
    p = jia.state.player
    p.rack = [weapons.new_weapon(jia.state, name=f"尋常劍{i}", kind="劍", attribute="快", tier=1, quality="下品")
              for i in range(c.config.weapons.rack_cap)]
    robe, _ = _forge_sword(c, w, jia, ROBE)
    assert robe is not None and p.armor is None and robe in p.rack
    low = equipment.WEAR_LOW.format(n=1)
    assert equipment.wield(jia.state, c, robe.id, ("armor",)) == [f"（{low}。）"]
    from tianxia import armor

    row = next(r for r in armor.rows(jia.state, c, None)["rack"] if r["id"] == robe.id)
    assert row["wield_ok"] is False and row["wield_note"] == low
    p.rack = [robe]
    jia.choose("act:smith")
    if equipment.page(jia.state.player, c) != "armor":
        jia.choose("smith:page:armor")
    assert f"smith:wield:{robe.id}" not in [o.id for o in jia.options()]
    p.member.level = 15
    assert f"smith:wield:{robe.id}" in [o.id for o in jia.options()]
    assert equipment.wield(jia.state, c, robe.id, ("armor",)) == [equipment.WIELDED.format(name=robe.name)]


def test_the_practice_page_greys_the_wield_button_below_fifteen():
    """修練頁（web/app.js 的 rowButtons）：14 級時那一列的「換上」灰掉、說明底下寫還差幾級；15 級照常。"""
    import pytest
    import webharness

    if webharness.NODE is None:
        pytest.skip("沒有 node，前端畫面測試略過")
    import server
    from test_prologue_web import run

    c = _content()
    w = _opened(c)
    jia = _smith(c, w, "甲", level=14)
    robe, _ = _forge_sword(c, w, jia, ROBE)
    low = equipment.WEAR_LOW.format(n=1)
    page = run(server.main_view(jia), "return H.pagePractice();", menxia=server.menxia_view(jia))
    assert f'data-act="wield" data-id="{robe.id}" disabled title="{low}"' in page and f'<small class="rwhy">{low}</small>' in page
    jia.state.player.member.level = 15
    page = run(server.main_view(jia), "return H.pagePractice();", menxia=server.menxia_view(jia))
    assert f'data-act="wield" data-id="{robe.id}">換上' in page and low not in page


def test_the_manual_remembers_solved_divines():
    c = _content()
    w = _opened(c)
    jia = _smith(c, w, "甲")
    _forge_sword(c, w, jia)
    assert SWORD in jia.state.player.divine_solved
    _roll(c, w, jia, lineup=["wd_fallen_star", ROBE])  # 這一季玄晶劍沒現世
    row = next(r for r in forge_secrets.view(jia.state, c, w) if r["solved"] == c.forge_secrets[SWORD].name)
    assert forge_secrets.NOT_NOW in row["recipe"]
    _roll(c, w, jia, lineup=[SWORD, ROBE])  # 又現世了
    row = next(r for r in forge_secrets.view(jia.state, c, w) if r["solved"] == c.forge_secrets[SWORD].name)
    assert forge_secrets.SEEN_NOW in row["recipe"]
    tianji = w.read().tianji
    for i in range(40):  # 打中過的那一件不再分片子給他
        forge_secrets.hear(jia.state, c, tianji, forge_secrets.TALE, f"s{i}")
    assert SWORD not in jia.state.player.forge_manual.pieces
    assert forge_secrets.solved_name(jia.state, c, tianji, "weapon", "劍", "kuai_4", "rou_4") == c.forge_secrets[SWORD].name
