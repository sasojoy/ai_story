"""一條線的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路，真實內容）：開《賣兒契》，第一段是事件、人就在那裡，直接端出來；
開頭的卡跳出來、看過就清；「未了之事」的選項走 choose 掛鉤，標題是線的名字。標記 @pytest.mark.smoke 留著（每一包至少一條，test_test_for 守）。"""
import pytest
from jianfa_kit import jianfa_game, ready

from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_story_opens_a_real_line_and_takes_its_option_through_the_choose_hook():
    game = ready(jianfa_game(), side="guan", loc="runan_wilds", level=20)
    feature = next(f for f in FEATURES if f.name == "story")
    assert feature.enabled(game) is True
    assert not any(o.id.startswith("story:") for o in game.options())
    line = game.content.storylines["maier"]
    game._story_begin(line)
    assert game.state.pending_event == "maier_1"  # 第一段是事件、人就在那裡：直接端出來
    cards = game.story_card_view()
    assert [card["kind"] for card in cards] == ["start"] and cards[0]["title"] == line.title
    game.story_seen()
    assert game.story_card_view() == []
    outcome = feature.choose(game, "story", "maier")
    assert outcome is not None and outcome.title == line.title
    assert feature.choose(game, "talk", "maier") is None
