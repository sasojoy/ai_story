"""契約測試（tests/core/test_contract_features.py）把傳承擺進「有選項」的局面：每擺好一種 yield 一個名字。

三種局面一路接著擺（同一個 game）：身上有一份神品 → 換季後有候選（開季準備卡的識海那一步，prep 給封進／不帶）→
封著、條件到了（options 給「解封」）。"""
from legacy_kit import give_god

from tianxia.features.legacy import actions


def stages(game):
    cfg = game.content.config.legacy
    cfg.enabled = True
    give_god(game, "寒江獨照")
    yield "身上有一份神品"
    # 換季：on_season_start 把神品留成候選（開季準備卡的識海那一步；配比那一步不在這一包）
    game._reset_player_for_new_season(game.state.player.season_number + 1)
    yield "換季後有候選"
    # 封第一份，再把三道封印（一天、15 級、心得）擺到過了：解封那一顆按得下去
    actions.act(game, "seal:0")
    p = game.state.player
    p.member.level = max(p.member.level, cfg.shihai_level)
    p.stats["xinde"] = max(p.stats.get("xinde", 0), cfg.shihai_xinde + 30)
    game.state.world.time = max(game.state.world.time, cfg.shihai_after)
    yield "封著、條件到了"
