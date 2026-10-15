"""陣營通緝（名聲 4.6）與官府通緝（5.4）。"""
import random

from conftest import real_content

from tianxia import bounties, calendar, renown
from tianxia.engine import Game


def _game(name, faction=None, fame=0, good=0, evil=0, content=None, world=None):
    c = content or real_content("weekend")
    c.config.auto_open_first_season = True
    g = Game.new(c, name, rng=random.Random(0), world=world)
    g.client = None
    p = g.state.player
    p.faction = faction
    p.stats.update({"fame": fame, "good": good, "evil": evil})
    p.joined_at = -1e9  # 過了新手期
    return g


def test_faction_wanted_posts_once_a_week():
    g = _game("甲", faction="guan", fame=50)
    assert bounties.post_auto(g.state, g.content) == ["黃巾軍貼出了通緝你的告示（威震州郡）。"]
    assert bounties.post_auto(g.state, g.content) == []
    posted = [b for b in g.state.world.bounties if b.auto_by == "陣營"]
    assert len(posted) == 1 and posted[0].faction == "huang" and posted[0].silver == 40 and posted[0].poster is None
    assert bounties.title(g.content, posted[0]) == "黃巾軍通緝・甲（威震州郡）"
    assert bounties.issuer(g.content, posted[0]) == "黃巾軍"


def test_who_is_not_posted():
    assert bounties.post_auto(_game("散", fame=90).state, real_content("weekend")) == []  # 散人沒有對面
    g = _game("豪", faction="haoqiang", fame=90)
    assert bounties.post_auto(g.state, g.content) == []  # 第三方豪強：兩邊都打，挑不出哪一軍
    n = _game("新", faction="guan", fame=90)
    n.state.player.joined_at = n.state.world.time
    assert bounties.post_auto(n.state, n.content) == []  # 新手期
    off = real_content("weekend")
    off.config.renown.faction_wanted = False
    assert bounties.post_auto(_game("關", faction="guan", fame=90, content=off).state, off) == []
    r = real_content("weekend")
    r.config.raid.enabled = False
    assert bounties.post_auto(_game("停", faction="guan", fame=90, content=r).state, r) == []


def test_official_wanted_for_great_rogues_any_side():
    g = _game("乙", evil=15)
    assert bounties.post_auto(g.state, g.content) == ["官府貼出了海捕文書，畫的是你（江湖巨寇）。"]
    b = next(x for x in g.state.world.bounties if x.auto_by == "官府")
    assert (b.faction, b.silver, bounties.title(g.content, b), bounties.issuer(g.content, b)) == (None, 30, "官府通緝・乙（江湖巨寇）", "官府")
    hero = _game("丙", faction="huang", good=15, world=g.world)
    hero.state.world = g.state.world
    assert bounties.take_problem(hero.state, hero.content, b) is None
    rogue = _game("丁", faction="huang", good=3, world=g.world)
    rogue.state.world = g.state.world
    assert bounties.take_problem(rogue.state, rogue.content, b) == "要一方豪俠才揭得了官府的海捕文書"
    assert bounties.take(hero.state, hero.content, b.id)[0].startswith("你揭下了")
    assert bounties.stranded(hero.state, hero.content, "guan") == []  # 換陣營不作廢
    hero.state.player.faction = "guan"
    assert bounties.deliver_lapses(hero.state, hero.content) == []
    hero.state.player.stats.update({"good": 0, "evil": 9})  # 揭了之後掉段、換成寇：手上那一張照留
    assert [x.id for x in bounties.mine(hero.state, hero.content)] == [b.id]


def test_system_wanted_expire_off_the_board():
    g = _game("甲", faction="guan", fame=50)
    bounties.post_auto(g.state, g.content)
    b = next(x for x in g.state.world.bounties if x.auto_by)
    w = g.state.world
    w.time = b.expires + 1
    week = calendar.point(w.time, g.content, w).week
    w.bounty_week = week - 1
    bounties.issue(g.state, g.content, week)
    assert b not in w.bounties


def test_a_hero_with_the_magistrates_notice_beats_the_rogue_and_cuts_his_name():
    rogue = _game("寇甲", faction="guan", evil=20)
    hero = _game("俠乙", faction="guan", good=20, world=rogue.world)
    for g in (rogue, hero):
        g.state.player.location = "yingchuan_wilds"
    hero.state.world = rogue.state.world
    rogue.own_turn_checks()
    hero.state.world = rogue.world.get_season()
    b = next(x for x in hero.state.world.bounties if x.auto_by == "官府")
    bounties.take(hero.state, hero.content, b.id)
    assert hero.raid_shown(rogue)  # 同一邊也打得到（官府通緝是例外）
    hero.state.player.stats["str"] = 30
    hero.rng = random.Random(1)
    hero.raid(rogue)
    assert rogue.state.player.stats["evil"] == 17
    line = "惡名 -3（你被揭了官府海捕文書的俠乙打敗了）"
    assert any(line in r.changes for r in rogue.state.battles)
    assert any(line in e.lines or line in e.changes for e in rogue.state.journal)


def test_the_virtue_perks_name_the_notices():
    c = real_content("weekend")
    assert "官府每週貼你的海捕文書（賞 30 兩）" in renown.virtue_perks(c, "寇", 2)
    assert "揭得了官府通緝" in renown.virtue_perks(c, "俠", 2)
