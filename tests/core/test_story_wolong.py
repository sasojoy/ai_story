"""長篇奇事《臥龍岡的地》（企劃者 2026-10-27）：用正式內容走三條路（岡上藏書、絹成灰、來不及），
看記號換段落、紀念物、跨季旗標、餘波與傳。整個檔標 slow。"""
from __future__ import annotations

import pytest
from jianfa_kit import jianfa_game, ready

from tianxia import storyline
from tianxia.rules import day_seconds, fill_marks

pytestmark = pytest.mark.slow

ACADEMY, RIVER, ROAD, XINYE, HILL = "yingchuan_academy", "yingshui", "nanyang_road", "xinye", "nanyang_wilds"


def _pick(game, words: str) -> list[str]:
    """按眼前選單上寫著 words 的那一顆（按得下去的）。"""
    for opt in game.options():
        if words in opt.label and opt.enabled:
            return game.choose(opt.id)
    raise AssertionError(f"沒有「{words}」：{[o.label for o in game.options()]}")


def _labels(game) -> list[str]:
    return [o.label for o in game.options()]


def _go(game, loc: str, days: float = 0) -> None:
    s = game.state
    s.player.location, s.player.journey = loc, None
    s.world.time += days * day_seconds(game.content, s.world) + 1


def _step(game, loc: str, words: str, days: float = 0) -> list[str]:
    _go(game, loc, days)
    _pick(game, "未了之事")
    return _pick(game, words)


def _begin(silver: int = 0):
    game = ready(jianfa_game(), side="guan", loc=ACADEMY, level=20)
    game.state.player.stats["silver"] = silver
    game._story_begin(game.content.storylines["wolong"])
    assert game.state.pending_event == "wolong_1"
    return game


def _progress(game):
    return game.state.player.storylines["wolong"]


def test_silk_path_with_praise_dates_and_the_quiet_hour_burns_the_list():
    game = _begin()
    s = game.state
    _pick(game, "寫得很好")
    _step(game, RIVER, "吃掉那顆棗")
    assert "宋母的乾棗" in s.player.keepsakes
    _step(game, ROAD, "分他們乾棗", 0.3)  # 有乾棗才有這一顆；記「分棗」，地保住了
    assert _progress(game).marks.get("地") == 1
    _step(game, XINYE, "假裝沒醒")
    _go(game, XINYE)
    assert not any("未了之事" in label for label in _labels(game))  # 渡口要等到第二天
    _go(game, XINYE, 0.3)
    _pick(game, "未了之事")
    assert "我一直知道" not in " ".join(_labels(game))  # 沒偷看過
    text = fill_marks(game.content.events["wolong_5"].text, s)
    assert "渡口的茶棚裡" in text and "半夜你聽見車動" not in text
    _pick(game, "什麼也不說，坐到他旁邊")
    _step(game, HILL, "跟著他的手指")
    _step(game, HILL, "讓他一個人待一會兒", 0.6)
    _go(game, HILL, 0.6)
    _pick(game, "未了之事")
    text = fill_marks(game.content.events["wolong_7"].text, s)
    assert "那一隻好眼睛看著鄭家的家丁" in text and "他手裡拿著那卷農書" in text
    msgs = _pick(game, "讓宋季自己決定")  # 讚＋留白兩個：燒絹
    assert any("抄錯了" in m for m in msgs)
    progress = _progress(game)
    assert progress.ending == "silk"
    end = [c for c in s.player.story_cards if c.kind == "end"][-1]
    assert "地還在黃老手上" in end.text and not end.failed
    note = s.player.annals[-1].text
    assert "焚其父所遺告密之絹" in note and "云宋母所贈" in note and "{" not in note
    assert "隆中藏書" not in s.player.lasting
    # 餘波：老耿在新野；三天後
    s.player.story_cards = []
    _go(game, XINYE, 3)
    storyline.tick(s, game.content, game.world)
    after = [c for c in s.player.story_cards if c.kind == "after"]
    assert len(after) == 1 and "老耿" in after[0].text


def test_shelf_path_after_reading_the_letter_and_handing_the_list_to_achou():
    game = _begin()
    s = game.state
    _pick(game, "什麼也不說，把簡還給他")
    _step(game, RIVER, "我會把他帶回來")
    assert "宋母的乾棗" not in s.player.keepsakes
    _go(game, ROAD, 0.3)
    _pick(game, "未了之事")
    assert not any("分他們乾棗" in label for label in _labels(game))  # 沒吃那顆棗：沒有乾棗可分
    _pick(game, "讓宋季念")
    _go(game, XINYE)
    _pick(game, "未了之事")
    s.player.stats["agi"] = 30  # 偷看要身法
    s.player.stats["good"] = good = 5  # 善名夾在 0：先給一點，看得出偷看扣的那 1
    _pick(game, "從麻布裡把那封信拿出來看")
    assert s.pending_event == "wolong_4b" and s.player.stats["good"] == good - 1
    _pick(game, "在貨郎走之前把信攔下來")
    _go(game, XINYE, 0.3)
    _pick(game, "未了之事")
    text = fill_marks(game.content.events["wolong_5"].text, s)
    assert "半夜你聽見車動" in text and "渡口的茶棚裡" not in text
    _pick(game, "我一直知道")
    _step(game, HILL, "跟著他的手指")
    _step(game, HILL, "教阿醜", 0.6)
    _go(game, HILL, 0.6)
    _pick(game, "未了之事")
    text = fill_marks(game.content.events["wolong_7"].text, s)
    assert "名冊在你手上" in text and "好眼睛看著鄭家" not in text
    _pick(game, "交給阿醜")
    progress = _progress(game)
    assert progress.ending == "shelf"
    end = [c for c in s.player.story_cards if c.kind == "end"][-1]
    assert "黃老從此是這塊地的佃農" in end.text
    assert "隆中藏書" in s.player.lasting and "隆中藏書" in s.player.flags
    note = s.player.annals[-1].text
    assert "陪他走到隆中" in note and "宋母所贈" not in note and "{" not in note
    # 一週後在潁水邊：記了「諾」，宋母先問
    s.player.story_cards = []
    _go(game, RIVER, 7)
    storyline.tick(s, game.content, game.world)
    after = [c for c in s.player.story_cards if c.kind == "after"]
    assert len(after) == 1 and after[0].text.startswith("她看見你，先問") and "他的名字，寫得那麼大" in after[0].text
    # 跨季旗標
    game._reset_player_for_new_season(s.player.season_number + 1)
    assert "隆中藏書" in game.state.player.flags


def test_late_when_you_never_reach_the_hill():
    game = _begin()
    s = game.state
    _pick(game, "寫得很好")
    _go(game, "yingchuan", 20)  # 一直沒去：每一段過期往下一段，到隆中岡那一段過期就是來不及
    for _ in range(8):
        storyline.tick(s, game.content, game.world)
        _go(game, "yingchuan", 4)
    progress = _progress(game)
    assert progress.ending == "late"
    end = [c for c in s.player.story_cards if c.kind == "end"][-1]
    assert end.failed and "少了一卷" in end.text
    assert "惟餘書一穴、灰一堆" in s.player.annals[-1].text
