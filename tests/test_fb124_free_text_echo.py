"""FB-124（QA 32efa2c6，2026-10-09）：隨口應對的結果句寫了兩次。

黃巾丁在「夜探營柵」寫了一句做法、失敗：模型潤色的那一段已經把結果句寫進去（「……巡夜的兵卒發現了你，你在霧裡狂奔了半夜才甩掉
追兵。」），引擎接著又照原樣接一次結果句（effect.text 那一行）。提示詞本來就叫模型「不要重複結果文字本身」，是模型沒照做，
所以提示詞不動，引擎這邊擋：潤色插回江湖紀錄時（Game.add_gamble_narration），那一段已經含結果句（空白、標點不算，event_llm.
tells_the_outcome）就拿掉引擎那一行；沒含照舊接在後面。

假的模型：把 requests.post 換掉（tests/test_fb104_kana.py 的做法），走真的 event_llm.narrate_event_gamble；不連任何網路。"""
from __future__ import annotations

import pytest
import requests

from conftest import FixedRandom
from tianxia import event_llm
from tianxia.models import Effect, FreeTextChoice
from tianxia.ollama_client import OllamaClient

REAL_CHAT_TEXT = OllamaClient.chat_text  # 匯入時抓：conftest 的 autouse 之後會換成「連不上」

OUTCOME = "巡夜的兵卒發現了你，你在霧裡狂奔了半夜才甩掉追兵。"
GAMBLE = FreeTextChoice(
    prompt="另想法子混進營柵", stat="agi", by="self",
    effect=Effect(text="你摸進了營柵。", stats={"good": 1}), fail_effect=Effect(text=OUTCOME, stamina=-16),
)
# QA 看到的那一段（模型把結果句寫在自己那一段的最後）
QA_PARAGRAPH = "你試圖藉著幫巡夜兵卒分擔重擔來掩人耳目，不料動作間的聲響卻驚動了對方，" + OUTCOME


class _Reply:
    def __init__(self, content):
        self._content = content
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": self._content}}


@pytest.fixture
def model(monkeypatch):
    """假的 Ollama：replies 依序回。真的 chat_text 換回來。"""
    state = {"replies": []}
    monkeypatch.setattr(requests, "post", lambda url, json=None, timeout=None: _Reply(state["replies"].pop(0)))
    monkeypatch.setattr(OllamaClient, "chat_text", REAL_CHAT_TEXT)
    return state


@pytest.fixture
def failed_gamble(game):
    """測試內容的「醉漢」事件掛上這個隨口應對，玩家寫了一句、失敗了（江湖紀錄有了那一則，還沒有潤色）。"""
    game.content.events["drunk"].free_text = GAMBLE
    game.state.pending_event = "drunk"
    game.rng = FixedRandom(0.99)  # 擲骰 99：失敗
    game.answer_event(game.free_text_request("我幫你扛起這擔子"), 40)
    assert game.last_gamble is not None and game.last_gamble.success is False
    return game


def _polish(game, model, paragraph):
    """鎖外那一段（server.answer_event 的 D、E）：假的模型回 paragraph，潤色插回那一則紀錄。"""
    model["replies"] = [paragraph]
    outcome = game.last_gamble
    game.before = list(game.state.journal[0].lines)  # 潤色插回之前的那一則（比對「其他照舊」用）
    narration = event_llm.narrate_event_gamble(
        OllamaClient(), game.content.events[outcome.event_id], outcome.text, outcome.success, outcome.effect_text,
    )
    game.add_gamble_narration(outcome, narration)
    return narration, list(game.state.journal[0].lines)


def _bare(text):
    return "".join(ch for ch in text if ch.isalnum())


