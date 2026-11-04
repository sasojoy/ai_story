"""傳承的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：關著不出聲；開著時換季結算三項、識海帶一份神品過去、解封。"""
import pytest
from legacy_kit import god_game, next_season

from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_legacy_is_registered_and_quiet_while_closed(game):
    feature = next(f for f in FEATURES if f.name == "legacy")
    assert feature.enabled(game) is False
    assert not any(o.id.startswith("legacy:") for o in game.options())
    assert "legacy" not in game.state.player.model_dump()  # 存檔一個鍵都不多


@pytest.mark.smoke
def test_keep_a_god_insight_through_the_season_change_and_unseal_it():
    game, iid = god_game()
    game.choose(f"legacy:keep:{iid}")
    next_season(game)
    p = game.state.player
    assert p.legacy.sealed is not None and not p.own_insights
    p.member.level, p.stats["xinde"] = 15, 500
    game.state.world.time = game.content.config.legacy.shihai_after
    msgs = game.choose("legacy:open")
    assert any("識海解封" in m for m in msgs)
    assert p.legacy.sealed is None and len(p.own_insights) == 1
