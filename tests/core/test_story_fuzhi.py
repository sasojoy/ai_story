"""長篇奇事《符水與湯藥》（企劃者 2026-10-27 的長版，取代三幕的短版）：用正式內容走湯藥（她選）、符水、遲三條路，
看前面的記號與自己寫的話在後面收回來、傳的中段最多兩句、餘波、紀念物、仲景欠你一次。整個檔標 slow。"""
from __future__ import annotations

from unittest import mock

import pytest
from jianfa_kit import jianfa_game, ready

from tianxia import storyline, team
from tianxia.encounter import EncounterResult
from tianxia.rules import day_seconds, fill_marks

pytestmark = pytest.mark.slow

WILDS, WAN, ROAD, XINYE = "nanyang_wilds", "wan_city", "nanyang_road", "xinye"


def _pick(game, words: str) -> list[str]:
    """按眼前選單上寫著 words 的那一顆（按得下去的）。"""
    for opt in game.options():
        if words in opt.label and opt.enabled:
            return game.choose(opt.id)
    raise AssertionError(f"沒有「{words}」：{[o.label for o in game.options()]}")


def _labels(game) -> list[str]:
    return [o.label for o in game.options() if o.enabled]


def _say(game, text: str) -> None:
    """隨口應對（不叫模型：成功率直接給）；故事的隨口應對成敗都走同一步。"""
    game.answer_event(game.free_text_request(text), 80)


def _go(game, loc: str, days: float = 0) -> None:
    s = game.state
    s.player.location, s.player.journey = loc, None
    s.world.time += days * day_seconds(game.content, s.world) + 1


def _fight(tier: str):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


def _begin(silver: int = 0):
    game = ready(jianfa_game(), side="guan", loc=WILDS, level=20)
    game.state.player.stats["silver"] = silver
    game._story_begin(game.content.storylines["fuzhi"])
    assert game.state.pending_event == "fuzhi_1"
    return game


def _next(game, loc: str, days: float = 0) -> None:
    _go(game, loc, days)
    _pick(game, "未了之事")


def test_tang_she_path_quotes_what_was_said_and_pays_back_at_the_clinic():
    game = _begin(silver=100)
    s = game.state
    progress = s.player.storylines["fuzhi"]
    _say(game, "爹在家等你")  # 第一幕：對石頭說
    assert progress.stage == "act2" and progress.marks == {"話1": 1}
    assert not any("未了之事" in o.label for o in game.options())  # 入夜以前沒有那一顆
    _next(game, WILDS, 0.3)
    _pick(game, "熱一碗粥")
    assert "一截甘草" in s.player.keepsakes
    _next(game, WAN)
    _pick(game, "付六十銀")
    assert s.player.stats["silver"] == 40 and s.pending_event == "fuzhi_3b"
    _say(game, "總有一天試得準")  # 第三幕：回答杜度
    assert progress.stage == "act4"
    _next(game, ROAD)
    assert "十里鋪" not in fill_marks(game.content.events["fuzhi_4"].text, s)  # 買的，不是採的
    with _fight("大勝"):
        _pick(game, "打一場")
    assert progress.stage == "day1"  # 藥全
    _next(game, WILDS)
    text = fill_marks(game.content.events["fuzhi_5a"].text, s)
    assert "你那天跟他說『爹在家等你』" in text and "十劑" in text
    _pick(game, "不說")
    _next(game, WILDS, 0.6)
    _pick(game, "陪他坐到天亮")
    _next(game, WILDS, 0.6)
    _pick(game, "說草的名字")
    _next(game, XINYE)
    _pick(game, "連夜趕回柳灣")
    _next(game, WILDS)
    assert s.pending_event == "fuzhi_7"  # 報信：宋嫂擋掉亭長，不用打
    text = fill_marks(game.content.events["fuzhi_7"].text, s)
    assert "他有兩隻手" in text and "石頭是喝我的藥好的" in text and "塞進灶膛裡" in text and "麻黃。桂枝。" in text
    assert "按著死人的下巴" not in text
    assert any("讓她自己說" in label for label in _labels(game))  # 記了草名才有
    msgs = _pick(game, "讓她自己說")
    assert progress.ending == "tang_she"
    assert any("其父親手餵之" in m for m in msgs)
    assert "zhongjing_owes" in s.player.flags and "仲景的方子" in s.player.keepsakes
    note = s.player.annals[-1].text
    # 中段最多兩句：守夜、藥全；報信那一句排第三，不寫
    assert "執其手以守其夜" in note and "全其藥而還" in note and "騰夜馳告之" not in note
    assert "使女自擇之" in note and "{" not in note
    # 兩週後在醫館：信裡讀回第三幕寫的那一句（前面只寫過第一幕那一句）
    s.player.story_cards = []
    _go(game, WAN, 14)
    storyline.tick(s, game.content, game.world)
    letter = [c for c in s.player.story_cards if c.kind == "after"]
    assert len(letter) == 1 and "我欠你一次" in letter[0].text
    assert "客人那天說『總有一天試得準』" in letter[0].text and "給了甘草" in letter[0].text
    _go(game, WILDS)
    storyline.tick(s, game.content, game.world)
    assert "頭髮用一根草繩紮著" in s.player.story_cards[-1].text  # 三天後那一段（報信）


