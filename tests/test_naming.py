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


def test_the_fallback_name_is_seeded_by_this_seasons_tianji(content):
    """最終審查 Critical 1（Infra 第 3 點）：退路字表的種子是配方鍵＋這一季的天機；天機 0（第一季）照舊的種子，
    名字跟以前一樣——同一個配方每季長出不同的名字，跟 generate_from_name 的天機同一個規矩。"""
    key = "融|basic_fist+feng"
    assert naming.fallback_name(content, key, "武學", tianji=0) == naming.fallback_name(content, key, "武學")
    names = {naming.fallback_name(content, key, "武學", tianji=t) for t in range(6)}
    assert len(names) > 1
    assert all(naming.name_problem(n, content) is None for n in names)


class Timed:
    """記下每一次呼叫時 client 的 timeout（秒）；replies 依序回，用完就丟 RuntimeError（當作逾時）。"""

    def __init__(self, timeout, *replies):
        self.timeout = timeout
        self.replies = list(replies)
        self.seen = []

    def chat_structured(self, messages, response_model, **kwargs):
        self.seen.append(self.timeout)
        if not self.replies:
            raise RuntimeError("逾時")
        return naming.NameReply(name=self.replies.pop(0), description="一句話。")


def _calls(client):
    """propose 有預算時拿 client 的複本去叫（改複本的 timeout，不動原本那個）：記錄在原本那個的 seen 裡。"""
    return client.seen


def test_a_budget_caps_every_call_so_the_whole_naming_fits_inside_it(content):
    """最終審查 Critical 1：首次取名在鎖外跑，但整個請求要在 trycloudflare 約 100 秒的斷線前結束。propose 拿到 budget（秒）：
    每一次呼叫的 timeout 是 min(client.timeout, 剩下的一半)——chat_structured 一次最多送兩趟（第一次＋格式不對的重問），
    兩趟都用完也不會超過剩下的；剩下的不夠一次就不叫了，回 (None, "") 走退路字表。不看時鐘：預算照給出去的 timeout 扣。"""
    slow = Timed(120, "九陰真經", "裂江訣")  # 第一次取壞了：剩下的預算不夠再叫一次
    assert naming.propose(slow, content, MESSAGES, budget=60) == (None, "")
    assert _calls(slow) == [30.0] and slow.timeout == 120  # 原本那個 client 的 timeout 沒被改
    quick = Timed(10, "九陰真經", "九陰真經", "裂江訣")  # client 自己的 timeout 短：預算夠叫滿三次
    assert naming.propose(quick, content, MESSAGES, budget=60) == ("裂江訣", "一句話。")
    assert _calls(quick) == [10, 10, 10]
    assert sum(2 * t for t in _calls(quick)) <= 60


def test_an_empty_budget_never_calls_the_model(content):
    client = Timed(120, "裂江訣")
    assert naming.propose(client, content, MESSAGES, budget=0) == (None, "")
    assert naming.propose(client, content, MESSAGES, budget=1.5) == (None, "")  # 一趟不到一秒：不叫
    assert _calls(client) == []


def test_without_a_budget_propose_keeps_the_clients_own_timeout(content):
    client = Timed(120, "九陰真經", "裂江訣")
    assert naming.propose(client, content, MESSAGES) == ("裂江訣", "一句話。")
    assert _calls(client) == [120, 120]


def test_generate_takes_the_prepared_request_and_returns_the_name_and_note(content):
    """B 段（鎖外、很慢）是單獨一個函式：進來的是 A 段的單子，出去的是（名字, 說明）；不碰狀態、不拿鎖
    （之後線上架構第 2 期的模型佇列只換掉這一段）。"""
    request = naming.NamingRequest(kind="fuse", key="融|basic_fist+feng", name_kind="武學", messages=MESSAGES)
    client = Timed(120, "「裂江诀」")
    assert naming.generate(client, content, request, budget=60) == ("裂江訣", "一句話。")
    assert naming.generate(None, content, request, budget=60) == (None, "")


@pytest.mark.parametrize(("proposed", "expected"), [
    (("「裂江诀」", "说明"), ("裂江訣", "說明")),  # 繁體、去掉包裝
    (("九陰真經", "一句話。"), (None, "")),  # 禁用詞
    (("長拳", "一句話。"), (None, "")),  # 跟內容裡的武學同名
    ((None, ""), (None, "")),
])
def test_a_name_from_outside_the_lock_is_filtered_again(content, proposed, expected):
    """C 段（鎖內）登記之前把鎖外拿到的名字再過一次完整的過濾（整理、繁體與異體字、禁用詞、跟內容同名）；
    全服重名留給登記時原子判斷（world.claim_*）。過不了就當沒取到名字。"""
    assert naming.recheck(content, proposed) == expected


def test_the_prompt_never_asks_for_numbers():
    assert "絕對不要提到任何數字" in naming.SYSTEM_PROMPT
    assert not hasattr(naming.NameReply(name="甲乙"), "base_power")
