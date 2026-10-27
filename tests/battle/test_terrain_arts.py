"""武學隨地理環境（地利；第 36 項，計畫 docs/superpowers/plans/2026-10-18-武學隨地理環境.md）：一般的仗裡，本人與出戰同伴身上的
武學、內功一門一門比這一地最濃的意境——同一路 ×1.10、被它剋 ×0.95【預設】；部下不吃，決戰那一類不吃，江湖水漲浮難度不吃；
勝算照算，戰報一句、輿圖一行、玩法說明一句；開關關著一個字都不變。測試內容（湖邊悟得到水、風）自己打開兩個開關。"""
from __future__ import annotations

import random
import re

import pytest
import webharness
from conftest import real_content

from tianxia import atlas, battlelog, encounter, howto, team, terrain
from tianxia.content import check_terrain_arts
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

WATER_LINE = "此地水氣最濃：柔勁的功夫在這裡得勢，剛猛的施展不開。"


def _on(content):
    content.config.train_event_chance = 0.0
    content.config.insight_strong.enabled = True
    content.config.terrain_arts.enabled = True
    content.locations["lake"].insight_strong = "shui"  # 湖邊：水（柔）
    content.locations["town"].insight_strong = "huo"  # 小鎮：火（剛）
    return content


def _lake(content, world, wugong="sword", neigong="breath"):
    """湖邊的沈浪：流雲劍（柔）配吐納法（陰，跟水不相干）。"""
    g = Game.new(_on(content), "沈浪", rng=random.Random(0), world=world)
    p = g.state.player
    p.location, p.member.wugong_id, p.member.neigong_id = "lake", wugong, neigong
    return g


def _thug(g):
    return g.content.squads["thug"]


def _power(g, **kw):
    return team.power_vs(g.state, g.content, g.world, _thug(g), **kw)


def _strong(g, insight="shui"):
    return g.content.insights[insight]


# ── 純規則 ─────────────────────────────────────────────


def test_the_factor_is_match_clash_or_one(content):
    _on(content)
    water = content.insights["shui"]
    assert terrain.factor("柔", content, water) == pytest.approx(1.10)  # 同一路
    assert terrain.factor("剛", content, water) == pytest.approx(0.95)  # 水剋剛
    assert terrain.factor("快", content, water) == 1.0
    assert terrain.factor(None, content, water) == 1.0
    assert terrain.factor("柔", content, None) == 1.0


def test_the_strongest_here_needs_both_switches_and_a_place(content, world):
    g = _lake(content, world)
    assert terrain.here(g.state, g.content).id == "shui"
    assert terrain.strong_at(g.content, "town").id == "huo"
    content.config.terrain_arts.enabled = False
    assert terrain.here(g.state, g.content) is None
    content.config.terrain_arts.enabled = True
    content.config.insight_strong.enabled = False
    assert terrain.here(g.state, g.content) is None
    content.config.insight_strong.enabled = True
    content.locations["lake"].prologue_only = True  # 序章專屬的地方沒有地利
    assert terrain.strong_at(g.content, "lake") is None


def test_on_the_road_there_is_no_terrain(content, world):
    from tianxia.state import Journey

    g = _lake(content, world)
    g.state.player.journey = Journey(mode="walk", path=["town"], arrive_at=[99.0])
    assert terrain.here(g.state, g.content) is None


def test_the_note_prefers_match_then_clash_then_a_companion(content):
    _on(content)
    water = content.insights["shui"]
    lines = content.config.terrain_arts.lines
    assert terrain.note(content, water, ["剛", "柔"], []) == [lines["match:shui"]]  # 一門對上、一門被剋：寫對上的
    assert terrain.note(content, water, ["剛", None], [("韓鐵", ["柔", None])]) == [lines["clash:shui"]]  # 本人先於同伴
    assert terrain.note(content, water, ["快", "陰"], [("韓鐵", ["柔", None])]) == [lines["mate_match"].format(name="韓鐵")]
    assert terrain.note(content, water, ["快", "陰"], [("韓鐵", ["剛", None])]) == []  # 同伴被剋不寫
    assert terrain.note(content, None, ["柔"], []) == []


