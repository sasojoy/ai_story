"""契約測試（tests/core/test_contract_features.py）把傳承擺進「有選項」的局面：每擺好一種 yield 一個名字。"""
from legacy_kit import give_god


def stages(game):
    game.content.config.legacy.enabled = True
    give_god(game, "寒江獨照")
    yield "身上有一份神品"
