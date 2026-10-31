"""減法季批 3b QA 之後的修正：FB-856 豪強貼了約戰（或應戰、同去）之後改幫，結算時的帳照貼（應、同去）那一刻替哪一軍出力記。

約戰的推（拉）本來就照貼（應）那一刻抄進 SortieSide.side 的那一軍；貢獻的第二本帳（wins.credit 的 side）與攻城、守城軍令（_order_credit 的陣營）
以前照結算那一刻的傾向，豪強能在窗內改幫、看好會贏的那一邊再結算，把那一場的帳搬過去。同 FB-812（決戰：開打之後改了傾向，戰功照參戰那一邊記）。
同去的人替攻方那一軍出力（join_problem 要求同一軍）。"""
from __future__ import annotations


from duel_kit import LOC, NOW, WINDOW, do, duel_content, duel_world, game_of, load, rounds_go, seat, tick
from tianxia import conquest, orders, wins
from tianxia.state import Order

HOME = "zhuo_county"  # 涿郡：官軍的地方，黃巾開季就碰得到（守方贏要拉進度、守城軍令認它）


def _go(c, world, name, moves="強攻,固守,奇襲", now=NOW):
    return do(c, world, name, lambda g: g.choose(f"sortie:go:{moves}"), now)


def _answer(c, world, name, duel_id, now=NOW + 60):
    return do(c, world, name, lambda g: g.choose(f"sortie:answer:{duel_id}:固守,固守,固守"), now)


def _only(world):
    duels = world.sortie_duels()
    assert len(duels) == 1, duels
    return next(iter(duels.values()))


def _orders(c, world, loc: str, *templates: tuple[str, str]) -> dict[str, str]:
    """每一軍各掛一道指定種類的軍令（量大到不會達成）。回 {軍令種類+陣營: 軍令 id}。"""
    g = game_of(c, world, "甲")
    season = g.state.world
    front = conquest.line_of(season, c, loc)
    ids = {}
    for template, faction in templates:
        order = Order(id=f"t:{faction}:{template}", template=template, faction=faction, week=orders.period_of(g.state, c), front=front,
                      quota=99, text="（測試）")
        season.orders.append(order)
        ids[f"{template}:{faction}"] = order.id
    g._save_season()
    return ids


def _bars(c, world, loc: str, **values: float) -> None:
    season = world.get_season()
    for side, value in values.items():
        conquest.push(season, c, loc, side, "某", value, "attack")
    world.save_season(season)


def _progress(world, order_id: str, name: str) -> int:
    return next(o for o in world.get_season().orders if o.id == order_id).progress.get(name, 0)


def _gentry(c, world, name: str, ally: str, loc: str) -> None:
    seat(c, world, name, None, loc, faction="haoqiang", ally=ally)


def _lean(c, world, name: str, side: str, now: float):
    msgs, _ = do(c, world, name, lambda g: g.choose(f"faction:lean:{side}"), now)
    assert load(world, name).player.ally == side, msgs


def test_the_attacker_who_leans_after_posting_is_still_credited_to_the_army_he_posted_for(monkeypatch):
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "乙", "huang", LOC)
    _gentry(c, world, "丙", "guan", LOC)
    assert wins.on(c, world.get_season())
    ids = _orders(c, world, LOC, ("siege", "guan"), ("siege", "huang"))
    _bars(c, world, LOC, guan=10.0, huang=10.0)  # 兩軍在這一塊進度一樣高：兩邊的攻城軍令都認這一處
    _go(c, world, "丙")
    _answer(c, world, "乙", _only(world).id)
    _lean(c, world, "丙", "huang", NOW + 120)  # 窗內改幫：看好黃巾會贏
    rounds_go(monkeypatch, "大勝")
    tick(c, world, NOW + WINDOW + 1)
    duel = _only(world)
    assert duel.status == "settled" and duel.result.tier == "big" and duel.attacker.side == "guan"
    p = load(world, "丙").player
    assert p.ally == "huang" and p.contrib > 0
    # 帳記在貼約戰時替的那一軍；攻城軍令也記在官軍那一道
    assert (p.ledgers, _progress(world, ids["siege:guan"], "丙"), _progress(world, ids["siege:huang"], "丙")) \
        == ({"guan": p.contrib}, 1, 0)