def test_the_lines_have_no_numbers(content):
    assert not any(re.search(r"[0-9０-９]", text) for text in content.config.terrain_arts.lines.values())


# ── 威力：只走 _styled_fighters ───────────────────────────


def test_a_matching_art_is_ten_percent_stronger(content, world):
    g = _lake(content, world, wugong="sword")  # 柔
    assert _power(g) == pytest.approx(_power(g, terrain=False) * 1.10)


def test_a_countered_art_is_five_percent_weaker(content, world):
    g = _lake(content, world, wugong="fist")  # 剛：被水剋
    assert _power(g) == pytest.approx(_power(g, terrain=False) * 0.95)


def test_an_unrelated_art_does_not_change(content, world):
    g = _lake(content, world, wugong="step")  # 快
    assert _power(g) == pytest.approx(_power(g, terrain=False))


def test_a_matching_neigong_only_scales_the_neigong(content, world):
    g = _lake(content, world, wugong="step", neigong="basic_breath")  # 快的武學、柔的內功
    s, c = g.state, g.content
    # 武學重構：基礎吐納兼容並蓄，屬性照槽裡最強那一格——裝一個水（柔）才是柔的內功
    s.player.insights = sorted({*s.player.insights, "shui"})
    s.player.art_slots["basic_breath"] = ["shui", None]
    arts = team.team_arts(s, c, g.world)
    members, conditions, boosts = team._styled_fighters(s, c, g.world, arts, _thug(g), terrain=False)
    want = encounter.member_power(members[0], arts, "剛", conditions[0], boosts[0].model_copy(update={"inner_scale": 1.10}))
    assert _power(g) == pytest.approx(want)
    assert _power(g, terrain=False) < want < _power(g, terrain=False) * 1.10


def test_companions_take_it_one_by_one(content, world):
    g = _lake(content, world, wugong="fist")  # 本人剛：被剋
    g.world.update_companion("mate", lambda p: setattr(p, "wugong_id", "sword"))  # 同伴柔：對上
    g.state.player.team = ["mate"]
    s, c = g.state, g.content
    arts = team.team_arts(s, c, g.world)
    members, conditions, boosts = team._styled_fighters(s, c, g.world, arts, _thug(g), terrain=False)
    me, mate = (encounter.member_power(m, arts, "剛", k, b) for m, k, b in zip(members, conditions, boosts, strict=True))
    assert _power(g) == pytest.approx(me * 0.95 + mate * 1.10)


@pytest.mark.slow
def test_followers_do_not_take_it():
    c = real_content("week7")
    c.config.auto_open_first_season = True
    fid, follower = next(iter(c.followers.items()))
    attribute = c.skills[follower.wugong].attribute
    place = next(loc.id for loc in c.locations.values() if loc.insight_strong
                 and c.insights[loc.insight_strong].attribute == attribute)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    p = game.state.player
    p.location, p.followers, p.member.wugong_id = place, [fid], follower.wugong
    arts = team.team_arts(game.state, c, game.world)
    squad = next(iter(c.squads.values()))
    _, _, boosts = team._styled_fighters(game.state, c, game.world, arts, squad)
    assert len(boosts) == 2 and team.follower_rows(game.state, c)
    assert boosts[0].outer_scale == pytest.approx(c.config.terrain_arts.match)  # 本人同一路
    assert boosts[1].outer_scale == 1.0 and boosts[1].inner_scale == 1.0  # 部下同一路也不吃


def test_another_place_can_be_asked_for(content, world):
    g = _lake(content, world, wugong="fist")  # 剛：湖邊被剋、小鎮對上
    assert _power(g, at="town") == pytest.approx(_power(g, terrain=False) * 1.10)
    assert _power(g) == pytest.approx(_power(g, terrain=False) * 0.95)


