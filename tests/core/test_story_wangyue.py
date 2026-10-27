"""《王越的劍》長版（content/storylines.json 的 wangyue，scripts/story/gen_wangyue.py 產生）：洛陽官道探索擲中就開，
十段（七幕、第四幕的夜裡、第五幕三天）走到四個結局。前面的選擇在後面收回：第一幕的話在尾聲由阿蘅說出來，
第二、三幕的話在第七幕門前說回來；第五幕贖不贖劍決定第六幕有哪一顆；第七幕攔、讓、說一句分出遠、字、名，沒到場走晚。
用正式內容（season21），整個檔標 slow。"""
from __future__ import annotations

from unittest import mock

import pytest
from jianfa_kit import jianfa_game, ready

from tianxia import annals, explore_one, storyline, team
from tianxia.encounter import EncounterResult
from tianxia.models import Condition
from tianxia.rules import check_condition, day_seconds

pytestmark = pytest.mark.slow

L = "wangyue"
ROAD, HILL, TEMPLE, PALACE = "luoyang_road", "beimang_hill", "baima_temple", "luoyang_palace"


def _start(game):
    """洛陽官道探索、擲中（chance 照 1、第 2 週起的條件拿掉）就開，端出第一幕。"""
    start = game.content.storylines[L].start
    start.chance, start.condition = 1.0, Condition()
    with mock.patch.object(explore_one, "draw", return_value=explore_one.MATERIAL):
        game.choose("act:explore")
    assert game.state.pending_event == "wangyue_1"
    return game.state.player.storylines[L]


def _go(game, loc: str, wait: float, event: str):
    """等過這一段的 wait_days、走到 loc、按「未了之事」那一顆，端出 event。"""
    s = game.state
    s.world.time += int(wait * day_seconds(game.content, s.world)) + 1
    s.player.location, s.player.journey = loc, None
    game.choose(f"story:{L}")
    assert s.pending_event == event


def _say(game, text: str, rate: int, roll: float) -> list[str]:
    request = game.free_text_request(text)
    assert request is not None
    with mock.patch("random.Random.random", return_value=roll):
        return game.answer_event(request, llm_rate=rate, moral="中")


def _annal(game, ending: str) -> str:
    """寫進傳的那一句：照記號拼好的底稿（行狀照 annals.TEXT_MAX 截，存進去的是它的開頭）。"""
    p = game.state.player
    full = storyline.vary(game.content.storylines[L].ending(ending).annal, game.state).replace("{name}", p.name)
    assert p.annals[-1].text == annals.clip(full, annals.TEXT_MAX)
    return full


def _fight(won: bool):
    tier, margin = ("大勝", 50) if won else ("落敗", -50)
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=margin, our_power=100, difficulty=40))


def test_the_line_opens_only_from_the_second_week_on_the_luoyang_road():
    game = ready(jianfa_game(), side="guan", loc=ROAD)
    line = game.content.storylines[L]
    assert line.start.where.locations == [ROAD] and line.start.chance == 0.08
    assert not check_condition(line.start.condition, game.state, game.content)  # 開季第一天
    game.state.world.time += 8 * day_seconds(game.content, game.state.world)
    assert check_condition(line.start.condition, game.state, game.content)


