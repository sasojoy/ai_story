"""省電模式（2026-10-18，Joy「有時候這台電腦還要同步跑到其他東西」）。

量到的是：吃掉這台機器的不是遊戲程式（12 核裡 2～5% 的一核、約 320 MB），是常駐的模型
（keep_alive 12h → 約 7.5 GiB VRAM 整天躺著）。所以省電模式只改一件事：模型的 keep_alive。
"""
from __future__ import annotations

import copy
import time

import pytest

from tianxia import power_save
from tianxia.ollama_client import OllamaClient, capped

REAL_WARM = OllamaClient.warm  # conftest 會把它假掉，這裡在 import 時先留一份真的


@pytest.fixture(autouse=True)
def _no_flag(monkeypatch, tmp_path):
    """每個測試都從「沒開省電模式」開始：旗標檔指到空的暫存路徑、環境變數清掉。"""
    monkeypatch.delenv(power_save.ENV, raising=False)
    monkeypatch.setattr(power_save, "FLAG", tmp_path / "power_save")


def test_off_by_default():
    assert power_save.wanted() is None and not power_save.on()
    assert power_save.keep_alive("12h") == "12h"


def test_the_flag_file_turns_it_on(monkeypatch, tmp_path):
    flag = tmp_path / "power_save"
    flag.write_text("2m", encoding="utf-8")
    monkeypatch.setattr(power_save, "FLAG", flag)
    assert power_save.on() and power_save.keep_alive("12h") == "2m"


def test_an_empty_flag_file_uses_the_default(monkeypatch, tmp_path):
    flag = tmp_path / "power_save"
    flag.write_text("  \n", encoding="utf-8")
    monkeypatch.setattr(power_save, "FLAG", flag)
    assert power_save.keep_alive("12h") == power_save.DEFAULT


@pytest.mark.parametrize("word", ["0", "off", "OFF", "false", "no", "none"])
def test_words_that_mean_off(monkeypatch, tmp_path, word):
    flag = tmp_path / "power_save"
    flag.write_text(word, encoding="utf-8")
    monkeypatch.setattr(power_save, "FLAG", flag)
    assert not power_save.on() and power_save.keep_alive("12h") == "12h"


def test_a_bom_in_the_flag_file_does_not_leak_into_the_value(monkeypatch, tmp_path):
    """PowerShell 的 Set-Content -Encoding utf8 會寫 BOM。帶著 BOM 送給 Ollama 是 HTTP 400
    （time: invalid duration），而暖機失敗只記一行警告——於是「模型就是不載」而且看不出原因（2026-10-18 實機踩到）。"""
    flag = tmp_path / "power_save"
    flag.write_bytes("5m".encode("utf-8-sig"))  # 就是 b"ï»¿5m"
    monkeypatch.setattr(power_save, "FLAG", flag)
    assert power_save.keep_alive("12h") == "5m"


def test_the_env_var_wins_over_the_flag_file(monkeypatch, tmp_path):
    flag = tmp_path / "power_save"
    flag.write_text("2m", encoding="utf-8")
    monkeypatch.setattr(power_save, "FLAG", flag)
    monkeypatch.setenv(power_save.ENV, "off")  # 環境變數說不要，就是不要
    assert power_save.keep_alive("12h") == "12h"
    monkeypatch.setenv(power_save.ENV, "30s")
    assert power_save.keep_alive("12h") == "30s"


def test_a_flag_we_cannot_read_is_not_an_outage(monkeypatch, tmp_path):
    """讀不到旗標檔就當沒開：省電是方便，不能因為它讓模型叫不動。"""
    monkeypatch.setattr(power_save, "FLAG", tmp_path)  # 是目錄，不是檔
    assert power_save.keep_alive("12h") == "12h"


def test_existing_clients_follow_the_switch(monkeypatch):
    """開關換了不必重開伺服器：已經建好的 client 與它的複本都跟著換。"""
    client = OllamaClient(keep_alive="12h")
    plain, quick = copy.copy(client), capped(client, 15, retry=False)
    assert [c.keep_alive for c in (client, plain, quick)] == ["12h"] * 3
    monkeypatch.setenv(power_save.ENV, "2m")
    assert [c.keep_alive for c in (client, plain, quick)] == ["2m"] * 3
    monkeypatch.delenv(power_save.ENV)
    assert [c.keep_alive for c in (client, plain, quick)] == ["12h"] * 3


def test_the_request_really_carries_it(monkeypatch):
    """送出去的 JSON 裡的 keep_alive 是省電模式那一個（不是只有 property 變了）。

    conftest 的 no_real_ollama_flavor_calls 把 warm 假掉了（免得整套測試去戳這台機器真的那個 Ollama），
    這個測試要的是真的那一個，所以拿 import 時留下來的 REAL_WARM 裝回去。warm 在背景執行緒裡送，等它一下。
    """
    sent = {}

    class Reply:
        status_code = 200
        text = ""

    def fake_post(url, json=None, timeout=None, **kw):
        sent.update(json or {})
        return Reply()

    monkeypatch.setattr("tianxia.ollama_client.requests.post", fake_post)
    monkeypatch.setattr(OllamaClient, "warm", REAL_WARM)
    client = OllamaClient(keep_alive="12h")
    monkeypatch.setenv(power_save.ENV, "90s")
    assert client.warm() is True  # 呼叫端馬上拿到，不等模型載完
    for _ in range(200):  # 背景那條執行緒送出去之前先等一下（最多 2 秒）
        if sent:
            break
        time.sleep(0.01)
    assert sent["keep_alive"] == "90s"
    assert sent["options"]["num_ctx"] == client.context_length  # ctx 要跟真正呼叫時一樣，不然 Ollama 會整個重載
