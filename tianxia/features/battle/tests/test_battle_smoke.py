"""全服決戰的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：這一包搬的是「看」那一半，所以走一次「看」——
開打的場景、戰局條、放手一搏的輸入框；打完那一回合收場，自己的戰報、江湖紀錄與「剛剛」那張卡片的戰局條補上來。測試內容（不到一秒）。"""
import pytest
from conftest import at
from test_engine import _install_battle_def_with_free_text, _join_and_open

from tianxia import battle_instance
from tianxia.core.registry import FEATURES


@pytest.mark.smoke
def test_a_fight_is_drawn_and_its_closing_report_is_filed(content, game):
    feature = next(f for f in FEATURES if f.name == "battle")
    assert feature.enabled(game) is False  # 測試內容沒有決戰
    definition = _install_battle_def_with_free_text(content)  # 一幕一回合
    assert feature.enabled(game) is True
    after = _join_and_open(content, game, definition)
    with at(game, after):
        assert definition.name in game.scene_text() and "第 1／1 回合" in game.scene_text()
        assert game.battle_on_screen() and game.battle_gauge() is not None and game.siege_banner() is None
        assert game.battle_free_text_prompt() == "放手一搏（20字內）"
        move = next(o.id for o in game.options() if o.id.startswith("battle:act:"))
        game.choose(move)
        game.world.mutate_battle(lambda b: battle_instance.submit_action(b, "機器人", "huang_hold"))
        game.options()  # 兩邊都送了：結算、收場，補到自己手上
    record = game.state.battles[0]
    assert record.kind == "showdown" and record.event == definition.name and record.battle_ref is not None
    assert any(e.title.startswith(definition.name) for e in game.state.journal)
    assert game.card_gauge() == record.gauge is not None
    assert not game.battle_on_screen() and game.battle_free_text_prompt() is None
