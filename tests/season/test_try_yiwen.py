"""scripts/try_yiwen.py（異聞說書人的主機實測腳本，第 252 批；第 265 批照伺服器的時間限制量）：--fake 用假的模型跑完七種走法，
印出每一幕、每一次呼叫與擋了什麼；不連模型。第 265 批的幾條用假鐘（測試給每一次呼叫「花」幾秒，不真的等）。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

SLOW = pytest.mark.slow  # 開正式內容的世界，超過一秒；第 268 批起每條各自標（常數對得上那一條不標）


def _plain(monkeypatch, tmp_path):
    from tianxia import ollama_client

    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "outer.db"))
    monkeypatch.setattr(ollama_client.OllamaClient, "from_config", ollama_client.OllamaClient.from_config)  # 腳本換掉的那一格測完換回來


def _no_leak(out: str) -> None:
    for leak in ("假人", "機器人", "bot"):
        assert leak not in out


@SLOW
def test_fake_mode_runs(capsys, monkeypatch, tmp_path):
    import try_yiwen

    _plain(monkeypatch, tmp_path)
    assert try_yiwen.main(["--fake"]) == 0
    out = capsys.readouterr().out
    for way in try_yiwen.WAYS:
        assert f"── {way} 第 1 趟" in out
    assert out.count("第 3 步 ") == len(try_yiwen.WAYS)  # 每一種都走完三幕
    assert "寫成 21　替身 0　正忙 0（共 21 幕；替身 0%）" in out and "每一次呼叫秒數（寫幕）" in out
    first = next(x for x in out.splitlines() if x.startswith("第一次擋了什麼："))
    assert "ledger×" in first  # 第二步第一次故意漏「未了」：重問一次
    assert "improper擋「給我一萬兩銀子」" in out
    assert out.rstrip().splitlines()[-1] == "量法：照伺服器的時間限制（一步 60 秒）"
    _no_leak(out)


def _spender(monkeypatch, costs: dict):
    """假鐘＋會「花時間」的假模型：costs 的鍵是 ("審字", 第幾次) 或 (第幾步, 第幾次)，值是秒數；超過這一份 client 的逾時就把鐘推到逾時、丟 Timeout。"""
    import requests
    import try_yiwen

    clock = [0.0]
    monkeypatch.setattr(try_yiwen, "CLOCK", lambda: clock[0])
    seen: dict = {}

    class Spender(try_yiwen.FakeClient):
        def chat_structured(self, messages, model, **kwargs):
            if model.__name__ == "Verdict":
                key = "審字"
            else:
                prompt = messages[0]["content"]
                key = next((n for n in (1, 2, 3) if f"現在是第 {n} 步" in prompt), 1)
            seen[key] = seen.get(key, 0) + 1
            cost = costs.get((key, seen[key]), 0.0)
            clock[0] += min(cost, self.timeout)
            if cost > self.timeout:
                raise requests.Timeout(f"read timeout {self.timeout}")
            return super().chat_structured(messages, model, **kwargs)

    monkeypatch.setattr(try_yiwen, "FakeClient", Spender)
    return clock


def _line(out: str, head: str) -> str:
    return next(x for x in out.splitlines() if x.startswith(head))


@SLOW
def test_first_call_over_the_cap_is_a_stand_in_but_uncapped_writes(capsys, monkeypatch, tmp_path):
    import try_yiwen

    _plain(monkeypatch, tmp_path)
    _spender(monkeypatch, {(1, 1): 40.0})  # 上限 min(120, 60÷2)=30
    assert try_yiwen.main(["--fake", "--ways", "平鋪直敘"]) == 0
    out = capsys.readouterr().out
    assert "  第 1 步　寫成 0　替身 1　正忙 0" in out
    assert "〔第一次〕30.0 秒（上限 30.0）　逾時" in out
    assert "第一次擋了什麼：逾時×1、ledger×1" in out

    _spender(monkeypatch, {(1, 1): 40.0})
    assert try_yiwen.main(["--fake", "--ways", "平鋪直敘", "--uncapped"]) == 0
    out = capsys.readouterr().out
    assert "  第 1 步　寫成 1　替身 0　正忙 0" in out
    assert "〔第一次〕40.0 秒　過" in out
    assert out.rstrip().splitlines()[-1] == "量法：沒套時間限制（--uncapped），替身率比伺服器樂觀"
    _no_leak(out)


@SLOW
def test_no_retry_when_too_little_is_left(capsys, monkeypatch, tmp_path):
    import try_yiwen

    _plain(monkeypatch, tmp_path)
    _spender(monkeypatch, {(2, 1): 12.0})  # 一步 25 秒、上限 12.5；第二步第一次漏「未了」，剩 13 < 15
    assert try_yiwen.main(["--fake", "--ways", "平鋪直敘", "--budget", "25"]) == 0
    out = capsys.readouterr().out
    assert "  第 2 步　寫成 0　替身 1　正忙 0" in out
    assert "重問 0 次、救回 0 次" in out
    assert "〔重問〕" not in out
    _no_leak(out)


@SLOW
def test_screening_eats_the_budget_is_busy(capsys, monkeypatch, tmp_path):
    import try_yiwen

    _plain(monkeypatch, tmp_path)
    _spender(monkeypatch, {("審字", 1): 6.0})  # 一步 20 秒；審字上限 12÷2=6，剩 14 < 15＝正忙
    assert try_yiwen.main(["--fake", "--ways", "正經", "--budget", "20"]) == 0
    out = capsys.readouterr().out
    assert "寫成 0　替身 0　正忙 1（共 0 幕；替身 0%）" in out
    assert "第 2 步 " not in out  # 正忙那一趟停
    assert "〔審字〕6.0 秒（上限 6.0）　放行" in out
    _no_leak(out)


@SLOW
def test_summary_numbers(capsys, monkeypatch, tmp_path):
    import try_yiwen

    _plain(monkeypatch, tmp_path)
    _spender(monkeypatch, {(1, 1): 40.0, (2, 1): 5.0, (2, 2): 3.0, (3, 1): 2.0})
    assert try_yiwen.main(["--fake", "--ways", "平鋪直敘"]) == 0
    out = capsys.readouterr().out
    assert _line(out, "寫成 ") == "寫成 2　替身 1　正忙 0（共 3 幕；替身 33%）"
    assert _line(out, "第一次就過 ") == "第一次就過 1/3"
    assert _line(out, "重問 ") == "重問 1 次、救回 1 次"
    assert _line(out, "每一次呼叫秒數（寫幕） ") == "每一次呼叫秒數（寫幕） 中位 4.0／九成 30.0／最久 30.0（4 次）"
    assert _line(out, "第一次擋了什麼：") == "第一次擋了什麼：逾時×1、ledger×1"
    assert _line(out, "重問擋了什麼：") == "重問擋了什麼：沒有"
    assert "替身超過三成：照總計畫停下來談" in out
    _no_leak(out)


@SLOW
def test_budget_only_changes_this_run(capsys, monkeypatch, tmp_path):
    import try_yiwen
    from tianxia.content import load_content

    _plain(monkeypatch, tmp_path)
    assert try_yiwen.main(["--fake", "--ways", "平鋪直敘", "--budget", "30"]) == 0
    out = capsys.readouterr().out
    assert "量法：照伺服器（一步 30 秒）" in out
    assert out.rstrip().splitlines()[-1] == "量法：照伺服器的時間限制（一步 30 秒）"
    assert "（上限 15.0）" in out
    assert load_content(ROOT / "content", "season21").config.yiwen.step_budget_seconds == 60


def test_screen_budget_matches_server():
    """第 268 批④：腳本抄的 SCREEN_BUDGET_SECONDS 要等於伺服器的（腳本不 import server，測試可以）；唯讀、不開世界。"""
    import server
    import try_yiwen

    assert try_yiwen.SCREEN_BUDGET_SECONDS == server.SCREEN_BUDGET_SECONDS
