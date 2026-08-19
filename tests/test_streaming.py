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

    # ---- web_ui.process_player_choice (Stage 6：Web UI 接上串流) ----

    @patch("src.save_manager.save_account_game")
    @patch("src.ollama_client.OllamaClient.chat_structured_stream")
    def test_process_player_choice_streams_partial_then_final_update(self, mock_stream, mock_save):
        """process_player_choice 結尾會呼叫 engine.auto_save() 寫入真實存檔檔案；
        這裡 mock 掉磁碟寫入，避免測試之間透過殘留的存檔檔案互相污染 used_options_history，
        導致選項去重的結果每次執行都不一樣。"""
        final_delta = GameStateDelta(
            narrative="賽金花緩緩靠近，眼神炙熱",
            options=[
                # 注意：不能用「全新選項A」這種字面帶「選項a」的文字，會被
                # is_placeholder_option() 判定為佔位字串而被過濾掉，改用具體描述
                "A) 邀請對方共飲一杯，順勢打探消息",
                "B) 冷靜分析局勢利弊，提出新的合作條件",
                "C) 靠近對方低聲耳語幾句心事",
                "D) 亮出兵器故作警戒姿態",
                "E) 轉身望向窗外的江湖夜色"
            ]
        )
        mock_stream.return_value = iter([
            ("賽金花緩緩", None),
            ("賽金花緩緩靠近", None),
            ("賽金花緩緩靠近，眼神炙熱", final_delta),
        ])

        from web_ui import process_player_choice, get_engine_for_user, DEFAULT_OPTIONS
        eng = get_engine_for_user("_stage6_stream_test")
        eng.switch_npc("風騷老闆娘")

        # process_player_choice 在每次 yield 之間會就地修改同一個 clean_history 物件
        # (讓 Gradio 能低成本地逐步更新畫面)，所以這裡逐步消費 generator 時要立刻把
        # 當下的文字內容取出存成不可變的字串快照，而不是用 list(generator) 整批收集
        # tuple 參照 —— 否則收集到的每個 tuple 最終都會指向同一個「已被改到最後狀態」的物件。
        gen = process_player_choice(
            custom_name="_stage6_stream_test",
            user_input=DEFAULT_OPTIONS[0],
            history=[],
            prev_opt_a=DEFAULT_OPTIONS[0],
            prev_opt_b=DEFAULT_OPTIONS[1],
            prev_opt_c=DEFAULT_OPTIONS[2],
            prev_opt_d=DEFAULT_OPTIONS[3],
            prev_opt_e=DEFAULT_OPTIONS[4],
        )

        texts = []
        final_result = None
        for result in gen:
            texts.append(result[0][-1]["content"][0]["text"])
            final_result = result

        # 兩個 partial yield + 一個最終 yield
        self.assertEqual(len(texts), 3)

        # 中途 yield：chatbot 最後一則訊息的文字隨串流逐步變長
        self.assertEqual(texts[0], "賽金花緩緩")
        self.assertEqual(texts[1], "賽金花緩緩靠近")

        # 最後一個 yield 才是完整格式化過的訊息，且選項已經更新（不是 gr.update() 空白 no-op）
        self.assertIn("賽金花緩緩靠近，眼神炙熱", texts[-1])
        self.assertEqual(final_result[10], "A) 邀請對方共飲一杯，順勢打探消息")


if __name__ == "__main__":
    unittest.main()