def test_the_odds_and_the_fight_use_the_same_power(content, world, monkeypatch):
    g = _lake(content, world, wugong="sword")
    seen: dict[str, float] = {}
    real_word, real_resolve = team.odds_word, encounter.resolve_encounter
    monkeypatch.setattr(team, "odds_word", lambda power, *a, **k: seen.setdefault("odds", power) and real_word(power, *a, **k))
    monkeypatch.setattr(encounter, "resolve_encounter",
                        lambda power, *a, **k: seen.setdefault("fight", power) and real_resolve(power, *a, **k))
    g.odds("thug")
    team.fight(g.state, g.content, g.world, "thug", random.Random(0))
    assert seen["odds"] == pytest.approx(seen["fight"]) == pytest.approx(_power(g))
    assert seen["fight"] == pytest.approx(_power(g, terrain=False) * 1.10)


def test_the_rise_floats_without_the_terrain(content, world, monkeypatch):
    """江湖水漲浮難度用的全隊威力不含地利（不然地利被浮上去的難度吃掉）。"""
    g = _lake(content, world, wugong="sword")
    content.config.rise.enabled = True
    asked: list[dict] = []
    real = team.power_vs
    monkeypatch.setattr(team, "power_vs", lambda *a, **k: asked.append(k) or real(*a, **k))
    g._story_squad(g.content.squads["boss"])
    assert asked and all(k.get("fresh") and k.get("terrain") is False for k in asked)


@pytest.mark.slow
def test_the_figure_rise_floats_without_the_terrain(monkeypatch):
    c = real_content("week7")
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    asked: list[dict] = []
    real = team.power_vs
    monkeypatch.setattr(team, "power_vs", lambda *a, **k: asked.append(k) or real(*a, **k))
    game._figure_squad(next(iter(c.figures)))
    assert asked and all(k.get("fresh") and k.get("terrain") is False for k in asked)


def test_the_big_battle_power_has_no_terrain(content, world):
    g = _lake(content, world, wugong="sword")
    on = g._battle_power()
    content.config.terrain_arts.enabled = False
    assert g._battle_power() == pytest.approx(on)


def test_switched_off_nothing_changes(content, world):
    g = _lake(content, world, wugong="sword")
    content.config.terrain_arts.enabled = False
    assert _power(g) == pytest.approx(_power(g, terrain=False))
    content.config.terrain_arts.enabled = True
    content.config.insight_strong.enabled = False
    assert _power(g) == pytest.approx(_power(g, terrain=False))


# ── 戰報那一句 ─────────────────────────────────────────


def _train(g):
    g.choose("act:train")
    s = g.state
    return next(r for r in s.battles if r.id == s.battle_card)


def test_the_report_says_the_terrain_helped(content, world):
    g = _lake(content, world, wugong="sword")
    line = content.config.terrain_arts.lines["match:shui"]
    record = _train(g)
    assert line in record.notes and line in battlelog.card_text(record)


def test_the_report_says_the_terrain_hurt(content, world):
    g = _lake(content, world, wugong="fist")
    assert content.config.terrain_arts.lines["clash:shui"] in _train(g).notes


def test_the_report_names_the_companion(content, world):
    g = _lake(content, world, wugong="step")
    g.world.update_companion("mate", lambda p: setattr(p, "wugong_id", "sword"))
    g.state.player.team = ["mate"]
    assert content.config.terrain_arts.lines["mate_match"].format(name="韓鐵") in _train(g).notes


def _all_lines(content):
    lines = content.config.terrain_arts.lines
    return set(lines.values()) | {lines["mate_match"].format(name="韓鐵")}


def test_the_report_is_quiet_when_unrelated(content, world):
    g = _lake(content, world, wugong="step")
    assert not _all_lines(content) & set(_train(g).notes)


def test_the_report_is_quiet_when_off(content, world):
    g = _lake(content, world, wugong="sword")
    content.config.terrain_arts.enabled = False
    assert not _all_lines(content) & set(_train(g).notes)


def test_a_story_fight_writes_it_too(content, world):
    g = _lake(content, world, wugong="sword")
    event = g.content.events["duel"]
    g._event_battle(event, event.choices[0])
    record = next(r for r in g.state.battles if r.id == g.state.battle_card)
    assert content.config.terrain_arts.lines["match:shui"] in record.notes


