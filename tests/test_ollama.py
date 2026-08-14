import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ollama_client import OllamaClient, clean_json_text, repair_truncated_json, parse_json_robustly
from src.models import GameStateDelta


class TestOllamaClient(unittest.TestCase):

    def test_clean_json_text(self):
        raw_markdown = "```json\n{\"narrative\": \"test\", \"npc_status_tag\": \"normal\"}\n```"
        cleaned = clean_json_text(raw_markdown)
        self.assertEqual(cleaned, "{\"narrative\": \"test\", \"npc_status_tag\": \"normal\"}")

    def test_repair_truncated_json(self):
        truncated_raw = '{"narrative": "殺手阿福擦拭著鐵劍", "options": ["A) 詢問意圖"'
        repaired = repair_truncated_json(truncated_raw)
        parsed = parse_json_robustly(repaired)
        self.assertEqual(parsed["narrative"], "殺手阿福擦拭著鐵劍")
        self.assertEqual(parsed["options"], ["A) 詢問意圖"])

    @patch("requests.get")
    def test_check_health_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        client = OllamaClient()
        self.assertTrue(client.check_health())

    @patch("requests.get")
    def test_check_health_failure(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")
        client = OllamaClient()
        self.assertFalse(client.check_health())

    @patch("requests.post")
    def test_chat_structured_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "content": '{"narrative": "殺手阿福看了看錶說下班了", "player_hp_change": 0, "player_gold_change": -10, "inventory_added": [], "inventory_removed": [], "npc_status_tag": "準時下班", "world_flag_set": {}}'
            }
        }
        mock_post.return_value = mock_resp

        client = OllamaClient()
        result = client.chat_structured(
            messages=[{"role": "user", "content": "打劫！"}],
            response_model=GameStateDelta
        )

        self.assertIsInstance(result, GameStateDelta)
        self.assertEqual(result.narrative, "殺手阿福看了看錶說下班了")
        self.assertEqual(result.player_gold_change, -10)
        self.assertEqual(result.npc_status_tag, "準時下班")

    @patch("requests.post")
    def test_chat_structured_retry_mechanism(self, mock_post):
        # 第一次返回無效 JSON，第二次返回有效 JSON
        bad_resp = MagicMock()
        bad_resp.status_code = 200
        bad_resp.json.return_value = {
            "message": {"content": "INVALID JSON OUTPUT"}
        }

        good_resp = MagicMock()
        good_resp.status_code = 200
        good_resp.json.return_value = {
            "message": {
                "content": '{"narrative": "重構成功", "player_hp_change": 5, "player_gold_change": 0, "inventory_added": [], "inventory_removed": [], "npc_status_tag": "冷靜", "world_flag_set": {}}'
            }
        }

        mock_post.side_effect = [bad_resp, good_resp]

        client = OllamaClient()
        result = client.chat_structured(
            messages=[{"role": "user", "content": "測試"}],
            response_model=GameStateDelta
        )

        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(result.narrative, "重構成功")
        self.assertEqual(result.player_hp_change, 5)


if __name__ == "__main__":
    unittest.main()
