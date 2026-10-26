"""鑄譜線索拆三片（素材與經濟設計第三節，企劃者 2026-10-15）：神器配方的線索拆成種類（或防具）、主料、輔料三片，照天機分給各家
鐵匠鋪（同一家講完之前不重複），說書、殘譜也帶得到；三片都聽過，鑄譜那一條就完整。照這一季開季時蓋的章（forge_split_clues）。"""
from __future__ import annotations

import random

from conftest import real_content
from jianfa_kit import classic_explore  # 殘譜在探索三選一的幾顆裡擲（減法季探索一顆開著時出門一趟擲一次，tests/test_explore_one.py）
from tianxia import forge_secrets
from tianxia.engine import Game
from tianxia.world_state import fresh_season


def _game(c, name="鑄者"):
    g = Game.new(c, name, rng=random.Random(1))
    g.state.world = fresh_season(c)
    return g


def _divine(c, season):
    return [r for r in forge_secrets.active(c, season.tianji, season) if r.divine]


def test_every_piece_is_known_by_some_smith():
    c = classic_explore(real_content("week7"))
    season = fresh_season(c)
    known = {item for town in forge_secrets.towns(c) for item in forge_secrets.smith_items(c, season, season.tianji, town)}
    assert {(r.id, p) for r in _divine(c, season) for p in forge_secrets.PIECES} <= known


def test_a_smith_never_repeats_until_it_has_told_everything():
    c = classic_explore(real_content("week7"))
    g = _game(c)
    town = forge_secrets.towns(c)[0]
    g.state.player.location = town
    items = forge_secrets.smith_items(c, g.state.world, g.state.world.tianji, town)
    assert len(items) >= 2
    told = [forge_secrets.hear_smith(g.state, c, g.state.world.tianji) for _ in range(len(items) + 2)]
    assert all(told[: len(items)]) and len(set(told[: len(items)])) == len(items)
    assert told[len(items):] == [None, None]


def test_walking_the_towns_completes_every_divine_recipe():
    c = classic_explore(real_content("week7"))
    g = _game(c)
    tianji = g.state.world.tianji
    for town in forge_secrets.towns(c):
        g.state.player.location = town
        while forge_secrets.hear_smith(g.state, c, tianji):
            pass
    book = forge_secrets.manual(g.state, tianji)
    for r in _divine(c, g.state.world):
        assert sorted(book.pieces.get(r.id, [])) == list(forge_secrets.PIECES), r.id


def test_three_pieces_make_the_book_line_complete():
    c = classic_explore(real_content("week7"))
    g = _game(c)
    sword = next(r for r in _divine(c, g.state.world) if r.kind == "劍")
    # 神器配方改用四階（正式季整合 5.5）：鑄譜那一行寫「快四」
    assert forge_secrets.piece_line(c, sword, [forge_secrets.MAIN]) == "？：快四＋？"
    assert forge_secrets.piece_line(c, sword, list(forge_secrets.PIECES)) == "劍：快四＋柔四"
    book = forge_secrets.manual(g.state, g.state.world.tianji)
    book.pieces[sword.id] = [forge_secrets.MAIN, forge_secrets.KIND]
    row = next(r for r in forge_secrets.view(g.state, c, g.world) if r["recipe"] and r["recipe"].endswith("＋？"))
    assert row["recipe"] == "劍：快四＋？" and row["solved"] is None
    assert row["clues"] == [forge_secrets.piece_text(c, sword, forge_secrets.KIND), forge_secrets.piece_text(c, sword, forge_secrets.MAIN)]


def test_the_alias_does_not_give_away_the_kind():
    c = real_content()
    for r in c.forge_secrets.values():
        if r.divine:
            alias = forge_secrets.alias(r)
            assert alias and alias != r.name and forge_secrets.piece_text(c, r, forge_secrets.MAIN).startswith(f"『{alias}』")


