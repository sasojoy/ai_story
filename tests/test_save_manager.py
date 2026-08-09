import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.game_engine import GameEngine
from src.save_manager import save_game, load_game, list_saves, get_latest_save_slot_id, get_save_path


class TestSaveManager(unittest.TestCase):

    def setUp(self):
        self.engine = GameEngine()
        self.test_slot = 99  # 使用測試專用 Slot

    def tearDown(self):
        # 測試清理
        test_path = get_save_path(self.test_slot)
        if os.path.exists(test_path):
            os.remove(test_path)

    def test_save_and_load_full_restoration(self):
        # 1. 設置自訂變更狀態
        self.engine.set_player_name("楚留香測試")
        self.engine.player_state.hp = 85
        self.engine.player_state.gold = 350
        self.engine.player_state.stamina = 70
        self.engine.player_state.charm = 25
        self.engine.player_state.cultivation_arts.append("合歡玄天功")

        self.engine.game_turn = 5
        self.engine.main_quest_summary = "已加入血衣樓，準備反殺正派盟主"
        self.engine.move_to_location("亂葬崗")
        self.engine.factions["血衣樓"] = 80
        self.engine.world_flags["met_she_maiden"] = True

        if "合歡宗聖女" in self.engine.agents:
            agent = self.engine.agents["合歡宗聖女"]
            agent.profile.intimacy = 65
            agent.history = [
                {"role": "user", "content": "聖女可願與我雙修？"},
                {"role": "assistant", "content": "柳如煙眼波流轉，微笑道：『少俠若是誠心，有何不可？』"}
            ]

        # 2. 執行存檔
        msg = save_game(self.test_slot, self.engine)
        self.assertIn("存檔成功", msg)

        # 3. 建立全新 GameEngine 實例並讀取存檔
        new_engine = GameEngine()
        success = load_game(self.test_slot, new_engine)

        self.assertTrue(success)

        # 4. 驗證 100% 還原所有世界狀態與對話歷史
        self.assertEqual(new_engine.player_state.name, "楚留香測試")
        self.assertEqual(new_engine.player_state.hp, 85)
        self.assertEqual(new_engine.player_state.gold, 350)
        self.assertEqual(new_engine.player_state.stamina, 70)
        self.assertEqual(new_engine.player_state.charm, 25)
        self.assertIn("合歡玄天功", new_engine.player_state.cultivation_arts)

        self.assertEqual(new_engine.game_turn, 5)
        self.assertEqual(new_engine.main_quest_summary, "已加入血衣樓，準備反殺正派盟主")
        self.assertEqual(new_engine.current_location, "亂葬崗")
        self.assertEqual(new_engine.factions["血衣樓"], 80)
        self.assertTrue(new_engine.world_flags.get("met_she_maiden"))

        if "合歡宗聖女" in new_engine.agents:
            restored_agent = new_engine.agents["合歡宗聖女"]
            self.assertEqual(restored_agent.profile.intimacy, 65)
            self.assertEqual(len(restored_agent.history), 2)
            self.assertEqual(restored_agent.history[0]["content"], "聖女可願與我雙修？")


if __name__ == "__main__":
    unittest.main()
