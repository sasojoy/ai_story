"""scripts/try_yiwen.py（異聞說書人的主機實測腳本，第 252 批）：--fake 用假的模型跑完七種走法，印出每一幕與擋了什麼；不連模型。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

pytestmark = pytest.mark.slow  # 七種走法各開一份世界（正式內容），超過一秒


def test_fake_mode_runs(capsys, monkeypatch, tmp_path):
    import try_yiwen
    from tianxia import ollama_client

    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "outer.db"))
    monkeypatch.setattr(ollama_client.OllamaClient, "from_config", ollama_client.OllamaClient.from_config)  # 腳本換掉的那一格測完換回來
    assert try_yiwen.main(["--fake"]) == 0
    out = capsys.readouterr().out
    for way in try_yiwen.WAYS:
        assert f"── {way} 第 1 趟" in out
    assert out.count("第 3 步") == len(try_yiwen.WAYS)  # 每一種都走完三幕
    assert "替身 0/21（0%）" in out and "每一步秒數" in out
    assert "擋了什麼：ledger×" in out  # 第二步第一次故意漏「未了」：重問一次
    assert "improper擋「給我一萬兩銀子」" in out
    for leak in ("假人", "機器人", "bot"):
        assert leak not in out