def test_the_defender_who_leans_after_answering_is_still_credited_to_the_army_he_answered_for(monkeypatch):
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "乙", "huang", HOME)
    _gentry(c, world, "丙", "guan", HOME)
    ids = _orders(c, world, HOME, ("defend", "guan"), ("defend", "huang"))
    _bars(c, world, HOME, huang=20.0)  # 黃巾在官軍的涿郡推到一半：官軍的守城軍令認這一處
    _go(c, world, "乙")
    duel = _only(world)
    assert duel.attacker.side == "huang"
    _answer(c, world, "丙", duel.id)
    assert _only(world).defender.side == "guan"
    _lean(c, world, "丙", "huang", NOW + 120)
    rounds_go(monkeypatch, "落敗")  # 攻方輸：守方贏，拉進度
    tick(c, world, NOW + WINDOW + 1)
    duel = _only(world)
    assert duel.status == "settled" and duel.result.defender_tier == "big"
    p = load(world, "丙").player
    assert p.ally == "huang" and p.contrib > 0
    assert (p.ledgers, _progress(world, ids["defend:guan"], "丙"), _progress(world, ids["defend:huang"], "丙")) \
        == ({"guan": p.contrib}, 1, 0)


def test_the_ally_who_joined_and_then_leaned_is_credited_to_the_attackers_army(monkeypatch):
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan", LOC)
    seat(c, world, "乙", "huang", LOC)
    _gentry(c, world, "丙", "guan", LOC)
    _go(c, world, "甲")
    duel = _only(world)
    do(c, world, "丙", lambda g: g.choose(f"sortie:join:{duel.id}"), NOW + 30)
    assert _only(world).attacker.allies == ["丙"]
    _answer(c, world, "乙", duel.id)
    _lean(c, world, "丙", "huang", NOW + 120)
    rounds_go(monkeypatch, "大勝")
    tick(c, world, NOW + WINDOW + 1)
    p = load(world, "丙").player
    assert p.ally == "huang" and p.contrib > 0
    assert p.ledgers == {"guan": p.contrib}, p.ledgers
    assert load(world, "甲").player.ledgers == {}  # 兩軍的人沒有第二本帳


def test_without_leaning_the_ledger_is_unchanged(monkeypatch):
    """沒改幫的對照：帳照舊記在幫的那一軍（所以上面三條的「記官軍」是修的結果，不是本來就這樣）。"""
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "乙", "huang", LOC)
    _gentry(c, world, "丙", "guan", LOC)
    _go(c, world, "丙")
    _answer(c, world, "乙", _only(world).id)
    rounds_go(monkeypatch, "大勝")
    tick(c, world, NOW + WINDOW + 1)
    p = load(world, "丙").player
    assert p.ledgers == {"guan": p.contrib} and p.contrib > 0


def test_the_push_itself_still_follows_the_snapshot(monkeypatch):
    """推（拉）的條本來就照貼約戰那一刻的那一軍，改幫之後也不動它（這一批不改，鎖住）。"""
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "乙", "huang", LOC)
    _gentry(c, world, "丙", "guan", LOC)
    _go(c, world, "丙")
    _answer(c, world, "乙", _only(world).id)
    _lean(c, world, "丙", "huang", NOW + 120)
    rounds_go(monkeypatch, "大勝")
    tick(c, world, NOW + WINDOW + 1)
    season = world.get_season()
    assert conquest.bar(season, LOC, "guan") > 0 and conquest.bar(season, LOC, "huang") == 0
