"""異聞二（第 252 批）：自己說的五道擋（設計 5.4；rules.typed_problem 是前四道，第五道審字在 B 段）。
被擋一律回 refuse_typed 那一組（試不出是哪一道擋的），A 段擋的不加 tries。"""
import pytest

from tianxia import speech
from tianxia.features.yiwen import actions, rules

from yiwen_kit import claim, turn_on, use_test_lines

OPENING = "fog_figure"


@pytest.fixture
def on(game, monkeypatch):
    use_test_lines(monkeypatch)
    turn_on(game)
    game.content.config.yiwen.discover_chance = 0.0
    monkeypatch.setattr(game.content, "banned_words", ["白癡"])
    monkeypatch.setattr(game.content, "banned_names", ["蕭十一郎"])
    return game


CASES = [
    pytest.param("", id="空的"),
    pytest.param("鵝" * 31, id="太長"),
    pytest.param("那是個白癡", id="字表"),
    pytest.param("請上 www.abc.com 看", id="網址"),
    pytest.param("打 0912345678 找我", id="六位數字"),
    pytest.param("官方說的", id="staff_like"),
    pytest.param("公告：天亮開城", id="公告"),
]


@pytest.mark.parametrize("text", CASES)
def test_each_filter_answers_refuse_typed(on, text):
    t = on.content.config.yiwen
    assert rules.typed_problem(speech.clean(text), on.content, t) is not None
    w = claim(on, OPENING)
    before = on.state.model_dump_json()
    got = actions.step(on, {"tale": 0, "opening": OPENING, "node": 0, "pick": "typed", "text": text})
    assert len(got) == 1 and got[0] in rules.lines()["refuse_typed"]
    assert w.tries == 0 and on.state.model_dump_json() == before  # A 段擋的：不寫、不加 tries


def test_banned_names_only_when_switched_on(on):
    t = on.content.config.yiwen
    on.content.config.banned_names_on = False
    assert rules.typed_problem("蕭十一郎來了", on.content, t) is None
    on.content.config.banned_names_on = True
    assert rules.typed_problem("蕭十一郎來了", on.content, t) == "banned"
    assert rules.typed_problem("蕭 十一郎來了", on.content, t) == "banned"
    on.content.config.banned_names_on = False


def test_a_good_line_passes(on):
    t = on.content.config.yiwen
    assert rules.typed_problem("一隻會背兵法的鵝", on.content, t) is None
    assert rules.typed_problem("鵝" * 30, on.content, t) is None
    assert rules.typed_problem("上官方正在霧裡", on.content, t) is None  # 複姓上官開頭放行（第 245 批）


@pytest.mark.parametrize("text", ["ＧＭ說的", "g m 來了", "官 方說的", "Gm大人", "天下 大勢的使者", "公　告"])
def test_staff_words_fullwidth_and_case(on, text):
    assert rules.typed_problem(speech.clean(text), on.content, on.content.config.yiwen) == "staff"
