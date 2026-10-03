"""OllamaClient 送給 Ollama 的參數（2026-10-03 實測換 gemma4:26b：要關掉思考、拿掉重複懲罰、拉長常駐時間）。"""
from tianxia.engine import Game
from tianxia.ollama_client import OllamaClient


def test_defaults_keep_the_old_payload_and_send_no_think_field():
    payload = OllamaClient()._build_payload([{"role": "user", "content": "hi"}], 0.8)
    assert "think" not in payload
    assert payload["keep_alive"] == "30m"
    assert payload["options"]["repeat_penalty"] == 1.18
    assert payload["options"]["presence_penalty"] == 0.3
    assert payload["options"]["frequency_penalty"] == 0.3


def test_think_keep_alive_and_penalties_are_configurable():
    client = OllamaClient(think=False, keep_alive="12h", repeat_penalty=1.0, presence_penalty=0.0, frequency_penalty=0.0)
    payload = client._build_payload([{"role": "user", "content": "hi"}], 0.8)
    assert payload["think"] is False
    assert payload["keep_alive"] == "12h"
    assert payload["options"]["repeat_penalty"] == 1.0
    assert payload["options"]["presence_penalty"] == 0.0
    assert payload["options"]["frequency_penalty"] == 0.0


def test_the_game_builds_its_client_from_the_config(content):
    cfg = content.config
    cfg.ollama_model = "gemma4:26b"
    cfg.ollama_think = False
    cfg.ollama_keep_alive = "12h"
    cfg.ollama_repeat_penalty = 1.0
    cfg.ollama_presence_penalty = 0.0
    cfg.ollama_frequency_penalty = 0.0
    payload = Game.new(content, "測試").client._build_payload([{"role": "user", "content": "hi"}], 0.8)
    assert payload["model"] == "gemma4:26b"
    assert payload["think"] is False and payload["keep_alive"] == "12h"
    assert payload["options"]["repeat_penalty"] == 1.0