def test_letting_go_after_telling_him_of_the_dowry_ends_in_the_four_characters_and_the_single_edged_sword():
    game = ready(jianfa_game(), side="guan", loc=ROAD)
    s, p = game.state, game.state.player
    progress = _start(game)
    game.choose("choice:1")  # 讓它死當
    assert progress.stage == "act2" and progress.marks == {"死當": 1}
    assert s.pending_event is None  # 隔天才接第二幕
    _go(game, ROAD, 0.5, "wangyue_2")
    game.choose("choice:0")  # 給餅
    _go(game, HILL, 0.25, "wangyue_3")
    game.choose("choice:2")  # 問史阿數什麼
    _go(game, TEMPLE, 0, "wangyue_4")
    game.choose("choice:1")  # 留在廊下
    assert s.pending_event == "wangyue_4b" and "廊下只剩下王越" in storyline.vary(game.content.events["wangyue_4b"].text, s)
    game.choose("choice:0")  # 勸
    _go(game, HILL, 0.25, "wangyue_4n")
    game.choose("choice:0")
    _go(game, ROAD, 0.5, "wangyue_5a")
    p.stats["silver"] = 0
    assert "choice:0" not in [o.id for o in game.options(odds=False)]  # 沒有三十銀：贖不了
    game.choose("choice:1")  # 妳自己去贖
    _go(game, PALACE, 0.5, "wangyue_5b")
    game.choose("choice:0")  # 告范
    _go(game, HILL, 0.5, "wangyue_5c")
    assert "choice:0" in [o.id for o in game.options(odds=False)]  # 記了「數」：可以教史阿左腳
    game.choose("choice:0")
    _go(game, ROAD, 0.5, "wangyue_6")
    ids = [o.id for o in game.options(odds=False)]
    assert "choice:0" in ids and "choice:1" not in ids  # 不贖：有「點破」、沒有「末油」
    game.choose("choice:0")  # 是她的嫁妝
    s.player.location = PALACE
    game.choose(f"story:{L}")
    assert s.pending_event == "wangyue_7"
    text = storyline.vary(game.content.events["wangyue_7"].text, s)
    assert "握得指節發白" in text and "你來了" in text and "只有風" not in text
    msgs = game.choose("choice:2")  # 退到一邊
    assert any("拿嫁妝贖的" in m for m in msgs)
    assert progress.ending == "zi" and "市井第一" in "".join(msgs)
    assert "單刃" in p.keepsakes and "蓋了「贖訖」的當票存根" not in p.keepsakes
    annal = _annal(game, "zi")
    assert annal.startswith(f"中平元年，{p.name}客洛陽。") and f"當肆女以奩資贖之，{p.name}以告越。" in annal
    assert f"{p.name}先以告范公，公不去。" in annal and f"越遂解所藏單刃劍以贈{p.name}" in annal


def test_free_words_come_back_at_the_door_and_a_failed_last_word_ends_in_the_name():
    game = ready(jianfa_game(), side="guan", loc=ROAD)
    s, p = game.state, game.state.player
    progress = _start(game)
    _say(game, "他看的是妳", rate=80, roll=0.0)
    assert progress.stage == "act2" and progress.said == ["他看的是妳"]
    _go(game, ROAD, 0.5, "wangyue_2")
    _say(game, "跟緊你師父", rate=80, roll=0.0)
    _go(game, HILL, 0.25, "wangyue_3")
    with _fight(False):
        game.choose("choice:1")  # 空手領教，輸了也記「交手」
    assert progress.marks.get("交手") == 1 and "交手勝" not in progress.marks
    _go(game, TEMPLE, 0, "wangyue_4")
    with mock.patch("random.Random.random", return_value=0.0):
        game.choose("choice:0")  # 跟上邵管事（身法）
    assert s.pending_event == "wangyue_4b" and progress.marks.get("跟蹤") == 1
    silver, evil = p.stats.get("silver", 0), p.stats.get("evil", 0)
    game.choose("choice:1")  # 拿錢
    assert p.stats["silver"] == silver + 30 and p.stats["evil"] == evil + 2
    _go(game, HILL, 0.25, "wangyue_4n")
    game.choose("choice:0")
    _go(game, ROAD, 0.5, "wangyue_5a")
    p.stats["silver"] = 30
    msgs = game.choose("choice:0")  # 贖劍：花的是邵管事那包裡真的三十銀
    assert p.stats["silver"] == 0 and "蓋了「贖訖」的當票存根" in p.keepsakes
    assert any("香爐的味道" in m for m in msgs)
    _go(game, PALACE, 0.5, "wangyue_5b")
    _say(game, "他會先看劍", rate=80, roll=0.0)
    _go(game, HILL, 0.5, "wangyue_5c")
    assert "choice:0" not in [o.id for o in game.options(odds=False)]  # 沒看懂也沒數：教不了史阿
    game.choose("choice:2")  # 跟緊他
    _go(game, ROAD, 0.5, "wangyue_6")
    ids = [o.id for o in game.options(odds=False)]
    assert "choice:1" in ids and "choice:0" not in ids  # 贖了劍：有「末油」、沒有「點破」
    game.choose("choice:1")
    s.player.location = PALACE
    game.choose(f"story:{L}")
    text = storyline.vary(game.content.events["wangyue_7"].text, s)
    assert "『跟緊你師父』。我記得。" in text  # 第二幕的話：史阿說回來
    assert "手上纏布的人" in text and "跟王越只隔一步" in text and "只有風" not in text
    assert "有人說。" not in text  # 第三幕沒寫話
    labels = [(o.id, o.label) for o in game.options(odds=False)]
    assert ("choice:0" not in [i for i, _ in labels]) and "choice:1" in [i for i, _ in labels]  # 交過手：對上的是見過的那一個
    msgs = _say(game, "天下劍術王越第一", rate=10, roll=0.99)  # 不成
    assert progress.ending == "ming" and any("不是這句。" in m for m in msgs)
    assert "牆上的釘子" in p.keepsakes
    annal = _annal(game, "ming")
    assert f"{p.name}以三十銀贖其劍。" in annal and f"{p.name}受張氏金，不辭。" in annal
    assert f"{p.name}嘗與越搏於北邙墓間。" in annal and f"{p.name}謂之曰：『天下劍術王越第一』越不顧。" in annal
    # 餘波：兩週後回到當鋪，阿蘅拔下釘子，說出第一幕那一句
    s.world.time += 15 * day_seconds(game.content, s.world)
    s.player.location = ROAD
    game._story_tick()  # 一週後・市口
    msgs = game._story_tick()  # 兩週後・當鋪
    assert any("『他看的是妳』。你說得對，也不對。" in m for m in msgs)


