"""大勢人物的行動的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：week7 的官軍站在長社（三位官軍人物的地點），
按「護衛皇甫嵩」——這一包的 aid: 接走（標題「護衛・皇甫嵩」），站崗一班、記貢獻，選單上他那一顆換成灰的「護衛中」。"""
import pytest

from stances_kit import real_game
from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_a_soldier_guards_a_figure_and_the_button_turns_grey():
    feature = next(f for f in FEATURES if f.name == "figure_acts")
    g = real_game("week7", location="changshe")
    p = g.state.player
    assert feature.enabled(g) and feature.prefix == ("aid", "plan") and feature.bot_always == ("aid:",)
    assert "aid:guard:huangfusong" in {o.id for o in g.options(odds=False) if o.enabled}
    stamina = p.stamina
    msgs = g.choose("aid:guard:huangfusong")
    assert msgs[0].startswith("你在皇甫嵩身邊站崗") and p.stamina == stamina - g.content.config.figure_aid.guard_stamina
    assert g.state.journal[0].title == "護衛・皇甫嵩"
    assert not {o.id: o for o in g.options(odds=False)}["aid:guard:huangfusong"].enabled
