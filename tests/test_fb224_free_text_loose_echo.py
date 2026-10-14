"""FB-224（回饋單丁批 QA，2026-10-14，模型 gemma4:26b）：潤色把結果句改寫幾個字整句寫進去，結果句又接一次。

田埂設卡寫「塞給他們十個錢讓鄉民先過」成功，模型寫「……散兵們接過錢財後，便讓開了路，挑菜的鄉民一個個跟著你過去，沒人掉一隻鞋。」，
引擎又接「散兵們讓開了路，挑菜的鄉民一個個跟著你過去，沒人掉一隻鞋。」：結果句整句都在，只是中間多了「接過錢財後，便」，
FB-124 的判斷（event_llm.tells_the_outcome）只認一字不差的整句，FB-222 只切潤色尾巴跟結果句開頭重疊的那一截，兩個都沒認出來。

修法：結果句（只算字）至少 LOOSE_MIN 個字、每一個字都依序出現在潤色裡、而且擠在不超過結果句 LOOSE_SPREAD 倍長的一段裡，
也算整句寫了（拿掉引擎那一行）。少一個字、換一個字、拉得太開、短的結果句都不算——寧可多接一次，不把沒寫的當成寫了。"""
from __future__ import annotations

import pytest

from conftest import FixedRandom
from tianxia import event_llm
from tianxia.models import Effect, FreeTextChoice

TOLL_OUTCOME = "散兵們讓開了路，挑菜的鄉民一個個跟著你過去，沒人掉一隻鞋。"
TOLL_PARAGRAPH = "你從懷中摸出十枚錢幣拋向那幾名散兵，示意他們放行鄉民，散兵們接過錢財後，便讓開了路，挑菜的鄉民一個個跟著你過去，沒人掉一隻鞋。"
GAMBLE = FreeTextChoice(
    prompt="另想法子過卡", stat="wis", by="self",
    effect=Effect(text=TOLL_OUTCOME, stats={"good": 1}), fail_effect=Effect(text="散兵把你連人帶菜轟了回去。", stamina=-10),
)


def _bare(text):
    return "".join(ch for ch in text if ch.isalnum())


@pytest.fixture
def toll(game):
    """測試內容的「醉漢」事件掛上田埂設卡的隨口應對，玩家寫了一句、成功了（江湖紀錄有了那一則，還沒有潤色）。"""
    game.content.events["drunk"].free_text = GAMBLE
    game.state.pending_event = "drunk"
    game.rng = FixedRandom(0.0)
    game.answer_event(game.free_text_request("塞給他們十個錢讓鄉民先過"), 50)
    assert game.last_gamble is not None and game.last_gamble.success is True
    game.before = list(game.state.journal[0].lines)
    return game


def test_the_qa_case_writes_the_outcome_once(toll):
    toll.add_gamble_narration(toll.last_gamble, TOLL_PARAGRAPH)
    lines = toll.state.journal[0].lines
    assert TOLL_PARAGRAPH in lines and TOLL_OUTCOME not in lines  # 引擎那一行拿掉了，模型那一段不切
    assert "".join(lines).count("沒人掉一隻鞋") == 1
    assert [x for x in lines if x != TOLL_PARAGRAPH] == [x for x in toll.before if x != TOLL_OUTCOME]


def test_a_paragraph_that_only_retells_part_of_it_is_still_followed_by_it(toll):
    paragraph = "你摸出十枚錢幣拋過去，散兵們接過錢財後，便讓開了路。"
    toll.add_gamble_narration(toll.last_gamble, paragraph)
    lines = toll.state.journal[0].lines
    assert lines.index(paragraph) == lines.index(TOLL_OUTCOME) - 1  # 跟以前一樣：潤色在前、結果句在後


@pytest.mark.parametrize("narration", [
    TOLL_PARAGRAPH,
    "散兵們讓開了路，挑菜的鄉民一個個跟著你過去，沒人掉一隻鞋。",  # 一字不差（FB-124）
    "你丟出錢袋。散兵們一哄而上、讓開了路，挑菜的鄉民一個個低頭跟著你過去，路上沒人掉一隻鞋！",  # 插了好幾處
], ids=["qa", "verbatim", "several-insertions"])
def test_tells_the_outcome_with_a_few_words_inserted(narration):
    assert event_llm.tells_the_outcome(narration, TOLL_OUTCOME)


@pytest.mark.parametrize("narration, outcome", [
    # 換了一個字（讓開 → 讓出）：寧可多接一次
    ("散兵們接過錢財後，便讓出了路，挑菜的鄉民一個個跟著你過去，沒人掉一隻鞋。", TOLL_OUTCOME),
    # 少了最後一個子句
    ("散兵們接過錢財後，便讓開了路，挑菜的鄉民一個個跟著你過去。", TOLL_OUTCOME),
    # 只寫了開頭
    ("你摸出十枚錢幣，散兵們讓開了路。", TOLL_OUTCOME),
    # 字都在、順序也對，可是拉得太開（每個字中間都插了別的）
    ("".join(ch + "又" for ch in _bare(TOLL_OUTCOME)), TOLL_OUTCOME),
    # 順序不對
    ("挑菜的鄉民一個個跟著你過去，散兵們讓開了路，沒人掉一隻鞋。", TOLL_OUTCOME),
    # 短的結果句（不到 LOOSE_MIN 個字）只認一字不差
    ("你走近一看，沒有人理會你。", "沒人理你。"),
    # 不相干
    ("你把錢塞回懷裡，轉身走了。", TOLL_OUTCOME),
    ("隨便一段話。", ""),
], ids=["one-char-changed", "last-clause-missing", "head-only", "too-spread", "out-of-order", "short-outcome", "unrelated", "empty"])
def test_tells_the_outcome_does_not_take_what_was_not_written(narration, outcome):
    assert not event_llm.tells_the_outcome(narration, outcome)


def test_the_spread_limit_is_one_and_a_half_times_the_outcome():
    bare = _bare(TOLL_OUTCOME)
    half = len(bare) // 2
    inside = bare[:half] + "某" * (len(bare) // 2) + bare[half:]  # 多插的字等於結果句的一半：寬度剛好一倍半
    outside = bare[:half] + "某" * (len(bare) // 2 + 1) + bare[half:]
    assert len(bare) >= event_llm.LOOSE_MIN
    assert event_llm.tells_the_outcome(inside, TOLL_OUTCOME)
    assert not event_llm.tells_the_outcome(outside, TOLL_OUTCOME)
