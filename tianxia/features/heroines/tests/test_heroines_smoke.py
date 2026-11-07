"""女子與隱線的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：測試內容沒有女子時一個選項都不給；
正式內容裡葉三娘收在留得下她的結局之後，出現在孟津渡。"""
import pytest
from jianfa_kit import jianfa_game, ready

from tianxia.core.registry import FEATURES
from tianxia.state import StoryProgress


@pytest.mark.smoke
def test_heroines_is_registered_and_quiet_without_heroines(game):
    feature = next(f for f in FEATURES if f.name == "heroines")
    assert feature.enabled(game) is False
    assert not any(o.id.startswith("heroines:") for o in game.options())


@pytest.mark.smoke
def test_she_appears_at_the_ford_after_her_story():
    game = ready(jianfa_game(), side="guan", loc="mengjin_ford")
    assert "yesanniang" not in game._figures_here()
    game.state.player.storylines["yesanniang"] = StoryProgress(line="yesanniang", ending="shao")
    assert "yesanniang" in game._figures_here()