def test_fb269_a_framed_piece_quotes_the_alias_inside_with_double_corners():
    """FB-269：鐵匠、說書、殘譜的框是「{clue}」，片子裡配方的號用『』（引號裡再引用），畫面上不會疊成「「。"""
    c = classic_explore(real_content("week7"))
    rule = c.config.forge_secrets
    for r in c.forge_secrets.values():
        if r.divine:
            for piece in forge_secrets.PIECES:
                for frame in (rule.smith_frame, rule.smith_frame_free, rule.tale_frame, rule.scrap_frame):
                    line = frame.format(clue=forge_secrets.piece_text(c, r, piece))
                    assert "「「" not in line and "」」" not in line and f"『{forge_secrets.alias(r)}』" in line


def test_tales_and_scraps_carry_pieces_too():
    c = classic_explore(real_content("week7"))
    g = _game(c)
    tianji = g.state.world.tianji
    texts = {forge_secrets.hear(g.state, c, tianji, forge_secrets.SCRAP, f"seed{i}") for i in range(60)}
    book = forge_secrets.manual(g.state, tianji)
    assert sum(len(v) for v in book.pieces.values()) > 0
    assert any(t and t.startswith("『") for t in texts)  # 片子的句子以配方的號開頭（FB-269 起用『』）


def test_divine_verses_are_not_used_once_split():
    c = classic_explore(real_content("week7"))
    g = _game(c)
    tianji = g.state.world.tianji
    divine = {r.id for r in _divine(c, g.state.world)}
    for i in range(80):
        forge_secrets.hear(g.state, c, tianji, forge_secrets.TALE, f"tale{i}")
    book = forge_secrets.manual(g.state, tianji)
    assert not divine & set(book.heard)


def _explorer(scrap_every_mode=True):
    """潁水河畔（野外、悟得到水）的人，兩種殘譜都一定撿到（scrap_chance 1）。"""
    from tianxia.sqlite_world import open_world

    c = classic_explore(real_content("week7"))
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.duel.explore_chance = 0.0
    c.config.explore_modes.encounter_chance = 0.0
    c.config.secrets.scrap_chance = 1.0
    c.config.forge_secrets.scrap_chance = 1.0
    c.config.forge_secrets.scrap_every_mode = scrap_every_mode
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.location, p.stamina = "yingshui", float(c.config.stamina_max)
    p.tutorial_step = len(c.tutorial.steps)
    return game


def _scraps(msgs, c):
    frames = (c.config.secrets.scrap_frame.split("{")[0], c.config.forge_secrets.scrap_frame.split("{")[0])
    return [m for m in msgs if m.startswith(frames)]


def test_scraps_turn_up_in_all_three_ways_of_exploring():
    """殘譜（武學口訣、半張鑄譜）找素材、找事件、靜心感悟都擲（素材與經濟設計第三節第 2 條）。"""
    for mode in ("explore:gather", "explore:seek", "explore:sense"):
        game = _explorer()
        msgs = game.choose(mode)
        assert len(_scraps(msgs, game.content)) == 2, (mode, msgs)


def test_with_the_switch_off_only_seeking_finds_scraps():
    for mode, want in (("explore:gather", 0), ("explore:seek", 2), ("explore:sense", 0)):
        game = _explorer(scrap_every_mode=False)
        assert len(_scraps(game.choose(mode), game.content)) == want, mode


def test_an_unstamped_season_keeps_the_verses():
    c = classic_explore(real_content("week7"))
    g = _game(c)
    g.state.world.forge_split_clues = False
    town = forge_secrets.towns(c)[0]
    season = g.state.world
    assert forge_secrets.smith_items(c, season, season.tianji, town) == [
        (forge_secrets.smith_clue(c, season.tianji, town, season).id, forge_secrets.VERSE)]
    g.state.player.location = town
    recipe = forge_secrets.smith_clue(c, season.tianji, town, season)
    assert forge_secrets.hear_smith(g.state, c, season.tianji) == recipe.clues[forge_secrets.SMITH]
    assert forge_secrets.hear_smith(g.state, c, season.tianji) is None
