"""bout 這一包的測試，從 tests/core/test_engine.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import re
import pytest
from conftest import FixedRandom, walk_to

pytestmark = pytest.mark.whole_content


def test_an_event_battle_is_played_with_the_fighters_from_before_its_rewards(game):
    """劇情戰的回合照開打時的陣容與身法演（計畫三 Task 1 審查修正）：打贏的效果（真實內容的 wolves 打贏身法 +1）
    不能回頭改寫這一場——身法 5 比水寇小隊的 5.25 慢，是對手先出手；效果加了身法也一樣。學到的武學同理：
    本人空著手上陣、打贏才學會（配上身）的追風步，不會出現在這一場的回合裡，出手的只有帶著長拳的韓鐵。"""
    duel = game.content.events["duel"].choices[0]
    duel.combat = "thug"  # 換成打得贏的水寇小隊（難度 5：身法 5＋5÷20＝5.25）
    duel.effect.stats = {"agi": 3}
    duel.effect.learn_skills = ["step"]
    game.state.player.team = ["mate"]
    game.world.update_companion("mate", lambda p: setattr(p, "wugong_id", "fist"))
    walk_to(game, "lake")
    game.choose("act:socialize")
    assert game.state.pending_event == "duel"
    game.rng = FixedRandom(1.0)  # 最佳運氣：穩穩打贏
    game.choose("choice:0")
    record = game.state.battles[0]
    p = game.state.player
    assert record.tier in ("大勝", "險勝") and (p.stats["agi"], p.member.wugong_id) == (8, "step")  # 效果真的生效了
    assert record.rounds and all(re.match(f"第{i}回合　[^：]*：水寇小隊", line) for i, line in enumerate(record.rounds, 1))  # 回合前面寫兩邊出的招
    assert all("韓鐵以【長拳】" in line and "追風步" not in line and "沈浪" not in line for line in record.rounds)
