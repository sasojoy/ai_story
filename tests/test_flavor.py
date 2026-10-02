from unittest import mock

from tianxia import flavor


def test_polish_revisit_returns_empty_without_a_client():
    assert flavor.polish_revisit(None, "揚州城", "熱鬧的城池。") == ""


def test_polish_revisit_strips_whitespace_and_quotes_from_the_llm_reply():
    client = mock.Mock()
    client.chat_text.return_value = '「風又吹起了。」\n'
    assert flavor.polish_revisit(client, "揚州城", "熱鬧的城池。") == "風又吹起了。"


def test_polish_revisit_swallows_any_connection_error():
    client = mock.Mock()
    client.chat_text.side_effect = RuntimeError("connection refused")
    assert flavor.polish_revisit(client, "揚州城", "熱鬧的城池。") == ""


def test_polish_event_repeat_passes_the_event_title_and_text():
    client = mock.Mock()
    client.chat_text.return_value = "巷口又傳來同樣的吆喝聲。"
    result = flavor.polish_event_repeat(client, "酒樓鬥毆", "原文內容")
    assert result == "巷口又傳來同樣的吆喝聲。"
    prompt = client.chat_text.call_args[0][0][1]["content"]
    assert "酒樓鬥毆" in prompt and "原文內容" in prompt


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
    assert flavor.polish_revisit(client, "潁川", "城外營寨連綿。") == "風吹過城頭的旗幟。"
