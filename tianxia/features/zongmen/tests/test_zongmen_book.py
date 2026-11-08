"""師門武譜（門派包第二批；設計稿 v6 第一根柱子，Joy 2026-11-08「不錯，按照設計稿動工」）：獻式、同門試練入譜、學式（低一品）、
基本意境與神品不能獻、期限到了退回、換季譜還在。"""
from __future__ import annotations

import random

from conftest import real_content

from tianxia import insights
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.features.zongmen import actions, book as B, bots
from tianxia.martial_arts import Insight
from tianxia.state import InsightFx

NOW = 1_000_000.0


def _content():
    c = real_content("week7")
    c.config.auto_open_first_season = True
    c.config.zongmen.enabled = True
    return c


def _member(c, name, now=NOW, world=None):
    if world is None:
        g = Game.new(c, name, rng=random.Random(0))
    else:
        g = Game.new(c, name, rng=random.Random(0))
    g.sync(now)
    p = g.state.player
    p.location, p.journey = "baima_temple", None
    g.choose("zongmen:join:baima")
    p.stats["xinde"] = 500
    CharacterStore(g.world.db).save(g.state)
    return g


def _again(c, g, now):
    h = Game(c, CharacterStore(g.world.db).load(g.state.player.name), random.Random(0), g.world)
    h.client = None
    h.sync(now)
    return h


def _done(g):
    CharacterStore(g.world.db).save(g.state)


def _own(g, name="寒潭映月", quality="上品"):
    own = insights.add_own(g.state, Insight(id="x", name=name, attribute="柔", note="水底一輪月"))
    g.state.player.insight_fx[own.id] = InsightFx(quality=quality, general={"柔": 2})
    return own


def _book(g):
    return g.world.read().sect_books["baima"]


def test_offer_try_and_learn():
    c = _content()
    a, b, d = _member(c, "甲"), _member(c, "乙"), _member(c, "丙")
    a = _again(c, a, NOW + 1)
    own = _own(a)
    assert (own.id, "寒潭映月") in actions.offerable(a)
    assert actions.offer(a, own.id) == [B.OFFERED.format(name="寒潭映月")]
    _done(a)
    entry = _book(a).entries[0]
    assert entry.status == "pending" and entry.need == 2 and entry.giver == "甲"
    assert actions.offer(a, own.id) == [B.TOO_MANY + "。"]
    # 獻的人自己試不了；乙、丙在山門前試練
    assert not any(o.id.startswith("zongmen:try:") for o in a.options())
    b = _again(c, b, NOW + 2)
    opt = next(o for o in b.options() if o.id.startswith("zongmen:try:baima:"))
    assert opt.label == "試寒潭映月" and "甲獻" in opt.note
    b.choose(opt.id)
    assert b.state.player.stats["xinde"] == 500 - c.config.zongmen.trial_xinde
    _done(b)
    d = _again(c, d, NOW + 3)
    msgs = d.choose(opt.id)
    _done(d)
    assert any("第一式" in m for m in msgs)
    entry = _book(d).entries[0]
    assert entry.status == "in" and entry.number == 1 and B.carve(entry) == "第一式・甲所創・第 1 季"
    view = actions.view(d)
    assert view["entries"][0]["name"] == "寒潭映月" and view["entries"][0]["problem"] == ""
    out = actions.learn(d, entry.id)
    assert out == [B.LEARNED.format(sect="白馬寺", num="一", name="寒潭映月")]
    got = next(i for i in d.state.player.own_insights.values() if i.name == "寒潭映月")
    assert d.state.player.insight_fx[got.id].quality == "中品" and got.id in d.state.player.insights
    assert actions.learn(d, entry.id) == [B.HAVE + "。"]
    assert all(name != "寒潭映月" for _, name in actions.offerable(d))  # 學來的那一份不能再獻回去


def test_basic_insights_and_gods_cannot_be_offered_and_offers_need_the_gate():
    c = _content()
    a = _member(c, "甲")
    basic = next(iter(c.insights))
    a.state.player.insights.append(basic)
    assert actions.offer(a, basic) == [B.BASIC + "。"]
    own = _own(a)
    a.state.player.location = "luoyang_palace"
    assert actions.offer(a, own.id) == ["此刻無法這麼做。"]
    assert all(iid != basic for iid, _ in actions.offerable(a))


def test_an_offer_nobody_tries_goes_back_after_the_window():
    c = _content()
    a = _member(c, "甲")
    own = _own(a)
    actions.offer(a, own.id)
    _done(a)
    later = NOW + c.config.zongmen.offer_seconds + 1
    b = _member(c, "乙", now=later)
    assert not any(o.id.startswith("zongmen:try:") for o in b.options())
    a = _again(c, a, later)
    assert actions.offer(a, own.id) == [B.OFFERED.format(name="寒潭映月")]  # 退回之後可以再獻


def test_the_book_survives_a_new_season_and_the_copy_does_not():
    c = _content()
    a, b, d = _member(c, "甲"), _member(c, "乙"), _member(c, "丙")
    own = _own(a)
    actions.offer(a, own.id)
    _done(a)
    for g, t in ((b, 2), (d, 3)):
        g = _again(c, g, NOW + t)
        g.choose(next(o.id for o in g.options() if o.id.startswith("zongmen:try:")))
        _done(g)
    d = _again(c, d, NOW + 4)
    entry = _book(d).entries[0]
    actions.learn(d, entry.id)
    d._reset_player_for_new_season(d.state.player.season_number + 1)
    assert d.state.player.sect == "baima"
    assert not any(i.name == "寒潭映月" for i in d.state.player.own_insights.values())
    assert _book(d).entries[0].status == "in"


def test_need_grows_with_the_sect_but_stays_capped():
    cfg = _content().config.zongmen
    assert B.need_for(1, cfg) == cfg.need_min
    assert B.need_for(9, cfg) == 4
    assert B.need_for(100, cfg) == cfg.need_max
    assert B.num(1) == "一" and B.num(12) == "十二" and B.num(21) == "二十一"


def test_bots_try_by_a_fixed_roll():
    c = _content()
    a = _member(c, "甲")
    own = _own(a)
    actions.offer(a, own.id)
    _done(a)
    b = _again(c, _member(c, "乙"), NOW + 2)
    opt = next(o for o in b.options() if o.id.startswith("zongmen:try:"))
    first = bots.score(b, opt)
    assert first in (None, bots.TRY_SCORE) and bots.score(b, opt) == first
