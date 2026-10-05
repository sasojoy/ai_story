"""取名（tianxia/naming.py，從舊的 craft.py 搬來）：整理、過濾、決定性退路、請模型取名。

模型一律 mock 掉——真正要驗的是「名字過了過濾才登記、模型只給名字」這件事本身。
"""
from unittest import mock

import pytest

from tianxia import naming


def named(*names):
    client = mock.Mock()
    client.chat_structured.side_effect = [naming.NameReply(name=n, description="一句話。") for n in names]
    return client


MESSAGES = [{"role": "user", "content": "取個名字"}]


@pytest.mark.parametrize("raw", ["【龍吟九霄】", " 龍吟九霄 ", "「龍吟九霄」"])
def test_clean_name_strips_the_wrapping(raw):
    assert naming.clean_name(raw) == "龍吟九霄"


def test_clean_name_converts_simplified_characters():
    assert naming.clean_name("龙吟九霄") == "龍吟九霄"


@pytest.mark.parametrize(
    ("name", "why"),
    [("一", "長度"), ("七個字的功法名稱", "長度"), ("Fist", "中文"), ("劍法X", "中文"), ("九陰真經", "專有名詞"),
     ("小龍女心法", "專有名詞")],
)
def test_bad_names_are_rejected(content, name, why):
    assert naming.name_problem(name, content) is not None, why


def test_a_name_that_collides_with_content_is_rejected(content):
    assert naming.name_problem("精鐵砂", content) is not None  # 素材
    assert naming.name_problem("長拳", content) is not None  # 內容裡的武學


def test_an_insight_name_is_taken_even_when_long_enough(content):
    from tianxia.models import InsightDef

    content.insights["long"] = InsightDef(id="long", name="長風破浪", attribute="快", desc="一句話。")
    assert "意境" in naming.name_problem("長風破浪", content)


def test_a_good_name_passes(content):
    assert naming.name_problem("裂江訣", content) is None


def test_the_fallback_name_is_deterministic_and_passes_the_filter(content):
    first = naming.fallback_name(content, "融|basic_fist+feng", "武學")
    assert first == naming.fallback_name(content, "融|basic_fist+feng", "武學")
    assert naming.name_problem(first, content) is None


def test_the_fallback_name_differs_by_kind_and_salt(content):
    key = "融|basic_fist+feng"
    assert naming.fallback_name(content, key, "武學") != naming.fallback_name(content, key, "內功")
    assert naming.fallback_name(content, key, "武學") != naming.fallback_name(content, key, "武學", salt=1)


def test_the_fallback_name_for_an_insight_ends_with_an_insight_suffix(content):
    name = naming.fallback_name(content, "合|feng+huo", "意境")
    assert name[-1] in content.craft_names.insight and name[:-1] in content.craft_names.prefixes


def test_propose_returns_the_cleaned_name_and_note(content):
    name, note = naming.propose(named("「裂江诀」"), content, MESSAGES)
    assert (name, note) == ("裂江訣", "一句話。")


def test_propose_retries_a_bad_name_then_gives_up(content):
    client = named("九陰真經", "九陰真經", "九陰真經", "裂江訣")
    assert naming.propose(client, content, MESSAGES) == (None, "")
    assert client.chat_structured.call_count == naming.NAME_ATTEMPTS
    assert naming.propose(named("九陰真經", "裂江訣"), content, MESSAGES)[0] == "裂江訣"


def test_propose_without_a_client_or_with_the_model_down_asks_for_the_fallback(content):
    assert naming.propose(None, content, MESSAGES) == (None, "")
    down = mock.Mock()
    down.chat_structured.side_effect = RuntimeError("連不上")
    assert naming.propose(down, content, MESSAGES) == (None, "")
    nothing = mock.Mock()
    nothing.chat_structured.return_value = None
    assert naming.propose(nothing, content, MESSAGES) == (None, "")


def test_the_prompt_never_asks_for_numbers():
    assert "絕對不要提到任何數字" in naming.SYSTEM_PROMPT
    assert not hasattr(naming.NameReply(name="甲乙"), "base_power")
