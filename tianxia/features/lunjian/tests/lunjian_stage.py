"""契約測試（tests/core/test_contract_features.py）把門派論劍擺進「有選項」的局面：每擺好一種 yield 一個名字。"""


def stages(game):
    yield "平常"
    if not game.content.config.lunjian.enabled:
        return
    game.state.player.sect = game.state.player.sect or next(iter(game.content.sects), None)
    yield "拜了門"
    from tianxia.features.lunjian import actions

    b = actions.bag(game, make=True)
    b.boxes, b.picks = 1, 1
    yield "有賞"
