"""OllamaClient 送給 Ollama 的參數（2026-10-03 實測換 gemma4:26b：要關掉思考、拿掉重複懲罰、拉長常駐時間）。"""
import pytest
import requests
from pydantic import BaseModel

from tianxia.battle_instance import SuccessRateJudgment
from tianxia.engine import Game
from tianxia.ollama_client import OllamaClient, _ensure_required_present

REAL_CHAT_STRUCTURED = OllamaClient.chat_structured  # 匯入時抓：conftest 的 autouse 之後會換成「連不上」


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


def _configured(content):
    """八個參數都設成跟 OllamaClient 的預設、也跟彼此不同的值（預設是 localhost、qwen2.5:14b、120、None、30m、1.18、0.3、0.3）：
    漏帶任何一個，client 就會悄悄變回預設。回傳預期的欄位值。"""
    cfg = content.config
    cfg.ollama_url, cfg.ollama_model, cfg.ollama_timeout = "http://gpu-box:11434", "gemma4:26b", 77
    cfg.ollama_think, cfg.ollama_keep_alive = False, "12h"
    cfg.ollama_repeat_penalty, cfg.ollama_presence_penalty, cfg.ollama_frequency_penalty = 1.0, 0.0, 0.1
    return {
        "base_url": "http://gpu-box:11434", "model": "gemma4:26b", "timeout": 77, "think": False, "keep_alive": "12h",
        "repeat_penalty": 1.0, "presence_penalty": 0.0, "frequency_penalty": 0.1,
    }


def test_a_client_from_the_config_carries_every_configured_parameter(content):
    """OllamaClient.from_config（假人程式用）：照預期的值逐一比，不是跟另一個也走同一個函式的 client 比。"""
    expected = _configured(content)
    made = OllamaClient.from_config(content.config)
    assert {field: getattr(made, field) for field in expected} == expected
    payload = made._build_payload([{"role": "user", "content": "hi"}], 0.8)
    assert payload["options"]["presence_penalty"] == 0.0 and payload["options"]["frequency_penalty"] == 0.1


def test_the_games_client_carries_every_configured_parameter_too(content):
    """Game 與假人程式用同一套參數：Game 的 client 也照同樣預期的值，一個不少。"""
    expected = _configured(content)
    client = Game.new(content, "測試").client
    assert {field: getattr(client, field) for field in expected} == expected


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


# ── 截斷檢查（required_fields）：falsy 不等於缺欄位 ──────────────────────


def test_a_success_rate_of_zero_is_a_real_answer_not_a_truncation():
    """防灌水的提示詞要模型對「我必定成功」這類寫法給 0~10，實測 gemma4:26b 就是回 0
    （done_reason=stop、JSON 完整）。以前用 `not data.get(...)` 判斷，0 會被當成截斷丟掉，
    重試再拿到 0 再丟一次，最後退回保底 40——比正常評出來的低分還高。"""
    _ensure_required_present({"success_rate": 0, "reasoning": "在對遊戲下指令"}, SuccessRateJudgment, ["success_rate"])


def test_a_missing_or_empty_field_still_counts_as_truncated():
    for data in ({}, {"success_rate": None}, {"reasoning": "只有理由"}):
        with pytest.raises(ValueError, match="success_rate"):
            _ensure_required_present(data, SuccessRateJudgment, ["success_rate"])


def test_an_empty_list_or_string_still_counts_as_truncated():
    """原本的用意（ai_story 的 options 坑）要留著：有 default_factory 的欄位空著就是截斷。"""
    class Reply(BaseModel):
        options: list[str] = []
        name: str = ""

    for field in ("options", "name"):
        with pytest.raises(ValueError, match=field):
            _ensure_required_present({"options": [], "name": ""}, Reply, [field])
    _ensure_required_present({"options": ["甲"], "name": "鑄韌拳"}, Reply, ["options", "name"])


# ── 模型沒裝（Ollama 回 404）：錯誤訊息照字寫，三個地方都是同一句 ──────────────────────


class _Reply:
    """假的 HTTP 回應：status 400 以上時 raise_for_status 丟 HTTPError，跟 requests 一樣。"""

    def __init__(self, status, content=""):
        self.status_code, self._content = status, content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)

    def json(self):
        return {"message": {"content": self._content}}


def _first_reply_is_404():
    yield _Reply(404)


def _the_post_raises_an_http_404():
    raise requests.HTTPError("404", response=_Reply(404))
    yield  # 讓它也是個產生器：第一趟就丟例外


def _the_retry_gets_404():
    yield _Reply(200, "這不是 JSON")  # 第一趟格式不對，重問
    yield _Reply(404)


@pytest.mark.parametrize("replies", [_first_reply_is_404, _the_post_raises_an_http_404, _the_retry_gets_404],
                         ids=["first-post", "http-error", "retry"])
def test_a_missing_model_is_reported_in_the_same_words_at_each_of_the_three_places(monkeypatch, replies):
    """模型沒裝時主控台看到的那一句（整併第 8 區把三份合成 _model_missing，最終審查 M5 要釘住字）：
    第一趟就回 404、送出時就丟 404 的 HTTPError、格式不對重問那一趟回 404，都是這一句，模型名字照 client 的。"""
    stream = replies()

    def post(url, json=None, timeout=None):
        return next(stream)

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(OllamaClient, "chat_structured", REAL_CHAT_STRUCTURED)
    client = OllamaClient(model="gemma4:26b")
    with pytest.raises(RuntimeError) as raised:
        client.chat_structured([{"role": "user", "content": "取個名字"}], SuccessRateJudgment)
    assert str(raised.value) == "Ollama 回傳 404：模型 'gemma4:26b' 未找到，請先 `ollama pull gemma4:26b`。"
