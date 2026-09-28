from tianxia.bot import spend_xinde


def test_bot_spends_xinde_on_the_cheapest_upgrade_first(game):
    p = game.state.player
    p.stats["xinde"] = 100
    spend_xinde(game)
    # 三門都在第一成（各 20）→ 依序各升一成；剩 40 剛好把排在最前面的長拳再升到第三成
    assert p.skills == {"fist": 3, "family": 2}
    assert p.members["mate"].innate_level == 2
    assert p.stats["xinde"] == 0


def test_bot_keeps_xinde_it_cannot_spend(game):
    p = game.state.player
    p.stats["xinde"] = 19
    spend_xinde(game)
    assert p.skills == {"fist": 1, "family": 1}
    assert p.stats["xinde"] == 19


def test_bot_skips_arts_at_tenth_level(game):
    p = game.state.player
    p.skills["fist"] = 10
    p.stats["xinde"] = 20
    spend_xinde(game)
    assert p.skills == {"fist": 10, "family": 2}