def test_a_paragraph_that_already_tells_the_outcome_is_not_followed_by_it_again(failed_gamble, model):
    narration, lines = _polish(failed_gamble, model, QA_PARAGRAPH)
    assert narration == QA_PARAGRAPH and narration in lines
    assert OUTCOME not in lines  # 引擎那一行拿掉了
    assert _bare("".join(lines)).count(_bare(OUTCOME)) == 1  # 整則紀錄裡結果句只出現一次
    # 其他照舊：潤色緊接在你說的那一句後面；拿掉潤色、補回結果句那一行，就是插回之前的那一則（扣的體力等其他行一行不少）
    said = next(i for i, line in enumerate(lines) if line.startswith("你：「我幫你扛起這擔子」"))
    assert lines[said + 1] == narration
    before = failed_gamble.before
    assert OUTCOME in before and [x for x in lines if x != narration] == [x for x in before if x != OUTCOME]


@pytest.mark.parametrize("paragraph", [
    "你剛扛起擔子就弄出了聲響。巡夜的兵卒發現了你  你在霧裡狂奔了半夜，才甩掉追兵！",  # 標點、空白不同
    "你剛扛起擔子就弄出了聲響——「巡夜的兵卒發現了你，你在霧裡狂奔了半夜才甩掉追兵」。",  # 加了引號
], ids=["punctuation-and-spaces", "quoted"])
def test_punctuation_and_spacing_do_not_hide_the_echo(failed_gamble, model, paragraph):
    narration, lines = _polish(failed_gamble, model, paragraph)
    assert narration in lines and OUTCOME not in lines
    assert _bare("".join(lines)).count(_bare(OUTCOME)) == 1


def test_a_paragraph_without_the_outcome_is_followed_by_it_as_before(failed_gamble, model):
    narration, lines = _polish(failed_gamble, model, "你剛扛起擔子，腳下一滑，扁擔撞上了柵欄。")
    assert lines.index(narration) == lines.index(OUTCOME) - 1  # 跟以前一樣：潤色在前、結果句在後
    assert _bare("".join(lines)).count(_bare(OUTCOME)) == 1


@pytest.mark.parametrize("paragraph", [
    "你剛扛起擔子，巡夜的兵卒發現了你。",  # 前一半
    "你剛扛起擔子，巡夜的兵卒發現了你，你在霧裡狂奔了半夜。",  # 只差最後「才甩掉追兵」
], ids=["half", "all-but-the-end"])
def test_part_of_the_outcome_is_not_enough_to_drop_it(failed_gamble, model, paragraph):
    """只寫了結果句的一部分：引擎那一行照接，沒寫到的那一截（甩掉追兵）才不會不見。"""
    narration, lines = _polish(failed_gamble, model, paragraph)
    assert OUTCOME in lines and lines.index(narration) == lines.index(OUTCOME) - 1


def test_the_success_side_is_guarded_the_same_way(game, model):
    game.content.events["drunk"].free_text = GAMBLE
    game.state.pending_event = "drunk"
    game.rng = FixedRandom(0.0)
    game.answer_event(game.free_text_request("裝成送水的"), 60)
    assert game.last_gamble.success is True
    narration, lines = _polish(game, model, "你提著水桶走過哨口，你摸進了營柵。")
    assert "你摸進了營柵。" not in lines and narration in lines


def test_tells_the_outcome_ignores_spacing_and_punctuation_and_an_empty_outcome():
    assert event_llm.tells_the_outcome("……發現了你 你在霧裡狂奔！", "發現了你，你在霧裡狂奔。")
    assert event_llm.tells_the_outcome("「發現了你」", "發現了你")
    assert not event_llm.tells_the_outcome("發現了你。", "發現了你，你在霧裡狂奔。")
    assert not event_llm.tells_the_outcome("發現了你，你在霧裡。", "發現了你，你在霧裡狂奔。")  # 只差最後兩個字也不算
    assert not event_llm.tells_the_outcome("隨便一段話。", "")  # 沒有結果句（effect 沒寫字）：沒有東西可以重複
    assert not event_llm.tells_the_outcome("隨便一段話。", "。")
