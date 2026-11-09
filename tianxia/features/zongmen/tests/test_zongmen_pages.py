"""師門武譜第三批（設計稿 v6 第一根柱子，Joy 2026-11-08「不錯，按照設計稿動工」）：獻武學（自創、合成、練成絕學的）、
學到的低一品、下一季全服登記沒了照抄的那一份再登記、學過的人重學打折；截殺打贏別門親傳撿殘頁、照殘頁偷學一份下品的。"""
from __future__ import annotations

from test_zongmen_book import NOW, _again, _book, _content, _done, _member, _own

from tianxia import team
from tianxia.engine import Game
from tianxia.features.zongmen import actions, book as B


def _art(g: Game, name="寒江劍", quality="絕學"):
    """一門全服登記的武學（合成的樣子），配到 g 身上、品質是 quality。"""
    base = team.resolve_art("chanzuo_tiaoxi", g.content, g.world)
    art = base.model_copy(update={"id": name, "name": name, "kind": "武學", "origin": "fused", "creator": g.state.player.name,
                                  "creator_shown": g.state.player.name, "quality": "上品"})
    assert g.world.claim_skill_name(art)
    g.state.player.arts.append(art.id)
    g.state.player.art_quality[art.id] = quality
    return art


def _enter(c, giver, offer_id, voters):
    assert actions.offer(giver, offer_id)[0].startswith("你把")
    _done(giver)
    for i, g in enumerate(voters):
        g = _again(c, g, NOW + 10 + i)
        g.choose(next(o.id for o in g.options() if o.id.startswith("zongmen:try:")))
        _done(g)


def test_an_art_goes_into_the_book_and_is_learned_one_grade_lower():
    c = _content()
    a, b, d = _member(c, "甲"), _member(c, "乙"), _member(c, "丙")
    art = _art(a)
    assert (actions.ART + art.id, "武學・寒江劍（絕學）") in actions.offerable(a)
    assert actions.offer(a, actions.ART + "chanzuo_tiaoxi") == [B.NOT_YOURS + "。"]  # 內容寫死的不收
    _enter(c, a, actions.ART + art.id, [b, d])
    entry = _book(a).entries[0]
    assert entry.status == "in" and entry.art.name == "寒江劍" and entry.art_quality == "絕學"
    d = _again(c, d, NOW + 20)
    row = actions.view(d)["entries"][0]
    assert row["kind"] == "武學" and row["fx"] == "學到的是上品"
    assert actions.learn(d, entry.id) == [B.LEARNED.format(sect="白馬寺", num="一", name="寒江劍")]
    assert art.id in d.state.player.arts and team.art_quality(d.state, art) == "上品"
    assert actions.learn(d, entry.id) == [B.HAVE + "。"]
    assert "寒江劍" not in {n for _, n in actions.offerable(d)}  # 學來的那份不能再獻（譜上已經有）


def test_next_season_the_art_is_registered_again_and_relearning_costs_half():
    c = _content()
    a, b, d = _member(c, "甲"), _member(c, "乙"), _member(c, "丙")
    art = _art(a)
    _enter(c, a, actions.ART + art.id, [b, d])
    d = _again(c, d, NOW + 20)
    entry_id = _book(d).entries[0].id
    actions.learn(d, entry_id)
    d.world.mutate(lambda shared: None)
    d._reset_player_for_new_season(d.state.player.season_number + 1)
    assert art.id not in d.state.player.arts
    d.state.player.stats["xinde"] = 100
    d.state.player.location, d.state.player.journey = "baima_temple", None
    entry = _book(d).entries[0]
    assert B.learn_price(entry, d.state.player.name, c.config.zongmen) == c.config.zongmen.learn_xinde // 2
    d.world.get_skill = lambda name: None  # 下一季全服登記沒有這一門
    claimed = []
    d.world.claim_skill_name = lambda a: claimed.append(a.name) or True
    assert actions.learn(d, entry_id)[0].startswith("你學會了")
    assert claimed == ["寒江劍"] and d.state.player.stats["xinde"] == 100 - c.config.zongmen.learn_xinde // 2


def test_an_outsider_who_beats_an_inner_disciple_can_pick_up_a_page():
    c = _content()
    c.config.zongmen.page_chance = 1.0
    a, b, d = _member(c, "甲"), _member(c, "乙"), _member(c, "丙")
    own = _own(a)
    _enter(c, a, own.id, [b, d])
    a = _again(c, a, NOW + 20)
    assert B.is_inner(a.state.player, _book(a), c.config.zongmen)  # 有一式入譜刻名
    b = _again(c, b, NOW + 21)
    assert not B.is_inner(b.state.player, _book(b), c.config.zongmen)
    assert actions.raid_win(b, "甲") == []  # 同門不撿
    thief = Game.new(c, "丁")
    thief.sync(NOW + 22)
    thief.state.player.stats["xinde"] = 200
    assert actions.raid_win(thief, "乙") == []  # 不是親傳
    assert actions.raid_win(thief, "甲") == []  # 撿到了：寫自己那一則紀錄，不混進懸賞榜
    assert "殘頁" in thief.state.model_dump_json()
    entry = _book(thief).entries[0]
    assert "丁" in entry.pages
    view = actions.view(thief)
    assert view["sect"] is None and view["pages"][0]["name"] == "寒潭映月"
    assert actions.raid_win(thief, "甲") == []  # 一式只撿一張
    assert _book(thief).entries[0].pages == ["丁"]
    got = actions.page_learn(thief, "baima", entry.id)
    assert got == [B.PAGE_LEARNED.format(sect="白馬寺", num="一", name="寒潭映月")]
    learned = next(i for i in thief.state.player.own_insights.values() if i.name == "寒潭映月")
    assert thief.state.player.insight_fx[learned.id].quality == B.PAGE_QUALITY
    assert _book(thief).entries[0].pages == [] and actions.view(thief) is None
    assert actions.page_learn(thief, "baima", entry.id) == [B.GONE]


def test_no_page_when_the_switch_is_off_or_the_roll_misses():
    c = _content()
    c.config.zongmen.page_chance = 0.0
    a, b, d = _member(c, "甲"), _member(c, "乙"), _member(c, "丙")
    _enter(c, a, _own(a).id, [b, d])
    thief = Game.new(c, "丁")
    thief.sync(NOW + 22)
    actions.raid_win(thief, "甲")
    assert _book(thief).entries[0].pages == []
    c.config.zongmen.page_chance, c.config.zongmen.enabled = 1.0, False
    actions.raid_win(thief, "甲")
    assert _book(thief).entries[0].pages == []
