from unittest import mock

from tianxia import flavor


def test_polish_world_event_returns_empty_without_a_client():
    assert flavor.polish_world_event(None, "黃巾軍攻破潁川防線！") == ""


def test_polish_world_event_strips_whitespace_and_quotes_from_the_llm_reply():
    client = mock.Mock()
    client.chat_text.return_value = '「風又吹起了。」\n'
    assert flavor.polish_world_event(client, "黃巾軍攻破潁川防線！") == "風又吹起了。"


def test_polish_world_event_swallows_any_connection_error():
    client = mock.Mock()
    client.chat_text.side_effect = RuntimeError("connection refused")
    assert flavor.polish_world_event(client, "黃巾軍攻破潁川防線！") == ""


def test_polish_world_event_passes_the_threshold_text():
    client = mock.Mock()
    client.chat_text.return_value = "街坊議論紛紛。"
    result = flavor.polish_world_event(client, "黃巾軍攻破潁川防線！")
    assert result == "街坊議論紛紛。"
    prompt = client.chat_text.call_args[0][0][1]["content"]
    assert "黃巾軍攻破潁川防線" in prompt


def test_flavor_is_late_han_not_wuxia_and_comes_out_in_traditional_characters():
    assert "漢末" in flavor._SYSTEM_PROMPT
    assert "三國時代" not in flavor._SYSTEM_PROMPT and "文字武俠遊戲" not in flavor._SYSTEM_PROMPT
    client = mock.Mock()
    client.chat_text.return_value = "风吹过城头的旗帜。"
    assert flavor.polish_world_event(client, "城外營寨連綿。") == "風吹過城頭的旗幟。"


def test_polish_world_event_drops_a_long_or_marked_up_reply():
    """2026-10-31 自檢：結果全服快取、每季都看同一句，以前標題、數字、「假人」都原樣快取。"""
    client = mock.Mock()
    for reply in ("## 標題\n- 據說死了 10000 人", "假人都跑了，城裡空蕩蕩的。", "風" * 80):
        client.chat_text.return_value = reply
        assert flavor.polish_world_event(client, "黃巾軍攻破潁川防線！") == ""