def test_fu_path_after_beating_the_constable_and_late_when_the_night_passes():
    game = _begin()
    s = game.state
    progress = s.player.storylines["fuzhi"]
    _pick(game, "按住那具屍身的下巴")
    _next(game, WILDS, 0.3)
    _pick(game, "推門進去")
    _next(game, WAN)
    assert not any("付六十銀" in label or "後面咳嗽的是誰" in label for label in _labels(game))  # 沒錢：只剩採藥
    _pick(game, "採野麻黃")
    _pick(game, "沒有回答")
    _next(game, ROAD)
    assert "十里鋪的坡上" in fill_marks(game.content.events["fuzhi_4"].text, s)
    with _fight("落敗"):
        msgs = _pick(game, "打一場")
    assert any("只剩一半" in m for m in msgs) and progress.stage == "day1h"
    _next(game, WILDS)
    assert "四劑" in fill_marks(game.content.events["fuzhi_5h"].text, s)
    _pick(game, "什麼也不說")
    _next(game, WILDS, 0.6)
    _pick(game, "你的水，救過誰")
    _next(game, WILDS, 0.6)
    _pick(game, "抱她去找仲景")
    assert not any("讓她自己說" in label for label in _labels(game))
    _next(game, XINYE)
    _pick(game, "什麼都不做")
    _next(game, WILDS)
    assert s.pending_event == "fuzhi_7f"
    text = fill_marks(game.content.events["fuzhi_7f"].text, s)
    assert "就是他" in text and "按著死人的下巴" in text and "那不是水" in text
    with _fight("大勝"):
        _pick(game, "對上賈亭長")
    assert s.pending_event == "fuzhi_7b"
    _pick(game, "讓她喝符水")
    assert progress.ending == "fu"
    assert "阿蒲的小葫蘆" in s.player.keepsakes and "zhongjing_owes" not in s.player.flags
    note = s.player.annals[-1].text
    assert "助機驗死者" in note and "全其藥" not in note and "其端在此冊云" in note

    late = _begin()
    pr = late.state.player.storylines["fuzhi"]
    storyline._enter(late.state, late.content, pr, late.content.storylines["fuzhi"], "act7")
    _go(late, ROAD, 2)  # 一天內沒回柳灣
    storyline.tick(late.state, late.content, late.world)
    assert pr.ending == "late" and "阿蒲的小葫蘆" in late.state.player.keepsakes
    assert [c for c in late.state.player.story_cards if c.kind == "end"][-1].failed
