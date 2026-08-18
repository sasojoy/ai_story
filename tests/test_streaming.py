import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.models import NPCProfile, PlayerState, GameStateDelta
from src.npc_agent import NPCAgent
from src.game_engine import GameEngine


class TestStreaming(unittest.TestCase):
    """Stage 0 安全網：interact_stream / process_action_stream 目前零測試覆蓋率，
    先補上再進行 ARCHITECTURE.md 規劃的重構，確保重構前後行為一致。"""

    def setUp(self):
        self.profile = NPCProfile(
            name="殺手阿福",
            identity="血衣樓高級殺手",
            personality="下午六點準時下班，絕不加班。",
            hp=120,
            location="龍門客棧旁暗巷"
        )
        self.player_state = PlayerState(hp=100, max_hp=100, gold=50)

    # ---- NPCAgent.process_action_stream ----

    def test_process_action_stream_yields_partials_then_final_and_records_history_once(self):
        agent = NPCAgent(self.profile)
        mock_client = MagicMock()
        final_delta = GameStateDelta(narrative="阿福冷冷一笑，按劍不語", npc_status_tag="警戒")
        mock_client.chat_structured_stream.return_value = iter([
            ("阿福冷", None),
            ("阿福冷冷一笑", None),
            ("阿福冷冷一笑，按劍不語", final_delta),
        ])

        results = list(agent.process_action_stream(
            client=mock_client,
            player_action="出招試探",
            player_state=self.player_state
        ))

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0], ("阿福冷", None))
        self.assertEqual(results[1], ("阿福冷冷一笑", None))
        self.assertEqual(results[2], ("阿福冷冷一笑，按劍不語", final_delta))

        # 只有最後一個 yield（delta 非 None）才會寫入歷史/去重集合，中途的 partial 不應重複記錄
        self.assertEqual(len(agent.history), 2)
        self.assertEqual(agent.history[0]["content"], "出招試探")
        self.assertEqual(agent.history[1]["content"], "阿福冷冷一笑，按劍不語")
        self.assertIn("出招試探", agent.used_options_history)
        self.assertEqual(agent.current_status_tag, "警戒")

    def test_process_action_stream_fallback_on_exception(self):
        agent = NPCAgent(self.profile)
        mock_client = MagicMock()
        mock_client.chat_structured_stream.side_effect = Exception("Ollama stream timeout")

        results = list(agent.process_action_stream(
            client=mock_client,
            player_action="你好",
            player_state=self.player_state
        ))

        # 串流失敗時，跟非串流版一樣只保底輸出一次，不應該完全沒有結果
        self.assertEqual(len(results), 1)
        final_narrative, final_delta = results[0]
        self.assertIsNotNone(final_delta)
        self.assertIn("阿福", final_narrative)
        self.assertGreaterEqual(len(final_delta.options), 3)
        self.assertEqual(len(agent.history), 2)
        self.assertIn("你好", agent.used_options_history)

    # ---- GameEngine.interact_stream ----

    @patch("src.ollama_client.OllamaClient.chat_structured_stream")
    def test_interact_stream_applies_delta_exactly_once_on_final_yield(self, mock_stream):
        final_delta = GameStateDelta(
            narrative="老王低聲附耳道有妙計",
            player_gold_change=30,
            inventory_added=["密函"],
        )
        mock_stream.return_value = iter([
            ("老王低聲", None),
            ("老王低聲附耳道有妙計", final_delta),
        ])

        engine = GameEngine()
        engine.switch_npc("錢莊老王")
        start_turn = engine.game_turn
        start_gold = engine.player_state.gold

        collected = list(engine.interact_stream("附耳過去聽老王的計畫"))

        self.assertEqual(len(collected), 2)
        self.assertIsNone(collected[0][1])
        self.assertIs(collected[1][1], final_delta)

        # apply_delta 只在最後一個 yield 套用一次：回合數只 +1，金幣只加一次
        self.assertEqual(engine.game_turn, start_turn + 1)
        self.assertEqual(engine.player_state.gold, start_gold + 30)
        self.assertIn("密函", engine.player_state.inventory)

    @patch("src.ollama_client.OllamaClient.chat_structured_stream")
    def test_interact_stream_falls_back_and_still_applies_state_when_stream_fails(self, mock_stream):
        mock_stream.side_effect = Exception("Ollama stream timeout")

        engine = GameEngine()
        engine.switch_npc("殺手阿福")
        start_turn = engine.game_turn

        collected = list(engine.interact_stream("試探性攻擊"))

        self.assertEqual(len(collected), 1)
        narrative, delta = collected[0]
        self.assertIsNotNone(delta)
        self.assertEqual(engine.game_turn, start_turn + 1)

    def test_interact_stream_without_current_agent_raises(self):
        engine = GameEngine()
        engine.current_agent = None
        with self.assertRaises(ValueError):
            list(engine.interact_stream("隨便做點什麼"))


if __name__ == "__main__":
    unittest.main()
