"""長篇奇事《賣兒契》（企劃者 2026-10-27）與它用到的引擎：照記號換段落（storyline.vary）、多日段（wait_days）、
餘波（StoryEnding.after）、紀念物與跨季旗標。用正式內容走完兩條路，整個檔標 slow。"""
from __future__ import annotations

import pytest
from jianfa_kit import jianfa_game, ready

from tianxia import storyline
from tianxia.rules import day_seconds, fill_marks

pytestmark = pytest.mark.slow

WILDS, MARKET = "runan_wilds", "runan_market"


def _pick(game, words: str) -> list[str]:
    """按眼前選單上寫著 words 的那一顆（按得下去的）。"""
    for opt in game.options():
        if words in opt.label and opt.enabled:
            return game.choose(opt.id)
    raise AssertionError(f"沒有「{words}」：{[o.label for o in game.options()]}")


def _go(game, loc: str, days: float = 0) -> None:
    s = game.state
    s.player.location, s.player.journey = loc, None
    s.world.time += days * day_seconds(game.content, s.world) + 1


def _begin(silver: int = 0):
    game = ready(jianfa_game(), side="guan", loc=WILDS, level=20)
    game.state.player.stats["silver"] = silver
    game._story_begin(game.content.storylines["maier"])
    assert game.state.pending_event == "maier_1"
    return game


def _to_camp(game, act1: str = "照實念", act2: str = "我要去西華", act3: str = "陪他把鍋抬回去", act4: str = "讓孩子上車"):
    s = game.state
    _pick(game, "識得幾個")
    assert s.pending_event == "maier_1b"
    _pick(game, act1)
    assert "草蚱蜢" in s.player.keepsakes
    _go(game, MARKET)
    _pick(game, "未了之事")
    _pick(game, act2)
    _go(game, MARKET, 0.6)  # 第二天晚上
    _pick(game, "未了之事")
    assert s.pending_event == "maier_3"
    _pick(game, act3)
    _go(game, MARKET, 0.3)
    _pick(game, "未了之事")
    _pick(game, act4)
    _go(game, WILDS)
    _pick(game, "未了之事")
    assert s.pending_event == "maier_5"


def _days(game, day1: str, day2: str, day3: str) -> None:
    for words in (day1, day2, day3):
        progress = game.state.player.storylines["maier"]
        assert storyline.waiting(game.state, game.content, progress, storyline.current(game.content, progress)[1])
        assert not any("未了之事" in o.label for o in game.options())  # 還沒到時候：沒有那一顆
        _go(game, WILDS, 0.6)
        _pick(game, "未了之事")
        _pick(game, words)


def test_home_path_recalls_marks_and_leaves_aftermath_and_keepsake_across_seasons():
    game = _begin()
    s = game.state
    _to_camp(game)
    text = fill_marks(game.content.events["maier_5"].text, s)
    assert "那他知道了吧" in text and "你騙他了" not in text  # 記了「實」
    _pick(game, "把葛三給的草蚱蜢拿出來")
    _pick(game, "我帶你回家")
    _days(game, "寫她的名字", "幫她編", "連夜趕回荒野")
    _go(game, WILDS, 0.6)
    _pick(game, "未了之事")
    text = fill_marks(game.content.events["maier_7"].text, s)
    assert "葛三到營裡的那個傍晚" in text and "是我。」小滿說" in text and "腳上全是血" not in text
    msgs = _pick(game, "帶一家三口")  # 上車過：不用檢定，蘇掌櫃的車
    progress = s.player.storylines["maier"]
    assert progress.ending == "home"
    assert any("這一車的帳，我自己記" in m for m in msgs)
    end = [c for c in s.player.story_cards if c.kind == "end"][-1]
    assert "姊姊會寫字" in end.text
    note = s.player.annals[-1].text
    assert "讀之以實" in note and "教其女書己名" in note and "賴糧商蘇氏之車而出" in note and "{" not in note
    # 餘波：三天後在汝南集市；不在那裡不跳
    s.player.story_cards = []
    _go(game, WILDS, 3)
    msgs, _ = storyline.tick(s, game.content, game.world)
    assert not any(c.kind == "after" for c in s.player.story_cards)
    _go(game, MARKET)
    msgs, _ = storyline.tick(s, game.content, game.world)
    after = [c for c in s.player.story_cards if c.kind == "after"]
    assert len(after) == 1 and "自賣為佃" in after[0].text and "阿禾記" not in after[0].text  # 沒問過蘇掌櫃的來歷
    storyline.tick(s, game.content, game.world)
    assert len([c for c in s.player.story_cards if c.kind == "after"]) == 1  # 一段只一次
    # 紀念物跨季
    s.player.lasting.append("測試旗標")
    game._reset_player_for_new_season(s.player.season_number + 1)
    assert "草蚱蜢" in game.state.player.keepsakes and "測試旗標" in game.state.player.flags


def test_ash_path_when_the_night_passes_without_you():
    game = _begin(silver=100)
    s = game.state
    _to_camp(game, act1="說「是押的", act2="這一行，我買了", act4="什麼也不做")
    assert s.player.stats["silver"] == 60
    _pick(game, "什麼也不拿")
    _pick(game, "撿起一紮柴")
    _days(game, "把木棍還給她", "把你的外衣拆了", "留下來")
    _go(game, "runan", 3)  # 不在營裡，期限過了
    storyline.tick(s, game.content, game.world)
    progress = s.player.storylines["maier"]
    assert progress.ending == "ash"
    assert "一段燒斷的繩子" in s.player.keepsakes
    end = [c for c in s.player.story_cards if c.kind == "end"][-1]
    assert end.failed and "其中一節的顏色跟別的不一樣" in end.text
    assert "紿之曰" in s.player.annals[-1].text


def test_vary_nests_and_quotes_what_was_said():
    game = _begin()
    s = game.state
    progress = s.player.storylines["maier"]
    progress.marks = {"字名": 1}
    progress.said = ["秋後我陪你去", "第二句"]
    text = "{?maier.字永:永|{?maier.字名:名|無}}・{!maier.欺:沒騙}・{?maier.說:他說『{said:maier}』，又說『{said:maier.-1}』}"
    assert storyline.vary(text, s) == "名・沒騙・他說『秋後我陪你去』，又說『第二句』"
    assert storyline.vary("{?nope.x:有|沒有}", s) == "沒有"
