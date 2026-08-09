import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.models import NPCProfile, PlayerState, GameStateDelta
from src.npc_agent import NPCAgent
from src.game_engine import GameEngine


class TestEngine(unittest.TestCase):

    def setUp(self):
        self.profile = NPCProfile(
            name="殺手阿福",
            identity="血衣樓高級殺手",
            personality="下午六點準時下班，絕不加班。",
            hp=120,
            location="龍門客棧旁暗巷"
        )
        self.player_state = PlayerState(
            hp=100,
            max_hp=100,
            gold=50,
            inventory=["鏽蝕鐵劍"]
        )

    def test_npc_agent_prompt(self):
        agent = NPCAgent(self.profile)
        prompt = agent.build_system_prompt(self.player_state)

        self.assertIn("殺手阿福", prompt)
        self.assertIn("血衣樓高級殺手", prompt)
        self.assertIn("HP=100", prompt)
        self.assertIn("金幣=50", prompt)
        self.assertIn("鏽蝕鐵劍", prompt)
        self.assertIn("允許玩家進行任何荒謬", prompt)

    def test_game_engine_apply_delta(self):
        engine = GameEngine()
        engine.player_state.hp = 50
        engine.player_state.gold = 20
        engine.player_state.inventory = ["鏽蝕鐵劍"]

        delta = GameStateDelta(
            narrative="測試獲得寶物與受傷",
            player_hp_change=-10,
            player_gold_change=100,
            inventory_added=["秘笈"],
            inventory_removed=["鏽蝕鐵劍"],
            npc_status_tag="驚訝",
            world_flag_set={"met_afu": True}
        )

        engine.apply_delta(delta)

        self.assertEqual(engine.player_state.hp, 40)
        self.assertEqual(engine.player_state.gold, 120)
        self.assertIn("秘笈", engine.player_state.inventory)
        self.assertNotIn("鏽蝕鐵劍", engine.player_state.inventory)
        self.assertTrue(engine.world_flags.get("met_afu"))

    def test_switch_npc(self):
        engine = GameEngine()
        self.assertIsNotNone(engine.current_agent)
        
        if "錢莊老王" in engine.agents:
            success = engine.switch_npc("錢莊老王")
            self.assertTrue(success)
            self.assertEqual(engine.current_agent.profile.name, "錢莊老王")

    @patch("src.ollama_client.OllamaClient.chat_structured")
    def test_engine_interact(self, mock_chat):
        mock_delta = GameStateDelta(
            narrative="老王算盤打得飛快",
            player_hp_change=0,
            player_gold_change=50,
            inventory_added=["銀票"],
            inventory_removed=[],
            npc_status_tag="興奮",
            world_flag_set={"invested": True}
        )
        mock_chat.return_value = mock_delta

        engine = GameEngine()
        engine.switch_npc("錢莊老王")
        delta = engine.interact("我要買 IPO 股票")

        self.assertEqual(delta.narrative, "老王算盤打得飛快")
        self.assertEqual(engine.player_state.gold, 100)  # 50 + 50
        self.assertIn("銀票", engine.player_state.inventory)


if __name__ == "__main__":
    unittest.main()