def test_beating_him_at_the_door_sends_him_north_and_missing_the_night_is_too_late():
    game = ready(jianfa_game(), side="guan", loc=ROAD)
    s = game.state
    progress = _start(game)
    game.choose("choice:0")
    for loc, wait, ev, pick in [(ROAD, 0.5, "wangyue_2", 2), (HILL, 0.25, "wangyue_3", 2), (TEMPLE, 0, "wangyue_4", 1)]:
        _go(game, loc, wait, ev)
        game.choose(f"choice:{pick}")
    game.choose("choice:2")  # 隨
    _go(game, HILL, 0.25, "wangyue_4n")
    game.choose("choice:0")
    for loc, ev, pick in [(ROAD, "wangyue_5a", 1), (PALACE, "wangyue_5b", 1), (HILL, "wangyue_5c", 1), (ROAD, "wangyue_6", 2)]:
        _go(game, loc, 0.5, ev)
        game.choose(f"choice:{pick}")
    assert progress.stage == "act7"
    s.player.location = PALACE
    game.choose(f"story:{L}")
    with _fight(True):
        assert "choice:1" not in [o.id for o in game.options(odds=False)]  # 只記了「數」：沒有見過劍的那一顆
        msgs = game.choose("choice:0")
    assert progress.ending == "yuan" and any("不回了" in m for m in msgs)
    assert "阿蘅的油布" in s.player.keepsakes
    assert _annal(game, "yuan").endswith("北之遼東，終身不復入洛。")
    # 另一個人：第六幕之後當夜沒到巷子裡，過了期限走「晚」
    other = ready(jianfa_game(name="陸小鳳"), side="guan", loc=ROAD)
    pr = _start(other)
    pr.stage = "act6"
    pr.marks = {"告范": 1}
    storyline._enter(other.state, other.content, pr, other.content.storylines[L], "act7")
    other.state.pending_event = None
    other.state.world.time += 2 * day_seconds(other.content, other.state.world)
    other._story_tick()
    assert pr.ending == "wan" and other.state.player.story_cards[-1].failed
    other.state.world.time += 3 * day_seconds(other.content, other.state.world)
    other.state.player.location = PALACE
    msgs = other._story_tick()
    assert any("門不鎖。來過了。" in m for m in msgs)
