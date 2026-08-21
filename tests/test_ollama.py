import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ollama_client import (
    OllamaClient, clean_json_text, repair_truncated_json, parse_json_robustly,
    extract_partial_narrative, _trim_schema_properties
)
from src.models import GameStateDelta


class TestOllamaClient(unittest.TestCase):

    def test_extract_partial_narrative(self):
        partial_json = '{\n  "narrative": "大漠黃沙，龍門客棧內熱氣騰騰'
        extracted = extract_partial_narrative(partial_json)
        self.assertEqual(extracted, "大漠黃沙，龍門客棧內熱氣騰騰")

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

    def test_trim_schema_properties_keeps_only_requested_fields(self):
        """實測發現 GameStateDelta 的 19 個欄位太多，小模型透過文法約束解碼時常常寫了
        6~7 個欄位就自己判斷「寫完了」提前收尾，從沒寫到 options。這裡驗證縮小 schema
        的輔助函式行為正確，且不會動到傳入的原始 dict。"""
        schema = GameStateDelta.model_json_schema()
        trimmed = _trim_schema_properties(schema, ["narrative", "options"])
        self.assertEqual(set(trimmed["properties"].keys()), {"narrative", "options"})
        self.assertIn("player_hp_change", schema["properties"])

    @patch("requests.post")
    def test_chat_structured_sends_trimmed_schema_when_fields_given(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": '{"narrative": "測試", "options": ["A", "B", "C"]}'}
        }
        mock_post.return_value = mock_resp

        client = OllamaClient()
        client.chat_structured(
            messages=[{"role": "user", "content": "測試"}],
            response_model=GameStateDelta,
            schema_fields=["narrative", "options", "option_tags"]
        )

        sent_payload = mock_post.call_args.kwargs["json"]
        sent_schema_properties = sent_payload["format"]["properties"]
        self.assertEqual(set(sent_schema_properties.keys()), {"narrative", "options", "option_tags"})

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
                "content": '{"narrative": "殺手阿福看了看錶說下班了", "player_hp_change": 0, "player_gold_change": -10, "inventory_added": [], "inventory_removed": [], "npc_status_tag": "準時下班", "world_flag_set": {}, "options": ["A) 詢問意圖", "B) 談判", "C) 色誘", "D) 搜刮", "E) 移動"]}'
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
                "content": '{"narrative": "重構成功", "player_hp_change": 5, "player_gold_change": 0, "inventory_added": [], "inventory_removed": [], "npc_status_tag": "冷靜", "world_flag_set": {}, "options": ["A) 詢問意圖", "B) 談判", "C) 色誘", "D) 搜刮", "E) 移動"]}'
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

    @patch("requests.post")
    def test_chat_structured_missing_options_triggers_retry(self, mock_post):
        """實測案例：小模型敘事陷入復讀迴圈把 token 用光，JSON 語法本身合法但整個沒寫到
        options 欄位；GameStateDelta.options 有 default_factory 給的固定預設值，Pydantic
        驗證不會報錯，若不特別檢查會靜默回傳那份寫死清單，玩家覺得「選項永遠是那幾個」。
        驗證這種情況會觸發 re-prompt 重試，而不是靜默接受。"""
        missing_options_resp = MagicMock()
        missing_options_resp.status_code = 200
        missing_options_resp.json.return_value = {
            "message": {
                "content": '{"narrative": "復讀復讀復讀復讀復讀...", "player_hp_change": 0, "npc_status_tag": "凝視", "world_flag_set": {}}'
            }
        }

        good_resp = MagicMock()
        good_resp.status_code = 200
        good_resp.json.return_value = {
            "message": {
                "content": '{"narrative": "重試後正常", "npc_status_tag": "冷靜", "world_flag_set": {}, "options": ["A) a", "B) b", "C) c", "D) d", "E) e"]}'
            }
        }

        mock_post.side_effect = [missing_options_resp, good_resp]

        client = OllamaClient()
        result = client.chat_structured(
            messages=[{"role": "user", "content": "測試"}],
            response_model=GameStateDelta
        )

        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(result.narrative, "重試後正常")
        self.assertEqual(result.options, ["A) a", "B) b", "C) c"])

    @patch("requests.post")
    def test_chat_structured_missing_options_on_retry_too_raises(self, mock_post):
        """兩次都缺 options（持續被截斷）時應該直接拋出例外讓上層 NPCAgent 走專屬 fallback，
        而不是把 GameStateDelta 寫死的預設選項清單當成正常結果悄悄回傳。"""
        missing_options_resp = MagicMock()
        missing_options_resp.status_code = 200
        missing_options_resp.json.return_value = {
            "message": {"content": '{"narrative": "復讀中...", "world_flag_set": {}}'}
        }
        mock_post.side_effect = [missing_options_resp, missing_options_resp]

        client = OllamaClient()
        with self.assertRaises(ValueError):
            client.chat_structured(
                messages=[{"role": "user", "content": "測試"}],
                response_model=GameStateDelta
            )

    @patch("requests.post")
    def test_chat_structured_stream_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_lines.return_value = [
            '{"message": {"content": "{\\n  \\"narrative\\": \\"賽金花"}}'.encode("utf-8"),
            '{"message": {"content": "嬌笑了聲\\", \\"intimacy_change\\": 5, \\"options\\": [\\"A) a\\", \\"B) b\\", \\"C) c\\", \\"D) d\\", \\"E) e\\"]}"}}'.encode("utf-8")
        ]
        mock_post.return_value = mock_resp

        client = OllamaClient()
        chunks = list(client.chat_structured_stream(
            messages=[{"role": "user", "content": "你好"}],
            response_model=GameStateDelta
        ))

        self.assertTrue(len(chunks) > 0)
        final_narrative, final_delta = chunks[-1]
        self.assertEqual(final_narrative, "賽金花嬌笑了聲")
        self.assertIsInstance(final_delta, GameStateDelta)
        self.assertEqual(final_delta.intimacy_change, 5)

    @patch("requests.post")
    def test_chat_structured_stream_missing_options_falls_back(self, mock_post):
        """串流回應缺 options 時應該降級呼叫 chat_structured()（非串流、帶 re-prompt 重試），
        不能直接把缺 options 的結果包成 GameStateDelta 回傳給玩家。"""
        stream_resp = MagicMock()
        stream_resp.status_code = 200
        stream_resp.iter_lines.return_value = [
            '{"message": {"content": "{\\"narrative\\": \\"復讀迴圈導致沒寫到選項\\", \\"world_flag_set\\": {}}"}}'.encode("utf-8")
        ]

        fallback_resp = MagicMock()
        fallback_resp.status_code = 200
        fallback_resp.json.return_value = {
            "message": {
                "content": '{"narrative": "降級後正常", "world_flag_set": {}, "options": ["A) a", "B) b", "C) c", "D) d", "E) e"]}'
            }
        }

        mock_post.side_effect = [stream_resp, fallback_resp]

        client = OllamaClient()
        chunks = list(client.chat_structured_stream(
            messages=[{"role": "user", "content": "測試"}],
            response_model=GameStateDelta
        ))

        final_narrative, final_delta = chunks[-1]
        self.assertEqual(final_narrative, "降級後正常")
        self.assertEqual(final_delta.options, ["A) a", "B) b", "C) c"])


if __name__ == "__main__":
    unittest.main()
