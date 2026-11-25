"""異聞二（第 252 批）：模型寫的一幕的程式檢查（rules.check_scene，設計 5.1）——每一條一個代碼。"""
import pytest

from tianxia.features.yiwen import rules

OPENING = {"id": "fog_figure", "title": "霧裡的身影", "hook": "前面濃霧瀰漫，隱約看到一個身影⋯"}
A = "你撥開霧，看清那是一隊官軍，領頭的瞪你一眼。"
B = "隊尾有個小兵偷偷朝你招手，手裡攥著一封信。"


def _draft(**over):
    d = rules.SceneDraft(text=[A, B], options=["接過那封信", "瞪回去", "學鵝叫"], ledger=["在場：你、官軍", "你手上：無", "未了：那封信"])
    for k, v in over.items():
        setattr(d, k, v)
    return d


@pytest.fixture
def content(game, monkeypatch):
    c = game.content
    monkeypatch.setattr(c, "banned_words", ["白癡"])
    monkeypatch.setattr(rules, "figure_names", lambda _c: ["曹操"])
    return c


def _codes(content, depth=1, typed=(), **over):
    return rules.check_scene(_draft(**over), depth=depth, opening=OPENING, typed_words=typed, content=content)


def test_a_good_scene_passes(content):
    assert _codes(content) == []
    assert _codes(content, depth=3, options=[], ledger=[]) == []


@pytest.mark.parametrize(("code", "over", "depth", "typed"), [
    pytest.param("paras", {"text": [A]}, 1, (), id="段數"),
    pytest.param("length", {"text": [A, "你好"]}, 1, (), id="字數"),
    pytest.param("no_you", {"text": ["霧裡走出一隊官軍，領頭的瞪了一眼。", "隊尾有個小兵偷偷招手，手裡攥著一封信。"]}, 1, (), id="沒有你"),
    pytest.param("modern", {"text": [A, "小兵說這是一項任務，你要接下來嗎？快點決定。"]}, 1, (), id="現代詞"),
    pytest.param("jump", {"text": [A, "一夜過去，你醒來時小兵已經站在你面前。"]}, 1, (), id="跳時間"),
    pytest.param("turn", {"text": [A, "領頭的拍拍你的肩膀，當場收你入伍，你成了官軍。"], "options": [], "ledger": []}, 3, (), id="第三步身分改變"),
    pytest.param("digit", {"text": [A, "小兵塞給你3封信，你一封一封拆開來看。"]}, 1, (), id="阿拉伯數字"),
    pytest.param("kana", {"text": [A, "小兵朝你喊了一聲ありがとう，轉身就跑。"]}, 1, (), id="假名"),
    pytest.param("latin", {"text": [A, "小兵朝你比了個OK的手勢，轉身就跑開。"]}, 1, (), id="夾英文"),
    pytest.param("words", {"text": [A, "小兵指著你罵了一句白癡，轉身就跑開了。"]}, 1, (), id="字表"),
    pytest.param("figure", {"text": [A, "領頭的說他就是曹操，你愣了一下。好嚇人。"]}, 1, (), id="大勢人物名"),
    pytest.param("options", {"options": ["接過那封信", "接過那封信", "學鵝叫"]}, 1, (), id="做法三個不重複"),
    pytest.param("ledger", {"ledger": ["在場：你、官軍", "你手上：無", "你知道：信"]}, 1, (), id="帳有未了"),
])
def test_check_codes(content, code, over, depth, typed):
    assert code in _codes(content, depth=depth, typed=typed, **over)


def test_figure_name_the_player_typed_is_let_through(content):
    text = [A, "領頭的說他就是曹操，你愣了一下。好嚇人。"]
    assert "figure" in _codes(content, text=text)
    assert "figure" not in _codes(content, text=text, typed=("他是曹操",))


def test_figure_names_come_from_the_real_figure_table():
    from conftest import real_content

    assert len(rules.figure_names(real_content("season21"))) >= 3


def test_latin_in_the_hook_or_typed_words_is_let_through(content):
    text = [A, "小兵朝你喊著Rayal，轉身就跑開了。真怪。"]
    assert "latin" in _codes(content, text=text)
    assert "latin" not in _codes(content, text=text, typed=("叫Rayal的人",))