# ── 輿圖 ───────────────────────────────────────────────


def test_the_old_detail_panel_has_a_terrain_line(content, world):
    g = _lake(content, world)
    assert atlas.TERRAIN_LABEL + WATER_LINE in g.place_detail("lake")
    assert "此地火氣最濃：剛猛的功夫在這裡得勢，柔勁的施展不開。" in g.place_detail("town")
    content.config.terrain_arts.enabled = False
    assert "地利" not in g.place_detail("lake")


def test_the_detail_panel_odds_follow_the_place(content, world, monkeypatch):
    g = _lake(content, world)
    g.state.player.location = "town"  # 人在小鎮，看湖邊（水寇小隊站在那裡）
    asked: list[str | None] = []
    real = team.estimate
    monkeypatch.setattr(team, "estimate", lambda *a, **k: asked.append(k.get("at")) or real(*a, **k))
    g.place_detail("lake")
    assert asked and set(asked) == {"lake"}


@pytest.mark.slow
def test_the_map_lists_the_terrain_line_per_place():
    c = real_content("week7")
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    places = {p["id"]: p for p in game.map_base()["places"]}
    for loc_id, p in places.items():
        assert p["terrain_arts"] == terrain.place_line(c, loc_id)
    fire = next(i for i, p in places.items() if p["strong"] == "huo")
    assert places[fire]["terrain_arts"] == "此地火氣最濃：剛猛的功夫在這裡得勢，柔勁的施展不開。"
    c.config.terrain_arts.enabled = False
    assert all(p["terrain_arts"] == "" for p in game.map_base()["places"])


@pytest.mark.slow
def test_the_map_odds_follow_each_place_and_ask_once_per_terrain(monkeypatch):
    c = real_content("week7")
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.state.player.faction = "guan"
    asked: list[tuple[str, str | None]] = []
    real = game.odds
    game.odds = lambda sid, at=None: asked.append((sid, at)) or real(sid, at=at)
    game.map_state()
    assert asked and all(at is not None for _, at in asked)
    keys = [(sid, terrain.strong_at(c, at).id if terrain.strong_at(c, at) else None) for sid, at in asked]
    assert len(keys) == len(set(keys))  # 同一路對手、同一種地利只算一次


@pytest.mark.slow
@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_map_drawer_shows_the_terrain_section():
    import test_map_web

    game = test_map_web._game()
    fire = next(p["id"] for p in game.map_base()["places"] if p["strong"] == "huo")
    out = test_map_web.run(game, f'return H.placeCard(H.S.mapBase, H.S.mapState, "{fire}");')
    # 那一句包成不折行的小段（FB-470，tests/test_fb470_471_terrain_wrap.py），字照舊
    assert "<h4>地利</h4>此地火氣最濃：剛猛的功夫在這裡得勢，柔勁的施展不開。" in re.sub(r'</?span[^>]*>', "", out)
    game.content.config.terrain_arts.enabled = False
    assert "<h4>地利</h4>" not in test_map_web.run(game, f'return H.placeCard(H.S.mapBase, H.S.mapState, "{fire}");')


# ── 玩法說明與內容檢查 ─────────────────────────────────


def test_the_howto_says_it_only_when_on(content, world):
    g = _lake(content, world)
    assert howto.TERRAIN_HOWTO in howto.page(content, g.state.world, recruitable=False)
    content.config.terrain_arts.enabled = False
    assert howto.TERRAIN_HOWTO not in howto.page(content, g.state.world, recruitable=False)


def test_the_content_check_wants_lines_for_every_strongest_insight():
    c = real_content()
    errors: list[str] = []

    def need(ok, msg):
        if not ok:
            errors.append(msg)

    check_terrain_arts(c, need)
    assert errors == []
    del c.config.terrain_arts.lines["clash:huo"]
    check_terrain_arts(c, need)
    assert errors and "clash:huo" in errors[0]
